# SoapFaultMappingExceptionResolver và ánh xạ lớp ngoại lệ

## 1. Bối cảnh: từ ngoại lệ Java đến lỗi SOAP có thể tích hợp

Trong ứng dụng **Spring Web Services (Spring-WS)** theo hướng **contract-first**, client trao đổi thông điệp XML được quy định bởi XSD/WSDL, còn server triển khai endpoint và nghiệp vụ bằng Java. Khi xảy ra lỗi, hai thế giới cần được nối với nhau một cách có kiểm soát:

- Java có các lớp ngoại lệ như `InvalidOrderRequestException`, `OrderNotFoundException` hoặc `PartnerServiceUnavailableException`.
- SOAP có cấu trúc lỗi chuẩn **SOAP Fault** bên trong Body, với fault code, mô tả lỗi và tùy chọn chi tiết (*detail*).
- WSDL/XSD có thể công bố **hợp đồng lỗi nghiệp vụ** để client Java, .NET hoặc ngôn ngữ khác xử lý nhất quán.

Một stack trace Java không phải là hợp đồng SOAP. Nếu server trả thẳng tên lớp Java, đường dẫn file hay chi tiết database vào SOAP Fault, client bị phụ thuộc vào implementation nội bộ và thông tin nhạy cảm có thể bị lộ.

**`SoapFaultMappingExceptionResolver`** của Spring-WS giúp **ánh xạ một ngoại lệ Java sang định nghĩa SOAP Fault**. Bạn cấu hình bảng ánh xạ giữa **lớp ngoại lệ** và **loại Fault/thông điệp**, sau đó resolver tham gia xử lý khi endpoint phát sinh ngoại lệ phù hợp.

Bài học thuộc chương **SOAP Fault**, tập trung vào:

1. Cách SOAP Fault khác Java exception và HTTP error.
2. Cấu hình `SoapFaultMappingExceptionResolver` với `exceptionMappings`, `defaultFault` và `order`.
3. Cách lựa chọn ánh xạ theo lớp ngoại lệ, kế thừa và resolver chain.
4. Giới hạn của ánh xạ đơn giản, đặc biệt là **SOAP Fault detail** và WSDL typed fault.
5. Tích hợp cùng XSD validation, JAXB, interceptor, WS-Security và SOAP client.
6. Kiểm thử hợp đồng và các tình huống lỗi bảo mật, truyền tải, retry.

**Mục tiêu:** lỗi được phân loại rõ, không làm lộ implementation, không bị nhầm với timeout/TLS/HTTP, và hành vi trên dây có thể được kiểm thử bằng client đối tác.

## 2. SOAP Fault là gì?

SOAP Fault là cấu trúc lỗi nằm trong **SOAP Body**. Nó đại diện cho lỗi xử lý thông điệp SOAP, không phải toàn bộ các loại lỗi có thể xảy ra trong một lần gọi HTTP.

### 2.1. Ví dụ SOAP 1.1

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>Invalid order request</faultstring>
            <detail>
                <err:OrderError xmlns:err="urn:example:orders:fault:v1">
                    <err:code>ORDER_ID_INVALID</err:code>
                </err:OrderError>
            </detail>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Các thành phần:

| Thành phần SOAP 1.1 | Vai trò |
| --- | --- |
| `soap:Fault` | Phần tử biểu diễn lỗi bên trong `soap:Body` |
| `faultcode` | Phân loại lỗi theo SOAP; ví dụ `Client` hoặc `Server` |
| `faultstring` | Mô tả để chẩn đoán/hiển thị theo hợp đồng |
| `faultactor` | Tùy chọn, cho biết actor liên quan trong SOAP 1.1 |
| `detail` | Tùy chọn; chứa dữ liệu lỗi ứng dụng dạng XML |

Ví dụ `err:OrderError` là **thiết kế hợp đồng lỗi riêng**. Chỉ khai báo `SoapFaultMappingExceptionResolver` **không tự sinh phần tử `err:OrderError`**. Muốn có detail ổn định cần thêm cấu hình/tùy chỉnh phù hợp và định nghĩa XML trong hợp đồng.

### 2.2. Ví dụ SOAP 1.2

~~~xml
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Body>
        <env:Fault>
            <env:Code>
                <env:Value>env:Sender</env:Value>
            </env:Code>
            <env:Reason>
                <env:Text xml:lang="en">Invalid order request</env:Text>
            </env:Reason>
            <env:Detail>
                <err:OrderError xmlns:err="urn:example:orders:fault:v1">
                    <err:code>ORDER_ID_INVALID</err:code>
                </err:OrderError>
            </env:Detail>
        </env:Fault>
    </env:Body>
</env:Envelope>
~~~

SOAP 1.2 có cấu trúc `Code`/`Reason`/`Detail` khác SOAP 1.1, và hỗ trợ cơ chế `Subcode`. `Sender` gần với ý nghĩa `Client` của SOAP 1.1; `Receiver` gần với `Server`. Không được trộn các phần tử `faultcode`/`faultstring` của SOAP 1.1 vào Envelope SOAP 1.2.

### 2.3. SOAP Fault khác HTTP status

| Trường hợp | Có nhất thiết có SOAP Fault? | Cách hiểu |
| --- | --- | --- |
| SOAP 1.1 xử lý lỗi và trả Fault qua HTTP | Thường có SOAP Envelope/Fault, HTTP 500 theo SOAP 1.1 HTTP binding | Đọc Fault code và detail |
| SOAP 1.2 Fault qua HTTP | Có khi SOAP processor tạo Fault; HTTP status theo SOAP 1.2 binding và loại lỗi | Không áp quy tắc SOAP 1.1 máy móc |
| Gateway trả HTTP 502 kèm HTML | **Không** | Lỗi upstream/gateway |
| HTTP 404 vì sai URL | **Không** bắt buộc | Lỗi định tuyến HTTP |
| TLS handshake thất bại | **Không** | Chưa có phiên HTTP/SOAP thành công |
| Read timeout sau khi gửi request | Không có response hoàn chỉnh để kết luận | Outcome nghiệp vụ có thể chưa xác định |

**HTTP 500 không đủ để khẳng định đó là SOAP Fault.** Cần kiểm tra Content-Type, Envelope hợp lệ và cấu trúc Fault. Ngược lại, SOAP Fault là một thông điệp có cấu trúc; client thường xử lý nó khác đường response JAXB thành công.

## 3. Vị trí của `SoapFaultMappingExceptionResolver` trong Spring-WS

Một luồng điển hình:

~~~mermaid
flowchart TD
    A["HTTP(S) SOAP request"] --> B["MessageDispatcherServlet"]
    B --> C["MessageDispatcher / EndpointMapping"]
    C --> D["Interceptor chain / EndpointAdapter"]
    D --> E["@Endpoint gọi nghiệp vụ"]
    E --> F{"Có ném exception?"}
    F -- "Không" --> G["Tạo SOAP response thông thường"]
    F -- "Có" --> H["EndpointExceptionResolver chain"]
    H --> I["SoapFaultMappingExceptionResolver"]
    I --> J{"Tìm thấy mapping hoặc defaultFault?"}
    J -- "Có" --> K["Tạo SOAP Fault theo definition"]
    J -- "Không" --> L["Resolver khác / xử lý ngoại lệ còn lại"]
    K --> M["Serialize SOAP response"]
    G --> M
~~~

Sơ đồ là khái quát. Một số lỗi bị chặn ngay tại parser, servlet, security interceptor hoặc validation interceptor; **không phải mọi lỗi đều đi qua endpoint method và resolver này**.

