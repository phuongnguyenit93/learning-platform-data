# So khớp XML, XPath và namespace trong dữ liệu phản hồi

## 1. Bối cảnh: response đúng dữ liệu nhưng test vẫn thất bại

Một hệ thống đặt hàng công bố SOAP contract theo hướng **contract-first**. XSD định nghĩa `SubmitOrderRequest` và `SubmitOrderResponse`; WSDL mô tả operation và SOAP binding. JAXB ánh xạ XML thành Java classes, còn Spring Web Services nhận message bằng `MessageDispatcherServlet`, gọi `@Endpoint` và trả SOAP response cho consumer.

Sau một lần thay đổi serializer, test so sánh toàn bộ XML thất bại dù response vẫn đúng contract. Prefix XML đổi từ `o` sang `ns2`, indentation khác và namespace declaration được đặt tại vị trí khác. Một test khác chỉ dùng `contains("ACCEPTED")` lại pass ngay cả khi status nằm sai namespace.

Với SOAP, **XML là dữ liệu có cấu trúc và namespace**. Kiểm thử phản hồi cần xác minh điều consumer thực sự dựa vào: SOAP Envelope đúng version, payload QName, element/value, cardinality, attributes, namespace URI và những phần tử được phép xuất hiện.

Đây là đề mục **“So khớp XML, XPath và namespace trong dữ liệu phản hồi”**, thuộc chương **Kiểm thử máy chủ** của module **SPRING_WEB_SERVICES**. Bài học gắn với xây dựng SOAP endpoint/client, thiết kế XSD/WSDL, JAXB, SOAP Fault, interceptor và kiểm thử tương thích.

Sau bài học, bạn có thể:

- Phân biệt so sánh chuỗi XML với so sánh cấu trúc/XML infoset.
- Viết XPath assertion ổn định khi prefix thay đổi.
- Dùng `NamespaceContext` để kiểm tra QName và namespace URI.
- Dùng XMLUnit để so sánh XML theo semantics của contract.
- Kiểm thử response payload, SOAP Header và SOAP Fault bằng Spring-WS test support.
- Kiểm tra nil/optional, sequence, attributes, collection và SOAP 1.1/1.2.
- Tránh test quá lỏng, test phụ thuộc prefix hoặc test vô tình bỏ qua namespace.

## 2. XML response không phải một chuỗi văn bản tùy ý

### 2.1. Hai XML có cách viết khác nhau nhưng cùng QName

Response A:

```xml
<o:SubmitOrderResponse xmlns:o="urn:example:orders:v1">
  <o:orderId>ORD-1001</o:orderId>
  <o:status>ACCEPTED</o:status>
</o:SubmitOrderResponse>
```

Response B:

```xml
<ns2:SubmitOrderResponse xmlns:ns2="urn:example:orders:v1">
  <ns2:orderId>ORD-1001</ns2:orderId>
  <ns2:status>ACCEPTED</ns2:status>
</ns2:SubmitOrderResponse>
```

Hai response có cùng expanded names:

```text
{urn:example:orders:v1}SubmitOrderResponse
{urn:example:orders:v1}orderId
{urn:example:orders:v1}status
```

Prefix `o` và `ns2` chỉ là alias cục bộ cho namespace URI. **Prefix không phải định danh namespace**. Nếu contract chỉ định namespace URI và local part, hai response ở trên tương đương về tên phần tử.

### 2.2. Nhưng namespace URI khác là một thay đổi thực

```xml
<o:SubmitOrderResponse xmlns:o="urn:example:orders:v2">
  <o:orderId>ORD-1001</o:orderId>
  <o:status>ACCEPTED</o:status>
</o:SubmitOrderResponse>
```

Root QName bây giờ là `{urn:example:orders:v2}SubmitOrderResponse`, không còn là QName V1. Test bỏ qua namespace có thể vẫn pass, che đi một breaking contract change.

### 2.3. So sánh chuỗi có thể gây false negative và false positive

| Cách assertion | Vấn đề |
|---|---|
| So sánh toàn bộ string | Nhạy với prefix, whitespace, attribute order, XML declaration và formatting |
| `contains("ACCEPTED")` | Có thể tìm nhầm node, bỏ qua namespace/path và trùng giá trị |
| XPath `//*[local-name()='status']` | Bỏ namespace hoàn toàn, có thể match nhầm phần tử cùng local name |
| XPath có namespace URI đúng | Kiểm tra được phần tử theo contract |
| XMLUnit semantic comparison | So sánh cấu trúc theo cấu hình, cần chọn đúng node/ignore rules |

**Không phải mọi khác biệt giữa hai XML đều không quan trọng.** Prefix/indentation thường không quan trọng, nhưng namespace URI, QName, element order trong `xs:sequence`, value, occurrence và attributes có thể là điều kiện bắt buộc của contract.

## 3. Namespace và QName: nền tảng của XPath assertion

### 3.1. Expanded name

Một element có tên mở rộng (expanded name) gồm namespace URI và local name.

```xml
<o:status xmlns:o="urn:example:orders:v1">ACCEPTED</o:status>
```

Expanded name là `{urn:example:orders:v1}status`. Prefix có thể thay đổi; namespace URI và local name quyết định QName.

### 3.2. Default namespace vẫn áp dụng cho element không prefix

```xml
<SubmitOrderResponse xmlns="urn:example:orders:v1">
  <orderId>ORD-1001</orderId>
  <status>ACCEPTED</status>
</SubmitOrderResponse>
```

Các element trên vẫn thuộc namespace `urn:example:orders:v1`, dù không có prefix. Một XPath không khai báo namespace như `//status` **không tự động** có nghĩa “status trong default namespace của XML”.

Đây là lỗi phổ biến khiến test trả về zero nodes dù XML có element đúng.

### 3.3. Default namespace của element không tự áp dụng cho attribute không prefix

