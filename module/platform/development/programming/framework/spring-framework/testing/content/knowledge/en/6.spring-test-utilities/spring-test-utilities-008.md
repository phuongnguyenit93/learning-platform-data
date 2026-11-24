# Utilities for Comparing JSON, XML, and Resources

When testing Spring applications, outputs are often represented as JSON, XML, or resource contents such as image files, PDFs, CSVs, and configuration files. Comparing raw strings or bytes directly is simple, yet it does not always express what actually needs protection. JSON can vary in property order or whitespace without changing meaning; XML can have namespaces and node structures to verify; binary resources need byte content and metadata comparisons.

Spring Test provides matchers for MockMvc and integrates with specialized libraries to check content. Common tools include:

- **ContentResultMatchers:** checks content type, encoding, strings, bytes, JSON, and XML of an HTTP response.
- **JsonPathResultMatchers:** queries a subset of JSON using JSONPath expressions.
- **XPathResultMatchers:** queries XML nodes and values using XPath.
- **Spring Resource abstraction:** reads resources from the classpath, filesystem, servlet context, or other data sources through one unified interface.
- **Resource and byte assertions:** verifies fixture files, downloaded content, or binary payloads.

The goal of this lesson is to choose comparison strategies that match the contract of the component under test, making assertions readable and less sensitive to formatting differences.

## 1. Choosing a comparison method based on data meaning

Before writing an assertion, identify what truly matters:

| Data | What needs verification | Suitable approach |
|---|---|---|
| JSON response | Structure, field values, array elements | JSON comparison or JSONPath |
| XML response | Node structure, attributes, namespaces, values | XML comparison or XPath |
| Text resource | Text content | Read Resource as string and compare |
| Binary resource | Bytes, content type, content length | Compare bytes and response metadata |
| File fixture | File exists, readable, expected content | Resource abstraction and assertions |

There are three common comparison levels:

1. **Exact verbatim comparison:** fits when formatting and every character are part of the contract, such as plain text output or strict file formats.
2. **Structural comparison:** fits JSON and XML when property ordering, whitespace, or formatting are not what is being tested.
3. **Partial comparison:** fits when only specific fields, nodes, or metadata matter; use JSONPath, XPath, or targeted assertions.

Do not use full-string comparison for every kind of data. An assertion should reflect what clients or dependent components are entitled to expect.

## 2. Checking JSON with MockMvc

Spring MVC Test provides ContentResultMatchers to verify the response body. For JSON, you can use the json method of the content matcher:

~~~java
mockMvc.perform(get("/api/products/42"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ))
    .andExpect(content().json("""
        {
          "id": 42,
          "name": "Keyboard",
          "active": true
        }
        """));
~~~

This example assumes the endpoint returns a product as JSON. The content type assertion checks that the response has a media type compatible with JSON; the json assertion compares content by JSON structure rather than requiring identical whitespace or presentation order.

### 2.1. Comparing JSON in strict and lenient modes

When using JSONAssert through Spring Test, the comparison mode determines strictness:

- **STRICT:** structure must match, extra fields are disallowed, and array element order must match.
- **LENIENT:** extra fields are allowed and array element order is not fixed; fields and values declared in expected must still be present and match.

You can specify the mode explicitly with JSONCompareMode:

~~~java
import org.skyscreamer.jsonassert.JSONCompareMode;

mockMvc.perform(get("/api/products/42"))
    .andExpect(status().isOk())
    .andExpect(content().json(
        """
        {
          "id": 42,
          "name": "Keyboard"
        }
        """,
        JSONCompareMode.STRICT
    ));
~~~

Choose STRICT when the response is a stable contract and unexpected extra fields should be caught. Choose LENIENT when the API is allowed to add fields or array order carries no meaning. If array order is a business rule, use strict mode or a dedicated ordering assertion.

Do not pick LENIENT solely to make a failing test pass. Before changing the mode, verify whether the API genuinely permits extra fields or varying array order.

### 2.2. Checking JSON with JSONPath

JSONPath works well when only a few fields need verification. Spring MVC Test provides the jsonPath matcher through MockMvcResultMatchers:

~~~java
mockMvc.perform(get("/api/products/42"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.name").value("Keyboard"))
    .andExpect(jsonPath("$.active").value(true));
~~~

JSONPath expressions start from the root symbol $. Dots access properties, while square brackets select array elements or special property names.

Example response:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "id": "CUS-20",
    "name": "An"
  },
  "items": [
    {"sku": "BOOK-01", "quantity": 2},
    {"sku": "PEN-02", "quantity": 3}
  ]
}
~~~

Assertions can focus on the needed fields:

~~~java
mockMvc.perform(get("/api/orders/ORD-100"))
    .andExpect(jsonPath("$.customer.id").value("CUS-20"))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items.length()").value(2))
    .andExpect(jsonPath("$.items[0].sku").value("BOOK-01"))
    .andExpect(jsonPath("$.items[1].quantity").value(3));
~~~

The JSONPath matcher supports several kinds of checks:

- value: the field's value or query result.
- exists and doesNotExist: presence or absence of the queried value.
- isEmpty and isNotEmpty: empty or non-empty collections/values.
- isArray and isMap: the queried structure type.
- value with a Hamcrest matcher: more flexible condition checks.

Example:

~~~java
mockMvc.perform(get("/api/orders/ORD-100"))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items").isNotEmpty())
    .andExpect(jsonPath("$.discountCode").doesNotExist());
~~~

When checking numeric values, pay attention to data types. JSON only has a number type; query libraries may convert values into specific Java types. If a matcher needs a specific type, specify the target type using the overload supported by your Spring version, or check with the appropriate numeric type. Do not coerce to a string when the JSON contract specifies a number.

### 2.3. Checking array elements and collections

If the response contains a list, decide whether order is significant:

~~~java
mockMvc.perform(get("/api/products"))
    .andExpect(jsonPath("$.products").isArray())
    .andExpect(jsonPath("$.products.length()").value(2))
    .andExpect(jsonPath("$.products[0].id").value(10))
    .andExpect(jsonPath("$.products[1].id").value(20));
~~~

This example protects both element count and order. If the API does not guarantee order, check elements by stable attributes or use JSON comparison in a mode that allows order changes. Avoid writing tests that depend on incidental database ordering.

For nested arrays, JSONPath lets you drill into the exact position:

~~~java
mockMvc.perform(get("/api/orders/ORD-100"))
    .andExpect(jsonPath("$.items[?(@.quantity > 1)].length()").value(1));
~~~

Filter expressions like this are useful for conditional queries, but keep expressions simple so readers understand what is being verified. For complex logic, parse the response into a JSON tree with ObjectMapper and write clear Java assertions.

### 2.4. Checking JSON null, missing fields, and empty fields

These three states are distinct:

- Field absent from JSON.
- Field present with value null.
- Field present with an empty string or empty collection.

Example:

~~~json
{
  "middleName": null,
  "tags": [],
  "displayName": ""
}
~~~

Do not treat these states as equivalent. An API may use null to denote no data yet, an empty array to denote a list currently without elements, and an omitted field to denote an unsupplied attribute.

When you need to distinguish a missing field from a null field, use an appropriate JSONPath check and verify node existence. If the JSONPath library or provider configuration makes missing vs. null hard to distinguish, parse the JSON into a JsonNode and inspect it directly:

~~~java
JsonNode root = objectMapper.readTree(responseBody);

assertTrue(root.has("middleName"));
assertTrue(root.get("middleName").isNull());
assertTrue(root.get("tags").isArray());
assertEquals(0, root.get("tags").size());
~~~

### 2.5. When to use full comparison vs. JSONPath?

| Need | Recommended tool |
|---|---|
| Response has a small schema and all fields are part of the contract | content().json with STRICT |
| API allows extra fields or unordered arrays | content().json with LENIENT |
| Only a few key fields matter | jsonPath |
| Need to check elements matching a condition | JSONPath filter or parsed JSON tree |
| Need to distinguish missing, null, and empty fields | JSONPath with existence check or JsonNode |
| Body is text with exact formatting | content().string |

