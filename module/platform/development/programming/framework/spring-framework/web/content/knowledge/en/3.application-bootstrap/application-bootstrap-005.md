# @EnableWebMvc, WebMvcConfigurer, and Equivalent XML Configuration in Spring MVC

When reading a Spring Web project, you may encounter three configuration styles: **Java config with @EnableWebMvc**, **WebMvcConfigurer callbacks**, or **XML with mvc:annotation-driven and other mvc elements**. They all address Spring MVC configuration, yet **they do not play the same role**. In particular, in a **Spring Boot** application, adding @EnableWebMvc is not mandatory and often disables part of the MVC conveniences Boot configures automatically.

This lesson distinguishes each component, shows where configuration sits during Servlet startup, provides a runnable Java example, maps Java and XML feature by feature, and explains how to choose the right configuration with or without Spring Boot.

## 1. The Big Picture

Spring MVC is a web framework on the **Servlet stack**. For an application to receive HTTP requests and invoke controllers, it needs a **Servlet accepting requests**, an **ApplicationContext holding MVC infrastructure**, and **controllers/handlers**.

~~~text
HTTP client
    |
Servlet container: Tomcat / Jetty ...
    |
Servlet mapping and filter chain
    |
DispatcherServlet  <-- registered via Boot, initializer, or web.xml
    |
Servlet's Spring WebApplicationContext
    |
    +-- HandlerMapping: finds @GetMapping, @PostMapping...
    +-- HandlerAdapter: invokes controller, binds parameters
    +-- HandlerExceptionResolver: handles exceptions
    +-- HttpMessageConverter: reads/writes JSON, text, ...
    +-- ViewResolver / resource handler / interceptor / CORS...
    |
Controller -> Service -> response
~~~

Three roles to remember:

1. **@EnableWebMvc:** enables **Java-based Spring MVC infrastructure configuration** in the ApplicationContext; it sits on the web stack configuration side and does not directly start an HTTP server or register DispatcherServlet.
2. **WebMvcConfigurer:** callback interface to **customize MVC configuration**, such as interceptors, formatters, static resources, CORS, view controllers, and path matching. Can be used alongside @EnableWebMvc when managing MVC manually, or standalone in Spring Boot while preserving auto-configuration.
3. **XML mvc namespace:** expresses many functionally equivalent settings in XML. The **mvc:annotation-driven** element enables most of the core infrastructure similarly to @EnableWebMvc; **mvc:interceptors**, **mvc:resources**, **mvc:cors**, etc. correspond to Java config callbacks.

**Separate two questions:** Who registers and serves **DispatcherServlet**? Who creates/customizes the **MVC beans** that the servlet uses? Focusing on the second question clarifies @EnableWebMvc and WebMvcConfigurer.

## 2. Quick Identification Table

| Component | Primary Effect | When Appropriate | Common Misconception |
|---|---|---|---|
| **@EnableWebMvc** | Imports foundational MVC configuration into the Spring context | Plain Spring MVC to enable framework infrastructure; Boot only when intentionally taking full MVC control | Not a required annotation for every Boot app |
| **WebMvcConfigurer** | Allows adding/adjusting MVC settings via callback methods | Boot when adding MVC settings while keeping Boot defaults; or with @EnableWebMvc in plain MVC | Implementing the interface alone does not enable DispatcherServlet or start a server |
| **mvc:annotation-driven** | Enables MVC annotation support and related beans via XML | Spring MVC apps using XML configuration | Does not register a servlet in web.xml |
| **mvc:interceptors** | Declares MVC interceptors | Spring MVC XML | Does not replace Servlet Filters or Spring Security |
| **mvc:resources** | Maps URLs to static resource locations | Spring MVC XML | Does not automatically point to all Boot directories and resources |
| **mvc:cors** | Configures CORS by URL pattern | Spring MVC XML | CORS is not authentication/authorization |
| **mvc:view-controller** | Routes to a view or redirect/forward without a controller method | Spring MVC XML | Not for complex API business logic |
| **Spring Boot MVC auto-configuration** | Preconfigures most of MVC plus Boot-specific integrations | Boot apps using Spring Web | Affected when enabling @EnableWebMvc or declaring low-level custom MVC infrastructure |

## 3. What Does @EnableWebMvc Actually Do?

A basic Java configuration in **plain Spring Framework MVC without Boot**:

~~~java
package example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class WebConfig {
}
~~~

**Meaning of each annotation:**

- **@Configuration:** registers the class as a source of Spring bean definitions.
- **@EnableWebMvc:** activates Java-based MVC configuration by importing **DelegatingWebMvcConfiguration**. This configuration registers many components required for @RequestMapping-based controllers to work.
- This is **illustrative configuration code, not a standalone runnable HTTP app**. Handling requests requires a servlet container, a registered DispatcherServlet, and controllers inside the appropriate context.

DelegatingWebMvcConfiguration is a configuration class based on **WebMvcConfigurationSupport**, and it also collects registered **WebMvcConfigurer** beans and invokes the appropriate callbacks. Default MVC components are set up according to classpath libraries and actual configuration; for instance, an appropriate JSON library is needed to convert objects to JSON.

