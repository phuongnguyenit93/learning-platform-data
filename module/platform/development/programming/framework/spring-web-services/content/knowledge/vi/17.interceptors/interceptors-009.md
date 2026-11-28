# ClientInterceptor và chuỗi xử lý ở phía máy khách

## 1. ClientInterceptor giải quyết vấn đề gì?

Trong Spring Web Services (Spring-WS), một SOAP client thường sử dụng `WebServiceTemplate` để gửi thông điệp đến dịch vụ bên ngoài. `WebServiceTemplate` có thể dùng JAXB/OXM để chuyển đổi Java object ↔ XML, sử dụng SOAP message factory để tạo Envelope và dùng message sender để thực hiện HTTP transport.

Khi một ứng dụng tích hợp nhiều SOAP operation hoặc nhiều đối tác, mỗi lời gọi thường cần thêm một số hành vi chung:

- Gắn correlation ID hoặc các SOAP headers được hợp đồng quy định.
- Áp dụng WS-Security, chữ ký số, timestamp hoặc mã hóa khi cần.
- Thu thập số liệu về request, response, SOAP Fault và thời gian xử lý.
- Kiểm tra dữ liệu, ghi log an toàn và bổ sung chẩn đoán lỗi.
- Phân loại lỗi SOAP Fault mà không để logic nghiệp vụ lặp lại ở từng client method.

Spring-WS cung cấp interface **`ClientInterceptor`** để tham gia vòng đời xử lý thông điệp **ở phía máy khách**. Mỗi interceptor có cơ hội xem hoặc thao tác request trước khi gửi, response khi nhận về, SOAP Fault khi có lỗi và thực hiện dọn dẹp sau lượt xử lý.

Bài thuộc chương **Interceptor** của module **SPRING_WEB_SERVICES**. Chúng ta học riêng về **ClientInterceptor và chuỗi xử lý ở phía máy khách**, đặt trong hướng phát triển SOAP **contract-first** với XSD/WSDL, JAXB, `WebServiceTemplate`, WS-Security, XML security và kiểm thử tương thích khi tích hợp hệ thống doanh nghiệp.

Sau bài học, bạn có thể:

1. Phân biệt `ClientInterceptor` với `EndpointInterceptor` ở server.
2. Giải thích vòng đời `handleRequest`, `handleResponse`, `handleFault` và `afterCompletion`.
3. Khai báo nhiều interceptors trong `WebServiceTemplate` theo thứ tự có chủ đích.
4. Tạo interceptor thêm SOAP Header có QName đúng, lưu correlation ID theo từng lượt gọi.
5. Thu thập metrics/log không làm lộ thông tin nhạy cảm.
6. Phân biệt SOAP Fault với lỗi HTTP/transport, đồng thời hiểu quan hệ với `FaultMessageResolver`.
7. Thiết kế thứ tự WS-Security, logging và tracing phù hợp yêu cầu chữ ký/mã hóa.
8. Viết unit/integration tests dùng `MockWebServiceServer`, kiểm tra thứ tự callback và Fault.
9. Tránh lỗi shared mutable state, xử lý lặp, validation sai phạm vi và lỗi tương thích WSDL/XSD.

## 2. Phân biệt interceptor phía client và server

Hai interface có tên gần nhau nhưng nằm ở hai ranh giới khác nhau:

| Thành phần | Chạy tại | Nhiệm vụ |
|---|---|---|
| `ClientInterceptor` | Ứng dụng **gọi** SOAP service | Theo dõi/chỉnh sửa outbound request và inbound response/Fault |
| `EndpointInterceptor` | Ứng dụng **cung cấp** SOAP service | Xử lý request/response/Fault quanh endpoint server |
| `WebServiceMessageCallback` | Phía client, cho **một lần gọi** | Chỉnh request, ví dụ SOAPAction/headers |
| `FaultMessageResolver` | Phía client, khi xử lý SOAP Fault | Chuyển Fault thành exception hoặc xử lý lỗi theo chính sách |
| `WebServiceMessageSender` | Phía client, tầng transport | HTTP connection, authentication transport, TLS, timeout... |
| `Jaxb2Marshaller` | Client hoặc server | Marshal/unmarshal Java ↔ XML |
| `PayloadValidatingInterceptor` | Chủ yếu server-side endpoint chain | Validation XML payload bằng XSD |

**ClientInterceptor không thay thế endpoint server.** Nó chạy trong client application do `WebServiceTemplate` điều phối; không gắn vào `MessageDispatcherServlet` của nhà cung cấp dịch vụ.

Cũng không nên dùng ClientInterceptor để thực hiện mọi chính sách HTTP networking. Những nhiệm vụ như connection pool, proxy, TLS handshake hoặc connect/read timeout thuộc message sender hoặc HTTP client bên dưới.

## 3. Luồng tổng thể khi gọi SOAP qua WebServiceTemplate

Một lời gọi mẫu:

~~~java
GetOrderResponse response =
    (GetOrderResponse) template.marshalSendAndReceive(
        "https://partner.example.test/ws",
        request
    );
~~~

Bên dưới, logic mức cao gồm:

~~~mermaid
flowchart TD
    A["Code nghiệp vụ client"] --> B["WebServiceTemplate"]
    B --> C["Marshal request bằng JAXB/OXM"]
    C --> D["WebServiceMessageCallback nếu có"]
    D --> E["ClientInterceptor: handleRequest"]
    E --> F{"Tiếp tục gửi?"}
    F -->|"Có"| G["SOAP message sender / HTTP"]
    F -->|"Không"| H["Luồng ngắn mạch / dừng xử lý"]
    G --> I{"Kết quả nhận về"}
    I -->|"SOAP response thường"| J["ClientInterceptor: handleResponse"]
    I -->|"SOAP Fault"| K["ClientInterceptor: handleFault"]
    I -->|"Lỗi transport"| L["Xử lý exception"]
    J --> M["Unmarshaller / response extractor"]
    K --> N["FaultMessageResolver / xử lý Fault"]
    H --> O["afterCompletion nếu đủ điều kiện lifecycle"]
    L --> O
    M --> O
    N --> O
~~~

Sơ đồ mô tả các **điểm can thiệp** chứ không phải hợp đồng tuyệt đối về thứ tự mọi adapter, SOAP fault classifier, callbacks và cleanup trong tất cả phiên bản Spring-WS. Luồng thực tế có những nhánh đặc biệt khi interceptor trả `false`, throw exception, hoặc khi không nhận được SOAP response.

Các nguyên tắc cần phân biệt:

- `handleRequest` làm việc trên **outbound request** trong `MessageContext`.
- `handleResponse` dành cho **inbound response thông thường**.
- `handleFault` dành cho **SOAP Fault response được runtime nhận diện**.
- `afterCompletion` hỗ trợ dọn dẹp/ghi nhận cuối lượt xử lý đã đi qua interceptor theo semantics của framework.
- Lỗi TCP/TLS, timeout hoặc HTTP transport có thể xảy ra mà **không có SOAP Fault hợp lệ**; không mặc định `handleFault` được gọi.

## 4. Hợp đồng XSD/WSDL mẫu để thử client interceptors

Để hiểu rằng một SOAP interceptor không được phá hợp đồng, xét một dịch vụ `GetOrder` có namespace:

~~~text
urn:example:orders:v1
~~~

XSD request/response:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
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
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Request SOAP 1.1:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header/>
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-2048</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Response SOAP 1.1:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderResponse>
            <ord:orderId>ORD-2048</ord:orderId>
            <ord:status>PAID</ord:status>
        </ord:GetOrderResponse>
    </soap:Body>
</soap:Envelope>
~~~

Root payload QNames phải tương ứng:

~~~text
{urn:example:orders:v1}GetOrderRequest
{urn:example:orders:v1}GetOrderResponse
~~~

Interceptor có thể thêm SOAP Header, nhưng **không được tự ý đổi namespace/root payload** hoặc cấu trúc request/response chỉ vì muốn thêm tracing. Những thay đổi XSD/WSDL hoặc SOAP binding đều phải được quản lý theo contract-first.

### 4.1. Header correlation dùng namespace riêng

Giả sử hợp đồng vận hành cho phép SOAP Header:

~~~xml
<com:CorrelationId
    xmlns:com="urn:example:common:v1">
    8f4a2e31-5c3d-4e9b-a833-6dc0a7e22320
</com:CorrelationId>
~~~

QName của header:

~~~text
{urn:example:common:v1}CorrelationId
~~~

