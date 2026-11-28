# Không tìm thấy endpoint: kiểm tra URL, QName, mapping và action

## 1. Hiểu đúng lỗi không tìm thấy endpoint

Trong module **SPRING_WEB_SERVICES**, dịch vụ SOAP được phát triển theo hướng **contract-first**: WSDL mô tả operation và binding, XSD định nghĩa payload, JAXB/OXM ánh xạ XML với Java object, còn Spring-WS chọn endpoint để xử lý request. Khi client gọi đúng server nhưng Spring-WS không tìm được endpoint phù hợp, request có thể kết thúc bằng lỗi kiểu *No endpoint mapping found*, *No endpoint found*, HTTP 404/500 hoặc SOAP Fault tùy nơi phát sinh và cấu hình exception resolver.

Không nên vội sửa `@PayloadRoot` hoặc đổi URL theo cảm tính. Việc chẩn đoán cần đi theo đúng thứ tự:

1. HTTP request có tới đúng host, port, context path và servlet mapping không?
2. `MessageDispatcherServlet` có nhận được SOAP message không?
3. SOAP version và Envelope có được message factory chấp nhận không?
4. Root element trong SOAP Body có đúng **QName** (namespace URI + local name) không?
5. Endpoint mapping đang dùng `@PayloadRoot`, SOAPAction, WS-Addressing Action hay mapping khác?
6. Có endpoint bean và adapter hỗ trợ method signature tương ứng không?
7. Client có gửi action/header đúng binding WSDL không?

Các câu hỏi này phân biệt lỗi ở HTTP routing, message parsing, endpoint mapping và endpoint invocation. Một HTTP 404 thường chỉ cho biết đường dẫn không được route; một lỗi endpoint mapping thường cho biết SOAP request đã tiến xa hơn nhưng không khớp mapping. Cần đọc log và response thực tế để xác định lớp gây lỗi.

### Mục tiêu học tập

Sau bài thuộc chương **Quan sát và chẩn đoán**, bạn có thể:

- Phân biệt URL/servlet mapping với endpoint mapping của Spring-WS.
- Đọc QName của SOAP Body root element và xác định namespace mismatch.
- Kiểm tra `@PayloadRoot`, `@SoapAction` và các loại endpoint mapping.
- Phân biệt SOAP 1.1 SOAPAction với WS-Addressing Action.
- Đối chiếu WSDL binding/operation với request thực tế.
- Kiểm tra endpoint bean, adapter và method signature.
- Dùng log, breakpoint, `MockWebServiceClient` và HTTP integration test để tìm đúng điểm lỗi.
- Viết regression test chứng minh request được route tới endpoint mong đợi.

## 2. Luồng định tuyến từ HTTP đến endpoint method

Spring-WS không định tuyến request chỉ dựa vào URL. URL đưa HTTP request tới servlet; sau khi SOAP message được đọc, `MessageDispatcher` sử dụng endpoint mappings để tìm endpoint. Mapping có thể xét payload root QName, SOAPAction, WS-Addressing Action hoặc tiêu chí khác.

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["HTTP host / port / context path"]
    B --> C["Servlet mapping: /ws/*"]
    C -->|Không match| D["HTTP 404 hoặc servlet/container error"]
    C -->|Match| E["MessageDispatcherServlet"]
    E --> F["SOAP parsing / MessageFactory"]
    F -->|Parse / SOAP version error| G["Protocol or SOAP Fault"]
    F -->|Valid message| H["MessageDispatcher"]
    H --> I["EndpointMapping"]
    I --> J{"Matching criteria"}
    J -->|PayloadRoot QName| K["Namespace URI + local name"]
    J -->|SOAPAction| L["SOAPAction value"]
    J -->|WS-Addressing| M["wsa:Action URI"]
    K --> N["Selected endpoint"]
    L --> N
    M --> N
    J -->|No mapping| O["No endpoint / EndpointNotFound"]
    N --> P["EndpointAdapter"]
    P --> Q["Endpoint method"]
    Q --> R["SOAP response or Fault"]
~~~

### 2.1. Bốn lớp địa chỉ/định danh không thể thay thế nhau

| Giá trị | Ví dụ | Vai trò |
| --- | --- | --- |
| HTTP URL/path | `https://api.example.com/app/ws` | Đưa request tới servlet/container. |
| Payload root QName | `{https://example.com/orders/v1}GetOrderRequest` | Nhận diện payload operation với `PayloadRootAnnotationMethodEndpointMapping`. |
| SOAPAction | `https://example.com/orders/GetOrder` | Action trong SOAP 1.1 HTTP binding; có thể được dùng bởi `SoapActionAnnotationMethodEndpointMapping`. |
| WS-Addressing Action | `https://example.com/orders/GetOrder` | Giá trị trong Header `wsa:Action`; có thể được dùng bởi WS-Addressing endpoint mapping. |