`SoapFaultMappingExceptionResolver` thuộc cơ chế **`EndpointExceptionResolver`** phía **server**, thường được Spring-WS dispatcher tìm trong application context theo cách cấu hình tương ứng. Nó không phải:

- `@ControllerAdvice`/`@ExceptionHandler` của Spring MVC.
- Servlet `Filter` xử lý mọi HTTP exception.
- `ClientInterceptor` của `WebServiceTemplate`.
- Bộ xử lý HTTP status toàn cục ở reverse proxy.
- Một thư viện tự động chuyển mọi Java exception thành WSDL typed fault.

Điểm thiết kế quan trọng: **định tuyến tới endpoint xảy ra trước việc resolver xử lý exception do endpoint**, nên nếu request không được map tới handler, bạn phải chẩn đoán đường lỗi mapping riêng. Không giả định ánh xạ class `OrderNotFoundException` có thể xử lý lỗi DNS, TLS hay HTTP 404 của gateway.

## 4. Các khái niệm API cốt lõi

| API | Vai trò |
| --- | --- |
| `SoapFaultMappingExceptionResolver` | Chọn Fault definition dựa trên exception class/mapping |
| `SoapFaultDefinition` | Mô tả loại Fault, fault string/reason và locale ở mức framework |
| `setExceptionMappings(Properties)` | Đăng ký bảng ánh xạ tên lớp ngoại lệ → Fault definition dạng text |
| `setDefaultFault(SoapFaultDefinition)` | Định nghĩa Fault dự phòng khi resolver không tìm được mapping cụ thể |
| `setOrder(int)` | Ưu tiên resolver khi có nhiều `EndpointExceptionResolver` |
| `SoapFaultAnnotationExceptionResolver` | Resolver khác, đọc annotation `@SoapFault` trên exception class |
| `EndpointExceptionResolver` | Hợp đồng giải quyết lỗi phía server |
| `SoapFault` / `SoapBody` | API truy cập/tạo Fault của một `SoapMessage` |

Một resolver ánh xạ **loại lỗi** dựa trên class Java, không dựa trên chuỗi message của exception để quyết định Fault code theo mặc định. Vì vậy việc tạo hệ phân cấp exception rõ ràng quan trọng hơn việc cố parse thông điệp tự do:

~~~text
RuntimeException
├── InvalidOrderRequestException        (lỗi đầu vào)
├── OrderNotFoundException             (lỗi miền nghiệp vụ)
├── OrderStateConflictException        (không thỏa điều kiện thao tác)
└── PartnerServiceUnavailableException (phụ thuộc hệ thống)
~~~

Tên class ở đây là **ví dụ ứng dụng**, không phải các exception có sẵn trong Spring-WS.

## 5. Thiết kế phân loại lỗi trước khi viết bảng mapping

Hãy xác định chính sách lỗi theo **ngữ nghĩa contract**, không theo sở thích nội bộ của Java.

| Ngoại lệ ứng dụng | Tình huống | Fault code tham khảo | Fault string công khai |
| --- | --- | --- | --- |
| `InvalidOrderRequestException` | Dữ liệu yêu cầu không thỏa điều kiện đầu vào | `Client` / `Sender` | `Invalid order request` |
| `OrderNotFoundException` | Không tìm được đơn hàng theo contract yêu cầu báo lỗi | Có thể dùng lỗi phía request, tùy hợp đồng | `Order not found` |
| `OrderStateConflictException` | Đơn hàng không ở trạng thái cho phép hủy | Có thể là lỗi request/precondition | `Order cannot be cancelled` |
| `PartnerServiceUnavailableException` | Dịch vụ phụ thuộc đang lỗi | `Server` / `Receiver` | `Service temporarily unavailable` |
| Ngoại lệ nội bộ chưa dự kiến | Lỗi phần mềm/cấu hình | `Server` / `Receiver` | `Internal service error` |

Đây là **gợi ý phân loại**, không phải quy tắc bắt buộc. Ví dụ operation `GetOrder` có thể quy định trả response thành công với `status=NOT_FOUND` thay vì SOAP Fault. Nếu vậy **không ném `OrderNotFoundException` để map thành SOAP Fault** cho trường hợp bình thường. Hợp đồng XSD/WSDL mới quyết định dạng đáp ứng phù hợp.

Không phân loại lỗi “mọi `RuntimeException` đều là Client” chỉ để client nhận dễ hơn. Các lỗi phần mềm, database hoặc dependency thường không thể sửa chỉ bằng thay payload; nên được báo là lỗi server một cách an toàn.

### 5.1. Tạo exception ứng dụng với dữ liệu nội bộ

~~~java
package example.orders.domain;

public class InvalidOrderRequestException extends RuntimeException {
    public InvalidOrderRequestException(String message) {
        super(message);
    }
}
~~~

~~~java
package example.orders.domain;

public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
    }
}
~~~

~~~java
package example.orders.domain;

public class PartnerServiceUnavailableException extends RuntimeException {
    public PartnerServiceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

`getMessage()` của ngoại lệ có thể mang mã đơn hàng, URL nội bộ hoặc mô tả kỹ thuật. **Không dùng trực tiếp mọi `ex.getMessage()` làm faultstring công khai**. Giữ message/cause để chẩn đoán nội bộ, còn lỗi SOAP trả client cần dùng thông điệp đã được duyệt hoặc detail contract được thiết kế riêng.

## 6. Cấu hình resolver bằng Java và `@Bean`

Giả sử ứng dụng Spring Boot dùng `spring-boot-starter-web-services`, có `@EnableWs`, SOAP servlet và `@Endpoint` được component scan đúng. Ta tạo resolver:

~~~java
package example.orders.ws;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.SoapFaultDefinition;
import org.springframework.ws.soap.server.endpoint.SoapFaultMappingExceptionResolver;
import example.orders.domain.InvalidOrderRequestException;
import example.orders.domain.OrderNotFoundException;
import example.orders.domain.PartnerServiceUnavailableException;

@Configuration
public class OrderSoapFaultConfig {

