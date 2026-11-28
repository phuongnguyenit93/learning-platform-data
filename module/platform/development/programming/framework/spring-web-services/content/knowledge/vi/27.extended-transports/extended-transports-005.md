# Thông điệp một chiều, phản hồi và giới hạn thời gian chờ

Một SOAP client gọi operation thành công không có nghĩa nó luôn nhận một SOAP response. Có operation chỉ nhận thông điệp rồi xử lý; operation khác cần trả kết quả ngay trong cùng lượt trao đổi; còn một số tích hợp gửi yêu cầu vào queue và nhận kết quả qua một kênh khác sau vài giây hoặc vài phút. Nếu ứng dụng coi mọi trường hợp là request–response đồng bộ, nó dễ giữ thread quá lâu, retry gây trùng nghiệp vụ hoặc hiểu nhầm **HTTP 202 / JMS enqueue acknowledgment** là kết quả business.

Trong **Spring Web Services (Spring-WS)**, `WebServiceTemplate` cung cấp API gửi/nhận SOAP message, còn các `WebServiceMessageSender` triển khai transport như **HTTP, JMS, email và XMPP**. Mỗi transport có hành vi phản hồi và giới hạn chờ riêng. Để chọn đúng mô hình, cần phân biệt **message exchange pattern (MEP)** trong hợp đồng WSDL, **acknowledgment của transport**, **SOAP response/Fault**, và **kết quả nghiệp vụ bất đồng bộ**.

Bài học thuộc chương **Truyền tải mở rộng** của module **SPRING_WEB_SERVICES**: phát triển dịch vụ SOAP contract-first với XSD/WSDL, JAXB/OXM, endpoint và SOAP client, đồng thời xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích doanh nghiệp. Trọng tâm là lựa chọn **thông điệp một chiều, phản hồi và giới hạn thời gian chờ** phù hợp; cấu hình HTTP/JMS; xử lý response đến muộn, retry, correlation và idempotency.

## 1. Bốn loại “xác nhận” cần phân biệt

Một giao dịch SOAP có thể có nhiều mốc xác nhận khác nhau:

| Loại xác nhận | Ý nghĩa | Ví dụ | Chưa chứng minh được |
| --- | --- | --- | --- |
| **Transport accepted** | Transport đã nhận/gửi message ở mức giao thức | HTTP `202 Accepted`, broker nhận JMS `send()` | Endpoint đã xử lý hoặc nghiệp vụ đã commit |
| **SOAP response** | SOAP peer đã trả message response theo MEP | `SubmitOrderResponse` hoặc SOAP Fault | Các tác dụng phụ phía sau đã hoàn tất bền vững nếu response không cam kết điều đó |
| **Application acknowledgment** | Ứng dụng xác nhận đã tiếp nhận một yêu cầu theo contract | `accepted=true`, `requestId=...` | Công việc nền đã hoàn thành |
| **Business completion** | Nghiệp vụ đã hoàn tất theo định nghĩa hợp đồng | `status=COMPLETED`, hóa đơn đã phát hành | Hệ thống downstream khác đã đồng bộ nếu chưa có cam kết |

Ví dụ client POST tới HTTP endpoint và nhận `202 Accepted`. Nó chỉ biết server/proxy **đã chấp nhận request để xử lý** theo semantics của HTTP. Nếu hợp đồng yêu cầu kết quả cuối cùng, client vẫn cần polling, callback hoặc một request tra cứu trạng thái bằng `requestId`.

**Không được gộp** “đã gửi”, “đã nhận vào queue”, “đã xử lý SOAP”, “đã commit nghiệp vụ” thành một trạng thái `SUCCESS`.

## 2. Mô hình message exchange pattern

Trong WSDL 1.1, hai kiểu operation thường gặp:

| WSDL operation | Message exchange | Ý nghĩa |
| --- | --- | --- |
| **One-way** | Một `input` message | Consumer nhận request; không có `output` message trong operation |
| **Request-response** | `input` rồi `output`, hoặc Fault | Caller gửi request và chờ response trong lượt trao đổi |

WSDL mô tả **contract logic**. Binding và transport quy định cách trao đổi message trên dây; không phải mọi one-way operation đều biến thành một HTTP POST không có phản hồi transport.

### 2.1. One-way operation trong WSDL

Ví dụ operation `SubmitOrder` chỉ có input:

~~~xml
<wsdl:portType name="OrderPortType"
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:tns="urn:example:orders:v1">
    <wsdl:operation name="SubmitOrder">
        <wsdl:input message="tns:SubmitOrderRequestMessage"/>
    </wsdl:operation>
</wsdl:portType>
~~~

**Đây là trích đoạn portType**, còn WSDL đầy đủ cần khai báo `wsdl:message`, `wsdl:binding`, `wsdl:service`/`port` và địa chỉ transport. Không có `wsdl:output` trong operation này: caller không chờ một SOAP output message theo MEP.

Ví dụ `GetOrderStatus` là request-response:

~~~xml
<wsdl:operation name="GetOrderStatus">
    <wsdl:input message="tns:GetOrderStatusRequestMessage"/>
    <wsdl:output message="tns:GetOrderStatusResponseMessage"/>
    <wsdl:fault name="OrderFault" message="tns:OrderFaultMessage"/>
</wsdl:operation>
~~~

Caller chờ một response hoặc Fault. Điều đó không có nghĩa client phải chờ vô hạn; timeout vẫn là một phần của thiết kế runtime.

### 2.2. Sơ đồ luồng một chiều và request-response

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant T as Transport
    participant S as SOAP server
    participant B as Business service
    C->>T: SubmitOrder request
    T->>S: Deliver SOAP message
    S->>B: Accept / enqueue
    B-->>S: Accepted (theo contract)
    S-->>T: Transport acknowledgment
    T-->>C: HTTP 202 / transport result
    Note over B: Công việc có thể tiếp tục sau đó
~~~

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant T as HTTP/JMS
    participant S as SOAP server
    participant B as Business service
    C->>T: GetOrderStatus request
    T->>S: Deliver SOAP message
    S->>B: Execute query
    B-->>S: Status result
    S-->>T: SOAP response
    T-->>C: Response within receive deadline
~~~

Trong luồng thứ nhất, HTTP hoặc broker vẫn có thể trả tín hiệu ở tầng transport trong khi công việc nền chưa xong. Trong luồng thứ hai, client giữ lời gọi đến khi nhận response/Fault hoặc hết giới hạn chờ.

## 3. One-way không đồng nghĩa “không có bất kỳ phản hồi nào”

Đây là điểm dễ gây lỗi thiết kế:

- **WSDL one-way:** operation không định nghĩa SOAP output message.
- **HTTP:** server vẫn phải hoàn tất HTTP exchange bằng status/headers; có thể trả `202 Accepted` hoặc status khác theo binding/implementation.
- **JMS:** message sender gửi JMS Message; nếu không dùng request/reply, client không cần một SOAP reply message.
- **Application acknowledgment:** có thể nằm ngay trong HTTP status, JMS send result hoặc một message riêng, nhưng semantics phải được contract mô tả.
- **Callback/status query:** nếu muốn biết kết quả sau xử lý, cần một operation/message khác có correlation rõ ràng.

