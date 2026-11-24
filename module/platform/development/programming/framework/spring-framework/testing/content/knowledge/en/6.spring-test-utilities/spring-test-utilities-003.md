# MockServletContext and Mock Servlet Objects

Spring Test provides a group of Servlet API mock classes for testing components that require a web environment without starting a real servlet container. The central component is **MockServletContext**: a lightweight ServletContext implementation that can store init parameters, application attributes, and provide resource access as configured by the test. Alongside it are objects such as **MockHttpServletRequest**, **MockHttpServletResponse**, **MockHttpSession**, **MockServletConfig**, and **MockFilterConfig**.

These classes are useful when testing a servlet, filter, listener, or a Spring component that accepts a ServletContext. They also form the foundation Spring MVC Test uses to simulate requests and responses. However, you need to choose the right test level: creating MockServletContext directly helps test an individual Servlet component; using MockMvc sends requests through the Spring MVC processing chain; testing with an embedded server is what confirms behavior through an actual servlet container.

## 1. ServletContext in a web application

According to the Servlet API, each web application has a ServletContext representing the deployed application environment. ServletContext provides application-wide capabilities:

- Reading initialization parameters configured for the web application.
- Storing and sharing application attributes among components in the same application.
- Accessing web application resources.
- Retrieving information about the context and Servlet environment.
- Supporting dynamic component registration APIs during startup, depending on the Servlet version.

ServletContext has a broader scope than HttpServletRequest or HttpSession. A request represents a single HTTP exchange; a session represents state tied to a user session; ServletContext represents the shared environment of the web application.

| Object | Scope | Example data |
|---|---|---|
| ServletContext | Entire web application | Application name, shared configuration, application attributes |
| ServletConfig | Single servlet | Servlet name, servlet-specific init parameters |
| FilterConfig | Single filter | Filter-specific init parameters |
| HttpServletRequest | Single HTTP request | Method, URI, headers, parameters, body |
| HttpServletResponse | Single HTTP response | Status, headers, body |
| HttpSession | Single user session | User id, session data, login state |

Distinguishing scopes is important when preparing tests. If data belongs to a single request, do not store it in ServletContext just so other methods can read it. If configuration applies to an individual servlet, ServletConfig is usually the more appropriate place.

## 2. What is MockServletContext?

**MockServletContext** is located in the org.springframework.mock.web package of the spring-test module. It is a Java object implementing ServletContext with mock behavior suited for tests. It is not a Mockito mock that only has pre-programmed calls; it holds basic state and behavior so the component under test can use it like a ServletContext.

You can create a minimal context:

~~~java
import org.springframework.mock.web.MockServletContext;

class ServletContextComponentTest {

    void example() {
        MockServletContext servletContext = new MockServletContext();

        servletContext.setAttribute("application.name", "test-app");
        servletContext.setInitParameter("feature.upload.enabled", "true");

        assertEquals("test-app",
            servletContext.getAttribute("application.name"));
        assertEquals("true",
            servletContext.getInitParameter("feature.upload.enabled"));
    }
}
~~~

The snippet illustrates setting an application attribute and an init parameter. In real tests, these values should be prepared before invoking the component under test.

### 2.1. Init parameters and application attributes

Init parameters are configuration values read through ServletContext. They typically represent configuration settings for the web application. Application attributes are runtime state that can be stored and shared among components using the same context.

~~~java
MockServletContext context = new MockServletContext();

context.setInitParameter("asset.version", "v2");
context.setAttribute("maintenance.enabled", Boolean.FALSE);

assertEquals("v2", context.getInitParameter("asset.version"));
assertEquals(Boolean.FALSE, context.getAttribute("maintenance.enabled"));
~~~

These two kinds of data have different meanings:

- Init parameters are used to read configuration. In the real Servlet API, setting init parameters is restricted to the application initialization phase. In tests, set them right when creating the mock context, before running the component.
- Attributes are runtime state; components can add, read, or remove attributes during execution.

If a component calls setAttribute, removeAttribute, or getAttributeNames, MockServletContext allows observing those operations in tests. However, tests should verify behavior that is meaningful to the component's contract rather than asserting unnecessary internal details.

### 2.2. Web application resources

ServletContext provides APIs such as getResource, getResourceAsStream, and getResourcePaths to access resources in the web application. MockServletContext provides a mechanism to simulate these APIs based on a configured resource base path and ResourceLoader.

