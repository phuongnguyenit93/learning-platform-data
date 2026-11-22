# Migrating a Project Using JAXB Off Implicit JDK Dependencies

## 1. Exercise Context and Objectives

A Java project developed on JDK 8 can use JAXB (Java Architecture for XML Binding) simply through imports such as `javax.xml.bind.JAXBContext`, `javax.xml.bind.Marshaller`, and `javax.xml.bind.annotation.XmlRootElement`. Back then, certain JAXB components were supplied alongside the JDK 8 distribution; `pom.xml` or `build.gradle` could **omit any JAXB declaration** while the program still compiled and ran.

When moving to JDK 11, 17, or 21, that assumption no longer holds. Under **JEP 320**, JDK 11 removed previously bundled Java EE/CORBA modules, including JAXB and JAX-WS. Newer JDKs still ship XML parsers, DOM, SAX, StAX, and many other Java SE APIs, yet **do not automatically supply the JAXB API along with a runtime implementation like the JDK 8 model**.

This exercise walks through how to:

1. Create a minimal JAXB project to reproduce the implicit JDK 8 dependency.
2. Run the exact same artifact on a newer JDK and distinguish compilation errors from runtime errors.
3. Declare both the **JAXB API** and **JAXB runtime provider** as explicit dependencies.
4. Choose one of two strategies: **keep `javax.xml.bind`** on the JAXB 2.3 track, or **migrate to `jakarta.xml.bind`** on JAXB 3/4.
5. Test marshalling/unmarshalling with real data, inspect transitive dependencies, and verify the packaged artifact.
6. Handle XJC/generated code, Activation, JPMS, classloaders, and XML security.
7. Finalize migration verification criteria, CI, and rollback readiness.

This is a lab to **execute in an isolated environment**. The commands in this guide are practical instructions, not confirmed execution results in the reader's environment. When applying to production, use official versions supported by your framework/vendor and your organization's dependency policy.

### Expected Outcome

After this exercise:

- The JAXB application no longer relies on an implicit JAXB module in the JDK.
- The compile classpath contains the JAXB API matching the source code.
- The runtime classpath includes a compatible provider when the application runs JAXB on its own.
- Code includes XML round-trip tests and explicit UTF-8 handling.
- Build/CI records the minimum JDK, dependency versions, and packaging method.
- The team understands **when adding dependencies alone is sufficient** and when migrating from `javax` to `jakarta` is mandatory.

## 2. Background: JAXB API Differs from JAXB Implementation

JAXB converts back and forth between Java objects and XML, commonly referred to as:

- **Marshalling:** Java object → XML.
- **Unmarshalling:** XML → Java object.
- **Binding metadata:** annotations, mappings, namespaces, and schema information.
- **Provider/runtime:** the implementation executing marshalling/unmarshalling.

An example:

```java
JAXBContext context = JAXBContext.newInstance(Customer.class);
Marshaller marshaller = context.createMarshaller();
Unmarshaller unmarshaller = context.createUnmarshaller();
```

Classes like `JAXBContext` and `Marshaller` come from the **API**. For the factory `JAXBContext.newInstance(...)` to work, the application requires a **JAXB provider** at runtime. For standalone applications on JDK 11+, the provider must be placed on the classpath/module path in a supported manner.

Diagram:

```text
Java application
      |
      | compile: JAXB API annotations, JAXBContext, Marshaller
      v
JAXB API
      |
      | runtime: locate JAXB provider
      v
JAXB implementation (e.g., GlassFish JAXB Runtime)
      |
      v
XML parser / serializer / supporting libraries
      |
      v
XML files / streams / messages
```

Having only the JAXB API JAR typically produces **compilation passing while `JAXBContext.newInstance` fails**. Having only the provider without an explicit API can prevent compilation or rely on an unstable transitive API. The lab's goal is declaring both roles deliberately.

## 3. Key History Before Choosing Versions

| Milestone | JAXB status and migration significance |
|---|---|
| JDK 8 | Many JDK distributions supply JAXB 2.x with `javax.xml.bind`, `xjc`, and `schemagen` in the toolset |
| JDK 9 | JAXB became a Java EE-related module, no longer resolved by default like a Java 8 classpath in many cases; could temporarily be enabled via `--add-modules java.xml.bind` |
| JDK 10 | Transitional phase remained, though bundled modules should not be treated as a long-term path |
| **JDK 11** | **JEP 320 removed `java.xml.bind` and previously bundled JAXB tools** |
| JDK 17 | No bundled JAXB; applications must manage external API/provider if using JAXB |
| JDK 21 | Same: external dependencies required; upgrading the JDK does not automatically convert `javax` to `jakarta` |
| Jakarta XML Binding 2.3.x | Some artifacts bear `jakarta.xml.bind` coordinates yet **still publish the `javax.xml.bind` package** |
| Jakarta XML Binding 3.x/4.x | API moved to the `jakarta.xml.bind` package; binary-incompatible with `javax` source/bytecode |

The easiest trap to fall into: **Maven artifact names and Java package namespaces do not always match**. For example, `jakarta.xml.bind:jakarta.xml.bind-api:2.3.3` belongs to the 2.3 line and supplies an API with the `javax.xml.bind` package. The 4.x line uses `jakarta.xml.bind`. Never pick a version solely by reading the groupId.

**Do not try the following workaround on JDK 11/17/21:**

```bash
java --add-modules java.xml.bind -jar app.jar
```

JDK 11+ no longer contains the `java.xml.bind` module in the runtime, so the flag cannot resurrect what has been removed. External dependencies or an actual migration are required.

## 4. Decision Flow Before Modifying Source Code

```text
Application currently using JAXB from JDK 8
               |
               v
Source / generated code imports javax.xml.bind?
               |
               +--- Yes
               |     |
               |     v
               |   Current framework still uses javax?
               |     |
               |     +--- Yes ---> Branch A: keep javax, add JAXB 2.3 API/runtime
               |     |
               |     +--- No  ---> Branch B: upgrade full stack to jakarta
               |
               +--- Already uses jakarta
                     |
                     v
               Select JAXB 3/4 API/runtime matching framework
               |
               v
         Build + runtime + XML contracts
               |
               v
          Test minimum supported JDK
```

**Branch A** is typically the minimal-change step when the goal is simply moving a legacy Java 8 application onto JDK 17/21 while continuing to use a `javax` framework.

**Branch B** fits when the application is migrating to a Jakarta-generation framework/server, such as a newer stack requiring `jakarta.*`. In that case, merely adding JAXB 2.3 will not resolve the API mismatch.

Do not accidentally mix APIs/providers from both branches in the same runtime. The two classes `javax.xml.bind.JAXBContext` and `jakarta.xml.bind.JAXBContext` have different binary names.

## 5. Preparing the Lab Environment

### 5.1. Requirements

- JDK 8 to reproduce the baseline if available in the practice environment.
- JDK 17 or 21 to test the target runtime.
- Maven 3.x and Maven Wrapper (if used by the project).
- An editor and terminal.
- Access to an authorized artifact repository.
- An empty project directory.

JDK 8 is not required for every step if unavailable; you can start from an existing `javax` project. However, a JDK 8 baseline illustrates how the implicit dependency formed.

### 5.2. Project Structure

```text
jaxb-migration-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/jaxb/
    │           ├── Customer.java
    │           └── App.java
    └── test/
        └── java/
            └── com/example/jaxb/
                └── JaxbRoundTripTest.java
```

In the baseline, we create two main classes with no test dependency yet. After switching to the new JDK, we add tests and the runtime provider.

### 5.3. Checking the Build Process JDK

Example:

```bash
java -version
javac -version
mvn -version
```

If using Maven Wrapper:

```bash
./mvnw -version
```

On PowerShell, you can use `.\mvnw.cmd -version`.

