# Gọi một chiều, phản hồi rỗng và kiểm tra ngữ nghĩa của từng API

## 1. Bài toán: “không có dữ liệu trả về” nghĩa là gì?

Một hệ thống quản lý đơn hàng sử dụng **Spring Web Services (Spring-WS)** để gọi dịch vụ SOAP của đối tác. Phía đối tác công bố một operation nhận thông báo giao hàng nhưng **không có thông điệp output** trong WSDL. Phía client gọi operation và thấy phương thức Java trả `null`. Có người kết luận “gửi thành công”, người khác kết luận “server trả dữ liệu rỗng”.

Hai kết luận ấy đều có thể sai nếu chưa đọc hợp đồng và xem thông điệp thật trên đường truyền.

Trong SOAP over HTTP, cần phân biệt ít nhất các trường hợp:

1. **One-way operation theo WSDL**: hợp đồng chỉ có input message, không khai báo output message.
2. **Không có SOAP response message**: HTTP có thể vẫn trả status và headers, nhưng không có SOAP Envelope để client trích xuất.
3. **Có SOAP Envelope nhưng Body rỗng**: response message tồn tại, chỉ không có phần tử payload nghiệp vụ.
4. **Có phần tử response rỗng**: chẳng hạn `<n:AckResponse/>`, đây **vẫn là một payload XML có QName**.
5. **Có payload với phần tử `xsi:nil="true"`**: XML thể hiện một giá trị nil theo XSD; không đồng nghĩa không có message.
6. **Có SOAP Fault**: server trả cấu trúc lỗi, không phải “response rỗng”.
7. **Không nhận được phản hồi vì lỗi mạng hoặc timeout**: không thể suy rằng operation one-way đã hoàn tất ở server.

Lựa chọn sai API client hoặc diễn giải sai giá trị trả về có thể gây mất sự kiện, gửi trùng thông báo, bỏ qua lỗi bảo mật và khó đối soát giao dịch.

Trong chương **Máy khách Spring-WS**, bài này tập trung vào **ngữ nghĩa của lời gọi một chiều, các trạng thái phản hồi rỗng và giá trị trả về của từng API `WebServiceTemplate`**. Kiến thức này gắn với cách phát triển SOAP contract-first bằng XSD/WSDL, JAXB, SOAP Action, WS-Security, chứng chỉ, SOAP Fault và kiểm thử tương thích với hệ thống doanh nghiệp.

## 2. Hai lớp ngữ nghĩa: WSDL operation và HTTP transport

Mô hình khái quát:

~~~mermaid
flowchart TD
    A["WSDL định nghĩa operation"] --> B{"Có output message?"}
    B -- "Không: one-way" --> C["Client gửi SOAP request"]
    B -- "Có: request-response" --> D["Client gửi và chờ SOAP response"]
    C --> E["HTTP(S) transport"]
    D --> E
    E --> F{"Kết quả kết nối"}
    F -- "Status/headers, không SOAP body" --> G["Không có SOAP message để unmarshal"]
    F -- "SOAP Envelope + payload" --> H["Trích xuất/unmarshal response"]
    F -- "SOAP Fault" --> I["Xử lý đường lỗi SOAP"]
    F -- "Timeout/TLS/HTTP không phải SOAP" --> J["Lỗi transport, outcome có thể chưa rõ"]
~~~

**One-way là thuộc tính của hợp đồng thông điệp**, không phải lời hứa rằng client sẽ không chờ bất cứ thứ gì. Với SOAP truyền qua HTTP, client vẫn phải mở kết nối, gửi request và có thể đợi HTTP response/status theo cơ chế transport. Thậm chí HTTP status báo thành công về mặt vận chuyển vẫn chưa đủ chứng minh nghiệp vụ đã hoàn tất.

### 2.1. Định nghĩa one-way trong WSDL 1.1

Một operation WSDL 1.1 kiểu one-way có **`wsdl:input` nhưng không có `wsdl:output`**:

~~~xml
<wsdl:portType name="NotificationPort">
    <wsdl:operation name="PublishEvent">
        <wsdl:input message="tns:PublishEventInput"/>
    </wsdl:operation>
</wsdl:portType>
~~~

Đây là đoạn trích, giả định `wsdl:definitions` đã định nghĩa namespace `wsdl`/`tns`, message `PublishEventInput` và schema cho payload. Trong WSDL 1.1, one-way operation không có một output message thông thường để client unmarshalling.

Một operation request-response có thêm `wsdl:output`:

~~~xml
<wsdl:operation name="GetDeliveryStatus">
    <wsdl:input message="tns:GetDeliveryStatusInput"/>
    <wsdl:output message="tns:GetDeliveryStatusOutput"/>
</wsdl:operation>
~~~

Hai operation vẫn có thể sử dụng **cùng URL SOAP**. Sự khác nhau được thể hiện trong WSDL operation và các binding liên quan, không phải tự động từ việc URL chứa chữ “publish” hay “status”.

### 2.2. HTTP acknowledgment không phải SOAP output

Một trao đổi minh họa:

~~~http
POST /ws/notifications HTTP/1.1
Host: partner.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:notifications:PublishEvent"
~~~

Client gửi SOAP Envelope chứa `PublishEventRequest`. Tùy hợp đồng và HTTP binding, phía đối tác có thể phản hồi:

~~~http
HTTP/1.1 202 Accepted
Content-Length: 0
~~~

Đây là **một kịch bản minh họa**, không phải tuyên bố mọi one-way SOAP operation bắt buộc trả HTTP 202. HTTP 202 cho biết request được chấp nhận ở mức HTTP, bản thân nó **không bảo đảm** sự kiện đã được xử lý xong, lưu bền vững, hay được chuyển tiếp thành công.

Một số transport/binding có thể trả HTTP status khác hoặc phản hồi khác. Cần đọc WSDL, thỏa thuận tích hợp và kiểm thử đối tác thực tế.

## 3. Bốn hình thái “rỗng” trên dây

### 3.1. Không có SOAP message ở response

~~~http
HTTP/1.1 202 Accepted
Content-Length: 0
~~~

Ở đây HTTP response tồn tại nhưng **không có XML SOAP Envelope**. Một API `WebServiceTemplate` được thiết kế nhận response có thể không chạy extractor/unmarshaller; giá trị trả về và ngoại lệ phụ thuộc API, transport và cách server đóng gói response.

### 3.2. Có SOAP Envelope nhưng Body không có payload

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Header/>
    <soap:Body/>
</soap:Envelope>
~~~

Đây là một **SOAP message thực sự**. `SoapMessage` có thể tồn tại dù `getPayloadSource()` không có một phần tử nghiệp vụ để đọc. Không thể coi Envelope rỗng là đồng nghĩa với transport không phản hồi.

### 3.3. Có một response element rỗng

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:n="urn:example:notifications:v1">
    <soap:Body>
        <n:AckResponse/>
    </soap:Body>
</soap:Envelope>
~~~

Body ở đây **không rỗng**: nó có phần tử payload `{urn:example:notifications:v1}AckResponse`. XSD có thể quy định `AckResponse` là complex type không có phần tử con, và JAXB có thể ánh xạ thành một object response không có dữ liệu nghiệp vụ bên trong.

Một API kiểm tra “có payload hay không” phải phân biệt `AckResponse` với trường hợp `<soap:Body/>`.

### 3.4. Có phần tử nil

~~~xml
<n:AckResponse
    xmlns:n="urn:example:notifications:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Phần tử ở đây có QName và thuộc tính `xsi:nil`. Nó chỉ hợp lệ nếu **XSD cho phép `nillable="true"`** ở vị trí tương ứng. Khi JAXB unmarshalling, nil có thể dẫn tới giá trị Java `null` ở một số mapping, nhưng điều đó **không chứng minh SOAP message vắng mặt**.

### 3.5. Bảng phân biệt