When testing a component that reads files from the web application, define the test's resource root explicitly. Do not assume that the working directory of the IDE, Gradle, or CI is the same. You can use the constructor that takes a resource base path and a ResourceLoader to specify how resources are resolved.

Example initialization structure:

~~~java
MockServletContext context = new MockServletContext(
    "src/main/webapp",
    new FileSystemResourceLoader()
);
~~~

The path here is an example and needs to match your project's resource directory as well as the working directory when running tests. If the goal is to test resources on the classpath, choose the corresponding ResourceLoader instead of depending on a file path on a developer's machine.

When testing resource lookups, verify the essential scenarios:

- The resource exists and can be read.
- Missing resources are handled properly.
- The passed path follows ServletContext conventions, typically starting with a slash.
- The component does not assume every resource has a real file-system path.

MockServletContext can simulate resource lookups, but it does not reproduce every difference in how WARs are packaged and deployed on containers. If behavior depends on how the container publishes resources or on the production filesystem, add appropriate deployment tests.

## 3. Testing components that accept ServletContext

Some Spring components implement ServletContextAware to receive the ServletContext during initialization. For small components, you can pass a MockServletContext directly to test how it uses the context.

~~~java
import jakarta.servlet.ServletContext;
import org.springframework.web.context.ServletContextAware;

class UploadSettings implements ServletContextAware {

    private String uploadDirectory;

    @Override
    public void setServletContext(ServletContext servletContext) {
        this.uploadDirectory =
            servletContext.getInitParameter("upload.directory");
    }

    String uploadDirectory() {
        return uploadDirectory;
    }
}
~~~

Corresponding test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockServletContext;

class UploadSettingsTest {

    @Test
    void readsUploadDirectoryFromServletContext() {
        // Arrange
        MockServletContext servletContext = new MockServletContext();
        servletContext.setInitParameter(
            "upload.directory",
            "/var/app/uploads"
        );
        UploadSettings settings = new UploadSettings();

        // Act
        settings.setServletContext(servletContext);

        // Assert
        assertEquals("/var/app/uploads", settings.uploadDirectory());
    }
}
~~~

The example uses the Jakarta Servlet API. With Spring Framework 6 and later, the Servlet API is in the jakarta.servlet namespace. With Spring Framework 5.x, the corresponding imports are usually in javax.servlet. Do not mix both namespaces in the same application because they are two different sets of classes.

The test above checks that the component reads the configuration properly from ServletContext. It does not test Spring's automatic detection of ServletContextAware and invocation of the callback. If the goal is to test Spring WebApplicationContext wiring, initialize a web context in the test and retrieve the bean from that context.

## 4. Commonly used Servlet mocks

Spring Test provides multiple mock objects for individual parts of the Servlet API. Each type has its own scope:

| Mock class | Simulated object | Common use case |
|---|---|---|
| MockServletContext | ServletContext | Application-level configuration and state |
| MockServletConfig | ServletConfig | Servlet-specific init parameters and servlet name |
| MockFilterConfig | FilterConfig | Filter-specific init parameters |
| MockHttpServletRequest | HttpServletRequest | Method, URI, headers, parameters, body, session |
| MockHttpServletResponse | HttpServletResponse | Status, headers, cookies, and response body |
| MockHttpSession | HttpSession | Attributes and session state |
| MockPart | Part | Multipart upload data |
| MockRequestDispatcher | RequestDispatcher | Testing forward/include in appropriate tests |
| MockServletInputStream | ServletInputStream | Request content stream |
| MockServletOutputStream | ServletOutputStream | Response content stream |

These classes are designed to work together. For example, MockHttpServletRequest can be constructed with a MockServletContext and have a MockHttpSession attached; MockServletConfig also takes a ServletContext to represent a servlet's environment.

## 5. MockServletConfig and MockFilterConfig

ServletConfig holds configuration specific to a servlet. FilterConfig holds configuration specific to a filter. Both reference the shared ServletContext.

~~~java
import org.springframework.mock.web.MockServletConfig;
import org.springframework.mock.web.MockServletContext;
import org.springframework.mock.web.MockFilterConfig;

MockServletContext context = new MockServletContext();

MockServletConfig servletConfig =
    new MockServletConfig(context, "reportServlet");
servletConfig.addInitParameter("format", "csv");

