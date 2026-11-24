# Mockito Agent, Mock Maker, and JDK Compatibility

> **Module:** Spring Boot – testing  
> **Group:** Test Troubleshooting  
> **Topic:** Mockito agent, mock maker, and JDK compatibility  
> **Goal:** Distinguish Mockito's mock maker from a Java instrumentation agent, interpret JDK 21+ JEP 451 warnings accurately, configure Mockito's `-javaagent` on the test JVM in Maven/Gradle, understand `INLINE`/`SUBCLASS`/`PROXY` trade-offs, detect Mockito/Byte Buddy/JDK mismatches, and verify Spring `@MockitoBean`. Includes a Java 17 + Spring Boot 3.5.0 + Mockito 5/JUnit 5 project with **11 `@Test` methods**.

## 1. Symptom: Agent Warning Appears After Upgrading the JDK

A Mockito 5 project whose tests pass on JDK 17 may print warnings when switched to JDK 21 or newer:

```text
Mockito is currently self-attaching to enable the inline-mock-maker.
This will no longer work in future releases of the JDK.
Please add Mockito as an agent to your build.

WARNING: A Java agent has been loaded dynamically
WARNING: Dynamic loading of agents will be disallowed by default
         in a future release
```

This is a **condensed representative notice**, not captured stdout from running the project here. JDK 21 emits the warning per **JEP 451** whenever a Java agent loads dynamically **after the JVM has started**. In some environments the warning appears while tests still PASS; in environments prohibiting attachment, Mockito can outright FAIL:

```text
org.mockito.exceptions.base.MockitoInitializationException:
Could not initialize inline Byte Buddy mock maker.

It appears as if your JDK does not supply a working
agent attachment mechanism.
```

Exact messages depend on Mockito, Byte Buddy, JDK, and vendor. Do not lump both outcomes into "Mockito is incompatible with Java 21":

- **Warning yet tests PASS:** Inline instrumentation succeeded via dynamic self-attach; migrate to a startup agent for future compatibility.
- **Error initializing inline mock maker:** Investigate Java agent setup, VM capabilities, classpath, and Byte Buddy versions.
- **Final classes fail to mock while interfaces succeed:** You may be running `SUBCLASS`/`PROXY`, or inline instrumentation failed.
- **Maven green, IDE red:** The two runners likely launch the test JVM with different arguments or JDKs.
- **Surefire fork crashes:** `argLine` may not have interpolated, the agent jar is missing, or the JVM crashed—do not assume a Mockito bug immediately.

**Right diagnostic questions:** Which mock maker is Mockito using? Is the Java agent loaded **at JVM startup** or attached dynamically? Is instrumentation compatible with that JDK? Is the test mocking an interface, open class, `final` class, `static` method, or constructor?

## 2. Diagram: A MockMaker Is Not a Java Agent

```text
JUnit Jupiter test
      |
      +-- Mockito.mock(...)
      +-- @Mock / @InjectMocks
      +-- Spring @MockitoBean (bean override)
      |
      v
Mockito plugin: org.mockito.plugins.MockMaker
      |
      +-- INLINE (default Mockito 5)
      |     |
      |     +-- Byte Buddy class instrumentation
      |     +-- java.lang.instrument.Instrumentation
      |           |
      |           +-- JVM startup -javaagent [recommended]
      |           +-- JVM dynamic self-attach [warning/restricted]
      |
      +-- SUBCLASS
      |     +-- generates mock subclass; overridable methods/types only
      |
      +-- PROXY
            +-- Java dynamic proxy; interfaces only
```

**Mockito** handles stubbing and verification; **`MockMaker`** creates mock instances; **Byte Buddy** performs bytecode instrumentation and generation; a **Java agent** grants access to JVM `Instrumentation`. They are related layers, **not identical concepts**.

JUnit 5's `MockitoExtension` manages `@Mock`/`@InjectMocks` lifecycle and validation, not JVM instrumentation. Spring Framework 6.2's `@MockitoBean` swaps a bean in the `ApplicationContext` with a Mockito mock; it also does not configure `-javaagent` itself.

### 2.1. Default Change in Mockito 5

Starting with **Mockito 5.0**, the **inline mock maker** became the default inside `mockito-core`. Consequently, older Mockito 2–4 tutorials claiming "you must add `mockito-inline` to mock final classes" are outdated for Mockito 5.

In Spring Boot 3.5:

- `spring-boot-starter-test` pulls in Mockito and JUnit Jupiter via managed dependencies.
- Do not add `mockito-inline` blindly from outdated blog posts.
- Do not pin a `mockito-core` version out of sync with `mockito-junit-jupiter`, `byte-buddy`, and `byte-buddy-agent`.
- Declaring `mockito-core` explicitly in test scope is fine so Maven plugins resolve its jar path cleanly, while letting the BOM manage the version.
- Do not drop in `mockito-subclass` with conflicting plugin resource extensions without auditing mock-maker usage across the module.

### 2.2. Comparing the Three Mock Makers

| Capability | `INLINE` | `SUBCLASS` | `PROXY` |
| --- | --- | --- | --- |
| Mock interfaces | Yes | Yes | Yes |
| Mock concrete non-final classes | Yes | Yes | No |
| Mock `final` classes/`final` methods | Yes if VM supports | No | No |
| `Mockito.mockStatic` | Yes, within JVM/type limits | No | No |
| `Mockito.mockConstruction` | Yes, within JVM/type limits | No | No |
| Needs inline `Instrumentation` | Yes | Not for subclass mocks | Not for interface proxies |
| Mock native methods | Limited under inline | Not a workaround | Not applicable |
| Best suited for | Final/static/constructor tests | Open non-final collaborators | Ports/interfaces |

In Mockito 5.17, use constants:

```java
MockMakers.INLINE
MockMakers.SUBCLASS
MockMakers.PROXY
```

Corresponding to extension names `mock-maker-inline`, `mock-maker-subclass`, and `mock-maker-proxy`. `SUBCLASS` has a fundamental JVM limitation: it cannot subclass a `final` class. `PROXY` handles interfaces only.

**Nuance:** Passing `withSettings().mockMaker(MockMakers.PROXY)` for one interface mock does not stop the **rest of the JVM** from initializing the default inline maker; other tests and plugins can still trigger inline. Never infer global agent status from a single per-mock setting.

