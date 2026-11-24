# Registering `DispatcherServlet` in Java and Recognizing `web.xml` Configuration

## 1. Objectives and Context

After this lesson, you will be able to:

1. Explain why a Spring MVC application needs to register `DispatcherServlet` with the **Servlet container**.
2. Initialize Spring MVC in Java through `AbstractAnnotationConfigDispatcherServletInitializer`, without requiring `web.xml`.
3. Recognize how to directly implement `WebApplicationInitializer` and call `ServletContext.addServlet(...)`.
4. Read traditional Servlet configuration in `WEB-INF/web.xml` and map each part to Java configuration.
5. Distinguish **Servlet registration**, **Spring application context**, **Spring MVC configuration**, and **Spring Boot auto-configuration**.
6. Build, package a WAR, deploy, invoke the endpoint, and diagnose the causes of common initialization errors.

**Scope:** Spring MVC on the **Jakarta Servlet stack**, illustrated with Java 17+, Spring Framework 6.2, and Tomcat 10.1. Older versions may use the `javax.servlet.*` namespace and a different initialization layout; do not mix `javax` and `jakarta` within the same example.

## 2. Why Must `DispatcherServlet` Be Registered?

### 2.1. The Servlet Container and Spring MVC Have Different Responsibilities

In a WAR application running on Tomcat, Jetty, or another Servlet container:

- The **Servlet container** accepts HTTP connections, manages the lifecycle of Servlets, Filters, and Listeners, and maps URLs to Servlets.
- **`DispatcherServlet`** is Spring MVC's central Servlet. After the container routes a request here, it finds the appropriate handler/controller, processes input data, and produces the HTTP result.
- **Spring `WebApplicationContext`** holds Spring beans (controllers, services, converters, `HandlerMapping`, `HandlerAdapter`, …) serving the Servlet.

```text
          HTTP GET /mvc-demo/hello
                       |
               Tomcat / Servlet container
                       |
             Servlet URL mapping: "/"
                       |
               DispatcherServlet
                       |
              Spring WebApplicationContext
                       |
      HandlerMapping -> HandlerAdapter -> @GetMapping
                       |
                HelloController
                       |
               HTTP 200 + response body
```

Even if a class is annotated with `@RestController`, a request **cannot reach that class** if the Servlet container does not initialize/map the HTTP entry point and Spring does not create the context containing the controller. In other words, **registering the Servlet** and **declaring a controller** are two separate tasks.

### 2.2. Java Registration Mechanism at Startup

Since Servlet 3.0, containers support registering a `Servlet` in Java. In a traditional Spring MVC application:

1. When deploying a WAR, the Servlet container uses the `ServletContainerInitializer` mechanism per the Jakarta Servlet specification to discover initializers.
2. Spring provides `SpringServletContainerInitializer`, which is discovered through the service-provider declaration in the appropriate JAR.
3. Spring's initializer finds valid `WebApplicationInitializer` implementations on the application classpath and invokes `onStartup(ServletContext)`.
4. The initialization code creates or specifies a Spring `WebApplicationContext`, registers `DispatcherServlet`, declares the URL mapping, and configures eager loading.
5. The container initializes `DispatcherServlet`; the Servlet connects to the Spring MVC infrastructure; HTTP requests begin being dispatched.

When using `AbstractAnnotationConfigDispatcherServletInitializer`, the superclass performs the boilerplate registration in step 4. Therefore, the application **does not need to write `web.xml`** solely to declare the dispatcher.

Note: discovery also depends on the Servlet container configuration, a properly packaged WAR, and initializers not being disabled/skipped during scanning. Simply naming a class `WebAppInitializer` is not enough; the class must inherit from/implement the proper SPI.

## 3. Preferred Approach: `AbstractAnnotationConfigDispatcherServletInitializer`

### 3.1. Three Methods That Determine Configuration

The `org.springframework.web.servlet.support.AbstractAnnotationConfigDispatcherServletInitializer` class provides a concise declaration style:

```java
package example.web;

import org.springframework.web.servlet.support.AbstractAnnotationConfigDispatcherServletInitializer;

public class WebAppInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return null;
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] { WebConfig.class };
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] { "/" };
    }
}
```

Meaning of each method:

| Method | Value in Example | Meaning |
| --- | --- | --- |
| `getRootConfigClasses()` | `null` | Do not create a separate root Spring context. A small exercise only needs the dispatcher's context. |
| `getServletConfigClasses()` | `WebConfig.class` | Declares the Java `@Configuration` used for the `DispatcherServlet`'s `WebApplicationContext`. |
| `getServletMappings()` | `"/"` | Registers the dispatcher as the **default Servlet mapping** of the web application, allowing paths such as `/hello` to be mapped. |

**Common point of confusion:** `getServletMappings()` is not the `@GetMapping` annotation. The `"/"` mapping routes a group of requests **into the Servlet**; Spring MVC then continues matching endpoint paths based on `@RequestMapping`, `@GetMapping`, and MVC configuration.

`"/"` is the **default mapping** in the Servlet specification; `"/*"` is a broader path-prefix mapping and may intercept requests meant for JSPs or other Servlets. Do not swap these two values arbitrarily.

### 3.2. Configuring Spring MVC with `@EnableWebMvc`

Create a `WebConfig` class in the same package:

```java
package example.web;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@ComponentScan(basePackages = "example.web")
public class WebConfig {
}
```

- `@Configuration`: declares a Spring bean configuration class.
- `@EnableWebMvc`: enables Java-based MVC configuration, registering the request-processing components needed for controller mappings, handler adapters, and foundational MVC features.
- `@ComponentScan`: discovers controllers/components in the selected package. In large projects, keep the scanned package scope narrow enough to avoid unintentionally loading too many beans.

In plain Spring Framework, `@EnableWebMvc` is the typical way to provide annotation-driven MVC configuration. In **Spring Boot MVC**, if you want to retain Boot's auto-configuration, you usually do **not** add `@EnableWebMvc` unless you intentionally want full manual control over MVC configuration.

### 3.3. Demonstration Controller

```java
package example.web;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping(path = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "DispatcherServlet received the request";
    }
}
```

`@RestController` includes response-body return semantics; `@GetMapping("/hello")` declares the **handler mapping inside Spring MVC**. The content is plain text, so the example does not depend on a JSON serializer just to return a string.

When the WAR is deployed under the `/mvc-demo` context path, the actual request URL is:

```text
http://localhost:8080/mvc-demo/hello
                     |       |
             context path    handler mapping
```

This is the path **external to the application**. Internally, the Servlet mapping `"/"` operates on the path after the context path, and Spring MVC maps `/hello`.

## 4. Complete Deployable WAR Example

Together, the snippets below form a Maven project using **Spring Framework 6.2.0**, Jakarta Servlet 6.0, and Java 17. These versions serve a consistent exercise and do not imply you must use those exact versions in a production system.

### 4.1. File Structure

```text
mvc-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── web/
                    ├── WebAppInitializer.java
                    ├── WebConfig.java
                    └── HelloController.java
```

**Do not create `src/main/webapp/WEB-INF/web.xml`** for this Java initializer deployment branch. The three Java files use the exact contents from section 3.

### 4.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>mvc-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.0</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-webmvc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
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
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Key points to note:

- `spring-webmvc` provides Spring MVC components, including `DispatcherServlet`; the dependency transitively provides the underlying foundation.
- `jakarta.servlet-api` is **provided** because Tomcat supplies the Servlet API at runtime. Do not package a competing Servlet API inside the WAR.
- `packaging=war` builds the archive deployed by the Servlet container.
- `failOnMissingWebXml=false` expresses the intent that no XML descriptor is needed in the Java initializer branch.
- Source code uses `jakarta.servlet.*`, not `javax.servlet.*` as in older Servlet projects.

