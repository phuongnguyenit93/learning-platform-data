# Testing GET, POST, PUT, PATCH, DELETE with Statuses and Headers

## Goal

After this lesson, you will be able to:

- Write integration tests for the HTTP methods published by Spring Data REST.
- Verify status codes, Content-Type, Location, and HAL contents appropriate for each operation.
- Distinguish between PUT and PATCH behaviors.
- Test error scenarios such as 400, 401, 403, 404, 405, and 415.
- Use independent test data to confirm the API adheres to its HTTP contract.

## 1. Why Check Both Status and Headers?

A REST request does not just return JSON. It also carries a status code and headers describing the outcome, data format, resource location, or processing conditions.

For example:

- `GET /people` may return `200 OK` along with a HAL representation.
- `POST /people` creates a new resource, typically returning `201 Created` and a `Location` header.
- `PUT` or `PATCH` updates a resource; the response may be `204 No Content` or `200 OK` depending on body-return configuration.
- `DELETE` deletes a resource and typically returns `204 No Content`.

If a test only checks JSON, an API might return the right data with the wrong status or omit a crucial header without the test catching it. Conversely, checking only the status is insufficient to know whether the representation has the right media type or contains the required HAL links.

With Spring Data REST, repositories are published as REST resources. Therefore, integration tests should call actual endpoints through the HTTP layer to exercise Spring Security, content negotiation, the repository exporter, and serialization together.

## 2. Common Status Codes

The table below shows the standard HTTP contract for collection and item resources. Application configuration, repository exposure, and exception handlers can alter certain responses; tests must match the chosen contract.

| Operation | Example request | Typical success result | What to check |
|---|---|---|---|
| Read collection | `GET /people` | `200 OK` | HAL Content-Type, `_links`, data |
| Read item | `GET /people/42` | `200 OK` | HAL Content-Type, item contents |
| Create | `POST /people` | `201 Created` | `Location` header, representation if configured |
| Replace/update | `PUT /people/42` | `204 No Content` or `200 OK` | Status per configuration, body if present |
| Partial update | `PATCH /people/42` | `204 No Content` or `200 OK` | Status per configuration, body if present |
| Delete | `DELETE /people/42` | `204 No Content` | No response body |

Common error statuses that should be tested:

| Status | Meaning | Example scenario |
|---|---|---|
| `400 Bad Request` | Invalid request | Malformed JSON or data failing validation |
| `401 Unauthorized` | Unauthenticated | Missing or invalid authentication credentials |
| `403 Forbidden` | Authenticated but insufficient permissions | Principal lacks required authority |
| `404 Not Found` | Resource not found | Nonexistent ID or unexported endpoint |
| `405 Method Not Allowed` | Endpoint does not support method | Calling `DELETE` when deletion is disabled |
| `406 Not Acceptable` | No representation matches `Accept` | Client requests a media type the server does not provide |
| `415 Unsupported Media Type` | Request body uses an unsupported media type | Sending PATCH with a Content-Type not accepted by the API |

Do not assume every application returns these exact statuses for every error. For instance, a custom exception handler may map business errors to a different status. What matters is defining the API contract and writing tests pinned to that contract.

## 3. Headers to Watch

### Accept

The `Accept` header tells the server which representation format the client wants to receive. Spring Data REST commonly uses HAL JSON:

~~~http
Accept: application/hal+json
~~~

In MockMvc, you can use `MediaTypes.HAL_JSON` to avoid retyping the media type string repeatedly.

### Content-Type

The `Content-Type` header describes the format of the request body. For standard JSON create or update operations:

~~~http
Content-Type: application/json
~~~

For JSON Merge Patch, the commonly used media type is:

~~~http
Content-Type: application/merge-patch+json
~~~

Use the exact media type supported by the application's endpoint. If the API implements JSON Patch or another format, the test must send the corresponding Content-Type.

### Location

When resource creation succeeds, the response typically includes a `Location` header pointing to the URI of the newly created resource:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/people/42
~~~

Clients can use this URI to read or perform follow-up operations on the created resource. At a minimum, tests should verify the header exists; if the URI structure is part of the API contract, verify the path as well.

### Response Content-Type

When a response has a HAL representation, verify the media type is compatible with `application/hal+json`. For a `204 No Content` response, there is no body, so do not require the server to return a representation Content-Type.

### Allow and conditional headers

For `405 Method Not Allowed`, HTTP allows the server to advertise supported methods using the `Allow` header. If the application publishes this header, check both allowed and disallowed methods.

Headers like `ETag` and `Last-Modified` should only be asserted when the application explicitly enables or implements the corresponding mechanism. Do not assume every repository endpoint automatically provides ETags or supports `If-Match`.

## 4. Setting Up MockMvc Integration Tests

MockMvc sends requests through Spring MVC inside the application context, allowing endpoint testing without opening a real HTTP port. With Spring Data REST, use integration tests so the exporter, security filters, and repository configuration all participate.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonRestApiTest {

    @Autowired
    private MockMvc mockMvc;

    // Each test prepares independent data, e.g. a Person with ID 42.
}
~~~

