# JdkHttpClientMessageSender và kiểm tra khả năng hỗ trợ theo phiên bản

Trong **Spring Web Services (Spring-WS)**, SOAP client không tự gửi XML ra mạng chỉ nhờ `Jaxb2Marshaller` hoặc `WebServiceTemplate`. Giữa đối tượng JAXB và máy chủ có một lớp **transport** chịu trách nhiệm mở kết nối, thực hiện HTTP POST, gửi SOAP Envelope, nhận HTTP response và trả dữ liệu cho SOAP message factory. Một lựa chọn cho tầng này là **`JdkHttpClientMessageSender`**, sử dụng `java.net.http.HttpClient` của JDK.

Chủ đề thuộc chương **HTTP và kết nối** của module `SPRING_WEB_SERVICES`: phát triển SOAP contract-first với XSD/WSDL, JAXB, endpoint, client, interceptor, SOAP Fault, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Bài tập trung vào **kiểm tra khả năng hỗ trợ theo đúng phiên bản Spring-WS** và chọn/cấu hình HTTP message sender phù hợp thay vì đoán theo tên thư viện.

> **Điểm quan trọng:** Không được đồng nhất việc JDK có `java.net.http.HttpClient` với việc Spring-WS version đang chạy có `org.springframework.ws.transport.http.JdkHttpClientMessageSender`. JDK cung cấp HTTP client gốc; Spring-WS phải cung cấp **adapter triển khai `WebServiceMessageSender`** để `WebServiceTemplate` sử dụng nó.

Các ví dụ Java phía dưới minh họa một ứng dụng dùng JDK 17+, Spring-WS có class nói trên, SOAP 1.1 và JAXB model từ XSD. Endpoint URL, package JAXB, timeout và chính sách TLS đều là dữ liệu ví dụ cần thay theo dự án thật.

## 1. Vị trí của JdkHttpClientMessageSender trong SOAP client

Một chuỗi gọi SOAP contract-first thường đi qua các tầng:

~~~mermaid
flowchart TD
    A["Service Java / JAXB request"] --> B["WebServiceTemplate"]
    B --> C["Marshaller + SOAP MessageFactory"]
    C --> D["ClientInterceptor / WS-Security"]
    D --> E["WebServiceMessageSender"]
    E --> F["JdkHttpClientMessageSender"]
    F --> G["java.net.http.HttpClient"]
    G --> H["DNS / proxy / TCP / TLS / HTTP"]
    H --> I["SOAP endpoint / gateway"]
    I --> J["HTTP response: status + bytes"]
    J --> K["SOAP parser / Fault resolver / Unmarshaller"]
    K --> A
~~~

Sơ đồ gom các bước theo trách nhiệm, không cam kết thứ tự nội bộ chính xác của mọi interceptor/callback. Phải tách rõ:

| Thành phần | Vai trò | Không chịu trách nhiệm |
| --- | --- | --- |
| `WebServiceTemplate` | Điều phối gửi request/nhận response và áp dụng callback, fault resolver. | Không tự chọn logic SOAP operation từ tên Java method. |
| `Jaxb2Marshaller` | Chuyển object Java thành XML payload và ngược lại. | Không mở HTTP connection hoặc xác minh TLS. |
| `SaajSoapMessageFactory` / Axiom | Tạo/parse SOAP Envelope, Header, Body/Fault. | Không quyết định proxy và connect timeout. |
| **`JdkHttpClientMessageSender`** | Kết nối `WebServiceTemplate` với JDK `HttpClient` qua giao diện Spring-WS transport. | Không sinh WSDL, không marshal JAXB, không tạo WS-Security chữ ký. |
| `java.net.http.HttpClient` | Quản lý HTTP protocol, kết nối, proxy, TLS, redirects và các lựa chọn JDK phù hợp. | Không hiểu QName SOAP payload hay XSD. |
| `ClientInterceptor` / security layer | Bổ sung/kiểm tra SOAP message, headers và WS-Security theo cấu hình. | Không tự điều chỉnh timeout của JDK HTTP client. |
| SOAP server `MessageDispatcherServlet` | Nhận request, route tới `@Endpoint`. | Không bị thay đổi chỉ vì phía client đổi message sender. |

**Đổi message sender là đổi tầng kết nối phía client.** WSDL/XSD và JAXB DTO không tự thay đổi, nhưng hành vi timeout, TLS, HTTP versions, proxy, authentication và xử lý status có thể thay đổi; vì vậy cần integration test.

### 1.1. Transport URL khác URL WSDL

Giả sử WSDL được công bố tại:

~~~text
GET https://orders.example.test/ws/orders.wsdl
~~~

nhưng `soap:address` bên trong WSDL là:

~~~xml
<soap:address location="https://orders.example.test/ws"/>
~~~

Thì SOAP client thường gửi:

~~~http
POST /ws HTTP/1.1
Host: orders.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/CreateOrder"
~~~

**Không gửi SOAP POST tới `/ws/orders.wsdl` chỉ vì đó là đường tải hợp đồng.** `setDefaultUri(...)` trong `WebServiceTemplate` phải là SOAP endpoint address theo môi trường, không mặc định là URL GET WSDL.

## 2. Xác minh lớp có thật ở phiên bản đang chạy

Đây là bước **bắt buộc** trước khi copy cấu hình. Những bản Spring-WS khác nhau có thể hỗ trợ transport khác nhau và có các setter/constructor thay đổi theo release.

### 2.1. Những mốc có thể đối chiếu từ Javadoc chính thức

| Dòng/bản Spring-WS | Bằng chứng từ API docs | Kết luận an toàn |
| --- | --- | --- |
| **4.0.4** | Danh sách *All Classes and Interfaces* của bản này **không liệt kê** `JdkHttpClientMessageSender`. | **Không giả định** có class đó trên classpath của 4.0.4. |
| **4.0.6** | Javadoc bản này **có** `JdkHttpClientMessageSender`, constructor mặc định/nhận `HttpClient` và setters timeout kiểu `Duration`. | Có thể cấu hình nếu dependency/runtime tương thích. |
| **4.0.9, 4.0.17** | Javadoc các bản này có lớp adapter. | Vẫn xem Javadoc của **patch version thực tế**. |
| **4.1.4** | Javadoc có class, `setHttpClient`, `setConnectionTimeout`, `setRequestTimeout` và constructors. | Có bằng chứng API rõ ràng cho 4.1.4. |
| **5.0.0-M1** | Javadoc milestone còn có class nói trên. | Milestone chỉ chứng minh ở **bản milestone đó**, không bảo đảm mọi patch tương lai hoặc đường nâng cấp đều giống. |

Một chi tiết dễ nhầm: Javadoc của class ở các bản có hỗ trợ hiển thị **`Since: 4.0`**. Đây là metadata về dòng API, **không phải bằng chứng lớp tồn tại trong mọi bản 4.0.0–4.0.4**. Chính vì thế phải kiểm tra JAR/Javadoc **đúng bản phát hành**, thay vì suy từ `@since` hoặc tài liệu của nhánh `current`.

Các trang để tra cứu (tên tài liệu và nội dung có thể đổi khi site cập nhật):