```xml
<o:order xmlns:o="urn:example:orders:v1"
         id="ORD-1001"
         o:source="PARTNER_A"/>
```

- `o:order` có QName `{urn:example:orders:v1}order`.
- `id` không prefix là attribute **không namespace**.
- `o:source` có QName `{urn:example:orders:v1}source`.

Test phải phân biệt attributes có namespace và không namespace; không suy rằng vì element có namespace nên mọi attribute đều thuộc namespace đó.

### 3.4. QName trong SOAP Body

```xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soap:Header/>
  <soap:Body>
    <o:SubmitOrderResponse>
      <o:orderId>ORD-1001</o:orderId>
    </o:SubmitOrderResponse>
  </soap:Body>
</soap:Envelope>
```

SOAP Body có QName `{http://schemas.xmlsoap.org/soap/envelope/}Body`; payload root là `{urn:example:orders:v1}SubmitOrderResponse`. Khi test endpoint, cần biết matcher đang xét **SOAP message**, **SOAP Body** hay **payload source**.

## 4. XPath: truy vấn XML theo cấu trúc

XPath định vị node bằng đường dẫn, điều kiện và hàm. XPath 1.0 thường được dùng trong JAXP và nhiều matcher Spring-WS/XMLUnit.

Với payload:

```xml
<o:SubmitOrderResponse xmlns:o="urn:example:orders:v1">
  <o:orderId>ORD-1001</o:orderId>
  <o:status>ACCEPTED</o:status>
  <o:total currency="USD">125.50</o:total>
</o:SubmitOrderResponse>
```

Các XPath dưới đây giả sử prefix `o` đã được khai báo trong XPath context:

| Mục tiêu | XPath |
|---|---|
| Root element | `/o:SubmitOrderResponse` |
| Order ID | `/o:SubmitOrderResponse/o:orderId` |
| Status text | `string(/o:SubmitOrderResponse/o:status)` |
| Tổng tiền | `/o:SubmitOrderResponse/o:total/text()` |
| Currency attribute không namespace | `/o:SubmitOrderResponse/o:total/@currency` |
| Số lượng orderId | `count(/o:SubmitOrderResponse/o:orderId)` |
| Có ít nhất một item | `count(/o:SubmitOrderResponse/o:items/o:item) > 0` |

**Prefix trong XPath là prefix do test tự khai báo**, không cần giống prefix trong XML response.

### 4.1. Absolute path và relative path

`/o:SubmitOrderResponse/o:status` bắt đầu từ document root. `//o:status` tìm mọi descendant có QName tương ứng; cách sau linh hoạt hơn nhưng có thể match nhầm status nằm trong nested object khác.

Với contract rõ ràng, nên dùng đường dẫn đủ cụ thể thay vì tìm mọi phần tử có local name giống nhau.

### 4.2. Kiểm tra tồn tại và số lượng node

Các biểu thức:

```xpath
count(/o:SubmitOrderResponse/o:orderId) = 1
count(/o:SubmitOrderResponse/o:status) = 1
count(/o:SubmitOrderResponse/o:warning) = 0
```

giúp phát hiện thiếu, lặp hoặc xuất hiện ngoài ý muốn các element. Đây là kiểm tra quan trọng khi contract quy định `minOccurs`, `maxOccurs` hoặc element đơn.

### 4.3. Kiểm tra giá trị và attribute

```xpath
normalize-space(string(/o:SubmitOrderResponse/o:status)) = 'ACCEPTED'
/o:SubmitOrderResponse/o:total/@currency = 'USD'
```

Lưu ý: XPath 1.0 `number()` dùng floating-point, không thích hợp để xác minh monetary precision. Với tiền, nên lấy text node dưới dạng String rồi parse `BigDecimal` trong Java và assert chính xác.

### 4.4. Kiểm tra order trong `xs:sequence`

Nếu contract quy định `orderId` đứng trước `status`, có thể kiểm tra vị trí bằng XPath hoặc dùng XML schema validation để xác minh sequence. Không nên lạm dụng XPath position nếu mục tiêu thực sự là schema validity; XSD validator diễn đạt ràng buộc thứ tự chính xác và dễ bảo trì hơn.

## 5. Dùng NamespaceContext trong Java XPath

JAXP XPath không tự lấy prefix mapping từ tài liệu XML. Test phải cung cấp namespace mapping của **XPath expression** thông qua `NamespaceContext`.

### 5.1. Một NamespaceContext đơn giản

```java
import java.util.Iterator;
import java.util.Map;
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;

public final class MapNamespaceContext implements NamespaceContext {
    private final Map<String, String> namespaces;

    public MapNamespaceContext(Map<String, String> namespaces) {
        this.namespaces = Map.copyOf(namespaces);
    }

    @Override
    public String getNamespaceURI(String prefix) {
        if (prefix == null) {
            throw new IllegalArgumentException("Prefix must not be null");
        }
        if (XMLConstants.XML_NS_PREFIX.equals(prefix)) {
            return XMLConstants.XML_NS_URI;
        }
        if (XMLConstants.XMLNS_ATTRIBUTE.equals(prefix)) {
            return XMLConstants.XMLNS_ATTRIBUTE_NS_URI;
        }
        return namespaces.getOrDefault(prefix, XMLConstants.NULL_NS_URI);
    }

    @Override
    public String getPrefix(String namespaceURI) {
        return namespaces.entrySet().stream()
                .filter(entry -> entry.getValue().equals(namespaceURI))
                .map(Map.Entry::getKey)
                .findFirst()
                .orElse(null);
    }

    @Override
    public Iterator<String> getPrefixes(String namespaceURI) {
        return namespaces.entrySet().stream()
                .filter(entry -> entry.getValue().equals(namespaceURI))
                .map(Map.Entry::getKey)
                .iterator();
    }
}
```

