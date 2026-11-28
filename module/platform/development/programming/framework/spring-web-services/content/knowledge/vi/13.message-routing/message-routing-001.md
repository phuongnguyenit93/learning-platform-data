# Định tuyến theo nội dung khác với định tuyến theo URL HTTP

## 1. Bài toán: cùng một URL nhưng có nhiều operation SOAP

Khi thiết kế API REST, lập trình viên thường phân biệt hành động bằng **HTTP method và đường dẫn**, ví dụ `GET /orders/123` hoặc `POST /orders/123/cancel`. Với dịch vụ **SOAP dùng Spring Web Services (Spring-WS)** theo hướng **contract-first**, cách chọn operation thường khác: HTTP URL đưa request đến **SOAP servlet**, còn nội dung của **SOAP Envelope**, đặc biệt phần tử gốc trong **SOAP Body**, có thể quyết định endpoint method nào được gọi.

Giả sử một dịch vụ đơn hàng công bố hai operation:

- `GetOrder`: truy vấn đơn hàng.
- `CancelOrder`: hủy đơn hàng theo quy tắc nghiệp vụ.

Cả hai request có thể được gửi bằng HTTP POST tới **cùng URL**:

`https://api.example.test/ws/orders`

Nhưng phần tử đầu của SOAP Body khác nhau:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>ORD-1001</o:orderId>
</o:GetOrderRequest>
~~~

và:

~~~xml
<o:CancelOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>ORD-1001</o:orderId>
</o:CancelOrderRequest>
~~~

Spring-WS có thể chọn hai handler khác nhau dựa trên **QName** (namespace URI + local name) của phần tử request. Đây là **định tuyến theo nội dung** (*content-based dispatch*) ở tầng xử lý SOAP; nó không đồng nhất với định tuyến bằng HTTP URL.

Nếu nhầm hai tầng, đội tích hợp dễ gặp các lỗi: WSDL được công bố ở `/ws/orders.wsdl` nhưng client POST vào đó; HTTP URL đúng nhưng `@PayloadRoot` không khớp; thay `SOAPAction` mà không đổi root QName; hoặc áp dụng phân quyền theo path và vô tình cho phép operation nhạy cảm được gọi qua một URL không mong đợi.

**Mục tiêu bài học:** đọc đúng các tầng định tuyến, cấu hình `MessageDispatcherServlet` và `@PayloadRoot`, hiểu vai trò `SOAPAction`, liên hệ XSD/WSDL/JAXB với QName, rồi xây dựng quy tắc bảo mật và kiểm thử tương thích.

## 2. Hai tầng định tuyến chính trong SOAP over HTTP

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["HTTPS / proxy / load balancer"]
    B --> C{"Host + URL path + HTTP method"}
    C -->|"/ws/* được chuyển đến SOAP"| D["MessageDispatcherServlet"]
    C -->|"URL không khớp"| X["404 / 405 / route khác tùy hạ tầng"]
    D --> E["Tạo WebServiceMessage, đọc SOAP Envelope"]
    E --> F["MessageDispatcher + EndpointMapping"]
    F --> G{"Payload QName / SOAP action / mapping được cấu hình"}
    G -->|"GetOrderRequest"| H["@Endpoint: getOrder"]
    G -->|"CancelOrderRequest"| I["@Endpoint: cancelOrder"]
    G -->|"Không có mapping"| J["Lỗi SOAP dispatch, tùy cấu hình"]
    H --> K["SOAP response"]
    I --> K
~~~

Sơ đồ trên minh họa trường hợp sử dụng **`@PayloadRoot`**; trong thực tế, `EndpointMapping` có thể chọn dựa trên SOAP action hoặc một tiêu chí khác nếu được đăng ký. Cũng có thể tồn tại interceptor kiểm tra security/validation và cơ chế xử lý exception trước hoặc sau khi gọi endpoint.

| Đặc điểm | Định tuyến HTTP | Định tuyến SOAP theo nội dung |
| --- | --- | --- |
| Diễn ra tại | Proxy, web server, Servlet container, Servlet mapping | `MessageDispatcher` và các `EndpointMapping` của Spring-WS |
| Dữ liệu quyết định | Host, port, URL path, method, đôi khi header | Payload QName, SOAP action hoặc thông tin thông điệp theo strategy |
| Ví dụ | `/ws/*` tới `MessageDispatcherServlet` | `{urn:example:orders:v1}GetOrderRequest` tới `getOrder` |
| Xử lý khi không khớp | 404, 405 hoặc route của server/gateway | Không tìm thấy endpoint SOAP; response cụ thể tùy stack/config |
| Liên quan XSD/WSDL | `soap:address` mô tả URL dịch vụ | `wsdl:message`/`wsdl:operation` và XSD mô tả payload |
| Ranh giới bảo mật | TLS, HTTP auth, gateway policy | SOAP/WS-Security, XSD validation, authorization theo operation |

**Một URL đúng chỉ giúp request đến đúng điểm vào HTTP.** Nó không bảo đảm phần tử SOAP Body hợp đồng, action phù hợp, chữ ký hợp lệ hay operation đã được phép thực hiện.

## 3. URL HTTP đưa thông điệp đến `MessageDispatcherServlet`

### 3.1. Vai trò của servlet mapping

Với Spring-WS, `MessageDispatcherServlet` là servlet tiếp nhận HTTP request SOAP, tạo biểu diễn `WebServiceMessage` và chuyển cho hạ tầng xử lý của Spring-WS. Trong một ứng dụng Spring Boot có hỗ trợ auto-configuration Web Services, cấu hình thường thấy:

~~~properties
server.port=8080
spring.webservices.path=/ws
~~~

Trong các phiên bản Boot hỗ trợ property này, `spring.webservices.path` đặt đường dẫn gốc của SOAP servlet. Nếu servlet phục vụ `/ws/*`, request tới `/ws/orders` và `/ws/customers` **có thể cùng đi vào một servlet**. Đường dẫn cụ thể của POST không tự trở thành tên operation.

Khi cần tự đăng ký servlet thay vì dùng Boot-managed registration, ví dụ:

~~~java
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

@Configuration
public class SoapServletConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
            soapServletRegistration(ApplicationContext context) {
        MessageDispatcherServlet servlet =
                new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }
}
~~~

Đây là **phương án thay thế** khi cần kiểm soát registration, không phải đoạn nên thêm vô điều kiện bên cạnh cấu hình servlet tự động của Boot. Cần xác minh cơ chế back-off và chỉ giữ một servlet mapping có hiệu lực cho URL dự định.

### 3.2. `@PostMapping` không thay thế `@PayloadRoot`

Spring MVC có `DispatcherServlet`, `@RestController`, `@RequestMapping` và `@PostMapping`. Spring-WS dùng `MessageDispatcherServlet`, `@Endpoint` và các cơ chế ánh xạ **thông điệp SOAP**.

Chẳng hạn, khai báo Spring MVC:

~~~java
@PostMapping("/ws/orders")
public ResponseEntity<String> postOrder(@RequestBody String body) {
    // Đây là handler Spring MVC, không phải SOAP @Endpoint tự động.
    return ResponseEntity.ok(body);
}
~~~

không thay thế hạ tầng xử lý Envelope/Header/Fault của Spring-WS. Trường hợp hệ thống cố tình dùng Spring MVC để nhận XML thô là một thiết kế khác, phải tự đảm nhiệm các quy tắc SOAP mà Spring-WS vốn hỗ trợ.

### 3.3. URL WSDL khác URL gửi SOAP

Giả sử bean WSDL tên `orders` được xuất bản qua:

`http://localhost:8080/ws/orders.wsdl`

và trong WSDL có:

~~~xml
<soap:address
    location="http://localhost:8080/ws/orders"/>
~~~

URL `.wsdl` dùng để **tải mô tả hợp đồng**, còn `/ws/orders` là **địa chỉ nhận SOAP request**. Không POST tới `.wsdl` chỉ vì client đã tải tài liệu tại đó; phải dùng địa chỉ `soap:address` hoặc URL endpoint được cấu hình và xác minh tương đương.

## 4. Định tuyến theo `QName` của phần tử gốc trong SOAP Body

### 4.1. QName không chỉ là tên ngắn

Trong XML namespace-aware, tên mở rộng của một phần tử là:

`{namespace URI}localName`

Ví dụ:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1"/>
~~~

có tên:

`{urn:example:orders:v1}GetOrderRequest`

Trong khi:

~~~xml
<GetOrderRequest/>
~~~

không có namespace mặc định thì mang tên `{}GetOrderRequest` — **khác** phần tử phía trên.

Đổi prefix từ `o` thành `ord` nhưng giữ nguyên URI **không đổi QName**:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1"/>
~~~

Với `@PayloadRoot`, Spring-WS định tuyến dựa trên namespace URI và local name, không so khớp chuỗi prefix trong XML.

### 4.2. XSD tạo ra QName của request

Một hợp đồng contract-first nên khai báo rõ global elements:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:complexType name="OrderKeyType">
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>

    <xs:element name="GetOrderRequest"
                type="tns:OrderKeyType"/>
    <xs:element name="CancelOrderRequest"
                type="tns:OrderKeyType"/>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="CancelOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="cancelled" type="xs:boolean"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Hai request dùng chung `OrderKeyType` nhưng là **hai global elements khác tên**, nên Spring-WS có thể định tuyến đến hai endpoint method khác nhau. `elementFormDefault="qualified"` quy định phần tử con `orderId` mang namespace ứng dụng; còn global element có namespace của `targetNamespace` bất kể form default.

Các DTO Java có thể được sinh từ XSD bằng JAXB/XJC; tuy nhiên **tên class Java không phải khóa định tuyến**. Khóa của `@PayloadRoot` vẫn là QName thực sự được gửi trong SOAP Body.

## 5. Cấu hình Spring-WS cho hai operation trên cùng URL

### 5.1. Kích hoạt endpoint và công bố WSDL

Ví dụ Java config dùng trong ứng dụng đã có `MessageDispatcherServlet`:

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class OrderWsConfig {

    private static final String NS = "urn:example:orders:v1";

    @Bean("orderSchema")
    public XsdSchema orderSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(
            XsdSchema orderSchema) {
        DefaultWsdl11Definition definition =
                new DefaultWsdl11Definition();
        definition.setPortTypeName("OrdersPort");
        definition.setServiceName("OrderService");
        definition.setTargetNamespace(NS);
        definition.setSchema(orderSchema);
        definition.setLocationUri("/ws/orders");
        definition.setCreateSoap11Binding(true);
        definition.setCreateSoap12Binding(false);

        Properties actions = new Properties();
        actions.setProperty(
                "GetOrder", "urn:example:orders:GetOrder");
        actions.setProperty(
                "CancelOrder", "urn:example:orders:CancelOrder");
        definition.setSoapActions(actions);
        return definition;
    }
}
~~~