- [Spring-WS 4.0.4 — danh sách lớp](https://docs.spring.io/spring-ws/docs/4.0.4/api/allclasses-index.html).
- [Spring-WS 4.0.6 — JdkHttpClientMessageSender](https://www.springframework.org/spring-ws/docs/4.0.6/api/org/springframework/ws/transport/http/JdkHttpClientMessageSender.html).
- [Spring-WS 4.1.4 — JdkHttpClientMessageSender](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/transport/http/JdkHttpClientMessageSender.html).
- [Spring-WS 5.0.0-M1 — JdkHttpClientMessageSender](https://docs.spring.io/spring-ws/docs/5.0.0-M1/api/org/springframework/ws/transport/http/JdkHttpClientMessageSender.html).
- [Spring-WS 4.1.4 — Reference, HTTP transports](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/).

### 2.2. Dependency thực tế quan trọng hơn tên Spring Boot starter

Khi dự án dùng Spring Boot starter SOAP, có thể có **BOM/dependency management** chọn phiên bản `spring-ws-core`. Đừng kết luận khả năng hỗ trợ chỉ từ tên starter hoặc phiên bản Spring Boot nếu chưa xem **dependency đã resolve**.

Ví dụ các lệnh kiểm tra **cho người học chạy trong dự án của mình**:

~~~bash
# Maven: xem spring-ws-core đang được resolve qua dependency tree.
./mvnw dependency:tree -Dincludes=org.springframework.ws:spring-ws-core

# Gradle: xem dependency cụ thể và bản đã được chọn.
./gradlew dependencyInsight --dependency spring-ws-core --configuration runtimeClasspath
~~~

Các lệnh này là **hướng dẫn**, không phải kết quả phân tích repository hiện tại; Maven/Gradle wrapper có thể khác theo dự án. Hãy tìm:

- `org.springframework.ws:spring-ws-core` với version chính xác.
- Các bản bị ép/version override hoặc transitive dependency conflict.
- Spring Framework, Spring Boot, JAXB/Jakarta API và JDK đang chạy.
- Có nhiều JAR Spring-WS thuộc các version khác nhau cùng nằm trên runtime classpath hay không.

Một `import org.springframework.ws.transport.http.JdkHttpClientMessageSender;` compile được ở IDE không chứng minh production chạy đúng nếu dependency của test/dev và deployment khác nhau.

### 2.3. Kiểm tra class trong JAR thay vì đoán

Sau khi xác định **đúng file JAR `spring-ws-core` đang được đóng gói**, có thể kiểm tra nó chứa class hay không:

~~~bash
jar tf spring-ws-core-<actual-version>.jar | grep 'JdkHttpClientMessageSender.class'
~~~

Lệnh trên là cú pháp minh họa cho shell có `grep`; trên Windows có thể dùng `findstr`. Ký hiệu `<actual-version>` phải được thay bằng tên version thực và không được gõ nguyên literal vào command. Dùng `javap` hoặc Javadoc của đúng JAR để xác nhận constructor/setter:

~~~bash
javap -classpath spring-ws-core-<actual-version>.jar org.springframework.ws.transport.http.JdkHttpClientMessageSender
~~~

Trên JDK module path, `java.net.http.HttpClient` thuộc module `java.net.http`. Nếu ứng dụng có `module-info.java`, cần khai báo module phù hợp và kiểm tra cả các module của Spring; với ứng dụng Spring Boot thông thường trên classpath, không cần tự tạo module descriptor chỉ để dùng JDK client.

### 2.4. Khi không hỗ trợ: không cố import class từ JAR khác

Nếu version đang chạy **không có** sender:

1. Chọn `HttpUrlConnectionMessageSender`/sender khác đã hỗ trợ trên version đó, hoặc nâng cấp Spring-WS theo BOM được hỗ trợ.
2. Không tự copy một `JdkHttpClientMessageSender.class` từ version mới vào classpath cũ để “bù” tính năng; binary compatibility có thể sai.
3. Không áp dụng code sử dụng `setRequestTimeout(Duration)` cho sender khác vốn dùng API timeout khác.
4. Khi nâng version, test lại SOAP 1.1/1.2, JAXB, Fault, security headers, TLS và interoperability, không chỉ test import.

**Kết luận của bước kiểm tra:** chỉ khi class/API có thật trong `spring-ws-core` và JDK/runtime tương thích, mới tiếp tục cấu hình. Không chọn dựa vào suy đoán từ tài liệu `current`.

## 3. API của JdkHttpClientMessageSender và vòng đời kết nối

Tại các bản Spring-WS có class này (ví dụ 4.0.6 và 4.1.4), tên đầy đủ là:

~~~java
org.springframework.ws.transport.http.JdkHttpClientMessageSender
~~~

Nó triển khai giao diện `WebServiceMessageSender`, dùng `java.net.http.HttpClient` để gửi **HTTP POST** chứa SOAP message. Hai cách khởi tạo đã được Javadoc công bố:

~~~java
// Tạo sender để Spring-WS cấu hình HttpClient mặc định.
JdkHttpClientMessageSender sender1 = new JdkHttpClientMessageSender();

// Dùng HttpClient được ứng dụng xây trước.
HttpClient httpClient = HttpClient.newHttpClient();
JdkHttpClientMessageSender sender2 =
        new JdkHttpClientMessageSender(httpClient);
~~~

Trong Java ví dụ này `HttpClient` có import `java.net.http.HttpClient`, **không phải** `org.apache.http.client.HttpClient` hay `org.apache.hc.client5.http.classic.HttpClient`.

Những setter chính được Javadoc 4.1.4 công bố:

| API | Kiểu | Mục đích |
| --- | --- | --- |
| `JdkHttpClientMessageSender()` | Constructor | Dùng đường cấu hình JDK HTTP client mặc định của sender. |
| `JdkHttpClientMessageSender(HttpClient)` | Constructor | Cung cấp HTTP client được cấu hình từ bên ngoài. |
| `setHttpClient(HttpClient)` | Setter | Thay object HTTP client mà sender dùng. |
| `setConnectionTimeout(Duration)` | Setter | Cấu hình timeout kết nối theo cơ chế implementation. |
| `setRequestTimeout(Duration)` | Setter | Cấu hình thời hạn request theo cơ chế implementation. |
| `createConnection(URI)` | Method | Tạo `WebServiceConnection` đến URI. |
| `afterPropertiesSet()` | Lifecycle | Kiểm tra/khởi tạo state khi Spring bean được tạo. |

**Quan trọng:** `createConnection(URI)` là API framework, không nên gọi thủ công để né `WebServiceTemplate` khi xây SOAP client thông thường. Cho Spring quản lý bean và lifecycle của sender, để framework còn xử lý SOAP serialization, Fault, callbacks và connection cleanup.

### 3.1. Cấu hình tối giản với sender mặc định

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.JdkHttpClientMessageSender;

@Configuration
public class JdkSenderConfig {

    @Bean
    public JdkHttpClientMessageSender jdkSender() {
        JdkHttpClientMessageSender sender =
                new JdkHttpClientMessageSender();

        sender.setConnectionTimeout(Duration.ofSeconds(3));
        sender.setRequestTimeout(Duration.ofSeconds(15));
        return sender;
    }
}
~~~

Đoạn này chỉ định **timeout ở sender** và dùng đường khởi tạo mặc định. Nó **chưa** chứng minh `WebServiceTemplate` đang sử dụng bean đó. Cần đăng ký bean với template ở mục tiếp theo.

**Không đổi nhầm đơn vị**: JDK sender nhận `java.time.Duration`, không phải số millisecond kiểu `int`. Các sender khác như Apache hoặc HttpURLConnection ở version khác có setter khác. Nếu copy từ code cũ `setReadTimeout(5000)` mà API JDK sender không có, đó là sai class/phiên bản.

### 3.2. Một HttpClient có thể phục vụ nhiều request

`java.net.http.HttpClient` được thiết kế để sử dụng lại. Không tạo mới client cho **mỗi** SOAP request nếu không có lý do rõ, vì có thể mất cơ hội reuse connection, tăng socket/TLS handshakes và tài nguyên.

Mô hình thường dùng:

~~~text
Spring singleton bean: java.net.http.HttpClient
       |
       +-- Spring-WS JdkHttpClientMessageSender bean
                  |
                  +-- WebServiceTemplate
                         |
                         +-- SOAP call 1
                         +-- SOAP call 2
                         +-- SOAP call N
~~~

JDK client có thể quản lý keep-alive/connection reuse nội bộ, nhưng **mức độ pooling, connection lifetime, TLS session reuse và số connection** còn phụ thuộc JDK, HTTP version, proxy, server và tải. Không tuyên bố cứ dùng JDK sender thì connection pool luôn có dung lượng/timeout giống Apache HttpClient.

Cũng không đổi config mutable của sender đang được gọi đồng thời. Hãy tạo bean hoàn chỉnh trước khi ứng dụng phục vụ traffic; cấu hình lại transport thường cần rollout/test rõ ràng.

### 3.3. JDK `HttpClient` không làm WebServiceTemplate bất đồng bộ

Dù `java.net.http.HttpClient` có API `sendAsync`, Spring-WS `WebServiceTemplate.marshalSendAndReceive(...)` vẫn là **lời gọi đồng bộ** theo contract của template. Thay message sender không tự biến endpoint thành reactive stream hay non-blocking API.

Nếu yêu cầu bất đồng bộ, cần thiết kế ở tầng orchestration/executor/queue, concurrency limits và context propagation, không giả định “JDK HttpClient = SOAP async”. Với SOAP operation có side effect, task retry và timeout vẫn cần idempotency.

## 4. Gắn sender vào WebServiceTemplate đúng cách

Đây là cấu hình client SOAP **contract-first** khi đã sinh JAXB model từ XSD. Giả sử model nằm ở package `com.example.orders.contract`.

~~~java
package com.example.orders.config;

import java.time.Duration;
import java.net.http.HttpClient;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.http.JdkHttpClientMessageSender;

@Configuration
public class OrdersSoapClientConfig {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.contract");
        return marshaller;
    }

    @Bean
    public HttpClient ordersJdkHttpClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }

    @Bean
    public JdkHttpClientMessageSender ordersMessageSender(
            HttpClient ordersJdkHttpClient) {
        JdkHttpClientMessageSender sender =
                new JdkHttpClientMessageSender(ordersJdkHttpClient);
        sender.setRequestTimeout(Duration.ofSeconds(15));
        return sender;
    }

    @Bean
    public WebServiceTemplate ordersTemplate(
            Jaxb2Marshaller ordersMarshaller,
            JdkHttpClientMessageSender ordersMessageSender) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri("https://orders.example.test/ws");
        template.setMarshaller(ordersMarshaller);
        template.setUnmarshaller(ordersMarshaller);
        template.setMessageSender(ordersMessageSender);
        return template;
    }
}
~~~

