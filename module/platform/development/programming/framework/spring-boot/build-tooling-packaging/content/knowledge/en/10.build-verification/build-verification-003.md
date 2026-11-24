# Separating Integration Tests Using Maven Failsafe or Gradle Test Suites

## 1. Why Separate Unit Tests and Integration Tests?

In Spring Boot development, **unit tests** typically verify an isolated function or class without initializing the entire application. **Integration tests** verify collaboration across multiple components: HTTP controllers, the Spring application context, databases, message brokers, or external services. The two groups differ in execution cost and runtime preconditions.

For example, in an application with a GET /greet endpoint:

- A **unit test** directly calls GreetingService.greet(" Ada ") and checks the returned string. No HTTP server runs.
- An **integration test** starts Spring Boot on a **random port**, sends an HTTP GET /greet?name=Ada via a client, and asserts the status code and response body. It verifies wiring, request mapping, the HTTP stack, and overall handler logic.

If all tests are mixed into one task/phase, even editing a small function could trigger Spring context startup or external infrastructure. Separation enables **fast feedback**, makes it easy to group tests in CI, and clearly distinguishes unit code bugs from integration failures. However, integration tests must still run at an appropriate quality gate—never "separate" them and forget to execute them.

Two corresponding mechanisms exist:

1. **Maven:** use **maven-surefire-plugin** for unit tests and **maven-failsafe-plugin** for integration tests across Maven lifecycle phases.
2. **Gradle:** use the **JVM Test Suite plugin** (provided via the Java plugin) to declare an **integrationTest** suite with separate sources, dependencies, tasks, and reports from the default **test** suite.

**Configuration context:** Spring Boot **3.3.5**, Java **17**, Maven Surefire/Failsafe **3.5.4**, and Gradle **8.5**. This is a sample version set to illustrate syntax; it does not imply the latest release or suitability for every repository. Always verify compatibility across Gradle/Maven, Java, and Spring Boot when upgrading.

## 2. Distinguishing Test Scopes

| Characteristic | Unit test | Integration test | End-to-end (E2E) test |
| --- | --- | --- | --- |
| Target | Single isolated class/method or small group | Multiple components interacting under real contracts | A user/system flow close to production |
| Initialization level | Usually does not start Spring | May start Spring context, HTTP server, DB | May require multiple services, frontend, browser |
| Typical speed | Fast, easily repeatable | Slower, more setup | Usually slowest and most resource-heavy |
| External dependencies | Avoid | May use controlled DB/container/mock server | May use a staging environment |
| Example | GreetingServiceTest | GreetingHttpIT | UI login → place order → receive confirmation |

**File names do not automatically define test type.** A class named MyIntegrationTest can still be just a unit test, and MyIT can contain a very simple check. File names, directories, and Gradle/Maven configuration are **execution organization**, whereas "integration" depth comes from actual test behavior.

Intermediate tests like **@WebMvcTest + MockMvc** verify the MVC slice without starting a real HTTP server; they are typically lighter than **@SpringBootTest(webEnvironment = RANDOM_PORT)**. Group tests by cost and verification goal, not solely by annotation.

## 3. Diagram of Two Testing Pipelines

~~~text
                 Application source
                 src/main/java
                      |
                      v
                   compile
                      |
          +-----------+------------+
          |                        |
          v                        v
  UNIT TEST PIPELINE      INTEGRATION TEST PIPELINE
  GreetingServiceTest     GreetingHttpIT
  no HTTP server          starts Spring Boot HTTP
  runs fast               calls real endpoint via HTTP
          |                        |
          v                        v
     Surefire/test          Failsafe/integrationTest
          |                        |
          +-----------+------------+
                      |
                      v
                GATE: verify/check
                      |
                      v
                reports & artifacts
~~~

In Maven, Failsafe defaults to selecting integration tests by **class name patterns** within the standard test source root. In Gradle JVM Test Suites, we create a **separate source set** for integration tests; this isolates test dependencies and test resources as well.

**Do not confuse:** Separating *test execution* does not automatically provision databases or containers. If integration tests need real PostgreSQL, Kafka, or Redis, you must configure separate lifecycle setup/teardown and grant appropriate CI permissions.

