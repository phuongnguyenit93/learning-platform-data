# Mockito, Bytecode Mocking, and Agent Requirements

During a **Java Advance Compatibility Migration**, a project may compile cleanly yet its unit tests start emitting warnings or failing upon changing the JDK. Common symptoms include Mockito failing to initialize the inline mock maker, Byte Buddy failing to understand a newer class-file version, mocking a `final` class failing, or JDK 21+ warning that a Java agent was loaded dynamically into a running JVM.

These symptoms stem from an important fact: Mockito does not merely create ordinary fake objects. To supply mocks, it can **generate subclasses or transform bytecode** using Byte Buddy. Some mechanisms, especially **inline mocking** for final classes, static methods, and constructors, require `java.lang.instrument.Instrumentation` access, typically provided by a **Java agent**.

This lesson explains mocking mechanisms, differences between the subclass and inline mock makers, the relationship between Mockito, Byte Buddy, and Java agents, JDK 21 changes under JEP 451, how to configure the agent in Maven/Gradle, errors from JPMS and class-file versions, and a migration workflow to keep test suites stable. The goal is accurately diagnosing **test infrastructure** failures rather than mistaking them for business logic bugs.

## 1. How Does Mockito Create a Test Double?

Suppose a service depends on a payment gateway:

~~~java
public interface PaymentGateway {
    boolean charge(String orderId, long minorUnits);
}
~~~

~~~java
public final class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public boolean checkout(String orderId, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        return gateway.charge(orderId, amount);
    }
}
~~~

Test with Mockito and JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void chargesPositiveAmount() {
        PaymentGateway gateway = mock(PaymentGateway.class);
        when(gateway.charge("ord-1", 12500L)).thenReturn(true);

        CheckoutService service = new CheckoutService(gateway);

        assertTrue(service.checkout("ord-1", 12500L));
        verify(gateway).charge("ord-1", 12500L);
        verifyNoMoreInteractions(gateway);
    }
}
~~~

Here `gateway` is a mock, not a real payment gateway. The test uses `when(...).thenReturn(...)` to stub outcomes and `verify(...)` to inspect calls.

Common terminology:

| Test double kind | Role | Example |
|---|---|---|
| Mock | Configures behavior and tracks interactions | `verify(gateway).charge(...)` |
| Stub | Supplies controlled return data | Repository returning a sample entity |
| Spy | Wraps a real object, overriding only selected methods | `spy(realService)` |
| Fake | Lightweight implementation with real logic | In-memory repository |
| Fixture | Fixed data or setup for tests | Sample JSON, entities, test tokens |

**Not every mock requires a Java agent.** Mocking an interface by generating an implementation or mocking an ordinary class via subclassing usually works without inline instrumentation. An agent becomes essential when using a mock maker that must transform existing classes.

### 1.1. Why Are Mocks Not Integration Tests?

Mockito isolates `CheckoutService` logic, yet tests do not prove:
- Real gateways support TLS, proxies, or newer APIs.
- HTTP clients/JSON serializers run properly on the target JDK.
- Database drivers, timezones, native dependencies, and security properties are compatible.
- Real dependency bytecode loads cleanly on the production JVM.

During migration, keep both **unit tests** and **integration/contract tests**. Passing mocked tests does not mean the whole system is compatible with the new JDK.

## 2. Byte Buddy, MockMaker, and JVM Instrumentation

Mockito uses the **MockMaker** extension point to determine how mocks are built. Byte Buddy is the library handling generation, definition, and transformation of class files; that process must align with the Java class-file format and active JVM rules.

~~~text
                 Mockito.mock(Type.class)
                           |
                           v
                     Mockito API
                           |
                           v
                        MockMaker
                           |
                +----------+----------+
                |                     |
                v                     v
        Subclass mock maker     Inline mock maker
                |                     |
        Byte Buddy creates      Byte Buddy retransforms/
        a subclass              instruments target class
                |                     |
        JVM loads subclass       java.lang.instrument
                |                Instrumentation / agent
                +----------+----------+
                           |
                        Mock object
                           |
                   stub / verify calls
~~~

### 2.1. Subclass Mock Maker

The subclass mechanism generates a subclass extending the target type and overrides methods to intercept calls. It generally suits:
- Java interfaces.
- Non-`final` classes that can be subclassed.
- Methods eligible for overriding.
- Tests that do not need to intercept static methods or constructors.

**Limitations:** it cannot subclass `final` classes, cannot override `final` methods, and cannot turn static methods into virtual methods via overriding. Therefore, if a test mocks a `final` type under the subclass maker, the test can fail even if the JDK supports agents.

Subclassing still uses bytecode generation, yet **does not require self-attaching an agent** for ordinary mocks. This explains why environments restricting instrumentation can still execute many Mockito tests.

