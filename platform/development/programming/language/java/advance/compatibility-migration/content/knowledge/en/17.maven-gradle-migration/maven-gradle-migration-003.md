# Maven Toolchains and selecting a JDK for each plugin group

When upgrading the JDK or publishing a library supporting multiple Java versions, asking "which Java version does this project use?" is not enough to verify compatibility. A single Maven project can **run Maven on JDK 21**, **compile source code with JDK 21 while passing `--release 17`**, **run unit tests on JDK 17**, **run integration tests on JDK 21**, and **generate Javadoc using JDK 21**. Reading only `JAVA_HOME` or `mvn -version` can mislead a team about which JDK each stage actually uses.

**Maven Toolchains** provides a mechanism for supported Maven plugins to select a JDK independently of the JVM that launched Maven. Alongside the **default toolchain** placed in the session by Maven Toolchains Plugin, several plugins such as Maven Compiler, Surefire, Failsafe, and Javadoc also expose a `jdkToolchain` parameter to choose a separate JDK.

For Java Advance Compatibility Migration, the goal is not merely getting a build to pass. You must ensure the compiler, bytecode target, test suites, and other plugins run on the exact declared JDK, and that this result is reproducible across developer machines and CI.

## 1. Four JDK roles to distinguish

| Role | What does it execute? | How to verify |
|---|---|---|
| **Maven JVM** | Maven core and Maven plugin goals/mojos running inside the Maven process | `mvn -version` |
| **Compiler JDK** | `javac` selected by Maven Compiler Plugin to compile main/test sources | Compiler Plugin logs, toolchain info |
| **Test JVM** | JVM used by Surefire/Failsafe to run unit/integration tests | Fork logs and `java.version` inside tests |
| **Other JDK tools** | `javadoc`, `jdeps`, `jlink`, `jarsigner`, and external tools when supported by plugins | Individual plugin/goal logs |

Diagram of a possible build:

~~~text
JAVA_HOME -> JDK 21
        |
        v
Maven JVM 21
        |
        +-- Compiler -> javac JDK 21, --release 17
        |
        +-- Surefire -> JVM 17 (unit tests)
        |
        +-- Failsafe -> JVM 21 (integration tests)
        |
        +-- Javadoc -> javadoc JDK 21
        |
        +-- Plugin without toolchain support
                       |
                       v
                May use Maven JVM 21
~~~

### 1.1. `mvn -version` does not answer the whole question

The command:

~~~bash
mvn -version
~~~

shows the JDK running **Maven**. Once a compiler/test plugin selects a different toolchain, this output is no longer proof of the `javac` JDK or the test JVM.

The reverse matters too: a JDK 21 toolchain **does not automatically make an older Maven or plugin version compatible with JVM 21**. Components executing inside the Maven JVM remain bound by that Maven/plugin runtime requirement.

### 1.2. Toolchains do not automatically control every child JVM

A plugin may fork a Java process, invoke a native executable, launch a container, or execute logic right inside the Maven JVM. Toolchains affect only tasks that integrate with the toolchain mechanism. For example, Surefire can fork a JVM using `jdkToolchain`, yet a Java service started by integration tests via a Docker image uses the image's JDK rather than automatically switching with Failsafe.

Therefore, when building a JDK matrix, ask: **which process runs the compiler/test/plugin, what spawns that process, and by what mechanism is its JDK chosen?**

## 2. How do Maven Toolchains work?

A toolchain describes a tool suite installed on the build machine — for instance JDK 17 or JDK 21 along with its installation path and metadata. Maven Toolchains Plugin matches a JDK satisfying requirements, places that selection into the **Maven session**, and toolchain-aware plugins can look up that selection.

~~~text
Machine / CI runner:
  JDK 17 ----+
             |
  JDK 21 ----+--> toolchains.xml or JDK discovery
                             |
                             v
                    Maven Toolchains Plugin
                             |
                             v
                      Default toolchain
                             |
                 +-----------+-----------+
                 |           |           |
               Compiler    Surefire     Javadoc
                 |           |           |
                 +-- May have separate jdkToolchain --+
