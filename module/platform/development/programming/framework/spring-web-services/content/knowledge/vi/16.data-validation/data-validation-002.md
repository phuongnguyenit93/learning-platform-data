# PayloadValidatingInterceptor và cấu hình schema kiểm tra

## 1. Vì sao SOAP contract-first cần xác thực payload?

Một dịch vụ **Spring Web Services (Spring-WS)** có thể nhận được SOAP Envelope hoàn toàn hợp lệ về cú pháp XML, xác định đúng operation bằng `@PayloadRoot`, nhưng nội dung request vẫn **không tuân thủ XSD đã công bố**. Ví dụ client gửi `GetOrderRequest` thiếu `orderId`, dùng sai namespace, đặt phần tử sai thứ tự hoặc đưa số âm vào trường số lượng chỉ cho phép số dương.

Trong mô hình **contract-first**, XSD/WSDL là hợp đồng trao đổi dữ liệu giữa hệ thống. Việc xác thực payload giúp phát hiện sai lệch hợp đồng **trước khi nghiệp vụ sử dụng dữ liệu** và, khi được cấu hình, phát hiện response do server tạo ra không đúng schema trước khi gửi cho đối tác.

Spring-WS cung cấp **`PayloadValidatingInterceptor`**, một interceptor dùng **XML Schema (XSD)** để kiểm tra phần payload XML. Đây là một thành phần của chuỗi xử lý thông điệp SOAP, không phải annotation Bean Validation trên DTO Java.

Bài học thuộc chương **Kiểm tra dữ liệu**, bao gồm:

- Hiểu phạm vi `PayloadValidatingInterceptor` và vị trí của nó trong pipeline server.
- Tạo XSD cho request/response và đăng ký `XsdSchema`.
- Kích hoạt validation bằng `WsConfigurer` cùng `@EnableWs`.
- Phân biệt `validateRequest` và `validateResponse`.
- Xử lý nhiều schema, namespace, import/include và version của hợp đồng.
- Phân loại lỗi XSD, SOAP Fault, ánh xạ endpoint, HTTP/TLS và WS-Security.
- Viết các ca kiểm thử tích hợp đủ để chứng minh **validation thực sự chạy**, không chỉ WSDL tồn tại.

**Mục tiêu cuối cùng:** SOAP request hợp đồng hợp lệ được xử lý; request vi phạm schema không được đưa vào nghiệp vụ theo đường thành công; lỗi được diễn giải đúng tầng, không làm lộ thông tin nhạy cảm và không ảnh hưởng tính tương thích client.

## 2. Validation nằm ở đâu trong kiến trúc Spring-WS?

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["HTTP(S), reverse proxy, TLS"]
    B --> C["MessageDispatcherServlet"]
    C --> D["WebServiceMessageFactory đọc SOAP XML"]
    D --> E["MessageDispatcher / EndpointMapping"]
    E --> F["EndpointInterceptor chain"]
    F --> G{"Payload hợp XSD?"}
    G -->|"Không"| H["Dừng xử lý / phản hồi lỗi theo cấu hình"]
    G -->|"Có"| I["EndpointAdapter + @Endpoint"]
    I --> J["Tạo response SOAP payload"]
    J --> K{"Có bật validation response?"}
    K -->|"Có"| L["Kiểm tra response theo XSD"]
    K -->|"Không"| M["Gửi phản hồi"]
    L --> M
    L -->|"Sai"| N["Xử lý lỗi response theo chính sách"]
~~~

Đây là **sơ đồ khái quát**, không phải đặc tả đầy đủ về thứ tự của mọi mapping, interceptor, resolver và SOAP Fault. Trong Spring-WS, các endpoint interceptor gắn với endpoint được chọn theo cấu hình mapping; do đó cần phân biệt lỗi xảy ra **trước mapping** với lỗi được interceptor kiểm tra **sau khi chọn endpoint**.

| Tầng | Kiểm tra chính | Ví dụ lỗi |
| --- | --- | --- |
| DNS/TCP/TLS/HTTP | Địa chỉ, kết nối, chứng chỉ, method, Content-Type | 404, 415, TLS handshake failure |
| SOAP parser / message factory | XML well-formed và SOAP Envelope theo version | XML lỗi cú pháp, `VersionMismatch` |
| Endpoint mapping | QName của root payload hoặc SOAP action | Không tìm được handler cho namespace mới |
| **`PayloadValidatingInterceptor`** | **Payload đúng XSD đã cấu hình** | Thiếu phần tử bắt buộc, sai kiểu số, sai thứ tự |
| JAXB binding | XML ↔ lớp Java | Không marshal/unmarshal được kiểu hoặc root |
| Business validation | Quy tắc nghiệp vụ và quyền thao tác | Đơn hàng không tồn tại, không được phép hủy |
| WS-Security | Signature, token, timestamp và policy | Chữ ký không hợp lệ, token hết hạn |

**Đừng gộp các tầng này thành một loại “validation”.** XSD hợp lệ không chứng minh người gọi được phép truy cập, chữ ký đúng, mã đơn hàng tồn tại hay dữ liệu đã an toàn cho mọi xử lý tiếp theo.

### 2.1. `@PayloadRoot` không thay thế XSD validation

Giả sử endpoint được đánh dấu:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest"
)
~~~

Spring-WS có thể chọn đúng method khi SOAP Body chứa `{urn:example:orders:v1}GetOrderRequest`. Nhưng lựa chọn đó **không bảo đảm** phần tử con `orderId` tồn tại, đúng kiểu, nằm đúng thứ tự hoặc đáp ứng quy tắc `xs:pattern`.

Đặc biệt, khi root QName sai hoàn toàn, có thể không tìm thấy endpoint **trước khi interceptor validation của endpoint được gọi**. Vì vậy các test phải phân biệt **lỗi ánh xạ endpoint** với **lỗi payload sai cấu trúc bên trong một root đã được nhận diện**.

## 3. XSD mẫu: định nghĩa điều kiện hợp lệ một cách có thể kiểm tra

Ta thiết kế một hợp đồng đơn hàng tối thiểu tại:

`src/main/resources/xsd/orders.xsd`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:minLength value="8"/>
            <xs:maxLength value="16"/>
            <xs:pattern value="ORD-[0-9]{4,12}"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="FOUND"/>
            <xs:enumeration value="NOT_FOUND"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId"
                            type="tns:OrderIdType"/>
                <xs:element name="includeItems"
                            type="xs:boolean"
                            minOccurs="0"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="status"
                            type="tns:OrderStatusType"/>
                <xs:element name="itemCount"
                            type="xs:nonNegativeInteger"
                            minOccurs="0"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Phân tích hợp đồng:

| Khai báo | Ý nghĩa khi validation |
| --- | --- |
| `targetNamespace="urn:example:orders:v1"` | Global elements `GetOrderRequest`/`GetOrderResponse` thuộc namespace này |
| `elementFormDefault="qualified"` | Local elements `orderId`, `includeItems`, `status`, `itemCount` cũng phải thuộc namespace tương ứng |
| `xs:sequence` | Thứ tự phần tử con được quy định, không tùy ý hoán đổi |
| `orderId: minLength/maxLength/pattern` | Mã phải theo định dạng `ORD-` và 4–12 chữ số, tổng 8–16 ký tự |
| `includeItems: xs:boolean, minOccurs=0` | Có thể bỏ; nếu xuất hiện phải có lexical boolean hợp lệ như `true`/`false`/`1`/`0` |
| `status: xs:enumeration` | Chỉ `FOUND` hoặc `NOT_FOUND` được chấp nhận |
| `itemCount: xs:nonNegativeInteger` | Chỉ số nguyên không âm; có thể bỏ |

**Lưu ý:** XSD không kiểm tra được tất cả quy tắc nghiệp vụ. Schema cho phép `status=NOT_FOUND` đi cùng `itemCount=100` về mặt cấu trúc; nếu hai trường đó phải có quan hệ logic đặc biệt, cần business validation hoặc một cơ chế ràng buộc bổ sung phù hợp.

### 3.1. Một payload request hợp lệ

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>ORD-1001</o:orderId>
    <o:includeItems>true</o:includeItems>
</o:GetOrderRequest>
~~~

Payload này đáp ứng QName, thứ tự và pattern đã khai báo. Prefix `o` không quan trọng bằng **namespace URI**.

### 3.2. Bốn payload không hợp lệ

**Thiếu `orderId` bắt buộc:**

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:includeItems>true</o:includeItems>
</o:GetOrderRequest>
~~~

**`orderId` không khớp pattern:**

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>ORDER-ABC</o:orderId>
</o:GetOrderRequest>
~~~

**Sai thứ tự trong `xs:sequence`:**

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:includeItems>true</o:includeItems>
    <o:orderId>ORD-1001</o:orderId>
</o:GetOrderRequest>
~~~

**Local element sai namespace:**

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <orderId>ORD-1001</orderId>
</o:GetOrderRequest>
~~~

Ở ví dụ cuối, `GetOrderRequest` đúng namespace nhưng `orderId` không có namespace. Với `elementFormDefault="qualified"`, phần tử đó **không hợp lệ**, dù local name và nội dung trông giống nhau.

### 3.3. Một response hợp lệ

~~~xml
<o:GetOrderResponse xmlns:o="urn:example:orders:v1">
    <o:status>FOUND</o:status>
    <o:itemCount>3</o:itemCount>
</o:GetOrderResponse>
~~~

Nếu server trả `<o:itemCount>-1</o:itemCount>` hoặc `<o:status>SUCCESS</o:status>`, XML response vi phạm schema. Đây là lý do **response validation** có giá trị đối với các SOAP API phục vụ nhiều đối tác.

## 4. Đối tượng nào thực hiện validation?

### 4.1. `PayloadValidatingInterceptor`

`org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor` thuộc hạ tầng interceptor phía SOAP server. Nó sử dụng cấu hình XSD để kiểm tra **payload**, không yêu cầu bạn tự biến XML thành DOM rồi gọi `SchemaFactory` ở từng endpoint.

Các thiết lập thường dùng:

~~~java
PayloadValidatingInterceptor validator =
        new PayloadValidatingInterceptor();
validator.setXsdSchema(ordersSchema);
validator.setValidateRequest(true);
validator.setValidateResponse(false);
~~~

Ý nghĩa:

- `setXsdSchema(...)`: chọn XSD mà interceptor sử dụng để kiểm tra dữ liệu.
- `setValidateRequest(true)`: bật kiểm tra request payload.
- `setValidateResponse(false)`: trong ví dụ ban đầu, chưa kiểm tra response payload.

Sau khi hệ thống đã có response XSD ổn định, có thể dùng `setValidateResponse(true)` và kiểm thử đầy đủ đường phản hồi. **Không giả định mọi bản Spring-WS đều xử lý response validation failure theo cùng một HTTP status hoặc SOAP Fault**; kiểm tra behavior của phiên bản và resolver đã cấu hình.

### 4.2. `XsdSchema` không có nghĩa validation tự bật

`org.springframework.xml.xsd.XsdSchema` là abstraction đại diện một schema. Một bean `XsdSchema` có thể được sử dụng để **công bố WSDL** qua `DefaultWsdl11Definition` và cũng có thể được **gán cho interceptor** để validation.

Hai vai trò này độc lập:

~~~text
XsdSchema bean
    ├── DefaultWsdl11Definition → công bố XSD/WSDL
    └── PayloadValidatingInterceptor → kiểm tra XML
~~~

Nếu chỉ tạo `XsdSchema` và `DefaultWsdl11Definition` mà **không đăng ký interceptor**, Spring-WS không mặc nhiên kiểm tra mọi request bằng XSD đó.

### 4.3. Phạm vi validation của payload

Payload validation tập trung vào **nội dung Body ứng dụng**. Nó không tự bảo đảm:

- SOAP Envelope đúng version; phần này liên quan SOAP stack/message factory.
- SOAP Header được hiểu/xác thực; cần header processing và WS-Security.
- HTTP `SOAPAction` nhất quán với operation; cần contract/mapping/policy phù hợp.
- HTTP auth hoặc TLS/mTLS hợp lệ; đây là trách nhiệm tầng kết nối và security.
- Object JAXB tuân thủ mọi luật nghiệp vụ; JAXB mapping khác schema/business validation.
- Người gọi có quyền xem/hủy đơn hàng; cần authorization ở nghiệp vụ hoặc policy.

Do đó hãy xem `PayloadValidatingInterceptor` là **một bước bảo vệ hợp đồng XML**, không phải tường lửa tổng quát.

## 5. Cấu hình hoàn chỉnh trong ứng dụng Spring Boot

Ví dụ sử dụng một ứng dụng Spring Boot có dependency **Web Services** và Servlet runtime phù hợp. Với Maven, dependency cốt lõi có thể là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web-services</artifactId>
    </dependency>

    <dependency>
        <groupId>wsdl4j</groupId>
        <artifactId>wsdl4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây chỉ là đoạn dependencies, không phải POM hoàn chỉnh. Project cần Spring Boot parent/BOM tương thích, JDK và cấu hình build thích hợp; thư viện nào không được BOM quản lý cần xác định phiên bản phù hợp. Không tự ghép ngẫu nhiên các thế hệ `javax.servlet` và `jakarta.servlet`.

### 5.1. Bố cục source

