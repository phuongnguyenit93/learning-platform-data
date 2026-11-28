# DefaultWsdl11Definition và quy ước nhận diện yêu cầu, phản hồi

Trong module **SPRING_WEB_SERVICES**, một dịch vụ SOAP được phát triển theo hướng **contract-first**: định nghĩa các phần tử XML bằng XSD, công bố cách gọi bằng WSDL, ánh xạ dữ liệu bằng JAXB, rồi mới xây dựng endpoint và SOAP client. Ở chương **Đọc và công bố WSDL**, `DefaultWsdl11Definition` là công cụ Spring Web Services (Spring-WS) giúp **tạo WSDL 1.1 từ XSD theo quy ước đặt tên**. Hiểu chính xác cách nó nhận diện `Request` và `Response` giúp tránh lỗi “có XSD nhưng WSDL không có operation”, đồng thời bảo đảm WSDL công bố phản ánh đúng hợp đồng tích hợp doanh nghiệp.

Bài học tập trung vào **quy tắc tạo WSDL** và cách xác minh kết quả, bao gồm quan hệ với `MessageDispatcherServlet`, `@PayloadRoot`, JAXB, SOAP client, SOAP Fault, interceptor, bảo mật XML/WS-Security và kiểm thử tương thích. Các ví dụ dùng Spring-WS 4.x và SOAP 1.1 làm ngữ cảnh; khi dùng bản framework khác, cần kiểm tra API và WSDL được xuất ra thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `DefaultWsdl11Definition` tạo `wsdl:message`, `wsdl:portType`, `wsdl:binding` và `wsdl:service` từ các phần tử XSD theo quy ước.
2. Suy ra operation `GetOrder` từ cặp global elements `GetOrderRequest` và `GetOrderResponse`.
3. Phân biệt **tên bean WSDL**, **tên operation**, **portType**, **service**, **SOAP address** và **QName phần tử payload**.
4. Cấu hình `setSchema`, `setPortTypeName`, `setTargetNamespace`, `setLocationUri`, `setRequestSuffix` và `setResponseSuffix`.
5. Chẩn đoán các lỗi sai hậu tố, sai namespace, thiếu message hoặc WSDL trỏ nhầm endpoint.
6. Quyết định khi nào nên công bố WSDL tĩnh, kiểm thử hợp đồng và bảo vệ việc tích hợp trước thay đổi phiên bản.

## 1. XSD, WSDL và SOAP message có trách nhiệm gì?

Hãy bắt đầu bằng ba câu hỏi khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **XSD (XML Schema)** | Payload XML gồm những phần tử, kiểu, thứ tự và ràng buộc nào? | `GetOrderRequest`, `GetOrderResponse` |
| **WSDL 1.1** | Dịch vụ có thao tác nào, dùng những message nào, SOAP binding và địa chỉ nào? | Operation `GetOrder`, port `OrdersPort` |
| **SOAP Envelope** | Một lần gọi thật sự gửi/nhận dữ liệu gì? | HTTP POST chứa Body với `GetOrderRequest` |

`DefaultWsdl11Definition` làm việc ở **lớp công bố hợp đồng**. Nó đọc các khai báo phần tử trong XSD và tạo một WSDL theo quy ước. Nó **không** tự sinh endpoint Java, không triển khai logic nghiệp vụ và không tự bảo đảm request/response thực tế hợp XSD.

Mô hình tổng quát:

~~~mermaid
flowchart LR
    X["orders.xsd<br/>Global elements"] --> D["DefaultWsdl11Definition"]
    D --> W["orders.wsdl<br/>messages / operations / binding / service"]
    W --> C["SOAP client<br/>đọc hoặc sinh stub theo WSDL"]
    X --> J["JAXB / XJC<br/>kiểu Java"]
    C --> R["SOAP request"]
    R --> E["Spring-WS endpoint<br/>định tuyến theo payload QName"]
    J --> E
    E --> S["SOAP response hoặc SOAP Fault"]
~~~

Hình trên là luồng phụ thuộc và trao đổi ở mức khái niệm. Việc máy khách sinh stub từ WSDL hay sử dụng `WebServiceTemplate` là lựa chọn triển khai; không có nghĩa WSDL được gửi trong từng SOAP message.

## 2. Quy ước mặc định: `Request` và `Response`

`DefaultWsdl11Definition` sử dụng các thành phần nội bộ chuyên xử lý schema, message, portType và SOAP binding. Theo quy ước mặc định, **tên global element trong XSD kết thúc bằng `Request` được nhận là đầu vào**, còn tên kết thúc bằng **`Response` là đầu ra**. Cùng tiền tố tên sẽ hình thành tên thao tác sau khi bỏ hậu tố.

Ví dụ:

| Global element trong XSD | Vai trò theo suffix | Tên operation suy ra |
| --- | --- | --- |
| `GetOrderRequest` | Request | `GetOrder` |
| `GetOrderResponse` | Response | `GetOrder` |
| `CancelOrderRequest` | Request | `CancelOrder` |
| `CancelOrderResponse` | Response | `CancelOrder` |
| `OrderStatus` | Không kết thúc bằng suffix | Không tự tạo operation `OrderStatus` |
| `FindOrderInput` | Không khớp suffix mặc định | Không được nhận là request của `FindOrder` |

Cặp:

~~~text
GetOrderRequest   ──bỏ Request──► GetOrder ──┐
                                               ├── operation GetOrder
GetOrderResponse  ─bỏ Response─► GetOrder ────┘
~~~

**Lưu ý về phạm vi:** cơ chế dựa trên suffix để suy ra operation trong WSDL. Spring-WS khi nhận SOAP request thường định tuyến endpoint theo **QName của phần tử gốc trong SOAP Body** (chẳng hạn `@PayloadRoot`), không dựa vào việc tên method Java là `getOrder`. Hai cơ chế liên quan đến cùng hợp đồng nhưng không thay thế nhau.

### 2.1. Thế nào là `global element`?

Một phần tử ở cấp trực tiếp bên trong `xs:schema` là **global element**:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

  <!-- Đây là global element: có thể làm payload root. -->
  <xs:element name="GetOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <!-- Đây là local element: field của request. -->
        <xs:element name="orderId" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

`GetOrderRequest` là phần tử root mà bộ tạo WSDL có thể dùng làm message. `orderId` là field con trong kiểu của request: tên `orderId` không tạo một operation. Điều quan trọng không chỉ là tên chứa chuỗi `Request` hay `Response`, mà **global element phải tồn tại trong tập schema được cấu hình**.

### 2.2. Thiếu một vế Request hoặc Response

Nếu XSD chỉ có `PingRequest` mà không có `PingResponse`, hoặc có `PingResponse` nhưng thiếu `PingRequest`, bộ tạo WSDL vẫn dựa vào các message nhận diện được để xây operation. **Đừng giả định** nó sẽ tự tạo phần tử còn thiếu hoặc luôn suy ra thao tác request-response đúng kỳ vọng. Với thao tác một chiều, kiểu `portType`/binding có thể khác; phải kiểm tra WSDL đầu ra và yêu cầu tương tác thực tế.

Với một thao tác request-response điển hình, hãy chủ động khai báo **đủ hai global elements** có cùng phần gốc tên rồi xác nhận trong WSDL rằng operation có đúng `input` và `output`.

## 3. Ví dụ hợp đồng XSD với hai thao tác

Ta xây dựng hợp đồng tra cứu và hủy đơn hàng. File minh họa `src/main/resources/orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

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
        <xs:element name="orderId" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="state" type="ord:OrderStateType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="CancelOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="reason" type="xs:string" minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="CancelOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="state" type="ord:OrderStateType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

Từ XSD trên, các phần tử root có QName:

~~~text
{urn:example:orders:v1}GetOrderRequest
{urn:example:orders:v1}GetOrderResponse
{urn:example:orders:v1}CancelOrderRequest
{urn:example:orders:v1}CancelOrderResponse
~~~

Vì `elementFormDefault="qualified"`, các phần tử con như `orderId`, `state`, `reason` cũng thuộc namespace hợp đồng. Tiền tố XML như `ord` chỉ là bí danh: đổi thành `o` vẫn cùng QName nếu URI không đổi.

Từ hai cặp suffix, WSDL được kỳ vọng cung cấp hai operation logic: **`GetOrder`** và **`CancelOrder`**. Trạng thái `SHIPPED` của đơn hàng có thể là lý do nghiệp vụ để từ chối hủy; XSD không tự xác nhận tính hợp lệ của hành động đó.

## 4. Cấu hình `DefaultWsdl11Definition` trong Spring-WS

Trong ứng dụng Spring Boot với các dependency Spring Web Services phù hợp, có thể khai báo `MessageDispatcherServlet` và bean WSDL như sau. Đoạn mã minh họa theo API Spring-WS 4.x:

~~~java
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class OrderSoapConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
    messageDispatcherServlet(ApplicationContext context) {
        MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition wsdl =
            new DefaultWsdl11Definition();

        wsdl.setPortTypeName("OrdersPort");
        wsdl.setServiceName("OrdersService");
        wsdl.setTargetNamespace("urn:example:orders:v1");
        wsdl.setLocationUri("/ws");
        wsdl.setSchema(ordersSchema);

        // Ghi rõ quy ước mặc định để thấy cơ chế.
        wsdl.setRequestSuffix("Request");
        wsdl.setResponseSuffix("Response");

        // SOAP 1.1 là binding mặc định.
        wsdl.setCreateSoap11Binding(true);
        wsdl.setCreateSoap12Binding(false);
        return wsdl;
    }
}
~~~

Giả sử ứng dụng chạy tại `http://localhost:8080` với servlet context path rỗng:

- `GET http://localhost:8080/ws/orders.wsdl` tải tài liệu WSDL.
- `POST http://localhost:8080/ws` là lời gọi SOAP nghiệp vụ trong ví dụ.
- `orders.xsd` phải tồn tại trên classpath.
- Địa chỉ `/ws` được khai báo ở `setLocationUri` để tạo SOAP address; khi bật `setTransformWsdlLocations(true)`, Spring-WS có thể biến đổi địa chỉ thành URL phù hợp với request GET WSDL.

Host, port, context path và địa chỉ hiển thị có thể thay đổi theo môi trường. Khi triển khai sau reverse proxy/gateway, **phải mở WSDL từ chính tuyến truy cập của client bên ngoài** để kiểm tra `soap:address`, scheme HTTPS, path và chính sách forwarded headers/proxy. Bật `transformWsdlLocations` không tự giải quyết mọi sai lệch cấu hình proxy.

### 4.1. Mỗi thuộc tính cấu hình có vai trò riêng

| Cấu hình | Vai trò | Ví dụ |
| --- | --- | --- |
| `@Bean(name="orders")` | Xác định tên tài nguyên WSDL được servlet công bố | `orders.wsdl` |
| `setSchema(...)` | Cung cấp XSD để lấy định nghĩa các phần tử | `orders.xsd` |
| `setSchemaCollection(...)` | Cung cấp nhiều XSD khi hợp đồng cần collection/import/include | Schema collection đã cấu hình |
| `setPortTypeName(...)` | Đặt tên giao diện WSDL logic | `OrdersPort` |
| `setServiceName(...)` | Đặt tên `wsdl:service`; nếu không đặt, tên thường dựa trên portType + `Service` | `OrdersService` |
| `setTargetNamespace(...)` | Namespace của định nghĩa WSDL | `urn:example:orders:v1` |
| `setLocationUri(...)` | Địa chỉ đưa vào `soap:address` | `/ws` |
| `setRequestSuffix(...)` | Nhận diện message đầu vào và tên thao tác | `Request` |
| `setResponseSuffix(...)` | Nhận diện message đầu ra và tên thao tác | `Response` |
| `setFaultSuffix(...)` | Quy tắc tên cho fault message, khi áp dụng | `Fault` |
| `setCreateSoap11Binding(...)` | Sinh SOAP 1.1 binding | `true` |
| `setCreateSoap12Binding(...)` | Sinh SOAP 1.2 binding | `false` |

Theo API Spring-WS 4.x, SOAP 1.1 binding mặc định bật, SOAP 1.2 binding mặc định tắt; `setTransportUri` mặc định transport HTTP. Nếu bật SOAP 1.2, cần kiểm tra thêm media type, namespace Envelope, Fault và cấu hình message factory/client, không chỉ bật một boolean.

**Phân biệt `portTypeName` và bean name:** `OrdersPort` là tên giao diện logic bên trong WSDL, còn `orders` trong `@Bean(name="orders")` quyết định đường dẫn `orders.wsdl`. Hai tên phục vụ mục đích khác nhau. Thay bean name có thể đổi URL tải WSDL mà không đổi QName operation; thay portTypeName có thể ảnh hưởng stub client sinh từ WSDL.

### 4.2. Lưu ý về `soapAction`

Với SOAP 1.1 trên HTTP, một số đối tác yêu cầu `SOAPAction` cụ thể. `DefaultWsdl11Definition` hỗ trợ `setSoapActions(Properties)`, trong đó key là **tên operation trong binding**, còn value là SOAP Action URI:

~~~java
Properties actions = new Properties();
actions.setProperty("GetOrder", "urn:example:orders:v1:GetOrder");
actions.setProperty("CancelOrder", "urn:example:orders:v1:CancelOrder");

wsdl.setSoapActions(actions);
~~~

Đây là đoạn bổ sung minh họa đặt **trước `return wsdl;`** trong bean ở trên, không phải một chương trình độc lập. Nếu client gửi `SOAPAction`, cần kiểm tra cả header HTTP và annotation/mapping của endpoint nếu ứng dụng chọn định tuyến dựa vào `@SoapAction`. Việc **WSDL khai báo SOAPAction** không đồng nghĩa rằng endpoint được định tuyến theo SOAPAction; ví dụ phía server có thể dùng `@PayloadRoot`.

## 5. WSDL sinh ra có hình dạng nào?

WSDL 1.1 gồm các phần thường gặp:

| Phần WSDL | Vai trò khi đọc hợp đồng | Liên hệ với ví dụ |
| --- | --- | --- |
| `wsdl:types` | Chứa/nhập XSD | Bốn global elements từ `orders.xsd` |
| `wsdl:message` | Gắn tên message với phần tử XML | `GetOrderRequest` và `GetOrderResponse` |
| `wsdl:portType` | Liệt kê operation logic và input/output/fault | `GetOrder`, `CancelOrder` |
| `wsdl:binding` | Gắn portType với SOAP version/style/transport/action | Document/literal SOAP 1.1 |
| `wsdl:service` và `wsdl:port` | Công bố điểm truy cập cụ thể | `OrdersService` và `soap:address` |

Một đoạn WSDL 1.1 **rút gọn để học cách đọc**, không phải bản xuất nguyên văn hay tài liệu độc lập hoàn chỉnh:

~~~xml
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1">

  <!-- wsdl:types chứa schema minh họa ở mục 3. -->

  <wsdl:message name="GetOrderRequest">
    <wsdl:part name="parameters"
               element="ord:GetOrderRequest"/>
  </wsdl:message>
  <wsdl:message name="GetOrderResponse">
    <wsdl:part name="parameters"
               element="ord:GetOrderResponse"/>
  </wsdl:message>

  <wsdl:portType name="OrdersPort">
    <wsdl:operation name="GetOrder">
      <wsdl:input message="ord:GetOrderRequest"/>
      <wsdl:output message="ord:GetOrderResponse"/>
    </wsdl:operation>
    <!-- Operation CancelOrder tương tự. -->
  </wsdl:portType>

  <wsdl:binding name="OrdersPortSoap11"
                type="ord:OrdersPort">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
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
  </wsdl:binding>

  <wsdl:service name="OrdersService">
    <wsdl:port name="OrdersPortSoap11"
               binding="ord:OrdersPortSoap11">
      <soap:address location="http://localhost:8080/ws"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
~~~

Đoạn trên được viết để giải thích quan hệ giữa các phần. **Tên binding/port cụ thể, thứ tự và namespace prefix do công cụ sinh có thể khác**; không suy đoán thay kết quả thật. Muốn biết chính xác client sẽ sinh stub gì, hãy tải `orders.wsdl` từ dịch vụ và kiểm tra nó bằng công cụ WSDL/SoapUI hoặc client generator mục tiêu.

### 5.1. Đọc WSDL theo thứ tự nào?

Đối với một operation `GetOrder`:

1. Tìm `wsdl:portType/wsdl:operation[@name='GetOrder']` để xác định `input`, `output`, và fault nếu được khai báo.
2. Tra QName `message` trong `wsdl:input`/`wsdl:output` về `wsdl:message`.
3. Theo `wsdl:part/@element` về global element trong `wsdl:types`/XSD: đây là hình dạng XML ở SOAP Body.
4. Xem `wsdl:binding` để xác định SOAP version, document/literal, `soapAction` và transport.
5. Xem `wsdl:service/wsdl:port/soap:address` để biết URL gọi thật.

Luồng tra cứu:

~~~mermaid
flowchart TD
    O["wsdl:portType<br/>GetOrder operation"] --> I["wsdl:input / wsdl:output"]
    I --> M["wsdl:message<br/>GetOrderRequest / GetOrderResponse"]
    M --> P["wsdl:part/@element"]
    P --> X["Global XSD element<br/>QName + cấu trúc field"]
    O --> B["wsdl:binding<br/>SOAP version / action / style"]
    B --> S["wsdl:service / port<br/>soap:address"]
~~~

Những tên `wsdl:message` và `wsdl:operation` trong WSDL thuộc **namespace của WSDL definition**; còn `wsdl:part/@element` trỏ tới phần tử có QName trong **namespace dữ liệu XSD**. Trong ví dụ hai namespace URI được đặt giống nhau cho đơn giản, nhưng về mặt khái niệm vẫn là hai vai trò khác nhau.

## 6. SOAP request/response tương ứng với operation

Một lời gọi thực tế cho `GetOrder` với SOAP 1.1:

~~~http
POST /ws HTTP/1.1
Host: localhost:8080
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1:GetOrder"
~~~

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-42</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Phản hồi:

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

`SOAPAction` phía trên chỉ là ví dụ cho cấu hình `setSoapActions` ở mục 4.2. Nếu không khai báo SOAPAction tương ứng trong WSDL, client có thể có cách xử lý header khác, tùy công cụ. SOAP 1.2 dùng Envelope namespace và HTTP media type khác.

### 6.1. Endpoint mapping vẫn dựa trên payload root

Ví dụ Spring-WS sau đây dùng `@PayloadRoot`:

~~~java
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
        OrderData order = service.requireOrder(request.getOrderId());

        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(order.id());
        response.setState(order.state());
        return response;
    }
}
~~~

