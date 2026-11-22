# Maven Toolchain: Managing JDKs for the Build Process

Maven Toolchains allow a project to select an appropriate JDK or build tool without forcing Maven itself to run on that JDK. As a result, Maven can run on JDK 21 while using JDK 17 to compile sources, run unit tests, generate Javadoc, or sign artifacts if the corresponding plugins are toolchain-aware.

A toolchain decouples project requirement configuration from installation paths on each machine. The POM describes the required JDK type and version/vendor; the `toolchains.xml` file on the build machine maps those criteria to the actual JDK directory. This article uses Maven 3.6.3 or later, Maven Toolchains Plugin 3.3.0, and JDK 17 as an example.

## 1. What Is a Maven Toolchain?

A toolchain is a configuration object that describes a tool that can be used by Maven plugins. For a JDK toolchain, the most important pieces of information are:

- Toolchain type: jdk.
- Identifying attributes: version, vendor, or other metadata.
- JDK installation root directory: jdkHome.

The Maven Toolchains Plugin reads the toolchains configured on the build machine, matches them against the requirements in the POM, and places the selected toolchain into the Maven build context. Toolchain-aware plugins can then retrieve the selected JDK to execute their work.

For example, a project requires JDK 17. A developer's machine has both JDK 17 and JDK 21; CI may also have multiple JDKs installed. The POM only requests JDK 17, while each machine declares its own JDK 17 path in its local `toolchains.xml`.

A toolchain does not install a JDK. It only selects an existing installation and provides that information to supporting plugins.

## 2. Distinguishing the Maven Runtime JDK, Toolchain JDK, and Target Release

These three concepts are often confused:

| Concept | How It Is Determined | Effect |
|---|---|---|
| Maven runtime JDK | JAVA_HOME, PATH, or Maven/IDE configuration | Runs Maven core and most plugin code |
| Toolchain JDK | Selected by Maven Toolchains Plugin from toolchains.xml or discovery | Provides the JDK to toolchain-aware plugins |
| Java release/target | maven.compiler.release or equivalent compiler configuration | Controls the language level, API, and bytecode version the source is allowed to use |

For example:

- Maven runs on JDK 21.
- The toolchain provides JDK 17 to the Compiler Plugin and Surefire.
- The compiler uses release 17 to generate Java 17-compatible bytecode.

In that case, the Maven process still runs on JDK 21. The toolchain does not change `JAVA_HOME`, `PATH`, `java.home`, or the JDK used by every plugin. Only toolchain-aware plugins use the selected JDK.

The `maven.compiler.release` property does not select an installed JDK. It restricts the API and bytecode version produced by the compiler. If you need a specific `javac`, configure a toolchain; if you need artifacts that run on a specific Java release, set the corresponding `release`. Often, both configurations are needed.

## 3. When Should You Use Maven Toolchains?

Toolchains are useful in the following scenarios:

- Building a Java 17 project while Maven or the IDE is running on JDK 21.
- Testing compatibility across multiple JDKs without changing the system-wide `JAVA_HOME`.
- Using the same JDK for compilation, testing, Javadoc, and other toolchain-aware plugins.
- Standardizing builds across developer machines, build servers, and CI runners.
- Supporting multiple project branches that require different JDKs.
- Selecting a JDK by vendor or version range.
- Avoiding hardcoding personal machine paths into the POM.

Toolchains are especially useful in large projects where multiple plugins invoke tools such as `javac`, `java`, `javadoc`, `jdeps`, or `jarsigner`.

If the entire team and CI already run Maven on the same JDK, no plugin needs a different JDK, and multi-version testing is unnecessary, toolchain configuration may not be needed.

## 4. Two-Sided Configuration Architecture

There are two main parts:

1. The project's POM declares the toolchain requirement and invokes the Maven Toolchains Plugin.
2. `toolchains.xml` on the build machine describes the installed JDKs and the paths to them.

Workflow:

~~~text
mvn clean verify
       |
       v
Maven starts on the JDK from JAVA_HOME
       |
       v