### Things @EnableWebMvc Does Not Do

- Does not start Tomcat or open any HTTP port.
- Does not replace **DispatcherServlet registration**.
- Does not automatically scan controllers across all packages.
- Does not download Jackson, JSP, Thymeleaf, or other dependencies from Maven.
- Does not mean "the app is now running Spring Boot".
- Does not apply to **Spring WebFlux**; WebFlux has a different configuration model.

### Why Does Spring Boot Usually Not Need @EnableWebMvc?

Spring Boot brings in **WebMvcAutoConfiguration** when web stack/classpath conditions are met. It automatically provides MVC configuration alongside conveniences such as resource handling, view resolvers, converter/formatter integration, and support for the corresponding properties.

If you add **@EnableWebMvc** to a Boot MVC project, you switch to **full Spring Framework-managed MVC configuration**; most of Boot's specialized MVC auto-configuration **is no longer applied as before**. Controllers may still work, making issues harder to notice; however, defaults such as static resource serving, JSON behavior, and property-based customizations can change and require manual reconfiguration.

**Practical rule:** In Spring Boot, if you only need to add CORS, an interceptor, a formatter, a resource mapping, or a view controller, use **@Configuration implements WebMvcConfigurer** and **do not add @EnableWebMvc**.

## 4. WebMvcConfigurer: Selective Customization Mechanism

**WebMvcConfigurer** is an interface containing default methods, so an implementing class only overrides what it needs.

~~~java
package example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {
    // Override only the MVC callbacks you need.
}
~~~

In the snippet above, the class must still be **registered in the Spring ApplicationContext**. @Configuration combined with component scanning or explicit import is standard. If Spring does not detect the class, the callbacks will not run. Simply having a class "implements WebMvcConfigurer" without being a bean has no effect.

### Important Callbacks

| Java Callback | Function | Functional XML Equivalent |
|---|---|---|
| **addInterceptors** | Registers HandlerInterceptors for URL patterns | mvc:interceptors |
| **addResourceHandlers** | Maps URLs to static resource locations and caching | mvc:resources |
| **addCorsMappings** | Path-based CORS policy | mvc:cors |
| **addViewControllers** | Direct URL-to-view or redirect mapping | mvc:view-controller |
| **addFormatters** | Registers Converters/Formatters for MVC binding | mvc:annotation-driven with conversion-service and converter beans |
| **configureContentNegotiation** | Adjusts how requested media types are resolved | Corresponding content-negotiation attributes/elements depending on schema/version |
| **configureViewResolvers** | Configures ViewResolvers | ViewResolver beans or mvc:view-resolvers element depending on version |
| **configureMessageConverters / extendMessageConverters** | Controls reading/writing HTTP bodies | mvc:annotation-driven with message-converters |
| **configurePathMatch** | Customizes how MVC matches paths | Some XML/schema options may differ; not always a 1:1 mapping |
| **addArgumentResolvers** | Adds custom controller parameter resolvers | mvc:annotation-driven/argument-resolvers depending on schema |
| **addReturnValueHandlers** | Adds handlers for return value types | Advanced configuration; not always a direct single XML element |

**This is a table of functional intent equivalents**, not a promise that Java callbacks and XML elements share identical attribute sets or execution timing across every Spring version.

### Callbacks Take Effect Only Within MVC Infrastructure

When @EnableWebMvc is present, **DelegatingWebMvcConfiguration** discovers WebMvcConfigurer beans. In Spring Boot MVC, auto-configuration likewise integrates WebMvcConfigurer beans to collect additions. Implementing the interface without actual MVC infrastructure provides no web handlers/services to consume the settings.

**Multiple WebMvcConfigurer beans can exist.** Contributions are generally combined by Spring, yet if two beans modify an order- or priority-sensitive setting, check ordering and conflicts. Do not split configuration haphazardly while assuming the outcome is always identical.

## 5. Complete Spring Boot MVC Example: Customizing While Keeping Boot Defaults

This is a **runnable** example with Java 17+, Maven, and a Spring Boot application having the **Spring Web** dependency. Generate an **MVC** project from Spring Initializr choosing Java, Maven, and Spring Web. With Boot 3.x, the common starter is **spring-boot-starter-web**; with Boot 4.x, the MVC starter is **spring-boot-starter-webmvc**. Let Initializr generate the pom.xml matching your chosen version.

Use package **example.demo** for all Java files (or rename packages consistently to match your project), ensuring the @SpringBootApplication class sits in the root package covering controllers/config. The example requires no database, template engine, or Spring Security.

Structure:

~~~text
src/main/
  java/example/demo/
    DemoApplication.java
    DemoController.java
    MarkerInterceptor.java
    WebConfig.java
  resources/
    manual/
      hello.txt
~~~

### 5.1. Application Entry Point

**src/main/java/example/demo/DemoApplication.java**