Mã giả định file `xsd/orders.xsd` được đặt trong classpath và có nội dung ví dụ mục 4. Với quy ước hậu tố `Request` và `Response`, `DefaultWsdl11Definition` có thể suy ra hai operation `GetOrder` và `CancelOrder`. Hãy **đọc WSDL được sinh thực tế** để xác minh tên operation, binding, action và địa chỉ; đây không phải cơ chế tự đảm bảo mọi WSDL tùy chỉnh đều được sinh đúng như kỳ vọng.

`setLocationUri("/ws/orders")` công bố địa chỉ endpoint; nó **không tạo một handler HTTP riêng cho từng operation**. Nếu ứng dụng tự đăng ký servlet và Boot cũng tự đăng ký servlet trên cùng path, cần xử lý xung đột registration trước khi thử gửi SOAP.

### 5.2. Hai `@PayloadRoot` khác nhau

Ví dụ endpoint dùng DOM `Element` để tránh phụ thuộc code sinh JAXB trong bước minh họa routing:

~~~java
import javax.xml.transform.Source;
import org.w3c.dom.Element;
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
    public Source getOrder(@RequestPayload Element request) {
        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>FOUND</o:status>" +
                "</o:GetOrderResponse>");
    }

    @PayloadRoot(namespace = NS, localPart = "CancelOrderRequest")
    @ResponsePayload
    public Source cancelOrder(@RequestPayload Element request) {
        return new StringSource(
                "<o:CancelOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:cancelled>true</o:cancelled>" +
                "</o:CancelOrderResponse>");
    }
}
~~~

Đây là **ví dụ kiểm tra định tuyến**, không phải dịch vụ đơn hàng sản xuất: hai method cố ý trả kết quả cố định, không kiểm tra `orderId` và không thực hiện hủy thực tế. Trong ứng dụng thật, phải kiểm tra XSD, xác thực/ủy quyền, idempotency hoặc quy tắc chống thực hiện trùng, rồi gọi service nghiệp vụ. Nếu dùng JAXB, có thể thay `Element`/`Source` bằng DTO sinh từ XSD khi argument resolver và JAXB mapping được cấu hình tương ứng.

Điều đáng chú ý là **không có `@PostMapping("/ws/orders/get")` hay `@PostMapping("/ws/orders/cancel")`**. Cả hai method được chọn thông qua nội dung SOAP Body.

### 5.3. HTTP endpoint chưa biết operation cho tới khi đọc message

Giả sử cả hai request gửi đến:

~~~http
POST /ws/orders HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:GetOrder"
~~~

Với SOAP Body:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
    <soap:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Một request thứ hai vẫn đến `/ws/orders` nhưng có action và Body:

~~~http
POST /ws/orders HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:CancelOrder"
~~~

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
    <soap:Body>
        <o:CancelOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:CancelOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Với `@PayloadRoot` và mapping tương ứng được dùng, phần tử gốc Body là yếu tố phân biệt hai method. Cả hai request dùng **HTTP POST và cùng URL**; đổi operation không bắt buộc đổi URL.

## 6. `SOAPAction` là một tiêu chí định tuyến khác, không phải URL

Trong SOAP 1.1 over HTTP, `SOAPAction` là header thể hiện action của request. WSDL 1.1 có thể công bố giá trị tại:

~~~xml
<wsdl:operation name="GetOrder">
    <soap:operation
        soapAction="urn:example:orders:GetOrder"/>
    <!-- input / output binding -->
</wsdl:operation>
~~~

Ví dụ:

`SOAPAction: "urn:example:orders:GetOrder"`

**Giá trị này không phải:**

- URL để client gửi HTTP POST.
- QName của phần tử trong SOAP Body.
- Tên Java method bắt buộc phải trùng `getOrder`.
- Dữ liệu đáng tin cậy để cấp quyền thao tác.
- Tự động đồng nghĩa với phần tử `wsa:Action` của WS-Addressing.

Spring-WS hỗ trợ mapping theo SOAP action bằng annotation `@SoapAction` khi endpoint mapping liên quan được cấu hình:

~~~java
import javax.xml.transform.Source;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.server.endpoint.annotation.SoapAction;
import org.springframework.xml.transform.StringSource;

@Endpoint
public class ActionBasedOrderEndpoint {

    @SoapAction("urn:example:orders:GetOrder")
    @ResponsePayload
    public Source byAction(@RequestPayload Source request) {
        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>FOUND</o:status>" +
                "</o:GetOrderResponse>");
    }
}
~~~

Đây là **phương án minh họa thay thế** cách định tuyến `GetOrder` ở mục 5.2, không phải một endpoint bổ sung nên đăng ký song song với cùng operation khi chưa xác định rõ thứ tự và strategy của các `EndpointMapping`. Nếu nhiều mapping có thể chọn các handler khác nhau, cần quy định cơ chế định tuyến rõ ràng, tránh phụ thuộc vào thứ tự ngầm không được kiểm thử.

### 6.1. Nếu SOAPAction và Body không nhất quán?

Ví dụ:

~~~http
SOAPAction: "urn:example:orders:GetOrder"
~~~

nhưng Body lại là:

~~~xml
<o:CancelOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>ORD-1001</o:orderId>
</o:CancelOrderRequest>
~~~

**Không có một kết quả duy nhất đúng cho mọi ứng dụng Spring-WS.** Với mapping theo QName, Body có thể khiến `cancelOrder` được chọn. Với mapping theo action hoặc gateway định tuyến theo action, request có thể đi nhánh khác hoặc bị từ chối. Nếu bật các cơ chế kiểm tra tính nhất quán trong middleware hoặc endpoint, request có thể bị báo lỗi.