Note that Maven uses the `${spring.version}` property syntax in actual XML. If copying from a viewer introduces a `\` character before `$`, remove that backslash; the valid XML value is the Maven property name with `$` and curly braces.

### 4.3. Build, Deploy, and Verify

Prerequisites: JDK 17+, Maven, and Tomcat 10.1 installed; Tomcat 10.1 implements Jakarta Servlet 6.0. In the project directory:

```bash
mvn clean package
```

Upon a successful build, Maven produces `target/mvc-demo-1.0.0.war`. Copy the WAR to Tomcat's `webapps` directory as `mvc-demo.war` and start Tomcat. POSIX environment example:

```bash
cp target/mvc-demo-1.0.0.war "$CATALINA_BASE/webapps/mvc-demo.war"
```

If Tomcat uses `CATALINA_HOME` as the deployment directory and does not set a separate `CATALINA_BASE`, substitute the actual `webapps` path. On Windows, you can copy the file via File Explorer. Tomcat must be configured for WAR deployment and must be running; merely running `mvn package` does not start an HTTP server.

Use:

```bash
curl --fail-with-body http://localhost:8080/mvc-demo/hello
```

Expected response body:

```text
DispatcherServlet received the request
```

Port 8080, the context path, and the host here are **demo assumptions**; if the WAR name or connector is configured differently, the URL will differ. `curl` may print the response body without a trailing newline, which does not change the payload content.

Execution path when running properly:

```text
Tomcat discovers WebApplicationInitializer in WAR
    -> WebAppInitializer.onStartup(...)
    -> creates context from WebConfig
    -> registers DispatcherServlet with mapping "/"
    -> @ComponentScan discovers HelloController
    -> GET /mvc-demo/hello
    -> DispatcherServlet selects HelloController.hello()
    -> HTTP 200, text/plain body
```

If you want to verify which classes participate on your own, inspect the list of Servlet registrations at startup and `DispatcherServlet` initialization logs in Tomcat. Do not treat a successful package build as proof that the HTTP endpoint is running.

## 5. Writing `WebApplicationInitializer` Directly

Extending `AbstractAnnotationConfigDispatcherServletInitializer` is convenient, yet sometimes you need to see exactly how Spring communicates with the Servlet container. An equivalent option is to implement `org.springframework.web.WebApplicationInitializer` directly:

```java
package example.web;

import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRegistration;
import org.springframework.web.WebApplicationInitializer;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.DispatcherServlet;

public class ManualInitializer implements WebApplicationInitializer {

    @Override
    public void onStartup(ServletContext servletContext)
            throws ServletException {

        AnnotationConfigWebApplicationContext context =
                new AnnotationConfigWebApplicationContext();
        context.register(WebConfig.class);

        DispatcherServlet dispatcher = new DispatcherServlet(context);

        ServletRegistration.Dynamic registration =
                servletContext.addServlet("mvc", dispatcher);
        if (registration == null) {
            throw new ServletException("Servlet name 'mvc' is already in use");
        }

        registration.setLoadOnStartup(1);
        registration.addMapping("/");
    }
}
```

Meaning of each step:

1. Create `AnnotationConfigWebApplicationContext`: a Spring context taking configuration from annotations/Java classes.
2. `context.register(WebConfig.class)`: register the MVC configuration source. The context will be refreshed during the lifecycle managed by the dispatcher on initialization.
3. `new DispatcherServlet(context)`: associate the dispatcher with the Spring context.
4. `servletContext.addServlet("mvc", dispatcher)`: instruct the **Servlet container** to register a Servlet named `mvc`; returns a dynamic registration object.
5. `setLoadOnStartup(1)`: set initialization priority on application startup instead of waiting for the first request by default.
6. `addMapping("/")`: register the URL pattern at the Servlet layer.

**This is an alternative to `WebAppInitializer` in section 3.** To run this approach, **delete/remove the old `WebAppInitializer` class from the WAR**, create `ManualInitializer.java` with the content above, and keep `WebConfig` and `HelloController`. Do not deploy both initializers registering the `"/"` mapping at the same time; having different names does not make two Servlets valid front controllers for the same URL pattern.

Java Servlet registration can additionally configure init-params, async support, and multipart config when a problem requires it. This example focuses on the minimal initialization flow.

## 6. Recognizing Traditional `WEB-INF/web.xml`

### 6.1. Location and Role

`web.xml` is the **deployment descriptor** of a Servlet application. For a WAR, it is located at:

```text
src/main/webapp/WEB-INF/web.xml
          |
          v (after packaging)
