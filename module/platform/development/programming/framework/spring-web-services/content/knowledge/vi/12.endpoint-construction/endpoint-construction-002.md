# @RequestPayload, @ResponsePayload và chữ ký phương thức xử lý

Trong **Spring Web Services (Spring-WS)**, một SOAP endpoint không hoạt động giống REST controller thông thường. Phương thức xử lý nhận **payload XML nằm bên trong SOAP Body**, được chọn bởi cơ chế endpoint mapping và được chuyển đổi từ/đến Java nhờ endpoint adapter. Hai annotation thường xuất hiện trên chữ ký phương thức là **`@RequestPayload`** và **`@ResponsePayload`**.

Để xây dựng dịch vụ SOAP **contract-first** ổn định, cần phân biệt rõ ba câu hỏi:

1. **Method nào được gọi?** Ví dụ `@PayloadRoot` định tuyến theo QName của phần tử đầu tiên trong SOAP Body.
2. **Tham số method được lấy từ đâu?** `@RequestPayload` yêu cầu Spring-WS giải payload XML của request thành kiểu tham số Java tương thích.
3. **Kết quả trả về được đưa vào đâu?** `@ResponsePayload` cho biết giá trị trả về của method cần được ghi thành payload XML trong SOAP Body của response.

Chương **Xây dựng endpoint** này hướng dẫn cách thiết kế **chữ ký phương thức** dựa trên XSD/WSDL, chọn `JAXB` hoặc XML API, xử lý SOAP Fault và interceptor, đồng thời kiểm tra tính tương thích với SOAP client. Ví dụ minh họa sử dụng **SOAP 1.1, Spring-WS annotation endpoint và JAXB trong hệ Jakarta**; tên class chính xác và hỗ trợ tham số phụ thuộc phiên bản Spring-WS, JAXB generator và endpoint adapter thực tế.

## 1. Xác định vai trò của từng annotation

Ví dụ một endpoint có chữ ký:

~~~java
@Endpoint
public class OrdersEndpoint {

    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderResponse createOrder(
            @RequestPayload CreateOrderRequest request) {

        // Chuyển request sang nghiệp vụ và tạo response.
        return new CreateOrderResponse();
    }
}
~~~

Có bốn vai trò riêng:

| Annotation / thành phần | Đặt ở đâu? | Công việc | Không làm gì? |
| --- | --- | --- | --- |
| `@Endpoint` | Class | Đánh dấu bean là SOAP endpoint để Spring-WS phát hiện. | Không tự mở URL HTTP hay công bố WSDL. |
| `@PayloadRoot` | Method | Chọn handler bằng **QName** của payload request: namespace URI + local name. | Không serialize/unmarshal DTO; không đồng nghĩa SOAPAction hoặc URL. |
| `@RequestPayload` | Tham số method | Đánh dấu tham số lấy từ payload XML của SOAP request qua method argument resolver. | Không lấy toàn bộ HTTP body như `@RequestBody` của Spring MVC; không tự bật XSD validation. |
| `@ResponsePayload` | Method | Đánh dấu giá trị trả về cần được xử lý thành XML payload của SOAP response. | Không trực tiếp quyết định HTTP status, SOAP Fault hoặc namespace của XML root. |
| Endpoint adapter, converter/marshaller | Spring-WS runtime | Đọc/ghi XML hoặc JAXB và thực hiện method. | Không tự bảo đảm mọi ràng buộc nghiệp vụ được kiểm tra. |

**Cốt lõi:** `@PayloadRoot` là tiêu chí **chọn method**; `@RequestPayload` và `@ResponsePayload` là tiêu chí **liên kết tham số và kết quả**. Có annotation đúng nhưng thiếu adapter/marshaller hỗ trợ kiểu dữ liệu vẫn có thể không gọi được method hoặc không marshal được response.

### 1.1. Sơ đồ từ request tới response

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as MessageDispatcherServlet
    participant M as EndpointMapping
    participant I as Interceptor/Validation
    participant A as MethodEndpointAdapter
    participant E as OrdersEndpoint
    C->>S: HTTP POST + SOAP Envelope
    S->>M: Tìm QName trong SOAP Body
    M-->>S: Method có @PayloadRoot phù hợp
    S->>I: Xử lý security, validation, logging
    I->>A: Payload request hợp lệ
    A->>A: @RequestPayload → JAXB/XML argument
    A->>E: createOrder(request)
    E-->>A: CreateOrderResponse
    A->>A: @ResponsePayload → XML Body
    A-->>S: SOAP response hoặc Fault
    S-->>C: HTTP + SOAP Envelope
~~~

Thứ tự chính xác giữa mapping, interceptor, security và validation có thể phụ thuộc cấu hình/phiên bản. Sơ đồ chỉ giúp phân biệt **định tuyến**, **giải payload**, **nghiệp vụ**, **ghi phản hồi**, không phải lời cam kết rằng mọi request luôn đi qua cùng interceptor.

## 2. XSD contract-first quyết định chữ ký có ý nghĩa gì

Một schema XSD 1.0 tự chứa cho nghiệp vụ tạo đơn hàng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

  <xs:simpleType name="OrderCodeType">
    <xs:restriction base="xs:token">
      <xs:pattern value="[A-Z]{3}-[0-9]{8}-[0-9]{4}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="CreateOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="clientOrderId"
                    type="ord:OrderCodeType"/>
        <xs:element name="amount"
                    type="xs:decimal"/>
        <xs:element name="currency"
                    type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="CreateOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="status" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Ở ví dụ này, `CreateOrderRequest` và `CreateOrderResponse` là **global elements**, mỗi element chứa một **anonymous complex type**. Một JAXB generator phù hợp thường tạo lớp theo tên global element, ví dụ `CreateOrderRequest` và `CreateOrderResponse`, với metadata `@XmlRootElement`. Đây là một thiết kế giúp code mẫu dưới đây trực quan; nếu XSD thay bằng *named complex type* được tham chiếu từ element, JAXB có thể sinh lớp `...Type` và `ObjectFactory` trả `JAXBElement` thay vì cùng hình thức.

**Không tự suy Java class từ tên method**: phải sinh hoặc xác nhận class từ **XSD thực tế**. XSD quy định QName XML, thứ tự element và kiểu dữ liệu; WSDL quy định operation, message, binding và SOAP address; còn `@RequestPayload` chỉ dùng những khả năng mapping mà endpoint adapter cung cấp.

### 2.1. Payload XML được gửi trong SOAP Body

