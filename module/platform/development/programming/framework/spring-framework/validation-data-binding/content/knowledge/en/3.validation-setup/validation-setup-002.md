# Role of spring-beans, spring-core, spring-context, and Web Modules in Spring Framework

## 1. The Big Picture

Spring Framework is divided into multiple modules with clear responsibilities. When building web applications, we commonly see four groups appearing together:

- **spring-core**: foundational utilities and core mechanisms shared by other Spring modules.
- **spring-beans**: defines, creates, configures, and manages beans, including dependencies between objects.
- **spring-context**: builds `ApplicationContext` on top of the bean factory, providing configuration environments and application-level services.
- **Web modules** (typically `spring-web`, `spring-webmvc`, `spring-webflux`): HTTP protocol integration, request/response handling, and building web applications in either the servlet or reactive model.

Understand this relationship along the axis **foundation → container → application context → web**. Not every Spring application needs web; a command-line application can still use core, beans, and context. Conversely, Spring MVC requires a Spring application and the appropriate web parts to handle requests.

```text
                Web Application
                 /       \
         Spring MVC     WebFlux
             |             |
         spring-web    spring-webflux
              \          /
            spring-context
                  |
             spring-beans
                  |
              spring-core
```

This diagram only illustrates the main responsibility layers, not a complete Maven dependency graph. Each module also has other dependencies (such as `spring-aop`, `spring-expression`, `spring-jcl`, or underlying libraries) depending on features and versions.

## 2. spring-core: Foundational Mechanisms and Utilities

`spring-core` provides many building blocks for the Framework to operate. Key concepts to recognize:

1. **Resource abstraction**: `Resource`, `ClassPathResource`, `FileSystemResource`, and APIs to read resources uniformly instead of letting each module handle classpath/file/URL individually.
2. **Type conversion**: `ConversionService`, `Converter<S,T>`, `ConverterFactory`, and `GenericConverter` allow converting data between Java types.
3. **Type/introspection utilities**: supports metadata analysis, reflection, generic types, and collection/string utilities needed by the framework.
4. **Environment-related foundational APIs**: foundational abstractions that the context layer can build upon to handle properties and configuration.
5. **Spring utilities**: some internal/utility tools can be used directly when appropriate, though you should not rely on unstable internal APIs.

Example using type conversion directly, without needing a web server:

```java
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public class CoreConversionDemo {
    public static void main(String[] args) {
        ConversionService conversionService = new DefaultConversionService();
        Integer port = conversionService.convert("8080", Integer.class);
        System.out.println(port);
    }
}
```

Output when run with Spring Core on the runtime classpath:

```text
8080
```

`CoreConversionDemo.java` is a valid program with `main`, but **it must have the corresponding Spring dependencies on the compile/runtime classpath**. Running plain `javac CoreConversionDemo.java` without providing the Spring JARs will report missing packages; the example does not imply the JDK includes Spring.

**Boundary:** `spring-core` does not act as an IoC container on its own and does not start an HTTP application. `ConversionService` is a general API, while Spring MVC selects and uses the conversion service through the web layer's data binding mechanism.

## 3. spring-beans: Creating and Managing Application Objects

`spring-beans` is the core part of the IoC container. It provides APIs such as:

- `BeanFactory`: interface for retrieving beans by name/type; the container can instantiate objects and resolve dependencies.
- `BeanDefinition`: metadata describing how to create a bean, its class, scope, and related settings.
- `DefaultListableBeanFactory`: common implementation for registering and managing bean definitions.
- `BeanPostProcessor`: extends bean initialization, intervening in stages before/after initialization.
- `BeanWrapper` and property binding infrastructure: supports accessing/updating JavaBean properties and converting data.

**Dependency Injection (DI)** is a major application of IoC: instead of creating dependencies everywhere with `new`, objects receive the components they need via constructors (usually preferred), setters, or other injection forms. The container is responsible for wiring the object graph.

Example using `BeanFactory` directly:

```java
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;

public class BeanFactoryDemo {
    public static class GreetingService {
        public String greet() {
            return "Hello";
        }
    }

    public static void main(String[] args) {
        DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
        factory.registerBeanDefinition(
                "greetingService",
                BeanDefinitionBuilder
                        .genericBeanDefinition(GreetingService.class)
                        .getBeanDefinition()
        );

        GreetingService service = factory.getBean(
                "greetingService", GreetingService.class);
        System.out.println(service.greet());
    }
}
```

Output (when Spring Beans and accompanying dependencies are present):

```text
Hello
```

The example illustrates how the container stores `BeanDefinition` and returns a bean. With a plain `BeanFactory`, do not assume every utility that `ApplicationContext` enables out of the box is registered or behaves the same way. In real-world applications, `ApplicationContext` is usually preferred over managing `DefaultListableBeanFactory` directly.

### Scope, Lifecycle, and Dependencies

