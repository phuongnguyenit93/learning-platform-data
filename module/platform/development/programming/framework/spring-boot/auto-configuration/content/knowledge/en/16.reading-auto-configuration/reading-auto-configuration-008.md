# Distinguishing Documented Contracts from Changeable Implementation Details

## 1. Goal: Reading Source Code Without Turning Assumptions into Guarantees

When reading Spring Boot Auto-Configuration, you typically encounter two kinds of information:

- **Documented contract:** behavior, APIs, configuration properties, conditions, and extension points described in official documentation/Javadoc that users can rely on.
- **Implementation detail:** how a specific version implements that contract—such as internal helper classes, algorithms, private method call order, variable names, collection structures, log text, or how a helper happens to be written.

An implementation detail can accurately explain what happens in the version you are reading. However, if Spring Boot has not committed to that detail in supported docs/APIs, applications should not depend on it as a long-term contract.

For example, Spring Boot 3.3 documentation states that `@ConditionalOnProperty` checks a property and provides `havingValue`/`matchIfMissing`. That is a usable contract. The fact that version 3.3.13 uses an internal condition class, string-comparison helper, or specific order of private helper calls only explains **how it is implemented**, not an API applications should invoke directly.

This lesson helps you:

1. Identify which sources establish a contract.
2. Read source to explain behavior without over-relying on internal details.
3. Design tests around public behavior rather than locking tests to logs or internal class names.
4. Evaluate changes when upgrading Spring Boot.
5. Clearly separate what documentation guarantees, what is merely observed in one version, and what remains a hypothesis.

**Example scope:** Spring Boot 3.3.13, Spring Framework 6.1, and Java 17+. When using another version, open the docs/Javadoc for the exact running version before concluding.

## 2. What Is a Documented Contract?

A documented contract is a description with an official source, clear scope, and stated applicability conditions. In Spring Boot Auto-Configuration, it commonly takes the following forms.

### 2.1. Public Annotations and Properties with Javadoc

Example:

```java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

When reading Javadoc, check:

- Which element types the annotation targets (`@Target`).
- Default values of each attribute (`Default`).
- Semantics of `havingValue` and `matchIfMissing`.
- API version introduced (`Since`).
- Deprecation status and replacement APIs if any.
- Links to related annotations, conditions, or documentation sections.

Attributes with clear Javadoc descriptions tell users what is supported. There is no need to copy Spring Boot's internal matching logic into application code.

### 2.2. Reference Guide

The Reference Guide explains how to use APIs in the larger context: how auto-configurations are discovered, how conditions work, how starters are declared, how to test, how properties are configured, and known limitations.

For instance, Spring Boot 3.3's developing auto-configuration guide describes:

- How to list candidates in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- How to use `@AutoConfiguration`, `@ConditionalOnClass`, and `@ConditionalOnMissingBean`.
- How to test with `ApplicationContextRunner`.
- How to add user configurations and properties to test contexts.
- How to use `ConditionEvaluationReportLoggingListener` to log condition reports at INFO or DEBUG.

This is published usage guidance. When docs describe a specific behavior, keep its applicability conditions intact; do not stretch it into a promise for scenarios the docs never mention.

### 2.3. Public APIs and Intentional Extension Points

A public API typically has a searchable name/package, signature, and Javadoc. However, **being `public` in Java does not automatically mean "recommended as an extension point for every application"**.

Also read:

- Class/interface purpose and the `See Also` section in Javadoc.
- Whether the docs guide applications to use the class.
- Any notes indicating internal, experimental, deprecated, or for removal.
- Whether the API exposes constructors/extension hooks for users to implement, or is solely an object constructed by the framework.
- Which documentation version the API belongs to.

For example, `ApplicationContextRunner` is explicitly introduced by Spring Boot in the auto-configuration testing guide. Starter authors can rely on it for tests. An internal helper that happens to have a `public` modifier without being documented as an extension point should not become a custom library's foundation merely because code can import it.

### 2.4. Configuration Properties and Metadata

For properties, distinguish:

- **Configuration contract:** key names, data types, defaults, meaning, and usage conditions described in the reference guide/Javadoc.
- **Configuration metadata:** metadata supporting IDE completion for property names, types, default values, descriptions, and deprecations when present.
- **Binder/validator internals:** how a particular version binds, converts, validates, or constructs internal objects.

Metadata is helpful for lookup, yet a single metadata file should not be treated as complete behavioral documentation. Check property descriptions and corresponding reference guide sections, especially when a property is conditional or tied to a configuration group.

For example, if docs state that `demo.feature.enabled` is a boolean defaulting to false, that is what users can configure by contract. How the binder converts strings to booleans, which helper is called, and which intermediate objects are allocated are implementation details unless a public API specifies otherwise.

## 3. Common Implementation Details Encountered When Reading Source Code

The following details can help explain the current version, yet should not be treated by default as compatibility guarantees.

| Detail Observed in Source | Why It May Change | Proper Way to Use It |
| --- | --- | --- |
| Internal condition/helper class names | May be renamed, split, merged, or replaced | Read to understand why; use public annotations/APIs in apps |
| Private/package-private methods and call order | Refactoring may alter structure without changing public behavior | Use as a debugging trail for the exact version |
| Internal map/list structures and storage keys | Framework may change representation | Never use reflection to mutate internal data |
| Auto-generated bean names when not guaranteed | Bean naming strategies or config structure may change | Depend on names only when naming is an explicit contract |
| Log order, message text, punctuation, and indentation | Logging formatters/diagnostics may change | Read for diagnosis; do not assert full logs as an API |
| Condition report source strings built from class/method | How reports format sources may change | Prefer asserting bean behavior and needed condition results |
| Internal sorting algorithms | May be optimized or changed while keeping the contract | Rely on ordering only where API/docs publish semantics |
| Private fields, caches, flags, or sentinels | Implementation choices of the current version | Avoid reflection or package-private workarounds |
| Helper invocation counts | May change due to caching, lazy init, or refactoring | Do not treat internal call counts as a contract without a callback API |
| Accidental initialization order in one test | May vary by context, dependencies, or version | Declare dependencies/ordering via proper APIs; test real behavior |

**Key point:** internal details are not wrong or useless. They simply carry a narrower compatibility scope. You can use them to answer "why does Boot 3.3.13 behave this way?", yet you should not build another library on top of them without a compatibility promise.

## 4. Distinguishing with an Auto-Configuration Example

Suppose a starter has a notification feature. Desired contract:

- Enabled only when `demo.notification.enabled=true`.
- If the user has not provided `NotificationSender`, the starter registers a default implementation.
- If the user already provides a matching bean, the starter yields.
- If the feature is disabled, no beans are created by this auto-configuration.

### 4.1. Public Contract Part

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.notification",
    name = "enabled",
    havingValue = "true"
)
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    NotificationSender notificationSender() {
        return new DefaultNotificationSender();
    }
}
```

This is sample code for a starter; `NotificationSender` and `DefaultNotificationSender` are library types. Behaviors users need to know:

1. The property must be true for the configuration class to match.
2. If a matching `NotificationSender` bean is already known when the condition is evaluated, the default bean backs off.
3. If the property is false or missing under the default `matchIfMissing=false`, auto-configuration creates no bean.
4. Applications can replace behavior by registering their own `NotificationSender` bean.

The annotations and attributes are described by Javadoc/reference guide. This is the foundation for writing tests and documentation for the starter.

### 4.2. What You Must Not Infer on Your Own

From the snippet above, do not conclude that:

- Spring always invokes one specific private method before another.
- The default bean name is guaranteed to always be `notificationSender` across every configuration registration approach.
- A specific internal condition class will always be used in future releases.
- Logs must contain an exact sentence, line order, or indentation.
- Every `NotificationSender` bean across the entire system was registered by this auto-configuration.
- The bean instance is guaranteed to be instantiated at the exact moment the configuration class is processed.

If a behavior is not described by the contract, treat it as something to verify on a specific version rather than a starter guarantee.

## 5. Hierarchy of Information Sources When Reading Source Code

When a conflict seems to appear between what you observe in source and what users are told, document the exact version and scope. A useful evaluation hierarchy:

1. **Exact-version Reference Guide:** documented user behavior, conditions, and limits.
2. **Exact-version Javadoc/API:** signatures, defaults, annotation/method semantics, and deprecation status.
3. **Configuration changelog, release notes, and migration guides:** changes across versions, added/removed/changed properties, deprecated APIs and replacements.
4. **Public framework tests and doc examples:** supporting evidence of how authors intend APIs to be used; still verify against docs and version.
5. **Source code at the exact tag/commit:** explains how a specific version implements the contract, uncovers bugs, or clarifies undocumented edge cases.
6. **Logs/stack traces/runtime observations:** evidence of one specific run, which does not automatically become a general contract.