~~~java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**Explanation:** SpringApplication creates the ApplicationContext, Boot activates auto-configurations matching the MVC dependencies, and registers the embedded HTTP server. No @EnableWebMvc is needed here.

### 5.2. Controller to Observe Behavior

**src/main/java/example/demo/DemoController.java**

~~~java
package example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/greet")
    public Message greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return new Message("Hello " + name);
    }

    public record Message(String message) {
    }
}
~~~

**Explanation:** @RestController combines @Controller and @ResponseBody, and the Message record is written as JSON by Spring/Jackson. This is an **HTTP controller**, not an MVC configuration method.

### 5.3. Interceptor with Observable Behavior

**src/main/java/example/demo/MarkerInterceptor.java**

~~~java
package example.demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

public class MarkerInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) {
        response.setHeader("X-Mvc-Config", "applied");
        return true;
    }
}
~~~

**Explanation:** preHandle returns **true** so the request proceeds to the handler. The X-Mvc-Config header merely proves the interceptor ran; in real applications, replace it with timing, correlation/tracing, or appropriate cross-cutting logic. **Do not use MVC interceptors as your primary authorization barrier**; consider Spring Security/the Servlet filter chain.

### 5.4. WebMvcConfigurer Adding Four Configuration Types

**src/main/java/example/demo/WebConfig.java**

