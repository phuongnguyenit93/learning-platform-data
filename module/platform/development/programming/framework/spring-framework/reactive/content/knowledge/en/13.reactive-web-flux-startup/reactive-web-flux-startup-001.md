# Preparing Compatible Spring, Reactor, and Server Library Versions

## 1. Goal: choose a set of versions that works as one system

A Spring WebFlux application usually involves several library layers working together:

- **Java/JDK**: the runtime version, compiler, and bytecode target.
- **Spring Boot** (if used): configuration, auto-configuration, starters, and a dependency list that has been tested together.
- **Spring Framework**: Spring WebFlux, codecs, HTTP abstractions, and dependency injection.
- **Project Reactor**: Reactor Core, Mono, Flux, Scheduler, and operators.
- **Reactor Netty** (if chosen): an asynchronous HTTP/TCP client and server based on Netty.
- **Netty**: transport, codecs, resolvers, handlers, and native transport when needed.
- **Alternative servers**: Tomcat or Jetty can also run WebFlux through a suitable non-blocking adapter.

These components have **their own release cycles and version numbering**. You cannot assume that Reactor Core must have the same major number as Spring Framework, or that Reactor Netty must have the same version number as Reactor Core. What you need to guarantee is a **combination of versions that are supported and tested together**.

For an application that uses Spring Boot, the most stable approach is to choose a Boot release that fits the target JDK and let **Spring Boot dependency management (BOM)** manage the versions of Spring Framework, Reactor, Reactor Netty, Netty, and related libraries. Override a version only when there is a specific compatibility or security reason, and only after checking the dependency graph and running tests.

## 2. Dependency diagram and responsibilities

~~~text
Java application
    |
    +-- Spring Boot (if used)
    |      +-- dependency management / BOM
    |      +-- auto-configuration and starters
    |
    +-- Spring Framework
    |      +-- spring-webflux
    |      +-- codec / HTTP handler / WebClient
    |
    +-- Project Reactor
    |      +-- reactor-core: Mono, Flux, Scheduler
    |      +-- reactor-test: StepVerifier
    |
    +-- Runtime HTTP server (choose one)
            |
            +-- Reactor Netty
            |      +-- Netty transport / codec / resolver
            |
            +-- Tomcat (Servlet non-blocking adapter)
            |
            +-- Jetty (Servlet non-blocking adapter)
~~~

**Spring WebFlux is a reactive web framework, not a standalone HTTP server.** The Spring Boot WebFlux starter automatically assembles the required components and uses Reactor Netty by default; Tomcat and Jetty are also valid choices. Therefore, you must check both the server version and its underlying dependencies.

One way to read a dependency tree:

- `spring-boot-starter-webflux` is the application-level dependency.
- `spring-webflux` is a Spring Framework module.
- `reactor-core` is the library that runs Mono/Flux.
- `reactor-netty-http` is the HTTP runtime based on Reactor Netty.
- `io.netty:*` are the Netty modules at the network layer.

If the dependency graph contains two versions of `reactor-core` or several Netty versions because of overrides/transitive dependencies, you need to determine which version is actually selected and why before deploying.

## 3. Understand the version line before choosing dependencies

### 3.1. Choose Java first

Java is the baseline requirement for both the build and the runtime:

1. The JDK used on the developer machine.
2. The JDK that the Maven/Gradle daemon actually uses.
3. The Java release/bytecode target of the project.
4. The JRE/JDK in the container or production server.
5. The minimum Java version of third-party libraries.

For example, the compiler may produce Java 21 bytecode while production only has Java 17. In that case the application may hit `UnsupportedClassVersionError` at startup, even though the build on the developer machine succeeded.

At the time of writing, the Spring Boot 4.1.2 documentation specifies **Java 17 as the minimum**, supports up to Java 27, and requires **Spring Framework 7.0.10 or later**. Maven is supported from 3.6.3; Gradle 8.x needs at least 8.14, or you can use Gradle 9.x. Third-party dependencies may require a higher Java version. Read the System Requirements page for the exact Boot version you chose instead of applying the numbers from an older release.

### 3.2. Version lines that must go together