    @Bean
    public SoapFaultMappingExceptionResolver orderFaultResolver() {
        SoapFaultMappingExceptionResolver resolver =
                new SoapFaultMappingExceptionResolver();

        Properties mappings = new Properties();
        mappings.setProperty(
                InvalidOrderRequestException.class.getName(),
                "CLIENT,Invalid order request,en");
        mappings.setProperty(
                OrderNotFoundException.class.getName(),
                "CLIENT,Order not found,en");
        mappings.setProperty(
                PartnerServiceUnavailableException.class.getName(),
                "SERVER,Service temporarily unavailable,en");

        resolver.setExceptionMappings(mappings);

        SoapFaultDefinition fallback = new SoapFaultDefinition();
        fallback.setFaultCode(SoapFaultDefinition.SERVER);
        fallback.setFaultStringOrReason("Internal service error");
        resolver.setDefaultFault(fallback);

        resolver.setOrder(1);
        return resolver;
    }
}
~~~

**Ý nghĩa:**

1. `@Configuration` và `@Bean` đưa resolver vào Spring application context.
2. `exceptionMappings` dùng **tên lớp Java đầy đủ** làm khóa. `Class.getName()` tránh viết sai package khi refactor.
3. Giá trị mapping trong ví dụ có dạng **`FAULT_CODE,fault string,locale`**, một cách biểu diễn mà `SoapFaultMappingExceptionResolver` hỗ trợ khi parse Fault definition. Ví dụ `CLIENT,Invalid order request,en`.
4. `setDefaultFault(...)` đặt Fault dự phòng khi không có mapping cụ thể.
5. `setOrder(1)` chọn ưu tiên tương đối trong resolver chain; số nhỏ thường có ưu tiên cao hơn.

**Lưu ý về phiên bản SOAP:** ví dụ này minh họa cấu hình kiểu SOAP 1.1 với `CLIENT`/`SERVER`. Nếu endpoint dùng SOAP 1.2, hãy xác nhận cơ chế ánh xạ fault code của Spring-WS/runtime tương ứng tạo `Sender`/`Receiver` đúng chuẩn. Không chỉ đổi `Content-Type` rồi kỳ vọng mọi Fault code/Envelope tự nhất quán.

**Lưu ý về version thư viện:** tên package/API và định dạng Fault definition cần tương thích phiên bản Spring-WS đang dùng. Bài học dùng API Spring-WS thường gặp; khi nâng version cần đối chiếu bằng compile/runtime tests và inspect SOAP Fault thực tế.

### 6.1. Cấu hình mặc định không được rò rỉ exception nội bộ

Khi không tìm thấy mapping, `defaultFault` có thể trả:

~~~xml
<faultcode>soap:Server</faultcode>
<faultstring>Internal service error</faultstring>
~~~

Đây là **đoạn trích trong SOAP 1.1 Fault**, không phải XML response hoàn chỉnh. Client không được thấy `NullPointerException`, câu SQL, mật khẩu, khóa riêng hoặc đường dẫn file nội bộ.

Nhưng cũng phải nhớ rằng **default fault có thể che lỗi lập trình nếu log/monitoring không phân loại nguyên nhân**. Hãy giữ stack trace đã được kiểm soát trong hệ thống quan sát nội bộ, nối với correlation ID, và đặt cảnh báo cho lỗi server thay vì dựa vào faultstring mơ hồ.

### 6.2. Vì sao không map toàn bộ `Exception` thành `CLIENT`?

Ví dụ nguy hiểm:

~~~java
// KHÔNG nên làm: mọi exception bị báo là lỗi phía client.
mappings.setProperty(
        Exception.class.getName(),
        "CLIENT,Invalid request,en");
~~~

Lỗi mất kết nối database hoặc lỗi ký XML cũng sẽ bị báo sai là do payload. Điều đó khiến client có thể thử sửa request mãi mà không giải quyết được nguyên nhân, đồng thời làm metrics lỗi server thiếu chính xác.

Nếu cần dự phòng cho lỗi không dự kiến, hãy dùng `defaultFault` có thông điệp công khai an toàn và log nguyên nhân nội bộ. Những ngoại lệ cần thông điệp nghiệp vụ riêng mới nên được khai báo mapping cụ thể.

## 7. Đặt resolver trong đúng Spring-WS application context

`SoapFaultMappingExceptionResolver` chỉ tham gia xử lý khi **`MessageDispatcher` đang phục vụ request nhìn thấy nó qua cơ chế resolver registration**.

Trong Spring Boot đơn giản, `@Configuration` nằm dưới package của `@SpringBootApplication` thường được scan. Trong WAR truyền thống, `MessageDispatcherServlet` có thể dùng WebApplicationContext riêng, khác root context. Một bean có mặt ở context khác chưa chắc được dispatcher đang chạy tìm thấy.

Kiểm tra lần lượt:

1. SOAP URL có đi vào đúng `MessageDispatcherServlet` không?
2. Request có được map vào đúng `@Endpoint` không?
3. Bean resolver có nằm trong Spring context mà SOAP dispatcher dùng không?
4. Có resolver khác đã xử lý ngoại lệ trước nó không?
5. Lỗi xảy ra ở endpoint hay sớm hơn, chẳng hạn XML parser, WS-Security interceptor, servlet/gateway?

**Đăng ký đúng bean nhưng sai context cũng tương đương resolver không hoạt động** ở luồng request thực tế.

## 8. Cấu hình bằng Spring XML trong ứng dụng truyền thống

Nếu project dùng Spring XML, có thể khai báo resolver tương ứng:

~~~xml
<bean id="orderFaultResolver"
      class="org.springframework.ws.soap.server.endpoint.SoapFaultMappingExceptionResolver">

    <property name="order" value="1"/>

