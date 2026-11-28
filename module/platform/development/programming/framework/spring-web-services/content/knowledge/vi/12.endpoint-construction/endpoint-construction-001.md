# @Endpoint và trách nhiệm chuyển đổi thông điệp sang lời gọi nghiệp vụ

Trong **Spring Web Services (Spring-WS)**, `@Endpoint` đánh dấu một thành phần xử lý SOAP ở **ranh giới tích hợp**. Nó nhận thông điệp XML phù hợp với XSD/WSDL, chuyển dữ liệu sang dạng mà ứng dụng hiểu, điều phối lời gọi tới dịch vụ nghiệp vụ, rồi chuyển kết quả về **payload XML** đúng hợp đồng. Endpoint không nên ôm luôn truy vấn cơ sở dữ liệu, xử lý nghiệp vụ, cấu hình TLS hay tự xác minh chữ ký WS-Security.

Bài học thuộc chương **Xây dựng endpoint** của module `SPRING_WEB_SERVICES`. Ta áp dụng phương pháp **contract-first**: định nghĩa XSD/WSDL trước, sinh JAXB để ánh xạ XML, xây endpoint mỏng gọi application service, xử lý lỗi bằng SOAP Fault và kiểm thử luồng thực tế. Mục tiêu là nhận biết rõ **trách nhiệm của endpoint** và **trách nhiệm của từng lớp xung quanh nó**.

Các đoạn mã bên dưới minh họa Spring-WS 4.x trên Java 17+ với JAXB Jakarta. Tên lớp JAXB phụ thuộc công cụ sinh từ XSD; nếu dùng Spring-WS/JAXB thế hệ cũ, cần điều chỉnh dependency và package tương ứng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa `@Endpoint` và vai trò của `@PayloadRoot`, `@RequestPayload`, `@ResponsePayload`.
2. Mô tả đường đi từ SOAP Envelope tới `MessageDispatcher`, mapping, adapter, endpoint và application service.
3. Thiết kế endpoint mỏng: **nhận payload → kiểm tra ranh giới → chuyển đổi → gọi nghiệp vụ → chuyển đổi kết quả**.
4. Phân biệt **JAXB contract model**, **application command/query** và **domain model**.
5. Xây endpoint contract-first có QName và response type khớp XSD/WSDL, kể cả khi cần `JAXBElement`.
6. Phân loại validation, authorization, SOAP Fault, logging, XML security và WS-Security theo đúng tầng xử lý.
7. Viết kiểm thử chứng minh endpoint được định tuyến và trả XML/SOAP Fault đúng hợp đồng, không chỉ unit test trực tiếp phương thức Java.

## 1. Tình huống xuyên suốt: tra cứu đơn hàng

Giả sử dịch vụ SOAP cung cấp thao tác `GetOrder`. Client gửi `GetOrderRequest` chứa mã đơn, server trả `GetOrderResponse` có mã đơn và trạng thái.

### 1.1. Hợp đồng XSD trước khi có endpoint

