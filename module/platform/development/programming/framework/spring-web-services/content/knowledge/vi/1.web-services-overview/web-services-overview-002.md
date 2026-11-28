# Thông điệp, hợp đồng, endpoint và máy khách trong một lần trao đổi

Trong Spring Web Services (Spring-WS), một lời gọi SOAP thành công là sự phối hợp của **hợp đồng XML**, **thông điệp SOAP**, **endpoint phía máy chủ** và **máy khách SOAP**. Bốn thành phần này có vai trò riêng nhưng phải thống nhất về namespace, cấu trúc dữ liệu và quy tắc xử lý lỗi. Hiểu một lượt trao đổi từ đầu đến cuối là nền tảng để phát triển dịch vụ SOAP theo hướng **contract-first**, thiết kế XSD/WSDL, ánh xạ JAXB, dùng interceptor, xử lý SOAP Fault và tích hợp hệ thống doanh nghiệp ổn định.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt XSD, WSDL, SOAP message, Spring-WS endpoint và SOAP client; chỉ ra thành phần nào được sử dụng trước và trong một lần gọi.
- Đọc được cấu trúc SOAP Envelope, Header, Body và Fault; liên hệ phần tử gốc trong Body với hợp đồng.
- Mô tả luồng JAXB marshalling/unmarshalling, xác thực XML, định tuyến endpoint và xử lý nghiệp vụ.
- Tạo bộ khung hợp đồng XSD, công bố WSDL, viết endpoint và gọi dịch vụ bằng WebServiceTemplate.
- Xác định nơi áp dụng schema validation, interceptor, WS-Security, chứng chỉ và kiểm thử tương thích.

## 1. Kịch bản xuyên suốt: tra cứu trạng thái đơn hàng

Giả sử hệ thống A cần hỏi hệ thống B trạng thái đơn hàng **ORD-42**. Hai hệ thống tích hợp qua thao tác SOAP tên **GetOrder**.

- **Yêu cầu:** phần tử XML `GetOrderRequest` chứa `orderId`.
- **Phản hồi thành công:** phần tử `GetOrderResponse` chứa `orderId` và `status`.
- **Thất bại:** máy chủ trả một **SOAP Fault** phù hợp với loại lỗi.
- **Đường dẫn minh họa:** `http://localhost:8080/ws`; địa chỉ này chỉ dùng cho ví dụ local.

Có hai thời điểm cần phân biệt:

1. **Trước khi gửi yêu cầu:** hai bên thống nhất hợp đồng XSD/WSDL; từ XSD có thể sinh kiểu Java bằng JAXB; phía máy khách biết địa chỉ dịch vụ và quy tắc bảo mật.
2. **Trong mỗi lần gọi:** máy khách tạo payload XML, đóng gói thành SOAP, gửi đến máy chủ; máy chủ kiểm tra, tìm endpoint, xử lý rồi trả SOAP response hoặc SOAP Fault.

**WSDL và XSD mô tả hợp đồng được sử dụng để tạo và hiểu thông điệp; thông thường chúng không được đính kèm trong từng SOAP request.**

| Thành phần | Vai trò | Ví dụ trong ca tra cứu |
| --- | --- | --- |
| XSD (XML Schema) | Quy định phần tử, kiểu dữ liệu, thứ tự và ràng buộc của XML | `GetOrderRequest`, `GetOrderResponse` |
| WSDL | Công bố các thao tác, thông điệp, binding/protocol và điểm truy cập dịch vụ | Thao tác `GetOrder`, địa chỉ SOAP |
| SOAP message | Phong bì XML thực sự đi qua mạng khi gọi dịch vụ | `Envelope` chứa `Body` |
| Endpoint Spring-WS | Nhận payload phù hợp, gọi xử lý nghiệp vụ và tạo phản hồi | Phương thức gắn `@PayloadRoot` |
| SOAP client | Tạo/gửi yêu cầu và đọc phản hồi theo cùng hợp đồng | `WebServiceTemplate` + JAXB |
| Interceptor / security | Kiểm tra, bổ sung hoặc xác thực thông điệp trước/sau xử lý | XSD validation, chữ ký, timestamp |

