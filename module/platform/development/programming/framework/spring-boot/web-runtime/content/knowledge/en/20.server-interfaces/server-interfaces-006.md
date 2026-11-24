# JSP Limitations by Server and Packaging Type

In Spring Boot, a web application can return HTML from **JSP (Jakarta Server Pages)** through Spring MVC. However, JSP does not have uniform support across every Servlet container and packaging format. In particular, an application may run in an IDE and open JSP pages via Maven, yet fail to find or compile JSPs once packaged as an **executable JAR**. This is an issue of the **JSP engine, `ServletContext` mechanics, and artifact layout**, not simply a view-resolver bug.

This lesson uses **Spring Boot 3.3.x, Java 17+, and Spring MVC Servlet** as its reference baseline. When upgrading major versions or switching containers, check the corresponding documentation. The focus is understanding the JSP support matrix across **Tomcat / Jetty / Undertow** and **executable JAR / executable WAR / externally deployed WAR**, so you can choose an appropriate project structure and verification workflow.

## 1. Learning Outcomes

After this lesson, you should be able to:

1. Explain how a JSP is compiled and executed as a **Servlet**, and how Spring MVC maps a **logical view name** to a JSP file.
2. State the official limitations: **Tomcat/Jetty + WAR** is the supported path for JSP in embedded setups, **executable JARs do not support JSP**, and **Undertow does not support JSP**.
3. Distinguish an **executable WAR run with `java -jar`** from a **WAR deployed to an external Servlet container**; understand the role of **`SpringBootServletInitializer`** and the **`provided`** dependency scope.
4. Place JSPs in the right location (**`src/main/webapp/WEB-INF/jsp/`**), configure view prefix/suffix, and declare the JSP compiler and JSTL dependencies using Spring Boot 3.x's **`jakarta`** namespace.
5. Build a minimal application with one JSP view and one REST endpoint, package a WAR, and verify both HTML and JSON over real HTTP requests.
6. Recognize failures caused by using a JAR, missing Jasper, wrong paths, `javax`/`jakarta` mismatches, wrong view resolvers, unsupported servlet containers, and improper error-page configuration.
7. Choose another rendering technology such as Thymeleaf when deployment requires executable JARs, container flexibility, or a decoupled frontend.

**Scope boundary:** this lesson covers **JSP runtime compatibility by server and packaging**. It does not go deep into scriptlet syntax, UI design, session management, or template engine tuning.

## 2. What Is JSP in a Spring MVC Web Application?

