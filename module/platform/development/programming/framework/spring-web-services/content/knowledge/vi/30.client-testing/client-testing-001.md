
# MockWebServiceServer và gắn với WebServiceTemplate cần kiểm thử

> **Chương:** Kiểm thử máy khách  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp.

## 1. Vì sao cần MockWebServiceServer?

SOAP client có thể gửi sai QName, namespace, thứ tự XML, SOAPAction hoặc headers; client cũng có thể xử lý sai response, SOAP Fault và lỗi transport. Test một business service gọi interface giả không chứng minh WebServiceTemplate đã tạo SOAP message đúng.

Spring-WS cung cấp MockWebServiceServer để kiểm thử request/response của WebServiceTemplate mà không gọi SOAP server thật. Mock server nhận message client gửi, kiểm tra expectations và trả response do test định nghĩa.

Điểm cốt yếu: **MockWebServiceServer phải được gắn vào đúng WebServiceTemplate mà client production code sử dụng**. Nếu test tạo mock cho template khác với template được inject vào client, test có thể pass trong khi request thực không đi qua mock.

Sau bài này, bạn có thể:
1. Phân biệt createServer và bindTo.
2. Gắn mock server vào đúng template.
3. Khai báo request expectations và kiểm QName, payload, SOAPAction, headers.
4. Tạo response XML, SOAP Envelope và SOAP Fault.
5. Kiểm tra JAXB marshalling/unmarshalling.
6. Kiểm soát số lần gọi, thứ tự expectations và lỗi không match.
7. Cô lập mock giữa các test.
8. Nhận biết giới hạn của mock so với HTTP/TLS/WS-Security thật.

**Nguyên tắc:** MockWebServiceServer kiểm tra message contract tại ranh giới WebServiceTemplate. Nó không thay thế integration test với HTTP server, TLS, mTLS, WSS4J hoặc implementation thật của đối tác.

## 2. Vị trí MockWebServiceServer

Một SOAP client thường có luồng:

~~~mermaid
flowchart LR
 A["Application service"] --> B["SOAP client adapter"]
 B --> C["WebServiceTemplate"]
 C --> D["Marshaller / Unmarshaller"]
 C --> E["ClientInterceptor"]
 C --> F["MessageSender"]
 F --> G["Remote SOAP service"]
~~~

Trong test, mock server thay ranh giới gửi message:

~~~mermaid
flowchart LR
 A["Application service"] --> B["SOAP client adapter"]
 B --> C["WebServiceTemplate"]
 C --> D["MockWebServiceServer"]
 D --> E["Request matchers"]
 D --> F["Response creators"]
 F --> C
 C --> B
~~~

Mock có thể kiểm tra request đi qua template đã bind, XML payload/QName, SOAPAction, headers, số lần gọi, response unmarshalling và Fault mapping.

Mock không chứng minh DNS, proxy, HTTP sockets, TLS/hostname, mTLS handshake, content type trên transport thật, timeout, connection pool hay WS-Security interoperability với vendor khác. Cũng không chứng minh SOAP server đã chạy business logic.

## 3. Dependency và API cơ bản

Spring-WS Test cung cấp các API thường dùng:

- org.springframework.ws.test.client.MockWebServiceServer
- org.springframework.ws.test.client.RequestMatchers
- org.springframework.ws.test.client.ResponseCreators
- org.springframework.ws.test.client.ResponseMatchers

Static methods thường gặp gồm payload, xpath, soapAction, withPayload, withSoapEnvelope, withConnectionFault và các response creators cho SOAP Fault. Tên overload có thể khác giữa Spring-WS releases; kiểm tra version dependency của dự án.

Maven test dependency:

~~~xml
<dependency>
  <groupId>org.springframework.ws</groupId>
  <artifactId>spring-ws-test</artifactId>
  <scope>test</scope>
</dependency>
~~~

Gradle:

~~~groovy
testImplementation("org.springframework.ws:spring-ws-test")
~~~

Để dependency management/BOM của dự án quản lý version, tránh trộn spring-ws-test khác version với spring-ws-core.

## 4. Gắn mock server với đúng WebServiceTemplate

Ví dụ client adapter:

~~~java
public class OrdersSoapClient {
    private final WebServiceTemplate template;

    public OrdersSoapClient(WebServiceTemplate template) {
        this.template = template;
    }

    public SubmitOrderResponse submit(SubmitOrderRequest request) {
        return (SubmitOrderResponse) template.marshalSendAndReceive(request);
    }
}
~~~

### 4.1. Dùng createServer

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;

class OrdersSoapClientTest {
    private WebServiceTemplate template;
    private MockWebServiceServer mockServer;
    private OrdersSoapClient client;

    @BeforeEach
    void setUp() throws Exception {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.schema");
        marshaller.afterPropertiesSet();

        template = new WebServiceTemplate(marshaller);
        template.setDefaultUri("https://soap.example.test/orders");

        mockServer = MockWebServiceServer.createServer(template);
        client = new OrdersSoapClient(template);
    }
}
~~~

createServer(template) gắn mock vào template được truyền. OrdersSoapClient phải giữ đúng instance đó.

### 4.2. Dùng bindTo

~~~java
mockServer = MockWebServiceServer
        .bindTo(template)
        .build();
~~~

Cách này giúp thể hiện rõ cấu hình bind và có thể dùng các option do API version cung cấp. Dù chọn cách nào, template được bind phải là template mà client gọi.

### 4.3. Anti-pattern: bind nhầm instance

~~~java
WebServiceTemplate templateA = new WebServiceTemplate();
OrdersSoapClient client = new OrdersSoapClient(templateA);

// Sai: mock gắn vào templateB, client vẫn dùng templateA.
WebServiceTemplate templateB = new WebServiceTemplate();
MockWebServiceServer mock = MockWebServiceServer.createServer(templateB);
~~~

Client gửi qua templateA, mock chặn templateB. Test có thể đi ra transport thật hoặc fail ngoài ý muốn. Không để endpoint production có thể được gọi từ test.

### 4.4. Spring application context

~~~java
@SpringBootTest
class OrdersSoapClientContextTest {
    @Autowired
    WebServiceTemplate ordersWebServiceTemplate;

    @Autowired
    OrdersSoapClient ordersSoapClient;

    MockWebServiceServer server;

    @BeforeEach
    void bindMock() {
        server = MockWebServiceServer.createServer(
                ordersWebServiceTemplate);
    }
}
~~~

Nếu có nhiều WebServiceTemplate, dùng bean name/qualifier rõ ràng. Tránh inject nhầm template khi Spring context có nhiều candidates.

## 5. Request expectations

Khai báo expectations trước khi gọi client, rồi verify để xác nhận các requests mong đợi đã xảy ra.

### 5.1. Request/response cơ bản

~~~java
@Test
void sendsRequestAndReadsResponse() {
    Source expected = new StringSource("""
        <ord:SubmitOrderRequest
            xmlns:ord="urn:example:orders:v1">
          <ord:orderId>ORD-1001</ord:orderId>
          <ord:quantity>2</ord:quantity>
        </ord:SubmitOrderRequest>
        """);

    Source response = new StringSource("""
        <ord:SubmitOrderResponse
            xmlns:ord="urn:example:orders:v1">
          <ord:orderId>ORD-1001</ord:orderId>
          <ord:accepted>true</ord:accepted>
        </ord:SubmitOrderResponse>
        """);

    mockServer.expect(payload(expected))
              .andRespond(withPayload(response));

    SubmitOrderResponse result =
            client.submit(new SubmitOrderRequest("ORD-1001", 2));

    assertEquals("ORD-1001", result.getOrderId());
    assertTrue(result.isAccepted());
    mockServer.verify();
}
~~~

DTO/constructor/getter là types giả định của ứng dụng. Cần cấu hình JAXB context path và imports phù hợp project. Payload matcher giúp kiểm XML sau khi client marshal, thay vì chỉ kiểm Java DTO trước serialization.

### 5.2. Kiểm tra QName bằng XPath

~~~java
mockServer.expect(xpath(
        "local-name(/*) = 'SubmitOrderRequest' and " +
        "namespace-uri(/*) = 'urn:example:orders:v1'"))
    .andRespond(withPayload(response));
~~~

