# WebServiceMessage và SoapMessage trong mô hình thông điệp

## 1. Vì sao cần hiểu mô hình thông điệp?

Trong **Spring Web Services (Spring-WS)**, một dịch vụ SOAP không chỉ nhận object Java rồi trả object Java. Trên đường truyền, hệ thống trao đổi **thông điệp XML**: SOAP Envelope có Header, Body, có thể có Fault và các thông tin khác như action, chữ ký WS-Security hoặc phần đính kèm. Spring-WS dùng các abstraction về thông điệp để kết nối tầng vận chuyển, xử lý XML, ánh xạ endpoint và nghiệp vụ.

Với cách phát triển **contract-first**, nhóm phát triển thiết kế **XSD/WSDL** trước, sinh mã **JAXB** khi cần, rồi hiện thực endpoint và SOAP client. Để phân tích lỗi tích hợp, bạn phải phân biệt:

- **`WebServiceMessage`:** abstraction chung cho một thông điệp web service, cung cấp cách đọc/ghi phần payload XML và tuần tự hóa thông điệp.
- **`SoapMessage`:** abstraction chuyên biệt cho thông điệp SOAP, bổ sung Envelope, Header, Body, SOAP version, SOAP Action và các thao tác đặc thù SOAP.
- **`MessageContext`:** ngữ cảnh một lần trao đổi thông điệp ở phía xử lý server, giữ request/response và các thuộc tính liên quan đến việc xử lý.
- **`WebServiceMessageFactory` / `SoapMessageFactory`:** đối tượng tạo hoặc đọc thông điệp, thường dùng một implementation SAAJ khi xử lý SOAP.

Bài học thuộc chương **Kiến trúc xử lý**, tập trung vào vai trò, API và vòng đời của `WebServiceMessage` cùng `SoapMessage`. Cuối bài, bạn có thể giải thích vì sao một endpoint nhận đúng JAXB request nhưng vẫn lỗi SOAP Header, vì sao `SOAPAction` khác payload QName, cách interceptor quan sát thông điệp và cách kiểm thử những khác biệt này.

## 2. Vị trí của hai interface trong kiến trúc Spring-WS

Mô hình khái niệm:

~~~mermaid
flowchart TD
    C["SOAP client / WebServiceTemplate"] --> T["HTTP(S) transport"]
    T --> S["MessageDispatcherServlet"]
    S --> F["WebServiceMessageFactory / SoapMessageFactory"]
    F --> M["MessageContext: request / response"]
    M --> I["EndpointMapping và EndpointInterceptor"]
    I --> A["EndpointAdapter"]
    A --> E["@Endpoint / nghiệp vụ"]
    E --> A
    A --> M
    M --> O["WebServiceMessage / SoapMessage response"]
    O --> T
~~~

Sơ đồ là **mô hình khái quát**; thứ tự chi tiết của mapping, interceptor, xử lý exception và tạo response phụ thuộc đường đi thực tế của dispatcher. Ý chính: HTTP cung cấp kênh vận chuyển, **message factory** tạo biểu diễn thông điệp, **dispatcher** tổ chức xử lý và **endpoint** thực hiện logic ứng dụng.

| Thành phần | Cấp trừu tượng | Điều nó quản lý |
| --- | --- | --- |
| `WebServiceMessage` | Một thông điệp | Payload XML, kết quả ghi payload, serialize thông điệp |
| `SoapMessage` | Một thông điệp SOAP | SOAP Envelope/Header/Body, version, action |
| `MessageContext` | Một lần xử lý request/response | Request, response và thuộc tính xử lý |
| `WebServiceMessageFactory` | Cơ chế tạo/đọc | Tạo thông điệp mới hoặc đọc thông điệp từ input |
| `WebServiceTemplate` | SOAP/web service client | Chuẩn bị request, truyền tải, nhận và diễn giải response |
| `MessageDispatcherServlet` | HTTP server entry point | Nhận HTTP request và đưa vào Spring-WS |
| `EndpointInterceptor` | Điểm can thiệp trước/sau endpoint | Validation, security, tracing và xử lý thông điệp |

**Quan hệ quan trọng:** một `SoapMessage` cũng là một `WebServiceMessage`, nhưng không phải mọi implementation `WebServiceMessage` đều có API SOAP. Nếu API được khai báo bằng kiểu `WebServiceMessage`, không được gọi `getSoapHeader()` cho đến khi xác định đối tượng thật là `SoapMessage`.

## 3. `WebServiceMessage`: abstraction chung của thông điệp

`org.springframework.ws.WebServiceMessage` là interface cấp thấp mô tả một thông điệp web service. Các phương thức cốt lõi thường được sử dụng:

| API | Vai trò |
| --- | --- |
| `getPayloadSource()` | Lấy `javax.xml.transform.Source` để đọc payload XML |
| `getPayloadResult()` | Lấy `javax.xml.transform.Result` để ghi payload XML |
| `writeTo(OutputStream)` | Serialize thông điệp thành byte để gửi hoặc kiểm tra |

### 3.1. Payload khác toàn bộ thông điệp

Giả sử HTTP request mang SOAP:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
    <soap:Header>
        <o:CorrelationId>REQ-2048</o:CorrelationId>
    </soap:Header>
    <soap:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Đối với SOAP document/literal thông thường, phần payload mà endpoint thao tác là phần tử nghiệp vụ **`o:GetOrderRequest` trong Body**. Nó khác với:

1. **SOAP Envelope**: phần tử bọc ngoài, thuộc namespace SOAP.
2. **SOAP Header**: các thành phần mở rộng như correlation ID, WS-Addressing và WS-Security.
3. **SOAP Body**: container chứa nội dung yêu cầu/phản hồi, có thể chứa SOAP Fault khi có lỗi.
4. **HTTP headers**: `Content-Type`, HTTP authentication, `SOAPAction` trong SOAP 1.1; các header này nằm **ngoài XML Envelope**.

`getPayloadSource()` dành cho **payload**, không có nghĩa nó trả về toàn bộ Envelope kèm Header. Khi cần đọc SOAP Header hoặc kiểm tra Fault, sử dụng `SoapMessage` và các API tương ứng.

### 3.2. `Source` là đầu vào XML, `Result` là nơi nhận XML

`Source` và `Result` là abstraction chuẩn trong Java API for XML Processing (JAXP), nằm trong `javax.xml.transform`:

- `Source` biểu diễn một nguồn dữ liệu XML để đọc/chuyển đổi.
- `Result` biểu diễn đích để ghi kết quả biến đổi XML.
- `Transformer` có thể chuyển nội dung từ một `Source` sang `Result`.

Một đoạn minh họa độc lập cho việc **ghi payload vào message mới**:

~~~java
import java.io.ByteArrayOutputStream;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;
import org.springframework.xml.transform.StringSource;

SaajSoapMessageFactory factory = new SaajSoapMessageFactory();
factory.setSoapVersion(SoapVersion.SOAP_11);
factory.afterPropertiesSet();

WebServiceMessage message = factory.createWebServiceMessage();

String payload =
        "<o:GetOrderRequest xmlns:o=\"urn:example:orders:v1\">"
      + "<o:orderId>ORD-1001</o:orderId>"
      + "</o:GetOrderRequest>";

Transformer transformer =
        TransformerFactory.newInstance().newTransformer();
transformer.transform(
        new StringSource(payload),
        message.getPayloadResult());

SoapMessage soap = (SoapMessage) message;
soap.setSoapAction("urn:example:orders:GetOrder");

ByteArrayOutputStream output = new ByteArrayOutputStream();
message.writeTo(output);
byte[] serializedMessage = output.toByteArray();
~~~

Ví dụ này cho thấy sự khác nhau giữa **ghi một payload** vào `getPayloadResult()` và **serialize thông điệp** qua `writeTo(...)`. Với `SoapMessage` do SAAJ tạo, phần serialize mang SOAP Envelope, không chỉ riêng `GetOrderRequest`. Kết quả từng byte, prefix XML hoặc thứ tự các namespace declaration tùy implementation; không so sánh XML như chuỗi cố định.

Đây là ví dụ minh họa API Spring-WS/SAAJ, **chưa phải chương trình hoàn chỉnh**: Maven/Gradle cần có dependency Spring-WS và SAAJ/JAXB tương thích. Trong ứng dụng thực tế, nên chọn message factory qua cấu hình chung và xử lý payload bằng JAXB hoặc thành phần XML phù hợp, thay vì tạo factory/transformer theo mỗi nghiệp vụ.

### 3.3. Không lạm dụng `writeTo(...)` để log dữ liệu

`writeTo(OutputStream)` hữu ích khi kiểm tra serialization hoặc viết adapter vận chuyển; tuy nhiên dump toàn bộ SOAP message có thể chứa:

- Header WS-Security với UsernameToken, timestamp, chữ ký hoặc dữ liệu xác thực.
- Dữ liệu cá nhân, thanh toán hoặc mã giao dịch trong Body.
- Dữ liệu lớn hoặc attachment khiến log tăng mạnh.

Trong production, nên log **correlation ID, QName payload, SOAP version, action, trạng thái xử lý và thời gian**, cùng cơ chế masking nếu cần. Việc serialize một thông điệp để log cũng có thể tốn tài nguyên và ảnh hưởng hành vi của implementation khi thông điệp đang được xây dựng hoặc luồng dữ liệu chưa được tiêu thụ hoàn toàn.

## 4. `SoapMessage` mở rộng mô hình cho SOAP

`org.springframework.ws.soap.SoapMessage` là interface chuyên biệt, kế thừa `WebServiceMessage`. Những thao tác quan trọng:

| API `SoapMessage` | Dùng để làm gì |
| --- | --- |
| `getEnvelope()` | Truy cập biểu diễn SOAP Envelope |
| `getSoapHeader()` | Truy cập SOAP Header |
| `getSoapBody()` | Truy cập SOAP Body, bao gồm khả năng chứa Fault |
| `getVersion()` | Xác định phiên bản SOAP của thông điệp |
| `getSoapAction()` | Đọc action của thông điệp theo mô hình Spring-WS |
| `setSoapAction(String)` | Đặt action cho thông điệp gửi ra |

Ví dụ quan sát một message khi đã biết nó là SOAP:

~~~java
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.soap.SoapBody;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.SoapVersion;

void inspect(WebServiceMessage message) {
    if (!(message instanceof SoapMessage)) {
        throw new IllegalArgumentException("Expected a SOAP message");
    }

    SoapMessage soapMessage = (SoapMessage) message;
    SoapVersion version = soapMessage.getVersion();
    String action = soapMessage.getSoapAction();
    SoapBody body = soapMessage.getSoapBody();

    boolean fault = body.hasFault();

    // Ghi nhận version/action/fault vào hệ thống theo dõi
    // mà không log nội dung SOAP nhạy cảm.
}
~~~

API `getSoapHeader()`, `getEnvelope()` cung cấp lối vào các thành phần SOAP đặc thù. Nếu endpoint chỉ quan tâm đối tượng nghiệp vụ từ Body, nó có thể dùng `@RequestPayload` mà không cần trực tiếp thao tác `SoapMessage`. Khi làm security, header processing hoặc SOAP Fault, phải hiểu phần chuyên biệt.

