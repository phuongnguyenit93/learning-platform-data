# Phân biệt lớp dữ liệu JAXB với proxy dịch vụ JAX-WS

Trong một dự án **Spring Web Services (Spring-WS)** triển khai SOAP theo hướng **contract-first**, lập trình viên thường thấy các class được sinh từ XSD/WSDL rồi tưởng rằng tất cả đều là “SOAP client”. Thực tế, **lớp dữ liệu JAXB** và **proxy dịch vụ JAX-WS** đảm nhiệm hai phần việc khác nhau: một bên mô tả **hình dạng dữ liệu XML**, bên còn lại cung cấp **cách gọi operation SOAP qua mạng**.

Phân biệt đúng giúp lựa chọn công cụ sinh mã, tránh nhầm package/API, thiết kế endpoint và SOAP client phù hợp với hợp đồng, đồng thời tìm lỗi ở đúng tầng khi gặp SOAP Fault, sai QName, lỗi marshalling hoặc WS-Security. Bài này thuộc chương **Sinh mã JAXB**, tập trung vào sự khác biệt đó và cách dùng các thành phần trong hệ sinh thái Spring-WS. Các tên class/operation dùng trong ví dụ là minh họa; tên Java thực tế phụ thuộc XSD, WSDL và cấu hình công cụ sinh mã.

## 1. Hai câu hỏi khác nhau: dữ liệu XML là gì và gọi dịch vụ ra sao?

Một hợp đồng SOAP thường gồm **XSD** mô tả element/complexType và **WSDL 1.1** mô tả message, operation, binding, service/port. Từ đó có thể sinh các loại mã:

| Câu hỏi | Lớp dữ liệu JAXB | Proxy dịch vụ JAX-WS |
| --- | --- | --- |
| Được sinh từ đâu? | Chủ yếu từ **XSD**; cũng có thể được tạo gián tiếp khi công cụ đọc WSDL có nhúng/tham chiếu XSD. | Từ **WSDL** với các mô tả message, portType, binding và service. |
| Nhiệm vụ chính | Biểu diễn dữ liệu XML dưới dạng object Java và quy tắc marshalling/unmarshalling. | Gọi operation SOAP qua endpoint; quản lý invocation, transport, SOAP message và ánh xạ response/fault qua runtime. |
| Những class thường gặp | `CreateOrderRequestType`, `CreateOrderResponseType`, `ObjectFactory`, `package-info.java`, `JAXBElement`. | Class `OrdersService` gắn `@WebServiceClient`, interface port gắn `@WebService`, method `@WebMethod` và các wrapper/fault classes. |
| Có HTTP/SOAP client tự thân? | **Không**: object JAXB chỉ là dữ liệu, không tự gửi HTTP. | **Có khi đi qua JAX-WS runtime**: code dùng service/port proxy để thực hiện lời gọi. |
| Có thể dùng trong Spring-WS? | **Có**: thường dùng với `Jaxb2Marshaller`, `WebServiceTemplate` và endpoint. | Có thể dùng làm **client JAX-WS riêng** để gọi một Spring-WS endpoint nếu binding/WSDL tương thích, nhưng Spring-WS không yêu cầu JAX-WS proxy. |
| Có kiểm tra toàn bộ XSD facet mặc định? | Không nên giả định; cần bật validation khi muốn bảo đảm ràng buộc. | Không nên giả định chỉ vì gọi qua port; phụ thuộc runtime và cấu hình validation. |
| Tác động của đổi WSDL endpoint | JAXB DTO có thể giữ nguyên nếu XSD không đổi. | Proxy có thể cần cập nhật WSDL/address/binding nếu hợp đồng vận chuyển hoặc operation thay đổi. |

Hãy xem luồng từ hợp đồng đến lúc gọi dịch vụ:

~~~mermaid
flowchart TD
    A["orders.xsd: element/type"] --> B["XJC / JAXB binding compiler"]
    B --> C["JAXB model: request, response, ObjectFactory"]
    W["orders.wsdl: message/portType/binding/service"] --> D["wsimport / JAX-WS tooling"]
    A --> D
    D --> E["JAX-WS Service + port interface"]
    D --> F["JAXB value types"]
    C --> G["Spring-WS Jaxb2Marshaller"]
    G --> H["WebServiceTemplate hoặc @Endpoint"]
    E --> I["JAX-WS runtime proxy"]
    I --> J["SOAP HTTP request/response"]
    H --> J
~~~

Sơ đồ có hai đường triển khai client phổ biến: **Spring-WS với `WebServiceTemplate` + JAXB**, hoặc **JAX-WS với `Service` + port proxy**. Cả hai có thể trao đổi SOAP tuân theo cùng WSDL/XSD, nhưng cách tổ chức mã, cấu hình interceptor và xử lý lỗi khác nhau.

## 2. Hợp đồng mẫu: XSD định nghĩa dữ liệu, WSDL định nghĩa lời gọi

Giả sử bên cung cấp triển khai operation `CreateOrder` với namespace nghiệp vụ `urn:example:orders:v1`. Một file `orders.xsd` rút gọn, đầy đủ về cấu trúc XML, như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

  <xs:complexType name="CreateOrderRequestType">
    <xs:sequence>
      <xs:element name="clientOrderId" type="xs:string"/>
      <xs:element name="amount" type="xs:decimal"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="CreateOrderResponseType">
    <xs:sequence>
      <xs:element name="orderId" type="xs:string"/>
      <xs:element name="status" type="xs:string"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="CreateOrderRequest"
              type="ord:CreateOrderRequestType"/>
  <xs:element name="CreateOrderResponse"
              type="ord:CreateOrderResponseType"/>
</xs:schema>
~~~

Hai `complexType` mô tả **kiểu dữ liệu**. Hai `xs:element` global định nghĩa **phần tử gốc** khi XML xuất hiện trong SOAP Body. Do kiểu được khai báo có tên riêng, công cụ JAXB có thể sinh class `CreateOrderRequestType` và `CreateOrderResponseType` cùng các phương thức `ObjectFactory` tạo `JAXBElement` đại diện phần tử global.

Một WSDL 1.1 tương ứng có các phần khái niệm:

~~~xml
<!-- Đây là các đoạn nằm bên trong một WSDL đã khai báo
     các prefix wsdl, soap, tns và schema tương ứng. -->
<wsdl:message name="CreateOrderRequestMessage">
  <wsdl:part name="parameters" element="tns:CreateOrderRequest"/>
</wsdl:message>

<wsdl:message name="CreateOrderResponseMessage">
  <wsdl:part name="parameters" element="tns:CreateOrderResponse"/>
</wsdl:message>

<wsdl:portType name="OrdersPortType">
  <wsdl:operation name="CreateOrder">
    <wsdl:input message="tns:CreateOrderRequestMessage"/>
    <wsdl:output message="tns:CreateOrderResponseMessage"/>
  </wsdl:operation>
