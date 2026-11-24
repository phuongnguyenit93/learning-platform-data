# Looking Up Javadoc, Versioned Documentation, and API Changes When Upgrading Spring

## Objectives

When working with Spring, an answer that is accurate for the latest version is not necessarily accurate for the running application. A method may appear only from a specific minor release, be marked deprecated in another version, change signatures, or be removed in a major release. Configurations can also keep the same name while changing behavior or default values.

Therefore, looking up APIs and upgrading Spring must start from **the version actually resolved in the project**, then cross-reference Javadoc, Reference Documentation, release notes, and migration notes for that exact version line. This lesson provides a repeatable process to locate a class/method, determine whether an API is still supported, evaluate upgrade impact, and verify changes through builds and tests.

## 1. Distinguishing documentation sources

No single documentation page answers every question. Use the right source for the right purpose:

| Source | Used to answer | What to verify |
| --- | --- | --- |
| Javadoc | Classes, interfaces, constructors, methods, parameters, return types, exceptions, annotations, and inheritance | Exact artifact and exact version |
| Reference Documentation | Usage, configuration, lifecycle, semantics, and Spring-supported patterns | Select the exact version in the docs version switcher |
| Release Notes / What's New | New APIs, behavioral changes, deprecations, removals, baselines, and default changes | Read every release between source version and target version |
| Upgrade / Migration Notes | Actions required when moving from one generation or minor line to another | Follow the project's exact starting point |
| JAR and source JAR | Actual signatures of resolved dependencies and how implementations behave | Use the exact artifact/version file on the classpath |
| Project issues / pull requests | Design rationale or context behind a specific change | Use as supplement, not a replacement for public API docs |

**Javadoc is the Java-level API contract.** Reference Documentation explains how to apply the API in a scenario. Release notes explain what changed between releases. Source code helps clarify implementation when needed, but private details or internal packages are not compatibility guarantees.

## 2. Identifying the Spring version actually running

Do not start by searching the web for a class name and taking the first result. First, determine which dependencies are being built and run.

Spring Framework is split across multiple artifacts, for example:

| Common package | Maven artifact |
| --- | --- |
| `org.springframework.core`, `org.springframework.util` | `spring-core` |
| `org.springframework.context`, `org.springframework.beans` | `spring-context`, `spring-beans` |
| `org.springframework.messaging` | `spring-messaging` |
| `org.springframework.jms` | `spring-jms` |
| `org.springframework.web` | `spring-web` |
| `org.springframework.web.servlet` | `spring-webmvc` |
| `org.springframework.web.reactive` | `spring-webflux` |
| `org.springframework.test` | `spring-test` |

Package names suggest the module, but are not always enough to identify the dependency. Verify which artifact owns a class using Javadoc, package documentation, or the dependency tree.

### Maven

Inspect the resolved Spring modules:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Inspect the POM after applying parent/BOM and profiles:

~~~bash
./mvnw help:effective-pom
~~~

If you need to know why a version was chosen, inspect the full dependency tree and check dependency management, exclusions, profiles, and version overrides. A dependency declared in the POM may not be the final version on the runtime classpath.

### Gradle

List dependencies on the compile classpath:

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

Inspect why Gradle chose a specific module:

~~~bash
./gradlew dependencyInsight --dependency spring-messaging --configuration runtimeClasspath
~~~

Repeat for `spring-core`, `spring-context`, `spring-jms`, or whichever module relates to the API being checked. If compile classpath and runtime classpath differ, check both.

### Checking the version at runtime

You can print the version provided by `spring-core`:

~~~java
import org.springframework.core.SpringVersion;

public class SpringVersionProbe {

    public static void main(String[] args) {
        System.out.println(
                "Spring Framework: " + SpringVersion.getVersion());
    }
}
~~~

The output depends on the loaded JAR. For example, if runtime uses Spring Framework 6.2.19, the output will be:

~~~text
Spring Framework: 6.2.19
~~~

This is a useful signal for diagnosing the classpath, though `SpringVersion` reads the version from Spring Core. It does not prove all Spring modules share the same version. Use the dependency tree to check the entire artifact group.

