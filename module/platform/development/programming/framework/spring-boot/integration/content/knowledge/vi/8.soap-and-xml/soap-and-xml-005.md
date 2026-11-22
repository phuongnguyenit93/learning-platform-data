# Message sender, kết nối HTTP, xác thực và thời gian chờ

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức kết nối hệ thống qua HTTP client, cơ sở dữ liệu, cache, message broker và các adapter của Spring Integration. Ngoài REST/JSON, nhiều ERP, hệ thống ngân hàng, bảo hiểm và nền tảng quản trị doanh nghiệp cung cấp **SOAP Web Services** trên HTTP(S). Để gọi một dịch vụ SOAP đáng tin cậy, việc JAXB marshalling đúng XML chỉ là một phần: ứng dụng còn phải quản lý **message sender**, kết nối TCP/TLS, xác thực, thời gian chờ, SOAP Fault, retry và khả năng quan sát.

Ví dụ Order Service phải gửi yêu cầu `SubmitOrder` sang ERP:

- Đầu vào: một business command đã được xác thực, có khóa nghiệp vụ duy nhất.
- Payload: XML đúng WSDL/XSD của đối tác.
- Transport: HTTPS, có thể qua proxy, kèm HTTP Basic/Bearer hoặc mTLS.
- SOAP layer: SOAP 1.1/1.2, SOAPAction hoặc WS-Security nếu đối tác yêu cầu.
- Đầu ra: SOAP response, SOAP Fault, HTTP error hoặc timeout.
- Vận hành: timeout hữu hạn, connection pool, retry/idempotency, metrics và audit.

Bài thuộc chương **SOAP và XML**, tập trung trực tiếp vào **message sender, kết nối HTTP, xác thực và thời gian chờ** của Spring Web Services trong Spring Boot. Sau bài này, bạn có thể:

1. Hiểu `WebServiceTemplate`, `WebServiceMessageSender`, message factory, marshaller và fault resolver khác nhau thế nào.
2. Cấu hình HTTP sender mặc định và sender sử dụng connection pooling theo phiên bản Spring-WS.
3. Thiết lập connect/read/connection-pool timeouts, budget tổng và chính sách concurrency.
4. Phân biệt HTTP Basic/Bearer, mTLS, SOAP UsernameToken/Signature và application authorization.
5. Sử dụng đúng SOAPAction, SOAP Envelope version, Content-Type và endpoint URI.
6. Phân loại lỗi kết nối, TLS, HTTP và SOAP Fault; tránh retry làm lặp tác động nghiệp vụ.
7. Viết kiểm thử không kết nối ERP thật và kiểm thử riêng transport/TLS/auth/timeouts.
8. Tạo observability theo ranh giới HTTP/SOAP và kiểm soát secrets, payload nhạy cảm.

> **Nguyên tắc:** `WebServiceTemplate.marshalSendAndReceive(...)` trả về mà không ném lỗi chỉ cho biết request/response hoàn tất theo xử lý ở client; **không** tự bảo đảm giao dịch từ xa đã commit hoặc không thể phát sinh kết quả trùng khi retry.

## 1. Tách rõ SOAP payload và HTTP transport

Một lời gọi SOAP đi qua các lớp:

~~~mermaid
flowchart LR
    A["Order command"] --> B["SOAP gateway"]
    B --> C["JAXB Marshaller"]
    C --> D["SOAP message factory"]
    D --> E["WebServiceTemplate"]
    E --> F["WebServiceMessageSender"]
    F --> G["HTTP connection + TLS"]
    G --> H["ERP SOAP endpoint"]
    H --> I["SOAP response / Fault"]
    I --> J["Unmarshaller + outcome mapping"]
    J --> K["Business result"]
    B -.-> L["Outbox / retry / observability"]
~~~

| Lớp | API tiêu biểu | Quyết định gì? |
| --- | --- | --- |
| XML mapping | `Jaxb2Marshaller` | DTO ↔ XML root, QName, namespace |
| SOAP message | `SoapMessage`, `SaajSoapMessageFactory` | SOAP Envelope, Body, Header, version |
| SOAP client orchestration | `WebServiceTemplate` | Gửi request, nhận response, fault handling |
| HTTP transport | `WebServiceMessageSender` | Kết nối, HTTP headers, TLS, timeouts, proxy, pool |
| Application adapter | `ErpSoapGateway` | Business key, validate, map errors, retry policy |
| Data/messaging | SQL outbox, broker consumer | Durable intent, acknowledgement, idempotency |

`RestClient` hoặc `WebClient` có thể gửi XML qua HTTP, nhưng **không mặc nhiên cung cấp SOAP marshalling, SOAP message factory, SOAP Fault resolver và WS-Security**. Nếu đối tác sử dụng WSDL/SOAP, `WebServiceTemplate` là lựa chọn phù hợp; HTTP transport vẫn có thể sử dụng các client libraries tương tự.

### 1.1. WebServiceMessageSender là gì?

`WebServiceMessageSender` là abstraction của Spring-WS để gửi/nhận `WebServiceMessage` qua một đích được xác định bằng URI. Với SOAP over HTTP, sender tạo connection tương ứng, ghi request (HTTP headers + SOAP Envelope), đọc response và để tầng trên giải quyết SOAP Fault.

Một sender không quyết định dữ liệu nào là đơn hàng hợp lệ, không chọn transaction SQL và không tự có retry/idempotency theo nghiệp vụ.

### 1.2. Một request SOAP trên wire

~~~http
POST /soap/orders HTTP/1.1
Host: erp.example.org
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:SubmitOrder"
Authorization: Basic <redacted>

<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:o="urn:example:orders:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <o:SubmitOrderRequest>
      <o:orderId>ORD-100</o:orderId>
    </o:SubmitOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là **ví dụ mô tả cấu trúc, không phải request để sao chép trực tiếp**, và `Authorization` đã được che. Tên `SOAPAction`, namespace và operation phải lấy từ WSDL. Với SOAP 1.2, HTTP `Content-Type` thường là `application/soap+xml` và action có thể nằm trong Content-Type parameter; không áp quy tắc SOAP 1.1 nguyên xi.

## 2. Dependency và tính tương thích Spring Boot/Spring-WS

### 2.1. Dependencies cơ bản

Ví dụ Gradle Groovy DSL cho Spring Boot 3.x và Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web-services'

    // Cần khi tự dùng JAXB/Jaxb2Marshaller:
    implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
    runtimeOnly 'org.glassfish.jaxb:jaxb-runtime'

    // Tùy nhu cầu đo metrics:
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.ws:spring-ws-test'
}
~~~

Starter Web Services mang hạ tầng Spring-WS; phụ thuộc JAXB có thể đã được kéo transitively trong một project cụ thể. Kiểm tra dependency tree và để **Spring Boot BOM** quản lý version tương thích khi có thể.

Các lớp chính:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.WebServiceMessageSender;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.soap.client.core.SoapActionCallback;
~~~

### 2.2. Version matters

| Dòng nền tảng | Điểm cần chú ý |
| --- | --- |
| Spring Boot 2 / Spring-WS 3 legacy | JAXB thường dùng `javax.xml.bind`; Apache HttpClient 4 sender có thể xuất hiện trong code cũ |
| Spring Boot 3 / Spring-WS 4 | Java 17+, namespace `jakarta.xml.bind`; có sender dựa trên Apache HttpClient 5 trong các bản hỗ trợ |
| Spring Boot 4 / Spring-WS thế hệ mới | Một số package auto-config, constructor và transport APIs có thể thay đổi; kiểm tra Javadoc của version thực |
| HTTP JDK URLConnection | Không cần external Apache client, phù hợp kịch bản đơn giản; giới hạn kiểm soát pool/transport |
| Apache HttpClient sender | Hỗ trợ pooling, proxy, credentials và timeout chi tiết; cần đúng major HttpClient/Spring-WS |

