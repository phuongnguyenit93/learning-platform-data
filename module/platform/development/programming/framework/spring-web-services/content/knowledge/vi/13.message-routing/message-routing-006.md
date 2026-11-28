# Không có endpoint phù hợp, cấu hình trùng và chẩn đoán định tuyến

Một lỗi thường gặp khi xây dựng dịch vụ SOAP bằng **Spring Web Services (Spring-WS)** là client gửi request đến đúng URL, thậm chí tải được WSDL, nhưng server vẫn ghi log tương tự **“No endpoint mapping found”**. Ở trường hợp khác, sau khi bổ sung endpoint mới, ứng dụng báo ánh xạ trùng, khởi động lỗi hoặc request đi vào handler không như dự kiến.

Hai hiện tượng này không nhất thiết do XSD, JAXB hay nghiệp vụ sai. Chúng thường xuất hiện ở **lớp định tuyến thông điệp**: request đã đi đến đâu, Spring-WS dùng thông tin nào để chọn endpoint, có bao nhiêu mapping đang cạnh tranh và thành phần nào thực sự tiếp nhận method được chọn?

Bài học thuộc chương **Định tuyến thông điệp** của module **SPRING_WEB_SERVICES**. Trong toàn module, hợp đồng SOAP được xây dựng theo hướng **contract-first** với XSD/WSDL; JAXB ánh xạ XML sang Java; `@Endpoint` thực thi nghiệp vụ; SOAP client, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích giúp tích hợp hệ thống doanh nghiệp ổn định. Ở đây, trọng tâm là **không có endpoint phù hợp, cấu hình định tuyến trùng và cách chẩn đoán có hệ thống**, thay vì thử sửa annotation hay WSDL một cách mò mẫm.

## 1. Định tuyến SOAP là một chuỗi quyết định, không phải một lần tìm URL

Giả sử hệ thống công bố:

~~~text
WSDL công khai:  https://api.example.org/soap/orders.wsdl
SOAP endpoint:   https://api.example.org/soap
Backend servlet: http://orders-app:8080/ws
Payload QName:   {urn:example:orders:v1}GetOrderRequest
~~~

Một request thành công phải vượt qua các chặng sau:

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["Gateway / reverse proxy<br/>URL, TLS, HTTP method"]
    B --> C["MessageDispatcherServlet<br/>servlet mapping /ws/*"]
    C --> D["WebServiceMessageFactory<br/>SOAP Envelope + Body"]
    D --> E["EndpointMapping<br/>QName / SOAPAction / strategy"]
    E --> F["EndpointAdapter<br/>tham số @RequestPayload"]
    F --> G["@Endpoint method<br/>application service"]
    G --> H["Marshalling response<br/>hoặc SOAP Fault"]
    H --> I["HTTP/SOAP response tới client"]
~~~

| Tầng | Câu hỏi | Một lỗi tiêu biểu |
| --- | --- | --- |
| **Gateway/transport** | URL, method, TLS và đường dẫn nội bộ đúng không? | HTTP 404 từ proxy, TLS handshake fail |
| **Message factory** | SOAP version, Content-Type và Envelope parse được không? | SOAP 1.1/1.2 không khớp, XML hỏng |
| **Endpoint mapping** | Payload QName hoặc action có khớp một handler không? | Không có mapping, hoặc mapping cạnh tranh |
| **Endpoint adapter** | Method được chọn có tham số/kiểu trả về được hỗ trợ không? | Không có adapter phù hợp, JAXB type không hỗ trợ |
| **Interceptor/security** | Request có vượt qua validation, chữ ký, token và chính sách không? | Bị từ chối trước khi endpoint thực thi |
| **Endpoint/nghiệp vụ** | Handler có xử lý thành công không? | Exception, SOAP Fault, response sai schema |

**Nguyên tắc đầu tiên:** không được quy tất cả HTTP 404/500 hoặc SOAP Fault thành lỗi `@PayloadRoot`. Phải xác định **tầng đầu tiên đã thất bại**.

## 2. `@PayloadRoot` định tuyến theo QName, không theo tên class hay URL

Trong Spring-WS, một cơ chế phổ biến là `PayloadRootAnnotationMethodEndpointMapping`, ánh xạ method được đánh dấu `@PayloadRoot` theo tên mở rộng (**QName**) của phần tử gốc payload trong SOAP Body.

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";
    private final OrderService service;

    public OrderEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        OrderStatusType status = service.findStatus(request.getOrderId());
        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(request.getOrderId());
        response.setStatus(status);
        return response;
    }
}
~~~

Ví dụ giả định `GetOrderRequest`, `GetOrderResponse` và `OrderStatusType` đã được sinh từ XSD, `OrderService` đã được triển khai, và Spring-WS đã bật các endpoint adapter/JAXB binding tương ứng. Không dùng đoạn mã minh họa để suy ra mọi class XJC đều có `@XmlRootElement`: cách ánh xạ còn phụ thuộc schema và toolchain.

Request phù hợp:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Header/>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1024</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

QName dùng để ánh xạ: `{urn:example:orders:v1}GetOrderRequest`.

### 2.1. Prefix không quyết định mapping

XML sau đây vẫn mang **cùng QName**:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>ORD-1024</o:orderId>
</o:GetOrderRequest>
~~~

Nhưng những trường hợp dưới đây **khác QName**:

~~~xml
<!-- Khác namespace URI -->
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v2"/>

<!-- Khác local name vì XML phân biệt chữ hoa/chữ thường -->
<ord:getOrderRequest xmlns:ord="urn:example:orders:v1"/>

<!-- Không namespace, dù tên nhìn giống -->
<GetOrderRequest/>
~~~

**Không sửa `@PayloadRoot` để khớp prefix hiển thị trong XML.** Prefix là bí danh; điều cần so sánh là **namespace URI chính xác** và **local name chính xác**. Việc đổi namespace v1 sang v2 là thay đổi danh tính hợp đồng, có thể ảnh hưởng cả WSDL, JAXB và client.

### 2.2. Chỉ xét phần tử gốc payload, không nhầm với SOAP Header