`HTTP 202` không phải SOAP response body và không chứng minh database transaction đã commit. Tương tự, lệnh `JmsTemplate.send(...)` trả về không chứng minh listener đã xử lý message.

### 3.1. Ba thiết kế có vẻ giống nhau nhưng khác contract

| Thiết kế | Request | Phản hồi | Dùng cho |
| --- | --- | --- | --- |
| **Fire-and-forget** | SOAP one-way message | Không có SOAP output; có thể có transport acceptance | Event/notification không cần kết quả ngay |
| **Synchronous request-response** | SOAP input | SOAP output hoặc Fault | Tra cứu/command cần kết quả tức thời |
| **Asynchronous command + status** | SOAP submit | Ack chứa request ID; kết quả truy vấn/callback sau | Công việc dài, xử lý nền, tích hợp queue |

Nếu một API nhận đơn hàng rồi trả `SubmitOrderResponse` chứa `requestId`, hãy xem đó là **acknowledgment theo application contract**. Operation WSDL lúc này là request-response, dù nghiệp vụ chưa hoàn tất.

## 4. Spring-WS WebServiceTemplate: gửi và nhận response

`WebServiceTemplate` là client abstraction trung tâm. Nó sử dụng `WebServiceMessageFactory` để tạo SOAP message và `WebServiceMessageSender` để gửi qua URI/transport. Các API `marshalSendAndReceive`, `sendAndReceive` hoặc `sendSourceAndReceive` đều thiết kế cho luồng **gửi rồi đọc response nếu có**.

Ví dụ request-response với JAXB:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;

public final class OrderClient {
    private final WebServiceTemplate template;

    public OrderClient(WebServiceTemplate template) {
        this.template = template;
    }

    public GetOrderStatusResponse getStatus(
            GetOrderStatusRequest request) {
        Object response = template.marshalSendAndReceive(
                "https://api.example.org/soap/orders",
                request);
        if (response == null) {
            throw new IllegalStateException(
                    "Không nhận SOAP response cho operation request-response");
        }
        return (GetOrderStatusResponse) response;
    }
}
~~~

Ví dụ giả định JAXB generated model và marshaller/unmarshaller được cấu hình đúng. Tùy API/MEP và transport, `WebServiceTemplate` có thể trả `null` khi không nhận được response; không ép mọi `null` thành thành công nếu contract yêu cầu output.

### 4.1. Boolean/response callback biểu thị điều gì?

Một overload `sendAndReceive(...)` nhận callback để xử lý response có thể trả về `true` nếu response được nhận và `false` nếu không có response. Đây là **trạng thái nhận message của client API**, không phải cờ xác nhận transaction nghiệp vụ.

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;

boolean responseReceived = template.sendAndReceive(
        requestMessage -> {
            // Tạo SOAP request Header/Body theo contract.
        },
        responseMessage -> {
            // Đọc SOAP response trong callback.
        });

if (!responseReceived) {
    // Không nhận response trong trao đổi này.
}
~~~

Đây là **khung minh họa API**, cần dùng đúng callback/import của phiên bản Spring-WS. Không dùng callback để che SOAP Fault hoặc tự suy ra nghiệp vụ đã thành công.

### 4.2. API gửi một message

Spring-WS client API có các overload `sendAndReceive`/`marshalSendAndReceive` tập trung vào request-response. Với transport one-way, việc peer không gửi SOAP output không có nghĩa mọi tầng đều không có response; ví dụ HTTP vẫn trả status. **Phải chọn đúng sender/connection semantics và kiểm tra behavior của binding**.

Một lựa chọn khác là dùng transport API phù hợp trực tiếp (ví dụ producer JMS cho one-way event) khi ứng dụng cần **gửi message vào broker và không chờ SOAP reply**. Khi đó bạn tự quản lý destination, message conversion, delivery mode, transaction/ack và correlation theo kiến trúc. Không giả định một overload request-response của `WebServiceTemplate` tự trở thành message queue fire-and-forget chỉ bằng việc giảm timeout về 0.

## 5. Thiết kế contract cho submit, acknowledgment và status query

Một mô hình bất đồng bộ thực tế nên có ba operations:

1. `SubmitDocument`: nhận lệnh, kiểm tra hợp đồng và trả acknowledgment với `requestId`.
2. `GetDocumentStatus`: tra trạng thái theo `requestId`.
3. `CancelDocument` (nếu business cho phép): yêu cầu hủy, trả kết quả tiếp nhận yêu cầu hủy.

### 5.1. XSD minh họa

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:doc="urn:example:documents:v1"
           targetNamespace="urn:example:documents:v1"
           elementFormDefault="qualified">

  <xs:simpleType name="ProcessingStatus">
    <xs:restriction base="xs:string">
      <xs:enumeration value="ACCEPTED"/>
      <xs:enumeration value="PROCESSING"/>
      <xs:enumeration value="COMPLETED"/>
      <xs:enumeration value="FAILED"/>
      <xs:enumeration value="CANCELLED"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="SubmitDocumentRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="clientRequestId" type="xs:string"/>
        <xs:element name="documentName" type="xs:string"/>
        <xs:element name="content" type="xs:base64Binary"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="SubmitDocumentResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="xs:string"/>
        <xs:element name="status" type="doc:ProcessingStatus"/>
        <xs:element name="acceptedAt" type="xs:dateTime"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetDocumentStatusRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetDocumentStatusResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="xs:string"/>
        <xs:element name="status" type="doc:ProcessingStatus"/>
        <xs:element name="resultReference" type="xs:anyURI"
                    minOccurs="0"/>
        <xs:element name="failureCode" type="xs:string"
                    minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Đây là schema rút gọn để minh họa contract. Trong dự án thực, tách type dùng lại, định nghĩa giới hạn độ dài/pattern cho IDs, xử lý `minOccurs`/`nillable` rõ ràng, quy định bảo mật result reference và công bố fault details.

### 5.2. Status là state machine có quy tắc

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> PROCESSING
    PROCESSING --> COMPLETED
    PROCESSING --> FAILED
    ACCEPTED --> CANCELLED
    PROCESSING --> CANCELLED
~~~

`COMPLETED`, `FAILED` và `CANCELLED` là trạng thái kết thúc trong ví dụ. Hệ thống cần định nghĩa trạng thái nào có thể chuyển tiếp, thời gian lưu status, cách xử lý cancel đến muộn và liệu `FAILED` có retry tự động hay cần một request mới. Đừng để client tự suy đoán trạng thái từ thời gian phản hồi.

### 5.3. Endpoint nhận và trả acknowledgment

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class DocumentSubmissionEndpoint {
    private static final String NS = "urn:example:documents:v1";
    private final DocumentSubmissionService service;

    public DocumentSubmissionEndpoint(
            DocumentSubmissionService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "SubmitDocumentRequest")
    @ResponsePayload
    public SubmitDocumentResponse submit(
            @RequestPayload SubmitDocumentRequest request) {
        AcceptedDocument accepted = service.accept(request);

        SubmitDocumentResponse response = new SubmitDocumentResponse();
        response.setRequestId(accepted.requestId());
        response.setStatus(ProcessingStatus.ACCEPTED);
        response.setAcceptedAt(accepted.acceptedAt());
        return response;
    }
}
~~~