Tệp minh họa `orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="OrderIdType">
    <xs:restriction base="xs:string">
      <xs:minLength value="1"/>
      <xs:maxLength value="64"/>
      <xs:pattern value="[A-Z0-9-]+"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="OrderStateType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="CREATED"/>
      <xs:enumeration value="SHIPPED"/>
      <xs:enumeration value="CANCELLED"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="GetOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="ord:OrderIdType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="ord:OrderIdType"/>
        <xs:element name="state" type="ord:OrderStateType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

Hai phần tử **global** có QName:

~~~text
{urn:example:orders:v1}GetOrderRequest
{urn:example:orders:v1}GetOrderResponse
~~~

Hợp đồng quy định namespace URI, local name, kiểu và thứ tự con. Với `elementFormDefault="qualified"`, `orderId` và `state` cũng thuộc namespace `urn:example:orders:v1`. Prefix trong XML có thể khác nhau; **namespace URI mới là danh tính**, không phải chuỗi prefix.

XSD này chỉ mô tả dữ liệu. Việc một mã đơn có tồn tại không, người gọi có quyền xem hay không, truy vấn có cần phân trang hay không là **quy tắc nghiệp vụ/ủy quyền**, không do XSD tự quyết định.

### 1.2. Request và response trên đường truyền

Request SOAP 1.1:

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

Response SOAP 1.1 thành công:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:GetOrderResponse>
      <ord:orderId>ORD-42</ord:orderId>
      <ord:state>CREATED</ord:state>
    </ord:GetOrderResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

**Endpoint thường làm việc với payload** `GetOrderRequest` và `GetOrderResponse`, không tự tạo/đọc toàn bộ `Envelope`. SOAP Header, phiên bản giao thức, HTTP transport và SOAP Fault được xử lý bởi các thành phần Spring-WS thích hợp.

### 1.3. WSDL nối operation với hai phần tử

Trong WSDL 1.1 document/literal, operation `GetOrder` có input/output tham chiếu các global elements trong XSD. Với cách công bố qua `DefaultWsdl11Definition`, hậu tố `Request`/`Response` trên tên global element là một quy ước để suy ra operation. Nếu dùng WSDL tĩnh, các `wsdl:part/@element` cũng phải trỏ đúng QName.

Điểm quan trọng: WSDL mô tả **giao diện đối tác nhìn thấy**, còn `@Endpoint` quyết định **implementation Java nhận payload**. Spring-WS không tự tạo logic nghiệp vụ từ một operation WSDL.

## 2. `@Endpoint` nằm ở đâu trong kiến trúc Spring-WS?

Một luồng request thành công điển hình:

~~~mermaid
sequenceDiagram
    autonumber
    participant Client as SOAP Client
    participant Servlet as MessageDispatcherServlet
    participant Dispatcher as MessageDispatcher
    participant Mapping as EndpointMapping
    participant Interceptor as EndpointInterceptor
    participant Adapter as EndpointAdapter
    participant Endpoint as OrdersEndpoint
    participant Service as OrderQueryService

    Client->>Servlet: HTTP POST /ws + SOAP Envelope
    Servlet->>Dispatcher: MessageContext (request)
    Dispatcher->>Mapping: Tìm endpoint từ payload QName
    Mapping-->>Dispatcher: EndpointInvocationChain
    Dispatcher->>Interceptor: handleRequest (schema/security...)
    Interceptor-->>Dispatcher: Cho phép xử lý
    Dispatcher->>Adapter: Chọn adapter và gọi endpoint
    Adapter->>Adapter: Resolve @RequestPayload thành JAXB
    Adapter->>Endpoint: getOrder(request)
    Endpoint->>Service: getVisibleOrder(orderId)
    Service-->>Endpoint: OrderSnapshot
    Endpoint-->>Adapter: GetOrderResponse
    Adapter->>Adapter: Viết @ResponsePayload thành XML
    Dispatcher->>Interceptor: handleResponse + afterCompletion
    Dispatcher-->>Servlet: MessageContext (response)
    Servlet-->>Client: HTTP SOAP response
~~~

Trường hợp SOAP Fault, interceptor từ chối request, adapter không hỗ trợ chữ ký method hoặc mapping không tìm được endpoint sẽ đi nhánh khác. **Không nên suy ra rằng mọi nhánh đều tự tạo SOAP Fault hoặc luôn có cùng HTTP status**; kết quả phụ thuộc cấu hình exception resolver, SOAP version và transport.

Các thành phần có trách nhiệm riêng:

| Thành phần | Công việc | Không nên nhầm với |
| --- | --- | --- |
| `MessageDispatcherServlet` | Tiếp nhận HTTP/SOAP qua URL servlet, phối hợp thông điệp và công bố WSDL/XSD | Nơi chứa nghiệp vụ đơn hàng |
| `MessageDispatcher` | Điều phối mapping, adapter, interceptor, exception resolver | Endpoint method cụ thể |
| `EndpointMapping` | Chọn endpoint theo QName, SOAPAction hoặc WS-Addressing khi được cấu hình | JAXB unmarshal |
| `EndpointAdapter` | Gọi method đã chọn, giải tham số và ghi kết quả | Business service |
| `@Endpoint` | Lớp biên tiếp nhận/gửi payload XML | `@RestController` xử lý REST/JSON |
| `OrderQueryService` | Áp dụng quy tắc truy vấn và kiểm tra quyền để đọc đơn | SOAP transport |
| `EndpointExceptionResolver` | Hỗ trợ chuyển exception thành SOAP Fault | Tự động định nghĩa đầy đủ fault contract |

`@Endpoint` là Spring stereotype cho các thành phần web service. Nó không có nghĩa phương thức được gọi trực tiếp theo URL kiểu `GET /orders/{id}`. Với SOAP, nhiều operation có thể đi qua cùng HTTP endpoint `POST /ws` và được chọn qua **nội dung/metadata thông điệp**.

## 3. Ba annotation chủ yếu trong một endpoint contract-first

### 3.1. `@Endpoint`: đăng ký lớp chuyên xử lý SOAP

Ví dụ:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;

@Endpoint
public class OrdersEndpoint {
    // Các phương thức handler được đăng ký theo annotation mapping.
}
~~~

Khi có component scanning và Spring-WS configuration thích hợp, class này trở thành bean để các endpoint mappings khảo sát. Chỉ gắn `@Endpoint` chưa đủ để định tuyến: cần method có annotation mapping hoặc mapping tùy chỉnh.

### 3.2. `@PayloadRoot`: chọn method dựa trên QName

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest")
~~~

`PayloadRootAnnotationMethodEndpointMapping` dùng QName của **phần tử gốc trong SOAP Body** để tìm handler. Trong trường hợp contract-first document/literal, đây thường là chiến lược dễ hiểu và bền vững.

Ba request sau cần phân biệt:

| Root payload | Có khớp mapping trên? | Lý do |
| --- | --- | --- |
| `<o:GetOrderRequest xmlns:o="urn:example:orders:v1">` | Có | URI + local name đúng |
| `<GetOrderRequest xmlns="urn:example:orders:v1">` | Có | Default namespace vẫn cùng QName |
| `<o:GetOrderRequest xmlns:o="urn:example:orders:v2">` | Không | Namespace version khác |
| `<GetOrderRequest>` không khai báo namespace | Không | QName thuộc no namespace |

Đừng sửa `localPart` chỉ để khớp tên Java method hoặc JAXB class: nó phải khớp **global element** mà WSDL/XSD công bố.

### 3.3. `@RequestPayload` và `@ResponsePayload`: dữ liệu vào/ra

~~~java
@ResponsePayload
public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request) {
    // ...
}
~~~

`@RequestPayload` báo cho adapter biết một tham số cần được giải từ XML payload. `@ResponsePayload` báo cho adapter rằng giá trị trả về của method cần được biến thành XML response payload.

Có các hình thức tham số/kết quả khác nhau tùy adapter/resolver được cấu hình: JAXB object có `@XmlRootElement`, `JAXBElement<T>`, `Source`, DOM và các hình thức khác. **Không phải mọi kiểu Java đều được tự hỗ trợ** chỉ vì có annotation. Nếu schema sinh named complex type không có root annotation, cần dùng `JAXBElement`/`ObjectFactory` theo binding thực tế.

Nếu method dùng `void` hoặc trả `null`, đừng mặc định nó đã đáp ứng hợp đồng request-response: điều đó có thể không tạo payload `GetOrderResponse` bắt buộc. Cần thiết kế đúng kiểu operation và kiểm thử XML đầu ra.

## 4. Thiết kế endpoint mỏng: translation boundary

Một endpoint được tổ chức tốt thường chỉ thực hiện sáu trách nhiệm gần ranh giới giao tiếp:

1. **Nhận thông điệp** do Spring-WS chuyển thành JAXB hoặc biểu diễn XML được hỗ trợ.
2. **Kiểm tra các tiền điều kiện của giao tiếp** khi chưa có lớp khác đảm nhiệm (ví dụ trường bắt buộc, ngữ nghĩa identifier), nhưng không lặp lại toàn bộ domain validation.
3. **Ánh xạ payload sang input ứng dụng** như command/query, không truyền mô hình SOAP tùy tiện vào domain.
4. **Gọi application service** đã được inject, nơi xử lý giao dịch, ủy quyền, idempotency và nghiệp vụ.
5. **Ánh xạ kết quả ứng dụng sang response contract** đúng QName, field và kiểu XSD.
6. **Để exception theo chính sách** được chuyển thành SOAP Fault qua exception resolver; không tự tạo XML lỗi tùy tiện trong response thành công.

Một sơ đồ phân lớp:

~~~mermaid
flowchart TD
    X["SOAP XML + WS-Security Header"] --> I["Spring-WS infrastructure<br/>dispatcher, mapping, adapters, interceptors"]
    I --> E["@Endpoint<br/>XML contract ↔ application DTO"]
    E --> A["Application service<br/>use case, orchestration, authorization"]
    A --> D["Domain model/rules"]
    A --> R["Repository / external integration"]
    A --> E
    E --> I
    I --> Y["SOAP response hoặc SOAP Fault"]
~~~

Không nên đưa `WebServiceMessage`, `JAXBElement`, `SoapHeader` hay `MessageContext` sâu vào domain layer nếu ứng dụng không có nhu cầu tích hợp đó. Khi business service phải biết SOAP namespace để quyết định tình trạng đơn hàng, đó là dấu hiệu các tầng đang phụ thuộc ngược.

### 4.1. Ai sở hữu việc chuyển đổi?

| Công việc | Thành phần chịu trách nhiệm chính |
| --- | --- |
| SOAP Envelope ↔ thông điệp Spring-WS | Message factory/transport + hạ tầng Spring-WS |
| Chọn method từ payload QName | EndpointMapping |
| Payload XML ↔ đối tượng JAXB | EndpointAdapter/argument resolver/OXM |
| Đối tượng JAXB ↔ application query/command | Mapper ở ranh giới endpoint (hoặc mapper riêng) |
| Quy tắc tìm đơn, kiểm soát quyền xem đơn | Application/domain service |
| Domain result ↔ JAXB response | Mapper ở ranh giới endpoint |
| JAXB response ↔ payload XML | EndpointAdapter/return value handler/OXM |
| Validation XSD / WS-Security | Interceptor hoặc tầng tương ứng được cấu hình |
| Exception ↔ SOAP Fault | EndpointExceptionResolver/fault handler |

Giữ ranh giới này rõ giúp sửa XSD/JAXB hoặc đổi SOAP version mà không bắt toàn bộ domain logic thay đổi theo.

## 5. Ví dụ Java: từ JAXB request sang lời gọi nghiệp vụ

Giả sử từ XSD mục 1, công cụ XJC sinh các kiểu trong package `com.example.orders.contract.v1`:

- `GetOrderRequest` với `getOrderId()`.
- `GetOrderResponse` với `setOrderId(...)` và `setState(...)`.
- `OrderStateType` là enum JAXB tương ứng ba giá trị `CREATED`, `SHIPPED`, `CANCELLED`.

Hình dạng này thường gặp với **global element chứa anonymous complex type**; generator và external binding có thể cho kết quả khác. Trước khi dùng code, xem class và `ObjectFactory` sinh thực tế.

### 5.1. Input/result ứng dụng không phụ thuộc SOAP

~~~java
// Các kiểu application/domain thuần, không dùng annotation SOAP/JAXB.

public record GetOrderQuery(String orderId) {
}

public enum OrderState {
    CREATED, SHIPPED, CANCELLED
}

public record OrderSnapshot(
        String orderId,
        OrderState state) {
}

public interface OrderQueryService {
    OrderSnapshot getVisibleOrder(GetOrderQuery query);
}
~~~

Đây là **các khai báo khái niệm**, đặt trong file Java riêng theo quy tắc một public top-level type mỗi file. `getVisibleOrder` phải xác định danh tính đã xác thực và thực thi quyền xem theo security context/chính sách đáng tin cậy, không chỉ dựa vào `orderId` được người gọi nhập.

Một implementation thật có thể sử dụng repository và chính sách authorization. Endpoint không cần biết truy vấn SQL, transaction hay thứ tự tìm cache/database.

### 5.2. Mapper tách biệt khỏi handler

~~~java
import org.springframework.stereotype.Component;

// Các import JAXB và application model được lược bớt.
@Component
public class OrderSoapMapper {

    public GetOrderQuery toQuery(GetOrderRequest request) {
        return new GetOrderQuery(request.getOrderId());
    }

    public GetOrderResponse toResponse(OrderSnapshot result) {
        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(result.orderId());

        // Giả định giá trị enum JAXB và domain có cùng tên.
        response.setState(OrderStateType.valueOf(result.state().name()));
        return response;
    }
}
~~~

Mapper này minh họa một phép ánh xạ đơn giản. Trong hệ thống lớn, việc chuyển đổi có thể gồm ngày giờ với timezone, `BigDecimal` và currency, collection, field optional/nil, version enum, mã lỗi và biểu diễn identifier. **Không nên ép mapper tự ra quyết định nghiệp vụ**: ví dụ liệu `SHIPPED` có thể hủy được là quyết định của use case, không phải phép đổi enum sang chuỗi.

Đặt mapper riêng cũng giúp unit test sự phù hợp giữa domain result và SOAP response mà không phải khởi động toàn bộ servlet.

### 5.3. Endpoint hoàn chỉnh ở mức cấu trúc

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrdersEndpoint {

    private static final String ORDERS_NS =
        "urn:example:orders:v1";

    private final OrderQueryService orderQueryService;
    private final OrderSoapMapper mapper;

    public OrdersEndpoint(
            OrderQueryService orderQueryService,
            OrderSoapMapper mapper) {
        this.orderQueryService = orderQueryService;
        this.mapper = mapper;
    }

    @PayloadRoot(
        namespace = ORDERS_NS,
        localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        GetOrderQuery query = mapper.toQuery(request);
        OrderSnapshot result = orderQueryService.getVisibleOrder(query);
        return mapper.toResponse(result);
    }
}
~~~

Phương thức `getOrder` làm đúng việc của một **boundary adapter**:

- Input là JAXB request thuộc SOAP contract.
- Chuyển sang `GetOrderQuery` thuần ứng dụng.
- Gọi `OrderQueryService`.
- Chuyển `OrderSnapshot` về JAXB response hợp đồng.

Nó **không** tự dựng SOAP Envelope, không truy vấn database, không ghi cookie HTTP và không tự xác thực chữ ký số. Nếu server cần kiểm tra quyền xem đơn, hãy dùng một service/security policy có thể kiểm thử được, với danh tính được xác thực từ lớp bảo mật.

### 5.4. Luồng dữ liệu cần phân biệt

~~~text
<ord:GetOrderRequest>             ← XML element, XSD/WSDL
         │
         ▼ JAXB unmarshal / endpoint adapter
GetOrderRequest                   ← Java contract DTO
         │
         ▼ OrderSoapMapper
GetOrderQuery                     ← Application input
         │
         ▼ OrderQueryService
OrderSnapshot                     ← Application/domain result
         │
         ▼ OrderSoapMapper
GetOrderResponse                  ← Java contract DTO
         │
         ▼ JAXB marshal / endpoint adapter
<ord:GetOrderResponse>            ← XML element, XSD/WSDL
~~~

Việc tạo Java contract object là chức năng của binding; việc định nghĩa quy tắc nghiệp vụ là chức năng của domain/application. Hai tầng có thể sử dụng cùng kiểu trong bản demo nhỏ, nhưng tách chúng thường giúp hợp đồng SOAP ổn định khi nội bộ thay đổi.

## 6. `JAXBElement` khi class không có `@XmlRootElement`

Ví dụ ở mục 5 giả định XJC sinh class root trực tiếp. Một schema khác có thể khai báo:

~~~xml
<xs:complexType name="GetOrderRequestType">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
  </xs:sequence>
</xs:complexType>

<xs:element name="GetOrderRequest"
            type="ord:GetOrderRequestType"/>
~~~

Với mô hình này, XJC thường sinh class `GetOrderRequestType` **không có** `@XmlRootElement`, và `ObjectFactory` cung cấp `createGetOrderRequest(value)` trả `JAXBElement<GetOrderRequestType>`. Nếu marshal trực tiếp một type chưa có root element declaration, JAXB có thể báo lỗi thiếu `@XmlRootElement`.

Ví dụ biến thể endpoint, **không đăng ký đồng thời với method cùng QName ở mục 5**:

~~~java
import jakarta.xml.bind.JAXBElement;

// Giả định ObjectFactory/GetOrderRequestType/
// GetOrderResponseType được sinh từ XSD tương ứng.

@PayloadRoot(
    namespace = ORDERS_NS,
    localPart = "GetOrderRequest")
@ResponsePayload
public JAXBElement<GetOrderResponseType> getOrderTyped(
        @RequestPayload JAXBElement<GetOrderRequestType> element) {

    GetOrderRequestType xmlValue = element.getValue();
    GetOrderQuery query = new GetOrderQuery(xmlValue.getOrderId());

    OrderSnapshot result = orderQueryService.getVisibleOrder(query);

    GetOrderResponseType responseValue =
        objectFactory.createGetOrderResponseType();
    responseValue.setOrderId(result.orderId());
    responseValue.setState(
        OrderStateType.valueOf(result.state().name()));

    return objectFactory.createGetOrderResponse(responseValue);
}
~~~

`objectFactory` ở đây là field/bean của model JAXB sinh tương ứng; đoạn method **chỉ để minh họa biến thể**, cần thêm nó và các dependency vào class thật. Điều quan trọng là **QName của response** được gắn qua `createGetOrderResponse(...)`. `javax.xml.namespace.QName` vẫn là kiểu QName chuẩn của Java kể cả khi `JAXBElement` thuộc package `jakarta.xml.bind`.

Không giả định rằng thêm một bean `Jaxb2Marshaller` sẽ tự động khiến **mọi** dạng method parameter được hỗ trợ. Chữ ký handler phải tương thích với argument resolver/return value handler của `DefaultMethodEndpointAdapter` trong cấu hình Spring-WS đang dùng. Khi có vấn đề, kiểm tra annotation JAXB và kiểu return thực tế, thay vì sửa tùy tiện QName trong XSD.

## 7. Trách nhiệm validation: endpoint không nên là XML validator thủ công

Dữ liệu trao đổi có ít nhất ba tầng kiểm tra:

| Tầng | Những câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **XML / XSD validation** | Root QName, kiểu, thứ tự, trường bắt buộc, cardinality hợp lệ? | Có `orderId`, đúng regex, đúng namespace |
| **Application/domain validation** | Dữ liệu có ý nghĩa nghiệp vụ và trạng thái hệ thống cho phép thao tác? | Order tồn tại, trạng thái truy xuất được |
| **Authorization/security** | Danh tính đã xác thực có được phép đọc đơn này? | Người gọi chỉ xem đơn thuộc phạm vi của mình |

Để kiểm tra XSD tại ranh giới SOAP, có thể sử dụng `PayloadValidatingInterceptor`:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

@Configuration
@EnableWs
public class OrdersSoapValidationConfig implements WsConfigurer {

    @Bean
    public PayloadValidatingInterceptor ordersPayloadValidator() {
        PayloadValidatingInterceptor validator =
            new PayloadValidatingInterceptor();

        validator.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd"));
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);
        return validator;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(ordersPayloadValidator());
    }
}
~~~

**Lưu ý API:** ví dụ sử dụng setter `setSchema(Resource)` của `AbstractValidatingInterceptor` trong Spring-WS. Nếu một dự án dùng `XsdSchema` bean, có thể sử dụng `setXsdSchema(...)` theo API tương ứng. Đường dẫn tài nguyên là classpath **runtime**, không phải đường dẫn `src/main/resources` trên filesystem. `@EnableWs` chỉ nên được cấu hình phù hợp với ứng dụng, tránh trùng lặp servlet/config ngoài ý muốn.

Khi `setValidateResponse(true)`, response XML của server cũng có thể được kiểm tra theo schema, hữu ích trong phát triển và test. Với production, cần cân nhắc chi phí và cách xử lý lỗi nếu response chưa hợp lệ. Tùy cấu hình validator và SOAP version, request lỗi có thể bị chặn và tạo SOAP Fault; phải kiểm tra code/reason/detail thực tế thay vì mặc định mọi trường hợp luôn cùng một response.

### 7.1. Không đồng nhất `required=true` và validation

Annotation JAXB như `@XmlElement(required=true)` là metadata binding. Nó **không bảo đảm** mọi lần marshal/unmarshal sẽ tự kiểm tra hết `xs:minLength`, `xs:sequence` hoặc `maxOccurs` nếu bạn chưa bật schema validation phù hợp. Endpoint cũng không nên chỉ gọi `request.getOrderId()` rồi tin rằng mọi thứ đã hợp lệ.

Trường hợp quan trọng là request thật sự đã đi qua validator được cấu hình: một unit test gọi trực tiếp `OrdersEndpoint.getOrder(...)` **bỏ qua** interceptor, trừ khi test tự kích hoạt nó.

### 7.2. XSD không thể thay thế authorization

`GetOrderRequest.orderId` là một tham số do bên ngoài gửi. Mã đơn `ORD-42` hợp XSD không chứng minh người gọi có quyền xem dữ liệu đơn đó. Authentication/authorization phải dùng danh tính từ kênh hoặc token/chữ ký đã được xác minh theo chính sách, rồi kiểm tra phạm vi truy cập trong application layer.

**Tránh sai lầm:** nhận một `buyerId` trong Body rồi coi đó là danh tính đáng tin. Khi thiết kế service `getVisibleOrder(...)`, cần có cách truyền/lấy principal đáng tin và kiểm tra quyền cụ thể, không chỉ kiểm tra hình dạng XML.

## 8. SOAP Fault: endpoint không nên ngụy trang lỗi thành response thành công

Có ba tình huống:

1. **Request sai hợp đồng XML**: ví dụ `GetOrderRequest` thiếu `orderId`; validation từ chối.
2. **Request hợp đồng nhưng không thỏa nghiệp vụ**: ví dụ order không tồn tại.
3. **Hệ thống lỗi tạm thời**: ví dụ database không thể truy cập.

Một cách thiết kế phù hợp là business/application service ném exception có nghĩa rõ ràng, và `EndpointExceptionResolver` chuyển exception thành SOAP Fault theo hợp đồng. Không nên trả:

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
  <ord:orderId></ord:orderId>
  <ord:state>ERROR</ord:state>
</ord:GetOrderResponse>
~~~

XML trên còn **vi phạm XSD minh họa**: `orderId` không được rỗng và `ERROR` không thuộc enum `OrderStateType`. Ngay cả nếu nới schema để cho phép, việc dùng “response thành công + string ERROR” vẫn khiến client khó phân biệt fault với trạng thái nghiệp vụ.

Bảng quy ước lỗi gợi ý:

| Exception/tình huống | Ý nghĩa | Cách xử lý đề xuất |
| --- | --- | --- |
| XML không hợp XSD | Client gửi sai hợp đồng | SOAP Fault phía request (SOAP 1.1 thường là Client; SOAP 1.2 thường là Sender) |
| `OrderNotFoundException` | Order ID hợp lệ về hình dạng nhưng không tồn tại | SOAP Fault có mã nghiệp vụ ổn định, nếu hợp đồng yêu cầu |
| `OrderAccessDeniedException` | Danh tính đã xác thực không có quyền | Từ chối theo security policy; không làm lộ dữ liệu đơn |
| Timeout hạ tầng | Không thể tra cứu | Fault phía server hoặc lỗi transport, retry policy rõ ràng |
| JAXB không tạo được response hợp đồng | Lỗi phía triển khai | Ghi log có kiểm soát; trả lỗi server phù hợp |
| WS-Security validation thất bại | Chữ ký/token/timestamp không hợp lệ | Security interceptor/fault handler từ chối |

Trong Spring-WS, `SoapFaultMappingExceptionResolver`, `SoapFaultAnnotationExceptionResolver` hoặc exception resolver tùy biến có thể được sử dụng theo yêu cầu. **Không suy ra** rằng mọi exception Java đều tự có fault detail khớp XSD/WSDL: cần cấu hình resolver, fault code, message, detail và kiểm thử đúng SOAP version.

### 8.1. SOAP Fault 1.1 minh họa

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Order not found</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là cấu trúc minh họa. Nếu hợp đồng cần mã `ORDER_NOT_FOUND` để client quyết định hành động, nên thiết kế một phần tử **fault detail** có schema và cách ánh xạ chuẩn, thay vì bắt client so khớp nội dung `faultstring`. SOAP 1.2 có Fault structure khác, không dùng mẫu 1.1 nguyên xi.

## 9. Interceptor, SOAP Header và bảo mật: không nhồi vào handler

Một request SOAP có thể chứa Header chứa correlation ID, WS-Security token, signature hoặc WS-Addressing metadata. Không nên để endpoint tự parse một chuỗi XML tùy ý từ Header và quyết định xác thực:

| Chức năng | Nơi phù hợp | Lưu ý |
| --- | --- | --- |
| XML schema validation | `PayloadValidatingInterceptor` / schema validation | Kiểm tra cấu trúc theo XSD |
| Correlation ID và tracing | Interceptor/logging infrastructure | Không đưa toàn bộ payload nhạy cảm vào log |
| Signature, timestamp, token WS-Security | `Wss4jSecurityInterceptor` và security stack | Xác minh chữ ký bằng thư viện chuyên trách |
| TLS/mTLS và kiểm tra chứng chỉ | Transport/container/gateway | Xác minh trust chain, hostname và client cert theo chính sách |
| Quyền xem đơn của caller | Application service/security policy | Không tin danh tính khai báo trong Body |
| Chuyển request thành business query | Endpoint/mapper | Không là trách nhiệm của WSS4J |
| Truy vấn đơn hàng | Application/domain service | Không là trách nhiệm của SOAP transport |

**Điểm kiến trúc cần nhớ:** `EndpointInterceptor` thường nằm trong invocation chain **sau bước endpoint mapping**. Vì vậy không thể khẳng định một interceptor gắn với endpoint sẽ bảo vệ tất cả request HTTP không khớp mapping. Các lớp bảo vệ ở gateway, servlet/filter và transport vẫn cần được cấu hình riêng cho đúng phạm vi.

### 9.1. Bảo mật XML không kết thúc ở việc JAXB unmarshal

XML parser cần cấu hình chống XXE/DTD bên ngoài theo provider và phương thức parse; giới hạn kích thước request, độ sâu XML và thời gian xử lý. Với thông điệp có chữ ký, phải bảo đảm phần tử đã được xác thực là **đúng phần tử endpoint xử lý**, tránh tình huống XML signature wrapping: một nút được ký nhưng một nút khác được business service sử dụng.

Đừng dùng XPath rộng như `//*[local-name()='GetOrderRequest']` để tự chọn dữ liệu “có vẻ là request” rồi bypass QName và security context chuẩn. Khi định tuyến theo `@PayloadRoot`, namespace/version là một phần hợp đồng và góp phần tránh chọn nhầm phần tử.