~~~java
package example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MarkerInterceptor())
                .addPathPatterns("/api/**");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/docs/**")
                .addResourceLocations("classpath:/manual/");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET")
                .allowedHeaders("Accept", "Content-Type");
    }

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController(
                "/welcome", "/api/greet");
    }
}
~~~

**Explanation by callback:**

- **addInterceptors:** only /api/** URLs pass through MarkerInterceptor; /docs/hello.txt does not receive the X-Mvc-Config header because the pattern does not match.
- **addResourceHandlers:** URI /docs/hello.txt reads **classpath:/manual/hello.txt**; URL mapping and resource location are two distinct concepts.
- **addCorsMappings:** only allows browser origin **http://localhost:5173** to access /api/** with the specified methods. Credentials are not enabled in this example.
- **addViewControllers:** /welcome returns a redirect to /api/greet without writing a dedicated controller method.
- **No @EnableWebMvc.** Boot remains the owner of MVC auto-configuration in the sample app.

### 5.5. Resource for Testing File Serving

**src/main/resources/manual/hello.txt** contains verbatim:

~~~text
Static resource from WebMvcConfigurer
~~~

### 5.6. Starting and Verifying

In the Spring Initializr project root (containing pom.xml and the Maven wrapper), run:

~~~bash
# macOS / Linux
./mvnw spring-boot:run
~~~

On Windows, use the corresponding command:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

In another terminal, call:

~~~bash
curl -i "http://localhost:8080/api/greet?name=An"
~~~

Expected response has status 200, header **X-Mvc-Config: applied**, and JSON body:

~~~json
{"message":"Hello An"}
~~~

Some other HTTP response headers and their order may differ by server/Boot version.

Test the static resource:

~~~bash
curl -i "http://localhost:8080/docs/hello.txt"
~~~

Expected body:

~~~text
Static resource from WebMvcConfigurer
~~~

Test the redirect:

~~~bash
curl -i "http://localhost:8080/welcome"
~~~

Expected status is in the **3xx** range, specifically **302** under default redirect configuration, with Location pointing to /api/greet (which the server may render as an absolute URL). Add **-L** for curl to follow the redirect if you want to see the final JSON.

Test CORS from an allowed origin:

~~~bash
curl -i \
  -H "Origin: http://localhost:5173" \
  "http://localhost:8080/api/greet"
~~~

Expect the response to include **Access-Control-Allow-Origin: http://localhost:5173**. For disallowed origins, browsers are not granted permission to read cross-origin responses under this policy. **curl does not enforce browser CORS policies**, so curl can still display the response when invoked directly; do not use curl's ability to send a request as proof that CORS allows a browser.

This runnable sample proves that a WebMvcConfigurer can add an interceptor, static mapping, CORS, and a redirect in a Boot MVC app **without taking over full MVC setup**.

## 6. Plain Spring MVC with Java Config: Needs @EnableWebMvc and Servlet Bootstrap

For **Spring Framework MVC without Spring Boot**, you typically need to enable MVC infrastructure and register DispatcherServlet with the servlet container.

Example Java config:

~~~java
package example.plainmvc;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@ComponentScan("example.plainmvc")
public class WebConfig implements WebMvcConfigurer {
    // Can override addInterceptors(), addResourceHandlers()...
}
~~~

**This is configuration for a separate Servlet app, not a replacement for the Boot app's WebConfig in the previous section.** @ComponentScan discovers controllers/services in the specified package. @EnableWebMvc enables MVC infrastructure and aggregates WebMvcConfigurer beans.

DispatcherServlet can be registered via a Java initializer:

~~~java
package example.plainmvc;

import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

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
~~~

**Environment dependencies:** the app must be packaged as a servlet web app, providing **spring-webmvc**, required dependencies, and a container supporting the Jakarta Servlet version compatible with your Spring generation. With Spring Framework 6, use **jakarta.servlet.***, not legacy **javax.servlet.***. This is a realistic bootstrap skeleton, yet **not a complete standalone WAR project**: build configuration, controllers, and container deployment are still needed. Do not run directly with javac/java without the dependency classpath and servlet runtime.

### Role of the Initializer

- **getRootConfigClasses():** configures the root context (if needed). The example returns null to focus on a single web context.
- **getServletConfigClasses():** configures **DispatcherServlet's WebApplicationContext**, containing MVC beans/controllers.
- **getServletMappings():** maps the servlet to "/", serving controllers by URL.
- The container detects WebApplicationInitializer via the corresponding Servlet startup mechanism and registers DispatcherServlet.

**Context placement matters greatly:** MVC infrastructure and controllers usually belong in DispatcherServlet's context. The root ApplicationContext can hold shared services/repositories; beans in the child context see parent beans, whereas the parent does not automatically see child beans. Placing @EnableWebMvc in the wrong context can prevent DispatcherServlet from seeing expected infrastructure or create two confusing configurations.

## 7. Equivalent XML Configuration: mvc:annotation-driven and web.xml

In XML-based Spring MVC applications, the counterpart to @EnableWebMvc for enabling annotation MVC is:

~~~xml
<mvc:annotation-driven/>
~~~

For the XML to be meaningful and loadable, it needs the beans, mvc, and context namespaces along with **DispatcherServlet** configuration. The **WEB-INF/spring-mvc.xml** example below shows complete MVC XML configuration; controllers and the interceptor class are assumed to exist on the Servlet project's classpath.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:mvc="http://www.springframework.org/schema/mvc"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/mvc
           https://www.springframework.org/schema/mvc/spring-mvc.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <!-- Discover @Controller, @Service, and @Component. -->
    <context:component-scan base-package="example.plainmvc"/>

    <!-- Enable MVC annotation infrastructure. -->
    <mvc:annotation-driven/>

    <!-- Equivalent to addInterceptors(...). -->
    <mvc:interceptors>
        <mvc:interceptor>
            <mvc:mapping path="/api/**"/>
            <bean class="example.plainmvc.MarkerInterceptor"/>
        </mvc:interceptor>
    </mvc:interceptors>

    <!-- Equivalent to addResourceHandlers(...). -->
    <mvc:resources mapping="/docs/**"
                   location="classpath:/manual/"/>

    <!-- Equivalent to addViewControllers(...). -->
    <mvc:view-controller path="/welcome"
                         view-name="redirect:/api/greet"/>

    <!-- Equivalent to addCorsMappings(...). -->
    <mvc:cors>
        <mvc:mapping path="/api/**"
                     allowed-origins="http://localhost:5173"
                     allowed-methods="GET"
                     allowed-headers="Accept, Content-Type"/>
    </mvc:cors>
</beans>
~~~

Classes such as **example.plainmvc.MarkerInterceptor** and the controllers must be created in the XML project; do not copy package **example.demo** verbatim from the Boot project in section 5 while ignoring package differences. For example, you can write MarkerInterceptor with the same code as in the Boot example and change its package to **example.plainmvc**. This XML is a **configuration reference**, not a standalone runnable app without the Java classes and container.

Without a Java initializer, a Servlet app can declare the servlet via **WEB-INF/web.xml**. Sample web.xml for Servlet 6.0/Jakarta API:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             https://jakarta.ee/xml/ns/jakartaee
             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <servlet>
        <servlet-name>dispatcher</servlet-name>
        <servlet-class>
            org.springframework.web.servlet.DispatcherServlet
        </servlet-class>
        <init-param>
            <param-name>contextConfigLocation</param-name>
            <param-value>/WEB-INF/spring-mvc.xml</param-value>
        </init-param>
        <load-on-startup>1</load-on-startup>
    </servlet>

    <servlet-mapping>
        <servlet-name>dispatcher</servlet-name>
        <url-pattern>/</url-pattern>
    </servlet-mapping>
</web-app>
~~~

**Explanation:**

- The Servlet container creates **DispatcherServlet** for the "/" mapping.
- DispatcherServlet reads contextConfigLocation and initializes its **WebApplicationContext** from spring-mvc.xml.
- The **mvc:annotation-driven** element enables beans needed for @RequestMapping, @RequestBody, @ResponseBody, and appropriate converters/validation.
- **context:component-scan** locates controllers and Java beans.
- XML-configured interceptors/resources/CORS/view-controllers apply within that MVC context.

If using **AbstractAnnotationConfigDispatcherServletInitializer** (Java), do not simultaneously configure **the same DispatcherServlet** again via web.xml; unintentionally configuring both can cause duplicate servlets/contexts, colliding mappings, or startup failure.

## 8. Direct Behavioral Comparison Between Java Config and XML

### 8.1. Enabling Annotation-Based MVC

Java:

~~~java
@Configuration
@EnableWebMvc
public class WebConfig {
}
~~~

XML:

~~~xml
<mvc:annotation-driven/>
~~~

Both enable foundational MVC components in a plain Spring MVC context. **However**, @Configuration/@EnableWebMvc by themselves do not declare component scanning; neither does XML mvc:annotation-driven. To discover controllers, you must use @ComponentScan, context:component-scan, or another bean registration mechanism.

### 8.2. Registering Interceptors

Java, inside a WebMvcConfigurer class:

~~~java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(new MarkerInterceptor())
            .addPathPatterns("/api/**");
}
~~~

XML:

~~~xml
<mvc:interceptors>
    <mvc:interceptor>
        <mvc:mapping path="/api/**"/>
        <bean class="example.plainmvc.MarkerInterceptor"/>
    </mvc:interceptor>
</mvc:interceptors>
~~~

The two snippets are **goal-equivalent** when the interceptor class has the same logic. Yet there is a technical difference: XML mvc:interceptors declares **MappedInterceptor** beans that can be discovered by other HandlerMappings in the context, whereas the Java callback registers through HandlerMappings managed by MVC Java config. When integrating extra frameworks, check the scope of application rather than assuming identical behavior.

**Do not confuse HandlerInterceptor with Servlet Filter**: Filters run in the servlet container's filter chain and can cover URLs before DispatcherServlet; HandlerInterceptors attach to MVC handlers after HandlerMapping. Authorization security should be delegated to an appropriate layer, usually Spring Security/the filter chain.

### 8.3. Serving Static Resources

Java:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/docs/**")
            .addResourceLocations("classpath:/manual/");
}
~~~

XML:

~~~xml
<mvc:resources mapping="/docs/**"
               location="classpath:/manual/"/>
~~~

If the file sits at **src/main/resources/manual/hello.txt**, a request to **/docs/hello.txt** returns that file once resources are packaged on the classpath. Do not confuse the **URL path** /docs with the **resource location** classpath:/manual/.