So namespace URI và local part, không so prefix literal. Prefix khác nhau vẫn có thể tạo cùng QName.

Có thể dùng XPath kiểm orderId, quantity, optional fields, số child elements, nested namespaces và các giá trị biên.

### 5.3. Kiểm SOAPAction

~~~java
mockServer.expect(soapAction(
        "urn:example:orders:v1/SubmitOrder"))
    .andRespond(withPayload(response));
~~~

SOAPAction phải khớp WSDL binding/đối tác. Nó là routing metadata, không phải authentication hoặc bằng chứng WS-Security.

### 5.4. Callback và custom headers

~~~java
template.marshalSendAndReceive(
        request,
        new SoapActionCallback(
            "urn:example:orders:v1/SubmitOrder"));
~~~

Nếu callback hoặc ClientInterceptor thêm SOAP headers, hãy kiểm tra final SOAP message bằng built-in matcher hoặc custom RequestMatcher. Test callback độc lập không chứng minh header đã xuất hiện trong message được gửi.

## 6. Response creators

### 6.1. Payload response

~~~java
mockServer.expect(anything())
    .andRespond(withPayload(new StringSource("""
        <ord:GetOrderResponse
            xmlns:ord="urn:example:orders:v1">
          <ord:orderId>ORD-1001</ord:orderId>
          <ord:status>PAID</ord:status>
        </ord:GetOrderResponse>
        """)));
~~~

anything() chỉ phù hợp khi test không quan tâm request content. Với contract-sensitive tests, dùng payload/QName/XPath/SOAPAction cụ thể.

### 6.2. SOAP Envelope response

~~~java
mockServer.expect(anything())
    .andRespond(withSoapEnvelope(new StringSource("""
      <soapenv:Envelope
          xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
          xmlns:ord="urn:example:orders:v1">
        <soapenv:Header/>
        <soapenv:Body>
          <ord:GetOrderResponse>
            <ord:orderId>ORD-1001</ord:orderId>
            <ord:status>PAID</ord:status>
          </ord:GetOrderResponse>
        </soapenv:Body>
      </soapenv:Envelope>
    """)));
~~~

API overload cần đối chiếu Spring-WS version thực. Với SOAP 1.2, envelope namespace/message factory phải đúng; không chỉ đổi HTTP content type của SOAP 1.1.

### 6.3. SOAP Fault

Spring-WS test có response creators cho Sender/Client và Receiver/Server faults; naming thay đổi theo version. Ví dụ API một số phiên bản:

~~~java
mockServer.expect(anything())
    .andRespond(withClientOrSenderFault(
        "Invalid order identifier", Locale.ENGLISH));
~~~

Test phải kiểm client ánh xạ fault đúng exception/domain error. Không assert RuntimeException tổng quát nếu contract có modeled fault. SOAP 1.1 Client/Server và SOAP 1.2 Sender/Receiver có fault model khác nhau.

### 6.4. Connection fault

~~~java
mockServer.expect(anything())
    .andRespond(withConnectionFault());
~~~

Dùng để test adapter xử lý connection failure. Nó không mô phỏng đầy đủ DNS, TLS handshake, socket timeout, half-closed connection hay proxy reset. Những trường hợp đó cần HTTP transport tests.

## 7. Thứ tự và số lần gọi

### 7.1. Verify expectations

Gọi mockServer.verify() cuối test hoặc qua lifecycle support tương ứng. Nếu không verify, test có thể bỏ sót trường hợp client không gửi request dù expectation đã khai báo.

### 7.2. Nhiều requests

~~~java
mockServer.expect(payload(tokenRequest))
    .andRespond(withPayload(tokenResponse));

mockServer.expect(payload(orderRequest))
    .andRespond(withPayload(orderResponse));

client.submitOrder(...);
mockServer.verify();
~~~

Khi thứ tự quan trọng, giữ ordered expectations theo semantics của Spring-WS version. Nếu cấu hình cho phép unordered expectations, không dùng nó trong test cần xác minh protocol sequence.

### 7.3. Số lần gọi

Một số version hỗ trợ ExpectedCount:

~~~java
mockServer.expect(times(2), payload(statusRequest))
    .andRespond(withPayload(statusResponse));
~~~