Đây là khung minh họa: generated JAXB classes và `DocumentSubmissionService` do ứng dụng cung cấp. Acknowledgment chỉ nên được trả sau khi hệ thống đã **lưu yêu cầu một cách bền vững** hoặc đạt đúng semantics mà contract cam kết. Nếu chỉ đặt task vào in-memory executor rồi trả `ACCEPTED`, tiến trình restart có thể làm mất việc đã được xác nhận.

## 6. Tách tiếp nhận khỏi xử lý bằng queue

Với công việc dài, endpoint có thể lưu request và phát event qua broker. Một mô hình phổ biến:

~~~mermaid
flowchart LR
    C["SOAP client"] --> H["Spring-WS endpoint"]
    H --> DB["Database<br/>request + status"]
    H --> O["Outbox record"]
    O --> P["Outbox publisher"]
    P --> Q["JMS queue"]
    Q --> W["Worker/consumer"]
    W --> B["Business processing"]
    B --> DB
    C --> S["GetDocumentStatus SOAP"]
    S --> DB
~~~

Lưu request/status và outbox record trong **cùng một database transaction** giúp tránh trường hợp DB đã ghi request nhưng event chưa gửi, hoặc event gửi rồi DB rollback. Publisher có thể gửi lại outbox item; consumer vì thế vẫn cần idempotency.

### 6.1. JMS receiver phía server

Spring-WS cung cấp `WebServiceMessageListener` để gắn `MessageDispatcher` với Spring JMS `MessageListenerContainer`. Ví dụ cấu hình khái niệm:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.jms.WebServiceMessageListener;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;
import org.springframework.ws.soap.server.SoapMessageDispatcher;

@Configuration
public class JmsSoapReceiverConfiguration {

    @Bean
    public SaajSoapMessageFactory jmsSoapMessageFactory() {
        return new SaajSoapMessageFactory();
    }

    @Bean
    public WebServiceMessageListener jmsSoapListener(
            SaajSoapMessageFactory messageFactory,
            SoapMessageDispatcher messageDispatcher) {
        WebServiceMessageListener listener =
                new WebServiceMessageListener();
        listener.setMessageFactory(messageFactory);
        listener.setMessageReceiver(messageDispatcher);
        return listener;
    }
}
~~~

Đây là phần wiring rút gọn để giải thích vai trò listener; ứng dụng chạy thật còn phải cấu hình `ConnectionFactory`, listener container, destination, transaction manager, concurrency, error handler và các beans `MessageDispatcher`/endpoint mapping tương thích. **Không copy đoạn này rồi mặc định rằng listener container đã được tạo hoặc queue đã được provision.**

### 6.2. JMS sender phía client

Spring-WS có `JmsMessageSender`, dùng `ConnectionFactory` của Spring để chuyển `WebServiceMessage` thành JMS message. URI có thể có dạng:

~~~text
jms:SubmitOrderQueue
jms:SubmitOrderQueue?deliveryMode=PERSISTENT
jms:RequestQueue?replyToName=ResponseQueue
jms:RequestQueue?priority=7&deliveryMode=PERSISTENT
~~~

Theo Spring-WS Reference 4.1.4, `JmsMessageSender` mặc định dùng `BytesMessage`; `TextMessage` có thể cấu hình qua `messageType=TEXT_MESSAGE`, nhưng **BytesMessage được khuyến nghị** vì TextMessage không hỗ trợ attachment và character encoding đáng tin cậy bằng. Nếu có `replyToName`, sender có thể dùng destination trả lời được chỉ định; nếu không, mặc định là temporary queue. [Tài liệu Spring-WS — JMS transport](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/#transports-jms)

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.jms.JmsMessageSender;

@Configuration
public class JmsSoapClientConfiguration {

    @Bean
    public JmsMessageSender jmsMessageSender(
            ConnectionFactory connectionFactory) {
        JmsMessageSender sender = new JmsMessageSender();
        sender.setConnectionFactory(connectionFactory);
        sender.setReceiveTimeout(5_000);
        return sender;
    }

    @Bean
    public WebServiceTemplate jmsSoapTemplate(
            JmsMessageSender sender) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri("jms:RequestQueue?replyToName=ResponseQueue");
        template.setMessageSender(sender);
        return template;
    }
}
~~~

Đây là ví dụ sender cấu hình theo Spring-WS 4.1 / Jakarta JMS; cần cấu hình message factory, marshaller/unmarshaller nếu dùng POJO, và endpoint/broker thật. `setReceiveTimeout(5_000)` là **5 giây chờ response JMS**, không phải timeout tổng của toàn bộ công việc nghiệp vụ. Giá trị thực tế phải theo contract và SLA. Nếu queue chỉ dùng one-way, chọn sender/API/delivery semantics không chờ reply; đừng giả định giảm receive timeout sẽ biến request-response thành one-way đúng contract.

## 7. Transport JMS: request/reply, queue và timeout

JMS phù hợp khi hai hệ thống cần tách thời gian xử lý hoặc không muốn caller giữ HTTP connection dài. Tuy nhiên phải phân biệt:

- **Queue:** một consumer cạnh tranh nhận một message theo semantics broker/consumer.
- **Topic:** phát tới subscribers theo subscription semantics; durable/non-durable subscriptions ảnh hưởng delivery.
- **Temporary reply queue:** thuận tiện cho request/reply, nhưng vòng đời gắn với connection/session và không thích hợp để thay thế callback lâu dài sau khi client disconnect.
- **Named reply queue:** có thể dùng cho response/callback ổn định, nhưng cần correlation ID và quyền consume riêng.
- **Persistent delivery:** broker được yêu cầu lưu message bền vững theo cấu hình broker/store/transaction; không có nghĩa consumer đã xử lý.

### 7.1. Receive timeout của JmsMessageSender

`JmsMessageSender.setReceiveTimeout(long)` điều khiển giới hạn chờ khi gọi receive:

| Giá trị | Ý nghĩa của Spring JMS/JmsMessageSender | Hệ quả |
| --- | --- | --- |
| `-1` | Chờ vô hạn | Thread có thể bị giữ mãi nếu không có response |
| `0` | Không chờ/receive ngay theo semantics Spring JMS | Có thể chưa có response dù request đã được gửi |
| `> 0` | Chờ tối đa số milliseconds | Hết thời gian, caller không nhận response trong lượt đó |

Giá trị mặc định của `JmsMessageSender` là `-1` theo API Spring-WS 4.1.4, tức **blocking receive không timeout**. Đừng để mặc định này tồn tại ngoài ý muốn trong hệ thống request-response. [JmsMessageSender API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/jms/JmsMessageSender.html)

**Receive timeout = 0 không có nghĩa là message one-way bền vững hoặc đã được broker xác nhận xử lý.** Nó chỉ thay đổi hành vi chờ response; cần xác định producer send completion, transacted session, persistent delivery, broker acknowledgment và consumer processing độc lập.