</wsdl:portType>

<wsdl:binding name="OrdersSoap11Binding"
              type="tns:OrdersPortType">
  <soap:binding style="document"
                transport="http://schemas.xmlsoap.org/soap/http"/>
  <wsdl:operation name="CreateOrder">
    <soap:operation soapAction="urn:example:orders:v1/CreateOrder"/>
    <wsdl:input><soap:body use="literal"/></wsdl:input>
    <wsdl:output><soap:body use="literal"/></wsdl:output>
  </wsdl:operation>
</wsdl:binding>

<wsdl:service name="OrdersService">
  <wsdl:port name="OrdersSoap11Port"
             binding="tns:OrdersSoap11Binding">
    <soap:address location="https://api.example.test/ws"/>
  </wsdl:port>
</wsdl:service>
~~~

Đây là **đoạn WSDL minh họa**, không phải tài liệu WSDL độc lập: `wsdl:definitions`, `wsdl:types` (hoặc import XSD), các khai báo namespace và định nghĩa khác vẫn cần có trong file thật. Cặp XSD/WSDL chia trách nhiệm như sau:

- `xs:complexType` và `xs:element`: dữ liệu phải có dạng nào, thuộc namespace gì.
- `wsdl:message` và `wsdl:portType`: operation nhận/trả những message nào.
- `wsdl:binding`: dùng SOAP version, transport, style/use và action nào.
- `wsdl:service/wsdl:port/soap:address`: địa chỉ dịch vụ được công bố cho client.

Vì vậy, **đọc riêng XSD không đủ để biết gửi HTTP POST tới URL nào, và chỉ có JAXB DTO không đủ để gọi operation**.

## 3. XJC sinh ra những gì từ XSD?

**XJC** là tên thường dùng của công cụ JAXB schema compiler: lấy XSD và tạo Java source để biểu diễn XML. Ở môi trường hiện đại, công cụ nằm trong bộ tooling/plugin JAXB tương ứng; không mặc định có sẵn trong JDK đang chạy.

Một lệnh minh họa khi đã cài bản `xjc` tương thích, có sẵn thư mục đích và tệp XSD:

~~~text
xjc -d target/generated-sources/jaxb \
    -p com.example.orders.xml \
    src/main/resources/xsd/orders.xsd
~~~

Ký hiệu `\` ở ví dụ trên thể hiện lệnh được ngắt dòng để đọc; cách nối dòng thực tế phụ thuộc shell. Khi tự động hóa build, nên dùng Maven/Gradle plugin để giữ phiên bản JAXB, package và output directory nhất quán, thay vì yêu cầu mọi lập trình viên chạy tay trên máy khác nhau.

Các tệp được sinh có thể gồm:

~~~text
target/generated-sources/jaxb/
└── com/example/orders/xml/
    ├── CreateOrderRequestType.java
    ├── CreateOrderResponseType.java
    ├── ObjectFactory.java
    └── package-info.java
~~~

Tùy kiểu XSD, binding customization và phiên bản generator, class có thể mang tên khác hoặc có thêm annotation, enum, adapter. Không được dùng danh sách tệp ở trên như một quy luật bắt buộc của mọi schema.

### 3.1. Một kiểu JAXB DTO đại diện cho dữ liệu, không phải service

Dạng code rút gọn để giải thích vai trò (không phải output nguyên văn của một phiên bản XJC cụ thể):

~~~java
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlType;
import java.math.BigDecimal;

@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(
    name = "CreateOrderRequestType",
    propOrder = {"clientOrderId", "amount"}
)
public class CreateOrderRequestType {
    protected String clientOrderId;
    protected BigDecimal amount;

    public String getClientOrderId() {
        return clientOrderId;
    }
    public void setClientOrderId(String value) {
        this.clientOrderId = value;
    }
    public BigDecimal getAmount() {
        return amount;
    }
    public void setAmount(BigDecimal value) {
        this.amount = value;
    }
}
~~~

- `@XmlType` mô tả **XML type** và thứ tự phần tử con theo schema.
- `@XmlAccessorType(XmlAccessType.FIELD)` cho JAXB biết cách truy cập dữ liệu để marshal/unmarshal.
- `BigDecimal` phù hợp với kiểu `xs:decimal`; kết quả chính xác còn phụ thuộc mapping và custom bindings.
- Class **không có method `createOrder()` gửi mạng**, không biết địa chỉ `https://api.example.test/ws` và không tự sinh SOAP Envelope.

Sử dụng DTO như một *domain entity* của hệ thống cũng cần cân nhắc. DTO phản ánh contract với đối tác, có thể chứa tên trường, namespace và kiểu số bị ràng buộc bởi schema. Domain model có thể cần bất biến, kiểm tra nghiệp vụ, hoặc mô hình trạng thái khác; có thể có lớp chuyển đổi giữa JAXB DTO và domain model để tránh ràng buộc code nghiệp vụ vào hợp đồng bên ngoài.

### 3.2. `ObjectFactory` và `JAXBElement` để biểu diễn phần tử gốc

Với `xs:complexType` đặt tên `CreateOrderRequestType` và `xs:element` global `CreateOrderRequest`, JAXB generator thường sinh factory và một khai báo element đại diện cho QName. Ví dụ cách dùng minh họa:

~~~java
import java.math.BigDecimal;
import jakarta.xml.bind.JAXBElement;

ObjectFactory factory = new ObjectFactory();

CreateOrderRequestType request =
        factory.createCreateOrderRequestType();
request.setClientOrderId("WEB-20261127-0042");
request.setAmount(new BigDecimal("1250000.00"));

JAXBElement<CreateOrderRequestType> root =
        factory.createCreateOrderRequest(request);
~~~

`request` chứa **giá trị dữ liệu**, còn `root` mang thêm thông tin **XML element name** `{urn:example:orders:v1}CreateOrderRequest`. Khi marshal một class không có `@XmlRootElement`, nhiều trường hợp cần `JAXBElement` để chỉ ra phần tử gốc. Không phải class được sinh nào cũng có `@XmlRootElement`; hãy xem chính xác class và `ObjectFactory` do công cụ tạo.

`package-info.java` thường chứa `@XmlSchema` để khai báo namespace và `elementFormDefault` cho package. Một class có field đúng nhưng đóng sai QName vẫn có thể không phù hợp contract của SOAP client hoặc endpoint.

## 4. `wsimport` sinh mã gì từ WSDL?

**`wsimport`** là tên công cụ quen thuộc của hệ sinh thái JAX-WS dùng đọc WSDL và tạo mã client Java. Nó xử lý **phần dịch vụ** ở WSDL, đồng thời dùng JAXB binding để sinh lớp dữ liệu từ XSD nằm trong hoặc được WSDL tham chiếu. Tùy phiên bản Jakarta XML Web Services hoặc JAX-WS cũ, bộ tooling có thể là chương trình độc lập hoặc plugin build.

