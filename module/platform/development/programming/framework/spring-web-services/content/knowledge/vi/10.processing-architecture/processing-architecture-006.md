# MessageDispatcher và các chiến lược tìm, gọi endpoint

Trong **Spring Web Services (Spring-WS)**, một SOAP request không tự động biến thành lời gọi tới phương thức Java chỉ vì trong dự án có class được gắn `@Endpoint`. Hạ tầng cần **nhận thông điệp**, **xác định endpoint phù hợp**, **chọn cơ chế gọi endpoint**, thực thi các **interceptor**, và **tạo phản hồi hoặc SOAP Fault**. Thành phần điều phối trung tâm của quá trình đó là `MessageDispatcher`.

Bài này thuộc chương **Kiến trúc xử lý** của module `SPRING_WEB_SERVICES`, phục vụ mục tiêu phát triển SOAP theo hướng **contract-first** với XSD/WSDL, JAXB, endpoint và SOAP client. Hiểu tuyến xử lý giúp xác định chính xác vì sao một request “đúng XML” vẫn không vào endpoint, vì sao đặt `@SoapAction` có thể khác `@PayloadRoot`, và những thành phần nào chịu trách nhiệm validation, XML security, WS-Security, chứng chỉ, lỗi và kiểm thử tương thích.

Các ví dụ dùng Spring-WS 4.x với Java/Jakarta JAXB làm ngữ cảnh. Những thuộc tính và loại mapping được giải thích theo API Spring-WS; cấu hình cụ thể có thể khác theo phiên bản, starter và ứng dụng, vì vậy luôn kiểm tra kết quả chạy thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả đường đi **HTTP → `MessageDispatcherServlet` → `MessageDispatcher` → `EndpointMapping` → `EndpointAdapter` → endpoint → SOAP response**.
2. Phân biệt `WebServiceMessage`, `MessageContext`, `EndpointInvocationChain`, `EndpointMapping`, `EndpointAdapter`, `EndpointInterceptor` và `EndpointExceptionResolver`.
3. Chọn chiến lược định tuyến dựa trên **QName của payload root**, **SOAPAction**, hoặc **WS-Addressing Action** theo hợp đồng.
4. Phân tích thứ tự lựa chọn mapping và điều gì xảy ra khi không tìm được endpoint hoặc adapter phù hợp.
5. Hiểu callback interceptor trước/sau endpoint, fault path và sự khác biệt giữa xác thực cấu trúc XML với bảo mật SOAP.
6. Thiết kế ca kiểm thử xác minh endpoint được chọn, payload JAXB được giải mã, response/fault phù hợp XSD/WSDL và yêu cầu tương thích.

## 1. Tình huống xuyên suốt: tra cứu đơn hàng

Một ứng dụng đối tác cần gọi thao tác `GetOrder`. Hợp đồng XSD có hai global elements:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
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
        <xs:element name="state" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

Ví dụ HTTP + SOAP 1.1 request:

~~~http
POST /ws HTTP/1.1
Host: localhost:8080
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1:GetOrder"
~~~

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soap:Header/>
  <soap:Body>
    <o:GetOrderRequest>
      <o:orderId>ORD-42</o:orderId>
    </o:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Có ít nhất **hai thông tin có thể dùng để định tuyến**:

- QName của phần tử gốc trong SOAP Body: `{urn:example:orders:v1}GetOrderRequest`.
- Giá trị SOAPAction ở lớp SOAP/HTTP: `urn:example:orders:v1:GetOrder`.

Hai thông tin này **không phải cùng một thứ**. Phần tử payload do XSD định nghĩa; SOAPAction là metadata giao thức có thể được khai báo trong WSDL binding. Một ứng dụng có thể định tuyến theo một trong hai cách, tùy annotation và mapping đã đăng ký.

Phản hồi thành công theo hợp đồng:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soap:Body>
    <o:GetOrderResponse>
      <o:orderId>ORD-42</o:orderId>
      <o:state>CREATED</o:state>
    </o:GetOrderResponse>
  </soap:Body>
</soap:Envelope>
~~~

`MessageDispatcher` không tự quyết định `CREATED` là đúng hay không: nghiệp vụ quyết định nội dung; dispatcher chịu trách nhiệm **đưa request tới thành phần có khả năng xử lý và vận chuyển phản hồi qua hạ tầng SOAP**.

## 2. Bản đồ các thành phần xử lý

Hãy phân biệt các tầng ngay từ đầu.

| Thành phần | Trách nhiệm | Cần nhớ |
| --- | --- | --- |
| `MessageDispatcherServlet` | Nhận HTTP trong ứng dụng servlet, tích hợp hạ tầng Spring-WS, chuyển SOAP request tới message receiver/dispatcher | URL `/ws` không phải tên operation |
| `WebServiceMessage` | Abstraction cho một thông điệp web service, với payload và thành phần giao thức | Có thể đại diện SOAP message |
| `MessageContext` | Giữ request, response và trạng thái liên quan trong một lượt xử lý | Được truyền xuyên suốt dispatcher/interceptor |
| **`MessageDispatcher`** | Điều phối tìm endpoint, adapter, interceptor và xử lý exception | Không chứa logic nghiệp vụ đơn hàng |
| `EndpointMapping` | Kiểm tra request để xác định endpoint | Có thể dùng QName, SOAPAction, WS-Addressing |
| `EndpointInvocationChain` | Bao gồm endpoint đã chọn và danh sách interceptors gắn với tuyến | Kết quả được mapping trả về |
| `EndpointInterceptor` | Xử lý trước/sau endpoint, lỗi và cleanup theo vòng đời | Validation, logging, WS-Security có thể được tích hợp tại đây |
| `EndpointAdapter` | Biết cách gọi đối tượng/phương thức endpoint đã chọn | Đọc tham số và ghi kết quả qua các resolver phù hợp |
| `@Endpoint` và method xử lý | Điều phối nghiệp vụ, tạo response/fault theo contract | Không nên tự điều khiển HTTP servlet |
| `EndpointExceptionResolver` | Chuyển một số exception thành response lỗi phù hợp | Có thể tạo SOAP Fault theo cấu hình |

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A["HTTP POST /ws"] --> B["MessageDispatcherServlet<br/>Đọc SOAP từ transport"]
    B --> C["MessageContext<br/>request / response"]
    C --> D["MessageDispatcher"]
    D --> E["EndpointMapping<br/>tìm endpoint"]
    E --> F{"Có mapping?"}
    F -- "Không" --> X["Không tìm thấy endpoint<br/>đi vào nhánh lỗi"]
    F -- "Có" --> G["EndpointInvocationChain<br/>endpoint + interceptors"]
    G --> H["handleRequest"]
    H --> I{"Cho phép tiếp tục?"}
    I -- "Không" --> Z["Dừng chuỗi, xử lý response/fault theo cấu hình"]
    I -- "Có" --> J["EndpointAdapter<br/>giải tham số / gọi method"]
    J --> K["Endpoint + business service"]
    K --> L["Response XML hoặc Exception"]
    L --> M["handleResponse / handleFault<br/>afterCompletion"]
    M --> N["SOAP response qua transport"]
    X --> N
    Z --> N