Tên `HttpComponentsMessageSender` trong bài viết cũ **không đồng nghĩa** `HttpComponents5MessageSender` sử dụng Apache HttpClient 5. Không trộn Apache `org.apache.http.*` (4.x) với `org.apache.hc.client5.*` (5.x). Trong các ví dụ có API phụ thuộc phiên bản, ưu tiên verify chữ ký method sau khi build dependency của project đã được quyết định.

**Không chọn sender chỉ bằng tên thư viện:** cần xác định hệ thống có proxy, mTLS, connection pooling, maximum concurrent requests, streaming, compression và auth scheme nào.

## 3. Cấu hình WebServiceTemplate từ Spring Boot

Một client SOAP thường có:

- Endpoint URI.
- Message factory chọn SOAP 1.1/1.2.
- Marshaller/unmarshaller từ JAXB generated classes.
- HTTP sender với TLS/auth/timeouts.
- Fault resolver/interceptors nếu cần.
- Adapter ánh xạ dữ liệu nghiệp vụ.

### 3.1. Externalized configuration

~~~yaml
integrations:
  erp:
    uri: ${ERP_SOAP_URL:https://erp.example.org/soap/orders}
    connect-timeout: 3s
    read-timeout: 12s
    max-attempts: 3
~~~

`ERP_SOAP_URL` ở đây là endpoint minh họa. Production phải lấy URL từ config theo môi trường, tuyệt đối không đưa credentials vào URL như `https://user:pass@host` hoặc log nguyên URL chứa query token.

Bind cấu hình vào record (ví dụ trên Boot 3/Java 17+):

~~~java
// ErpSoapProperties.java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integrations.erp")
public record ErpSoapProperties(
        URI uri,
        Duration connectTimeout,
        Duration readTimeout,
        int maxAttempts) {
}
~~~

Đăng ký properties bằng `@EnableConfigurationProperties(ErpSoapProperties.class)` hoặc `@ConfigurationPropertiesScan`. Trong production, validate URI scheme là HTTPS, timeout dương/có upper bound và hostname nằm trong danh sách endpoint được phép.

### 3.2. JAXB marshaller cho payload

Giả sử `com.example.erp.generated` là package XJC-generated từ WSDL/XSD và chứa `ObjectFactory`:

~~~java
// ErpSoapConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration(proxyBeanMethods = false)
public class ErpSoapConfiguration {

    @Bean
    Jaxb2Marshaller erpMarshaller() {
        Jaxb2Marshaller mapper = new Jaxb2Marshaller();
        mapper.setContextPath("com.example.erp.generated");
        mapper.setSupportDtd(false);
        mapper.setProcessExternalEntities(false);
        return mapper;
    }
}
~~~

Đây là ví dụ cho JAXB Jakarta phù hợp Boot hiện đại. Nếu generated DTO không có `ObjectFactory`/`jaxb.index`, dùng `setClassesToBeBound(...)` cho các lớp JAXB đã xác định. Chặn DTD và external entities là cần thiết, nhưng còn phải kiểm soát parser đầu vào và XSD imports nếu có.

## 4. Sender đơn giản: HttpUrlConnectionMessageSender

`HttpUrlConnectionMessageSender` sử dụng cơ chế HTTP URL connection của JDK. Đây là lựa chọn dễ hiểu cho kịch bản gọi SOAP với mức đồng thời vừa phải, không đòi hỏi pooling/proxy/authentication phức tạp.

Với Spring-WS **có setters nhận `Duration`**, cấu hình minh họa:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.ws.transport.WebServiceMessageSender;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

@Bean
WebServiceMessageSender erpMessageSender(
        ErpSoapProperties props) {

    HttpUrlConnectionMessageSender sender =
            new HttpUrlConnectionMessageSender();

    sender.setConnectionTimeout(props.connectTimeout());
    sender.setReadTimeout(props.readTimeout());

    return sender;
}
~~~

**Kiểm tra API phiên bản:** ở một số phiên bản Spring-WS cũ, setters timeout nhận `int` mili giây thay vì `Duration`. Khi dùng dòng cũ, đổi kiểu/đơn vị theo Javadoc cụ thể; không cast một `Duration` trực tiếp sang `int` hoặc nhầm seconds với milliseconds.

### 4.1. Đấu nối vào WebServiceTemplate

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.WebServiceMessageSender;

@Bean
WebServiceTemplate erpWebServiceTemplate(
        ErpSoapProperties props,
        Jaxb2Marshaller erpMarshaller,
        WebServiceMessageSender erpMessageSender) {

    WebServiceTemplate template = new WebServiceTemplate();
    template.setDefaultUri(props.uri().toString());
    template.setMarshaller(erpMarshaller);
    template.setUnmarshaller(erpMarshaller);
    template.setMessageSender(erpMessageSender);
    return template;
}
~~~

Đây là những `@Bean` methods đặt trong class `@Configuration` (ví dụ `ErpSoapConfiguration`) và cần bật `ErpSoapProperties`. Đừng đăng ký đồng thời hai sender beans cùng type mà không dùng `@Qualifier` hoặc có quy tắc inject rõ.

### 4.2. Thời gian chờ của URLConnection

| Timeout | Ý nghĩa | Không bảo đảm |
| --- | --- | --- |
| Connect timeout | Giới hạn thời gian chờ mở kết nối mạng (theo HTTP stack/JDK) | Toàn bộ lời gọi SOAP sẽ hoàn tất trong ngần ấy thời gian |
| Read timeout | Giới hạn thời gian chờ đọc dữ liệu/phản hồi | Deadline tổng của request |
| DNS resolution | Tra cứu hostname trước khi kết nối | Có thể không bị chặn chính xác bởi connect timeout |
| TLS handshake | Kết nối bảo mật, xác thực chain/hostname | Không mặc định có deadline độc lập ở mọi sender |
| Client total deadline | Budget tổng cho SOAP operation | Phải thiết kế ở application/transport tùy stack |

Với `HttpUrlConnectionMessageSender`, không giả định có một connection pool cấu hình được như Apache HttpClient. Keep-alive của JDK có thể tái sử dụng socket, nhưng khả năng giới hạn pending acquisitions và số connection được điều chỉnh khác với pool chuyên dụng.

### 4.3. Khi nào không chọn sender này?

Nếu workload có hàng trăm concurrent SOAP calls, nhiều proxy, credential scopes hoặc cần pool metrics, Apache HttpClient sender thường giúp kiểm soát tốt hơn. Tuy nhiên việc thêm pool không tự giải quyết SQL transaction lâu hay downstream throughput thấp; phải đo thực tế.

## 5. Sender dùng Apache HttpClient và connection pooling

Spring-WS cung cấp các sender hỗ trợ Apache HttpClient theo phiên bản:

- Legacy `HttpComponentsMessageSender` gắn với Apache HttpClient 4 trong nhiều dự án cũ.
- `HttpComponents5MessageSender` sử dụng API Apache HttpClient 5 ở các phiên bản Spring-WS hỗ trợ.
- Class/package, constructor và HTTP client builder cụ thể **phải kiểm tra với dependency graph thực**.

Với Apache HttpClient 5 có ba timeout thường được phân biệt:

| Khái niệm | Ví dụ lỗi | Điều khiển |
| --- | --- | --- |
| **Pool acquisition / connection request timeout** | Đã hết kết nối rảnh, caller chờ lease connection quá lâu | RequestConfig/pool client |
| **Connect timeout** | Không mở được socket đến host/proxy | ConnectionConfig/transport client tùy version |
| **Response/read timeout** | Endpoint chậm trả SOAP response hoặc socket không nhận dữ liệu | RequestConfig/SocketConfig tùy version |
| **TLS handshake timeout** | Handshake/certificate exchange chậm | TLS strategy/socket policy tùy client |
| **Total budget** | Nhiều bước hoặc nhiều retry tiêu thụ quá thời gian nghiệp vụ | Deadline ở adapter/caller |

Ví dụ wiring **chỉ ở tầng sender** sau khi ứng dụng đã tạo và cấu hình đúng một Apache 5 `HttpClient` có pool:

~~~java
import org.apache.hc.client5.http.classic.HttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.ws.transport.WebServiceMessageSender;
import org.springframework.ws.transport.http.HttpComponents5MessageSender;

@Bean
WebServiceMessageSender pooledErpSender(
        HttpClient erpApacheHttpClient) {
    return new HttpComponents5MessageSender(
            erpApacheHttpClient);
}
~~~

Snippet này phụ thuộc phiên bản Spring-WS có `HttpComponents5MessageSender` và HttpClient 5; nó **không tự cấu hình pool, TLS, Basic auth hay timeouts**. Các phần đó phải nằm trong `erpApacheHttpClient` do ứng dụng tạo. Không đăng ký sender này song song với `erpMessageSender` ở mục 4 nếu template chỉ cần một sender, trừ khi sử dụng `@Qualifier` tường minh.

### 5.1. Nguyên tắc cấu hình pool

Ví dụ một Inventory API có capacity cố định, bạn chọn:

~~~text
Max connections total       : 80
Max connections per route   : 20
Max SOAP calls per worker   : 8
Pool acquisition timeout   : 1 second
Connect timeout            : 2 seconds
Response timeout           : 10 seconds
~~~

Các giá trị chỉ minh họa; phải xét số replicas, QPS, response time, số downstream và quota ERP. Với 10 pod và `maxPerRoute=20`, tổng khả năng tạo connection tới ERP có thể lên tới 200, không phải 20.

Một pool nên:

- Giới hạn max total và max per route.
- Có connection request timeout để không chờ mãi khi bão hòa.
- Evict idle/stale connections và quản lý connection TTL theo HTTP client.
- Giữ hostname verification, truststore và client identity đúng khi reuse TLS connections.
- Theo dõi leased, pending, available và lỗi timeout từ pool/transport.
- Đóng resources theo lifecycle; nếu tạo custom `CloseableHttpClient`, quản lý shutdown phù hợp.

**Không giữ một object `HttpClient` được cấu hình cho ERP credentials rồi dùng chung tùy tiện với Payment/HR downstream.** Tách client/credential scope theo trust boundary.

### 5.2. HTTP/1.1 keep-alive không đồng nghĩa SOAP session

HTTP keep-alive có thể tái sử dụng socket cho nhiều SOAP requests, giảm chi phí TCP/TLS handshake. Nhưng:

- Một SOAP request vẫn phải có identity/idempotency theo nghiệp vụ.
- Connection reuse không đồng nghĩa server giữ business session.
- Cert rotation có thể không áp dụng lên kết nối TLS đã mở; phải kiểm tra lifecycle.
- Một pool lỗi stale connection có thể làm retry phức tạp vì request đã được gửi một phần.

Không dùng TLS session ID hoặc connection object identity làm khóa chống gửi SOAP trùng.

## 6. SOAP message factory, SOAP version và SOAPAction

`WebServiceTemplate` thao tác trên `WebServiceMessage`, còn `SoapMessageFactory` tạo SOAP Envelope. Nếu đối tác yêu cầu SOAP 1.2 nhưng client gửi SOAP 1.1, server có thể trả HTTP 415, SOAP VersionMismatch Fault hoặc lỗi contract khác.

### 6.1. SOAP 1.1 và SOAP 1.2

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| HTTP Content-Type thường gặp | `text/xml` | `application/soap+xml` |
| SOAPAction | HTTP header thường xuất hiện theo binding | Action có thể ở Content-Type parameter/binding |
| Fault structure | `faultcode`, `faultstring`, `detail` | `Code`, `Reason`, `Detail` |
| Nguồn sự thật | WSDL/binding và hợp đồng đối tác | WSDL/binding và hợp đồng đối tác |

Trong Spring-WS, có thể tạo message factory phù hợp; ví dụ cho SOAP 1.1:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Bean
SaajSoapMessageFactory erpSoapMessageFactory() {
    SaajSoapMessageFactory factory =
            new SaajSoapMessageFactory();
    factory.setSoapVersion(SoapVersion.SOAP_11);
    return factory;
}
~~~

Với SOAP 1.2, chọn `SoapVersion.SOAP_12` nếu SOAP message factory/Jakarta SOAP implementation hỗ trợ. Một số integration providers còn yêu cầu Content-Type/action rất cụ thể; không đổi SOAP version vì muốn sửa một HTTP 500 mà không đọc WSDL.

Đưa message factory vào template bằng constructor hoặc setter được Spring-WS version hỗ trợ:

~~~java
WebServiceTemplate template =
        new WebServiceTemplate(erpSoapMessageFactory);

template.setMarshaller(erpMarshaller);
template.setUnmarshaller(erpMarshaller);
template.setMessageSender(erpMessageSender);
template.setDefaultUri(props.uri().toString());
~~~

Đây là cấu hình **thay thế cách tạo template ở mục 4.1**, không phải bắt buộc tạo một template thứ hai.

### 6.2. SOAPAction không phải URL endpoint

Ví dụ gọi operation `SubmitOrder`:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

Object response =
        erpWebServiceTemplate.marshalSendAndReceive(
                request,
                new SoapActionCallback("urn:SubmitOrder"));
~~~

- `https://erp.example.org/soap/orders` là URL transport.
- `urn:SubmitOrder` là SOAPAction **do WSDL quy định**, không phải URL gọi mạng.
- `SubmitOrderRequest` là XML root element do XSD định nghĩa.
- Các giá trị này có thể khác nhau và không tự suy ra được cho mọi đối tác.

Không tự đặt SOAPAction bằng tên Java method nếu WSDL quy định action khác. Nếu SOAP 1.2/binding khác, xác minh Spring-WS xử lý action đúng chuẩn đang dùng.

## 7. Xác thực: HTTP Basic, Bearer, mTLS và WS-Security

Một hệ thống SOAP có thể sử dụng **nhiều lớp xác thực đồng thời**. Khi gọi bị 401/403 hoặc SOAP Fault liên quan security, phải biết đối tác kiểm tra ở đâu.

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["TLS/mTLS handshake"]
    B --> C["HTTP Authorization"]
    C --> D["SOAP Envelope Header"]
    D --> E["Application authorization"]
    E --> F["SOAP business handler"]
~~~

### 7.1. HTTP Basic authentication

HTTP Basic đặt `Authorization: Basic base64(username:password)` trong HTTP request. Base64 **không phải mã hóa**; chỉ dùng qua HTTPS và bảo vệ credentials.

~~~http
POST /soap/orders HTTP/1.1
Host: erp.example.org
Authorization: Basic <redacted>
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:SubmitOrder"
~~~

Các điểm quan trọng:

- Cấu hình credentials ở **HTTP client/message sender**, không phải JAXB request DTO.
- Dùng secret manager hoặc environment variables; không hardcode password trong `application.yml`.
- Xác định provider dùng challenge/response hay yêu cầu preemptive Basic; điều này có thể thêm round-trip hoặc tương tác với HTTP client pool.
- Không log Authorization header, wire request hoặc raw credentials.
- Khi đổi credential, có thể cần restart/reconfigure client/pool theo implementation.

**Một header SOAP `<UsernameToken>` không tương đương HTTP Basic.** Nếu đối tác yêu cầu WS-Security, gửi HTTP Basic dù đúng username/password vẫn có thể thất bại.

### 7.2. Bearer / OAuth2 client credentials

Một số SOAP endpoints hiện đại dùng OAuth2 ở HTTP layer:

~~~http
Authorization: Bearer <redacted-access-token>
~~~

Luồng service-to-service thông thường:

1. Client đã được cấp client credentials hoặc workload identity.
2. Token client lấy access token từ authorization server.
3. Token được thêm vào HTTP request đến SOAP endpoint.
4. Đối tác kiểm tra signature/introspection, `aud`, `scope`, expiration và chính sách riêng.
5. Token được cache/refresh có kiểm soát, không phát hành mới cho từng item nếu không cần.

Mã token phải được đưa vào **HTTP transport**, ví dụ qua request-level interceptor có khả năng viết HTTP headers trong sender hoặc custom HTTP client. Spring-WS `ClientInterceptor` thao tác ở tầng SOAP message; đừng giả định mọi interceptor SOAP đều có quyền sửa HTTP `Authorization`.

### 7.3. mTLS (mutual TLS)

Với mTLS:

- SOAP client xác minh **server certificate chain + hostname SAN**.
- HTTP sender trình **client certificate/private key** khi server yêu cầu.
- Server xác minh client certificate theo CA/usage/policy.
- Application có thể áp authorization từ certificate identity và token.

Đây là **TLS handshake**, không phải SOAP element. `spring.ssl.bundle.*` của Spring Boot giúp quản lý key/trust material, nhưng **không tự gắn mọi SSL bundle vào `WebServiceTemplate`**. Phải cấu hình **message sender/underlying HTTP client** sử dụng SSL context/bundle tương ứng.

~~~text
SOAP gateway
    |
    +-- WebServiceTemplate
         |
         +-- WebServiceMessageSender
              |
              +-- HTTP client TLS context
                   +-- KeyManager: client private key + certificate chain
                   +-- TrustManager: approved server CA(s)
                   +-- Hostname verification: enabled
~~~

Không sửa `PKIX path building failed` bằng trust-all manager hoặc tắt hostname verification. Cấp đúng CA chain/trust anchor, kiểm tra SAN/expiry/EKU và kiểm thử negative handshake.

### 7.4. WS-Security nằm trong SOAP Header

Các cơ chế thường gặp:

| WS-Security mechanism | Vai trò | Lưu ý |
| --- | --- | --- |
| UsernameToken | Định danh/credential trong SOAP header | Có PasswordText/PasswordDigest theo hợp đồng; cần TLS và policy chống replay |
| Timestamp | Giới hạn thời gian hợp lệ của message | Cần đồng bộ đồng hồ và kiểm soát clock skew |
| XML Signature | Ký các phần XML được chọn | Phải xác minh signed parts/keys và canonicalization |
| XML Encryption | Mã hóa nội dung XML được chọn | Khác với TLS hop-to-hop |
| SecurityTokenReference | Tham chiếu chứng chỉ hoặc token | Phụ thuộc profile WSDL/WS-Policy |

Spring Web Services có hỗ trợ **WSS4J security interceptor** trong module security phù hợp. Ví dụ cấu hình theo nguyên tắc (kiểm tra API và action strings theo Spring-WS/WSS4J version):

~~~java
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

// Minh họa cấu hình trong @Bean method với
// username/password được inject từ secret/config:
Wss4jSecurityInterceptor security =
        new Wss4jSecurityInterceptor();

security.setSecurementActions("UsernameToken Timestamp");
security.setSecurementUsername(serviceUsername);
security.setSecurementPassword(servicePassword);
~~~

Đây là **snippet**, không phải một security configuration hoàn chỉnh: `serviceUsername`/`servicePassword` phải đến từ secret, password type, nonce/timestamp/signature/crypto phải tuân theo WS-SecurityPolicy của đối tác. Cần cấu hình interceptor cho `WebServiceTemplate`, ví dụ `template.setInterceptors(...)` theo contract.

Với chữ ký số/WS-Security header, không tự nối XML strings vào SOAP body rồi hy vọng tương đương chữ ký; dùng thư viện chuẩn và kiểm chứng signed elements, certificate trust và replay policy.

### 7.5. Authorization vẫn là lớp riêng

Một client có certificate hợp lệ hoặc token xác thực được vẫn có thể **không được phép submit order cho tenant khác**. Server phải kiểm tra resource ownership, operation scope, đối tác và môi trường. Ở client, không nên đưa raw bearer token hoặc credential vào domain message để bị lưu trong SQL outbox/broker.

## 8. Proxy, firewall và định tuyến kết nối

Trong mạng doanh nghiệp, outbound HTTPS có thể đi qua egress proxy:

~~~text
Order Service → Egress proxy → Firewall → ERP SOAP endpoint
~~~

Proxy ảnh hưởng đến:

- DNS/hostname resolution, routing và CONNECT tunnel.
- Proxy authentication (HTTP 407), khác HTTP 401 từ ERP.
- TLS termination/re-encryption theo chính sách.
- Connection pooling theo route/proxy.
- Timeout ở từng hop.
- Observability và identity propagation.

Không giả định mọi proxy đều chỉ chuyển tiếp byte. Nếu proxy TLS terminate, phải xác định **client đang xác minh certificate của proxy hay ERP**, mTLS diễn ra tại hop nào, và app có thật sự dùng identity mà đối tác yêu cầu không.

### 8.1. Endpoint whitelist và SSRF

Không cho người dùng gửi URL tùy ý để `WebServiceTemplate` gọi. Nếu API cho phép caller chọn `targetUrl`, attacker có thể hướng server tới metadata service/internal endpoints.

Ưu tiên cấu hình URL theo partner được phê duyệt; khi thực sự cần dynamic endpoints:

- Chỉ cho phép `https` và các hostname/port được phép.
- Giới hạn redirect; không tin redirect sang private IP/host lạ.
- Kiểm soát DNS rebinding, proxy route và network egress.
- Không bao giờ gắn ERP credentials lên domain không thuộc đối tác.
- Log endpoint theo tên logic, tránh log credential/url nhạy cảm.

## 9. Thời gian chờ: connect, read, pool và deadline tổng

Timeout là hợp đồng vận hành, không phải chỉ vài property.

~~~mermaid
sequenceDiagram
    participant A as SOAP Gateway
    participant P as HTTP pool
    participant N as DNS/TCP/TLS
    participant E as ERP Server
    A->>P: Borrow connection (pool acquisition timeout)
    P-->>A: Connection/slot
    A->>N: Resolve + connect + TLS handshake
    N-->>A: Connected/verified
    A->>E: POST SOAP payload
    E-->>A: SOAP response
    Note over A,E: Response/read timeout, operation deadline
~~~

### 9.1. Các loại timeout

| Timeout | Khi nào phát huy tác dụng | Sai lầm hay gặp |
| --- | --- | --- |
| **Connection request / lease timeout** | Chờ một connection từ pool client | Nhầm với connect timeout tới server |
| **TCP connect timeout** | Tạo socket/kết nối đến proxy/server | Nghĩ rằng nó giới hạn toàn bộ request |
| **TLS handshake timeout** | Chờ hoàn tất xác thực/cipher negotiation | Đặt read timeout mà không kiểm thử hành vi thực |
| **Socket/response/read timeout** | Chờ dữ liệu từ phía server | Coi là absolute deadline cho toàn bộ body |
| **Write timeout** | Đẩy request body lớn qua network | Bỏ qua vì request nhỏ trong test |
| **Total operation deadline** | Toàn bộ SOAP operation qua nhiều giai đoạn | Quên DNS, pool wait hoặc retry |
| **Retry budget** | Tổng số lần attempt/backoff | Chồng retry ở nhiều lớp |
| **Business SLA** | Từ lúc nhận event đến khi ERP xác nhận | Lấy một TCP timeout làm SLA cuối |

Ví dụ timeout policy cho một command có SLA 30s:

~~~text
Business deadline         : 30 s
Pool acquisition timeout  : 1 s
TCP connect timeout       : 3 s
Read/response timeout     : 8 s
Backoff                   : có jitter
Max attempts              : tối đa 2 hoặc 3 theo remaining budget
~~~

Các con số là minh họa; tổng thời gian thực có thể lớn hơn nếu mỗi attempt có nhiều stage và backoff. Không được lấy “3 attempts × 8s = 24s” làm deadline chắc chắn vì còn pool wait, DNS, TLS, connect và scheduling.

### 9.2. Hai loại read timeout cần phân biệt

Một **socket inactivity timeout** thường giới hạn khoảng không có dữ liệu trên socket; không nhất thiết giới hạn tổng thời gian nhận một response chảy rất chậm. Một **response deadline** hoặc cancel at application level có thể dùng để chặn toàn bộ operation.

Với SOAP response có body lớn, cần thêm giới hạn body size, parse depth và số phần tử XML; một response rất lớn có thể tiêu tốn CPU/RAM sau khi dữ liệu đã đọc xong.

### 9.3. Không cấu hình timeout ở WebServiceTemplate nếu sender mới là nơi áp dụng

`WebServiceTemplate` là lớp SOAP orchestration, trong khi các thời gian chờ HTTP phải được áp dụng trên **HTTP sender/client/connection manager** đang được template sử dụng.

Nếu ứng dụng thay `HttpUrlConnectionMessageSender` bằng `HttpComponents5MessageSender`, các giá trị timeout cũ không tự đi theo. Cần map lại policy sang Apache HttpClient 5 `ConnectionConfig`, `RequestConfig`, TLS strategy hoặc lớp cấu hình tương đương theo version.

### 9.4. Timeout không đồng nghĩa không có side effect

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant E as ERP
    participant D as ERP Database
    O->>E: SubmitOrder ORD-100
    E->>D: COMMIT order
    Note over O,E: Response mất do read timeout
    O->>O: Nhận timeout (outcome unknown)
    O->>E: Retry ORD-100
    E->>D: Có thể insert duplicate nếu không dedupe
~~~

Trong tình huống này, retry cùng request có thể gây **hai đơn hàng** nếu ERP không cung cấp idempotency hoặc lookup. **Timeout là thiếu thông tin về kết quả**, không phải bằng chứng request chưa đến đối tác.

## 10. Mapping response, HTTP status và SOAP Fault

Một client SOAP cần phân loại **transport outcome** và **business outcome**.

| Hiện tượng | Ví dụ | Phản ứng |
| --- | --- | --- |
| HTTP success + SOAP response hợp lệ | `SubmitOrderResponse accepted=true` | Map kết quả thành công |
| HTTP success + business rejection trong XML | `accepted=false` | Kết quả nghiệp vụ, không coi là network failure |
| SOAP Fault (Client/Sender) | Invalid orderId | Không retry nếu dữ liệu sai |
| SOAP Fault (Server/Receiver) | ERP internal error | Có thể retry theo policy và idempotency |
| HTTP 401/403 | Credentials/token/policy sai | Sửa auth; tránh retry dồn dập |
| HTTP 407 | Proxy authentication required | Kiểm tra proxy credentials |
| HTTP 404/415 | Endpoint hoặc SOAP content type sai | Kiểm tra URL, SOAP version, WSDL |
| HTTP 429/503 | Rate limit/unavailable | Retry có backoff theo hợp đồng |
| SSLHandshakeException | Untrusted CA/SAN/client cert | Sửa TLS material |
| SocketTimeoutException | Connect/read timeout | Phân biệt phase và trạng thái side effect |
| XmlMappingException | XML không khớp JAXB/XSD | Sửa contract; không retry mù |

### 10.1. Spring-WS exceptions quan trọng

Spring-WS có các exception ở các lớp khác nhau, chẳng hạn:

- `WebServiceIOException`: I/O lỗi khi gọi transport.
- `WebServiceTransportException`: transport trả trạng thái lỗi không được xử lý như SOAP Fault hợp lệ.
- `SoapFaultClientException`: SOAP Fault do resolver chuyển thành exception (với policy mặc định phù hợp).
- `XmlMappingException` và các subtype OXM: marshalling/unmarshalling lỗi.
- `WebServiceClientException`: nhóm exception của client Spring-WS.

Tên exception cuối có thể phụ thuộc sender, resolver và Spring-WS version. Khi xử lý lỗi, không chỉ `catch (Exception)` rồi đánh dấu mọi trường hợp là "network timeout". Cần giữ **cause chain** có kiểm soát để phân loại root cause, không log dữ liệu nhạy cảm.

### 10.2. SOAP Fault có thể đi cùng HTTP 500

Theo SOAP 1.1, server thường trả HTTP 500 kèm SOAP Fault hợp lệ:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/xml; charset=utf-8

<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Order amount invalid</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Đây là ví dụ Fault, **không phải HTTP 500 rỗng**. `WebServiceTemplate` có cơ chế xử lý SOAP Fault/connection error; không nên tắt kiểm tra HTTP status hoặc fault handling tùy tiện chỉ để qua một test của đối tác không chuẩn.

SOAP 1.2 có cấu trúc Fault khác; cần đọc WSDL, đặc tả và kiểm thử response fixture thực.

### 10.3. Một lớp kết quả rõ ràng

Nên phân biệt kết quả:

~~~java
public sealed interface ErpSubmitOutcome
        permits ErpSubmitOutcome.Accepted,
                ErpSubmitOutcome.Rejected,
                ErpSubmitOutcome.Unknown {

    record Accepted(String reference)
            implements ErpSubmitOutcome {}

    record Rejected(String businessCode)
            implements ErpSubmitOutcome {}

    record Unknown(String reasonCode)
            implements ErpSubmitOutcome {}
}
~~~

- `Accepted`: nhận được xác nhận nghiệp vụ hợp lệ.
- `Rejected`: đối tác xác định không áp dụng vì quy tắc nghiệp vụ.
- `Unknown`: không biết phía đối tác đã commit chưa, ví dụ timeout sau khi gửi.

Không biến mọi `Unknown` thành `Rejected`. Với payment/booking/order create, cần tra cứu kết quả hoặc dùng partner idempotency contract.

## 11. Retry, circuit breaker và idempotency

Retries là cơ chế phục hồi lỗi tạm thời, nhưng có thể khuếch đại tải và gửi trùng side effects.

### 11.1. Các điều kiện tối thiểu

Trước khi retry một SOAP command có side effect, xác định:

1. **Operation có idempotent không?** `GET status` thường dễ retry hơn `SubmitPayment`.
2. **Có business idempotency key không?** Ví dụ `operationId`/`orderId` được đối tác lưu duy nhất.
3. **Có API tra cứu trạng thái không?** Khi response bị mất.
4. **Lỗi thuộc nhóm retryable không?** 503/timeout tạm thời vs 401/validation fault.
5. **Tổng deadline còn không?** Không attempt sau khi SLA hết.
6. **Có thể chạy song song nhiều attempt không?** Cần ngăn retry storm.
7. **Broker consumer có redeliver ngoài retry ở HTTP client không?**

### 11.2. Ví dụ chính sách

| Lỗi | Retry tự động | Ghi chú |
| --- | --- | --- |
| Wrong QName/XSD | Không | Fix payload/version |
| HTTP Basic credentials sai | Không | Rotate/correct secret |
| TLS certificate untrusted | Không | Fix CA/truststore |
| SOAP Fault business rejected | Không | Business outcome |
| Server/Receiver Fault tạm thời | Có thể | Cần hợp đồng operation và idempotency |
| HTTP 503/429 | Có giới hạn | Backoff/jitter, xem Retry-After nếu applicable |
| Connect refused trước khi gửi | Có thể | Thường chưa tạo side effect |
| Read timeout sau write | Chỉ khi an toàn | Outcome có thể đã commit |
| Connection pool exhausted | Kiểm soát tải trước | Retry ngay thường làm quá tải thêm |

Đặt retry ở một **tầng điều phối rõ ràng**, ví dụ integration adapter hoặc message consumer. Nếu HTTP client, Resilience4j, Spring Retry và broker đều tự retry 3 lần, một message có thể gây 27 attempts không chủ đích.

### 11.3. Circuit breaker khác timeout

Circuit breaker giúp giảm lời gọi tới downstream đang lỗi và cho phép phục hồi có kiểm soát. Nó **không** thay timeout: một request có thể mắc kẹt nếu không có giới hạn network.

Tách các chức năng:

- Timeout giới hạn thời gian chờ của một phase/operation.
- Bulkhead/concurrency cap giới hạn số request cùng lúc.
- Circuit breaker tạm chặn calls khi downstream có tỷ lệ lỗi cao.
- Retry lặp lại những lỗi tạm thời đủ an toàn.
- Outbox/broker giúp ý định tích hợp không mất sau process crash.
- Idempotency/reconciliation bảo vệ business correctness khi có duplicate hoặc outcome unknown.

## 12. Transaction với SQL, outbox và SOAP

Một anti-pattern dễ thấy:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    orderRepository.markConfirmed(orderId);
    erpWebServiceTemplate.marshalSendAndReceive(
            buildSubmitRequest(orderId));
}
~~~

