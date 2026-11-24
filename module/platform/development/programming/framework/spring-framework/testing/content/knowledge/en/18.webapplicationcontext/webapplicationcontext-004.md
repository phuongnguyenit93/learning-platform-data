# Injecting WebApplicationContext and Mock Web Objects

When testing a Spring MVC application, we typically need both parts: the Spring container to obtain controllers, services, and web configuration; and Servlet objects to simulate requests, responses, sessions, and the servlet context. Spring Test combines these two parts via `WebApplicationContext` and the suite of mock web objects in `spring-test`.

`WebApplicationContext` allows tests to access the application context for a web application. Classes such as `MockHttpServletRequest`, `MockHttpServletResponse`, and `MockHttpSession` provide Servlet objects that can be controlled directly in tests. For full MVC flow testing, `MockMvc` uses those same mock objects to send requests through `DispatcherServlet` without starting a real HTTP server.

## 1. What Is WebApplicationContext?

`WebApplicationContext` is a variant of `ApplicationContext` for Servlet web environments. In addition to managing beans like a regular Spring application context, it is also linked to a `ServletContext`.

From `WebApplicationContext`, an application can access:

- Beans registered in the web application context, such as controllers, services, handler mappings, and view resolvers.
- `ServletContext`, representing the application's web environment.
- Web-environment-dependent capabilities such as request scope, session scope, and web-context-relative resources.

In a Spring MVC application, `DispatcherServlet` receives requests and dispatches them to controllers. `WebApplicationContext` provides the configuration and beans needed by the web layer. An application may have a shared root context and a child context attached to `DispatcherServlet`; the exact structure depends on how the application is configured.

In tests, injecting `WebApplicationContext` lets us build `MockMvc` from the application's actual web configuration. Injecting `ServletContext` also helps test components that need awareness of the Servlet environment.

## 2. Creating WebApplicationContext for Tests

With the Spring TestContext Framework, two annotations are commonly used together:

- `@ContextConfiguration`: specifies the configuration or configuration classes used to create the context.
- `@WebAppConfiguration`: instructs Spring to create a `WebApplicationContext` for the test instead of a regular application context.

When no path is passed to `@WebAppConfiguration`, the default resource base path is `src/main/webapp`. A different resource directory can be specified, for example `@WebAppConfiguration("src/test/webapp")`. Spring Test uses `MockServletContext` to provide a simulated Servlet environment for this context.

With JUnit Jupiter, `@ExtendWith(SpringExtension.class)` connects JUnit 5 to Spring TestContext:

```java
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = WebTestConfig.class)
@WebAppConfiguration
class GreetingControllerTests {
    // Test dependencies will be injected by Spring.
}
```

`WebTestConfig` is the Spring MVC configuration class. For example:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = GreetingController.class)
class WebTestConfig {
}
```

`@EnableWebMvc` registers the core Spring MVC infrastructure; `@ComponentScan` discovers controllers and components in the package containing `GreetingController`. In real projects, tests usually reference the configuration class used by the application to ensure testing covers the running configuration.

## 3. Injecting WebApplicationContext and ServletContext

When Spring creates a web test context, tests can inject `WebApplicationContext` and `ServletContext` with `@Autowired`:

```java
import jakarta.servlet.ServletContext;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.context.WebApplicationContext;

class GreetingControllerTests {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Autowired
    private ServletContext servletContext;
}
```

`WebApplicationContext` also provides `getServletContext()`, so you can verify that both references point to the web application's servlet context:

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(webApplicationContext.getServletContext())
    .isSameAs(servletContext);
```

In components that need to access the Servlet API, Spring also supports mechanisms such as `ServletContextAware` to receive `ServletContext`. However, regular business services should receive explicit business dependencies; do not pass `ServletContext` across layers just to read data unrelated to the web environment.

## 4. Spring's Mock Web Objects

Spring Test provides several classes in the `org.springframework.mock.web` package. They implement or simulate Servlet APIs so tests can configure data and verify results without needing a real servlet container.

