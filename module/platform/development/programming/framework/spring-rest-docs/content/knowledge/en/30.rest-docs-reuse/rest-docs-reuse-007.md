# Sharing snippet configuration across tests

## 1. Why share snippet configuration?

Spring REST Docs produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Each operation can generate snippets for requests, responses, payloads, parameters, headers, and hypermedia links. Snippets are compiled into Asciidoctor/Markdown and integrated into the build and CI.

Within a module, multiple documentation tests often need the same rules: output directory, template format, request/response preprocessors, default snippets, URI host/port, and template overrides. If each test configures these individually, snippets easily diverge and format changes require editing many places.

Sharing configuration keeps tests concise, preserves consistent output, and reduces maintenance effort. Configuration rules should be shared in helpers or test configurations while each test still creates its own operations and descriptors. Do not share builders or mutable state across tests running in parallel.

## 2. Components that can be placed in shared configuration

| Component | Where to configure | Reason to share |
| --- | --- | --- |
| Output directory | RestDocumentationContextProvider or build | Centralize snippets |
| Template format | SnippetConfigurer.withTemplateFormat(...) | Standardize file extensions and syntax |
| Default snippets | withDefaults(...), withAdditionalDefaults(...) | Automatically generate common snippets |
| Request preprocessor | OperationPreprocessors | Normalize URI/headers/body before writing |
| Response preprocessor | OperationPreprocessors | Pretty-print and sanitize responses |
| Template overrides | Test resources classpath | Use the same Mustache templates |
| Operation attributes | Documentation configuration | Pass common metadata when appropriate |

Only share rules that are genuinely identical across tests. An endpoint with uniquely sensitive responses may need its own preprocessor; a streaming endpoint may not need body pretty-printing.

## 3. Sharing MockMvc configuration with a helper

With MockMvc, REST Docs configuration is applied via documentationConfiguration(...). You can create a shared method to configure MockMvcConfigurer:

~~~java
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.mockmvc.MockMvcRestDocumentation;
import org.springframework.restdocs.mockmvc.MockMvcRestDocumentationConfigurer;
import org.springframework.restdocs.templates.TemplateFormats;

final class RestDocsMockMvcConfig {

    private RestDocsMockMvcConfig() {
    }

    static MockMvcRestDocumentationConfigurer restDocs(
            RestDocumentationContextProvider contextProvider) {
        return MockMvcRestDocumentation.documentationConfiguration(contextProvider)
                .snippets()
                .withTemplateFormat(TemplateFormats.asciidoctor());
    }
}
~~~

This illustrative example focuses on format. Return types and fluent APIs should be verified against your project's Spring REST Docs version; if you need URI defaults, add uris() according to that version's API. If fixed URIs are unnecessary, keep the URIs from the test environment.

Apply in a test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderDocumentationTest {

    @Autowired
    WebApplicationContext context;

    @Autowired
    RestDocumentationContextProvider restDocumentation;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(RestDocsMockMvcConfig.restDocs(restDocumentation))
                .build();
    }
}
~~~

The helper creates a configurer for the current test context. MockMvc is built in BeforeEach; do not store a pre-built builder shared across tests.

## 4. Sharing preprocessors

Preprocessors are high-value candidates for sharing. For example, if every request/response needs readable JSON and certain headers with sensitive values removed:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

final class RestDocsPreprocessors {

    private RestDocsPreprocessors() {
    }

    static OperationRequestPreprocessor cleanRequest() {
        return preprocessRequest(
                prettyPrint(),
                removeHeaders("Authorization", "Cookie"));
    }

    static OperationResponsePreprocessor cleanResponse() {
        return preprocessResponse(
                prettyPrint(),
                removeHeaders("Set-Cookie"));
    }
}
~~~

Preprocessor type names and imports must match your Spring REST Docs version. For sensitive headers, removing a header from the snippet does not mean the test skips authentication; the request is still sent, and the preprocessor only changes the recorded copy used for documentation.

Apply preprocessors in an operation:

~~~java
mockMvc.perform(get("/api/orders/{id}", "o-9001"))
        .andExpect(status().isOk())
        .andDo(document("orders-get",
                preprocessRequest(prettyPrint(), removeHeaders("Authorization")),
                preprocessResponse(prettyPrint())));
~~~

