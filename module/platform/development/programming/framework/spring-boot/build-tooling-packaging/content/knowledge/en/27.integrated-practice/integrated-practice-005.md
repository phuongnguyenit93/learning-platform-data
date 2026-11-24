# Creating a Standalone Executable WAR and Deploying Spring Boot to a Servlet Container

## 1. Goal: One WAR, Two Ways to Run

Spring Boot can package an application into an **executable WAR**. This artifact can be run in two ways:

1. Standalone via the **java -jar** command, using the embedded servlet container packaged inside the WAR.
2. Deployed into an external servlet container such as Apache Tomcat; the external container manages the process, HTTP connector, and application lifecycle.

This is useful when an organization runs a shared Tomcat platform while still wanting the ability to test-run the artifact directly in developer or CI environments.

~~~text
Source code + Maven dependencies
              |
              v
       mvn clean verify
              |
              v
    release-demo-0.1.0.war
       /                \
      /                  \
     v                    v
java -jar app.war    External Tomcat
     |                    |
Embedded Tomcat       Servlet container
     |                    |
     +--------+-----------+
              |
              v
       Spring Boot app
       /ready, /version
~~~

**An executable WAR is still a standard WAR file for deployment to a servlet container.** The Spring Boot Maven Plugin adds the launcher and places embedded container dependencies into **WEB-INF/lib-provided**. When run with **java -jar**, the launcher uses those dependencies; when deployed to external Tomcat, the container provides its own servlet engine.

Versions used throughout this article:
- Java 17.
- Spring Boot 3.5.0.
- Maven 3.9.x.
- Packaging war.
- Apache Tomcat 10.1 for external deployment.

Versions are pinned so the example stays consistent. For real projects, verify Spring Boot system requirements and the compatibility matrix of the servlet container your organization operates.

## 2. Checking Servlet Container Compatibility Before Building

Spring Boot 3.x uses Jakarta EE APIs. Servlet packages moved from the **javax.servlet.*** namespace to **jakarta.servlet.***.

Therefore, choose a servlet container compatible with the Jakarta Servlet specification supported by Spring Boot 3.5. Tomcat 10.1 is a suitable choice for this example; use JDK 17 when running the application.

| Component | Used in example | Notes |
| --- | --- | --- |
| Java | JDK 17 | Same major version at build and runtime to avoid unexpected differences |
| Spring Boot | 3.5.0 | Uses Jakarta namespace |
| Maven | 3.9.x | Manages dependencies and WAR packaging |
| External container | Tomcat 10.1 | Jakarta Servlet 6.0 |
| Artifact | release-demo-0.1.0.war | Standalone runnable or external deployment |

Do not deploy a Spring Boot 3.x application to Tomcat 9 or a container supporting only javax.servlet. Errors commonly appear as ClassNotFoundException, NoClassDefFoundError, or Servlet initialization failures due to incompatible API namespaces.

If maintaining a legacy Spring Boot 2.x application using javax.*, handle that migration separately. Do not mix javax.servlet and jakarta.servlet libraries in the same deployment expecting the container to convert them automatically.

Before choosing a container, verify:
- The container version falls within Spring Boot's supported range.
- The JDK runtime meets the requirements of both Spring Boot and the container.
- The container has no old Spring/Jakarta libraries manually copied into shared lib directories.
- Third-party libraries in the application have Jakarta-compatible versions.

## 3. Maven Project Structure

The example uses a small project with two endpoints to verify both executable WAR execution and external deployment:

~~~text
release-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/release/
                └── ReleaseDemoApplication.java
~~~

A WAR does not strictly require web.xml if the application uses Servlet 3.0+ programmatic initialization. Spring Boot uses SpringBootServletInitializer to register the application with the servlet container.

## 4. Configuring pom.xml to Build an Executable WAR

Here is the complete pom.xml file for the example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>release-demo</artifactId>
    <version>0.1.0</version>
    <name>release-demo</name>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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

### 4.1. Why change packaging to war?

The packaging war element instructs the Maven WAR lifecycle to create a web archive. The output artifact ends with .war and uses the WEB-INF/classes and WEB-INF/lib structure expected by servlet containers.

If left as jar, Maven builds a standard JAR. A Spring Boot JAR can run standalone, but it is not a WAR for deploying into Tomcat this way.

### 4.2. Why use provided scope for starter Tomcat?

spring-boot-starter-web pulls in embedded Tomcat by default. When deploying to external Tomcat, the servlet engine is already provided by the container.