## 10. Khi nào endpoint có thể xử lý XML trực tiếp?

Không phải hệ thống nào cũng dùng JAXB cho mọi thao tác. Spring-WS hỗ trợ các cách tiếp cận như `Source`, DOM hoặc payload model khác tùy adapter/resolver.

Ví dụ khung handler dùng `Source`:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest")
@ResponsePayload
public Source handleRaw(@RequestPayload Source payload) {
    // Biến đổi XML có kiểm soát, trả Source hợp XSD.
    // Phải bảo đảm parser, validation và giới hạn tài nguyên an toàn.
    return responseSource;
}
~~~

Đây chỉ là **đoạn minh họa chữ ký**, chưa có `responseSource` hay code xử lý thực tế. Không đăng ký handler này đồng thời với handler JAXB ở mục 5 cho cùng QName, nếu không việc chọn endpoint trở nên nhập nhằng hoặc bị từ chối cấu hình. Khi làm việc trực tiếp với XML, ứng dụng phải có lý do kỹ thuật cụ thể (tích hợp bán cấu trúc, streaming hoặc xử lý tài liệu phức tạp) và kiểm soát namespace, parser, XPath và validation.

Đối với thao tác nghiệp vụ rõ schema, **JAXB contract model + mapper + application service** thường dễ kiểm thử và bảo trì hơn việc viết XPath trực tiếp trong endpoint.

