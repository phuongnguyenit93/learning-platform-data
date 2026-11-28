# Phân biệt Spring-WS với Spring MVC, REST và WebSocket

Khi xây dựng ứng dụng Java, bốn cái tên **Spring Web Services (Spring-WS)**, **Spring MVC**, **REST** và **WebSocket** thường xuất hiện cùng nhau. Tuy nhiên, chúng không phải bốn framework cạnh tranh trực tiếp: Spring-WS và Spring MVC là các thành phần trong hệ sinh thái Spring; REST là một phong cách kiến trúc; còn WebSocket là một giao thức truyền thông hai chiều. Phân biệt đúng cấp độ giúp chọn cách tích hợp, thiết kế hợp đồng và kiểm thử phù hợp.

Trong module **SPRING_WEB_SERVICES**, trọng tâm là xây dựng **dịch vụ SOAP theo hướng contract-first**: bắt đầu từ XSD/WSDL, ánh xạ dữ liệu XML bằng JAXB, triển khai endpoint và SOAP client, xử lý SOAP Fault, interceptor, bảo mật XML/WS-Security, chứng chỉ và kiểm thử tương thích với hệ thống doanh nghiệp. Các công nghệ còn lại được dùng làm đối chiếu để xác định khi nào Spring-WS thực sự cần thiết.

## 1. Bốn khái niệm nằm ở những cấp độ khác nhau

| Khái niệm | Bản chất | Mục đích chính |
| --- | --- | --- |
| **Spring-WS** | Framework hỗ trợ web service dựa trên thông điệp SOAP/XML | Công bố và tiêu thụ dịch vụ SOAP với hợp đồng XSD/WSDL, xử lý SOAP header, SOAP Fault và các yêu cầu WS-* |
| **Spring MVC** | Framework web dựa trên mô hình Servlet MVC | Xử lý HTTP request/response, xây dựng trang web hoặc HTTP API, thường dùng cùng `@RestController` |
| **REST** | Phong cách kiến trúc cho hệ thống phân tán | Tổ chức giao diện quanh tài nguyên, phương thức và ngữ nghĩa HTTP khi triển khai trên HTTP |
| **WebSocket** | Giao thức truyền thông sau bắt tay HTTP | Duy trì kết nối để client và server gửi thông điệp hai chiều theo thời gian thực |

Điểm cần nhớ:

- **Spring MVC có thể dùng để xây dựng REST API**, nhưng hai tên gọi không đồng nghĩa. Một controller trả HTML, tải tệp hoặc xử lý form cũng thuộc Spring MVC, chưa chắc là REST.
- **REST không bắt buộc dùng JSON**. REST API có thể trả XML hoặc định dạng khác. JSON là lựa chọn phổ biến, không phải điều kiện định nghĩa REST.
- **SOAP không đồng nghĩa với Spring-WS**. SOAP là giao thức nhắn tin; Spring-WS là một cách triển khai và sử dụng SOAP trong Spring.
- **WebSocket không phải SOAP hay REST**. Nó giải quyết nhu cầu kết nối hai chiều lâu dài, trong khi SOAP/REST mô tả các kiểu thông điệp hoặc giao diện dịch vụ.

### Bảng so sánh theo khía cạnh triển khai