Đây là helper **dành cho test**. Nó giữ mapping prefix → URI rõ ràng và xử lý hai namespace chuẩn của XML (`xml`, `xmlns`). Không nên dùng default namespace làm XPath prefix ngầm; khai báo một prefix riêng như `o` sẽ rõ ràng hơn.

### 5.2. Tạo XPath và đọc giá trị

```java
import java.io.StringReader;
import java.util.Map;
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;

public final class SoapResponseXPath {
    private SoapResponseXPath() {}

    public static Document parse(String xml) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature(
                "http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities", false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        return factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
    }

    public static String evaluateString(
            Document document, String expression) throws Exception {
        XPath xpath = XPathFactory.newInstance().newXPath();
        NamespaceContext context = new MapNamespaceContext(Map.of(
                "o", "urn:example:orders:v1"));
        xpath.setNamespaceContext(context);
        return (String) xpath.evaluate(
                expression, document, XPathConstants.STRING);
    }
}
```

Đây là helper minh họa dùng JAXP và DOM. Tùy XML parser/provider, một số feature/attribute có thể không hỗ trợ và sẽ ném exception; với security-sensitive tests, không bỏ qua lỗi hardening. Trong dự án thật nên gom cấu hình parser an toàn vào utility đã được kiểm thử thay vì lặp cấu hình tùy tiện.

Ví dụ sử dụng:

```java
Document document = SoapResponseXPath.parse(responseXml);
String orderId = SoapResponseXPath.evaluateString(
        document, "/o:SubmitOrderResponse/o:orderId");
assertEquals("ORD-1001", orderId);

String status = SoapResponseXPath.evaluateString(
        document, "normalize-space(/o:SubmitOrderResponse/o:status)");
assertEquals("ACCEPTED", status);
```

### 5.3. Kiểm tra node count

```java
XPath xpath = XPathFactory.newInstance().newXPath();
xpath.setNamespaceContext(new MapNamespaceContext(Map.of(
        "o", "urn:example:orders:v1")));

Double count = (Double) xpath.evaluate(
        "count(/o:SubmitOrderResponse/o:orderId)",
        document,
        XPathConstants.NUMBER);
assertEquals(1.0, count);
```

XPath 1.0 trả count dạng number; trong JAXP thường được map thành `Double`. Với assertion số lượng nguyên, convert/check một cách có chủ đích; không so sánh floating-point cho dữ liệu tiền hoặc phép tính domain.

### 5.4. Đừng dùng namespace URI rỗng để “fix” XPath

Nếu XPath trả về rỗng, đừng lập tức đổi XPath sang `local-name()`. Trước tiên kiểm tra:

1. DocumentBuilderFactory có `setNamespaceAware(true)` không?
2. Element thực sự thuộc namespace URI nào?
3. XPath NamespaceContext có khai báo prefix đúng chưa?
4. Có đang truy vấn payload document hay SOAP Envelope document?
5. Response dùng default namespace hay nested namespace declaration?

Tắt namespace awareness hoặc bỏ namespace khỏi XPath có thể làm test pass giả.

## 6. XMLUnit: so sánh XML theo cấu trúc và semantics

XMLUnit cung cấp API để so sánh XML, kiểm tra differences và viết assertion ít phụ thuộc formatting hơn so sánh String.

### 6.1. Khi nào dùng XMLUnit?

- So expected XML và actual XML theo cấu trúc.
- Bỏ qua whitespace nodes được xác định là không đáng kể.
- So element/attribute theo namespace URI và local name.
- Tùy chỉnh node matching hoặc difference evaluator.
- Tạo diff dễ đọc khi test thất bại.

Không dùng XMLUnit để bỏ qua mọi khác biệt. Nếu ignore element `status`, `currency` hoặc namespace URI, test có thể không còn kiểm tra contract quan trọng.

### 6.2. Ví dụ XMLUnit 2

```java
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import org.xmlunit.builder.DiffBuilder;
import org.xmlunit.diff.Diff;

class OrderXmlComparisonTest {
    @Test
    void responseMatchesExpectedXmlStructure() {
        String expected = """
            <o:SubmitOrderResponse xmlns:o="urn:example:orders:v1">
              <o:orderId>ORD-1001</o:orderId>
              <o:status>ACCEPTED</o:status>
            </o:SubmitOrderResponse>
            """;
        String actual = """
            <ns2:SubmitOrderResponse xmlns:ns2="urn:example:orders:v1">
              <ns2:orderId>ORD-1001</ns2:orderId>
              <ns2:status>ACCEPTED</ns2:status>
            </ns2:SubmitOrderResponse>
            """;

        Diff diff = DiffBuilder.compare(expected)
                .withTest(actual)
                .ignoreWhitespace()
                .checkForSimilar()
                .build();

        assertFalse(diff.hasDifferences(), diff.toString());
    }
}
```

`DiffBuilder` trả một `Diff`; với test mong muốn hai XML tương đương, assertion phải xác nhận `hasDifferences()` là false. Nếu có differences, đưa `diff.toString()` vào failure message để hiểu node nào khác.

### 6.3. Prefix khác nhau không nên làm test hỏng

XMLUnit so sánh XML theo node/namespace semantics, không chỉ so raw prefix text. Dù vậy, namespace URI phải được kiểm tra. Hai element cùng local name nhưng khác URI vẫn là khác biệt contract.

### 6.4. Ignore whitespace một cách có chủ đích

`ignoreWhitespace()` có thể loại bỏ whitespace-only text nodes. Nhưng với dữ liệu mixed content hoặc text nơi whitespace có ý nghĩa, normalize quá rộng có thể che lỗi.

Ví dụ:

```xml
<description>Express  delivery</description>
```

và:

```xml
<description>Express delivery</description>
```