Placing spring-boot-starter-tomcat in provided scope signals to the deployment model that this dependency is provided by the servlet container. The Spring Boot Maven Plugin still retains provided dependencies needed for executable WAR mode in WEB-INF/lib-provided.

Result:
- WEB-INF/lib: application libraries and standard runtime dependencies.
- WEB-INF/lib-provided: embedded container libraries used when running the executable WAR.
- External Tomcat uses its own servlet engine when deploying the WAR.

Do not add another Tomcat version into WEB-INF/lib or the server's shared lib folder to patch classpath issues. Inspect scopes and the dependency tree first.

### 4.3. What role does the Spring Boot Maven Plugin play?

The Spring Boot Maven Plugin runs the repackage goal to turn the generated WAR into an executable WAR. When using spring-boot-starter-parent, the default plugin execution configuration is managed by the parent.

Declare the plugin in build/plugins as shown to enable Spring Boot packaging. If the project does not inherit from spring-boot-starter-parent, configure a compatible plugin version and explicitly declare the repackage goal execution:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Do not add an arbitrary plugin version that differs from Spring Boot dependency management. Keep the plugin aligned with the Spring Boot release line to avoid mismatches during repackaging.

## 5. Writing an Application Class Supporting Both Modes

Create **src/main/java/com/example/release/ReleaseDemoApplication.java**:

~~~java
package com.example.release;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReleaseDemoApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseDemoApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(ReleaseDemoApplication.class);
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @GetMapping("/version")
    public String version() {
        return "release-demo:0.1.0";
    }
}
~~~

### 5.1. Role of main()

main() starts Spring Boot in the usual standalone way. When running:

~~~bash
java -jar target/release-demo-0.1.0.war
~~~

Spring Boot uses the embedded Tomcat packaged inside the executable WAR and starts the web server as a standalone application.

### 5.2. Role of SpringBootServletInitializer

An external servlet container does not boot the application by calling main() like a standard Spring Boot process. Instead, the container initializes the web application via the Servlet API.

SpringBootServletInitializer connects that initialization process to the Spring ApplicationContext. The configure() method returns the application's primary configuration source:

~~~java
@Override
protected SpringApplicationBuilder configure(
        SpringApplicationBuilder application) {
    return application.sources(ReleaseDemoApplication.class);
}
~~~

Because the main class both defines main() and extends SpringBootServletInitializer, the exact same artifact supports both execution modes.

If the initializer is missing or configure() is misconfigured, the executable WAR may run fine with java -jar while failing to deploy into external Tomcat. This is one of the most important differences to test for dual-mode WARs.

### 5.3. Why is web.xml unnecessary?

With servlet containers supporting Servlet 3.0 or later, applications can be initialized programmatically. Spring Boot uses its initializer and Servlet APIs to register the application.

Only create WEB-INF/web.xml when the application has specific legacy configuration requirements. Do not create an empty file just to make a WAR recognizable.

## 6. Building the WAR and Inspecting the Artifact

From the release-demo root directory, run:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify
~~~

verify runs preceding Maven lifecycle phases, including compile, test, package, and any verification steps configured in the project. The Spring Boot Maven Plugin repackages the WAR according to the parent/plugin setup.

Main artifact:

~~~text
target/release-demo-0.1.0.war
~~~

If the build fails, inspect the root exception and the failing Maven phase. Do not treat a stale WAR from a previous build as proof that the current build succeeded.

### 6.1. Inspecting the WAR structure

Use the JDK jar tool:

~~~bash
jar tf target/release-demo-0.1.0.war
~~~

On Linux/macOS, filter for key components:

~~~bash
jar tf target/release-demo-0.1.0.war \
  | grep -E 'WEB-INF/(classes|lib|lib-provided)/|spring-boot'
~~~

On Windows Command Prompt:

~~~cmd
jar tf target\release-demo-0.1.0.war | findstr /I "WEB-INF spring-boot"
~~~

Verify these components exist:
- WEB-INF/classes/com/example/release/ReleaseDemoApplication.class
- WEB-INF/lib/ containing Spring Boot application dependencies.
- WEB-INF/lib-provided/ containing embedded Tomcat libraries for the executable WAR.
- Spring Boot loader entries added by the plugin.

Actual library names/versions depend on dependency management. Do not hardcode an assumed list of JARs; read the output from the built artifact.

### 6.2. Inspecting the Maven dependency tree

