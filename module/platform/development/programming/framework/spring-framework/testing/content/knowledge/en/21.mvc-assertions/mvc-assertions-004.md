# JSON Comparison With or Without Strict Ordering

## Purpose of JSON Comparison in MVC Testing

When testing a Spring MVC endpoint with MockMvc, the HTTP result often contains JSON in the response body. We need to verify that the response content matches the API contract: required fields are present, values are accurate, object and array structures match, and element order is checked when order is part of the contract.

Do not compare JSON by comparing two raw strings verbatim. Two JSON payloads can represent the same data while differing in whitespace, line breaks, or the declaration order of object properties. For example, the following two objects are semantically equivalent:

~~~json
{"id": 42, "status": "PAID"}
~~~

~~~json
{
  "status": "PAID",
  "id": 42
}
~~~

By JSON semantics, an object is an unordered collection of name/value pairs; property order carries no meaning. By contrast, an array is an ordered sequence. Two arrays containing the same elements in different orders can represent different results if the API commits to ordering.

Spring MVC Test provides the **content().json(...)** matcher to parse and compare JSON structurally. This comparison lets tests focus on the returned data rather than string formatting produced by Jackson or another serializer.

## Strict vs. Lenient Comparison with MockMvc

In Spring Framework 6.1 (commonly found in Spring Boot 3.3), ContentResultMatchers provides two key overloads:

- **content().json(expectedJson, true):** strict comparison.
- **content().json(expectedJson, false):** lenient comparison.

The **content().json(expectedJson)** overload defaults to lenient mode. When reading a test, passing the boolean parameter explicitly often communicates intent more clearly.

Example endpoint returning a list of orders:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class OrderControllerTests {

    // Assume mockMvc is configured in the test class.

    @Test
    void returnsOrdersInTheContractualOrder() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(content().json("""
                        [
                          {"id": 101, "status": "NEW"},
                          {"id": 102, "status": "PAID"}
                        ]
                        """, true));
    }
}
~~~

With **true**, the test requires the JSON structure to match strictly: arrays must have matching element order and objects must not contain extra properties beyond the expected data. If the response swaps two orders or adds a field not present in the expected JSON, the comparison fails.

If the API only commits to returning the set of orders without guaranteeing order, use lenient mode:

~~~java
@Test
void returnsTheOrdersWithoutDependingOnTheirOrder() throws Exception {
    mockMvc.perform(get("/api/orders")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().json("""
                    [
                      {"id": 101, "status": "NEW"},
                      {"id": 102, "status": "PAID"}
                    ]
                    """, false));
}
~~~

Lenient mode allows array elements to appear in a different order and allows objects in the response to have additional properties. Fields specified in the expected JSON must still be present with matching values. Thus, the test above does not depend on the order of the two orders, while still checking each order's id and status.

## What Exactly Changes Between the Two Modes?

| Aspect | Strict (true) | Lenient (false) |
| --- | --- | --- |
| Property order inside an object | Ignored | Ignored |
| Element order inside an array | Must match | May differ |
| Extra object properties in the response | Rejected | Accepted |
| Expected field missing or wrong value | Fails | Fails |

A common misconception is that "strict" means the JSON must match character for character. Object property order is still not considered significant. Strict mode focuses on matching the expected structure and preserving array order.

For example, given the expected JSON:

~~~json
[
  {"id": 101, "status": "NEW"},
  {"id": 102, "status": "PAID"}
]
~~~

The following cases produce these results:

| Actual JSON | Strict | Lenient | Reason |
| --- | --- | --- | --- |
| Object swaps id and status order, array order unchanged | Pass | Pass | Key order inside an object has no semantic meaning |
| Two array elements swap positions | Fail | Pass | Only strict mode enforces array order |
| An object includes an extra createdAt field | Fail | Pass | Lenient mode accepts additional properties |
| Missing status or id | Fail | Fail | Expected data requirement is not met |
| status has a different value | Fail | Fail | Business value does not match |

Choose the mode based on the API contract. If list ordering is meaningful, such as an endpoint returning results sorted by time or priority, use strict comparison. If the API simply returns a collection without promising order, lenient comparison prevents tests from depending on unstable query or data-source ordering.

## When You Only Want to Ignore Array Order

The boolean parameter of **content().json(expectedJson, strict)** chooses between two common modes, but it toggles both policies together: array ordering and extra properties. Sometimes you want to ignore array order while still catching unexpected object properties not declared in the expected JSON.

JSONAssert provides four comparison modes to separate these two choices:

| JSONAssert Mode | Array Order | Extra Properties |
| --- | --- | --- |
| STRICT | Strict | Disallowed |
| LENIENT | Lenient | Allowed |
| NON_EXTENSIBLE | Lenient | Disallowed |
| STRICT_ORDER | Strict | Allowed |

If you need `NON_EXTENSIBLE` mode, you can extract the response from MockMvc and invoke JSONAssert directly:

~~~java
import org.skyscreamer.jsonassert.JSONAssert;
import org.skyscreamer.jsonassert.JSONCompareMode;
import org.springframework.test.web.servlet.MvcResult;