Maven Toolchains Plugin runs in the validate phase
       |
       v
Reads toolchains.xml and matches requirements from the POM
       |
       v
Selects the JDK toolchain and stores it in the Maven build context
       |
       v
Toolchain-aware plugins retrieve the selected JDK
       |
       +---- Compiler Plugin: compiles sources
       |
       +---- Surefire/Failsafe: runs the test JVM
       |
       +---- Javadoc/Jarsigner: invokes JDK tools
~~~

The toolchain is selected in the `validate` phase so that plugins running in later phases can use it. A plugin that does not support toolchains may still run using its own configured JVM or tool.

## 5. Installing and Verifying JDKs

Install the required JDKs on the developer machine or CI runner. Each JDK must be a full JDK distribution containing the necessary tools in its `bin` directory.

Example paths:

~~~text
Windows:
C:/Java/jdk-17
C:/Java/jdk-21

Linux:
 /opt/jdk-17
 /opt/jdk-21

macOS:
 /Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
~~~

Verify the JDK directly:

~~~powershell
C:\Java\jdk-17\bin\java -version
C:\Java\jdk-17\bin\javac -version
~~~

On Linux/macOS:

~~~bash
/opt/jdk-17/bin/java -version
/opt/jdk-17/bin/javac -version
~~~

Check the Maven runtime:

~~~powershell
mvn -version
~~~

This command reports the Maven version, Java version, Java home, and operating system that Maven is using. It does not prove that a toolchain was selected; you need to check the logs of the Maven Toolchains Plugin and the plugins using the JDK.

## 6. Creating the toolchains.xml File

By default, Maven looks for the user-level file at:

~~~text
~/.m2/toolchains.xml
~~~

On Windows, the corresponding path is typically:

~~~text
%USERPROFILE%\.m2\toolchains.xml
~~~

Example declaring a JDK 17 and a JDK 21:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17.0.12</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>C:/Java/jdk-17</jdkHome>
    </configuration>
  </toolchain>

  <toolchain>
    <type>jdk</type>
    <provides>
      <version>21.0.4</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>C:/Java/jdk-21</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Elements:

- type: toolchain type. For a standard JDK, the value is `jdk`.
- provides: metadata used by plugins for matching, such as `version` and `vendor`.
- configuration: path configuration to access the toolchain.
- jdkHome: root directory of the JDK, not the path to `java.exe` or `javac.exe`.

You can declare multiple toolchains of the same type. Each toolchain needs a set of metadata sufficient to distinguish it and a valid installation path.

Using forward slashes in Windows paths makes the XML easier to read and avoids confusion with escape sequences. Replace the example paths with the actual JDK locations on your machine.

## 7. Configuring Maven Toolchains Plugin in the POM

Example requiring JDK 17 with vendor metadata `temurin`:

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
            <version>[17,18)</version>
            <vendor>temurin</vendor>
          </jdk>
        </toolchains>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

The plugin searches for an entry with type `jdk`, a version in the range `[17,18)`, and a vendor matching `temurin`. If found, the plugin stores the toolchain in the build context for supporting plugins to use.

The `toolchain` goal is bound to the `validate` phase. You still need to declare the execution and matching criteria in the POM as shown above.

Maven Toolchains Plugin 3.3.0 requires Maven 3.6.3 or later and JDK 8 or later to run the plugin. Verify your Maven runtime before using this plugin version.

## 8. Understanding Version and Vendor Matching

This is a common source of configuration errors.

If `toolchains.xml` declares:

~~~xml
<version>17.0.12</version>
~~~

then requesting:

~~~xml
<version>17</version>
~~~

will not necessarily match. With full version strings, use a version range:

~~~xml
<version>[17,18)</version>
~~~

This range accepts versions greater than or equal to 17 and less than 18, such as `17` or `17.0.12`.

Some version range examples:

| Requirement | Meaning |
|---|---|
| [17,18) | JDK 17.x, excluding JDK 18 |
| [17,) | JDK 17 or higher |
| [21,22) | JDK 21.x |
| [8,9) | Version metadata 8.x using that notation |
| [1.8,1.9) | Java 8 version represented in 1.8.x form |

