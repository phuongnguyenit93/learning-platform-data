# RequestMatcher, RequestMatchers và kiểm tra thông điệp được gửi

## 1. Vì sao phải kiểm tra SOAP request ở phía client?

Trong module **SPRING_WEB_SERVICES**, dịch vụ SOAP được phát triển theo hướng **contract-first**: XSD định nghĩa cấu trúc payload, WSDL mô tả operation và binding, JAXB/OXM ánh xạ object với XML, còn `WebServiceTemplate` tạo và gửi SOAP message tới đối tác. Một client có thể vẫn nhận được response hợp lệ dù request gửi đi đã sai hợp đồng: sai endpoint URI, QName, namespace, SOAP Header, action hoặc field nghiệp vụ.

Nếu chỉ kiểm tra object trả về, test có thể bỏ sót lỗi trong phần serialization hoặc cấu hình transport. Ví dụ, JAXB có thể marshal sai namespace; interceptor có thể không thêm WS-Security Header; client có thể gọi nhầm URL; hoặc payload có cấu trúc hợp lệ với Java object nhưng không hợp XSD đối tác yêu cầu.

Spring-WS cung cấp **`MockWebServiceServer`** để kiểm tra chính request mà `WebServiceTemplate` gửi ra. Các expectation dùng:

- **`RequestMatcher`**: strategy nhận URI đích và `WebServiceMessage` request, rồi xác minh request có thỏa điều kiện hay không.
- **`RequestMatchers`**: factory cung cấp matcher dựng sẵn như `anything`, `connectionTo`, `payload`, `validPayload`, `xpath`, `soapHeader` và `soapEnvelope`.
- **`ResponseCreator` / `ResponseCreators`**: tạo response giả sau khi request khớp expectation.
- **`verify()`**: xác nhận các expectation đã khai báo đều được thỏa mãn.

Mục tiêu của bài là kiểm thử **thông điệp client thực sự gửi** ở ranh giới `WebServiceTemplate`, chứ không chỉ kiểm tra method Java đã được gọi.

### Mục tiêu học tập

Sau bài thuộc chương **Kiểm thử máy khách**, bạn có thể:

1. Giải thích vai trò `MockWebServiceServer`, `RequestMatcher`, `RequestMatchers`, `ResponseCreator` và `ResponseActions`.
2. Tạo mock server bằng `WebServiceTemplate`, `WebServiceGatewaySupport` hoặc `ApplicationContext`.
3. Viết expectation theo URI, XML payload, XSD, XPath, SOAP Header và SOAP Envelope.
4. Kết hợp nhiều matcher cho cùng một request bằng `andExpect(...)`.
5. Dựng response thành công, SOAP Fault hoặc transport error bằng `ResponseCreators`.
6. Hiểu vì sao cần gọi `verify()` và cách kiểm tra thiếu/thừa request.
7. Tự viết matcher khi điều kiện cần kiểm tra vượt ngoài matcher có sẵn.
8. Phân biệt `RequestMatcher` phía client với `ResponseMatcher` phía server.
9. Nhận biết giới hạn của mock transport so với kiểm thử HTTP/TLS/proxy và SOAP endpoint thật.

## 2. Kiến trúc kiểm thử client với MockWebServiceServer

### 2.1. Mock server thay thế WebServiceMessageSender

Thông thường `WebServiceTemplate` sử dụng `WebServiceMessageSender` để mở kết nối tới SOAP endpoint. Trong test, `MockWebServiceServer` gắn một mock message sender vào template. Khi client gọi template:

1. Template marshal Java object thành SOAP request message.
2. Template gọi mock sender thay cho sender network thật.
3. Mock server lấy URI và `WebServiceMessage` được gửi ra.
4. `RequestMatcher` xác minh request theo expectation.
5. Nếu expectation đạt, `ResponseCreator` dựng response giả.
6. `WebServiceTemplate` nhận response và tiếp tục unmarshal/trả kết quả cho client.
7. Test gọi `verify()` để đảm bảo các expectation đã được sử dụng.

~~~mermaid
sequenceDiagram
    participant T as JUnit test
    participant C as SOAP client
    participant W as WebServiceTemplate
    participant M as MockWebServiceServer
    participant RM as RequestMatcher
    participant RC as ResponseCreator
    T->>M: createServer(template)
    T->>M: expect(matcher).andRespond(creator)
    T->>C: Gọi operation trên client
    C->>W: marshalSendAndReceive(request)
    W->>M: Gửi URI + SOAP WebServiceMessage
    M->>RM: match(uri, request)
    RM-->>M: Expectation đạt
    M->>RC: createResponse(...)
    RC-->>M: SOAP response giả
    M-->>W: Trả WebServiceMessage response
    W-->>C: Unmarshal response
    C-->>T: Kết quả Java
    T->>M: verify()
    M-->>T: Xác nhận expectation
~~~

Mock server chặn kết nối ở lớp Spring-WS `WebServiceMessageSender`. Vì vậy test có thể xác nhận **URI mà template yêu cầu** và **SOAP message trước khi gửi ra ngoài**, đồng thời mô phỏng response mà không cần server đối tác.

### 2.2. Ba khái niệm không được nhầm

| Thành phần | Hướng dữ liệu | Chức năng |
| --- | --- | --- |
| `RequestMatcher` | URI + request từ client | Kiểm tra request outbound. |
| `ResponseCreator` | Request đã khớp | Tạo response giả cho client. |
| `ResponseMatcher` | Request + response ở server test | Kiểm tra response mà endpoint trả về. |

`RequestMatcher` và `ResponseMatcher` cùng có chữ “Matcher” nhưng thuộc hai luồng test khác nhau:

- Client test dùng package `org.springframework.ws.test.client`.
- Server test dùng package `org.springframework.ws.test.server`.

Đừng dùng `ResponseMatchers` để xác minh request outbound của `WebServiceTemplate`; hãy dùng `RequestMatchers`.

## 3. Contract của RequestMatcher

### 3.1. Interface nhận URI và WebServiceMessage

Spring-WS định nghĩa strategy interface theo dạng:

~~~java
public interface RequestMatcher {
    void match(URI uri, WebServiceMessage request)
            throws IOException, AssertionError;
}
~~~

Hai tham số mang ý nghĩa riêng:

- `uri`: destination mà `WebServiceTemplate` đang kết nối tới. Matcher có thể xác minh endpoint URI, scheme, path hoặc host theo expectation.
- `request`: SOAP message đã được client tạo. Matcher có thể kiểm tra payload, SOAP Header, Envelope hoặc các dữ liệu XML liên quan.

