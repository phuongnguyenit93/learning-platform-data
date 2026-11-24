# Choosing a Consistent Assertion Style Across the Test Suite

**Context:** Spring Framework Testing → MockMvcTester.

When testing Spring MVC, a request can be verified in multiple ways. Traditional Spring MVC Test uses **MockMvc**, **ResultActions**, and **ResultMatcher** to check results. Starting with Spring Framework 6.2, **MockMvcTester** provides an AssertJ-based assertion API with a more fluent writing style.

Both styles can verify the same HTTP contract. The main differences lie in how expectations are expressed, how assertions are composed, and how the test suite is organized. A project should choose a primary style suited to its Spring version, existing libraries, and team needs, and then apply it consistently within each test scope.

Choosing consistently does not mean every test across the entire repository must use the exact same API. An older module may continue using ResultMatcher; a newer module may choose MockMvcTester. What should be avoided is each test mixing multiple assertion styles without a clear reason, forcing readers to constantly switch mental models and making shared helpers harder to maintain.

## 1. Two Assertion Styles in Spring MVC Test

### 1.1. MockMvc with ResultMatcher

MockMvc is the foundational API for executing simulated requests through Spring MVC. The **perform** method takes a request builder and returns **ResultActions**.

Traditional tests typically chain matchers using **andExpect**:

~~~java
mockMvc.perform(get("/orders/42")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"));
~~~

Matchers are provided in groups:

- **status()**: checks the HTTP status.
- **header()**: checks response headers.
- **content()**: checks content type, encoding, or body content.
- **jsonPath()**: accesses JSON data via JSONPath expressions.
- **xpath()**: accesses XML.
- **view()** and **model()**: check the view name and model of an MVC controller.
- **flash()** and **redirectedUrl()**: check redirects and flash attributes.
- **request()**: checks request states, such as async.

This style clearly states that the request is executed and then each condition is verified. Spring's matchers produce per-condition failure messages, making them a good fit for test suites that have used MockMvc for years.

### 1.2. MockMvcTester with AssertJ

**MockMvcTester** was introduced in Spring Framework 6.2. This API provides an AssertJ-style way to send requests and verify results.

Equivalent example:

~~~java
MockMvcTester mvcTester = MockMvcTester.create(mockMvc);

assertThat(mvcTester.get().uri("/orders/42")
                .accept(MediaType.APPLICATION_JSON))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.id")
        .isEqualTo(42);
~~~

In this example:

- **mvcTester.get()** creates a GET request.
- **uri(...)** specifies the path.
- **accept(...)** specifies the media type accepted by the client.
- **assertThat(...)** starts the AssertJ assertion chain on the MVC result.
- **hasStatusOk()** confirms HTTP 200.
- **bodyJson()** accesses the response body as JSON.
- **extractingPath(...)** retrieves a value by JSONPath for further assertions.

This style fits well when the team is familiar with AssertJ and wants HTTP assertions phrased similarly to assertions on objects, collections, or exceptions in other Java tests.

### 1.3. Quick Comparison

| Criterion | MockMvc + ResultMatcher | MockMvcTester + AssertJ |
|---|---|---|
| Request execution API | MockMvc.perform(...) | MockMvcTester.get()/post()/... |
| Verification style | andExpect(matcher) | assertThat(...).hasStatus... |
| Assertion library | Spring ResultMatcher | AssertJ |
| Organization style | Chain of Spring matcher groups | Fluent assertion chain |
| Spring version | Available in earlier Spring MVC Test versions | Spring Framework 6.2 or later |
| Well suited for | Existing suites, specialized matchers, legacy codebases | New suites, AssertJ-using teams, fluent assertions |
| Reuse | Custom ResultMatcher and helpers | AssertJ assertions/helpers and fluent structures |

Both approaches use the Spring MVC Test infrastructure. MockMvcTester does not replace DispatcherServlet, controllers, converters, validators, or MVC configuration; it changes the interface for writing requests and assertions.

## 2. Prerequisites for Using MockMvcTester

MockMvcTester is part of Spring Test and was added in Spring Framework 6.2. Using it requires a compatible Spring version and AssertJ on the test classpath.

Gradle example:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.assertj:assertj-core")
}
~~~

