# Tái sử dụng WebServiceTemplate sau cấu hình và điều kiện an toàn luồng

**`WebServiceTemplate`** là thành phần trung tâm của SOAP client trong **Spring Web Services (Spring-WS)**. Nó quản lý quy trình tạo thông điệp, marshal request, gửi qua transport, chạy client interceptors, đọc response, xử lý SOAP Fault và unmarshal dữ liệu trả về. Một câu hỏi triển khai rất thực tế là: *có thể inject một `WebServiceTemplate` singleton vào nhiều service và gọi đồng thời từ nhiều thread không?*

**Có, sau khi đã cấu hình hoàn chỉnh và khi tất cả thành phần phụ thuộc được chia sẻ cũng an toàn luồng.** Tài liệu Spring-WS nêu rõ `WebServiceTemplate` *thread-safe once configured* với điều kiện dependencies cũng thread-safe; các dependency chuẩn của Spring-WS được thiết kế cho mô hình đó. Tuy nhiên, điều này **không có nghĩa** mọi JAXB object, `ClientInterceptor` tự viết, callback có state, HTTP client tùy biến hay thông tin người dùng gắn vào template đều trở nên thread-safe.

Bài thuộc chương **Máy khách Spring-WS** của module `SPRING_WEB_SERVICES`, đặt trong bối cảnh phát triển SOAP **contract-first** với XSD/WSDL, JAXB/OXM, endpoint, SOAP Fault, interceptor, XML security, WS-Security và chứng chỉ. Ta thiết kế một client tra cứu đơn hàng dùng chung `WebServiceTemplate`, nhưng giữ dữ liệu request/response và metadata riêng cho từng lần gọi, rồi mở rộng sang timeout, TLS/mTLS và kiểm thử đồng thời trong tích hợp doanh nghiệp.

Các ví dụ hướng tới Spring-WS 4.x, Spring Framework 6+/Jakarta JAXB và Java 17+. API minh họa thuộc Spring-WS; Spring Boot có thể cung cấp `WebServiceTemplateBuilder` nhưng không tự tạo sẵn **một `WebServiceTemplate` bean duy nhất** cho mọi ứng dụng. Các ví dụ có type giả định sẽ được chú thích rõ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phát biểu **đúng điều kiện** để tái sử dụng một `WebServiceTemplate` giữa nhiều request/threads.
2. Tách **configuration state dùng chung** khỏi **per-invocation state** (JAXB DTO, SOAP Header, callback, `MessageContext`, connection).
3. Khai báo một `WebServiceTemplate` bean đã cấu hình đầy đủ với marshaller, URI mặc định, interceptors và message sender.
4. Thực hiện calls tới URI/action khác nhau **bằng tham số của method**, không thay đổi setter trên shared template.
5. Nhận diện các lỗi race condition ở custom interceptor, callback, JAXB object, marshaller phụ trợ và TLS credential.
6. Phân biệt tính thread-safe của template với throughput, connection pooling, timeout, authentication và bảo đảm idempotency.
7. Thiết kế stress/integration tests chứng minh không trộn payload, SOAPAction, correlation ID, principal và response giữa các lời gọi đồng thời.
8. Đánh giá điều kiện phải tách riêng nhiều template cho các đối tác, SOAP versions hoặc cấu hình bảo mật khác nhau.

## 1. Bài toán: nhiều luồng cùng gọi GetOrder

Một dịch vụ nội bộ cần gửi SOAP tới đối tác để tra cứu `GetOrder`. Bên trong ứng dụng:

- Worker A gọi `GetOrder(orderId="ORD-A")` cho đối tác X.
- Worker B gọi `GetOrder(orderId="ORD-B")` cũng qua đối tác X.
- Worker C đồng thời gọi đối tác X bằng một correlation ID khác.
- Các request dùng chung cấu hình XSD/WSDL, endpoint URL, marshaller và truststore, nhưng **không được trộn thông tin từng người gọi**.

Payload SOAP minh họa:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soap:Body>
    <o:GetOrderRequest>
      <o:orderId>ORD-A</o:orderId>
    </o:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

XSD contract-first tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:o="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

  <xs:element name="GetOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="state" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

WSDL 1.1 document/literal định nghĩa operation `GetOrder` dùng các global elements trên, có thể có SOAPAction `urn:example:orders:v1:GetOrder` trong binding. Trên đường truyền, mã `orderId` của A và B là **dữ liệu request**, tuyệt đối không nằm trong cấu hình chung của `WebServiceTemplate`.

Một kiến trúc tốt:

~~~mermaid
flowchart TD
    A["Worker A<br/>GetOrder ORD-A"] --> C["OrdersSoapGateway singleton"]
    B["Worker B<br/>GetOrder ORD-B"] --> C
    D["Worker C<br/>GetOrder ORD-C"] --> C
    C --> T["WebServiceTemplate<br/>đã cấu hình, dùng chung"]
    T --> O["Marshaller / Unmarshaller<br/>cấu hình bất biến"]
    T --> I["ClientInterceptors<br/>thread-safe"]
    T --> S["MessageSender / HTTP pool<br/>quản lý đồng thời"]
    T --> M["Mỗi invocation:<br/>message, callback, connection, response"]
    M --> X["SOAP Partner Service"]
~~~

Mỗi lời gọi có request payload object, SOAP message, callback/metadata và kết quả **riêng**; phần dùng chung là chiến lược/configuration đã được chuẩn bị một lần.

## 2. Thế nào là “thread-safe once configured”?

### 2.1. Câu trả lời đúng gồm hai điều kiện

Tài liệu Spring-WS mô tả `WebServiceTemplate` **thread-safe sau khi cấu hình**, với điều kiện **mọi dependencies cũng thread-safe**. Đây là bảo đảm theo *giai đoạn sử dụng*:

1. **Configuration phase:** tạo instance, set message factory, marshaller/unmarshaller, URI, sender, interceptors, fault resolver và policy liên quan.
2. **Publication/use phase:** bean đã được Spring khởi tạo và công bố; các thread chỉ gọi các phương thức thực hiện request, **không thay đổi shared configuration**.

Không nên hiểu nó là “bất cứ lúc nào gọi setter đều an toàn đồng thời”. `setDefaultUri(...)`, `setInterceptors(...)`, `setMarshaller(...)`, `setUnmarshaller(...)` hoặc `setMessageSender(...)` là các thao tác thay đổi cấu hình dùng chung; tài liệu **không bảo đảm** dùng chúng đồng thời với `marshalSendAndReceive(...)` sẽ tạo behavior nhất quán.

### 2.2. Thread-safe không giống immutable

Một instance `WebServiceTemplate` có các setter và các thành phần bên trong có thể thay thế. Vì vậy nó **không phải immutable object** theo kiểu Java `record`. Tuy nhiên, ứng dụng có thể áp dụng **quy ước bất biến sau khởi tạo** bằng cách:

- Chỉ tạo/cấu hình instance trong Spring `@Bean` factory hoặc qua builder khi startup.
- Inject bằng constructor vào service/gateway, không expose setter qua business API.
- Không giữ reference để “đổi template tạm thời” khi xử lý request.
- Nếu cần đổi certificate/endpoint/sender do cấu hình vận hành, thực hiện **tái cấu hình có kiểm soát và công bố instance mới**, không sửa giữa các calls đang chạy.

### 2.3. Phạm vi của lời cam kết thread-safe

