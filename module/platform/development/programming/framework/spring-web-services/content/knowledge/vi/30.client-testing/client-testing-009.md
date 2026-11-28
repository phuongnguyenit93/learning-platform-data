# Tạo matcher, response tùy chỉnh cho quy tắc hợp đồng riêng

Khi kiểm thử SOAP client bằng Spring-WS MockWebServiceServer, matcher mặc định như payload() hoặc xpath() thường đủ để xác nhận XML cơ bản. Nhưng hợp đồng thực tế có thể đòi hỏi nhiều điều kiện đồng thời: client phải gọi đúng endpoint URI, gửi SOAPAction/WS-Addressing Action, truyền header đối tác đúng QName, ký hoặc mã hóa message theo policy, và serialize decimal/date đúng quy ước. Response cũng có thể cần thay đổi theo request, trả SOAP Fault theo mã lỗi, hoặc mô phỏng response lỗi để kiểm tra retry và fallback.

Spring-WS cho phép mở rộng test bằng hai strategy interface:

- **RequestMatcher**: kiểm tra request mà WebServiceTemplate thực sự gửi. Test xác nhận URI, SOAP message, payload, header và các quy tắc liên quan. Nếu điều kiện không đạt, matcher ném AssertionError.
- **ResponseCreator**: tạo response cho WebServiceTemplate tiêu thụ sau khi request được matcher chấp nhận. Creator tạo SOAP Body theo input, thêm SOAP Header, tạo Fault hoặc mô phỏng response đặc biệt.

Bài thuộc chương **Kiểm thử máy khách** của module **SPRING_WEB_SERVICES**: phát triển SOAP contract-first với XSD/WSDL, JAXB/OXM, endpoint và client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích doanh nghiệp. Trọng tâm là tạo **matcher và response tùy chỉnh cho quy tắc hợp đồng riêng**, giữ test sát message thật nhưng cô lập network và dịch vụ bên ngoài.

## 1. Vị trí của MockWebServiceServer trong kiểm thử client

Một client Spring-WS thường gọi WebServiceTemplate để marshal request, gửi SOAP message và unmarshal response. Trong integration test client, MockWebServiceServer thay message sender bằng mock sender theo expectation:

~~~mermaid
sequenceDiagram
    participant T as Test
    participant C as SOAP client
    participant W as WebServiceTemplate
    participant M as MockWebServiceServer
    T->>M: expect(custom RequestMatcher)
    T->>M: andRespond(custom ResponseCreator)
    T->>C: call client operation
    C->>W: marshalSendAndReceive(request)
    W->>M: SOAP request + URI
    M->>M: execute RequestMatcher
    M->>M: execute ResponseCreator
    M-->>W: mock SOAP response
    W->>W: unmarshal response / resolve Fault
    W-->>C: DTO or exception
    C-->>T: result
    T->>M: verify expectations
~~~

Mock server xác minh XML/headers mà client tạo ra mà không mở HTTP connection thật. Theo Spring-WS Reference 4.1.4, flow chuẩn là tạo server từ WebServiceTemplate, đăng ký RequestMatcher qua expect(...), cung cấp ResponseCreator qua andRespond(...), gọi client như bình thường và cuối cùng gọi verify(). [Spring-WS 4.1.4 — Client-side Testing](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)

### 1.1. Khi nào cần custom strategy?

| Nhu cầu kiểm thử | Matcher/creator mặc định | Khi cần custom |
| --- | --- | --- |
| So request XML | payload(...) | Nhiều field phụ thuộc nhau hoặc canonicalize đặc thù |
| Kiểm XSD | validPayload(...) | Rule ngoài XSD như decimal scale/cross-field invariant |
| Kiểm XPath | xpath(...) | Tổng hợp nhiều node và báo lỗi theo domain |
| Kiểm SOAP Header | soapHeader(...) | QName/value/cardinality/multiple headers/WS-A metadata |
| Kiểm URI | connectionTo(...) | URI cần so host/path/query theo policy |
| Response payload tĩnh | withPayload(...) | Body/header phụ thuộc request |
| SOAP Fault chuẩn | withClientOrSenderFault(...) | Fault detail/code phụ thuộc request |
| Transport error/exception | withError(message), withException(exception) | Điều kiện và kiểu lỗi riêng theo scenario |

Đừng viết custom matcher chỉ để thay một matcher có sẵn. Giữ test đơn giản khi RequestMatchers/ResponseCreators đã diễn đạt được contract.

## 2. Hai interface và contract của chúng

### 2.1. RequestMatcher

Interface nằm trong package:

~~~java
org.springframework.ws.test.client.RequestMatcher
~~~