### If the project uses Spring Boot or Spring Cloud

Spring Boot manages a compatible set of Spring Framework and dependency versions through dependency management. Spring Cloud also has its own release trains and compatibility matrix.

- If using Spring Boot, first determine the Boot version and the Spring versions managed by Boot's BOM.
- If using Spring Cloud, check which release train is compatible with the selected Spring Boot version.
- Avoid upgrading `spring-core`, `spring-messaging`, or `spring-context` individually to a different version from the rest of the Framework without a clear reason and compatibility testing.
- If using standalone Spring Framework, manage all modules at the same version with `spring-framework-bom`.

Example BOM for applications using Spring Framework directly:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

When using the Spring Boot parent/BOM, follow Boot's dependency management rather than adding a standalone Framework BOM that skews the versions Boot tested together.

## 3. Selecting the right versioned Reference Documentation

Current Reference Documentation pages are typically accessed via:

- Current: https://docs.spring.io/spring-framework/reference/
- 6.2 line: https://docs.spring.io/spring-framework/reference/6.2/
- 7.0 line: https://docs.spring.io/spring-framework/reference/7.0/

The homepage has a version selector distinguishing Stable, Preview, and Snapshot. When looking up production applications, choose the exact stable line matching resolved dependencies. Snapshots, milestones, and release candidates are useful for early evaluation, not for representing GA release APIs.

Pages labeled "current" can change over time. If a project uses 6.2.x, a current guide for 7.0.x may describe APIs or baselines the project does not yet have. Compare the same page across both versions when evaluating an upgrade.

Reference Documentation is especially helpful for understanding:

- In which lifecycle an API is used and which component creates it.
- Which Java, XML, or property configurations are supported.
- Default behavior, transaction boundaries, threading, and error handling.
- Conditions when integrating with Servlet containers, brokers, databases, or reactive runtimes.
- Patterns recommended by Spring to replace older APIs.

Do not assume a method exists merely from a snippet in a blog post. Locate the class and signature in the Javadoc for your exact version before applying it.

## 4. Opening Javadoc for the right artifact and version

Spring Framework Javadoc is published by version. Use an explicitly versioned URL:

~~~text
https://docs.spring.io/spring-framework/docs/{version}/javadoc-api/
~~~

Replace `{version}` with the version identified from the dependency tree, such as `6.2.19`. You can look up a specific class by appending the package path and class name:

~~~text
https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/Message.html
~~~

The current Javadoc path has the form:

~~~text
https://docs.spring.io/spring-framework/docs/current/javadoc-api/
~~~

Use `current` to explore the latest API; use the versioned URL to decide whether code compiles against your project's dependencies.

Inside Javadoc, you can navigate by levels:

1. **Overview / All Classes:** find a package or class name when the location is unknown.
2. **Package Summary:** understand API groups, related packages, and classes in the package.
3. **Class / Interface Page:** inspect declarations, superclasses, implemented interfaces, constructors, and methods.
4. **Method Detail:** check exact overloads, parameter types, generics, return types, exceptions, and descriptions.
5. **Deprecated List:** review APIs marked deprecated.
6. **Index / Search:** find method names, constants, annotations, or classes across the entire Javadoc.

For example, with Spring Messaging, look up `org.springframework.messaging.Message` in artifact `spring-messaging`; with JMS listeners, look up `org.springframework.jms.listener.DefaultMessageListenerContainer` in artifact `spring-jms`. Do not search for a class solely by a short name like `Message` because many packages and abstractions share the same name.

## 5. Reading a Javadoc page systematically

When opening a class page, do not read only the top description. Check these sections:

- **Declaration:** class/interface/record/enum, generic parameters, modifiers, and implemented interfaces.
- **Since:** first version where the API appeared. If the project version is lower, that API may not exist yet.
- **Constructor Summary:** how to instantiate the object, which constructors are public, and which are deprecated.
- **Method Summary:** list of methods, return types, names, and parameters.
- **Method Detail:** full signature, preconditions, results, side effects, exceptions, and thread/lifecycle contracts if any.
- **Inherited Methods:** methods may come from a superclass or interface; check the original declaration site.
- **Nullability:** nullness annotations, nullable/non-null types, and Java/Kotlin differences.
- **See Also:** related APIs, replacements, or higher-level abstractions.