## 11. Endpoint và SOAP client là hai hướng của cùng hợp đồng

Ở phía client, `WebServiceTemplate` có thể sử dụng `Jaxb2Marshaller` để:

~~~text
GetOrderRequest Java object
        │ marshal
        ▼
<GetOrderRequest> XML payload
        │ Spring-WS wraps in SOAP Envelope
        ▼
HTTP POST /ws
        │ server dispatches to @Endpoint
        ▼
<GetOrderResponse> XML payload
        │ unmarshal
        ▼
GetOrderResponse Java object
~~~

Nếu client sử dụng `JAXBElement<T>` vì type không có `@XmlRootElement`, cần tạo wrapper bằng `ObjectFactory` để đảm bảo đúng QName. Nếu SOAP 1.1 binding yêu cầu `SOAPAction` cụ thể, client cần gửi action theo WSDL; trong Spring-WS có thể dùng `SoapActionCallback`.

Về phía endpoint, `@PayloadRoot` chọn handler dựa trên QName. Nếu ứng dụng chọn mapping theo `@SoapAction` hoặc WS-Addressing `@Action`, phải thống nhất metadata với WSDL/client và kiểm tra hành vi khi các thông tin xung đột. **Định tuyến thành công không có nghĩa request đã được xác thực hay business logic đã hợp lệ.**