JSP is a **server-side view** technology of the Servlet ecosystem. A JSP is translated into Servlet code by a JSP engine (for example, Tomcat's **Apache Jasper**), compiled when needed, and executed to produce HTML. The browser never runs JSP; the browser receives only the final HTML response.

Typical flow:

~~~text
Browser: GET /ui/hello
       |
       v
Servlet container (Tomcat/Jetty with a suitable JSP engine)
       |
       v
DispatcherServlet
       |
       v
@Controller @GetMapping("/ui/hello")
       |
       +-- model.addAttribute("greeting", ...)
       +-- return "hello" (logical view name)
       |
       v
InternalResourceViewResolver
       |
       +-- prefix = /WEB-INF/jsp/
       +-- suffix = .jsp
       v
/WEB-INF/jsp/hello.jsp
       |
       v
JSP engine compiles/executes the JSP
       |
       v
HTTP 200 text/html + HTML body
~~~

In Spring MVC, **`@Controller`** with a **`String`**-returning method typically selects a view name; **`@RestController`** (or `@ResponseBody`) writes data directly to the response body without selecting a JSP. Therefore, changing `@Controller` to `@RestController` and returning `"hello"` can make the browser display literal **hello** without rendering the JSP at all.

**`InternalResourceViewResolver`** translates view name `"hello"` into Servlet resource path **`/WEB-INF/jsp/hello.jsp`**. That is only the view-selection step; it **does not install a JSP compiler**. The Servlet container must provide a compatible JSP engine to process the JSP file. Controller, view resolver, JSP engine, and WAR packaging are separate links in the chain.

JSPs should be placed inside **`WEB-INF`**: Servlet containers block HTTP clients from accessing files under `WEB-INF` directly, while controllers can forward to them for rendering. Placing JSPs outside `WEB-INF` can allow direct client access bypassing controllers or create hard-to-control UI routes.

## 3. Support Matrix by Server and Packaging

For **Spring Boot 3.3 embedded Servlet containers packaged as executable archives**, the Spring Boot documentation states:

| Servlet Server | Executable JAR (`java -jar file.jar`) | Executable WAR (`java -jar file.war`) | WAR Deployed to External Container |
| --- | --- | --- | --- |
| **Tomcat** | **JSP not supported** | **JSP works** when proper Jasper/Jakarta dependencies are present and JSPs are in WAR webapp | **Works**, provided external Tomcat and WAR match Servlet/Jakarta versions |
| **Jetty** | **JSP not supported** | **JSP should work**, requiring compatible JSP engine/modules and Jetty version | **Works**, provided external Jetty supplies JSP and matches the WAR |
| **Undertow** | **JSP not supported** | **JSP not supported** per Spring Boot | Do not treat this as a guaranteed JSP target; use a JSP-capable container |
| **Other Servlet containers** | JAR conclusions do not generalize to custom hacks | Depends on server/runtime; support cannot be assumed | Suitable only when the container supports Servlet/Jakarta, a JSP engine, and the matching environment |

**How to read the matrix:**

- The **executable JAR** column refers to **Spring Boot's application packaging format**. Even though the JAR contains embedded Tomcat and controllers work, **JSP is not supported by Spring Boot in executable JARs**. Adding Jasper while keeping JAR packaging does not bypass this limitation.
- The **executable WAR** column refers to a WAR packaged by the Spring Boot build plugin so it can both run via **`java -jar`** and be deployed to an external container. **WAR does not necessarily mean you must install Tomcat separately.**
- The **external WAR** column refers to a WAR loaded by an external container. Servlet/JSP implementations and deployment settings partly live in that container, so you may need to verify container versions and JSP modules.
- **Undertow does not support JSP** according to Spring Boot's JSP limitations guide. Do not switch to Undertow solely to save resources if you have a JSP requirement.
- For **Jetty**, the documentation says **should work** with WARs, which does not mean every default setup includes a JSP engine out of the box. Verify JSP integration, classloading, and the actual Jetty version before committing to production.

**Quick decision rule:** if a project requires JSP and uses an embedded Spring Boot container, choose **Tomcat + WAR** as the clearest supported path. If the artifact must be a **JAR**, choose a non-JSP view technology instead of forcing JSP into an executable JAR.

## 4. Why Do JAR and WAR Differ?

### 4.1. Executable JAR

A Spring Boot executable JAR typically has a layout like:

~~~text
application.jar
  META-INF/
  BOOT-INF/
    classes/
      com/example/...class
      application.yml
      static/
      templates/
    lib/
      spring-*.jar
      tomcat-*.jar
      ...
  org/springframework/boot/loader/...
~~~

JAR packaging suits Spring MVC REST APIs, static content in **`src/main/resources/static/`**, and template engines like Thymeleaf in **`src/main/resources/templates/`**. However, JSP relies on `ServletContext` web resources and JSP engine mechanics designed around a web application archive layout. Spring Boot **does not support JSP with executable JARs**. Do not assume that sitting inside `BOOT-INF/classes` qualifies a JSP file as a Servlet JSP resource.

In practice, **`src/main/webapp/`** is not a reliable directory in executable JARs; Spring Boot documentation warns that build tools normally ignore it when building a JAR. This explains why a JSP project can run in an IDE yet fail under **`java -jar app.jar`**.

### 4.2. Traditional WAR

WAR is the Java Servlet web application archive format. Its layout typically includes:

~~~text
application.war
  WEB-INF/
    classes/
      com/example/...class
      application.yml
    lib/
      spring-*.jar
      ...
    jsp/
      hello.jsp
  META-INF/
  ...
~~~

**`WEB-INF/jsp/hello.jsp`** is a Servlet resource inside the WAR and can be processed by the container's JSP engine when Spring MVC forwards to it. JSP files belong in the WAR's **webapp** root, unlike templates on `classpath:/templates`.

When deployed to an external Tomcat instance, Tomcat supplies the Servlet/JSP container while the application supplies controllers, services, and views. The WAR filename or container config typically determines the **context path**: **`demo.war`** may be served under **`/demo/ui/hello`**, whereas an executable WAR run with `java -jar` usually uses context path **`/`** unless **`server.servlet.context-path`** is changed. Do not hardcode external URLs without accounting for context path or reverse proxies.

### 4.3. Executable WAR and `WEB-INF/lib-provided`

The Spring Boot Maven/Gradle plugin can package a WAR as an **executable WAR**. To support both embedded execution and external deployment, container runtime dependencies should be declared as **`provided`** (Maven) or **`providedRuntime`** (Gradle) per Spring Boot's documentation.

In an executable WAR, the plugin places provided dependencies under **`WEB-INF/lib-provided/`**. When running **`java -jar application.war`**, the Boot loader can load them; when deployed to an external container, they are kept off the webapp's `WEB-INF/lib` classpath, preventing conflicts with the external container's Servlet engine.

Example diagram:

~~~text
application.war
  WEB-INF/
    classes/
    jsp/
      hello.jsp
    lib/
      spring-webmvc-*.jar
      ...
    lib-provided/
      tomcat-embed-*.jar
      tomcat-embed-jasper-*.jar
      ...
  org/springframework/boot/loader/...
~~~

This is a schematic, not an exact inventory of every artifact. **Inspect the actual built artifact** to confirm dependencies land in the right directory, especially after switching containers or tweaking packaging plugins.

**Do not confuse:** a plain WAR might lack the main/Boot launcher needed for `java -jar`; "WAR" and "executable WAR" are distinct properties. Only a properly configured Spring Boot build plugin produces an archive that both runs standalone and deploys externally.

## 5. Why Does JSP Depend on the Servlet Container?

### 5.1. Jasper and the JSP Engine

Tomcat supports JSP through the **Jasper** engine. Spring MVC only prepares the model, selects the view name, and forwards; Jasper handles JSP syntax, expression language, tag libraries, and compiling JSPs into Servlets when needed. Without the JSP compiler/runtime, the app may still boot and JSON APIs may still work, while requests to JSP pages fail with **404**, **500**, or compilation/servlet exceptions.

With embedded Tomcat, the project typically needs **`org.apache.tomcat.embed:tomcat-embed-jasper`**. Use the version managed by the Spring Boot BOM to prevent mismatches between Tomcat core and the JSP engine. Never pull in a random **`tomcat-jasper`** version from a different Tomcat release into an app using embedded Tomcat 10.1.

### 5.2. Jetty

Jetty provides its own JSP implementation/modules depending on the Jetty version and EE environment enabled. Spring Boot notes that JSP should work with Jetty in WAR packaging, provided compatible JSP dependencies/modules are included and initialized properly. Do not take Tomcat's Jasper dependency and assume it is the standard choice for Jetty.

If migrating from Tomcat to Jetty, verify **JSP rendering in the packaged WAR**, not merely app startup or a 200 API response. A Jetty deployment serving JSPs requires an actually working JSP-capable setup.

### 5.3. Undertow

According to Spring Boot's JSP limitations guide, **Undertow does not support JSP**. Using Undertow for REST APIs or non-JSP apps is a separate use case; do not treat swapping to Undertow while keeping JSP as a supported migration path.

### 5.4. Servlet and Jakarta EE Versions

Spring Boot 3.x uses **`jakarta.*`** instead of **`javax.*`** for Jakarta EE APIs. Spring Boot 3.3 works with Servlet containers supporting Jakarta, such as Tomcat 10.1. A Spring Boot 3.3 WAR should not be deployed onto an older **Tomcat 9** (which uses `javax.servlet`) expecting JSPs to translate automatically. Match the container to the Servlet/JSP API, Java runtime, and dependency management.

Errors like **`NoClassDefFoundError: javax/servlet/...`**, **`ClassNotFoundException: jakarta/servlet/...`**, or taglib/TLD failures often indicate mixing old and new libraries. Do not "fix" this by bundling both **`javax.servlet`** and **`jakarta.servlet`** into the WAR. Standardize on one Servlet/Jakarta generation compatible with your target Spring Boot version.

## 6. Complete Practice: Spring Boot 3.3 + Tomcat + Executable WAR + JSP

This example pins **Spring Boot 3.3.13**, **Java 17**, **Maven**, **Spring MVC**, and **embedded Tomcat** to show the exact WAR setup. In real projects, choose a supported patch release and follow your project's security update policy. Use the **Maven Wrapper** generated by Spring Initializr if available.

The application provides:

- **`GET /ui/hello`** → Spring MVC controller returns logical view **`hello`**; JSP renders HTML.
- **`GET /api/status`** → REST endpoint returns JSON without using JSP.
- **`GET /WEB-INF/jsp/hello.jsp`** → must not be directly accessible over HTTP.

### 6.1. Project Structure

~~~text
jsp-war/
  pom.xml
  mvnw
  mvnw.cmd
  src/
    main/
      java/com/example/jspwar/
        JspWarApplication.java
        PageController.java
        ApiController.java
      resources/
        application.properties
      webapp/
        WEB-INF/
          jsp/
            hello.jsp
    test/
      java/com/example/jspwar/
        PageControllerTest.java
~~~

**`src/main/webapp/WEB-INF/jsp/`** is the critical location. Do not move sample JSP files into **`src/main/resources/templates/`** expecting a Servlet view resolver to compile them automatically. The `templates` folder is for Thymeleaf/FreeMarker/Mustache, not the Servlet WAR webapp root.

### 6.2. Complete `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jsp-war</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>war</packaging>

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
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.apache.tomcat.embed</groupId>
            <artifactId>tomcat-embed-jasper</artifactId>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>jakarta.servlet.jsp.jstl</groupId>
            <artifactId>jakarta.servlet.jsp.jstl-api</artifactId>
        </dependency>

        <dependency>
            <groupId>org.glassfish.web</groupId>
            <artifactId>jakarta.servlet.jsp.jstl</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Dependency breakdown:**

1. **`spring-boot-starter-web`** brings Spring MVC and the embedded Tomcat starter.
2. Declaring **`spring-boot-starter-tomcat`** explicitly as **`provided`** prevents bundling embedded container libraries into `WEB-INF/lib` when deploying the WAR externally. Even though `starter-web` pulls Tomcat transitively, explicitly declaring `provided` scope is the pattern in Spring Boot's WAR deployment guide.
3. **`tomcat-embed-jasper`** is the JSP compiler/runtime for embedded Tomcat. **`provided`** scope lets Boot package it properly for executable/deployable WARs while external Tomcat uses its own JSP engine. Never hardcode a Jasper version different from the Tomcat version managed by Boot.
4. **`jakarta.servlet.jsp.jstl-api`** and **`org.glassfish.web:jakarta.servlet.jsp.jstl`** provide the Jakarta JSTL tag library. The Spring Boot 3.3 BOM manages their versions.
5. **`spring-boot-maven-plugin`** repackages the WAR into an executable WAR. An unrepackaged WAR will not execute via **`java -jar`** as a Spring Boot executable archive.
6. **`spring-boot-starter-test`** provides unit/controller testing; running Java tests alone **does not** prove the JSP compiler works inside the WAR.

If a JSP uses no JSTL at all, the two JSTL dependencies may not be required, though this example uses **`c:out`** to HTML-escape data. Spring Boot 3.x uses **Jakarta Tags 3.0** URI **`jakarta.tags.core`**; do not blindly copy tag URIs from Spring Boot 1.x/2.x projects.

### 6.3. Application Supporting Standalone Execution or External WAR Deployment

**`src/main/java/com/example/jspwar/JspWarApplication.java`**

~~~java
package com.example.jspwar;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class JspWarApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(JspWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(JspWarApplication.class, args);
    }
}
~~~

