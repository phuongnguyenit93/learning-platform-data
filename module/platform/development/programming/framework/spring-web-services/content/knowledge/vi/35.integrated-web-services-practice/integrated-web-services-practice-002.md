# Sinh lớp JAXB và hiện thực endpoint dựa trên hợp đồng

**Chương:** Thực hành tổng hợp  
**Chủ đề:** Spring Web Services (SOAP, contract-first)  
**Bài thực hành:** Từ hợp đồng XSD đến lớp JAXB, endpoint xử lý yêu cầu, WSDL và kiểm thử tương thích.

## 1. Mục tiêu và bối cảnh

Một hệ thống quản lý đơn hàng cần cung cấp thao tác tra cứu đơn hàng cho ứng dụng của đối tác qua SOAP. Nhóm tích hợp thống nhất cấu trúc XML trước khi viết Java để hai bên có thể phát triển và kiểm thử độc lập. Bài này thực hiện quy trình **contract-first** với Spring Web Services:

1. Định nghĩa thông điệp và kiểu dữ liệu trong XSD, giữ namespace và tên phần tử làm giao diện công khai.
2. Dùng XJC sinh các lớp JAXB từ XSD; ứng dụng sử dụng lớp sinh ra thay vì tự tạo DTO XML.
3. Công bố WSDL dựa trên XSD và hiện thực `@Endpoint` ánh xạ đúng QName của yêu cầu.
4. Gửi SOAP request, kiểm chứng response và xử lý trường hợp lỗi bằng SOAP Fault.
5. Kiểm thử cả hành vi endpoint và tính tuân thủ hợp đồng; nhận diện các thay đổi có thể phá vỡ client.

Ví dụ dùng **Java 17, Spring Boot 3.3.x, Spring Web Services 4.x, Jakarta JAXB** và Maven. Nếu tích hợp vào dự án đang dùng phiên bản khác, cần giữ một hệ tương thích thống nhất: Spring Boot 3+ sử dụng `jakarta.xml.bind.*`, trong khi nhiều dự án cũ vẫn sử dụng `javax.xml.bind.*`. Không trộn hai hệ annotation/runtime trong cùng một mô hình JAXB.

## 2. Hình dung luồng contract-first

~~~mermaid
flowchart LR
    A["orders.xsd\nHợp đồng XML"] --> B["XJC\nSinh JAXB"]
    A --> C["DefaultWsdl11Definition\nCông bố WSDL"]
    B --> D["OrderEndpoint\n@RequestPayload / @ResponsePayload"]
    C --> E["SOAP client\nĐọc WSDL"]
    E -->|SOAP request| D
    D --> F["OrderService\nNghiệp vụ"]
    F --> D
    D -->|SOAP response / fault| E
~~~

**Nguyên tắc cốt lõi:** XSD là nguồn quy định cấu trúc dữ liệu XML. WSDL mô tả cách gọi dịch vụ; mã Java chỉ là phần hiện thực. Một client SOAP ở nền tảng khác vẫn có thể tích hợp chỉ dựa vào WSDL/XSD, không cần biết tên package hay class Java nội bộ.

Cấu trúc mã nguồn minh họa:

~~~text
src/main/
  java/vn/example/soap/
    OrdersSoapApplication.java
    config/SoapConfig.java
    endpoint/OrderEndpoint.java
    service/OrderService.java
    fault/OrderNotFoundException.java
  resources/
    application.yml
    xsd/orders.xsd
target/generated-sources/jaxb/
  vn/example/soap/contract/      # XJC sinh ra; không chỉnh sửa bằng tay
src/test/java/vn/example/soap/
  endpoint/OrderEndpointTest.java
~~~

## 3. Chuẩn bị Maven và bộ sinh JAXB

Trong `pom.xml` của ứng dụng Spring Boot, cần có các dependency và plugin sau. Nếu đã có các phần tử `dependencies` hoặc `build/plugins`, ghép các mục tương ứng vào đó thay vì khai báo phần tử trùng lặp.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web-services</artifactId>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
    </dependency>
    <dependency>
        <groupId>wsdl4j</groupId>
        <artifactId>wsdl4j</artifactId>
        <version>1.6.3</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>jaxb2-maven-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <id>generate-jaxb</id>
                    <goals>
                        <goal>xjc</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <sources>
                    <source>src/main/resources/xsd/orders.xsd</source>
                </sources>
                <packageName>vn.example.soap.contract</packageName>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Plugin `jaxb2-maven-plugin` phiên bản 3.x tạo annotation thuộc namespace Jakarta. Goal `xjc` được gắn vào pha `generate-sources` và đưa mã sinh ra vào source root của Maven. Đây là ví dụ cho một dự án sử dụng Spring Boot parent/BOM để quản lý phiên bản dependency Spring và JAXB; hãy chọn một phiên bản Boot 3.3.x cụ thể trong cấu hình parent của dự án.