Một SOAP 1.1 request có phần Body tương ứng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header/>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
      <ord:currency>VND</ord:currency>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Phần tử đầu trong Body có QName:

~~~text
namespace URI = urn:example:orders:v1
local part    = CreateOrderRequest
QName         = {urn:example:orders:v1}CreateOrderRequest
~~~

Do đó, `@PayloadRoot(namespace="urn:example:orders:v1", localPart="CreateOrderRequest")` khớp. Prefix `ord` chỉ là cách viết XML; client có thể thay `ord` thành `o` hoặc dùng default namespace mà **không đổi QName**.

Một response hợp lệ theo schema ví dụ có dạng:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soap:Body>
    <ord:CreateOrderResponse>
      <ord:orderId>ORD-000184</ord:orderId>
      <ord:status>ACCEPTED</ord:status>
    </ord:CreateOrderResponse>
  </soap:Body>
</soap:Envelope>
~~~

Method trả về object Java không tự đặt SOAP Body element là `CreateOrderResponse`. **JAXB root metadata hoặc XML Source/Result được trả về** mới quyết định QName của payload khi serialize; `@ResponsePayload` đánh dấu việc ghi kết quả đó vào response.

## 3. Chữ ký JAXB điển hình: một request, một response

Khi đã sinh Java source từ schema ở mục 2 và đặt trong package, ví dụ `com.example.orders.contract`, mẫu endpoint hoàn chỉnh về mặt luồng có thể là:

~~~java
package com.example.orders.endpoint;

import com.example.orders.contract.CreateOrderRequest;
import com.example.orders.contract.CreateOrderResponse;
import com.example.orders.service.OrderApplicationService;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrdersEndpoint {

    private static final String NAMESPACE =
            "urn:example:orders:v1";

    private final OrderApplicationService orderService;

    public OrdersEndpoint(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(
        namespace = NAMESPACE,
        localPart = "CreateOrderRequest"
    )
    @ResponsePayload
    public CreateOrderResponse createOrder(
            @RequestPayload CreateOrderRequest request) {

        String orderId = orderService.createOrder(
                request.getClientOrderId(),
                request.getAmount(),
                request.getCurrency());

        CreateOrderResponse response = new CreateOrderResponse();
        response.setOrderId(orderId);
        response.setStatus("ACCEPTED");
        return response;
    }
}
~~~

Giả định: `OrderApplicationService` là một bean nghiệp vụ do dự án tự cung cấp (không phải API Spring-WS), với method trả về `String`; các getter/setter của JAXB classes khớp schema/generator; runtime có endpoint adapter và JAXB converter phù hợp. Đây là **ví dụ contract-first theo thành phần**, không đại diện cho toàn bộ project Spring Boot có thể chạy độc lập.

Trong code này:

1. Spring tạo bean `OrdersEndpoint` qua `@Endpoint` và component scan/registration tương ứng.
2. Mapping chọn `createOrder(...)` dựa trên QName payload.
3. `@RequestPayload` cho phép adapter chuyển XML thành `CreateOrderRequest`.
4. Method gọi lớp nghiệp vụ, thay vì tự chứa transaction, SQL hoặc HTTP logic.
5. Trả `CreateOrderResponse` với JAXB root đúng contract; `@ResponsePayload` đưa nó vào SOAP Body.
6. `MessageDispatcherServlet` và SOAP message factory đảm nhiệm Envelope, HTTP và transport.

### 3.1. Phân biệt kiểu JAXB với tên element

Lớp Java `CreateOrderRequest` là kiểu tham số trong mã nguồn, còn QName `{urn:example:orders:v1}CreateOrderRequest` thuộc hợp đồng XML. Hai tên thường tương tự nhưng không phải đồng nhất bắt buộc.

Nếu `package-info.java` hoặc `@XmlRootElement(namespace=...)` có namespace sai, bạn có thể tạo được object Java nhưng khi marshal lại sinh XML root khác QName mà WSDL/XSD quy định. Lỗi điển hình là endpoint mapping không thấy handler hoặc phía client không unmarshal response.

### 3.2. Điều gì không nên đưa vào chữ ký?

Không dùng `@RequestBody` hay `@RestController` cho một endpoint Spring-WS SOAP thông thường, vì chúng thuộc mô hình Spring MVC HTTP/JSON. Spring-WS `@RequestPayload` không phải bản sao của `@RequestBody`; nó thao tác ở **tầng payload SOAP** và phụ thuộc `MethodEndpointAdapter` tương ứng.

Ví dụ cần tránh:

~~~java
// Sai mong đợi: @RequestBody là annotation của Spring MVC,
// không phải cơ chế JAXB payload binding của Spring-WS.
@PayloadRoot(namespace = NAMESPACE, localPart = "CreateOrderRequest")
public CreateOrderResponse create(
        @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

Dù code Java compile khi import Spring MVC, điều đó không chứng minh endpoint adapter Spring-WS có thể resolve argument. Với SOAP, dùng `@RequestPayload` cùng mapping/adapter thích hợp.

## 4. `@RequestPayload`: chọn kiểu tham số để đọc SOAP Body

`@RequestPayload` đánh dấu **tham số mang payload**. Spring-WS không đưa cả `soap:Envelope`, `soap:Header` và HTTP headers vào tham số này. Nó lấy phần nội dung Body mà endpoint adapter có thể chuyển thành kiểu Java đã khai báo.

### 4.1. Những kiểu tham số thường gặp

| Chữ ký minh họa | Khi nào nên dùng | Điều cần xác nhận |
| --- | --- | --- |
| `@RequestPayload CreateOrderRequest request` | JAXB DTO sinh từ XSD, có root metadata thích hợp. | JAXB adapter, `@XmlRootElement`/QName, mapping schema đúng version. |
| `@RequestPayload JAXBElement<CreateOrderRequestType> root` | JAXB model tách named complexType và global element. | Method adapter của Spring-WS version hiện tại hỗ trợ `JAXBElement`; `ObjectFactory` có đúng QName. |
| `@RequestPayload Source payload` | Muốn xử lý bằng XML transformer, XPath hoặc custom parser. | `Source` có thể không đọc lại được nếu dựa trên stream; bảo vệ parser và transform. |
| `@RequestPayload Element element` | Muốn thao tác DOM theo element. | Adapter có DOM processing phù hợp; chi phí dựng cây với payload lớn. |
| `MessageContext context` (không phải payload argument) | Cần truy cập SOAP message, Header hoặc response ở mức thấp. | Không nhầm với JAXB Body; tránh sửa các phần security đã ký. |

Danh sách không có nghĩa mọi biến thể đều hoạt động ở mọi release hoặc mọi adapter. Hãy kiểm tra `DefaultMethodEndpointAdapter`, các `MethodArgumentResolver` có trong Spring-WS version, cấu hình JAXB hoặc XML converter, và viết test với payload thật trước khi chốt chữ ký.

**Không dùng `@RequestPayload` hai lần cho hai trường XML con** rồi mong Spring-WS tự ánh xạ từng field:

~~~java
// Sai về kỳ vọng binding: @RequestPayload không hoạt động
// giống nhiều tham số query/form của Spring MVC.
public CreateOrderResponse create(
        @RequestPayload String clientOrderId,
        @RequestPayload BigDecimal amount) {
    // ...
}
~~~

Đối với XML gồm `clientOrderId` và `amount`, chữ ký JAXB nên nhận **một root object** chứa các field tương ứng. Hoặc dùng `@XPathParam` với namespace context và một method signature được adapter hỗ trợ trong trường hợp cần truy xuất giá trị XML đơn lẻ; cách đó là một chiến lược khác với unmarshalling JAXB full payload.

### 4.2. Chữ ký dựa trên `Source`: xử lý XML mà không phụ thuộc JAXB DTO

Nếu contract biến động hoặc endpoint cần xử lý XML với API mức thấp, có thể dùng `javax.xml.transform.Source`. Một chữ ký **minh họa**, với helper XML do ứng dụng tự triển khai:

~~~java
import javax.xml.transform.Source;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "CreateOrderRequest"
)
@ResponsePayload
public Source createOrderXml(@RequestPayload Source requestXml) {
    // Helper phải parse XML an toàn và tạo Source
    // có root QName là CreateOrderResponse.
    return orderXmlProcessor.createResponse(requestXml);
}
~~~

Ví dụ giả định `orderXmlProcessor` đã có, method adapter hỗ trợ `Source`. `Source` là giao diện Java SE cho nguồn XML, có thể bọc DOM, SAX, stream hoặc StAX tùy runtime. Nó **không phải chuỗi XML** và không tự xác thực XSD. Khi dùng `StreamSource`, đọc một lần có thể tiêu thụ stream; khi dùng DOM, chi phí giữ cây XML trong heap có thể lớn hơn.

Vì `Source` không tạo Java DTO domain-friendly, hãy dùng nó khi có yêu cầu XML chuyên biệt thực sự. Với hợp đồng doanh nghiệp có XSD rõ ràng, JAXB thường dễ bảo trì hơn, nhất là khi schema thay đổi có thể được phát hiện trong bước regenerate và kiểm thử.

### 4.3. Chữ ký dùng `JAXBElement` với named complexType

Không phải XSD nào cũng cho class có `@XmlRootElement`. Xét cấu trúc:

~~~xml
<xs:complexType name="CreateOrderRequestType">
  <xs:sequence>
    <xs:element name="clientOrderId" type="xs:string"/>
  </xs:sequence>
</xs:complexType>

<xs:element name="CreateOrderRequest"
            type="ord:CreateOrderRequestType"/>
~~~

XJC có thể sinh `CreateOrderRequestType` và `ObjectFactory#createCreateOrderRequest(...)` trả `JAXBElement<CreateOrderRequestType>`. Chữ ký endpoint tham khảo:

~~~java
import jakarta.xml.bind.JAXBElement;

@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "CreateOrderRequest"
)
@ResponsePayload
public JAXBElement<CreateOrderResponseType> createOrder(
        @RequestPayload JAXBElement<CreateOrderRequestType> root) {

    CreateOrderRequestType request = root.getValue();
    CreateOrderResponseType response =
            orderService.createTypedResponse(request);

    return objectFactory.createCreateOrderResponse(response);
}
~~~