**`main()`** supports running the executable WAR with **`java -jar`**. **`SpringBootServletInitializer.configure(...)`** is the integration hook allowing an external Servlet container to initialize Spring Boot from the WAR. For apps run solely standalone without external deployment, the initializer is not always mandatory; here it is included to cover **both execution modes**.

### 6.4. Controller Returning a JSP View

**`src/main/java/com/example/jspwar/PageController.java`**

~~~java
package com.example.jspwar;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {
    @GetMapping("/ui/hello")
    public String hello(Model model) {
        model.addAttribute("greeting", "Hello from JSP WAR!");
        return "hello";
    }
}
~~~

**`return "hello"`** is a logical view name, not a body string. **`@Controller`** must not be switched to `@RestController` if you want to render JSP. The model is passed to the view, where JSP EL/JSTL reads the data.

### 6.5. API Independent of JSP

**`src/main/java/com/example/jspwar/ApiController.java`**

~~~java
package com.example.jspwar;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/api/status")
    public Map<String, String> status() {
        return Map.of("status", "ok");
    }
}
~~~

REST endpoints can work even when the JSP engine is broken. That is why **a 200 API response is not enough to prove JSP rendering works**.

### 6.6. View Resolver

**`src/main/resources/application.properties`**

~~~properties
spring.application.name=jsp-war
server.port=8080
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
~~~