Other attributes such as `vendor` are matched as exact strings rather than fuzzy matches; comparison is case-insensitive. Use the same value in both the POM and `toolchains.xml`.

Important note: `version` and `vendor` inside `provides` are metadata used for matching. Maven does not verify that the actual JDK at `jdkHome` matches the declared version or vendor metadata. The plugin checks that the path exists; the person configuring it must ensure the path points to the right JDK.

## 9. Which Plugins Support JDK Toolchains?

Several Apache Maven plugins support JDK toolchains:

| Plugin | Purpose |
|---|---|
| maven-compiler-plugin | Compiles sources using the toolchain's javac |
| maven-surefire-plugin | Runs unit tests using the toolchain JDK |
| maven-failsafe-plugin | Runs integration tests using the toolchain JDK |
| maven-javadoc-plugin | Generates Javadoc using JDK tools |
| maven-jarsigner-plugin | Signs JARs |
| maven-jdeps-plugin | Analyzes dependencies/modules |
| maven-jlink-plugin | Creates runtime images |
| maven-jmod-plugin | Creates JMOD files |

The list and supported versions are maintained in the Maven documentation. A third-party plugin might not support toolchains, even if it invokes a tool included in the JDK.

Do not assume every plugin in the lifecycle automatically switches to the selected JDK. Check the plugin documentation or build logs to confirm whether a specific plugin reads the toolchain.

## 10. Configuring Compiler Plugin with a Toolchain

The Compiler Plugin is one of the most common consumers of a JDK toolchain.

Example:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.16.0</version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Once the Maven Toolchains Plugin has selected JDK 17, the Compiler Plugin can use `javac` from that JDK. `release` 17 governs the source language level, Java APIs, and target bytecode.

Distinction:

- The toolchain determines which JDK compiler is invoked.
- `release` determines which Java version the source code is allowed to use and the bytecode version generated.
- `source`/`target` only control language level and bytecode at a lower level; `release` is usually the better choice on JDK 9 and later because it also constrains the API.

If you only set `release` 17 while Maven is running on JDK 21, the compiler can still run on JDK 21 and emit Java 17 bytecode. To ensure `javac` 17 is used, you need a toolchain or a separate compiler executable configuration.

## 11. Using Toolchains for Surefire and Failsafe

Surefire runs unit tests; Failsafe runs integration tests. When a shared toolchain is configured, Surefire/Failsafe can launch the test JVM using the selected JDK.

Example:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.5.4</version>
  <configuration>
    <forkCount>1</forkCount>
  </configuration>
</plugin>
~~~

By default, Surefire can use the primary toolchain to run the test JVM. The toolchain only affects forked test processes. If `forkCount` is set to `0`, tests run inside the Maven process itself, which cannot switch its already-running JVM to a different JDK.

Therefore, when tests need to verify the actual JDK, let Surefire fork a process and check `Runtime.version()` inside the test.

Failsafe has a similar toolchain mechanism, suitable for the `integration-test` and `verify` phases. Consult the documentation for your plugin version if you have custom JVM or fork configurations.

## 12. Selecting Different JDKs per Plugin

The Toolchains Plugin selects a single shared JDK for toolchain-aware plugins. In some projects, compilation and testing require different JDKs.

Plugins that support the `jdkToolchain` parameter can specify a dedicated toolchain:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.16.0</version>
  <configuration>
    <jdkToolchain>
      <version>[17,18)</version>
    </jdkToolchain>
  </configuration>
</plugin>
~~~

A plugin-specific `jdkToolchain` configuration overrides the shared toolchain selected by the Maven Toolchains Plugin for that plugin.

Version requirements for this support:

- Compiler Plugin supports `jdkToolchain` starting from version 3.6, with Maven 3.3.1 or later.
- Surefire and Failsafe support it starting from 3.0.0-M5.
- Javadoc Plugin supports it starting from 3.0.0.

