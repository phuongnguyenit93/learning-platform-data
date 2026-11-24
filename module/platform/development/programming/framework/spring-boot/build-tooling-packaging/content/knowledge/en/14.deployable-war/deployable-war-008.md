# Verifying Java, Servlet, Jakarta, and Target Server Compatibility for WAR Deployment

## 1. Why Can a Successfully Built WAR Still Fail to Deploy?

A Spring Boot application can run in the IDE, pass `mvn clean package`, and produce a `.war` file, yet fail when deployed onto Tomcat or the target servlet container. Common causes lie in the **Java runtime**, **Servlet API version**, **Java EE/Jakarta EE namespace**, **libraries inside the WAR**, or **how the server initializes the application**.

An important example: Spring Boot 3.x uses `jakarta.servlet.*` classes, whereas Tomcat 9 implements Servlet 4.0 with `javax.servlet.*`. Running Tomcat 9 on Java 17 or 21 still does not turn it into a Jakarta Servlet container. Upgrading the JDK does **not** change API class names at the bytecode level.

This article belongs to the **Deployable WAR** section under **Spring Boot Build Tooling Packaging**. After this lesson, you will be able to:

1. Build a compatibility matrix covering Java/JVM, Servlet specification, Jakarta namespace, and server version for a project.
2. Distinguish the JDK used to compile from the JVM **actually** running Tomcat.
3. Explain why `javax.servlet` and `jakarta.servlet` are not interchangeable.
4. Properly configure a WAR with Maven, `SpringBootServletInitializer`, and `provided` container dependency scope.
5. Inspect bytecode, manifest, `WEB-INF/lib`, and `WEB-INF/lib-provided` using JDK tools.
6. Deploy a WAR to external Tomcat and verify Java/Servlet/container versions at runtime.
7. Diagnose startup, classpath, namespace, context path, and Servlet API errors.

**Practice stack:** Java target `17`, Spring Boot `3.5.16`, Maven, external Tomcat `10.1.x` with Servlet `6.0`. Versions are pinned so examples can be checked against documentation, not because they are the latest or mandatory for every project. If using Spring Boot 4.x, do not apply the Boot 3.5 matrix verbatim.

## 2. Five Conditions That Must All Hold Simultaneously

| Check Axis | What Must Be Verified | What Happens If Wrong? |
| --- | --- | --- |
| Java build/bytecode | Compile JDK, release target, class major version | WAR contains classes newer than target Java |
| Server JVM | Java **actually used by the Tomcat service process** | `UnsupportedClassVersionError` right when loading classes |
| Servlet specification | Servlet 4.0/5.0/6.0/6.1, plus Pages/EL/WebSocket if used | Called class or method does not exist on the server |
| API namespace | `javax.servlet` vs. `jakarta.servlet` in app and dependencies | `ClassNotFoundException`, `NoClassDefFoundError`, type mismatch |
| Server product/patch/deploy | Tomcat, Jetty, WildFly, WebLogic... version, context, classloader | WAR fails to deploy or runs in an unexpected environment |

Beyond those five axes, also verify **dependency scopes**. A WAR might accidentally bundle embedded Tomcat into `WEB-INF/lib` and clash with external Tomcat; or run via `java -jar` using provided dependencies yet lack a proper Servlet initializer for an external container to load the app.

Thus the practical formula is:

~~~text
Deployable WAR
    = sufficiently new Java runtime
    + supported class-file target
    + matching Servlet API/version
    + matching Java EE/Jakarta EE namespace
    + compatible container version and configuration
    + proper dependencies/scopes
    + verified external deployment
~~~

Do not conflate these conditions. Tomcat 10.1 itself runs on Java 11+, yet a Spring Boot 3.5 application requires Java 17+, so Tomcat's JVM **must satisfy the higher requirement**.

## 3. Compatibility Matrix: Tomcat, Java, Servlet, and Spring Boot

### 3.1. Tomcat Lines