Ví dụ ở mức ý tưởng khi đã cài tool tương thích, có thư mục output và có WSDL 1.1 truy cập được:

~~~text
wsimport -keep \
    -s target/generated-sources/jaxws \
    -p com.example.orders.soap \
    https://api.example.test/ws/orders.wsdl
~~~

Lệnh trên được ngắt dòng để dễ đọc; dấu `\` phải được thay bằng cú pháp nối dòng phù hợp với shell. Ví dụ dùng hostname `example.test` giả định và không thể chạy để gọi server thật. Khi tích hợp doanh nghiệp, nên generate client từ **file WSDL/XSD đã kiểm soát phiên bản** hoặc URL hợp đồng đáng tin cậy; không phụ thuộc một endpoint mạng luôn online trong mỗi lần build.

Các thành phần sinh ra có thể tương tự:

~~~text
com/example/orders/soap/
├── OrdersService.java            (JAX-WS service class)
├── OrdersPortType.java           (service endpoint interface)
├── CreateOrderRequestType.java   (JAXB request data)
├── CreateOrderResponseType.java  (JAXB response data)
├── ObjectFactory.java            (JAXB XML element factories)
├── package-info.java
└── ...                            (wrapper, exception hoặc metadata)
~~~

**Không có quy tắc bắt buộc rằng `wsimport` phải tạo một class tên `OrdersProxy`.** JAX-WS thường dùng class `Service` sinh từ WSDL, rồi runtime tạo một **port proxy** tại thời điểm gọi `get...Port()`. Kiểu dữ liệu proxy thực tế có thể là implementation runtime; interface Java của port chính là hợp đồng lập trình mà client sử dụng.

### 4.1. `@WebServiceClient` và port interface là lớp truy cập dịch vụ

Đây là dạng code minh họa của lớp `Service`, lược bỏ phần WSDL metadata và constructor phụ:

~~~java
import jakarta.xml.ws.Service;
import jakarta.xml.ws.WebServiceClient;
import javax.xml.namespace.QName;

@WebServiceClient(
    name = "OrdersService",
    targetNamespace = "urn:example:orders:v1"
)
public class OrdersService extends Service {
    // Constructor va thong tin WSDL do generator quy dinh.

    public OrdersPortType getOrdersSoap11Port() {
        return super.getPort(
            new QName(
                "urn:example:orders:v1",
                "OrdersSoap11Port"
            ),
            OrdersPortType.class
        );
    }
}
~~~

Đây chỉ là **phác họa cấu trúc**, không phải class có thể chạy độc lập: trong thực tế class `Service` cần constructor khởi tạo `super(wsdlLocation, serviceQName)` hoặc thông tin metadata tương ứng. Tên getter và QName cũng tùy file WSDL.

Interface của port thường mang các annotation JAX-WS như:

~~~java
import jakarta.jws.WebMethod;
import jakarta.jws.WebService;
import jakarta.jws.soap.SOAPBinding;

@WebService(
    name = "OrdersPortType",
    targetNamespace = "urn:example:orders:v1"
)
@SOAPBinding(
    parameterStyle = SOAPBinding.ParameterStyle.BARE
)
public interface OrdersPortType {

    @WebMethod(
        operationName = "CreateOrder",
        action = "urn:example:orders:v1/CreateOrder"
    )
    CreateOrderResponseType createOrder(
            CreateOrderRequestType request);
}
~~~

Đoạn trên minh họa **hình thái** một service endpoint interface, không khẳng định `wsimport` sẽ generate chính xác method đó. Với `document/literal` và thiết lập wrapper style, công cụ có thể chọn `BARE`, `WRAPPED` hoặc một chữ ký tham số khác, sinh wrapper classes và annotation `@WebParam`/`@WebResult`; tên Java cũng tùy binding customizations. Để viết code client, phải đọc **interface đã generate thực tế**.

Điểm khác với JAXB DTO: interface `OrdersPortType` biểu diễn **operation** có thể gọi, còn `CreateOrderRequestType` chỉ biểu diễn **tham số dữ liệu** của operation.

### 4.2. Client JAX-WS gọi qua proxy như thế nào?

Ví dụ client sử dụng `Service` và port từ WSDL đã generate:

~~~java
import jakarta.xml.ws.BindingProvider;
import java.math.BigDecimal;

// Ten API/minh hoa phu thuoc ma thuc te do wsimport sinh ra.
OrdersService service = new OrdersService();
OrdersPortType port = service.getOrdersSoap11Port();

BindingProvider binding = (BindingProvider) port;
binding.getRequestContext().put(
    BindingProvider.ENDPOINT_ADDRESS_PROPERTY,
    "https://api.example.test/ws"
);

CreateOrderRequestType request = new CreateOrderRequestType();
request.setClientOrderId("WEB-20261127-0042");
request.setAmount(new BigDecimal("1250000.00"));

CreateOrderResponseType response = port.createOrder(request);
System.out.println(response.getOrderId());
~~~

Trong ví dụ này:

1. `service` cung cấp thông tin WSDL `service/port` và cách tạo proxy.
2. `port` là giao diện gọi operation theo JAX-WS.
3. `request`/`response` vẫn là các lớp **JAXB data**.
4. `BindingProvider.ENDPOINT_ADDRESS_PROPERTY` cho phép chỉ định lại địa chỉ SOAP tại runtime khi port hỗ trợ `BindingProvider`.
5. JAX-WS runtime chuẩn bị SOAP Envelope, gửi HTTP(S), xử lý response và chuyển dữ liệu từ/đến JAXB theo mapping.

**Chú ý:** `OrdersService()` mặc định có thể tìm WSDL tại một URL/resource do code generator đưa vào metadata; nếu file đó không còn ở runtime, khởi tạo proxy có thể thất bại. Việc client override endpoint address không thay thế việc WSDL contract, binding và runtime provider phải khả dụng.

JAX-WS proxy không tự quyết định tất cả vấn đề bảo mật. TLS trust, client certificate, WS-Security policy, token, chữ ký, timeout, proxy networking và handler chain cần cấu hình theo JAX-WS runtime/stack được sử dụng. Một dịch vụ SOAP theo Spring-WS có thể tiếp nhận request từ JAX-WS client nếu hai phía dùng đúng WSDL/binding, SOAPAction, envelope namespace, schema và chính sách bảo mật.

## 5. Spring-WS thường chọn JAXB và `WebServiceTemplate`

Spring-WS cho phép tạo client SOAP **mà không phải dùng proxy JAX-WS**. Thay vì gọi method Java trên interface `@WebService` do `wsimport` sinh, bạn dùng `WebServiceTemplate` để gửi payload và `Jaxb2Marshaller` để chuyển object ↔ XML.

### 5.1. Cấu hình JAXB marshaller và client template

Ví dụ cấu hình Spring Java, giả định package `com.example.orders.xml` chứa các lớp generate từ XSD:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class SoapClientConfig {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.xml");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate ordersWebServiceTemplate(
            Jaxb2Marshaller ordersMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(ordersMarshaller);
        template.setUnmarshaller(ordersMarshaller);
        template.setDefaultUri("https://api.example.test/ws");
        return template;
    }
}
~~~

`setContextPath(...)` trỏ đến **package JAXB** có metadata/factory phù hợp, không trỏ đến URL WSDL hay path file XSD. `setDefaultUri(...)` là địa chỉ SOAP request được gửi đi. Bạn có thể định nghĩa một WSDL bằng bean ở server để publish hợp đồng, nhưng **client `WebServiceTemplate` không tự động đọc WSDL khi mỗi lần gọi**: nó cần biết địa chỉ và payload được marshal theo contract.

Ở trường hợp có nhiều package JAXB hoặc thiếu metadata đủ để tạo `JAXBContext` từ context path, có thể cấu hình `setClassesToBeBound(...)` hoặc `setPackagesToScan(...)` phù hợp với Spring OXM, và nên xác minh bằng test thực tế.

### 5.2. Gửi payload JAXB và nhận kết quả

Giả định `ObjectFactory` được sinh từ schema ở mục 2 và có factory methods tương ứng:

~~~java
import java.math.BigDecimal;
import jakarta.xml.bind.JAXBElement;

ObjectFactory factory = new ObjectFactory();

CreateOrderRequestType payload =
        factory.createCreateOrderRequestType();
payload.setClientOrderId("WEB-20261127-0042");
payload.setAmount(new BigDecimal("1250000.00"));

JAXBElement<CreateOrderRequestType> root =
        factory.createCreateOrderRequest(payload);

Object rawResponse = ordersWebServiceTemplate
        .marshalSendAndReceive(root);

// Ket qua co the la JAXBElement hoac object,
// tuy JAXB mapping va cau hinh.
if (rawResponse instanceof JAXBElement<?> element) {
    Object value = element.getValue();
    if (value instanceof CreateOrderResponseType response) {
        System.out.println(response.getOrderId());
    }
}
~~~

Đây là **minh họa phần gọi** trong class đã được tiêm bean `ordersWebServiceTemplate`; nó không gồm toàn bộ class/import hoặc nghiệp vụ. Dạng trả về có thể là `JAXBElement` hoặc object root trực tiếp tùy schema/`@XmlRootElement`/marshaller. Không ép kiểu mù quáng khi chưa đọc lớp generate và thử unmarshalling.

`marshalSendAndReceive` thực hiện gửi nhận qua các cơ chế Spring-WS message factory/sender, trong khi `Jaxb2Marshaller` chỉ đảm nhiệm **phần nội dung XML**. Nếu hợp đồng yêu cầu SOAPAction, có thể đặt thêm callback:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

Object response = ordersWebServiceTemplate.marshalSendAndReceive(
    root,
    new SoapActionCallback("urn:example:orders:v1/CreateOrder")
);
~~~

Với một số dịch vụ, SOAPAction có thể rỗng/khác ví dụ; phải lấy từ WSDL binding và yêu cầu đối tác. Kết nối HTTPS, timeout, proxy, TLS credentials và WS-Security xử lý ở các lớp message sender/interceptor theo stack hiện tại, không phải do JAXB class tự làm.

### 5.3. Ở Spring-WS server, JAXB request không phải JAX-WS port

Một endpoint có thể định tuyến theo QName phần tử trong SOAP Body:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrdersEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderResponseType create(
            @RequestPayload CreateOrderRequestType request) {
        // Logic nghiep vu va tao response.
        return new CreateOrderResponseType();
    }
}
~~~

Đây là ví dụ **mô tả vai trò** `@Endpoint` và `@PayloadRoot`, chưa phải implementation đầy đủ chạy với schema ở mục 2. Với global element có kiểu `CreateOrderRequestType`, binding như ví dụ thường cần `JAXBElement` hoặc cấu hình JAXB endpoint phù hợp để ánh xạ đúng root; không mặc định mọi `CreateOrderRequestType` gắn `@XmlRootElement`. Dạng tham số/giá trị trả có thể cần đổi thành `JAXBElement<CreateOrderRequestType>` và `JAXBElement<CreateOrderResponseType>` tùy adapter/handler.

**Điểm cốt lõi:** Spring-WS server dùng `@Endpoint`, handler mappings và marshaller; nó **không bắt buộc có interface JAX-WS `OrdersPortType`**. Một JAX-WS client bên ngoài vẫn có thể gọi server này theo hợp đồng SOAP chung.

## 6. Cách nhận diện nhanh khi mở thư mục mã được sinh

Khi được giao một package có hàng chục tệp từ công cụ sinh mã, hãy **đọc annotation và API public** trước khi kết luận file thuộc lớp nào.

| Dấu hiệu | Phân loại thường gặp | Nên kiểm tra gì |
| --- | --- | --- |
| `@XmlType`, `@XmlAccessorType`, các field và getter/setter | JAXB DTO | Tên XML type, namespace, thứ tự element, kiểu Java, nullable. |
| `@XmlRootElement` | JAXB root value | QName root thực tế có khớp SOAP Body/XSD không? |
| `@XmlElementDecl` trong `ObjectFactory` | Factory của JAXB element | QName trong annotation và kiểu `JAXBElement` trả về. |
| `@XmlSchema` trong `package-info.java` | Metadata JAXB package | Target namespace và element form default. |
| `@WebServiceClient`, class kế thừa `jakarta.xml.ws.Service` | JAX-WS service class | WSDL location, `serviceQName`, method `get...Port`. |
| Interface `@WebService` với `@WebMethod` | Service endpoint interface (SEI) | Operation, action, request/response wrappers, binding. |
| `@WebFault` và exception được sinh | JAX-WS fault mapping | Fault name/namespace và kiểu detail. |
| `BindingProvider`, `getRequestContext()` | Runtime JAX-WS client port | Endpoint override, timeout, provider-specific settings. |
| `@Endpoint` + `@PayloadRoot` | Spring-WS server endpoint | QName payload, adapters, handler/interceptor. |
| `WebServiceTemplate` và `Jaxb2Marshaller` | Spring-WS client/serialization | SOAP URI, callback, marshalling, interceptor. |

**Không chỉ dựa vào tên file.** `CreateOrderRequest.java` xuất hiện cả trong output của XJC lẫn phần JAXB mà `wsimport` tạo. Ngược lại, một JAX-WS service class có thể tên `OrdersService` nhưng chứa rất ít logic: hoạt động mạng nằm trong **runtime proxy**.

Một cách đọc cấu trúc call chain là:

~~~text
Client dùng Spring-WS:
  JAXB request → Jaxb2Marshaller → WebServiceTemplate
     → SOAP/HTTP → server @Endpoint
     → JAXB response → client

Client dùng JAX-WS:
  JAXB request → port.createOrder(...) trên proxy
     → JAX-WS runtime → SOAP/HTTP → server
     → JAX-WS runtime → JAXB response
~~~

Hai luồng đều có JAXB DTO. Khác biệt nằm ở **API gọi dịch vụ và runtime quản lý SOAP**, không nằm ở chỗ một bên “có XML” còn bên kia “không có XML”.

## 7. Những lỗi thường gặp khi nhầm JAXB với JAX-WS

### 7.1. Có XJC classes rồi cố gọi `createOrder()`

Sau khi chạy XJC từ XSD, class request chỉ có field/getter/setter, không có địa chỉ endpoint hay operation method. Code như sau là nhầm trách nhiệm:

~~~java
// Khong co API call SOAP tu mot JAXB DTO thong thuong:
CreateOrderRequestType request = new CreateOrderRequestType();
// request.createOrder(); // khong ton tai
~~~

**Cách làm đúng:** nếu dự án sử dụng Spring-WS, cấu hình `WebServiceTemplate`, marshaller và URI; nếu dùng JAX-WS, sinh/khởi tạo `Service` và lấy port từ WSDL.

### 7.2. Thấy `OrdersService` rồi tưởng nó là lớp nghiệp vụ server

JAX-WS `OrdersService` sinh ra ở **client side** chủ yếu giúp tạo proxy tới một endpoint. Nó không phải service nghiệp vụ quản lý đơn hàng trong ứng dụng và cũng không thay thế Spring-WS `@Endpoint`.

Nên phân biệt trong tên và package của dự án, ví dụ:

~~~text
com.example.contract.xml      → JAXB data model
com.example.integrations.soap → client JAX-WS proxy hoặc WebServiceTemplate wrapper
com.example.orders.service    → business service
com.example.orders.endpoint   → Spring-WS @Endpoint
~~~

Tên package chỉ là gợi ý tổ chức; tên thực tế do cấu trúc repo và công cụ sinh mã quy định. Không nên sửa code được sinh bằng tay vì lần regenerate sau có thể ghi đè thay đổi.

### 7.3. JAXB marshal được XML nhưng server trả Fault

Marshal thành công chỉ chứng tỏ thư viện có thể biến một object thành XML, **không chứng minh XML đúng schema hay đúng operation SOAP**. Các nguyên nhân điển hình:

- JAXB root QName sai: element thực tế không phải `{urn:example:orders:v1}CreateOrderRequest`.
- Payload đúng kiểu dữ liệu nhưng sai ràng buộc XSD `enumeration`, `pattern`, `minOccurs` hoặc thứ tự `xs:sequence`.
- SOAP 1.1/1.2 không khớp binding; HTTP `Content-Type`/`SOAPAction` không đúng yêu cầu.
- Endpoint URL khác `soap:address` đang dùng.
- SOAP Header yêu cầu WS-Security, timestamp hoặc chữ ký nhưng client không có.
- Interceptor validation/security chặn request **trước khi vào endpoint**.

Ở JAX-WS client, SOAP Fault có thể trở thành `jakarta.xml.ws.soap.SOAPFaultException` hoặc một checked exception theo WSDL fault mapping. Ở Spring-WS client, một SOAP Fault thường được xử lý qua `SoapFaultClientException` hoặc fault resolver tùy cấu hình. HTTP transport error (DNS, TLS, timeout) lại có thể tạo exception ở tầng khác.

Không nên viết code chỉ bắt một loại exception chung rồi coi tất cả là lỗi nghiệp vụ.

### 7.4. Sử dụng `@XmlRootElement` sai giả định

Với schema có **global element tham chiếu named complexType** như ở mục 2, XJC có thể sinh `CreateOrderRequestType` nhưng **không** gắn `@XmlRootElement`. Nếu gọi:

~~~java
marshaller.marshal(request, outputStream);
~~~

với object không có root element metadata tương ứng, JAXB có thể báo không marshal được như một phần tử gốc. Khi đó dùng factory:

~~~java
JAXBElement<CreateOrderRequestType> root =
    new ObjectFactory().createCreateOrderRequest(request);

marshaller.marshal(root, outputStream);
~~~

Đừng tự thêm `@XmlRootElement` vào file sinh nếu có thể dùng `ObjectFactory` hoặc custom binding hợp lệ: việc tự sửa file generated vừa dễ hỏng ở lần build tiếp theo vừa có thể tạo QName không đúng hợp đồng.

## 8. Chọn công cụ theo mục tiêu thực tế

| Tình huống | Hướng thường phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Chỉ có `orders.xsd` và muốn Java DTO | Dùng **XJC/JAXB schema compiler**. | Chỉ sinh mô hình XML, chưa có SOAP client network. |
| Có WSDL và muốn gọi `port.createOrder(...)` như một method | Dùng **JAX-WS tooling (`wsimport`)** + runtime tương thích. | Sinh service/SEI và JAXB types; phải cấu hình endpoint/security/timeout. |
| Đang triển khai SOAP client trong dự án Spring-WS | Dùng XSD-generated JAXB + **`WebServiceTemplate`/`Jaxb2Marshaller`**. | SOAPAction, endpoint URI, transport/interceptors cấu hình riêng. |
| Đang triển khai Spring-WS server contract-first | XSD → JAXB model, WSDL publication, `@Endpoint`. | Định tuyến bằng `@PayloadRoot`, không đòi hỏi JAX-WS proxy. |
| Hợp đồng WSDL có fault, WS-Addressing/WS-Security policy phức tạp | Chọn stack theo khả năng runtime, policy và đối tác. | Công cụ sinh mã không bảo đảm mọi policy tự được thực thi. |
| Tích hợp nhiều dịch vụ trong cùng ứng dụng | Cân nhắc wrapper client riêng quanh API đã sinh/template. | Tách cấu hình từng endpoint, tránh trộn model namespace và dependency. |

Một hệ thống có thể dùng Spring-WS server và JAX-WS client ở ứng dụng khác vì chuẩn giao tiếp chung là **SOAP + WSDL/XSD**. Điều kiện là cùng hiểu operation/binding, XML QName, phần tử, SOAP Header và chính sách bảo mật; không cần cùng framework Java.

### 8.1. Vì sao không generate cả hai rồi trộn chung một package?

Nếu cùng sinh XJC và `wsimport` vào một package, dễ gặp **duplicate class** như `ObjectFactory`/`CreateOrderRequestType` hoặc xung đột JAXB metadata. Đừng thêm cả hai thư mục generated sources lên classpath nếu chúng tạo cùng class name/full qualified name.

Nếu dự án thật cần cả hai cách gọi, hãy quyết định ownership của **một bộ JAXB model** theo hợp đồng, phân tách package khi phù hợp và xác minh các lớp proxy có dùng đúng cùng kiểu. Công cụ không phải lúc nào hỗ trợ tái sử dụng DTO theo một cách đơn giản; binding customization và schema catalog có thể cần thiết. Tránh tạo hai bộ DTO giống cấu trúc rồi ép cast giữa chúng, vì hai class khác package là hai kiểu Java khác nhau.

### 8.2. Sinh mã tự động hóa trong build

Với Maven/Gradle, cấu hình plugin tương ứng để:

1. Đọc **XSD/WSDL phiên bản đã được kiểm soát**.
2. Chọn đúng phiên bản `javax` hoặc `jakarta` của API và runtime.
3. Đặt output vào `target/generated-sources/...` hoặc `build/generated/...` đúng convention.
4. Đưa generated source directory vào compile source set theo plugin/build tool.
5. Regenerate khi XSD/WSDL thay đổi, kiểm tra diff và compatibility.
6. Chạy kiểm thử marshalling, XSD validation và SOAP integration trước phát hành.

**Không cần chỉnh sửa generated classes trực tiếp.** Khi muốn đổi tên Java class, package, danh sách field hoặc kiểu mapping, ưu tiên chỉnh XSD/WSDL (nếu có quyền sở hữu contract) hoặc tạo binding customization được tool hỗ trợ. Với WSDL của đối tác, thay đổi tùy tiện schema chỉ ở client có thể khiến bản tin gửi không còn khớp hợp đồng.

## 9. `javax` và `jakarta`: tránh trộn API khi chuyển phiên bản

Đây là nguồn lỗi lớn ở các dự án Spring-WS/JAXB nâng cấp hoặc khi dùng công cụ sinh mã không cùng thế hệ với runtime.

| Nhóm API | Hệ cũ | Hệ Jakarta mới |
| --- | --- | --- |
| JAXB annotations | `javax.xml.bind.annotation.*` | `jakarta.xml.bind.annotation.*` |
| JAXB core | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| JAX-WS client | `javax.xml.ws.*` | `jakarta.xml.ws.*` |
| JAX-WS annotations liên quan | `javax.jws.*` | `jakarta.jws.*` |
| XML nền tảng JDK | `javax.xml.namespace.QName`, `javax.xml.parsers.*` | Vẫn là `javax.xml.*` cho những API Java SE này; **không** đổi toàn bộ mọi `javax` thành `jakarta`. |

Với Java 11 trở đi, JAXB và JAX-WS không còn được phát kèm như các module Java EE trong JDK chuẩn; cần cung cấp dependency và tooling phù hợp. Nhiều hệ thống cũ vẫn dùng `javax.xml.bind`/`javax.xml.ws`, còn các runtime Jakarta thế hệ mới dùng `jakarta.xml.bind`/`jakarta.xml.ws`.

Ví dụ một class generated import `javax.xml.bind.annotation.XmlType` thường không thể dùng trực tiếp với một runtime JAXB thế hệ Jakarta 4.x chỉ bằng đổi một dependency ở POM. Có thể phải regenerate source bằng XJC mới, điều chỉnh bindings và dependencies theo phiên bản framework. Ngược lại, code `jakarta.xml.ws.Service` không tự hoạt động nếu project chỉ có runtime JAX-WS cũ của hệ `javax`.

**Chú ý đặc biệt:** `QName` là `javax.xml.namespace.QName` trong API Java SE và vẫn như vậy ngay cả trong ứng dụng dùng Jakarta JAXB/JAX-WS mới. Không thực hiện tìm-thay `javax` → `jakarta` trên toàn bộ source mà không phân biệt package.

### 9.1. Lỗi classpath/runtime thường gặp

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| `ClassNotFoundException: jakarta.xml.bind.JAXBContext` | Thiếu Jakarta XML Binding API hoặc classpath không thống nhất. |
| `JAXBException: Implementation of Jakarta XML Binding-API has not been found` | Có API nhưng thiếu implementation runtime tương thích. |
| `ClassNotFoundException: javax.xml.bind.JAXBContext` | Generated classes/runtime còn dùng `javax` nhưng dependency tương ứng không có. |
| `Provider... not found` khi dùng JAX-WS `Service` | Thiếu JAX-WS runtime/provider phù hợp, dù đã có API. |
| Build sinh code với annotation khác dependency ứng dụng | Tool/plugin và runtime thuộc hai thế hệ `javax/jakarta` khác nhau. |
| `ClassCastException` giữa hai bộ request DTO | Các loại Java trùng cấu trúc nhưng khác package/class loader. |

Tên lỗi thay đổi theo JDK, implementation và phiên bản. Đọc stack trace, dependency tree và import của mã được sinh để khoanh vùng chính xác trước khi sửa.

## 10. Validation, SOAP Fault và security nằm ở đâu?

Để tích hợp ổn định, nên nhìn luồng xử lý ở từng lớp:

~~~mermaid
sequenceDiagram
    participant C as Client code
    participant B as JAXB binding
    participant T as SOAP runtime/template
    participant S as Server SOAP processor
    participant E as Business endpoint
    C->>B: Tạo request data
    B->>T: Marshal XML payload
    T->>S: HTTP(S) + SOAP Envelope
    Note over S: SOAP headers, WS-Security, XSD validation
    S->>E: Dispatch payload nếu hợp lệ
    E-->>S: Response object hoặc lỗi
    S-->>T: SOAP response hoặc Fault
    T->>B: Unmarshal payload
    B-->>C: Object dữ liệu
~~~

**JAXB DTO** chịu trách nhiệm biểu diễn data. **JAX-WS runtime hoặc Spring-WS template** chịu trách nhiệm gửi nhận SOAP. **Server-side SOAP processor/interceptor** và ứng dụng xử lý validation, security và nghiệp vụ theo cấu hình.

- **XSD validation:** JAXB không mặc định bảo đảm toàn bộ `pattern`, `enumeration`, `min/max` trong XSD đã được kiểm tra. Có thể đặt schema trên JAXB marshaller/unmarshaller hoặc dùng `PayloadValidatingInterceptor` trong Spring-WS; thứ tự và kiểu lỗi phụ thuộc pipeline.
- **SOAP Fault:** là cấu trúc protocol để phản hồi lỗi SOAP. Một JAX-WS client có thể ánh xạ fault vào checked exception hoặc `SOAPFaultException`; Spring-WS client có fault resolver và exception riêng. HTTP `500` và SOAP Fault có quan hệ theo binding nhưng không đồng nghĩa mọi lỗi mạng đều là SOAP Fault.
- **XML security:** cấu hình parser/transformer trước XML từ nguồn không tin cậy, hạn chế DTD, external entity, entity expansion và giới hạn resource. Class `@XmlType` tự thân không bảo vệ parser khỏi XXE.
- **WS-Security:** cấu hình header bảo mật, token, timestamp, XML Signature, trust và chứng chỉ ở SOAP runtime/interceptor. `Jaxb2Marshaller` không tự thêm chữ ký số hay UsernameToken chỉ vì DTO có annotation XML.
- **TLS và chứng chỉ:** thuộc transport/security config; không được nhầm với namespace XSD hay thông tin trên `ObjectFactory`. Khi truy vết lỗi chứng chỉ cần phân biệt TLS handshake với kiểm tra chữ ký WS-Security.

Trong Spring-WS, các interceptor như `Wss4jSecurityInterceptor` hoặc interceptor nghiệp vụ có thể tham gia việc xử lý SOAP Header. Trong JAX-WS, WS-Security/WS-Policy support và handler configuration là khả năng cụ thể của runtime, không nên mặc định mọi JAX-WS provider có cùng chức năng hoặc tự bật chính sách WSDL.

## 11. Đọc WSDL để chọn đúng công cụ và kiểm tra kết quả

Khi nhận một WSDL 1.1 từ đối tác, làm theo thứ tự:

1. Mở `wsdl:definitions/wsdl:types` để xác định XSD, `targetNamespace`, phần tử global và các `xs:include`/`xs:import` phải resolve.
2. Mở `wsdl:message` và `wsdl:portType` để biết input/output/fault của operation; những phần này là cơ sở sinh JAX-WS SEI.
3. Mở `wsdl:binding` để biết SOAP 1.1/1.2, `document/literal` hay kiểu khác, SOAPAction, binding chi tiết.
4. Mở `wsdl:service/wsdl:port` và `soap:address` để kiểm tra endpoint URL, nhưng phải nhớ runtime có thể override URL theo môi trường.
5. Nếu muốn Java **data model** cho Spring-WS, ưu tiên JAXB generation từ XSD và dùng marshaller/template.
6. Nếu muốn **method proxy** gọi SOAP theo interface đã generate, chọn JAX-WS tooling và runtime phù hợp với WSDL.
7. Kiểm thử payload XML thực nhận/truyền, namespace, schema và SOAP Fault; không đánh giá thành công chỉ bằng việc compile source được sinh.

WSDL/XSD có thể được công bố động hay tĩnh từ Spring-WS server. Tên bean WSDL quyết định URL GET `orders.wsdl` trong một cấu hình servlet nhất định, còn `soap:address` trong WSDL xác định URL SOAP mà port proxy hoặc template dùng khi gọi. XJC không tự biết địa chỉ này từ một XSD đơn lẻ.

## 12. Bài thực hành: xác định thành phần nào thực sự gọi SOAP

### 12.1. Tình huống A: chỉ sinh JAXB model

Một nhóm phát triển tạo `orders.xsd` như mục 2 và chạy XJC. Trong source xuất hiện:

~~~text
CreateOrderRequestType.java
CreateOrderResponseType.java
ObjectFactory.java
package-info.java
~~~

Nhưng code sau báo lỗi vì không tồn tại method:

~~~java
CreateOrderRequestType request = new CreateOrderRequestType();
// request.getOrdersSoap11Port(); // Loi: DTO khong co API proxy
~~~

**Câu hỏi:** Thiếu điều gì nếu ứng dụng phải gửi SOAP request?

**Đáp án:** cần một **SOAP client runtime/cơ chế gửi nhận**. Trong ứng dụng Spring-WS, dùng `WebServiceTemplate`, `Jaxb2Marshaller`, URI và callback/interceptors theo hợp đồng. Trong ứng dụng JAX-WS, sinh và khởi tạo `Service`/port từ WSDL. Không thể biến một DTO thành network client chỉ bằng đổi tên class.

### 12.2. Tình huống B: sinh JAX-WS client từ WSDL

Công cụ `wsimport` tạo:

~~~text
OrdersService.java
OrdersPortType.java
CreateOrderRequestType.java
CreateOrderResponseType.java
ObjectFactory.java
~~~

**Câu hỏi:** Khi gọi `port.createOrder(request)`, thành phần nào thực sự phát SOAP HTTP request?

**Đáp án:** `port` là **proxy được JAX-WS runtime cung cấp**, còn `OrdersPortType` là interface mô tả operation. Các JAXB classes chỉ là tham số và kết quả dữ liệu. Nếu runtime provider không có trên classpath hoặc cấu hình TLS chưa đúng, lời gọi vẫn thất bại dù toàn bộ class Java compile thành công.

### 12.3. Tình huống C: XSD đổi nhưng JAX-WS proxy không đổi URL

Đối tác thêm element bắt buộc `customerCode` vào `CreateOrderRequestType` nhưng vẫn dùng cùng WSDL service/port URL.

**Câu hỏi:** Có thể chỉ giữ code JAXB cũ vì `OrdersService` vẫn trỏ đúng URL không?

**Đáp án:** không thể mặc định. Hợp đồng payload đã thay đổi; phải kiểm tra tương thích, regenerate DTO/port cần thiết, sửa mapping nghiệp vụ và kiểm thử XSD cả chiều gửi/nhận. Port proxy kết nối đúng máy chủ không bảo đảm XML đúng schema mới.

### 12.4. Tình huống D: XML SOAP đã marshal nhưng endpoint trả lỗi namespace

`ObjectFactory` của một package sinh từ XSD cũ đặt QName `{urn:example:orders:v0}CreateOrderRequest`, còn server `@PayloadRoot` chờ namespace `urn:example:orders:v1`.

**Câu hỏi:** Tại sao serializer vẫn có thể xuất XML nhưng server không chọn đúng endpoint?

**Đáp án:** JAXB đang xuất XML **phù hợp metadata của package cũ**, không phù hợp hợp đồng của server v1. So QName đầy đủ của phần tử trong `soap:Body`, WSDL/XSD và `@PayloadRoot`; regenerate từ contract đúng phiên bản thay vì đổi prefix XML thủ công.

### 12.5. Tình huống E: SOAP Fault vì WS-Security

Một JAX-WS client gọi được port nhưng nhận Fault yêu cầu `wsse:Security`. Nhóm phát triển định thêm `@XmlElement(name="Security")` vào `CreateOrderRequestType`.

**Câu hỏi:** Có đúng tầng xử lý không?

**Đáp án:** không. WS-Security thuộc **SOAP Header** và cơ chế bảo mật thông điệp; DTO request thuộc **SOAP Body** theo XSD. Cần cấu hình WS-Security trên client runtime hoặc interceptor phù hợp với WSDL/policy của đối tác. Đưa một field tên `Security` vào payload nghiệp vụ không tạo ra header SOAP hợp lệ và có thể làm sai contract.

## 13. Kiểm thử nào phân biệt được lỗi JAXB và lỗi proxy?

Nên xây dựng hai nhóm kiểm thử độc lập rồi ghép thành kiểm thử tích hợp.

| Mức kiểm thử | Đầu vào | Điều quan sát | Thành phần đang được kiểm |
| --- | --- | --- | --- |
| Marshal JAXB | Tạo `CreateOrderRequestType` + `JAXBElement` | XML root QName và các element/giá trị đúng. | JAXB annotations, ObjectFactory, context path. |
| Unmarshal JAXB | XML hợp lệ theo contract | Đối tượng Java đúng kiểu/giá trị. | JAXB binding, namespace, kiểu dữ liệu. |
| XSD validation | Payload XML mẫu | Valid/invalid theo facets, thứ tự và required fields. | XSD/schema validator, không phải network client. |
| JAX-WS proxy invocation | Port và SOAP test server | SOAP Envelope, HTTP headers, SOAPAction, response/fault. | JAX-WS runtime + service/port mapping. |
| Spring-WS template invocation | Template và SOAP test server | Payload, destination URI, header, interceptor, response. | `WebServiceTemplate`/`Jaxb2Marshaller`/sender. |
| Integration contract | WSDL/XSD public + server + client | Gọi operation thành công hoặc Fault đúng hợp đồng. | Toàn bộ chuỗi tích hợp. |
| Security compatibility | TLS/WS-Security test material | Header/signature/timestamp/trust được xử lý như thỏa thuận. | Client/server security stack, không phải DTO. |

### 13.1. Test marshalling chỉ dùng JAXB

Nếu có class sinh từ schema ở mục 2, một bài thử đơn giản:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.JAXBElement;
import jakarta.xml.bind.Marshaller;
import java.io.StringWriter;
import java.math.BigDecimal;

ObjectFactory factory = new ObjectFactory();
CreateOrderRequestType request =
        factory.createCreateOrderRequestType();

request.setClientOrderId("WEB-20261127-0042");
request.setAmount(new BigDecimal("1250000.00"));

JAXBElement<CreateOrderRequestType> root =
        factory.createCreateOrderRequest(request);

JAXBContext context = JAXBContext.newInstance(
        "com.example.orders.xml"
);
Marshaller marshaller = context.createMarshaller();
marshaller.setProperty(Marshaller.JAXB_FORMATTED_OUTPUT, true);

StringWriter writer = new StringWriter();
marshaller.marshal(root, writer);
System.out.println(writer);
~~~

Đoạn này giả định generated package chứa `ObjectFactory` và binding tương ứng; nó **không kết nối mạng**. Nếu muốn validation XSD, cấu hình `Schema` qua `marshaller.setSchema(...)` hoặc validate XML riêng bằng JAXP; marshalling bình thường chưa đủ chứng minh tất cả facets đã được kiểm tra.

Vì output là `StringWriter`, khai báo encoding trong XML do marshaller sinh không mô tả một file byte UTF-8 đã được ghi. Khi xuất qua HTTP/file, encoding ở transport/output stream và metadata phải nhất quán; sử dụng `StringWriter` không phải cách xác minh byte trên dây.

### 13.2. Test lời gọi proxy/template ở cấp SOAP

Với môi trường thử nghiệm đáng tin cậy, quan sát **raw SOAP Envelope** và HTTP metadata:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:ord="urn:example:orders:v1">
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Hãy kiểm tra: namespace của `Envelope` (SOAP 1.1), QName payload, text sau XML escaping, `Content-Type` và `SOAPAction` so WSDL, sau đó xem response/Fault. Một lỗi TLS handshake trước HTTP request không phải lỗi JAXB; một lỗi `Invalid XML character` khi marshal lại thường xảy ra trước khi gửi; một SOAP Fault về `MustUnderstand`/security có thể xảy ra sau khi server nhận request nhưng trước endpoint.

Đừng bật log nguyên văn production SOAP chứa thông tin nhận dạng, token hay chữ ký nếu chưa có kiểm soát; thay bằng dữ liệu giả và metadata đã được lọc.

## 14. Checklist khi tích hợp Spring-WS với client JAXB/JAX-WS

| Câu hỏi | Trạng thái đạt |
| --- | --- |
| Đâu là nguồn hợp đồng chính? | Có bản WSDL/XSD đã version và xác nhận với đối tác. |
| Class này có phải DTO? | Chứa binding JAXB (`@XmlType`, `ObjectFactory`, `JAXBElement`), không đảm nhiệm HTTP invocation. |
| Class này có phải JAX-WS service/SEI? | Có `@WebServiceClient`/`Service` hoặc `@WebService`/`@WebMethod` mô tả operation. |
| Client chọn stack nào? | Dùng một cơ chế rõ ràng: Spring-WS template hoặc JAX-WS port. |
| Các dependencies có đồng bộ không? | JAXB và JAX-WS tooling/runtime đúng hệ `javax` hay `jakarta` và đúng phiên bản ứng dụng. |
| QName của request/response? | Namespace URI + local name đúng XSD/WSDL và `@PayloadRoot`. |
| JAXB root được marshal ra sao? | Dùng `@XmlRootElement` hoặc `JAXBElement` theo output generator. |
| Có kiểm tra XSD không? | Bật validation/contract tests khi cần; không nhầm JAXB unmarshal với XSD validation. |
| Port/Template gửi đến đâu? | Đúng SOAP `soap:address` hoặc override URI của môi trường. |
| SOAP binding đúng? | SOAP 1.1/1.2, `Content-Type`, SOAPAction, request/response wrapping phù hợp. |
| Lỗi được xử lý ở đâu? | Phân biệt transport, marshal/unmarshal, schema validation, SOAP Fault, business error. |
| Security có cấu hình riêng? | TLS/trust, WS-Security interceptor/runtime, header/timestamp/chữ ký được thử nghiệm. |
| Generated code được bảo trì thế nào? | Tái sinh từ contract và binding customizations, không sửa tay trong source generated. |

### Ghi nhớ

- **JAXB DTO** được sinh từ cấu trúc XML của XSD: biểu diễn dữ liệu, kiểu và QName; nó **không phải** HTTP/SOAP client.
- **JAX-WS `Service` + port proxy** được sinh từ WSDL cùng các JAXB classes: cung cấp API gọi operation, còn runtime quản lý SOAP/HTTP.
- Với Spring-WS, có thể dùng **XJC-generated JAXB + `Jaxb2Marshaller` + `WebServiceTemplate`** để xây SOAP client mà không cần JAX-WS proxy; server dùng `@Endpoint`/`@PayloadRoot`.
- **`ObjectFactory`/`JAXBElement`** thường xác định root element khi class JAXB không có `@XmlRootElement`. Cần xem output generate thực tế trước khi marshal/cast.
- **`javax` và `jakarta`** phải nhất quán giữa tool, generated classes, runtime; riêng các Java SE API như `javax.xml.namespace.QName` vẫn giữ tên `javax`.
- **SOAP Fault, schema validation, TLS và WS-Security** thuộc các tầng khác nhau; chọn công cụ và chẩn đoán theo tầng giúp tích hợp hợp đồng doanh nghiệp ổn định.




