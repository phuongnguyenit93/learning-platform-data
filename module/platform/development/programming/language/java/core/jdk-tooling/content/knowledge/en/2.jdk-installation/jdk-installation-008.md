# Managing JDK Versions

## 1. Why Do We Need to Manage Multiple JDK Versions?

In practice, a development machine often needs multiple Java versions at the same time. Legacy projects may still run on Java 8 or 11, while newer projects require Java 17, 21, or later. Certain libraries, frameworks, build plugins, and deployment environments also impose their own version requirements.

**Managing JDK versions** is the process of installing, selecting, switching, and pinning the appropriate JDK version for each project or environment. The goal is to ensure that compile, run, test, and packaging commands all use the right toolchain.

For example, a single machine might have:

- JDK 17 to maintain a legacy service.
- JDK 21 to develop a new application.
- JDK 25 to test compatibility with a newer Java release.

Installing multiple JDKs does not mean they are automatically used correctly. Your terminal, IDE, Maven, Gradle, and CI may each be pointing to different JDKs. Therefore, you need to know which tool is selecting which version and how to verify that selection.

## 2. Distinguishing Java Versions, Vendors, and Updates

When someone says a project uses Java 21, that only specifies the **feature release**. A JDK distribution also has a specific vendor and update number.

For example, a version string may look like this:

```text
21.0.5+11
│  │ │  └─ build number
│  │ └──── update release
│  └────── feature version
└───────── Java version
```

The exact display format may vary across vendors and distributions.

### 2.1. Feature Releases and LTS

Java releases feature releases on a regular cadence. Some versions receive Long-Term Support (LTS) from vendors, while others have shorter support windows.

LTS feature releases are commonly used as baselines for enterprise systems. For example, Java 8, 11, 17, 21, and 25 are common LTS milestones. Specific support policies and update timelines depend on the vendor, support contracts, and organizational policies.

When choosing a version for a project, consider:

- The minimum version supported by frameworks and libraries.
- The JDK version running in the production environment.
- The support duration and security update availability.
- Compatibility of build plugins, testing tools, and IDEs.
- The development team's upgrade roadmap.

### 2.2. JDK Vendors

Many vendors distribute JDKs compatible with the Java specification, such as Eclipse Temurin, Oracle JDK, Amazon Corretto, Azul Zulu, and Microsoft Build of OpenJDK.

Distributions of the same feature release generally aim for Java compatibility, but may differ in patch release schedules, platform support, licensing terms, bundled tools, and support services.

For team or production projects, it is best to standardize both the feature release and the JDK vendor when there are requirements for support, auditing, or environment reproducibility. Avoid simply stating "use Java 21" if the team needs a specific distribution.

## 3. Installing Multiple JDKs Side by Side

You can install multiple JDKs on the same machine. Each installation should reside in its own directory so it is easy to identify and does not overwrite others.

Example directory layout:

```text
Windows:
C:\Dev\Java\jdk-17
C:\Dev\Java\jdk-21
C:\Dev\Java\jdk-25

Linux:
 /opt/jdks/jdk-17
 /opt/jdks/jdk-21
 /opt/jdks/jdk-25

macOS:
 /Library/Java/JavaVirtualMachines/
```

On macOS, JDK installers typically create a bundle directory named like `jdk-21.jdk` inside `/Library/Java/JavaVirtualMachines/`.

You can download a JDK from the vendor's website or install it using an OS-appropriate package manager. When installing, verify the CPU architecture (x64 or ARM64), operating system, and required version. Do not download installers from untrusted sources.

After installation, note the root directory of each JDK. The root directory is the folder containing `bin`, `conf`, `include`, and other JDK components; `JAVA_HOME` must point to this directory, not directly to `bin`.

## 4. How `JAVA_HOME` and `PATH` Determine the Active Version

The two most common mechanisms are `JAVA_HOME` and `PATH`.

- `JAVA_HOME` indicates the JDK directory that build tools or scripts may use.
- `PATH` determines the order in which the operating system searches for executables when you run commands such as `java` or `javac`.

For example, if `JAVA_HOME` points to JDK 21, but `PATH` has a JDK 17 directory listed earlier, running `java` in the terminal may still execute JDK 17.

Therefore, changing `JAVA_HOME` alone does not guarantee that the active runtime version has switched. After switching, verify both variables and the output of the Java commands.

### 4.1. Checking the Current Version and Paths

On any operating system, start with:

```bash
java --version
javac --version
```

On Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
```

`Get-Command ... -All` shows all matching commands that PowerShell can find. `where.exe` lists the executables found in `PATH`.

On Linux or macOS:

```bash
echo "$JAVA_HOME"
type -a java
type -a javac
command -v java
command -v javac
```

On Linux, you can inspect the actual target path of the command:

```bash
readlink -f "$(command -v java)"
```

To see which directory the runtime is actually using, run:

```bash
java -XshowSettings:properties -version
```

Look for the `java.home` property in the output. Note that `java.home` is the runtime directory used by the JVM, which is not necessarily the root directory of the installed JDK.

### 4.2. Switching JDK Temporarily in Windows PowerShell

Set the environment variables in the current PowerShell session:

```powershell
$env:JAVA_HOME = "C:\Dev\Java\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java --version
javac --version
```

This applies to the current PowerShell session and child processes launched from it. It does not permanently modify system configuration or other open terminal windows.

If `PATH` already contains the `bin` directory of an older JDK before the new one, the command above leaves the older entries later in the list. Because the new path is prepended, it takes precedence in the current session.

For persistent configuration, open **Environment Variables** in Windows:

1. Create or update the user variable `JAVA_HOME` to point to the root directory of the desired JDK.
2. In the `Path` variable, add `%JAVA_HOME%\bin`.
3. Move this entry above any older JDK entries, or remove old entries if they are no longer needed.
4. Open a new terminal and verify with `java --version`, `javac --version`, and `Get-Command java -All`.

Do not set `JAVA_HOME` to `C:\Dev\Java\jdk-21\bin`. It must point to `C:\Dev\Java\jdk-21`.

### 4.3. Switching JDK on Linux

In a shell session, you can set the variables as follows:

```bash
export JAVA_HOME=/opt/jdks/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
```

`export` commands affect only the current shell and its child processes. To apply them to new login sessions, add the appropriate configuration to `~/.bashrc`, `~/.zshrc`, or the configuration file for your shell.

On Debian/Ubuntu distributions, `update-alternatives` can manage the default selection for Java commands:

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
```

Make sure to select the same version for both `java` and `javac`. `update-alternatives` manages command paths; it does not guarantee that `JAVA_HOME` is updated accordingly. Check and set `JAVA_HOME` separately if your build tools require it.

Command names and configurations may differ on other Linux distributions. In container environments or organization-managed servers, follow the software installation and management conventions of that environment.

### 4.4. Switching JDK on macOS

macOS provides the `/usr/libexec/java_home` utility to locate installed JDKs.

List installed JDKs:

```bash
/usr/libexec/java_home -V
```