**Các giả định:**

- Spring-WS runtime có `JdkHttpClientMessageSender` và class JAXB từ `orders.xsd` có metadata phù hợp.
- `orders.example.test` chỉ là hostname minh họa, không phải địa chỉ dịch vụ đang hoạt động.
- WSDL binding dùng **SOAP 1.1**, nên ví dụ ưu tiên HTTP/1.1 ở client để giảm biến số interoperability; đây không phải yêu cầu chung rằng SOAP chỉ chạy HTTP/1.1.
- Bean `Jaxb2Marshaller` có thể cần cấu hình khác nếu XJC sinh `JAXBElement` hoặc nhiều packages; không tự sinh Java classes bằng khai báo context path.
- Cấu hình timeout, TLS/proxy/authentication và connection reuse cần phù hợp SLA thực tế, không copy nguyên 3/15 giây từ ví dụ.

Điểm phân biệt: **`setMessageSender(ordersMessageSender)` trên template** là bước bảo đảm client dùng sender đó. Chỉ khai báo `@Bean JdkHttpClientMessageSender` trong ApplicationContext **không nhất thiết** khiến mọi `WebServiceTemplate` tự chuyển sang sử dụng nó.

### 4.1. Không cấu hình connection timeout chồng chéo mơ hồ

Khi **tự tạo `HttpClient`** bằng `HttpClient.newBuilder().connectTimeout(...)`, nên đặt connect timeout tại JDK builder như ví dụ và không tự giả định `sender.setConnectionTimeout(...)` sẽ sửa client đã build. JDK `HttpClient` được cấu hình theo mô hình builder; sau khi build, các lựa chọn connection/TLS/proxy không được mutate tùy ý.

Có thể lựa chọn **một trong hai đường**:

1. **Sender mặc định:** `new JdkHttpClientMessageSender()` rồi dùng các setters được Javadoc chính xác hỗ trợ.
2. **Client tùy chỉnh:** build `HttpClient` với `connectTimeout`, proxy, SSL context, redirects, executor..., truyền vào constructor hoặc `setHttpClient(...)`; cấu hình request timeout theo API sender.

Không trộn cả hai đường khi không hiểu precedence/implementation của đúng version.

### 4.2. Gửi SOAPAction theo WSDL binding

`JdkHttpClientMessageSender` không tự suy SOAPAction từ tên Java class hoặc tên method. Với SOAP 1.1, bạn có thể dùng `SoapActionCallback`:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

Object reply = ordersTemplate.marshalSendAndReceive(
    createOrderRequest,
    new SoapActionCallback("urn:example:orders:v1/CreateOrder")
);
~~~

`ordersTemplate` và `createOrderRequest` là object/bean đã tồn tại ở ứng dụng; SOAPAction là **giá trị minh họa**, phải đối chiếu `soap:operation soapAction` trong WSDL thực tế. SOAP 1.2 có cách biểu diễn action khác ở HTTP media type và SOAP processing; không copy `text/xml`/SOAPAction của SOAP 1.1 sang mọi binding.

### 4.3. Client chọn một sender hay nhiều sender?

`WebServiceTemplate` hỗ trợ đăng ký message sender hoặc nhiều senders theo URI/transport trong những version có API tương ứng. Đối với một SOAP endpoint HTTPS duy nhất, **một sender** là cấu hình dễ quan sát.

Nếu ứng dụng có cả HTTP/JMS transports hoặc các sender dành cho đích khác nhau, phải bảo đảm lựa chọn sender theo URI đúng như framework hỗ trợ. Không gắn hai sender cùng hỗ trợ `https` rồi giả định framework sẽ tự fail over khi một sender lỗi; failover/retry cần logic riêng có kiểm thử.

### 4.4. Đổi sender không thay message factory

~~~text
WebServiceTemplate
  ├── messageFactory: SaajSoapMessageFactory / AxiomSoapMessageFactory
  ├── marshaller: Jaxb2Marshaller
  ├── messageSender: JdkHttpClientMessageSender
  ├── faultResolver: SOAP Fault strategy
  └── interceptors: security, tracing, validation (tùy cấu hình)
~~~

Một client muốn xử lý SOAP 1.2 phải cấu hình SOAP message factory và contract binding phù hợp. **Không có `setSoapVersion(...)` trên JDK sender để đổi SOAP version**: đó thuộc SOAP message factory. Tương tự, SOAP Fault được parse/xử lý bởi SOAP stack và fault resolver, không phải tự động bởi JDK `HttpClient`.

## 5. Timeout: kết nối, request và deadline tổng thể

Một lỗi tích hợp phổ biến là gọi mọi thời hạn “read timeout”. Trên JDK HTTP client và Spring-WS adapter, cần phân biệt:

| Khái niệm | Bắt đầu/kết thúc về mặt ý nghĩa | Nơi thường cấu hình |
| --- | --- | --- |
| **Connect timeout** | Giới hạn chờ thiết lập kết nối mới khi điều kiện áp dụng. | `HttpClient.Builder.connectTimeout(Duration)` hoặc setter sender được hỗ trợ. |
| **Request timeout** | Thời hạn dành cho việc gửi request và nhận kết quả theo cơ chế JDK/sender. | `JdkHttpClientMessageSender#setRequestTimeout(Duration)`. |
| **DNS timeout** | Độ trễ phân giải hostname. | Không mặc định được khống chế tuyệt đối bởi connect timeout trong mọi JDK/môi trường. |
| **TLS handshake** | Thỏa thuận TLS/hostname/certificate trust. | Phụ thuộc JDK HTTP client, SSL stack và thời hạn/request lifecycle. |
| **End-to-end deadline** | Tổng thời gian nghiệp vụ được phép cho một call, bao gồm retries/backoff. | Tầng ứng dụng/orchestration, không chỉ một setter. |
| **Proxy/gateway timeout** | Giới hạn ở reverse proxy, LB, API gateway. | Cấu hình hạ tầng riêng. |

Không kết luận “`setRequestTimeout(Duration.ofSeconds(15))` bảo đảm toàn bộ giao dịch kết thúc sau đúng 15 giây” trong mọi tình huống. DNS, TLS, HTTP/2 negotiation, scheduler, queue, đọc body/serialization, retries và hệ thống ở giữa có thể ảnh hưởng đến thời điểm ngoại lệ xuất hiện.