~~~text
order-soap-service/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/orders/ws/
    │   │   ├── OrderSoapApplication.java
    │   │   ├── OrderContractConfig.java
    │   │   ├── OrderValidationConfig.java
    │   │   └── OrderEndpoint.java
    │   └── resources/
    │       ├── application.properties
    │       └── xsd/orders.xsd
    └── test/java/...
~~~

`orders.xsd` chính là file mẫu ở mục 3. Trong một ứng dụng thực, có thể tách các lớp cấu hình theo module hoặc package; điều bắt buộc là chúng được Spring component scan/import và vận hành trong cùng SOAP application context phù hợp.

### 5.2. Entry point và servlet path

~~~java
package example.orders.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderSoapApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderSoapApplication.class, args);
    }
}
~~~

Với một phiên bản Spring Boot có Web Services servlet auto-configuration tương ứng, có thể đặt:

~~~properties
server.port=8080
spring.webservices.path=/ws
~~~

Property `spring.webservices.path` điều chỉnh đường dẫn SOAP servlet khi Boot **đang quản lý registration**. Nếu ứng dụng tự tạo `ServletRegistrationBean<MessageDispatcherServlet>`, cần kiểm tra cơ chế back-off và mapping thực tế, không giả định property này tự áp dụng lên servlet thủ công.

### 5.3. Cấu hình schema và WSDL

~~~java
package example.orders.ws;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class OrderContractConfig {

    private static final String NAMESPACE =
            "urn:example:orders:v1";

    @Bean("ordersSchema")
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(
            @Qualifier("ordersSchema") XsdSchema schema) {
        DefaultWsdl11Definition definition =
                new DefaultWsdl11Definition();
        definition.setPortTypeName("OrdersPort");
        definition.setServiceName("OrderService");
        definition.setTargetNamespace(NAMESPACE);
        definition.setLocationUri("/ws/orders");
        definition.setSchema(schema);
        definition.setCreateSoap11Binding(true);
        definition.setCreateSoap12Binding(false);
        return definition;
    }
}
~~~

Các phần quan trọng:

1. `@EnableWs` kích hoạt hạ tầng cấu hình annotation của Spring-WS.
2. `ordersSchema` đọc XSD trên classpath.
3. Bean WSDL tên `orders` công bố hợp đồng 1.1 từ schema; với servlet mapping `/ws/*`, URL thường là `/ws/orders.wsdl`.
4. `setLocationUri("/ws/orders")` đặt địa chỉ SOAP endpoint được công bố trong WSDL, cần nhất quán với nơi servlet nhận HTTP POST.
5. `@Qualifier("ordersSchema")` tránh việc inject nhầm nếu context có nhiều bean `XsdSchema`.

**WSDL được sinh không thay thế validation.** Còn phải đăng ký interceptor riêng bên dưới. Mặt khác, nếu WSDL tĩnh đã được đối tác sử dụng, đừng nghĩ thay XSD trong ứng dụng là đủ: hợp đồng được công bố và schema validation phải được quản lý phiên bản đồng bộ.

### 5.4. Đăng ký `PayloadValidatingInterceptor` qua `WsConfigurer`

~~~java
package example.orders.ws;

import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class OrderValidationConfig implements WsConfigurer {

    private final XsdSchema ordersSchema;

    public OrderValidationConfig(
            @Qualifier("ordersSchema") XsdSchema ordersSchema) {
        this.ordersSchema = ordersSchema;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validator =
                new PayloadValidatingInterceptor();
        validator.setXsdSchema(ordersSchema);
        validator.setValidateRequest(true);
        validator.setValidateResponse(false);
        interceptors.add(validator);
    }
}
~~~

Trong ví dụ này, `@EnableWs` đã nằm ở `OrderContractConfig`; `OrderValidationConfig` không phải thêm `@EnableWs` lần nữa. Lớp `WsConfigurer` tham gia cấu hình cơ chế Spring-WS; `addInterceptors` đăng ký validator vào chain endpoint.

**Ba khác biệt dễ nhầm:**

- Tạo `new PayloadValidatingInterceptor()` trong một method ứng dụng **chưa đủ**: phải thêm nó vào interceptor chain hoặc hạ tầng cấu hình phù hợp.
- Tạo bean `PayloadValidatingInterceptor` nhưng **không liên kết vào endpoint mapping chain** cũng chưa chứng minh request đang được kiểm tra.
- Một XSD được nạp để tạo WSDL có thể **không** phải XSD interceptor đang dùng nếu cấu hình trỏ sai bean.

Trong dự án thực, nếu cần bảo đảm lifecycle được Spring quản lý và tái sử dụng một interceptor có cấu hình rõ, có thể tạo `@Bean` validator và inject bean đó vào `WsConfigurer`; vẫn phải liên kết với chain. Ví dụ trên chủ ý tạo interceptor trong callback cấu hình để minh họa mối liên hệ chính.

### 5.5. Một endpoint để quan sát validation chạy trước nghiệp vụ

~~~java
package example.orders.ws;

import javax.xml.transform.Source;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.xml.transform.StringSource;

@Endpoint
public class OrderEndpoint {

    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public Source getOrder(@RequestPayload Element request) {
        NodeList ids = request.getElementsByTagNameNS(NS, "orderId");
        String orderId = ids.item(0).getTextContent();

        // Trong ví dụ, input đã được validator XSD kiểm tra.
        // Dự án thực phải áp dụng xác thực, phân quyền và nghiệp vụ.
        String status = orderId.equals("ORD-1001")
                ? "FOUND"
                : "NOT_FOUND";

        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>" + status + "</o:status>" +
                "</o:GetOrderResponse>");
    }
}
~~~

Đây là **endpoint minh họa**, giả định `PayloadValidatingInterceptor` được áp dụng thành công trước lời gọi method, nên `orderId` tồn tại và hợp XSD. Trong ứng dụng thật, không nên dựa hoàn toàn vào một giả định hạ tầng khi xử lý dữ liệu không tin cậy; dùng validation, lỗi được kiểm soát và code nghiệp vụ đúng nhu cầu.

Mã response dùng `status` lấy từ hai giá trị nội bộ đã biết, không nội suy dữ liệu người dùng vào XML. Trong hệ thống sản xuất, nên dùng JAXB/`Source` builder chuẩn và trả typed SOAP Fault khi gặp lỗi; không tự ghép chuỗi XML từ input không được escape.

## 6. Kích hoạt validation request và response

### 6.1. Request validation

~~~java
validator.setValidateRequest(true);
validator.setValidateResponse(false);
~~~

