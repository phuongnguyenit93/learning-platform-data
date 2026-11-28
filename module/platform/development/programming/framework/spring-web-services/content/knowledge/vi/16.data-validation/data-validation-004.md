# Tập hợp nhiều schema và giải quyết import, include

> **Chương:** Kiểm tra dữ liệu  
> **Phạm vi:** SPRING_WEB_SERVICES — xây dựng SOAP service contract-first bằng Spring Web Services (Spring-WS), thiết kế XSD/WSDL, dùng JAXB/OXM và endpoint/client, kiểm soát SOAP Fault, interceptor, XML security, WS-Security và tương thích tích hợp doanh nghiệp.

## 1. Vì sao một SOAP service cần nhiều XSD?

Một SOAP service thực tế hiếm khi chỉ dùng một tệp XSD. Hợp đồng đơn hàng có thể chia phần tử request/response theo nghiệp vụ, định nghĩa các kiểu đơn hàng trong một tệp riêng và dùng lại metadata chung như `correlationId` từ một namespace khác. Việc chia nhỏ giúp tổ chức và tái sử dụng schema, nhưng gây ra hai vấn đề mới:

1. **Kết hợp schema:** trình biên dịch và trình kiểm tra XML phải nhìn thấy các khai báo type/element được tham chiếu xuyên tệp.
2. **Giải quyết vị trí phụ thuộc:** khi `xs:include` hoặc `xs:import` dẫn tới một XSD khác, hệ thống phải tìm đúng tài nguyên đó cả khi chạy unit test, trong Spring Boot JAR và khi client tải WSDL từ HTTP.

Với Spring-WS, cũng cần phân biệt **dùng bộ schema để validation** với **đưa bộ schema vào WSDL công bố**. Một WSDL tải được chưa chứng minh server đã validate request theo tất cả XSD. Ngược lại, server dùng schema nội bộ hợp lệ vẫn có thể công bố WSDL có đường dẫn import hỏng khiến client không sinh mã được.

Sau bài học, bạn có thể:

- Phân biệt `xs:include`, `xs:import` và cơ chế tham chiếu XSD ở tầng WSDL.
- Thiết kế bộ XSD có **hai namespace** và các phụ thuộc tương đối rõ ràng.
- Cấu hình `XsdSchemaCollection` và `CommonsXsdSchemaCollection` cho Spring-WS.
- Sử dụng `PayloadValidatingInterceptor` để kiểm tra nhiều schema theo contract.
- Xác minh dependency resolution và lỗi thường gặp khi đóng gói classpath/JAR, công bố WSDL, sinh JAXB client.
- Thiết kế chiến lược XML Catalog, giới hạn truy cập tài nguyên ngoài, kiểm thử validation và tương thích.

## 2. Ba lớp của bài toán: hợp đồng, nạp tài nguyên và thực thi

~~~mermaid
flowchart TD
    A["WSDL 1.1: message, operation, binding, service"] --> B["wsdl:types / XSD entrypoint"]
    B --> C["orders.xsd — namespace orders"]
    C --> D["xs:include → order-types.xsd (cùng namespace)"]
    C --> E["xs:import → common.xsd (namespace khác)"]
    E --> F["xs:include → common-types.xsd"]
    C --> V["Schema collection / validator"]
    D --> V
    E --> V
    F --> V
    V --> G["Spring-WS endpoint / JAXB / SOAP client"]
~~~

Có ba câu hỏi khác nhau cần trả lời:

| Câu hỏi | Tầng chịu trách nhiệm | Dấu hiệu lỗi |
|---|---|---|
| Những kiểu/phần tử XML nào hợp lệ? | XSD namespace, global elements, types, constraints | XML instance không thỏa type, order, min/max, pattern |
| Tệp tham chiếu nằm ở đâu? | `schemaLocation`, base URI, classpath, catalog/resource resolver | `Cannot resolve ...`, `src-resolve`, lỗi đọc schema |
| Server/client dùng hợp đồng như thế nào? | Spring-WS validator, WSDL publication, JAXB/XJC | Server nhận dữ liệu sai hoặc client không resolve được WSDL/XSD |

Trong contract-first, **global element QName** của request/response mới quyết định SOAP Body payload. Tên file như `orders.xsd`, tên type Java được XJC sinh ra và HTTP URL tải WSDL là các chi tiết khác, không thay thế QName.

## 3. `xs:include` và `xs:import` khác nhau ở đâu?

### 3.1. `xs:include`: kết hợp các thành phần cùng namespace

`xs:include` đưa các khai báo từ một schema khác vào tập thành phần schema hiện tại. Nó được dùng khi tệp được include có **cùng `targetNamespace`** hoặc **không khai báo `targetNamespace`** trong trường hợp *chameleon include*.

~~~xml
<xs:include schemaLocation="order-types.xsd"/>
~~~

Nếu `orders.xsd` khai báo `targetNamespace="urn:example:orders:v1"` và `order-types.xsd` cũng khai báo URI đó, include là hợp lệ. Nó cho phép `orders.xsd` tham chiếu type `ord:OrderIdType` từ tệp kia.

### 3.2. `xs:import`: dùng khai báo từ namespace khác

`xs:import` cho phép schema của một namespace dùng type/element từ **namespace khác**, kể cả trường hợp import các khai báo không có namespace theo quy tắc XSD.

~~~xml
<xs:import
    namespace="urn:example:common:v1"
    schemaLocation="../common/common.xsd"/>
~~~

Ở đây:

- `namespace` là URI định danh **namespace được nhập**.
- `schemaLocation` là **gợi ý vị trí tài nguyên** để tìm XSD, không phải namespace.
- Prefix `com` được khai báo riêng ở `xs:schema` để dùng QNames như `com:RequestMetadataType`.
- `schemaLocation` có thể không xuất hiện trong một số import; khi đó môi trường biên dịch phải có cách khác để nạp schema được tham chiếu. Không giả định mọi validator sẽ tự tìm ra bằng namespace URI.

Một ví dụ không hợp lệ về mặt thiết kế:

~~~xml
<!-- Sai khi namespace của common.xsd là urn:example:common:v1 -->
<xs:include schemaLocation="../common/common.xsd"/>
~~~

Hai schema thuộc namespace khác nhau không thể được kết hợp như cùng một không gian khai báo qua `xs:include`.

### 3.3. Bảng so sánh

| Tiêu chí | `xs:include` | `xs:import` |
|---|---|---|
| Quan hệ namespace | Cùng `targetNamespace` hoặc tệp con không namespace | Namespace khác hoặc không namespace |
| Thuộc tính chính | `schemaLocation` | `namespace` và `schemaLocation` (location có thể tùy chọn) |
| Phạm vi dùng | Chia một namespace thành nhiều tệp | Dùng type/element của namespace khác |
| Cách dùng type | `ord:OrderIdType` trong namespace hiện tại | `com:RequestMetadataType` từ namespace imported |
| Kiểu lỗi điển hình | Included schema có namespace không tương thích; định nghĩa trùng | Import không resolve được; QName imported không khai báo |
| Tác động tương thích | Thay đổi các thành phần cùng namespace | Kéo theo sự phụ thuộc vào contract namespace khác |

**Nguyên tắc:** dùng `include` để tách file trong một namespace; dùng `import` để kết nối các namespace khác nhau. Không dùng `include` chỉ vì đường dẫn file gần nhau.

### 3.4. Chameleon include là gì?

Một tệp `shared-fragments.xsd` **không có `targetNamespace`** có thể được include vào schema có namespace. Các khai báo phù hợp sẽ mang namespace của schema đang include theo cơ chế *chameleon*. Điều này đôi khi tiện cho thư viện schema dùng lại, nhưng dễ gây khó hiểu:

- Cùng một file có thể trở thành các khai báo thuộc nhiều namespace khác nhau khi được include ở nhiều nơi.
- Các tham chiếu QName, kiểu built-in và namespace mặc định phải được thiết kế cẩn thận.
- Có thể phát sinh trùng tên global element/type trong namespace đích.
- Code generation và hệ thống catalog có thể khó chẩn đoán hơn khi nhiều bản include cùng file.

Với contract SOAP doanh nghiệp, **ưu tiên namespace tường minh và đường dẫn rõ ràng** trừ khi có lý do cụ thể để dùng chameleon. Đừng áp dụng chameleon như một cách né `xs:import`.

## 4. Bộ XSD thực hành: common và orders

Ví dụ thiết kế một dịch vụ tra cứu đơn hàng. Tập schema gồm bốn file:

~~~text
src/main/resources/xsd/
├── common/
│   ├── common-types.xsd
│   └── common.xsd
└── orders/
    ├── order-types.xsd
    └── orders.xsd
~~~

Tập phụ thuộc:

~~~mermaid
flowchart LR
    A["orders/orders.xsd"] -->|"include (same namespace)"| B["orders/order-types.xsd"]
    A -->|"import common namespace"| C["common/common.xsd"]
    C -->|"include (same namespace)"| D["common/common-types.xsd"]
~~~

Tất cả là tài nguyên **được đóng gói cùng ứng dụng**. Các `schemaLocation` tương đối được resolve theo vị trí tài nguyên chứa tham chiếu, không dựa trên thư mục hiện tại của shell.

### 4.1. `common/common-types.xsd` — simple type dùng chung

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:com="urn:example:common:v1"
    targetNamespace="urn:example:common:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="CorrelationIdType">
    <xs:restriction base="xs:string">
      <xs:minLength value="1"/>
      <xs:maxLength value="64"/>
      <xs:pattern value="[A-Za-z0-9-]+"/>
    </xs:restriction>
  </xs:simpleType>

</xs:schema>
~~~

### 4.2. `common/common.xsd` — include type cùng namespace

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:com="urn:example:common:v1"
    targetNamespace="urn:example:common:v1"
    elementFormDefault="qualified">

  <xs:include schemaLocation="common-types.xsd"/>

  <xs:complexType name="RequestMetadataType">
    <xs:sequence>
      <xs:element name="correlationId"
                  type="com:CorrelationIdType"/>
      <xs:element name="sourceSystem" type="xs:string"
                  minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

</xs:schema>
~~~

Ở `common.xsd`, tên type `com:CorrelationIdType` được định nghĩa trong file included **cùng namespace**. Dùng QName có prefix `com` hay không là lựa chọn biểu diễn theo namespace; trong ví dụ này khai báo rõ để dễ đọc.

### 4.3. `orders/order-types.xsd` — kiểu đơn hàng

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="OrderIdType">
    <xs:restriction base="xs:string">
      <xs:minLength value="5"/>
      <xs:maxLength value="32"/>
      <xs:pattern value="[A-Z0-9-]+"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="OrderStatusType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="NEW"/>
      <xs:enumeration value="PROCESSING"/>
      <xs:enumeration value="DONE"/>
    </xs:restriction>
  </xs:simpleType>

</xs:schema>
~~~

### 4.4. `orders/orders.xsd` — entrypoint gồm import và include

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    xmlns:com="urn:example:common:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:include schemaLocation="order-types.xsd"/>

  <xs:import
      namespace="urn:example:common:v1"
      schemaLocation="../common/common.xsd"/>

  <xs:element name="GetOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="metadata"
                    type="com:RequestMetadataType"/>
        <xs:element name="orderId"
                    type="ord:OrderIdType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId"
                    type="ord:OrderIdType"/>
        <xs:element name="status"
                    type="ord:OrderStatusType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

Đây là schema **entrypoint**: dùng nó để mô tả SOAP payload root và nạp các XSD phụ thuộc. Những khai báo nội bộ được đặt sao cho `GetOrderRequest`, `GetOrderResponse` là global elements dùng trong WSDL 1.1 document/literal.

### 4.5. XML hợp lệ trông như thế nào?

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:com="urn:example:common:v1">
  <ord:metadata>
    <com:correlationId>REQ-12345</com:correlationId>
    <com:sourceSystem>BACKOFFICE</com:sourceSystem>
  </ord:metadata>
  <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

Phân tích namespace:

- `ord:GetOrderRequest` là global element thuộc namespace orders.
- `ord:metadata` là **local element được khai báo trong `orders.xsd`**, nên thuộc orders namespace do `elementFormDefault="qualified"`.
- `com:correlationId` và `com:sourceSystem` được khai báo **trong `RequestMetadataType` của common schema**, nên thuộc common namespace.
- `ord:orderId` là local element của orders schema, dù type của nó được nạp từ `order-types.xsd`.

Điểm dễ sai: **namespace của element do chỗ nó được khai báo quyết định, không tự động lấy namespace của type tham chiếu.** Đặt `com:metadata` thay cho `ord:metadata` sẽ tạo element QName khác và không hợp lệ theo schema ví dụ.

Response mẫu:

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:status>PROCESSING</ord:status>
</ord:GetOrderResponse>
~~~

## 5. Base URI và schemaLocation: vì sao chạy ở IDE mà JAR lại lỗi?

Các giá trị:

~~~text
order-types.xsd
../common/common.xsd
~~~

là **đường dẫn tương đối**, được tính từ **base URI của chính tài liệu XSD chứa tham chiếu**. Nếu một validator chỉ được cấp một `InputStream` mà không có `systemId`/base URI, engine có thể không biết thư mục của `orders.xsd` để tìm file đi kèm.

| Môi trường | Điều cần lưu ý |
|---|---|
| IDE/unit test | Schema nằm trên filesystem, đường dẫn tương đối thường dễ resolve |
| JAR/Boot executable JAR | Tài nguyên nằm trong classpath/JAR; đừng giả định có đường dẫn file vật lý |
| CI với working directory khác | Relative schemaLocation không được phụ thuộc CWD |
| WSDL phục vụ qua HTTP | Client phải tìm được các schema theo URL tương đối hoặc từ nội dung inline |
| XSD nhập từ URL bên ngoài | Có nguy cơ network dependency, độ trễ, thay đổi phiên bản và SSRF nếu không kiểm soát |

Một ví dụ dễ lỗi:

~~~java
// Không đủ thông tin vị trí gốc để đảm bảo import/include resolve:
InputStream in = resource.getInputStream();
Schema schema = schemaFactory.newSchema(new StreamSource(in));
~~~

Cách an toàn hơn là giữ **base URI** của tài nguyên hoặc cung cấp resource resolver có policy rõ. Với bộ schema nằm trong ứng dụng Spring-WS, nên dùng `ClassPathResource`, `XsdSchemaCollection` cùng cơ chế resolution phù hợp, rồi kiểm tra lại trên artifact được đóng gói. Không đổi `schemaLocation` trong XSD thành đường dẫn tuyệt đối tại máy phát triển.

## 6. Tập hợp schema trong Spring-WS

Spring-WS có hai abstraction liên quan:

- `XsdSchema`: một schema XSD, ví dụ `SimpleXsdSchema` từ `ClassPathResource`.
- `XsdSchemaCollection`: tập schema dùng cùng nhau, thích hợp với nhiều XSD và quan hệ import/include.

Một implementation thường dùng là `org.springframework.xml.xsd.commons.CommonsXsdSchemaCollection` (dựa trên Apache XmlSchema). Với đồ thị `orders.xsd → common.xsd → common-types.xsd`, schema collection giúp tổ chức dữ liệu cần cho WSDL và validator.