Inspect dependencies related to the servlet container:

~~~bash
mvn -B -ntp dependency:tree \
  -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
~~~

Inspect the effective POM if packaging or plugin execution differs from expectations:

~~~bash
mvn -B -ntp help:effective-pom
~~~

Read the output alongside scope configuration and WAR contents. The dependency tree explains Maven resolution; jar tf confirms actual archive contents.

## 7. Running the Executable WAR Standalone

After a successful build:

~~~bash
java -jar target/release-demo-0.1.0.war
~~~

Spring Boot starts embedded Tomcat. By default, the example uses HTTP port 8080.

Open another terminal and test:

~~~bash
curl -i http://localhost:8080/ready
curl -i http://localhost:8080/version
~~~

Response bodies respectively:

~~~text
ready
release-demo:0.1.0
~~~

You can change the port for a standalone run:

~~~bash
java -jar target/release-demo-0.1.0.war --server.port=9090
~~~

Then call http://localhost:9090/ready and http://localhost:9090/version.

server.port is used by the embedded server in this mode. When deployed to external Tomcat, the HTTP port is managed by Tomcat's connector in conf/server.xml.

## 8. Preparing External Tomcat

### 8.1. Choosing the right Tomcat

With Spring Boot 3.5 and Jakarta Servlet, use a compatible external container, such as Tomcat 10.1. Download the distribution from the official Apache Tomcat website, verify checksums/signatures per your organization's process, and select an operations-supported patch release.

Do not just look at the product name Tomcat and ignore the major version. Tomcat 9 uses javax.servlet; Tomcat 10.1 uses jakarta.servlet.

### 8.2. Checking the JDK used by Tomcat

External Tomcat runs on its process/container JVM. Point JAVA_HOME to JDK 17 or a JDK supported by your application's Spring Boot version.

On Linux/macOS:

~~~bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"

"$CATALINA_HOME/bin/catalina.sh" version
~~~

On Windows Command Prompt:

~~~cmd
set JAVA_HOME=C:\Java\jdk-17
set PATH=%JAVA_HOME%\bin;%PATH%

%CATALINA_HOME%\bin\catalina.bat version
~~~

Confirm the Tomcat output shows the expected Java version and Java home. A Tomcat instance installed as a Windows Service or systemd service may use a different environment from your terminal; check the actual service configuration.

### 8.3. Distinguishing CATALINA_HOME and CATALINA_BASE

- CATALINA_HOME: installation directory of the Tomcat binaries.
- CATALINA_BASE: instance directory containing configuration, logs, deployed applications, and runtime data.

For a simple installation, both directories may be the same. In production, a single Tomcat binary installation can serve multiple instances with separate CATALINA_BASE directories.

The WAR must be placed in the webapps directory of the running instance, usually:

~~~text
$CATALINA_BASE/webapps/
~~~

If CATALINA_BASE is not configured, Tomcat typically defaults to using CATALINA_HOME as the base.

## 9. Deploying the WAR to Tomcat 10.1

### 9.1. Naming the WAR to define the context path

Tomcat typically derives the context path from the WAR filename:
- release-demo.war → /release-demo
- ROOT.war → /
- inventory.war → /inventory

For cleaner URLs, copy the versioned artifact to a stable deployment name release-demo.war. Keep the versioned source file in target so release records identify it accurately.

### 9.2. Deploying on Linux/macOS

If the Tomcat instance uses CATALINA_BASE:

~~~bash
cp target/release-demo-0.1.0.war \
  "$CATALINA_BASE/webapps/release-demo.war"
~~~

If using a simple single-directory install without a separate base:

~~~bash
cp target/release-demo-0.1.0.war \
  "$CATALINA_HOME/webapps/release-demo.war"
~~~

Start Tomcat in the foreground to watch logs:

~~~bash
"$CATALINA_HOME/bin/catalina.sh" run
~~~

If Tomcat is managed by systemd or a service manager, use that environment's deploy/restart workflow. Avoid starting a second Tomcat process on the same port.

### 9.3. Deploying on Windows

In Command Prompt, when CATALINA_BASE is configured:

~~~cmd
copy target\release-demo-0.1.0.war "%CATALINA_BASE%\webapps\release-demo.war"
%CATALINA_HOME%\bin\catalina.bat run
~~~

If not separating CATALINA_BASE, use %CATALINA_HOME%\webapps.

