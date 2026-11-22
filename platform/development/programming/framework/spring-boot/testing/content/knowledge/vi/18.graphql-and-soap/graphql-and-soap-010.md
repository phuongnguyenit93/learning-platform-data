# Kiểm tra XML payload, SOAP fault và ánh xạ lỗi

Trong nhóm **GraphQL và SOAP** của Spring Boot, kiểm thử SOAP không thể chỉ kiểm tra một Java method trả đúng giá trị. Hợp đồng còn nằm ở **XML payload, namespace, SOAP Envelope/Body/Header, XSD/WSDL, thông điệp SOAP Fault và cách lỗi ở bên ngoài được chuyển thành lỗi nghiệp vụ an toàn**. Một ứng dụng có thể trả HTTP 500 nhưng vẫn gửi SOAP Fault hợp lệ; ngược lại, một HTTP error không có SOAP Envelope **không phải** một SOAP Fault hợp lệ.

Mục tiêu của bài này là viết được test cho cả hai phía:

- **Client/Gateway gọi SOAP bên ngoài:** gửi đúng XML request, đọc đúng XML response, nhận SOAP Fault và ánh xạ sang lỗi ứng dụng; cô lập mạng bằng `MockWebServiceServer`.
- **SOAP endpoint của ứng dụng:** xử lý request payload đúng namespace, trả response/fault theo contract; dùng `MockWebServiceClient` với context thích hợp khi cần kiểm tra annotation, endpoint adapter và resolver.
- **Mức Java/XML thuần:** parse XML một cách an toàn và kiểm tra structure/fault `detail` mà không phải khởi động Spring context.

Bài cung cấp ví dụ đầy đủ **Java 17+, Spring Boot 3.4/3.5, Spring Web Services (Spring-WS 4.x), JUnit Jupiter**, có test client thật chạy với server giả, demo Java SE chạy bằng `javac/java` và các trường hợp biên về SOAP 1.1/1.2, fault mapping, XXE và dữ liệu nhạy cảm.

## 1. Nhận diện đúng ranh giới SOAP

SOAP message thường gồm Envelope, Header tùy chọn và Body. Một SOAP 1.1 request ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:o="urn:example:orders">
  <s:Header/>
  <s:Body>
    <o:GetOrderRequest>
      <o:orderId>ORD-7</o:orderId>
    </o:GetOrderRequest>
  </s:Body>
</s:Envelope>
```

Payload nghiệp vụ trong Body là **`o:GetOrderRequest`**, còn Envelope là khung SOAP. Khi dùng `WebServiceTemplate.sendSourceAndReceiveToResult(...)`, bạn truyền **payload Source**; Spring-WS đặt payload vào SOAP Body. Không tự lồng một Envelope thứ hai vào payload.

Một SOAP 1.1 response thành công:

```xml
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:o="urn:example:orders">
  <s:Body>
    <o:GetOrderResponse>
      <o:orderId>ORD-7</o:orderId>
      <o:status>PAID</o:status>
    </o:GetOrderResponse>
  </s:Body>
</s:Envelope>
```

Một SOAP 1.1 Fault:

```xml
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:o="urn:example:orders">
  <s:Body>
    <s:Fault>
      <faultcode>s:Client</faultcode>
      <faultstring>Invalid order</faultstring>
      <detail>
        <o:OrderError>
          <o:code>ORDER_NOT_FOUND</o:code>
        </o:OrderError>
      </detail>
    </s:Fault>
  </s:Body>
</s:Envelope>
```

Ở SOAP 1.1, `faultcode` và `faultstring` nằm dưới `Fault`; `detail` chứa thông tin lỗi của ứng dụng nếu contract định nghĩa. Giá trị `s:Client` **là QName**, không phải chỉ một chuỗi có dấu hai chấm. Khi parse, phải resolve prefix `s` thành namespace SOAP Envelope.

### SOAP 1.1 và SOAP 1.2 không giống nhau

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Namespace Envelope | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Lỗi đầu vào phía sender | `Client` | `Sender` |
| Lỗi xử lý phía receiver | `Server` | `Receiver` |
| Vùng mã lỗi | `faultcode` | `Code/Value`, có thể có `Subcode` |
| Thông điệp đọc được | `faultstring` | `Reason/Text` |
| Thông tin lỗi ứng dụng | `detail` | `Detail` |
| MIME thông dụng | `text/xml` | `application/soap+xml` |

Đừng áp dụng XPath của SOAP 1.1 để parse SOAP 1.2 rồi kết luận “không có fault”. Ví dụ SOAP 1.2:

```xml
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Body>
    <env:Fault>
      <env:Code>
        <env:Value>env:Sender</env:Value>
      </env:Code>
      <env:Reason>
        <env:Text xml:lang="en">Invalid request</env:Text>
      </env:Reason>
    </env:Fault>
  </env:Body>
</env:Envelope>
```

Spring-WS có abstraction `SoapVersion.SOAP_11` và `SoapVersion.SOAP_12` để so sánh fault QName. Với parser tự viết, cần **chọn version rồi test version riêng**, không chỉ đổi `faultcode` thành `Code` một cách cơ học.

## 2. Kiểm tra XML theo namespace, không theo prefix cố định

Hai payload sau **tương đương về tên element** nếu contract dựa vào namespace URI và local name:

```xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders">
  <ord:orderId>ORD-7</ord:orderId>
  <ord:status>PAID</ord:status>
</ord:GetOrderResponse>
```

```xml
<x:GetOrderResponse xmlns:x="urn:example:orders">
  <x:orderId>ORD-7</x:orderId>
  <x:status>PAID</x:status>
</x:GetOrderResponse>
```

Prefix `ord` hay `x` chỉ là alias; **expanded name** của element là `{urn:example:orders}GetOrderResponse`. Test byte-for-byte toàn XML dễ thất bại do khác prefix, namespace declaration, whitespace hoặc thuộc tính không có thứ tự cố định dù ý nghĩa XML đúng.

Ngược lại:

```xml
<x:GetOrderResponse xmlns:x="urn:wrong:orders">
  <x:orderId>ORD-7</x:orderId>
  <x:status>PAID</x:status>
</x:GetOrderResponse>
```

là **khác contract** vì namespace URI sai. Test phải fail.

**Những gì nên kiểm tra:**

- Root payload đúng QName (namespace URI + local name).
- Các element bắt buộc xuất hiện đúng số lần, type/giá trị phù hợp.
- Các element nhạy cảm không xuất hiện ngoài schema.
- `orderId`/`status` của response khớp request.
- XML hợp lệ theo XSD khi điều đó thuộc contract; logic ứng dụng có xử lý giá trị biên.
- Với SOAP full envelope: Body chứa chính xác payload hoặc Fault, Header được kiểm tra riêng nếu có WS-Addressing/WS-Security.

Trong Java/JAXP, bật `DocumentBuilderFactory.setNamespaceAware(true)`. Với XPath, đăng ký `NamespaceContext` thay vì phụ thuộc vào prefix thực tế của tài liệu:

```java
XPath xpath = XPathFactory.newInstance().newXPath();
xpath.setNamespaceContext(
        new org.springframework.xml.namespace.SimpleNamespaceContext(
                java.util.Map.of("ord", "urn:example:orders")));
String value = xpath.evaluate(
        "/ord:GetOrderResponse/ord:status", document);