| Tomcat | Servlet Specification | Namespace | Minimum Java for Tomcat | Notes |
| --- | --- | --- | --- | --- |
| `9.0.x` | `4.0` | `javax.servlet.*` | `8+` | Java EE line; not an appropriate target for Spring Boot 3/Jakarta WARs |
| `10.0.x` | `5.0` | `jakarta.servlet.*` | `8+` | Jakarta transition line, end-of-life; avoid for new production |
| `10.1.x` | `6.0` | `jakarta.servlet.*` | `11+` | Suitable example for Boot 3.5; Boot app still requires Java 17+ |
| `11.0.x` | `6.1` | `jakarta.servlet.*` | `17+` | Servlet 6.1 line, suitable when evaluating a Boot 4.x stack |

These are **Tomcat product requirements** based on official Apache Tomcat documentation. Always pick a **supported patch**, not just a major/minor line. Other servers have their own matrices that cannot be deduced from product names or the word "Jakarta."

### 3.2. Common Spring Boot Generations

| Framework | Minimum Java | Core Servlet and Namespace | Guidance |
| --- | --- | --- | --- |
| Spring Boot `2.7.x` / Framework 5 | Java `8+` | Java EE Servlet, `javax.servlet.*` | Commonly paired with Tomcat 9; moving to Boot 3 requires migration |
| Spring Boot `3.5.x` / Framework 6.2 | Java `17+` | Jakarta Servlet; embedded Tomcat 10.1 / Servlet 6.0 | Docs support external Servlet 5.0+ containers; example picks Tomcat 10.1 |
| Spring Boot `4.1.x` / Framework 7 | Java `17+` | Servlet `6.1+` | Requires container supporting Servlet 6.1+, such as Tomcat 11 |

Sharing the Jakarta namespace does not make Servlet 5.0, 6.0, and 6.1 identical. If a framework or library calls a method introduced only in a newer spec, an older container can throw `NoSuchMethodError` even though the namespace is already `jakarta`.

Note that three numbers are **not synonymous**: `Tomcat 10.1` is a product version; `Jakarta EE 10` is a platform version covering many specs; `Jakarta Servlet 6.0` is one specification's version. A servlet container like Tomcat does **not** automatically provide all services of a full Jakarta EE application server.

## 4. Java: Checking the Exact Process Runtime and Class Bytecode

### 4.1. Do Not Look Only at `java -version` in Your Terminal

In the build environment:

~~~bash
java -version
javac -version
mvn -version
~~~

Those commands show which JDK the developer/build-agent terminal uses. Tomcat may run under a Windows Service, systemd, a container, or a separate user, picking its JVM from service configuration. What you must verify is the **JVM of the process actually deploying the WAR**, not just your shell's `JAVA_HOME`.

For a script-installed Tomcat, you can check version details with:

~~~bash
"$CATALINA_HOME/bin/version.sh"
~~~

On Windows use `version.bat` in `bin`. However, if Tomcat runs under a service manager, that script can reflect a **different Java environment** than the service JVM. Check service startup logs, process command line / JVM path, runtime image, and (when permitted) an endpoint reporting `Runtime.version().feature()` from inside the web app itself.

### 4.2. Class-File Major Versions

| Java Target | Major Version |
| --- | --- |
| Java `8` | `52` |
| Java `11` | `55` |
| Java `17` | `61` |
| Java `21` | `65` |
| Java `25` | `69` |

For example, bytecode `major=65` compiled for Java 21 cannot load on a Java 17 JVM. Tomcat 10.1 supporting Java 11+ does not solve class files that are too new or Spring Boot 3.5 requiring Java 17+.

After `mvn compile`, inspect a compiled class:

~~~bash
javap -verbose -classpath target/classes demo.WarApplication
~~~

With Java 17 configured, look for `major version: 61`. `WarInspect.java` in section 8 can check a class **inside the WAR**. Still, an app class with major 61 does not prove every dependency supports Java 17: a third-party JAR containing major-65 classes will still fail when the server loads it.

**Rule:** the minimum Java level of the entire stack is the highest level demanded by Spring Boot, the servlet container, your application, and its dependencies. When upgrading a server's JDK, verify that every actual service/container switched JVMs and re-test.