### 5.1. Ví dụ xác định ngân sách thời gian

Giả sử luồng nghiệp vụ chỉ cho phép khoảng **20 giây** cho bước gọi Orders SOAP:

~~~text
Total budget                     20 s
 ├─ Prepare/marshal SOAP         ~1 s
 ├─ HTTP connect                 ~3 s (khi cần kết nối mới)
 ├─ Request/response             ~12 s
 └─ Retry/backoff/processing     phần thời gian còn lại
~~~

Các con số chỉ minh họa cách chia **budget**, không phải phép đo hay SLA chung. Nếu mỗi retry tự có request timeout 15 giây và cho 3 attempts, tổng thời gian có thể lớn hơn 20 giây đáng kể. Phải giới hạn **tổng thời gian thực hiện**, số lần retry và tôn trọng deadline từ service gọi.

### 5.2. Timeout không chứng minh server chưa xử lý

~~~mermaid
sequenceDiagram
    participant C as Spring-WS client
    participant S as Orders SOAP
    participant D as Database

    C->>S: CreateOrder, idempotencyKey=op-42
    S->>D: Commit đơn hàng
    D-->>S: orderId=ORD-000184
    Note over C,S: Response mất hoặc timeout
    C->>S: Retry với cùng idempotencyKey (nếu contract cho phép)
    S->>D: Tra cứu kết quả theo key
    D-->>S: ORD-000184
    S-->>C: Trả kết quả cũ
~~~

Nếu một `WebServiceTemplate` ném network/timeout exception sau khi request đã gửi, hãy phân loại **outcome unknown**, không mặc định server chưa commit. Correlation ID chỉ giúp truy vết; **idempotency key** với lưu trữ giao dịch phù hợp mới giúp giảm nguy cơ tạo đơn/thanh toán lặp.

## 6. HTTP version, redirects và khả năng tương thích SOAP

### 6.1. HTTP/1.1 hay HTTP/2?

JDK `HttpClient` có thể dùng HTTP/2 khi server/proxy hỗ trợ; lựa chọn HTTP version ở builder là **ưu tiên/chiến lược**, không bảo đảm tất cả hop sẽ đi đúng protocol đó. Để giảm biến số khi làm việc với SOAP gateway hoặc hệ thống cũ, ví dụ ở mục 4 dùng:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
~~~

Nếu hệ thống đã được kiểm thử với HTTP/2, có thể đánh giá cấu hình tương ứng. SOAP 1.1/1.2 là **phiên bản SOAP**, không phải HTTP/1.1 hay HTTP/2. Một SOAP 1.1 message có thể đi qua HTTP/2 nếu binding/stack hỗ trợ; không trộn hai trục phiên bản.

### 6.2. Redirect không nên là cơ chế mặc định cho SOAP POST

JDK client cho phép cấu hình redirect behavior:

~~~java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

Với SOAP POST, redirect có thể làm thay đổi endpoint đích hoặc cách xử lý request tùy HTTP status, policy và client implementation. Tự động redirect qua hostname khác còn có thể gây rủi ro **lộ thông tin xác thực, message metadata hoặc gửi lệnh nghiệp vụ tới nhầm đích**.

Thực hành an toàn: đặt **SOAP address đúng** ngay từ đầu, dùng HTTPS và endpoint allowlist; nếu đối tác yêu cầu redirect, phải xác minh URI/host/scheme mới, security và khả năng xử lý POST qua redirect trong integration test. Không bật follow-all redirect chỉ vì lỗi `301/302` từ proxy.

### 6.3. Keep-alive và connection reuse

Một `HttpClient` dùng chung thường có thể tái sử dụng kết nối. Nhưng điều đó **không phải** cam kết số kết nối tối đa, TTL, eviction hoặc pool shutdown API giống Apache HttpClient. Khi performance hoặc vận hành đòi kiểm soát pool cụ thể, hãy kiểm tra JDK version, backend và chọn Apache `HttpComponents5MessageSender` nếu nó phù hợp hơn.

Các nguyên nhân phổ biến làm mất reuse: mỗi call tạo client mới, proxy đóng idle connection, server giới hạn keep-alive, TLS/certificate configuration thay đổi, DNS/load-balancing hoặc retry không đúng cách. Hãy đo số connection mới, TLS handshakes, p95/p99 và HTTP status trên hạ tầng thực.

## 7. Proxy, TLS, chứng chỉ và HTTP authentication

Trong môi trường doanh nghiệp, SOAP client có thể đi qua proxy công ty, API gateway, VPN hoặc mTLS. Một sender dùng JDK `HttpClient` cần tuân theo **chính sách mạng và tin cậy** của môi trường, không chỉ hoạt động trên `localhost`.

### 7.1. Cấu hình proxy bằng API JDK

`java.net.http.HttpClient.Builder` hỗ trợ `ProxySelector`. Một ví dụ định hướng:

~~~java
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .proxy(ProxySelector.of(
            new InetSocketAddress("proxy.example.test", 8080)))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

Địa chỉ proxy là ví dụ, không phải proxy khả dụng. Trong production phải dùng địa chỉ/cổng do hệ thống quản lý, có quy tắc `nonProxyHosts`/routing nội bộ được cho phép và chính sách thông qua hoặc bỏ qua proxy đối với từng destination. Không nên tự sửa global JVM proxy properties trong một đoạn helper gọi SOAP nếu nhiều HTTP clients cùng chạy trong tiến trình.

Nếu proxy yêu cầu authentication, thiết kế `Authenticator`/credential provider phù hợp với stack và loại proxy, không ghi username/password vào URL, header log hoặc source code. **Proxy authentication khác với WS-Security** của SOAP Envelope.

### 7.2. HTTPS và truststore

Khi gọi:

~~~text
https://orders.example.test/ws
~~~

JDK HTTP client cần hoàn thành TLS handshake, kiểm tra certificate chain, hostname và trust anchors theo cấu hình. Có thể dùng SSL context được tạo bằng truststore/keystore hợp lệ:

~~~java
import javax.net.ssl.SSLContext;
import java.net.http.HttpClient;

// sslContext được hệ thống khởi tạo từ truststore/keystore
// và policy chứng chỉ đáng tin, không dùng trust-all.
SSLContext sslContext = trustedSslContext;

HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

Đây là **đoạn cấu hình minh họa**, `trustedSslContext` phải được cấp qua cơ chế an toàn của ứng dụng. Tránh các hướng dẫn kiểu `TrustManager` chấp nhận mọi chứng chỉ hoặc tắt hostname verification: chúng phá ranh giới tin cậy và dễ dẫn tới gửi dữ liệu SOAP/tokens cho endpoint giả mạo.

Với **mTLS**:

- Client cần key material/chứng chỉ client để xác thực với server.
- Client vẫn phải **xác minh chứng chỉ server** qua trust material hợp lệ.
- Server/gateway cần kiểm tra chain, mục đích chứng chỉ, mapping identity và authorization.
- Chứng chỉ phải được quản lý vòng đời: hết hạn, rotation, thu hồi, key permissions và secret storage.

`JdkHttpClientMessageSender` chỉ dùng HTTP client đã cấu hình; nó không tự phát hành, ký hay phân phối chứng chỉ.

### 7.3. HTTP authentication không giống WS-Security

| Thành phần | Tầng | Ví dụ | Trách nhiệm |
| --- | --- | --- | --- |
| HTTP Basic/Bearer authentication | HTTP header/proxy/app gateway. | `Authorization: Basic ...` hoặc `Bearer ...`. | Cấu hình HTTP sender/callback/transport đã thỏa thuận. |
| Proxy authentication | HTTP proxy. | `Proxy-Authorization` hoặc cơ chế JDK `Authenticator`. | Chỉ dùng với proxy tin cậy. |
| TLS/mTLS | TLS handshake. | Certificate chain, client key, truststore. | JDK SSL stack/infra. |
| WS-Security | **SOAP Header**. | `wsse:UsernameToken`, `ds:Signature`, timestamp, encryption. | SOAP security interceptor/policy, ví dụ WSS4J. |
| Correlation/trace context | SOAP/HTTP metadata. | `CorrelationId`, `traceparent`. | Truy vết, **không phải credential**. |