Matcher không trả về boolean. Nếu request đạt expectation, method kết thúc bình thường. Nếu không đạt, matcher ném `AssertionError`; lỗi đọc dữ liệu có thể biểu diễn bằng `IOException`.

Vì interface là một strategy, có thể viết matcher tùy chỉnh. Tuy nhiên, với phần lớn test contract, `RequestMatchers` dựng sẵn đã đủ.

### 3.2. RequestMatchers là factory

Các factory method nằm trong `org.springframework.ws.test.client.RequestMatchers`. Import tĩnh giúp test ngắn và dễ đọc:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.*;
~~~

Một số matcher tiêu biểu:

| Matcher | Kiểm tra |
| --- | --- |
| `anything()` | Chấp nhận bất kỳ request nào. |
| `connectionTo(String)` | Request kết nối tới URI được chỉ định. |
| `connectionTo(URI)` | Tương tự nhưng dùng `URI` object. |
| `payload(Source)` | Payload XML của request khớp `Source`. |
| `payload(Resource)` | Payload XML khớp resource. |
| `validPayload(Resource, Resource...)` | Payload hợp lệ với các XSD schema được cung cấp. |
| `xpath(String)` | XPath tồn tại/không tồn tại hoặc có giá trị kỳ vọng. |
| `xpath(String, Map<String,String>)` | XPath với namespace mapping tường minh. |
| `soapHeader(QName)` | Request có SOAP Header block với QName đó. |
| `soapEnvelope(Source)` | Toàn bộ SOAP Envelope khớp XML nguồn. |
| `soapEnvelope(Resource)` | Toàn bộ SOAP Envelope khớp resource. |

`RequestMatchers` là lớp factory; không cần tự khởi tạo instance của lớp này. Các test thường gọi trực tiếp `payload(...)`, `connectionTo(...)`, `xpath(...)` qua static imports.

## 4. Khởi tạo MockWebServiceServer

### 4.1. Gắn vào WebServiceTemplate

Đây là cách thường dùng nhất khi test một client có `WebServiceTemplate` cụ thể:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;

class OrderClientTest {
    private WebServiceTemplate webServiceTemplate;
    private MockWebServiceServer mockServer;
    private OrderClient orderClient;

    @BeforeEach
    void setUp() {
        webServiceTemplate = createWebServiceTemplate();
        orderClient = new OrderClient(webServiceTemplate);
        mockServer = MockWebServiceServer.createServer(
            webServiceTemplate);
    }
}
~~~

`createWebServiceTemplate()` là helper của test, có trách nhiệm cấu hình SOAP message factory, marshaller/unmarshaller và URI mặc định hoặc URI được truyền lúc gọi. `OrderClient` là class ứng dụng minh họa.

Khi gọi `createServer(webServiceTemplate)`, Spring-WS thay thế message sender của template bằng mock sender cho test. Hãy tạo mock server **sau khi template đã được cấu hình** và trước khi client gửi request.

### 4.2. Gắn vào WebServiceGatewaySupport

Nếu client kế thừa `WebServiceGatewaySupport`, có thể gắn mock server vào gateway:

~~~java
MockWebServiceServer mockServer =
    MockWebServiceServer.createServer(orderClient);
~~~

Spring-WS lấy `WebServiceTemplate` đã được cấu hình bên trong gateway. Cách này phù hợp khi client đóng gói template trong một lớp chuyên trách.

### 4.3. Tạo từ ApplicationContext

Có thể tạo mock server từ context Spring:

~~~java
MockWebServiceServer mockServer =
    MockWebServiceServer.createServer(applicationContext);
~~~

Factory method tìm `WebServiceTemplate` hoặc `WebServiceGatewaySupport` đã cấu hình trong context. Nếu không tìm thấy, nó ném `IllegalArgumentException`. Vì vậy, context test cần chứa đúng bean client/template mà bài kiểm thử muốn thay sender.

### 4.4. Không tạo hai mock server cho cùng một template một cách tùy tiện

Mock server gắn mock sender vào template. Nếu nhiều setup cùng sửa một template, expectation có thể thuộc sai instance hoặc sender bị thay thế. Mỗi test fixture nên có lifecycle rõ: tạo template/client cho test; tạo một mock server; đăng ký expectation; gọi client; `verify()`; reset hoặc tạo fixture mới ở test tiếp theo.

Nếu test chạy song song, không chia sẻ một mutable `WebServiceTemplate`/`MockWebServiceServer` giữa các test execution mà không có isolation.

## 5. RequestCreators và ResponseCreators trong một test client

### 5.1. RequestCreator phía server khác RequestMatcher phía client

`RequestCreator` của server test tạo message để gửi vào endpoint. `RequestMatcher` của client test xác minh message được client tạo ra. Với client test, không cần tự tạo `RequestCreator`.

### 5.2. ResponseCreator tạo response giả

Sau khi request khớp, `MockWebServiceServer` cần một response để trả về cho `WebServiceTemplate`. `ResponseCreators` có các factory phổ biến:

| Factory | Behavior |
| --- | --- |
| `withPayload(Source)` | Trả response payload XML. |
| `withPayload(Resource)` | Trả payload từ resource. |
| `withSoapEnvelope(Source)` | Trả SOAP Envelope hoàn chỉnh. |
| `withSoapEnvelope(Resource)` | Trả Envelope từ resource. |
| `withClientOrSenderFault(String, Locale)` | Tạo Client/Sender Fault. |
| `withServerOrReceiverFault(String, Locale)` | Tạo Server/Receiver Fault. |
| `withMustUnderstandFault(String, Locale)` | Tạo MustUnderstand Fault. |
| `withVersionMismatchFault(String, Locale)` | Tạo VersionMismatch Fault. |
| `withException(IOException)` | Làm connection mô phỏng ném IOException. |
| `withException(RuntimeException)` | Làm connection mô phỏng ném runtime exception. |
| `withError(String)` | Đặt trạng thái connection error/message. |

Test client cần response phù hợp với SOAP version và cách client đang parse Fault. Nếu ứng dụng mong muốn exception, hãy test exception mapping/unmarshal behavior đúng với cấu hình `WebServiceTemplate`.

### 5.3. Một request expectation hoàn chỉnh

~~~java
mockServer.expect(payload(expectedRequest))
    .andRespond(withPayload(responsePayload));
~~~

`expect(...)` nhận `RequestMatcher`. `andRespond(...)` nhận `ResponseCreator`. Cùng một đoạn chain nhưng hai thành phần có nhiệm vụ khác nhau: **đầu tiên xác minh request, sau đó dựng response**.

## 6. connectionTo(): xác minh destination URI