`OrderService` và `OrderData` là các abstraction nghiệp vụ minh họa. Code giả định lớp JAXB sinh từ XSD có getter/setter và được cấu hình marshaller phù hợp; tùy XSD/XJC, có trường hợp cần dùng `JAXBElement` thay vì truyền trực tiếp class root. Trong Spring Boot 3+/Spring-WS 4.x, JAXB thuộc hệ `jakarta.xml.bind`, còn nhiều dự án cũ dùng `javax.xml.bind`.

**Sự khác biệt cần nhớ:** `DefaultWsdl11Definition` nhìn **tên global element** để sinh **operation trong WSDL**; `@PayloadRoot` nhìn **namespace URI + local name** của root payload thực tế để chọn **phương thức endpoint**. Nếu WSDL có `GetOrder` nhưng endpoint chỉ lắng nghe `LookupOrderRequest`, việc tải WSDL thành công không làm lời gọi `GetOrder` tự hoạt động.

## 7. Tùy chỉnh quy ước `Request`/`Response`

Một số đối tác dùng hậu tố khác, ví dụ:

~~~xml
<xs:element name="FindOrderIn">
  <!-- kiểu request ... -->
</xs:element>

<xs:element name="FindOrderOut">
  <!-- kiểu response ... -->
</xs:element>
~~~

Khi đó `DefaultWsdl11Definition` với hậu tố mặc định `Request`/`Response` **không tự hiểu** `FindOrderIn` là request và `FindOrderOut` là response. Có thể cấu hình:

~~~java
wsdl.setRequestSuffix("In");
wsdl.setResponseSuffix("Out");
~~~

và kiểm tra WSDL để bảo đảm operation `FindOrder` có đúng hai message. Nếu vẫn dùng `@PayloadRoot`, endpoint phải định tuyến `localPart="FindOrderIn"`, chứ không phải `FindOrderRequest`.

Quy tắc tùy chỉnh suffix phải được xem là **quyết định của toàn bộ tập schema mà bean đang dùng**. Nếu cùng một schema trộn `GetOrderRequest` với `FindOrderIn` nhưng bean chỉ có một bộ suffix, việc nhận diện các operation sẽ không đồng nhất. Nên thống nhất tên global elements trước khi xuất WSDL; không tùy chỉnh để “chữa cháy” một phần schema mà bỏ qua các operation khác.

### 7.1. Có nên đặt tên request là `RequestGetOrder`?

Theo quy ước mặc định, `RequestGetOrder` **không kết thúc bằng** `Request`, vì vậy nó không được nhận diện như `GetOrderRequest`. Tương tự, `GetOrderReply` không khớp hậu tố `Response`. Có hai hướng:

- **Chuẩn hóa XSD** để dùng `GetOrderRequest` / `GetOrderResponse`, đặc biệt khi hợp đồng còn đang thiết kế.
- **Cấu hình suffix khác** nếu bộ tên mới nhất quán và thực sự kết thúc bằng hậu tố chung, hoặc dùng WSDL tĩnh/thiết kế tùy chỉnh nếu hợp đồng của đối tác phức tạp hơn quy tắc suffix.

`DefaultWsdl11Definition` không phải công cụ tự suy luận từ nội dung field rằng một phần tử “có vẻ là request”. Nó nhận diện theo tên phần tử đã được schema cung cấp.

## 8. Trường hợp Fault: không chỉ cần hậu tố `Fault`

API `DefaultWsdl11Definition` có `setFaultSuffix(String)`. Điều này phục vụ quy ước nhận diện message fault trong quá trình dựng WSDL. Tuy nhiên, **SOAP Fault khi runtime xảy ra** còn cần luồng xử lý exception, fault resolver và hợp đồng fault detail thích hợp.

Ví dụ các tình huống lỗi của `GetOrder`:

| Tình huống | Nơi quyết định | Điều cần có |
| --- | --- | --- |
| Thiếu `orderId` hoặc XML sai XSD | Schema validation/interceptor | Từ chối request, tạo SOAP Fault phù hợp |
| Mã đơn không tồn tại | `OrderService` | Mapping exception sang fault code/detail |
| Người gọi không có quyền | Xác thực/ủy quyền | Không xử lý nghiệp vụ, trả lỗi theo chính sách |
| Chữ ký WS-Security sai | Thành phần bảo mật | Từ chối trước khi tin payload |
| Cơ sở dữ liệu tạm thời lỗi | Nghiệp vụ/hạ tầng | Fault server, chính sách retry rõ ràng |

Chỉ thêm một phần tử `GetOrderFault` vào XSD hoặc đổi `faultSuffix` **không tự thiết lập** cách chuyển `OrderNotFoundException` thành SOAP Fault hợp đồng. Nếu đối tác yêu cầu WSDL fault được mô tả tường minh, cần xem **WSDL thật** có message/fault/binding phù hợp hay không và xác minh Spring-WS tạo fault runtime đúng thiết kế. Với những ràng buộc đặc biệt hoặc WSDL đã ký duyệt, WSDL tĩnh thường kiểm soát hợp đồng tốt hơn.