Khi ERP đã xử lý nhưng SQL transaction rollback, hai hệ có trạng thái trái ngược. Ngược lại, nếu SQL commit rồi SOAP timeout, caller không biết kết quả.

Một kiến trúc bền vững hơn:

~~~mermaid
flowchart LR
    A["Order command"] --> B["SQL transaction"]
    B --> C["Update order state"]
    B --> D["Insert SOAP outbox intent"]
    D --> E["Outbox relay / broker"]
    E --> F["ERP SOAP gateway"]
    F --> G["ERP"]
    F -.-> H["Retry + status lookup"]
    H -.-> I["Persist outcome / DLQ"]
~~~

Trong cùng SQL transaction, ghi order và ý định gọi ERP. Worker xử lý outbox sau commit, dùng operationId ổn định cho mọi attempt. Nếu timeout, xử lý trạng thái `UNKNOWN` và đối soát trước khi tạo side effect mới.

**Lưu ý:** mTLS, HTTP Basic, JAXB, WebServiceTemplate hoặc SOAP protocol **không tạo distributed transaction** cùng database. Ngay cả khi server nhận HTTP 200, vẫn cần đọc response contract để xác định ERP đã thực sự ghi nhận giao dịch.

### 12.1. Exactly-once không xuất hiện chỉ nhờ SOAP

