# WsConfigurationSupport và trường hợp cần kiểm soát cấu hình sâu

> **Chương:** Cấu hình máy chủ  
> **Module:** SPRING_WEB_SERVICES – phát triển SOAP theo hướng contract-first với Spring Web Services (Spring-WS), XSD/WSDL, JAXB, endpoint và SOAP client; quản lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích khi tích hợp doanh nghiệp.

## 1. Mục tiêu học tập

`WsConfigurationSupport` nằm ở **tầng cấu hình cơ chế xử lý SOAP server** trong Spring-WS. Học về lớp này không có nghĩa mọi dự án đều phải kế thừa nó. Phần lớn ứng dụng nên bắt đầu bằng `@EnableWs` và `WsConfigurer`; chỉ đưa cơ chế cấu hình lõi vào quyền kiểm soát trực tiếp khi thật sự cần thay đổi những thành phần mặc định.

Sau bài học, bạn có thể:

1. Giải thích vai trò của `MessageDispatcherServlet`, `MessageDispatcher`, endpoint mapping, endpoint adapter, interceptor và exception resolver trên đường đi SOAP request.
2. Phân biệt trách nhiệm của `@EnableWs`, `WsConfigurer`, `WsConfigurationSupport` và `DelegatingWsConfiguration`.
3. Biết khi nào bổ sung interceptor/argument resolver đủ, khi nào phải mở rộng hoặc thay thế cấu hình hạ tầng.
4. Tránh lỗi đăng ký bean trùng, endpoint mapping không đúng QName, mất handler mặc định hoặc vô tình thay đổi WSDL công bố.
5. Xây checklist kiểm chứng XSD/WSDL, SOAP Fault, WS-Security, chứng chỉ và client tương thích sau một thay đổi cấu hình server.

### Một định hướng quan trọng

**Cấu hình sâu có chi phí vận hành.** Mỗi lần thay đổi các thành phần lõi, ứng dụng cần kiểm thử lại dispatch, XML binding, xử lý lỗi và chính sách bảo mật. Tùy biến mức thấp chỉ đáng làm khi yêu cầu không giải quyết được qua API cấu hình thông thường hoặc bean chuyên biệt.

## 2. Bản đồ các tầng của SOAP server

Để hiểu `WsConfigurationSupport`, cần biết nó nằm ở đâu trong luồng:

~~~mermaid
flowchart TD
  Client["SOAP client (CXF/JAX-WS, Spring-WS, .NET...)"]
  HTTP["HTTP server / servlet container"]
  Servlet["MessageDispatcherServlet"]
  Dispatcher["MessageDispatcher"]
  Mapping["EndpointMapping: chọn handler"]
  Chain["EndpointInterceptor chain"]
  Adapter["EndpointAdapter: gọi method"]
  Endpoint["&#64;Endpoint"]
  Service["Business service"]
  Client -->|SOAP Envelope HTTP POST| HTTP
  HTTP --> Servlet --> Dispatcher
  Dispatcher --> Mapping
  Mapping --> Chain
  Chain --> Adapter --> Endpoint --> Service
  Service --> Endpoint
  Endpoint --> Adapter
  Adapter --> Chain
  Chain --> Dispatcher
  Dispatcher --> Servlet
  Servlet -->|SOAP response/Fault| Client
~~~

Sơ đồ là mô hình trách nhiệm khái quát. Spring-WS có các hook cho request, response và fault ở các giai đoạn khác nhau; exception có thể được chuyển tới các `EndpointExceptionResolver`. Thứ tự các hook và hành vi cụ thể cần kiểm tra theo phiên bản và cấu hình thực tế.

| Thành phần | Chịu trách nhiệm | Không thay thế cho |
|---|---|---|
| `MessageDispatcherServlet` | Tiếp nhận HTTP request và tích hợp Spring-WS vào servlet | Quy tắc map QName sang method |
| `MessageDispatcher` | Điều phối xử lý SOAP message | XSD contract hoặc business service |
| `EndpointMapping` | Tìm endpoint/method tương ứng request, chẳng hạn theo payload root | XML schema validation |
| `EndpointAdapter` | Gọi endpoint và chuyển đổi tham số/kết quả theo các adapter được hỗ trợ | HTTP URL routing |
| `EndpointInterceptor` | Cross-cutting xử lý SOAP: validation, auditing, bảo mật, correlation | Toàn bộ WS-SecurityPolicy hoặc quyền nghiệp vụ |
| `EndpointExceptionResolver` | Chuyển một số exception ở endpoint thành xử lý lỗi/ SOAP Fault | Xử lý mọi lỗi transport trước khi request vào dispatcher |
| `XsdSchema`, WSDL definition | Hợp đồng cấu trúc dữ liệu và service công bố | Cấu hình dispatch runtime |
| `Jaxb2Marshaller` | XML ↔ Java theo JAXB | Đảm bảo mọi XML qua XSD validation một cách tự động |

**Ranh giới cốt lõi:** endpoint được định tuyến theo QName của payload hoặc một cơ chế mapping khác; contract XSD/WSDL định nghĩa XML mà client được phép gửi. Có thể cấu hình dispatcher đúng nhưng vẫn công bố sai WSDL, hoặc công bố WSDL đúng nhưng mapping endpoint sai.

## 3. Bốn cơ chế thường thấy trong cấu hình Spring-WS

### 3.1. `@EnableWs`: bật cấu hình endpoint theo annotation