| Thành phần | Có thể dùng chung không? | Điều kiện |
| --- | --- | --- |
| `WebServiceTemplate` | **Có** | Sau cấu hình và dependencies thread-safe |
| Spring `@Service`/gateway dùng template | **Có** | Không giữ state của từng call trong field mutable |
| `Jaxb2Marshaller` bean | Thường có thể | Cấu hình xong, xem custom adapters/listeners/handlers |
| `WebServiceMessageFactory` chuẩn | Có theo hợp đồng framework | Không chia sẻ **message instance** |
| `WebServiceMessageSender` chuẩn | Có theo thiết kế framework | Connection pool, timeout, TLS được cấu hình đúng |
| Custom `ClientInterceptor` | **Phải đánh giá** | Không có per-call mutable fields dùng chung |
| Custom `WebServiceMessageSender` | **Phải đánh giá** | Đúng hợp đồng concurrency và connection lifecycle |
| JAXB `Marshaller` / `Unmarshaller` trực tiếp | **Không mặc định** | Jakarta JAXB runtime objects thường không thread-safe |
| JAXB request/response DTO mutable | **Không nên chia sẻ** | Mỗi invocation tạo object graph riêng |
| `SoapMessage` hoặc `MessageContext` | **Không chia sẻ giữa các calls** | Chúng thuộc một lần trao đổi |
| Callback chứa mutable fields | Không nếu chia sẻ bừa bãi | Tạo callback mới hoặc bảo đảm immutable/stateless |
| `SoapFaultClientException`/response result | Không cần chia sẻ | Mỗi call xử lý độc lập |

**Điểm tinh tế về JAXB:** `JAXBContext` thường được thiết kế để dùng lại; còn `jakarta.xml.bind.Marshaller` và `Unmarshaller` **không có bảo đảm thread-safe tương đương**. `Jaxb2Marshaller` của Spring là lớp quản lý binding; với đường hoạt động thông thường, nó tạo các JAXB marshaller/unmarshaller thích hợp cho mỗi lần dùng, nhưng một `XmlAdapter`, `ValidationEventHandler` hoặc custom listener gắn vào cấu hình có thể mang state và phá vỡ giả định. Đừng tự lưu một JAXB `Marshaller` duy nhất làm field rồi cho mọi thread gọi `marshal` đồng thời.

## 3. WebServiceTemplate thực hiện gì trong mỗi invocation?

`WebServiceTemplate` không lấy một SOAP Envelope “toàn cục” rồi thay `orderId`. Quy trình điển hình cho mỗi call:

1. Xác định đích URI từ tham số method hoặc cấu hình `defaultUri`/`DestinationProvider`.
2. Tạo `WebServiceConnection` qua message sender.
3. Tạo `WebServiceMessage` request mới từ message factory.
4. Marshal request payload sang XML rồi gọi `WebServiceMessageCallback` nếu có.
5. Chạy `ClientInterceptor.handleRequest(...)`.
6. Gửi request, nhận response trên connection.
7. Phân loại response bình thường, SOAP Fault hoặc transport error theo cấu hình.
8. Chạy callback response/fault của client interceptors, và fault resolver khi phù hợp.
9. Unmarshal response thành result object hoặc báo lỗi.
10. Cleanup connection/interceptor theo lifecycle, không giữ message hoặc stream qua calls.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Thread A
    participant B as Thread B
    participant T as Shared WebServiceTemplate
    participant F as MessageFactory
    participant S as MessageSender
    participant P as SOAP Partner

    A->>T: marshalSendAndReceive(reqA, callbackA)
    B->>T: marshalSendAndReceive(reqB, callbackB)
    T->>F: New message for A
    T->>F: New message for B
    T->>S: Connection for A
    T->>S: Connection for B
    T->>P: SOAP request A
    T->>P: SOAP request B
    P-->>T: SOAP response B
    P-->>T: SOAP response A
    T-->>B: resultB
    T-->>A: resultA
~~~

Sơ đồ thể hiện các calls có thể **hoàn thành khác thứ tự bắt đầu** mà vẫn không được trộn response. Connection pooling có thể tái sử dụng TCP connections **theo cơ chế của HTTP client**, không đồng nghĩa có thể dùng chung một mutable `WebServiceConnection` cho hai calls đồng thời.

### 3.1. Điều gì không nằm trong `WebServiceTemplate`?

Template **không** tự quyết định:

- Caller đã xác thực có quyền xem `ORD-A` không.
- Dữ liệu JAXB có hợp với quy tắc kinh doanh hay không.
- Có được retry operation có side effect khi mạng timeout không.
- Một SOAP Fault có ý nghĩa rollback DB hay không.
- Mật khẩu/chứng chỉ bên gửi được phép chia sẻ giữa các tenant hay không.

Các quyết định này cần hợp đồng WSDL/XSD, use case, security policy, sender/TLS và retry logic riêng.

## 4. Cấu hình một lần rồi inject: ví dụ Spring

Một cấu hình thông dụng với Java/Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;

@Configuration(proxyBeanMethods = false)
public class OrdersSoapClientConfig {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.contract.v1");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate ordersWebServiceTemplate(
            Jaxb2Marshaller ordersMarshaller,
            ClientInterceptor ordersClientInterceptor) {

        WebServiceTemplate template =
            new WebServiceTemplate(ordersMarshaller);

        template.setDefaultUri(
            "https://partner.example.test/soap/orders");
        template.setInterceptors(
            new ClientInterceptor[] { ordersClientInterceptor });

        // Nếu cần HTTPS/mTLS, pooling, timeout: cấu hình
        // message sender chuyên dụng TẠI ĐÂY, trước khi publish.
        // template.setMessageSender(configuredSender);

        return template;
    }
}
~~~

`ClientInterceptor ordersClientInterceptor` là bean do ứng dụng cung cấp (mục 8 sẽ có ví dụ). Constructor `WebServiceTemplate(Marshaller)` sử dụng cùng marshaller làm unmarshaller khi object triển khai cả hai interface, như `Jaxb2Marshaller`. Đường dẫn `contextPath` phải tương ứng package JAXB mà XJC sinh từ XSD; nếu JAXB root là named type không có `@XmlRootElement`, cần `JAXBElement` và `ObjectFactory`.

**Chốt:** code cấu hình template chỉ chạy khi tạo bean, không chạy lại mỗi lần gọi SOAP. Khi ứng dụng dùng nhiều đối tác, dùng bean name/`@Qualifier` để tránh inject nhầm cấu hình.

### 4.1. Spring Boot và WebServiceTemplateBuilder

Spring Boot hỗ trợ `spring-boot-starter-webservices`. Theo tài liệu Boot, Boot có thể tự cấu hình `WebServiceTemplateBuilder`, nhưng **không tự cấp một singleton `WebServiceTemplate` chung** vì mỗi ứng dụng thường phải tùy biến sender, JAXB binding và endpoint.

Có thể tạo bean template bằng builder trong `@Configuration`. Trong các phiên bản Boot hiện hành, builder cung cấp những setter/builder methods tương ứng như `setMarshaller`, `setUnmarshaller`, `setDefaultUri` hoặc cấu hình message sender. **Kiểm tra API builder của phiên bản Boot đang dùng**, vì cú pháp và cơ chế cấu hình HTTP client có thể thay đổi qua major versions.