### 7.2. JMS replyTo và correlation

Trong request/reply, request message có thể mang `JMSReplyTo` và correlation identifier. Response cần liên hệ đúng request:

~~~text
Request:
  JMSMessageID = ID-1001
  JMSReplyTo   = ResponseQueue

Response:
  JMSCorrelationID = ID-1001
~~~

Đây là mô hình minh họa. Spring-WS/JMS sender/receiver quản lý một phần chi tiết theo URI/destination resolver; ứng dụng cần kiểm tra broker/provider và cách response được correlate, đặc biệt khi dùng named reply queues hoặc nhiều concurrent calls.

Không sử dụng một reply queue duy nhất mà không có correlation strategy: phản hồi request A có thể bị gán cho request B khi có nhiều lời gọi đồng thời.

## 8. HTTP transport: kết nối, nhận response và timeout

Với HTTP, `WebServiceTemplate` gọi `WebServiceMessageSender`. Spring-WS 4.1 có các sender:

- `HttpUrlConnectionMessageSender`: dựa trên HTTP facilities của JDK.
- `JdkHttpClientMessageSender`: dùng JDK `HttpClient`.
- `HttpComponents5MessageSender` và `SimpleHttpComponents5MessageSender`: dựa trên Apache HttpClient 5, phù hợp khi cần authentication, pooling và cấu hình nâng cao.

Ví dụ Spring-WS 4.1:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.HttpComponents5MessageSender;

@Configuration
public class SoapHttpTransportConfiguration {

    @Bean
    public HttpComponents5MessageSender soapMessageSender() {
        HttpComponents5MessageSender sender =
                new HttpComponents5MessageSender();
        sender.setConnectionTimeout(Duration.ofSeconds(3));
        sender.setReadTimeout(Duration.ofSeconds(15));
        sender.setMaxTotalConnections(100);
        return sender;
    }
}
~~~

Đoạn này minh họa API `Duration` và pool của Spring-WS 4.1; cần kiểm tra cấu hình `RequestConfig`/connection lease và TLS theo sender/provider đang dùng. **Connect timeout 3 giây không phải tổng deadline 3 giây**, và read timeout 15 giây không nhất thiết giới hạn thời gian chờ connection pool hoặc toàn bộ nhiều lần gửi/đọc. `HttpComponents5MessageSender.setHttpClient(...)` được đánh dấu deprecated từ Spring-WS 4.1.0 để chuyển sang `SimpleHttpComponents5MessageSender`; khi cần custom HttpClient 5, dùng API được khuyến nghị của đúng phiên bản. [Spring-WS HttpComponents5MessageSender API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/http/HttpComponents5MessageSender.html)

### 8.1. Phân biệt các loại thời gian chờ

| Timeout | Đo thời gian nào? | Lỗi thường gặp |
| --- | --- | --- |
| **DNS/connect timeout** | Phân giải tên/kết nối TCP | Host unreachable, connection refused |
| **TLS handshake timeout** | Thương lượng TLS/chứng chỉ | Handshake stall/failure |
| **Connection pool lease timeout** | Chờ một connection khả dụng | Pool exhausted/lease timeout |
| **Response/read timeout** | Chờ dữ liệu response hoặc lần đọc kế tiếp theo implementation | Socket read timeout |
| **JMS receive timeout** | Chờ response message từ reply destination | Receive timeout / no response |
| **Application deadline** | Tổng thời gian nghiệp vụ caller cho phép | Hủy/chuyển trạng thái timeout ở ứng dụng |
| **Broker message TTL** | Thời gian message còn sống trong broker | Message hết hạn/dead-letter theo policy |
| **Server processing deadline** | Thời gian endpoint/worker được phép xử lý | Server timeout/cancel nếu hỗ trợ |

Không có một tham số `timeout` duy nhất tự giới hạn tất cả các tầng. Với retry, tổng deadline cần tính cả thời gian backoff và mỗi lần attempt.

### 8.2. Ví dụ ngân sách thời gian

~~~text
Overall application deadline:     20 s
Connection pool lease:              1 s
DNS/connect:                        3 s
TLS handshake:                      2 s (nếu cấu hình riêng)
Response/read:                     12 s
Client-side processing/margin:      2 s
~~~

Đây chỉ là **ngân sách minh họa**, không cộng tuyến tính máy móc nếu các pha overlap hoặc timeout được áp dụng lặp lại theo chunk. Cần đo p95/p99 và biết chính xác sender áp từng tham số ở đâu.

## 9. Email và XMPP: transport phản hồi không giống HTTP/JMS

Spring-WS 4.1 vẫn mô tả các transport mở rộng:

### 9.1. Email transport

`MailMessageSender` gửi SOAP request qua SMTP, rồi chờ phản hồi được gửi về mailbox truy xuất bằng POP3/IMAP. Cấu hình cần:

- `defaultUri` dạng `mailto:...`.
- `transportUri` là server gửi (thường SMTP).
- `storeUri` là server nhận/đọc response (POP3 hoặc IMAP).
- `receiveTimeout`/mail polling theo API và cấu hình client.

API Spring-WS 4.1.4 ghi default receive timeout của `MailMessageSender` là **60 giây**. Đây là thời gian chờ response, không phải đảm bảo email/SOAP operation hoàn tất trong một phút. [MailMessageSender API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/mail/MailMessageSender.html)

Email có thể đến muộn, trùng hoặc không đúng thứ tự; cần correlation, xử lý thư không hợp lệ, xác thực sender và bảo vệ dữ liệu nhạy cảm. Không dùng mailbox polling làm cơ chế đồng bộ có SLA thấp.

### 9.2. XMPP transport

`XmppMessageSender` gửi SOAP message qua XMPP và lắng nghe response. Cần cấu hình connection và destination JID/URI theo môi trường. Client phải xử lý disconnect, presence/session, message delivery semantics và response timeout theo provider. Gửi XMPP stanza thành công không tự có nghĩa nghiệp vụ được hoàn tất.

Transport này chỉ phù hợp khi cả hai phía có hạ tầng XMPP và quy định rõ identity, connection lifecycle và routing; nó không phải lựa chọn thay thế HTTP chỉ bằng cách đổi URI.

## 10. Timeout không đồng nghĩa hủy tác vụ

Đây là một trong những lỗi thiết kế phổ biến nhất:

1. Client gửi `PlaceOrder`.
2. Server nhận và bắt đầu xử lý.
3. Client hết read timeout sau 10 giây.
4. Client không nhận response nên đánh dấu “failed”.
5. Server hoàn tất và commit đơn hàng sau 12 giây.
6. Client retry request vì nghĩ lần đầu thất bại.
7. Server tạo đơn thứ hai nếu không có idempotency.

Timeout ở client chỉ cho biết **client không nhận được response trong thời hạn**, không cho biết server có dừng công việc hay không. TCP connection đóng không tự rollback transaction database, queue message hoặc worker đã bắt đầu.

### 10.1. Phân loại trạng thái client

