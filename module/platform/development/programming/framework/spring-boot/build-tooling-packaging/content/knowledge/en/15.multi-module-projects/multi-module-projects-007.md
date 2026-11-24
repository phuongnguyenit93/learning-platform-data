# Why Shared Libraries Need an Ordinary JAR Instead of a Boot JAR

## 1. Goal

In a multi-module Spring Boot project, `shared-core` is the shared library, while `web-app` is the standalone runnable program:

~~~text
multi-module-demo/
├── shared-core/       -> library JAR, imported onto the classpath by other projects
└── web-app/           -> Spring Boot executable JAR, run with java -jar
    └── depends on shared-core
~~~

Because the two modules have **different usage contracts**, you should not package every module as a Spring Boot executable JAR. When a Spring Boot application needs to share classes with other projects, the Spring Boot documentation recommends **moving the shared code into an independent module** and having that module produce an ordinary JAR.

After this lesson, you will understand why at the classpath and archive-structure levels, how to configure a Maven reactor or Gradle multi-project build for both module types, how to verify with a Java 17 consumer and an HTTP application, the classifier option when you cannot yet split modules, the publishing workflow, and common errors.

Examples use Java 17, Spring Boot 4.1.2, and Maven 3.6.3+ or Gradle 8.14+ (8.x line)/9.x per the Spring Boot 4.1.2 system requirements documentation.

## 2. The Most Important Mechanism: Class Paths Inside the Archive

### Ordinary JAR for Libraries

Suppose `shared-core`'s public class is named `dev.example.core.GreetingFormatter`. When built with Maven `jar:jar` or Gradle `jar`, `shared-core-1.0.0.jar` normally has the structure:

~~~text
shared-core-1.0.0.jar
├── META-INF/MANIFEST.MF
└── dev/example/core/GreetingFormatter.class
~~~

When another project runs `javac -cp shared-core-1.0.0.jar`, the Java compiler locates classes by package name, meaning entry `dev/example/core/GreetingFormatter.class` **relative to the JAR root**. No Boot launcher is needed, and no Spring runtime is needed if this API is plain Java.

### Spring Boot Executable JAR for Applications

When the Spring Boot Maven Plugin `repackage` or Gradle `bootJar` builds an executable archive, its layout is typically:

~~~text
web-app-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/dev/example/app/WebApplication.class
    └── lib/
        ├── shared-core-1.0.0.jar
        ├── spring-boot-...jar
        └── ...
~~~

The Spring Boot launcher knows how to add `BOOT-INF/classes` along with nested archives under `BOOT-INF/lib` to the classpath when **launching `java -jar`**. However, the standard Java compiler/classloader does not automatically treat `BOOT-INF/classes` as a package root when you put an executable archive onto the **dependency classpath** of another application; nor does it automatically load nested JARs inside `BOOT-INF/lib`.

**Consequence:** a Boot JAR can contain the exact class while a consumer still encounters `package ... does not exist` or `ClassNotFoundException`. That is the wrong **artifact type**, not missing Java source code.

| Criterion | Ordinary Library JAR | Boot Executable JAR |
| --- | --- | --- |
| Purpose | Import and use as a dependency | Run a program |
| Class path | `dev/example/...` directly at root | `BOOT-INF/classes/dev/example/...` |
| Dependencies | Managed via POM/Gradle metadata | Nested JARs in `BOOT-INF/lib` |
| Entry point | No `Main-Class` required | Boot loader + `Start-Class` |
| Right verification test | Consumer `javac -cp` | `java -jar` and smoke test |
| Interchangeable? | No | No |

**Note:** a library using Spring Framework can still be an ordinary JAR. Adding a starter or BOM does not force repackaging: it is specifically the Maven plugin execution or Gradle `bootJar` that determines the executable layout.

## 3. Multi-Module Architecture Should Have Clear Responsibilities

~~~text
                service X      service Y
                    \           /
                     \         /
                 shared-core.jar     [ordinary]
                       ^
                       |
                 web-app module
                       |
                       v
                 web-app.jar         [Boot executable]
                    BOOT-INF/classes
                    BOOT-INF/lib/shared-core.jar
~~~