Một số đối tác yêu cầu **cả mTLS và WS-Security**. Chỉ đổi từ `HttpComponents5MessageSender` sang JDK sender **không đồng nghĩa policy WS-Security tự tương thích**. Cần kiểm tra thứ tự các bước: tạo SOAP Header/security, ký và mã hóa message, gửi qua HTTPS, nhận SOAP Fault/security response. Không sửa message đã ký bằng callback không được thiết kế để ký lại.

### 7.4. Lỗi chứng chỉ thường không có SOAP Fault

Nếu JDK client ném `SSLHandshakeException` khi không tin chứng chỉ, có thể **chưa có HTTP response và chưa có SOAP message response**. Client nên phân loại là lỗi TLS/transport, không chuyển thành `SOAP Sender Fault` hay `Client Fault`.

Nếu HTTP kết nối thành công nhưng server trả SOAP Fault về UsernameToken/chữ ký sai, đó là lỗi SOAP message security. Hai trường hợp dẫn đến kế hoạch sửa khác nhau: **truststore/hostname/certificate** so với **SOAP Header/security policy/clock skew**.

### 7.5. Giới hạn địa chỉ đích và tránh SSRF

Một SOAP integration client thường gọi danh sách endpoint đã cấu hình, không nhận URL tự do từ request của người dùng. Nếu ứng dụng cho phép thay endpoint URI từ bên ngoài, có thể bị lạm dụng để truy cập mạng nội bộ qua JDK HTTP client.

Biện pháp gợi ý:

- Allowlist scheme `https`, hostname và port theo môi trường.
- Chặn loopback, link-local, internal/metadata endpoints khi chúng không phải đích nghiệp vụ hợp lệ.
- Không follow redirect mù quáng; nếu cho phép, kiểm tra lại từng destination sau redirect.
- Kiểm soát DNS resolution, proxy behavior và quyền outbound ở hạ tầng.
- Không dùng request data để tạo URI kết nối mà không validate/authorize.
- Có giới hạn kích thước SOAP request và response/attachment để tránh cạn tài nguyên.

Giữ ý nghĩa **“địa chỉ đích phải đáng tin”** tách biệt với **“request XML phải hợp lệ XSD”**. XSD validation không ngăn SSRF nếu app tự chọn endpoint URI theo một trường trong Body.

## 8. So sánh các HTTP message sender của Spring-WS

`JdkHttpClientMessageSender` không phải lựa chọn duy nhất. Reference của Spring-WS 4.1.x mô tả `HttpUrlConnectionMessageSender` là implementation mặc định, bên cạnh JDK `HttpClient` và các sender Apache HttpClient. Một số tên class có thể khác theo thế hệ Spring-WS.

| Sender | Nền tảng | Khi nào cân nhắc | Giới hạn/điều cần xác minh |
| --- | --- | --- | --- |
| `HttpUrlConnectionMessageSender` | JDK `HttpURLConnection`. | Dự án đơn giản, giữ default, ít yêu cầu kết nối nâng cao. | Timeout, auth và TLS controls theo version; không đồng nghĩa JDK `HttpClient`. |
| **`JdkHttpClientMessageSender`** | `java.net.http.HttpClient`. | Muốn dùng HTTP client chuẩn JDK hiện đại, cấu hình builder và reuse connection. | Class/API phải có trong Spring-WS version; hành vi proxy, redirects, timeout cần test. |
| `HttpComponents5MessageSender` | Apache HttpClient 5. | Cần quản lý pool, HTTP authentication, policy hoặc instrumentation nâng cao. | Cần dependency Apache phù hợp; API khác JDK. |
| `SimpleHttpComponents5MessageSender` | Apache HttpClient 5 đã cung cấp từ ngoài. | Muốn tái sử dụng Apache client được tùy chỉnh sẵn ở phiên bản hỗ trợ. | Kiểm tra constructor/setter và lifecycle owner. |
| `HttpComponentsMessageSender` (các nhánh cũ) | Apache HttpClient thế hệ cũ. | Duy trì hệ thống legacy khi version còn hỗ trợ. | Không copy sang HttpComponents5 một cách máy móc. |
| `ClientHttpRequestMessageSender` | Spring `ClientHttpRequestFactory`. | Tận dụng HTTP request factory được framework hỗ trợ. | Đây là một adapter khác; không giả định nó sử dụng JDK HttpClient mặc định. |

**Lựa chọn không chỉ theo performance.** Nếu service cần auth/proxy phức tạp, pooling controls đặc thù, wire-level instrumentation, streaming lớn hoặc quản trị TLS chi tiết, so sánh JDK sender với Apache sender trong **load test và môi trường hạ tầng thật**.

### 8.1. Tại sao không đổi sang sender mới chỉ vì “có HTTP/2”?

SOAP server hoặc corporate proxy có thể được tối ưu cho HTTP/1.1, đóng connection theo quy tắc cũ hoặc có behavior với chunked request/response. JDK HttpClient có HTTP/2 nhưng **việc công bố hỗ trợ HTTP/2 ở tầng JDK không chứng minh các hop đến SOAP server đã tương thích**.

Khi chọn, đo:

- Số kết nối/TLS handshakes, latency p50/p95/p99.
- Throughput và giới hạn concurrent calls.
- HTTP status distribution, SOAP Fault rate, timeout rate.
- Behavior qua proxy, network loss, expired certificates, redirects.
- Peak heap/GC với payload JAXB, SOAP Envelope và MTOM attachments.
- Tỷ lệ retry, duplicate side effects và time-to-recovery.

Nếu sender cũ đáp ứng SLA và hệ thống có yêu cầu compatibility cao, không có áp lực phải chuyển ngay.

### 8.2. Không tự quản lý connection như một HTTP request thô

`WebServiceMessageSender` tạo `WebServiceConnection` cho Spring-WS. `WebServiceTemplate` chịu trách nhiệm workflow gửi message, đọc response và quản lý connection theo contract của Spring-WS. Hãy tránh:

~~~java
// Không khuyến khích: tự tạo connection rồi bỏ qua quy trình
// đóng, xử lý Fault và serialize XML của WebServiceTemplate.
sender.createConnection(URI.create(endpointUrl));
~~~

Dòng trên chỉ minh họa hành vi **không nên làm khi không có lý do chuyên biệt**. Với SOAP client bình thường, dùng `marshalSendAndReceive` hoặc `sendSourceAndReceiveToResult` để giữ đầy đủ xử lý SOAP.

## 9. Gắn lỗi HTTP với SOAP Fault trong JDK sender

Một HTTP transport có thể trả status thành công/lỗi; sau khi nhận dữ liệu, Spring-WS phân tích SOAP message và xử lý Fault theo SOAP version. **JDK `HttpClient` không tự hiểu `soap:Fault` hay WSDL fault detail**.

### 9.1. Các trường hợp cơ bản

| Hiện tượng | HTTP status/body | Loại lỗi client nên phân biệt |
| --- | --- | --- |
| Request-response thành công | Thường `200` và `CreateOrderResponse` đúng XSD. | SOAP success hoặc business status. |
| SOAP 1.1 Client/Server Fault | Thường `500` + `soap:Fault`. | `SoapFaultClientException`/fault resolver theo stack. |
| SOAP 1.2 Sender/Receiver Fault | Có thể `400/500` theo binding + `env:Fault`. | Fault code/subcode/reason/detail. |
| URL SOAP sai | `404` HTML hoặc rỗng. | HTTP transport error, không phải SOAP Fault. |
| Media type sai | `415`, không nhất thiết SOAP XML. | HTTP/binding mismatch. |
| Gateway lỗi | `502/503/504` với HTML/empty body. | HTTP transport/gateway error. |
| TLS handshake fail | Không có HTTP response. | SSL/connectivity exception. |
| Timeout sau khi gửi POST | Có thể không có response. | Outcome chưa biết, retry có điều kiện. |
| SOAP response có root QName sai | `200` và Envelope nhưng payload lệch XSD. | Contract/unmarshalling error. |
| Business reject theo WSDL | `200` và `status=REJECTED`. | Business result, không tự coi HTTP failure. |