~~~

Maven does not swap out its own running JVM between goals. Toolchains let plugins use **another tool/JVM** when the plugin supports doing so.

### 2.1. Two common configuration locations

- **`~/.m2/toolchains.xml`**: describes JDKs installed on the machine and their `jdkHome` paths.
- **`pom.xml`**: defines the default JDK requirement and overrides on specific plugins.

With Maven 3, `~/.m2/toolchains.xml` is commonly used. Since Maven 3.3.1, the `-t` / `--toolchains` option specifies a file at another location. If CI runners use custom install paths, generate the toolchain file per runner rather than committing personal paths into the POM.

### 2.2. Advantages over hardcoding an executable

Hardcoding `/home/developer/jdk-17/bin/javac` in the POM makes the build fragile on Windows or other runners. Toolchains let the POM request only version/vendor while the environment supplies the real path.

Even so, **toolchains select by metadata** — they do not install JDKs, fetch dependencies, or rewrite source code to match a JDK.

## 3. Declaring JDK 17 and JDK 21 in `toolchains.xml`

Example `~/.m2/toolchains.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>

    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Paths are illustrative; replace them with actual JDK install locations on the machine. The `jdkHome` directory must hold a valid JDK including the corresponding tools, not an empty directory or a JRE lacking a compiler.

### 3.1. Metadata must accurately describe the real JDK

`<version>` and `<vendor>` inside `<provides>` are matching criteria. Setting `version=21` while pointing to JDK 17 does not turn it into JDK 21; it is a misconfiguration.

You can verify the actual installation:

~~~bash
/opt/jdks/temurin-17/bin/java -version
/opt/jdks/temurin-17/bin/javac -version
/opt/jdks/temurin-21/bin/java -version
/opt/jdks/temurin-21/bin/javac -version
~~~

When reproducing JDK migration bugs, record the patch version and build number too, because security updates or bug fixes can change behavior.

### 3.2. Common pitfall: `17` does not match `17.0.20`

Per Maven guidance, in the traditional toolchain matcher, a single version requirement matches against corresponding metadata. If `toolchains.xml` provides `17.0.20` while the POM requests `17`, do not assume they automatically match. You can use an appropriate version range such as `[17,18)` when allowing multiple JDK 17.x releases.

Discovery-generated metadata may record full versions, whereas hand-written files often record feature versions. Vendor criteria must also match provider names in metadata; different file-generation tools may use different names.

**Principle:** inspect actual metadata before writing selection criteria; do not assume Maven treats two version/vendor formats as equivalent.

## 4. Selecting a default JDK toolchain

Use the `toolchain` goal of Maven Toolchains Plugin in `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>toolchain</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <toolchains>
                    <jdk>
                        <version>21</version>
                        <vendor>temurin</vendor>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The goal selects a matching JDK 21 from `toolchains.xml` and places it in the session for supporting plugins to use.

Understand the limit: this sets a **default toolchain**, not a command changing `JAVA_HOME` or the Maven JVM. If Compiler Plugin or Surefire configures its own `jdkToolchain`, that dedicated configuration overrides the default selection for its task.

### 4.1. Why can a build report no matching toolchain found?

Common causes:

- `toolchains.xml` is not where Maven reads from.
- No matching `jdk` type entry exists.
- `version`/`vendor` does not satisfy POM criteria.
- `jdkHome` does not exist or points to the wrong path.
- The CI runner lacks the requested JDK installed.
- Toolchains Plugin was not bound/executed in the lifecycle as expected.

This is a tool-selection failure. Randomly changing `JAVA_HOME` is not the right diagnosis if the toolchain matcher still finds no entry.

## 5. JDK discovery in newer Maven Toolchains Plugin

Starting in **Maven Toolchains Plugin 3.2.0**, the `select-jdk-toolchain` goal supports discovering JDKs installed in common locations and via environment variables. You can display discovered results with:

~~~bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
~~~

Example selecting a JDK in the 21 line:

~~~xml
<properties>
    <toolchain.jdk.version>[21,22)</toolchain.jdk.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>select-jdk-toolchain</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

This mechanism can choose between explicitly declared JDKs and discovered JDKs; a hand-written `toolchains.xml` is not strictly mandatory if the plugin finds a matching JDK.

### 5.1. Discovery is not auto-installation

If the runner does not have the JDK installed or places it where heuristics do not search, the plugin will not provision a new JDK. For reproducible CI, prepare consistent images/runners or discovery configuration.

When multiple JDKs match, the plugin applies preference criteria such as LTS, current JDK, environment source, version, or vendor. Avoid overly broad criteria that pick unexpectedly different JDKs between local machines and CI.

### 5.2. When to use which mechanism?

| Approach | Best suited for | Notes |
|---|---|---|
| `toolchains.xml` + `toolchain` | Standardized runners wanting explicit JDK path mappings | Keep metadata, JDK installs, and paths aligned |
| `select-jdk-toolchain` | Leveraging automatic JDK discovery | Verify discovered JDKs and selection criteria |
| Plugin-level `jdkToolchain` | Distinct plugin groups needing different JDKs | Applies only to plugins supporting the parameter |
| Separate `executable`/`jvm` config | Legacy plugins or tools without toolchain integration | Less portable; requires path management and verification |

Do not activate two competing default-selection mechanisms in the same build without clarifying precedence and intent.

## 6. Maven Compiler Plugin: choosing a dedicated `javac`

Compiler Plugin clearly illustrates the difference between **compiler JDK** and **Java release target**.

### 6.1. Using a JDK 21 toolchain while compiling for Java 17

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

If the default toolchain selects JDK 21, Compiler Plugin can invoke `javac` 21 and pass `--release 17`. The release flag constrains language level, class file version, and Java SE APIs to Java 17.

However, `release=17` **does not select a JDK 17 compiler**, does not restrict third-party dependency APIs, and does not prove tests pass on Java 17.

### 6.2. Overriding the compiler with `jdkToolchain`

Maven Compiler Plugin **3.6.0+** supports dedicated JDK selection (with Maven 3.3.1 or later):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
            <vendor>temurin</vendor>
        </jdkToolchain>
        <release>17</release>
    </configuration>
</plugin>
~~~

Even when the session default toolchain is 21, the compiler can pick JDK 17 matching its own constraint. This is helpful when verifying source compiles under the exact minimum JDK.

### 6.3. Distinguishing `source`/`target` from `release`

~~~xml
<configuration>
    <source>17</source>
    <target>17</target>
</configuration>
~~~

is not fully equivalent to `release=17` when the actual compiler is a newer JDK. Setting only `target` can emit level-17 class files while accidentally calling Java SE APIs introduced in JDK 21. Running on 17 can then throw linkage errors.

When targeting Java 17, prefer `release=17` where supported by the compiler, verify class file versions, and run tests on a 17 runtime.

### 6.4. Main sources and test sources with separate targets

A project may keep main code on Java 17 while using Java 21 APIs in test code running on Java 21. In that case, distinguish main `release` from test `testRelease` and ensure a suitable compiler:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <jdkToolchain>
            <version>21</version>
        </jdkToolchain>
        <release>17</release>
        <testRelease>21</testRelease>
    </configuration>
</plugin>
~~~

With `testRelease=21`, those test classes cannot run on JVM 17. When both runtimes must be tested, split executions, source sets, or CI jobs depending on project layout.

Annotation processors and code generators also require attention: processors run inside the compiler environment while the final artifact may target an older Java release. Do not infer processor JDK requirements from `release` alone.

## 7. Maven Surefire Plugin: JDK for unit tests

Surefire typically executes unit tests in the `test` phase. With a Toolchains-capable version, a separate JDK can be selected for the test runner:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.5</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
            <vendor>temurin</vendor>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

With valid configuration and toolchain, the JVM forked by Surefire can be JDK 17 even while the Maven JVM runs on JDK 21.