có thể khác nhau về text content. Đừng bật whitespace normalization cho mọi XML response nếu contract có mixed content, signature-sensitive content hoặc text formatting semantics.

### 6.5. checkForSimilar và checkForIdentical

| Cấu hình | Mục đích |
|---|---|
| `checkForSimilar()` | Xem hai tài liệu là tương tự theo các difference được XMLUnit coi không đáng kể |
| `checkForIdentical()` | Yêu cầu không có differences theo comparison rules đang cấu hình |
| Custom DifferenceEvaluator | Cho phép chính sách cụ thể với một số loại difference |
| NodeMatcher | Quyết định cách ghép các node lặp/cùng loại khi so sánh |

Không nên dùng `checkForSimilar()` như cách bỏ qua namespace hoặc element order nếu hai thuộc tính đó thuộc contract. Đọc `Diff.toString()` khi test hỏng và đánh giá từng difference.

## 7. So khớp response payload với Spring-WS MockWebServiceClient

Spring-WS cung cấp `MockWebServiceClient` để gửi một SOAP request vào endpoint trong test context và kiểm tra kết quả bằng response matchers.

### 7.1. Dựng test client cho server

Một test cấu trúc thường có:

1. Khởi tạo Spring application context chứa endpoint và endpoint mappings.
2. Tạo `MockWebServiceClient` gắn với application context.
3. Gửi request XML bằng `withPayload(...)`.
4. Assert payload response, XPath, SOAP Fault hoặc những điều kiện cần thiết.

### 7.2. Test response payload bằng matcher

```java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.context.ApplicationContext;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

@SpringBootTest
class SubmitOrderEndpointTest {

    @Autowired
    private ApplicationContext applicationContext;

    private MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(applicationContext);
    }

    @Test
    void returnsOrderConfirmation() {
        String request = """
            <o:SubmitOrderRequest xmlns:o="urn:example:orders:v1">
              <o:orderId>ORD-1001</o:orderId>
              <o:customerId>C-01</o:customerId>
              <o:amount>125.50</o:amount>
            </o:SubmitOrderRequest>
            """;

        String expected = """
            <o:SubmitOrderResponse xmlns:o="urn:example:orders:v1">
              <o:orderId>ORD-1001</o:orderId>
              <o:status>ACCEPTED</o:status>
            </o:SubmitOrderResponse>
            """;

        client.sendRequest(withPayload(new StringSource(request)))
                .andExpect(payload(new StringSource(expected)));
    }
}
```

Đây là ví dụ dùng Spring-WS test support trong Spring Boot context. `MockWebServiceClient.createClient(applicationContext)` tạo test client từ Spring context; context cần có endpoint, mapping, marshaller và service dependencies. Request payload trong ví dụ chưa gồm SOAP Header, WS-Security hay transport-level HTTP headers.

Matcher `payload(...)` tập trung vào **payload của SOAP Body**, do đó không nên dùng nó để khẳng định HTTP status, Content-Type, SOAP Header hoặc TLS/mTLS đúng. Các yếu tố đó cần test ở layer phù hợp.

## 8. Payload matcher khác Envelope matcher

### 8.1. Body payload test không kiểm tra SOAP Header

`withPayload` nhận nội dung payload và test support dựng message phù hợp. Nó hữu ích cho endpoint logic, nhưng không chứng minh:

- SOAP Header chứa `wsa:Action` chính xác.
- `wsa:MessageID`/`wsa:To` đúng.
- `wsse:Security` có Timestamp/Signature hợp lệ.
- SOAP `mustUnderstand` được xử lý đúng.
- HTTP Content-Type/SOAPAction đúng.

Nếu operation phụ thuộc các header này, cần test riêng qua request/envelope đầy đủ và interceptor behavior.

### 8.2. Chọn SOAP version trong test

SOAP 1.1 Envelope namespace:

```text
http://schemas.xmlsoap.org/soap/envelope/
```

SOAP 1.2 Envelope namespace:

```text
http://www.w3.org/2003/05/soap-envelope
```

Không gửi một SOAP 1.1 Envelope vào endpoint/message factory chỉ cấu hình SOAP 1.2 rồi coi lỗi parse là lỗi business. Cấu hình `SaajSoapMessageFactory`/message factory và WSDL binding phải nhất quán.

### 8.3. Chọn matcher theo điều cần chứng minh

| Mục tiêu | Hướng kiểm tra |
|---|---|
| Endpoint nhận đúng payload | `withPayload` + payload matcher |
| Response element/value theo QName | XPath matcher với namespace map |
| SOAP Header bắt buộc | Envelope/header-level matcher hoặc inspect SOAP message |
| WS-Addressing action | Header assertion theo QName và URI |
| SOAP Fault | Fault matcher + code/detail assertion |
| HTTP status/header | Embedded server hoặc HTTP integration test |
| TLS/mTLS | HTTPS integration test với trust/key material test |
| WS-Security Signature | WSS4J processing với signed fixtures/test peer |

### 8.4. Đừng parse SOAP Envelope như payload document

Nếu XPath dùng:

```xpath
/o:SubmitOrderResponse/o:status
```

thì XPath context phải trỏ đến document mà root là payload `SubmitOrderResponse`. Nếu document là SOAP Envelope đầy đủ, đường dẫn phải đi qua SOAP `Body`:

```xpath
/soap:Envelope/soap:Body/o:SubmitOrderResponse/o:status
```

với cả hai prefix `soap` và `o` được khai báo. Sai điểm bắt đầu document là nguyên nhân phổ biến khiến XPath trả rỗng.

## 9. Kiểm tra SOAP Header và WS-Addressing

SOAP Header chứa metadata định tuyến, tương quan, security hoặc extension. Với endpoint cần những header này, test phải xác minh **đúng QName và giá trị**, đồng thời kiểm tra behavior khi header thiếu hoặc sai.