| Hiện tượng | Có HTTP response? | Có SOAP Envelope? | Có payload QName? |
| --- | --- | --- | --- |
| HTTP 202, body 0 byte | Có | Không | Không |
| SOAP Envelope với `<Body/>` | Có | Có | Không |
| SOAP Body chứa `<AckResponse/>` | Có | Có | Có |
| SOAP Body chứa `<AckResponse xsi:nil="true"/>` | Có | Có | Có |
| SOAP Body chứa `<Fault>` | Có | Có | Có cấu trúc Fault, không phải response nghiệp vụ |
| Read timeout trước khi nhận đủ response | Chưa có response đầy đủ | Không thể kết luận | Không thể kết luận |

**Không viết logic `if (result == null) success` khi chưa quy định “null” đại diện cho trường hợp nào của API cụ thể.**

## 4. Ví dụ XSD/WSDL xuyên suốt: PublishEvent và GetDeliveryStatus

### 4.1. Schema cho operation one-way

File `src/main/resources/xsd/notifications.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:notifications:v1"
    targetNamespace="urn:example:notifications:v1"
    elementFormDefault="qualified">

    <xs:element name="PublishEventRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="eventId" type="xs:string"/>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="occurredAt" type="xs:dateTime"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetDeliveryStatusRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="eventId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetDeliveryStatusResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="AckResponse">
        <xs:complexType/>
    </xs:element>
</xs:schema>
~~~

Điểm đáng chú ý: **XSD có phần tử `AckResponse` không có nghĩa operation PublishEvent tự nhiên có output**. XSD chỉ định nghĩa kiểu/phần tử có thể dùng; **WSDL portType** mới quy định một operation cụ thể có input và output hay không. `AckResponse` có thể được dùng cho operation khác, hoặc trong một phiên bản hợp đồng request-response thay thế.

### 4.2. WSDL trừu tượng minh họa

~~~xml
<wsdl:message name="PublishEventInput">
    <wsdl:part name="payload"
               element="tns:PublishEventRequest"/>
</wsdl:message>

<wsdl:message name="GetDeliveryStatusInput">
    <wsdl:part name="payload"
               element="tns:GetDeliveryStatusRequest"/>
</wsdl:message>

<wsdl:message name="GetDeliveryStatusOutput">
    <wsdl:part name="payload"
               element="tns:GetDeliveryStatusResponse"/>
</wsdl:message>

<wsdl:portType name="NotificationPort">
    <wsdl:operation name="PublishEvent">
        <wsdl:input message="tns:PublishEventInput"/>
    </wsdl:operation>

    <wsdl:operation name="GetDeliveryStatus">
        <wsdl:input message="tns:GetDeliveryStatusInput"/>
        <wsdl:output message="tns:GetDeliveryStatusOutput"/>
    </wsdl:operation>
</wsdl:portType>
~~~

Đây **chưa phải WSDL hoàn chỉnh**: cần `wsdl:definitions` và namespace declarations, `types` nhúng/import XSD, SOAP binding cho từng operation, `service`, `port` và `soap:address`. Với SOAP document/literal, binding phải nhất quán với message và phần tử XSD.

### 4.3. Hợp đồng đối tác phải xác định tín hiệu tiếp nhận

Với operation one-way như `PublishEvent`, cần thỏa thuận riêng:

- Khi nào phía nhận coi event là **accepted**?
- Có cơ chế ghi bền vững vào queue/outbox trước khi trả HTTP 202 không?
- Có event ID hoặc idempotency key để chống gửi trùng không?
- Nếu server không xử lý được sau khi đã accepted thì báo lỗi ở kênh nào?
- Client có thể gọi `GetDeliveryStatus` theo event ID không?
- Có SLA/TTL, retry policy, dead-letter hoặc thông báo bất đồng bộ không?

Không có những điều đó, one-way chỉ giảm yêu cầu về **message output**, chứ không tự tạo cơ chế giao nhận đáng tin cậy.

## 5. Nhìn đúng trách nhiệm của `WebServiceTemplate`

`org.springframework.ws.client.core.WebServiceTemplate` là API mức cao phía client Spring-WS. Nó quản lý việc chuẩn bị `WebServiceMessage`, gửi qua `WebServiceMessageSender`, nhận SOAP response khi có và chuyển sang cách xử lý tương ứng. Trong một lời gọi, template thường phối hợp:

~~~mermaid
flowchart LR
    A["Java object hoặc XML Source"] --> B["WebServiceTemplate"]
    B --> C["WebServiceMessageCallback / Marshaller"]
    C --> D["SoapMessage request"]
    D --> E["Message sender / HTTP(S)"]
    E --> F["SOAP server"]
    F --> G{"Có phản hồi hợp lệ?"}
    G --> H["Không SOAP response"]
    G --> I["SOAP response bình thường"]
    G --> J["SOAP Fault"]
    I --> K["Extractor / Unmarshaller"]
    J --> L["Fault resolver hoặc exception"]
~~~

Trong nhiều API, tên phương thức chứa **`sendAndReceive`** vì nó hỗ trợ vòng request/response, nhưng bản thân việc gọi API không làm thay đổi WSDL one-way thành request-response. Ngược lại, dùng `marshalSendAndReceive` không phải bằng chứng server đã gửi object response.

### 5.1. Các abstraction cần phân biệt

| Abstraction | Đối tượng nó đại diện |
| --- | --- |
| `WebServiceMessageCallback` | Chuẩn bị request message trước khi gửi; có thể đặt payload hoặc SOAP action/header |
| `WebServiceMessageExtractor<T>` | Trích xuất thông tin từ **response message** nếu có response mà API xử lý |
| `Marshaller` / `Unmarshaller` | Chuyển Java object ↔ XML payload theo OXM/JAXB |
| `Source` / `Result` | Nguồn hoặc đích XML, không tự mang ngữ nghĩa nghiệp vụ accepted/delivered |
| `SoapMessage` | Envelope/Header/Body/Action/Fault của một SOAP message |
| `WebServiceMessageSender` | Kết nối và truyền thông điệp qua transport |
| `ClientInterceptor` | Can thiệp luồng client trước/sau request, response hoặc fault theo chain |

Một callback được gọi trong đường chuẩn bị request **không đồng nghĩa** server đã nhận request. Một extractor được gọi nghĩa là đã có response message được framework đưa qua đường xử lý này, **không bảo đảm nghiệp vụ thành công** nếu contract response chỉ là acknowledgment.

## 6. So sánh ngữ nghĩa của các API client phổ biến

Đây là bảng quyết định quan trọng nhất của bài:

| API `WebServiceTemplate` | Input chính | Đầu ra được trả/ghi | Khi phù hợp |
| --- | --- | --- | --- |
| `marshalSendAndReceive(...)` | Java object, qua marshaller | Object đã unmarshal khi có SOAP response payload phù hợp; có thể `null` trong những trường hợp không có kết quả | Contract request-response với JAXB |
| `sendSourceAndReceiveToResult(...)` | XML `Source` | XML response được ghi vào `Result` khi có response và API xử lý được; trả boolean chỉ trạng thái có response được xử lý theo API | Client XML trực tiếp, cần biết có response để ghi |
| `sendSourceAndReceive(...)` | XML `Source` | Giá trị do `SourceExtractor<T>` trích xuất từ response payload khi có | Client tự phân tích XML response |
| `sendAndReceive(callback, extractor)` | `WebServiceMessageCallback` | `T` do `WebServiceMessageExtractor<T>` trả về, hoặc không có giá trị khi không trích xuất được response | Cần quan sát toàn bộ SOAP message và tùy chỉnh request |

**Đừng suy ngữ nghĩa qua tên API một mình.** Cần đọc chữ ký phương thức, cấu hình sender/marshaller, callback/extractor, WSDL operation và response thật. Các overload/API cụ thể có thể khác theo phiên bản Spring-WS; chọn đúng overload bằng kiểm tra compile với dependency đang dùng.

### 6.1. Vì sao `null` không phải mã trạng thái nghiệp vụ?

Giả sử:

~~~java
Object result = template.marshalSendAndReceive(request);
~~~

Giá trị `result == null` **không đủ** để suy:

- Event đã được ghi bền vững.
- Đối tác xử lý xong nghiệp vụ.
- Có HTTP 202.
- SOAP Body rỗng hay Envelope không tồn tại.
- JAXB unmarshalling thành công nhưng trả null theo một mapping nil.

Cần đánh giá luồng thực tế, contract và khả năng gặp exception. Với response có `xsi:nil`, chính JAXB mapping cũng có thể biểu diễn giá trị rỗng; việc đó khác với one-way không có output.

### 6.2. Vì sao boolean không phải “business success”?

Khi dùng overload `sendSourceAndReceiveToResult(...)` trả `boolean`, giá trị boolean liên quan việc API có xử lý được **response message cho Result** theo hợp đồng của phương thức, **không phải trạng thái nghiệp vụ**.

Ví dụ `true` có thể chỉ xác nhận đường response được xử lý; payload trả về vẫn có thể biểu diễn `REJECTED` hoặc `PENDING` theo XSD ứng dụng. `false` có thể là không có response để ghi, chứ không nhất thiết là transport đã mất gói.

Đọc giá trị cùng với HTTP/SOAP contract; không viết:

~~~java
// SAI về ngữ nghĩa:
boolean accepted = template.sendSourceAndReceiveToResult(
        requestSource, responseResult);
if (accepted) {
    markInvoiceAsPaid();
}
~~~

Tên biến `accepted` và hành động `markInvoiceAsPaid()` đưa một ý nghĩa nghiệp vụ không được phương thức bảo đảm.

## 7. Tạo SOAP client với cấu hình tối thiểu

Ví dụ ứng dụng Spring Boot có dependency `spring-boot-starter-web-services` và các lớp JAXB sinh từ XSD đối tác. Bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class NotificationSoapClientConfig {

    @Bean
    public Jaxb2Marshaller notificationMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("example.notifications.generated");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate notificationWebServiceTemplate(
            Jaxb2Marshaller notificationMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(notificationMarshaller);
        template.setUnmarshaller(notificationMarshaller);
        return template;
    }
}
~~~

`example.notifications.generated` là package ví dụ cho JAXB/XJC generated classes. Bạn phải thực sự sinh lớp phù hợp từ XSD, quản lý JAXB runtime và namespace tương thích. Với Jakarta JAXB trong Spring hiện đại, không trộn `javax.xml.bind` DTO từ thế hệ cũ vào runtime yêu cầu `jakarta.xml.bind`.

Đây là cấu hình **tối thiểu**, chưa có timeouts, TLS truststore/keystore, HTTP authentication, WS-Security, logging, default URI hoặc lựa chọn SOAP 1.1/1.2. Những cấu hình đó phải được bổ sung theo hợp đồng và phiên bản Spring-WS.

### 7.1. SOAP action cho một lời gọi

Với SOAP 1.1, có thể đặt action qua callback:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

Object response = notificationWebServiceTemplate
        .marshalSendAndReceive(
                "https://partner.example.test/ws/notifications",
                publishEventRequest,
                new SoapActionCallback(
                        "urn:example:notifications:PublishEvent"));
~~~

`publishEventRequest` phải là object JAXB được marshaller hỗ trợ, có root QName phù hợp `PublishEventRequest` (đôi khi là `JAXBElement` tạo từ `ObjectFactory`). `SoapActionCallback` chuẩn bị SOAP action; nó không quyết định URL HTTP hay tự tạo response. Việc action được biểu diễn trên transport khác nhau giữa SOAP 1.1 và 1.2.

**Lưu ý quan trọng:** đoạn mã minh họa cách gọi API và không khẳng định `Object response` sẽ tồn tại đối với one-way operation. Nếu response không xuất hiện hoặc có SOAP Fault, hành vi cần được kiểm thử; không lấy `null` làm tín hiệu accepted.

## 8. API `marshalSendAndReceive(...)`: khi nào hợp lý?

`marshalSendAndReceive` phù hợp nhất khi:

- XSD/WSDL quy định request và response payload có thể JAXB marshalling/unmarshalling.
- Ứng dụng cần DTO Java thay vì thao tác với XML `Source`.
- Response có cấu trúc nghiệp vụ rõ ràng (ví dụ `GetDeliveryStatusResponse` chứa `status`).

Ví dụ response contract:

~~~xml
<n:GetDeliveryStatusResponse
    xmlns:n="urn:example:notifications:v1">
    <n:status>DELIVERED</n:status>
</n:GetDeliveryStatusResponse>
~~~

Mã minh họa với lớp đã được XJC sinh:

~~~java
GetDeliveryStatusRequest request =
        new GetDeliveryStatusRequest();
request.setEventId("EVT-1001");

Object raw = notificationWebServiceTemplate.marshalSendAndReceive(
        "https://partner.example.test/ws/notifications",
        request,
        new SoapActionCallback(
                "urn:example:notifications:GetDeliveryStatus"));

// Tùy cách XJC/JAXB sinh mã, raw có thể là JAXBElement<...>
// hoặc object root phù hợp.
~~~

Không tự cast `raw` thành một class chỉ dựa trên tên WSDL; kiểm tra cách JAXB tạo root element và cách ứng dụng cấu hình marshaller. Nếu response chứa `status=PENDING`, lời gọi **đã nhận response** nhưng sự kiện chưa được xử lý hoàn tất.

### 8.1. Khi one-way vẫn dùng API này

Một số ứng dụng có thể gọi một one-way operation qua `marshalSendAndReceive` vì code đã có marshaller và muốn gửi request. Tuy nhiên cách viết này dễ khiến người đọc hiểu nhầm rằng luôn có JAXB response. Nếu mục tiêu là chứng minh “không có SOAP output” và ghi nhận trạng thái HTTP, cần bổ sung kiểm thử transport, logging/correlation và thỏa thuận tiếp nhận của đối tác.

Trong hợp đồng thật, có thể cân nhắc dùng API callback/extractor để **phân biệt message có được trích xuất hay không**, nhưng đó cũng không biến kết quả Java thành xác nhận nghiệp vụ.

### 8.2. Nếu SOAP Fault xảy ra?

SOAP Fault không phải `GetDeliveryStatusResponse`. `WebServiceTemplate` thường nhận diện Fault và có thể ném `SoapFaultClientException` theo fault resolver mặc định. Không viết code kỳ vọng mọi lỗi sẽ trả `null`:

~~~java
try {
    Object raw = notificationWebServiceTemplate
            .marshalSendAndReceive(uri, request);
    // raw chỉ thuộc đường xử lý thành công/không có kết quả,
    // chưa phải bằng chứng nghiệp vụ hoàn thành.
} catch (SoapFaultClientException fault) {
    // Đọc fault code/reason/detail theo contract.
}
~~~

`uri` và `request` trong đoạn này là biến của ứng dụng; cần import `org.springframework.ws.soap.client.SoapFaultClientException`. Các lỗi khác như TLS, HTTP gateway, XML parsing và JAXB mapping không nhất thiết bị bắt bằng exception này.

## 9. API `sendSourceAndReceiveToResult(...)`: response có được ghi không?

Khi trao đổi XML trực tiếp, không dùng JAXB, Spring-WS có overload `sendSourceAndReceiveToResult` nhận request `Source` và response `Result`:

~~~java
import java.io.StringWriter;
import org.springframework.xml.transform.StringSource;
import javax.xml.transform.stream.StreamResult;

String requestXml =
        "<n:GetDeliveryStatusRequest " +
        "xmlns:n=\"urn:example:notifications:v1\">" +
        "<n:eventId>EVT-1001</n:eventId>" +
        "</n:GetDeliveryStatusRequest>";

StringWriter writer = new StringWriter();

boolean responseHandled =
        notificationWebServiceTemplate.sendSourceAndReceiveToResult(
                new StringSource(requestXml),
                new StreamResult(writer));

if (responseHandled) {
    String xml = writer.toString();
    // Phân tích payload XML theo XSD và domain status.
} else {
    // Không có response được xử lý theo ngữ nghĩa API này.
    // Không suy ra event đã thành công hoặc thất bại.
}
~~~

Ví dụ giả định template có **default URI** được cấu hình. Nếu chưa có, dùng overload nhận URI có trong phiên bản đang dùng hoặc cấu hình `template.setDefaultUri(...)`.

**Boolean trả về không đại diện HTTP 2xx, SOAP accepted hay trạng thái doanh nghiệp.** Khi có SOAP Fault, framework có thể chuyển sang fault resolver/exception trước khi trả boolean. Cần kiểm tra cả nhánh exception.

### 9.1. Cẩn thận với `Result` dù boolean là true

Một response có SOAP Envelope nhưng Body rỗng hoặc không có payload phù hợp có thể làm việc copy `Source → Result` khác với response chứa XML root bình thường. Chi tiết cách API xử lý trường hợp đó phụ thuộc stack/response. `StringWriter` rỗng không tự chứng minh server không trả SOAP Envelope.

Vì thế đừng coi:

~~~java
writer.toString().isEmpty()
~~~

là phép kiểm tra duy nhất cho **không có SOAP response**. Nếu cần phân biệt, dùng extractor ở mức `WebServiceMessage` như phần tiếp theo và kiểm thử bằng wire response cụ thể.

## 10. API `sendAndReceive(callback, extractor)`: quan sát message rõ hơn

`WebServiceMessageCallback` cho phép ứng dụng chuẩn bị request; `WebServiceMessageExtractor<T>` đọc response message khi đường xử lý phản hồi được thực hiện. Đây là lựa chọn linh hoạt khi cần quan sát riêng **có SOAP message** và **có payload**.

Ví dụ dùng một `record` Java 17 làm giá trị trả về không null:

~~~java
import javax.xml.transform.Source;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamResult;
import java.io.StringWriter;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.xml.transform.StringSource;

record ResponseObservation(boolean soapMessageSeen,
                           boolean payloadPresent,
                           String payloadXml) {}

String payload =
        "<n:PublishEventRequest " +
        "xmlns:n=\"urn:example:notifications:v1\">" +
        "<n:eventId>EVT-1001</n:eventId>" +
        "<n:orderId>ORD-1001</n:orderId>" +
        "<n:occurredAt>2026-11-27T09:00:00+07:00</n:occurredAt>" +
        "</n:PublishEventRequest>";

ResponseObservation observation =
        notificationWebServiceTemplate.sendAndReceive(
            "https://partner.example.test/ws/notifications",
            message -> {
                TransformerFactory.newInstance()
                        .newTransformer()
                        .transform(
                            new StringSource(payload),
                            message.getPayloadResult());
                ((SoapMessage) message).setSoapAction(
                    "urn:example:notifications:PublishEvent");
            },
            message -> {
                Source source = message.getPayloadSource();
                if (source == null) {
                    return new ResponseObservation(true, false, "");
                }
                StringWriter output = new StringWriter();
                TransformerFactory.newInstance()
                        .newTransformer()
                        .transform(source, new StreamResult(output));
                return new ResponseObservation(
                    true, true, output.toString());
            });
~~~

**Đây là ví dụ minh họa các callback API**, giả định source/payload được tin cậy, transport và SOAP version đã cấu hình tương thích. Các exception checked của biến đổi XML được các callback hỗ trợ theo hợp đồng phương thức; khi triển khai trong dự án thật cần kiểm tra compile với phiên bản đang sử dụng và xử lý exception phù hợp.

Ý nghĩa của `ResponseObservation`:

- Nếu **extractor được gọi**, nó trả một object khác `null`, báo rằng một SOAP response message đã đi qua extractor.
- `payloadPresent=false` nghĩa là extractor quan sát thấy `getPayloadSource()==null` trong runtime đó; chưa thể kết luận transport trước đó không có HTTP body.
- Nếu `observation==null`, có thể đường response extraction không được gọi vì không có response message thích hợp; vẫn phải đối chiếu sender, HTTP status và khả năng extractor/handler trả về null theo API.
- Nếu có SOAP Fault, fault resolver có thể can thiệp **trước** extractor; đừng dựa vào extractor để tự bắt mọi Fault.

Ví dụ tạo một Transformer mới cho mỗi phép biến đổi, tránh chia sẻ mutable `Transformer` giữa các request. Trong production, cần harden XML factories trước nguồn không tin cậy; tránh dump toàn bộ XML chứa dữ liệu nhạy cảm vào log.

## 11. API `sendSourceAndReceive(...)` và phạm vi của `SourceExtractor`

`sendSourceAndReceive(...)` là lựa chọn trung gian: request được đưa vào dưới dạng `Source`, response được trao cho một `SourceExtractor<T>` để ứng dụng đọc **payload Source**, không phải toàn bộ SOAP Envelope.

Ví dụ cho operation `GetDeliveryStatus`:

~~~java
import java.io.StringWriter;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamResult;
import org.springframework.xml.transform.StringSource;

String requestXml =
        "<n:GetDeliveryStatusRequest " +
        "xmlns:n=\"urn:example:notifications:v1\">" +
        "<n:eventId>EVT-1001</n:eventId>" +
        "</n:GetDeliveryStatusRequest>";

String responsePayloadXml =
        notificationWebServiceTemplate.sendSourceAndReceive(
            "https://partner.example.test/ws/notifications",
            new StringSource(requestXml),
            source -> {
                StringWriter output = new StringWriter();
                TransformerFactory.newInstance()
                        .newTransformer()
                        .transform(source, new StreamResult(output));
                return output.toString();
            });
~~~

Đây là **ví dụ đọc payload**, không phải một phép xác nhận delivery. Nếu cần SOAP Header, SOAP version, action hoặc thông tin Fault, `SourceExtractor` chưa phải tầng trừu tượng đầy đủ; dùng callback/extractor theo `WebServiceMessage` hoặc interceptor client phù hợp.

### 11.1. `SourceExtractor` chỉ thấy payload?

Trong luồng thông thường, extractor nhận `Source` của **payload response**, tức phần XML nghiệp vụ trong SOAP Body. Nó không được coi là API truy cập:

- Toàn bộ HTTP status/headers.
- SOAP Header (WS-Security, WS-Addressing, correlation ID).
- SOAP Envelope nguyên vẹn.
- MIME attachment/MTOM qua tất cả các implementation.
- Phần XML Fault theo một đường success response đã được fault resolver xử lý.

Nếu Body không chứa payload, extractor có thể không có nguồn XML hữu ích; phải kiểm thử cách API và implementation xử lý trường hợp này. **Không truyền `null` vào Transformer** rồi quy mọi lỗi thành “server trả response rỗng”.

### 11.2. Không trộn hai lời gọi XML API

`sendSourceAndReceiveToResult(...)` hướng về **ghi payload vào Result** và báo bằng boolean theo ngữ nghĩa overload; `sendSourceAndReceive(...)` hướng về **trả `T` do SourceExtractor tạo**. Cả hai đều khác `sendAndReceive(callback, extractor)` ở mức API: cách cuối cho phép thao tác với đối tượng message, kể cả SOAP-specific header/action.

Nếu ứng dụng cần trạng thái HTTP chính xác, như phân biệt 200, 202 và 204, không thể mặc định rằng bất kỳ trong ba API đều tự trả status code cho caller. Cần **quan sát transport bằng thành phần sender/callback được hỗ trợ hoặc integration test HTTP**, đồng thời tránh phụ thuộc chi tiết implementation nếu không được contract cam kết.

## 12. One-way có phải “fire-and-forget” không?

Trong ngôn ngữ nghiệp vụ, cụm từ *fire-and-forget* thường gợi ý “gửi xong thì không quan tâm phản hồi”. Với SOAP over HTTP, cách diễn đạt này dễ gây hiểu nhầm:

1. **Về WSDL:** one-way có input nhưng không có output message.
2. **Về API Java:** lời gọi `WebServiceTemplate` thường **đồng bộ về thao tác truyền tải**; thread caller có thể phải chờ kết nối, ghi request và đọc kết quả HTTP.
3. **Về hệ thống nhận:** có thể chỉ nhận vào hàng đợi, xử lý sau, hoặc xảy ra lỗi trước khi nhận.
4. **Về nghiệp vụ:** không có output SOAP không có nghĩa client được bảo đảm “at most once”, “exactly once” hay đã hoàn tất công việc.

### 12.1. Ba mốc cần quản lý

~~~mermaid
sequenceDiagram
    participant C as SOAP Client
    participant G as HTTP Gateway
    participant S as SOAP Server
    participant Q as Queue/Worker
    C->>G: PublishEventRequest (eventId)
    G->>S: SOAP request
    S->>Q: Ghi nhận event
    S-->>G: HTTP 202, không SOAP Envelope
    G-->>C: HTTP 202
    Note over C: Biết HTTP đã trả lời, chưa chắc worker xong
    Q-->>S: Xử lý bất đồng bộ
    Note over S: Cần trạng thái/receipt riêng nếu client cần đối soát
~~~

Mốc **transport responded** khác **accepted durably** và khác **processed successfully**. Sơ đồ giả định server ghi vào queue trước khi trả 202, nhưng triển khai cụ thể có thể khác. Hợp đồng tích hợp phải xác định mốc nào được đảm bảo, chứ không suy từ status code.

### 12.2. Idempotency và retry

Giả sử client gửi `PublishEventRequest` với `eventId=EVT-1001` rồi bị **read timeout**. Có hai khả năng:

- Server chưa nhận/ghi được sự kiện.
- Server đã ghi sự kiện nhưng phản hồi HTTP bị mất trên mạng.

Nếu retry một cách mù quáng, server có thể tạo bản ghi/sự kiện trùng lặp. Đối với nghiệp vụ có tác dụng phụ, nên:

- Gửi **event ID/idempotency key** ổn định qua mỗi lần retry của cùng một sự kiện.
- Phía server lưu và từ chối/bỏ qua yêu cầu trùng theo quy tắc nghiệp vụ đã định.
- Có API/status operation hoặc luồng acknowledgment để truy vấn tiến độ.
- Đặt retry backoff, số lần tối đa và phân biệt lỗi tạm thời với lỗi không thể retry.
- Đối soát các event có trạng thái không xác định thay vì ghi nhận thành công giả.

**Không có API nào của `WebServiceTemplate` tự cung cấp idempotency nghiệp vụ** chỉ vì operation là one-way.

### 12.3. Thiết kế khi thật sự cần kết quả đồng bộ

Nếu caller phải biết việc xử lý có thành công hay không **trước khi tiếp tục**, hãy cân nhắc thay đổi contract thành request-response có một response message:

~~~xml
<n:PublishEventResponse
    xmlns:n="urn:example:notifications:v1">
    <n:receiptId>RCPT-1001</n:receiptId>
    <n:status>ACCEPTED</n:status>
</n:PublishEventResponse>
~~~

Thậm chí response `ACCEPTED` vẫn có thể chỉ biểu thị queue nhận, không phải xử lý xong. Nếu cần xác minh hoàn thành, response phải phản ánh mốc nghiệp vụ đó hoặc có operation/query riêng. **Không thêm output message vào WSDL một chiều mà không đánh giá breaking change với client hiện hữu.**

## 13. SOAP Action, WS-Addressing và Body trong one-way call

One-way không miễn trừ yêu cầu tuân thủ **SOAP binding**. Với SOAP 1.1, request thường có:

~~~http
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:notifications:PublishEvent"
~~~

và SOAP Body:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:n="urn:example:notifications:v1">
    <soap:Body>
        <n:PublishEventRequest>
            <n:eventId>EVT-1001</n:eventId>
            <n:orderId>ORD-1001</n:orderId>
            <n:occurredAt>2026-11-27T09:00:00+07:00</n:occurredAt>
        </n:PublishEventRequest>
    </soap:Body>
</soap:Envelope>
~~~

**Ba thông tin không được đánh đồng:**

- HTTP URL `https://partner.example.test/ws/notifications` đưa message đến server.
- SOAP action `urn:example:notifications:PublishEvent` có thể được server sử dụng để phân biệt operation theo binding/`@SoapAction`.
- Root QName `{urn:example:notifications:v1}PublishEventRequest` dùng cho định tuyến theo payload, ví dụ `@PayloadRoot`.

