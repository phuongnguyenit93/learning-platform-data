# Query Parameters, Form Parameters, and Encoding

When testing a Spring MVC endpoint with MockMvc, we often need to send data through the URL or through the request body. Two common mechanisms are **query parameters** and **form parameters**. Both can be bound by Spring into controller parameters using **@RequestParam**, yet they reside in different parts of the HTTP request and have encoding rules that need to be clearly understood.

For example, the following two requests can carry the same pair of data:

~~~http
GET /search?keyword=spring&page=2
~~~

~~~http
POST /search
Content-Type: application/x-www-form-urlencoded

keyword=spring&page=2
~~~

The first request passes data in the URI's query string. The second request passes data in the body in form URL-encoded format. When using the Servlet API, both the query string and the form body can contribute to the request parameter map. As a result, a controller using @RequestParam can receive values from either source.

## 1. Query Parameters in the URI

Query parameters appear after the question mark in the URI. Name-value pairs are usually separated by ampersands:

~~~text
/products?keyword=java&page=2&tag=spring&tag=mvc
~~~

In this example:

- keyword has the value java.
- page has the value 2.
- tag appears twice, with values spring and mvc respectively.

Query parameters are suitable for data used to identify or filter resources, such as search keywords, filters, sort order, and page numbers. For GET requests, this is typically the primary way to pass input data.

A controller can receive these values using @RequestParam:

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/products")
    ProductSearchResult search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(name = "tag", required = false) List<String> tags
    ) {
        List<String> selectedTags = tags == null ? List.of() : tags;
        return new ProductSearchResult(keyword, page, selectedTags);
    }
}

record ProductSearchResult(
    String keyword,
    int page,
    List<String> tags
) {}
~~~