### 2.2. Inline Mock Maker

The inline mock maker instruments the target class's bytecode, enabling additional use cases:
- Mocking `final` classes or `final` methods within supported scope.
- Mocking static methods via `Mockito.mockStatic(...)`.
- Mocking constructor calls via `Mockito.mockConstruction(...)`.
- Intercepting methods that cannot be overridden via subclassing.

This mechanism typically requires `Instrumentation`. Mockito/Byte Buddy may attempt to self-attach an agent to the already running JVM if instrumentation is unavailable at startup. When the JDK disallows or warns about dynamic agent loading, that initialization becomes environment-sensitive.

Inline mocking also has limits: certain native methods, core JVM types, special class loaders/modules, finalizers, and internal VM mechanisms cannot be mocked arbitrarily. Do not interpret "inline" as "able to mock every class and method."

### 2.3. What Is a Java Agent?

A Java agent is a JAR containing a compliant agent entry point, allowing the JVM to supply an `Instrumentation` instance. When specified at startup:

~~~bash
java -javaagent:/path/to/compatible-agent.jar ...
~~~

the agent can register transformers or use redefinition/retransformation mechanisms permitted by the JVM. The path must point to a **JAR genuinely containing a valid agent manifest/entry point**, not just any JAR with "agent" in its filename.

Three components to distinguish:

| Component | Purpose | What to Pin |
|---|---|---|
| `mockito-core` | Mockito API and mock maker implementation | Version supporting JDK/test runtime |
| `byte-buddy` | Generates/modifies bytecode | Version understanding class-file release |
| `byte-buddy-agent` / Java agent | Supplies instrumentation via matching mechanism | Version/attach mode and JVM policy |

Per modern Mockito 5 documentation, passing the **`mockito-core` JAR itself** to `-javaagent` can supply instrumentation when the test JVM starts. Verify against your **exact Mockito version** before applying, rather than substituting a cached `byte-buddy-agent` JAR solely because a warning mentions that name.

## 3. Key Mockito Milestones When Upgrading Java

| Aspect | Mockito 4 | Mockito 5 |
|---|---|---|
| Java baseline | Supports Java 8+ | Requires Java 11+ |
| Default mock maker | Subclass was default prior to Mockito 5 | Inline became default starting in 5.0 |
| Mocking final/static/constructor | Requires compatible inline version/config | Inline available by default when JVM allows |
| Java agent startup | Depends on mock maker and use case | Should be configured explicitly for inline on JDK 21+ |
| `mockito-inline` artifact | Previously used to opt into inline | Generally unnecessary since inline is default |
| Running on newer JDKs | Depends on Mockito/Byte Buddy version | Depends on Mockito/Byte Buddy version |

**Mockito 5 cannot run on a Java 8 JVM merely via a compiler flag.** If your project's test runtime remains Java 8, keep a Mockito version supporting Java 8 or update the test runtime. Conversely, a product library can still be compiled with `--release 8` while tests run on a newer JDK, provided the released artifact is actually tested on Java 8 per support commitments.

### 3.1. MockMaker Extensions and Legacy Config

Some projects contain:

~~~text
src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker
~~~

Contents:

~~~text
mock-maker-inline
~~~

to select the inline mock maker in older Mockito versions. With Mockito 5, inline is normally the default; the old extension file may no longer be needed.

If there is a reason to use the subclass mock maker, use the matching token:

~~~text
mock-maker-subclass
~~~

However, after switching, tests using `mockStatic`, `mockConstruction`, or mocking `final` classes may fail. Check actual usage before changing. Avoid leaving multiple extension files from dependencies/test resources that make Mockito pick an unintended mock maker.

### 3.2. Mockito Jupiter Extension

In JUnit 5, integration typically uses `mockito-junit-jupiter`:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class CheckoutWithExtensionTest {
    @Mock PaymentGateway gateway;
    @InjectMocks CheckoutService service;

    @Test
    void rejectsZeroAmount() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.checkout("ord-1", 0L)
        );
    }
}
~~~

Pin `mockito-core` and `mockito-junit-jupiter` to the same compatible version/family. If a test runner fails to discover JUnit 5 tests, verify Gradle `useJUnitPlatform()` or Maven Surefire/JUnit integration before assuming an agent bug.

## 4. JEP 451 and JDK 21+: Dynamic Agent Loading

**JEP 451 — Prepare to Disallow the Dynamic Loading of Agents** introduces warnings starting in JDK 21 when a Java agent or JVMTI agent is **dynamically loaded into an already running JVM**. The intent is preparing for a future release that may disallow dynamic agent loading by default to improve JVM integrity.