- `shared-core`: reusable public APIs, DTOs, domain rules, helpers, and business logic. Does not need `@SpringBootApplication` or a `main` method.
- `web-app`: application entry point, controllers, runtime configuration, and dependency on `shared-core`.
- Other consumers: declare `shared-core` as a Maven/Gradle dependency, **never grab `web-app.jar`** to compile against.
- Unidirectional dependency graph: `web-app → shared-core`. Avoid `shared-core` depending back on `web-app`.

Splitting this way gives `core` its own release cycle, Java compatibility, tests, and API contract. Executable apps still consume `core` because the Spring Boot launcher loads the ordinary core JAR from `BOOT-INF/lib`.

## 4. Complete Maven Reactor Example

Source structure:

~~~text
multi-module-demo/
├── pom.xml
├── shared-core/
│   ├── pom.xml
│   ├── src/main/java/dev/example/core/GreetingFormatter.java
│   └── src/test/java/dev/example/core/GreetingFormatterTest.java
├── web-app/
│   ├── pom.xml
│   └── src/main/java/dev/example/app/WebApplication.java
└── consumer/ConsumerMain.java
~~~

### Root `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>multi-jar-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-core</module>
        <module>web-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

The root serves solely as aggregator and parent with `pom` packaging. **Do not activate the Spring Boot Maven Plugin in the root's `<build><plugins>`**, because the plugin could be inherited by `core`. The starter parent already pre-configures the plugin version and `repackage` execution; the app module activates it when needed.

### `shared-core/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>multi-jar-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Note:** do not declare `spring-boot-maven-plugin` in `core`. Maven still runs Java compilation, Surefire unit tests, and `maven-jar-plugin:jar` to produce the **ordinary `shared-core-1.0.0.jar`**. The `spring-boot-starter-test` dependency stays in `test` scope and does not turn the main artifact into an executable.

### `web-app/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>multi-jar-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>web-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>shared-core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

**Only the app activates the Spring Boot Maven Plugin.** The Boot parent already configures the `repackage` execution in the `package` phase; when the plugin is declared in the app, Maven builds an executable app JAR. `web-app → shared-core` is an ordinary dependency, guiding the reactor to build `core` before `app`.

If using a corporate parent/BOM instead of the starter parent, you must manage the Boot plugin version and bind the `repackage` goal to `package` **only in the app module**; importing the `spring-boot-dependencies` BOM does not bring plugin executions.

## 5. Java 17 Code for the Exercise

### `shared-core/src/main/java/dev/example/core/GreetingFormatter.java`

~~~java
package dev.example.core;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

`shared-core` does not need `main()`. `greet("Mai")` returns `Hello, Mai`.

### `shared-core/src/test/java/dev/example/core/GreetingFormatterTest.java`

~~~java
package dev.example.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingFormatterTest {
    @Test
    void greetFormatsName() {
        assertEquals("Hello, Mai", GreetingFormatter.greet("Mai"));
    }
}
~~~

This test proves the logic works on the test classpath; it does not yet prove the final JAR has the right layout for a compiler.

### `web-app/src/main/java/dev/example/app/WebApplication.java`

~~~java
package dev.example.app;

import dev.example.core.GreetingFormatter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(name = "name", defaultValue = "world") String name) {
        return GreetingFormatter.greet(name);
    }
}
~~~

The app exposes an HTTP endpoint. This Java class compiles because Maven `web-app` declares a dependency on `shared-core`; there is no need to copy `core` code into the `app` module.

### `consumer/ConsumerMain.java`

~~~java
package dev.consumer;

import dev.example.core.GreetingFormatter;

public class ConsumerMain {
    public static void main(String[] args) {
        System.out.println("CONSUMER=" + GreetingFormatter.greet("Mai"));
    }
}
~~~

`ConsumerMain` is an independent Java program placed outside both modules. We will deliberately put only the **ordinary core JAR** onto the compiler classpath to prove the artifact behaves like a library.

## 6. Build Maven, Verify the Library, and Run the Application

At root:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Expected output:

~~~text
shared-core/target/shared-core-1.0.0.jar
web-app/target/web-app-1.0.0.jar
web-app/target/web-app-1.0.0.jar.original   # usually the original JAR before repackage
~~~

- `shared-core-1.0.0.jar`: ordinary library JAR.
- `web-app-1.0.0.jar`: Boot executable JAR.
- The app's `.jar.original`, if present, is not the file to deploy.