Chính sách này thích hợp ở bước đầu khi cần bảo vệ endpoint khỏi payload sai schema và chưa ổn định các cấu trúc response/fault. Khi request có root QName đã được mapping và đi qua interceptor chain, validator kiểm tra XSD **trước khi phương thức nghiệp vụ chạy** theo cách cấu hình thông thường.

Điều cần xác nhận bằng test:

- Request hợp schema đi vào endpoint đúng một lần.
- Request sai schema không được xử lý như thành công.
- Dữ liệu trong SOAP Fault/error response phù hợp chính sách và không lộ chi tiết hạ tầng.
- Request sai root QName được phân loại đúng lỗi mapping, không nhầm với lỗi XSD của một endpoint đã chọn.

### 6.2. Response validation

~~~java
validator.setValidateRequest(true);
validator.setValidateResponse(true);
~~~

Khi bật `validateResponse`, dữ liệu **response payload** do endpoint tạo ra cũng được đối chiếu với schema theo cơ chế interceptor. Đây là lớp bảo vệ hữu ích khi:

- Endpoint trả `status` ngoài danh sách enum.
- JAXB marshals một response thiếu phần tử bắt buộc.
- Developer đổi namespace hoặc thứ tự phần tử response nhưng chưa sửa contract.
- Nhiều nhóm cùng đóng góp các endpoint trong một service.

Không nên xem response validation như một tính năng miễn phí:

- Nó bổ sung chi phí parse/validate XML ở đường phản hồi.
- Nếu chỉ cấu hình schema request, response có namespace/kiểu khác có thể bị từ chối.
- Một lỗi response sau khi nghiệp vụ đã thực thi cần được xử lý khác request sai; **không retry thao tác ghi theo suy đoán**.
- Hành vi ghi log, dừng xử lý hay tạo Fault khi response invalid tùy cấu hình/implementation; phải kiểm thử với stack đang dùng.

**Ví dụ:** SOAP request tạo hóa đơn có thể đã tạo giao dịch thành công, nhưng response XML sinh sai XSD. Chỉ dựa vào lỗi response để client gửi lại có thể tạo hai hóa đơn. Với operation ghi, thiết kế idempotency và cơ chế đối soát kết quả.

### 6.3. Validation không đổi hợp đồng SOAP

Thêm interceptor **không sửa XSD** và không tự cập nhật WSDL. Nếu XSD quy định `orderId` phải có pattern, server cần kiểm tra theo cùng schema mà client nhìn thấy. Không dùng một schema nội bộ “chặt hơn” một cách âm thầm khiến XML mà WSDL cho là hợp lệ lại bị server từ chối, trừ khi có quy định hợp đồng bổ sung đã được công bố rõ.

## 7. Xử lý lỗi validation và SOAP Fault

Một SOAP request sai schema thường cần một phản hồi lỗi có kiểm soát thay vì để nghiệp vụ ném `NullPointerException`. Spring-WS có khả năng phản hồi lỗi trong chuỗi interceptor và các cơ chế xử lý exception/Fault tương ứng.

**Không nên gán một kết quả HTTP/SOAP Fault duy nhất cho mọi cấu hình.** Mã Fault, HTTP status, fault detail và đường xử lý khác nhau theo phiên bản SOAP, implementation interceptor và resolver/policy đã đăng ký.

### 7.1. SOAP 1.1 Fault minh họa

Một Fault có thể có dạng:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>Payload does not match XML Schema</faultstring>
            <detail>
                <err:ValidationError
                    xmlns:err="urn:example:errors:v1">
                    <err:code>INVALID_REQUEST</err:code>
                </err:ValidationError>
            </detail>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Đây là **ví dụ thiết kế Fault**, không phải khẳng định `PayloadValidatingInterceptor` mặc định sinh đúng `err:ValidationError` như trên. Muốn có một `detail` với QName và fields cố định, phải định nghĩa schema/contract lỗi và thiết kế cơ chế tạo Fault tương ứng. Trong SOAP 1.2, các thành phần Fault là `Code`, `Reason` và `Detail`, không sử dụng nguyên xi `faultcode`/`faultstring` của SOAP 1.1.

### 7.2. Những điều nên và không nên trả cho client

Nên trả:

- Mã lỗi ổn định như `INVALID_REQUEST` theo contract.
- Mô tả ngắn đủ để client nhận biết loại vi phạm.
- Correlation ID để đối chiếu với log server khi cần.

Không nên tự động đưa ra:

- Đường dẫn tuyệt đối đến file XSD trong container.
- Stack trace Java, class name nội bộ, cấu hình parser.
- Nội dung request chứa dữ liệu cá nhân hoặc thông tin xác thực.
- Toàn bộ exception message từ thư viện XML nếu chưa được kiểm soát.

Khi cần liệt kê lỗi trường dữ liệu cho client, phải cân nhắc giới hạn số lượng, thông tin được phép tiết lộ và **độ ổn định của định dạng Fault** trước khi công bố hợp đồng.

### 7.3. Phân biệt lỗi schema với lỗi tầng khác

| Dấu hiệu | Tầng lỗi có khả năng | Bước kiểm tra |
| --- | --- | --- |
| HTTP 404 hoặc 405 | URL/Servlet mapping, method | `soap:address`, HTTP URL và gateway route |
| SOAP Envelope không parse được | XML syntax hoặc SOAP message factory | Envelope namespace, XML well-formed |
| “No endpoint mapping found” | QName/action không match | `@PayloadRoot`, `@SoapAction`, namespace |
| Lỗi `xs:sequence`/`pattern` | **XSD validation** | XSD đang được interceptor sử dụng |
| JAXB unmarshal exception | XML ↔ Java binding | DTO sinh, JAXB context, QName, nillable |
| SOAP `MustUnderstand` | Header processing | SOAP Header và policy |
| Chữ ký WS-Security không hợp lệ | Security interceptor | Signed parts, token, timestamp, certificate |
| HTTP 500 kèm SOAP Fault | SOAP framework/endpoint/security | Fault code, detail và contract |
| HTTP 500 kèm HTML | Web server hoặc gateway | HTTP Content-Type/body, không giả là SOAP Fault |
| TLS handshake failure | SSL/TLS connection | Truststore, certificate, mTLS |

**Một HTTP 500 không tự chứng minh validator đã chạy.** Chỉ khi xác định được SOAP response/Fault và log hoặc test điều kiện XSD cụ thể, mới có cơ sở đánh giá chức năng validation.

## 8. XSD validation khác JAXB và Bean Validation như thế nào?

Khi dùng JAXB/XJC, lớp Java sinh từ schema có thể khai báo:

~~~java
@XmlElement(name = "orderId", required = true)
protected String orderId;
~~~

Annotation `required=true` không làm cho mọi lời gọi `setOrderId(null)` ném exception. JAXB thường chịu trách nhiệm **ánh xạ**, không mặc định bảo đảm toàn bộ ràng buộc schema như pattern, length, enumeration, `maxOccurs` hoặc quan hệ giữa các phần tử.

