# SOAP Fault, mã trạng thái HTTP và lỗi kết nối

## 1. Bối cảnh: một lời gọi SOAP có thể thất bại ở nhiều tầng

Khi tích hợp hệ thống doanh nghiệp bằng **Spring Web Services (Spring-WS)** theo hướng **contract-first**, client gửi một SOAP Envelope qua HTTP(S) tới endpoint được định nghĩa trong WSDL. Nếu không nhận được kết quả mong đợi, cần xác định lỗi phát sinh ở tầng nào trước khi sửa mã, báo lỗi cho người dùng hay thử gửi lại yêu cầu.

Ba tình huống dễ bị nhầm lẫn:

1. **SOAP Fault:** phía nhận đã tạo một thông điệp SOAP mô tả lỗi; lỗi có `Code`/`Reason` hoặc `faultcode`/`faultstring`, có thể có thông tin chi tiết theo hợp đồng.
2. **Lỗi HTTP:** client nhận được phản hồi HTTP với mã trạng thái không mong đợi, ví dụ `401`, `404`, `415` hoặc `503`; phần thân có thể chứa SOAP Fault, HTML, JSON, văn bản thuần hoặc không có gì.
3. **Lỗi kết nối:** không có phản hồi HTTP hợp lệ để đọc, ví dụ DNS thất bại, không kết nối TCP được, bắt tay TLS thất bại hoặc hết thời gian chờ.

**Không thể chỉ nhìn một mã HTTP 500 để kết luận chắc chắn có SOAP Fault; cũng không thể thấy timeout rồi kết luận server chưa xử lý yêu cầu.**

Bài học thuộc chương **Giao thức SOAP** này giúp bạn đọc Fault theo SOAP 1.1/1.2, hiểu quan hệ với HTTP, xử lý ngoại lệ trên Spring-WS endpoint và SOAP client, rồi xây dựng quy tắc chẩn đoán, kiểm thử và retry an toàn.

## 2. Nhận diện tầng lỗi theo thứ tự xử lý

Một lời gọi SOAP qua HTTPS có thể đi qua các bước:

~~~mermaid
flowchart TD
    A[Ứng dụng SOAP client] --> B[DNS và kết nối TCP]
    B --> C[Bắt tay TLS nếu dùng HTTPS]
    C --> D[HTTP proxy / gateway / web server]
    D --> E[Đọc và kiểm tra SOAP Envelope]
    E --> F[Xác thực XML / WS-Security]
    F --> G[Spring-WS endpoint]
    G --> H[Nghiệp vụ / hệ thống phụ thuộc]
    H --> I[SOAP response hoặc SOAP Fault]
    I --> J[HTTP response về client]
~~~

Sự cố tại **DNS, TCP hoặc TLS** thường không có SOAP Envelope ở phía client vì quá trình chưa đến tầng thông điệp SOAP. Lỗi tại **gateway** có thể tạo HTTP response nhưng không có SOAP Fault. Lỗi trong **xử lý SOAP, xác thực, endpoint hoặc nghiệp vụ** có thể được biểu diễn thành SOAP Fault nếu bên nhận có khả năng tạo phản hồi SOAP hợp lệ.

| Dấu hiệu client quan sát | Kết luận có thể rút ra | Điều chưa thể khẳng định |
| --- | --- | --- |
| Nhận SOAP Envelope có phần tử `Fault` hợp lệ | Có phản hồi SOAP báo lỗi | Không chắc lỗi xuất phát từ nghiệp vụ; có thể do security hoặc hạ tầng SOAP |
| HTTP 500 và body là HTML | HTTP server/proxy báo lỗi | Không có bằng chứng đây là SOAP Fault |
| HTTP 404 | URL/route không tìm thấy tài nguyên phù hợp | Không biết endpoint SOAP có được gọi hay chưa |
| HTTP 200 và SOAP Body bình thường | Trao đổi ở tầng SOAP có vẻ thành công | Chưa chắc kết quả nghiệp vụ đúng nếu ứng dụng dùng quy ước lỗi riêng |
| Connect timeout, DNS failure, TLS handshake failure | Chưa có HTTP response hoàn chỉnh | Chưa được phép suy ra mã trạng thái hoặc SOAP Fault |
| Read timeout sau khi gửi request | Client chưa nhận phản hồi kịp thời | Server có thể đã thực hiện thao tác |

Nguyên tắc chẩn đoán: **kiểm tra có nhận HTTP response hay chưa → xác định HTTP status và Content-Type → kiểm tra body có phải SOAP Envelope hợp lệ → xác định có SOAP Fault không → đọc lỗi nghiệp vụ và dấu vết hệ thống**.

