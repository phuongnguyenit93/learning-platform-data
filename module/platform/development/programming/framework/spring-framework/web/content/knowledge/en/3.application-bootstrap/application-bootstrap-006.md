# Distinguishing Manual Spring MVC Configuration from Spring Boot Auto-Configuration

The exact same Spring MVC endpoint can run in a **manually configured Spring Framework** application or in a **Spring Boot application with auto-configuration**. Both still use core Spring MVC components such as `DispatcherServlet`, `HandlerMapping`, `HandlerAdapter`, `HttpMessageConverter`, and controllers. The primary difference lies in **who registers, wires, and supplies default configuration** for those components.

This lesson belongs to the *Application Bootstrap* section: the goal is to understand the initialization sequence, configuration responsibilities, the boundary between Spring Framework and Spring Boot, how to preserve useful Boot defaults when extending Spring MVC, and when to take manual control of configuration.

## 1. Distinguishing Three Layers of Responsibility

First, separate three layers that are often conflated:

1. **Spring Framework IoC container** (`ApplicationContext`, `@Configuration`, `@Bean`, `@ComponentScan`) creates, manages, and wires beans. It is not synonymous with an HTTP server.
2. **Spring Web MVC** is a web framework built on the Servlet API. It provides `DispatcherServlet` and the machinery to map requests to controllers, convert data, handle errors, render views, etc. To accept HTTP requests, `DispatcherServlet` must be registered in a Servlet container.
3. **Spring Boot** assists with bootstrapping the application and applies **conditional configuration** based on the classpath, application type, existing beans, and properties. For a Servlet app with matching libraries, Boot can configure an embedded web server, register `DispatcherServlet`, and supply Spring MVC defaults.

```text
                       CORE SPRING MVC
                          DispatcherServlet
                           │            │
                        Mapping       Adapter
                           │            │
                         Controller → Service
                           │
                         Response

       MANUAL SPRING FRAMEWORK                  SPRING BOOT
       ───────────────────────                  ───────────
       You register the Servlet                 SpringApplication.run(...)
       You enable MVC configuration             Boot decides applied configs
       You choose and configure container       Uses embedded server when suitable
       You add integrations as needed           Supplies many defaults automatically
```

**There are not two different "kinds of Spring MVC"**: Boot does not replace `DispatcherServlet` with a separate dispatcher. Controllers written with `@RestController` and `@GetMapping` still use Spring MVC APIs. Spring Boot can build an executable JAR with an embedded server, yet it can also be deployed as a WAR in an appropriate environment. Plain Spring Framework apps can also use an embedded server if the developer configures it manually; the WAR example below is chosen to highlight Servlet registration responsibilities.

## 2. Manual Spring MVC Configuration: Assembling the Web Layer Yourself

### 2.1. Mandatory Requirements

A traditional Spring MVC application using an external Servlet container must answer:

- **Which Servlet container** will accept HTTP connections? For instance, Apache Tomcat supporting the appropriate Jakarta Servlet version.
- **How is `DispatcherServlet` created and mapped to URLs?** For example, `/` or `/api/*`.
- **Which beans live in `WebApplicationContext`?** Including controllers/services and MVC configuration.
- **Who registers the MVC infrastructure configuration?** Typically `@EnableWebMvc`, conceptually equivalent to `<mvc:annotation-driven/>` in XML configuration.
- **What do non-default features require?** JSON converters, resource handlers, view resolvers, multipart support, exception advice, filters, interceptors, CORS... Depending on dependencies and configuration, each capability has different conditions.

`@EnableWebMvc` registers many MVC infrastructure beans such as request mappings, argument resolvers, and message converters suited to your dependencies. It **does not start Tomcat** and **does not replace `DispatcherServlet` registration**.

You can register `DispatcherServlet` using `web.xml`, `WebApplicationInitializer`, or the convenience class `AbstractAnnotationConfigDispatcherServletInitializer`. A root context and a Servlet context can be used in a hierarchical architecture; creating both is not mandatory for small applications.

### 2.2. Example A — Manual Spring MVC, Packaged as WAR

