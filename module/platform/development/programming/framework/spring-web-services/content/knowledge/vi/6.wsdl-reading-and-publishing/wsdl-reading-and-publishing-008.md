# Công bố XSD qua XsdSchema và tập hợp nhiều schema

## 1. Vai trò của XSD khi công bố một dịch vụ SOAP

Trong mô hình **contract-first** của Spring Web Services (Spring-WS), hợp đồng XML Schema (XSD) xác định QName, kiểu dữ liệu, thứ tự phần tử và các ràng buộc của SOAP request/response. WSDL mô tả thao tác, message, SOAP binding và địa chỉ mà client gọi. Đối tác tích hợp thường tải WSDL và những XSD liên quan để sinh mã JAXB/JAX-WS, .NET hoặc kiểm tra thông điệp trước khi gọi dịch vụ.

Bài học thuộc chương **Đọc và công bố WSDL** của module **SPRING_WEB_SERVICES**. Trọng tâm là cách sử dụng **XsdSchema** và **XsdSchemaCollection** để công bố XSD đơn lẻ hoặc tập hợp nhiều schema, rồi kết nối chúng với **DefaultWsdl11Definition**, SOAP endpoint và quá trình kiểm thử tương thích.

Sau bài học, bạn cần thực hiện được các việc sau:

- Biết XsdSchema và SimpleXsdSchema biểu diễn điều gì trong Spring.
- Công bố một XSD theo URL từ MessageDispatcherServlet.
- Phân biệt việc công bố XSD, sinh WSDL và xác thực SOAP payload.
- Chia hợp đồng thành nhiều XSD với xs:include và xs:import mà không làm sai namespace.
- Tạo tập hợp nhiều schema bằng CommonsXsdSchemaCollection và cung cấp cho DefaultWsdl11Definition.
- Kiểm tra toàn bộ các tài liệu mà client cần tải, kể cả schema phụ thuộc, khi hệ thống ở sau reverse proxy.
- Đánh giá nguy cơ tương thích và an toàn XML khi thay đổi cấu trúc hợp đồng.

## 2. Bốn trách nhiệm khác nhau trong Spring-WS

Một XSD nằm trong classpath của ứng dụng không tự biến thành một tài liệu công khai trên Internet. Ngược lại, việc công bố WSDL thành công không có nghĩa mọi request SOAP đều được kiểm tra theo XSD.

| Trách nhiệm | Thành phần thường dùng | Kết quả |
|---|---|---|
| Đọc một XSD | XsdSchema, SimpleXsdSchema | Quản lý XML Schema như một tài nguyên Spring |
| Tổ chức nhiều XSD | XsdSchemaCollection, CommonsXsdSchemaCollection | Kết hợp các schema entrypoint và giải quyết phụ thuộc |
| Công bố WSDL | DefaultWsdl11Definition hoặc SimpleWsdl11Definition | Tài liệu mô tả operation, binding, service, port |
| Nhận và kiểm tra SOAP | MessageDispatcherServlet, PayloadValidatingInterceptor, @Endpoint | Xử lý HTTP/SOAP, xác thực payload và nghiệp vụ |

~~~mermaid
flowchart TD
    A["XSD trong resources"] --> B["XsdSchema"]
    A --> C["XsdSchemaCollection"]
    B --> D["WSDL definition"]
    C --> D
    B --> E["URL .xsd nếu công bố"]
    D --> F["URL .wsdl"]
    E --> G["SOAP client / công cụ sinh mã"]
    F --> G
    G --> H["HTTP SOAP request"]
    H --> I["MessageDispatcherServlet"]
    I --> J["Schema validation và JAXB"]
    J --> K["Spring-WS Endpoint"]
~~~

**XsdSchema** là abstraction đại diện cho một XML Schema, cung cấp metadata như target namespace và nguồn tài liệu. **SimpleXsdSchema** là implementation phổ biến cho một file. **XsdSchemaCollection** biểu diễn một tập các schema; **CommonsXsdSchemaCollection** hỗ trợ tập hợp nhiều schema và xử lý import/include theo cấu hình.

**DefaultWsdl11Definition** dùng XSD để tạo WSDL động. MessageDispatcherServlet, khi nhận diện những bean metadata thích hợp, phục vụ tài liệu WSDL và XSD theo tên bean. Những công việc này vẫn độc lập với việc @Endpoint có xử lý một SOAP request cụ thể hay không.

