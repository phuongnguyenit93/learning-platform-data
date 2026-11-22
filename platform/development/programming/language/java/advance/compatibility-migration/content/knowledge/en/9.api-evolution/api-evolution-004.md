# Using `@Deprecated`, `since`, and `forRemoval` to Communicate the Roadmap

During Java API evolution, not every method or class can be deleted immediately when a better design emerges. Other applications may be calling that API, libraries may be released independently, and some customers need time to upgrade their JDK or dependencies. **Deprecation** is the mechanism for announcing that an API is no longer recommended for use, while creating a transition window for users to migrate to a replacement solution.

Since Java 9, the `@Deprecated` annotation has two important attributes: `since` and `forRemoval`. Combining them with Javadoc, release notes, and a version support policy helps API authors clearly communicate three pieces of information: **from which version the API became deprecated, whether removal is planned, and where users should migrate**.

This lesson belongs to the **API Evolution** group of the **Java Advance Compatibility Migration** module. The content applies to maintainers of libraries, frameworks, SDKs, or shared APIs in a multi-module system, especially when compatibility must be preserved while upgrading JDK and dependency versions.

## 1. Learning Objectives

After this lesson, learners can:

- Understand how `@Deprecated` affects the compiler, documentation, and API consumers.
- Properly use `since` and `forRemoval` to describe API status and lifecycle direction.
- Distinguish the annotation's `since` attribute from the `@since` and `@deprecated` tags in Javadoc.
- Design a migration path from an old API to a new API while maintaining a compatibility window.
- Identify `javac` warnings, use tools to audit deprecated APIs, and plan upgrades.
- Write release notes, migration guides, and verifiable API removal criteria.

## 2. What Does `@Deprecated` Actually Mean?

`java.lang.Deprecated` is a standard annotation. When attached to an API, the author announces that the API is no longer recommended for new code. Reasons may include an unsuitable design, an existing replacement, misleading behavior, security limitations, or a plan to remove the feature.

Simple example:

```java
public final class UserApi {
    private UserApi() {}

    @Deprecated
    public static String lookup(String userId) {
        return findNameById(userId);
    }

    public static String findNameById(String userId) {
        return "user-" + userId;
    }
}
```

New clients should call `findNameById`, while `lookup` still exists and can be called. `@Deprecated` does **not** automatically delete the method, prevent execution, change the return value, or schedule removal. It sends a signal to compilers, IDEs, analysis tools, and API users.

Common effects:

- When other source code uses a deprecated API, `javac` can emit warnings; IDEs usually mark the call and suggest viewing replacement documentation.
- Javadoc can display the API in the deprecated list and explain the roadmap if thoroughly written.
- Compatibility analysis tools can count call sites using old APIs for migration purposes.
- The API remains part of the public binary until developers actually modify or remove it.

Do not use `@Deprecated` as a generic label for every rarely used piece of code. You must identify the reason and replacement approach; without a migration path, warnings hardly lead to concrete action.

## 3. `since` and `forRemoval` in Java 9 and Later

Since Java 9, `@Deprecated` allows declaring two additional elements:

```java
@Deprecated(since = "2.4", forRemoval = false)
public static String lookup(String userId) {
    return findNameById(userId);
}
```

### 3.1. `since`: From Which Version Was the API Deprecated?

`since` is a string (`String`) describing **the version where deprecation began**. For JDK APIs, the value can be a Java version; for APIs belonging to a custom library, the value is usually the release version of that library itself.

For example:

```java
@Deprecated(since = "2.4")
public void connectLegacy() { /* ... */ }
```

Here, `2.4` only has meaning in the context of the library's versioning convention. It does not automatically mean Java 2.4, JDK 24, or a specific calendar date.

Points to remember:

- `since` answers the question **“From which release was it deprecated?”**, not “In which release did the API first appear?”.
- This value is human-readable metadata; the compiler does not automatically cross-check it against a release schedule and does not enforce a fixed version format.
- If undeclared, the default value of `since` is an empty string, meaning no version information is present in the annotation.
- When later changing `forRemoval` from `false` to `true`, `since` is normally kept unchanged to preserve the history of when deprecation began; the milestone when it moved to pending removal can be recorded in release notes.

### 3.2. `forRemoval`: Is the API Intended for Removal?

`forRemoval` is a boolean value:

```java
@Deprecated(since = "2.4", forRemoval = false)
public void oldOperation() { /* ... */ }
```

