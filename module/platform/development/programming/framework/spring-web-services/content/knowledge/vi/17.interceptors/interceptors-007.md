# SoapEnvelopeLoggingInterceptor và ghi phong bì SOAP

Khi tích hợp dịch vụ **Spring Web Services (Spring-WS)** theo hướng **contract-first**, một SOAP client có thể gặp lỗi dù XSD/WSDL hợp lệ: phần tử request đúng kiểu nhưng sai namespace, SOAP Header thiếu thông tin WS-Security, SOAPAction không khớp binding, hoặc server trả SOAP Fault trước khi đến `@Endpoint`. Lúc này cần quan sát **SOAP Envelope thực sự được xử lý** thay vì chỉ nhìn Java object đã ánh xạ bằng JAXB.

`SoapEnvelopeLoggingInterceptor` là interceptor phía **server** của Spring-WS, được dùng để ghi nội dung **phong bì SOAP** (*SOAP Envelope*) khi request, response hoặc Fault đi qua điểm xử lý phù hợp. Công cụ này hữu ích trong phát triển và chẩn đoán tích hợp, nhưng cũng có rủi ro nghiêm trọng: Envelope chứa cả SOAP Header lẫn Body, có thể mang UsernameToken, chữ ký XML, thông tin chứng chỉ, dữ liệu khách hàng hoặc thông tin giao dịch.

Bài học thuộc chương **Interceptor** của module `SPRING_WEB_SERVICES`. Trọng tâm là hiểu **ghi cái gì, ghi ở đâu, cấu hình ra sao, khi nào không nên ghi nguyên Envelope và kiểm thử thế nào**. Các ví dụ Java minh họa API của những phiên bản Spring-WS hỗ trợ class và các thuộc tính được nêu; cần đối chiếu Javadoc/dependency của đúng phiên bản Spring-WS, Spring Framework và Java/Jakarta mà dự án đang dùng.

## 1. SOAP Envelope bao gồm những gì?

Một bản tin SOAP không chỉ là payload nghiệp vụ. Với **SOAP 1.1**, cấu trúc điển hình là:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1"
    xmlns:ctx="urn:example:context:v1">

  <soap:Header>
    <ctx:CorrelationId>corr-27a</ctx:CorrelationId>
  </soap:Header>

  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
      <ord:currency>VND</ord:currency>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Các phần có vai trò khác nhau:

| Phần | Chứa nội dung gì? | Vì sao có thể cần quan sát? |
| --- | --- | --- |
| `soap:Envelope` | Root element và namespace phiên bản SOAP. | Xác định SOAP 1.1 hay SOAP 1.2, envelope hợp lệ không. |
| `soap:Header` | Metadata như correlation, WS-Addressing, WS-Security. | Kiểm tra sự hiện diện, QName/role, `mustUnderstand` và thứ tự xử lý header. |
| `soap:Body` | XML payload nghiệp vụ hoặc SOAP Fault. | Đối chiếu QName, cấu trúc XSD, dữ liệu request/response và Fault. |
| `soap:Fault` | Thông tin lỗi protocol/ứng dụng khi có. | Phân biệt Fault của server với lỗi HTTP/TLS/proxy. |

Một bản tin có thể **không có Header**, nhưng **Body là thành phần chính cần có** theo cấu trúc SOAP. Nội dung bên trong Body thường là phần tử global từ XSD, ví dụ QName `{urn:example:orders:v1}CreateOrderRequest`. Spring-WS có thể định tuyến đến method `@PayloadRoot` dựa trên QName này.

### 1.1. SOAP Envelope không phải raw HTTP request

Khi ghi Envelope, bạn thường không ghi đầy đủ:

- Dòng HTTP như `POST /ws HTTP/1.1` và HTTP response status.
- HTTP headers như `Host`, `Content-Type`, `Authorization`, `Cookie` hoặc `traceparent`.
- Thông tin bắt tay TLS, peer certificate chain hoặc proxy networking.
- Bảo đảm toàn bộ MIME attachments/MTOM được biểu diễn đầy đủ như byte trên dây.

Một log XML của Envelope **không phải bản chụp byte-for-byte của HTTP request**. Message factory có thể parse và serialize lại XML, thay prefix/whitespace/XML declaration hoặc biểu diễn attachment bằng XOP reference. Vì thế, để kiểm tra lỗi `415 Unsupported Media Type`, TLS handshake, proxy timeout hoặc MIME boundary, đôi khi cần **transport-level diagnostics** riêng, với chính sách bảo vệ dữ liệu tương ứng.

### 1.2. Khác biệt với SOAP 1.2

SOAP 1.2 có namespace Envelope khác:

~~~xml
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Header/>
  <env:Body>
    <!-- XML payload hoặc env:Fault theo SOAP 1.2 -->
  </env:Body>
</env:Envelope>
~~~

SOAP 1.1 thường dùng HTTP `Content-Type: text/xml`; SOAP 1.2 dùng `application/soap+xml` trong các binding tương ứng. SOAP Fault cũng khác cấu trúc: SOAP 1.1 có `faultcode`/`faultstring`/`detail`; SOAP 1.2 có các element như `Code`/`Reason`/`Detail`. Logging giúp nhận diện sự khác biệt nhưng **không tự sửa lỗi SOAP version**; phải kiểm tra WSDL binding, message factory và client.

## 2. Ghi Envelope khác ghi payload và ghi giao thức HTTP

Spring-WS có nhiều cách quan sát bản tin; chọn đúng công cụ giúp tránh thu thập dữ liệu quá mức.

| Cách quan sát | Phạm vi thường ghi | Mục tiêu | Giới hạn chính |
| --- | --- | --- | --- |
| `PayloadLoggingInterceptor` | Payload XML trong SOAP Body. | Kiểm tra QName/schema và dữ liệu nghiệp vụ. | Không cho biết đầy đủ SOAP Header/WS-Security. |
| **`SoapEnvelopeLoggingInterceptor`** | SOAP Envelope, gồm Header + Body tại interceptor. | Chẩn đoán header, Envelope, Fault, namespace. | Có thể làm lộ dữ liệu nhạy cảm; có chi phí serialize. |
| Spring-WS `MessageTracing` | Tùy logging level và version: thông tin tóm tắt hoặc message chi tiết ở server/client. | Theo dõi message sent/received mà không tự viết interceptor. | Cần xác minh phạm vi/log level và bảo vệ log. |
| Custom `EndpointInterceptor` | Metadata chọn lọc như correlation ID, SOAPAction, outcome. | Log production an toàn, có cấu trúc. | Không thay thế raw XML khi cần debug sâu. |
| Client `ClientInterceptor` | Message outbound/inbound ở client stack. | Chẩn đoán phía SOAP caller. | Không dùng trực tiếp server interceptor như client interceptor. |
| HTTP transport/proxy tracing | HTTP method, URL, headers, status, timing, có thể raw bytes. | Tìm lỗi mạng, gateway, TLS/HTTP. | Có thể thu thập secrets ở HTTP layer; khác XML SOAP. |

**Không nên bật đồng thời tất cả các cơ chế ở mức chi tiết cao trong production.** Một request có thể bị ghi lặp nhiều bản, tạo áp lực I/O, heap và khiến dữ liệu nhạy cảm xuất hiện ở nhiều nơi.

### 2.1. Vì sao ghi Payload không đủ để tìm lỗi Header?

Ví dụ client gửi `CreateOrderRequest` đúng schema nhưng thiếu `wsse:Security`. `PayloadLoggingInterceptor` có thể ghi một Body trông hoàn toàn hợp lệ. Trong khi đó, **Envelope logging** có thể cho thấy Header thiếu hoặc khác QName, dù để xác định **chữ ký có hợp lệ không** vẫn phải xem kết quả của security interceptor, không dựa vào mắt đọc XML.

Ngược lại, nếu chỉ muốn xác nhận `amount` và namespace `CreateOrderRequest`, ghi cả Header WS-Security có thể thu thập dữ liệu quá mức. Trong nhiều trường hợp, **metadata logging** với QName, correlation ID và mã kết quả là đủ.

### 2.2. Vì sao ghi Envelope không thay việc kiểm tra XSD?

Interceptor logging chủ yếu phục vụ **quan sát**. Nó không xác nhận `xs:pattern`, `xs:enumeration`, `minOccurs` hay miền giá trị có hợp lệ không. Cần `PayloadValidatingInterceptor` hoặc schema validation tương đương theo thiết kế contract-first.