Ở mô hình Java configuration thông thường:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;

@Configuration
@EnableWs
public class SoapServerConfig {
    // Các bean XSD/WSDL, interceptor, servlet tùy nhu cầu.
}
~~~

`@EnableWs` đưa cấu hình hạ tầng cho annotation-driven endpoints vào Spring context. Trong hệ thống Spring-WS có cơ chế cấu hình qua `DelegatingWsConfiguration` dựa trên `WsConfigurationSupport`, cho phép tập hợp các `WsConfigurer` từ ứng dụng.

Bản thân `@EnableWs` **không tự tạo** XSD chuẩn theo nghiệp vụ, WSDL đáp ứng đối tác hay bảo đảm việc đăng ký servlet mapping HTTP đúng theo môi trường. Những phần đó phải được khai báo hoặc được auto-configuration tương thích cung cấp.

### 3.2. `WsConfigurer`: thêm khả năng mà vẫn giữ cấu hình mặc định

`WsConfigurer` là điểm mở rộng dành cho ứng dụng. Những callback quan trọng gồm:

- `addInterceptors(List<EndpointInterceptor>)` để thêm interceptor server.
- `addArgumentResolvers(List<MethodArgumentResolver>)` để bổ sung cách chuyển tham số của endpoint method.
- `addReturnValueHandlers(List<MethodReturnValueHandler>)` để bổ sung cách xử lý giá trị trả về.

Các callback trên được dùng bởi cấu hình annotation-driven. Với nhu cầu xác thực payload theo XSD hoặc thêm logic logging, phần lớn ứng dụng chỉ cần dùng `WsConfigurer`; không cần trực tiếp thay cấu hình lõi.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;

@Configuration
@EnableWs
public class SoapConfig implements WsConfigurer {

    private final EndpointInterceptor auditingInterceptor;

    public SoapConfig(EndpointInterceptor auditingInterceptor) {
        this.auditingInterceptor = auditingInterceptor;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(auditingInterceptor);
    }
}
~~~

Ở đây `auditingInterceptor` là bean **đã được người phát triển cung cấp**. Đoạn minh họa cho thấy vị trí đăng ký; chưa phải ứng dụng đầy đủ. Khi dùng nhiều `WsConfigurer`, cần kiểm chứng thứ tự thực của interceptor trên request/response/fault; đừng dựa vào thứ tự không được quy định trong contract.

### 3.3. `WsConfigurationSupport`: lớp cơ sở cấp thấp

`org.springframework.ws.config.annotation.WsConfigurationSupport` là lớp cấu hình cung cấp những thành phần nền tảng cho endpoint theo annotation và các điểm mở rộng được bảo vệ (`protected hooks`). Một ứng dụng **có thể** tạo lớp `@Configuration` kế thừa trực tiếp nó nếu cần kiểm soát sâu những bean/hook mặc định.

Điều đáng nhớ: `WsConfigurationSupport` là **hạ tầng cấu hình**, không phải một annotation trên endpoint và cũng không phải SOAP servlet. Khi chọn kế thừa trực tiếp, bạn đang nhận trách nhiệm bảo đảm các thành phần cơ sở được tạo phù hợp.

### 3.4. `DelegatingWsConfiguration`: cầu nối đến nhiều WsConfigurer

`DelegatingWsConfiguration` dựa trên `WsConfigurationSupport` và phối hợp các `WsConfigurer` đã được đăng ký. Đây là lý do có thể chia việc cấu hình interceptor và adapter ra các lớp config riêng mà vẫn dùng `@EnableWs` ở một nơi.

Hình dung quan hệ:

~~~mermaid
flowchart TB
  Enable["@EnableWs"]
  Delegate["DelegatingWsConfiguration"]
  Core["WsConfigurationSupport"]
  A["WsConfigurer: audit"]
  B["WsConfigurer: schema validation"]
  C["WsConfigurer: custom XML resolver"]
  Enable --> Delegate
  Delegate --> Core
  A --> Delegate
  B --> Delegate
  C --> Delegate
~~~

Một lỗi thiết kế thường gặp là **dùng đồng thời `@EnableWs` và một `@Configuration extends WsConfigurationSupport` độc lập trong cùng application context**. Hai cấu hình có thể đăng ký trùng các bean hạ tầng (tùy tên bean, điều kiện auto-configuration và chính sách bean overriding). Hãy chọn một cơ chế chủ quản cho cấu hình annotation-driven và kiểm tra bean registry thực tế khi thay đổi.

## 4. Những bean nền tảng được WsConfigurationSupport liên quan đến

Các phiên bản Spring-WS cung cấp cơ chế annotation-driven thường sử dụng những thành phần sau:

| Bean/chức năng | Tác dụng | Triệu chứng khi sai |
|---|---|---|
| `PayloadRootAnnotationMethodEndpointMapping` | Khớp `@PayloadRoot(namespace, localPart)` với QName payload đầu SOAP Body | Client gửi đúng XSD nhưng báo không tìm thấy endpoint |
| `SoapActionAnnotationMethodEndpointMapping` | Khớp endpoint method dựa trên `@SoapAction` / SOAPAction theo binding | SOAPAction không như dự kiến; request đi sai handler |
| `AnnotationActionEndpointMapping` | Ánh xạ WS-Addressing action nếu có dùng | Client có WS-Addressing không được định tuyến |
| `DefaultMethodEndpointAdapter` | Gọi method annotation-based; phối hợp argument resolvers và return handlers | `@RequestPayload`/`@ResponsePayload` không được xử lý |
| Chuỗi `EndpointInterceptor` | Kiểm tra request và xử lý response/fault xuyên suốt | Validation/logging/security không chạy đúng thời điểm |
| `EndpointExceptionResolver` | Ánh xạ exception sang fault theo cách được cấu hình | Lỗi nghiệp vụ bị trả như lỗi nội bộ khó kiểm soát |

