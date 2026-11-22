# Next Learning Steps After Java Core JDK Tooling

This lesson belongs to the **JDK Tooling Summary** group. After knowing how to install the JDK, check `JAVA_HOME`/`PATH`, compile with `javac`, run with `java`, package with `jar`, and diagnose with JDK tools, the next step is to use those skills to build a structured application with tests, dependency management, and something you can hand off to others.

The goal is not to learn a framework as early as possible. Complete a small development lifecycle first: understand the Java language, organize source code, automate builds, test, debug, package, and run the artifact. This foundation applies to backend, desktop, cloud, data processing, and JVM-focused specializations.

## 1. The Destination After JDK Tooling

A basic Java project goes through these steps:

~~~text
Requirements
  |
  v
Design classes, packages, and APIs
  |
  v
Write Java source
  |
  v
Compile and test
  |
  v
Manage dependencies and build
  |
  v
Package JAR or distribution
  |
  v
Test-run the artifact
  |
  v
Write documentation and release
~~~

You are ready when you can explain on your own why the JDK is needed, how source code is compiled into bytecode, how a build tool selects dependencies, at which step tests run, and which file is actually delivered to users.

## 2. Review What You Already Know

Before learning new topics, give yourself a short self-check:

- Use java -version and javac -version to identify the runtime/compiler.
- Explain JAVA_HOME and PATH, and know how to find executables with where.exe or command -v.
- Compile source code with javac --release 17.
- Run a class with java -cp and understand the classpath.
- Create a JAR with jar, and inspect entries and the manifest.
- Use javap to inspect bytecode and jdeps to inspect dependencies.
- Distinguish compiler, classpath, and runtime errors.
- Read a stack trace to locate the exception and relevant source line.

If you still get stuck on an item, practice that exact tool again. You do not need to memorize every option; you need to understand which problem each tool solves and know how to look up the documentation when needed.

## 3. Build a Solid Foundation in the Java Language

Follow this order:

1. Data types, variables, operators, conditionals, loops, and arrays.
2. Methods, parameters, return values, overloading, and variable scope.
3. Classes, objects, constructors, encapsulation, and access modifiers.
4. Interfaces, inheritance, composition, and polymorphism.
5. Exceptions, try-with-resources, and error handling.
6. Enums, records, generics, and annotations.
7. Lambdas, method references, and functional interfaces.
8. Collections, Stream API, and Optional.

For each concept, write a small example, test valid inputs, edge cases, and invalid cases. Then make sure you can explain why the output appears as it does.

## 4. Design Classes and Interfaces

An application has multiple classes with distinct responsibilities. Practice separating them:

- Model represents data and invariant rules.
- Service implements business logic.
- Repository or gateway accesses data.
- CLI, controller, or UI receives input and presents output.
- Tests verify public behavior.

For example, Study Planner has StudySession to represent a study session, StudyPlan to manage study sessions, and StudyPlanApp as the program entry point.

Do not create classes just to increase the number of files. A class should have a clear responsibility, a name that expresses intent, and a right-sized API. Use composition when an object needs the functionality of another object; only use inheritance when there is a valid substitutability ("is-a") relationship.

## 5. Learn Exceptions and Validation

Distinguish the error categories:

- Invalid input or state: typically validate early and throw IllegalArgumentException or IllegalStateException.
- I/O errors: may raise IOException and require deciding whether to handle or propagate.
- Programming errors: such as NullPointerException or IndexOutOfBoundsException, usually require fixing the root cause.
- Expected business errors: represent clearly according to the application contract.

Do not catch Exception and silently ignore it. Do not use exceptions to replace normal control flow. Error messages should include context, but never log passwords, tokens, or sensitive data.

## 6. Learn Collections, Generics, and the Stream API

| API | Purpose |
|---|---|
| List | Stores elements in order, allows duplicates |
| Set | Stores a collection of unique values |
| Map | Maps keys to values |
| Queue/Deque | Queue or double-ended queue model |
| Generics | Keeps data types explicit and reduces casting |
| Stream | Filters, transforms, sorts, and aggregates data |

Example of calculating total duration:

~~~java
int totalMinutes = sessions.stream()
        .mapToInt(StudySession::minutes)
        .sum();
~~~