~~~

Đây là **sơ đồ định hướng**, không phải một cam kết rằng mọi nhánh lỗi luôn tạo SOAP Fault hoặc luôn có HTTP status giống nhau. Hành vi chính xác phụ thuộc exception resolver, SOAP version, adapter, cấu hình servlet và interceptor.

### 2.1. Servlet và Dispatcher không phải cùng một lớp

`MessageDispatcherServlet` là cổng vào thường dùng trong ứng dụng servlet. Nó kết nối HTTP transport với hạ tầng xử lý message, đồng thời có thể phục vụ tài liệu WSDL/XSD theo các bean đã cấu hình.

`MessageDispatcher` thực hiện **message dispatching**: nó nhận `MessageContext`, duyệt các mapping, chọn adapter và điều phối endpoint. Về thiết kế, việc định tuyến nghiệp vụ không nên phụ thuộc trực tiếp vào URL REST-style. Chẳng hạn `GET /ws/orders.wsdl` là truy vấn tài liệu hợp đồng, còn `POST /ws` là truyền SOAP request, có thể chứa nhiều operation khác nhau.

Trong một ứng dụng Spring Boot, servlet có thể được cấu hình tự động hoặc đăng ký rõ ràng. Cần kiểm tra cách ứng dụng hiện tại tạo servlet để tránh mapping trùng/nhầm path.

## 3. `MessageDispatcher` điều phối ra sao?

Spring-WS cho phép đăng ký nhiều implementation của ba giao diện chiến lược chính:

1. **`EndpointMapping`**: từ `MessageContext` suy ra endpoint nào phù hợp.
2. **`EndpointAdapter`**: với endpoint đã chọn, tìm cơ chế có thể **invoke** nó.
3. **`EndpointExceptionResolver`**: nếu quá trình xử lý ném exception, thử chuyển exception thành response lỗi.

### 3.1. Bước 1: tìm endpoint với `EndpointMapping`

`MessageDispatcher` thử các mapping đã đăng ký **theo thứ tự**, đến khi một mapping trả về `EndpointInvocationChain`. Mapping này có thể chứa interceptor và một endpoint object, trong đó endpoint có thể là biểu diễn của method đã chọn.

Nếu không mapping nào khớp, dispatcher không thể tự suy ra method Java chỉ từ tên service trong WSDL. Trong API Spring-WS, quá trình dispatch có thể dẫn tới `NoEndpointFoundException`. Response thực tế ở client phụ thuộc cấu hình xử lý lỗi/transport; không nên mặc định luôn là một SOAP Fault chuẩn với detail cụ thể.

**Một điều quan trọng về bảo mật:** phần lớn interceptor gắn với `EndpointInvocationChain` chỉ chạy **sau khi đã tìm được mapping**. Nếu không tìm thấy endpoint, không thể giả định mọi interceptor đã chạy. Những chính sách cần bảo vệ toàn bộ HTTP traffic hoặc từ chối request trước bước ánh xạ còn phụ thuộc lớp gateway, servlet filter hoặc các thành phần thích hợp khác.

### 3.2. Bước 2: chọn `EndpointAdapter`

Khi có endpoint, dispatcher cần một adapter hiểu **cách gọi endpoint đó**. Spring-WS có nhiều kiểu endpoint: method annotation, payload-oriented, message-oriented, và có thể có adapter tùy biến. Adapter sẽ xét nó có hỗ trợ endpoint object hay không rồi thực hiện invocation.

Đối với các method `@Endpoint` có `@RequestPayload` / `@ResponsePayload`, hỗ trợ thông thường đi qua `DefaultMethodEndpointAdapter` với các **method argument resolvers** và **method return value handlers** thích hợp. Chúng có thể hỗ trợ XML `Source`, DOM, JAXB type, `JAXBElement` và những biểu diễn khác tùy cấu hình/binding.

Điểm cần phân biệt:

- Mapping trả lời **“gọi method nào?”**.
- Adapter trả lời **“làm cách nào để truyền tham số và nhận kết quả của method?”**.
- JAXB/OXM trả lời **“giải XML thành object Java và tạo XML từ object thế nào?”**.
- Business service trả lời **“đơn hàng này có tồn tại và trạng thái gì?”**.

Một request có thể **tìm đúng endpoint** nhưng vẫn **không gọi được method** nếu chữ ký tham số/return type không được adapter và resolver hiện có hỗ trợ. Ngược lại, JAXB marshal một đối tượng thành công không chứng minh payload QName sẽ khớp mapping.

### 3.3. Bước 3: interceptor, response và lỗi

Mapping thường trả một invocation chain với interceptors. Các interceptor hợp lệ có thể kiểm tra schema, metadata, bảo mật thông điệp, logging/tracing hoặc thay đổi thông điệp theo chính sách.

Nếu endpoint chạy thành công, adapter chuyển kết quả thành payload response và dispatcher điều phối nhánh xử lý response. Nếu ném exception, hệ thống thử các `EndpointExceptionResolver` đã đăng ký; khi phù hợp chúng có thể chuyển lỗi thành SOAP Fault. Không phải mọi exception Java đều tự ánh xạ thành fault nghiệp vụ như mong muốn.