### 9.1. SOAP 1.1 Header ví dụ

```xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:o="urn:example:orders:v1">
  <soap:Header>
    <wsa:Action>urn:example:orders:v1:SubmitOrder</wsa:Action>
    <wsa:MessageID>urn:uuid:123e4567-e89b-12d3-a456-426614174000</wsa:MessageID>
    <wsa:To>https://api.example.org/soap/orders</wsa:To>
  </soap:Header>
  <soap:Body>
    <o:SubmitOrderRequest>
      <o:orderId>ORD-1001</o:orderId>
    </o:SubmitOrderRequest>
  </soap:Body>
</soap:Envelope>
```

Đây là fixture minh họa WS-Addressing 1.0. Contract thật phải dùng đúng version namespace/action URI, endpoint To và policy được công bố.

### 9.2. XPath trên toàn Envelope

Với namespace context:

```java
NamespaceContext namespaces = new MapNamespaceContext(Map.of(
        "soap", "http://schemas.xmlsoap.org/soap/envelope/",
        "wsa", "http://www.w3.org/2005/08/addressing",
        "o", "urn:example:orders:v1"));
```

Có thể kiểm tra:

```xpath
/soap:Envelope/soap:Header/wsa:Action
/soap:Envelope/soap:Header/wsa:To
/soap:Envelope/soap:Body/o:SubmitOrderRequest
```

Không dùng `//*[local-name()='Action']` khi có nhiều extension headers có thể cùng local name.

### 9.3. Kiểm tra mustUnderstand

Nếu một SOAP header có `soap:mustUnderstand="1"` ở SOAP 1.1, node recipient phải hiểu và xử lý header đó theo vai trò của nó. Test nên có:

- Header được hỗ trợ, server xử lý và tiếp tục.
- Header bắt buộc nhưng không được hỗ trợ, server tạo SOAP Fault phù hợp.
- Header không bắt buộc và không được hỗ trợ, server xử lý theo quy định.
- Role/actor/role targeting phù hợp nếu contract dùng intermediaries.

Tên attribute và semantics ở SOAP 1.2 khác namespace/version, nên không copy XPath của SOAP 1.1.

### 9.4. Không dùng XPath để xác minh mật mã

XPath có thể khẳng định `ds:Signature` xuất hiện hoặc `wsse:BinarySecurityToken` tồn tại, nhưng **không chứng minh chữ ký hợp lệ**, certificate trusted hoặc Body đã được ký.

WS-Security test cần WSS4J verify thực, fixture được ký và negative tests sửa nội dung sau ký. XPath chỉ kiểm tra cấu trúc/metadata bổ trợ.

## 10. Kiểm tra SOAP Fault theo QName và detail

Fault là response công khai trong SOAP contract. Test cần phân biệt Fault code/reason và typed detail, không chỉ so một chuỗi “failed”.

### 10.1. SOAP 1.1 Fault ví dụ

```xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:o="urn:example:orders:v1">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Invalid order request</faultstring>
      <detail>
        <o:OrderFault>
          <o:code>ORDER_NOT_FOUND</o:code>
          <o:message>Order does not exist</o:message>
        </o:OrderFault>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
```

`faultcode` là QName lexical value nên khi parse cần resolve prefix `soap` qua namespace context. `OrderFault` là element detail theo application namespace. Fault detail không tự trở thành SOAP standard fault code.

### 10.2. SOAP 1.2 Fault có cấu trúc khác

```xml
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"
              xmlns:o="urn:example:orders:v1">
  <env:Body>
    <env:Fault>
      <env:Code>
        <env:Value>env:Sender</env:Value>
      </env:Code>
      <env:Reason>
        <env:Text xml:lang="vi">Yêu cầu đơn hàng không hợp lệ</env:Text>
      </env:Reason>
      <env:Detail>
        <o:OrderFault>
          <o:code>ORDER_NOT_FOUND</o:code>
        </o:OrderFault>
      </env:Detail>
    </env:Fault>
  </env:Body>
</env:Envelope>
```

SOAP 1.2 dùng Code, Reason, Detail với namespace SOAP 1.2. Không dùng matcher SOAP 1.1 để kiểm tra response SOAP 1.2.

### 10.3. XPath kiểm tra Fault detail

Cho SOAP 1.1:

```xpath
/soap:Envelope/soap:Body/soap:Fault/faultstring
/soap:Envelope/soap:Body/soap:Fault/detail/o:OrderFault/o:code
```

Cho SOAP 1.2:

```xpath
/env:Envelope/env:Body/env:Fault/env:Reason/env:Text
/env:Envelope/env:Body/env:Fault/env:Detail/o:OrderFault/o:code
```

XPath context cần khai báo đúng prefix `soap`/`env` và `o` URI tương ứng. Trong SOAP 1.1, `faultcode` là text QName; nếu cần xác minh namespace của code, parse giá trị QName và resolve prefix theo namespace declarations của Fault node.

### 10.4. Không so Fault detail chỉ bằng reason text

Reason/string phục vụ con người và có thể đổi ngôn ngữ hoặc wording. Nếu consumer cần logic máy đọc, hãy assert **Fault QName/code và typed detail element** theo contract. Tránh phụ thuộc dấu câu hoặc thông điệp lỗi nội bộ.

### 10.5. Fault test phải xác minh không side effect

Với request không hợp lệ:

1. Assert Fault đúng version và typed detail.
2. Assert domain method không thực thi hoặc transaction rollback theo policy.
3. Assert fault detail không chứa stack trace, SQL, private path hoặc credential.
4. Nếu Fault xuất hiện sau xác thực/security processing, assert identity/security behavior đúng.

Chỉ assert Fault có tồn tại là chưa đủ để chứng minh server xử lý request an toàn.

## 11. XSD validation: kiểm tra contract thay vì đoán từ response