The example pins the platform to avoid API mismatches: **Java 17+, Spring Framework 6.2.x, Jakarta Servlet 6.0, and Tomcat 10.1**. Create a separate Gradle project named `manual-mvc` (with Gradle wrapper); `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'war'
}

group = 'demo'
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
    implementation 'org.springframework:spring-webmvc:6.2.19'
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
```

`spring-webmvc` contains the Spring MVC infrastructure; the Servlet API is only needed at compile time because Tomcat supplies it at runtime. The example returns a plain string so it **does not require a JSON library**. If you want a `record` serialized to JSON, an appropriate converter/dependency is needed and the MVC context config must be checked.

File `src/main/java/demo/manual/WebConfig.java`:

```java
package demo.manual;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = WebConfig.class)
public class WebConfig {
}
```

Explanation: `@Configuration` declares a configuration class for the Spring container; `@ComponentScan` discovers controllers and components in package `demo.manual` (including subpackages); `@EnableWebMvc` imports MVC infrastructure configuration. These three responsibilities are not interchangeable.

File `src/main/java/demo/manual/AppInitializer.java`:

```java
package demo.manual;

import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class AppInitializer
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

This class registers `DispatcherServlet`, initializes the Servlet web application context with `WebConfig`, and maps the Servlet at `/`. There is no separate root context in this example: controllers and MVC infrastructure reside together in the Servlet's context. **The `/` mapping is within the web application**; it does not automatically remove the context path when packaged as a WAR.

File `src/main/java/demo/manual/GreetingController.java`:

```java
package demo.manual;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/greet")
    public String greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return "Hello, " + name + "!";
    }
}
```

These are the **three complete Java files** in the Gradle project above. With the wrapper present:

```bash
./gradlew clean war
```

On Windows PowerShell you can run:

```powershell
.\gradlew.bat clean war
```

Deploy the WAR file from `build/libs/` to Tomcat 10.1 (for example, naming the deployment `manual-mvc.war`). Start Tomcat and test:

```bash
curl -i 'http://localhost:8080/manual-mvc/greet?name=Lan'
```

When deployed under context path `/manual-mvc`, a successful response has status **200 OK** and text body:

```text
Hello, Lan!
```

Actual WAR name and context path depend on how you deploy it. If the WAR is deployed as the root application, the path will be `/greet`. This example is **runnable given Gradle/JDK/Tomcat as described**, not with standalone `javac` because it requires dependencies and a Servlet container.

**Startup flow in the manual model:**

```text
Tomcat starts
  → discovers WebApplicationInitializer
  → AppInitializer registers DispatcherServlet mapping "/"
  → WebApplicationContext is created
  → WebConfig enables MVC infrastructure + component scan
  → GreetingController becomes a bean/handler
  → GET /greet → DispatcherServlet → controller → String response