| Mock object | Simulated API | Common purpose |
|---|---|---|
| `MockServletContext` | `ServletContext` | Shared web application environment, context attributes, and web resources |
| `MockServletConfig` | `ServletConfig` | Servlet name, `ServletContext`, and init parameters |
| `MockHttpServletRequest` | `HttpServletRequest` | HTTP method, URI, parameters, headers, attributes, and session |
| `MockHttpServletResponse` | `HttpServletResponse` | Status, headers, cookies, and response body |
| `MockHttpSession` | `HttpSession` | Session attributes and session state |

These mock classes allow tests to set up state as desired. For instance, a test can set parameters, headers, or session attributes before invoking the component under test, then assert on the status or data written to the response.

### MockServletContext and MockServletConfig

`MockServletContext` represents the shared servlet context. It is useful when a component needs to read context attributes or access web resources. `MockServletConfig` represents the configuration of a specific servlet and provides the servlet name and init parameters.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.mock.web.MockServletConfig;
import org.springframework.mock.web.MockServletContext;

MockServletContext servletContext = new MockServletContext();

MockServletConfig servletConfig =
    new MockServletConfig(servletContext, "exampleServlet");
servletConfig.addInitParameter("mode", "test");

assertThat(servletConfig.getServletName()).isEqualTo("exampleServlet");
assertThat(servletConfig.getInitParameter("mode")).isEqualTo("test");
```

In tests using `@WebAppConfiguration`, Spring Test typically creates and manages `MockServletContext` for `WebApplicationContext`. There is no need to create another context manually if the goal is to test beans injected into the web test context.

### MockHttpServletRequest, MockHttpServletResponse, and MockHttpSession

HTTP mock objects can be created directly to test a filter, adapter, or low-level Servlet component:

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockServletContext;

MockServletContext servletContext = new MockServletContext();

MockHttpServletRequest request =
    new MockHttpServletRequest(servletContext);
request.setMethod("POST");
request.setRequestURI("/orders");
request.setParameter("customerId", "C-208");
request.addHeader("X-Request-Source", "test");

MockHttpSession session = new MockHttpSession(servletContext);
session.setAttribute("userId", "U-17");
request.setSession(session);

MockHttpServletResponse response = new MockHttpServletResponse();
response.setStatus(HttpServletResponse.SC_CREATED);
response.addHeader("X-Result", "created");

assertThat(request.getParameter("customerId")).isEqualTo("C-208");
assertThat(request.getSession().getAttribute("userId")).isEqualTo("U-17");
assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_CREATED);
assertThat(response.getHeader("X-Result")).isEqualTo("created");
```

This example only creates and inspects the state of mock Servlet objects. It does not invoke `DispatcherServlet`, execute controllers, or prove that an HTTP request can pass through the entire application.

## 5. Using WebApplicationContext to Build MockMvc

For testing controllers and Spring MVC flows, `MockMvc` is usually a better choice than calling controllers directly or wiring request and response objects manually. `MockMvc` sends requests through a `DispatcherServlet` configured with Spring MVC, uses the mock servlet objects underneath, and returns results for test assertions.

Build `MockMvc` from `WebApplicationContext` using `MockMvcBuilders.webAppContextSetup(...)`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

class GreetingControllerTests {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .build();
    }
}
```

Suppose the application has the following controller:

```java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
class GreetingController {