### 6.1. Cấu hình collection bằng classpath resource

~~~java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.xml.xsd.XsdSchemaCollection;
import org.springframework.xml.xsd.commons.CommonsXsdSchemaCollection;

@Configuration
public class OrderSchemaConfig {

    @Bean
    public XsdSchemaCollection orderSchemas() {
        CommonsXsdSchemaCollection schemas =
                new CommonsXsdSchemaCollection(
                    new ClassPathResource("xsd/orders/orders.xsd"));

        // Cho phép inlining schema khi xuất WSDL theo implementation.
        schemas.setInline(true);
        return schemas;
    }
}
~~~

**Các điều kiện quan trọng:**

1. `orders.xsd` là **entrypoint**; nó đã tham chiếu các file khác bằng `include/import`.
2. Thư mục dưới `src/main/resources/xsd` phải được đóng gói giữ nguyên vào classpath/JAR.
3. `setInline(true)` ảnh hưởng cách đưa schema vào WSDL; nó **không tự bật XSD validation** và không thay đổi global element QName.
4. Tùy phiên bản Spring-WS, cần có Apache XmlSchema đúng phiên bản trên classpath. Đồng bộ dependency theo BOM/stack Spring Boot, tránh tự trộn các thế hệ API.
5. Không thêm cùng một tệp vào collection nhiều lần nếu nó đã được nhập/include mà chưa kiểm chứng công cụ nạp schema có loại trùng hay không.

Nếu runtime/JAR không resolve được relative paths, phải xem base URI và resource resolver của implementation. **Collection không tự sửa mọi đường dẫn bị sai**.

### 6.2. Khi nào SimpleXsdSchema đủ?

~~~java
@Bean
public XsdSchema ordersSchema() {
    return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders/orders.xsd"));
}
~~~

Với schema đơn giản hoặc môi trường có resolver xử lý dependencies phù hợp, `SimpleXsdSchema` có thể đáp ứng. Với nhiều namespace và nhu cầu **inline XSD trong WSDL**, `CommonsXsdSchemaCollection` thường phù hợp hơn. Quyết định phải dựa trên cấu trúc dependency và kết quả runtime, không chỉ dựa vào tên class.

### 6.3. Nhiều root cùng namespace

Nếu `orders.xsd` và `returns.xsd` cùng include `order-types.xsd`, hai entrypoint đó có thể được biên dịch theo các ngữ cảnh khác nhau. Đưa cả hai vào một collection, hoặc gộp toàn bộ declaration một cách tùy ý, có thể làm xuất hiện **global definition bị trùng**.

Nên xác định rõ root nào là nguồn công bố cho từng WSDL, tập schema nào dùng cho validation, và tên toàn cục nào chỉ được định nghĩa một lần. Khi nhiều service chia sẻ namespace nhưng nâng version khác nhau, cần thiết kế vòng đời và phạm vi collection để tránh một update ảnh hưởng toàn hệ thống.

## 7. Công bố WSDL từ XsdSchemaCollection

`DefaultWsdl11Definition` có khả năng xây WSDL 1.1 từ một tập XSD. Ví dụ bean dùng `orderSchemas` của mục 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.xml.xsd.XsdSchemaCollection;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;

@Configuration
public class OrderWsdlConfig {

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(
            XsdSchemaCollection orderSchemas) {
        DefaultWsdl11Definition wsdl =
                new DefaultWsdl11Definition();

        wsdl.setPortTypeName("OrdersPort");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace("urn:example:orders:v1");
        wsdl.setSchemaCollection(orderSchemas);
        return wsdl;
    }
}
~~~

Nếu `MessageDispatcherServlet` được map ở `/ws/*`, URL thường là:

~~~text
GET http://localhost:8080/ws/orders.wsdl
~~~

Từ các global elements `GetOrderRequest` và `GetOrderResponse`, generator thường tạo operation `GetOrder` theo quy tắc hậu tố. **Không dựa hoàn toàn vào tên để suy đoán:** tải WSDL thực và kiểm tra `portType`, `binding`, `service`, `soap:address`, `message` và `wsdl:part/@element`.

### 7.1. WSDL import không thay cho XSD import

| Cú pháp | Vai trò |
|---|---|
| `xs:include` | Kết hợp các khai báo XSD cùng namespace |
| `xs:import` | Sử dụng các khai báo XSD từ namespace khác |
| `wsdl:import` | Tham chiếu **tài liệu WSDL 1.1 khác** |
| `wsdl:types` | Chứa hoặc tham chiếu định nghĩa type/schema dữ liệu |
| `wsdl:message/wsdl:part/@element` | Chỉ global element dùng làm SOAP document/literal payload |

Không dùng `wsdl:import` để “chữa” lỗi `xs:import` trong XSD. Hai cơ chế ở hai tầng khác nhau và cần resolver tương ứng.

### 7.2. Inlining hay để external references?

- **Inline:** công cụ đưa nhiều schema vào `wsdl:types`, giảm số URL phải tải nhưng có thể làm WSDL lớn và dễ lộ lỗi trùng/không thống nhất namespace.
- **External:** WSDL hoặc XSD giữ các `schemaLocation` references, đòi client có thể resolve toàn bộ URL/tài nguyên liên quan, nhưng thuận lợi nếu tổ chức chia sẻ schema độc lập.

`CommonsXsdSchemaCollection#setInline(true)` hỗ trợ hướng inlining; tuy nhiên **không bảo đảm mọi output trong mọi version sẽ chỉ còn một file duy nhất**. Hãy tải WSDL qua HTTP, đọc các import/include thực, kiểm tra namespace và thử một công cụ sinh JAXB client từ chính WSDL đó.

### 7.3. WSDL đã được đối tác phê duyệt

Một số hệ thống cần WSDL **tĩnh** vì nội dung message, binding, policy và namespace là hợp đồng đã ký kết. Khi đó, schema collection vẫn có thể dùng để validation nội bộ, nhưng không nên thay WSDL công khai chỉ để tiện cho Spring-WS.

Đảm bảo `soap:address` phù hợp host/scheme/path nhìn từ bên ngoài qua reverse proxy/TLS termination; các `schemaLocation` công bố phải tải được từ hệ thống client, không chỉ từ localhost server.

## 8. XSD validation với nhiều schema

`PayloadValidatingInterceptor` có thể được cấu hình với `XsdSchemaCollection` để kiểm tra SOAP payload theo tập các schema đã nạp:

~~~java
package com.example.orders.config;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.XsdSchemaCollection;

@Configuration
@EnableWs
public class OrdersValidationConfig implements WsConfigurer {

    private final XsdSchemaCollection orderSchemas;

    public OrdersValidationConfig(XsdSchemaCollection orderSchemas) {
        this.orderSchemas = orderSchemas;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validator =
                new PayloadValidatingInterceptor();

        validator.setXsdSchemaCollection(orderSchemas);
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);

        interceptors.add(validator);
    }
}
~~~

Lưu ý: xác minh API và cách nạp collection với **version Spring-WS thực** của project. Nếu ứng dụng đã có lớp `@EnableWs`, tích hợp `WsConfigurer` vào cấu hình chủ quản thay vì vô ý tạo nhiều hạ tầng annotation-driven. Mã ví dụ chưa có endpoint, servlet và logic nghiệp vụ.

Validator của ví dụ cần hiểu:

- `ord:GetOrderRequest` / `ord:GetOrderResponse` thuộc orders namespace.
- `ord:metadata` là phần tử của orders namespace nhưng **type** là `com:RequestMetadataType`.
- `com:correlationId` có pattern và maxLength từ `common-types.xsd`.
- `ord:orderId` có pattern và giới hạn độ dài từ `order-types.xsd`.
- `ord:status` có enum `NEW`, `PROCESSING`, `DONE`.