Vì vậy:

1. Xác định **mapping strategy** thực sự đang sử dụng.
2. Đồng bộ `soapAction` trong WSDL, header action client gửi và phần tử request được định nghĩa trong XSD.
3. Thêm kiểm thử cố ý gửi **action của A + Body của B**, nhất là với operation có tác dụng phụ.
4. Không dùng giá trị SOAPAction mà client tự đặt làm bằng chứng một thao tác đã được xác thực hoặc cho phép.

### 6.2. SOAP 1.2 và WS-Addressing

SOAP 1.2 dùng Envelope namespace `http://www.w3.org/2003/05/soap-envelope` và HTTP media type thường là `application/soap+xml`. Action, khi có, thường được biểu diễn qua tham số `action` của media type:

~~~http
Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:GetOrder"
~~~

Không áp dụng máy móc `SOAPAction` header của SOAP 1.1 cho mọi SOAP 1.2 client. Ngoài ra, `wsa:Action` là phần tử SOAP Header thuộc WS-Addressing, chịu quy tắc của thông số kỹ thuật/policy riêng. SOAP 1.2 action và WS-Addressing action có thể cần tương thích nhau theo hợp đồng, nhưng **không phải cùng một vị trí dữ liệu**.

## 7. Đọc WSDL để biết URL, binding và operation

Trong WSDL 1.1, cần phân biệt **định nghĩa trừu tượng** với **cách gọi cụ thể**:

~~~mermaid
flowchart TD
    A["wsdl:types — XSD elements"] --> B["wsdl:message"]
    B --> C["wsdl:portType — GetOrder / CancelOrder"]
    C --> D["wsdl:binding — document/literal, HTTP transport, SOAP action"]
    D --> E["wsdl:service / wsdl:port"]
    E --> F["soap:address — URL endpoint"]
~~~

Ví dụ trích đoạn WSDL 1.1:

~~~xml
<wsdl:binding name="OrdersSoap11Binding"
              type="tns:OrdersPort">
    <soap:binding
        style="document"
        transport="http://schemas.xmlsoap.org/soap/http"/>

    <wsdl:operation name="GetOrder">
        <soap:operation
            soapAction="urn:example:orders:GetOrder"/>
        <wsdl:input><soap:body use="literal"/></wsdl:input>
        <wsdl:output><soap:body use="literal"/></wsdl:output>
    </wsdl:operation>

    <wsdl:operation name="CancelOrder">
        <soap:operation
            soapAction="urn:example:orders:CancelOrder"/>
        <wsdl:input><soap:body use="literal"/></wsdl:input>
        <wsdl:output><soap:body use="literal"/></wsdl:output>
    </wsdl:operation>
</wsdl:binding>

<wsdl:service name="OrderService">
    <wsdl:port name="OrdersSoap11Port"
               binding="tns:OrdersSoap11Binding">
        <soap:address
            location="https://api.example.test/ws/orders"/>
    </wsdl:port>
</wsdl:service>
~~~

Đây là **đoạn trích**, không phải tài liệu WSDL hoàn chỉnh. Trong `wsdl:definitions` thực tế cần khai báo prefix `wsdl`, `soap`, `tns` và các phần `types`, `message`, `portType` tương ứng. `type="tns:OrdersPort"` phải tham chiếu portType có tên và namespace đúng.

Ý nghĩa:

| Trường WSDL | Giá trị minh họa | Tầng được mô tả |
| --- | --- | --- |
| `wsdl:binding/@type` | `tns:OrdersPortType` | Gắn binding với operation trừu tượng |
| `soap:binding/@style` | `document` | Kiểu đóng gói SOAP |
| `soap:body/@use` | `literal` | Payload theo schema/literal |
| `soap:binding/@transport` | `http://schemas.xmlsoap.org/soap/http` | SOAP-over-HTTP transport binding |
| `soap:operation/@soapAction` | Hai URI riêng cho hai operation | Action |
| `soap:address/@location` | `https://api.example.test/ws/orders` | URL HTTP(S) thực sự |

**Hai operation dùng chung một `soap:address` là cấu hình hoàn toàn bình thường.** Chính WSDL message và XSD cung cấp hình dạng payload để client gửi đúng SOAP Body. Một client sinh mã từ WSDL có thể có hai method Java khác nhau nhưng cả hai cùng dùng URL ở `soap:address`.

## 8. Định tuyến ở proxy hoặc gateway không nhất thiết giống Spring-WS

Trong hệ thống doanh nghiệp, request có thể đi qua ingress, API gateway hoặc reverse proxy trước khi đến Spring-WS:

~~~text
Client
  POST https://api.example.test/soap/orders
    |
    v
Gateway:
  /soap/orders -> http://order-service:8080/ws/orders
    |
    v