Kiểm tra static import và semantics của times() theo dependency version. Với retry/polling, assert số lần WebServiceTemplate được gọi và tổng số responses. Unexpected extra request phải làm test fail.

## 8. JAXB marshalling và unmarshalling

Nên dùng đúng Marshaller/Unmarshaller production:

~~~java
@Bean
Jaxb2Marshaller ordersMarshaller() {
    Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
    marshaller.setContextPath("com.example.orders.schema");
    marshaller.setSchemas(
            new ClassPathResource("xsd/orders-v1.xsd"));
    return marshaller;
}

@Bean
WebServiceTemplate ordersTemplate(Jaxb2Marshaller ordersMarshaller) {
    WebServiceTemplate template =
            new WebServiceTemplate(ordersMarshaller);
    template.setDefaultUri("https://soap.example.test/orders");
    return template;
}
~~~

Request expectations nên kiểm:
- Global element name/QName.
- Namespace URI, child qualification.
- Element sequence và required fields.
- Optional/nil behavior.
- Decimal/date-time lexical forms.
- Enum value và repeated elements.

Response assertions nên kiểm collection size/order, decimal precision, absent vs nil, unknown enum/element behavior và namespace/version. Không chỉ assert DTO khác null.

Không tự sửa generated JAXB classes; thay đổi XSD cần regenerate model và kiểm wire output.

## 9. SOAP headers và client interceptors

Khi built-in matcher không đủ, custom RequestMatcher có thể đọc SOAP message:

~~~java
mockServer.expect(message -> {
    assertInstanceOf(SoapMessage.class, message);

    SoapMessage soap = (SoapMessage) message;
    assertNotNull(soap.getSoapHeader());

    // Dùng QName/namespace-aware DOM để assert header.
})
.andRespond(withPayload(response));
~~~

Đây là pseudocode; signature/import phụ thuộc API. Đừng chuyển message thành String rồi so prefix text. Dùng QName, namespace-aware DOM hoặc XPath.

ClientInterceptor có thể thêm custom headers/correlation IDs, ký/mã hóa WS-Security request, validate response, log metadata redacted và chuẩn hóa lỗi. Mock có thể chứng minh interceptor được gọi và message được thay đổi. Nó không chứng minh signature/certificate tương thích với peer ngoài; phải test bằng real test keys/certificates và implementation phù hợp.

Không log password, token, SignatureValue, private key hoặc dữ liệu nhạy cảm trong matcher/CI output.

## 10. SOAP versions, endpoint versions và actions

Nếu hỗ trợ SOAP 1.1 và SOAP 1.2, tạo test riêng theo message factory/binding. Kiểm Envelope namespace, Fault model, SOAPAction/action parameter, headers, mustUnderstand, WSDL binding và response.

Contract v1/v2 nên có template/marshaller/URI hoặc routing rõ. Không validate payload v1 bằng schema v2 rồi suy ra compatibility.

## 11. Retry, timeout và idempotency

Mock server có thể mô phỏng sequence lỗi tạm thời rồi thành công, Fault hoặc connection failure. Tách biệt:
- Application retry policy.
- HTTP transport retry.
- SOAP Fault retryability.
- Idempotency.
- Timeout/cancellation.
- Connection recovery.

Không retry mọi SOAP Fault; business Fault như invalid order thường không retry. Với side effects, retry có thể tạo duplicate nếu server đã xử lý nhưng response bị mất. Dùng idempotency key/correlation theo contract.

Mock kiểm số lần WebServiceTemplate invocation; transport retry nội bộ cần test với HTTP sender/server thật.

## 12. Cô lập mock server và tránh flaky tests

Tạo MockWebServiceServer trong BeforeEach để mỗi test có expectations độc lập:

~~~java
@BeforeEach
void setUp() {
    mockServer = MockWebServiceServer.createServer(template);
}
~~~

Gọi verify sau mỗi test. Nếu nhiều tests song song dùng cùng singleton WebServiceTemplate/mock state, expectations có thể cạnh tranh. Tạo context/template riêng hoặc tắt parallel execution cho nhóm tests này. Thông thường tạo server mới mỗi test an toàn hơn reuse.

## 13. Các lỗi client cần test