When Mockito inline lacks `Instrumentation`, Byte Buddy may self-attach an agent. On HotSpot/OpenJDK JDK 21+, the JVM can emit a warning such as:

~~~text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: If a serviceability tool is in use, please run with
         -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: If a serviceability tool is in use, please run with
         -Djdk.instrument.traceUsage for more information
WARNING: Dynamic loading of agents will be disallowed by default
         in a future release
~~~

**A warning is not a test failure**, yet it signals a mechanism needing remediation before runtimes tighten policies. Do not wait until CI jobs fail before configuring the agent.

### 4.1. Startup Agent vs. Dynamic Attach

| Mechanism | When Applied | Meaning |
|---|---|---|
| `-javaagent:path/to/mockito-core.jar` | Before test JVM executes main | Agent explicitly declared; matches modern Mockito guidance |
| Mockito/Byte Buddy self-attach | After JVM is already running | Can trigger JDK 21+ warnings or fail under JVM policy |
| `-XX:+EnableDynamicAgentLoading` | JVM launcher option | Allows dynamic attach and may suppress warnings on JDK 21; not preferred |
| `-XX:-EnableDynamicAgentLoading` | JVM launcher option | Disallows dynamic attach; helpful to detect reliance on self-attach |
| `-Djdk.instrument.traceUsage` | JVM system property | Helps diagnose `Instrumentation` usage |

**Do not use `-XX:+EnableDynamicAgentLoading` solely to silence warnings** if tests genuinely need inline mocking. The intentional solution is configuring `-javaagent` at test JVM startup.

Nor should you assume all JDK 21+ releases already block dynamic agent loading by default: when warnings turn into hard blocks depends on release and vendor. For newer JDKs, check release notes of the actual runtime rather than guessing a cutoff solely from JDK 21 warnings.

### 4.2. Why Is JEP 451 Related to Security?

Dynamic attach grants agents low-level power to inspect/modify running code. Java is moving toward letting the JVM process owner decide upfront before allowing such tools to load. When test runtimes declare the agent via a launcher option, instrumentation privileges become explicit, auditable, and independent of library self-attachment.

This does not mean putting Mockito agents into production. **Mockito is a test dependency** in normal setups; test agents belong strictly on the test JVMs that need them.

## 5. Configuring the Mockito Java Agent in Gradle Kotlin DSL

In Gradle, `testImplementation` places Mockito onto the test classpath yet **does not automatically add the `-javaagent` JVM launcher option**. Create a dedicated configuration resolving only the agent JAR, then pass it to `Test` tasks.

Example `build.gradle.kts`. Placeholder versions must be replaced with pinned, verified versions:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

val mockitoVersion = "REPLACE_WITH_PINNED_MOCKITO_VERSION"
val mockitoAgent = configurations.create("mockitoAgent")

dependencies {
    testImplementation("org.mockito:mockito-core:" + mockitoVersion)
    testImplementation("org.mockito:mockito-junit-jupiter:" + mockitoVersion)
    testImplementation("org.junit.jupiter:junit-jupiter:REPLACE_WITH_JUNIT_VERSION")

    mockitoAgent("org.mockito:mockito-core:" + mockitoVersion) {
        isTransitive = false
    }
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    jvmArgs("-javaagent:" + mockitoAgent.asPath)
}
~~~

Here:
1. Mockito APIs still resolve normally via `testImplementation`.
2. `mockitoAgent` resolves the exact matching `mockito-core` JAR version.
3. `isTransitive = false` prevents passing a list of transitive JARs inside a single `-javaagent` argument.
4. `jvmArgs(...)` delivers the option to the **forked test JVM**, not the Gradle daemon.
5. The test runner must use a Mockito version documented as loadable via `-javaagent`.

This is a minimal configuration template. Do not run before replacing placeholders. Manage JUnit/Mockito versions via your repository's BOM, version catalog, or conventions.

### 5.1. Gradle CommandLineArgumentProvider

For builds using configuration/build caching and relocatability, Gradle recommends `CommandLineArgumentProvider` with tracked input files. Replace `jvmArgs(...)` with a provider to avoid untracked path inputs:

~~~kotlin
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.process.CommandLineArgumentProvider

abstract class MockitoAgentProvider : CommandLineArgumentProvider {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val agentJar: ConfigurableFileCollection

    override fun asArguments(): Iterable<String> =
        listOf("-javaagent:" + agentJar.singleFile.absolutePath)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    jvmArgumentProviders.add(
        objects.newInstance(MockitoAgentProvider::class.java).apply {
            agentJar.from(mockitoAgent)
        }
    )
}
~~~

This snippet relies on `mockitoAgent` declared above. **Do not enable both the provider and `jvmArgs("-javaagent:...")` simultaneously** if both load the Mockito agent, as duplicate agent loading can cause errors or side effects.