### 6.1. Inspect Archives

~~~bash
jar tf shared-core/target/shared-core-1.0.0.jar
jar tf web-app/target/web-app-1.0.0.jar
~~~

In `core`, you should find:

~~~text
dev/example/core/GreetingFormatter.class
~~~

In `app`, you should find:

~~~text
BOOT-INF/classes/dev/example/app/WebApplication.class
BOOT-INF/lib/shared-core-1.0.0.jar
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

The core JAR **must not** contain `BOOT-INF/classes`. If you see a Boot layout in `core`, check plugin inheritance and misbound executions.

### 6.2. Java 17 Consumer Test on Linux/macOS

~~~bash
mkdir -p target/consumer-classes
javac -cp shared-core/target/shared-core-1.0.0.jar -d target/consumer-classes consumer/ConsumerMain.java
java -cp target/consumer-classes:shared-core/target/shared-core-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Exact stdout:**

~~~text
CONSUMER=Hello, Mai
~~~

On Windows PowerShell, the classpath separator is `;`. You can run one command per line:

~~~powershell
New-Item -ItemType Directory -Force target\consumer-classes | Out-Null
javac -cp shared-core\target\shared-core-1.0.0.jar -d target\consumer-classes consumer\ConsumerMain.java
java -cp "target\consumer-classes;shared-core\target\shared-core-1.0.0.jar" dev.consumer.ConsumerMain
~~~

Do not include `shared-core/target/classes` in `-cp`; doing so would hide errors if the JAR were packaged improperly.

### 6.3. Run the App via Boot Executable

First terminal:

~~~bash
java -jar web-app/target/web-app-1.0.0.jar --server.port=18080
~~~

Once the server starts, second terminal:

~~~bash
curl -fsS 'http://127.0.0.1:18080/greeting?name=Mai'
~~~

**Exact HTTP response body:**

~~~text
Hello, Mai
~~~

This is the HTTP response body, not the complete stdout of the `java -jar` process because Spring Boot may print other logs. After verifying, stop the server with `Ctrl+C`.

**Two independent checks:** consumer compilation proves the library JAR works; app `java -jar` and HTTP prove the executable JAR carries the nested core dependency. Unit tests in `core` cannot substitute for either check.

## 7. Gradle Multi-Project: Do Not Apply the Boot Plugin to `shared-core`

Reusing the exact Java source from section 5, replace the build configuration with four Gradle files.

### `settings.gradle`

~~~groovy
rootProject.name = 'multi-module-demo'
include 'shared-core', 'web-app'
~~~

### Root `build.gradle`

~~~groovy
allprojects {
    group = 'dev.example'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}
~~~

### `shared-core/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:4.1.2'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**The library applies only `java-library`**, not the Boot plugin. The `jar` task produces an ordinary JAR with classes at the root package path; JUnit test dependencies stay exclusively on the test classpath.

### `web-app/build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:4.1.2'
    )
    implementation project(':shared-core')
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
}

tasks.named('bootJar') {
    mainClass = 'dev.example.app.WebApplication'
}
~~~

Only the app applies the Boot plugin. The `implementation project(':shared-core')` dependency links the right project, causing the core JAR to be built and packaged into `BOOT-INF/lib` of the app when `bootJar` runs.

### Build and Verify Gradle

~~~bash
./gradlew clean build
jar tf shared-core/build/libs/shared-core-1.0.0.jar
jar tf web-app/build/libs/web-app-1.0.0.jar
~~~

Output:

~~~text
shared-core/build/libs/shared-core-1.0.0.jar   # ordinary JAR
web-app/build/libs/web-app-1.0.0.jar           # executable Boot JAR
web-app/build/libs/web-app-1.0.0-plain.jar     # may also include the app's ordinary JAR
~~~

The Boot Gradle plugin typically assigns the `plain` classifier to the app's `jar` task to avoid colliding with `bootJar`'s output. **Do not confuse the app's plain JAR with the library module**; consumers need the `shared-core` JAR.

To test the consumer against the Gradle output:

~~~bash
mkdir -p build/consumer-classes
javac -cp shared-core/build/libs/shared-core-1.0.0.jar -d build/consumer-classes consumer/ConsumerMain.java
java -cp build/consumer-classes:shared-core/build/libs/shared-core-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Exact stdout:** `CONSUMER=Hello, Mai`.