XPath assertion xác minh các node cụ thể, nhưng không thay thế XSD validation. Một response có đủ `orderId` và `status` vẫn có thể sai sequence, type, namespace, occurrence hoặc facet.

### 11.1. Ví dụ schema cho response

```xml
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:orders:v1"
    xmlns:o="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:element name="SubmitOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="status" type="o:OrderStatus"/>
        <xs:element name="trackingId"
                    type="xs:string"
                    minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:simpleType name="OrderStatus">
    <xs:restriction base="xs:string">
      <xs:enumeration value="ACCEPTED"/>
      <xs:enumeration value="REJECTED"/>
    </xs:restriction>
  </xs:simpleType>
</xs:schema>
```

Response phải có root QName đúng, `orderId` và `status` theo thứ tự, status thuộc enum và `trackingId` chỉ xuất hiện tối đa một lần. XPath kiểm tra từng điều kiện có ích cho diagnostics, còn XSD validator kiểm tra tất cả ràng buộc schema đã khai báo.

### 11.2. Kiểm tra schema trong test

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.SchemaFactory;
import org.junit.jupiter.api.Test;

class OrderResponseSchemaTest {
    private static final String XSD = """
        <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   targetNamespace="urn:example:orders:v1"
                   xmlns:o="urn:example:orders:v1"
                   elementFormDefault="qualified">
          <xs:element name="SubmitOrderResponse">
            <xs:complexType>
              <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="xs:string"/>
              </xs:sequence>
            </xs:complexType>
          </xs:element>
        </xs:schema>
        """;

    private static final String RESPONSE = """
        <o:SubmitOrderResponse xmlns:o="urn:example:orders:v1">
          <o:orderId>ORD-1001</o:orderId>
          <o:status>ACCEPTED</o:status>
        </o:SubmitOrderResponse>
        """;

    @Test
    void responseIsValidAgainstPublishedSchema() throws Exception {
        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        var schema = factory.newSchema(
                new StreamSource(new StringReader(XSD)));
        var validator = schema.newValidator();

        assertDoesNotThrow(() -> validator.validate(
                new StreamSource(new StringReader(RESPONSE))));
    }
}
```

Đây là ví dụ schema test tự chứa, phù hợp minh họa. Với schema thật có `xs:include`/`xs:import`, dùng catalog/resolver allowlist và đóng gói dependency. Không bật external schema access chỉ để test tải XSD tùy ý từ mạng.

### 11.3. Test response sai schema phải thất bại

Các fixture negative nên gồm:

- Sai root namespace URI.
- Thiếu element bắt buộc.
- Đảo vị trí element trong sequence.
- Status ngoài enum.
- Có quá nhiều element vượt `maxOccurs`.
- `xsi:nil="true"` khi schema không cho phép.
- Decimal/number vượt facet hoặc lexical format sai.

Negative tests xác nhận schema validation đang thực sự chạy. Một positive fixture pass đơn lẻ không chứng minh endpoint đã bật validator trong production path.

### 11.4. Test schema bên ngoài và schema validation trên server

Một test tự gọi validator trên response **sau khi endpoint đã trả về** chứng minh fixture hợp lệ, nhưng chưa chứng minh Spring-WS server tự validate outbound response. Nếu mục tiêu là bảo đảm endpoint luôn tuân XSD:

1. Cấu hình response validation/interceptor phù hợp Spring-WS.
2. Gửi request qua endpoint test harness.
3. Cố tình tạo response không hợp lệ từ test-only endpoint/stub.
4. Xác nhận pipeline từ chối hoặc báo lỗi theo policy.
5. Xác nhận không trả một response sai schema như thành công.

## 12. An toàn khi parse XML trong test

Test thường parse trực tiếp XML do endpoint trả về. Nếu test utility có thể nhận XML từ nguồn ngoài, hãy cấu hình parser an toàn tương tự production ingress. **Một test helper có XXE không an toàn vẫn có thể đọc file hoặc truy cập network của máy chạy CI.**

### 12.1. Những cấu hình cần chú ý

- Bật namespace awareness.
- Từ chối DOCTYPE nếu SOAP contract không cần DTD.
- Tắt external general entities và parameter entities.
- Tắt XInclude nếu không được sử dụng.
- Cấm external DTD/schema access, ngoại trừ catalog/resolver allowlist có chủ đích.
- Giới hạn kích thước message và độ sâu/nodes nếu test service xử lý input không tin cậy.
- Không dùng parser mặc định chưa harden chỉ vì XML test là fixture.

### 12.2. Negative test cho DTD và external entity

Ví dụ fixture độc hại:

```xml
<!DOCTYPE request [
  <!ENTITY secret SYSTEM "file:///not-a-real-secret">
]>
<request>&secret;</request>
```

Parser đã harden cần từ chối hoặc không resolve external entity theo policy. **Không kiểm tra bằng cách trỏ đến file secrets thật.** Dùng URI giả/canary trong môi trường test và xác minh parser không gọi external resolver.

### 12.3. XML Signature và XML normalization

Không lấy XML đã được ký rồi parse/serialize lại để so chuỗi và kết luận chữ ký còn hợp lệ. XML Signature phụ thuộc canonicalization, transforms và signed references. Test phải dùng WSS4J verify thực sau các biến đổi được mô phỏng.

XMLUnit/XPath hữu ích để kiểm tra payload sau parse, nhưng không thay signature verification và không nên dùng để mutate message đã ký.

## 13. Tổ chức fixture và test suite theo contract

Một cấu trúc test rõ ràng:

```text
src/test/
  java/
    .../endpoint/
      SubmitOrderEndpointTest.java
    .../contract/
      OrderResponseSchemaTest.java
      OrderXmlComparisonTest.java
      OrderFaultContractTest.java
    .../security/
      SignedSoapResponseTest.java
  resources/
    contracts/
      orders/
        v1/
          request-valid.xml
          response-accepted.xml
          response-invalid-namespace.xml
          response-missing-status.xml
          fault-order-not-found.xml
        v2/
          ...