This ordering is a reliability evaluation process, not a claim that source code is unimportant. When hunting bugs, source and stack traces are essential. When designing public APIs for applications, the documented contract is the anchor.

### 5.1. Look Up the Exact Version

Do not open the latest Javadoc and use it to explain an application running Boot 3.3. Determine the actual version from dependency management or runtime, then open matching documentation.

For example:

- Spring Boot 3.3.13: `https://docs.spring.io/spring-boot/3.3/api/java/`
- Spring Boot 3.4.x: use 3.4.x Javadoc/reference.
- Spring Boot 3.5.x: use 3.5.x Javadoc/reference.

If investigating a specific patch release, prefer docs from the same version line and check patch release notes. Different minor lines can change published APIs or behavior.

### 5.2. Use Source Code for Controlled Verification

When you need to read implementation code:

1. Identify the exact artifact and version (e.g., `spring-boot-autoconfigure:3.3.13`).
2. Open the corresponding sources JAR or tag; do not rely on the `main` branch when analyzing Boot 3.3.
3. Start from the observed public API/annotation and trace the invoked conditions/helpers.
4. Note which details explain the outcome, but mark them as implementation details if docs do not commit to them.
5. Cross-check tests and release notes to see if behavior changed in later versions.
6. When reporting, distinguish "per documentation" from "what 3.3.13 source currently does".

You do not need to copy or invoke internal classes directly in application code to prove you understood them. Source is an investigative tool, not necessarily a production dependency.

## 6. What Can Spring Boot Change Between Versions?

"Documented contract" does not mean immutable forever. Supported contracts can still evolve under compatibility policies, major/minor releases, and deprecations.

Under Spring Boot's version support policy:

- Patch releases are expected to maintain backward compatibility with earlier patches **as much as possible**.
- Minor and major releases **may** introduce backward-incompatible API changes.
- When feasible, older APIs are retained and marked deprecated to signal ahead of time that they are no longer recommended.
- Spring Boot has its own deprecation policy; check `@Deprecated`, Javadoc `@deprecated`, deprecated version, and planned removal version.

This is a compatibility policy and guideline, not a guarantee that every dependency, property, or third-party-dependent behavior never changes.

### 6.1. Deprecated Does Not Mean Already Removed

For example, an API may be marked:

```java
/**
 * @deprecated since 3.3.0 for removal in 3.5.0
 */
@Deprecated(since = "3.3.0", forRemoval = true)
public void oldMethod() {
}
```

This is only a syntax illustration. For real APIs, read exact `since`, `forRemoval`, and Javadoc replacements. Do not guess the removal version solely from when you first notice a compiler warning.

When encountering a deprecation:

1. Find the alternative noted in Javadoc.
2. Check which version introduced the alternative.
3. Review the migration guide/release notes of the target version.
4. Migrate and run tests on both the current version and upgraded version if your project supports multiple versions.
5. Do not postpone indefinitely if the API is marked for removal.

### 6.2. Why Release Notes and Configuration Changelogs Matter

Release notes list notable changes, deprecations, and upgrade guidance. Configuration changelogs list properties added, removed, or changed across versions.

For example, Spring Boot 3.3 changed several properties, upgraded dependencies, and deprecated certain APIs. These changes show that **a property or dependency used today is not guaranteed to keep the same status in the next minor line**.

When upgrading, do not fix compile errors alone. Also verify property binding, default values, condition outcomes, and context behavior.

## 7. Writing Tests Against Contracts Rather Than Internal Details

Good tests protect what starter users care about: does the bean appear at the right time, are values right, and does a user bean take precedence?

### 7.1. Public Behavior Test Example

Testing with `ApplicationContextRunner`:

```java
class NotificationAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    NotificationAutoConfiguration.class
                )
            );

    @Test
    void createsDefaultSenderWhenEnabledAndMissing() {
        this.contextRunner
            .withPropertyValues("demo.notification.enabled=true")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(NotificationSender.class);

                assertThat(context.getBean(NotificationSender.class))
                    .isInstanceOf(DefaultNotificationSender.class);
            });
    }

    @Test
    void backsOffWhenUserProvidesSender() {
        this.contextRunner
            .withPropertyValues("demo.notification.enabled=true")
            .withUserConfiguration(UserSenderConfiguration.class)
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(NotificationSender.class);

                assertThat(context.getBean(NotificationSender.class))
                    .isInstanceOf(CustomNotificationSender.class);
            });
    }

    @Test
    void doesNotCreateSenderWhenDisabled() {
        this.contextRunner
            .withPropertyValues("demo.notification.enabled=false")
            .run(context ->
                assertThat(context)
                    .doesNotHaveBean(NotificationSender.class)
            );
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSenderConfiguration {

        @Bean
        NotificationSender customNotificationSender() {
            return new CustomNotificationSender();
        }
    }
}
```