WEB-INF/web.xml inside the WAR
```

This descriptor declares Servlets, Servlet mappings, Filters, Listeners, init-params, security constraints, and other Servlet container settings. It is read by the **Servlet container**, not as a plain Spring bean XML file.

### 6.2. `web.xml` Corresponding to the Java Example Above

To deploy the **same `WebConfig` and `HelloController` using XML**, remove the `WebAppInitializer`/`ManualInitializer` class from the WAR and add `src/main/webapp/WEB-INF/web.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <servlet>
        <servlet-name>mvc</servlet-name>
        <servlet-class>
            org.springframework.web.servlet.DispatcherServlet
        </servlet-class>

        <init-param>
            <param-name>contextClass</param-name>
            <param-value>
                org.springframework.web.context.support.AnnotationConfigWebApplicationContext
            </param-value>
        </init-param>

        <init-param>
            <param-name>contextConfigLocation</param-name>
            <param-value>example.web.WebConfig</param-value>
        </init-param>

        <load-on-startup>1</load-on-startup>
    </servlet>

    <servlet-mapping>
        <servlet-name>mvc</servlet-name>
        <url-pattern>/</url-pattern>
    </servlet-mapping>
</web-app>
```

This is an **XML descriptor for Servlet 6.0/Jakarta**, not using legacy Java EE/`javax.servlet` schema URIs. After deploying as in section 4, the endpoint is still `GET /mvc-demo/hello`.

Reading each tag:

| XML Element | Effect | Java Equivalent |
| --- | --- | --- |
| `<servlet>` | Declares a Servlet to the container | `servletContext.addServlet(...)` |
| `<servlet-name>mvc</servlet-name>` | Identifies the Servlet, linked to the mapping | Name `"mvc"` in `addServlet` |
| `<servlet-class>...DispatcherServlet</servlet-class>` | Specifies the Servlet class to instantiate | `new DispatcherServlet(context)` |
| `<init-param>contextClass</param-name>` | Uses `AnnotationConfigWebApplicationContext` instead of the default XML context | `new AnnotationConfigWebApplicationContext()` |
| `<init-param>contextConfigLocation</init-param>` | Points to `example.web.WebConfig`, the **configuration class name** when using an annotation-based context | `context.register(WebConfig.class)` |
| `<load-on-startup>1</load-on-startup>` | Initializes eagerly on deployment | `registration.setLoadOnStartup(1)` |
| `<servlet-mapping>` and `<url-pattern>/</url-pattern>` | Registers the URL pattern | `registration.addMapping("/")` |

**Do not confuse:** `contextConfigLocation` is a Spring **init-param name**. The meaning of its value depends on `contextClass`. With `XmlWebApplicationContext`, the value can be a bean XML file path; with `AnnotationConfigWebApplicationContext` in this example, it is a `@Configuration` class.

### 6.3. Recognizing More Traditional XML

In older codebases, you may encounter this configuration:

```xml
<servlet>
    <servlet-name>dispatcher</servlet-name>
    <servlet-class>org.springframework.web.servlet.DispatcherServlet</servlet-class>
    <init-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>/WEB-INF/spring/mvc-config.xml</param-value>
    </init-param>
    <load-on-startup>1</load-on-startup>
</servlet>
<servlet-mapping>
    <servlet-name>dispatcher</servlet-name>
    <url-pattern>/</url-pattern>