Điều không nên làm là gọi `builder.build()` ở **mọi business request** chỉ vì builder sẵn có. Nếu các calls cùng một partner và cấu hình không đổi, hãy build một lần thành bean và reuse; điều này tránh tạo cấu hình mới không cần thiết và đơn giản hóa quản trị connection pool/certificate.

### 4.2. Gateway chỉ giữ dependency, không giữ request state

~~~java
import org.springframework.stereotype.Service;
import org.springframework.ws.client.core.WebServiceTemplate;

@Service
public final class OrdersSoapGateway {

    private final WebServiceTemplate template;

    public OrdersSoapGateway(WebServiceTemplate ordersWebServiceTemplate) {
        this.template = ordersWebServiceTemplate;
    }

    // Các method sẽ tạo payload/callback riêng từng call.
}
~~~

Nếu có nhiều template beans, sử dụng `@Qualifier("ordersWebServiceTemplate")` hoặc bean cấu hình rõ ràng. Đừng khai báo fields như `private GetOrderRequest currentRequest;`, `private String currentTraceId;` hoặc `private String currentSoapAction;` trong singleton gateway.

## 5. Chọn URI, SOAPAction và Header theo từng lời gọi

### 5.1. Một URI cố định: dùng defaultUri

Nếu chỉ kết nối một endpoint cố định, có thể gọi:

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-A");

Object raw = template.marshalSendAndReceive(
    request,
    new SoapActionCallback("urn:example:orders:v1:GetOrder"));
~~~

`SoapActionCallback` thuộc `org.springframework.ws.soap.client.core.SoapActionCallback`. `request` ở đây giả định JAXB root class sinh từ global element `GetOrderRequest`. Không chia sẻ `request` với invocation khác. Cần kiểm tra kiểu `raw` dựa trên generated response class/`JAXBElement` thực tế.

### 5.2. Nhiều endpoint, nhưng không thay defaultUri khi đang xử lý

**Anti-pattern có race condition:**

~~~java
// SAI nếu template shared và các requests chạy đồng thời.
public Object send(String endpointUri, Object payload) {
    template.setDefaultUri(endpointUri); // Mutates shared configuration!
    return template.marshalSendAndReceive(payload);
}
~~~

Timeline:

~~~text
Thread A: setDefaultUri("https://partner-a.test/ws")
Thread B: setDefaultUri("https://partner-b.test/ws")
Thread A: marshalSendAndReceive(reqA)
          └── Có thể gửi đến partner-b thay vì partner-a
~~~

**Cách đúng:** truyền URI vào overload của method:

~~~java
public Object send(
        String endpointUri,
        Object payload,
        String soapAction) {

    return template.marshalSendAndReceive(
        endpointUri,
        payload,
        new SoapActionCallback(soapAction));
}
~~~

`marshalSendAndReceive(String uri, Object request, WebServiceMessageCallback callback)` là API của `WebServiceTemplate`. Nó không cần sửa `defaultUri`. URI nên đến từ **cấu hình/allowlist đích được tin cậy**, không phải URL tùy ý mà SOAP caller đưa vào, nếu không ứng dụng có thể gặp rủi ro SSRF hoặc gửi chứng chỉ/credentials nhầm đối tác.

### 5.3. Callback riêng cho mỗi request

Khi cần gửi cả SOAPAction và correlation ID trong **SOAP Header**, dùng một callback chỉ nắm các giá trị **đã chuẩn hóa và dành riêng cho lời gọi**:

~~~java
import javax.xml.namespace.QName;

import org.springframework.ws.client.core.WebServiceMessageCallback;
import org.springframework.ws.soap.SoapMessage;

private static final QName CORRELATION_QNAME =
    new QName("urn:example:orders:meta:v1", "CorrelationId");

public WebServiceMessageCallback callbackFor(
        String soapAction,
        String correlationId) {

    // Hai biến capture là các String immutable.
    return message -> {
        if (!(message instanceof SoapMessage soap)) {
            throw new IllegalStateException("SOAP message required");
        }

        soap.setSoapAction(soapAction);
        soap.getSoapHeader()
            .addHeaderElement(CORRELATION_QNAME)
            .setText(correlationId);
    };
}
~~~

Đoạn code là **method minh họa** trong class gateway/helper; cần imports/cấu hình như dự án thật. `message` truyền tới callback là **message riêng của invocation hiện tại**. Lambda không ghi vào `template`, không lưu `correlationId` trong mutable field và không dùng một `SoapHeaderElement` được tái sử dụng.

Đối với dữ liệu Header từ bên ngoài, phải giới hạn length/format và chống log injection. Nếu WSDL/policy yêu cầu `mustUnderstand`, WS-Addressing hoặc WS-Security, dùng đúng API/chính sách cho những Header đó; đừng tùy ý thêm Header rồi xem như đối tác sẽ hiểu.

### 5.4. Không trộn SOAPAction giữa calls

Giả sử hai operation cùng dùng một URI:

~~~java
template.marshalSendAndReceive(
    uri,
    getOrderRequest,
    callbackFor("urn:example:orders:v1:GetOrder", traceA));

template.marshalSendAndReceive(
    uri,
    cancelOrderRequest,
    callbackFor("urn:example:orders:v1:CancelOrder", traceB));
~~~

Hai callbacks độc lập giúp SOAPAction và correlation Header không phụ thuộc thứ tự thực thi giữa threads. Việc SOAPAction đúng **không thay thế** payload QName và XSD validation; nếu contract dùng WS-Addressing `wsa:Action`, đó là một thông tin khác trong SOAP Header, cần callback/chính sách tương ứng.

## 6. JAXB và dữ liệu request/response: per-call là lựa chọn an toàn

### 6.1. JAXB DTO sinh từ XSD thường mutable

Từ XSD `GetOrderRequest`, XJC có thể sinh JAXB class với setter:

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId(orderId);
~~~

Tạo **mỗi request một instance**. Không giữ:

~~~java
// SAI: cùng một request DTO có thể bị các threads ghi đè.
private final GetOrderRequest reusedRequest =
    new GetOrderRequest();

public Object getOrder(String orderId) {
    reusedRequest.setOrderId(orderId);
    return template.marshalSendAndReceive(reusedRequest);
}
~~~

Thread A có thể đặt `ORD-A`, thread B đặt `ORD-B` trước khi marshaller đọc object graph của A; kết quả là hai SOAP requests mang cùng dữ liệu hoặc dữ liệu lai. Tính thread-safe của `WebServiceTemplate` **không bảo vệ state bên trong object được truyền vào**.

### 6.2. JAXB live list có cùng rủi ro

JAXB-generated classes thường có getter collection trả **live list**:

~~~java
OrderItemsType items = new OrderItemsType();
items.getItem().add(lineA);
items.getItem().add(lineB);
~~~

Không dùng chung cùng `items` instance cho nhiều calls rồi vừa marshal vừa `add/remove`. Object graph phải hoàn thiện trước khi gửi và không bị thay đổi đến khi marshal xong. Với request nhiều item, nên chuyển input bất biến từ application DTO sang một **JAXB object graph mới** tại ranh giới client.

### 6.3. `Jaxb2Marshaller` khác JAXB `Marshaller`

| Thành phần | Cách sử dụng |
| --- | --- |
| `JAXBContext` | Khởi tạo tốn chi phí, thường nên tái sử dụng |
| `jakarta.xml.bind.Marshaller` | Không mặc định thread-safe; không chia sẻ một instance mutable giữa threads |
| `jakarta.xml.bind.Unmarshaller` | Tương tự; không chia sẻ trực tiếp nếu không có cơ chế riêng |
| Spring `Jaxb2Marshaller` | Dùng bean đã cấu hình, triển khai marshalling/unmarshalling cho template |
| JAXB DTO và `JAXBElement` | Mỗi lần gọi tạo root/graph riêng |
| Custom `XmlAdapter`/listener | Đánh giá riêng nếu chúng được chia sẻ và có state |