Header này khác payload `GetOrderRequest`. Không tự thêm một element `ord:CorrelationId` vào SOAP Body rồi cho rằng client vẫn hợp XSD vì server có thể từ chối phần tử ngoài sequence.

Nếu WSDL/policy yêu cầu header có `mustUnderstand`, WS-Addressing hoặc chữ ký WS-Security, hãy đảm bảo interceptor tạo và bảo vệ header đúng quy tắc đó.

## 5. API ClientInterceptor gồm bốn điểm vòng đời

Interface thuộc package:

~~~java
org.springframework.ws.client.support.interceptor.ClientInterceptor
~~~

Các phương thức tiêu biểu:

~~~java
public interface ClientInterceptor {

    boolean handleRequest(MessageContext messageContext)
        throws WebServiceClientException;

    boolean handleResponse(MessageContext messageContext)
        throws WebServiceClientException;

    boolean handleFault(MessageContext messageContext)
        throws WebServiceClientException;

    void afterCompletion(
        MessageContext messageContext,
        Exception ex
    ) throws WebServiceClientException;
}
~~~

Đây là chữ ký API minh họa từ Spring-WS. Khi áp dụng vào project, import `MessageContext` từ `org.springframework.ws.context` và `WebServiceClientException` từ `org.springframework.ws.client`.

### 5.1. handleRequest

Chạy khi request phía client đã được tạo để chuẩn bị gửi và trước khi transport gửi theo luồng thông thường.

Dùng cho:

- Thêm SOAP Header, correlation ID, headers liên quan contract.
- Đặt metadata theo từng lần gọi trong `MessageContext`.
- Thực hiện bước security của request qua interceptor chuyên dụng.
- Ghi metric/tracing start time.
- Kiểm tra outbound request ở client nếu có chính sách tương ứng.

Giá trị trả về `true` cho phép chuỗi tiếp tục. `false` báo không tiếp tục theo cơ chế chain của framework; **không nên dùng tùy tiện như “trả lỗi tự động cho server”**. Cần test hành vi short-circuit và cách `WebServiceTemplate` hoàn tất lời gọi trong Spring-WS version đang dùng.

### 5.2. handleResponse

Chạy khi template có response thông thường (không được phân loại là SOAP Fault trong pipeline đó).

Dùng cho:

- Đọc correlation ID, metadata hoặc response SOAP Header.
- Ghi nhận success status theo giao thức.
- Quan sát response trước khi unmarshal/extract dữ liệu.
- Thực hiện các điều chỉnh thực sự được hợp đồng cho phép.

`handleResponse` không được coi là tín hiệu “nghiệp vụ thành công” tuyệt đối. SOAP response không phải Fault vẫn có thể chứa một business result thể hiện từ chối theo XSD. Domain client phải đọc/diễn giải dữ liệu response theo contract.

### 5.3. handleFault

Chạy khi response được nhận diện là **SOAP Fault**. Một SOAP 1.1 Fault có cấu trúc:

~~~xml
<soap:Fault
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <faultcode>soap:Client</faultcode>
    <faultstring>Invalid orderId</faultstring>
</soap:Fault>
~~~

SOAP 1.2 Fault sử dụng cấu trúc khác, trong đó có `Code` và `Reason`. Không hard-code cách đọc Fault của SOAP 1.1 nếu client hỗ trợ SOAP 1.2.

`handleFault` có thể dùng để ghi metric, map correlation data, cảnh báo hoặc enrichment phù hợp. **Nó không tự thay thế `FaultMessageResolver`.** Nếu template có resolver mặc định, một Fault thường vẫn có thể dẫn đến exception như `SoapFaultClientException` sau khi các interceptor đã xử lý.

### 5.4. afterCompletion

Đây là điểm callback phù hợp để dọn dẹp/tổng hợp trạng thái của một lượt xử lý đã đi qua chain theo semantics của framework.

Ví dụ:

- Tính duration từ `System.nanoTime()` đã lưu trong request context.
- Kết thúc một tracing span.
- Dọn tài nguyên gắn với lượt gọi.
- Ghi nhận exception nếu xuất hiện.

**Không mặc định `afterCompletion` luôn chạy khi mọi lời gọi thất bại.** Trường hợp exception trước khi các interceptor được vào chain, hoặc chain bị dừng sớm, có thể dẫn đến tập callback khác. Cần kiểm tra bằng test cho Spring-WS version của ứng dụng.

Không để cleanup ném một exception mới làm che mất lỗi SOAP/transport ban đầu.

### 5.5. ClientInterceptorAdapter

Spring-WS có lớp `ClientInterceptorAdapter` cung cấp cách triển khai mặc định tiện lợi (các `handle...` mặc định cho phép tiếp tục và `afterCompletion` không làm gì). Khi chỉ cần override một vài hook, có thể kế thừa adapter:

~~~java
import org.springframework.ws.client.support.interceptor.ClientInterceptorAdapter;
import org.springframework.ws.context.MessageContext;

public final class SimpleTelemetryInterceptor
        extends ClientInterceptorAdapter {

    @Override
    public boolean handleRequest(MessageContext context) {
        // Logic quan sát.
        return true;
    }
}
~~~

Khi dự án có API version khác, cần đối chiếu class/method thực tế. Dù dùng interface hay adapter, logic nên giữ nguyên nguyên tắc không lưu trạng thái per-request vào field của singleton interceptor.

## 6. Đăng ký ClientInterceptor trong WebServiceTemplate

Một cấu hình Spring Boot/Spring Java Config:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;

@Configuration
public class PartnerOrderClientConfiguration {

    @Bean
    public Jaxb2Marshaller partnerOrdersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath(
            "com.example.partner.orders.v1"
        );
        return marshaller;
    }

    @Bean
    public WebServiceTemplate partnerOrdersTemplate(
            Jaxb2Marshaller partnerOrdersMarshaller,
            ClientCorrelationInterceptor correlation,
            ClientObservationInterceptor observation) {

        WebServiceTemplate template = new WebServiceTemplate();

        template.setMarshaller(partnerOrdersMarshaller);
        template.setUnmarshaller(partnerOrdersMarshaller);

        template.setDefaultUri(
            "https://partner.example.test/ws"
        );

        template.setInterceptors(new ClientInterceptor[] {
            correlation,
            observation
        });

        return template;
    }
}
~~~

Giả định các class `ClientCorrelationInterceptor` và `ClientObservationInterceptor` được định nghĩa/đăng ký thành Spring beans, còn JAXB binding package đã được XJC sinh từ XSD/WSDL của đối tác.

Điều cần nhớ:

- `setInterceptors(...)` gán **mảng interceptor** cho template. Khi gọi lại, bạn đang cấu hình một tập interceptor khác; không mặc định Spring tự nối thêm với tập cũ.
- Thứ tự trong mảng quan trọng.
- Nếu ứng dụng có nhiều `WebServiceTemplate`, phải xác định interceptor thuộc **đúng client/đúng đối tác**; đừng mặc định mọi client đều cần cùng security/signature và namespace.
- Một template có thể được dùng đồng thời từ nhiều thread khi được cấu hình ổn định. Các interceptor là đối tượng có thể được chia sẻ, nên phải thiết kế thread-safe.
- Không nên liên tục thay `setInterceptors(...)` trong lúc template đang được các request threads sử dụng.

### 6.1. Bean của client khác bean của server

Cấu hình `WebServiceTemplate#setInterceptors` không liên quan đến `WsConfigurer.addInterceptors` của SOAP server. Khi cùng ứng dụng vừa nhận vừa gọi SOAP:

~~~text
Inbound:
  MessageDispatcherServlet
    -> EndpointInterceptor chain
    -> @Endpoint

Outbound:
  WebServiceTemplate
    -> ClientInterceptor chain
    -> Remote SOAP service
~~~

Nếu muốn validation hai đầu, client cần chính sách outbound/inbound riêng (chẳng hạn `Jaxb2Marshaller#setSchema` hoặc custom ClientInterceptor phù hợp); việc server dùng `PayloadValidatingInterceptor` không tự xác thực mọi response mà client nhận từ đối tác khác.

## 7. Ví dụ ClientInterceptor thêm SOAP CorrelationId

Một interceptor thêm header theo QName do hai bên đã thống nhất:

~~~java
import java.util.UUID;

import javax.xml.namespace.QName;

import org.springframework.ws.client.support.interceptor.ClientInterceptorAdapter;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