## 4. Chiến lược 1: định tuyến theo QName của payload root

Đây là chiến lược thường rõ ràng nhất cho SOAP **document/literal contract-first**.

`PayloadRootAnnotationMethodEndpointMapping` dùng annotation `@PayloadRoot(namespace, localPart)` để tìm method phù hợp với **QName của phần tử gốc trong SOAP Body**.

### 4.1. Endpoint minh họa

Giả sử XJC đã sinh `GetOrderRequest` và `GetOrderResponse`, cả hai là JAXB root types được cấu hình marshaller phù hợp:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrdersEndpoint {

    private static final String NS = "urn:example:orders:v1";
    private final OrderService service;

    public OrdersEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        OrderRecord record = service.requireById(request.getOrderId());
        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(record.id());
        response.setState(record.state());
        return response;
    }
}
~~~

`OrderService` và `OrderRecord` là các kiểu nghiệp vụ do ứng dụng tự định nghĩa. Đoạn Java giả định JAXB generator tạo object root tương ứng; nếu XSD tách global element khỏi named type, có thể cần `JAXBElement<T>` qua `ObjectFactory` hoặc chữ ký khác. Không nên sửa QName trong `@PayloadRoot` cho vừa tên class Java nếu điều đó làm sai hợp đồng XSD.

### 4.2. Vì sao namespace là điều kiện bắt buộc?

Hai Body này có vẻ tương tự nhưng **khác QName**:

~~~xml
<!-- Khớp annotation: đúng namespace URI. -->
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-42</ord:orderId>
</ord:GetOrderRequest>
~~~

~~~xml
<!-- Không khớp annotation NS=v1: URI là v2. -->
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v2">
  <ord:orderId>ORD-42</ord:orderId>
</ord:GetOrderRequest>
~~~

Ngược lại, thay prefix `ord` bằng `x` mà vẫn trỏ tới `urn:example:orders:v1` **không làm thay đổi QName**. Cùng quy tắc đó áp dụng khi XML dùng default namespace.

Đừng dùng `local-name()` rộng để bỏ qua namespace như một cách sửa lỗi định tuyến. Việc bỏ qua namespace có thể khiến cùng local name của phiên bản hợp đồng khác bị xử lý nhầm, đặc biệt nguy hiểm khi thông điệp dùng chữ ký số.

### 4.3. Khi nào nên dùng payload root?

Phù hợp khi:

- XSD/WSDL quy định rõ một phần tử gốc cho mỗi thông điệp request.
- Contract cần hoạt động giữa các client Java, .NET và các nền tảng khác.
- Nhóm dự án muốn định tuyến không phụ thuộc vào cách client viết SOAPAction transport header.
- Phần tử XML gốc có namespace/version rõ ràng.

Cũng cần nhớ: một phương thức được chọn bằng QName **không tự bảo đảm** toàn bộ payload hợp lệ theo XSD. Field bắt buộc, thứ tự `xs:sequence` và các ràng buộc khác phải được kiểm tra qua validation nếu chính sách yêu cầu.

## 5. Chiến lược 2: định tuyến bằng SOAPAction

Với SOAP 1.1 trên HTTP, một request có thể chứa header `SOAPAction`. Trong Spring-WS, `SoapActionAnnotationMethodEndpointMapping` dùng `@SoapAction` trên method để ánh xạ action tới endpoint.

Ví dụ **phương án thay thế** cho method xử lý cùng request `GetOrder`:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.server.endpoint.annotation.SoapAction;

@Endpoint
public class OrderActionEndpoint {

    private final OrderService service;

    public OrderActionEndpoint(OrderService service) {
        this.service = service;
    }

    @SoapAction("urn:example:orders:v1:GetOrder")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        OrderRecord record = service.requireById(request.getOrderId());
        GetOrderResponse result = new GetOrderResponse();
        result.setOrderId(record.id());
        result.setState(record.state());
        return result;
    }
}
~~~

Đây là **biến thể để học mapping**: không đồng thời đăng ký nó cùng endpoint ở mục 4 với cùng ý định xử lý mà chưa quyết định thứ tự và chính sách định tuyến. Dù `@SoapAction` chọn method, adapter/JAXB vẫn phải giải được payload `GetOrderRequest`, và XSD validation vẫn phải bảo đảm cấu trúc dữ liệu hợp lệ.

### 5.1. WSDL binding và SOAPAction

WSDL 1.1 có thể khai báo action trên binding:

~~~xml
<wsdl:operation name="GetOrder">
  <soap:operation
      soapAction="urn:example:orders:v1:GetOrder"/>
  <wsdl:input>
    <soap:body use="literal"/>
  </wsdl:input>
  <wsdl:output>
    <soap:body use="literal"/>
  </wsdl:output>
</wsdl:operation>
~~~

Đây là đoạn **rút gọn**, giả định có namespace `wsdl` và `soap` đúng cùng các định nghĩa WSDL còn lại. Khai báo `soapAction` cho client biết action theo binding; nó **không tự tạo annotation `@SoapAction`** trong server. Muốn chọn endpoint bằng action, phải có mapping và annotation/configuration phù hợp.

### 5.2. Khi nào SOAPAction có ưu và nhược điểm?

| Ưu điểm | Điểm cần kiểm soát |
| --- | --- |
| Hợp với đối tác yêu cầu SOAPAction cố định | Client/gateway có thể bỏ hoặc gửi action khác |
| Có thể giúp phân biệt những thao tác có cấu trúc payload giống nhau | Action phải thống nhất giữa WSDL, client và server |
| Không cần dựa duy nhất vào QName để chọn method | Payload vẫn phải được kiểm tra schema và security |
| Giúp kiểm thử binding/action ở mức protocol | SOAP 1.1/1.2 biểu diễn action ở HTTP khác nhau |

**SOAPAction không phải bằng chứng xác thực**. Client có thể tự đặt header; việc action khớp không cho phép bỏ qua quyền truy cập, chữ ký WS-Security hay kiểm tra payload.