~~~mermaid
stateDiagram-v2
    [*] --> NOT_SENT
    NOT_SENT --> SENT
    SENT --> RESPONSE_RECEIVED
    SENT --> TIMED_OUT_UNKNOWN
    TIMED_OUT_UNKNOWN --> RECONCILING
    RECONCILING --> COMPLETED
    RECONCILING --> FAILED
    RECONCILING --> ACCEPTED
    ACCEPTED --> PROCESSING
    PROCESSING --> COMPLETED
    PROCESSING --> FAILED
~~~

Sau timeout, trạng thái đúng thường là **UNKNOWN / OUTCOME_UNKNOWN**, không tự kết luận FAILED. Client cần truy vấn theo idempotency key/request ID hoặc gọi API tra cứu trạng thái trước khi gửi lại command tạo side effect.

### 10.2. Server cần deadline và cancellation semantics riêng

Server/worker có thể áp deadline để hạn chế tài nguyên, nhưng:

- Deadline của server cần lớn hơn hoặc phối hợp rõ với budget caller.
- Cancellation phải được truyền tới tầng thực thi có hỗ trợ; đóng HTTP response không tự cancel DB/job.
- Nếu công việc đã commit, yêu cầu hủy đến muộn phải trả trạng thái phù hợp.
- Khi dùng queue, message TTL có thể làm message hết hạn trước khi consumer nhận; nó không nhất thiết hủy tác vụ đã được consumer xử lý.
- Phải ghi trạng thái và correlation để client có thể reconciliation.

## 11. Retry, idempotency và delivery semantics

Timeout và transport error thường tạo **kết quả không chắc chắn**: server có thể đã xử lý nhưng response bị mất. Vì vậy không retry mù quáng mọi SOAP call.

| Operation | Retry strategy | Điều kiện |
| --- | --- | --- |
| Read-only `GetOrderStatus` | Thường có thể retry có giới hạn | Chấp nhận dữ liệu hơi cũ/cùng snapshot theo contract |
| `SubmitOrder` tạo side effect | Retry với cùng idempotency key | Server phải deduplicate và trả cùng logical result |
| `CancelOrder` | Retry có kiểm soát, semantics idempotent | Cancel đã hoàn tất không tạo tác dụng phụ mới |
| Payment/transfer | Không retry mù | Idempotency, reconciliation và business reference bắt buộc |
| JMS consumer xử lý event | Có thể redeliver | Consumer idempotent, transaction/ack đúng |

### 11.1. Idempotency key trong contract

Ví dụ request có `clientRequestId`:

~~~xml
<doc:SubmitDocumentRequest
    xmlns:doc="urn:example:documents:v1">
    <doc:clientRequestId>client-42-request-9001</doc:clientRequestId>
    <doc:documentName>report.pdf</doc:documentName>
    <doc:content>BASE64_DATA</doc:content>
</doc:SubmitDocumentRequest>
~~~

Server lưu cặp khóa:

~~~text
authenticatedPartnerId + clientRequestId
           ↓
unique constraint / idempotency record
           ↓
payload fingerprint + request status + response reference
~~~

Nếu cùng partner gửi lại cùng `clientRequestId` và payload tương đương, server trả lại `requestId`/kết quả đã biết thay vì tạo tác vụ mới. Nếu key giống nhưng payload khác, trả conflict/Fault theo contract; không silently dùng kết quả cũ cho nội dung khác.

**Idempotency key không phải authorization token.** Nó phải được scope theo principal/tenant đã xác minh; nếu là giá trị do client tự chọn, không cho phép đoán hoặc truy cập trạng thái request của người khác.

### 11.2. Exponential backoff và jitter

Ví dụ lịch retry có giới hạn:

~~~text
attempt 1: immediately
attempt 2: 500 ms + random jitter
attempt 3: 1 s + random jitter
attempt 4: 2 s + random jitter
stop: overall deadline reached or non-retryable fault
~~~

Đây là lịch minh họa. Thực tế cần retry budget, max attempts, random jitter, circuit breaker và phân biệt lỗi transient (connection reset, temporary 503) với lỗi permanent (XSD invalid, authorization denied, certificate trust failure). Không retry ngay lập tức theo vòng lặp không giới hạn.

## 12. Correlation ID, MessageID và business request ID

Ba loại định danh có nhiệm vụ khác nhau:

| Identifier | Dùng để | Ví dụ |
| --- | --- | --- |
| **Transport correlation** | Gắn response JMS với request hoặc kết nối/trace của transport | `JMSCorrelationID` |
| **WS-Addressing MessageID / RelatesTo** | Định danh SOAP message và liên kết response với request | `urn:uuid:...` |
| **Business request ID / idempotency key** | Nhận diện một command nghiệp vụ trong các lần retry | `clientRequestId=...` |

Không dùng `MessageID` làm idempotency key nếu contract không cam kết semantics đó: một retry hợp lệ có thể tạo MessageID mới, nhưng vẫn phải được nhận diện là cùng một business request qua idempotency key.

### 12.1. WS-Addressing ActionCallback

Spring-WS hỗ trợ WS-Addressing ở client bằng `ActionCallback`; callback có thể đặt `Action` và `To`, còn MessageID/correlation có thể dùng theo policy và message exchange. Ví dụ:

~~~java
import java.net.URI;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing10;

ActionCallback callback = new ActionCallback(
        URI.create("urn:example:documents:action:SubmitDocument"),
        new Addressing10(),
        URI.create("https://api.example.org/soap/documents"));

Object ack = template.marshalSendAndReceive(
        request, callback);
~~~

Ví dụ giả định template được cấu hình đúng JAXB, SOAP message factory và transport. `ActionCallback` tạo WS-Addressing message headers; nó **không tự biến request-response thành asynchronous processing**, không tạo queue và không thay business request ID.

### 12.2. Callback response bất đồng bộ

Nếu hợp đồng dùng non-anonymous `ReplyTo`, server có thể gửi message mới đến callback endpoint. Kiến trúc cần:

- Callback receiver có identity và TLS/WS-Security policy phù hợp.
- Allowlist destination, chống SSRF và chỉ cho phép callback URL được đăng ký.
- Correlation bằng MessageID/RelatesTo và business request ID.
- Xử lý duplicate/out-of-order callbacks và callback đến trước khi client lưu state.
- Retry delivery, dead-letter queue và reconciliation nếu callback không tới.

Đừng dùng callback URL tùy ý trong SOAP Header làm nơi gửi Fault/kết quả mà không xác minh quyền sở hữu và allowlist destination.

## 13. SOAP Fault, HTTP status và transport error

Spring-WS `WebServiceTemplate` mặc định sử dụng `SoapFaultMessageResolver`. API cũng kiểm tra connection error và SOAP Fault indicator; HTTP status lỗi có thể dẫn tới `WebServiceTransportException`, trong khi SOAP Fault được xử lý theo message. [WebServiceTemplate API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/client/core/WebServiceTemplate.html)