Contract của API:

~~~java
public interface RequestMatcher {
    void match(URI uri, WebServiceMessage request)
            throws IOException, AssertionError;
}
~~~

uri là URI mà WebServiceTemplate sử dụng cho exchange; request là message đã được tạo để gửi. Matcher nên:

- Chỉ đọc và xác nhận request.
- Ném AssertionError với thông tin chẩn đoán nếu expectation sai.
- Không thay đổi request để “sửa” client; việc mutate có thể che lỗi serialization.
- Không gọi dịch vụ thật, mở network hay ghi dữ liệu nghiệp vụ.
- Kiểm tra URI/headers theo semantics hợp đồng, không dựa vào thứ tự XML attributes hoặc prefix.

MockWebServiceServer.expect(RequestMatcher) nhận matcher; có thể nối matcher bằng andExpect(...) trước khi cấu hình response. [RequestMatcher API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/RequestMatcher.html)

### 2.2. ResponseCreator

Interface nằm trong package:

~~~java
org.springframework.ws.test.client.ResponseCreator
~~~

Contract của API:

~~~java
public interface ResponseCreator {
    WebServiceMessage createResponse(
            URI uri,
            WebServiceMessage request,
            WebServiceMessageFactory messageFactory)
            throws IOException;
}
~~~

Creator nhận URI, request đã được xác minh và message factory tương ứng. Nó trả về WebServiceMessage cho mock sender. Dùng messageFactory để tạo message tương thích SOAP version/factory của test; đừng tự tạo implementation WebServiceMessage không đúng factory.

ResponseCreator có thể đọc request để phản hồi động, nhưng không nên dùng request làm bằng chứng đã được xác thực bởi server thật, truy cập database/service bên ngoài làm test mất deterministic, hoặc tái sử dụng cùng mutable message cho nhiều lần gọi.

Đây là strategy interfaces độc lập; Spring-WS cung cấp factory methods trong RequestMatchers và ResponseCreators cho phần lớn ca thông dụng. [Spring-WS Reference 4.1.4 — RequestMatcher and ResponseCreator](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)

## 3. Tạo custom RequestMatcher kiểm tra URI và SOAP payload

Ví dụ hợp đồng Orders yêu cầu:

- Gọi endpoint https://partner.example.test/soap/orders.
- Payload root có QName {urn:example:orders:v1}GetOrderRequest.
- orderId không rỗng và đúng format.
- Client gửi SOAPAction theo operation.

Ta tạo matcher gom các điều kiện thành một rule có tên rõ:

~~~java
import java.io.IOException;
import java.net.URI;
import javax.xml.transform.Source;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMResult;
import javax.xml.transform.Transformer;

import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.test.client.RequestMatcher;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

public final class GetOrderRequestMatcher implements RequestMatcher {
    private static final String EXPECTED_URI =
            "https://partner.example.test/soap/orders";
    private static final String NS = "urn:example:orders:v1";
    private static final String EXPECTED_ACTION =
            "urn:example:orders:action:GetOrder";

    @Override
    public void match(URI uri, WebServiceMessage request)
            throws IOException, AssertionError {
        assertEquals(EXPECTED_URI, uri.toString(), "Endpoint URI");

        if (!(request instanceof SoapMessage soap)) {
            throw new AssertionError("Expected SOAP message");
        }
        assertEquals(EXPECTED_ACTION, soap.getSoapAction(), "SOAPAction");

        Document document = toDocument(request.getPayloadSource());
        Element root = document.getDocumentElement();
        assertQName(root, NS, "GetOrderRequest");

        String orderId = childText(root, NS, "orderId");
        if (orderId == null || !orderId.matches("ORD-[0-9]{6}")) {
            throw new AssertionError(
                    "orderId must match ORD- followed by six digits");
        }
    }

    private static Document toDocument(Source source) {
        try {
            DOMResult result = new DOMResult();
            Transformer transformer =
                    TransformerFactory.newInstance().newTransformer();
            transformer.transform(source, result);
            Node node = result.getNode();
            if (node instanceof Document document) {
                return document;
            }
            if (node instanceof Element element) {
                Document document = element.getOwnerDocument();
                if (document != null) {
                    return document;
                }
            }
            throw new AssertionError("Payload did not produce a DOM document");
        } catch (TransformerException ex) {
            throw new AssertionError("Cannot read SOAP payload", ex);
        }
    }

    private static void assertQName(
            Element element, String namespace, String localName) {
        if (!namespace.equals(element.getNamespaceURI())
                || !localName.equals(element.getLocalName())) {
            throw new AssertionError(
                    "Unexpected payload root QName: {"
                            + element.getNamespaceURI() + "}"
                            + element.getLocalName());
        }
    }