| Công cụ | Kiểm tra gì? | Ví dụ |
| --- | --- | --- |
| XSD + `PayloadValidatingInterceptor` | Cấu trúc XML trên dây theo schema | QName, thứ tự, kiểu số, pattern, `minOccurs` |
| JAXB marshaller/unmarshaller | Ánh xạ XML ↔ object Java | `XMLGregorianCalendar`, enum, list, root element |
| Bean Validation (Jakarta Validation) | Các constraint áp dụng trên object Java nếu được kích hoạt | `@NotBlank`, `@Size`, quy tắc do ứng dụng khai báo |
| Business validation | Quy tắc domain và hệ thống | Quyền hủy đơn, tồn kho, trạng thái chuyển tiếp |

Hai kiểu validation có thể bổ sung nhau:

1. **XSD validation** chặn payload sai hợp đồng XML.
2. **Bean/domain validation** kiểm tra quy tắc không thể hoặc không nên biểu diễn trong XSD.

Ví dụ `orderId="ORD-9999"` hợp pattern nhưng không tồn tại trong database. Interceptor có thể chấp nhận request; nghiệp vụ vẫn phải trả lỗi “không tìm thấy” theo contract. Đây **không phải lỗ hổng của XSD validation** mà là ranh giới trách nhiệm.

### 8.1. Trường hợp `minOccurs`, `nillable` và giá trị rỗng

Ba trạng thái cần được thiết kế rõ:

~~~xml
<!-- Không có phần tử dueDate -->
~~~

~~~xml
<o:dueDate/>
~~~

~~~xml
<o:dueDate
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

- `minOccurs="0"` cho phép **vắng mặt** phần tử.
- `nillable="true"` cho phép phần tử hiện diện với `xsi:nil="true"`.
- Một phần tử rỗng như `<o:dueDate/>` có thể hợp lệ với `xs:string` nhưng **không hợp lệ** với `xs:date` thông thường.

Một property JAXB có giá trị `null` không nhất thiết phân biệt đủ absent và explicit nil. Test validation cần dùng **XML thật**, không chỉ so sánh object Java.

## 9. Nhiều schema và các quan hệ `xs:include`/`xs:import`

Hệ thống doanh nghiệp thường không chỉ có một XSD file. Ví dụ:

~~~text
xsd/
├── orders.xsd
├── common-types.xsd
└── customer-types.xsd
~~~

`orders.xsd` có thể dùng:

~~~xml
<xs:include schemaLocation="common-types.xsd"/>
~~~

khi file được include có **cùng target namespace** (hoặc là *chameleon schema* không khai báo targetNamespace theo quy tắc XSD).

Với một schema thuộc namespace khác, sử dụng `xs:import`:

~~~xml
<xs:import
    namespace="urn:example:customers:v1"
    schemaLocation="customer-types.xsd"/>
~~~

Sau đó các type từ namespace nhập vào được tham chiếu bằng prefix trỏ đúng URI, ví dụ `cust:CustomerIdType`.

### 9.1. Chọn cách cấu hình schema

- Với **một file XSD tương đối độc lập**, `SimpleXsdSchema` dễ hiểu và đủ cho ví dụ đơn giản.
- Với **nhiều XSD liên kết** và cần giải quyết import/include, cân nhắc abstraction **`XsdSchemaCollection`** và implementation thích hợp như **`CommonsXsdSchemaCollection`** của Spring XML theo phiên bản đang dùng, hoặc cơ chế schema resolution được framework hỗ trợ.
- Với **nhiều namespace không liên quan**, không trộn bừa mọi XSD vào một interceptor nếu chúng không được tổ chức thành tập schema hợp lệ và không được scope đúng endpoint.
- Khi cấu hình XSD cho WSDL và validator, cần kiểm tra cả **schema location** và cách resolver thực tế tìm tài nguyên trong JAR/WAR.

Đừng sửa `schemaLocation` trong XSD thành một URL ngoài ngẫu nhiên chỉ để build chạy. Cần quản lý tài nguyên được phép truy cập, offline build, version schema và security policy.

### 9.2. Schema đơn không nhận diện được mọi payload

Giả sử cùng SOAP servlet có:

- `GetOrderRequest` trong namespace `urn:example:orders:v1`.
- `CreateInvoiceRequest` trong namespace `urn:example:invoices:v1`.

Nếu một `PayloadValidatingInterceptor` dùng **chỉ** `orders.xsd` và áp dụng cho mọi endpoint, request hóa đơn có thể bị từ chối **dù nó hợp schema riêng của hóa đơn**.

Phương án kiến trúc có thể bao gồm:

1. Xây dựng **tập schema** có thể kiểm tra cả hai namespace khi phù hợp.
2. Tổ chức **interceptor theo nhóm endpoint/service** nếu ứng dụng có cơ chế scope/mapping tương ứng.
3. Tách cấu hình SOAP servlet/application context theo hợp đồng nếu cần cô lập rõ.
4. Dùng một cơ chế lựa chọn schema theo QName có kiểm soát nếu yêu cầu dự án phức tạp; phải kiểm thử chính xác scope và thứ tự xử lý.

**Không tồn tại phép tự động bảo đảm một XSD được chọn đúng theo URL HTTP.** Định tuyến HTTP và QName payload khác nhau; phải thiết kế schema selection phù hợp chiến lược endpoint mapping.

### 9.3. Quản lý version của schema

Thay `targetNamespace` từ `...:v1` sang `...:v2` có thể làm `@PayloadRoot` và JAXB classes của client cũ không còn khớp. Đổi `pattern`, enumeration hoặc yêu cầu `minOccurs` cũng có thể khiến những request trước đây hợp lệ bị từ chối.

Với dịch vụ công bố cho nhiều đối tác:

- Quản lý bản XSD/WSDL được phát hành theo version.
- Đảm bảo schema mà interceptor dùng khớp hợp đồng đang được công bố.
- Chạy contract regression tests với các payload cũ.
- Không “siết” schema âm thầm mà không đánh giá tác động đến client.
- Khi cùng phục vụ v1/v2, xác định rõ cách ánh xạ endpoint và chọn validator từng phiên bản.

## 10. Thứ tự interceptor: validation, security và authorization

Một ứng dụng có thể cần đồng thời:

~~~text
SOAP request
  ├── xử lý SOAP Header / WS-Security
  ├── kiểm tra XSD payload
  ├── đối chiếu quyền gọi operation
  └── thực thi nghiệp vụ
~~~

Trong thực tế, **thứ tự interceptor được đăng ký có thể ảnh hưởng hành vi**, và một số xử lý (chẳng hạn đọc SOAP Envelope, chọn endpoint) diễn ra **trước** chain endpoint interceptor.