Tên và tập bean cụ thể có thể thay đổi giữa các dòng phiên bản Spring-WS; trong dự án thực tế, hãy xác minh qua JavaDoc của **version đang dùng** và Spring context lúc chạy. Không nên sao chép tên bean nội bộ từ một hướng dẫn rồi giả định chúng bất biến qua mọi lần nâng cấp.

### Vấn đề thường bị hiểu sai: thứ tự endpoint mapping

Spring-WS hỗ trợ nhiều cách mapping request; cách nào chọn được endpoint phụ thuộc mapping nào áp dụng, thứ tự và dữ liệu SOAP thực. **Không suy ra thứ tự ưu tiên chỉ từ tên `@PayloadRoot` hay `@SoapAction`.**

Giả sử một method được đánh dấu để khớp payload root, method khác khớp SOAPAction; request có cả hai thông tin. Nếu cấu hình endpoint mapping thay đổi, kết quả chọn endpoint có thể khác. Nên tránh contract mơ hồ, làm rõ cơ chế dispatch chủ đạo và viết regression test cho các request trùng trường hợp.

Ở SOAP 1.1, `SOAPAction` là HTTP header có thể được binding quy định; trong SOAP 1.2, cách thể hiện action liên quan đến media type/profile khác. `@PayloadRoot` dựa trên **XML QName**, không dựa trên HTTP URL hoặc tên Java method.

## 5. Cách cấu hình mặc định: @EnableWs + WsConfigurer

Với dịch vụ contract-first, một cấu hình **thực tế, dễ bảo trì** là dùng `@EnableWs` và bổ sung đúng interceptor cần thiết. Giả sử có file `orders.xsd` trong classpath, định nghĩa các global element `GetOrderRequest` và `GetOrderResponse` thuộc namespace `urn:example:orders:v1`.

~~~java
package com.example.orders.config;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class OrdersWsConfig implements WsConfigurer {

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("orders.xsd"));
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validator =
                new PayloadValidatingInterceptor();

        validator.setXsdSchema(ordersSchema());
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);

        interceptors.add(validator);
    }
}
~~~

Cấu hình là **một ví dụ triển khai riêng biệt**; cần dự án có Spring-WS tương thích và `orders.xsd` thực sự tồn tại. Với `@Configuration` mặc định sử dụng bean-method proxy, lời gọi `ordersSchema()` từ cùng lớp nhận bean được Spring quản lý. Nếu dùng `proxyBeanMethods=false`, cần tổ chức dependency injection khác để tránh tạo schema ngoài ý định.

Điều cấu hình này làm và chưa làm:

- **Có:** bật annotation-driven Spring-WS; đăng ký interceptor để validate request/response theo schema.
- **Chưa có:** servlet HTTP mapping, bean WSDL, XSD mẫu, JAXB model và endpoint nghiệp vụ.
- **Không tự động có:** WS-Security, certificate validation, giới hạn dung lượng XML, business authorization hoặc retry/idempotency.

Để giữ quyền kiểm soát tốt, nên tập trung giao diện cấu hình server ở mức `WsConfigurer` trước. Khi cần đổi một bean cụ thể, hãy xem liệu định nghĩa bean riêng hoặc một extension point chính thức đã đủ mà không cần thay cả cơ chế lõi.

## 6. Khi nào phải tiếp cận WsConfigurationSupport trực tiếp?

Có những yêu cầu phải chạm sâu hơn vào cơ chế annotation mapping/adapter mặc định, ví dụ:

1. **Thay đổi cách chọn endpoint:** nhiều action/QName cần logic ưu tiên rõ ràng, hoặc phải tích hợp cơ chế dispatch legacy đặc thù.
2. **Tùy chỉnh cấu hình một mapping/adapter nền tảng:** cần kiểm soát order, interceptors áp dụng, hoặc vòng đời của bean mà `WsConfigurer` không phơi bày.
3. **Đăng ký argument resolver/return handler đặc biệt và quản lý chính xác danh sách:** custom XML envelope/header semantics không giải quyết được bằng binding chuẩn.
4. **Tách nhiều SOAP infrastructure context:** cùng ứng dụng nhưng các nhóm contract/endpoint có yêu cầu cấu hình thực sự độc lập; phải kiểm soát cách tạo context/bean.
5. **Can thiệp khởi tạo bean nền tảng để đảm bảo legacy compatibility:** cần duy trì một hành vi xác định của đối tác sau khi thay runtime.

Đây là **tình huống đánh giá**; không phải trường hợp nào cũng buộc kế thừa `WsConfigurationSupport`. Đôi khi cách nhỏ hơn là thêm `EndpointInterceptor`, `EndpointMapping` riêng hoặc custom `MethodArgumentResolver` qua `WsConfigurer`.

### 6.1. Một cấu hình kế thừa trực tiếp

Ví dụ kiểm soát các protected extension points của lớp nền. Cấu hình này **thay thế phương án `@EnableWs` ở mục 5**, không được bật cả hai một cách độc lập trong cùng context.