## 3. Cấu trúc SOAP Fault trong SOAP 1.1

SOAP 1.1 sử dụng namespace envelope:

`http://schemas.xmlsoap.org/soap/envelope/`

Ví dụ phản hồi lỗi cho thao tác lấy thông tin khách hàng:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/xml; charset=utf-8
~~~

~~~xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:err="urn:example:customer:fault:v1">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>Customer ID is invalid</faultstring>
            <detail>
                <err:ValidationFault>
                    <err:code>CUSTOMER_ID_INVALID</err:code>
                    <err:field>customerId</err:field>
                    <err:message>Customer ID must not be blank</err:message>
                </err:ValidationFault>
            </detail>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Trong SOAP 1.1, `Fault` nằm trực tiếp trong `soap:Body` và thường có các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `faultcode` | Mã phân loại lỗi ở cấp SOAP, ví dụ `Client` hoặc `Server` |
| `faultstring` | Mô tả dành cho người đọc; không nên parse để quyết định xử lý nghiệp vụ |
| `faultactor` | Thành phần tùy chọn mô tả tác nhân liên quan đến lỗi |
| `detail` | Phần thông tin chi tiết, thường chứa XML theo namespace và schema do dịch vụ quy định |

Các `faultcode` chuẩn quan trọng trong SOAP 1.1:

- `VersionMismatch`: phiên bản Envelope không được bên nhận hỗ trợ.
- `MustUnderstand`: có SOAP Header đánh dấu `mustUnderstand` nhưng node đích không xử lý được theo yêu cầu.
- `Client`: thông điệp phía gửi sai cú pháp hoặc không đủ thông tin để xử lý.
- `Server`: bên nhận gặp vấn đề khi xử lý thông điệp.

`Client`/`Server` nói về **nguồn gốc loại lỗi ở tầng SOAP**, không đồng nhất với số HTTP 4xx/5xx. Chẳng hạn, một SOAP 1.1 Fault mã `soap:Client` vẫn thường đi kèm **HTTP 500**, theo quy tắc SOAP 1.1 HTTP binding; không phải mặc định HTTP 400.

`detail` cho phép mô tả lỗi nghiệp vụ/validation bằng cấu trúc XML có thể công bố trong XSD/WSDL. Hệ thống tích hợp nên dựa vào **mã lỗi có cấu trúc** như `CUSTOMER_ID_INVALID` nếu hợp đồng quy định, thay vì so khớp nguyên văn `faultstring` vốn có thể thay đổi theo ngôn ngữ hoặc phiên bản.

## 4. SOAP Fault trong SOAP 1.2

SOAP 1.2 dùng namespace envelope khác:

`http://www.w3.org/2003/05/soap-envelope`

Ví dụ Fault tương đương ở SOAP 1.2:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/soap+xml; charset=utf-8
~~~

~~~xml
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"
              xmlns:err="urn:example:customer:fault:v1">
    <env:Body>
        <env:Fault>
            <env:Code>
                <env:Value>env:Sender</env:Value>
            </env:Code>
            <env:Reason>
                <env:Text xml:lang="vi">Mã khách hàng không hợp lệ</env:Text>
            </env:Reason>
            <env:Detail>
                <err:ValidationFault>
                    <err:code>CUSTOMER_ID_INVALID</err:code>
                    <err:field>customerId</err:field>
                </err:ValidationFault>
            </env:Detail>
        </env:Fault>
    </env:Body>
</env:Envelope>
~~~

Các thành phần chính:

| SOAP 1.1 | SOAP 1.2 | Ý nghĩa |
| --- | --- | --- |
| `faultcode` | `env:Code/env:Value` | Mã lỗi chính |
| Có thể dùng mã lỗi con theo quy ước | `env:Code/env:Subcode` | Mã lỗi phân cấp, có thể lồng nhau |
| `faultstring` | `env:Reason/env:Text` | Nội dung mô tả, có thông tin ngôn ngữ bằng `xml:lang` |
| `faultactor` | `env:Role` / `env:Node` | Thông tin vai trò và node liên quan |
| `detail` | `env:Detail` | Chi tiết ứng dụng |

Trong SOAP 1.2, hai mã lỗi chính tương ứng `Client`/`Server` của SOAP 1.1 đổi thành **`Sender`/`Receiver`**. Ngoài `VersionMismatch`, `MustUnderstand` còn có `DataEncodingUnknown`. Khác nhau về tên phần tử, namespace và mã lỗi khiến **client SOAP 1.1 không thể mặc nhiên parse Fault SOAP 1.2**.