public final class ClientCorrelationInterceptor
        extends ClientInterceptorAdapter {

    public static final String CONTEXT_CORRELATION_ID =
        ClientCorrelationInterceptor.class.getName() + ".id";

    private static final QName CORRELATION_QNAME =
        new QName(
            "urn:example:common:v1",
            "CorrelationId",
            "com"
        );

    @Override
    public boolean handleRequest(MessageContext context) {

        String id = UUID.randomUUID().toString();

        // Property nằm trên MessageContext của lượt gọi.
        context.setProperty(CONTEXT_CORRELATION_ID, id);

        if (!(context.getRequest() instanceof SoapMessage soap)) {
            throw new IllegalStateException(
                "SOAP client yêu cầu SoapMessage"
            );
        }

        SoapHeader header = soap.getSoapHeader();

        SoapHeaderElement element =
            header.addHeaderElement(CORRELATION_QNAME);

        element.setText(id);

        return true;
    }
}
~~~

Ví dụ dùng Java version hỗ trợ pattern matching cho `instanceof`. Nếu dự án dùng Java cũ, thay bằng kiểm tra và cast thông thường.

**Không tự thêm CorrelationId vào một contract không cho phép hoặc không hiểu header này.** Nếu đối tác yêu cầu header khác namespace, tên hoặc kiểu giá trị, phải lấy từ WSDL/policy/tài liệu tích hợp.

### 7.1. Vì sao dùng QName mà không dùng chuỗi XML?

`SoapHeader.addHeaderElement(QName)` cho phép Spring-WS tạo phần tử có **namespace URI và local name** đúng. Prefix `com` là cách viết; client và server phải so QName.

Sai cách tiếp cận:

~~~java
// Không xây header bằng cách nối raw XML input người dùng:
String xml =
    "<com:CorrelationId>" + userInput + "</com:CorrelationId>";
~~~

Nếu dữ liệu có ký tự `&` hoặc `<`, XML có thể bị hỏng; nếu nội dung do người dùng kiểm soát, còn có rủi ro tạo markup ngoài ý muốn. Dùng API SOAP header hoặc XML writer namespace-aware thay vì nối chuỗi.

### 7.2. Không lưu correlationId vào field mutable của interceptor

**Sai về concurrency** nếu interceptor được dùng chung:

~~~java
public class UnsafeCorrelationInterceptor
        extends ClientInterceptorAdapter {

    private String lastCorrelationId;

    @Override
    public boolean handleRequest(MessageContext context) {
        lastCorrelationId = UUID.randomUUID().toString();
        return true;
    }
}
~~~

Hai SOAP calls đồng thời có thể ghi đè `lastCorrelationId`, khiến response A bị gắn ID của request B.

**Đúng hơn:** Lưu metadata trên `MessageContext` của lượt xử lý, hoặc hệ thống tracing context có lifecycle rõ ràng. Không dùng singleton field cho trạng thái biến thiên theo từng request.

### 7.3. Mở rộng để đọc correlationId khi nhận response

Nếu đối tác echo header, interceptor phía response có thể kiểm tra header theo QName. Tuy nhiên, `SoapHeader` có thể chứa nhiều element và nhiều namespace khác nhau. Khi đọc, hãy:

- Kiểm tra message là `SoapMessage`.
- Duyệt header với API phù hợp phiên bản Spring-WS.
- So **namespace URI + local name**, không so prefix raw.
- Không coi echo header là bằng chứng xác thực người gọi; nếu cần integrity, phải bảo vệ bằng chữ ký/WS-Security.
- Không phát lộ correlation ID nhạy cảm trong log công khai.

Nếu đối tác không echo header, không tự báo lỗi cho mọi request nếu hợp đồng chưa yêu cầu điều đó.

## 8. Quan sát thời gian và trạng thái của SOAP call

Một interceptor ghi thời điểm bắt đầu và phân loại kết quả:

~~~java
import org.springframework.ws.client.support.interceptor.ClientInterceptorAdapter;
import org.springframework.ws.context.MessageContext;

public final class ClientObservationInterceptor
        extends ClientInterceptorAdapter {

    private static final String START_KEY =
        ClientObservationInterceptor.class.getName() + ".start";

    private static final String OUTCOME_KEY =
        ClientObservationInterceptor.class.getName() + ".outcome";

    @Override
    public boolean handleRequest(MessageContext context) {
        context.setProperty(START_KEY, System.nanoTime());
        context.setProperty(OUTCOME_KEY, "unknown");
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext context) {
        context.setProperty(OUTCOME_KEY, "soap_response");
        return true;
    }

    @Override
    public boolean handleFault(MessageContext context) {
        context.setProperty(OUTCOME_KEY, "soap_fault");
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context,
            Exception exception) {

        Object started = context.getProperty(START_KEY);

        if (!(started instanceof Long startNanos)) {
            return;
        }

        long elapsedNanos = System.nanoTime() - startNanos;
        String outcome = (String) context.getProperty(OUTCOME_KEY);

        if (exception != null) {
            outcome = "client_exception";
        }

        // Thực tế: xuất metric qua MeterRegistry/tracer,
        // không in thô request/response body.
        recordMetric(outcome, elapsedNanos);
    }

    private void recordMetric(String outcome, long elapsedNanos) {
        // Adapter tới thư viện telemetry của ứng dụng.
    }
}
~~~

Ở đây `System.nanoTime()` phù hợp để đo elapsed duration, không phải wall-clock timestamp để hiển thị cho đối tác. `MessageContext` chứa metadata per-call, tránh field dùng chung trong interceptor.

Đừng ghi metric thành công và Fault hai lần: ví dụ trên phân loại trong `handleResponse`/`handleFault`, rồi tổng hợp trong `afterCompletion`. Nếu framework không gọi `afterCompletion` trong một nhánh đặc biệt, cần có observability ở tầng gọi client hoặc transport để không bỏ mất lỗi.

### 8.1. Phân biệt kết quả kỹ thuật và kết quả nghiệp vụ

Không có SOAP Fault chưa chắc thao tác thành công theo nghiệp vụ. Response có thể là:

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
    <ord:status>CANCELLED</ord:status>
</ord:GetOrderResponse>
~~~

Đây là response hợp lệ về giao thức và có thể là kết quả nghiệp vụ từ chối theo chính sách. Client application cần đọc `status`/response type thay vì dựa duy nhất vào `handleResponse` để coi `success=true`.

### 8.2. Chọn metric labels có cardinality kiểm soát

Nên gắn labels như:

~~~text
client=partner-order
operation=GetOrder
soap_version=1.1
outcome=soap_fault
~~~

Không dùng `orderId`, requestId động hoặc nguyên SOAP body làm metric labels: số lượng giá trị không giới hạn có thể gây nổ cardinality, tiêu tốn tài nguyên monitoring và lộ thông tin.

## 9. Chuỗi interceptor: thứ tự gọi và điều kiện dừng

Một `WebServiceTemplate` có thể nhận nhiều interceptors:

~~~java
template.setInterceptors(new ClientInterceptor[] {
    correlationInterceptor,
    securityInterceptor,
    observationInterceptor
});
~~~

Theo mô hình chain thông dụng của Spring-WS, các callback request đi theo **thứ tự đăng ký**. Khi xử lý response hoặc Fault, chain thường được xử lý theo **chiều ngược lại**, như thao tác unwind; cleanup cũng tuân semantics vòng đời tương ứng.

~~~text
Request outbound:
  Correlation -> Security -> Observation -> HTTP send

Response/Fault inbound:
  Observation -> Security -> Correlation -> caller

Completion:
  Chạy callbacks hoàn tất theo phạm vi interceptor đã thực sự tham gia.
~~~

**Đừng chỉ học thuộc sơ đồ rồi bỏ qua test.** Khi interceptor trả `false` hoặc throw exception, những interceptor sau đó có thể không chạy. Một số lifecycle branches khác nhau theo Spring-WS version và cách `WebServiceTemplate` short-circuit. Viết test ghi lại callback order cho stack thực tế.

### 9.1. handleRequest trả false nghĩa là gì?

`false` báo cho framework **ngừng tiếp tục xử lý request theo chain**. Một số client interceptors có thể dùng để short-circuit/caching theo cơ chế được framework hỗ trợ. Tuy nhiên, nếu không tạo response hoặc không nắm rõ semantics của template, người gọi có thể nhận kết quả bất ngờ thay vì một SOAP Fault.

Không dùng:

~~~java
@Override
public boolean handleRequest(MessageContext context) {
    return false; // "Để trả SOAP Fault" -- hiểu như vậy là sai.
}
~~~

