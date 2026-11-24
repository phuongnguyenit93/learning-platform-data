# Testing Session-Scoped Beans with MockHttpSession

## 1. Goal of the Test

A bean with **@SessionScope** has a separate target instance for each HTTP session. Requests belonging to the same session share that target; two different sessions receive two different targets. Therefore, a meaningful test must demonstrate both behaviors:

- State is retained when the same session sends multiple requests.
- State from one session does not appear in another session.

**MockHttpSession** belongs to Spring Test and simulates **HttpSession** in memory. You can pass the same **MockHttpSession** object into multiple MockMvc requests to test a bean's session-based lifecycle without starting a real servlet container.

## 2. How Session Scope Works

A bean can be declared with **@SessionScope** on a component:

~~~java
@Component
@SessionScope
public class UserPreferences {
    // State specific to an HTTP session
}
~~~

Or declared on a **@Bean** method:

~~~java
@Bean
@SessionScope
Cart cart() {
    return new Cart();
}
~~~

**@SessionScope** is shorthand for **WebApplicationContext.SCOPE_SESSION** and defaults to a class-based scoped proxy. The proxy can be injected into a singleton bean such as a controller. When an active request calls a method on the proxy, Spring looks up the corresponding target in the current HTTP session; if the session does not yet have a target, Spring creates one and stores it in the session.

This creates three characteristics that need testing:

1. A controller can hold the proxy for the lifetime of the application context.
2. Two requests with the same **HttpSession** access the same target bean.
3. Two requests with different **HttpSession** instances access different target beans.

The target of a session-scoped bean can only be resolved when an active request context exists. If you call the proxy from plain test code outside a request, Spring does not know which session is current and may report that the scope is not active. Using MockMvc creates a request context during dispatch.

**@SessionScope** creates a class proxy by default, so the proxied class should not be **final**. If you want to use a JDK interface proxy, you can declare **@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)** and inject via the corresponding interface.

### Distinguishing from @SessionAttributes

**@SessionScope** manages the lifecycle of a Spring bean per HTTP session. **@SessionAttributes** is a Spring MVC mechanism for retaining controller model attributes across multiple requests in a workflow.

Both mechanisms use the HTTP session but serve different purposes. This article tests beans declared with **@SessionScope**; if the goal is to test model attributes stored by **@SessionAttributes**, you must test the controller flow and those model attributes.

## 3. MockHttpSession and MockMvc

**MockHttpSession** is a simulated implementation of **HttpSession**. It supports setting, reading, and removing session attributes, and can be reused across multiple requests.

The most important point when testing session scope with MockMvc is passing **the exact same session object** to each request:

~~~java
MockHttpSession session = new MockHttpSession();

mockMvc.perform(post("/cart/items/book").session(session));
mockMvc.perform(get("/cart/items").session(session));
~~~

MockMvc creates a new mock request on each **perform** call. Calling **.session(session)** attaches the same **HttpSession** object to that new request. Because Spring stores the session-scoped bean's target in the session, the second request accesses the target already created during the first request.

Do not create a **new MockHttpSession()** for every request if the goal is to verify retained state. Each new session represents a different user or working session.

Also distinguish two ways of setting up data:

- **.session(session)** passes a specific session so it can be reused across multiple requests.
- **.sessionAttr("key", value)** sets a session attribute for a request. This is convenient for preparing input data, but by itself does not prove that multiple requests use the same session object.

**MockHttpSession** simulates the server-side session in memory. It does not fully simulate browser cookies, network exchanges, real timeouts, or the session storage behavior of a real servlet container.

## 4. Example Application to Test

The example below builds a simple shopping cart. Each HTTP session has its own **Cart**. The controller is a singleton, yet receives a scoped proxy of **Cart**.

### Cart Bean

~~~java
import java.util.ArrayList;
import java.util.List;

public class Cart {

    private final List<String> items = new ArrayList<>();

    public void add(String itemId) {
        items.add(itemId);
    }