The actual versions must be managed in sync with the Spring Framework version used by the project. If using Spring Boot dependency management, let the BOM or plugin manage compatible versions instead of declaring a spring-test version that differs from the rest of the Spring modules.

If the project uses a Spring Framework version lower than 6.2, MockMvcTester is not available yet. In that case, continue using MockMvc with ResultMatcher or plan a framework upgrade before adopting the new API. Do not add a homegrown wrapper mimicking MockMvcTester just for shorter syntax.

### 2.1. Creating MockMvcTester from an Existing MockMvc

When MockMvc is already configured via standalone setup or a web application context, you can create MockMvcTester from that instance:

~~~java
MockMvcTester mvcTester = MockMvcTester.create(mockMvc);
~~~

This preserves how controllers, filters, ControllerAdvice, converters, Validator, and other MVC components are set up. Only the layer expressing requests and assertions changes.

Example with Spring TestContext:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = MvcTestConfig.class)
class OrderControllerTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    MockMvcTester mvcTester;

    @BeforeEach
    void setUp() {
        MockMvc mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();

        mvcTester = MockMvcTester.create(mockMvc);
    }
}
~~~

This approach is useful when you want to adopt MockMvcTester without altering existing MVC configuration. Beans in the WebApplicationContext remain the configuration source for requests.

## 3. Writing the Same Test in Both Styles

Suppose an API has a GET endpoint returning an order:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable long id) {
        return new OrderResponse(id, "PAID");
    }
}

record OrderResponse(long id, String status) {}
~~~

### 3.1. Version Using ResultMatcher