### 7.1. `jdkToolchain` vs. `jvm`

Surefire also has a `jvm` parameter taking a direct path to a Java executable. `jdkToolchain` selects by version/vendor instead of hardcoding paths. Avoid combining both without understanding precedence and verifying actual output in your Surefire version.

### 7.2. Check fork configuration

Test toolchains apply when Surefire spawns a test JVM. If forking is disabled, tests execute inside the Maven JVM, or a legacy provider behaves differently, results may not match expectations. Check `forkCount`, `reuseForks`, provider config, and debug logs.

### 7.3. Test runners have minimum runtime requirements

Surefire's `ForkedBooter` or JUnit provider may be compiled for a minimum Java version. A test JDK that is too old can fail with `UnsupportedClassVersionError` before running business tests. Therefore verify the plugin and framework support matrix, not just toolchain metadata.

## 8. Maven Failsafe Plugin: JDK for integration tests

Failsafe typically runs in the `integration-test` and `verify` phases and can target a different JDK from Surefire.

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.5</version>
    <configuration>
        <jdkToolchain>
            <version>21</version>
            <vendor>temurin</vendor>
        </jdkToolchain>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

An illustrative layout:

~~~text
Maven JVM:           JDK 21
Compiler:            javac 21, --release 17
Surefire:            JDK 17
Failsafe:            JDK 21
~~~

Note that `mvn test` is not equivalent to `mvn verify`: the former typically does not execute Failsafe `integration-test`/`verify` goals. To verify both suites, invoke the appropriate lifecycle phase.

### 8.1. The test JVM is not necessarily the integrated application's JVM

If integration tests use Testcontainers, an external microservice, a script-spawned Java process, or an independent application server, Failsafe's `jdkToolchain` usually governs only **the test runner JVM**. Services inside containers or child processes may run different JDKs.

Multi-service test setups should record each service's JDK rather than letting the test runner's `java.version` stand for everything.

## 9. Javadoc and plugins invoking JDK tools

Maven Javadoc Plugin supports its own `jdkToolchain`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <configuration>
        <jdkToolchain>
            <version>21</version>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

When newer Java modules use Javadoc tags, APIs, or language features tied to a newer JDK, choosing the right `javadoc` ensures consistent doc generation. Doing so does not mean main class files were compiled with JDK 21.

### 9.1. Plugin groups often needing extra verification

| Plugin group | Example | Toolchain role |
|---|---|---|
| Dependency analysis | `maven-jdeps-plugin` | Chooses JDK tool to inspect bytecode/modules when goal supports it |
| Deprecated API checks | `maven-jdeprscan-plugin` | Chooses compatible `jdeprscan` |
| Runtime image builders | `maven-jlink-plugin`, `maven-jmod-plugin` | Uses matching module tools |
| Artifact signing | `maven-jarsigner-plugin` | Selects `jarsigner` from matching JDK |
| JAR packaging | `maven-jar-plugin` | Some versions use toolchain for `Build-Jdk-Spec`, not all packaging steps |
| Code analysis | `maven-pmd-plugin` or third-party plugins | Check per version/goal |
| External commands | `exec-maven-plugin` `exec` goal | Depends on config and toolchain support |

**Do not infer that any plugin in this table automatically supports a standalone `jdkToolchain`.** A plugin may only use the default toolchain, support only specific goals, or lack support in older versions.

### 9.2. Plugins executing directly inside the Maven JVM

Some plugins run code directly inside the Maven process without forking a JVM. Toolchains do not switch the VM running that Mojo. For instance, the `exec:java` goal may run classes inside the Maven JVM; never assume it uses the Maven Toolchains Plugin JDK as a separate child JVM.

If a plugin spawns Java processes or Docker containers itself, inspect that specific plugin/process runtime-selection mechanism.

## 10. Combined POM: compiling Java 17, testing on 17 and 21