Note that `mvn -version` displays the Java runtime executing Maven. This may differ from the JVM used to run the application if a launcher or CI configures it separately. When writing migration reports, record the **compiler JDK, build JVM, and runtime JDK** whenever they differ.

## 6. Step 1 — Create a JAXB Model Under the javax Namespace

File `src/main/java/com/example/jaxb/Customer.java`:

```java
package com.example.jaxb;

import javax.xml.bind.annotation.XmlAccessType;
import javax.xml.bind.annotation.XmlAccessorType;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
import javax.xml.bind.annotation.XmlType;

@XmlRootElement(name = "customer")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(propOrder = {"name", "email"})
public class Customer {
    @XmlElement(required = true)
    private String name;

    @XmlElement(required = true)
    private String email;

    public Customer() {
        // JAXB requires an accessible no-arg constructor.
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
```

Explanation:

- `@XmlRootElement(name = "customer")` maps the object to the root `<customer>` element.
- `@XmlAccessorType(XmlAccessType.FIELD)` instructs JAXB to access fields directly.
- `@XmlType(propOrder = ...)` preserves XML element ordering per the defined mapping.
- `@XmlElement(required = true)` describes metadata/schema; **do not assume it automatically rejects invalid XML** without configuring validation.
- The no-arg constructor lets JAXB instantiate objects during unmarshalling.
- `javax.xml.bind.annotation.*` belongs to the legacy JAXB API line; it stays unchanged when following Branch A.

This model is simple enough to show dependency effects without being obscured by databases or SOAP frameworks.

## 7. Step 2 — Write a Marshal/Unmarshal Program

File `src/main/java/com/example/jaxb/App.java`:

```java
package com.example.jaxb;

import java.io.StringReader;
import java.io.StringWriter;

import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws Exception {
        Customer original = new Customer(
                "Nguyễn An",
                "an@example.test"
        );

        JAXBContext context = JAXBContext.newInstance(Customer.class);

        Marshaller marshaller = context.createMarshaller();
        marshaller.setProperty(
                Marshaller.JAXB_FORMATTED_OUTPUT,
                Boolean.TRUE
        );

        StringWriter xmlWriter = new StringWriter();
        marshaller.marshal(original, xmlWriter);

        String xml = xmlWriter.toString();
        System.out.println(xml);

        Unmarshaller unmarshaller = context.createUnmarshaller();
        Customer restored = (Customer) unmarshaller.unmarshal(
                new StringReader(xml)
        );

        System.out.println(
                "Round-trip: "
                + restored.getName()
                + " <" + restored.getEmail() + ">"
        );
    }
}
```

Expected output **in terms of content**:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<customer>
    <name>Nguyễn An</name>
    <email>an@example.test</email>
</customer>
```

Declaration formatting, whitespace, and attribute order depend on the specific API/provider/configuration; **do not compare XML by raw strings when the contract only requires identical structure and values**.

Important: `StringWriter` holds data in a Java `String`. The XML declaration may state UTF-8, yet that alone does not govern the bytes written to a file. The file I/O section later in this lesson specifies `StandardCharsets.UTF_8` explicitly.

## 8. Step 3 — Reproduce Implicit JAXB Dependency on JDK 8

### 8.1. Baseline POM Simulating a Java 8 Project

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jaxb-migration-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.source>8</maven.compiler.source>
        <maven.compiler.target>8</maven.compiler.target>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

This POM **does not declare JAXB**. When compiled on a JDK 8 with bundled JAXB, `javax.xml.bind.*` sources still compile because the APIs come from the JDK.

The versions and build settings in the template serve the lab. For a real project, use Maven/Compiler Plugin versions per your support policy; do not blindly apply an old POM across an entire system.

### 8.2. Compile Using JDK 8

Verify the terminal/CI actually uses JDK 8:

```bash
mvn -version
mvn clean package
```

Command to test running the class inside the JAR:

```bash
java -cp target/jaxb-migration-lab-1.0.0.jar \
  com.example.jaxb.App
```

The program can run **without `jaxb-api.jar` or `jaxb-runtime.jar`** in the POM. That exact implicit dependency is what we must eliminate during migration.

### 8.3. Record the Baseline

Save:

- Maven and JDK versions.
- Artifact SHA-256.
- Sample XML output and round-trip result.
- Encoding of XML when actually exported to a file.
- Schemas/XSDs if used by the application.
- Set of technologies relying on JAXB such as SOAP, JPA converters, and generated DTOs.

If no JDK 8 environment is available, you can skip the reproduction step and start from existing classes/POM, yet record the real baseline rather than pretending you ran it.

## 9. Step 4 — Run the Unmodified Java 8 Artifact on JDK 17/21

**Do not rebuild at this step.** We want to demonstrate the runtime's independent impact.

Suppose the JAR was just built on JDK 8; use a terminal targeting a Java 17 runtime:

```bash
"$JAVA17_HOME/bin/java" -version
"$JAVA17_HOME/bin/java" \
  -cp target/jaxb-migration-lab-1.0.0.jar \
  com.example.jaxb.App
```

`JAVA17_HOME` is a placeholder variable; replace it with the real JDK path.

A symptom that can appear:

```text
java.lang.NoClassDefFoundError:
  javax/xml/bind/JAXBContext
```

or `ClassNotFoundException` appearing in the chain, depending on the class-loading site and how the launcher/framework handles it.

### 9.1. What We Just Proved

- The Java 8 class file itself is not necessarily rejected by the Java 17/21 JVM.
- The application invokes a JAXB class no longer present in the JDK runtime.
- The first problem lies in **runtime dependency availability**.
- We **do not yet need to conclude** we must rewrite annotations, change namespaces, or upgrade every framework.

### 9.2. Do Not Confuse with Compilation Errors

If you subsequently run Maven build on JDK 17 without adding a JAXB dependency, an error like this will appear:

```text
package javax.xml.bind does not exist
package javax.xml.bind.annotation does not exist
```

That is a **compile classpath** error. In the test running the unmodified Java 8 JAR, the symptom is primarily **runtime linkage/class loading**. Same dependency root cause, yet two distinct layers; record them separately.

### 9.3. Why Does --add-modules Not Solve It on JDK 17?

Starting in JDK 11, the `java.xml.bind` module was removed. `--add-modules java.xml.bind` was only useful in JDK 9/10 where the module still existed; it cannot bring the module back in JDK 17/21.

## 10. Step 5 — Branch A: Keep javax.xml.bind and Add Explicit Dependencies

This is the lowest-source-churn path for a project still using JAXB 2.x and `javax`-compatible frameworks.

### 10.1. Choose the Right API and Runtime Generation

An illustrative set of coordinates:

| Role | Maven artifact | Sample version | Java namespace |
|---|---|---|---|
| JAXB API | `jakarta.xml.bind:jakarta.xml.bind-api` | `2.3.3` | **`javax.xml.bind.*`** |
| JAXB runtime/provider | `org.glassfish.jaxb:jaxb-runtime` | `2.3.8` | Serves JAXB 2.3/`javax` |
| Activation | Compatible Activation library actually required by runtime | Per dependency graph | Usually `javax.activation.*` in legacy line |

The confusing point is that **the API artifact has `jakarta` in its name yet version 2.3.3 still contains `javax.xml.bind`**. Inspect the actual packages inside the JAR if your tooling allows.

Do not pair JAXB API 4.x with `javax.xml.bind` source: API 4.x uses the `jakarta.xml.bind` namespace.

### 10.2. POM for JDK 17 with API + Runtime

Complete example POM using JDK 17 to compile the current project **without changing `javax` imports**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jaxb-migration-lab</artifactId>
    <version>1.1.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <jaxb.api.version>2.3.3</jaxb.api.version>
        <jaxb.runtime.version>2.3.8</jaxb.runtime.version>
        <junit.jupiter.version>5.10.2</junit.jupiter.version>
    </properties>

    <dependencies>
        <!-- API: application code imports javax.xml.bind.* -->
        <dependency>
            <groupId>jakarta.xml.bind</groupId>
            <artifactId>jakarta.xml.bind-api</artifactId>
            <version>${jaxb.api.version}</version>
        </dependency>

        <!-- Provider: JAXB code executing at runtime -->
        <dependency>
            <groupId>org.glassfish.jaxb</groupId>
            <artifactId>jaxb-runtime</artifactId>
            <version>${jaxb.runtime.version}</version>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.jaxb.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

This template uses previously published releases to illustrate a JAXB 2.3 branch. For production projects, pin versions per your current BOM and support/security matrix; do not treat the illustrative numbers as the newest or always optimal choice.

Scope explanation:

- The API is needed on the **compile classpath** because source code imports `JAXBContext` and JAXB annotations.
- The API must also be available at runtime.
- `jaxb-runtime` has **runtime** scope because source code in the lab does not directly import the provider's implementation classes.
- JUnit is used only in tests.
- Maven's default thin JAR **does not embed** `jaxb-runtime` and dependencies into the final JAR file; the launch command must supply an appropriate classpath or distribution.

### 10.3. Build with JDK 17

```bash
mvn -version
mvn clean test
```

If JDK 17 is the compiler, `maven.compiler.release=17` allows Java 17 source and bytecode output. If the product must still support JDK 8 or 11, choose compatible release targets and dependency versions accordingly, then test on the **minimum runtime JDK**—do not set 17 if policy still supports older runtimes.

### 10.4. Run with the Maven Exec Plugin

```bash
mvn -q exec:java
```

The `exec:java` goal constructs a classpath from project dependencies per plugin configuration and version. It is convenient for the lab, yet not proof that a thin JAR can run standalone via `java -jar`.

### 10.5. Success Criteria That Must Be Verified

- The project compiles without a JAXB module from the JDK.
- `JAXBContext.newInstance(Customer.class)` creates a context.
- Marshalling produces XML containing `customer/name/email`.
- Unmarshalling restores `Customer`.
- Tests with Vietnamese data remain unaltered.
- No `NoClassDefFoundError` or missing-provider errors occur.

Do not rely merely on "BUILD SUCCESS"; the provider may only be loaded when the factory executes, so tests must actually invoke marshaller/unmarshaller.

## 11. Step 6 — Write a Round-Trip Regression Test

File `src/test/java/com/example/jaxb/JaxbRoundTripTest.java`:

```java
package com.example.jaxb;