## 3. JDK Compatibility: Do Not Look Only at `java.version` in `pom.xml`

Three distinct version axes exist:

1. **Source/bytecode target:** Java 17, e.g., `<java.version>17</java.version>`.
2. **Runtime executing Maven, Surefire test forks, or the IDE runner:** could be JDK 17, 21, or newer.
3. **Mockito + Byte Buddy/JUnit/Spring versions:** must align with both compiled bytecode and runtime JDK.

A POM targeting Java 17 **can still run tests on JDK 21** when CI updates `JAVA_HOME`. JDK 21 prints dynamic agent loading warnings, and newer JDKs may require a Byte Buddy release supporting newer class file versions.

### 3.1. Java 17 Baseline

- Does not print Java 21's default JEP 451 warning.
- Mockito inline still uses instrumentation and needs attach/agent support.
- Restricted JREs or hardened container images can block self-attach even on JDK 17.
- Configuring an explicit Mockito startup `-javaagent` remains valid here too.
- Maven Surefire, Byte Buddy, and Mockito versions still must align.

### 3.2. JDK 21, JEP 451, and Startup Agents

JEP 451 emits warnings when **loading a Java agent dynamically** into an already-running JVM, preparing the ecosystem for integrity-by-default. It does not mean every Mockito test on Java 21 breaks.

Two paths:

```text
With startup agent:
Surefire forks JVM -javaagent:/path/mockito-core.jar
     |
     +-- Mockito receives Instrumentation at startup
     +-- No dynamic self-attach needed to enable inline
```

```text
Without startup agent:
Surefire forks JVM
     |
     +-- Mockito inline needs Instrumentation
           |
           +-- dynamic self-attach
                 |
                 +-- JDK 21 warning or attach rejected
```

That is why **Mockito 5 Javadoc section 0.3** recommends passing the `mockito-core` jar via `-javaagent` to the **test-executing JVM**.

### 3.3. Why Not Just Pass `-XX:+EnableDynamicAgentLoading`?

HotSpot JDK 21 supports `-XX:+EnableDynamicAgentLoading` to allow dynamic loading and silence the warning. However:

- It still relies on dynamic self-attach instead of loading the agent explicitly upfront.
- It does not fix missing or mismatched agent jars/versions.
- It does not solve JDKs without attach mechanisms or class file versions unsupported by Byte Buddy.
- It is not guaranteed as a standard flag across every vendor and future JDK.
- Never deploy it across production fleets merely to silence a test warning.

It may help during targeted diagnosis, yet **startup `-javaagent` per Mockito docs is the durable fix**. `-Djdk.instrument.traceUsage` helps trace instrumentation calls without replacing agent configuration.

### 3.4. Mocking on Specialized JVMs

Android, GraalVM native-image, stripped/custom runtimes, strict container security policies, or alternative JDK vendors may restrict bytecode instrumentation. Even when version numbers look fine, agent attach can be blocked; check root causes and VM capabilities. `SUBCLASS` or `PROXY` can serve well-designed test seams, though neither can emulate final/static/constructor mocking.

### 3.5. Distinguishing Common Errors and Warnings

| Error / Warning | Likely Meaning | Where to Check |
| --- | --- | --- |
| `Mockito is currently self-attaching` | Dynamic attach used for inline | Configure startup Mockito agent |
| `WARNING: A Java agent has been loaded dynamically` | JEP 451 warning | Check test outcome and attaching agent |
| `Could not initialize inline Byte Buddy mock maker` | Instrumentation init failed | Agent, VM, Byte Buddy, attach support |
| `No compatible attachment provider` | VM attach mechanism unavailable | Startup agent / supported JDK |
| `Unsupported class file major version` | Byte Buddy/ASM lacks support for JDK bytecode | Upgrade BOM-managed dependencies |
| `Could not modify all classes` | Type/redefinition restriction | Inspect class hierarchy and VM |
| `Cannot mock/spy ... final class` | Subclass maker active or inline unavailable | Mock maker selection, `final` modifier |
| `ClassNotFoundException org.mockito...` | Broken test classpath | Test dependencies |
| `NoClassDefFoundError net.bytebuddy...` | Missing/mismatched Byte Buddy | Dependency tree / exclusions |
| `InaccessibleObjectException` | JPMS reflective access blocked | Inspect specific module/package |
| `Forked VM terminated ... goodbye` | Bad JVM args, crash, or exit | Effective Surefire launch, dumps |
| IDE red, Maven green | Runner JVM args or dependencies differ | IDE runner/toolchain vs Maven |

**Do not** blindly add `--add-opens java.base/java.lang=ALL-UNNAMED`, `-Djdk.attach.allowAttachSelf`, or disable tests before finding the root cause. A warning is not the same as a failure exception.

## 4. Maven Surefire `-javaagent` per Mockito Javadoc

### 4.1. Principles

- Load the Mockito jar at **test JVM startup**.
- Do not attach the agent only to Maven's parent JVM.
- Do not hardcode `~/.m2/repository` or one developer's absolute path.
- Preserve other Java agents such as JaCoCo using `@{argLine}` late replacement.
- Avoid an unresolved literal `@{argLine}` if no plugin sets it by declaring `<argLine></argLine>` by default.
- Surefire must spawn a **forked test JVM** to apply configured agent flags.

### 4.2. Maven POM Pattern