Các URI trong ví dụ chỉ minh họa. WSDL có thể quy định action URI khác nhau, hoặc operation không sử dụng action mapping riêng. Không suy ra payload QName từ URL hoặc giả định SOAPAction luôn bằng WS-Addressing Action.

### 2.2. URL đúng chưa chắc endpoint đúng

Nhiều operation thường dùng chung một servlet endpoint:

~~~text
/ws
  ├── GetOrderRequest
  ├── CancelOrderRequest
  └── SubmitOrderRequest
~~~

HTTP routing chỉ đưa request tới `/ws`. Spring-WS tiếp tục chọn method theo mapping. Nếu `GetOrderRequest` có namespace sai, server vẫn có thể nhận đúng URL nhưng không tìm được endpoint method.

Ngược lại, QName có thể đúng nhưng URL trỏ nhầm servlet hoặc ứng dụng khác. Vì vậy hãy xác minh cả URL lẫn mapping.

## 3. Bước 1 — Xác minh URL và servlet mapping

### 3.1. Kiểm tra host, port, context path và servlet path

Một endpoint có thể được deploy tại:

~~~text
https://orders.example.com/integration/ws
~~~

Trong đó host là `orders.example.com`; context path là `/integration`; servlet mapping là `/ws/*`. URL client gọi phải kết hợp đúng context path và servlet mapping. Nếu ứng dụng đổi context path khi deploy, URL hard-code trong client có thể trở thành sai.

Kiểm tra actual endpoint URI mà client dùng; context path của ứng dụng; `MessageDispatcherServlet` được đăng ký dưới pattern nào; reverse proxy/ingress có rewrite path hoặc thêm prefix không; HTTP method có là POST không; host/port có trỏ đúng service/version không.

### 3.2. Cấu hình servlet mapping

Với cấu hình servlet registration tường minh trong Spring Boot:

~~~java
@Bean
ServletRegistrationBean<MessageDispatcherServlet> messageDispatcherServlet(
        ApplicationContext applicationContext) {
    MessageDispatcherServlet servlet =
        new MessageDispatcherServlet();
    servlet.setApplicationContext(applicationContext);
    servlet.setTransformWsdlLocations(true);

    ServletRegistrationBean<MessageDispatcherServlet> registration =
        new ServletRegistrationBean<>(servlet, "/ws/*");
    registration.setName("spring-ws");
    return registration;
}
~~~

Đây là một pattern cấu hình; nếu dùng Spring Boot auto-configuration hoặc cấu hình servlet khác thì không đăng ký trùng servlet. `transformWsdlLocations` giúp địa chỉ trong WSDL được điều chỉnh theo request/deployment context trong những cấu hình phù hợp; nó không tự sửa QName hoặc endpoint mapping.

### 3.3. Phân biệt HTTP 404 với endpoint mapping miss

| Triệu chứng | Khả năng xảy ra | Bước kiểm tra |
| --- | --- | --- |
| HTTP 404 từ ingress | Host/path không tồn tại ở proxy | Proxy route, upstream và rewrite rules |
| HTTP 404 từ servlet container | Không có servlet mapping hoặc context path sai | Servlet registration và deployment path |
| HTTP 405 | HTTP method không được route hỗ trợ | Request method, SOAP binding |
| HTTP 415 | Content-Type/media type không phù hợp | SOAP 1.1 `text/xml`, SOAP 1.2 media type theo binding |
| SOAP Fault hoặc HTTP 500 sau khi servlet nhận message | Parsing, mapping, interceptor, endpoint hoặc exception resolution | Application log và dispatcher trace |
| No endpoint mapping found | Không mapping nào chọn endpoint cho message | QName, SOAPAction, WS-Addressing và mapping registrations |

Response status có thể thay đổi theo container, proxy và exception resolver. Hãy lấy response body, server logs và request trace làm bằng chứng thay vì chỉ dựa vào mã HTTP.

## 4. Bước 2 — Đọc SOAP Envelope và xác định payload root QName

### 4.1. QName gồm namespace URI và local name

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="https://example.com/orders/v1">
    <soap:Header/>
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Root QName là:

~~~text
{https://example.com/orders/v1}GetOrderRequest
~~~

Prefix `ord` không phải định danh. Namespace URI và local name mới xác định QName. Đổi prefix từ `ord` thành `o` mà giữ nguyên namespace URI không làm QName thay đổi.

### 4.2. Những lỗi namespace thường gặp

**Sai namespace URI:**

~~~xml
<!-- Client gửi -->
<ord:GetOrderRequest
    xmlns:ord="https://example.com/order/v1">
    <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

~~~xml
<!-- Endpoint mong đợi -->
<ord:GetOrderRequest
    xmlns:ord="https://example.com/orders/v1">
    <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

Khác biệt `order/v1` và `orders/v1` khiến hai QName khác nhau dù local name giống nhau.

**Element không có namespace:**

~~~xml
<GetOrderRequest>
    <orderId>ORD-1001</orderId>
</GetOrderRequest>
~~~

Nếu endpoint mong root element thuộc namespace `https://example.com/orders/v1`, XML trên không khớp.

**Namespace default chỉ áp dụng cho element, không mặc nhiên áp dụng cho attribute không prefix:**

~~~xml
<GetOrderRequest
    xmlns="https://example.com/orders/v1"
    version="1">
    <orderId>ORD-1001</orderId>
</GetOrderRequest>
~~~

Root và child elements thuộc default namespace; attribute không prefix `version` không thuộc namespace đó. Điều này thường không ảnh hưởng root mapping nhưng có thể ảnh hưởng XSD validation hoặc attribute processing.

### 4.3. Dùng @PayloadRoot

~~~java
@Endpoint
public class OrderEndpoint {
    private static final String NAMESPACE =
        "https://example.com/orders/v1";

    private final OrderApplicationService orderService;

    public OrderEndpoint(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(
        namespace = NAMESPACE,
        localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        return orderService.getOrder(request.getOrderId());
    }
}
~~~

`PayloadRootAnnotationMethodEndpointMapping` dùng root QName của payload để tìm method. So sánh namespace với URI trong SOAP Body root; localPart có đúng hoa/thường không; annotation có đặt trên method endpoint Spring quản lý không; method có nằm trong bean `@Endpoint` được component scan không.

Không dùng namespace của child `orderId` hoặc namespace SOAP Envelope thay cho namespace của application payload.

## 5. Bước 3 — Kiểm tra các endpoint mapping đã đăng ký

### 5.1. PayloadRootAnnotationMethodEndpointMapping

~~~java
@PayloadRoot(
    namespace = "https://example.com/orders/v1",
    localPart = "CancelOrderRequest")
@ResponsePayload
public CancelOrderResponse cancel(
        @RequestPayload CancelOrderRequest request) {
    // ...
}
~~~

Mapping này phù hợp khi mỗi operation có một request root element được định danh rõ trong XSD.

### 5.2. SoapActionAnnotationMethodEndpointMapping

~~~java
@SoapAction("https://example.com/orders/GetOrder")
@ResponsePayload
public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request) {
    // ...
}
~~~

Chỉ dùng mapping này khi endpoint mapping tương ứng được đăng ký và client thực sự gửi SOAPAction theo binding. `@SoapAction` không tự có tác dụng nếu mapping tương ứng không được tạo trong ứng dụng.

### 5.3. WS-Addressing Action mapping

WS-Addressing dùng Header `wsa:Action` trong SOAP Envelope. Đây là thông tin khác với HTTP SOAPAction. Service có thể dùng `AnnotationActionEndpointMapping` hoặc mapping WS-Addressing tương ứng trong phiên bản Spring-WS đang chạy.

~~~xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Action>
        https://example.com/orders/GetOrder
    </wsa:Action>
</soap:Header>
~~~

Nếu service dùng WS-Addressing, kiểm tra namespace version; Action URI; Header có thực sự được serialize; endpoint mapping có được đăng ký; Action có khớp operation trong WSDL/WS-Addressing policy không.

Không thêm Header `wsa:Action` chỉ để chữa lỗi `@PayloadRoot` nếu service không dùng WS-Addressing.

### 5.4. Mapping theo URI hoặc custom endpoint mapping

Spring-WS cho phép custom `EndpointMapping`. Với custom mapping, điều kiện chọn endpoint có thể dựa vào URI, Header, tenant metadata hoặc quy tắc ứng dụng. Khi chẩn đoán, xác định mapping nào đang thực sự được đăng ký và thứ tự/priority của chúng.

Nếu nhiều mapping cùng có khả năng khớp, việc chọn endpoint phụ thuộc mapping order và implementation. Tránh cấu hình hai mapping mơ hồ cùng tuyên bố xử lý một request.

| Mapping | Điều kiện chính | Dữ liệu cần xem |
| --- | --- | --- |
| Payload root | QName của Body root | Namespace URI + local part |
| SOAPAction | SOAPAction value | HTTP header hoặc SOAP message action |
| WS-Addressing | `wsa:Action` | SOAP Header và Action URI |
| Custom mapping | Logic ứng dụng | Code, priority và request metadata |

## 6. SOAPAction và WS-Addressing Action không giống nhau

### 6.1. SOAP 1.1 SOAPAction

~~~http
POST /ws HTTP/1.1
Content-Type: text/xml; charset=utf-8
SOAPAction: "https://example.com/orders/GetOrder"
~~~

Giá trị SOAPAction do WSDL binding/operation quy định. Tùy binding, giá trị có thể là URI, chuỗi rỗng hoặc quy ước khác; không tự suy từ tên method Java.

### 6.2. SOAP 1.2 action parameter

SOAP 1.2 thường dùng `application/soap+xml` và action có thể được thể hiện dưới dạng media-type parameter:

~~~http
Content-Type: application/soap+xml; charset=utf-8; action="https://example.com/orders/GetOrder"
~~~

Không áp nguyên cách gửi SOAP 1.1 `SOAPAction` header cho mọi SOAP 1.2 endpoint. Hãy kiểm tra binding và HTTP sender/client implementation.

### 6.3. WS-Addressing Action

WS-Addressing Action là SOAP Header element `wsa:Action`, không phải HTTP header SOAPAction. Một integration có thể dùng cả HTTP binding action và WS-Addressing, nhưng chúng phải tuân contract/policy. Hai giá trị có thể liên quan hoặc giống nhau, nhưng không tự động là cùng một trường.

### 6.4. Cách so sánh action

Khi request không map được:

1. Lấy action từ WSDL operation/binding hoặc WS-Addressing policy;
2. Ghi lại SOAPAction HTTP header hoặc SOAP 1.2 `action` parameter;
3. Đọc `wsa:Action` trong SOAP Header nếu dùng WS-Addressing;
4. So sánh với mapping annotation/configuration;
5. Kiểm tra dấu ngoặc kép, khoảng trắng, trailing slash, version suffix và case của URI string.

URI action thường được so sánh như chuỗi theo mapping/framework. Không tự normalize hoặc bỏ path segment nếu contract không cho phép.

## 7. Bước 4 — Kiểm tra endpoint bean và endpoint adapter

### 7.1. Endpoint bean có được Spring phát hiện?

Một method có `@PayloadRoot` nhưng class không được Spring quản lý thì không được endpoint mapping phát hiện.

Kiểm tra class có `@Endpoint` hoặc bean definition phù hợp; package có nằm trong component scan; profile/condition có làm bean không được tạo; ApplicationContext có đúng configuration; và không có bean bị thay bởi test/mock profile ngoài dự kiến.

### 7.2. EndpointAdapter hỗ trợ method signature?

Sau khi mapping chọn endpoint method, Spring-WS cần một `EndpointAdapter` hỗ trợ cách gọi method và tham số/return type. Với annotated endpoints, ứng dụng thường dùng `DefaultMethodEndpointAdapter` cùng argument resolvers và return value handlers.

Nếu mapping đã tìm thấy endpoint nhưng adapter không hỗ trợ signature, lỗi sẽ khác với “không có endpoint mapping”. Kiểm tra:

- Annotation `@RequestPayload` và `@ResponsePayload` đặt đúng nơi khi cần;
- JAXB marshaller/unmarshaller hoặc message converters được cấu hình;
- Request Java type tương ứng XSD/JAXB model;
- Return type có handler phù hợp;
- Không có nhiều annotation/parameter mapping mâu thuẫn.

### 7.3. Mapping miss khác adapter failure

| Giai đoạn | Lỗi thường gặp | Nơi kiểm tra |
| --- | --- | --- |
| Endpoint mapping | Không có endpoint phù hợp | QName/action/mapping registry |
| Endpoint adapter | Không có adapter hỗ trợ endpoint method | Adapter và method signature |
| Argument resolution | Không thể chuyển request thành parameter | JAXB/OXM/message converters |
| Endpoint invocation | Exception trong method | Business log/exception resolver |
| Return value handling | Không serialize được response | Marshaller/return handler/schema |

Đừng chỉnh QName khi log cho thấy endpoint đã được chọn và lỗi xảy ra ở JAXB conversion hoặc method invocation.

## 8. Đối chiếu WSDL và request thực tế

### 8.1. Xác minh operation, binding và message

Trong WSDL, kiểm tra operation name trong portType; input/output message và phần tử được tham chiếu; binding SOAP version/style/use; soap:operation soapAction hoặc action theo SOAP 1.2 binding; service/port address; imported WSDL/XSD namespace và schema location.

Operation name không nhất thiết giống local name của request element, dù nhiều contract đặt giống nhau.

### 8.2. WSDL location có thể đúng nhưng contract version sai

Một URL WSDL có thể trỏ tới service version khác hoặc reverse proxy cache một WSDL cũ. Kiểm tra namespace version, imported XSD và SOAP address thực sự mà client sử dụng.

~~~text
/orders/v1 -> namespace https://example.com/orders/v1
/orders/v2 -> namespace https://example.com/orders/v2
~~~

Không gửi payload v1 đến endpoint chỉ nhận namespace v2 dù URL HTTP có thể vẫn giống nhau. Versioning cần được thể hiện rõ trong namespace/binding/endpoint deployment.

### 8.3. Dùng contract fixture làm nguồn so sánh

Khi viết test, fixture request nên được xây từ XSD/WSDL đã version hóa. Không chỉ copy XML từ log production rồi coi đó là chuẩn; log có thể chứa message sai, đã bị redact hoặc đến từ client version cũ.

## 9. Quan sát và log để xác định điểm request bị rơi

### 9.1. Bật log có mục tiêu

Trong môi trường phát triển/integration, có thể tăng log level cho các package Spring-WS liên quan:

~~~yaml
logging:
  level:
    org.springframework.ws.server.MessageDispatcher: DEBUG
    org.springframework.ws.server.endpoint.mapping: TRACE
    org.springframework.ws.server.endpoint.adapter: DEBUG
~~~

Log category cụ thể và mức độ chi tiết có thể thay đổi theo phiên bản. Không giữ TRACE payload logging vô thời hạn trong production vì SOAP message có thể chứa PII, credentials, WS-Security token hoặc dữ liệu doanh nghiệp nhạy cảm.

### 9.2. Những gì cần ghi nhận

Log/trace chẩn đoán hữu ích nên có correlation ID; HTTP path/servlet mapping; SOAP version/content type; payload root QName; mapping type hoặc endpoint bean/method được chọn nếu có; action value đã được chuẩn hóa/giới hạn; kết quả parse, mapping, adapter và interceptor; Fault code/error category; processing duration.

Tránh log toàn bộ SOAP Envelope. Có thể ghi QName và kích thước payload thay cho body; nếu buộc phải lấy sample, dùng synthetic data và redaction.

### 9.3. Breakpoint theo đúng thứ tự

1. Đặt breakpoint tại MessageDispatcherServlet hoặc servlet entry để xác minh request đã tới.
2. Kiểm tra MessageContext/SOAP message sau parse.
3. Xem payload root QName trong Body.
4. Kiểm tra endpoint mapping được gọi và tiêu chí mapping.
5. Xác minh endpoint object/method được chọn.
6. Nếu mapping thành công, chuyển sang adapter, argument resolver, marshaller và endpoint method.

Đặt breakpoint trong business service ngay từ đầu có thể gây hiểu nhầm: nếu mapping miss, breakpoint đó không bao giờ được kích hoạt.

## 10. Checklist chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân cần kiểm tra đầu tiên | Bằng chứng |
| --- | --- | --- |
| HTTP 404 | Host, context path, servlet mapping, proxy rewrite | Access log, servlet registration |
| HTTP 405 | Method hoặc HTTP binding không phù hợp | Request method, WSDL binding |
| HTTP 415 | Content-Type/SOAP version sai | Content-Type và Envelope namespace |
| SOAP parse Fault | XML malformed hoặc SOAP version không hỗ trợ | Message factory log, Envelope QName |
| No endpoint mapping found | QName/action/custom mapping không khớp | Body root QName, action và mapping |
| Đổi prefix nhưng lỗi vẫn còn | Namespace URI/local name có thể vẫn sai | Expanded QName |
| `@PayloadRoot` không được gọi | Endpoint bean không register hoặc annotation sai | Context beans, mapping registry |
| Endpoint được chọn nhưng invocation fail | Adapter/argument resolver/signature | Adapter logs, parameter types |
| Request tới đúng operation nhưng Fault | Interceptor/business exception/validation | Fault code và stack trace server |
| WSDL client gọi sai địa chỉ | WSDL service/port address hoặc proxy transform | WSDL runtime và actual URI |
| SOAP 1.1 chạy, SOAP 1.2 lỗi | Binding, message factory hoặc media type/action | Envelope namespace, Content-Type |
| SOAPAction đúng nhưng mapping fail | Service có thể map theo payload/WS-Addressing khác | Endpoint mapping registrations |

## 11. Ví dụ: sửa lỗi QName mismatch

Giả sử endpoint:

~~~java
@Endpoint
public class CustomerEndpoint {
    @PayloadRoot(
        namespace = "https://example.com/customers/v1",
        localPart = "FindCustomerRequest")
    @ResponsePayload
    public FindCustomerResponse find(
            @RequestPayload FindCustomerRequest request) {
        // ...
    }
}
~~~

Client thực tế gửi:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:c="https://example.com/customer/v1">
    <soap:Body>
        <c:FindCustomerRequest>
            <c:customerId>C-100</c:customerId>
        </c:FindCustomerRequest>
    </soap:Body>
</soap:Envelope>
~~~

Root QName của request là:

~~~text
{https://example.com/customer/v1}FindCustomerRequest
~~~

Endpoint mong:

~~~text
{https://example.com/customers/v1}FindCustomerRequest
~~~

Khác biệt nằm ở `customer` và `customers`. Cách khắc phục đúng là sửa client/XSD/WSDL theo contract thống nhất hoặc sửa annotation nếu annotation là phần sai. Không đổi `localPart`, servlet URL hoặc SOAPAction nếu chúng đã đúng.

## 12. Ví dụ: SOAPAction mapping không khớp

~~~java
@SoapAction("https://example.com/orders/GetOrder")
@ResponsePayload
public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request) {
    // ...
}
~~~

Nhưng HTTP request gửi:

~~~http
SOAPAction: "https://example.com/orders/GetOrderV2"
~~~

Nếu action mapping là mapping được dùng để chọn endpoint, hai giá trị không khớp. Cần sửa action theo binding contract hoặc cập nhật mapping theo version đúng. Nếu service đồng thời có `@PayloadRoot`, không mặc định `@PayloadRoot` sẽ cứu được request: kết quả phụ thuộc endpoint mappings thực tế đã đăng ký và request có khớp mapping nào.

Với SOAP 1.2, kiểm tra action parameter trong Content-Type thay vì chỉ nhìn HTTP SOAPAction header. Với WS-Addressing, đọc riêng `wsa:Action`.

## 13. Kiểm thử tái hiện endpoint mapping

### 13.1. Server-side test bằng MockWebServiceClient

`MockWebServiceClient` kiểm tra dispatcher/endpoint mappings mà không cần HTTP listener:

~~~java
@SpringJUnitConfig(OrderSoapTestConfiguration.class)
class OrderEndpointMappingTest {
    @Autowired
    ApplicationContext applicationContext;

    private MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(
            applicationContext);
    }

    @Test
    void mapsGetOrderByPayloadRootQName() {
        Source request = new StringSource("""
            <ord:GetOrderRequest
                xmlns:ord="https://example.com/orders/v1">
                <ord:orderId>ORD-1001</ord:orderId>
            </ord:GetOrderRequest>
            """);

        Source expected = new StringSource("""
            <ord:GetOrderResponse
                xmlns:ord="https://example.com/orders/v1">
                <ord:orderId>ORD-1001</ord:orderId>
            </ord:GetOrderResponse>
            """);

        client.sendRequest(withPayload(request))
            .andExpect(noFault())
            .andExpect(payload(expected));
    }
}
~~~

Test này cần test context có endpoint, mapping, adapter và service fixture. Nếu đổi namespace request thành URI khác, test nên fail ở mapping. Có thể thêm test âm cho root QName sai để ghi nhận Fault/error behavior của cấu hình.

### 13.2. Client-side test cho URI và request payload

`MockWebServiceServer` kiểm tra request client gửi qua `WebServiceTemplate`:

~~~java
mockServer.expect(connectionTo(
        "https://partner.example.com/ws"))
    .andExpect(payload(expectedRequest))
    .andRespond(withPayload(expectedResponse));

orderClient.getOrder("ORD-1001");
mockServer.verify();
~~~

Test này kiểm tra URL và payload outbound của client, không chứng minh server thật đã đăng ký mapping. Kết hợp client-side và server-side tests sẽ định vị được hợp đồng sai ở bên nào.

### 13.3. HTTP integration test

Khi cần kiểm tra servlet mapping, reverse proxy path hoặc SOAPAction HTTP header, gửi request qua server đang chạy:

~~~java
ResponseEntity<String> response = restTemplate.exchange(
    baseUrl + "/ws",
    HttpMethod.POST,
    new HttpEntity<>(soapEnvelope, headers),
    String.class);
~~~

Assertions cụ thể cần theo binding, SOAP version và error contract. Test này bao phủ HTTP/servlet boundary mà `MockWebServiceClient` không bao phủ.

## 14. Một quy trình chẩn đoán ngắn gọn, có thể lặp lại

Khi nhận ticket “không tìm thấy endpoint”, thu thập request đã redact và đi theo thứ tự:

1. **URL:** ghi actual scheme/host/port/context path/servlet path.
2. **HTTP:** xác minh POST, Content-Type, SOAP version và proxy rewrite.
3. **Envelope:** xác minh XML hợp lệ và SOAP Envelope namespace đúng.
4. **Body QName:** ghi namespace URI và local name của root element.
5. **Mapping:** xác định mapping type được cấu hình (`@PayloadRoot`, SOAPAction, WS-Addressing hoặc custom).
6. **Action:** so sánh đúng action source mà mapping đọc.
7. **Bean:** xác minh `@Endpoint` bean đã được tạo trong application context.
8. **Adapter:** nếu mapping thành công, kiểm tra argument/return handlers và marshalling.
9. **Regression test:** tạo test nhỏ cho request đã sửa và giữ fixture làm bằng chứng.
10. **Deploy verification:** kiểm tra WSDL/address/mapping trong đúng environment sau deploy.

Mỗi bước cần ghi rõ pass/fail và bằng chứng. Điều này tránh nhiều nhóm cùng sửa URL, WSDL, annotation và proxy mà không biết thay đổi nào giải quyết lỗi.

## 15. Checklist phòng ngừa

### Contract và namespace

- [ ] Version hóa WSDL/XSD và namespace URI.
- [ ] Ghi rõ QName request/response cho mỗi operation.
- [ ] Kiểm tra elementFormDefault và namespace của local elements.
- [ ] Không dùng prefix làm định danh.
- [ ] Đồng bộ WSDL action với client/server mapping.

### HTTP và servlet

- [ ] Document endpoint URL, context path và servlet mapping.
- [ ] Kiểm tra reverse proxy/ingress rewrite.
- [ ] Đúng HTTP method và SOAP Content-Type/version.
- [ ] WSDL address phù hợp environment.

### Endpoint mapping

- [ ] @Endpoint bean được scan/register.
- [ ] @PayloadRoot namespace/localPart chính xác.
- [ ] Nếu dùng SOAPAction/WS-Addressing, mapping tương ứng đã đăng ký.
- [ ] Không có mapping mơ hồ hoặc custom priority ngoài ý muốn.
- [ ] Adapter hỗ trợ method signature, JAXB types và return handler.

### Kiểm thử và quan sát

- [ ] Có server-side test cho từng payload root QName.
- [ ] Có client-side test cho actual URI và payload.
- [ ] Có HTTP integration test khi cần xác minh servlet/proxy/action header.
- [ ] Log QName, mapping decision và correlation ID an toàn.
- [ ] Không log raw SOAP token, credentials hoặc PII mặc định.

## 16. Câu hỏi tự kiểm tra

1. HTTP URL và payload root QName khác nhau thế nào?
2. Vì sao request tới đúng /ws vẫn có thể không tìm thấy endpoint?
3. QName được cấu thành từ những phần nào?
4. Đổi prefix XML có làm QName thay đổi không?
5. Khi nào @PayloadRoot được dùng để chọn endpoint?
6. @SoapAction cần endpoint mapping nào hỗ trợ?
7. SOAP 1.1 SOAPAction khác WS-Addressing wsa:Action ra sao?
8. SOAP 1.2 thường thể hiện action ở đâu trong HTTP Content-Type?
9. Endpoint mapping miss khác endpoint adapter failure thế nào?
10. Vì sao một @PayloadRoot method có thể không xuất hiện trong mapping registry?
11. MessageDispatcherServlet mapping liên hệ context path thế nào?
12. HTTP 404 và No endpoint mapping found có cùng nguồn gốc không?
13. WSDL binding cung cấp thông tin gì để kiểm tra action?
14. Vì sao không nên suy action URI từ tên Java method?
15. MockWebServiceClient và MockWebServiceServer kiểm tra hai phía nào?
16. Khi nào cần HTTP integration test thay vì chỉ dùng mock client/server?
17. Những thông tin nào an toàn và hữu ích để log khi mapping miss?
18. Làm sao xác định request đã tới adapter nhưng lỗi ở JAXB?

## 17. Bài tập thực hành

**Bối cảnh:** Bạn có Spring-WS service với ba operation GetOrder, CancelOrder và SubmitOrder, tất cả dùng chung HTTP endpoint /ws. Client báo lúc thành công, lúc nhận lỗi không tìm thấy endpoint sau khi nâng WSDL/XSD version.

### Phần A — Lập bản đồ contract

1. Liệt kê request root QName của ba operation.
2. Liệt kê SOAP version, Content-Type, SOAPAction và WS-Addressing Action nếu có.
3. Đối chiếu WSDL service/port address với URL trong từng environment.
4. Ghi servlet context path và MessageDispatcherServlet mapping.

### Phần B — Tạo lỗi có kiểm soát

5. Sửa namespace URI của GetOrderRequest thành namespace cũ.
6. Đổi localPart thành GetorderRequest để tạo lỗi case-sensitive.
7. Gửi SOAP 1.1 SOAPAction sai.
8. Gửi WS-Addressing wsa:Action sai trong khi payload QName đúng.
9. Gọi sai context path /integration-old/ws.
10. Bỏ hoặc đổi component scan khiến endpoint bean không được register.

### Phần C — Chẩn đoán và sửa

11. Bật log mapping có mục tiêu và ghi điểm request dừng.
12. Dùng QName (namespace URI + local part) để tìm namespace mismatch.
13. Kiểm tra mapping registry, endpoint bean và adapter.
14. Sửa đúng layer gây lỗi, không thay đồng thời URL/QName/action nếu chưa có bằng chứng.

### Phần D — Regression tests

15. Viết MockWebServiceClient test cho từng payload root QName.
16. Viết MockWebServiceServer test cho client URI và payload.
17. Viết HTTP integration test cho servlet path và action header.
18. Thêm negative tests cho root QName/action sai.
19. Kiểm tra response/error contract của từng ca và lưu correlation ID.
20. Chạy lại sau deploy trên environment có reverse proxy để xác nhận WSDL address và servlet mapping thực tế.

**Tiêu chí đạt:** có bảng mapping operation → QName → action → URL; xác định endpoint miss ở HTTP, parser hay mapping; test tái hiện được namespace/action/path sai; test đúng route tới endpoint method mong đợi; không cần thay đổi nhiều lớp không liên quan.

## 18. Tài liệu tham khảo chính thức

- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): MessageDispatcher, endpoint mappings, annotated endpoints và MessageDispatcherServlet.
- [PayloadRootAnnotationMethodEndpointMapping API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/endpoint/mapping/PayloadRootAnnotationMethodEndpointMapping.html): mapping theo payload root QName.
- [SoapActionAnnotationMethodEndpointMapping API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/server/endpoint/mapping/SoapActionAnnotationMethodEndpointMapping.html): mapping theo SOAPAction.
- [EndpointInterceptor API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/EndpointInterceptor.html): vòng đời interceptor sau khi mapping chọn endpoint.
- [W3C SOAP 1.1](https://www.w3.org/TR/SOAP/): SOAP Envelope, HTTP binding và SOAPAction.
- [W3C SOAP 1.2 Part 2](https://www.w3.org/TR/soap12-part2/): SOAP 1.2 HTTP binding và action media-type parameter.
- [W3C WS-Addressing Core](https://www.w3.org/TR/ws-addr-core/): wsa:Action và message addressing properties.

Javadoc liên kết theo Spring-WS 4.1.x/4.1.4. Khi dự án dùng version khác, đối chiếu dependency thực tế, endpoint mapping registrations và SOAP binding trước khi áp dụng.

## 19. Tổng kết

**Lỗi không tìm thấy endpoint phải được chẩn đoán từ ngoài vào trong:** xác minh host/context path/servlet mapping; parse SOAP Envelope; đọc root QName; xác định endpoint mapping dùng payload root, SOAPAction, WS-Addressing Action hay custom criteria; sau đó mới kiểm tra endpoint bean và adapter.

URL, QName, SOAPAction và WS-Addressing Action là các định danh ở những lớp khác nhau. Chúng không thay thế nhau và không phải lúc nào cũng xuất hiện đồng thời. Đối chiếu từng giá trị với WSDL/XSD và cấu hình mapping, dùng log/breakpoint có mục tiêu, rồi tạo regression test cho request thực tế.

**Ghi nhớ:** request tới đúng URL chưa chứng minh Spring-WS đã tìm được endpoint. Bằng chứng quyết định là payload/action khớp mapping đang được đăng ký và endpoint method mong đợi được chọn.