Spring Boot MVC has its own default resource locations and welcome page support. Adding @EnableWebMvc can alter static content serving behavior; in Boot, prefer **WebMvcConfigurer** or the corresponding Boot properties when only adjustments are needed.

### 8.4. Global CORS for MVC

Java:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("http://localhost:5173")
            .allowedMethods("GET")
            .allowedHeaders("Accept", "Content-Type");
}
~~~

XML:

~~~xml
<mvc:cors>
    <mvc:mapping path="/api/**"
                 allowed-origins="http://localhost:5173"
                 allowed-methods="GET"
                 allowed-headers="Accept, Content-Type"/>
</mvc:cors>
~~~

If a browser calls from another origin, the CORS policy may cause the browser to block reading the response or reject preflight requests. CORS must not be used to authenticate users. If using cookies or credentials, configure specific trusted origins, credentials, and CSRF/authorization protection properly; do not combine credentials with a wildcard `"*"` origin casually.

### 8.5. View Controller/Redirect

Java:

~~~java
@Override
public void addViewControllers(ViewControllerRegistry registry) {
    registry.addRedirectViewController(
            "/welcome", "/api/greet");
}
~~~

XML with similar intent:

~~~xml
<mvc:view-controller path="/welcome"
                     view-name="redirect:/api/greet"/>
~~~

Both let `/welcome` return a redirect without writing a business controller. Do not define an annotated controller and a view-controller competing for ownership of the same route, as mapping precedence and error statuses may not behave as expected.

### 8.6. Formatter/Converter and Validation

Java:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(String.class, Code.class,
            value -> new Code(value.trim()));
}
~~~

This is an **illustrative method** inside WebMvcConfigurer that requires a defined **Code** type and the appropriate FormatterRegistry import, not a standalone Java snippet. To run it yourself, you can declare:

~~~java
public record Code(String value) {
}
~~~

When a controller method accepts @RequestParam Code, the formatter/converter converts the parameter text into a Code object. This is **conversion during HTTP parameter binding**, distinct from JSON deserialization for @RequestBody.

XML uses a custom conversion service wired to annotation-driven:

~~~xml
<mvc:annotation-driven conversion-service="conversionService"/>

<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="example.plainmvc.StringToCodeConverter"/>
        </set>
    </property>
</bean>
~~~

**Additional requirement:** StringToCodeConverter must implement Spring Converter<String, Code> with a suitable constructor; the XML above is an integration snippet, insufficient to run on its own. Validator configuration can be declared with the validator attribute of mvc:annotation-driven depending on schema; Bean Validation support also depends on provider/dependencies and configuration.

### 8.7. HTTP Message Converters and Content Negotiation

In **Spring Framework 6.x** Java config, the method:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Add to or refine the already configured converter list.
}
~~~

is an adjustment hook. **configureMessageConverters(List...)** has different semantics: providing converters yourself there can suppress default registrations in plain Spring Framework unless you re-add them explicitly.

In XML, message converters can be configured inside **mvc:annotation-driven**:

~~~xml
<mvc:annotation-driven>
    <mvc:message-converters register-defaults="true">
        <!-- Custom converter beans can be added here. -->
    </mvc:message-converters>