## 12. Kiểm thử: gọi thẳng method là chưa đủ

Một test:

~~~java
GetOrderResponse result = ordersEndpoint.getOrder(request);
~~~

chỉ kiểm thử một phần: mapping và service được gọi (nếu inject mock phù hợp). Nó **không** chứng minh `MessageDispatcher` chọn đúng handler, JAXB đọc được XML, interceptor validation/WS-Security chạy, hay SOAP Fault trên đường truyền đúng hợp đồng.

Cần ít nhất ba lớp kiểm thử bổ sung.

### 12.1. Unit test endpoint orchestration

Mock `OrderQueryService` và dùng `OrderSoapMapper` thật hoặc mock theo mục tiêu test:

~~~java
@Test
void mapsSoapRequestToApplicationQuery() {
    GetOrderRequest request = new GetOrderRequest();
    request.setOrderId("ORD-42");

    when(orderQueryService.getVisibleOrder(
        new GetOrderQuery("ORD-42")))
        .thenReturn(new OrderSnapshot("ORD-42", OrderState.CREATED));

    GetOrderResponse response = ordersEndpoint.getOrder(request);

    assertEquals("ORD-42", response.getOrderId());
    assertEquals(OrderStateType.CREATED, response.getState());
    verify(orderQueryService)
        .getVisibleOrder(new GetOrderQuery("ORD-42"));
}
~~~