SOAP 1.2 HTTP binding phân biệt các loại lỗi theo HTTP status, trong đó **400** có thể đi với Fault kiểu Sender và **500** có thể đi với Fault kiểu Receiver. Cần xét binding và sản phẩm SOAP đang dùng; không áp dụng máy móc một mã HTTP duy nhất cho mọi Fault SOAP 1.2.

## 5. SOAP Fault khác mã trạng thái HTTP ở điểm nào?

**HTTP status** mô tả kết quả xử lý yêu cầu ở tầng HTTP. **SOAP Fault** là một cấu trúc XML trong SOAP Body để chuyển thông tin lỗi ở tầng SOAP. Khi SOAP chạy trên HTTP, hai tầng cùng tồn tại và cần được đọc song song.

### 5.1. Bảng đối chiếu thực tế

| HTTP status | Khi nào có thể gặp | Có chắc chứa SOAP Fault? |
| --- | --- | --- |
| `200 OK` | Trả SOAP response thành công; đôi khi hệ thống ngoài chuẩn có cách báo lỗi riêng | Không |
| `202 Accepted` | Yêu cầu được chấp nhận nhưng chưa có kết quả đồng bộ; phụ thuộc MEP/binding | Không |
| `400 Bad Request` | Yêu cầu HTTP/XML sai; SOAP 1.2 có thể dùng cho Sender Fault | Không |
| `401 Unauthorized` | Chưa xác thực ở tầng HTTP/proxy | Không |
| `403 Forbidden` | Đã nhận diện nhưng không được phép, hoặc bị policy tầng HTTP chặn | Không |
| `404 Not Found` | Sai URL endpoint, reverse proxy route hoặc path | Không |
| `405 Method Not Allowed` | Ví dụ gửi GET tới endpoint chỉ chấp nhận POST | Không |
| `415 Unsupported Media Type` | `Content-Type` không phù hợp phiên bản SOAP/binding | Không |
| `500 Internal Server Error` | SOAP 1.1 Fault, lỗi xử lý server, hoặc trang lỗi do framework/proxy tạo | Không |
| `502 Bad Gateway` | Gateway không nhận phản hồi hợp lệ từ upstream | Không |
| `503 Service Unavailable` | Dịch vụ tạm không sẵn sàng, quá tải hoặc bảo trì | Không |
| `504 Gateway Timeout` | Gateway chờ upstream quá thời hạn | Không |

Quy tắc cần nhớ:

1. **SOAP 1.1 over HTTP:** khi xử lý SOAP request thất bại và trả SOAP Fault, binding SOAP 1.1 yêu cầu dùng **HTTP 500** kèm Envelope chứa Fault. Vì vậy, `soap:Client` không đồng nghĩa HTTP 400.
2. **SOAP 1.2 over HTTP:** định nghĩa khác SOAP 1.1; các lỗi phía gửi có thể đi với HTTP 400, lỗi phía nhận có thể đi với HTTP 500. Một số trường hợp lỗi xảy ra trước khi tạo Envelope vẫn chỉ có lỗi HTTP.
3. **Bất cứ phiên bản nào:** HTTP 500 không đảm bảo body chứa SOAP Fault; phải kiểm tra `Content-Type` và parse body.
4. **Bất cứ phiên bản nào:** SOAP Fault có thể được chuyển qua transport/binding khác HTTP, nên không thể định nghĩa SOAP Fault bằng một số HTTP cụ thể.

### 5.2. Content-Type và SOAP version

Ví dụ HTTP request SOAP 1.1 điển hình:

~~~http
POST /ws/customers HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:getCustomer"
~~~

Ví dụ SOAP 1.2:

~~~http
POST /ws/customers HTTP/1.1
Host: api.example.test
Content-Type: application/soap+xml; charset=utf-8; action="urn:getCustomer"
~~~

`SOAPAction` là HTTP header được SOAP 1.1 HTTP binding định nghĩa; SOAP 1.2 có thể mang action dưới dạng tham số của media type `application/soap+xml`. Giá trị action cần phù hợp WSDL và cấu hình endpoint cụ thể. Dùng sai `Content-Type`, envelope namespace hoặc action có thể dẫn tới `415`, lỗi định tuyến hoặc SOAP Fault tùy stack xử lý.

**Không tự động suy ra SOAP version chỉ từ tên operation:** kiểm tra SOAP binding trong WSDL, namespace Envelope và Content-Type thực tế trên dây.

## 6. Lỗi kết nối: khi chưa có HTTP response để phân tích

Các lỗi transport xảy ra ở DNS, TCP, TLS, socket hoặc thời gian chờ thường được client quan sát dưới dạng exception. Khi đó không có gì đảm bảo tồn tại HTTP status hay SOAP Fault.