    <property name="exceptionMappings">
        <props>
            <prop key="example.orders.domain.InvalidOrderRequestException">CLIENT,Invalid order request,en</prop>
            <prop key="example.orders.domain.OrderNotFoundException">CLIENT,Order not found,en</prop>
            <prop key="example.orders.domain.PartnerServiceUnavailableException">SERVER,Service temporarily unavailable,en</prop>
        </props>
    </property>
</bean>
~~~

Đoạn trên là **fragment nằm trong một file Spring `<beans>` hoàn chỉnh**; tên package class ứng dụng phải khớp project thật. Các giá trị `<prop>` được Spring truyền vào `Properties` để resolver parse. Nếu muốn có fallback như cấu hình Java, cũng cần cấu hình `defaultFault` thích hợp hoặc giữ một resolver cuối rõ ràng.

Điểm cần phân biệt:

- XML `<bean>` tạo resolver phía server; nó **không phải** `<sws:interceptors>`.
- `EndpointExceptionResolver` và `EndpointInterceptor` là **hai cơ chế mở rộng khác nhau**.
- Khi dùng cả Java configuration và XML trong cùng context, không đăng ký hai resolver trùng chính sách một cách vô thức; phải kiểm tra ordering và behavior thật.

### 8.1. Không nhầm `WsConfigurer.addInterceptors(...)` với exception resolver

`WsConfigurer.addInterceptors(List<EndpointInterceptor>)` dùng để đăng ký **interceptor** như `PayloadValidatingInterceptor` hoặc một interceptor tracing. Không thêm `SoapFaultMappingExceptionResolver` vào danh sách đó: class này thuộc họ **`EndpointExceptionResolver`**, không triển khai `EndpointInterceptor`.

Theo thiết kế thông thường, resolver được đưa vào Spring-WS thông qua bean resolution trong dispatcher context. Nếu ứng dụng tự tạo `MessageDispatcher` hoặc override infrastructure đặc biệt, phải xác nhận resolver list và ordering thực tế theo cấu hình đó.

## 9. Ánh xạ lớp ngoại lệ, kế thừa và khả năng trùng mapping

Một exception class có thể kế thừa class khác. Đoạn dưới đây là **biến thể thay thế** cho định nghĩa `InvalidOrderRequestException` ở mục 5.1, không khai báo đồng thời hai class trùng tên trong cùng project:

~~~java
public class OrderDomainException extends RuntimeException {
    public OrderDomainException(String message) {
        super(message);
    }
}

public class InvalidOrderRequestException extends OrderDomainException {
    public InvalidOrderRequestException(String message) {
        super(message);
    }
}
~~~

Giả sử bảng mapping có:

~~~text
OrderDomainException          -> CLIENT,Order business error,en
InvalidOrderRequestException -> CLIENT,Invalid order request,en
~~~

Một ngoại lệ `InvalidOrderRequestException` có thể khớp với tiêu chí của lớp con và của lớp cha theo cơ chế match mà resolver thực hiện. Spring-WS hỗ trợ tìm mapping theo exception class/hierarchy; **cách chọn khi nhiều mapping có thể khớp cần được kiểm thử theo phiên bản** thay vì giả định thứ tự viết `Properties` quyết định kết quả.

### 9.1. Thực hành thiết kế hierarchy

- Dùng class **chuyên biệt** cho lỗi nghiệp vụ cần Fault string/detail khác nhau.
- Dùng class cha khi các lỗi thực sự có **cùng chính sách công khai**.
- Tránh mapping quá rộng như `RuntimeException` khiến lỗi server bị ngụy trang thành lỗi client.
- Tránh dùng exception message để suy ra mã lỗi bằng `contains("not found")`; thông điệp có thể thay đổi hoặc bị quốc tế hóa.
- Test cả trường hợp subclass chưa có mapping riêng.
- Khi thay package hoặc rename exception class, bảo đảm bảng mapping được cập nhật; dùng `.class.getName()` trong Java config sẽ dễ refactor hơn chuỗi XML hard-code.

**Lưu ý**: mapping theo exception class là chi tiết Java **nằm phía server**. Đối tác SOAP không nhìn thấy Java class đó; họ nhìn thấy Fault XML và các mã lỗi contract công bố.

## 10. Nhiều resolver cùng hoạt động và ưu tiên xử lý

Ứng dụng có thể đồng thời dùng:

- `SoapFaultMappingExceptionResolver`: mapping dựa trên class ngoại lệ.
- `SoapFaultAnnotationExceptionResolver`: mapping qua annotation `@SoapFault` trên lớp ngoại lệ.
- Resolver tùy chỉnh để tạo fault detail hoặc xử lý một nhóm lỗi chuyên biệt.
- Các resolver mặc định hoặc do thư viện tích hợp đăng ký.

Khi một exception xảy ra, Spring-WS dùng **resolver chain** theo cơ chế cấu hình và thứ tự ưu tiên; resolver xử lý được lỗi sẽ ảnh hưởng việc những resolver sau còn cơ hội xử lý hay không.

~~~mermaid
flowchart TD
    A["Endpoint throws Exception"] --> B["Resolver A: thứ tự ưu tiên cao"]
    B --> C{"A xử lý được?"}
    C -- "Có" --> D["SOAP Fault / response theo A"]
    C -- "Không" --> E["Resolver B"]
    E --> F{"B xử lý được?"}
    F -- "Có" --> G["SOAP Fault / response theo B"]
    F -- "Không" --> H["Fallback / xử lý mặc định"]
~~~

Giá trị `setOrder(...)` có thể được dùng để đặt ưu tiên. **Số thấp có độ ưu tiên cao** theo quy tắc Spring ordering thông thường. Tuy nhiên, chỉ sắp thứ tự không đủ nếu một resolver được cấu hình **`defaultFault` quá rộng**:

~~~text
Resolver A:
  defaultFault = SERVER
  order = 0

Resolver B:
  mapping riêng cho InvalidOrderRequestException
  order = 10
~~~

Nếu A xử lý được mọi lỗi bằng default fault trước, B có thể **không bao giờ thấy** `InvalidOrderRequestException`. Hệ quả là client nhận `Server` thay vì lỗi đầu vào có chủ đích.

**Quy tắc:** đặt mapping chuyên biệt và resolver cần xử lý chi tiết ở vị trí rõ ràng; để fallback ở cuối hoặc có scope phù hợp. Kiểm thử exception chưa có mapping để chắc Fault dự phòng hoạt động mà không che mất lỗi chuyên biệt.

### 10.1. Khi nào chọn annotation `@SoapFault`?

Spring-WS có thể dùng annotation trên exception class theo cơ chế `SoapFaultAnnotationExceptionResolver`:

~~~java
import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;

@SoapFault(
        faultCode = FaultCode.CLIENT,
        faultStringOrReason = "Invalid order request")
public class InvalidOrderRequestException extends RuntimeException {
    public InvalidOrderRequestException(String message) {
        super(message);
    }
}
~~~

Ví dụ này trình bày **một chiến lược thay thế**. Nếu cùng exception được xử lý bởi cả annotation resolver lẫn mapping resolver, phải chọn ưu tiên và nguồn chính sách rõ ràng; không mặc nhiên cho rằng annotation “thắng” bảng mapping.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Muốn tập trung toàn bộ ánh xạ trong configuration | `SoapFaultMappingExceptionResolver` |
| Muốn đặt Fault policy gần lớp exception | `@SoapFault` + annotation resolver |
| Cần Fault detail XML có cấu trúc riêng | Resolver tùy chỉnh hoặc extension point phù hợp |
| Cần fallback an toàn cho lỗi không dự kiến | Một resolver cuối hoặc default fault được thiết kế cẩn thận |

Không chọn annotation hay property chỉ vì ít dòng code hơn; hãy cân nhắc quyền quản lý contract, versioning và cách đội vận hành kiểm tra được chính sách lỗi.

## 11. Kết nối `@Endpoint` với resolver: một luồng nghiệp vụ

Giả sử XSD/WSDL công bố global element `GetOrderRequest`:

~~~xml
<xs:element name="GetOrderRequest">
    <xs:complexType>
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>
</xs:element>
~~~

Schema ví dụ giả định `targetNamespace="urn:example:orders:v1"` và `elementFormDefault="qualified"`. Client gửi SOAP 1.1:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
    <soap:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-9999</o:orderId>
        </o:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Một endpoint minh họa:

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
import example.orders.domain.OrderNotFoundException;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public Source getOrder(@RequestPayload Element request) {
        NodeList nodes =
                request.getElementsByTagNameNS(NS, "orderId");
        if (nodes.getLength() != 1) {
            throw new IllegalArgumentException("Missing orderId");
        }

        String orderId = nodes.item(0).getTextContent();
        if ("ORD-9999".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }

        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>FOUND</o:status>" +
                "</o:GetOrderResponse>");
    }
}
~~~

**Giới hạn ví dụ:** code cố ý giả lập `ORD-9999` không tồn tại, không sử dụng database, không triển khai toàn bộ response XSD/WSDL, không minh họa authentication/authorization và không phản ánh logic sản xuất. Trong ứng dụng thật, hãy xác thực XML theo XSD, xử lý dữ liệu qua JAXB hoặc parser an toàn, rồi gọi service nghiệp vụ.

Khi endpoint ném `OrderNotFoundException`, resolver đã đăng ký ở mục 6 có thể chọn:

~~~text
OrderNotFoundException
    ↓ exceptionMappings
CLIENT,Order not found,en
    ↓ SoapFaultDefinition
SOAP 1.1 Fault Client / "Order not found"
~~~

Đối tác **không nhận** object Java `OrderNotFoundException`. Họ nhận XML Fault. Nếu hợp đồng quy định `GetOrderResponse` với `NOT_FOUND` thay vì Fault, phải thiết kế endpoint theo hợp đồng đó, không áp dụng ví dụ ném exception một cách máy móc.

### 11.1. Một HTTP URL có nhiều operation

Giả sử `GetOrderRequest` và `CancelOrderRequest` đều POST tới `/ws/orders`. Spring-WS chọn method theo `@PayloadRoot` hoặc strategy khác đã đăng ký. Resolver chỉ được gọi theo đường ngoại lệ sau quá trình xử lý có liên quan; **không dùng `SoapFaultMappingExceptionResolver` để thay thế `EndpointMapping`**.

Nếu namespace thay từ `urn:example:orders:v1` sang `...:v2` mà endpoint chỉ khai báo v1, request có thể thất bại ở mapping **trước khi logic `OrderNotFoundException` có cơ hội chạy**.

## 12. Giới hạn của mapping đơn giản: SOAP Fault detail có cấu trúc