    public List<String> items() {
        return List.copyOf(items);
    }
}
~~~

### Controller

~~~java
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/cart")
public class CartController {

    private final Cart cart;

    public CartController(Cart cart) {
        this.cart = cart;
    }

    @PostMapping("/items/{id}")
    public ResponseEntity<Void> add(@PathVariable String id) {
        cart.add(id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/items")
    public List<String> items() {
        return cart.items();
    }
}
~~~

### WebApplicationContext Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.context.annotation.SessionScope;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class WebConfig {

    @Bean
    @SessionScope
    Cart cart() {
        return new Cart();
    }

    @Bean
    CartController cartController(Cart cart) {
        return new CartController(cart);
    }
}
~~~

The **cart()** method creates a session-scoped bean. When Spring creates **CartController**, the injected dependency is a scoped proxy. The real **Cart** target is retrieved according to the session of the request being processed.

In an example returning JSON, the application needs a JSON message converter, typically provided by Jackson. With Spring Boot, the **spring-boot-starter-web** dependency usually provides the required configuration.

## 5. Testing with MockMvc and MockHttpSession

This is the right approach when you want to verify **WebApplicationContext** wiring, controller mappings, and session scope behavior together in a request flow.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebConfig.class)
class CartSessionScopeTest {

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
    void shouldKeepCartStateAcrossRequestsInTheSameSession() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mockMvc.perform(post("/cart/items/{id}", "book")
                        .session(session))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/cart/items")
                        .session(session))
                .andExpect(status().isOk())
                .andExpect(content().json("[\"book\"]"));
    }

    @Test
    void shouldIsolateCartStateBetweenDifferentSessions() throws Exception {
        MockHttpSession firstSession = new MockHttpSession();
        MockHttpSession secondSession = new MockHttpSession();

        mockMvc.perform(post("/cart/items/{id}", "book")
                        .session(firstSession))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/cart/items")
                        .session(firstSession))
                .andExpect(status().isOk())
                .andExpect(content().json("[\"book\"]"));

        mockMvc.perform(get("/cart/items")
                        .session(secondSession))
                .andExpect(status().isOk())
                .andExpect(content().json("[]"));
    }
}
~~~

The first test sends a request to add an item and then sends a request to read the cart using the same **MockHttpSession**. The result must contain the added item. This proves that the target bean is retained across requests within the same session.

The second test creates two independent sessions. The request to add an item uses only **firstSession**. When reading with **secondSession**, the cart must be empty; when reading again with **firstSession**, the item is still present. These two assertions verify both isolation and state retention.

**@WebAppConfiguration** instructs Spring Test to create a **WebApplicationContext**. This is the proper environment for web scopes. **MockMvcBuilders.webAppContextSetup(...)** uses that context to configure MVC components and dispatch requests. If only a regular **ApplicationContext** is used, web scopes may not be registered properly.

### If the Session Is Created by the Application on the First Request

You do not necessarily have to create the session before the test. If the first request creates a session itself, you can extract the session from the request afterward:

~~~java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

MvcResult result = mockMvc.perform(post("/cart/items/{id}", "book"))
        .andExpect(status().isNoContent())
        .andReturn();

MockHttpSession session =
        (MockHttpSession) result.getRequest().getSession(false);
~~~

Then pass **session** to subsequent requests using **.session(session)**. Check that session is not **null** before using it if the application is not guaranteed to create a session on the first request.

## 6. Testing the Bean Directly Without Dispatching a Controller

In some cases, you only need to verify target resolution for a session-scoped bean. You can then combine **MockHttpSession**, **MockHttpServletRequest**, and **RequestContextHolder**.

The following example assumes the test has loaded a **WebApplicationContext** declaring a **Cart** bean with **@SessionScope** as configured above:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import static org.assertj.core.api.Assertions.assertThat;

class CartScopeUnitTest {

    @Autowired
    private Cart cart; // This is the scoped proxy injected by Spring.