If the helper already returns OperationRequestPreprocessor or OperationResponsePreprocessor, pass it directly to the corresponding document overload. Do not wrap it in preprocessRequest(...) a second time.

## 5. Using consistent default snippets

You can configure which snippets are generated for every operation. Distinguish between two APIs:

- withAdditionalDefaults(...) appends snippets to the existing default list.
- withDefaults(...) replaces the default list with the list you specify.

If you only want to add snippets, prefer withAdditionalDefaults(...). Use withDefaults(...) when you genuinely want full control over the entire list and are ready to redeclare the snippets you want to keep.

Illustrative configuration example:

~~~java
documentationConfiguration(restDocumentation)
        .snippets()
        .withAdditionalDefaults(new CustomSummarySnippet());
~~~

CustomSummarySnippet is a project-defined snippet class. Before adding a default snippet to the shared configuration, verify that every operation can produce it. Not every endpoint has the same body or headers.

## 6. Sharing WebTestClient configuration

WebTestClient uses documentationConfiguration(...) inside a filter. You can create a helper:

~~~java
static WebTestClientConfigurer restDocs(
        RestDocumentationContextProvider contextProvider) {
    return WebTestClientRestDocumentation.documentationConfiguration(contextProvider)
            .snippets()
            .withTemplateFormat(TemplateFormats.asciidoctor());
}
~~~

The actual return type depends on the WebTestClient API of your Spring REST Docs version. Use your IDE/compiler to confirm the provided filter/configurer type; the goal is to centralize format and snippet configuration in one helper.

Apply:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .filter(WebTestClientRestDocumentation.documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.asciidoctor()))
        .build();
~~~

Keep the same format and output rules between MockMvc and WebTestClient if they document the same API. Preprocessors may differ because one uses the Servlet stack and the other uses the Reactive stack.

## 7. Sharing REST Assured configuration

REST Assured integrates REST Docs through a filter. You can provide a factory creating a filter for each test context:

~~~java
static RestDocumentationFilter restDocsFilter(
        RestDocumentationContextProvider contextProvider) {
    return documentationConfiguration(contextProvider)
            .snippets()
            .withTemplateFormat(TemplateFormats.asciidoctor());
}
~~~

Apply in a test:

~~~java
given(this.spec)
        .filter(restDocsFilter(restDocumentation))
        .when()
        .get("/api/orders/o-9001")
        .then()
        .statusCode(200)
        .apply(document("orders-get"));
~~~

REST Assured has its own filter type compared to MockMvc and WebTestClient. Do not try to force one interface returning the same filter type for all three adapters; share high-level rules such as format, URI, templates, and metadata, and use adapter-specific helpers to apply them.

## 8. Organizing helpers by class

~~~text
src/test/java/
└── com/example/docs/
    ├── config/
    │   ├── RestDocsMockMvcConfig.java
    │   ├── RestDocsWebTestClientConfig.java
    │   ├── RestDocsRestAssuredConfig.java
    │   └── RestDocsPreprocessors.java
    ├── descriptors/
    │   ├── ApiHeaderDescriptors.java
    │   └── OrderFieldDescriptors.java
    └── tests/
        ├── OrderDocumentationTest.java
        └── CustomerDocumentationTest.java
~~~

Separate by responsibility:

- config: how the adapter creates operations and writes snippets.
- preprocessors: normalizing or sanitizing requests/responses before writing.
- descriptors: reusable API contract descriptions.
- tests: fixture data, HTTP assertions, and operation-specific documentation.

Avoid putting everything into a large BaseDocumentationTest with many hard-to-follow hooks. Small, clearly named helpers are usually easier to understand than multi-level inheritance.

## 9. Using JUnit setup to reduce duplication

With JUnit Jupiter, BeforeEach is well suited for building MockMvc from the current context. If multiple test classes share the exact same configuration, a small base class can be used:

~~~java
abstract class AbstractRestDocsMockMvcTest {

    @Autowired
    protected WebApplicationContext context;

    @Autowired
    protected RestDocumentationContextProvider restDocumentation;

    protected MockMvc mockMvc;

    @BeforeEach
    void configureMockMvc() {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(RestDocsMockMvcConfig.restDocs(restDocumentation))
                .build();
    }
}
~~~

Concrete tests extend it when they genuinely share lifecycle and configuration:

~~~java
class OrderDocumentationTest extends AbstractRestDocsMockMvcTest {