## 4. Maven: Surefire for Unit Tests, Failsafe for Integration Tests

### 4.1. Relevant Maven Lifecycle Phases

Maven's key phases:

~~~text
validate → compile → test-compile → test → package
                                  Surefire     |
                                              v
                                    pre-integration-test
                                              |
                                         integration-test
                                           Failsafe IT
                                              |
                                    post-integration-test
                                              |
                                            verify
                                        Failsafe verify
~~~

**Surefire** normally binds to the **test** phase to run unit tests. **Failsafe** is designed specifically for integration tests:

- Goal **failsafe:integration-test** runs integration tests during the **integration-test** phase.
- Goal **failsafe:verify** evaluates results during the **verify** phase.
- Failsafe holds onto failed IT results so **verify** reports the build failure instead of halting the lifecycle immediately at integration-test. This gives **post-integration-test** (if configured) a chance to clean up infrastructure.
- Therefore, **mvn verify** is the right entry point to run the full IT lifecycle. **Do not use mvn integration-test as the final CI gate**, because cleanup and Failsafe verification have not run yet.

**Note:** In this HTTP integration example, the test uses **@SpringBootTest(RANDOM_PORT)**, which starts and stops the embedded server together with the Spring test context, so no external server needs to be configured in pre/post integration-test. Only add lifecycle setup/cleanup when a project requires external services.

### 4.2. Default Test Naming Conventions

Surefire selects classes matching by default:

~~~text
Test*.java
*Test.java
*Tests.java
*TestCase.java
~~~

Failsafe selects by default:

~~~text
IT*.java
*IT.java
*ITCase.java
~~~

These patterns can be changed via **includes/excludes** in each plugin.

Example:

| Test class | Surefire default | Failsafe default |
| --- | --- | --- |
| GreetingServiceTest | Yes | No |
| GreetingServiceTests | Yes | No |
| GreetingHttpIT | No | Yes |
| ITDatabaseRepository | No | Yes |
| PaymentITCase | No | Yes |

If named **GreetingIntegrationTest**, it ends with **Test**, so Surefire may run it as a unit test. To preserve Failsafe's default convention, name it **GreetingHttpIT** as shown in the example. Adjust include/exclude when a project has its own naming policy.

### 4.3. Key Difference Between Maven and Gradle

**Maven does not create an independent Java source set for Failsafe by default.** Both GreetingServiceTest and GreetingHttpIT reside in **src/test/java**, test resources in **src/test/resources**, and they compile together in **test-compile**. Separation here is primarily about **the execution plugin, naming patterns, and execution phase**. If you want fully separated IT directories/dependencies, you must configure extra plugins or another module.

**Gradle JVM Test Suite** creates a dedicated suite with its own sources/resources/dependencies and its own Test task. That is a stronger build-level boundary.

## 5. Unified Hands-On Exercise: HTTP Greeting in Spring Boot

We will write a small Spring Boot application to demonstrate the **same testing idea** in both Maven and Gradle. The **main** code is identical for both; the differences lie in where the integration test sits and in the build configuration.

### 5.1. Directory Tree per Tool

**Maven:**

~~~text
greeting-checks/
├── pom.xml
└── src/
    ├── main/java/com/example/greeting/
    │   ├── GreetingApplication.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    └── test/
        ├── java/com/example/greeting/
        │   ├── GreetingServiceTest.java
        │   └── GreetingHttpIT.java
        └── resources/application-it.properties
~~~

**Gradle:**

~~~text
greeting-checks/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/greeting/
    │   ├── GreetingApplication.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    ├── test/java/com/example/greeting/
    │   └── GreetingServiceTest.java
    └── integrationTest/
        ├── java/com/example/greeting/GreetingHttpIT.java
        └── resources/application-it.properties
~~~

**Choose only one set of build files** matching Maven or Gradle. The main Java files and the contents of both test classes are identical, but GreetingHttpIT is placed in **src/test/java** for Maven and **src/integrationTest/java** for Gradle. That determines which tool discovers and runs the test.

### 5.2. GreetingApplication.java File

**src/main/java/com/example/greeting/GreetingApplication.java**:

~~~java
package com.example.greeting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GreetingApplication {
    public static void main(String[] args) {
        SpringApplication.run(GreetingApplication.class, args);
    }
}
~~~

This is a complete **entry point** class. Spring Boot scans classes under the **com.example.greeting** package, including the service and controller below.

### 5.3. GreetingService.java File

**src/main/java/com/example/greeting/GreetingService.java**:

~~~java
package com.example.greeting;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name.strip() + "!";
    }
}
~~~

Uses Java 11+ **String.strip()**, valid for JDK 17. Unit tests can instantiate the class with **new GreetingService()** without a Spring context; when running the application, **@Service** lets Spring manage this bean.

### 5.4. GreetingController.java File

**src/main/java/com/example/greeting/GreetingController.java**:

~~~java
package com.example.greeting;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet(@RequestParam(defaultValue = "World") String name) {
        return service.greet(name);
    }
}
~~~

The controller receives GreetingService via constructor injection. For GET **/greet?name=Ada**, the expected body is **Hello, Ada!**. Both Java files declare packages matching their directory paths.

### 5.5. Unit Test Without a Spring Context

**src/test/java/com/example/greeting/GreetingServiceTest.java**:

~~~java
package com.example.greeting;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void trimsWhitespaceAndFormatsGreeting() {
        assertEquals("Hello, Ada!", service.greet("  Ada  "));
    }
}
~~~

JUnit Jupiter runs a plain Java test. **No @SpringBootTest, HTTP client, server, or database**. This test is ideal for a fast feedback loop whenever greet() logic changes.

### 5.6. Integration Test Starting a Real HTTP Server

**Maven:** file **src/test/java/com/example/greeting/GreetingHttpIT.java**.

**Gradle:** same file content, placed at **src/integrationTest/java/com/example/greeting/GreetingHttpIT.java**.

~~~java
package com.example.greeting;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@ActiveProfiles("it")
class GreetingHttpIT {

    @Autowired
    private TestRestTemplate client;

    @Autowired
    private Environment environment;