Commonly used imports:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
~~~

The examples use the `/people` endpoint. Actual endpoint names depend on repositories and `@RepositoryRestResource` configuration. If the application requires authentication, tests must supply an appropriate principal or token; the examples below focus on the HTTP contract.

## 5. Testing GET Collection and GET Item

### GET collection

~~~java
@Test
void getPeopleReturnsHalCollection() throws Exception {
    mockMvc.perform(get("/people")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content()
            .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

Assertions verified:

- Status is `200 OK`.
- Response has a media type compatible with HAL JSON.
- Representation contains a `self` link.

If you need to verify data, you can add assertions on the corresponding JSON paths. In HAL collections, items typically reside in `_embedded`; the key name depends on the published relation for the repository. Avoid hard-coding `_embedded.people` if the application's relation has a different name.

### GET item

~~~java
@Test
void getPersonReturnsHalResource() throws Exception {
    long existingId = 42L; // Fixture created before the test.

    mockMvc.perform(get("/people/{id}", existingId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content()
            .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

If the item does not exist, verify the response against the application's error contract, typically `404 Not Found`:

~~~java
mockMvc.perform(get("/people/{id}", 999999L)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isNotFound());
~~~

## 6. Testing POST to Create a Resource

POST on a collection endpoint typically creates a new resource. The request sends JSON via `Content-Type` while declaring the desired response format via `Accept`.

~~~java
@Test
void postPeopleCreatesResourceAndReturnsLocation() throws Exception {
    String requestBody = """
        {
            "name": "Ada Lovelace"
        }
        """;

    MvcResult result = mockMvc.perform(post("/people")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content(requestBody))
        .andExpect(status().isCreated())
        .andExpect(header().exists(HttpHeaders.LOCATION))
        .andReturn();

    String location = result.getResponse()
        .getHeader(HttpHeaders.LOCATION);

    assertThat(location).isNotBlank();
}
~~~

Key points:

- `201 Created` confirms resource creation succeeded.
- `Location` provides the URI of the newly created resource.
- If configured to return a representation after creation, you can additionally check Content-Type and body. If configured not to return a body, do not require the response to contain a HAL representation.

If you want to verify the exact URI, parse `Location` using `URI` or assert on its path instead of depending on host, random port, or absolute addresses of the test environment.

## 7. Testing PUT for Full Resource Update

PUT is typically used to replace or update the representation of a resource at an existing URI. The body must conform to the writable fields allowed by the resource.

~~~java
@Test
void putPersonUpdatesResource() throws Exception {
    long existingId = 42L; // Fixture created before the test.

    String requestBody = """
        {
            "name": "Ada Byron"
        }
        """;

    mockMvc.perform(put("/people/{id}", existingId)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content(requestBody))
        .andExpect(status().isNoContent());
}
~~~

In the common default Spring Data REST configuration, `returnBodyOnUpdate` is false, so a successful PUT/PATCH returns `204 No Content`. If the application enables returning a body after update via `RepositoryRestConfiguration.setReturnBodyOnUpdate(true)`, adjust tests to expect `200 OK` and verify the HAL representation.

Example when returning a body is enabled:

~~~java
mockMvc.perform(put("/people/{id}", existingId)
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .content(requestBody))
    .andExpect(status().isOk())
    .andExpect(content()
        .contentTypeCompatibleWith(MediaTypes.HAL_JSON));
~~~

Do not write tests that accept both `200` and `204` just to keep the test green. Choose one explicit response configuration and assert the exact contract published by the application.

## 8. Testing PATCH for Partial Update

PATCH is used to modify part of a resource. JSON Merge Patch is a common format; in that case the request uses `application/merge-patch+json`.

~~~java
@Test
void patchPersonUpdatesSelectedFields() throws Exception {
    long existingId = 42L; // Fixture created before the test.

    String patchBody = """
        {
            "name": "Ada King"
        }
        """;

    MediaType mergePatch = MediaType.valueOf(
        "application/merge-patch+json"
    );

    mockMvc.perform(patch("/people/{id}", existingId)
            .contentType(mergePatch)
            .accept(MediaTypes.HAL_JSON)
            .content(patchBody))
        .andExpect(status().isNoContent());
}
~~~

If the application enables `returnBodyOnUpdate`, the status can be `200 OK` and the response contains a representation. If the API uses JSON Patch instead of JSON Merge Patch, the body and Content-Type will differ. Tests must match the actual PATCH format rather than merely switching the HTTP method from PUT to PATCH while keeping everything else unchanged.

You should verify persisted data after the update to be sure PATCH only changes the submitted fields and preserves other fields. For example, if the request only changes `name`, the test should confirm that `email` or other omitted fields retain their previous values per the semantics chosen by the application.

## 9. Testing DELETE to Remove a Resource

DELETE on an item endpoint typically returns `204 No Content`. Because there is no representation in the response, assertions should focus on status and confirming the resource is no longer accessible.

~~~java
@Test
void deletePersonRemovesResource() throws Exception {
    long existingId = 42L; // Fixture created before the test.

    mockMvc.perform(delete("/people/{id}", existingId))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));

    mockMvc.perform(get("/people/{id}", existingId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isNotFound());
}
~~~

This test verifies two things:

1. DELETE returns a success status per the contract.
2. A subsequent GET no longer finds the resource.

If the application uses soft deletes, or the endpoint has archival semantics rather than physical deletion, check the corresponding business state. Do not assume every DELETE operation permanently removes a row from the database.

## 10. Testing Errors and Access Control

Error cases help uncover situations where the API unintentionally allows invalid operations or returns inconsistent responses.

### Invalid data

~~~java
mockMvc.perform(post("/people")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .content("{ invalid json"))
    .andExpect(status().isBadRequest());
~~~

You can add validation tests, such as missing required fields or invalid values. Statuses and error structures should follow the application's exception handling.

### Unauthenticated and unauthorized requests

If the API is protected by Spring Security, test separately:

- Missing authentication credentials: typically `401 Unauthorized`.
- Authenticated but lacking authority: typically `403 Forbidden`.

With MockMvc, you can use Spring Security request post-processors to supply principals with different authorities. For example:

~~~java
mockMvc.perform(delete("/people/{id}", 42L)
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("people:read")
        )))
    .andExpect(status().isForbidden());
~~~

For this snippet to work, the project needs Spring Security test support dependencies and corresponding security configuration. If the application uses JWT or an OAuth2 Resource Server, use test support appropriate for the implemented authentication type.

### Unsupported method

If the repository does not export a method or the application blocks that method, tests can verify `405 Method Not Allowed`:

~~~java
mockMvc.perform(delete("/people")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isMethodNotAllowed());
~~~

If the response includes an `Allow` header, check the advertised list of methods. Some endpoints may return another error per configuration; base assertions on the actual response contract.

### Unsupported media type

Sending a Content-Type not accepted by the endpoint can lead to `415 Unsupported Media Type`. This case is useful to confirm the API rejects invalid request formats instead of misinterpreting payloads.

## 11. Organizing Data and Assertions in Tests

A reliable integration test needs deterministic input data and independence from execution order:

1. Create fixtures per test or use test data with controlled IDs.
2. Do not share a single record if any test updates or deletes it.
3. Clean up data after the test, or use a transaction/fixture strategy matching how requests execute in the test context.
4. Assert status first, then check relevant headers and body.
5. When checking collections, avoid depending on item order if the API does not guarantee default sorting.
6. Check Content-Type compatibility instead of overly rigid header string comparisons when charset parameters may vary.

For create/update requests, verify data was saved using the repository or a follow-up GET. That distinguishes a superficially successful response from an operation that actually changed state.

If tests require authentication, create principals for each role: reader, creator, editor, and administrator. Each role should have both allowed and denied tests to confirm policies do not accidentally grant excessive permissions.

## 12. Minimum Testing Matrix

| HTTP method | Success case | Status to check | Key headers/body |
|---|---|---|---|
| GET | Read collection/item | 200 | Accept, Content-Type, HAL links |
| POST | Create resource | 201 | Request Content-Type, Location |
| PUT | Update resource | 204 or 200 per configuration | Request Content-Type; body if enabled |
| PATCH | Partial update | 204 or 200 per configuration | Patch Content-Type; body if enabled |
| DELETE | Delete resource | 204 | Response has no body |

In addition to success cases, add cases for invalid data, unauthenticated access, insufficient permissions, nonexistent resources, unsupported methods, and invalid media types. For each case, explicitly document which request is sent and which status/headers are expected.

## 13. Self-Check Exercises

A `PersonRepository` is published at `/people`. The application uses HAL JSON and does not enable returning bodies after updates.

1. What status and Content-Type should a successful collection GET return?
2. What header should a successful POST creation include so the client knows the newly created resource URI?
3. With body-return-on-update disabled, what status do successful PUT and PATCH typically return?
4. Does a successful DELETE normally have a body or not?
5. What status does a logged-in user lacking authority to delete a resource typically receive?
6. What status might a client receive when sending a Content-Type not supported by the endpoint?
7. Why should a PATCH test also verify persisted data after the update instead of checking only the status?

**Answers:**

1. `200 OK` and a Content-Type compatible with `application/hal+json`.
2. `Location`.
3. `204 No Content`.
4. No body, typically `204 No Content`.
5. `403 Forbidden`.
6. `415 Unsupported Media Type`.
7. Because status only confirms the request was processed; you need to confirm the intended fields were updated and other fields remained unchanged per PATCH semantics.

## Takeaways

- GET typically returns `200 OK` and a HAL representation.
- POST creating a resource typically returns `201 Created` along with `Location`.
- PUT/PATCH may return `204` or `200` depending on return-body-on-update configuration.
- DELETE typically returns `204 No Content`.
- Verify `Accept`, `Content-Type`, `Location`, and conditional headers according to the API contract.
- Use integration tests to verify status, headers, representation, and post-operation data state.

References:

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
