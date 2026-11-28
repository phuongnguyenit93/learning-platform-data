# RequestCreator, RequestCreators và tạo yêu cầu từ payload hoặc envelope

Trong kiểm thử máy chủ Spring Web Services (Spring-WS), **RequestCreator** mô tả cách chuẩn bị một SOAP request đầu vào. Bộ **RequestCreators** cung cấp các factory methods để tạo request từ payload XML, SOAP Header hoặc toàn bộ SOAP Envelope. Chọn đúng creator giúp test tập trung vào endpoint mapping và business payload, hoặc kiểm tra message-level behavior như SOAP version, WS-Addressing, WS-Security và các Header bắt buộc.

Bài này thuộc chương **Kiểm thử máy chủ** của module **SPRING_WEB_SERVICES**. Module phát triển SOAP theo hướng contract-first, do đó test cần bám XSD/WSDL, QName, JAXB mapping, endpoint, interceptor, SOAP Fault và XML security. Payload đúng schema chưa chắc là SOAP message đúng policy: thiếu Header, sai Envelope namespace hoặc thiếu WS-Security có thể khiến request bị từ chối trước khi endpoint chạy.

Công cụ trung tâm là **MockWebServiceClient**, dùng kiểm thử server-side Spring-WS trong application context. Đây là test client in-process: nó dispatch message qua Spring-WS components nhưng **không mở TCP/HTTP socket thật**. Vì vậy nó không chứng minh TLS handshake, reverse proxy, connector limits hay MIME wire behavior.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò RequestCreator và RequestCreators.
2. Tạo request từ payload bằng withPayload.
3. Tạo request có SOAP Header hoặc full SOAP Envelope.
4. Phân biệt payload, Header và Envelope.
5. Dùng MockWebServiceClient qua endpoint mapping/interceptors.
6. Tạo custom RequestCreator cho Header động và test fixtures.
7. Chọn XML Source và quản lý stream lifecycle.
8. Viết tests cho SOAP 1.1/1.2, WS-Addressing, SOAP Fault và WS-Security.
9. Biết giới hạn của in-process tests và khi cần HTTP integration tests.
10. Xác nhận request bị từ chối không tạo business side effects.

## 2. RequestCreator là gì?

RequestCreator đại diện cho **cách dựng WebServiceMessage đầu vào**. Test client gọi creator để chuẩn bị request, sau đó Spring-WS dispatch qua endpoint mappings, interceptors, endpoint adapter và endpoint.

~~~mermaid
sequenceDiagram
    participant T as Test
    participant C as MockWebServiceClient
    participant R as RequestCreator
    participant M as WebServiceMessage
    participant D as Spring-WS dispatcher
    participant E as Endpoint
    T->>C: sendRequest(creator)
    C->>R: createRequest(message)
    R->>M: ghi payload/header/envelope
    C->>D: dispatch message
    D->>D: mapping + interceptors
    D->>E: invoke endpoint
    E-->>C: response message
    C-->>T: ResponseActions
~~~

| Lớp | Nội dung | Ví dụ |
|---|---|---|
| Payload | Phần tử nghiệp vụ bên trong SOAP Body | SubmitPaymentRequest |
| SOAP Header | Metadata điều khiển/ràng buộc | wsa:Action, wsse:Security |
| SOAP Envelope | Envelope, Header tùy chọn và Body | Toàn bộ SOAP message |

Nếu chỉ kiểm JAXB/business logic, payload creator thường đủ. Nếu kiểm mustUnderstand, WS-Addressing, WS-Security, SOAP role hoặc version, cần tạo Header/Envelope phù hợp.

## 3. MockWebServiceClient trong Spring-WS test

Ví dụ tạo client từ application context:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.context.ApplicationContext;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.ws.test.server.MockWebServiceClient;

class PaymentEndpointTest {
    @Autowired
    ApplicationContext applicationContext;

    MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(
            applicationContext
        );
    }
}
~~~