**Không dùng `if (httpStatus == 200) success; else retry();`**. Cách đó sai khi SOAP Fault đi cùng HTTP lỗi và không an toàn với side effects.

### 9.2. Ví dụ xử lý exception phía client

~~~java
import org.springframework.ws.client.WebServiceClientException;
import org.springframework.ws.client.WebServiceIOException;
import org.springframework.ws.client.WebServiceTransportException;
import org.springframework.ws.soap.client.SoapFaultClientException;

try {
    Object response = ordersTemplate.marshalSendAndReceive(
        createOrderRequest,
        soapActionCallback);

    // Sau đó kiểm tra JAXB response và business status
    // theo đúng XSD/WSDL.
} catch (SoapFaultClientException fault) {
    // SOAP Fault: code, reason, detail theo SOAP version.
    classifySoapFault(fault);
} catch (WebServiceTransportException transport) {
    // HTTP/transport error: không mặc định là SOAP Fault.
    classifyTransport(transport);
} catch (WebServiceIOException network) {
    // I/O, timeout, TLS/connectivity tùy root cause.
    classifyNetwork(network);
} catch (WebServiceClientException other) {
    // Lỗi khác của SOAP client framework.
    classifyClientError(other);
}
~~~

Các hàm `classify*`, biến `ordersTemplate`, `createOrderRequest` và `soapActionCallback` là **phần ứng dụng tự viết**; code này mô tả vị trí bắt lỗi, không phải chương trình độc lập. Các exception có thể được lồng/bọc khác nhau theo Spring-WS/JDK version; hãy test **thực tế** với HTTP `502`, TLS handshake, timeout và SOAP Fault.

### 9.3. Retry cần idempotency, không chỉ backoff

~~~text
Client gửi CreateOrder
    → Gateway nhận POST
    → Orders server tạo orderId và commit
    → Response mất vì timeout
    → Client chưa biết kết quả
~~~

Nếu client tự retry với một transaction ID mới, có thể tạo đơn trùng. **Correlation ID** giúp nối log, **idempotency key** giúp quản trị tác vụ lặp khi server thực thi đúng chính sách. Với HTTP `429/503` có thể backoff giới hạn, còn HTTP `404/415` thường cần sửa cấu hình; SOAP `Sender/Client` thường phải sửa request thay vì gửi lại y nguyên.

## 10. SOAP security và attachment khi thay sender

### 10.1. WS-Security ở tầng SOAP, không phải HTTP sender

Trong Spring-WS, một `ClientInterceptor` kiểu WSS4J có thể bổ sung UsernameToken, timestamp, XML Signature hoặc encryption trước khi truyền SOAP message. JDK sender chỉ chuyển SOAP bytes qua HTTP.

Nếu đổi sender, phải kiểm tra:

- Header `wsse:Security` có được tạo đúng policy và namespace không.
- Server chấp nhận chữ ký/canonicalization và chứng chỉ không.
- Response security/Fault được xác minh và map đúng.
- Proxy/redirect không làm mất SOAPAction hoặc thay đích không được phép.
- Log HTTP/SOAP có che token, key material và PII không.

### 10.2. MTOM/MIME attachments

Một số SOAP operation dùng `xop:Include` và MIME parts để chuyển dữ liệu nhị phân lớn. Đổi sender có thể ảnh hưởng hành vi **chunking, Content-Type/boundary, buffering và response streaming** ở transport.

Không suy “HTTP client hỗ trợ streaming” nghĩa Spring-WS `WebServiceTemplate`, SAAJ/Axiom, JAXB, WS-Security và proxy đều không buffer. Cần kiểm tra end-to-end từ SOAP message factory, attachment API, transport sender tới server và gateway.

### 10.3. XML security vẫn cần validation riêng

Input SOAP từ upstream là dữ liệu không tin cậy. Nếu server/client có XML parser cho phép external entities/DTD không đúng chính sách, việc dùng JDK `HttpClient` **không giải quyết** XXE, entity expansion hoặc schema import. Bảo vệ parser, transformer, XSD resolver và giới hạn message size ở các tầng phù hợp.

## 11. Kiểm thử JdkHttpClientMessageSender đúng tầng

Nếu chỉ tạo được Spring bean mà không gửi được SOAP request thật, chưa thể nói sender tương thích production. Cần **tách hai tầng test**: test logic SOAP/JAXB và test HTTP transport thật.

### 11.1. Test SOAP contract bằng MockWebServiceServer

Spring-WS Test có `MockWebServiceServer` giúp mô phỏng SOAP response và Fault cho một `WebServiceTemplate` trong ApplicationContext.

~~~java
import java.util.Locale;

import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.ws.soap.client.SoapFaultClientException;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.ws.test.client.RequestMatchers.anything;
import static org.springframework.ws.test.client.ResponseCreators
    .withServerOrReceiverFault;

// ordersTemplate có JAXB marshaller/unmarshaller và SOAP config.
MockWebServiceServer server =
        MockWebServiceServer.createServer(ordersTemplate);

server.expect(anything())
      .andRespond(withServerOrReceiverFault(
          "Temporary service error", Locale.ENGLISH));

assertThrows(SoapFaultClientException.class,
    () -> ordersTemplate.marshalSendAndReceive(createOrderRequest));

server.verify();
~~~

Ví dụ cần Spring-WS Test, JUnit và JAXB DTO phù hợp; `ordersTemplate` và `createOrderRequest` là biến được cung cấp từ fixture. Với custom `FaultMessageResolver`, exception được ném có thể khác mặc định. `anything()` chỉ xác nhận có request, nên bổ sung matcher kiểm tra QName, SOAPAction/headers và schema khi viết test thật.

**Rất quan trọng:** `MockWebServiceServer.createServer(ordersTemplate)` thường **thay đường sender thật bằng mock sender** để trả response giả. Nó giúp kiểm thử **SOAP client orchestration, marshalling và Fault handling**, **không chứng minh `JdkHttpClientMessageSender` đã mở TCP/TLS, dùng đúng proxy hay áp dụng timeout**.

Nếu test mock pass nhưng integration gọi endpoint thật fail, cần xem transport, không chỉ sửa JAXB model.

### 11.2. Test HTTP integration với server/proxy cục bộ

Để kiểm chứng JDK sender, tạo một **server HTTP test thật** (embedded servlet, loopback HTTP stub hoặc test service có kiểm soát) nhận SOAP POST. Không cần gọi ra Internet. Những assertion có giá trị:

1. `WebServiceTemplate` đang thật sự dùng **`JdkHttpClientMessageSender`**, không phải sender default hoặc mock.
2. Server nhận **HTTP POST** đến đúng `soap:address` path và Host.
3. `Content-Type` khớp binding SOAP 1.1/1.2; SOAPAction được tạo đúng WSDL.
4. Request SOAP Envelope well-formed, QName Body đúng XSD; JAXB marshalling không đổi contract.
5. Response `200` chứa normal SOAP XML được unmarshal đúng; `500` chứa SOAP Fault được fault resolver phân loại.
6. HTTP `404/415/502` chứa HTML/rỗng không bị hiểu nhầm là SOAP Fault.
7. Timeout, reset connection và TLS certificate invalid dẫn tới error category đúng.
8. Proxy/TLS/redirect rules được tôn trọng khi hạ tầng test có mô phỏng chúng.
9. Sau nhiều lời gọi, connection reuse/latency/concurrency phù hợp mục tiêu (không suy từ một request).
10. Khi yêu cầu có side effect, retry không tạo dữ liệu trùng do thiếu idempotency.

Có thể dùng một endpoint loopback `http://127.0.0.1:<port>/ws` **chỉ trong test**; production phải dùng HTTPS và certificate policy thật. Đừng hardcode port tùy ý vào bộ test song song, nên dùng cổng động và lấy địa chỉ từ test server.