| Kết quả | Tầng | Hướng xử lý |
| --- | --- | --- |
| SOAP 1.1 Client / SOAP 1.2 Sender Fault | Request/policy không hợp lệ | Không retry nếu dữ liệu/quyền không đổi |
| SOAP 1.1 Server / SOAP 1.2 Receiver Fault | Server gặp lỗi xử lý | Chỉ retry nếu fault được contract đánh dấu transient/idempotent |
| HTTP 401/403 | HTTP authentication/authorization | Sửa credential/permission; không retry liên tục |
| HTTP 404 | Endpoint/route không tồn tại | Kiểm URI/deployment |
| HTTP 429/503 | Throttle/temporary service unavailable | Tuân Retry-After nếu có, retry có budget |
| HTTP 202 | Transport accepted, thường không có final SOAP body | Lấy request ID/status theo contract |
| Read timeout | Không nhận response kịp | Outcome có thể unknown; reconciliation trước retry side effect |
| TLS handshake failure | Transport security | Kiểm trust/hostname/cert; không coi là SOAP Fault |
| JMS receive timeout | Không nhận được reply trong thời hạn | Request có thể vẫn được consumer xử lý |
| Malformed SOAP/XML | Parser/protocol | Không retry nguyên xi nếu message sai |

Một lỗi HTTP 500 có thể mang SOAP Fault hoặc HTML/gateway error. Client phải phân biệt response content type/message, không ép body HTML thành SOAP Fault.

## 14. Timeout và Fault trong client code

Ví dụ xử lý riêng timeout và SOAP Fault ở mức ứng dụng:

~~~java
import org.springframework.ws.client.WebServiceIOException;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.SoapFaultClientException;

public SubmitDocumentResponse submit(
        WebServiceTemplate template,
        SubmitDocumentRequest request) {
    try {
        Object response = template.marshalSendAndReceive(request);
        if (response == null) {
            throw new SubmissionOutcomeUnknownException(
                    request.getClientRequestId());
        }
        return (SubmitDocumentResponse) response;
    } catch (SoapFaultClientException fault) {
        // SOAP Fault: phân loại theo fault code/detail và contract.
        throw new SubmissionRejectedException(
                request.getClientRequestId(), fault);
    } catch (WebServiceIOException transport) {
        // Có thể lỗi network/read timeout sau khi server đã nhận request.
        throw new SubmissionOutcomeUnknownException(
                request.getClientRequestId(), transport);
    }
}
~~~

Đây là ví dụ minh họa; `SubmissionOutcomeUnknownException` và `SubmissionRejectedException` là exceptions do ứng dụng định nghĩa. Các lỗi transport có thể được bọc bởi các kiểu `WebServiceClientException` khác tùy sender/underlying HTTP library; cần phân loại theo cause chain và policy. **Không gắn nhãn mọi transport exception là timeout**, và không kết luận server chưa xử lý.

### 14.1. Client reconciliation

~~~java
public SubmissionStatus reconcile(String clientRequestId) {
    // Gọi GetDocumentStatus bằng clientRequestId hoặc requestId
    // đã nhận từ acknowledgment trước đó.
    // Nếu vẫn không xác định được trạng thái, trả UNKNOWN,
    // không tạo một command mới với khóa idempotency khác.
    throw new UnsupportedOperationException("Ví dụ contract");
}
~~~

Nếu lần đầu mất response trước khi client nhận `requestId`, server cần cho phép tra cứu bằng **clientRequestId đã gửi** (scoped theo caller) hoặc idempotency key để client không phải phát sinh command mới.

## 15. Testing: one-way, response, timeout và late delivery

Kiểm thử cần chạy trên cả message-level và transport-level. `MockWebServiceServer` thích hợp để kiểm tra `WebServiceTemplate` gửi đúng SOAP request, nhưng nó không mô phỏng đầy đủ broker delivery, HTTP socket timeout hoặc late reply trên network thật.

### 15.1. Server-side test

`MockWebServiceClient` có thể gửi SOAP request vào Spring-WS application context và xác minh response/Fault. Dùng nó để kiểm tra:

- One-way operation không khai báo output không tạo response business ngoài contract.
- Request sai XSD/Auth trả đúng Fault.
- Request ID được lưu và trạng thái ban đầu là `ACCEPTED`.
- Duplicate idempotency key không tạo hai job.
- Response body có đúng QName/schema khi operation request-response.

Đối với HTTP one-way/202 semantics, cần test bằng **HTTP integration test** qua servlet/container thật vì mock SOAP client không nhất thiết tái hiện status/headers của transport.

### 15.2. Client-side test

`MockWebServiceServer` cho phép expect SOAP request và trả response giả lập:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

MockWebServiceServer mock =
        MockWebServiceServer.createServer(template);

mock.expect(payload(new StringSource(expectedRequestXml)))
    .andRespond(withPayload(new StringSource(expectedResponseXml)));

Object response = template.marshalSendAndReceive(request);

mock.verify();
~~~

Đây là khung test; cần import đúng matcher/response creator và cấu hình JAXB. Test này xác nhận message content và client mapping. Nó **không** kiểm tra read timeout thật; để kiểm timeout, cần HTTP/JMS integration fixture có thể trì hoãn response có kiểm soát.

### 15.3. Test receive timeout có kiểm soát

Thiết lập test broker:

~~~text
1. Gửi request có correlation ID.
2. Broker/consumer nhận request.
3. Consumer trì hoãn reply lâu hơn receiveTimeout.
4. Client hết thời gian chờ và ghi OUTCOME_UNKNOWN.
5. Consumer vẫn xử lý hoặc phát response sau đó.
6. Client tra cứu status bằng business request ID.
7. Xác minh chỉ có một business side effect.
~~~

Không dùng `Thread.sleep()` dài trong test để giả lập production. Tạo test worker với latch/barrier hoặc broker fixture có thể điều khiển thời điểm release; timeout test có deadline hợp lý và cleanup resources.

### 15.4. Ma trận test tối thiểu

| Test | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| One-way accepted | WSDL one-way, request valid | Transport/application ack theo binding; không đợi business output |
| Request-response success | Server trả SOAP output | Client đọc đúng JAXB response |
| SOAP Fault | Server trả business/protocol Fault | Client phân loại Fault, không coi là success |
| HTTP 202 | Server nhận command và trả accepted | Client ghi request ID/status accepted |
| HTTP 503 | Server tạm unavailable | Retry policy có giới hạn |
| Connect timeout | Server không accept connection | Không có SOAP xử lý nếu request chưa tới; phân loại transport |
| Read timeout | Server nhận request nhưng trì hoãn reply | Client outcome unknown, reconciliation |
| JMS receive timeout | Không có reply trước deadline | Không kết luận consumer chưa nhận request |
| Late reply | Reply đến sau client timeout | Không gán cho request khác; correlate hoặc bỏ theo policy |
| Duplicate delivery | Broker redeliver message | Consumer idempotent, một business result |
| Retry same ID | Client gửi lại cùng idempotency key | Cùng logical request/result |
| Retry different ID | Cùng command nhưng key mới | Có thể tạo request khác; xác minh business policy |
| Queue expiry | Message hết TTL trước consume | Dead-letter/expiry semantics rõ |
| Consumer unavailable | Broker giữ message | Persistence/retry/dead-letter theo cấu hình |
| Client shutdown | Client mất connection khi server vẫn chạy | Server outcome không tự rollback |
| Callback duplicate/out of order | Nhiều callback delivery | State machine và correlation xử lý đúng |