    @Test
    void getOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-9001"))
                .andExpect(status().isOk())
                .andDo(document("orders-get"));
    }
}
~~~

If tests need different security, standalone setups, controller advice, or message converters, use composition/helpers instead of forcing everything into one base class.

## 10. Avoiding mutable state shared across tests

Sharing factories/configuration is good; sharing builders that mutate state can cause hard-to-find bugs:

- Do not reuse a MockMvcBuilder and append filters/configurers per test.
- Do not hold a mutable descriptor list and modify its contents after tests begin.
- Do not use the same operation identifier for multiple tests generating different snippets, unless intentionally overwriting the same operation.
- Do not make a test depend on execution order to read snippets generated by another test.
- Do not share an output directory across parallel builds if they can overwrite each other.

Factories should return fresh configurations for the test context; descriptors should be freshly created when different states are needed. Each operation should have a stable, unique identifier within the build output.

## 11. Configuring URI and output directory

REST Docs can configure default URIs so snippets display a host/scheme suitable for public documentation:

~~~java
documentationConfiguration(restDocumentation)
        .uris()
        .withScheme("https")
        .withHost("api.example.test")
        .withPort(443);
~~~

Do not put internal hosts or staging addresses into snippets if the documentation targets external users. If endpoints use multiple base URLs or versions, configure them on the appropriate operations.

The output directory is typically provided through RestDocumentationContextProvider and build configuration. Keep a consistent output convention:

~~~text
build/
└── generated-snippets/
    ├── orders-get/
    ├── orders-create/
    └── customers-update/
~~~

Do not hard-code different output directories inside individual tests. Let the plugin/build script manage the snippet output directory while tests focus on operations and descriptors.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Snippets across tests have different formats | Format configuration duplicated inconsistently | Use a shared adapter config helper |
| Some snippets lack HTTP request/response | Default snippets not configured uniformly | Check withDefaults/withAdditionalDefaults |
| Sensitive headers appear in output | Preprocessor not applied to the operation | Put the preprocessor in a helper and verify generated files |
| MockMvc and WebTestClient produce different output | Each adapter uses separate format/preprocessors | Share high-level rules and configure each adapter accordingly |
| Parallel tests overwrite snippets | Duplicate operation identifiers or shared output | Use unique identifiers and isolate output per build |
| Base class is hard to extend | Too much specific setup stuffed into parent class | Extract adapter-specific composition helpers |
| URI in snippet points to wrong host | URI defaults set in an unsuitable configuration | Review scheme/host/port and documentation environment |
| Build cannot find snippets | Compilation task ran before snippet-generating tests | Declare task dependencies in the proper order |

## 13. Practice exercise

1. Create RestDocsMockMvcConfig to centralize template format and URI defaults.
2. Create a shared RestDocsPreprocessors to pretty-print JSON and strip Authorization/Cookie from recordings.
3. Use the helpers in two documentation tests; compare snippet structure.
4. Add default snippets without dropping the default snippets already in use.
5. Create a dedicated helper for WebTestClient or REST Assured and unify the format.
6. Migrate a test with custom configuration to the shared helper; keep assertions and operation identifier unchanged.
7. Run tests in parallel to verify output is not overwritten due to duplicate identifiers.

**Completion criteria:** know what to share; create config helpers per adapter; reuse preprocessors and template formats; keep descriptors/operations separate; avoid mutable state; build generates snippets before compilation.

## 14. Pre-commit checklist

- [ ] Template format and output directory are configured consistently.
- [ ] MockMvc/WebTestClient/REST Assured have appropriate adapter-specific helpers.
- [ ] Shared preprocessors are applied to the right operations.
- [ ] Sensitive headers and session cookies are sanitized before writing snippets.
- [ ] Default snippets are added without accidentally replacing the existing list.
- [ ] Helpers return fresh configs without sharing mutable builders across tests.
- [ ] Operation identifiers do not collide.
- [ ] Specific descriptors and assertions remain in the appropriate tests.
- [ ] The snippet generation task runs before the Asciidoctor/Markdown task.
- [ ] CI builds documentation from the current test run's output.

**Remember:** Share snippet configuration using adapter-specific helpers and common rules such as template format, preprocessors, URI defaults, and output conventions. Each test still keeps its own operations, assertions, and descriptors; this organization reduces duplication without making tests depend on mutable state or execution order.