| Khía cạnh | Spring-WS / SOAP | Spring MVC (thường làm REST API) | Spring WebSocket |
| --- | --- | --- | --- |
| Điểm vào phía server | `MessageDispatcherServlet`, `@Endpoint` | `DispatcherServlet`, `@Controller` / `@RestController` | WebSocket handler hoặc STOMP message handler |
| Cách định tuyến | QName của XML payload, SOAP action hoặc cơ chế mapping hỗ trợ | HTTP path, method, header, tham số… | Đường dẫn kết nối; sau đó định tuyến từng message nếu dùng STOMP |
| Dạng trao đổi phổ biến | SOAP Envelope chứa XML; thường request/response | HTTP request/response với JSON, XML, HTML… | Các frame text/binary qua kết nối còn mở |
| Hợp đồng | XSD + WSDL là trọng tâm; thường thiết kế trước code | HTTP API; có thể đặc tả bằng OpenAPI, không bắt buộc | Thỏa thuận định dạng thông điệp; không có WSDL mặc định |
| Biểu diễn lỗi | SOAP Fault, kết hợp trạng thái HTTP tùy binding | HTTP status cùng response body | Thông điệp lỗi ứng dụng và/hoặc mã đóng kết nối |
| Bảo mật đặc trưng | TLS và có thể WS-Security: ký, mã hóa thông điệp, token, chứng chỉ | TLS, cơ chế xác thực/ủy quyền HTTP, OAuth2/JWT… | TLS (`wss://`), xác thực kết nối và phân quyền thông điệp |
| Nhu cầu điển hình | Tích hợp hệ thống doanh nghiệp có hợp đồng SOAP, yêu cầu WS-* | Web app và API tài nguyên | Chat, thông báo, bảng điều khiển cập nhật liên tục |

Đây là các **mô hình thường gặp**, không phải giới hạn tuyệt đối: SOAP có thể chạy trên transport khác HTTP; Spring MVC có thể nhận XML; và WebSocket có thể truyền JSON hay dữ liệu nhị phân.

## 2. Spring-WS giải quyết bài toán gì?

Giả sử hệ thống quản lý đơn hàng phải tích hợp với một đối tác bảo hiểm. Đối tác yêu cầu các thao tác `GetOrder`, `SubmitClaim`, yêu cầu và phản hồi phải theo XML Schema cụ thể, lỗi nghiệp vụ phải là SOAP Fault, và thông điệp phải được ký bằng chứng chỉ. Nếu chỉ tạo một HTTP endpoint trả JSON, hệ thống sẽ không đáp ứng hợp đồng đã thống nhất.

**Spring-WS hướng vào thông điệp và hợp đồng XML.** Cách làm phổ biến là **contract-first**:

1. Thiết kế **XSD** để định nghĩa namespace, phần tử, kiểu dữ liệu và các ràng buộc của request/response.
2. Công bố **WSDL** để mô tả operations, messages, binding và địa chỉ dịch vụ; có thể dùng WSDL cố định hoặc tạo WSDL từ XSD theo cấu hình.
3. Sinh hoặc chuẩn bị các lớp **JAXB** tương ứng với XSD; lớp Java là biểu diễn lập trình của hợp đồng XML.
4. Viết endpoint Spring-WS xử lý phần **SOAP Body**; bổ sung xử lý header, SOAP Fault, interceptor và WS-Security khi cần.
5. Dùng SOAP client để gửi đúng Envelope và kiểm thử khả năng tương thích với hệ thống thực tế.

Luồng điển hình khi SOAP chạy trên HTTP:

~~~mermaid
flowchart LR
    A["SOAP client<br/>JAXB / WebServiceTemplate"] -->|SOAP Envelope qua HTTPS| B["MessageDispatcherServlet"]
    B --> C["MessageDispatcher<br/>Endpoint mapping"]
    C --> D["@Endpoint<br/>@PayloadRoot"]
    D --> E["Dịch vụ nghiệp vụ"]
    E --> D
    D -->|Payload phản hồi| C
    C -->|SOAP Response hoặc Fault| A
~~~

`MessageDispatcherServlet` phụ trách tiếp nhận request tại URL servlet đã cấu hình. `MessageDispatcher` cùng các endpoint mapping tìm phương thức xử lý thông điệp. Đây là pipeline của **Spring-WS**, khác với `DispatcherServlet` và cơ chế chọn controller của **Spring MVC**.

### 2.1. XSD là hợp đồng dữ liệu, không phải lớp Java