Ngoài payload XML, cần mô phỏng:
- SOAP Fault theo code/detail.
- Response không có body.
- QName sai.
- Response không unmarshal được.
- Connection error.
- Timeout/cancellation.
- SOAP version không hợp lệ.
- Missing required response header.
- Enum/element mới.
- Unexpected additional request.

Malformed wire data, true timeout, socket truncation và TLS handshake cần transport tests ngoài mock.

## 14. Error mapping tại adapter layer

SOAP client nên bọc WebServiceTemplate để business layer không phụ thuộc trực tiếp Spring-WS exceptions:

~~~java
public class OrdersGateway {
    private final WebServiceTemplate template;

    public OrdersGateway(WebServiceTemplate template) {
        this.template = template;
    }

    public OrderStatus getStatus(String orderId) {
        try {
            GetOrderStatusRequest request =
                    new GetOrderStatusRequest(orderId);
            GetOrderStatusResponse response =
                    (GetOrderStatusResponse)
                    template.marshalSendAndReceive(request);
            return response.getStatus();
        } catch (WebServiceIOException ex) {
            throw new PartnerUnavailableException(ex);
        } catch (SoapFaultClientException ex) {
            throw mapFault(ex);
        }
    }
}
~~~

DTOs, PartnerUnavailableException và mapFault là types do ứng dụng định nghĩa. Map theo exception thực tế của Spring-WS/transport version; không catch mọi exception rồi trả success mặc định.

Test fault mapping, connection error, unmarshal failure và không log token/XML nhạy cảm.

## 15. Fault detail và unknown faults

Nếu WSDL định nghĩa modeled business fault, tạo fixture detail đúng schema và assert domain mapping. Không dùng generic fault cho mọi lỗi khi contract yêu cầu typed detail.

Với SOAP 1.1, kiểm Client/Server fault codes; SOAP 1.2 dùng Sender/Receiver và subcodes. Test theo version. Với unknown fault detail, xác định client có trả generic exception an toàn, giữ correlation ID và không tự retry business faults không retryable hay không.

## 16. Test JUnit hoàn chỉnh phía client

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

class OrdersSoapClientTest {
    private WebServiceTemplate template;
    private MockWebServiceServer mockServer;
    private OrdersSoapClient client;

    @BeforeEach
    void setUp() throws Exception {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.schema");
        marshaller.afterPropertiesSet();

        template = new WebServiceTemplate(marshaller);
        template.setDefaultUri("https://partner.test/soap/orders");

        mockServer = MockWebServiceServer.createServer(template);
        client = new OrdersSoapClient(template);
    }

    @Test
    void sendsExpectedRequestAndMapsResponse() {
        var expected = new StringSource("""
            <ord:GetOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-2001</ord:orderId>
            </ord:GetOrderRequest>
            """);

        var response = new StringSource("""
            <ord:GetOrderResponse
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-2001</ord:orderId>
              <ord:status>PAID</ord:status>
            </ord:GetOrderResponse>
            """);

        mockServer.expect(payload(expected))
                  .andRespond(withPayload(response));

        OrderStatus result = client.getStatus("ORD-2001");

        assertEquals(OrderStatus.PAID, result);
        mockServer.verify();
    }
}
~~~

Đây là mẫu cấu trúc. Project cần DTO/client/domain types, context path, imports và static imports phù hợp version. Nếu client dùng SOAPAction, custom headers hoặc interceptors, thêm expectations tương ứng. Điều cần test là production adapter gọi đúng template đã bind.

## 17. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Bind mock vào template khác | Mock không bắt request | Inject cùng template instance |
| Chỉ test DTO | Không test XML/JAXB | Match payload/QName sau marshal |
| Dùng anything cho mọi request | Payload sai vẫn pass | Expectations cụ thể |
| Không gọi verify | Bỏ sót request không xảy ra | Verify cuối test/lifecycle |
| Shared static mock | Rò state/flaky | Tạo mock mỗi test |
| So prefix literal | False negative | Assert QName |
| Generic Fault cho mọi lỗi | Error mapping thiếu chính xác | Fixtures theo fault/version |
| Coi connection fault là TLS test | Không chứng minh handshake | HTTP/TLS integration |
| Chỉ test success | Bỏ sót error | Negative response matrix |
| Retry mọi exception | Duplicate side effects | Retry classification/idempotency |
| Log SOAP Header | Lộ credentials | Assert metadata/redact |