```

Đây là snippet minh họa trong project Spring-WS với đúng imports và object `document` đã parse. Prefix `ord` trong expression là prefix do **test gán**, không bắt buộc trùng prefix trong XML gốc. Bộ Java SE đầy đủ ở mục 5 sử dụng DOM API và `getNamespaceURI()/getLocalName()` để tránh phụ thuộc Spring.

## 3. SOAP Fault, transport failure và lỗi nghiệp vụ là ba lớp khác nhau

Một tích hợp SOAP thường có ít nhất ba loại thất bại:

1. **Transport failure:** DNS, TLS, connection timeout, proxy, HTTP response không có SOAP message hợp lệ. Không nhất thiết có một SOAP Fault.
2. **Protocol/SOAP Fault:** server gửi SOAP Envelope có `Fault`, mã `Client/Server` hoặc `Sender/Receiver`. Đây là lỗi được biểu diễn **bên trong SOAP**, không được suy ra chỉ từ HTTP status.
3. **Business error detail:** SOAP Fault có thể có `detail` với `ORDER_NOT_FOUND`, `VALIDATION_FAILED` hoặc mã lỗi do schema ứng dụng định nghĩa. Đây là lớp dữ liệu nghiệp vụ **tùy WSDL/XSD**, không thuộc tập code tiêu chuẩn của SOAP.

Một bảng mapping **minh họa theo chính sách của gateway**:

| Input từ bên ngoài | Mã nội bộ gợi ý | Retry? | Lưu ý |
| --- | --- | --- | --- |
| SOAP 1.1 `Client` / SOAP 1.2 `Sender`, không có detail đặc biệt | `INVALID_SOAP_REQUEST` | Thường không | Sai request/contract; không tự suy ra HTTP 400 từ SOAP faultcode |
| Client/Sender với `detail.code=ORDER_NOT_FOUND` đã được xác minh | `ORDER_NOT_FOUND` | Không | Mapping dựa vào business contract |
| SOAP 1.1 `Server` / SOAP 1.2 `Receiver` | `UPSTREAM_FAILURE` | Có điều kiện | Chỉ retry nếu operation/idempotency policy cho phép |
| `VersionMismatch`, `MustUnderstand` | `SOAP_PROTOCOL_FAILURE` | Thường không | Sửa version/header/client configuration |
| XML response không parse được / namespace sai | `SOAP_PROTOCOL_FAILURE` | Thường không | Fail closed, không coi là order hợp lệ |
| Network timeout / TLS / 503 không có SOAP envelope | `SOAP_TRANSPORT_FAILURE` | Có điều kiện | Kiểm tra riêng transport, timeout và retry |
| Ứng dụng phát hiện dữ liệu nội bộ sai | `INTERNAL_FAILURE` | Theo policy | Không echo exception/stacktrace ra SOAP faultstring |

**Không ánh xạ `Client → 400` hoặc `Server → 500` một cách máy móc cho mọi hệ thống.** Với SOAP 1.1, HTTP 500 thường đi cùng SOAP Fault, kể cả một fault thuộc lớp Client. Khi SOAP được bọc trong một REST gateway, **HTTP 400/404/502/503** là chính sách do gateway chọn dựa trên contract, không phải một định luật của chuẩn SOAP.

Cũng không lấy chuỗi `faultstring` làm định danh lỗi nghiệp vụ: nó dùng để đọc, có thể bản địa hóa, đổi wording hoặc chứa dữ liệu nhạy cảm. Nếu cần phân biệt `ORDER_NOT_FOUND`, hãy dùng mã có cấu trúc trong `detail` hoặc contract chính thức.

## 4. Chọn tầng test để tránh xanh giả

| Mục tiêu | Công cụ phù hợp | Điều được kiểm tra |
| --- | --- | --- |
| XML parser, namespace, fault detail, XXE | JUnit + JAXP/DOM | Cấu trúc XML thật và mapping thuần Java |
| SOAP client gửi request/nhận response/fault | `MockWebServiceServer` + `WebServiceTemplate` | Client XML payload và fault handling, **không gọi mạng** |
| Spring-WS endpoint mapping, response và fault resolver | `MockWebServiceClient` + context | `@Endpoint`/`@PayloadRoot`/resolver theo config test |
| XSD/WSDL contract | XML schema validator + Spring-WS test matchers | Có tuân thủ các kiểu/schema mà contract yêu cầu |
| HTTP Content-Type/SOAPAction/TLS/proxy/server thực | Integration/E2E HTTP test | Transport và deployment config ở môi trường được nạp |
| REST facade gọi SOAP rồi trả error response | MVC/WebFlux test phù hợp | Mapping SOAP domain error sang HTTP/JSON API của facade |

**Đừng dùng `MockMvc` như thể nó kiểm tra native SOAP endpoint Spring-WS.** MockMvc tập trung vào Spring MVC controllers, còn SOAP endpoint trong Spring-WS được xử lý qua `MessageDispatcher` và `MessageDispatcherServlet`. Với endpoint SOAP, `MockWebServiceClient` là công cụ đúng hơn.

Ngược lại, `MockWebServiceServer` là một **mock phía server để kiểm tra SOAP client**, không phải một embedded SOAP service đang lắng nghe cổng TCP. Tên “Server” ở đây mô tả vai trò đối với client test; không có network thật.

## 5. Demo Java 17 thuần: kiểm tra XML payload và SOAP Fault an toàn

Trước khi mở Spring context, ta tạo parser Java SE độc lập. Parser này **cố ý hỗ trợ SOAP 1.1** cho fixture fault; SOAP 1.2 cần nhánh parsing riêng vì namespace và cấu trúc khác nhau.

### 5.1. Cấu trúc file

```text
src/
├── main/java/example/testing/soap/
│   ├── OrderXml.java
│   ├── SoapContractDemo.java
│   └── OrderSoapClient.java
└── test/java/example/testing/soap/
    ├── OrderXmlTest.java
    └── OrderSoapClientTest.java
```

`OrderXml.java` và `SoapContractDemo.java` chỉ phụ thuộc Java SE; có thể chạy `javac/java` với JDK 17+ để kiểm tra cấu trúc XML và policy mapping. `OrderSoapClient.java` và test client cần Spring Web Services dependencies từ Gradle.

### 5.2. Parser an toàn: OrderXml.java

Tạo `src/main/java/example/testing/soap/OrderXml.java`:

```java
package example.testing.soap;

import java.io.StringReader;
import java.util.Objects;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.xml.sax.InputSource;

public final class OrderXml {
    public static final String ORDERS_NS = "urn:example:orders";
    public static final String SOAP11_NS =
            "http://schemas.xmlsoap.org/soap/envelope/";

    private OrderXml() {
    }

    public record OrderStatus(String orderId, String status) {
    }

    public record FaultView(
            String faultCode, String detailCode, String reason) {
    }

    public enum ErrorKind {
        NOT_FOUND,
        INVALID_REQUEST,
        UPSTREAM_FAILURE,
        PROTOCOL_FAILURE
    }

