# Công bố WSDL, XSD rồi tạo client gọi dịch vụ qua HTTP

## 1. Bài toán và kết quả cần đạt

Trong tích hợp doanh nghiệp, hai hệ thống thường được phát triển bằng công nghệ khác nhau nhưng phải thống nhất chính xác cấu trúc dữ liệu, thao tác và cách xử lý lỗi. Với **Spring Web Services (Spring-WS)**, cách tiếp cận **contract-first** bắt đầu bằng lược đồ XSD; từ hợp đồng đó, máy chủ công bố WSDL, triển khai SOAP endpoint và client sinh lớp JAXB để trao đổi thông điệp qua HTTP.

Bài thực hành xây dựng dịch vụ **Orders** cho phép một hệ thống tra cứu đơn hàng bằng mã đơn:

- Client gửi thông điệp **GetOrderRequest** chứa **orderId**.
- Server xử lý và trả **GetOrderResponse** gồm mã đơn, trạng thái, tổng tiền.
- Server công bố XSD và WSDL để một client độc lập biết được hợp đồng mà không cần truy cập mã nguồn Java của server.
- Client dùng **JAXB** và **WebServiceTemplate** để gọi SOAP 1.1 qua HTTP; đồng thời kiểm tra trường hợp thành công, sai hợp đồng và SOAP Fault.

Sau bài này, bạn có thể giải thích quan hệ giữa XSD, WSDL, XML payload, SOAP envelope, HTTP và JAXB; triển khai endpoint contract-first; tải WSDL/XSD từ URL công bố; tạo Java client; xác minh lời gọi thực tế và nhận diện các vấn đề tích hợp về namespace, version, bảo mật và tương thích.

Ví dụ dùng **Java 17+, Spring Boot 3.x và Spring-WS 4.x** (hệ **jakarta.xml.bind**). Khi làm trong một dự án có phiên bản khác, hãy đối chiếu API và hệ **javax/jakarta** tương ứng.

## 2. Luồng tương tác và quy ước hợp đồng

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant H as HTTP/SOAP servlet
    participant E as Spring-WS endpoint
    C->>H: GET /ws/orders.wsdl
    H-->>C: WSDL mô tả GetOrder và địa chỉ dịch vụ
    C->>H: GET /ws/ordersSchema.xsd
    H-->>C: XSD mô tả request/response
    Note over C: Sinh lớp JAXB từ XSD
    C->>H: POST /ws, SOAP GetOrderRequest
    H->>E: Phân giải @PayloadRoot
    E-->>H: GetOrderResponse hoặc SOAP Fault
    H-->>C: SOAP response qua HTTP
~~~

Phân biệt bốn thành phần:

| Thành phần | Vai trò trong ví dụ |
| --- | --- |
| **XSD** | Định nghĩa kiểu dữ liệu XML và hai phần tử gốc GetOrderRequest, GetOrderResponse. |
| **WSDL** | Công bố thao tác GetOrder, message, binding SOAP và địa chỉ dịch vụ. Trong ví dụ WSDL được Spring-WS sinh từ XSD. |
| **SOAP** | Bao bọc payload XML trong Envelope/Body; khi có lỗi có thể trả Fault. |
| **HTTP** | Kênh vận chuyển: GET tài liệu hợp đồng, POST thông điệp SOAP tới endpoint. |

Quy ước dùng trong toàn bài:

| Thuộc tính | Giá trị |
| --- | --- |
| Namespace | https://example.org/orders/v1 |
| Tên thao tác | GetOrder |
| Payload đầu vào | GetOrderRequest |
| Payload đầu ra | GetOrderResponse |
| WSDL | http://localhost:8080/ws/orders.wsdl |
| XSD | http://localhost:8080/ws/ordersSchema.xsd |
| SOAP endpoint | http://localhost:8080/ws |

**Chú ý:** URL namespace là định danh XML, không nhất thiết là trang web có thể mở. Prefix như **ord** chỉ là bí danh; namespace URI và tên phần tử mới quyết định cách Spring-WS nhận diện request.

## 3. Viết XSD trước khi viết Java

Tạo file **src/main/resources/xsd/orders.xsd**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="https://example.org/orders/v1"
           targetNamespace="https://example.org/orders/v1"
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
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="xs:string"/>
                <xs:element name="total" type="xs:decimal"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