`false` indicates the API is discouraged from use but **not yet marked as scheduled for removal**. This is also the default value, so `@Deprecated(since = "2.4")` is equivalent to declaring `forRemoval = false`.

When the API enters the planned-deletion phase:

```java
@Deprecated(since = "2.4", forRemoval = true)
public void oldOperation() { /* ... */ }
```

`true` is a stronger signal: the author **intends to remove the API in a future version**. However, this annotation has no `removeIn` field and does not guarantee the API will be deleted on a specific date. Target milestones, conditions, and exceptions must be recorded in the support policy or release notes.

### 3.3. Quick Understanding of the Three Declaration Forms

| Declaration | Meaning | Missing Information |
| --- | --- | --- |
| `@Deprecated` | The API is no longer recommended. | Does not record the release deprecation started; does not mark intended removal. |
| `@Deprecated(since = "2.4")` | The API has been deprecated since release 2.4. | No removal intent declared; does not point to a replacement API. |
| `@Deprecated(since = "2.4", forRemoval = true)` | The API has been deprecated since 2.4 and is currently intended for removal. | Does not state when it will be deleted or how to migrate. |

When notifying users, include both the reason and the migration path. `since` and `forRemoval` alone cannot replace documentation.

### 3.4. Caution When Still Compiling with Java 8

Java 8 already supports `@Deprecated` but does not yet have the two annotation elements `since` and `forRemoval`. Therefore, source code that must compile against Java 8 APIs should use:

```java
/**
 * @deprecated Since library version 2.4, use {@link #findById(String)}.
 */
@Deprecated
public String findLegacy(String id) {
    return findById(id);
}
```

If the library still commits to supporting Java 8, do not add `@Deprecated(since = ..., forRemoval = ...)` into source compiled with `--release 8`. The compiler checks the annotation API against Java 8, where those elements do not exist yet. Metadata about the deprecation timeline can be kept in Javadoc and release notes; only use the new elements when the minimum source/API release permits.

## 4. Distinguishing Annotations and Javadoc Tags

There are three components easily confused because of similar names:

| Syntax | Where Is It? | Answers the Question |
| --- | --- | --- |
| `@Deprecated(since = "2.4")` | Annotation in Java source | From which release was the API marked deprecated? |
| `@since 1.0` | Tag in Javadoc | From which release was the API first introduced? |
| `@deprecated ...` | Tag in Javadoc | Why should the API not be used and what replaces it? |

`@since` in Javadoc describes **the version the API appeared**, not the version it was deprecated. Meanwhile, lowercase `@deprecated` in Javadoc is where to explain the reason, migration steps, and link to the replacement API. Both are documentation tags, not Java annotation attributes.

Full example:

```java
package com.example.accounts;

public final class AccountApi {
    private AccountApi() {}

    /**
     * Returns the account name by identifier.
     *
     * @param id the account ID
     * @return the account name
     * @since 1.0
     * @deprecated Since 2.4, use
     *             {@link #findNameById(String)}. The old method
     *             is kept so clients have time to upgrade.
     */
    @Deprecated(since = "2.4", forRemoval = false)
    public static String getName(String id) {
        return findNameById(id);
    }

    /**
     * Looks up the account name by identifier.
     *
     * @param id the account ID
     * @return the account name
     * @since 2.4
     */
    public static String findNameById(String id) {
        return "account-" + id;
    }
}
```

In the example:

- `getName` was introduced in 1.0 but only deprecated starting in 2.4.
- `findNameById` is a new API appearing in 2.4.
- The annotation describes machine-readable status; Javadoc explains how users must act.
- Keeping `getName` delegating to `findNameById` is a way to preserve old behavior during the transition period, provided the two methods truly have equivalent contracts.

When writing Javadoc, prioritize `{@link ...}` to the exact replacement method or class, and describe differences in return values, exceptions, nullability, and behavior if any. A single sentence saying “This API is old” is not enough to help users update their code.

## 5. Designing an API Evolution Roadmap with Clear Phases

Deprecation is most useful when it sits within a release plan that users can follow.

### 5.1. Example of a Multi-Version Roadmap

Suppose the `account-client` library has had the `getName()` API since version 1.0. The development team wants to switch to `findNameById()` and plans to remove the old API in a major release. An illustrative roadmap:

| Library Version | Old API Status | Developer Work |
| --- | --- | --- |
| 1.0 | Supported API | Publish usage contract and test normally. |
| 2.4 | Deprecated, `forRemoval = false` | Add replacement API, Javadoc, migration examples, and announcement in release notes. |
| 3.0 | Deprecated, `forRemoval = true` | Keep API compatible in the final phase, emit stronger warnings, and announce removal target. |
| 4.0 | Removed per plan | Delete old API when conditions are met, update API diff, migration guide, and release notes. |

This is only an illustrative model; the project must follow its actual versioning policy and support window. An API may need multiple releases to transition, or have to be handled faster if there is a severe risk.

When moving to phase 3.0, keep the original deprecated version metadata:

```java
/**
 * @since 1.0
 * @deprecated Since 2.4, use {@link #findNameById(String)}.
 *             Scheduled for removal per the published roadmap for 4.0.
 */
@Deprecated(since = "2.4", forRemoval = true)
public static String getName(String id) {
    return findNameById(id);
}
```

In the 3.0 release notes, clearly state that `forRemoval` just switched to `true`. Do not change `since` to `3.0`, because doing so loses track of when the API originally became deprecated.

### 5.2. Conditions for Switching to `forRemoval = true`

Before marking an API for removal, the API maintenance team should know:

- Is the replacement API ready with sufficient documentation?
- Is the replacement API supported on the JDKs and environments customers are using?
- Have users had the necessary time and tools to migrate?
- Which independent clients, plugins, SDKs, or services still depend on the old API?
- Does removal belong to a major release or are there exceptions under the versioning policy?
- Are there customer support mechanisms and deferral options if the impact level is high?

`forRemoval = true` should be a responsible compatibility decision, not merely a way to make warnings more prominent.

### 5.3. When Should a Deprecated API Be Kept Long-Term?

There are cases where an old API still needs to remain due to long-term support contracts, legacy systems that are hard to upgrade, or excessively high change costs. When no removal decision has been made yet, `forRemoval = false` is the more appropriate signal.

However, keeping an API does not mean encouraging its use in new code. Developers can still direct all new usage to the redesigned API while maintaining old behavior with clear tests and documentation.

## 6. Replacing APIs Without Breaking Clients Too Early

### 6.1. Keeping Old Entry Points During the Transition Period

If the new API is equivalent to the old API, a simple approach is to have the old method delegate to the new method:

```java
public class Formatter {
    public String formatText(String input) {
        return input == null ? "" : input.trim();
    }

    /**
     * @deprecated Since 2.1, use {@link #formatText(String)}.
     */
    @Deprecated(since = "2.1", forRemoval = false)
    public String normalize(String input) {
        return formatText(input);
    }
}
```

Keeping the name, descriptor, and access level of `normalize` helps old calls continue linking in normal situations. However, behavior still needs testing: if the new `formatText` changes `null` handling, locale, exceptions, or data normalization, you cannot assume the two APIs are equivalent.

### 6.2. If the New Contract Differs from the Old Contract

When the new API changes return types, parameter types, or error handling, one-line delegation may not be safe. Put an adapter in place to handle the differences:

```java
public enum Mode { FAST, SAFE }

public final class Decoder {
    public byte[] decode(String text, Mode mode) {
        // Decoding details belong to the library's implementation.
        return text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }

    /**
     * @deprecated Since 2.0, call {@link #decode(String, Mode)}
     *             and specify the desired mode.
     */
    @Deprecated(since = "2.0", forRemoval = false)
    public byte[] decode(String text) {
        return decode(text, Mode.SAFE);
    }
}
```

The example illustrates pinning old default behavior via a new parameter. In a real project, the implementation and adapter must preserve the published rules of the old API; do not silently change results just because it is deprecated.

### 6.3. Do Not Delete an API Just Because `@Deprecated` Was Attached

For independently released libraries, clients may exist as compiled binaries. If you delete or change the descriptor of a method that clients still call, runtime can encounter errors such as `NoSuchMethodError`. For deleted classes, `NoClassDefFoundError` or `ClassNotFoundException` can occur depending on loading mechanism.

Therefore, deprecation should precede removal in a communicated roadmap, except in special cases where the organization accepts a breaking change. When deciding to remove, check both source clients and binary clients, not just the library's own build.

## 7. Impact on Compilers and Analysis Tools

### 7.1. Detecting Deprecated Calls with `javac`

With client source:

```java
public final class Client {
    public static void main(String[] args) {
        System.out.println(AccountApi.getName("a123"));
    }
}
```

You can compile with diagnostic options:

```bash
javac -Xlint:deprecation -Xlint:removal \
  -cp path/to/account-client.jar \
  Client.java
```

The example uses `\` for line continuation in Unix-like shells; on Windows, adjust for PowerShell or `cmd`. In Maven/Gradle projects, configure compiler arguments in the build script or active plugin rather than running `javac` manually for the whole project.

Two types of warnings to distinguish:

| Option/Warning | Notable Case | Action |
| --- | --- | --- |
| `-Xlint:deprecation` | Usage of standard deprecated API. | Check Javadoc, find replacement API, and plan migration. |
| `-Xlint:removal` | Usage of API marked `forRemoval = true`. | Prioritize replacement, check announced removal milestone and risk of upcoming releases. |
| `-Werror` | Build policy turns warnings into errors. | Triage warnings and decide controlled handling; do not mask all warnings. |

Depending on the JDK and compiler, message contents and default-enabled warnings may differ. Always record compiler version, flags, and dependencies when comparing migration results.

### 7.2. How Should `@SuppressWarnings` Be Used?

In cases where a call cannot be fixed immediately, you can scope the warning at the specific location:

```java
@SuppressWarnings("deprecation")
static String callLegacy(String id) {
    return AccountApi.getName(id);
}
```

For APIs marked for removal, the JDK supports the corresponding suppression type:

```java
@SuppressWarnings("removal")
static String callPendingRemoval(String id) {
    return AccountApi.getName(id);
}
```

Use only when there is a reason, an accountable owner, and a replacement plan. Suppression does not make the API safe or prevent the library from deleting the method in a future release. Do not place suppression at the whole-module level just to hide build warnings.

### 7.3. Using `jdeprscan` Within Its Proper Scope

The JDK provides the `jdeprscan` tool to analyze compiled classes/JARs and find references to deprecated Java SE APIs belonging to releases supported by the tool. For example:

```bash
jdeprscan --release 11 path/to/application.jar
```

Some JDK versions also support an option to filter APIs marked for removal; check `jdeprscan --help` on the active JDK before automating. This command is **not** a universal scanner for all deprecated APIs of third-party libraries. For self-developed libraries, you can use compiler warnings, API diffs, source search, and client tests.

Static analysis only covers classes and references present in the provided input. Reflection, classes loaded from configuration, and runtime-loaded plugins may require separate verification.

### 7.4. Reading Javadoc and Release Notes Alongside Warnings

Compiler warnings usually only point out the name of the deprecated or removal-marked API. Programmers need to open Javadoc to learn:

- Why the old API should not be used.
- The replacement API or pattern.
- Contract, parameter, exception, data, and behavioral differences.
- The release milestone starting deprecation and planned removal if any.
- Migration steps when the new API cannot be substituted with an equivalent single call.

If Javadoc lacks guidance, request the API owner to add documentation instead of merely suppressing the warning.

## 8. Communicating the Roadmap Through Multiple Channels

Annotations are part of communicating with library consumers, but users do not always recompile frequently. A deprecation roadmap needs to be delivered through channels that teams using the API actually monitor.

### 8.1. Javadoc at the Usage Site

Each deprecated API should have concise, direct information at its declaration. Describe the reason and migration path. If differences between the old and new APIs are complex, link to the migration guide.

### 8.2. Release Notes by Version

When an API changes status, release notes should record:

- The old API name, the release deprecation started, and the reason.
- The new API name and a short migration example.
- That `forRemoval` transitioned to `true`, if applicable.
- The expected removal milestone and committed support scope; distinguish planned from firm decisions.
- Breaking changes when the API is actually removed or its signature changes.

Example release notes content:

> Since library 2.4, `AccountApi.getName(String)` is marked deprecated; use `findNameById(String)`. In 3.0, the old API transitions to `forRemoval = true`. Per the current roadmap, removal is planned for 4.0; clients should complete migration before upgrading to 4.0.

### 8.3. Migration Guide for Users

For complex changes, provide before/after examples:

```java
// Before
String name = AccountApi.getName(id);

