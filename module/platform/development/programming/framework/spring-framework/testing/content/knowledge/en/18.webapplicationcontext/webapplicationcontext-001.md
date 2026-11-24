# `@WebAppConfiguration` and the Web Resource Root Directory

In Spring Test, `@WebAppConfiguration` indicates that a test requires a `WebApplicationContext` tied to a Servlet environment. This annotation enables Spring to create a `MockServletContext` so that web beans, controllers, resource resolvers, and code that uses `ServletContext` can run in tests. The value of the annotation specifies the web resource root directory used to create that servlet context.

The web resource root directory is the starting point for resolving paths such as `/WEB-INF/views/home.html` or `/static/css/site.css`. It is independent of where the Spring configuration files declared in `@ContextConfiguration` are stored. Understanding this distinction helps avoid errors where views, static files, or resources read through `ServletContext` cannot be found in integration tests.

## 1. Why Is `@WebAppConfiguration` Needed?

A regular `ApplicationContext` manages Spring beans but is not necessarily tied to a web application environment. In a Spring MVC application, many components require a `WebApplicationContext`, which is a type of application context linked to a `ServletContext` and supporting web features such as request scope, session scope, and servlet-context-relative resources.

When testing those components, Spring Test needs to provide an appropriate web environment. `@WebAppConfiguration` marks the test class so that the TestContext Framework loads a web application context and creates a mock servlet context. For example:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebTestConfig.class)
class WebApplicationContextTest {
    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

In the example above:

- `@ExtendWith(SpringExtension.class)` integrates the Spring TestContext Framework with JUnit Jupiter.
- `@ContextConfiguration` specifies the bean configuration to load for the test.
- `@WebAppConfiguration` requests a web environment and a `MockServletContext`.
- The injected `WebApplicationContext` is the web context created by Spring Test for the test class.

With JUnit 4, `@RunWith(SpringRunner.class)` can be used instead of `@ExtendWith(SpringExtension.class)`. `@WebAppConfiguration` is typically used together with `@ContextConfiguration` or `@ContextHierarchy` to specify the configuration for the context.

## 2. What Is the Web Resource Root Directory?

The web resource root directory represents the root of the web application in `ServletContext`. Suppose the directory structure is as follows:

```text
src/test/webapp/
├── index.html
├── static/
│   ├── css/
│   │   └── site.css
│   └── images/
│       └── logo.png
└── WEB-INF/
    └── views/
        └── home.html
```

If `src/test/webapp` is chosen as the resource base path, resource paths in the servlet context are resolved from that directory:

| Path in servlet context | Corresponding file in test fixture |
| --- | --- |
| `/index.html` | `src/test/webapp/index.html` |
| `/static/css/site.css` | `src/test/webapp/static/css/site.css` |
| `/static/images/logo.png` | `src/test/webapp/static/images/logo.png` |
| `/WEB-INF/views/home.html` | `src/test/webapp/WEB-INF/views/home.html` |

Paths starting with `/` in `ServletContext` APIs are interpreted relative to the servlet context root, not the current working directory of the process and not the directory containing the Spring configuration files.

The `WEB-INF` directory follows a special Servlet convention: its contents are not served directly as public resources via regular URLs. However, the application and Spring can read files inside it to resolve views or load configuration. Therefore, a test can verify the existence of `/WEB-INF/views/home.html` through `ServletContext` or `Resource`.

## 3. Default Value and Choosing the Resource Base Path

If no value is passed, `@WebAppConfiguration` uses the default resource base path `file:src/main/webapp`:

```java
@WebAppConfiguration
@ContextConfiguration(classes = WebTestConfig.class)
class DefaultWebRootTest {
}
```

A different directory can be specified using the `value` attribute:

```java
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(classes = WebTestConfig.class)
class TestWebRootTest {
}
```

In this case, Spring uses `src/test/webapp` as the resource root of `MockServletContext`. This approach is useful when tests need a dedicated set of resources and should avoid depending on web content packaged for the real runtime environment.

Spring also supports a resource base path on the classpath:

```java
@WebAppConfiguration("classpath:test-web-resources")
@ContextConfiguration(classes = WebTestConfig.class)
class ClasspathWebRootTest {
}
```

With the configuration above, the corresponding resource directory can be placed at `src/test/resources/test-web-resources`:

```text
src/test/resources/
└── test-web-resources/
    ├── index.html
    └── WEB-INF/
        └── views/
            └── home.html
```

The two common path forms have different meanings:

| Prefix | Resource source | When to use |
| --- | --- | --- |
| `file:` | File system | Tests need to directly use a web directory in the workspace |
| `classpath:` | Resources available on the classpath | Tests need fixtures managed alongside test resources and packaged on the classpath |

For relative `file:` paths such as `file:src/test/webapp`, the location is resolved relative to the working directory of the test runner process. Therefore, ensure tests are run with the expected working directory or configure a path suitable for the project's build setup. With `classpath:`, ensure the resource directory is included on the test classpath.

The `@WebAppConfiguration` value is a resource location, not a URL that a browser accesses. Nor is it the location of a bean configuration file. Do not pass the path to `dispatcher-servlet.xml` as the resource base path; that configuration file belongs to `@ContextConfiguration`.

## 4. Distinguishing `@WebAppConfiguration` and `@ContextConfiguration`

These two annotations address two separate concerns and often appear together:

| Annotation | Responsibility | Example |
| --- | --- | --- |
| `@WebAppConfiguration` | Selects the web environment and the resource root of the mock `ServletContext` | `file:src/test/webapp` |
| `@ContextConfiguration` | Selects the Spring configuration used to create beans and the application context | `WebTestConfig.class` or `classpath:application-context.xml` |

Example with Java configuration:

```java
@Configuration
@EnableWebMvc
@ComponentScan(basePackages = "com.example.web")
class WebTestConfig {
}
```

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(classes = WebTestConfig.class)
class ProductControllerWebTest {
    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

Example with XML configuration:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(locations = "classpath:spring/web-test-context.xml")
class XmlConfiguredWebTest {
    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

In the XML example, `web-test-context.xml` is the Spring configuration loaded from the classpath. The `src/test/webapp` directory remains the resource root of the servlet context. Changing one value does not automatically change the other.

## 5. How Is `MockServletContext` Created and Used?

When the Spring TestContext Framework processes a test class annotated with `@WebAppConfiguration`, the framework creates a `MockServletContext` based on the resource base path. The web application context is loaded with that servlet context so beans can access the web environment during testing.

`MockServletContext` implements the `ServletContext` API in a simulated form. It supports common testing operations such as retrieving resources, obtaining real paths, accessing context attributes, and providing basic servlet environment information. It does not start Tomcat, Jetty, or a real servlet container.

The servlet context and resource reading can be tested as follows:

```java
import jakarta.servlet.ServletContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.Resource;
import org.springframework.mock.web.MockServletContext;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.web.context.WebApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(classes = WebTestConfig.class)
class WebRootResourceTest {
    @Autowired
    private WebApplicationContext webApplicationContext;

    @Test
    void createsMockServletContextWithConfiguredRoot() throws Exception {
        ServletContext servletContext = webApplicationContext.getServletContext();

        assertThat(servletContext).isInstanceOf(MockServletContext.class);
        assertThat(servletContext.getResource("/index.html")).isNotNull();
    }

    @Test
    void resolvesResourceRelativeToWebRoot() {
        Resource view = webApplicationContext.getResource(
                "/WEB-INF/views/home.html");

        assertThat(view.exists()).isTrue();
    }
}
```

The files verified in the example must actually exist under `src/test/webapp`. `ServletContext.getResource()` returns a URL or `null` if the resource is not found; `WebApplicationContext.getResource()` returns a `Resource` object that can be checked with `exists()`. Paths with a leading `/` are resolved from the servlet context root.

The example imports use `jakarta.servlet`, which fits Spring Framework 6 and Spring Boot 3. For Spring Framework 5 or Spring Boot 2 projects, the Servlet API typically belongs to the `javax.servlet` namespace; use imports matching the project's version.

## 6. Inspecting Resources Through `ResourceLoader`

`WebApplicationContext` is also a `ResourceLoader`. Therefore, tests can use `getResource()` to inspect view files, templates, or other resources in the web root without manually assembling file system paths.

```java
@Test
void canReadAViewTemplate() throws IOException {
    Resource template = webApplicationContext.getResource(
            "/WEB-INF/views/home.html");

    assertThat(template.exists()).isTrue();
    try (InputStream input = template.getInputStream()) {
        String content = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        assertThat(content).contains("Home");
    }
}
```

To inspect file contents, the test needs to import `java.io.InputStream`, `java.io.IOException`, and `java.nio.charset.StandardCharsets`. For projects using Java versions prior to 9, the stream can be read using another approach instead of `readAllBytes()`.

When using `ServletContextResource` directly, the path is also resolved relative to the servlet context root:

```java
Resource css = new ServletContextResource(
        webApplicationContext.getServletContext(),
        "/static/css/site.css");

assertThat(css.exists()).isTrue();
```

`ServletContextResource` is useful when code needs to state explicitly that a resource is retrieved from the servlet context. Using `webApplicationContext.getResource()` is usually more concise and keeps tests less coupled to a concrete implementation class.

## 7. Combining with `MockMvc`

`@WebAppConfiguration` is commonly used when testing Spring MVC together with `MockMvc`. `MockMvc` sends mock requests through the Spring MVC infrastructure loaded in `WebApplicationContext`, allowing tests to verify routing, controllers, filters, and HTTP results without opening a network port or starting a real servlet container.

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(classes = WebTestConfig.class)
class HomeControllerTest {
    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void returnsHomePage() throws Exception {
        mockMvc.perform(get("/home"))
                .andExpect(status().isOk());
    }
}
```

This test assumes `WebTestConfig` registers the controller and required MVC components, and that the application has a `/home` endpoint. Commonly used imports include `MockMvc`, `MockMvcBuilders`, `BeforeEach`, `get`, and `status` from their respective Spring Test and MockMvc packages.

The resource base path and request URL are two distinct concepts. For example, `src/test/webapp/static/css/site.css` has the servlet-context path `/static/css/site.css`. For a browser or MockMvc to access that file via a URL such as `/assets/site.css`, the application also needs a resource handler mapping the URL to the resource directory:

```java
@Configuration
@EnableWebMvc
class WebTestConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("/static/");
    }
}
```

With the configuration above, a request to `/assets/css/site.css` is mapped to the resource `/static/css/site.css` in the servlet context. Simply setting `@WebAppConfiguration("file:src/test/webapp")` does not automatically create URL mappings for static resources; mapping remains part of Spring MVC configuration.

## 8. When an Application Has a Root Context and a DispatcherServlet Context

A traditional Spring MVC application may use two context tiers: a root context containing shared beans such as services and repositories, and a `DispatcherServlet` context containing controllers, handler mappings, and view resolvers. When this structure needs to be replicated in an integration test, Spring Test supports `@ContextHierarchy`.

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextHierarchy({
    @ContextConfiguration(name = "root", locations = "classpath:spring/root-context.xml"),
    @ContextConfiguration(name = "dispatcher", locations = "classpath:spring/dispatcher-context.xml")
})
class HierarchicalWebApplicationTest {
    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

Both configurations are placed in the same context hierarchy: the `dispatcher` context is the child context and can use beans from the `root` context. `@WebAppConfiguration` provides the servlet environment for the web context. Use a hierarchy only when the application genuinely has a parent-child boundary; an application with a single simple web context does not need this complex configuration.

When testing a hierarchy, pay attention to which context contains the bean under test. Controllers usually reside in the `DispatcherServlet` context, while shared services usually reside in the root context. Injection from a child context can see beans in the parent context, whereas the parent context cannot see beans declared only in the child context.

## 9. Using `@WebAppConfiguration` in Spring Boot Projects

In traditional Spring Framework tests, `@WebAppConfiguration` combined with `@ContextConfiguration` is the direct way to create a `WebApplicationContext` backed by `MockServletContext`.

With Spring Boot, `@SpringBootTest` can automatically create a web application context and a mock servlet environment when the application is a web application and `webEnvironment` is set to `MOCK` (which is also the default value of `@SpringBootTest`). When MVC testing is needed, it can be combined with `@AutoConfigureMockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class HomeControllerIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void servesHomeEndpoint() throws Exception {
        mockMvc.perform(get("/home"))
                .andExpect(status().isOk());
    }
}
```

In this Spring Boot approach, there is no need to add `@WebAppConfiguration` just to obtain a `MockServletContext`; Boot already configures the web context according to `webEnvironment`. If the goal is to verify behavior when running on a real servlet container, use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` and send HTTP requests to the server started for the test. That is a different testing scope from `MockMvc` and `@WebAppConfiguration`.