**targetNamespace** chỉ rõ hợp đồng v1. **elementFormDefault="qualified"** yêu cầu các phần tử con nằm trong namespace đó. Hai phần tử gốc kết thúc bằng **Request** và **Response** để **DefaultWsdl11Definition** ghép thành thao tác **GetOrder**. Trong môi trường thực tế nên giới hạn dữ liệu bằng **minLength**, **pattern**, **enumeration**, và xác định rõ đơn vị tiền tệ, độ chính xác cùng tính tùy chọn của từng trường.

Contract-first có một nguyên tắc quan trọng: **đổi cấu trúc XML phải bắt đầu từ thay đổi hợp đồng và đánh giá tương thích**. Không âm thầm sửa DTO Java rồi để mỗi phía tự suy đoán XML tương ứng.

## 4. Cấu hình dự án và sinh JAXB

Tạo ứng dụng Spring Boot có các dependency Maven sau (đoạn này đặt trong các mục tương ứng của **pom.xml**; phiên bản Spring/JAXB runtime nên do Spring Boot BOM quản lý):

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
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>jaxb2-maven-plugin</artifactId>
            <version>3.2.0</version>
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
                <packageName>org.example.orders.xml</packageName>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Giữ nguyên các khai báo **parent**, **dependencyManagement** và plugin khác của dự án Boot hiện có. Chạy tại thư mục dự án:

~~~bash
./mvnw clean compile
~~~

Trên Windows có thể dùng **mvnw.cmd clean compile**; nếu không có Maven Wrapper thì dùng **mvn clean compile**. XJC tạo lớp JAXB dưới **target/generated-sources/jaxb**, chẳng hạn **GetOrderRequest**, **GetOrderResponse**, **ObjectFactory**. Các lớp sinh tự động cần được tạo lại khi XSD đổi, không sửa trực tiếp. Nếu dùng workspace gồm server và client là hai dự án, cả hai phải sinh lớp từ **cùng phiên bản XSD** hoặc dùng chung artifact chứa model đã sinh.

## 5. Công bố WSDL và XSD từ Spring-WS server

Trong ứng dụng server, tạo cấu hình **SoapWebServiceConfig.java**. Các import dưới đây tương ứng với Spring-WS 4 và Spring Boot 3:

~~~java
package org.example.orders;

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

@EnableWs
@Configuration
public class SoapWebServiceConfig {
    public static final String NAMESPACE = "https://example.org/orders/v1";

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet> messageDispatcherServlet(
            ApplicationContext context) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean(name = "ordersSchema")
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
        wsdl.setPortTypeName("OrdersPort");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace(NAMESPACE);
        wsdl.setSchema(ordersSchema);
        return wsdl;
    }
}
~~~

**Giải thích từng điểm quan trọng:**

1. **MessageDispatcherServlet** tiếp nhận HTTP request dưới **/ws/** và điều phối thông điệp SOAP tới endpoint. Đây là servlet SOAP; đường dẫn không đi qua REST controller.
2. Bean **ordersSchema** cung cấp XSD tại **/ws/ordersSchema.xsd**. Bean **orders** có kiểu **DefaultWsdl11Definition** công bố **/ws/orders.wsdl**. Tên bean quyết định tên URL tài liệu.
3. Spring-WS suy ra thao tác GetOrder từ cặp phần tử có hậu tố **Request/Response**. Khi tên không tuân quy ước, cần điều chỉnh suffix hoặc tự cung cấp WSDL tĩnh nếu cần kiểm soát hợp đồng chặt hơn.
4. **setLocationUri("/ws")** xác định địa chỉ SOAP service bên trong WSDL; **setTransformWsdlLocations(true)** hỗ trợ cập nhật địa chỉ được công bố theo request thực tế. Khi chạy sau reverse proxy, cần cấu hình forwarded headers/host đúng và xác minh URL công bố từ bên ngoài.

Ví dụ này dùng **WSDL được sinh động từ XSD**. Với hợp đồng do đối tác cấp, đã kiểm duyệt/chốt version hoặc yêu cầu giữ nguyên từng chi tiết binding, nên **công bố WSDL tĩnh** và chỉ triển khai endpoint tuân theo nó; không tự ý thay WSDL bên đối tác.