Một số nguyên tắc:

1. Validation không được coi là thay thế **authentication/authorization**.
2. Không cho chạy nghiệp vụ nhạy cảm khi request chưa qua kiểm soát security cần thiết.
3. Các XML parser ở tầng thấp phải được harden **ngay khi nhận XML**, không chờ validator chặn XXE sau khi XML đã được parse.
4. Đăng ký interceptor rõ ràng và **kiểm thử thứ tự thực tế** khi có nhiều interceptor, đặc biệt khi một interceptor có thể dừng chain.
5. Xác định hành vi khi validation failure, security failure hoặc SOAP Header `mustUnderstand` xảy ra: loại Fault và log có thể khác nhau.

**Ví dụ:** một request có root QName đúng và Body hợp XSD, nhưng SOAP Header chứa timestamp WS-Security hết hạn. Validator có thể không phản đối payload; security interceptor vẫn phải từ chối. Ngược lại, request có chữ ký hợp lệ chưa chắc có `orderId` theo đúng XSD.

## 11. Cấu hình an toàn khi biên dịch và đọc XML Schema

XML có thể chứa DTD, external entities hoặc các tham chiếu schema. Nếu xử lý XML từ người dùng/đối tác không đáng tin cậy, phải giảm nguy cơ **XXE**, SSRF, đọc file nội bộ và tấn công tiêu tốn tài nguyên.

### 11.1. Không lấy schema validation từ input không tin cậy

Một XML instance có thể chứa:

~~~xml
<o:GetOrderRequest
    xmlns:o="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation=
      "urn:example:orders:v1 https://attacker.example/schema.xsd">
    <o:orderId>ORD-1001</o:orderId>
</o:GetOrderRequest>
~~~

**Không chọn một URL schema do client tự chỉ định làm nguồn tin cậy để thay thế contract của server.** Validation phải dựa trên XSD được ứng dụng quản lý và cơ chế resolver đã kiểm soát. Cũng không nên tự viết code “đọc `xsi:schemaLocation` rồi tải URL” để validate mà không có ràng buộc truy cập.

Một số parser/validator có thể có hành vi riêng đối với schema hints, external DTD và imports; cần kiểm tra cấu hình JAXP/Spring-WS thực tế thay vì mặc định mọi implementation chặn hết.

### 11.2. Nguyên tắc bảo vệ parser và schema resolver

- **Giới hạn kích thước SOAP request**, độ sâu XML, số lượng node/attribute phù hợp khả năng stack và gateway.
- **Hạn chế external DTD/schema access** và tắt những cơ chế XML external entity không cần thiết trong parser/message factory.
- Kiểm soát `xs:include`/`xs:import`: chỉ cho phép tài nguyên từ classpath hoặc kho tin cậy.
- Từ chối các cấu hình quan trọng không được provider hỗ trợ thay vì silently ignore.
- Không log toàn bộ XML payload chứa PII/token, đặc biệt trong thông báo lỗi validation.
- Xác minh cả dependency/runtime SOAP parser, JAXB và XML security nếu ứng dụng dùng nhiều XML processor khác nhau.

`PayloadValidatingInterceptor` kiểm tra schema **không thể bảo vệ hệ thống khỏi rủi ro đã xảy ra ở bước parser trước nó**. Việc bảo vệ XML phải bắt đầu từ cách dữ liệu được đọc vào.

### 11.3. Ví dụ JAXP khi cần validator riêng ngoài Spring-WS

Để hình dung các thiết lập bảo vệ, một thành phần **tự compile XSD** có thể dùng JAXP:

~~~java
import javax.xml.XMLConstants;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;

SchemaFactory factory = SchemaFactory.newInstance(
        XMLConstants.W3C_XML_SCHEMA_NS_URI);
