# Khởi tạo bằng Spring Boot hoặc cấu hình Spring độc lập

## 1. Bài toán khởi tạo một dịch vụ Spring Web Services

**Spring Web Services (Spring-WS)** là framework xây dựng và sử dụng dịch vụ **SOAP** trên nền Spring. Trong cách phát triển **contract-first**, ta thiết kế **XSD/WSDL** trước, rồi tạo Java endpoint, JAXB mapping, SOAP client và các thành phần kiểm soát lỗi/bảo mật. Bước khởi tạo dự án cần chuẩn bị đủ phần chạy ứng dụng lẫn phần xuất bản hợp đồng, để một hệ thống khác có thể đọc WSDL và gửi SOAP XML đúng quy cách.

Có hai hướng khởi tạo thường gặp:

1. **Spring Boot:** đóng gói ứng dụng cùng máy chủ nhúng, dùng dependency management và auto-configuration của Boot, có thể chạy như một tiến trình độc lập.
2. **Spring độc lập (không dùng Boot):** tự cấu hình Spring context, `MessageDispatcherServlet` và cách triển khai lên Servlet container, thường là một WAR.

Cả hai **đều dùng Spring-WS** để xử lý thông điệp SOAP. Chúng khác nhau chủ yếu ở cách bootstrap, quản lý dependency, đăng ký servlet và vận hành. Không phải Spring Boot mới hỗ trợ contract-first, cũng không phải dùng Spring thuần thì phải xây dựng SOAP bằng tay.

### Kết quả cần đạt sau bài

Sau khi học và thực hành, bạn có thể:

- Chọn được Boot hoặc cấu hình Spring độc lập theo yêu cầu triển khai.
- Tạo một XSD chung và công bố WSDL thông qua `DefaultWsdl11Definition`.
- Đăng ký `MessageDispatcherServlet` để nhận SOAP request.
- Viết `@Endpoint` và hiểu cách ánh xạ `@PayloadRoot` tới phần tử gốc của SOAP Body.
- Kiểm tra URL WSDL, địa chỉ SOAP thực tế và XML phản hồi.
- Biết cách bổ sung JAXB, XSD validation, SOAP Fault và WS-Security mà không phải thay đổi nền tảng khởi tạo.

Ví dụ xuyên suốt là dịch vụ **OrderService** với operation `GetOrder`, nhận `orderId` và trả trạng thái `FOUND`. Đây là ví dụ tối thiểu để kiểm chứng cấu hình, chưa có database hay xử lý nghiệp vụ thực.

## 2. So sánh Spring Boot và Spring độc lập

| Tiêu chí | Spring Boot | Spring không dùng Boot |
| --- | --- | --- |
| Cách chạy điển hình | Executable JAR với Servlet container nhúng | WAR trên Servlet container được quản lý riêng |
| Khởi tạo context | `@SpringBootApplication` và Boot startup | `WebApplicationInitializer` hoặc `web.xml` và Spring context |
| Đăng ký SOAP servlet | Boot có thể auto-configure; có thể đăng ký rõ để kiểm soát mapping | Phải đăng ký `MessageDispatcherServlet` |
| Quản lý phiên bản dependency | Boot BOM/starter cung cấp bộ tương thích | Tự quản lý BOM và phiên bản Spring/WS |
| URL WSDL và SOAP | Quy định qua servlet mapping + WSDL bean | Quy định qua servlet mapping + WSDL bean |
| Endpoint SOAP | `@Endpoint`, `@PayloadRoot` | Vẫn dùng `@Endpoint`, `@PayloadRoot` |
| XSD/JAXB/WS-Security | Dùng chung công nghệ Spring-WS/JAXB | Dùng chung công nghệ Spring-WS/JAXB |
| Triển khai và cấu hình | Dễ tích hợp property, health, metrics của Boot | Linh hoạt theo nền tảng ứng dụng hiện có |
| Phù hợp | Dịch vụ mới, triển khai container/cloud, đội muốn ít cấu hình bootstrap | Tích hợp vào hệ thống Spring truyền thống hoặc yêu cầu WAR/external Servlet container |

**Chọn Spring Boot** khi bắt đầu một dịch vụ SOAP mới và không bị ràng buộc bởi hạ tầng triển khai cũ. **Chọn Spring độc lập** khi phải nhúng vào web application Spring truyền thống, triển khai trên application server có sẵn hoặc cần kiểm soát trực tiếp vòng đời Servlet context. Đây là lựa chọn về vận hành và kiến trúc, không phải thước đo chất lượng hợp đồng SOAP.

### 2.1. Chọn bộ phiên bản tương thích

Spring Boot, Spring Framework, Spring-WS, Servlet API và JAXB có các thế hệ phụ thuộc nhau. Trước khi khởi tạo, hãy chọn một **bộ phiên bản được hỗ trợ cùng nhau** theo tài liệu của phiên bản dự án:

| Thành phần | Điều cần kiểm tra |
| --- | --- |
| Java | JDK tương thích phiên bản Spring Boot/Spring Framework đã chọn |
| Spring-WS | Phiên bản tương thích Spring Framework của ứng dụng |
| Servlet API | Servlet container triển khai hỗ trợ namespace API cần dùng |
| JAXB | Các bản dùng `javax.xml.bind.*` và `jakarta.xml.bind.*` thuộc các thế hệ khác nhau |
| Plugin sinh code XSD | Sinh source JAXB phù hợp runtime và namespace API |
| Maven/Gradle | Phiên bản build tool và plugin tương thích JDK |