```

Tách fixture theo contract version giúp tránh vô tình dùng XML V2 làm expected output của endpoint V1.

### 13.1. Đặt tên fixture theo mục tiêu

Tên như `response-invalid.xml` quá chung. Ưu tiên:

- `response-wrong-root-namespace.xml`.
- `response-missing-required-status.xml`.
- `response-duplicate-order-id.xml`.
- `response-unknown-status-enum.xml`.
- `soap11-fault-order-not-found.xml`.
- `soap12-fault-order-not-found.xml`.

Tên fixture nên mô tả một lỗi cụ thể để test failure dễ đọc.

### 13.2. Expected response phải độc lập với implementation

Không tạo expected XML bằng cách gọi chính mapper/serializer đang được test, vì test sẽ dùng cùng logic tạo actual và expected.

```java
// Dễ tạo test giả: expected và actual cùng code path.
String expected = marshaller.marshal(responseObject);
String actual = endpointResponse;
```

Thay vào đó, giữ một fixture XML được review theo WSDL/XSD hoặc assertions XPath độc lập. Có thể dùng generated classes để tạo input test, nhưng expected cần kiểm tra contract thật.

### 13.3. Tránh fixture khổng lồ khó đọc

Với payload lớn, không nhất thiết so toàn bộ XML. Kết hợp:

- Schema validation cho cấu trúc tổng thể.
- XPath cho fields quan trọng và cardinality.
- XMLUnit diff khi cần so cả document.
- Domain assertions cho amount/state/side effects.

Đừng bỏ qua những phần tử quan trọng chỉ để fixture ngắn hơn; chọn assertion theo requirement.

## 14. Chẩn đoán XPath/XML assertion thất bại

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| XPath trả chuỗi rỗng | Thiếu namespace mapping hoặc sai document root | Kiểm tra NamespaceContext và Envelope/Body |
| `//status` không match | Element thuộc default namespace | Dùng prefix trong XPath gắn với URI |
| `local-name()` match nhiều node | Có cùng local name ở các namespace/nested objects | Dùng full path + namespace URI |
| XMLUnit báo khác prefix | Comparator/config xử lý namespace chưa đúng | Xác minh expanded QName, cấu hình comparator có kiểm soát |
| XMLUnit không báo khác value | DifferenceEvaluator/ignore rule quá rộng | Thu hẹp ignored differences |
| Test fail do indentation | So raw string hoặc whitespace-only nodes | Dùng XML-aware comparison nếu whitespace không có nghĩa |
| Monetary assertion lệch | Dùng XPath number/floating-point | Parse decimal text thành BigDecimal |
| Matcher payload pass nhưng Header sai | Payload matcher không kiểm tra Header | Tạo envelope/header test riêng |
| Fault assertion sai namespace | SOAP 1.1/1.2 hoặc app detail URI khác | Xác minh QName đầy đủ và binding |
| Prefix SOAP Fault code không resolve | QName lexical value chưa resolve theo namespace declarations | Parse text thành QName theo context |
| XSD test pass nhưng endpoint trả sai schema | Test chỉ validate fixture riêng, server chưa bật validation | Integration test qua response validation pipeline |
| JAXB object null nhưng XML có node | Mapping context, nillability hoặc adapter mismatch | Kiểm tra XJC binding và JAXB annotations |
| Duplicate element không bị phát hiện | Test chỉ đọc first matching node | Assert node count và validate XSD |
| Response V1 bất ngờ fail | Fixture V1 đang được so với generated V2/namespace mới | Cố định fixture và version rõ ràng |
| SOAP message malformed khi test | SOAP version/Content-Type hoặc namespace Envelope sai | Kiểm tra MessageFactory và WSDL binding |
| XMLUnit báo khác thứ tự element | Schema dùng sequence hoặc node matcher khác | Kiểm tra order contract, không tự ignore |
| xsi:nil không phân biệt với missing | Assertion chỉ đọc text value | Assert existence + nil attribute riêng |
| Test security pass dù Signature giả | Chỉ XPath kiểm tra ds:Signature tồn tại | WSS4J verify signed fixture thực |

### 14.1. Quy trình debug có thứ tự

1. Lưu actual response fixture an toàn khi test fail, không chứa secrets/PII thật.
2. Xác định actual là payload hay toàn SOAP Envelope.
3. Đọc namespace URI của root và các elements liên quan.
4. Chạy XPath tối thiểu cho root QName, node count và field cần kiểm tra.
5. Đọc XMLUnit diff hoặc schema validation errors.
6. So với WSDL/XSD version mà test đang nhắm đến.
7. Xác minh matcher đang bỏ qua những khác biệt nào.
8. Nếu liên quan WS-Security, chạy cryptographic validation độc lập.

Không sửa XPath thành `local-name()` hoặc tắt namespace validation chỉ để test xanh khi chưa hiểu nguyên nhân.

## 15. Checklist chất lượng XML response tests

### Namespace và cấu trúc

- [ ] Parser test bật namespace awareness.
- [ ] XPath dùng NamespaceContext với URI chính xác.
- [ ] Assert payload root QName đầy đủ, không chỉ local name.
- [ ] Phân biệt namespace element và namespace attribute.
- [ ] Không phụ thuộc prefix serializer chọn.
- [ ] Assert element count, required/optional, nil/empty/missing.
- [ ] Sequence/order và schema facets được kiểm tra bằng XSD validator khi phù hợp.

### SOAP message