    @GetMapping("/greeting")
    @ResponseBody
    String greeting(
            @RequestParam(defaultValue = "friend") String name) {
        return "Hello " + name;
    }
}
```

A test can send a request and verify the response as follows:

```java
import org.junit.jupiter.api.Test;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void returnsGreetingForRequestedName() throws Exception {
    mockMvc.perform(get("/greeting").param("name", "Mai"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello Mai"));
}
```

The request builder constructs a mock request; `DispatcherServlet` processes the request using beans in the web application context; result matchers verify the HTTP status and response body. The test does not need to open a network port or send requests to a running server.

`webAppContextSetup` uses the web configuration loaded in the context, making it suitable when you need to verify the interaction of controllers, handler mappings, converters, exception resolvers, and other MVC components. If filters need to be applied in MockMvc, register them through the appropriate test configuration, such as the builder's `addFilters(...)` or the testing setup in use.

## 6. Choosing webAppContextSetup or standaloneSetup

The two ways of building `MockMvc` serve two different testing scopes:

| Creation method | Configuration used | When appropriate |
|---|---|---|
| `webAppContextSetup(webApplicationContext)` | Web application context loaded by Spring | MVC integration testing with real application configuration and beans |
| `standaloneSetup(controller)` | Direct registration of the controller with minimal configuration | Focused testing of one or a few controllers without loading the full web context |

If the test's goal is to confirm that Spring created `WebApplicationContext`, injected the right beans, and that MVC works with application configuration, use `webAppContextSetup`. `standaloneSetup` does not take configuration from `WebApplicationContext`, so it cannot be used to verify web context injection or initialization.

## 7. Using Spring Boot in Web Testing

For Servlet-based Spring Boot applications, you can use the integration test configuration provided by Boot:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerBootTests {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void webContextIsAvailable() {
        assertThat(webApplicationContext.getServletContext()).isNotNull();
    }
}
```

For Servlet web applications, `@SpringBootTest` uses a mock web environment by default; `@AutoConfigureMockMvc` configures and provides `MockMvc` for injection into the test. In this configuration style, Boot creates the web context and MockMvc through its auto-configuration mechanism. Normally there is no need to add `@WebAppConfiguration` or call `MockMvcBuilders.webAppContextSetup(...)` again manually.

If the application is not a Servlet web application, you cannot assume by default that `WebApplicationContext` will exist. Verify the application type and web environment before injecting Servlet APIs.

## 8. Limitations to Understand When Using Mock Web Objects

Mock objects are very useful, but they are not a complete servlet container:

- They do not open HTTP ports and do not test network communication.
- They do not prove that deployment configuration for Tomcat, Jetty, or another container works properly.
- Having a parameter or session attribute on a mock request does not automatically prove a browser, proxy, or real container will produce a similar request.
- Creating `MockHttpServletRequest` directly does not automatically run filter chains, `DispatcherServlet`, interceptors, or controllers.
- `MockMvc` tests the Spring MVC pipeline in a mock environment; differences dependent on a real container still need testing in an appropriate environment.

If you need to test requests passing through a real server, use a test style that starts a server, such as Spring Boot `@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)`, and send HTTP requests to that server. That is a different scope from testing with `MockMvc`.

## 9. Common Errors and How to Identify the Cause

| Symptom | Causes to check |
|---|---|
| Cannot inject `WebApplicationContext` | The test context is not configured as a web context; check `@WebAppConfiguration` or Spring Boot configuration and application type |
| Controller or handler not found | Component scan configuration does not include the controller, or MVC configuration was not loaded |
| `webAppContextSetup` does not receive a context | `WebApplicationContext` is not injected or a non-web application context is being used |
| Test uses `standaloneSetup` but expects application configuration to apply | `standaloneSetup` does not use the web application context; switch to `webAppContextSetup` if full configuration is needed |
| Testing a request-scoped component directly without an active request | The component is being called outside the request lifecycle; use `MockMvc` or set up an appropriate request context for that test type |
| Mock test succeeds but real deployment hits container errors | Mocks do not fully test servlet container behavior; add tests against a real server when requirements demand it |

When investigating errors, identify which layer the test is verifying: a Servlet API object, a filter, an individual controller, the full Spring MVC context, or a deployed server. Choosing the right test level helps avoid drawing false conclusions from an overly simple mock.

## 10. Process for Selecting Testing Tools

1. If you need the application's web beans and configuration, create `WebApplicationContext` with `@WebAppConfiguration` combined with `@ContextConfiguration`, or use Spring Boot's web test configuration.
2. If you need access to the web environment, inject `WebApplicationContext` or `ServletContext`.
3. If you only need to inspect the state of Servlet API objects, create `MockHttpServletRequest`, `MockHttpServletResponse`, `MockHttpSession`, or the corresponding mock.
4. If you need to send requests through Spring MVC, create `MockMvc` with `webAppContextSetup` and verify results using request/result matchers.
5. If you need to verify behavior of a real server or servlet container, use tests that start a server rather than relying on mocks.

`WebApplicationContext` provides the Spring foundation for the web environment; web mock objects simulate the Servlet API; `MockMvc` connects both parts to test requests through Spring MVC. Understanding each part's role helps tests verify the right scope and avoid confusing mock results with the behavior of a real server.
