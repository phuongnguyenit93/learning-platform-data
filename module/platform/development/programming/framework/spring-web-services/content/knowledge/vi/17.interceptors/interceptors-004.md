# Đăng ký interceptor qua WsConfigurer và cấu hình XML

## 1. Đặt vấn đề: interceptor phải được đưa vào đúng chuỗi xử lý

Trong **Spring Web Services (Spring-WS)**, dịch vụ SOAP được xây dựng theo hướng **contract-first** thường dựa vào XSD/WSDL để quy định XML trao đổi, JAXB để ánh xạ kiểu dữ liệu và `@Endpoint` để thực hiện nghiệp vụ. Bên cạnh code endpoint, ứng dụng còn cần các công việc dùng chung: xác thực payload theo XSD, kiểm tra WS-Security, ghi nhận thời gian xử lý, kiểm soát SOAP Fault và quan sát giao tiếp với hệ thống đối tác.

**`EndpointInterceptor`** là điểm mở rộng ở phía **SOAP server** cho các công việc đó. Tuy nhiên, viết một class implements `EndpointInterceptor` hoặc khai báo một bean interceptor **chưa đủ**: bean phải được **đăng ký vào chuỗi interceptor của Spring-WS**. Hai cách cấu hình thường gặp là:

1. **Java configuration:** triển khai `WsConfigurer`, override `addInterceptors(...)` và sử dụng `@EnableWs`.
2. **Spring XML configuration:** dùng namespace `sws` với `<sws:annotation-driven/>` và `<sws:interceptors>`.

Bài học thuộc chương **Interceptor**, trình bày hai cách đăng ký đó, khi nào chọn mỗi cách, vòng đời và thứ tự thực thi interceptor, cách gắn XSD validation, liên hệ với SOAP client, WS-Security, SOAP Fault và các phép kiểm thử cần có để tích hợp doanh nghiệp ổn định.

**Điểm cần nhớ ngay:** interceptor server thuộc **luồng xử lý SOAP message sau khi hạ tầng nhận thông điệp**, không tương đương với Servlet Filter, Spring MVC `HandlerInterceptor` hay client-side `ClientInterceptor`.

## 2. Vị trí của interceptor trong kiến trúc Spring-WS

~~~mermaid
flowchart TD
    A["SOAP client / HTTP(S)"] --> B["Reverse proxy / Servlet container"]
    B --> C["MessageDispatcherServlet"]
    C --> D["WebServiceMessageFactory"]
    D --> E["MessageDispatcher + EndpointMapping"]
    E --> F["EndpointInterceptor chain"]
    F --> G{"Cho phép xử lý?"}
    G -- "Có" --> H["EndpointAdapter"]
    H --> I["@Endpoint / nghiệp vụ"]
    I --> J["Tạo SOAP response"]
    J --> K["Interceptor xử lý response / fault"]
    K --> L["Gửi thông điệp cho client"]
    G -- "Không" --> M["Dừng chuỗi; phản hồi theo cấu hình"]
    M --> L
~~~

Đây là sơ đồ tổng quan, **không phải cam kết mọi callback sẽ chạy trong mọi trường hợp lỗi**. Việc một interceptor có được gọi hay không còn phụ thuộc endpoint đã được map thành công chưa, interceptor đứng ở vị trí nào trong chain và cách dispatcher/resolver hoàn thành xử lý.

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| `MessageDispatcherServlet` | Điểm vào HTTP của Spring-WS | Servlet map `/ws/*` |
| `EndpointMapping` | Chọn endpoint theo nội dung thông điệp hoặc action | `@PayloadRoot`, `@SoapAction` |
| **`EndpointInterceptor`** | Xử lý chéo trước/sau endpoint và khi có Fault | Validation, tracing, kiểm tra policy |
| `EndpointAdapter` | Gọi phương thức endpoint tương ứng | `@RequestPayload` → Java method |
| `EndpointExceptionResolver` | Chuyển một số ngoại lệ sang phản hồi phù hợp | SOAP Fault mapping |
| `ClientInterceptor` | Can thiệp SOAP client ở `WebServiceTemplate` | Thêm header, kiểm tra phản hồi đối tác |

**Một endpoint được phát hiện đúng không đồng nghĩa interceptor đã được gắn.** Đối tượng `EndpointInterceptor` phải tham gia cấu hình endpoint mapping của đúng Spring application context.

### 2.1. HTTP URL và SOAP mapping khác nhau

Ví dụ request đi vào `http://localhost:8080/ws/orders`, nhưng Spring-WS chọn phương thức theo root QName `{urn:example:orders:v1}GetOrderRequest`. Nếu HTTP URL sai, request có thể bị chặn ở Servlet container **trước khi bất kỳ EndpointInterceptor nào hoạt động**. Nếu root QName không có endpoint phù hợp, có thể không tồn tại một chain interceptor gắn với endpoint để chạy.

Vì vậy **không dùng interceptor endpoint làm biện pháp duy nhất** để phòng thủ lỗi ở tầng HTTP, hạn chế kích thước request hay bảo vệ XML parser khỏi XXE trước khi parse. Các lớp bảo vệ HTTP/TLS/parser phải được thiết lập riêng.

## 3. Bốn callback của `EndpointInterceptor`

Interface `org.springframework.ws.server.EndpointInterceptor` có bốn callback cốt lõi:

| Callback | Thời điểm và mục đích | Giá trị trả về |
| --- | --- | --- |
| `handleRequest(MessageContext, Object)` | Xử lý request sau khi endpoint được xác định | `true` để cho phép xử lý tiếp; `false` để dừng |
| `handleResponse(MessageContext, Object)` | Xử lý response trong đường thành công tương ứng | `true` để cho phép xử lý tiếp; `false` để dừng |
| `handleFault(MessageContext, Object)` | Xử lý response SOAP Fault khi luồng xử lý tạo Fault | `true` hoặc `false` |
| `afterCompletion(MessageContext, Object, Exception)` | Dọn tài nguyên và quan sát khi xử lý endpoint hoàn thành theo quy tắc dispatcher | `void` |