Đoạn trên là **test minh họa** với JUnit/Mockito đã cấu hình; `GetOrderQuery` là Java record nên so sánh dựa trên giá trị. Test chứng minh orchestration/mapper đúng trong Java, không chứng minh WSDL/XSD/SOAP hoạt động.

### 12.2. Test Spring-WS dispatching và XML payload

Có thể dùng `MockWebServiceClient` để đưa request qua hạ tầng Spring-WS:

~~~java
// Giả định applicationContext và fixture XML đã được chuẩn bị.
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

client.sendRequest(
        withPayload(new StringSource(getOrderRequestPayloadXml)))
      .andExpect(
        payload(new StringSource(expectedResponsePayloadXml)));
~~~

Các static factory `withPayload` và `payload` thuộc Spring-WS Test, còn `StringSource` là utility XML của Spring. `getOrderRequestPayloadXml` ở đây là **nội dung phần tử root request**, không phải toàn bộ SOAP Envelope nếu dùng `withPayload(...)`.

Khi chạy test với service stub/mock, phải có cấu hình mapping, adapter, JAXB binding và interceptor phù hợp trong application context. Test theo cách này kiểm tra nhiều tầng hơn so với gọi Java method trực tiếp.

### 12.3. Ma trận kiểm thử có chủ đích