```xml
<properties>
    <java.version>17</java.version>
    <argLine></argLine>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>properties</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <forkCount>1</forkCount>
                <reuseForks>true</reuseForks>
                <argLine>@{argLine} -javaagent:${org.mockito:mockito-core:jar}</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

`maven-dependency-plugin:properties` populates the Maven property `${org.mockito:mockito-core:jar}` with the **resolved jar path**. Surefire passes that path to `-javaagent`. `@{argLine}` performs **late property expansion**, preserving agent flags injected by JaCoCo's `prepare-agent`. Mockito documents this exact pattern in its Javadoc.

**Do not confuse three distinct syntaxes:**

- `${org.mockito:mockito-core:jar}`: Maven property resolved by the dependency plugin.
- `@{argLine}`: Surefire late property replacement.
- `-javaagent:<path>`: JVM startup flag, not a `-D...` system property.

If Maven fails to resolve the property, the JVM attempts to open a literal string as an agent path and the Surefire fork crashes. Debug property/plugin execution instead of hardcoding an absolute path.

### 4.3. What If JaCoCo Is Active?

`jacoco-maven-plugin:prepare-agent` writes its JVM flags into `argLine`. Overwriting Surefire with `<argLine>-javaagent:mockito...</argLine>` drops the **JaCoCo agent from the test JVM**, yielding empty coverage reports.

Safe pattern:

```xml
<argLine>@{argLine} -javaagent:${org.mockito:mockito-core:jar}</argLine>
```

paired with default `<argLine></argLine>` in case no other plugin sets it. If a project overrides `jacoco.propertyName`, match that exact property name in late replacement. Do not pass `mvn -DargLine=...` casually without checking its impact on Surefire and coverage.

### 4.4. Why Is `MAVEN_OPTS` Not Enough?

`MAVEN_OPTS` configures the Maven build JVM. Surefire typically launches a **separate forked JVM** to execute JUnit, and Maven does not forward all parent JVM flags into that fork. If `forkCount=0`, `argLine` behaves differently because no fork spawns.

```text
Maven JVM (build)
   |
   +-- Surefire test JVM [-javaagent:mockito-core.jar]
         |
         +-- JUnit Jupiter + Mockito tests
         +-- Spring Boot test contexts
```

Configure the agent on the plugin launching the **test process**.

### 4.5. Maven Diagnostic Commands

```bash
java -version
mvn -version

# Inspect Mockito version managed by Boot parent:
mvn -B -ntp help:evaluate -Dexpression=mockito.version -q -DforceStdout

# Inspect resolved dependencies:
mvn -B -ntp dependency:tree -Dincludes=org.mockito:mockito-core,net.bytebuddy:byte-buddy,net.bytebuddy:byte-buddy-agent

# Run inline canary:
mvn -B -ntp -Dtest=InlineMockMakerTest test

# Run full suite:
mvn -B -ntp test
```

If path interpolation looks broken, run Maven debug mode in a test-only CI run (redacting any secrets) and inspect the Surefire fork command line. Never mask JVM agent crashes with `mvn test || true`.

## 5. Gradle and IDEs: Targeting the Right Test JVM

Mockito Javadoc provides a Gradle Kotlin DSL example creating a dedicated configuration holding only the `mockito-core` jar (no transitive dependencies) for `-javaagent`.

### 5.1. Gradle Kotlin DSL — Separate Snippet, Outside the Maven Sample

The snippet assumes a version catalog declaring `libs.mockito` pointing to `org.mockito:mockito-core` aligned with the BOM:

```kotlin
val mockitoAgent = configurations.create("mockitoAgent")

dependencies {
    testImplementation(libs.mockito)
    mockitoAgent(libs.mockito) {
        isTransitive = false
    }
}

tasks.withType<Test>().configureEach {
    jvmArgs("-javaagent:${mockitoAgent.asPath}")
}
```

Gradle/Mockito docs recommend using `CommandLineArgumentProvider` when build-cache relocatability matters. Without a version catalog, use coordinates/versions managed by Gradle platform/dependency management rather than arbitrary versions copied from blogs.

### 5.2. IDE Run Configurations

- IntelliJ/Eclipse/VS Code may launch JUnit in their own JVM without reading Surefire `argLine`.
- Either delegate test execution to Maven/Gradle so the build configuration applies,
- Or add the startup agent to the **test runner VM arguments**—never the production app run config.
- Check the JDK used by the IDE test runner, not just the project language level.
- When IDE and CI disagree, compare JDK vendor/version, classpath, mock-maker extension resources, and startup JVM flags.
- Never commit an absolute local Maven repository path tied to one developer's machine.

### 5.3. CI Compatibility Matrix

A practical strategy runs 2 matrix jobs on Java **17 and 21** while keeping the Mockito/Boot BOM consistent. Before adopting a newer JDK, verify the Byte Buddy/Mockito/Boot compatibility matrix. Never mark a build compatible solely because source target=17; tests must execute on the target runtime.

Simple illustrative GitHub Actions workflow:

```yaml
name: Mockito Compatibility
on:
  push:
  pull_request:
permissions:
  contents: read
jobs:
  jdk17:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - run: mvn -B -ntp test
  jdk21:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - run: mvn -B -ntp test
```

This is an **illustrative workflow**, not evidence of an executed CI run. Both jobs inherit the agent JVM config from Maven POM.

## 6. Choosing a Mock Maker Per Mock vs Module-Wide

### 6.1. `INLINE`

Mockito 5's default inline maker supports final classes/methods, static methods, and constructor interception when the JVM permits instrumentation.

```java
PriceMath math = mock(PriceMath.class);
when(math.addFee(100, 5)).thenReturn(77);
assertThat(math.addFee(100, 5)).isEqualTo(77);
```

`PriceMath` is a `final` class in the sample project; imports are omitted in this snippet. To keep final/`mockStatic`/`mockConstruction` tests reliable, the project configures an explicit Mockito startup agent.

### 6.2. `SUBCLASS`

`SUBCLASS` generates a subclass overriding methods, valid only for overridable types and methods:

```java
OpenPricePolicy policy = mock(
        OpenPricePolicy.class,
        withSettings().mockMaker(MockMakers.SUBCLASS));

when(policy.adjust(100)).thenReturn(91);
assertThat(policy.adjust(100)).isEqualTo(91);
```

You cannot use the subclass maker to mock `final` `PriceMath`. Any `@Service` marked `final` in Java or Kotlin (classes are `final` by default in Kotlin) likewise fails under `SUBCLASS`.

### 6.3. `PROXY`

`PROXY` mocks interfaces only and cannot mock concrete classes:

```java
DiscountGateway gateway = mock(
        DiscountGateway.class,
        withSettings().mockMaker(MockMakers.PROXY));