với kỳ vọng framework tự sinh SOAP Fault hợp đồng. Nếu cần từ chối lời gọi trước khi gửi, nên thiết kế một exception client rõ ràng hoặc policy precondition ở tầng application, và kiểm thử kết quả thực tế.

### 9.2. handleResponse/handleFault trả false

Giá trị `false` ngăn xử lý tiếp theo theo semantics của interceptor chain tương ứng. Nó **không có nghĩa tự động biến SOAP Fault thành success** hay tự hủy kết quả Fault resolver mặc định.

Nếu viết một interceptor đọc Fault rồi trả `false`, hãy xem nó ảnh hưởng ra sao đến các callbacks phía sau, phần giải mã response và resolver. Tránh dùng `false` làm cách “nuốt lỗi” khi chưa có test đầy đủ.

### 9.3. afterCompletion chỉ dọn dẹp trong phạm vi được gọi

Nếu yêu cầu cần bảo đảm tài nguyên được đóng trong **mọi** tình huống, đừng chỉ đặt trách nhiệm đó vào `afterCompletion` rồi giả định nó luôn chạy bất kể lỗi xảy ra ở đâu. Những lỗi trước khi chain bắt đầu hoặc khi callback của một interceptor không hoàn tất có thể không kích hoạt cleanup như dự tính.

Các tài nguyên nên được quản lý bằng `try/finally` tại nơi chúng được tạo nếu API yêu cầu, hoặc gắn vào vòng đời rõ ràng của transport. Interceptor nên tránh giữ socket/file handles thủ công.

## 10. SOAP Fault khác lỗi HTTP và transport

Một SOAP client có thể thất bại theo nhiều cách:

| Tình huống | Dấu hiệu | Callback thường liên quan |
|---|---|---|
| SOAP response bình thường | SOAP Body chứa response operation | `handleResponse` |
| SOAP Fault hợp lệ | SOAP Body có Fault | `handleFault`, sau đó fault resolution |
| HTTP 404/403 không có SOAP Fault | Lỗi endpoint/auth/proxy | Transport/template exception; không chắc có `handleFault` |
| Connection timeout | Không nhận SOAP response | Transport exception |
| TLS handshake lỗi | Không kết nối bảo mật thành công | Transport exception |
| HTTP 500 chứa SOAP Fault | Có thể hợp SOAP binding của dịch vụ | `handleFault` nếu được nhận diện |
| XML response sai SOAP version | Không parse/nhận diện được Envelope | Message factory/transport exception |
| JAXB unmarshal lỗi | XML đã nhận nhưng không ánh xạ được type | Exception ở tầng mapping, có thể sau response interceptors |
| Business error trong success payload | Response không phải Fault, nhưng trạng thái nghiệp vụ từ chối | `handleResponse` và application logic |

Trong SOAP 1.1, HTTP 500 có thể được dùng cho SOAP Fault; điều đó không biến mọi HTTP 500 thành SOAP Fault. Cần đọc Content-Type, Envelope và fault classifier của template.

### 10.1. FaultMessageResolver ở đâu?

`WebServiceTemplate` có khả năng dùng `FaultMessageResolver` để xử lý SOAP Fault. Resolver thường chuyển Fault thành exception. Ví dụ Spring-WS cung cấp `SoapFaultMessageResolver` và exception `SoapFaultClientException`.

Một trình tự khái quát:

~~~text
Remote SOAP Fault
   -> WebServiceTemplate phân loại Fault
   -> ClientInterceptor.handleFault(...)
   -> FaultMessageResolver xử lý (nếu được áp dụng)
   -> Caller nhận exception/kết quả theo policy
~~~

Không nên ghi vào tài liệu hợp đồng rằng `handleFault` luôn “xử lý hết lỗi” nếu template vẫn có resolver khác. Một cách xử lý nhất quán là dùng interceptor cho telemetry/enrichment chung, còn tầng client adapter xử lý exception nghiệp vụ và quyết định retry.

### 10.2. SOAP Fault không đồng nghĩa retry được

SOAP 1.1 Fault code `Client` và SOAP 1.2 `Sender` thường đại diện vấn đề phía request; retry nguyên thông điệp có thể vô ích. `Server`/`Receiver` có thể phản ánh lỗi tạm thời hoặc không, cần xét fault detail và chính sách đối tác.

Không tự retry trong `handleFault` bằng cách gọi lại template một cách đệ quy: dễ tạo vòng lặp, tạo duplicate side effects và làm mờ số lần gọi thực. Retry nên được điều phối ở tầng có **idempotency key**, timeout budget và phân loại lỗi rõ ràng.

## 11. Phân biệt WebServiceMessageCallback với ClientInterceptor

`WebServiceMessageCallback` chỉ phục vụ cho một lời gọi hoặc một nhánh gửi request, còn `ClientInterceptor` được đăng ký trên template và có thể áp dụng cho nhiều lời gọi.

Ví dụ `SoapActionCallback`:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

Object response = template.marshalSendAndReceive(
    "https://partner.example.test/ws",
    request,
    new SoapActionCallback(
        "urn:example:orders:actions:GetOrder"
    )
);
~~~

`SoapActionCallback` giúp cấu hình SOAPAction/action tương ứng binding, không phải cơ chế chạy response/Fault hooks. Với SOAP 1.1, SOAPAction gắn với HTTP header; SOAP 1.2 có cách biểu diễn action khác. Phải đối chiếu WSDL binding thực tế.

| Nhu cầu | Chọn |
|---|---|
| Thêm SOAPAction riêng cho operation | `SoapActionCallback` hoặc callback tương ứng |
| Thêm correlation header cho mọi lời gọi cùng client | `ClientInterceptor` |
| Tạo XML request từ Java object | JAXB/OXM qua `WebServiceTemplate` |
| Kiểm tra inbound SOAP Fault của mọi lời gọi | `ClientInterceptor.handleFault` + `FaultMessageResolver` |
| Đổi HTTP connection timeout | Message sender/HTTP client |
| Đổi policy retry | Tầng client adapter/application với idempotency |
| Xác thực chữ ký WS-Security | Security interceptor phù hợp |
| Kiểm tra XSD của request/response ở client | Marshaller/validator phù hợp ranh giới |

Nếu callback và interceptor **cùng chỉnh một SOAP Header**, phải xác định thứ tự xử lý và ai là nguồn chính xác của dữ liệu. Tránh hai nơi cùng tạo `CorrelationId` hoặc ghi đè SOAPAction dẫn tới hành vi khó kiểm soát.

## 12. Thứ tự interceptor khi có WS-Security

Một hệ thống doanh nghiệp thường cần phối hợp ba nhóm hành vi:

1. **Observation/telemetry**: đo thời gian, phân loại kết quả và tạo tracing span.
2. **Correlation headers**: tạo các SOAP headers được đối tác cho phép và phục vụ correlation.
3. **WS-Security**: ký/mã hóa request và xác minh/giải mã response theo security policy.

Một thứ tự cần cân nhắc:

~~~text
Request:
    Observation -> Correlation -> WS-Security -> Remote server

Response/Fault:
    Remote server -> WS-Security -> Correlation -> Observation
~~~

Ý nghĩa:

- Telemetry bao quanh vòng đời request/response, không bị giới hạn ở một thao tác bên trong.
- Correlation header được tạo **trước bước ký**.
- Response được security interceptor xác minh trước khi những interceptor phía ngoài tin cậy nội dung và ghi nhận metadata.

Đây là một **mô hình thiết kế cần được kiểm chứng** trên Spring-WS version và thư viện WS-Security đang dùng. Cách callback chạy khi security validation throw exception có thể khác nhánh nhận SOAP response thông thường.

### 12.1. Header được tạo trước khi ký chưa chắc đã được ký

Bộ ký chỉ bảo vệ những SOAP parts được chỉ rõ trong cấu hình/policy. Nếu thêm `CorrelationId` vào SOAP Header trước bước ký nhưng cấu hình chữ ký chỉ bao phủ Body, header này **không tự động có integrity protection**.

Để có yêu cầu bảo mật đúng:

- Xác định QName cụ thể của SOAP Header cần được bảo vệ.
- Cấu hình signature parts và thuật toán theo policy đối tác.
- Xác minh chữ ký ở đầu nhận với truststore/certificate đáng tin.
- Test sửa Header sau khi ký để chắc chắn việc thay đổi bị phát hiện.
- Có kiểm soát replay, timestamp và key rotation theo yêu cầu.

Correlation ID không phải bằng chứng xác thực danh tính, dù được ký; authentication và authorization vẫn cần những bước riêng.