## 2. Hợp đồng đi trước mã Java: XSD và WSDL

### 2.1. XSD xác định hình dạng dữ liệu

Với contract-first, thiết kế XML từ nhu cầu tích hợp rồi mới sinh/viết mã Java. File minh họa `orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:orders:v1"
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

Các điểm cần đọc đúng:

- `targetNamespace` xác định danh tính phần tử trong hợp đồng; cặp **namespace + local name** mới là tên đầy đủ của phần tử XML. Tiền tố như `ord` chỉ là bí danh có thể thay đổi.
- `elementFormDefault="qualified"` làm cho các phần tử con cục bộ trong ví dụ cũng thuộc namespace hợp đồng.
- `xs:sequence` quy định thứ tự: trong response, `orderId` đứng trước `status`.
- `minOccurs` mặc định là 1; hai trường trên là bắt buộc trong XML hợp lệ theo XSD. Tuy vậy, `xs:string` vẫn có thể chứa chuỗi rỗng: nếu không được phép thì phải bổ sung ràng buộc XSD hoặc quy tắc nghiệp vụ.
- Đây là hợp đồng cấu trúc. Các quy tắc như “đơn hàng phải tồn tại” thuộc lớp nghiệp vụ, không thể được bảo đảm chỉ nhờ XSD.

Với XSD nêu trên, công cụ JAXB/XJC có thể sinh các kiểu Java đại diện cho request/response. Trong dự án Spring Boot 3+/Spring Framework 6+, mã JAXB thuộc hệ `jakarta.xml.bind`; không trộn lẫn tùy tiện với mã sinh từ hệ `javax.xml.bind` cũ.

### 2.2. WSDL mô tả cách giao tiếp

XSD trả lời “XML có hình dạng nào?”, còn WSDL trả lời “dịch vụ cung cấp thao tác nào, truyền những thông điệp gì và gọi ở đâu?”. Một WSDL SOAP 1.1 thường có các phần:

| Phần WSDL | Ý nghĩa |
| --- | --- |
| `types` | Khai báo hoặc nhập các kiểu/phần tử XSD |
| `message` | Mô tả thông điệp đầu vào, đầu ra hoặc lỗi |
| `portType` | Giao diện thao tác logic, chẳng hạn `GetOrder` |
| `binding` | Cách gắn thao tác với SOAP, style và transport |
| `service` / `port` | Địa chỉ endpoint có thể được client gọi |

Spring-WS có thể công bố WSDL từ XSD bằng `DefaultWsdl11Definition`. Khi dùng quy ước hậu tố `Request`/`Response`, nó có thể suy ra thao tác `GetOrder` từ `GetOrderRequest` và `GetOrderResponse`. Với tích hợp có yêu cầu WSDL chính xác từ đối tác, có thể công bố WSDL đã chốt sẵn thay cho WSDL sinh tự động; phải kiểm tra bản WSDL thực tế được công bố.

**Điểm then chốt:** client và server có thể được viết bằng các ngôn ngữ khác nhau. Họ cần tuân thủ cùng hợp đồng XML/WSDL, chứ không cần dùng chung class Java.

## 3. SOAP message thực sự được gửi đi

### 3.1. Yêu cầu SOAP 1.1

Ví dụ máy khách gửi qua HTTP POST:

~~~http
POST /ws HTTP/1.1
Host: localhost:8080
Content-Type: text/xml; charset=utf-8
~~~

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-42</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Các lớp cấu trúc:

- **Envelope** là phần tử gốc của thông điệp SOAP; namespace ở trên biểu thị **SOAP 1.1**.
- **Header** là nơi đặt metadata mức thông điệp, chẳng hạn thông tin bảo mật WS-Security, định tuyến hoặc correlation. Header có thể rỗng hoặc không xuất hiện nếu không cần.
- **Body** chứa payload nghiệp vụ. Phần tử `{urn:example:orders:v1}GetOrderRequest` là phần Spring-WS có thể dùng để chọn endpoint.
- **HTTP** là một transport phổ biến. SOAP là giao thức thông điệp; SOAP 1.2 dùng namespace Envelope và media type khác (`application/soap+xml`). Hai phiên bản cần cấu hình tương thích giữa các bên.

Đừng nhầm SOAP Body với toàn bộ HTTP body: **HTTP body chứa SOAP Envelope**, còn **SOAP Body** chỉ là một thành phần bên trong Envelope.

### 3.2. Phản hồi thành công

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:GetOrderResponse>
      <ord:orderId>ORD-42</ord:orderId>
      <ord:status>SHIPPED</ord:status>
    </ord:GetOrderResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Response mang phần tử `GetOrderResponse` đúng XSD. Máy khách giải mã XML về đối tượng JAXB tương ứng. Dù đoạn XML dùng tiền tố `ord`, một tiền tố khác vẫn hợp lệ nếu cùng URI namespace.

### 3.3. Lỗi là SOAP Fault, không phải response nghiệp vụ tùy tiện

Ví dụ SOAP 1.1 Fault:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Ma don hang khong hop le</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Với SOAP 1.1, `Client` biểu thị lỗi bắt nguồn từ yêu cầu; `Server` biểu thị phía xử lý không thể thực hiện yêu cầu. Trong SOAP 1.2, khái niệm gần tương ứng là `Sender` và `Receiver`, nhưng **cấu trúc XML Fault khác**. Không tự suy luận loại lỗi chỉ từ HTTP status: client phải hiểu cả SOAP Fault. Tránh đưa stack trace, token hoặc chi tiết nội bộ vào `faultstring`/`detail`. Nếu đối tác cần mã lỗi có cấu trúc, hãy định nghĩa và công bố schema cho fault detail trong hợp đồng.

## 4. Máy chủ Spring-WS: nhận thông điệp và chọn endpoint

### 4.1. Cấu hình công bố WSDL

Ví dụ sau minh họa ứng dụng Spring Boot với starter Web Services, một XSD đặt tại `src/main/resources/orders.xsd` và servlet nhận request tại `/ws/*`:

~~~java
@Configuration
@EnableWs
public class SoapConfiguration {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet> messageDispatcherServlet(
            ApplicationContext applicationContext) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(applicationContext);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(new ClassPathResource("orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition definition = new DefaultWsdl11Definition();
        definition.setPortTypeName("OrdersPort");
        definition.setLocationUri("/ws");
        definition.setTargetNamespace("urn:example:orders:v1");
        definition.setSchema(ordersSchema);
        return definition;
    }
}
~~~

Với cấu hình ví dụ này, WSDL thường được truy cập tại `http://localhost:8080/ws/orders.wsdl` và endpoint SOAP qua `http://localhost:8080/ws`. Địa chỉ host/port còn phụ thuộc cấu hình triển khai. Khi chạy sau gateway hoặc reverse proxy, hãy kiểm tra địa chỉ `soap:address` hiển thị trong WSDL từ phía client bên ngoài. Ngoài ra, nên xác minh operation, binding, namespace và các element được sinh đúng với hợp đồng đối tác.

### 4.2. Endpoint xử lý payload

Giả sử đã sinh `GetOrderRequest` và `GetOrderResponse` từ XSD bằng JAXB. Endpoint minh họa:

~~~java
@Endpoint
public class OrdersEndpoint {

    private static final String NS = "urn:example:orders:v1";
    private final OrderService orderService;

    public OrdersEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        OrderData order = orderService.requireById(request.getOrderId());

        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(order.id());
        response.setStatus(order.status());
        return response;
    }
}
~~~

Ở đây `OrderService` và `OrderData` là các kiểu nghiệp vụ do ứng dụng tự định nghĩa. Đoạn mã giả định các lớp JAXB đã sinh hỗ trợ đối tượng gốc và getter/setter như ví dụ; tùy cách khai báo XSD, JAXB cũng có thể dùng `JAXBElement` làm phần tử gốc, khi đó chữ ký endpoint hoặc cơ chế marshalling cần điều chỉnh tương ứng.

Ý nghĩa annotation:

- `@Endpoint` đăng ký một thành phần endpoint cho Spring-WS.
- `@PayloadRoot(namespace = ..., localPart = ...)` chọn phương thức theo **QName của phần tử gốc trong SOAP Body**, không theo đường dẫn REST hay tên method Java.
- `@RequestPayload` yêu cầu Spring-WS giải mã payload vào tham số; trong ví dụ là đối tượng JAXB.
- `@ResponsePayload` cho biết giá trị trả về được chuyển thành payload SOAP response.

Nếu request XML có đúng namespace nhưng khác `localPart`, hoặc đúng tên nhưng sai namespace, endpoint trên sẽ không được chọn. Một ứng dụng có thể có nhiều endpoint/mapping; việc định tuyến cụ thể do hạ tầng Spring-WS quản lý.

### 4.3. Những bước phía server diễn ra xung quanh endpoint

Luồng điển hình:

1. `MessageDispatcherServlet` nhận SOAP qua HTTP.
2. Spring-WS đọc SOAP Envelope và xác định payload; các interceptor đã cấu hình có thể kiểm tra thông điệp.
3. Endpoint mapping chọn phương thức phù hợp với QName của payload.
4. Endpoint adapter cùng JAXB chuyển XML thành đối tượng Java và gọi phương thức endpoint.
5. Lớp nghiệp vụ tra cứu đơn hàng; endpoint tạo `GetOrderResponse`.
6. Spring-WS marshal phản hồi thành XML, tạo SOAP Envelope và gửi về client.
7. Nếu xảy ra lỗi, exception resolver phù hợp có thể tạo SOAP Fault. Việc ánh xạ lỗi nghiệp vụ cụ thể cần được cấu hình, không mặc nhiên có chỉ vì endpoint ném exception.

Đây là luồng khái niệm: tùy cấu hình, interceptor, validation và xử lý lỗi có thể chạy ở các điểm khác nhau trước hoặc sau khi gọi endpoint.

## 5. Máy khách Spring-WS: tạo request và đọc response

Máy khách dùng `WebServiceTemplate`, kết hợp `Jaxb2Marshaller` để chuyển đối tượng Java thành XML và ngược lại. Ví dụ cấu hình:

~~~java
@Configuration
public class OrderClientConfiguration {

    @Bean
    public Jaxb2Marshaller orderMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.ws.schema");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate orderWebServiceTemplate(
            Jaxb2Marshaller orderMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(orderMarshaller);
        template.setUnmarshaller(orderMarshaller);
        template.setDefaultUri("http://localhost:8080/ws");
        return template;
    }
}
~~~

`com.example.orders.ws.schema` là package ví dụ chứa mã JAXB được sinh, cùng metadata JAXB phù hợp. Một client gọi dịch vụ như sau:

~~~java
@Component
public class OrderSoapClient {
    private final WebServiceTemplate template;

    public OrderSoapClient(WebServiceTemplate orderWebServiceTemplate) {
        this.template = orderWebServiceTemplate;
    }

    public GetOrderResponse getOrder(String orderId) {
        GetOrderRequest request = new GetOrderRequest();
        request.setOrderId(orderId);

        Object result = template.marshalSendAndReceive(request);
        if (!(result instanceof GetOrderResponse response)) {
            throw new IllegalStateException("Unexpected SOAP response");
        }
        return response;
    }
}
~~~

Ví dụ giả định phần tử request/response là các kiểu JAXB được marshal trực tiếp. Với kiểu JAXB chỉ có `@XmlType` mà không có `@XmlRootElement`, có thể cần bọc bằng `JAXBElement` do `ObjectFactory` tạo. Khi nhận SOAP Fault, `WebServiceTemplate` có cơ chế fault handling riêng; không nên ép kiểu kết quả thành response thành công và coi lỗi như dữ liệu thông thường.

Trong môi trường thực tế, client cần bổ sung **timeout kết nối/đọc**, xác thực TLS, chính sách retry phù hợp, xử lý SOAP Fault và logging có che dữ liệu nhạy cảm. Không tự động retry thao tác có tác dụng phụ nếu chưa xác minh tính idempotent.

## 6. Một lần trao đổi diễn ra theo thứ tự nào?

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Ứng dụng A
    participant T as WebServiceTemplate + JAXB
    participant D as MessageDispatcherServlet
    participant I as Interceptor / Endpoint mapping
    participant E as OrdersEndpoint
    participant B as OrderService

    Note over C,B: Trước lời gọi: hai phía thống nhất XSD/WSDL và cấu hình SOAP
    C->>T: getOrder("ORD-42")
    T->>T: Marshal GetOrderRequest thành XML
    T->>D: HTTP POST chứa SOAP Envelope / Body
    D->>I: Đọc SOAP, kiểm tra chính sách
    I->>I: Kiểm tra XML / Header, định tuyến theo QName
    I->>E: Gọi @PayloadRoot GetOrderRequest
    E->>B: requireById("ORD-42")
    B-->>E: OrderData("ORD-42", "SHIPPED")
    E-->>I: GetOrderResponse
    I-->>D: Payload phản hồi
    D-->>T: SOAP Envelope / Body phản hồi
    T->>T: Unmarshal XML thành GetOrderResponse
    T-->>C: Kết quả Java
~~~

Trên luồng thành công, dữ liệu có thể đi qua các dạng:

| Tại điểm | Dạng dữ liệu | Trách nhiệm chính |
| --- | --- | --- |
| Ứng dụng gọi | `GetOrderRequest` Java | Cung cấp dữ liệu đầu vào |
| Marshalling | XML `GetOrderRequest` | Ánh xạ đúng namespace/schema |
| Truyền mạng | SOAP Envelope qua HTTP | Chuyển thông điệp và header |
| Endpoint | Đối tượng Java đã unmarshal | Điều phối nghiệp vụ |
| Nghiệp vụ | `OrderData` | Xử lý quy tắc, đọc dữ liệu |
| Phản hồi | XML `GetOrderResponse` trong SOAP | Gửi kết quả theo hợp đồng |
| Ứng dụng nhận | `GetOrderResponse` Java | Sử dụng kết quả |

Nếu schema không hợp lệ, chữ ký không hợp lệ, endpoint không khớp hoặc nghiệp vụ phát sinh lỗi, luồng có thể dừng sớm và trả SOAP Fault thay cho nhánh phản hồi thành công.

## 7. Validation, SOAP Fault, interceptor và bảo mật nằm ở đâu?

### 7.1. Xác thực XML khác với kiểm tra nghiệp vụ

**XSD validation** kiểm tra phần tử/namespace, kiểu dữ liệu, thứ tự và các ràng buộc được khai báo trong schema. Spring-WS hỗ trợ `PayloadValidatingInterceptor` để kiểm tra payload request hoặc response với schema được cấu hình. Chẳng hạn, thiếu `orderId` là lỗi cấu trúc nếu schema yêu cầu phần tử này; một `orderId` tồn tại về mặt XML nhưng không có trong cơ sở dữ liệu là lỗi nghiệp vụ.

Không coi JAXB unmarshal thành công là bằng chứng payload hợp lệ theo mọi ràng buộc XSD; cần cấu hình validation rõ ràng nếu yêu cầu chặt chẽ. Đồng thời kiểm tra dữ liệu đầu vào tại lớp nghiệp vụ theo các quy tắc không thể hoặc không nên biểu diễn bằng XSD.

### 7.2. SOAP Fault là hợp đồng lỗi của dịch vụ

Thiết kế tối thiểu nên xác định trước:

| Tình huống | Cách xử lý mong đợi |
| --- | --- |
| XML sai cấu trúc hoặc sai schema | Từ chối yêu cầu, trả fault phù hợp và không chạy nghiệp vụ |
| Không khớp endpoint hoặc SOAP action/chính sách | Trả lỗi định tuyến/protocol thích hợp |
| Không tìm thấy đơn hàng | Ánh xạ exception nghiệp vụ thành fault đã thỏa thuận |
| Không qua xác thực chữ ký/token | Từ chối trước khi xử lý nghiệp vụ |
| Lỗi tạm thời ở hệ thống phụ thuộc | Trả fault phía server, theo chính sách xử lý lỗi |

Spring-WS cung cấp cơ chế `EndpointExceptionResolver` như `SoapFaultMappingExceptionResolver` để ánh xạ exception sang SOAP Fault. Cần xét có nên bổ sung `detail` có cấu trúc cho client hay không, cùng cách biểu diễn tương ứng trong XSD/WSDL. Không gửi ngoại lệ Java nguyên văn cho hệ thống bên ngoài.

### 7.3. Interceptor hỗ trợ các yêu cầu xuyên suốt

Interceptor có thể đảm nhiệm việc kiểm tra schema, xác thực header, ghi nhận correlation ID hoặc thực thi chính sách thông điệp. Phân biệt **interceptor của Spring-WS** với servlet filter hoặc HTTP proxy: interceptor hiểu thông điệp SOAP ở lớp Spring-WS, còn filter/proxy làm việc tại các lớp khác.

Ở cả request và response, cần thiết kế quan sát được lỗi mà không làm lộ payload nhạy cảm. Khi debug, log nên có correlation ID, tên operation, trạng thái xử lý và mã lỗi; dữ liệu cá nhân, token và khóa bí mật cần được che hoặc bỏ khỏi log.

### 7.4. TLS và WS-Security giải quyết những nhu cầu khác nhau

- **HTTPS/TLS** bảo vệ kênh kết nối khi dữ liệu truyền giữa hai đầu TLS. Cần kiểm tra chứng chỉ server, chain tin cậy, hostname và cấu hình hết hạn/gia hạn.
- **WS-Security** là bảo mật ở cấp SOAP message: tùy chính sách có thể dùng timestamp, chữ ký số XML, mã hóa XML và token xác thực. Spring-WS tích hợp các khả năng này qua `Wss4jSecurityInterceptor` và thư viện liên quan.
- **Chứng chỉ và khóa** dùng cho chữ ký/mã hóa cần được quản lý keystore/truststore và phân quyền, thay thế định kỳ. Không đặt private key hoặc password vào source code.
- **XML security** bao gồm cấu hình parser an toàn trước XXE, giới hạn kích thước/độ phức tạp XML và kiểm tra chữ ký đúng phần tử nghiệp vụ được sử dụng. Cấu hình WS-Security phải được kiểm thử với dữ liệu và chính sách thực tế của đối tác.

Không mặc định rằng chỉ cần HTTPS là đã đáp ứng yêu cầu chữ ký thông điệp, hoặc chỉ có chữ ký XML là không cần HTTPS. Chính sách nào bắt buộc do thỏa thuận tích hợp quyết định.

## 8. Kiểm thử hợp đồng và khả năng tương thích

Một SOAP endpoint trả HTTP 200 chưa chứng minh tích hợp hoạt động đúng. Cần kiểm tra theo nhiều mức:

| Mức kiểm thử | Câu hỏi cần trả lời | Gợi ý kỹ thuật |
| --- | --- | --- |
| Schema | Request/response có đúng QName, thứ tự, kiểu và trường bắt buộc? | XSD validation, XML mẫu hợp lệ/không hợp lệ |
| WSDL | Client đối tác có hiểu operation, binding, address và namespace? | Kiểm tra WSDL công bố; sinh client từ WSDL |
| Endpoint | Payload đúng có gọi đúng `@PayloadRoot`? Sai namespace có bị từ chối? | `MockWebServiceClient` của Spring-WS Test |
| SOAP client | Có gửi đúng XML, header và đọc đúng response/fault? | `MockWebServiceServer` |
| Lỗi | Lỗi nghiệp vụ, schema và security ra fault thống nhất? | Test fault code/detail và ánh xạ exception |
| Bảo mật | Timestamp, chữ ký, chứng chỉ sai/hết hạn có bị từ chối? | Test chính sách WS-Security/TLS |
| Tương thích | Java client có giao tiếp được với .NET/Java khác phiên bản? | Integration test theo XML/WSDL thực tế |

Ví dụ các trường hợp tối thiểu trong kịch bản đơn hàng:

1. `GetOrderRequest` hợp lệ với `ORD-42` trả `GetOrderResponse` có `status=SHIPPED`.
2. Bỏ `orderId` làm request vi phạm XSD, phải bị từ chối trước nghiệp vụ nếu bật validation.
3. Đổi namespace từ `urn:example:orders:v1` sang URI khác thì không còn khớp `@PayloadRoot`.
4. Tra cứu mã đơn hàng không tồn tại phải sinh fault theo hợp đồng lỗi nghiệp vụ.
5. Client gọi từ ngoài reverse proxy phải thấy địa chỉ endpoint khả dụng trong WSDL.
6. Khi đã bật WS-Security, thông điệp sai chữ ký hoặc timestamp vượt giới hạn phải bị từ chối.

Đối với thay đổi hợp đồng, không suy luận rằng “thêm trường optional luôn tương thích”: client cũ có thể có validator nghiêm ngặt, schema cố định hoặc code sinh với quy tắc riêng. Cần kiểm thử thực tế cả **client cũ → server mới** và **client mới → server cũ** theo chính sách versioning của hệ thống. Thay đổi namespace/operation hoặc chuyển SOAP 1.1 sang 1.2 thường ảnh hưởng đáng kể đến tương thích.

## 9. Các nhầm lẫn thường gặp và cách lần lỗi

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Client gửi SOAP nhưng endpoint không chạy | QName của phần tử gốc trong Body; namespace bị viết sai; endpoint mapping; mapping servlet |
| JAXB báo không marshal/unmarshal được | Context path, metadata `@XmlRootElement`/`JAXBElement`, package hoặc khác phiên bản Jakarta/Javax |
| XML nhìn đúng nhưng bị XSD từ chối | Thiếu phần tử, sai thứ tự `xs:sequence`, prefix trỏ tới namespace khác, sai kiểu |
| Mở WSDL được nhưng gọi API không được | `soap:address` sai sau proxy, khác SOAP version, lỗi TLS hoặc chính sách xác thực |
| HTTP status có lỗi nhưng code không thấy response | Nhánh SOAP Fault; fault resolver và fault handling ở client |
| Qua môi trường staging rồi production thất bại | Chứng chỉ/truststore, timestamp lệch, chính sách WS-Security, địa chỉ mạng |
| Client sinh từ WSDL không hoạt động với XML thực tế | WSDL và XSD triển khai bị lệch, khác contract version hoặc binding |

Trình tự gỡ lỗi hiệu quả: bắt đầu từ **WSDL đang công bố**, xác nhận **SOAP version và URL**, kiểm tra **QName của Body**, sau đó mới đến **JAXB, interceptor và xử lý nghiệp vụ**. Với security, hãy dùng log và trace đã ẩn dữ liệu nhạy cảm; không vô hiệu hóa xác minh chứng chỉ để làm cho môi trường thử nghiệm “chạy được”.

## 10. Tự kiểm tra hiểu biết

1. Vì sao WSDL không phải payload gửi trong mỗi lần gọi SOAP? WSDL cung cấp những thông tin gì mà XSD không đủ?
2. Hai request có cùng local name `GetOrderRequest` nhưng namespace khác nhau có cùng định tuyến vào endpoint ví dụ không? Vì sao?
3. Nếu request không có `orderId`, thành phần nào có thể phát hiện lỗi cấu trúc? Nếu `orderId` là mã không tồn tại, lớp nào quyết định kết quả?
4. JAXB, `WebServiceTemplate`, `MessageDispatcherServlet` và `@PayloadRoot` lần lượt tham gia vào những khâu nào?
5. Khi máy khách nhận SOAP Fault, vì sao không thể xử lý như một `GetOrderResponse` bình thường?
6. Vì sao cần kiểm thử cả XSD/WSDL, chứng chỉ/WS-Security và các client khác nền tảng?

**Ghi nhớ:** Một lần trao đổi SOAP chỉ đáng tin cậy khi **contract** xác định đúng cấu trúc và thao tác, **client** tạo thông điệp đúng chuẩn, **Spring-WS endpoint** định tuyến và xử lý đúng payload, còn **validation, fault handling và security** bảo đảm hành vi nhất quán ở cả nhánh thành công lẫn thất bại.