## 5. Envelope, Header và Body: mỗi phần mang một trách nhiệm

### 5.1. Cấu trúc SOAP 1.1

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1"
    xmlns:sec="urn:example:security:v1">
    <soap:Header>
        <sec:ClientId soap:mustUnderstand="1">APP-A</sec:ClientId>
    </soap:Header>
    <soap:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Ba phần tử `Envelope`, `Header` và `Body` ở đây dùng namespace SOAP 1.1: `http://schemas.xmlsoap.org/soap/envelope/`. `GetOrderRequest` thuộc namespace nghiệp vụ khác: `urn:example:orders:v1`.

**Header** có thể chứa thông tin phục vụ xử lý thông điệp, chẳng hạn truy vết, định tuyến hoặc WS-Security. Thuộc tính `mustUnderstand` có nghĩa tại SOAP node đích: node được yêu cầu xử lý header tương ứng theo quy tắc SOAP; nếu không thể thực hiện, SOAP có cơ chế Fault `MustUnderstand`. Header ví dụ ở trên là **mở rộng minh họa**; không tự trở thành một chính sách bảo mật có hiệu lực nếu chưa có code/interceptor hiểu `sec:ClientId`.

**Body** chứa nội dung nghiệp vụ theo hợp đồng XSD/WSDL hoặc SOAP Fault. Với mô hình document/literal, phần tử con đầu của Body thường là global element request/response. Không suy ra toàn bộ contract chỉ từ local name của Java method; cần đối chiếu expanded name của phần tử XML.

### 5.2. Cấu trúc SOAP 1.2

~~~xml
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:o="urn:example:orders:v1">
    <env:Header/>
    <env:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </env:Body>
</env:Envelope>
~~~

SOAP 1.2 dùng namespace Envelope `http://www.w3.org/2003/05/soap-envelope`. SOAP 1.1 và SOAP 1.2 **không tương đương chỉ vì cùng có các local name Envelope/Header/Body**. Message factory, HTTP Content-Type, WSDL binding và cách xử lý SOAP Fault phải đúng phiên bản.

| Khía cạnh | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Namespace Envelope | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| HTTP media type phổ biến | `text/xml` | `application/soap+xml` |
| HTTP action điển hình | `SOAPAction` header | Tham số `action` của media type khi được sử dụng |
| Fault code chính phía gửi | `Client` | `Sender` |
| Fault code chính phía nhận | `Server` | `Receiver` |

Đổi namespace Envelope trong chuỗi XML mà không đồng bộ binding/MessageFactory **không phải phương pháp chuyển SOAP version hợp lệ**.

## 6. `SoapBody` và SOAP Fault

`SoapBody` đại diện cho Body của SOAP message. Tại đây có thể đọc trạng thái Fault:

~~~java
import org.springframework.ws.soap.SoapBody;
import org.springframework.ws.soap.SoapFault;
import org.springframework.ws.soap.SoapMessage;

void inspectFault(SoapMessage soapMessage) {
    SoapBody body = soapMessage.getSoapBody();
    if (body.hasFault()) {
        SoapFault fault = body.getFault();
        String reason = fault.getFaultStringOrReason();
        // Có thể đọc mã Fault, detail theo SOAP version/hợp đồng.
    }
}
~~~

Ví dụ SOAP 1.1 Fault:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>Invalid orderId</faultstring>
            <detail>
                <e:OrderFault
                    xmlns:e="urn:example:orders:fault:v1">
                    <e:errorCode>ORDER_ID_INVALID</e:errorCode>
                </e:OrderFault>
            </detail>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Với SOAP 1.2, phần tử Fault có cấu trúc `env:Code`, `env:Reason` và `env:Detail`. Không viết code chỉ đọc `faultstring` theo giả định mọi thông điệp là SOAP 1.1. Các phương thức của Spring-WS như `getFaultStringOrReason()` giúp che bớt sự khác biệt ở mức API, nhưng các mã/chi tiết cụ thể vẫn phải đối chiếu với hợp đồng.

Trong Spring-WS, ngoại lệ từ endpoint có thể được chuyển thành SOAP Fault qua `EndpointExceptionResolver` như `SoapFaultMappingExceptionResolver` hoặc `SoapFaultAnnotationExceptionResolver` khi được cấu hình. **Không phải mọi Java exception đều tự trở thành Fault nghiệp vụ có detail được định nghĩa trong WSDL**. Lỗi DNS/TLS/gateway có thể xảy ra trước khi Spring-WS tạo được bất kỳ SOAP response nào.

Ở SOAP client dùng `WebServiceTemplate`, khi nhận SOAP Fault, luồng xử lý thông thường có thể ném `SoapFaultClientException` thay vì trả về đối tượng JAXB response. Vì vậy không giả định mọi thông điệp Fault sẽ đi qua nhánh xử lý kết quả thành công.

## 7. `SoapHeader`, action và những thông tin ở ngoài Body

### 7.1. SOAP Header không phải HTTP Header

So sánh hai đoạn thông tin:

~~~http
POST /ws/orders HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:GetOrder"
~~~

~~~xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:t="urn:example:trace:v1">
    <t:CorrelationId>REQ-2048</t:CorrelationId>
</soap:Header>
~~~

`SOAPAction` trong SOAP 1.1 là **HTTP header**, trong khi `CorrelationId` ở ví dụ là một **XML element trong SOAP Header**. Với WS-Addressing, `wsa:Action` có thể là phần tử trong SOAP Header; nó không tự động đồng nhất với HTTP `SOAPAction` dù các chính sách tương tác có thể yêu cầu liên hệ giữa chúng.