Đây là skeleton; test context phải được khởi tạo bằng Spring test framework hoặc Spring Boot test để inject ApplicationContext. Context cần chứa endpoint, mappings, adapters và interceptors cần kiểm.

Ví dụ gửi payload:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;
import org.springframework.xml.transform.StringSource;

client.sendRequest(
    withPayload(new StringSource("""
        <pay:CheckStatusRequest
            xmlns:pay="urn:example:health:v1"/>
        """))
).andExpect(noFault());
~~~

Ví dụ minh họa luồng cơ bản. Package/static imports và API cần khớp Spring-WS test artifact của dự án. Assertion noFault chỉ kiểm không có SOAP Fault; chưa chứng minh response fields, security policy hay transport.

### 3.1. Test dependency

Dùng Spring-WS test dependency cùng version line với Spring-WS runtime. Nếu dự án theo Spring Boot BOM, để BOM quản lý phiên bản tương thích. Không tự kéo test artifact của Spring-WS release mới vào dự án cũ khi Spring Framework/WSS4J còn ở version line khác.

## 4. RequestCreators.withPayload

withPayload(Source) tạo request có Source làm payload trong SOAP Body. Đây là creator phù hợp khi test quan tâm payload root QName, JAXB mapping, endpoint mapping kiểu PayloadRoot, schema validation và business behavior.

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import org.springframework.xml.transform.StringSource;

RequestCreator request = withPayload(
    new StringSource("""
        <pay:GetPaymentRequest
            xmlns:pay="urn:example:payments:v1">
            <pay:paymentId>PAY-100</pay:paymentId>
        </pay:GetPaymentRequest>
        """)
);
~~~

Với request dynamic, tạo Source mới cho mỗi test/invocation. Không dùng lại một stream đã consume hoặc closed. Creator chỉ nên giữ immutable fixture data, không giữ message instance.

### 4.1. QName quan trọng hơn prefix

Hai payload có thể có cùng QName dù prefix khác nhau:

~~~xml
<pay:GetPaymentRequest xmlns:pay="urn:example:payments:v1">
    <pay:paymentId>PAY-100</pay:paymentId>
</pay:GetPaymentRequest>
~~~

~~~xml
<x:GetPaymentRequest xmlns:x="urn:example:payments:v1">
    <x:paymentId>PAY-100</x:paymentId>
</x:GetPaymentRequest>
~~~

Prefix pay và x khác nhau, nhưng namespace URI và local name giống nhau. Endpoint mapping phải khớp QName, không nên phụ thuộc prefix nếu contract không yêu cầu serialization cụ thể. Bỏ namespace URI hoặc đổi sang namespace gần giống sẽ tạo QName khác.

### 4.2. Khi nào withPayload không đủ?

Payload-only creator không thích hợp khi test cần chứng minh:

- wsa:Action nằm trong SOAP Header.
- wsse:Security được tạo và kiểm bởi WSS4J.
- SOAP 1.1 và SOAP 1.2 Envelope namespace khác nhau.
- mustUnderstand, actor/role và SOAP Header processing.
- Fault code/reason theo SOAP version.
- MIME/MTOM parts được serialize đúng.

## 5. Thêm SOAP Header bằng custom RequestCreator

RequestCreators 4.1.x không cung cấp factory method withSoapHeader(Source). Khi cần thêm Header bên cạnh payload, tạo custom RequestCreator; hoặc dùng withSoapEnvelope cho fixture cố định có cả Header và Body. Ví dụ dưới đây dùng custom creator để dựng WS-Addressing Action:

~~~java
import org.springframework.xml.transform.StringSource;

client.sendRequest(
    new PartnerRequestCreator(
        "urn:example:payments:GetPayment",
        new StringSource("""
        <pay:GetPaymentRequest
            xmlns:pay="urn:example:payments:v1">
            <pay:paymentId>PAY-100</pay:paymentId>
        </pay:GetPaymentRequest>
        """)
    )
).andExpect(noFault());
~~~

