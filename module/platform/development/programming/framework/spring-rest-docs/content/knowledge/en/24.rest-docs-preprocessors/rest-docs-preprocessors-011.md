# Writing Custom Preprocessors

Spring REST Docs' built-in preprocessors—such as pretty print, modifying headers, removing headers, normalizing URIs, and replacing patterns—cover many common needs. However, a project may need its own policy: masking requests only for public APIs, skipping health-check endpoints, normalizing correlation IDs per internal conventions, or bundling the same sanitization rules across many tests. In such cases, you can write a custom preprocessor to encapsulate project logic and reuse it across documentation operations.

Spring REST Docs distinguishes two abstractions: `OperationRequestPreprocessor` processes recorded requests, and `OperationResponsePreprocessor` processes recorded responses. You can implement either interface, often by delegating to built-in preprocessors and adding contract-specific conditions. This keeps the scope of change clear: custom preprocessors only operate on the message used to generate snippets and do not change the application's real requests or responses.

This lesson belongs to the **Preprocessors** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generating request, response, payload, parameter, and header snippets, then authoring Asciidoctor/Markdown and integrating builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify when built-in preprocessors are insufficient and a custom policy is needed.
2. Distinguish `OperationRequestPreprocessor` and `OperationResponsePreprocessor`.
3. Write a custom preprocessor class by delegating to built-in processors.
4. Apply conditions by URI or endpoint policy before processing a message.
5. Combine custom processors with `preprocessRequest(...)` and `preprocessResponse(...)`.
6. Test behavior, ordering, skip conditions, and sensitive data handling.
7. Package, reuse, and maintain custom preprocessors.

## 2. When Should You Write a Custom Preprocessor?

First, check the built-in preprocessors. If you only need to format JSON, drop a header, replace `Authorization`, or normalize scheme/host/port, built-in processors are usually easier to read and require less code.

A custom preprocessor is useful when a policy has one or more of these characteristics:

- Many endpoints share the same masking rule, but it applies only to certain route groups.
- Health checks, metrics, or internal operations need to be skipped.
- Values to normalize are decided by the operation's path, method, or headers.
- The project needs a meaningful policy name rather than repeating a long processor chain in every test.
- Multiple built-in processors need to coordinate under a unified rule that can be tested independently.
- Structural transformation logic is required that built-in processors cannot express directly.

Do not create a custom processor just to wrap a single `prettyPrint()` call if there is no additional policy. A simple configuration helper may suffice. The goal is to encapsulate a genuinely meaningful rule, not create obscure abstractions.

## 3. Core Abstractions

Spring REST Docs provides these operation processing types:

| Type | Input Message | Output | Configuration Wrapper |
| --- | --- | --- | --- |
| `OperationRequestPreprocessor` | `OperationRequest` | Post-processed request for snippets | `preprocessRequest(...)` |
| `OperationResponsePreprocessor` | `OperationResponse` | Post-processed response for snippets | `preprocessResponse(...)` |

These interfaces belong to Spring REST Docs' preprocessing package. An implementation receives an operation message and returns an operation message passed onward to snippet generation. Do not confuse them with Servlet Filters, Spring MVC Interceptors, or WebFlux filters; those participate in the application's runtime request/response processing.

Common static imports with MockMvc:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
```

Return types and interface signatures must be verified against the Spring REST Docs version your project uses. Rely on the public API of your pinned dependency; do not depend on internal implementation classes.

## 4. Custom Request Preprocessor Pattern via Delegation

A safe way to start is creating a custom policy class that uses built-in request processors internally. For example, public APIs need tokens and correlation IDs replaced, while removing `Cookie` and internal trace headers.

```java
import java.net.URI;

import org.springframework.restdocs.operation.OperationRequest;
import org.springframework.restdocs.operation.preprocess.OperationRequestPreprocessor;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