Spring-WS cung cấp `SoapMessage.setSoapAction(...)` ở abstraction SOAP để đặt action trên request. Cách action được ghi ra transport phụ thuộc phiên bản SOAP và sender/binding; với SOAP 1.1 HTTP thông thường, nó liên quan đến header `SOAPAction`. Đừng thử dùng `getPayloadResult()` để thêm HTTP header hoặc SOAP Header: payload Result là nơi ghi **nội dung Body**.

### 7.2. Header phục vụ WS-Security và định tuyến

WS-Security thường đặt các thành phần bảo mật vào SOAP Header: token, timestamp, signature, encryption metadata hoặc các thành phần được policy chỉ định. Những header này có thể được interceptor kiểm tra trước khi phương thức `@Endpoint` xử lý nghiệp vụ.

Hệ quả:

- Payload JAXB hợp lệ **chưa chắc** làm request được chấp nhận nếu signature sai hoặc token hết hạn.
- Một SOAP Header bị xử lý không đúng có thể dẫn đến Fault trước khi endpoint chạy.
- **Không nên xóa/sửa header bảo mật** trong interceptor tự viết nếu chưa hiểu canonicalization, chữ ký và policy; sửa nội dung sau khi ký có thể làm chữ ký không hợp lệ.
- Header namespace và `mustUnderstand` cần được xử lý đúng theo SOAP version và vai trò node.

## 8. `WebServiceMessageFactory` và implementation của SOAP message

Một interface thông điệp không tự tạo ra XML parser hoặc SOAP Envelope. Vai trò đó thuộc **message factory**. Tại phía server, Spring-WS nhận bytes từ transport, sử dụng factory để tạo message, rồi chuyển nó cho dispatcher.

Hai thao tác mang tính khái niệm:

~~~java
WebServiceMessage fresh = messageFactory.createWebServiceMessage();

WebServiceMessage incoming =
        messageFactory.createWebServiceMessage(inputStream);
~~~

Biến `messageFactory` ở đây có kiểu `WebServiceMessageFactory`, còn `inputStream` là dữ liệu thông điệp nhận từ transport. Đây là ví dụ độc lập mô tả API, chưa khai báo cách lấy stream, sở hữu/đóng stream và xử lý exception.

Khi làm việc với SOAP, ứng dụng thường sử dụng factory có khả năng tạo `SoapMessage`. Một lựa chọn là **`SaajSoapMessageFactory`**:

~~~java
SaajSoapMessageFactory soap11Factory =
        new SaajSoapMessageFactory();
soap11Factory.setSoapVersion(SoapVersion.SOAP_11);
soap11Factory.afterPropertiesSet();

SoapMessage request =
        soap11Factory.createWebServiceMessage();
~~~

Factory này tạo message được hỗ trợ bởi SAAJ. Đoạn minh họa giả định runtime đã có API/implementation SAAJ tương thích. Các tùy chọn factory và khả năng hỗ trợ SOAP 1.2 phụ thuộc phiên bản Spring-WS, SOAP stack và cấu hình thực tế.

### 8.1. Cấu hình SOAP version ở factory

Với các hệ thống hỗ trợ SOAP 1.2, factory có thể được cấu hình với:

~~~java
factory.setSoapVersion(SoapVersion.SOAP_12);
~~~

Điều đó chưa đủ để công bố một dịch vụ SOAP 1.2 hoàn chỉnh: WSDL phải có binding phù hợp, Content-Type của request/response phải đúng, endpoint cùng interceptor phải hỗ trợ message và lỗi theo SOAP 1.2. Cũng không nên tưởng rằng thay version của factory sẽ tự sửa WSDL tĩnh đã công bố cho đối tác.

### 8.2. SAAJ là một implementation, không phải hợp đồng WSDL

SAAJ cung cấp mô hình XML/SOAP message ở mức thư viện. `SaajSoapMessage` là lớp triển khai `SoapMessage` tương ứng. Code ứng dụng nên ưu tiên **interface Spring-WS** khi chỉ cần đọc SOAP Header/Body/action; sử dụng lớp SAAJ cụ thể khi thực sự cần tính năng mức thấp và đã kiểm soát dependency.

Điểm quan trọng trong thiết kế: **đừng gắn hợp đồng SOAP của đối tác vào một implementation Java cụ thể**. Client .NET hoặc một ngôn ngữ khác không thấy đối tượng `SaajSoapMessage`; họ chỉ nhận XML và HTTP theo WSDL/XSD cùng các chính sách bảo mật đã thỏa thuận.

## 9. `MessageContext` khác `WebServiceMessage` như thế nào?

Trong một lần xử lý SOAP request, server cần quản lý **request message**, khả năng tạo **response message** và dữ liệu phụ trợ. `org.springframework.ws.context.MessageContext` đóng vai trò đó.

Các API thường được dùng:

| API `MessageContext` | Ý nghĩa |
| --- | --- |
| `getRequest()` | Lấy request `WebServiceMessage` đang xử lý |
| `hasResponse()` | Kiểm tra có response được tạo hay chưa |
| `getResponse()` | Lấy response message, có thể tạo khi cần theo cơ chế context |
| `setResponse(WebServiceMessage)` | Đặt response message trong context |
| `getProperty(...)` / `setProperty(...)` | Chia sẻ thuộc tính giữa các bước xử lý trong context |

**`MessageContext` không phải một SOAP Envelope**. Nó là đối tượng điều phối vòng xử lý, có thể giữ hai thông điệp khác nhau: request và response. Một `SoapMessage` chỉ biểu diễn **một** trong các thông điệp đó.