### 12.2. Dùng WSS4J/Spring-WS security interceptor

Spring-WS tích hợp Apache WSS4J qua security interceptor trong các module/phiên bản hỗ trợ. Tên package và cấu hình chính xác phụ thuộc dòng Spring-WS/WSS4J:

~~~java
// Minh họa ý tưởng -- không phải cấu hình WS-Security hoàn chỉnh:
//
// Wss4jSecurityInterceptor security = new Wss4jSecurityInterceptor();
//
// security.setSecurementActions("Timestamp Signature");
// security.setValidationActions("Timestamp Signature");
//
// Bản triển khai cần thêm crypto properties,
// keystore/truststore, password callbacks,
// signature parts, chính sách thuật toán,
// thời gian hiệu lực, certificate trust,
// kiểm soát replay và xử lý lỗi.
~~~

Không đặt private keys, mật khẩu hoặc token trực tiếp trong source code/log. Hãy dùng secret management và chính sách bảo mật phù hợp môi trường doanh nghiệp. TLS bảo vệ kênh HTTP, còn WS-Security bảo vệ nội dung SOAP theo phần được ký hoặc mã hóa; có thể cần cả hai.

### 12.3. Logging trước hay sau security?

Nếu log request sau khi serialize trước bước ký, logger có thể thấy plaintext nghiệp vụ. Nếu log sau ký, log có thể chứa chữ ký, token hoặc binary security metadata. Với response, log trước verify có nguy cơ ghi dữ liệu chưa đáng tin; log sau decrypt có thể lộ thông tin nhạy cảm.

Trong production, nên ghi **metadata tối thiểu**: client alias, operation, duration, outcome, SOAP fault code đã chuẩn hóa, correlation ID được phép và kích thước payload đã làm tròn nếu hữu ích. Không ghi raw request/response, secrets, private key, certificate material hoặc dữ liệu khách hàng trừ khi có một quy trình điều tra được kiểm soát nghiêm ngặt.

## 13. ClientInterceptor không tự xác thực XSD

Một client SOAP có thể phải kiểm tra:

- **Outbound XML request** hợp XSD trước khi gửi đến đối tác.
- **Inbound XML response** hợp XSD khi nhận về, trước khi chuyển sang domain object.

Nếu dùng JAXB/OXM, cấu hình `Jaxb2Marshaller` với schema là một lựa chọn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class PartnerOrderBindingConfiguration {

    @Bean
    public Jaxb2Marshaller partnerMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();

        marshaller.setContextPath(
            "com.example.partner.orders.v1"
        );

        marshaller.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd")
        );

        return marshaller;
    }
}
~~~

Điều này kiểm tra những lời gọi marshal/unmarshal **đi qua chính bean này**. Nếu có nhiều client templates, phải gắn đúng marshaller và XSD cho từng client. Với `xs:import`/`xs:include`, resolver cần tìm được schema dependencies từ nguồn đáng tin.

**Không đưa `PayloadValidatingInterceptor` của server vào `WebServiceTemplate.setInterceptors(...)`.** Thành phần đó phục vụ endpoint interceptor chain phía server, không phải client chain. Nếu dùng custom client-side validation interceptor, nó cần implement `ClientInterceptor` thực sự và bảo đảm đọc XML không phá một nguồn streaming chỉ dùng được một lần.

### 13.1. JAXB marshal thành công không chứng minh XML hợp XSD

Một generated JAXB type có thể cho phép Java gán null vào required field hoặc một enum/value sai nếu binding tùy chỉnh. Không có schema validation, code có thể marshal XML sai hợp đồng.

Ngược lại, unmarshal XML có QName root đúng không có nghĩa các facet, cardinality và business rules đều đã được kiểm tra. Để chứng minh contract, dùng schema validator và negative XML fixtures viết độc lập từ WSDL/XSD.

### 13.2. Đừng làm biến đổi dữ liệu trong interceptor telemetry

Nếu logging interceptor tự unmarshal rồi marshal lại toàn bộ request, nó có thể thay đổi namespace declarations, nil/empty semantics, XML Signature hoặc chi phí xử lý mà không thêm giá trị cho logging.

Dành việc chuyển đổi business payload cho adapter chuyên dụng có test tương thích. ClientInterceptor nên ưu tiên các nhiệm vụ **cross-cutting** như bảo mật, headers, tracing và quan sát lỗi.

## 14. Xây dựng chính sách lỗi cho SOAP client

Một client adapter cần phân loại lỗi để application layer biết cần báo người dùng, retry hay cảnh báo kỹ thuật:

~~~text
PartnerOrderClient.getOrder(...)
   |
   +-- SOAP success response
   |      -> JAXB unmarshal
   |      -> kiểm tra kết quả nghiệp vụ
   |
   +-- SOAP Fault
   |      -> handleFault
   |      -> FaultMessageResolver
   |      -> SOAP Fault exception / map app exception
   |
   +-- HTTP / TCP / TLS / timeout
   |      -> transport exception
   |      -> retry nếu có cơ sở và idempotency
   |
   +-- JAXB / schema exception
          -> dấu hiệu lệch contract/integration
          -> xử lý như sự cố tích hợp
~~~

Ví dụ adapter gọi `WebServiceTemplate`:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.ws.soap.client.core.SoapActionCallback;

public final class PartnerOrderClient {

    private final WebServiceTemplate template;

    public PartnerOrderClient(WebServiceTemplate template) {
        this.template = template;
    }

    public Object getOrder(Object request) {
        try {
            return template.marshalSendAndReceive(
                request,
                new SoapActionCallback(
                    "urn:example:orders:actions:GetOrder"
                )
            );
        } catch (SoapFaultClientException fault) {
            throw new PartnerSoapFaultException(
                "Đối tác trả SOAP Fault",
                fault
            );
        }
    }
}
~~~

`PartnerSoapFaultException` ở đây là exception application-level minh họa, không phải lớp sẵn có của Spring-WS. Mã này chỉ minh họa nhánh SOAP Fault; transport và JAXB exceptions cần policy riêng ở production.

**Không biến mọi exception thành null hoặc response giả chứa OK.** Caller phải phân biệt không nhận được response, nhận Fault, response sai contract và kết quả nghiệp vụ thành công.

### 14.1. Retry không nên được thực hiện đệ quy trong handleFault

Một SOAP Fault do `Client`/`Sender` (sai request) thường không được giải quyết bằng cách gửi lại y hệt. Một lỗi `Server`/`Receiver` có thể là tạm thời nhưng cũng cần xem fault detail và chính sách đối tác.

Không gọi lại `WebServiceTemplate` từ `handleFault` bằng một vòng retry không kiểm soát. Điều đó có thể:

- Tạo vòng gọi lồng nhau.
- Sinh nhiều giao dịch nếu operation có side effect.
- Khiến tracing và timeout budget khó đúng.
- Làm mờ kết quả của attempt nào là kết quả cuối cùng.

Retry, circuit breaker, rate limit và timeout budget nên đặt ở **tầng client adapter/application** có hiểu operation có idempotent hay không. Một `SubmitPayment` timeout có thể đã được server thực hiện trước khi client nhận được response; retry nếu không có idempotency key có thể tạo giao dịch trùng.

### 14.2. Transport timeout không giống SOAP Fault

Nếu kết nối HTTPS thất bại khi TLS handshake, ứng dụng có thể chưa nhận được SOAP Envelope nào. Khi đó `handleFault` không phải callback đảm bảo sẽ chạy. Wrapper quanh client operation hoặc telemetry ở tầng transport cần ghi nhận exception đúng.

Không đổ lỗi cho XSD validation khi thực tế response lỗi do HTTP 404/503, TLS trust hoặc SOAP version mismatch.

## 15. Quan sát SOAP Fault mà không nuốt lỗi

Ví dụ một interceptor chỉ ghi nhận fault code/reason ở mức an toàn:

~~~java
import org.springframework.ws.client.support.interceptor.ClientInterceptorAdapter;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapBody;
import org.springframework.ws.soap.SoapFault;
import org.springframework.ws.soap.SoapMessage;

public final class FaultObservationInterceptor
        extends ClientInterceptorAdapter {

    @Override
    public boolean handleFault(MessageContext context) {

        if (context.getResponse() instanceof SoapMessage soap) {
            SoapBody body = soap.getSoapBody();
            SoapFault fault = body.getFault();

            if (fault != null) {
                // Không log Fault Detail chưa được masking.
                String reason = fault.getFaultStringOrReason();
                recordFaultClass(reason);
            }
        }

        // Tiếp tục chain/fault processing theo cấu hình.
        return true;
    }

    private void recordFaultClass(String reason) {
        // Chỉ phân loại reason; không dùng raw text làm label.
    }
}
~~~