### 8.1. XSD validation và các trách nhiệm khác

| Điều cần kiểm tra | XSD validation làm được? | Bộ phận còn lại |
|---|---|---|
| Global element QName và thứ tự child elements | Có | Endpoint routing vẫn cần đúng QName |
| Pattern/length của correlationId và orderId | Có | — |
| Enum của trạng thái đơn hàng | Có | — |
| Đơn hàng tồn tại trong database | Không | Business service |
| Caller được phép xem đơn hàng | Không | Authentication và business authorization |
| Chữ ký SOAP, timestamp, chứng chỉ | Không bởi XSD Body | WS-Security/TLS stack |
| Dung lượng MIME attachment/mã độc trong file | Không đầy đủ | Transport limits, file security |

Có XSD và JAXB-generated classes **không đồng nghĩa runtime đã bật validation**. Phải chủ động cài validator và gửi request sai schema để chứng minh nó từ chối.

### 8.2. Validation SOAP Body khác validation Envelope

Bộ XSD ở mục 4 khai báo **payload root** `GetOrderRequest`, không định nghĩa `soapenv:Envelope`. Khi dùng validator độc lập, validate XML bắt đầu từ global element đó. Khi gửi request qua HTTP, SOAP Envelope được parser/message factory của Spring-WS xử lý và validator có thể được áp dụng trên **payload**.

Không dùng một XSD của nghiệp vụ để thay kiểm tra SOAP version, Header security, MTOM attachments hay transport metadata.

### 8.3. Nhiều service trên một servlet

Nếu có hai contract orders và invoices trong cùng context, một interceptor chứa **chỉ** schema orders có thể từ chối payload invoices. Cần chọn rõ phạm vi:

- Collection chứa đầy đủ global elements và types của các service được kiểm tra, không trùng khai báo.
- Interceptor áp dụng chọn lọc theo endpoint mapping hoặc tách servlet/context có chủ đích.
- Có test dương tính và âm tính cho **từng namespace** và từng version.

Đừng giả định validator chọn schema bằng tên Java method; dữ liệu thực là XML QName và tập schema được cấp.

## 9. Kiểm tra độc lập XSD và thử dữ liệu biên

Trước khi tạo Spring endpoint hoặc công bố WSDL, nên **biên dịch và validate bộ XSD độc lập**. Điều này tách lỗi thiết kế schema khỏi lỗi servlet, SOAPAction, endpoint mapping và JAXB.

### 9.1. Dùng xmllint khi có môi trường hỗ trợ

Giả sử lưu XML payload của `GetOrderRequest` ở `payload.xml` trong thư mục gốc dự án. Trong môi trường có `xmllint`:

~~~bash
xmllint --nonet --noout \
  --schema src/main/resources/xsd/orders/orders.xsd \
  payload.xml
~~~

`--nonet` hạn chế việc truy cập mạng trong quá trình nạp phụ thuộc; các `schemaLocation` cục bộ `order-types.xsd` và `../common/common.xsd` vẫn cần tồn tại và được truy cập từ file entrypoint. Lệnh trên là **hướng dẫn chạy ở project ví dụ**, không phải bài test đã được thực thi trong tài liệu.

Chỉ truyền **XML payload root**, không phải cả SOAP Envelope, vì `orders.xsd` không khai báo global element `soap:Envelope`.

### 9.2. Java JAXP SchemaFactory trong unit test

Trên JDK hiện đại, `javax.xml.validation.SchemaFactory` có thể biên dịch một entrypoint XSD có import/include. Một cách kiểm thử **local test fixtures**:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.File;
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.xml.sax.SAXException;

class OrdersSchemaTest {
    private Schema schema;

    @BeforeEach
    void compileSchemas() throws Exception {
        SchemaFactory factory =
                SchemaFactory.newInstance(
                    XMLConstants.W3C_XML_SCHEMA_NS_URI);

        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");

        // Chỉ dành cho test có các XSD là file local tin cậy.
        // Production nên dùng catalog/resolver giới hạn chặt hơn.
        factory.setProperty(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "file");

        schema = factory.newSchema(new File(
                "src/main/resources/xsd/orders/orders.xsd"));
    }

    private void validate(String xml) throws Exception {
        Validator validator = schema.newValidator();
        validator.validate(
                new StreamSource(new StringReader(xml)));
    }

    @Test
    void acceptsRequestReferencingCommonTypes() throws Exception {
        String xml = """
            <o:GetOrderRequest
                xmlns:o="urn:example:orders:v1"
                xmlns:c="urn:example:common:v1">
              <o:metadata>
                <c:correlationId>REQ-12345</c:correlationId>
              </o:metadata>
              <o:orderId>ORD-1001</o:orderId>
            </o:GetOrderRequest>
            """;

        validate(xml);
    }

    @Test
    void rejectsCorrelationIdViolatingImportedPattern() {
        String xml = """
            <o:GetOrderRequest
                xmlns:o="urn:example:orders:v1"
                xmlns:c="urn:example:common:v1">
              <o:metadata>
                <c:correlationId>has spaces</c:correlationId>
              </o:metadata>
              <o:orderId>ORD-1001</o:orderId>
            </o:GetOrderRequest>
            """;

        assertThrows(SAXException.class,
                () -> validate(xml));
    }
}
~~~

**Giới hạn chủ đích:**

- `new File("src/main/resources/...")` ở đây giả định test chạy từ **thư mục gốc dự án**. Nó không phải cách truy cập resource đáng tin cậy khi chạy production trong executable Spring Boot JAR.
- `ACCESS_EXTERNAL_SCHEMA="file"` cho phép compiler nạp các file XSD local; đây là **mức quyền có giới hạn trong bài test** trên tập schema được review, không phải cấu hình tối thiểu an toàn cho môi trường nhận schema do client cung cấp.
- Khi triển khai production, ưu tiên catalog hoặc resolver chỉ cho phép các tài nguyên đã đóng gói/xác minh, đồng thời xem cách provider xử lý `ACCESS_EXTERNAL_SCHEMA` khi có resolver.
- `Schema` đã biên dịch có thể được dùng làm cơ sở tạo validators; **không chia sẻ một đối tượng `Validator` qua nhiều thread** khi chưa có cơ chế đồng bộ. Tạo validator riêng cho từng lượt kiểm tra.
- Test trên chỉ chứng minh XSD composition và facets; không chứng minh Spring-WS interceptor, SOAP Fault hoặc WSDL công bố đúng.

### 9.3. Bài test âm tính nên có

| Thay đổi XML đầu vào | Kết quả mong đợi |
|---|---|
| Bỏ `ord:metadata` | Không hợp lệ; field bắt buộc |
| Đổi `ord:metadata` thành `com:metadata` | Không hợp lệ; element QName khác |
| Bỏ `com:correlationId` | Không hợp lệ theo common metadata type |
| `com:correlationId` có khoảng trắng | Không hợp lệ theo pattern |
| Đổi `ord:orderId` thành `ord:orderCode` | Không hợp lệ theo orders.xsd |
| Đưa `ord:orderId` lên trước `ord:metadata` | Không hợp lệ theo `xs:sequence` |
| `ord:orderId` quá ngắn hoặc có chữ thường | Không hợp lệ theo `OrderIdType` |
| `ord:status` là `ARCHIVED` | Không hợp lệ theo enum của `OrderStatusType` |
| Đổi prefix `com` thành `c`, giữ URI | Vẫn hợp lệ |
| Đổi URI common từ `v1` sang `v2` chỉ trong instance | Không hợp lệ vì child QNames khác |

### 9.4. Phân biệt compile schema với validate document