Đổi một trường không tự động sửa hai trường còn lại. Với Spring-WS, `SoapActionCallback` giúp đặt action trên request message, **không sửa XML root QName được JAXB hoặc Source tạo ra**.

### 13.1. SOAP 1.2

SOAP 1.2 dùng namespace Envelope `http://www.w3.org/2003/05/soap-envelope` và media type thường là `application/soap+xml`. Action có thể được thể hiện bằng tham số `action`:

~~~http
Content-Type: application/soap+xml; charset=utf-8; action="urn:example:notifications:PublishEvent"
~~~

Không áp dụng máy móc `SOAPAction` header theo quy tắc SOAP 1.1 cho mọi SOAP 1.2 service. Factory phía client, WSDL binding, Content-Type và Fault code phải đồng bộ theo phiên bản.

### 13.2. WS-Addressing không phải HTTP SOAPAction

Nếu đối tác yêu cầu WS-Addressing, một SOAP Header có thể chứa `wsa:Action`, `wsa:MessageID` hoặc `wsa:ReplyTo`. Một số profile/policy có thể sử dụng `ReplyTo` hoặc các cơ chế định tuyến phản hồi bất đồng bộ.

Điều đó **không có nghĩa** mọi one-way SOAP automatically dùng WS-Addressing, hay `wsa:ReplyTo` sẽ tự hoạt động chỉ bằng cách đặt HTTP `SOAPAction`. Phải cấu hình tiêu chuẩn/policy cụ thể và kiểm thử các phần header được ký, xác nhận address, lỗi định tuyến và correlation.