Select JDK 21 for the current shell session:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
```

To automatically select JDK 21 when opening a shell, add those two `export` lines to `~/.zshrc` if using zsh, or the corresponding shell configuration file. To switch to another version, replace `-v 21` with the desired feature release.

## 5. Using a JDK Version Manager

When frequently switching between multiple projects, manually editing `JAVA_HOME` and `PATH` is error-prone. Version managers let you install and select JDKs via commands, and sometimes pin versions per project directory.

Common options include:

| Tool | Common Platforms | How It Manages Versions |
|---|---|---|
| SDKMAN! | Linux, macOS, and compatible Unix environments | Installs multiple Java distributions, switches versions per shell or sets a default |
| jenv | macOS and Linux | Selects JDK globally, per directory, or per shell |
| mise | macOS, Linux, and Windows | Manages multiple runtimes/tools, selects versions globally or per project |
| asdf | macOS and Linux; other platforms depending on environment | Manages Java and directory-level versions via plugins |
| IDE tooling | Varies by IDE | Selects JDK per project, module, and build runner |

You do not need to install all of these tools. Choose one approach that fits your operating system, company policies, and team workflow.

### 5.1. SDKMAN!

SDKMAN! is commonly used on Linux and macOS. After installing SDKMAN! according to the official guide, you can list available Java versions:

```bash
sdk list java
```

Install a specific candidate shown in the list:

```bash
sdk install java <candidate>
```

Switch to an installed version in the current shell:

```bash
sdk use java <candidate>
```

Set a default version for new shells:

```bash
sdk default java <candidate>
```

`<candidate>` is the full version identifier listed by SDKMAN!, typically including the feature release, update, and vendor. Copy the exact identifier from the list at installation time rather than guessing the version string.

### 5.2. jenv

jenv manages Java selection by adjusting command shims in the shell. After installing jenv and registering existing JDKs, you can use these commands:

```bash
jenv versions
jenv add /path/to/jdk
jenv global 21
jenv local 17
jenv shell 21
```

Command breakdown:

- `jenv versions`: lists versions known to jenv.
- `jenv add`: registers an installed JDK.
- `jenv global`: sets the default selection for the user.
- `jenv local`: sets the selection for a project directory via jenv's configuration file.
- `jenv shell`: sets a temporary selection for the current shell.

Version names recognized by jenv may include vendor or update details. Use the exact name shown in `jenv versions`.

If you also want jenv to manage `JAVA_HOME`, enable the `export` plugin according to the instructions for your installed jenv version. Without it, `java` may switch via jenv while tools reading `JAVA_HOME` still see the old value.

### 5.3. mise

mise can manage multiple development tools, including Java. After installing mise and activating it in your shell, you can set a Java version for a project:

```bash
mise use java@21
```

This command writes the version configuration into the project directory. To set the version globally:

```bash
mise use --global java@21
```

Check the configuration and currently selected version:

```bash
mise current
java --version
javac --version
```

How JDKs are installed, whether versions are downloaded automatically, and how distribution sources are configured depend on your mise configuration and Java backend plugin. Check the installation status if a command asks to download or select an unavailable JDK.

### 5.4. Which Tool Should You Choose?

- Single JDK and rarely switch versions: setting `JAVA_HOME` and `PATH` is sufficient.
- Developing multiple projects on macOS/Linux: SDKMAN! or jenv are familiar choices.
- Want a single tool to manage multiple runtimes and pin versions per project: consider mise or asdf.
- Working on Windows: you can use Windows environment variables, mise, or other suitable version managers. SDKMAN! is typically used inside WSL rather than native PowerShell.
- Working in a team: prefer an explicit version-pinning approach documented in the project so all members stay consistent.

## 6. Pinning the JDK Version per Project

A machine may have a default JDK, but every project should explicitly declare the version it requires. That way, opening an older project will not accidentally use a newer JDK just because it is the machine's default.

There are typically three configuration layers to consider:

1. The JDK running the build tool (Maven or Gradle).
2. The JDK compiler used to compile the source code.
3. The target Java version that the application supports at runtime.

These three values are related, but they do not have to be identical.

### 6.1. Using `--release` When Compiling Directly

If you have a newer JDK installed but want to compile an application compatible with Java 17:

```bash
javac --release 17 -d out src/com/example/Hello.java
```

`--release 17` instructs the compiler to use the language rules, bytecode level, and public APIs corresponding to Java 17. It is useful when building on a newer JDK for an older runtime.

This option does not replace choosing the JDK that runs the application. Nor does it turn an older JDK into a compiler for a newer version. If your source code uses syntax introduced in Java 21, a Java 17 compiler cannot compile it.

### 6.2. Configuring Maven

With Maven, you can declare the target Java version in `pom.xml` using the `maven.compiler.release` property:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

This configuration instructs the Maven Compiler Plugin to use release 17 when compiling. The plugin version must support the `release` configuration parameter.

Maven also supports **Toolchains** to select a locally installed JDK specifically for build plugins. The `~/.m2/toolchains.xml` file can declare installed JDKs:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>C:\Dev\Java\jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
```

This is an illustrative example: `vendor` and `jdkHome` must match an actually installed JDK and what the plugin requests from the toolchain. On Linux/macOS, replace `jdkHome` with the actual path to the JDK.

Toolchains let Maven select the compiler JDK for toolchain-aware plugins. However, the Maven launcher and the JVM running Maven itself can still be a different JDK. Check Maven's JVM version with:

```bash
mvn -version
```

### 6.3. Configuring Gradle Java Toolchains

