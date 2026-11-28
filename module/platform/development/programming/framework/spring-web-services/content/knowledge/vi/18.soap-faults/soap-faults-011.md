# SOAP Fault, mã HTTP và cách máy khách phân loại phản hồi

Trong một hệ thống tích hợp **Spring Web Services (Spring-WS)** theo hướng **contract-first**, máy khách gửi SOAP request không chỉ cần đọc được response JAXB. Nó phải xác định chính xác **đã nhận kết quả thành công, nhận SOAP Fault, gặp lỗi HTTP/transport, hay không biết yêu cầu đã được xử lý đến đâu**. Nhầm các trường hợp này gây hậu quả thực tế: báo thành công dù server từ chối, retry một giao dịch đã ghi nhận, hoặc hiển thị lỗi bảo mật như lỗi nghiệp vụ.

**SOAP Fault** là thông điệp lỗi ở **tầng SOAP**, nằm trong `soap:Body` với cấu trúc quy định bởi SOAP version. **HTTP status** thuộc **tầng HTTP**, báo kết quả trao đổi ở transport/binding. Hai tầng có liên quan theo HTTP binding nhưng **không đồng nghĩa**. Một HTTP `500` có thể chứa SOAP Fault chuẩn, cũng có thể chỉ là trang HTML lỗi của reverse proxy. Một HTTP `200` thường đi kèm SOAP response thành công, nhưng client vẫn cần kiểm tra nội dung SOAP đúng hợp đồng. Một timeout thậm chí **không có HTTP response**.

Bài học thuộc chương **SOAP Fault** của module `SPRING_WEB_SERVICES`. Nó kết nối thiết kế XSD/WSDL, JAXB, `@Endpoint`, `WebServiceTemplate`, exception resolver, interceptor, XML security, WS-Security, TLS/chứng chỉ và kiểm thử tương thích giữa hệ thống doanh nghiệp. Ví dụ sử dụng SOAP 1.1 trước rồi đối chiếu SOAP 1.2; các tên namespace, endpoint và thông điệp là minh họa.

## 1. Phân biệt ba tầng trước khi xử lý lỗi

Một yêu cầu SOAP qua HTTP gồm nhiều lớp:

~~~mermaid
flowchart TD
    A["SOAP client / WebServiceTemplate"] --> B["DNS, TCP, TLS, proxy"]
    B --> C["HTTP request/response: status, headers, body bytes"]
    C --> D["SOAP parser: Envelope, Header, Body"]
    D --> E["EndpointMapping, interceptor, security, validation"]
    E --> F["JAXB adapter + business service"]
    F --> G["SOAP response hoặc SOAP Fault"]
    G --> H["HTTP binding / response bytes"]
    H --> A
~~~

Khi chẩn đoán, phải trả lời theo thứ tự:

1. **Có kết nối/nhận HTTP response không?** Nếu DNS, TCP, TLS hay timeout lỗi, có thể chưa có SOAP message.
2. **HTTP status và Content-Type là gì?** Phân biệt trạng thái transport/binding, xem proxy/gateway có thay thế response không.
3. **Body có phải SOAP Envelope hợp lệ không?** Kiểm tra SOAP namespace, XML well-formed, kích thước và mã hóa.
4. **SOAP Body có Fault không?** Nếu có, đọc Fault code/reason/detail theo SOAP version.
5. **Nếu là normal SOAP Body**, payload có khớp XSD/WSDL và deserialize thành DTO không?
6. **Nếu nghiệp vụ báo trạng thái từ chối trong response hợp lệ**, đây có thể là kết quả nghiệp vụ, không phải SOAP Fault hoặc lỗi HTTP.

### 1.1. Bốn kết quả thường bị nhầm lẫn

| Kết quả thực tế | HTTP thường thấy | SOAP Body | Ý nghĩa đối với client |
| --- | --- | --- | --- |
| **SOAP success** | `200 OK` cho synchronous response | Phần tử output theo WSDL/XSD. | Tiếp tục kiểm tra dữ liệu/nghiệp vụ. |
| **SOAP Fault** | Thường `500` trong SOAP 1.1 HTTP binding; SOAP 1.2 có ánh xạ theo binding và loại Fault. | `soap:Fault` hoặc `env:Fault` theo SOAP version. | Phân loại Fault code, detail, retry policy. |
| **HTTP/transport failure** | `404`, `405`, `415`, `502`, `503`, v.v. hoặc không có response | Có thể là HTML/JSON/rỗng hoặc message SOAP. | Không suy Fault nếu chưa parse được SOAP; phân loại transport. |
| **Business rejection trong normal response** | Có thể `200 OK` | Output nghiệp vụ, ví dụ `status=REJECTED`. | Xử lý theo contract nghiệp vụ, không coi là SOAP Fault. |

**Các giá trị HTTP là hình mẫu, không phải quy tắc duy nhất của mọi endpoint.** SOAP 1.1/1.2 có HTTP binding và profile tương thích riêng; framework hoặc gateway có thể trả khác chuẩn. Client robust nên ưu tiên phát hiện response có SOAP Fault hợp lệ, đồng thời ghi nhận mismatch HTTP/SOAP để sửa interoperability.

## 2. Anatomy của SOAP 1.1 Fault

Một SOAP 1.1 Fault là **phần tử `soap:Fault` trong `soap:Body`**. Ví dụ server từ chối request có giá trị không hợp lệ:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/xml; charset=utf-8
~~~

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:err="urn:example:orders:errors:v1">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring xml:lang="vi">Yêu cầu tạo đơn không hợp lệ</faultstring>
      <detail>
        <err:OrderFault>
          <err:code>INVALID_AMOUNT</err:code>
          <err:message>Giá trị amount phải lớn hơn 0</err:message>
        </err:OrderFault>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Đây là **HTTP response và SOAP XML minh họa**, không phải log nguyên văn của một phiên bản Spring-WS. Lưu ý `faultstring` mang thông điệp đã được phép công bố, không chứa stack trace, token hay cấu trúc database nội bộ.

### 2.1. Ý nghĩa các thành phần

| Thành phần SOAP 1.1 | Vai trò | Cách client nên dùng |
| --- | --- | --- |
| `faultcode` | Mã lỗi SOAP dưới dạng QName. | Phân biệt lỗi liên quan request, server, version, header; không chỉ so chuỗi không namespace. |
| `faultstring` | Mô tả lỗi dễ đọc cho con người. | Hiển thị có kiểm soát; **không dùng làm khóa quyết định nghiệp vụ** vì có thể đổi ngôn ngữ. |
| `faultactor` | URI mô tả actor/processor phát hiện Fault (nếu có). | Hữu ích khi thông điệp qua intermediaries. |
| `detail` | Dữ liệu lỗi gắn với xử lý Body, thường theo schema riêng. | Parse **theo contract** và QName để lấy mã nghiệp vụ có cấu trúc. |
| `soap:Envelope/Body` | Vỏ SOAP hợp lệ. | Cho biết đây là SOAP Fault, không phải trang lỗi HTTP bất kỳ. |

**`faultcode` không thay thế mã lỗi nghiệp vụ**. `soap:Client` có thể có nhiều nguyên nhân (sai schema, operation không hỗ trợ, dữ liệu không được chấp nhận). Để client xử lý cụ thể, nên có mã lỗi bền vững như `INVALID_AMOUNT` trong `detail` được XSD/WSDL định nghĩa, thay vì parser so câu chữ `faultstring`.

### 2.2. Các Fault code cơ bản của SOAP 1.1

| Fault code | Ý nghĩa điển hình | Hành vi gợi ý |
| --- | --- | --- |
| `soap:Client` | Message gửi lên có vấn đề khiến bên nhận không xử lý được. | Xem lại XML/schema/request/header; không retry y nguyên một cách vô hạn. |
| `soap:Server` | Có vấn đề phía xử lý server, có thể tạm thời. | Xem detail và retry policy; không tự suy side effect chưa xảy ra. |
| `soap:VersionMismatch` | Envelope namespace không được hiểu là SOAP version phù hợp. | Sửa SOAP version, Content-Type, WSDL binding. |
| `soap:MustUnderstand` | SOAP header được đánh dấu phải hiểu nhưng bên nhận không xử lý được. | Kiểm tra QName, actor/role, `mustUnderstand` và processor. |

Một số Fault code có thể được xây dựng với subcode/nghiệp vụ theo cơ chế riêng; client chỉ được dựa vào các code có **namespace, ý nghĩa và ổn định đã được thỏa thuận**. Không tạo logic kiểu “mọi `soap:Server` đều retry 3 lần” mà bỏ qua idempotency và hậu quả giao dịch.

### 2.3. Business error không mặc định phải là SOAP Fault

Có hai hướng thiết kế hợp đồng cho tình huống “hết hàng”:

- **Normal response có trạng thái nghiệp vụ:** `CreateOrderResponse` chứa `status=REJECTED`, `reasonCode=OUT_OF_STOCK`. Vẫn là kết quả hợp lệ theo XSD nếu contract định nghĩa.
- **SOAP Fault có detail kiểu `OrderFault`:** contract định nghĩa Fault cho operation, client xử lý bằng model lỗi riêng.

Cả hai có thể hợp lý tùy semantics đã thỏa thuận. Tránh **vừa trả normal response với HTTP `500`, vừa định nghĩa một SOAP Fault khác cho cùng một trường hợp mà không có quy tắc**. Điều này khiến client/gateway không biết dùng tầng nào làm nguồn sự thật.

## 3. SOAP 1.2 Fault khác SOAP 1.1 thế nào?

SOAP 1.2 dùng Envelope namespace:

~~~text
http://www.w3.org/2003/05/soap-envelope
~~~