`@PayloadRoot` thường định tuyến theo phần tử gốc **bên trong SOAP Body**. Nó không lấy:

- Tên `soapenv:Envelope` hoặc `soapenv:Body`.
- SOAP Header chứa `CorrelationId` hoặc `wsse:Security`.
- Tên Java class hay tên method `getOrder`.
- Tên WSDL `portType` hoặc `operation` bằng cách so chuỗi tự động.
- URL `/ws` hay URL `orders.wsdl`.

WSDL và XSD giúp xác định element root hợp đồng; các annotation trong Spring-WS phải thống nhất với QName root mà SOAP client gửi thực tế.

## 3. Ví dụ contract-first: từ XSD/WSDL đến routing key

Một XSD rút gọn cho truy vấn đơn hàng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="CONFIRMED"/>
            <xs:enumeration value="CANCELLED"/>
        </xs:restriction>
    </xs:simpleType>

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
                <xs:element name="status" type="ord:OrderStatusType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Với WSDL 1.1 ở dạng document/literal, `wsdl:part` có thể tham chiếu phần tử toàn cục:

~~~xml
<!-- Trích đoạn WSDL; wsdl/ord/tns đã được khai báo ở definitions. -->
<wsdl:message name="GetOrderInput">
    <wsdl:part name="parameters" element="ord:GetOrderRequest"/>
</wsdl:message>
<wsdl:message name="GetOrderOutput">
    <wsdl:part name="parameters" element="ord:GetOrderResponse"/>
</wsdl:message>
<wsdl:portType name="OrdersPortType">
    <wsdl:operation name="GetOrder">
        <wsdl:input message="tns:GetOrderInput"/>
        <wsdl:output message="tns:GetOrderOutput"/>
    </wsdl:operation>
</wsdl:portType>
~~~

Ở đây `GetOrder` là **tên WSDL operation**, còn `GetOrderRequest` là **tên root payload**. Với `@PayloadRoot`, Spring-WS dùng `GetOrderRequest` cùng namespace của nó, không suy ngược tên method `getOrder` từ `wsdl:operation`.

Ngoài `portType` và `message`, WSDL công bố thực tế còn cần `binding`, `service` và `port` phù hợp SOAP 1.1/1.2, `soap:address` truy cập được và các XSD import/include có thể resolve. Một WSDL hợp cú pháp nhưng trỏ vào backend sai vẫn khiến client thất bại **trước khi** đến định tuyến endpoint.

## 4. Khi không có endpoint phù hợp, hệ thống có thể đã thất bại ở đâu?

Thông báo như **“No endpoint mapping found for [...]”** có giá trị vì nó thường cho biết Spring-WS đã tiến tới giai đoạn tìm handler nhưng **không tìm thấy mapping tương ứng trong cấu hình hiện tại**. Tuy nhiên, tình trạng client thấy HTTP status gì còn phụ thuộc phiên bản Spring-WS, message receiver, SOAP binding và cấu hình xử lý lỗi; không thể luôn khẳng định “no endpoint” sẽ tự sinh một SOAP Fault cụ thể.

### 4.1. Request chưa tới Spring-WS

Ví dụ:

~~~text
Client POST https://api.example.org/soap
Proxy chuyển sai thành /orders
MessageDispatcherServlet chỉ map /ws/*
→ request không vào SOAP servlet.
~~~

Triệu chứng có thể là HTTP 404 của gateway/container hoặc một servlet khác nhận request. **Không sửa `@PayloadRoot`** ở trường hợp này. Hãy xác minh URL công khai → proxy rewrite → servlet mapping.

### 4.2. SOAP parse không thành công

Client gửi SOAP 1.2 Envelope với header SOAP 1.1 không tương thích, gửi JSON thay cho XML, hoặc gửi Envelope XML sai cú pháp. Message factory có thể từ chối trước khi endpoint mapping nhận được một root payload hợp lệ.

Kiểm tra **`Content-Type`**, SOAP Envelope namespace, encoding và trạng thái HTTP/SOAP Fault của request thực tế. Đổi annotation mapping không sửa được XML hỏng.

### 4.3. Payload QName khác cấu hình

`@PayloadRoot` khai báo:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest")
~~~

Client lại gửi:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v2">
    <ord:orderId>ORD-1024</ord:orderId>
</ord:GetOrderRequest>
~~~

Local name đúng, nhưng URI namespace v2 khác v1. Từ góc nhìn QName, **đây là operation payload khác**. Giải pháp có thể là sửa client gửi đúng contract v1, hoặc chủ đích phát hành v2 bằng endpoint/schema mới; không âm thầm chấp nhận hai namespace mà chưa đánh giá tương thích.

### 4.4. Endpoint bean không có trong application context

Một class có `@Endpoint` vẫn có thể không được Spring quản lý nếu:

- Package không nằm trong phạm vi **component scanning**.
- Class được tạo bằng `new` thủ công nhưng không đăng ký bean.
- Một profile/condition loại bỏ bean trong môi trường đang chạy.
- Endpoint thuộc **application context khác** với context mà `MessageDispatcherServlet` truy cập.
- Cấu hình Spring-WS support/endpoint mapping chưa được bật hoặc bị thay thế.

Không suy ra “bean có tồn tại trong code repository” đồng nghĩa bean đã được đăng ký **trong runtime đang nhận SOAP request**.

### 4.5. Method thiếu annotation hoặc mapping strategy khác

`@Endpoint` trên class **không tự quyết định QName cho mọi method**. Method cần quy tắc mapping mà ứng dụng đã đăng ký, chẳng hạn `@PayloadRoot` hoặc `@SoapAction` theo các strategy tương ứng.

Một method `@RequestPayload` bình thường nhưng thiếu mapping phù hợp có thể không được chọn, dù kiểu Java của tham số nhìn giống JAXB class đúng hợp đồng.

## 5. Cấu hình Spring-WS cần có để routing hoạt động

Ví dụ Spring Boot/Servlet application với SOAP endpoint map ở `/ws/*`:

~~~java
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

@EnableWs
@Configuration
public class SoapWebServiceConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet> soapServlet(
            ApplicationContext context) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }
}
~~~

**Giả định:** dự án dùng ngăn xếp Spring Boot tương thích, và chưa có auto-configuration hoặc đăng ký `MessageDispatcherServlet` khác tạo mapping chồng lấn. Trong ứng dụng thật, cần kiểm tra cơ chế tự cấu hình của phiên bản Spring Boot/Spring-WS trước khi thêm registration thủ công.

Để nhận `@Endpoint` qua component scanning:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;

@SpringBootApplication(scanBasePackages = "org.example.orders")
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Ví dụ chỉ có tác dụng nếu `OrderEndpoint` thực tế nằm dưới package `org.example.orders` hoặc package con. Nếu endpoint ở `org.example.integration.soap`, cần mở rộng scan bằng cấu hình có chủ đích hoặc di chuyển package phù hợp.

### Phân biệt `@Endpoint` với annotation khác

| Annotation/class | Mục đích thường gặp | Có tự tạo Spring-WS SOAP mapping không? |
| --- | --- | --- |
| `@Endpoint` | Đánh dấu Spring-WS endpoint | Có thể được các endpoint mapping của Spring-WS phát hiện khi method có annotation phù hợp |
| `@RestController` | REST/HTTP MVC controller | **Không** tự tạo `@PayloadRoot` SOAP routing |
| `@Service` | Bean chứa nghiệp vụ | Không tự tạo SOAP method mapping |
| `@PayloadRoot` | Mapping payload QName | Có, khi endpoint mapping tương ứng được đăng ký |
| `@SoapAction` | Mapping SOAP action theo strategy tương ứng | Có, nếu action-based endpoint mapping hoạt động |
| `@RequestPayload` | Binding dữ liệu XML vào method argument | Không tự chọn endpoint |
| `@ResponsePayload` | Binding kết quả method ra XML | Không tự chọn endpoint |

WSDL được công bố từ `DefaultWsdl11Definition` hoặc WSDL tĩnh **không tự động bảo đảm** đã tồn tại method Java triển khai mọi operation trong đó. WSDL là hợp đồng, còn mapping và endpoint implementation là cấu hình runtime riêng.

## 6. SOAPAction cũng là một chiến lược định tuyến — nhưng khác QName

Spring-WS có thể được cấu hình để định tuyến theo action qua `SoapActionAnnotationMethodEndpointMapping` với `@SoapAction`. Đây là tiêu chí khác với `@PayloadRoot`.

~~~java
import org.springframework.ws.soap.server.endpoint.annotation.SoapAction;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import javax.xml.transform.Source;

@Endpoint
public class ActionBasedOrderEndpoint {
    @SoapAction("urn:example:orders:actions:GetOrder")
    @ResponsePayload
    public Source process(@RequestPayload Source payload) {
        // Đây là ví dụ chữ ký. Cần xử lý/validate payload
        // và tạo response Source hợp XSD ở implementation thực.
        throw new UnsupportedOperationException("Ví dụ routing theo SOAPAction");
    }
}
~~~

Đoạn mã trên **chỉ minh họa annotation mapping**, không phải endpoint hoàn chỉnh để triển khai cùng handler `@PayloadRoot`. Khi cần sử dụng, hãy triển khai logic, SOAP Fault handling, validation và chọn chiến lược ánh xạ một cách minh bạch.

### Những loại action thường bị nhầm

| Trường | Nằm ở đâu? | Có phải chính là payload QName? |
| --- | --- | --- |
| `SOAPAction` trong SOAP 1.1 HTTP binding | HTTP header, liên hệ với `soap:operation soapAction` trong WSDL | Không |
| Tham số `action` của `application/soap+xml` | Media type parameter trong SOAP 1.2 HTTP binding | Không |
| WS-Addressing `wsa:Action` | SOAP Header theo WS-Addressing | Không |
| `@PayloadRoot` | QName root element của SOAP Body | Là tiêu chí routing theo payload |

Đừng đồng nhất ba dạng action hoặc ngầm kỳ vọng chúng có cùng giá trị. Cơ chế nào được Spring-WS sử dụng phụ thuộc **endpoint mapping thực tế đã đăng ký** và cách request được xử lý.

Ví dụ request SOAP 1.1 với header action:

~~~http
POST /ws HTTP/1.1
Host: orders.example.org
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:actions:GetOrder"
~~~

Nếu ứng dụng chỉ định tuyến theo `@PayloadRoot`, thay đổi `SOAPAction` không tự làm QName root khác đi. Nếu ứng dụng dùng action-based mapping, client gửi thiếu/sai action có thể dẫn đến **không có handler theo chiến lược đó**. Kết quả cuối cùng còn phụ thuộc thứ tự và các mapping khác cùng tồn tại.

### Nhiều EndpointMapping cùng hoạt động

Spring-WS có thể có nhiều `EndpointMapping`. `MessageDispatcher` tìm handler bằng cách xét các mapping theo **thứ tự ưu tiên của chúng**, rồi chọn mapping phù hợp theo cơ chế runtime. Một QName có thể được phục vụ bởi mapping dựa vào payload, trong khi mapping khác dùng SOAPAction; nếu cấu hình chồng nhau, **handler được chọn có thể phụ thuộc thứ tự mapping**.

Điều này không có nghĩa “cứ đặt `@Order` lên endpoint class là giải quyết được trùng QName”. Thứ tự **mapping strategy** khác với việc có hai method cùng đăng ký một routing key **trong chính một mapping**. Giải pháp là thiết kế một quy tắc dispatch rõ ràng và kiểm tra registration/lookup lúc khởi động.

## 7. Cấu hình trùng: những dạng va chạm phổ biến

### 7.1. Hai endpoint cùng `namespace + localPart`

Ví dụ xung đột:

~~~java
@Endpoint
public class OrderReadEndpoint {
    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse handle(
            @RequestPayload GetOrderRequest request) {
        // ...
        return null;
    }
}

@Endpoint
public class LegacyOrderEndpoint {
    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse legacy(
            @RequestPayload GetOrderRequest request) {
        // ...
        return null;
    }
}
~~~

**Hai method cùng ánh xạ một QName** trong cùng chiến lược payload-root. Không nên kỳ vọng Spring-WS tự suy ra method đúng dựa vào tên class `Legacy`, version Java DTO, thứ tự khai báo hay chữ ký method.

Tùy phiên bản và implementation của endpoint mapping, hệ thống có thể **phát hiện ánh xạ trùng lúc đăng ký/khởi động**, gây lỗi hoặc kết quả lookup không như mong đợi. Không dựa vào hành vi mơ hồ như “method đăng ký sau thắng” để xử lý hợp đồng công khai.

**Cách sửa bền vững:** mỗi routing key có đúng một owner trong mỗi strategy. Nếu hai xử lý khác nhau:

- Dùng **hai root elements/QName khác nhau** (`GetOrderRequest` so với `GetOrderHistoryRequest`).
- Nếu phát hành contract v2, dùng namespace hoặc element names versioned theo chính sách đã phê duyệt.
- Đưa logic phân nhánh **nghiệp vụ hợp lệ** vào service/dispatcher nội bộ sau một endpoint duy nhất, thay vì đăng ký hai endpoint có cùng key.
- Nếu thực sự cần action-based routing riêng, thiết kế lại mapping strategies và thứ tự một cách có kiểm thử — không áp dụng như bản vá che xung đột ngẫu nhiên.

### 7.2. Trùng method trong cùng class

~~~java
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
public GetOrderResponse handleV1(GetOrderRequest input) { /* ... */ }