~~~java
package com.example.orders.config;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.WsConfigurationSupport;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class ExplicitWsInfrastructure extends WsConfigurationSupport {

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("orders.xsd"));
    }

    @Override
    protected void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validator =
                new PayloadValidatingInterceptor();

        validator.setXsdSchema(ordersSchema());
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);

        interceptors.add(validator);
    }
}
~~~

Ví dụ này chủ yếu **minh họa quyền kiểm soát**. Nếu chỉ thêm validation interceptor, mã ở mục 5 thường đủ và dễ hiểu hơn. Kế thừa `WsConfigurationSupport` có ý nghĩa khi bạn thực sự cần phát triển tiếp cấu hình bên dưới, đồng thời **chịu trách nhiệm** cho những bean/hook mà framework vốn thiết lập giúp.

**Không dùng `@EnableWs` trên cấu hình trực tiếp kế thừa `WsConfigurationSupport` trong cùng context** nếu điều đó tạo thêm `DelegatingWsConfiguration` và duplicate infrastructure beans. Khi dự án dùng auto-configuration của Spring Boot, cần kiểm tra kỹ bean nào đã được auto-registered. Khả năng bean overriding, cách đăng ký servlet và đường dẫn mặc định phụ thuộc phiên bản cấu hình.

### 6.2. Đọc protected hooks đúng mục đích

Trong các phiên bản Spring-WS hỗ trợ mô hình này, những hook quan trọng gồm:

~~~java
// Dạng chữ ký minh họa trong lớp cấu hình mở rộng:
protected void addInterceptors(
        List<EndpointInterceptor> interceptors);

protected void addArgumentResolvers(
        List<MethodArgumentResolver> argumentResolvers);

protected void addReturnValueHandlers(
        List<MethodReturnValueHandler> returnValueHandlers);
~~~

Các interface argument resolver/return value handler thuộc cơ chế endpoint method adapter của Spring-WS; đường import chính xác và một số API có thể khác theo phiên bản. Trong dự án thật, xác nhận chữ ký qua `WsConfigurationSupport` và `DefaultMethodEndpointAdapter` **đúng version dependency** trước khi ghi `@Override`.

Các hook này là nơi **thêm** phần tử vào cơ chế hiện có, không phải lời mời xóa toàn bộ resolver/handler mặc định. Khi tùy chỉnh thấp hơn bằng cách tự tạo `DefaultMethodEndpointAdapter`, phải đặc biệt chú ý bảo toàn khả năng xử lý `@RequestPayload`, `@ResponsePayload`, DOM/`Source`, JAXB và các dạng method được app đang dùng.

### 6.3. Lưu ý về context và bean trùng

Khi phát triển một dự án có cả Spring Boot auto-configuration, `@EnableWs` và cấu hình tự kế thừa `WsConfigurationSupport`, hãy kiểm tra:

- Có **bao nhiêu** bean kiểu `PayloadRootAnnotationMethodEndpointMapping`, `DefaultMethodEndpointAdapter` và `MessageDispatcherServlet`?
- Chúng nằm trong **cùng** hay **khác** application context?
- Bean có tên trùng không? Nếu có, Spring đang từ chối startup hay cho override?
- Interceptor có được gắn lên mapping **thực đang xử lý request** hay chỉ lên một bean không được dùng?
- Sau khi tách context, `@Endpoint` có còn được component scan thấy không?

Cấu hình trùng có thể dẫn tới lỗi startup (bean definition conflict), hoặc khó phát hiện hơn là servlet/mapping không dùng đúng bean bạn định cấu hình. Vì vậy, **đọc Spring context thực tế** quan trọng hơn suy đoán từ việc có một annotation trong mã.

## 7. Cấu hình HTTP servlet và công bố WSDL là hai vấn đề khác

Một trong những lỗi phổ biến khi nghiên cứu `WsConfigurationSupport` là nghĩ rằng kế thừa lớp này tự công bố WSDL và mở URL SOAP. Trong thực tế cần xác định cấu hình servlet, contract và WSDL bean.

Ví dụ explicit servlet mapping cho một ứng dụng Spring Boot có chủ ý tự quản lý `MessageDispatcherServlet`:

~~~java
package com.example.orders.config;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

@Configuration
public class SoapServletConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
            soapServletRegistration(ApplicationContext context) {
        MessageDispatcherServlet servlet =
                new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }
}
~~~

**Nếu Spring Boot đã tự đăng ký servlet** theo starter/phiên bản đang dùng, không đăng ký servlet thứ hai mà chưa kiểm soát mapping. Đoạn trên là một lựa chọn cấu hình explicit, không phải đoạn luôn phải thêm vào mọi dự án.

Một WSDL 1.1 có thể được sinh từ XSD bằng bean:

~~~java
@Bean(name = "orders")
public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
    DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
    wsdl.setPortTypeName("OrdersPort");
    wsdl.setTargetNamespace("urn:example:orders:v1");
    wsdl.setLocationUri("/ws");
    wsdl.setSchema(ordersSchema);
    return wsdl;
}
~~~

Với servlet map `/ws/*` và tên bean `orders`, URL công bố thường là `/ws/orders.wsdl`. Cần import `org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition` và bảo đảm `ordersSchema` được định nghĩa. WSDL sinh từ các element có hậu tố `Request` và `Response` có thể tạo operation tương ứng; phải xem **WSDL thực** để chắc chắn message, binding và operation đúng contract.