By default, beans in a Spring container typically have **singleton scope per IoC container**: one instance is reused across requests for the corresponding bean definition; this **does not mean singleton across the entire JVM**. Scopes such as `prototype`, `request`, and `session` carry different meanings, and some scopes are only available in a web context.

For singletons, Spring manages the bean's initialization and destruction callbacks while the container runs/closes. For prototypes, the container creates a new instance on demand but does not manage the full destruction phase after handing the bean to the caller. This is an important point when a bean holds resources that must be closed.

## 4. spring-context: ApplicationContext and Application-Level Services

`spring-context` provides the `ApplicationContext` abstraction, extending the capabilities of `BeanFactory`. In addition to bean management, it supports patterns commonly used in an application:

- **Application events** via `ApplicationEventPublisher` and `@EventListener`.
- **Internationalization** via `MessageSource` and locale.
- **Resource loading** and application environment (`Environment`, property sources, profiles).
- **Lifecycle orchestration**: refreshing/closing the context and many application-level hooks.
- **Annotation-driven configuration** with `@Configuration`, `@Bean`, `@ComponentScan`, and `AnnotationConfigApplicationContext`.

Java 17+ example of constructor injection, without depending on HTTP:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ContextDemo {
    public static final class Repository {
        public String value() { return "DATA"; }
    }

    public static final class Service {
        private final Repository repository;

        public Service(Repository repository) {
            this.repository = repository;
        }

        public String read() {
            return repository.value();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean Repository repository() {
            return new Repository();
        }

        @Bean Service service(Repository repository) {
            return new Service(repository);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Service service = context.getBean(Service.class);
            System.out.println(service.read());
        }
    }
}
```

Output:

```text
DATA
```

Point to observe: `service(Repository repository)` declares its dependency via the `@Bean` method parameter. The container picks the matching bean, instantiates it, and supplies the instance. `try-with-resources` closes the context, helping execute proper shutdown procedures and destroy callbacks.

### How Do ApplicationContext and BeanFactory Differ?

| Criterion | BeanFactory | ApplicationContext |
| --- | --- | --- |
| Primary role | Basic container API to retrieve/configure beans | Application-level container built on top of BeanFactory |
| Bean configuration | Can register definitions and processors manually | Typically integrates annotation configuration and prepares infrastructure automatically |
| Events, messages, environment | Not all services are enabled by default in the base interface | Supports application-level services |
| Lifecycle | Depends on implementation and setup | Has `refresh`, `close` via the corresponding contexts |
| Common usage | Framework internals or specialized scenarios | Most Spring applications |

Do not infer that `ApplicationContext` is a separate process or service: it is an object/container living inside the application's JVM.

## 5. Web Modules: From HTTP to Controller

Web components build upon the container/context foundation but solve problems at a different layer: receiving HTTP requests, selecting handlers, mapping parameters, orchestrating processing, converting data, and producing responses.

### 5.1. spring-web

`spring-web` provides many common web components, such as:

- Abstractions for web contexts and servlet-related infrastructure.
- HTTP message conversion and request/response support types.
- APIs/utilities for web integration and HTTP clients in appropriate configurations.
- Supporting infrastructure for parts of MVC/WebFlux at various levels.

`spring-web` **is not equivalent to a complete Spring MVC application**. The MVC portion—including handler mapping, controller invocation, view resolution, and `DispatcherServlet`—resides in `spring-webmvc`.

### 5.2. spring-webmvc

Spring MVC is the traditional web model based on the Servlet API. Main building blocks:

1. **Servlet container** (e.g., Tomcat) accepts HTTP connections and calls `DispatcherServlet`.
2. **`DispatcherServlet`** is the front controller dispatching requests.
3. **`HandlerMapping`** finds the handler matching the URL/method/mapping conditions.
4. **`HandlerAdapter`** executes the handler/controller, typically invoking argument resolvers and data binders.
5. **`ConversionService`**, validators, and `HttpMessageConverter` assist with converting/reading/writing data in context.
6. **ViewResolver** serves view-based responses when using MVC views; with `@ResponseBody` or `@RestController`, the response is typically serialized via message converters.

REST endpoint example:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {
    @GetMapping("/status/{code}")
    public String status(@PathVariable int code) {
        return "status=" + code;
    }
}
```

In a started Spring MVC application with this controller registered, `GET /status/200` returns the body `status=200`. The string `"200"` from the path is converted to `int` when resolving the parameter; the controller relies on Spring's DI/container, while the web layer orchestrates HTTP. This is an **application component**, not a standalone Java class with `main`.

### 5.3. spring-webflux

`spring-webflux` is the reactive web stack, using `Mono`/`Flux` from Reactor and supporting a non-blocking runtime model. It can run on a suitable runtime such as Reactor Netty or a Servlet container supporting the corresponding configuration.

WebFlux provides both annotation-based controller and functional routing programming models, but its request pipeline/adapters differ from MVC. Do not assume that adding `spring-webflux` to the classpath automatically turns an entire MVC application reactive or makes blocking code non-blocking. Stack choice must be based on workload characteristics, APIs, dependencies, and deployment runtime.

## 6. How Modules Coordinate When a Request Arrives

Suppose a web app exposes `GET /users/7`:

```text
HTTP GET /users/7
       |
       v
Servlet container -> DispatcherServlet      (spring-webmvc)
       |
       v
HandlerMapping + HandlerAdapter             (spring-webmvc)
       |
       +--> resolve path variable "7"
       |       -> convert String to long    (spring-core conversion API,
       |                                     binder/web integration)
       v
UserController                             (bean in ApplicationContext)
       |
       v
UserService                                (bean created/injected by spring-beans)
       |
       v
UserRepository                             (injected dependency)
       |
       v
HTTP response                              (spring-web / spring-webmvc)
```

`spring-context` is responsible for the context holding beans and configuration, `spring-beans` handles the object graph and injection, `spring-core` provides the utility/conversion foundation, and MVC handles the HTTP portion. They **work together**, rather than being four competing frameworks.

### Request Parameters and JSON Are Two Different Paths

For `@PathVariable`, `@RequestParam`, and `@ModelAttribute`, Spring typically uses the conversion/binding infrastructure to go from a string to the target type.

For `@RequestBody` containing JSON, the framework uses `HttpMessageConverter` and the configured serialization/deserialization library (typically Jackson) to construct the object. Therefore, a `Converter<String, X>` registered by the application in `ConversionService` does not automatically become a Jackson JSON deserializer.

## 7. Dependencies and Configuration in Real-World Applications

In projects using Spring Boot, the most common approach is declaring the corresponding **starter**, instead of adding individual Spring JARs manually. Gradle example (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

The web starter brings in the MVC web stack along with essential Spring components according to Boot's dependency management and an appropriate embedded server. The Spring Framework version is selected consistently by the Spring Boot BOM/plugin; do not manually mix a `spring-webmvc` version different from `spring-context` without strict reasons and thorough testing.

For the reactive stack, you can use the WebFlux starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

If both starters are declared in the same Spring Boot application, the default web application type is typically servlet/MVC when MVC is present. If you intentionally want reactive, understand and configure the environment explicitly; do not rely on Gradle declaration order.

In a plain Spring Framework application (without Boot), you must configure the context, controller registration, servlet/reactive runtime, and appropriate MVC/WebFlux infrastructure. Adding a dependency is a necessary condition, but not sufficient on its own for endpoints to run.

### Common Classpath Issues

- **`ClassNotFoundException` / `NoClassDefFoundError`**: a required JAR may be missing or the runtime classpath is inconsistent.
- **`NoSuchMethodError`**: usually indicates a binary version conflict between JARs.
- **Bean not found**: an issue with context/component scan/`@Bean`/profile/bean creation conditions—do not automatically conclude a `spring-core` bug.
- **HTTP 404 despite having a controller**: check request mapping, whether the controller is inside the MVC context, servlet path, and route configuration.
- **Registered converter is not used**: check the registry of the conversion service serving the exact binding flow.
- **Inappropriate bean scope**: do not inject request state into a singleton without a scope/proxy model or clear design.

## 8. Testing Layer by Layer

You can verify each module's responsibility at different testing levels:

1. **Core**: instantiate `DefaultConversionService` and test conversions of individual strings, including invalid input.
2. **Beans**: create `DefaultListableBeanFactory`, register bean definitions, and test dependencies/lifecycle when needed.
3. **Context**: use `AnnotationConfigApplicationContext` to test `@Configuration`, `@Bean`, and dependency injection without a web server.
4. **Web MVC**: use integration tests or `MockMvc` with the appropriate context to test mapping, binding, validation, and status/response.
5. **WebFlux**: use the corresponding reactive testing tools (such as `WebTestClient`) and test both error handling and asynchronous behavior when needed.

Layered testing helps pinpoint failures to the right responsibility. A unit test of `ConversionService` does not prove an HTTP endpoint is registered; conversely, a successful request does not test all converters and lifecycle behaviors.

## 9. Key Takeaways and Application

| Need | Module/class to start exploring |
| --- | --- |
| Convert strings to Java types, read resources, core utilities | `spring-core`, `ConversionService`, `Resource` |
| Create, configure, inject beans | `spring-beans`, `BeanFactory`, `BeanDefinition` |
| Manage context, `@Configuration`, events, profiles, messages | `spring-context`, `ApplicationContext` |
| HTTP abstractions, integration, and message conversion | `spring-web` |
| Servlet-based request routing, controllers, MVC pipeline | `spring-webmvc`, `DispatcherServlet` |
| Reactive HTTP pipeline, `Mono`/`Flux`, functional router | `spring-webflux` |

When reading stack traces, documentation, or dependency trees, categorize the issue into these groups first: **foundational mechanisms**, **bean container**, **application context**, or **web request pipeline**. From there, locate the right extension point and avoid configuring at the wrong layer.