### 11.3. Baseline bằng curl không thay thế test JDK sender

Trong môi trường test có endpoint SOAP 1.1 ở `http://localhost:8080/ws`, lưu request đầy đủ ở `request.xml` mã hóa UTF-8:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Gửi từ PowerShell:

~~~powershell
curl.exe --include --request POST --header 'Content-Type: text/xml; charset=utf-8' --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' --data-binary '@request.xml' 'http://localhost:8080/ws'
~~~

Đây là **lệnh kiểm tra HTTP/SOAP bằng curl**, không chạy Spring-WS sender. URL, SOAPAction và XML payload chỉ là ví dụ; phải lấy schema và action thực từ WSDL/XSD của service. Nếu server trả SOAP Fault, kiểm tra cả HTTP status, SOAP Envelope, faultcode/reason/detail; nếu trả HTTP HTML `502`, kiểm tra gateway.

Lệnh curl có thể thành công trong khi JDK client vẫn fail do truststore, proxy, timeout, HTTP version hoặc source code đang dùng nhầm sender. Cần test chính **`WebServiceTemplate` cấu hình JDK sender** trước khi công bố đã hỗ trợ.

### 11.4. Test mTLS/SSL và proxy

| Case | Cách tạo tình huống trong test | Điều cần khẳng định |
| --- | --- | --- |
| TLS certificate hợp lệ | Server test có chứng chỉ ký bởi CA tin cậy của client. | Handshake thành công, hostname verification đúng. |
| TLS certificate không tin | Truststore không có CA tương ứng. | Gọi bị từ chối, không disable validation để làm pass. |
| Hostname sai | Certificate không khớp tên host test. | Bị từ chối đúng policy. |
| mTLS thiếu chứng chỉ client | Server yêu cầu client certificate. | Handshake thất bại hoặc bị từ chối rõ ràng. |
| Proxy hợp lệ | Đường đi qua proxy test được phép. | Proxy nhận request đúng, target được kiểm soát. |
| Proxy yêu cầu auth | Proxy trả HTTP `407` cho credentials thiếu. | Phân loại proxy/auth error, không phải SOAP Fault nghiệp vụ. |
| HTTP redirect bất ngờ | Server trả `301/302/307/308`. | Không tự gửi lại SOAP POST tới đích ngoài allowlist. |
| Connect timeout | Đích kiểm soát không mở kết nối/không đáp ứng. | Exception được phân loại, có tổng deadline hợp lý. |
| Request timeout | Server nhận POST nhưng cố ý phản hồi chậm. | Không tự suy server chưa tạo side effect. |
| SOAP Fault | Server trả Fault đúng SOAP version. | Fault resolver xử lý khác HTTP HTML/empty body. |

Khi test thông tin xác thực, chỉ sử dụng **credential và chứng chỉ giả/lab**, không đưa key thật vào repository, log, test snapshot hoặc chat.

### 11.5. Test tải và bộ nhớ

Chạy nhiều SOAP calls đồng thời bằng **một** JDK `HttpClient` được reuse, với payload nhỏ/vừa/lớn theo contract và XSD validation/security được giữ nguyên.

Theo dõi:

- Throughput và latency p50/p95/p99 của toàn lời gọi.
- Connection setup/TLS handshake count, reuse rate và lỗi socket.
- Tỷ lệ HTTP status, SOAP Fault, TLS failure, timeout.
- Peak heap/GC, allocation rate và attachment temp disk.
- Backpressure/concurrency limit ở client, proxy, server.
- Retry count, idempotency conflicts và side effect trùng.
- Số lượng thread do HTTP client/executor và business request sử dụng.

Một benchmark tốt phải giữ **đúng cùng workload, JDK, network, TLS, XSD/JAXB, message factory và WS-Security** khi so sánh JDK sender với sender khác. Nếu đổi đồng thời transport và validation, kết quả không thể quy toàn bộ khác biệt hiệu năng cho sender.

## 12. Khắc phục sự cố thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Không import được `JdkHttpClientMessageSender` | `spring-ws-core` quá cũ hoặc class không có trong patch version. | Dependency tree, class list/JAR, Javadoc version chính xác. |
| `NoClassDefFoundError`/`NoSuchMethodError` lúc chạy | Compile/runtime version khác hoặc dependency conflict. | Kiểm tra JAR deployed, BOM overrides và toàn classpath. |
| Setter `setRequestTimeout` không tìm thấy | Nhầm sender hoặc dùng version khác API. | Xác minh package và Javadoc của đúng artifact. |
| Bean được tạo nhưng vẫn dùng HTTP URLConnection | `WebServiceTemplate` chưa gắn `setMessageSender` hoặc đã bị auto-config override. | Kiểm tra template bean thật và sender selection. |
| `SSLHandshakeException` | Truststore/client cert/hostname/TLS mismatch. | Certificate chain, SNI, hostname, trust/keystore, mTLS. |
| HTTP `407 Proxy Authentication Required` | Proxy cần auth. | ProxySelector, proxy credentials và policy. |
| HTTP `301/302` sau POST | Địa chỉ SOAP sai, gateway redirect, HTTP→HTTPS. | So WSDL `soap:address`, sửa URI; không follow mù quáng. |
| HTTP `404` | Gửi SOAP POST tới URL WSDL GET hoặc sai servlet/context path. | So URL `orders.wsdl` với `soap:address`. |
| HTTP `415` | SOAP 1.1/1.2 media type/action mismatch. | Xem message factory, binding, Content-Type và SOAPAction. |
| SOAP Fault dù HTTP connection thành công | Server xử lý SOAP và trả Fault. | Fault code/reason/detail, XSD, WS-Security. |
| HTTP `500` là HTML | Gateway/server lỗi không phát SOAP Fault hợp lệ. | Content-Type, body, proxy logs; không ép SOAP exception. |
| Timeout sau khi POST | Upstream chậm, proxy, network hoặc server đã commit. | Correlation ID, query trạng thái, idempotency, timeout budget. |
| SOAP Header bị thiếu | Callback hoặc WS-Security interceptor chưa cấu hình/không chạy. | Capture outgoing Envelope trong test, kiểm tra order callback/interceptor. |
| MTOM bị lỗi | MIME multipart, message factory, chunking/proxy không tương thích. | Test attachment thực, Content-Type/boundary, limits và streaming. |
| Latency tăng sau khi đổi sender | HTTP version, redirects, pool reuse, proxy, TLS handshake, logging. | Benchmark từng thành phần; không đoán. |
| JDK sender pass mock, fail production | Mock test không chạy network sender. | Real HTTP integration test với proxy/TLS/headers. |

**Quy trình debug theo thứ tự:** kiểm tra version/JAR → cấu hình `WebServiceTemplate` đang dùng sender nào → SOAP address và Content-Type → proxy/TLS/DNS → HTTP status và headers → SOAP Envelope/Fault → JAXB unmarshalling/business status. Phân loại lỗi ở tầng đầu tiên có bằng chứng thay vì sửa nhiều cờ timeout cùng lúc.

## 13. Quy trình quyết định chọn JDK sender

~~~mermaid
flowchart TD
    A["Muốn dùng JdkHttpClientMessageSender?"] --> B{"Class và API có trong runtime spring-ws-core?"}
    B -- "Không / chưa xác minh" --> C["Giữ sender đang hỗ trợ hoặc nâng cấp stack"]
    B -- "Có" --> D{"JDK, Boot/BOM/Jakarta tương thích?"}
    D -- "Không" --> C
    D -- "Có" --> E["Chọn default HttpClient hoặc custom HttpClient"]
    E --> F["Gắn sender thật vào WebServiceTemplate"]
    F --> G["Test SOAP contract, TLS/proxy, HTTP status, Fault"]
    G --> H{"Đạt tính đúng, security và hiệu năng?"}
    H -- "Không" --> I["Chỉnh cấu hình hoặc chọn sender khác"]
    H -- "Có" --> J["Deploy có giám sát, retry/idempotency policy"]
~~~

### 13.1. Các bước áp dụng trong một dự án