    @Test
    void servesHttpRequestAndUsesItProfile() {
        ResponseEntity<String> response =
                client.getForEntity("/greet?name=Ada", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Hello, Ada!", response.getBody());
        assertEquals("enabled",
                environment.getProperty("demo.integration.mode"));
    }
}
~~~

Meaning of the annotations:

- **@SpringBootTest(webEnvironment = RANDOM_PORT)** starts the **web application context** with an embedded HTTP server on an OS-assigned available port. Do not hardcode port 8080 to avoid CI collisions.
- **TestRestTemplate** is provided by Spring Boot test and configured for the server's random port; it uses the relative URL **/greet?name=Ada**.
- **@ActiveProfiles("it")** activates the **it** profile in the Spring test context.
- **Environment** verifies that suite/IT-specific resources were loaded properly.
- **assertEquals** verifies HTTP 200, the response body, and the property; if the controller, service, or route is broken, the integration test fails.

You do not need to run **java -jar** or **bootRun** beforehand for this integration test to work: **@SpringBootTest(RANDOM_PORT)** starts the server inside the test JVM. This is a real HTTP-level integration test, though it does **not** verify the packaged JAR deployed in production.

### 5.7. Dedicated Resource for Integration Tests

Create **application-it.properties** containing:

~~~properties
demo.integration.mode=enabled
spring.main.banner-mode=off
~~~

- **Maven:** place at **src/test/resources/application-it.properties** (Maven's shared test resources).
- **Gradle:** place at **src/integrationTest/resources/application-it.properties** (resources dedicated to the integrationTest suite).

**@ActiveProfiles("it")** tells Spring Boot to load this profile configuration from the test runtime classpath. Unit tests do not activate this profile and do not depend on that property. Do not place an IT-only fixture file in **src/main/resources** when you do not want it packaged into the application.

**Note on "separation":** Maven uses the same default test resources folder for both Surefire and Failsafe; if strict resource isolation is required, you must configure additional test sources or a separate module. Gradle suites have a dedicated test resource source set, providing a clearer isolation model.

## 6. Maven: Complete pom.xml with Surefire and Failsafe

Create **pom.xml** at the root directory for the Maven option:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>greeting-checks</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>greeting-checks</name>

    <properties>
        <java.version>17</java.version>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.4</version>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**This is a complete POM for Java 17/Spring Boot 3.3.5** using Maven. Spring Boot parent manages starter versions and related plugin settings. Declaring Surefire and Failsafe with the same explicit version prevents provider/JUnit Platform mismatches between the two groups.

With default naming patterns:

- Surefire runs **GreetingServiceTest** during the **test** phase.
- Failsafe runs **GreetingHttpIT** during the **integration-test** phase, then **verify** checks the outcome.
- Starter test has **test** scope, so JUnit and TestRestTemplate classes are available on the test classpath without becoming production dependencies of the JAR.

### 6.1. Running Unit Tests Fast

From the project root containing the Maven Wrapper:

~~~bash
./mvnw clean test
~~~

Maven executes **compile → test-compile → test**. Surefire finds **GreetingServiceTest**, whereas **GreetingHttpIT** does not match Surefire's default patterns. Thus no embedded server starts from the IT test.

If the machine lacks a wrapper, you can use **mvn clean test** with a compatible installed Maven. On Windows, use **mvnw.cmd**.

**Expected outcome:** one unit test runs and passes, without running GreetingHttpIT. Exact plugin output and test counts depend on other tests if the learner adds files.

### 6.2. Running All Checks with verify

~~~bash
./mvnw clean verify
~~~

This runs all phases prior to **verify**, including Surefire tests, Spring Boot package/repackage, Failsafe integration-test, post-integration-test cleanup if present, and Failsafe verification. For the example, **GreetingHttpIT** starts the Spring HTTP server on a random port and verifies the endpoint.

**Important:** Do not replace **verify** with **integration-test** when CI needs to detect build failures from ITs. Failsafe is designed to report failures at the end of the lifecycle in verify, allowing cleanup phases to run.

### 6.3. Does Running package Run ITs?

~~~bash
./mvnw clean package
~~~

In the Maven lifecycle, **package precedes integration-test**, so this command runs unit tests and builds the artifact, but **does not pass through Failsafe integration-test/verify**. That is the core difference from **verify**. If a pipeline only invokes **mvn package**, integration tests may never run even though Failsafe is declared in the POM.

### 6.4. Reading Maven Reports

Typically:

~~~text
target/surefire-reports/TEST-com.example.greeting.GreetingServiceTest.xml
target/failsafe-reports/TEST-com.example.greeting.GreetingHttpIT.xml
target/failsafe-reports/failsafe-summary.xml
~~~

Exact report filenames depend on package/class names, plugin versions, and configuration. In CI, you can collect with globs:

~~~text
target/surefire-reports/TEST-*.xml
target/failsafe-reports/TEST-*.xml
~~~

If Failsafe reports no tests found, check that the class name ends with **IT**, the path is **src/test/java**, plugin/execution goals are configured, and test compilation succeeded. Do not casually add failure-ignoring options just to turn a pipeline green.

## 7. Gradle: build.gradle with JVM Test Suite

Gradle uses a **dedicated source set and test task** rather than detecting ITs solely by class name.

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'greeting-checks'
~~~

### 7.2. Complete build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

testing {
    suites {
        test {
            useJUnitJupiter()
        }

        integrationTest(JvmTestSuite) {
            useJUnitJupiter()

            dependencies {
                implementation project()
                implementation 'org.springframework.boot:spring-boot-starter-test'
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(tasks.named('test'))
                    }
                }
            }
        }
    }
}

tasks.named('check') {
    dependsOn(testing.suites.integrationTest)
}
~~~

**This is a complete Groovy DSL build.gradle** for the Gradle option. Use Gradle **8.5** or another version with compatible JVM Test Suite DSL; the Gradle Java plugin already includes the necessary JVM Test Suite functionality, so explicitly declaring **id 'jvm-test-suite'** is not strictly required.

Exact explanation:

1. **test { useJUnitJupiter() }** configures the default test suite to use JUnit Jupiter. Tests for this suite live in **src/test/java**; the task name is **test**.
2. **integrationTest(JvmTestSuite)** registers a new suite. By convention, source code lives in **src/integrationTest/java** and resources in **src/integrationTest/resources**. Gradle creates an **integrationTest** task, compiler task, and separate classpath for the suite.
3. **implementation project()** inside the suite is required for the suite to reference **the project's production code**. Custom suites do not inherit access to production sources the way the default test suite does.
4. **implementation 'org.springframework.boot:spring-boot-starter-test'** inside the suite enables **@SpringBootTest, TestRestTemplate, JUnit/AssertJ** when running ITs. This dependency belongs to **integrationTestImplementation**, not production dependencies.
5. **shouldRunAfter(tasks.named('test'))** prefers running integrationTest after unit tests when both are in the task graph; **it does not create a task dependency by itself**.
6. **tasks.named('check') { dependsOn(...) }** is what causes **./gradlew check** to run integrationTest along with other verification steps. Without this line, **check** does not automatically run custom suites by convention.
7. The **io.spring.dependency-management** plugin together with the Spring Boot plugin manages starter dependency versions per Boot's BOM. Newer Gradle/Boot setups may require checking the JUnit platform launcher version; avoid relying on leaked internal classpaths.

**JVM Test Suite is an incubating API in the Gradle versions cited here**, and may evolve across versions. Pin the Gradle Wrapper and review release notes when upgrading.

### 7.3. Directories and Classpaths Created by Gradle

~~~text
src/main/java                          → compileJava → main classes
src/test/java                          → compileTestJava → test classes
src/integrationTest/java               → compileIntegrationTestJava → IT classes
src/integrationTest/resources          → processIntegrationTestResources

testImplementation / testRuntimeClasspath
integrationTestImplementation / integrationTestRuntimeClasspath

test task                              → default test suite only
integrationTest task                   → integrationTest suite only
check task                             → test + integrationTest (via dependsOn)
~~~

**Do not copy GreetingHttpIT into src/test/java in the Gradle option** if you want fast unit test runs. The Gradle `test` task does not distinguish "IT" vs. "Test" by name like Maven Failsafe; it runs whatever classes belong to the configured **source set**. Placing files in the wrong directory can cause slow tests to run inside the unit pipeline.

### 7.4. Essential Gradle Commands

~~~bash
./gradlew clean test
./gradlew integrationTest
./gradlew check
./gradlew build
~~~

- **clean test**: runs the default suite, which in this example is only GreetingServiceTest. Does not automatically run the integrationTest suite merely because it exists.
- **integrationTest**: runs the integration suite, GreetingHttpIT in this example, along with the compile/resources tasks the suite needs.
- **check**: runs both unit and ITs because **dependsOn(testing.suites.integrationTest)** was added.
- **build**: depends on **check** and **assemble**; with the configuration above, it runs both test groups and builds the artifact.

The Gradle Wrapper on Windows uses **gradlew.bat**. Log statuses such as **UP-TO-DATE** or **FROM-CACHE** mean Gradle may skip re-running unchanged tests; use **--rerun-tasks** when you genuinely need to force re-execution during diagnostics.

### 7.5. Where Are Gradle Reports?

After running the test suites, Gradle typically produces:

~~~text
build/test-results/test/TEST-*.xml
build/test-results/integrationTest/TEST-*.xml

build/reports/tests/test/index.html
build/reports/tests/integrationTest/index.html
~~~

Because they are two distinct tasks, CI can upload JUnit XML reports from each path. When a test fails, check the **task name** in the output and HTML/XML reports to tell whether the failure came from unit tests or integration tests.

### 7.6. When Gradle Reports Missing TestRestTemplate or JUnit Classes

Check that **dependencies** are declared **inside the integrationTest suite**, not only in top-level testImplementation. The integrationTest suite does not automatically inherit testImplementation dependencies from the default test suite. Inspect resolved classpaths:

~~~bash
./gradlew dependencies --configuration integrationTestCompileClasspath
./gradlew dependencies --configuration integrationTestRuntimeClasspath
~~~

Also confirm **implementation project()** is present, since without it integration tests cannot compile against application classes.

## 8. Comparing Maven Failsafe and Gradle JVM Test Suite