For an overloaded method, compare the full signature. Two methods with the same name may differ in parameter types, generics, varargs overloads, return types, or semantics. An online example calling a method does not mean that overload exists in your version.

Meaning of Javadoc tags:

| Tag / annotation | How to read |
| --- | --- |
| `@since` | Version in which the API was introduced |
| `@deprecated` | Reason not to continue using it and replacement if any |
| `@Deprecated(since = "...")` | Java compiler/IDE can warn; `since` records the version marked deprecated |
| `@Deprecated(forRemoval = true)` | API is marked for planned removal; plan a replacement |
| `@throws` | Conditions under which exceptions can be thrown |
| `@Nullable`, `@NonNull`, or JSpecify | Nullness contract, which can affect Java and Kotlin |

Not every deprecated API is removed in the very next release. Conversely, a major release may remove APIs deprecated years earlier. Read release notes to confirm actual status.

## 6. Searching APIs by class, package, and method

Once you have a technical question, turn it into a precise query:

1. Write down the fully qualified name, e.g., `org.springframework.messaging.rsocket.RSocketRequester`.
2. Identify the artifact containing the class, e.g., `spring-messaging`.
3. Note the current version and planned target upgrade version.
4. Open Javadoc for both versions.
5. Locate the exact method and overload, not just the class name.
6. Cross-check against Reference Documentation for the same version line.
7. Search release notes or migration notes mentioning that API, module, or behavior.

When searching the web, use fully qualified names and restrict to the official domain:

~~~text
site:docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/
"org.springframework.messaging.rsocket.RSocketRequester"
~~~

Or search for a specific method:

~~~text
site:docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/
"setValidator" "RSocketMessageHandler"
~~~

Search results only help locate the right page. Afterward, open the Javadoc and read the full signature. Search engine snippets can truncate overloads, versions, or context.

If an API belongs to Spring Integration, Spring AMQP, Spring Kafka, Spring Security, or Spring Cloud, use the documentation and Javadoc of **that specific project**. Spring Framework Javadoc does not document all APIs across ecosystem projects.

## 7. Checking deprecated, replacement, and removed APIs

When encountering a deprecation warning, record four details:

1. Which API is deprecated: class, constructor, method, field, or package.
2. Version where deprecation began and whether `forRemoval` is set.
3. Reason: legacy API, unsuitable semantics, unsupported dependency, or better abstraction.
4. Recommended replacement and differences when migrating.

Do not swap a deprecated method for a similarly named method without reading the replacement's Javadoc. The replacement may change lifecycle, threading, transactions, exceptions, or default behavior.

Signals to audit:

- IDE shows strikethrough or deprecation warnings.
- Compiler reports `[deprecation]`.
- Release notes state "removed", "no longer supported", "replaced by", or "breaking change".
- APIs live in internal packages such as `*.support`, `*.internal`, or implementation classes not documented as extension points.
- Code depends on protected fields/methods of classes that documentation notes have changed or been removed.

Public APIs can still change across major releases. Internal APIs carry higher risk because they have no stability guarantee. Prefer public documented interfaces and extension points.

## 8. Reading Release Notes and Migration Notes along the exact upgrade path

Release notes are not just a list of new features. They are where you find changes that a single method's Javadoc might not highlight, such as:

- JDK, Jakarta EE, Servlet, JPA, Validation, or Kotlin baselines.
- Removed APIs, classes, packages, or integrations.
- Default configuration and behavioral changes.
- Changes in autowiring, generic matching, nullability, or parameter-name discovery.
- Changes in the test framework, transactions, or runtime containers.
- Third-party dependencies upgraded or no longer supported.

Important rule: if upgrading from an older major line, read **every intermediate step**. For example, upgrading from 5.3 to 7.0 requires reviewing changes in 6.0, 6.1, 6.2, and 7.0. Reading only the 7.0 release notes can miss changes that already occurred in 6.0 or 6.1.