</servlet-mapping>
```

This is **a fragment inside a valid `web.xml`**, not a complete standalone file. It references the **Spring bean XML** `/WEB-INF/spring/mvc-config.xml`, a different file from the `web.xml` descriptor. When `contextClass` is not declared and `DispatcherServlet`'s default Servlet configuration is used, Spring typically uses `XmlWebApplicationContext`.

Many projects also omit `contextConfigLocation`: in that case, `DispatcherServlet` has a convention of looking for a default file based on `servlet-name`, for example `/WEB-INF/dispatcher-servlet.xml`. Do not assume every project uses the default path; inspect the actual `init-param` and context configuration.

If XML bean configuration is used, the `mvc-config.xml` file usually registers controller scanning and MVC annotation capabilities via corresponding elements such as `<context:component-scan>` and `<mvc:annotation-driven>`. These elements belong to **Spring bean XML**, not Servlet descriptor tags.

### 6.4. When Is `web.xml` Still Seen?

- Legacy Servlet/Spring MVC applications not yet migrated to Java initializers.
- Project teams maintaining a deployment descriptor convention for multiple Servlets, Filters, and Listeners.
- Systems intentionally combining a descriptor with controlled programmatic registration.

**Misconception:** a missing `web.xml` is not always a configuration error. With a suitable container and WAR, a Java initializer can perform registration entirely in code. The Maven WAR plugin may need explicit configuration indicating no descriptor is required, as in section 4.

## 7. Two Types of Spring Application Context

In large MVC systems, there may be a **root WebApplicationContext** and one or more **child WebApplicationContexts**, one per `DispatcherServlet`:

```text
ServletContext (entire web application)
  |
  +-- Root WebApplicationContext
  |      ├── services
  |      ├── repositories
  |      └── shared infrastructure
  |
  +-- DispatcherServlet "mvc"
            |
            +-- Child WebApplicationContext
                  ├── controllers
                  ├── HandlerMappings
                  ├── HandlerAdapters
                  └── view resolvers / MVC config
```

In simple examples, `getRootConfigClasses()` returns `null`, and Spring MVC configuration resides in the dispatcher's context. If you want to separate business layers and MVC configuration, you can write:

```java
@Override
protected Class<?>[] getRootConfigClasses() {
    return new Class<?>[] { RootConfig.class };
}