This is an **illustrative snippet**; sender interfaces/classes and JUnit/AssertJ imports must exist in the actual module. `NotificationAutoConfiguration` is explicitly selected in the runner. Spring Boot guides using `ApplicationContextRunner` to create isolated contexts per combination of user configurations, Environment, and conditions.

The assertions here stick to the contract:

- Property enabled and no user bean → one default sender exists.
- Property enabled and user bean exists → user's sender is kept.
- Property disabled → no sender from auto-configuration.

### 7.2. Brittle Tests Locked to Implementation

The following checks generally should not serve as application contract tests:

```text
- Asserting the exact verbatim text of the entire condition log.
- Asserting exact names of internal helper classes.
- Asserting a private method was invoked exactly N times.
- Asserting internal source ordering in the report when that order is unpublished.
- Asserting auto-generated bean names when naming is not part of the contract.
- Using reflection to inspect Spring Boot internal fields.
```

For example, if a log message changes while the bean is still registered properly, a message-based test fails spuriously. Conversely, if the bean disappears while the log text looks similar, a log-only test can miss the bug.

### 7.3. When Is Testing the Condition Report Appropriate?

`ConditionEvaluationReport` and `ConditionEvaluationReportLoggingListener` have public Javadoc in Spring Boot. You can use them for diagnostics or specialized tests when condition reporting itself is the genuine goal.

Still, do not turn every report formatting detail into an application contract. Prefer:

- Asserting bean presence/absence.
- Asserting behavior/configuration values.
- When inspecting conditions is needed, reading structured outcomes instead of matching raw log strings.
- Asserting source keys/messages only if your project intentionally treats them as a contract and accepts maintenance across Boot upgrades.

## 8. Process for Classifying a Finding When Reading Code

Whenever you spot a noteworthy piece of code, answer the following questions.

### 8.1. Which Category Does This Finding Belong To?

| Finding Type | Indicator | How to Write the Conclusion |
| --- | --- | --- |
| **Documented contract** | Clearly described in exact-version reference guide/Javadoc | "Spring Boot 3.3 documents that..." |
| **Public API lacking context** | Public class/method without clear usage guide or extension intent | "The API is accessible; verify whether it is a supported extension point..." |
| **Implementation detail** | Private/package-private helper, field, algorithm, log formatting | "In current 3.3.13 source, the implementation..." |
| **Observed behavior** | Observed via one test or one run | "In this scenario, the observed result is..." |
| **Hypothesis** | Inference not yet backed by docs or tests | "Hypothesis to verify..." |
| **Project contract** | Defined by the project itself via interfaces, docs, tests, config | "The project's starter specifies..." |

Classification tells readers the confidence level and applicability scope of each conclusion.

### 8.2. Example of Writing an Accurate Report

**Unclear scope:**

> Spring Boot always evaluates condition X before condition Y because current source calls X before Y.

**Scoped and evidenced:**

> Spring Boot 3.3 documentation specifies that auto-configurations are ordered by before/after relationships. In 3.3.13 source, the current helper class performs sorting with a specific algorithm. That algorithm is an implementation detail; the starter's tests depend only on the documented bean outcomes.

The second phrasing separates the contract from source evidence, preventing reviewers from mistaking a version observation for a cross-version guarantee.

## 9. Checklist When Reviewing or Upgrading Versions

When reviewing an auto-configuration or upgrading Spring Boot:

1. **Identify the actual version:** check dependency management, BOMs, and runtime artifacts.
2. **Read exact-version docs:** reference guide and Javadoc for the APIs in use.
3. **Check release notes:** look for deprecations, property changes, dependency upgrades, and behavioral changes.
4. **Check migration guides:** review major/minor upgrade requirements.
5. **Classify dependencies on internals:** separate source APIs used directly from source that merely explains implementation.
6. **Audit deprecations:** read alternatives and removal versions; do not ignore forRemoval warnings.
7. **Run contract tests:** property true/false/missing, class present/absent, user/default beans, web/non-web, and real starter scenarios.
8. **Avoid locking tests to logs:** inspect reports/messages only when that is the specific test objective.
9. **Check the dependency graph:** Boot may upgrade third-party libraries whose APIs may also change.
10. **State conclusion scope clearly:** version, source, test cases, and unverified items.