Collections store data; streams describe a processing pipeline. Do not convert every loop into a stream if a regular loop is easier to read.

## 7. Expand to the Java Core API

| Group | Topics to Practice |
|---|---|
| Collections | List, Set, Map, Queue, Comparator |
| Date/Time | LocalDate, Instant, Duration, ZoneId |
| I/O and NIO | Path, Files, InputStream, Reader, Writer |
| Text | String, StringBuilder, regex, Formatter |
| Functional | Optional, Predicate, Function, Stream |
| Networking | URI, HttpClient, HttpRequest, HttpResponse |
| Concurrency | Thread, ExecutorService, synchronization, CompletableFuture |
| Resource management | try-with-resources, AutoCloseable |

Learn Date/Time before handling dates and times manually with strings. Learn Path/Files before concatenating paths with slashes. Learn HttpClient before writing the HTTP protocol yourself.

JSON, YAML, and databases usually require libraries or drivers outside the JDK. When you reach those parts, learn how to add dependencies and check version compatibility.

## 8. Organize Packages and the Source Tree

A project should not place every class in a single folder or the default package. With Maven, main source code lives in src/main/java and tests live in src/test/java:

~~~text
study-planner/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/study/
│   │   │   ├── StudySession.java
│   │   │   ├── StudyPlan.java
│   │   │   └── StudyPlanApp.java
│   │   └── resources/
│   └── test/
│       ├── java/com/example/study/
│       │   └── StudyPlanTest.java
│       └── resources/
└── README.md
~~~

Package names are lowercase and usually based on the organization's reversed domain name. Classes use PascalCase; methods and variables use camelCase. Do not include JUnit as a runtime dependency if it is only used for running tests.

## 9. Use an IDE After Understanding the Command Line

Pick an IDE and learn the core operations:

- Import a project from Maven or Gradle.
- Select the Project SDK/JDK and language level.
- Create classes, packages, and test classes.
- Find symbols, rename, and refactor.
- Set breakpoints, step over, step into, and inspect variables.
- Run a single test or the entire test suite.
- Inspect the dependency tree and build output.

An IDE speeds up your workflow, but you still need to understand which JDK the project uses, which build task runs, and where the output is placed. Occasionally build from the terminal to make sure the project does not depend on IDE-specific configuration.

## 10. Learn One Build Tool First

A build tool automates compilation, testing, packaging, and dependency resolution. You can learn Maven first because its POM and lifecycle are straightforward, or learn Gradle if your project/team uses Gradle.

You do not need to master both at the same time. Learn one tool deeply first, then map the concepts to the other.

| Concept | Maven | Gradle |
|---|---|---|
| Project configuration | pom.xml | build.gradle or build.gradle.kts |
| Dependencies | dependencies in POM | dependencies block |
| Compile | mvn compile | compileJava |
| Test | mvn test | test |
| Package | mvn package | jar or assemble |
| Verify | mvn verify | check or build |
| Wrapper | mvnw / mvnw.cmd | gradlew / gradlew.bat |

Prefer the wrapper provided by the project so the team uses the same build tool version.

## 11. Learn the Maven Lifecycle and POM

A POM describes coordinates, properties, dependencies, and plugins. The main phases are:

- validate: validates the project and required information.
- compile: compiles main source code.
- test: runs unit tests.
- package: creates the JAR/WAR.
- verify: runs additional checks.
- install: installs the artifact into the local repository.
- deploy: uploads the artifact to a remote repository.

Commonly used commands:

~~~bash
mvn clean
mvn compile
mvn test
mvn package
mvn verify
~~~

When you invoke a phase, Maven runs all preceding phases in the default lifecycle. verify includes compile, test, and package according to the lifecycle, though it does not automatically guarantee the project has configured a smoke test on the final JAR.

Learn how to read the dependency tree, compile/test/runtime scopes, transitive dependencies, repositories, plugins, and toolchains.

## 12. Learn Gradle Basics If Your Project Uses Gradle

Gradle uses a task graph. The Java plugin provides compileJava, processResources, classes, compileTestJava, test, jar, assemble, check, and build.

Example build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.example.study.StudyPlanApp'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Commands:

~~~bash
./gradlew tasks
./gradlew dependencies
./gradlew test
./gradlew build
~~~