## 6. Chiến lược 3: WS-Addressing Action

WS-Addressing đưa metadata định tuyến vào **SOAP Header**, chẳng hạn `wsa:Action`, `wsa:To`, `wsa:MessageID` và `wsa:ReplyTo`. Đây là lớp thông tin khác với HTTP SOAPAction.

Trong Spring-WS có `AnnotationActionEndpointMapping` với annotation `@Action` từ package WS-Addressing để ánh xạ method:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.addressing.server.annotation.Action;

@Endpoint
public class AddressedOrdersEndpoint {

    private final OrderService service;

    public AddressedOrdersEndpoint(OrderService service) {
        this.service = service;
    }

    @Action("urn:example:orders:v1:GetOrder")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        OrderRecord record = service.requireById(request.getOrderId());
        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(record.id());
        response.setState(record.state());
        return response;
    }
}
~~~

Đây cũng là một **phương án định tuyến thay thế** cho thao tác `GetOrder`. Để chạy thực tế, cần bật/cấu hình phần WS-Addressing tương thích và bảo đảm đối tác truyền Header theo đúng phiên bản/chính sách đã thống nhất.

Ví dụ SOAP Header:

~~~xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Action>urn:example:orders:v1:GetOrder</wsa:Action>
  <wsa:MessageID>urn:uuid:12345678-1234-1234-1234-1234567890ab</wsa:MessageID>
</soap:Header>
~~~

Đây là **fragment**, không phải thông điệp hoàn chỉnh. WS-Addressing có các yêu cầu/semantics khác ngoài hai header minh họa; cấu hình và interoperability test phải dựa trên phiên bản tiêu chuẩn mà hai bên dùng.

**Đừng nhầm:**

- `@PayloadRoot` dùng QName của phần tử gốc trong **Body**.
- `@SoapAction` dùng thông tin **SOAPAction** theo binding/transport SOAP.
- `@Action` dùng **WS-Addressing Action** trong SOAP Header.

Cả ba chỉ giúp xác định nơi xử lý. Không cách nào tự xác minh chữ ký số, chứng chỉ hay quyền truy cập nghiệp vụ.

## 7. Nhiều mapping cùng tồn tại: thứ tự nào quyết định?

Một ứng dụng Spring-WS có thể đăng ký nhiều `EndpointMapping`. `MessageDispatcher` thử **theo thứ tự** và sử dụng mapping đầu tiên tìm được endpoint; vì vậy thứ tự cấu hình là một phần của hành vi thực tế.

Với `@EnableWs` trong cấu hình annotation ở Spring-WS 4.x, `WsConfigurationSupport` đăng ký các mapping phổ biến như:

| Mapping | Dữ liệu dùng để quyết định | Thứ tự bean mặc định được API mô tả |
| --- | --- | --- |
| `PayloadRootAnnotationMethodEndpointMapping` | QName của payload root | 0 |
| `SoapActionAnnotationMethodEndpointMapping` | SOAPAction | 1 |
| `AnnotationActionEndpointMapping` | WS-Addressing Action | 2 |

Các giá trị trên mô tả cấu hình mặc định của `WsConfigurationSupport` ở nhánh Spring-WS 4.x được tham khảo. Ứng dụng có thể có mapping tùy chỉnh, các bean `Ordered` khác hoặc cấu hình ghi đè; **không dựa vào bảng như một định luật bất biến**.

### 7.1. Ví dụ mâu thuẫn giữa action và payload

Giả sử SOAP Body mang:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-42</ord:orderId>
</ord:GetOrderRequest>
~~~

nhưng SOAPAction là:

~~~text
urn:example:orders:v1:CancelOrder
~~~

Nếu mapping dựa trên payload root đứng trước và có method `GetOrderRequest`, nó có thể chọn endpoint `GetOrder`. Nếu ứng dụng dùng action mapping hoặc đã thay đổi thứ tự, kết quả có thể khác. **Không nên dựa vào sự mâu thuẫn này để phân quyền hoặc chống giả mạo thông điệp.**

Quy tắc triển khai nên là: contract quy định action, payload QName và operation nhất quán; validation/security có thể từ chối request mâu thuẫn theo chính sách. Hãy kiểm thử trường hợp này vì một số client được sinh từ WSDL có thể xử lý SOAPAction khác nhau.

### 7.2. `defaultEndpoint` có phải giải pháp cho mọi lỗi?

Các implementation từ `AbstractEndpointMapping` có thể cho phép cấu hình `defaultEndpoint` để dùng khi không tìm được mapping cụ thể. Đây là cơ chế fallback, phù hợp một số trường hợp đặc biệt, nhưng có các hệ quả:

- Request sai QName có thể bị chuyển đến một endpoint tổng quát, che mất lỗi hợp đồng.
- Một catch-all endpoint có thể vô tình xử lý thông điệp không mong đợi.
- Cần bảo đảm fallback tuân thủ validation, authorization và chính sách SOAP Fault rõ ràng.

Với dịch vụ contract-first có tập operation cố định, thường tốt hơn nếu **request không khớp được từ chối rõ ràng** thay vì làm cho mọi request đều rơi vào một endpoint mặc định.

### 7.3. Mapping tùy chỉnh

Spring-WS cho phép viết `EndpointMapping` riêng khi phải chọn endpoint theo metadata đặc thù (ví dụ một Header nghiệp vụ được xác thực). Khi đó cần xác định:

1. Cấu trúc và độ tin cậy của header dùng để định tuyến.
2. Thứ tự mapping so với các mapping sẵn có.
3. Endpoint object và interceptor chain trả về có hợp lệ không.
4. Adapter có hỗ trợ kiểu endpoint đó không.
5. Cách phản hồi khi không có mapping, khi mâu thuẫn hoặc khi thông điệp giả mạo.

Chỉ xây custom mapping khi hợp đồng thật sự yêu cầu. Một mapping tự viết dựa trên XPath rộng như `//*[local-name()='GetOrderRequest']` có thể chọn sai phần tử, sai namespace hoặc bị lợi dụng trong tình huống XML signature wrapping.

