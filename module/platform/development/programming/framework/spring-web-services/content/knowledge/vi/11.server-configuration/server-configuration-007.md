# Phối hợp cấu hình Spring Boot tự động với các bean do ứng dụng khai báo

## 1. Bài toán: tự động cấu hình đến đâu, tự khai báo đến đâu?

Khi xây dựng dịch vụ **Spring Web Services (Spring-WS)**, Spring Boot giúp tạo môi trường chạy, quản lý dependency và tự đăng ký một số thành phần hạ tầng khi đủ điều kiện. Trong khi đó, đội phát triển vẫn phải xác định **XSD/WSDL, endpoint, chính sách xử lý thông điệp, validation và bảo mật** của riêng dịch vụ.

Ví dụ, ứng dụng có dependency `spring-boot-starter-web-services` và được yêu cầu cung cấp SOAP operation `GetOrder`:

- Spring Boot có thể chuẩn bị việc đăng ký `MessageDispatcherServlet` trên một URL path khi auto-configuration tương ứng được áp dụng.
- Ứng dụng khai báo `XsdSchema`, `DefaultWsdl11Definition` và `@Endpoint` để xác định **hợp đồng và nghiệp vụ cụ thể**.
- Ứng dụng có thể khai báo thêm `SoapMessageFactory`, `EndpointInterceptor`, `Jaxb2Marshaller` và `WebServiceTemplate` khi cần kiểm soát SOAP version, schema validation, WS-Security hoặc client tích hợp.

Điểm khó là quyết định **bean nào nên để Boot cung cấp, bean nào tự khai báo, và khi nào một bean tùy chỉnh làm auto-configuration lùi lại (back off)**. Nếu phối hợp sai, dự án có thể gặp hai servlet trên một mapping, hai bean cùng tên, cấu hình SOAP 1.1/1.2 lệch nhau hoặc công bố WSDL tại một URL nhưng endpoint lại nhận POST ở URL khác.

Trong chương **Cấu hình máy chủ**, bài này tập trung vào cách phối hợp hai nguồn cấu hình đó cho dịch vụ SOAP **contract-first**. Các nguyên tắc còn có ích khi triển khai SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích hệ thống doanh nghiệp.

## 2. Phân chia trách nhiệm giữa Spring Boot và Spring-WS

| Thành phần | Boot thường hỗ trợ | Ứng dụng phải chủ động quyết định |
| --- | --- | --- |
| HTTP server | Khởi động Servlet container nhúng, cổng, context path | Mạng, TLS, proxy, xác thực và cấu hình production |
| `MessageDispatcherServlet` | Có thể đăng ký tự động khi starter và điều kiện phù hợp | URL mapping, các tùy chỉnh servlet không được property hỗ trợ |
| Spring application context | Tạo/đăng ký bean, dependency injection, lifecycle | Tên bean, package scan, tránh cấu hình trùng |
| `@EnableWs` / cơ chế endpoint | Cung cấp thư viện và cơ chế tích hợp | Kích hoạt cấu hình annotation và khai báo `@Endpoint` đúng |
| XSD/WSDL | Cung cấp khả năng triển khai bean công bố WSDL | XSD, `Wsdl11Definition`, namespace, location và version |
| JAXB | Cung cấp các thành phần tích hợp theo dependency | Sinh mã từ XSD, ánh xạ marshaller/unmarshaller |
| SOAP message factory | Có thể có mặc định qua hạ tầng Spring-WS | SOAP 1.1/1.2 và factory tùy chỉnh khi cần |
| Interceptor / SOAP Fault | Có API và điểm mở rộng | XSD validation, WS-Security, fault mapping và thứ tự xử lý |
| SOAP client | Có `WebServiceTemplate` và builder/configuration liên quan tùy phiên bản | Endpoint đối tác, timeout, action, truststore, marshaller |

**Spring Boot auto-configuration không có nghĩa “tự sinh toàn bộ hợp đồng SOAP”.** Chỉ thêm starter không tự tạo XSD, WSDL, các lớp JAXB hoặc một operation có thể xử lý nghiệp vụ. Tương tự, tạo `@Endpoint` không làm URL công khai xuất hiện nếu Servlet chưa được đăng ký đúng.

### 2.1. Phụ thuộc giữa các lớp

~~~mermaid
flowchart TD
    A["Spring Boot application + dependencies"] --> B["Auto-configuration theo điều kiện"]
    A --> C["@Configuration / @Bean của ứng dụng"]
    B --> D["Spring ApplicationContext"]
    C --> D
    D --> E["MessageDispatcherServlet + message factory"]
    D --> F["XSD / WSDL definition"]
    D --> G["@Endpoint / interceptor / Fault resolver"]
    E --> H["SOAP request qua HTTP(S)"]
    H --> G
    G --> I["SOAP response hoặc SOAP Fault"]
~~~

Đây là sơ đồ quan hệ, không phải cam kết chính xác về thời điểm tạo bean. Trình tự khởi tạo thực tế chịu ảnh hưởng của auto-configuration conditions, phụ thuộc bean, cấu hình Servlet container và phiên bản Spring Boot/Spring-WS.

## 3. Cách auto-configuration hoạt động: điều kiện và back-off

Spring Boot nạp các cấu hình tự động dựa trên **điều kiện**, ví dụ loại ứng dụng đang chạy, những lớp có mặt trên classpath, property và các bean đã được khai báo. Trong mã nguồn Boot, những điều kiện kiểu `@ConditionalOnClass`, `@ConditionalOnWebApplication` và `@ConditionalOnMissingBean` được dùng để quyết định có đăng ký bean mặc định hay không.

Luồng tư duy:

~~~mermaid
flowchart TD
    A["Có Spring-WS trên classpath?"] -->|Không| B["Không kích hoạt cấu hình liên quan"]
    A -->|Có| C["Ứng dụng có hỗ trợ Servlet web?"]
    C -->|Không| D["Không đăng ký SOAP HTTP servlet theo nhánh Servlet"]
    C -->|Có| E["Kiểm tra các bean / property / condition"]
    E --> F{"Điều kiện auto-config thỏa?"}
    F -->|Có| G["Boot đăng ký thành phần mặc định"]
    F -->|Không| H["Giữ cấu hình ứng dụng hoặc bỏ qua nhánh này"]
~~~

Ví dụ với một bean mặc định được bảo vệ bởi điều kiện `@ConditionalOnMissingBean`: khi ứng dụng tự khai báo bean phù hợp điều kiện, Boot thường **không tạo bean mặc định tương ứng**. Tuy vậy:

- Không phải **mọi** auto-configuration đều có cùng điều kiện back-off; cần đọc condition report hoặc tài liệu của đúng phiên bản.
- Điều kiện có thể xét **kiểu bean, tên bean hoặc annotation**, không chỉ một tên phương thức Java.
- `@Primary` chỉ ảnh hưởng việc chọn bean khi dependency injection có nhiều ứng viên phù hợp; nó **không xóa một servlet đã đăng ký** và không tự giải quyết hai URL mapping xung đột.
- Hai bean cùng tên không phải một cách cấu hình chủ động an toàn; việc bật bean-definition overriding để “chữa” xung đột có thể che mất cấu hình sai.
- Property do Boot hỗ trợ có thể không còn tác dụng với một thành phần đã được ứng dụng **tạo và đăng ký thủ công**.

Vì vậy không nên phát biểu “bean tự khai báo luôn thắng tất cả mặc định Boot”. Phải kiểm tra **chính xác bean nào được tạo, auto-configuration nào đã back off và servlet nào đang phục vụ URL**.

## 4. Bộ ví dụ chung: SOAP OrderService theo contract-first

Để đối chiếu giữa cách dựa vào auto-configuration và cách tự khai báo bean, ta dùng một hợp đồng nhỏ: `GetOrderRequest` nhận mã đơn hàng; `GetOrderResponse` trả trạng thái đơn hàng.