Ví dụ rút gọn cho thao tác truy vấn trạng thái đơn hàng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="https://example.org/orders/v1"
           xmlns:tns="https://example.org/orders/v1"
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
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Theo hợp đồng này, phần thân của yêu cầu SOAP 1.1 có thể như sau:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="https://example.org/orders/v1">
    <soapenv:Header/>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>O-1024</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Tên namespace và tên phần tử XML tham gia xác định thông điệp; chỉ thay prefix `ord` bằng một prefix khác vẫn có thể hợp lệ nếu URI namespace giữ nguyên. Ngược lại, đổi `https://example.org/orders/v1` hoặc `GetOrderRequest` có thể khiến endpoint không được chọn hoặc payload không còn khớp schema.

**WSDL** mô tả dịch vụ ở cấp cao hơn XSD: phần `types` tham chiếu định nghĩa dữ liệu, còn các thành phần tương ứng định nghĩa thông điệp, operation, binding (ví dụ SOAP/HTTP) và endpoint mà client sẽ gọi. Một số dự án duy trì WSDL tĩnh như một tạo tác có phiên bản; Spring-WS cũng hỗ trợ cấu hình để tạo WSDL 1.1 từ XSD.

### 2.2. Endpoint Spring-WS làm việc với XML payload

Ví dụ sau giả định đã tạo các lớp `GetOrderRequest` và `GetOrderResponse` từ XSD thông qua công cụ JAXB và đã cấu hình marshalling phù hợp:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String NAMESPACE = "https://example.org/orders/v1";
    private final OrderService orderService;

    public OrderEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NAMESPACE, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(@RequestPayload GetOrderRequest request) {
        GetOrderResponse response = new GetOrderResponse();
        response.setStatus(orderService.getStatus(request.getOrderId()));
        return response;
    }
}
~~~

Các annotation có ý nghĩa riêng:

- `@Endpoint`: đánh dấu thành phần xử lý thông điệp Spring-WS.
- `@PayloadRoot`: chọn phương thức dựa trên **QName của phần tử gốc trong SOAP Body**, gồm namespace và local name.
- `@RequestPayload` và `@ResponsePayload`: ánh xạ payload đầu vào/đầu ra; JAXB có thể biến XML thành đối tượng Java và ngược lại.

Endpoint không cần phân tích chuỗi XML bằng tay. Tuy nhiên, mã ví dụ chỉ là **một thành phần** của ứng dụng: muốn chạy còn cần servlet SOAP, JAXB marshaller, XSD/WSDL, cấu hình Bean và lớp `OrderService` thích hợp.