```

Here the Servlet container actively invokes web application initialization. That differs from Boot's `SpringApplication.run` in the common JAR run style.

### 2.3. Manual Configuration Does Not Mean Writing Everything from Scratch

`@EnableWebMvc` supplies a practical baseline for Spring MVC. You can still implement `WebMvcConfigurer` to customize interceptors, view controllers, formatters, CORS, resource handlers, etc. For example:

```java
@Configuration
@EnableWebMvc
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/start", "/greet");
    }
}
```

This is an **illustrative replacement configuration for `WebConfig`**, requiring proper Spring type imports and keeping `@ComponentScan` if controllers are not declared as `@Bean`s. Do not overwrite the project above with this condensed snippet and forget component scanning. With manual registration, you are responsible for ensuring all needed parts of the application are compatibly configured.

## 3. Spring Boot: Conditional Auto-Configuration

### 3.1. Where Does Boot Initialize the Application From?

`@SpringBootApplication` combines three main behaviors:

- `@SpringBootConfiguration`: allows the application class to participate in Spring configuration, playing the role corresponding to `@Configuration` in this app style.
- `@EnableAutoConfiguration`: instructs Boot to evaluate appropriate auto-configurations.
- `@ComponentScan`: scans for `@Component`, `@Controller`, `@Service`, `@Configuration`, etc. in the application class's package and subpackages by default.

`SpringApplication.run(...)` builds the Spring application context, determines the application/web environment type, and runs the corresponding initialization chain. Given Servlet MVC dependencies and a suitable embedded server, Boot can create the embedded web server, register `DispatcherServlet`, and wire MVC infrastructure.

Auto-configuration is **not** "Boot scans every JAR and creates every bean regardless of what you have". Configurations are selected when conditions are satisfied, such as:

| Condition/Input | Role in Configuration Process |
| --- | --- |
| `@EnableAutoConfiguration` / `@SpringBootApplication` | Enables evaluation of auto-configurations |
| Classpath | Presence of matching classes like Servlet, DispatcherServlet, and web libraries |
| Application type | Servlet web application, reactive web application, or non-web application |
| Existing beans | Some defaults back off when the application already declares a bean with the same responsibility |
| Property | Enables/disables/tunes behavior when supported |
| Other conditions | For example, resources, other configs/beans, and evaluation order |

Annotations such as `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnWebApplication`, and `@ConditionalOnProperty` are the typical mechanisms. A starter normally bundles matching dependencies, while **auto-configuration** is the conditional bean registration logic; the two concepts are related yet distinct.

### 3.2. Example B — Spring Boot MVC with Embedded Server

To compare the same `/greet` endpoint, create a **separate project** named `boot-mvc` with **Java 17+ and Spring Boot 3.5.7** (pinned version so the example is reproducible; in real projects follow a currently supported release line). File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

You do not need to specify versions directly for `spring-webmvc`, the Servlet API, or embedded Tomcat because Boot's dependency management coordinates compatible versions. File `src/main/java/demo/boot/BootMvcApplication.java`:

```java
package demo.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootMvcApplication.class, args);
    }
}
```

File `src/main/java/demo/boot/GreetingController.java`:

```java
package demo.boot;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/greet")
    public String greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return "Hello, " + name + "!";
    }
}
```

With the Gradle wrapper present:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Open another terminal:

```bash
curl -i 'http://localhost:8080/greet?name=Lan'
```

Expected status **200 OK**, body:

```text
Hello, Lan!
```

You can also package with `./gradlew bootJar` and run the generated JAR in `build/libs/` using `java -jar <jar-file-name>`. The endpoint uses `/greet` because in this embedded JAR example the **default context path is root**. If another context path is configured, the URL changes.

**Startup flow in the Boot JAR:**

```text
main()
  → SpringApplication.run(BootMvcApplication.class, args)
  → scans package demo.boot and subpackages
  → evaluates auto-configurations by dependencies/conditions
  → creates Servlet web application context + embedded server (when applicable)
  → registers DispatcherServlet and MVC infrastructure
  → /greet is mapped to GreetingController
  → HTTP request → same Spring MVC processing mechanism