File `src/main/resources/xsd/orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
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
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Hai global elements dùng namespace `urn:example:orders:v1`. Phần tử con `orderId` và `status` cũng thuộc namespace này do `elementFormDefault="qualified"`.

### 4.1. Dependencies

Một đoạn dependencies trong `pom.xml` dành cho ứng dụng Spring Boot/Maven:

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

Đây **không phải một POM đầy đủ**: dự án còn phải có Boot parent hoặc BOM, phiên bản Java/build plugin phù hợp và phiên bản cho dependency nào không được BOM quản lý. Thư viện `wsdl4j` được sử dụng trong cơ chế tạo WSDL 1.1 của Spring-WS. Cần kiểm tra dependency tree và khả năng tương thích thực tế của tổ hợp phiên bản.

Với dự án Spring hiện đại, cần chọn nhất quán thế hệ **Jakarta Servlet/JAXB**; không trộn API `javax.servlet` cũ với runtime yêu cầu `jakarta.servlet`. Các API Java XML như `javax.xml.transform` vẫn giữ package `javax` và **không** đồng nghĩa đang dùng JAXB/Servlet cũ.

### 4.2. Entry point Boot

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

Đặt các class cấu hình và endpoint dưới package `example.orders.ws` để component scanning có thể tìm thấy. Đây là điểm khởi động Spring Boot; các bean hợp đồng được mô tả ngay sau đây.

## 5. Phương án A: giữ servlet do Boot tự động cấu hình

Trong nhiều phiên bản Spring Boot có hỗ trợ Spring Web Services, phần Servlet auto-configuration có thể đăng ký `MessageDispatcherServlet` khi starter, môi trường và các điều kiện phù hợp. Đường dẫn được điều chỉnh qua property của Boot:

~~~properties
server.port=8080
spring.webservices.path=/ws
~~~

Ở các phiên bản Boot hỗ trợ property này, `spring.webservices.path` chọn **đường dẫn gốc của SOAP servlet**. Với cấu hình minh họa, WSDL bean tên `orders` thường có thể truy cập qua:

~~~text
http://localhost:8080/ws/orders.wsdl
~~~

và SOAP request được gửi tới URL khớp servlet mapping, chẳng hạn:

~~~text
http://localhost:8080/ws/orders
~~~

**Hãy xác minh phiên bản Boot và servlet mapping thực tế.** Cú pháp property và cơ chế đăng ký có thể thay đổi giữa các thế hệ; khi ứng dụng tự đăng ký servlet, property này không nhất thiết điều khiển được servlet thủ công.

### 5.1. Ứng dụng khai báo hợp đồng XSD/WSDL

~~~java
package example.orders.ws;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class WsContractConfig {

    private static final String NS = "urn:example:orders:v1";

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(
            XsdSchema ordersSchema) {
        DefaultWsdl11Definition definition =
                new DefaultWsdl11Definition();
        definition.setPortTypeName("OrdersPort");
        definition.setServiceName("OrderService");
        definition.setTargetNamespace(NS);
        definition.setLocationUri("/ws/orders");
        definition.setSchema(ordersSchema);
        definition.setCreateSoap11Binding(true);
        definition.setCreateSoap12Binding(false);
        return definition;
    }
}
~~~

Giải thích từng phần:

| Thành phần | Vai trò |
| --- | --- |
| `@EnableWs` | Kích hoạt hỗ trợ endpoint Spring-WS dùng annotation trong context |
| `@Bean XsdSchema ordersSchema` | Đưa XSD thật của ứng dụng vào context |
| `@Bean(name = "orders")` | Tên WSDL definition dùng để xuất bản `orders.wsdl` theo convention của servlet |
| `setPortTypeName("OrdersPort")` | Tên portType được sinh trong WSDL 1.1 |
| `setTargetNamespace(NS)` | Namespace của các thành phần WSDL được tạo |
| `setLocationUri("/ws/orders")` | Địa chỉ SOAP được công bố trong `soap:address` |
| `setCreateSoap11Binding(true)` | Sinh binding SOAP 1.1 trong ví dụ |

`DefaultWsdl11Definition` có thể suy ra operation `GetOrder` từ hậu tố `Request`/`Response` theo quy ước mặc định. Nó **không tự sinh lớp Java JAXB** và không triển khai nghiệp vụ. Hãy xem WSDL được xuất bản để xác nhận input/output, binding, action và address đúng mong đợi.

Điểm quan trọng trong phối hợp cấu hình: **Boot đăng ký servlet**, còn **ứng dụng cung cấp WSDL definition và schema**. Không phải khai báo `@Bean Wsdl11Definition` là yêu cầu Boot phải bỏ servlet mặc định.

### 5.2. Khai báo `@Endpoint` mà không tự tạo servlet mới

Để thử việc ánh xạ SOAP payload, dùng endpoint nhận `Element` và trả `Source` (không cần sinh JAXB trước):

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
        if (ids.getLength() != 1
                || ids.item(0).getTextContent().isBlank()) {
            throw new IllegalArgumentException(
                    "Exactly one nonempty orderId is required");
        }

        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>FOUND</o:status>" +
                "</o:GetOrderResponse>");
    }
}
~~~

Đây là **smoke test cấu hình**, không phải endpoint nghiệp vụ hoàn chỉnh. Phần trả về là XML cố định và các trường hợp lỗi chưa được ánh xạ thành SOAP Fault theo hợp đồng. Với hệ thống thực, hãy dùng lớp JAXB sinh từ XSD và validation trước khi xử lý.

Hai yếu tố cần phân biệt:

1. `@PayloadRoot` chọn endpoint theo **QName của phần tử đầu trong SOAP Body**. Nó không tự thiết lập URL servlet.
2. `@Endpoint` là Spring stereotype được cơ chế Spring-WS phát hiện trong context; nó **không tương đương `@RestController`** và không tạo một HTTP route kiểu Spring MVC.

Nếu WSDL tải được nhưng POST trả lỗi “No endpoint mapping found”, hãy kiểm tra package scan, `@EnableWs` và root QName trước khi thay URL.

## 6. Phương án B: tự đăng ký servlet để chỉnh hành vi nâng cao

Có những yêu cầu mà property mapping của Boot không đủ, ví dụ cần:

- Bật cơ chế biến đổi `soap:address` khi công bố WSDL qua reverse proxy.
- Thiết lập rõ các tùy chọn khởi tạo của `MessageDispatcherServlet`.
- Tích hợp SOAP servlet vào cấu hình Servlet container hiện hữu.
- Sử dụng URL mapping đặc biệt và kiểm soát chính xác thứ tự đăng ký.

Khi đó ứng dụng có thể đăng ký `MessageDispatcherServlet` thông qua `ServletRegistrationBean`:

~~~java
package example.orders.ws;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

@Configuration
public class ExplicitSoapServletConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
            ordersSoapServlet(ApplicationContext context) {

        MessageDispatcherServlet servlet =
                new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);

        ServletRegistrationBean<MessageDispatcherServlet> registration =
                new ServletRegistrationBean<>(servlet, "/ws/*");
        registration.setName("orders-soap-servlet");
        return registration;
    }
}
~~~

Đây là **phương án thay thế** cấu hình servlet tự động ở mục 5, không phải mã nên thêm vào cùng một ứng dụng mà chưa kiểm tra auto-configuration. Một số phiên bản Boot có cơ chế back-off khi phát hiện bean đăng ký servlet tương ứng; ở các phiên bản/cấu hình khác, bạn có thể phải tắt phần auto-configuration cụ thể hoặc điều chỉnh registration để **chỉ còn một SOAP servlet phục vụ mapping dự định**.

### 6.1. Tránh hai registration tranh chấp URL

Không nên làm:

~~~text
Boot auto-config:
    MessageDispatcherServlet A -> /ws/*

Application @Bean:
    MessageDispatcherServlet B -> /ws/*

Kết quả:
    mapping xung đột hoặc request đi đến servlet/context
    không phải servlet mà nhóm phát triển nghĩ đang dùng.
~~~

Quy trình an toàn:

1. Chọn **A (Boot quản lý registration)** hoặc **B (ứng dụng quản lý registration)** cho môi trường triển khai.
2. Nếu chọn B, kiểm tra condition report để xác nhận nhánh đăng ký servlet tự động đã back off hoặc đã được loại trừ bằng cấu hình của đúng phiên bản.
3. Xác nhận Servlet container chỉ có **một mapping mong muốn** cho `/ws/*`.
4. Kiểm tra GET `/ws/orders.wsdl` và POST `/ws/orders`.
5. Đảm bảo URL trong `soap:address` đúng với đường dẫn được container/gateway phục vụ.

Đừng bật `spring.main.allow-bean-definition-overriding=true` chỉ để ép một cấu hình đè lên cấu hình khác. Bean overriding giải quyết xung đột **tên bean**, không bảo đảm xung đột **servlet mapping** hay các dependency đã được tạo trước đó sẽ biến mất.

### 6.2. Transform WSDL locations khi chạy sau reverse proxy

Giả sử hạ tầng:

~~~text
SOAP client
  -> https://api.example.test/soap/orders
  -> gateway (public URL)
  -> http://orders:8080/ws/orders
  -> MessageDispatcherServlet
~~~

WSDL được phục vụ qua gateway có thể sai nếu công bố địa chỉ nội bộ:

~~~xml
<soap:address location="http://orders:8080/ws/orders"/>
~~~

`setTransformWsdlLocations(true)` có thể điều chỉnh địa chỉ công bố dựa trên request tới servlet. Tuy nhiên nó **không tự biết** domain public nếu reverse proxy không truyền và ứng dụng không xử lý đúng metadata được tin cậy về host, scheme, port và path.

Nếu gateway đổi `/ws/orders` thành `/soap/orders`, cần phối hợp **location URI, servlet mapping, forwarded headers và route rewrite**. Không tự tin rằng chỉ bật transform sẽ sửa được mọi trường hợp. Hãy tải WSDL **qua URL thực tế mà đối tác nhìn thấy** và so sánh `soap:address/@location` với URL dùng gửi SOAP POST.

## 7. Bean hạ tầng khác bean hợp đồng: cách tránh ghi đè nhầm

Các bean liên quan đến Spring-WS có thể được chia theo trách nhiệm:

| Nhóm | Ví dụ | Thường do ai quản lý? |
| --- | --- | --- |
| Transport/bootstrap | Servlet registration, HTTP server | Boot hoặc cấu hình chủ động của ứng dụng |
| SOAP message infrastructure | `WebServiceMessageFactory` / `SoapMessageFactory` | Mặc định của hạ tầng hoặc bean tùy chỉnh |
| Contract | `XsdSchema`, `Wsdl11Definition` | Ứng dụng |
| Endpoint | `@Endpoint`, mapping, adapter | Hỗ trợ Spring-WS + endpoint của ứng dụng |
| Cross-cutting | `EndpointInterceptor`, Fault resolver | Ứng dụng |
| Client integration | `Jaxb2Marshaller`, `WebServiceTemplate` | Ứng dụng hoặc builder/configuration phù hợp |

Một bean `XsdSchema` của ứng dụng **không đè** một `SoapMessageFactory` vì chúng là hai kiểu khác nhau. Ngược lại, hai bean cùng kiểu `XsdSchema` có thể làm một tham số method hoặc constructor cần `XsdSchema` trở nên mơ hồ nếu không có `@Qualifier` hoặc tên tham số khả dụng.

### 7.1. Khi ứng dụng có nhiều XSD

~~~java
@Bean("ordersSchema")
public XsdSchema ordersSchema() {
    return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders.xsd"));
}

@Bean("customersSchema")
public XsdSchema customersSchema() {
    return new SimpleXsdSchema(
            new ClassPathResource("xsd/customers.xsd"));
}

@Bean(name = "orders")
public DefaultWsdl11Definition ordersWsdl(
        @Qualifier("ordersSchema") XsdSchema schema) {
    DefaultWsdl11Definition definition =
            new DefaultWsdl11Definition();
    definition.setPortTypeName("OrdersPort");
    definition.setTargetNamespace("urn:example:orders:v1");
    definition.setLocationUri("/ws/orders");
    definition.setSchema(schema);
    return definition;
}
~~~

Đoạn này là **biến thể thay thế**, không thêm song song với bean `ordersSchema` và `ordersWsdl` cùng tên ở mục 5.2. Nó giả định bạn đã import `@Bean`, `@Qualifier`, `ClassPathResource`, `XsdSchema`, `SimpleXsdSchema` và `DefaultWsdl11Definition`. Dùng `@Qualifier` bảo đảm WSDL đơn hàng nhận **schema đơn hàng**, không phụ thuộc thứ tự tạo bean.

### 7.2. Khi có nhiều bean cùng interface

Quy tắc:

- Nếu một nơi cần chính xác một bean, dùng **`@Qualifier`** hoặc cơ chế lựa chọn rõ ràng.
- `@Primary` có thể chọn ứng viên mặc định trong injection, nhưng không phân biệt các WSDL đã công bố theo tên.
- Bean `Wsdl11Definition` thường được nhận diện theo **tên bean** khi phục vụ URL `<bean-name>.wsdl`. Đổi tên bean có thể đổi URL WSDL public.
- Nếu tự đặt bean với tên hạ tầng đã được Spring-WS sử dụng theo convention, cần hiểu cơ chế lookup theo tên và khả năng trùng bean.

Không dùng một cơ chế chọn bean để giải quyết vấn đề thuộc cơ chế khác. Chẳng hạn `@Primary` không thể khắc phục `/ws/*` bị đăng ký hai lần.

## 8. Tùy chỉnh `SoapMessageFactory`: SOAP 1.1 và SOAP 1.2

Thông thường Spring-WS có khả năng tạo SOAP message bằng một message factory như `SaajSoapMessageFactory`. Nếu hợp đồng chỉ dùng SOAP 1.1 và mặc định được cấu hình đúng, không cần tự khai báo factory.

Khi cần kiểm soát SOAP version, có thể khai báo bean được servlet/adapter tra cứu theo quy tắc của phiên bản Spring-WS đang dùng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Configuration
public class SoapFactoryConfig {

    @Bean(name = "messageFactory")
    public SaajSoapMessageFactory messageFactory() {
        SaajSoapMessageFactory factory =
                new SaajSoapMessageFactory();
        factory.setSoapVersion(SoapVersion.SOAP_11);
        return factory;
    }
}
~~~

Spring quản lý vòng đời bean và thực hiện callback khởi tạo phù hợp; trong code ví dụ không cần tự gọi `afterPropertiesSet()` cho bean do context quản lý. Lựa chọn factory này giả định dependency SAAJ tương thích với Spring-WS đang dùng.

**Lưu ý quan trọng:** tên `messageFactory` là một convention có ý nghĩa trong một số cơ chế Spring-WS servlet/adapter. Cần kiểm tra cấu hình `MessageDispatcherServlet` thực tế, bean name lookup và runtime classpath, không chỉ thấy bean của mình xuất hiện trong context rồi kết luận mọi luồng SOAP đang sử dụng nó.

### 8.1. Khi chuyển sang SOAP 1.2

Nếu đổi:

~~~java
factory.setSoapVersion(SoapVersion.SOAP_12);
~~~

thì còn phải đồng bộ:

1. **WSDL binding**: công bố SOAP 1.2 binding thực sự, không chỉ SOAP 1.1.
2. **SOAP Envelope**: dùng namespace `http://www.w3.org/2003/05/soap-envelope`.
3. **HTTP Content-Type**: điển hình `application/soap+xml` thay vì `text/xml`.
4. **Action**: xử lý phù hợp quy tắc SOAP 1.2/HTTP binding, không áp dụng máy móc SOAP 1.1 `SOAPAction` header.
5. **Client, interceptor và Fault**: kiểm tra chúng tương thích SOAP version mới.

Thay đổi một bean message factory **không tự cập nhật WSDL tĩnh hay client của đối tác**. Với hệ thống có đồng thời SOAP 1.1 và SOAP 1.2, cần thiết kế rõ binding, port, factory và kiểm thử thực tế từng đường gọi.

### 8.2. Factory server khác factory client

`WebServiceTemplate` phía **client** có thể được cấu hình message factory riêng. Bean message factory dùng bởi server servlet không nhất thiết tự được mọi `WebServiceTemplate` mới tạo lựa chọn như mong muốn. Khi cần kiểm soát SOAP version của client, hãy cấu hình rõ trên template/builder và kiểm tra HTTP message gửi đi.

## 9. Phối hợp `@EnableWs`, endpoint mapping và interceptor

`@EnableWs` kích hoạt hạ tầng annotation-driven của Spring-WS trong context. Các `@Endpoint` được Spring phát hiện thông qua component scan; endpoint mapping dùng các annotation như `@PayloadRoot` hoặc `@SoapAction` theo cơ chế đã đăng ký.

Đừng nhầm ba việc:

- **Servlet mapping:** request HTTP đi vào `MessageDispatcherServlet` hay không.
- **Endpoint mapping:** SOAP request đã vào dispatcher sẽ được chuyển tới handler nào.
- **Payload validation:** cấu trúc XML của request có hợp lệ theo XSD hay không.

Một application có thể thành công ở bước đầu nhưng thất bại ở bước sau: POST `/ws/orders` đến đúng servlet mà `@PayloadRoot` không khớp vì namespace sai; hoặc endpoint được chọn nhưng dữ liệu `orderId` vi phạm XSD.

### 9.1. Thêm XSD validation qua `WsConfigurer`

Giả sử đã có bean `XsdSchema ordersSchema`, ứng dụng có thể đăng ký `PayloadValidatingInterceptor`:

~~~java
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class WsValidationConfig implements WsConfigurer {

    private final XsdSchema ordersSchema;

    public WsValidationConfig(
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

Đây là **cấu hình bổ sung** cho dự án đã kích hoạt `@EnableWs` trong `WsContractConfig` ở mục 5.1. Không cần lặp lại `@EnableWs` trên mỗi lớp cấu hình interceptor. Nếu dự án dùng cách tích hợp interceptor khác, chọn một cách đăng ký rõ ràng.

Với `setValidateRequest(true)`, payload request được kiểm tra so với XSD trước khi endpoint thực hiện logic theo quy tắc interceptor chain. Ví dụ đặt `setValidateResponse(false)` để tập trung kiểm thử request; trong ứng dụng thực tế có thể bật validation response sau khi đã định nghĩa đầy đủ response/fault và kiểm tra tác động.

**Không nên coi `XsdSchema` tồn tại trong context là bằng chứng validation đã bật.** Nó có thể chỉ được dùng để sinh WSDL. Ngược lại, thêm validator mà schema không tương thích namespace payload có thể khiến request đúng nghiệp vụ cũng bị từ chối.

### 9.2. SOAP Fault resolver cũng cần cấu hình

Spring-WS có các cơ chế `EndpointExceptionResolver`, ví dụ `SoapFaultAnnotationExceptionResolver` và `SoapFaultMappingExceptionResolver`. Khi muốn chuyển exception nghiệp vụ thành SOAP Fault đúng code/detail, ứng dụng cần đăng ký và kiểm tra thứ tự xử lý resolver.

Không có gì bảo đảm mọi `IllegalArgumentException` hoặc lỗi trong interceptor sẽ biến thành **typed SOAP Fault trong WSDL** chỉ vì có `@EnableWs`. Hãy định nghĩa fault XML trong XSD/WSDL khi đối tác cần contract ổn định và kiểm thử SOAP Body thực tế.

## 10. Bean SOAP client trong cùng ứng dụng server

Ứng dụng SOAP server đôi khi cũng là SOAP client của một dịch vụ khác. Lúc đó có hai cấu hình liên quan nhưng độc lập:

| Vai trò | Thành phần chính |
| --- | --- |
| Server nhận SOAP | `MessageDispatcherServlet`, `@Endpoint`, `Wsdl11Definition` |
| Client gửi SOAP | `WebServiceTemplate`, `Jaxb2Marshaller`, message sender, SOAP action/URL |

Ví dụ tự khai báo client:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class PartnerSoapClientConfig {

    @Bean("partnerMarshaller")
    public Jaxb2Marshaller partnerMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("example.orders.partner.schema");
        return marshaller;
    }

    @Bean("partnerWebServiceTemplate")
    public WebServiceTemplate partnerWebServiceTemplate(
            Jaxb2Marshaller partnerMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(partnerMarshaller);
        template.setUnmarshaller(partnerMarshaller);
        return template;
    }
}
~~~

`example.orders.partner.schema` là **package minh họa** của các lớp JAXB sinh từ XSD đối tác. Cần có runtime JAXB tương thích; một số lớp global element có thể yêu cầu `JAXBElement` từ `ObjectFactory` khi marshal. Trong dự án nhiều marshaller, hãy dùng `@Qualifier("partnerMarshaller")` tại điểm injection để tránh chọn nhầm mapping.

Với SOAP 1.1, `SoapActionCallback` có thể được dùng khi gửi:

~~~java
Object response = partnerWebServiceTemplate.marshalSendAndReceive(
        "https://partner.example.test/soap/orders",
        request,
        new SoapActionCallback("urn:partner:GetOrder"));
~~~

Các biến `partnerWebServiceTemplate` và `request` là đối tượng do ứng dụng tạo; URL/action chỉ là ví dụ. Cần cấu hình timeout, SOAP version, chứng chỉ/truststore và WS-Security phù hợp hợp đồng. Việc Boot có bean builder hoặc cơ chế cấu hình client ở một phiên bản nào đó **không có nghĩa một template tự tạo sẽ luôn mang theo mọi thiết lập transport/security mong muốn**.

### 10.1. Không biến mọi client thành bean toàn cục mơ hồ

Nếu server tích hợp nhiều đối tác, nên định danh:

~~~text
partnerAWebServiceTemplate
partnerBWebServiceTemplate
internalOrderWebServiceTemplate
~~~

Mỗi client có thể có JAXB context, SOAP version, endpoint URL, certificate và timeout riêng. Đừng tạo nhiều `WebServiceTemplate` không tên rõ rồi inject theo kiểu mà không có qualifier; và đừng dùng một truststore hoặc key chung cho mọi đối tác nếu chính sách bảo mật yêu cầu tách biệt.

## 11. Cấu hình property và bean: phân biệt hai mức tùy chỉnh

Spring Boot thường ưu tiên cung cấp **property chính thức** cho những thay đổi phổ biến, như cổng HTTP, context path và SOAP servlet path. Khi cần thao tác không được property hỗ trợ, ứng dụng có thể cần `@Bean` hoặc customizer theo đúng extension point.

| Nhu cầu | Thường nên bắt đầu từ |
| --- | --- |
| Đổi cổng HTTP local | `server.port` |
| Đổi context path toàn ứng dụng | `server.servlet.context-path` |
| Đổi root SOAP path khi dùng Boot-managed servlet | `spring.webservices.path` nếu phiên bản hỗ trợ |
| Định nghĩa phần tử request/response | XSD do ứng dụng quản lý |
| Công bố WSDL cho một service | Bean `Wsdl11Definition` tên rõ ràng |
| Biến đổi `soap:address` theo request | Cấu hình `MessageDispatcherServlet` tương ứng |
| Kiểm tra payload XML | `PayloadValidatingInterceptor` và XSD |
| Quy định SOAP Fault nghiệp vụ | Exception resolver và fault contract |
| Xác thực WS-Security | Security interceptor/policy và chứng chỉ |
| Kết nối SOAP đối tác | `WebServiceTemplate` và transport/security config |

**Quy tắc:** dùng property để điều chỉnh thành phần mà Boot **đang quản lý**; dùng bean để bổ sung hành vi hoặc thay thế khi có chủ đích. Với thành phần do ứng dụng đăng ký, không kỳ vọng mọi property liên quan của Boot sẽ tự được áp dụng.

### 11.1. Ví dụ lỗi do nhầm phạm vi property

Giả sử:

~~~properties
spring.webservices.path=/services
~~~

nhưng ứng dụng vẫn tự đăng ký:

~~~java
return new ServletRegistrationBean<>(servlet, "/ws/*");
~~~

Nếu registration thủ công là registration đang hoạt động, request SOAP đi tới **`/ws/*`** theo mapping của nó, không thể suy rằng `spring.webservices.path=/services` đã sửa mapping đó. Đây là lý do cần xác nhận servlet được đăng ký thực tế, thay vì chỉ nhìn `application.properties`.

## 12. Khi auto-configuration và bean do ứng dụng khai báo mâu thuẫn

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Khởi động báo duplicate bean definition | Cùng tên bean do hai configuration khai báo | Kiểm tra tên bean, cấu hình import, tránh override mù quáng |
| Servlet mapping `/ws/*` bị xung đột | Boot và ứng dụng cùng đăng ký servlet hoặc trùng với servlet khác | Điều kiện auto-config, registration bean, servlet mappings |
| WSDL tải được nhưng POST 404/405 | `soap:address` không khớp URL nhận request | URL WSDL, `setLocationUri`, servlet mapping, gateway |
| `No endpoint mapping found` | Sai QName của payload, scan không thấy `@Endpoint` | Namespace, local name, component scan và `@EnableWs` |
| Có hai `XsdSchema` và inject thất bại | Spring không chọn được schema | `@Qualifier` hoặc tên bean rõ ràng |
| SOAP 1.2 client bị từ chối | Factory SOAP 1.1, binding WSDL hoặc Content-Type không khớp | Envelope namespace, SOAP factory, WSDL binding |
| `SOAPAction` khác mong đợi | Client callback/action mapping sai | WSDL action và header HTTP thực tế |
| Validator không chạy | Chưa đăng ký interceptor hoặc mapping không đi qua chain | `WsConfigurer`, cấu hình endpoint interceptor |
| Endpoint ném exception trả Fault không đúng | Chưa cấu hình resolver/fault detail | Resolver chain, SOAP version, XSD/WSDL fault |
| WSDL có địa chỉ HTTP nội bộ | Reverse proxy / location transform sai | Public URL, forwarded headers tin cậy, WSDL response |
| Client JAXB không marshal được | JAXB context package sai, thiếu runtime, root cần wrapper | Class sinh, `ObjectFactory`, marshaller |
| TLS hoặc WS-Security thất bại | Cấu hình security độc lập với servlet/endpoint | Truststore, keystore, policy, security interceptors |

### 12.1. Đọc condition evaluation report

Trong môi trường phát triển, có thể chạy ứng dụng Boot với chế độ debug để xem báo cáo các auto-configuration condition:

~~~bash
java -jar app.jar --debug
~~~

Tên `app.jar` là minh họa. Báo cáo thường giúp xác định cấu hình nào đã match và cấu hình nào không match, kèm lý do. Chỉ dựa vào việc thấy một `@Bean` trong source chưa đủ chắc Boot đã bỏ qua một nhánh auto-configuration.

Nếu dự án có Spring Boot Actuator, có thể dùng thông tin **conditions/beans** theo cấu hình và quyền truy cập nội bộ để chẩn đoán. Không tự mở những endpoint chẩn đoán này ra Internet công khai; chúng có thể bộc lộ thông tin cấu hình ứng dụng.

### 12.2. Đọc log Spring-WS phù hợp

Trong môi trường thử nghiệm, tăng log cho những phần liên quan đến Servlet/mapping và Spring-WS có thể giúp xác định root QName, SOAP action và đường đi request. Tuy nhiên không bật log SOAP Body/Header đầy đủ trong production nếu chưa có masking, giới hạn kích thước và chính sách lưu trữ.

Thứ tự kiểm tra thực tế:

1. Có đúng một SOAP servlet phục vụ URL yêu cầu hay không?
2. WSDL bean có được nhìn thấy qua đường dẫn `<bean-name>.wsdl` không?
3. URL `soap:address` có thực sự đến đúng servlet không?
4. QName root SOAP Body có khớp `@PayloadRoot` không?
5. Interceptor/schema/message factory có cùng SOAP version và namespace không?
6. Response/Fault có đúng với WSDL và HTTP binding không?

## 13. Kiểm thử bằng HTTP và XML

Đối với ví dụ OrderService khi chạy local, GET WSDL:

~~~bash
curl -i http://localhost:8080/ws/orders.wsdl
~~~

Request SOAP 1.1 gửi tới `/ws/orders` (giả sử servlet mapping, WSDL address và SOAP version đã được xác minh):

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

Vì ví dụ `DefaultWsdl11Definition` chưa khai báo action cụ thể, header rỗng được dùng để minh họa SOAP 1.1. Nếu WSDL runtime công bố một `soapAction` khác, client phải theo hợp đồng đã công bố. HTTP response thành công thường có SOAP Body:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
    <soap:Body>
        <o:GetOrderResponse>
            <o:status>FOUND</o:status>
        </o:GetOrderResponse>
    </soap:Body>
</soap:Envelope>
~~~

Đây là **XML minh họa về cấu trúc**; không đòi serializer giữ nguyên prefix hoặc whitespace. Khi dùng `PayloadValidatingInterceptor`, hãy gửi thêm request sai schema, ví dụ bỏ `orderId`, để kiểm tra validator thực sự tham gia chain.

### 13.1. Ma trận kiểm thử cấu hình

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Chỉ dùng Boot-managed SOAP servlet | Có một servlet mapping phù hợp property |
| Chỉ dùng explicit registration | Có một servlet mapping thủ công, không còn mapping xung đột |
| GET `/ws/orders.wsdl` | WSDL có request/response elements, binding và address đúng |
| POST SOAP 1.1 đúng QName | `@Endpoint` được gọi và có SOAP response |
| POST sai namespace | Không ánh xạ nhầm vào endpoint hợp lệ |
| POST thiếu `orderId` khi bật XSD validation | Validator phát hiện vi phạm XSD |
| Thêm XSD thứ hai | WSDL tương ứng lấy đúng schema nhờ qualifier |
| Khởi tạo client JAXB | Marshal/unmarshal đúng schema và root element |
| Dùng SOAP 1.2 vào cấu hình chỉ hỗ trợ SOAP 1.1 | Lỗi tương thích được xác định rõ |
| Bật custom factory | Runtime dùng factory dự kiến, không tạo bean trùng ngoài ý muốn |
| Bật Fault resolver | Exception nghiệp vụ thành Fault đúng code/detail đã định nghĩa |
| Public WSDL qua HTTPS gateway | `soap:address` chỉ URL public đúng với endpoint |
| WS-Security ký/xác thực | Security interceptor được gọi đúng thứ tự và policy |

`MockWebServiceClient` hữu ích để kiểm thử endpoint, payload và interceptor trong Spring context; `MockWebServiceServer` hỗ trợ kiểm thử client. Để kiểm tra **Servlet mapping, HTTP status, TLS, proxy và địa chỉ WSDL công khai**, cần bài thử tích hợp qua HTTP(S) thực hoặc môi trường mô phỏng transport phù hợp.

**Không cần test mọi implementation detail.** Tập trung vào hành vi người dùng và đối tác quan sát được: WSDL đúng, URL đúng, SOAP message đúng, lỗi được phân loại đúng, các cấu hình do ứng dụng khai báo không làm hỏng thành phần tự động.

## 14. Chiến lược mở rộng cho môi trường doanh nghiệp

Sau khi cấu hình SOAP server cơ bản hoạt động, cần mở rộng đồng bộ thay vì thêm bean rời rạc:

### 14.1. XSD/WSDL và JAXB

Thiết kế XSD theo nghiệp vụ, chốt namespace, đặt rõ `minOccurs`/`nillable` và kiểu dữ liệu. Sinh JAXB bằng công cụ tương thích thế hệ Java/Jakarta đang dùng. Kiểm tra WSDL sau khi được Boot/Spring-WS công bố; việc dùng `DefaultWsdl11Definition` không thay thế kiểm thử hợp đồng.

### 14.2. XSD validation và SOAP Fault

Đăng ký validator ở interceptor chain và xác định phạm vi kiểm tra request/response. Với lỗi nghiệp vụ, tạo Fault theo SOAP version và cấu trúc detail quy định trong hợp đồng. Tránh lộ stack trace, credentials và dữ liệu người dùng trong Fault trả cho đối tác.

### 14.3. XML parser, WS-Security và chứng chỉ

Khi ứng dụng tự parse XML hoặc dùng các parser/transformer mức thấp, cần kiểm soát external entities, schema import và tài nguyên bên ngoài. Với WS-Security, thứ tự interceptor và chính sách xác minh chữ ký, timestamp, token phải rõ ràng. HTTPS/TLS bảo vệ kết nối; WS-Security có yêu cầu bảo vệ thông điệp khác. Boot không tự sinh truststore, keystore và policy phù hợp từng đối tác.

### 14.4. Quan sát vận hành

Ghi correlation ID, tên operation, URL host/path, SOAP version, mã HTTP và fault code khi cần. Không mặc định log toàn bộ SOAP Header/Body. Với request có tác dụng phụ, như tạo hóa đơn hoặc chuyển tiền, timeout không chứng minh server chưa xử lý; retry phải dựa trên idempotency hoặc trạng thái giao dịch.

### 14.5. Nhiều môi trường triển khai

Local có thể dùng `http://localhost:8080/ws/orders`, staging dùng hostname nội bộ và production dùng HTTPS qua gateway. **Không hard-code production URL trong Java endpoint**, nhưng phải bảo đảm WSDL public đưa ra đúng endpoint mà client thực sự gọi. Client đã sinh từ WSDL cũ có thể giữ URL cũ; kiểm tra và version hóa hợp đồng khi triển khai.

## 15. Bài tập phân tích cấu hình

Một dự án có:

~~~properties
spring.webservices.path=/soap
~~~

và đồng thời khai báo:

~~~java
@Bean
ServletRegistrationBean<MessageDispatcherServlet> customSoapServlet(
        ApplicationContext context) {
    MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();
    servlet.setApplicationContext(context);
    return new ServletRegistrationBean<>(servlet, "/ws/*");
}
~~~

Trong cùng ứng dụng còn có `@Bean(name="orders")` kiểu `DefaultWsdl11Definition` với `setLocationUri("/ws/orders")` và một `@Endpoint` nhận `GetOrderRequest`. Hãy trả lời:

1. Có thể kết luận chắc `/soap/orders` và `/ws/orders` đều phục vụ SOAP không?
2. Có cần xem condition report trước khi quyết định sửa property hay không?
3. `@Primary` đặt trên servlet bean có bảo đảm không còn mapping trùng không?
4. Nếu WSDL công bố `/ws/orders` nhưng client POST tới `/soap/orders`, đâu là điểm cần đối chiếu?
5. Chỉ thêm `XsdSchema` có tự bật XSD validation không?

**Đáp án gợi ý:**

1. **Không.** Phải kiểm tra servlet registration nào thực sự tồn tại và URL mapping có hiệu lực. Property Boot không nhất thiết điều khiển registration thủ công.
2. **Có.** Condition report giúp hiểu auto-configuration nào match, back off hoặc bị loại trừ.
3. **Không.** `@Primary` ảnh hưởng dependency injection, không giải quyết Servlet mapping trùng.
4. Đối chiếu `soap:address`, URL POST thật, Servlet container mapping và gateway route; giữ chúng nhất quán.
5. **Không.** Cần đăng ký interceptor/validation mechanism tương ứng, sau đó kiểm thử XML sai schema.

### 15.1. Thực hành lựa chọn

Thử hai nhánh trên **hai cấu hình chạy tách biệt**:

- **Nhánh A:** Boot-managed Servlet, điều chỉnh `spring.webservices.path` và cung cấp các bean XSD/WSDL/endpoint.
- **Nhánh B:** Explicit `ServletRegistrationBean`, bật tùy chỉnh WSDL location và xác nhận Boot không đăng ký Servlet mapping cạnh tranh.

Trong mỗi nhánh, ghi lại URL GET WSDL, URL POST SOAP, root QName, HTTP Content-Type, SOAP version và response thực tế. Kết quả mong đợi là **cùng một hợp đồng SOAP hoạt động nhất quán**, còn khác biệt chỉ ở cách cấu hình/đăng ký hạ tầng.

## 16. Ghi nhớ

- **Spring Boot tự động cấu hình theo điều kiện.** Bean ứng dụng có thể khiến cấu hình mặc định back off, nhưng cần xác minh điều kiện ở đúng phiên bản; không có quy tắc “bean tự khai báo luôn thắng”.
- **Ứng dụng vẫn quản lý hợp đồng XSD/WSDL và endpoint**. Starter Spring-WS không tự sinh toàn bộ operation, JAXB và Fault nghiệp vụ.
- **Chọn một chiến lược đăng ký `MessageDispatcherServlet`** cho URL mong muốn: Boot-managed hoặc explicit. Cẩn trọng với duplicate servlet mapping.
- **Property chỉ điều khiển thành phần được thiết kế để đọc property đó**; ví dụ `spring.webservices.path` có thể không chi phối registration thủ công.
- **Tên bean `Wsdl11Definition`, `@Qualifier` và namespace quan trọng**. Đừng dùng `@Primary` để xử lý nhầm lỗi URL/servlet.
- **`@EnableWs`, `@Endpoint`, `@PayloadRoot`, message factory và interceptor** là các phần của chuỗi xử lý SOAP, có trách nhiệm khác nhau và cần được cấu hình nhất quán.
- **SOAP 1.1/1.2, XML validation, SOAP Fault, WS-Security và TLS** không tự đồng bộ chỉ nhờ một bean; phải kiểm tra WSDL, message trên dây và policy thực tế.
- **Kiểm thử ngoài HTTP(S)** để xác minh URL WSDL, URL SOAP endpoint, reverse proxy, chứng chỉ, lỗi và khả năng tương thích với client đối tác.