## 14. Không có SOAP response, SOAP Fault và lỗi kết nối là ba đường khác nhau

Trong sản phẩm thực, nên thiết kế một **mô hình kết quả gọi dịch vụ** thay vì chỉ trả `boolean` hoặc `null` từ service wrapper:

| Nhóm kết quả | Tín hiệu quan sát được | Hướng xử lý |
| --- | --- | --- |
| Không có SOAP output như contract dự kiến | Request gửi qua HTTP và nhận acknowledgment phù hợp contract | Ghi nhận transport acknowledgment, tiếp tục theo dõi event |
| Có SOAP response với payload nghiệp vụ | JAXB/Source extractor nhận response | Đọc status/detail trong payload, validate XSD |
| Có SOAP Envelope nhưng Body rỗng | SOAP message tồn tại, payload không có | Đối chiếu WSDL: có cho phép không? |
| Có `AckResponse` rỗng | Payload có root QName nhưng không có child fields | Xử lý theo contract của response element |
| Có SOAP Fault | Fault code/reason/detail hợp đồng | Phân loại lỗi SOAP; không coi là response thành công |
| HTTP lỗi trả HTML/JSON | Không phải SOAP Envelope | Xử lý HTTP/proxy theo transport |
| Connect timeout/DNS/TLS | Không có response SOAP hợp lệ | Báo lỗi kết nối, dùng policy retry/đối soát |
| Read timeout sau khi ghi request | Không rõ outcome phía server | Không retry thao tác ghi khi chưa có cơ chế chống trùng |
| JAXB unmarshal failure | Có XML không map được object mong đợi | Kiểm tra schema, root QName, adapter và compatibility |