## 6. Xây dựng SOAP endpoint theo payload

Tạo **OrderEndpoint.java**. Đây là xử lý mẫu để quan sát giao thức; trong hệ thống thực, endpoint sẽ gọi service nghiệp vụ hoặc repository.

~~~java
package org.example.orders;

import java.math.BigDecimal;
import org.example.orders.xml.GetOrderRequest;
import org.example.orders.xml.GetOrderResponse;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {

    @PayloadRoot(
        namespace = SoapWebServiceConfig.NAMESPACE,
        localPart = "GetOrderRequest"
    )
    @ResponsePayload
    public GetOrderResponse getOrder(@RequestPayload GetOrderRequest request) {
        if (!"ORD-1001".equals(request.getOrderId())) {
            throw new OrderNotFoundException(request.getOrderId());
        }

        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(request.getOrderId());
        response.setStatus("CONFIRMED");
        response.setTotal(new BigDecimal("125000.00"));
        return response;
    }
}
~~~

**@PayloadRoot** khớp phần tử đầu tiên trong SOAP Body bằng **{namespace}localPart**. **@RequestPayload** chuyển XML vào object JAXB; **@ResponsePayload** biến object trả về thành XML. Một endpoint hợp lệ cần khớp chính xác namespace và tên phần tử, bất kể prefix bên client viết là gì.

Để biểu diễn lỗi nghiệp vụ thành SOAP Fault, khai báo exception có chú thích:

~~~java
package org.example.orders;

import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;

@SoapFault(faultCode = FaultCode.CLIENT)
public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(String orderId) {
        super("Không tìm thấy đơn hàng: " + orderId);
    }
}
~~~

**SoapFaultAnnotationExceptionResolver** cần được đăng ký trong cấu hình xử lý exception của ứng dụng để ánh xạ chú thích này thành SOAP Fault. Có thể khai báo tường minh nếu chưa được cấu hình:

~~~java
@Bean
public SoapFaultAnnotationExceptionResolver soapFaultResolver() {
    SoapFaultAnnotationExceptionResolver resolver =
            new SoapFaultAnnotationExceptionResolver();
    resolver.setOrder(1);
    return resolver;
}
~~~

Thêm import **org.springframework.ws.soap.server.endpoint.SoapFaultAnnotationExceptionResolver** vào class cấu hình. Với SOAP 1.1, **Client** (còn gọi **Sender** trong SOAP 1.2) biểu thị lỗi đầu vào/nghiệp vụ; **Server** (**Receiver** trong SOAP 1.2) dành cho lỗi xử lý phía dịch vụ. Trong hệ thống thật, nên ánh xạ riêng các loại lỗi, định nghĩa fault detail ổn định và tránh đưa stack trace hay thông tin nội bộ vào response.

## 7. Chạy server và xác minh tài liệu đã công bố

Với class **@SpringBootApplication** nằm tại package **org.example.orders** hoặc package cha của cấu hình/endpoint, khởi động server:

~~~bash
./mvnw spring-boot:run
~~~

Đảm bảo HTTP port 8080 không bị ứng dụng khác chiếm. Sau khi server chạy, tải các tài liệu:

~~~bash
curl -fS http://localhost:8080/ws/orders.wsdl -o orders.wsdl
curl -fS http://localhost:8080/ws/ordersSchema.xsd -o ordersSchema.xsd
~~~

Kiểm tra trong **orders.wsdl** có các thành phần **GetOrder**, **OrdersPort**, SOAP binding và **soap:address** trỏ tới **/ws**; đối chiếu phần XML Schema với **orders.xsd** gốc. Trong **ordersSchema.xsd** phải thấy **GetOrderRequest**, **GetOrderResponse** và namespace **https://example.org/orders/v1**.

Nếu mở **/ws/orders.wsdl** được nhưng gọi **/ws** thất bại, chưa thể kết luận dịch vụ đã hoạt động: GET WSDL chỉ kiểm tra công bố hợp đồng, còn POST SOAP mới kiểm tra dispatch, JAXB và xử lý nghiệp vụ.

## 8. Gửi SOAP request trực tiếp bằng HTTP

Tạo **request.xml** tại thư mục kiểm thử:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="https://example.org/orders/v1">
  <soapenv:Header/>
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Gửi request bằng cURL:

~~~bash
curl -i -X POST http://localhost:8080/ws -H "Content-Type: text/xml; charset=utf-8" --data-binary @request.xml
~~~

Phần SOAP Body của response thành công có dạng (prefix thực tế có thể khác):

~~~xml
<ord:GetOrderResponse xmlns:ord="https://example.org/orders/v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:status>CONFIRMED</ord:status>
  <ord:total>125000.00</ord:total>
</ord:GetOrderResponse>
~~~

**SOAP 1.1** sử dụng namespace Envelope **http://schemas.xmlsoap.org/soap/envelope/** và Content-Type **text/xml**; **SOAP 1.2** sử dụng namespace Envelope **http://www.w3.org/2003/05/soap-envelope** và Content-Type **application/soap+xml**. Hai phiên bản phải nhất quán giữa client, binding WSDL và server. Trong một số tích hợp SOAP 1.1, đối tác còn yêu cầu HTTP header **SOAPAction** theo WSDL; chỉ gửi giá trị được hợp đồng quy định.

Để thử lỗi nghiệp vụ, đổi **ORD-1001** thành **ORD-NOT-FOUND**, gửi lại request và kiểm tra response có **soap:Fault** với fault code phù hợp. Để thử lỗi định dạng, đổi **GetOrderRequest** thành tên phần tử hoặc namespace khác, hoặc bỏ trường **orderId** khi có bật schema validation. Hai trường hợp phải được kiểm tra riêng: **không tìm thấy SOAP endpoint** do QName sai khác với **payload đúng QName nhưng vi phạm XSD**.

## 9. Tạo Java SOAP client dùng chung XSD

Ở một ứng dụng client Spring Boot độc lập, khai báo **spring-boot-starter-web-services**, **jaxb-runtime** và cấu hình XJC như bước 4 để sinh lớp từ **cùng orders.xsd**. Không sao chép thủ công các DTO vì rất dễ lệch namespace hoặc kiểu dữ liệu.

Trong **application.yml** của client, khai báo địa chỉ có thể thay đổi theo môi trường:

~~~yaml
orders:
  soap:
    url: http://localhost:8080/ws
~~~

Cấu hình **Jaxb2Marshaller** và **WebServiceTemplate**:

~~~java
package org.example.orders.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class OrderClientConfig {

    @Bean
    public Jaxb2Marshaller orderMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("org.example.orders.xml");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate orderWebServiceTemplate(
            Jaxb2Marshaller orderMarshaller,
            Environment environment) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(orderMarshaller);
        template.setUnmarshaller(orderMarshaller);
        template.setDefaultUri(environment.getRequiredProperty("orders.soap.url"));
        return template;
    }
}
~~~

Class **OrderSoapClient.java** đóng gói thao tác để code nghiệp vụ không phải trực tiếp xây SOAP envelope:

~~~java
package org.example.orders.client;

import org.example.orders.xml.GetOrderRequest;
import org.example.orders.xml.GetOrderResponse;
import org.springframework.stereotype.Component;
import org.springframework.ws.client.core.WebServiceTemplate;

@Component
public class OrderSoapClient {
    private final WebServiceTemplate template;

    public OrderSoapClient(WebServiceTemplate template) {
        this.template = template;
    }

    public GetOrderResponse getOrder(String orderId) {
        GetOrderRequest request = new GetOrderRequest();
        request.setOrderId(orderId);
        return (GetOrderResponse) template.marshalSendAndReceive(request);
    }
}
~~~

Từ service hoặc **CommandLineRunner** của ứng dụng client, gọi:

~~~java
GetOrderResponse order = orderSoapClient.getOrder("ORD-1001");
System.out.println(order.getOrderId());
System.out.println(order.getStatus());
System.out.println(order.getTotal());
~~~

Kết quả mong đợi lần lượt là **ORD-1001**, **CONFIRMED** và **125000.00** (cách hiển thị BigDecimal phụ thuộc dữ liệu và xử lý hiển thị). Luồng thực tế: client marshal object JAXB thành XML → **WebServiceTemplate** gói SOAP và POST HTTP → server unmarshall request → endpoint xử lý → marshal response → client unmarshall thành **GetOrderResponse**. Client được cấu hình **SOAP endpoint /ws**, không dùng URL **/ws/orders.wsdl** làm đích POST.