```

`@SpringBootApplication` **does not create endpoints automatically**: controllers must still be discovered by Spring and have matching mappings. If `GreetingController` is moved outside the scanned package without reconfiguring scanning, 404 can occur even though the Boot app starts.

### 3.3. What MVC Defaults Does Boot Supply?

In a Boot 3.x Servlet MVC app with complete dependencies, commonly preconfigured capabilities include:

- `DispatcherServlet` registration and coordinated MVC components.
- Multiple `HttpMessageConverter`s, including JSON when a suitable library is on the classpath.
- Static resource support from conventional locations (such as `classpath:/static/`, `classpath:/public/`) when the feature is enabled.
- `ViewResolver`s, content negotiation, binding/conversion, and error handling support per Boot configuration.
- Configuration via properties rather than re-registering entire blocks in Java code, where Boot supports it.

**Defaults depend on version/conditions**. Do not assume every converter, view resolver, security filter, or CORS rule appears in every app. For example, having Boot's web starter does not mean an API is authenticated or CSRF/CORS are configured for your business requirements.

## 4. Direct Comparison Table

| Criterion | Manually Configured Spring MVC | Spring Boot Auto-Configured MVC |
| --- | --- | --- |
| Request processing engine | Spring MVC's `DispatcherServlet` | The exact same `DispatcherServlet` from Spring MVC |
| Who triggers web initialization | Servlet container calls initializer or `web.xml`; or manually built embedded server | `SpringApplication.run` coordinates auto-config and suitable web server |
| Who registers `DispatcherServlet` | Developer registers it or uses an initializer | Boot provides an auto-configuration that registers it when conditions match |
| Enabling MVC infrastructure | Typically `@EnableWebMvc` or XML equivalent | Boot's MVC auto-config provides the foundation; no `@EnableWebMvc` needed |
| Controllers | `@Controller`, `@RestController`, `@RequestMapping`... | The exact same annotations/controllers |
| Component scan | Explicitly declared or imported beans | `@SpringBootApplication` provides scanning from the root package |
| Default configuration | Spring MVC baseline plus components you add | Spring MVC baseline plus many conditional Boot defaults |
| Dependencies | Manually selected/aligned libraries | Uses starters and compatible dependency version management |
| Typical packaging | WAR on external container or custom embedded setup | JAR with embedded server; WAR is still supported |
| Changing configuration | Configured directly as needed | Properties, custom beans, `WebMvcConfigurer`; or intentional takeover |
| Testing needs | Pay attention to initializers/contexts, Servlet environment, and dependencies | Boot provides test slices/auto-config, though actual behavior still needs verification |

Keep one key point in mind: "fewer lines of configuration" does not mean "the framework does less work". Boot performs much of the registration/configuration on your behalf, yet requests still flow through Spring MVC.

## 5. Three Levels of Customizing MVC When Using Spring Boot

This is crucial when a project already uses Boot and needs specific customization.

### Level 1 — Keep Boot Auto-Config, Customize via Properties

Prefer properties when Boot explicitly supports them. For example, set the listening port and context path prefix in `src/main/resources/application.yml`:

```yaml
server:
  port: 9090
  servlet:
    context-path: /demo
```

With the Boot example, the URL becomes `http://localhost:9090/demo/greet?name=Lan`. Changing the context path is a container/server configuration responsibility; the controller keeps `@GetMapping("/greet")`.

Various `spring.mvc.*` or `spring.web.*` properties can customize MVC. Property names and meanings change across Boot lines; check the reference documentation for the **exact version** in use. There is no need to recreate `DispatcherServlet` just to change port or context path.

### Level 2 — Add WebMvcConfigurer While Keeping Boot Auto-Config

When customizing MVC without replacing Boot's foundation, create a configuration class implementing `WebMvcConfigurer` **without `@EnableWebMvc`**. In the example Boot project, add `src/main/java/demo/boot/MvcExtras.java`:

```java
package demo.boot;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation
        .ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation
        .WebMvcConfigurer;

@Configuration
public class MvcExtras implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/start", "/greet");
    }
}
```

Restart and test:

```bash
curl -i 'http://localhost:8080/start'
```

A valid redirect response targets `/greet` with a 3xx status (typically 302). Try `curl -i -L ...` to follow the redirect. Using `WebMvcConfigurer` to add interceptors, formatters, view controllers, or CORS mappings is the standard way to **extend** MVC in a Boot app. For specific routes/controllers, business code still belongs in controllers/services.

Crucial point: `WebMvcConfigurer` is an **extension point**, not a signal to disable all auto-configuration. One or more configurers can contribute customizations; be careful when settings overlap or override one another.

### Level 3 — Use @EnableWebMvc to Take Full Control of MVC Configuration