Hai trạng thái lỗi cần báo riêng:

1. **Schema compilation failed:** thiếu included/imported XSD, namespace sai, unresolved type, global definition trùng. Validator chưa sẵn sàng chạy.
2. **Instance validation failed:** bộ schema compile được nhưng dữ liệu XML không thỏa constraint.

Một ứng dụng không nên tiếp tục nhận request như thể contract đã được bảo vệ nếu bộ schema quan trọng không compile được ở startup. Nên **fail fast** với cấu hình validation bắt buộc và log tên resource/cause ở nội bộ (không đưa đường dẫn nhạy cảm vào SOAP Fault).

## 10. XML Catalog và resource resolver: làm việc offline và an toàn

### 10.1. Vì sao không nên tải schema từ Internet?

Một XSD đôi khi được công bố với `schemaLocation="https://schemas.partner.example/..."`. Nếu runtime tự tải qua mạng mỗi lần khởi tạo hoặc validate, hệ thống phụ thuộc vào:

- DNS, proxy, firewall và khả năng mạng ở môi trường triển khai.
- Nội dung XSD có thể bị thay đổi mà không đi qua version review.
- Lỗi timeout, SSRF hoặc truy xuất host nội bộ nếu URI được điều khiển bởi input chưa tin cậy.
- Phụ thuộc vào môi trường bên ngoài khi dựng CI hoặc xử lý SOAP production.

**Đừng đồng nhất `namespace="https://..."` với yêu cầu phải tải URL đó.** Namespace là định danh logic; `schemaLocation` và catalog/resolver mới chi phối nơi nạp XSD.

### 10.2. Chiến lược đề xuất

Công bố một **mapping có kiểm soát** từ định danh/URI của schema đã chốt sang resource tin cậy:

~~~text
Logical namespace:
  urn:example:common:v1

Known schema systemId:
  https://schemas.partner.example/common/v1/common.xsd

Local approved copy:
  classpath:/xsd/common/common.xsd
~~~

Tùy parser/framework, có thể dùng XML Catalog (OASIS XML Catalog hoặc JAXP Catalog API) hay một `LSResourceResolver` để giải quyết hệ thống phụ thuộc. Nếu dùng `org.w3c.dom.ls.LSResourceResolver`, callback có thể xét `namespaceURI`, `systemId` và `baseURI` rồi trả `LSInput` trỏ tới tài nguyên **whitelist**.

Chính sách tốt:

1. Chỉ tải từ những XSD thuộc **phiên bản contract đã duyệt**.
2. Không cho caller SOAP truyền một URL rồi yêu cầu parser tự đọc nó.
3. Dùng các đường dẫn relative của bộ XSD packaged để resolution tái lập được.
4. Với mọi phụ thuộc, đảm bảo có base URI/systemId rõ ràng và không mơ hồ.
5. Giới hạn `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` theo policy provider. Nếu đặt giá trị rỗng để chặn mọi truy cập ngoài, cần **thử rằng catalog/resolver của bạn vẫn nạp được các dependency nội bộ**.
6. Không chấp nhận tắt bảo vệ XML parser chỉ để “sửa lỗi include”.
7. Kiểm thử khi **mất Internet** và khi schema remote trả lỗi; service vẫn phải khởi động nếu đã đóng gói đủ dependencies.

### 10.3. Ví dụ lỗi do thiếu base URI

Xét code:

~~~java
InputStream in = rootResource.getInputStream();
StreamSource root = new StreamSource(in);
// root chưa có systemId; đường dẫn ../common/common.xsd
// có thể không resolve được.
Schema schema = factory.newSchema(root);
~~~

Cách sửa về mặt nguyên lý:

~~~java
StreamSource root = new StreamSource(
        rootResource.getInputStream());
root.setSystemId(rootResource.getURL().toExternalForm());

Schema schema = factory.newSchema(root);
~~~

Đoạn này minh họa ý nghĩa của `systemId`. Nó yêu cầu stream được đóng phù hợp và vẫn phụ thuộc provider có thể truy cập URL resource (đặc biệt trong nested JAR) hay không. Với production, nên chọn cơ chế framework/catalog đã thử trên **executable artifact thực** thay vì giả định mọi `jar:` URL đều được JAXP hỗ trợ giống file URL.

### 10.4. Đường dẫn nào nên ghi trong XSD?

Trong bộ ví dụ:

~~~xml
<xs:include schemaLocation="order-types.xsd"/>
<xs:import
    namespace="urn:example:common:v1"
    schemaLocation="../common/common.xsd"/>
~~~

là các URI tương đối thông thường. Tránh:

~~~xml
<!-- Không portable -->
<xs:include schemaLocation="C:\Users\me\schemas\order-types.xsd"/>
~~~

và tránh mặc định dùng:

~~~xml
<!-- Chỉ dùng khi implementation có resolver hiểu classpath: -->
<xs:include schemaLocation="classpath:/xsd/orders/order-types.xsd"/>
~~~

`classpath:` là cú pháp resource hữu ích trong Spring Java configuration, nhưng **không phải schemaLocation URI chung được mọi XML Schema compiler/client hiểu**. Giữ XSD portable hoặc có resolver/catalog được công bố rõ cho đối tác.

## 11. Đóng gói và công bố hợp đồng qua HTTP

### 11.1. Hai hành trình khác nhau của cùng một schema

**Đường runtime server:**

~~~text
src/main/resources/xsd/orders/orders.xsd
   → ClassPathResource
   → CommonsXsdSchemaCollection
   → PayloadValidatingInterceptor
   → validate SOAP payload
~~~

**Đường runtime client:**

~~~text
GET /ws/orders.wsdl
   → wsdl:types / schema imports
   → GET or inline XSD dependencies
   → generate JAXB / JAX-WS / CXF / .NET model
   → send SOAP request
~~~

Đường server có thể hoạt động hoàn toàn bằng classpath, trong khi đường client có thể phải tải schema qua HTTP. Phải kiểm tra riêng.

### 11.2. Reverse proxy làm thay đổi URL công bố

Một dịch vụ bên trong chạy `http://127.0.0.1:8080/ws` nhưng đối tác truy cập `https://api.example.test/soap/orders`. WSDL công bố không được chứa các URL chỉ truy cập được từ máy chủ nội bộ nếu client cần tải tài nguyên bên ngoài.

Kiểm tra từ **góc nhìn client**:

- `soap:address location` có scheme/host/path đúng.
- Mọi imported XSD references resolve được khi dùng URL công bố.
- Relative `schemaLocation` giữ ý nghĩa đúng sau khi proxy rewrite path.
- Không vô tình để lộ localhost, internal hostnames, filesystem path hoặc credentials.
- TLS certificate/truststore của đường tải WSDL và đường SOAP POST có phù hợp đối tác không?

`MessageDispatcherServlet#setTransformWsdlLocations(true)` có thể hỗ trợ điều chỉnh location được công bố theo request, nhưng **không thay thế** cấu hình reverse proxy/forwarded headers đáng tin cậy và kiểm tra URL tải schema.

### 11.3. Contract-first và JAXB

Khi dùng plugin JAXB/XJC sinh mã từ `orders.xsd`:

- Tool phải resolve `order-types.xsd` và `../common/common.xsd`, cũng như common include.
- Các kiểu Java có thể nằm trong **package khác nhau** theo namespace orders/common.
- `@XmlElement`/`JAXBElement` có namespace được sinh từ schema, không phải từ tên file.
- Thay đổi `targetNamespace` hoặc kiểu import có thể khiến Java package/class và wire XML đổi theo.
- Server Spring-WS vẫn định tuyến dựa trên **global element QName**, không dựa vào đường dẫn XSD hay tên class generated.