If the build has custom `integrationTest`, multiple JVM test suites, or non-standard tasks outside `Test`, add the option to the **exact tasks launching JVMs that use inline mocks**.

### 5.2. Groovy DSL

Example `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

configurations {
    mockitoAgent
}

dependencies {
    testImplementation 'org.mockito:mockito-core:REPLACE_WITH_VERSION'
    testImplementation 'org.mockito:mockito-junit-jupiter:REPLACE_WITH_VERSION'

    mockitoAgent('org.mockito:mockito-core:REPLACE_WITH_VERSION') {
        transitive = false
    }
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    jvmArgs '-javaagent:' + configurations.mockitoAgent.asPath
}
~~~

This illustrates option placement; add JUnit 5 dependencies and manage versions per your project. For builds with strict caching requirements, prefer declaring the agent file as a tracked task input.

### 5.3. Gradle Daemon JDK Does Not Equal Test JDK

Example:

~~~text
Gradle daemon: JDK 21
Compiler toolchain: JDK 17
Test JVM: JDK 21
Application runtime floor: Java 17
~~~

`org.gradle.jvmargs` controls the Gradle daemon, **not test JVM args**. The agent belongs in `Test.jvmArgs` or `Test.jvmArgumentProviders`. If an IDE runs tests directly with its own JUnit launcher rather than delegating to Gradle, the IDE may omit Gradle's agent config; verify actual workflows.

## 6. Configuring Maven Surefire/Failsafe

In Maven, `mockito-core` usually uses `test` scope. For startup agent loading, pass `-javaagent:path/to/mockito-core.jar` through Surefire/Failsafe JVM fork `argLine`.

Partial `pom.xml` example (placeholders must be replaced and checked against your actual plugin versions):

~~~xml
<properties>
    <mockito.version>REPLACE_WITH_PINNED_MOCKITO_VERSION</mockito.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-core</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
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
            <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
            <configuration>
                <argLine>-javaagent:${org.mockito:mockito-core:jar}</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The Maven Dependency Plugin's `properties` goal sets properties holding resolved JAR paths, avoiding hard-coding paths into `~/.m2/repository`. Verify property behavior and lifecycle execution with your pinned plugin version.

**Do not use the template verbatim with unreplaced placeholders.** Add required JUnit dependencies/plugins for your project; verify the resolved Mockito JAR actually contains the proper agent manifest.

### 6.1. If the Project Uses JaCoCo

JaCoCo commonly populates the JVM `argLine` property to attach its coverage agent. Overwriting `argLine` with only Mockito lets tests run yet silently drops coverage.

With Surefire supporting late property evaluation:

~~~xml
<properties>
    <argLine></argLine>
</properties>

<configuration>
    <argLine>
        @{argLine} -javaagent:${org.mockito:mockito-core:jar}
    </argLine>
</configuration>
~~~

This illustrates preserving JaCoCo's `argLine` while appending Mockito. In a real repository, verify plugin execution order, property names, multi-agent configs, and the resulting JVM command line. Never duplicate agents or assume all Maven plugins share `argLine` automatically.

Maven Failsafe runs integration tests in another lifecycle phase; if Failsafe tests use inline mocks, configure JVM args on Failsafe too. When Maven and test forks use **different JDKs** via toolchains, the agent must be compatible with the **test JDK**.

## 7. Example: Mocking a Final Class

Suppose an external API is a `final` class:

~~~java
public final class RateClient {
    public int currentRate(String currency) {
        return 100;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class RateClientTest {
    @Test
    void mocksFinalClass() {
        RateClient client = mock(RateClient.class);
        when(client.currentRate("USD")).thenReturn(25000);

        assertEquals(25000, client.currentRate("USD"));
        verify(client).currentRate("USD");
    }
}
~~~

In Mockito 5 with the inline mock maker active and a JVM supporting instrumentation, this test works. With the subclass mock maker, `RateClient` cannot be subclassed because it is `final`.

To avoid coupling to concrete implementations, consider wrapping third-party `final` classes behind an adapter/interface rather than mocking them directly. In legacy codebases, however, inline mocking can be a helpful transitional step while refactoring is deferred.

## 8. Example: Mocking Static Methods with MockedStatic

A legacy utility:

~~~java
public final class EnvironmentMode {
    private EnvironmentMode() {}

    public static String current() {
        return "PRODUCTION";
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;

class EnvironmentModeTest {
    @Test
    void overridesStaticMethodTemporarily() {
        try (MockedStatic<EnvironmentMode> mocked =
                     mockStatic(EnvironmentMode.class)) {

            mocked.when(EnvironmentMode::current)
                  .thenReturn("TEST");

            assertEquals("TEST", EnvironmentMode.current());
            mocked.verify(EnvironmentMode::current);
        }

        assertEquals("PRODUCTION", EnvironmentMode.current());
    }
}
~~~

**Manage scope carefully:** use try-with-resources to close static mocks. Leaving one unclosed can leak interception to subsequent tests on the same thread, causing failures only under parallel or full-suite execution.

Static mocks have scope and thread-affinity semantics; do not assume a mock created on one thread applies to every asynchronous task. Avoid mocking core JVM classes, `System`, or classes interacting with threads/class loaders, as Mockito may not support them and side effects are hard to diagnose.

When testing time-dependent logic, prefer injecting `java.time.Clock` instead of mocking JDK `now()` static methods.

## 9. Example: Mocking Constructors with MockedConstruction

Legacy code instantiating dependencies inside methods:

~~~java
public class ExternalReader {
    public String load() {
        return "REAL";
    }
}
~~~

~~~java
public final class ReaderService {
    public String read() {
        return new ExternalReader().load();
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.mockito.MockedConstruction;

class ReaderServiceTest {
    @Test
    void mocksNewInstancesInsideScope() {
        try (MockedConstruction<ExternalReader> scope =
                     mockConstruction(
                             ExternalReader.class,
                             (mock, context) ->
                                     when(mock.load()).thenReturn("STUB")
                     )) {

            ReaderService service = new ReaderService();
            assertEquals("STUB", service.read());
            assertEquals(1, scope.constructed().size());
        }
    }
}
~~~

`mockConstruction` requires compatible inline mocking. It helps when legacy code cannot yet be refactored, though tests remain coupled to how the implementation calls `new`. Over time, constructor injection or factories produce more resilient tests without intercepting object creation.

## 10. Diagnosing Mockito / Byte Buddy / JDK Errors

| Error or Symptom | First Check | Resolution |
|---|---|---|
| JDK warns agent loaded dynamically | Mockito inline self-attaching | Configure `-javaagent` on the test JVM |
| Mockito self-attach warning | Tests lack startup instrumentation | Pass matching-version Mockito agent JAR |
| Could not initialize inline Byte Buddy mock maker | Instrumentation unavailable or init failed | Agent path, JDK policy, mock maker, stack trace |
| Could not self-attach to current VM | Attach disallowed or no attach provider | Startup `-javaagent` or switch mock strategy |
| Mockito cannot mock this class | Class/method/VM/mock maker limitation | Check `final`, native, module, maker |
| Unsupported class file major version | Byte Buddy/ASM/plugin too old or old JVM | Verify JDK and upgrade bytecode tooling |
| InaccessibleObjectException | JPMS strong encapsulation/reflection | Find module/package; adjust test/lib; open narrowly only if needed |
| NoClassDefFoundError: net.bytebuddy... | Missing dependency or classloader conflict | Inspect test runtime classpath |
| NoSuchMethodError in Mockito/Byte Buddy | Binary version mismatch | Inspect dependency resolution and BOMs |
| mockStatic already registered in current thread | Static mock scope not closed | try-with-resources, test cleanup |
| Tests pass, coverage disappears | Surefire `argLine` overwrote JaCoCo | Combine agents properly |
| Passes locally, fails in CI | Different JVM/fork/container attach rules | Compare launcher args, vendor/build |
| Agent JAR invalid/missing Premain-Class | Wrong JAR/version/manifest | Verify resolved artifact |

### 10.1. Bytecode Versions and Byte Buddy

Class-file major versions advance with each JDK:

| Java | Class-file major |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |

Byte Buddy must understand the class-file format it reads and instruments. If Byte Buddy is too old for the target JDK, you may see messages like:

~~~text
Java 21 (65) is not supported by the current version of Byte Buddy
~~~

This differs from `UnsupportedClassVersionError` thrown when an older JVM loads newer class files. One is **bytecode tooling not supporting the format**; the other is **the runtime JVM not supporting the format**.

When this happens:
1. Check the exact resolved Mockito and Byte Buddy versions.
2. Check the test process JDK, not just the build daemon.
3. Read Mockito/Byte Buddy release notes for new JDK/class-file support.
4. Pin a supported combination.
5. Never add experimental flags bypassing bytecode validation without assessing risk.

### 10.2. JPMS and Reflective Access

If tests run on the **module path**, Mockito or mocked libraries can hit module access restrictions. Distinguish:
- Module does not read another module: readability.
- Package not exported: public API access.
- Package not opened: deep reflection.
- Instrumentation unavailable: agent/JVM issue.

`--add-opens` does not fix self-attach failures; `-javaagent` does not make every module/package accessible automatically. Before adding flags, read the stack trace to pinpoint the exact module, package, and operation. For packages in modules you own, consider adding appropriate `opens` directives or adjusting test design. Avoid opening huge swaths of internal JDK packages solely to turn tests green.

### 10.3. Mockito Extensions and Dependency Conflicts

A project can pull in Mockito via:
- Direct `mockito-core`.
- Spring Boot test starters/BOMs.
- Test framework plugins.
- Transitive dependencies.
- Test resources declaring a MockMaker extension.

If `mockito-core` resolves to one version while `mockito-junit-jupiter` or Byte Buddy is forced to an incompatible version, linkage errors unrelated to JEP 451 can happen. Inspect the dependency tree to confirm final artifacts rather than reading only one version line in a build script.

## 11. Observing the Actual JVM Running Tests

### 11.1. Gradle

Diagnostic commands in a real project:

~~~bash
./gradlew --version
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency byte-buddy --configuration testRuntimeClasspath
~~~

These show the build tool and dependency graph; also inspect `Test.javaLauncher`, test fork JVM args, custom test suites, and IDE runners. **Gradle daemon JVM differs from the test JVM** when toolchains or forks are configured.

### 11.2. Maven

~~~bash
./mvnw -version
./mvnw dependency:tree -Dscope=test
~~~

Inspect Maven Surefire/Failsafe config, profiles, `pluginManagement`, and toolchains. Maven running on JDK 21 does not prove test forks run on JDK 21; if test forks use JDK 17, the agent must work on JDK 17.

### 11.3. Printing Test JVM Arguments for Diagnostics

~~~java
import java.lang.management.ManagementFactory;
import org.junit.jupiter.api.Test;

class TestJvmInfo {
    @Test
    void printRuntimeAndInputArgs() {
        System.out.println("java.runtime.version=" +
                System.getProperty("java.runtime.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println(
                ManagementFactory.getRuntimeMXBean().getInputArguments()
        );
    }
}
~~~

If the input arguments list lacks `-javaagent:...` on the test JVM, agent configuration did not reach the right process. Never print arguments to public logs if they contain secrets or sensitive system properties.

### 11.4. Testing Without Dynamic Attach

On JVMs supporting the corresponding HotSpot option, add to test forks:

~~~text
-XX:-EnableDynamicAgentLoading
~~~

If tests using the inline mock maker **lack a startup agent**, they can fail when trying to self-attach. Once `-javaagent` is configured properly, Mockito obtains the preconfigured `Instrumentation` without self-attaching.

This is a proactive migration check, not a requirement to set the flag in production. The flag may also impact profilers or diagnostic tools used in operations.

### 11.5. Avoid Workarounds Relying on Self-Attach

Older guides may suggest `-Djdk.attach.allowAttachSelf=true` or `-XX:+EnableDynamicAgentLoading`. They do not replace a startup agent, are not guaranteed across every container or vendor, and bypass JEP 451's integrity goal.

Never run containers in privileged mode merely so Byte Buddy can self-attach. Configure the agent explicitly, or reduce instrumentation needs via subclass mocking or test redesign.

## 12. Keeping Gradle/Maven Test Infrastructure Consistent

A Java project can spawn multiple processes:
 
~~~text
          Maven / Gradle launcher
                  |
          Plugin/configuration
                  |
        +---------+----------+
        |                    |
     Unit tests       Integration tests
       JVM A                JVM B
        |                    |
       Agent?               Agent?
        |                    |
     Mockito               Mockito
~~~

If you configure the agent only on `test`, an integration suite added by another plugin may still self-attach and emit warnings. The same applies to tests run directly in an IDE, CI JUnit launchers, or containers.

Inventory:
- Every task/process executing tests.
- Which JDK each uses.
- Which Mockito and MockMaker versions are active.
- Agent JAR/version and launcher options.
- Other agents such as JaCoCo, profilers, and tracing agents.
- Classpath/module path and instrumentation privileges.

Never infer from **a single passing test** that all test suites are configured properly.

## 13. Android, Native Images, and Restricted Environments

### 13.1. Android

Tests running on Android Runtime (ART) differ from HotSpot JVM unit tests. Mockito provides dedicated artifacts/mechanisms per version, such as `mockito-android`. Do not assume `-javaagent:mockito-core.jar` from Gradle JVM unit tests applies to on-device Android instrumented tests.

Check Android Gradle Plugin version, Android API level, build JDK, ART-compatible mock makers, and each test type separately.

### 13.2. Native Image / GraalVM

Native images and AOT have different constraints from JVMs supporting runtime instrumentation. Mockito/Byte Buddy working in JVM unit tests does not prove equivalent runtime instrumentation works in native images.

For native applications:
- Use JVM tests for logic verification.
- Use native-specific tests for native artifacts.
- Avoid dynamic class generation on production paths.
- Check reflection, class initialization, and framework AOT configuration.

Never bundle Mockito agents into native production images merely because unit tests use inline mocking.

### 13.3. Attach-Restricted Containers/CI

Containers may restrict PID namespaces, the Attach API, process spawning, capabilities, and filesystems. Self-attach can fail in CI even though a laptop on the exact same JDK version succeeds.

Startup `-javaagent` makes configuration explicit, yet still requires:
- The exact artifact present in the container filesystem.
- A JDK supporting Java agents.
- Permissions to read the JAR and valid JVM options.
- Pinned runtime image/vendor/architecture.
- Test tasks/runners passing options into the right process.

Do not widen container permissions unnecessarily merely to make self-attach succeed.

## 14. Reducing Instrumentation Reliance Through Test Design

In legacy code, static methods and hard-coded `new` calls often leave tests dependent on inline mocks. You can migrate gradually toward injection.

Hard-to-test code:

~~~java
public class OrderNotifier {
    public void notifyOrder(String orderId) {
        new HttpNotifier().send(orderId);
    }
}
~~~

Replace with an explicit contract:

~~~java
public interface Notifier {
    void send(String orderId);
}
~~~

~~~java
public final class OrderNotifier {
    private final Notifier notifier;

    public OrderNotifier(Notifier notifier) {
        this.notifier = notifier;
    }

    public void notifyOrder(String orderId) {
        notifier.send(orderId);
    }
}
~~~

Tests only mock the interface:

~~~java
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;

class OrderNotifierTest {
    @Test
    void delegatesToNotifier() {
        Notifier notifier = mock(Notifier.class);
        OrderNotifier service = new OrderNotifier(notifier);

        service.notifyOrder("ord-1");

        verify(notifier).send("ord-1");
    }
}
~~~

Benefits:
- Fewer static/constructor mocks needed.
- Tests depend on contracts instead of implementations.
- Easier refactoring or swapping HTTP clients when upgrading JDKs.
- Subclass/interface mocking often suffices.

However, do not rip out all inline mocking under tight migration deadlines and high refactoring costs. Inline mocking is a valid tool when explicitly configured and tested; balance test-infrastructure fixes against architectural changes.

## 15. Step-by-Step Mockito Migration Workflow When Upgrading JDKs

### Step 1: Lock Down the Runtime Matrix

Record separately:
- JDK running Maven/Gradle.
- JDK compiling sources and `--release` target.
- JDK for unit/integration tests.
- Production runtime JDK and lowest supported version.
- Versions of Mockito, Byte Buddy, JUnit, and coverage agents.

### Step 2: Inventory Mock Maker Usage

Search for static/constructor mocking and `MockMaker` config:

~~~bash
rg -n 'mockStatic|mockConstruction|MockedStatic|MockedConstruction' src/test
rg -n 'mockito-extensions|mock-maker-inline|mock-maker-subclass' .
~~~

This provides a preliminary scan and does not catch all `final`-class mocks or plugins/frameworks using Mockito internally.

### Step 3: Pick Mockito/Byte Buddy Compatible with the Target JDK

If tests still run on Java 8, do not pick Mockito 5 for that JVM. On newer JDKs, check Mockito release notes, Byte Buddy class-file version support, and dependency versions managed by BOMs/plugins.

### Step 4: Configure the Startup Agent

When inline Mockito is needed on JDK 21+:
1. Resolve the exact matching Mockito agent JAR version.
2. Pass `-javaagent` to the test JVM (Gradle `Test` or Surefire/Failsafe).
3. Preserve JaCoCo and other agent configurations.
4. Confirm IDEs, CI runners, and integration test runners are all covered.
5. Never enable it on production application JVMs without justification and approval.

### Step 5: Test with Dynamic Attach Disabled

In suitable environments, pass `-XX:-EnableDynamicAgentLoading` alongside the startup agent to ensure tests do not silently depend on self-attach. When errors appear, inspect JVM args and root causes before adding permission flags.

### Step 6: Exercise Key Test Categories

Cover:
- Standard interface/class mocks.
- Final class/method mocks.
- Static mocks with properly closed scopes.
- Constructor mocks.
- Parallel tests, test retries, and integration suites.
- Real module path / classpath with actual JPMS setups.

### Step 7: Keep Real-Behavior Tests

Passing mocked unit tests demonstrates isolated logic yet cannot verify HTTP/TLS, JDBC, dependency bytecode, and serialization on a new JDK. Use integration and contract tests against real dependencies to catch runtime breaking changes.

### Step 8: Document and Pin Configuration

Record Mockito/Byte Buddy versions, JDK vendor/build, agent artifact/path, launcher arguments, and mock maker. Maintain an update procedure when adding newer JDKs or upgrading test frameworks.

## 16. Common Misconceptions

- **"Every Mockito test needs a Java agent":** False; subclass/interface mocks normally do not need self-attach.
- **"Mockito 5 still uses subclass by default":** False; Mockito 5 switched inline to the default.
- **"Mockito 5 runs on Java 8 if `--release 8` is set":** False; Mockito 5's runtime requires Java 11+.
- **"JDK 21 already bans all dynamic agents":** JEP 451 initially warns; check target release policy.
- **"Setting `-XX:+EnableDynamicAgentLoading` fixes it":** That suppresses warnings or permits attach rather than setting an intentional startup agent.
- **"Having `mockito-core` on the classpath configures `-javaagent`":** Those are two separate steps.
- **"Adding the agent to the Gradle daemon passes it to Test JVMs":** Daemon and test JVMs/tasks can be separate processes.
- **"Setting a new `argLine` won't hurt JaCoCo":** It can overwrite the coverage agent.
- **"Old Byte Buddy versions still understand future class-file versions":** Always check release support.
- **"`--add-opens` fixes every Mockito failure":** It does not fix agent initialization or dependency conflicts.
- **"Static mocks auto-reset when a test ends":** Scopes must close cleanly; try-with-resources makes this explicit.
- **"Mocking a final class means tests verified the real API":** Mocks do not replace integration tests.
- **"Android/Native Image works just like HotSpot":** Each runtime imposes distinct constraints.
- **"Container privileges must be raised for self-attach":** Prefer startup agents or redesign tests instead.

## 17. Pre-Completion Migration Checklist

- [ ] Recorded actual build, compiler, test, and runtime JDKs.
- [ ] Identified Mockito core/extension, Byte Buddy, JUnit, and coverage agent versions.
- [ ] Confirmed which mock maker is active (subclass vs. inline).
- [ ] Found tests mocking final types, static methods, or constructors.
- [ ] Confirmed Mockito version supports the lowest test JVM JDK.
- [ ] Confirmed Byte Buddy supports target JDK bytecode.
- [ ] When inline is needed on JDK 21+, configured `-javaagent` on the exact test JVMs.
- [ ] Resolved Mockito agent JAR cleanly as a matching-version artifact.
- [ ] Gradle `Test`/custom suites or Maven Surefire/Failsafe receive required JVM args.
- [ ] JaCoCo/profiler configs are not overwritten.
- [ ] Tested disabling dynamic attach on supporting JDKs to uncover hidden self-attach reliance.
- [ ] Distinguished JPMS access errors from agent initialization errors.
- [ ] Closed all static/constructor mock scopes cleanly.
- [ ] Executed both unit and integration tests on the new JDK.
- [ ] Confirmed the test agent does not enter production runtimes unintentionally.
- [ ] Documented owner, versions, runners, JDK vendor/build, and upgrade path.

## 18. References

- [Mockito API — agent configuration guide for inline mocking on Java 21+](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html).
- [Mockito source Javadoc on MockMaker and -javaagent](https://github.com/mockito/mockito/blob/main/mockito-core/src/main/java/org/mockito/Mockito.java).
- [Mockito 5 release notes — Java 11 baseline and default inline](https://github.com/mockito/mockito/wiki/Draft-Mockito-5-release-notes).
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451).
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html).
- [Gradle Java build caching and CommandLineArgumentProvider](https://docs.gradle.org/current/userguide/caching_java_projects.html).
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/).
- [Maven Dependency Plugin properties goal](https://maven.apache.org/plugins/maven-dependency-plugin/properties-mojo.html).

Consult documentation for your **exact versions** of Mockito, Gradle/Maven, and JDK vendor at implementation time. Examples from a recent release may not apply verbatim to older build plugins or runtimes.

## 19. Conclusion

Mockito creates mocks via subclass generation or **inline bytecode instrumentation**. The inline mock maker—default starting in Mockito 5—unlocks mocking final classes/methods, static methods, and constructors, making the **Java agent** an essential part of test infrastructure in many projects.

Starting in JDK 21, **JEP 451 warns when agents are loaded dynamically**. The right migration path is pinning a Mockito–Byte Buddy combination supporting your target JDK, passing **`-javaagent` explicitly to test JVMs**, and verifying across Gradle/Maven, CI, IDEs, and relevant test forks. Do not merely silence warnings with dynamic-attach flags, never confuse the build JVM with test JVMs, and never treat Mockito unit tests as sole proof of runtime compatibility. Where practical, pair interfaces/dependency injection with integration tests to keep test suites resilient across future JDK upgrades.