MessageDispatcherServlet (/ws/*)
    |
    v
EndpointMapping theo SOAP payload QName
~~~

Gateway thường quyết định upstream bằng **host/path/method**. Một số sản phẩm cũng hỗ trợ định tuyến theo HTTP header, SOAP action hoặc kiểm tra XML, nhưng **đó là cấu hình sản phẩm cụ thể**, không phải hành vi mặc định của mọi reverse proxy.

Giả sử gateway đưa toàn bộ `/soap/*` tới một ứng dụng Spring-WS có servlet mapping `/ws/*`. Nếu không có quy tắc bổ sung, đường dẫn bên ngoài chỉ quyết định **đưa request tới đâu**, còn Spring-WS bên trong vẫn có thể chọn `CancelOrderRequest` theo QName, ngay cả khi client đặt path gần giống tên operation khác.

### 8.1. Một nguy cơ: nhầm URL với giới hạn operation

Giả sử ứng dụng công bố:

- `/soap/orders-read` cho client chỉ đọc.
- `/soap/orders-write` cho client có quyền ghi.

Nếu cả hai URL được gateway chuyển về **cùng một `MessageDispatcherServlet` và cùng tập endpoint mappings**, việc gửi `CancelOrderRequest` vào URL `/soap/orders-read` **có thể vẫn được Spring-WS dispatch tới operation hủy**, trừ khi hạ tầng có cơ chế ràng buộc URL, operation và quyền truy cập.

Không thể coi tên URL `orders-read` là cơ chế authorization đủ mạnh. Cần áp dụng **phân quyền dựa trên danh tính và operation/nghiệp vụ thật sự**, có thể kết hợp gateway policy, endpoint security và WS-Security theo yêu cầu.

### 8.2. Không để WSDL công bố địa chỉ nội bộ

Nếu WSDL được tải qua gateway mà `soap:address` lại là:

~~~xml
<soap:address
    location="http://order-service:8080/ws/orders"/>
~~~

client bên ngoài có thể không gọi được. Cần cấu hình URL public, xử lý forwarded headers từ proxy tin cậy và kiểm tra cơ chế chuyển đổi WSDL location nếu sử dụng `MessageDispatcherServlet.setTransformWsdlLocations(true)`.

Lưu ý: việc **đổi location trong WSDL** không tự tạo route ở gateway hoặc đổi servlet mapping. WSDL công bố và hạ tầng thực tế phải được kiểm tra cùng nhau.

## 9. Tính nhất quán giữa routing, validation và JAXB

Một thông điệp có thể đi đúng HTTP URL và đúng endpoint mapping nhưng vẫn **không hợp lệ theo XSD**:

~~~xml
<o:CancelOrderRequest xmlns:o="urn:example:orders:v1">
    <!-- thiếu orderId mà schema yêu cầu -->
</o:CancelOrderRequest>
~~~

`@PayloadRoot` chỉ so khớp QName của request element; nó **không tự kiểm tra đầy đủ** `xs:sequence`, kiểu dữ liệu, `minOccurs`, `nillable` hay facet của các phần tử con. XSD validation cần được đăng ký, ví dụ bằng `PayloadValidatingInterceptor` trong Spring-WS.

Tương tự, JAXB unmarshalling biến XML thành object Java theo mapping đã sinh, nhưng việc tạo được object **không thay thế toàn bộ schema validation**. Với SOAP document/literal, hãy kiểm tra ít nhất:

1. **SOAP version và Envelope namespace** đúng binding.
2. **Root QName** trong Body khớp operation đã công bố.
3. **Cấu trúc payload XML** hợp XSD.
4. **Header/action** tương thích chính sách của dịch vụ.
5. **Quyền gọi operation và điều kiện nghiệp vụ** được kiểm tra trước khi thao tác có tác dụng phụ.

Trong Spring-WS, chuỗi interceptor có thể thực hiện XSD validation, WS-Security, tracing và các kiểm tra chung trước endpoint. Nhưng thứ tự xử lý và cách trả SOAP Fault cần được cấu hình/kiểm thử: không mặc định mọi lỗi validator hoặc security đều thành cùng một Fault nghiệp vụ.

## 10. SOAP Fault, lỗi HTTP và lỗi định tuyến

Khi client “không gọi được operation”, xác định thất bại xảy ra **trước** hay **sau** khi request đi vào Spring-WS.

| Dấu hiệu | Tầng cần xem đầu tiên | Diễn giải và hướng xử lý |
| --- | --- | --- |
| HTTP 404 từ gateway | URL/gateway/servlet mapping | Route không tìm thấy; không đủ chứng minh payload sai |
| HTTP 405 | HTTP method/servlet | Có thể dùng GET sai nơi hoặc POST vào URL WSDL |
| HTTP 415 | Content-Type/SOAP binding | Kiểm tra SOAP 1.1 `text/xml` và SOAP 1.2 `application/soap+xml` |
| SOAP `VersionMismatch` | SOAP processor | Envelope namespace không tương thích |
| Log “No endpoint mapping found” | `EndpointMapping` | So sánh root QName, action và mapping được đăng ký |
| Lỗi XSD validation | Interceptor/schema | Root có thể đúng nhưng phần tử con sai hoặc thiếu |
| SOAP `MustUnderstand` | SOAP Header processing | Header bắt buộc không được node đích hiểu/xử lý |
| HTTP 500 + SOAP Fault | Tầng SOAP/endpoint/security | Đọc Fault code, reason và detail theo SOAP version |
| HTTP 500 + HTML | Web server/proxy | Không cố parse HTML thành `SoapFault` |
| HTTP 502/504 | Gateway/upstream | Kiểm tra kết nối và thời hạn chờ giữa gateway và dịch vụ |
| DNS/TCP/TLS failure | Kết nối trước HTTP | Không có SOAP response hợp lệ để đọc |

Với SOAP 1.1 over HTTP, SOAP Fault thường đi kèm HTTP 500 theo binding; SOAP 1.2 có quy tắc HTTP status khác. **Không suy từ HTTP 500 rằng chắc chắn có SOAP Fault**. Cũng không thể khẳng định một request đã thất bại nghiệp vụ hay chưa nếu chỉ thấy read timeout sau khi gửi một operation ghi dữ liệu.

### 10.1. Hai loại “không tìm thấy” khác nhau

**Tình huống A — URL HTTP không được phục vụ:**

~~~http
POST /unknown/orders HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
~~~

Gateway/Servlet container có thể trả HTTP 404 trước khi SOAP dispatcher đọc Body. Sửa URL hoặc route, không chỉ đổi `GetOrderRequest` sang `CancelOrderRequest`.

**Tình huống B — đã vào SOAP dispatcher nhưng không có endpoint khớp:**

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v2">
    <soap:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

HTTP URL có thể đúng `/ws/orders`, nhưng root QName là `{urn:example:orders:v2}GetOrderRequest`, không khớp annotation đòi `v1`. Hệ thống có thể báo không tìm thấy endpoint SOAP và trả phản hồi lỗi tùy implementation/configuration, **không được tự quy mọi trường hợp này thành HTTP 404**.

## 11. Bảo mật: không tin URL hoặc SOAPAction thay cho kiểm tra operation

Với operation chỉ đọc, lỗi định tuyến có thể làm truy vấn sai. Với operation có tác dụng phụ như `CancelOrder`, `CreateInvoice` hay `TransferFunds`, lỗi bảo mật do nhầm tầng routing có thể nghiêm trọng hơn.

Các nguyên tắc cần tuân thủ:

- **Xác thực danh tính** tại lớp phù hợp: TLS/mTLS, HTTP authentication, WS-Security token/chữ ký theo contract.
- **Ủy quyền theo operation/ngữ nghĩa nghiệp vụ**, không chỉ dựa vào path `/ws/orders` hoặc chuỗi `SOAPAction` do client gửi.
- **Kiểm tra tính toàn vẹn** của thông điệp khi policy yêu cầu; nếu dựa vào chữ ký WS-Security, chỉ tin những phần được ký và xác thực đúng.
- **Xác thực XSD** để tránh dữ liệu không hợp lệ, nhưng không nhầm schema validation với authentication/authorization.
- **Giới hạn kích thước XML, bảo vệ parser** trước external entities/DTD hoặc tài nguyên ngoài không được phép.
- **Không log toàn bộ SOAP Header/Body mặc định**: message có thể chứa token, chữ ký, thông tin cá nhân hoặc dữ liệu thanh toán.
- **Chống thực hiện trùng** cho operation ghi khi client retry sau read timeout; correlation ID chỉ giúp truy vết, không tự bảo đảm idempotency.

Nếu một reverse proxy thực hiện bảo mật theo URL và ứng dụng Spring-WS định tuyến theo payload mà không ràng buộc đường dẫn, cần thiết kế chính sách thống nhất và **kiểm thử gửi operation bị cấm qua từng URL có thể vào servlet**. Một URL đẹp hoặc một WSDL phân tách không thay thế quyền hạn runtime.

## 12. Quy trình chẩn đoán định tuyến theo tầng

Giả sử client gọi `CancelOrder` nhưng không nhận response mong đợi. Có thể lần lượt kiểm tra:

1. **Đường truyền:** DNS, TCP, TLS, HTTP Host, port và URL request thực sự.
2. **Gateway/Servlet mapping:** request có đến `MessageDispatcherServlet` không? Nếu dùng Spring Boot, `spring.webservices.path` có hiệu lực với servlet nào?
3. **WSDL đã công bố:** `soap:address` là gì? WSDL binding là SOAP 1.1 hay SOAP 1.2? Operation `CancelOrder` có action nào?
4. **HTTP metadata:** method POST, `Content-Type`, `SOAPAction` hoặc SOAP 1.2 action đúng hợp đồng không?
5. **SOAP Envelope:** namespace Envelope đúng version, Body có root QName gì?
6. **EndpointMapping:** ứng dụng có `@Endpoint` được scan không? `@PayloadRoot` hoặc `@SoapAction` có khớp không? Có nhiều mapping strategy cạnh tranh không?
7. **Interceptor:** request có bị chặn bởi WS-Security, `mustUnderstand` hay XSD validation trước khi vào endpoint không?
8. **Nghiệp vụ và response:** operation đã thực hiện tới bước nào? Có SOAP Fault, HTTP error hay timeout? Nếu không rõ kết quả thao tác ghi, cần đối soát trước retry.

Nên ghi log có kiểm soát gồm **request/correlation ID, host/path, SOAP version, payload QName, action, HTTP status, fault code và thời lượng**. Đây là những trường đủ hữu ích để xác định tầng lỗi mà thường không cần dump toàn bộ XML chứa dữ liệu nhạy cảm.

## 13. Kiểm thử: tách kiểm thử SOAP routing khỏi HTTP routing

### 13.1. Kiểm thử Spring-WS endpoint bằng mock

`MockWebServiceClient` có thể kiểm tra cách Spring-WS chọn endpoint dựa trên SOAP payload mà không cần khởi động cổng HTTP thực. Tư duy test:

~~~text
Given:
  - Spring context chứa @Endpoint cho GetOrder và CancelOrder.
  - Endpoint mapping theo payload QName đã được kích hoạt.
When:
  - Gửi {urn:example:orders:v1}GetOrderRequest.
Then:
  - Nhận GetOrderResponse.

When:
  - Gửi {urn:example:orders:v1}CancelOrderRequest.
Then:
  - Nhận CancelOrderResponse.
~~~

Để kiểm tra hành vi thật, dùng XSD request/response và test theo namespace-aware XML assertion. Test chỉ gọi Java method trực tiếp **không kiểm tra được** cơ chế `EndpointMapping` của Spring-WS.

### 13.2. Kiểm thử HTTP bằng môi trường tích hợp

Các tình huống sau cần gửi request qua Servlet container hoặc gateway thử nghiệm:

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| POST `/ws/orders` với `GetOrderRequest` | Vào SOAP servlet, chọn `getOrder` |
| POST `/ws/orders` với `CancelOrderRequest` | Cùng URL, chọn `cancelOrder` |
| POST `/unknown/orders` | Thất bại ở URL routing nếu không có route |
| POST nhầm `/ws/orders.wsdl` | Không tự giả định URL WSDL nhận SOAP POST |
| Đổi prefix `o` nhưng giữ namespace URI | Không làm thay đổi QName, routing không bị ảnh hưởng |
| Đổi namespace `v1` thành `v2` | Không còn khớp `@PayloadRoot` của `v1` |
| SOAPAction của `GetOrder` + Body `CancelOrderRequest` | Bộc lộ mapping strategy và quy tắc kiểm tra nhất quán |
| Gửi SOAP 1.2 vào endpoint chỉ hỗ trợ SOAP 1.1 | Báo lỗi tương thích SOAP version/binding |
| Payload đúng root nhưng sai cấu trúc con | Bị validator từ chối nếu validation bật |
| Request thiếu token/chữ ký WS-Security | Bị từ chối theo policy trước nghiệp vụ |
| Chuyển URL qua gateway có prefix rewrite | WSDL public và URL thực sự truy cập được phải khớp |
| Gửi operation ghi vào URL chỉ đọc | Hệ thống **không** cho phép vượt quyền qua content routing |
| Read timeout sau operation ghi | Không tự retry khi outcome chưa xác định |

Các mock tests về payload không thay thế bài thử HTTP, vì chúng thường không đi qua Servlet URL mapping, gateway, DNS, TLS hay HTTP status thật.

### 13.3. Ví dụ hai request `curl`

Lưu request SOAP `GetOrder` ở `get-order.xml` và `CancelOrder` ở `cancel-order.xml` rồi chạy:

~~~bash
curl -i -X POST "http://localhost:8080/ws/orders" \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: "urn:example:orders:GetOrder"' \
  --data-binary @get-order.xml
~~~

~~~bash
curl -i -X POST "http://localhost:8080/ws/orders" \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: "urn:example:orders:CancelOrder"' \
  --data-binary @cancel-order.xml
~~~

Hai lệnh đều POST **cùng URL**, chỉ khác action và nội dung Body. Nếu chỉ dùng `@PayloadRoot` như ví dụ mục 5, điểm quyết định được nhấn mạnh là **QName của request**. Khi dùng chính sách xác minh action hoặc mapping theo action, kết quả còn phụ thuộc cấu hình.

Trên PowerShell, tùy môi trường `curl` có thể là alias; có thể dùng `curl.exe` khi cần chương trình cURL chuẩn. Đây là lệnh hướng dẫn thực hành, không phải thao tác đã được chạy trong bài.

## 14. Bài tập tình huống: tại sao đổi URL không đổi operation?

Một dự án đăng ký `MessageDispatcherServlet` trên `/soap/*` và có hai handler:

~~~java
@PayloadRoot(namespace = "urn:example:bank:v1",
             localPart = "GetBalanceRequest")
public Source getBalance(@RequestPayload Source request) { /* ... */ }