## 8. `EndpointAdapter`: khâu thường bị bỏ sót khi gỡ lỗi

Hai phương thức endpoint có cùng annotation định tuyến nhưng tham số khác nhau có thể yêu cầu resolver/adapter khác nhau:

~~~java
// Ví dụ 1: Spring-WS + JAXB binding phù hợp.
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
@ResponsePayload
public GetOrderResponse handle(
        @RequestPayload GetOrderRequest request) {
    // ...
}
~~~

~~~java
// Ví dụ 2: làm việc trực tiếp với XML Source.
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
@ResponsePayload
public Source handleRaw(@RequestPayload Source payload) {
    // ...
}
~~~

**Không khai báo đồng thời hai method trên** với cùng QName trong một cấu hình mapping, vì đó là xung đột định tuyến. Chúng minh họa hai kiểu chữ ký khác nhau.

`DefaultMethodEndpointAdapter` kết hợp các **argument resolvers** và **return value handlers**. Khi resolver phù hợp tồn tại, nó có thể chuyển payload XML sang tham số Java như `Source`, DOM hoặc JAXB; khi không phù hợp, invocation không thể thực hiện như dự kiến.

Trong contract-first:

- Nếu XSD khai báo **global element dùng anonymous complex type**, XJC có thể sinh class có `@XmlRootElement` để dùng trực tiếp.
- Nếu XSD có **named complex type** và global element tham chiếu type đó, JAXB có thể dùng `JAXBElement<T>` cùng `ObjectFactory`; chữ ký method cần tương thích.
- `Jaxb2Marshaller` có thể được sử dụng trong client/OXM. Cơ chế method adapter trên server và các converter/resolver hiện có phải hỗ trợ model được sử dụng; đừng cho rằng chỉ tạo một bean marshaller là mọi chữ ký endpoint đều được giải tự động trong mọi cấu hình.

### 8.1. Luồng giải tham số và viết response

~~~mermaid
sequenceDiagram
    autonumber
    participant Client as SOAP client
    participant Servlet as MessageDispatcherServlet
    participant Disp as MessageDispatcher
    participant Mapping as EndpointMapping
    participant Int as Interceptors
    participant Adapter as EndpointAdapter
    participant Endpoint as GetOrderEndpoint
    participant Svc as OrderService

    Client->>Servlet: HTTP POST SOAP Envelope
    Servlet->>Disp: MessageContext
    Disp->>Mapping: Tìm endpoint
    Mapping-->>Disp: InvocationChain
    Disp->>Int: handleRequest
    Int-->>Disp: Tiếp tục
    Disp->>Adapter: Chọn adapter và invoke endpoint
    Adapter->>Adapter: Đọc payload / resolve Java argument
    Adapter->>Endpoint: getOrder(request)
    Endpoint->>Svc: requireById("ORD-42")
    Svc-->>Endpoint: OrderRecord
    Endpoint-->>Adapter: GetOrderResponse
    Adapter->>Adapter: Chuyển return value thành XML payload
    Adapter-->>Disp: Response đã tạo
    Disp->>Int: handleResponse, afterCompletion
    Disp-->>Servlet: MessageContext với response
    Servlet-->>Client: HTTP SOAP response
~~~

Thứ tự trình bày là luồng **thành công điển hình**. Exception, interceptor trả `false` hoặc SOAP Fault sẽ tạo nhánh khác.

## 9. Vòng đời `EndpointInterceptor`

`EndpointInterceptor` có bốn callback cơ bản:

| Callback | Thời điểm | Chức năng phổ biến |
| --- | --- | --- |
| `handleRequest(context, endpoint)` | Sau khi mapping tìm endpoint, trước adapter gọi endpoint | XSD validation, kiểm tra SOAP header, xác thực WS-Security |
| `handleResponse(context, endpoint)` | Sau khi endpoint được gọi và có response bình thường | Ghi log/tracing, bổ sung header hợp lệ |
| `handleFault(context, endpoint)` | Nhánh response SOAP Fault | Quan sát mã lỗi, xử lý metadata lỗi |
| `afterCompletion(context, endpoint, ex)` | Sau chu trình xử lý đối với interceptor đã tham gia thành công | Cleanup/tài nguyên/trace kết thúc |

**Giá trị boolean có ý nghĩa:** `handleRequest(...)` trả `true` để tiếp tục, `false` để dừng việc gọi endpoint theo invocation chain. Tương tự, callback trên response/fault có thể dừng chuỗi xử lý tương ứng. Interceptor xử lý response/cleanup thường chạy **theo thứ tự ngược** so với chuỗi request; chỉ những interceptor đã hoàn tất `handleRequest` đúng cách mới được gọi ở các pha sau theo hợp đồng API.

### 9.1. Ví dụ interceptor theo dõi metadata

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.server.endpoint.interceptor.EndpointInterceptorAdapter;

// Minh họa ghi nhận thời gian/trace, lược bỏ logger/metrics.
public class TraceInterceptor extends EndpointInterceptorAdapter {

    @Override
    public boolean handleRequest(
            MessageContext messageContext, Object endpoint) {
        // Lấy correlation ID đáng tin theo chính sách ứng dụng.
        // Không log token hay toàn bộ payload nhạy cảm.
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext messageContext, Object endpoint) {
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext messageContext, Object endpoint) {
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext messageContext,
            Object endpoint, Exception ex) {
        // Ghi metric/trace kết thúc theo chính sách.
    }
}
~~~

Bean có thể được đăng ký qua `WsConfigurer.addInterceptors(...)`:

~~~java
@Configuration
@EnableWs
public class SoapInterceptorsConfig implements WsConfigurer {

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(new TraceInterceptor());
    }
}
~~~

Ví dụ trên minh họa cách kết nối interceptor trong cấu hình annotation; các import `WsConfigurer`/`EnableWs`/`Configuration`/`List` cần bổ sung tương ứng nếu tách thành class độc lập. Trong dự án thật, cân nhắc quản lý interceptor là Spring bean để inject dependency.

### 9.2. Validation và bảo mật nằm ở đâu?