If you add this to a Boot app:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class ManualMvcOwnership {
}
```

you are declaring: **I want to manage Spring MVC infrastructure configuration myself instead of using Boot's MVC auto-configuration.**

In Boot 3.x, `WebMvcAutoConfiguration` is applied conditionally when the Servlet app has the appropriate MVC classes **and no bean of type `WebMvcConfigurationSupport` exists**. `@EnableWebMvc` activates MVC configuration built on that mechanism, causing the corresponding condition to no longer match. Boot steps aside on MVC auto-config in favor of the developer's configuration.

**Consequences to distinguish precisely:**

- Core Spring MVC beans supplied by `@EnableWebMvc` can still function, so `@GetMapping` endpoints **do not necessarily disappear**.
- Certain conveniences/defaults **supplied solely by Boot's MVC auto-config** may cease to apply or require manual reconfiguration: for instance, conventional static resource serving or specific resolver/converter integrations.
- This **does not disable all Spring Boot auto-configuration**: embedded server, data sources, and other independent features can still be configured if their conditions hold.
- If taking full manual control, you are responsible for re-establishing expected behavior for converters, static resources, formatters, view resolvers, CORS, and related MVC features.

Example scenario: `/greet` still returns text, yet `/style.css` previously served by default resource handling starts returning 404 after adding `@EnableWebMvc`. Do not see 404 and immediately conclude `DispatcherServlet` is broken; check resource handlers and MVC auto-config conditions.

### 5.1. `WebMvcConfigurer` Is Not `WebMvcConfigurationSupport`

Similar names easily cause confusion:

- `WebMvcConfigurer`: **extension-point interface** that can be used in Boot to add configuration **while retaining** MVC auto-config.
- `WebMvcConfigurationSupport`: **MVC infrastructure class**; the presence of a bean of this type is the condition that causes Boot's MVC auto-config to back off in Boot 3.x.
- `@EnableWebMvc`: imports MVC configuration based on `DelegatingWebMvcConfiguration` (a subclass of `WebMvcConfigurationSupport`), so it takes ownership of MVC configuration.
- Do not subclass `WebMvcConfigurationSupport` just to add a standard interceptor or formatter. Use `WebMvcConfigurer` when the feature is supported by the extension point.

When needing to replace specific components like `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, or `ExceptionHandlerExceptionResolver`, Boot 3.x also offers extension points such as `WebMvcRegistrations`; this is an advanced scenario unnecessary for simple MVC setups.

## 6. What Does "Back Off" Actually Mean?

**Back off** means an auto-configuration **conditionally skips part or all of its default configuration** upon detecting that the application already provides a component filling the same role. It does not automatically mean Boot stops running, deletes user beans, or disables all auto-configuration.

Example illustrating the principle with custom configuration code of your own:

```java
@AutoConfiguration
@ConditionalOnClass(SmtpClient.class)
class MailExampleAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MailSender.class)
    MailSender defaultMailSender() {
        return new DefaultMailSender();
    }
}
```

This is **illustrative pseudocode for conditions**, not a standalone Java example: `SmtpClient`, `MailSender`, and `DefaultMailSender` are hypothetical types, not standard Spring APIs. If `SmtpClient` is absent from the classpath or a `MailSender` bean already exists, the default configuration method will not register the bean. The annotation syntax and principle are real; the class names in this snippet are purely for clarity.

Applying this back to Spring MVC:

```text
Auto-configuration evaluated
  │
  ├── Missing Servlet/Web MVC on classpath?    → Skip MVC auto-config
  │
  ├── Not a Servlet web application?           → Skip Servlet MVC auto-config
  │
  ├── WebMvcConfigurationSupport already exists? → WebMvcAutoConfiguration backs off
  │
  └── Matching conditions satisfied            → Register Boot's MVC defaults
```

Conditions are specific to **a given Boot version**, not fixed rules across all Spring generations. Do not deduce from the presence of any arbitrary `@Bean` that all default MVC beans will be dropped.

## 7. What Happens When a Request Arrives?

For the same `GET /greet?name=Lan` request, regardless of initialization style, the Spring MVC pipeline is similar:

1. The HTTP request reaches the Servlet container via host, port, and context path.
2. The Servlet container forwards the request to the registered `DispatcherServlet`.
3. `HandlerMapping` finds the handler matching the URL, method, and other mapping conditions.
4. `HandlerAdapter` executes the controller method, resolving arguments like `@RequestParam`.
5. The controller returns `String`; because `@RestController` is used, the value is written into the HTTP response body via the appropriate MVC mechanism.
6. The server sends status, headers, and body back to the client.