`MessageContext` giữ thông điệp request/response và các thuộc tính của một lần xử lý. Nó **không phải SOAP Envelope**. Có thể lấy `context.getRequest()` rồi kiểm tra `instanceof SoapMessage` khi cần đọc action hoặc header đặc thù SOAP.

### 3.1. Ý nghĩa của `true` và `false`

Trong `handleRequest`, trả `true` thông thường cho phép dispatcher tiếp tục sang các bước còn lại. Trả `false` có thể ngăn endpoint được gọi. Tuy nhiên **trả `false` không tự bảo đảm đã tạo một SOAP Fault đúng hợp đồng**. Một interceptor muốn chặn request phải có cơ chế phản hồi rõ ràng; không để client nhận response không hoàn chỉnh hoặc im lặng không lý do.

Tương tự, `handleResponse`/`handleFault` có thể ảnh hưởng quá trình tiếp tục xử lý chain, nên cần kiểm thử khi tùy chỉnh. Không nên lạm dụng `return false` trong interceptor đo thời gian hoặc ghi log đơn thuần.

### 3.2. Không giả định mọi callback đều luôn chạy

Một vài ví dụ:

- Lỗi DNS hoặc TLS xảy ra trước HTTP: interceptor server không chạy.
- HTTP URL không tới SOAP servlet: interceptor không chạy.
- SOAP XML sai nghiêm trọng khiến message factory không đọc được: có thể chưa chọn endpoint.
- Endpoint mapping không tìm thấy handler: các interceptor gắn với endpoint có thể không được gọi.
- Interceptor phía trước trả `false`: các interceptor phía sau và endpoint không nhất thiết được gọi.
- Endpoint tạo SOAP Fault: `handleFault` có thể tham gia tùy cách dispatcher xử lý.

Nếu cần một việc **luôn xảy ra cho mọi HTTP request**, kể cả request không được map vào SOAP endpoint, hãy xem xét cơ chế tầng HTTP như filter/gateway, không mặc định `EndpointInterceptor` bao phủ toàn bộ.

## 4. Ví dụ xuyên suốt: hợp đồng OrderService