Giả định các kiểu `...Type`, factory, `orderService` và adapter JAXB hỗ trợ `JAXBElement` trong version được sử dụng; đây là **ví dụ về chữ ký**, không phải file Java độc lập hoàn chỉnh. Khi xây contract thật, phải có global `CreateOrderResponse` và `ObjectFactory` tương ứng. **Không ép bỏ `JAXBElement`** nếu nó là phương tiện giữ đúng root QName.

Một số model được sinh tạo `@XmlRootElement` trực tiếp, nên có thể trả `CreateOrderResponse` thay vì `JAXBElement`. Hai cách biểu diễn khác nhau ở metadata JAXB, không phải hai giao thức SOAP khác nhau.

## 5. `@ResponsePayload`: chuyển giá trị trả về thành XML Body

Thông thường, `@ResponsePayload` được đặt **trên method**, không đặt trên tham số. Nó đánh dấu rằng giá trị trả về của handler sẽ được ghi vào SOAP Body thông qua `MethodReturnValueHandler` tương ứng.

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "CreateOrderRequest"
)
@ResponsePayload
public CreateOrderResponse createOrder(
        @RequestPayload CreateOrderRequest request) {
    // ...
    return response;
}
~~~

Spring-WS tạo/điều phối SOAP response thông qua message factory; `@ResponsePayload` không tự tạo `soap:Envelope` bằng String concatenation và cũng không chọn QName từ tên method `createOrder`.

### 5.1. Kiểu trả về phải tương thích adapter và hợp đồng

| Kiểu trả về | Cơ chế ghi kết quả | Bẫy thường gặp |
| --- | --- | --- |
| JAXB root object | Marshaller dùng `@XmlRootElement`/context để sinh XML root. | Root namespace hoặc localName sai. |
| `JAXBElement<T>` | Marshaller lấy QName từ `JAXBElement`. | Factory từ XSD khác version; QName sai. |
| `Source` hoặc DOM element được hỗ trợ | XML adapter ghi XML source/node vào payload. | Tạo nhầm toàn bộ SOAP Envelope làm nội dung Body; XML không hợp lệ. |
| `void` | Không có payload object từ method để ghi. | Không nhất thiết phù hợp WSDL request-response; xem hợp đồng một chiều. |
| DTO không được JAXB biết đến | Không có handler/marshaller phù hợp. | Trả về POJO tùy ý rồi mong Spring-WS tự biến thành XML. |

Không thể dựa vào kiểu Java `String` rồi mặc nhiên coi nó là XML document hợp đồng. Đặc biệt, một response như:

~~~java
@ResponsePayload
public String createOrder(@RequestPayload CreateOrderRequest request) {
    return "<CreateOrderResponse>OK</CreateOrderResponse>";
}
~~~