    @Test
    void shouldResolveTheSameTargetForRequestsInOneSession() {
        MockHttpSession session = new MockHttpSession();

        try {
            ServletRequestAttributes firstRequest = bind(session);
            try {
                cart.add("book");
            } finally {
                firstRequest.requestCompleted();
            }

            ServletRequestAttributes secondRequest = bind(session);
            try {
                assertThat(cart.items()).containsExactly("book");
            } finally {
                secondRequest.requestCompleted();
            }
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }

    private ServletRequestAttributes bind(MockHttpSession session) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setSession(session);

        ServletRequestAttributes attributes =
                new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(attributes);
        return attributes;
    }
}
~~~

Here, each call to **bind(session)** creates a new mock request while attaching the same **MockHttpSession**. **RequestContextHolder** binds the request attributes to the current thread so the scoped proxy knows which session is being used. The **finally** blocks call **requestCompleted()** and **resetRequestAttributes()** to clean up the request context even if an assertion fails.

This approach tests scope resolution directly and is useful for a narrow bean-level test. It does not test controller mappings, argument resolvers, message converters, or the full MVC dispatch process. When you need to confirm that the web flow behaves as in the real application, prefer the MockMvc test in the previous section.

## 7. Common Errors

| Symptom | Common cause | How to resolve |
|---|---|---|
| Calling a session-scoped bean reports that scope is not active | Accessing the scoped proxy without a request context | Execute through MockMvc or bind **ServletRequestAttributes** in a direct test |
| State disappears between two requests | Each request uses a new **MockHttpSession** | Create one session and pass it again via **.session(session)** |
| Bean is not resolved properly in test | Context is not a **WebApplicationContext** | Use **@WebAppConfiguration** along with **@ContextConfiguration** |
| Controller does not receive the right session-scoped target | Bean lacks a scoped proxy when injected into a singleton | Use **@SessionScope**, or declare **@Scope** with an appropriate **proxyMode** |
| Test verifies a session attribute but does not prove bean scope | Only using **.sessionAttr(...)** or inspecting a key directly in the session | Send multiple requests with the same session and verify the bean's public behavior |
| Test passes yet different users still share data | Application accidentally stores state in another singleton bean or static field | Check where state is stored and add assertions with two separate sessions |

Do not rely on the internal attribute name Spring uses to store the scoped target in **HttpSession**. That name is an implementation detail of scoped proxies. Verify behavior through controllers or the bean's public API.

Also avoid calling a method on a session-scoped proxy inside **@BeforeEach** before a request context exists. Injecting the proxy into the test works without error, yet the target is only resolved when a method is invoked. Perform such calls inside a MockMvc request or inside a region where **RequestContextHolder** is bound.

One session can be used concurrently by multiple requests. Session scope guarantees the target is tied to the session, but does not automatically make mutable state inside the bean thread-safe. If multiple concurrent requests can update the same **Cart** or **UserPreferences**, the bean design still needs appropriate concurrency handling.

## 8. Choosing the Appropriate Testing Approach

| Goal | Approach |
|---|---|
| Verify state persists across multiple requests in the same session | MockMvc and reuse **.session(session)** |
| Verify data of two sessions is isolated | Create two different **MockHttpSession** instances |
| Prepare a session attribute for a request | **.sessionAttr("key", value)** or **session.setAttribute(...)** |
| Verify target bean resolution in isolation | **MockHttpServletRequest** + **ServletRequestAttributes** + **RequestContextHolder** |
| Verify cookies, timeouts, and real servlet container behavior | Integration test running with an embedded or deployed servlet container |

With Spring Boot, you can use **@SpringBootTest** combined with **@AutoConfigureMockMvc**, inject **MockMvc** directly, and apply the same principle: create one **MockHttpSession** and pass that session to every request that should belong to the same session.

A good session scope test always makes clear which session is used in each request. When the same session retains state and a different session does not see that state, the test has verified the two most important properties of **@SessionScope**.