Một business operation có thể bị gửi lại khi:

- Broker redeliver.
- Client retry vì timeout.
- Worker crash giữa "ERP accepted" và "outbox marked success".
- Một scheduled reconciliation job chạy lại.
- Caller dùng cùng request body nhưng sinh operationId mới.

Khóa dedupe phải là **business identity bền vững** (ví dụ partner operation ID hoặc một unique business command ID), không dùng TLS session ID, HTTP connection ID hoặc request traceId.

Nếu đối tác không hỗ trợ idempotency key, cần API status lookup hoặc quy trình manual reconciliation, đặc biệt với thanh toán/tạo hóa đơn/booking.

## 13. Bảo mật dữ liệu và logs

SOAP XML thường chứa dữ liệu nhạy cảm hơn so với payload đơn giản:

- Người mua, địa chỉ, số định danh, thông tin giao dịch.
- HTTP Authorization/Bearer token.
- SOAP Header chứa WS-Security UsernameToken/Signature.
- Certificate details hoặc transport metadata.
- Business identifiers có thể dùng để truy vết cá nhân.

**Không bật wire logging request/response toàn phần trên production** chỉ để debug. Nếu cần điều tra, cấu hình redaction và retention, chỉ mở tạm thời với kiểm soát quyền.

Những việc cần làm:

1. HTTPS/TLS, hostname verification và CA trust đúng.
2. Credential storage qua vault/secret manager; không đẩy vào repository.
3. Phân tách client identities/truststores giữa môi trường và đối tác.
4. Giới hạn request/response size, XML depth và chặn XXE.
5. Validate XSD và SOAP/WS-Security signatures nếu contract yêu cầu.
6. Không ghi raw XML, token hoặc PII vào metric tags.
7. Giới hạn outbound endpoint theo allowlist, chống SSRF.
8. Xác thực callback/webhook nếu ERP có phản hồi bất đồng bộ.
9. Dùng TLS và WS-Security đúng threat model; TLS hop-to-hop không thay XML Signature khi cần non-repudiation/message-level security.

### 13.1. mTLS và certificate rotation

Nếu sender dùng SSLContext với client certificate, certificate rotation cần xem:

- Key/trust material mới đã được nạp vào HTTP client chưa?
- Connection pool cũ còn giữ TLS sessions/cert cũ không?
- Downstream đã chấp nhận new issuing CA chưa?
- Có cần rebuild HttpClient/WebServiceMessageSender hoặc restart pod không?
- Có test positive/negative sau rotation không?

Không giả định `spring.ssl.bundle` chỉ cần đổi file trên disk là mọi sender/connection đang mở tự cập nhật. Một số Boot integrations hỗ trợ reload, nhưng custom Apache client/SSLContext có thể không.