Để minh họa hai phương án đăng ký, ta dùng cùng một XSD tại `src/main/resources/xsd/orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:pattern value="ORD-[0-9]{4,12}"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId"
                            type="tns:OrderIdType"/>
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

XML request hợp đồng:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>ORD-1001</o:orderId>
</o:GetOrderRequest>
~~~

Một request **có đúng root QName nhưng sai schema**:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>INVALID</o:orderId>
</o:GetOrderRequest>
~~~

Chuỗi `INVALID` vi phạm `xs:pattern`. Đây là test quan trọng: nếu root QName đúng, endpoint mapping có thể xác định handler, còn validator mới chứng minh việc kiểm tra cấu trúc đang hoạt động.

### 4.1. Endpoint minh họa

~~~java
package example.orders.ws;

import javax.xml.transform.Source;
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
    public Source getOrder(@RequestPayload Source request) {
        // Ví dụ kiểm tra pipeline; chưa triển khai nghiệp vụ thực.
        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>FOUND</o:status>" +
                "</o:GetOrderResponse>");
    }
}
~~~

`@PayloadRoot` chọn handler theo QName phần tử gốc trong SOAP Body. Endpoint ví dụ cố ý trả status cố định để tập trung vào **cấu hình interceptor**; không dùng nó như bằng chứng đã kiểm tra tồn tại đơn hàng, quyền truy cập hoặc lỗi nghiệp vụ.

## 5. Một interceptor tự viết: đo thời gian xử lý an toàn luồng

Vì interceptor thường được Spring quản lý như **singleton**, không được lưu dữ liệu riêng của request trong field mutable dùng chung:

~~~java
// SAI: biến field có thể bị ghi đè bởi các request song song.
private long startNanos;
~~~

Thay vào đó, có thể lưu timestamp vào `MessageContext` thuộc từng lần xử lý:

~~~java
package example.orders.ws;

import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;

public final class RequestTimingInterceptor
        implements EndpointInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(RequestTimingInterceptor.class);

    private static final String START_NANOS =
            RequestTimingInterceptor.class.getName() + ".startNanos";

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint) {
        context.setProperty(START_NANOS, System.nanoTime());
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        Object value = context.getProperty(START_NANOS);
        if (value instanceof Long) {
            long elapsedNanos =
                    System.nanoTime() - ((Long) value).longValue();
            long elapsedMillis =
                    TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
            log.info(
                    "SOAP endpoint completion: elapsedMs={}, exception={}",
                    elapsedMillis,
                    ex != null);
        }
    }
}
~~~

Đây là một implementation **stateless ở phạm vi singleton**. Trạng thái đo thời gian nằm trong `MessageContext`, không chia sẻ giữa các request. `System.nanoTime()` thích hợp để đo khoảng thời gian trôi qua, không dùng làm timestamp lịch.

Lưu ý: log ở `afterCompletion` chỉ bao phủ những đường xử lý mà callback đó thực sự được gọi; nó **không phải** metric của mọi HTTP request thất bại trước endpoint mapping. Để đo end-to-end ở tầng HTTP, dùng thêm filter, metrics hoặc gateway instrumentation.

### 5.1. Vì sao không dump toàn bộ SOAP message?

SOAP Header có thể chứa token, chữ ký, timestamp WS-Security; Body có thể chứa PII, số tài khoản hoặc dữ liệu thanh toán. Với production, ưu tiên metadata đã được cho phép như correlation ID, operation, kết quả xử lý, thời gian và Fault code. Không bật log toàn bộ request/response chỉ để chứng minh interceptor hoạt động.

## 6. Phương án A: đăng ký qua `WsConfigurer` và Java configuration

Trong ứng dụng dùng Spring Java configuration, `@EnableWs` kích hoạt hạ tầng Spring-WS annotation-driven; `WsConfigurer` cung cấp hook `addInterceptors(...)` để bổ sung các `EndpointInterceptor`.

Giả sử dự án Spring Boot đã có dependency `spring-boot-starter-web-services`, một Servlet mapping hoạt động và các class dưới package `example.orders.ws` được component-scan. Ta tách cấu hình thành:

1. Bean XSD/WSDL và `@EnableWs`.
2. Bean interceptor.
3. `WsConfigurer` đăng ký interceptor theo thứ tự có chủ đích.

Việc tách lớp giúp tránh khởi tạo cấu hình theo cách gây phụ thuộc vòng tròn và làm rõ **bean tồn tại** khác với **bean đã nằm trong chain**.

### 6.1. Cấu hình XSD/WSDL

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
        definition.setTargetNamespace("urn:example:orders:v1");
        definition.setLocationUri("/ws/orders");
        definition.setSchema(schema);
        definition.setCreateSoap11Binding(true);
        definition.setCreateSoap12Binding(false);
        return definition;
    }
}
~~~

Trong ví dụ Spring Boot có cấu hình SOAP servlet mapping `/ws/*`, WSDL bean tên `orders` thường được công bố tại `/ws/orders.wsdl`; SOAP request POST đến địa chỉ khớp `/ws/orders`. Phải kiểm tra mapping thực tế, nhất là khi có reverse proxy/context path.

**XSD bean có thể phục vụ hai mục đích khác nhau:** dùng để sinh WSDL và dùng để validation. Chỉ khai báo `ordersSchema` hoặc WSDL **không tự bật validation**.

### 6.2. Khai báo bean validator và timing interceptor

~~~java
package example.orders.ws;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class InterceptorBeansConfig {

    @Bean("requestTimingInterceptor")
    public RequestTimingInterceptor requestTimingInterceptor() {
        return new RequestTimingInterceptor();
    }

    @Bean("ordersPayloadValidator")
    public PayloadValidatingInterceptor ordersPayloadValidator(
            @Qualifier("ordersSchema") XsdSchema schema) {
        PayloadValidatingInterceptor interceptor =
                new PayloadValidatingInterceptor();
        interceptor.setXsdSchema(schema);
        interceptor.setValidateRequest(true);
        interceptor.setValidateResponse(false);
        return interceptor;
    }
}
~~~

`PayloadValidatingInterceptor` kiểm tra payload theo XSD khi interceptor được đăng ký vào chain. `setValidateRequest(true)` yêu cầu kiểm tra request; `setValidateResponse(false)` giữ response validation tắt trong bước khởi tạo để tập trung vào request. Với hợp đồng đầy đủ, có thể bật response validation khi đã kiểm thử cách xử lý response sai schema.

### 6.3. Đăng ký interceptor trong `WsConfigurer`

~~~java
package example.orders.ws;

import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

@Configuration
public class OrderWsInterceptorConfig implements WsConfigurer {

    private final RequestTimingInterceptor timing;
    private final PayloadValidatingInterceptor validator;

    public OrderWsInterceptorConfig(
            @Qualifier("requestTimingInterceptor")
            RequestTimingInterceptor timing,
            @Qualifier("ordersPayloadValidator")
            PayloadValidatingInterceptor validator) {
        this.timing = timing;
        this.validator = validator;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(timing);
        interceptors.add(validator);
    }
}
~~~

**Dòng quyết định chính là `interceptors.add(...)`.** Nếu chỉ tạo hai `@Bean` ở mục 6.2 mà không đưa vào chain, bạn chưa có cơ sở kết luận các request đang được timing/validate.

Với cấu hình này:

- `@EnableWs` kích hoạt hạ tầng mapping/adapter và cơ chế tích hợp `WsConfigurer` trong context.
- `@Configuration` đưa `OrderWsInterceptorConfig` vào Spring context khi được component-scan.
- Constructor injection chọn chính xác hai bean qua `@Qualifier`.
- `addInterceptors` bổ sung interceptor theo thứ tự được viết ra.
- Cùng một `ordersSchema` được dùng để công bố WSDL và xác thực request.

**Cần tránh cấu hình trùng:** đừng đồng thời tạo các endpoint mapping khác bằng tay với interceptor list riêng nhưng lại kỳ vọng mọi request đi qua list do `WsConfigurer` cấu hình. Nếu dùng custom `EndpointMapping`, phải kiểm tra cơ chế interceptor thực sự của mapping đó.

## 7. Phương án B: đăng ký bằng cấu hình Spring XML

Một ứng dụng Spring truyền thống, thường đóng gói WAR, có thể dùng Spring bean XML và namespace `sws` thay vì `@EnableWs` + `WsConfigurer`. Các endpoint Java vẫn có thể dùng `@Endpoint` và `@PayloadRoot`.

Ví dụ cấu hình `/WEB-INF/spring-ws.xml` (được Servlet context nạp):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:sws="http://www.springframework.org/schema/web-services"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         http://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/context
         http://www.springframework.org/schema/context/spring-context.xsd
         http://www.springframework.org/schema/web-services
         http://www.springframework.org/schema/web-services/web-services.xsd">

    <context:component-scan base-package="example.orders.ws"/>

    <sws:annotation-driven/>

    <bean id="ordersSchema"
          class="org.springframework.xml.xsd.SimpleXsdSchema">
        <constructor-arg value="classpath:xsd/orders.xsd"/>
    </bean>

    <bean id="orders"
          class="org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition">
        <property name="portTypeName" value="OrdersPort"/>
        <property name="serviceName" value="OrderService"/>
        <property name="targetNamespace"
                  value="urn:example:orders:v1"/>
        <property name="locationUri" value="/ws/orders"/>
        <property name="schema" ref="ordersSchema"/>
        <property name="createSoap11Binding" value="true"/>
        <property name="createSoap12Binding" value="false"/>
    </bean>

    <bean id="requestTimingInterceptor"
          class="example.orders.ws.RequestTimingInterceptor"/>

    <bean id="ordersPayloadValidator"
          class="org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor">
        <property name="xsdSchema" ref="ordersSchema"/>
        <property name="validateRequest" value="true"/>
        <property name="validateResponse" value="false"/>
    </bean>

    <sws:interceptors>
        <ref bean="requestTimingInterceptor"/>
        <ref bean="ordersPayloadValidator"/>
    </sws:interceptors>
</beans>
~~~

XML ở đây chứa ba phần chức năng:

1. **`<sws:annotation-driven/>`**: kích hoạt cách xử lý `@Endpoint` qua annotation theo cấu hình Spring-WS XML.
2. **`<bean ...>`**: tạo các bean XSD, WSDL và interceptor bằng dependency injection của Spring.
3. **`<sws:interceptors>`**: **đăng ký** các bean interceptor với cơ chế endpoint mapping tương ứng.

**Nếu bỏ phần `<sws:interceptors>`, các bean `requestTimingInterceptor` và `ordersPayloadValidator` vẫn tồn tại nhưng chưa chắc được gọi trong quá trình xử lý SOAP.** Cần kiểm tra chính xác cấu hình đang dùng và test request sai XSD.

### 7.1. Đăng ký Servlet trong ứng dụng XML truyền thống

Nếu sử dụng WAR và `web.xml`, một đoạn khai báo điển hình:

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

Đây là **đoạn trích nằm bên trong phần tử `web-app`**, không phải toàn bộ `web.xml`. Nó cho phép `MessageDispatcherServlet` dùng application context nạp từ `spring-ws.xml`. Những phiên bản Spring/Servlet dùng Jakarta và những bản Java EE cũ dùng `javax.servlet` có quy tắc compatibility khác nhau; chọn đúng stack cho container.

Nếu WAR được triển khai dưới context path `/order-service`, URL có thể là `/order-service/ws/orders.wsdl` và `/order-service/ws/orders`. Bên ngoài có reverse proxy, địa chỉ public có thể khác; phải đối chiếu với `soap:address` trong WSDL.

### 7.2. Vì sao không kết hợp hai phương án một cách máy móc?

**Java `@EnableWs` + `WsConfigurer`** và **XML `<sws:annotation-driven/>` + `<sws:interceptors>`** là hai cách cấu hình hạ tầng tương đương về mục đích, không phải hai bước bắt buộc phải dùng đồng thời.

Trong cùng một context, nếu cấu hình cả hai mà không kiểm soát registration, có nguy cơ tạo các bean mapping/adapter trùng lặp, hai danh sách interceptor khác nhau hoặc lời gọi lặp lại. Khi đó lỗi có thể không hiện rõ cho tới lúc test request hoặc nâng phiên bản Spring-WS.

**Khuyến nghị:** một SOAP servlet/context nên có một chiến lược cấu hình annotation infrastructure rõ ràng. Nếu dự án phải trộn cấu hình XML và Java, hãy xác định **context nào sở hữu endpoint mappings** và kiểm tra interceptor chain cuối cùng thay vì dựa vào giả định “Spring sẽ tự gộp”.

## 8. So sánh hai cách đăng ký

| Tiêu chí | `WsConfigurer` + Java | Spring XML namespace |
| --- | --- | --- |
| Kích hoạt endpoint annotation | `@EnableWs` | `<sws:annotation-driven/>` |
| Điểm thêm interceptor | `addInterceptors(List<EndpointInterceptor>)` | `<sws:interceptors> ... </sws:interceptors>` |
| Cấu hình property | Method setters trên object/bean | `<property name="..." .../>` |
| Lấy dependency XSD | `@Bean`, injection với `@Qualifier` | `<bean id=...>`, `ref` |
| Quản lý theo Java refactoring | Tên kiểu/method được IDE hỗ trợ | Cấu hình tập trung không cần sửa Java |
| Phù hợp | Spring Boot, ứng dụng Java config hiện đại | WAR hoặc ứng dụng Spring XML hiện có |
| Rủi ro điển hình | Bean tạo ra nhưng không add vào chain; context scan sai | Bean khai báo nhưng không có `sws:interceptors`; schema namespace sai |
| Điều phải test chung | SOAP request thật đi qua đúng interceptor | SOAP request thật đi qua đúng interceptor |

Không có cách nào tự làm XSD, WSDL, JAXB hoặc WS-Security “đúng” nếu nội dung hợp đồng/cấu hình sai. Điểm quan trọng là **tương thích với nền tảng dự án và dễ xác minh được chain thực tế**.

## 9. Thứ tự interceptor và dừng chuỗi xử lý

Giả sử trong cấu hình Java:

~~~java
interceptors.add(timing);
interceptors.add(validator);
interceptors.add(security);
~~~

thì thứ tự **đăng ký** là timing, validator, security. Trong các tuyến xử lý, interceptor chain có quy tắc callback trước/sau và có thể dừng khi một callback trả `false`; các đường response/Fault/completion không nhất thiết đơn giản là chạy mọi callback cùng chiều như request.

Không nên dựa vào một sơ đồ tưởng tượng để quyết định kết quả bảo mật. Hãy kiểm tra behavior của phiên bản Spring-WS và test các tổ hợp:

- Request hợp lệ: những interceptor nào chạy, theo thứ tự nào?
- Validator từ chối: security có được gọi không? Endpoint có được gọi không?
- Security từ chối: validator đã đọc Body chưa? Có lộ thông tin validation cho client chưa xác thực không?
- Endpoint ném exception: interceptor nào thấy Fault, interceptor nào nhận completion?
- Handler không được map: chain endpoint có được gọi không?

### 9.1. Ví dụ kiểm soát trách nhiệm

| Interceptor | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| Timing/tracing | Gắn correlation metadata, đo elapsed time | Log đầy đủ SOAP Header/Body |
| `PayloadValidatingInterceptor` | Xác thực XML theo XSD | Đánh giá quyền người gọi |
| WS-Security interceptor | Kiểm tra token, timestamp, chữ ký, policy | Suy đoán hợp lệ XSD chỉ từ chữ ký |
| Custom authorization | Kiểm tra quyền operation và dữ liệu nghiệp vụ | Tin mỗi URL hoặc chuỗi SOAPAction do client tự đặt |
| Business endpoint | Thực hiện nghiệp vụ đã được kiểm soát | Tự đọc XML thô khi đã có contract/binding an toàn |

Không có thứ tự duy nhất đúng với mọi ứng dụng. Có hệ thống cần kiểm tra authentication trước khi phản hồi chi tiết lỗi XSD để tránh tiết lộ schema, có hệ thống kiểm tra cấu trúc tối thiểu trước để tránh chi phí xử lý security không cần thiết. Cần thiết kế theo **threat model**, khả năng của SOAP stack và kiểm thử đầy đủ, không chỉ hoán đổi các dòng `add`.

### 9.2. Khi một interceptor trả `false`

Một interceptor có thể chủ động chặn xử lý. Tuy nhiên **chặn không đồng nghĩa đã trả SOAP Fault hợp lệ**. Với các tình huống authorization hoặc validation, nên ưu tiên component đã được hỗ trợ và có cơ chế tạo Fault rõ ràng; nếu tự viết, phải bảo đảm response có code/reason/detail đúng SOAP version và contract.

SOAP 1.1 dùng `faultcode`/`faultstring`/`detail`; SOAP 1.2 dùng `Code`/`Reason`/`Detail`. Không tự chép một XML Fault của SOAP 1.1 sang SOAP 1.2 chỉ bằng cách đổi namespace Envelope.

## 10. Interceptor được quản lý trong application context nào?

Trong một hệ thống Spring Boot đơn giản, cấu hình ứng dụng, endpoint và servlet có thể dùng cùng một `ApplicationContext`. Trong WAR truyền thống, `MessageDispatcherServlet` có thể tạo **WebApplicationContext con** nạp XML riêng; root context có thể chứa service nghiệp vụ và các bean dùng chung.

Điều cần kiểm tra:

1. `@Endpoint` và các `EndpointMapping` nằm trong context nào?
2. `@EnableWs` hoặc `<sws:annotation-driven/>` được kích hoạt ở đâu?
3. Bean interceptor nằm trong cùng context hoặc có thể nhìn thấy qua quan hệ parent/child không?
4. `WsConfigurer` có được tìm và áp dụng cho hạ tầng Spring-WS đang xử lý request không?
5. Có servlet hoặc context thứ hai xử lý cùng đường dẫn mà không dùng interceptor này không?

**Lỗi rất phổ biến:** bean interceptor xuất hiện khi kiểm tra Spring context nhưng request thực tế đi qua một SOAP servlet dùng context khác. Vì thế cần **kiểm chứng bằng request chạy qua pipeline**, không chỉ assert bean tồn tại.

### 10.1. Spring MVC và Spring-WS không cùng interceptor type

Trong một ứng dụng có cả REST và SOAP:

~~~text
HTTP requests
    ├── DispatcherServlet       → Spring MVC HandlerInterceptor
    └── MessageDispatcherServlet → Spring-WS EndpointInterceptor
~~~

`WebMvcConfigurer.addInterceptors(...)` đăng ký interceptor cho Spring MVC, **không tự áp dụng cho SOAP endpoint của Spring-WS**. Ngược lại, `WsConfigurer.addInterceptors(...)` không tự can thiệp REST controller. Nếu cần một chính sách chạy trên cả hai, hãy chọn tầng phù hợp như Servlet Filter hoặc tích hợp security tương ứng, rồi kiểm tra mỗi stack.

## 11. Đăng ký interceptor theo service hoặc operation

Một SOAP servlet có thể phục vụ nhiều hợp đồng:

- `GetOrderRequest` trong `urn:example:orders:v1`.
- `CreateInvoiceRequest` trong `urn:example:invoices:v1`.

Nếu đăng ký một `PayloadValidatingInterceptor` dùng **chỉ XSD đơn hàng** cho mọi endpoint, request hóa đơn có thể bị từ chối ngay cả khi đúng XSD hóa đơn.

Không thể giải quyết vấn đề này bằng cách đổi URL WSDL hoặc tên Java class. Cần chọn **schema và scope interceptor** tương thích với các request được phục vụ.

Các chiến lược:

1. **Một tập schema phù hợp:** sử dụng cấu hình hỗ trợ nhiều XSD/namespace với resolver đáng tin cậy.
2. **Interceptor theo nhóm endpoint:** dùng cơ chế endpoint mapping/interceptor có thể áp dụng theo điều kiện được phiên bản Spring-WS hỗ trợ, bảo đảm predicate dựa trên QName/action chính xác.
3. **Tách SOAP servlet/context:** hợp đồng rất khác nhau có thể được cô lập với chain và chính sách bảo mật riêng.
4. **Custom interceptor có chọn schema:** chỉ khi cần, kèm kiểm thử và đảm bảo không tin dữ liệu đầu vào một cách mù quáng.

Ví dụ ở mục 7 là **đăng ký interceptor ở mức chung**. Không nên đem nguyên `ordersPayloadValidator` áp dụng cho mọi contract khác namespace rồi coi đó là kiểm tra dữ liệu phù hợp.

### 11.1. `xs:include` và `xs:import`

Khi một service có nhiều file XSD, cần phân biệt:

- `xs:include`: kết hợp schema cùng target namespace (hoặc chameleon schema tương thích).
- `xs:import`: tham chiếu types/elements từ namespace khác.

Ứng dụng phải cấu hình resource resolver và schema collection phù hợp. Không bật quyền truy cập URL ngoài tùy ý chỉ vì file XSD có `schemaLocation`. Nên gói XSD được review cùng ứng dụng hoặc sử dụng kho schema nội bộ đáng tin cậy, kiểm tra import/include khi đóng gói JAR/WAR.

## 12. Cần interceptor server hay `ClientInterceptor`?

Trong cùng một ứng dụng, server có thể nhận SOAP request và dùng `WebServiceTemplate` để gọi đối tác. Cần phân biệt hai interface:

| Mục đích | Server | Client |
| --- | --- | --- |
| Interface | `EndpointInterceptor` | `ClientInterceptor` |
| Vị trí | Đường request/response của `MessageDispatcher` | Đường gửi/nhận của `WebServiceTemplate` |
| Đăng ký điển hình | `WsConfigurer` hoặc `sws:interceptors` | `WebServiceTemplate.setInterceptors(...)` hoặc builder/config tương ứng |
| Ví dụ | XSD validation request, xử lý security header server | Thêm WS-Security header client, kiểm tra response |
| Có được `WsConfigurer` tự động áp dụng? | Có khi nằm đúng Spring-WS configuration | **Không** |

Ví dụ cấu hình phía client minh họa:

~~~java
WebServiceTemplate template = new WebServiceTemplate();
template.setMarshaller(marshaller);
template.setUnmarshaller(marshaller);
template.setInterceptors(new ClientInterceptor[] {
        auditClientInterceptor
});
~~~

`marshaller` và `auditClientInterceptor` là các bean được ứng dụng tạo/cấu hình; đoạn code không trình bày đầy đủ việc chọn SOAP message factory, endpoint URL, HTTP sender, timeout, chứng chỉ và policy. **Không được ép một `EndpointInterceptor` vào mảng `ClientInterceptor[]`** hoặc kỳ vọng nó được gọi khi template gửi request.

## 13. XSD validation, XML security và WS-Security phải phối hợp

Đăng ký interceptor là bước cấu hình, nhưng **interceptor nào làm gì** mới quyết định mức độ an toàn:

### 13.1. XSD validation

`PayloadValidatingInterceptor` có thể kiểm tra `GetOrderRequest` đúng cấu trúc XSD, chẳng hạn pattern của `orderId` và thứ tự các phần tử. Tuy nhiên:

- Nó không kiểm tra nội dung SOAP Header theo policy.
- Nó không chứng minh người gọi được phép truy vấn đơn hàng.
- Nó không tự biến mọi ngoại lệ thành Fault detail do WSDL quy định.
- Một request sai root QName có thể không được map tới endpoint để interceptor hoạt động.

### 13.2. XML parser security

Payload XML từ mạng cần được đọc bởi parser/message factory đã được harden: hạn chế external entities, external DTD/schema access, payload size, tài nguyên xử lý. **XXE có thể xảy ra ở thời điểm parse trước khi interceptor XSD kiểm tra**, nên không coi interceptor là cách duy nhất chặn XXE hoặc SSRF.

### 13.3. WS-Security và chứng chỉ

WS-Security interceptor có thể xác minh chữ ký số, username token, timestamp hoặc các policy được cấu hình, thường làm việc với phần SOAP Header. TLS/mTLS bảo vệ kênh kết nối và chứng chỉ ở tầng HTTP/TLS; nó không tự thay thế chữ ký thông điệp.

Khi cấu hình WS-Security:

- Dùng thư viện/interceptor phù hợp phiên bản Spring-WS và WSS4J.
- Bảo vệ và giới hạn quyền truy cập keystore/truststore.
- Xác định signed parts, algorithms, clock skew và replay policy theo contract.
- Không sửa XML đã ký theo cách làm mất tính toàn vẹn.
- Không log token, password, private key hoặc toàn bộ signed payload.

### 13.4. SOAP Fault

Chặn request do validation hoặc security cần tạo phản hồi theo chính sách. SOAP Fault có thể xuất phát từ interceptor, SOAP processor hoặc `EndpointExceptionResolver`. **Không suy ra rằng mọi `Exception` ném từ interceptor sẽ tự trở thành typed Fault với `detail` nghiệp vụ**. Hãy xây dựng error contract và kiểm thử các nhánh lỗi thực tế.

## 14. Kiểm thử đăng ký: làm sao chứng minh interceptor thực sự chạy?

Chỉ xem mã Java/XML hoặc đọc danh sách bean là **không đủ**. Một phép thử cần gửi message qua hạ tầng Spring-WS có interceptor mapping đang hoạt động.

### 14.1. Test tích cực: request hợp lệ

Trong Spring-WS có thể dùng `MockWebServiceClient`:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

class OrderInterceptorIntegrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void acceptsValidOrder() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(context);

        String xml =
                "<o:GetOrderRequest " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:orderId>ORD-1001</o:orderId>" +
                "</o:GetOrderRequest>";

        client.sendRequest(
                withPayload(new StringSource(xml)))
              .andExpect(noFault());
    }
}
~~~

Test giả định class đang chạy trong một **Spring test context** thực sự chứa `@EnableWs` hoặc XML namespace configuration, endpoint và interceptor (ví dụ qua `@SpringBootTest` hoặc cấu hình test tương đương). Annotation `@Autowired` một mình không khởi tạo context. Cũng cần thêm dependency Spring-WS test tương thích, vì không phải mọi project có starter test đều tự chứa tất cả các công cụ SOAP test.

**Test `noFault()` chỉ cho thấy request này được xử lý thành công; nó chưa chứng minh validator có chạy.** Muốn xác minh interceptor, phải có thêm test âm tính và/hoặc một interceptor spy/counter kiểm soát được.

### 14.2. Test âm tính: root đúng, dữ liệu sai XSD

Gửi:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>BAD-ID</o:orderId>
</o:GetOrderRequest>
~~~

Root QName vẫn khớp `@PayloadRoot`, nhưng `orderId` vi phạm `xs:pattern`. Test nên xác minh:

1. Request bị từ chối theo cơ chế validator, không đi vào endpoint như thành công.
2. Phản hồi là lỗi SOAP theo cấu hình, không phải `GetOrderResponse` thành công.
3. Không có stack trace, nội dung bí mật hoặc chi tiết tài nguyên nội bộ trong Fault.
4. Khi tạm bỏ validator trong **cấu hình test kiểm soát**, test âm tính đổi kết quả; đây là bằng chứng mạnh để phát hiện “bean tồn tại nhưng không đăng ký”.

Nếu implementation mặc định trả SOAP Fault loại Client/Sender, có thể dùng response matcher của Spring-WS tương ứng. Tuy nhiên mã Fault/HTTP status/detail chính xác phải được xác minh theo phiên bản, interceptor và resolver đang dùng, không hard-code một kết quả chưa từng quan sát.

### 14.3. Test thứ tự và short-circuit

Đối với các interceptor tùy chỉnh, có thể tạo implementation thử nghiệm ghi nhận sự kiện:

~~~text
handleRequest: timing
handleRequest: validator
handleRequest: security
...
handleResponse / handleFault / afterCompletion:
  ghi nhận những callback thực sự chạy
~~~

Chạy tối thiểu các đường: request hợp lệ, request sai XSD, security failure, endpoint exception và endpoint không được map. So sánh **danh sách sự kiện thực tế**, không bắt test luôn có mọi callback; đó không phải hợp đồng chung cho các trường hợp dừng sớm.

### 14.4. Test XML configuration riêng

Nếu sản phẩm chạy trên XML `spring-ws.xml`, phải có test nạp đúng XML đó hoặc triển khai WAR thử nghiệm. **Không sử dụng chỉ một Java config test rồi tuyên bố cấu hình XML hoạt động**. Những lỗi cần thử:

- `sws:interceptors` bị xóa.
- `ref bean="ordersPayloadValidator"` sai tên.
- `<sws:annotation-driven/>` bị thiếu.
- XSD resource không tồn tại trong classpath.
- Servlet context không nạp đúng `spring-ws.xml`.

## 15. Ma trận kiểm thử SOAP, HTTP và security

| Ca kiểm thử | Điều kỳ vọng và tầng cần xem |
| --- | --- |
| `GetOrderRequest` đúng XSD | Endpoint được gọi; response không Fault |
| `orderId=BAD-ID` | Interceptor XSD từ chối; endpoint không xử lý thành công |
| Bỏ `orderId` | XSD validation phát hiện phần tử bắt buộc |
| Root QName sai namespace | Có thể thất bại ở `EndpointMapping` trước interceptor |
| Prefix XML thay đổi nhưng URI giữ nguyên | Cùng QName, kết quả không thay đổi |
| `SOAPAction` khác Body | Kiểm tra mapping strategy và policy nhất quán |
| SOAP 1.2 vào factory chỉ hỗ trợ SOAP 1.1 | Lỗi SOAP version/transport, không quy là lỗi XSD |
| Security token hết hạn, Body hợp XSD | Security layer từ chối theo policy |
| XSD hợp lệ, người gọi không có quyền | Authorization từ chối, validation không cấp quyền |
| Interceptor trả `false` | Không thực thi endpoint; response phải được xử lý có chủ đích |
| Endpoint ném lỗi nghiệp vụ | Fault/error resolver và callback chain được kiểm thử |
| Response XML sai XSD, bật validateResponse | Lỗi phản hồi bị phát hiện |
| Nhiều namespace và một validator | Validator không được từ chối nhầm contract khác |
| XML có DTD/external entities | Parser/security policy chặn trước khi gây tác dụng phụ |
| Truy cập sai URL Servlet | Tầng HTTP thất bại; endpoint interceptor có thể không chạy |
| WSDL public sau reverse proxy | `soap:address` trỏ URL thật mà client có thể POST |
| Mười/nhiều request song song | Interceptor không trộn trạng thái giữa request |
| SOAP Fault kèm dữ liệu nhạy cảm | Logging/masking không phát tán token hoặc PII |

### 15.1. Mock và HTTP integration bổ sung nhau

`MockWebServiceClient` phù hợp để xác minh mapping, interceptor, payload, response và SOAP Fault trong Spring context. Nhưng nó **không kiểm tra đầy đủ** Servlet URL mapping, DNS, TLS/mTLS, reverse proxy, HTTP status thực hoặc truststore của client đối tác.

Với HTTP(S) thực, gửi request SOAP 1.1:

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

SOAPAction rỗng chỉ là ví dụ cho hợp đồng chưa khai báo action cụ thể. Trong hệ thống thực, client phải đọc binding/WSDL và gửi action được quy định. Sau đó thay `ORD-1001` bằng `BAD-ID` và quan sát khác biệt khi interceptor validator được bật.

## 16. Sự cố thường gặp và cách phân tích

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Có bean interceptor nhưng không ghi log | Chưa add vào `WsConfigurer`/`sws:interceptors` hoặc sai context | Kiểm tra chain thực tế và test request |
| Request sai XSD vẫn được xử lý | Validator không chạy hoặc `validateRequest=false` | Kiểm tra cấu hình, test root QName đúng nhưng sai facet |
| Không tìm thấy `@Endpoint` | Sai package scan hoặc thiếu annotation-driven | Xem `@EnableWs`/`sws:annotation-driven`, context |
| Servlet 404 | URL mapping/gateway không khớp | Xem `MessageDispatcherServlet` và `soap:address` |
| XML config load lỗi namespace | `xmlns:sws`/schemaLocation không hợp phiên bản | Kiểm tra XML namespace và dependency |
| Interceptor chỉ chạy ở REST | Đăng ký qua `WebMvcConfigurer` thay vì `WsConfigurer` | Dùng API của Spring-WS |
| Interceptor chạy hai lần | Cấu hình Java và XML chồng chéo, mapping trùng | Chọn chiến lược rõ, kiểm tra bean/mapping |
| Nhiều service bị từ chối sai schema | Interceptor dùng XSD của một service cho toàn bộ | Scope/schema collection theo endpoint |
| Request sai QName không có log validator | Endpoint mapping thất bại trước chain | Tách test mapping và schema validation |
| Phản hồi không có Fault rõ ràng khi `return false` | Không thiết kế response/error contract | Tạo Fault có kiểm soát, test đường chặn |
| Security đúng nhưng payload sai | XSD validation là trách nhiệm riêng | Kiểm tra validator và policy |
| SOAP Fault khác client mong đợi | SOAP version/resolver/detail chưa đồng bộ WSDL | Đối chiếu Fault trên dây |
| Dữ liệu request A xuất hiện trong log B | Interceptor singleton lưu request state ở field | Chuyển state sang `MessageContext` hoặc local variables |
| Lỗi trong production nhưng mock pass | HTTP/TLS/proxy/context khác | Bổ sung test tích hợp qua endpoint public |

### 16.1. Quy trình kiểm tra có hệ thống

Khi nghi ngờ interceptor chưa hoạt động, làm theo thứ tự:

1. Xác nhận SOAP request thật sự đến `MessageDispatcherServlet`.
2. Xác nhận root QName và `EndpointMapping` chọn endpoint dự kiến.
3. Kiểm tra `@EnableWs` hoặc `sws:annotation-driven` có được nạp trong đúng context không.
4. Kiểm tra interceptor bean tồn tại và **đã được thêm vào chain**.
5. Gửi request root đúng nhưng sai đúng **một constraint XSD**.
6. Xác minh endpoint không chạy theo đường thành công và phản hồi lỗi có kiểm soát.
7. Kiểm tra thứ tự với security interceptor/Fault resolver nếu cần.
8. Lặp lại qua HTTP(S) thực để xác nhận Servlet mapping, proxy và message factory.

Đừng vội thay WSDL hoặc namespace khi lỗi thật là `WsConfigurer` chưa được nhận diện. Ngược lại, đừng thay interceptor nếu request thậm chí không đến servlet.

## 17. Bài tập tình huống

Một ứng dụng có SOAP endpoint `CreatePaymentRequest` và `GetPaymentStatusRequest`. Đội phát triển đăng ký:

~~~java
@Configuration
public class PaymentWsConfig implements WsConfigurer {
    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(new PayloadValidatingInterceptor());
    }
}
~~~

Ứng dụng khởi động, request hợp lệ đôi khi có phản hồi thành công, nhưng request sai XSD vẫn đến nghiệp vụ, đồng thời có một số SOAP request không có log interceptor.

**Câu hỏi:**

1. Tại sao `new PayloadValidatingInterceptor()` chưa phải cấu hình đủ?
2. Tại sao một số request có thể không đi qua interceptor dù servlet nhận được?
3. Nếu thêm `@EnableWs`, cần lưu ý gì khi ứng dụng đã dùng XML `<sws:annotation-driven/>`?
4. Khi bật XSD validation, có nên dùng schema payment cho cả GetPaymentStatus thuộc namespace khác không?
5. Nếu validation từ chối một request tạo thanh toán, làm sao biết nghiệp vụ đã chạy hay chưa?
6. Trong một interceptor singleton, có nên lưu `currentPaymentId` ở field để ghi log không?

**Đáp án gợi ý:**

1. Interceptor chưa được cấu hình schema, và cần xác nhận `WsConfigurer` thực sự được áp dụng. Phải gán XSD, thiết lập validateRequest/Response phù hợp rồi đưa vào chain.
2. Endpoint mapping có thể thất bại trước interceptor; hoặc servlet/context đang dùng không có chain được cấu hình.
3. **Không cấu hình trùng hạ tầng một cách máy móc.** Chọn một cơ chế annotation-driven rõ ràng hoặc kiểm soát registration và context.
4. **Không.** Cần schema collection/scope phù hợp với từng operation và namespace.
5. Phải kiểm thử bằng counter/mock business service và kiểm tra đường xử lý thực tế. Không suy chỉ từ một HTTP status.
6. **Không.** Singleton có thể phục vụ nhiều request song song; lưu request state vào `MessageContext` hoặc biến cục bộ.

### 17.1. Bài thực hành có hướng dẫn

Hãy triển khai hai cấu hình tương đương **ở hai profile/ứng dụng chạy tách biệt**:

- **Cấu hình Java:** `@EnableWs` + `WsConfigurer` + `ordersSchema` + `RequestTimingInterceptor` + `PayloadValidatingInterceptor`.
- **Cấu hình XML:** `sws:annotation-driven` + `sws:interceptors` tham chiếu cùng hai loại interceptor và schema.

Trong mỗi cấu hình:

1. Xác minh WSDL `orders.wsdl` và địa chỉ SOAP endpoint thật.
2. Gửi `GetOrderRequest` hợp lệ và kiểm tra `GetOrderResponse`.
3. Gửi `orderId=BAD-ID`, khẳng định endpoint không xử lý thành công.
4. Thử root QName sai namespace; xem lỗi xảy ra ở mapping hay validation.
5. Thử interceptor trả `false` trong một tình huống test được kiểm soát và thiết kế phản hồi đúng.
6. Thử SOAP Header/security lỗi và xem thứ tự callback.
7. Gửi các request song song; bảo đảm dữ liệu timing/log không lẫn nhau.
8. Chạy test HTTP qua Servlet container/gateway, không chỉ mock.

**Tiêu chí hoàn thành:** hai cơ chế đăng ký đều tạo được interceptor chain có thể kiểm chứng; các lỗi được phân loại đúng; response và security không bị ảnh hưởng bởi trùng cấu hình hoặc trạng thái dùng chung.

## 18. Tóm tắt

- **`WsConfigurer.addInterceptors(...)`** là cách đăng ký `EndpointInterceptor` bằng Java trong hạ tầng Spring-WS được kích hoạt qua `@EnableWs`.
- **`<sws:interceptors>`** là cách đăng ký tương ứng trong Spring XML, thường đi kèm **`<sws:annotation-driven/>`**.
- **Bean tồn tại không đủ:** interceptor chỉ có tác dụng khi gắn vào **đúng endpoint processing chain** trong đúng application context.
- **`EndpointInterceptor` khác `ClientInterceptor`, Servlet Filter và Spring MVC `HandlerInterceptor`**; mỗi loại áp dụng cho tầng riêng.
- Các callback **`handleRequest`, `handleResponse`, `handleFault`, `afterCompletion`** có vòng đời và điều kiện gọi khác nhau; cần kiểm thử cả đường short-circuit và Fault.
- **`PayloadValidatingInterceptor`** kiểm tra XML theo XSD, nhưng không thay thế authentication, authorization, WS-Security hoặc biện pháp chống XXE ở parser.
- **Không chia sẻ mutable request state trong singleton interceptor**; dùng `MessageContext` hoặc local variable và bảo vệ log nhạy cảm.
- Khi có nhiều endpoint/namespace, phải chọn **schema và scope interceptor** đúng; không dùng một validator hẹp cho mọi dịch vụ.
- **Java và XML là hai chiến lược cấu hình**, không phải những bước phải chồng lên nhau. Kiểm tra mapping/registration trước khi kết luận ứng dụng hoạt động.
- Với SOAP contract-first, luôn xác minh **XSD/WSDL, JAXB, endpoint, SOAP Fault, interceptor chain, TLS/WS-Security và kiểm thử tương thích** để tích hợp hệ thống doanh nghiệp ổn định.