A short review table usable in PRs:

| Finding | Source of Evidence | Classification | Required Tests |
| --- | --- | --- | --- |
| `demo.notification.enabled=true` enables sender | Boot 3.3 reference/Javadoc | Starter documented contract | enabled/disabled/missing |
| User bean causes default back-off | `@ConditionalOnMissingBean` docs | Documented contract | user bean override |
| Internal condition helper name | Source tag 3.3.13 | Implementation detail | Do not assert helper name |
| Log message contains a specific phrase | One test run | Observed behavior | Do not assert verbatim log |
| Newly deprecated property | Changelog/Javadoc | Versioned migration contract | Test old and new config per supported versions |

## 10. Self-Check Exercises

**Question 1.** Javadoc for `@ConditionalOnProperty` describes `havingValue` and `matchIfMissing`. Is this a contract or an implementation detail?  
**Answer:** A documented contract of the API for that version. Applications can rely on those semantics within the supported version range.

**Question 2.** You see Boot 3.3.13 source using a package-private condition class to handle an annotation. Should you import that class into your own starter?  
**Answer:** No. That is an internal detail; use public annotations/APIs and verify results via context tests.

**Question 3.** Your test asserts that condition logs must have exact punctuation, indentation, and source names. When upgrading a Boot patch, the log changes while the beans remain correct. Is the test checking the right contract?  
**Answer:** No, unless the log format itself is a product contract. Assert meaningful beans and outcomes; use logs for diagnosis.

**Question 4.** A class has a `public` modifier. Is that enough to prove it is a stable extension point?  
**Answer:** No. Check Javadoc, the reference guide, the API's purpose, and deprecation/compatibility policies.

**Question 5.** Docs 3.3 state API A is supported, while source 3.3.13 implements it using helper B. Should your application call A or B?  
**Answer:** Call the documented API A. Helper B is only for understanding that exact version's implementation.

**Question 6.** A property is deprecated in a minor release. Can you wait until compilation breaks before changing it?  
**Answer:** You should not. Read `since`, `forRemoval`, replacements, and release notes; plan migration before the removal version.

**Question 7.** A test with `ApplicationContextRunner` proves the default bean is created when a property is enabled. Does it guarantee Spring Boot will always use the same internal condition algorithm?  
**Answer:** No. The test proves observed behavior for that configuration combination and tested version; implementation may change while the contract stays intact.

**Question 8.** When current source and docs appear to conflict, how should you report it?  
**Answer:** Specify the version, API, doc excerpt, and source/test observation; determine whether it is a bug, incomplete documentation, or a hypothesis to verify. Never silently turn an implementation detail into a contract.

## 11. Takeaways and References

- **Exact-version documentation and Javadoc** define what users may rely on in the API.
- **Source code** explains how a specific version implements the contract; private helpers/fields/log formatting do not automatically become contracts.
- The `public` modifier alone does not guarantee a class is a supported extension point.
- Spring Boot strives to preserve compatibility in patch releases; minor/major releases may contain breaking API changes. Follow deprecations and migration guides.
- Tests should protect **behavior**: bean presence/absence, config values, back-off, and meaningful condition outcomes; avoid locking onto report/log details.
- When reporting, classify clearly: documented contract, public API needing confirmation, implementation detail, observed behavior, hypothesis, and project contract.

Official documentation:

1. Spring Boot — [Supported Versions and Release Compatibility](https://github.com/spring-projects/spring-boot/wiki/Supported-Versions).
2. Spring Boot 3.3 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
3. Spring Boot 3.3 — [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).
4. Spring Boot 3.3 — [Spring Boot API Javadoc 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/).
5. Spring Boot — [Deprecations Policy](https://github.com/spring-projects/spring-boot/wiki/Deprecations).
6. Spring Boot 3.3 — [Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes).
7. Spring Boot 3.3 — [Configuration Changelog](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Configuration-Changelog).
8. Spring Boot 3.3.13 — [`@ConditionalOnProperty` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