và Fault có cấu trúc khác:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:err="urn:example:orders:errors:v1">
  <env:Body>
    <env:Fault>
      <env:Code>
        <env:Value>env:Sender</env:Value>
        <env:Subcode>
          <env:Value>err:InvalidOrder</env:Value>
        </env:Subcode>
      </env:Code>
      <env:Reason>
        <env:Text xml:lang="vi">Đơn hàng không hợp lệ</env:Text>
      </env:Reason>
      <env:Detail>
        <err:OrderFault>
          <err:code>INVALID_AMOUNT</err:code>
        </err:OrderFault>
      </env:Detail>
    </env:Fault>
  </env:Body>
</env:Envelope>
~~~

### 3.1. Đối chiếu cấu trúc

| SOAP 1.1 | SOAP 1.2 | Ghi chú |
| --- | --- | --- |
| `faultcode` | `env:Code/env:Value` | SOAP 1.2 dùng cơ chế `Subcode` có QName cho phân loại chi tiết. |
| `faultstring` | `env:Reason/env:Text` | `Text` có `xml:lang`, có thể có nhiều bản dịch. |
| `faultactor` | `env:Node`/`env:Role` | Mô tả node/role liên quan theo mô hình SOAP 1.2. |
| `detail` | `env:Detail` | Dữ liệu lỗi có cấu trúc, nên theo contract. |
| `Client` | `Sender` | Ý nghĩa gần tương ứng, không sao chép literal name. |
| `Server` | `Receiver` | Ý nghĩa gần tương ứng, không sao chép literal name. |

SOAP 1.2 còn có các mã như `MustUnderstand`, `VersionMismatch` và `DataEncodingUnknown`. Khả năng phát/nhận các mã cụ thể phụ thuộc binding và stack. **Đừng parse SOAP 1.2 Fault bằng XPath của SOAP 1.1** hoặc nhìn một thẻ `<faultstring>` không có namespace rồi suy đó là SOAP 1.2.

### 3.2. HTTP binding SOAP 1.2 cần xem loại Fault

Ở HTTP binding của SOAP 1.2, các ánh xạ HTTP status khác SOAP 1.1: ví dụ `400 Bad Request` có thể được dùng cho `env:Sender` Fault, còn `500 Internal Server Error` cho `env:Receiver` Fault theo binding; thành công request-response có thể dùng `200 OK`. Một số trường hợp như no SOAP response có thể dùng `202 Accepted` nếu phù hợp message-exchange pattern.

**Đừng quy tắc hóa thành “mọi SOAP Fault có HTTP 500”**. Đồng thời, HTTP `400` không tự chứng minh Body là SOAP 1.2 Fault; gateway cũng có thể trả `400` với HTML/JSON. Client phải xem Content-Type và SOAP Envelope, không chỉ nhìn số HTTP.

## 4. HTTP status biểu thị điều gì trong tích hợp SOAP?

HTTP status xuất hiện ở tầng transport/binding. Nó là tín hiệu quan trọng để phân biệt lỗi routing, authentication, proxy và overload, nhưng **không thay thế SOAP Fault code hoặc dữ liệu contract**.

| HTTP status | Nguyên nhân thường gặp | Có thể có SOAP Fault? | Hướng xử lý client |
| --- | --- | --- | --- |
| `200 OK` | Request-response hoàn tất ở HTTP layer. | Thường là normal SOAP response; nếu có Fault là trường hợp cần kiểm tra interoperability. | Parse SOAP Body, xác định Fault/normal response; không mặc định business success. |
| `202 Accepted` | Request đã được chấp nhận để xử lý/không trả nội dung đồng bộ theo binding. | Không nhất thiết có SOAP response body. | Chỉ xem là hợp lệ nếu WSDL/MEP và API hỗ trợ; không tự suy nghiệp vụ đã hoàn thành. |
| `204 No Content` | Không có HTTP response body. | Không có SOAP Envelope trong body. | Chỉ chấp nhận khi hợp đồng/stack có hành vi đó; không unmarshal output bắt buộc. |
| `400 Bad Request` | HTTP request sai; với SOAP 1.2 có thể đi cùng Sender Fault. | Có thể. | Kiểm tra XML/binding/header, parse SOAP khi có Envelope hợp lệ. |
| `401 Unauthorized` | HTTP authentication thiếu/sai. | Có thể là non-SOAP response. | Xác thực/credential ở transport; không mặc định retry y nguyên. |
| `403 Forbidden` | HTTP authorization/WAF từ chối. | Có thể là non-SOAP response. | Kiểm tra policy và quyền; không retry vô hạn. |
| `404 Not Found` | URL SOAP POST sai, route/proxy không tồn tại. | Thường không. | Phân biệt URL GET WSDL và URL POST SOAP. |
| `405 Method Not Allowed` | Sai HTTP method (ví dụ GET vào SOAP POST-only endpoint). | Thường không. | Sửa HTTP method. |
| `408 Request Timeout` | Tầng HTTP/proxy timeout. | Có thể không. | Xác định trạng thái chưa biết; retry chỉ nếu an toàn. |
| `413 Content Too Large` | Request body vượt giới hạn. | Thường non-SOAP. | Giảm kích thước, MTOM/attachment nếu contract hỗ trợ. |
| `415 Unsupported Media Type` | `Content-Type` không khớp SOAP binding. | Có thể không. | So SOAP 1.1/1.2, charset và transport headers. |
| `429 Too Many Requests` | Rate limit. | Thường non-SOAP. | Backoff, `Retry-After` nếu có, và kiểm soát idempotency. |
| `500 Internal Server Error` | SOAP 1.1 Fault hoặc lỗi server/proxy không phải SOAP. | **Có hoặc không**. | Kiểm tra SOAP Envelope/Fault, không phân loại chỉ theo status. |
| `502 Bad Gateway` | Proxy/gateway nhận upstream response lỗi. | Thường không đáng tin là SOAP Fault. | Xem gateway/request ID, backoff có điều kiện. |
| `503 Service Unavailable` | Quá tải, bảo trì, upstream unavailable. | Có thể non-SOAP. | Backoff có giới hạn, tôn trọng `Retry-After` nếu phù hợp. |
| `504 Gateway Timeout` | Gateway chờ upstream quá lâu. | Thường không có SOAP result đáng tin. | Coi outcome nghiệp vụ chưa rõ; tra cứu/idempotency trước retry. |

Các status mô tả những tình huống **điển hình**, không phải bảng ánh xạ chính thức duy nhất của mọi SOAP/HTTP binding. Ví dụ reverse proxy có thể trả `200` cùng HTML trang đăng nhập khi sai cấu hình, hoặc HTTP `500` với empty body. Không được ép chúng vào `SoapFaultClientException` nếu **không có SOAP Fault hợp lệ**.

### 4.1. Mã HTTP và SOAP Fault có thể mâu thuẫn

Một số hệ thống cũ có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/xml; charset=utf-8
~~~

nhưng SOAP Body lại chứa `soap:Fault`. Đây thường là hành vi **không phù hợp với kỳ vọng SOAP 1.1 HTTP binding**. Một số SOAP client sẽ phát hiện Fault khi parse message; số khác có thể dựa vào connection-level status hoặc cấu hình riêng. Không sửa bằng cách tự coi mọi `200` đều thành công: phải ghi nhận mismatch và phối hợp sửa endpoint/binding.

Chiều ngược lại, `500` kèm **normal SOAP response** hoặc `Content-Type: text/html` cũng có thể làm `WebServiceTemplate` phân loại là lỗi kết nối trước khi unmarshalling. Việc đặt `checkConnectionForFault` hay thay đổi error handling (nếu API/version hỗ trợ) chỉ là **giải pháp tương thích có điều kiện**, không nên áp dụng đại trà để che hệ thống sai chuẩn.

## 5. Thuật toán phân loại phản hồi: từ network tới business

Một ứng dụng SOAP client nên phân loại theo **sự kiện thực sự quan sát được**, không dựa vào từ khóa trong exception message. Hãy coi đó là một pipeline gồm các cổng kiểm tra.

~~~mermaid
flowchart TD
    A["Gửi SOAP request"] --> B{"Nhận HTTP response?"}
    B -- "Không" --> C["TRANSPORT_UNCERTAIN: DNS/TLS/timeout/I-O"]
    B -- "Có" --> D{"Body có SOAP Envelope hợp lệ?"}
    D -- "Có" --> E{"SOAP Body là Fault?"}
    E -- "Có" --> F["SOAP_FAULT: code/reason/detail, SOAP version"]
    E -- "Không" --> G{"Đúng operation, WSDL/XSD và output?"}
    G -- "Có" --> H{"Business status?"}
    H -- "Accepted" --> I["SUCCESS"]
    H -- "Rejected" --> J["BUSINESS_REJECTED"]
    G -- "Không" --> K["CONTRACT_OR_DESERIALIZATION_ERROR"]
    D -- "Không" --> L{"HTTP status lỗi?"}
    L -- "Có" --> M["HTTP_TRANSPORT_ERROR"]
    L -- "Không" --> N["INVALID_OR_UNEXPECTED_RESPONSE"]
    C --> O["Retry/lookup tùy idempotency"]
    F --> O
    M --> O
~~~

Lưu ý: sơ đồ rút gọn để học cách suy luận. Với client framework, một response HTTP `500` chứa SOAP Fault có thể được đưa qua **fault detection/resolver** mà không đến callback đọc normal output; điều đó không làm thay đổi bản chất Fault. Với một operation **one-way**, không có SOAP output theo WSDL thì nhánh `BUSINESS_REJECTED` có thể không tồn tại; outcome còn phụ thuộc xác nhận bất đồng bộ.

### 5.1. Enum lỗi nội bộ nên có ngữ nghĩa tách biệt

Một cách thiết kế lớp kết quả riêng trong ứng dụng:

~~~java
public enum SoapOutcomeCategory {
    SUCCESS,
    BUSINESS_REJECTED,
    SOAP_SENDER_FAULT,
    SOAP_RECEIVER_FAULT,
    SOAP_OTHER_FAULT,
    HTTP_TRANSPORT_ERROR,
    NETWORK_OR_TLS_ERROR,
    INVALID_SOAP_RESPONSE,
    CONTRACT_UNMARSHALLING_ERROR,
    OUTCOME_UNKNOWN
}
~~~

Đây là **enum ứng dụng**, không phải class Spring-WS. Nó giúp mọi nơi trong hệ thống sử dụng chung vocabulary để ghi log/metrics, quyết định retry, hiển thị thông báo hoặc đưa vào dead-letter queue. Không nên gom `NETWORK_OR_TLS_ERROR` và `SOAP_SENDER_FAULT` vào một `RuntimeException` duy nhất rồi retry cả hai như nhau.

Một số trường hợp không thể phân biệt bằng dữ liệu nhận được; ví dụ client timeout khi server vẫn đang xử lý. Hãy giữ loại `OUTCOME_UNKNOWN` thay vì đoán `FAILED` hoặc `SUCCESS`.

### 5.2. Thứ tự các câu hỏi khi dùng gateway

1. **DNS/TLS:** có tạo được kết nối tới endpoint qua đúng hostname/certificate/trust không?
2. **HTTP layer:** request có bị reverse proxy, load balancer, API gateway hoặc WAF trả về status không?
3. **Media type:** `text/xml` (SOAP 1.1) hoặc `application/soap+xml` (SOAP 1.2) có đúng binding được thỏa thuận?
4. **SOAP layer:** có Envelope đúng namespace và Body đúng cấu trúc không?
5. **Fault:** có `Fault` trong Body và mã/detail được xác định theo SOAP version không?
6. **Business contract:** normal response có đúng element output và mã trạng thái nghiệp vụ được khai báo không?

Nếu một proxy trả trang HTML `502 Bad Gateway`, đó là lỗi gateway/transport ngay cả khi HTML có từ “fault”. Nếu server trả XML `<error>...</error>` ngoài SOAP Envelope, nó **không phải SOAP Fault chuẩn**, trừ khi hợp đồng giao tiếp thực tế không dùng SOAP trên nhánh đó.

## 6. Phía Spring-WS client: WebServiceTemplate xử lý Fault

Ứng dụng Spring-WS thường dùng `WebServiceTemplate` với `Jaxb2Marshaller` hoặc `sendSourceAndReceiveToResult`. Trong đường hoạt động thông thường, template gửi SOAP message, nhận response, kiểm tra điều kiện lỗi/Fault và sử dụng **fault resolver**. Khi có SOAP Fault, mặc định thường ném `SoapFaultClientException`; các lỗi HTTP/transport hoặc marshalling có exception khác.

### 6.1. Cấu hình client contract-first

Giả định đã generate JAXB classes từ `orders.xsd` trong package `com.example.orders.contract` và có service endpoint SOAP 1.1 ở URL minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class OrdersClientConfig {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.contract");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate ordersTemplate(
            Jaxb2Marshaller ordersMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri("https://orders.example.test/ws");
        template.setMarshaller(ordersMarshaller);
        template.setUnmarshaller(ordersMarshaller);
        return template;
    }
}
~~~

**Phạm vi:** URL `orders.example.test` không phải endpoint chạy thật, package phải có JAXB metadata phù hợp và Spring-WS runtime phải có SOAP message factory/HTTP sender được cấu hình tương thích. Code này chỉ minh họa các bean; production còn cần TLS trust, timeout, WS-Security, connection pool, retry policy và monitoring.

### 6.2. Catch SOAP Fault trước lỗi transport khác

Một SOAP client wrapper có thể làm rõ các nhóm exception:

~~~java
import org.springframework.ws.client.WebServiceClientException;
import org.springframework.ws.client.WebServiceTransportException;
import org.springframework.ws.client.WebServiceIOException;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.ws.soap.client.core.SoapActionCallback;

public final class OrdersSoapGateway {

    private final WebServiceTemplate template;

    public OrdersSoapGateway(WebServiceTemplate template) {
        this.template = template;
    }

    public CreateOrderResponse createOrder(
            CreateOrderRequest request) {

        try {
            Object value = template.marshalSendAndReceive(
                request,
                new SoapActionCallback(
                    "urn:example:orders:v1/CreateOrder"));

            if (!(value instanceof CreateOrderResponse response)) {
                throw new UnexpectedSoapResponseException(
                    "Unexpected JAXB response type");
            }
            return response;

        } catch (SoapFaultClientException fault) {
            // SOAP Fault da duoc framework phat hien.
            // Chuyen sang loi domain/contract da duoc phep.
            throw translateSoapFault(fault);

        } catch (WebServiceTransportException transport) {
            // HTTP transport error: khong duoc mac dinh la SOAP Fault.
            throw new DownstreamTransportException(transport);

        } catch (WebServiceIOException network) {
            // I/O, connect timeout, TLS/connectivity (tuy root cause).
            throw new DownstreamConnectivityException(network);

        } catch (WebServiceClientException other) {
            // Co the la loi client SOAP khac: resolver/adapter,
            // message creation, giao tiep... Can phan loai root cause.
            throw new DownstreamSoapClientException(other);
        }
    }

    private RuntimeException translateSoapFault(
            SoapFaultClientException fault) {
        // Ham minh hoa; production parse code/detail an toan.
        return new RemoteSoapFaultException(fault);
    }
}
~~~

Các lớp `UnexpectedSoapResponseException`, `DownstreamTransportException`, `DownstreamConnectivityException`, `DownstreamSoapClientException` và `RemoteSoapFaultException` là **exception ứng dụng phải tự định nghĩa**, không thuộc Spring-WS. `CreateOrderRequest`/`CreateOrderResponse` được giả định có `@XmlRootElement`; nếu schema generate `JAXBElement`, cách marshal/nhận response phải điều chỉnh theo JAXB mapping thực tế.

Việc phân nhánh bằng type giúp tránh trộn SOAP Fault với HTTP transport error, nhưng **các API exception và vị trí catch cụ thể phải xác nhận theo Spring-WS version**. Một số lỗi serializer/unmarshaller có thể được bọc trong exception khác với ví dụ. Ở nơi dịch exception, cần đọc root cause an toàn, không chỉ dùng câu chữ exception và không làm lộ nội dung nhạy cảm.

### 6.3. Đọc Fault code, reason và detail an toàn

`SoapFaultClientException` cung cấp cách lấy thông tin Fault ở mức Spring-WS. Một pattern để đọc dữ liệu phân loại:

~~~java
catch (SoapFaultClientException fault) {
    QName code = fault.getFaultCode();
    String reason = fault.getFaultStringOrReason();

    // reason chỉ là text cho người đọc:
    // KHONG so chuoi theo ngon ngu de quyet dinh retry.
    logger.warn(
        "Downstream SOAP fault code={} reasonPresent={}",
        code,
        reason != null && !reason.isBlank());

    throw translateSoapFault(fault);
}
~~~

`QName` là `javax.xml.namespace.QName` (Java SE); không tự thay package này bằng `jakarta.xml.namespace.QName`. Các API trên phản ánh **SOAP Fault code và reason**, nhưng để phân biệt nghiệp vụ chi tiết, cần đọc `Fault Detail` theo **QName và schema**. Tránh ném toàn bộ `SoapFaultClientException#toString()` vào log nếu message có thể chứa dữ liệu chưa được redact.

Nếu SOAP Fault có `detail` được định nghĩa bằng XSD, nên tạo một parser/mapping chuyên trách cho các phần tử lỗi được phép, đặt giới hạn kích thước và namespace-aware validation. Không viết logic so thông điệp kiểu:

~~~java
// Tranh: chuoi faultstring co the duoc dich hoac thay doi.
if (fault.getFaultStringOrReason().contains("timeout")) {
    retry();
}
~~~

**Lý do:** câu mô tả không phải API contract ổn định; có thể đổi localization, chứa text do server/proxy điều khiển, hoặc khác nhau giữa Java/.NET/legacy SOAP stacks.

### 6.4. Fault resolver và connection-level checks

`WebServiceTemplate` có `FaultMessageResolver`; cấu hình mặc định thường biến SOAP Fault thành `SoapFaultClientException`. Có thể thay bằng resolver ứng dụng để chuẩn hóa outcome:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapFaultMessageResolver;

// template la bean da duoc inject/cau hinh truoc.
// Mac dinh thuong da xu ly SOAP Fault qua resolver nay.
void configureFaultResolver(WebServiceTemplate template) {
    template.setFaultMessageResolver(
        new SoapFaultMessageResolver());
}
~~~

Đoạn code cố ý là **minh họa setter**, không phải cấu hình cần thêm mặc định. Không tạo template `null` trong ứng dụng thật; lấy bean qua dependency injection. Khi viết custom resolver, phải quyết định xử lý SOAP 1.1/1.2, Fault detail, lỗi parse, logging, correlation và tương thích WSDL. Không biến mọi Fault thành `null` hoặc bỏ qua Fault rồi cố unmarshal như response thành công.

Ở một số phiên bản, template có các lựa chọn liên quan kiểm tra lỗi kết nối và Fault (ví dụ `setCheckConnectionForError`, `setCheckConnectionForFault`). Chúng hữu ích trong tích hợp legacy có HTTP/SOAP status không chuẩn, nhưng **không phải công tắc “sửa hết mọi lỗi 500”**. Chỉ thay đổi khi đã ghi nhận hành vi đối tác, kiểm thử thành công/Fault thật và không làm mất khả năng phát hiện HTML error hoặc non-SOAP response.