## 4. Viết XSD trước khi viết endpoint

Tạo `src/main/resources/xsd/orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="https://example.vn/orders/v1"
           targetNamespace="https://example.vn/orders/v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderStatus">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="PAID"/>
            <xs:enumeration value="CANCELLED"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:complexType name="OrderType">
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
            <xs:element name="status" type="tns:OrderStatus"/>
            <xs:element name="totalAmount" type="xs:decimal"/>
            <xs:element name="currency" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>

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
                <xs:element name="order" type="tns:OrderType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Các điểm cần hiểu:

| Thành phần XSD | Tác dụng khi tích hợp SOAP |
|---|---|
| `targetNamespace` | Định danh hợp đồng; QName gồm namespace URI và local name. |
| `elementFormDefault="qualified"` | Các phần tử con trong XML phải thuộc namespace của hợp đồng. |
| `GetOrderRequest`, `GetOrderResponse` | Hai phần tử toàn cục được Spring-WS nhận diện là request/response của một thao tác `GetOrder`. |
| `xs:sequence` | Thứ tự phần tử XML có ý nghĩa, đặc biệt khi kiểm tra theo XSD. |
| `OrderStatus` | Giới hạn trạng thái vào các giá trị được công bố. |
| `xs:decimal` | Sinh kiểu `BigDecimal`, phù hợp hơn `double` cho số tiền. |

Các phần tử bên trong `xs:sequence` mặc định đều bắt buộc (`minOccurs="1"`). Vì `orderId` đang là `xs:string`, chuỗi rỗng vẫn có thể hợp lệ theo XSD; nếu hợp đồng cần cấm rỗng, bổ sung ràng buộc `minLength` hoặc `pattern` vào schema trước khi thống nhất với đối tác.

## 5. Sinh lớp JAXB và đọc đúng kết quả XJC

Chạy từ thư mục gốc dự án:

~~~bash
mvn clean generate-sources
~~~

XJC sẽ tạo các class trong `target/generated-sources/jaxb/vn/example/soap/contract/`, dự kiến gồm:

~~~text
GetOrderRequest.java
GetOrderResponse.java
OrderType.java
OrderStatus.java
ObjectFactory.java
package-info.java
~~~

Ví dụ về cách sử dụng API được sinh (lược bỏ phần annotation để thấy cấu trúc):

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1001");

OrderType order = new OrderType();
order.setOrderId("ORD-1001");
order.setStatus(OrderStatus.PAID);
order.setTotalAmount(new BigDecimal("149900.00"));
order.setCurrency("VND");

GetOrderResponse response = new GetOrderResponse();
response.setOrder(order);
~~~

Đừng chép đoạn trên vào chính các file generated. Mọi mã ở `target/generated-sources` có thể bị ghi lại khi chạy Maven. Muốn thay tên lớp, package hoặc kiểu ánh xạ, sửa XSD hoặc cấu hình binding XJC rồi sinh lại.

Các phần tử toàn cục như `GetOrderRequest` và `GetOrderResponse` thường có `@XmlRootElement` nên Spring-WS có thể nhận/trả trực tiếp. Nếu trong một hợp đồng khác XJC tạo kiểu chỉ có `@XmlType`, cần dùng `JAXBElement` cùng `ObjectFactory` hoặc điều chỉnh mô hình phần tử; không tự thêm annotation vào mã sinh.

**Kiểm tra bắt buộc sau khi sinh:** import phải là `jakarta.xml.bind.annotation.*`. Nếu thấy `javax.xml.bind.annotation.*`, kiểm tra lại plugin và dependency trước khi viết endpoint.

## 6. Công bố WSDL từ XSD bằng Spring Web Services

Trong `src/main/resources/application.yml`:

~~~yaml
spring:
  webservices:
    path: /ws
~~~

Đường dẫn này cấu hình nơi `MessageDispatcherServlet` của Spring Boot tiếp nhận SOAP. Tạo `src/main/java/vn/example/soap/config/SoapConfig.java`:

~~~java
package vn.example.soap.config;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurerAdapter;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class SoapConfig extends WsConfigurerAdapter {

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
        wsdl.setPortTypeName("OrdersPort");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace("https://example.vn/orders/v1");
        wsdl.setSchema(ordersSchema);
        return wsdl;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validator = new PayloadValidatingInterceptor();
        validator.setXsdSchema(ordersSchema());
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);
        interceptors.add(validator);
    }
}
~~~

`DefaultWsdl11Definition` tạo tài liệu WSDL 1.1 dựa trên phần tử toàn cục có hậu tố `Request` và `Response`. Với hai phần tử trên, WSDL sẽ có thao tác `GetOrder`. Sau khi khởi động ứng dụng, mở:

~~~text
http://localhost:8080/ws/orders.wsdl
~~~

Điểm cần đối chiếu trong WSDL là namespace `https://example.vn/orders/v1`, thao tác `GetOrder`, schema của thông điệp và `soap:address`. Dù Spring-WS sinh WSDL khi chạy, **hợp đồng công khai cần được đóng phiên bản, lưu trữ và kiểm thử tương thích**; không xem mọi thay đổi từ mã Java là lý do để tự động thay WSDL đã giao cho đối tác.