~~~mermaid
flowchart LR
    MC["MessageContext"]
    MC --> REQ["request: WebServiceMessage"]
    MC --> RES["response: WebServiceMessage"]
    REQ --> SREQ["SoapMessage / Envelope request"]
    RES --> SRES["SoapMessage / Envelope response"]
~~~

Không nên gọi `getResponse()` chỉ để hỏi xem response có tồn tại hay không; trong những implementation/context, thao tác đó có thể khiến response được tạo theo nhu cầu. Hãy dùng `hasResponse()` để kiểm tra trạng thái mà không gây tác dụng phụ.

### 9.1. Một request không nhất thiết luôn có response nghiệp vụ

Một số operation có thể mang tính một chiều hoặc có lỗi trước khi endpoint phản hồi. Tùy cơ chế giao tiếp, HTTP binding và dispatcher, response có thể là SOAP message, SOAP Fault hoặc không có payload nghiệp vụ. Vì vậy đừng giả định **mọi request luôn đi kèm một JAXB response object**.

## 10. Endpoint và JAXB chỉ làm việc với một phần của mô hình

Với hợp đồng:

~~~xml
<xs:element name="GetOrderRequest">
    <xs:complexType>
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>
</xs:element>
~~~

Giả sử schema có `targetNamespace="urn:example:orders:v1"` và `elementFormDefault="qualified"`. Một endpoint Spring-WS có thể chọn request bằng QName phần tử gốc:

~~~java
import javax.xml.transform.Source;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.xml.transform.StringSource;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public Source getOrder(@RequestPayload Source request) {
        // Ví dụ tối thiểu về một endpoint nhận và trả payload.
        // Ứng dụng thật cần parse/validate request và xử lý nghiệp vụ.
        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>FOUND</o:status>" +
                "</o:GetOrderResponse>");
    }
}
~~~

`@RequestPayload Source` nhận nội dung payload từ SOAP Body; `@ResponsePayload Source` cung cấp nội dung payload cho response. Ví dụ không trực tiếp tạo SOAP Envelope vì framework chịu trách nhiệm xử lý lớp vỏ đó thông qua message infrastructure.

Nếu dùng JAXB, signature có thể thay `Source` bằng class XJC đã sinh, ví dụ `GetOrderRequest` và `GetOrderResponse`. Khi đó adapter/marshaller thực hiện chuyển payload XML thành object và ngược lại, dựa trên mapping JAXB. Nhưng:

- **JAXB không tự xử lý SOAP Header** khi bạn chỉ map DTO từ Body.
- **`@PayloadRoot` ánh xạ QName của payload**, không dựa trên tên Java class.
- **`@ResponsePayload` ghi nội dung trả về vào Body**, không biến một exception thành typed SOAP Fault tự động.
- **XSD validation** cần được cấu hình riêng nếu muốn kiểm tra đầy đủ kiểu, thứ tự phần tử, minOccurs/maxOccurs và facet.

Ví dụ endpoint trên nhằm minh họa mô hình, chưa có đầy đủ response XSD/WSDL, logic nghiệp vụ và security. Trong ứng dụng contract-first hoàn chỉnh, thêm `GetOrderResponse` và fault types vào XSD/WSDL được công bố trước khi chốt integration.

## 11. Interceptor thao tác với thông điệp khi nào?

Spring-WS có `EndpointInterceptor`, cho phép đặt logic vào chuỗi xử lý request/response/Fault của endpoint. Đây là vị trí quan trọng cho validation, WS-Security, audit và correlation ID.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["SOAP request trong MessageContext"] --> B["EndpointMapping"]
    B --> C["Interceptor: handleRequest"]
    C --> D{"Cho phép tiếp tục?"}
    D -- "Không" --> F["Có thể tạo response/Fault hoặc dừng xử lý"]
    D -- "Có" --> E["@Endpoint / EndpointAdapter"]
    E --> G{"Xử lý thành công?"}
    G -- "Có" --> H["Interceptor: handleResponse"]
    G -- "Lỗi được chuyển thành Fault" --> I["Interceptor: handleFault"]
    H --> J["Hoàn tất / serialize"]
    I --> J
    F --> J
~~~

Đây là sơ đồ giản lược; `afterCompletion` và luồng ngoại lệ phụ thuộc kết quả xử lý thực tế. `handleRequest` trả `false` để ngăn gọi endpoint; việc message phản hồi/Fault được tạo thế nào phụ thuộc interceptor và dispatcher.

Một interceptor minh họa chỉ đọc metadata:

~~~java
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.SoapMessage;

public class SoapMetadataInterceptor implements EndpointInterceptor {

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint) {
        WebServiceMessage request = context.getRequest();

        if (request instanceof SoapMessage) {
            SoapMessage soap = (SoapMessage) request;
            String action = soap.getSoapAction();
            // Ghi action/trace metadata nếu được phép.
            // Tránh ghi nguyên SOAP Header có thông tin nhạy cảm.
        }
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        // Giải phóng tài nguyên hoặc ghi nhận kết quả xử lý.
    }
}
~~~

Để sử dụng interceptor này, ứng dụng phải **đăng ký nó trong Spring-WS interceptor chain** qua cấu hình tương ứng; chỉ tạo class chưa đủ. Một interceptor tự viết nên thao tác với `WebServiceMessage` và `SoapMessage` theo đúng trách nhiệm, đồng thời tránh thay đổi SOAP signature, payload hoặc header đã xác thực.

### 11.1. Validation và security không thay thế nhau