Chẳng hạn `clientOrderId` vi phạm pattern XSD vẫn có thể được ghi thành XML well-formed. Logger không nên bị nhầm thành validator hoặc chứng cứ nghiệp vụ đã chấp nhận request.

## 3. SoapEnvelopeLoggingInterceptor nằm ở đâu trong pipeline?

Một request SOAP từ đối tác thường đi qua HTTP transport, SOAP message factory, endpoint mapping, interceptor chain, endpoint adapter và business service:

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as MessageDispatcherServlet
    participant M as MessageFactory/Dispatcher
    participant L as EnvelopeLoggingInterceptor
    participant V as Validation/Security Interceptors
    participant E as @Endpoint/Business
    C->>S: HTTP POST + SOAP Envelope
    S->>M: Parse SOAP message
    M->>L: handleRequest()
    L->>V: Tiếp tục interceptor chain
    V->>E: Invoke khi hợp lệ
    E-->>V: Response hoặc exception
    V-->>L: handleResponse()/handleFault()
    L-->>M: Hoàn thiện xử lý
    M-->>C: SOAP response/Fault
~~~

Sơ đồ chỉ minh họa một thứ tự khả dĩ của các interceptor. **Thứ tự và việc interceptor có được gọi hay không phụ thuộc cấu hình**, kết quả endpoint mapping, lỗi xảy ra ở tầng nào và cách Spring-WS giải quyết exception.

Các callback của `EndpointInterceptor` thường liên quan tới:

| Callback | Khi nào có thể được gọi? | Ý nghĩa đối với logging |
| --- | --- | --- |
| `handleRequest(MessageContext, Object)` | Trước khi endpoint method được gọi, sau khi request đã thành message và endpoint tương ứng được xác định. | Có thể ghi request Envelope. |
| `handleResponse(MessageContext, Object)` | Khi xử lý tạo SOAP response bình thường. | Có thể ghi response Envelope. |
| `handleFault(MessageContext, Object)` | Khi message response là SOAP Fault qua pipeline tương ứng. | Có thể ghi Fault Envelope. |
| `afterCompletion(MessageContext, Object, Exception)` | Sau vòng xử lý interceptor tương ứng trong điều kiện framework gọi callback. | Phù hợp dọn MDC/resource, không coi là nơi bảo đảm có đầy đủ body. |

**Hệ quả quan trọng:** `SoapEnvelopeLoggingInterceptor` là **endpoint interceptor**, không phải một HTTP filter chạy trên mọi byte đầu vào. Nếu SOAP XML malformed và parser thất bại trước khi dispatcher chọn endpoint, hoặc lỗi nằm ở TLS/proxy, interceptor có thể **không hề được gọi**. “Không có log Envelope” không chứng minh client chưa gửi request.

### 3.1. Khi handler không được tìm thấy

Một request có QName `{urn:example:orders:v2}CreateOrderRequest` nhưng server chỉ đăng ký `@PayloadRoot(namespace="urn:example:orders:v1", ...)`. Mapping có thể không chọn được endpoint. Vì interceptor được gắn trong chu trình endpoint, việc không thấy log từ interceptor **không phải bằng chứng** rằng XML Body không tới server.

Khi điều tra dạng lỗi này, có thể bật trace/diagnostics của framework ở môi trường test, kiểm tra mapping logs hoặc sử dụng transport-level metadata tracing. Tránh tắt bảo mật hoặc bật ghi raw production toàn diện chỉ để “cho chắc”.

### 3.2. Khi validation hoặc security từ chối request

Một interceptor đứng **sau** security interceptor có thể không thấy request nếu security từ chối và dừng chuỗi trước đó. Một interceptor đứng **trước** security có thể thấy bản tin **chưa được xác minh**, bao gồm token hoặc dữ liệu attacker gửi.

Không có thứ tự “ghi trước hay sau security” luôn đúng:

- **Ghi trước security** có thể hỗ trợ debug nhưng rủi ro lộ raw secrets và nhận dữ liệu không đáng tin.
- **Ghi sau security** hạn chế ghi request bị từ chối, nhưng có thể khó tìm lỗi security và vẫn không loại trừ dữ liệu nhạy cảm trong bản tin hợp lệ.
- Với production, thường nên log **metadata đã lọc** ở các ranh giới có thể kiểm soát, và dùng cơ chế chẩn đoán có kiểm soát đặc biệt nếu thật sự cần Envelope.

## 4. Cấu hình SoapEnvelopeLoggingInterceptor trong Spring-WS

Ở các phiên bản Spring-WS có `SoapEnvelopeLoggingInterceptor`, có thể đăng ký nó qua `WsConfigurer#addInterceptors`. Ví dụ sau **chỉ bật ở profile debug riêng**, không bật mặc định trong production:

~~~java
package com.example.orders.config;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.SoapEnvelopeLoggingInterceptor;

@Configuration
@Profile("soap-envelope-debug")
public class SoapEnvelopeDebugConfig implements WsConfigurer {

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        SoapEnvelopeLoggingInterceptor logging =
                new SoapEnvelopeLoggingInterceptor();

        logging.setLogRequest(true);
        logging.setLogResponse(true);
        logging.setLogFault(true);

        interceptors.add(logging);
    }
}
~~~

**Giả định của ví dụ:** ứng dụng đã bật cấu hình endpoint Spring-WS, ví dụ thông qua `@EnableWs` và cấu hình `MessageDispatcherServlet` phù hợp; `WsConfigurer` được framework phát hiện; phiên bản Spring-WS thực tế có class/các setter trên. `@Profile("soap-envelope-debug")` chỉ đăng ký cấu hình này khi profile được kích hoạt; một profile Spring khác có thể đăng ký interceptors bổ sung.

Đây là **server interceptor**. Không thêm thẳng object đó vào `WebServiceTemplate#setInterceptors(...)` nếu nó không triển khai `ClientInterceptor`: server endpoint interceptor và client interceptor là hai giao diện, hai chu trình khác nhau.

### 4.1. Các thuộc tính logging

| Thuộc tính | Ý nghĩa khi bật | Điều cần kiểm tra |
| --- | --- | --- |
| `setLogRequest(true)` | Cho phép ghi request trong callback phù hợp. | Chỉ log khi cấp logger và callback/endpoint mapping cho phép. |
| `setLogResponse(true)` | Cho phép ghi response thành công. | Không bảo đảm response có ngay nếu đang là lỗi transport. |
| `setLogFault(true)` | Cho phép ghi SOAP Fault đi qua đường Fault. | Không bao gồm mọi lỗi HTTP, TLS hay proxy. |
| Logger name / log level | Quyết định bản ghi có được xuất qua logging backend không. | Tùy implementation và version, cần xác nhận category/level thực tế. |
| Thứ tự đăng ký | Quyết định quan hệ với validation/security/logging interceptors khác. | Có thể làm thay đổi bản tin nào được ghi và thời điểm ghi. |

Trước khi dùng một setter, nên xác minh Javadoc/bytecode của artifact `spring-ws-core` đang chạy. Nếu cấu hình sao chép từ phiên bản khác không compile, đừng bỏ qua lỗi và cho rằng property đã được bật; cần chọn API phù hợp với runtime.

### 4.2. Bật profile debug theo cách có kiểm soát

Ví dụ cấu hình Spring Boot khi cần kiểm thử cục bộ:

~~~yaml
spring:
  profiles:
    active: soap-envelope-debug

logging:
  level:
    org.springframework.ws.soap.server.endpoint.interceptor: DEBUG
~~~

YAML trên chỉ minh họa rằng profile và logging level đều phải phù hợp. **Không đưa `spring.profiles.active: soap-envelope-debug` vào cấu hình chung của production.** Trong triển khai thật, kích hoạt profile qua công cụ deployment, môi trường test riêng hoặc tham số runtime được quản lý, và bật trong thời gian ngắn.

Logger category/cấp chi tiết có thể khác theo phiên bản hoặc cấu hình backend, nên cần **kiểm tra log thực tế**. Nếu class được đăng ký mà không thấy log, lần lượt kiểm tra profile active, bean config, tên logger, mức logger, endpoint mapping, callback, appender/filter và yêu cầu có đi đến `MessageDispatcherServlet` hay không.

Đối với một số phiên bản/configuration, logger chỉ xây dựng chuỗi XML khi cấp log cho phép; đối với các phiên bản khác, đường đi có thể thay đổi. Không dựa vào giả định này để bỏ qua benchmark chi phí logging.

### 4.3. Thứ tự với những interceptor khác

Ví dụ cấu hình mang tính lựa chọn:

~~~java
@Override
public void addInterceptors(List<EndpointInterceptor> interceptors) {
    // Chỉ minh họa thứ tự, không phải khuyến nghị dùng chung
    // trong môi trường chứa dữ liệu thật.
    interceptors.add(correlationInterceptor);
    interceptors.add(envelopeLoggingInterceptor);
    interceptors.add(validationInterceptor);
    interceptors.add(securityInterceptor);
}
~~~

Đây là **trích đoạn**: các biến interceptor phải do ứng dụng tạo/tiêm, và chính sách thứ tự thực tế phải được thiết kế theo khả năng framework, security và request mapping. Thứ tự ảnh hưởng đến việc:

- Correlation ID có sẵn để gắn vào log trước/sau khi in XML hay không.
- Envelope được log trước hay sau validation/security.
- Một interceptor trả `false` hoặc ném exception thì interceptor phía sau có được gọi không.
- Response/Fault callbacks được chạy theo thứ tự nào trong chain.

**Không dùng thứ tự logging để thay đổi mức độ tin cậy của dữ liệu.** Nếu cần kiểm tra chữ ký trước xử lý nghiệp vụ, security interceptor phải có cấu hình bảo vệ thích hợp; logger không thực hiện xác thực. Các dữ liệu nằm trong Header chưa được ký/xác minh phải được xem là dữ liệu không đáng tin.

## 5. Request, response và SOAP Fault được ghi như thế nào?

Để hiểu rõ, giả sử XSD/WSDL có operation `CreateOrder` và bean endpoint được đăng ký cho QName `{urn:example:orders:v1}CreateOrderRequest`.

### 5.1. Request Envelope tại server

SOAP client POST tới địa chỉ `soap:address` của WSDL, ví dụ:

~~~http
POST /ws HTTP/1.1
Host: localhost:8080
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/CreateOrder"
~~~

HTTP header bên trên không phải nội dung mà `SoapEnvelopeLoggingInterceptor` nhất thiết ghi. Nội dung XML SOAP tương ứng:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ctx="urn:example:context:v1"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header>
    <ctx:CorrelationId>corr-27a</ctx:CorrelationId>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
      <ord:currency>VND</ord:currency>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Một bản ghi debug **minh họa**, không phải output cố định của mọi Spring-WS version:

~~~text
DEBUG [SoapEnvelopeLoggingInterceptor] Request SOAP Envelope:
<soap:Envelope ...>
  <soap:Header>...</soap:Header>
  <soap:Body><ord:CreateOrderRequest>...</ord:CreateOrderRequest></soap:Body>
</soap:Envelope>
~~~

Trong log thực tế, các prefix, whitespace, XML declaration và format của log line có thể khác. Đừng viết monitoring dựa trên việc logger dùng chính xác từ `Request SOAP Envelope:` nếu implementation chưa cam kết định dạng đó.

### 5.2. Response thành công

Khi endpoint hoàn thành và JAXB/return handler tạo response, một Envelope dự kiến:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ctx="urn:example:context:v1"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header>
    <ctx:CorrelationId>corr-27a</ctx:CorrelationId>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderResponse>
      <ord:orderId>ORD-000184</ord:orderId>
      <ord:status>ACCEPTED</ord:status>
    </ord:CreateOrderResponse>
  </soap:Body>
</soap:Envelope>
~~~

Nếu `setLogResponse(true)` và response callback chạy, logger có thể ghi XML response. Một SOAP response **không nhất thiết chứa các Header giống request**: chỉ có correlation header trong response khi server code/interceptor chủ động thêm nó theo hợp đồng.

Nếu SOAP response đang được tạo theo streaming, thời điểm log có thể ảnh hưởng đến việc payload đã materialize chưa. Không giả định nội dung được ghi là bản copy bitwise của HTTP response sau khi đi qua serializer/proxy.

### 5.3. SOAP Fault

Khi schema validation hoặc nghiệp vụ thất bại, Spring-WS có thể tạo SOAP 1.1 Fault:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Request không hợp lệ</faultstring>
      <detail>
        <errorCode>INVALID_ORDER_REQUEST</errorCode>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

`setLogFault(true)` cho phép ghi Fault ở callback `handleFault` khi chu trình xử lý chạy đến đó. Nhưng **không phải mọi lỗi đều có SOAP Fault**. Ví dụ, request bị chặn tại WAF/gateway, TLS handshake thất bại, HTTP body không parse được hoặc service process bị mất kết nối có thể không tạo SOAP response.

### 5.4. Khi log thiếu request hoặc thiếu response

| Quan sát | Những nguyên nhân cần kiểm tra |
| --- | --- |
| Có request log, không có response log | Server bị lỗi trước response; response property/callback chưa chạy; endpoint một chiều; logger filter. |
| Có SOAP Fault log, không có log success | Lỗi chuyển qua `handleFault` thay vì `handleResponse`. |
| Có HTTP access log, không có Envelope log | Chưa có endpoint mapping, parser thất bại sớm, profile/log level chưa bật hoặc interceptor không đăng ký. |
| Có response SOAP nhưng không có HTTP status | Envelope logger không ghi HTTP status; cần transport metadata. |
| Có Header nhưng không thấy dữ liệu attachment | XML Envelope có thể chỉ có reference tới MIME attachment; không đại diện byte MIME. |

Đọc **cả log server, thông điệp mà client thấy, WSDL/XSD và vị trí lỗi** trước khi kết luận vấn đề nằm ở interceptor.

## 6. Phạm vi quan sát: SOAP 1.1, SOAP 1.2 và attachments

### 6.1. Không đồng nhất SOAP Fault với HTTP 500

Trong SOAP 1.1 trên HTTP, một Fault thường đi cùng HTTP status lỗi theo binding, nhưng còn phụ thuộc server, SOAP version và transport. HTTP 500 **có thể** chứa SOAP Fault, cũng có thể là trang lỗi HTML từ proxy. HTTP status khác cũng không tự xác định nghiệp vụ thành công.

Envelope logging cho thấy SOAP `Fault` nếu message thực sự được tạo; transport-level logs mới cho biết HTTP status, response time, TCP/TLS lỗi. Do đó cần hai loại tín hiệu khi chẩn đoán tích hợp.

### 6.2. MTOM và MIME attachments

SOAP with Attachments hoặc MTOM/XOP có thể gửi dữ liệu nhị phân bằng MIME parts, trong khi XML Body chứa tham chiếu như `xop:Include` thay vì toàn bộ byte nhị phân. Logging Envelope:

- Không nhất thiết ghi được đầy đủ byte attachment.
- Có thể chứa metadata, content IDs hoặc tên file mang thông tin nhạy cảm.
- Nếu code cố chuyển attachment thành base64 hoặc đọc hết stream để ghi log, bộ nhớ và I/O có thể tăng mạnh.
- Không giúp xác minh MIME boundary, `Content-Type` hoặc tính nguyên vẹn file theo cách transport/attachment-specific.

Khi kiểm thử MTOM, nên dùng số liệu attachment count/size đã giới hạn, content ID được xử lý theo chính sách và kiểm tra riêng stream, MIME parser và WSDL/XSD binding.

### 6.3. SOAP Header và `mustUnderstand`

Một Header có `soap:mustUnderstand="1"` có thể khiến bên nhận phát `MustUnderstand` Fault nếu không có handler phù hợp. Envelope log giúp thấy QName, namespace và attribute có trong message **đã được parse**; nhưng việc Header được xử lý đúng phụ thuộc SOAP processor và WS-Security/WS-Addressing stack, không phải logger.

Dù log cho thấy đúng `wsse:Security`, không kết luận token hoặc chữ ký hợp lệ. Cần xem kết quả xác minh của security interceptor và chính sách certificate/trust tương ứng.

## 7. Rủi ro lớn nhất: Envelope có thể chứa dữ liệu nhạy cảm

Một request SOAP hợp lệ có thể chứa thông tin xác thực và dữ liệu nghiệp vụ nhạy cảm trong **cùng một Envelope**. Ghi toàn bộ Envelope nghĩa là có thể **chép dữ liệu đó vào logging backend**, nơi chính sách retention, quyền đọc và phạm vi phân phối khác với application database.

### 7.1. Các trường dữ liệu có nguy cơ bị lộ