Suppose a Java library has a minimum runtime of Java 17, yet the team builds with JDK 21 and checks runtimes 17 and 21. The POM can set JDK 21 as default toolchain, target Java 17 on the compiler, JDK 17 on Surefire, and JDK 21 on Failsafe:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jdk-compatibility-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <goals><goal>toolchain</goal></goals>
                    </execution>
                </executions>
                <configuration>
                    <toolchains>
                        <jdk>
                            <version>21</version>
                            <vendor>temurin</vendor>
                        </jdk>
                    </toolchains>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration><release>17</release></configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.5</version>
                <configuration>
                    <jdkToolchain>
                        <version>17</version>
                        <vendor>temurin</vendor>
                    </jdkToolchain>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.5</version>
                <configuration>
                    <jdkToolchain>
                        <version>21</version>
                        <vendor>temurin</vendor>
                    </jdkToolchain>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <jdkToolchain>
                        <version>21</version>
                    </jdkToolchain>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The example requires a `toolchains.xml` with JDKs 17 and 21, appropriate test dependencies (such as JUnit), and integration tests recognized by Failsafe. Setting `jdkToolchain` on Javadoc does not automatically run Javadoc generation if that goal is not bound to the lifecycle.

### 10.1. How tasks choose JDKs in the example

| Task | Expected JDK | Reason |
|---|---|---|
| Maven JVM | Per launcher/`JAVA_HOME` | Toolchains do not change Maven JVM |
| `compile`/`testCompile` | `javac` JDK 21 | Compiler uses default toolchain |
| Bytecode/API target | Java 17 | `--release 17` |
| Surefire unit tests | JVM JDK 17 | Dedicated toolchain override |
| Failsafe integration tests | JVM JDK 21 | Dedicated toolchain override |
| Javadoc | JDK 21 tools | Dedicated override |
| Non-toolchain-aware plugin | Plugin-dependent, may use Maven JVM | Must verify |

This configuration does not prove production also runs Java 17 or 21. It is a build/test configuration; production images and startup runtimes must be managed separately.

### 10.2. Why a missing JDK 17 should fail CI

If a project claims Java 17 support, lacking JDK 17 in test jobs leaves an unverified gap. Do not automatically switch tests to 21 just to turn the pipeline green while still advertising 17 support. Provision toolchain 17 or publicly revise the support policy.

## 11. Running the same test suite on multiple JDKs

A single Maven lifecycle typically selects one Surefire test JVM per invocation. To confirm a library works on Java 17 and Java 21, use **two CI jobs** with matching profiles or toolchain configs.

Example of two profiles:

~~~xml
<profiles>
    <profile>
        <id>test-jdk17</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <configuration>
                        <jdkToolchain>
                            <version>17</version>
                        </jdkToolchain>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>

    <profile>
        <id>test-jdk21</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <configuration>
                        <jdkToolchain>
                            <version>21</version>
                        </jdkToolchain>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Use `pluginManagement` or shared plugin config to keep versions consistent. Avoid setting another fixed `jdkToolchain` in shared configuration without verifying how Maven merges or overrides profile configurations.

Run each job independently:

~~~bash
mvn -Ptest-jdk17 clean test
mvn -Ptest-jdk21 clean test
~~~

### 11.1. Testing the exact same artifact proves more than two separate builds

When the goal is confirming runtime compatibility, build a single artifact with `--release 17` and run tests against that exact artifact on both JDK 17 and 21:

~~~text
Compile once (javac 21 --release 17)
                 |
                 v
             Artifact A
               /    \
              v      v
       Test JDK 17   Test JDK 21
~~~

If each CI job rebuilds using different dependencies/profiles/compilers, behavioral differences may stem from **different artifacts** rather than runtime differences alone. When needed, store artifact hashes and compiler info for verification.

### 11.2. Do not let profiles silently alter test scope

A Java 17 profile might also alter dependencies, includes/excludes, Java release, or system properties. That can easily make tests appear "green" simply by skipping the very test cases needed. Record exact profiles and test inventories for each job.

## 12. Multi-module Maven: not every module shares one target

A reactor may look like:

~~~text
parent
  +-- api-contract-java17
  +-- service-java21
  +-- integration-tests
  +-- docs
~~~

- `api-contract-java17` must publish classes/APIs at level 17.
- `service-java21` can use Java 21 APIs.
- `integration-tests` needs the target service's JDK environment.
- `docs` can pick Javadoc 21.

In the parent POM, pin plugin versions and sensible defaults. Child modules should override only when clearly required.

### 12.1. Distinguishing `pluginManagement` from `plugins`

`pluginManagement` manages shared config/versions inherited when a plugin is activated; listing a plugin there does not execute all its goals automatically. Inspect lifecycle bindings and `build/plugins` when a toolchain config appears present yet has no effect.

### 12.2. Watch dependency direction between 17 and 21 modules

A module intended to run on Java 17 must not depend at runtime on code compiled exclusively to Java 21 class files. Conversely, a Java 21 module can use a library compiled for level 17 if APIs/logic match.

Setting `--release 17` on the first module cannot make a dependency JAR built at level 21 backward-compatible. Verify class file versions and runtime requirements of transitively used dependencies.

### 12.3. Annotation processors and generated sources

An annotation processor may require a newer JDK than the artifact's minimum runtime. For example, a processor running under javac 21 generating sources compiled with `--release 17` can be valid.

Conversely, choosing javac 17 just to match runtime 17 may break a processor requiring JDK 21. Separate the compiler/processor JDK from the artifact's target API/bytecode, and verify generated code does not call APIs beyond the target.

## 13. Verifying rather than just reading the POM

### 13.1. Record the Maven JVM

~~~bash
mvn -version
~~~

Record Maven version, Java version, vendor, and Java home.

### 13.2. Check JDKs discovered by Toolchains Plugin

~~~bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
~~~

If using a manual file, compare output against `toolchains.xml` entries and JDK paths on the runner.

### 13.3. Enable Maven debug logging

~~~bash
mvn -X clean verify
~~~

Look specifically for:

- Which JDK was picked as the default toolchain?
- Which toolchain did the compiler fork/invoke `javac` from?
- Which JVM did Surefire and Failsafe launch?
- Which executables did Javadoc, jdeps, or signing tools use?
- Did a plugin run directly inside the Maven JVM?

Do not assume an identical log string across every plugin version.

### 13.4. Print the JDK inside tests

JUnit Jupiter example:

~~~java
import org.junit.jupiter.api.Test;

class TestRuntimeInfo {
    @Test
    void showJavaRuntime() {
        System.out.println(
            "java.version=" + System.getProperty("java.version"));
        System.out.println(
            "java.vendor=" + System.getProperty("java.vendor"));
        System.out.println(
            "java.home=" + System.getProperty("java.home"));
    }
}
~~~

If the test runner prints Java 21 when `jdkToolchain` requested 17, inspect effective POM, Surefire fork settings, and runtime selection before concluding tests verified Java 17.

### 13.5. Check class file version with `javap`

~~~bash
javap -verbose -classpath target/classes com.example.App
~~~

Common levels:

| Java | Class file major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

`major version: 61` indicates Java 17 class files, yet does not prove external dependencies support runtime 17 or that tests actually ran on it.

### 13.6. Inspect effective POM and active profiles

~~~bash
mvn help:effective-pom
mvn help:active-profiles
~~~

In projects with complex parent POMs and profiles, this shows the resolved configuration. When a plugin picks the wrong JDK, trace what was inherited or overridden rather than staring only at a snippet in a child module.

## 14. Common errors and how to isolate them