### 6.1. Endpoint URI là một phần của integration contract

Client có thể marshal XML chính xác nhưng gọi nhầm URL do cấu hình environment, typo hoặc nhầm endpoint WSDL. `connectionTo(...)` kiểm tra URI mà `WebServiceTemplate` sử dụng.

~~~java
import static org.springframework.ws.test.client.RequestMatchers.connectionTo;

mockServer.expect(connectionTo(
        "https://partner.example.com/services/orders"))
    .andRespond(withPayload(responsePayload));
~~~

Có overload nhận `URI`:

~~~java
URI endpoint = URI.create(
    "https://partner.example.com/services/orders");

mockServer.expect(connectionTo(endpoint))
    .andRespond(withPayload(responsePayload));
~~~

### 6.2. Khi dùng defaultUri và khi truyền URI lúc gọi

Nếu template được cấu hình `defaultUri`, test có thể xác minh destination mặc định:

~~~java
template.setDefaultUri(
    "https://partner.example.com/services/orders");
~~~

Hoặc client có thể truyền URI động:

~~~java
template.marshalSendAndReceive(
    partnerEndpoint,
    request);
~~~

`connectionTo(...)` kiểm tra URI mà template thật sự yêu cầu, vì vậy nó bắt được trường hợp client chọn nhầm endpoint dù defaultUri nhìn có vẻ đúng.

### 6.3. Không hard-code môi trường vào logic client

Production endpoint, staging endpoint và local test endpoint thường khác nhau. Nên cấp URI qua configuration/property; test cung cấp URI kỳ vọng cho môi trường test.

Không viết test chỉ pass khi trùng một URL production cố định nếu client được thiết kế để cấu hình theo môi trường. Thay vào đó, test có thể xác minh scheme/host/path cụ thể của test configuration hoặc inject một URI đã biết.

Matcher `connectionTo(...)` kiểm tra URI được dùng bởi Spring-WS mock connection. Nó không xác minh DNS resolution, TLS certificate, reverse proxy hoặc firewall của URI đó.

## 7. payload(): kiểm tra SOAP Body được gửi

### 7.1. Kiểm tra XML sau khi JAXB marshal

`payload(...)` là matcher thường dùng nhất. Nó kiểm tra payload XML của request đã được client tạo từ object Java:

~~~java
import org.springframework.xml.transform.StringSource;
import static org.springframework.ws.test.client.RequestMatchers.payload;

var expectedRequest = new StringSource("""
    <ord:GetOrderRequest
        xmlns:ord="https://example.com/orders/v1">
        <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderRequest>
    """);

mockServer.expect(payload(expectedRequest))
    .andRespond(withPayload(responsePayload));
~~~

Điều này kiểm tra output XML của marshalling/client pipeline. Nếu JAXB annotation sai namespace, element name hoặc cấu trúc, expectation sẽ thất bại.

### 7.2. payload(Source) và payload(Resource)

Dùng `Source` khi fixture ngắn hoặc được tạo ngay trong test:

~~~java
var expected = new StringSource("""
    <ord:CancelOrderRequest
        xmlns:ord="https://example.com/orders/v1">
        <ord:orderId>ORD-1001</ord:orderId>
        <ord:reason>CUSTOMER_REQUEST</ord:reason>
    </ord:CancelOrderRequest>
    """);

mockServer.expect(payload(expected))
    .andRespond(withPayload(cancelResponse));
~~~

Dùng `Resource` khi fixture được quản lý thành file XML:

~~~java
import org.springframework.core.io.ClassPathResource;

mockServer.expect(payload(
        new ClassPathResource("soap/requests/cancel-order.xml")))
    .andRespond(withPayload(
        new ClassPathResource("soap/responses/cancel-order.xml")));
~~~

Resource phù hợp khi XML fixture dài, được tái sử dụng hoặc muốn review độc lập với code Java. Hãy giữ fixture đồng bộ với contract version.

### 7.3. XML comparison và XMLUnit Placeholders

`payload(...)` hỗ trợ XMLUnit Placeholders. Chúng hữu ích khi một vài giá trị được sinh động trong lúc chạy, chẳng hạn request ID hoặc timestamp. Chỉ đánh dấu những node biến động; không bỏ qua toàn bộ vùng payload quan trọng.

Nếu request ID được tạo tự động, test có thể dùng XPath xác minh ID không rỗng và đúng format; dùng fixture placeholder nếu cấu hình XMLUnit hỗ trợ; hoặc viết custom matcher để kiểm tra regex/business invariant.

Không thay kiểm tra request ID bằng một placeholder rộng làm test không còn xác minh correlation semantics.

### 7.4. Namespace là một phần của hợp đồng

Hai prefix khác nhau nhưng cùng namespace URI và local name có thể biểu diễn cùng QName. Tuy nhiên, namespace URI sai là lỗi contract. Không nên chuyển fixture sang `local-name()` để matcher bỏ qua namespace một cách vô điều kiện.

`payload(...)` so sánh XML theo cơ chế XML comparison của Spring-WS/XMLUnit; không hiểu nó là `String.equals(...)` trên raw SOAP bytes. Prefix/format whitespace không phải lúc nào cũng có ý nghĩa như QName, element hierarchy và text values.

## 8. validPayload(): xác minh request tuân XSD

### 8.1. Vì sao cần schema assertion?

Một request có thể trông hợp lý nhưng vi phạm XSD: thiếu element bắt buộc; thứ tự element sai với `xs:sequence`; sai kiểu dữ liệu/pattern; giá trị không nằm trong enumeration; vi phạm `minOccurs`/`maxOccurs`; QName/namespace không đúng contract; hoặc attribute bắt buộc không có.

`validPayload(...)` kiểm tra SOAP payload outbound có hợp lệ với schema được cung cấp.

### 8.2. Ví dụ

~~~java
import org.springframework.core.io.ClassPathResource;
import static org.springframework.ws.test.client.RequestMatchers.validPayload;

mockServer.expect(validPayload(
        new ClassPathResource("xsd/order-request.xsd")))
    .andRespond(withPayload(responsePayload));
~~~

Nếu schema có import/include các schema khác, truyền resources bổ sung:

~~~java
mockServer.expect(validPayload(
        new ClassPathResource("xsd/order-request.xsd"),
        new ClassPathResource("xsd/common-types.xsd")))
    .andRespond(withPayload(responsePayload));
~~~

Factory signature nhận schema đầu tiên và varargs `furtherSchemas`. Nó có thể ném `IOException` khi tải resource. Hãy dùng đúng các XSD version được WSDL công bố, không dùng schema cũ chỉ vì nó làm test pass.