Official sources to open:

- Spring Framework Versions: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions
- Upgrading to Spring Framework 6.x: https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x
- Spring Framework 7.0 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes
- Spring Framework What's New: linked from the wiki and Reference Documentation.

The Supported Versions page indicates which branches remain supported and each generation's baseline. Re-check this page at planning time because support schedules can change.

## 9. Example changes from Spring Framework 6.2 to 7.0

A few examples below illustrate why both API references and migration notes must be read. These are representative examples, not an exhaustive list.

### Platform baseline

Spring Framework 7.0 retains the JDK 17 baseline while moving to a Jakarta EE 11 baseline. Platform changes include Servlet 6.1, JPA 3.2, Bean Validation 3.1, Kotlin 2.2, Netty 4.2, and JUnit 6. Before upgrading the Framework, verify whether your Servlet container, JPA/Validation providers, test libraries, and integration libraries are compatible.

### javax and jakarta namespaces

Spring Framework 7 drops support for annotations from `javax.annotation` and `javax.inject`. For example, `@javax.annotation.Resource`, `@javax.annotation.PostConstruct`, and `@javax.inject.Inject` must move to their corresponding Jakarta packages if used by the application.

This is a namespace change in dependencies and source code. It cannot be resolved merely by bumping the Spring version while keeping old Java EE APIs.

### HttpHeaders and MultiValueMap

In Spring Framework 7, `HttpHeaders` no longer implements the `MultiValueMap` contract. Code assigning `HttpHeaders` to a `MultiValueMap` variable, casting it, or calling methods relying on that contract may no longer compile. Migration notes describe deprecated fallback methods; move to `HttpHeaders`-specific APIs per the target version's Javadoc.

### ListenableFuture

Several Spring `ListenableFuture` APIs were removed in Spring Framework 7 in favor of `CompletableFuture`. When upgrading, search for all related imports, return types, callbacks, and adapters. A plain type swap may not suffice if code relies on callback registration or cancellation behavior.

### Behavioral changes without signature changes

Since Spring Framework 7.0.8, SpEL caps the number of operations in a single expression evaluation at a default limit of 10,000. A very complex expression may start throwing exceptions even though the code still compiles. This illustrates why upgrades need behavioral testing with realistic data, not just API signature checks.

## 10. Distinguishing source, binary, and behavioral compatibility

An upgrade can succeed at one layer yet fail at another:

| Compatibility type | Question | Failure example |
| --- | --- | --- |
| Source compatibility | Does source code compile against the new API? | Removed method or changed parameter type |
| Binary compatibility | Does already-compiled bytecode run with the new JARs? | `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError` |
| Behavioral compatibility | Does the API remain, yet results/behavior change? | Changed default timeouts, ordering, transactions, or parser behavior |
| Configuration compatibility | Are old properties/XML/Java configs still supported? | Removed property or changed default |
| Ecosystem compatibility | Are related modules and libraries compatible? | Incompatible Spring Boot/Cloud, broker client, or Servlet container |

A project can compile yet fail at runtime because two different Spring versions sit on the classpath. A project can run yet change behavior because of a new default or limit. Therefore, dependency convergence, compilation, unit/integration tests, and smoke tests are all required.

## 11. Comparing APIs between two versions

When determining how an API changed, build an explicit comparison table:

| Item | Current version | Target version |
| --- | --- | --- |
| Artifact/version | e.g., `spring-messaging:6.2.x` | e.g., `spring-messaging:7.0.x` |
| FQCN | Full class/interface name | Full class/interface name |
| Method signature | Return type, name, parameters, generics | New signature |
| Status | Public / deprecated / internal | Public / deprecated / removed |
| Since / Deprecated | Tag and version | Tag and version |
| Replacement | Recommended API | Replacement API |
| Behavior | Nullability, threading, transactions, defaults | Differences to address |
| Validation | Existing build/tests | Tests proving compatibility |

Do not compare only method names. Check:

- Parameter types and return types.
- Generic bounds, wildcards, varargs, and overload resolution.
- Checked/unchecked exceptions and exception contracts.
- Nullability and Kotlin null-safety.
- Interfaces/superclasses, default methods, and visibility.
- Packages, modules, and artifacts containing the class.
- Side effects, lifecycles, threading, transactions, and default values.