when(gateway.discountPercent("u-1")).thenReturn(15);
assertThat(gateway.discountPercent("u-1")).isEqualTo(15);
```

Designing clean business port interfaces lets tests use proxy mocks or simple fakes without instrumenting concrete class bytecode. Note that proxy mocks do not support `mockStatic` or constructor interception.

### 6.4. Mock-Maker Extension File — Reference Only

To switch the mock maker **module-wide**, create:

```text
src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker
```

containing:

```text
mock-maker-subclass
```

**Do not create this file in the sample project below.** Doing so would break the inline tests mocking final/static/constructor targets. Watch out for multiple conflicting extension resources/artifacts on the classpath: Mockito resolves plugins from the classpath and behavior can shift unexpectedly. If a restricted runtime forces `SUBCLASS`, refactor production seams to interfaces and audit tests before altering the global maker.

### 6.5. Avoid Mocking What Does Not Need Mocking

- For pure arithmetic, call the real method and assert the output rather than mocking `PriceMath` in business tests.
- For time/clocks, inject `Clock` instead of static-mocking `LocalDateTime.now`.
- For IDs/randomness, inject a generator interface rather than mocking `UUID.randomUUID`.
- For network/DB, mock adapter boundaries in unit tests and test real protocols in integration tests.
- For Spring AOP/transactions, mocking a service never proves `@Transactional` advice runs.
- Avoid mocking `System`, `Thread`, `ClassLoader`, or sensitive core JVM classes.
- Static and constructor mocks couple tests tightly and leak state if scopes are left unclosed.

## 7. Spring Boot: `@Mock`, `@InjectMocks`, and `@MockitoBean` Differ

### 7.1. Pure Unit Test

```java
@ExtendWith(MockitoExtension.class)
class ServiceTest {
    @Mock DiscountGateway gateway;
    @InjectMocks BillingService service;
}
```

`MockitoExtension` instantiates mock fields, injects them, and validates interactions. It **does not** start a Spring `ApplicationContext`.

### 7.2. Spring Context Bean Override

With Spring Framework 6.2 / Boot 3.5:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

`@MockitoBean` replaces or registers a Mockito mock bean inside the **Spring test context** per matching rules. It is not just another name for `@Mock`; it swaps the collaborator injected by Spring into controllers and services.

Example:

```java
@WebMvcTest(BillingController.class)
class BillingControllerSliceTest {
    @MockitoBean BillingService service;
    @Autowired MockMvc mvc;
}
```

This test mocks a **`final` `BillingService`**: default Mockito 5 inline/agent support must work. `@WebMvcTest` omits the full service layer; the bean override supplies the controller's collaborator. No real HTTP server socket opens.

### 7.3. `@SpringBootTest` with Mock Collaborator and Real Service

```java
@SpringBootTest
class BillingSpringIntegrationTest {
    @MockitoBean DiscountGateway gateway;
    @Autowired BillingService service;
}
```

Here `BillingService` is the real Spring bean while `DiscountGateway` is overridden by Mockito. The test verifies Spring wiring and service logic, without proving live remote discount API connectivity.

### 7.4. Legacy `@MockBean`

Spring Boot 3.4+ deprecated Boot's legacy `@MockBean`/`@SpyBean` in favor of Spring Framework's `@MockitoBean`/`@MockitoSpyBean`. Because this project pins Boot 3.5, use `org.springframework.test.context.bean.override.mockito.MockitoBean` instead of mixing Boot 2.7 or Boot 4 imports.

### 7.5. Diagnosing Spring Bean Overrides

- Using plain `@Mock` leaves Spring injecting the real production bean.
- When multiple beans share an interface, specify `@Qualifier` or `@MockitoBean(name=...)`.
- `@MockitoBean(enforceOverride=true)` requires an existing target bean, catching misspelled or missing beans instead of silently applying `REPLACE_OR_CREATE`.
- Default `@MockitoBean` creates a new bean if none matches.
- `@MockitoSpyBean` wraps the real bean and can trigger real side effects; prefer `doReturn` over `when(realMethod())`.
- With cached contexts running in parallel, concurrent tests sharing a mock can race on resets and stubbing.
- Mocking a bean never verifies Spring AOP `@Transactional`, `@Async`, or security advice on that replaced bean.

## 8. Java 17, Boot 3.5.0 Project with 11 JUnit Tests

The project uses the Mockito 5 version managed by the Boot BOM. Maven Surefire passes `-javaagent` to the test JVM even on JDK 17, ensuring seamless inline instrumentation without dynamic self-attach when upgraded to JDK 21+.

### 8.1. File Tree

```text
mockito-agent-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/mockitoagent/
    │   ├── MockitoAgentApplication.java
    │   ├── DiscountGateway.java
    │   ├── DefaultDiscountGateway.java
    │   ├── BillingService.java
    │   ├── BillingController.java
    │   ├── PriceMath.java
    │   └── OpenPricePolicy.java
    └── test/java/com/example/mockitoagent/
        ├── InlineMockMakerTest.java
        ├── AlternativeMockMakerTest.java
        ├── BillingServiceTest.java
        ├── BillingControllerSliceTest.java
        └── BillingSpringIntegrationTest.java
```

No `mockito-extensions` file or `mockito-inline` dependency is present. Every public Java class matches its filename under package `com.example.mockitoagent`.

### 8.2. `pom.xml` — Complete Agent Configuration

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mockito-agent-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
        <argLine></argLine>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <executions>
                    <execution>
                        <goals>
                            <goal>properties</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <argLine>@{argLine} -javaagent:${org.mockito:mockito-core:jar}</argLine>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Why declare `mockito-core` directly?** So `maven-dependency-plugin` exposes its exact artifact path property for `-javaagent`; the Spring Boot BOM still manages its version even though `starter-test` brings it in transitively.

**Why `@{argLine}` and `<argLine></argLine>`?** Mockito Javadoc highlights Surefire late replacement and warns that an unexpanded literal `@{argLine}` crashes the fork if the property is undefined.

### 8.3. `MockitoAgentApplication.java`

```java
// src/main/java/com/example/mockitoagent/MockitoAgentApplication.java
package com.example.mockitoagent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockitoAgentApplication {
    public static void main(String[] args) {
        SpringApplication.run(MockitoAgentApplication.class, args);
    }
}
```

### 8.4. `DiscountGateway.java`

```java
// src/main/java/com/example/mockitoagent/DiscountGateway.java
package com.example.mockitoagent;