## 5. `javax.servlet` and `jakarta.servlet` Differ at the Bytecode Level

The following two imports are **not equivalent**:

~~~java
// Java EE / Tomcat 9
import javax.servlet.http.HttpServletRequest;
~~~

~~~java
// Jakarta EE / Spring Boot 3+
import jakarta.servlet.http.HttpServletRequest;
~~~

The JVM sees two completely different class names:

~~~text
javax/servlet/http/HttpServletRequest
jakarta/servlet/http/HttpServletRequest
~~~

If a third-party filter was compiled against `javax.servlet.Filter`, dropping it into a Jakarta environment cannot magically rewrite it to `jakarta.servlet.Filter`. Errors may surface only when external Tomcat initializes the webapp, even if your own code migrated and the Maven build is green.

Key API groups to check when upgrading from Java EE to Jakarta EE:

| Previous API | Corresponding Jakarta API |
| --- | --- |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.websocket.*` | `jakarta.websocket.*` |

**Do not search-and-replace every `javax.`**: many Java SE APIs still use the `javax` namespace, such as `javax.sql`, `javax.crypto`, `javax.net.ssl`, and `javax.naming`. Migrate only the relevant Java EE/Jakarta EE APIs while updating third-party libraries.

A similar failure occurs if you compile against Servlet 6.1 while the runtime container implements only Servlet 6.0. Both share the Jakarta namespace, yet the specification versions and method sets differ. The right fix is matching the API/framework version to the **actual server** or upgrading the server, rather than merely bundling a newer Servlet API JAR inside the WAR.

## 6. Maven WAR, `SpringBootServletInitializer`, and `provided` Scope

For a Spring Boot WAR deployed to an external servlet container, three components are needed:

1. Maven `<packaging>war</packaging>` to build a genuine WAR archive.
2. A `SpringBootServletInitializer` subclass configuring the Spring application for the external servlet container lifecycle.
3. The embedded servlet container dependency, e.g. `spring-boot-starter-tomcat`, marked `provided` instead of packaged as a regular runtime library.

In `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

`provided` does **not** hide the Servlet API from the compiler. It declares that the external runtime container supplies the implementation. In an executable WAR created by Spring Boot `repackage`, provided container libraries may still appear in `WEB-INF/lib-provided` so `java -jar` can launch the embedded server. External Tomcat does **not** treat `WEB-INF/lib-provided` as standard libraries in `WEB-INF/lib`.

Do not add `javax.servlet-api` to a Boot 3 WAR to "patch" Tomcat 9. Nor should you bundle a newer `jakarta.servlet-api` JAR hoping to upgrade the server's servlet engine. Verify Maven scopes and the Servlet implementation provided by the target server.

## 7. Complete WAR Example: Maven, Spring Boot 3.5, and Java 17

Directory structure:

~~~text
compat-war-demo/
  pom.xml
  WarInspect.java
  src/
    main/
      java/
        demo/
          WarApplication.java
          CompatibilityController.java
~~~

### 7.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>compat-war-demo</artifactId>
    <version>1.0.0</version>
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
                <configuration>
                    <mainClass>demo.WarApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explanation:

- `spring-boot-starter-parent` manages compatible versions and plugin settings; when `spring-boot-maven-plugin` is declared, the `repackage` goal is bound to the `package` lifecycle by the parent.
- `packaging=war` selects Maven WAR packaging.
- `java.version=17` sets the Java compile target via the parent; it does not prove what Java version the Tomcat service runs.
- `spring-boot-starter-web` provides the Spring MVC/web stack.
- Declaring `spring-boot-starter-tomcat` directly with `provided` scope lets the external host supply the container while executable WAR mode can still use `WEB-INF/lib-provided`.

If a project **does not use** Boot starter parent, it must manage dependency versions, Maven compiler, and bind `repackage` in the lifecycle explicitly; a plugin declaration without a matching execution is not enough.