public final class PublicRequestPreprocessor
        implements OperationRequestPreprocessor {

    private final OperationRequestPreprocessor delegate;

    public PublicRequestPreprocessor() {
        this.delegate = preprocessRequest(
            modifyHeaders()
                .set("Authorization", "Bearer <access-token>")
                .set("X-Correlation-Id", "docs-correlation-id")
                .build(),
            removeHeaders("Cookie", "X-Internal-Trace")
        );
    }

    @Override
    public OperationRequest preprocess(OperationRequest request) {
        URI uri = request.getUri();

        // Skip health endpoints; snippets for these endpoints do not need the public policy.
        if (uri.getPath() != null && uri.getPath().startsWith("/actuator/health")) {
            return request;
        }

        return this.delegate.preprocess(request);
    }
}
```

This class encapsulates the project's policy and applies a URI-based condition. Header transformations are delegated to built-in processors. For the health check route, the processor returns the recorded request without applying this policy. If that route could contain sensitive data, define a separate safe policy rather than accidentally leaking headers.

### 4.1. Why Use Delegation?

Delegation helps you:

- Reuse behavior provided by the library.
- Avoid manually copying and reconstructing HTTP messages.
- Keep the project's policy in a clearly named class.
- Test applicability conditions independently from header transformation details.
- Adjust the built-in chain when the contract evolves.

A custom wrapper does not necessarily have to rebuild `OperationRequest` manually. Only transform operation objects directly when built-ins fall short and you thoroughly understand your library version's public API.

## 5. Custom Response Preprocessor Pattern

Responses have their own policy: remove `Set-Cookie` and internal headers, replace dynamic request IDs with a stable value, and format the body. This can be packaged as follows:

```java
import org.springframework.restdocs.operation.OperationResponse;
import org.springframework.restdocs.operation.preprocess.OperationResponsePreprocessor;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

public final class PublicResponsePreprocessor
        implements OperationResponsePreprocessor {

    private final OperationResponsePreprocessor delegate;

    public PublicResponsePreprocessor() {
        this.delegate = preprocessResponse(
            modifyHeaders()
                .set("X-Request-Id", "docs-request-id")
                .build(),
            removeHeaders("Set-Cookie", "X-Internal-Node"),
            prettyPrint()
        );
    }

    @Override
    public OperationResponse preprocess(OperationResponse response) {
        return this.delegate.preprocess(response);
    }
}
```

This class names the response policy and reuses built-in processors. If an endpoint needs to retain `Set-Cookie` because it documents cookie authentication, do not apply the default public policy; create a specialized policy or allow explicit configuration.

## 6. Using Custom Processors in document(...)

With MockMvc, pass instances into the corresponding wrappers:

```java
mockMvc.perform(
        get("/api/orders/{id}", 42L)
            .header("Authorization", "Bearer docs-test-token")
            .header("Cookie", "SESSION=test-session")
            .header("X-Correlation-Id", "run-91382")
    )
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andDo(document("orders-get",
        preprocessRequest(new PublicRequestPreprocessor()),
        preprocessResponse(new PublicResponsePreprocessor())
    ));