### 8.3. payload và validPayload trả lời hai câu hỏi khác nhau

| Matcher | Câu hỏi |
| --- | --- |
| `payload(expected)` | Request có đúng XML content được mong đợi không? |
| `validPayload(schema)` | Request có tuân XSD schema không? |

Một payload có thể hợp lệ theo XSD nhưng gửi sai `orderId` hoặc sai giá trị business; vì vậy schema validation không thay thế assertion nội dung. Ngược lại fixture có thể đúng một vài field nhưng thiếu field bắt buộc; payload assertion và schema validation bổ sung cho nhau.

## 9. xpath(): xác minh dữ liệu theo namespace

### 9.1. XPath có namespace mapping

Với XML namespace, hãy dùng overload nhận map:

~~~java
import java.util.Map;
import static org.springframework.ws.test.client.RequestMatchers.xpath;

Map<String, String> namespaces = Map.of(
    "ord", "https://example.com/orders/v1");

mockServer.expect(xpath(
        "/ord:CancelOrderRequest/ord:reason",
        namespaces).evaluatesTo("CUSTOMER_REQUEST"))
    .andRespond(withPayload(cancelResponse));
~~~

Prefix `ord` là prefix do test đặt và ánh xạ tới namespace URI. Prefix này không nhất thiết phải giống prefix mà marshaller serialize trong request.

### 9.2. Các kiểu expectation

`RequestMatchers.xpath(...)` trả về `RequestXPathExpectations`, cho phép xây matcher cụ thể:

| Method | Ý nghĩa |
| --- | --- |
| `exists()` | XPath chọn được node/nội dung. |
| `doesNotExist()` | XPath không chọn được nội dung. |
| `evaluatesTo(String)` | Kết quả XPath dạng chuỗi đúng kỳ vọng. |
| `evaluatesTo(int)` | Kết quả XPath dạng số nguyên đúng kỳ vọng. |
| `evaluatesTo(double)` | Kết quả XPath dạng số thực đúng kỳ vọng. |
| `evaluatesTo(boolean)` | Kết quả XPath boolean đúng kỳ vọng. |

~~~java
mockServer.expect(xpath(
        "/ord:GetOrderRequest/ord:orderId",
        namespaces).exists())
    .andExpect(xpath(
        "string(/ord:GetOrderRequest/ord:orderId)",
        namespaces).evaluatesTo("ORD-1001"))
    .andExpect(xpath(
        "count(/ord:GetOrderRequest/ord:lineItems/ord:item)",
        namespaces).evaluatesTo(2))
    .andRespond(withPayload(responsePayload));
~~~

`andExpect(...)` ở đây vẫn nối **các RequestMatcher** cho cùng một request. XPath chỉ là một cách xây matcher.

### 9.3. XPath không namespace có thể tạo false positive

Không nên dùng XPath chung chung như:

~~~java
xpath("//*[local-name()='orderId']").evaluatesTo("ORD-1001");
~~~

Nó có thể chọn một `orderId` ở namespace/nhánh không mong đợi. Hãy ưu tiên absolute XPath và namespace mapping. Nếu payload chứa nhiều node có local name giống nhau, expression phải chỉ rõ đường dẫn đầy đủ.

### 9.4. Kiểm tra dữ liệu không được gửi

Client cũng cần bảo đảm không gửi field nội bộ tới đối tác:

~~~java
mockServer.expect(xpath(
        "/ord:GetOrderRequest/ord:internalNotes",
        namespaces).doesNotExist())
    .andRespond(withPayload(responsePayload));
~~~

Đây là regression assertion hữu ích khi request model có field nội bộ hoặc có nguy cơ lộ dữ liệu. Nó bổ sung cho review data minimization, không thay thế security review.

## 10. soapHeader(): kiểm tra SOAP Header outbound

### 10.1. Header thường chứa metadata giao thức

SOAP Header có thể chứa WS-Addressing `Action`, `To`, `MessageID`, `ReplyTo`; WS-Security `Security`, UsernameToken, Timestamp, Signature; Correlation ID hoặc Header nghiệp vụ theo contract.

`soapHeader(QName)` xác minh request có một Header block với qualified name mong đợi:

~~~java
import javax.xml.namespace.QName;
import static org.springframework.ws.test.client.RequestMatchers.soapHeader;

QName securityQName = new QName(
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "Security");

mockServer.expect(soapHeader(securityQName))
    .andRespond(withPayload(responsePayload));
~~~

`QName` là `javax.xml.namespace.QName` thuộc Java SE; namespace URI và local part xác định Header block, không phải prefix tình cờ.

### 10.2. Có Header không có nghĩa nội dung Header đúng

`soapHeader(QName)` chỉ xác minh sự tồn tại của Header block. Nó không tự xác minh:

- UsernameToken có Username/Password type đúng;
- Nonce/Created hợp lệ;
- XML Signature đúng và bao phủ SOAP Body;
- WS-Addressing Action/To/MessageID có giá trị mong đợi;
- `mustUnderstand`, role/actor hoặc thứ tự Header;
- Header không bị lặp ngoài ý muốn.

Nếu phải kiểm tra giá trị, kết hợp XPath hoặc custom matcher. Đặc biệt với WS-Security, sự hiện diện của `wsse:Security` không chứng minh chữ ký/token được cấu hình đúng.

## 11. soapEnvelope(): kiểm tra toàn bộ SOAP message

### 11.1. Khi cần kiểm tra cả Header và Body

`soapEnvelope(...)` kiểm tra toàn bộ SOAP Envelope request thay vì chỉ payload. Dùng khi contract yêu cầu chính xác cả SOAP Header và cấu trúc Body:

~~~java
import org.springframework.xml.transform.StringSource;
import static org.springframework.ws.test.client.RequestMatchers.soapEnvelope;

var expectedEnvelope = new StringSource("""
    <soap:Envelope
        xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:addr="http://www.w3.org/2005/08/addressing"
        xmlns:ord="https://example.com/orders/v1">
        <soap:Header>
            <addr:Action>https://example.com/orders/GetOrder</addr:Action>
        </soap:Header>
        <soap:Body>
            <ord:GetOrderRequest>
                <ord:orderId>ORD-1001</ord:orderId>
            </ord:GetOrderRequest>
        </soap:Body>
    </soap:Envelope>
    """);

mockServer.expect(soapEnvelope(expectedEnvelope))
    .andRespond(withPayload(responsePayload));
~~~

Ví dụ giả định client thực sự tạo WS-Addressing Action. Nếu action không thuộc contract thì không đưa vào fixture chỉ để test qua.