~~~java
@Test
void returnsOrderDetails() throws Exception {
    mockMvc.perform(get("/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("PAID"));
}
~~~

Each condition is expressed as a matcher. When a condition is not met, the failure message points out the failing matcher and the actual value if the matcher supports displaying it.

### 3.2. Version Using MockMvcTester

~~~java
@Test
void returnsOrderDetails() {
    assertThat(mvcTester.get().uri("/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .hasStatusOk()
            .bodyJson()
            .extractingPath("$.id")
            .isEqualTo(42);
}
~~~

Another field can be verified in a separate assertion if needed:

~~~java
@Test
void returnsPaidOrder() {
    assertThat(mvcTester.get().uri("/orders/42"))
            .hasStatusOk()
            .bodyJson()
            .extractingPath("$.status")
            .isEqualTo("PAID");
}
~~~

The snippets above illustrate expression style. A real test should pick a set of conditions sufficient to verify the endpoint contract. Do not repeat the same request just to verify each field individually when important conditions can be checked in the same chain or a readable helper.

### 3.3. Verifying Requests with a Body

With traditional MockMvc:

~~~java
@Test
void createsOrder() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": "An"
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.customerName").value("An"));
}
~~~

With MockMvcTester:

~~~java
@Test
void createsOrder() {
    assertThat(mvcTester.post().uri("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": "An"
                            }
                            """))
            .hasStatus(HttpStatus.CREATED)
            .bodyJson()
            .extractingPath("$.customerName")
            .isEqualTo("An");
}
~~~

MockMvcTester's request builder provides ways to declare the method, URI, headers, parameters, content type, and body matching the request to send. What matters is that test data and HTTP expectations remain unchanged when moving from one style to the other.

## 4. Choosing a Style Based on Test Suite Characteristics

There is no single best assertion style for every repository. Choose based on concrete factors.

### 4.1. Keep ResultMatcher When the Test Suite Is Already Stable

If the project has many tests using:

- Custom ResultMatchers.
- Spring matchers for model, view, flash attributes, and redirects.
- Async requests with specialized assertions.
- Helpers already widely used by the development team.

Then continuing with ResultMatcher is a reasonable choice. Changing syntax does not automatically increase test reliability. If a test suite is already clear, maintainable, and produces good error messages, only change when there is a concrete benefit.

### 4.2. Choose MockMvcTester for New Tests When Suitable

MockMvcTester is a good fit when:

- The project uses Spring Framework 6.2 or later.
- AssertJ is already the primary assertion library.
- Tests mainly verify status, headers, content, and JSON responses.
- The team wants a consistent fluent style across MVC tests and other Java tests.
- Team members are already familiar with how AssertJ assertions are structured.

For new tests, you can establish a convention in test support to initialize MockMvcTester from a configured MockMvc. This keeps request configuration centralized and avoids having each test create a different instance.

### 4.3. Do Not Choose Purely for Fewer Lines of Code

A shorter assertion is not automatically easier to understand. For example:

~~~java
assertThat(mvcTester.get().uri("/orders/42"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.id")
        .isEqualTo(42);
~~~

It is concise, but readers unfamiliar with MockMvcTester may find it harder to understand what bodyJson and extractingPath do.

Conversely, a ResultMatcher chain is longer, yet matcher names like status, contentTypeCompatibleWith, and jsonPath directly describe their intent.

Choose the API that most team members can read, modify, and diagnose when tests fail. Once a style is chosen, standardize imports, helpers, and naming within the module.

## 5. Consistency Conventions at Class, Package, and Module Levels

Conventions can be defined by scope:

| Scope | Suggested Convention |
|---|---|
| New test class | Choose one primary assertion style |
| Existing test package | Keep the style already in use unless there is a reason to change |
| New module | Choose the style according to Spring version and team standards |
| Whole repository | Allow older and newer modules to differ when clearly justified |
| Shared helpers | Do not force tests to switch styles if a helper does not serve both |

You do not need to force the entire repository to switch at once. A repository may contain multiple modules at different Spring versions or maturity levels. Module-level conventions reduce migration cost and avoid large edits solely to unify syntax.

### 5.1. A Single Test Should Have One Primary Style

Example to avoid:

~~~java
@Test
void returnsOrder() throws Exception {
    MvcResult result = mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk())
            .andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(200);
    assertThat(result.getResponse().getContentAsString())
            .contains("\"id\":42");
}
~~~

This test checks status with ResultMatcher and then checks status again with AssertJ on the response. Two duplicate assertions add lines of code without adding evidence.

If choosing ResultMatcher:

~~~java
@Test
void returnsOrder() throws Exception {
    mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42));
}
~~~

If choosing MockMvcTester:

~~~java
@Test
void returnsOrder() {
    assertThat(mvcTester.get().uri("/orders/42"))
            .hasStatusOk()
            .bodyJson()
            .extractingPath("$.id")
            .isEqualTo(42);
}
~~~

In some cases, you need to retrieve MvcResult to inspect data that lacks a corresponding fluent assertion. In those cases, using the lower-level API intentionally is acceptable. What matters is not repeating the same condition in both styles and clearly stating why if mixing is necessary.

### 5.2. Standardize How JSON Is Checked

With ResultMatcher, teams commonly use JSONPath:

~~~java
.andExpect(jsonPath("$.customer.name").value("An"))
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items.length()").value(2))
~~~

With MockMvcTester, you can use bodyJson and extractingPath:

~~~java
assertThat(mvcTester.get().uri("/orders/42"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.customer.name")
        .isEqualTo("An");
~~~

Standardize how fields, arrays, nulls, counts, and data types are checked within the test scope. Avoid having one class use JSONPath, another parse the entire body as a string, and another use ObjectMapper unless complexity or verification needs justify it.

### 5.3. Standardize How Errors Are Checked

With ResultMatcher:

~~~java
mockMvc.perform(get("/orders/404"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
~~~

With MockMvcTester:

~~~java
assertThat(mvcTester.get().uri("/orders/404"))
        .hasStatusNotFound()
        .bodyJson()
        .extractingPath("$.code")
        .isEqualTo("ORDER_NOT_FOUND");
~~~

Whichever API is used, tests should verify both the status and the important error contract. Checking only status 404 can miss cases where an endpoint returns the wrong error code or a body not matching what clients expect.

## 6. Combining with Other Assertion Components

### 6.1. AssertJ for Domain Results

MockMvcTester uses AssertJ for MVC results. AssertJ is also well suited for checking domain objects, DTOs, or collections created during tests.

Example service test:

~~~java
assertThat(order.getStatus()).isEqualTo(OrderStatus.PAID);
assertThat(order.getItems())
        .extracting(OrderItem::getProductCode)
        .containsExactly("P-01", "P-02");
~~~

If MVC tests choose MockMvcTester, the assertion style can stay uniform with other tests using AssertJ. If MVC tests choose ResultMatcher, AssertJ can still be used for domain results in separate checks, while keeping assertions on HTTP results clearly distinct from assertions on Java objects.

### 6.2. AssertJ Does Not Replace Every Spring Matcher

Spring MVC Test has specialized matchers for parts of MVC such as:

- Model and view.
- Flash attributes.
- Redirects and forwards.
- Async requests.
- Session and request attributes.
- Content and JSON/XML.

MockMvcTester provides many fluent assertions for MVC results, but do not assume every existing matcher or extension in the project has a direct equivalent. When a specialized capability is needed, check the API of your Spring version and choose the clearest way to verify it.

If a test needs deep inspection of a property available only via ResultMatcher or ResultHandler, keeping that test on traditional MockMvc is appropriate. Do not convert solely for cosmetic uniformity if it forces an obscure adapter layer.

### 6.3. Diagnostics with print and MvcResult

With traditional MockMvc, you can attach a ResultHandler:

~~~java
mockMvc.perform(get("/orders/42"))
        .andDo(print())
        .andExpect(status().isOk());
~~~

Or obtain MvcResult:

~~~java
MvcResult result = mockMvc.perform(get("/orders/42"))
        .andReturn();

assertThat(result.getResponse().getStatus()).isEqualTo(200);
~~~

MockMvcTester focuses on fluent assertions over request results. When a handler or detailed inspection API is needed that the current syntax does not express conveniently, you can use MockMvc in a dedicated diagnostic test or access results through the API provided by the version in use.

Do not create a helper that executes the request once with MockMvcTester and executes it a second time with MockMvc just to print output. Two requests may traverse two different test states, causing diagnostic data to no longer correspond to the assertion.

## 7. Organizing Shared Configuration

A group of tests can share a factory for creating MockMvc and MockMvcTester.

Example with Spring Framework TestContext:

~~~java
abstract class AbstractMvcTest {

    @Autowired
    protected WebApplicationContext webApplicationContext;

    protected MockMvc mockMvc;
    protected MockMvcTester mvcTester;

    @BeforeEach
    void configureMvc() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();

        mvcTester = MockMvcTester.create(mockMvc);
    }
}
~~~

Subclasses pick one primary style. If a package uses MockMvcTester by convention:

~~~java
class OrderControllerTest extends AbstractMvcTest {

    @Test
    void returnsOrder() {
        assertThat(mvcTester.get().uri("/orders/42"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.id")
                .isEqualTo(42);
    }
}
~~~

If a package still uses ResultMatcher:

~~~java
class LegacyOrderControllerTest extends AbstractMvcTest {

    @Test
    void returnsOrder() throws Exception {
        mockMvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42));
    }
}
~~~

This is an illustrative organization approach. Composition or test support utilities can be used depending on project structure. Do not build an oversized base class containing every assertion helper, every converter, and every mock dependency of the entire application; shared configuration should reflect genuinely shared MVC components.

If using standalone setup, you can create a factory returning a MockMvc with the required controllers, advice, converters, and validators registered. Then create MockMvcTester from that instance. That keeps the two layers separated: the factory handles MVC configuration, while the test class chooses the assertion style.

## 8. Gradually Migrating from ResultMatcher to MockMvcTester

A project with many ResultMatcher tests can migrate incrementally. There is no need to modify all tests just to use the new API.

### Step 1: Verify Platform Prerequisites

Check the Spring Framework version in use. MockMvcTester requires Spring Framework 6.2 or later and AssertJ on the test classpath.

If the project does not meet these requirements yet, continue using traditional MockMvc or plan a separate framework upgrade. Do not mix a newer spring-test into an application using older Spring modules without managing dependency alignment.

### Step 2: Pick a Representative Test

Pick a test with a simple request, such as a JSON GET returning HTTP 200. Convert that test to MockMvcTester while preserving:

- Request method and URI.
- Query parameters, headers, and body.
- Expected HTTP status.
- Content type and important response fields.

Compare the verification goal, not just line count.

### Step 3: Migrate in Groups with Similar Characteristics

You can migrate sequentially by group:

- GET endpoints returning JSON.
- POST endpoints accepting JSON and returning JSON.
- Validation errors.
- Exception handlers.
- Redirect/model/view cases if the fluent API fully supports the need.
- Async or specialized MVC cases.

Tests with specialized matchers or complex helpers can stay on ResultMatcher. Do not force conversion if the result is a wrapper layer harder to read than the existing API.

### Step 4: Update Test Support When Needed

If there is a helper creating MockMvc, add a factory creating MockMvcTester from the same MockMvc. Keep MVC configuration in one place so the two styles do not accidentally use two different configurations.

Do not create two separate configurations just because there are two assertion styles. What should change is how tests express expectations, not how controllers are registered or how requests are processed.

### Step 5: Document Conventions for New Tests

Once the team agrees on a primary style, document it in test support or module guidelines:

- Which style new MVC tests use.
- When ResultMatcher may be kept for specialized matchers.
- How MockMvcTester is created.
- How to print/diagnose when tests fail.
- Rules for avoiding duplicate assertions.

Clear conventions prevent new tests from introducing even more diverging styles.

## 9. Cases Where Traditional MockMvc Should Be Kept

MockMvcTester does not make legacy MockMvc obsolete. In some situations, continuing with ResultMatcher or ResultHandler may be clearer.

### 9.1. Tests Using Many Specialized Matchers

If a test checks model, view, flash attributes, forwards, and session together, Spring's ResultMatchers may express intent directly. Switch to MockMvcTester only when the API of your version fully supports it and the new syntax is easier to read.

### 9.2. Tests Needing ResultHandler

If a test needs print, capturing MvcResult, collecting handler info, or recording requests/responses via a custom workflow, traditional MockMvc provides andDo and andReturn directly.

### 9.3. Tests with Stable Helpers

A test suite with solid custom ResultMatchers and helpers does not need to convert just to follow a trend. Migration costs include editing tests, updating docs, onboarding team members, and handling differences in failure messages. Only migrate when maintenance or readability gains are substantial enough.

### 9.4. Framework Version Does Not Support It Yet

If a module still uses Spring Framework prior to 6.2, ResultMatcher is the natural choice. Avoid adopting a convention requiring an API absent from the module's dependencies.

## 10. Common Mistakes When Choosing an Assertion Style

### Using MockMvcTester Without AssertJ

If the MockMvcTester class is not found or the API is unavailable, check the Spring Test version and AssertJ dependency. Also check dependency resolution to be sure spring-test is actually resolved to the expected version.

### MockMvcTester API Does Not Exist in the Spring Version in Use

MockMvcTester was added in Spring Framework 6.2. Check the resolved version of spring-test rather than looking only at a version declared in one build file. Dependency management or other modules may determine the final version.

### Test Has Two Assertions for the Same Condition

For example, calling both status().isOk() and assertThat(response.getStatus()).isEqualTo(200). Keeping one assertion is enough. Only keep two checks if they verify two distinct properties for a clear reason.

### Using AssertJ on the Raw Response Body for Every Case

Fetching the body as a String and calling contains can overlook JSON structure, data types, or colliding field names. Use JSONPath or bodyJson/extractingPath to verify the exact structure needed.

### Migration Drops Important Matchers

Before replacing ResultMatcher with MockMvcTester, list the test's current conditions. Make sure the new version still verifies status, headers, content type, body, model, redirects, or async as required. Do not drop assertions merely due to unfamiliarity with the equivalent API.

### Using a Helper That Hides the Style

A shared helper may return overly generic types or wrap both MockMvc and MockMvcTester, making it unclear which API the test is using. Helpers should reduce setup duplication, not obscure the assertion style.

### Arbitrarily Mixing Styles Between Nearby Tests

If two tests in the same class use two different styles without reason, readers have to switch context constantly. Pick a primary style per class or package; exceptions should be made explicit.

## 11. Example of a Test Suite with Clear Conventions

Suppose a module chooses MockMvcTester for new MVC tests. A test class might look like this:

~~~java
class OrderControllerTest {

    private final MockMvcTester mvcTester;

    OrderControllerTest(MockMvcTester mvcTester) {
        this.mvcTester = mvcTester;
    }

    @Test
    void returnsOrderDetails() {
        assertThat(mvcTester.get().uri("/orders/42"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.id")
                .isEqualTo(42);
    }

    @Test
    void returnsNotFoundForMissingOrder() {
        assertThat(mvcTester.get().uri("/orders/404"))
                .hasStatusNotFound()
                .bodyJson()
                .extractingPath("$.code")
                .isEqualTo("ORDER_NOT_FOUND");
    }

    @Test
    void createsOrder() {
        assertThat(mvcTester.post().uri("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerName": "An"
                                }
                                """))
                .hasStatus(HttpStatus.CREATED)
                .bodyJson()
                .extractingPath("$.customerName")
                .isEqualTo("An");
    }
}
~~~

The snippet above illustrates the MockMvcTester convention; supplying the instance via constructor depends on the test setup or test framework chosen by the project. In Spring TestContext, a bean can be injected if registered in the configuration, or MockMvcTester can be created from MockMvc during setup. Do not treat the constructor above as an automatic configuration available out of the box in every Spring project.

If a module chooses ResultMatcher, tests can keep this structure:

~~~java
class OrderControllerTest {

    @Test
    void returnsOrderDetails() throws Exception {
        mockMvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42));
    }

    @Test
    void returnsNotFoundForMissingOrder() throws Exception {
        mockMvc.perform(get("/orders/404"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("ORDER_NOT_FOUND"));
    }

    @Test
    void createsOrder() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerName": "An"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.customerName").value("An"));
    }
}
~~~