MockFilterConfig filterConfig =
    new MockFilterConfig(context, "auditFilter");
filterConfig.addInitParameter("header-name", "X-Request-Id");

assertEquals("reportServlet", servletConfig.getServletName());
assertEquals("csv", servletConfig.getInitParameter("format"));
assertEquals("auditFilter", filterConfig.getFilterName());
assertEquals("X-Request-Id", filterConfig.getInitParameter("header-name"));
~~~

This example demonstrates preparing both types of configuration. When testing a servlet or filter, pass the appropriate config to the corresponding init lifecycle method. A servlet receives ServletConfig; a filter receives FilterConfig. Both can access ServletContext via the config.

A filter test can use MockFilterConfig to verify that the filter reads the expected header name or operating mode. If the filter is configured by a Spring bean, test the Spring configuration in an appropriate test rather than creating config manually and concluding the entire filter initialization process is correct.

## 6. MockHttpServletRequest and MockHttpServletResponse

MockHttpServletRequest and MockHttpServletResponse are two essential classes when testing components that interact directly with the HTTP Servlet API.

The mock request allows setting up:

- HTTP method and request URI.
- Context path, servlet path, and query string.
- Headers and parameters.
- Request body and content type.
- Principal, roles, and session.

The mock response allows observing:

- HTTP status.
- Headers and cookies.
- Content type and encoding.
- Response body as bytes or text.
- Redirect or error status that was set.

Example testing a filter that attaches a correlation id to the response:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockServletContext;

class CorrelationIdFilterTest {

    @Test
    void copiesCorrelationIdToResponseHeader() throws Exception {
        // Arrange
        MockServletContext context = new MockServletContext();
        MockHttpServletRequest request =
            new MockHttpServletRequest(context);
        MockHttpServletResponse response =
            new MockHttpServletResponse();

        request.setMethod("GET");
        request.setRequestURI("/orders");
        request.addHeader("X-Correlation-Id", "trace-123");

        Filter filter = (ServletRequest servletRequest,
                         ServletResponse servletResponse,
                         FilterChain chain) -> {
            HttpServletRequest httpRequest =
                (HttpServletRequest) servletRequest;
            HttpServletResponse httpResponse =
                (HttpServletResponse) servletResponse;

            httpResponse.setHeader(
                "X-Correlation-Id",
                httpRequest.getHeader("X-Correlation-Id")
            );
            chain.doFilter(servletRequest, servletResponse);
        };

        // Act
        filter.doFilter(request, response, (req, res) -> {
            ((HttpServletResponse) res).setStatus(
                HttpServletResponse.SC_NO_CONTENT
            );
        });

        // Assert
        assertEquals("trace-123", response.getHeader("X-Correlation-Id"));
        assertEquals(HttpServletResponse.SC_NO_CONTENT, response.getStatus());
    }
}
~~~

The filter in the example is a lambda illustrating the Servlet Filter contract. The request and response are passed directly into the filter; the FilterChain simulates the next processing step and sets a status so the test confirms the filter called the chain.

In real tests, you can instantiate your application's filter class and pass in mock request and response objects. If you need to check that the filter is registered in the right order within Spring Security or the servlet container, testing the filter in isolation is not enough; verify the filter chain configuration or send requests through MockMvc or the corresponding embedded server.

### 6.1. Testing request body and response body

The mock request lets you attach a byte body:

~~~java
byte[] requestBody = """
    {"name":"Ada"}
    """.getBytes(StandardCharsets.UTF_8);
request.setContent(requestBody);
request.setContentType("application/json");
~~~

The mock response lets a component write content via a writer or output stream. After invoking the component, the test can read the content using getContentAsString or getContentAsByteArray:

~~~java
assertEquals("created", response.getContentAsString());
~~~

When testing bodies, keep charsets consistent. If the content is JSON or Unicode text, configure the appropriate encoding and compare the content decoded with the matching charset. For binary responses, compare byte arrays or check metadata such as content type and content length.

Do not merely assert that the response body is non-empty. Verify a structure or value that is meaningful to the HTTP contract the component provides.

## 7. MockHttpSession and session state

HttpSession stores state tied to a user session. MockHttpSession lets you test reading, writing, and removing session attributes without a browser or container.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockServletContext;

class SessionStateTest {