@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
public GetOrderResponse handleAnother(GetOrderRequest input) { /* ... */ }
~~~

Ví dụ là **pseudocode** rút gọn: không có `@RequestPayload`, `@ResponsePayload` và phần thân hoàn chỉnh. Dù method names khác nhau, cả hai vẫn đăng ký **cùng QName**. Java method overloading không phải cơ chế để SOAP endpoint mapping chọn giữa hai handler cùng root.

### 7.3. Trùng bean do component scan và đăng ký `@Bean`

Nếu một class có `@Endpoint` được component-scan **và** cũng được tạo thủ công qua `@Bean` hoặc imported configuration khác, bạn có thể vô tình tạo **nhiều bean** của cùng endpoint. Tùy cơ chế bean registration, hệ thống có thể báo trùng bean name, có hai instance hoặc sinh duplicate mapping.

Khi điều tra, đừng chỉ tìm text `@PayloadRoot`; hãy kiểm tra **số endpoint beans runtime** và nguồn khai báo của chúng. Một mapping key xuất hiện một lần trong code chưa chứng minh nó chỉ được đăng ký một lần.

### 7.4. Cùng operation nhưng hai servlet hoặc application contexts

Hai `MessageDispatcherServlet` có mapping URL chồng nhau, hoặc một root context và một child servlet context chứa các endpoint khác nhau, có thể làm:

- Request đi vào servlet không có bean cần thiết.
- WSDL được phục vụ bởi context này nhưng POST SOAP đi vào context khác.
- Endpoint registration chạy hai lần hoặc một endpoint chỉ xuất hiện trong context không được dùng cho request.

Không đồng nhất **HTTP servlet mapping** với **SOAP endpoint mapping**. Hãy kiểm tra **cả hai**.

### 7.5. Trùng giữa payload mapping và action mapping

Cùng một request có thể phù hợp với `@PayloadRoot` của handler A và `@SoapAction` của handler B, nếu cả hai strategy được bật. Trường hợp này không giống “hai key trùng trong cùng map”: đây là **competition giữa strategies**. Handler thực tế có thể tùy thứ tự mapping và mức ưu tiên. Đối với public API, hãy định nghĩa chính sách nhất quán rồi viết integration test để không có thay đổi ngầm sau nâng cấp framework.

## 8. Chiến lược tổ chức endpoint tránh trùng từ thiết kế

Một thiết kế dễ bảo trì cho các operation khác nhau:

~~~java
@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse get(
            @RequestPayload GetOrderRequest request) {
        // ...
        return null;
    }

    @PayloadRoot(namespace = NS, localPart = "CancelOrderRequest")
    @ResponsePayload
    public CancelOrderResponse cancel(
            @RequestPayload CancelOrderRequest request) {
        // ...
        return null;
    }
}
~~~

Đây là skeleton để minh họa mapping; hai method cần implementation thật, business service và JAXB types tương ứng. Điều quan trọng là hai root local names khác nhau.

Có thể phân chia theo domain:

~~~text
urn:example:orders:v1
  {namespace}GetOrderRequest    → OrderQueryEndpoint
  {namespace}CancelOrderRequest → OrderCommandEndpoint

urn:example:payments:v1
  {namespace}GetPaymentRequest  → PaymentEndpoint
~~~

Các trường hợp dùng tên Java trùng như `GetRequest` ở hai package vẫn có thể định tuyến khác nhau nếu **QName namespace khác nhau**. Tuy nhiên, client phải tải đúng WSDL/XSD và dùng chính QName mà contract mô tả.

### Không tạo phiên bản bằng đổi namespace tùy tiện

Đổi `urn:example:orders:v1` thành v2 có thể giải quyết một va chạm tên về mặt kỹ thuật, nhưng nó cũng đổi **danh tính XML** và có thể làm hỏng client đã triển khai. Versioning chỉ nên thực hiện khi có thay đổi hợp đồng được quản lý, có kế hoạch vận hành song song và kiểm thử tương thích.

## 9. Phân biệt không có EndpointMapping và không có EndpointAdapter

Hai loại lỗi xảy ra ở **hai chặng khác nhau**:

| Trạng thái | Ý nghĩa | Cách điều tra |
| --- | --- | --- |
| **Không có endpoint mapping** | Không tìm được endpoint method cho QName/action trong các mapping đang hoạt động | QName, `@PayloadRoot`, `@SoapAction`, scan beans, servlet context |
| **Có mapping nhưng không có adapter** | Đã chọn handler nhưng không có `EndpointAdapter` hỗ trợ cách gọi method đó | Chữ ký method, `@RequestPayload`/`@ResponsePayload`, JAXB processor, Spring-WS config |
| **Adapter gọi được nhưng unmarshalling fail** | Endpoint đã được chọn; XML không ánh xạ được sang Java theo binding | XSD, `@XmlRootElement`, `JAXBElement`, package/namespace, Jakarta/Javax |
| **Method chạy rồi ném exception** | Routing thành công, lỗi nằm ở nghiệp vụ hoặc infrastructure | Service logs, exception resolver, SOAP Fault |

Ví dụ, method sau có thể được **chọn đúng** theo QName nhưng không có argument resolver phù hợp nếu cấu hình adapter thiếu tính năng cần thiết:

~~~java
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
@ResponsePayload
public GetOrderResponse get(
        @RequestPayload CustomXmlRecord request) {
    // CustomXmlRecord không tự động được hỗ trợ bởi mọi adapter.
    return null;
}
~~~

Không sửa root QName để “fix” method adapter. Giải pháp phải giải quyết **kiểu tham số được endpoint adapter hỗ trợ**, JAXB binding hoặc cách chuyển payload thích hợp.

Ngược lại, nếu method nhận `Source` thay vì JAXB và có processor hỗ trợ, sự khác biệt nằm ở **cách đọc payload**, không thay đổi routing key từ `@PayloadRoot`.

## 10. Một quy trình chẩn đoán có thể lặp lại

### Bước 1 — Lấy request thực tế từ client bị lỗi

Ghi nhận tối thiểu:

- URL public mà client POST, HTTP method, Content-Type, SOAP 1.1/1.2.
- SOAP Envelope namespace và root QName trong Body.
- Header `SOAPAction` (nếu SOAP 1.1) hoặc SOAP 1.2 action/WS-Addressing nếu được sử dụng trong contract.
- Timestamp, correlation ID, mã phản hồi HTTP và payload Fault/response đã được lọc.

**Không log raw mật khẩu, token, private key, thẻ tín dụng hoặc thông tin nhạy cảm** chỉ để tìm lỗi routing. Khi SOAP đã được ký/mã hóa, cần quy trình quan sát có kiểm soát để không làm thay đổi thông điệp.

### Bước 2 — Xác nhận request vào đúng servlet

Ví dụ môi trường:

~~~text
Public:  https://api.example.org/gateway/ws
Proxy:   /gateway/ws → http://orders-app:8080/ws
Servlet: /ws/*
~~~

Xác minh proxy rewrite, virtual host, TLS termination, HTTP POST, ingress allowlist và mapping của `MessageDispatcherServlet`. Một GET `orders.wsdl` thành công **không chứng minh** POST SOAP đã vào cùng backend/service context.

### Bước 3 — So QName từ message với annotation

Ghi theo dạng chuẩn:

~~~text
Request QName   = {urn:example:orders:v1}GetOrderRequest
Annotation QName= {urn:example:orders:v1}GetOrderRequest
~~~

Nếu khác:

- Khác namespace URI? Kiểm tra default namespace ở phần tử gốc.
- Khác local name hoặc chữ hoa/chữ thường?
- Client đang dùng XSD/WSDL phiên bản nào?
- Có transform/gateway thay XML body không?

**Không so prefix** `ord`/`o` để kết luận khác namespace.

### Bước 4 — Kiểm tra bean và mapping được đăng ký

Xác minh:

1. `@Endpoint` bean hiện diện trong **ApplicationContext phục vụ SOAP POST**.
2. `@EnableWs` hoặc cấu hình Spring-WS tương đương đã đăng ký các mapping/adapter cần thiết.
3. Method có đúng annotation mapping, tên namespace và localPart.
4. Không có nhiều bean hoặc method cùng đăng ký một key.
5. Nếu có payload/action/WS-Addressing mappings, thứ tự và tiêu chí được cấu hình có chủ đích.

Nếu class chỉ tồn tại trong mã nguồn mà không phải runtime bean, hãy sửa component scan/bean registration — không sửa WSDL.

### Bước 5 — Xem log đúng nhóm và môi trường

Ví dụ cấu hình log tạm trong **môi trường kiểm thử**:

~~~yaml
# application.yml — ví dụ; logger có thể khác theo phiên bản.
logging:
  level:
    org.springframework.ws.server.MessageDispatcher: DEBUG
    org.springframework.ws.server.endpoint.mapping: TRACE
    org.springframework.ws.server.endpoint.adapter: DEBUG
    org.springframework.ws.transport.http: DEBUG
~~~

Các logger chi tiết và mức log hiệu quả phụ thuộc bản Spring-WS/SLF4J đang sử dụng; cần xem output thực tế. Không bật TRACE payload toàn hệ thống lâu dài trên production. Mục tiêu là biết **request đi qua dispatcher nào, mapping nào trả handler, adapter nào nhận method và exception/fault xuất hiện ở chặng nào**.

### Bước 6 — Kiểm tra response/Fault và đối chiếu source gốc

Nếu endpoint đã chạy, kiểm tra JAXB/marshalling, response QName, schema validation, SOAP Fault và security interceptor. Nếu endpoint **chưa được chọn**, đừng truy lỗi trong `OrderService` hoặc sửa JAXB generated class trước.

## 11. Gửi SOAP request tối thiểu để tái hiện lỗi

Ví dụ tạo một file test `get-order.xml` chứa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Header/>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1024</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Lệnh kiểm thử tương ứng (minh họa, không chạy trong bài):

~~~bash
curl --verbose --request POST \
  "https://api.example.org/gateway/ws" \
  --header "Content-Type: text/xml; charset=utf-8" \
  --header 'SOAPAction: "urn:example:orders:actions:GetOrder"' \
  --data-binary @get-order.xml
~~~

Lệnh dùng SOAP 1.1. `SOAPAction` chỉ là giá trị minh họa; trong hệ thống thật phải theo WSDL/operation và mapping đang sử dụng. Không dùng request này để test SOAP 1.2 mà chỉ thay namespace Envelope: SOAP 1.2 dùng media type/binding khác và cần cấu hình message factory tương ứng.

**Tạo hai biến thể kiểm thử:**

1. Đổi `ord` thành `x` nhưng giữ URI `urn:example:orders:v1`. Nếu routing đúng theo QName, kết quả selection không nên thay đổi.
2. Đổi URI sang `urn:example:orders:v2` nhưng giữ tên `GetOrderRequest`. Nếu không có mapping v2, request không nên vào handler v1.

Khi test, phân biệt **kết quả HTTP** với **kết quả SOAP**: status HTTP không nói hết nội dung Body; SOAP Fault có cấu trúc theo version và policy, còn lỗi reverse proxy có thể trả HTML, JSON hoặc body rỗng.

## 12. Những sai khác nhỏ làm routing hỏng

| Hiện tượng | Nguyên nhân thường gặp | Khắc phục có căn cứ |
| --- | --- | --- |
| `No endpoint mapping found` với namespace v2 | Client dùng sai phiên bản hoặc server chưa triển khai v2 | Đối chiếu namespace XSD/WSDL và strategy version |
| Cùng local name nhưng không dispatch | Sai `targetNamespace`, default namespace hoặc chữ hoa/thường | Log QName root chính xác |
| Đổi prefix khiến code tự viết không nhận request | Code phụ thuộc prefix thay vì QName | Dùng API namespace-aware, không regex trên tag |
| GET WSDL được, POST SOAP 404 | Proxy chỉ route GET, POST khác đường dẫn hoặc context | Kiểm tra servlet mapping và reverse proxy POST |
| SOAP 1.2 request bị từ chối | Message factory/binding đang nhận SOAP 1.1 | Kiểm tra Envelope NS, Content-Type và cấu hình |
| `@Endpoint` không được chọn | Bean không được scan/context sai | Kiểm tra runtime bean và mapping registration |
| Có nhiều handler cùng QName | Hai method hoặc bean trùng registration | Giữ một owner mỗi routing key |
| Mapping chọn method không mong muốn | Nhiều strategies và order khác nhau | Kiểm tra EndpointMapping order và tiêu chí |
| Đã chọn method nhưng không gọi được | Không có adapter/argument resolver | Kiểm tra chữ ký method, JAXB/OXM |
| SOAPAction đúng nhưng payload QName sai | Action không thay đổi QName Body | Chọn strategy rõ ràng; kiểm tra cả hợp đồng và validation |
| Endpoint chạy nhưng client thấy Fault | Exception/schema/security sau routing | Kiểm tra fault resolver, validation, WS-Security |
| Chỉ production lỗi routing | Ingress rewrite, deployment/profile/context khác staging | So sánh cấu hình đã triển khai và request thực |

### Cách tránh “sửa đúng triệu chứng, sai nguyên nhân”

Nếu client gửi namespace v2 nhưng server chỉ triển khai v1, thay toàn bộ `@PayloadRoot` sang v2 sẽ khiến **client v1 trước đó không còn hoạt động**. Đây không phải sửa lỗi routing đơn thuần mà là thay đổi API contract. Cần phân tích tương thích và chính sách versioning.

Nếu thiếu endpoint bean, thêm `@PayloadRoot` vào method khác mà không sửa component scanning cũng không giải quyết vấn đề. Nếu lỗi nằm ở HTTPS proxy, sửa JAXB model không có tác dụng.

## 13. SOAP Fault: lỗi định tuyến không đồng nghĩa lỗi nghiệp vụ

SOAP Fault là **message SOAP có cấu trúc lỗi**, ví dụ SOAP 1.1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>Yêu cầu không hợp lệ theo hợp đồng</faultstring>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là minh họa về SOAP Fault; **không bảo đảm** Spring-WS tự trả chính xác Fault trên khi không có endpoint mapping. Cách một lỗi xảy ra trước/sau mapping được chuyển thành Fault, status HTTP hay body rỗng phụ thuộc message dispatcher, exception resolvers, message sender/receiver và phiên bản SOAP.

| Lỗi | Có thể diễn ra trước endpoint không? | Tầng giải quyết |
| --- | --- | --- |
| Proxy route sai | Có, ngoài Spring-WS | Gateway/transport, không có Spring SOAP Fault bắt buộc |
| Envelope XML hỏng | Có | Message factory/parser và xử lý lỗi SOAP |
| Không có mapping cho QName | Có, tại endpoint mapping | Dispatcher/mapping configuration |
| XSD payload invalid | Tùy interceptor/validation placement | Schema validation và SOAP fault policy |
| Không có adapter phù hợp | Sau khi endpoint mapping được chọn | Endpoint adapter configuration |
| Business rule từ chối order | Sau khi endpoint method được gọi | Service + exception resolver/typed fault |
| Chữ ký/timestamp sai | Có thể trước method | WS-Security interceptor/security policy |

Nếu WSDL công bố **typed fault** hoặc hợp đồng lỗi riêng, cần bảo đảm lỗi nghiệp vụ được ánh xạ đúng phần tử Fault detail tương ứng. Một handler không tồn tại **không phải** lý do để bịa một business fault “ORDER_NOT_FOUND”.

## 14. Interceptor và WS-Security trong quá trình routing

Một số interceptor chạy trong chuỗi được endpoint mapping chọn. Vì vậy:

- Interceptor gắn với endpoint mapping/endpoint chain **không nên là hàng rào duy nhất** bảo vệ những request **không tìm thấy endpoint**.
- Nếu SOAP message bị chặn bởi TLS, reverse proxy hoặc XML parser trước khi có endpoint, interceptor ở mức endpoint có thể **không được gọi**.
- Trường hợp SOAP security được xử lý trước khi endpoint method thực thi, thứ tự verify/decrypt/validation phải theo cấu hình và chính sách thực tế. Không dùng việc request “đã tìm thấy endpoint” để suy ra đã xác thực.
- Dữ liệu từ SOAP Header, `SOAPAction` hoặc QName chỉ là **thông tin định tuyến**; caller có thể tự đặt chúng. Authorization vẫn phải dựa trên danh tính/claims đã được xác minh đáng tin cậy.

### Tại sao không được chỉ dựa vào SOAPAction để cấp quyền?

Một client không tin cậy có thể gửi:

~~~http
SOAPAction: "urn:example:orders:actions:AdminCancel"
~~~

Header action không chứng minh người dùng có quyền `AdminCancel`. Dù action mapping dẫn đến một handler, service vẫn phải kiểm tra **authentication/authorization**; nếu dùng WS-Security cần xác minh token/chữ ký/timestamp và chính sách liên quan. Với mTLS cần kiểm tra chứng chỉ và ràng buộc identity tại đúng tầng transport.

### XML security cũng có thể chặn trước routing

Parser SOAP phải xử lý XML không tin cậy theo chính sách chống XXE/DTD hoặc external entity, giới hạn kích thước/độ sâu và thời gian xử lý. Việc “không thấy `@Endpoint` chạy” có thể do request bị từ chối **trước khi có QName hợp lệ**, không phải do Spring-WS quên scan bean.

Không hạ thấp cấu hình XML security để làm một request bất thường đi vào endpoint; hãy xác định input nào vi phạm chính sách và báo lỗi theo contract.

## 15. Kiểm thử routing bằng Spring-WS và client thực tế

Một method Java được gọi thành công trong unit test **không chứng minh** `MessageDispatcher` tìm được method qua SOAP request. Routing cần được kiểm tra bằng **SOAP message ở biên**.

### 15.1. `MockWebServiceClient` cho endpoint phía server

Spring-WS có `MockWebServiceClient` để gửi payload test tới endpoint trong application context và kiểm tra phản hồi.

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

String req = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
    """;

String expected = """
    <ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-1024</ord:orderId>
        <ord:status>CONFIRMED</ord:status>
    </ord:GetOrderResponse>
    """;

MockWebServiceClient client =
        MockWebServiceClient.createClient(applicationContext);

client.sendRequest(withPayload(new StringSource(req)))
      .andExpect(payload(new StringSource(expected)));
~~~

Đoạn minh họa giả định test context có `OrderEndpoint` và mock service trả `CONFIRMED`, Java hỗ trợ text blocks (Java 15+) và các dependency Spring-WS Test. Đây là **integration test lớp endpoint**, không kiểm thử HTTP reverse proxy, TLS hay toàn bộ WSDL public.

### 15.2. Ma trận routing tối thiểu

| Test | Payload hoặc cấu hình | Kỳ vọng |
| --- | --- | --- |
| Happy path v1 | `{urn:example:orders:v1}GetOrderRequest` | Chọn đúng `OrderEndpoint`, response hợp XSD |
| Prefix thay đổi | `<o:GetOrderRequest>` với URI v1 | Chọn cùng handler, không phụ thuộc prefix |
| Namespace khác | URI v2, không có endpoint v2 | Không chọn handler v1 |
| Local name khác | `getOrderRequest` thay `GetOrderRequest` | Không chọn handler v1 |
| Chưa scan bean | Endpoint class tồn tại nhưng ngoài scan | Không được đăng ký; test phát hiện cấu hình |
| Hai mapping giống hệt | Hai methods cùng QName | Phát hiện cấu hình cạnh tranh/trùng trong startup hoặc kiểm thử |
| Method argument không hỗ trợ | Handler có mapping nhưng parameter type chưa được adapter hỗ trợ | Phân biệt adapter failure với no mapping |
| SOAPAction thiếu/sai | App dùng `@SoapAction` | Kiểm tra behavior của đúng action mapping strategy |
| XSD không hợp lệ | Đúng QName nhưng Body thiếu field | Handler mapping có thể thành công; validation từ chối |
| Fault nghiệp vụ | Đúng QName, order không tồn tại | Fault theo contract, không phải no endpoint |
| Security từ chối | Token hoặc chữ ký không hợp lệ | Không chạy nghiệp vụ nhạy cảm |
| Cùng WSDL, POST qua proxy | URL public → backend servlet | Routing/transport đúng cả ngoài mạng |

**Lưu ý khi viết test âm:** kết quả cụ thể của “không có mapping” có thể là exception hoặc phản hồi/HTTP status khác tùy phiên bản/config. Hãy test **bất biến nghiệp vụ** rằng handler v1 không được gọi, và test chính sách lỗi đã được hệ thống công bố — không hardcode một status/Fault khi chưa xác nhận runtime.

### 15.3. Phát hiện duplicate mappings trong CI

Khi một nhóm thêm endpoint:

1. Khởi tạo test application context thật với các `@Endpoint` beans.
2. Bắt lỗi đăng ký mapping trùng hoặc ghi nhận tất cả routing keys được ánh xạ.
3. Định nghĩa mỗi QName/action key thuộc owner nào.
4. Test cùng một request chỉ được xử lý bởi method chủ đích.
5. Nếu nâng cấp Spring-WS, so kết quả mapping với baseline đã thống nhất.

Mục tiêu là **không để một thay đổi thư viện, component scan hoặc import configuration làm âm thầm đổi handler**.

### 15.4. SOAP client test và interoperability

`MockWebServiceServer` giúp kiểm tra phía **SOAP client** khi dùng `WebServiceTemplate`: request marshal đúng QName/header, response/Fault được xử lý phù hợp. Nó không thay thế `MockWebServiceClient` cho phía server.

Một đợt kiểm thử tương thích nên sinh client Java/.NET/ESB từ **WSDL public**, gửi SOAP request thật qua proxy, rồi đối chiếu XML message, SOAPAction, SOAP version, certificate/WS-Security, Fault và mapping. WSDL chỉ đọc được từ local không đủ chứng minh endpoint deploy đúng public route.

## 16. Ca điều tra thực tế: WSDL đúng, không có endpoint v1

Giả sử:

~~~text
GET  https://api.example.org/soap/orders.wsdl → 200, WSDL hợp lệ
POST https://api.example.org/soap             → lỗi khi gọi GetOrder
~~~

Lúc đầu nhóm nghi JAXB hoặc schema validation. Nhưng request trên dây cho thấy:

~~~xml
<p:GetOrderRequest xmlns:p="urn:example:orders:v2">
    <p:orderId>ORD-1024</p:orderId>
</p:GetOrderRequest>
~~~

Trong khi endpoint runtime:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest")
~~~

**Phân tích có căn cứ:** request mang QName v2, endpoint map QName v1. Spring-WS không nên tự đoán v2 tương đương v1 chỉ vì local name giống nhau.

Quy trình xử lý:

1. Xác nhận WSDL mà client **thực sự dùng khi sinh mã** có tham chiếu XSD v1 hay v2.
2. Xác định bên nào đã đổi namespace: contract đã phát hành hay client build sai artifact.
3. Nếu hợp đồng v1 còn hiệu lực, sửa client gửi v1; không tùy tiện chuyển v1 server sang v2.
4. Nếu có nghiệp vụ v2 thật, phát hành v2 theo chính sách, đăng ký handler v2, test song song v1/v2.
5. Viết regression test với hai QName, bảo đảm request v1 tiếp tục vào endpoint v1 và v2 vào endpoint v2 chỉ khi đã triển khai chính thức.

**Kết luận ca điều tra:** chẩn đoán bằng **QName thực tế** tránh một thay đổi server phá vỡ client v1 chỉ để đáp ứng một request v2 chưa được phê duyệt.

## 17. Bài tập tự kiểm tra

### Bài tập A — Tìm tầng lỗi

Cho các triệu chứng sau, hãy xác định tầng cần điều tra đầu tiên và bước xác minh:

1. Client nhận HTTP 404 từ gateway, không có log trong `MessageDispatcherServlet`.
2. Log có “No endpoint mapping found” nhưng `@Endpoint` class đã tồn tại trong source.
3. Method `@PayloadRoot` được chọn, sau đó framework báo không có adapter hỗ trợ tham số.
4. JAXB unmarshal thất bại vì request dùng `urn:example:orders:v2`.
5. Client tải được WSDL qua HTTPS nhưng request POST bị đưa đến backend khác.
6. Có SOAP Fault do chữ ký WS-Security không hợp lệ, dù QName khớp annotation.

### Bài tập B — Nhận diện các key trùng

Trong một ứng dụng có hai class:

~~~java
@PayloadRoot(namespace = "urn:example:orders:v1",
             localPart = "GetOrderRequest")
public GetOrderResponse getCurrent(GetOrderRequest req) { /* ... */ }