Both approaches produce equivalent evidence for the API. Choosing one standard within the test scope makes it easy during code review to spot when an endpoint is missing assertions.

## 12. Practical Guidelines

1. Check the Spring version before choosing MockMvcTester; this API requires Spring Framework 6.2 or later.
2. Use MockMvc + ResultMatcher if the existing test suite is stable or requires specialized matchers.
3. Choose MockMvcTester when the project uses a compatible Spring version, AssertJ is present, and the team wants fluent assertions.
4. Pick one primary style per test class or package; do not mix the two purely out of personal preference.
5. Keep requests and the contract being verified unchanged when migrating tests.
6. Do not repeat the same assertion using both ResultMatcher and AssertJ.
7. Use JSONPath or bodyJson/extractingPath to verify JSON structure instead of arbitrary string comparisons.
8. Keep traditional MockMvc for cases requiring ResultHandler, MvcResult, or specialized matchers when the fluent approach does not serve well.
9. Reuse the same MVC configuration when creating MockMvc and MockMvcTester; do not create two different configurations solely for two assertion APIs.
10. Migrate in small groups, preserve valuable tests, and update conventions for new tests.

A consistent MVC test suite lets readers focus on endpoint behavior instead of relearning how assertions are phrased in every test. ResultMatcher fits Spring MVC Test's specialized checks; MockMvcTester brings AssertJ style to MVC results in Spring Framework 6.2 and later. Choose based on version, needs, and team familiarity, and then keep the writing style steady within the agreed scope.