| Criterion | Maven Surefire + Failsafe | Gradle JVM Test Suite |
| --- | --- | --- |
| Default grouping mechanism | **Class name**: *Test vs *IT | **Source set/suite**: test vs integrationTest |
| Integration test source | **src/test/java** under standard config | **src/integrationTest/java** |
| Test resources | Shared **src/test/resources** | Isolated **src/integrationTest/resources** per suite |
| Libraries for integration tests | Usually shared **test** scope dependencies | Declared inside **integrationTest.dependencies** |
| Unit task/phase | **test**, Surefire | **test** task |
| IT task/phase | **integration-test + verify**, Failsafe | **integrationTest** task |
| CI gate for both | **mvn verify** | **./gradlew check** when wired; or **build** |
| Reports | surefire-reports, failsafe-reports | test-results/test and test-results/integrationTest |
| External setup/teardown | Maven pre/post integration-test phases available | Gradle requires appropriate tasks/services and dependencies/finalizers |
| Key caveat | Do not stop at **mvn integration-test** | Do not forget **check.dependsOn(integrationTest)** |

**Do not equate** Gradle's integrationTest name with Maven's integration-test phase. One is a **Gradle task** generated for a suite; the other is a **Maven lifecycle phase** hosting Failsafe goals.

## 9. CI Pipeline: Fast on Pull Requests, Thorough Before Release

### 9.1. Recommended Two-Tier Checks

**Fast tier (on every edit or push)** prioritizes unit tests:

~~~bash
# Maven
./mvnw -B clean test

# Gradle
./gradlew --no-daemon clean test
~~~

**Full tier (pull request, merge gate, or pre-release)** runs both unit and integration tests:

~~~bash
# Maven
./mvnw -B clean verify

# Gradle
./gradlew --no-daemon clean check
~~~

These are **two alternatives** for their respective tools, not a requirement to run both Maven and Gradle in one repository. Depending on your project's quality policy, integration tests may be required on **every pull request**, not just before release. If integration tests are slow, consider parallel jobs, dependency caching, and disposable test environments rather than quietly dropping ITs.

**For Gradle**, if you also need packaging simultaneously, invoke **./gradlew clean build**; because integrationTest is wired into check, build runs both test suites in the lifecycle.

### 9.2. Environment Dependencies and Testcontainers

When integration tests require PostgreSQL/Kafka/Redis, never let results depend on personal data on a developer's machine:

- Use disposable databases/containers or isolated schemas per job.
- Testcontainers can launch containers from JUnit/Spring test setup, provided CI has a suitable container runtime and permissions.
- Use random ports wherever appropriate; avoid fixed hardcoded ports that collide across CI jobs.
- Set explicit timeouts and cleanup; do not leave orphaned containers/services running after a test fails.
- Store CI passwords/tokens in a secret store; never commit real credentials into **application-it.properties**.
- If tests need network access or uncached images, offline runs can fail; document environment prerequisites clearly.

In this lesson's Hello HTTP example, there is no DB or broker, so **Docker is not required**. Do not add Testcontainers to the POM/Gradle file unless your exercise actually uses it.

### 9.3. Test and Production Environments Differ

**@SpringBootTest(RANDOM_PORT)** runs the app with the test classpath and an embedded server inside the test JVM. It is **not** completely equivalent to deploying the executable JAR onto Kubernetes, Docker, or a real server. If packaging/deployment verification is required, add a smoke test against the built artifact (typically as a separate CI stage).

### 9.4. Preserving Reports When ITs Fail

With Maven, ensure **failsafe:verify** runs so failures are detected per lifecycle, while archiving **target/failsafe-reports**. With Gradle, do not set **ignoreFailures = true** for ITs on mandatory gates. CI systems should always upload test reports after a job—even when the build fails—and must surface a failing exit code to the pipeline status.

## 10. Common Integration Testing Scenarios

**10.1. HTTP controller + service:** like this example. Tests run a Spring context and real HTTP server, verifying routes, dependency injection, and responses. Well-suited as a first exercise.

**10.2. Repository + database:** tests queries/writes and verifies transactions/schemas. In-memory H2 is handy for quick demos, but if production uses PostgreSQL/MySQL, SQL/dialect differences may cause H2 tests to miss bugs. For real compatibility requirements, use the matching database engine in a container.