| Hiện tượng | Khả năng thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| DNS lookup failure | Sai hostname, DNS không phân giải | Host trong URL/WSDL, DNS nội bộ, network |
| Connection refused | Không có tiến trình nghe ở host:port, firewall từ chối | Port, service process, network policy |
| Connect timeout | Không thiết lập TCP kịp | Firewall, route, load balancer, thời gian chờ |
| TLS handshake failure | Không thống nhất được TLS, chuỗi chứng chỉ không tin cậy, hostname không khớp, mTLS thiếu client certificate | Truststore, keystore, certificate chain, hostname, TLS protocol |
| Read timeout / socket timeout | Đã gửi yêu cầu nhưng chưa nhận dữ liệu kịp | Thời gian xử lý, gateway timeout, tác vụ dài, backend |
| Connection reset / EOF | Kết nối bị đóng đột ngột | Proxy, server restart, idle timeout, keep-alive |
| HTTP 502/504 | Gateway đã phản hồi lỗi thay mặt upstream | Log/tracing của proxy, upstream health, timeout policy |

**Phân biệt connect timeout và read timeout:** connect timeout thường xảy ra trước khi gửi payload trên kết nối mới; read timeout có thể xảy ra **sau khi bên nhận đã tiếp nhận hoặc xử lý yêu cầu**. Cả hai không đủ để suy ra chính xác server đã hay chưa chạy nghiệp vụ nếu không có thông tin đối chiếu.

Ví dụ giao dịch chuyển tiền: client gửi SOAP request, server đã ghi giao dịch nhưng response bị rơi; client nhận read timeout. Nếu client gửi lại nguyên yêu cầu mà không có cơ chế chống trùng, server có thể thực hiện chuyển tiền thêm một lần. Vì vậy, **timeout không tự động đồng nghĩa được retry vô điều kiện**.

Lỗi TLS có thể ngăn hoàn toàn HTTP request; trường hợp này không thể mong Spring-WS endpoint tạo SOAP Fault. Một HTTP `401` do Basic Authentication hay HTTP `403` do reverse proxy cũng có thể xảy ra trước khi thông điệp vào SOAP layer. Trái lại, kiểm tra chữ ký WS-Security bên trong SOAP Header có thể bị SOAP security interceptor từ chối bằng SOAP Fault nếu thông điệp đã đi đủ sâu để tạo phản hồi SOAP.

## 7. Phân biệt lỗi SOAP từ Header, schema và nghiệp vụ

Không phải mọi SOAP Fault đều xuất phát từ dòng code trong endpoint. Trong Spring-WS, có thể có nhiều bước trước khi phương thức `@Endpoint` được gọi:

| Nguồn phát hiện | Ví dụ | Kết quả có thể có |
| --- | --- | --- |
| SOAP processor | Sai namespace Envelope, header `mustUnderstand` không được xử lý | Fault `VersionMismatch` hoặc `MustUnderstand` |
| XML parser | XML không well-formed | Lỗi parse; có thể bị trả về dưới dạng Fault hoặc HTTP error tùy stack |
| XSD validator/interceptor | Thiếu phần tử bắt buộc hoặc sai kiểu dữ liệu | SOAP Fault phía gửi nếu cấu hình xác thực payload và xử lý lỗi tương ứng |
| WS-Security interceptor | Chữ ký sai, token hết hạn, timestamp không hợp lệ | Thường là security Fault, tùy thư viện và cấu hình |
| Endpoint/service | Mã khách hàng không hợp lệ, dữ liệu không tồn tại, hệ thống phụ trợ không đáp ứng | Fault nghiệp vụ hoặc Fault phía nhận theo hợp đồng |
| Reverse proxy/web server | Sai route, giới hạn kích thước request, auth HTTP, upstream mất kết nối | Có thể là HTTP error thuần, không có SOAP Fault |

Với hướng **contract-first**, cấu trúc lỗi nghiệp vụ nên được định nghĩa thành XML element/type trong XSD và liên kết rõ với `wsdl:fault` khi cần fault message có kiểu. Cơ chế tạo Fault ở runtime phải phù hợp hợp đồng WSDL; việc thêm `<detail>` tùy ý mà không công bố cấu trúc có thể khiến client đã sinh code không giải mã được.

Lưu ý: `wsdl:fault` không đại diện cho mọi trục trặc mạng hoặc lỗi HTTP. WSDL mô tả thông điệp/operation ở tầng dịch vụ; lỗi mất kết nối hoặc gateway trả HTML nằm ngoài phạm vi Fault nghiệp vụ mà client sinh từ WSDL có thể dự đoán.