**Bước 1 — Khóa version.** Xác nhận `spring-ws-core`, Spring Boot/BOM, JDK và các dependency JAXB, HTTP sender. Đặc biệt đừng suy JDK sender tồn tại ở mọi `4.0.x` chỉ vì `Since: 4.0`.

**Bước 2 — Xác nhận API.** Kiểm tra class có trong runtime JAR; đối chiếu constructors và setters kiểu `Duration` với Javadoc chính xác.

**Bước 3 — Lựa chọn transport.** Nếu không cần advanced pool/auth controls, JDK sender có thể phù hợp. Nếu proxy/auth/concurrency policy phức tạp, xem xét `HttpComponents5MessageSender` ở version hỗ trợ.

**Bước 4 — Tạo bean và gắn template.** `JdkHttpClientMessageSender` phải là sender được `WebServiceTemplate` sử dụng; giữ `Jaxb2Marshaller`, SOAP message factory và security interceptors đúng contract.

**Bước 5 — Kiểm tra mạng và trust.** HTTP/1.1/HTTP/2, redirects, proxy, hostname/certificate, mTLS, timeouts và endpoint allowlist.

**Bước 6 — Kiểm tra SOAP semantics.** WSDL SOAP address, SOAPAction, Envelope 1.1/1.2, WS-Security headers, response JAXB, SOAP Fault và XSD validation.

**Bước 7 — Kiểm thử integration thật.** Mock tests giúp logic SOAP, nhưng cần real HTTP/TLS/proxy tests để chứng minh sender hoạt động.

**Bước 8 — Triển khai có quan sát.** Ghi correlation/request/trace IDs đã lọc, HTTP error classes, SOAP Fault category, latency/timeout, backoff và idempotency; không log raw credentials/Body nhạy cảm.

## 14. Bài thực hành có đáp án gợi ý

### Bài A — Trên 4.0.4, import bị lỗi

Dự án dùng `spring-ws-core:4.0.4` và IDE báo không có `JdkHttpClientMessageSender`, nhưng tài liệu `4.1.4` có class ghi `Since: 4.0`.

**Đáp án:** đừng tự thêm import và copy class từ bản mới. Kiểm tra JAR và đúng Javadoc; danh sách 4.0.4 không liệt kê class. Giữ sender được hỗ trợ hoặc lên kế hoạch nâng cấp patch/stack tương thích, rồi test.

### Bài B — Có bean sender nhưng template vẫn dùng default

Dự án định nghĩa:

~~~java
@Bean
JdkHttpClientMessageSender sender() {
    return new JdkHttpClientMessageSender();
}
~~~

nhưng tạo template bằng `new WebServiceTemplate()` và không gọi `setMessageSender(sender)`.

**Đáp án:** chỉ có bean không bảo đảm template đã chọn nó. Inject sender vào bean template và gọi `setMessageSender(...)`, sau đó test HTTP integration để xác nhận hành vi.

### Bài C — SOAP Fault bị xem là HTTP 500 bất kỳ

Client bắt tất cả HTTP `500` rồi retry, không đọc SOAP Body. Một số lỗi là `soap:Client` Fault do request sai pattern.

**Đáp án:** xử lý SOAP Fault theo code/detail/schema, phân biệt HTTP HTML error và network error; không retry lỗi input y nguyên. Chỉ retry có điều kiện và bảo vệ idempotency.

### Bài D — Kết nối TLS fail trong khi curl vẫn thành công

JDK client ném `SSLHandshakeException`, nhưng `curl` trên máy phát triển gọi được endpoint.

**Đáp án:** hai client có thể dùng truststore, proxy, certificate store và hostname verification khác nhau. Kiểm tra chính JDK runtime/truststore/keystore và cấu hình client, không tắt xác minh chứng chỉ để cho test pass.

### Bài E — Chuyển sang JDK sender làm tăng latency

Client gọi SOAP nhiều lần, tạo `HttpClient.newHttpClient()` và sender mới cho **mỗi** request. Server/proxy có thể đóng idle connections.

**Đáp án:** chuyển sang bean HTTP client/sender dùng lại, đo số kết nối/TLS handshakes và p95/p99; kiểm tra thêm HTTP version/proxy. Không thể quy mọi khác biệt chỉ cho sender nếu workload và caching khác nhau.

### Bài F — Timeout khi thanh toán

Client timeout sau khi gửi `ReservePayment`. Nó định retry với idempotency key mới.

**Đáp án:** có nguy cơ ghi giao dịch hai lần. Giữ idempotency key cho cùng ý định, tra cứu trạng thái hoặc theo workflow bù trừ. Request/attempt ID có thể mới để theo dõi từng lần; correlation ID có thể giữ xuyên workflow.

## 15. Checklist cuối bài

| Câu hỏi kiểm tra | Điều kiện đạt |
| --- | --- |
| Đúng class, đúng version? | JAR `spring-ws-core` thực tế có `JdkHttpClientMessageSender` và API cần dùng. |
| Đúng JDK/runtime? | `java.net.http.HttpClient` khả dụng, modules/classpath phù hợp. |
| Không nhầm sender? | Phân biệt `HttpURLConnection`, JDK `HttpClient` và Apache HttpClient 5. |
| Gắn vào template? | `WebServiceTemplate#setMessageSender` dùng đúng bean JDK sender. |
| JAXB/contract đúng? | DTO, QName, XSD/WSDL, `soap:address` và SOAPAction khớp. |
| Timeout phù hợp? | Connect timeout và request timeout có nghĩa rõ, tổng SLA/retry được quản lý. |
| HTTP version/redirect phù hợp? | HTTP/1.1/2 và redirect policy đã test với SOAP gateway. |
| TLS/mTLS đúng trust? | Certificate chain, hostname, client key và truststore được xác minh. |
| Proxy/auth hợp lệ? | ProxySelector, HTTP authentication và quyền mạng đúng policy. |
| WS-Security không bị thay đổi? | SOAP Header/chữ ký/UsernameToken do đúng security stack xử lý. |
| SOAP Fault được phân loại? | HTTP status, SOAP Fault, network/TLS và business response tách biệt. |
| Retry an toàn? | Backoff, giới hạn attempts, idempotency hoặc trạng thái chưa rõ được xử lý. |
| Attachment/MTOM tương thích? | Không phá MIME, Content-Type, size limits và memory strategy. |
| Không SSRF/redirect ra ngoài? | Destination allowlist/egress control được kiểm tra. |
| Test sender thật? | Có integration HTTP/TLS/proxy test, không chỉ `MockWebServiceServer`. |
| Đã đo hiệu năng? | Latency, throughput, connections, GC, timeout và lỗi được theo dõi. |
| Có cách rollback? | Giữ lựa chọn sender trước đó và test hồi quy đủ điều kiện. |

### Ghi nhớ

- **`JdkHttpClientMessageSender` là adapter HTTP transport của Spring-WS sử dụng JDK `java.net.http.HttpClient`**; nó không phải SOAP marshaller, XML parser, WS-Security interceptor hay WSDL generator.
- **Hỗ trợ theo phiên bản phải được kiểm tra thật**: Javadoc 4.0.4 không liệt kê class, trong khi 4.0.6 và 4.1.4 có; nhãn `Since: 4.0` không chứng minh toàn bộ patch version hỗ trợ.
- **`WebServiceTemplate` phải sử dụng sender được gắn rõ ràng**; khai báo bean sender đơn lẻ không tự đảm bảo mọi client chuyển sang dùng nó.
- **Timeout, proxy, TLS/mTLS, HTTP version và redirects thuộc tầng transport**; SOAPAction, JAXB/XML, SOAP Fault, XSD và WS-Security thuộc các tầng khác.
- **JDK HttpClient không tự biến WebServiceTemplate thành async API** và không tự bảo đảm full streaming/zero-copy cho SOAP/MTOM.
- **Mock SOAP tests không chứng minh HTTP sender đã hoạt động**; cần test network/TLS/proxy thật, đồng thời bảo vệ idempotency khi timeout hoặc retry.
- **Chọn sender cuối cùng bằng tính đúng, tương thích và số liệu vận hành**, không bằng nhãn công nghệ mới hơn.