@Override
protected Class<?>[] getServletConfigClasses() {
    return new Class<?>[] { WebConfig.class };
}
```

This is only an **illustrative fragment**: a runnable application must define `RootConfig` and scope component scanning appropriately. In a context hierarchy, beans in the child usually see beans from the parent; the reverse is **not automatic**. If a controller is scanned into the root context instead of the servlet context, the child servlet context may not register handler mappings as expected.

The corresponding `web.xml` form usually includes `ContextLoaderListener` to initialize the root context; root config is set via `<context-param>`, while the child dispatcher is configured via `<servlet><init-param>...`. These are **two distinct configuration scopes** even though both use the name `contextConfigLocation`. Do not add `ContextLoaderListener` by default if the application does not need a separate root context.

## 8. Java Initializer vs. `web.xml`: Role Comparison

| Perspective | Java Initializer | `web.xml` |
| --- | --- | --- |
| Where declared | Java class in WAR implementing `WebApplicationInitializer` | `WEB-INF/web.xml` |
| Container activation mechanism | Discovers `ServletContainerInitializer` and invokes `onStartup` | Container parses the deployment descriptor |
| `DispatcherServlet` configuration | `addServlet(...)` or abstract initializer | `<servlet>` + `<servlet-class>` |
| URL mapping | `addMapping("/")` or `getServletMappings()` | `<servlet-mapping><url-pattern>/</url-pattern>` |
| Init-param | `registration.setInitParameter(...)` or logic in context | `<init-param>` |
| Eager loading | `setLoadOnStartup(1)` | `<load-on-startup>1</load-on-startup>` |
| Spring Java configuration | `WebConfig.class` | `AnnotationConfigWebApplicationContext` + class name |
| Root context when needed | `getRootConfigClasses()` | `ContextLoaderListener` with root context config |
| Best suited for | Java config projects on the Servlet stack | Legacy or descriptor-centric systems |

Both approaches lead to **a `DispatcherServlet` managed by the Servlet container**. Using a Java initializer does not mean bypassing the Servlet specification either: it uses that specification's own dynamic API.

## 9. How Does Spring Boot Initialize Differently?

With Spring Boot Web MVC and an embedded Servlet container, the entry point is usually `@SpringBootApplication` and `SpringApplication.run(...)`. Boot automatically sets up many parts of the servlet web server, context, dispatcher registration, and MVC configuration based on classpath/bean/property conditions.

An example **only to illustrate the Boot style**, independent of the plain Framework WAR in section 4:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

- With `spring-boot-starter-web`, a typical application does not need to write `WebAppInitializer` or `web.xml`.
- In Boot, you can use `ServletRegistrationBean` or `FilterRegistrationBean` when you truly need to register a custom Servlet/Filter; this belongs to the **Spring Boot API**, unlike implementing `WebApplicationInitializer` for a plain Spring Framework WAR.
- When packaging a WAR for deployment to an external Servlet container, Boot provides an appropriate workflow (such as `SpringBootServletInitializer`) and appropriate container dependency scoping. Do not take the plain Framework trio of classes in this lesson and assume it is the default setup for a Boot executable JAR.
- Spring WebFlux uses reactive HTTP dispatch; do not apply `DispatcherServlet` to a pure WebFlux server.

## 10. Common Errors and How to Verify

### 10.1. 404 Error Even Though `@GetMapping` Is Written

Check in order:

1. Are the host/port and **context path** of the WAR correct? `/mvc-demo/hello` differs from `/hello` when deployed as `mvc-demo.war`.
2. Did the WAR deploy successfully and did the container actually detect `WebAppInitializer`?
3. Is there a `"/"` mapping for the right `DispatcherServlet`?
4. Does `WebConfig` have `@EnableWebMvc` and `@ComponentScan` covering the controller package?
5. Does `@GetMapping` have the right path and HTTP method?
6. Is another Servlet capturing the mapping, or is a filter/security layer blocking the request?

If you call `GET /mvc-demo/hello` and receive 404, determine whether the 404 comes from **Tomcat before reaching Spring** or from **Spring MVC after finding no handler**; startup logs, mapping registrations, and request logs help distinguish them.

### 10.2. Application Does Not Detect the Initializer

Possible causes:

- The initializer class is not in the WAR's `WEB-INF/classes` or is not scanned.
- The class does not implement `WebApplicationInitializer` / extend the abstract initializer.
- The Spring MVC dependency is not packaged properly, or container initializer discovery is restricted by deployment configuration.
- Wrong Servlet container / `javax` versus `jakarta` namespace mismatch.
- Another bean/Servlet initialization error caused startup to fail; inspect the **first root error** in the server log.

Inspect WAR contents with the JDK tool:

```bash
jar tf target/mvc-demo-1.0.0.war
```

You should see at least `WEB-INF/classes/example/web/WebAppInitializer.class` and the related Spring JARs in `WEB-INF/lib`. Verify by actual class path inside the archive, not by Java source filenames on the development machine.

### 10.3. Duplicate `DispatcherServlet` or Mapping Conflict

Usually caused by keeping both `web.xml` and a Java initializer registering the same URL, or having multiple initializers coexist. The fact that Servlet containers permit combining Java and XML configuration **does not mean duplicate registration is valid**. Uniquely determine which mechanism owns each Servlet name/mapping and remove overlapping declarations.

### 10.4. Incorrect `contextConfigLocation`

- In `web.xml` with the default XML context: a value like `/WEB-INF/mvc-config.xml` is a path to **Spring bean configuration XML**.
- In `web.xml` configured with `AnnotationConfigWebApplicationContext`: `example.web.WebConfig` is a **configuration class name**.
- In a Java initializer: `getServletConfigClasses()` normally returns **`Class<?>[]`**, not XML filenames.
- `getRootConfigClasses()` and `getServletConfigClasses()` scanning overlapping packages can cause missing controllers or duplicate beans.

### 10.5. Mixing `javax` and `jakarta` Generations

Spring Framework 6 and Tomcat 10.1 work with Jakarta Servlet; Spring MVC 5/Tomcat 9 applications typically belong to the `javax.servlet.*` family. If the namespace is only half-migrated, errors may include `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, or Servlet initialization failure. Align framework, dependencies, container, and source imports; **do not try to fix it by adding two competing Servlet APIs side by side**.

