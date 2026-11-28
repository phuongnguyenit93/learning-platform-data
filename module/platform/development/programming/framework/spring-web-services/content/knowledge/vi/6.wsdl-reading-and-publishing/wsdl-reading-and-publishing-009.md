# Tên bean, URL WSDL và đường dẫn tài nguyên schema

Trong hệ thống SOAP xây dựng **contract-first** với **Spring Web Services (Spring-WS)**, XSD mô tả dữ liệu yêu cầu/phản hồi, WSDL mô tả cách truy cập dịch vụ, còn `MessageDispatcherServlet` tiếp nhận yêu cầu HTTP. Một endpoint Java có thể chạy bình thường nhưng client vẫn gặp lỗi **404 khi tải WSDL**, hoặc WSDL tải được nhưng `soap:address` lại chỉ đến localhost. Nguyên nhân thường nằm ở tên bean, servlet mapping, đường dẫn tài nguyên XSD hoặc cấu hình triển khai.

Bài học trong chương **Đọc và công bố WSDL** giải thích cách ánh xạ tên bean Spring thành URL `.wsdl`, cách tải schema từ runtime classpath, vai trò `locationUri` và cách xác minh hợp đồng khi có reverse proxy. Các ví dụ liên hệ với thiết kế XSD/WSDL, JAXB, SOAP endpoint/client, interceptor, SOAP Fault, XML security và WS-Security để hỗ trợ tích hợp doanh nghiệp ổn định.

## 1. Phân biệt bốn loại tên và đường dẫn

Giả sử dịch vụ đơn hàng có cấu hình như sau:

| Thành phần | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| File XSD trong source | `src/main/resources/xsd/orders.xsd` | Tập tin chỉnh sửa ở dự án. |
| Path resource khi chạy | `xsd/orders.xsd` | Vị trí trong **classpath** để Spring đọc XSD. |
| Tên bean schema | `ordersSchema` | Bean kiểu `XsdSchema`. |
| Tên bean WSDL | `orders` | Bean kiểu `Wsdl11Definition`, quyết định tên tài liệu được công bố. |
| Servlet mapping | `/ws/*` | Các request HTTP đi vào `MessageDispatcherServlet`. |
| URL WSDL local | `http://localhost:8080/ws/orders.wsdl` | Client **GET** để lấy hợp đồng. |
| SOAP endpoint local | `http://localhost:8080/ws` | Client **POST** SOAP Envelope. |
| Payload QName | `{urn:example:orders:v1}CreateOrderRequest` | Tên phần tử để Spring-WS tìm handler tương ứng. |

Các giá trị này không bắt buộc phải trùng nhau. Tên bean WSDL không phải tên operation; tên file XSD không quyết định URL WSDL; namespace URI trong XML không phải đường dẫn file hay địa chỉ web.

~~~mermaid
flowchart TD
    A["src/main/resources/xsd/orders.xsd"] --> B["ClassPathResource: xsd/orders.xsd"]
    B --> C["XsdSchema bean: ordersSchema"]
    C --> D["DefaultWsdl11Definition bean: orders"]
    D --> E["MessageDispatcherServlet /ws/*"]
    E --> F["GET /ws/orders.wsdl"]
    E --> G["POST /ws"]
    G --> H["SOAP Body: CreateOrderRequest"]
~~~

HTTP `GET /ws/orders.wsdl` dùng để tải mô tả dịch vụ; nó không gọi endpoint nghiệp vụ. HTTP `POST /ws` mang SOAP Envelope, có thể tạo response hay SOAP Fault. Khi dùng HTTPS, URL bên ngoài phải phản ánh đúng TLS, host và đường dẫn được proxy công bố.

## 2. Thiết kế XSD trước khi công bố WSDL

Ví dụ file `src/main/resources/xsd/orders.xsd` là schema XSD 1.0 tự chứa, gồm hai global element request/response:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

  <xs:element name="CreateOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="clientOrderId" type="xs:string"/>
        <xs:element name="amount" type="xs:decimal"/>
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

Hai global element kết thúc bằng `Request` và `Response` giúp bộ tạo WSDL mặc định của Spring-WS xác định cặp message cho operation tên `CreateOrder`. Khi đổi sang hậu tố khác như `Input`/`Output`, cần xem lại cấu hình nhận diện của `DefaultWsdl11Definition`; schema có thể hợp lệ nhưng WSDL sinh ra không có operation như dự kiến.

`targetNamespace` gắn định danh logic cho phần tử/kiểu XML, không quyết định file XSD nằm trong thư mục nào. `elementFormDefault="qualified"` yêu cầu các element con được khai báo cục bộ trong ví dụ dùng namespace nghiệp vụ khi xuất hiện trong XML instance.

