# JDK Distribution

## Objectives

After this lesson, you will be able to explain how OpenJDK and a JDK distribution differ, distinguish between JVM, JRE, and JDK, read vendor information from an installation, choose a suitable JDK for a project, and verify the configuration when multiple JDKs are installed on a machine.

## 1. What is a JDK distribution?

A **JDK distribution** is a JDK build that an organization or vendor builds, tests, packages, and releases for users to install. Most popular distributions today take source code from the **OpenJDK** project, after which the vendor produces binaries for specific operating systems and CPU architectures, maintains updates, publishes support policies, and provides installation methods.

You can think of the release chain as follows:

1. **Java SE specification** describes the behavior and APIs that a compatible Java platform must provide.
2. **OpenJDK** is the open-source development project of the JDK, where the community and multiple vendors contribute together.
3. **JDK distribution** is a specific build from that source code, which may include patches, build configurations, packaging tools, installers, container images, and its own update commitments.
4. **Java applications** are compiled and run on an appropriate JDK/JRE distribution.

The name “OpenJDK” is sometimes used to refer to the project/source code, and sometimes to a binary built from OpenJDK source code. Therefore, when comparing two downloads, check the vendor name, full version, license, and support schedule rather than looking only at the word “OpenJDK”.

### JVM, JRE, and JDK

| Component | Role |
|---|---|
| JVM (Java Virtual Machine) | Virtual machine that executes Java bytecode, manages memory, garbage collection, class loading, and runtime operations |
| JRE (Java Runtime Environment) | Environment for running Java applications, consisting of the JVM and required runtime libraries |
| JDK (Java Development Kit) | Development toolkit, consisting of the runtime along with the compiler and tools such as javac, javadoc, jshell, jdb, jlink, jpackage, and diagnostic tools |

JRE is still a useful concept for describing an application's runtime environment, but not every vendor releases a separate JRE package for every version. Many projects today install a full JDK on development machines and create a minimal runtime image when packaging the application.

When learning Java, compiling source code, or running Gradle/Maven, install a **JDK**. Installing only a stripped-down runtime package may leave you with the java command while missing javac or other development tools.

## 2. Why are there multiple distributions?

Distributions targeting the same Java SE version may be compatible at the API level yet still differ in important ways:

- **Updates and security:** patch release timing, backport policies, maintenance duration for each version, and vulnerability handling processes.
- **Support:** providing free binaries only, community support, or commercial support contracts and SLAs.
- **Licensing:** the source code license does not automatically determine all terms of the binaries, installer packages, or support services.
- **Platforms:** Windows, Linux, macOS, AIX; x64, ARM64, s390x, ppc64le; glibc or musl; installers, archives, package repositories, or container images.
- **Virtual machine and build configuration:** HotSpot, OpenJ9, or custom optimization components; GC, compiler, profiling, and monitoring options.
- **Bundled components:** JavaFX, Java Mission Control, native image tools, or trimmed JDK variants.
- **Testing and certification process:** level of compatibility testing, certified platforms, and official support scope.

You should not conclude that one distribution is faster or more secure based solely on the vendor name. Results also depend on the version, workload, JVM configuration, operating system, hardware, and native libraries used by the application.

### What does the TCK test?

The **Technology Compatibility Kit (TCK)** is a test suite used to verify whether an implementation meets the compatibility requirements of the corresponding Java specification. For Java SE, the TCK/JCK focuses on the compatibility of APIs and specified behavior.

The TCK is not a performance benchmark, does not prove a binary is bug-free, and does not replace testing the actual application. When a product requires Java SE compatibility, check the certification status for the exact version and platform you intend to deploy on.

## 3. Some popular JDK distributions

The options below all have a place in the Java ecosystem. This is a reference list, not a ranking.

| Distribution | Organization | Key Notes |
|---|---|---|
| **Eclipse Temurin** | Eclipse Adoptium | Cross-platform OpenJDK builds tested for Java SE compatibility; often a neutral, easy-to-use choice for learning and general application development |
| **Amazon Corretto** | Amazon | Free OpenJDK distribution with LTS policies and security/performance updates published by Amazon; TCK certified |
| **Azul Zulu** | Azul | OpenJDK builds for many platforms; offers binary downloads and commercial support packages |
| **BellSoft Liberica JDK** | BellSoft | OpenJDK builds with multiple variants such as Lite, Standard, and Full; choose the right variant if the project needs JavaFX or additional components |
| **Microsoft Build of OpenJDK** | Microsoft | Free OpenJDK distribution; Microsoft publishes binaries tested for Java SE compatibility, supporting multiple operating systems and architectures |
| **Oracle JDK** | Oracle | Oracle's distribution. Usage terms depend on version, update release, and intended use; you must read the license for the exact binary |
| **Oracle OpenJDK** | Oracle/OpenJDK | OpenJDK binaries released by Oracle under an open-source license; this is a separate option from Oracle JDK |
| **IBM Semeru Runtimes** | IBM | Uses OpenJDK class libraries with the Eclipse OpenJ9 virtual machine. Available in Open Edition and Certified Edition with different licenses |
| **GraalVM** | Oracle and the GraalVM community | Suitable when you need the Graal compiler, polyglot runtime, or Native Image to build native executables; a more specialized choice than a general-purpose JDK |