If Tomcat runs as a Windows Service, use the service manager and the instance directory actually used by that service. Your current terminal does not necessarily reflect the Windows Service configuration.

### 9.4. Verifying context path and endpoints

With deployment file release-demo.war, call:

~~~bash
curl -i http://localhost:8080/release-demo/ready
curl -i http://localhost:8080/release-demo/version
~~~

Response bodies respectively:

~~~text
ready
release-demo:0.1.0
~~~

URL differences to remember:

| Mode | URL |
| --- | --- |
| Executable WAR, embedded Tomcat | http://localhost:8080/ready |
| External Tomcat, WAR named release-demo.war | http://localhost:8080/release-demo/ready |
| External Tomcat, WAR named ROOT.war | http://localhost:8080/ready |

If a URL returns 404, verify the context path corresponding to the WAR filename before editing controller mappings.

## 10. Who Manages the Port and Context Path?

The two execution modes have different owners for configuration:

| Configuration | Executable WAR | External Tomcat |
| --- | --- | --- |
| HTTP port | Embedded Tomcat, typically via server.port | External Tomcat connector in conf/server.xml |
| Context path | Usually / unless configured otherwise | Container deployment name/context descriptor |
| JVM process | java -jar ...war | Tomcat service/process |
| Server lifecycle | Spring Boot launcher | External container |
| Servlet engine | Embedded Tomcat inside the WAR | Externally installed Tomcat |
| Startup logs | Application console/logging | Tomcat logs and application logs |

Do not use server.port to change the listener port of external Tomcat. Update the connector in server.xml according to container operations procedures, then restart/reload the service as managed by the organization.

With external deployment, the context path is usually determined by the WAR name or context descriptor. Renaming the deployed artifact can change the URL even when source code and controller mappings are unchanged.

## 11. Verifying Real Deployment

A successful Maven build only proves the artifact was created. You must test the WAR inside the target servlet container itself.

### 11.1. Inspecting startup logs

When deploying, inspect Tomcat logs:
- logs/catalina.*.log
- logs/localhost.*.log
- Console output when running catalina.sh run or catalina.bat run.
- Application logs according to the project's logging configuration.

Look for messages confirming Tomcat deployed the context, Spring ApplicationContext startup, and any bean initialization errors. Do not merely check whether the WAR file appears in webapps; the container may create an expanded directory while the application still fails to start.

### 11.2. HTTP smoke test

Check status codes and response bodies:

~~~bash
curl -fsS http://localhost:8080/release-demo/ready
curl -fsS http://localhost:8080/release-demo/version
~~~

-f makes curl return a non-zero exit code on HTTP error responses; -sS keeps output concise while still displaying errors. For applications deployed at context root, omit /release-demo from the URL.

You can inspect status/headers with:

~~~bash
curl -i http://localhost:8080/release-demo/ready
~~~

### 11.3. Distinguishing startup failures from request errors

- **Startup failure:** Tomcat failed to deploy the context or the Spring context failed to initialize. Inspect logs before calling endpoints.
- **404:** the request reached the server, but the context path or route is wrong, or the application has not deployed successfully.
- **500:** the route may have been matched, but request handling threw an error; inspect the application stack trace.
- **Connection refused:** no process is listening on that port, Tomcat is not running, or the connector uses a different port.
- **503:** a proxy/load balancer or container may mark the instance as unavailable; check health routing and startup state.

Do not modify controller code when the root cause is that Tomcat has not started or the URL context path is wrong.

## 12. Avoiding Duplicate Server Libraries

A WAR normally contains Spring libraries in WEB-INF/lib. External Tomcat provides the Servlet API and server implementation.

Common classloading errors:
- ClassCastException even with identical class names: the class may have been loaded from different classloaders.
- NoSuchMethodError: dependency version conflict between the WAR and shared libraries.
- NoClassDefFoundError for javax.servlet.*: an old library has not been migrated to Jakarta.
- NoClassDefFoundError for jakarta.servlet.*: incompatible container/API or wrong dependency scope.
- Bean/Servlet initialization failure: misconfigured initializer, listener, or deployment configuration.

How to investigate:
1. Inspect WEB-INF/lib and WEB-INF/lib-provided.
2. Run mvn dependency:tree to find version conflicts.
3. Check CATALINA_HOME/lib and CATALINA_BASE/lib for manually added Spring/Jakarta libraries.
4. Ensure the Tomcat version supports the application's Servlet namespace.
5. Use a consistent dependency management source for Spring Boot modules.