Trong môi trường nhiều client SOAP, chỉ định đúng **WebServiceTemplate** bằng tên bean hoặc **@Qualifier** khi có nhiều instance; không để Spring chọn nhầm client khác.

## 10. Xử lý Fault, validation và bảo mật

**SOAP Fault** là một phần của hợp đồng tích hợp, không tương đương việc server chỉ trả thông báo lỗi dạng văn bản. Phía client nên phân biệt:

| Tình huống | Biểu hiện và hướng xử lý |
| --- | --- |
| Sai namespace hoặc tên payload | Endpoint mapping không tìm thấy; so QName của phần tử gốc với XSD và **@PayloadRoot**. |
| Payload vi phạm XSD | Bật **PayloadValidatingInterceptor** để phát hiện sớm, trả lỗi phù hợp; so cấu trúc phần tử, thứ tự và kiểu dữ liệu. |
| Đơn hàng không tồn tại | Server trả SOAP Fault nghiệp vụ; client có thể nhận **SoapFaultClientException** và hiển thị thông điệp an toàn. |
| HTTP 401/403, 404, 502 hoặc lỗi kết nối | Kiểm tra xác thực, URL, proxy, TLS và timeout; không xử lý như lỗi dữ liệu đơn hàng. |
| Marshal/unmarshal lỗi | Đối chiếu phiên bản XSD, package JAXB, namespace, SOAP version và cấu hình marshaller. |

Trong Spring-WS, có thể dùng **PayloadValidatingInterceptor** để xác thực request và response theo XSD. Cấu hình interceptor với **ordersSchema**; đặt **validateRequest** và **validateResponse** theo yêu cầu rồi đăng ký qua **WsConfigurer#addInterceptors**. Bài kiểm thử tối thiểu cần có một request hợp lệ và ít nhất một request sai XSD. Việc JAXB đọc được XML không thay thế cho kiểm tra đầy đủ mọi ràng buộc schema.

Khi đưa SOAP ra môi trường doanh nghiệp, cần bổ sung:

- **HTTPS/TLS**, hostname verification và truststore tin cậy; không tắt kiểm tra chứng chỉ để xử lý lỗi kết nối.
- **WS-Security** (chẳng hạn UsernameToken hoặc XML Signature) khi hợp đồng yêu cầu tính xác thực, toàn vẹn thông điệp; cấu hình chứng chỉ/khóa ở nơi quản lý bí mật, xác minh chữ ký và replay protection theo chính sách.
- Timeout kết nối/đọc và retry có kiểm soát; thao tác không idempotent cần tránh gọi lặp gây nhân đôi giao dịch.
- Giới hạn kích thước XML, phòng chống XML External Entity (XXE), không ghi bí mật hay toàn bộ SOAP Header nhạy cảm vào log.
- Giám sát HTTP status, SOAP Fault code, correlation ID và thời gian xử lý. Khi có lỗi từ đối tác, lưu bản request/response đã loại dữ liệu nhạy cảm để tái hiện.

**Lưu ý:** SOAP trên HTTPS chỉ mã hóa kênh truyền; nó không tự tạo XML Signature hay đáp ứng yêu cầu WS-Security ở cấp thông điệp. Ngược lại, có WS-Security cũng không phải lý do bỏ TLS.

## 11. Kiểm thử tích hợp và khả năng tương thích

Một bài thực hành được xem là hoàn tất khi kiểm chứng **hợp đồng công bố**, **giao tiếp HTTP thực**, **JAXB mapping** và **hành vi lỗi**, chứ không chỉ chạy được phương thức Java trong endpoint.

| Kiểm thử | Thao tác | Kết quả cần đạt |
| --- | --- | --- |
| Công bố XSD | GET **/ws/ordersSchema.xsd** | HTTP 200, XML hợp lệ, đúng namespace và phần tử gốc. |
| Công bố WSDL | GET **/ws/orders.wsdl** | HTTP 200, có thao tác GetOrder và SOAP address có thể truy cập. |
| Happy path bằng cURL | POST request **ORD-1001** | SOAP Body chứa response và các trường đúng schema. |
| Client JAXB | Gọi **OrderSoapClient.getOrder("ORD-1001")** | Unmarshal được object với giá trị mong đợi. |
| Lỗi nghiệp vụ | POST mã đơn không tồn tại | SOAP Fault có mã lỗi phù hợp, không lộ stack trace. |
| Lỗi XML/namespace | POST payload bị sửa QName hoặc sai XSD | Server từ chối có kiểm soát; không âm thầm xử lý sai nghiệp vụ. |
| Tương thích đối tác | Import WSDL vào SOAP UI hoặc client công nghệ khác | Tạo được request hợp đồng và gọi thành công. |