    public static Document parseSecure(String xml) {
        Objects.requireNonNull(xml, "xml");
        if (xml.length() > 100_000) {
            throw new IllegalArgumentException("XML too large");
        }

        try {
            DocumentBuilderFactory factory =
                    DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature(
                    XMLConstants.FEATURE_SECURE_PROCESSING, true);
            factory.setFeature(
                    "http://apache.org/xml/features/disallow-doctype-decl",
                    true);
            factory.setFeature(
                    "http://xml.org/sax/features/external-general-entities",
                    false);
            factory.setFeature(
                    "http://xml.org/sax/features/external-parameter-entities",
                    false);
            factory.setFeature(
                    "http://apache.org/xml/features/nonvalidating/load-external-dtd",
                    false);
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);
            factory.setAttribute(
                    XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(
                    XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

            return factory.newDocumentBuilder().parse(
                    new InputSource(new StringReader(xml)));
        } catch (Exception error) {
            throw new IllegalArgumentException(
                    "Invalid or unsafe XML", error);
        }
    }

    private static Element directChild(
            Element parent, String ns, String localName) {
        Element found = null;
        for (Node node = parent.getFirstChild();
                node != null; node = node.getNextSibling()) {
            if (node instanceof Element element
                    && Objects.equals(ns, element.getNamespaceURI())
                    && localName.equals(element.getLocalName())) {
                if (found != null) {
                    throw new IllegalArgumentException(
                            "Duplicate element: " + localName);
                }
                found = element;
            }
        }
        return found;
    }

    private static Element requiredChild(
            Element parent, String ns, String localName) {
        Element found = directChild(parent, ns, localName);
        if (found == null) {
            throw new IllegalArgumentException(
                    "Missing element: " + localName);
        }
        return found;
    }

    private static String text(Element element) {
        return element.getTextContent().trim();
    }

    public static OrderStatus readPayload(String xml) {
        Element root = parseSecure(xml).getDocumentElement();
        if (!ORDERS_NS.equals(root.getNamespaceURI())
                || !"GetOrderResponse".equals(root.getLocalName())) {
            throw new IllegalArgumentException(
                    "Unexpected response QName");
        }

        String id = text(requiredChild(root, ORDERS_NS, "orderId"));
        String status = text(
                requiredChild(root, ORDERS_NS, "status"));

        if (!id.matches("ORD-[0-9]{1,6}")
                || !(status.equals("PAID")
                     || status.equals("PENDING"))) {
            throw new IllegalArgumentException(
                    "Invalid order response fields");
        }

        return new OrderStatus(id, status);
    }

    public static FaultView readSoap11Fault(String envelopeXml) {
        Element envelope = parseSecure(envelopeXml)
                .getDocumentElement();
        if (!SOAP11_NS.equals(envelope.getNamespaceURI())
                || !"Envelope".equals(envelope.getLocalName())) {
            throw new IllegalArgumentException(
                    "Not a SOAP 1.1 Envelope");
        }

        Element body = requiredChild(
                envelope, SOAP11_NS, "Body");
        Element fault = requiredChild(
                body, SOAP11_NS, "Fault");
        Element faultCode = requiredChild(
                fault, null, "faultcode");

        String lexicalCode = text(faultCode);
        int separator = lexicalCode.indexOf(':');
        if (separator <= 0 || separator == lexicalCode.length() - 1) {
            throw new IllegalArgumentException(
                    "Fault code needs a bound prefix");
        }

        String prefix = lexicalCode.substring(0, separator);
        String localCode = lexicalCode.substring(separator + 1);
        String namespace = faultCode.lookupNamespaceURI(prefix);

        if (!SOAP11_NS.equals(namespace)) {
            throw new IllegalArgumentException(
                    "Fault code namespace mismatch");
        }

        String reason = text(requiredChild(
                fault, null, "faultstring"));

        String detailCode = "";
        Element detail = directChild(fault, null, "detail");
        if (detail != null) {
            Element orderError = directChild(
                    detail, ORDERS_NS, "OrderError");
            if (orderError != null) {
                detailCode = text(requiredChild(
                        orderError, ORDERS_NS, "code"));
            }
        }

        return new FaultView(localCode, detailCode, reason);
    }

    public static ErrorKind classify(FaultView fault) {
        return switch (fault.faultCode()) {
            case "Client" ->
                    "ORDER_NOT_FOUND".equals(fault.detailCode())
                            ? ErrorKind.NOT_FOUND
                            : ErrorKind.INVALID_REQUEST;
            case "Server" -> ErrorKind.UPSTREAM_FAILURE;
            default -> ErrorKind.PROTOCOL_FAILURE;
        };
    }
}
```

**Điểm đáng kiểm thử trong parser:**

- `setNamespaceAware(true)` khiến DOM nhìn thấy namespace URI/local name thay vì so prefix text.
- `disallow-doctype-decl` chặn DOCTYPE, giảm nguy cơ **XXE/SSRF/file disclosure**. Các cờ tắt external entities/DTD và `ACCESS_EXTERNAL_DTD/SCHEMA` bổ sung phòng vệ. Nếu provider không hỗ trợ cài đặt bảo mật, code **fail closed** bằng exception, không âm thầm bật parse không an toàn.
- `directChild(...)` chỉ lấy **child trực tiếp**, không dùng `getElementsByTagNameNS(...)` trên mọi descendants rồi nhận nhầm một trường cùng tên ở tầng khác.
- Nếu có **hai element bắt buộc cùng tên** trong một parent, parser từ chối thay vì lặng lẽ chọn phần tử đầu tiên.
- `FaultView` giữ fault code, mã business ở `detail` và reason để phân tích. `classify(...)` chỉ dùng **code có cấu trúc**, không phân loại bằng câu tiếng Anh trong reason.
- Parser này giới hạn SOAP **1.1** ở `readSoap11Fault`. Với SOAP 1.2 phải parse `env:Code/env:Value`, `env:Reason/env:Text` và `env:Detail` riêng hoặc dùng Spring-WS abstraction.

**Hạn chế cần nêu đúng:** đây là parser minh họa tối giản, chưa thay thế việc validate **XSD/WSDL** và chưa cung cấp đủ schema/size/depth constraints của production. Nếu dữ liệu XML đầu vào từ đối tác không đáng tin, còn cần giới hạn kích thước request, độ sâu/nested nodes, thời gian parse và chính sách transport. Không log raw payload chứa token, địa chỉ hoặc PII.

### 5.3. Demo Java SE: SoapContractDemo.java

Tạo `src/main/java/example/testing/soap/SoapContractDemo.java`:

```java
package example.testing.soap;

public class SoapContractDemo {
    public static void main(String[] args) {
        String payload = """
                <o:GetOrderResponse xmlns:o="urn:example:orders">
                  <o:orderId>ORD-7</o:orderId>
                  <o:status>PAID</o:status>
                </o:GetOrderResponse>
                """;

        String clientFault = """
                <s:Envelope
                  xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:o="urn:example:orders">
                  <s:Body>
                    <s:Fault>
                      <faultcode>s:Client</faultcode>
                      <faultstring>Invalid order</faultstring>
                      <detail>
                        <o:OrderError>
                          <o:code>ORDER_NOT_FOUND</o:code>
                        </o:OrderError>
                      </detail>
                    </s:Fault>
                  </s:Body>
                </s:Envelope>
                """;

        String serverFault = """
                <s:Envelope
                  xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
                  <s:Body>
                    <s:Fault>
                      <faultcode>s:Server</faultcode>
                      <faultstring>Temporary failure</faultstring>
                    </s:Fault>
                  </s:Body>
                </s:Envelope>
                """;

        OrderXml.OrderStatus order =
                OrderXml.readPayload(payload);
        OrderXml.FaultView fault =
                OrderXml.readSoap11Fault(clientFault);

        System.out.println(
                order.orderId() + " | " + order.status());
        System.out.println(
                fault.faultCode() + " | " + fault.detailCode());
        System.out.println(OrderXml.classify(fault));
        System.out.println(OrderXml.classify(
                OrderXml.readSoap11Fault(serverFault)));
    }
}
```

Biên dịch và chạy với **JDK 17+**, từ root project:

```bash
javac -d out src/main/java/example/testing/soap/OrderXml.java src/main/java/example/testing/soap/SoapContractDemo.java
java -cp out example.testing.soap.SoapContractDemo
```

Stdout chính xác:

```text
ORD-7 | PAID
Client | ORDER_NOT_FOUND
NOT_FOUND
UPSTREAM_FAILURE
```

Đây là **demo Java SE hoàn chỉnh**, không cần Spring. Nó kiểm tra parser, QName của SOAP 1.1 Fault và bảng ánh xạ lỗi nghiệp vụ minh họa. Nó **không chứng minh** một SOAP HTTP request thực sự đã được gửi hoặc Spring-WS endpoint được đăng ký. Đó là trách nhiệm của phần test với Spring-WS và test integration tương ứng.

## 6. Unit test XML: đúng payload, namespace và XXE

Tạo `src/test/java/example/testing/soap/OrderXmlTest.java`:

```java
package example.testing.soap;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderXmlTest {

    @Test
    void acceptsDifferentPrefixWithSameNamespace() {
        String payload = """
                <x:GetOrderResponse xmlns:x="urn:example:orders">
                  <x:orderId>ORD-7</x:orderId>
                  <x:status>PAID</x:status>
                </x:GetOrderResponse>
                """;

        assertEquals(
                new OrderXml.OrderStatus("ORD-7", "PAID"),
                OrderXml.readPayload(payload));
    }

    @Test
    void rejectsWrongNamespace() {
        String payload = """
                <x:GetOrderResponse xmlns:x="urn:wrong:orders">
                  <x:orderId>ORD-7</x:orderId>
                  <x:status>PAID</x:status>
                </x:GetOrderResponse>
                """;

        assertThrows(IllegalArgumentException.class,
                () -> OrderXml.readPayload(payload));
    }

    @Test
    void rejectsDuplicateRequiredElement() {
        String payload = """
                <o:GetOrderResponse xmlns:o="urn:example:orders">
                  <o:orderId>ORD-7</o:orderId>
                  <o:orderId>ORD-8</o:orderId>
                  <o:status>PAID</o:status>
                </o:GetOrderResponse>
                """;

        assertThrows(IllegalArgumentException.class,
                () -> OrderXml.readPayload(payload));
    }

    @Test
    void rejectsDoctypeBeforeEntityExpansion() {
        String payload = """
                <!DOCTYPE data [
                  <!ENTITY example SYSTEM "file:///no-such-file">
                ]>
                <o:GetOrderResponse xmlns:o="urn:example:orders">
                  <o:orderId>&example;</o:orderId>
                  <o:status>PAID</o:status>
                </o:GetOrderResponse>
                """;

        assertThrows(IllegalArgumentException.class,
                () -> OrderXml.readPayload(payload));
    }

    @Test
    void mapsBusinessCodeFromSoap11Detail() {
        String xml = """
                <s:Envelope
                  xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:o="urn:example:orders">
                  <s:Body>
                    <s:Fault>
                      <faultcode>s:Client</faultcode>
                      <faultstring>Readable reason</faultstring>
                      <detail>
                        <o:OrderError>
                          <o:code>ORDER_NOT_FOUND</o:code>
                        </o:OrderError>
                      </detail>
                    </s:Fault>
                  </s:Body>
                </s:Envelope>
                """;

        OrderXml.FaultView fault =
                OrderXml.readSoap11Fault(xml);

        assertEquals("Client", fault.faultCode());
        assertEquals("ORDER_NOT_FOUND", fault.detailCode());
        assertEquals(
                OrderXml.ErrorKind.NOT_FOUND,
                OrderXml.classify(fault));
    }
}
```

**Năm method test trên** kiểm tra:

1. XML cùng namespace nhưng khác prefix phải được chấp nhận.
2. Namespace sai phải bị từ chối.
3. Có hai element `orderId` phải bị từ chối (đề phòng data ambiguity).
4. DOCTYPE/external entity không được xử lý, ngăn đường XXE minh họa.
5. SOAP 1.1 Fault có `detail.code=ORDER_NOT_FOUND` phải ánh xạ `NOT_FOUND`.

Một test chỉ `assertTrue(xml.contains("PAID"))` sẽ bỏ sót XML có namespace sai hoặc nhiều field lồng nhau. Việc parse DOM an toàn và kiểm tra QName/số lượng giúp assertion thực sự bảo vệ **cấu trúc thông điệp**.

## 7. Spring-WS client: tạo payload, nhận kết quả và ánh xạ SOAP Fault

### 7.1. Tách lỗi nghiệp vụ ra khỏi raw fault

Để tránh mã trong controller phụ thuộc trực tiếp vào SOAP infrastructure, client chuyển `SoapFaultClientException` thành một exception thuộc tầng tích hợp:

| `GatewayError` | Ý nghĩa | `retryable` mặc định |
| --- | --- | --- |
| `INVALID_REQUEST` | Upstream nhận lỗi Sender/Client | `false` |
| `UPSTREAM_UNAVAILABLE` | Upstream báo Receiver/Server hoặc I/O failure | `true` **chỉ là tín hiệu**, còn cần policy idempotency |
| `SOAP_PROTOCOL_ERROR` | Fault code không nhận diện, XML sai QName/schema | `false` |
| `EMPTY_RESPONSE` | Request hoàn tất nhưng không có payload như contract | `false` |

**Lưu ý:** ví dụ Spring-WS client bên dưới ánh xạ theo **standard SOAP fault QName**. Nó không tự đọc business detail `ORDER_NOT_FOUND`; nếu đối tác yêu cầu phân loại 404 theo detail, cần mở rộng gateway để đọc `SoapFault.getFaultDetail()` theo schema đã thỏa thuận và test riêng. Không được đoán NOT_FOUND chỉ vì reason chứa chữ “not found”.

### 7.2. File Spring-WS: OrderSoapClient.java

Tạo `src/main/java/example/testing/soap/OrderSoapClient.java`:

```java
package example.testing.soap;

import java.io.StringWriter;
import java.util.Objects;

import javax.xml.namespace.QName;
import javax.xml.transform.stream.StreamResult;

import org.springframework.ws.client.WebServiceIOException;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.xml.transform.StringSource;

public final class OrderSoapClient {
    private final WebServiceTemplate template;