**10.3. Messaging:** tests publishing/consuming messages and retry/dead-letter handling. Requires a stable broker environment and avoiding shared queues across jobs. Isolate fixtures and clean up so tests do not pollute each other's state.

**10.4. REST client calling external services:** use MockWebServer/WireMock to verify stable HTTP contracts, or run contract tests against real services in a controlled environment. Unit tests should never accidentally call the public internet.

**10.5. Security filters:** use the Spring test context and an HTTP client to assert 401/403/200 statuses with or without valid tokens. Distinguish mocked authentication tests from real authentication provider integration.

**10.6. Data migrations:** run migrations against a clean database and verify key schema/data expectations. These are typically slower integration tests, so keep them in a dedicated suite and reset state afterward.

In all cases, tests must be **deterministic**, order-independent, and bounded in execution time. A test that only passes when run after another test signals shared state or missing cleanup.

## 11. When to Use JUnit Tags Instead of Separate Maven/Gradle Suites?

**JUnit Jupiter @Tag** lets you categorize tests by label, for example:

~~~java
package com.example.greeting;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ExampleTaggedTest {
    @Test
    @Tag("integration")
    void tagged() {
        assertTrue(true);
    }
}
~~~

This is **a complete Java/JUnit example**, separate from the main exercise files in section 5. Using **@Tag("integration")** does not by itself alter the Maven lifecycle or create a Gradle source set. You must configure include/exclude groups/tags in Surefire, Failsafe, or the Test task if using this approach. Do not allow the same test to run twice unintentionally simply because it matches both a naming pattern and a tag.

**When are tags a good fit?** When categorizing within the same source set, or along orthogonal dimensions like **slow**, **database**, **contract**. **When should you use separate suites?** When you need distinct classpaths, resources, tasks, timeouts, or CI policies; Gradle JVM Test Suites fit that separation well.

With **Maven Failsafe**, the ***IT** convention is simple and predictable. With **Gradle JVM Test Suites**, the **IT** suffix is not required for discovery, though keeping it helps readers immediately recognize a test's purpose.

## 12. Common Pitfalls and How to Fix Them

**Pitfall 1 — Maven integration test runs during mvn test.** A class named **GreetingIntegrationTest** ends in Test, so Surefire picks it up. Rename it to **GreetingHttpIT** or configure appropriate includes/excludes; verify plugin reports.

**Pitfall 2 — Maven verify does not run ITs.** Verify **maven-failsafe-plugin** is declared in build/plugins with goals **integration-test** and **verify**, test names match ***IT**, and test classes compile in src/test/java. Declaring the plugin only in **pluginManagement** is not enough to execute it unless activated in plugins.

**Pitfall 3 — CI only invokes mvn package.** Package runs before the integration-test phase. Change the full gate to **mvn verify**; do not infer that ITs ran merely because the JAR was built successfully.

**Pitfall 4 — Calling only mvn integration-test and treating BUILD SUCCESS as enough.** Failsafe records test failures to evaluate at **verify**. You must call **mvn verify** to reach verification and cleanup phases.

**Pitfall 5 — Gradle declares a suite, yet ./gradlew check skips ITs.** Custom suites are not wired into **check** automatically. Add **dependsOn(testing.suites.integrationTest)**, then verify the task graph.

**Pitfall 6 — GreetingHttpIT placed in src/test/java under Gradle.** The **test** task picks it up, slowing down the unit loop, or the integrationTest task misses it. Move it to **src/integrationTest/java**, keeping unit tests in src/test/java.

**Pitfall 7 — Gradle integrationTest fails to compile because main classes are missing.** Custom suites do not receive project production outputs automatically; declare **implementation project()** inside **integrationTest.dependencies**.

**Pitfall 8 — Gradle integrationTest lacks @SpringBootTest/TestRestTemplate.** **testImplementation** from the default test suite does not carry over to integrationTest. Declare **spring-boot-starter-test** in **integrationTest.dependencies**.

**Pitfall 9 — Assuming shouldRunAfter makes IT a dependency of test.** **shouldRunAfter** only orders execution when both tasks are already in the graph. Use **check.dependsOn** to guarantee ITs run in the gate.

**Pitfall 10 — @SpringBootTest does not hit a real server.** By default, **@SpringBootTest** uses a MOCK web environment. To test real HTTP, use **webEnvironment = RANDOM_PORT** and send requests to the started server.