On Windows use gradlew.bat. Learn the wrapper, plugins, dependency configurations, task graph, and toolchains before writing custom tasks yourself.

## 13. Manage Dependencies

When adding a library, determine:

- What problem does the library solve?
- Does the version support the project's Java release?
- Does the dependency belong in compile, runtime, or test?
- What transitive dependencies are pulled in?
- Are the license and security posture acceptable?
- Do you need to pin versions or use a BOM?

Do not copy dependencies from old blog posts without checking official documentation. Do not add a library just for one convenience method if the JDK already provides a suitable API.

Use the dependency tree to see why a library appears. When there is a version conflict, find which dependency brings in the old version and resolve it in the right place instead of manually adding JARs to the classpath.

## 14. Start Testing with JUnit

Testing verifies behavior with repeatable examples. With JUnit Jupiter, the basic annotations/assertions include:

- @Test marks a test method.
- @BeforeEach and @AfterEach set up/clean up data.
- assertEquals, assertTrue, and assertFalse verify results.
- assertThrows verifies an expected exception.
- @ParameterizedTest runs the same test with multiple inputs.

Test names should describe behavior. Prepare clear inputs and assert important outcomes. Avoid tests that depend on execution order or share mutable state that another test can modify.

## 15. Distinguish Testing Layers

| Type | Tests | Example |
|---|---|---|
| Unit | A single class or small behavior | Calculating total duration |
| Integration | Multiple components working together | Service reading/writing a file |
| Contract/API | Contract between components | HTTP request/response |
| Smoke | Whether the artifact starts on critical paths | Running the packaged JAR |
| End-to-end | Business flow across multiple layers | Creating, saving, and viewing a plan |

You do not need to write tests for every getter/setter. Prioritize logic with rules, boundary inputs, expected errors, and user-facing behavior. Fast unit tests catch bugs early; integration/smoke tests confirm that components are wired together properly.

## 16. Design Good Tests

For each important method, consider:

1. Normal cases.
2. Empty or missing input.
3. Boundary values.
4. Invalid input.
5. Empty-data state.
6. Exceptions or I/O errors.
7. Ordering and stability of results if required.

Tests should not mirror the implementation. If the code uses a stream to compute a sum, the test verifies the business result, not that a stream was called. If you refactor internals without changing behavior, good tests continue to pass.

## 17. Debug Methodically

When an error occurs, gather evidence before fixing:

- Read the exception and stack trace.
- Find the first frame belonging to the project's source code.
- Identify the input and state at the time of failure.
- Reproduce with a small test.
- Use breakpoints and step execution in the IDE or jdb.
- Test hypotheses with small changes.
- Add a regression test to prevent the bug from returning.

Distinguish compile errors, test failures, runtime exceptions, configuration errors, and environment issues. Do not fix bugs by catching every exception or increasing timeouts before understanding the root cause.

## 18. Leverage JDK Diagnostic Tools

| Tool | Used For |
|---|---|
| jps | Listing running JVMs |
| jcmd | Sending diagnostic commands to a JVM |
| jstack | Capturing a thread dump |
| jfr | Viewing or analyzing Flight Recorder recordings |
| jconsole | Monitoring a JVM through a GUI |
| jmap | Inspecting heap information |
| jdeps | Analyzing class/module dependencies |
| javadoc | Generating API documentation |
| javap | Inspecting class/bytecode structure |
| jdb | Debugging a Java program |

For example, replace the sample PID with the actual process PID:

~~~bash
jps -l
jcmd -l
jcmd 12345 VM.version
jstack 12345
~~~

Some commands must run under the same user as the process and may be restricted by OS/container permissions. Do not run diagnostic commands in production without understanding their impact and operational procedures.

## 19. Learn Logging and Application Observability

Real-world applications need structured logging with appropriate levels:

- ERROR: an operation failed and needs attention.
- WARN: something unexpected happened, but the application continues.
- INFO: important business or lifecycle events.
- DEBUG: detailed information for investigation.
- TRACE: deep detail, usually enabled only when needed.

Start with java.util.logging or the logging library used by the project. Do not print everything with System.out in long-lived applications. Never log passwords, access tokens, private keys, or unnecessary personal data.

Logs should include context such as a request ID or operation ID when appropriate. Choose a single layer responsible for logging errors to avoid logging the same stack trace multiple times.