Không giả định API có overload nhận nhiều creators. Trong Spring-WS 4.1.x, RequestCreators tập trung vào withPayload và withSoapEnvelope; Header riêng cần custom creator hoặc full Envelope fixture.

Header phải ở đúng SOAP Header và dùng namespace URI chuẩn. wsa:Action đặt trong Body không tương đương Action Header. Custom tenant/correlation header cũng cần QName và version rõ ràng.

### 5.1. SOAP role và mustUnderstand

Tạo các case riêng cho Header được xử lý, Header bắt buộc nhưng không có interceptor phù hợp, Header dành cho role khác và duplicate Header bị contract cấm. Kỳ vọng không phải lúc nào cũng là noFault; với Header không hiểu nhưng mustUnderstand, server có thể phải trả Fault.

## 6. RequestCreators.withSoapEnvelope

withSoapEnvelope(Source) cho test cung cấp **toàn bộ SOAP Envelope**. Dùng khi cần kiểm soát SOAP version, Header, Body, namespace, role hoặc cấu trúc message.

~~~java
import static org.springframework.ws.test.server.RequestCreators.withSoapEnvelope;
import org.springframework.xml.transform.StringSource;

client.sendRequest(
    withSoapEnvelope(new StringSource("""
        <soap:Envelope
            xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:wsa="http://www.w3.org/2005/08/addressing"
            xmlns:pay="urn:example:payments:v1">
            <soap:Header>
                <wsa:Action>urn:example:payments:GetPayment</wsa:Action>
            </soap:Header>
            <soap:Body>
                <pay:GetPaymentRequest>
                    <pay:paymentId>PAY-100</pay:paymentId>
                </pay:GetPaymentRequest>
            </soap:Body>
        </soap:Envelope>
        """))
).andExpect(noFault());
~~~

Đây là SOAP 1.1 vì Envelope namespace là http://schemas.xmlsoap.org/soap/envelope/. SOAP 1.2 dùng http://www.w3.org/2003/05/soap-envelope và binding/Content-Type khác. Không chỉ thay HTTP Content-Type; message factory và Envelope phải tương ứng.

Envelope creator hữu ích cho Header ordering, Envelope malformed, SOAP version mismatch, mustUnderstand, role/actor, WS-Addressing và SOAP security fixtures. Parser có thể từ chối request trước endpoint mapping; test cần xác nhận không có business side effect.

## 7. Custom RequestCreator

Khi factory methods không đủ, implement RequestCreator để chuẩn bị WebServiceMessage. Hợp đồng method và package cần kiểm theo Spring-WS test version; ví dụ khung:

~~~java
import java.io.IOException;
import javax.xml.transform.Source;
import javax.xml.transform.TransformerFactory;
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.WebServiceMessageFactory;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.test.server.RequestCreator;
import org.springframework.xml.transform.StringSource;

public final class PartnerRequestCreator implements RequestCreator {
    private final Source payload;

    private final String action;

    public PartnerRequestCreator(String action, Source payload) {
        this.action = action;
        this.payload = payload;
    }

    @Override
    public WebServiceMessage createRequest(
            WebServiceMessageFactory messageFactory)
            throws IOException {
        WebServiceMessage message =
            messageFactory.createWebServiceMessage();
        if (!(message instanceof SoapMessage soapMessage)) {
            throw new IOException("SOAP message implementation required");
        }
        try {
            var transformer =
                TransformerFactory.newInstance().newTransformer();
            var header = new StringSource(
                "<wsa:Action xmlns:wsa=\"http://www.w3.org/2005/08/addressing\">"
                + action + "</wsa:Action>");
            transformer.transform(header, soapMessage.getSoapHeader().getResult());
            transformer.transform(payload, soapMessage.getPayloadResult());
            return message;
        } catch (javax.xml.transform.TransformerException ex) {
            throw new IOException("Could not create SOAP request", ex);
        }
    }
}
~~~