- **`PayloadValidatingInterceptor`** có thể kiểm tra payload theo XSD ở request và/hoặc response. Nó phát hiện XML thiếu trường, sai kiểu, sai namespace hay thứ tự `xs:sequence` theo schema, khi đã bật validation.
- **`Wss4jSecurityInterceptor`** có thể thực thi chính sách WS-Security phù hợp như xác minh signature, timestamp/token và xử lý bảo mật thông điệp.
- **TLS/mTLS** hoạt động ở kênh kết nối, thường do container/gateway/HTTP transport quản lý; đây không phải chức năng tự động của `EndpointAdapter`.
- **Authorization** phải gắn với danh tính được xác thực và quy tắc nghiệp vụ; không tin một `buyerId` hay `role` được gửi tùy ý trong SOAP Body.

Một thông điệp có XML hợp XSD chưa chắc chữ ký hợp lệ. Ngược lại, một thông điệp đã qua xác thực ở lớp WS-Security vẫn cần validation và kiểm tra nghiệp vụ. Tùy chính sách chữ ký, phải bảo đảm **đúng phần tử đã được xác thực** cũng là phần tử endpoint xử lý.

### 9.3. Một lưu ý quan trọng về thứ tự

Một số bộ lọc bảo mật phải hoạt động **trước khi xử lý SOAP message**, trong khi `EndpointInterceptor` được gọi sau mapping. Ví dụ nếu yêu cầu chưa khớp bất kỳ endpoint nào, interceptor gắn với endpoint đó không được bảo đảm chạy. Do đó:

- Dùng TLS/gateway/filter cho chính sách ở ranh giới HTTP/transport.
- Dùng WS-Security interceptor để xác minh nội dung theo chính sách ở đường xử lý SOAP đã được định tuyến.
- Không coi một interceptor endpoint duy nhất là cơ chế bảo vệ toàn bộ URL, kể cả tài nguyên WSDL/XSD và các request chưa map.

## 10. Xử lý exception và SOAP Fault

`EndpointExceptionResolver` cho phép Spring-WS chuyển exception sang response lỗi, thường là SOAP Fault. Các implementation/cách cấu hình như `SoapFaultMappingExceptionResolver` có thể ánh xạ loại exception sang fault code/reason phù hợp.

Ví dụ, nghiệp vụ tra cứu đơn hàng:

~~~java
public OrderRecord requireById(String orderId) {
    return repository.findById(orderId)
        .orElseThrow(() ->
            new OrderNotFoundException("Order not found"));
}
~~~

`repository` và `OrderNotFoundException` là mã nghiệp vụ minh họa. Nếu không cấu hình fault mapping, **không mặc định** lỗi này tự trở thành fault với mã đối tác đã thống nhất.

Một SOAP 1.1 Fault minh họa:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Order not found</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Cấu trúc SOAP Fault 1.2 khác SOAP 1.1 (và các mã như `Sender`/`Receiver` khác `Client`/`Server`). Nếu đối tác yêu cầu fault detail có mã lỗi máy đọc được, hãy định nghĩa cấu trúc schema/WSDL phù hợp và triển khai resolver/customization tương ứng.

### 10.1. Những nhánh lỗi cần phân biệt

| Giai đoạn | Lỗi điển hình | Điểm kiểm tra |
| --- | --- | --- |
| Transport/parse | HTTP path không đúng, SOAP version/content type không tương thích, XML không well-formed | Servlet, message factory, transport |
| Mapping | Body root QName hoặc SOAPAction không khớp | Endpoint mappings, order, annotations |
| Adapter | Method parameter/return type không được hỗ trợ | Adapter và argument/return resolver |
| Validation | XML vi phạm XSD | `PayloadValidatingInterceptor` hoặc validator |
| Security | Chữ ký sai, timestamp hết hạn, token/chứng chỉ không hợp lệ | WS-Security interceptor, TLS/gateway |
| Business | Order không tồn tại, không đủ quyền, xung đột trạng thái | Service và exception resolver |
| Response serialization | JAXB root thiếu, sai namespace, response vi phạm XSD | JAXB/OXM, response validation |

Không nên gộp tất cả thành “SOAP trả 500”: lỗi transport, lỗi SOAP Fault và lỗi nghiệp vụ có thể tạo những hành vi khác nhau. Client phải phân biệt **response thành công**, **SOAP Fault** và **lỗi mạng/transport**.

## 11. Quan hệ với XSD, WSDL, JAXB và client

Một ứng dụng contract-first có thể công bố WSDL cho operation `GetOrder`, với input/output trỏ tới global elements `GetOrderRequest` và `GetOrderResponse`. Những thông tin này giúp client biết phải tạo XML nào, nhưng **WSDL không phải bảng mapping runtime giữa XML và Java method**.

| Thành phần | Quyết định | Có quyết định endpoint method không? |
| --- | --- | --- |
| XSD | QName, kiểu và cấu trúc payload | Gián tiếp: cung cấp QName cho mapping |
| WSDL | Operation, binding, SOAPAction và service address | Gián tiếp: là hợp đồng để client gửi đúng |
| JAXB/XJC | XML ↔ object Java | Không, chủ yếu xử lý tham số/kết quả |
| `MessageDispatcherServlet` | Nhận request qua HTTP path | Chọn cổng nhận, không chọn nghiệp vụ theo QName |
| `EndpointMapping` | Endpoint nào khớp message | **Có** |
| `EndpointAdapter` | Gọi endpoint đã được mapping chọn | Không chọn operation; thực hiện lời gọi |
| `EndpointInterceptor` | Kiểm tra/quan sát/sửa thông điệp theo chuỗi | Có thể chặn xử lý, không thay thế mapping |
| `EndpointExceptionResolver` | Chuyển exception thành phản hồi lỗi | Không chọn endpoint ban đầu |

`WebServiceTemplate` ở phía SOAP client sử dụng marshaller/unmarshaller để gửi/nhận payload, có thể kèm `SoapActionCallback` khi hợp đồng SOAP 1.1 yêu cầu action. Một client gửi `GetOrderRequest` theo đúng XSD nhưng dùng wrong namespace hoặc action trái chính sách có thể không được định tuyến/được chấp nhận.