Trong kiểm thử tự động, có thể dùng **spring-ws-test**: **MockWebServiceClient** để kiểm tra dispatch/response phía server và **MockWebServiceServer** để kiểm tra payload do client gửi, Fault và cách xử lý lỗi. Bổ sung một bài kiểm thử thực qua HTTP trên port ngẫu nhiên để xác minh servlet mapping, WSDL công bố và cấu hình mạng thực.

Một số lỗi thường gặp:

1. **GET WSDL 404:** kiểm tra tên bean **orders**, ánh xạ servlet **/ws/** và ứng dụng đã khởi động đúng port/context path.
2. **XSD 404:** kiểm tra tên bean **ordersSchema**, đường dẫn **ClassPathResource("xsd/orders.xsd")** và việc đóng gói resource.
3. **No endpoint mapping found:** so namespace URI và local name trong SOAP Body với **@PayloadRoot**; prefix XML khác nhau là bình thường.
4. **JAXBException / class not known to context:** kiểm tra **setContextPath**, version JAXB và việc plugin đã sinh/biên dịch các lớp từ XSD.
5. **WSDL trỏ host nội bộ:** kiểm tra proxy, forwarded headers, base URL của deployment và **setTransformWsdlLocations**.
6. **SOAP 415 hoặc không phân tích được Envelope:** so SOAP version, Content-Type, cấu hình message factory và HTTP body.
7. **Client nhận Fault hoặc timeout:** đọc SOAP Fault code/detail nếu có, kiểm tra log tương quan, TLS, firewall và timeout trước khi retry.

## 12. Bài tập mở rộng

1. Bổ sung **currency** và ràng buộc **orderId** trong XSD, sinh lại JAXB, chứng minh request cũ còn hoặc không còn tương thích theo đúng thay đổi đã chọn.
2. Tách server và client thành hai ứng dụng chạy trên hai port khác nhau; chỉ chia sẻ file XSD hoặc artifact contract. Dùng client tạo từ hợp đồng để gọi dịch vụ mà không import class endpoint.
3. Tạo một trường hợp SOAP Fault nghiệp vụ có **fault detail** được định nghĩa bằng XSD, viết kiểm thử kiểm tra Fault thay vì phụ thuộc vào chuỗi lỗi tự do.
4. Chạy server sau reverse proxy và cấu hình HTTPS; kiểm tra địa chỉ trong WSDL mà client bên ngoài thực sự nhìn thấy.
5. Dùng công cụ SOAP độc lập để import WSDL, sinh request, gọi dịch vụ và đối chiếu kết quả với **WebServiceTemplate**.

### Tự kiểm tra kiến thức

- Vì sao thay đổi tên Java method **getOrder** không đủ để đổi tên operation mà client SOAP nhìn thấy?
- **GetOrderRequest** khác **soap:Envelope** ở cấp cấu trúc và trách nhiệm nào?
- Vì sao WSDL mở được nhưng POST SOAP vẫn có thể trả 404, Fault hoặc lỗi unmarshalling?
- Tại sao URL namespace không cần trả nội dung web, trong khi URL WSDL/XSD cần truy cập được?
- Khi đối tác đổi XSD, phải kiểm tra điều gì trước khi sinh lại JAXB và triển khai phiên bản mới?

**Kết quả đầu ra cần nộp:** XSD làm nguồn hợp đồng, WSDL/XSD truy cập bằng HTTP, endpoint nhận đúng QName, request/response SOAP minh họa, Java client gọi được dịch vụ và bằng chứng kiểm thử cả luồng thành công lẫn SOAP Fault. Đây là chuỗi thao tác cơ bản của phát triển dịch vụ SOAP contract-first với Spring Web Services, JAXB và HTTP trong hệ thống tích hợp doanh nghiệp.