**không phải thiết kế contract-first chuẩn để khẳng định chạy được**: `String` có thể không được handler xử lý như một XML payload, và nếu có cơ chế transform tùy chỉnh thì vẫn có nguy cơ sai namespace, escaping và schema. Hãy trả class JAXB hoặc `Source` có chủ đích, thay vì lắp XML bằng chuỗi.

### 5.2. Method không trả payload: khi nào dùng `void`?

Một chữ ký một chiều có thể biểu diễn như sau:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "NotifyOrderRequest"
)
public void notifyOrder(@RequestPayload NotifyOrderRequest request) {
    notificationService.accept(request);
}
~~~

Trường hợp này **chỉ hợp lý nếu contract và cơ chế request/response phù hợp**. WSDL one-way operation không khai báo `wsdl:output`; ở transport HTTP, vẫn có response ở mức protocol/transport tùy SOAP version, runtime và binding. Không giả định cứ trả `void` là client được HTTP `202`, không có Envelope hoặc server sẽ không bao giờ gửi SOAP Fault.

Ngược lại, với WSDL đã định nghĩa operation `CreateOrder` **request-response** có output element `CreateOrderResponse`, method trả `void` sẽ khiến hợp đồng thực thi không phù hợp yêu cầu client. Tùy adapter và framework, Spring-WS có thể gửi một response không có payload hoặc lỗi; cần giữ đúng kiểu phản hồi contract quy định.

### 5.3. Không dùng `@ResponsePayload` thay cho SOAP Fault

Một method nghiệp vụ gặp lỗi không nên tự ý tạo:

~~~xml
<ord:CreateOrderResponse xmlns:ord="urn:example:orders:v1">
  <ord:status>ERROR</ord:status>
</ord:CreateOrderResponse>
~~~

nếu XSD yêu cầu thêm `orderId` hoặc hợp đồng quy định lỗi protocol bằng SOAP Fault. Có hai loại lỗi cần phân biệt:

- **Kết quả nghiệp vụ hợp lệ:** response schema cho phép trạng thái từ chối, ví dụ `REJECTED` và đầy đủ các element.
- **Lỗi SOAP protocol/validation/security hoặc exception được map:** dùng SOAP Fault theo binding và exception resolver tương ứng, không coi mọi lỗi đều là response thành công.

`@ResponsePayload` chỉ liên quan tới **giá trị return thành công** mà adapter serialize; SOAP Fault thường do exception mapping và SOAP runtime xử lý.

## 6. Định tuyến handler là việc của `@PayloadRoot`, không phải URL WSDL

Với bean WSDL tên `orders` và servlet mapping `/ws/*`, client có thể:

~~~text
GET  /ws/orders.wsdl   → tải hợp đồng
POST /ws               → gửi SOAP Envelope
~~~

Ở POST, Spring-WS có thể có nhiều endpoint cùng dùng đường dẫn `/ws`, ví dụ:

~~~java
@PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
public CreateOrderResponse createOrder(...)

@PayloadRoot(namespace = NS, localPart = "CancelOrderRequest")
public CancelOrderResponse cancelOrder(...)

@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
public GetOrderResponse getOrder(...)
~~~

Các ví dụ trên rút gọn để thể hiện mapping; trong code chạy thực tế còn cần `@ResponsePayload`, kiểu tham số, import và chú thích JAXB/XML tương ứng. **URL HTTP là một cửa vào**, còn QName payload giúp chọn method. Tên method Java `createOrder` có thể khác tên operation WSDL; điểm bắt buộc là XML input/output và binding hợp đồng phải nhất quán.

### 6.1. QName gồm namespace URI và localPart

Nếu client gửi:

~~~xml
<x:CreateOrderRequest xmlns:x="urn:example:orders:v1">
  ...
</x:CreateOrderRequest>
~~~

thì prefix `x` khác `ord` **không ảnh hưởng mapping**. Nhưng:

~~~xml
<x:CreateOrderRequest xmlns:x="urn:example:orders:v2">
  ...
</x:CreateOrderRequest>
~~~

có QName khác với hợp đồng v1 và không khớp method đang chờ `urn:example:orders:v1`. Tương tự, `createOrderRequest` khác `CreateOrderRequest` do phân biệt chữ hoa/thường của local name.

Cẩn thận `elementFormDefault="qualified"`: nội dung payload có root QName đúng nhưng các element con sai namespace vẫn có thể bị XSD validation từ chối, dù routing đã chọn được method.

### 6.2. Một QName không nên được đăng ký cho hai handler cùng điều kiện

Nếu hai bean hoặc hai method đều khai báo cùng một `@PayloadRoot(namespace, localPart)` và cùng độ ưu tiên mapping, hệ thống có thể xung đột hoặc chọn handler không như mong đợi. Không xem việc đổi tên method Java là một cách phân biệt operation khi QName giống nhau.

Khi cần phiên bản song song, dùng namespace hoặc contract strategy rõ ràng; khi cần routing theo SOAPAction thay vì Body, Spring-WS cũng có `@SoapAction` và mapping tương ứng, nhưng phải bảo đảm SOAPAction có mặt/khớp WSDL và version hỗ trợ. Không trộn tùy tiện hai chiến lược mapping mà không kiểm tra thứ tự/ưu tiên endpoint mappings.

## 7. Một method có thể cần dữ liệu ngoài payload

Không phải mọi thông tin đều nằm trong `soap:Body`. Hệ thống doanh nghiệp thường mang correlation ID, timestamp, chữ ký, thông tin chứng thực hoặc WS-Addressing trong `soap:Header`. Khi thiết kế chữ ký, cần tách **tham số nghiệp vụ** và **metadata protocol**.

### 7.1. Nhận SOAP Header qua `@SoapHeader` khi cần

Spring-WS có annotation `@SoapHeader` để đánh dấu header element muốn đưa vào tham số handler tương ứng. Ví dụ về **chữ ký**:

~~~java
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.server.endpoint.annotation.SoapHeader;

@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "CreateOrderRequest"
)
@ResponsePayload
public CreateOrderResponse createOrder(
        @RequestPayload CreateOrderRequest request,
        @SoapHeader("{urn:example:headers:v1}CorrelationId")
        SoapHeaderElement correlationHeader) {

    // Xử lý request, lấy metadata nếu cần.
    return orderService.createResponse(request);
}
~~~