| Tình huống | Kỳ vọng | Chức năng được kiểm chứng |
| --- | --- | --- |
| Request root QName `GetOrderRequest` v1, `orderId=ORD-42` | Chọn đúng endpoint và trả response hợp XSD | Mapping + adapter + JAXB |
| Prefix XML đổi, URI không đổi | Cùng endpoint nhận được | QName, không phụ thuộc prefix |
| Namespace đổi `v1` → `v2` | Endpoint v1 không nhận nhầm | Versioning và mapping |
| Root local name sai | Không vào handler v1 | `@PayloadRoot` |
| Thiếu `orderId` | Bị từ chối khi bật XSD validation | Schema interceptor |
| `orderId` có ký tự không thuộc pattern | Bị từ chối khi bật validation | XSD restriction |
| `orderId` hợp lệ về hình dạng nhưng không tồn tại | SOAP Fault nghiệp vụ theo hợp đồng | Application service + fault resolver |
| Caller không có quyền xem đơn | Từ chối đúng policy, không lộ đơn | Authorization |
| Response thiếu `state` | Test phát hiện response không hợp XSD | Response mapper + validation |
| JAXB trả root QName sai | Client/test XML phát hiện | Marshalling |
| Chữ ký WS-Security sai hoặc timestamp hết hạn | Từ chối trước nghiệp vụ theo policy | Security interceptor |
| TLS certificate không tin cậy | Từ chối ở transport, không gọi endpoint | TLS/mTLS |
| Client .NET sinh từ WSDL công bố | Gửi/nhận payload đúng tên/kiểu | Interoperability |
| SOAP Fault 1.1/1.2 | Fault code/structure đúng version đang dùng | SOAP fault handling |
| Có nhiều handler trùng QName | Phát hiện xung đột cấu hình, tránh routing ngẫu nhiên | EndpointMapping |

Ở phía SOAP client, `MockWebServiceServer` có thể mô phỏng server để kiểm tra `WebServiceTemplate` gửi XML đúng hợp đồng và xử lý response/fault. Với đối tác khác nền tảng, cần kiểm thử **wire XML và WSDL thực tế** chứ không chỉ dùng cùng các Java class.

## 13. Những thiết kế endpoint nên tránh