```text
                   manual WAR                Boot JAR
                  ┌────────────┐            ┌────────────┐
Browser → HTTP →  │ Tomcat WAR │            │ Embedded   │ ← HTTP ← Browser
                  │ + Servlet  │            │ Servlet    │
                  └─────┬──────┘            └──────┬─────┘
                        │                          │
                        ▼                          ▼
                  DispatcherServlet          DispatcherServlet
                        │                          │
                        └────────────┬─────────────┘
                                     ▼
                            @GetMapping("/greet")
                                     ▼
                           "Hello, Lan!"
```

Differences in deployment and default configuration do not mean one endpoint is automatically faster or slower than the other. Actual performance depends on dependencies, memory, threading, converters, business logic, I/O, and deployment configuration. Do not conclude from two setups returning the same body that bean lifecycles or middleware configurations are completely identical.

## 8. Diagnosing When "Boot Does Not Auto-Configure as Expected"

### 8.1. Using the Condition Evaluation Report

Spring Boot can display a report explaining why auto-configurations were selected or skipped when debug is enabled:

```bash
./gradlew bootRun --args='--debug'
```

Or when running the JAR:

```bash
java -jar build/libs/boot-mvc-1.0.0.jar --debug
```

The JAR name in the second command is an **example matching the demo project/version name**; if your actual file has a different name, substitute the path from `build/libs/`.

In the output, find the **CONDITIONS EVALUATION REPORT** section and entries related to `WebMvcAutoConfiguration`, `DispatcherServletAutoConfiguration`, and the web server. The report answers: which auto-configs matched, which conditions failed, and which class or bean caused a back-off. Read both positive and negative matches carefully; debug logs do not automatically fix errors.

If Spring Boot Actuator is present and appropriately configured, `/actuator/conditions` can provide similar information; this endpoint is **not publicly exposed by default** and requires access control.

### 8.2. Common Scenarios Table

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Boot app runs yet endpoint returns 404 | Controller outside scan package, wrong method/path/context path | Confirm `@SpringBootApplication` package, mapping, and context path |
| Error missing Servlet/DispatcherServlet | Missing MVC/Servlet dependency or wrong web app type | Inspect dependency graph, starters, and conditions report |
| Manual WAR returns 404 | `DispatcherServlet` unregistered, wrong WAR context path, or missing scan | Inspect Tomcat logs, `AppInitializer`, `/` mapping, and actual URL |
| Manual WAR errors on `javax.servlet.*` / `jakarta.servlet.*` | Mismatched Spring and Servlet container generations | With Spring 6, use `jakarta.*` and a compatible container |
| Static CSS/JS stops working after adding `@EnableWebMvc` | Boot MVC auto-config backed off; resource handler missing | Check conditions report; remove annotation if takeover isn't needed |
| JSON serialize/deserialize fails | Missing converter/Jackson, incompatible MIME type, or binding error | Check dependencies, `Content-Type`, and message converters |
| Added `WebMvcConfigurer` yet interceptor does not run | Config outside component scan, wrong pattern, request bypasses expected chain | Confirm bean registration and request mapping |
| Defined a bean yet Boot still configures something else | Bean type/conditions differ; config only backed off partially | Read conditions of the specific auto-configuration |
| Mistakenly assumed `@SpringBootApplication` replaces `@RestController` | Application annotation only handles bootstrap/scan/auto-config | Controllers need actual bean registration and mappings |
| Changed `server.port` yet still hitting old port | Port changed, overridden elsewhere, or app runs under a different profile | Check web server startup log and effective configuration |

### 8.3. Short Inspection Checklist

When encountering startup or routing errors, proceed in order:

1. **Dependencies:** is the right Servlet MVC stack present (`spring-webmvc`, web starter) without mixing `javax.*`/`jakarta.*` APIs?
2. **Bootstrap:** did the container start? Were `SpringApplication.run`/initializers invoked and `DispatcherServlet` registered?
3. **Context:** was the controller bean created in the proper application context?
4. **Mapping:** do the actual method, URL, context path, and servlet mapping match the request?
5. **MVC configuration:** does the app have `@EnableWebMvc`/`WebMvcConfigurationSupport` causing back-off? Is `WebMvcConfigurer` registered properly?
6. **Converter/resource/error behavior:** an endpoint running yet failing on JSON, static files, or views is a different issue from a missing Servlet.
7. **Condition report:** use runtime data to see what actually matched instead of guessing from annotations.

## 9. Choosing the Configuration Style Based on Needs

**Use manual Spring MVC** when you need to integrate the framework into an existing Servlet environment, tightly control lifecycles and bean graphs, or learn/maintain a non-Boot Spring MVC application. You must understand containers, Servlet registration, dependencies, context hierarchies, and MVC components thoroughly.

**Use Spring Boot MVC** when you want consistent web startup, manageable dependencies, and conditional default configurations. This is usually the convenient path for new services, though you still need to understand the underlying mechanics to debug effectively.

**In an existing Boot application**, choose the smallest appropriate level of change: properties for built-in settings; `WebMvcConfigurer` for common MVC customizations; `@EnableWebMvc` only when you genuinely want responsibility for managing most MVC configuration yourself. Custom `@Bean` definitions may cause only specific parts of auto-config to back off; check exact conditions.

## 10. Common Pitfalls and Self-Check Questions

**Pitfall 1:** "`@EnableWebMvc` is a mandatory annotation in every Spring Boot web app." In reality, Boot MVC auto-config typically covers that need; adding `@EnableWebMvc` can disable MVC configuration provided by Boot.

**Pitfall 2:** "Spring Boot auto-configures everything so there is no `DispatcherServlet`." Spring MVC in Boot still uses `DispatcherServlet`; Boot merely handles registering and configuring much of it.

**Pitfall 3:** "Having `@RestController` makes the endpoint work automatically." The class must be registered as a bean, have MVC infrastructure, and have the Servlet container route requests to it.

**Pitfall 4:** "`WebMvcConfigurer` disables auto-config." `WebMvcConfigurer` is an additive extension mechanism; `@EnableWebMvc` or MVC-owning infrastructure beans are what require special attention.

**Pitfall 5:** "Plain Spring MVC must use XML and an external server; Boot can only produce executable JARs." Both Java config/initializers and `web.xml` are valid. Spring MVC can be wired to an embedded server manually; Boot also supports WARs when configured properly.

**Pitfall 6:** "Auto-config always overrides user-declared beans." Many auto-configurations check for existing beans conditionally, yet not every case is identical. Precedence depends on the source/conditions of the specific configuration.

Self-check:

1. Why does `@EnableWebMvc` not automatically open port 8080? Which component actually accepts HTTP connections?
2. In the manual WAR example, which class registers `DispatcherServlet` and which class activates MVC infrastructure?
3. In the Boot example, what are the three main behaviors of `@SpringBootApplication`? Which condition determines whether MVC auto-config is applied?
4. How do the two `/greet` endpoints share identical controller logic yet differ in context path when running as a WAR versus a Boot JAR?
5. If you only want to add the redirect `/start → /greet`, why is `WebMvcConfigurer` more suitable than taking over with `@EnableWebMvc`?
6. If a static file stops working after adding `@EnableWebMvc`, describe the likely cause and how to prove it using the conditions report.
7. Explain the differences between `@ConditionalOnMissingBean`, `WebMvcConfigurer`, `WebMvcConfigurationSupport`, and the **back off** concept.
8. If you remove the web starter and keep only basic Spring libraries, why shouldn't you assume Boot will still create `DispatcherServlet` and a web server?

**Mastery criteria:** you are ready when you can diagram the startup flow of both approaches, run both endpoints, point out exactly where `DispatcherServlet` is registered, choose between properties/`WebMvcConfigurer`/`@EnableWebMvc` by requirement, and use the condition report to verify a configuration hypothesis.

### Technical Documentation to Cross-Check Against Your Version

- Spring Framework — DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework — Enable MVC Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html
- Spring Boot 3.5 — Servlet Web Applications / Spring MVC Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