@PayloadRoot(namespace = "urn:example:bank:v1",
             localPart = "TransferFundsRequest")
public Source transfer(@RequestPayload Source request) { /* ... */ }
~~~

Trong thực tế, code trên chỉ là **trích đoạn minh họa**: một method có `Source` return phải có implementation hợp lệ và `@ResponsePayload` khi trả payload. Ngữ cảnh giả định class chứa hai method đã được đăng ký như một `@Endpoint`.

Client gửi:

~~~http
POST /soap/balance HTTP/1.1
Host: bank.example.test
Content-Type: text/xml
SOAPAction: "urn:example:bank:GetBalance"
~~~

nhưng SOAP Body:

~~~xml
<b:TransferFundsRequest xmlns:b="urn:example:bank:v1">
    <b:transactionId>TX-1001</b:transactionId>
    <b:amount>100.00</b:amount>
</b:TransferFundsRequest>
~~~

Hãy trả lời:

1. Nếu `/soap/balance` được cùng servlet `/soap/*` phục vụ và mapping theo `@PayloadRoot`, operation nào có khả năng được chọn?
2. Đổi URL thành `/soap/transfer` có phải cách bắt buộc để chọn `transfer` không?
3. Có thể cho phép transfer chỉ dựa trên SOAPAction hoặc path `/soap/transfer` không?
4. Cần kiểm thử và bổ sung những biện pháp nào trước khi triển khai nghiệp vụ chuyển tiền?