### 10.6. Using `@EnableWebMvc` in the Wrong Context

In plain Framework, `@EnableWebMvc` is the standard way to set up Java MVC configuration. In Spring Boot, it can disable parts of the MVC auto-configuration that Boot provides. Check whether the project is a **plain Framework WAR or Boot** before copying code.

## 11. Self-Check Exercises

**Exercise 1 — identify mapping layers:** Given `getServletMappings() = new String[]{"/api/*"}` and a controller with `@GetMapping("/hello")`, with the WAR running at context path `/mvc-demo`. Requests typically take the form `GET /mvc-demo/api/hello`. Because `/api/*` is the Servlet mapping, the `/api` prefix is the Servlet path portion, while `/hello` is the corresponding controller mapping. Explain why calling `/mvc-demo/hello` does not reach that dispatcher.

**Exercise 2 — convert configuration:** From Java `getServletMappings() = new String[]{"/"}`, `getServletConfigClasses() = {WebConfig.class}`, `getRootConfigClasses() = null`, write a `web.xml` descriptor declaring `DispatcherServlet`, `contextClass`, and `contextConfigLocation` such that no root context is needed. Compare against the table in section 6.2.

**Exercise 3 — diagnose an error:** The WAR contains a controller and `WebConfig`, yet the servlet container logs no dispatcher registration. List three things to check before modifying `@GetMapping`: the initializer class inside the WAR, discovery mechanism, and Servlet/Spring compatibility.

**Exercise 4 — context design:** If there are two separate `DispatcherServlet` instances, each with different controllers sharing a common service, describe placing the service in the root context and MVC infrastructure in child servlet contexts. Distinguish when `ContextLoaderListener` is needed.

### Review Questions

- **Who registers `DispatcherServlet`?** The Servlet container receives the declaration from `web.xml` or Java registration performed by `WebApplicationInitializer`.
- **What is `WebApplicationInitializer`?** A Spring SPI automatically discovered via the Servlet container's initializer mechanism to configure `ServletContext` programmatically.
- **Does `@EnableWebMvc` replace `addServlet`?** No. It configures MVC beans; the Servlet container still needs to know about `DispatcherServlet`.
- **Is `web.xml` mandatory?** No, provided Java registration and the Servlet container's startup conditions are met.
- **Does `contextConfigLocation` always point to XML?** No; with `AnnotationConfigWebApplicationContext` it can point to a Java `@Configuration` class.
- **Does a Boot app with `spring-boot-starter-web` typically need the Java initializer shown in this lesson?** No. Boot provides its own bootstrap/auto-configuration process.

## 12. Official References

- DispatcherServlet and Java/XML configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html
- Servlet Config, `WebApplicationInitializer`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/container-config.html
- Context hierarchy: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/context-hierarchy.html
- Configuring Spring MVC with Java: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/config.html
- `WebApplicationInitializer` API: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/WebApplicationInitializer.html

**Key takeaway:** both `web.xml` and `WebApplicationInitializer` tell the Servlet container that `DispatcherServlet` exists and which URLs it handles. Spring `WebConfig` determines **how the dispatcher finds MVC beans/controllers**. These two layers of responsibility must be understood separately when initializing and debugging Spring MVC.