## 8. Trả SOAP Fault trong Spring Web Services

### 8.1. Chuyển ngoại lệ thành Fault

Spring-WS hỗ trợ các `EndpointExceptionResolver` để ánh xạ ngoại lệ khi xử lý endpoint thành SOAP Fault, trong đó có **`SoapFaultAnnotationExceptionResolver`** và **`SoapFaultMappingExceptionResolver`**. Lựa chọn cụ thể và thứ tự resolver phụ thuộc cấu hình ứng dụng.

Ví dụ minh họa một loại lỗi đầu vào được đánh dấu bằng annotation:

~~~java
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;
import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;

@SoapFault(
    faultCode = FaultCode.CLIENT,
    faultStringOrReason = "Invalid customer identifier"
)
public class InvalidCustomerIdException extends RuntimeException {
    public InvalidCustomerIdException(String message) {
        super(message);
    }
}
~~~

Nếu ứng dụng đã **đăng ký `SoapFaultAnnotationExceptionResolver`**, ngoại lệ này có thể được chuyển thành SOAP Fault phía gửi. Trong SOAP 1.1, mã Fault điển hình là `Client`; với message factory SOAP 1.2, mã tương ứng là `Sender`. Phản hồi SOAP 1.1 theo HTTP binding vẫn có thể mang **HTTP 500** dù vấn đề nằm ở dữ liệu yêu cầu.