| Anti-pattern | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Endpoint chứa SQL, transaction và hàng loạt luật nghiệp vụ | Khó test, domain phụ thuộc SOAP, code phình to | Chuyển use case vào application/domain service |
| Service nhận trực tiếp JAXB request | Nghiệp vụ bị khóa vào một phiên bản XML | Chuyển sang command/query riêng |
| Mapper quyết định có cho phép hủy đơn | Ranh giới chuyển đổi bị lẫn nghiệp vụ | Đưa rule vào service |
| Endpoint tự tạo SOAP Envelope bằng chuỗi | Dễ sai namespace, SOAP version, encoding | Để framework tạo thông điệp |
| Dùng `@PayloadRoot` chỉ có localPart mà bỏ namespace khi contract có namespace | Có thể map sai version/tên, hoặc không match | Dùng QName đầy đủ |
| Bắt mọi exception và trả `success=false` | Mất semantics SOAP Fault, client khó retry | Dùng fault resolver và hợp đồng lỗi |
| Không validation vì JAXB đã “biết XSD” | Dữ liệu sai vẫn có thể lọt qua | Bật XSD validation và business validation |
| Tin `buyerId`/`role` trong Body để ủy quyền | Có nguy cơ giả mạo danh tính | Dựa trên principal đã xác thực |
| Tự kiểm chữ ký bằng XPath hoặc substring | Dễ chọn sai nút hoặc bypass XML Signature | Dùng WS-Security library phù hợp |
| So sánh XML text và yêu cầu prefix cố định | Test hỏng khi serializer đổi prefix hợp lệ | So QName/schema và dữ liệu |
| Trùng hai handler cùng `@PayloadRoot` | Ambiguous mapping hoặc startup/test failure | Mỗi request QName ánh xạ rõ ràng |
| Trả `null` khi WSDL yêu cầu response | Có thể không tạo response hợp đồng | Trả JAXB response đầy đủ hoặc tạo fault |

### 13.1. Checklist review một endpoint mới

Trước khi hoàn thành một endpoint, hãy xác minh:

1. XSD/WSDL có global elements cho request/response, namespace và kiểu dữ liệu rõ.
2. Java JAXB binding phù hợp với contract (root annotation hoặc `JAXBElement`).
3. `@Endpoint` và `@PayloadRoot` có namespace/localPart đúng.
4. `@RequestPayload`/`@ResponsePayload` sử dụng kiểu mà adapter hỗ trợ.
5. Method chỉ điều phối và chuyển đổi; application service nắm nghiệp vụ/transaction/authorization.
6. Request/response được kiểm tra XSD ở lớp phù hợp; lỗi được ánh xạ thành SOAP Fault.
7. Security interceptor và TLS/mTLS được cấu hình độc lập; không tin dữ liệu caller chưa xác thực.
8. Có unit test mapping, dispatch test, fault test và ít nhất một integration test với XML/wire contract.
9. Response không chứa dữ liệu nhạy cảm ngoài phạm vi đối tác được quyền xem.
10. Thay đổi version hợp đồng được review tương thích và sinh lại client/endpoint nếu cần.

## 14. Bài tập vận dụng

**Bài 1 — Trách nhiệm của endpoint.** Một handler `@Endpoint` dài 400 dòng, chứa SQL và tạo SOAP XML bằng chuỗi. Hãy phân chia nó thành mapper, application service, repository và lớp lỗi; giải thích điều gì vẫn nằm trong endpoint.

**Bài 2 — QName.** Client gửi `<GetOrderRequest xmlns="urn:example:orders:v2">` nhưng server map namespace v1. Vì sao Java method không được chọn? Có nên đổi `@PayloadRoot` để chấp nhận mọi version không?

**Bài 3 — JAXBElement.** Schema dùng global element `GetOrderRequest` trỏ đến named type `GetOrderRequestType`. Vì sao kiểu Java có thể cần `ObjectFactory.createGetOrderRequest(...)`? Endpoint response có cần wrapper tương tự không?

**Bài 4 — Validation.** Request thiếu `orderId`, nhưng unit test gọi Java method trực tiếp vẫn chạy. Cần bật lớp kiểm tra nào để thử chính xác SOAP request thực tế? Vì sao `@XmlElement(required=true)` chưa đủ?

**Bài 5 — Business errors.** `OrderQueryService` ném `OrderNotFoundException`. Thiết kế fault code/detail và resolver để client xử lý lỗi ổn định như thế nào? Vì sao không nên tạo trạng thái `ERROR` ngoài enum của `GetOrderResponse`?

**Bài 6 — Quyền truy cập.** Người gọi `A` yêu cầu đơn `ORD-42` thuộc người dùng `B`. XSD hợp lệ, JAXB unmarshal thành công. Thành phần nào phải từ chối? Danh tính tin cậy lấy từ đâu?

**Bài 7 — Interoperability.** Java client hoạt động nhưng .NET client gặp lỗi khi unmarshalling response. Bạn sẽ kiểm tra WSDL/XSD, QName root, `xs:sequence`, enum, SOAPAction và SOAP version theo thứ tự nào?

### Gợi ý định hướng

- Với bài 1, endpoint chỉ giữ phần ranh giới SOAP, ánh xạ và lời gọi service; domain và persistence không nằm trong handler.
- Với bài 2, namespace URI là thành phần QName, thay version cần chiến lược versioning/migration minh bạch.
- Với bài 3, type không tự xác định global element root; `JAXBElement` gắn QName.
- Với bài 4, integration test phải chạy qua Spring-WS dispatcher/interceptor và XSD validation.
- Với bài 5, lỗi hợp đồng cần SOAP Fault có nghĩa, không dùng response thành công sai schema.
- Với bài 6, service/security policy phải dựa vào danh tính đã xác thực và quyền trên tài nguyên.
- Với bài 7, kiểm tra **XML trên đường truyền** cùng hợp đồng được công bố, không chỉ object Java.

**Ghi nhớ:** `@Endpoint` là **cổng chuyển đổi giữa hợp đồng SOAP và use case ứng dụng**. `@PayloadRoot` chọn handler theo QName; `@RequestPayload`/`@ResponsePayload` đưa dữ liệu qua adapter/JAXB; endpoint gọi service và tạo response đúng XSD/WSDL. Schema validation, SOAP Fault, XML/WS-Security, chứng chỉ và kiểm thử tương thích thuộc các cơ chế bổ trợ có trách nhiệm riêng—được kết nối với endpoint, không bị nhồi vào endpoint.