MockMvc can build a query string using queryParam:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/products")
        .queryParam("keyword", "spring")
        .queryParam("page", "2")
        .queryParam("tag", "spring", "mvc"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.keyword").value("spring"))
    .andExpect(jsonPath("$.page").value(2))
    .andExpect(jsonPath("$.tags[0]").value("spring"))
    .andExpect(jsonPath("$.tags[1]").value("mvc"));
~~~

queryParam explicitly indicates that the data belongs to the query string. Multiple values can be passed for the same name to test repeated parameters. When you need to verify the actual URL or query string as well, use this API rather than merely adding entries to the parameter map.

## 2. Form Parameters in the Request Body

Form parameters are typically sent via POST with the media type application/x-www-form-urlencoded. The body contains name-value pairs formatted as:

~~~text
username=alice&city=Hanoi
~~~

This format resembles a query string in structure, except the data lives in the body. Browsers typically generate this kind of request when submitting a standard HTML form without multipart upload.

An endpoint handling a form can use @RequestParam:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @PostMapping(
        path = "/profile",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    ProfileResult update(
        @RequestParam String displayName,
        @RequestParam String city
    ) {
        return new ProfileResult(displayName, city);
    }
}

record ProfileResult(String displayName, String city) {}
~~~

In MockMvc, the common way to test form field binding is to use param together with the appropriate content type:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(post("/profile")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("displayName", "Nguyễn Văn An")
        .param("city", "Hồ Chí Minh"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").value("Nguyễn Văn An"))
    .andExpect(jsonPath("$.city").value("Hồ Chí Minh"));
~~~

Here, param places the already-decoded values into the simulated request's parameter map. This approach works well for testing controller binding, validation, and processing outcomes. It does not by itself verify how a URL-encoded byte sequence in the body is decoded by a Servlet container. If the goal is to test the HTTP-level body parsing step itself, test against a real server/container or configure request builders and filters appropriate for the Spring version in use.

If you want to bind the entire form into an object, @ModelAttribute can be used:

~~~java
public class RegistrationForm {
    private String displayName;
    private String city;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

~~~java
@PostMapping(
    path = "/registration",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
RegistrationForm register(@ModelAttribute RegistrationForm form) {
    return form;
}
~~~

The test can submit individual fields:

~~~java
mockMvc.perform(post("/registration")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("displayName", "Lan")
        .param("city", "Da Nang"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").value("Lan"))
    .andExpect(jsonPath("$.city").value("Da Nang"));
~~~

## 3. Distinguishing queryParam, param, and Form Data in MockMvc

MockMvc provides several APIs that look similar yet serve different purposes:

| API | Meaning when building the request | When to use |
|---|---|---|
| queryParam(name, values...) | Adds values to the URI query string and the request parameter map. | When you want to clearly express query parameters and verify how the URL is built. |
| param(name, values...) | Adds values directly to the request parameter map. | When testing @RequestParam binding without needing to simulate the wire-level location of the data. |
| params(multiValueMap) | Adds a prepared group of request parameters. | When a test has many parameters or data generated from fixtures. |
| content(body) | Sets the raw request body. | When the endpoint reads the body, or when you need to test the payload at the content level. |
| contentType(mediaType) | Sets the request Content-Type. | When the endpoint requires form data, JSON, or a specific media type. |

One very important point: param is not synonymous with creating a query string. It places values into the parameter map of MockHttpServletRequest. Therefore, a test using param can cause the controller to receive @RequestParam without proving that the URL has the expected query string.

Conversely, queryParam explicitly indicates that the data lies in the URI. For URL-encoded forms, param is usually the convenient choice for testing how form fields bind into the controller. Set contentType to application/x-www-form-urlencoded so the mock request reflects the content type required by the endpoint.

Do not use content("a=1&b=2") and assume MockMvc will automatically parse the body into Servlet parameters identically to a real HTTP server across all configurations. The raw body and the parameter map are two separate parts of the simulated request. Choose the API that matches the layer of behavior you want to test.

## 4. Where Does @RequestParam Get Its Data?

In Spring MVC running on the Servlet API, @RequestParam binds to request parameters. A Servlet request's parameter map can contain data parsed from the query string and from the form body of an appropriate request.

This means a controller such as:

~~~java
@GetMapping("/search")
SearchResult search(@RequestParam String keyword) {
    return new SearchResult(keyword);
}
~~~

can receive keyword from:

~~~http
GET /search?keyword=spring
~~~

And a form-handling controller:

~~~java
@PostMapping(
    path = "/search",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
SearchResult searchForm(@RequestParam String keyword) {
    return new SearchResult(keyword);
}
~~~

can receive keyword from the form body:

~~~http
POST /search
Content-Type: application/x-www-form-urlencoded

keyword=spring
~~~

If the same name appears in both the query string and the form body, the Servlet request may provide multiple values for the same parameter name. Do not build logic on the assumption that one source always wins over the other. If the API needs to distinguish between the two locations, design an explicit input contract and test each source separately.

### Binding Cases to Test

| Case | Behavior to verify |
|---|---|
| Missing required parameter | By default Spring returns a client error, typically HTTP 400 due to a missing request parameter. |
| Parameter with defaultValue | The default value is used when the parameter is missing or empty according to @RequestParam rules. |
| required = false | The controller can receive null when the parameter is not sent. |
| Optional<T> | Optional parameters can be represented using Optional. |
| Multiple values with the same name | Use List<T> or an array to receive multiple values. |
| Wrong data type | Verify conversion errors, such as a string that cannot be parsed into an int. |
| Empty value | Distinguish a missing parameter from a parameter with an empty string value if business logic requires it. |

Example testing repeated parameters:

~~~java
mockMvc.perform(get("/products")
        .queryParam("tag", "spring", "mvc", "testing"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.tags.length()").value(3));
~~~

Example testing a missing required parameter:

~~~java
mockMvc.perform(get("/products"))
    .andExpect(status().isBadRequest());
~~~

Example testing a default value:

~~~java
mockMvc.perform(get("/products")
        .queryParam("keyword", "spring"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page").value(1));
~~~

## 5. URL Encoding and Form Encoding

HTTP requests transmit data in the URI or body as byte sequences. Characters outside the safe set must be represented using the appropriate encoding rules. For URIs, the common representation is percent-encoding: each byte is written as a percent sign followed by two hexadecimal digits.

For URL-encoded forms, names and values are joined by an equals sign, and pairs are joined by an ampersand. Spaces are typically represented by a plus sign. Characters with structural meaning such as ampersand, equals sign, plus sign, or percent sign inside a value itself must be encoded so they are not mistaken for delimiter syntax.

For example, the value:

~~~text
red & blue + green
~~~

cannot be inserted verbatim into a form body because the ampersand could be interpreted as starting a new field. The corresponding form-encoded representation can be:

~~~text
color=red+%26+blue+%2B+green
~~~

In this representation:

- Spaces are represented by plus signs in form encoding.
- The ampersand character inside the value is represented by %26.
- A literal plus sign in the value is represented by %2B.

For Vietnamese text, characters are encoded into UTF-8 bytes and then percent-encoded. For example, part of the value Nguyễn Văn An can appear in a form body as:

~~~text
Nguy%E1%BB%85n+V%C4%83n+An
~~~

It is crucial to distinguish the **decoded Java value** from the **string transmitted on the wire**. When using MockMvc param or queryParam, we pass logical values such as Nguyễn Văn An. Do not pre-encode and then pass the already-encoded string into these APIs, because the result may be double-encoded or the controller may receive literal % characters.

### Plus Signs and Spaces

In URL-encoded forms, the plus sign represents a space. Therefore, if a value actually contains a plus sign, it must be encoded as %2B. For example:

~~~text
q=C%2B%2B
~~~

represents the value C++.

If you send:

~~~text
q=C++
~~~

the form decoder may interpret it as C followed by two spaces. This is a common mistake when manually concatenating query strings or form bodies.

### Ampersands and Equals Signs

Ampersands separate parameter pairs, while equals signs separate names from values. If they appear inside data, they must be encoded:

| Character in value | Percent-encoded representation |
|---|---|
| & | %26 |
| = | %3D |
| + | %2B |
| % | %25 |

Do not encode the entire query string all at once. Encode each name and each value using the proper URI or form-body builder APIs so structural delimiters remain intact.

## 6. Encoding in MockMvc Tests

MockMvc can test decoded values by passing Strings directly into queryParam or param:

~~~java
mockMvc.perform(get("/search")
        .queryParam("keyword", "cà phê & trà")
        .queryParam("sort", "name+asc"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.keyword").value("cà phê & trà"))
    .andExpect(jsonPath("$.sort").value("name+asc"));
~~~

When building the URI, MockMvc handles placing query values into the request. We do not need to manually replace spaces with plus signs or ampersands with %26 before calling queryParam.

For form parameters, the usual way to test binding also passes decoded values:

~~~java
mockMvc.perform(post("/profile")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding("UTF-8")
        .param("displayName", "Nguyễn Văn An")
        .param("note", "A&B + C"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").value("Nguyễn Văn An"))
    .andExpect(jsonPath("$.note").value("A&B + C"));
~~~

characterEncoding sets the encoding of the simulated request. However, when using param, the values have already been provided directly as Java Strings. This test verifies that binding receives the Unicode characters properly; it does not verify that the raw form body bytes were encoded and decoded accurately.

If you need to construct a form-encoded string manually, Java provides URLEncoder with the UTF-8 charset:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String encodedName = URLEncoder.encode(
    "Nguyễn Văn An",
    StandardCharsets.UTF_8
);
~~~

URLEncoder produces data according to application/x-www-form-urlencoded rules, where spaces become plus signs. It is suitable when deliberately building a form body. Do not use URLEncoder to encode a value and then pass it to queryParam or param, because these MockMvc APIs accept unencoded logical values.

If you need to test the decoding of the raw form body itself, identify the exact Servlet container, request encoding, and filters processing the request. A MockMvc test using the parameter map tests controller binding very well, but does not fully replace end-to-end HTTP testing for the container's form decoder.

## 7. Request Charset and Unicode Data

Encoding is not just replacing characters with %xx. Both sides must agree on the charset to convert between bytes and characters. If the client sends UTF-8 but the server decodes with a different charset, data can suffer mojibake—for example, Vietnamese characters turning into garbled character sequences.

When simulating a form request in MockMvc, you can specify it explicitly:

~~~java
mockMvc.perform(post("/profile")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding(StandardCharsets.UTF_8.name())
        .param("displayName", "Đặng Thị Mai"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").value("Đặng Thị Mai"));
~~~

With real requests, the encoding configuration must be applied before the Servlet container reads request parameters. In a Spring MVC application, verify the web stack's encoding configuration and related filters, especially when supporting legacy clients or form data containing Unicode. Do not assume that setting the charset in just any single place suffices for every layer.

The query string and the form body follow different processing paths. The query string is parsed from the URI; the form body is parsed according to the content type and request encoding. Therefore, if an issue only appears in one source, inspect that source's transport path and decoding mechanism separately.

## 8. When to Use Query Parameters, Form Parameters, or a Request Body?

| Data style | Where transmitted | Example | Common test approach |
|---|---|---|---|
| Query parameter | URI after the ? | GET /products?category=book | get(...).queryParam(...) |
| Form parameter | application/x-www-form-urlencoded body | POST /login with username and password | post(...).contentType(APPLICATION_FORM_URLENCODED).param(...) |
| JSON request body | application/json body | POST /orders with JSON object | post(...).contentType(APPLICATION_JSON).content(...) |
| Multipart field/file | multipart/form-data body | Upload image with description | multipart(...) with appropriate param/file parts |
| Path variable | A segment of the URI path | GET /orders/123 | get("/orders/{id}", 123) |

Query parameters are usually suited for filtering and query criteria. Form parameters suit data submitted from HTML forms. JSON bodies typically fit APIs accepting a structured object. Path variables represent resource identifiers or hierarchy. Multipart is used for file uploads or forms with multiple part types.

Do not use @RequestBody to accept form data out of habit when the endpoint is designed to bind Servlet request parameters. For URL-encoded forms in Spring MVC, @RequestParam and @ModelAttribute are usually more appropriate. For JSON, use @RequestBody and send application/json.

## 9. A Practical Test Suite for Query and Form Data

A test class using @WebMvcTest can initialize controllers and MockMvc to test request binding without running a real HTTP server:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest({ProfileController.class, ProductController.class})
class ProfileControllerTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void bindsQueryParameters() throws Exception {
        mockMvc.perform(get("/products")
                .queryParam("keyword", "cà phê & trà")
                .queryParam("page", "2")
                .queryParam("tag", "spring", "mvc"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.keyword").value("cà phê & trà"))
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.tags[0]").value("spring"))
            .andExpect(jsonPath("$.tags[1]").value("mvc"));
    }

    @Test
    void bindsUrlEncodedFormParameters() throws Exception {
        mockMvc.perform(post("/profile")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding("UTF-8")
                .param("displayName", "Nguyễn Văn An")
                .param("city", "Hồ Chí Minh"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Nguyễn Văn An"))
            .andExpect(jsonPath("$.city").value("Hồ Chí Minh"));
    }
}
~~~

The example demonstrates two independent requests. In a real project, substitute the controller and endpoints with the classes under test; if the controller depends on services, configure mock beans according to the project's Spring Boot version. There is no need to start a real server when the goal is only to verify Spring MVC mapping and binding.

Additional test cases should be added according to the API contract:

1. Normal query parameter with an ASCII value.
2. Query parameter containing spaces, Vietnamese characters, plus signs, and ampersands.
3. Multiple values for the same parameter name.
4. Unicode form fields and values with special characters.
5. Missing required parameters, empty parameters, and default values.
6. Values that cannot be converted to the target data type.
7. Requests with the wrong Content-Type when the endpoint declares consumes.

## 10. Common Mistakes

### Using param and Concluding the Query String Is Correct

param adds data to the request parameter map. If you need to verify the URI query string, use queryParam or inspect the request URI/query string in an appropriate way. These two goals are not the same.

### Double-Encoding Values

If you call URLEncoder first and then pass the result into queryParam or param, percent signs in the already-encoded string may be encoded again. For example, %26 can become %2526. Pass raw logical values into MockMvc builders.

### Confusing Plus Signs with Spaces

In form encoding, a plus sign represents a space. A literal plus sign in data must be represented as %2B on the wire. When using param or queryParam, pass the literal plus sign in the Java String and let the builder handle it.

### Ignoring the Form Content-Type

A POST request with param does not automatically prove the endpoint accepted the right form type. If the endpoint requires application/x-www-form-urlencoded, set the matching contentType and also test the wrong media type case when needed.

### Thinking content(body) Automatically Populates Request Parameters

content sets the raw body. param sets request parameters. These two APIs play different roles. If the controller binds using @RequestParam, make sure the test supplies parameters in a way supported by MockHttpServletRequest.

### Testing Only ASCII

Simple values like abc do not expose encoding bugs. Include tests with Vietnamese characters, spaces, plus signs, ampersands, and percent signs to uncover discrepancies between logical data and wire-level data.

### Confusing URL-Encoded Forms with JSON

application/x-www-form-urlencoded and application/json are two different formats. An endpoint accepting @RequestParam or @ModelAttribute is not equivalent to an endpoint accepting @RequestBody. Tests must send the exact Content-Type and data structure published by the controller.

## 11. How to Choose the MockMvc API

When writing a test request, start from the endpoint's HTTP contract:

1. If the data resides in the URI after the question mark, use queryParam to express the query string.
2. If you want to test binding of Servlet request parameters without caring where the data is transmitted, use param.
3. If sending a URL-encoded form, set Content-Type to application/x-www-form-urlencoded and use param for regular binding tests.
4. If you need to test the raw body or HTTP-level parsing/encoding, use tests suited for the raw body and Servlet container; do not infer that from the parameter map alone.
5. If the endpoint accepts JSON, send a JSON body with application/json and test @RequestBody.
6. If values contain Unicode or structural characters, pass raw data into the builder and verify the value received by the controller.

Clearly understanding where data resides, the role of each MockMvc request builder, and the boundary between decoded values and bytes transmitted on the wire helps tests reflect the HTTP contract accurately. Query parameters, form parameters, and encoding are closely related, yet each piece needs to be verified at the proper layer of the request.