The Spring MVC view resolver combines:

~~~text
logical view: hello
prefix:       /WEB-INF/jsp/
suffix:       .jsp
result:       /WEB-INF/jsp/hello.jsp
~~~

The view path is a Servlet webapp resource, not an external JVM filesystem path outside the archive. **Prefix** should end with **`/`**, and **suffix** is **`.jsp`**. Do not append **`.jsp`** directly in the controller string when suffix is already configured, to avoid **`hello.jsp.jsp`**.

### 6.7. Actual JSP File

**`src/main/webapp/WEB-INF/jsp/hello.jsp`**

~~~jsp
<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>JSP WAR</title>
</head>
<body>
    <h1><c:out value="${greeting}" /></h1>
</body>
</html>
~~~

JSTL's **`c:out`** tag renders model content as HTML text and escapes special characters by default. Avoid injecting unvalidated input into HTML with scriptlets or unescaped expressions. No Java scriptlets **`<% ... %>`** are needed for this example.

### 6.8. Testing Controller Logic—Plus Smoke Testing the Real WAR

**`src/test/java/com/example/jspwar/PageControllerTest.java`**

~~~java
package com.example.jspwar;

import org.junit.jupiter.api.Test;
import org.springframework.ui.ExtendedModelMap;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PageControllerTest {
    @Test
    void returnsJspLogicalViewName() {
        ExtendedModelMap model = new ExtendedModelMap();
        String viewName = new PageController().hello(model);

        assertEquals("hello", viewName);
        assertEquals("Hello from JSP WAR!",
                model.getAttribute("greeting"));
    }
}
~~~

This test verifies that the controller picks the logical view name and populates the model, but it **does not boot a Servlet container, run Jasper, or verify WAR packaging**. That is an intentional boundary: testing JSP compatibility requires adding an HTTP smoke test against the **packaged artifact**.

### 6.9. Building and Running the Executable WAR

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/jsp-war-0.0.1-SNAPSHOT.war
~~~

Windows (PowerShell or CMD):

~~~text
mvnw.cmd clean package
java -jar target/jsp-war-0.0.1-SNAPSHOT.war
~~~

If the project lacks a Maven Wrapper, use a compatible Maven installation via **`mvn clean package`**. The WAR filename in this example matches **`artifactId=jsp-war`** and **`version=0.0.1-SNAPSHOT`**; adjust commands if your artifact differs.

In another terminal:

~~~bash
curl -i http://localhost:8080/ui/hello
curl -i http://localhost:8080/api/status
~~~

**First expectation:** HTTP 200, HTML Content-Type, and body containing:

~~~html
<h1>Hello from JSP WAR!</h1>
~~~

**Second expectation:** HTTP 200, JSON Content-Type, and body containing:

~~~json
{"status":"ok"}
~~~