    @Test
    void readsUserIdFromSession() {
        // Arrange
        MockServletContext context = new MockServletContext();
        MockHttpSession session = new MockHttpSession(context);
        session.setAttribute("userId", "user-42");

        MockHttpServletRequest request =
            new MockHttpServletRequest(context);
        request.setSession(session);

        // Act
        Object userId = request.getSession().getAttribute("userId");

        // Assert
        assertEquals("user-42", userId);
    }
}
~~~

MockHttpSession is also useful for testing invalidation behavior, session attributes, and new/existing session state. When testing login or authorization logic, remember that placing an attribute in a mock session only tests that the code reads that state. It does not prove that cookies, session ids, session fixation protection, or container-side session storage are configured correctly.

If you need to test Spring Security integration, send requests through MockMvc with an appropriate authentication mechanism. When you need to test session persistence or real session configuration, use an embedded server and the corresponding session store environment.

## 8. MockServletContext in Spring WebApplicationContext

WebApplicationContext is an ApplicationContext aware of the web environment. Some beans in a web context require a ServletContext. In low-level tests, you can create a web application context and attach a MockServletContext before refreshing.

Conceptual example with AnnotationConfigWebApplicationContext:

~~~java
import org.springframework.mock.web.MockServletContext;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;

class WebContextConfigurationTest {

    @Test
    void createsWebContextWithMockServletContext() {
        MockServletContext servletContext = new MockServletContext();

        try (AnnotationConfigWebApplicationContext context =
                 new AnnotationConfigWebApplicationContext()) {

            context.setServletContext(servletContext);
            context.register(WebTestConfiguration.class);
            context.refresh();

            assertNotNull(context.getServletContext());
            assertNotNull(context.getBean(WebComponent.class));
        }
    }
}
~~~

The example assumes WebTestConfiguration registers WebComponent. The important order is attaching the ServletContext and registering configurations before refreshing the context. After refresh, Spring creates beans and executes related callbacks according to the context lifecycle.

In Spring Boot applications, most tests do not need to create AnnotationConfigWebApplicationContext manually. You can use @SpringBootTest or @WebMvcTest so Spring Boot and Spring Test prepare an appropriate context. Creating a context manually is better suited when testing a small web configuration or a standalone Spring Web component.

## 9. Relationship between Servlet mocks and MockMvc

MockServletContext, MockHttpServletRequest, and MockHttpServletResponse are the foundational building blocks. MockMvc builds on these mock objects and provides a high-level API to dispatch requests through Spring MVC's DispatcherServlet.

| Testing approach | Entry point | Scope tested |
|---|---|---|
| Calling a component with MockServletContext | ServletContext or context-receiving component | How the component uses the context |
| Calling a filter/servlet with mock request and response | Servlet Filter or Servlet | Behavior of the specific Servlet component |
| MockMvc | Simulated HTTP request dispatched through DispatcherServlet | Mappings, argument resolvers, converters, validation, controllers, exception handling, and response |
| Embedded servlet container | HTTP client sending over a real port | Integration with container, server connector, and real deployment pipeline |

MockMvc example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsNotFoundForUnknownOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", "missing"))
            .andExpect(status().isNotFound());
    }
}
~~~

MockMvc is appropriate when the goal is to test Spring MVC HTTP behavior. There is no need to create MockHttpServletRequest and call DispatcherServlet manually for typical controller scenarios.

Conversely, if you are testing an isolated filter or a component that only needs to read a ServletContext attribute, creating Servlet mocks directly can make the test shorter and more focused.

## 10. Limitations to understand when using Servlet mocks

MockServletContext and the other mock classes provide a lightweight model of the Servlet API. They do not replace a full servlet container. Some behaviors that depend on the real environment may not be simulated or may not share the exact same characteristics.

Do not use Servlet mocks to draw conclusions about:

- Sockets, TLS, HTTP connectors, and real network communication.
- Reverse proxy or load balancer configuration.
- How the container deploys and initializes a WAR.
- The full lifecycle of the container, listeners, filters, and servlet registrations in a production environment.
- JSP engines, container session persistence, or characteristics specific to Tomcat/Jetty/Undertow.
- Compatibility between the application and a specific container version.

MockServletContext can hold attributes and provide basic resource lookups, but it does not fully simulate the application deployment process. MockHttpSession can hold session attributes, but it does not prove real cookies and session stores work. MockHttpServletResponse can capture status/headers/body, but it does not prove the response was transmitted over the network.