WSDL được tải bằng HTTP GET và SOAP nghiệp vụ thường được gửi bằng HTTP POST; cả hai có thể đi qua cùng servlet path nhưng theo luồng xử lý khác nhau.

## 12. Kiểm thử kiến trúc dispatching

Để biết hệ thống thật sự xử lý đúng, cần kiểm tra **đường đi**, không chỉ gọi thẳng method Java.

### 12.1. Ma trận kiểm thử

| Ca kiểm thử | Kỳ vọng | Điều xác minh |
| --- | --- | --- |
| `GetOrderRequest` đúng namespace và cấu trúc | Mapping theo `@PayloadRoot` chọn `getOrder` | QName và annotation |
| Đổi prefix `o` thành `ord`, giữ URI | Vẫn chọn cùng endpoint | QName không phụ thuộc prefix |
| Đổi namespace v1 thành v2 | Mapping v1 không nhận yêu cầu này | Version theo QName |
| Sai local name `GetOrdersRequest` | Không khớp payload mapping v1 | LocalPart |
| Đúng payload, thiếu/sai SOAPAction | Hành vi phụ thuộc mapping và chính sách đã cấu hình | Phân biệt payload vs action |
| Payload `GetOrderRequest` nhưng SOAPAction `CancelOrder` | Bị kiểm tra theo chính sách; test thứ tự mapping | Xung đột metadata |
| SOAPAction đúng nhưng payload sai XSD | Có thể tìm endpoint bằng action; validator phải từ chối khi bật | Routing khác validation |
| WS-Addressing `wsa:Action` đúng, SOAPAction khác | Hành vi theo mapping order/chính sách | Phân biệt hai action |
| Method dùng JAXB type không được resolver hỗ trợ | Không invoke thành công dù đã mapping | EndpointAdapter |
| Request thiếu `orderId` | Bị từ chối khi XSD validation bật | Interceptor/schema |
| Chữ ký WS-Security sai | Từ chối trước nghiệp vụ theo policy | Security interceptor |
| Order không có trong database | SOAP Fault nghiệp vụ đúng mã | Exception resolver |
| Response có sai root QName | Kiểm thử wire/schema phát hiện | Response serialization |
| Không mapping nào tìm được endpoint | Lỗi theo chính sách, không gọi business service | NoEndpointFound/transport |
| Hai mapping cùng có khả năng khớp | Kết quả theo thứ tự cấu hình đã chủ đích | Mapping order |
| Gọi SOAP client từ .NET/Java khác | XML, SOAPAction/binding, fault tương thích | Interoperability |

### 12.2. Công cụ test phù hợp

- **`MockWebServiceClient`:** gửi XML qua hạ tầng Spring-WS test và xác minh response/fault/dispatch phía server.
- **`MockWebServiceServer`:** kiểm tra `WebServiceTemplate` gửi request, action và nhận response/fault phía client.
- **XSD validation:** kiểm tra QName, field bắt buộc, kiểu, thứ tự và cardinality theo contract.
- **Integration test thực:** gửi SOAP qua URL servlet, xác nhận content type, SOAP version, TLS, WSDL address, interceptor và logging theo môi trường.

Trong unit test gọi trực tiếp `ordersEndpoint.getOrder(request)`, bạn đang kiểm thử logic method, **không kiểm tra `EndpointMapping`, adapter, interceptor hay SOAP Fault**. Ít nhất một nhóm integration test phải đi qua dispatching thật.

### 12.3. Ví dụ khung test với `MockWebServiceClient`

Giả sử bean Spring-WS và `OrdersEndpoint` đã được cấu hình, XML request/response fixtures đã có:

~~~java
// Khung minh họa, cần import JUnit/Spring-WS Test và fixture cụ thể.
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

Source request = new StreamSource(
    new StringReader(getOrderRequestXml));

Source response = new StreamSource(
    new StringReader(getOrderResponseXml));

client.sendRequest(withPayload(request))
      .andExpect(payload(response));
~~~

Các static methods `withPayload` và `payload` thuộc nhóm request/response creators/matchers của Spring-WS Test. Test này mới xác nhận payload mong đợi; cần thêm assertion kiểm tra fault path, interceptor, namespace, SOAP header và routing khi bài toán có những chính sách đó.

## 13. Chẩn đoán lỗi theo trình tự

| Triệu chứng | Điểm nghi vấn | Hành động xác minh |
| --- | --- | --- |
| HTTP POST trả 404 trước khi đến SOAP | Sai servlet mapping/path hoặc gateway | Kiểm tra `MessageDispatcherServlet` và URL |
| Endpoint không được gọi dù WSDL có operation | QName hoặc SOAPAction không khớp mapping | Xem Body root, namespace URI, action, annotation |
| Đúng QName nhưng vẫn gọi method khác | Nhiều mappings và thứ tự ưu tiên | Liệt kê mapping thực tế; review `Ordered` |
| `@PayloadRoot` method không xử lý được JAXB type | Adapter/resolver/JAXB root configuration | Kiểm tra signature, `@XmlRootElement`/`JAXBElement` |
| Request đúng XML nhưng bị fault validation | XSD triển khai khác version, field sai namespace/thứ tự | Validate XML với schema đang chạy |
| Security interceptor không chạy ở request lạ | Chưa tìm được endpoint chain hoặc scope interceptor khác | Kiểm tra mapping và ranh giới bảo mật |
| SOAPAction trong WSDL khác header client gửi | Binding/client callback sai | So `soap:operation/@soapAction` và HTTP |
| Client dùng SOAP 1.2, server dùng SOAP 1.1 | Envelope namespace và media type khác | Kiểm tra SOAP factory/binding |
| Response ra XML nhưng client không giải được | Sai root QName, type, namespace, JAXB binding | So XML wire với XSD/WSDL |
| SOAP Fault thiếu mã nghiệp vụ | Exception resolver chưa đúng hợp đồng | Kiểm tra fault mapping/detail |
| Chạy trong IDE được nhưng deploy lỗi mapping | Bean scanning, servlet context hoặc config khác | Kiểm tra Spring context và packaged app |
| Có lỗi chứng chỉ, nhưng method không chạy | TLS handshake thất bại trước dispatch | Kiểm tra truststore/hostname/mTLS |

