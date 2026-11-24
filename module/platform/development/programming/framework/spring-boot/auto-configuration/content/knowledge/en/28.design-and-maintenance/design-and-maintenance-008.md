# Review dependency changes to catch unexpected feature activation

## 1. Why can adding a library change application behavior?

In Spring Boot, dependencies do not merely provide classes for your code to call directly. JARs on the runtime classpath can also cause Spring Boot to discover additional auto-configurations, satisfy conditions of existing configurations, register new beans, or cause another configuration to back off.

Therefore, a small change in `pom.xml`, `build.gradle`, or a BOM can change application behavior even when not a single line of Java is modified.

Examples:

- Adding the JDBC starter and H2 can cause Spring Boot to auto-configure an embedded `DataSource` when no application-provided `DataSource` exists.
- Adding the Web MVC starter can turn the application into a servlet web application and trigger MVC configuration along with an embedded web server.
- Adding Spring Security to a web application can activate security auto-configuration and default protection rules if the application has not declared its own `SecurityFilterChain`.
- Adding Actuator can register management infrastructure and corresponding endpoints; which endpoints are exposed over HTTP still depends on exposure configuration.
- Adding a library with its own registry or driver can activate metrics, database, messaging, or serialization integrations if the relevant conditions match.

What must be reviewed is **the behavioral impact of the resolved dependency graph**, not just the direct dependency line a developer added.

## 2. Two mechanisms by which a new dependency activates auto-configuration

### 2.1. A new JAR introduces auto-configuration candidates

A JAR can contain the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

This file lists auto-configuration classes Spring Boot can consider. When a dependency containing that file is added to the application, the library's configuration classes become candidates during startup.

Example library resource:

~~~text
com.example.search.autoconfigure.SearchClientAutoConfiguration
com.example.search.autoconfigure.SearchMetricsAutoConfiguration
~~~

Spring Boot looks for this resource across JARs on the classpath. Each declared class can be applied if its conditions are satisfied.

Thus, adding a starter can alter the entire set of auto-configuration candidates even if the application never imports those configuration classes directly.

### 2.2. A new JAR satisfies conditions of an existing auto-configuration

An auto-configuration already present in the application might previously have failed to match due to a missing class, bean, or property. When a new dependency is added, that condition can flip from false to true.

Common conditions:

| Condition | What Spring Boot checks | Dependency impact |
|---|---|---|
| `@ConditionalOnClass` | Whether the specified class is on the classpath | A new JAR may supply the missing class |
| `@ConditionalOnMissingClass` | Whether the specified class is absent | Adding a JAR may stop the configuration from matching |
| `@ConditionalOnBean` | Whether a matching bean is registered | Another integration may create a bean another config needs |
| `@ConditionalOnMissingBean` | No matching bean exists yet | A new bean from another library may make a default bean back off |
| `@ConditionalOnProperty` | Whether a property exists with a matching value | A new dependency may bring default properties or expose existing config |
| `@ConditionalOnResource` | Whether a specific resource exists | A new JAR may supply a resource making the condition match |
| `@ConditionalOnWebApplication` | Whether the context is a web application | A web starter may make web conditions match |

Key point: **having a class on the classpath does not mean every bean of that library is created**. Auto-configuration can also depend on beans, properties, resources, application context types, configuration ordering, and exclusions.

### 2.3. Matching conditions can cause another configuration to back off

Suppose auto-configuration A creates `SearchClient` if no bean of that type exists. A new dependency brings auto-configuration B into the context; B creates `SearchClient` first. When A is evaluated, `@ConditionalOnMissingBean(SearchClient.class)` may no longer match.

Outcomes can include:

- A new bean appears.
- A default bean disappears due to back-off.
- A different implementation gets used.
- Integration ordering or initialization changes.

Therefore, when reviewing dependency changes, compare both positive matches and negative matches in the condition report.

## 3. Dependency changes that must be included in review scope

Do not review only the new dependency line. All of the following changes can affect runtime behavior:

1. **Adding a direct dependency:** adding a starter, driver, client, or integration.
2. **Adding a transitive dependency:** a library version bump pulls in new JARs.
3. **Upgrading versions:** a newer version adds classes, auto-configuration imports, default properties, or altered conditions.
4. **Swapping starters:** a new starter may pull in a different set of integrations.
5. **Removing or excluding dependencies:** classes can disappear, causing an auto-configuration to stop matching or fall back.
6. **Changing BOMs or dependency constraints:** many dependencies resolve to different versions even if the module's build file did not change.
7. **Changing scopes/configurations:** moving a library from test to runtime, provided to runtime, or compileOnly to implementation.
8. **Changing packaging or deployment:** executable JARs, WARs, containers, or application servers can add JARs outside the module's dependency graph.
9. **Changing plugin/build tool versions:** variant resolution, metadata, or dependency graph resolution can shift.
10. **Changing dependency locks:** resolved transitive versions can change even when direct declarations stay unchanged.