JSON key order in a single-key object yields the exact body above; HTTP headers, charset, and whitespace in the full HTML may vary by environment. **`GET /WEB-INF/jsp/hello.jsp`** must not return raw JSP source to the client.

**Important:** a successful build only proves Java compilation and packaging succeeded; **JSP compilation may happen only when the first request arrives**. You must actually call **`/ui/hello`** on the running executable WAR and check the HTTP status, body, and server logs.

### 6.10. Inspecting WAR Contents

Use the JDK **`jar`** tool:

~~~bash
jar tf target/jsp-war-0.0.1-SNAPSHOT.war
~~~

In the entry list, verify **`WEB-INF/jsp/hello.jsp`**, **`WEB-INF/classes/`**, and the required libraries. When Spring Boot repackages an executable/deployable WAR with provided dependencies, **`WEB-INF/lib-provided/`** should appear. If **`WEB-INF/jsp/hello.jsp`** is missing from the WAR, the view resolver cannot conjure it out of thin air.

When reporting errors, capture the **artifact name, Java version, Spring Boot version, runtime server, root-cause log, and URL/status** to separate build failures, packaging errors, server issues, and view errors.

## 7. Deploying the Same WAR to External Tomcat

With the sample app, **`JspWarApplication extends SpringBootServletInitializer`** allows an external Servlet container to bootstrap the Spring context. Conceptual steps:

1. Build **`jsp-war-0.0.1-SNAPSHOT.war`**.
2. Confirm the external Tomcat matches the app's **Jakarta Servlet/JSP** generation; for instance, Tomcat **10.1** matches Spring Boot 3.3, unlike Tomcat 9.
3. Deploy the WAR via the container's deployment mechanism. **Do not change the embedded port in `application.properties` expecting it to configure external Tomcat's port**: the external container owns connectors and ports.
4. Determine the deployment's actual context path (derived from the WAR name or context config). If deployed under **`/jsp-war`**, URLs carry that prefix.
5. Call both **`/jsp-war/ui/hello`** and **`/jsp-war/api/status`**, verifying both HTML and JSON.
6. Check for library conflicts between packaged JARs and the container's JSP/JSTL modules; avoid duplicate Servlet/JSP engines inside **`WEB-INF/lib`**.

If deployed as **`ROOT.war`** on the root context, external URLs may omit the application-name prefix. Never blindly assume identical URLs between an executable WAR and an external WAR. Verify **port, context path, reverse proxy mappings, and security rules** on the real environment.

**Ownership difference:** with **`java -jar .war`**, Boot starts the embedded container; in an external WAR, the external container owns startup, shutdown, and the `ServletContext`. That is why **`provided`** scope is necessary so Boot's embedded Tomcat runtime is not placed on the webapp classpath alongside the external container's engine.

## 8. Gradle and the Equivalent `providedRuntime` Rule

If a project uses Gradle, you do not have to switch to Maven just to use JSP. Apply the **`war` plugin** to build a WAR and **`providedRuntime`** for servlet container dependencies. Below is an **illustrative Gradle configuration** for Spring Boot **3.3.x** using Java, Spring Boot, dependency management, and the `war` plugin:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    providedRuntime 'org.apache.tomcat.embed:tomcat-embed-jasper'
    implementation 'jakarta.servlet.jsp.jstl:jakarta.servlet.jsp.jstl-api'
    implementation 'org.glassfish.web:jakarta.servlet.jsp.jstl'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Build and run:

~~~bash
./gradlew clean bootWar
java -jar build/libs/jsp-war-0.0.1-SNAPSHOT.war
~~~

On Windows use **`gradlew.bat clean bootWar`**. When the **`war` plugin** is applied, the Spring Boot Gradle plugin creates the **`bootWar`** task, segregating dependencies so runnable WARs and externally deployable WARs do not clash with external container libraries.

**Do not confuse:**

- **`bootJar`** builds an executable JAR, unsuitable for validating JSP.
- **`bootWar`** builds an executable WAR, suitable for JSP with a compatible server/JSP engine.
- **`war`** builds a standard plain WAR whose packaging differs from `bootWar`.
- **`implementation`** and **`providedRuntime`** do not mean the same thing; container dependencies belong in the scope suited for both embedded and external use.
- Adding the `war` plugin **does not fix** misplaced JSP files or missing Jasper/JSTL dependencies.

The Gradle snippet pins versions consistent with the Maven example. When a project has existing build conventions or its own Gradle Wrapper, use the project-managed versions and plugins rather than duplicating configuration.

## 9. Other JSP Limitations That Remain Even with a WAR

### 9.1. `error.jsp` Does Not Automatically Replace Spring Boot's Error Page

In Spring Boot, adding an arbitrary **`error.jsp`** file does not automatically override the **default error view**. Spring Boot uses its **`/error`** pipeline, **`BasicErrorController`**, `ErrorAttributes`, view resolvers, and status-specific custom error page paths. The JSP limitations documentation explicitly notes you must **configure a custom error page appropriately** to customize error rendering.