### 7.2. `WarApplication.java`

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(WarApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarApplication.class);
    }
}
~~~

`main` runs when launching the executable WAR with `java -jar`. `SpringBootServletInitializer.configure` runs when **external Tomcat** loads the WAR through the Servlet lifecycle. These two startup paths are distinct: a WAR working well on the embedded server does **not** guarantee external deployment succeeds.

### 7.3. `CompatibilityController.java`

~~~java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CompatibilityController {

    @GetMapping(value = "/probe",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        return "war-ok";
    }

    @GetMapping(value = "/compat",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String compatibility(HttpServletRequest request) {
        var context = request.getServletContext();
        return "java.feature="
                + Runtime.version().feature() + "\n"
                + "servlet.version="
                + context.getMajorVersion() + "."
                + context.getMinorVersion() + "\n"
                + "server=" + context.getServerInfo() + "\n";
    }
}
~~~

This code imports `jakarta.servlet.http.HttpServletRequest`, matching the Spring Boot 3 API generation. `GET /probe` returns **exactly** `war-ok` with no method-added newline. `GET /compat` returns the Java feature version of the **JVM serving the request**, the Servlet version from `ServletContext`, and the server name/version from `getServerInfo()`.

`/compat` should only exist in test environments or be protected: exposing JDK/container versions on a public endpoint is unnecessary in production.

No `WEB-INF/web.xml` is needed for Spring Boot's initializer/annotation bootstrap in this example. If an application has a legacy `web.xml` descriptor, verify its namespace/schema and filter/listener declarations for Jakarta compatibility.

## 8. Build, Inspect, and Verify Class Files Inside the WAR

At the project root:

~~~bash
mvn clean package
jar tf target/compat-war-demo-1.0.0.war
~~~

If the project uses Maven Wrapper, run `./mvnw clean package` or `.\mvnw.cmd clean package` in Windows PowerShell. Expected **abbreviated** archive output is:

~~~text
META-INF/MANIFEST.MF
WEB-INF/classes/demo/WarApplication.class
WEB-INF/classes/demo/CompatibilityController.class
WEB-INF/lib/...
WEB-INF/lib-provided/...
org/springframework/boot/loader/...
~~~

The `...` entries denote an abbreviated listing, not literal stdout from `jar tf`. In an executable WAR, runtime libraries sit in `WEB-INF/lib`, while libraries such as provided Tomcat may sit under `WEB-INF/lib-provided`.

### 8.1. Java 17 Utility to Inspect the WAR Directly

Place `WarInspect.java` at root, **outside** `src/main/java`, so the utility is not packaged into the WAR:

~~~java
import java.io.DataInputStream;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class WarInspect {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java WarInspect.java <war-path>");
        }

        try (JarFile war = new JarFile(
                Path.of(args[0]).toFile())) {
            JarEntry entry = war.getJarEntry(
                    "WEB-INF/classes/demo/WarApplication.class");
            if (entry == null) {
                throw new IllegalStateException("Missing main class");
            }

            int major;
            try (InputStream raw = war.getInputStream(entry);
                 DataInputStream in = new DataInputStream(raw)) {
                if (in.readInt() != 0xCAFEBABE) {
                    throw new IllegalStateException("Invalid class");
                }
                in.readUnsignedShort(); // minor version
                major = in.readUnsignedShort();
            }

            Manifest manifest = war.getManifest();
            Attributes attrs = manifest == null
                    ? new Attributes()
                    : manifest.getMainAttributes();

            boolean hasLibraries = war.stream().anyMatch(
                    e -> e.getName().startsWith("WEB-INF/lib/")
                            && e.getName().endsWith(".jar"));
            boolean providedTomcat = war.stream().anyMatch(
                    e -> e.getName().startsWith(
                            "WEB-INF/lib-provided/tomcat-embed-core-"));

            System.out.println("class.major=" + major);
            System.out.println("class.java=" + (major - 44));
            System.out.println("manifest.main="
                    + attrs.getValue("Main-Class"));
            System.out.println("manifest.start="
                    + attrs.getValue("Start-Class"));
            System.out.println("war.libs=" + hasLibraries);
            System.out.println(
                    "war.provided.tomcat=" + providedTomcat);
        }
    }
}
~~~