For large changes or multi-module projects, API/binary compatibility tools such as japicmp or Revapi can detect differences between two JARs. Tool output is an input to review; you still must read release notes and test runtime behavior.

## 12. Using source JARs and javap when Javadoc is not enough

If Javadoc does not explain enough detail, download the exact version's source JAR via Maven/Gradle or the IDE's Download Sources action. Source helps clarify implementations, though you should not depend on private fields or internal logic when an equivalent public API exists.

You can inspect class bytecode signatures from an actual JAR using `javap`:

~~~bash
javap -classpath path/to/spring-messaging-6.2.x.jar org.springframework.messaging.Message
~~~

`javap` is useful when:

- The IDE cannot find sources.
- You need to confirm a method actually exists in the runtime JAR.
- There is a discrepancy between displayed Javadoc and resolved dependencies.
- Investigating linkage errors such as `NoSuchMethodError`.

`javap` does not replace Javadoc: it does not provide full semantics, migration notes, nullness contracts, or design rationale. Do not use source from the `main` branch to conclude an API exists in an already released version.

## 13. Controlled upgrade workflow

### Step 1 — Capture a baseline

Record:

- Spring Boot, Spring Framework, and Spring Cloud versions.
- Java toolchain/JDK used to compile and run.
- Resolved Spring modules.
- Jakarta EE/Servlet/JPA/Validation providers.
- Brokers, database drivers, HTTP clients, and integration libraries.
- Current test suite and pre-existing warnings.

Save the dependency tree or lockfile as pre-upgrade evidence.

### Step 2 — Choose the target version

Choose the version based on supported-version policies, security requirements, JDK, and ecosystem compatibility. If using Boot/Cloud, pick a compatible release train first and let the BOM manage related dependencies. Do not upgrade a single Spring module arbitrarily.

### Step 3 — Read migration notes

Read from the source version to the target version, including every major/minor release in between. Search for keywords `removed`, `deprecated`, `breaking`, `baseline`, `behavior`, `default`, `no longer supported`.

Create a list of APIs and configurations requiring changes before swapping dependencies. Flag whether each change is compile-time, runtime, configuration, or behavioral.

### Step 4 — Find and replace deprecated APIs

Enable compiler warnings and address deprecations within upgrade scope:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:deprecation</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

With Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-Xlint:deprecation")
}
~~~

Do not silence warnings via wholesale suppression. For each deprecated API, document the replacement and the reason if deferral is necessary.

### Step 5 — Upgrade dependencies via BOM

Update the selected parent/BOM or release train. Then inspect the dependency tree to catch mismatched Spring module versions, older transitive dependencies, or exclusions dropping required modules.

### Step 6 — Compile and test

Run a clean build with the target JDK:

~~~bash
./mvnw clean verify
~~~

Or:

~~~bash
./gradlew clean test
~~~

Add tests based on application risks: application context startup, messaging brokers, listener concurrency, transactions, serialization, WebSocket/RSocket, security, database migrations, and external clients. If behavior changed, write tests describing the expected behavior rather than merely patching code to compile.

### Step 7 — Verify runtime

After a successful build:

- Check the runtime dependency tree and actual classpath.
- Run smoke tests in a production-like environment.
- Read deprecation/removal logs and startup warnings.
- Verify actuator/health, broker connections, listener containers, and transactions.
- Monitor error rates, latency, queue backlogs, and resource usage after rollout.

Do not treat successful compilation as proof an upgrade is complete.

## 14. Troubleshooting common lookup or upgrade errors

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| IDE cannot find method | Method does not exist in active version or wrong class imported | Open exact-version Javadoc and dependency tree |
| `cannot find symbol` | API/package removed, renamed, or missing dependency | Check release notes, FQCN, and artifacts |
| `NoSuchMethodError` | Runtime loads a different version than compile time | Inspect runtime dependency tree and duplicate JARs |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing artifact or moved package | Check dependencies, namespaces, and new modules |
| `AbstractMethodError` | Mismatched interface/class versions or incompatible implementation | Check all related modules and dependency convergence |
| Compiles but behavioral tests fail | Changed semantics/defaults/configuration | Read migration notes and write regression tests |
| Javadoc lacks the used class | Wrong artifact, wrong version, or internal class | Check package summary and source JAR of exact artifact |
| Conflicting search results | Current docs, snapshots, old blogs, or other versions | Restrict domain and version, prefer official docs |