Các ví dụ Java dưới đây dùng **họ Jakarta Servlet API** (`jakarta.servlet.*`), phù hợp dự án Spring Framework 6/Spring-WS 4 và các phiên bản Boot tương ứng. Nếu đang duy trì ứng dụng cũ dùng `javax.servlet.*` và `javax.xml.bind.*`, không trộn trực tiếp import của hai thế hệ. Bài không khóa vào một số phiên bản cụ thể để tránh trình bày phiên bản không tương thích trong một project có BOM khác.

## 3. Thiết kế XSD chung trước khi viết cấu hình

Một dịch vụ contract-first nên có XSD cụ thể trước khi mở endpoint. Tạo file:

`src/main/resources/xsd/orders.xsd`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
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

Từ XSD này:

- Global request element là `{urn:example:orders:v1}GetOrderRequest`.
- Global response element là `{urn:example:orders:v1}GetOrderResponse`.
- Hai phần tử con `orderId` và `status` thuộc cùng namespace vì `elementFormDefault="qualified"`.
- XSD quy định hình dạng payload; không tự quy định URL endpoint, HTTP action hay logic tìm đơn hàng.

Tên hậu tố `Request` và `Response` được chọn có chủ đích. Khi dùng `DefaultWsdl11Definition` với các quy ước mặc định, Spring-WS có thể suy ra operation `GetOrder` từ các cặp phần tử này. Các tên thực tế sinh ra phải được kiểm tra bằng cách đọc WSDL xuất bản.

## 4. Khởi tạo bằng Spring Boot

### 4.1. Tạo project và chọn dependency