public interface DiscountGateway {
    int discountPercent(String customer);
}
```

### 8.5. `DefaultDiscountGateway.java`

```java
// src/main/java/com/example/mockitoagent/DefaultDiscountGateway.java
package com.example.mockitoagent;

import org.springframework.stereotype.Component;

@Component
public class DefaultDiscountGateway
        implements DiscountGateway {

    @Override
    public int discountPercent(String customer) {
        return 0;
    }
}
```

Demo adapter making no network calls. In the full-context test, `@MockitoBean DiscountGateway` replaces this bean.

### 8.6. `BillingService.java`

```java
// src/main/java/com/example/mockitoagent/BillingService.java
package com.example.mockitoagent;

import org.springframework.stereotype.Service;

@Service
public final class BillingService {

    private final DiscountGateway gateway;

    public BillingService(DiscountGateway gateway) {
        this.gateway = gateway;
    }

    public int totalFor(String customer, int subtotal) {
        if (customer == null || customer.isBlank()
                || subtotal < 0) {
            throw new IllegalArgumentException(
                    "invalid billing request");
        }

        int discount = gateway.discountPercent(customer);
        if (discount < 0 || discount > 100) {
            throw new IllegalStateException(
                    "invalid discount");
        }

        return Math.toIntExact(
                (long) subtotal * (100 - discount) / 100);
    }
}
```

Making the service `final` demonstrates that `@MockitoBean` in the MVC slice relies on the inline mock maker/agent. Because it uses no Spring AOP/`@Transactional`, the Java `final` modifier does not block Spring from instantiating the bean directly. Integer arithmetic here is strictly for the mocking lesson, not a production monetary rounding standard.

### 8.7. `BillingController.java`

```java
// src/main/java/com/example/mockitoagent/BillingController.java
package com.example.mockitoagent;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/billing")
public class BillingController {

    private final BillingService service;

    public BillingController(BillingService service) {
        this.service = service;
    }

    @GetMapping("/{customer}")
    public int total(
            @PathVariable String customer,
            @RequestParam int subtotal) {
        return service.totalFor(customer, subtotal);
    }
}
```

`@RestController` serializes `int` as a JSON number string; MockMvc asserts the string representation such as `"85"`.

### 8.8. `PriceMath.java`

```java
// src/main/java/com/example/mockitoagent/PriceMath.java
package com.example.mockitoagent;

public final class PriceMath {

    public int addFee(int base, int fee) {
        return Math.addExact(base, fee);
    }

    public static String currencyCode() {
        return "VND";
    }
}
```

Final/static/constructor tests target this class. It is an **instrumentation canary**, not advice to mock arithmetic in normal tests.

### 8.9. `OpenPricePolicy.java`

```java
// src/main/java/com/example/mockitoagent/OpenPricePolicy.java
package com.example.mockitoagent;

public class OpenPricePolicy {

    public int adjust(int amount) {
        return amount + 10;
    }
}
```

Non-final class with a non-final method, compatible with the `SUBCLASS` mock maker.

## 9. Eleven JUnit Methods

### 9.1. `InlineMockMakerTest.java` — 4 tests

```java
// src/test/java/com/example/mockitoagent/InlineMockMakerTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.mockito.MockMakers;
import org.mockito.MockedConstruction;
import org.mockito.MockedStatic;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockConstruction;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.withSettings;

class InlineMockMakerTest {

    @Test
    void canMockFinalClass() {
        PriceMath math = mock(PriceMath.class);
        when(math.addFee(100, 5)).thenReturn(77);

        assertThat(math.addFee(100, 5)).isEqualTo(77);
        verify(math).addFee(100, 5);
    }

    @Test
    void staticMockIsScopedAndRestored() {
        assertThat(PriceMath.currencyCode())
                .isEqualTo("VND");

        try (MockedStatic<PriceMath> scoped =
                     mockStatic(PriceMath.class)) {
            scoped.when(PriceMath::currencyCode)
                    .thenReturn("TEST");

            assertThat(PriceMath.currencyCode())
                    .isEqualTo("TEST");
            scoped.verify(PriceMath::currencyCode);
        }

        assertThat(PriceMath.currencyCode())
                .isEqualTo("VND");
    }

    @Test
    void constructionMockIsScopedAndRestored() {
        try (MockedConstruction<PriceMath> constructed =
                     mockConstruction(
                             PriceMath.class,
                             (mock, context) ->
                                     when(mock.addFee(100, 5))
                                             .thenReturn(42))) {
            PriceMath created = new PriceMath();

            assertThat(created.addFee(100, 5))
                    .isEqualTo(42);
            assertThat(constructed.constructed())
                    .containsExactly(created);
        }

        assertThat(new PriceMath().addFee(100, 5))
                .isEqualTo(105);
    }

    @Test
    void explicitInlineMakerSupportsFinalType() {
        PriceMath math = mock(
                PriceMath.class,
                withSettings().mockMaker(MockMakers.INLINE));

        when(math.addFee(10, 5)).thenReturn(99);
        assertThat(math.addFee(10, 5)).isEqualTo(99);
        verify(math).addFee(10, 5);
    }
}
```

`MockedStatic` and `MockedConstruction` implement scoped mocking; **closing via `try-with-resources`** is mandatory so mocks do not contaminate the test thread afterward. Static mocks apply strictly to the thread creating the scope; never treat them as global fakes for background async threads.

### 9.2. `AlternativeMockMakerTest.java` — 2 tests

```java
// src/test/java/com/example/mockitoagent/AlternativeMockMakerTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.mockito.MockMakers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.withSettings;

class AlternativeMockMakerTest {

    @Test
    void subclassMakerMocksOverridableClass() {
        OpenPricePolicy policy = mock(
                OpenPricePolicy.class,
                withSettings().mockMaker(MockMakers.SUBCLASS));

        when(policy.adjust(100)).thenReturn(91);
        assertThat(policy.adjust(100)).isEqualTo(91);
        verify(policy).adjust(100);
    }