### 14.1. SOAP Fault được xử lý ở đâu?

Với `WebServiceTemplate`, một SOAP Fault thường đi qua fault detection/fault resolver và gây `SoapFaultClientException` theo cấu hình mặc định. Một mẫu phân loại:

~~~java
import org.springframework.ws.soap.client.SoapFaultClientException;

try {
    Object response = notificationWebServiceTemplate
            .marshalSendAndReceive(
                    "https://partner.example.test/ws/notifications",
                    request);
    // Chỉ xử lý đường không có Fault theo contract.
} catch (SoapFaultClientException fault) {
    String reason = fault.getFaultStringOrReason();
    // Đọc fault code/detail nếu được công bố.
    // Không log thẳng secret hoặc toàn bộ SOAP message.
}
~~~

Lưu ý: **SOAP Fault trước/không thuộc operation one-way** còn phụ thuộc binding và xử lý thực tế của server; một WSDL one-way không định nghĩa output nghiệp vụ để unmarshalling. HTTP transport vẫn có thể báo lỗi, và một số SOAP stack có thể tạo Fault trong những tình huống xử lý khác nhau. Không thiết kế client dựa trên giả định “one-way không bao giờ lỗi”.

### 14.2. Đừng catch mọi exception thành một “accepted”

Một anti-pattern:

~~~java
try {
    template.marshalSendAndReceive(request);
    return true;
} catch (Exception ignored) {
    return true; // SAI: âm thầm bỏ qua lỗi TLS, transport, XML...
}
~~~

Điều này che mất lỗi xác thực, lỗi HTTP, trục trặc gateway hoặc lỗi XML. Với ứng dụng quản lý thanh toán/đơn hàng, kết quả “thành công” giả có thể khiến sự kiện bị mất mà không có cơ chế đối soát.

Nên phân biệt:

1. **SOAP Fault**: lỗi có cấu trúc SOAP, phân tích mã và detail contract.
2. **Lỗi truyền tải**: DNS, kết nối, TLS, HTTP status không SOAP, timeout.
3. **Lỗi biến đổi XML**: JAXB, XSD validation, parsing, namespace.
4. **Trạng thái nghiệp vụ**: `ACCEPTED`, `QUEUED`, `DELIVERED`, `REJECTED` theo contract, **không đồng nhất với return value của API**.

## 15. An toàn XML, chứng chỉ và WS-Security ở SOAP client

Client one-way vẫn gửi thông điệp có thể chứa dữ liệu quan trọng. Việc không chờ SOAP output không làm các yêu cầu bảo mật biến mất.

### 15.1. TLS/mTLS

- **HTTPS** bảo vệ đường truyền và xác thực phía server thông qua hệ thống chứng chỉ.
- **mTLS** có thể xác thực thêm client bằng chứng chỉ khi đối tác yêu cầu.
- Phải quản lý truststore/keystore theo môi trường, kiểm tra expiration và rotation.
- Không vô hiệu hóa hostname verification hoặc bỏ qua kiểm tra chứng chỉ chỉ để “SOAP client chạy được”.
- Một lỗi TLS handshake xảy ra **trước** khi nhận SOAP response; không ánh xạ nó thành một SOAP Fault nghiệp vụ do server trả.

`WebServiceTemplate` dùng message sender phù hợp HTTP client/transport. Cách cấu hình TLS và timeout cụ thể phụ thuộc phiên bản Spring-WS, HTTP client implementation và framework Boot; không mặc định template tự dùng mọi custom truststore chỉ vì bean có mặt trong context.

### 15.2. WS-Security

WS-Security có thể yêu cầu token, timestamp, signature và encryption ở SOAP Header. Một client gửi one-way operation có thể vẫn cần ký request và tuân thủ policy của đối tác.

Các câu hỏi cần xác minh:

- Payload nào phải được ký hoặc mã hóa?
- Header nào phải có timestamp/username token?
- Chứng chỉ nào được đối tác tin cậy?
- Có giới hạn clock skew và chống replay không?
- Nếu server trả SOAP Fault có ký, client có kiểm chứng nó không?
- Với cơ chế asynchronous acknowledgment, correlation ID và message ID được bảo vệ thế nào?

Không tự thêm header vào message **sau khi nó đã được ký** nếu việc đó làm chữ ký không còn hợp lệ. Khi dùng `ClientInterceptor` như WSS4J security interceptor, cần kiểm tra thứ tự callback và policy thực tế.

### 15.3. Không log XML đầy đủ mặc định

`PublishEventRequest` có thể chứa mã đơn hàng, danh tính người nhận, địa chỉ hoặc thông tin giao hàng. SOAP Header có thể chứa UsernameToken và chữ ký. Trong production, ưu tiên log:

~~~text
eventId / correlationId
operation QName
SOAP version
endpoint logical name (không cần URL có credentials)
transport outcome category
SOAP Fault code (nếu có)
durationMs
retryAttempt
~~~

Với dữ liệu nhạy cảm, áp dụng masking, phân quyền log và retention. Không serialize toàn bộ SOAP message chỉ để điều tra vì payload/attachment lớn và thông tin bảo mật có thể bị lộ.

### 15.4. XML parsing trực tiếp

Nếu dùng `sendSourceAndReceive(...)` hoặc `sendAndReceive(...)` với `Source`/`Transformer`, hãy harden parser, chặn DTD/external entity và external stylesheet access khi có nguồn XML không đáng tin cậy. XSD validation cần thiết nhưng không thay thế chống XXE trước bước parsing. Với JAXB, cần thống nhất schema validation nếu hợp đồng yêu cầu; việc unmarshal được object không chứng minh mọi facet XSD đều đúng.

## 16. Xây dựng wrapper client với kết quả được đặt tên rõ

Để tránh lan truyền hiểu nhầm `null`/`boolean` vào tầng nghiệp vụ, nên tạo một adapter có ngữ nghĩa rõ:

~~~java
public enum PublishTransportOutcome {
    HTTP_ACK_OBSERVED,
    SOAP_RESPONSE_OBSERVED,
    SOAP_FAULT,
    TRANSPORT_FAILURE,
    UNKNOWN_AFTER_SEND
}
~~~

Đây là mô hình **minh họa**, không phải enum được Spring-WS cung cấp và không phải logic tự phân loại có sẵn. Việc chọn `HTTP_ACK_OBSERVED` cần quan sát status transport qua cơ chế phù hợp; chỉ có return value `marshalSendAndReceive` không đủ để chọn trạng thái này.

Nếu muốn theo dõi nghiệp vụ, dùng một mô hình riêng:

~~~java
public enum DeliveryBusinessStatus {
    UNKNOWN,
    ACCEPTED,
    QUEUED,
    DELIVERED,
    REJECTED
}
~~~

Sự phân tách giữa **transport outcome** và **business status** giúp hệ thống:

- Không đánh dấu `DELIVERED` ngay khi nhận HTTP 202.
- Đặt retry đúng khi có kết nối lỗi hoặc SOAP Fault được công bố là tạm thời.
- Cho phép đối soát khi outcome không xác định.
- Thu thập metric riêng về transport error, SOAP Fault và business rejection.
- Không sửa dữ liệu kế toán hoặc gửi thông báo hoàn thành dựa trên một `null` Java.

### 16.1. Không che lấp tính bất định

Một client wrapper không nên chuyển mọi `null` thành `HTTP_ACK_OBSERVED`. Khi chưa có đủ quan sát để phân loại:

~~~text
UNKNOWN_AFTER_SEND
~~~

phù hợp hơn “success” hoặc “failed” giả định. Dùng event ID ổn định để hỏi lại hệ thống nhận. Ngay cả khi request gửi qua HTTPS thành công, cần thỏa thuận rằng acknowledgment phản ánh bước nào của workflow.

### 16.2. Khi nào chọn operation request-response thay cho one-way?