import java.io.StringReader;
import java.io.StringWriter;

import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JaxbRoundTripTest {

    @Test
    void shouldMarshalAndUnmarshalVietnameseText() throws Exception {
        Customer original = new Customer(
                "Nguyễn An",
                "an@example.test"
        );

        JAXBContext context = JAXBContext.newInstance(Customer.class);

        Marshaller marshaller = context.createMarshaller();
        StringWriter output = new StringWriter();
        marshaller.marshal(original, output);

        String xml = output.toString();
        assertTrue(xml.contains("<customer"));
        assertTrue(xml.contains("Nguyễn An"));

        Unmarshaller unmarshaller = context.createUnmarshaller();
        Customer restored = (Customer) unmarshaller.unmarshal(
                new StringReader(xml)
        );

        assertEquals("Nguyễn An", restored.getName());
        assertEquals("an@example.test", restored.getEmail());
    }
}
```

Run:

```bash
mvn clean test
```

This test matters more than a `Class.forName("javax.xml.bind.JAXBContext")` check because it verifies the API **and** provider working together.

### 11.1. How Should Results Be Verified?

- The test is discovered and executed by the test runner, not skipped.
- No provider lookup exception occurs.
- The XML contains the expected root, fields, and Unicode characters.
- Unmarshalling produces an object of the exact type and values.
- Source/target compiler levels are printed/recorded in CI.

### 11.2. Test XML by Semantics, Without Relying on Whitespace

A JAXB provider may add or omit the XML declaration, alter whitespace in formatted output, or vary attribute ordering in XML. Those differences do not necessarily break the XML contract.

For stricter contracts, use XMLUnit, schema validation, or a DOM/XPath parser to compare values/namespaces. Compare full strings only when byte-for-byte formatting is truly a product requirement.

## 12. Step 7 — Simulate Having Only the API Without the Runtime Provider

To understand why two dependencies are necessary, on a **separate lab branch**, temporarily remove the `jaxb-runtime` dependency from the POM and rerun:

```bash
mvn clean test
```

A `JAXBException` can occur because no implementation/provider is found—for example, an exception chain mentioning `ContextFactory`, ServiceLoader, or a message stating no JAXB implementation was found.

The exact message is not guaranteed identical across versions/providers. What must be confirmed is:

- The compiler still has the API needed to compile.
- At runtime, creating `JAXBContext` or marshalling/unmarshalling fails.
- Restoring the right-generation provider makes tests work again.

**Do not keep this intentional failure change on the main branch.** This is purely a negative test to understand API/implementation separation.

### 12.1. Why Can a Provider Be Missing Even When the JAR Is Declared?

Possible causes include:

- Dependency wrongly placed in `test`, `provided`, or `compileOnly` scope.
- Thin JAR run without a runtime classpath.
- Fat JAR/shading stripped `META-INF/services`.
- Application server uses a separate classloader.
- Provider was excluded during transitive dependency resolution.
- Provider version does not match the API generation.
- OSGi/JPMS module resolution mismatch.

Inspect the dependency graph and actual artifact before adding multiple providers "just to be safe."

## 13. Step 8 — Inspect the Maven Dependency Graph

### 13.1. View the Dependency Tree

```bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
```

Verification goals:

- Correct JAXB API version is present.
- JAXB runtime/provider is present.
- Activation dependencies are present if required by the provider.
- No two API JARs contain `javax.xml.bind` at different versions.
- No JAXB 4.x is pulled into a branch using `javax`.
- No unintended mix of old and new providers exists.
- The runtime dependency set is genuinely supplied by packaging/launch.

Maven dependency resolution cannot automatically detect every duplicate class located across **two different artifact coordinates**. If one branch uses both `javax.xml.bind:jaxb-api` and `jakarta.xml.bind:jakarta.xml.bind-api:2.3.x`, both may contain `javax.xml.bind` classes. Choose one consistent API owner.

### 13.2. Effective POM

```bash
mvn help:effective-pom
```

In projects with multiple parents/BOMs, the effective version can differ from what is directly visible in the POM. Inspect `dependencyManagement`, Maven profiles, and module overrides.

### 13.3. Distinguish Runtime Errors from Plugin Errors

If JAXB is used by an XJC codegen plugin during the build, the plugin has its own classpath separate from application dependencies. Adding `jaxb-runtime` to project `<dependencies>` will not necessarily make an old XJC plugin run on a newer Maven JVM.

Conversely, adding a library to the plugin realm does not guarantee the production runtime has a JAXB provider.

## 14. Step 9 — Packaging When the Application Is a Thin JAR

### 14.1. Why Can `java -jar` Still Fail?

When Maven builds a default thin JAR, `jaxb-migration-lab-1.1.0.jar` holds application classes/resources yet generally **does not contain dependency JARs**.

Hence:

```bash
java -jar target/jaxb-migration-lab-1.1.0.jar
```

may fail to run because:

1. There is no `Main-Class` manifest entry, or
2. `jaxb-api`/`jaxb-runtime` are not on the runtime classpath.

Do not conclude POM dependencies are wrong just because you used the wrong packaging/launcher command.

### 14.2. Valid Distribution Strategies

- Use the Maven Exec Plugin inside the lab.
- Build an application distribution containing a `bin/` launcher and `lib/` runtime dependencies.
- Use a supported framework executable JAR plugin.
- Use Maven Shade/Assembly or Gradle Shadow when a single artifact is needed, while preserving service metadata.
- Use a container image copying the app + runtime JARs with an explicit classpath.
- Use an application server supplying the provider per contract, with appropriate scope.

Example distribution:

```text
jaxb-app/
├── bin/
│   └── launch.sh
├── app/
│   └── jaxb-migration-lab.jar
└── lib/
    ├── jakarta.xml.bind-api-2.3.3.jar
    ├── jaxb-runtime-2.3.8.jar
    └── ...other-runtime-jars...