Interceptor ở trên kiểm tra payload yêu cầu và phản hồi theo XSD. XJC tạo class/annotation nhưng **không mặc nhiên xác thực mọi ràng buộc của XML khi marshal/unmarshal**; việc kiểm tra schema cần cấu hình rõ như ví dụ này.

## 7. Viết nghiệp vụ và endpoint SOAP

Tạo `src/main/java/vn/example/soap/service/OrderService.java`:

~~~java
package vn.example.soap.service;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import vn.example.soap.fault.OrderNotFoundException;

@Service
public class OrderService {

    public Order findById(String orderId) {
        // Dữ liệu giả lập; thay bằng repository/service thật khi tích hợp.
        if (!"ORD-1001".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }
        return new Order(
                "ORD-1001",
                "PAID",
                new BigDecimal("149900.00"),
                "VND");
    }

    public record Order(
            String id,
            String status,
            BigDecimal totalAmount,
            String currency) {
    }
}
~~~

Tạo `src/main/java/vn/example/soap/fault/OrderNotFoundException.java`:

~~~java
package vn.example.soap.fault;

import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;

@SoapFault(
        faultCode = FaultCode.CLIENT,
        faultStringOrReason = "Đơn hàng không tồn tại")
public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
    }
}
~~~

`@SoapFault` giúp phía SOAP nhận mã lỗi phù hợp với dữ liệu được yêu cầu (`Client` trong SOAP 1.1), thay vì để exception nghiệp vụ rơi thành lỗi máy chủ không rõ nguyên nhân. Thông điệp SOAP Fault ở đây là thông điệp tĩnh, tránh vô tình lộ dữ liệu nội bộ hoặc stack trace.

Tạo `src/main/java/vn/example/soap/endpoint/OrderEndpoint.java`:

~~~java
package vn.example.soap.endpoint;

import org.springframework.stereotype.Component;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import vn.example.soap.contract.GetOrderRequest;
import vn.example.soap.contract.GetOrderResponse;
import vn.example.soap.contract.OrderStatus;
import vn.example.soap.contract.OrderType;
import vn.example.soap.service.OrderService;

@Endpoint
public class OrderEndpoint {
    private static final String NAMESPACE = "https://example.vn/orders/v1";
    private final OrderService orderService;

    public OrderEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NAMESPACE, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(@RequestPayload GetOrderRequest request) {
        OrderService.Order found = orderService.findById(request.getOrderId());

        OrderType xmlOrder = new OrderType();
        xmlOrder.setOrderId(found.id());
        xmlOrder.setStatus(OrderStatus.fromValue(found.status()));
        xmlOrder.setTotalAmount(found.totalAmount());
        xmlOrder.setCurrency(found.currency());

        GetOrderResponse response = new GetOrderResponse();
        response.setOrder(xmlOrder);
        return response;
    }
}
~~~