When a requirement depends on the container, supplement with embedded server tests. For instance, Spring Boot can start the application on a random port with @SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT). Then an HTTP client sends requests through the running server and verifies broader integration behavior.

## 11. Choosing the right test level

You can use the following questions to select a tool:

| Goal | Suitable approach |
|---|---|
| Component reading init parameters or application attributes | MockServletContext directly |
| Servlet reading its own init parameters | MockServletConfig |
| Filter reading its own init parameters | MockFilterConfig |
| Filter processing headers, requests, or responses | MockHttpServletRequest and MockHttpServletResponse |
| Logic depending on session attributes | MockHttpSession |
| Spring MVC controllers, validation, and HTTP mappings | MockMvc or @WebMvcTest |
| Bean wiring in a web application context | WebApplicationContext with MockServletContext or an appropriate test slice |
| Behavior depending on servlet container or network | Embedded server/integration test |

A good test sets up only the environment needed for the question being tested. If the goal is reading an init parameter, MockServletContext is enough. If the goal is verifying that a controller accepts JSON, applies validation, and returns the exact status, MockMvc represents the MVC pipeline more completely. If the goal is checking how the application behaves after being deployed to a container, run the application on a real server.

## 12. Common pitfalls in usage

### 12.1. Confusing ServletContext with HttpSession

ServletContext has application-wide scope; HttpSession has single-user session scope. Putting user-specific information into ServletContext can leak state across sessions in a real application. Choose the right object based on the data's scope.

### 12.2. Using a mock context and expecting container auto-initialization

Creating MockServletContext does not automatically register filters, servlets, listeners, or run the full container lifecycle. The test must invoke the component or initialize a Spring web context according to the goal.

### 12.3. Setting init parameters too late

Set init parameters before initializing the servlet, filter, or Spring context that depends on that value. Changing them after the component has already read its configuration may leave the component holding the old value in its field.

### 12.4. Using machine-dependent resource paths

Absolute paths on a developer machine may not exist in CI. Use ResourceLoader and an explicit resource base path, preferring test fixture or classpath resources where appropriate.

### 12.5. Inspecting the response before the component finishes

If a component writes the body via a writer or output stream, finish executing the action before reading the response. For code that flushes or closes streams, ensure the test follows the same lifecycle the component uses.

### 12.6. Over-mocking Servlet API behavior

When using MockServletContext, rely on the mock class's default behavior and set only the required values. If you need to simulate a special behavior the mock does not support, you can use a dedicated test double or Mockito for a specific interface, while understanding that the test is checking a narrower contract.

### 12.7. Using Servlet mocks to conclude production integration

A test with MockHttpServletRequest does not prove the application accepts real requests through a connector. Scope your conclusions strictly to the test's boundary and add embedded-container tests for deployment requirements.

## 13. Test structure pattern with MockServletContext

For a component reading application-level configuration, you can start with this pattern:

~~~java
class WebFeatureTest {

    @Test
    void usesApplicationConfiguration() {
        // Arrange
        MockServletContext servletContext = new MockServletContext();
        servletContext.setInitParameter("feature.enabled", "true");
        servletContext.setAttribute("feature.mode", "test");

        WebFeature feature = new WebFeature();

        // Act
        feature.setServletContext(servletContext);
        boolean enabled = feature.isEnabled();

        // Assert
        assertTrue(enabled);
        assertEquals("test", feature.mode());
    }
}
~~~

Class and method names in the example illustrate an application component. When applying it, keep the three-part structure:

1. Create MockServletContext and configure the right init parameters, attributes, or resources.
2. Pass the context into the component via constructor, setter, or Spring WebApplicationContext depending on the actual mechanism.
3. Invoke the behavior under test and verify the observed outcome.

With mock request/response objects, the structure is similar: prepare the method, URI, headers, parameters, body, and session; invoke the servlet or filter; and finally check status, headers, and body.

## Conclusion

MockServletContext and Spring Test's mock Servlet objects help test web components in a lightweight, fast, and controllable way. Use MockServletContext for application-level configuration and state, MockServletConfig or MockFilterConfig for servlet/filter-specific configuration, mock request/response/session objects for HTTP interactions, and MockMvc for the Spring MVC pipeline. When behavior depends on a real container or network, integration tests with an embedded server are required to provide proper evidence.