`Jaxb2Marshaller` sử dụng `JAXBContext` để tạo các thành phần JAXB cần thiết. Nếu cấu hình schema validation, event handlers, adapters, listeners hoặc callback có state, phải đảm bảo chính chúng không phá vỡ thread-safety. Không gọi các setter thay đổi `contextPath`, `classesToBeBound`, schema hoặc adapters của marshaller khi calls đang chạy.

### 6.4. Trường hợp `JAXBElement`

Nếu XSD khai báo global element `GetOrderRequest` trỏ tới named type `GetOrderRequestType`, object type có thể không có `@XmlRootElement`. Khi đó:

~~~java
ObjectFactory factory = new ObjectFactory();

GetOrderRequestType payloadValue = new GetOrderRequestType();
payloadValue.setOrderId("ORD-A");

JAXBElement<GetOrderRequestType> root =
    factory.createGetOrderRequest(payloadValue);

Object response = template.marshalSendAndReceive(
    root,
    new SoapActionCallback("urn:example:orders:v1:GetOrder"));
~~~

`ObjectFactory` và các type này là mã giả định đã sinh từ **một biến thể XSD** với named type; không dùng đồng thời với anonymous type của mục 1 mà không điều chỉnh contract. `JAXBElement` gắn QName cho root; nó không làm object graph trở nên immutable. Mỗi invocation vẫn tạo object và wrapper riêng.


## 7. `ClientInterceptor`: điểm rủi ro khi tự viết middleware

`ClientInterceptor` chạy trong `WebServiceTemplate` trước/sau việc gửi nhận SOAP. Nhiều teams dùng interceptor để gắn Header, thêm WS-Security, đo latency, kiểm tra lỗi hoặc ghi log. Vì interceptor thường được **đăng ký một lần** trên shared template, một custom interceptor có state từng request là nguồn race condition phổ biến.

### 7.1. API lifecycle client interceptor

| Callback | Khi nào | Trách nhiệm gợi ý |
| --- | --- | --- |
| `handleRequest(MessageContext)` | Trước khi request được gửi | Chuẩn bị metadata, ghi mốc đo latency, kiểm tra Header |
| `handleResponse(MessageContext)` | Sau khi nhận non-fault response, trước khi xử lý payload | Đo response, kiểm tra policy, tracing |
| `handleFault(MessageContext)` | Khi nhận SOAP Fault, trước fault resolution | Metric/fault code/correlation |
| `afterCompletion(MessageContext, Exception)` | Kết thúc invocation theo lifecycle | Cleanup tài nguyên nếu interceptor tham gia |

Với `ClientInterceptor`, các callback sau được gọi cho interceptor mà `handleRequest` đã hoàn tất thành công theo hợp đồng API. `handleRequest` trả `false` có thể chặn chuỗi xử lý; đừng giả định endpoint phía server vẫn nhận request. Exception sớm ở connection/message factory có thể thay đổi callbacks được chạy; cần test đường fault/transport của phiên bản đang dùng.

### 7.2. Anti-pattern: lưu request ID vào field của interceptor

~~~java
// SAI: interceptor được nhiều threads dùng chung.
public final class BrokenCorrelationInterceptor
        extends ClientInterceptorAdapter {

    private String currentRequestId;

    @Override
    public boolean handleRequest(MessageContext context) {
        currentRequestId = newId();
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext context) {
        log.info("Finished {}", currentRequestId);
        return true;
    }
}
~~~

Luồng A có thể ghi `ID-A`, luồng B ghi `ID-B` rồi `handleResponse` của A đọc `ID-B`. Logs sai, và nguy hiểm hơn nếu field này mang token hoặc tenant identity rồi bị đưa vào message của request khác.

### 7.3. Lưu thông tin theo `MessageContext` của invocation

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.client.support.interceptor.ClientInterceptorAdapter;

public final class DurationInterceptor
        extends ClientInterceptorAdapter {

    private static final String START_NANOS =
        DurationInterceptor.class.getName() + ".startNanos";

    @Override
    public boolean handleRequest(MessageContext context) {
        context.setProperty(START_NANOS, System.nanoTime());
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Exception ex) {
        Object value = context.getProperty(START_NANOS);
        if (value instanceof Long start) {
            long elapsedNanos = System.nanoTime() - start;
            // Đưa elapsedNanos vào metrics registry thread-safe.
            // Không ghi vào một mutable field per-request.
        }
        context.removeProperty(START_NANOS);
    }
}
~~~

`MessageContext` được cấp cho **một lần trao đổi thông điệp**, nên property ở đó không trộn với invocation khác. Code trên minh họa đo thời gian, cần thêm metrics implementation phù hợp và bảo đảm xử lý riêng các nhánh exception rất sớm.

Nếu interceptor đặt MDC (SLF4J `MDC.put(...)`) vào thread-local, phải cleanup đúng lifecycle (kể cả khi `handleRequest` ném exception **trước khi trả `true`**); MDC không tự lan tới worker threads. **`MessageContext` property không tự biến thành HTTP/SOAP Header**: muốn gửi ra ngoài phải viết Header lên `SoapMessage` của call đó.

### 7.4. Các dependency của interceptor cũng phải an toàn

Có thể interceptor không có field `currentRequestId` nhưng lại dùng:

- `SimpleDateFormat` static mutable (không thread-safe) thay vì `DateTimeFormatter`.
- Một `StringBuilder` instance dùng chung để dựng Header.
- Một custom `XmlAdapter` hoặc security handler lưu token/nonce hiện tại ở field.
- Một mutable `HashMap` làm cache không đồng bộ.
- Một custom audit logger ghi vào buffer dùng chung không kiểm soát.

Thread-safe là **thuộc tính của toàn bộ cây dependency**, không chỉ class có annotation hoặc template. Với thiết kế logging, dùng metrics/tracing libraries thread-safe và bỏ dữ liệu nhạy cảm khỏi raw SOAP logs.

## 8. Message sender, connection pool và timeout

`WebServiceTemplate` ủy quyền transport cho `WebServiceMessageSender`. Tài liệu Spring-WS cung cấp các sender chuẩn. Hệ thống thật có thể sử dụng sender HTTP mặc định hoặc sender tích hợp Apache HttpClient theo phiên bản, cũng như cấu hình HTTPS, proxy và connection pool.

### 8.1. Ba khái niệm cần phân biệt

| Khái niệm | Cách dùng | Không được hiểu nhầm |
| --- | --- | --- |
| **Template** | Reuse cấu hình SOAP client giữa calls | Không có nghĩa chỉ có một request chạy tại một thời điểm |
| **Message sender / HTTP client** | Quản lý kết nối mạng, timeouts, TLS, pool | Không mặc định vô hạn concurrency hoặc retry |
| **Per-call connection** | Đại diện một lần gửi/nhận thực tế | Không giữ một mutable connection làm field và chia sẻ giữa threads |

Một HTTP connection pool thread-safe có thể tái sử dụng socket tuần tự theo HTTP client, nhưng từng request vẫn phải được gán đúng connection/response. **Pool shared** và **request shared** là hai điều khác nhau.