Đoạn này giả định SOAP request có một header `CorrelationId` thuộc namespace `urn:example:headers:v1` và adapter của phiên bản Spring-WS hỗ trợ chữ ký tương ứng. Việc header thiếu, rỗng hoặc nhiều bản sao cần chính sách xử lý rõ ràng. Không được tự coi `correlationHeader` là bằng chứng xác thực chỉ vì nó được client gửi; correlation ID chỉ dùng theo dõi, còn danh tính và tính toàn vẹn cần được xác minh bởi tầng security.

SOAP request ví dụ:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1"
    xmlns:meta="urn:example:headers:v1">
  <soap:Header>
    <meta:CorrelationId>9a7d58b4-2d0d-4adb-9568-abc123def456</meta:CorrelationId>
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

`@RequestPayload` trong cùng method chỉ xử lý phần `ord:CreateOrderRequest` ở Body; `@SoapHeader` không biến `CorrelationId` thành một field của JAXB request.

### 7.2. Sử dụng `MessageContext` khi cần thao tác SOAP ở mức thấp

Một số endpoint cần đọc message context, header, attachment hoặc các thông tin thấp tầng khác. Spring-WS có kiểu `org.springframework.ws.context.MessageContext` mà endpoint adapter có thể hỗ trợ làm tham số, không đánh dấu bằng `@RequestPayload`:

~~~java
@PayloadRoot(
    namespace = NAMESPACE,
    localPart = "CreateOrderRequest"
)
@ResponsePayload
public CreateOrderResponse createOrder(
        @RequestPayload CreateOrderRequest request,
        MessageContext messageContext) {

    // Có thể truy cập request/response message nếu cần.
    return orderService.createResponse(request);
}
~~~

Ví dụ rút gọn, giả định import và `orderService` đã có. Không nên dùng `MessageContext` để tự parse lại Body khi JAXB đã xử lý đầy đủ: có thể tăng chi phí, làm hỏng cơ chế streaming hoặc vô tình bỏ qua validation/interceptor. Với MTOM/attachment, phải xem cơ chế SOAP message/attachment API tương ứng, **không giả định `@RequestPayload` tự chuyển mọi MIME attachment thành một field byte[] trong mọi trường hợp**.

## 8. Vai trò của endpoint adapter và JAXB configuration

Một `@Endpoint` bean có thể được phát hiện qua component scan, nhưng handler còn cần endpoint mapping và endpoint adapter. Trong thiết lập Spring-WS phổ biến, `DefaultMethodEndpointAdapter` cùng những method argument resolvers/return value handlers hỗ trợ các kiểu JAXB và XML nhất định.

### 8.1. Method signature hợp lệ không chỉ phụ thuộc cú pháp Java

Ví dụ cùng annotation nhưng khác kiểu:

~~~java
@PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
@ResponsePayload
public UnknownResponse create(
        @RequestPayload UnknownRequest request) {
    // ...
}
~~~

Java compiler có thể chấp nhận nếu `UnknownRequest`/`UnknownResponse` tồn tại, nhưng Spring-WS chỉ xử lý được khi endpoint adapter có converter/resolver tương thích. Một POJO không mang JAXB metadata và không có marshaller tùy chỉnh **không tự trở thành SOAP payload**. Vì vậy hãy đặt câu hỏi:

1. Object Java được sinh bởi công cụ XJC/JAXB từ XSD nào?
2. Class có `@XmlRootElement` hay phải dùng `JAXBElement`?
3. JAXB context có biết package/class đó không?
4. Endpoint adapter xử lý kiểu tham số và kiểu return trên phiên bản đang chạy không?
5. Serializer tạo đúng namespace, localName và thứ tự element theo XSD không?

### 8.2. `Jaxb2Marshaller`: cấu hình khi cần marshalling rõ ràng

Với Spring-WS, một cấu hình client hoặc adapter tùy chỉnh có thể dùng `Jaxb2Marshaller`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Bean
public Jaxb2Marshaller orderMarshaller() {
    Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
    marshaller.setContextPath("com.example.orders.contract");
    return marshaller;
}
~~~

`setContextPath` là **tên package chứa JAXB metadata/factory**, không phải WSDL URL và không phải `src/main/resources/xsd/orders.xsd`. Chỉ khai báo bean này **không bảo đảm** mọi endpoint adapter sẽ tự động chọn nó; tùy Spring-WS version, có thể cần đăng ký converter/adapter hoặc dùng JAXB2 payload processor được framework cấu hình mặc định. Đối với endpoint đơn giản dùng annotation JAXB root class, Spring-WS có thể sử dụng bộ xử lý JAXB mà không yêu cầu gắn thủ công một bean `Jaxb2Marshaller` riêng.

Khi đổi XSD, hãy regenerate JAXB model thay vì sửa mã generated. Đặc biệt, khi nâng cấp từ `javax.xml.bind.*` sang `jakarta.xml.bind.*`, phải bảo đảm framework, generator, JAXB runtime và các classes được sinh cùng thế hệ. Riêng `javax.xml.namespace.QName` vẫn là Java SE API có tên `javax`.

### 8.3. Tại sao `@RequestPayload` không tự validate mọi XSD facet?

JAXB unmarshalling thường chuyển XML thành object, nhưng **không mặc định có nghĩa toàn bộ XSD được validate**. Ví dụ:

~~~xml
<ord:clientOrderId>abc</ord:clientOrderId>
~~~

Có thể deserialize thành `String`, dù `OrderCodeType` trong XSD yêu cầu pattern ba chữ hoa, dấu nối, tám chữ số, dấu nối, bốn chữ số. Muốn từ chối input sai contract, cần cấu hình schema validation thật sự.

Trong Spring-WS, `PayloadValidatingInterceptor` là một lựa chọn server-side để kiểm tra request payload dựa trên XSD, độc lập với việc method đang nhận JAXB object hay `Source`.

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

PayloadValidatingInterceptor validating =
        new PayloadValidatingInterceptor();

validating.setXsdSchema(
        new ClassPathResource("xsd/orders.xsd"));
validating.setValidateRequest(true);
validating.setValidateResponse(true);
~~~

Đây là một đoạn tạo interceptor; **phải đăng ký nó vào interceptor chain** của Spring-WS (ví dụ qua `WsConfigurer#addInterceptors`) để nó có tác dụng. Bật `setValidateResponse(true)` hữu ích trong test/điều kiện cần kiểm soát response; cân nhắc chi phí và tình huống response Fault theo môi trường. Đừng nhầm với việc dùng Bean Validation `@Valid`/`@NotNull` của Java: các constraint ấy không tự nhiên đồng nhất với XSD validation, và `@RequestPayload` không có cơ chế `required=false` như `@RequestBody` của Spring MVC.