    private static String childText(
            Element parent, String namespace, String localName) {
        for (Node node = parent.getFirstChild();
             node != null; node = node.getNextSibling()) {
            if (node instanceof Element element
                    && namespace.equals(element.getNamespaceURI())
                    && localName.equals(element.getLocalName())) {
                return element.getTextContent().trim();
            }
        }
        return null;
    }

    private static void assertEquals(
            String expected, String actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected <" + expected + "> but was <"
                            + actual + ">");
        }
    }
}
~~~

Đây là implementation minh họa cho test JDK có DOM support; import/exception có thể được tinh chỉnh theo Java/JAXP version dự án. Với payload lớn, nên dùng SAX/StAX hoặc XPath thay vì materialize cả DOM. Matcher chỉ kiểm SOAPAction được expose qua SoapMessage; với SOAP 1.2, action có thể được biểu diễn qua Content-Type parameter theo binding/provider, do đó phải dùng matcher phù hợp message factory/version thay vì giả định mọi version đều đọc giống nhau.

### 3.1. Lưu ý về DOM và QName

Không viết:

~~~java
assertEquals("GetOrderRequest", root.getNodeName());
~~~

getNodeName() phụ thuộc prefix như ord:GetOrderRequest. Hãy so getNamespaceURI() và getLocalName(). Prefix có thể thay đổi mà QName không đổi.

### 3.2. Dùng matcher kết hợp matcher mặc định

~~~java
mockServer.expect(connectionTo(
                "https://partner.example.test/soap/orders"))
        .andExpect(new GetOrderRequestMatcher())
        .andExpect(validPayload(orderRequestSchema))
        .andRespond(withPayload(orderResponsePayload));
~~~

Điều này chia trách nhiệm: connectionTo kiểm URI, custom matcher kiểm rule đặc thù, validPayload kiểm XSD, còn response creator tạo payload. Không lặp lại cùng assertion trong nhiều nơi nếu không cần.

## 4. Custom matcher kiểm SOAP Header và WS-Addressing

Nhiều partner contract quy định header bắt buộc:

~~~xml
<soap:Header>
    <ctx:PartnerContext xmlns:ctx="urn:example:context:v1">
        <ctx:partnerId>PARTNER-42</ctx:partnerId>
        <ctx:correlationId>corr-9001</ctx:correlationId>
    </ctx:PartnerContext>
    <wsa:Action xmlns:wsa="http://www.w3.org/2005/08/addressing">
        urn:example:orders:action:GetOrder
    </wsa:Action>
</soap:Header>
~~~

Matcher có thể cast message sang SoapMessage, duyệt SoapHeader và xác nhận QName header, cardinality và value:

~~~java
import java.util.Iterator;
import javax.xml.namespace.QName;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

private static SoapHeaderElement requireSingleHeader(
        SoapMessage message, QName expectedName) {
    SoapHeader header = message.getSoapHeader();
    Iterator<SoapHeaderElement> elements =
            header.examineAllHeaderElements();

    SoapHeaderElement found = null;
    while (elements.hasNext()) {
        SoapHeaderElement candidate = elements.next();
        if (expectedName.equals(candidate.getName())) {
            if (found != null) {
                throw new AssertionError(
                        "Duplicate SOAP header " + expectedName);
            }
            found = candidate;
        }
    }
    if (found == null) {
        throw new AssertionError("Missing SOAP header " + expectedName);
    }
    return found;
}
~~~

Sau đó lấy payload của header theo SoapHeaderElement/Source API tương ứng implementation đang dùng, parse namespace-aware và assert partnerId. Kiểm tra duplicate header quan trọng khi contract yêu cầu đúng một phần tử; chỉ gọi “header exists” chưa kiểm cardinality.

### 4.1. Kiểm WS-Addressing

ActionCallback của Spring-WS có thể tạo WS-Addressing Action/To và các header liên quan theo phiên bản. Custom matcher có thể xác minh:

- Action URI đúng operation.
- To đúng endpoint logic nếu contract yêu cầu.
- MessageID có định dạng hợp lệ khi client phải gửi.
- ReplyTo/FaultTo đúng policy, không trỏ đến URI ngoài allowlist.
- Header namespace/version là WS-Addressing 1.0 hoặc draft partner thống nhất.

Không gắn điều kiện MessageID phải bằng một UUID cố định nếu production client sinh ID mới mỗi lần gọi. Thay vào đó kiểm định dạng, uniqueness trong test hoặc quan hệ giữa request và response RelatesTo.