```

A POSIX launcher might use:

```bash
java -cp "app/jaxb-migration-lab.jar:lib/*" \
  com.example.jaxb.App
```

Relative paths work only when the working directory matches. For production, use a launcher script resolving paths relative to its own location and check Windows/Linux differences.

### 14.3. ServiceLoader and Shaded JARs

JAXB implementations may rely on provider-discovery metadata. When creating a fat JAR, the plugin must merge service entries properly if multiple JARs have `META-INF/services`.

If shading drops/overwrites service descriptors, API and provider classes might both sit inside the fat JAR while `JAXBContext.newInstance` still fails to find the implementation.

Do not relocate `javax.xml.bind` or `jakarta.xml.bind` API packages to "dodge conflicts": XML bindings/frameworks look for standard binary names.

## 15. Step 10 — Branch A with Gradle

If the project uses Gradle instead of Maven, separate the compile API and runtime implementation similarly.

### 15.1. Groovy DSL (Java Application)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation(
        'jakarta.xml.bind:jakarta.xml.bind-api:2.3.3'
    )

    runtimeOnly(
        'org.glassfish.jaxb:jaxb-runtime:2.3.8'
    )

    testImplementation(
        'org.junit.jupiter:junit-jupiter:5.10.2'
    )
}

application {
    mainClass = 'com.example.jaxb.App'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

This example requires a Gradle Wrapper supporting the corresponding JDK/toolchain; an overly old Gradle version may not recognize `java.toolchain` or may fail to run on JDK 17. Choose a Wrapper version matching the Gradle and plugin support matrix.

Run in an authorized lab project:

```bash
./gradlew --version
./gradlew clean test
./gradlew run
```

Do not use `compileOnly` for the JAXB API if the runtime application needs that class without another container providing it. `runtimeOnly` is appropriate for the provider when source code does not directly import implementation classes.

### 15.2. Inspecting the Resolved Graph

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Check that `runtimeClasspath` contains the provider and required supporting libraries; do not inspect only `compileClasspath`.

### 15.3. Gradle `application` Distribution

The `application` plugin can assemble a distribution with launcher scripts and runtime dependencies per plugin configuration. For small Java CLIs, this is often a simpler classpath management approach than constructing a fat JAR.

However, do not assume the default `jar` task embeds dependency JARs; inspect the distribution or run the plugin-generated script.

## 16. Step 11 — Branch B: Migrating Fully to jakarta.xml.bind

Branch A preserves `javax.xml.bind` sources. When upgrading to a modern Jakarta stack, migrating source/annotations to `jakarta.xml.bind` may be mandatory.

This is a **source and binary compatibility migration**, not merely adding a runtime dependency.

### 16.1. Updating Package Imports in the Model

`Customer.java` on Branch B:

```java
package com.example.jaxb;

import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(name = "customer")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(propOrder = {"name", "email"})
public class Customer {
    @XmlElement(required = true)
    private String name;

    @XmlElement(required = true)
    private String email;