## 9. Request hợp lệ và request sai hợp đồng sẽ đi qua những gì?

Giả sử request có Body:

~~~xml
<ord:CreateOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
  <ord:amount>1250000.00</ord:amount>
  <ord:currency>VND</ord:currency>
</ord:CreateOrderRequest>
~~~

Quy trình logic:

1. SOAP parser xác nhận Envelope/Body well-formed và đúng SOAP version.
2. Endpoint mapping tìm `@PayloadRoot` khớp QName request.
3. Các interceptor được cấu hình kiểm tra security/validation/logging theo thứ tự áp dụng.
4. Adapter chuyển payload thành tham số `CreateOrderRequest` (nếu hỗ trợ).
5. Method gọi business service và trả `CreateOrderResponse`.
6. Return value handler ghi XML payload vào SOAP response.
7. HTTP sender trả dữ liệu về client theo binding và trạng thái thực tế.

Nếu thay `clientOrderId` thành `bad`, QName root **vẫn đúng**: endpoint mapping có thể chọn đúng method. Nhưng `PayloadValidatingInterceptor` nên từ chối vì vi phạm XSD pattern nếu interceptor đã được đăng ký và chạy đúng. Vì thế **mapping thành công không đồng nghĩa payload hợp lệ**.

### 9.1. Lỗi kiểu dữ liệu so với lỗi nghiệp vụ

| Ví dụ lỗi | Tầng phát hiện điển hình | Cách xử lý mong muốn |
| --- | --- | --- |
| SOAP Envelope sai namespace | SOAP parser/message factory | SOAP protocol error/Fault tùy stack. |
| Root payload sai namespace | EndpointMapping | Không tìm thấy handler phù hợp; phản hồi tùy resolver. |
| `amount=ABC` | Schema validator hoặc JAXB unmarshaller | Lỗi hợp đồng/type; từ chối request phù hợp. |
| `clientOrderId=bad` | Schema validator nếu bật pattern validation | Lỗi XSD facet, không nhất thiết JAXB tự chặn. |
| `orderId` đã tồn tại | Business service | Lỗi nghiệp vụ/response hoặc Fault theo hợp đồng. |
| Header WS-Security sai chữ ký | Security interceptor/runtime | Từ chối trước business logic; SOAP Fault/security failure. |
| Lỗi DB timeout | Business/infrastructure | Exception được map sang Fault hoặc xử lý nghiệp vụ phù hợp. |
| JAXB response thiếu element bắt buộc | Response validator/client validation | Phát hiện server sinh payload trái XSD. |

Không có quy tắc chung rằng mọi lỗi schema sẽ trở thành một `faultcode`, HTTP status hay message giống nhau. **Exception resolver và SOAP version** quyết định cách ánh xạ Fault; tránh viết client dựa trên chuỗi lỗi mặc định của một bản Spring-WS cụ thể.

### 9.2. SOAP Fault không phải `@ResponsePayload`

Với SOAP 1.1, một phản hồi lỗi có thể trông như:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Request payload không hợp lệ</faultstring>
      <detail>
        <errorCode>INVALID_ORDER_REQUEST</errorCode>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Ví dụ chỉ minh họa Fault khi server mapping lỗi thành SOAP 1.1 Client Fault; định dạng `detail`, namespace tùy hợp đồng và resolver thực tế. SOAP 1.2 dùng cấu trúc Code/Reason/Detail khác. Không nên dùng JAXB `CreateOrderResponse` để lắp một `soap:Fault` thủ công bằng return value khi exception resolver và SOAP runtime được giao trách nhiệm đó.

Với Spring-WS, có các cơ chế như `SoapFaultMappingExceptionResolver` và `SoapFaultAnnotationExceptionResolver` (tùy version/config) để ánh xạ exception nghiệp vụ/kỹ thuật sang Fault. Không trả thẳng stack trace, token, SQL hoặc private key trong `faultstring`/`detail`.

## 10. Viết endpoint an toàn: security, trạng thái và khả năng chịu tải

Một chữ ký `@RequestPayload`/`@ResponsePayload` đơn giản không có nghĩa xử lý SOAP trong production chỉ gồm deserialize rồi gọi service. Các tích hợp doanh nghiệp còn cần xác thực, ủy quyền, chống replay, giới hạn kích thước và phản hồi lỗi đúng chuẩn.

### 10.1. Không xử lý WS-Security như field nghiệp vụ trong Body

WS-Security thường nằm trong **SOAP Header**, có thể gồm UsernameToken, timestamp, XML Signature, encryption và thông tin chứng chỉ. Những dữ liệu đó không phải field JAXB của `CreateOrderRequest` trừ khi hợp đồng nghiệp vụ định nghĩa một field khác với mục đích khác.

~~~text
HTTP + TLS / client certificate
  → SOAP MessageFactory / parser
  → WS-Security interceptor: token, signature, timestamp
  → EndpointMapping / XSD validation / other interceptors
  → @RequestPayload JAXB object
  → business service, authorization, transaction
  → @ResponsePayload JAXB response hoặc SOAP Fault
~~~

Thứ tự tương đối giữa mapping, validation và security phụ thuộc cấu hình thực tế; yêu cầu an toàn là kiểm tra quyền và dữ liệu đáng tin cậy **trước thao tác nghiệp vụ nhạy cảm**. Chỉ có `@RequestPayload` không làm Spring-WS tự xác minh XML Signature hoặc chứng chỉ.

Một số dự án dùng `Wss4jSecurityInterceptor` để kiểm tra header bảo mật. Không tin `username` hoặc correlation ID do client gửi nếu chưa xác thực. Sau khi signature được xác minh, tránh sửa tùy tiện các XML nodes đã ký vì có thể làm thay đổi dữ liệu được bảo vệ.

### 10.2. XML security và giới hạn tài nguyên

Đầu vào XML không tin cậy có thể khai thác parser nếu external entity/DTD, entity expansion hoặc schema resolution không được kiểm soát. Cần cấu hình an toàn parser/transformer, kiểm soát schema import, giới hạn kích thước HTTP request, timeout và concurrency.