## 9. Sinh WSDL động hay công bố WSDL tĩnh?

`DefaultWsdl11Definition` thuận tiện cho lúc bắt đầu triển khai contract-first. Nhưng **WSDL là tài liệu giao tiếp công khai**, có thể được các đối tác dùng để sinh mã client và lưu vào môi trường của họ. Một thay đổi nhỏ ở WSDL sinh động có thể khiến mã client khác.

| Lựa chọn | Ưu điểm | Rủi ro/cách dùng |
| --- | --- | --- |
| **WSDL động**: `DefaultWsdl11Definition` | Dễ thử nghiệm XSD và xem operation được suy ra; giảm thao tác tự viết WSDL | Có phụ thuộc quy ước và cơ chế sinh của framework; phải kiểm tra WSDL sau mỗi thay đổi |
| **WSDL tĩnh**: `SimpleWsdl11Definition` | Chủ động kiểm soát chính xác tài liệu giao cho đối tác; thuận lợi versioning và review diff | Cần quản lý tài liệu và bảo đảm endpoint/XML triển khai thực tế đúng WSDL đã chốt |

Tài liệu tham khảo chính thức của Spring-WS khuyến nghị cân nhắc **sinh WSDL lúc phát triển, sau đó lưu lại và công bố tĩnh** để tránh thay đổi ngoài ý muốn khi nâng framework hoặc thay cấu hình. Một bean công bố WSDL đã lưu trong `src/main/resources/orders.wsdl`:

~~~java
@Bean(name = "orders")
public SimpleWsdl11Definition ordersWsdl() {
    return new SimpleWsdl11Definition(
        new ClassPathResource("orders.wsdl"));
}
~~~

Đây là phương án **thay thế bean `DefaultWsdl11Definition` có cùng tên**, không được khai báo đồng thời hai bean `orders`. `SimpleWsdl11Definition` thuộc package `org.springframework.ws.wsdl.wsdl11`. Khi công bố WSDL tĩnh có `xsd:import` hoặc `wsdl:import`, cần bảo đảm các URL/tài nguyên tham chiếu cũng truy cập được hoặc được đóng gói theo chính sách hợp đồng.

### 9.1. Quy trình chốt WSDL

1. Thiết kế và review XSD: QName, request/response, kiểu, `minOccurs/maxOccurs`, dữ liệu lỗi.
2. Dùng `DefaultWsdl11Definition` sinh `orders.wsdl` trong môi trường phát triển.
3. Mở chính URL WSDL đã công bố và kiểm tra `types`, `portType`, `binding`, `service`, `soap:address`, SOAPAction.
4. Sinh thử SOAP client theo các nền tảng dự kiến; chạy request/response XML với server mẫu.
5. Khi WSDL được đối tác xác nhận, lưu phiên bản WSDL cố định và công bố theo cách kiểm soát được thay đổi.
6. Mỗi lần sửa hợp đồng phải có diff, đánh giá tương thích và kiểm thử cả client cũ/server mới nếu còn hỗ trợ phiên bản cũ.

Đừng chỉ so sánh file XSD. Một thay đổi ở tên service, portType, binding hay địa chỉ endpoint dù XSD không đổi cũng có thể ảnh hưởng client.

## 10. Lỗi thường gặp khi WSDL không nhận đúng operation

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xác minh |
| --- | --- | --- |
| Mở `orders.wsdl` được nhưng không thấy `GetOrder` | Tên global elements không kết thúc bằng suffix, hoặc schema cấu hình không chứa phần tử | Đọc XSD được bean sử dụng; kiểm tra `Request`/`Response` |
| Có `GetOrderRequest`, không có output | Thiếu `GetOrderResponse` hoặc tên không cùng phần gốc | Đọc `wsdl:portType` thực tế |
| `GET /ws/orders.wsdl` trả 404 | Bean `orders` không trong context servlet, mapping hoặc URL sai | Kiểm tra `MessageDispatcherServlet`, bean name, context path |
| WSDL có operation nhưng SOAP POST không vào endpoint | QName payload không khớp `@PayloadRoot`, mapping servlet sai | Ghi nhận localPart/namespace URI của SOAP Body |
| `soap:address` trỏ localhost khi gọi từ ngoài | `locationUri` hoặc proxy/forwarded headers chưa đúng | Đọc WSDL qua tuyến public; kiểm tra HTTPS/host/path |
| Client báo binding/protocol không hợp lệ | SOAP 1.1 vs SOAP 1.2, action/transport lệch | Đọc `wsdl:binding`, HTTP Content-Type, SOAP Envelope |
| Client sinh stub từ WSDL nhưng marshal sai XML | Namespace, thứ tự phần tử, JAXB binding hay schema version lệch | So XML wire với XSD/WSDL |
| WSDL mới làm client cũ không gọi được | Operation, service/port, enum, namespace, field thay đổi | Diff WSDL/XSD và test tương thích |
| WSDL công bố thiếu schema phụ | XSD import/include hoặc schema collection không được xử lý đúng | Kiểm tra `types` và URL import thực tế |
| Có tên `OrderFault` nhưng lỗi trả không đúng contract | Exception resolver/WS-Security fault handling khác WSDL | Gửi request lỗi và so fault code/detail với hợp đồng |