Ví dụ minh họa RequestCreator API của Spring-WS 4.x: nhận WebServiceMessageFactory và **trả WebServiceMessage**. Nó yêu cầu SOAP message implementation. Action ở đây là test value tĩnh; nếu nhận giá trị tùy ý, hãy ghi Header bằng XML writer để escape đúng, không nối chuỗi raw. Kiểm API SoapMessage/Result của implementation thực tế.

Một custom creator nên:

1. Chỉ mutate message được truyền vào invocation.
2. Kiểm implementation và fail rõ nếu không hỗ trợ.
3. Ghi Header đúng QName/role.
4. Ghi Body từ Source mới hoặc có thể đọc lại.
5. Không giữ WebServiceMessage, Transformer hay Result ở field shared.
6. Không bỏ qua lỗi ghi Header/Body.

Nếu chỉ cần một fixed full envelope, withSoapEnvelope thường dễ đọc và ít code hơn.

## 8. Source và stream lifecycle

Spring-WS dùng XML transformation abstractions từ JDK như javax.xml.transform.Source/Result. Các Source phổ biến:

| Source | Dùng khi | Lưu ý |
|---|---|---|
| StringSource | XML fixture ngắn | Dễ đọc, namespace tường minh |
| StreamSource | InputStream/Reader/file | Quản lý đóng stream |
| DOMSource | Có DOM Document sẵn | Tăng memory, DOM mutable |
| SAXSource | Có SAX pipeline | Parser phải harden |
| StAXSource | XML streaming | Support phụ thuộc stack |

StreamSource có thể one-shot. Không reuse cùng InputStream qua nhiều request nếu đã consume/close. Tạo Source mới cho mỗi invocation, hoặc giữ XML string bất biến và dựng Source mới. Với XML không tin cậy, parser phải chống DTD/external entities; fixture test cũng không cần external schema references.

## 9. Contract-first payload tests

Với contract XSD/WSDL, kiểm payload root QName, element order, required/optional elements, type và version.

~~~xml
<pay:SubmitPaymentRequest xmlns:pay="urn:example:payments:v1">
    <pay:requestId>REQ-100</pay:requestId>
    <pay:tenantId>TENANT-A</pay:tenantId>
    <pay:accountId>ACC-100</pay:accountId>
    <pay:amount>250.00</pay:amount>
    <pay:currency>VND</pay:currency>
</pay:SubmitPaymentRequest>
~~~

Chia tests thành payload hợp lệ, thiếu required element, sai decimal type, sai namespace/local name, element order sai và version QName cũ/mới. Không cần nhúng toàn WSDL vào mọi test payload, nhưng cần contract tests cho generated JAXB types, QName và schema validation config.

## 10. SOAP 1.1 và SOAP 1.2

| Version | Envelope namespace | HTTP media type phổ biến |
|---|---|---|
| SOAP 1.1 | http://schemas.xmlsoap.org/soap/envelope/ | text/xml |
| SOAP 1.2 | http://www.w3.org/2003/05/soap-envelope | application/soap+xml |

Với withSoapEnvelope, fixture phải có đúng namespace. Test riêng SOAP 1.1 và SOAP 1.2 khi service công bố hai bindings. Kiểm Fault serialization, Action handling và mustUnderstand semantics. Một Envelope SOAP 1.1 không thành SOAP 1.2 chỉ bằng việc đổi HTTP header.

## 11. WS-Addressing và custom context headers

Ví dụ Header fragment:

~~~xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ctx="urn:example:context:v1">
    <wsa:Action>urn:example:payments:GetBalance</wsa:Action>
    <ctx:CorrelationId>corr-test-001</ctx:CorrelationId>
    <ctx:ClientApplication>partner-billing</ctx:ClientApplication>
</soap:Header>
~~~