`getFaultStringOrReason()` lấy mô tả; nó có thể là dữ liệu từ đối tác, không nên dùng nguyên chuỗi làm metric label hoặc in vào log nhạy cảm. Nếu hợp đồng có fault code/QName ổn định, nên ưu tiên chúng để phân loại.

Không tự suy ra `handleFault` đã “giải quyết” Fault: `FaultMessageResolver` có thể tiếp tục ném exception, và caller vẫn cần xử lý.

### 15.1. Lỗi XML không phải SOAP Fault

Nếu partner trả HTML lỗi, response không phải SOAP Envelope, hoặc trả XML malformed, message factory có thể ném exception trước khi có `SoapFault` object. Phải kiểm tra exception ở wrapper/transport, không chỉ đo số lần `handleFault` chạy.

Với SOAP 1.2, Fault có `Code`/`Reason`; tránh hard-code việc parse `faultcode`/`faultstring` theo SOAP 1.1 khi client chấp nhận cả hai phiên bản.

## 16. Có nên sửa response trong ClientInterceptor?

Hạn chế việc chỉnh business payload ở đây. Trước khi sửa XML cần đặt các câu hỏi:

1. XSD/WSDL cho phép phần tử/attribute đó không?
2. Response đã ký hoặc mã hóa chưa, có security validation nào chạy trước/sau không?
3. Sửa response có làm thay QName, type, nil, absent/empty hoặc thứ tự không?
4. JAXB unmarshaller có còn đọc được XML sau khi sửa?
5. Cùng quy tắc chuyển đổi có nên nằm ở mapper/domain adapter để dễ test hơn không?

Thường nên để ClientInterceptor phục vụ cross-cutting concerns, còn business response transformation ở một adapter chuyên dụng, có XSD validation và regression fixtures.

### 16.1. Đọc Source có thể tiêu thụ stream

Một số `WebServiceMessage#getPayloadSource()` trả representation dùng luồng. Không mặc định mọi Source đều có thể đọc lại nhiều lần hoặc ép kiểu về `DOMSource`. Nếu interceptor serialize toàn bộ Source để log, bước unmarshal sau có thể thất bại tùy message factory.

Với payload logging, nên dùng framework-provided tracing hoặc buffering có giới hạn và kiểm thử Spring-WS/XML provider thực tế. Với dữ liệu nhạy cảm, metadata-only logging là lựa chọn an toàn hơn.

### 16.2. Không sửa DOM đã ký tùy tiện

Thay namespace declarations, prefix, element structure hoặc giá trị có thể làm mất hiệu lực XML Signature tùy canonicalization và signed references. Một response có business data giống nhau không có nghĩa chữ ký ban đầu tự động bảo vệ representation mới.

## 17. Nhiều WebServiceTemplate cho nhiều đối tác

Giả sử ứng dụng gọi:

~~~text
Partner A:
  orders-v1.wsdl
  SOAP 1.1
  Header CorrelationId
  UsernameToken + Timestamp

Partner B:
  billing-v2.wsdl
  SOAP 1.2
  XML Signature + Encryption
  Namespace và certificate khác
~~~

Không nên mặc định dùng chung một template và một tập interceptors nếu hai đối tác khác SOAP version, binding, namespace, JAXB type và security policy.

Ví dụ cấu hình tách biệt:

~~~java
@Configuration
public class PartnerSoapClientsConfiguration {

    @Bean(name = "partnerATemplate")
    public WebServiceTemplate partnerA(
            Jaxb2Marshaller partnerAMarshaller,
            ClientInterceptor partnerAObservation,
            ClientInterceptor partnerACorrelation,
            ClientInterceptor partnerASecurity) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(partnerAMarshaller);
        template.setUnmarshaller(partnerAMarshaller);

        template.setInterceptors(new ClientInterceptor[] {
            partnerAObservation,
            partnerACorrelation,
            partnerASecurity
        });

        return template;
    }

    @Bean(name = "partnerBTemplate")
    public WebServiceTemplate partnerB(
            Jaxb2Marshaller partnerBMarshaller,
            ClientInterceptor partnerBObservation,
            ClientInterceptor partnerBSecurity) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(partnerBMarshaller);
        template.setUnmarshaller(partnerBMarshaller);

        template.setInterceptors(new ClientInterceptor[] {
            partnerBObservation,
            partnerBSecurity
        });

        return template;
    }
}
~~~

Đây là skeleton, chưa khai báo URI, SOAP factory, message sender hoặc security crypto configuration cụ thể. Khi Spring context có nhiều `ClientInterceptor` hoặc `Jaxb2Marshaller` beans cùng type, cần `@Qualifier` và đặt tên bean rõ ràng, tránh inject nhầm cấu hình đối tác.

### 17.1. Tách context binding theo contract

Orders v1 có QName `{urn:example:orders:v1}GetOrderRequest`. Billing v2 có namespace khác và có thể dùng SOAP 1.2. Một endpoint URL khác không đủ để diễn tả mọi khác biệt; phải chọn binding, SOAP message factory, action và security đúng.

### 17.2. Template dùng chung nhưng trạng thái per-call tách biệt

`WebServiceTemplate` có thể được dùng từ nhiều threads khi cấu hình hoàn chỉnh và không bị thay đổi trong lúc chạy. Interceptor beans cũng có thể được dùng chung; requestId, start time, tracing span cần đặt trên `MessageContext` hoặc một request-scoped carrier đáng tin.

Không gọi `template.setInterceptors(...)` trong mỗi method call khi template còn được threads khác dùng; đó là thay mutable configuration global và dễ sinh race condition.

## 18. Wiring ClientInterceptor bằng Spring XML

Trong hệ thống Spring XML hiện hữu:

~~~xml
<bean id="orderClientTemplate"
      class="org.springframework.ws.client.core.WebServiceTemplate">

    <property name="defaultUri"
              value="https://partner.example.test/ws"/>

    <property name="marshaller" ref="ordersMarshaller"/>
    <property name="unmarshaller" ref="ordersMarshaller"/>

    <property name="interceptors">
        <list>
            <ref bean="observationInterceptor"/>
            <ref bean="correlationInterceptor"/>
            <ref bean="securityInterceptor"/>
        </list>
    </property>
</bean>
~~~

Đây là một fragment cấu hình, các bean tham chiếu phải được định nghĩa và implements `ClientInterceptor`. Framework version phải tương thích với các constructor/properties thực tế.

Thứ tự `<ref>` trong list là thứ tự cấu hình client chain. Khi chuyển sang Java Config, phải giữ thứ tự có chủ đích, đặc biệt với security và correlation.

**Không nhầm** cấu hình server-side `<sws:interceptors>` với property `WebServiceTemplate.interceptors` của client. Chúng là hai cơ chế riêng, dù ứng dụng có thể vừa cung cấp vừa tiêu thụ SOAP services.

## 19. Kiểm thử ClientInterceptor với MockWebServiceServer

Spring-WS cung cấp `MockWebServiceServer` trong thư viện `spring-ws-test`. Công cụ này giả lập **SOAP server** để kiểm tra hành vi **SOAP client** sử dụng `WebServiceTemplate`, không yêu cầu mở kết nối đến đối tác thật.

Cần phân biệt:

| Công cụ | Đối tượng kiểm thử |
|---|---|
| `MockWebServiceServer` | WebServiceTemplate, client interceptor, outbound request, inbound response/Fault |
| `MockWebServiceClient` | Server endpoint, endpoint interceptor, SOAP handler phía cung cấp |

Nếu dùng `MockWebServiceClient` để kiểm tra callback của `ClientInterceptor`, bạn đang kiểm tra sai phía của integration boundary.

### 19.1. Test SOAP request/response không cần JAXB object

Ví dụ để tập trung vào client interceptor, dùng XML Source:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import java.io.StringWriter;

import javax.xml.transform.stream.StreamResult;

import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

class PartnerSoapClientTest {