Run the app and test HTTP:

~~~bash
java -jar web-app/build/libs/web-app-1.0.0.jar --server.port=18080
~~~

In another terminal:

~~~bash
curl -fsS 'http://127.0.0.1:18080/greeting?name=Mai'
~~~

The response body is `Hello, Mai`.

**Different tasks:** `:shared-core:jar` only packages the library; `:web-app:bootJar` packages the app without guaranteeing all tests run. Run `./gradlew clean build` to execute configured verification tasks.

## 8. When Publishing, Which Artifact Should Other Modules Consume?

Maven consumers use:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>shared-core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Gradle consumers use:

~~~groovy
dependencies {
    implementation 'dev.example:shared-core:1.0.0'
}
~~~

**Do not** use the executable `web-app` as a dependency simply because it contains the nested core JAR.

To install `core` into the local Maven repository:

~~~bash
mvn -pl shared-core -am install
~~~

This is a local `install`, not a remote `deploy`. If building the app module standalone before `core` is in the local repository, use the reactor `mvn -pl web-app -am verify` or install/resolve `core` appropriately.

With Gradle, publish the ordinary library using `maven-publish` and the Java component in the **`shared-core` module**, for example with this fragment:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

You must add `id 'maven-publish'` to `core`'s existing `plugins` block and run `./gradlew :shared-core:publishToMavenLocal`. The fragment above will not work unless `maven-publish` is applied. Remote publishing requires separate repository and credentials configuration.

After publishing, QA should pull `core` back from the repository in an independent consumer and genuinely compile it. Do not rely solely on checking files inside `target` or `build/libs`.

## 9. When You Cannot Yet Split Modules: Classifier as a Temporary Option

For a single module that contains both a public API and an executable application, you can produce **two separate artifacts** instead of letting the Boot archive overwrite the ordinary library JAR.

**Maven** using starter parent: customize the `repackage` execution with classifier `exec`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

This is a fragment inside `build/plugins`. When no source artifact carries the `exec` classifier, Maven preserves the ordinary `artifact-1.0.0.jar` and additionally produces the executable `artifact-1.0.0-exec.jar`. If not using starter parent, you must declare the plugin version and `repackage` goal execution in `package` explicitly.

**Gradle:** keep `jar` without a classifier, and give `bootJar` classifier `exec`:

~~~groovy
tasks.named('jar') {
    archiveClassifier = ''
}
tasks.named('bootJar') {
    archiveClassifier = 'exec'
}
~~~

Classifiers solve **giving the two archives different layouts**. However, the same module still shares the same dependency metadata; consumers needing only the API may inadvertently pull in web-stack dependencies. When a library has multiple consumers, splitting `shared-core`/`web-app` remains the cleaner design.

## 10. Common Errors and Diagnosis

| Error | Cause to Inspect | Fix |
| --- | --- | --- |
| Core build reports missing main class | Boot plugin ran by mistake on library | Activate Boot Maven/Gradle plugin only on app |
| Core JAR has `BOOT-INF/classes` | Repackage overwrote ordinary artifact | Inspect effective POM / task graph; fix core packaging |
| Consumer cannot import `GreetingFormatter` | Using Boot JAR or wrong version | Check `jar tf` and consumer compile classpath |
| App `NoClassDefFoundError` for core | App missing dependency or nested JAR | Check `BOOT-INF/lib/shared-core-...jar` |
| Maven app cannot resolve `shared-core` | Built app alone while core is missing from repo | Use `-pl web-app -am` or install/publish core |
| Maven root `pom` tries to repackage | Boot plugin enabled at root and inherited | Enable only in app; use `pluginManagement` if needed |
| Gradle core creates `bootJar` | Applied Boot plugin across all subprojects | Use `java-library` in core |
| Gradle app also has `-plain.jar` | `jar` and `bootJar` are two tasks | Deploy exact `bootJar` output |
| Tests pass yet published core is broken | Tests ran on classes, not inspecting JAR | Add `javac -cp core.jar` consumer gate |
| App runs yet HTTP fails | Port/config/route or runtime dependency | Run HTTP smoke test checking status and body |
| Core compiler target higher than runtime | Mismatched toolchain/release | Use compatible Java targets across modules |
| Library pulls unwanted web dependencies | Core/app not split or bad metadata | Split modules; manage API/implementation deps |