## 3. Ví dụ hợp đồng có ba tài liệu XSD

Hãy thiết kế một dịch vụ tra cứu đơn hàng trong đó:

1. orders-v1.xsd chứa hai global elements GetOrderRequest và GetOrderResponse.
2. orders-model-v1.xsd chứa kiểu OrderSummaryType cùng miền nghiệp vụ orders.
3. common-types-v1.xsd chứa RequestMetaType thuộc namespace dùng chung.

Sơ đồ phụ thuộc:

~~~mermaid
flowchart TD
    A["orders-v1.xsd\nurn:example:orders:v1"] -->|"xs:include"| B["orders-model-v1.xsd\nurn:example:orders:v1"]
    A -->|"xs:import"| C["common-types-v1.xsd\nurn:example:common:v1"]
~~~

### 3.1. Schema kiểu đơn hàng cùng namespace

File src/main/resources/xsd/orders-model-v1.xsd:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:complexType name="OrderSummaryType">
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
            <xs:element name="status" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>
</xs:schema>
~~~

OrderSummaryType có QName:

~~~text
{urn:example:orders:v1}OrderSummaryType
~~~

### 3.2. Schema kiểu dùng chung khác namespace

File src/main/resources/xsd/common-types-v1.xsd:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:com="urn:example:common:v1"
    targetNamespace="urn:example:common:v1"
    elementFormDefault="qualified">

    <xs:complexType name="RequestMetaType">
        <xs:sequence>
            <xs:element name="requestId" type="xs:string"/>
            <xs:element name="tenantId"
                        type="xs:string"
                        minOccurs="0"/>
        </xs:sequence>
    </xs:complexType>
</xs:schema>
~~~

RequestMetaType thuộc QName:

~~~text
{urn:example:common:v1}RequestMetaType
~~~

### 3.3. Schema gốc dùng cả include và import

File src/main/resources/xsd/orders-v1.xsd:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    xmlns:com="urn:example:common:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:include schemaLocation="orders-model-v1.xsd"/>

    <xs:import
        namespace="urn:example:common:v1"
        schemaLocation="common-types-v1.xsd"/>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="meta"
                            type="com:RequestMetaType"
                            minOccurs="0"/>
                <xs:element name="orderId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="order"
                            type="ord:OrderSummaryType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

XSD gốc có hai element công khai:

~~~text
{urn:example:orders:v1}GetOrderRequest
{urn:example:orders:v1}GetOrderResponse
~~~

Nội dung SOAP Body hợp lệ có thể là:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:com="urn:example:common:v1">
    <ord:meta>
        <com:requestId>REQ-1001</com:requestId>
    </ord:meta>
    <ord:orderId>ORD-7002</ord:orderId>
</ord:GetOrderRequest>
~~~

Lý do dùng hai prefix trong đoạn XML này là trường meta thuộc namespace orders, còn các phần tử con được định nghĩa trong kiểu common với elementFormDefault="qualified". Client và server so QName, không so tên prefix theo chuỗi ký tự.

## 4. Phân biệt xs:include và xs:import

Cả hai là khai báo của XML Schema, nhưng điều kiện áp dụng khác nhau.

| Tiêu chí | xs:include | xs:import |
|---|---|---|
| Quan hệ namespace | Tài liệu cùng targetNamespace; có thể include schema không có targetNamespace theo cơ chế chameleon | Dùng để tham chiếu namespace khác |
| Thuộc tính chính | schemaLocation | namespace và schemaLocation (có thể tùy chọn theo đặc tả/khả năng resolver) |
| Ví dụ | orders-v1.xsd include orders-model-v1.xsd | orders-v1.xsd import common-types-v1.xsd |
| Nguy cơ hay gặp | Include tài liệu có targetNamespace khác | Khai báo namespace không khớp type QName hoặc đường dẫn gãy |

**Sai cách dùng:**

~~~xml
<!-- Sai nếu common-types-v1.xsd có namespace urn:example:common:v1 -->
<xs:include schemaLocation="common-types-v1.xsd"/>
~~~

**Đúng cách dùng:**

~~~xml
<xs:import
    namespace="urn:example:common:v1"
    schemaLocation="common-types-v1.xsd"/>
~~~

schemaLocation là gợi ý vị trí để tìm schema, không thay thế việc kiểm tra namespace. Hai file cùng tên local type nhưng khác namespace vẫn là hai định nghĩa khác nhau. Ngược lại, nạp hai định nghĩa global type cùng QName vào một bộ schema có thể tạo lỗi trùng.

