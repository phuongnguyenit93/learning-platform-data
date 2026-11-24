# XPath and XML Content

## 1. Asserting XML Responses in MVC Testing

When testing a Spring MVC endpoint that returns XML, you need to verify both the data structure and the values that clients actually receive. `MockMvc` provides two suitable matcher groups:

- `content().xml(...)` compares the entire response body against an expected XML document.
- `xpath(...)` evaluates an XPath expression on the response body and asserts the result as a string, number, boolean, or node count.

The two checks complement each other. Full XML comparison detects missing, extra, or mismatched elements and attributes across the whole document. XPath focuses on a specific condition, such as an identifier, total element count, or the content of an important node.

These matchers are commonly placed after `status()` and content-type matchers in a `mockMvc.perform(...).andExpect(...)` chain. They verify the response produced through the MVC processing pipeline rather than merely invoking the controller method directly.

## 2. Preparing an Endpoint Returning XML

The example below uses a controller that returns an XML string. Declaring `produces` lets Spring MVC advertise the response media type as `application/xml`.

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    @GetMapping(value = "/catalog", produces = MediaType.APPLICATION_XML_VALUE)
    String catalog() {
        return """
                <?xml version="1.0" encoding="UTF-8"?>
                <catalog>
                    <book id="bk-1">
                        <title>Spring MVC Testing</title>
                        <price>29.5</price>
                    </book>
                    <book id="bk-2">
                        <title>XML in Practice</title>
                        <price>35.0</price>
                    </book>
                </catalog>
                """;
    }
}
```

In this example the controller returns a `String`, so the body is pre-built XML content. In real applications, a controller can also return an object serialized by an XML message converter. Either way, MVC tests should verify both the media type and the final response content.

## 3. Comparing Full XML with `content().xml()`

`content().xml(expectedXml)` takes an expected XML string and compares it against the response body. Spring uses XMLUnit to perform the XML comparison. Because comparison is based on XML structure, differences in indentation or formatting whitespace typically do not fail the test. This is not a byte-for-byte or verbatim string comparison.

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(CatalogController.class)
class CatalogControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsExpectedCatalogXml() throws Exception {
        String expectedXml = """
                <catalog>
                    <book id="bk-1">
                        <title>Spring MVC Testing</title>
                        <price>29.5</price>
                    </book>
                    <book id="bk-2">
                        <title>XML in Practice</title>
                        <price>35.0</price>
                    </book>
                </catalog>
                """;

        mockMvc.perform(get("/catalog").accept(MediaType.APPLICATION_XML))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_XML))
                .andExpect(content().xml(expectedXml));
    }
}
```

`contentTypeCompatibleWith(...)` confirms the response has a media type compatible with `application/xml`, even when the header includes parameters such as charset. `content().xml(...)` then verifies the body matches the expected structure and data.

Because Spring Test's XML comparison relies on XMLUnit, the project must have `xmlunit-core` on the test runtime classpath. If this dependency is not already provided by your test configuration or dependency management, you can declare it in Gradle:

```groovy
dependencies {
    testImplementation("org.xmlunit:xmlunit-core")
}
```

When using Spring Boot dependency management, let the BOM manage the version if that artifact is already managed; otherwise, declare a version compatible with your project's dependency set.

## 4. Selecting Data with XPath

XPath expresses paths or computations over an XML document. In MockMvc, the static `xpath(...)` method of `MockMvcResultMatchers` creates an `XpathResultMatchers` instance to assert the expression's result on the response body.

Commonly used matchers:

| Matcher | XPath Result Checked | Example |
|---|---|---|
| `string(expected)` | String value of the expression | `xpath("/catalog/book[1]/title").string("Spring MVC Testing")` |
| `number(expected)` | Numeric value | `xpath("count(/catalog/book)").number(2.0)` |
| `booleanValue(expected)` | Boolean value | `xpath("boolean(/catalog/book[@id='bk-1'])").booleanValue(true)` |
| `nodeCount(expected)` | Number of nodes selected by the expression | `xpath("/catalog/book").nodeCount(2)` |

Example combining multiple assertions on the same response:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.xpath;

@Test
void exposesExpectedBookFields() throws Exception {
    mockMvc.perform(get("/catalog").accept(MediaType.APPLICATION_XML))
            .andExpect(status().isOk())
            .andExpect(xpath("/catalog/book").nodeCount(2))
            .andExpect(xpath("/catalog/book[@id='bk-1']/title")
                    .string("Spring MVC Testing"))
            .andExpect(xpath("/catalog/book[@id='bk-2']/price")
                    .string("35.0"))
            .andExpect(xpath("count(/catalog/book)").number(2.0))
            .andExpect(xpath("boolean(/catalog/book[@id='bk-1'])")
                    .booleanValue(true));
}
```

The expression `/catalog/book[@id='bk-1']/title` selects the `title` element inside the `book` whose `id` attribute equals `bk-1`. `string(...)` asserts the text value of the selected node. The `count(...)` expression returns the number of matching nodes, while `boolean(...)` evaluates the result to a boolean value.

`nodeCount(...)` is useful when you need to confirm that the selected node set has an exact count. To confirm no matching elements exist, use `nodeCount(0)` with the corresponding expression.

## 5. Working with XML Namespaces

XML namespaces directly affect how XPath selects nodes. Consider a document using a default namespace:

```xml
<catalog xmlns="urn:example:catalog">
    <book id="bk-1">
        <title>Spring MVC Testing</title>
    </book>