A simpler and common approach for HTTP 404 is creating **`src/main/resources/public/error/404.html`** per Spring Boot's custom error page mechanism, or using a dedicated template/error view resolver. Do not assume **`/WEB-INF/jsp/error.jsp`** alone is a sufficient convention to handle all errors.

When an app serves both JSPs to browsers and JSON to APIs, check **`Accept`**, Content-Type, and HTTP status; never let a fallback JSP return HTTP 200 HTML for an API error that should be 404 or 500. Custom error handlers must not leak stack traces, credentials, or sensitive data.

### 9.2. JSPs Do Not Live in `src/main/resources/templates`

Many auto-configured template engines look under **`classpath:/templates/`**. For JSP, the view resolver typically forwards to a **Servlet resource** like **`/WEB-INF/jsp/`**. The two mechanisms are not equivalent. Moving JSPs to **`resources/templates`** to share Thymeleaf's path is not guaranteed to work.

Using **`src/main/webapp/WEB-INF/jsp`** matches WAR packaging. For executable JARs, **`src/main/webapp`** is normally omitted from Servlet resources, so this is not a "workaround" to make JSP work in a JAR.

### 9.3. JSP Needs a JSP Engine Even When the Controller Returns the Right View

A controller returning **`"hello"`**, a view resolver knowing the path, and the Spring context starting up do not prove Jasper is present. JSPs can require first-request compilation. Smoke tests must run against the same **server + artifact + classpath** as the target deployment, not solely via **`MockMvc`**.

### 9.4. Jakarta JSTL Differs from Legacy `javax`/JSTL Libraries

For Spring Boot 3.x / Jakarta Tags 3.0, dependencies and URIs must align. The lesson example uses:

~~~jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<c:out value="${greeting}" />
~~~

Older Spring Boot 1.x/2.x guides may use **`javax.servlet`** and taglib URIs like **`http://java.sun.com/jsp/jstl/core`**. Do not copy legacy configurations verbatim into a Boot 3 project and conclude JSP is unsupported. Choose Jakarta-compatible JSTL API/implementation artifacts and inspect the dependency tree.

**Security:** use **`c:out`** or appropriate HTML escaping for untrusted data. Legacy JSP scriptlets embedding raw Java inside pages are hard to test, hard to maintain, and prone to escaping bugs; keep business logic in controllers/services and let views focus on presentation.

### 9.5. Limitations of `MockMvc` Tests

**`MockMvc`** tests Spring MVC handlers, models, status codes, redirects, or logical view names without starting a real JSP-capable container. A **`view().name("hello")`** assertion can PASS even if the WAR lacks the JSP file or Jasper is absent. Treat it as only one test layer; verifying server compatibility requires **building the WAR and requesting the JSP over real HTTP**.

### 9.6. Servlet Stack and Reactive Stack Do Not Share JSP View Paths

JSP belongs to the Servlet server-side view model. Spring WebFlux uses reactive view rendering and compatible template engines; adding **`spring.mvc.view.prefix`** to a pure WebFlux app does not enable JSP. Using Tomcat as the HTTP server for a reactive stack does not automatically turn WebFlux into a Spring MVC JSP application.

### 9.7. Native Images and Specialized Packaging

JSP relies on dynamic compilation/rendering via a JSP engine and Servlet resource/class loading. Do not assume a JSP WAR will work unchanged in a **GraalVM native image**, custom layered archive, or runtime lacking standard filesystem/resource handling. If deployment targets native images or minimal executable JARs, reconsider the view technology rather than promising JSP support just because a native build compiled.

## 10. Layer-by-Layer Verification Workflow

A claim that **"JSP is supported"** is reliable only after verifying every layer:

| Layer | Question | How to Verify |
| --- | --- | --- |
| **1. Build** | Does the build produce a WAR? | `pom.xml` `packaging=war` / Gradle `war` plugin; `.war` file exists. |
| **2. Artifact** | Is the JSP inside `WEB-INF/jsp`? | List entries with `jar tf`; confirm `WEB-INF/jsp/hello.jsp`. |
| **3. Dependencies** | Are the JSP compiler and JSTL versions aligned? | Maven `dependency:tree` or Gradle `dependencies`; check for `ClassNotFoundException` logs. |
| **4. Server** | Is the actual container JSP-capable Tomcat/Jetty? | Startup logs, dependency tree, external container config; exclude Undertow. |
| **5. MVC** | Does the controller select the JSP view? | `@Controller` returns view name; prefix/suffix match; test model/view. |
| **6. HTTP** | Does the JSP actually render? | `curl -i` the controller JSP URL; status 200, `Content-Type: text/html`, expected HTML. |
| **7. Compatibility** | Does the same WAR run in the other target mode? | Separate smoke tests on embedded WAR and supported external container. |
| **8. Operations** | Are error pages, URL prefixes, security, and encoding right? | Test 404, JSON API, HTML escaping, context path, and logs. |

Do not conclude support solely from **`mvn test PASS`**, **`Spring started`**, or **`GET /api/status` returning 200**. All three can succeed while Jasper fails to render a single page.

## 11. Real-World Troubleshooting

### 11.1. Works in IDE, Fails JSP in `java -jar .jar`