- [ ] Xác định test đang so payload hay toàn Envelope.
- [ ] SOAP 1.1/1.2 namespace và Content-Type đúng binding.
- [ ] SOAP Header/WS-Addressing được kiểm tra riêng nếu operation phụ thuộc.
- [ ] SOAP Fault được kiểm tra theo version, QName/code và typed detail.
- [ ] WS-Security được verify mật mã bằng WSS4J, không chỉ XPath.

### Chất lượng assertion

- [ ] Không so raw XML string nếu formatting/prefix không thuộc contract.
- [ ] Không dùng `contains()` làm bằng chứng response đúng schema.
- [ ] Không bỏ namespace bằng `local-name()` khi contract yêu cầu QName.
- [ ] Ignore whitespace/attribute/node chỉ khi semantics cho phép.
- [ ] Monetary values được so bằng BigDecimal, không XPath number.
- [ ] XMLUnit failure message cung cấp diff hữu ích.
- [ ] Fixture độc lập với code path đang được kiểm thử.

### Security và bảo trì

- [ ] XML parser tắt DTD/external entities hoặc có policy allowlist.
- [ ] Không ghi raw SOAP có token/PII vào test output/CI artifacts.
- [ ] Fixtures theo version được lưu và review.
- [ ] Có positive và negative cases, bao gồm schema/security failures.
- [ ] Test chứng minh business side effects không xảy ra khi request bị reject.
- [ ] Toolchain/parser/XMLUnit/Spring-WS versions được khóa và ghi nhận.

## 16. Bài tập thực hành

### Bài tập 1 — Prefix khác nhau nhưng QName giống nhau

Cho hai response dùng prefix `o` và `ns2` nhưng cùng URI `urn:example:orders:v1`. Viết XMLUnit test chứng minh chúng tương đương theo expanded names. Sau đó đổi URI sang V2 và chứng minh test phải fail.

### Bài tập 2 — Default namespace

Tạo response dùng default namespace thay vì prefix. Viết XPath test với NamespaceContext prefix riêng. Chứng minh `//status` không match đúng phần tử namespace-qualified và XPath có prefix thì match.

### Bài tập 3 — Attribute namespace

Với element có `id` không namespace và `o:source` có namespace, viết XPath assertion kiểm tra từng attribute. Tạo test negative khi source attribute bị bỏ namespace hoặc URI đổi.

### Bài tập 4 — Cardinality và sequence

Tạo response thiếu status, duplicate orderId và đảo order element. Dùng node count/XPath và XSD validator để xác định lớp nào phát hiện lỗi nào.

### Bài tập 5 — Optional, empty và nil

Tạo ba response: trackingId không tồn tại, empty element, và `xsi:nil="true"`. Viết assertion riêng cho existence, text và nil attribute. Không dùng một assertion chuỗi rỗng cho cả ba.

### Bài tập 6 — Spring-WS endpoint response

Dùng MockWebServiceClient gửi SubmitOrderRequest và kiểm tra response payload bằng XPath matcher. Assert QName, orderId, status, số lượng status và optional trackingId. Sau đó đổi response prefix để chứng minh test không phụ thuộc prefix.

### Bài tập 7 — SOAP Header

Tạo Envelope SOAP 1.1 có WS-Addressing Action, MessageID và To. Viết XPath kiểm tra namespace URI/giá trị. Tạo fixture sai Action và thiếu Header để xác nhận endpoint behavior.

### Bài tập 8 — SOAP Fault

Tạo Fault SOAP 1.1 và SOAP 1.2 có cùng application detail code. Viết hai bộ XPath khác nhau để kiểm tra Code/Reason/Detail đúng namespace. Thêm negative test detail namespace sai.

### Bài tập 9 — XSD validation

Viết validator test cho SubmitOrderResponse. Chạy positive fixture và các negative fixtures sai QName, thiếu required field, enum lạ, sequence sai, nil không được phép. Xác minh test không tải external schemas từ mạng.

### Bài tập 10 — XMLUnit differences

So sánh expected/actual có prefix khác và whitespace-only indentation khác. Dùng `checkForSimilar()` và `checkForIdentical()` trong hai test riêng. Quan sát differences; không bỏ qua element order hoặc namespace URI nếu contract yêu cầu chúng.

### Bài tập 11 — Secure parser

Đưa DTD/external entity fixture vào XML parser của test utility. Xác minh external resolver không được gọi và test fail an toàn. Không trỏ tới file secret thật.

### Bài tập 12 — Test bảo đảm độc lập

Tạo expected XML fixture độc lập với JAXB mapper. So actual response bằng schema + XPath + XMLUnit. Thay mapper để tạo response sai namespace và xác nhận test phát hiện được.

## 17. Tổng kết

**So khớp XML đúng nghĩa là so cấu trúc và namespace theo contract, không phải so cách serializer viết chuỗi.** Prefix có thể đổi mà QName vẫn giữ nguyên; namespace URI thay đổi thì contract identity thay đổi. XPath cần NamespaceContext rõ ràng, và đường dẫn phải bắt đầu từ đúng document: payload hay SOAP Envelope.

Trong Spring Web Services, `MockWebServiceClient` cùng payload/XPath matchers giúp kiểm tra response ở endpoint test. XMLUnit hữu ích khi cần so sánh cấu trúc và đọc differences; XSD validator bảo đảm sequence, type, cardinality và facets; SOAP Header/Fault cần assertion theo đúng SOAP version và QName. Những lớp này bổ sung nhau và không thay thế xác minh WS-Security bằng WSS4J thực.

Một suite đáng tin cần positive/negative fixtures, test optional/nil/missing, namespace, sequence, enum, fault detail, XML parser hardening và xác nhận không side effect. **Hãy khóa đúng contract version, dùng fixture độc lập và chỉ ignore những khác biệt thực sự không mang nghĩa nghiệp vụ.** Khi đó test response vừa ổn định trước thay đổi formatting, vừa đủ chặt để phát hiện lỗi tương thích SOAP trong môi trường doanh nghiệp.