### 11.2. Khi full-envelope matcher quá chặt

Một SOAP Envelope có thể chứa dữ liệu biến động như WS-Security Timestamp, Nonce, SignatureValue, WS-Addressing MessageID hoặc Correlation ID.

Nếu test không có mục tiêu xác minh toàn bộ các dữ liệu này, `soapEnvelope(...)` có thể làm test dễ vỡ khi implementation hợp lệ thay đổi metadata. Dùng `payload(...)` kết hợp `soapHeader(...)` hoặc XPath cho phần thực sự thuộc contract.

## 12. anything(): khi nào chấp nhận bất kỳ request nào?

`anything()` tạo matcher chấp nhận bất kỳ request message nào:

~~~java
mockServer.expect(anything())
    .andRespond(withPayload(responsePayload));
~~~

Nó có thể hữu ích khi test chỉ quan tâm đến response parsing của client và không muốn lặp payload assertions trong một test nhỏ. Tuy nhiên, nó không chứng minh client gửi đúng endpoint, operation, payload hoặc security headers.

Không dùng `anything()` làm expectation duy nhất trong test contract/interoperability. Nếu client vô tình bỏ payload, gọi sai URI hoặc bỏ WS-Security Header, test vẫn có thể pass miễn code nhận được response giả.

## 13. Kết hợp nhiều RequestMatcher cho một request

### 13.1. andExpect() thêm expectation

`MockWebServiceServer.expect(RequestMatcher)` trả về `ResponseActions`. `ResponseActions.andExpect(RequestMatcher)` cho phép thêm matcher cho **cùng request expectation**; `andRespond(ResponseCreator)` định nghĩa response sau khi các matcher thỏa mãn.

~~~java
Map<String, String> ns = Map.of(
    "ord", "https://example.com/orders/v1");

mockServer.expect(connectionTo(
        "https://partner.example.com/services/orders"))
    .andExpect(payload(expectedRequest))
    .andExpect(validPayload(orderRequestSchema))
    .andExpect(xpath(
        "/ord:GetOrderRequest/ord:orderId", ns)
        .evaluatesTo("ORD-1001"))
    .andExpect(soapHeader(actionQName))
    .andRespond(withPayload(responsePayload));
~~~

Đoạn test diễn đạt một request phải thỏa đồng thời các điều kiện: gửi tới đúng URI; payload khớp fixture; payload hợp XSD; `orderId` đúng; có SOAP Header Action; sau đó mới nhận response giả.

Mỗi matcher bổ sung một góc kiểm tra. Nếu `payload(...)` đã xác minh toàn bộ phần dữ liệu và XPath không thêm thông tin rõ ràng, có thể lược bớt XPath để tránh assertion trùng lặp.

### 13.2. Đừng dùng matcher tổng quát thay assertion cụ thể

Một test chỉ có `anything()` rồi trả response thành công là test mô phỏng response parsing, không phải test request contract. Một test chỉ dùng `soapHeader(Security)` cũng không chứng minh UsernameToken đúng.

| Mục tiêu test | Matcher gợi ý |
| --- | --- |
| Chọn đúng endpoint | `connectionTo(...)` |
| JAXB marshal đúng payload | `payload(...)` |
| Tuân thủ XSD | `validPayload(...)` |
| Giá trị field quan trọng | `xpath(...)` |
| Header block bắt buộc có mặt | `soapHeader(...)` |
| Full SOAP wire shape | `soapEnvelope(...)` |
| Chỉ test response handling | Có thể dùng `anything()` với phạm vi hẹp |

## 14. Luồng request order và verify()

### 14.1. Đăng ký expectation trước khi gọi client

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

@Test
void getOrderUsesExpectedSoapRequest() {
    mockServer.expect(payload(expectedRequest))
        .andRespond(withPayload(expectedResponse));

    OrderSummary result = orderClient.getOrder("ORD-1001");

    assertEquals("ORD-1001", result.orderId());
    assertEquals("CONFIRMED", result.status());
    mockServer.verify();
}
~~~

Expectation phải được đăng ký trước khi gọi operation tạo outbound request. Nếu client chạy trước khi mock server được gắn/expectation được cài đặt, nó có thể dùng sender khác hoặc bị báo không có expectation.

### 14.2. verify() xác nhận expectation đã được thực hiện

`verify()` là bước quan trọng. Nếu test gọi client không hề phát request, assertion object ở một nhánh khác có thể vẫn pass; `verify()` phát hiện expectation chưa được đáp ứng.

Các lỗi `verify()` có thể phát hiện:

- Client không gọi `WebServiceTemplate`;
- Code return sớm trước khi gửi SOAP request;
- Nhánh điều kiện không gọi operation dự kiến;
- Request gửi không khớp matcher;
- Số lần gửi không thỏa expectation.

### 14.3. Nhiều request trong một test

Khi client thực hiện nhiều SOAP calls, đăng ký từng expectation và response tương ứng:

~~~java
mockServer.expect(connectionTo(customerEndpoint))
    .andExpect(payload(customerLookupRequest))
    .andRespond(withPayload(customerResponse));

mockServer.expect(connectionTo(orderEndpoint))
    .andExpect(payload(orderLookupRequest))
    .andRespond(withPayload(orderResponse));

CustomerDashboard result =
    dashboardClient.loadDashboard("C-100");

mockServer.verify();
~~~

Đặt mỗi expectation sát với request/response tương ứng trong test setup để dễ nhìn. Mặc định hãy thiết kế flow xác định và dùng thứ tự expectation rõ ràng; nếu client gửi requests song song hoặc không xác định thứ tự, cần kiểm tra khả năng mock server/expectation trong version đang dùng và tách test hoặc dùng chiến lược matcher phù hợp. Không giả định mọi mock expectations đều thread-safe trong mọi pattern.

## 15. ResponseCreators dùng để mô phỏng phản hồi client

### 15.1. Success response

Thông dụng nhất là `withPayload(...)`:

~~~java
mockServer.expect(payload(expectedRequest))
    .andRespond(withPayload(expectedResponse));
~~~

Sau đó client thực hiện unmarshal response như khi gọi server thật.

### 15.2. Trả SOAP Fault

Có thể mô phỏng Client/Sender Fault:

~~~java
import java.util.Locale;
import static org.springframework.ws.test.client.ResponseCreators.withClientOrSenderFault;

mockServer.expect(payload(invalidRequest))
    .andRespond(withClientOrSenderFault(
        "Invalid order request",
        Locale.ENGLISH));
~~~

Server/Receiver Fault:

~~~java
mockServer.expect(payload(request))
    .andRespond(withServerOrReceiverFault(
        "Temporary processing failure",
        Locale.ENGLISH));
~~~

### 15.3. Transport exception

Khi muốn kiểm tra retry/error mapping phía client:

~~~java
import java.io.IOException;
import static org.springframework.ws.test.client.ResponseCreators.withException;

mockServer.expect(payload(request))
    .andRespond(withException(
        new IOException("Simulated connection failure")));
~~~

`withException(...)` mô phỏng exception từ mock connection. Nó hữu ích để kiểm tra client chuyển lỗi network thành application exception, ghi nhận retryable/non-retryable error hoặc không làm mất correlation context. Không dùng exception fixture chứa credentials hoặc dữ liệu nhạy cảm.

### 15.4. withError() khác withException()

`withError(String)` đánh dấu connection có error message theo cơ chế `WebServiceConnection.hasError()` / `getErrorMessage()`. `withException(...)` ném exception trong luồng connection. Hai tình huống có thể dẫn đến error handling khác nhau trong client transport; test đúng loại lỗi mà client cần xử lý.

## 16. Tự viết RequestMatcher

### 16.1. Khi matcher dựng sẵn không đủ

Custom matcher hữu ích khi cần kiểm tra điều kiện đặc thù như Header có giá trị correlation đúng định dạng; HTTP destination path thuộc tenant cụ thể; SOAP Body field có metadata custom; giá trị dynamic phải thỏa regex/range; hoặc Header và payload có quan hệ nhất quán.

~~~java
import java.io.IOException;
import java.net.URI;
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.test.client.RequestMatcher;

public final class CorrelationHeaderMatcher
        implements RequestMatcher {
    @Override
    public void match(URI uri, WebServiceMessage request)
            throws IOException {
        // Đọc SOAP message/header bằng API phù hợp.
        // Nếu expectation không đạt, ném AssertionError.
    }
}
~~~

Đây là skeleton; cần triển khai phần đọc Header bằng SOAP API tương ứng message type/SOAP version. Không đọc raw transport bytes hoặc parse XML bằng string matching nếu SOAP API đã cung cấp accessor.

### 16.2. Viết matcher có failure message tốt

Một custom matcher nên kiểm tra URI/message type null hoặc không đúng loại rõ ràng; dùng QName/namespace-aware APIs; chỉ đọc dữ liệu thuộc contract; ném `AssertionError` cụ thể với giá trị thực ở mức an toàn; không ghi credentials/WS-Security token/PII; không mutate request; và không tiêu thụ stream theo cách khiến bước khác không đọc được.

Đừng tạo matcher tùy chỉnh để viết lại `payload` hoặc `xpath` chỉ vì muốn tên method khác. Dùng API dựng sẵn khi nó diễn đạt đúng requirement.

## 17. RequestMatcher khác ResponseMatcher và RequestCreator thế nào?

| Interface | Package | Thời điểm | Nhiệm vụ |
| --- | --- | --- | --- |
| `RequestCreator` | `org.springframework.ws.test.server` | Trước khi server test dispatch | Tạo request message cho server. |
| `RequestMatcher` | `org.springframework.ws.test.client` | Khi `WebServiceTemplate` gửi request trong client test | Xác minh URI và outbound request message. |
| `ResponseMatcher` | `org.springframework.ws.test.server` | Sau khi endpoint trả response trong server test | Xác minh response message. |

Client-side flow:

~~~text
WebServiceTemplate
    → RequestMatcher xác minh request
    → ResponseCreator dựng response
    → WebServiceTemplate nhận response
~~~

Server-side flow:

~~~text
MockWebServiceClient
    → RequestCreator tạo request
    → MessageDispatcher/Endpoint xử lý
    → ResponseMatcher xác minh response
~~~

Tên gần giống nhưng vị trí hoàn toàn khác. Hãy xác định test đang kiểm tra **client gửi ra** hay **server trả về** trước khi chọn API.

## 18. Những lỗi thường gặp khi viết RequestMatchers

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có request expectation được đáp ứng | Client không gọi template, flow return sớm hoặc gọi template khác. | Kiểm tra bean/template được mock và gọi `verify()`. |
| `connectionTo(...)` fail | URI runtime khác cấu hình test, path/context/query khác. | Kiểm tra config và destination thật. |
| `payload(...)` fail | JAXB namespace, QName, element order hoặc value sai. | Kiểm tra XML fixture và marshaller context. |
| `validPayload(...)` fail | XSD sai version hoặc payload vi phạm schema. | Dùng XSD contract thật và các schema dependencies. |
| XPath không tìm node | Thiếu namespace map hoặc sai absolute path. | Dùng overload `xpath(expression, namespaces)`. |
| XPath chọn sai node | Dùng local-name() quá rộng hoặc expression thiếu scope. | Dùng QName/namespace và absolute XPath. |
| `soapHeader(...)` fail | Interceptor không thêm Header hoặc QName sai. | Kiểm tra interceptor, SOAP version và QName. |
| `soapEnvelope(...)` fail | Fixture cố định metadata động như timestamp/MessageID. | Chuyển sang payload/Header/XPath matcher cụ thể. |
| Test pass với request sai | Chỉ dùng `anything()` hoặc matcher quá lỏng. | Thêm assertion đúng contract, XSD và URI. |
| Client không unmarshal response giả | Response payload namespace/QName không đúng JAXB model. | Sửa response fixture theo response XSD. |
| Fault test không ném exception dự kiến | Fault type/SOAP version hoặc client fault resolver khác assumption. | Kiểm tra response Fault và template exception mapping. |
| `verify()` báo thiếu request | Operation chưa được gọi hoặc expectation chưa match. | Xác minh branch, URI, request count và test setup. |
| Matcher custom làm hỏng assertion khác | Đọc/tiêu thụ stream hoặc mutate message. | Dùng API accessor/copy có chủ ý và không sửa message. |
| Mock test pass nhưng production gửi sai TLS/HTTP headers | Mock server không mở kết nối network thật. | Bổ sung integration test transport/HTTP riêng. |

### 18.1. Prefix không phải QName

Hai XML fragment có thể biểu diễn cùng QName:

~~~xml
<ord:orderId xmlns:ord="https://example.com/orders/v1">ORD-1001</ord:orderId>
~~~

~~~xml
<o:orderId xmlns:o="https://example.com/orders/v1">ORD-1001</o:orderId>
~~~

Prefix khác, namespace URI và local part giống nhau. Test nên kiểm tra namespace URI, không gắn cứng prefix nếu prefix không phải lexical requirement của đối tác.

### 18.2. Không dùng payload fixture sai contract để làm test pass