## 14. Kiểm thử SOAP payload với MockWebServiceServer

`MockWebServiceServer` của Spring-WS có thể kiểm tra SOAP payload và response **mà không dùng HTTP socket thật**.

Giả định:

- `com.example.erp.generated` có JAXB root classes cho `SubmitOrderRequest` và `SubmitOrderResponse`.
- `Jaxb2Marshaller` có thể marshal/unmarshal hai root.
- Có dependency `spring-ws-test`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

class ErpSoapGatewayTest {

    @Test
    void sendsSoapPayloadAndReadsResponse() throws Exception {
        Jaxb2Marshaller mapper = new Jaxb2Marshaller();
        mapper.setContextPath("com.example.erp.generated");
        mapper.afterPropertiesSet();

        WebServiceTemplate template =
                new WebServiceTemplate();
        template.setMarshaller(mapper);
        template.setUnmarshaller(mapper);
        template.setDefaultUri(
                "https://erp.test/soap/orders");

        MockWebServiceServer server =
                MockWebServiceServer.createServer(template);

        String requestXml =
                "<e:SubmitOrderRequest "
                + "xmlns:e=\"urn:example:orders:v1\">"
                + "<e:orderId>ORD-100</e:orderId>"
                + "</e:SubmitOrderRequest>";

        String responseXml =
                "<e:SubmitOrderResponse "
                + "xmlns:e=\"urn:example:orders:v1\">"
                + "<e:accepted>true</e:accepted>"
                + "<e:reference>ERP-55</e:reference>"
                + "</e:SubmitOrderResponse>";

        server.expect(payload(new StringSource(requestXml)))
                .andRespond(
                        withPayload(
                                new StringSource(responseXml)));

        Object result =
                template.marshalSendAndReceive(
                        new SubmitOrderRequest("ORD-100"));

        org.junit.jupiter.api.Assertions.assertNotNull(result);
        server.verify();
    }
}
~~~