factory.setFeature(
        XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setProperty(
        XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setProperty(
        XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema = factory.newSchema(
        trustedLocalSchemaSource);
~~~

`trustedLocalSchemaSource` là một `Source` do ứng dụng cung cấp và có `systemId`/resource resolver phù hợp khi schema dùng import/include. Đoạn code chỉ là **ví dụ bảo vệ một đường biên dịch XSD riêng**, không phải cách đặt properties trực tiếp lên `PayloadValidatingInterceptor`. Khi cần import/include cục bộ, phải tổ chức resolver rõ ràng thay vì bỏ bảo vệ bằng cách cho phép đọc bất kỳ URL ngoài.

## 12. Kiểm thử `PayloadValidatingInterceptor` trong Spring-WS

### 12.1. Test logic Spring-WS bằng `MockWebServiceClient`

`MockWebServiceClient` hỗ trợ gửi SOAP payload vào application context Spring-WS mà không cần mở cổng HTTP thật. Một mẫu test:

~~~java
import static org.springframework.ws.test.server.RequestCreators
        .withPayload;
import static org.springframework.ws.test.server.ResponseMatchers
        .noFault;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

class OrderEndpointValidationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void validPayloadIsAccepted() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(context);

        String xml =
                "<o:GetOrderRequest " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:orderId>ORD-1001</o:orderId>" +
                "</o:GetOrderRequest>";

        client.sendRequest(withPayload(new StringSource(xml)))
                .andExpect(noFault());
    }
}
~~~

Test ví dụ giả định được chạy trong **Spring test context chứa cấu hình Spring-WS và endpoint**, như `@SpringBootTest` hoặc cấu hình test tương đương, cùng dependency Spring-WS test tương thích. Nếu context không được khởi tạo, chỉ đặt `@Autowired` trong một class thường không làm injection hoạt động.

Lưu ý: với request hợp lệ, chỉ assert `noFault()` chưa đủ chứng minh **response đúng schema**; có thể thêm assertion về root QName và giá trị theo XML hoặc response matcher phù hợp. Để chứng minh validation chạy, đặc biệt cần **test một payload có root QName đúng nhưng sai XSD**.

### 12.2. Kiểm thử request sai schema

Ví dụ đầu vào để thử interceptor:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>INVALID</o:orderId>
</o:GetOrderRequest>
~~~

Root `GetOrderRequest` vẫn đúng QName, nên endpoint mapping có cơ sở chọn handler. Tuy nhiên `INVALID` vi phạm `xs:pattern`. Test cần khẳng định:

1. Validator từ chối request theo cấu hình.
2. **Endpoint nghiệp vụ không được gọi theo đường thành công**.
3. Phản hồi/Fault thuộc nhóm lỗi contract được quy định; không lộ stack trace.

Với một số cấu hình SOAP 1.1, có thể kiểm tra bằng response matcher dành cho SOAP Fault loại phía client/sender, nhưng kết quả chính xác phụ thuộc handler và mapping của phiên bản. Không viết test chỉ so sánh **HTTP 500** để kết luận validator đã hoạt động; mock SOAP client thường không kiểm thử HTTP layer.

### 12.3. Kiểm thử response sai schema

Giả lập một endpoint trả:

~~~xml
<o:GetOrderResponse xmlns:o="urn:example:orders:v1">
    <o:status>SUCCESS</o:status>
    <o:itemCount>-2</o:itemCount>
</o:GetOrderResponse>
~~~

Nếu bật `setValidateResponse(true)`, response trên vi phạm **hai ràng buộc**:

- `SUCCESS` không thuộc enum `FOUND/NOT_FOUND`.
- `-2` không hợp `xs:nonNegativeInteger`.

Test cần ghi nhận hành vi interceptor/resolver khi response sai; không chấp nhận response nghiệp vụ thành công mà không phát hiện vi phạm. Với operation có tác dụng phụ, kiểm thử thêm cơ chế báo lỗi và khả năng đối soát sau khi nghiệp vụ đã hoàn tất.

### 12.4. Ma trận kiểm thử đề xuất

| Input / điều kiện | Kỳ vọng | Vì sao? |
| --- | --- | --- |
| `orderId=ORD-1001` | Hợp XSD | Khớp pattern và length |
| Bỏ `orderId` | Bị validator từ chối | Phần tử bắt buộc |
| `orderId=BAD` | Bị từ chối | Không khớp `xs:pattern` |
| `orderId=ORD-1` | Bị từ chối | Quá ít chữ số |
| `includeItems=true` | Hợp XSD | Boolean hợp lệ |
| `includeItems=maybe` | Bị từ chối | Không thuộc lexical space của `xs:boolean` |
| `includeItems` đứng trước `orderId` | Bị từ chối | Sai `xs:sequence` |
| `orderId` không namespace | Bị từ chối | Sai `elementFormDefault=qualified` |
| Prefix `o` đổi thành `x` nhưng URI giữ nguyên | Vẫn hợp XSD | QName không thay đổi |
| Root dùng namespace `v2` thay `v1` | Không match mapping v1 hoặc validation fail theo tuyến xử lý | Sai QName root |
| `itemCount=-1` trong response | Response invalid khi validation response bật | `nonNegativeInteger` |
| `status=SUCCESS` trong response | Response invalid khi validation response bật | Sai enum |
| SOAP 1.2 Envelope vào binding chỉ hỗ trợ SOAP 1.1 | Lỗi SOAP version/transport | Không phải lỗi pattern XSD |
| HTTP POST đến URL WSDL `.wsdl` | Lỗi URL/method theo server | Không phải lỗi schema request |
| SOAP Header token hết hạn, Body hợp schema | Security layer từ chối theo policy | XSD không xác thực token |
| Input có DTD/external entity | Parser/security policy chặn | XXE xảy ra trước validation |
| Hai contract khác namespace dùng chung interceptor một schema | Không loại nhầm operation hợp lệ của contract khác | Scope schema cần đúng |

### 12.5. Test HTTP thực ngoài mock

Để kiểm tra endpoint end-to-end, gửi SOAP 1.1 tới URL do `soap:address` công bố:

~~~http
POST /ws/orders HTTP/1.1
Host: localhost:8080
Content-Type: text/xml; charset=utf-8
SOAPAction: ""
~~~

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
    <soap:Header/>
    <soap:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Vì WSDL ví dụ không khai báo `soapAction` riêng, HTTP action rỗng được dùng để minh họa SOAP 1.1; với dịch vụ thực, phải tuân thủ action WSDL/runtime đã công bố.

Thực hiện thêm các phép thử qua HTTPS gateway và proxy để xác định HTTP status, TLS, WSDL public URL, Content-Type và lỗi transport. `MockWebServiceClient` **không thay thế** kiểm thử Servlet mapping hay chứng chỉ TLS.

## 13. Các lỗi cấu hình thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Request sai schema vẫn vào nghiệp vụ | Validator chưa đăng ký hoặc validation request tắt | `WsConfigurer.addInterceptors`, endpoint chain, `validateRequest` |
| WSDL có XSD đúng nhưng server không kiểm tra | Chỉ đăng ký `XsdSchema`/`DefaultWsdl11Definition` | Kiểm tra có `PayloadValidatingInterceptor` thực sự |
| Mọi request của service B bị từ chối | Validator dùng XSD của service A | Bean qualifier, XSD collection, scope interceptor |
| Missing field không gây lỗi ở JAXB object | JAXB không tự enforce toàn bộ XSD facet | Test payload thật qua validator |
| Root `GetOrderRequest` không vào endpoint | Sai namespace hoặc handler chưa scan | `@PayloadRoot`, URI/local name, component scan |
| `schemaLocation` import không resolve được | Resource path hoặc resolver thiếu | Classpath, `xs:include`/`xs:import`, packaging |
| WSDL chỉ hoạt động local | `soap:address` dùng URL nội bộ | Proxy, servlet mapping, WSDL public |
| Response bị validator từ chối | Response XSD khác payload thực tế | `validateResponse`, serializer, JAXB schema |
| SOAP Fault không có detail như mong đợi | Chưa thiết kế/gắn resolver và Fault contract | Response thực tế và exception handling |
| HTTP 415 | SOAP Content-Type/version lệch | SOAP 1.1 vs SOAP 1.2 binding |
| SOAP Header lỗi chữ ký | WS-Security policy, không phải XSD payload | Token/signature/certificate |
| DTD ngoài được tải | XML parser/hệ thống resolver chưa harden | JAXP/SAAJ parser, XXE tests |

**Cách chẩn đoán hiệu quả nhất** là gửi lần lượt một request **hợp lệ** và một request **chỉ sai đúng một facet XSD** qua cùng endpoint. Nếu cả hai cùng thành công, validation có thể chưa chạy; nếu cả hai cùng thất bại, có thể schema, mapping hoặc hạ tầng sai. Tách từng biến số để xác định nguyên nhân.

## 14. Thiết kế vận hành: hiệu năng, quan sát và thay đổi hợp đồng

### 14.1. Chi phí kiểm tra XML

XSD validation cần parse/đánh giá XML theo schema và có thể ảnh hưởng latency, nhất là với SOAP Body lớn hoặc nhiều phần tử lặp. Cách giảm rủi ro:

- Tải/biên dịch schema trong vòng đời cấu hình ứng dụng, tránh tự compile XSD mỗi request.
- Đo latency và memory ở các kích thước request thực tế.
- Đặt giới hạn kích thước payload ở reverse proxy/Servlet container/parser.
- Dùng XML streaming phù hợp với bài toán khi cần, nhưng không giả định mọi SOAP stack đều thực hiện validation streaming hoàn toàn.
- Không tắt validation một cách âm thầm chỉ vì kết quả benchmark chậm; cần xác định yêu cầu bảo mật và hợp đồng của đối tác.

### 14.2. Log và metrics

Nên quan sát:

~~~text
correlationId
soapVersion
operation / payloadQName
schemaVersion
validationOutcome = PASS | FAIL
validationErrorCategory
httpStatus / soapFaultCode
elapsedMillis
~~~

Không log mặc định toàn bộ SOAP Body chứa PII hay SOAP Header có UsernameToken/signature. Với lỗi validation, có thể lưu mã quy tắc bị vi phạm hoặc tên phần tử đã được làm sạch, giới hạn độ dài và không chép nguyên dữ liệu người dùng.

### 14.3. Thay đổi schema là thay đổi behavior runtime

Giả sử trước đây `orderId` là `xs:string` tùy ý, sau đó nhóm phát triển thêm pattern `ORD-[0-9]{4,12}`. Client cũ từng gửi `LEGACY-ABC` có thể bắt đầu nhận lỗi ngay khi interceptor dùng schema mới, **dù endpoint Java không thay đổi**.

Vì vậy trong CI/CD:

1. Kiểm tra diff XSD/WSDL so với version đang vận hành.
2. Chạy regression tests với payload của client hiện tại.
3. Xác minh validator và WSDL được cấu hình **cùng version**.
4. Đánh giá backward compatibility và quy trình thông báo đối tác.
5. Triển khai v1/v2 song song khi có thay đổi phá vỡ contract.

## 15. Bài tập tình huống

Một SOAP service quản lý hóa đơn có hai operation:

- `CreateInvoiceRequest` ở namespace `urn:example:invoice:v1`.
- `GetOrderRequest` ở namespace `urn:example:orders:v1`.

Ứng dụng đã nạp hai file XSD để tạo WSDL, nhưng trong `WsConfigurer` lại dùng duy nhất:

~~~java
PayloadValidatingInterceptor validator =
        new PayloadValidatingInterceptor();
validator.setXsdSchema(ordersSchema);
validator.setValidateRequest(true);
interceptors.add(validator);
~~~

Kết quả: truy vấn đơn hàng hoạt động, còn tạo hóa đơn bị báo sai schema dù request đúng XSD hóa đơn.

**Câu hỏi:**

1. Vì sao có hai `XsdSchema` bean trong context vẫn chưa đủ?
2. Vấn đề là thiếu `@PayloadRoot`, sai XML hay scope schema validation?
3. Có thể giải quyết bằng cách đổi tên bean WSDL `orders` thành `invoices` không?
4. Nếu thêm response validation, cần làm gì với schema của cả hai response?
5. Một client gửi payload đúng schema nhưng không có quyền tạo hóa đơn thì validator có nên cho đi qua để nghiệp vụ kiểm tra quyền không?

**Đáp án gợi ý:**

1. Vì interceptor đang được gán **chỉ `ordersSchema`**; việc tồn tại bean `invoiceSchema` để công bố WSDL không làm validator tự sử dụng nó.
2. Nếu root QName được mapping và request đúng XSD hóa đơn, vấn đề chính là **schema selection/scope** của interceptor. Phải xác minh mapping thực tế trước khi kết luận.
3. **Không.** Tên bean WSDL ảnh hưởng cách công bố tài liệu, không tự sửa schema mà interceptor đang kiểm tra.
4. Cấu hình schema collection hoặc interceptor được scope đúng để nhận diện response từng contract, rồi kiểm thử cả hai.
5. **Validation chỉ kiểm tra cấu trúc.** Quyền gọi operation phải được kiểm tra độc lập; không được cho thực thi nghiệp vụ chỉ vì XSD hợp lệ.

### 15.1. Bài thực hành nâng cao

Hãy xây dựng dịch vụ `ReserveStock`:

~~~xml
<s:ReserveStockRequest xmlns:s="urn:example:stock:v1">
    <s:sku>SKU-1001</s:sku>
    <s:quantity>2</s:quantity>
</s:ReserveStockRequest>
~~~

Yêu cầu:

1. Tạo XSD có global element `ReserveStockRequest`, `sku` bắt buộc và `quantity` là `xs:positiveInteger`.
2. Công bố WSDL document/literal và kiểm tra URL `soap:address`.
3. Đăng ký `PayloadValidatingInterceptor` trong Spring-WS với request validation bật.
4. Thử `quantity=0`, số âm, thiếu `sku`, sai namespace, sai thứ tự và XML đúng.
5. Chứng minh nghiệp vụ đặt giữ hàng **không chạy** khi request sai schema.
6. Bổ sung response XSD và bật response validation; thử response thiếu trường bắt buộc.
7. Kiểm thử lỗi SOAP Fault, các trường log an toàn và HTTP transport riêng.
8. Nếu thêm contract thứ hai cùng servlet, giải thích cách ngăn schema của service này từ chối nhầm service kia.

**Tiêu chí đạt:** request/response tuân thủ XSD, interceptor được gắn đúng chain, lỗi không bị nhầm với TLS/HTTP/WS-Security, và thay đổi schema được kiểm soát bằng test.

## 16. Ghi nhớ

- **`PayloadValidatingInterceptor`** dùng XSD để kiểm tra **SOAP payload**, giúp bảo vệ hợp đồng XML trong Spring-WS.
- **`XsdSchema` bean và WSDL publication không tự bật validation**: phải gắn interceptor vào endpoint processing chain.
- **`setValidateRequest(true)`** kiểm tra request; **`setValidateResponse(true)`** kiểm tra response, cần đánh giá chi phí và chính sách xử lý lỗi.
- **`@PayloadRoot` chỉ chọn endpoint theo QName**, không bảo đảm các trường con hợp XSD. Root không match mapping có thể thất bại trước validation interceptor.
- **XSD validation khác JAXB mapping, Bean Validation và business validation**: cùng bổ sung cho nhau, không thay thế nhau.
- Với nhiều XSD hoặc nhiều namespace, phải cấu hình **schema selection/collection và scope interceptor** đúng; không lấy nhầm schema của operation khác.
- Xác thực SOAP Header, WS-Security, TLS, quyền truy cập và XML parser security là **những trách nhiệm riêng**; XSD payload không tự giải quyết chúng.
- **Không mặc định mọi validation failure có cùng SOAP Fault/HTTP status**. Phải kiểm thử với phiên bản SOAP, endpoint mapping và resolver thực tế.
- Luôn kiểm thử **ít nhất một payload hợp lệ và nhiều payload cố ý sai facet XSD**, cùng response validation, concurrency, security và HTTP(S) integration khi cần.
