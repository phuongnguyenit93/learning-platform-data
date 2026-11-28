# Cấu hình bằng Java và cấu hình XML trong hệ thống hiện hữu

## 1. Vì sao cần hiểu cả hai cách cấu hình máy chủ Spring-WS?

Spring Web Services (Spring-WS) xây dựng dịch vụ SOAP tập trung vào **hợp đồng XML**: XSD xác định cấu trúc request/response, WSDL mô tả operation và SOAP binding, còn Spring-WS tiếp nhận thông điệp qua `MessageDispatcherServlet` để chuyển đến `@Endpoint`. Trong các ứng dụng mới, cấu hình thường được viết bằng Java với `@Configuration`, `@Bean`, `@EnableWs` và `WsConfigurer`. Trong nhiều hệ thống doanh nghiệp đã vận hành lâu năm, cấu hình có thể nằm trong `web.xml`, các file Spring XML và những servlet context riêng.

Hai cách này phục vụ cùng một mục tiêu: **tạo đúng các bean, kết nối đúng SOAP dispatcher và công bố đúng hợp đồng**. Khác biệt lớn nằm ở nơi khai báo, cách tổ chức application context, cơ chế đóng gói/triển khai và phương pháp kiểm soát thay đổi.

Bài thuộc chương **Cấu hình máy chủ** của module **SPRING_WEB_SERVICES**. Nội dung bám sát hướng **contract-first**: dùng XSD/WSDL, JAXB/OXM, `@Endpoint`, interceptor, SOAP Fault và kiểm thử tương thích. Mục tiêu là hiểu một server Spring-WS thực sự được cấu thành như thế nào để có thể cấu hình ứng dụng mới, bảo trì ứng dụng XML hiện hữu hoặc chuyển đổi từng phần mà không làm gián đoạn SOAP client.

Sau bài học, bạn có thể:

- Trình bày vai trò của `MessageDispatcherServlet`, `@EnableWs`, `WsConfigurer`, `XsdSchema`, `Wsdl11Definition` và `@Endpoint`.
- Cấu hình một SOAP server tối thiểu bằng Java Config/Spring Boot.
- Đọc và duy trì cấu hình `web.xml` cùng `spring-ws-servlet.xml` trong ứng dụng WAR cũ.
- Biết cách liên kết schema, WSDL, SOAP version, JAXB và interceptors giữa hai mô hình.
- Nhận diện lỗi trùng bean, trùng servlet, sai application context, URL metadata sai hoặc SOAP binding không khớp runtime.
- Thiết kế kiểm thử để bảo vệ QName, WSDL/XSD, SOAP Fault và hành vi tích hợp khi thay cấu hình.

## 2. Các thành phần phải khớp nhau trong cả hai mô hình

Một dịch vụ SOAP Spring-WS điển hình gồm các phần:

| Thành phần | Nhiệm vụ | Cần kiểm tra |
|---|---|---|
| `MessageDispatcherServlet` | Nhận HTTP request/response SOAP, xử lý truy cập tài liệu WSDL/XSD khi được cấu hình | URL mapping, servlet context, đường dẫn công bố |
| SOAP message factory | Tạo và đọc SOAP message | SOAP 1.1/1.2, Content-Type, Envelope namespace |
| `@Endpoint` | Xử lý payload theo hợp đồng | `@PayloadRoot` QName, method signature, response |
| Annotation endpoint infrastructure | Phát hiện/định tuyến method `@Endpoint` | `@EnableWs` hoặc cấu hình XML tương ứng |
| `XsdSchema` | Đọc/đại diện một XML Schema | Namespace, import/include, đường dẫn resource |
| `DefaultWsdl11Definition` hoặc WSDL tĩnh | Công bố WSDL | Operation, binding, action, endpoint address |
| JAXB/OXM | Ánh xạ Java object và XML | Generated classes, `JAXBElement`, QName |
| `EndpointInterceptor` | Xử lý request/response/fault quanh endpoint | Thứ tự, validation, logging, security |
| Exception resolver | Chuyển exception thành SOAP Fault | Fault code, reason/string, detail và bảo mật |

Một chu trình xử lý khái quát:

~~~mermaid
flowchart TD
    A["HTTP SOAP client"] --> B["MessageDispatcherServlet"]
    B --> C["SOAP message factory"]
    C --> D["Header và interceptor"]
    D --> E["Payload QName / @PayloadRoot"]
    E --> F["JAXB unmarshal hoặc Source"]
    F --> G["Spring-WS @Endpoint"]
    G --> H["Application service"]
    H --> I["JAXB marshal response"]
    I --> J["SOAP response / SOAP Fault"]
    K["XSD + WSDL beans"] --> L["GET .xsd / .wsdl"]
    B --> L
~~~

Sơ đồ mô tả trách nhiệm, không ép tất cả interceptor hoặc mọi cách unmarshalling chạy đúng một thứ tự cố định. Framework, adapter, binding và cấu hình bảo mật quyết định pipeline chi tiết.

**Chìa khóa của contract-first:** Dù cấu hình bằng Java hay XML, request đến endpoint phải có **QName phần tử gốc trong SOAP Body** đúng XSD; response phải đúng WSDL và SOAP version đã công bố.

## 3. Một hợp đồng XSD tối giản dùng chung cho các ví dụ