    @Test
    void sendsExpectedPayloadAndReceivesResponse() {
        WebServiceTemplate template = new WebServiceTemplate();

        template.setInterceptors(new ClientInterceptor[] {
            new ClientCorrelationInterceptor()
        });

        MockWebServiceServer server =
            MockWebServiceServer.createServer(template);

        String request = """
            <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-2048</ord:orderId>
            </ord:GetOrderRequest>
            """;

        String response = """
            <ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-2048</ord:orderId>
                <ord:status>PAID</ord:status>
            </ord:GetOrderResponse>
            """;

        server.expect(payload(new StringSource(request)))
              .andRespond(withPayload(new StringSource(response)));

        StringWriter output = new StringWriter();

        template.sendSourceAndReceiveToResult(
            "https://partner.example.test/ws",
            new StringSource(request),
            new StreamResult(output)
        );

        server.verify();
    }
}
~~~

Ví dụ cần dependency `spring-ws-test`, JUnit 5 và SOAP message factory phù hợp. Vì test sử dụng payload Source, nó tập trung vào đường gửi/nhận của template chứ không kiểm tra XJC/JAXB binding; bộ kiểm thử thật nên có thêm test marshalSendAndReceive với generated classes.

`server.verify()` giúp xác nhận những request kỳ vọng đã thực sự diễn ra. Bản thân đoạn code chưa assert Header CorrelationId, SOAPAction hoặc Fault; các mục tiếp theo bổ sung.

### 19.2. Kiểm tra SOAP Header bằng QName

Một matcher tùy chỉnh có thể duyệt header:

~~~java
import java.util.Iterator;

import javax.xml.namespace.QName;

import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

// Trích đoạn bên trong custom RequestMatcher:
QName expected = new QName(
    "urn:example:common:v1",
    "CorrelationId"
);

if (!(requestMessage instanceof SoapMessage soap)) {
    throw new AssertionError("Request không phải SOAP");
}

boolean found = false;

Iterator<SoapHeaderElement> iterator =
    soap.getSoapHeader().examineAllHeaderElements();

while (iterator.hasNext()) {
    SoapHeaderElement element = iterator.next();

    if (expected.equals(element.getName())) {
        found = true;
        break;
    }
}

if (!found) {
    throw new AssertionError(
        "Không thấy CorrelationId với đúng QName"
    );
}
~~~

Đây là **phần thân của một matcher minh họa**, không phải một Java test class độc lập: cần cung cấp biến `requestMessage` từ `RequestMatcher` của Spring-WS. Nó kiểm tra QName (namespace URI + local name), không ép đối tác phải dùng prefix `com`.

Khi kiểm thử header được ký, chỉ assert header có mặt **chưa đủ**: cần xác nhận WS-Security signature parts và kiểm chứng chữ ký. Một header không được bảo vệ có thể bị thay đổi trên đường truyền ở những môi trường không áp dụng chính sách integrity thích hợp.

### 19.3. Ghi nhận thứ tự callback

Tạo một interceptor chỉ để test:

~~~java
import java.util.List;

import org.springframework.ws.client.support.interceptor.ClientInterceptorAdapter;
import org.springframework.ws.context.MessageContext;

public final class RecordingInterceptor
        extends ClientInterceptorAdapter {

    private final String name;
    private final List<String> events;

    public RecordingInterceptor(
            String name,
            List<String> events) {
        this.name = name;
        this.events = events;
    }

    @Override
    public boolean handleRequest(MessageContext context) {
        events.add(name + ".request");
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext context) {
        events.add(name + ".response");
        return true;
    }

    @Override
    public boolean handleFault(MessageContext context) {
        events.add(name + ".fault");
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context,
            Exception ex) {
        events.add(name + ".completion");
    }
}
~~~

Trong test tuần tự:

~~~java
List<String> events = new java.util.ArrayList<>();

template.setInterceptors(new ClientInterceptor[] {
    new RecordingInterceptor("A", events),
    new RecordingInterceptor("B", events)
});
~~~

Sau một request thành công, các callback request thường được ghi theo `A.request` rồi `B.request`, còn response được xử lý theo chiều unwind. Cần kiểm tra thực tế cả các completion callbacks để xác nhận version Spring-WS đang chạy.

Viết các test riêng cho:

1. Cả hai interceptor trả `true`.
2. Interceptor A trả `false` ở request.
3. Interceptor B throw exception ở request.
4. SOAP response bình thường.
5. SOAP Fault.
6. Transport timeout hoặc lỗi kết nối.
7. Lỗi JAXB khi unmarshal response.

Không dùng test một nhánh thành công để khẳng định mọi đường đều gọi `afterCompletion` hoặc `handleFault`.

### 19.4. Test SOAP Fault và FaultMessageResolver

`MockWebServiceServer` có response creators cho SOAP Fault. Một kiểm thử đầy đủ nên:

- Giả lập Fault do request sai hợp đồng.
- Đảm bảo `handleFault` được gọi đúng những interceptor liên quan.
- Đảm bảo `handleResponse` không bị ghi nhận như success.
- Kiểm tra `FaultMessageResolver` mặc định/custom chuyển Fault thành exception hoặc kết quả theo policy.
- Kiểm tra telemetry phân loại Fault an toàn.
- Tạo một lỗi không phải SOAP Fault (ví dụ transport error) để bảo đảm wrapper vẫn ghi nhận lỗi.

Đừng xem `handleFault` là nơi phải tự động retry hay khởi tạo một response giả; Fault từ SOAP đối tác cần được chuyển thành lỗi nghiệp vụ/kỹ thuật phù hợp ở client adapter.

### 19.5. Test concurrency để phát hiện shared mutable state

Một đơn vị test dùng nhiều threads có thể gửi các requests đồng thời, mỗi request có correlation ID riêng. Assertions cần xác nhận:

- Mỗi request có đúng một header CorrelationId.
- ID của request này không xuất hiện trong response/metrics gắn request khác.
- Không có field mutable của interceptor lưu “currentOrderId” hay “currentCorrelationId”.
- `MessageContext` được xử lý riêng cho mỗi lượt gọi.
- Bộ metrics không dùng orderId hoặc UUID làm label gây cardinality cao.

Nếu mock server test không mô phỏng concurrency thuận tiện, có thể dùng một fake transport hoặc môi trường tích hợp cục bộ; không dùng production partner để tạo tải kiểm thử không có thỏa thuận.

## 20. Contract-first và khả năng tương thích với hệ thống khác

Spring-WS có thể gọi SOAP partner viết bằng .NET, Java EE/Jakarta hoặc ESB. Khi một phía thay đổi interceptor, những lỗi tương thích thường đến từ:

- QName của SOAP Header bị đổi.
- Payload namespace hoặc local name bị sửa.
- SOAP 1.1/1.2 không khớp Content-Type/Envelope.
- SOAPAction không khớp WSDL binding.
- WS-Addressing Action khác SOAPAction và chưa được xử lý.
- `mustUnderstand` yêu cầu một header processor mà partner không có.
- WS-Security dùng certificate chưa được trust hoặc signature parts không đúng.
- Client JAXB binding v1 không đọc được response với namespace v2/enum mới.
- Interceptor đọc rồi ghi lại XML làm thay đổi giá trị nil/absent/empty.

**Thêm một SOAP Header cũng có thể là breaking change** nếu partner từ chối header không được khai báo, không hiểu `mustUnderstand` hoặc yêu cầu nó có chữ ký.

Vì vậy, sau khi thay chain, hãy kiểm thử không chỉ payload XSD mà còn **Envelope, Header, SOAPAction, WS-Security policy và Fault**. Khi có thể, dùng client/tool độc lập với generated classes của bên cung cấp để tránh hai phía cùng che một sai lệch.

### 20.1. WSDL/XSD là hợp đồng; interceptor là triển khai

Một thay đổi về logging hoặc metric không cần đổi targetNamespace hay WSDL operation. Nếu đội phát triển buộc phải đổi XSD/WSDL để thêm thông tin nghiệp vụ, hãy quản lý hợp đồng version theo cách có kiểm thử tương thích, không giấu thay đổi trong ClientInterceptor.

Ví dụ, đổi `GetOrderRequest` thành `FindOrderRequest` là thay đổi root QName; không sửa bằng cách lấy XML của client cũ rồi đổi tên element trong một interceptor không được kiểm soát.

## 21. Hiệu năng và giới hạn tài nguyên

Một chain có nhiều interceptor sẽ thêm chi phí. Một vài metadata operations thường nhẹ, nhưng chi phí tăng đáng kể khi:

- Serialize toàn bộ request/response nhiều lần để log.
- Parse lại XML ở mỗi interceptor.
- Compile XSD hoặc nạp keystore ở mỗi request.
- Chạy XPath phức tạp trên DOM lớn.
- Ký và mã hóa XML payload lớn.
- Gửi log đến mạng đồng bộ trong request thread.
- Tạo retry đệ quy không giới hạn.