**Đáp án gợi ý:**

1. **`transfer`** có thể được chọn vì root QName là `{urn:example:bank:v1}TransferFundsRequest`. Tuy nhiên, interceptor/mapping bổ sung có thể chặn mismatch hoặc chọn theo tiêu chí khác.
2. **Không.** Với content-based routing theo QName, URL trước hết chọn servlet; operation được chọn từ payload.
3. **Không.** Path và SOAPAction là thông tin client có thể điều khiển, không đủ làm bằng chứng danh tính hoặc quyền hạn. Cần authn/authz theo operation và dữ liệu được bảo vệ.
4. Cần kiểm tra WS-Security/TLS, payload validation, quyền gọi transfer, tính toàn vẹn, tính nhất quán action–Body, chống trùng bằng transaction ID/idempotency, logging an toàn và thử nghiệm qua gateway thật.

Điểm rút ra: **“đến đúng URL” và “được phép chạy đúng operation” là hai điều kiện độc lập** trong nhiều triển khai SOAP.

## 15. Quy tắc thiết kế cho hệ thống doanh nghiệp

Khi thiết kế SOAP service Spring-WS có nhiều operation và nhiều đối tác:

1. **Thiết kế XSD/WSDL trước**: mỗi operation có global element request/response có QName rõ ràng, binding và action thống nhất.
2. **Chọn mapping strategy có chủ đích**: `@PayloadRoot` cho content QName, `@SoapAction` khi hợp đồng yêu cầu action-based dispatch; tránh sự chồng chéo không được kiểm thử.
3. **Giữ URL endpoint nhất quán**: `soap:address`, Servlet mapping và gateway route cần trỏ đúng nhau; phân biệt URL WSDL và SOAP POST.
4. **Không dùng URL như một “tường lửa operation” ngầm** nếu nhiều path có thể đi vào cùng dispatcher. Thiết kế authz theo người gọi và operation.
5. **Kiểm tra XML theo XSD**, namespace, SOAP version và policy header; có thể dùng interceptor validation/WS-Security phù hợp.
6. **Phân loại lỗi theo tầng**: HTTP routing, SOAP dispatch, XSD validation, SOAP Fault, HTTP proxy và kết nối TLS có triệu chứng/giải pháp khác nhau.
7. **Không đưa thông tin nhạy cảm vào log đầy đủ**; log metadata đủ để tái hiện route và xác định lỗi.
8. **Kiểm thử khác biệt giữa path, action và Body** bằng cả Spring-WS mock và bài thử HTTP(S) thực; đặc biệt với operation có tác dụng phụ.
9. **Quản lý phiên bản contract**: đổi namespace hoặc root element là thay đổi QName có thể làm client cũ không gọi được, dù HTTP URL không đổi.
10. **Kiểm soát retry/idempotency** cho thao tác ghi; timeout không chứng minh request chưa được thực thi.