| Platform | Version line to cross-check | How to decide |
| --- | --- | --- |
| Spring Boot 4.1.2 | Java 17+; Spring Framework 7.0.10+ | Use the Boot BOM for Spring and Reactor libraries |
| Spring Boot 3.x | Java 17+; Spring Framework 6.x depending on the minor release | Use the BOM of the exact Boot 3.x release you chose; do not mix in Boot 4 dependencies |
| Spring Framework without Boot | Spring Framework BOM and the Java requirements of the corresponding release | Manage Reactor and the server runtime yourself according to each project's compatibility documentation |
| Reactor Core | Independent version following the Reactor release train | Use the version managed by the platform's BOM |
| Reactor Netty and Netty | Independent versions, with compatibility relationships between modules | Keep the Netty modules in sync according to the BOM/Reactor Netty recommendations |

This table shows **how to choose a version line**, not a rule that any patch releases can be combined freely. With Spring Boot, the Managed Dependency Coordinates table of the Boot release itself is the source that determines the specific versions of `spring-webflux`, `reactor-core`, `reactor-netty-http`, and Netty.

**Do not take the latest version of each library individually and mix them into an application that uses an older Boot.** A newer Reactor Netty release may require a different Reactor Core or Netty than the one the current Boot release manages.

### 3.3. What is a BOM?

A BOM (Bill of Materials) is a POM used to manage the versions of related dependencies. When a project imports a BOM, declared dependencies **may not need their own version**; Maven/Gradle takes the version from dependency management.

Spring Boot provides the `spring-boot-dependencies` BOM. This BOM manages the Spring Framework modules, Reactor, Reactor Netty, Netty, and many other libraries according to a set of versions that were chosen together.

Distinguish between:

- **Dependency declaration**: which libraries the project actually needs.
- **Dependency management**: which version is chosen when a library is declared.
- **Transitive dependency**: a library pulled in through another dependency.
- **Version override**: the project deliberately replaces the BOM's default version.
- **Dependency convergence**: the same artifact is not selected in multiple conflicting versions within the graph.

Importing a BOM does not automatically add all libraries to the classpath. It provides version rules; the project still declares the starters/modules it needs.

## 4. Preferred approach when the project uses Spring Boot

For a new WebFlux application, start with these decisions:

1. Choose a Spring Boot release that still fits the support policy and the JDK of your environment.
2. Set the JDK/toolchain and bytecode target according to production requirements.
3. Add `spring-boot-starter-webflux`.
4. Let the Boot BOM choose Spring Framework, Reactor Core, Reactor Netty, and Netty.
5. Choose a different server only when there is a clear deployment requirement.
6. Check the dependency tree, build, and run integration tests.

**You do not need to declare a separate version for `spring-webflux`, `reactor-core`, and `reactor-netty-http`** when Boot already manages these dependencies. Declaring them manually can easily create a combination that deviates from Boot's tested set of dependencies.

## 5. Maven example: Spring Boot 4.1.2 + WebFlux + default Reactor Netty

The following example uses **Java 17+**, **Maven 3.6.3+**, and Spring Boot 4.1.2. Version 4.1.2 is an illustrative version based on the current documentation at the time of writing; for a real project, choose a patch release that your organization supports and that includes security updates.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>webflux-version-check</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Only the **Spring Boot parent** has a version here. The WebFlux starter does not declare a version; transitive dependencies such as Spring Framework, Reactor Core, and Reactor Netty are managed through the Boot BOM.

### Application example

Create the file `src/main/java/com/example/compat/WebfluxVersionCheckApplication.java`:

~~~java
package com.example.compat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxVersionCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxVersionCheckApplication.class, args);
    }
}
~~~

Create the file `src/main/java/com/example/compat/ProbeController.java`:

~~~java
package com.example.compat;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ProbeController {

    @GetMapping("/ping")
    public Mono<String> ping() {
        return Mono.just("webflux-ready");
    }

    @GetMapping("/numbers")
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
~~~

Start up:

~~~bash
mvn -version
java -version
mvn clean package
mvn spring-boot:run
~~~

In another terminal, call the endpoints:

~~~bash
curl -s http://localhost:8080/ping
curl -s http://localhost:8080/numbers
~~~

Expected response body:

~~~text
webflux-ready
[1,2,3]
~~~

The result shows that the classpath is sufficient to run Spring WebFlux and Reactor. However, **a working endpoint does not prove that the whole dependency graph is safe for production**; you still need to inspect the dependency tree, run tests, and check the real runtime.

## 6. Gradle example: let the Spring Boot plugin manage dependencies

If you use the Gradle Groovy DSL, the equivalent configuration is:

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

When you apply the dependency management plugin together with the Spring Boot plugin, Boot automatically imports the corresponding BOM; managed dependencies can be declared without a version.

If you use native Gradle BOM support, you can declare the platform of the Spring Boot dependency BOM in dependencies:

~~~groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

You only need to choose **one clear way to manage versions** and verify the resolution result. Avoid using several BOMs with conflicting constraints while also forcing individual versions on each artifact without a plan.

Check the dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty --configuration runtimeClasspath
~~~

`dependencyInsight` shows the selected dependency, the paths that pull it in, and why a version was preferred.

## 7. Choosing Reactor Netty, Tomcat, or Jetty?

### 7.1. When to keep the default Reactor Netty?

`spring-boot-starter-webflux` includes Reactor Netty as the reactive server by default. This is a suitable choice for most WebFlux applications when:

- You want a non-blocking runtime based on Netty.
- You want to share the Reactor ecosystem between the server and WebClient.
- There is no deployment constraint that requires a different Servlet container.
- You want to keep the starter configuration and version management simple.

Boot can create Reactor Netty resources for the server and share some resources with the auto-configured WebClient under suitable conditions. Do not arbitrarily create additional client/server resource pools unless you understand their lifecycle and the goal of the configuration.

### 7.2. When to use Tomcat or Jetty?

Spring WebFlux has adapters for Servlet non-blocking I/O, so it can run on **Tomcat or Jetty**. This is useful if the deployment environment has already standardized on a container, or has its own operational requirements or monitoring tools.

However, using Tomcat/Jetty with WebFlux **does not mean the application becomes Spring MVC**. The programming model is still WebFlux; how the server reads/writes the network and integrates with the HTTP handler varies with the runtime.

### 7.3. Replacing Reactor Netty with Tomcat in Maven

If you want to use the Tomcat reactive runtime, exclude the Reactor Netty starter and add the Boot-managed Tomcat starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-reactor-netty</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
</dependency>
~~~

For Jetty, replace the Tomcat dependency with the corresponding Jetty starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

This is a **replacement dependency configuration fragment**, not a complete pom.xml. Keep the versions managed by the Boot BOM. After changing the server, run `mvn dependency:tree` again to make sure Reactor Netty is no longer pulled in as the server runtime unintentionally, and also check whether other dependencies may still need Reactor Netty as an HTTP client.

**Do not add Reactor Netty, Tomcat, and Jetty all together as three default servers** if the application only needs one server. Having multiple runtimes present can make auto-configuration unpredictable or cause the application to pull in unnecessary dependencies.

### 7.4. Avoid confusing MVC and WebFlux

Spring MVC and Spring WebFlux can coexist in the Spring ecosystem, but the application needs to define its **web application type** clearly. Spring Boot prefers MVC when both the MVC and WebFlux starters are present in some default configurations; a common case is an MVC application that adds WebFlux only to use WebClient.

If the goal is a reactive server:

- Keep the WebFlux dependency and a suitable reactive server.
- Remove the MVC starter if it is not needed.
- If there is a reason to keep both, configure the application type explicitly, for example `spring.main.web-application-type=reactive`, and verify the auto-configuration at runtime.

Do not conclude that the application is running WebFlux just because the source code contains `Mono` or `Flux`. Check the startup logs, the web application type, and the actual runtime server.

## 8. How to manage versions without Spring Boot?

A plain Spring Framework application can still use WebFlux, Reactor, and a compatible HTTP server. Without the Boot BOM, the development team has to manage the version lines itself.

Approach:

1. Choose a **Spring Framework release** and check the Java requirements and supported server runtimes in that release's documentation.
2. Use the Spring Framework BOM so that Spring modules such as `spring-webflux` and `spring-web` share the same version line.
3. Choose **Reactor Core** according to a Reactor release train compatible with the application; `reactor-test` must follow the same version line as Reactor Core.
4. Choose **Reactor Netty** according to the release documentation/BOM of Reactor Netty itself and ensure the Netty modules are managed consistently.
5. If you choose Tomcat/Jetty, check the Servlet API, the Jakarta namespace, and the requirements of the server version.
6. Run real integration tests with the final JDK, server, and dependency graph.

There is no universal rule like "Spring 7 means Reactor must be 7". The projects have their own release cycles. Use the official BOMs and the support table of each release to determine the specific combination, instead of assembling versions by major number.

## 9. Checking the versions Maven actually resolves

A declaration in pom.xml is only an **input requirement**; the version that actually runs must be confirmed from the effective POM and the dependency graph.

### 9.1. See which JDK Maven is using

~~~bash
java -version
javac -version
mvn -version
~~~

`mvn -version` shows the Java that the Maven process uses. If Maven runs on a different JDK from the `java` in your terminal, unify the toolchain/IDE/CI to avoid "it builds on my machine".

### 9.2. View the effective POM

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

The effective POM is the result after Maven merges the parent POM, properties, dependency management, and plugin configuration. Use it to see which versions the Boot BOM actually brings in.

### 9.3. View the dependency tree

~~~bash
mvn dependency:tree -Dverbose
~~~

You can filter the important groups:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework:*,io.projectreactor:*,io.projectreactor.netty:*,io.netty:*
~~~

Focus on checking:

- Only one suitable version of `spring-webflux` and the related Spring modules.
- `reactor-core` and `reactor-test` are on the same version line.
- `reactor-netty-core` and `reactor-netty-http` are on the same Reactor Netty version line.
- The `io.netty` modules are not forced into conflicting versions.
- No old dependency pulls a Spring/Reactor module back in unintentionally.
- No exclusion mistakenly removes a required runtime library.

The keyword `omitted for conflict` in the dependency tree indicates that Maven dropped a dependency path because it chose a different version; this is not always an error, but you need to understand why that version was chosen.

### 9.4. Checking the Gradle runtime classpath

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
~~~

When Gradle uses a version catalog, platform, or constraints, you need to check the **final resolved version**, not just read the version alias in `libs.versions.toml`.

## 10. Signs of an incompatible version set

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Bytecode compiled with a newer Java than the runtime JDK | Compare `mvn -version`, the toolchain, the release target, and the container JRE |
| `NoSuchMethodError` | The runtime loads an old version of a class even though it was compiled against a newer version | Dependency tree, BOM overrides, and transitive libraries |
| `NoClassDefFoundError` / `ClassNotFoundException` | A module is missing or a dependency was wrongly excluded | Runtime dependency tree, packaging, and classpath |
| `LinkageError` | Modules of the same family are not binary compatible | Check the resolved Spring/Reactor/Netty versions |
| Application starts as MVC by mistake | An MVC starter is present together with WebFlux, or the web application type is wrong | Starter list, application type, and auto-configuration |
| Reactive server cannot be created | The server starter was excluded or no suitable runtime is present | Dependency tree, auto-configuration log |
| Netty method/class errors | Netty modules have mismatched versions or the native transport is incompatible | The `io.netty` artifacts, classifier, and OS/architecture |
| Tests compile but production fails | The test classpath differs from the runtime or the container uses a different JDK | Run integration tests on the same image/JDK/dependency profile |

A stack trace with `NoSuchMethodError` does not mean the method was just removed from the code you are writing. Usually the compiler saw a version that has that method, but the runtime loaded a different version. So you need to read the dependency tree and check the packaged artifacts.

### 10.1. Do not override individual Netty modules by yourself

Reactor Netty uses many Netty modules: transport, codec, handler, resolver, and others. If you only override `netty-codec-http` but leave `netty-handler` and `netty-transport` at a different version, binary errors can appear that are very hard to trace.

When you find a security vulnerability or a bug that requires updating Netty:

1. Determine whether the Spring Boot version you are using has a suitable patch.
2. Check the Netty version managed by the Boot BOM.
3. Read the upgrade recommendations of Spring Boot/Reactor Netty.
4. Override only the recommended group of dependencies in sync, and document the reason.
5. Run integration tests, and check TLS, HTTP/2, WebClient, and the server runtime if the application uses them.

Do not use `netty-all` or a single new Netty module as a "quick fix" before checking the dependency graph. Adding one artifact does not by itself make all the Netty modules in the application compatible.

## 11. A safe version upgrade process

When you need to upgrade Spring/Boot/Reactor:

**Step 1 — record the current baseline**

- JDK and Maven/Gradle.
- Spring Boot or Spring Framework version.
- Spring WebFlux version.
- Reactor Core, Reactor Test, Reactor Netty, and Netty.
- The HTTP server in use.
- Dependency overrides and exclusions.

**Step 2 — choose the target release line**

- Check the System Requirements.
- Check the support status and security fixes.
- Check the Java, Jakarta, and Servlet requirements.
- Read the migration/release notes if upgrading across a major version.

**Step 3 — upgrade the root version**

For a Boot application, usually you only need to upgrade the Boot parent/plugin version; let the BOM change the managed dependencies. Do not edit many Spring, Reactor, and Netty versions manually at the same time.

**Step 4 — check the dependency graph**

Run the effective POM/dependency tree or Gradle dependencyInsight. Compare the artifacts that changed, and look for versions overridden by direct dependencies or another BOM.

**Step 5 — build and test layer by layer**

- Compile and unit tests.
- Application context startup.
- WebFlux integration test.
- Test WebClient calling external HTTP.
- Test serialization/codec, timeout, cancellation, and streaming.
- Test TLS, HTTP/2, or native transport if used.
- Smoke test on a container/JDK identical to production.

**Step 6 — trial deployment and observation**

Monitor startup logs, connection errors, latency, thread usage, the Netty event loop, memory, GC, and 5xx errors. Do not judge only by whether the compile succeeds.

## 12. Minimum testing for a WebFlux application

A minimum set of checks should include:

1. The application starts with the correct web application type.
2. The reactive server binds to the correct port.
3. Endpoints returning Mono and Flux are encoded correctly.
4. WebClient can connect to external services through the chosen runtime.
5. Cancellation/timeout/error handling works as expected.
6. There are no binary linkage errors when running on the correct JDK/container.
7. The production dependency graph is equivalent to the dependency graph that was tested.

Example of a manual smoke test with the application from the Maven section:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/ping
curl -i http://localhost:8080/numbers
~~~

Expect HTTP 200 and the corresponding body:

~~~text
webflux-ready
[1,2,3]
~~~

For automated tests, use WebTestClient and StepVerifier appropriate to the endpoint type; check both the HTTP status/content-type and the reactive signals. If you change the server from Reactor Netty to Tomcat/Jetty, rerun the integration tests on the **new server**, because some differences only show up with real network I/O.

## 13. Docker and the deployment environment are also part of compatibility

A project may build on JDK 21 but use a Java 17 runtime image; this is only safe if the bytecode target and all libraries are compatible with Java 17. Conversely, using a newer Java runtime image may be able to run older bytecode, but you need to test in exactly that environment.

Illustrative Dockerfile using Java 17:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/webflux-version-check-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This Dockerfile assumes the jar file with the correct name has been built in target. If you use a newer JDK/Boot or need native libraries, choose a base image that fits the JDK, OS, and CPU architecture. Netty native transport needs the right classifier/platform; do not copy a native artifact for one OS into an image for another.

Make sure CI and production use the same approach:

- Choose the runtime JDK.
- Resolve dependencies from the same pom/lockfile.
- Use the same server starter and profile.
- Do not override versions only in production without testing.
- Build the image from the artifact that has been tested.

## 14. Common mistakes

| Mistake | Risk | Correct approach |
| --- | --- | --- |
| Individually picking the latest version for Spring, Reactor, and Netty | Deviates from the tested version set | Use the Boot BOM or officially compatible BOMs |
| Declaring a version directly for every transitive dependency | Easily creates conflicts when upgrading Boot | Override only when there is justification and tests |
| Only checking the JDK on the developer machine | Maven/Gradle/CI/container may use a different JDK | Check `mvn -version`, the toolchain, and the runtime image |
| Thinking Spring WebFlux is Reactor Netty | Not understanding that the server runtime can change | Separate the WebFlux framework from the HTTP server |
| Using the WebFlux starter then adding Tomcat but forgetting to exclude Reactor Netty | Pulls in two runtimes unintentionally | Exclude the default server starter and add the replacement server |
| Having both MVC and WebFlux starters without checking the application type | Boot may auto-configure MVC | Keep the right starters or set the reactive application type deliberately |
| Overriding only one Netty module | The remaining modules may be binary-mismatched | Follow the BOM/supported version set |
| Manually adding `spring-webflux` with a version different from Boot | Spring Framework modules out of sync | Let the Boot BOM manage the Spring modules |
| Testing on Reactor Netty but running Tomcat in production | Missing adapter/server errors | Test on the actual production server |
| Only running compile/package | Does not detect runtime linkage/network problems | Startup and integration tests on the right JDK/server |
| Looking at `dependency:tree` but not reading the selected version | Not knowing which BOM or transitive dependency won | Use the verbose tree and the effective POM |
| Upgrading Boot major but keeping the old configuration as is | May run into Jakarta, starter, or API migration issues | Read the migration guide/release notes of the major |

## 15. Checklist before starting a WebFlux project

- [ ] Determine the minimum JDK and the actual JDK in production.
- [ ] Choose a Spring Boot release line that fits the support policy.
- [ ] Check the System Requirements and the migration guide.
- [ ] Use the Boot parent/plugin and BOM of the same version.
- [ ] Declare `spring-boot-starter-webflux` without a separate version.
- [ ] Choose the default Reactor Netty or explicitly specify Tomcat/Jetty.
- [ ] Avoid pulling in the MVC starter if the application must be a reactive server.
- [ ] Check the dependency tree for Spring, Reactor, Reactor Netty, and Netty.
- [ ] Check that there are no unintended version overrides/exclusions.
- [ ] Build, test, startup, and smoke test on a JDK/runtime close to production.
- [ ] Save the dependency graph and test results as the baseline for the next upgrade.

## 16. Self-check

**Question 1.** If you use Spring Boot WebFlux, do you need to declare a separate version for reactor-core?

**Usually no.** The Boot BOM manages Reactor Core; check the managed dependency coordinates of the exact Boot release.

**Question 2.** Does Spring WebFlux require Reactor Netty?

**No.** Spring Boot uses Reactor Netty by default, but Tomcat and Jetty can also run WebFlux through suitable adapters.

**Question 3.** Why shouldn't you take Spring Framework 7, the latest Reactor, and the latest Netty and mix them into a Boot 3 application?

Because each Boot release manages a set of dependencies that was chosen to be compatible. Mixing versions outside the BOM can cause binary, auto-configuration, or runtime errors.

**Question 4.** What does a `NoSuchMethodError` after upgrading dependencies usually suggest?

The compiler and the runtime may be using **two different versions** of the same class/artifact. Check the dependency tree, the effective POM, and the contents of the packaged jar.

**Question 5.** Can an application that uses WebClient but whose server is still Spring MVC have a WebFlux dependency?

Yes. WebFlux provides WebClient; adding WebFlux to use the reactive client does not automatically mean the server is running WebFlux. Check the web application type.

**Question 6.** Why does switching from Reactor Netty to Tomcat require rerunning integration tests?

Because the HTTP adapter, the transport, and the way the server integrates are different. A successful compile does not prove that the new network runtime behaves the same as the old server.

**Question 7.** If the developer JDK is 21 but the Docker runtime is 17, is it certain to run?

No. You need to ensure the bytecode target and all dependencies are compatible with Java 17, and then actually test on the runtime image.

**Question 8.** If you only want to update Netty because of a security advisory, should you change the version of just one module?

You shouldn't do it arbitrarily. Read the Boot/Reactor Netty recommendations, update the set of compatible modules, and run appropriate network/TLS tests.

## 17. Official references

- [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) — Java, Maven, Gradle, and the requirements of the exact Boot release.
- [Spring Boot Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html) — versions managed by the Boot BOM, including Spring, Reactor, Reactor Netty, and Netty.
- [Spring Boot Build Systems: Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — using dependency management with Maven and Gradle.
- [Spring Boot Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html) — WebFlux starter, application type, and reactive server auto-configuration.
- [Spring Boot Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html) — using Reactor Netty, Tomcat, or Jetty and how to switch the server starter.
- [Spring Framework WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html) — supported server APIs and the adapter architecture.
- [Project Reactor Documentation](https://projectreactor.io/docs) — Reactor Core, Reactor Test, and release documentation.
- [Reactor Netty Reference Guide](https://projectreactor.io/docs/netty/release/reference/) — client/server, transport, and Reactor Netty configuration.
- [Maven Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — view the Maven dependency graph.

**Remember:** Choose the **JDK and the Spring Boot release line first**, then let the **Boot BOM** synchronize Spring Framework, Reactor Core, Reactor Netty, and Netty. WebFlux is a framework; Reactor Netty, Tomcat, and Jetty are server runtimes you can choose from. Check the resolved versions through the effective POM/dependency tree, keep the server and JDK consistent with production, then confirm with build, startup, and integration tests in the actual deployment environment.