    public OrderSoapClient(WebServiceTemplate template) {
        this.template = Objects.requireNonNull(
                template, "template");
    }

    public OrderXml.OrderStatus fetch(String orderId) {
        if (orderId == null
                || !orderId.matches("ORD-[0-9]{1,6}")) {
            throw new IllegalArgumentException(
                    "Invalid orderId");
        }

        String requestXml = """
                <o:GetOrderRequest xmlns:o="urn:example:orders">
                  <o:orderId>%s</o:orderId>
                </o:GetOrderRequest>
                """.formatted(orderId);

        StringWriter responseWriter = new StringWriter();

        try {
            boolean received =
                    template.sendSourceAndReceiveToResult(
                            new StringSource(requestXml),
                            new StreamResult(responseWriter));

            if (!received) {
                throw new GatewayException(
                        GatewayError.EMPTY_RESPONSE, false);
            }

            OrderXml.OrderStatus result =
                    OrderXml.readPayload(
                            responseWriter.toString());

            if (!orderId.equals(result.orderId())) {
                throw new GatewayException(
                        GatewayError.SOAP_PROTOCOL_ERROR, false);
            }

            return result;
        } catch (SoapFaultClientException fault) {
            throw mapFault(fault);
        } catch (WebServiceIOException transport) {
            throw new GatewayException(
                    GatewayError.UPSTREAM_UNAVAILABLE, true);
        } catch (IllegalArgumentException badPayload) {
            throw new GatewayException(
                    GatewayError.SOAP_PROTOCOL_ERROR, false);
        }
    }

    private static GatewayException mapFault(
            SoapFaultClientException fault) {
        QName code = fault.getFaultCode();

        if (SoapVersion.SOAP_11
                    .getClientOrSenderFaultName().equals(code)
                || SoapVersion.SOAP_12
                    .getClientOrSenderFaultName().equals(code)) {
            return new GatewayException(
                    GatewayError.INVALID_REQUEST, false);
        }

        if (SoapVersion.SOAP_11
                    .getServerOrReceiverFaultName().equals(code)
                || SoapVersion.SOAP_12
                    .getServerOrReceiverFaultName().equals(code)) {
            return new GatewayException(
                    GatewayError.UPSTREAM_UNAVAILABLE, true);
        }

        return new GatewayException(
                GatewayError.SOAP_PROTOCOL_ERROR, false);
    }
}

enum GatewayError {
    INVALID_REQUEST,
    UPSTREAM_UNAVAILABLE,
    SOAP_PROTOCOL_ERROR,
    EMPTY_RESPONSE
}

final class GatewayException extends RuntimeException {
    private final GatewayError code;
    private final boolean retryable;

    GatewayException(GatewayError code, boolean retryable) {
        super(code.name());
        this.code = code;
        this.retryable = retryable;
    }

    public GatewayError code() {
        return code;
    }