Nếu hợp đồng doanh nghiệp có **WSDL chuẩn cố định** do đối tác phê duyệt, hãy ưu tiên kiểm soát nội dung WSDL được phát hành và toàn bộ XSD import/include. WSDL sinh động có thể bị thay đổi do schema/config hoặc công cụ sinh mã; đó là rủi ro tương thích.

### 7.1. Ranh giới URL, QName và SOAPAction

Một ví dụ SOAP 1.1 với `GetOrderRequest`:

~~~http
POST /ws HTTP/1.1
Host: localhost:8080
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/GetOrder"
~~~

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là **mẫu minh họa**; giá trị SOAPAction phải theo WSDL binding thực tế, không sao chép tùy ý. Thông điệp đi qua ba cơ chế khác nhau:

1. HTTP path `/ws` chọn servlet.
2. SOAPAction hoặc WS-Addressing Action (nếu cấu hình dùng) có thể tham gia mapping.
3. `@PayloadRoot(namespace="urn:example:orders:v1", localPart="GetOrderRequest")` khớp global element trong SOAP Body.

Thay HTTP URL không tự đổi QName. Thay QName của payload cũng không tự đổi URL WSDL. Khi điều tra lỗi, xác định chính xác tầng nào đang từ chối request.

## 8. EndpointMapping và EndpointAdapter: tùy chỉnh đúng ranh giới

### 8.1. Khi có nhiều cách định tuyến

Một hệ thống legacy có thể định tuyến theo SOAPAction, trong khi dịch vụ mới dùng QName của payload. Trước khi sửa mapping:

1. Xác định QName, SOAPAction, WS-Addressing Action thực sự xuất hiện trong request của từng đối tác.
2. Chọn một cơ chế dispatch chính dựa trên contract; tránh để cùng request được nhiều mapping khớp mà không có quy tắc ưu tiên rõ.
3. Nếu cần thay order hoặc thêm custom `EndpointMapping`, kiểm thử cả request **khớp** và **không khớp**, bao gồm trường hợp hai mapping có thể cùng xử lý.
4. Chứng minh mapping mới không đưa request tới endpoint ngoài phạm vi security interceptor.
5. So sánh WSDL đã công bố trước và sau thay đổi, bởi việc sửa dispatch không nên âm thầm đổi contract.

Khi can thiệp sâu bằng cách ghi đè phương thức tạo bean của `WsConfigurationSupport`, phải xem **JavaDoc/source của phiên bản đang chạy** và giữ đúng interceptor, order, bean name cũng như lifecycle. Tùy biến chỉ để “làm request chạy được” mà chưa tìm nguyên nhân SOAPAction/QName sai dễ gây hồi quy cho client cũ.

### 8.2. Custom argument resolver

`WsConfigurer#addArgumentResolvers` hoặc protected hook tương ứng cho phép bổ sung một `MethodArgumentResolver`, ví dụ chuyển một SOAP header correlation ID thành tham số Java đặc biệt. Một resolver tốt cần:

- `supportsParameter` chỉ nhận những annotation/type mà nó thực sự hiểu.
- `resolveArgument` kiểm tra đúng namespace/header, độ dài và cú pháp; không coi correlation ID là chứng thực danh tính.
- Không chiếm quyền xử lý của các resolver JAXB, DOM và `Source` mặc định.
- Được kiểm thử khi method có đồng thời tham số `@RequestPayload` thông thường và tham số custom.

Mảnh cấu hình minh họa, trong lớp thực hiện `WsConfigurer`:

~~~java
@Override
public void addArgumentResolvers(
        List<MethodArgumentResolver> resolvers) {
    resolvers.add(new CorrelationHeaderResolver());
}
~~~

`CorrelationHeaderResolver` là class ứng dụng phải tự xây; `MethodArgumentResolver` thuộc API endpoint adapter của Spring-WS. Dùng import phù hợp đúng version dependency. Chỉ ghi đoạn trên khi đã có resolver hỗ trợ tất cả các nhánh request/exception mà ứng dụng dự kiến.

### 8.3. Custom return-value handler

`addReturnValueHandlers` được sử dụng khi kiểu trả về đặc biệt không thể xử lý bằng các handler mặc định. Cần bảo đảm custom handler:

- Chỉ xử lý return type được hỗ trợ, không bắt nhầm `@ResponsePayload` thường.
- Tạo **payload XML** với QName và cấu trúc theo XSD, không phát sinh Envelope lồng đôi.
- Giữ quy tắc nil/optional và lỗi khi serialize.
- Không làm bỏ qua response validation, SOAP Fault hay WS-Security.
- Có test với client độc lập, không chỉ đơn vị Java.

Đối với JAXB/DOM/`Source` thông thường, các endpoint adapters mặc định đã đủ. **Thay toàn bộ `DefaultMethodEndpointAdapter` là một thay đổi lớn**, cần kiểm chứng mọi method signature đang sử dụng.

| Yêu cầu | Can thiệp nên thử trước | Rủi ro của tùy biến rộng |
|---|---|---|
| Validate XSD | `addInterceptors` | Validation không chạy ở mapping thực |
| Truy cập SOAP header theo kiểu riêng | `addArgumentResolvers` | Resolver bắt nhầm tham số |
| Trả kiểu payload tùy biến | `addReturnValueHandlers` | Marshal sai XML QName |
| Chọn ưu tiên SOAPAction/QName | Mapping/config riêng có test | Sai endpoint, bỏ qua security |
| Đổi toàn bộ cơ chế gọi method | `WsConfigurationSupport` / custom adapter đã đánh giá | Mất JAXB/DOM/Source handler mặc định |