### 8.2. Các cấu hình nên cố định trước khi gọi

- Connect timeout, read/response timeout và thời gian chờ lấy connection từ pool.
- Pool max-total và max-per-route, idle eviction/connection TTL theo client.
- TLS truststore/keystore, mTLS client certificate, hostname verification.
- HTTP proxy, DNS và policy chuyển hướng (redirect) nếu có.
- Truyền dữ liệu lớn/MTOM attachment limits và buffer/streaming constraints.
- Fault resolver, request tracing, security interceptor, URI theo môi trường.

Những tên API cụ thể phụ thuộc sender/HTTP client và Spring Boot version. Ví dụ Spring Boot có hỗ trợ cấu hình sender/timeout qua `WebServiceTemplateBuilder`; **không copy các setter của HttpClient thế hệ cũ** sang client mới mà không kiểm tra compile/runtime behavior.

### 8.3. Pool không tự làm hệ thống nhanh vô hạn

Nếu có 300 tasks đồng thời nhưng HTTP pool chỉ cho phép 20 connections đến đối tác, phần còn lại có thể chờ, timeout hoặc thất bại. Shared template vẫn **an toàn luồng**, nhưng throughput có thể không đạt yêu cầu.

Cần đo:

- Số cuộc gọi đồng thời đang chạy, queue wait time.
- Time-to-connect, time-to-first-byte và tổng latency.
- Tỷ lệ SOAP Fault vs transport timeout.
- Connection pool exhaustion, stale connections, TLS handshake latency.
- XML/JAXB CPU và kích thước payload.

Thường nên có **bounded concurrency**, timeout thực tế, backpressure, bulkhead/circuit breaker nếu nghiệp vụ cần, và retry có giới hạn/jitter. Đừng “sửa” pool exhaustion bằng cách tạo một `WebServiceTemplate` mới cho mỗi request; điều đó có thể tạo **nhiều connection pools** khó kiểm soát.

### 8.4. Shutdown và đời sống resource

Nếu ứng dụng quản lý một HTTP client/pool riêng và inject nó vào message sender, cần cấu hình lifecycle để đóng pool khi application context dừng. Đồng thời phải xác định thời điểm drain các requests đang chạy khi triển khai lại hoặc thay chứng chỉ.

Tạo template singleton **không đồng nghĩa** pool sẽ tự đóng đúng lúc trong mọi cách tự cấu hình. Cần dựa trên lifecycle của sender/HTTP client thực tế, không tự khẳng định Spring luôn xử lý mọi resource tùy biến.

## 9. TLS, mTLS và WS-Security khi có nhiều người gọi

Một template có thể gửi nhiều SOAP requests đồng thời tới **cùng một đối tác và cùng một security profile**. Tuy nhiên, không nên thay các security settings dùng chung theo thông tin của từng tenant/request.

### 9.1. Phân biệt ba mức bảo mật

| Mức | Ví dụ | Cách cấu hình an toàn |
| --- | --- | --- |
| **TLS server authentication** | Trust CA/certificate của đối tác, hostname verification | SSL context/HTTP sender cấu hình một lần |
| **mTLS client identity** | Client certificate/keystore đại diện ứng dụng hoặc tenant | Sender/HTTP client có key material phù hợp, không đổi trong lúc call |
| **WS-Security message security** | XML signature, token, timestamp, encryption | Client security interceptor/callback/crypto được cấu hình theo policy |

Lỗi certificate/trust xảy ra ở transport có thể **không có SOAP Fault**. Lỗi WS-Security có thể tạo SOAP Fault theo security policy nhưng không nhất thiết đi qua cùng fault resolver của ứng dụng.

Ở phía Spring-WS client, `org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor` có thể được đăng ký như một `ClientInterceptor` để thực hiện WS-Security (ví dụ UsernameToken, signature, timestamp hoặc encryption theo policy). **Cấu hình interceptor, crypto, callback handler và credentials trước khi đưa template vào sử dụng**; nếu callback handler tùy biến có mutable state thì phải đánh giá thread-safety riêng. Đừng thay `securementActions`, keystore hoặc credential dùng chung trước từng lần gọi.

### 9.2. Sai lầm: thay certificate/token trên shared object lúc runtime

~~~text
Thread A: muốn gửi thay mặt Tenant-A
          → sửa shared sender keystore/credentials thành A
Thread B: muốn gửi thay mặt Tenant-B
          → sửa shared sender keystore/credentials thành B
Thread A: gửi message
          → có nguy cơ dùng danh tính B hoặc policy khác
~~~

Nếu các đối tác/tenant dùng **mTLS certificate khác nhau**, nên dùng **các sender/pool hoặc template riêng theo security profile** (và quản lý số lượng profile) hoặc một cơ chế chọn credentials *per connection* được thư viện chứng minh thread-safe. Không chỉ dùng `setMessageSender(...)`/đổi shared keystore field trước mỗi request.

Với SOAP Header bearer-like token hoặc UsernameToken chứa credential thay đổi theo call, dùng một cơ chế *per-invocation* của thư viện security được cấu hình đúng, **không lưu currentPassword/currentUser trong singleton interceptor**. Token phải gắn đúng invocation và không bị log; không tự viết XML Signature từ string concatenation.

### 9.3. Rotation có kiểm soát

Khi đối tác thay certificate hoặc cần đổi truststore:

1. Chuẩn bị security configuration mới và xác minh chain/hostname/trust.
2. Tạo sender/HTTP client/SSL context mới theo cấu hình đã duyệt.
3. Tạo hoặc công bố template/gateway mới ở điểm chuyển đổi có kiểm soát.
4. Cho các requests cũ kết thúc theo chính sách và đóng pool cũ.
5. Test SOAP Fault, TLS handshake, expiry/rotation và rollback configuration.

Không suy rằng gọi một setter trên `WebServiceTemplate` đang được hàng trăm threads dùng là **atomic hot-reload**.

## 10. Dynamic routing, DestinationProvider và ranh giới tin cậy

`WebServiceTemplate` có thể dùng `defaultUri`, `DestinationProvider` hoặc URI được truyền trực tiếp tới overload của method. Cách nào cũng cần tuân theo một chính sách **destination trust**.

### 10.1. Khi nào tách nhiều templates?

| Tình huống | Cách thiết kế đề xuất |
| --- | --- |
| Cùng partner, một SOAP version, một marshaller, một security profile | Một shared template |
| Cùng partner, nhiều operations/SoapActions, cùng cấu hình | Một shared template, callback/action per call |
| Hai host tin cậy, cùng security profile và JAXB binding | Có thể một template + explicit URI, cân nhắc tách observability |
| Hai đối tác dùng hai XSD/JAXB contexts khác nhau | Templates/marshallers riêng giúp rõ hợp đồng |
| SOAP 1.1 và SOAP 1.2 qua message factories khác nhau | Thường dùng templates riêng theo binding |
| Nhiều client certificates/WS-Security profiles | Templates/senders riêng theo profile hoặc chiến lược thread-safe được kiểm chứng |
| Muốn thay URL qua mỗi call | Truyền URI vào method; **không** đổi `setDefaultUri` runtime |
| Endpoint từ input không đáng tin | **Không gửi trực tiếp**: cần allowlist/mapping cấu hình chống SSRF |

### 10.2. URI từ người dùng là nguy cơ SSRF

Một API nhận `targetUrl` từ request rồi gọi:

~~~java
template.marshalSendAndReceive(targetUrl, requestPayload);
~~~

có thể gửi SOAP request và credentials đến host ngoài ý muốn, ví dụ metadata endpoint, internal admin service hoặc attacker-controlled server. **Thread-safe không bảo đảm security-safe**.

Giải pháp: ánh xạ một `partnerCode` đã xác thực sang URI được cấu hình/allowlist; kiểm tra scheme, host, port, TLS, redirects/DNS và policy mạng theo threat model. Với đối tác có credentials đặc thù, route tới **đúng gateway/template dành cho partner đó** để tránh credential cross-leak.

### 10.3. DestinationProvider tùy biến cũng phải thread-safe

`DestinationProvider` giúp chọn đích động, nhưng nếu provider chứa một field mutable `currentTenantUrl` được nhiều threads thay đổi, race condition vẫn tồn tại. Khi routing thực sự phụ thuộc từng request, ưu tiên overload có URI explicit thay vì shared mutable provider, hoặc xây routing strategy với context/inputs tường minh và kiểm tra chính sách.

## 11. Lỗi SOAP, lỗi mạng và retry khi template được dùng chung

Một shared `WebServiceTemplate` có thể đồng thời trả success cho A, SOAP Fault cho B, timeout cho C. Các kết quả phải được xử lý theo từng invocation.

### 11.1. SOAP Fault không phải kết quả JAXB bình thường

~~~java
try {
    Object raw = template.marshalSendAndReceive(
        endpointUri,
        request,
        callbackFor(SOAP_ACTION, correlationId));

    return mapSuccess(raw);

} catch (SoapFaultClientException ex) {
    // ex.getFaultCode(), getFaultStringOrReason(),
    // ex.getSoapFault().getFaultDetail() nếu có.
    throw mapKnownFault(ex);

} catch (WebServiceIOException ex) {
    // Transport I/O problem; kết quả phía server có thể chưa rõ.
    throw mapTransportFailure(ex);
}
~~~

`mapSuccess`, `mapKnownFault` và `mapTransportFailure` là mã ứng dụng minh họa; cần import `SoapFaultClientException` và `WebServiceIOException` từ các package Spring-WS tương ứng. Không catch tất cả exceptions rồi lập tức retry vô hạn hoặc chia sẻ một mutable `lastFailure` trên gateway.

SOAP Fault thường được xử lý qua `SoapFaultMessageResolver` mặc định của template; với resolver khác hoặc cấu hình đặc thù, kết quả có thể khác. Phân biệt **SOAP Fault có mã/detail** với **transport timeout không có thông điệp SOAP tin cậy**.

### 11.2. Rủi ro retry ở thao tác có side effect

`GetOrder` dạng tra cứu thường có thể retry nếu policy cho phép. `SubmitOrder` hoặc `CancelOrder` có side effect: request ban đầu có thể **đã commit** trên server trước khi client timeout. Vì thế:

- Dùng `requestId`/idempotency key ổn định cho cùng một ý định nghiệp vụ.
- Retry đúng cùng key và payload theo hợp đồng hoặc gọi `GetOrderStatus`.
- Sử dụng backoff + jitter, giới hạn số attempts/tổng timeout.
- Không thay retry policy globally trên template theo từng người gọi.
- Phân biệt `Client/Sender` fault do sai request với `Server/Receiver` và network failures.
- Không suy rằng `Receiver` nghĩa là transaction phía server đã rollback.

### 11.3. Circuit breaker và cache đặt ở đâu?

Có thể đặt resilience ở **gateway/application layer** bao quanh calls:

~~~text
Application service
    ↓
Retry policy cho operation cụ thể
    ↓
Bulkhead / rate limiter / circuit breaker
    ↓
OrdersSoapGateway
    ↓
Shared WebServiceTemplate
    ↓
MessageSender pool → Partner
~~~

Retry policy có thể khác theo operation dù dùng cùng template. Đừng đóng gói một biến `retryCount` mutable vào template rồi cho nhiều calls ghi đè; dùng per-invocation retry context/metrics.

## 12. Async calls, context propagation và lifetime của data

Tái sử dụng template với `CompletableFuture`, scheduler, batch processing hay executor là hợp lý nếu dependencies an toàn luồng. Điều nguy hiểm là **truyền nhầm object mutable/request-scoped** sang worker.

### 12.1. Anti-pattern: giữ SOAP message hoặc context ngoài invocation

~~~java
// Không nên: truyền một MessageContext của call đã kết thúc
// hoặc một JAXB request bị thread khác mutate.
executor.submit(() -> processLater(capturedMessageContext));
~~~

`MessageContext`, SOAP message, response stream hoặc connection thuộc một exchange và không phải durable state. Không giữ chúng sau khi call hoàn tất.

### 12.2. Snapshot dữ liệu tối thiểu

~~~java
record OrderLookupTask(String orderId, String correlationId) {}

OrderLookupTask task = new OrderLookupTask(orderId, correlationId);

CompletableFuture<GetOrderResponse> future =
    CompletableFuture.supplyAsync(
        () -> ordersGateway.getOrder(task.orderId(),
                                    task.correlationId()),
        executor);
~~~

Ví dụ cần `ordersGateway.getOrder(...)` được hiện thực theo contract của mục 5. `OrderLookupTask` là immutable snapshot; callback của gateway tạo JAXB DTO và SOAP message mới ở worker thread. Nếu task cần bền vững qua restart, hãy dùng queue/outbox/workflow thay vì chỉ `CompletableFuture` in-memory.

### 12.3. Principal, MDC và tracing

MDC/`ThreadLocal`, security context và transactions không nhất thiết tự lan sang thread khác. Nếu gateway cần danh tính đã xác thực, lựa chọn tenant hoặc correlation ID, hãy dùng propagation mechanism chính thức hoặc immutable metadata DTO đã được cấp phép và kiểm tra. Không truyền raw token/private key vào executor payload không kiểm soát.

Shared template không tự cung cấp “sticky” user session. **Không lưu `currentTenant`, `lastSoapAction` hay `currentRequestId` trong field của template/interceptor**.


## 13. Kiểm thử thread safety: test điều gì mới đủ?

Một test gọi `template.marshalSendAndReceive(...)` thành công một lần **không chứng minh thread-safe**. Phải chạy nhiều lời gọi trùng thời gian và kiểm tra dữ liệu **không trộn giữa những invocation**, đồng thời kiểm soát lỗi transport/connection pool.

### 13.1. Ma trận kiểm thử

| Kịch bản | Kỳ vọng | Khía cạnh được kiểm tra |
| --- | --- | --- |
| 100 calls `GetOrder` với 100 `orderId` khác nhau | Mỗi response khớp đúng orderId request | JAXB DTO không shared mutable |
| Hai operations `GetOrder`/`CancelOrder` xen kẽ | SOAPAction và payload QName đúng từng call | Callback per invocation |
| Nhiều correlation IDs | Header đúng request, không lẫn trace | Interceptor/callback state |
| Đổi prefix XML nhưng giữ QName | Client unmarshal đúng | Namespace/XML interoperability |
| Hai tenants với profile bảo mật khác nhau | Không gửi credential A sang B | Template/sender isolation |
| Một call nhận SOAP Fault, calls khác success | Fault chỉ ảnh hưởng call lỗi | Fault resolver và per-call result |
| Một call timeout, calls khác hoàn thành | Không trộn exception/response | Transport isolation |
| HTTP pool nhỏ hơn concurrency | Queue/timeouts theo cấu hình, không deadlock | Pool capacity |
| Request chứa JAXB live list | Không trộn/mất items giữa calls | Object graph per-call |
| Dữ liệu có `JAXBElement` root | Mỗi call giữ đúng QName | JAXB marshalling |
| URI explicit A/B xen kẽ | Không request nào gửi sai host | Không `setDefaultUri` runtime |
| Client cert rotation có kiểm soát | Không cross-tenant/partial config | Lifecycle/security |
| Interceptor cleanup MDC | Request sau không mang trace cũ | Thread reuse |
| 1.1 SOAPAction và 1.2 Action/binding | Đúng protocol mỗi template | SOAP version isolation |
| Stress với payload lớn | Memory/latency có giới hạn | Resource use và backpressure |