Several other vendors such as Red Hat and SAP also release JDK distributions serving their operating systems, platforms, or enterprise ecosystems.

### HotSpot, OpenJ9, and GraalVM

**HotSpot** is the virtual machine used in many popular OpenJDK distributions. **OpenJ9** is another JVM implementation, used in IBM Semeru Runtimes. Differences in memory usage, startup time, throughput, and optimization strategies can affect real-world workloads.

**GraalVM** provides the Graal compiler and additional capabilities such as Native Image. Native Image analyzes reachable classes and methods to produce a native executable for a specific operating system and architecture. It can reduce startup time and footprint in some cases, but the build process requires separate configuration and testing; not every Java application can be converted to a native image without adjustments.

When switching between JVM implementations, re-run tests, benchmarks, and check native/JNI libraries. The same Java SE version does not mean all operational characteristics are identical.

## 4. Reading Java versions and distinguishing vendor versions

A JDK build usually has several components in its version string:

- **Feature release:** platform version such as 17, 21, or 25.
- **Update release:** security and bug-fix updates, for example 21.0.1 or 21.0.13.
- **Build number:** build number of a specific release, usually after a plus sign or within the vendor's identifier string.
- **Vendor/build label:** the vendor's own naming and numbering scheme.

Not all vendors represent the build number in the same way. Therefore, when switching from one distribution to another, compare the **Java feature version and update version**, rather than comparing only the full version string displayed by the vendor.

Basic check commands:

~~~bash
java -version
javac -version
~~~

To view more detailed runtime information:

~~~bash
java -XshowSettings:properties -version
~~~

In the system properties section, pay attention to these properties:

| Property | Meaning |
|---|---|
| java.version | Version of the running Java runtime |
| java.specification.version | Java SE specification version, typically 17, 21, or 25 |
| java.vendor | Vendor of the runtime |
| java.home | Runtime directory used by the Java process |
| java.vm.name | Name of the JVM implementation |
| java.vm.vendor | Vendor of the JVM |

The `java -version` command shows the runtime found via PATH. The `javac -version` command shows the compiler found. The two commands can point to two different installations if the machine has multiple JDKs.

## 5. Feature releases and LTS

Java has a feature release cadence of roughly every six months. Some versions are designated **Long-Term Support (LTS)** by vendors and maintained longer than regular feature releases.

Common LTS milestones in the modern ecosystem include Java 8, 11, 17, 21, and 25. However, update and support lifecycles are not identical across vendors.

Three concepts should be distinguished:

1. **LTS of a Java version:** a version chosen by a vendor to be maintained over a long period.
2. **Security updates:** updates that patch vulnerabilities and bugs; check the release date and the vendor's end-of-updates date.
3. **Commercial support:** contracted support services, SLAs, consulting, or incident resolution. Free LTS does not mean every form of support is free.

For new applications, it is generally best to choose an LTS that is still receiving updates and is compatible with your frameworks and deployment environment. For existing systems, you must check the requirements of frameworks, libraries, application servers, and pipelines before upgrading versions.

## 6. Licensing and cost: always check the exact build

Do not infer a license solely from the name Java or from the fact that a download does not require payment.

- OpenJDK source code is primarily released under GPLv2 with the Classpath Exception (GPLv2+CPE), but each binary and additional package must still be checked against the vendor's terms.
- Some vendors release binaries free of charge for both commercial and production use, while enterprise support services may be paid.
- Oracle JDK and Oracle OpenJDK are two separate options. Oracle JDK has licensing policies that vary by version and update release.
- According to the Oracle Java SE Licensing FAQ updated on 2026-10-20, Oracle JDK 25 and later are provided under the Oracle No-Fee Terms and Conditions (NFTC); for Java 21, updates from 21.0.13 onward have different terms from updates up to 21.0.12. Read the FAQ and the license accompanying the exact binary you download, especially when deploying to production or redistributing the JDK with a product.