Đây là fragment, không phải Envelope hoàn chỉnh. Trong test, đặt fragment vào full Envelope bằng withSoapEnvelope hoặc ghi vào SOAP Header trong custom RequestCreator. Header tenant/correlation phải được kiểm nguồn, namespace, duplicate values và signature coverage nếu nó ảnh hưởng quyết định bảo mật. Một tenant ID do caller khai báo không chứng minh quyền truy cập tenant.

## 12. UsernameToken và XML Signature test fixtures

Khi server yêu cầu WS-Security, payload-only request có thể bị từ chối vì thiếu wsse:Security. Positive tests nên dùng WSS4J test client/config tạo token hợp lệ. Negative tests nên bao gồm:

- Không có Security Header.
- UsernameToken thiếu Username/Password.
- PasswordText sai hoặc token profile không cho phép.
- Nonce replay hoặc Created hết hạn.
- Token đúng nhưng thiếu XML Signature khi policy yêu cầu.
- Signature hợp lệ toán học nhưng không ký required Body/Header.
- Certificate không được tin.
- Duplicate IDs/signature wrapping.

Không tạo ds:Signature giả với SignatureValue placeholder rồi dùng làm positive test. Dùng WSS4J/XML security library tạo chữ ký thật bằng test key; receiver xác minh trust và signed parts. Không dùng key test trong production.

## 13. Kết hợp creators và dynamic headers

Một test cần correlation ID, WS-Addressing và partner metadata có thể dùng full envelope fixture, composition API nếu version hỗ trợ, hoặc custom creator. Tạo Source mới cho mỗi invocation, tránh sửa XML fixture dùng chung bằng string replacement. Dùng XML writer/Marshaller cho values động để escape XML đúng, chống malformed input.

Tách test cho Action, correlation, tenant và Security Header. Khi tất cả đều nằm trong một happy-path test lớn, failure khó chỉ ra phần nào gây lỗi.

## 14. ResponseActions và assertions

Sau sendRequest, MockWebServiceClient trả ResponseActions để kiểm response. Các matcher thường dùng để kiểm noFault, payload, XPath, SOAP Header hoặc Fault; API cụ thể phụ thuộc Spring-WS test release.

~~~java
import static org.springframework.ws.test.server.ResponseMatchers.noFault;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

client.sendRequest(
    withPayload(new StringSource("""
        <pay:GetPaymentRequest
            xmlns:pay="urn:example:payments:v1">
            <pay:paymentId>PAY-100</pay:paymentId>
        </pay:GetPaymentRequest>
        """))
)
.andExpect(noFault())
.andExpect(payload(new StringSource("""
    <pay:GetPaymentResponse
        xmlns:pay="urn:example:payments:v1">
        <pay:paymentId>PAY-100</pay:paymentId>
        <pay:status>APPROVED</pay:status>
    </pay:GetPaymentResponse>
    """)));
~~~

Kiểm response theo semantics payload, tránh phụ thuộc indentation/prefix nếu không phải yêu cầu serialization. noFault không đủ khi cần xác minh response field, Header, SOAP version hoặc Fault code.

## 15. Test Fault với request không hợp lệ

Một request có Body thiếu fields có thể phục vụ test validation:

~~~java
client.sendRequest(
    withPayload(new StringSource("""
        <pay:SubmitPaymentRequest
            xmlns:pay="urn:example:payments:v1"/>
        """))
).andExpect(hasFault());
~~~

Đây là fragment, cần static import/matcher theo dependency version. Với contract quan trọng, assert Fault code/reason/detail đã sanitize; không chỉ assert có Fault. Một parser exception, no endpoint mapping hoặc HTTP gateway rejection không nhất thiết là SOAP Fault và không thể mô phỏng đầy đủ chỉ bằng MockWebServiceClient.

## 16. Interceptor chain và request creator

RequestCreator chỉ dựng input; nó không bảo đảm security/validation interceptors đã được bật. ApplicationContext của test phải chứa đúng endpoint mappings, adapters, interceptors và thứ tự registration cần kiểm.