### 13.2. Unit test cho gateway: không mutate template

Có thể mock `WebServiceTemplate` và verify đúng overload chứa URI/action callback, nhưng test này **chỉ kiểm tra cách sử dụng API**, chưa chứng minh HTTP/JAXB hoạt động:

~~~java
@Test
void usesExplicitUriRatherThanChangingSharedDefaultUri() {
    WebServiceTemplate template = mock(WebServiceTemplate.class);
    OrdersSoapGateway gateway = new OrdersSoapGateway(template);

    // Gọi gateway.getOrder(...) qua test fixture/mocks thích hợp.
    // verify(template, never()).setDefaultUri(anyString());
    // verify(template).marshalSendAndReceive(
    //    eq("https://partner.example.test/soap/orders"),
    //    any(), any(WebServiceMessageCallback.class));
}
~~~

Với code hoàn chỉnh, cần thực thi call, dựng fixture và xử lý response mock theo JAXB type thực tế. Các comment mô tả **điều cần assert**, không là một unit test tự chạy độc lập.

### 13.3. Integration test concurrent calls

Dùng SOAP test server hỗ trợ concurrent requests và echo `orderId` đã nhận về response tương ứng. Có thể chạy qua HTTP test server ở localhost, với **một shared template bean thật** và một marshaller bean thật:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);
CountDownLatch start = new CountDownLatch(1);

List<Callable<GetOrderResponse>> tasks =
    IntStream.range(0, 80)
        .mapToObj(i -> (Callable<GetOrderResponse>) () -> {
            start.await();
            return gateway.getOrder(
                "ORD-" + i,
                "corr-" + i);
        })
        .toList();

List<Future<GetOrderResponse>> futures =
    tasks.stream().map(pool::submit).toList();

start.countDown();

try {
    for (int i = 0; i < futures.size(); i++) {
        GetOrderResponse response =
            futures.get(i).get(10, TimeUnit.SECONDS);
        assertEquals("ORD-" + i, response.getOrderId());
    }
} finally {
    pool.shutdownNow();
}
~~~

Đây là **khung JUnit/Java concurrency test**, cần các imports `java.util.concurrent.*`, `java.util.stream.IntStream`, `java.util.List`, fixture server và gateway implementation. Timeout 10 giây chỉ là **giới hạn test minh họa**, không phải SLA khuyến nghị. Test server phải có khả năng nhận nhiều requests đồng thời; đừng mặc định mọi mock server/fake transport đều thread-safe.

Ngoài response ID, server thử nghiệm nên **ghi lại và assert** SOAPAction và correlation ID theo từng request, cũng như xác minh không có token/tenant bị lẫn. Nếu chỉ assert result mà không kiểm raw wire message, một số lỗi Header sẽ bị bỏ sót.

### 13.4. `MockWebServiceServer` dùng cho gì?

`MockWebServiceServer` rất phù hợp cho **kiểm thử tuần tự, deterministic** của `WebServiceTemplate`: kiểm tra XML payload, SOAPAction, SOAP Header, fault và response handling. Nhưng không nên mặc định một instance mock server là harness chịu đồng thời cao hay mọi matcher có state đều thread-safe. Đối với race conditions và pool, cần **HTTP server/harness hỗ trợ concurrency thực sự** hoặc custom stub được kiểm chứng thread-safe.

Một bộ test nên gồm:

1. Unit test gateway mapping/binding riêng từng operation.
2. Spring-WS client test với `MockWebServiceServer` cho request/response/fault chuẩn.
3. Integration test có HTTP sender và marshaller thật với nhiều threads.
4. Failure-injection test timeout, disconnect, pool pressure, TLS/cert rotation.
5. Interoperability test với server/client khác stack theo WSDL.

### 13.5. Kiểm thử security riêng biệt

- Một nhóm tests xác minh mTLS certificate đã cấu hình đúng theo partner.
- Nhóm khác xác minh WS-Security signature/token **đúng từng invocation**.
- Không chứng minh security bằng việc chỉ có `wsse:Security` XML element.
- Kiểm tra certificate/keystore rotation không ảnh hưởng requests đang chạy theo policy.
- Đảm bảo token/private key không xuất hiện trong logs, exception hoặc correlation ID.
- Nếu caller không có quyền truy cập một order, test authorization ở **server**, không chỉ phụ thuộc client đã tạo request đúng schema.

## 14. Các anti-pattern thường gặp

| Anti-pattern | Vì sao sai | Giải pháp |
| --- | --- | --- |
| `new WebServiceTemplate()` mỗi lần gọi khi cấu hình giống nhau | Tốn setup, khó quản lý sender/connection pool | Shared, fully configured bean |
| Gọi `setDefaultUri` trước mỗi call | Race giữa các threads | Overload có URI explicit |
| Gọi `setMarshaller` khi app đang chạy | Config nhìn thấy không nhất quán | Thay cấu hình ngoài đường hot path |
| Thay `setInterceptors` giữa các calls | Interceptor chain thay đổi không dự đoán được | Cố định trước startup; versioned config |
| Để `currentRequestId` trong gateway singleton | Cross-call leak | Local variables / `MessageContext` |
| Interceptor chứa `currentUser`/`currentToken` | Cross-tenant security issue | Per-invocation security context hợp lệ |
| Reuse JAXB request object với setter mutable | Request A có thể bị B ghi đè | Tạo JAXB graph riêng từng call |
| Reuse raw JAXB `Marshaller` giữa threads | Không có thread-safety guarantee | `Jaxb2Marshaller` hoặc per-thread/per-call objects đúng thiết kế |
| Chia sẻ `SoapMessage` giữa requests | Header/body bị trộn | Message factory tạo message cho mỗi call |
| Lưu SOAP Header vào shared array rồi thay theo caller | Header mutation giữa calls | Callback riêng mỗi invocation |
| Custom message sender/pool không thread-safe | Response sai hoặc resource lỗi | Sender được chứng minh concurrency-safe |
| Không giới hạn concurrency/timeout | Pool exhaustion và queue tích tụ | Capacity limits, backpressure |
| Coi template thread-safe là TLS/WS-Security đã an toàn | Có thể rò credential/chữ ký | Kiểm security dependencies và profile |
| Gọi user-supplied URL trực tiếp | SSRF và gửi credentials sai host | Allowlist/partner routing |
| Một template cho các bên có client cert khác nhau và sửa shared cert | Cross-tenant identity leak | Tách security profile/sender |
| Retry `SubmitOrder` bằng requestId mới sau timeout | Có thể tạo đơn trùng | Idempotent retry/query |
| Chỉ unit test single-thread | Không phát hiện race, pool exhaustion | Concurrent wire integration tests |