## 20. Write API Documentation and READMEs

Use Javadoc to describe purpose, parameters, return values, exceptions, and usage examples for public APIs.

~~~bash
javadoc -d docs/api -sourcepath src/main/java com.example.study
~~~

A project README should include:

- What the project does and who it is for.
- JDK/build tool requirements.
- How to build, test, and run.
- Directory structure.
- Example input/output.
- How to configure it.
- Known limitations and future direction.

Documentation must match actual commands and behavior. When changing dependencies, versions, or how to run the app, update the README in the same change.

## 21. Learn Git and Team Collaboration

Know how to use clone, status, add, commit, pull, push, create branches, read diffs, resolve conflicts, and open pull requests.

Do not commit secrets or build outputs unless the project requires it. Commit messages should describe the change. A good pull request has a clear goal, tests alongside the code, and verification instructions. Reading code reviews is a great way to learn naming, class design, and error handling.

## 22. Capstone: Build Study Planner

To bring your new knowledge together, build a CLI application called Study Planner. The first version stores study sessions in memory, validates input, and calculates total duration.

Requirements:

- Each StudySession has a topic and a number of minutes.
- Topic is non-blank; minutes must be greater than 0.
- StudyPlan adds study sessions and returns a read-only list.
- The application prints the session count, total duration, and average.
- JUnit tests cover valid data, invalid data, and an empty plan.
- Maven builds with Java release 17.
- The JAR has Main-Class and runs with java -jar.

Once complete, extend it step by step: save to a file, load data, add CLI commands, filter by topic, add dates/times, and then replace file storage with a database once you learn JDBC/SQL.

## 23. Capstone Project Structure

~~~text
study-planner/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/study/
    │       ├── StudySession.java
    │       ├── StudyPlan.java
    │       └── StudyPlanApp.java
    └── test/
        └── java/com/example/study/
            └── StudyPlanTest.java
~~~

StudySession models a study session; StudyPlan manages the collection and calculations; StudyPlanApp is the entry point; StudyPlanTest verifies behavior.

## 24. StudySession.java Source Code

Use a record for small, immutable data. The compact constructor normalizes topic and rejects invalid data:

~~~java
package com.example.study;

import java.util.Objects;

public record StudySession(String topic, int minutes) {
    public StudySession {
        topic = Objects.requireNonNull(topic, "topic").strip();
        if (topic.isEmpty()) {
            throw new IllegalArgumentException("topic must not be blank");
        }
        if (minutes <= 0) {
            throw new IllegalArgumentException("minutes must be positive");
        }
    }
}
~~~

A record automatically provides accessors, equals, hashCode, and toString. The constructor still needs validation because invalid data should never enter the domain model.

## 25. StudyPlan.java Source Code

~~~java
package com.example.study;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.OptionalDouble;

public final class StudyPlan {
    private final List<StudySession> sessions = new ArrayList<>();

    public void add(StudySession session) {
        sessions.add(Objects.requireNonNull(session, "session"));
    }

    public List<StudySession> sessions() {
        return List.copyOf(sessions);
    }

    public int totalMinutes() {
        return sessions.stream().mapToInt(StudySession::minutes).sum();
    }

    public OptionalDouble averageMinutes() {
        return sessions.stream().mapToInt(StudySession::minutes).average();
    }
}
~~~

List.copyOf returns a list that cannot be modified through the returned reference. OptionalDouble explicitly expresses that an empty plan has no average value. This is an example of encapsulation, an immutable view, and an API that represents the absence of a result.

## 26. StudyPlanApp.java Source Code

~~~java
package com.example.study;

import java.util.Locale;

public final class StudyPlanApp {
    private StudyPlanApp() {
    }

    public static void main(String[] args) {
        StudyPlan plan = new StudyPlan();
        plan.add(new StudySession("Java collections", 45));
        plan.add(new StudySession("Maven basics", 30));
        plan.add(new StudySession("Unit testing", 40));

        System.out.println("STUDY_PLAN sessions=" + plan.sessions().size());
        System.out.println("TOTAL_MINUTES=" + plan.totalMinutes());
        System.out.println("AVERAGE_MINUTES="
                + String.format(Locale.ROOT, "%.1f",
                        plan.averageMinutes().orElse(0.0)));
    }
}
~~~