### 4.2. Kiểm SOAP Header không đồng nghĩa kiểm WS-Security

Việc thấy wsse:Security chỉ xác nhận header tồn tại. Nó không chứng minh chữ ký hợp lệ, certificate trusted, Timestamp chưa hết hạn hay Body thực sự được ký. Đối với test outbound signing, dùng WSS4J/keystore fixture và xác minh chữ ký bằng thành phần crypto phù hợp; không thay bằng matcher chỉ kiểm tên element.

## 5. Tạo custom ResponseCreator phụ thuộc request

Một số contract trả response tùy theo request:

- GetOrderStatus trả status theo order ID.
- Response mang correlation ID tương ứng.
- Phản hồi versioned namespace theo operation/request.
- SOAP Header chứa partner reference.

Ví dụ custom creator tạo response Body dựa trên order ID:

~~~java
import java.io.IOException;
import java.net.URI;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.WebServiceMessageFactory;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.test.client.ResponseCreator;
import org.springframework.xml.transform.StringSource;

public final class OrderStatusResponseCreator implements ResponseCreator {
    @Override
    public WebServiceMessage createResponse(
            URI uri,
            WebServiceMessage request,
            WebServiceMessageFactory messageFactory)
            throws IOException {
        String orderId = extractOrderId(request);
        String status = orderId.endsWith("000001")
                ? "SHIPPED"
                : "PROCESSING";

        String responseXml = """
            <ord:GetOrderStatusResponse
                xmlns:ord="urn:example:orders:v1">
                <ord:orderId>%s</ord:orderId>
                <ord:status>%s</ord:status>
            </ord:GetOrderStatusResponse>
            """.formatted(escapeXml(orderId), status);

        WebServiceMessage response = messageFactory.createWebServiceMessage();
        try {
            Transformer transformer =
                    TransformerFactory.newInstance().newTransformer();
            transformer.transform(
                    new StringSource(responseXml),
                    response.getPayloadResult());
        } catch (TransformerException ex) {
            throw new IOException("Cannot create SOAP response", ex);
        }

        if (response instanceof SoapMessage soapResponse) {
            soapResponse.setSoapAction(
                    "urn:example:orders:action:GetOrderStatusResponse");
        }
        return response;
    }

    private static String extractOrderId(WebServiceMessage request)
            throws IOException {
        // Parse {urn:example:orders:v1}orderId bằng XML API
        // namespace-aware và kiểm tra định dạng trước khi trả về.
        throw new UnsupportedOperationException(
                "Implement namespace-aware extraction for this contract");
    }

    private static String escapeXml(String value) {
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&apos;");
    }
}
~~~

Đây là khung minh họa: extractOrderId cố ý để ứng dụng triển khai bằng parser namespace-aware và kiểm tra định dạng. Ví dụ escapeXml cho phép chèn text đã escape vào template; khi mapping phức tạp hoặc có mixed content, ưu tiên tạo DOM/StAX node để tránh tự serialize XML.

### 5.1. Tránh custom creator khi response cố định

Nếu response cố định, withPayload(...) đơn giản và dễ đọc hơn. Chỉ dùng creator phụ thuộc request khi cần test một rule hợp đồng cụ thể, chẳng hạn response correlation hoặc branch theo operation input.

## 6. ResponseCreator thêm SOAP Header

Một client có thể cần nhận header phản hồi:

~~~xml
<soap:Header>
    <ctx:Correlation xmlns:ctx="urn:example:context:v1">
        corr-9001
    </ctx:Correlation>
</soap:Header>
~~~

Với SOAP implementation hỗ trợ SoapMessage, creator có thể tạo message qua factory, ghi payload vào getPayloadResult() và thêm header bằng getSoapHeader().addHeaderElement(QName):

~~~java
import javax.xml.namespace.QName;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

QName correlationName =
        new QName("urn:example:context:v1", "Correlation", "ctx");

SoapMessage soapResponse = (SoapMessage)
        messageFactory.createWebServiceMessage();

SoapHeaderElement correlation =
        soapResponse.getSoapHeader().addHeaderElement(correlationName);
correlation.setText("corr-9001");
~~~

Đây là phần thân creator; cần đặt trong implementation ResponseCreator và viết payload response trước khi trả message. Nếu response có WS-Addressing headers, hãy tạo bằng API/header callback phù hợp và tuân thủ namespace/spec version; không tự tạo một header gần giống chuẩn.

## 7. Tạo SOAP Fault theo quy tắc riêng

Client cần xử lý business fault theo contract, ví dụ:

- SOAP Sender/Client Fault cho request sai.
- SOAP Receiver/Server Fault cho lỗi xử lý tạm thời.
- Fault detail có errorCode, message và correlationId.
- Fault code/reason khác nhau theo SOAP 1.1 và SOAP 1.2.

Spring-WS ResponseCreators cung cấp creators chuẩn withMustUnderstandFault, withClientOrSenderFault, withServerOrReceiverFault và withVersionMismatchFault. Dùng chúng khi test chỉ cần loại Fault chuẩn. [Spring-WS Reference — ResponseCreators](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)

Khi cần Fault detail riêng, tạo một SoapMessage và cấu hình SoapBody tương ứng message factory:

~~~java
import java.io.IOException;
import java.net.URI;
import java.util.Locale;
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.WebServiceMessageFactory;
import org.springframework.ws.soap.SoapBody;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.test.client.ResponseCreator;

public final class PartnerRejectedFaultCreator implements ResponseCreator {
    @Override
    public WebServiceMessage createResponse(
            URI uri,
            WebServiceMessage request,
            WebServiceMessageFactory messageFactory)
            throws IOException {
        WebServiceMessage message = messageFactory.createWebServiceMessage();
        if (!(message instanceof SoapMessage response)) {
            throw new IOException("Expected SOAP message factory");
        }

        SoapBody body = response.getSoapBody();
        body.addClientOrSenderFault(
                "Partner request rejected by contract policy",
                Locale.ENGLISH);
        return response;
    }
}
~~~

API Fault body phân biệt SOAP 1.1/1.2 thông qua message factory. Để test Detail tùy chỉnh, lấy SoapFault từ body, thêm detail element có QName đúng rồi ghi nội dung bằng XML API. Creator ở trên tạo Fault reason cơ bản; nó **chưa** tạo structured detail.

### 7.1. Kiểm Fault ở client

| Điều cần xác minh | Vì sao |
| --- | --- |
| SOAP version/Fault code | Client có thể phân loại Sender/Receiver |
| Fault reason | Hỗ trợ chẩn đoán đã được lọc |
| Detail QName và error code | Ánh xạ sang exception/domain error |
| Correlation ID | Liên kết log và request |
| Retry decision | Sender/client fault thường không retry nguyên xi; receiver có thể retry theo policy |
| Không lộ nội bộ | Stack trace/SQL/secret không được trả caller |

Không retry mọi SOAP Fault. Quy tắc retry theo fault code, detail/error code và idempotency của operation.

## 8. Matcher kiểm quy tắc hợp đồng ngoài XSD

XSD có thể xác nhận type, occurrence, pattern và enum. Nhưng một số điều kiện nằm ở mức message/business contract:

- Hai trường phải khớp quan hệ, ví dụ startDate <= endDate.
- currency phải đúng currency được partner đăng ký.
- Nếu deliveryMode=EXPRESS thì signature hoặc insurance reference phải có.
- requestId phải nhất quán với header correlation.
- Không gửi trường PII vào partner endpoint cụ thể.

Custom matcher là nơi tốt để xác nhận client **đã serialize đúng rule**. Domain rule phía server vẫn phải được validate ở production server; test client không thay thế validation server.

### 8.1. Kiểm decimal lexical/precision

Giả sử contract yêu cầu số tiền có tối đa hai chữ số thập phân:

~~~text
Allowed: 12.34
Allowed: 0.10
Rejected by partner contract: 12.345
Policy question: whether 12.3400 is equivalent to 12.34
~~~

Không tự giả định scale lexical phải giữ nguyên chỉ vì hai giá trị numerically equal. Contract cần nói rõ scale là rule nghiệp vụ hay chỉ là formatting.

### 8.2. Kiểm timestamp và timezone

Với xs:dateTime, matcher có thể parse thành OffsetDateTime/XMLGregorianCalendar theo contract rồi assert offset/range. Không so chuỗi nếu contract chỉ định instant; cũng không normalize timezone nếu partner yêu cầu giữ local offset.

## 9. Custom matcher sử dụng XPath thay vì DOM thủ công

Nếu điều kiện là các XPath ngắn, dùng RequestMatchers.xpath(...) chuẩn. Custom matcher hữu ích khi cần phối hợp nhiều XPath, chuyển node values thành object hoặc tạo error message có ngữ cảnh.

Ví dụ conceptual matcher:

~~~java
public final class PaymentRequestMatcher implements RequestMatcher {
    @Override
    public void match(URI uri, WebServiceMessage request) {
        // 1. Kiểm URI.
        // 2. Dùng XPath namespace-aware để đọc:
        //    paymentId, amount, currency, merchantId.
        // 3. Assert amount > 0.
        // 4. Assert currency nằm trong allowlist fixture.
        // 5. Assert header correlation khớp payload requestId.
    }
}
~~~