`@Endpoint` đánh dấu endpoint để Spring-WS đăng ký. `@PayloadRoot` so khớp **QName của phần tử gốc bên trong SOAP Body**, không dựa vào URL hay tên method Java. `@RequestPayload` chuyển XML sang đối tượng JAXB; `@ResponsePayload` chuyển đối tượng JAXB ngược thành XML. Endpoint chỉ điều phối ánh xạ dữ liệu, nghiệp vụ nằm trong `OrderService`.

Để ví dụ chạy độc lập, class khởi động ứng dụng đặt tại package cha `vn.example.soap`:

~~~java
package vn.example.soap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersSoapApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersSoapApplication.class, args);
    }
}
~~~

## 8. Gửi SOAP request và kiểm tra response

Tạo file `request.xml` để thử thủ công:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="https://example.vn/orders/v1">
    <soapenv:Header/>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Chạy server bằng `mvn spring-boot:run`, rồi gửi SOAP 1.1:

~~~bash
curl -i \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: ""' \
  --data-binary @request.xml \
  http://localhost:8080/ws
~~~

Nội dung mong đợi trong SOAP Body (prefix có thể khác, namespace và giá trị phải đúng):

~~~xml
<ord:GetOrderResponse xmlns:ord="https://example.vn/orders/v1">
    <ord:order>
        <ord:orderId>ORD-1001</ord:orderId>
        <ord:status>PAID</ord:status>
        <ord:totalAmount>149900.00</ord:totalAmount>
        <ord:currency>VND</ord:currency>
    </ord:order>
</ord:GetOrderResponse>
~~~

Thay `ORD-1001` bằng mã không tồn tại như `ORD-9999`, endpoint trả SOAP Fault với mã lỗi phía yêu cầu. Thử xóa phần tử `orderId`, bộ kiểm tra XSD phải từ chối payload không đúng hợp đồng. Lưu ý `SOAPAction` không được dùng làm khóa định tuyến ở ví dụ này; `@PayloadRoot` định tuyến theo QName của payload.

### Kiểm thử tự động endpoint

Tạo `src/test/java/vn/example/soap/endpoint/OrderEndpointTest.java`:

~~~java
package vn.example.soap.endpoint;

import javax.xml.transform.Source;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

@SpringBootTest
class OrderEndpointTest {

    @Autowired
    private ApplicationContext applicationContext;

    private MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(applicationContext);
    }

    @Test
    void returnsOrderThatMatchesContract() throws Exception {
        Source request = new StringSource("""
                <o:GetOrderRequest xmlns:o="https://example.vn/orders/v1">
                    <o:orderId>ORD-1001</o:orderId>
                </o:GetOrderRequest>
                """);

        Source expected = new StringSource("""
                <o:GetOrderResponse xmlns:o="https://example.vn/orders/v1">
                    <o:order>
                        <o:orderId>ORD-1001</o:orderId>
                        <o:status>PAID</o:status>
                        <o:totalAmount>149900.00</o:totalAmount>
                        <o:currency>VND</o:currency>
                    </o:order>
                </o:GetOrderResponse>
                """);

        client.sendRequest(withPayload(request))
                .andExpect(noFault())
                .andExpect(payload(expected));
    }
}
~~~

`MockWebServiceClient` gọi các thành phần endpoint ngay trong application context, không cần mở HTTP port. Chạy `mvn test` để kiểm tra mapping, JAXB marshalling và nội dung payload. Test này không thay thế test qua HTTP thực: kiểm tra endpoint URL, WSDL và cấu hình reverse proxy nên nằm trong bộ kiểm thử tích hợp riêng.

Với SOAP Fault, nên bổ sung test cho đơn hàng không tồn tại và request sai XSD để kiểm tra loại lỗi, mã lỗi và phần thông tin client được phép thấy. Khi hợp đồng được giao cho đối tác, lưu các mẫu request/response làm dữ liệu kiểm thử hồi quy.

## 9. Dùng lại JAXB ở phía SOAP client

Lớp JAXB cũng có thể phục vụ client, giúp giảm lỗi viết XML bằng tay. Ví dụ cấu hình trong một ứng dụng client Spring:

~~~java
@Configuration
class OrderClientConfig {