### 10.1. Phân biệt bốn điểm rất dễ nhầm

- **Đường dẫn tải WSDL:** URL GET thường kết thúc bằng `.wsdl` và gắn với bean name.
- **Địa chỉ gọi SOAP:** URL POST trong `soap:address`, ví dụ `/ws`.
- **Tên operation:** phần chung được suy ra từ `GetOrderRequest` và `GetOrderResponse`, ví dụ `GetOrder`.
- **Tên phần tử XML trên đường truyền:** root thực tế trong SOAP Body, ví dụ `{urn:example:orders:v1}GetOrderRequest`.

Trong Spring-WS, WSDL công bố đẹp nhưng SOAP Body sai QName vẫn là yêu cầu không khớp endpoint. Ngược lại, endpoint có thể trả lời SOAP request trong một số cấu hình dù WSDL công bố thiếu operation; đó không phải tình trạng tích hợp đáng tin cậy.

## 11. Ma trận kiểm thử hợp đồng và khả năng tương thích

| Ca kiểm thử | Kết quả mong đợi | Nơi kiểm tra |
| --- | --- | --- |
| XSD có `GetOrderRequest` + `GetOrderResponse` | WSDL chứa `GetOrder` với input/output đúng | WSDL `portType` |
| XSD có `CancelOrderRequest` + `CancelOrderResponse` | WSDL chứa `CancelOrder` | WSDL `portType` |
| Đổi `GetOrderResponse` thành `GetOrderReply` mà giữ suffix mặc định | Operation không còn output như hợp đồng mong đợi | WSDL diff; test fail có chủ đích |
| Đổi suffix thành `In`/`Out` cho schema phù hợp | Operation được suy ra đúng phần gốc | WSDL `portType` |
| Đổi prefix XML `ord` nhưng giữ URI | Payload vẫn cùng QName | XSD và SOAP test |
| Đổi namespace URI sang `urn:example:orders:v2` | Endpoint/schema v1 không tự nhận v2 | Mapping + version test |
| GET WSDL từ reverse proxy HTTPS | `soap:address` là URL client truy cập được | Kiểm tra WSDL ngoài hạ tầng |
| POST `GetOrderRequest` hợp XSD | Đúng endpoint, response hợp XSD | `MockWebServiceClient` |
| POST thiếu `orderId` | Bị từ chối nếu bật XSD validation | Interceptor + SOAP Fault |
| Order không tồn tại | SOAP Fault nghiệp vụ như đã thỏa thuận | Exception resolver + client test |
| Client gửi SOAPAction khác chính sách | Hành vi nhất quán với binding/mapping đã cấu hình | HTTP + endpoint test |
| Client sinh từ WSDL cũ gọi server mới | Chỉ thay đổi trong phạm vi tương thích đã cam kết | Kiểm thử xuyên phiên bản |
| WS-Security sai timestamp/chữ ký | Từ chối dù XML Body hợp XSD | Security interceptor test |
| TLS server certificate không được tin cậy | Kết nối bị từ chối theo chính sách | Test truststore/hostname |

Có thể dùng `MockWebServiceClient` để kiểm tra phía server và `MockWebServiceServer` để kiểm tra SOAP client sử dụng `WebServiceTemplate`; thêm kiểm thử XSD, SOAP Fault và bảo mật trong môi trường tích hợp. Các test chỉ kiểm tra object Java là chưa đủ: client khác ngôn ngữ tiêu thụ **WSDL và SOAP XML**, không tiêu thụ class Java.

### 11.1. Các kiểm tra bảo mật đi kèm WSDL

WSDL cho biết binding, địa chỉ và cấu trúc dữ liệu; nó không tự xác minh tính bảo mật của một thông điệp. Trong môi trường doanh nghiệp:

- **HTTPS/TLS:** kiểm tra CA, hostname, hạn chứng chỉ, chính sách mTLS nếu dùng; URL công bố trong WSDL nên phù hợp tuyến kết nối hợp lệ.
- **WS-Security:** dùng thư viện/interceptor chuyên trách như WSS4J để xác minh timestamp, token, chữ ký XML hoặc mã hóa theo chính sách; không coi việc có thẻ `Security` là đã xác thực.
- **XML security:** chặn XXE/DTD bên ngoài ở parser phù hợp, giới hạn kích thước SOAP, độ sâu XML và tài nguyên xử lý.
- **Schema validation:** kiểm tra request/response theo XSD nhưng vẫn phải xác thực quyền và quy tắc nghiệp vụ riêng.
- **Fault/logging:** không đưa token, thông tin chứng chỉ nhạy cảm, private key, stack trace hay payload nhạy cảm vào WSDL, SOAP Fault hoặc log.

Nếu WSDL được sinh tự động, thay đổi schema hoặc binding cần được review cả về **bề mặt tấn công** và **tương thích**, đặc biệt khi thêm operation có tác dụng phụ.

## 12. Bài tập thực hành

**Bài 1 — Suy luận operation.** Cho XSD có global elements: `CreateInvoiceRequest`, `CreateInvoiceResponse`, `GetInvoiceRequest`, `GetInvoiceResult`, `InvoiceStatus`. Với suffix mặc định, operation nào có cặp input/output đầy đủ? Thay đổi nhỏ nhất nào giúp `GetInvoice` có response đúng quy ước?

**Bài 2 — Đọc WSDL.** Với một `wsdl:portType` có `GetOrder`, hãy lần từ `wsdl:input/@message` đến `wsdl:message/wsdl:part/@element`, rồi xác định QName của phần tử cần có trong SOAP Body. Vì sao tên operation không nhất thiết trùng tên element?

**Bài 3 — Tùy chỉnh suffix.** Một đối tác chỉ công bố `QueryOrderIn` và `QueryOrderOut`. Viết hai dòng Java thay đổi suffix. Sau đó nêu vị trí cần sửa ở endpoint nếu sử dụng `@PayloadRoot`.

**Bài 4 — Deployment.** Ứng dụng chạy trong container nội bộ `http://orders:8080/ws` nhưng public URL là `https://api.example.com/order-soap`. Làm sao kiểm tra người dùng bên ngoài đọc WSDL và gọi được `soap:address`? Những cấu hình nào liên quan?

**Bài 5 — Hợp đồng lâu dài.** Tại sao việc đổi `OrdersPort` thành `OrdersPortV2` có thể ảnh hưởng client đã sinh stub, dù XSD request/response không thay đổi? Khi nào nên chuyển từ WSDL động sang WSDL tĩnh?

### Gợi ý đáp án ngắn

1. `CreateInvoice` có đủ cặp `Request`/`Response`; `GetInvoiceResult` cần đổi tên thành `GetInvoiceResponse` nếu giữ suffix mặc định.
2. Operation là khái niệm thao tác WSDL, còn `part/@element` dẫn tới phần tử XML có QName trong XSD.
3. `setRequestSuffix("In")` và `setResponseSuffix("Out")`; endpoint phải khớp `QueryOrderIn` cùng namespace.
4. Tải WSDL qua public URL, kiểm tra `soap:address` HTTPS và path thật; điều chỉnh `locationUri`, location transformation, reverse proxy và forwarded headers.
5. Tên portType là một phần API WSDL mà client generator có thể sử dụng; WSDL tĩnh giúp khóa tài liệu hợp đồng sau khi đối tác đã chấp thuận.

## Tài liệu tham khảo

- [Spring Web Services Reference — Publishing the WSDL](https://docs.spring.io/spring-ws/docs/4.0.17/reference/html/) — cơ chế công bố WSDL động/tĩnh, servlet và quy ước hậu tố.
- [Spring-WS API — DefaultWsdl11Definition](https://docs.spring.io/spring-ws/docs/4.0.17/api/org/springframework/ws/wsdl/wsdl11/DefaultWsdl11Definition.html) — constructor và các setter cấu hình.
- [Spring-WS API — SuffixBasedPortTypesProvider](https://docs.spring.io/spring-ws/docs/4.1.x-SNAPSHOT/api/org/springframework/ws/wsdl/wsdl11/provider/SuffixBasedPortTypesProvider.html) — nhận diện input/output/fault message theo suffix.
- [Spring-WS API — SimpleWsdl11Definition](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/wsdl/wsdl11/SimpleWsdl11Definition.html) — công bố WSDL tĩnh.

**Ghi nhớ:** `DefaultWsdl11Definition` **suy ra WSDL operation từ quy ước tên global elements trong XSD**, phổ biến là `*Request` và `*Response`. Muốn tích hợp SOAP ổn định, hãy đọc WSDL được công bố thật, kiểm tra operation → message → XSD QName → SOAP binding/address, rồi đối chiếu với endpoint Spring-WS, JAXB/SOAP client, SOAP Fault và yêu cầu bảo mật của đối tác.