Một build sinh client thành công chỉ chứng minh tool xử lý được những schema tại lúc build; hãy chạy **integration test qua WSDL được server thật công bố** để phát hiện đường dẫn HTTP, security và response validation.

## 12. Versioning: sửa một XSD dùng chung ảnh hưởng nhiều dịch vụ

Giả sử `common/common-types.xsd` định nghĩa `CorrelationIdType` được cả orders và invoices import. Nếu tăng `minLength` từ 1 lên 12, một request có correlation ID 8 ký tự trước đây hợp lệ nay có thể bị từ chối. Không có thay đổi Java method nào vẫn là **thay đổi contract**.

| Thay đổi | Rủi ro |
|---|---|
| Thêm field bắt buộc vào `RequestMetadataType` | Các request cũ dùng metadata không còn hợp lệ |
| Thêm field tùy chọn | Request cũ có thể hợp lệ với schema mới; XML mới có field lạ có thể bị client cũ từ chối |
| Siết pattern/enum | Giá trị từng hợp lệ bị chặn |
| Đổi namespace common v1 → v2 | Mọi `xs:import`, QNames, JAXB model và client liên quan phải xem lại |
| Đổi thư mục/file nhưng giữ namespace và nội dung | Có thể chỉ là thay đổi đóng gói; phải sửa `schemaLocation` và resource resolution |
| Thay `xs:include` bằng `xs:import` | Có thể thay namespace của type, không phải refactor thuần túy |
| Copy một kiểu vào hai schema chung namespace | Có nguy cơ duplicate definition và xung đột khi tập hợp |
| Đổi từ WSDL inline sang external XSD | Có thể giữ semantics XML nhưng phá client tooling/network access |
| Đổi thứ tự `xs:sequence` | XML instance cũ có thể không qua validation |

Nên version hóa **toàn bộ đồ thị** XSD/WSDL cùng nhau, không chỉ file entrypoint. Lưu một snapshot có thể tái tạo khi phát hành, dùng kiểm tra diff QName/types/constraints và chạy compatibility test bằng client đã phát hành.

Với namespace có hậu tố `v1`, một thay đổi breaking thường nên được lên kế hoạch thành `v2` theo chiến lược đối tác. Không phải mọi chỉnh sửa file cần đổi namespace, nhưng những thay đổi làm thay tập XML hợp lệ hoặc khiến client cũ không chạy phải được đánh giá rõ.

## 13. Chẩn đoán lỗi import/include theo triệu chứng

Khi một công cụ báo `Cannot resolve name`, đừng lập tức thêm tất cả XSD vào một collection hoặc bật quyền truy cập Internet. Hãy kiểm tra **namespace**, **đường dẫn** và **base URI** theo thứ tự.

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra ưu tiên |
|---|---|---|
| `src-resolve: Cannot resolve ... com:RequestMetadataType` | `xs:import` không nạp được common schema, namespace sai hoặc type chưa tồn tại | `namespace` import, `targetNamespace` của common, đúng tên type, import dependency |
| `schema_reference... Failed to read schema document` | `schemaLocation` sai, base URI bị mất, resource không đóng gói | Đường dẫn relative từ file tham chiếu, classpath/JAR, quyền đọc |
| `xs:include` báo namespace không phù hợp | Included XSD có targetNamespace khác | Dùng include cùng namespace hoặc import khác namespace |
| Duplicate global type/element | Cùng QName được khai báo hai lần trong tập schema | Tìm định nghĩa trùng trong các entrypoints/include và cách flatten |
| `cvc-elt.1.a: Cannot find declaration of element` | XML payload root QName không nằm trong schema đang validate | Namespace URI, global element và collection được validator cấp |
| `cvc-complex-type... Invalid content` | Child QName/order sai hoặc thiếu field | `elementFormDefault`, `xs:sequence`, namespace của từng child |
| `cvc-pattern-valid`, `cvc-enumeration-valid` | Giá trị không thỏa facet của type | Xác nhận schema đã import đúng và XML lexical value |
| IDE pass, executable JAR fail | Parser không resolve nested-JAR URL/thiếu systemId | Artifact resources, resolver/catalog, cách nạp classpath |
| Server validate pass, client sinh mã fail | WSDL công bố thiếu XSD dependencies hoặc URL import chỉ dùng nội bộ | GET WSDL từ phía client, theo từng `schemaLocation` |
| SOAP request tốt nhưng response bị validation reject | Server tạo XML sai type hoặc validateResponse dùng schema thiếu response element | `GetOrderResponse` QName, response XSD, interceptor scope |
| Import namespace đúng nhưng không có schemaLocation | Không có resolver/catal​og cung cấp schema định danh đó | Cấu hình mapping namespace → tài nguyên đã duyệt |
| Client dùng namespace v2 với server v1 | QName/type thay phiên bản | Versioning XSD/WSDL và mapping v2 có chủ đích |

Các đoạn mã lỗi ở bảng là **ví dụ thông điệp** thường thấy từ XML Schema validators; wording và mã cụ thể phụ thuộc Xerces, Apache XmlSchema, JAXP và phiên bản runtime.

### 13.1. Quy trình tìm lỗi sáu bước

1. **Xác định điểm lỗi:** XSD compile, WSDL generation, client codegen, request validation hay response validation?
2. **Ghi root schema:** tài nguyên nào là entrypoint, URI/base URI nào đang được parser dùng?
3. **Dò dependency graph:** với mỗi `xs:include`, so namespace; với mỗi `xs:import`, so namespace khác và địa chỉ resolution.
4. **Kiểm tra đường dẫn đích:** tài nguyên thực có trong classpath/JAR không, relative path có dùng slash URI `/` không?
5. **Thử một XML payload nhỏ:** validate đúng root QName và các field từ schema imported, để chứng minh collection hoàn chỉnh.
6. **Chạy kiểm thử từ phía client:** tải WSDL từ public URL, theo các imports còn lại và sinh client thử.

Không sửa bằng cách tắt schema validation hoặc bỏ `xs:import` rồi sửa Java model thủ công; điều đó có thể che giấu sai lệch contract.

### 13.2. Khi thiếu namespace import

Một lỗi cấu hình thường gặp:

~~~xml
<xs:import schemaLocation="../common/common.xsd"/>
~~~

Trong một số bối cảnh, import không có `namespace` thể hiện import **schema không có namespace**, chứ không tự suy ra `urn:example:common:v1` từ tài liệu đích. Với bộ schema đang học, cần khai báo rõ:

~~~xml
<xs:import
    namespace="urn:example:common:v1"
    schemaLocation="../common/common.xsd"/>
~~~

Nếu schema common có `targetNamespace="urn:example:common:v1"` mà import lại ghi URI khác, việc resolve type `com:RequestMetadataType` sẽ thất bại hoặc schema bị báo không nhất quán. **Không đổi namespace URI tùy tiện chỉ để làm compiler hết báo lỗi**, vì đây là public contract.

### 13.3. Lỗi do namespace của child element

Payload này có root và metadata đúng nhưng children sai:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:com="urn:example:common:v1">
  <ord:metadata>
    <ord:correlationId>REQ-12345</ord:correlationId>
  </ord:metadata>
  <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

Tại sao sai? `correlationId` được khai báo **trong common schema**, và `elementFormDefault="qualified"` ở common làm QName mong đợi là `{urn:example:common:v1}correlationId`. Element `ord:correlationId` khác QName. Đây là lỗi instance, không nhất thiết là lỗi import; dù validator đã nạp đủ common.xsd, XML vẫn không hợp lệ.

## 14. SOAP Fault, XML security, WS-Security và lỗi schema

### 14.1. Lỗi contract khác lỗi hệ thống