## 3. Cấu hình Spring Boot và Spring-WS để công bố WSDL

Một cấu hình Spring Boot kết hợp `MessageDispatcherServlet` và `DefaultWsdl11Definition` có thể viết:

~~~java
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class SoapWebServiceConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
    messageDispatcherServlet(ApplicationContext applicationContext) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(applicationContext);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean(name = "ordersSchema")
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition definition =
                new DefaultWsdl11Definition();
        definition.setPortTypeName("OrdersPort");
        definition.setLocationUri("/ws");
        definition.setTargetNamespace("urn:example:orders:v1");
        definition.setSchema(ordersSchema);
        return definition;
    }
}
~~~

Ví dụ giả định ứng dụng đã có dependency Spring Boot/Spring-WS phù hợp, file XSD nằm trong runtime classpath và context path đang rỗng. Đây là cấu hình công bố WSDL, chưa bao gồm endpoint, schema validation, JAXB marshaller, TLS hay WS-Security.

### 3.1. Vì sao tên bean tạo URL `orders.wsdl`?

~~~java
@Bean(name = "orders")
public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
    // ...
}
~~~

Trong phạm vi servlet nhận các URL `/ws/*`, Spring-WS dùng tên bean `WsdlDefinition` để công bố tài liệu dưới tên `orders.wsdl`. Với server chạy cổng 8080 ở root context:

~~~text
bean WsdlDefinition: orders
mapping:             /ws/*
URL GET:             http://localhost:8080/ws/orders.wsdl
~~~

Tên method Java là `ordersWsdl` **không quyết định tên URL** ở đây, vì annotation `@Bean(name = "orders")` đã chỉ định tên bean. Ngược lại, với `@Bean` không có `name`, bean thường được đặt tên theo method, ví dụ `ordersWsdl`, dẫn tới `/ws/ordersWsdl.wsdl`.

| Định nghĩa bean | Tên bean | URL trong mapping `/ws/*` |
| --- | --- | --- |
| `@Bean(name="orders")` trên `ordersWsdl(...)` | `orders` | `/ws/orders.wsdl` |
| `@Bean` trên `ordersWsdl(...)` | `ordersWsdl` | `/ws/ordersWsdl.wsdl` |
| `@Bean(name="billing")` trên method bất kỳ | `billing` | `/ws/billing.wsdl` |

Tên bean còn phải được `MessageDispatcherServlet` nhìn thấy trong ApplicationContext mà nó sử dụng. Nếu bean bị loại bởi profile hoặc điều kiện khởi tạo, hoặc servlet chạy ở context khác, URL dự kiến vẫn có thể 404.

### 3.2. Bean schema và bean WSDL có trách nhiệm khác nhau

~~~java
@Bean(name = "ordersSchema")
public XsdSchema ordersSchema() {
    return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders.xsd"));
}
~~~

Bean `ordersSchema` cung cấp schema cho bộ tạo WSDL bằng lời gọi `definition.setSchema(ordersSchema)`. Tên schema bean **không** làm WSDL tự đổi thành `ordersSchema.wsdl`. Tên công bố của WSDL vẫn phụ thuộc `@Bean(name="orders")`.

Với `MessageDispatcherServlet` và bean `XsdSchema` được phát hiện phù hợp, Spring-WS có thể công bố schema dưới tên bean với đuôi `.xsd`, chẳng hạn `/ws/ordersSchema.xsd`. Đây là **HTTP URL công bố schema**, khác hoàn toàn `ClassPathResource("xsd/orders.xsd")`. Đừng tự suy ra một URL `/ws/xsd/orders.xsd` chỉ vì tài nguyên nằm trong thư mục `xsd`.

Hãy xác minh URL schema từ HTTP và tham chiếu thực tế trong WSDL, đặc biệt nếu schema có `xs:include` hoặc `xs:import`.

### 3.3. `setPortTypeName` và `setTargetNamespace` không đổi URL tải WSDL

~~~java
definition.setPortTypeName("OrdersPort");
definition.setTargetNamespace("urn:example:orders:v1");
~~~

`OrdersPort` là tên cổng trừu tượng (WSDL `portType`); `urn:example:orders:v1` là target namespace của hợp đồng WSDL. Chúng góp phần mô tả service và QName trong hợp đồng, nhưng URL tài liệu ở ví dụ vẫn là `/ws/orders.wsdl`.

Để định tuyến SOAP request, Spring-WS có thể dùng `@PayloadRoot(namespace = "urn:example:orders:v1", localPart = "CreateOrderRequest")` ở endpoint. Annotation này dựa vào QName payload trong SOAP Body, không dựa vào tên bean WSDL hay file XSD.

## 4. `ClassPathResource` khác file path và HTTP URL

Trong cấu trúc dự án:

~~~text
project/
└── src/
    └── main/
        ├── java/
        │   └── .../SoapWebServiceConfig.java
        └── resources/
            └── xsd/
                └── orders.xsd
~~~

Đường dẫn `new ClassPathResource("xsd/orders.xsd")` được giải từ **gốc runtime classpath**. Khi build, `src/main/resources` thường được đưa vào `target/classes`, `build/resources/main` hoặc nằm trong executable JAR dưới `BOOT-INF/classes`. Do đó, đọc `new File("src/main/resources/xsd/orders.xsd")` thường không phù hợp ở môi trường deploy.

| Giá trị | Ý nghĩa | Dùng lúc nào |
| --- | --- | --- |
| `src/main/resources/xsd/orders.xsd` | Path của source project | Chỉnh file trong IDE. |
| `xsd/orders.xsd` | Path tính từ runtime classpath | `ClassPathResource` đọc XSD trong JAR. |
| `ordersSchema` | Tên bean `XsdSchema` | Bean registration, có thể là tên công bố schema. |
| `/ws/ordersSchema.xsd` | URL HTTP của schema bean nếu được servlet expose | Client tải schema theo cơ chế công bố tương ứng. |
| `/ws/orders.wsdl` | URL công bố WSDL theo bean name | Client GET WSDL. |
| `/ws` | SOAP endpoint theo `locationUri` của ví dụ | Client POST SOAP Envelope. |

Khi gặp lỗi `FileNotFoundException` hoặc schema bean không thể khởi tạo, hãy kiểm tra file có thực sự được đóng gói, tên thư mục, chữ hoa/chữ thường và giá trị `ClassPathResource`. Trong môi trường Linux, `Orders.xsd` và `orders.xsd` thường là hai tên khác nhau. Nếu source file nằm ở `src/main/resources/schemas/orders.xsd` thì phải dùng `new ClassPathResource("schemas/orders.xsd")`.

Không tự gọi `getFile()` trên `ClassPathResource` khi resource có thể nằm bên trong JAR: nó không nhất thiết có một file vật lý tách rời trên hệ thống.

## 5. URL WSDL hình thành từ host, context path, servlet mapping và tên bean

Với môi trường Spring Boot local, có thể phân tích URL:

~~~text
http://localhost:8080/ws/orders.wsdl
|____ scheme, host, port ___| |_____ path _____|
                              /ws/ + orders + .wsdl
~~~

Công thức nhận biết thường là:

~~~text
scheme://host:port
  + ứng dụng context path (nếu có)
  + path do servlet mapping nhận
  + tên bean WsdlDefinition + ".wsdl"
~~~

Ví dụ, nếu ứng dụng được cấu hình context path `/integration`, servlet mapping `/ws/*` và bean tên `orders` thì URL bên ngoài ứng dụng (không qua proxy rewrite) thường là `http://localhost:8080/integration/ws/orders.wsdl`. Nếu đổi bean thành `billing` thì URL tương ứng có tên `billing.wsdl`.

| Cấu hình | URL WSDL dự kiến |
| --- | --- |
| Port 8080, root context, bean `orders` | `http://localhost:8080/ws/orders.wsdl` |
| Port 9090, root context, bean `orders` | `http://localhost:9090/ws/orders.wsdl` |
| Context path `/integration` | `http://localhost:8080/integration/ws/orders.wsdl` |
| Servlet mapping `/soap/*` | `http://localhost:8080/soap/orders.wsdl` |
| Bean WSDL tên `billing` | `http://localhost:8080/ws/billing.wsdl` |
| Public reverse proxy có rewrite path | URL theo cấu hình proxy, ví dụ `https://partner.example.test/api/soap/orders.wsdl` |

Những URL này chỉ là kết quả từ **giả định cấu hình**, không phải địa chỉ có thể truy cập thật. Khi triển khai sau reverse proxy, ingress hoặc API gateway, URL public có thể khác đáng kể với URL nội bộ mà ứng dụng nhìn thấy.

### 5.1. Địa chỉ tải WSDL khác địa chỉ gọi SOAP

Trong code:

~~~java
definition.setLocationUri("/ws");
~~~

`locationUri` xác định địa chỉ dịch vụ dùng cho `soap:address` trong phần `wsdl:service/wsdl:port` của WSDL được sinh; nó **không đặt tên URL tải WSDL**.

Hai request HTTP của cùng dịch vụ trong ví dụ:

~~~http
GET /ws/orders.wsdl HTTP/1.1
Host: localhost:8080
~~~

~~~http
POST /ws HTTP/1.1
Host: localhost:8080
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/CreateOrder"
~~~

GET tải hợp đồng, còn POST gửi SOAP Envelope. Đoạn POST chỉ là **HTTP header trích đoạn**, chưa gồm body và `Content-Length`/cách đóng khung. `SOAPAction` được ghi làm giá trị minh họa; action chính xác phải lấy từ binding WSDL của hệ thống, vì bộ sinh WSDL không nhất thiết tự tạo giá trị action như trong ví dụ.

Không phải mọi Spring-WS app đều POST đến `/ws`. Một dịch vụ khác có thể dùng `setLocationUri("/ws/orders")` hoặc path riêng; client cần dựa vào `soap:address` được công bố và cấu hình routing thực tế.

### 5.2. `setTransformWsdlLocations(true)` dùng khi nào?

Trong `MessageDispatcherServlet`:

~~~java
servlet.setTransformWsdlLocations(true);
~~~

Tùy chọn này cho phép Spring-WS biến đổi địa chỉ dịch vụ trong WSDL trả về theo ngữ cảnh HTTP request. Nó hữu ích nếu WSDL được truy cập ở nhiều hostname/port. Tuy nhiên, **không có bảo đảm** tùy chọn này tự biết cách API gateway thay đổi path, host hoặc scheme khi proxy không truyền đủ metadata.

Ví dụ phía đối tác truy cập:

~~~text
https://partner.example.test/api/soap/orders.wsdl
~~~

Nhưng ứng dụng phía sau proxy nhận request nội bộ qua:

~~~text
http://localhost:8080/ws/orders.wsdl
~~~

Nếu kết quả WSDL chứa:

~~~xml
<soap:address location="http://localhost:8080/ws"/>
~~~

thì client từ bên ngoài có thể tải WSDL nhưng không gọi được SOAP operation. Mục tiêu công bố thực tế thường là một địa chỉ public có thể sử dụng, chẳng hạn:

~~~xml
<soap:address location="https://partner.example.test/api/soap"/>
~~~

Để đạt được, cần kiểm tra **cả** cấu hình `locationUri`, quy tắc route/rewrite của proxy, forwarded headers và cơ chế xử lý forwarded headers của Spring Boot/Spring Framework đang dùng. Chỉ tin các header như `Forwarded` hoặc `X-Forwarded-*` từ reverse proxy đáng tin; client không nên có quyền tự quyết nội dung host/scheme trong WSDL bằng cách giả mạo header.

Sau khi chỉnh proxy, kiểm tra WSDL bằng GET **từ mạng bên ngoài** và xem trực tiếp `soap:address`. Một response 200 tại localhost không chứng minh SOAP address công bố ra ngoài là đúng.

## 6. Đọc WSDL được công bố: phần nào chịu ảnh hưởng bởi cấu hình?

Sau khi GET `orders.wsdl`, một WSDL 1.1 thông thường gồm các thành phần:

~~~text
wsdl:definitions
├── wsdl:types        — XSD types / schema reference
├── wsdl:message      — message input/output
├── wsdl:portType     — operation trừu tượng
├── wsdl:binding      — protocol, style/use, SOAPAction
└── wsdl:service
    └── wsdl:port
        └── soap:address — URL gửi SOAP request
~~~

Một trích đoạn chỉ minh họa cấu trúc service (không phải WSDL hoàn chỉnh vì thiếu `types/message/portType/binding`):

~~~xml
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1">
  <!-- types, message, portType, binding... -->
  <wsdl:service name="OrdersService">
    <wsdl:port name="OrdersPort"
               binding="tns:OrdersPortBinding">
      <soap:address location="http://localhost:8080/ws"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
~~~

| Thành phần | Kiểm tra | Liên hệ cấu hình |
| --- | --- | --- |
| `wsdl:types` | Có schema cần dùng, có import/include? | Bean `XsdSchema` và `setSchema`. |
| `wsdl:message` | Request/response tham chiếu element nào? | Global elements trong XSD. |
| `wsdl:portType` | Có operation `CreateOrder`? | Hậu tố request/response, `setPortTypeName`. |
| `wsdl:binding` | SOAP 1.1/1.2, `document/literal`, action? | Cấu hình WSDL generator hoặc hợp đồng tĩnh. |
| `wsdl:service`/`soap:address` | Client phải POST ở URL nào? | `setLocationUri`, transform và proxy. |

Đừng nhầm `soap:address` với URL mà bạn vừa GET WSDL. `wsdl:service` mô tả địa chỉ gọi dịch vụ, trong khi tên bean định tuyến HTTP GET lấy hợp đồng. Nếu `wsdl:types` có schema nhưng QName request khác annotation `@PayloadRoot` ở Spring-WS endpoint, request có thể không vào handler dù WSDL công bố thành công.

### 6.1. Tên operation độc lập với tên bean

Ví dụ:

~~~text
Bean WSDL                    orders
WSDL URL                     /ws/orders.wsdl
WSDL port type               OrdersPort
Operation                    CreateOrder
Global request element       CreateOrderRequest
Global response element      CreateOrderResponse
SOAP POST path               /ws
~~~

Đổi bean `orders` thành `purchase` có thể đổi URL thành `purchase.wsdl` nhưng **không tự đổi** operation `CreateOrder`. Đổi `setPortTypeName("OrdersPort")` cũng không tự đổi tên bean hoặc URL tải WSDL. Thay global element request/response lại ảnh hưởng đến message/operation sinh động và QName endpoint, nên cần kiểm thử contract toàn diện.

## 7. Đường dẫn `xs:include`, `xs:import` và client tải schema

Với XSD đơn giản trong mục 2, schema có thể được đưa vào WSDL theo cơ chế của generator mà không cần client tải thêm file. Trong dự án doanh nghiệp, schema thường có nhiều phụ thuộc:

~~~text
src/main/resources/xsd/
├── orders.xsd
├── common-types.xsd
└── audit.xsd
~~~

Ví dụ schema `orders.xsd` chứa:

~~~xml
<xs:include schemaLocation="common-types.xsd"/>
~~~

`xs:include` dùng cho schema có namespace tương thích, thường cùng `targetNamespace` hoặc schema được include không định nghĩa targetNamespace theo quy tắc XSD. Với các namespace khác nhau, có thể dùng `xs:import` với `namespace` và `schemaLocation` tương ứng.

Có **hai giai đoạn giải quyết đường dẫn**:

1. **Ở server khi khởi tạo/generate WSDL:** parser và schema loader phải tìm được `common-types.xsd` từ các tài nguyên classpath/URI được cấu hình. Đối với cấu trúc nhiều schema, có thể cần schema collection và resource resolver phù hợp.
2. **Ở client khi tải WSDL/XSD:** mọi URL mà tài liệu công bố còn tham chiếu phải có thể truy cập được từ môi trường của client. Tài nguyên `classpath:xsd/common-types.xsd` trên server không phải một public HTTP URL.

Ví dụ, nếu client tải schema từ:

~~~text
https://partner.example.test/api/soap/ordersSchema.xsd
~~~

và schema công bố chứa `schemaLocation="common-types.xsd"`, client thường thử URL:

~~~text
https://partner.example.test/api/soap/common-types.xsd
~~~

Nếu URL này trả 404 thì hợp đồng phân tán chưa được công bố đầy đủ. Đừng mặc định rằng mọi file nằm cạnh nhau dưới `src/main/resources/xsd` sẽ tự động có URL cạnh nhau trên web.

**Khi dùng WSDL tĩnh**, tham chiếu `wsdl:import` và `xs:import` cũng phải được kiểm tra tương tự. Với WSDL động, tùy schema provider và cấu hình inlining/collection, WSDL có thể inline schema hoặc giữ tham chiếu. Hãy xem **XML WSDL trả về thực tế**, không dựa vào giả định.

### 7.1. Phân biệt path trên đĩa với path tương đối trong XML

| Path | Ai giải quyết? | Nguồn tham chiếu |
| --- | --- | --- |
| `xsd/orders.xsd` trong `ClassPathResource` | Java class loader/resource abstraction | Runtime classpath của server. |
| `common-types.xsd` trong `xs:include` | XML Schema resolver/parser | Base URI của schema đang xử lý. |
| `https://.../common-types.xsd` trong WSDL public | SOAP client/HTTP client | Mạng, URL public, TLS, auth. |
| `/ws/ordersSchema.xsd` | `MessageDispatcherServlet` hoặc resource handler | Servlet mapping và bean/resource công bố. |

Nếu schema không tải được, cần xác định lỗi xảy ra ở **startup phía server** hay **fetch phía client**. Cùng lỗi “schema not found” có thể cần hai cách sửa khác nhau.

## 8. Tạo WSDL động hay công bố WSDL tĩnh?

### 8.1. `DefaultWsdl11Definition`: tạo WSDL từ schema và cấu hình

Cấu hình trong mục 3 dùng:

~~~java
@Bean(name = "orders")
public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
    DefaultWsdl11Definition definition =
            new DefaultWsdl11Definition();
    definition.setPortTypeName("OrdersPort");
    definition.setLocationUri("/ws");
    definition.setTargetNamespace("urn:example:orders:v1");
    definition.setSchema(ordersSchema);
    return definition;
}
~~~

Cách này phù hợp khi schema và quy ước tên global element đủ để sinh operation. Cần lưu ý thay đổi request/response elements, hậu tố hoặc kiểu dữ liệu có thể ảnh hưởng WSDL được công bố. Các yêu cầu SOAPAction, binding phức tạp, WS-Policy hoặc cấu trúc nhiều schema có thể đòi hỏi cấu hình bổ sung hay WSDL tĩnh.

### 8.2. `SimpleWsdl11Definition`: xuất một file WSDL đã thống nhất

Một dự án có thể lưu WSDL 1.1 hoàn chỉnh tại:

~~~text
src/main/resources/wsdl/orders.wsdl
~~~

Sau đó thay bean `DefaultWsdl11Definition` bằng `SimpleWsdl11Definition`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.wsdl.wsdl11.SimpleWsdl11Definition;

@Bean(name = "orders")
public SimpleWsdl11Definition ordersWsdl() {
    return new SimpleWsdl11Definition(
            new ClassPathResource("wsdl/orders.wsdl"));
}
~~~

Đây là **một phương án thay thế**, không khai báo hai bean cùng tên `orders` đồng thời. Nếu servlet mapping vẫn là `/ws/*`, tên URL WSDL vẫn là `/ws/orders.wsdl`. File WSDL tĩnh phải mô tả đầy đủ `types/message/portType/binding/service`, SOAP address, namespace và tham chiếu schema; không mặc định framework sẽ tự tạo nội dung còn thiếu.

| Đặc điểm | WSDL động | WSDL tĩnh |
| --- | --- | --- |
| Nguồn tạo WSDL | XSD và cấu hình generator | File `.wsdl` đầy đủ. |
| URL công bố | Tên bean `WsdlDefinition` | Tên bean `WsdlDefinition` |
| Đổi operation | Có thể phát sinh từ thay global elements/suffix | Sửa WSDL có chủ đích. |
| Hợp đồng có import/policy phức tạp | Có thể cần xử lý thêm | Có thể quản lý trực tiếp mọi tham chiếu. |
| Rủi ro chính | Thay đổi XSD làm WSDL đổi ngoài dự tính | WSDL tĩnh lệch với XSD hoặc implementation. |

Với hợp đồng đã cấp cho nhiều đối tác, ưu tiên tính **ổn định của tài liệu được công bố** và kiểm thử tương thích. Một thay đổi tên bean dù không đổi code Java endpoint vẫn có thể phá đường dẫn mà đối tác dùng để tải hợp đồng.

## 9. Kiểm tra HTTP: WSDL GET rồi SOAP POST

Khi ứng dụng mẫu đang chạy ở `localhost:8080`, dùng PowerShell/Windows:

~~~powershell
curl.exe --include "http://localhost:8080/ws/orders.wsdl"
~~~

Đọc kết quả theo thứ tự: HTTP status, `Content-Type`, phần tử gốc `wsdl:definitions`, `wsdl:types`, message/operation/binding, rồi `soap:address`. Một response HTTP 200 mang HTML của trang đăng nhập hoặc gateway không phải WSDL hợp lệ. Kiểm tra schema được công bố nếu servlet nhận diện bean `ordersSchema`:

~~~powershell
curl.exe --include "http://localhost:8080/ws/ordersSchema.xsd"
~~~

Để tải tài liệu về máy nhằm kiểm tra bằng WSDL validator hoặc client generator:

~~~powershell
curl.exe --fail --location --output orders.wsdl "http://localhost:8080/ws/orders.wsdl"
~~~

Tên file ở tham số `--output` là tên trên máy người kiểm tra, không ảnh hưởng tên bean Spring hay URL của server. Nếu có `xs:include`, `xs:import` hoặc `wsdl:import`, tiếp tục tải thử mọi phụ thuộc từ môi trường của **client**, nhất là qua public proxy.

### 9.1. Gửi một SOAP request tới endpoint

Tạo file `request.xml` mã hóa UTF-8 chứa SOAP 1.1 Envelope:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:ord="urn:example:orders:v1">
  <soap:Header/>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Gửi đến `soap:address` của môi trường test, ví dụ bằng một dòng:

~~~powershell
curl.exe --include --request POST --header 'Content-Type: text/xml; charset=utf-8' --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' --data-binary '@request.xml' "http://localhost:8080/ws"
~~~

`SOAPAction` là **giá trị minh họa**; action chính xác phải lấy từ WSDL và yêu cầu đối tác. `curl.exe` tự tính độ dài HTTP body theo byte file. GET WSDL thành công không chứng minh endpoint đã tồn tại hoặc marshaller JAXB và interceptor đã hoạt động. Nếu không có handler phù hợp, server có thể báo lỗi hoặc SOAP Fault tùy cấu hình.

Ví dụ handler thường dùng `@PayloadRoot` để ghép QName payload:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "CreateOrderRequest"
)
@ResponsePayload
public CreateOrderResponse createOrder(
        @RequestPayload CreateOrderRequest request) {
    // Xu ly nghiep vu va tao response.
}
~~~

Đây là chữ ký minh họa, giả định đã có import, class JAXB và cấu hình handler/marshaller. Spring-WS dùng QName `{urn:example:orders:v1}CreateOrderRequest` để định tuyến; nó không dùng tên bean WSDL `orders` để thay thế QName. Nếu có `PayloadValidatingInterceptor`, XML hợp cú pháp vẫn có thể bị từ chối vì sai ràng buộc XSD.

## 10. Khoanh vùng các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Phép kiểm cần làm |
| --- | --- | --- |
| GET `/ws/orders.wsdl` → 404 | Tên bean khác `orders`, servlet mapping/context path hoặc proxy route sai. | Xem `@Bean(name=...)`, runtime bean và URL thực tế. |
| GET `/ws/ordersWsdl.wsdl` mới trả 200 | `@Bean` không có `name`, tên bean theo method. | Đặt `@Bean(name="orders")` nếu cần URL ổn định. |
| Khởi động lỗi thiếu `xsd/orders.xsd` | Resource không có trong JAR, path hoặc chữ hoa/thường sai. | Kiểm tra classpath và file đã được đóng gói. |
| WSDL không có operation `CreateOrder` | Global elements/suffix không khớp quy ước generator. | So tên `CreateOrderRequest`, `CreateOrderResponse` và cấu hình WSDL. |
| WSDL trả 200 nhưng client lỗi import schema | `schemaLocation` hoặc `wsdl:import` trỏ URL không phục vụ. | Lấy từng XSD/WSDL tham chiếu qua HTTP. |
| GET `/ws/xsd/orders.xsd` → 404 | Nhầm path classpath với HTTP URL. | Kiểm tra bean `XsdSchema` hoặc static resource mapping. |
| Public WSDL có `soap:address` localhost | Proxy rewrite, forwarded headers, `locationUri` hoặc transform sai. | GET WSDL qua public URL và kiểm tra địa chỉ SOAP. |
| GET WSDL trả HTML hoặc redirect | Gateway, auth hoặc web handler chặn request. | Xem status, Content-Type, final URL, body. |
| POST SOAP → 404/405 | Sai địa chỉ POST hoặc servlet không nhận path/method. | Dùng `soap:address`, kiểm tra mapping. |
| SOAP không vào endpoint | QName Body sai, thiếu `@PayloadRoot` hoặc mapping handler. | So namespace URI + local name với XSD và annotation. |
| SOAP Fault/unmarshal error | Sai XSD, JAXB, SOAP version hoặc interceptor. | Đọc Fault/detail và log ở tầng tương ứng. |
| WS-Security/`MustUnderstand` Fault | Header bắt buộc, chứng chỉ, token, timestamp, signature sai. | Xem SOAP Header và cấu hình bảo mật. |

Để không sửa nhầm tầng, phân biệt ba tình huống. **Không tải được WSDL** là lỗi routing/bean/publication; **tải WSDL nhưng thiếu XSD** là lỗi schema reference/resource URL; **tải đủ hợp đồng nhưng POST thất bại** mới cần xem QName SOAP, JAXB, endpoint, SOAP Fault, security và nghiệp vụ.

### 10.1. Khi triển khai sau reverse proxy

Nếu public URL là `https://partner.example.test/api/soap/orders.wsdl` nhưng app chạy ở `http://localhost:8080/ws/orders.wsdl`, hãy lưu đồng thời URL mà client gửi, URL proxy chuyển tiếp, host/scheme/port mà servlet thấy và `soap:address` được trả về. `setTransformWsdlLocations(true)` chỉ có thể dựa trên thông tin request/framework nhận được; proxy đổi prefix có thể đòi hỏi cấu hình rõ ràng hơn.

Trường hợp khó thường là **WSDL tải được nhưng client tự gọi URL nội bộ**. Khi đó kiểm tra `soap:address` và sửa cấu hình tại nơi công bố hợp đồng; không khắc phục lâu dài bằng cách hardcode địa chỉ SOAP trên từng máy client.

## 11. Versioning và bảo mật khi công bố hợp đồng

Một client có thể lưu URL WSDL để generate code Java/.NET hoặc cấu hình địa chỉ SOAP lúc build. Đổi bean `orders` thành `ordersV2` có thể đổi URL WSDL dù operation vẫn tên `CreateOrder`. Thay targetNamespace hoặc cấu trúc XSD có thể phá tương thích dữ liệu dù URL không đổi.

Trước khi phát hành phiên bản mới, cần kiểm tra WSDL public cũ và mới, schema imports, QName của request/response, SOAP binding, `soap:address` và client đã sinh mã. Nếu thay đổi không tương thích, cân nhắc công bố song song các phiên bản, tên/namespace mới và kế hoạch chuyển đổi có thông báo.

WSDL chứa các operation và địa chỉ dịch vụ nên quyền GET tài liệu phải phù hợp chính sách của hệ thống. Có thể GET WSDL thành công nhưng POST SOAP vẫn bị từ chối vì TLS client certificate, WS-Security UsernameToken, XML Signature, timestamp hoặc interceptor. Hãy tách kiểm tra **quyền tải tài liệu**, **bảo vệ kênh**, **bảo mật thông điệp** và **valid XSD**.

Khi ghi log SOAP để phân tích lỗi, thay thế thông tin cá nhân, token, mật khẩu và private key. Parser xử lý XML từ đối tác cần hạn chế DTD/external entity, entity expansion và giới hạn kích thước theo cấu hình thực tế; không mở tùy ý tài nguyên ngoài để chữa lỗi schema import.

## 12. Bài thực hành: dự đoán URL và tìm lỗi

**Tình huống A — Đổi tên bean:** servlet mapping `/ws/*`, port 8080, context path rỗng; WSDL definition có `@Bean(name="sales")` trên method `ordersWsdl(...)`. URL GET WSDL là `http://localhost:8080/ws/sales.wsdl`; tên operation `CreateOrder` và tên XSD element không tự đổi.

**Tình huống B — Sai classpath:** file thật ở `src/main/resources/schemas/orders.xsd` nhưng code dùng `ClassPathResource("xsd/orders.xsd")`. Cần sửa thành `ClassPathResource("schemas/orders.xsd")` hoặc bố trí lại resource; không dùng `new File("src/main/resources/...")` như cách chữa khi chạy JAR.

**Tình huống C — WSDL public dùng địa chỉ nội bộ:** GET từ `https://partner.example.test/api/soap/orders.wsdl` trả `soap:address location="http://localhost:8080/ws"`. Cần kiểm tra `locationUri`, transform, forwarded headers và path rewrite; chỉ hoàn tất khi SOAP client từ bên ngoài POST được vào địa chỉ public.

**Tình huống D — Import XSD trả 404:** `orders.xsd` và `common-types.xsd` đều có trong classpath nhưng client không tải được `common-types.xsd` từ URL liên quan. Cần kiểm tra `schemaLocation` public, cơ chế công bố từng schema và relative URL; resource trong JAR không tự tạo HTTP endpoint.

| Checklist | Dấu hiệu hoàn thành |
| --- | --- |
| Bean WSDL | Đúng tên và URL `.wsdl` đã thỏa thuận. |
| Servlet mapping/context path | GET đến đúng `MessageDispatcherServlet`. |
| Runtime resource | `ClassPathResource` tải được XSD trong classpath/JAR. |
| Hợp đồng WSDL | `types/message/portType/binding/service` khớp XSD và SOAP protocol. |
| Schema references | Client resolve được toàn bộ import/include cần thiết. |
| SOAP address | Đúng địa chỉ POST public, kể cả sau proxy rewrite. |
| Endpoint/JAXB | QName payload, object mapping và validation nhất quán. |
| Security | Quyền GET, HTTPS, client certificate/WS-Security phù hợp. |
| Compatibility | Client cũ/mới tải và sử dụng hợp đồng theo chính sách version. |

### Ghi nhớ

- Bean `Wsdl11Definition` tên `orders` thường được `MessageDispatcherServlet` công bố dưới `orders.wsdl` trong phạm vi servlet mapping. `@Bean(name=...)` quyết định tên bean ngay cả khi tên method Java khác.
- `setLocationUri("/ws")` chỉ địa chỉ SOAP POST trong WSDL; URL tải WSDL do bean name, mapping và context path quyết định.
- `ClassPathResource("xsd/orders.xsd")` đọc resource ở runtime classpath; `src/main/resources` không tự tương ứng với một public HTTP URL.
- Đường dẫn XSD trong JAR, tên bean `XsdSchema` và URL `.xsd` mà client tải là các khái niệm riêng.
- Kiểm thử công bố WSDL phải bao gồm **GET public WSDL → resolve XSD → kiểm tra SOAP address → POST SOAP → đọc response/Fault**, đặc biệt khi triển khai qua proxy và bật interceptor/WS-Security.