Giả sử dịch vụ tra cứu đơn hàng công bố root elements `GetOrderRequest` và `GetOrderResponse` trong namespace `urn:example:orders:v1`. XSD tại `src/main/resources/xsd/orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
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
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Với anonymous complex types của ví dụ, JAXB/XJC thường có thể sinh các class `GetOrderRequest` và `GetOrderResponse` mang `@XmlRootElement`. Kết quả chính xác còn tùy công cụ và cấu hình binding. Nếu XSD dùng named complex types, XJC có thể sinh `GetOrderRequestType` cùng `ObjectFactory` trả `JAXBElement<GetOrderRequestType>` thay vì class root như ví dụ.

SOAP 1.1 request tương ứng:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

QName để Spring-WS định tuyến là:

~~~text
{urn:example:orders:v1}GetOrderRequest
~~~

Tên method Java có thể là `getOrder`, `findOrder` hoặc `lookupOrder`; bản thân tên method không thay thế QName từ contract.

## 4. Cấu hình Java: mô hình thường gặp với Spring Boot

Một dự án Spring Boot hiện đại có thể đăng ký servlet, schema, WSDL và interceptors bằng các bean Java. Cần dependency Spring-WS server, JAXB API/runtime và các thành phần phù hợp với phiên bản Spring Boot. Cấu hình ứng dụng thực tế có thể được Spring Boot tự động cung cấp một phần; khi chủ động đăng ký các bean như bên dưới, phải kiểm tra để tránh trùng hoặc xung đột với auto-configuration.

### 4.1. Đăng ký MessageDispatcherServlet

~~~java
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

@Configuration
public class SoapServletConfiguration {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
    messageDispatcherServlet(ApplicationContext applicationContext) {

        MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();

        servlet.setApplicationContext(applicationContext);
        servlet.setTransformWsdlLocations(true);

        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }
}
~~~

Trong ví dụ, servlet xử lý URL nằm dưới `/ws/*`. Nếu application có context path `/orders-app`, URL được phục vụ qua host sẽ có tiền tố context path đó. Nếu chạy sau gateway, URL bên ngoài có thể còn thêm phần đường dẫn được reverse proxy định tuyến.

**Cần phân biệt servlet mapping với SOAP operation.** `/ws/*` xác định request nào đến `MessageDispatcherServlet`; còn `@PayloadRoot` xác định method nào xử lý request sau khi SOAP Body được đọc.

Trong ứng dụng dùng Spring MVC đồng thời với SOAP, `DispatcherServlet` của MVC và `MessageDispatcherServlet` của Spring-WS phục vụ hai mục đích khác nhau. Đừng cấu hình cả hai nhận cùng URL một cách thiếu chủ đích.

### 4.2. Kích hoạt annotation-based endpoint

Một cấu hình thực tế sử dụng `@EnableWs` và `WsConfigurer`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;

@Configuration
@EnableWs
public class SoapEndpointConfiguration implements WsConfigurer {

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        // Đăng ký interceptor theo yêu cầu ở phần sau.
    }
}
~~~

`@EnableWs` kích hoạt hạ tầng cần thiết để sử dụng Spring-WS annotation endpoint; `WsConfigurer` cung cấp các hook cấu hình. Đây là mô hình nên ưu tiên trong code Java mới thay vì phụ thuộc vào các adapter cấu hình đời cũ có thể đã bị loại bỏ ở phiên bản Spring-WS gần đây.

Nếu cấu hình không có `@EnableWs` hoặc một cơ chế tương đương, việc chỉ viết `@Endpoint` có thể chưa đủ để framework định tuyến tới method mong muốn. Cần kiểm tra hạ tầng endpoint adapters và mappings thực tế, nhất là khi Spring Boot auto-configuration hoặc các library nội bộ đã thêm cấu hình.

### 4.3. Công bố XSD và WSDL bằng Java @Bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class OrdersContractConfiguration {

    @Bean(name = "ordersSchema")
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders-v1.xsd")
        );
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(
            XsdSchema ordersSchema) {

        DefaultWsdl11Definition definition =
            new DefaultWsdl11Definition();

        definition.setPortTypeName("OrdersPort");
        definition.setServiceName("OrdersService");
        definition.setLocationUri("/ws");
        definition.setTargetNamespace("urn:example:orders:v1");
        definition.setSchema(ordersSchema);

        return definition;
    }
}
~~~

Cấu hình trên giả định chỉ có một bean `XsdSchema`; nếu có nhiều schema trong application context, hãy dùng `@Qualifier("ordersSchema")` cho tham số `ordersWsdl`.

Khi servlet được cấu hình đúng và các bean nằm trong context có thể tìm kiếm, URL thường gặp:

~~~text
GET /ws/orders.wsdl
GET /ws/ordersSchema.xsd
~~~

Quy ước URL được xác định theo tên bean WSDL/XSD cùng servlet mapping. Tên file thực `orders-v1.xsd` trên classpath không tự quyết định URL công bố nếu bean tên `ordersSchema`.

**Đường dẫn URL và namespace là hai khái niệm khác nhau.** URL `/ws/ordersSchema.xsd` giúp client tải tài liệu. Namespace `urn:example:orders:v1` là định danh QName XML; không cần đổi namespace chỉ vì đổi URL tài liệu hoặc môi trường triển khai.

`DefaultWsdl11Definition` thường suy ra operation từ global element names dùng hậu tố `Request` và `Response`. Với ví dụ trên, nó có thể sinh operation `GetOrder`. Điều này phải được **kiểm tra trên WSDL thực tế**. Nếu hợp đồng đòi hỏi binding/fault/operation đặc thù, có thể công bố WSDL viết sẵn thay vì sinh động.

### 4.4. Định nghĩa một @Endpoint

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class GetOrderEndpoint {

    private static final String NS = "urn:example:orders:v1";

    private final OrderApplicationService orderService;

    public GetOrderEndpoint(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(request.getOrderId());
        response.setStatus(
            orderService.findStatus(request.getOrderId())
        );
        return response;
    }
}
~~~

Đây là mã minh họa, giả định XJC đã sinh các class có `@XmlRootElement` tương ứng và cấu hình JAXB endpoint processors phù hợp. Nếu XSD dùng named complex type và tạo `JAXBElement`, chữ ký method cần điều chỉnh theo binding thực tế, chẳng hạn `JAXBElement<GetOrderRequestType>` và `ObjectFactory.createGetOrderResponse(...)`.

Điểm quan trọng là phần **XSD/WSDL không phụ thuộc tên package hoặc service Java nội bộ**. Endpoint nên chuyển từ lớp SOAP binding sang application/domain service để những thay đổi bên trong không vô tình làm thay đổi contract XML của đối tác.

### 4.5. Kết nối JAXB/OXM ở tầng endpoint

Spring-WS hỗ trợ nhiều cách nhận dữ liệu: `Source`, DOM, JAXB/JAXBElement hoặc cơ chế marshalling được cấu hình thích hợp. Với binding sinh từ XSD, bạn có thể dùng `Jaxb2Marshaller` để cấu hình chuyển đổi XML–Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class SoapMarshallingConfiguration {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath(
            "com.example.orders.contract.v1"
        );
        return marshaller;
    }
}
~~~

`Jaxb2Marshaller` thường được dùng trực tiếp với `WebServiceTemplate`, các marshalling endpoint adapters hoặc cấu hình OXM khác. Việc **có bean này không mặc nhiên buộc mọi endpoint tự sử dụng nó**; cách chọn processor/adapter phụ thuộc cấu hình Spring-WS và kiểu tham số method. Với `@RequestPayload` có JAXB annotations phù hợp, annotation-based processors có thể sử dụng JAXB theo cơ chế riêng của framework.

Không nên vừa trông đợi một `Jaxb2Marshaller` bean hoạt động tự động theo mọi trường hợp, vừa không kiểm tra method signature và runtime thực tế.

## 5. Thêm interceptor và validation qua Java Config

Một dịch vụ SOAP contract-first thường cần kiểm tra XML request/response với XSD. Đây là trách nhiệm riêng với việc công bố XSD. Ví dụ cấu hình `PayloadValidatingInterceptor`:

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
public class SoapValidationConfiguration implements WsConfigurer {

    private final XsdSchema ordersSchema;

    public SoapValidationConfiguration(
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
        validator.setValidateResponse(true);
        interceptors.add(validator);
    }
}
~~~

Trong ví dụ Java Config này, có thể có **nhiều class implements `WsConfigurer`** cùng đóng góp vào cấu hình. Khi dự án bắt đầu phức tạp, nên tổ chức thứ tự interceptor rõ ràng và kiểm tra chúng có được thêm đúng một lần hay không.

Cần lưu ý:

- Nếu schema chỉ mô tả request mà không mô tả response, bật `validateResponse(true)` có thể khiến response bị báo không hợp lệ. XSD của ví dụ chứa cả hai.
- Nếu XSD gồm nhiều `xs:include`/`xs:import`, phải bảo đảm validator có thể phân giải tất cả dependency.
- Schema validation không kiểm tra khách hàng có quyền truy cập đơn hàng, chữ ký WS-Security có hợp lệ, hay certificate của đối tác có đáng tin hay không.
- Khi validation thất bại, ứng dụng cần có hành vi SOAP Fault phù hợp. Mã HTTP/Fault phụ thuộc phiên bản SOAP, cấu hình resolver và transport binding.

Nếu có WS-Security, việc xác thực chữ ký, token, chứng chỉ và mã hóa XML thường cần interceptor hoặc bộ xử lý bảo mật riêng, với thứ tự và chính sách phù hợp. Không thể coi `PayloadValidatingInterceptor` là thay thế cho security.

## 6. Cấu hình XML: mô hình phổ biến trong ứng dụng WAR hiện hữu

Một hệ thống Java doanh nghiệp cũ có thể sử dụng **Servlet container**, `web.xml` và Spring XML thay vì Spring Boot executable JAR. Cấu trúc thường gặp:

~~~text
legacy-order-service/
├── src/main/java/com/example/orders/soap/
│   └── GetOrderEndpoint.java
├── src/main/resources/xsd/
│   └── orders-v1.xsd
└── src/main/webapp/WEB-INF/
    ├── web.xml
    └── spring-ws-servlet.xml
~~~

Tệp `web.xml` đăng ký servlet và ánh xạ URL. Tệp `spring-ws-servlet.xml` tạo Spring bean: endpoint infrastructure, component scan, XSD, WSDL và interceptor.

Trong một ứng dụng đời cũ, cũng có thể xuất hiện `applicationContext.xml` ở **root context** và nhiều tệp XML con. Khi kiểm tra hệ thống hiện hữu, phải hiểu context nào sở hữu từng bean và servlet nào đang được phục vụ.

### 6.1. Đăng ký MessageDispatcherServlet trong web.xml

Ví dụ sử dụng cấu trúc Jakarta Servlet 6:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/jakartaee
        https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

    <servlet>
        <servlet-name>spring-ws</servlet-name>
        <servlet-class>
            org.springframework.ws.transport.http.MessageDispatcherServlet
        </servlet-class>

        <init-param>
            <param-name>transformWsdlLocations</param-name>
            <param-value>true</param-value>
        </init-param>

        <load-on-startup>1</load-on-startup>
    </servlet>

    <servlet-mapping>
        <servlet-name>spring-ws</servlet-name>
        <url-pattern>/ws/*</url-pattern>
    </servlet-mapping>
</web-app>
~~~

Đây là **ví dụ cho stack Jakarta mới** chạy trong Servlet container tương thích. Một ứng dụng Spring-WS/Servlet cũ dùng API `javax.servlet` có thể cần `web.xml` với namespace và phiên bản Servlet cũ, đồng thời dùng dependency Spring tương ứng. Không đổi namespace web.xml từ Java EE sang Jakarta chỉ bằng sửa văn bản nếu chưa nâng cấp framework/container.

Trong cấu hình servlet truyền thống, theo quy ước tên `spring-ws`, servlet tìm cấu hình con ở đường dẫn tương ứng kiểu:

~~~text
/WEB-INF/spring-ws-servlet.xml
~~~

Có thể thay vị trí hoặc danh sách file cấu hình bằng `contextConfigLocation` nếu cần. Phải kiểm tra giá trị thực tế trong web.xml trước khi kết luận bean nằm ở file nào.

### 6.2. Spring XML cấu hình endpoint và hợp đồng

Ví dụ tệp `/WEB-INF/spring-ws-servlet.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans
    xmlns="http://www.springframework.org/schema/beans"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:context="http://www.springframework.org/schema/context"
    xmlns:sws="http://www.springframework.org/schema/web-services"
    xsi:schemaLocation="
        http://www.springframework.org/schema/beans
        https://www.springframework.org/schema/beans/spring-beans.xsd
        http://www.springframework.org/schema/context
        https://www.springframework.org/schema/context/spring-context.xsd
        http://www.springframework.org/schema/web-services
        https://www.springframework.org/schema/web-services/web-services.xsd">

    <context:component-scan
        base-package="com.example.orders.soap"/>

    <sws:annotation-driven/>

    <bean id="ordersSchema"
          class="org.springframework.xml.xsd.SimpleXsdSchema">
        <constructor-arg
            value="classpath:xsd/orders-v1.xsd"/>
    </bean>

    <bean id="orders"
          class="org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition">
        <property name="portTypeName" value="OrdersPort"/>
        <property name="serviceName" value="OrdersService"/>
        <property name="locationUri" value="/ws"/>
        <property name="targetNamespace"
                  value="urn:example:orders:v1"/>
        <property name="schema" ref="ordersSchema"/>
    </bean>

    <sws:interceptors>
        <bean
            class="org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor">
            <property name="xsdSchema" ref="ordersSchema"/>
            <property name="validateRequest" value="true"/>
            <property name="validateResponse" value="true"/>
        </bean>
    </sws:interceptors>
</beans>
~~~

Ý nghĩa từng phần:

- `context:component-scan` phát hiện `@Endpoint` và các component trong package được chỉ định.
- `sws:annotation-driven` bật hạ tầng annotation endpoint phù hợp với Spring-WS XML namespace.
- Bean `ordersSchema` nạp XSD từ classpath.
- Bean `orders` dùng XSD để tạo WSDL có tên URL dựa trên bean.
- `sws:interceptors` đăng ký interceptor để kiểm tra payload theo XSD.

**Lưu ý về phiên bản:** Spring XML namespace và cấu hình annotation endpoint có thể thay đổi theo dòng Spring-WS cụ thể. Các ví dụ này minh họa cách cấu hình tiêu biểu; trước khi áp dụng vào sản phẩm đã vận hành, hãy đối chiếu API/dependency/schema XSD của framework thực tế.

### 6.3. Cách đọc lỗi XML configuration

Một tệp XML không hợp lệ có thể khiến ứng dụng không khởi động; ngoài lỗi chính tả thẻ, cần chú ý:

- Namespace `sws` trỏ nhầm URL hoặc thiếu mapping `xsi:schemaLocation`.
- Sai class FQCN sau nâng cấp Spring-WS.
- Constructor/property trong XML không còn tương thích với API của bean.
- `context:component-scan` không chứa package có `@Endpoint`.
- Spring application context nạp tệp XML khác với file mà người sửa đang xem.
- Có nhiều bean trùng tên hoặc cùng loại ở root và child contexts.
- Một cấu hình annotation-driven khác đã được kích hoạt thêm qua Java.

Trong hệ thống lâu năm, **đọc log khởi tạo servlet và application context** thường có giá trị hơn việc chỉ nhìn một file XML đơn lẻ.

## 7. So sánh Java Config và Spring XML

| Yếu tố | Java Config | Spring XML hiện hữu |
|---|---|---|
| Nơi khai báo | `@Configuration`, `@Bean`, `@EnableWs` | `web.xml`, `<bean>`, `<sws:annotation-driven/>` |
| Servlet mapping | `ServletRegistrationBean` hoặc cấu hình Java Servlet | `<servlet>` và `<servlet-mapping>` |
| Phát hiện endpoint | Component scan và Spring-WS annotation infrastructure | `context:component-scan` và Spring-WS XML namespace |
| XSD bean | Method trả `XsdSchema` | Bean `SimpleXsdSchema` và constructor resource |
| WSDL bean | Method trả `DefaultWsdl11Definition` | Bean `DefaultWsdl11Definition` với properties |
| Interceptor | `WsConfigurer.addInterceptors(...)` | `sws:interceptors` hoặc bean mapping tương ứng |
| Cách kiểm tra cấu hình | Java compile-time + runtime startup | XML parse/schema + bean binding + runtime startup |
| Tình huống thường gặp | Ứng dụng Spring Boot mới, Java-centric | Ứng dụng WAR và nền tảng Spring cũ |
| Khả năng dùng chung | Có thể `@ImportResource` khi cần | Có thể import XML khác hoặc dùng bean Java từ context phù hợp |

Java Config mang lại kiểm tra kiểu ở cấp code và dễ tái cấu trúc bằng IDE. XML thuận tiện khi hệ thống đã có hàng trăm bean, quy tắc triển khai và tệp cấu hình ổn định. **Mức độ hiện đại của cú pháp không quyết định chất lượng SOAP contract**: điều quan trọng vẫn là WSDL/XSD, QName và hành vi runtime.

## 8. Mapping các phần cấu hình tương đương

Đối chiếu những mục tiêu cụ thể giúp chuyển đổi từng phần dễ hơn:

| Mục đích | Java | XML |
|---|---|---|
| Kích hoạt SOAP annotation infrastructure | `@EnableWs` | `<sws:annotation-driven/>` |
| Khai báo XSD | `@Bean XsdSchema` | `<bean class="...SimpleXsdSchema">` |
| Khai báo WSDL động | `@Bean DefaultWsdl11Definition` | `<bean class="...DefaultWsdl11Definition">` |
| Đăng ký validation interceptor | `WsConfigurer.addInterceptors` | `<sws:interceptors>` |
| Quét `@Endpoint` | Component scan từ `@SpringBootApplication` hoặc `@ComponentScan` | `<context:component-scan>` |
| Đăng ký HTTP SOAP servlet | `ServletRegistrationBean<MessageDispatcherServlet>` | `web.xml` |
| Chỉnh URL SOAP address trong WSDL | `setTransformWsdlLocations(true)` | Servlet init-param `transformWsdlLocations` |
| Chọn SOAP message factory | Bean `messageFactory` cấu hình bằng Java | Bean `messageFactory` trong Spring XML |

Đây là **ánh xạ về trách nhiệm**, không phải lời khẳng định mọi thuộc tính trên hai phiên bản Spring-WS là một-một về runtime.

## 9. Cấu hình SOAP 1.1/1.2 ở server

Một thay đổi thường bị bỏ sót khi chuyển Java Config/XML là **SOAP version**. SOAP 1.1 và SOAP 1.2 khác namespace Envelope, HTTP Content-Type và cấu trúc SOAP Fault.

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
|---|---|---|
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| HTTP media type thường dùng | `text/xml` | `application/soap+xml` |
| HTTP action | `SOAPAction` header theo binding 1.1 | Tham số `action` tùy chọn của media type |
| Fault chính | `faultcode`, `faultstring` | `Code`, `Reason` |

### 9.1. Chọn version qua SaajSoapMessageFactory

Với một stack Spring-WS hỗ trợ `SaajSoapMessageFactory`, có thể tạo bean server tên `messageFactory`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Configuration
public class SoapVersionConfiguration {

    @Bean(name = "messageFactory")
    public SaajSoapMessageFactory messageFactory() {
        SaajSoapMessageFactory factory =
            new SaajSoapMessageFactory();

        factory.setSoapVersion(SoapVersion.SOAP_11);
        return factory;
    }
}
~~~

Nếu muốn SOAP 1.2, dùng `SoapVersion.SOAP_12` **trên server được cấu hình tương thích** và bảo đảm WSDL binding/client cũng hỗ trợ SOAP 1.2. `MessageDispatcherServlet` cần được kết nối đúng bean `messageFactory` mà bạn cấu hình.

Trong XML, có thể khai báo một bean cùng vai trò:

~~~xml
<bean id="messageFactory"
      class="org.springframework.ws.soap.saaj.SaajSoapMessageFactory">
    <property name="soapVersion">
        <util:constant
            static-field="org.springframework.ws.soap.SoapVersion.SOAP_11"/>
    </property>
</bean>
~~~

Đoạn XML này sử dụng prefix `util`, nên nếu tích hợp vào tệp ở phần 6 phải khai báo namespace `http://www.springframework.org/schema/util` và schema location của util; đây chỉ là trích đoạn minh họa, chưa phải tệp XML độc lập.

**Cảnh báo khi migration:** Việc đổi SOAP factory không tự chỉnh WSDL binding và không tự cho phép endpoint hỗ trợ đồng thời SOAP 1.1/1.2. Cần kiểm tra SOAP Envelope thực tế, media type và WSDL được công bố.

### 9.2. Nếu server đang chạy SOAP 1.1, đừng ép client gửi SOAP 1.2

Một request có:

~~~http
Content-Type: application/soap+xml; charset=utf-8
~~~

và Envelope SOAP 1.2 có thể bị server chỉ cấu hình SOAP 1.1 từ chối **trước khi đến `@Endpoint`**. Khi debug, kiểm tra response HTTP/Content-Type, log message factory và QName của SOAP Envelope.

Bởi vậy, smoke test phải gửi **SOAP request thật**; chỉ kiểm tra rằng `@Endpoint` bean tồn tại chưa đủ.

## 10. Application context trong hệ thống hiện hữu: nguồn lỗi phổ biến

Một ứng dụng Servlet truyền thống có thể có:

~~~text
ServletContext
├── Root WebApplicationContext
│   ├── orderApplicationService
│   ├── dataSource
│   └── security-related beans
└── MessageDispatcherServlet child WebApplicationContext
    ├── SOAP endpoint mapping
    ├── XsdSchema
    ├── Wsdl11Definition
    └── EndpointInterceptor
~~~

Thông thường child context có thể tìm các bean từ parent, nhưng bean trong child không tự động được parent nhìn thấy. Từ đó phát sinh lỗi:

- `@Endpoint` nằm ở package chưa được scan trong servlet child context.
- WSDL/XSD bean nằm ở context mà servlet không tìm kiếm đúng như kỳ vọng.
- OrderApplicationService được định nghĩa trong một context khác nhưng không được wire tới endpoint.
- Hai application contexts cùng tạo `orderApplicationService` hoặc `XsdSchema`, dẫn đến ambiguity, trạng thái không đồng nhất hoặc vòng đời bean không mong muốn.
- Có một `@EnableWs` ở root context nhưng SOAP servlet cần hạ tầng annotation mapping trong context khác.

Ví dụ một ứng dụng cũ có cả `ContextLoaderListener` và `MessageDispatcherServlet`:

~~~xml
<!-- web.xml trích đoạn minh họa root context -->
<context-param>
    <param-name>contextConfigLocation</param-name>
    <param-value>/WEB-INF/applicationContext.xml</param-value>
</context-param>

<listener>
    <listener-class>
        org.springframework.web.context.ContextLoaderListener
    </listener-class>
</listener>
~~~

Trong ứng dụng đó, tệp `applicationContext.xml` thường chứa bean tầng nghiệp vụ/infrastructure dùng chung, còn `spring-ws-servlet.xml` chứa SOAP-specific bean. Cần đặt các bean có chủ đích và kiểm tra dependency lookup thực tế.

Nếu dùng Java Config trong ứng dụng Boot, cách phân chia có thể khác: các bean thường nằm trong một ApplicationContext rộng hơn hoặc các context do Boot tạo. **Đừng mang nguyên giả định về root/child context của WAR sang Boot rồi suy ra bean sẽ tự tìm thấy nhau.**

## 11. Kết hợp XML và Java Config khi chưa thể chuyển đổi toàn bộ

Một hệ thống nhiều năm tuổi khó có thể thay tất cả `<bean>` thành `@Bean` trong một lần. Spring cho phép kết hợp hai hình thức trong phạm vi context phù hợp.

### 11.1. Import Spring XML từ Java

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportResource;

@Configuration
@ImportResource("classpath:/legacy/order-services.xml")
public class LegacyServicesImport {
}
~~~

Khi Java configuration được nạp, các bean trong `order-services.xml` cũng được import vào context đó. Cách này hữu ích nếu muốn giữ những bean application service cũ trong khi cấu hình SOAP servlet, XSD và WSDL bằng Java.

Tuy nhiên, **không import một tệp XML đang đăng ký lại SOAP infrastructure và servlet nếu Java Config đã đăng ký chúng**. Kiểm tra từng bean sẽ được tạo ở đâu và tại sao.

### 11.2. Đưa Java @Configuration vào ứng dụng XML

Một ứng dụng XML có thể quét package chứa class `@Configuration` hoặc đăng ký các class cấu hình qua cơ chế Spring phù hợp. Ví dụ XML:

~~~xml
<context:component-scan base-package="com.example.orders.config"/>
~~~

Nếu context này chưa có cấu hình annotation cần thiết, hãy kiểm tra cách bật annotation processing tương ứng. Nhưng trong migration, điểm chính là **không kích hoạt trùng hạ tầng SOAP**: cùng lúc có `<sws:annotation-driven/>`, `@EnableWs`, nhiều endpoint mappings hoặc nhiều adapter có thể gây thay đổi thứ tự xử lý.

### 11.3. Chiến lược chuyển đổi từng phần

Một tiến trình ít rủi ro:

1. **Đóng băng trạng thái hiện tại**: xuất WSDL/XSD và lưu SOAP fixtures của các client đang hoạt động.
2. **Lập sơ đồ cấu hình**: servlet nào nhận `/ws/*`, mỗi bean được tạo từ Java hay XML, thuộc context nào.
3. **Chuyển một nhóm bean mỗi lần**: ví dụ `XsdSchema`/WSDL bean trước, rồi interceptor; giữ nguyên QName, SOAP version và endpoint URL.
4. **So sánh contract và runtime** sau mỗi lần chuyển: XML fixtures, WSDL, XSD, SOAP Fault, response body.
5. **Loại bỏ cấu hình cũ đã bị thay thế** để không có bean trùng hoặc mapping mơ hồ.
6. **Giữ adapter và domain mapping tách biệt** để thay hình thức cấu hình không kéo theo đổi nghiệp vụ.

Đây là ví dụ về chuyển đổi có kiểm soát. Nếu có yêu cầu thay đổi lớn như từ Java EE `javax.*` sang Jakarta `jakarta.*`, cần coi đó là một nhánh migration riêng với kiểm tra binary compatibility, dependency và container.

## 12. Một tình huống migration có lỗi thực tế

Giả sử trước đây WAR chạy:

~~~text
/legacy-order/ws/orders.wsdl
/legacy-order/ws
~~~

và SOAP client gửi request có QName:

~~~text
{urn:example:orders:v1}GetOrderRequest
~~~

Nhóm chuyển sang Spring Boot và khai báo:

~~~java
new ServletRegistrationBean<>(servlet, "/soap/*");
~~~

nhưng `DefaultWsdl11Definition` vẫn dùng:

~~~java
definition.setLocationUri("/ws");
~~~

Kết quả: WSDL có thể còn công bố SOAP address `/ws` hoặc bị rewrite phụ thuộc cấu hình, trong khi servlet đang nhận `/soap/*`. SOAP client sinh từ WSDL mới có thể gửi sai URL.

Cách xử lý là thống nhất:

- Servlet mapping và endpoint URL thực tế.
- `setLocationUri(...)` và chính sách rewrite SOAP address.
- Context path của ứng dụng.
- Reverse proxy route.
- URL được client đã triển khai sử dụng hoặc kế hoạch redirect/migration nếu thay đổi endpoint là cần thiết.

**Đừng đổi namespace của XSD chỉ để giải quyết lỗi URL.** SOAP endpoint path là địa chỉ triển khai; namespace là danh tính của XML contract. Có thể giữ QName v1 và cung cấp một URL tương thích trong quá trình đổi hạ tầng.

## 13. Công bố WSDL/XSD và kiểm tra reverse proxy

Với Java Config hoặc XML, metadata phải tải được **từ môi trường của đối tác**, không chỉ từ máy chủ nội bộ.

Ví dụ:

~~~text
Server nội bộ:
http://orders-service:8080/ws/orders.wsdl

Đối tác truy cập:
https://soap.example.test/integration/ws/orders.wsdl
~~~

Các lỗi thường gặp:

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| `GET orders.wsdl` trả 404 | Tên bean, servlet mapping, context path |
| WSDL có `soap:address` nội bộ | `transformWsdlLocations`, forwarded headers, proxy |
| WSDL tải được nhưng XSD import trả 404 | Công bố XsdSchema phụ thuộc, schemaLocation tương đối |
| WSDL trả HTTP 200 nhưng body là HTML | Login/proxy/error page thay metadata |
| Client sinh mã không tìm thấy QName type | Namespace/import/include không nhất quán |
| Client gửi SOAP nhưng nhận 415 | Content-Type/SOAP version không đúng |
| Client gửi SOAP và nhận `No endpoint mapping` | QName Body không khớp `@PayloadRoot` |
| Response bị lỗi sau khi endpoint chạy | JAXB binding, XSD response, exception resolver |

`setTransformWsdlLocations(true)` giúp viết lại vị trí SOAP service trong WSDL dựa vào request, nhưng không được coi là giải pháp tự động cho mọi `xs:import`, `xs:include` hay proxy header. Khi cần rewrite `schemaLocation`, phải kiểm tra cơ chế mà phiên bản Spring-WS hiện tại hỗ trợ.

## 14. SOAP Fault và exception resolver trong hai kiểu cấu hình

Các exception phát sinh trong endpoint có thể được ánh xạ sang SOAP Fault qua `EndpointExceptionResolver` hoặc annotation/resolver tương ứng.

Ví dụ một exception nghiệp vụ có annotation Spring-WS:

~~~java
import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;

@SoapFault(
    faultCode = FaultCode.CLIENT,
    faultStringOrReason = "Yêu cầu tra cứu đơn hàng không hợp lệ"
)
public class InvalidOrderRequestException extends RuntimeException {

    public InvalidOrderRequestException(String message) {
        super(message);
    }
}
~~~

Để annotation này được xử lý, cần có `SoapFaultAnnotationExceptionResolver` hoặc hạ tầng exception resolver được cấu hình thích hợp với phiên bản Spring-WS. Khi dịch vụ dùng SOAP 1.1, mã lỗi phía gửi tương ứng `Client`; với SOAP 1.2 là `Sender`. Cấu trúc Fault và HTTP binding khác giữa hai phiên bản.

Trong Java Config, có thể đăng ký resolver bằng bean hoặc qua cấu hình framework tương ứng; trong XML, có thể khai báo một bean resolver hoặc sử dụng namespace/adapter mà hệ thống đang hỗ trợ. **Không nên giả định chỉ thêm `@SoapFault` vào exception là đủ trong mọi hệ thống cũ.**

Đối với lỗi XSD validation hoặc WS-Security, framework/interceptor có thể tạo Fault theo cơ chế riêng. Hãy kiểm tra hành vi bằng SOAP request thực. Tránh phát tán stack trace, access token, đường dẫn nội bộ hoặc thông tin certificate nhạy cảm trong Fault Detail.

## 15. Cấu hình bảo mật và logging cần đặt ở đúng lớp

Khi vận hành hệ thống SOAP doanh nghiệp, có nhiều lớp liên quan:

- **HTTP/TLS**: máy chủ/proxy xử lý HTTPS, truststore/keystore và chính sách xác thực vận chuyển.
- **SOAP WS-Security**: token, chữ ký, encryption và certificate validation nằm ở message security interceptor/pipeline.
- **XML parser security**: kiểm soát DTD, external entities, external schema resolution và giới hạn tài nguyên.
- **Schema validation**: kiểm tra XML hợp XSD.
- **Domain authorization**: kiểm tra quyền truy cập nghiệp vụ sau khi đã nhận dạng người gọi.

Thứ tự thực thi các interceptor có thể ảnh hưởng hành vi. Ví dụ, nếu request phải được xác thực chữ ký trước khi log thông tin payload nhạy cảm, cần cấu hình logger và bảo mật tương ứng. Không có một thứ tự duy nhất đúng cho mọi hệ thống; hãy định nghĩa từ threat model, công cụ WS-Security và chính sách xử lý fault, rồi kiểm thử.

Trong hệ thống XML cũ, logging interceptors có thể đã được đăng ký ở một tệp khác hoặc context khác. Khi chuyển sang Java Config, cần tránh **đăng ký hai lần** khiến cùng SOAP payload bị log lặp, hoặc vô tình log thông tin bảo mật mà trước đây đã được che.

## 16. Kiểm thử cấu hình bằng SOAP thật

Để biết cấu hình có hoạt động, không nên chỉ kiểm tra Spring context khởi tạo thành công. Cần xác minh metadata và request/response.

### 16.1. Kiểm tra WSDL/XSD qua HTTP

Ví dụ kiểm tra:

~~~bash
curl -i "https://api.example.test/ws/orders.wsdl"
curl -i "https://api.example.test/ws/ordersSchema.xsd"
~~~

Đây là lệnh mẫu để người học chạy trong môi trường phù hợp; bài này không thực thi các URL ví dụ. Cần xem cả HTTP status, `Content-Type`, body XML thực tế, các import/include và SOAP address công bố.

### 16.2. Gửi một SOAP 1.1 request hợp lệ

Ví dụ:

~~~bash
curl -i -X POST "https://api.example.test/ws" \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: ""' \
  --data-binary @get-order-soap11.xml
~~~

Ví dụ này giả định WSDL/binding hiện tại chấp nhận SOAP 1.1 với `SOAPAction` rỗng. **Nếu WSDL yêu cầu action cụ thể, phải dùng đúng action đó**. Tệp `get-order-soap11.xml` là fixture kiểm thử do người học chuẩn bị; không phải tài nguyên được tạo tự động bởi đoạn lệnh.

Kỳ vọng:

- HTTP request đến đúng servlet mapping.
- SOAP Envelope dùng namespace SOAP 1.1.
- Body chứa `{urn:example:orders:v1}GetOrderRequest`.
- `@Endpoint` được chọn.
- JAXB trả đúng dữ liệu request và response.
- Response SOAP Body chứa `GetOrderResponse` theo XSD.

### 16.3. Gửi request vi phạm schema

Ví dụ payload bỏ `orderId`:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderRequest/>
    </soap:Body>
</soap:Envelope>
~~~

Với interceptor XSD validation đã bật, cần kiểm tra request bị từ chối đúng và service nghiệp vụ **không xử lý dữ liệu thiếu**. Xác nhận SOAP Fault, HTTP status, nội dung lỗi và logging theo chính sách.

### 16.4. Kiểm thử endpoint mà không cần server HTTP thật

Spring-WS có hỗ trợ kiểm thử endpoint với `MockWebServiceClient` trong thư viện `spring-ws-test`. Ví dụ skeleton:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import javax.xml.transform.Source;
import javax.xml.transform.stream.StreamSource;

import java.io.StringReader;

import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;

public class EndpointContractTest {

    private final MockWebServiceClient client;

    public EndpointContractTest(ApplicationContext context) {
        this.client = MockWebServiceClient.createClient(context);
    }

    public void verifiesGetOrder() {
        Source request = new StreamSource(
            new StringReader(
                "<ord:GetOrderRequest " +
                "xmlns:ord=\"urn:example:orders:v1\">" +
                "<ord:orderId>ORD-1001</ord:orderId>" +
                "</ord:GetOrderRequest>"
            )
        );

        Source expectedResponse = new StreamSource(
            new StringReader(
                "<ord:GetOrderResponse " +
                "xmlns:ord=\"urn:example:orders:v1\">" +
                "<ord:orderId>ORD-1001</ord:orderId>" +
                "<ord:status>PAID</ord:status>" +
                "</ord:GetOrderResponse>"
            )
        );

        client.sendRequest(withPayload(request))
            .andExpect(payload(expectedResponse));
    }
}
~~~

Đây là skeleton minh họa cách dùng test DSL, **chưa phải JUnit test chạy độc lập**: dự án cần cấu hình ApplicationContext, dependency `spring-ws-test` và stub/mocking `OrderApplicationService` trả `PAID`. Thư viện cung cấp những matcher khác để kiểm tra SOAP Fault; chọn matcher phù hợp với lỗi đang kiểm thử.

Test bằng `MockWebServiceClient` kiểm tra hạ tầng Spring-WS/endpoint trong application context mà không cần HTTP transport thật. Nó **không thay thế** việc kiểm tra servlet mapping, proxy, Content-Type và địa chỉ WSDL/XSD từ phía client bên ngoài.

### 16.5. Bộ regression tối thiểu trước khi đổi Java/XML config

| Ca | Kỳ vọng |
|---|---|
| Khởi tạo application context | Không thiếu bean, không ambiguous mapping |
| GET WSDL | Trả hợp đồng chứa operation/binding đúng |
| GET XSD | Tài liệu và import/include tải được |
| SOAP request hợp lệ | Đến đúng endpoint, response hợp XSD |
| SOAP request thiếu required field | Validation/Fault đúng; không gọi nghiệp vụ |
| SOAP request sai namespace | Không bị xử lý như QName hợp lệ |
| Sai SOAP version/media type | Bị từ chối phù hợp cấu hình |
| Lỗi nghiệp vụ | Fault không lộ dữ liệu nội bộ |
| Client JAXB/.NET độc lập | Sinh mã/đọc request-response theo contract |
| Bản cũ và bản mới | WSDL/XSD/QName và behavior đã cam kết không đổi |

## 17. Một kế hoạch kiểm tra khi chuyển từ XML sang Java Config

Khi phải nâng cấp một ứng dụng WAR hiện hữu, hãy thực hiện các bước có thể review được:

1. **Vẽ bản đồ bean hiện tại:** Xác định root/servlet contexts, location của `web.xml`, các file XML, message factory, endpoint mapping, interceptor và exception resolver.
2. **Ghi lại public contract:** Tải WSDL/XSD từ URL hiện tại, chốt namespace, SOAP version, binding, action và các sample request/response.
3. **Chọn phạm vi chuyển đổi:** Chuyển nhóm cấu hình rõ ràng, ví dụ XSD/WSDL trước, sau đó interceptor, rồi servlet registration nếu thay deployment model.
4. **Giữ nguyên behavior công khai:** Giữ QName, XSD constraints, operation và Fault trừ khi có một thay đổi contract được quản lý riêng.
5. **Chạy regression theo từng lớp:** Context startup, metadata GET, SOAP request/response, negative validation, client độc lập.
6. **Kiểm tra triển khai thật:** context path, proxy, TLS, forwarded headers, auth, log và metrics.
7. **Loại bỏ bean/mapping cũ đã thay thế:** Tránh duplicate servlet, interceptor hoặc endpoint mapping.
8. **Có rollback thực tế:** Giữ bản artifact và cấu hình trước migration để có thể phục hồi nếu các client doanh nghiệp gặp lỗi sau deploy.

Không nên đánh đồng “build và start thành công” với “cấu hình SOAP tương thích”. Client chỉ nhìn thấy WSDL, SOAP Envelope, URL, response và Fault; đây mới là các điều cần bảo vệ bằng kiểm thử.

## 18. Câu hỏi phân tích tình huống

Giả sử ứng dụng cũ có:

~~~text
web.xml:
    servlet-name = spring-ws
    url-pattern  = /ws/*

spring-ws-servlet.xml:
    orders WSDL bean
    ordersSchema XSD bean
    <sws:annotation-driven/>
    PayloadValidatingInterceptor
~~~

Sau khi chuyển sang Spring Boot, nhóm thêm `@EnableWs`, khai báo `MessageDispatcherServlet` map `/soap/*`, giữ `DefaultWsdl11Definition.locationUri="/ws"` và chuyển JAXB package. Ứng dụng khởi động thành công nhưng client nhận 404, 415 hoặc SOAP Fault.

Hãy phân tích theo lớp:

- **404:** Client POST/GET đúng URL public chưa? Mapping servlet và context path có đổi không?
- **415:** Content-Type và SOAP message factory có cùng phiên bản SOAP không?
- **No endpoint mapping:** QName request có đúng `@PayloadRoot` không?
- **Marshal/unmarshal error:** Binding JAXB có đúng namespace/ObjectFactory/`@XmlRootElement` không?
- **Fault/validation thay đổi:** Interceptor, exception resolver và XML schema đang nằm ở context nào?
- **WSDL không nhất quán:** Location URI, SOAP binding và WSDL generator có công bố cùng hành vi runtime không?

Sau đó, lập một bảng so sánh **trước/sau** gồm URL, QName, SOAP version, action, XSD, Fault và security policy. Chỉ công bố migration tương thích khi các ca kiểm thử thực tế chứng minh điều đó.

## 19. Checklist cấu hình server Spring-WS

- [ ] Đã xác định duy nhất servlet nhận SOAP request và URL mapping chính xác.
- [ ] `@EnableWs` hoặc `<sws:annotation-driven/>` được cấu hình tại context phù hợp.
- [ ] `@Endpoint` được component scan và có `@PayloadRoot` khớp QName của XSD.
- [ ] XSD/WSDL bean được đăng ký trong context mà `MessageDispatcherServlet` nhìn thấy.
- [ ] WSDL công bố đúng operation, SOAP version, binding và địa chỉ endpoint.
- [ ] JAXB binding, `Jaxb2Marshaller`/endpoint processors và schema đồng bộ.
- [ ] `PayloadValidatingInterceptor` có đúng schema request/response và dependency.
- [ ] SOAP Fault và exception resolver được kiểm thử cho dữ liệu lỗi.
- [ ] Security interceptor, TLS, WS-Security, chứng chỉ và parser security được cấu hình riêng đúng chính sách.
- [ ] Không có servlet, endpoint mapping, message factory hoặc interceptor bị đăng ký trùng do Java/XML cùng tồn tại.
- [ ] Reverse proxy/HTTPS không làm sai `soap:address`, URL XSD hoặc schema import.
- [ ] Đã kiểm thử bằng SOAP client độc lập trước khi đưa thay đổi cấu hình vào sản xuất.

## 20. Ghi nhớ

- **Java Config và Spring XML là hai cách khai báo cùng các trách nhiệm của Spring-WS**: servlet, XSD/WSDL, endpoint, JAXB, interceptor và Fault resolver.
- **`MessageDispatcherServlet` nhận HTTP SOAP**, còn **`@PayloadRoot` định tuyến SOAP Body theo QName**.
- **`@EnableWs` và `<sws:annotation-driven/>` hỗ trợ hạ tầng annotation endpoint**, nhưng phải kiểm tra context và tránh kích hoạt trùng.
- **Bean XsdSchema/WSDL không tự bảo đảm runtime hợp contract**; cần validation, SOAP integration tests và interoperability tests.
- **Trong ứng dụng WAR cũ, root context và servlet child context là nguồn lỗi cấu hình phổ biến.**
- **Chuyển từ XML sang Java Config không cần đổi QName/WSDL/XSD** nếu chỉ thay cơ chế wiring nội bộ. Đổi SOAP version, namespace hoặc URL public phải được đánh giá tác động đối tác.

**Câu hỏi tự kiểm tra:** Một ứng dụng cũ dùng `web.xml` và `spring-ws-servlet.xml` hoạt động bình thường. Sau khi chuyển sang Java Config, WSDL vẫn tải được nhưng `POST /ws` không đến endpoint và validator không chạy. Bạn sẽ kiểm tra thứ tự nào giữa servlet mapping, application context, `@EnableWs`, component scan, `@PayloadRoot` và `WsConfigurer`? Nêu cách xác minh để không phải đoán từ một tệp cấu hình đơn lẻ.