Một SOAP request vi phạm `CorrelationIdType` là **lỗi dữ liệu client** khi hợp đồng yêu cầu pattern đó. Nhưng một server không nạp được `common.xsd` do đóng gói thiếu file là **lỗi cấu hình server**; không nên trả cùng một fault detail gây hiểu lầm.

| Tình huống | Phân loại và xử lý |
|---|---|
| Client gửi `orderId` sai pattern | Input validation error; SOAP Fault theo thỏa thuận |
| Client gửi sai root QName | Endpoint routing/contract mismatch |
| Client gửi SOAP 1.2 vào endpoint chỉ hỗ trợ SOAP 1.1 | SOAP protocol/message factory |
| Server thiếu XSD imported khi khởi động | Configuration/deployment failure, nên fail fast |
| Client chưa tải được external XSD khi sinh mã | Contract publication/network resolver issue |
| Caller không được phép xem đơn hàng | Authentication/authorization failure, dù XML hợp lệ |
| SOAP signature không hợp lệ | WS-Security failure, không phải XSD validation |
| Gateway hết hạn chứng chỉ hoặc sai trust chain | TLS/certificate configuration |

Spring-WS có `EndpointExceptionResolver` và các SOAP fault resolver, nhưng lỗi parser, transport hay schema collection khởi tạo thất bại có thể xảy ra **trước** endpoint. Không thiết kế một resolver duy nhất rồi giả định bao phủ mọi lỗi.

### 14.2. Không tin `xsi:schemaLocation` do client gửi

XML instance có thể chứa:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      urn:example:orders:v1
      https://untrusted.example/schema.xsd">
  ...
</ord:GetOrderRequest>
~~~

`xsi:schemaLocation` là **hint từ XML instance**. Server contract-first nên validate bằng **schema đã cấu hình và tin cậy**, không tự tải đường dẫn do client cung cấp như nguồn hợp đồng. Nếu parser/validator phụ thuộc input-provided hints, attacker có thể tìm cách làm thay đường nạp schema hoặc buộc server truy cập tài nguyên ngoài.

### 14.3. XML security cần chặn cả parser và dependency resolution

- Vô hiệu hóa hoặc giới hạn DTD và external entities theo policy chống XXE.
- Hạn chế truy cập external schema/document ở parser, SchemaFactory và transformer khi thích hợp.
- Giữ một **catalog/resolver whitelist** cho các XSD cần thiết; không cho URL ngẫu nhiên.
- Giới hạn XML size, nesting depth, số phần tử, attributes, số bytes của Base64/MTOM attachments và thời gian xử lý.
- Tránh logging raw SOAP Body, tokens, certificates hoặc dữ liệu nhạy cảm trong quá trình xử lý lỗi.
- Kiểm tra certificate/truststore khi tải WSDL/XSD qua HTTPS nếu thực sự cần external references.
- Bảo đảm schema compiler không thể thay đổi hành vi chạy production chỉ vì một tài nguyên remote bị cập nhật.

### 14.4. WS-Security không được giải quyết bởi xs:include/import

WS-Security bảo vệ tính xác thực và toàn vẹn của SOAP message theo policy; XSD import/include chỉ quyết định cách các **kiểu XML** liên hệ.

Một dịch vụ có thể validate XSD thành công nhưng vẫn thiếu:

- Chữ ký số SOAP Body/Header.
- Timestamp, replay protection hoặc token hợp lệ.
- Kiểm chứng certificate chain/keystore/truststore.
- Quyền gọi operation và truy cập bản ghi đơn hàng.
- Quy định xử lý WS-Security khi message sử dụng MTOM/XOP.

Thay đổi common schema có thể làm thay SOAP Body XML được ký; cần kiểm thử canonicalization và khả năng xác minh chữ ký trên client/server theo profile thực. **TLS bảo vệ kênh truyền, WS-Security bảo vệ thông điệp** khi chính sách yêu cầu; không mặc định HTTPS đã thay thế WS-Security.

## 15. Kiểm thử tích hợp SOAP và khả năng tương thích

### 15.1. SOAP request hoàn chỉnh

Một request SOAP 1.1 cho payload ở mục 4:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1"
    xmlns:com="urn:example:common:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:metadata>
        <com:correlationId>REQ-12345</com:correlationId>
        <com:sourceSystem>BACKOFFICE</com:sourceSystem>
      </ord:metadata>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Nếu file này được lưu thành `soap-order.xml`, có thể gọi endpoint HTTP:

~~~bash
curl -i -sS \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: ""' \
  --data-binary @soap-order.xml \
  http://localhost:8080/ws
~~~

Đây là hướng dẫn tích hợp cho ứng dụng mẫu có endpoint `GetOrderRequest`; **SOAPAction thực phải theo WSDL binding** nếu contract quy định một action cụ thể. Lệnh chưa được thực thi trong bài viết và không bảo đảm bất kỳ server nào đang chạy tại localhost.

Phần kiểm thử cần ghi lại:

1. HTTP status, SOAP version và Envelope/Body QNames.
2. Server dispatch tới đúng `@PayloadRoot`.
3. Payload hợp lệ với **toàn bộ schema collection**, bao gồm common namespace.
4. Response `GetOrderResponse` đúng XSD.
5. Dữ liệu thiếu/sai `com:correlationId` được từ chối theo policy.
6. Security headers, certificate validation và authorization được áp dụng khi triển khai doanh nghiệp.

### 15.2. Test bằng MockWebServiceClient

Sau khi ứng dụng Spring-WS có endpoint và schema collection thực sự, `MockWebServiceClient` (dependency `spring-ws-test`) hỗ trợ kiểm tra dispatch/response payload mà không mở cổng HTTP.

~~~java
@SpringBootTest
class OrdersEndpointTest {
    @Autowired
    ApplicationContext context;

    @Test
    void acceptsImportedCommonType() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(context);

        Source request = new StringSource("""
            <ord:GetOrderRequest
                xmlns:ord="urn:example:orders:v1"
                xmlns:com="urn:example:common:v1">
              <ord:metadata>
                <com:correlationId>REQ-12345</com:correlationId>
              </ord:metadata>
              <ord:orderId>ORD-1001</ord:orderId>
            </ord:GetOrderRequest>
            """);

        Source expected = new StringSource("""
            <ord:GetOrderResponse
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-1001</ord:orderId>
              <ord:status>PROCESSING</ord:status>
            </ord:GetOrderResponse>
            """);

        client.sendRequest(withPayload(request))
              .andExpect(payload(expected));
    }
}
~~~

Đây là **mẫu test**: cần bổ sung import JUnit/Spring, static imports `withPayload` từ `RequestCreators`, `payload` từ `ResponseMatchers`, và một `@Endpoint`/service tạo response khớp ví dụ. Test này không tự kiểm chứng WSDL download, servlet, proxy/TLS hay chứng chỉ.

### 15.3. Client contract test từ WSDL đã công bố

Một kiểm tra interoperability có giá trị cao là:

- Tải `/ws/orders.wsdl` từ URL mà đối tác thực sự truy cập.
- Theo tất cả `xs:import`, `xs:include` hoặc inline XSD còn lại.
- Sinh client bằng công cụ phù hợp (CXF/JAX-WS, .NET hoặc stack đối tác).
- Gửi request có `com:RequestMetadataType` và nhận response.
- Kiểm tra request không đúng enum/pattern, SOAP Fault và WS-Security.
- Tắt mạng tới hệ schema không được phép và xác minh build/khởi động vẫn tái lập được.

Nếu server chỉ pass test `PayloadValidatingInterceptor` nhưng client không sinh mã được vì không GET được `../common/common.xsd`, **bài toán chưa giải quyết xong**.

### 15.4. Test matrix khi nâng version