## 9. Interceptor, fault và thứ tự xử lý

### 9.1. Interceptor không phải bộ điều phối duy nhất

`EndpointInterceptor` có các hook xử lý request, response và fault ở tầng endpoint mapping. Các trách nhiệm thường gặp:

- `PayloadValidatingInterceptor` xác nhận cấu trúc XML theo XSD.
- Interceptor ghi nhận correlation ID, latency và mã lỗi nhưng cần ẩn thông tin nhạy cảm.
- Interceptor WSS4J xử lý WS-Security token, timestamp, chữ ký/mã hóa theo policy.
- Kiểm tra header/phiên bản contract hoặc điều kiện nghiệp vụ liên quan đến SOAP boundary.

Thứ tự interceptor có thể ảnh hưởng thời điểm xác minh chữ ký, XML validation và logging; response/fault có thể được xử lý theo chiều hoặc hook khác request. **Kiểm thử thứ tự thực tế**, đặc biệt khi nhiều `WsConfigurer` được đăng ký.

Một tầng HTTP/XML parsing có thể từ chối request **trước khi** endpoint mapping tìm được handler, nên không thể trông chờ mọi lỗi đều đi qua cùng một interceptor.

### 9.2. Chuyển exception thành SOAP Fault

`EndpointExceptionResolver` giúp xử lý lỗi từ endpoint; `SoapFaultMappingExceptionResolver` có thể ánh xạ exception phù hợp thành SOAP Fault. Những trường hợp cần phân biệt:

| Sự cố | Tầng phát hiện thường gặp |
|---|---|
| XML không well-formed, SOAP version sai | Message factory/parser |
| Không có endpoint khớp payload/action | Endpoint mapping/dispatcher |
| Request vi phạm XSD | Schema validation interceptor |
| JAXB không unmarshal được | Method adapter/binding |
| Không đủ quyền | Security hoặc business service |
| Business error có modeled fault | Business service + fault resolver |
| Lỗi marshal response | Adapter/serializer |

Không trả Java stack trace, thông tin chứng chỉ, đường dẫn nội bộ hoặc body nhạy cảm trong fault detail. SOAP Fault code/reason/detail phải phù hợp phiên bản SOAP, WSDL và profile của đối tác; **HTTP 500 không đủ để chứng minh fault chính xác**. Nếu thay mapper/adapter, test lại cả modeled fault và lỗi không khai báo.

### 9.3. Validation và authorization khác nhau

SOAP XML có thể đúng schema nhưng người gửi không được phép tra cứu dữ liệu. XSD không xác thực danh tính, chứng chỉ không tự cấp quyền nghiệp vụ, và JAXB unmarshal thành công không chứng minh các facet đã được validate khi chưa cấu hình validator.

~~~mermaid
flowchart TB
  A["HTTP/SOAP request"] --> B["Transport + XML parser limits"]
  B --> C["Authentication và WS-Security policy"]
  C --> D["XSD validation"]
  D --> E["XML/JAXB binding"]
  E --> F["Business authorization và validation"]
  F --> G["Business operation"]
  G --> H["Response marshal + validation"]
  H --> I["Signature/encryption theo policy"]
  I --> J["SOAP response/Fault"]
~~~

Đây là mô hình trách nhiệm chứ không khẳng định thứ tự nội bộ của mọi implementation. Quan trọng là dữ liệu chưa tin cậy được kiểm soát trước khi sử dụng.

## 10. WS-Security, XML security và chứng chỉ

Kế thừa `WsConfigurationSupport` không tự thiết lập an ninh end-to-end. Cần cấu hình các lớp riêng:

| Lớp bảo vệ | Điều cần xác minh |
|---|---|
| HTTP/TLS | HTTPS, hostname/certificate validation, proxy termination, mutual TLS nếu cần |
| XML parser | XXE/DTD/external entity, giới hạn kích thước và độ sâu XML, schema resolution |
| WS-Security | Timestamp, token, chữ ký, mã hóa, phần nào của Body/Header được bảo vệ |
| Keystore/truststore | Private key, certificate chain, rotation, thời hạn và quyền truy cập |
| SOAP authorization | Principal có quyền gọi operation và xem tài nguyên cụ thể |
| Logging | Không ghi token, tài liệu đính kèm, số tài khoản hoặc plaintext nhạy cảm |

Spring-WS có tích hợp WSS4J để xử lý nhiều yêu cầu WS-Security. Tuy vậy, `WS-SecurityPolicy` của đối tác phải được kiểm chứng theo runtime và module thực tế. **TLS bảo vệ kết nối; WS-Security có thể bảo vệ thông điệp qua trung gian.** Một dịch vụ trả SOAP 200 qua HTTPS không đồng nghĩa chữ ký đúng profile.

Khi thêm mapping/adapter custom, hãy xác minh các tuyến dispatch vẫn chạy security interceptor. Không được đặt interceptor tùy biến ở vị trí khiến request chưa qua xác minh bị xử lý như đã xác thực. Tránh gửi XML/binary chưa tin cậy cho parser không có giới hạn tài nguyên; Base64, MTOM và chữ ký XML có thể gia tăng CPU/bộ nhớ.

## 11. Nhiều dịch vụ SOAP trong một ứng dụng