</mvc:annotation-driven>
~~~

This is an **illustrative configuration snippet**, not mandatory. Only create converter beans when genuinely needed. In Boot, Boot's **HttpMessageConverters** mechanism and converter bean registration are usually more suitable than replacing the entire list manually.

**Version note:** the message converter configuration API is changing between Spring Framework 6.x and 7.x; in Spring 7, hooks accepting **List<HttpMessageConverter<?>>** have been deprecated in favor of a builder-based API. When upgrading, read the Javadoc for your exact version rather than copying 6.x examples verbatim.

The MVC XML namespace remains a way to read/maintain many legacy codebases, yet **starting with Spring Framework 7.0, XML MVC namespace support has been marked deprecated**; Spring documentation also notes that XML config is no longer updated to keep pace with every new Java config option. For new projects, prefer Java config; when maintaining XML, consider a tested, incremental migration path.

## 9. Why Can @EnableWebMvc Cause Failures in Spring Boot?

Suppose you start with a Boot MVC app having the resource:

~~~text
src/main/resources/static/css/site.css
~~~

With Boot's auto-configuration, the URL **/css/site.css** is normally served by default resource mappings. Later a developer adds:

~~~java
@Configuration
@EnableWebMvc
public class CustomWebConfig implements WebMvcConfigurer {
    // Only wanted to register an interceptor.
}
~~~

The application may **still start** and JSON controllers may still run, yet parts of the MVC configuration provided by Boot (including static resource mapping or related customizations) may **stop working as before**. Therefore, do not treat enabling @EnableWebMvc as "enabling a small helper".

### How to Fix When You Only Want to Add an Interceptor

~~~java
@Configuration
public class CustomWebConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MarkerInterceptor());
    }
}
~~~

This is **illustrative code** requiring imports and MarkerInterceptor as in section 5. The core change is **removing @EnableWebMvc**, keeping Boot's MVC auto-configuration and applying callbacks.

**Is @EnableWebMvc always a mistake?** No. When a Boot app has special requirements and the team **intentionally wants to manage all of Spring MVC themselves**, @EnableWebMvc can be used, provided they understand what Boot no longer supplies automatically and re-declare/test everything needed.

### Extending WebMvcConfigurationSupport Is Also Full Control

~~~java
@Configuration
public class FullControlMvcConfig
        extends WebMvcConfigurationSupport {
    // Allows overriding low-level infrastructure hooks and beans.
}
~~~

This is an **incomplete illustrative snippet**. Having a WebMvcConfigurationSupport bean can prevent Boot's MVC auto-configuration conditions from matching. Do not use this approach merely to add CORS or a formatter.

If you need deep customization of **RequestMappingHandlerMapping**, **RequestMappingHandlerAdapter**, or **ExceptionHandlerExceptionResolver** while keeping Boot's MVC customizations, look into Spring Boot's **WebMvcRegistrations** mechanism. This is an advanced path requiring full testing across the exact framework/Boot combination.

## 10. Comparing Configuration Paths in Boot and Plain Spring MVC

~~~text
A. Spring Boot + Spring MVC
@SpringBootApplication
      |
SpringApplication + AutoConfiguration
      |
WebMvcAutoConfiguration, DispatcherServletAutoConfiguration
      |
WebMvcConfigurer beans add callbacks (NO @EnableWebMvc)
      |
DispatcherServlet -> HandlerMapping / Adapter / Converter...
      |
Controller

B. Plain Spring Framework MVC — Java
Servlet container
      |
WebApplicationInitializer registers DispatcherServlet
      |
@Configuration + @EnableWebMvc
      |
DelegatingWebMvcConfiguration collects WebMvcConfigurer beans
      |
MVC infrastructure -> Controller

C. Plain Spring Framework MVC — XML
Servlet container
      |
web.xml registers DispatcherServlet and XML config location
      |
spring-mvc.xml:
  context:component-scan
  mvc:annotation-driven
  mvc:interceptors / resources / cors / view-controller...
      |
MVC infrastructure -> Controller
~~~

**A** is the modern path with minimal manual wiring. **B/C** show the parts Boot supplies or replaces via auto-configuration. When debugging, determine which branch the project uses before editing annotations/XML.

## 11. Testing Configuration Instead of Guessing Effectiveness

### HTTP Checks for the Boot Example

After starting the sample app from section 5:

1. GET **/api/greet?name=An** should return the greeting JSON and header **X-Mvc-Config: applied**.
2. GET **/docs/hello.txt** should return the file contents from the classpath.
3. GET **/welcome** should redirect to **/api/greet**.
4. A request with **Origin: http://localhost:5173** to /api/greet should receive the corresponding CORS header.
5. Other origins should not automatically be permitted cross-origin access in browsers.
6. Verify behavior after changing/fixing configuration; do not test while keeping multiple overlapping configuration layers with duplicate responsibilities.

### Writing Automated Tests