| Thành phần | Ví dụ | Nguy cơ khi ghi Envelope |
| --- | --- | --- |
| `wsse:UsernameToken/wsse:Password` | PasswordText hoặc PasswordDigest. | Lộ credential hoặc dữ liệu hỗ trợ replay/phân tích offline. |
| `wsse:BinarySecurityToken` | Chứng chỉ X.509 được mã hóa. | Lộ thông tin định danh/certificate; không đồng nghĩa private key nằm trong message. |
| `ds:Signature` và các reference | Chữ ký XML, digest, KeyInfo. | Lộ metadata security, có thể hỗ trợ phân tích cấu trúc message. |
| SAML assertion hoặc token tùy chính sách | Subject/claims/conditions. | Lộ identity, role, tenant và thuộc tính nhạy cảm. |
| SOAP Body nghiệp vụ | Tên khách hàng, địa chỉ, số tài khoản, số tiền. | Lộ dữ liệu cá nhân/tài chính hoặc bí mật thương mại. |
| Correlation/trace header | Request ID, trace ID. | Cho phép liên kết nhiều log, có rủi ro truy vết trái phép nếu log không được phân quyền. |
| SOAP Fault detail | Lỗi ứng dụng, nội dung thông báo. | Có thể lộ stack trace hoặc cấu trúc nội bộ khi exception mapping không an toàn. |

Ví dụ **dữ liệu giả** để minh họa việc một Envelope có thể chứa Header bảo mật và Body nhạy cảm:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header>
    <wsse:Security>
      <wsse:UsernameToken>
        <wsse:Username>test-user</wsse:Username>
        <wsse:Password>NOT_A_REAL_PASSWORD</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Không copy thông điệp thực vào tài liệu, ticket, chat hay log để minh họa. Dùng dữ liệu giả rõ ràng; **không in password thật, access token, private key, dữ liệu thẻ hoặc thông tin khách hàng**.

### 7.2. Dùng TLS không bảo vệ nội dung đã ghi vào log

HTTPS/TLS bảo vệ dữ liệu **khi truyền giữa các điểm kết nối**. Sau khi application đọc Envelope và logger ghi XML vào file, stdout, collector hoặc hệ thống tập trung, dữ liệu trở thành bản sao mới với hệ thống phân quyền và retention riêng. Do đó:

- TLS của SOAP endpoint **không** mã hóa tự động từng dòng log ở nơi lưu trữ.
- mTLS/client certificate giúp xác thực peer, **không** biến log Envelope thành dữ liệu vô hại.
- WS-Security có thể bảo vệ message ở cấp XML, nhưng logger vẫn có thể ghi metadata hoặc plaintext ở một số giai đoạn xử lý.
- Chỉ có một `UsernameToken` hoặc token đã hash/digest trong log **vẫn là rủi ro**; không nên dựa vào việc nó “không phải password rõ”.

### 7.3. Ghi trước và sau WS-Security đều có trade-off

Nếu security interceptor **chưa xác minh** request, nội dung Envelope có thể do attacker điều khiển; giá trị bất thường và XML độc hại vẫn là nguồn dữ liệu log không tin cậy. Nếu interceptor **đã giải mã** một phần message, log ở giai đoạn đó có thể chứa dữ liệu nhạy cảm đã được giải mã (phụ thuộc stack/cách xử lý).

Không cố ép thứ tự để “log đủ trước khi xác minh” ở production. Thay vào đó, ưu tiên các sự kiện **security outcome** đã được phân loại, ví dụ `AUTH_FAILED`, `SIGNATURE_INVALID`, `TOKEN_EXPIRED`, correlation ID do server tạo và thông tin actor đã xác thực khi được phép. Không ghi nguyên token/certificate/private data.

### 7.4. Không sửa message đang được ký chỉ để redact log

XML Signature xác minh dữ liệu XML có tham chiếu rõ ràng và canonicalization. Nếu một interceptor xóa `wsse:Security` hoặc sửa Body **trực tiếp trên `SoapMessage`** trước khi xác minh, chữ ký có thể thất bại; tệ hơn, ứng dụng có thể xử lý dữ liệu khác với dữ liệu thực sự được xác minh.

Nếu bắt buộc ghi XML đã che dữ liệu:

1. Cân nhắc **không ghi XML**, chỉ ghi metadata (ưu tiên).
2. Nếu có yêu cầu chẩn đoán đặc biệt, tạo **bản sao để quan sát**, không thay đổi message nghiệp vụ.
3. Parse XML bản sao bằng parser an toàn; redact theo **QName/namespace và schema**, không regex thay chuỗi đơn giản.
4. Kiểm soát kích thước, quyền xem, thời gian sống, cơ chế mã hóa và audit việc truy cập bản ghi.
5. Kiểm thử rằng redaction không làm xuất hiện bản plaintext ở logger/trace khác và không làm thay đổi message gửi tới endpoint.

Một regex xóa chuỗi từ `<Password>` đến `</Password>` dễ thất bại khi namespace prefix, whitespace, thuộc tính hoặc serializer khác đi. Nó cũng có thể bỏ sót token trong `wsse:BinarySecurityToken`, `saml:Assertion` hay Body nghiệp vụ.

## 8. Cách ghi log an toàn hơn trong production

Đối với vận hành thường ngày, dữ liệu cần để truy vết thường là **metadata**, không phải toàn bộ XML. Một bản ghi phù hợp có thể gồm:

~~~text
timestamp=2026-11-27T03:00:00Z
service=orders-soap
operation=CreateOrder
soapVersion=1.1
correlationId=corr-27a
requestId=req-001
direction=inbound
outcome=VALIDATION_FAULT
durationMs=45
~~~

Các giá trị chỉ là ví dụ. Ở production, nên lấy `operation`, `correlationId` và `outcome` từ các nguồn đã được xác minh/chuẩn hóa; không log nguyên chuỗi người dùng gửi tùy ý mà không xử lý ký tự điều khiển và giới hạn kích thước.

### 8.1. Một custom EndpointInterceptor chỉ log metadata

Đoạn code sau minh họa cách đọc **SOAPAction** từ request SOAP, **correlation ID đã được interceptor trước đó kiểm tra** trong `MessageContext`, rồi log trạng thái thay vì serialize Envelope:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.SoapMessage;