    @Bean
    Jaxb2Marshaller orderMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("vn.example.soap.contract");
        return marshaller;
    }

    @Bean
    WebServiceTemplate orderWebServiceTemplate(Jaxb2Marshaller marshaller) {
        WebServiceTemplate template = new WebServiceTemplate(marshaller);
        template.setUnmarshaller(marshaller);
        template.setDefaultUri("http://localhost:8080/ws");
        return template;
    }
}
~~~

Với các import `org.springframework.context.annotation.*`, `org.springframework.oxm.jaxb.Jaxb2Marshaller` và `org.springframework.ws.client.core.WebServiceTemplate`, client có thể gọi:

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1001");

GetOrderResponse response = (GetOrderResponse)
        orderWebServiceTemplate.marshalSendAndReceive(request);
~~~

Trong môi trường doanh nghiệp, URL đích thường lấy từ cấu hình; client phải có timeout, cơ chế xác thực, xử lý SOAP Fault và chính sách retry phù hợp. Không mặc định retry mọi thao tác làm thay đổi trạng thái.

## 10. Các lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| HTTP 404 khi mở `/ws/orders.wsdl` | Đường dẫn servlet hoặc tên bean WSDL không khớp | Kiểm tra `spring.webservices.path` và `@Bean(name = "orders")`. |
| Không tìm thấy endpoint cho payload | Namespace URI hoặc `localPart` khác XSD | So QName của phần tử đầu trong SOAP Body với `@PayloadRoot`. |
| Lỗi `NoClassDefFoundError: javax/xml/bind` | Trộn mã JAXB kiểu Java EE và Jakarta | Kiểm tra imports và plugin/runtime JAXB. |
| `UnmarshallingFailureException` | XML không khớp QName hoặc cấu trúc do XJC sinh | Kiểm tra element gốc, namespace, thứ tự `xs:sequence` và các kiểu dữ liệu. |
| Trả SOAP Fault khi thiếu phần tử | XSD yêu cầu dữ liệu đó, validator đã từ chối | Đối chiếu `minOccurs`, `xs:sequence` và XML gửi lên. |
| WSDL hoạt động nội bộ nhưng URL công bố sai | `soap:address` chưa phù hợp đường dẫn công khai/proxy | Kiểm tra thiết lập WSDL location và cơ chế biến đổi địa chỉ ở deployment. |
| Thay đổi XSD làm client cũ lỗi | Phá vỡ schema hoặc namespace đã công bố | Đối chiếu WSDL/XSD giữa các phiên bản và chạy regression test client. |

## 11. Tiêu chí hoàn thành và mở rộng an toàn

Một bài thực hành đạt yêu cầu khi:

- XSD được quản lý như hợp đồng và XJC sinh ra class JAXB bằng lệnh build, không sửa file generated.
- WSDL ở `/ws/orders.wsdl` mô tả đúng thao tác `GetOrder` và kiểu yêu cầu/phản hồi.
- SOAP request đúng namespace trả dữ liệu khớp XSD; request thiếu phần tử bắt buộc bị chặn và mã đơn hàng không tồn tại trả SOAP Fault có kiểm soát.
- Có test tự động xác nhận payload hợp lệ và kế hoạch kiểm thử tương thích cho các client hiện hữu.

Khi đưa vào hệ thống doanh nghiệp, mở rộng theo thứ tự: **(1)** định nghĩa quy tắc phiên bản hợp đồng, tránh đổi hoặc xóa phần tử đã công bố; **(2)** áp dụng HTTPS/TLS, kiểm soát truy cập và chứng chỉ; **(3)** nếu cần bảo đảm tính toàn vẹn và danh tính ở mức thông điệp, cấu hình WS-Security (chẳng hạn xác thực, chữ ký và mã hóa với interceptor phù hợp); **(4)** giới hạn kích thước XML, cấu hình parser an toàn để giảm rủi ro XXE/entity expansion, kiểm tra schema và tránh ghi log thông tin nhạy cảm; **(5)** thử WSDL/XSD và SOAP Fault bằng client độc lập như SoapUI hoặc ứng dụng khác ngôn ngữ.

**Câu hỏi tự kiểm tra:** Vì sao thay tên Java method `getOrder()` thường không đổi hợp đồng, còn đổi `targetNamespace` có thể làm mọi SOAP client hiện có thất bại? Hãy giải thích dựa trên cơ chế định tuyến QName của `@PayloadRoot` và cách JAXB biểu diễn cấu trúc XML.