## 7. WSDL/XSD: Fault detail là một phần của hợp đồng

Một thiết kế **contract-first** nên chỉ ra máy khách nhận dữ liệu lỗi nào, không chỉ ghi “nếu lỗi, server trả 500”. Ví dụ `orders-faults.xsd` có một global element:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:orders:errors:v1"
    xmlns:err="urn:example:orders:errors:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="OrderErrorCode">
    <xs:restriction base="xs:string">
      <xs:enumeration value="INVALID_AMOUNT"/>
      <xs:enumeration value="ORDER_NOT_FOUND"/>
      <xs:enumeration value="ORDER_CONFLICT"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="OrderFault">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="code"
                    type="err:OrderErrorCode"/>
        <xs:element name="message"
                    type="xs:string"
                    minOccurs="0"/>
        <xs:element name="correlationId"
                    type="xs:string"
                    minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Một WSDL 1.1 document/literal có thể khai báo message và operation Fault:

~~~xml
<!-- Trich doan WSDL, khong phai WSDL doc lap. -->
<wsdl:message name="OrderFaultMessage">
  <wsdl:part name="fault"
             element="err:OrderFault"/>
</wsdl:message>

<wsdl:portType name="OrdersPortType">
  <wsdl:operation name="CreateOrder">
    <wsdl:input message="tns:CreateOrderRequestMessage"/>
    <wsdl:output message="tns:CreateOrderResponseMessage"/>
    <wsdl:fault
        name="OrderFault"
        message="tns:OrderFaultMessage"/>
  </wsdl:operation>
</wsdl:portType>

<!-- Phần binding cũng cần khai báo wsdl:fault/soap:fault
     tương ứng, cùng service/port và mọi namespace liên quan. -->
~~~

Đoạn WSDL chưa gồm `definitions`, `types`/XSD imports, SOAP binding đầy đủ và `service`. Khi dùng client JAX-WS generated từ WSDL, lỗi có khai báo `wsdl:fault` có thể được ánh xạ thành **checked exception** cụ thể; với Spring-WS `WebServiceTemplate`, việc ánh xạ mặc định không nhất thiết tự biến detail thành cùng exception class. Cần thực hiện mapping ở lớp client theo contract.

### 7.1. Cần giữ ổn định những gì?

- **Fault QName và cấu trúc `detail`**: client parse theo namespace và XSD, không so prefix `err` literal.
- **Error code**: ổn định theo enum/documented values; thêm code mới cần chiến lược tương thích.
- **Thông điệp mô tả**: có thể dịch/đổi, không phải key logic.
- **`correlationId`**: hỗ trợ điều tra nhưng không phải proof of authentication và không dùng làm idempotency key.
- **Phân biệt business rejection và SOAP Fault**: WSDL/XSD và tài liệu API phải chọn cách nhất quán.
- **Versioning**: nếu thay đổi `detail` breaking change, cần phối hợp với mọi client Java, .NET và gateway.

### 7.2. Tránh lộ nội bộ trong Fault detail

Không đặt SQL statement, stack trace, hostname nội bộ, file path, token, private key hoặc dữ liệu cá nhân không được phép vào `faultstring`/`Reason`/`detail`. Client nên nhận **mã lỗi an toàn để hành động** và một correlation ID để đội vận hành tra log được phân quyền.

Nếu server gặp lỗi chưa được phân loại, trả Fault tổng quát phù hợp binding và ghi chi tiết trong log nội bộ có quyền truy cập; đừng tự động serialize mọi `Throwable#getMessage()` sang response công khai.

## 8. Phía Spring-WS server: exception được ánh xạ thành Fault ra sao?

Ở server Spring-WS, một `@Endpoint` xử lý SOAP Body qua endpoint mapping và adapter. Nếu method hoặc interceptor ném exception, **exception resolver** có thể chuyển lỗi đó thành SOAP Fault. Không phải cứ ném `RuntimeException` là bạn được bảo đảm đúng `faultcode`, `faultstring` và `detail` theo WSDL.

### 8.1. Tách validation error và lỗi hạ tầng

Một service tạo đơn có thể ném exception theo tầng:

~~~java
@Endpoint
public class OrdersEndpoint {

    private static final String NS = "urn:example:orders:v1";
    private final OrderApplicationService orderService;

    public OrdersEndpoint(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderResponse create(
            @RequestPayload CreateOrderRequest request) {

        if (request.getAmount().signum() <= 0) {
            throw new InvalidOrderException("INVALID_AMOUNT");
        }

        return orderService.createOrder(request);
    }
}
~~~

**Phạm vi ví dụ:** import Spring-WS annotations và JAXB request/response đã được bỏ qua để tập trung vào luồng; `OrderApplicationService` và `InvalidOrderException` do ứng dụng định nghĩa; `request.getAmount()` cần null validation trước khi dùng; XSD và handler adapter thực tế phải tương thích. Không dùng validation thủ công duy nhất ở đây để thay thế XSD validation, `PayloadValidatingInterceptor` hoặc các kiểm tra nghiệp vụ sâu hơn.

Một cách phân nhóm:

| Loại exception | Tầng nguồn | Fault hợp đồng thường phù hợp | Điều cần tránh |
| --- | --- | --- | --- |
| Request sai QName/type/XSD facet | SOAP parser/validator/adapter. | Fault mô tả request không hợp lệ; SOAP version quyết định mã/struktur. | Trả toàn bộ XML lỗi, stack trace hoặc validator internals. |
| Dữ liệu nghiệp vụ không hợp lệ | Business service. | `Client/Sender` hoặc normal rejection theo WSDL. | Tự động coi mọi lỗi nghiệp vụ là `Server/Receiver`. |
| Đơn hàng không tồn tại | Business service. | Fault detail `ORDER_NOT_FOUND` nếu contract định nghĩa. | Dùng HTTP `404` như REST mặc dù SOAP binding không khai báo cách đó. |
| Hạ tầng DB unavailable | Server/infrastructure. | `Server/Receiver` hoặc lỗi nội bộ tương ứng. | Tiết lộ JDBC/SQL/hostname. |
| WS-Security signature invalid | Security interceptor. | Fault theo WS-Security/SOAP policy hoặc HTTP authentication failure ở tầng transport. | Bỏ kiểm tra chữ ký chỉ để endpoint được gọi. |
| SOAP Header `mustUnderstand` chưa xử lý | SOAP processor. | `MustUnderstand` Fault. | Thay bằng business rejection hoặc giả vờ Header đã xử lý. |

### 8.2. Annotation `@SoapFault` trên exception

Spring-WS có annotation để gắn metadata Fault lên exception trong những phiên bản hỗ trợ:

~~~java
import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;

@SoapFault(
    faultCode = FaultCode.CLIENT,
    faultStringOrReason = "Invalid order request"
)
public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String errorCode) {
        super(errorCode);
    }
}
~~~

Để annotation được áp dụng, cần **đăng ký `SoapFaultAnnotationExceptionResolver`** trong cấu hình tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.ws.soap.server.endpoint.SoapFaultAnnotationExceptionResolver;

@Bean
public SoapFaultAnnotationExceptionResolver soapFaultResolver() {
    SoapFaultAnnotationExceptionResolver resolver =
        new SoapFaultAnnotationExceptionResolver();
    resolver.setOrder(1);
    return resolver;
}
~~~

Khi SOAP 1.2 được dùng, cách biểu diễn Fault code/reason do runtime SOAP version và resolver quyết định; không lấy chữ `CLIENT` trong Java annotation làm literal XML `env:Client` của SOAP 1.2. **Hãy kiểm thử trên binding thật**, đặc biệt với client nhiều ngôn ngữ và WSDL đã công bố.

Annotation minh họa chỉ đủ tạo Fault **cơ bản**. Nếu WSDL yêu cầu `detail` kiểu `err:OrderFault`, phải có cơ chế xây `SoapFaultDetail` phù hợp: custom exception resolver hoặc logic SOAP Fault được Spring-WS hỗ trợ, không mặc định annotation tự marshal mọi field từ exception thành `detail`.

### 8.3. `SoapFaultMappingExceptionResolver`

Khi không muốn đặt annotation trực tiếp trên mọi exception hoặc cần ánh xạ theo class, có thể dùng `SoapFaultMappingExceptionResolver` với `SoapFaultDefinition`:

~~~java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.ws.soap.SoapFaultDefinition;
import org.springframework.ws.soap.server.endpoint.SoapFaultMappingExceptionResolver;

@Bean
public SoapFaultMappingExceptionResolver mappingFaultResolver() {
    SoapFaultMappingExceptionResolver resolver =
        new SoapFaultMappingExceptionResolver();

    Properties mappings = new Properties();
    mappings.setProperty(
        "com.example.orders.InvalidOrderException",
        "CLIENT,Invalid order request"
    );
    resolver.setExceptionMappings(mappings);

    SoapFaultDefinition fallback = new SoapFaultDefinition();
    fallback.setFaultCode(SoapFaultDefinition.SERVER);
    fallback.setFaultStringOrReason("Internal service error");
    resolver.setDefaultFault(fallback);

    resolver.setOrder(2);
    return resolver;
}
~~~

**Ví dụ có tính định hướng:** key exception class, định dạng mapping `CLIENT,reason`, thứ tự exception resolvers và các API phải được kiểm tra theo Spring-WS version. Đừng đăng ký song song nhiều resolver cùng ánh xạ một exception mà không xác định precedence. `SERVER` fallback có thông điệp an toàn cho client nhưng vẫn cần log nguyên nhân kỹ thuật bằng hệ thống nội bộ có kiểm soát.

### 8.4. Thêm `detail` đúng schema không giống thêm text tùy ý