Tính năng chính của `SoapFaultMappingExceptionResolver` là lựa chọn **Fault definition** từ exception: fault code, chuỗi mô tả, locale và fallback. Nhưng nhiều hệ thống tích hợp cần một `detail` dạng XML có mã lỗi ổn định:

~~~xml
<detail>
    <err:OrderError xmlns:err="urn:example:orders:fault:v1">
        <err:code>ORDER_NOT_FOUND</err:code>
        <err:correlationId>REQ-2048</err:correlationId>
    </err:OrderError>
</detail>
~~~

Để có cấu trúc trên, cần một **cơ chế tùy chỉnh Fault detail** và hợp đồng XML tương ứng. Một chuỗi mapping như:

~~~properties
example.orders.domain.OrderNotFoundException=CLIENT,Order not found,en
~~~

**không tự tạo** `err:OrderError`, `err:code` hay `err:correlationId`. Nếu client sinh mã từ WSDL và mong đợi typed fault, việc chỉ có faultstring thường là chưa đủ.

### 12.1. Ví dụ XSD định nghĩa chi tiết lỗi

File lỗi có namespace riêng, chẳng hạn `xsd/order-fault.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:fault:v1"
           xmlns:err="urn:example:orders:fault:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderErrorCodeType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="ORDER_ID_INVALID"/>
            <xs:enumeration value="ORDER_NOT_FOUND"/>
            <xs:enumeration value="ORDER_STATE_CONFLICT"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="OrderError">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="code"
                            type="err:OrderErrorCodeType"/>
                <xs:element name="correlationId"
                            type="xs:string"
                            minOccurs="0"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Ưu điểm:

- Client có thể xử lý `ORDER_NOT_FOUND` ổn định thay vì so sánh toàn bộ faultstring tiếng Anh.
- `correlationId` hỗ trợ đối soát log mà không cần lộ chi tiết hệ thống.
- XSD xác định namespace và kiểu dữ liệu của detail.
- Khi thêm mã lỗi, có thể đánh giá ảnh hưởng đến client cũ theo quy tắc versioning.

Nhưng code XML chi tiết đó **không tự động được thêm bởi `DefaultWsdl11Definition` hoặc resolver mapping đơn giản**. Nếu muốn đối tác sinh được typed fault exception từ WSDL, cần công bố cấu trúc lỗi trong WSDL phù hợp và kiểm thử với công cụ sinh client thực tế.

### 12.2. WSDL 1.1 fault message không chỉ là tên Java exception

Trong WSDL 1.1, một operation có thể khai báo `wsdl:fault` gắn với `wsdl:message` dành cho lỗi; binding SOAP tương ứng có thể cần `soap:fault`. Một đoạn minh họa **không hoàn chỉnh**:

~~~xml
<wsdl:message name="OrderNotFoundFaultMessage">
    <wsdl:part name="fault" element="err:OrderError"/>
</wsdl:message>

<wsdl:portType name="OrdersPort">
    <wsdl:operation name="GetOrder">
        <wsdl:input message="tns:GetOrderInput"/>
        <wsdl:output message="tns:GetOrderOutput"/>
        <wsdl:fault name="OrderNotFoundFault"
                    message="tns:OrderNotFoundFaultMessage"/>
    </wsdl:operation>
</wsdl:portType>
~~~

Fragment giả định `wsdl:definitions` khai báo prefix `wsdl`, `tns`, `err`, nhập XSD fault và có các `GetOrderInput`/`GetOrderOutput` message tương ứng. Phần binding và service/port còn phải được khai báo đầy đủ.

**Điểm mấu chốt:** Java `OrderNotFoundException` và `wsdl:fault name="OrderNotFoundFault"` không tự gắn kết chỉ vì cùng ý nghĩa. Bạn phải viết/kiểm chứng cơ chế tạo `detail` đúng QName và tổ chức WSDL phù hợp để client hiểu đó là lỗi có cấu trúc.

### 12.3. Tùy chỉnh Fault thay vì trả message tự do

Trong một số phiên bản Spring-WS, lớp nền của resolver SOAP cung cấp extension point như `customizeFault(Object endpoint, Exception ex, SoapFault fault)` để tùy chỉnh Fault sau khi định nghĩa cơ bản được chọn.

**Phác thảo ý tưởng**, không phải implementation hoàn chỉnh:

~~~java
// Trong lớp resolver tùy chỉnh phù hợp với phiên bản Spring-WS:
@Override
protected void customizeFault(
        Object endpoint, Exception ex, SoapFault fault) {

    if (ex instanceof OrderNotFoundException) {
        SoapFaultDetail detail = fault.addFaultDetail();

        // Tạo detail XML với QName
        // {urn:example:orders:fault:v1}OrderError,
        // bên trong chứa err:code và correlationId.
        // Dữ liệu phải được escape/serialize bằng API XML an toàn.
    }
}
~~~

Đoạn trên cố tình chỉ thể hiện **điểm tùy chỉnh và trách nhiệm dữ liệu**. API thao tác `SoapFaultDetail`/`SoapFaultDetailElement` và cách ghi XML chi tiết cần được hiện thực, import và thử nghiệm theo phiên bản Spring-WS; không dùng comment trên như một bộ tạo typed fault có thể chạy ngay.

Khi triển khai:

1. Chỉ xuất ra các mã lỗi/field **đã công bố**.
2. Không dùng exception message không tin cậy làm XML thô.
3. Tạo detail bằng API XML namespace-aware, JAXB hoặc phép biến đổi an toàn.
4. Kiểm tra QName và cấu trúc detail bằng XSD test.
5. Thử SOAP 1.1 và SOAP 1.2 riêng nếu service hỗ trợ cả hai.
6. Kiểm tra signed parts nếu WS-Security áp dụng lên thông điệp lỗi.

## 13. Validation và interceptor có tự đi vào resolver này không?

Đây là một nhầm lẫn phổ biến: `SoapFaultMappingExceptionResolver` giải quyết **ngoại lệ mà dispatcher chuyển đến resolver chain**. Nhưng Spring-WS có nhiều nguồn lỗi với cách xử lý khác nhau.

### 13.1. `PayloadValidatingInterceptor`

`PayloadValidatingInterceptor` kiểm tra payload theo XSD khi được đăng ký. Khi XML sai cấu trúc, nó có thể **tự xử lý lỗi validation và tạo SOAP Fault theo hành vi cấu hình**, thay vì ném đúng lớp `InvalidOrderRequestException` mà ứng dụng đã map.

Do đó **không thể suy** rằng:

~~~text
XSD invalid
  -> InvalidOrderRequestException
  -> SoapFaultMappingExceptionResolver
~~~

luôn xảy ra. Muốn dùng cùng error contract cho lỗi validation, cần xác định và tùy chỉnh đúng luồng lỗi của validator/dispatcher theo framework đang chạy.

### 13.2. Interceptor chủ động dừng xử lý

Một `EndpointInterceptor.handleRequest(...)` có thể trả `false` để ngăn gọi endpoint. Việc trả `false` **không đồng nghĩa đã ném exception** hoặc đã tạo Fault detail. Nếu interceptor tự tạo SOAP Fault, resolver mapping theo Java exception có thể hoàn toàn không tham gia.

Tương tự, lỗi WS-Security có thể phát sinh ở security interceptor, SOAP processor hoặc transport; cần xem policy và cơ chế Fault thực tế. Không cố ép lỗi token, chứng chỉ hay chữ ký vào một `OrderNotFoundException` chỉ để tái sử dụng resolver.

### 13.3. JAXB và lỗi marshal/unmarshal

Lỗi JAXB không ánh xạ được request/response có thể phát sinh tại adapter, endpoint hoặc marshaller, với các lớp exception thuộc Spring OXM/JAXB stack. Một số lỗi có thể đi qua resolver chain; một số lỗi có thể xảy ra sớm hơn hoặc được xử lý ở tầng khác.

Nếu muốn ánh xạ lỗi OXM thành Fault thân thiện:

- Xác định exception class thực tế của phiên bản runtime.
- Không gán tất cả lỗi JAXB thành lỗi phía client; lỗi **marshal response phía server** là trách nhiệm server.
- Không đưa toàn bộ XML input hay JAXB stack trace vào Fault.
- Kiểm thử riêng malformed XML, sai XSD, unmarshalling và marshalling response.

## 14. Mối quan hệ với SOAP client và `WebServiceTemplate`

Ở phía client, một SOAP Fault được nhận diện khác response JAXB thông thường. Spring-WS thường dùng `WebServiceTemplate` để gửi request và có thể ném **`SoapFaultClientException`** khi server trả SOAP Fault.

~~~java
import org.springframework.ws.soap.client.SoapFaultClientException;

try {
    Object response =
            webServiceTemplate.marshalSendAndReceive(request);
    // Xử lý response nghiệp vụ thành công.
} catch (SoapFaultClientException ex) {
    javax.xml.namespace.QName faultCode = ex.getFaultCode();
    String reason = ex.getFaultStringOrReason();

    // Phân loại bằng fault code và detail contract khi có.
    // Không hiển thị nguyên xi mọi reason cho người dùng cuối.
}
~~~

`webServiceTemplate` và `request` là object đã được ứng dụng cấu hình. Đây là ví dụ xử lý lớp lỗi SOAP ở client; một triển khai thật phải cấu hình endpoint URL, JAXB marshaller/unmarshaller, SOAP version, timeout, TLS và WS-Security.

**Quan trọng:** `SoapFaultClientException` là ngoại lệ **ở phía client khi nhận Fault**, không phải lớp ngoại lệ domain mà server bắt buộc phải ném. Server có thể dùng `OrderNotFoundException`, còn client chỉ biết SOAP Fault theo contract.

### 14.1. Không dùng `faultstring` làm API machine-readable duy nhất

Fault reason có thể được địa phương hóa, thay đổi câu chữ hoặc chịu chính sách che thông tin. Client nên dựa vào **mã lỗi có cấu trúc và QName detail** nếu contract định nghĩa, sau đó dùng Fault reason để hiển thị/chẩn đoán trong giới hạn cho phép.

Ví dụ chính sách client:

| Fault code/detail | Hành động client phù hợp |
| --- | --- |
| `ORDER_ID_INVALID` | Báo dữ liệu đầu vào không hợp lệ; không retry nguyên request |
| `ORDER_NOT_FOUND` | Hiển thị hoặc cập nhật trạng thái theo contract |
| `ORDER_STATE_CONFLICT` | Yêu cầu tải lại trạng thái; không retry mù quáng |
| Lỗi server tạm thời | Có thể cân nhắc retry có giới hạn theo chính sách |
| SOAP Fault không nhận diện | Ghi nhận correlation ID, báo lỗi tương thích |

**Fault code “Server” không tự bảo đảm retry an toàn.** Với operation có tác dụng phụ, server có thể đã commit giao dịch rồi mới thất bại khi tạo response. Client cần idempotency key, truy vấn đối soát hoặc quy tắc retry theo hợp đồng.

### 14.2. Cẩn trọng khi client gặp HTTP lỗi không phải SOAP

~~~text
HTTP 502 + HTML response
     ≠ SOAP Fault

TLS handshake exception
     ≠ SOAP Fault

HTTP read timeout, chưa nhận đủ body
     ≠ SOAP Fault đã được xác thực
~~~

Đừng catch mọi exception từ `WebServiceTemplate` rồi coi đó là một mã SOAP `Server`. Phải phân loại lỗi transport/I/O, HTTP/proxy, SOAP Fault và lỗi unmarshalling tương ứng.

## 15. Chính sách bảo mật cho SOAP Fault

Lỗi công khai là **bề mặt rò rỉ thông tin**: client có thể chủ động tạo payload sai để khám phá backend. Mapping theo exception class nên có chính sách rõ ràng.

### 15.1. Không tiết lộ implementation

Tránh các Fault như:

~~~xml
<faultstring>
    java.sql.SQLException: password authentication failed
    at com.internal.payment.DatabaseClient:207
</faultstring>
~~~

Đây là ví dụ **nội dung không an toàn**. Nó tiết lộ công nghệ, tên package và chi tiết sự cố; đôi khi exception message còn có dữ liệu cá nhân hoặc thông tin truy cập.

Thay bằng:

~~~xml
<faultstring>Internal service error</faultstring>
~~~

và ghi nguyên nhân vào hệ thống log nội bộ có giới hạn truy cập, gắn correlation ID để đối soát.

### 15.2. Không tin exception message hoặc dữ liệu request

Nếu class `OrderNotFoundException` chứa `"Order not found: " + orderId`, đừng tự động phản chiếu mọi `orderId` người dùng gửi vào Fault detail. Dữ liệu có thể dài, chứa ký tự đặc biệt hoặc PII. Khi cần đưa mã định danh trở lại, thực hiện escaping, giới hạn độ dài và đánh giá quyền xem thông tin đó.

### 15.3. WS-Security và SOAP Fault

Trong hệ thống có WS-Security, policy có thể yêu cầu ký hoặc bảo vệ các phần nhất định của **SOAP response và Fault**. Do đó:

- Không tự sửa Fault sau khi chữ ký đã được tạo theo cách phá vỡ tính toàn vẹn.
- Kiểm tra interceptor bảo mật có xử lý Fault path hay không.
- Không công bố khóa, token, chứng chỉ nội bộ hoặc thông tin xác thực trong detail.
- Kiểm tra SOAP Header security và Fault riêng với từng SOAP version.

TLS/mTLS bảo vệ kênh truyền; không tự làm Fault detail hợp đồng, chữ ký SOAP hay mã lỗi nghiệp vụ đúng.

### 15.4. Giới hạn công việc xảy ra trước resolver

XML parser không được harden có thể tải external entity **trước khi endpoint ném exception**. Vì vậy XSD validation, XXE prevention, resource limits và SOAP security là các lớp phòng vệ khác nhau. Resolver không phải nơi “chữa” mọi XML payload độc hại.

## 16. Kiểm thử `SoapFaultMappingExceptionResolver`

Muốn chứng minh resolver hoạt động, cần gửi thông điệp qua Spring-WS context thực sự chứa `EndpointMapping`, `EndpointAdapter` và resolver, không chỉ gọi Java method trực tiếp.

### 16.1. Các ca bắt buộc

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Request hợp lệ, nghiệp vụ thành công | Nhận response đúng XSD, không có SOAP Fault |
| Endpoint ném `InvalidOrderRequestException` | SOAP Fault loại client/sender với reason đã chọn |
| Endpoint ném `OrderNotFoundException` | Mapping riêng được áp dụng; không rơi vào fallback |
| Endpoint ném `PartnerServiceUnavailableException` | SOAP Fault loại server/receiver, không lộ endpoint đối tác |
| Ngoại lệ nội bộ chưa map | `defaultFault` an toàn; log nội bộ có correlation ID |
| Subclass của exception đã map | Lựa chọn mapping theo hierarchy đúng kỳ vọng |
| Hai resolver có thứ tự khác nhau | Không có resolver fallback che mapping chuyên biệt |
| Sai root QName | Phân biệt lỗi endpoint mapping và lỗi do domain exception |
| Sai XSD, root đúng | Validation interceptor hoạt động; không giả định domain resolver nhận lỗi |
| Interceptor trả `false` | Endpoint không chạy; phản hồi lỗi theo chính sách |
| Fault detail XML | QName, thứ tự, mã lỗi, namespace và XSD đúng contract |
| SOAP 1.1 vs SOAP 1.2 | Fault Code/Reason/Detail và HTTP binding đúng |
| Client `WebServiceTemplate` | Đường SOAP Fault được xử lý khác response thành công |
| HTTP 502/HTML hoặc TLS lỗi | Không bị phân loại nhầm thành SOAP Fault domain |
| Response Fault chứa dữ liệu nhạy cảm | Không lộ stack trace, key/token hoặc PII |

### 16.2. Dùng `MockWebServiceClient` cho SOAP handler

Một test mock Spring-WS có thể gửi request đúng QName khiến endpoint ném `OrderNotFoundException`:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.clientOrSenderFault;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

class OrderSoapFaultTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void notFoundIsMappedToClientFault() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(applicationContext);

        String request =
                "<o:GetOrderRequest " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:orderId>ORD-9999</o:orderId>" +
                "</o:GetOrderRequest>";

        client.sendRequest(withPayload(new StringSource(request)))
              .andExpect(clientOrSenderFault());
    }
}
~~~

Đây là **mẫu kiểm thử**, giả định Spring test context đã được khởi tạo với endpoint và resolver; `@Autowired` một mình không kích hoạt Spring test engine. Khi dùng Spring Boot, cần cấu hình test như `@SpringBootTest` và dependency Spring-WS test tương thích. Matcher có thể khác theo phiên bản; hãy đối chiếu API `ResponseMatchers` thực tế khi build.

Để test chặt hơn, ngoài loại Fault, hãy kiểm tra:

- Fault reason **chính xác** theo hợp đồng.
- Không có response `GetOrderResponse` trong trường hợp lỗi.
- Fault detail nếu contract định nghĩa.
- Thứ tự ưu tiên resolver có hiệu lực; không dùng fallback ngoài ý muốn.
- Không có stack trace hoặc dữ liệu nhạy cảm trong SOAP Envelope.

Test chỉ assert Fault type **chưa chứng minh** ánh xạ lớp ngoại lệ được chọn đúng nếu nhiều exception cùng tạo `Client`. Nên có test riêng từng exception và các reason/detail phân biệt.

### 16.3. Test phân nhánh với nghiệp vụ giả lập

Trong test, có thể tạo service nghiệp vụ giả lập trả các tình huống:

~~~text
OrderService.findById("ORD-1001") → kết quả FOUND
OrderService.findById("ORD-9999") → OrderNotFoundException
OrderService.findById("ORD-0000") → PartnerServiceUnavailableException
OrderService.findById("ORD-8888") → RuntimeException nội bộ
~~~

Điều quan trọng là đường vào vẫn có **SOAP Body hợp XSD**. Nếu test dùng payload sai ngay từ đầu, validation interceptor có thể chặn trước và bạn sẽ không kiểm thử được resolver của domain exception.

### 16.4. Kiểm thử HTTP(S) ngoài mock

`MockWebServiceClient` kiểm tra Spring-WS handler/resolver trong context, nhưng không kiểm tra đầy đủ Servlet mapping, gateway, TLS, Content-Type và HTTP status thực tế.

Với SOAP 1.1, một request qua HTTP có thể có:

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
    <soap:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-9999</o:orderId>
        </o:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Giả định WSDL operation/binding chấp nhận action rỗng; với WSDL thật phải gửi action đã công bố. Kiểm tra toàn bộ HTTP response, `Content-Type`, Envelope namespace, Fault code/reason, phần detail và correlation ID. Với SOAP 1.2, lặp lại bằng binding và media type phù hợp, không chỉ thay namespace.

## 17. Chẩn đoán lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Endpoint ném exception nhưng client nhận Fault mặc định | Resolver không được đăng ký hoặc bị resolver khác bắt trước | Kiểm tra context và `order` của toàn chain |
| Mapping class không hoạt động | Sai tên package, subclass khác, giá trị `Properties` sai | Kiểm tra class runtime và cấu hình mapping |
| Mọi exception đều thành SERVER | Resolver có `defaultFault` ưu tiên quá cao | Đưa mapping chuyên biệt lên trước; test fallback |
| Một lỗi database bị báo là Client | Mapping quá rộng như `Exception -> CLIENT` | Thu hẹp mapping, giữ server fallback |
| SOAP Fault không có `err:OrderError` | Resolver chỉ tạo code/reason, chưa tùy chỉnh detail | Thiết kế XSD/WSDL fault và detail writer |
| Client Java không nhận typed fault exception | WSDL thiếu `wsdl:fault` hoặc detail QName không khớp | Kiểm tra WSDL, XSD và XML thực tế |
| SOAP 1.2 Fault có cấu trúc lạ | SoapMessageFactory/binding/version không khớp | Kiểm tra SOAP 1.2, HTTP media type và Fault codes |
| Request sai XSD không vào resolver domain | Validator xử lý trước endpoint | Test validation interceptor riêng |
| Error ở `@ControllerAdvice` không chạy | Đang ở Spring-WS chứ không phải MVC | Dùng EndpointExceptionResolver phù hợp |
| Ném lỗi từ `ClientInterceptor` nhưng server resolver không xử lý | Lỗi xảy ra ở client khác hoặc transport | Phân biệt nơi exception phát sinh |
| Fault chứa message SQL/stack trace | Dùng `ex.getMessage()` không kiểm soát | Mapping public reason tĩnh, log nội bộ |
| HTTP 500 từ gateway nhưng không có SOAP Fault | Server/gateway trả HTML hoặc body khác | Đọc Content-Type và HTTP response |
| Fault đúng trong mock nhưng sai qua proxy | Config SOAP servlet/version khác, gateway thay response | Kiểm thử transport end-to-end |
| Client retry tạo bản ghi trùng | Không phân loại lỗi và trạng thái transaction | Idempotency/reconciliation theo domain |

### 17.1. Quy trình debug từ ngoài vào trong

1. **Xác minh URL:** `soap:address` trong WSDL có trỏ đúng Servlet/gateway không?
2. **Xác minh SOAP version:** Envelope và HTTP media type có khớp binding không?
3. **Xác minh QName:** root SOAP Body có map tới endpoint không?
4. **Xác minh exception:** lớp Java thực tế bị ném ra là gì, có bị wrap không?
5. **Xác minh resolver chain:** các resolver nào tồn tại, thứ tự nào, có fallback quá rộng không?
6. **Xác minh mapping value:** exception class name và Fault definition có hợp lệ không?
7. **Xác minh Fault XML:** có Code/Reason/Detail đúng namespace và kiểu SOAP không?
8. **Xác minh security:** có interceptor nào chặn request hoặc thay đổi Fault trước khi gửi không?
9. **Xác minh client:** client có thật sự nhận SOAP Fault hay lỗi HTTP/TLS khác?
10. **Xác minh contract:** Fault detail có được XSD/WSDL định nghĩa và client sinh mã đúng không?

Không thay một lúc URL, XSD, resolver order và WS-Security policy. Hãy cố định một request đầu vào rồi kiểm tra từng tầng để tách nguyên nhân.

## 18. Bài tập tình huống: lỗi thanh toán bị map sai

Một hệ thống thanh toán nhận `CreatePaymentRequest` và gọi API ngân hàng. Các exception:

~~~text
PaymentValidationException      → thiếu dữ liệu bắt buộc
InsufficientBalanceException    → không đủ số dư
BankTimeoutException            → ngân hàng không phản hồi
IllegalStateException           → lỗi lập trình hoặc trạng thái bất ngờ
~~~

Đội phát triển khai báo hai resolver:

~~~text
Resolver A (order=0):
  defaultFault = CLIENT,Invalid request

Resolver B (order=10):
  PaymentValidationException   -> CLIENT,Invalid payment
  InsufficientBalanceException -> CLIENT,Insufficient balance
  BankTimeoutException         -> SERVER,Service unavailable
~~~

Client luôn thấy `Invalid request`, kể cả khi ngân hàng timeout.

**Câu hỏi:**

1. Vì sao các mapping trong Resolver B có thể không được sử dụng?
2. Có nên giữ `defaultFault=CLIENT` ở Resolver A không?
3. `BankTimeoutException` có chứng minh giao dịch chưa được thực hiện không?
4. Làm thế nào để client phân biệt `InsufficientBalanceException` với lỗi validation mà không so sánh chuỗi tiếng Anh?
5. Nếu interceptor WS-Security từ chối signature trước endpoint, có nên mong Resolver B xử lý exception của business service không?
6. Nếu lỗi do `IllegalStateException` chưa biết nguyên nhân, Fault public nên chứa thông tin nào?

**Đáp án gợi ý:**

1. Resolver A có ưu tiên cao và fallback xử lý rộng, nên có thể kết thúc chain trước khi B nhận ngoại lệ.
2. **Không nên** dùng client Fault làm fallback chung cho lỗi hệ thống; đặt mapping chuyên biệt trước và server fallback an toàn ở cuối.
3. **Không.** Ngân hàng có thể đã xử lý rồi nhưng response bị mất; cần idempotency key và truy vấn đối soát.
4. Dùng mã lỗi có cấu trúc trong SOAP Fault detail, được XSD/WSDL công bố, ví dụ `INSUFFICIENT_BALANCE`.
5. **Không.** Lỗi ở interceptor/security có thể có luồng xử lý riêng trước khi endpoint/ngoại lệ nghiệp vụ xuất hiện.
6. Fault công khai tổng quát như `Internal service error` kèm correlation ID không nhạy cảm; stack trace và nguyên nhân giữ trong log bảo vệ.

### 18.1. Thực hành cải thiện hệ thống

Hãy thiết kế lại:

- Một bộ exception domain có ý nghĩa rõ ràng.
- Một `SoapFaultMappingExceptionResolver` cho các lỗi domain được biết, không dùng mapping `Exception → CLIENT` quá rộng.
- Một fallback **server error** an toàn và có độ ưu tiên đúng.
- XSD `PaymentError` với `code`, `correlationId` và một WSDL fault contract khi client yêu cầu typed fault.
- Kiểm thử cả SOAP 1.1 và SOAP 1.2 nếu ứng dụng hỗ trợ hai binding.
- Kiểm thử mapping domain, schema validation, security failure, timeout, HTTP gateway error và retry/idempotency như các đường khác nhau.

**Tiêu chí đạt:** mỗi ngoại lệ đã biết tạo Fault public đúng chính sách, lỗi chưa biết không rò rỉ thông tin, resolver không che mất mapping chuyên biệt, và client không cần phụ thuộc tên Java exception.

## 19. Checklist đưa vào production

Trước khi công bố dịch vụ SOAP cho đối tác, hãy xác minh:

1. **Contract-first:** XSD/WSDL mô tả các operation, payload và fault detail cần thiết.
2. **Exception taxonomy:** phân biệt dữ liệu đầu vào, lỗi nghiệp vụ, lỗi hệ thống và lỗi bảo mật.
3. **Resolver registration:** bean nằm trong application context đúng của `MessageDispatcher`.
4. **Mapping chính xác:** dùng exception class name ổn định, không parse thông điệp lỗi tự do.
5. **Resolver ordering:** mapping chuyên biệt không bị default fault rộng che khuất.
6. **Fault code:** SOAP 1.1 Client/Server và SOAP 1.2 Sender/Receiver được kiểm thử đúng binding.
7. **Fault reason:** thông điệp công khai ổn định, không lộ stack trace hoặc bí mật.
8. **Fault detail:** QName, namespace, kiểu dữ liệu và lỗi WSDL typed fault được kiểm thử nếu sử dụng.
9. **XSD validation:** các lỗi payload không bị nhầm với domain exception do endpoint ném.
10. **WS-Security/TLS:** signature, header, certificate và lỗi transport được xử lý theo lớp tương ứng.
11. **SOAP client:** phân biệt `SoapFaultClientException`, JAXB failure, HTTP/proxy và timeout.
12. **Retry policy:** chỉ retry khi được phép, có idempotency/reconciliation cho tác vụ ghi.
13. **Observability:** correlation ID, operation QName, fault code và metrics nội bộ có masking.
14. **Compatibility:** thử bằng client Java và ít nhất một implementation khác khi hợp đồng yêu cầu.
15. **Regression:** mỗi lần đổi exception hierarchy, mapping, XSD/WSDL hoặc Spring-WS version đều chạy lại test Fault.

## 20. Ghi nhớ

- **`SoapFaultMappingExceptionResolver`** ánh xạ **lớp ngoại lệ Java → SOAP Fault definition** trong Spring-WS server; nó không phải cơ chế xử lý mọi HTTP exception.
- **`setExceptionMappings(Properties)`** chứa quy tắc theo exception class; **`setDefaultFault(...)`** cung cấp lỗi dự phòng, cần tránh che mapping chuyên biệt.
- **`setOrder(...)`** ảnh hưởng thứ tự khi có nhiều `EndpointExceptionResolver`; resolver có fallback quá rộng đặt sớm có thể cướp quyền xử lý lỗi.
- **SOAP 1.1** dùng `faultcode`/`faultstring`/`detail`, còn **SOAP 1.2** dùng `Code`/`Reason`/`Detail`. Không trộn cấu trúc hoặc HTTP binding giữa hai phiên bản.
- **Mapping đơn giản chủ yếu xác định Fault code và reason**; muốn có **typed Fault detail** cần thiết kế XSD/WSDL cùng cơ chế tạo XML detail đúng contract.
- **`PayloadValidatingInterceptor`, WS-Security, XML parser và JAXB** có những đường lỗi riêng; không phải mọi lỗi đều đi qua exception resolver của endpoint.
- **Phía client**, SOAP Fault thường đi qua `SoapFaultClientException`, khác response JAXB thành công và khác lỗi HTTP/TLS/timeout.
- **Không trả `ex.getMessage()` hoặc stack trace tùy ý** cho đối tác; ghi log nội bộ có kiểm soát và xuất mã lỗi ổn định.
- **Không retry mù quáng** chỉ vì Fault phía server hoặc timeout; nghiệp vụ có tác dụng phụ cần idempotency và đối soát.
- **Kiểm thử toàn bộ SOAP contract**, bao gồm exception mapping, Fault XML, resolver order, XSD/WSDL, WS-Security và khả năng tương thích đa nền tảng, để tích hợp doanh nghiệp ổn định.