Kiểm interceptor:

- Được đăng ký trong server configuration.
- Chạy ở đúng lifecycle phase.
- Reject malformed/unauthorized request trước business side effect.
- Không log raw credentials/XML.
- Có behavior riêng cho success, response và Fault.
- Không bị loại bỏ bởi test slice quá hẹp.

Một mock test bỏ qua security config có thể pass dù production interceptor chưa được wired. Với policy trọng yếu, dùng full application context integration test.

## 17. MTOM và attachments

withPayload không chứng minh multipart/related MTOM wire format. Attachment tests cần message factory và test fixture có khả năng biểu diễn MIME parts. Cần kiểm:

- SOAP Body có xop:Include đúng cid reference.
- MIME part Content-ID match reference.
- Content-Type/boundary đúng.
- Size/stream lifecycle và missing/duplicate Content-ID.
- Attachment bytes được ký/xác minh theo profile nếu policy yêu cầu.

MockWebServiceClient có thể kiểm logic endpoint nếu message implementation hỗ trợ attachment, nhưng không thay HTTP/MIME integration test qua server/proxy khi cần streaming, chunked transfer và limits.

## 18. MockWebServiceClient không thay HTTP integration test

MockWebServiceClient nhanh và deterministic, nhưng không mở socket. Nó không chứng minh:

- Embedded Tomcat/Jetty connector, port binding và thread pools.
- HTTP 401/403/413, proxy 502/504 hoặc forwarded headers.
- TLS handshake, hostname verification và mTLS.
- Content-Length/chunked transfer/keep-alive.
- MIME multipart streaming qua proxy.
- HTTP connection pools.
- Public WSDL address sau ingress.
- Graceful shutdown với request đang chạy.

Dùng Spring Boot random-port tests hoặc HTTP/TLS/proxy tests tùy mục tiêu. Giữ mock tests cho endpoint mapping, payload semantics và interceptor logic.

## 19. Statelessness và concurrency

RequestCreator test fixtures không nên giữ state theo request trong singleton. Các lỗi thường gặp:

| Lỗi | Triệu chứng | Cách khắc phục |
|---|---|---|
| Reuse StreamSource đã consume | Request lần hai Body rỗng | Tạo Source mới |
| Reuse mutable DOM giữa tests | Flaky/cross-test mutation | Document mới |
| Creator giữ SoapMessage | Header lẫn giữa tests | Chỉ populate message truyền vào |
| Static nonce/timestamp | Replay test sai hoặc hết hạn | Tạo token theo scenario |
| Shared Transformer | Thread-safety không đảm bảo | Tạo theo invocation |
| Test order dependency | Riêng lẻ pass, suite fail | Isolated fixtures |

Creator nên stateless hoặc chỉ giữ immutable values. Không giữ WebServiceMessage, SecurityContext, credentials hay request DTO mutable ở field shared.

## 20. Bộ test theo failure boundary

| Nhóm | Creator | Assertion |
|---|---|---|
| Payload routing | withPayload | Endpoint QName/mapping |
| JAXB contract | withPayload | Required fields/types/namespace |
| WS-Addressing | Header/Envelope | Action/To/MessageID |
| SOAP version | Envelope | Namespace/version |
| WS-Security | Envelope/custom/WSS4J fixture | Token/signature verification |
| SOAP Fault | Payload/Envelope malformed | Fault code/detail |
| MTOM | MIME-capable fixture | Attachment/Content-ID |
| Interceptors | Creator đúng scenario | Validation/security trước business |
| Transport | HTTP client trên server thật | TLS/status/headers/limits |

Test name nên mô tả rõ failure boundary, ví dụ rejectsMissingUsernameTokenBeforeInvokingEndpoint. Không gom mọi behavior vào một test khiến root cause khó định vị.

## 21. Troubleshooting