## 15. Recording lookup findings for team reuse

For important APIs or major upgrades, record a brief note in the PR or migration document:

| Field | What to record |
| --- | --- |
| Question | Which API/behavior needed verification |
| Source/target version | Resolved version and target version |
| Artifact and FQCN | Maven module and fully qualified class name |
| Javadoc | Versioned link to the class/method |
| Reference / Release note | Link to guide page and change entry |
| Conclusion | Supported, deprecated, removed, or behavior changed |
| Action | Replacement, config change, or keep as-is |
| Evidence | Build, tests, runtime checks, and results |

Record exact versions rather than just writing "per Spring docs." Later when dependencies upgrade again, readers can see which version the conclusion applied to.

## 16. Common lookup mistakes

- **Using current Javadoc for older projects:** leads to calling non-existent methods or applying new APIs.
- **Reading only a single class page:** misses package-level contracts, superclasses, overloads, or Reference Documentation behaviors.
- **Reading only the target version's release notes:** misses removals from intermediate releases.
- **Confusing Spring Boot version with Spring Framework version:** Boot and Framework have distinct version numbers; check the resolved BOM.
- **Upgrading a single Spring module:** creates inconsistent classpaths across `spring-core`, `spring-context`, `spring-messaging`, `spring-jms`, and other modules.
- **Trusting old blogs or snippets:** examples may apply to an older version or a specific provider.
- **Relying on internal implementations:** code may run today without stability guarantees.
- **Fixing only compile errors:** ignores changes in transactions, threading, ordering, nullability, or configuration.
- **Not saving evidence:** future teammates must repeat the lookup process and may reach conflicting conclusions.

## 17. Lookup and upgrade checklist

- [ ] Identified the actual Spring Framework version from dependency resolution.
- [ ] Identified the artifact containing the required class/API.
- [ ] Opened exact-version Javadoc, not just current or snapshot pages.
- [ ] Read class declaration, method overloads, generics, nullability, and exception contracts.
- [ ] Checked `@since`, `@Deprecated`, `forRemoval`, and Deprecated List.
- [ ] Read Reference Documentation for the matching version line.
- [ ] Read release notes and migration notes for all intermediate versions.
- [ ] Verified Spring Boot/Cloud compatibility and BOM management if used by the project.
- [ ] Audited JDK, Jakarta EE, container, and third-party provider baselines.
- [ ] Checked source/API diffs for high-risk changes.
- [ ] Compiled with the target JDK and addressed deprecation warnings.
- [ ] Ran unit, integration, and smoke tests covering affected behaviors.
- [ ] Verified the runtime classpath has no mismatched Spring module versions.
- [ ] Saved documentation links and test evidence in the PR/migration record.

## Official references

- [Spring Framework Reference Documentation](https://docs.spring.io/spring-framework/reference/): current documentation and version selector.
- [Spring Framework Reference 6.2](https://docs.spring.io/spring-framework/reference/6.2/): example documentation for a specific version line.
- [Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/): current API reference; replace `current` with a specific version when checking older projects.
- [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions): supported versions, JDK ranges, and Jakarta EE baselines.
- [Upgrading to Spring Framework 6.x](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x): changes when upgrading from the 5.x generation.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): upgrading from 6.2, baselines, removed APIs, and breaking changes.
- [Spring Framework Documentation Update](https://spring.io/blog/2023/05/11/spring-framework-reference-documentation-update/): how to choose Reference Documentation versions and documentation structure.
- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/): dependency management and configuration by Boot version.
- [Spring Cloud Documentation](https://docs.spring.io/spring-cloud/reference/): documentation and compatibility guidance for Spring Cloud release trains.