```

Assertions run on the test's exchange. The request preprocessor cleans request snippets; the response preprocessor normalizes response snippets. Instances can be instantiated directly or managed by shared factories/helpers in test support.

### 6.1. Use Only One Side When Needed

Not every operation requires both types:

```java
.andDo(document("products-get",
    preprocessResponse(new PublicResponsePreprocessor())
));
```

If the request contains no data needing replacement, there is no need to add a request processor. Similarly, an operation that only needs token masking in the request can use only the custom request preprocessor.

## 7. Conditionalizing Policy per Operation

A custom processor can decide whether to apply its delegate based on the recorded message. For example, the request processor above skips health-check paths. Conditions can be based on:

- Path or URI pattern.
- HTTP method if the operation API exposes it.
- Headers present in the recorded message.
- Public/internal endpoint groups configured in test support.

Conditions should be simple, deterministic, and tested. Avoid checking the host machine name to decide whether to mask; results could differ between local and CI. Prefer policies driven by the contract or documentation configuration.

### 7.1. Do Not Skip Sanitization Just for Internal Routes

If a route is skipped, ensure snippets for that route cannot contain secrets. Skipping a policy does not automatically make data safe. You can apply a different policy for internal operations, but you must explicitly decide which headers stay and which must be removed.

## 8. Writing a True Custom Transformation

Delegation is ideal when merely coordinating built-ins. When you need data transformations that built-ins cannot express, implement logic directly against the public API of `OperationRequestPreprocessor` or `OperationResponsePreprocessor`.

A custom transformation should:

1. Read the input message without mutating shared collections or byte arrays in place.
2. Modify only the requested parts.
3. Preserve method, URI path, status, content type, and unrelated data.
4. Return a new operation message via the public factory/builder of your exact library version.
5. Not depend on internal implementation classes or package-private constructors.
6. Have tests proving both what changes and what stays untouched.

```java
// Conceptual skeleton: how to create a new OperationRequest depends on the public API
// of the Spring REST Docs version used by the project.
final class CustomRequestPreprocessor
        implements OperationRequestPreprocessor {

    @Override
    public OperationRequest preprocess(OperationRequest request) {
        // 1. Read URI, headers, method, parameters, and content.
        // 2. Create a copy via the library version's public factory/builder.
        // 3. Modify only the necessary fields.
        // 4. Return the new OperationRequest.
        return request;
    }
}
```

This is a directional skeleton, not a complete transformation implementation. Check factory/builder signatures in your dependency version before writing code that constructs new operations. If the change is only for common headers or patterns, built-in processors usually carry lower risk.

## 9. Testing Custom Preprocessors

Do not merely confirm that endpoint tests succeed. Separately verify the policy and snippet output. For a custom wrapper using built-ins, documentation tests should confirm:

| Case | Expectation |
| --- | --- |
| Request with test `Authorization` | Snippet shows placeholder, no test token |
| Request with `Cookie` | `Cookie` does not appear if policy requires removal |
| Request to health path | Skip branch executes properly; output remains safe |
| Response with dynamic request ID | Snippet has configured sample ID |
| Response with `Set-Cookie` | Header removed from raw response snippet per policy |
| JSON response | Body remains valid and readable |
| Contract header/field | Descriptor describes accurately and does not contradict raw snippet |

You can unit-test processors with operation fixtures if your project can construct stable messages using the public API. Integration/documentation tests remain essential because they verify the recorder, processor, and snippet output together.

### 9.1. Inspecting Derived Snippets

After running tests, read the related files:

```text
target/generated-snippets/orders-get/
├── http-request.adoc
├── http-response.adoc
├── curl-request.adoc
├── httpie-request.adoc
├── request-headers.adoc
└── response-headers.adoc
```

Filenames depend on descriptors and configuration. Search for fixture tokens, cookies, random IDs, or internal hostnames across the entire output directory. Also inspect rendered HTML/PDF if snippets are included in documentation.

## 10. Error Handling and Limitations

| Issue | Cause | Resolution |
| --- | --- | --- |
| Custom processor is not called | Passed to wrong request/response wrapper or not attached to `document` | Check branch and operation recorder |
| Token still appears | Delegate did not replace the right header or another snippet keeps data | Inspect raw, cURL, and HTTPie |
| Skipped endpoint contains secret | Skip condition too broad or unsafe input data | Narrow condition; do not skip protective policies |
| Response header unexpectedly missing | Applied wrong response policy to special operation | Create contract-specific policy |
| Snippets differ between local and CI | Policy depends on host/environment or dynamic data | Use deterministic fixtures and configuration |
| Custom code drops metadata | Rebuilt operation message without copying all properties | Use built-ins/delegation or copy completely via public API |
| Descriptors do not match snippets | Processor altered/removed documented elements | Align descriptors with contract and final record |
| Used internal implementation class | Coupled to version-specific internals | Use only public APIs of pinned dependency |

Never use custom processors to convert error statuses into success, insert missing fields, fix wrong URIs, or erase traces of unsafe responses. Those actions strip documentation of its verifiability.

## 11. Reuse and Configuration Management

A project can place custom processors in a test support package:

```text
src/test/java/
└── com/example/docs/
    ├── preprocessor/
    │   ├── PublicRequestPreprocessor.java
    │   └── PublicResponsePreprocessor.java
    └── OrdersDocumentationTests.java
