# Root WebApplicationContext, Servlet Context, and Parent–Child Relationship

## 1. The Problem to Understand When Bootstrapping a Spring MVC Application

When developing Spring MVC applications, you encounter several similarly named objects: `ApplicationContext`, `WebApplicationContext`, `ServletContext`, `DispatcherServlet`, and `ContextLoaderListener`. They have distinct responsibilities. Without distinguishing them, it is easy to run into unmapped controllers, uninjected services, the same bean initialized twice, or MVC configuration placed in the wrong context.

A web application can be organized with **a single Spring context** or **a parent–child context hierarchy**. In the classic hierarchical model:

- **Root `WebApplicationContext`** holds beans shared across the application, such as services, repositories, data sources, transaction managers, or infrastructure configuration.
- **Servlet-specific `WebApplicationContext`** (dedicated to a single `DispatcherServlet`) typically holds controllers, handler mappings, view resolvers, message converters, and that servlet's web configuration.
- Root is the **parent**; the servlet context is the **child**. A child can look up beans from its parent, whereas the parent does not automatically see beans declared only in a child.
- An application can have multiple `DispatcherServlet` instances, each with its own child context referencing a shared root context.

**Important point:** Root–child is **an organizational option** of Spring MVC on the Servlet stack; it is not mandatory for every Spring Web application, especially in modern Spring Boot applications.

## 2. Distinguishing Five Frequently Confused Concepts

| Component | Belongs To | Responsibility | Holds Spring Beans? |
|---|---|---|---|
| `ApplicationContext` | Spring Core | IoC container: creates, manages, and wires beans; manages configuration, events, and lifecycle | Yes |
| `WebApplicationContext` | Spring Web | Extends `ApplicationContext` for the Servlet web environment; accesses `ServletContext` and related objects | Yes |
| `ServletContext` | Jakarta Servlet API | Represents the web application's environment in the Servlet container; stores attributes and web app metadata | Not a Spring IoC container |
| `DispatcherServlet` | Spring MVC | Front controller that receives HTTP requests, finds handlers, coordinates MVC strategies, and builds responses | Not an IoC container; uses a `WebApplicationContext` |
| `ContextLoaderListener` | Spring Web on Servlet | Initializes and destroys the root `WebApplicationContext` aligned with the web application lifecycle | Not a container, rather a bootstrap component |

`WebApplicationContext` is an interface extending `ApplicationContext`, not a single special bean named "webApplicationContext". There are multiple implementations, such as `AnnotationConfigWebApplicationContext` and `XmlWebApplicationContext`. A single application can own multiple Spring contexts, yet **each context has its own bean registry and management scope**.

`ServletContext` is usually provided by the Servlet container (such as Tomcat) for a web application. It is not the servlet-specific Spring child context. The phrase "servlet context" in this lesson's topic must be understood in context: **`ServletContext`** (Jakarta API) differs from **`DispatcherServlet`'s `WebApplicationContext`** (Spring). Their names look similar, yet the objects and responsibilities differ.

## 3. Diagram of Root Context and Servlet Child Context

```text
                    Servlet container (e.g., Tomcat)
                                  |
                      ServletContext (Jakarta)
                                  |
                    +-------------+-------------+
                    |                           |
          ContextLoaderListener           Servlet registrations
                    |                           |
                    v                    +------+------+
       Root WebApplicationContext         |             |
           (shared beans)                 v             v
            - OrderService           DispatcherServlet A  DispatcherServlet B
            - OrderRepository             |             |
            - DataSource                  v             v
            - TransactionManager       Child A        Child B
                    ^                  (web MVC)       (web MVC)
                    |                     |             |
                    +------ parent -------+             |
                    +-------- parent -------------------+
                                          |             |
                                    controllers A  controllers B
                                    mappings A     mappings B
                                    views A        views B
```

The `parent` arrow depicts Spring's `ApplicationContext.getParent()` relationship, **not** Java class inheritance. Each child still has its own bean definitions, scopes, and lifecycle; only bean lookup and resolution can walk up to the parent.

With only a single `DispatcherServlet`, the model is similar:

```text
Root WebApplicationContext
    ├── UserService
    └── UserRepository
          ↑ parent of
Servlet WebApplicationContext
    ├── UserController
    ├── HandlerMapping
    ├── HandlerAdapter
    └── ViewResolver
          ↑ used by
     DispatcherServlet
```