Locale.ROOT keeps decimal formatting consistent between local machines and CI. The application only keeps data in memory; when the process exits, data is lost. Persistent storage is the next extension.

## 27. StudyPlanTest.java Source Code

JUnit tests verify the total, average, invalid data, and an empty plan:

~~~java
package com.example.study;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class StudyPlanTest {
    @Test
    void recordsSessionsAndCalculatesTotals() {
        StudyPlan plan = new StudyPlan();
        plan.add(new StudySession("Collections", 45));
        plan.add(new StudySession("Testing", 30));

        assertEquals(2, plan.sessions().size());
        assertEquals(75, plan.totalMinutes());
        assertEquals(37.5, plan.averageMinutes().orElseThrow());
    }

    @Test
    void rejectsInvalidSessionData() {
        assertThrows(IllegalArgumentException.class,
                () -> new StudySession("   ", 10));
        assertThrows(IllegalArgumentException.class,
                () -> new StudySession("Java", 0));
    }

    @Test
    void averageIsEmptyForAnEmptyPlan() {
        assertTrue(new StudyPlan().averageMinutes().isEmpty());
    }
}
~~~

The first test verifies data and calculations. The second test verifies validation. The third test checks the empty-data state. You can add tests for null, the unmodifiable returned list, and new rules.

## 28. pom.xml for the Capstone

The POM sets Java release 17, adds JUnit for testing, configures Surefire, and writes Main-Class into the manifest so the JAR runs standalone:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>study-planner</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.study.StudyPlanApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

JUnit has test scope so it is not included in the application's runtime dependencies. The Maven Compiler Plugin uses release 17; the Maven JAR Plugin writes the main class. In a real project, add the Maven Wrapper so the team uses the same Maven version.

## 29. Build, Test, and Run the Capstone

From the directory containing pom.xml:

~~~bash
mvn clean verify
java -jar target/study-planner-1.0.0.jar
~~~

If the project already has the Maven Wrapper, use mvnw or mvnw.cmd depending on the operating system.

Expected test output:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Application output:

~~~text
STUDY_PLAN sessions=3
TOTAL_MINUTES=115
AVERAGE_MINUTES=38.3
~~~

If the build succeeds but the JAR does not run, check that the manifest has Main-Class, that the classes were packaged, and that the runtime supports the bytecode version. Do not just run the code in an IDE and assume the artifact is working.

## 30. Practice Debugging the Capstone

Introduce an intentional bug, such as changing minutes to 0. The test must fail because the constructor rejects the data. Read the failure report to identify which test caught the bug and the related source line.

Try additional scenarios:

- Topic is an empty string or whitespace only.
- A plan with no study sessions.
- Adding the same topic multiple times.
- Calling sessions() and attempting to modify the returned list.
- Adding a very large duration.
- Passing null to add.
- Running the application from the JAR after a clean build.

Each time you fix a bug, keep a test that reproduces it. When the test passes, run verify again to ensure the change did not break other behavior.

## 31. Add CI for the Project

Automatically build and test on every push or pull request. Example GitHub Actions workflow when the project has committed the Maven Wrapper:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify
        run: ./mvnw --batch-mode --no-transfer-progress clean verify
~~~

CI should use the same release target as the local build and save test reports on failure. Later you can add a matrix for multiple JDKs, static analysis, dependency scanning, and artifact uploads. Never put signing keys or secrets in the repository or logs.

## 32. Extend After the Capstone

Expand one feature at a time:

1. Persistence: save and load StudySession using Path/Files.
2. CLI: support add, list, remove, and summary.
3. Date/Time: attach study dates and filter by week.
4. Testing: add parameterized tests and integration tests.
5. Database: learn SQL/JDBC, transactions, and migrations.
6. HTTP: build an API after understanding request/response.
7. Packaging: create a ZIP distribution or runtime image with jlink.
8. Observability: add logging, metrics, and JFR when needed.
9. Security: validate input, check dependencies, and protect secrets.
10. Release: versioning, changelog, checksums, and release pipelines.

Each extension should have clear requirements, accompanying tests, and a runnable build. Avoid adding a framework before understanding the problem the framework solves.

## 33. Choose a Specialization Path