Use this override only when there is a real requirement, such as compiling with JDK 17 but running tests on JDK 21. If separation is not needed, keeping a single shared toolchain is easier to manage.

## 13. Automatic JDK Discovery with Maven Toolchains Plugin

Starting from version 3.2.0, the Maven Toolchains Plugin includes a JDK discovery mechanism. The plugin uses heuristics to locate JDKs in common installation directories and via environment variables.

List discovered JDKs:

~~~powershell
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
~~~

The output can show:

- Installation path.
- Version and runtime version.
- Vendor and vendor version.
- Whether this JDK is the one currently running Maven.
- Whether it is an LTS release.
- Related environment variables.

If you want the plugin to automatically select a matching JDK, use the `select-jdk-toolchain` goal. For example, selecting JDK 17:

~~~powershell
mvn toolchains:select-jdk-toolchain -Dtoolchain.jdk.version="[17,18)" compile
~~~

You can also declare this goal in the POM:

~~~xml
<properties>
  <toolchain.jdk.version>[17,18)</toolchain.jdk.version>
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

The `select-jdk-toolchain` goal can choose from both explicitly declared JDKs and discovered JDKs. The discovered list is cached to reduce lookup time.

Discovery depends on heuristics and how JDKs are installed. If the plugin fails to detect a JDK, declare it manually in `toolchains.xml` or check environment variables and installation paths.

Do not configure two different executions at the same time just to select the same JDK without understanding the execution order and purpose of each goal. Choose the management approach that fits your build environment.

## 14. Complete Example: Maven on JDK 21, Build and Test with JDK 17

This example verifies the toolchain with a unit test. Maven can run on JDK 21; the Toolchains Plugin selects JDK 17; Surefire forks the test JVM using JDK 17.

Project structure:

~~~text
toolchain-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          App.java
    test/
      java/
        demo/
          ToolchainTest.java
~~~