**Symptom:** IDE renders views properly, executable JAR returns 404/Whitelabel error or cannot find JSP. **Primary cause:** JSP is not supported in **executable JARs**, and **`src/main/webapp`** is not packaged as a Servlet WAR layout. **Resolution:** switch packaging to **WAR** and run **`java -jar file.war`** on JSP-capable Tomcat/Jetty, or migrate JSPs to a JAR-compatible template engine if JAR artifacts are required.

Stop trying to add Jasper dependencies to a JAR without changing packaging: doing so does not remove the limitation documented by Spring Boot.

### 11.2. WAR Boots, but Opening JSP Returns HTTP 500

**Suspects:** missing **`tomcat-embed-jasper`**, JSP compilation error, JSTL taglib error, mixing Javax/Jakarta, missing runtime class, or mismatched container/JSP engine versions. **Checks:** inspect the root exception in server logs, dependency tree, `lib-provided`/`lib` entries, and JSP path. **Fixes:** align BOM dependencies, add the right server JSP engine, use Jakarta taglibs, and fix JSP syntax.

Failures appearing on the very first request make sense because JSP compilation can occur lazily on demand. Never assume successful application startup means JSP compilation already succeeded.

### 11.3. 404 on `/ui/hello`

**Suspects:** `@Controller` not scanned, wrong `@GetMapping`, different servlet context path, WAR deployed under a prefix, wrong view path, or missing JSP file inside the WAR. **Checks:** call `/api/status` with the same base URL, inspect mapping logs, list WAR entries, and verify the actual request URL.

Distinguish a **404 from an unmatched controller** from a **missing view/JSP resource error**: one occurs before handler selection, the other after the view resolver runs.

### 11.4. Browser Displays Literal `hello` Instead of the Page

**Suspects:** using **`@RestController`**, **`@ResponseBody`**, or a `text/plain` return. **Fix:** use **`@Controller`** with a logical view name, and do not return a JSP file path directly as a body string. If the browser sees raw JSP source code, check JSP engine/Servlet mappings and resource exposure; never allow browsers to download raw JSP source directly.

### 11.5. Circular View Path or 500 During View Resolution

**Suspects:** missing prefix/suffix on view resolver, view name matching the handler URL, forwarding back into the same handler, or missing view file. **Fix:** set **`spring.mvc.view.prefix=/WEB-INF/jsp/`** and **`spring.mvc.view.suffix=.jsp`**, return view name **`"hello"`** instead of URL **`"/ui/hello"`**, and confirm the JSP sits under `WEB-INF`.

Do not add **`@EnableWebMvc`** randomly to fix views: it alters many other MVC auto-configurations.

### 11.6. `NoClassDefFoundError: javax.servlet.*` or `jakarta.servlet.*`

**Suspects:** Boot 3.x WAR running in Tomcat 9 / older Servlet API, or `javax` dependencies brought over from a Boot 2.x project into a Jakarta runtime. **Fix:** use a Jakarta-compatible container and aligned dependency versions; remove incompatible legacy libraries. Avoid "fixing" it by shipping both `javax` and `jakarta` simultaneously.

### 11.7. Works on Tomcat, Fails on Jetty or Undertow

**Jetty:** verify the right JSP module, Jetty/Jakarta Servlet version, classloader, and WAR packaging; documentation only states **WAR should work**, without guaranteeing every setup works automatically.

**Undertow:** does not support JSP per Spring Boot documentation. Choose a JSP-capable container or change view technologies; tweaking prefix/suffix will not resolve it.

### 11.8. Added `error.jsp`, Still Seeing Default Error Page

**Cause:** Spring Boot uses its own **`/error`** pipeline and error view mechanism; a file named `error.jsp` does not override it automatically. **Fix:** configure status-specific custom error pages (such as `public/error/404.html`), a custom template/error view resolver, or an `ErrorController` while preserving proper HTTP status codes.

### 11.9. Same WAR Runs Standalone, Fails When Deployed Externally

**Suspects:** external container incompatible with Jakarta/Servlet, duplicate container dependencies in `WEB-INF/lib`, missing JSP engine in the external container, changed context path, or differing JNDI/service expectations. **Checks:** `provided` scope, `jar tf`, external container logs, Java version, and WAR classpath. Never infer from **`java -jar .war` working** that every external server is compatible.

## 12. Choose JSP or Another View Technology?

| Requirement | Usually Suitable Choice | Reason |
| --- | --- | --- |
| Maintaining a large legacy Spring MVC app with JSP/JSTL | **Keep JSP, use tested WAR + Tomcat/Jetty** | Reduces migration cost, preserves existing views within supported scope. |
| New project, server-side HTML with executable JAR | **Thymeleaf, FreeMarker, or Mustache** | Templates in `classpath:/templates`, free of JSP WAR packaging constraints. |
| REST API + independent SPA/SSR frontend | **JSON API and separate frontend** | Decouples backend from JSP engines and Servlet view paths. |
| Easy switching across Tomcat, Jetty, and Undertow | **Avoid JSP** | JSP support is not uniform across containers. |
| Undertow required | **Do not design around JSP as view engine** | Undertow does not support JSP per Spring Boot docs. |
| Executable JAR required | **Choose another template engine** | Spring Boot does not support JSP in executable JARs. |
| WAR deployed to an existing external Tomcat | **JSP may fit**, verify Jakarta and scope | Container supplies Servlet/JSP engine; still requires smoke testing. |