Đây là **test skeleton phụ thuộc DTO generated thực**. Constructor `new SubmitOrderRequest("ORD-100")` chỉ hợp lệ nếu generated class có constructor đó; XJC thông thường có thể chỉ sinh no-arg constructor và setters, vì vậy điều chỉnh cách tạo DTO theo code thực tế. Mục tiêu của ví dụ là matcher/response handling, không phải một class tự chạy độc lập.

**Giới hạn quan trọng:** MockWebServiceServer thay connection để mock transport, vì thế **không chứng minh** HTTP sender đã cấu hình Basic/Bearer, TLS/mTLS, proxy, pool hoặc read timeout đúng. Cần integration tests riêng.

## 15. Kiểm thử HTTP transport, auth và timeout

### 15.1. Dùng SOAP HTTP stub hoặc server local

Dùng WireMock, MockWebServer hoặc test HTTP server có thể trả SOAP Envelope thật. Các bước:

1. Khởi động stub trên port động.
2. Trỏ `integrations.erp.uri` tới server test, không tới production.
3. Assert HTTP method POST, Content-Type, SOAPAction và HTTP Authorization policy.
4. Stub response SOAP 1.1/1.2 hợp lệ, HTTP 500 SOAP Fault, 401, 503 và 415.
5. Giả lập connect/read timeout theo transport mà test server hỗ trợ.
6. Kiểm tra retry budget, error classification và không log secret.
7. Dừng server/HTTP client pool sau test.

**Không thử authentication bằng việc đưa credential thật của production vào test suite.**

### 15.2. Test mTLS phải dùng handshake TLS thật

Test mock SOAP payload không thể kiểm chứng certificates. Cần TLS-enabled server với certificate test, trust chain và client-auth bắt buộc:

| Test case | Kỳ vọng |
| --- | --- |
| Valid server cert + trusted client cert | Handshake pass |
| Client không có certificate | Handshake bị từ chối nếu server yêu cầu |
| Sai CA trust | Client hoặc server từ chối chain |
| Hostname không nằm trong SAN | Client từ chối |
| Client cert hết hạn | Handshake bị từ chối |
| Server yêu cầu WS-Security ngoài mTLS | Handshake pass nhưng SOAP security validation fail nếu thiếu header |

Nếu dùng proxy/mesh termination, phải kiểm tra riêng từng TLS hop; JVM có thể không trực tiếp xem client certificate từ caller gốc.

### 15.3. Test connection pool saturation

Một load/integration test có thể:

- Đặt `maxPerRoute` thấp và tăng concurrency.
- Quan sát thời gian chờ acquire.
- Bật timeout hữu hạn để một request không chờ mãi.
- Xác nhận rejected/timeout được phân loại đúng.
- Xác nhận retry không làm tăng traffic vượt ngân sách.
- Kiểm tra connection được trả về pool khi có SOAP Fault hoặc XML parse error.

Không thực hiện saturation test lên ERP thật khi chưa có quyền và giới hạn tải rõ ràng.

### 15.4. Test outcome unknown và idempotency

Một test quan trọng:

~~~text
Given: ERP stub đã ghi nhận operationId=ORDER-100
And:   ERP intentionally drops/holds response
When:  Client receives read timeout
Then:  Adapter records UNKNOWN
And:   Client does not blindly create a new operationId
When:  Worker retries or reconciles
Then:  One business operation is recorded according to contract
~~~

Nếu đối tác không có idempotency API, test nên xác minh đường `UNKNOWN → manual reconciliation` hoặc status lookup tương ứng. Không giả lập “một lần gọi HTTP” thành chứng minh exactly-once.

## 16. Observability và chỉ số cần theo dõi

Đo ở hai cấp: transport và nghiệp vụ.

| Metric/Observation | Ý nghĩa |
| --- | --- |
| `integration.soap.request.duration` | Thời gian gọi SOAP client đồng bộ |
| `integration.soap.request.count` | Số attempts |
| `integration.soap.fault.count` | SOAP Fault phân loại theo fault code |
| `integration.soap.transport.error` | TLS, timeout, connect errors |
| HTTP connection pool leased/pending | Cạnh tranh connection |
| Retry attempts và next retry age | Mức độ phục hồi |
| Outbox pending/oldest age | Tồn đọng ý định gọi ERP |
| Business confirmation lag | Từ command commit đến ERP confirmed |
| Reconciliation pending/failed | Outcome chưa xác định cần xử lý |

Micrometer `Observation` có thể bọc một call:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ws.client.core.WebServiceTemplate;

public Object submitObserved(
        WebServiceTemplate template,
        ObservationRegistry registry,
        Object request) {

    return Observation.createNotStarted(
                    "integration.soap.submit", registry)
            .lowCardinalityKeyValue("partner", "erp")
            .lowCardinalityKeyValue("operation", "submitOrder")
            .observe(() ->
                    template.marshalSendAndReceive(request));
}
~~~

Observation đo **thời gian đồng bộ từ lời gọi đến return/exception**; nó không xác nhận business commit ở ERP. Nếu project chưa cấu hình meter/tracing handler cho `ObservationRegistry` thì không mặc nhiên có timer/span xuất ra backend.

Tags nên có tập giá trị hữu hạn:

~~~text
partner   = erp
operation = submitOrder
result    = success | soap_fault | transport_error
~~~

Không đưa `orderId`, `operationId`, XML payload, email, access token, certificate serial hoặc raw URL có query vào metrics labels. Cần audit/correlation theo ID thì lưu trong hệ thống log/audit được bảo vệ với retention và redaction policy.

### 16.1. Correlation qua SOAP/Header

Một `operationId` ổn định có thể được đưa vào **business payload hoặc SOAP header theo WSDL/WS-Policy** và lưu trong outbox. Nó giúp đối tác tra cứu/đối soát.

Phân biệt:

- `traceId`: nối observability của **một attempt**, có thể thay đổi khi retry.
- `operationId`: định danh **business intent**, cần ổn định xuyên retry.
- `SOAPAction`: chọn operation theo binding, không phải correlation ID.
- `Message-ID` của WS-Addressing nếu dùng: là metadata protocol, không tự tạo idempotency ở ERP.

### 16.2. Dashboard theo ranh giới