| Thành phần | Kiểm tra điều gì |
| --- | --- |
| XSD validation (ví dụ `PayloadValidatingInterceptor`) | Payload có đúng cấu trúc XML/schema và facet hay không |
| SOAP Header processing | Header có được diễn giải theo SOAP version/role/mustUnderstand không |
| WS-Security interceptor | Token, chữ ký, timestamp, mã hóa và policy bảo mật đã cấu hình |
| HTTP/TLS layer | Kết nối, chứng chỉ, xác thực/ủy quyền ở tầng HTTP/TLS khi được cấu hình |
| Business service | Mã đơn hàng có tồn tại, quyền thao tác, quy tắc nghiệp vụ |

Một request có thể **valid theo XSD** nhưng bị từ chối vì chữ ký sai. Ngược lại, một request có chữ ký hợp lệ vẫn có thể chứa `orderId` sai kiểu dữ liệu. Các lớp kiểm tra phục vụ mục đích khác nhau.

## 12. `WebServiceTemplate` nhìn mô hình thông điệp từ phía client

Phía SOAP client, Spring-WS dùng `WebServiceTemplate` để chuẩn bị request, gọi transport và xử lý response:

~~~mermaid
flowchart LR
    A["Java request object"] --> B["JAXB marshaller"]
    B --> C["WebServiceMessage / SoapMessage request"]
    C --> D["WebServiceConnection: HTTP(S)"]
    D --> E["SOAP server"]
    E --> F["WebServiceMessage response"]
    F --> G["Fault detection hoặc unmarshal"]
    G --> H["Java response / exception"]
~~~

Ví dụ client dùng JAXB:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1001");

GetOrderResponse response = (GetOrderResponse)
        webServiceTemplate.marshalSendAndReceive(
                "https://api.example.test/ws/orders",
                request,
                new SoapActionCallback("urn:example:orders:GetOrder"));
~~~

`GetOrderRequest`, `GetOrderResponse` và biến `webServiceTemplate` là các thành phần của ứng dụng; cấu hình marshaller/unmarshaller và WSDL binding phải phù hợp. `SoapActionCallback` thao tác trên thông điệp SOAP trước khi gửi để đặt action; object JAXB chỉ biểu diễn payload nghiệp vụ.

### 12.1. Callback làm việc với message, extractor đọc response

Khi cần xử lý mức thấp, client có thể dùng các abstraction:

- `WebServiceMessageCallback`: điều chỉnh thông điệp request trước khi gửi, ví dụ action hoặc SOAP Header được phép.
- `WebServiceMessageExtractor<T>`: đọc/trích xuất thông tin từ response sau khi nhận, khi luồng client cho phép.
- `WebServiceMessageFactory`: khởi tạo SOAP message đúng phiên bản, được cấu hình trong `WebServiceTemplate`.

Các callback/extractor **không thay thế** schema và chính sách bảo mật. Chẳng hạn thêm một `wsa:Action` vào SOAP Header không tự bảo đảm HTTP `SOAPAction`, WSDL operation và WS-Addressing policy đều nhất quán.

### 12.2. Fault và lỗi truyền tải nằm ở hai tầng khác nhau

| Hiện tượng | Có SOAP message để đọc? | Hướng xử lý |
| --- | --- | --- |
| SOAP response thành công | Có | Unmarshal payload, kiểm tra nghiệp vụ |
| SOAP Fault hợp lệ | Có | Đọc fault code/reason/detail theo hợp đồng |
| HTTP 500 trả HTML | Có HTTP response, nhưng không có SOAP Envelope hợp lệ | Xử lý lỗi transport/server, không parse thành SOAP Fault |
| DNS/connect timeout | Chưa có HTTP response thích hợp | Xử lý lỗi mạng, không tự gán Fault code |
| Read timeout sau khi gửi request | Không có response đầy đủ để xác minh | Không retry mù quáng với thao tác có tác dụng phụ |

Trong một SOAP client chuẩn, `WebServiceTemplate` thường phát hiện SOAP Fault và ném `SoapFaultClientException`. Để phân tích lỗi HTTP, timeout hoặc TLS, cần xử lý nhóm lỗi transport/I/O tương ứng. Không nên log hoặc catch mọi exception rồi trả về cùng một mã “SOAP Fault” vì sẽ làm mất thông tin tầng xảy ra lỗi.

## 13. Thông điệp đính kèm và MTOM: payload không phải toàn bộ dữ liệu

Một bản tin SOAP có thể kèm tệp hoặc dữ liệu nhị phân qua MIME attachment hay cơ chế MTOM/XOP tùy hợp đồng và message implementation. Khi đó không thể suy từ `getPayloadSource()` rằng **mọi byte của dữ liệu nhị phân đều nằm trực tiếp trong XML**.

Ví dụ về contract:

~~~xml
<xs:element name="fileContent" type="xs:base64Binary"/>
~~~

Ở dạng inline, byte có thể được biểu diễn dưới dạng Base64 bên trong SOAP Body. Với MTOM, payload có thể dùng XOP include tham chiếu đến MIME part, còn dữ liệu nhị phân được gửi trong phần đính kèm phù hợp với package. API liên quan đến attachment có thể nằm trên interface hoặc implementation bổ sung hỗ trợ MIME; **không giả định mọi `WebServiceMessage` đều có cùng các phương thức thao tác attachment**.

Với file lớn, cần tính chi phí bộ nhớ, streaming và giới hạn kích thước ở transport/server. Không dump serialized message chứa attachment ra log. Kiểm thử khả năng tương thích MTOM giữa Java và hệ thống đối tác, đặc biệt khi WSDL/XSD khai báo `xs:base64Binary` nhưng bên gửi/bên nhận sử dụng cơ chế tối ưu hóa nhị phân khác nhau.