@PayloadRoot(namespace = "urn:example:orders:v1",
             localPart = "GetOrderRequest")
public GetOrderResponse getLegacy(GetOrderRequest req) { /* ... */ }
~~~

Đây là pseudocode. Hãy đề xuất ba phương án **hợp đồng rõ ràng** để tránh trùng, rồi giải thích vì sao việc đổi tên Java method không giải quyết routing.

### Bài tập C — Viết kiểm thử định tuyến

Với `GetOrderRequest`:

1. Viết request v1 hợp lệ và request v2 khác namespace.
2. Viết test `MockWebServiceClient` chứng minh v1 được xử lý bởi `OrderEndpoint`.
3. Viết test negative bảo đảm handler v1 **không** xử lý request v2.
4. Viết test khi đổi XML prefix nhưng giữ URI, endpoint không thay đổi.
5. Thêm một handler trùng QName trong test context và xác định behavior registration thực tế của phiên bản Spring-WS đang dùng.
6. Nếu ứng dụng dùng SOAPAction mapping, thử action đúng/sai và kiểm tra thứ tự với payload-root mapping.
7. Chạy thử qua public proxy để phân biệt lỗi HTTP route với lỗi SOAP endpoint mapping.

### Bài tập D — Bảo mật và vận hành

Một đối tác gửi `SOAPAction=CancelOrder` nhưng token WS-Security không hợp lệ. Vì sao handler có thể **được chọn** nhưng tuyệt đối **không được thực thi nghiệp vụ hủy đơn**? Phác thảo vị trí của transport/mTLS, XML parser, endpoint mapping, security interceptor, schema validation và authorization trong giải pháp triển khai của bạn.