**Purpose of separation:** Servlets can share the business layer while remaining independent in endpoints, views, or web configuration. For example, one servlet serves user routes and another serves admin routes. Do not create multiple servlets or contexts merely to "make the architecture look layered" when one context suffices.

## 4. What Is the Root WebApplicationContext?

The root context is the web-application-level `WebApplicationContext`, typically initialized early by `ContextLoaderListener` in a Servlet container WAR deployment. It can hold:

- Business services: `CustomerService`, `OrderService`, etc.
- Repositories and data-access layer dependencies.
- DataSources, transaction managers, and external-system clients.
- Infrastructure beans that need to be shared across servlet contexts.

Java root configuration example:

```java
package com.example.hierarchy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RootConfig {
    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }
}
```

`GreetingService` is an ordinary Java class; in this example `@Bean` registers it into the **root context**. The root being named "root" does not automatically make every class a bean in root: which context a bean appears in depends on which configuration is loaded into that context.

When root exists, Spring stores a reference to the root `WebApplicationContext` in an attribute of the Jakarta `ServletContext`. To look up root from low-level servlet components, Spring provides `WebApplicationContextUtils.getWebApplicationContext(servletContext)` or `getRequiredWebApplicationContext(servletContext)`; this retrieves **root**, not an automatic pick among every `DispatcherServlet` child.

### Root Context Is Optional

A small application can have only a servlet-specific `WebApplicationContext`. When there is no need to share infrastructure across multiple servlets, splitting root and child can add unnecessary configuration complexity. `AbstractAnnotationConfigDispatcherServletInitializer` allows returning `null` from `getRootConfigClasses()` to avoid creating a separate root.

Conversely, placing all configuration in root and returning `null` from `getServletConfigClasses()` is also supported by Spring MVC when separating web and shared config into two groups is unnecessary; however, you must understand how the initializer and `DispatcherServlet` use the resulting context. When learning the parent–child relationship, use two separate configurations to observe it clearly.

## 5. What Is the Servlet-Specific WebApplicationContext?

`DispatcherServlet` uses a `WebApplicationContext` dedicated to itself. This is the typical place to configure:

- Controllers (`@Controller`, `@RestController`).
- `HandlerMapping` and `HandlerAdapter` to detect and invoke HTTP handler methods.
- View resolvers, template/view configuration.
- HTTP message converters, formatters, validators.
- MVC configurations such as `@EnableWebMvc`, `WebMvcConfigurer`.