## 14. SOAP version, namespace và quy tắc phân tích XML

Để làm việc đúng với message abstraction, cần giữ ba loại namespace riêng biệt:

| Mục đích | Ví dụ |
| --- | --- |
| SOAP Envelope 1.1 | `http://schemas.xmlsoap.org/soap/envelope/` |
| SOAP Envelope 1.2 | `http://www.w3.org/2003/05/soap-envelope` |
| XSD nghiệp vụ | `urn:example:orders:v1` |

Một đoạn `<s:Envelope xmlns:s="...">` và `<soap:Envelope xmlns:soap="...">` có thể là cùng QName nếu URI giống nhau. Nhưng `<GetOrderRequest>` không namespace **khác** `<o:GetOrderRequest xmlns:o="urn:example:orders:v1">` dù local name giống nhau.

Khi dùng `@PayloadRoot`, Spring-WS đối chiếu **namespace URI + local name** của payload root. Khi unmarshalling bằng JAXB, namespace và `elementFormDefault` trong XSD cũng quyết định XML có khớp DTO hay không.

**Không kết luận chỉ từ XML well-formed.** Parser có thể đọc được Envelope XML nhưng schema validation vẫn từ chối `orderId` sai kiểu, thiếu trường, sai thứ tự hoặc nhầm namespace. XSD validation và xử lý SOAP Fault nên được tích hợp đúng nơi trong chuỗi xử lý.

## 15. Bảo mật khi làm việc trực tiếp với message

Truy cập message mức thấp đem lại tính linh hoạt nhưng đòi hỏi kỷ luật với XML và thông tin nhạy cảm:

1. **Không tự parse XML thiếu cấu hình an toàn**: khi sử dụng SAX/DOM/TransformerFactory với nguồn không đáng tin cậy, kiểm soát external entities, external DTD/schema và quyền truy cập tài nguyên.
2. **Không coi `getPayloadSource()` là dữ liệu đã được validate**: phải áp dụng schema validation và kiểm tra nghiệp vụ khi cần.
3. **Không coi TLS là thay thế WS-Security**: TLS bảo vệ kết nối; chữ ký/message security có phạm vi và yêu cầu riêng.
4. **Không chỉnh payload/header sau khi ký** nếu thay đổi có thể khiến canonicalization/signature validation thất bại.
5. **Không log thông điệp thô mặc định** vì SOAP Header có thể chứa secret/token, Body có thể chứa PII, và attachment có thể rất lớn.
6. **Hạn chế kích thước request và payload** ở lớp transport/parser; tránh dùng DOM trên dữ liệu rất lớn nếu có cơ chế streaming phù hợp.
7. **Không retry vô điều kiện khi có timeout** với operation có tác dụng phụ; trạng thái nghiệp vụ sau khi gửi request có thể chưa xác định.

Một hợp đồng doanh nghiệp tốt cần quy định rõ XSD/WSDL, SOAP version, header bảo mật, chứng chỉ/trust, lỗi SOAP Fault và khả năng kiểm thử tương thích. `WebServiceMessage` giúp truy cập dữ liệu, nhưng **không tự đưa ra chính sách tin cậy và bảo mật**.

## 16. Kiểm thử kiến trúc xử lý ở nhiều tầng

Với Spring-WS, có thể sử dụng `MockWebServiceClient` để kiểm thử endpoint và `MockWebServiceServer` để kiểm thử SOAP client. Tuy nhiên HTTP status, TLS, reverse proxy và lỗi mạng cần kiểm thử tích hợp qua transport phù hợp.

Một bộ test tối thiểu:

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| Message factory tạo SOAP 1.1 | Namespace Envelope và HTTP media type tương thích SOAP 1.1 |
| Message factory tạo SOAP 1.2 | Namespace Envelope và binding tương thích SOAP 1.2 |
| `getPayloadResult()` ghi request | XML nghiệp vụ nằm trong Body, không bị đặt thành SOAP Header |
| `writeTo(...)` serialize message | Có Envelope đúng phiên bản và payload mong đợi |
| `getPayloadSource()` đọc request | Đọc đúng root QName payload, không giả định Source chứa toàn Envelope |
| `SoapMessage.getSoapAction()` | Action đúng hợp đồng, không nhầm URL endpoint |
| SOAP Header có correlation ID | Header đúng namespace, không làm sai Body |
| Header `mustUnderstand` không được xử lý | SOAP processor xử lý lỗi theo quy tắc tương ứng |
| Request hợp XSD | Endpoint nhận đúng payload và response đúng QName |
| Request sai XSD | Validator/interceptor báo lỗi khi được cấu hình |
| SOAP Fault | Đọc được Fault code/reason/detail, không coi đó là JAXB response bình thường |
| Lỗi HTTP trả HTML | Client phân loại lỗi transport, không cố parse SOAP Fault |
| DNS/TLS/read timeout | Xử lý ở lớp transport; không tự gán SOAP fault code |
| WS-Security signature/token sai | Bị từ chối theo security policy trước khi thực hiện nghiệp vụ nhạy cảm |
| Có MIME/MTOM attachment | Bảo toàn dữ liệu nhị phân và không log dữ liệu nhạy cảm |
| Prefix XML thay đổi | Vẫn nhận diện cùng namespace URI/local name |

### 16.1. Điều gì được kiểm thử với mock và điều gì cần chạy thực?