| Tác vụ | v1 client → v1 server | v1 client → v2 server | v2 client → v1 server |
|---|---|---|---|
| Request cũ không thêm field | Phải pass | Kiểm tra schema/semantics | Tùy WSDL mà client dùng |
| Request với type/common namespace mới | Không được giả định | Test theo contract v2 | Có thể bị từ chối |
| Response có optional element mới | Phụ thuộc schema cũ | Test old client unmarshaller | Không áp dụng nếu server v1 không phát field |
| SOAP Fault detail đổi | Test chính xác | Test backward compatibility | Có thể không hiểu |
| WS-Security policy đổi | Test signature/cert | Test migration | Có thể không tương thích |

Đừng chỉ test XML dữ liệu thành công; **client cũ đã phát hành** thường là nguồn phát hiện các thay đổi schema nhỏ nhưng phá vỡ tương thích.

## 16. Khi nào cần collection, khi nào không?

### Trường hợp A — Một XSD, không import/include

Có thể dùng `SimpleXsdSchema` và WSDL definition đơn giản; không cần thêm collection chỉ để tăng số lượng bean.

### Trường hợp B — Nhiều file cùng targetNamespace

Dùng `xs:include` với đường dẫn ổn định; đảm bảo không trùng global declarations. Nếu cần công bố WSDL đa file, cân nhắc `CommonsXsdSchemaCollection` và kiểm tra inlining/external references.

### Trường hợp C — Nhiều namespaces và type dùng chung

Dùng `xs:import` để nối các namespaces. Bảo đảm prefix QNames đúng, imported schema resolve được từ root, và collection/schema compiler biết toàn bộ dependencies.

### Trường hợp D — Nhiều dịch vụ có chính sách validation khác nhau

Cân nhắc **phạm vi collection/interceptor** theo endpoint hoặc tách context. Tránh gắn một validator không hiểu đầy đủ các namespaces lên mọi SOAP operation.

### Trường hợp E — Đối tác cần WSDL cố định

Ưu tiên WSDL tĩnh được kiểm soát phiên bản; tập XSD có thể được dùng cho validation nội bộ, nhưng phải giữ WSDL ngoài đúng hợp đồng đã phê duyệt.

### Trường hợp F — Schema nhập từ đối tác có URL remote

Đóng gói một bản đã duyệt và dùng catalog/resource resolver có kiểm soát. Không để client SOAP tự định nghĩa URL schema mà server sẽ tải trong runtime.

## 17. Bài tập tự luyện và đáp án

**Bài 1 — Chọn include hay import.** `orders.xsd` và `order-types.xsd` cùng namespace `urn:example:orders:v1`. Chọn cơ chế nào?

*Đáp án:* `xs:include`; cả hai thuộc cùng namespace, schemaLocation trỏ tới file đã tách.

**Bài 2 — Nhập namespace khác.** `orders.xsd` muốn dùng `RequestMetadataType` từ `urn:example:common:v1`. Có thể `xs:include` trực tiếp `common.xsd` không?

*Đáp án:* Không, vì common có targetNamespace khác. Dùng `xs:import namespace="urn:example:common:v1"` và khai báo prefix cho type tham chiếu.

**Bài 3 — Sai QName child.** Vì sao `ord:metadata/com:correlationId` hợp lệ, còn `com:metadata/ord:correlationId` không?

*Đáp án:* `metadata` được khai báo cục bộ trong orders schema nên thuộc namespace orders; `correlationId` khai báo trong common type nên thuộc namespace common. Namespace của **element** phụ thuộc nơi nó được khai báo, không phụ thuộc namespace của type bao ngoài theo suy đoán.

**Bài 4 — File import đúng ở IDE nhưng không resolve trong JAR.** Cần kiểm tra gì?

*Đáp án:* Xác minh mọi XSD được đóng gói, `schemaLocation` tương đối từ base URI, parser có `systemId`/resolver phù hợp nested-JAR và mọi dependency được whitelist. Không hardcode đường dẫn `C:\...` vào schema.

**Bài 5 — XSD hợp lệ, WSDL client codegen lỗi.** Server đã compile schema collection nhưng client nhận lỗi tải `../common/common.xsd`. Kết luận?

*Đáp án:* Resolution ở server và client là hai đường khác. Cần kiểm tra WSDL công bố, inlining/external URL, reverse proxy và quyền tải schema từ phía client.

**Bài 6 — Import không có schemaLocation.** `xs:import namespace="urn:example:common:v1"` có luôn sai?

*Đáp án:* Không nhất thiết; import có thể không có location hint. Nhưng validator/codegen cần một schema source hoặc resolver/catalog phù hợp; không tự suy ra nó từ namespace URI.

**Bài 7 — Chặn truy cập Internet làm lỗi validation.** Đội an ninh cấu hình `ACCESS_EXTERNAL_SCHEMA=""` và server bắt đầu không nạp được common XSD. Có nên bật `http` toàn cục?

*Đáp án:* Không nên. Đóng gói schema và cấu hình catalog/resolver whitelist cho dependencies, rồi kiểm tra JAXP provider vẫn giải được local resources dưới chính sách chặn external access.

**Bài 8 — Schema validation có xác thực chữ ký không?** Request thỏa toàn bộ XSD, nhưng WS-Security signature sai. Server có được phép xử lý nghiệp vụ không?

*Đáp án:* Không. XSD validation chỉ kiểm tra cấu trúc/giá trị XML; bảo mật thông điệp và quyền nghiệp vụ phải được xử lý riêng.

## 18. Checklist và tổng kết

- [ ] Đã xác định từng `targetNamespace` và global element request/response.
- [ ] `xs:include` chỉ dùng với namespace phù hợp; `xs:import` dùng cho namespace khác.
- [ ] Mỗi `schemaLocation` resolve đúng theo base URI và tài nguyên đã đóng gói.
- [ ] Đã kiểm tra nested imports/includes, không chỉ file XSD entrypoint.
- [ ] Không có global type/element trùng QName trong schema collection.
- [ ] Spring-WS dùng `XsdSchema` hoặc `XsdSchemaCollection` phù hợp cấu trúc hợp đồng.
- [ ] `PayloadValidatingInterceptor` được bật thật sự cho request/response cần kiểm tra.
- [ ] Tập schema của validator bao phủ tất cả namespaces và versions thuộc phạm vi nó phục vụ.
- [ ] WSDL `wsdl:types` và các `wsdl:part/@element` trỏ đúng global elements.
- [ ] Đã test WSDL tải từ URL client, mọi imports/includes và `soap:address` sau proxy/TLS.
- [ ] Có unit tests compile schema, test XML hợp lệ và các trường hợp sai facet/QName/order.
- [ ] Có integration tests SOAP qua HTTP và với client sinh từ WSDL chính thức.
- [ ] XML parser và schema resolver dùng tài nguyên tin cậy; hạn chế DTD, XXE và truy cập ngoài.
- [ ] Đã kiểm tra SOAP Fault, WS-Security, chứng chỉ và authorization ở tầng phù hợp.
- [ ] Mọi thay đổi XSD dùng chung đều được đánh giá tác động client và versioning.

**Ghi nhớ:** `xs:include` kết hợp các khai báo thuộc **cùng namespace**; `xs:import` cho phép tham chiếu khai báo từ **namespace khác**. Với Spring Web Services, `XsdSchemaCollection` và `CommonsXsdSchemaCollection` giúp quản lý tập schema, còn `PayloadValidatingInterceptor` thực thi kiểm tra XML ở ranh giới SOAP. Một thiết kế contract-first đúng cần bảo đảm cả **schema compilation trên server**, **WSDL/XSD resolution từ client** và **an toàn tài nguyên**, không chỉ tạo được Java DTO.