Đây là pseudocode mô tả rule. Khi hiện thực, cấu hình XPathExpression một lần với namespace mappings rõ, tránh tạo XPath compiler mới cho mọi field nếu matcher dùng nhiều. Không viết XPath không namespace rồi chọn node theo local name khi nhiều vocabulary có thể trùng tên.

## 10. Kết hợp matcher với XSD, URI và SOAP Header

Một expectation tốt thường tách điều kiện:

~~~java
mockServer.expect(connectionTo(endpoint))
    .andExpect(validPayload(requestSchema))
    .andExpect(soapHeader(new QName(
            "urn:example:context:v1", "PartnerContext")))
    .andExpect(new GetOrderRequestMatcher())
    .andRespond(new OrderStatusResponseCreator());
~~~

Thứ tự matcher giúp báo lỗi rõ: URI, schema, header cơ bản, rồi rule business riêng. Tất cả cùng kiểm **một request expectation**; không biến các matcher thành nhiều expectation nếu client chỉ gửi một SOAP request.

## 11. ResponseCreator cho các tình huống đặc biệt

ResponseCreators dựng sẵn bao gồm:

| Creator | Mô phỏng |
| --- | --- |
| withPayload(Source/Resource) | SOAP response bình thường |
| withError(message) | Lỗi response connection |
| withException(IOException) | Exception khi đọc response |
| withMustUnderstandFault(...) | MustUnderstand Fault |
| withClientOrSenderFault(...) | Sender/Client Fault |
| withServerOrReceiverFault(...) | Receiver/Server Fault |
| withVersionMismatchFault(...) | VersionMismatch Fault |

Dùng response phù hợp với failure boundary:

- HTTP/transport error để test network exception handling.
- SOAP Fault để test protocol/business fault resolution.
- Payload sai XSD nhưng SOAP exchange hoàn tất để test response unmarshalling/validation.
- Payload hợp lệ nhưng giá trị business bất thường để test client-side mapping/validation.

Không dùng SOAP Fault để thay lỗi TLS handshake; TLS thất bại trước SOAP response. MockWebServiceServer không tạo socket/TLS nên certificate/hostname phải test bằng transport integration test riêng.

## 12. Kiểm soát expectation order và verify

MockWebServiceServer cho phép đăng ký nhiều expectation. Mỗi test nên:

1. Tạo mock server mới cho WebServiceTemplate tương ứng.
2. Đăng ký đúng số request dự kiến.
3. Nêu rõ request nào có matcher và response nào được tạo.
4. Gọi client operation.
5. Assert business result/exception.
6. Gọi verify() để bảo đảm tất cả expectation được dùng.

Nếu client retry, đăng ký số expectation phù hợp hoặc thiết kế expectation sequence cụ thể. Không để anything() bắt mọi request rồi vô tình che một lần gọi sai endpoint hoặc gửi thừa. Khi test retry, assert chính xác số attempt, URI, payload/idempotency key và thời điểm/backoff nếu client policy expose được.

### 12.1. Reset và isolation giữa các test

Tạo mock server độc lập trong mỗi test/setup lifecycle. Không dùng chung mutable mock server giữa tests chạy song song. Cần xác định cách WebServiceTemplate được bind mock sender; nếu hai test cùng mutate một template singleton trong context, có thể va chạm. Tách template bean/test context hoặc serialize test theo cấu hình.

## 13. Kiểm thử client security mà matcher/creator có thể và không thể làm

Custom matcher có thể kiểm:

- SOAP Header chứa wsse:Security.
- Presence của wsu:Timestamp, ds:Signature, xenc:EncryptedData.
- QName/algorithm attributes theo policy.
- URI/Action/To và correlation metadata.

Nhưng chỉ kiểm sự hiện diện không chứng minh:

- Signature cryptographically valid.
- Chứng chỉ thuộc trust chain được chấp nhận.
- Signed parts thực sự cover Body/headers quan trọng.
- Timestamp còn hợp lệ hoặc replay bị chặn.
- Encryption có thể giải mã bằng private key đối tác.

Để test bảo mật outbound, dùng test keystore/certificate, verify signature bằng WSS4J/crypto độc lập và giải mã response nếu cần. Không dùng production private key/secret. Mock server chỉ kiểm request message được tạo; partner validation/interoperability vẫn cần test thực với security stack phù hợp.

## 14. Ví dụ client test ở message layer

Giả sử OrderClient dùng WebServiceTemplate và trả OrderStatus. Test có thể như sau:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import static org.springframework.ws.test.client.RequestMatchers.connectionTo;
import static org.springframework.ws.test.client.RequestMatchers.validPayload;