## 10. Common Errors and How to Resolve Them

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Unable to inject `WebApplicationContext` | The test only loads a regular context or lacks web configuration | Use `@WebAppConfiguration` with an appropriate context configuration |
| `ServletContext.getResource()` returns `null` | The file is not under the resource base path or the path is wrong | Check the directory structure and the path relative to the web root |
| `Resource.exists()` returns `false` | The `file:` or `classpath:` prefix points to the wrong location | Check the working directory or the test classpath |
| Spring configuration file loads but views are not found | Confusing `@ContextConfiguration` with the resource base path | Place configuration files in `@ContextConfiguration`, and the web directory in `@WebAppConfiguration` |
| Static file exists but requests return 404 | No resource handler configured or URL mapping does not match | Check `addResourceHandlers` and the request URL |
| Test passes locally but fails in CI | Relying on relative file paths with different working directories | Use a stable resource path or classpath resources |
| Expecting JSPs to render as on a server, but the test cannot do so | `MockServletContext` does not compile and execute JSPs like a real servlet container | Use integration tests with a real container for JSP/deployment testing |
| Test needs Servlet APIs, but the context lacks the expected beans | The test configuration does not create a web application context | Check `@WebAppConfiguration`, the context loader, and the web configuration |

A common mistake is specifying `@WebAppConfiguration("file:src/test/webapp/WEB-INF")` while code reads `/WEB-INF/views/home.html`. In that case, paths are resolved from the chosen `WEB-INF` root directory, leading to lookups in the wrong location. If servlet-context paths should start with `/WEB-INF/...`, the resource base path must be the parent directory containing `WEB-INF`, such as `file:src/test/webapp`.