Do not copy Spring Boot JARs into Tomcat's shared lib to fix missing class errors. Doing so forces multiple applications to share one library version and causes classloader conflicts.

## 13. Application Configuration Across Two Environments

Shared application configuration can be placed in src/main/resources/application.properties or in environment-specific external configurations.

Example:

~~~properties
spring.application.name=release-demo
logging.level.root=INFO
~~~

For an executable WAR:
- server.port can adjust embedded Tomcat.
- JVM options and environment variables of the java -jar process determine runtime behavior.

For external Tomcat:
- Port/listener and TLS connector belong to Tomcat configuration.
- JVM options belong to the service/container process.
- Context path belongs to the deployment name or context descriptor.
- Application properties can still be supplied via external configuration, but confirm the exact mechanism and locations that Spring Boot reads.

Do not put production secrets inside the WAR or committed application.properties. Use the deployment platform's secret store/environment configuration.

If the same WAR must run across multiple environments, keep the artifact immutable and supply configuration externally. Record config version/secret references with the release so deployments are reproducible.

## 14. Testing and CI for Executable WARs

### 14.1. Building a single artifact

Basic pipeline:

~~~bash
mvn -B -ntp clean verify
jar tf target/release-demo-0.1.0.war
~~~

After the build:
1. Store the WAR as a CI artifact.
2. Compute the SHA-256 of the WAR file.
3. Test-run it with java -jar.
4. Deploy that exact WAR file to a compatible servlet container.
5. Run smoke tests against the real context path.
6. Link test results to the same checksum and build ID.

Compute checksum:

~~~bash
sha256sum target/release-demo-0.1.0.war
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash target/release-demo-0.1.0.war -Algorithm SHA256
~~~

The checksum identifies the exact bytes of the artifact. Do not rely on a version string alone to prove that the WAR in CI and the deployed WAR are the same file.

### 14.2. Testing both modes

| Test | Purpose |
| --- | --- |
| mvn clean verify | Compile, unit tests, and Maven lifecycle |
| jar tf ...war | Confirm the archive has WAR structure and loader |
| java -jar ...war | Test executable mode with embedded Tomcat |
| Deploy to Tomcat 10.1 | Test external servlet initialization |
| GET /ready | Verify the application is ready to accept requests |
| GET /version | Confirm the right artifact/version is running |
| Startup log review | Catch bean, classloader, and Servlet errors |

Do not treat testing java -jar as a substitute for external deployment testing. The two modes take two different server initialization paths.

### 14.3. Testing in CI without maintaining a production Tomcat

You can use a version-pinned Tomcat test instance/container during an integration test job:
- Start a Jakarta Servlet-compatible container.
- Copy/deploy the built WAR.
- Wait for the health endpoint with a bounded timeout.
- Run smoke tests.
- Collect logs if deployment fails.
- Stop and discard the test instance after the job.

Pin the Tomcat image/version in CI and production under the same compatibility policy. If production uses custom configurations/context descriptors, add deployment tests representative of those configurations.

## 15. Common Pitfalls When Creating and Deploying WARs

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Maven creates a JAR instead of a WAR | packaging is still jar | Set packaging war and run a clean build |
| WAR does not run with java -jar | Spring Boot repackage did not run or main class missing | Check plugin execution and manifest |
| WAR runs standalone but fails to deploy to external Tomcat | Missing SpringBootServletInitializer or wrong configure() | Extend initializer and return application source |
| Tomcat reports missing javax.servlet | App/dependency uses legacy namespace or wrong server version | Use Jakarta-compatible dependencies and Tomcat 10.1 |
| Tomcat reports missing jakarta.servlet | External container does not provide compatible Jakarta Servlet | Upgrade container to a compatible version |
| Embedded Tomcat conflict on deploy | Starter Tomcat not provided or duplicate libraries copied | Check scope, WEB-INF/lib-provided, and shared lib |
| URL returns 404 after deploy | Context path derived from WAR filename | Call /release-demo or deploy as ROOT.war |
| Port 8080 already in use | Another process/server is listening | Check processes/connectors; adjust port per environment |
| Connection refused | Tomcat not running or connector port differs | Check process and server.xml |
| HTTP 500 | Error in application code/beans/config | Read application stack trace |
| WAR present in webapps but not working | Deployment/startup failed after container picked up file | Check catalina/localhost logs |
| NoSuchMethodError | Spring/library version conflict or old shared library | Inspect dependency tree and Tomcat shared lib |
| ClassCastException when loading Servlet/filter | Classloader issue or duplicate API classes | Deduplicate Servlet API/server libraries |
| Java version mismatch | Tomcat service uses a different JDK than terminal | Check service environment and catalina version |
| Build passes but external deployment fails | Only executable mode was tested | Add integration test against the real servlet container |
| Renaming WAR changes URLs | Tomcat uses WAR name to generate context path | Standardize deployment filename or context descriptor |
| web.xml does not exist | Misconception that every WAR requires web.xml | Use Servlet 3+ initializer; add descriptor only when explicitly needed |