## 18. Checklist và bài tập

### 18.1. Cấu hình
- [ ] spring-ws-test version đồng bộ runtime.
- [ ] MockWebServiceServer bind đúng WebServiceTemplate production bean.
- [ ] Client adapter nhận chính template đã bind.
- [ ] Default URI/callbacks/interceptors cấu hình trước khi tạo mock.
- [ ] Marshaller/unmarshaller dùng cấu hình production tương đương.
- [ ] Schema/version/namespace được kiểm.

### 18.2. Request và response
- [ ] Positive payload có QName, namespace, sequence và datatype đúng.
- [ ] SOAPAction/custom SOAP headers đúng.
- [ ] Optional/nil/repeated values được kiểm.
- [ ] Response unmarshal thành DTO/domain đúng.
- [ ] SOAP 1.1/1.2 test riêng nếu hỗ trợ.
- [ ] Fault và error mapping có test.
- [ ] Invalid response không bị coi là success.
- [ ] Expectations bao phủ đúng số request/thứ tự.
- [ ] mockServer.verify() được gọi.

### 18.3. Cô lập và phạm vi
- [ ] Mock server mới mỗi test hoặc reset state có kiểm soát.
- [ ] Không chạy song song trên cùng template/mock state.
- [ ] Test không gọi endpoint production ngoài ý muốn.
- [ ] Không log credentials/token/signature/raw PII.
- [ ] Có HTTP integration tests cho content type/transport.
- [ ] Có TLS/mTLS/WSS4J tests riêng khi cần.
- [ ] Có cross-vendor interoperability tests.
- [ ] Không coi mock pass là bằng chứng remote server hoạt động.

### 18.4. Bài tập tự luyện

**Bài 1 — Gắn nhầm template:** Mock server tạo cho template A nhưng adapter dùng template B. Vì sao expectation không match?

**Đáp án:** Mock chỉ chặn request của template được bind; template B dùng transport khác. Bind vào đúng instance adapter nhận.

**Bài 2 — QName:** DTO có orderId đúng nhưng XML marshal sai namespace. Test nào bắt?

**Đáp án:** Request payload/QName matcher sau marshal. DTO field test không đủ.

**Bài 3 — Prefix:** Prefix khác nhưng namespace URI và local name giống. Có nên fail?

**Đáp án:** Không. QName mới quyết định identity; dùng namespace-aware matcher.

**Bài 4 — Verify:** Client method không được gọi nhưng expectation được khai báo. Làm sao phát hiện?

**Đáp án:** Gọi mockServer.verify() để expectation chưa được đáp ứng làm test fail.

**Bài 5 — Connection fault:** Đã chứng minh TLS client certificate đúng?

**Đáp án:** Không. TLS handshake cần HTTPS server/client test thật.

**Bài 6 — Parallel tests:** Hai test dùng chung template/mock. Rủi ro?

**Đáp án:** Expectations/request state cạnh tranh gây flaky. Cô lập template/context hoặc tránh parallel execution.

**Bài 7 — Retry:** Submit timeout rồi retry có thể tạo đơn trùng?

**Đáp án:** Có nếu server đã xử lý nhưng response mất. Dùng idempotency key và retry classification.

**Bài 8 — Unknown enum:** Response mock có enum mới. Cần assert gì?

**Đáp án:** Kiểm unknown-value behavior theo binding/runtime policy, không chỉ assert object khác null.

**Ghi nhớ:** MockWebServiceServer chỉ có giá trị khi bind vào **chính WebServiceTemplate mà SOAP client sử dụng** và expectations kiểm tra message sau khi JAXB/callback/interceptors chuẩn bị. Dùng request matchers cụ thể, response creators cho success/Fault, verify số lần/thứ tự request và cô lập mock theo test. Mock pass chứng minh client behavior ở ranh giới Spring-WS; HTTP, TLS/mTLS, WS-Security, timeout, server-side XSD validation và interoperability liên vendor vẫn cần test ở tầng tương ứng.