Create `toolchains.xml` at `~/.m2/toolchains.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17.0.12</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>C:/Java/jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Replace `version`, `vendor`, and `jdkHome` with your actual JDK metadata and path. The POM uses the version range `[17,18)` to match metadata such as `17` or `17.0.12`.

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>toolchain-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

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
              <version>[17,18)</version>
              <vendor>temurin</vendor>
            </jdk>
          </toolchains>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.16.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.4</version>
        <configuration>
          <forkCount>1</forkCount>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Create `src/main/java/demo/App.java`:

~~~java
package demo;

public final class App {
    public static String message() {
        return "Built with Maven toolchain.";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Create `src/test/java/demo/ToolchainTest.java`:

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ToolchainTest {
    @Test
    void surefireRunsOnJdk17() {
        assertEquals(17, Runtime.version().feature());
    }

    @Test
    void applicationReturnsExpectedMessage() {
        assertEquals("Built with Maven toolchain.", App.message());
    }
}
~~~

Run:

~~~powershell
mvn -version
mvn clean verify
~~~

The first command shows the JDK running Maven. The second performs toolchain selection during `validate`, compiles the sources with the Compiler Plugin, and runs the tests with Surefire.

When the JDK is selected, the log will look similar to:

~~~text
[INFO] --- toolchains:3.3.0:toolchain (default) @ toolchain-demo ---
[INFO] Required toolchain: jdk [ version='[17,18)', vendor='temurin' ]
[INFO] Found matching toolchain for type jdk: JDK[C:/Java/jdk-17]
~~~

Expected test output:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

The two tests confirm that Surefire forks a JVM with Java feature version 17 and that the application method returns the expected result. The exact JDK path and full log lines depend on the machine; the Maven runtime version may be 21 while the tests still run on 17.

If Maven cannot find the toolchain, the build should fail at the toolchain selection step. Do not work around that error by changing `release` or just changing `JAVA_HOME` if the goal is to verify that JDK 17 is selected.

## 15. Using a Separate toolchains.xml for CI

Each CI runner may have JDKs installed at different paths. Therefore:

- Install the required JDK on the runner before invoking Maven.
- Create `toolchains.xml` in the CI user's home directory or pass the file using the `-t` option.
- Use the runner's actual JDK paths.
- Keep `version`/`vendor` metadata consistent with the requirements in the POM.
- Run the Maven Wrapper to standardize the Maven distribution.
- Retain toolchain selection logs in the build output for easy inspection.

Example using a custom toolchains file:

~~~powershell
mvn -t C:\ci\config\toolchains.xml clean verify
~~~

Since Maven 3.3.1, the `-t` or `--toolchains` option allows specifying an alternate toolchains file. This file path belongs to the build environment and does not need to be hardcoded in the POM.

Do not commit a `toolchains.xml` containing developer-specific absolute paths into the repository. Each developer or runner manages its own file; the POM only holds the shared project criteria.

The Maven Wrapper pins the Maven version for the project, but it does not install or select a JDK on behalf of toolchains. CI must still provision the JDK and configure the proper paths.

## 16. Verifying Which JDK Is Actually Used

Use multiple layers of evidence:

1. Run `mvn -version` to see the JDK of the Maven process.
2. Read the Maven Toolchains Plugin log to see the requirement and selected JDK.
3. Check the Compiler Plugin log to confirm the compiler toolchain is being used.
4. For Surefire/Failsafe, confirm the test JVM is forked using the toolchain.
5. Use a test that reads `Runtime.version()` when you need to verify the JVM version running tests.
6. Inspect artifact bytecode with `javap -verbose` if you need to verify the class-file major version.

Example:

~~~powershell
mvn -X clean verify
~~~

Debug mode provides additional details about plugin execution and toolchains. The log can be verbose; filter for lines containing `toolchains`, `maven-compiler-plugin`, `maven-surefire-plugin`, and the JDK path.

Inspect bytecode:

~~~powershell
javap -verbose target/classes/demo/App.class
~~~

For Java 17, the class-file major version is `61`. The bytecode version confirms the class target level; it does not prove which JDK directory supplied the compiler executable. To prove the compiler JDK, check the toolchain selection and compiler logs.

## 17. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| No toolchain matched | No entry satisfies version/vendor in toolchains.xml | Check metadata in both the POM and toolchains.xml |
| JDK 17 does not match | POM uses version 17 while the file specifies 17.0.x | Use range [17,18) or match metadata exactly |
| Vendor does not match | Vendor strings differ | Use the same metadata string, paying attention to exact matching |
| Invalid jdkHome | Path points to a JRE or a non-existent directory | Point to the root of a full JDK |
| Maven still shows Java 21 | Maven process still runs on JAVA_HOME JDK 21 | This is normal behavior; check the toolchain log and test JVM |
| Compiler uses the wrong JDK | Compiler plugin is not reading the toolchain or has an override configured | Check the plugin version and jdkToolchain |
| Tests run on a different JDK | Surefire is not forking or has custom JVM settings | Check forkCount, jdkToolchain, and the forked JVM log |
| CI passes locally but fails | CI lacks the JDK or has a different toolchains.xml | Provision the JDK and create a toolchain file for the runner |
| Discovery does not find the JDK | JDK is outside heuristic locations or env var is not set | Configure toolchains.xml manually or check JAVA17_HOME |
| Plugin does not use the selected JDK | Plugin does not support toolchains | Check plugin documentation or configure a separate executable if supported |

### 17.1. Step-by-Step Diagnosis

When troubleshooting an error:

1. Confirm the Maven runtime with `mvn -version`.
2. Confirm `toolchains.xml` belongs to the right user and is at the right path.
3. Open the XML file and check the `type`/`provides`/`configuration` structure.
4. Verify that the `jdkHome` directory exists and contains `bin/javac` and `bin/java`.
5. Compare the `version`/`vendor` requested in the POM with the entry's metadata.
6. Run `mvn -X validate` to see which toolchain the plugin selects.
7. Check whether the target plugin supports toolchains and is at a recent enough version.
8. If the failure occurs in tests, check Surefire/Failsafe forking and `jdkToolchain`.
9. Re-run the same command in the CI environment with JDK selection logs saved.

## 18. Alternatives and Limitations

You can specify the `javac` executable directly in the Compiler Plugin using `fork` and `executable`. This approach only configures the compiler plugin; it does not automatically provide the same JDK to Surefire, Javadoc, or other plugins.

Example:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.16.0</version>
  <configuration>
    <fork>true</fork>
    <executable>C:/Java/jdk-17/bin/javac</executable>
  </configuration>
</plugin>
~~~

This approach depends on system paths and makes the POM less portable. Toolchains are usually a better fit when multiple plugins need the same JDK.

Limitations to keep in mind:

- Toolchains only apply to plugins that support them.
- Toolchains do not change the JVM running Maven itself.
- `toolchains.xml` does not install, update, or verify the provenance of a JDK.
- `version`/`vendor` in `provides` are matching metadata only.
- A plugin can override the shared toolchain using `jdkToolchain`.
- The JDK toolchain and compiler `release` are two independent configurations.
- Native tools or custom plugins need explicit toolchain support to use them.

## 19. Best Practices for Stable Builds

- Pin the Maven Wrapper version and the versions of key build plugins.
- Choose a tight enough version range, such as `[17,18)` instead of `[17,)`, if the project requires a specific major version.
- Standardize vendor metadata across the team and CI.
- Provision the same JDK distribution/patch level if strict build reproducibility is required.
- Keep `toolchains.xml` in the user home directory or dedicated CI secrets/config, and never commit local paths.
- Let the build fail early when a required JDK cannot be found.
- Log the JDK runtime and toolchain selection.
- Use a test that checks `Runtime.version()` when the test JDK is a critical requirement.
- Consider plugin-specific `jdkToolchain` only when multiple JDKs are genuinely needed in one build.
- Never assume every plugin uses the toolchain.
- Cross-check the Maven runtime, compiler JDK, test JDK, and release target when investigating compatibility issues.

## 20. Maven Toolchain Checklist

- [ ] Identified the JDK used to run Maven.
- [ ] Identified the JDK toolchain required by the project.
- [ ] Distinguished the toolchain JDK from `maven.compiler.release`.
- [ ] Full JDKs are installed on developer machines/CI runners.
- [ ] `toolchains.xml` has an entry with type `jdk` and a valid `jdkHome`.
- [ ] Version range and vendor metadata match the entry.
- [ ] Maven Toolchains Plugin version is pinned and has a `toolchain` goal execution.
- [ ] Compiler Plugin supports toolchains and has the correct `release` configured.
- [ ] Surefire/Failsafe uses the expected JDK when running tests.
- [ ] Checked plugin-specific `jdkToolchain` if overrides are used.
- [ ] Verified toolchain selection logs.
- [ ] Verified `Runtime.version()` in tests if needed.
- [ ] CI runners have the appropriate JDK and `toolchains.xml`.
- [ ] Local paths are not hardcoded into the POM or accidentally committed.
- [ ] Build fails clearly when a required toolchain cannot be found.

Maven Toolchains separate a project's JDK requirements from the JDK running Maven. The POM declares the criteria, `toolchains.xml` or discovery provides the installed JDK, and supporting plugins use the selected toolchain. Always verify the Maven runtime, compiler JDK, test JVM, and release target to ensure the build truly uses the right Java version at every step.

## References

- Apache Maven, Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Apache Maven Toolchains Plugin, Usage: https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html
- Apache Maven Toolchains Plugin, JDK Discovery Mechanism: https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html
- Apache Maven Toolchains Plugin, JDK Toolchain: https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html
- Apache Maven Compiler Plugin, Compiling Sources Using a Different JDK: https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html
- Apache Maven Surefire Plugin, Using Maven Toolchains: https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html
- Apache Maven Toolchains Plugin, Plugin Details and System Requirements: https://maven.apache.org/plugins/maven-toolchains-plugin/plugin-info.html