A pull request that only bumps a starter's version must still be treated as a potential behavioral change.

## 4. Examples of features that can activate unexpectedly

| Dependency or change | Feature that may activate | Conditions to check |
|---|---|---|
| JDBC starter + H2/HSQLDB | Embedded `DataSource` | Driver on classpath, no other matching `DataSource`/configured URL |
| Web MVC starter | MVC infrastructure and embedded web server | Servlet web context, classpath, and application-provided beans |
| Spring Security starter in a web app | Default security filter chain | No application-provided security configuration |
| Actuator starter | Management/endpoint infrastructure | Whether endpoints are enabled and exposed per config |
| Metrics registry | Registry/exporter for metrics system | Micrometer and registry classes on classpath, matching config conditions |
| Mail starter | `JavaMailSender` infrastructure | Mail classes on classpath and matching auto-configuration |
| Messaging client/starter | Connection factory, listener, or template | Client library, properties, and broker-related conditions |
| Validation provider | Validator infrastructure | Validation API/provider on classpath |

These examples illustrate possibilities under Spring Boot conditions. Exact results depend on the Boot release line, dependency versions, properties, and existing beans. Never conclude a feature is definitely enabled solely from a starter's name.

### 4.1. Embedded database scenario

An application initially has no embedded JDBC driver. After adding H2 to run a small utility, Spring Boot may detect H2 on the classpath. If the application also has JDBC infrastructure and does not provide its own `DataSource`, embedded database auto-configuration can create an in-memory `DataSource`.

This can make the application start successfully against an empty database while developers believe it is connecting to an external database. If a URL property or profile is missing, an embedded database can mask environment configuration mistakes.

Check:

- Which database type the actual `DataSource` bean points to.
- The effective JDBC URL.
- Active profiles and property sources.
- Driver classes and runtime JARs.
- The condition report for `DataSourceAutoConfiguration` and related database configurations.

Do not verify merely that the application has a `DataSource` bean; verify which database that bean points to.

### 4.2. Adding the Security starter scenario

An MVC application previously had no Spring Security. When adding the Security starter, security classes appear on the classpath and security auto-configuration can match.

If the application has not declared its own `SecurityFilterChain`, default configuration can alter request handling, require authentication, or affect controller tests.

Review must check:

- Whether security auto-configuration matched.
- How many `SecurityFilterChain` beans exist.
- Whether the default configuration was created or replaced by user configuration.
- Whether health, actuator, internal APIs, and static resources have the intended access rules.
- Whether integration tests still verify actual security behavior.

### 4.3. Adding Actuator scenario

The Actuator starter can add management infrastructure and endpoint beans. However, an endpoint being created, enabled, and exposed over HTTP are distinct concepts.

Do not infer that adding Actuator makes every endpoint public. Check:

- Which endpoints are enabled.
- Which endpoints are exposed over web or JMX.
- Whether management port/context is separate.
- How security rules protect endpoints.
- Whether production config differs from local/staging.


## 5. Create regression tests for classpath-activated features

When a dependency can trigger unexpected auto-configuration, write tests proving behavior in both states: class present and class absent.

The example below uses H2 as an optional class. The auto-configuration creates a marker bean when the H2 driver is on the classpath. The marker keeps the test focused on the classpath condition; in real applications, the integration bean could be a service or adapter using that library.

### 5.1. Sample auto-configuration

File `src/main/java/com/example/demo/OptionalH2AutoConfiguration.java`:

~~~java
package com.example.demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class OptionalH2AutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.h2.Driver")
    static class H2Configuration {

        @Bean
        @ConditionalOnMissingBean
        EmbeddedDatabaseCapability embeddedDatabaseCapability() {
            return new EmbeddedDatabaseCapability();
        }
    }
}
~~~

File `src/main/java/com/example/demo/EmbeddedDatabaseCapability.java`:

~~~java
package com.example.demo;

public final class EmbeddedDatabaseCapability {
}
~~~