Một SOAP Body lớn có thể tăng heap vì parser, JAXB model, DOM, logging hoặc validation. `Source` có thể hỗ trợ xử lý kiểu luồng, nhưng **không mặc định stream đọc lại được**. Với Apache Axiom và `payloadCaching=false` trong những phiên bản hỗ trợ, một số mapping/interceptor đọc Body trước adapter có thể tiêu thụ stream, khiến `@RequestPayload` không còn payload để xử lý. Phải kiểm tra compatibility toàn pipeline trước khi bật.

Đừng tối ưu hiệu năng bằng cách vô hiệu hóa validation, chữ ký số hoặc audit bắt buộc. Nên đo workload thực, chọn buffering hợp lý và cân nhắc MTOM cho dữ liệu nhị phân nếu hợp đồng cho phép.

### 10.3. Endpoint thường là bean singleton

Một endpoint Spring thông thường có thể phục vụ **nhiều SOAP request đồng thời**. Vì vậy dùng field cho dependency dài hạn và biến cục bộ cho dữ liệu từng request:

~~~java
@Endpoint
public class OrdersEndpoint {

    private final OrderApplicationService orderService;

    public OrdersEndpoint(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    // Request/response được giữ trong biến cục bộ của method.
}
~~~

Không đặt `CreateOrderRequest currentRequest` hay `CreateOrderResponse lastResponse` làm field mutable dùng chung; điều đó có thể làm trộn dữ liệu giữa các request. Lớp business service được inject cũng cần có chiến lược thread safety và transaction phù hợp.

## 11. Kiểm thử hợp đồng: không chỉ gọi Java method trực tiếp

Một unit test gọi thẳng `endpoint.createOrder(new CreateOrderRequest())` có thể kiểm tra business mapping, nhưng **không chứng minh** `@PayloadRoot` được định tuyến, XML được unmarshal hoặc `@ResponsePayload` serialize thành đúng QName. Cần kiểm thử từ payload XML.

### 11.1. Ma trận các ca thử thiết yếu

| Ca thử | Điều cần xác nhận | Tầng |
| --- | --- | --- |
| Request hợp lệ, đúng QName | Đúng handler, response đúng XSD. | Mapping/adapter/JAXB. |
| Prefix XML đổi từ `ord` sang `x` | Vẫn chọn handler nếu namespace URI không đổi. | QName mapping. |
| Namespace đổi v1 sang v2 | Không bị xử lý nhầm bằng endpoint v1. | Routing/versioning. |
| Root localName sai chữ hoa/thường | Không match handler ngoài ý muốn. | Routing. |
| Sai thứ tự element hoặc thiếu phần tử bắt buộc | Bị schema validation từ chối khi bật. | XSD validation. |
| `amount=abc` | Không thực thi nghiệp vụ thành công. | JAXB/type validation. |
| `clientOrderId=bad` | Bị từ chối theo XSD pattern nếu validator bật. | Facet validation. |
| Response không có root JAXB metadata | Lỗi marshalling được phát hiện. | Return value handler. |
| Business service gặp mã đơn trùng | Response/Fault đúng hợp đồng. | Business/exception resolver. |
| WS-Security thiếu chữ ký hoặc token | Bị từ chối trước xử lý nhạy cảm. | Security. |
| SOAP version không khớp binding | Không bị coi là request hợp lệ. | Protocol. |
| Client Java/.NET gọi và đọc response/Fault | Tương thích schema/binding/headers. | Interoperability. |

### 11.2. Kiểm thử với `MockWebServiceClient`

Spring-WS Test có `MockWebServiceClient` để gửi payload XML qua cấu hình server trong môi trường kiểm thử mà không phải chạy một HTTP server đầy đủ:

~~~java
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;

// applicationContext đã chứa endpoint, mapping, adapter và service test.
MockWebServiceClient client =
        MockWebServiceClient.createClient(applicationContext);

String requestXml =
        "<ord:CreateOrderRequest " +
        "xmlns:ord=\"urn:example:orders:v1\">" +
        "<ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>" +
        "<ord:amount>1250000.00</ord:amount>" +
        "<ord:currency>VND</ord:currency>" +
        "</ord:CreateOrderRequest>";

client.sendRequest(withPayload(new StringSource(requestXml)))
      .andExpect(noFault());
~~~

Code giả định các dependency Spring-WS Test và test context phù hợp. `noFault()` chỉ xác nhận không xuất hiện SOAP Fault; vẫn cần assertion đối với payload response và kết quả nghiệp vụ, đồng thời các ca test invalid XML để kiểm tra schema/security. Khi service trả order ID ngẫu nhiên, dùng stub hoặc assertion phù hợp để test ổn định.

### 11.3. Kiểm tra HTTP SOAP thực tế

Khi ứng dụng test chạy ở `localhost:8080`, có servlet mapping `/ws/*`, `soap:address` là `http://localhost:8080/ws`, lưu SOAP Envelope ở mục 2 vào file `request.xml` UTF-8 rồi gửi:

~~~powershell
curl.exe --include --request POST --header 'Content-Type: text/xml; charset=utf-8' --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' --data-binary '@request.xml' "http://localhost:8080/ws"
~~~

`SOAPAction` ở đây là **giá trị giả định** từ một hợp đồng WSDL minh họa; phải đối chiếu `soap:operation` thực tế trước khi dùng. `@PayloadRoot` định tuyến theo Body QName, không tự đặt SOAPAction. URL tải WSDL có thể là `/ws/orders.wsdl` **nếu** server có bean WSDL tên `orders` dưới servlet mapping `/ws/*`; URL tải WSDL và URL POST SOAP không đồng nhất.

Sau khi gửi, kiểm tra HTTP status, SOAP Envelope, QName của response, SOAP Fault nếu có, XSD validity, TLS/auth và log correlation. **HTTP 200 không tự chứng minh response đúng hợp đồng**; HTTP lỗi có thể chứa SOAP Fault chuẩn hoặc chỉ là lỗi proxy/transport không có SOAP XML.

## 12. Các lỗi thường gặp khi thiết kế chữ ký endpoint

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `@Endpoint` không được gọi | Bean chưa được scan, servlet mapping sai hoặc QName không khớp. | Bean registration, `MessageDispatcherServlet`, `@PayloadRoot`. |
| Method bị báo không hỗ trợ | Adapter thiếu argument resolver/return handler cho kiểu Java. | `DefaultMethodEndpointAdapter` và kiểu tham số/return. |
| Không unmarshal request | JAXB context thiếu class, element name khác XSD. | Generated classes, `@XmlRootElement`/`JAXBElement`. |
| Mapping đúng nhưng validation fail | Element con sai namespace, thứ tự `xs:sequence`, enum/pattern. | Validate payload riêng bằng XSD. |
| Response sinh root sai | Class/factory JAXB mang QName khác `CreateOrderResponse`. | Xem XML trên wire và JAXB metadata. |
| Trả `String` nhưng không ra XML đúng | Return handler không phù hợp, XML thiếu namespace. | Dùng JAXB root/`JAXBElement` hoặc `Source` được hỗ trợ. |
| `@RequestBody` không hoạt động | Nhầm annotation Spring MVC với Spring-WS. | Kiểm tra imports và endpoint framework. |
| Client báo thiếu response | Method trả `void` nhưng WSDL có output bắt buộc. | So method với `wsdl:operation`. |
| SOAP Fault không đúng contract | Thiếu exception resolver/fault mapping. | Kiểm tra mapping Fault của SOAP version. |
| Header không được xử lý | Chỉ đọc Body qua `@RequestPayload`. | `@SoapHeader`/`MessageContext` và security interceptor. |
| Trộn `javax`/`jakarta` | JAXB code sinh từ tool khác thế hệ runtime. | Kiểm tra imports, generator, dependency tree. |
| Thất bại khi dùng Axiom non-caching | Stream bị mapping/validation/logging đọc nhiều lần. | Kiểm tra `payloadCaching` và interceptor chain. |

**Quy trình debug:** bắt đầu với raw HTTP/SOAP → xác nhận SOAP version → so QName root → kiểm tra endpoint mapping → xem interceptor/validation → thử JAXB argument → chạy method → xem JAXB return → đọc response/Fault. Hãy ghi rõ tầng cuối cùng thành công thay vì sửa annotation ngẫu nhiên.

## 13. Bài thực hành: chọn đúng chữ ký

### Tình huống A — Đúng tên class, sai namespace

Handler chờ QName `{urn:example:orders:v1}CreateOrderRequest` nhưng client gửi:

~~~xml
<x:CreateOrderRequest xmlns:x="urn:example:orders:v2">
  <x:clientOrderId>WEB-20261127-0042</x:clientOrderId>
  <x:amount>1250000.00</x:amount>
  <x:currency>VND</x:currency>
</x:CreateOrderRequest>
~~~

**Câu hỏi:** lỗi xảy ra ở mapping hay business? **Đáp án:** trước tiên là mapping theo QName. Namespace v2 khác v1; không sửa Java class name hay localPart để chữa sai namespace tùy tiện.

### Tình huống B — JAXB dùng named complex type

XSD có `xs:element name="CreateOrderRequest" type="ord:CreateOrderRequestType"`. XJC sinh `ObjectFactory#createCreateOrderRequest(...)` trả `JAXBElement<CreateOrderRequestType>`. Method nhận trực tiếp `CreateOrderRequestType` nhưng adapter không xử lý được.

**Đáp án:** kiểm tra JAXB root metadata, generator và resolvers của phiên bản Spring-WS. Có thể cần `@RequestPayload JAXBElement<CreateOrderRequestType>`, và return `JAXBElement<CreateOrderResponseType>` tương ứng. Không tự thêm `@XmlRootElement` sai QName vào file generated.

### Tình huống C — Thiếu return value

WSDL khai báo input `CreateOrderRequest` và output `CreateOrderResponse`, nhưng method là `public void createOrder(...)`.

**Đáp án:** chữ ký không phản ánh output mà contract yêu cầu. Trả đúng response object với `@ResponsePayload` hoặc thiết kế lại WSDL thành operation một chiều nếu nghiệp vụ và đối tác cho phép; không dùng `void` để che lỗi marshalling.

### Tình huống D — XML hợp cú pháp nhưng sai pattern

Client gửi `clientOrderId=bad`. JAXB đọc được `String`, còn schema yêu cầu `[A-Z]{3}-[0-9]{8}-[0-9]{4}`.

**Đáp án:** bật và đăng ký XSD validation, kiểm tra request invalid bị từ chối. `@RequestPayload` không tự enforce pattern/facet.

### Tình huống E — Chữ ký WS-Security trong SOAP Header

Lập trình viên muốn thêm field `signature` vào `CreateOrderRequest` để kiểm tra WS-Security trực tiếp trong endpoint.

**Đáp án:** XML Signature của WS-Security thuộc SOAP Header/chính sách bảo mật, không phải payload nghiệp vụ. Cấu hình security interceptor/runtime và trust theo hợp đồng; chỉ xử lý business sau khi xác minh thành công.

## 14. Checklist và ghi nhớ

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Handler có được phát hiện? | Class có `@Endpoint`, bean được scan/đăng ký đúng. |
| Root QName của request đúng? | `@PayloadRoot` khớp namespace URI + localPart trong XSD/WSDL. |
| Payload parameter đúng kiểu? | `@RequestPayload` và adapter hỗ trợ JAXB/Source/DOM tương ứng. |
| JAXB root metadata hợp lệ? | `@XmlRootElement` hoặc `JAXBElement` mang QName chính xác. |
| Operation có output? | `@ResponsePayload` và return type đúng contract request-response. |
| Response XML đúng XSD? | Namespace, thứ tự, required elements, kiểu và giá trị phù hợp. |
| Header/security được xử lý riêng? | SOAP Header, TLS, WS-Security ở tầng phù hợp. |
| XSD validation hoạt động? | Interceptor/schema validator được đăng ký khi cần. |
| Business logic có tách khỏi endpoint? | Endpoint chuyển dữ liệu, gọi service, trả response/Fault rõ ràng. |
| Fault mapping nhất quán? | Có exception resolver và không lộ thông tin nhạy cảm. |
| Có kiểm thử cả SOAP XML? | Định tuyến, marshalling, validation, WSDL và client interoperability. |
| Dependencies có tương thích? | Spring-WS, JAXB, JDK và `javax`/`jakarta` đồng bộ. |

**Ghi nhớ:** `@PayloadRoot` **chọn method** theo QName SOAP Body; `@RequestPayload` **liên kết input XML** với tham số Java; `@ResponsePayload` **ghi return value** thành SOAP response payload. Ba annotation liên quan nhưng không thay thế lẫn nhau.

**Thiết kế đúng chữ ký không đủ nếu bỏ qua hợp đồng.** Luôn kiểm tra XSD/WSDL, JAXB root QName, endpoint adapter, interceptor/WS-Security và SOAP Fault trên các bản tin XML thực tế. Đây là nền tảng để dịch vụ Spring-WS contract-first tích hợp ổn định và dễ phát hiện sai khác giữa client và server.