**Investigation sequence:** identify module → artifact identity → archive layout → dependency graph → consumer compile → executable runtime → repository metadata. Never fix classpath layout issues by arbitrarily changing the Java version.

## 11. QA Gates for Multi-Module Projects

| Gate | PASS Evidence |
| --- | --- |
| Library layout | `shared-core.jar` has `dev/example/core/GreetingFormatter.class` at root, no `BOOT-INF/classes` |
| Library API | `javac -cp shared-core.jar` succeeds; `ConsumerMain` prints `CONSUMER=Hello, Mai` |
| Core tests | `GreetingFormatterTest` actually ran, 0 failures/errors |
| App archive | `web-app.jar` has `BOOT-INF/classes`, `BOOT-INF/lib/shared-core-1.0.0.jar`, and launcher |
| App runtime | `java -jar web-app.jar` starts on the target JDK |
| App smoke | HTTP `/greeting?name=Mai` returns 200 and body `Hello, Mai` |
| Publish | Consumer downloads `dev.example:shared-core:1.0.0` from repository and compiles |
| Build lineage | Both modules from the same commit/version; core was not accidentally repackaged |

**Important:** `BUILD SUCCESS` alone does not prove the library artifact has the right layout; nor does a running app prove consumers can import `core` from a repository. Both the **library contract** and the **executable contract** must be verified.

## 12. Practice Questions

**1. Why is a Boot executable JAR unsuitable as a dependency?** Because classes sit in `BOOT-INF/classes` and nested dependencies sit in `BOOT-INF/lib`, whereas standard compilers/classloaders search for classes starting at the root of a classpath entry.

**2. Must a core library using Spring Framework be a Boot JAR?** No. An ordinary JAR can contain Spring classes as long as dependencies and configuration are properly managed.

**3. Does a Maven root inheriting the Boot starter parent make core automatically repackage?** No, as long as the root does not activate the plugin and core does not declare it. Only the app module should activate the Boot Maven Plugin.

**4. Which plugin should Gradle core apply?** `java-library` (or `java`), not `org.springframework.boot`.

**5. Why does a core JAR need a consumer compile test?** Unit tests may run against compiled classes before packaging; a consumer test proves the final JAR has the right package layout.

**6. If the app contains core as a nested JAR, why does the app still run?** The Spring Boot launcher builds the runtime classpath from `BOOT-INF/lib` during `java -jar`.

**7. When modules cannot yet be split, what does a classifier solve?** It separates the plain JAR and exec JAR; it does not separate the dependency graph or API coupling.

**8. Does `mvn install` mean the library was published remotely?** No. Install targets the local repository; deploy is what publishes remotely per configuration.

## 13. Final Checklist

- [ ] Identify library modules and standalone runnable modules.
- [ ] Core produces only an ordinary JAR; only the app uses Boot repackage/bootJar.
- [ ] Core classes reside at Java package paths at the root of the ordinary JAR.
- [ ] App Boot JAR contains the loader, `BOOT-INF/classes`, and nested core JAR.
- [ ] Root Maven/Gradle does not apply the Boot plugin across all modules.
- [ ] App depends on core unidirectionally.
- [ ] Core unit tests and consumer `javac -cp` both PASS.
- [ ] App `java -jar` and HTTP smoke test both PASS.
- [ ] Java toolchain/release is compatible across modules.
- [ ] Downstreams use core's coordinates, not executable `web-app`.
- [ ] Publication metadata points to the ordinary artifact.
- [ ] Inspect actual outputs and reports, not only the build exit code.

**Remember:** `shared-core.jar` is a **classpath input for consumers**; `web-app.jar` is an **input for `java -jar`**. Splitting library and app into two modules preserves both contracts and prevents Boot packaging from breaking shared code reusability.

## 14. Official Documentation

1. [Spring Boot — Use a Spring Boot Application as a Dependency](https://docs.spring.io/spring-boot/how-to/build.html)
2. [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
3. [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
4. [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
5. [Spring Boot Gradle Plugin — Packaging Executable and Plain Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
6. [Apache Maven — Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
7. [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
8. [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
9. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)