import org.junit.jupiter.api.Test;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

class OrderClientTest {
    private final WebServiceTemplate template = createTemplate();
    private final OrderClient client = new OrderClient(template);

    @Test
    void sendsContractCompliantRequestAndReadsResponse() throws Exception {
        MockWebServiceServer server =
                MockWebServiceServer.createServer(template);

        StringSource response = new StringSource("""
            <ord:GetOrderStatusResponse
                xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-000001</ord:orderId>
                <ord:status>SHIPPED</ord:status>
            </ord:GetOrderStatusResponse>
            """);

        server.expect(connectionTo(
                        "https://partner.example.test/soap/orders"))
                .andExpect(new GetOrderRequestMatcher())
                .andExpect(validPayload(orderRequestSchema()))
                .andRespond(withPayload(response));

        OrderStatus actual = client.getStatus("ORD-000001");

        assertEquals("SHIPPED", actual.status());
        server.verify();
    }
}
~~~

Đây là khung ví dụ: createTemplate(), orderRequestSchema(), OrderClient và DTO là thành phần project cung cấp. Matcher phải khớp cấu trúc request thực tế của client; đừng copy GetOrderRequestMatcher nếu operation/payload khác.

## 15. Test failure và exception mapping

Ví dụ kiểm client xử lý SOAP Receiver Fault:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.ws.test.client.RequestMatchers.anything;
import static org.springframework.ws.test.client.ResponseCreators.withServerOrReceiverFault;

@Test
void mapsReceiverFaultToRetryableServiceException() {
    MockWebServiceServer server =
            MockWebServiceServer.createServer(template);

    server.expect(anything())
            .andRespond(withServerOrReceiverFault(
                    "Temporary order service failure",
                    Locale.ENGLISH));

    assertThrows(
            RetryablePartnerException.class,
            () -> client.getStatus("ORD-000001"));
    server.verify();
}
~~~

Test trên chỉ đúng khi client thực sự map receiver Fault thành RetryablePartnerException. Đây là policy do application viết, không phải hành vi mặc định mà Spring-WS tự bảo đảm. Nên có test riêng Sender Fault không retry và Receiver Fault chỉ retry khi operation/idempotency cho phép.

## 16. Những lỗi phổ biến khi viết custom matcher/creator

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| So nodeName thay QName | Phụ thuộc prefix | So namespace URI + local name |
| Chỉ kiểm payload, bỏ URI | Client có thể gọi nhầm partner endpoint | Thêm connectionTo hoặc URI assertion |
| Chỉ kiểm wsse:Security | Không xác minh signature | Crypto verification với test keys |
| Matcher sửa request khi fail | Che lỗi serialization thật | Matcher chỉ assert, không mutate |
| Creator hardcode mọi response | Không test response/request correlation | Creator động khi cần kiểm quan hệ |
| Creator dùng string concat XML | Nguy cơ XML injection/escaping bug | DOM/StAX/Transformer và text nodes |
| Dùng anything() cho toàn suite | Expectation quá yếu | Matcher cụ thể theo operation |
| Không gọi verify() | Có thể bỏ sót request không được gửi | Verify sau client invocation |
| Mock cùng template ở nhiều test song song | Request expectation có thể bị lẫn | Template/mock server riêng hoặc isolation |
| Dùng mock server để test TLS | Không đi qua socket/TLS | Embedded HTTPS/contract environment |
| Fault matcher quá rộng | Không xác minh code/detail | Kiểm fault code, QName và domain mapping |
| So string XML tuyệt đối | False negative do prefix/whitespace | XML-aware assertions |

## 17. Ma trận test cho custom matcher và response creator

| ID | Request condition | Response creator | Điều cần assert |
| --- | --- | --- | --- |
| CUS-01 | URI đúng, QName đúng | Payload chuẩn | Client unmarshal thành công |
| CUS-02 | URI sai | Matcher fail | URI diagnostic rõ |
| CUS-03 | Namespace sai | Matcher fail | QName failure |
| CUS-04 | SOAPAction sai | Matcher fail | Action đúng operation |
| CUS-05 | Thiếu partner header | Matcher fail | Header mandatory |
| CUS-06 | Duplicate partner header | Matcher fail | Cardinality đúng |
| CUS-07 | Correlation không khớp payload | Matcher fail | Header/body invariant |
| CUS-08 | Payload vi phạm XSD | Matcher fail | Schema validation |
| CUS-09 | Payload hợp XSD nhưng sai business rule | Matcher fail | Cross-field invariant |
| CUS-10 | Request A | Creator trả response A | Correlation đúng |
| CUS-11 | Request B | Creator trả response B | Không dùng response stale |
| CUS-12 | Operation cần business fault | Sender Fault creator | Client error mapping |
| CUS-13 | Operation lỗi tạm thời | Receiver Fault creator | Retry policy |
| CUS-14 | Transport connection error | withError(message) | Network error branch |
| CUS-15 | Response read exception | withException(IOException) | Exception branch |
| CUS-16 | Signed outbound request | Matcher + crypto verifier | Signature và signed parts |
| CUS-17 | Retry | N expectation tương ứng | Attempt count/key/URI |
| CUS-18 | Extra unexpected call | Không có expectation phù hợp | Test fail, không accept silently |