    public boolean retryable() {
        return retryable;
    }
}
```

Tính runnable:

- File có một top-level `public` class `OrderSoapClient`; enum `GatewayError` và `GatewayException` là package-private, nên JUnit tests cùng package truy cập được.
- Client nhận `WebServiceTemplate` qua constructor, dễ kiểm tra bằng `MockWebServiceServer` và không phụ thuộc ApplicationContext.
- `orderId.matches(...)` **allowlist ký tự** trước khi đưa ID vào XML text block. Mục tiêu là tránh XML injection trong ví dụ; production có dữ liệu linh hoạt hơn nên dùng JAXB/DOM XML writer an toàn thay vì tự nối XML string.
- `sendSourceAndReceiveToResult(...)` gửi **XML payload** và ghi phần payload của response vào `StreamResult`; Spring-WS xử lý SOAP Envelope/Fault.
- `OrderXml.readPayload(...)` kiểm tra root QName, fields, namespace; client còn kiểm tra `orderId` response đúng request.
- `SoapFaultClientException.getFaultCode()` trả `QName`; so theo `SoapVersion`, **không so mỗi local part** và không dựa vào `faultstring`.
- Error truyền ra ngoài là một code có kiểm soát; **không copy raw `fault.getFaultStringOrReason()`** vào message trả cho REST/UI/log không được kiểm soát.
- `GatewayError.UPSTREAM_UNAVAILABLE` có flag `retryable=true` trong ví dụ, nhưng retry thực tế **chỉ được phép** nếu operation là read-only/idempotent hoặc có idempotency key và chính sách tránh side effect trùng.

Đây là client **Spring-WS SOAP 1.1 mặc định** trong bộ test bên dưới. Với SOAP 1.2 production, cấu hình `SoapMessageFactory` tương ứng và test Content-Type/Fault riêng; không mặc định hai version dùng một Envelope.

### 7.3. Cấu hình Gradle cho Spring Boot 3.4/3.5

Trong project đã có Spring Boot Gradle plugin, repositories, Java toolchain và dependency management phù hợp, phần liên quan ở `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web-services'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.ws:spring-ws-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung** cho một project Spring Boot hoàn chỉnh, không phải toàn bộ build file. `spring-boot-starter-web-services` cung cấp Spring-WS integration và SAAJ dependencies phù hợp trong Boot 3.4/3.5. `spring-ws-test` cung cấp `MockWebServiceServer`/`MockWebServiceClient`. Các ví dụ không bắt buộc JAXB classes được sinh từ XSD vì đang dùng `Source/Result`; dự án thực thường dùng JAXB và WSDL code generation để có contract type-safe.

Với Spring Boot 4.x, module starter/test auto-configuration và packages có thể khác; kiểm tra đúng Boot BOM và tài liệu version thay vì copy một dependency set cũ một cách máy móc.

## 8. Bộ test client-side: MockWebServiceServer

Tạo `src/test/java/example/testing/soap/OrderSoapClientTest.java`:

```java
package example.testing.soap;

import java.util.Locale;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import static org.springframework.ws.test.client.ResponseCreators.withClientOrSenderFault;
import static org.springframework.ws.test.client.ResponseCreators.withServerOrReceiverFault;

class OrderSoapClientTest {
    private static final String REQUEST = """
            <o:GetOrderRequest xmlns:o="urn:example:orders">
              <o:orderId>ORD-7</o:orderId>
            </o:GetOrderRequest>
            """;

    private static final String RESPONSE = """
            <o:GetOrderResponse xmlns:o="urn:example:orders">
              <o:orderId>ORD-7</o:orderId>
              <o:status>PAID</o:status>
            </o:GetOrderResponse>
            """;

    private MockWebServiceServer server;
    private OrderSoapClient client;

    @BeforeEach
    void setUp() {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri(
                "https://soap.example.invalid/orders");
        server = MockWebServiceServer.createServer(template);
        client = new OrderSoapClient(template);
    }

    @Test
    void matchesRequestAndParsesSuccessPayload() {
        server.expect(payload(new StringSource(REQUEST)))
                .andRespond(withPayload(
                        new StringSource(RESPONSE)));

        OrderXml.OrderStatus result =
                client.fetch("ORD-7");

        assertEquals("ORD-7", result.orderId());
        assertEquals("PAID", result.status());
        server.verify();
    }

    @Test
    void clientFaultMapsToNonRetryableInvalidRequest() {
        server.expect(payload(new StringSource(REQUEST)))
                .andRespond(withClientOrSenderFault(
                        "Invalid SOAP request",
                        Locale.ENGLISH));

        GatewayException error = assertThrows(
                GatewayException.class,
                () -> client.fetch("ORD-7"));

        assertEquals(GatewayError.INVALID_REQUEST,
                error.code());
        assertFalse(error.retryable());
        server.verify();
    }

    @Test
    void serverFaultMapsToUpstreamUnavailable() {
        server.expect(payload(new StringSource(REQUEST)))
                .andRespond(withServerOrReceiverFault(
                        "Temporary SOAP failure",
                        Locale.ENGLISH));

        GatewayException error = assertThrows(
                GatewayException.class,
                () -> client.fetch("ORD-7"));

        assertEquals(GatewayError.UPSTREAM_UNAVAILABLE,
                error.code());
        assertTrue(error.retryable());
        server.verify();
    }

    @Test
    void malformedResponseQNameIsProtocolError() {
        String wrongResponse = """
                <x:GetOrderResponse xmlns:x="urn:wrong:orders">
                  <x:orderId>ORD-7</x:orderId>
                  <x:status>PAID</x:status>
                </x:GetOrderResponse>
                """;

        server.expect(payload(new StringSource(REQUEST)))
                .andRespond(withPayload(
                        new StringSource(wrongResponse)));

        GatewayException error = assertThrows(
                GatewayException.class,
                () -> client.fetch("ORD-7"));

        assertEquals(GatewayError.SOAP_PROTOCOL_ERROR,
                error.code());
        server.verify();
    }

    @Test
    void rejectsInvalidIdBeforeSendingAnyRequest() {
        assertThrows(IllegalArgumentException.class,
                () -> client.fetch("<bad>"));

        // Không có request được khai báo hoặc gửi.
        server.verify();
    }
}
```

**Năm test methods** trên không mở kết nối thật đến `soap.example.invalid`. `MockWebServiceServer.createServer(template)` thay message sender trong template bằng mock, kiểm tra SOAP request payload rồi dựng response/fault theo kịch bản.

Các lớp bằng chứng:

1. `matchesRequestAndParsesSuccessPayload`: request XML đúng namespace/cấu trúc, response payload được parse thành `OrderStatus` và method trả dữ liệu đúng. `server.verify()` xác nhận kỳ vọng gửi request đã thực sự được dùng.
2. `clientFaultMapsToNonRetryableInvalidRequest`: một SOAP 1.1 `Client` fault từ mock server làm `WebServiceTemplate` phát `SoapFaultClientException`; gateway chuyển thành code ứng dụng `INVALID_REQUEST`, không retry.
3. `serverFaultMapsToUpstreamUnavailable`: fault `Server` được ánh xạ `UPSTREAM_UNAVAILABLE`, flag retryable theo policy ví dụ; **không tự kích hoạt retry**.
4. `malformedResponseQNameIsProtocolError`: SOAP response có root payload namespace sai bị từ chối, không trả một order thành công giả.
5. `rejectsInvalidIdBeforeSendingAnyRequest`: ID chứa ký tự không được phép bị chặn trước khi gửi XML; test không khai báo request nào cho mock server.

**Không nên gọi test này là E2E SOAP server test**: server giả không có network, TLS, proxy, X.509, WS-Security hoặc service deployment. Nó là **client integration test với transport mock**. Khi cần chứng minh thật sự giao tiếp được với đối tác, bổ sung contract/HTTP integration tests ở môi trường an toàn và có dữ liệu test.

### 8.1. Chạy các test bằng Gradle

Từ thư mục gốc project có Gradle wrapper:

```bash
./gradlew test --tests example.testing.soap.OrderXmlTest
./gradlew test --tests example.testing.soap.OrderSoapClientTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.soap.OrderXmlTest"
.\gradlew.bat test --tests "example.testing.soap.OrderSoapClientTest"
```

**Kỳ vọng:** `OrderXmlTest` có 5 methods, `OrderSoapClientTest` có 5 methods, tổng **10 JUnit tests** pass khi source và dependencies khớp ví dụ. Không gán một chuỗi stdout cố định cho Gradle/JUnit vì runner/logging khác nhau.

Nếu test client báo lỗi không tạo được SOAP message factory, kiểm tra starter và SAAJ implementation trong dependencies. Nếu payload matcher fail, kiểm tra QName, namespace URI và thứ tự elements theo contract; không “sửa” bằng cách bỏ qua XML body. Nếu fault test không ném `SoapFaultClientException`, kiểm tra message factory, fault resolver của template và SOAP version đang được cấu hình.

## 9. Server-side SOAP endpoint: exception → SOAP Fault

Đối với **SOAP server** do bạn triển khai, Spring-WS có annotation mapping và exception resolver chuyên dụng. Mẫu dưới đây là **các đoạn minh họa**, không phải class độc lập đã được setup sẵn: cần endpoint configuration, schema, message factory, resolver và bean scanning phù hợp.

Một exception có policy public:

```java
@SoapFault(
        faultCode = FaultCode.CLIENT,
        faultStringOrReason = "Invalid order request",
        locale = "en")
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException() {
        super("Internal validation failed");
    }
}
```

Code cần imports `org.springframework.ws.soap.server.endpoint.annotation.SoapFault` và `FaultCode`, cùng một file Java theo tên class. Để annotation này có tác dụng, Spring-WS phải dùng `SoapFaultAnnotationExceptionResolver` trong context. **Annotation đặt trên exception không tự đảm bảo resolver đã được đăng ký.**

Ví dụ đăng ký resolver trong một `@Configuration`:

```java
@Bean
SoapFaultAnnotationExceptionResolver soapFaultResolver() {
    SoapFaultAnnotationExceptionResolver resolver =
            new SoapFaultAnnotationExceptionResolver();
    resolver.setOrder(1);
    return resolver;
}
```

Đây là method minh họa trong configuration class, cần import `@Bean` và `SoapFaultAnnotationExceptionResolver`. Nếu ứng dụng đã có resolver khác, cần xem order và thứ tự xử lý để tránh một generic resolver bắt lỗi trước và làm mapping mong muốn không chạy.

**Bẫy bảo mật:** cấu hình mặc định ở một số resolver có thể sử dụng exception message làm fault reason khi không khai báo reason công khai. Đừng đẩy raw SQL, JWT, token, stack trace hoặc tên bảng vào SOAP Fault. Đặt faultstring/reason có kiểm soát, còn thông tin chẩn đoán chi tiết chỉ nên ở log an toàn với masking.

### 9.1. MockWebServiceClient khác MockWebServiceServer

| Công cụ | Phía nào được kiểm tra? | Bạn mô phỏng gì? |
| --- | --- | --- |
| `org.springframework.ws.test.client.MockWebServiceServer` | SOAP **client** | Tạo server giả trả payload hoặc fault |
| `org.springframework.ws.test.server.MockWebServiceClient` | SOAP **server/endpoint** | Gửi request giả vào dispatcher/endpoint của context |
| `MockMvc` | Spring MVC REST controller | HTTP servlet request đến MVC mapping |
| HTTP client thật + server test | SOAP transport qua mạng | Content-Type, SOAPAction, TLS, reverse proxy, status |

Ví dụ syntax server-side:

```java
MockWebServiceClient mockClient =
        MockWebServiceClient.createClient(applicationContext);

mockClient.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(requestPayload)))
        .andExpect(ResponseMatchers.payload(
                new StringSource(expectedPayload)))
        .andExpect(ResponseMatchers.noFault());
```

Đây là snippet minh họa trong JUnit test có `ApplicationContext`, `requestPayload` và `expectedPayload` đã định nghĩa, cùng imports Spring-WS. Nó **không chạy độc lập** nếu chưa có `@Endpoint`/`@PayloadRoot`/resolver trong context. Mục tiêu là xác nhận endpoint thực tạo đúng response payload, không dùng một server giả để kiểm tra server.

### 9.2. Test SOAP Fault của endpoint

Khi endpoint ném `InvalidOrderException` và resolver tạo Client/Sender fault:

```java
mockClient.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(invalidRequest)))
        .andExpect(
                ResponseMatchers.clientOrSenderFault(
                        "Invalid order request"));
```

Snippet trên yêu cầu `invalidRequest` kích hoạt exception thật và resolver đã được nạp. Nó kiểm tra **loại fault và public fault reason**. Nếu contract còn yêu cầu `detail.code`, cần bổ sung matcher cho SOAP Envelope/Detail/XPath hoặc parse fault để kiểm tra mã business theo namespace.

**Không chỉ test response status:** Spring-WS endpoint có thể gửi một SOAP Fault hoàn toàn đúng mà test REST-style `status().isBadRequest()` không phù hợp. Phải kiểm tra **SOAP Fault trong Body** và transport status riêng nếu nó là phần contract.

## 10. Test XSD/WSDL contract thay vì chỉ so vài field

Một SOAP integration ổn định cần kiểm tra **message shape** theo XSD/WSDL đã thỏa thuận:

- Element names và namespaces; required/optional fields, `minOccurs/maxOccurs`.
- Type của number, date/time, decimal precision, enum values, `nillable`, empty string vs missing element.
- Thứ tự elements nếu XSD dùng `xs:sequence`.
- Fault `detail` structure, business error codes và namespace.
- Headers/WS-Addressing/action/WS-Security khi endpoint yêu cầu.
- Endpoint URL, binding SOAP 1.1/1.2, Content-Type và SOAPAction khi test transport.

Trong Spring-WS test matchers, các method `validPayload(schemaResource)`, `payload(expectedSource)` và XPath matchers có thể giúp kiểm tra XSD/structure. Khi chỉ dùng `payload(...)` để so với fixture, test bảo vệ **một mẫu XML**, chưa chắc bao phủ mọi constraint của XSD. Ngược lại, một XSD test có thể xanh nhưng business mapping của `ORDER_NOT_FOUND` vẫn sai.

**Chiến lược ba lớp:**

1. **Schema contract tests:** request/response/fault detail phải hợp lệ theo XSD và dùng đúng namespace.
2. **Behavior tests:** với id hợp lệ, status đúng; với id không tồn tại, fault/response đúng chính sách; không rò thông tin nhạy cảm.
3. **Transport/integration tests:** HTTP status, Content-Type, SOAPAction, TLS, WS-Security, retry/timeout thực sự; không đòi test giả server chứng minh các phần này.

Khi WSDL do đối tác cung cấp thay đổi, cập nhật generated types/fixtures và chạy regression tests. Không “nới” XPath để bỏ qua namespace sai chỉ vì WSDL mới không tương thích; hãy đánh giá versioning contract có chủ đích.

## 11. Ánh xạ lỗi sang REST/GraphQL facade

Một ứng dụng có thể cung cấp REST hoặc GraphQL ở phía người dùng nhưng gọi SOAP ở phía sau. Khi đó nên **cô lập SOAP exception ở adapter layer**:

```text
SOAP external service
    |
    +-- Success XML payload
    |       --> OrderStatus (domain DTO)
    |
    +-- SOAP Client/Sender Fault
    |       --> INVALID_REQUEST / business detail mapping
    |
    +-- SOAP Server/Receiver Fault
    |       --> UPSTREAM_UNAVAILABLE
    |
    +-- Transport failure
    |       --> SOAP_TRANSPORT_FAILURE
    |
    +-- Malformed XML / wrong namespace
            --> SOAP_PROTOCOL_ERROR

Domain/port layer
    |
    +-- REST API: map stable codes -> HTTP status + safe JSON
    |
    +-- GraphQL API: map stable codes -> GraphQL errors/extensions policy
```

Với REST facade, một **ví dụ chính sách**, không phải quy tắc cố định của SOAP:

| Domain error | HTTP phía facade gợi ý | Public response |
| --- | ---: | --- |
| `INVALID_REQUEST` do client request không hợp lệ | 400 | `{"code":"INVALID_ORDER_REQUEST"}` |
| `NOT_FOUND` được xác nhận từ fault detail | 404 | `{"code":"ORDER_NOT_FOUND"}` |
| `UPSTREAM_UNAVAILABLE` | 502 hoặc 503 tùy nguyên nhân | `{"code":"ORDER_SERVICE_UNAVAILABLE"}` |
| `SOAP_PROTOCOL_ERROR` | 502 | `{"code":"UPSTREAM_PROTOCOL_ERROR"}` |

**Với GraphQL**, response có thể có HTTP 200 kèm mảng `errors` tùy loại failure và chính sách GraphQL transport; không được áp một bảng HTTP của REST lên GraphQL mà không xem contract. Cần kiểm tra `errors[].extensions.code`/field-level partial data phù hợp nhưng **không echo raw SOAP fault reason**.

**Đặc biệt:** một SOAP Client fault có thể do **chính adapter của bạn tạo request sai**, không phải lỗi input của người dùng. Đừng tự trả 400 cho người dùng nếu bug ở serializer/wiring. Cần phân biệt “invalid input do user”, “invalid SOAP request do adapter” và “business not found” dựa trên mã detail và ranh giới đã xác minh.

### Retry và idempotency

`UPSTREAM_UNAVAILABLE` không có nghĩa luôn retry an toàn. Với SOAP action chuyển tiền, tạo order hoặc ghi dữ liệu, request có thể đã được upstream xử lý trước khi timeout; retry mù có thể tạo giao dịch trùng. Chỉ retry khi:

- Operation đọc/idempotent hoặc upstream có idempotency key/bộ cơ chế chống duplicate.
- Error thuộc nhóm retryable theo contract; có backoff, retry limit và circuit breaker phù hợp.
- Có metrics/log tracing an toàn để chẩn đoán; không ghi raw credentials, WS-Security headers hoặc PII.

Tất cả những policy này cần **test riêng** theo risk; test `GatewayException.retryable()==true` chỉ xác nhận flag mapping, không chứng minh hệ thống đã retry đúng hay không tạo side effects.

## 12. SOAP Fault detail: không nhầm mã tiêu chuẩn và mã ứng dụng

Trở lại fixture:

```xml
<s:Fault xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
         xmlns:o="urn:example:orders">
  <faultcode>s:Client</faultcode>
  <faultstring>Order was not found</faultstring>
  <detail>
    <o:OrderError>
      <o:code>ORDER_NOT_FOUND</o:code>
    </o:OrderError>
  </detail>
</s:Fault>
```

Có hai cấp mã:

- **`faultcode=s:Client`**: lỗi loại request ở SOAP 1.1; nhiều lỗi khác nhau có thể cùng code này.
- **`detail/o:OrderError/o:code=ORDER_NOT_FOUND`**: mã ứng dụng của service **nếu WSDL/XSD định nghĩa cấu trúc này**.

Bộ `OrderXml.readSoap11Fault(...)` parse **full Envelope**, resolve prefix `s`, đọc `detail` và phân loại `ORDER_NOT_FOUND`. Bộ `OrderSoapClientTest` tạo fault bằng `withClientOrSenderFault(...)` nhưng **không có custom detail**; test này chỉ chứng minh mapping theo standard fault code.

**Không tuyên bố test client đã bảo vệ `ORDER_NOT_FOUND` nếu chưa test detail trên đường đi thật của SOAP client.** Nếu integration contract yêu cầu điều đó, hãy mở rộng adapter để lấy `SoapFaultClientException.getSoapFault().getFaultDetail()`, chuyển các `SoapFaultDetailElement` sang schema parser có kiểm soát, rồi bổ sung mock SOAP envelope chứa detail; chỉ lúc ấy mới kết luận full client mapping đã được bảo vệ.

**Không so reason strings** như `contains("not found")` vì wording có thể thay đổi, đa ngôn ngữ, hoặc khác trên sandbox/production.

## 13. XML security và sự khác biệt giữa test và production

XML là định dạng có nhiều khả năng hơn JSON, bao gồm entity và DTD. Khi parse XML từ đối tác không đáng tin:

- **Chặn DTD/external entities** để giảm nguy cơ XXE, SSRF và đọc file nội bộ. Trong JAXP có `FEATURE_SECURE_PROCESSING` và các cờ tắt external entities/DTD; provider không hỗ trợ phải fail closed.
- **Giới hạn kích thước và độ sâu** tài liệu XML để tránh tốn CPU/RAM; demo giới hạn số ký tự, còn production nên có limit ở HTTP/message level.
- **Bật namespace-aware parsing** để tránh nhầm element có local name giống nhưng thuộc namespace khác.
- **Validate XSD** nếu contract yêu cầu; nhưng XSD cũng có thể import/include tài nguyên, nên phải cấu hình schema resolver/external access an toàn.
- **Không log raw SOAP Envelope** khi có `Authorization`, WS-Security `UsernameToken`, signature, account number hoặc PII. Nếu cần trace, mask secrets, giới hạn retention và quyền đọc logs.
- **Không tự tay làm string interpolation** cho input linh hoạt. Ví dụ client chỉ cho ID dạng `ORD-[0-9]{1,6}` nên an toàn với XML text. Với nhiều field/UTF-8 tự do, dùng JAXB/DOM/StAX writer; test cả escape `&`, `<` và ký tự Unicode.
- **Không bỏ qua SOAP Header** khi contract có mustUnderstand, WS-Addressing, signature hoặc timestamp. Test chỉ payload không chứng minh security headers hợp lệ.

**Cẩn thận với parser của Spring-WS/JAXB:** bảo vệ `OrderXml.parseSecure(...)` chỉ bảo vệ parser **mà code của bạn thực sự gọi**. SOAP library/transport/SAAJ có parser riêng; phải kiểm tra/cấu hình XXE/DTD ở cả tầng tiếp nhận message, schema validator và marshaller/unmarshaller theo documentation/version. Một unit test DOM parser xanh không tự chứng minh toàn bộ stack SOAP production chống XXE.

## 14. Tránh các test SOAP yếu hoặc đánh lừa

### 14.1. Chỉ kiểm tra chuỗi XML chứa “PAID”

```java
assertTrue(xml.contains("PAID"));
```

Không đủ vì `PAID` có thể nằm trong comment, sai element, sai namespace hoặc một message lỗi. Thay bằng test DOM/XPath namespace-aware và root QName cụ thể.

### 14.2. So XML byte-for-byte

Dùng so nguyên string sẽ thất bại khi server đổi prefix hoặc indentation mà XML vẫn tương đương. Với payload contract, ưu tiên `MockWebServiceServer.expect(payload(...))`/XMLUnit hoặc namespace-aware DOM/XPath, đồng thời kiểm tra trường quan trọng. **Không bỏ qua schema type/ordering** nếu đó là hợp đồng.

### 14.3. Chỉ assert HTTP 500 là đủ để xác nhận SOAP Fault

HTTP status chỉ là transport signal. Cần xác nhận Envelope chứa SOAP Fault, QName đúng và fault detail hợp lệ. Một HTTP 500 chứa HTML error page không phải SOAP Fault.

### 14.4. Dùng SOAP 1.1 XPath cho SOAP 1.2

`faultcode/faultstring/detail` khác `Code/Reason/Detail`; namespace cũng khác. Test phải nêu SOAP version rõ ràng.

### 14.5. Trả exception message thẳng ra faultstring

Raw message có thể chứa SQL, token hoặc internal class name; contract nên dùng code/reason public an toàn, log diagnostic chi tiết ở vùng được bảo vệ. Test với sentinel secret có thể chứng minh fault không lộ dữ liệu.

### 14.6. Unit test fault mapper rồi kết luận client transport đã đúng

Mapper test chỉ chứng minh code → domain classification; không chứng minh SOAP header, SOAPAction, SAAJ marshalling, TLS hoặc server thật. Có cả `MockWebServiceServer` tests và transport integration tests khi risk yêu cầu.

### 14.7. MockWebServiceServer có verify nhưng không kiểm tra đủ payload

Nếu chỉ `expect(anything())`, test không xác minh request namespace, element order hoặc giá trị ID. Dùng `payload(expectedSource)` và các XPath/header matchers theo contract.

### 14.8. Quên gọi server.verify()

Mock server expectations chưa được xác minh có thể làm test xanh giả. Sau hành động được kỳ vọng, **luôn gọi `server.verify()`**; khi dùng negative/no-request test, nó cũng xác nhận không còn expectation nào chưa đáp ứng.

### 14.9. Retry SOAP write operation không idempotent

Timeout không nói chắc server đã commit hay chưa. Không retry một mutation SOAP operation chỉ vì mã lỗi tên “Server”, trừ khi có idempotency/compensation policy.

## 15. Lỗi thường gặp và cách sửa

**1. Nhầm namespace với prefix.** Test so `ord:` trong text thay vì URI `urn:example:orders`; chuyển sang QName hoặc NamespaceContext.

**2. Gửi full SOAP Envelope cho API nhận payload.** `WebServiceTemplate.sendSourceAndReceiveToResult` đặt payload vào Body; không tự bọc Envelope lần hai.

**3. Dùng SOAP 1.2 fault structure cho message SOAP 1.1.** Kiểm tra Envelope namespace và parser theo version.

**4. Kiểm tra HTTP status nhưng bỏ qua SOAP Fault body.** SOAP-level failure phải được assert bằng fault code/reason/detail.

**5. Đánh đồng transport exception và SOAP Fault exception.** Network timeout/TLS lỗi có thể không có XML message; xử lý khác `SoapFaultClientException`.

**6. So `faultstring` để xác định ORDER_NOT_FOUND.** Sử dụng business `detail.code` theo schema; reason chỉ để đọc, có thể đổi ngôn ngữ.

**7. Map mọi Client fault thành lỗi người dùng.** Có thể adapter tạo request sai; cần phân loại theo nguồn và detail/validation contract.

**8. Bỏ qua nested `detail`.** Nhiều business codes chỉ nằm trong SOAP fault detail; test standard Client/Server code chưa đủ.

**9. Không dùng `server.verify()` với MockWebServiceServer.** Không chứng minh toàn bộ expectations đã xảy ra.

**10. Không test negative namespace.** Payload trông đúng về local name nhưng namespace sai phải bị từ chối.

**11. Dùng `getElementsByTagNameNS` không giới hạn để chọn field.** Có thể bắt nhầm element con sâu hơn; chỉ định parent/QName chính xác.

**12. Bật parser XML mặc định cho input không đáng tin.** Có nguy cơ XXE/DTD; cấu hình secure JAXP, giới hạn size và test DOCTYPE rejection.

**13. Giới hạn parser chỉ ở tầng business.** SAAJ/XML library còn parser khác; cần bảo vệ toàn stack.

**14. Test SOAP client bằng network thật trong mọi unit test.** Flaky và chậm; dùng MockWebServiceServer cho request/response/fault, integration thật có chọn lọc.

**15. Giả định SOAP Fault luôn có detail.** SOAP Fault có thể không có application detail; mapping cần fallback ổn định.

**16. Giả định Server/Receiver fault luôn retryable.** Retry còn phụ thuộc idempotency, tần suất, backoff, side effects và chính sách đối tác.

**17. Dùng MockMvc để test @Endpoint SOAP.** Với Spring-WS MessageDispatcher, dùng MockWebServiceClient; MockMvc dành cho Spring MVC.

**18. Dùng raw exception message làm JSON/GraphQL/HTTP public error.** Cần sanitize và mapping code ổn định.

## 16. Checklist QA SOAP XML/Fault

**XML contract:**

- SOAP version đang dùng là 1.1 hay 1.2? Namespace Envelope đúng?
- Test đã phân biệt **SOAP Envelope** với **business payload**?
- Root payload QName có namespace URI/local name đúng không?
- Các required elements đúng type, số lần xuất hiện, thứ tự theo XSD?
- Test có fixture đổi prefix vẫn pass nhưng đổi namespace URI thì fail?
- Có kiểm tra XML parser ngăn DOCTYPE/external entity?
- Nếu có schema validation, XSD references và external access có được bảo vệ?

**Fault/error mapping:**

- Có kiểm tra Client/Sender, Server/Receiver, MustUnderstand, VersionMismatch khi liên quan?
- Có tách fault code chuẩn khỏi application `detail.code`?
- Fault thiếu detail hoặc reason thay đổi có mapping fallback hợp lý?
- Có so `QName` đầy đủ thay vì local part đơn độc?
- Có tránh leak raw faultstring, exception/SQL/token ở error public?
- Mapping sang REST/GraphQL có theo contract riêng, không áp HTTP status máy móc?
- Có chính sách retry idempotency rõ ràng?

**Testing boundaries:**

- Test SOAP client có `MockWebServiceServer`, request payload matcher, fault fixtures và `server.verify()`?
- Test SOAP endpoint có `MockWebServiceClient` với endpoint/resolver thật được nạp?
- Nếu HTTP headers/SOAPAction/WS-Security/TLS thuộc contract, đã có test transport phù hợp?
- Mock/fixture có phản ánh đúng WSDL/XSD version đang triển khai không?
- Có giữ state độc lập, không dùng thông tin người dùng/token thật trong test?
- Test xanh chỉ được dùng để kết luận về **boundary thực sự chạy**?

**Kết luận:** test SOAP đáng tin phải kiểm tra **XML payload theo QName/XSD**, phân biệt **SOAP Fault, HTTP/transport failure và business detail**, và ánh xạ chúng sang các lỗi ứng dụng **ổn định, an toàn, đúng retry policy**. Dùng JAXP/XML tests cho parser, `MockWebServiceServer` cho SOAP client, `MockWebServiceClient` cho endpoint, và HTTP integration tests có chọn lọc cho transport/security. Không bỏ qua version, namespaces, fault detail hay XXE chỉ để các assertion dễ xanh.

## 17. Tài liệu tham khảo

- [Spring Web Services Reference — Testing Client/Server](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): cách dùng `MockWebServiceServer`, `MockWebServiceClient`, SOAP Fault và payload matchers.
- [Spring-WS — WebServiceTemplate API](https://docs.spring.io/spring-ws/docs/4.0.11/api/org/springframework/ws/client/core/WebServiceTemplate.html): `sendSourceAndReceiveToResult` và fault handling.
- [Spring-WS — SoapFaultClientException API](https://docs.spring.io/spring-ws/docs/4.0.9/api/org/springframework/ws/soap/client/SoapFaultClientException.html): `getFaultCode`/`getFaultStringOrReason`/`getSoapFault`.
- [Spring-WS — MockWebServiceServer API](https://docs.spring.io/spring-ws/docs/4.0.9/api/org/springframework/ws/test/client/MockWebServiceServer.html): khởi tạo mock server, expectations và verify.
- [Spring-WS — ResponseCreators API](https://docs.spring.io/spring-ws/docs/4.0.9/api/org/springframework/ws/test/client/ResponseCreators.html): `withPayload`, `withClientOrSenderFault` và `withServerOrReceiverFault`.
- [Spring Boot 3.5 — Managed Dependencies](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): version quản lý cho Spring-WS và Spring test.