## 18. Checklist trước khi công bố một endpoint mới

| Kiểm tra | Điều kiện hoàn thành |
| --- | --- |
| **XSD/WSDL** | Có global request/response elements, QName và binding rõ; schema dependencies resolve được |
| **Servlet/public URL** | GET WSDL và POST SOAP route đúng, không nhầm endpoint URL với WSDL URL |
| **Bean registration** | `@Endpoint` nằm trong đúng Spring application context; không đăng ký trùng |
| **Mapping** | Mỗi QName/action key thuộc một handler chủ đích; thứ tự strategies đã biết |
| **Adapter/JAXB** | Method signature được hỗ trợ, Javax/Jakarta phù hợp, marshal/unmarshal đúng |
| **Validation** | XML input/output hợp schema và quy tắc nghiệp vụ |
| **Fault** | Lỗi được phân loại đúng: transport, mapping, schema, business, security |
| **Security** | TLS/mTLS, WS-Security, certificate trust, XML parser và authorization được kiểm soát |
| **Regression** | Test QName v1/v2, prefix, unknown request, duplicate registration và SOAPAction khi dùng |
| **Interop** | Client độc lập dùng WSDL công khai gọi SOAP thật thành công |

**Kết luận:** Khi Spring-WS báo **không có endpoint phù hợp**, hãy bắt đầu từ tuyến HTTP/servlet, SOAP parsing và **QName hoặc action thực tế** trước khi nghi ngờ JAXB hay nghiệp vụ. Khi gặp **cấu hình trùng**, hãy tìm mọi endpoint beans, phương thức và mapping strategies cùng đăng ký, rồi bảo đảm mỗi routing key có một chủ sở hữu rõ ràng. Cuối cùng, **mapping tìm được handler không đồng nghĩa request đã hợp lệ hoặc được xác thực**: adapter, XSD validation, SOAP Fault, WS-Security và kiểm thử tương thích vẫn là những lớp riêng. Chẩn đoán theo đúng ranh giới giúp các dịch vụ **SPRING_WEB_SERVICES** ổn định và có thể bảo trì khi tích hợp doanh nghiệp.