The nested configuration isolates methods and types that depend on the optional library. When H2 is absent, Spring Boot can skip the nested configuration based on metadata conditions before needing to process H2-dependent components.

### 5.2. Test both classpath states

File `src/test/java/com/example/demo/OptionalH2AutoConfigurationTests.java`:

~~~java
package com.example.demo;

import org.h2.Driver;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalH2AutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(OptionalH2AutoConfiguration.class)
                    );

    @Test
    void activatesWhenH2IsOnTheClasspath() {
        runner.run(context ->
                assertThat(context)
                        .hasSingleBean(EmbeddedDatabaseCapability.class)
        );
    }

    @Test
    void backsOffWhenH2IsNotOnTheClasspath() {
        runner.withClassLoader(new FilteredClassLoader(Driver.class))
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(EmbeddedDatabaseCapability.class)
                );
    }
}
~~~

Test dependencies require H2 on the test classpath and Spring Boot test support. With Maven using the Spring Boot BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

With Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.h2database:h2'
}
~~~

Run tests:

~~~bash
./mvnw -Dtest=OptionalH2AutoConfigurationTests test
~~~

Or:

~~~bash
./gradlew test --tests com.example.demo.OptionalH2AutoConfigurationTests
~~~

Expected result: both tests pass. When H2 is present, the marker bean appears; when `FilteredClassLoader` hides H2 from the context classloader, the bean is not created.

This is a regression test for the classpath condition. In real projects, add tests for user-facing beans or endpoints to prove the unexpected feature is controlled.

### 5.3. Check explicit property conditions

A property condition can cause a feature to turn on unexpectedly if code uses `@ConditionalOnProperty` without specifying `havingValue`.

Example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "northstar.search", name = "enabled")
public class SearchAutoConfiguration {
}
~~~

By default, `@ConditionalOnProperty` matches when the property exists and its value does not equal the string `false` (case-insensitive). Thus values like `yes` or `on` can also match.

If the requirement is to enable only on boolean true, write explicitly:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "northstar.search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class SearchAutoConfiguration {
}
~~~

`matchIfMissing` defaults to false. When designing feature flags, decide explicitly how a missing property behaves rather than letting implicit defaults cause surprises.


## 6. Capture the dependency graph before and after changes

The first prerequisite for catching unexpected feature activation is knowing precisely how the runtime classpath changed.

### 6.1. Maven

Save the baseline dependency tree before merging:

~~~bash
./mvnw dependency:tree -Dscope=runtime -Dverbose -DoutputFile=target/runtime-dependencies-before.txt
~~~

After changing dependencies:

~~~bash
./mvnw dependency:tree -Dscope=runtime -Dverbose -DoutputFile=target/runtime-dependencies-after.txt
~~~

Diff the two files to find:

- Newly appearing artifacts.
- Removed artifacts.
- Upgraded or downgraded versions.
- New transitive dependency paths.
- Versions omitted due to conflict mediation.
- Scope changes across compile, runtime, and test.

To investigate a specific library:

~~~bash
./mvnw dependency:tree -Dverbose -Dincludes=com.h2database:h2
~~~

Inspect the POM after parent and BOM resolution:

~~~bash
./mvnw help:effective-pom
~~~

`dependency:analyze` can help spot declared-but-unused dependencies or indirectly used dependencies not declared directly. Results require review because reflection, annotation scanning, ServiceLoader, and framework integrations can hide usage from the tool.

### 6.2. Gradle

Save the runtime dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Investigate a specific artifact:

~~~bash
./gradlew dependencyInsight --dependency h2 --configuration runtimeClasspath
~~~

Compare both compile and runtime:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

If the feature only appears in tests:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency h2 --configuration testRuntimeClasspath
~~~

`dependencies` shows the resolved graph. `dependencyInsight` explains where a dependency was requested and why its version was chosen, such as conflict resolution, constraints, or rules.

### 6.3. Do not compare only direct dependencies

For example, the build file only changes:

~~~groovy
implementation 'com.example:report-client:4.1'
~~~

yet the new version of `report-client` pulls in:

~~~text
com.example:report-client:4.1
  |-- com.example:report-core:4.1
  |-- org.springframework:spring-context-support:...
  |-- com.example:metrics-exporter:...
  |-- com.h2database:h2:...
~~~

These transitive dependencies can introduce classes or auto-configuration candidates. A review looking only at the single `report-client` line will miss the real change.

### 6.4. Identify changes from dependency metadata

Beyond artifact coordinates and versions, inspect new JAR contents:

- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`
- `META-INF/spring.factories` for extension points still using this mechanism
- `META-INF/spring-configuration-metadata.json`
- `META-INF/services/`
- New classes that can satisfy `@ConditionalOnClass`
- Resources checked by `@ConditionalOnResource`

A library can add an auto-configuration imports file in an upgrade, causing new candidates to be discovered even when the application's component scan did not change.

## 7. Read the condition evaluation report to see which features actually matched

The dependency tree shows which JARs are present. It does not show which auto-configurations were ultimately applied. To confirm impact at the Spring context level, compare the condition evaluation report before and after the change.

### 7.1. Enable the report at startup

Run the application with:

~~~bash
java -jar application.jar --debug
~~~

Spring Boot logs the condition evaluation report. Look for:

- **Positive matches:** auto-configurations and conditions that matched.
- **Negative matches:** configurations that did not match along with their reasons.
- **Exclusions:** excluded auto-configurations.
- **Unconditional classes:** configurations without standard conditional guards.

Capture the report at baseline and after changing dependencies. A new auto-configuration under positive matches is a signal to review, though you must read the specific reason before concluding it is a bug.

### 7.2. Use the Actuator conditions endpoint

If the application includes Actuator, the `conditions` endpoint exposes the condition evaluation report as structured data.

Common endpoint path:

~~~text
/actuator/conditions
~~~

The endpoint must be enabled/exposed per Actuator configuration and protected by an appropriate security policy. Do not expose internal reports publicly merely for debugging convenience; the report can leak classes, properties, and application configuration.

### 7.3. Compare bean definitions and behavior

A matching condition does not always create new beans: auto-configuration may back off on individual methods or beans may be overridden by user configuration.

After spotting a new positive match, confirm:

1. Which beans were actually registered.
2. Which configuration class/method created each bean.
3. Whether any bean backed off due to `@ConditionalOnMissingBean` or another configuration.
4. Which properties control the feature.
5. Which endpoints, filters, listeners, schedulers, or clients were actually initialized.
6. Whether the feature creates network connections, threads, consumers, or side effects at startup.

Do not stop at "did the auto-configuration match?". The final question is "how did application behavior change?".

## 8. Check by environment and configuration

The same dependency graph can produce different behaviors across profiles, properties, and context types.

### 8.1. Compare effective properties

Check these sources:

- `application.properties` and `application.yml`.
- Profile-specific configs.
- Environment variables.
- Command-line arguments.
- Config server or Kubernetes ConfigMap/Secrets.
- `@PropertySource` and custom `EnvironmentPostProcessor`.

A new dependency can turn previously unused properties into properties that drive auto-configuration. Therefore, compare effective property values, not just property names searched in source code.

### 8.2. Check the actual classpath of each environment

At minimum compare:

| Environment | Classpath to inspect |
|---|---|
| Local development | `runtimeClasspath` or local launch command |
| Unit/slice tests | `testRuntimeClasspath` |
| Integration tests | Integration test configuration |
| Executable JAR | `BOOT-INF/lib/` inside the artifact |
| WAR/application server | `WEB-INF/lib/` and server shared libraries |
| Container/Kubernetes | Image digest, actual JAR, and mount/runtime configuration |

Do not use a local dependency tree to conclude production runtime has the exact same JARs. Application servers, plugins, mounted libraries, or stale images can alter the actual classpath.

### 8.3. Watch for scope differences

Maven `test` dependencies do not enter production runtime, yet they can cause test slices to activate auto-configurations absent in production.

Gradle `testImplementation` likewise applies only to test configurations. A test can pass thanks to H2 or a mock server on the test classpath while production runtime lacks that dependency.

Conversely, `runtimeOnly` can add drivers or providers at runtime even when source code never imports those classes directly. That is one reason to review the runtime graph rather than only the compile graph.


## 9. Control dependencies to prevent unintended feature activation

### 9.1. Choose starters matching actual required capabilities

Starters often bundle multiple related dependencies to make getting started easy. That is convenient, yet it can also pull in integrations the application does not need.

When reviewing a starter:

- Read the POM or module metadata to see transitive dependencies.
- Inspect the resolved runtime classpath.
- Prefer smaller starters tailored to the exact capability.
- Do not add a large starter just to grab one utility class.
- If only one API is needed, consider declaring the corresponding module rather than the whole starter.
- Check release notes when a starter changes version or alters its dependency set.

Replacing a starter with a single dependency is not always right: a starter may supply auto-configuration, version alignment, and required supporting libraries. Compare behavior and tests before trimming.

### 9.2. Design libraries with optional dependencies

If developing a library consumed by many applications, avoid pulling every integration onto consumers just for one core library.

An easily controlled structure:

~~~text
northstar-core
northstar-autoconfigure
northstar-starter
northstar-h2-integration
northstar-mail-integration
northstar-metrics-integration
~~~

Split integrations by technology so consumers add only what they need. In Maven, dependencies for non-mandatory integrations can be declared `optional` inside the autoconfigure module; consumers needing that feature declare the corresponding starter/integration.

Maven example:

~~~xml
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <optional>true</optional>
</dependency>
~~~

Optional dependencies do not propagate to consumers as regular transitive dependencies. Consumers wanting the H2 integration must add the required dependency explicitly.

In Gradle, publication/variant design and dependency configurations must be chosen to match the library's API/runtime goals; do not treat `compileOnly` as a universal replacement for Maven optional. Inspect published metadata and create a consumer sample to confirm which dependencies actually propagate downstream.

### 9.3. Use properties to activate features explicitly

If an integration has side effects or opens external connections, require an explicit property:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.search.SearchClient")
@ConditionalOnProperty(
        prefix = "northstar.search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class SearchAutoConfiguration {
}
~~~

This approach requires both the library on the classpath and the property explicitly enabled. Adding the JAR does not activate the feature automatically.

Use property conditions when that reflects a sensible product choice. Do not add configuration flags for every simple bean; redundant conditions increase complexity and can hide unnecessary dependencies.

### 9.4. Exclude auto-configuration with clear intent

If an auto-configuration must never run in an application, exclude it by class or class name in `@SpringBootApplication`, or via `spring.autoconfigure.exclude`.

Example using class name:

~~~java
@SpringBootApplication(
        excludeName = "com.example.search.autoconfigure.SearchClientAutoConfiguration"
)
public class Application {
}
~~~

The class name must be the actual auto-configuration candidate in that dependency version. Excluding only prevents the configuration from being applied; it does not remove the JAR from the classpath or fix the dependency graph.

Before excluding, determine why the dependency was pulled in. If the application does not need that integration, removing the dependency or swapping the starter may be the cleaner control. Exclude only when the JAR must remain for other features or for clear architectural reasons.

## 10. Keep the dependency graph stable and reproducible

### 10.1. Use the Spring Boot BOM

Each Spring Boot release provides the `spring-boot-dependencies` BOM containing versions managed and tested together.

- Use the Spring Boot parent or import the BOM in Maven.
- Use the Spring Boot Gradle plugin/dependency management plugin or Gradle platform.
- Avoid overriding baseline library versions without justification.
- Inspect libraries outside the BOM separately, such as Spring Cloud or vendor SDKs.
- When overriding a version, document the reason and add corresponding tests.

The BOM does not guarantee zero new auto-configurations: a library version bumped by the BOM can introduce classes or metadata. Therefore, BOM upgrades also require dependency diffs and condition reports.

### 10.2. Avoid dynamic versions in release builds

Declarations like `1.+`, `latest.release`, or wide version ranges can cause resolved versions to shift over time even without source code changes.

In release pipelines:

- Use explicit versions.
- Review BOM/version catalog changes as part of code review.
- Do not let production builds automatically pull latest without a control gate.
- Record the resolved dependency graph alongside build artifacts.

### 10.3. Use Gradle dependency locking

Gradle supports dependency locking to record resolved versions for locked configurations.

Example:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate/update lock state when intentionally accepting dependency changes:

~~~bash
./gradlew dependencies --write-locks
~~~

Commit lock files alongside build changes. When the dependency graph changes, the lock-file diff helps reviewers see which transitive versions shifted.

Locking makes builds reproducible; it does not prove locked versions are safe or compatible. Tests and condition report reviews are still required.

### 10.4. Use Maven Enforcer or dependency tree checks

Maven can use Enforcer rules to catch dependency convergence issues or unwanted version policies. `dependency:tree -Dverbose` remains an essential tool for tracing dependency paths and mediated versions.

Do not turn on overly strict rules without understanding legitimate exceptions in the graph. The goal is detecting risky version conflicts, not forcing every transitive dependency to a single version when libraries are designed to isolate them.

## 11. Pull request review workflow for dependency changes

Apply the same sequence when adding, removing, or upgrading dependencies.

1. **State the purpose:** which feature the new dependency serves, which module needs it, and why runtime scope is required.
2. **Capture the baseline:** save runtime and test dependency trees before the change.
3. **Review the diff:** identify added/removed/changed artifacts, transitive dependencies, and scope changes.
4. **Read JAR metadata:** inspect auto-configuration imports, service loaders, and new resources if an integration can self-register.
5. **Predict conditions:** locate `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnProperty`, and related configurations.
6. **Compare condition reports:** run with the same profiles/properties before and after the change; investigate new positive/negative matches.
7. **Compare bean behavior:** inspect created beans, filters, listeners, schedulers, clients, endpoints, and connections.
8. **Test both states:** feature dependency present and absent; property enabled and disabled; user bean overrides if applicable.
9. **Check packaging:** verify JAR/WAR/container contains only approved dependencies.
10. **Record the decision:** dependency accepted, narrowed, excluded, or gated behind an opt-in property; document the rationale in the PR.
11. **Lock versions:** update BOM, version catalog, or lock files deliberately.
12. **Run regressions:** unit, slice, integration, and smoke tests using the packaged artifact.

A pull request should answer the question: "Which auto-configurations and beans did this dependency change compared to the baseline?"

## 12. Common review mistakes

1. **Looking only at direct dependencies.** Features can be triggered by transitive dependencies.
2. **Looking only at the compile classpath.** Production auto-configuration depends on the actual runtime classpath.
3. **Assuming adding a class guarantees auto-configuration matches.** Other conditions such as beans, properties, and context type may still fail.
4. **Comparing only positive matches.** A new dependency can cause an older configuration to back off or become a negative match.
5. **Assuming the Actuator starter exposes every endpoint publicly.** Enablement, exposure, and security are separate configuration layers.
6. **Using `@ConditionalOnProperty` without specifying `havingValue`.** Existing values other than `false` can match; use `havingValue="true"` if strict true is required.
7. **Letting drivers/test libraries leak into runtime.** Wrong scopes can activate auto-configurations in production.
8. **Using exclusions to hide unneeded dependencies.** Configuration is disabled, yet the JAR and other integrations remain on the classpath.
9. **Upgrading the BOM without reviewing the graph.** Many transitive versions can change even if the module's build file was untouched.
10. **Believing lock files guarantee dependency safety.** Locking only stabilizes version resolution; it does not verify behavior.
11. **Testing only with `ApplicationContextRunner` registering classes directly.** Consumer tests are needed to verify imports files and artifact publication.
12. **Skipping production profile testing.** Different profiles or property sources can make the same dependency graph behave differently.

## 13. Checklist for completing a review

| Item | Pass criteria |
|---|---|
| Purpose | Know which feature the new dependency serves and which scope is required |
| Dependency graph | Runtime and test graphs compared before/after |
| Transitives | New, removed, or version-changed transitive dependencies identified |
| Auto-configuration | Imports metadata and new candidates inspected |
| Conditions | Positive/negative matches and reasons compared |
| Beans | New beans, backed-off beans, and overrides verified |
| Properties | Effective properties, defaults, and profiles checked |
| Side effects | Connections, threads, listeners, schedulers, and endpoints inspected |
| Packaging | JAR/WAR/image contains only approved dependencies |
| Scope | No test-only or compile-only dependencies leaked into runtime |
| Stability | BOM/version catalog/lock files updated deliberately |
| Tests | Regression tests cover key classpath/property states |
| Review record | PR records activated features and acceptance decision |

## 14. Takeaways

- Spring Boot auto-configures based on JAR dependencies and conditions; adding dependencies can change both candidates and match outcomes.
- A JAR can bring `AutoConfiguration.imports`, classes satisfying `@ConditionalOnClass`, beans, or resources for other conditions.
- New dependencies can also make existing configurations back off via `@ConditionalOnMissingBean`.
- The dependency tree shows the resolved graph; the condition report shows which auto-configurations matched and why; bean inspection/tests show actual behavior.
- Review runtime, test, packaged artifacts, and deployment environment classpaths.
- Use BOMs, lock files, dependency constraints, and optional integrations to keep changes intentional.
- Exclusions only prevent auto-configuration from applying; they do not remove dependencies from the classpath.
- Merge only once you can explain which features changed, why they changed, and have regression tests protecting that behavior.

### Official references

- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration and condition annotations: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Build Systems and dependency management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Spring Boot — Gradle dependency management and BOM: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html
- Apache Maven — Introduction to the Dependency Mechanism, transitive/optional dependencies and exclusions: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