Với WSDL đã định nghĩa `err:OrderFault`, server có thể tạo `SoapFaultDetail` bằng SOAP API do Spring-WS cung cấp, hoặc dùng XML/JAXB serializer phù hợp bên trong custom resolver. Một mô hình logic:

~~~text
Business exception
   → Error classification: INVALID_AMOUNT
   → SoapFaultDefinition: Client/Sender
   → Fault detail element:
       {urn:example:orders:errors:v1}OrderFault
       code = INVALID_AMOUNT
       correlationId = trusted server-side correlation ID
   → SOAP Fault serialized by message factory
~~~

Không tự trả về chuỗi `"<soap:Fault>..."` qua `@ResponsePayload`. Điều đó có thể tạo **Fault giả nằm trong normal Body** hoặc XML không hợp binding. Sử dụng SOAP Fault APIs/exception resolver để đảm bảo fault code, reason, detail và Envelope được dựng đúng SOAP version.

## 9. Interceptor có thể tạo Fault trước khi business endpoint chạy

Trong hệ thống contract-first, luồng xử lý SOAP thường gồm nhiều điểm từ chối request:

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as Servlet + SOAP parser
    participant M as EndpointMapping
    participant I as Security / Validation Interceptors
    participant E as @Endpoint
    participant R as Exception / Fault Resolver

    C->>S: HTTP + SOAP message
    S->>M: Tìm handler theo QName / SOAPAction
    M->>I: Request đã được route
    alt Security/Validation từ chối
        I->>R: Security/Schema exception
        R-->>C: SOAP Fault nếu pipeline hỗ trợ
    else Hợp lệ
        I->>E: JAXB request
        E-->>C: SOAP normal response
    end
~~~

Điểm quan trọng:

- `@Endpoint` có thể **chưa bao giờ được gọi** khi security/validation từ chối. Không tìm log method rồi kết luận request chưa đến server.
- `PayloadValidatingInterceptor` kiểm tra XSD khi được cấu hình. JAXB unmarshalling **không tự bảo đảm mọi XSD facet** như `pattern`/`enumeration`.
- `Wss4jSecurityInterceptor` có thể xử lý WS-Security Header/chữ ký/chứng chỉ theo policy. Một request đúng schema vẫn bị từ chối nếu thiếu UsernameToken hoặc chữ ký sai.
- `SoapEnvelopeLoggingInterceptor` và `MessageTracing` có thể giúp debug, nhưng ghi raw Envelope có rủi ro lộ token/PII và có thể làm tăng bộ nhớ hoặc ảnh hưởng streaming.
- `EndpointMapping` không tìm được handler có thể tạo lỗi không đi qua cùng interceptor chain với lỗi trong method.

**Thứ tự mapping, interceptor, exception resolver và fault delivery phụ thuộc cấu hình Spring-WS**; sơ đồ mô tả các trường hợp logic, không cam kết mọi exception ở mọi tầng đều được tự động chuyển thành SOAP Fault. Lỗi xảy ra trước SOAP message factory (ví dụ TLS handshake thất bại) không thể biến thành Fault bởi endpoint resolver.

### 9.1. SOAP Header và `MustUnderstand`

SOAP 1.1/1.2 có cơ chế yêu cầu recipient xử lý một header đánh dấu mustUnderstand. Nếu SOAP Header thuộc namespace WS-Addressing/WS-Security hoặc custom context header không được processor nhận diện theo role/actor, server có thể trả `MustUnderstand` Fault.

Đây là **lỗi ở tầng SOAP Header processing**, không phải lỗi validation của element trong SOAP Body. Client nên kiểm tra WSDL/policy, SOAP version, role/actor, QName và interceptor được đăng ký. Không chữa bằng cách xóa mọi header bảo mật hoặc tắt mustUnderstand trong môi trường cần tuân thủ policy.

### 9.2. TLS và WS-Security khác nhau

- **TLS/mTLS:** thuộc lớp kết nối. Lỗi truststore, certificate expiry, hostname verification có thể phát sinh **trước khi có HTTP response**, do đó thường là network/TLS error chứ không phải SOAP Fault.
- **WS-Security:** thuộc SOAP Header/message policy. Khi request đã được parse và security interceptor phát hiện token/chữ ký sai, server có thể tạo **SOAP security Fault** theo stack.
- **HTTP authentication:** có thể trả `401/403` ở servlet/proxy, đôi khi không có SOAP Envelope.

Một SOAP Fault `wsse:FailedAuthentication` hoặc fault code bảo mật tương ứng không đồng nghĩa mọi kết nối TLS phải thất bại. Client và monitoring cần phân biệt **phản hồi SOAP từ ứng dụng** với **lỗi xác thực ở transport**.

## 10. Quy tắc retry phải xét cả Fault, HTTP và side effect

Không thể xây retry policy chỉ từ mã HTTP. Điều quan trọng là **tác vụ có idempotent không, server có thể đã commit chưa và client có cách tra cứu trạng thái hay không**.

### 10.1. Vì sao timeout không phải chắc chắn thất bại?

~~~mermaid
sequenceDiagram
    participant C as SOAP Client
    participant S as Orders SOAP
    participant DB as Database

    C->>S: CreateOrder(key=op-42)
    S->>DB: Commit order ORD-000184
    DB-->>S: Success
    Note over C,S: Kết nối đứt / client timeout
    C->>S: Retry cùng tác vụ, key=op-42
    S->>DB: Kiểm tra idempotency key
    DB-->>S: Đơn đã tồn tại
    S-->>C: Trả kết quả đã lưu
~~~

Nếu client tự suy timeout là “server chưa làm gì”, retry có thể tạo hai đơn hoặc trừ tiền hai lần. Cần **idempotency key** ổn định cho cùng ý định, được server lưu/kiểm soát giao dịch atomically, hoặc **query trạng thái** trước retry. Correlation ID chỉ để truy vết, **không phải idempotency key**.

### 10.2. Ma trận retry sơ bộ

| Tình huống | Retry tự động? | Điều kiện an toàn |
| --- | --- | --- |
| `soap:Client` / `env:Sender` do input/schema sai | **Không** retry y nguyên. | Sửa payload/header/contract trước. |
| WS-Security `FailedAuthentication`/chữ ký sai | **Không** retry y nguyên. | Sửa credentials/certificate, policy; không thử mù quáng. |
| `soap:Server` / `env:Receiver` | **Có điều kiện**. | Xem fault detail và idempotency/khả năng side effect đã xảy ra. |
| HTTP `429` hoặc `503` | Có thể theo backoff. | Tôn trọng `Retry-After` nếu hợp lệ, giới hạn attempts và idempotency. |
| HTTP `502/504` | Có điều kiện. | Phân biệt proxy lỗi và trạng thái upstream chưa biết; tra cứu/idempotency. |
| HTTP `404/405/415` | Thường **không**. | Sửa URL/method/Content-Type trước. |
| Connect refused trước khi gửi bytes | Có thể thử lại khi endpoint tạm unavailable. | Xem thực tế network stack và chỉ làm với retry policy kiểm soát. |
| Timeout sau khi gửi request | **Không mặc định an toàn**. | Outcome unknown; cần query, idempotency hoặc bù trừ nghiệp vụ. |
| Business rejection `OUT_OF_STOCK` | Thường không retry ngay. | Theo workflow đặt hàng và lịch cập nhật tồn kho. |
| SOAP response hợp lệ có `status=REJECTED` | Không phải transport retry. | Xử lý theo logic nghiệp vụ/XSD. |

Không suy ra `soap:Server` luôn chỉ là lỗi tạm thời. Lỗi server có thể do bug cố định, cấu hình sai hoặc giao dịch đã commit một phần. Khi có retry, dùng exponential backoff, jitter, giới hạn thời gian/số lần, circuit breaker và observability; tránh retry storm khi downstream đang quá tải.

### 10.3. Các ID cần giữ hay đổi giữa lần thử

| ID | Khi retry cùng tác vụ |
| --- | --- |
| `correlationId` | Thường giữ để liên kết một workflow. |
| `idempotencyKey` | **Giữ** cho cùng ý định nghiệp vụ. |
| `requestId`/attempt ID | **Tạo mới** để phân biệt lần thử. |
| WS-Addressing `MessageID` | Theo mô hình retransmission/contract; cần thống nhất giữa hai phía. |
| Trace/span IDs | Theo propagation và tracing semantics; không giả định mọi lần thử có cùng span. |

Nếu client dùng `WebServiceTemplate`, hãy triển khai retry ở lớp wrapper/application phù hợp thay vì bọc mọi `marshalSendAndReceive` trong vòng lặp `catch(Exception) { retry(); }`.

## 11. Cách thiết kế loại lỗi ổn định cho người dùng và vận hành

Một dự án doanh nghiệp nên thống nhất “error contract” tách **mã lỗi máy đọc** khỏi **thông điệp hiển thị**. Ví dụ:

~~~json
{
  "category": "SOAP_SENDER_FAULT",
  "code": "INVALID_AMOUNT",
  "retryable": false,
  "correlationId": "corr-27a",
  "message": "Yêu cầu tạo đơn không hợp lệ"
}
~~~

Đây là **định dạng kết quả nội bộ minh họa** dùng trong wrapper client/monitoring, **không phải cấu trúc SOAP Fault chuẩn** hay JSON mà Spring-WS tự trả. Với SOAP on-the-wire, Fault vẫn phải tuân SOAP 1.1/1.2; với Fault detail, lấy trường theo XSD/WSDL.

Nguyên tắc:

1. Phân loại tầng lỗi (SOAP, HTTP, network, security, contract, business).
2. Dùng mã ổn định theo QName/XSD hoặc enum đã ký duyệt, không so `faultstring` localized.
3. Chỉ trả dữ liệu an toàn cho người dùng; chi tiết kỹ thuật trong log có quyền phù hợp.
4. Ghi `correlationId`/`requestId` để tra cứu theo chuỗi dịch vụ.
5. Không đưa raw SOAP Envelope, WS-Security token, credentials hoặc nội dung cá nhân vào metric labels/logs.
6. Bảo đảm loại lỗi mới không làm client cũ crash; có nhóm `UNKNOWN_REMOTE_FAULT` hoặc `UNCLASSIFIED`.

### 11.1. Phân loại security Fault mà không lộ bí mật

Nên log sự kiện kiểu `WS_SECURITY_SIGNATURE_INVALID`, `TOKEN_EXPIRED`, `TLS_CERTIFICATE_REJECTED` hoặc `HTTP_AUTH_FORBIDDEN` theo nguồn lỗi thực tế. Tránh log raw token, private key, password, toàn bộ XML signature reference nếu không cần.

Có thể log certificate fingerprint đã được phép hoặc tên trust policy nội bộ, nhưng không dùng fingerprint làm proof of authorization trong log và phải kiểm soát privacy. **Phân loại không được làm suy yếu quy trình WS-Security validation**.

### 11.2. Tách người dùng cuối và đội vận hành

Một SOAP Fault `Server/Receiver` có thể hiển thị cho người dùng là “Dịch vụ tạm thời chưa sẵn sàng, mã tham chiếu corr-27a”, trong khi log nội bộ ghi chi tiết exception kỹ thuật và HTTP status. Không đẩy raw `faultstring` do upstream tạo thẳng tới giao diện công khai nếu có khả năng chứa nội dung không an toàn hoặc không ổn định.

Với business rejection có schema rõ, client có thể hiển thị mã/giải thích nghiệp vụ đã được kiểm tra; ví dụ đơn hàng không đủ tồn kho là một **kết quả có thể xử lý** chứ không nhất thiết là “hệ thống bị lỗi”.

## 12. Kiểm thử phân loại phản hồi: phải kiểm tra cả HTTP và SOAP Body

Một unit test gọi thẳng method `@Endpoint` hoặc chỉ kiểm tra `CreateOrderResponse` không chứng minh client phân loại đúng **HTTP `500` có SOAP Fault**, HTTP `502` chứa HTML hay timeout không có response. Nên có test nhiều tầng.

### 12.1. Bảng ca kiểm thử bắt buộc

| Ca thử | HTTP quan sát | SOAP Body/transport | Kết quả client kỳ vọng |
| --- | --- | --- | --- |
| Thành công SOAP 1.1 | `200`, `text/xml` | `CreateOrderResponse` hợp XSD. | `SUCCESS` hoặc business result. |
| Business rejection | `200` theo contract | `CreateOrderResponse` với `REJECTED`. | `BUSINESS_REJECTED`, không tự retry transport. |
| SOAP 1.1 Client Fault | Thường `500` | `soap:Fault/faultcode=soap:Client`. | `SOAP_SENDER_FAULT`, đọc detail. |
| SOAP 1.1 Server Fault | Thường `500` | `soap:Fault/faultcode=soap:Server`. | `SOAP_RECEIVER_FAULT`, retry theo policy. |
| SOAP 1.2 Sender Fault | Theo binding, có thể `400` | `env:Fault/env:Code/env:Value=env:Sender`. | `SOAP_SENDER_FAULT`, không hiểu nhầm HTML 400. |
| SOAP 1.2 Receiver Fault | Theo binding, có thể `500` | `env:Fault/env:Code/env:Value=env:Receiver`. | `SOAP_RECEIVER_FAULT`. |
| `MustUnderstand` | Theo SOAP version/binding | SOAP Fault có mã `MustUnderstand`. | Phân loại SOAP Header processing error. |
| HTTP 404 | `404` | HTML hoặc rỗng. | `HTTP_TRANSPORT_ERROR`, sửa SOAP URL. |
| HTTP 405 | `405` | HTML hoặc rỗng. | Sai method; xem POST vs GET WSDL. |
| HTTP 415 | `415` | HTML hoặc rỗng. | Sửa `Content-Type`/SOAP version. |
| Gateway 502 | `502` | Trang HTML từ gateway. | `HTTP_TRANSPORT_ERROR`, không giả Fault. |
| Gateway timeout | `504` hoặc mất connection | Không có SOAP result đáng tin. | `OUTCOME_UNKNOWN` nếu request có side effect. |
| TLS fail | Không có HTTP response | SSL handshake exception. | `NETWORK_OR_TLS_ERROR`. |
| XML malformed | Có thể `400/500` hoặc lỗi parse local | Không dựng được Envelope hợp lệ. | `INVALID_SOAP_RESPONSE` hoặc request parse error. |
| HTTP 200 + SOAP Fault | `200` không điển hình | Body là SOAP Fault. | Phát hiện mismatch, vẫn phân loại Fault nếu runtime hỗ trợ. |
| HTTP 500 + HTML | `500` | Không phải SOAP XML. | Không cố parse thành `SoapFaultClientException`. |
| HTTP 200 + XML không đúng WSDL | `200` | Envelope đúng nhưng sai output QName/type. | `CONTRACT_UNMARSHALLING_ERROR`. |
| WS-Security signature invalid | Có thể SOAP Fault/HTTP auth error | Tùy security stack. | Phân loại theo bằng chứng của tầng lỗi. |
| Correlation header response | Theo outcome | Header có ID hợp lệ hoặc lỗi trước SOAP. | Ghép log/case; không dùng ID làm credential. |
| One-way message | Có thể `202`/không có SOAP output | Contract không yêu cầu synchronous payload. | Không cố JAXB-unmarshal `CreateOrderResponse`. |

**Không ép tất cả thành cùng một HTTP status trong mock**. Một mục tiêu của test là bắt khác biệt giữa status HTTP và SOAP content, đặc biệt qua reverse proxy. Trong production có thể chưa gặp mismatch, nhưng test giúp client không ngầm phụ thuộc sai vào một tình huống.

### 12.2. Kiểm thử SOAP Fault ở client với MockWebServiceServer

Spring-WS Test có `MockWebServiceServer` để mô phỏng SOAP server trả response hoặc SOAP Fault, từ đó xác minh lớp wrapper `WebServiceTemplate`. Ví dụ rút gọn:

~~~java
import java.util.Locale;
import org.springframework.ws.test.client.MockWebServiceServer;

import static org.springframework.ws.test.client.RequestMatchers.anything;
import static org.springframework.ws.test.client.ResponseCreators.withServerOrReceiverFault;
import static org.junit.jupiter.api.Assertions.assertThrows;

// template đã cấu hình marshaller, SOAP version và sender.
MockWebServiceServer server =
    MockWebServiceServer.createServer(template);

server.expect(anything())
      .andRespond(withServerOrReceiverFault(
          "Temporary service failure", Locale.ENGLISH));

assertThrows(
    SoapFaultClientException.class,
    () -> template.marshalSendAndReceive(validJaxbRequest)
);

server.verify();
~~~

Ví dụ giả định có JUnit 5, Spring-WS Test đúng version, `SoapFaultClientException` được import và `validJaxbRequest` là JAXB root object hợp đồng. Nếu project cài **custom FaultMessageResolver**, exception được ném ra có thể khác và test phải assert theo hành vi resolver của ứng dụng. `MockWebServiceServer` tập trung vào pipeline client; các trạng thái HTTP của gateway không nhất thiết được mô phỏng đầy đủ như real transport.

Để kiểm tra **HTTP `502` + HTML**, TLS handshake và proxy timeout, dùng embedded HTTP server, test proxy hoặc end-to-end environment được kiểm soát; không chỉ dựa vào fault-response creator.

### 12.3. Kiểm thử server với MockWebServiceClient

Ở phía Spring-WS server, `MockWebServiceClient` giúp gửi payload XML qua ApplicationContext có endpoint mapping/interceptor/exception resolver. Ví dụ:

~~~java
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.clientOrSenderFault;

// applicationContext chứa @Endpoint, validator, fault resolver.
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

String invalidXml =
    "<ord:CreateOrderRequest " +
    "xmlns:ord=\"urn:example:orders:v1\">" +
    "<ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>" +
    "<ord:amount>-1</ord:amount>" +
    "</ord:CreateOrderRequest>";

// Gia dinh resolver map loi input thanh Client/Sender Fault.
client.sendRequest(withPayload(new StringSource(invalidXml)))
      .andExpect(clientOrSenderFault());
~~~

**Ví dụ giả định resolver ánh xạ lỗi input thành Client/Sender Fault.** Không mặc định mọi lỗi validation đều có cùng Fault code: schema interceptor, endpoint adapter và exception resolver có thể quyết định đường xử lý khác nhau theo contract. Test phải xác minh cả SOAP version, `detail` và cấu hình thực tế.

`clientOrSenderFault()` là matcher minh họa cho loại Fault đó; các matcher và cách báo lỗi có thể khác theo Spring-WS version. Xác minh API, compile và behavior của dependency đang dùng trước khi chạy test.

### 12.4. Kiểm tra raw HTTP + SOAP ở môi trường test