Full comparison catches unexpected contract changes. JSONPath keeps tests focused on specific behavior and reduces coupling to unrelated fields. You can combine both when a test has key conditions that deserve dedicated expression.

## 3. Checking XML with MockMvc

XML has a tree structure consisting of elements, attributes, text nodes, and namespaces. Verbatim XML comparison is often overly sensitive to whitespace, newlines, and formatting. Spring Test supports structural XML comparison and XPath queries.

### 3.1. Comparing XML responses

You can use content().xml to verify XML responses:

~~~java
mockMvc.perform(get("/api/catalog/42")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_XML
    ))
    .andExpect(content().xml("""
        <product>
            <id>42</id>
            <name>Keyboard</name>
        </product>
        """));
~~~

Structural XML comparison makes tests less sensitive to newlines and indentation. Spring Test uses an XML comparison utility compatible with XMLUnit when verifying XML content; therefore, the corresponding XMLUnit dependency is needed on the test classpath when using this matcher.

When choosing a comparison strategy, determine whether child element order is part of the contract and whether attributes must be distinguished from elements. Two XML documents can represent similar data with different structures; tests should assert the exact structure clients rely on.

### 3.2. Querying XML with XPath

XPath lets you select nodes or values by path. Spring MVC Test provides the xpath matcher:

~~~java
mockMvc.perform(get("/api/catalog/42")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isOk())
    .andExpect(xpath("/product/id").string("42"))
    .andExpect(xpath("/product/name").string("Keyboard"));
~~~

Common matchers:

- node: checks the selected node.
- nodeCount: checks the number of nodes.
- exists and doesNotExist: checks whether a node exists.
- string: checks the string value.
- number: checks the numeric value.
- booleanValue: checks the boolean result of an XPath expression.

Example checking a list:

~~~java
mockMvc.perform(get("/api/catalog")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(xpath("/catalog/product").nodeCount(2))
    .andExpect(xpath("/catalog/product[1]/id").string("10"))
    .andExpect(xpath("/catalog/product[2]/id").string("20"));
~~~

XPath indexes node positions starting at 1 by default. This differs from Java array indices starting at 0. When checking multiple nodes, write indices according to XPath rules.

### 3.3. XPath with namespaces

XML with namespaces requires declaring a prefix in the XPath expression and mapping that prefix to a namespace URI. The prefix in XPath does not have to match the prefix used in the document; what matters is that the URI matches.

Example XML:

~~~xml
<p:product xmlns:p="urn:example:catalog">
    <p:id>42</p:id>
    <p:name>Keyboard</p:name>
</p:product>
~~~

The test can declare a namespace map:

~~~java
Map<String, String> namespaces = Map.of(
    "p", "urn:example:catalog"
);

mockMvc.perform(get("/api/catalog/42")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(xpath("/p:product/p:id", namespaces).string("42"))
    .andExpect(xpath("/p:product/p:name", namespaces).string("Keyboard"));
~~~

If you omit namespaces, the XPath expression may fail to find nodes even when the XML response contains the expected elements. This is a common issue when testing XML from SOAP services or namespace-aware APIs.

### 3.4. Checking attributes, nodes, and counts

XPath can select attributes using the @ symbol:

~~~xml
<product id="42" active="true">
    <name>Keyboard</name>
</product>
~~~

Corresponding assertions:

~~~java
mockMvc.perform(get("/api/catalog/42")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(xpath("/product/@id").string("42"))
    .andExpect(xpath("/product/@active").string("true"))
    .andExpect(xpath("/product/name").exists())
    .andExpect(xpath("/product/description").doesNotExist());
~~~

If you only need to check a node's presence, use exists or node. If you need to verify multiple nodes, use nodeCount. If you need to verify values, use string, number, or booleanValue so intent is explicit.

### 3.5. XML and whitespace

XML parsers can treat whitespace between elements differently from whitespace inside text nodes. For example, indentation whitespace between tags is usually not business data; however, whitespace inside a text element can be content that must be preserved.

Do not normalize XML strings by stripping all whitespace before comparing, as that can alter legitimate text content. Use XML structural comparison or XPath on the target element. If whitespace is part of the contract, write a dedicated assertion for that text node.

## 4. Reading and comparing resources with Spring Resource

Spring defines the Resource interface to access resources uniformly. Instead of forcing code to depend directly on File, Resource lets you work with the classpath, filesystem, URLs, or servlet context.

Common implementations:

| Resource implementation | Resource origin | Use case |
|---|---|---|
| ClassPathResource | Classpath | Fixture files in src/test/resources |
| FileSystemResource | Filesystem | Files at a specific path |
| UrlResource | URL | Resources via URL or URI |
| ByteArrayResource | In-memory byte array | Binary content built directly in tests |
| InputStreamResource | Existing InputStream | Stream source supplied externally |
| ServletContextResource | Web application resource | Resources inside ServletContext |

Resource provides operations such as exists, isReadable, getInputStream, contentLength, getFilename, and getURL. Not every implementation supports every operation in the same way.

### 4.1. Reading fixtures from the classpath

Place sample data in src/test/resources:

~~~text
src
└── test
    └── resources
        └── fixtures
            ├── product-response.json
            ├── catalog-response.xml
            └── sample-image.png
~~~

Reading a JSON fixture:

~~~java
Resource expectedJson = new ClassPathResource(
    "fixtures/product-response.json"
);

assertTrue(expectedJson.exists());
assertTrue(expectedJson.isReadable());

String expected = StreamUtils.copyToString(
    expectedJson.getInputStream(),
    StandardCharsets.UTF_8
);
~~~

Then you can pass expected to content().json or parse it with ObjectMapper to verify data. Close the stream after reading; use try-with-resources:

~~~java
String expected;
try (InputStream input = expectedJson.getInputStream()) {
    expected = StreamUtils.copyToString(
        input,
        StandardCharsets.UTF_8
    );
}
~~~

ClassPathResource keeps tests independent of Gradle's or the IDE's current working directory. Resources are looked up on the classpath, making it ideal for fixtures packaged with tests.

### 4.2. Reading binary resources and comparing bytes

For binary files, read into a byte array:

~~~java
Resource expectedFile = new ClassPathResource(
    "fixtures/sample-image.png"
);

byte[] expectedBytes;
try (InputStream input = expectedFile.getInputStream()) {
    expectedBytes = StreamUtils.copyToByteArray(input);
}
~~~

When an endpoint returns a file, you can compare the response body:

~~~java
mockMvc.perform(get("/api/files/sample-image"))
    .andExpect(status().isOk())
    .andExpect(content().contentType(MediaType.IMAGE_PNG))
    .andExpect(content().bytes(expectedBytes));
~~~

Byte comparison verifies exact content. If a file contains metadata that varies per generation, such as timestamps or dynamic headers inside an archive, full byte comparison can be too brittle. In such cases, parse the file structure with an appropriate library and verify the parts belonging to the contract.

### 4.3. Do not depend on getFile()

A common mistake is calling Resource.getFile() for every resource type. This method only works when the resource can be represented as a filesystem file. Classpath resources inside a JAR or resources coming from URLs/streams may not have a real file path.

Prefer getInputStream() for reading content. Use getFile() only when a test genuinely requires a filesystem file and you know the resource has a suitable backing file. This keeps tests working consistently in IDEs, Gradle, and packaged environments.

### 4.4. Using ResourceLoader

ResourceLoader provides an API to obtain a Resource from a location string:

~~~java
ResourceLoader resourceLoader = new DefaultResourceLoader();

Resource jsonFixture =
    resourceLoader.getResource("classpath:fixtures/product-response.json");

Resource localFile =
    resourceLoader.getResource("file:build/test-output/report.json");
~~~

Common prefixes:

- classpath: searches on the classpath.
- file: accesses the filesystem.
- https: or an appropriate URL scheme to access remote resources.

Paths without a prefix are handled according to the ResourceLoader's default rules. In tests, use explicit prefixes so readers know where the resource comes from. For external URLs, avoid making tests depend on the internet or uncontrolled services; use local fixtures or a test server.

## 5. Comparing JSON and XML loaded from fixture files

Fixtures make expected content readable, reusable, and prevent test methods from growing too long. However, fixtures must accurately reflect the test's contract and be stored in an easy-to-find location.

### 5.1. JSON fixture with content matcher

~~~java
@Test
void returnsProductDocument() throws Exception {
    // Arrange
    Resource fixture = new ClassPathResource(
        "fixtures/product-response.json"
    );
    String expected;
    try (InputStream input = fixture.getInputStream()) {
        expected = StreamUtils.copyToString(
            input,
            StandardCharsets.UTF_8
        );
    }

    // Act + Assert
    mockMvc.perform(get("/api/products/42"))
        .andExpect(status().isOk())
        .andExpect(content().json(expected, JSONCompareMode.STRICT));
}
~~~

This example uses a JSON fixture to verify the full contract. If the fixture is large and only a few fields need protection, JSONPath can keep the test shorter and more focused.

### 5.2. XML fixture with structural matcher

~~~java
@Test
void returnsCatalogXml() throws Exception {
    // Arrange
    Resource fixture = new ClassPathResource(
        "fixtures/catalog-response.xml"
    );
    String expected;
    try (InputStream input = fixture.getInputStream()) {
        expected = StreamUtils.copyToString(
            input,
            StandardCharsets.UTF_8
        );
    }

    // Act + Assert
    mockMvc.perform(get("/api/catalog")
            .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isOk())
        .andExpect(content().xml(expected));
}
~~~

If only one node in a large fixture needs verification, use XPath instead of comparing the entire XML document.

### 5.3. Organizing fixtures by purpose

Name files to reflect the scenario:

~~~text
fixtures/
├── product/
│   ├── product-active.json
│   └── product-not-found.json
├── catalog/
│   ├── catalog-with-items.xml
│   └── empty-catalog.xml
└── files/
    ├── sample-image.png
    └── report.csv
~~~

Avoid generic names like expected1.json or data.xml because it is hard to tell which scenario a fixture belongs to. If a fixture is used by only one test and is very short, declaring it inline inside the test method works fine. When content is large or shared across tests, fixture files make reviewing and updating easier.

## 6. Testing file uploads and multipart resources

Spring Test provides MockMultipartFile to simulate a multipart upload part in MVC tests. You can prepare the field name, filename, content type, and byte content:

~~~java
MockMultipartFile file = new MockMultipartFile(
    "document",
    "report.csv",
    "text/csv",
    "id,name\n1,Ada\n".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents")
        .file(file))
    .andExpect(status().isCreated());
~~~

This example tests an endpoint accepting a file with the field name document. When you need to confirm the file content was stored or processed properly, check the result via the service, repository, or response according to the endpoint's contract. A CREATED status alone does not prove the bytes were saved accurately.

For large files or multiple file types, prepare dedicated fixtures and read them with Resource:

~~~java
Resource csvFixture =
    new ClassPathResource("fixtures/files/report.csv");

byte[] content;
try (InputStream input = csvFixture.getInputStream()) {
    content = StreamUtils.copyToByteArray(input);
}

MockMultipartFile upload = new MockMultipartFile(
    "document",
    csvFixture.getFilename(),
    "text/csv",
    content
);
~~~

When testing uploads, verify meaningful edge cases such as empty files, unsupported content types, invalid filenames, size limits exceeded, and malformed content. MockMultipartFile simulates multipart data for tests; it does not prove browsers or networks send multipart payloads properly in a real environment.

## 7. Checking resource content type, encoding, and headers

Correct content with wrong metadata can still break clients. When testing endpoints that return files or JSON/XML, verify metadata belonging to the contract as well:

~~~java
mockMvc.perform(get("/api/reports/monthly"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_PDF
    ))
    .andExpect(header().exists(HttpHeaders.CONTENT_DISPOSITION))
    .andExpect(header().string(
        HttpHeaders.CONTENT_DISPOSITION,
        containsString("attachment")
    ));
~~~

For text responses, verify encoding and content:

~~~java
mockMvc.perform(get("/api/reports/export.csv"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.parseMediaType("text/csv")
    ))
    .andExpect(content().encoding("UTF-8"))
    .andExpect(content().string(containsString("id,name")));
~~~

Content types may include a charset parameter. Use contentTypeCompatibleWith when only media-type compatibility is needed; use contentType when an exact match is required by contract. Avoid asserting the full header string if parts of it are allowed to vary by environment.

## 8. Required dependencies for matchers

JSON/XML matchers in Spring Test may require corresponding supporting libraries on the test classpath. Spring Test integrates with specialized libraries rather than reimplementing every parser and comparator.

| Capability | Commonly used library | Role |
|---|---|---|
| JSON comparison via content().json | JSONassert | Structural JSON comparison and strict/lenient modes |
| JSONPath matcher | Jayway JsonPath | Querying JSON fields and nodes |
| XML comparison via content().xml | XMLUnit | Structural XML comparison |
| XPath matcher | XPath API and Spring Test support | Querying XML nodes/values |
| Reading Resource fixtures | Spring Core | Classpath, filesystem, and resource abstraction access |

In Spring Boot projects, the test starter typically brings in many common test libraries, though you should not assume every optional library is present in every setup. If a matcher reports a missing class or fails to create a parser, check the test runtime dependencies and compatible versions in your project's dependency management.

Conceptual Gradle declaration example:

~~~groovy
dependencies {
    testImplementation "org.springframework.boot:spring-boot-starter-test"

    // Only add individual libraries if the project's dependency graph does not already provide them.
    testImplementation "org.skyscreamer:jsonassert"
    testImplementation "com.jayway.jsonpath:json-path"
    testImplementation "org.xmlunit:xmlunit-core"
}
~~~

Versions should be managed by Spring Boot dependency management or an existing version catalog. Avoid pinning versions manually that differ from the project's dependency set without checking compatibility.

## 9. Writing diagnostic-friendly assertions

A good assertion shows what the test protects and helps pinpoint differences quickly. Apply these principles:

- Use JSONPath for key fields instead of comparing a long JSON string when only part of the response is contractual.
- Use structural JSON comparison when protecting the whole response schema.
- Use XPath to target exact nodes, especially in namespace-aware XML.
- Use Resource to load fixtures from the classpath rather than concatenating relative paths tied to the working directory.
- For binary files, check both bytes and necessary metadata.
- When responses contain dynamic values, check stable fields via JSONPath/XPath or exclude/normalize dynamic parts before comparing.
- When assertions fail, keep expected fixtures and actual responses clear enough to spot mismatches.

If JSON/XML contains timestamps, generated IDs, or host-dependent URLs, do not guess values in the expected fixture. Verify format, data type, relationships, or stable parts of the value. If values must be deterministic per contract, control the clock or generation logic in tests.

### 9.1. Avoiding over-asserting non-contract details

A response may accumulate internal metadata over time. If an API allows extension, checking the entire response in STRICT mode can create high maintenance cost. Conversely, if the API has a closed schema or clients consume the exact structure, strict comparison provides valuable protection.

Choose assertions from the consumer's perspective:

- Which fields does the consumer need?
- Can a field be absent or null?
- Does the array have a guaranteed order?
- Are XML namespaces part of the contract?
- Must a downloaded file match byte-for-byte or only logically?

### 9.2. Avoiding one fixture for multiple meanings

If the same fixture is reused across many tests with different goals, a small change can break many tests and obscure which test protects which contract. Split fixtures by scenario or use builders to create clearly named test data.

## 10. Common mistakes

### 10.1. Comparing JSON as a verbatim string

JSON remains valid even when whitespace or key order differs. Use content().string when exact formatting is required; use content().json or JSONPath when verifying structure.

### 10.2. Using LENIENT without understanding its implications

LENIENT allows extra fields and ignores array ordering. This can miss unintended changes if the contract requires a closed structure or specific ordering. Choose the mode based on API requirements.

### 10.3. Forgetting namespaces in XPath

XPath cannot always locate namespaced elements using only the local name. Declare a namespace map and use prefixes in the expression.

### 10.4. Confusing JSON array indices and XML node positions

JSONPath typically uses 0-based array indices, while XPath uses 1-based node positions. Check index offsets when switching assertions between the two formats.

### 10.5. Calling getFile() on classpath resources inside a JAR

A resource may not exist as a filesystem file. Use getInputStream() to read content portably.

### 10.6. Reading InputStreamResource multiple times

InputStreamResource typically wraps a stream that can be read only once. If multiple reads are required, use a resource capable of opening fresh streams or buffer bytes into a ByteArrayResource.

### 10.7. Checking only status on file downloads

A 200 status does not prove the body is right. Check content type, download headers, and bytes or structural content.

### 10.8. Ignoring encoding

Reading files with the machine's default charset can cause tests to behave differently across environments. Specify UTF-8 or the contractual charset when converting bytes to strings.

### 10.9. Fixtures tied to local paths

Absolute paths on a personal machine are unstable in CI. Place fixtures in src/test/resources and use ClassPathResource.

## 11. Pattern combining JSONPath, XPath, and Resource

An MVC test can combine utilities depending on each endpoint's purpose. Example with JSON:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ProductService productService;

    @Test
    void returnsProductFields() throws Exception {
        given(productService.findById(42L))
            .willReturn(new ProductDto(42L, "Keyboard", true));

        mockMvc.perform(get("/api/products/42"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.name").value("Keyboard"))
            .andExpect(jsonPath("$.active").value(true));
    }
}
~~~

This example assumes the controller and DTO have the corresponding methods. JSONPath makes the fields the endpoint must return explicit. If the entire JSON contract needs protection, replace or supplement it with content().json and an expected fixture.

With XML:

~~~java
@WebMvcTest(CatalogController.class)
class CatalogControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsCatalogElements() throws Exception {
        mockMvc.perform(get("/api/catalog")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isOk())
            .andExpect(xpath("/catalog/product").nodeCount(2))
            .andExpect(xpath("/catalog/product[1]/id").string("10"));
    }
}
~~~

With binary resources:

~~~java
@Test
void downloadsExpectedFile() throws Exception {
    Resource fixture =
        new ClassPathResource("fixtures/sample-image.png");

    byte[] expected;
    try (InputStream input = fixture.getInputStream()) {
        expected = StreamUtils.copyToByteArray(input);
    }

    mockMvc.perform(get("/api/files/sample-image"))
        .andExpect(status().isOk())
        .andExpect(content().contentType(MediaType.IMAGE_PNG))
        .andExpect(content().bytes(expected));
}
~~~

All three examples share the same structure: prepare expected data, send a request via MockMvc, and assert the response. The matcher varies with the nature of the content.

## 12. Workflow for choosing a utility

When writing tests for an endpoint or data-returning component, follow this sequence:

1. Identify the media type and content format: JSON, XML, text, or binary.
2. Identify the contract to protect: full structure, selected fields/nodes, or exact bytes.
3. Choose the matcher: JSON comparison, JSONPath, XML comparison, XPath, string, or bytes.
4. If expected content is long, put fixtures in src/test/resources and load them with Resource.
5. Verify content type, encoding, and download headers when part of the contract.
6. Run tests in the project's build setup to catch missing test dependencies.

For JSON, use structural comparison when the full schema matters and JSONPath when only certain fields need checking. For XML, use XML comparison for entire documents and XPath for specific nodes or values, handling namespaces explicitly. For resources, use Resource to read data sources and choose string or byte comparison appropriate to the content type.

## Conclusion

Spring Test combines MockMvc's JSON/XML matchers with JSONPath, XPath, and the Resource abstraction to verify responses at the right structural level. JSON should be compared by contract or queried by field; XML should be compared structurally or targeted by XPath; fixture files and downloadable resources should be read via Resource and checked for both content and required metadata. Choosing the right comparison strategy clarifies client expectations and reduces failures from meaningless formatting differences.