## 16. Tự kiểm tra

**Câu 1.** Hai SOAP request cùng POST tới `/ws/orders` nhưng Body lần lượt có `GetOrderRequest` và `CancelOrderRequest`. Có bắt buộc chúng cùng gọi một endpoint Java method không?

**Câu 2.** Nếu đổi prefix `o` thành `x` nhưng giữ `urn:example:orders:v1`, `@PayloadRoot` có cần đổi không?

**Câu 3.** Nếu WSDL được tải tại `/ws/orders.wsdl`, client có bắt buộc POST vào URL đó không?

**Câu 4.** Nếu HTTP URL và SOAPAction đều đúng nhưng payload root namespace sai, `@PayloadRoot` có thể chọn method dự kiến không?

**Câu 5.** Có thể dùng `SOAPAction` làm bằng chứng người gọi được phép `CancelOrder` không?

**Câu 6.** Test `MockWebServiceClient` thành công có chứng minh gateway và TLS đã được cấu hình đúng không?

**Đáp án ngắn:**

1. **Không.** Content-based mapping có thể chọn method khác nhau dựa trên payload QName.
2. **Không.** Prefix không định danh QName; namespace URI và local name mới quan trọng.
3. **Không.** Dùng `soap:address/@location` trong WSDL hoặc endpoint URL đã được xác minh.
4. **Không khớp theo QName dự kiến**; cần kiểm tra mapping strategy và namespace thực tế.
5. **Không.** Cần xác thực/ủy quyền độc lập cùng policy bảo mật phù hợp.
6. **Không.** Mock SOAP test không thay thế test Servlet URL mapping, proxy và HTTPS thực.

## 17. Ghi nhớ

- **Định tuyến HTTP** đưa request tới web server/`MessageDispatcherServlet` dựa trên URL, method và quy tắc hạ tầng; **định tuyến SOAP** chọn handler từ nội dung thông điệp hoặc action theo `EndpointMapping`.
- Với **`@PayloadRoot`**, yếu tố quyết định là **QName của phần tử gốc trong SOAP Body**: `{namespace URI}localName`, không phải prefix hay tên Java method.
- **Cùng một URL có thể phục vụ nhiều SOAP operation**. Ngược lại, nhiều URL có thể cùng đi vào một dispatcher; đừng suy ra giới hạn operation chỉ từ path.
- **`SOAPAction` không phải endpoint URL và không thay thế payload QName**. Mapping theo action là một chiến lược riêng, cần kiểm thử tương tác với mapping theo nội dung.
- **XSD/WSDL, JAXB, Servlet mapping, SOAP version và security interceptors** tham gia những giai đoạn khác nhau. Cần thiết kế/kiểm thử nhất quán để tránh lỗi tích hợp.
- Khi chẩn đoán, tách **HTTP 404/405/415**, **không có SOAP endpoint mapping**, **XSD validation**, **SOAP Fault** và **lỗi DNS/TLS/timeout**.
- Trong dịch vụ doanh nghiệp, **phân quyền theo operation, kiểm tra thông điệp và thử nghiệm qua gateway thật** là cần thiết, đặc biệt với SOAP request có tác dụng phụ.