## 16. Updates, Rollbacks, and Artifact Management

A repeatable deployment process should:
1. Build the WAR from an approved commit.
2. Run mvn clean verify.
3. Record GAV/version, build ID, and SHA-256.
4. Verify executable mode.
5. Deploy the WAR to test Tomcat and run smoke tests.
6. Promote that exact artifact to the next environment.
7. Record Tomcat version, JDK version, context path, and config reference.
8. Retain previous WARs per retention policy for rollback.

When updating an application:
- Use the platform's deployment process to avoid copying a WAR while the container is reading/writing it.
- Ensure old instances drain traffic if behind a load balancer.
- Confirm application startup completes before receiving traffic.
- Keep logs of both deployment and startup.
- If rolling back, redeploy the previous artifact identified by checksum.

Do not rebuild from source on a production host to create a different WAR from the QA-tested artifact. A release should promote the exact same tested file.

## 17. Pre-Handoff WAR Checklist

### Build and structure

- [ ] Maven project sets packaging war.
- [ ] Java/Spring Boot/Maven versions are pinned.
- [ ] spring-boot-starter-tomcat uses scope provided.
- [ ] Spring Boot Maven Plugin executes repackage.
- [ ] Main class extends SpringBootServletInitializer.
- [ ] configure() returns the right application source.
- [ ] mvn clean verify succeeds.
- [ ] WAR contains WEB-INF/classes, WEB-INF/lib, and needed entries.
- [ ] Executable WAR has the loader and appropriate WEB-INF/lib-provided.

### External servlet container

- [ ] Container version supports the Jakarta Servlet version required by the app.
- [ ] Tomcat service's JDK meets application requirements.
- [ ] Context path determined from WAR name/descriptor.
- [ ] External container manages HTTP port and TLS connector.
- [ ] No conflicting Spring/Servlet libraries in shared lib.
- [ ] Startup logs contain no deployment errors.
- [ ] Smoke tests return expected responses.

### Release and operations

- [ ] Same WAR tested in both executable and external modes.
- [ ] SHA-256 stored alongside build ID/release.
- [ ] WAR and config managed separately.
- [ ] No secrets packaged inside the artifact.
- [ ] Logging, health checks, rollback artifact, and retention policy in place.
- [ ] Deployment follows environment workflow rather than untraceable manual file edits.

## 18. Official Documentation

- Spring Boot 3.5 – [Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html): deploying Spring Boot applications as WARs to servlet containers and SpringBootServletInitializer.
- Spring Boot 3.5 – [Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): repackage, executable archives, and WAR packaging.
- Spring Boot 3.5 – [System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java and servlet container compatibility.
- Spring Boot 3.5 – [Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): servlet application initialization and embedded containers.
- Apache Tomcat 10.1 – [Application Developer's Guide](https://tomcat.apache.org/tomcat-10.1-doc/appdev/): web application structure and deployment.
- Apache Tomcat 10.1 – [Manager App HOW-TO](https://tomcat.apache.org/tomcat-10.1-doc/manager-howto.html): deploying/undeploying via Manager when enabled and secured in the environment.
- Apache Tomcat 10.1 – [Migration Guide](https://tomcat.apache.org/migration-10.html): Jakarta namespace differences when migrating from Tomcat 9 to Tomcat 10.
- Apache Maven – [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): package, verify, and lifecycle phases.
- Apache Maven – [Maven WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/): configuring WAR packaging.

**Remember:** An executable Spring Boot WAR can both run via java -jar with embedded Tomcat and be deployed to an external servlet container. To support both, set packaging to war, move embedded Tomcat to scope provided, enable Spring Boot repackage, and have the main application extend SpringBootServletInitializer. After building, inspect the WAR structure, run it standalone, deploy it to a Jakarta-compatible Tomcat, and smoke-test the artifact's exact context path.