With Spring Boot 3.x using **spring-boot-starter-test**, endpoints can be verified using **@SpringBootTest + @AutoConfigureMockMvc** or appropriate test slices. MVC tests have two levels of meaning:

- **Slice test @WebMvcTest:** focuses on controllers and a subset of MVC infrastructure; does not guarantee loading every custom configuration bean across the app. If a test needs a specific WebMvcConfigurer/interceptor, explicitly import/configure it in the slice.
- **Full-context test @SpringBootTest:** suitable for verifying integration of auto-configuration, converters, handler mappings, and MVC config. When combining with MockMvc, include the appropriate annotations/configuration.

An illustrative automated test for the Boot app in section 5:

~~~java
package example.demo;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MvcConfigTest {

    @Autowired
    MockMvc mvc;

    @Test
    void interceptorAndControllerAreConfigured() throws Exception {
        mvc.perform(get("/api/greet").param("name", "An"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Mvc-Config", "applied"))
                .andExpect(jsonPath("$.message")
                        .value("Hello An"));
    }
}
~~~

This is a **standalone test class inside the example Boot 3.x project**, placed at **src/test/java/example/demo/MvcConfigTest.java**, requiring Spring Boot Test and JUnit/Jackson/JsonPath via the test starter. With Boot 4.x, test auto-configuration packages may differ; create tests using the dependencies and imports matching your version. To run:

~~~bash
# macOS / Linux
./mvnw test
~~~

On Windows:

~~~powershell
.\mvnw.cmd test
~~~

**Expectation:** tests pass if the project declares the right dependencies, package scanning, and example files. Do not record specific test run logs without actually executing in that environment.

### Debugging When Configuration Has No Effect

- Check whether **WebConfig is actually a bean**: package, component scan, @Import, or XML registration.
- Check whether the app is **Servlet MVC or WebFlux**: WebMvcConfigurer does not configure WebFlux; the reactive stack has **WebFluxConfigurer**.
- Check whether **@EnableWebMvc** or extending **WebMvcConfigurationSupport** was accidentally added in Boot.
- Read the **auto-configuration condition report** (Boot can display it via startup debug/Actuator conditions depending on setup) to verify whether WebMvcAutoConfiguration ran.
- Check servlet **context path, servlet mapping, and handler patterns** before concluding addInterceptors/addResourceHandlers did not work.
- If using XML, verify the XML is actually loaded by **DispatcherServlet's context**, namespaces/schemas are valid, and referenced classes are on the classpath.
- With multiple DispatcherServlets or ApplicationContexts, determine which context owns the controllers and configs.
- Check conflicts between **@CrossOrigin and global CORS**, multiple converters, view resolvers, or static URL patterns.
- Inspect startup errors and detailed exceptions before changing framework versions.
- Do not use interceptors for access control enforcement; when security filters process requests before MVC, responses may be produced before the interceptor runs.

## 12. Notes When Migrating XML to Java Config

Migrating configuration requires **comparing behavior**, not just replacing syntax:

1. Identify servlet mappings, WebApplicationContext, root context, and where XML is loaded.
2. List features in XML: annotation-driven, scanning, interceptors, formatters, validation, converters, view resolvers, resources, CORS, redirects, and advanced settings.
3. For **plain Spring MVC** apps, translate mvc:annotation-driven to **@EnableWebMvc**, and extra elements to WebMvcConfigurer or corresponding beans; DispatcherServlet still needs bootstrapping.
4. For **Spring Boot** apps, leverage MVC auto-configuration first; move needed customizations to **WebMvcConfigurer without @EnableWebMvc**, rather than copying annotations mechanically from plain configs.
5. If XML has custom message converters, mapping rules, or handler adapters, compare defaults and test JSON/XML requests, validation, and error cases after migration.
6. Compare security/filter order, CORS preflight, static resources, cache headers, redirect URLs, and view rendering.
7. XML and Java config can coexist **simultaneously**, yet avoid duplicate registration of servlets, component scans, handler mappings, and converters/interceptors because results depend on ownership and precedence.
8. Keep versions consistent: Spring 5/javax.servlet and Spring 6+/jakarta.servlet are different API generations; upgrade alongside compatible libraries/containers.

Example configuration checklist table:

| Before (XML) | After (Java/Boot) | Tests to Keep |
|---|---|---|
| mvc:annotation-driven | @EnableWebMvc (plain); Boot MVC auto-config | Annotated controllers, binding, JSON |
| context:component-scan | @ComponentScan or @SpringBootApplication scan | Controllers/services registered |
| mvc:interceptors | addInterceptors | Headers/logging and include/exclude URLs |
| mvc:resources | addResourceHandlers or Boot static mapping | Files return on GET, right content type/cache |
| mvc:view-controller | addViewControllers | Redirect/forward and status |
| mvc:cors | addCorsMappings / @CrossOrigin | Allowed Origin, preflight, and credentials |
| conversion-service | addFormatters / Converter beans | Query/form binding and validation |
| ViewResolver beans | configureViewResolvers / Boot view integration | HTML views render |
| Custom HttpMessageConverters | Custom converters/Boot HttpMessageConverters | JSON/XML, Accept, error bodies |

## 13. Common Misconceptions and Errors

**"@EnableWebMvc enables all web features in Spring Boot."** False. Boot MVC usually already enables those features; @EnableWebMvc can discard Boot's automatic customizations.

**"WebMvcConfigurer replaces DispatcherServlet."** False. Configurers only describe callbacks for MVC infrastructure. The Servlet still must be registered by Boot, an initializer, or web.xml.

**"Having @EnableWebMvc automatically scans controllers."** False. Component scanning or explicit bean registration is still required.

**"@EnableWebMvc and mvc:annotation-driven are completely unrelated."** False. Both enable annotation-based MVC support in two configuration styles; differences lie in declaration syntax and specific feature/schema scope.

**"XML mvc:annotation-driven registers DispatcherServlet."** False. Servlet registration is a separate step.

**"Adding a converter with configureMessageConverters does not affect defaults."** Can be false in 6.x Java MVC configuration; distinguish replacing vs. extending. Check the Javadoc for your exact version. In Boot, prefer Boot's message converter integration to keep defaults.

**"WebMvcConfigurer applies to WebFlux since both use Spring Web."** False. WebFlux uses WebFluxConfigurer and reactive codecs; MVC uses the Servlet stack.

**"Interceptors are the ideal place to enforce authorization."** False in many architectures; MVC interceptors may not cover all request paths or security requirements. Use Spring Security/the appropriate filter chain.

**"CORS protects APIs from external clients."** False. CORS is a browser policy governing cross-origin response reading; non-browser clients can send HTTP requests normally. Authentication/authorization remain necessary.

**"XML can be migrated to Java via find-and-replace."** Unreliable. Context scope, bean/configurer ordering, converters, servlet mappings, Boot defaults, and testing must all be considered.

**"The Spring MVC XML namespace will always be developed equally alongside Java config in future releases."** False. Starting in Spring Framework 7.0, the MVC XML namespace is deprecated, and new features are not necessarily reflected fully in XML.

## 14. Self-Check

1. **In Spring Boot, if you only want to add an interceptor, what do you use?** @Configuration implements WebMvcConfigurer; typically do not use @EnableWebMvc.
2. **In plain Spring MVC, does @EnableWebMvc open an HTTP port on its own?** No; DispatcherServlet registration and a container are required.
3. **Which XML element is closest to @EnableWebMvc?** mvc:annotation-driven, placed inside the XML belonging to the appropriate MVC context.
4. **Which XML element corresponds to addResourceHandlers?** mvc:resources.
5. **Why does a Boot project return 404 for static files after adding @EnableWebMvc?** Boot MVC auto-configuration may have been replaced by application-managed configuration, omitting the required resource mappings.
6. **Does a WebMvcConfigurer need @Component/@Configuration?** The implementation must become a Spring bean; an annotation or explicit registration is standard.
7. **When using Spring WebFlux, can you use WebMvcConfigurer?** Not to configure the reactive stack; see WebFluxConfigurer.
8. **Do two DispatcherServlets share one WebApplicationContext by default?** No; each servlet can have its own child context, requiring attention to bean visibility.
9. **Can XML and Java config coexist?** Yes, yet ownership must be managed clearly and duplicate declarations avoided.
10. **What is the difference between configureMessageConverters and extendMessageConverters in Spring 6.x?** One configures the list and can suppress defaults; the other extends/adjusts the already configured list.
11. **When should WebMvcConfigurationSupport/WebMvcRegistrations be considered?** When there is a clear need for low-level infrastructure customization; verify impact on Boot auto-configuration.
12. **When migrating XML to Boot, should mvc:annotation-driven be converted directly to @EnableWebMvc?** Usually no; use Boot MVC auto-config and move needed customizations to WebMvcConfigurer.

## 15. Official Documentation

- [Spring Framework — Enable MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html): @EnableWebMvc, mvc:annotation-driven, Boot notes, and XML deprecation in Spring 7.
- [Spring Framework — MVC Config API](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/customize.html): WebMvcConfigurer.
- [Spring Framework — Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): interceptor mapping and Java/XML differences.
- [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): resource handlers.
- [Spring Framework — View Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-controller.html): view controllers and redirects.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): cors mappings and browser policy.
- [Spring Framework — Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): converter customization and API version notes.
- [Spring Framework — Advanced Java Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/advanced-java.html): DelegatingWebMvcConfiguration and WebMvcConfigurationSupport.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC auto-configuration, WebMvcConfigurer without @EnableWebMvc, and deep customization.
- [Spring Framework — Web MVC Reference](https://docs.spring.io/spring-framework/reference/web/webmvc.html): full Spring MVC lifecycle and architecture.

**Key takeaway:** **@EnableWebMvc enables MVC Java infrastructure**, **WebMvcConfigurer adds customization callbacks**, **mvc:annotation-driven and other mvc:* elements are the XML route**, while **Spring Boot typically auto-configures MVC and only needs WebMvcConfigurer for extensions**.