    public Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
```

### 16.2. Updating Imports in App and Tests

In `App.java` and `JaxbRoundTripTest.java`:

```java
// Branch A, JAXB 2.3:
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;

// Branch B, JAXB 4.x:
// import jakarta.xml.bind.JAXBContext;
// import jakarta.xml.bind.Marshaller;
// import jakarta.xml.bind.Unmarshaller;
```

In real Branch B code, **delete the `javax` imports and use the `jakarta` imports**; do not keep both sets in the same source file because of identical simple names and differing contracts.

Other annotations to scan include `@XmlElement`, `@XmlAttribute`, `@XmlType`, `@XmlAccessorType`, `@XmlJavaTypeAdapter`, `@XmlSeeAlso`, `package-info.java`, and XJC-generated classes.

### 16.3. Jakarta 4.x API and Provider

Illustrative Maven dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
        <version>4.0.2</version>
    </dependency>

    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>4.0.5</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Select truly compatible versions matching Jakarta XML Binding 4.x and your framework's dependency management. Versions here illustrate one generation, not a recommendation for the newest version in the current year.

On Branch B, `jakarta.xml.bind-api` 4.x provides the `jakarta.xml.bind.*` package. `jaxb-runtime` 4.x provides the matching provider. Activation modules must align with the Jakarta 2.x ecosystem if required by the stack; inspect the transitive dependency tree rather than forcing both legacy and new Activation onto the same runtime.

### 16.4. Corresponding Gradle Configuration

```groovy
dependencies {
    implementation(
        'jakarta.xml.bind:jakarta.xml.bind-api:4.0.2'
    )

    runtimeOnly(
        'org.glassfish.jaxb:jaxb-runtime:4.0.5'
    )
}
```

When switching sources to `jakarta.*`, update test imports and generated classes. Do not just bump versions and forget the source code: the compiler will report `package javax.xml.bind does not exist` once API 4.x is chosen.

### 16.5. Why Can't You Just Swap the JAR?

Two distinct classes:

```text
javax.xml.bind.JAXBContext
jakarta.xml.bind.JAXBContext
```

have different binary names. Bytecode compiled to invoke `javax.xml.bind.JAXBContext` will not automatically invoke `jakarta.xml.bind.JAXBContext` when swapping dependencies.

If an older library/framework still demands `javax` while the application moves to `jakarta`, upgrade that library or establish an explicit adapter boundary. Do not treat a 4.x API JAR as a "transparent drop-in replacement" for the 2.x API.

## 17. Deciding Between Keeping javax or Migrating to jakarta Based on Framework

| Target environment | Generally suitable strategy |
|---|---|
| Legacy Java SE CLI/batch, only upgrading JDK to 17/21 | Keep `javax` + external JAXB 2.3 runtime unless otherwise required |
| Legacy Java EE app still using `javax` | Do not change only the JAXB namespace alone; check server/runtime ownership |
| Spring Framework 5 / Spring Boot 2 legacy stack | Usually still uses `javax`-line Java EE interfaces; verify exact version/support |
| Spring Framework 6 / Spring Boot 3 modern stack | Use Jakarta APIs in needed integrations; choose matching-generation provider |
| Jakarta EE 9+ application server | Inspect server-provided platform/profile and JAXB version; avoid bundling duplicate provider |
| Plain servlet container | Does not bundle a JAXB runtime by default; application supplies it if needed |
| Reusable library supporting both ecosystems | Consider separate artifacts/adapters; avoid exposing incompatible JAXB types in shared APIs |

This is architectural guidance, not a substitute for detailed framework/vendor compatibility matrices. In particular, **upgrading the JDK** and **upgrading Java EE to Jakarta EE** are two distinct decisions; they can be executed in two separate phases to reduce risk where the stack allows.

## 18. Step 12 — Test Real XML Data, Not Only the Customer Example

A tiny example may pass, yet production JAXB models are more complex:

- Namespace URIs, prefixes, and default namespaces.
- `@XmlSchema` in `package-info.java`.
- `JAXBElement<T>` and `ObjectFactory`.
- `@XmlElementRef`, `@XmlAnyElement`, and polymorphism.
- `@XmlAdapter` handling dates/currency/IDs.
- Required attributes, optional elements, and null semantics.
- XML Schema validation (XSD).
- Date/time formats, decimals, and locales.
- CDATA, escaped characters, and Unicode.
- Collections, inheritance, and `xsi:type`.
- Mixed content, comments, and unknown elements.
- SOAP headers/attachments if integrating JAX-WS.

### 18.1. Testing the XML Contract

For business data, add tests:

1. Marshal objects according to the model.
2. Parse the XML with a reliable parser.
3. Compare root names, namespaces, and element/attribute names.
4. Unmarshal XML fixtures from partners or previous versions.
5. Verify object values and business invariants.
6. Validate against XSD if required by the contract.
7. Run negative tests for XML with missing/invalid fields.
8. Verify encoding and parser security.

If the contract genuinely enforces element ordering, `@XmlType(propOrder = ...)` and XSD should be tested. Do not merely check getter method values while ignoring XML namespaces.

### 18.2. Testing Bidirectional Compatibility During Rolling Deployment

If old and new versions run concurrently:

- Can the new JAXB version read XML written by the old version?
- Can the old version read XML written by the new version?
- Have any namespace URIs or element names changed?
- Has `ObjectFactory`/XSD binding output changed?
- Do external systems require a specific XML declaration/encoding?

A migration changing only the Java package `javax` → `jakarta` **does not necessarily change XML namespace URIs**, though generated code or updated configuration can alter XML output. Verify against fixtures and schemas rather than guessing.

## 19. Step 13 — Ensuring UTF-8 Encoding on File Export

A commonly misunderstood migration cause is default-encoding changes, especially on JDK 18+ where JEP 400 standardized UTF-8 as the default charset for many Java APIs.

### 19.1. Example That Should Not Rely on Defaults

```java
// Charset of both operations depends on API/default:
byte[] bytes = xml.getBytes();
String decoded = new String(bytes);
```

These operations can vary across environments, especially when legacy data does not use UTF-8.

### 19.2. Correct Example When the Contract Requires UTF-8

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.Writer;
import javax.xml.bind.Marshaller;

// Create marshaller from a JAXBContext with a valid provider.
Marshaller marshaller = context.createMarshaller();
marshaller.setProperty(Marshaller.JAXB_ENCODING, "UTF-8");

Path output = Path.of("customer.xml");

try (Writer writer = Files.newBufferedWriter(
        output, StandardCharsets.UTF_8)) {
    marshaller.marshal(customer, writer);
}
```

The example uses `Path.of`, fitting JDK 11+; if source must compile for Java 8, use `Paths.get(...)` instead of `Path.of(...)`.

**Do not** assume setting `Marshaller.JAXB_ENCODING` fixes every case: if you pass a `Writer` configured with a different encoding to the marshaller, the final bytes are handled by that `Writer`. At file/network boundaries, select a consistent charset per the contract.

### 19.3. Byte-Level Testing

- Verify written bytes are valid UTF-8.
- Read back using explicit UTF-8.
- Test with accented Vietnamese data.
- Verify the XML declaration matches the actual encoding.
- Test legacy files with other encodings if they must be supported.
- Do not silently mutate persisted data when upgrading the JDK.

## 20. Step 14 — JAXB and XML Security

JAXB typically relies on underlying XML parsers. When XML data originates from untrusted sources, control **external entities**, DTDs, schema fetching, and parser resources.

### 20.1. XXE Risk

Malicious XML can reference an external entity or resource:

```xml
<!DOCTYPE customer [
  <!ENTITY ext SYSTEM "file:///some/local/file">
]>
<customer>
    <name>&ext;</name>
    <email>an@example.test</email>
</customer>
```

This example illustrates the risk only. Do not feed malicious inputs on a production machine to "inspect visually"; run security tests in an isolated environment.

### 20.2. Designing a Safe Parser According to Contract

One approach is creating a StAX parser with external entities/DTDs restricted, then passing the reader to JAXB:

```java
import java.io.StringReader;
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Unmarshaller;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamReader;

JAXBContext context = JAXBContext.newInstance(Customer.class);
Unmarshaller unmarshaller = context.createUnmarshaller();

XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, Boolean.FALSE);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
        Boolean.FALSE
);

XMLStreamReader reader = factory.createXMLStreamReader(
        new StringReader(xmlFromUntrustedSource)
);

try {
    Customer customer = (Customer) unmarshaller.unmarshal(reader);
    // Process customer only after business checks pass.
} finally {
    reader.close();
}
```

This is a **design pattern for discussing parser hardening**, not a safety guarantee across every provider/version. Verify that the `XMLInputFactory` implementation supports/enforces the properties, and enforce resolvers, external schema access, entity expansion/size/time limits, input length, and XSD validation where needed. If a property is unsupported, never silently ignore it and assume the parser is safe.

With SAX/DOM or JAXB APIs receiving an `InputStream` directly, apply matching security settings for the actual parser/provider. Do not simply believe upgrading the JAXB dependency eliminates XXE on its own.

### 20.3. XSD Validation Also Has External Access Risks

When using `SchemaFactory`, you may need to block external DTD/schema fetching per policy—for example, using `XMLConstants.ACCESS_EXTERNAL_DTD` and `ACCESS_EXTERNAL_SCHEMA` where supported by the parser.

If a legitimate application needs to import XSDs from internal paths, supply a controlled allowlist resolver rather than enabling arbitrary network fetching.

## 21. Step 15 — XJC and schemagen Are No Longer Supplied by the JDK

JAXB involves more than API/runtime. Many Java 8 projects use tools such as:

- **XJC:** generates Java classes from XSD.
- **schemagen:** generates XSD from annotated Java classes.
- **wsimport/wsgen:** part of JAX-WS tooling, potentially involving SOAP/JAXB models.

When upgrading to JDK 11+, tools previously bundled in the JDK were removed under JEP 320. Do not merely add API/runtime and assume the JDK's `xjc` or `schemagen` commands will reappear.

### 21.1. Clues in Build Scripts

Search for:

```text
xjc
schemagen
wsimport
wsgen
jaxb2-maven-plugin
maven-jaxb2-plugin
jaxb-maven-plugin
xjcGenerate
generateSources
```

This is a list of common tool/plugin names; specific plugins may differ. Check actual build files and CI scripts.

### 21.2. Selecting an External Tool Matching the API Generation

A standard workflow:

```text
XSD files
   |
   v
Pinned XJC tool/plugin + matching JAXB generation
   |
   v
Generated Java sources (javax or jakarta)
   |
   v
Java compiler with target release
   |
   v
Application JAR + API/runtime dependencies
```

If application sources stay on `javax`, generated classes must match the `javax` generation. If moving to Jakarta 4.x, the codegen tool must emit `jakarta.xml.bind.annotation.*`.

Do not place generated sources from both namespaces into the same source set outside an explicitly designed setup.

### 21.3. Plugin Dependencies Differ from Application Dependencies

A Maven XJC plugin has its own **plugin realm**; a Gradle XJC task has its own **configuration**. Declare generator/tool dependencies and versions at the right layer.

If a plugin's `xjc` runs on a newer Maven JDK and fails due to bytecode/JPMS/removed APIs, that failure will not necessarily be fixed merely by adding `jaxb-runtime` to application dependencies.

### 21.4. Reproducible Generated Source

Record:

- XSD checksums/versions.
- XJC version.
- Plugin version and Maven/Gradle Wrapper.
- Java runtime running the generator.
- Generated package names.
- Source encoding.
- Binding configuration files.
- Namespace migration and customization scripts.
- Diffs of generated output.

Avoid manually editing generated files for a one-off fix: regenerating on CI will overwrite the edit or produce hard-to-explain diffs.

## 22. Step 16 — JAXB Activation and Supporting Dependencies

### 22.1. What Is Activation?

Some JAXB/JAX-WS use cases handling attachments, MIME, or `DataHandler` may use the Activation API/runtime. On JDK 8, Activation was also among the APIs that could be supplied by the JDK; starting in JDK 11, it is no longer bundled under JEP 320.

When migrating dependencies:

- Check whether sources import `javax.activation.*` or `jakarta.activation.*`.
- Verify the runtime provider pulls the matching Activation generation.
- Do not bundle two APIs with identical package/binary names unintentionally.
- Run attachment/MIME/MTOM tests if used by the system.
- Check licenses, vulnerabilities, and vendor support.

### 22.2. Why Not Just Add Every Activation JAR?

Artifacts from different generations can cause duplicate classes or mismatches between the JAXB API and provider. An older library named `jakarta.activation` may still contain the `javax.activation` namespace; newer releases use `jakarta.activation`.

Inspect the Maven/Gradle dependency tree and actual JAR packages. Choose a consistent runtime set supported by your framework/vendor, instead of piling on JARs just to silence an immediate `ClassNotFoundException`.

### 22.3. When Must Activation Be Declared Directly?

If application sources directly import Activation types, the matching API dependency should be declared explicitly. If only the JAXB provider uses Activation internally, it can remain a runtime transitive dependency managed by the provider/BOM—provided the final artifact truly contains the required libraries.

## 23. Step 17 — Testing JPMS and Module Path When Modularized

### 23.1. Classpath First, Module Path Second

A Java 8 application can continue running on the classpath under JDK 17/21. Upgrading the JDK does not automatically force creating `module-info.java`.

To isolate the JAXB migration, get the application working on the classpath first, then address JPMS migration separately if the product requires modules.

### 23.2. With Named Modules

When using the module path, you must:

- Identify the actual module name of the JAXB API JAR using `jar --describe-module`.
- Declare the appropriate `requires` in `module-info.java`.
- Ensure the JAXB provider is resolved.
- Open the model package for reflection as needed by the provider.
- Verify module readability and provider discovery.

Conceptual example for Jakarta JAXB 4.x:

```java
module com.example.jaxb.app {
    requires jakarta.xml.bind;

    opens com.example.jaxb to jakarta.xml.bind;
}
```

This example illustrates the module/API relationship and reflective access; with an actual provider/library, you may need to add or adjust `opens` targets per the implementation's requirements. Do not copy it for JAXB 2.3 without inspecting the module name of the actual API JAR.

### 23.3. Avoid Using --add-opens as a First Resort

If module access fails, inspect the root cause and module descriptor. Prefer declaring proper `opens` on the package containing the JAXB model rather than opening broad JDK internals with `--add-opens` in production.

An `InaccessibleObjectException` when the provider accesses fields may stem from model module encapsulation; it is not necessarily a JDK Java base issue.

## 24. Step 18 — Testing Applications Running on a Server Rather Than Java SE

### 24.1. Servlet Containers Do Not Guarantee JAXB

A WAR deployed on a servlet container like Tomcat/Jetty may require JAXB API/runtime inside `WEB-INF/lib` if the application uses JAXB and the container does not provide the matching implementation.

Do not mark JAXB as `provided` just because it is a "Java EE API." Scope must match the **actual runtime owner**.

### 24.2. Jakarta EE Application Servers May Already Supply JAXB

A Jakarta EE server with the right profile/version may supply a JAXB implementation and manage the provider/classloader. In that case, the application might compile against the JAXB API with `provided` scope per platform policy; bundling an extra application provider could cause classloader conflicts.

Verify:

- Server vendor/version.
- Jakarta EE Platform/Profile capabilities.
- JAXB API generation.
- The provider actually integrated by the server.
- Server classloader policy.
- WAR/EAR packaging contents.
- Whether using an application-bundled JAXB provider is vendor-supported if desired.

Do not copy a standalone CLI POM directly onto a full Jakarta EE application server while ignoring the runtime owner.

### 24.3. Spring Boot Executable JARs

A framework-packaged executable JAR has its own runtime classpath. When adding JAXB dependencies to Maven/Gradle, inspect the repackaged/bootJar output and test the app through the actual launcher.

If a newer framework version transitions from `javax` to `jakarta`, JAXB annotations/API must follow the framework's support matrix. Do not combine a Jakarta-generation Spring Boot with libraries tied to `javax` JAXB and assume interoperability.

## 25. Step 19 — Testing the JAXB Provider via the Deployed Artifact

### 25.1. Testing in Maven Does Not Equal Testing the Production Launcher

`mvn test` may pass because the test classpath contains dependencies. Yet a production thin JAR holding only the main JAR without `lib/` will still fail when creating `JAXBContext`.

Tests must cover:

1. Compiling sources.
2. Executing round-trip tests on the target JDK.
3. Packaging the artifact under the actual deployment model.
4. Listing runtime dependencies.
5. Launching **the exact artifact/distribution to be deployed**.
6. Exercising real XML/attachment workflows.
7. Checking logs/provider discovery.
8. Comparing output/serialized data against baseline.

### 25.2. Inspecting WAR/JAR Contents

Examples:

```bash
jar tf target/jaxb-migration-lab-1.1.0.jar
jar tf target/application.war
```

For WARs, check `WEB-INF/lib`. For executable JARs, check nested libraries or manifest/launcher. For thin JARs, check the distribution `lib/` directory.

Do not rely solely on `jar tf` of the main JAR to infer anything about external runtime JARs outside it.

### 25.3. Do Not Assert Provider Implementation Class Names Unnecessarily

You can print the provider name for diagnostics:

```java
JAXBContext context = JAXBContext.newInstance(Customer.class);
System.out.println(context.getClass().getName());
```

However, do not write business tests coupled to a specific internal implementation class name unless it is an explicit product contract. Internal class names can change across provider releases while behavior remains accurate.

## 26. Step 20 — Common Errors and Root Causes

| Symptom | Possible cause | First check |
|---|---|---|
| `package javax.xml.bind does not exist` | `javax` sources, but API missing from compile classpath | Maven/Gradle compile dependencies |
| `package jakarta.xml.bind does not exist` | `jakarta` sources, but API 3/4 not declared | API generation, dependencies |
| `NoClassDefFoundError: javax/xml/bind/JAXBContext` | JDK 11+ runtime does not provide legacy API; artifact lacks JAR | Runtime classpath/packaging |
| `NoClassDefFoundError: jakarta/xml/bind/JAXBContext` | Runtime missing Jakarta JAXB API | App packaging and runtime graph |
| `JAXBException` provider not found | API present without implementation or SPI failed | Runtime provider/service metadata |
| `ClassNotFoundException: ...ContextFactory` | Provider discovery seeking missing/mismatched implementation | Provider JAR, API generation |
| `NoSuchMethodError` in JAXB | Conflicting API/provider/transitive lib versions | Dependency graph + loaded class sources |
| `ClassCastException` between API types | Two classloaders or mixed namespaces/providers | Server loader and duplicate JARs |
| XJC fails to run after JDK 11 | Previously bundled tool was removed | Codegen plugin/tool dependencies |
| Generated code still imports `javax` | Generator not upgraded/retargeted | XJC version, XSD bindings |
| JAXBContext builds yet XML has wrong namespace | Changed `package-info`, schema, or annotations | XML fixtures + XSD |
| Corrupted Unicode diacritics | Different charset/default I/O | Byte-level UTF-8 contract |
| XXE/security warning | Parser unhardened or outdated dependency | Secure parser/XSD settings |
| WAR passes tests yet fails on server | Different scope/classloader/provider owner | Server version + `WEB-INF/lib` |
| Tests pass yet `java -jar` fails | Thin JAR lacks runtime dependencies/manifest | Launcher and packaging |
| `UnsupportedClassVersionError` | Provider or tool compiled for higher JDK than runtime | Class-file major version and JDK |
| `InaccessibleObjectException` | JPMS reflective access into model/package | `module-info`/opens/provider |
| SOAP attachment fails | Activation/JAX-WS stack missing or generation mismatch | Activation + SOAP runtime |

This is a classification guide, not an exhaustive error-to-cause mapping. Read the full stack trace, dependency graph, and actual packaging before fixing.

## 27. Step-by-Step Error Diagnosis in Real Environments

### 27.1. Classify Errors by Phase

- **Compile:** compiler cannot find package or method.
- **Build code generation:** XJC, schemagen, plugin realm.
- **Application startup:** API/provider/classloader.
- **XML workflow execution:** JAXBContext, marshalling, validation, encoding.
- **Deployment:** WAR/JAR packaging, module path, server-owned providers.
- **Operational:** memory leaks, concurrency, performance, or native integration.

Changing a Maven dependency differs from fixing an old XJC plugin, and both differ from fixing XML namespace output.

### 27.2. Read the Full Exception Chain

Hypothetical example:

```text
javax.xml.bind.JAXBException:
  Implementation of JAXB-API has not been found
Caused by:
  java.lang.ClassNotFoundException: com.sun.xml.bind.v2.ContextFactory
```

Identify which JAXB API version is active, which provider ought to be present, and which classloader is searching for the provider. Do not blindly add random versions of `com.sun.xml.bind`.

### 27.3. Confirm the Actual Class Source

If multiple JARs contain `javax.xml.bind.JAXBContext` or implementation classes, class-loading logs on HotSpot can be used when needed:

```bash
java -Xlog:class+load=info -jar application.jar
```

On servers, logging depends on runtime and startup configuration. Logs can be very large; use only during controlled investigations.

### 27.4. Verify the API Package Inside the JAR

You can list entries:

```bash
jar tf path/to/jakarta.xml.bind-api-2.3.3.jar
```

For API 2.3, look for entries under `javax/xml/bind/`; for API 4.x, look for `jakarta/xml/bind/`. Never infer the package from the groupId.

## 28. CI Pipeline for JAXB Migration

A reference pipeline:

```text
Commit / PR
   |
   v
Dependency resolution + lock/BOM verification
   |
   v
Compile (JDK target/toolchain)
   |
   v
JAXB round-trip + schema/contract tests
   |
   v
Generated code/XJC reproducibility check
   |
   v
Package real JAR/WAR/distribution
   |
   v
Runtime smoke on minimum supported JDK
   |
   v
Security/XXE + XML encoding tests
   |
   v
Integration tests with external XML/SOAP contracts
   |
   v
Staging deployment + performance/soak
   |
   v
Release/canary with rollback readiness
```

### 28.1. Why Test on the Minimum JDK?

If an application targets Java 17 yet a provider/runtime artifact was compiled for Java 21, Maven might build cleanly on JDK 21 in some configurations while production Java 17 fails.

CI must verify:

- The application's class-file target.
- Bytecode level of runtime dependencies.
- Supported minimum JDK of the provider.
- The JDK executing tests.
- Whether the final artifact truly contains the provider.
- Whether XML/attachment features are actually exercised.

### 28.2. Do Not Run Tests Only Under the Latest JDK

A project claiming support for JDK 17 and 21 might use:

| Stage | JDK | Purpose |
|---|---|---|
| Compile | JDK matching toolchain/release target | Emit bytecode per policy |
| Unit/integration | 17 | Verify minimum supported runtime |
| Unit/integration | 21 | Verify target runtime |
| Packaging smoke | 17 and/or 21 per support | Run the actual JAR/WAR |
| XML contracts | Same supported runtimes | Compare XML/XSD/encoding |
| Production canary | JDK to be deployed | SLO, telemetry, rollback |

Not every project needs to test two JVMs if policy supports only one. However, when advertising multi-JDK support, testing the lowest supported runtime is critical.

## 29. Release and Rollback Strategy

### 29.1. When Only Adding External JAXB Dependencies Outside the JDK

If sources remain on `javax` and XML logic stays unchanged, the release has a smaller scope than a Jakarta migration, yet still modifies:

- The runtime dependency graph.
- Library code/provider versions.
- Memory/allocation/performance.
- XML serialization details.
- Packaging and image size.
- Security vulnerabilities/support lifecycle.

Compare XML outputs against contracts and run canary/staging on real payloads, rather than only compiling.

### 29.2. When Migrating to the Jakarta Namespace

The new version has different bytecode/APIs, potentially impacting:

- Public Java APIs of reusable modules.
- JAX-RS/SOAP/CDI integrations.
- Generated DTOs and annotation processors.
- Framework version compatibility.
- Application servers/providers.
- XML namespaces/outputs if bindings changed.
- Rollback capability for consuming libraries.

For multiple services/libraries, migration may require separate release tracks or adapters; do not assume Java modules using `javax` and `jakarta` are directly interchangeable.

### 29.3. Rollback Is Not Just Reverting to the Old JDK

If the new release already wrote XML into a database, message queue, or shared filesystem, ensure the old release can still read that data if rollback is required. If schemas/namespaces changed, a data compatibility or data rollback plan is needed.

Retain:

- Baseline artifact/checksum.
- Approved legacy runtime JDK/image.
- Dependency manifests and configuration.
- Migration changelog.
- XML contract fixtures.
- Operational metrics and rollback criteria.

Do not disable XML validation or certificate/security checks merely for a faster rollback; such decisions require dedicated risk review.

## 30. Extension Exercise 1 — XML Schemas and Generated DTOs

Suppose the project has `src/main/resources/xsd/customer.xsd`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           elementFormDefault="qualified">