## 16. Quan sát và vận hành

Để debug, cần log các mốc thời gian riêng:

~~~text
request_created_at
request_sent_at
transport_accepted_at
server_received_at
business_started_at
business_completed_at
response_sent_at
client_response_received_at
~~~

Tên trường trên là telemetry do ứng dụng tự định nghĩa. Không log SOAP Body/PII, username/password, WS-Security tokens hoặc attachment bytes. Dùng correlation ID có kiểm soát và metric theo partner/operation/status.

### 16.1. Metrics gợi ý

| Metric | Đo gì? |
| --- | --- |
| `soap.request.sent.count` | Số request bắt đầu gửi |
| `soap.transport.accepted.count` | Số transport acceptance được quan sát |
| `soap.response.received.count` | Số SOAP response thực nhận |
| `soap.fault.count` | Số SOAP Fault theo category |
| `soap.timeout.count` | Timeout theo tầng (connect/read/JMS/application) |
| `soap.outcome.unknown.count` | Request timeout nhưng chưa xác định server outcome |
| `soap.async.pending` | Số request đang chờ xử lý |
| `soap.async.processing.duration` | Thời gian từ accepted đến completed/failed |
| `soap.retry.count` | Retry attempts |
| `soap.idempotency.duplicate.count` | Duplicate requests được deduplicate |
| `soap.deadletter.count` | Message vào dead-letter queue |

Metrics này là ví dụ đặt tên; framework không nhất thiết xuất sẵn các metric này.

### 16.2. Logging và tracing

- Ghi `requestId`, `clientRequestId`, WS-Addressing `MessageID` và JMS correlation theo vai trò khác nhau.
- Phân biệt event `SENT`, `ACCEPTED`, `PROCESSING`, `COMPLETED`, `FAILED`, `TIMED_OUT_UNKNOWN`.
- Không log response body đầy đủ nếu có dữ liệu nhạy cảm.
- Gắn trace context qua transport/broker theo cơ chế được phép; không giả định HTTP trace headers tự xuất hiện trong JMS message.
- Theo dõi queue depth, oldest message age, consumer lag, redelivery và dead-letter queue.
- Alert theo tỷ lệ timeout/unknown, không chỉ HTTP 5xx.

## 17. Chẩn đoán các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Client nhận `null` response | Transport không nhận response trong exchange | Xem MEP, HTTP status, JMS reply, không giả định thành công |
| HTTP 202 nhưng client chờ SOAP payload | Nhầm transport ack với business response | Trả request ID/status hoặc thiết kế polling/callback |
| JMS call treo vô hạn | Receive timeout mặc định `-1` | Thiết lập timeout có chủ đích, xem replyTo/consumer |
| JMS timeout dù consumer xử lý xong | Reply đến muộn hoặc correlation sai | Kiểm tra response queue, JMSCorrelationID và deadline |
| Client retry tạo đơn trùng | Thiếu idempotency key hoặc mỗi retry tạo key mới | Dedup theo principal + business request ID |
| HTTP read timeout nhưng đơn đã tạo | Server xử lý lâu hơn client timeout | Dùng trạng thái UNKNOWN và reconciliation |
| SOAP Fault bị retry vô hạn | Không phân biệt permanent/transient fault | Phân loại fault code/detail và retry policy |
| Queue backlog tăng | Consumer chậm, concurrency thấp hoặc downstream nghẽn | Scale consumer có giới hạn, backpressure và alert |
| Message mất sau acceptance | Non-persistent delivery/in-memory queue hoặc ack sai | Broker persistence, transaction, outbox |
| Duplicate JMS delivery | At-least-once delivery/redelivery | Consumer idempotency và transactional processing |
| Response tới nhầm client | Reply queue/correlation quản lý sai | Kiểm tra unique correlation và concurrency |
| Callback tới URL nội bộ | ReplyTo/FaultTo do caller cung cấp không được allowlist | DestinationPolicy, SSRF controls, xác minh partner |
| Email response không tới | SMTP/POP3/IMAP polling, mailbox/filter, response mapping | Theo dõi transport/store và correlation |
| XMPP response chậm | Session/disconnect/routing/presence | Connection lifecycle và timeout semantics |
| SOAP Fault không có HTTP response | Lỗi TLS/HTTP/parser trước SOAP processing | Phân biệt transport error và SOAP Fault |

### Quy trình điều tra

~~~mermaid
flowchart TD
    A["Client báo timeout/không response"] --> B{"Request có được gửi?"}
    B -->|Không| C["Local marshalling, DNS, connect/TLS"]
    B -->|Có| D{"Transport đã nhận?"}
    D -->|Không rõ| E["HTTP/broker logs, connection state, correlation"]
    D -->|Có| F{"Server đã nhận SOAP?"}
    F -->|Không| G["Gateway, queue, listener/container"]
    F -->|Có| H{"Business request đã commit/accepted?"}
    H -->|Không| I["SOAP Fault, validation, transaction rollback"]
    H -->|Có| J{"Response/callback được gửi?"}
    J -->|Không| K["ReplyTo, response queue, timeout, sender"]
    J -->|Có| L["Client correlation, late response, parser"]
~~~

Điều tra theo **correlation ID** ở mọi tầng; không dựa vào một log “request timeout” ở client để kết luận server đã không chạy.

## 18. An toàn khi dùng queue, timeout và callback

Asynchronous processing tạo thêm bề mặt rủi ro:

- **Queue poisoning:** message sai contract lặp đi lặp lại làm consumer retry vô hạn.
- **Replay/duplicate:** redelivery tạo side effect trùng nếu không idempotent.
- **Unauthorized destination:** JMS URI hoặc reply destination không được kiểm tra, có thể tạo indirection/JNDI-style routing.
- **Callback SSRF:** `ReplyTo`/`FaultTo` HTTP URI do caller chọn có thể trỏ tới mạng nội bộ.
- **Denial of service:** timeout dài, số message pending, payload quá lớn hoặc consumer concurrency vô hạn.
- **Sensitive data retention:** message persistent lưu SOAP Body/attachment trên broker lâu hơn dự kiến.
- **Dead-letter leakage:** message lỗi được copy sang queue có quyền truy cập rộng.

Spring-WS 4.1 có `DestinationPolicy` cho message senders để bổ sung allowlist/validation destination. JMS sender có kiểm tra mặc định với tên destination có dấu hiệu indirection; nếu môi trường cần tên đặc biệt, cấu hình allowlist cụ thể thay vì tắt toàn bộ kiểm tra. Với WS-Addressing callback ngoài băng, xác thực caller và kiểm soát URI trước khi mở outbound connection.

### 18.1. Queue security

- TLS giữa application và broker, authentication/authorization theo destination.
- Chỉ cho phép consumer/producer trên queue mà service cần.
- Giới hạn message size, TTL, redelivery và delivery count.
- Cấu hình dead-letter queue có ACL, retention và quy trình redrive.
- Mã hóa dữ liệu nhạy cảm ở tầng message/storage nếu policy yêu cầu; WS-Security có thể bổ sung bảo vệ SOAP message qua intermediaries.
- Không đưa password, token hoặc private key vào JMS properties/logs.