    @Test
    void proxyMakerMocksInterfaceOnly() {
        DiscountGateway gateway = mock(
                DiscountGateway.class,
                withSettings().mockMaker(MockMakers.PROXY));

        when(gateway.discountPercent("u-1"))
                .thenReturn(15);

        assertThat(gateway.discountPercent("u-1"))
                .isEqualTo(15);
        verify(gateway).discountPercent("u-1");
    }
}
```

This class does not attempt mocking `PriceMath` with `SUBCLASS` since it is `final`; an intentionally failing test does not belong in the runnable suite. Use a separate exercise to observe that exception instead of making Maven CI permanently red.

### 9.3. `BillingServiceTest.java` — 2 pure unit tests

```java
// src/test/java/com/example/mockitoagent/BillingServiceTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class BillingServiceTest {

    @Mock
    DiscountGateway gateway;

    @InjectMocks
    BillingService service;

    @Test
    void totalUsesDiscountFromMock() {
        when(gateway.discountPercent("u-1"))
                .thenReturn(15);

        assertThat(service.totalFor("u-1", 200))
                .isEqualTo(170);

        verify(gateway).discountPercent("u-1");
    }

    @Test
    void invalidInputDoesNotCallGateway() {
        assertThatThrownBy(
                () -> service.totalFor(" ", 100))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("invalid billing request");

        verifyNoInteractions(gateway);
    }
}
```

Mockito's `@InjectMocks` instantiates the service via constructor. It is not Spring `@Autowired` and starts no `ApplicationContext`.

### 9.4. `BillingControllerSliceTest.java` — 2 MVC tests

```java
// src/test/java/com/example/mockitoagent/BillingControllerSliceTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BillingController.class)
class BillingControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    BillingService service;

    @Test
    void controllerUsesMockedFinalService()
            throws Exception {
        when(service.totalFor("u-1", 100))
                .thenReturn(85);

        mvc.perform(get("/billing/u-1")
                        .param("subtotal", "100"))
                .andExpect(status().isOk())
                .andExpect(content().string("85"));

        verify(service).totalFor("u-1", 100);
    }

    @Test
    void missingParameterDoesNotInvokeService()
            throws Exception {
        mvc.perform(get("/billing/u-2"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

`@MockitoBean` swaps the `final` service bean inside the MVC slice. `@WebMvcTest` omits real business services by default; this is a controller wiring/routing test against a mock Servlet environment, not an end-to-end TCP server test.

### 9.5. `BillingSpringIntegrationTest.java` — 1 full-context test

```java
// src/test/java/com/example/mockitoagent/BillingSpringIntegrationTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class BillingSpringIntegrationTest {

    @Autowired
    BillingService service;

    @MockitoBean
    DiscountGateway gateway;

    @Test
    void fullContextUsesGatewayOverride() {
        when(gateway.discountPercent("u-2"))
                .thenReturn(25);

        assertThat(service.totalFor("u-2", 200))
                .isEqualTo(150);

        verify(gateway).discountPercent("u-2");
    }
}
```

Here we have the real `BillingService` bean plus a mocked `DiscountGateway` inside the Spring context. `@SpringBootTest` does **not** start an embedded HTTP server by default. This test does not verify remote provider contracts, production tracing, or transaction semantics.

### 9.6. Test Count and Run Commands

| Test Class | `@Test` Methods | What Is Verified |
| --- | ---: | --- |
| `InlineMockMakerTest` | 4 | Final/static/constructor/per-mock inline |
| `AlternativeMockMakerTest` | 2 | Subclass/proxy per mock |
| `BillingServiceTest` | 2 | `MockitoExtension` |
| `BillingControllerSliceTest` | 2 | `@WebMvcTest` and `@MockitoBean` |
| `BillingSpringIntegrationTest` | 1 | `@SpringBootTest` and `@MockitoBean` |
| **Total** | **11** | No Docker, no external services |

```bash
java -version
mvn -version

# Inline canaries:
mvn -B -ntp -Dtest=InlineMockMakerTest test

# Alternative mock makers:
mvn -B -ntp -Dtest=AlternativeMockMakerTest test

# Pure unit:
mvn -B -ntp -Dtest=BillingServiceTest test

# Spring slice/full:
mvn -B -ntp -Dtest=BillingControllerSliceTest,BillingSpringIntegrationTest test

# All 11 methods:
mvn -B -ntp test
```

**Expected from source:** tests PASS when JDK/Mockito/Byte Buddy align and Surefire launches the test JVM with the Mockito agent. These are instructions for the reader to **execute themselves**. Do not claim Maven/JUnit ran or fabricate `BUILD SUCCESS` logs or millisecond timings.

## 10. Troubleshooting by Symptom

### 10.1. Dynamic Warning on JDK 21, Assertions Still Green

Situation: Mockito self-attached successfully, yet the JVM emitted JEP 451 warnings.

Fix: use `maven-dependency-plugin:properties` and Surefire `-javaagent:${org.mockito:mockito-core:jar}`. Confirm the agent reaches the **test JVM**, then rerun the final/static canary. If warnings persist from other agents, inspect those specific agents rather than disabling all JVM logging.

### 10.2. Inline Mock Maker Fails to Initialize

Checklist:

1. Are `java -version` and `mvn -version` pointing to the expected JDK/VM vendor?
2. Which Mockito and Byte Buddy versions resolved?
3. Did an exclusion drop `byte-buddy-agent` or `byte-buddy`?
4. Is startup `-javaagent` pointing to the exact Mockito core jar in the test JVM?
5. Does the JVM support instrumentation/redefinition?
6. Is it running inside a custom JRE, Android, native image, or restricted container?
7. Is a mock-maker extension file or `mockito-subclass` overriding plugin selection?
8. Did the root cause stack trace fail during agent attach or class transformation?

Do not use `--add-opens` as a blanket remedy; consider targeted module options only after security review confirms JPMS encapsulation is the actual root cause.

### 10.3. Final Mocking Fails After Changing Mock Maker

`SUBCLASS` cannot extend a `final` class or override `final` methods. `PROXY` mocks interfaces only. Use `INLINE` where supported, or refactor production code to accept an interface/port and test behavior cleanly. Never suppress with `@SuppressWarnings` or force Mockito to ignore it.

### 10.4. Static Mock Leaks Cause Subsequent Tests to Fail

`MockedStatic` and `MockedConstruction` must be closed. For static mocks:

```java
try (MockedStatic<PriceMath> scoped =
             Mockito.mockStatic(PriceMath.class)) {
    // mock and assert in this scope
}
// MockedStatic.close() runs automatically.
```

Never store a static mock in a field shared across test classes or carry it across thread boundaries. For fake time, inject `Clock` instead of static-mocking globally.

### 10.5. `@MockitoBean` Fails to Replace the Expected Bean

- Plain JUnit `@Mock` fields do not register Spring beans.
- `@WebMvcTest` loads only MVC beans and needs mocked service collaborators.
- Multiple beans implementing the same interface require qualifiers or `name`.
- `@MockitoBean(enforceOverride=true)` catches missing targets instead of silently creating new beans via `REPLACE_OR_CREATE`.
- Target bean is `final` while a global `mockito-extensions` file forced `SUBCLASS`.
- Cached contexts running in parallel race on mock resets and stubs.

Do not swap every slice into `@SpringBootTest` simply because a bean override missed; fix imports and matching metadata.

### 10.6. JaCoCo Report Turns Empty After Adding the Agent

If Surefire `argLine` specifies only the Mockito agent, JaCoCo `prepare-agent` flags get dropped. Preserve `@{argLine}` late replacement and define an empty default `argLine` property. Confirm the forked JVM command carries both JaCoCo and Mockito agents, without pulling JaCoCo into production runtime.

### 10.7. Forked VM Terminated Without Goodbye

This generic Surefire error means the forked test JVM died abnormally. Inspect `target/surefire-reports`, dump logs, and the exact JVM command:

- Unexpanded literal `@{argLine}`.
- Unexpanded literal `${org.mockito:mockito-core:jar}` or invalid jar path.
- `forkCount=0` bypassing fork flags.
- Incompatible or unreadable agent JAR.
- JaCoCo and Mockito agents overwriting each other.
- `System.exit()` inside a test, `OutOfMemoryError`, or native JVM crash.
- Windows path quoting or CI environment differences.

Never turn a failing build green with `mvn test || true`.

### 10.8. Byte Buddy Does Not Support a Newer JDK

Errors like "Unsupported class file major version" or "Java N not supported" call for checking the Mockito/Byte Buddy/JDK support matrix. Upgrade the Spring Boot patch/version with managed dependencies aligned. Avoid keeping an old Mockito 5.x while overriding a mismatched Byte Buddy jar arbitrarily; align versions and run the canary tests.

### 10.9. IDE Red, Maven Green

IDE JUnit runners usually ignore Maven Surefire `argLine`. Delegate test runs to Maven/Gradle or configure matching VM arguments on the IDE test runner. Check the IDE runner's runtime JDK/path, not just the project language level.

### 10.10. Passing MockMaker Checks Do Not Replace Integration Tests

Mockito tests verify contracts at mock seams, not real HTTP, database, or broker integrations. `verify(gateway).discountPercent("u-1")` does not prove a production endpoint connects or a database transaction commits.

## 11. Security and JDK Upgrade Readiness Testing

### 11.1. Why Does JEP 451 Matter?

A Java agent can rewrite bytecode inside a live JVM. Integrity-by-default pushes operators to explicitly authorize agents at JVM startup rather than letting libraries self-attach mid-run. Declaring `-javaagent` in the test build keeps it reviewable, dependency-pinned, and auditable.

**Never** push the Mockito agent or `EnableDynamicAgentLoading` into production JVMs just because tests warned in CI. Keep production privileges minimal and audit any production agents separately.

### 11.2. Diagnosing Readiness with Dynamic Attach Disabled

On HotSpot JDKs supporting this flag, a diagnostic job can run:

```text
-XX:-EnableDynamicAgentLoading
-javaagent:<resolved Mockito core jar>
```

to confirm inline Mockito works under **startup instrumentation** even when dynamic agent loading is disabled. This is an optional diagnostic check per environment, not mandatory config, as coverage or profiler tools may still rely on dynamic attach.

### 11.3. Essential Canary Tests

A test mocking only interfaces can pass under `PROXY` or `SUBCLASS` without proving inline instrumentation works. When upgrading JDK, Mockito, or Byte Buddy, keep these canaries:

- Mock a **`final`** class.
- Mock a static method and close its scope.
- Mock construction and close its scope if tests rely on it.
- `@MockitoBean` on a `final` service inside a slice if your team uses that pattern.
- Run test fork startup flags across JDK 17, JDK 21, and candidate runtimes.

**Do not** suppress JDK 21 warnings across the whole suite; instead record the agent jar path and pin it into the build.

## 12. Quick Diagnostic Matrix

| Signal | Classification | How to Confirm |
| --- | --- | --- |
| JDK 21 dynamic attach warning | Warning, not necessarily failure | Run tests and check outcomes |
| Final mock fails to initialize | Instrumentation/maker | Run inline canary, read root cause |
| Mockito 5.x + legacy `mockito-inline` | Classpath/version risk | Inspect dependency tree |
| Byte Buddy unsupported major version | JDK/library mismatch | Upgrade BOM-managed versions |
| Mockito init fails on JDK 17 restricted runtime | Agent capability limit | Explicit startup agent + check vendor |
| Plain Mockito works yet `@MockitoBean` fails | Spring context/config | Check annotation/import and qualifiers |
| Final mock fails under `SUBCLASS` | Maker cannot extend final | Switch to `INLINE` or interface port |
| `PROXY` maker errors on concrete class | Wrong target type | Mock interfaces only |
| `mockStatic` already registered | Unclosed scope | Wrap in `try-with-resources` |
| JaCoCo coverage disappears | Overwritten `argLine` | Use `@{argLine}` late replacement |
| Maven passes, IDE fails | Test VM mismatch | Compare launch args and JDK |
| Surefire fork crashes | JVM launch/agent/crash | Inspect fork command and dumps |
| Full-context tests slow after overrides | Cache keys split | Standardize `@MockitoBean` qualifiers |
| Concurrent shared Mockito bean failures | Mock reset/stub race | Serialize or use isolated unit mocks |

## 13. Pre-Merge Checklist for Mockito/JDK Changes

- [ ] Verified the JDK running the **test JVM**, not just Java source target.
- [ ] Mockito 5 inline maker is default; omitted legacy `mockito-inline` unless explicitly needed.
- [ ] Mockito, Byte Buddy, and Byte Buddy Agent aligned under dependency management.
- [ ] `-javaagent` points to `mockito-core` jar at **test fork startup**.
- [ ] Maven dependency plugin properties resolve the jar path portably.
- [ ] Surefire `forkCount` and `argLine` configured; agent not put only on Maven parent.
- [ ] `@{argLine}` preserves JaCoCo and other agents.
- [ ] Empty default `argLine` property exists when needed to avoid literal expansion errors.
- [ ] IDE test runner uses equivalent agent args or delegates to Maven.
- [ ] JDK 17/21 matrix executes the inline canary.
- [ ] Dynamic attach flags never enabled on production JVMs.
- [ ] `SUBCLASS` never used on `final` classes or `final` methods.
- [ ] `PROXY` never used on concrete classes.
- [ ] `mockStatic` and `mockConstruction` closed cleanly via scope.
- [ ] Spring `@MockitoBean` kept distinct from plain Mockito `@Mock`.
- [ ] Bean override qualifiers, context cache impact, and concurrency audited.
- [ ] Mockito mocks never treated as proof of real AOP/DB/HTTP behavior.
- [ ] Unsupported class file errors resolved via compatible library/JDK versions.
- [ ] On failures, captured root cause stack trace, JVM args, and dependency tree.
- [ ] Never claimed tests PASSED without actually executing them.

## 14. Exercises

1. Run `InlineMockMakerTest` on JDK 17 and 21; compare warnings and confirm the test fork receives the startup Mockito agent.
2. Remove the startup agent on an experimental branch and compare the JEP 451 warning against failures on your JVM without touching production flags.
3. Try mocking `final` `PriceMath` with `SUBCLASS` in a separate exercise; explain why it fails, then refactor behind an interface seam.
4. Exercise `MockMakers.PROXY` with `DiscountGateway` and a concrete class; note the interface-only limit.
5. Remove the `try-with-resources` close on `MockedStatic` in a sandbox to observe mock leakage, then restore `try-with-resources`.
6. Use `MockitoExtension` `@Mock` and Spring `@MockitoBean` in two tests, showing which object Spring autowires.
7. Add JaCoCo `prepare-agent` and confirm the test JVM receives both the coverage agent and Mockito agent.
8. Run directly in the IDE vs Maven; compare launcher/test JDKs, classpaths, and JVM args.
9. Set up a candidate JDK CI job and inspect the dependency tree if an unsupported class format error occurs.
10. On a test-only HotSpot VM, test disabling dynamic attach alongside the explicit startup Mockito agent, noting whether other agents fail.
11. Refactor a static `Clock.systemUTC` wrapper to a constructor-injected `Clock` to eliminate static mocking in async code.
12. Build an error classifier distinguishing warnings, `MockitoInitializationException`, unsupported class versions, bean-override failures, and Surefire fork crashes.

## 15. Self-Check Questions

**1.** Which mock maker is default in Mockito 5? — `INLINE`.

**2.** Is `MockMaker` a Java agent? — No. `MockMaker` is Mockito's mock creation strategy; a Java agent supplies `Instrumentation`.

**3.** Does a JDK 21 warning mean all tests are failing? — No; inspect test status and root causes.

**4.** What is the recommended setup for inline mocking on Java 21+? — Passing `-javaagent` pointing to the `mockito-core` jar on the test JVM at startup.

**5.** Is `-XX:+EnableDynamicAgentLoading` better than a startup agent? — No; it still relies on dynamic attachment.

**6.** Can `SUBCLASS` mock a `final` class? — No.

**7.** Can `PROXY` mock a concrete class? — No; it handles interfaces only.

**8.** Why wrap `MockedStatic` in `try-with-resources`? — To close its scope and prevent static mock leakage.

**9.** Does `@Mock` register a mock as a Spring bean? — No; `@MockitoBean` overrides beans in the Spring context.

**10.** Does `@MockitoBean` bypass agent attachment errors? — No; it still relies on Mockito's mock maker.

**11.** Does `MAVEN_OPTS` always reach the Surefire fork? — No.

**12.** Why is `@{argLine}` useful? — It preserves flags injected by JaCoCo via late property replacement.

**13.** What should you check on `Unsupported class file major version`? — Byte Buddy, Mockito, and JDK compatibility.

**14.** Does a passing final-class mock prove production app compatibility on every JDK? — No; it only verifies that mock instrumentation boundary.

## 16. Official References

- [Mockito 5.17 Javadoc — Mockito](https://javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/Mockito.html): inline default; section 0.3 Java 21 agent Maven/Gradle config; static/constructor mocking APIs.
- [Mockito 5.17 — MockMakers](https://javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/MockMakers.html): `INLINE`/`SUBCLASS`/`PROXY` and constraints.
- [Mockito 5.17 — MockedStatic](https://javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/MockedStatic.html): scoped static mock lifecycle.
- [Mockito 5.17 — MockedConstruction](https://javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/MockedConstruction.html): constructor interception scope.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): dynamic agent loading warnings and integrity-by-default.
- [Oracle JDK 21 Release Notes](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): `EnableDynamicAgentLoading` semantics.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@SpringBootTest`, and `MockitoBean` tests.
- [Spring Framework 6.2 — MockitoBean & MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean matching and overrides.
- [Spring Boot 3.5 — Dependency versions](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Mockito/Byte Buddy BOM.
- [Apache Maven Surefire — fork options](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options.html): `forkCount`/`reuseForks`.
- [Apache Maven Surefire — test mojo](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo): `argLine`/late replacement.
- [JaCoCo — Maven prepare-agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html): coverage Java agent integration.
- [Gradle — Testing Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `Test` task JVM args.

**Conclusion:** Mockito 5 inline is a **mock maker**, while a Java agent is the mechanism supplying JVM instrumentation to it. JDK 21 warns about **dynamic loading** without automatically failing tests; when inline mocking needs instrumentation, configure `-javaagent` pointing to `mockito-core` at **test JVM startup** per Mockito docs. `SUBCLASS` and `PROXY` suit clean test seams yet cannot handle final/static/constructor mocking. During troubleshooting, inspect the **runtime** JDK, Mockito/Byte Buddy **dependency tree**, Surefire/IDE **JVM args**, Mockito's **MockMaker**, and Spring `@MockitoBean` wiring rather than applying a blanket workaround flag.