## 15. Quy trình thiết kế client thread-safe

~~~mermaid
flowchart TD
    A["Xác định XSD/WSDL + SOAP binding"] --> B["Xác định partner và security profile"]
    B --> C["Tạo Jaxb2Marshaller / MessageFactory"]
    C --> D["Tạo sender: timeout, TLS, pool"]
    D --> E["Đánh giá ClientInterceptors/custom callbacks"]
    E --> F["Cấu hình WebServiceTemplate một lần"]
    F --> G["Inject singleton gateway"]
    G --> H["Mỗi call: tạo JAXB DTO + callback riêng"]
    H --> I["marshalSendAndReceive với URI/action đúng"]
    I --> J["SOAP Fault/timeout/retry theo operation"]
    J --> K["Concurrent wire tests + fault/security tests"]
~~~

### Checklist review trước production

1. **Hợp đồng:** root QName, SOAPAction/WS-Addressing Action, WSDL binding, SOAP version và JAXB types nhất quán.
2. **Template:** chỉ cấu hình ở startup; không setter mutation trong request path.
3. **Beans:** gateway, template, marshaller, interceptors và sender có scope/lifecycle rõ.
4. **Per-call data:** JAXB object graph, callback, SOAP Header, principal metadata và requestId không shared mutable.
5. **Interceptor:** mọi field và dependency đều thread-safe; tracing/MDC được dọn đúng lifecycle.
6. **Transport:** sender/HTTP pool chịu concurrent requests, có timeout, max connections, cleanup và backpressure.
7. **Security:** certificate/truststore, hostname validation, mTLS và WS-Security được cô lập theo partner/profile.
8. **Routing:** URI đến từ cấu hình/allowlist; không nhận endpoint host tùy ý từ caller.
9. **Fault:** SOAP Fault khác lỗi transport; client đọc detail theo QName và không log credential.
10. **Retry:** query/read operations và commands có tác dụng phụ có policy riêng; idempotency key không bị thay bừa.
11. **Testing:** mock tests, concurrent HTTP tests, failure injection, TLS/WS-Security và Java/.NET interoperability.
12. **Operations:** kế hoạch rotation cấu hình/chứng chỉ, metric pool, latency, timeout và resource cleanup.

## 16. Bài tập vận dụng

**Bài 1 — Race ở defaultUri.** Hai threads A/B cùng dùng một template; A gọi `setDefaultUri(urlA)`, B gọi `setDefaultUri(urlB)` trước khi A gửi request. Hãy mô tả lỗi có thể xảy ra và thay bằng đúng overload `marshalSendAndReceive`.

**Bài 2 — JAXB object graph.** Một singleton gateway giữ `GetOrderRequest request` ở field và chỉ gọi `request.setOrderId(...)` trước khi gửi. Viết lại phương thức để không chia sẻ mutable request.

**Bài 3 — SOAPAction và tracing.** Thiết kế callback tạo mới cho mỗi call, gửi `SoapAction` và `CorrelationId`. Vì sao không lưu hai giá trị này trong field của interceptor singleton?

**Bài 4 — Custom interceptor.** Một `ClientInterceptor` lưu `long startedAtNanos` trong field rồi tính latency ở `handleResponse`. Hãy chuyển sang `MessageContext.setProperty` và xử lý `afterCompletion`.

**Bài 5 — JAXB thread safety.** Phân biệt `JAXBContext`, raw JAXB `Marshaller` và Spring `Jaxb2Marshaller`. Khi nào một custom `XmlAdapter` có thể làm hỏng thread safety dù template dùng chung đúng cách?

**Bài 6 — Security profile.** Hai partners yêu cầu hai mTLS certificates khác nhau và hai truststores khác nhau. Bạn sẽ tách sender/templates hay đổi config của một shared template giữa calls? Giải thích rủi ro credential leakage.

**Bài 7 — Pool capacity.** Có 200 concurrent requests nhưng pool chỉ cho 16 kết nối tới host. Template vẫn thread-safe không? Hệ thống cần kiểm thử timeout, queue và backpressure nào?

**Bài 8 — Retry.** `SubmitOrder` timeout sau khi request được gửi nhưng client không có SOAP response. Vì sao retry bằng `requestId` mới nguy hiểm, và idempotency trên server giải quyết điều gì?

**Bài 9 — Dynamic URL.** Một client nhận `partnerUrl` từ SOAP Body của người gọi và truyền trực tiếp vào template. Rủi ro gì ngoài thread safety? Đề xuất mapping/allowlist.

**Bài 10 — Concurrent test.** Viết integration test gửi 80 calls đồng thời, mỗi call có orderId và correlation ID riêng. Assert những trường nào ở server và client để chứng minh không trộn request, response hoặc Header?

**Bài 11 — Async.** Một background task chụp reference đến JAXB request và `MessageContext` cũ. Vì sao không an toàn? Hãy thiết kế immutable snapshot và tạo payload mới ở worker.

**Bài 12 — SOAP version.** Khi đối tác A dùng SOAP 1.1 và B dùng SOAP 1.2, bạn phải kiểm tra những thành phần nào ngoài việc đổi `SoapAction`? Vì sao hai templates với message factory/binding rõ ràng thường dễ bảo trì hơn?

## Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4 — Client](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): ghi rõ `WebServiceTemplate` *thread-safe once configured* với điều kiện dependencies thread-safe; giới thiệu `WebServiceGatewaySupport` và client API.
- [Spring-WS API 4.1 — WebServiceTemplate](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/client/core/WebServiceTemplate.html): cấu hình marshaller/unmarshaller, sender, URI, interceptors và các overload của `marshalSendAndReceive`.
- [Spring-WS API 4.1 — ClientInterceptor](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/client/support/interceptor/ClientInterceptor.html): callbacks request/response/fault/afterCompletion.
- [Spring-WS API 4.1 — Wss4jSecurityInterceptor](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/security/wss4j2/Wss4jSecurityInterceptor.html): cấu hình bảo mật SOAP và các dependency crypto/callback handler.
- [Spring-WS API 4.1 — WebServiceMessageCallback](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/client/core/WebServiceMessageCallback.html): thay đổi message theo từng invocation.
- [Spring-WS API 4.1 — SoapMessage](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/SoapMessage.html): `setSoapAction` và SOAP Header/Body.
- [Spring Boot Reference — Web Services](https://docs.spring.io/spring-boot/reference/io/webservices.html): `WebServiceTemplateBuilder` và chính sách không tự tạo một singleton template bean.
- [Spring Framework Reference — OXM/JAXB](https://docs.spring.io/spring-framework/reference/data-access/oxm.html): `Jaxb2Marshaller`, JAXB context và marshalling/unmarshalling.

**Ghi nhớ:** **Tái sử dụng một `WebServiceTemplate` đã cấu hình là cách dùng đúng và hiệu quả, nhưng chỉ khi mọi dependency dùng chung cũng an toàn luồng.** Cấu hình template, marshaller, sender, interceptors và security profile **một lần**; tạo JAXB payload, SOAP callback/Header, request metadata và response **riêng cho từng invocation**. Không mutate `setDefaultUri` hoặc credential trong hot path. Kết hợp connection pooling có giới hạn, timeouts, WS-Security/TLS đúng profile, retry idempotent và concurrent integration tests để SOAP client hoạt động ổn định khi nhiều luồng chạy đồng thời.