```

Name classes after their policy and scope, not vague implementation details. If multiple modules share a policy, consider a shared test-support library when Spring REST Docs versions and security rules are managed centrally.

Management guidelines:

- Prefer stateless constructors or immutable configuration.
- Never store request/response data across invocations.
- Never use mutable static state to pass data between tests.
- Make default policies and per-endpoint exceptions explicit.
- Treat policy changes like changes to public documentation content.
- Review snippet diffs during code review to see impact.

## 12. Integrating into Asciidoctor and CI

Custom processors do not change how documentation is authored. Tests still emit snippets to the output directory, and Asciidoctor/Markdown still include the corresponding files. What you should add is verification that policies ran and output is safe before rendering/publishing.

```text
Clean generated snippets
          │
          ▼
Run documentation tests
          │
          ▼
Apply custom request/response preprocessors
          │
          ▼
Verify snippets and scan sensitive values
          │
          ▼
Render Asciidoctor / Markdown
          │
          ▼
Review HTML/PDF artifact
          │
          ▼
Publish
```

If tests are skipped, custom processors do not run and stale output can remain in the directory. Clean output before tests, enforce test execution in the documentation lifecycle, and render solely from the current build's snippets.

## 13. Practice Exercise

Create two custom preprocessors for the orders API:

- Request policy replaces the Bearer token with a placeholder, normalizes the correlation ID, and removes `Cookie`.
- Response policy replaces the request ID with a sample value, removes `Set-Cookie` and internal node headers, then formats JSON.
- Health-check endpoints skip the public request policy but must have their own safe rule.

**Tasks:**

1. Write `PublicRequestPreprocessor` implementing `OperationRequestPreprocessor` and delegating to built-ins.
2. Write `PublicResponsePreprocessor` implementing `OperationResponsePreprocessor`.
3. Add an explicit condition for the health-check path and verify the skip branch.
4. Attach both processors to documentation tests via `preprocessRequest(...)` and `preprocessResponse(...)`.
5. Assert status, body, and headers on the real response.
6. Run tests and inspect request/response, cURL, HTTPie, and descriptor snippets.
7. Add unit/integration tests for the policy if operation fixtures can be built with your library version's public API.
8. Verify no tokens, `Cookie`, or internal metadata remain in output that must not be exposed.
9. Render Asciidoctor and review HTML/PDF.
10. Run a clean build in CI to ensure snippets regenerate cleanly.

**Completion criteria:** custom classes have clear responsibilities; request/response policies are separated; conditional branches are tested; real messages are asserted; snippets are safe and consistent with descriptors; builds are reproducible.

## 14. Takeaways

- Write a custom preprocessor when you need project-specific policies or conditional logic that built-ins do not express cleanly.
- `OperationRequestPreprocessor` and `OperationResponsePreprocessor` handle two distinct operation message types.
- Custom wrappers can delegate to `preprocessRequest(...)` or `preprocessResponse(...)` combining built-in processors.
- Define policies by contract and endpoint; skip conditions must be explicit and never leak secrets.
- When constructing new operation messages directly, use only the public factory/builder of your library version and preserve full metadata.
- Assertions check real requests/responses; preprocessors only normalize the snippet record.
- Unit/integration tests and reviewing all derived snippets catch policy mistakes before publishing.
