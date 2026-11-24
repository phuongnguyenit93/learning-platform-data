# Choosing Static Imports for Builders, Matchers, and Handlers

When writing tests with Spring MockMvc, a test often contains many short calls such as `get(...)`, `status()`, `jsonPath(...)`, and `print()`. These calls are static methods belonging to different classes in Spring Test. Java allows using **static imports** to invoke them directly without prefixing the class name.

Static imports keep the test focused on the request and expected outcome. However, importing the wrong class or pulling in too many static methods from multiple libraries makes test code harder to read and prone to method-name collisions. The best approach is to identify the role of the call first, then import the exact class that declares that method.

## 1. Static Imports in Java

A static import brings a static method or static field of a type into the simple-name scope of a Java file. Syntax:

~~~java
import static com.example.ClassName.methodName;
~~~

You can import all accessible static members of a class using `*`:

~~~java
import static com.example.ClassName.*;
~~~

For example, instead of writing:

~~~java
mockMvc.perform(
        MockMvcRequestBuilders.get("/api/books/42")
).andExpect(
        MockMvcResultMatchers.status().isOk()
);
~~~

you can write:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/books/42"))
        .andExpect(status().isOk());
~~~

A static import only changes how names are referenced in source code. It does not create extra objects, alter bean lifecycles, configure MockMvc, or change how requests execute.

## 2. Recognizing the Four Common API Groups

In MockMvc, distinguish the following groups:

| Role | Class Declaring Static Methods | Examples |
|---|---|---|
| Build MockMvc | `MockMvcBuilders` | `standaloneSetup(...)`, `webAppContextSetup(...)` |
| Build HTTP requests | `MockMvcRequestBuilders` | `get(...)`, `post(...)`, `multipart(...)`, `asyncDispatch(...)` |
| Assert request results | `MockMvcResultMatchers` | `status()`, `content()`, `jsonPath(...)`, `handler()` |
| Perform actions on results | `MockMvcResultHandlers` | `print()`, `log()` |

These classes reside in different packages. Looking at the role of a call helps pick the right package:

~~~text
MockMvcBuilders
    └── standaloneSetup / webAppContextSetup
            └── build() → MockMvc

MockMvcRequestBuilders
    └── get / post / put / delete / multipart
            └── builds requests for mockMvc.perform(...)

MockMvcResultMatchers
    └── status / content / jsonPath / view / handler
            └── ResultMatcher for andExpect(...)

MockMvcResultHandlers
    └── print / log
            └── ResultHandler for andDo(...)
~~~

Key point: `handler()` and `print()` are not the same kind of API. `handler()` is a matcher verifying which handler Spring selected; `print()` is a result handler printing details of the execution.

## 3. Static Imports for Builders

The builder creates a `MockMvc` instance with the appropriate test configuration.

The two common factory methods live in:

~~~java
org.springframework.test.web.servlet.setup.MockMvcBuilders
~~~

- `standaloneSetup(...)`: builds MockMvc from controllers passed directly. Fits when testing controllers in a minimal setup and declaring required supporting components yourself.
- `webAppContextSetup(...)`: builds MockMvc from a `WebApplicationContext`. Fits when using the MVC configuration and beans loaded in the web application context.

You can call them via the class name:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .build();
~~~

Or static-import the factory method:

~~~java
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

MockMvc mockMvc = standaloneSetup(new GreetingController()).build();
~~~

With a web application context:

~~~java
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

MockMvc mockMvc = webAppContextSetup(webApplicationContext).build();
~~~

Only import the factory method the test actually uses. If a test class uses multiple ways to build MockMvc or method names feel unclear, qualifying with `MockMvcBuilders` remains a clear choice.

In Spring Boot, tests using `@WebMvcTest` or `@SpringBootTest` combined with `@AutoConfigureMockMvc` typically receive `MockMvc` via injection. In that case, the test does not need to call a builder:

~~~java
@WebMvcTest(BookController.class)
class BookControllerTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

Do not add static imports for `standaloneSetup` or `webAppContextSetup` if the test does not call them directly.

## 4. Static Imports for Request Builders

Request-creating factory methods live in:

~~~java
org.springframework.test.web.servlet.request.MockMvcRequestBuilders
~~~

Common methods:

| Method | Purpose |
|---|---|
| `get(url, ...)` | Creates an HTTP GET |
| `post(url, ...)` | Creates an HTTP POST |
| `put(url, ...)` | Creates an HTTP PUT |
| `patch(url, ...)` | Creates an HTTP PATCH |
| `delete(url, ...)` | Creates an HTTP DELETE |
| `options(url, ...)` | Creates an HTTP OPTIONS |
| `head(url, ...)` | Creates an HTTP HEAD |
| `request(method, url, ...)` | Creates a request with the specified HTTP method |
| `multipart(url, ...)` | Creates a multipart request |
| `asyncDispatch(mvcResult)` | Creates the follow-up dispatch for an asynchronous result |

GET request example:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

mockMvc.perform(
        get("/api/books/{id}", 42L)
                .accept(MediaType.APPLICATION_JSON)
);
~~~

POST request example:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

mockMvc.perform(
        post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Spring Testing"
                        }
                        """)
);
~~~

These methods return a request builder, so you can chain additional details such as:

- `accept(...)`: media type accepted by the client.
- `contentType(...)`: data type in the request body.
- `content(...)`: body content.
- `param(...)`: query parameter or request parameter.
- `header(...)`: HTTP header.
- `cookie(...)`: cookie.
- `with(...)`: applies a request post-processor, such as configuring a user in Spring Security Test.

Example:

~~~java
mockMvc.perform(
        get("/api/books")
                .param("page", "0")
                .param("size", "20")
                .header("X-Request-Source", "test")
                .accept(MediaType.APPLICATION_JSON)
);
~~~

Methods such as `get(...)` and `post(...)` are static-imported because they build requests. Do not import them from `MockMvcBuilders`; the builder class is only responsible for building `MockMvc`.

## 5. Static Imports for Result Matchers

Matchers that verify request results typically come from:

~~~java
org.springframework.test.web.servlet.result.MockMvcResultMatchers
~~~

This group provides factory methods returning matchers compatible with `andExpect(...)`.

| Static Method | Verifies |
|---|---|
| `status()` | HTTP status |
| `content()` | Response body and content type |
| `jsonPath(expression)` | Value in JSON by JSONPath |
| `header()` | HTTP response headers |
| `cookie()` | Cookies in the response |
| `view()` | Selected view name |
| `model()` | Model passed to the view |
| `redirectedUrl(...)` | Redirect URL |
| `forwardedUrl(...)` | Forwarded URL |
| `flash()` | Flash attributes |
| `handler()` | Selected handler method or handler type |
| `request()` | Certain request attributes during processing, including async state |
| `xpath(...)` | XML content by XPath |

Example asserting HTTP status and JSON:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/books/{id}", 42L)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
        ))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.title").value("Spring Testing"));
~~~

Each matcher can check a distinct aspect. Chaining multiple `andExpect(...)` calls helps the test clearly express the HTTP contract the endpoint must satisfy.

Some other matchers:

~~~java
mockMvc.perform(get("/books/42"))
        .andExpect(status().isOk())
        .andExpect(header().exists("ETag"))
        .andExpect(cookie().exists("SESSION"));
~~~

For controllers returning views:

~~~java
mockMvc.perform(get("/books"))
        .andExpect(status().isOk())
        .andExpect(view().name("books/list"))
        .andExpect(model().attributeExists("books"));
~~~

For redirects or flash attributes:

~~~java
mockMvc.perform(post("/books")
                .param("title", "Spring Testing"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/books"))
        .andExpect(flash().attributeExists("message"));
~~~

### 5.1. Distinguishing MockMvcResultMatchers.handler() and MockMvcResultHandlers

The name `handler` is easily confused with result handlers. These two APIs serve different purposes:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/books/42"))
        .andExpect(handler().handlerType(BookController.class))
        .andExpect(handler().methodName("findById"))
        .andDo(print());
~~~

- `handler()` belongs to `MockMvcResultMatchers` and returns a `ResultMatcher`. It verifies the handler Spring MVC selected to handle the request, such as controller type or method name.
- `print()` belongs to `MockMvcResultHandlers` and returns a `ResultHandler`. It prints request, response, and execution details to aid diagnostics.

An easy mnemonic:

- `andExpect(...)` takes a condition to verify.
- `andDo(...)` takes an action to perform on the result.

Do not pass `handler()` as an argument to `andDo(...)`, and do not pass `print()` as an argument to `andExpect(...)`.

## 6. Static Imports for Result Handlers

Commonly used result handlers live in:

~~~java
org.springframework.test.web.servlet.result.MockMvcResultHandlers
~~~

Common methods:

- `print()`: prints details of the MockMvc execution to the default output.
- `print(outputStream)` or `print(writer)`: prints the result to the specified output stream or writer.
- `log()`: logs result details via Spring Test's logger.

Example:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/books"))
        .andDo(print())
        .andExpect(status().isOk());
~~~

`andDo(print())` is useful when inspecting requests, responses, headers, body, or exceptions while developing tests. Once tests stabilize, keep it only if log output is genuinely useful for the team; printing full responses in every test can bloat CI logs and obscure real failures.

A result handler does not replace assertions. A test calling `andDo(print())` without `andExpect(...)` has not yet verified that the endpoint returned the right result.

## 7. Complete Example with Explicit Static Imports

The following example uses MockMvc configured by Spring Boot via `@WebMvcTest`. The test checks status, content type, JSON data, and handler method.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsBookById() throws Exception {
        mockMvc.perform(
                        get("/api/books/{id}", 42L)
                                .accept(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(handler().handlerType(BookController.class))
                .andExpect(handler().methodName("findById"))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Spring Testing"));
    }
}
~~~

Imports fall into two groups:

- Regular imports for annotations, classes, and types such as `Test`, `WebMvcTest`, `MediaType`, `MockMvc`.
- Static imports for factory methods such as `get`, `print`, `content`, `handler`, `jsonPath`, `status`.

The class containing a static method does not need a regular import when only static imports are used. For instance, `import static ...MockMvcRequestBuilders.get` does not require adding `import ...MockMvcRequestBuilders`.

## 8. Async Testing: Combining Request Builders, Matchers, and Dispatch Builders

MockMvc can test asynchronously processed requests. In the first call, verify that the request started async processing and obtain `MvcResult`. Then use `asyncDispatch(...)` to simulate the follow-up dispatch and assert on the final response.

~~~java
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MvcResult pendingResult = mockMvc.perform(get("/api/reports"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(pendingResult))
        .andExpect(status().isOk());
~~~

Here:

- `get(...)` and `asyncDispatch(...)` are request builders, imported from `MockMvcRequestBuilders`.
- `request()` and `status()` are result matchers, imported from `MockMvcResultMatchers`.
- `andReturn()` returns `MvcResult`; this is an instance method on `ResultActions`, not a static method to import.

Distinguishing declaration sources properly prevents searching for a static import for a method that is actually an instance method on the result object.

## 9. Explicit Imports or Wildcard?

Two styles are common.

### 9.1. Importing Individual Methods

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Advantages:

- Looking at the imports shows exactly which APIs the test uses.
- Easy to spot whether a method comes from Spring Test or another library.
- Reduces the risk of simple-name collisions across static imports.
- Easy for IDEs and code reviews to track import changes.

The drawback is that the import list can grow long when a test uses many matchers.

### 9.2. Importing All Static Members of a Class

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.*;
~~~

The advantage is brevity and convenience when a test uses many methods from the same class. Some Spring examples also use this style.

The drawback is that readers must look up which class declares a called method; when adding static imports from Hamcrest, Mockito, AssertJ, or JUnit, colliding names can make calls ambiguous or hard to read.

A wildcard static import pulls in static members of only the specified class. It does not import static members of other classes in the package, nor does it import all classes in the package.

### 9.3. Project Selection Rules

A practical rule of thumb:

1. Prefer explicit imports in tests with few methods or multiple assertion libraries.
2. You may use a wildcard for a MockMvc class if the test uses many methods from that class and project conventions permit it.
3. Do not arbitrarily mix multiple wildcard static imports from different libraries.
4. Keep one consistent style within a module so readers can predict where methods come from.
5. Let the IDE organize imports, but review the result if the IDE collapses imports into wildcards past a configured threshold.

There is no Java rule forcing every project to use explicit imports. What matters is keeping import sources clear and avoiding name conflicts.

## 10. Resolving Name Collisions and Common Import Errors

### 10.1. Two Classes Declaring Same-Named Methods

Testing libraries contain many short static methods such as `is(...)`, `not(...)`, `any(...)`, or `assertThat(...)`. Importing the same name from multiple classes can cause the compiler to report an ambiguous call when it cannot pick one matching method.

For example, when you need a same-named method from two libraries, you can qualify one side with its full class name:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/books"))
        .andExpect(status().isOk());

org.hamcrest.MatcherAssert.assertThat(
        actualValue,
        org.hamcrest.Matchers.is(expectedValue)
);
~~~

In this example, `status()` is Spring MockMvc's matcher; `assertThat(...)` and `is(...)` are qualified through Hamcrest classes so their origin is unambiguous. In real tests, choose one consistent assertion style rather than mixing multiple libraries.

### 10.2. Importing the Wrong Package

Easy mistakes to make:

| Intended Call | Correct Static Import |
|---|---|
| `standaloneSetup(...)` | `org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup` |
| `get(...)` | `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get` |
| `status()` | `org.springframework.test.web.servlet.result.MockMvcResultMatchers.status` |
| `handler()` | `org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler` |
| `print()` | `org.springframework.test.web.servlet.result.MockMvcResultHandlers.print` |

Do not confuse `MockMvcBuilders` with `MockMvcRequestBuilders`: one class creates `MockMvc`, while the other creates HTTP requests for `MockMvc`.

### 10.3. Using Static Imports for Non-Static Methods

Not every method appearing in a MockMvc chain needs a static import. The following methods are called on objects:

- `mockMvc.perform(...)`: method of `MockMvc`.
- `andExpect(...)`, `andDo(...)`, `andReturn()`: methods of `ResultActions`.
- `build()`: method of the builder returned by `standaloneSetup(...)` or `webAppContextSetup(...)`.
- `accept(...)`, `contentType(...)`, `content(...)`, `param(...)`: methods on the request builder.
- `isOk()`, `isCreated()`, `isBadRequest()`: methods on the matcher object returned by `status()`.

Example:

~~~java
mockMvc.perform(get("/api/books"))
        .andExpect(status().isOk());
~~~

In this chain, only `get` and `status` are static factory methods typically imported. The remaining calls are instance methods.

### 10.4. Missing Dependencies

If the IDE cannot find the `org.springframework.test.web.servlet` package, the cause may be that the module lacks the Spring Test dependency or Spring Boot's test dependency. Static imports cannot supply missing libraries. Check the module's dependencies and test scope according to the active build configuration.

## 11. How to Determine Imports Yourself for Unfamiliar Methods

When encountering a method whose source is unfamiliar, follow this sequence:

1. Identify what the method creates: builder, request, matcher, or handler.
2. Use the IDE's `Go to Declaration` or `Quick Documentation` to inspect the declaring class.
3. Check the package of that class.
4. Choose an explicit import for the method you need.
5. If the method is an instance method, do not add a static import; inspect the object type before the dot.

Example:

| Call | Question to Ask | Conclusion |
|---|---|---|
| `get("/books")` | What builds the HTTP request? | `MockMvcRequestBuilders.get` |
| `status().isOk()` | What creates the status assertion condition? | `MockMvcResultMatchers.status` |
| `print()` | What acts on the result? | `MockMvcResultHandlers.print` |
| `standaloneSetup(controller)` | What builds MockMvc? | `MockMvcBuilders.standaloneSetup` |
| `andExpect(...)` | Which object is the method called on? | `ResultActions`, no static import |

## 12. Takeaways

- Builders that construct `MockMvc`: `MockMvcBuilders`.
- Request builders that create HTTP requests: `MockMvcRequestBuilders`.
- Result matchers that verify outcomes: `MockMvcResultMatchers`.
- Result handlers that perform actions on results: `MockMvcResultHandlers`.
- `handler()` is a matcher; `print()` is a handler.
- `andExpect(...)` accepts a `ResultMatcher`; `andDo(...)` accepts a `ResultHandler`.
- Static imports only shorten call names; they do not change MockMvc behavior.
- Explicit imports make origins easy to trace; wildcards save lines but require consistent use.

When reading or writing a MockMvc test, start from the method's role and then identify its declaring class. If a method name is ambiguous or collides, qualify it with its full class name to keep the test's meaning easy to understand.