| Symptom | Possible causes | First check |
|---|---|---|
| No matching toolchain found | JDK not installed, version/vendor metadata mismatch | `toolchains.xml` and discovery |
| Maven fails on newer JDK | Maven/plugin runtime unsupported | `mvn -version` and compatibility matrix |
| `UnsupportedClassVersionError` in `ForkedBooter` | Test JVM too old for test runner/provider | Surefire version and forked JVM |
| `UnsupportedClassVersionError` in app classes | Bytecode target newer than test JVM | `--release`, `javap`, test runtime |
| Tests run on Maven's JDK | Surefire did not pick expected toolchain or did not fork | Effective POM, debug logs, `forkCount` |
| Compile passes, runtime throws `NoSuchMethodError` | Newer API used on older runtime or dependency mismatch | `--release` and dependency tree |
| Javadoc uses wrong JDK | Toolchain override ineffective or plugin lacks support | Javadoc Plugin config/version |
| Codegen plugin uses wrong JDK | Plugin runs in Maven JVM or has separate executable | Plugin goal docs and logs |
| Passes locally, fails in CI | Different JDK inventory, wrong metadata | `jdkHome`, vendor, full version |
| Configured in parent, ignored by module | Plugin inactive or overridden by profile/child | Effective POM |
| Surefire 17 yet IT service is 21 | Test runner and container runtimes differ | Process/container `java.version` |

### 14.1. Toolchains cannot bypass a Maven plugin's own runtime requirement

If a plugin is compiled for Java 21 while the Maven JVM is 17, the plugin may fail to load. A JDK 21 compiler toolchain will not resolve that error because the **plugin Mojo** itself executes inside the Maven JVM. Choose a compatible Maven runtime or compatible plugin version instead.

### 14.2. Do not fix class-file errors merely by swapping `JAVA_HOME`

If Maven compiles with JDK 21 and `release=21` while Surefire's test JVM is JDK 17, `UnsupportedClassVersionError` is expected. Align the fix with the contract: either build/test classes for 17, or use a 21 test JVM if 21 is the supported runtime.

### 14.3. Avoid conflicting `jdkToolchain` and `jvm` configs

Some plugins accept multiple ways to specify a JVM. Mixing manual paths, default toolchains, and plugin-specific toolchains can produce different results from what a reader of the POM expects. Use one clear mechanism per task, or document precedence and verify logs.

## 15. Adoption workflow for Java migration projects

### Step 1: Build a version requirements table

Example:

| Component | JDK requirement | Goal |
|---|---|---|
| Maven core + plugin mojos | JDK 21 | Match build tool/plugin versions |
| Compiler | JDK 21 + `--release 17` | Java 17-compatible artifact |
| Unit tests | JDK 17 and 21 | Compare runtime behavior |
| Integration tests | JDK 21 | Verify newer runtime environment |
| Javadoc/API tools | JDK 21 | Support modern tools/modules |

Base the matrix on product policy rather than applying one setup mechanically across every repository.

### Step 2: Standardize build machines and CI

Install required JDKs from trusted sources, record version/build/vendor, and configure toolchains. Maintain a security patch update process. Avoid storing personal paths in shared parent POMs.

### Step 3: Set a default toolchain

Use `toolchain` and `toolchains.xml`, or `select-jdk-toolchain` with clear criteria. Verify the matcher actually finds the intended JDK.

### Step 4: Override per plugin group systematically

Compiler, Surefire, Failsafe, and Javadoc may require different JDKs. For other plugins, consult documentation on whether they are toolchain-aware, which goals apply, and whether they accept a dedicated `jdkToolchain` parameter.

### Step 5: Control targets and dependencies

Set `--release` when targeting a runtime older than the compiler, inspect class file versions, and audit third-party dependencies. Prevent Java-21-only libraries from slipping into an artifact advertised as supporting 17.

### Step 6: Execute tests per the matrix

Use clear CI jobs/profiles to run unit and integration tests on every supported runtime. When comparing runtime behavior, prefer testing **the exact same artifact** across JDKs.

### Step 7: Archive evidence

Record Maven version, Maven JVM, compiler toolchain, Surefire/Failsafe runtimes, artifact hash, active profiles, and test results. Any environment-skew issue should be reproducible from these records.

## 16. Common misconceptions

**"`mvn -version` shows Java 21, so tests are running on 21."** False. Surefire/Failsafe can fork a different JVM.

**"Selecting toolchain 17 guarantees Java 17 compatibility."** False. APIs/bytecode, dependencies, and runtime behavior still need verification.