Run with the Java 17 source-file launcher:

~~~bash
java WarInspect.java target/compat-war-demo-1.0.0.war
~~~

With the **exact example** compiled for Java 17 and repackaged successfully, the expected output is:

~~~text
class.major=61
class.java=17
manifest.main=org.springframework.boot.loader.launch.WarLauncher
manifest.start=demo.WarApplication
war.libs=true
war.provided.tomcat=true
~~~

This is the **expected result per the POM**, not measurements from your server. Exact Boot loader names depend on plugin version. The tool checks only the **main class and archive structure**; it does not check bytecode major versions of every class inside nested dependency JARs, nor does it prove filters/libs no longer reference `javax.servlet`.

If `unzip` is available, you can inspect the manifest separately:

~~~bash
unzip -p target/compat-war-demo-1.0.0.war META-INF/MANIFEST.MF
~~~

`Main-Class` and `Start-Class` in an executable WAR serve the Boot launcher. When external Tomcat deploys it, it uses the Servlet initializer rather than **`java -jar`** to start the WAR.

## 9. Smoke Testing Executable WAR vs. External Tomcat Differently

### 9.1. Check the `java -jar` Path First

In terminal 1:

~~~bash
java -jar target/compat-war-demo-1.0.0.war --server.address=127.0.0.1 --server.port=8087
~~~

In terminal 2, after startup:

~~~bash
curl -fsS http://127.0.0.1:8087/probe
curl -fsS http://127.0.0.1:8087/compat
~~~

Exact `/probe` body:

~~~text
war-ok
~~~

`/compat` returns runtime-dependent data. For example on Java 17 and Tomcat 10.1, the output **may look like**:

~~~text
java.feature=17
servlet.version=6.0
server=Apache Tomcat/10.1.x
~~~

`10.1.x` is an **illustrative version-line notation**, not literal text. The container prints its actual patch; if the JVM runs Java 21, `java.feature=21`. Once done, stop the process with `Ctrl+C`. In CI, use a runner with timeouts and cleanup.

Even when this test PASSES, it proves only the **executable WAR with embedded runtime**. External Tomcat has its **own** JVM, Servlet implementation, classloader, and context configuration, so you still need to test deploying there.

### 9.2. Test the Exact External Tomcat 10.1 in Staging

Before deploying, verify the server:

- Supported `10.1.x` Tomcat patch.
- **Service** JVM running Java 17+.
- Container implements Servlet 6.0 / Jakarta namespace.
- `CATALINA_BASE`, deploy mechanism, context path, connector port, and rollback plan are known.
- Authorized to deploy a test application without accidentally overwriting an active WAR.

On a staging Tomcat **permitted to use `autoDeploy`**, with `CATALINA_BASE` set:

Linux/macOS:

~~~bash
cp target/compat-war-demo-1.0.0.war "$CATALINA_BASE/webapps/compat.war"
~~~

Windows PowerShell:

~~~powershell
Copy-Item .\target\compat-war-demo-1.0.0.war "$env:CATALINA_BASE\webapps\compat.war"
~~~

If Tomcat disables `autoDeploy` or uses Tomcat Manager or platform CI/CD, use that mechanism; copying a file does not guarantee deployment. Filename `compat.war` normally creates context `/compat` when the server does not override context mappings.

After checking server deploy logs and confirming the context is active, call the sample URLs:

~~~bash
curl -fsS http://127.0.0.1:8080/compat/probe
curl -fsS http://127.0.0.1:8080/compat/compat
~~~

Adjust host/port/context for your **actual server**. `/compat` reads the **external** server's JVM/`ServletContext`, unlike the executable WAR endpoint in section 9.1. Expect Java feature at least 17, Servlet 6.0, and server info matching Tomcat 10.1.