</catalog>
```

Even though the document does not write a prefix before `catalog` and `book`, those elements still belong to the namespace URI `urn:example:catalog`. The expression `/catalog/book` will not match them automatically because XPath does not automatically inherit the document's default namespace.

Provide a prefix-to-namespace-URI map when creating the matcher:

```java
import java.util.Map;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.xpath;

@Test
void selectsElementsInDefaultNamespace() throws Exception {
    Map<String, String> namespaces = Map.of(
            "c", "urn:example:catalog");

    mockMvc.perform(get("/catalog").accept(MediaType.APPLICATION_XML))
            .andExpect(xpath("/c:catalog/c:book", namespaces).nodeCount(1))
            .andExpect(xpath("/c:catalog/c:book/c:title", namespaces)
                    .string("Spring MVC Testing"));
}
```

The `c` prefix is chosen by the test. It only needs to map to the right namespace URI; it does not have to match the prefix used in the XML response. This rule also applies when the XML uses different prefixes for the same namespace URI.

When XPath finds no nodes in a namespaced document, check the namespace URI and prefix mapping before concluding the controller returned the wrong structure. This is a common cause of unexpected `nodeCount(0)` or string matcher failures.

## 6. Choosing Between XML Matchers and XPath Matchers

| Testing Need | Appropriate Matcher | Reason |
|---|---|---|
| Verify full XML structure and data | `content().xml(expectedXml)` | A single assertion verifies the overall XML document. |
| Verify a critical field | `xpath(...).string(...)` | Pinpoints the exact node and value to check. |
| Verify element count | `xpath(...).nodeCount(...)` | Directly checks the selected node set size. |
| Verify a condition or computation | `xpath(...).booleanValue(...)` or `number(...)` | Expresses the condition as an XPath expression. |
| Verify exact characters or bytes | `content().string(...)` or `content().bytes(...)` | Use when whitespace, character sequence, or encoding is part of the tested contract. |

There is no need to duplicate all data with both an XML matcher and multiple XPath matchers if a full-document comparison already captures all requirements. Conversely, XPath is very useful when a test should highlight a specific business rule or when only part of the document matters for the test case.

You can combine both matcher groups in the same test when they answer different questions: `content().xml(...)` verifies the overall XML response, while XPath highlights a key condition that readers of the test should see clearly.

## 7. Common Errors and How to Handle Them

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `content().xml(...)` reports missing XMLUnit or cannot create XML diff | `xmlunit-core` is missing from the test runtime classpath. | Check test dependencies and add `org.xmlunit:xmlunit-core` if needed. |
| XPath matcher fails to parse the response | Empty body, malformed XML, or non-XML response content. | Check status, actual body, character escaping, and tag open/close structure. |
| XPath selects 0 nodes even though elements are in the XML | Wrong path expression or missing namespace mapping. | Check element names, case sensitivity, and namespace URI; supply a prefix map to XPath. |
| `string(...)` returns an empty string | Expression selects the wrong node or the node lacks the expected text value. | Recheck path, predicates, and nesting; use `nodeCount(...)` to confirm the node is selected. |
| XML matcher fails even though both documents look nearly identical | Real difference in text, attributes, elements, or namespaces; or expected XML does not match the response. | Inspect the diff details provided by XMLUnit and compare the corresponding nodes/attributes. |
| Test expects `application/xml` but gets another media type | Controller or message converter writes the response with a different media type. | Check `produces`, `Accept` header, and converter configuration; verify the intended API contract. |

Notes when writing XPath:

- Element and attribute names in XML are case-sensitive.
- Attributes are selected with `@id`; predicates go in square brackets, such as `book[@id='bk-1']`.
- XPath `string(...)` returns the string value of the expression. For an element node, that is its string-value, including contained text nodes per XPath rules.
- XPath operates on the parsed XML tree, so attribute ordering and indentation are not suited for asserting byte-for-byte content.
- If whitespace inside text is business-significant, assert the exact value with XPath or an appropriate string matcher; do not rely on XML comparison, which may ignore formatting whitespace.

## 8. Workflow for Writing Readable XML Tests

When writing tests for an XML endpoint, you can follow this sequence:

1. Send the request with `Accept: application/xml` if the client requests XML.
2. Assert the HTTP status to confirm the request was handled in the expected state.
3. Assert that the response content type is compatible with `application/xml`.
4. Use `content().xml(...)` if you need to verify the document as a whole.
5. Add XPath matchers for key rules such as required nodes, record counts, field values, or namespaces.
6. When a test fails, read the response body and diff/XPath details to determine whether the fault lies in status, media type, XML syntax, namespaces, or data.

The complete example above uses `@WebMvcTest` to load the controller class together with the required MVC infrastructure. If the application has converter configurations, filters, or security components affecting the response that need to be tested together, you can select a broader Spring test context. The `content()` and `xpath()` matchers work the same way on `MockMvc` results.

## 9. Conclusion

In Spring MVC Test, `content().xml(...)` verifies that the response body is structurally equivalent to the expected XML, while `xpath(...)` checks specific nodes or conditions of interest. Assert status and content type first, then pick matchers matching the scope of the contract you want to protect. For documents with namespaces, always map prefixes in XPath to their corresponding namespace URIs so expressions select the right nodes.