When evaluating cost, separate the following:

- Fees for downloading and using the binary.
- Rights for use in development, testing, production, and redistribution.
- Duration of receiving security updates.
- Support contracts, SLAs, and incident handling responsibilities.
- Upgrade costs when a version reaches end of support.

For organizations, record the distribution name, full version, download URL, checksum, applicable license, and update policy in the dependency/software inventory.

## 7. Choosing a distribution based on needs

| Need | Selection Guidance |
|---|---|
| Learning Java, doing assignments, or personal projects | A popular LTS that is easy to install and well-documented; Eclipse Temurin is a common neutral starting point |
| Projects running on AWS | Consider Amazon Corretto if its support schedule and platforms meet requirements |
| Projects running on Azure or the Microsoft ecosystem | Consider Microsoft Build of OpenJDK after checking supported versions and platforms |
| Enterprises using RHEL or needing OS vendor support | Check Red Hat build of OpenJDK and its corresponding support terms |
| Needing OpenJ9 or wanting to test different JVM characteristics | Evaluate IBM Semeru Open Edition/Certified Edition with real workloads |
| Needing Native Image or polyglot runtime | Evaluate GraalVM and check framework/library compatibility limits |
| Contracts or products requiring Oracle Java | Use the exact Oracle JDK version covered by the contract and verify the terms of the update release |

If there are no vendor constraints, choose in the following order:

1. Choose a Java feature version supported by your project/frameworks.
2. Choose a distribution still receiving security updates for that version.
3. Verify that the license fits your intended use.
4. Check the operating system, CPU architecture, container base image, and native libraries.
5. Determine whether commercial support or an SLA is needed.
6. Run application tests and benchmarks before standardizing on a distribution for production.

A project should pin the JDK version explicitly in documentation, CI, and container images. Avoid using the `latest` tag for production environments if the pipeline does not control version changes.

## 8. Installing and verifying on a development machine

### Choosing the right installation package

Before downloading, determine:

- The Java feature version required by the project.
- The operating system and CPU architecture: Windows/Linux/macOS, x64/ARM64...
- Package type: installer, archive, package manager, or container image.
- Full JDK package or trimmed runtime.
- Whether JavaFX, native tools, or a special variant is needed.

Prefer the vendor's official download page. For enterprise environments, verify checksums/digital signatures and record the exact version so the environment can be reproduced.

### Setting JAVA_HOME and PATH

**JAVA_HOME** should point to the root directory of the JDK, i.e., the installation directory containing `bin`, `lib`, and other components. Do not set JAVA_HOME to point directly to the `bin` directory or the `java.exe` file.

PATH must include the `bin` directory of the JDK you want to use. If the machine has multiple JDKs, the order of entries in PATH determines which `java` and `javac` commands are invoked first.

Example on Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
java -version
javac -version
java -XshowSettings:properties -version 2>&1 | Select-String 'java.vendor|java.version|java.home'
~~~

Example on Windows Command Prompt:

~~~bat
echo %JAVA_HOME%
where java
where javac
java -version
javac -version
~~~

Example on Linux/macOS:

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
java -XshowSettings:properties -version 2>&1 | grep -E 'java.vendor|java.version|java.home'
~~~

After changing environment variables, open a new terminal or reload your shell configuration to pick up the new values. On Windows, also check for old JDK paths in PATH because they may appear before `JAVA_HOME/bin`.

### Verifying the JDK has the full set of tools

In addition to `java` and `javac`, you can check:

~~~bash
jshell --version
jlink --version
jpackage --version
~~~

If `java` runs but `javac` does not exist, the machine may be using a runtime-only package or PATH is not pointing to the JDK. Check the path of each command before reinstalling.

### Checking which JDK the IDE and build tools are using

The JDK used in the terminal is not necessarily the JDK used by the IDE or build tools.

- IntelliJ IDEA has its own Project SDK and Gradle JVM settings.
- Gradle can use Java toolchains to select the compiler/runtime per project.
- Maven can use Maven Toolchains or compiler plugin configuration.
- CI runners and Docker images may provide a different JDK than the development machine.

When a build succeeds in the IDE but fails in the terminal or CI, check the JVM reported by each tool. With Maven, run `mvn -version`; with Gradle, run `gradle -version` to see which JVM is running the build.

## 9. Common issues

### java and javac have different versions

**Symptom:** `java -version` reports one major version while `javac -version` reports a different major version.