Child configuration example:

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class WebConfig {
    @Bean
    public GreetingController greetingController(
            GreetingService greetingService,
            ApplicationContext applicationContext) {
        return new GreetingController(greetingService, applicationContext);
    }
}
```

Here:

1. `WebConfig` is registered into the **child**.
2. `GreetingController` becomes a bean of the child.
3. `GreetingService` is registered only in root, yet is injected into the controller bean in the child via parent lookup.
4. `ApplicationContext` injected when creating a bean in the child is the context creating that bean; it can be used to inspect `getParent()`.

In classic configurations, each `DispatcherServlet` can receive a different child context, allowing two servlets to have separate sets of controllers/views. Which routes a servlet handles also depends on the **Servlet mapping** (such as `/api/*` or `/admin/*`) and the request mappings inside Spring MVC.

### Do Not Assume Controllers in Root Will Be Discovered by DispatcherServlet

Spring MVC's default handler mappings normally look for controllers in **the DispatcherServlet's own context**. Beans from the parent can be injected into the child, yet detecting **handler methods** in ancestor contexts is not enabled by default in common handler mappings. Therefore, to stay clear and avoid configuration-dependent behavior, place controllers and MVC configuration in the child, and place shared services/repositories in root.

If component scanning is accidentally configured to cover the entire package in both root and child, the same component can be instantiated as **two separate beans**, leading to separate service state, duplicate resource initialization, or unpredictable mappings.

## 6. Parent–Child Relationship: How Spring Resolves Beans

The core characteristic of the `ApplicationContext` hierarchy is that **lookup walks from child up to parent** when the child lacks a matching bean.

Consider the bean tree:

```text
ROOT
  bean: auditService
  bean: greetingService

CHILD /api
  bean: apiController
  bean: greetingFormatter

CHILD /admin
  bean: adminController
  bean: adminViewResolver
```

Key conclusions:

| Operation | Typical Outcome |
|---|---|
| `/api` child retrieves `greetingService` | Can find the bean in root |
| `/admin` child retrieves `auditService` | Can find the bean in root |
| Root looks up `apiController` | Does not automatically look down into child |
| `/api` child looks up `adminController` | Does not automatically look sideways into a sibling child |
| Child has a bean with the same name as one in root | The local bean of the same name can shadow the parent bean during child lookup |

If the child contains a bean named `greetingService` and root also contains `greetingService`, lookup by name from the child normally returns the local bean. However, **lookup by type (`getBean(SomeType.class)` or autowiring) involves additional rules for candidates, primary, qualifiers, and precedence**; do not assume every name and type collision resolves identically. Use explicit bean names, narrow component scans, and `@Qualifier` only when truly needed.

Singleton beans must also be understood within the scope of **a single container**: `singleton` means one instance per bean definition in one `ApplicationContext`, not an automatic guarantee of a single object across the entire JVM. Two contexts scanning and registering the same `@Service` can create two distinct singletons.

### Can the Parent Be Changed Dynamically?

At the API level, contexts provide a mechanism to set a parent during certain initialization phases. In practice, define the hierarchy **before refreshing the contexts** and keep it stable. Changing the parent of a running context or arbitrarily closing root while a child still uses root beans can cause unpredictable behavior.

## 7. Who Initializes Root and Child, and in What Order?

In a Spring MVC WAR application not using Spring Boot's bootstrap, the Servlet container drives the web application lifecycle and startup typically proceeds as follows:

1. The Servlet container initializes `ServletContext`.
2. A Spring Servlet initializer or `web.xml` configuration registers `ContextLoaderListener` and one or more `DispatcherServlet` instances.
3. When `ContextLoaderListener` is invoked during web application startup, it creates and `refresh`es the root `WebApplicationContext`, registers shared beans, and publishes root via `ServletContext`.
4. `DispatcherServlet` is initialized; it uses or creates its own `WebApplicationContext`, establishes the parent relationship when root exists, and initializes the required MVC strategies.
5. The Servlet container maps URLs according to Servlet mappings; requests reaching `DispatcherServlet` are processed by MVC beans in the servlet's context, which can inject beans from root.
6. When the web application stops, the respective context initializers clean up lifecycles and close the contexts they manage.

Exact startup order and details also depend on servlet registration, `load-on-startup`, and the bootstrap strategy. This is a typical flow, not advice to manually call `refresh()` inside a controller or create an `ApplicationContext` per request.

### Are ContextLoaderListener and DispatcherServlet the Same Object?

No. `ContextLoaderListener` is a web-application-level **listener** that bootstraps root; `DispatcherServlet` is a **servlet** that handles HTTP and owns its own context. Both can participate in startup while holding independent responsibilities. If you use only a single context, a separate `ContextLoaderListener` may not be needed.

## 8. Runnable Example: One Root Context and One Servlet Child

The example below demonstrates the exact dependency path and parent lookup mechanism. It uses **Spring Framework 6.2.x**, **Java 17+**, **Jakarta Servlet 6**, and deploys as a **WAR on Tomcat 10.1** or a compatible container. This is traditional Servlet bootstrapping without Spring Boot.

Maven project structure:

```text
spring-context-hierarchy-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/hierarchy/
                ├── AppInitializer.java
                ├── RootConfig.java
                ├── WebConfig.java
                ├── GreetingService.java
                └── GreetingController.java
```

### 8.1. Declaring Dependencies and Packaging the WAR

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-context-hierarchy-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
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
        <finalName>context-demo</finalName>
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

`spring-webmvc` brings in the required Spring MVC components. `jakarta.servlet-api` has scope `provided` because Tomcat supplies the Servlet API at runtime. No `web.xml` is needed because Spring provides the initializer mechanism per the Servlet specification.

### 8.2. Creating the Shared Service and Root Config

File `GreetingService.java`:

```java
package com.example.hierarchy;

public class GreetingService {
    public String greet(String name) {
        return "Hello " + name;
    }
}
```

File `RootConfig.java`:

```java
package com.example.hierarchy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RootConfig {
    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }
}
```

`GreetingService` is registered **solely in root**. `@Service` is not needed because it is declared via `@Bean`. This avoids duplicate scanning and makes bean ownership unambiguous.

### 8.3. Creating the Controller Belonging to Child

File `GreetingController.java`:

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;
    private final ApplicationContext context;

    public GreetingController(
            GreetingService service,
            ApplicationContext context) {
        this.service = service;
        this.context = context;
    }

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello(@RequestParam(defaultValue = "Lan") String name) {
        return service.greet(name);
    }

    @GetMapping(value = "/context", produces = MediaType.TEXT_PLAIN_VALUE)
    public String contextInfo() {
        ApplicationContext parent = context.getParent();
        return "hasParent=" + (parent != null)
                + ", parentHasService="
                + (parent != null && parent.containsLocalBean("greetingService"))
                + ", childHasController="
                + context.containsLocalBean("greetingController");
    }
}
```

File `WebConfig.java`:

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class WebConfig {
    @Bean
    public GreetingController greetingController(
            GreetingService service,
            ApplicationContext context) {
        return new GreetingController(service, context);
    }
}
```

Explanation:

- `@EnableWebMvc` registers MVC infrastructure in the **servlet child context**.
- `GreetingController` is a bean defined in the child via `@Bean`, and also carries `@RestController`/`@GetMapping` annotations so Spring MVC recognizes its HTTP handlers.
- `GreetingService` does not exist locally in the child; dependency injection walks up to root to fetch the bean.
- The `/context` endpoint lets you directly inspect the parent relationship and bean registration locations.
- Because it only returns plain text strings, the example requires no Jackson/JSON serialization configuration.

### 8.4. Registering Both Contexts

File `AppInitializer.java`:

```java
package com.example.hierarchy;

import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class AppInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return new Class<?>[] { RootConfig.class };
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

`AbstractAnnotationConfigDispatcherServletInitializer` assists with registering `DispatcherServlet` and Java-configured contexts. When `getRootConfigClasses()` returns `RootConfig.class`, Spring creates the root context; when `getServletConfigClasses()` returns `WebConfig.class`, Spring creates the servlet context with root as its parent. The `"/"` Servlet mapping routes the application's URLs to this `DispatcherServlet`.

**Import syntax note:** Java allows line breaks between whitespace-separated tokens, though not inside a single identifier. For readability and easy copying, the import can be written on a single line as:

```java
import org.springframework.web.servlet.support.AbstractAnnotationConfigDispatcherServletInitializer;
```

### 8.5. Compile, Deploy, and Observe Results

Place the files into the exact `com.example.hierarchy` package and run from the directory containing `pom.xml`:

```bash
mvn -q -DskipTests package
```

Maven produces the WAR at `target/context-demo.war`. Copy the WAR into Tomcat 10.1's `webapps` directory and start Tomcat. If the application is deployed under the default WAR-derived context path `/context-demo` and Tomcat listens on port 8080, call:

```bash
curl -s "http://localhost:8080/context-demo/hello?name=Lan"
```

Expected response body:

```text
Hello Lan
```

Next, inspect the context structure:

```bash
curl -s "http://localhost:8080/context-demo/context"
```

Expected response body:

```text
hasParent=true, parentHasService=true, childHasController=true
```

These are the expected values when the WAR is properly deployed, context mapping is intact, configuration is unmodified, and requests are not intercepted by another filter/proxy. When accessing an application deployed at another context path, substitute the `/context-demo` prefix accordingly.

How to read the result yourself:

- `hasParent=true`: the controller lives in a child that has a parent.
- `parentHasService=true`: `greetingService` is registered **locally in root**, not accidentally instantiated in the child.
- `childHasController=true`: `greetingController` is registered locally in the context used by `DispatcherServlet`.
- `/hello` works: the child successfully uses the `GreetingService` dependency from its parent.

The example uses Spring MVC on a Servlet container; do not use standalone `javac`/`java` to run a single class because dependencies, WAR packaging, and a Servlet container are required.

## 9. Equivalent Configuration via web.xml

In traditional or legacy systems, the root context and servlet context are declared in `web.xml`. The condensed example below illustrates XML-based configuration (the `/WEB-INF/root-context.xml` and `/WEB-INF/api-servlet.xml` files must exist and contain valid bean configurations):

```xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <context-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>/WEB-INF/root-context.xml</param-value>
    </context-param>

    <listener>
        <listener-class>
            org.springframework.web.context.ContextLoaderListener
        </listener-class>
    </listener>

    <servlet>
        <servlet-name>api</servlet-name>
        <servlet-class>
            org.springframework.web.servlet.DispatcherServlet
        </servlet-class>
        <init-param>
            <param-name>contextConfigLocation</param-name>
            <param-value>/WEB-INF/api-servlet.xml</param-value>
        </init-param>
        <load-on-startup>1</load-on-startup>
    </servlet>

    <servlet-mapping>
        <servlet-name>api</servlet-name>
        <url-pattern>/api/*</url-pattern>
    </servlet-mapping>
</web-app>
```

This is an **explanatory configuration snippet**, not a standalone runnable example: it requires the two corresponding Spring XML files and a full WAR application. Their functions differ:

- `context-param/contextConfigLocation` at the `web-app` level instructs `ContextLoaderListener` to load root.
- `init-param/contextConfigLocation` inside `<servlet>` instructs `DispatcherServlet` to load its own configuration.
- `servlet-mapping` determines the URI portion served by that servlet.

**Do not accidentally mix `web.xml` and a Java initializer to register the same root/servlet.** If the project already uses one bootstrap mechanism, check the existing configuration before adding a second one.

## 10. With Two DispatcherServlets, How Are Sharing and Isolation Handled?

Suppose an application has:

```text
Root:  sharedService, repository, transactionManager
   |
   +-- Child A (DispatcherServlet "public")
   |     +-- PublicController
   |     +-- public MVC configs
   |
   +-- Child B (DispatcherServlet "admin")
         +-- AdminController
         +-- admin MVC configs
```

`PublicController` and `AdminController` can inject the same `sharedService` bean from root. If neither servlet re-registers a bean of the same name/type, they reference the same root singleton object. However, `PublicController` cannot arbitrarily retrieve `AdminController` simply by looking it up in Child A.

Servlet URL mappings must be designed without conflicts, such as `/public/*` and `/admin/*`. Within each servlet, controller path mappings are evaluated against the path mapped into that servlet. Authorization is not automatically enforced merely by having separate servlets; an appropriate security mechanism is still needed.

**Why not put all controllers in root?** Because handler discovery and web configuration for each servlet need to stay clear, and root should hold only what truly needs sharing. If root contains controllers with identical mappings and a child enables custom ancestor handler scanning, duplicate or unpredictable mappings can occur.

## 11. Spring Boot Typically Has a Different Context Architecture

Many traditional Spring MVC resources describe a root `ContextLoaderListener` and child `DispatcherServlet` as mandatory. That view is **not true for every Spring Boot application**.

In a typical Spring Boot Servlet web application:

- Boot starts the Spring application context and embedded Servlet container via Boot's configuration mechanism.
- Boot automatically registers and configures `DispatcherServlet` along with the required MVC components.
- Controllers, services, and repositories usually reside together in **a single application context** component-scanned from the package containing the `@SpringBootApplication` class.
- Manually declaring `ContextLoaderListener` or writing `AbstractAnnotationConfigDispatcherServletInitializer` is usually unnecessary.
- Having a `DispatcherServlet` in Boot does not imply there will automatically be a separate child servlet context as in the classic WAR diagram.

Simple Boot example:

```java
@SpringBootApplication
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}
```

This is an **illustrative snippet**, not independently runnable because imports, dependencies, classpath, and project setup are omitted. When using Spring Boot, inspect the actual created contexts instead of inferring solely from the name `DispatcherServlet`.

A context hierarchy can exist in a Boot application if explicitly configured for a specific need, yet that is a deliberate choice requiring an understanding of context ownership, component scanning, and bootstrapping. For ordinary applications, a single context is sufficient.

## 12. Common Error Scenarios and How to Check

### 12.1. Controller Not Found, Request Returns 404

Common possibilities:

- The controller is registered only in root while the child servlet searches for handlers in its local context.
- Root/child scans the wrong package or the config class is not loaded into the intended context.
- The Servlet mapping does not match the URL (for example, the servlet serves `/api/*` while the request is sent to a different path).
- `@GetMapping` and the HTTP method/path do not match, or the application has a different context path.

To check, match the full URL comprising **application context path + servlet mapping + controller mapping**; verify which context owns the controller bean and inspect Spring MVC startup logs.

### 12.2. NoSuchBeanDefinitionException When Injecting a Service

For instance, a controller in a child needs `OrderService` and cannot find it. Possible causes include `OrderService` not being registered, root config not being loaded, the bean being created in a sibling child, or component scan excluding that class.

Do not hastily add broad `@ComponentScan` to the child just to "make the service visible". If the service needs to be shared, register it in root and verify the child references the proper parent.

### 12.3. Service Initialized Twice

If both root and child have `@ComponentScan("com.example")`, the same `@Service` may be instantiated in both places. Check:

- Package scope scanned by each config.
- Local bean names and bean definitions (`containsLocalBean`).
- `ApplicationContext.getParent()` to see beans in the parent.
- Whether `@Bean` factory methods have duplicate declarations.

Scope component scanning by purpose: root scans shared components; child scans controllers/MVC configuration. In large projects, `includeFilters`, `excludeFilters`, or clear package separation can be used.

### 12.4. A Bean in Root Tries to Inject a Controller in Child

The parent **does not look down into the child through normal mechanisms**, so injection can fail. This is usually a sign of inverted architectural dependencies: services in root should not depend directly on HTTP controllers. Use service abstractions or appropriate application events/messaging so the business layer remains independent of the web layer.

### 12.5. MVC Configuration Placed in the Wrong Context

`@EnableWebMvc`, `HandlerMapping`, `HandlerAdapter`, and `ViewResolver` should usually belong to the child of the servlet that uses them in a hierarchical setup. If there is only one context, they live in that context. Do not treat `@EnableWebMvc` as an annotation that must be added to every context.

Especially with Spring Boot, manually adding `@EnableWebMvc` can alter Boot's automatic MVC configuration mechanism. Enable it deliberately only when you understand and want manual control over MVC configuration.

### 12.6. Web Scopes Do Not Behave as Expected

`request` and `session` are scopes tied to a web request/session, unlike context singletons. Using web scopes requires an appropriate web environment and access within the corresponding HTTP request scope. Having root/child does not automatically give arbitrary threads an active request scope; background tasks or manually spawned threads normally lack the request attributes of an HTTP request.

### 12.7. Calling getBean(...) Produces Confusing Results

Methods such as `containsBean`, `containsLocalBean`, `getBean`, and `getBeanNamesForType` have different semantics across a context hierarchy. Specifically, listing local bean names alone may exclude ancestor beans. When debugging, always note whether you are inspecting **root** or **child**, and whether the lookup API considers ancestors. Spring also provides `BeanFactoryUtils` for hierarchical lookups when needed.

## 13. Self-Check Questions

**Question 1.** In a two-context WAR configuration, `CustomerController` in child needs `CustomerService` in root. Can it be injected?  
**Answer:** Yes, provided the service is registered properly in root, the child is linked to the proper parent, and there are no conflicting bean candidates.

**Question 2.** Can `CustomerService` in root directly inject `CustomerController` that exists only in child?  
**Answer:** Not via normal parent lookup. A parent does not automatically access beans existing only in a child.

**Question 3.** With two `DispatcherServlet` instances, are two root contexts mandatory?  
**Answer:** No. One root can be shared by multiple servlet-specific child contexts.

**Question 4.** Are Tomcat's `ServletContext` and Spring's `WebApplicationContext` the same kind of container?  
**Answer:** No. `ServletContext` belongs to the Jakarta Servlet API; `WebApplicationContext` is a Spring IoC container capable of interacting with the Servlet environment.

**Question 5.** Does a Spring Boot REST application with `@RestController` and `@Service` have to configure `ContextLoaderListener` and a separate child context?  
**Answer:** No. Boot normally bootstraps the web application and MVC components automatically, typically needing only one application context.

**Question 6.** Does scanning `@Service` in both root and child guarantee a single singleton across the whole application?  
**Answer:** No. Singletons are managed per bean definition/context; duplicate scanning can create two instances.

**Question 7.** Can one `DispatcherServlet` automatically invoke a controller existing only in another servlet's child context?  
**Answer:** No. Two child contexts are siblings and have no mechanism to automatically look up each other's beans.

## 14. References

- [Spring Framework Reference — DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html): role of `DispatcherServlet`, web application bootstrap, and Servlet environment integration.
- [Spring Framework Reference — Context Hierarchy](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/context-hierarchy.html): root and servlet-specific child model, bean sharing, Java initializer, and equivalent `web.xml` configuration.
- [Spring Framework Reference — Servlet Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/container-config.html): registering `DispatcherServlet` with Java configuration.
- [Spring Framework Reference — ApplicationContext Hierarchies in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/hierarchies.html): testing hierarchies in integration tests.
- [Javadoc — AbstractAnnotationConfigDispatcherServletInitializer](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/servlet/support/AbstractAnnotationConfigDispatcherServletInitializer.html): root/servlet configuration API and behavior when no separate root is used.

**Key takeaway:** `WebApplicationContext` is the Spring IoC container for web environments; `ServletContext` is a Servlet API object. In Spring MVC's hierarchical model, root holds shared beans and each `DispatcherServlet` can have a child context holding servlet-specific web beans; the child sees the parent, while the parent does not automatically see the child. This structure is useful in WAR/multi-servlet setups, whereas typical Spring Boot applications work well with a single application context.