Một dashboard tốt nên đặt:

- Inbound business command throughput/error.
- Outbox age và retry backlog.
- SOAP transport latency p95/p99, connect/read/pool timeout.
- HTTP status 401/403/429/503 và SOAP Fault code rate.
- TLS certificate expiry/handshake failures theo downstream.
- ERP business accept/reject/unknown counts.
- Release/credential/certificate rotation timeline.

Một tăng đột biến `SOAP Fault Sender` sau deploy thường gợi ý mapping/WSDL change; một tăng `connect timeout` cùng DNS failures gợi ý network/endpoint; một tăng `pool pending` có thể vì connection limit hoặc downstream chậm. Không gộp mọi tín hiệu thành “SOAP không ổn”.

## 17. Runbook chẩn đoán lỗi

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `UnknownHostException` | DNS/endpoint sai hoặc không resolve | Kiểm tra DNS/config và egress |
| `ConnectException: Connection refused` | Sai port, service down, firewall/proxy | Kiểm tra route và listening endpoint |
| `Connect timed out` | Network không mở connection kịp | Connect timeout, routing, proxy |
| `Read timed out` | ERP chậm, response treo, network stall | SLA, server logs, outcome unknown |
| Pool acquire timeout | Hết connection rảnh hoặc concurrency quá lớn | Leased/pending, pool sizing, bulkhead |
| `PKIX path building failed` | Truststore thiếu CA/intermediate | Cài đúng chain, không trust-all |
| `No subject alternative DNS name matching` | Hostname sai SAN | Sửa URL/cert SAN, không disable hostname |
| TLS client cert rejected | Client key/cert/CA/EKU/policy sai | Kiểm tra mTLS config |
| HTTP 401 | Basic/Bearer credentials hoặc token sai | Kiểm tra secret, audience/scope |
| HTTP 407 | Proxy yêu cầu authentication | Cấu hình proxy credentials đúng |
| HTTP 403 | Authenticated nhưng không có quyền | Policy của ERP/gateway |
| HTTP 415 | SOAP 1.1/1.2 Content-Type mismatch | Kiểm tra message factory/WSDL |
| HTTP 500 + SOAP Fault | Lỗi SOAP protocol/business/service | Phân loại fault theo code/detail |
| HTTP 500 + HTML body | Proxy/app server lỗi, không phải SOAP | Kiểm tra response và content type |
| JAXB unexpected element | Root QName/schema không khớp | Regenerate/validate XSD |
| Lỗi sau đổi thư viện HTTP | Apache HttpClient 4/5 API không khớp | So dependency và sender class |
| Credentials lộ qua logs | Wire logging hoặc exception message không redact | Tắt/kiểm soát logging |
| Duplicate order sau timeout | Không có idempotency/reconcile | Dùng stable operationId/outbox |

### 17.1. Chẩn đoán theo thứ tự

1. Xác nhận URI, DNS, port và proxy, không log secrets.
2. Kiểm tra TLS certificate chain, hostname SAN và mTLS client identity.
3. Kiểm tra HTTP credentials/headers (chỉ metadata đã redact).
4. Xác nhận SOAP version, SOAPAction và WSDL/XSD phù hợp.
5. Xem connect, pool acquisition và read timeout riêng.
6. Đọc SOAP Fault nếu có; phân biệt với HTTP proxy error.
7. Xem idempotency key/ERP status trước khi retry command có side effect.
8. Dùng SOAP fixture/HTTP stub để tái hiện mà không gọi production.
9. Theo dõi metrics sau sửa để biết lỗi thực sự đã giảm.

**Không khắc phục** bằng cách tắt hostname verification, xóa truststore, tăng mọi timeout vô hạn, cho phép DTD hay retry tất cả các exception.

## 18. Checklist triển khai SOAP HTTP sender

- [ ] Đã xác định endpoint URI, SOAP 1.1/1.2, WSDL/XSD và SOAPAction chính xác.
- [ ] `WebServiceTemplate` được nối với marshaller, message factory và sender phù hợp.
- [ ] Chọn `HttpUrlConnectionMessageSender` hoặc Apache HttpClient sender theo nhu cầu, **đúng version**.
- [ ] Connect/read/pool acquisition/handshake timeouts và total deadline được xác định rõ.
- [ ] Connection pool có giới hạn per-route, max total, idle cleanup và chính sách shutdown.
- [ ] HTTP Basic/Bearer, mTLS, WS-Security được phân biệt và cấu hình ở đúng tầng.
- [ ] Không hardcode/log credentials, bearer token, SOAP security header hoặc payload nhạy cảm.
- [ ] CA chain/hostname verification luôn bật; rotation được kiểm thử với connection pools.
- [ ] Proxy/egress và endpoint allowlist chống SSRF được cấu hình.
- [ ] SOAP Fault, HTTP status và XML binding error được phân loại riêng.
- [ ] Retry có budget, backoff và policy idempotency/unknown outcome; không chồng retry đa tầng.
- [ ] SQL outbox/broker acknowledgment phù hợp transaction/durability contract.
- [ ] Có `MockWebServiceServer` payload tests **và** transport integration tests cho auth/TLS/timeout.
- [ ] Có observability latency, pool saturation, fault type, retry, outbox age, business outcome.
- [ ] Dashboard/logs không lộ PII hoặc tạo metric labels có cardinality cao.

**Ghi nhớ:** Trong Spring Web Services, `WebServiceTemplate` điều phối SOAP request/response, `Jaxb2Marshaller` chuyển đổi object–XML và **`WebServiceMessageSender` chịu trách nhiệm kết nối HTTP**. Bảo vệ tích hợp production không chỉ là đặt URL HTTPS; cần sender đúng phiên bản, xác thực đúng tầng, timeout có giới hạn, xử lý SOAP Fault, retry/idempotency, kiểm thử transport thật và observability. Những quyết định này giữ luồng tích hợp SOAP/HTTP nhất quán với các nguyên tắc chung của Spring Boot Integration về **cấu hình, hợp đồng dữ liệu, giao dịch, lỗi và xử lý trùng lặp**.

## Tài liệu tham khảo

- [Spring Web Services — Client-side Web Services](https://docs.spring.io/spring-ws/docs/current/reference/html/#client): `WebServiceTemplate`, callback, sender và fault handling.
- [Spring Web Services — API: WebServiceTemplate](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/client/core/WebServiceTemplate.html): cấu hình sender, marshaller, fault resolver.
- [Spring Web Services — API: WebServiceMessageSender](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/transport/WebServiceMessageSender.html): abstraction transport.
- [Spring Web Services — API: HttpUrlConnectionMessageSender](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/transport/http/HttpUrlConnectionMessageSender.html): HTTP URLConnection sender và timeouts.
- [Spring Boot — Web Services](https://docs.spring.io/spring-boot/reference/io/webservices.html): Spring-WS auto-configuration và client support.
- [Spring Framework — O/X Mapping](https://docs.spring.io/spring-framework/reference/data-access/oxm.html): JAXB/Jaxb2Marshaller và XML contract.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles, CA trust và key materials.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client-credentials và token lifecycle.
- [Apache HttpClient 5 — Project](https://hc.apache.org/httpcomponents-client-5.5.x/index.html): connection pooling, TLS, credentials và transport.
- [Spring Web Services — WS-Security](https://docs.spring.io/spring-ws/docs/current/reference/html/#security): WSS4J, SOAP signatures, timestamps và security policies.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): observation lifecycle và metrics/traces.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS versions, certificate verification và an toàn cấu hình.