If you get 404, do not immediately blame Java/Jakarta: it could be the wrong context path, an undeployed WAR, an unmapped route, a proxy/vhost mismatch, or a failed context startup. Check deployment logs first.

## 10. Inspecting the Dependency Graph and Legacy `javax` Libraries

On a real POM, run:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api
mvn dependency:tree -Dincludes=jakarta.servlet:jakarta.servlet-api
mvn help:effective-pom
~~~

The dependency tree shows resolved versions and scopes, while effective POM shows inherited configuration. Still, a library can embed Servlet API classes **inside another artifact** or reference `javax.servlet` via reflection, `META-INF/services`, or configuration. Having no `javax.servlet-api` node in the tree does **not** guarantee zero static or dynamic references remain.

Proper workflow:

1. Search for `javax.servlet` imports in application code, filters, and listeners; leave Java SE `javax.*` untouched.
2. Check whether third-party JARs offer Jakarta-compatible versions, especially security integrations, JSP taglibs, and Servlet filters.
3. Inspect `WEB-INF/lib` for any embedded Tomcat or Servlet API that should not be bundled.
4. Check the compile target of dependencies, not just application classes.
5. Deploy the WAR onto the exact external server and read the stack trace if startup fails.

`jdeps` can help analyze dependencies at the class level, though an executable WAR holds nested JARs; deep analysis requires extracting classes/libraries into an inspection directory and setting up the classpath. Static analysis misses reflection and dynamic loading, so it **cannot replace** a smoke test on the real server.

## 11. Servers Beyond Tomcat and Other Jakarta EE Components

Do not assume a server is compatible simply because its product name contains the word Jakarta. With WebLogic, WildFly, Jetty, Payara, or vendor-managed environments, read the **compatibility matrix for the exact product release and patch**:

- Servlet/Jakarta specifications actually implemented by the server.
- Supported JVM versions and the Java version running on the service.
- Container classloader rules, server-provided libraries, and deployment descriptors.
- Context path, servlet mappings, reverse proxy, and security.
- JSP/Pages, EL, WebSocket, Persistence, CDI/transactions, or other Jakarta APIs used by the project.
- Specific requirements for servlet initializers, WAR deployment, and provided libraries.

Tomcat focuses on the servlet/web stack and is not a full Jakarta EE implementation. A full application server supplies more APIs; if a WAR bundles conflicting library versions, classloading conflicts can differ from Tomcat.

**Do not assume "both are Servlet 6.0" means everything behaves identically.** Patch versions, classloader policies, vendor support, annotations/JSP behavior, and environment integrations still matter. The final proof must be **the real WAR working as required in the target environment**.

## 12. Common Deployment Errors

| Symptom | Cause to Investigate | Evidence |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Server JVM is older than app/library bytecode | Server JVM, class major version, dependency JAR versions |
| `NoClassDefFoundError: jakarta/servlet/...` | Server still uses `javax.servlet` or lacks Jakarta API | Tomcat version and Servlet spec |
| `NoClassDefFoundError: javax/servlet/...` | Legacy filter/library not migrated to Jakarta | Dependency graph and class references |
| `NoSuchMethodError` on Servlet API | Compiled against newer spec/method than runtime | Servlet API version / method owner |
| `ClassCastException` on Servlet/Filter | Mixed namespaces or classloaders | `WEB-INF/lib` vs. server-wide libraries |
| `SpringBootServletInitializer` not invoked | Missing initializer, wrong startup/deploy config | App sources and Tomcat logs |
| `java -jar` PASSES yet external deploy FAILS | Bootstrap path, scopes, and classloader differ | WAR / servlet container logs |
| HTTP 404 after deploy | Wrong context path, route, `autoDeploy`, or startup failure | Context mapping and logs |
| HTTP 401/403 | Security/filter/proxy configuration | Auth, security policy, and request headers |
| JSP errors even when controllers work | Incompatible JSP/EL/JSTL version | Jakarta Pages/EL spec and library versions |
| Tomcat 10.1 runs Java 11 yet Boot 3.5 FAILS | Boot requires Java 17+ | Service JVM/version and logs |
| Boot 4.1 on Tomcat 10.1 FAILS | Boot 4.1 needs Servlet 6.1+, Tomcat 10.1 is Servlet 6.0 | Boot requirements and Tomcat spec |
| Local PASSES, production FAILS | Different Java, container patch, classloader/env | Compare compatibility records and logs |
| Build PASSES yet old WAR is deployed | Script selected wrong file/version | Artifact path, checksum, deploy logs |