**Pitfall 11 — HTTP test port 8080 collision.** Use RANDOM_PORT; avoid hardcoding host/port for embedded servers. For tests calling external services, also allocate random ports or isolated environments.

**Pitfall 12 — @ActiveProfiles("it") set, but property is missing.** Check **application-it.properties** is in the right source set: Maven src/test/resources; Gradle src/integrationTest/resources. Verify profile name, file extension, classpath, and other overrides.

**Pitfall 13 — Failing ITs do not fail CI.** In Maven, failsafe:verify may be missing or the pipeline does not call verify. In Gradle, the job may skip integrationTest or set **ignoreFailures**; fix pipeline/task dependencies.

**Pitfall 14 — Tests try to connect to a database, but CI has none.** Provision a database/container, configure test-specific URLs/credentials, wait for readiness, and clean up. Environment issues must not be fixed by unconditionally skipping integration tests.

**Pitfall 15 — Running only unit tests and claiming all integration works.** Unit tests do not catch every Spring wiring, servlet mapping, JSON serialization, schema migration, or networking bug. Run the IT suite at the gate according to project risk.

**Pitfall 16 — Every test uses @SpringBootTest.** Unit tests that do not need a Spring context should avoid booting one to keep feedback fast. Only boot the context/HTTP server for tests genuinely verifying integration.

**Pitfall 17 — Maven Failsafe and Surefire use inconsistent provider/plugin versions.** Pin compatible versions and ensure JUnit Jupiter engine is on the test classpath. Spring Boot starter-test supplies the required JUnit ecosystem for the example.

**Pitfall 18 — Gradle suite cannot use JUnit Platform launcher in newer Gradle versions.** Read the error message and corresponding Gradle documentation; in environments requiring explicit launcher declaration, add **org.junit.platform:junit-platform-launcher** to runtimeOnly of the appropriate suite with a compatible managed version rather than relying on leaked internal dependencies.

**Pitfall 19 — Integration tests pollute shared environments.** Generate unique data per test/job, apply cleanup, proper transactions, and test resource isolation. When HTTP tests execute on a separate server thread, test-side @Transactional does not automatically roll back server-side transactions.

## 13. Checklist Before Finalizing Test Separation

- [ ] Define the boundary between unit tests and integration tests by behavior, not just naming.
- [ ] Write unit tests without a Spring context wherever possible.
- [ ] Write ITs for at least one real integration path (HTTP, DB, messaging).
- [ ] Maven: Surefire runs ***Test**, Failsafe runs ***IT**, with both **integration-test** and **verify** goals.
- [ ] Maven: full CI uses **mvn verify**, never stopping at package or integration-test.
- [ ] Gradle: declare **integrationTest(JvmTestSuite)** with separate sources/resources.
- [ ] Gradle: suite includes **implementation project()** and its own test framework/dependencies.
- [ ] Gradle: **check.dependsOn(testing.suites.integrationTest)** when check/build must run ITs.
- [ ] Verify **RANDOM_PORT** and profile/resources, avoiding fixed port dependencies.
- [ ] Inspect unit/IT reports separately and confirm non-zero exit status when tests fail.
- [ ] Provide isolated test infrastructure and cleanup for external DBs/brokers/services.
- [ ] Re-run both groups after changing Spring Boot/Gradle/Maven/JUnit versions.

## 14. Official Documentation

- Apache Maven — Failsafe Plugin Introduction and lifecycle: https://maven.apache.org/surefire/maven-failsafe-plugin/index.html
- Apache Maven — Failsafe Plugin Inclusions/Exclusions: https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html
- Apache Maven — Surefire Plugin Inclusions/Exclusions: https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html
- Apache Maven — Lifecycle Phases: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Gradle — JVM Test Suite Plugin: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html

**Summary:** Maven separates unit and integration tests using **Surefire, Failsafe, test naming patterns, and the verify lifecycle**; Gradle separates them using **JVM Test Suites with dedicated source sets, dependencies, and tasks**, wiring **integrationTest** into **check**. Both approaches keep unit tests fast while preserving integration tests as a mandatory release gate.