Gradle supports declaring a toolchain in `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

This configuration tells Gradle to use a JDK with Java language version 17 for the corresponding Java tasks, such as compilation and testing. You can also add a vendor requirement when the team needs to standardize on a specific vendor.

Check the Gradle environment:

```bash
./gradlew --version
```

On Windows, use `gradlew.bat --version`.

Distinguish between the JDK running the Gradle daemon and the toolchain JDK used for project tasks. They can be different. Your Gradle version must support the JDK used to run Gradle itself; check Gradle's compatibility matrix before upgrading the build runner's JDK.

## 7. Configuring the JDK in an IDE

IDEs may maintain their own JDK settings, so having the terminal run the right Java does not guarantee that the Build or Run button in the IDE uses the same version.

### 7.1. IntelliJ IDEA

Common places to check:

- **Project SDK:** the main JDK for the project.
- **Project language level:** the Java syntax level allowed by the project.
- **Module SDK:** the JDK for a specific module if the project has multiple modules.
- **Gradle JVM:** the JDK running the Gradle daemon.
- **Maven Runner JRE:** the JDK running Maven inside the IDE.

When changing the JDK, check both Project SDK and Gradle JVM or Maven Runner if the project uses those build systems.

### 7.2. Eclipse

In Eclipse, you can register JDKs under **Installed JREs**. Then select the JDK for a project in **Java Build Path** or choose the appropriate execution environment.

The project's compiler compliance level must be compatible with the target Java version. A project can run the IDE on a newer JDK while still targeting a lower compilation level if configured appropriately.

### 7.3. Visual Studio Code

With the Extension Pack for Java, you can declare runtimes in `settings.json`:

```json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-17",
      "path": "C:\\Dev\\Java\\jdk-17"
    },
    {
      "name": "JavaSE-21",
      "path": "C:\\Dev\\Java\\jdk-21",
      "default": true
    }
  ]
}
```

The path must point to the JDK root directory. The `default` option specifies the default runtime used by the extension where appropriate. For Maven or Gradle projects, you still need to check the project's own build configuration.

## 8. Managing JDKs in CI and Deployment Environments

Developer machines are only part of the build pipeline. CI, build agents, containers, and production environments also need the right Java version.

Key principles:

- Explicitly specify the feature release, vendor, and update version when the project requires strict reproducibility.
- Use CI configurations that pin the JDK version, avoiding floating aliases that change over time unless you intend to upgrade proactively.
- Verify both the JDK running the build and the project's compiler toolchain.
- Run tests on the same runtime version that production will use.
- If supporting multiple Java versions, use a build matrix to test each target version.
- For Docker, use images with explicit version tags; when high reproducibility is required, consider pinning the image digest as well.
- Apply security patches on a maintenance schedule and re-verify compatibility after upgrades.

A successful build on a personal machine does not prove the application will run properly in production. CI must test with the target JDK and runtime, and the deployment environment must provide a runtime compatible with the bytecode and APIs the application uses.

## 9. Common Issues When Switching JDK Versions

| Symptom | Common Cause | Resolution |
|---|---|---|
| `java --version` does not change after editing `JAVA_HOME` | `PATH` still prioritizes an older JDK | Check `PATH` order and open a new terminal |
| `java` and `javac` show different versions | The two commands are resolved from different JDK directories | Check `Get-Command -All`, `where.exe`, `type -a`; align paths |
| Terminal uses the right JDK, but the IDE uses another | IDE stores its own Project SDK or build JVM | Check Project SDK, module SDK, and runner JVM |
| Maven runs with an unexpected JDK | `JAVA_HOME`, `PATH`, or IDE config points elsewhere | Run `mvn -version`, check Maven Runner and toolchains |
| Gradle fails to start after upgrading JDK | Current Gradle version does not support the JDK running Gradle | Check the compatibility matrix and upgrade the Gradle Wrapper if appropriate |
| `UnsupportedClassVersionError` | Runtime is older than the bytecode version of the app or a dependency | Use a compatible runtime or build targeting a lower release |
| Incompatible plugin or library | Plugin, annotation processor, or dependency does not yet support the new JDK | Check release notes and upgrade the relevant component |
| `JAVA_HOME` is valid, but a tool reports Java not found | Variable points to the wrong folder, points to `bin`, or path does not exist | Verify the directory contains `bin/java` or `bin/javac` |

Quick verification commands after switching versions:

```bash
java --version
javac --version
mvn -version
./gradlew --version
```

Not every project uses both Maven and Gradle. Run the command corresponding to your project's build system and check the JDK reported in the output.

## 10. Standard Workflow for Changing a Project's JDK

When upgrading or switching a JDK, follow these steps:

1. **Identify requirements:** review project configuration, frameworks, dependencies, build plugins, and the deployment environment's runtime version.
2. **Install the JDK:** install the chosen feature release and vendor; record the installation path.
3. **Select the JDK for the project:** update toolchains, version-pinning files, or IDE settings as needed.
4. **Verify build tools:** confirm both the JDK running Maven/Gradle and the compiler toolchain JDK.
5. **Compile and test:** run a clean build, unit tests, and integration tests on the target version.
6. **Verify the runtime:** run the application with the JDK or runtime image intended for deployment.
7. **Update CI and documentation:** align pipeline configurations, Docker images, and onboarding docs for team members.
8. **Monitor after upgrade:** check logs, warnings, performance, and compatibility issues in deployment.

Do not immediately delete an older JDK if other projects or tools still depend on it. Once all projects have migrated, you can remove unused installations according to your machine or organizational software management policy.

## 11. Summary

Managing JDK versions ensures that every project uses the right Java toolchain throughout development and deployment. Key takeaways:

- Multiple JDKs can be installed side by side; each should live in its own directory.
- `JAVA_HOME` points tools that read this variable to a JDK, while `PATH` determines which `java` and `javac` executables are found first.
- Verify the active version with `java --version`, `javac --version`, and by checking the actual resolved paths.
- SDKMAN!, jenv, mise, or asdf make switching versions convenient; pick one suitable tool rather than overlapping multiple mechanisms.
- Maven Toolchains, Gradle Java Toolchains, and IDE settings help pin the JDK per project.
- Separately verify the JDK running the build, the compiler JDK, and the target Java version.
- CI and production must be configured consistently with the version required by the project.

When you manage JDKs intentionally, you can maintain multiple Java projects on the same machine, upgrade each project in a controlled manner, and reduce errors caused by inconsistent development environments.