public final class SoapMetadataLoggingInterceptor
        implements EndpointInterceptor {

    private static final Logger LOG =
        LoggerFactory.getLogger(SoapMetadataLoggingInterceptor.class);

    private static final String CORRELATION_KEY =
        "com.example.soap.correlationId";

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint) {
        SoapMessage request = (SoapMessage) context.getRequest();
        String correlationId =
            safeId(context.getProperty(CORRELATION_KEY));

        // Chỉ log sự hiện diện của SOAPAction; không in
        // raw dữ liệu header chưa được kiểm soát.
        LOG.info(
            "soap.in correlationId={} soapActionPresent={}",
            correlationId,
            request.getSoapAction() != null);
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {
        LOG.info("soap.out correlationId={} outcome=SUCCESS",
            safeId(context.getProperty(CORRELATION_KEY)));
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {
        LOG.warn("soap.out correlationId={} outcome=SOAP_FAULT",
            safeId(context.getProperty(CORRELATION_KEY)));
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        // Dọn MDC ở đúng lớp sở hữu MDC, nếu có.
    }

    private static String safeId(Object value) {
        if (!(value instanceof String id)) {
            return "-";
        }
        String clipped = id.substring(0, Math.min(id.length(), 64));
        return clipped.replaceAll("[^A-Za-z0-9._:-]", "_");
    }
}
~~~

Ví dụ cố ý **không** đọc `getPayloadSource()` để tìm QName: đọc payload có thể tiêu thụ stream hoặc tăng chi phí nếu Spring-WS message factory đang dùng cơ chế streaming. `correlationId` cần được cấp/validate bằng một interceptor hoặc gateway đáng tin trước khi log; nếu không có, log `-` và để thành phần được chỉ định sinh ID.

Đoạn này cũng không ghi toàn bộ HTTP status hay thời gian xử lý; chúng nên được đo ở lớp transport/metrics phù hợp, hoặc bằng timer bắt đầu/kết thúc có quản lý lifecycle. `handleFault` chỉ ghi những Fault đi qua callback tương ứng, không ghi lỗi trước SOAP parser.

### 8.2. Gắn correlation ID, request ID và trace ID đúng nghĩa

| Giá trị | Phạm vi | Nên làm gì khi log? |
| --- | --- | --- |
| `correlationId` | Chuỗi tác vụ hoặc workflow. | Giữ xuyên các SOAP hops nếu hợp đồng yêu cầu; validate trước khi lưu. |
| `requestId` | Một request inbound cụ thể. | Tạo/ghi riêng ở mỗi hop theo convention. |
| `wsa:MessageID` | Một SOAP message theo WS-Addressing. | Ghi khi được hỗ trợ và đã kiểm tra format/độ tin cậy. |
| `traceId`/`spanId` | Distributed tracing context. | Do tracing SDK/instrumentation quản lý, không tự chép như ID nghiệp vụ. |
| `idempotencyKey` | Một ý định tác vụ nghiệp vụ phải chống lặp. | Thường chỉ ghi dạng băm/định danh đã kiểm soát nếu nhạy cảm, không dùng làm credential. |

`MDC` của SLF4J có thể giúp gắn correlation ID vào log trong **cùng execution context**. Nhưng nó không tự truyền sang thread pool, asynchronous worker, message broker hoặc HTTP client; cần cơ chế propagation riêng. Đồng thời phải xóa/khôi phục MDC đúng lifecycle để request sau không thừa hưởng ID cũ.

### 8.3. Redaction và quyền truy cập log

Nếu có lý do kiểm toán bắt buộc phải lưu XML, cần chính sách rõ:

- Phân loại field/element nhạy cảm theo **XSD, namespace, SOAP Header và nghiệp vụ**.
- Chỉ ghi nội dung cần thiết, giới hạn dung lượng, số bản ghi và thời gian lưu.
- Sử dụng log destination được mã hóa và phân quyền; hạn chế exporter, sao chép sang ticket/chat và môi trường bên ngoài.
- Không ghi toàn bộ thông điệp từ traffic production khi chưa có cơ sở và phê duyệt phù hợp.
- Bổ sung cảnh báo nếu log volume tăng đột biến hoặc dòng log mang dữ liệu nhạy cảm không mong muốn.
- Kiểm tra cả đường exception/validator/security: dữ liệu có thể bị ghi trong stack traces hoặc debug logger khác ngoài interceptor của bạn.

**Không coi `SoapEnvelopeLoggingInterceptor` có sẵn là một cơ chế masking tự động.** Mặc định hãy xem nó như công cụ dump Envelope phục vụ chẩn đoán, và chỉ dùng nơi dữ liệu đầu vào là dữ liệu giả/đã được kiểm soát.

## 9. Chi phí hiệu năng và liên hệ với Axiom streaming

Ghi SOAP Envelope có thể cần **truy cập/serialize toàn bộ nội dung XML**, tạo String/byte buffers hoặc IO tới logging backend. Khi request lớn, concurrency cao hoặc interceptor log nhiều lần, việc này có thể ảnh hưởng đáng kể đến latency và heap.

### 9.1. SAAJ và Axiom có đặc tính khác nhau

| Message factory | Đặc điểm liên quan tới logging |
| --- | --- |
| `SaajSoapMessageFactory` | Biểu diễn cây SOAP/SAAJ thường thuận tiện cho đọc lại; việc log toàn Envelope vẫn có chi phí serialization/buffering. |
| `AxiomSoapMessageFactory` với `payloadCaching=true` | Có thể truy cập payload đã cache trong điều kiện version/runtime phù hợp; cần benchmark khi log toàn Envelope. |
| `AxiomSoapMessageFactory` với `payloadCaching=false` | **Không được giả định có thể đọc lại payload**; logger hoặc endpoint mapping/validation có thể tiêu thụ stream trước adapter. |

Theo tài liệu Axiom ở các phiên bản có hỗ trợ, `payloadCaching=false` khiến SOAP Body được đọc trực tiếp từ stream và chỉ đọc một lần; các thành phần như `PayloadRootAnnotationMethodEndpointMapping`, `PayloadValidatingInterceptor` và `PayloadLoggingInterceptor` có thể xung đột khi cùng đọc payload. **Envelope logging cũng phải được kiểm chứng như một consumer XML**, không được giả định an toàn với non-caching.

Ví dụ một request được log trước khi JAXB adapter unmarshal:

~~~text
Inbound HTTP stream
    → Axiom non-caching Body
    → Envelope logging đọc Body
    → JAXB endpoint cố đọc lại Body
    → có thể gặp payload rỗng / parser error
~~~

**Kết luận:** không bật Envelope logging và non-caching Axiom cùng nhau chỉ vì cả hai là tính năng hợp lệ theo API. Cần test toàn pipeline thực tế, và nếu logging chỉ để chẩn đoán thì ưu tiên giữ caching hoặc tắt dump XML.

### 9.2. Tại sao log bất đồng bộ vẫn có chi phí?

Asynchronous appender có thể giảm thời gian đợi ghi file/network ở request thread, nhưng:

- XML vẫn có thể phải được **serialize/tạo String trước** khi đưa vào queue.
- Queue có thể giữ nhiều bản sao Envelope trong heap.
- Khi log đột biến, queue có thể đầy, làm drop logs hoặc tạo backpressure tùy cấu hình.
- Dữ liệu nhạy cảm vẫn tồn tại trong buffer và log destination.

Không xem async logging là giải pháp cho memory exhaustion khi request SOAP lớn hoặc upload MTOM. Đặt request-size limits ở gateway/container/message factory theo phiên bản, giới hạn attachment và benchmark concurrency.

### 9.3. Chỉ số nên đo

Khi so sánh có/không có Envelope logging, giữ nguyên XSD/WSDL, payload sizes và các interceptor bảo mật. Đo:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Request latency p50/p95/p99 | Logger có làm tăng độ trễ cuối không? |
| Throughput | Số SOAP operations/giây. |
| Peak heap và allocation rate | Có tạo XML/String/DOM copies lớn không? |
| GC pause và CPU | Serialization/formatting có tạo áp lực không? |
| Log bytes/giây và queue depth | Logging backend có chịu nổi tải không? |
| SOAP Fault/error rate | Logging có thay đổi tính đúng do stream bị tiêu thụ không? |
| Time-to-first-byte của response | Serialization/logging có trì hoãn gửi response không? |
| Attachment memory/disk | MIME attachments có bị đọc/buffer ngoài ý muốn không? |

Nếu bật logging làm mất khả năng xử lý XSD validation hoặc WS-Security, cấu hình đó **không đạt yêu cầu** dù throughput/heap có vẻ tốt hơn trong benchmark.

## 10. Spring-WS MessageTracing và chẩn đoán phía client

Không phải mọi tình huống cần viết thêm interceptor. Spring-WS có cơ chế **message tracing** qua logging categories ở client/server trong các phiên bản hỗ trợ. Cần phân biệt chúng với `SoapEnvelopeLoggingInterceptor`.

### 10.1. MessageTracing hoạt động ở cấp nào?

Những logger category thường gặp trong các phiên bản Spring-WS hỗ trợ message tracing:

~~~text
org.springframework.ws.server.MessageTracing.received
org.springframework.ws.server.MessageTracing.sent
org.springframework.ws.client.MessageTracing.sent
org.springframework.ws.client.MessageTracing.received
~~~

Theo cấu hình/phiên bản, ở cấp log thấp hơn có thể thấy thông tin tóm tắt; ở cấp chi tiết như TRACE có thể thấy XML message đầy đủ. **Phải kiểm tra tài liệu và output thực tế theo version**, vì cấu trúc log, mức chi tiết, đường ghi và sự khác biệt giữa sent/received có thể thay đổi.

Ví dụ Spring Boot logging configuration **dành cho môi trường thử nghiệm có dữ liệu giả**:

~~~yaml
logging:
  level:
    org.springframework.ws.server.MessageTracing: DEBUG
    org.springframework.ws.client.MessageTracing: DEBUG
~~~

Không bật `TRACE` toàn bộ SOAP traffic ở production nếu chưa đánh giá dữ liệu được ghi, thời gian lưu và tải. Tùy backend, cần xác minh pattern/logger name thực tế và phần nào được ghi khi bật từng cấp.

### 10.2. MessageTracing không giống server EndpointInterceptor

| Khía cạnh | `SoapEnvelopeLoggingInterceptor` | `MessageTracing` |
| --- | --- | --- |
| Vị trí | Đường server endpoint interceptor. | Cơ chế logger/tracing message của Spring-WS client/server tùy version. |
| Điều kiện nhìn thấy request | Cần SOAP message và endpoint/interceptor pipeline chạy tới callback. | Có thể có phạm vi khác interceptor, phụ thuộc message sender/dispatcher. |
| Điều khiển | Đăng ký interceptor và cờ log request/response/fault. | Cấu hình logger category/cấp độ. |
| Ghi SOAP Header/Body | Mục tiêu là SOAP Envelope. | Phụ thuộc log level; có thể là tóm tắt hoặc chi tiết. |
| Dùng bên client | Không phải `ClientInterceptor`. | Có client logger categories riêng. |
| Rủi ro lộ dữ liệu | Rất cao khi ghi full Envelope. | Cũng rất cao khi bật full message tracing. |

Khi một SOAP client báo “server không nhận request”, có thể cần kiểm tra **cả hai phía**:

1. Client có gửi đúng WSDL binding/endpoint/SOAPAction không?
2. Request có qua TLS/proxy tới servlet không?
3. Server có parse được Envelope không?
4. EndpointMapping có chọn được handler không?
5. Validator/security có tạo SOAP Fault không?
6. Client có nhận được response và unmarshal đúng XSD không?

Chỉ xem server Envelope interceptor không thể xác nhận đầy đủ bước 1 hoặc các lỗi diễn ra trước khi endpoint mapping.

### 10.3. `WebServiceTemplate` có các interceptor của client riêng

Một ứng dụng Spring-WS tạo SOAP client thường dùng `WebServiceTemplate` với `Jaxb2Marshaller` hoặc `Source`. `WebServiceTemplate` có thể đăng ký **`ClientInterceptor`**, tách biệt với `EndpointInterceptor` ở server.

~~~text
Client:
  JAXB / XML Source
    → WebServiceTemplate
    → ClientInterceptor(s)
    → HTTP message sender / TLS
    → SOAP endpoint

Server:
  HTTP servlet / SOAP message factory
    → EndpointMapping
    → EndpointInterceptor(s)
    → @Endpoint
~~~

Nếu muốn đọc đầy đủ request/response ở **client**, hãy sử dụng MessageTracing/client interceptor phù hợp hoặc công cụ test transport trong môi trường có dữ liệu giả; đừng ép class `SoapEnvelopeLoggingInterceptor` vào client stack khi nó không có giao diện phù hợp.

Khi chẩn đoán lỗi client, ghi metadata từ exception:

- SOAP Fault code/reason/detail đã được phép chia sẻ.
- Endpoint URI được cấu hình, SOAPAction/binding nếu không nhạy cảm.
- Correlation ID, request ID, trace ID đã được kiểm tra.
- Loại lỗi: transport, TLS, timeout, validation, unmarshalling hay SOAP Fault.

Không in raw SOAP Body chứa dữ liệu thực chỉ vì client không unmarshal được một response.

## 11. Cách kiểm thử logging interceptor mà không cần hệ thống thật

Mục tiêu kiểm thử là xác minh **interceptor được kích hoạt và ghi đúng loại message**, đồng thời không gây tác dụng phụ lên SOAP processing.

### 11.1. Kiểm tra bằng `MockWebServiceClient`

Spring-WS Test hỗ trợ `MockWebServiceClient` để gửi payload tới endpoint trong Spring ApplicationContext test. Ví dụ rút gọn:

~~~java
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;

// applicationContext có endpoint, endpoint adapter, mapping,
// interceptor và service test tương ứng.
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

String xml =
    "<ord:CreateOrderRequest " +
    "xmlns:ord=\"urn:example:orders:v1\">" +
    "<ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>" +
    "<ord:amount>1250000.00</ord:amount>" +
    "<ord:currency>VND</ord:currency>" +
    "</ord:CreateOrderRequest>";

client.sendRequest(withPayload(new StringSource(xml)))
      .andExpect(noFault());
~~~

Ví dụ giả định test ApplicationContext, XSD/JAXB model, service nghiệp vụ và interceptor đã được cấu hình đầy đủ; nó **không phải test độc lập có thể chạy ngay**. `noFault()` chỉ kiểm tra không nhận Fault, chưa xác nhận payload response chính xác. Trong test thật, bổ sung assertion XML response theo QName, dữ liệu, schema và các trường hợp exception.

Để kiểm tra bản ghi log của interceptor, có thể dùng một **in-memory test appender** được cung cấp bởi logging backend, hoặc kỹ thuật capture logs được team chuẩn hóa. Kiểm tra thông tin có xuất hiện trong môi trường test mà **không phải tạo thêm file log chứa PII**.

### 11.2. Ma trận kiểm thử đề xuất

| Ca kiểm thử | Dữ liệu/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Success request/response | SOAP 1.1 đúng QName, Body hợp lệ. | Endpoint chạy; request/response được ghi khi cờ và logger cho phép. |
| Tắt `logRequest` | Request hợp lệ. | Không ghi Envelope request bởi interceptor này. |
| Tắt `logResponse` | Response thành công. | Không ghi Envelope response bởi interceptor này. |
| Bật `logFault` | Endpoint/validator tạo SOAP Fault. | Ghi Fault nếu callback `handleFault` được gọi. |
| SOAP Header custom | Có `CorrelationId`. | Envelope log cho thấy Header ở mức debug, metadata service đúng. |
| SOAP Header WS-Security | Dữ liệu **giả**, không có credential thật. | Test phát hiện/giới hạn log secrets theo policy. |
| Prefix khác | XML đổi `ord` thành `x` nhưng cùng namespace. | Handler/response vẫn đúng QName; không snapshot test phụ thuộc prefix. |
| Header trùng/sai namespace | Dữ liệu invalid. | Interceptor xử lý theo contract; logging không biến request thành hợp lệ. |
| Body sai XSD | Sai `xs:sequence` hoặc `xs:pattern`. | Validator từ chối, Fault đúng; log nếu pipeline cho phép. |
| SOAP 1.2 | Envelope đúng namespace SOAP 1.2. | Chỉ chạy nếu binding/factory hỗ trợ; log và Fault theo version. |
| Không tìm thấy endpoint | Root QName không khớp `@PayloadRoot`. | Có thể không thấy endpoint interceptor log; kiểm tra mapping/tracing. |
| XML malformed | Parser không dựng được message. | Có thể không có interceptor log; không crash logging backend. |
| Axiom non-caching | Pipeline dùng đọc stream một lần. | Không để logging làm mất payload trước endpoint; giữ caching hoặc đổi thiết kế. |
| Concurrent requests | Nhiều correlation IDs đồng thời. | Log metadata không trộn ID, không dùng field mutable. |
| Attachment lớn | MTOM/MIME test data được phép. | Không dump byte nhị phân ngoài ý muốn, bộ nhớ/đĩa trong giới hạn. |
| Profile debug không bật | Môi trường production-like. | Không có Envelope interceptor; không ghi raw SOAP XML. |

**Đừng viết assertion “log phải chứa chính xác XML String ban đầu”**: khi SOAP message factory parse/serialize lại, prefix, thứ tự thuộc tính và whitespace có thể thay đổi. Assertion nên tập trung vào việc log đúng loại event, thông tin cần thiết, không ghi secret và không ảnh hưởng response.

### 11.3. Kiểm tra end-to-end bằng HTTP

Khi ứng dụng thử nghiệm chạy ở `http://localhost:8080/ws` và WSDL xác nhận SOAP 1.1, lưu SOAP Envelope sau vào `request.xml` dưới mã hóa UTF-8:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1"
    xmlns:ctx="urn:example:context:v1">
  <soap:Header>
    <ctx:CorrelationId>corr-test-27a</ctx:CorrelationId>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
      <ord:currency>VND</ord:currency>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Trong PowerShell, có thể gửi:

~~~powershell
curl.exe --include --request POST --header 'Content-Type: text/xml; charset=utf-8' --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' --data-binary '@request.xml' "http://localhost:8080/ws"
~~~

`SOAPAction` và địa chỉ SOAP trong ví dụ là **giả định**; phải kiểm tra `soap:operation` và `soap:address` từ WSDL thực tế. Không gửi dữ liệu thật hoặc thông tin xác thực thật khi debug Envelope logging.

Kiểm tra **ba đầu ra riêng biệt**:

1. HTTP status và response Envelope client nhận.
2. Log của Spring-WS có/không có Envelope theo cờ log và profile/cấp logger.
3. Hành vi endpoint/XSD validation/security vẫn đúng như khi không bật logging.

Nếu response lỗi chứa SOAP Fault, xem cả Fault XML và exception mapping; nếu chỉ nhận HTML từ gateway, Envelope interceptor có thể hoàn toàn không chạy.

## 12. Hướng dẫn chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Phép kiểm ưu tiên |
| --- | --- | --- |
| Bật bean nhưng không có log | Profile chưa active, logger level thấp, config `WsConfigurer` chưa được áp dụng. | Kiểm tra bean/profile, logging category, request đi qua servlet. |
| Chỉ thấy request, không thấy response | `logResponse` tắt, Fault thay success, endpoint lỗi hoặc không có response. | Xem `handleFault`, exception resolver và HTTP response. |
| Không thấy Fault | `logFault` tắt, lỗi nằm ngoài SOAP pipeline hoặc interceptor không được gọi. | Kiểm tra transport logs, XML parser, Fault resolver. |
| Ghi XML không có HTTP headers | Envelope logger không ghi raw HTTP metadata. | Dùng access log, message sender/gateway tracing có kiểm soát. |
| Không thấy `wsse:Security` | Client không gửi, header được xử lý ở nơi khác, hoặc log thuộc payload-only. | Xem cách tạo client, đúng loại logger, thứ tự security. |
| Có Header nhưng SOAP Fault `MustUnderstand` | Recipient không xử lý Header bắt buộc. | So QName, role/actor, mustUnderstand và registered processors. |
| WSDL GET thành công, không có log khi GET | Interceptor chạy trên SOAP endpoint dispatch, không phải WSDL GET. | Phân biệt GET hợp đồng và POST SOAP. |
| Body log bị rỗng khi Axiom streaming | Payload đã bị consumer khác đọc; `payloadCaching=false`. | Kiểm tra message factory, mapping/validation/logging chain. |
| Log mất một số attachment | Envelope XML không bao gồm đủ MIME binary parts. | Dùng attachment diagnostics, không dump full binaries. |
| Latency tăng khi bật log | XML serialization, String buffer, I/O/appender backlog. | Benchmark heap, GC, p95/p99, queue, log bytes. |
| Logger tạo quá nhiều log duplicate | Bật cả MessageTracing, PayloadLogging và Envelope logging. | Chọn một cơ chế phù hợp mục tiêu, giảm phạm vi debug. |
| Log chứa secrets | Dump toàn Envelope, thiếu masking/policy. | Tắt ngay nơi không được phép, xử lý sự cố dữ liệu, đổi strategy sang metadata. |
| Correlation IDs trộn giữa request | Giữ ID ở singleton field hoặc MDC không cleanup. | Dùng `MessageContext`/scope và dọn context đúng. |

### 12.1. Quy trình debug có thứ tự

1. Kiểm tra URL SOAP thật từ `soap:address`, HTTP status và SOAP version trong WSDL.
2. Xác minh profile/debug config và logger category của interceptor.
3. Xem client có gửi request qua gateway/servlet không.
4. Đối chiếu XML Envelope, namespace và `@PayloadRoot`; nhớ rằng không match endpoint có thể không đi qua interceptor.
5. Xem các interceptor validation/security, thứ tự, kết quả `handleRequest` và Fault resolver.
6. Nếu response đã tạo, kiểm tra SOAP Body hoặc Fault và correlation ID.
7. Nếu bật Axiom/streaming, xác nhận không có bước log làm tiêu thụ payload trước JAXB.
8. Nếu cần debug transport/TLS hoặc MIME attachment, dùng công cụ riêng với dữ liệu giả và quyền phù hợp.

Một lỗi thường gặp là thấy “server không có Envelope log” rồi lập tức kết luận **client chưa gửi HTTP request**. Kết luận đó chưa đủ cơ sở: request có thể đã bị loại tại proxy, parser, servlet mapping hoặc endpoint mapping trước khi interceptor được gọi.

## 13. Bài tập tình huống

### Tình huống A — Header WS-Security bị thiếu

Client gửi SOAP Body `CreateOrderRequest` đúng XSD, nhưng server trả SOAP Fault vì không tìm thấy UsernameToken. Nhóm phát triển đang bật `PayloadLoggingInterceptor` và chỉ thấy Body.

**Đáp án gợi ý:** `PayloadLoggingInterceptor` không phải nơi quan sát toàn Header. Dùng metadata/security outcome trước; nếu cần, bật Envelope logging trong môi trường test với token giả để kiểm tra Header được tạo và có đúng QName hay không. Không bật full Envelope logging trên production traffic có thông tin đăng nhập thật.

### Tình huống B — Interceptor không ghi request sai namespace

Client gửi `{urn:example:orders:v2}CreateOrderRequest` trong khi chỉ có endpoint mapping v1. HTTP transport thấy POST, nhưng `SoapEnvelopeLoggingInterceptor` không ghi XML.

**Đáp án:** interceptor thuộc pipeline endpoint; nếu mapping thất bại trước đó, callback có thể không được gọi. Kiểm tra endpoint mapping logs/message tracing ở môi trường phù hợp và raw XML test để xác nhận namespace.

### Tình huống C — SOAP Fault được trả, không có response log success

Business service ném exception; server tạo `soap:Fault`. Có `handleFault` nhưng không chạy `handleResponse`.

**Đáp án:** kiểm tra `setLogFault(true)` và logging backend. Không giả định mọi Fault sẽ xuất hiện dưới cùng kênh response success. Nếu lỗi xảy ra trước khi SOAP message được tạo, có thể không có Fault log.

### Tình huống D — Ghi Envelope làm lỗi JAXB khi Axiom không cache

Ứng dụng dùng `AxiomSoapMessageFactory#setPayloadCaching(false)`, routing theo SOAPAction. Trước khi bật logger, JAXB endpoint hoạt động. Sau khi bật logger, unmarshaller báo không còn payload.

**Đáp án:** Envelope logging có thể đã tiêu thụ stream. Tắt full Envelope log hoặc giữ caching/đổi kiến trúc để các consumer không đọc lại; không tắt XSD validation và WS-Security chỉ để log vẫn hoạt động. Test lại cả request, response và Fault.

### Tình huống E — Audit yêu cầu log toàn bộ SOAP Body của thanh toán

Nhóm vận hành muốn lưu Body cùng WS-Security Header trong log tập trung để thuận tiện tìm lỗi.

**Đáp án:** cần đánh giá policy dữ liệu và bảo mật trước; không coi “log đầy đủ” là lựa chọn mặc định. Thông thường có thể lưu metadata như correlation ID, operation, outcome, Fault category và mã giao dịch đã được che. Nếu thật sự bắt buộc lưu dữ liệu XML, phải có chính sách redaction theo QName, mã hóa, retention, quyền truy cập, giới hạn volume và audit. Không biến log backend thành nơi lưu credentials hoặc dữ liệu nhạy cảm ngoài kiểm soát.

## 14. Quyết định bật logging ở từng môi trường

Nhu cầu debug trong local, test tích hợp, staging và production không giống nhau. Một chính sách rõ giúp tránh việc dùng cấu hình phục vụ phát triển làm mặc định cho dịch vụ doanh nghiệp.

| Môi trường | Cách ghi nên ưu tiên | Khi nào cân nhắc Envelope log? |
| --- | --- | --- |
| Local với XML tự tạo | Payload XML/Envelope đầy đủ khi cần. | Có thể bật profile riêng; chỉ dùng dữ liệu giả. |
| Integration test/CI | Test assertions, metadata và capture có giới hạn. | Bật trong một số test khi kiểm tra Header, Fault, namespace. |
| Staging | Metadata có cấu trúc, correlation/trace IDs, security outcomes. | Chỉ khi được cho phép, dữ liệu đã thay thế/che và thời gian ngắn. |
| Production | Request/trace ID, operation, latency, outcome, Fault category. | Ngoại lệ cần phê duyệt, giới hạn phạm vi, audit quyền truy cập và retention. |
| Sự cố bảo mật | Security events đã phân loại, thông tin được phép chia sẻ. | Không bật full dump một cách phản xạ; tuân thủ quy trình ứng phó sự cố. |

Trong production, **bật logging có thể là một thay đổi vận hành nhạy cảm**. Nó không chỉ thay log level mà còn thay đổi lượng dữ liệu được thu thập, số bản sao được giữ và chi phí tài nguyên.

### 14.1. Checklist bật debug an toàn

Trước khi bật `SoapEnvelopeLoggingInterceptor`:

1. Xác nhận có **mục tiêu kỹ thuật cụ thể**, ví dụ kiểm tra QName SOAP Header trên một contract test.
2. Đảm bảo môi trường dùng **dữ liệu giả hoặc dữ liệu đã được phép**. Không mang credential thật vào fixture.
3. Kiểm tra phiên bản Spring-WS hỗ trợ class, setter và message factory đang dùng.
4. Bật bằng profile/config flag có phạm vi rõ, **mặc định tắt**.
5. Xác định logger category, level, appender, destination và quyền đọc log.
6. Nếu có WS-Security, kiểm tra nguy cơ lộ UsernameToken, BinarySecurityToken, assertion, chữ ký và plaintext.
7. Đặt giới hạn request/attachment size, timeout và số lượng log nếu cần.
8. Xác nhận không phá XSD validation, SOAP Fault handling, JAXB và Axiom streaming.
9. Giữ correlation ID và điều tra kết quả qua **log đã lọc**, không cần lưu một bản SOAP XML vô hạn.
10. Có kế hoạch **tắt debug và xử lý bản ghi đã tạo** sau khi chẩn đoán.

Khi không cần toàn Envelope, ưu tiên log metadata, hoặc chỉ dùng test assertion trên phần XML được chọn. **Không tạo cơ chế debug mà chỉ có cách bật, không có cách tắt/cleanup**.

### 14.2. Checklist kiểm thử khi tắt logger

Sau khi debug xong, cần xác nhận:

- Profile `soap-envelope-debug` không còn active ở môi trường mục tiêu.
- Bean `SoapEnvelopeLoggingInterceptor` không còn được đăng ký hoặc các flag/log level đã tắt theo policy.
- MessageTracing TRACE hoặc các transport raw-body loggers khác cũng không đang ghi toàn bộ message.
- Ứng dụng vẫn xử lý request thành công, SOAP Fault và WS-Security như trước.
- Không còn log pipeline/sidecar/gateway khác sao chép Envelope ngoài phạm vi dự kiến.
- Các log đã tạo được quản lý theo retention và quy trình xử lý dữ liệu đã quy định.

## 15. Mini case study: sự cố thanh toán sau khi thêm correlation header

Một dịch vụ Spring-WS `OrdersService` đã hoạt động với SOAP 1.1. Sau khi thêm custom `CorrelationId` vào SOAP Header, một client .NET báo SOAP Fault `MustUnderstand`. Đội phát triển định bật `SoapEnvelopeLoggingInterceptor` ở production để xem mọi request. Hãy phân tích lần lượt:

**Bước 1 — Đặt giả thuyết.** Header có thể có `soap:mustUnderstand="1"` nhưng phía nhận không có processor hỗ trợ QName/role. Hoặc WSDL và runtime không cùng hợp đồng. `CorrelationId` chỉ dùng theo dõi mà chưa chắc cần `mustUnderstand`.

**Bước 2 — Tái hiện bằng dữ liệu giả.** Trên integration environment, gửi hai request cùng payload nhưng một bản có correlation header đúng QName/không `mustUnderstand` và bản còn lại đánh dấu mustUnderstand. Xác minh Fault code, Header trong Envelope, endpoint mapping và thứ tự interceptor.

**Bước 3 — Chọn công cụ.** Bật Envelope logging trong profile test nếu cần quan sát Header. Song song, kiểm tra WSDL `soap:header`, WS-Addressing/WS-Security policy và SOAP processor. Không in header có token thật.

**Bước 4 — Sửa theo hợp đồng.** Nếu correlation header không bắt buộc theo SOAP processing semantics, điều chỉnh cách tạo Header phù hợp và cập nhật thỏa thuận đối tác. Nếu bắt buộc, triển khai processor và khả năng đáp ứng `mustUnderstand` trên cả các phía theo contract.

**Bước 5 — Kiểm thử hồi quy.** Test request/response thành công, Fault khi header sai, response correlation, WS-Security, client .NET và Java; sau đó tắt profile Envelope logging và giữ metadata logs.

Một vấn đề **phong bì SOAP** đã được giải quyết qua kiểm tra QName/role/contract; logging chỉ là công cụ quan sát, không phải cơ chế thực thi quy tắc của SOAP.

## 16. Câu hỏi ôn tập

1. `SoapEnvelopeLoggingInterceptor` khác `PayloadLoggingInterceptor` về phạm vi ghi như thế nào?
2. Tại sao một request có HTTP access log nhưng không có log từ `SoapEnvelopeLoggingInterceptor`?
3. Callback `handleResponse` và `handleFault` phục vụ những đường xử lý nào?
4. SOAP Envelope log có cung cấp toàn bộ HTTP headers và MIME attachment bytes không? Vì sao?
5. Vì sao `wsse:PasswordDigest`, `BinarySecurityToken` và SAML assertion vẫn là dữ liệu cần bảo vệ?
6. Tại sao không được sửa `SoapMessage` đã ký để che dữ liệu trước khi logging?
7. Khi dùng Axiom `payloadCaching=false`, Envelope logging có thể gây lỗi gì cho adapter JAXB?
8. Tại sao bật async appender không tự giải quyết vấn đề heap và PII?
9. `MessageTracing` của Spring-WS khác một server `EndpointInterceptor` ở những điểm nào?
10. Khi nào metadata log với correlation ID, SOAPAction presence và Fault category tốt hơn full XML dump?
11. Một HTTP 502 từ proxy có được bảo đảm xuất hiện trong `handleFault` không?
12. Khi triển khai contract-first, cần test gì để chắc rằng việc logging không làm thay đổi behavior của XSD validation và WS-Security?

## 17. Checklist cuối bài

| Câu hỏi | Dấu hiệu đã đạt |
| --- | --- |
| Xác định đúng công cụ? | Chọn Envelope log chỉ khi cần SOAP Header + Body, không nhầm với payload-only hoặc HTTP transport. |
| Interceptor thuộc đúng phía? | `SoapEnvelopeLoggingInterceptor` ở server `EndpointInterceptor`; client dùng cơ chế phù hợp riêng. |
| Có biết điểm chạy trong pipeline? | Hiểu parser, endpoint mapping, validation/security và callback có thể ngăn interceptor được gọi. |
| Request/response/Fault được cấu hình? | Các flag và logger level khớp nhu cầu, kiểm tra thực tế. |
| Profile debug an toàn? | Mặc định tắt, chỉ bật trong môi trường/phạm vi được phép. |
| XSD/WSDL không bị thay đổi? | Logging không tự sửa QName, operation, binding, Header hoặc Body. |
| Tránh ghi credentials? | Không lưu WS-Security tokens, private data, PII theo policy. |
| Không phá chữ ký XML? | Không mutate signed content để redact; kiểm tra security stack độc lập. |
| Có correlation/trace metadata? | Ghi ID đã kiểm tra, không dựa vào raw XML để truy vết mọi request. |
| Có giới hạn tài nguyên? | Request/attachment size, log volume, queue, heap và retention được kiểm soát. |
| Streaming có tương thích? | Không để logger tiêu thụ payload khi dùng Axiom non-caching. |
| SOAP Fault được phân loại đúng? | Phân biệt Fault message với HTTP/TLS/proxy failures. |
| Test đầy đủ? | Test success, Fault, invalid XML, missing endpoint, SOAP versions, security, concurrency. |
| Có cách tắt debug? | Kiểm tra sau triển khai và xử lý log đã tạo theo retention. |

### Ghi nhớ

- **`SoapEnvelopeLoggingInterceptor` ghi SOAP Envelope ở phía server** khi request, response hoặc Fault đi qua các callback phù hợp. Envelope gồm **SOAP Header + Body**; nó không tương đương raw HTTP request hoặc toàn bộ MIME attachment.
- **`PayloadLoggingInterceptor` chỉ tập trung payload**, còn `MessageTracing` và client/transport tracing là cơ chế khác. Chọn theo mục tiêu chẩn đoán thay vì bật tất cả.
- **Không thấy Envelope log không chứng minh client chưa gửi request**: request có thể thất bại trước endpoint mapping hoặc ở proxy/parser.
- **Full Envelope logging có rủi ro bảo mật lớn**: WS-Security Header, dữ liệu nghiệp vụ và Fault detail có thể chứa secrets hoặc PII. Ưu tiên metadata logging có cấu trúc trong production.
- **Logging không tự validate XSD, xác minh WS-Security hay sửa SOAP Fault**. Các nhiệm vụ đó thuộc validator, interceptor bảo mật, exception resolver và SOAP runtime.
- **Axiom streaming và logging phải được kiểm thử chung**: một bước đọc/serialize Envelope có thể tiêu thụ stream trước JAXB adapter hoặc gây thêm chi phí bộ nhớ.
- **Một quy trình tích hợp Spring-WS ổn định** kiểm thử cả WSDL/XSD, JAXB endpoint/client, SOAP Envelope, Header, interceptor, WS-Security, SOAP Fault và HTTP transport, đồng thời tắt việc ghi raw message sau khi chẩn đoán.