@Test
void ignoresArrayOrderButRejectsUnexpectedObjectFields() throws Exception {
    MvcResult result = mockMvc.perform(get("/api/orders")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andReturn();

    String expectedJson = """
            [
              {"id": 101, "status": "NEW"},
              {"id": 102, "status": "PAID"}
            ]
            """;

    String actualJson = result.getResponse().getContentAsString();

    JSONAssert.assertEquals(
            expectedJson,
            actualJson,
            JSONCompareMode.NON_EXTENSIBLE
    );
}
~~~

**NON_EXTENSIBLE** ignores array element order while still requiring objects to contain no extra fields. Conversely, **STRICT_ORDER** enforces array order while allowing additional object properties. Both modes are useful when an API contract needs a combination of structural and ordering policies different from the default strict/lenient options.

This snippet uses the JSONAssert library API (`org.skyscreamer:jsonassert`). This dependency is typically included via Spring Boot's test starter. If a project declares minimal test dependencies manually, ensure JSONAssert is on the test classpath before using these imports.

## Checking Partial Ordering with JsonPath

Not every test needs to compare the entire response. When the goal is to verify that a few key elements appear in the right positions, you can use jsonPath:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@Test
void placesTheHighestPriorityOrderFirst() throws Exception {
    mockMvc.perform(get("/api/orders/priority"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value(101))
            .andExpect(jsonPath("$[1].id").value(102));
}
~~~

The **$[0]** and **$[1]** expressions access the first and second elements of the root array. This approach verifies the positions of the IDs of interest while allowing the response to contain extra properties that the test does not need to assert.

JsonPath works well when only part of the structure or a few values need checking. When you need to verify the entire JSON payload, including nested fields, use **content().json(...)** or JSONAssert. Many scattered JsonPath assertions can miss absent fields or unexpected data that a full JSON comparison would catch.

## Combining JSON Comparison with Other HTTP Assertions

JSON comparison only verifies the response body. It does not replace checking status codes, content types, or headers. An MVC test should usually verify these aspects separately:

~~~java
mockMvc.perform(get("/api/orders/101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "id": 101,
                  "status": "NEW"
                }
                """, true));
~~~

Each assertion has a distinct purpose:

- **status().isOk()** verifies the HTTP status.
- **contentTypeCompatibleWith(...)** verifies the response has a JSON-compatible media type, even if the header includes a charset.
- **content().json(...)** verifies the body structure and data using the chosen mode.

If the API returns errors with a JSON structure, you can apply the same approach. Just specify the expected status and corresponding JSON body:

~~~java
mockMvc.perform(get("/api/orders/999999"))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "code": "ORDER_NOT_FOUND",
                  "message": "Order was not found"
                }
                """, true));
~~~

## Common Mistakes When Choosing a Mode

### Using Lenient Mode for an API with Business Ordering

An endpoint might commit to sorting orders newest first, search results by descending score, or workflow steps in sequence. Using **false** allows a test to pass even when the response violates the sorting contract. When order is part of the API contract, use **true** or JsonPath assertions at the relevant positions.

### Using Strict Mode When the API Allows Response Extension

An API may add metadata fields without altering existing fields. If tests always use **true**, even a valid additive field breaks the test. When the contract permits object extension and does not commit to array order, **false** is a better fit.

### Treating Object Key Reordering as a Bug

JSON objects do not carry property order. If key order changes while names and values remain identical, structural JSON comparison should still pass. If a system requires fixed string key ordering for a special reason, that is a separate serialization requirement and should be tested as a string or via the corresponding serializer contract.

### Confusing Array Order with Object Order

**strict=true** enforces array order, not that the serializer must emit id before status. Identify clearly which structures are arrays and which are objects before choosing a mode.

### Checking Only the Body While Forgetting Status and Content Type

A response with a valid JSON body and the wrong status code is still a wrong response. Combine body assertions with status and media type according to the endpoint contract.

### Using JsonPath for Every Case

JsonPath is great for asserting specific positions or values, but a large number of isolated assertions can make tests verbose and miss unexpected fields. Use full JSON comparison when the goal is to verify the entire payload.

## Decision Process for Choosing a Comparison Approach

1. Determine whether the endpoint commits to array element order.
2. Determine whether the response is allowed to add object properties without breaking the contract.
3. If either of the two common policy combinations fits, use **content().json(expected, true)** for strict or **content().json(expected, false)** for lenient.
4. If you need to ignore array order while still rejecting extra properties, use **JSONCompareMode.NON_EXTENSIBLE**; if you need to preserve array order while allowing extra properties, use **JSONCompareMode.STRICT_ORDER**.
5. If you only need to assert specific positions or fields, use **jsonPath** to express the condition directly.
6. Combine JSON comparison with HTTP status and content type checks to verify the full MVC result.

A good test reflects the endpoint's exact commitments. Strict mode catches unexpected changes in ordering and structure; lenient mode suits unordered data and extensible responses. When the two policies must be controlled independently, JSONAssert or JsonPath lets you express the exact requirement the test needs to protect.