Giả sử ứng dụng có hai contract: `{urn:example:orders:v1}GetOrderRequest` và `{urn:example:invoices:v1}GetInvoiceRequest`. Một `MessageDispatcherServlet` có thể phục vụ cả hai rồi định tuyến theo QName. Nhưng **hai URL HTTP không tự động đồng nghĩa hai tập endpoint độc lập** nếu servlet cùng trỏ vào một application context chứa chung endpoint mapping.

| Phương án | Phù hợp khi | Phải kiểm tra |
|---|---|---|
| Một servlet và infrastructure chung | Các service dùng cùng cơ chế vận hành, chỉ khác namespace và nghiệp vụ | Mapping QName, interceptor và schema validation phân biệt đúng từng contract |
| Nhiều servlet/context riêng | Cần chính sách bảo mật, vòng đời hoặc giới hạn HTTP thực sự khác nhau | Bean registry, component scan, WSDL URL, security isolation, routing |
| Một service với nhiều version contract | Cần duy trì client cũ trong giai đoạn migration | Namespace, payload root, XSD/WSDL versions và hồi quy |

Nếu nhiều service dùng chung một `PayloadValidatingInterceptor` nhưng schema chỉ khai báo một namespace, request hợp lệ của service khác có thể bị từ chối. Phải thiết kế phạm vi validation đúng theo endpoint/contract, thay vì bật một validator toàn cục mà không kiểm tra.

Khi bảo mật khác nhau theo đối tác, hãy test request của đối tác A vào đường phục vụ đối tác B **bị từ chối đúng cách**. Chỉ phân biệt URL trong gateway nhưng để dispatcher chấp nhận mọi QName ở mọi URL có thể tạo đường truy cập không mong muốn.

## 12. Kiểm thử cấu hình sâu sau mỗi thay đổi

Các kiểm tra cần có theo thứ tự:

1. **Bean registry:** ứng dụng chỉ có infrastructure mapping/adapter như thiết kế, không tự sinh thêm các bean trùng do `@EnableWs` và subclass cùng hoạt động.
2. **Servlet và WSDL:** HTTP POST vào URL SOAP đúng, GET WSDL công bố đúng global elements, bindings, endpoint address, XSD imports và scheme qua proxy.
3. **Mapping dương tính:** mỗi QName/SOAPAction/WS-Addressing Action có một kết quả định tuyến xác định.
4. **Mapping âm tính:** sai namespace hoặc action không được gọi nhầm endpoint khác.
5. **XML binding:** `@RequestPayload`, `@ResponsePayload`, JAXB và custom resolvers vẫn xử lý cả request mới lẫn cũ.
6. **Schema validation:** thiếu field, sai `xs:sequence` hoặc sai pattern tạo lỗi phù hợp trước khi vào nghiệp vụ.
7. **SOAP Fault:** lỗi business, parser và unmarshaller được xử lý đúng profile, không lộ stack trace.
8. **Security:** chữ ký đúng được chấp nhận; thiếu chữ ký, sai chứng chỉ và timestamp hết hạn bị từ chối.
9. **Client độc lập:** client JAX-WS/CXF hoặc .NET sinh từ WSDL chính thức còn tương thích.

### 12.1. MockWebServiceClient giúp kiểm tra mapping ở mức ứng dụng

Sau khi có `@Endpoint` thực tế, có thể dùng `MockWebServiceClient` (dependency `spring-ws-test`) để thử payload dispatch mà không cần mở cổng HTTP:

~~~java
@SpringBootTest
class OrdersEndpointTest {
    @Autowired
    ApplicationContext context;

    @Test
    void acceptsGetOrderRequest() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(context);

        Source request = new StringSource("""
            <o:GetOrderRequest xmlns:o="urn:example:orders:v1">
              <o:orderId>ORD-1001</o:orderId>
            </o:GetOrderRequest>
            """);

        Source expected = new StringSource("""
            <o:GetOrderResponse xmlns:o="urn:example:orders:v1">
              <o:status>PROCESSING</o:status>
            </o:GetOrderResponse>
            """);

        client.sendRequest(withPayload(request))
              .andExpect(payload(expected));
    }
}
~~~

Đoạn này là **mẫu kiểm thử**, cần bổ sung import JUnit/Spring, `withPayload` từ `RequestCreators`, `payload` từ `ResponseMatchers` và một endpoint trả response thực sự phù hợp XSD. Bản thân `MockWebServiceClient` không kiểm tra servlet mapping, HTTP headers, proxy hoặc TLS. Phải thêm integration test dùng POST SOAP qua HTTP thực tế và test interoperability với đối tác.

### 12.2. Một SOAP POST kiểm tra servlet

~~~bash
curl -i -sS \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: "urn:example:orders:v1/GetOrder"' \
  --data-binary @request.xml \
  http://localhost:8080/ws
~~~

Giá trị SOAPAction và port ở đây minh họa, phải theo WSDL và môi trường thực. File `request.xml` cần là SOAP 1.1 Envelope chứa `GetOrderRequest` trong namespace `urn:example:orders:v1`. Quan sát HTTP status **và SOAP Envelope**, không chỉ một trong hai.