### 18.2. Backpressure và giới hạn chờ

Nếu client gửi nhanh hơn consumer xử lý, queue backlog tăng. Không chữa bằng cách tăng vô hạn queue depth hoặc timeout. Hãy dùng:

1. Bounded concurrency ở producer và consumer.
2. Rate limits/quota theo partner/tenant.
3. Admission control: từ chối/return busy khi không thể tiếp nhận bền vững.
4. Queue age/depth alert, consumer lag và dead-letter tracking.
5. Deadline end-to-end và expiry policy cho command hết giá trị.

**Message TTL không thay business deadline**: một worker đã nhận và bắt đầu xử lý có thể tiếp tục sau khi message gốc hết hạn.

## 19. Bài tập thực hành

### Bài 1 — Phân biệt one-way và request-response

Thiết kế WSDL có `SubmitOrder` chỉ có input và `GetOrderStatus` có input/output. Nêu rõ client nhận transport acknowledgment nào và ở đâu có kết quả cuối cùng.

### Bài 2 — HTTP 202 và request ID

Tạo endpoint submit trả `requestId` cùng trạng thái `ACCEPTED`. Giả lập worker xử lý chậm và client gọi `GetDocumentStatus`. Chứng minh HTTP/ack thành công không tương đương business completed.

### Bài 3 — JMS request/reply

Dùng Artemis/ActiveMQ test broker và `JmsMessageSender`. Cấu hình `replyToName`, `receiveTimeout` 2 giây và consumer trả response sau 5 giây. Quan sát timeout, response đến muộn và correlation.

### Bài 4 — JMS one-way delivery

Gửi message vào queue không dùng reply queue. Chứng minh producer send completion và consumer processing là hai mốc riêng. Test persistent delivery, consumer restart và redelivery.

### Bài 5 — HTTP timeout

Dùng HTTP integration server trì hoãn SOAP response quá read timeout. Server vẫn commit nghiệp vụ. Xác minh client có `OUTCOME_UNKNOWN`, tra cứu status trước retry và không tạo command mới.

### Bài 6 — Idempotency

Gửi hai request cùng `clientRequestId` và payload giống nhau; sau đó gửi cùng ID nhưng payload khác. Kết quả phải deduplicate trường hợp đầu và trả conflict có kiểm soát ở trường hợp sau.

### Bài 7 — Fault classification

Tạo SOAP Sender/Client Fault, Receiver/Server Fault, HTTP 503, TLS failure và read timeout. Xác định lỗi nào retry được, lỗi nào cần sửa request/credential và lỗi nào có outcome không rõ.

### Bài 8 — Callback đến trễ/trùng

Tạo callback endpoint test nhận cùng `RelatesTo` hai lần và một response đến sau khi trạng thái đã `COMPLETED`. Chứng minh callback handler idempotent và state machine không chuyển ngược trạng thái.

### Bài 9 — Deadline nhiều tầng

Định nghĩa application deadline 20 giây; cấu hình connect/read/JMS receive và retry budget. Tính tổng worst-case gồm số attempts và backoff, sau đó sửa để không vượt SLA.

### Bài 10 — Queue backlog và dead-letter

Tắt consumer, gửi request hợp lệ, quan sát queue depth/age, rồi bật consumer. Gửi thêm message sai XSD để kiểm tra poison-message handling, retry count và DLQ.

## 20. Checklist triển khai

| Nhóm | Điều kiện đạt |
| --- | --- |
| **MEP/contract** | WSDL xác định one-way hay request-response; ack/result semantics rõ |
| **Transport** | HTTP/JMS/email/XMPP được chọn đúng với topology và durability |
| **HTTP** | Connect/read/pool/overall deadlines có cấu hình và test |
| **JMS** | Destination, persistent delivery, transaction, `replyTo`, receive timeout, TTL rõ |
| **Response** | SOAP response/Fault khác transport ack và application ack |
| **Async status** | `requestId`, status state machine, expiry và status query được công bố |
| **Correlation** | JMSCorrelationID, MessageID/RelatesTo và business ID không bị nhầm |
| **Idempotency** | Retry cùng request không tạo side effect trùng |
| **Timeout** | Timeout không tự gắn nhãn business failure; có reconciliation |
| **Retry** | Chỉ retry transient/permitted fault, có backoff/jitter/budget |
| **Queue reliability** | Outbox/transactional publish, redelivery, DLQ và consumer idempotency |
| **Callback** | Identity/allowlist, correlation, duplicate/out-of-order handling |
| **Security** | TLS/mTLS, WS-Security, ACL broker, destination policy |
| **Resource limits** | Max payload, queue depth, concurrency, rate limits và backpressure |
| **Testing** | Mock SOAP message + HTTP/JMS integration + late/duplicate/timeout tests |
| **Observability** | Metrics cho accepted/response/fault/timeout/unknown/pending/queue age |

## 21. Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4 — Transports](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/#transports): HTTP, JMS, email, XMPP và transport configuration.
- [Spring-WS Reference — JMS transport](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/#transports-jms): `WebServiceMessageListener`, `JmsMessageSender`, `replyToName`, BytesMessage/TextMessage.
- [Spring-WS WebServiceTemplate API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/client/core/WebServiceTemplate.html): client request/response flow, no-response behavior và Fault resolver.
- [Spring-WS WebServiceOperations API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/client/core/WebServiceOperations.html): semantics của `marshalSendAndReceive`, `sendAndReceive`, `sendSourceAndReceiveToResult`.
- [Spring-WS JmsMessageSender API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/jms/JmsMessageSender.html): `setReceiveTimeout`, destination, `replyToName` và delivery.
- [Spring-WS MailMessageSender API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/mail/MailMessageSender.html): SMTP/POP3/IMAP và receive timeout.
- [WSDL 1.1 Specification — Port Types and Operations](https://www.w3.org/TR/wsdl.html): operation patterns và input/output/fault messages.
- [HTTP Semantics — RFC 9110, `15.3.3`](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3): ý nghĩa `202 Accepted`.
- [Jakarta Messaging Specification](https://jakarta.ee/specifications/messaging/): delivery, acknowledgement, transactions và messaging semantics.

**Kết luận:** Thiết kế **thông điệp một chiều, phản hồi và giới hạn thời gian chờ** trong **SPRING_WEB_SERVICES** bắt đầu bằng việc chọn đúng MEP của WSDL, sau đó xác định transport acknowledgment, SOAP response/Fault và business completion có ý nghĩa gì. HTTP 202 hoặc JMS send completion chỉ xác nhận một mốc ở transport; timeout của client không chứng minh server đã dừng; retry không có idempotency có thể tạo side effect trùng. Với Spring-WS, hãy cấu hình `WebServiceTemplate`/sender đúng transport, giới hạn mọi tầng chờ, dùng correlation và business request ID riêng, quản lý trạng thái bất đồng bộ, xử lý late reply, redelivery và Fault theo contract. Khi các điều kiện này được kiểm thử trên HTTP/JMS thật ngoài mock message layer, tích hợp SOAP mới có hành vi ổn định khi phản hồi chậm, transport gián đoạn hoặc công việc kéo dài.