## 18. Bài tập thực hành

1. Viết RequestMatcher kiểm URI, QName và SOAPAction cho GetOrderRequest.
2. Mở rộng matcher kiểm PartnerContext đúng QName, đúng một lần xuất hiện và partnerId đúng.
3. Kiểm correlationId trong SOAP Header phải bằng requestId ở Body.
4. Kiểm XPath business rule: amount dương và currency nằm trong allowlist fixture.
5. Viết ResponseCreator tạo status response theo orderId của request.
6. Viết response creator thêm SOAP Header correlation.
7. Tạo Sender và Receiver Fault, kiểm ứng dụng map sang hai exception/domain category khác nhau.
8. Mô phỏng transport error và response read exception; kiểm branch xử lý riêng.
9. Kết hợp custom matcher với validPayload và connectionTo; giữ một expectation cho một request.
10. Dùng test keystore ký request, kiểm signature thật thay vì chỉ tìm ds:Signature.
11. Tạo retry test với cùng idempotency key; kiểm số request và response mỗi attempt.
12. Chạy test song song để chứng minh mock server/template không chia sẻ expectation state.

## 19. Checklist review

| Nhóm | Điều kiện đạt |
| --- | --- |
| **Strategy contract** | Matcher nhận URI + WebServiceMessage; creator nhận URI/request/message factory |
| **URI** | Scheme/host/path/port/query được kiểm theo đúng semantics |
| **XML** | QName/namespace/cardinality/value kiểm bằng XML API |
| **SOAP headers** | Partner/custom/WS-A headers có QName và policy rõ |
| **SOAPAction** | Test theo SOAP 1.1/1.2 binding thực tế |
| **Schema** | validPayload/XSD và custom business invariants được phân biệt |
| **Response** | Static payload dùng creator mặc định; dynamic response mới custom |
| **Fault** | Code/reason/detail và exception mapping được xác minh |
| **Transport failures** | Error và exception được test tách khỏi SOAP Fault |
| **Security** | Signature/certificate được kiểm bằng crypto test, không chỉ header presence |
| **Isolation** | Mock server/template không dùng chung mutable expectation state |
| **Verify** | Mọi expectation được verify; unexpected extra calls thất bại |
| **Diagnostics** | Assertion message nêu operation/field/expected và actual đã lọc |
| **Boundary** | Embedded HTTP/TLS/partner stack test dùng khi cần transport thật |

## 20. Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4 — Client-side Testing](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): MockWebServiceServer, RequestMatcher, RequestCreators, ResponseCreator và ResponseCreators.
- [RequestMatcher API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/RequestMatcher.html): contract match URI và WebServiceMessage, throws IOException/AssertionError.
- [ResponseCreator API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/ResponseCreator.html): tạo WebServiceMessage từ URI, request và WebServiceMessageFactory.
- [RequestMatchers API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/RequestMatchers.html): payload, validPayload, xpath, soapHeader, soapEnvelope, connectionTo.
- [ResponseCreators API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/ResponseCreators.html): payload, error, exception và SOAP Fault creators.
- [ResponseActions API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/ResponseActions.html): nối request expectations và cấu hình response creator.

**Kết luận:** Custom RequestMatcher và ResponseCreator là hai extension point để mô tả chính xác quy tắc hợp đồng mà matcher/creator mặc định chưa đủ diễn đạt. Matcher xác minh URI và message client thực sự gửi; creator tạo SOAP response/Fault phù hợp với request và message factory. Khi test dùng QName/namespace-aware XML, kiểm header/action/correlation, validate XSD, tạo response động có chủ ý và phân biệt SOAP Fault với transport error, bộ client tests sẽ bắt được lỗi serialization/interoperability sớm mà không cần gọi dịch vụ đối tác thật. MockWebServiceServer chỉ thay transport ở message layer; TLS, certificate trust và tương thích stack thực cần được kiểm ở integration environment riêng.