## 13. Chẩn đoán lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| Context không khởi động do trùng bean | Hai cấu hình SOAP chủ quản cùng hoạt động | `@EnableWs`, subclass `WsConfigurationSupport`, auto-configuration |
| GET WSDL trả 404 | Sai servlet mapping hoặc bean WSDL name | `/ws/*`, bean `orders`, `/ws/orders.wsdl` |
| POST trả 404 | Sai servlet URL hoặc context path | URL trước khi điều tra XML |
| WSDL chứa địa chỉ nội bộ | `locationUri`/reverse proxy chưa đúng | `soap:address` nhìn từ client ngoài |
| SOAP Fault không tìm thấy endpoint | QName/Action sai, endpoint chưa được scan | `@PayloadRoot` và XML Body thực |
| Endpoint khác bị gọi | Nhiều mapping cùng match, order tùy biến | Test đối chiếu QName + SOAPAction |
| JAXB endpoint bắt đầu lỗi | Custom resolver/adapter làm mất handler mặc định | `DefaultMethodEndpointAdapter` và resolvers |
| Validation từ chối request service khác | Validator dùng nhầm XSD/namespace | Phạm vi interceptor và schema đúng |
| SOAP Fault bị thay đổi | Exception resolver order hoặc path lỗi khác | Kiểm tra fault XML, HTTP status, log nội bộ |
| Security không chạy ở mapping mới | Interceptor không được gắn đúng | Test request không ký, token hết hạn |
| Sau nâng thư viện bị hồi quy | Thay đổi API hoặc bean mặc định | So Spring context và chạy full SOAP regression |

## 14. Lựa chọn kiến trúc theo yêu cầu

| Nhu cầu | Hướng ưu tiên |
|---|---|
| Thêm XSD validation, correlation/audit interceptor | `@EnableWs` + `WsConfigurer` |
| Thêm kiểu tham số/return value đặc thù | `WsConfigurer` với resolver/handler có phạm vi hẹp |
| Cần can thiệp mapping/adapter nền tảng | Cân nhắc `WsConfigurationSupport` trực tiếp cùng regression test đầy đủ |
| Cần thay URL WSDL, host, proxy | Kiểm tra servlet, WSDL definition, forwarded-header policy |
| Nhiều policy bảo mật không thể dùng chung | Thiết kế context/servlet/security scope riêng biệt |
| Thay đổi XSD/WSDL đã được đối tác dùng | Quản lý contract version và client migration; không coi đây chỉ là thay cấu hình |
| Nâng dòng Spring/Jakarta | Đồng bộ Spring Framework/Boot/Spring-WS, JAXB và các API tương ứng |

Một `WsConfigurationSupport` subclass có thể là giải pháp đúng khi ứng dụng có yêu cầu runtime thực sự khác mặc định. Tuy nhiên, nếu chỉ cần thêm một interceptor, lớp `WsConfigurer` đơn giản vừa dễ review hơn vừa giảm khả năng làm hỏng hạ tầng có sẵn.

## 15. Bài tập và checklist

**Bài tập 1.** Dự án có `@EnableWs` trên lớp A và `@Configuration extends WsConfigurationSupport` trên lớp B trong cùng context. Startup báo lỗi bean definition. Nguyên nhân?  
*Gợi ý:* Hai cơ chế có thể tạo cùng infrastructure beans. Chọn một cấu hình chủ quản và xác minh bean registry.

**Bài tập 2.** Client POST tới URL đúng nhưng gửi `GetOrderRequest` ở namespace `urn:example:orders:v2` thay vì `v1`. Vì sao không có endpoint?  
*Đáp án:* `@PayloadRoot` so QName (namespace URI + localPart), không so HTTP URL.

**Bài tập 3.** Custom `MethodArgumentResolver` trả `true` cho gần mọi object type, làm method JAXB đang chạy trước đây bị lỗi. Khắc phục thế nào?  
*Gợi ý:* Giới hạn `supportsParameter` vào đúng annotation/type và kiểm thử các method cũ.

**Bài tập 4.** Mapping mới nhận request thành công dù SOAP Body không có chữ ký được yêu cầu. Điều gì phải kiểm tra?  
*Gợi ý:* Security interceptor đang áp dụng ở mapping/context thực hay không, thứ tự và policy kiểm tra chữ ký/timestamp.

Checklist trước khi bàn giao:

- [ ] Phân biệt rõ `@EnableWs`, `DelegatingWsConfiguration`, `WsConfigurer` và `WsConfigurationSupport`.
- [ ] Một chủ quản cấu hình SOAP cho mỗi context; không có infrastructure beans trùng ngoài ý muốn.
- [ ] Servlet URL và WSDL published URL đúng từ góc nhìn client.
- [ ] XSD/WSDL QNames, SOAP version, action và binding được bảo toàn.
- [ ] Mapping, argument resolver và return handler custom không phá endpoints hiện có.
- [ ] Interceptor validation, Fault và WS-Security áp dụng đúng phạm vi.
- [ ] XML parser, kích thước payload/attachment và chứng chỉ được kiểm soát.
- [ ] Test dương tính, âm tính và hồi quy qua HTTP/client độc lập đều được thiết kế.
- [ ] Mọi thay đổi ảnh hưởng contract đều có kế hoạch version và tương thích.

**Ghi nhớ:** `WsConfigurationSupport` là lối vào để kiểm soát **cơ chế cấu hình lõi** của Spring-WS annotation-driven server. Phần lớn yêu cầu bổ sung interceptor/resolver được xử lý rõ ràng hơn qua `@EnableWs` và `WsConfigurer`. Khi bắt buộc đi sâu, cần xác minh đồng thời endpoint dispatch, XSD/WSDL, SOAP Fault, XML/WS-Security, chứng chỉ và hành vi của client đã triển khai.