    <xs:element name="customer">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="name" type="xs:string"/>
                <xs:element name="email" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

Exercise:

1. Use an **external-to-JDK** XJC tool/plugin matching JAXB 2.3 to generate `javax` classes.
2. Verify the generator no longer calls `$JAVA_HOME/bin/xjc`.
3. Record the generated output path and package.
4. Compile/run a JAXB round-trip from generated classes on JDK 17.
5. On another branch, switch to a Jakarta 4.x-compatible XJC and regenerate.
6. Compare generated annotations, `ObjectFactory`, `package-info`, and XML output.
7. Prove the XML contract has no unintended changes.

You do not need to hardcode a plugin version when comparing toolchains; select a version officially documented as compatible with your JDK, JAXB API generation, and current framework. Results must be verified with tests on actual generated code.

## 31. Extension Exercise 2 — Activation and XML Attachments

If the application uses `DataHandler` or MTOM attachments:

1. Check whether the current package is `javax.activation` or `jakarta.activation`.
2. Find where the API was previously supplied from the JDK/runtime.
3. Choose an Activation API and runtime generation compatible with JAXB/JAX-WS.
4. Inspect transitive dependencies and packaging.
5. Test binary payloads, MIME types, and large sizes.
6. Monitor memory usage when transferring large attachments.
7. Compare messages against baseline, including headers and content-type.

Do not assume marshalling a `Customer` with two text fields verifies attachment handling.

## 32. Extension Exercise 3 — Reusable Library Case

Suppose a library exposes a public method:

```java
public javax.xml.bind.JAXBElement<Customer> exportCustomer(Customer c);
```

When changing it to:

```java
public jakarta.xml.bind.JAXBElement<Customer> exportCustomer(Customer c);
```

you have altered the **public binary signature**. Consumer Java code may need recompilation/import updates, and framework libraries still tied to `javax` will not be automatically compatible.

Design options:

- Maintain separate legacy JAXB 2.x and Jakarta 4.x artifacts.
- Change the public API to use `String`, `byte[]`, or a JAXB-neutral domain DTO if the contract permits.
- Create an adapter at the boundary, converting data via XML/DTO rather than attempting to cast between two type systems.
- Publish a support matrix and migration guide for consumers.
- Test binary/source compatibility when releasing the library.

Do not simply change the dependency version inside the library and claim consumers are unaffected.

## 33. Extension Exercise 4 — A WAR on a Servlet Container

A WAR running on a servlet container with `javax.xml.bind` sources on JDK 17:

1. Confirm whether the container provides a JAXB API/provider.
2. If not, declare JAXB 2.3 API and runtime with the proper scope to be placed in `WEB-INF/lib`.
3. Verify the actual WAR includes the API/provider along with required supporting libraries.
4. Deploy to a matching container version.
5. Invoke an endpoint that marshals/unmarshals XML.
6. Verify classloading/provider resolution.
7. Compare output against the old JDK build and check memory/latency.
8. When transitioning to the Jakarta Servlet generation, create a dedicated migration plan for Servlet/JAXB namespaces rather than changing pieces without control.

With a full Jakarta EE server, the server may supply JAXB per profile; in that case, scope/ownership differs from a plain servlet container.

## 34. Misconceptions to Avoid

| Misconception | Reality |
|---|---|
| "JDK 17 still has JAXB because it has `javax.xml.parsers`" | Java SE XML parsers do not equal JAXB API/provider |
| "Adding `--add-modules java.xml.bind` on JDK 17 will make it run" | JDK 11+ removed the bundled module |
| "The JAXB API JAR alone is enough to marshal XML" | An implementation/provider is normally also required |
| "JAXB provider came in transitively so no need to check" | Transitive graph/packages can shift |
| "Every artifact named jakarta contains jakarta packages" | Jakarta XML Binding 2.3.x still contains `javax` |
| "Replacing API 2.3 with 4.x needs no source changes" | Package/binary names differ |
| "Having JAXB 4.x lets a javax framework use it" | Not automatically compatible |
| "Maven tests pass so the thin JAR runs standalone" | Packaging/launcher may lack runtime libs |
| "Every application server supplies JAXB" | Depends on server/profile and configuration |
| "A servlet container is full Jakarta EE" | Does not supply the entire platform by default |
| "Changing the JDK forces regenerating JAXB classes" | Keeping `javax` may avoid regeneration if dependencies align |
| "XJC will be available in JDK 21" | Bundled XJC/schemagen were removed starting in JDK 11 |
| "A UTF-8 XML declaration guarantees actual bytes are UTF-8" | Output Writer/stream encoding must also match |
| "`@XmlElement(required=true)` automatically validates all data" | Schema validation typically requires separate configuration |
| "Marshallers are always safe on untrusted XML" | Unmarshalling/parser security requires hardening |
| "Zero JAXB errors at startup means we are done" | The provider might only be invoked in rare workflows |
| "Adding multiple providers makes it safer" | Easily causes SPI/classloader conflicts |
| "Rolling back the JAR equals rolling back data" | Already-written XML data may be incompatible |
| "Compile target 17 makes all dependencies run on Java 17" | Third-party JARs keep their original bytecode |

## 35. Lab Handover Artifacts

Upon completion, the team should have:

1. **Baseline JDK:** version, vendor, checksum, and how legacy sources built/ran.
2. **Target JDK:** exact version, JVM flags, and runtime ownership.
3. **Namespace decision:** continue `javax` or migrate to `jakarta`, with rationale.
4. **Dependency inventory:** JAXB API, runtime, Activation, transitive versions, and scopes.
5. **Build artifacts:** POM/Gradle diffs, lockfiles/BOMs, generator/plugin versions.
6. **Generated code:** XJC inputs, plugin versions, imported namespaces, and source target.
7. **Packaging report:** thin/fat JAR, WAR/EAR, providers, and `META-INF/services`.
8. **Tests:** round-trip, XSD, Unicode, negative XML, attachments, and security.
9. **CI matrix:** compiler JDK, runtime JDK, minimum supported version.
10. **Compatibility report:** XML output and bidirectional data checks against baseline.
11. **Operational risks:** classloader conflicts, performance, XML parse limits, security.
12. **Release plan:** staging, canary, monitoring, and data/binary rollback.
13. **Ownership:** owner of generated bindings, dependency upgrades, and provider support.
14. **Known limitations:** XML patterns/workflows not yet tested.

### Practice Report Template

```yaml
lab:
  title: "Externalize JAXB from JDK"
  application: "jaxb-migration-lab"
  baseline:
    java_runtime: "JDK 8"
    JAXB_dependency_source: "Bundled JDK API/runtime"
  target:
    java_runtime: "JDK 17"
    namespace: "javax.xml.bind"
    api: "jakarta.xml.bind-api 2.3.3"
    runtime_provider: "jaxb-runtime 2.3.8"
  tests:
    compile: "PENDING"
    jaxb_context_creation: "PENDING"
    xml_round_trip: "PENDING"
    utf8_round_trip: "PENDING"
    schema_validation: "PENDING"
    packaged_launcher: "PENDING"
  migration_decision:
    path: "Keep javax for this phase"
    next_phase: "Evaluate jakarta 4.x with framework migration"
```

The `PENDING` statuses in the template must be replaced with the practitioner's actual execution results; do not treat this guide file as evidence that tests have run.

## 36. Completion Checklist

### Dependencies and Namespace

- [ ] Implicit `javax.xml.bind`/JAXB dependency from the legacy JDK identified.
- [ ] Confirmed JDK 11+ no longer bundles the JAXB module.
- [ ] Explicitly chose Branch A `javax` or Branch B `jakarta`.
- [ ] Selected JAXB API of the right package generation and a compatible provider.
- [ ] Avoided duplicate JAXB API JARs containing the same binary names.
- [ ] Checked Activation and supporting libraries where needed.
- [ ] Verified Maven/Gradle dependency graph with accurate scopes.

### Source, Code Generation, and Build

- [ ] `Customer.java`, `App.java`, and tests compile on the target JDK.
- [ ] Inspected JAXB annotations, `package-info`, and `ObjectFactory` if present.
- [ ] Generated sources match the namespace generation.
- [ ] XJC/schemagen no longer depend on tools bundled in JDK 8.
- [ ] Build plugins and compiler/toolchain versions pinned per support matrix.
- [ ] Tested the packaged application, not just source-set tests.

### XML Contract and Security

- [ ] Marshal/unmarshal tests produce the expected root, fields, namespaces, and values.
- [ ] Vietnamese Unicode regression test in place.
- [ ] Explicit encoding specified at file/network boundaries.
- [ ] XML/XSD validated when required by business contract.
- [ ] Parser settings verified against external entities/DTDs per provider.
- [ ] Malformed/empty/missing-field/large XML tested where necessary.
- [ ] Attachments/MIME tested if the application uses JAX-WS/Activation.
- [ ] Backward/forward XML compatibility tested where rolling/rollback requires it.

### Runtime and Operations

- [ ] Runtime includes the JAXB provider and transitive libraries.
- [ ] `--add-modules java.xml.bind` is not used on JDKs that removed that module.
- [ ] Checked JPMS/classloaders and packaging per the true runtime owner.
- [ ] Verified minimum JDK of all dependency JARs.
- [ ] Tested the real deployment artifact on the target JDK.
- [ ] Cross-checked TLS/I/O/encoding and resource behavior where relevant.
- [ ] Recorded checksums, dependency manifests, and release notes.
- [ ] Risk-appropriate staging/canary/rollback plan in place.
- [ ] Marked PASS only for verifications actually executed.

**Conclusion:** When leaving JDK 8, a project using JAXB must shift from thinking "the JDK includes JAXB" to **managing JAXB as an explicit dependency with its own API, implementation/provider, version, and scope**. If the goal is solely upgrading the JDK, keeping `javax.xml.bind` with a suitable JAXB 2.3 can be a lower-risk path; if simultaneously upgrading the framework to Jakarta, annotations, generated code, API, and runtime must all move to `jakarta.xml.bind`. A migration is proven successful not by adding a couple of dependencies to the POM, but by **being able to compile and run the packaged artifact on the target JDK, preserving accurate XML round-trips/contracts, reproducing codegen cleanly, securing parsers, and maintaining rollback feasibility**.