Đặc biệt, không được mặc định mọi file dưới cùng thư mục sẽ thuộc cùng namespace. Cần đọc targetNamespace và chuỗi import/include.

## 5. Công bố XSD đơn qua SimpleXsdSchema

Với Spring-WS, có thể tạo các bean XsdSchema trỏ đến file trong classpath:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class OrderSchemaConfig {

    @Bean(name = "orders-v1")
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders-v1.xsd")
        );
    }

    @Bean(name = "orders-model-v1")
    public XsdSchema ordersModelSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders-model-v1.xsd")
        );
    }

    @Bean(name = "common-types-v1")
    public XsdSchema commonSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/common-types-v1.xsd")
        );
    }
}
~~~

Các file resources phải được đóng gói trong artifact chạy, chứ không chỉ tồn tại ở thư mục nguồn của IDE. Spring sẽ quản lý vòng đời bean và có thể nạp tài nguyên schema theo cấu hình.

### 5.1. Vì sao đăng ký cả schema phụ thuộc?

Nếu MessageDispatcherServlet map vào /ws/* và tìm thấy các XsdSchema beans trong context, các URL phục vụ schema thường có dạng:

~~~text
GET https://api.example.test/ws/orders-v1.xsd
GET https://api.example.test/ws/orders-model-v1.xsd
GET https://api.example.test/ws/common-types-v1.xsd
~~~

Trong orders-v1.xsd, các schemaLocation tương đối:

~~~xml
<xs:include schemaLocation="orders-model-v1.xsd"/>

<xs:import
    namespace="urn:example:common:v1"
    schemaLocation="common-types-v1.xsd"/>
~~~

được một client tải từ /ws/orders-v1.xsd giải tương đối thành /ws/orders-model-v1.xsd và /ws/common-types-v1.xsd. Cách đặt tên bean trùng basename trong ví dụ giúp liên kết URL tương đối nhất quán.

URL chính xác phụ thuộc tên bean, servlet mapping, context path, proxy và quy tắc viết lại schema location. Đăng ký bean **không miễn kiểm thử HTTP**; muốn chắc chắn, phải thử tải từ máy client bên ngoài ứng dụng.

### 5.2. Namespace khác URL schema

Địa chỉ:

~~~text
https://api.example.test/ws/orders-v1.xsd
~~~

chỉ vị trí có thể tải file. Còn namespace:

~~~text
urn:example:orders:v1
~~~

là định danh của QName. Di chuyển endpoint hoặc chuyển máy chủ cung cấp WSDL/XSD không bắt buộc đổi namespace. Nếu tự ý đổi targetNamespace, các client đã sinh JAXB binding trước đó có thể không còn nhận đúng phần tử.

### 5.3. Có schema trên classpath nhưng trả HTTP 404

Khi GET /ws/orders-v1.xsd trả 404, kiểm tra theo thứ tự:

1. MessageDispatcherServlet đã được đăng ký chưa, và mapping có bao gồm /ws/* không?
2. Bean có đúng tên orders-v1 và đúng kiểu XsdSchema không?
3. Bean có nằm trong context mà servlet tìm kiếm không?
4. Context path/proxy có thêm tiền tố đường dẫn khác không?
5. Tài nguyên ClassPathResource có thực sự được đóng gói trong ứng dụng không?
6. Cấu hình bảo mật có chặn GET đến các URL metadata không?

Không nên kết luận Spring-WS không hỗ trợ công bố XSD chỉ vì một đường dẫn thử thủ công chưa đúng.

## 6. Sinh WSDL động từ một XsdSchema

Sau khi có schema gốc, bạn có thể tạo WSDL 1.1 với DefaultWsdl11Definition:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class OrderWsdlConfig {

    @Bean(name = "orders")
    public DefaultWsdl11Definition orderWsdl(
            @Qualifier("orders-v1") XsdSchema schema) {

        DefaultWsdl11Definition definition =
            new DefaultWsdl11Definition();

        definition.setPortTypeName("OrderPort");
        definition.setServiceName("OrderService");
        definition.setLocationUri("/ws");
        definition.setTargetNamespace("urn:example:orders:v1");
        definition.setSchema(schema);

        return definition;
    }
}
~~~

Một cách cấu hình servlet trong ứng dụng Spring Boot tương thích:

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
    messageDispatcherServlet(ApplicationContext context) {

        MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();

        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);

        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }
}
~~~

Với servlet trên và bean WSDL có tên orders, URL metadata điển hình là:

~~~text
GET https://api.example.test/ws/orders.wsdl
~~~

Tên bean quyết định phần tên URL tài liệu, còn setPortTypeName, setServiceName và setTargetNamespace xác định các tên quan trọng bên trong WSDL.

### 6.1. DefaultWsdl11Definition suy luận operation từ đâu?

Với hai global elements:

~~~text
GetOrderRequest
GetOrderResponse
~~~

generator có thể suy ra operation GetOrder bằng cách bỏ các hậu tố Request và Response. Các hậu tố có thể được cấu hình phù hợp quy ước dự án.

Hệ quả:

- Thay tên GetOrderRequest thành FindOrderRequest có thể làm thay đổi operation xuất hiện trong WSDL.
- Thêm global element có hậu tố Request/Response có thể tạo thêm operation ngoài ý định.
- Method Java của @Endpoint không tự quyết định WSDL operation trong mô hình này.
- Một file XSD chỉ chứa named complex types, không có global request/response elements, chưa đủ để suy luận các operation mong muốn.

Vì vậy, sau khi sinh WSDL phải kiểm tra thực tế các thành phần wsdl:types, wsdl:message, wsdl:portType, wsdl:binding và wsdl:service. Đừng chỉ kiểm tra rằng GET URL WSDL trả HTTP 200.

### 6.2. WSDL động và WSDL tĩnh

Nếu hợp đồng đã công bố cho nhiều đối tác và cần giữ từng operation, binding hoặc fault ổn định, có thể chọn WSDL đã chuẩn bị sẵn và công bố qua SimpleWsdl11Definition trong các phiên bản Spring-WS hỗ trợ.

WSDL động thuận tiện khi hợp đồng XSD là nguồn sinh operation theo quy ước. WSDL tĩnh cho phép kiểm soát chi tiết hơn, nhưng phải quản lý tham chiếu XSD và bảo đảm runtime vẫn đáp ứng hợp đồng.

Cả hai cách đều đòi hỏi quy trình versioning. Không được thay đổi schema một cách tùy ý chỉ vì công cụ sinh WSDL tự động.

## 7. Tập hợp nhiều schema với XsdSchemaCollection

Một XsdSchema trỏ đến một tài liệu XSD cụ thể. Khi dịch vụ có nhiều schema entrypoint, có thể dùng XsdSchemaCollection. Spring-WS/Spring XML cung cấp CommonsXsdSchemaCollection để tổng hợp nhiều tài liệu và xử lý inlining theo cấu hình.

Giả sử ngoài GetOrderRequest/GetOrderResponse, dịch vụ còn có CancelOrderRequest/CancelOrderResponse trong một file thứ tư: orders-commands-v1.xsd.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:element name="CancelOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="CancelOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="accepted" type="xs:boolean"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

File này thuộc cùng namespace orders, nhưng là một schema entrypoint độc lập cho nhóm operation khác. Muốn sinh WSDL từ cả hai nhóm, có thể đưa chúng vào collection:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.XsdSchemaCollection;
import org.springframework.xml.xsd.commons.CommonsXsdSchemaCollection;

@Configuration
public class MultiSchemaWsdlConfig {

    @Bean
    public XsdSchemaCollection orderSchemas() {
        CommonsXsdSchemaCollection collection =
            new CommonsXsdSchemaCollection(
                new ClassPathResource("xsd/orders-v1.xsd"),
                new ClassPathResource("xsd/orders-commands-v1.xsd")
            );

        collection.setInline(true);
        return collection;
    }

    @Bean(name = "ordersCombined")
    public DefaultWsdl11Definition combinedWsdl(
            XsdSchemaCollection orderSchemas) {

        DefaultWsdl11Definition definition =
            new DefaultWsdl11Definition();

        definition.setPortTypeName("OrderPort");
        definition.setServiceName("OrderService");
        definition.setLocationUri("/ws");
        definition.setTargetNamespace("urn:example:orders:v1");
        definition.setSchemaCollection(orderSchemas);

        return definition;
    }
}
~~~

Các đoạn cấu hình một-schema và collection trên minh họa **hai lựa chọn triển khai**. Nếu chỉ cần một WSDL công khai, chọn phương án thích hợp và thống nhất tên bean; không cần phát hành nhiều bản WSDL cho cùng interface nếu đối tác không có nhu cầu.

### 7.1. Vai trò của setInline(true)

Khi collection được cấu hình inline, implementation cố gắng xử lý các tài liệu được tham chiếu để đưa nội dung schema cần thiết vào kết quả sử dụng collection, ví dụ trong phần wsdl:types. Điều này có thể giảm phụ thuộc vào việc client phải gửi thêm HTTP GET tới những XSD liên quan.

Tuy nhiên:

- Inlining **không biến hai target namespace khác nhau thành một namespace**.
- WSDL kết quả có thể chứa nhiều khối xs:schema với targetNamespace khác nhau.
- Không nên mặc định mọi xs:import, xs:include hoặc external reference đều được xử lý giống nhau trong mọi phiên bản thư viện.
- Khả năng tải, compile và sinh client vẫn phải được xác minh bằng WSDL thực tế.

Nói cách khác, setInline(true) là một công cụ phục vụ **phân phối schema**, không phải cách sửa một hợp đồng có QName hoặc namespace sai.

### 7.2. Chọn schema entrypoint hợp lý

Hai mô hình được dùng phổ biến:

**Mô hình A: Một schema gốc có phụ thuộc**

~~~text
orders-v1.xsd
  +-- include orders-model-v1.xsd
  +-- import common-types-v1.xsd
~~~

Nếu tất cả root message của dịch vụ được mô tả từ orders-v1.xsd, một XsdSchema có thể đủ cho quá trình định nghĩa WSDL, với điều kiện những dependency được resolver xử lý đúng.

**Mô hình B: Nhiều schema gốc cho nhiều nhóm message**

~~~text
orders-v1.xsd             -> GetOrderRequest / GetOrderResponse
orders-commands-v1.xsd    -> CancelOrderRequest / CancelOrderResponse
common-types-v1.xsd       -> Common types được import
~~~

Nếu không có một root schema tổng hợp, collection giúp generator xem xét nhiều entrypoint. Không nên liệt kê lặp lại cả một schema gốc và từng file đã được include vào nó nếu điều đó khiến định nghĩa global bị nạp trùng. Hãy xác định rõ file nào là entrypoint, file nào chỉ có nhiệm vụ chứa kiểu dùng chung.

### 7.3. Có nên gộp mọi miền nghiệp vụ vào một WSDL?

Chưa chắc. Một tổ chức có thể có namespace:

~~~text
urn:example:orders:v1
urn:example:billing:v1
urn:example:customers:v1
~~~

Chúng có thể chia sẻ một schema common nhưng vẫn cần vòng đời, quyền truy cập và versioning riêng. Collection giải quyết vấn đề tổ chức schema, không tự xác định ranh giới service. Việc gộp quá nhiều operation vào một WSDL có thể làm tăng ảnh hưởng khi một nhóm thay đổi schema.

## 8. Công bố metadata không đồng nghĩa với schema validation

Đăng ký XsdSchema và công bố WSDL/XSD là một phần của contract-first. Để kiểm tra các request SOAP nhận vào có đúng schema hay không, cần cấu hình ranh giới validation.

Ví dụ một PayloadValidatingInterceptor:

~~~java
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class SoapValidationConfig implements WsConfigurer {

    private final XsdSchema ordersSchema;

    public SoapValidationConfig(
            @Qualifier("orders-v1") XsdSchema ordersSchema) {
        this.ordersSchema = ordersSchema;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {

        PayloadValidatingInterceptor interceptor =
            new PayloadValidatingInterceptor();

        interceptor.setXsdSchema(ordersSchema);
        interceptor.setValidateRequest(true);
        interceptor.setValidateResponse(true);

        interceptors.add(interceptor);
    }
}
~~~

Ví dụ giả định root schema có đủ message request/response, các import/include được phân giải và ứng dụng có phiên bản Spring-WS tương thích. Với nhiều entrypoint, cần cấu hình validator theo tập schema hoặc cơ chế validation mà version Spring-WS đang dùng hỗ trợ. Không suy ra validator nhận đủ mọi schema chỉ vì WSDL generator làm được.

XSD validation phát hiện thiếu field bắt buộc, sai thứ tự, sai datatype, namespace và facet. Nhưng nó không thể tự quyết định orderId có tồn tại trong database, người gọi có quyền xem đơn hàng, hoặc chữ ký WS-Security có đáng tin không. Các điều kiện đó cần nghiệp vụ, interceptor bảo mật và SOAP Fault được thiết kế riêng.

## 9. Vấn đề URL và reverse proxy

Một ứng dụng Spring-WS có thể chạy nội bộ tại:

~~~text
http://orders-service:8080/ws/orders.wsdl
~~~

và được công bố cho đối tác qua:

~~~text
https://soap.example.com/integration/ws/orders.wsdl
~~~

Nếu WSDL trả soap:address nội bộ, hoặc schemaLocation trỏ tới hostname mà client ngoài hệ thống không truy cập được, quá trình tích hợp sẽ thất bại.

Thiết lập transformWsdlLocations(true) giúp Spring-WS viết lại địa chỉ SOAP service trong WSDL dựa trên request. Nhưng với hệ thống dùng reverse proxy, vẫn cần cấu hình forwarded headers đáng tin cậy và bảo đảm scheme, host, port, context path được nhận diện đúng.

Điều cần kiểm tra độc lập:

| Thành phần | Câu hỏi |
|---|---|
| WSDL URL | Client ngoài hệ thống có tải được orders.wsdl không? |
| soap:address | Địa chỉ trong WSDL có đúng URL SOAP public không? |
| xs:import / xs:include | Các đường dẫn schemaLocation có phân giải từ URL public không? |
| HTTPS/proxy | Có bị đưa về HTTP hoặc hostname nội bộ không? |
| Bảo mật | GET .wsdl và .xsd có bị chặn hoặc redirect sang trang HTML không? |

Một số phiên bản Spring-WS có tùy chọn viết lại schema location riêng. Hành vi thực tế phụ thuộc phiên bản và cấu hình. **transformWsdlLocations không phải cam kết rằng mọi import/include trong XML Schema cũng được sửa đúng**.

## 10. Kiểm thử công bố toàn bộ chuỗi tài liệu

### 10.1. Tải metadata qua HTTP

Ví dụ lệnh kiểm tra từ máy client bên ngoài (chỉ là ví dụ, không phải lệnh đã chạy):

~~~bash
curl -i "https://api.example.test/ws/orders.wsdl"
curl -i "https://api.example.test/ws/orders-v1.xsd"
curl -i "https://api.example.test/ws/orders-model-v1.xsd"
curl -i "https://api.example.test/ws/common-types-v1.xsd"
~~~

Chỉ HTTP 200 chưa đủ. Body phải thực sự là WSDL/XSD, không phải HTML của login page, proxy lỗi hay trang mặc định. Đối chiếu targetNamespace và tên schema thực sự nhận được.

### 10.2. Compile toàn bộ XML Schema

Một XSD có thể là XML well-formed nhưng vẫn không phải schema hợp lệ. Hãy dùng schema-aware compiler để nạp entrypoint và theo toàn bộ import/include. Kiểm tra:

- Namespace import khớp với targetNamespace tài liệu được tải.
- Tất cả global elements/types được tham chiếu có tồn tại.
- Không có khai báo global trùng QName.
- Các type, sequence, occurrence và facet hợp lệ theo XSD.
- Đường dẫn import/include không cần truy cập vào máy cá nhân của người phát triển.

Nếu schema dùng các URL bên ngoài, nên có resolver theo danh sách nguồn đáng tin hoặc bản XSD cục bộ phù hợp; không cho parser tùy ý truy cập mạng khi xử lý đầu vào không tin cậy.

### 10.3. Đọc WSDL đã sinh thay vì đoán

Kiểm tra WSDL thực tế có các thành phần:

~~~xml
<wsdl:types>...</wsdl:types>
<wsdl:message>...</wsdl:message>
<wsdl:portType>...</wsdl:portType>
<wsdl:binding>...</wsdl:binding>
<wsdl:service>...</wsdl:service>
~~~

Với trường hợp một schema, kỳ vọng operation GetOrder được sinh từ GetOrderRequest/GetOrderResponse. Với collection, nếu cần cả operation CancelOrder thì phải xác nhận thực tế nó xuất hiện trong WSDL. Cũng kiểm tra binding SOAP 1.1 hay SOAP 1.2, SOAPAction/action và endpoint location phù hợp cấu hình runtime.

### 10.4. Sinh SOAP client độc lập

Đây là kiểm thử có giá trị cao nhất cho công bố contract:

1. Tải WSDL từ URL mà đối tác sẽ dùng, không lấy XSD trực tiếp từ classpath server.
2. Để công cụ sinh client tự tìm, tải và compile các XSD phụ thuộc.
3. Sinh binding JAXB/JAX-WS hoặc client .NET/ESB đại diện.
4. Gửi request có ord:meta và com:requestId, nhận response chứa ord:OrderSummaryType.
5. Gửi request sai schema và xác nhận lỗi SOAP Fault phù hợp.
6. Lặp lại qua domain HTTPS, proxy và quyền truy cập đúng như triển khai thực.

Nếu client mới chỉ sinh được code khi dùng đường dẫn XSD local của nhà phát triển, công bố contract chưa đạt yêu cầu.

## 11. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| GET /ws/orders.wsdl trả 404 | Bean WSDL hoặc servlet mapping không đúng | Tên bean orders, context, mapping |
| WSDL tải được nhưng XSD 404 | Schema phụ thuộc chưa được công bố hoặc schemaLocation sai | Resolve từng xs:include/xs:import từ URL WSDL |
| Không tìm thấy com:RequestMetaType | Namespace import, prefix hoặc location không khớp | targetNamespace common, import namespace |
| XML Schema báo duplicate type | Cùng global QName bị nạp/định nghĩa nhiều lần | Danh sách entrypoint và đồ thị include |
| WSDL thiếu operation CancelOrder | Chưa thêm schema command vào collection | setSchemaCollection, tên global elements |
| WSDL sinh operation ngoài ý muốn | Global element mang hậu tố Request/Response | Quy ước tên và cấu hình generator |
| soap:address trỏ vào máy nội bộ | Location URI hoặc proxy headers chưa đúng | transformWsdlLocations, forwarded headers |
| SOAP request bị từ chối dù tải WSDL thành công | SOAP version hoặc payload QName không khớp | Content-Type, Envelope namespace, @PayloadRoot |
| Payload sai XSD vẫn tới service | Chưa bật hoặc thiếu schema validation | PayloadValidatingInterceptor, resolver |
| Client cũ hỏng sau deploy | WSDL/XSD đã đổi phá vỡ tương thích | Diff hợp đồng, fixtures và client cũ |

### 11.1. Cẩn thận với khai báo trùng

Khi hai XSD cùng namespace cùng định nghĩa global element GetOrderRequest, không thể cho rằng collection tự chọn một trong hai. Đây thường là mâu thuẫn hợp đồng cần giải quyết từ nguồn. Tách mỗi type/element theo nơi sở hữu rõ ràng và loại bỏ khai báo thừa.

### 11.2. Cẩn thận với đường dẫn local

Ví dụ schemaLocation chỉ đến ổ đĩa Windows, localhost hoặc máy CI nội bộ có thể hoạt động trong một môi trường rồi làm đối tác không nạp được. Hãy giữ tham chiếu tương đối có thể phục vụ qua HTTP hoặc dùng cơ chế inlining được kiểm chứng.

### 11.3. Đừng thay namespace chỉ vì đổi host

Namespace URI và URL của schema có nhiệm vụ khác nhau. Đổi host công bố metadata không bắt buộc đổi QName XML. Thay namespace là thay đổi hợp đồng mà client JAXB và endpoint Spring-WS có thể nhận thấy, dù payload có các trường giống hệt.

## 12. Quản trị phiên bản và bảo mật

Với hợp đồng SOAP dùng trong doanh nghiệp, cần giữ lại một bản WSDL/XSD đã công bố và chạy kiểm thử so sánh trước khi thay đổi. Đặc biệt thận trọng khi:

- Đổi targetNamespace hay tên global request/response element.
- Đổi cấu trúc kiểu XSD, số lần xuất hiện và facet validation.
- Thêm field optional vào response mà client cũ kiểm tra chặt.
- Đổi tên operation do quy ước sinh WSDL tự động.
- Đổi SOAPAction, SOAP version hoặc binding.
- Thay schemaLocation khiến generated client không giải được phụ thuộc.

Một thay đổi phá vỡ tương thích nên được quản lý bằng chiến lược contract version, có thể cung cấp phiên bản v1 và v2 song song khi cần. Với thay đổi chỉ ở code Java hoặc database, cố gắng giữ QName và hành vi SOAP tương thích với client hiện có.

Ngoài ra, WSDL/XSD có thể lộ tên operation và dữ liệu giao dịch. Tùy chính sách tổ chức, metadata có thể được phân phối cho đối tác được phép thay vì để công khai không giới hạn. Khi compile schema, hạn chế truy cập external entities và external schema không đáng tin. Kiểm tra WS-Security, chứng chỉ, chữ ký và quyền truy cập là trách nhiệm khác với schema validation.

## 13. Bài thực hành

Thiết kế dịch vụ OrderService với hai thao tác GetOrder và CancelOrder, trong đó cả hai dùng dữ liệu chung RequestMetaType thuộc namespace common.

Các bước thực hành:

1. Tạo orders-model-v1.xsd trong namespace orders với OrderSummaryType.
2. Tạo common-types-v1.xsd trong namespace common với RequestMetaType.
3. Tạo orders-v1.xsd có GetOrderRequest/GetOrderResponse, include model và import common.
4. Tạo orders-commands-v1.xsd có CancelOrderRequest/CancelOrderResponse.
5. Đăng ký XsdSchema beans để đối tác tải được schema phụ thuộc theo đường dẫn tương đối.
6. Dùng CommonsXsdSchemaCollection cho các schema entrypoint nếu muốn sinh một WSDL chứa cả hai nhóm operation.
7. Công bố WSDL qua DefaultWsdl11Definition; kiểm tra operation, binding, QName, SOAP address.
8. Từ máy client, tải WSDL, resolve tất cả XSD, compile và sinh client độc lập.
9. Gửi một SOAP request hợp lệ và một request thiếu orderId, kiểm tra behavior của endpoint và Fault.
10. Chạy lại sau reverse proxy để bảo đảm URL/schemaLocation vẫn đúng.

**Tiêu chí hoàn thành:** Client không cần truy cập classpath server vẫn tải được mọi tài liệu; WSDL chứa đúng các operation được yêu cầu; các schema compile thành công; runtime nhận đúng payload và xử lý lỗi hợp đồng.

## 14. Checklist trước khi phát hành

- [ ] Đã xác định schema entrypoint, dependency và namespace sở hữu mỗi type.
- [ ] xs:include dùng cho cùng namespace; xs:import dùng cho namespace khác.
- [ ] XsdSchema beans tồn tại trong context của MessageDispatcherServlet.
- [ ] WSDL bean được công bố dưới URL đúng tên và đúng servlet mapping.
- [ ] Mọi xs:include/xs:import có thể được client ngoài hệ thống phân giải hoặc được inline đúng.
- [ ] Không có global QName trùng hoặc tham chiếu tới type không tồn tại.
- [ ] DefaultWsdl11Definition nhận đúng XsdSchema hoặc XsdSchemaCollection.
- [ ] Operation, SOAP version, binding, action và địa chỉ endpoint trong WSDL khớp runtime.
- [ ] Reverse proxy không làm hỏng schemaLocation và không lộ hostname nội bộ.
- [ ] Đã kiểm tra XML Schema validation của request/response riêng với công bố metadata.
- [ ] Đã kiểm thử sinh client thực tế và so sánh với hợp đồng đã phát hành.
- [ ] Chính sách truy cập metadata và parser/XML security phù hợp môi trường tích hợp.

## 15. Ghi nhớ

- **XsdSchema đại diện một XML Schema; XsdSchemaCollection tổ chức nhiều schema** để các thành phần Spring-WS khác dùng.
- **MessageDispatcherServlet giúp phục vụ tài liệu metadata**, còn **DefaultWsdl11Definition dùng XSD sinh WSDL** theo quy ước tên.
- **xs:include không giống xs:import**: khác biệt chủ yếu là quan hệ targetNamespace.
- **Schema trên classpath chưa đủ**: client ngoài hệ thống phải thực sự tải được WSDL và tất cả tài liệu phụ thuộc.
- **Inlining không thay namespace và không tự sửa schema sai**; kiểm thử bản WSDL được công bố là bước bắt buộc.
- **Công bố metadata, xác thực payload và bảo mật SOAP là các trách nhiệm tách biệt**; phối hợp đúng giúp dịch vụ contract-first ổn định khi nhiều hệ thống cùng tích hợp.

**Câu hỏi tự kiểm tra:** Một đối tác tải được orders.wsdl nhưng khi sinh client báo không tìm thấy com:RequestMetaType. Trong orders-v1.xsd có xs:import tới common-types-v1.xsd. Bạn cần kiểm tra những namespace, schemaLocation, XsdSchema bean và URL nào? Khi nào nên công bố riêng common-types-v1.xsd, và khi nào nên dùng XsdSchemaCollection với inlining?