**"`release=17` requires javac 17."** False. Newer `javac` releases can compile for older supported release targets.

**"Maven Toolchains switches the JVM running Maven."** False. The Maven JVM is chosen when the Maven command starts.

**"Every plugin uses the default toolchain."** False. Only supporting plugins/goals without overrides use that selection.

**"`jdkToolchain` on Compiler Plugin switches Surefire's JDK."** False. Compiler and test plugins can choose independently.

**"`mvn test` runs all integration tests."** False if the project binds Failsafe to `integration-test`/`verify`.

**"JDK discovery installs missing JDKs."** False. It discovers already-installed or provisioned JDKs.

**"`17` always matches `17.0.x`."** Not necessarily in the traditional matcher; understand metadata and version ranges.

**"A JDK 21 test JVM means the server inside Docker uses 21 too."** False. Process and container runtimes are independent.

**"A toolchain-aware plugin executes plugin code inside the toolchain JDK."** Not always: the Mojo itself may still execute inside the Maven JVM.

## 17. Checklist before standardizing multi-JDK builds

- [ ] Distinguished Maven JVM, compiler JDK, test JVM, and JDK tools.
- [ ] Recorded Maven/plugin versions and their runtime requirements.
- [ ] Created valid `toolchains.xml` or configured JDK discovery.
- [ ] Verified `jdkHome`, vendor, version, and matching criteria.
- [ ] Selected the default toolchain explicitly.
- [ ] Checked Compiler Plugin `jdkToolchain` if an override is needed.
- [ ] Configured `--release` matching the minimum supported runtime.
- [ ] Verified test classes and dependencies do not exceed the target runtime.
- [ ] Configured Surefire and Failsafe with the right JDKs.
- [ ] Distinguished test runner JVM from service/container JVMs.
- [ ] Verified toolchain support for Javadoc/`jdeps`/`jlink` and other plugins.
- [ ] Inspected active profiles, effective POM, and plugin execution configs.
- [ ] Confirmed JDK versions in debug logs and inside test code.
- [ ] Checked artifact class file major versions.
- [ ] Executed tests on both the minimum runtime and the target runtime.
- [ ] Recorded logs, toolchain identities, and artifact hashes in CI.

## 18. Apache Maven reference documentation

- [Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains): toolchains model, `toolchains.xml`, default toolchains, and per-plugin JDK selection.
- [Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): `toolchain` and `select-jdk-toolchain` goals.
- [JDK Discovery Mechanism](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html): JDK discovery, version/vendor handling, and selection criteria.
- [Maven Compiler Plugin – Compiling Sources Using A Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html): `jdkToolchain` and compiling with a JDK different from the Maven runtime.
- [Maven Surefire – Using Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html): running test JVMs with toolchains.
- [Maven Failsafe – Using Toolchains](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/toolchains.html): integration test JVMs.
- [Maven Javadoc Plugin](https://maven.apache.org/plugins/maven-javadoc-plugin/javadoc-mojo.html): `jdkToolchain` parameter.

Plugin versions in examples are illustrative versions with corresponding documentation. When integrating into a real project, check the support matrix and configuration of the exact Maven/plugin versions pinned.

## 19. Conclusion

Maven Toolchains lets supported Maven plugins select a JDK **without changing the JVM running Maven**. Maven Toolchains Plugin can establish a default JDK; Compiler, Surefire, Failsafe, and Javadoc can select separate JDKs via `jdkToolchain` in supported versions. At the same time, `--release` governs language level, standard APIs, and compiled bytecode, while the test runtime JDK governs where actual behavior is verified.

For Java Advance Compatibility Migration, what matters most is **not inferring everything from `JAVA_HOME` or a single POM line**. Build a compiler–test–plugin matrix, configure JDK toolchains reproducibly by version and vendor, run the proper CI jobs, verify runtimes via logs and `java.version`, and archive artifact evidence. Only then does the team have proof that code has been compiled and tested on the actually supported JDKs.