// After
String name = AccountApi.findNameById(id);
```

If the change is not just a rename, the guide must clearly explain how to convert data, handle errors, update configuration, or adjust default behavior. For multi-module systems, provide a mapping table of old API → new API and guidance on the order of updating dependencies/clients.

### 8.4. Tracking Usage of Old APIs

In an internal repository, deprecated calls can be found via compiler warnings, IDE inspections, static analysis, and source search. For a library ecosystem with many clients, gather compatibility information from shared modules and user feedback.

There is no need to add runtime logging into every deprecated API; doing so can increase operational cost, expose data, or create noisy logs. If usage measurement is needed, design metrics and collection limits appropriate for the system.

## 9. Versioning Policy and Compatibility Commitments

`@Deprecated` does not by itself define Semantic Versioning or a release schedule. The development team must publish a separate support policy. Several decisions usually need agreement:

- Will the API be kept for at least one or more minor releases after deprecation?
- When does an API transition to `forRemoval = true`?
- Is public API removal performed only in major releases?
- Are there long-term support releases or maintenance branches that continue keeping the old API?
- Do any modules or customers require exceptions due to binary compatibility?
- Who approves the timing of removal and who confirms the number of migrated clients?

For products following SemVer, removing a public API is usually a breaking change and typically belongs in a major release. However, a project's actual policy may differ; do not infer the removal milestone solely from `forRemoval = true`.

When an API belongs to a shared library, build a **compatibility matrix** across library versions, JDKs, frameworks, and major clients. A replacement API may only be usable on a newer JDK; that impacts the migration capability of customers still on older JDKs. Documentation must explicitly state prerequisites rather than merely commanding “switch to the new API”.

## 10. Common Mistakes

### 10.1. Confusing `since` with `@since`

`@Deprecated(since = "2.4")` records when the API was deprecated. The Javadoc tag `@since 1.0` records when the API appeared. Putting the same value in both fields when historically inaccurate causes users to misunderstand the API lifecycle.

### 10.2. Setting `forRemoval = true` Without a Plan

`forRemoval = true` signals that the API may disappear in the future. Without a release policy, replacement, or accountable owner, users do not know how to act and may lose trust in warnings.

### 10.3. Writing the Annotation Without Javadoc `@deprecated`

The annotation reports status but does not answer “what replaces it”. Have clear Javadoc linking to the new API, behavioral differences, and migration documentation.

### 10.4. Treating Deprecation as Removal

A deprecated API can still run. Conversely, deleting an API is a change requiring source and binary compatibility evaluation. Do not use `@Deprecated` to infer that old clients automatically switch to the new API.

### 10.5. Deleting a Method Immediately After Deprecation

Clients that have not updated in time may fail to compile or hit `NoSuchMethodError` when using old binaries. Determine the transition window, usage level, and appropriate release for removal.

### 10.6. Changing `since` Every Time Status Changes

If an API was deprecated in 2.4 and only marked `forRemoval = true` in 3.0, `since` should still reflect 2.4. The milestone transitioning to `forRemoval` can be stated in release notes, without overwriting deprecation history.

### 10.7. Using `@SuppressWarnings` to Evade All Migration Work

Suppression only hides warnings in the scope where it is applied. It does not fix an API about to be removed. Scope suppressions narrowly, state the reason, and plan to remove the suppression along with the legacy API.

### 10.8. Forgetting Clients That Have Not Been Recompiled

A library maintainer may see no warnings inside their own project yet still have many binary clients using the old API. Before removal, check independent clients, plugins, and integrated systems along with their release timelines.

## 11. Process for API Maintainers

### Step 1: Identify the Reason for Deprecation

Record the design, security, performance, or business issue making the old API no longer recommended. Confirm whether the replacement API solves the issue and can be used in currently supported environments.

### Step 2: Publish the Replacement API and Contract

Ensure the new method/class has documentation, tests, and examples. If behavior differs from the old API, clearly describe the changes, especially return data, exceptions, `null`, concurrency, and security.

### Step 3: Mark Deprecation with Annotation and Javadoc

For Java 9+:

```java
/**
 * @since 1.0
 * @deprecated Since 2.4, use {@link #newMethod()}.
 */
@Deprecated(since = "2.4", forRemoval = false)
public void oldMethod() {
    newMethod();
}