| Triệu chứng | Nguyên nhân | Hướng kiểm |
|---|---|---|
| Không tìm endpoint | Payload QName/namespace sai | PayloadRoot/XSD |
| Interceptor đòi Header | Dùng withPayload | Header/Envelope creator |
| Action không được nhận | Đặt trong Body hoặc sai namespace | SOAP Header + WSA namespace |
| SOAP 1.2 bị reject | Envelope namespace SOAP 1.1 | Version/message factory |
| XML không parse | StringSource malformed | Validate fixture |
| Fault không như kỳ vọng | Assertion quá rộng | Kiểm Fault code/reason |
| Header duplicate | Nhiều creators ghi cùng QName | Full Envelope/creator composition |
| WS-Security positive fail | Placeholder token/signature | Sinh bằng WSS4J test key |
| Mock pass, HTTP fail | Bỏ qua connector/proxy/TLS | HTTP integration |
| Body lần hai rỗng | Reuse one-shot Source | Factory tạo Source mới |
| Test suite flaky | Shared mutable state | Per-test fixtures |
| MTOM mock pass, partner fail | Không kiểm MIME wire | Raw HTTP multipart test |

## 22. Bài thực hành: tạo request ở ba mức

**Bối cảnh:** SOAP server có GetPayment và SubmitPayment, JAXB types sinh từ XSD. SubmitPayment yêu cầu wsa:Action, UsernameToken và XML Signature trên SOAP Body.

### Nhiệm vụ

1. Dựng test context có MessageDispatcherServlet, endpoint mappings và interceptors.
2. Tạo MockWebServiceClient từ context đúng.
3. Test payload-only GetPayment bằng withPayload.
4. Test SOAP Header Action bằng custom creator; RequestCreators 4.1.x không có withSoapHeader.
5. Tạo SOAP 1.1 full Envelope fixture.
6. Tạo SOAP 1.2 fixture nếu contract có binding đó.
7. Dùng WSS4J test config tạo UsernameToken hợp lệ.
8. Tạo XML Signature thật bằng test certificate và ký required parts.
9. Viết negative test thiếu token, sai password, expired timestamp và unsigned Body.
10. Assert business service không được gọi khi security/validation fail.
11. Assert response payload và SOAP Fault code/reason.
12. Viết custom creator thêm correlation ID động.
13. Test Source/stream không bị reuse sau consume.
14. Test MTOM bằng HTTP thật nếu operation có attachment.
15. Test TLS/proxy/status/headers ngoài MockWebServiceClient.
16. Chạy suite lặp hoặc song song để phát hiện shared mutable fixtures.

### Câu hỏi tự kiểm tra

1. RequestCreator chịu trách nhiệm gì?
2. withPayload khác withSoapEnvelope ra sao?
3. Vì sao withPayload đủ cho endpoint mapping tests?
4. Khi nào phải tạo SOAP Header?
5. wsa:Action nằm ở đâu?
6. SOAP version được quyết định bởi yếu tố nào?
7. Prefix khác nhau có luôn làm endpoint mapping fail?
8. Vì sao namespace URI quan trọng hơn prefix?
9. MockWebServiceClient có mở HTTP socket không?
10. Những gì cần test trên embedded server thật?
11. Khi nào custom creator cần thiết?
12. Vì sao StreamSource có thể không reuse?
13. Positive WS-Security test cần tránh placeholder thế nào?
14. UsernameToken có tự ký Body không?
15. Policy yêu cầu signed Body, test chỉ có UsernameToken đã đủ chưa?
16. MockWebServiceClient có thay MTOM wire test không?
17. Vì sao noFault không đủ trong mọi case?
18. Làm sao chứng minh business method không chạy khi security fail?

### Đáp án tham khảo