Nếu fixture XML được viết theo implementation hiện tại nhưng sai WSDL/XSD, test có thể đóng băng bug. Fixture cần đối chiếu contract được version hóa, nhất là QName, sequence, optional elements, SOAP version và Fault types.

### 18.3. Không log raw request khi test thất bại trong môi trường có secrets thật

Request có thể chứa WS-Security UsernameToken, signature, PII hoặc payload kinh doanh. Dùng synthetic credentials/data trong fixture, redaction khi logging và tránh để assertion dump toàn bộ payload nhạy cảm.

## 19. MockWebServiceServer kiểm tra được gì và không kiểm tra được gì?

### Có thể kiểm tra

- URI mà `WebServiceTemplate` yêu cầu;
- XML payload sau khi marshal;
- XSD validity của request;
- XPath/field value;
- SOAP Header block;
- SOAP Envelope;
- Request flow theo expectation;
- Cách client xử lý SOAP response/Fault hoặc exception được mô phỏng.

### Không tự kiểm tra

- DNS, routing, firewall hoặc endpoint server đối tác;
- TLS handshake, certificate chain, hostname verification, mTLS;
- Reverse proxy, gateway auth, HTTP status/headers ngoài behavior mock connection;
- Network timeouts và connection pool thật;
- SMTP/IMAP, XMPP, JMS hoặc message broker delivery;
- SOAP server thực đã nhận và xử lý request;
- Tải/concurrency trên network thật.

`MockWebServiceServer` thay thế message sender trong test. Vì vậy nó kiểm tra request tại ranh giới Spring-WS, không phải test wire-level của transport. Nếu yêu cầu có TLS, HTTP headers, proxy, timeout hoặc interoperability với server đối tác, cần thêm integration test qua embedded server/staging hoặc một test transport phù hợp.

## 20. Ví dụ đầy đủ: OrderClient với request validation

### 20.1. Client minh họa

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;

public class OrderClient {
    private final WebServiceTemplate template;

    public OrderClient(WebServiceTemplate template) {
        this.template = template;
    }

    public OrderResponse getOrder(String orderId) {
        GetOrderRequest request = new GetOrderRequest();
        request.setOrderId(orderId);
        return (OrderResponse) template.marshalSendAndReceive(request);
    }
}
~~~

Các lớp `GetOrderRequest`/`OrderResponse` là model sinh từ XSD. Template cần có defaultUri và marshaller/unmarshaller trong cấu hình test.

### 20.2. Test client

~~~java
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.client.MockWebServiceServer;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.ws.test.client.RequestMatchers.*;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

class OrderClientTest {
    private MockWebServiceServer mockServer;
    private OrderClient orderClient;

    @BeforeEach
    void setUp() {
        var template = createConfiguredTemplate();
        orderClient = new OrderClient(template);
        mockServer = MockWebServiceServer.createServer(template);
    }

    @Test
    void sendsContractCompliantGetOrderRequest() {
        var response = new StringSource("""
            <ord:GetOrderResponse
                xmlns:ord="https://example.com/orders/v1">
                <ord:orderId>ORD-1001</ord:orderId>
                <ord:status>CONFIRMED</ord:status>
            </ord:GetOrderResponse>
            """);

        mockServer.expect(connectionTo(
                "https://partner.example.com/services/orders"))
            .andExpect(payload(new StringSource("""
                <ord:GetOrderRequest
                    xmlns:ord="https://example.com/orders/v1">
                    <ord:orderId>ORD-1001</ord:orderId>
                </ord:GetOrderRequest>
                """)))
            .andExpect(validPayload(
                new ClassPathResource("xsd/order-request.xsd")))
            .andExpect(xpath(
                "/ord:GetOrderRequest/ord:orderId",
                Map.of("ord", "https://example.com/orders/v1"))
                .evaluatesTo("ORD-1001"))
            .andRespond(withPayload(response));

        OrderResponse result = orderClient.getOrder("ORD-1001");
        assertEquals("ORD-1001", result.getOrderId());
        assertEquals("CONFIRMED", result.getStatus());
        mockServer.verify();
    }
}
~~~

Ví dụ giả định `createConfiguredTemplate()` trả template có default URI khớp expectation, JAXB marshaller đã biết các model, và XSD resource tồn tại. `OrderResponse` là class JAXB sinh từ response XSD. Ví dụ tập trung vào pattern test, không thay thế cấu hình dependency/bean của từng project.

### 20.3. Test Fault handling

~~~java
import java.util.Locale;
import static org.springframework.ws.test.client.ResponseCreators.withServerOrReceiverFault;

mockServer.expect(payload(expectedRequest))
    .andRespond(withServerOrReceiverFault(
        "Temporary partner failure",
        Locale.ENGLISH));

// Gọi client và assert exception theo Fault resolver/client behavior.
// Gọi verify() sau khi request đã được gửi.
~~~

Fault response giả cho phép kiểm tra client exception mapping. Không mặc định mọi Fault đều được ném cùng một Java exception trong mọi cấu hình; xác minh behavior thực của `WebServiceTemplate`, `SoapFaultMessageResolver` và exception handling ứng dụng.

## 21. Checklist kiểm thử client SOAP

### Setup

- [ ] MockWebServiceServer được gắn vào đúng WebServiceTemplate/client.
- [ ] Template có message factory và JAXB marshaller/unmarshaller phù hợp.
- [ ] Expectation được khai báo trước khi gọi client.
- [ ] Có verify() sau khi client hoàn thành.

### Request contract

- [ ] connectionTo(...) kiểm tra URI khi destination là một phần requirement.
- [ ] payload(...) xác minh QName, namespace và field quan trọng.
- [ ] validPayload(...) dùng đúng XSD version và schema imports.
- [ ] XPath có namespace map rõ và absolute path phù hợp.
- [ ] soapHeader(...) xác minh Header block cần thiết.
- [ ] soapEnvelope(...) chỉ dùng khi toàn bộ Envelope là requirement.
- [ ] Custom matcher có failure message rõ và không mutate message.

### Response simulation và reliability

- [ ] withPayload(...) mô phỏng success response đúng XSD.
- [ ] Fault response dùng đúng SOAP version/category.
- [ ] withException(...)/withError(...) dùng khi cần test transport error mapping.
- [ ] Có tests cho retry, timeout và duplicate khi operation có side effect.
- [ ] Không dùng anything() làm expectation duy nhất cho test contract.

### Giới hạn

- [ ] Có integration tests riêng cho TLS/certificate/proxy/HTTP headers nếu cần.
- [ ] Không coi mock pass là bằng chứng partner server thực nhận được request.
- [ ] Không log raw secrets/WS-Security token hoặc dữ liệu nhạy cảm.