Nếu WSDL công bố endpoint SOAP tại `http://localhost:8080/ws`, có thể lưu một Envelope thử nghiệm vào `create-order.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>-1</ord:amount>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Dùng PowerShell:

~~~powershell
curl.exe --include --request POST --header 'Content-Type: text/xml; charset=utf-8' --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' --data-binary '@create-order.xml' "http://localhost:8080/ws"
~~~

Giá trị SOAPAction và URL chỉ là **ví dụ**, phải lấy từ `wsdl:binding/soap:operation` và `soap:address` thật. Nếu client nhận `500`, hãy xem **Content-Type và Body**. Nếu Body có SOAP Fault chuẩn, phân loại theo Fault code/detail; nếu trả HTML `500` hoặc không có Body, phân loại là HTTP/transport, không phải business Fault.

Test nhiều biến thể:

- Sửa XML root namespace từ `v1` sang `v2` để kiểm tra endpoint mapping.
- Gửi SOAP 1.2 Envelope vào endpoint chỉ hỗ trợ SOAP 1.1 (hoặc ngược lại).
- Bỏ Header WS-Security khi contract yêu cầu.
- Thay endpoint URL đúng bằng đường dẫn WSDL GET `/ws/orders.wsdl` để thấy khác nhau giữa lấy hợp đồng và POST SOAP.
- Mô phỏng upstream trả HTML `502`/`504` qua proxy test, thay vì buộc SOAP server trả Fault tương ứng.
- Tắt network/timeout trong môi trường được kiểm soát để kiểm tra `OUTCOME_UNKNOWN` và idempotency.

## 13. Troubleshooting: đi từ triệu chứng đến tầng lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Client báo `SoapFaultClientException` | Server trả SOAP Fault hợp lệ. | Fault QName/code/reason/detail, SOAP version và WSDL. |
| Client báo `WebServiceTransportException` | HTTP error không được xử lý thành SOAP Fault hoặc transport layer từ chối. | Status, Content-Type, raw response an toàn, proxy logs. |
| Client báo I/O/SSL exception | DNS, connect timeout, TLS certificate/trust, socket reset. | Network, TLS, JVM truststore, timeout; có HTTP response chưa? |
| HTTP `500` nhưng không có Fault | Server/proxy lỗi, HTML/empty body hoặc mismatch binding. | Xem Content-Type/Envelope, không tự ép thành SOAP. |
| HTTP `200` nhưng vẫn bị Fault | Partner trả SOAP Fault cùng status 200 hoặc fault detection configuration. | Kiểm tra chuẩn binding, response Body và template settings. |
| HTTP `400` + SOAP 1.2 Fault | Có thể Sender Fault theo HTTP binding. | Parse SOAP 1.2 Code/Subcode/Reason/Detail. |
| HTTP `415` | Sai media type hoặc SOAP version. | `text/xml` vs `application/soap+xml`, SOAPAction/action parameter. |
| HTTP `404` | POST tới URL WSDL hoặc sai context path/reverse proxy. | Đối chiếu `soap:address`, servlet mapping, host/port/context. |
| HTTP `405` | Gửi GET/POST sai endpoint. | Kiểm tra HTTP method và WSDL retrieval. |
| `MustUnderstand` Fault | Header bắt buộc chưa được SOAP processor xử lý. | QName, actor/role, WSDL/policy, WS-Addressing/security interceptors. |
| `VersionMismatch` Fault | Client và server không cùng SOAP Envelope version. | WSDL binding, namespace, Content-Type. |
| Fault message chứa localized text | Client so `faultstring` bằng text cố định. | Dùng code/QName và detail schema, không so chuỗi. |
| Lỗi JAXB khi HTTP 200 | Response normal SOAP Body không khớp expected output QName/XSD. | Generated classes, `JAXBElement`, JAXB package, schema version. |
| Timeout rồi thấy hai đơn trùng | Retry non-idempotent request khi outcome unknown. | Idempotency key/store, correlation/attempt IDs, query trạng thái. |
| SOAP Fault không có correlation | Server chưa echo header/Fault path khác success. | Interceptor chain, Fault resolver, trust boundary. |
| Không có Envelope log dù HTTP request tới | Parser/endpoint mapping lỗi trước logging interceptor. | Gateway/servlet traces, message factory, mapping logs. |
| Log lộ credentials | Bật raw Envelope/message tracing. | Tắt debug, thực hiện xử lý sự cố dữ liệu, chỉ log metadata. |

### 13.1. Khi HTTP status và SOAP Body trái ngược

Các bước chẩn đoán nên là:

1. Bảo đảm body có phải SOAP Envelope hợp lệ, đúng version và namespace.
2. Xác định có `Fault` trong SOAP Body hay không, không chỉ nhìn `500` hoặc `200`.
3. Đối chiếu WSDL binding và behavior client/runtime.
4. Kiểm tra gateway/proxy có sửa HTTP status hay Content-Type không.
5. Nếu legacy endpoint sai chuẩn, ghi nhận ngoại lệ và xây compatibility adapter có kiểm thử, không làm mọi SOAP call bỏ qua HTTP errors.

### 13.2. Khi chỉ biết timeout

Timeout có nhiều thời điểm: trước khi gửi, đang gửi, sau khi gửi, sau khi server commit hoặc khi đọc response. Chỉ biết “client timeout” thường **không đủ để kết luận server chưa thực hiện side effect**.

Lựa chọn hợp lý: tra cứu trạng thái bằng business ID/correlation theo quyền được phép, dùng idempotency key cho retry an toàn, hoặc áp dụng bù trừ nghiệp vụ nếu thiết kế yêu cầu. Đừng biểu diễn timeout không rõ kết quả thành `BUSINESS_REJECTED` hoặc `SUCCESS`.

## 14. Những sai lầm thiết kế client cần tránh

### 14.1. Chỉ kiểm tra mã HTTP

~~~java
// Sai khi goi SOAP qua HTTP:
if (httpStatus == 200) {
    return SUCCESS;
}
if (httpStatus == 500) {
    return SERVER_FAULT;
}
~~~

Code này bỏ qua SOAP Fault hợp lệ khi trạng thái HTTP không đúng chuẩn (interoperability), và nhầm mọi HTTP `500` thành SOAP Fault. **Hãy dùng SOAP-aware client** rồi phân loại Fault/message/transport rõ ràng.

### 14.2. Biến mọi exception thành retry

~~~java
// Sai: co the retry lai thanh toan da commit.
try {
    submitPayment();
} catch (Exception exception) {
    submitPayment();
}
~~~

Cần xác định request có side effect gì, failure xảy ra ở tầng nào và idempotency có được thực thi không. Với `SoapFaultClientException` do validation hoặc security, retry y nguyên thường chỉ gây thêm tải. Với network timeout, không có đủ cơ sở để kết luận kết quả giao dịch.

### 14.3. Phụ thuộc faultstring thay vì mã lỗi có hợp đồng

Câu `"Invalid amount"` có thể được dịch thành tiếng Việt, đổi ngữ pháp hoặc được backend khác viết lại. Dùng QName của SOAP Fault và code trong `detail` theo XSD là bền vững hơn.

### 14.4. Trả HTTP 404 như REST cho lỗi nghiệp vụ SOAP

Một SOAP operation `GetOrder` báo đơn hàng không tồn tại. Nếu thiết kế contract-first yêu cầu SOAP Fault với detail `ORDER_NOT_FOUND`, server nên dùng chính **Fault contract**; đừng tùy tiện chuyển thành HTTP `404` không có SOAP Envelope chỉ vì trong REST thường dùng `404`.

Điều này **không phủ nhận HTTP 404** khi chính SOAP endpoint URL không tồn tại: lỗi routing HTTP là một chuyện khác với nghiệp vụ “order not found”.

### 14.5. Đưa `Throwable#getMessage()` vào Fault detail

Thông điệp exception có thể chứa SQL, tên bảng, đường dẫn máy chủ, tenant, token hoặc dữ liệu khách hàng. Mapping thành mã lỗi an toàn đã được công bố, log chi tiết kỹ thuật trong hệ thống được bảo vệ và dùng correlation ID để truy tìm.

## 15. Bài tập tình huống

### Tình huống A — HTTP 500 từ gateway có HTML

Client POST `CreateOrder` và nhận HTTP `500`, `Content-Type: text/html`, body là trang lỗi proxy.

**Đáp án:** phân loại thành HTTP/transport error; **không thể gọi đây là SOAP Fault** vì không có SOAP Envelope/Fault. Kiểm tra proxy/upstream, correlation/request ID ở gateway. Retry chỉ khi idempotency và trạng thái nghiệp vụ cho phép.

### Tình huống B — SOAP 1.1 Fault do amount âm

Client nhận HTTP `500` + SOAP 1.1 `soap:Fault/faultcode=soap:Client`, detail `INVALID_AMOUNT`.

**Đáp án:** đây là SOAP Sender/Client Fault liên quan request. Sửa dữ liệu đầu vào, không retry request y nguyên. Client có thể chuyển `INVALID_AMOUNT` thành lỗi validation có cấu trúc cho người dùng.

### Tình huống C — SOAP 1.2 Sender Fault với HTTP 400

Endpoint dùng SOAP 1.2, trả `env:Fault/env:Code/env:Value=env:Sender` và HTTP `400`.

**Đáp án:** parse **SOAP 1.2 Fault** theo namespace/Code/Reason/Detail, không chỉ coi là “HTTP Bad Request chung”. Kiểm tra `Subcode` và detail đã công bố để biết lỗi cụ thể.

### Tình huống D — HTTP 200, Body là Fault

Một partner legacy trả HTTP `200` kèm `soap:Fault`.

**Đáp án:** behavior có thể không đúng SOAP 1.1 HTTP binding; client nên phát hiện SOAP Fault nếu stack hỗ trợ, nhưng đồng thời ghi nhận interoperability mismatch và ưu tiên sửa phía partner/binding. Không dùng `200` làm điều kiện quyết định business success duy nhất.

### Tình huống E — Thanh toán timeout

Client không nhận response sau khi gửi `ReservePayment`. Không biết server đã ghi nhận giao dịch chưa.

**Đáp án:** `OUTCOME_UNKNOWN`. Không tự động gửi lệnh thanh toán mới với key khác. Sử dụng idempotency key của cùng ý định, tra cứu kết quả hoặc workflow bù trừ được hợp đồng cho phép.

### Tình huống F — TLS lỗi và WS-Security Fault