| Yêu cầu nghiệp vụ | Thiết kế thường phù hợp |
| --- | --- |
| Chỉ phát tín hiệu, có outbox/queue và cơ chế đối soát riêng | WSDL one-way có thể phù hợp |
| Phải nhận receipt ID để tra cứu sau | Request-response trả `ReceiptResponse` |
| Phải biết kết quả xử lý ngay trong lời gọi | Request-response với response status/typed Fault |
| Payload lớn, xử lý bất đồng bộ | One-way hoặc submit+poll, tùy khả năng đối tác |
| Client bắt buộc phân biệt accepted/rejected đồng bộ | Contract phải khai báo tín hiệu đáp ứng rõ |

Không có lựa chọn mặc định tốt cho mọi hệ thống. Hợp đồng SOAP, đặc tính idempotency và SLA quan trọng hơn việc Java method trả `void` hay `Object`.

## 17. Chiến lược kiểm thử theo lớp

Kiểm thử đúng bài toán này phải phân biệt **WSDL**, **SOAP message** và **HTTP transport**. Một test chỉ gọi Java method hoặc assert `result == null` không đủ.

### 17.1. Ma trận kiểm thử

| Trường hợp | Kết quả cần quan sát |
| --- | --- |
| WSDL `PublishEvent` chỉ có `wsdl:input` | Contract one-way thực sự, không có `wsdl:output` |
| WSDL `GetDeliveryStatus` có input/output | Contract request-response với schema kết quả |
| HTTP 202, body 0 byte | API client xử lý theo quy tắc không SOAP response; không giả định nghiệp vụ xong |
| SOAP Envelope với `<Body/>` | Phân biệt SOAP message tồn tại và không có payload |
| SOAP Body chứa `<AckResponse/>` | Có root QName payload dù không có child field |
| SOAP response chứa `xsi:nil="true"` | Phân biệt nil theo XSD với không có message |
| SOAP Fault `Client/Sender` | Đi đường lỗi SOAP; không bị coi như accepted |
| SOAP Fault `Server/Receiver` | Phân loại theo hợp đồng, không retry mù quáng |
| HTTP 500 + HTML | Báo lỗi HTTP/proxy, không parse như SOAP Fault |
| HTTP 404/405/415 | Kiểm tra URL, method, Content-Type và SOAP binding |
| DNS/connect timeout | Lỗi transport; request có thể chưa được gửi |
| Read timeout sau khi ghi request | Outcome không xác định, kích hoạt đối soát |
| SOAP 1.1 vs SOAP 1.2 | Envelope, action, media type, binding phù hợp |
| SOAPAction không khớp QName | Server xử lý theo mapping/policy thực tế; kiểm tra consistency |
| JAXB response thiếu element bắt buộc | XSD validation hoặc unmarshalling báo lỗi phù hợp |
| Nhiều request cùng event ID | Server chống trùng theo idempotency contract |
| WS-Security signature/token sai | Bị từ chối theo security policy |
| Mất TLS certificate trust | Lỗi TLS trước SOAP, không coi như response rỗng |

### 17.2. Kiểm thử client Spring-WS bằng mock

`MockWebServiceServer` là lựa chọn hữu ích để kiểm tra **payload request**, SOAP action và response body với `WebServiceTemplate` ở mức Spring-WS:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import java.io.StringWriter;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamResult;
import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

class NotificationClientTest {
    @Test
    void readsDeliveryStatusResponse() {
        WebServiceTemplate template = new WebServiceTemplate();
        MockWebServiceServer server =
                MockWebServiceServer.createServer(template);

        String requestXml =
                "<n:GetDeliveryStatusRequest " +
                "xmlns:n=\"urn:example:notifications:v1\">" +
                "<n:eventId>EVT-1001</n:eventId>" +
                "</n:GetDeliveryStatusRequest>";

        String responseXml =
                "<n:GetDeliveryStatusResponse " +
                "xmlns:n=\"urn:example:notifications:v1\">" +
                "<n:status>DELIVERED</n:status>" +
                "</n:GetDeliveryStatusResponse>";

        server.expect(payload(new StringSource(requestXml)))
              .andRespond(withPayload(new StringSource(responseXml)));

        String actual = template.sendSourceAndReceive(
                "https://partner.example.test/ws/notifications",
                new StringSource(requestXml),
                source -> {
                    StringWriter output = new StringWriter();
                    TransformerFactory.newInstance()
                            .newTransformer()
                            .transform(source, new StreamResult(output));
                    return output.toString();
                });

        assertTrue(actual.contains("DELIVERED"));
        server.verify();
    }
}
~~~

Test gửi request qua chính `WebServiceTemplate` và kiểm tra mock server đã nhận yêu cầu mong đợi. Đây là **test minh họa ở mức Spring-WS**, chưa phải test HTTP(S) end-to-end. Assertion `contains("DELIVERED")` chỉ kiểm tra text quan trọng; với contract-first nghiêm ngặt nên parse response thành XML và assert QName, namespace, giá trị và XSD. Dependency Spring-WS test phù hợp phải có trong dự án.

Test mock giúp kiểm tra XML SOAP ở mức template, nhưng **không khẳng định** remote server thật sẽ trả HTTP 202/no body, không kiểm tra TLS, reverse proxy hay HTTP status. Một số framework mock không mô phỏng chính xác trường hợp không tạo response hoặc transport đóng kết nối; không ép test giả mạo phản hồi để kết luận one-way hoạt động.

### 17.3. Kiểm thử HTTP(S) thật hoặc fake server có kiểm soát

Để phân biệt chính xác:

1. Server trả HTTP 202 không body.
2. Server trả HTTP 200 với SOAP Envelope/Body rỗng.
3. Server trả HTTP 200 với `<AckResponse/>`.
4. Server trả HTTP 500 kèm SOAP Fault.
5. Gateway trả HTTP 502 kèm HTML.
6. Server trả response trễ hơn read timeout.

Hãy dùng test HTTP server/gateway hỗ trợ điều khiển status/headers/body và chạy **`WebServiceTemplate` thật** qua message sender đã cấu hình. Ghi lại loại exception/giá trị trả về của từng API và phiên bản Spring-WS, thay vì đoán chỉ từ tài liệu hoặc mock.

### 17.4. XML fixture không phụ thuộc prefix

Khi kiểm tra SOAP XML, so sánh **expanded QName** (namespace URI + local name), giá trị và schema, không đòi serializer dùng cùng prefix hoặc whitespace. Như:

~~~xml
<n:PublishEventRequest xmlns:n="urn:example:notifications:v1"/>
~~~

và:

~~~xml
<p:PublishEventRequest xmlns:p="urn:example:notifications:v1"/>
~~~

có cùng root QName. Nhưng:

~~~xml
<PublishEventRequest/>
~~~

không có namespace và không tương đương theo contract.

## 18. Tình huống thực hành: hai đối tác cùng trả `null`

Đội tích hợp gọi hai SOAP service:

**Đối tác A** công bố WSDL operation `PublishEvent` chỉ có input. Khi client gửi request, đối tác trả HTTP 202, không SOAP body. Method `marshalSendAndReceive` tại client quan sát `null`.

**Đối tác B** công bố operation `GetAck` kiểu request-response, có output element `AckResponse` với `nillable="true"`. Đối tác trả SOAP Envelope có `<AckResponse xsi:nil="true"/>`; JAXB mapping có thể cũng dẫn đến một giá trị `null`, tùy DTO/root handling.

Nhóm phát triển đang có code:

~~~java
Object result = template.marshalSendAndReceive(uri, request);
if (result == null) {
    markAsDelivered();
}
~~~

**Hãy trả lời:**