An exception name is a **clue**, not a full conclusion. Inspect the full stack trace and find the actually missing **class/method owner**. Avoid "fixing" issues by blindly bumping the JDK or dropping in an arbitrary API JAR.

## 13. Pre-Release Acceptance Checklist

- [ ] Identified Spring Boot/Framework versions and target Servlet/Jakarta version.
- [ ] Identified **service** JDK runtime, Java bytecode target, and dependency Java requirements.
- [ ] Server is supported and Servlet spec matches; did not confuse Tomcat 9 `javax` with Tomcat 10/11 `jakarta`.
- [ ] `packaging=war`, `SpringBootServletInitializer`, and `provided` container scope are configured.
- [ ] WAR artifact contains `WEB-INF/classes`, properly scoped libraries, and a clear deployment path.
- [ ] Audited dependency graph, legacy `javax.servlet` libraries, and required Jakarta APIs.
- [ ] Clean build completed; verified exact WAR file rather than matching by wildcard.
- [ ] Deployed WAR to an **external** staging server matching the target stack.
- [ ] Checked startup logs; called `/probe`/`/compat`, verifying HTTP status, body, and real server JVM/`ServletContext`.
- [ ] Ran additional smoke/integration tests for JSP, WebSocket, security, sessions, and databases if used by the app.
- [ ] Recorded checksum of the tested WAR and deployed **that exact file**; rollback plan in place.

### Self-Check Questions

**A. Tomcat 9 runs Java 21, and a Spring Boot 3.5 app is compiled for Java 17. Will it deploy cleanly?**

No. A newer JVM reads older bytecode, yet Tomcat 9 is still Servlet 4.0 `javax.servlet`, incompatible with Boot 3's `jakarta.servlet` namespace.

**B. Tomcat 10.1 itself supports Java 11, so can Boot 3.5 run on JVM 11?**

No. Spring Boot 3.5 requires Java 17+; the minimum for the entire stack is the highest requirement among all layers.

**C. Is running a WAR via `java -jar` sufficient proof that external Tomcat deployment works?**

Not yet. `java -jar` uses the Boot launcher and embedded libraries; external deployment uses the Servlet initializer and the container's actual APIs and classloader.

**D. Should you add a newer `jakarta.servlet-api` JAR into `WEB-INF/lib` to upgrade an old Tomcat?**

No. An API JAR does not replace the server's servlet implementation and can cause conflicts. Choose a container supporting the required specification.

**E. Both Boot 4.1 and Tomcat 10.1 support Java 17. Are they compatible?**

Not yet: Boot 4.1 requires Servlet 6.1+, whereas Tomcat 10.1 provides Servlet 6.0. You must verify the Servlet spec as well.

## 14. Official Documentation

- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 4.1 — System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
- Spring Boot — Traditional WAR Deployment: https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html
- Spring Boot Maven Plugin — Packaging: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Apache Tomcat — Which Version Do I Want?: https://tomcat.apache.org/whichversion.html
- Apache Tomcat — Migration Guide 10.1: https://tomcat.apache.org/migration-10.1.html
- Apache Tomcat — Migration Guide 11.0: https://tomcat.apache.org/migration-11.0.html
- Maven — Dependency Mechanism and Scopes: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Java 17 — JarFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Java 17 — Class File Format: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html

**Remember:** To know whether a WAR is compatible with its target server, you must verify **Java runtime, bytecode, Servlet specification, Java EE/Jakarta EE namespace, dependencies/scopes, server version, and an actual external deployment test**. A passing build or an executable WAR running in another environment does not prove deployment readiness.