Các nguyên tắc:

1. Khởi tạo tài nguyên cấu hình ổn định lúc startup.
2. Không compile XSD cho từng SOAP request nếu có thể reuse an toàn.
3. Dùng `MessageContext` cho metadata per-call.
4. Giới hạn kích thước payload, độ sâu XML và timeout.
5. Ghi telemetry theo outcome và operation, tránh dữ liệu nhạy cảm.
6. Đo latency p50/p95/p99, CPU, memory, Fault và error rate.
7. Tách security overhead khỏi business logic khi benchmark.
8. Đừng giữ toàn bộ SOAP body vào singleton field hoặc ThreadLocal không được dọn đúng lúc.

### 21.1. XML parser security vẫn quan trọng ở client

XML từ partner là đầu vào từ bên ngoài, dù có TLS và chứng chỉ. Client SOAP message factory, JAXB, validators và transformers cần được cấu hình chống XXE/external entities, truy cập schema không tin cậy và resource exhaustion. Không dựa vào một interceptor để bảo vệ mọi parser nằm trong pipeline.

## 22. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Interceptor không chạy | Gắn vào nhầm template hoặc bị ghi đè bởi `setInterceptors` khác | Bean wiring, mảng interceptor, test |
| Không thấy SOAP header | Header sai QName, factory hoặc callback ghi đè | SoapMessage, QName, mock matcher |
| Correlation IDs bị trộn | Shared mutable field trong singleton | Context property per-call |
| SOAP Fault nhưng metric là success | Chỉ xử lý `handleResponse` | Thêm `handleFault` và fault tests |
| TLS timeout không chạy `handleFault` | Không có SOAP Fault response | Wrapper/transport metrics |
| Thêm WSS4J gây lỗi | Signed parts, trust/cert hoặc thứ tự interceptor | Policy, keystore, security tests |
| Server báo SOAPAction không đúng | Action callback/binding lệch | WSDL, SOAP version |
| Response bị unexpected element | QName/XSD/JAXB version sai | WSDL/XSD, JAXBContext, payload |
| Chỉ partner B lỗi | Dùng nhầm template hoặc interceptors của A | Per-partner config |
| Logging làm hệ thống chậm | Serialize XML nhiều lần | Sampling, metadata-only logging |
| afterCompletion bỏ sót một số lỗi | Exception xảy ra trước/ngoài chain | Adapter/transport observation |
| Server trả MustUnderstand Fault | Header mới bắt buộc nhưng partner không hiểu | SOAP header policy/role |
| Unit test pass, partner vẫn lỗi | Chỉ test Body, không test Header/Action/TLS | HTTP SOAP integration |

### 22.1. Quy trình debug một lỗi thực tế

Giả sử trước khi thêm Correlation interceptor, `GetOrder` chạy tốt; sau khi thêm, partner bắt đầu trả SOAP Fault:

1. Xác nhận interceptors đã gắn lên đúng `WebServiceTemplate`.
2. So WSDL payload root QName và SOAPAction trước/sau thay đổi.
3. Kiểm tra header QName theo URI/local name, không theo prefix.
4. Xác nhận partner chấp nhận hoặc yêu cầu header đó.
5. Nếu có WS-Security, kiểm tra header đã được ký theo policy và certificate được trust.
6. Đọc fault code/detail theo chính sách không lộ dữ liệu nhạy cảm.
7. Dùng `MockWebServiceServer` để xác nhận outbound Envelope, Body, Header.
8. Chạy integration test với môi trường partner được phép, không thử tùy tiện ở production.
9. Không dùng `handleFault=false` hoặc vô hiệu hóa WS-Security chỉ để bỏ qua lỗi.

## 23. Bài thực hành: GetOrderClient có telemetry và WS-Security

Thiết kế client gọi `GetOrder` với contract ở phần 4:

1. Tạo JAXB binding từ XSD/WSDL hoặc dùng Source fixtures cho test ban đầu.
2. Khởi tạo `WebServiceTemplate` với JAXB marshaller/unmarshaller phù hợp.
3. Viết `ClientCorrelationInterceptor` để thêm `{urn:example:common:v1}CorrelationId`.
4. Viết `ClientObservationInterceptor` lưu start time và outcome theo từng `MessageContext`.
5. Thêm WS-Security interceptor theo policy đối tác (không hard-code secret).
6. Chọn thứ tự để header được tạo trước chữ ký, response được verify trước khi tin cậy nội dung.
7. Thêm `SoapActionCallback` theo WSDL binding khi cần.
8. Test outbound Body và SOAP Header với `MockWebServiceServer`.
9. Test successful response, SOAP Fault và transport exception riêng.
10. Test callback order ở cả request/response/Fault và nhánh `false`.
11. Test concurrency để không trộn correlation IDs.
12. Test response với QName v2 bị từ chối khi binding client chỉ hỗ trợ v1.
13. Đo overhead telemetry/security trên payload size đại diện.
14. Thử client qua HTTPS và certificate trust trong môi trường kiểm thử hợp lệ.

**Tiêu chí hoàn thành:** Client gửi XML hợp contract, SOAP headers đúng QName/policy, interceptor order được kiểm chứng, lỗi được phân loại, không có shared mutable per-call state và không làm lộ payload nhạy cảm.

## 24. Checklist trước khi triển khai ClientInterceptor

- [ ] Phân biệt `ClientInterceptor` phía client với `EndpointInterceptor` phía server.
- [ ] Xác định mỗi interceptor đảm nhiệm một trách nhiệm cross-cutting rõ ràng.
- [ ] `WebServiceTemplate` có đúng JAXB binding, SOAP factory, sender, URL và action.
- [ ] Mảng interceptors được khai báo theo thứ tự có chủ đích.
- [ ] `handleRequest` không làm hỏng QName, XML Schema, SOAP headers.
- [ ] `handleResponse` không tự coi mọi SOAP response là business success.
- [ ] `handleFault` quan sát Fault nhưng không nuốt lỗi của resolver.
- [ ] `afterCompletion` cleanup an toàn; lỗi xảy ra ngoài chain có wrapper/transport metrics.
- [ ] Không dùng `false` cho short-circuit nếu chưa test semantics thực tế.
- [ ] Correlation/tracing per-call không nằm trong mutable singleton field.
- [ ] SOAP Header và `mustUnderstand`/signed parts đáp ứng policy của partner.
- [ ] WS-Security, certificate trust, key rotation và TLS được cấu hình riêng.
- [ ] Không log raw SOAP Body, tokens, passwords, private keys hoặc Fault Detail nhạy cảm.
- [ ] Retry có timeout budget và idempotency policy, không nằm đệ quy trong `handleFault`.
- [ ] Có kiểm thử XSD/WSDL cho outbound request và inbound response.
- [ ] Có `MockWebServiceServer` tests cho payload, header, chain order, Fault.
- [ ] Có transport HTTP/TLS tests và interoperability tests khi cần.
- [ ] Đã đo metrics cardinality, latency, CPU, memory và concurrency.

## 25. Ghi nhớ

- **ClientInterceptor là extension point phía client của WebServiceTemplate** cho bốn hook: request, response, Fault và completion.
- **Callback order có ảnh hưởng đến security**: correlation header cần được thêm trước khi ký, inbound response cần verify đúng chính sách.
- **MessageContext giữ trạng thái theo lượt gọi**, tránh trộn dữ liệu giữa những request threads.
- **SOAP Fault khác transport/JAXB/schema exception**; interceptor quan sát Fault không thay thế FaultMessageResolver.
- **JAXB/OXM, XSD validation, SOAPAction, TLS và WS-Security là những tầng riêng**; không ép mọi logic vào một interceptor.
- **Contract-first luôn là ranh giới:** mọi thay đổi Header/Body/Action/security policy cần kiểm tra WSDL/XSD và tương thích với đối tác.

**Câu hỏi tự kiểm tra:** Bạn có ba interceptors `Observation`, `Correlation` và `Security`. Đối tác yêu cầu Header `CorrelationId` được ký, còn response phải được xác minh chữ ký trước khi ứng dụng tin cậy dữ liệu. Bạn sẽ đăng ký ba interceptors theo thứ tự nào? Khi đối tác trả SOAP Fault do sai chữ ký, callback nào có thể được gọi, và callback nào có thể không chạy khi lỗi xảy ra tại TLS handshake? Nêu ít nhất ba test để kiểm chứng và tránh nuốt lỗi.