Another mistake is assuming the resource base path is solely a public static resource directory. In reality, it represents the entire web root. Directories like `WEB-INF`, `META-INF`, or `static` are simply subdirectories within the application structure; how each resource is accessed depends on the Servlet API and Spring MVC configuration.

## 11. Principles for Organizing Test Web Resources

1. Choose a resource base path that accurately reflects the resource structure the test needs to verify. Use `src/main/webapp` to test the application's web root; use `src/test/webapp` when dedicated test fixtures are needed.
2. Use the `file:` prefix for directories on the file system and `classpath:` for resources placed on the classpath. Ensure the corresponding path actually exists.
3. Keep `@WebAppConfiguration` and `@ContextConfiguration` focused on their own responsibilities: one selects the web root, while the other loads the Spring configuration.
4. Use `WebApplicationContext.getResource()` or `ServletContext.getResource()` to inspect resources according to servlet context semantics.
5. When testing URLs for static files, configure and verify resource handlers separately. A file existing in the web root does not automatically guarantee a URL will serve it.
6. Use `MockMvc` for Spring MVC testing that does not require a real server; use tests with a real server/container when deployment, JSPs, or container-dependent behavior must be verified.
7. Keep tests independent of absolute paths on a local machine so they run reliably in CI.

`@WebAppConfiguration` enables Spring Test to reproduce the Servlet environment needed for an integration test. When the resource base path is chosen properly and kept separate from bean configuration locations, tests can verify resource resolution, `WebApplicationContext` behavior, and MVC request handling in a controllable simulated environment.