| Câu | Trả lời |
|---|---|
| 1 | Chuẩn bị WebServiceMessage đầu vào cho server-side mock client. |
| 2 | Một cái đặt payload vào Body; cái kia cung cấp full Envelope/Header/Body. |
| 3 | Endpoint mapping thường dựa payload root QName. |
| 4 | Khi test WS-Addressing, security, custom metadata, role/mustUnderstand. |
| 5 | Trong SOAP Header theo WS-Addressing namespace. |
| 6 | Envelope namespace/message factory và HTTP binding. |
| 7 | Không nếu QName namespace URI/local name giống. |
| 8 | Prefix chỉ là alias; namespace URI định danh vocabulary. |
| 9 | Không, dispatch in-process trong Spring-WS context. |
| 10 | Connector, HTTP status/headers, TLS, proxy, limits và socket behavior. |
| 11 | Khi cần Header động hoặc setup phức hợp chưa có factory method. |
| 12 | InputStream có thể one-shot và đã consume/close. |
| 13 | Dùng WSS4J tạo token/signature bằng test keys và verifier thật. |
| 14 | Không, XML Signature là action/policy riêng. |
| 15 | Không, cần signed-parts validation. |
| 16 | Không, cần HTTP/MIME integration khi kiểm wire behavior. |
| 17 | Không kiểm chính xác Fault code/detail hoặc security policy. |
| 18 | Verify service mock/spy/repository không được invoke hoặc không commit. |

## 23. Checklist chất lượng cho RequestCreator tests

- [ ] Spring-WS test dependency tương thích runtime.
- [ ] ApplicationContext có endpoint, mapping, adapters và interceptors cần kiểm.
- [ ] MockWebServiceClient được tạo từ đúng context.
- [ ] Payload fixtures bám XSD/QName.
- [ ] withPayload dùng cho body-focused tests.
- [ ] Header đặt trong SOAP Header, không lẫn Body.
- [ ] withSoapEnvelope dùng cho SOAP version/full-message tests.
- [ ] Custom creator compile theo API version và fail rõ khi message implementation khác.
- [ ] Source/stream/DOM không reuse mutable giữa tests.
- [ ] SOAP 1.1/1.2 fixtures dùng đúng Envelope namespace.
- [ ] WS-Addressing Action/To ở đúng namespace/Header.
- [ ] WS-Security positive tests dùng WSS4J test keys thật.
- [ ] Negative tests có missing token, bad signature, unsigned required Body và replay.
- [ ] Business side effects không xảy ra khi request security/contract fail.
- [ ] Response assertions kiểm payload/Fault code/detail theo mục tiêu.
- [ ] MTOM/attachment wire behavior được HTTP test khi cần.
- [ ] HTTP/TLS/proxy/status/headers kiểm ngoài MockWebServiceClient.
- [ ] Không log raw SOAP Header/credentials/PII.
- [ ] Creator không giữ shared mutable request/security state.
- [ ] Test names mô tả failure boundary.

## 24. Tổng kết

**RequestCreator** mô tả cách tạo request message cho server-side Spring-WS test client; **RequestCreators** 4.1.x cung cấp factory methods để dựng request từ payload hoặc full SOAP Envelope. Chọn withPayload khi cần kiểm payload QName, JAXB mapping, endpoint và validation. Chọn withSoapEnvelope khi cần WS-Addressing, SOAP version, role/mustUnderstand, WS-Security hoặc message structure. Nếu chỉ muốn thêm Header, implement custom RequestCreator tạo WebServiceMessage qua WebServiceMessageFactory rồi ghi Header và Body. Không giả định có withSoapHeader hoặc overload ghép creators.

**MockWebServiceClient** kiểm dispatch Spring-WS trong application context nhưng không mở HTTP socket. Nó không thay integration tests cho embedded connector, TLS/mTLS, reverse proxy, HTTP framing, MIME/MTOM wire behavior hoặc public WSDL URL. Một suite tốt kết hợp payload tests, full-envelope/security tests, Fault/negative tests và HTTP integration tests; đồng thời xác nhận request bị từ chối không tạo business side effects.