Một quy trình gỡ lỗi hiệu quả:

~~~mermaid
flowchart TD
    A["HTTP request có tới đúng servlet /ws?"] --> B{"Có?"}
    B -- "Không" --> C["Sửa URL, servlet mapping, gateway"]
    B -- "Có" --> D["SOAP version và XML parse hợp lệ?"]
    D --> E{"Hợp lệ?"}
    E -- "Không" --> F["Sửa Envelope, content type, parser"]
    E -- "Có" --> G["Xác định Body QName + SOAPAction + wsa:Action"]
    G --> H["Mapping nào được thử trước và khớp?"]
    H --> I{"Có endpoint?"}
    I -- "Không" --> J["Sửa contract/annotation/mapping order"]
    I -- "Có" --> K["Adapter/resolver có gọi được method?"]
    K --> L["Interceptor: validation / security"]
    L --> M["Business service"]
    M --> N["Response XML hoặc SOAP Fault"]
    N --> O["Kiểm tra XML wire và client compatibility"]
~~~

Đường đi này không cố định về thứ tự nội bộ của mọi interceptor; nó là checklist theo trách nhiệm các lớp.

## 14. Checklist thiết kế cho tích hợp doanh nghiệp

Một endpoint Spring-WS chỉ được xem là ổn định khi các quyết định sau đã rõ:

1. **Hợp đồng:** XSD/WSDL thống nhất root QName, operation, SOAPAction, WS-Addressing (nếu dùng) và version namespace.
2. **Transport:** `MessageDispatcherServlet` chỉ tiếp nhận đúng URL/schema, có TLS/mTLS hoặc policy gateway phù hợp.
3. **Mapping:** xác định chiến lược chính; tránh sự mơ hồ khi nhiều annotation/mapping cùng khớp; kiểm tra order thực tế.
4. **Adapter/JAXB:** chữ ký endpoint được resolver hỗ trợ; `@XmlRootElement`/`JAXBElement` đúng theo XSD.
5. **Validation:** yêu cầu/response được xác minh schema theo mức phù hợp; logic nghiệp vụ xử lý những quy tắc ngoài XSD.
6. **Security:** WS-Security xác minh chữ ký/timestamp/token; ủy quyền không dựa trên field có thể giả mạo trong SOAP Body.
7. **Fault:** mọi nhóm lỗi chính có phản hồi và mã lỗi nhất quán; không lộ stack trace hoặc dữ liệu nhạy cảm.
8. **Testing:** có mock dispatch tests, client tests, XSD/WSDL diff, SOAP Fault và kiểm thử thực với đối tác.
9. **Observability:** log operation/QName, correlation ID, mã lỗi và latency; che credential, key và dữ liệu nhạy cảm.

### Câu hỏi tự kiểm tra

1. Vì sao `MessageDispatcherServlet` và `MessageDispatcher` không phải cùng một vai trò? HTTP POST vào `/ws` có xác định được method Java không?
2. `EndpointMapping` và `EndpointAdapter` khác nhau thế nào? Vì sao có trường hợp tìm được endpoint nhưng không thể invoke?
3. `GetOrderRequest` trong namespace v1 được gửi bằng prefix khác có ảnh hưởng `@PayloadRoot` không? Đổi URI sang v2 thì sao?
4. Khi `SOAPAction=CancelOrder` nhưng Body root là `GetOrderRequest`, kết quả phụ thuộc những yếu tố nào?
5. `@SoapAction` và `@Action` có dùng cùng metadata không? Annotation thứ hai đọc thông tin ở đâu?
6. Nếu một request không tìm được endpoint, có được khẳng định mọi `EndpointInterceptor` đều chạy không? Các lớp bảo mật nào vẫn cần ở ranh giới hệ thống?
7. Khi endpoint ném `OrderNotFoundException`, thành phần nào có thể tạo SOAP Fault? Có tự động ra đúng fault detail contract không?
8. Test gọi trực tiếp `OrdersEndpoint.getOrder(...)` bỏ qua những bước nào? Vì sao `MockWebServiceClient` hữu ích hơn cho kiểm thử dispatching?
9. Tại sao định tuyến thành công không đủ chứng minh XML hợp XSD hay chữ ký WS-Security hợp lệ?
10. Nếu WSDL chứa `GetOrder` mà endpoint không được chọn, bạn sẽ kiểm tra QName, SOAPAction, servlet mapping và adapter theo thứ tự nào?

## Tài liệu tham khảo

- [Spring Web Services Reference — Endpoint mappings và WS-Addressing](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — khái niệm invocation chain, `@PayloadRoot`, `@SoapAction` và `@Action`.
- [Spring-WS API — MessageDispatcher](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/server/MessageDispatcher.html) — các chiến lược `EndpointMapping`, `EndpointAdapter`, `EndpointExceptionResolver`.
- [Spring-WS API — WsConfigurationSupport](https://docs.spring.io/spring-ws/docs/4.0.x/api/org/springframework/ws/config/annotation/WsConfigurationSupport.html) — cấu hình các annotation method mappings và thứ tự mặc định.
- [Spring-WS API — EndpointInterceptor](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/EndpointInterceptor.html) — hợp đồng callbacks request, response, fault và afterCompletion.

**Ghi nhớ:** `MessageDispatcher` là bộ điều phối trung tâm của Spring-WS. **`EndpointMapping` chọn nơi xử lý**, **`EndpointAdapter` gọi nơi đó**, **interceptor** kiểm tra hoặc quan sát chuỗi xử lý, còn **exception resolver** hỗ trợ tạo response lỗi. Để SOAP contract-first hoạt động ổn định, phải giữ QName, SOAPAction/WS-Addressing, XSD/WSDL, JAXB, bảo mật và kiểm thử tương thích nhất quán ở cả nhánh thành công lẫn nhánh SOAP Fault.