Một endpoint ví dụ phát hiện lỗi:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class CustomerEndpoint {
    private static final String NS = "urn:example:customer:v1";
    private final CustomerService service;

    public CustomerEndpoint(CustomerService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetCustomerRequest")
    @ResponsePayload
    public GetCustomerResponse getCustomer(
            @RequestPayload GetCustomerRequest request) {
        if (request.getCustomerId() == null
                || request.getCustomerId().isBlank()) {
            throw new InvalidCustomerIdException("customerId is blank");
        }
        return service.findCustomer(request.getCustomerId());
    }
}
~~~

`GetCustomerRequest`, `GetCustomerResponse` và `CustomerService` trong ví dụ là các kiểu giả định của ứng dụng, không phải lớp có sẵn của Spring-WS; hai DTO thường được sinh từ XSD/JAXB. Ví dụ dùng phương thức `String.isBlank()` (Java 11+).

**Cẩn trọng:** annotation trên exception hoặc câu lệnh `throw` không đủ để bảo đảm có SOAP Fault nếu resolver chưa được cấu hình, exception bị chặn trước đó, hoặc lỗi nằm bên ngoài SOAP endpoint. Với lỗi quy định chi tiết trong WSDL, cần bổ sung cơ chế tạo `Detail` đúng schema, không chỉ đặt chuỗi mô tả.

### 8.2. Chọn mã lỗi hợp lý

- **Client/Sender:** yêu cầu sai theo hợp đồng, ví dụ thiếu trường bắt buộc, sai định dạng hay giá trị không được hỗ trợ. Không retry với cùng dữ liệu chưa sửa.
- **Server/Receiver:** dịch vụ không thể hoàn tất xử lý yêu cầu, ví dụ backend tạm unavailable; khả năng retry phụ thuộc bản chất thao tác và chính sách an toàn.
- **VersionMismatch/MustUnderstand:** lỗi ở quy tắc SOAP Envelope/Header, thường cần sửa cấu hình tương thích hoặc bên gửi.
- **Mã chi tiết nghiệp vụ:** đặt trong `detail`/`Detail` theo XSD để client phân biệt `CUSTOMER_NOT_FOUND`, `BUSINESS_RULE_VIOLATION`, v.v.

Không lộ stack trace, connection string, thông tin chứng chỉ, token, khóa bí mật hoặc dữ liệu cá nhân trong Fault trả cho bên ngoài. Log nội bộ có thể lưu thông tin chẩn đoán đã được giới hạn và che dữ liệu nhạy cảm, cùng correlation ID để đối chiếu.

## 9. Nhận và phân loại lỗi tại SOAP client Spring-WS

`WebServiceTemplate` hỗ trợ gửi/nhận thông điệp SOAP (thường dùng `Jaxb2Marshaller` để chuyển object Java ↔ XML). Khi phía đối tác báo lỗi hoặc kết nối thất bại, các nhóm ngoại lệ cần quan tâm bao gồm:

| Nhóm ngoại lệ Spring-WS | Tình huống tiêu biểu | Cách xử lý đề xuất |
| --- | --- | --- |
| `SoapFaultClientException` | Nhận diện được SOAP Fault từ đối tác | Đọc mã Fault, nội dung lỗi và chi tiết hợp đồng |
| `WebServiceTransportException` | Transport HTTP báo lỗi, không được xử lý như SOAP Fault thành công | Ghi trạng thái/chi tiết transport, kiểm tra body nếu khả dụng |
| `WebServiceIOException` | Sự cố I/O, timeout, reset, DNS, handshake... | Xác định pha kết nối và trạng thái gửi yêu cầu; áp dụng chính sách retry thận trọng |
| `WebServiceClientException` | Lớp nền cho các loại lỗi client Spring-WS | Giữ làm xử lý dự phòng sau các loại cụ thể |

Ví dụ phân loại ở một lớp tích hợp:

~~~java
try {
    Object response = webServiceTemplate.marshalSendAndReceive(request);
    return (GetCustomerResponse) response;
} catch (SoapFaultClientException ex) {
    // Có SOAP Fault: dùng fault code/detail theo contract.
    log.warn("Partner SOAP Fault: {}", ex.getFaultStringOrReason());
    throw new PartnerSoapFaultException("Partner returned SOAP Fault", ex);
} catch (WebServiceTransportException ex) {
    // Mã HTTP/lỗi transport không được ánh xạ thành SOAP Fault.
    log.warn("Partner HTTP transport error: {}", ex.getMessage());
    throw new PartnerTransportException("Partner HTTP error", ex);
} catch (WebServiceIOException ex) {
    // Có thể là timeout, reset, DNS hoặc TLS: chưa biết outcome nghiệp vụ.
    log.warn("Partner I/O error: {}", ex.getMessage());
    throw new PartnerConnectivityException("Partner connection failed", ex);
}
~~~

Đây là **đoạn minh họa xử lý**, với các exception `Partner...Exception` và biến `request`/`webServiceTemplate` do dự án tự định nghĩa. Đối với `WebServiceTemplate`, việc nhận biết Fault còn phụ thuộc SOAP message factory, HTTP sender, phiên bản SOAP và cấu hình kiểm tra connection. Đặc biệt, cần kiểm thử tích hợp cho **SOAP 1.2 Fault trên HTTP 400** và những đối tác trả status khác quy ước; không nên chỉ dựa vào giả định mọi Fault đều được ném dưới cùng một exception.

Một chiến lược xử lý tốt tách ba hướng:

1. **Lỗi hợp đồng/validation:** trả lỗi có nghĩa cho caller, ghi nguyên nhân đủ để sửa payload.
2. **Fault nghiệp vụ:** chuyển mã lỗi có cấu trúc sang mô hình lỗi của ứng dụng; không parse chuỗi mô tả.
3. **Lỗi tạm thời ở transport/backend:** cân nhắc retry theo idempotency, thời hạn thực thi và dấu hiệu thao tác đã được xử lý.

## 10. Retry: tránh biến lỗi mạng thành lỗi dữ liệu

Không có quy tắc “HTTP 5xx thì retry ngay” cho mọi operation SOAP. Quyết định retry phụ thuộc **nguyên nhân**, **thao tác có tác dụng phụ không**, và **khả năng xác định kết quả lần gọi trước**.

| Tình huống | Retry tự động? | Lý do |
| --- | --- | --- |
| SOAP Sender/Client Fault vì dữ liệu sai | Thông thường không | Gửi lại cùng payload vẫn sai |
| HTTP 401/403 | Không cho tới khi sửa quyền/cấu hình | Lặp lại không giải quyết xác thực |
| HTTP 404/415 | Không cho tới khi sửa URL/Content-Type | Thường là cấu hình hoặc contract |
| HTTP 503/502/504 với truy vấn chỉ đọc | Có thể, giới hạn số lần | Có thể là lỗi tạm thời; cần backoff |
| SOAP Receiver/Server Fault | Tùy operation | Có thể là lỗi tạm, nhưng chưa chắc retry an toàn |
| Read timeout khi tạo đơn hàng/thanh toán | Không retry mù quáng | Server có thể đã ghi giao dịch |
| Connect failure trước khi request được gửi | Có thể tùy bằng chứng và operation | Vẫn cần kiểm soát retry và số lần |

Với các operation thay đổi trạng thái, áp dụng một hoặc nhiều biện pháp: **mã yêu cầu duy nhất/idempotency key**, chống trùng ở server, truy vấn trạng thái giao dịch trước khi gửi lại, cơ chế đối soát, hoặc thiết kế operation idempotent. Chỉ dùng correlation ID để truy vết **chưa đủ** bảo đảm chống thực hiện hai lần; phía server phải có quy tắc nhận diện và từ chối trùng hiệu quả.

Khi retry được cho phép, sử dụng số lần tối đa, exponential backoff có jitter, giới hạn timeout toàn bộ và theo dõi tác động lên đối tác. Không retry vô hạn khi đối tác đang quá tải. Với các bản tin có `Retry-After` ở tầng HTTP, cân nhắc hướng dẫn của đối tác và tính an toàn của operation trước khi thử lại.

## 11. Quy trình chẩn đoán một lỗi SOAP thực tế

Giả sử client gọi operation `CreateOrder` qua HTTPS và bị báo “server error”. Thay vì kết luận ngay lỗi nghiệp vụ, thực hiện:

**Bước 1 — Xác định có HTTP response không.** Nếu exception là DNS/TLS/connect timeout, tập trung vào cấu hình host/port/chứng chỉ/kết nối. Nếu read timeout, đánh dấu trạng thái xử lý là **chưa xác định** cho đến khi có đối soát.

**Bước 2 — Ghi lại HTTP status và thông tin không nhạy cảm.** Kiểm tra URL thật sự đã gọi, method POST, `Content-Type`, SOAP version, header action và mã HTTP. HTTP 404 hay 415 thường chỉ ra cấu hình lệch; HTTP 502/504 thường cần log gateway.

**Bước 3 — Kiểm tra body trước khi đọc Fault.** Nếu body bắt đầu bằng HTML của proxy hoặc không phải SOAP Envelope, không parse thành SOAP Fault. Nếu body là XML SOAP, kiểm tra namespace và phần tử `Fault` trong Body.

**Bước 4 — Đọc mã Fault và detail.** SOAP 1.1: `faultcode`, `faultstring`, `detail`. SOAP 1.2: `Code`, `Reason`, `Detail`. Đối chiếu mã lỗi chi tiết với XSD/WSDL và tài liệu tích hợp.

**Bước 5 — Đối chiếu ở server/gateway.** Sử dụng request ID/transaction ID, timestamp, endpoint, thời gian xử lý và log theo request để tìm xem operation đã bắt đầu, đã commit hay chưa. Không log thô body chứa token WS-Security, chứng chỉ, dữ liệu người dùng hoặc thông tin thanh toán.

**Bước 6 — Chọn hành động.** Sửa request nếu Sender/Client Fault; sửa endpoint/config nếu 404/415; kiểm tra authentication nếu 401/403; điều tra hạ tầng nếu gateway/timeout; chỉ retry khi đã đánh giá tính an toàn nghiệp vụ.

Ví dụ phân biệt hai phản hồi HTTP 500:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/xml; charset=utf-8

<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>Backend temporarily unavailable</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Đây là **SOAP 1.1 Fault**, có thể xử lý theo hợp đồng SOAP.

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/html; charset=utf-8

<html><body><h1>Internal Server Error</h1></body></html>
~~~

Đây chỉ là **lỗi HTTP với HTML body**; client SOAP không nên cố ép HTML thành `SoapFault` hay JAXB response.

## 12. Kiểm thử tương thích cho contract-first SOAP

Việc kiểm tra riêng code Java không đủ: cần kiểm tra **XML trên dây, mã HTTP và hành vi client**. Với Spring-WS, có thể dùng `MockWebServiceClient` để kiểm thử endpoint, `MockWebServiceServer` cho client và các bài thử tích hợp thực qua HTTP(S), proxy, TLS khi cần xác minh toàn bộ đường truyền.

| Ca kiểm thử | Kết quả cần xác nhận |
| --- | --- |
| Request hợp lệ | SOAP response bình thường; HTTP status phù hợp binding |
| Sai dữ liệu XSD | Validator/interceptor xử lý đúng; Fault khi ứng dụng được cấu hình tạo Fault |
| Lỗi nghiệp vụ đã công bố trong WSDL | Fault code/detail đúng namespace và XML type |
| SOAP 1.1 `Client` Fault | Client vẫn nhận diện Fault dù HTTP status thường là 500 |
| SOAP 1.2 `Sender` Fault qua HTTP 400 | Client nhận diện và phân loại đúng theo cấu hình/version |
| HTTP 500 kèm HTML | Phân loại transport/server error; không parse HTML thành SOAP Fault |
| HTTP 401/403/404/415 | Hiển thị nhóm lỗi auth/route/media thích hợp |
| HTTP 502/503/504 từ gateway | Phân loại lỗi hạ tầng và áp dụng retry policy phù hợp |
| Kết nối bị từ chối, DNS sai | Không giả định có HTTP status hoặc SOAP Fault |
| TLS certificate không tin cậy, hostname mismatch | Báo lỗi handshake; không gọi endpoint thành công |
| Read timeout sau khi server đã commit | Không lặp lại thao tác gây tác dụng phụ; đối soát theo transaction ID |
| Header `mustUnderstand` không được xử lý | Fault tương ứng khi SOAP processor phát hiện |
| SOAP version/Content-Type không phù hợp | Phát hiện lỗi tương thích chính xác |
| Fault chứa mã nghiệp vụ và thông tin nhạy cảm | Mã được giữ đúng; không lộ stack trace, secret hoặc PII |

Cần lưu ý một số bài thử không thể mô phỏng đầy đủ bằng mock thuần trong memory. Ví dụ **TCP reset, TLS handshake failure, gateway HTML 502** phải được kiểm thử với hạ tầng hoặc HTTP sender giả lập phù hợp, vì mock endpoint thông thường tập trung vào SOAP payload và hành vi trong ứng dụng.

Khi so sánh SOAP XML, kiểm tra theo **namespace URI, cấu trúc phần tử và giá trị**, không phụ thuộc prefix `soap` hay `env`; hai tiền tố khác nhau vẫn có thể trỏ cùng namespace. Kiểm tra thứ tự phần tử khi schema sử dụng `xs:sequence`. Tách assertion cho HTTP status và SOAP Fault code để tránh nhầm hai tầng.

## 13. Bài tập tình huống

Một đối tác công bố operation `CreateInvoice` qua SOAP 1.1. Client nhận bốn trường hợp:

**A.** HTTP 500, body là SOAP Envelope có `faultcode=soap:Client` và `detail` chứa `INVALID_TAX_CODE`.

**B.** HTTP 500, body là HTML với nội dung “upstream service unavailable”.

**C.** Không có HTTP response; client ghi nhận read timeout sau khi gửi request.

**D.** HTTP 415 khi gửi `application/soap+xml` vào endpoint yêu cầu `text/xml`.

Hãy tự trả lời: trường hợp nào là SOAP Fault, trường hợp nào có thể kết luận hóa đơn chưa được tạo, trường hợp nào cần sửa payload/cấu hình và trường hợp nào nguy hiểm nếu retry ngay?

**Gợi ý đáp án:**

- **A** là SOAP 1.1 Fault báo lỗi phía gửi. Kiểm tra `INVALID_TAX_CODE` theo hợp đồng và sửa dữ liệu trước khi gửi lại.
- **B** là lỗi HTTP phía server/gateway; không có chứng cứ body là SOAP Fault. Cần đối chiếu log và trạng thái giao dịch.
- **C** là lỗi kết nối với **kết quả nghiệp vụ chưa rõ**. Server có thể đã tạo hóa đơn; cần đối soát hoặc cơ chế chống trùng trước khi thử lại.
- **D** là lỗi media type/cấu hình tương thích SOAP version. Sửa Content-Type, Envelope và binding phù hợp thay vì retry nguyên bản tin.

Không trường hợp nào trong **B/C** cho phép chắc chắn kết luận hóa đơn **chưa** được tạo chỉ từ thông tin client đang có.

## 14. Ghi nhớ

- **SOAP Fault là cấu trúc trong SOAP Body**, còn HTTP status là phản hồi ở tầng truyền tải. Có thể tồn tại cùng lúc nhưng không thay thế nhau.
- **SOAP 1.1:** `faultcode`/`faultstring`/`detail`, mã `Client`/`Server`; SOAP Fault qua HTTP thường được trả với **500** theo SOAP 1.1 binding.
- **SOAP 1.2:** `Code`/`Reason`/`Detail`, mã `Sender`/`Receiver`; quy tắc HTTP binding khác SOAP 1.1, có thể gặp **400** hoặc **500** với SOAP Fault.
- **HTTP 500 không chứng minh có SOAP Fault; HTTP 404/415/502/504 cũng không mặc nhiên là lỗi nghiệp vụ SOAP.** Cần kiểm tra XML, namespace và Content-Type.
- **Lỗi DNS/TCP/TLS/timeout không cung cấp HTTP status hoặc SOAP Fault đáng tin cậy.** Read timeout có thể xảy ra sau khi server đã hoàn tất tác vụ.
- Trong **Spring-WS contract-first**, định nghĩa fault detail theo XSD/WSDL, cấu hình xử lý ngoại lệ ở endpoint, phân loại exception ở `WebServiceTemplate` và kiểm thử cả tình huống hạ tầng.
- Với thao tác có tác dụng phụ, **retry chỉ an toàn khi có quy tắc idempotency/chống trùng hoặc xác minh được trạng thái nghiệp vụ**.