1. `null` ở hai trường hợp có cùng ý nghĩa không?
2. Đối tác A trả 202 có chứng minh event đã được xử lý xong không?
3. Muốn biết B đã gửi SOAP Envelope hay không thì quan sát gì?
4. Nếu A bị read timeout sau khi gửi, có nên tự retry bằng event ID mới không?
5. Dùng `sendAndReceive(callback, extractor)` có giúp phân biệt response message và payload rỗng không?
6. Khi nào cần sửa WSDL thay vì chỉ đổi code client?

**Đáp án gợi ý:**

1. **Không.** A có thể không có SOAP response; B có SOAP message và nil element theo XSD.
2. **Không.** 202 ở HTTP không cam kết worker đã xử lý nghiệp vụ; cần receipt/status contract hoặc đối soát.
3. Quan sát SOAP Envelope/Body và QName bằng extractor mức message hoặc test HTTP thực; không chỉ xét JAXB return value.
4. **Không nên.** Giữ idempotency key/event ID cho cùng một event và đối soát outcome chưa xác định.
5. **Có thể.** Khi extractor trả một object sentinel khác null, client có thể nhận biết extractor đã được gọi và kiểm tra payload, nhưng vẫn cần test việc xử lý Fault/transport.
6. Khi nhu cầu nghiệp vụ đòi receipt, trạng thái xử lý đồng bộ hoặc typed output mà WSDL one-way không có; đó là thay đổi hợp đồng, cần thống nhất với đối tác và kiểm tra tương thích.

### 18.1. Bài thực hành mở rộng

Hãy xây dựng một SOAP client cho `PublishEventRequest` và `GetDeliveryStatusRequest` theo contract ở mục 4:

- Sinh JAXB classes từ XSD bằng công cụ tương thích với Java/Jakarta đang dùng.
- Cấu hình `WebServiceTemplate`, SOAP version và `SoapActionCallback`.
- Viết một đường gọi JAXB `marshalSendAndReceive` và một đường gọi XML `sendAndReceive(callback, extractor)`.
- Tạo HTTP test fixture có 202/no body, Envelope/Body rỗng, `AckResponse` rỗng và SOAP Fault.
- Ghi nhận **transport outcome** và **business status** trong hai trường độc lập.
- Đặt HTTP connect/read timeouts và policy retry có giới hạn, giữ event ID ổn định.
- Thêm kiểm thử XML namespace/XSD và WS-Security/TLS khi contract yêu cầu.
- Ghi log metadata an toàn, không dump token hoặc toàn bộ SOAP message.

**Tiêu chí đạt:** hệ thống không đánh dấu giao hàng hoàn tất chỉ vì Java trả `null`/`true`, không nhầm SOAP Fault với HTTP lỗi và có khả năng đối soát trường hợp không xác định sau khi gửi.

## 19. Các anti-pattern thường gặp

| Anti-pattern | Vì sao sai | Thay bằng |
| --- | --- | --- |
| “One-way nên gọi Java method không chờ mạng” | HTTP sender vẫn thực hiện I/O đồng bộ theo API | Xác định transport timeout và acceptance contract |
| “`marshalSendAndReceive()==null` nghĩa là accepted” | `null` không mang một mã trạng thái nghiệp vụ duy nhất | Receipt/status riêng hoặc quan sát transport có kiểm soát |
| “`sendSourceAndReceiveToResult` trả true nghĩa là delivered” | Boolean liên quan đường xử lý response, không phải delivery | Đọc payload/status, đối soát |
| “SOAP Body rỗng nghĩa là không có HTTP response” | Envelope có thể tồn tại với Body rỗng | Quan sát mức message và HTTP |
| “`AckResponse/>` là không có payload” | Có QName response element | Xác thực XSD và xử lý response theo contract |
| “One-way không bao giờ trả Fault” | Lỗi transport/SOAP vẫn có thể xảy ra tùy binding | Phân loại lỗi và kiểm thử stack |
| “HTTP 202 chứng minh giao dịch hoàn thành” | 202 không phải kết quả nghiệp vụ cuối | Truy vấn tiến độ/receipt |
| “Timeout thì gửi lại bằng event ID khác” | Có thể tạo bản ghi trùng | Idempotency key ổn định và reconciliation |
| “Test mock SOAP pass nghĩa là TLS/proxy đúng” | Mock không thay thế wire transport | HTTP(S) integration test |
| “Chỉ dùng SOAPAction để chọn service” | Action, payload QName và URL là thông tin khác nhau | Đồng bộ WSDL/binding/dispatcher |
| “Log toàn bộ message để debug” | Có thể lộ token, PII và attachment lớn | Log metadata và masking |
| “Lỗi JAXB cũng là SOAP Fault” | XML binding failure khác Fault do server trả | Phân loại lỗi theo tầng |

## 20. Checklist trước khi gọi one-way SOAP trong production

1. **WSDL:** operation thực sự chỉ có input hay có output element rỗng?
2. **Binding:** SOAP 1.1 hay SOAP 1.2, action, Content-Type và địa chỉ endpoint nào?
3. **XSD:** root QName, minOccurs/nillable, XML date/time, enum và kiểu số có được thống nhất?
4. **Client API:** cần JAXB object, XML payload Source hay quan sát toàn bộ SOAP message?
5. **Return semantics:** `null`, boolean và object extractor được diễn giải ra sao trong API thực tế?
6. **HTTP behavior:** server trả status nào và có SOAP body hay không, đã được xác minh qua test?
7. **Acceptance:** 200/202 phản ánh “đã nhận”, “đã ghi bền vững” hay “đã xử lý xong”?
8. **Fault:** SOAP Fault code/detail và các lỗi HTTP không phải SOAP được phân loại riêng chưa?
9. **Timeout:** connect/read timeout, backoff và policy retry có phù hợp với nghiệp vụ?
10. **Idempotency:** cùng event ID khi retry, server có chống xử lý trùng không?
11. **Reconciliation:** có operation/status/callback để kiểm tra kết quả bất đồng bộ không?
12. **Security:** TLS/mTLS, WS-Security token/signature, chứng chỉ và chính sách log có đúng không?
13. **Parser:** XML external entities/DTD và các giới hạn input có được kiểm soát?
14. **Test:** có kiểm thử 202/no body, SOAP Body rỗng, nil, empty element, Fault và timeout?
15. **Compatibility:** kiểm thử với WSDL/XSD, JAXB runtime và implementation đối tác thực tế chưa?

## 21. Ghi nhớ

- **WSDL one-way** nghĩa là operation có input nhưng không khai báo output thông thường; nó **không** tự bảo đảm “không đợi HTTP” hoặc xử lý nghiệp vụ hoàn tất.
- **Không có SOAP response**, **SOAP Envelope với Body rỗng**, **response element rỗng** và **`xsi:nil`** là những trạng thái **khác nhau**.
- **`marshalSendAndReceive`** trả giá trị từ JAXB unmarshal khi có response phù hợp; `null` không phải mã trạng thái business accepted/delivered.
- **`sendSourceAndReceiveToResult`** dùng `Source`/`Result` và boolean phản ánh đường xử lý response theo API, không phải business success.
- **`sendSourceAndReceive`** dùng `SourceExtractor` cho payload; **`sendAndReceive(callback, extractor)`** cho phép làm việc với `WebServiceMessage` để quan sát response ở mức message.
- **Callback/extractor không tự bảo đảm giao dịch đã xử lý**. Muốn biết điều đó cần receipt, status contract, event ID và cơ chế đối soát.
- **SOAP Fault** phải được phân biệt với response JAXB bình thường, HTTP lỗi HTML, TLS failure và timeout.
- **SOAP Action, root payload QName và endpoint URL** là ba khía cạnh khác nhau, phải cùng tuân thủ XSD/WSDL và binding.
- **Retry operation có tác dụng phụ** cần idempotency; read timeout có thể để lại outcome chưa xác định.
- Khi tích hợp SOAP contract-first với Spring-WS, cần kiểm thử cả **XML/schema, SOAP version, WS-Security, chứng chỉ, HTTP transport và business acknowledgment** để vận hành doanh nghiệp ổn định.