| Track | What to Learn Next |
|---|---|
| Backend/API | HTTP, REST, SQL, JDBC, transactions, Spring Boot or equivalent framework |
| Desktop | JavaFX, event-driven UI, persistence, and packaging |
| Data processing | Collections, Streams, SQL, batch processing, and concurrency |
| Cloud/services | HTTP client/server, containers, configuration, observability, and CI/CD |
| JVM/platform | Class loading, bytecode, garbage collection, JFR, profiling, and performance |
| Build/release engineering | Advanced Maven/Gradle, dependency verification, reproducible builds, and signing |

Whichever track you choose, you still need a foundation in the Java language, collections, exceptions, testing, Git, and build tools. Frameworks change faster than these fundamentals.

## 34. Learning Sequence by Completion Milestones

| Milestone | What to Do | Proof of Completion |
|---|---|---|
| Java language | Write classes, interfaces, records, exceptions, and generics | Multi-class program |
| Core API | Use collections, streams, date/time, and I/O | Correct data and file processing |
| Project structure | Separate packages, main/test sources, and resources | Well-structured project |
| Build | Use Maven or Gradle Wrapper | Clean build succeeds |
| Testing | Write unit and integration tests | Test report passes |
| Debugging | Use breakpoints, stack traces, and logs | Reproduce and fix a bug |
| Packaging | Create JAR/distribution and run the artifact | Artifact runs outside the IDE |
| Collaboration | Use Git and reviews | Clear commits/PRs |
| Specialization | Choose backend, desktop, cloud, or JVM | Complete project |

Move to the next milestone when you can explain and produce the current milestone's outcome on your own, not just when you have finished reading the documentation.

## 35. Common Mistakes When Moving Forward

- Learning Spring Boot before understanding classes, interfaces, exceptions, and collections.
- Adding dependencies without knowing their version, scope, or transitive dependencies.
- Only running via the IDE Run button without knowing how to build from the terminal.
- Writing business logic directly inside the main method.
- Not testing validation and boundary cases.
- Catching exceptions and ignoring them.
- Using static global state to share data.
- Committing JAR files/build outputs without a reason.
- Rebuilding a different artifact after having already tested a previous artifact.
- Learning multiple frameworks at once without finishing any project.

Keep the scope small, complete one end-to-end flow first, and then expand. A small, well-structured application with clear tests and a reproducible build connects far more skills than scattered code snippets.

## 36. Readiness Checklist for Your First Java Project

- [ ] Know how to use javac and java from the terminal.
- [ ] Understand packages, classes, interfaces, and exceptions.
- [ ] Know how to choose the right List, Set, and Map.
- [ ] Know how to use Path/Files for file operations.
- [ ] Create a project with main source and test source.
- [ ] Use Maven or Gradle Wrapper.
- [ ] Add dependencies with clear versions and scopes.
- [ ] Write JUnit tests for logic and boundary inputs.
- [ ] Debug using stack traces and breakpoints.
- [ ] Generate Javadoc for public APIs.
- [ ] Build a JAR and run that exact artifact.
- [ ] Use Git to save changes step by step.
- [ ] Have a README with build, test, and run commands.
- [ ] Know how to verify the hash and contents of an artifact before releasing.

If you have not checked off everything yet, pick one weak area and add it to the capstone. You do not need to wait until you know every API to start a project; the project itself is where concepts connect together.

## Further Reading

- Dev.java — [General Java Learning Path](https://dev.java/learn/).
- Dev.java — [Java Language: OOP, Generics, Exceptions and Pattern Matching](https://dev.java/learn/language/).
- Dev.java — [Collections and Streams](https://dev.java/learn/api/collections-and-streams/).
- Oracle — [JDK 26 Tool Specifications](https://docs.oracle.com/en/java/javase/26/docs/specs/man/index.html).
- Apache Maven — [Getting Started Guide](https://maven.apache.org/guides/getting-started/).
- Apache Maven — [Maven in 5 Minutes](https://maven.apache.org/guides/getting-started/maven-in-five-minutes.html).
- Gradle — [Getting Started and Beginner Tutorial](https://docs.gradle.org/current/userguide/getting_started.html).
- JUnit — [JUnit 5 User Guide](https://docs.junit.org/5.12.0/user-guide/).
- Oracle — [JDK Documentation and API References](https://docs.oracle.com/en/java/javase/26/).