Có thể dùng **Spring Initializr** để tạo một project Java/Maven hoặc Gradle, chọn dependency **Web Services**. Nếu dùng Maven, phần dependencies liên quan có thể được quản lý như sau (giả định POM đã dùng Spring Boot parent hoặc BOM phù hợp):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web-services</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-web-services` đưa các thành phần Spring-WS vào ứng dụng cùng hạ tầng Spring cần thiết. `spring-boot-starter-test` hỗ trợ kiểm thử thông dụng; nếu cần mock SOAP chuyên biệt thì còn phải kiểm tra các thư viện test của Spring-WS và cách phối hợp trong bộ dependency thực tế.

Không nên tự gán phiên bản riêng cho mọi dependency Spring-WS khi đã sử dụng BOM của Boot, trừ khi có nhu cầu và đã xác minh tính tương thích. Nếu cần JAXB code generation, thêm plugin sinh mã từ XSD riêng; chỉ khai báo starter **không tự sinh các lớp Java từ XSD**.

Một cấu trúc thư mục minh họa:

~~~text
order-soap-service/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── example/orders/ws/
    │   │       ├── OrderSoapApplication.java
    │   │       ├── SoapServletConfig.java
    │   │       ├── WsContractConfig.java
    │   │       └── OrderEndpoint.java
    │   └── resources/
    │       ├── application.properties
    │       └── xsd/orders.xsd
    └── test/
        └── java/...
~~~

### 4.2. Điểm vào của Spring Boot

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

`@SpringBootApplication` kích hoạt cấu hình Boot và quét component trong package hiện tại cùng các package con. Ở ví dụ này, các lớp cấu hình và `@Endpoint` được đặt trong `example.orders.ws` để Spring tìm thấy.

### 4.3. Đăng ký `MessageDispatcherServlet`

`MessageDispatcherServlet` là thành phần nhận HTTP request và chuyển SOAP message tới Spring-WS message dispatcher. Ví dụ dưới đây đăng ký servlet một cách **tường minh** để có đường dẫn ổn định:

~~~java
package example.orders.ws;

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

Ý nghĩa:

| Dòng cấu hình | Tác dụng |
| --- | --- |
| `new MessageDispatcherServlet()` | Tạo servlet để xử lý SOAP request và xuất bản WSDL |
| `setApplicationContext(context)` | Cho servlet sử dụng Spring context chứa endpoint/WSDL bean |
| `setTransformWsdlLocations(true)` | Cho phép điều chỉnh địa chỉ WSDL công bố dựa trên request |
| `new ServletRegistrationBean<>(..., "/ws/*")` | Ánh xạ các URL bắt đầu bằng `/ws/` tới servlet |

Một số cấu hình Boot có thể tự đăng ký `MessageDispatcherServlet` từ auto-configuration. **Chỉ dùng một chiến lược đăng ký servlet nhất quán**: nếu dự án đã có servlet mapping do Boot tạo và phù hợp yêu cầu, không cần thêm một servlet thứ hai tranh chấp cùng URL; nếu cần kiểm soát rõ, dùng bean tùy chỉnh và kiểm tra mapping khởi tạo thực tế.

`setTransformWsdlLocations(true)` là cơ chế hỗ trợ cập nhật địa chỉ công bố, **không tự tạo route HTTP trên gateway**. Sau reverse proxy, phải kiểm tra domain, scheme HTTPS, forwarded headers và context path của WSDL thực tế.

## 5. Cấu hình WSDL/XSD dùng chung cho cả hai cách khởi tạo

Tạo lớp `WsContractConfig`:

~~~java
package example.orders.ws;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@EnableWs
@Configuration
@ComponentScan(basePackages = "example.orders.ws")
public class WsContractConfig {

    private static final String NAMESPACE =
            "urn:example:orders:v1";

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders.xsd")
        );
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition definition =
                new DefaultWsdl11Definition();

        definition.setPortTypeName("OrdersPort");
        definition.setServiceName("OrderService");
        definition.setTargetNamespace(NAMESPACE);
        definition.setLocationUri("/ws/orders");
        definition.setSchema(ordersSchema);
        definition.setCreateSoap11Binding(true);
        definition.setCreateSoap12Binding(false);

        return definition;
    }
}
~~~

Trong cấu hình này:

1. `@EnableWs` kích hoạt các cấu hình cần thiết cho endpoint Spring-WS được khai báo bằng annotation.
2. `@ComponentScan` bảo đảm endpoint có thể được phát hiện ngay cả khi cấu hình được dùng trong ứng dụng Spring độc lập. Với Boot, việc quét có thể đã được thực hiện bởi `@SpringBootApplication`.
3. `SimpleXsdSchema` nạp `xsd/orders.xsd` từ classpath. Nếu đường dẫn sai hoặc file không được đóng gói, ứng dụng/WSDL bean có thể khởi tạo lỗi.
4. Bean tên **`orders`** cung cấp WSDL sinh từ XSD. Với servlet map `/ws/*`, URL WSDL điển hình là **`/ws/orders.wsdl`** (có thể thêm host, port và context path).
5. `setLocationUri("/ws/orders")` đặt địa chỉ SOAP endpoint được mô tả trong WSDL; cần nhất quán với servlet mapping.
6. `setCreateSoap11Binding(true)` và `setCreateSoap12Binding(false)` chọn công bố binding SOAP 1.1 trong ví dụ. Nếu bật SOAP 1.2, phải cấu hình message factory và kiểm thử phiên bản thực sự được endpoint chấp nhận.

`DefaultWsdl11Definition` không sinh Java DTO, không tự chạy nghiệp vụ và không tự triển khai SOAP endpoint. Nó tạo **mô tả WSDL 1.1** từ những thiết lập và XSD tương ứng. Đối với WSDL đòi hỏi cấu trúc đặc biệt, nhiều operation/fault/phần tử hoặc chính sách phức tạp, có thể quản lý **WSDL tĩnh** để kiểm soát hợp đồng chính xác hơn.

### 5.1. WSDL động khác WSDL tĩnh

| Cách công bố | Ưu điểm | Cần lưu ý |
| --- | --- | --- |
| `DefaultWsdl11Definition` từ XSD | Nhanh, ít phải viết WSDL thủ công | Phụ thuộc quy ước sinh operation; phải kiểm tra WSDL đầu ra |
| WSDL tĩnh được quản lý cùng source | Kiểm soát hoàn toàn các phần `binding`, `message`, `fault`, policy | Phải quản lý đồng bộ URL và các XSD import |

Trong quy trình contract-first, **WSDL đã công bố cho đối tác là hợp đồng thực tế**. Dù sinh động hay tĩnh, thay đổi có thể ảnh hưởng client đã sinh mã. Nên có kiểm thử hoặc bản lưu so sánh WSDL/XSD khi phát hành phiên bản mới.

## 6. Tạo một `@Endpoint` tối thiểu

Để chạy thử trước khi cấu hình JAXB code generation, có thể nhận payload dưới dạng DOM `Element` và trả `Source`. Cách này giúp tập trung vào việc servlet đã nhận đúng SOAP request và `@PayloadRoot` đã ánh xạ tới endpoint chưa.

~~~java
package example.orders.ws;

import javax.xml.transform.Source;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.xml.transform.StringSource;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

@Endpoint
public class OrderEndpoint {

    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public Source getOrder(@RequestPayload Element request) {
        NodeList orderIds = request.getElementsByTagNameNS(
                NS, "orderId");

        if (orderIds.getLength() != 1
                || orderIds.item(0).getTextContent().isBlank()) {
            throw new IllegalArgumentException(
                    "Expected one nonempty orderId");
        }

        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>FOUND</o:status>" +
                "</o:GetOrderResponse>"
        );
    }
}
~~~

Ở Java 11+, `String.isBlank()` dùng để kiểm tra chuỗi toàn khoảng trắng. Những import `javax.xml.transform` và `org.w3c.dom` vẫn thuộc các API XML chuẩn của Java; chúng **không phải** lỗi trộn `javax.servlet` với `jakarta.servlet`.

**Ví dụ này chỉ là smoke test cho hạ tầng Spring-WS**:

- `@Endpoint` khai báo một handler SOAP.
- `@PayloadRoot` ánh xạ root QName `{urn:example:orders:v1}GetOrderRequest`.
- `@RequestPayload Element` nhận phần tử gốc của SOAP Body.
- `@ResponsePayload Source` trả phần tử XML response cho Spring-WS tạo SOAP Body.
- Phương thức có đọc `orderId` để minh họa kiểm tra đầu vào, nhưng luôn trả `FOUND`. Không có truy vấn database hay kiểm tra đơn hàng thật.

Với dịch vụ sản xuất, nên sử dụng DTO JAXB sinh từ XSD, xác thực toàn bộ payload theo XSD và chuyển ngoại lệ nghiệp vụ thành SOAP Fault đã được thiết kế trong hợp đồng. Tránh thao tác chuỗi XML thủ công khi đưa dữ liệu người dùng vào response: nếu nội suy đầu vào không escape đúng cách có thể tạo XML sai hoặc gây lỗi an toàn dữ liệu.

### 6.1. Vì sao có thể chưa thấy SOAP Fault thân thiện?

Một ngoại lệ Java `IllegalArgumentException` trong ví dụ không tự được mô tả thành typed SOAP Fault theo WSDL. Khi xây dựng hợp đồng đầy đủ, cần dùng cơ chế xử lý ngoại lệ của Spring-WS, chẳng hạn `SoapFaultMappingExceptionResolver` hoặc `SoapFaultAnnotationExceptionResolver`, và định nghĩa `detail` có cấu trúc phù hợp. Cấu hình ở đây chỉ chứng minh ứng dụng đã nhận và trả SOAP thành công với request hợp lệ.

## 7. Chạy và kiểm tra ứng dụng Spring Boot

Một cấu hình khởi đầu:

~~~properties
# src/main/resources/application.properties
server.port=8080
~~~

Với Maven đã được cấu hình Spring Boot plugin phù hợp, có thể chạy:

~~~bash
mvn spring-boot:run
~~~

Hoặc sau khi package ra executable JAR:

~~~bash
java -jar target/order-soap-service.jar
~~~

Tên JAR phụ thuộc `artifactId`, `version` và cấu hình Maven. Hai lệnh trên là hướng dẫn thực hành, không phải các lệnh đã được chạy trong bước tạo tài liệu này.

### 7.1. Kiểm tra WSDL

Trong môi trường local không có context path, thử truy cập:

~~~text
http://localhost:8080/ws/orders.wsdl
~~~

WSDL nên chứa `wsdl:service`, `wsdl:port`, `wsdl:binding`, `wsdl:portType` và các phần tử XSD tương ứng. Kiểm tra `soap:address/@location`: đây phải là địa chỉ gửi SOAP request phù hợp với môi trường đang chạy.

Nếu dùng một REST client hoặc terminal, có thể gửi HTTP GET:

~~~bash
curl -i http://localhost:8080/ws/orders.wsdl
~~~

Ở Windows PowerShell có alias `curl` tùy môi trường; khi cần dùng chương trình cURL chuẩn, có thể gọi `curl.exe`.

### 7.2. Gửi SOAP 1.1 request

Nội dung bản tin:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

Nếu lưu bản tin trong file `request.xml`, gửi:

~~~bash
curl -i -X POST http://localhost:8080/ws/orders \
  -H 'Content-Type: text/xml; charset=utf-8' \
  -H 'SOAPAction: ""' \
  --data-binary @request.xml
~~~

Ví dụ cấu hình WSDL ở mục 5 **chưa đặt SOAPAction riêng**; header `SOAPAction: ""` được dùng cho request SOAP 1.1 minh họa. Nếu hợp đồng công bố một action cụ thể, client phải gửi đúng action đó hoặc theo yêu cầu binding/đối tác.

Phản hồi SOAP 1.1 mong đợi có dạng:

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

Prefix thực tế và cách định dạng XML có thể khác, vì SOAP serializer có quyền chọn prefix. Hãy đối chiếu bằng **namespace URI + local name**, không yêu cầu response phải có đúng chữ `soap` hoặc `o`.

### 7.3. Cách kiểm tra một ứng dụng đã khởi tạo đúng

Tối thiểu, xác nhận:

1. Ứng dụng khởi động không lỗi Spring bean hoặc Servlet mapping.
2. GET WSDL trả tài liệu hợp lệ; các QName request/response trỏ tới đúng XSD.
3. `soap:address` trong WSDL trỏ tới URL ứng dụng thực sự tiếp nhận POST.
4. POST SOAP request hợp lệ trả SOAP Envelope có `GetOrderResponse`.
5. Root QName và namespace khác hợp đồng không bị ứng dụng nhầm thành operation `GetOrder`.

Nếu chưa đạt các điều này, việc bổ sung security hoặc JAXB có thể che mất lỗi khởi tạo nền tảng; nên xác minh hợp đồng và routing trước.

## 8. Khởi tạo bằng Spring độc lập, không dùng Spring Boot

Spring-WS có thể chạy trong một ứng dụng web Spring thông thường. Ví dụ ở đây dùng **Java configuration + `WebApplicationInitializer`** trên **Servlet container tương thích Jakarta**. Không cần `@SpringBootApplication`, executable JAR hay Spring Boot starter.

### 8.1. Dependencies cần thiết

Đối với Maven, ứng dụng cần có:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-web</artifactId>
    </dependency>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <scope>provided</scope>
    </dependency>
</dependencies>
~~~

Đây là **phần dependency minh họa**, không phải POM độc lập có thể build ngay: một dự án không dùng Boot cần khai báo phiên bản tương thích thông qua `dependencyManagement`/BOM và cấu hình packaging `war`, compiler, WAR plugin theo container mục tiêu. `jakarta.servlet-api` được đánh dấu `provided` khi Servlet container bên ngoài sẽ cung cấp API đó.

Một số thư viện cần thiết được kéo vào qua dependency transitively; trường hợp muốn cố định phiên bản, dùng BOM tương thích thay vì chọn ngẫu nhiên từng version. Với ứng dụng truyền thống dựa trên `javax.servlet.*`, phải dùng cả hệ phiên bản tương thích với Java EE/Servlet container tương ứng, không thay trực tiếp bằng đoạn Jakarta phía trên.

### 8.2. Cấu trúc WAR

Một layout minh họa:

~~~text
order-soap-war/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/orders/ws/
        │       ├── WsInitializer.java
        │       ├── WsContractConfig.java
        │       └── OrderEndpoint.java
        ├── resources/
        │   └── xsd/orders.xsd
        └── webapp/
            └── WEB-INF/
~~~

Tái sử dụng **chính `WsContractConfig`, `OrderEndpoint` và `orders.xsd`** từ các mục 3, 5 và 6. Vì các lớp đó chỉ phụ thuộc Spring-WS/Spring Framework (không phụ thuộc `SpringApplication`), chúng có thể chạy trong Spring độc lập.

### 8.3. Đăng ký servlet bằng `WebApplicationInitializer`

~~~java
package example.orders.ws;

import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRegistration;
import org.springframework.web.WebApplicationInitializer;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

public class WsInitializer implements WebApplicationInitializer {

    @Override
    public void onStartup(ServletContext servletContext)
            throws ServletException {

        AnnotationConfigWebApplicationContext context =
                new AnnotationConfigWebApplicationContext();
        context.register(WsContractConfig.class);

        MessageDispatcherServlet servlet =
                new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);

        ServletRegistration.Dynamic registration =
                servletContext.addServlet("spring-ws", servlet);
        registration.setLoadOnStartup(1);
        registration.addMapping("/ws/*");
    }
}
~~~

Ý tưởng chính:

- Servlet container phát hiện `WebApplicationInitializer` thông qua hạ tầng khởi tạo của Spring Web.
- `AnnotationConfigWebApplicationContext` tải `WsContractConfig`, từ đó nhận `@EnableWs`, WSDL/XSD beans và endpoint scan.
- `MessageDispatcherServlet` phục vụ request trên `/ws/*`, tương tự cách Boot đăng ký servlet ở mục 4.
- Không cần Boot auto-configuration; vòng đời web application do Servlet container và Spring Web context quản lý.

Với WAR tên `order-soap-war.war`, context path trong container có thể là `/order-soap-war`. Khi đó URL WSDL thường tương đương:

~~~text
http://localhost:8080/order-soap-war/ws/orders.wsdl
~~~

SOAP endpoint tương ứng:

~~~text
http://localhost:8080/order-soap-war/ws/orders
~~~

**Context path phụ thuộc tên WAR và cấu hình triển khai thực tế.** Không mặc định rằng WAR luôn chạy ở root `/`; cũng không suy ra URL endpoint từ tên WSDL nếu servlet mapping/locationUri đã thay đổi.

### 8.4. Phương án Spring XML truyền thống

Một hệ thống cũ có thể đăng ký `MessageDispatcherServlet` trong `web.xml` và dùng file context XML thay cho Java configuration. Chẳng hạn, đoạn cấu hình servlet trong `web.xml`:

~~~xml
<servlet>
    <servlet-name>spring-ws</servlet-name>
    <servlet-class>
        org.springframework.ws.transport.http.MessageDispatcherServlet
    </servlet-class>
    <init-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>/WEB-INF/spring-ws.xml</param-value>
    </init-param>
    <load-on-startup>1</load-on-startup>
</servlet>

<servlet-mapping>
    <servlet-name>spring-ws</servlet-name>
    <url-pattern>/ws/*</url-pattern>
</servlet-mapping>
~~~

Đây là **đoạn trích bên trong `web-app`**, không phải file `web.xml` hoàn chỉnh. `spring-ws.xml` cần khai báo các bean Spring-WS tương đương `@EnableWs`, schema, WSDL definition và endpoint. Có thể dùng cấu hình namespace XML Spring-WS phù hợp phiên bản đang triển khai.

Không nên cùng lúc khai báo servlet ở `web.xml` **và** dùng `WebApplicationInitializer` để tạo một servlet khác trên cùng `/ws/*`; Servlet container có thể báo mapping trùng hoặc cho kết quả khó dự đoán. Trong một WAR, hãy chọn một cách bootstrap và kiểm tra mapping cuối cùng.

## 9. So sánh luồng khởi động của hai phương án

~~~mermaid
flowchart TB
    subgraph BOOT["Spring Boot"]
        BA["@SpringBootApplication"]
        BB["Boot ApplicationContext"]
        BC["ServletRegistrationBean"]
        BA --> BB --> BC
    end
    subgraph STANDALONE["Spring độc lập"]
        SA["Servlet container triển khai WAR"]
        SB["WebApplicationInitializer"]
        SC["AnnotationConfigWebApplicationContext"]
        SA --> SB --> SC
    end
    BC --> D["MessageDispatcherServlet /ws/*"]
    SC --> D
    D --> E["@Endpoint + @PayloadRoot"]
    D --> F["WSDL bean orders + XSD"]
~~~

Điểm hội tụ của cả hai phương án là:

`MessageDispatcherServlet → Spring-WS endpoint mapping → xử lý SOAP request/response`

Điểm khác biệt là **ai tạo và cấu hình Spring context cùng servlet**. Vì thế, khi chuyển dự án giữa Boot và ứng dụng Spring truyền thống, thường không cần viết lại XSD/WSDL hay quy tắc nghiệp vụ, nhưng phải thay đổi cách bootstrap, packaging, môi trường và dependency.

## 10. Bổ sung JAXB theo hướng contract-first

Sau khi xác nhận pipeline SOAP chạy được với `Element`/`Source`, bước tiếp theo thường là dùng **JAXB** để chuyển XML trong request/response thành các lớp Java.

Quy trình khuyến nghị:

1. Chốt XSD của operation, gồm namespace, kiểu dữ liệu, thứ tự phần tử và ràng buộc optional/nillable.
2. Cấu hình công cụ **XJC/JAXB code generation** tương thích với phiên bản Java/Spring (Jakarta hoặc javax).
3. Sinh các lớp Java và `ObjectFactory` theo XSD; không tự đặt lại QName khác hợp đồng.
4. Sử dụng các lớp sinh trong endpoint, hoặc cấu hình `Jaxb2Marshaller` khi ứng dụng cần marshal/unmarshal tường minh (nhất là SOAP client).
5. Đối chiếu XML do JAXB marshal với schema, kiểm tra namespace, loại phần tử rỗng/nil, và SOAP version.

Ví dụ endpoint sau khi đã sinh lớp `GetOrderRequest` và `GetOrderResponse`:

~~~java
@Endpoint
public class JaxbOrderEndpoint {

    private static final String NS = "urn:example:orders:v1";
    private final OrderService service;

    public JaxbOrderEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        GetOrderResponse response = new GetOrderResponse();
        response.setStatus(
                service.findStatus(request.getOrderId())
        );
        return response;
    }
}
~~~

Đây là **biến thể minh họa để thay thế** endpoint DOM trước đó, không được đăng ký đồng thời với `OrderEndpoint` cho cùng root QName. `OrderService` và các lớp JAXB là những thành phần của ứng dụng cần triển khai/sinh từ XSD. Việc endpoint có thể trực tiếp nhận/trả DTO còn phụ thuộc kiểu JAXB được sinh (có `@XmlRootElement` hay dùng `JAXBElement`) và các argument resolver/return value handler đang được cấu hình.

Client dùng `WebServiceTemplate` có thể cấu hình `Jaxb2Marshaller`:

~~~java
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("example.orders.ws.schema");
marshaller.afterPropertiesSet();

WebServiceTemplate template = new WebServiceTemplate();
template.setMarshaller(marshaller);
template.setUnmarshaller(marshaller);
~~~

Đoạn trên giả định `example.orders.ws.schema` là package thực tế chứa các lớp JAXB được sinh và metadata context hợp lệ. Phải khớp package sinh ra và runtime JAXB trên classpath; đây không phải giá trị dùng được cho mọi dự án. Để gửi SOAP 1.1 với action cụ thể, có thể dùng `SoapActionCallback` và URL lấy từ `soap:address` trong WSDL; tuy nhiên WSDL/endpoint ở ví dụ tối thiểu chưa bắt buộc một action khác rỗng.

Lưu ý: **chỉ thêm `Jaxb2Marshaller` vào context không bảo đảm mọi endpoint method tự chuyển đổi theo JAXB theo cách mong muốn**; cần kiểm tra annotation, JAXB class được sinh và cấu hình adapter thực tế.

## 11. Các thành phần nên bổ sung khi chuyển từ ví dụ sang hệ thống doanh nghiệp

Khởi tạo được servlet và endpoint mới là bước đầu. Một dịch vụ SOAP tích hợp ổn định còn cần xử lý dữ liệu không hợp lệ, bảo mật, kết nối và kiểm thử.

| Thành phần | Tác dụng | Thời điểm tích hợp |
| --- | --- | --- |
| `PayloadValidatingInterceptor` | Kiểm tra request/response theo XSD | Sau khi có XSD và endpoint ổn định |
| SOAP Fault resolver | Chuyển ngoại lệ thành SOAP Fault theo hợp đồng | Khi định nghĩa tình huống lỗi và mã lỗi |
| JAXB/XJC | Ánh xạ XML ↔ Java có kiểu | Khi contract đã ổn định để sinh mã |
| `WebServiceTemplate` | Viết SOAP client gọi dịch vụ đối tác | Khi ứng dụng cần gọi SOAP bên ngoài |
| WS-Security interceptor | Xác minh/đính kèm chữ ký, timestamp, token theo policy | Khi hợp đồng yêu cầu message security |
| TLS / mTLS | Bảo vệ kết nối, xác thực chứng chỉ máy chủ/client | Trước khi tích hợp môi trường bảo mật |
| Timeout và retry policy | Giới hạn treo request, kiểm soát thử lại | Khi có phụ thuộc mạng và nghiệp vụ có tác dụng phụ |
| Metrics, tracing, correlation ID | Điều tra lỗi qua proxy và nhiều dịch vụ | Trước khi đưa vào vận hành |
| Kiểm thử tương thích WSDL/XML | Phát hiện thay đổi phá vỡ client | Trong CI và trước mỗi bản phát hành |

### 11.1. XSD validation

`@PayloadRoot` chỉ giúp chọn handler; **nó không thay thế xác thực toàn bộ XSD**. Nếu request có đúng root element nhưng sai kiểu dữ liệu hoặc thiếu phần tử con, endpoint DOM trong ví dụ vẫn có thể được gọi.

Spring-WS có `PayloadValidatingInterceptor` để thực hiện validation nếu được đăng ký vào interceptor chain. Cần quyết định kiểm tra request, response hoặc cả hai, cùng chính sách lỗi khi dữ liệu không hợp lệ. Không nên khẳng định ứng dụng tự động validate chỉ vì đã nạp `XsdSchema` để sinh WSDL.

### 11.2. SOAP Fault và mã lỗi HTTP

Khi phát hiện lỗi nghiệp vụ, cần định nghĩa cách biểu diễn **SOAP Fault** (SOAP 1.1: `faultcode`/`faultstring`/`detail`; SOAP 1.2: `Code`/`Reason`/`Detail`). Mã HTTP phụ thuộc SOAP version/binding và hạ tầng. Chẳng hạn SOAP 1.1 Fault qua HTTP thường đi với HTTP 500, nhưng HTTP 500 trả HTML bởi gateway **không phải** SOAP Fault.

Các endpoint cần có cơ chế xử lý ngoại lệ rõ ràng để không làm lộ stack trace, thông tin kết nối hoặc dữ liệu nhạy cảm trong SOAP Fault trả cho client.

### 11.3. XML security, WS-Security và chứng chỉ

Spring-WS có thể được cấu hình với các interceptor phục vụ xử lý bảo mật thông điệp, chẳng hạn cơ chế WS-Security dựa trên thư viện hỗ trợ. Yêu cầu chữ ký số, username token, timestamp và xác thực chứng chỉ phải dựa trên policy/hợp đồng của đối tác, không chỉ dựa vào việc endpoint dùng HTTPS.

Tránh vô hiệu hóa kiểm tra chứng chỉ TLS để vượt qua lỗi kết nối trong môi trường thử nghiệm rồi đưa nguyên cấu hình đó lên production. Cũng cần kiểm soát external entities khi tự parse XML, tránh mở truy cập tài nguyên ngoài không cần thiết.

## 12. Những lỗi khởi tạo hay gặp và cách kiểm tra

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Ứng dụng không khởi động do thiếu class | BOM/phiên bản Spring-WS không tương thích, thiếu dependency | Dependency tree, Java/Jakarta API, Spring versions |
| WSDL URL trả HTTP 404 | Bean WSDL sai tên, servlet mapping sai hoặc context path khác | Bean `orders`, `/ws/*`, URL thực tế |
| WSDL tải được nhưng POST SOAP thất bại | `soap:address` sai địa chỉ, URL dùng nhầm `.wsdl`, proxy route khác | `setLocationUri`, URL POST và gateway |
| HTTP 405 | Gửi GET vào endpoint chỉ nhận POST hoặc sai servlet route | HTTP method và endpoint URL |
| HTTP 415 | `Content-Type` không phù hợp SOAP version | `text/xml` cho SOAP 1.1, `application/soap+xml` cho SOAP 1.2 |
| SOAP Fault `VersionMismatch` | SOAP Envelope namespace không đúng version | Binding công bố và message factory |
| “No endpoint mapping found” | `@Endpoint` không được quét hoặc root QName không khớp `@PayloadRoot` | Component scan, namespace/localPart |
| Không tìm thấy `orders.xsd` | Resource path/classpath sai hoặc file không được đóng gói | `src/main/resources/xsd/orders.xsd` và classpath |
| JAXB marshal/unmarshal thất bại | Class sinh sai package/namespace hoặc runtime JAXB thiếu | XJC config, `@XmlRootElement`, contextPath, XML thực tế |
| WAR chạy ở URL khác dự kiến | Context path của Servlet container thay đổi | Tên WAR, container config, reverse proxy |
| WSDL công bố URL `http://localhost:...` | Dịch vụ chạy sau proxy nhưng address không chuyển đúng | `transformWsdlLocations`, forwarded headers, public URL |
| Lỗi TLS handshake | Truststore, certificate chain, hostname, mTLS | Kiểm tra chứng chỉ/keystore theo môi trường |

Đừng sửa WSDL hoặc action theo cảm tính khi gặp lỗi. Hãy ghi lại **URL thực tế**, HTTP status, Content-Type, SOAP version, QName root của Body và log endpoint mapping. Nếu chỉ có lỗi DNS/TCP/TLS, thường chưa có SOAP response để phân tích.

## 13. Chiến lược kiểm thử ngay sau khi khởi tạo

Nên ưu tiên các kiểm thử cho thấy project đã kết nối đúng từng tầng:

| Ca kiểm thử | Spring Boot | Spring độc lập |
| --- | --- | --- |
| Spring context khởi động | `@SpringBootApplication` quét đúng endpoint/config | `WebApplicationInitializer` tải context đúng |
| Servlet nhận request | Mapping `/ws/*` hoạt động | Mapping `/ws/*` hoạt động trên container |
| GET WSDL | `/ws/orders.wsdl` có hợp đồng hợp lệ | `/<context-path>/ws/orders.wsdl` có hợp đồng hợp lệ |
| XSD được tải | Bean `ordersSchema` nạp từ classpath | Cùng bean nạp từ classpath |
| SOAP POST hợp lệ | Chọn `@PayloadRoot` và trả SOAP response | Cùng cách chọn endpoint |
| Sai namespace root | Không được ánh xạ nhầm sang `GetOrder` | Cùng kỳ vọng |
| Payload sai XSD | Bị phát hiện khi interceptor validator được bật | Cùng kỳ vọng |
| SOAP 1.2 vào SOAP 1.1 endpoint | Không giả định sẽ được chấp nhận | Cùng kỳ vọng |
| WSDL public sau proxy | Không chứa URL nội bộ không mong muốn | Tương tự |
| Kết nối HTTPS/mTLS | Kiểm tra hạ tầng runtime | Kiểm tra hạ tầng container |

Với Spring-WS, `MockWebServiceClient` hỗ trợ kiểm thử xử lý endpoint ở mức SOAP message; kiểm thử HTTP status, TLS, servlet mapping và reverse proxy thường cần một môi trường tích hợp chạy qua HTTP(S). Một test chỉ gọi Java method trực tiếp không chứng minh WSDL, servlet hay JAXB XML trên dây đúng.

### 13.1. Tối thiểu một bài test nội dung SOAP

Tư duy kiểm thử cho operation `GetOrder`:

~~~text
Given:
  - Đã khởi động application/context Spring-WS.
  - SOAP Body chứa {urn:example:orders:v1}GetOrderRequest.
  - Trường orderId = "ORD-1001".
When:
  - Client gửi request tới SOAP endpoint.
Then:
  - Phản hồi là SOAP Envelope hợp lệ.
  - SOAP Body chứa {urn:example:orders:v1}GetOrderResponse.
  - Trường status = "FOUND".
  - Không phát sinh SOAP Fault.
~~~

Test tiếp theo nên gửi một `GetOrderRequest` thiếu `orderId` và xác nhận ứng dụng xử lý đúng theo **XSD validation và hợp đồng lỗi** đã cấu hình; ví dụ DOM tối thiểu ở mục 6 chưa đại diện cho một chính sách Fault hoàn chỉnh.

## 14. Bài tập thực hành

Bạn cần tạo SOAP service cung cấp operation `CheckInventory`, nhận mã sản phẩm và trả số lượng còn tồn. Hãy thực hiện **một trong hai cách khởi tạo**, sau đó thử triển khai cách còn lại với cùng XSD.

Đầu vào đề xuất:

~~~xml
<i:CheckInventoryRequest xmlns:i="urn:example:inventory:v1">
    <i:productCode>SKU-001</i:productCode>
</i:CheckInventoryRequest>
~~~

Đầu ra đề xuất:

~~~xml
<i:CheckInventoryResponse xmlns:i="urn:example:inventory:v1">
    <i:quantity>12</i:quantity>
</i:CheckInventoryResponse>
~~~

Yêu cầu thực hành:

1. Tạo XSD có global elements `CheckInventoryRequest`/`CheckInventoryResponse`, `elementFormDefault="qualified"`; khai báo `quantity` là `xs:int`.
2. Tạo bean `DefaultWsdl11Definition` với tên như `inventory`, target namespace đúng, SOAP 1.1 document/literal và location URI rõ ràng.
3. Đăng ký servlet và một `@Endpoint` khớp `{urn:example:inventory:v1}CheckInventoryRequest`.
4. Lấy WSDL qua HTTP GET, ghi lại phần tử `wsdl:portType`, `wsdl:binding` và `soap:address`.
5. Gửi SOAP request qua POST, đối chiếu response XML với XSD.
6. Đổi prefix `i` thành một prefix khác nhưng giữ URI; kiểm tra endpoint vẫn hiểu đúng QName.
7. Gửi request với root sai namespace; xác nhận có lỗi ánh xạ/validation phù hợp, không đi vào nghiệp vụ sai.
8. Triển khai lên một URL có context path hoặc qua reverse proxy; kiểm tra địa chỉ WSDL công bố không bị lệch với URL SOAP thực tế.

**Tiêu chí hoàn thành:** cùng một hợp đồng XSD được phục vụ nhất quán trong cả hai cách bootstrap; client đọc được WSDL và gọi đúng endpoint; kiểm thử chứng minh namespace, servlet mapping và nội dung SOAP hoạt động theo hợp đồng.

## 15. Ghi nhớ

- **Spring Boot** đơn giản hóa việc bootstrap, dependency và vận hành; **Spring độc lập** cho phép cấu hình context/Servlet container trực tiếp. Cả hai dùng chung Spring-WS và có thể tuân theo contract-first.
- **XSD được thiết kế trước**, sau đó `DefaultWsdl11Definition` có thể công bố WSDL từ XSD; WSDL sinh ra phải được đọc và kiểm tra, nhất là operation, binding, namespace và address.
- **`MessageDispatcherServlet`** là điểm vào HTTP của SOAP; servlet mapping, WSDL location và URL gửi POST phải nhất quán.
- **`@EnableWs`**, `@Endpoint` và `@PayloadRoot` kết nối cấu hình Spring-WS với root QName của SOAP Body; việc quét component phải đúng.
- **JAXB code generation là bước riêng**: thêm Spring-WS starter hoặc dependency không tự sinh DTO từ XSD. Chọn đúng thế hệ Jakarta/javax để tránh lỗi classpath và marshal/unmarshal.
- **WSDL khả dụng chưa có nghĩa SOAP endpoint hoạt động**. Phải gửi request thật, kiểm tra SOAP Body/response và xác minh khi có proxy, context path hoặc TLS.
- Sau bước khởi tạo, tiếp tục bổ sung **XSD validation, SOAP Fault, interceptor, WS-Security, chứng chỉ và kiểm thử tương thích** để dịch vụ doanh nghiệp vận hành ổn định.