Trường hợp 1: Java client báo `SSLHandshakeException` trước khi có HTTP status. Trường hợp 2: client nhận SOAP Fault về UsernameToken hết hạn.

**Đáp án:** trường hợp 1 là lỗi TLS/transport, phải xem chứng chỉ và trust. Trường hợp 2 là SOAP message security Fault; cần xem WS-Security policy/clock skew/token, không xem hai lỗi là cùng một `HTTP 500`.

### Tình huống G — Normal response báo REJECTED

SOAP response thành công theo WSDL chứa `CreateOrderResponse/status=REJECTED` và `reasonCode=OUT_OF_STOCK`.

**Đáp án:** đây là **business rejection** khi contract định nghĩa như vậy. Không tự chuyển thành `SoapFaultClientException` hoặc retry request vô hạn; xử lý theo quy trình nghiệp vụ và giải thích cho người dùng.

## 16. Mô hình quyết định xử lý phản hồi trong ứng dụng

Khi thiết kế client adapter, nên biểu diễn kết quả thành một trong ba nhóm cấp cao:

~~~text
RemoteCallOutcome
  ├── Completed
  │   ├── Accepted: response theo WSDL/XSD
  │   └── Rejected: business response hợp lệ nhưng không được chấp nhận
  ├── Faulted
  │   ├── SoapFault: code/reason/detail
  │   ├── HttpTransportError: status và metadata đã lọc
  │   └── ProtocolOrContractError: XML/QName/JAXB mismatch
  └── Uncertain
      └── No authoritative response: timeout, connection lost
~~~

Đây là **mô hình ứng dụng**, không phải các class trong Spring-WS. Nó hữu ích vì “đã hoàn thành lời gọi HTTP” và “đã hoàn thành giao dịch nghiệp vụ” là hai mệnh đề khác nhau.

### 16.1. Ánh xạ kết quả tới thao tác tiếp theo

| Category | Hành động thường phù hợp | Điều không được làm |
| --- | --- | --- |
| `SUCCESS` | Ghi nhận kết quả, xử lý domain response. | Không bỏ qua kiểm tra output contract. |
| `BUSINESS_REJECTED` | Thông báo trạng thái nghiệp vụ, theo workflow. | Không retry vì tưởng mạng lỗi. |
| `SOAP_SENDER_FAULT` | Sửa input/policy, phân loại detail. | Không retry y nguyên vô hạn. |
| `SOAP_RECEIVER_FAULT` | Tra cứu trạng thái, retry có điều kiện, cảnh báo downstream. | Không mặc định “chưa commit”. |
| `HTTP_TRANSPORT_ERROR` | Phân tích status, Content-Type, proxy/gateway. | Không xây `SoapFault` giả từ trang HTML. |
| `NETWORK_OR_TLS_ERROR` | Sửa kết nối/trust/timeouts, đánh giá outcome. | Không gán cho business validation. |
| `CONTRACT_UNMARSHALLING_ERROR` | So schema, JAXB mapping, WSDL và SOAP version. | Không im lặng dùng object mặc định. |
| `OUTCOME_UNKNOWN` | Tra cứu, idempotency hoặc bù trừ theo thiết kế. | Không đánh dấu thất bại chắc chắn rồi tạo tác vụ mới. |

### 16.2. Observability nên lưu gì?

Để điều tra một SOAP call lỗi, log có thể chứa:

~~~text
timestamp=2026-11-27T02:00:00Z
service=orders-client
operation=CreateOrder
correlationId=corr-27a
requestId=req-002
soapVersion=1.1
httpStatus=500
faultCode={http://schemas.xmlsoap.org/soap/envelope/}Client
faultDetailCode=INVALID_AMOUNT
outcome=SOAP_SENDER_FAULT
retryable=false
~~~

Đây là dữ liệu giả định. Không phải mọi error có đủ mọi field. Khi TLS fail, có thể không có `httpStatus` hay `faultCode`. Khi lỗi gateway HTML, có thể có HTTP status nhưng không có SOAP Fault. Logger nên **bỏ/để null đúng sự thật** thay vì điền một Fault code do ứng dụng phỏng đoán.

Không ghi raw SOAP Envelope chứa WS-Security tokens, assertion, thông tin cá nhân hoặc nội dung giao dịch nhạy cảm. Nếu cần debug XML, dùng dữ liệu giả và cơ chế chẩn đoán có kiểm soát.

## 17. Câu hỏi ôn tập

1. Vì sao `HTTP 500` không đồng nghĩa với SOAP Fault? Hãy cho hai ví dụ có và không có Fault.
2. Trong SOAP 1.1, `faultcode`, `faultstring` và `detail` khác nhau về vai trò gì?
3. SOAP 1.2 `Code/Subcode/Reason/Detail` khác cấu trúc SOAP 1.1 thế nào?
4. Vì sao SOAP 1.2 `Sender` Fault có thể đi với HTTP `400` trong binding tương ứng?
5. Một normal SOAP response `status=REJECTED` khác SOAP Fault như thế nào?
6. Vì sao `SoapFaultClientException` không nên được xử lý như TLS timeout hoặc HTTP `502`?
7. `WebServiceTemplate` xử lý Fault qua cơ chế nào, và cần kiểm tra gì khi tích hợp endpoint sai chuẩn HTTP status?
8. Khi nào nên dùng `@SoapFault` trên exception và khi nào cần custom exception resolver để tạo `detail` đúng XSD?
9. Tại sao `PayloadValidatingInterceptor` có thể phát hiện lỗi request trước khi method `@Endpoint` chạy?
10. Vì sao SOAP Fault `MustUnderstand` liên quan SOAP Header hơn là validation của dữ liệu nghiệp vụ?
11. Khi client timeout sau khi gửi `CreateOrder`, kết quả nghiệp vụ nên được phân loại thế nào?
12. Correlation ID và idempotency key khác nhau ra sao trong thiết kế retry?
13. HTTP `404` của URL SOAP không tồn tại khác gì lỗi nghiệp vụ `ORDER_NOT_FOUND`?
14. Những trường hợp nào cần kiểm thử bằng HTTP/proxy thật thay vì chỉ dùng `MockWebServiceServer`?
15. Vì sao faultstring đa ngôn ngữ không phải khóa ổn định để quyết định retry?

## 18. Checklist trước khi triển khai máy khách SOAP

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Xác định SOAP version đúng? | SOAP 1.1/1.2, Content-Type, Envelope namespace khớp WSDL binding. |
| Phân biệt HTTP và SOAP? | Không quy mọi HTTP 500 thành Fault, mọi HTTP 200 thành business success. |
| Nhận dạng SOAP Fault đúng? | Đọc Code/Reason/Detail theo version; QName namespace-aware. |
| Phân loại lỗi ổn định? | Có nhóm Fault, transport, TLS, invalid XML, contract/JAXB, business, unknown. |
| Fault detail được công bố? | XSD/WSDL có cấu trúc/mã lỗi mà client xử lý được nếu nghiệp vụ yêu cầu. |
| Server mapping exception rõ? | `@SoapFault`/resolver cấu hình đúng, không lộ nội bộ. |
| XSD validation hoạt động? | Validator/interceptor được đăng ký và test request/response cần thiết. |
| WS-Security/TLS được xử lý đúng tầng? | Header security, certificate, trust và authorization tách biệt Fault/transport. |
| Client fault resolver đúng? | `WebServiceTemplate` không bỏ qua Fault hoặc nuốt lỗi. |
| Retry an toàn? | Có idempotency hoặc tra cứu trạng thái, backoff/limits/circuit breaker phù hợp. |
| Timeout outcome được diễn đạt đúng? | Không suy side effect chưa xảy ra chỉ vì mất response. |
| Có phân biệt success/rejected? | Normal response được kiểm tra theo XSD và business status. |
| Monitoring không lộ dữ liệu? | Log code, HTTP status, correlation/trace IDs đã lọc; không dump secrets. |
| Interoperability được test? | Java/.NET/legacy clients đọc SOAP Fault và normal response đúng WSDL. |
| Đã thử lỗi gateway? | HTTP HTML error, 502/504, TLS timeout, malformed XML đều có test riêng. |
| Đã thử SOAP 1.2 và Header Fault? | Sender/Receiver, MustUnderstand, VersionMismatch theo phạm vi hỗ trợ. |
| Có chiến lược versioning? | Error codes và detail schema tương thích hoặc có migration plan. |

### Ghi nhớ

- **SOAP Fault nằm trong SOAP Body** và có cấu trúc theo SOAP 1.1/1.2; **HTTP status thuộc transport/binding**, không thay thế Fault.
- **SOAP 1.1 HTTP binding thường dùng HTTP 500 cho SOAP Fault**, trong khi **SOAP 1.2 binding có ánh xạ đa dạng hơn** như Sender/Receiver Fault. Luôn nhìn cả HTTP status và SOAP XML thực nhận.
- **`faultstring`/`Reason` là text cho người đọc**; client nên phân loại qua Fault code/QName và `detail` theo XSD/WSDL, không phụ thuộc câu chữ.
- Trong Spring-WS, **`WebServiceTemplate`/`SoapFaultClientException`** là cơ chế xử lý SOAP Fault phía client; server dùng **`@SoapFault` hoặc exception resolver** để tạo Fault phù hợp. Lỗi HTTP/TLS, JAXB và business response phải được xử lý riêng.
- **Một timeout không khẳng định server chưa commit**. Retry phải dựa vào idempotency/tra cứu trạng thái, đặc biệt với tạo đơn và thanh toán.
- **XSD validation, WS-Security, chứng chỉ và SOAP Fault thuộc các tầng khác nhau**. Kiểm thử toàn bộ pipeline, gồm gateway/HTTP và client Java hoặc đối tác khác ngôn ngữ, để tích hợp doanh nghiệp ổn định.