**Common causes:** PATH contains multiple JDKs; the `bin` directory of an older version appears before the newer one; `JAVA_HOME` and `PATH` are inconsistent.

**Resolution:** check the actual paths with `where`/`Get-Command`/`command -v`, fix `JAVA_HOME` and the order of `PATH`, open a new terminal, and verify both commands again.

### IDE or Gradle uses a different JDK than the terminal

**Symptom:** the `java` command in the terminal is the right version, but building in the IDE reports missing APIs or unsupported source/target versions.

**Common causes:** Project SDK, Gradle JVM, Maven runner, or toolchain is selecting a different JDK.

**Resolution:** check the JDK configuration of each tool and declare a toolchain explicitly in the build if the project requires a consistent environment.

### UnsupportedClassVersionError

**Symptom:** the runtime cannot load a class because the class file was compiled with a newer Java version.

**Cause:** compiled with a newer JDK but run on an older runtime.

**Resolution:** upgrade the runtime to a compatible version, or compile with an appropriate target. For example, JDK 17 and later can use `javac --release 17` to generate bytecode and restrict APIs to Java 17.

### Incompatibility with native libraries or CPU architecture

**Symptom:** errors loading JNI libraries, linker errors, or a container fails to start even though the Java version is correct.

**Cause:** native binaries were built for a different OS/CPU/libc, or the distribution does not have a matching package.

**Resolution:** match the CPU architecture, libc, operating system, and native library version; use the right image/package for the deployment platform.

### Switched distribution but still seeing the old vendor

**Symptom:** installed a new distribution, yet `java.vendor` or `java -version` still displays the old vendor.

**Cause:** the shell is finding another `java` binary via PATH, a service/IDE has not been reconfigured, or an old process has not been restarted.

**Resolution:** check `java.home`, executable paths, `JAVA_HOME`, `PATH`, and service/IDE configurations. Restart processes after changing the environment.

## 10. Checklist when switching JDK distributions

When replacing Temurin with Corretto, Zulu, Liberica, Microsoft Build of OpenJDK, or another distribution, follow these steps in order:

1. Record the current Java feature version, update version, vendor, and JVM.
2. Confirm the new distribution has the same Java SE version required by the application.
3. Read the license, security update schedule, and support scope of the exact version.
4. Check the OS, CPU architecture, libc, package format, and container image.
5. Install the new version side by side if needed so you can compare and roll back.
6. Update `JAVA_HOME`, `PATH`, IDE, Gradle/Maven toolchains, CI, and Dockerfile.
7. Run unit tests, integration tests, security/TLS tests, and flows using JNI or JavaFX.
8. Run representative benchmarks if changing the JVM implementation or GC configuration.
9. Check logs, JFR/monitoring, and memory usage after a staging/trial deployment.
10. Record the version, checksum, download source, and rollback procedure.

Do not just check that the application starts. Verify that critical flows, performance, logging, certificates, timezones, native libraries, and security update processes still meet requirements.

## 11. Official references

- [OpenJDK Project](https://openjdk.org/) — OpenJDK source code, projects, and development activities.
- [JDK Release Information](https://ops.java/releases/) — release schedule and Java SE information.
- [Eclipse Temurin Downloads](https://adoptium.net/temurin/releases/) and [Supported Platforms](https://adoptium.net/supported-platforms) — versions, installer packages, and supported platforms.
- [Eclipse Temurin Support](https://adoptium.net/support/) — release schedule, updates, and support lifecycle.
- [Amazon Corretto](https://aws.amazon.com/corretto/) and [Corretto FAQs](https://aws.amazon.com/corretto/faqs/) — features, TCK, licensing, and LTS schedule.
- [Microsoft Build of OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/overview) — platforms, binaries, and compatibility testing.
- [Azul Zulu Migration Guide](https://docs.azul.com/core/install/migrate-to-azul-zulu) — identifying and migrating between distributions.
- [Liberica JDK](https://bell-sw.com/libericajdk/) — Liberica variants and platforms.
- [IBM Semeru Runtimes Release Notes](https://www.ibm.com/support/pages/semeru-runtimes-release-notes) — OpenJDK/OpenJ9 components and editions.
- [GraalVM Native Image](https://www.graalvm.org/latest/reference-manual/native-image/) — building native executables and limitations to consider.
- [Oracle Java SE Licensing FAQ](https://www.oracle.com/java/technologies/javase/jdk-faqs.html) — Oracle JDK terms by version and update release.

Support policies, available versions, and licenses are subject to change. When installing or deploying, verify against the official documentation at the time of downloading the binary and record the exact terms applicable to the build in use.