**Mock endpoint** rất phù hợp để kiểm tra `@PayloadRoot`, interceptor chain, payload, SOAP Fault và phần lớn hành vi Spring-WS bên trong application context. **HTTP/TLS/proxy test** cần môi trường thật hoặc transport mô phỏng chuyên biệt, vì mock thường không tái hiện đủ DNS, TCP, handshake, HTTP status từ gateway hay các lỗi timing.

Đối với hợp đồng đã công bố cho đối tác, nên bổ sung kiểm thử **round-trip JAXB** và xác thực XML với XSD: Java object → SOAP payload → XSD validation → Java object. Kiểm tra thêm cả envelope version, header policy và Fault khi cần; round-trip chỉ kiểm tra DTO không đủ chứng minh toàn bộ message processing.

## 17. Bài tập tình huống

Hệ thống `OrderService` có endpoint xử lý `GetOrderRequest`, dùng `@RequestPayload GetOrderRequest` sau khi sinh JAXB. Client gửi ba request:

**A.** SOAP 1.1 Envelope có Body hợp XSD, nhưng Header chứa token WS-Security hết hạn.

**B.** SOAP 1.1 Envelope và Header hợp lệ, nhưng payload `GetOrderRequest` mang namespace `urn:example:orders:v2` trong khi `@PayloadRoot` đăng ký `urn:example:orders:v1`.

**C.** SOAP 1.1 Envelope hợp lệ và payload đúng, nhưng client nhận HTTP 502 kèm body HTML từ gateway.

Hãy giải thích:

1. Trường hợp nào có thể bị từ chối **trước khi endpoint Java chạy**?
2. Trong trường hợp B, việc đổi prefix `o` thành `x` có giải quyết lỗi không?
3. Trong trường hợp C, có nên dùng `SoapBody.getFault()` để đọc HTML không?
4. Nếu cần ghi log an toàn, những metadata nào nên được ưu tiên?

**Đáp án gợi ý:**

- **A:** interceptor WS-Security có thể từ chối thông điệp trước nghiệp vụ; Body đúng XSD không làm token đã hết hạn trở thành hợp lệ.
- **B:** QName của payload không khớp endpoint mapping; có thể không tìm thấy endpoint. Thay prefix mà **không đổi namespace URI** thì không giải quyết được.
- **C:** gateway trả lỗi HTTP/HTML; không có SOAP Envelope hợp lệ để đọc `SoapBody`/`SoapFault`. Cần phân loại transport/gateway error.
- **Log:** ghi correlation ID, operation, root QName, SOAP version, action, HTTP status, mã Fault khi có và thời gian; che thông tin bảo mật và dữ liệu cá nhân.

## 18. Tự kiểm tra nhanh

1. `WebServiceMessage` có phương thức nào dùng để đọc payload, phương thức nào dùng để ghi payload?
2. Muốn phân tích SOAP Header hoặc Fault thì nên dùng abstraction nào?
3. `MessageContext` khác `SoapMessage` ở chỗ nào?
4. Đặt `soap.setSoapAction(...)` có giống ghi `wsa:Action` trong SOAP Header không?
5. Nếu `WebServiceTemplate` nhận SOAP Fault thì có được mặc định deserialize nó như response JAXB thành công không?
6. `getPayloadSource()` có luôn chứa HTTP headers, SOAP Header và attachment không?
7. Vì sao một payload JAXB hợp lệ vẫn có thể bị từ chối bởi WS-Security interceptor?

**Đáp án:**

1. `getPayloadSource()` đọc, `getPayloadResult()` ghi; `writeTo(...)` serialize thông điệp.
2. `SoapMessage` và các phần tử `SoapHeader`/`SoapBody`/`SoapFault`.
3. `MessageContext` quản lý lần xử lý gồm request/response, còn `SoapMessage` là **một** thông điệp SOAP.
4. **Không.** Action transport/SOAP và WS-Addressing Header có thể liên hệ theo policy, nhưng là hai thành phần khác nhau.
5. **Không.** SOAP Fault cần được nhận diện và xử lý theo đường lỗi.
6. **Không.** Payload là phần nghiệp vụ; các header/attachment và transport có API/abstraction riêng.
7. Vì XSD/JAXB kiểm tra cấu trúc/chuyển đổi XML, còn WS-Security kiểm tra chính sách bảo mật thông điệp.

## 19. Ghi nhớ

- **`WebServiceMessage`** cung cấp API chung để đọc/ghi payload XML và serialize thông điệp.
- **`SoapMessage`** kế thừa `WebServiceMessage`, bổ sung SOAP Envelope, Header, Body, version, action và truy cập Fault.
- **`MessageContext`** lưu request/response trong một lần xử lý server; nó không phải SOAP Envelope và không nên bị nhầm với một message.
- **`WebServiceMessageFactory`** tạo/đọc message; `SaajSoapMessageFactory` là một implementation SOAP. Phiên bản SOAP thực tế phải khớp WSDL binding và transport.
- **`@RequestPayload`, JAXB và `@PayloadRoot`** thường làm việc với payload thuộc Body; security header và SOAP Fault nằm ở các tầng xử lý bổ sung.
- **`EndpointInterceptor`** có thể xem, kiểm tra hoặc xử lý thông điệp trước/sau endpoint; XSD validation và WS-Security bảo vệ các khía cạnh khác nhau.
- **HTTP header, SOAP Header và SOAP Body** là ba lớp thông tin khác nhau; `SOAPAction` không phải URL endpoint hoặc tên phần tử request.
- Khi xây dựng tích hợp Spring-WS contract-first, cần kiểm thử **payload QName, SOAP version, message serialization, interceptor, Fault, TLS và security policy** để dịch vụ doanh nghiệp vận hành ổn định.