Ví dụ cấu hình xuất WSDL động từ XSD:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@EnableWs
@Configuration
public class SoapContractConfig {
    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(new ClassPathResource("orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
        wsdl.setPortTypeName("OrdersPort");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace("https://example.org/orders/v1");
        wsdl.setSchema(ordersSchema);
        return wsdl;
    }
}
~~~

Giả sử `MessageDispatcherServlet` được ánh xạ tới `/ws/*` và XSD nằm trên classpath ở tên `orders.xsd`, tài liệu WSDL có thể được công bố tại `/ws/orders.wsdl`. Đường dẫn thực tế phụ thuộc cấu hình servlet và môi trường triển khai; **không nên xem URL ví dụ là mặc định cố định của Spring-WS**. Khi cung cấp API cho đối tác, cần quản lý ổn định cả nội dung WSDL lẫn địa chỉ dịch vụ.

### 2.3. SOAP client dùng cùng hợp đồng

Phía client, Spring-WS cung cấp `WebServiceTemplate` để gửi/nhận SOAP, quản lý marshalling, transport và xử lý lỗi. Ví dụ khi `WebServiceTemplate` đã được cấu hình `Jaxb2Marshaller`:

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("O-1024");

GetOrderResponse response = (GetOrderResponse) webServiceTemplate
        .marshalSendAndReceive("https://partner.example.org/ws", request);

System.out.println(response.getStatus());
~~~

Trong thực tế, một số dịch vụ SOAP 1.1 yêu cầu HTTP header `SOAPAction`; có thể cấu hình `SoapActionCallback` khi gửi. Client cũng cần đúng SOAP version, namespace, chứng chỉ, timeout và quy tắc xác thực. Không nên mặc định chỉ có JAXB là đủ để gọi được dịch vụ bên ngoài.

## 3. Spring-WS khác Spring MVC ở đâu?

**Spring MVC được thiết kế quanh HTTP và mô hình controller.** Nó phù hợp để xử lý URL, phương thức HTTP, query parameter, path variable, header, request body, response body và các thao tác web. Một REST API thường được triển khai như sau:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderRestController {
    private final OrderService orderService;

    public OrderRestController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderView getOrder(@PathVariable String id) {
        return new OrderView(id, orderService.getStatus(id));
    }
}
~~~

Nếu client gọi `GET /api/orders/O-1024` và ứng dụng cấu hình chuyển đổi JSON, phản hồi có thể là:

~~~json
{
  "id": "O-1024",
  "status": "CONFIRMED"
}
~~~

Ở ví dụ này, Spring MVC chọn handler theo **HTTP method + URL**. Spring-WS chọn endpoint theo **thông điệp SOAP**, thường từ QName trong Body. Dù cả hai đều có thể dùng HTTP và XML, cách mô hình hóa hợp đồng và xử lý thông điệp khác nhau:

| Câu hỏi | Spring-WS | Spring MVC |
| --- | --- | --- |
| Tôi đang xử lý phần tử XML nào? | Thường dùng `@PayloadRoot` | Có thể tự phân tích XML hoặc map body, nhưng không mặc định theo SOAP Body |
| Hợp đồng nào mô tả operation? | WSDL, dựa trên các message/type trong XSD | Thường mô tả endpoint HTTP; OpenAPI là lựa chọn phổ biến |
| Cần SOAP Header / Fault / WS-Security? | Có mô hình và interceptor chuyên biệt | Phải tự bổ sung hoặc dùng một SOAP stack riêng |
| Cần HTTP resource, query, cookie, status, content negotiation? | Không phải trọng tâm | Là khả năng cốt lõi |

**Không nên chỉ viết `@PostMapping` nhận chuỗi SOAP rồi gọi đó là giải pháp tương đương Spring-WS.** Cách xử lý thủ công có thể dùng cho trường hợp rất hẹp, nhưng các việc như kiểm tra SOAP Envelope, dispatch theo QName, tạo SOAP Fault, xử lý header và tiêu chuẩn WS-* sẽ nhanh chóng trở thành mã tự xây dựng khó duy trì.

Một ứng dụng Spring Boot có thể triển khai **cả hai**: chẳng hạn `/api/*` phục vụ HTTP API qua Spring MVC, còn `/ws/*` phục vụ SOAP qua Spring-WS. Cần cấu hình các servlet mapping và bảo mật tương ứng để tránh xung đột URL.

## 4. REST khác SOAP như thế nào?

**REST** mô tả những ràng buộc kiến trúc như client–server, stateless, cacheability, layered system và **uniform interface**. Trong HTTP API thiết kế theo REST, ta thường thao tác trên **tài nguyên**:

~~~http
GET /api/orders/O-1024 HTTP/1.1
Host: api.example.org
Accept: application/json
~~~

Tài nguyên là `/api/orders/O-1024`; `GET` mang ngữ nghĩa đọc và an toàn theo định nghĩa HTTP. Các thao tác thêm/cập nhật/xóa thường được mô hình hóa bằng `POST`, `PUT`, `PATCH`, `DELETE` đúng ngữ nghĩa. Caching và conditional request có thể tận dụng HTTP khi triển khai phù hợp; chúng không tự động xuất hiện chỉ vì API sử dụng JSON.

**SOAP** quy định cấu trúc thông điệp với Envelope, Header và Body, cùng một mô hình Fault. Khi kết hợp WSDL, phía client có thể xác định operation và cấu trúc request/response theo hợp đồng. SOAP qua HTTP thường dùng `POST`, nhưng SOAP **không bị giới hạn về mặt khái niệm ở HTTP hoặc POST**; transport và binding cụ thể do dịch vụ quyết định.

Ví dụ tương quan cùng một mục đích nghiệp vụ:

| Tìm trạng thái đơn hàng | HTTP API theo REST | Dịch vụ SOAP |
| --- | --- | --- |
| Ý định | Đọc tài nguyên đơn hàng | Gọi operation `GetOrder` |
| Dữ liệu đầu vào | ID trong URL | `GetOrderRequest` trong SOAP Body |
| Phản hồi | Biểu diễn tài nguyên, thường JSON | `GetOrderResponse` trong SOAP Envelope |
| Đặc tả | API docs/OpenAPI nếu có | XSD/WSDL thường là hợp đồng tích hợp |
| Lỗi không tìm thấy | Có thể trả HTTP `404` cùng body lỗi | Có thể trả một SOAP Fault theo quy ước hợp đồng |

Không nên diễn giải rằng **mọi API trả JSON đều REST**, hay **mọi HTTP API trả XML đều SOAP**. Điều quyết định là quy tắc giao tiếp và hợp đồng, không phải chỉ định dạng dữ liệu.

### SOAP Fault và HTTP status không thay thế cho nhau

Với SOAP 1.1, một Fault có thể có dạng:

~~~xml
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Order ID không hợp lệ</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
~~~

SOAP 1.2 có cấu trúc Fault khác, ví dụ `Code` và `Reason`. Ở binding HTTP, SOAP Fault thường đi cùng mã HTTP lỗi theo quy tắc binding, nhưng **mã HTTP không mô tả đầy đủ ý nghĩa lỗi SOAP**. Client SOAP phải đọc Fault trong Envelope thay vì chỉ nhìn `200` hay `500`.

Spring-WS hỗ trợ cơ chế xử lý exception và ánh xạ thành SOAP Fault, chẳng hạn `SoapFaultMappingExceptionResolver`. Quy ước thông điệp Fault, mã lỗi nghiệp vụ và mức chi tiết trả về cần được thống nhất với phía tiêu thụ dịch vụ; không đưa stack trace hoặc bí mật vào phản hồi.

## 5. Spring-WS khác WebSocket ở đâu?

Tên hai công nghệ đều chứa từ “WebSocket/WS” nhưng **“WS” trong Spring-WS là Web Services**, không phải WebSocket.

Khi client thiết lập WebSocket, hai bên thường bắt đầu bằng HTTP handshake rồi nâng cấp kết nối sang WebSocket (trường hợp triển khai WebSocket qua HTTP/1.1). Sau đó server có thể **chủ động đẩy** thông điệp về client mà không phải đợi một HTTP request mới. Ứng dụng Spring có thể dùng WebSocket trực tiếp hoặc sử dụng STOMP để tổ chức destination, subscription và message handler.

Ví dụ bảng trạng thái đơn hàng ở trình duyệt:

1. Trình duyệt gọi `GET /api/orders/O-1024` để đọc trạng thái hiện tại.
2. Trình duyệt kết nối WebSocket đến `wss://app.example.org/updates` và subscribe theo kênh được cấp quyền.
3. Khi trạng thái chuyển từ `PENDING` sang `CONFIRMED`, server gửi một message cập nhật.
4. Người dùng thấy kết quả mới mà không cần liên tục polling HTTP.

Spring-WS không cung cấp cơ chế push WebSocket kiểu này chỉ vì tên có chữ “WS”. Ngược lại, WebSocket **không mặc định** có XSD, WSDL, SOAP Envelope, SOAP Fault hoặc WS-Security. Nếu muốn truyền thông điệp XML qua WebSocket, ứng dụng vẫn phải tự quy định định dạng và hợp đồng ở tầng ứng dụng.

| Nhu cầu | Spring-WS / SOAP | WebSocket |
| --- | --- | --- |
| Gửi yêu cầu nghiệp vụ và nhận kết quả theo hợp đồng WSDL | Rất phù hợp | Có thể tự xây dựng, nhưng không có sẵn ngữ nghĩa WSDL/SOAP |
| Server gửi hàng loạt cập nhật độc lập về client | Không phải mục tiêu chính trong mô hình SOAP request/response phổ biến | Phù hợp nhờ kết nối hai chiều |
| Tích hợp với đối tác bắt buộc ký SOAP message | Có các thành phần WS-Security chuyên dụng | Phải thiết kế cơ chế riêng nếu cần bảo mật mức thông điệp |
| Duy trì kết nối lâu dài | Thường không cần | Thành phần cốt lõi của mô hình |

WebSocket cũng có chi phí vận hành riêng: quản lý kết nối, heartbeat, reconnect, phân quyền cho subscription, cân bằng tải và phân phối sự kiện giữa nhiều instance. **Chỉ chọn WebSocket nếu nhu cầu cập nhật chủ động hoặc hội thoại hai chiều thực sự tồn tại.**

## 6. Bảo mật và tính tương thích: nơi Spring-WS phát huy giá trị

Trong hệ thống tích hợp doanh nghiệp, bảo mật không dừng ở HTTPS. Cần phân biệt:

- **TLS/HTTPS**: bảo vệ kênh truyền giữa hai điểm kết nối. Dữ liệu được giải mã tại các điểm kết thúc TLS; nếu thông điệp đi qua trung gian, bảo vệ kênh chưa chắc đáp ứng yêu cầu ký thông điệp từ đầu đến cuối.
- **WS-Security**: đặt token, chữ ký số, thông tin mã hóa và dữ liệu bảo mật liên quan trong SOAP Header. Nó có thể bảo vệ tính toàn vẹn và nguồn gốc của những phần thông điệp đã ký, hoặc tính bí mật của những phần đã mã hóa theo chính sách đã thống nhất.
- **Chứng chỉ**: có thể dùng trong TLS hai chiều (mTLS), ký/xác minh SOAP message hoặc mã hóa XML. Mục đích sử dụng, key store và trust store cần cấu hình đúng vai trò; có chứng chỉ chưa có nghĩa là WS-Security đã được áp dụng.

Spring-WS có `Wss4jSecurityInterceptor` để tích hợp các thao tác WS-Security được hỗ trợ, như xác minh chữ ký và xử lý UsernameToken, tùy cấu hình. Interceptor Spring-WS xử lý **thông điệp SOAP**; nó khác Servlet Filter hoặc Spring MVC `HandlerInterceptor` xử lý request web. Với hệ thống thật, cần xác minh các trường quan trọng nằm trong vùng được ký, giới hạn dữ liệu XML và chống replay khi chính sách yêu cầu.

XML có các rủi ro đặc trưng: dữ liệu ngoài mong đợi, tải tài nguyên bên ngoài (XXE nếu parser cấu hình thiếu an toàn), entity expansion, XML payload quá lớn, namespace sai, dữ liệu không đúng schema và chữ ký không hợp lệ. Dùng thư viện đã cập nhật, cấu hình parser an toàn, giới hạn kích thước và xác thực schema/WS-Security theo hợp đồng.

### Tương thích giữa các nền tảng

Một dịch vụ SOAP có thể được tiêu thụ bởi Java, .NET hoặc các sản phẩm ESB. Để tương thích, phải kiểm tra **thông điệp trên dây**, không chỉ kiểm thử phương thức Java:

| Phần cần đối chiếu | Lỗi thường gặp |
| --- | --- |
| Namespace, thứ tự và số lần xuất hiện của element trong XSD | JAXB marshal được nhưng đối tác từ chối vì sai schema |
| WSDL, `soap:binding`, operation, endpoint address | Client sinh từ WSDL gọi sai operation hoặc URL |
| SOAP 1.1 so với SOAP 1.2 | Envelope namespace và `Content-Type`/SOAP action không khớp |
| Kiểu dữ liệu, ngày giờ, timezone, null/optional | Giá trị hợp lệ ở Java nhưng bị diễn giải sai ở hệ khác |
| SOAP Fault và lỗi nghiệp vụ | Client không phân biệt được lỗi dữ liệu, lỗi xác thực và lỗi server |
| Chữ ký, chứng chỉ, encryption, timestamp | Chữ ký không xác minh được hoặc bị từ chối do chính sách bảo mật |
| Attachment/MTOM nếu có | Payload lớn hoặc tệp đính kèm không khớp binding |

Lưu ý phiên bản: các dự án sử dụng Spring Framework 6 / Spring Boot 3 thường làm việc với hệ namespace **`jakarta.xml.bind`**; mã và thư viện cũ có thể còn dùng **`javax.xml.bind`**. Khi sinh JAXB classes từ XSD, phải chọn phiên bản công cụ/phụ thuộc tương thích với runtime; không sửa XSD chỉ để che lỗi lệch phiên bản Java.

## 7. Chọn công nghệ dựa trên hợp đồng và luồng trao đổi

### Tình huống A — Kết nối core banking hoặc bảo hiểm có WSDL

Đối tác cung cấp WSDL/XSD cố định, yêu cầu thao tác `SubmitPayment` và dùng WS-Security để ký thông điệp. **Chọn Spring-WS cho lớp tích hợp SOAP**, vì endpoint/client cần tuân thủ namespace, SOAP Header, Fault và chính sách ký. Bên trong ứng dụng vẫn có thể dùng service Java thông thường để xử lý nghiệp vụ.

### Tình huống B — API quản lý đơn hàng cho ứng dụng di động

Client cần đọc danh sách, tạo và cập nhật tài nguyên đơn hàng qua HTTP; không có yêu cầu WSDL hoặc WS-Security. **Spring MVC với thiết kế HTTP API theo REST** thường dễ triển khai, quản lý status, caching và công cụ API hơn. Nếu hệ thống đang dùng Spring WebFlux, REST API cũng có thể được triển khai ở đó; REST không ràng buộc vào Spring MVC.

### Tình huống C — Giao diện cần thông báo liên tục

Nhân viên vận hành mở dashboard, cần nhận thông báo ngay khi trạng thái thanh toán thay đổi. **WebSocket** thích hợp cho kênh cập nhật. Ứng dụng có thể vẫn dùng Spring MVC để lấy dữ liệu ban đầu và Spring-WS để giao tiếp với một hệ thống thanh toán bên ngoài.

### Tình huống D — Một hệ thống cần cả ba

Không có yêu cầu phải chọn duy nhất một công nghệ. Kiến trúc có thể là:

~~~mermaid
flowchart LR
    U["Web / Mobile client"] -->|HTTP API| M["Spring MVC<br/>/api/*"]
    U <-->|WebSocket / STOMP| W["Spring WebSocket<br/>/updates"]
    M --> S["Application service"]
    W --> S
    S --> C["Spring-WS client<br/>WebServiceTemplate"]
    C <-->|SOAP + WSDL + WS-Security| P["Đối tác doanh nghiệp"]
~~~

Ở thiết kế này, **service nghiệp vụ được dùng chung**, còn từng adapter chịu trách nhiệm giao thức riêng. Tránh để đối tượng JAXB sinh từ XSD trở thành mô hình dữ liệu công khai của mọi REST API hoặc thông điệp WebSocket; việc tách DTO/API model giúp giảm ảnh hưởng khi hợp đồng SOAP thay đổi.

## 8. Những nhầm lẫn cần tránh

1. **“Spring-WS là cách gọi khác của Spring WebSocket.”** Sai. Spring-WS phục vụ SOAP Web Services; WebSocket là giao thức cho kết nối hai chiều.
2. **“Spring MVC không đọc được XML.”** Sai. Spring MVC có thể xử lý XML nếu có converter/serializer phù hợp; nó chỉ không tự đảm nhận toàn bộ ngữ nghĩa SOAP như Spring-WS.
3. **“Cứ dùng POST và trả JSON là REST.”** Chưa đủ. Thiết kế REST phải quan tâm tài nguyên, uniform interface và ngữ nghĩa HTTP.
4. **“WSDL và XSD chỉ cần viết cho có rồi sửa endpoint tùy ý.”** Sai trong tích hợp contract-first. Hợp đồng là giao diện bên ngoài, cần quản lý phiên bản và kiểm tra tương thích.
5. **“Bật HTTPS nghĩa là đã đáp ứng WS-Security.”** Sai. HTTPS và WS-Security bảo vệ ở các tầng khác nhau; yêu cầu chữ ký SOAP message cần xử lý riêng.
6. **“SOAP Fault chỉ là HTTP 500.”** Không chính xác. SOAP Fault có cấu trúc riêng; client phải đọc fault detail và phân biệt SOAP 1.1/1.2 cùng binding đang dùng.
7. **“Test xanh với JAXB tức là tích hợp chắc chắn chạy.”** Chưa đủ. Vẫn cần thử WSDL, schema, SOAP version, message headers, bảo mật, chứng chỉ và client của đối tác.

## 9. Kiểm thử theo đúng lớp giao tiếp

**Với Spring-WS**, nên kiểm thử ít nhất bốn tầng:

1. **Contract**: kiểm tra XSD/WSDL được công bố đúng; payload mẫu hợp lệ, namespace và cardinality chính xác.
2. **Endpoint**: dùng `MockWebServiceClient` để gửi request SOAP giả lập và đối chiếu payload, SOAP Fault hoặc header của phản hồi.
3. **SOAP client**: dùng `MockWebServiceServer` để kiểm tra `WebServiceTemplate` gửi đúng XML, SOAPAction và xử lý phản hồi/Fault.
4. **Interoperability**: gọi thử bằng công cụ hoặc client thực tế của đối tác, gồm các trường hợp thành công, lỗi nghiệp vụ, chữ ký sai, chứng chỉ hết hạn, timeout và phiên bản SOAP không khớp.

Với **Spring MVC**, có thể kiểm tra routing, validation, serialization và HTTP status bằng `MockMvc` hoặc integration test. Với **WebSocket**, cần kiểm tra handshake, xác thực, subscription, thứ tự thông điệp (nếu ứng dụng yêu cầu), reconnect và hành vi khi mất kết nối. Bộ test của từng công nghệ phản ánh khác biệt về **giao thức và hợp đồng**; không nên dùng duy nhất unit test service Java để thay thế.

## 10. Cách ra quyết định nhanh trong dự án

Hãy bắt đầu từ **đặc tả mà hệ thống bên ngoài yêu cầu**:

- Nếu phải trao đổi **SOAP Envelope theo WSDL/XSD**, đặc biệt có SOAP Fault, WS-Security hoặc yêu cầu tương thích Java–.NET/ESB: đánh giá **Spring-WS**.
- Nếu xây dựng **HTTP API tài nguyên** cho trình duyệt, mobile hoặc microservice: cân nhắc **REST** và triển khai bằng **Spring MVC** hoặc framework HTTP phù hợp.
- Nếu cần **client và server gửi cập nhật hai chiều qua kết nối lâu dài**: cân nhắc **WebSocket** (có thể đi kèm STOMP).
- Nếu một sản phẩm cần nhiều kênh giao tiếp: cho phép **Spring-WS, Spring MVC và WebSocket cùng tồn tại**, nhưng phân định rõ endpoint URL, mô hình dữ liệu, xác thực và kiểm thử cho từng kênh.

**Kết luận:** Spring-WS nổi bật khi trách nhiệm chính là **tuân thủ và vận hành hợp đồng SOAP contract-first**; Spring MVC xử lý HTTP web/API; REST định hướng cách thiết kế giao diện tài nguyên; WebSocket phục vụ trao đổi hai chiều liên tục. Chọn đúng theo yêu cầu giao tiếp sẽ giúp tránh viết lại những cơ chế giao thức vốn đã được framework hỗ trợ, đồng thời giữ tích hợp doanh nghiệp ổn định khi hai phía phát triển độc lập.