## 22. Câu hỏi tự kiểm tra

1. RequestMatcher.match(...) nhận những tham số nào?
2. Vì sao matcher cần nhận cả URI và WebServiceMessage?
3. RequestMatchers khác RequestCreators như thế nào?
4. Khi nào dùng MockWebServiceServer.createServer(WebServiceTemplate)?
5. Factory createServer(ApplicationContext) cần tìm thấy bean nào?
6. connectionTo(...) xác minh điều gì và không xác minh điều gì?
7. payload(...) khác validPayload(...) ở mục đích nào?
8. Vì sao XPath cần namespace mapping?
9. soapHeader(QName) chứng minh được gì và không chứng minh được gì?
10. Khi nào soapEnvelope(...) hữu ích, khi nào quá chặt?
11. anything() có thể làm test contract yếu đi như thế nào?
12. andExpect(...) thêm điều kiện cho một request ra sao?
13. andRespond(...) nhận interface nào?
14. Tại sao test cần verify() sau khi gọi client?
15. withException(...) và withError(...) mô phỏng lỗi khác nhau thế nào?
16. Khi nào cần custom RequestMatcher?
17. RequestMatcher và ResponseMatcher thuộc package nào?
18. Vì sao mock sender không kiểm tra TLS handshake hoặc reverse proxy?
19. Cách kiểm tra WS-Security Header có mặt khác gì xác minh chữ ký hợp lệ?
20. Làm sao tránh prefix namespace tình cờ làm test fail hoặc pass sai?

## 23. Bài tập thực hành

**Bối cảnh:** Bạn xây `OrderClient` gọi SOAP partner với operation `GetOrder` và `CancelOrder`. WSDL công bố SOAP 1.1, payload namespace `https://example.com/orders/v1`, và XSD có import `common-types.xsd`. Client phải gửi WS-Addressing Action và WS-Security Header.

### Phần A — Setup mock server

1. Tạo `WebServiceTemplate` với SOAP 1.1 message factory, JAXB marshaller/unmarshaller và default URI.
2. Tạo `MockWebServiceServer` từ template.
3. Tạo fixture XML request/response theo XSD/WSDL contract.

### Phần B — Kiểm tra request

4. Dùng `connectionTo(...)` xác minh URI partner.
5. Dùng `payload(...)` xác minh `GetOrderRequest` đúng QName/namespace/orderId.
6. Dùng `validPayload(...)` với request XSD và common-types XSD.
7. Dùng XPath kiểm tra `orderId` không rỗng và đúng định dạng.
8. Dùng `soapHeader(QName)` kiểm tra WS-Addressing Action và WS-Security Header có mặt.
9. Viết custom matcher khi cần so sánh MessageID/RelatesTo hoặc metadata động.
10. Có một test `CancelOrder` và xác minh field `reason` được marshal đúng.

### Phần C — Mô phỏng response/error

11. Dùng `withPayload(...)` trả success response.
12. Dùng `withClientOrSenderFault(...)` để mô phỏng request bị đối tác từ chối.
13. Dùng `withServerOrReceiverFault(...)` mô phỏng partner failure.
14. Dùng `withException(...)` để kiểm tra network error mapping và retry policy.
15. Gọi `verify()` và tạo test âm cố ý không gọi client để thấy expectation chưa được đáp ứng.

### Phần D — Robustness

16. Làm sai namespace trong fixture và xác minh matcher phát hiện.
17. Bỏ một field bắt buộc trong request và xác minh `validPayload(...)` fail.
18. Đổi destination URI và xác minh `connectionTo(...)` fail.
19. Bỏ WS-Security Header để xác minh matcher Header fail; kiểm tra chữ ký thật ở một test riêng phù hợp.
20. Bổ sung HTTP integration test cho TLS/headers nếu các thuộc tính transport đó là yêu cầu sản phẩm.

**Tiêu chí đạt:** client test chứng minh đúng URI, đúng SOAP payload, hợp XSD, đúng XPath/Header contract, xử lý response/Fault/error theo kỳ vọng và `verify()` xác nhận request đã được gửi. Các giới hạn TLS/network/partner interoperability được kiểm thử riêng ở đúng môi trường.

## 24. Tài liệu tham khảo chính thức

- [Spring Web Services Reference 4.1.4 — Client-side Testing](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): kiến trúc MockWebServiceServer, RequestMatcher, RequestMatchers, ResponseCreator.
- [MockWebServiceServer API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/MockWebServiceServer.html): createServer, expect, verify, reset.
- [RequestMatcher API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/RequestMatcher.html): contract match(URI, WebServiceMessage).
- [RequestMatchers API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/RequestMatchers.html): anything, connectionTo, payload, validPayload, xpath, soapHeader, soapEnvelope.
- [RequestXPathExpectations API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/RequestXPathExpectations.html): exists, doesNotExist, evaluatesTo.
- [ResponseActions API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/ResponseActions.html): andExpect và andRespond.
- [ResponseCreators API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/ResponseCreators.html): dựng payload, SOAP Envelope, SOAP Fault và transport errors.

Các liên kết Javadoc trên tham chiếu Spring-WS **4.1.4**. Nếu dự án dùng release khác, hãy đối chiếu đúng dependency/API, SOAP version và XMLUnit integration trước khi sao chép ví dụ.

## 25. Tổng kết

**RequestMatcher là strategy xác minh URI và SOAP request outbound; RequestMatchers cung cấp các matcher dựng sẵn; MockWebServiceServer gắn mock sender vào WebServiceTemplate, kiểm tra request rồi tạo response thông qua ResponseCreator.** `andExpect(...)` ghép nhiều điều kiện cho cùng request, còn `verify()` xác nhận expectation đã được đáp ứng.

Trong dịch vụ SOAP contract-first, hãy kiểm tra đúng những gì đối tác phụ thuộc: destination URI, payload QName/namespace, XSD validity, các giá trị bằng XPath và SOAP Header/Envelope khi cần. Sử dụng `anything()` có giới hạn, custom matcher cho invariant đặc thù và response creators để kiểm tra cách client xử lý success, Fault lẫn transport errors.

**Ghi nhớ:** một `MockWebServiceServer` test pass chứng minh request mà `WebServiceTemplate` tạo ra thỏa expectation trong mock boundary. Nó không tự chứng minh DNS, TLS, proxy hoặc SOAP server của đối tác hoạt động. Một bộ client tests tốt kết hợp RequestMatchers chính xác với integration tests ở những ranh giới transport thực tế.