Spring Boot recommends **avoiding JSP when a suitable alternative exists**, due to embedded Servlet container limitations. That does not mean every legacy JSP app must be rewritten immediately; base the decision on packaging/server requirements, testability, migration cost, and long-term upgrade paths.

## 13. Decision and Acceptance Checklist

- [ ] Confirmed the app uses **Spring MVC Servlet**, not confused with WebFlux.
- [ ] Confirmed the actual container: Tomcat, Jetty, Undertow, or another external Servlet container.
- [ ] If JSP is required, chose appropriate **WAR packaging**; never treat executable JAR as supported.
- [ ] If Undertow is used, dropped JSP requirements or switched servers.
- [ ] Placed JSPs in **`src/main/webapp/WEB-INF/jsp/`** and verified presence in the built WAR.
- [ ] **`@Controller`** returns logical view names; **`@RestController`** is used for API bodies.
- [ ] **`spring.mvc.view.prefix/suffix`** match Servlet resource paths without doubling `.jsp`.
- [ ] Included compatible JSP engine; for embedded Tomcat, verified **`tomcat-embed-jasper`**.
- [ ] Servlet/JSP/JSTL dependencies use **Jakarta** compatible with Spring Boot 3.x.
- [ ] Container runtimes use **`provided` / `providedRuntime`** when building WARs for both standalone and external deployment.
- [ ] Included **`SpringBootServletInitializer`** if deploying the WAR to an external Servlet container.
- [ ] Ran **`java -jar app.war`** and verified the JSP renders HTML over HTTP.
- [ ] Smoke-tested the WAR on the target external container, including context path and security.
- [ ] Kept independent JSON API tests; never substitute a 200 API response for a JSP smoke test.
- [ ] Configured custom error pages via Spring Boot's mechanism rather than only adding `error.jsp`.
- [ ] Kept JSP sources private inside `WEB-INF`; HTML-escaped rendered output.
- [ ] Planned a JSP replacement path if migrating to executable JARs, Undertow, or native deployment.

### Self-Check Questions

**1. Can you run a Spring MVC REST API using an executable JAR + Tomcat?** Yes. The limitation discussed here applies to **JSP**, not all of Spring MVC or embedded Tomcat.

**2. Is adding `tomcat-embed-jasper` to an executable JAR enough?** No. Spring Boot does not support JSP with executable JAR packaging. Switch to WAR or replace the template engine.

**3. Does an executable WAR require installing an external Tomcat?** No. A WAR properly repackaged by the Spring Boot plugin can run via **`java -jar app.war`** using the embedded container, while also supporting deployment to a compatible external container.

**4. Why are Tomcat/Jasper dependencies marked `provided` for external deployment?** Because the external container already provides Servlet/JSP runtimes; `provided` avoids mixing container libraries onto the application classpath. In a Boot executable WAR, those dependencies go into `lib-provided` for standalone execution.

**5. Are Jetty and Undertow identical regarding JSP?** No. Spring Boot states Jetty + WAR **should work** with a compatible setup, whereas Undertow **does not support JSP**.

**6. Why is `@Controller` returning `"hello"` different from `@RestController` returning `"hello"`?** `@Controller` selects a view via the view resolver, whereas `@RestController` writes the string directly into the HTTP body.

**7. If a `MockMvc` test for `viewName` PASSES, do you still need to test the WAR?** Yes. `MockMvc` does not verify Jasper, Servlet resource layout, or external deployment. Only an HTTP smoke test against the WAR exercises the full chain.

**8. Why doesn't `error.jsp` appear automatically when an API errors?** Spring Boot has its own `/error` pipeline, error views, and content negotiation. Use an explicit custom error page or error handler.

## 14. Official Documentation

1. [Spring Boot 3.3 — Servlet Web Applications: JSP Limitations](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): direct source for the JSP matrix, executable JAR/WAR, Undertow, and `error.jsp`.
2. [Spring Boot 3.3 — Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html): guide for WAR, `SpringBootServletInitializer`, Maven `provided`, Gradle `providedRuntime`, and external container deployment.
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.mvc.view.prefix` and `spring.mvc.view.suffix`.
4. [Spring Framework — JSP and JSTL](https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-jsp.html): `InternalResourceViewResolver` and the recommendation to place JSPs under `WEB-INF`.
5. [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): compatible Java, Servlet container, and Spring Framework baselines.

**Key takeaway:** choosing JSP means simultaneously choosing **the view technology, a JSP-capable Servlet server, a WAR artifact, JSP placement inside the WAR, and matching Jakarta dependencies**. Your build pipeline and HTTP smoke tests must match **the exact container + packaging type used in deployment**; running in an IDE or seeing a REST API return 200 is never enough to conclude JSP works.