public void newMethod() {
    // Replacement API.
}
```

For Java 8, keep `@Deprecated` without attributes and record release info in Javadoc.

### Step 4: Publish Migration Information

Update release notes, migration guide, API reference, and client examples. Specify the version deprecation began, the replacement, and urgency level.

### Step 5: Monitor Clients and Compatibility

Compile critical clients with deprecation warnings enabled, track usage in source code, and test binary clients when needed. Any behavioral changes in the old API's adapter must have regression tests.

### Step 6: Decide When to Transition to `forRemoval = true`

When support policy conditions are met, change the status, update Javadoc and release notes, and announce the planned removal timing. Keep `since` as the first release marked deprecated.

### Step 7: Remove When Conditions Are Met

Before deleting the API, confirm the appropriate release, that supported clients have a migration path, usage-detection tools have been run, and the migration guide is complete. After deletion, verify source compatibility, binary compatibility, and behavior according to the new release's committed scope.

## 12. Process for API Consumers

When encountering deprecation warnings during a JDK upgrade or library upgrade project:

1. **Verify the API and version:** locate the warned method/class along with the actual dependency in the build.
2. **Read the status:** check `since`, `forRemoval`, Javadoc `@deprecated`, and release notes.
3. **Assess priority:** `forRemoval = true` APIs need special attention if planning to upgrade to a release intending to remove them.
4. **Identify the replacement:** verify compatibility of the replacement API with the supported JDK, framework, and environment.
5. **Modify according to the new contract:** update source code, convert data/configuration if needed, and preserve business behavior.
6. **Test:** run unit, integration, and regression tests for affected flows.
7. **Remove temporary artifacts:** once migrated, remove suppressions, unneeded legacy adapters, and related warnings.

If immediate migration is not possible, record the reason, risks, responsible owner, and a reasonable deadline; avoid letting warnings linger without anyone responsible.

## 13. Template for Recording Deprecation in Project Documentation

A tracking table helps synchronize source code, release notes, and client team work:

| Field | Content to Record |
| --- | --- |
| Old API | Package, class, and relevant method/field signature. |
| Introduced in | Version the API first appeared (`@since`). |
| Deprecated since | Version deprecation started (`@Deprecated(since = ...)`). |
| For removal | `false` or `true`, with status transition version if applicable. |
| Reason | Why the API is no longer recommended. |
| Replacement API | Name, Javadoc link, and usage conditions. |
| Behavioral differences | Parameters, results, exceptions, `null`, concurrency, or security. |
| Removal target | Planned version if decided by policy; write “undetermined” if not yet decided. |
| Client scope | Modules, plugins, services, or customers still using it. |
| Owner | API owner and migration support point of contact. |
| Evidence | Build warnings, API diffs, migration tests, and release notes. |

For example, one row might describe: `AccountApi.getName(String)` introduced in 1.0, deprecated in 2.4, changed to `forRemoval = true` in 3.0, planned removal in 4.0; replacement API is `findNameById(String)`. These milestones must be recorded consistently in source, Javadoc, and release announcements.

## 14. Checklist Before Marking and Before Removing an API

**When starting deprecation:**

- [ ] Clearly described the reason for discouraging the old API.
- [ ] Provided a viable replacement API or approach.
- [ ] Chosen the correct version for the annotation's `since`.
- [ ] Distinguished `@since` (API introduction) from `@deprecated` (replacement guidance).
- [ ] Confirmed the source level supports `since` and `forRemoval` attributes if used.
- [ ] Added Javadoc, migration examples, and release notes.
- [ ] Tested the adapter if keeping the old method delegating to the new API.

**When preparing `forRemoval = true` or removal:**

- [ ] Established a support duration policy and planned release milestone.
- [ ] Evaluated source and binary clients still depending on it.
- [ ] Confirmed usability of the replacement API on supported JDKs and frameworks.
- [ ] Announced the status change and migration guide.
- [ ] Kept the `since` value from the initial deprecation.
- [ ] Verified source/binary compatibility per product commitments.
- [ ] Defined how to handle exceptions or deferrals if critical clients cannot upgrade yet.

## 15. Practical Conclusion

`@Deprecated` is a technical signal indicating an API is no longer recommended. `since` records the release deprecation started, while `forRemoval` indicates the author intends to remove the API in the future. `@since` and `@deprecated` in Javadoc supplement the origin history and migration guidance that the annotation cannot express by itself.

In Java compatibility migration, treat deprecation as a **communication and compatibility contract across multiple releases**: publish the replacement API, maintain an appropriate transition window, guide clients, monitor warnings, and remove the API only when support conditions allow. When code, Javadoc, release notes, and tests tell the same roadmap, library users can proactively upgrade before breaking changes occur.
