# HttpComponents5MessageSender và cấu hình Apache HttpClient 5

Một SOAP client có thể tạo XML đúng XSD, gửi đúng SOAPAction và khai báo JAXB model hợp lệ nhưng vẫn thất bại vì **kết nối HTTP**: không lấy được connection trong pool, timeout khi thiết lập TLS, proxy chuyển hướng sai, chứng chỉ mTLS không phù hợp hoặc một request đã được server xử lý nhưng client mất response. Đối với hệ thống tích hợp doanh nghiệp, cấu hình message sender vì thế là một phần của **độ tin cậy, hiệu năng và bảo mật**, không đơn thuần là chọn thư viện HTTP.

Trong **Spring Web Services (Spring-WS)**, `WebServiceTemplate` điều phối việc tạo SOAP message và truyền nó bằng `WebServiceMessageSender`. `HttpComponents5MessageSender` là message sender sử dụng **Apache HttpClient 5 classic (blocking)** cho HTTP(S) POST. Nó thuận tiện khi SOAP client cần connection pooling, timeout có kiểm soát, HTTP authentication, cấu hình TLS/mTLS, proxy hoặc quan sát kết nối. Tuy nhiên cần phân biệt **cấu hình sender do Spring-WS quản lý** với **HttpClient 5 tự xây dựng**; đặc biệt, API của Spring-WS 4.1 có thay đổi quan trọng khi nhận một `HttpClient` do ứng dụng cung cấp.

Bài này thuộc chương **HTTP và kết nối** của module **SPRING_WEB_SERVICES**. Trong bối cảnh phát triển SOAP **contract-first** bằng XSD/WSDL, JAXB, endpoint và SOAP client, sender chỉ chịu trách nhiệm **transport**; nó không thay thế payload validation, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Mục tiêu là cấu hình đúng từng tầng, hiểu giới hạn của các loại timeout và biết cách chẩn đoán lỗi HTTP mà không nhầm với lỗi XML/SOAP.

## 1. Sender nằm ở đâu trong lời gọi SOAP client?

~~~mermaid
flowchart LR
    A["Java request<br/>JAXB object"] --> O["Jaxb2Marshaller<br/>XML payload"]
    O --> F["WebServiceMessageFactory<br/>SOAP Envelope"]
    F --> T["WebServiceTemplate"]
    T --> S["HttpComponents5MessageSender<br/>Apache HttpClient 5"]
    S --> P["Proxy / TLS / mTLS"]
    P --> R["SOAP endpoint"]
    R --> P
    P --> S
    S --> T
    T --> U["SOAP Fault handler<br/>hoặc JAXB unmarshaller"]
    U --> B["Java response / exception"]
~~~

| Thành phần | Trách nhiệm | Điều **không** tự làm |
| --- | --- | --- |
| `Jaxb2Marshaller` | Marshal Java object thành XML Body; unmarshal response XML | Không mở HTTPS connection |
| `SaajSoapMessageFactory` | Tạo/đọc SOAP Envelope, Header và Body theo SOAP 1.1/1.2 | Không cấu hình pool HTTP |
| `WebServiceTemplate` | Phối hợp gửi request, nhận response/Fault, chạy callback/interceptor | Không tự quyết định mọi TLS/timeout theo hợp đồng |
| `HttpComponents5MessageSender` | Kết nối HTTP(S), gửi/nhận SOAP bytes, quản lý HTTP client/pool | Không xác minh nghiệp vụ hoặc tự ký SOAP |
| `Wss4jSecurityInterceptor` khi được cấu hình | WS-Security: ký, mã hóa, kiểm tra thông điệp | Không thay thế TLS trust/hostname verification |

**Dòng phân giới:** WSDL/XSD xác định **thông điệp phải là gì**; message factory/OXM xác định **biểu diễn SOAP/XML**; Apache HttpClient 5 xác định **cách gửi và nhận qua HTTP**.

Ví dụ, `GetOrderRequest` có QName `{urn:example:orders:v1}GetOrderRequest` và được gửi đến `https://partner.example.org/soap`. Sender không kiểm tra QName đó; client cần cấu hình JAXB/schema validation phù hợp. Ngược lại, QName đúng sẽ không sửa được lỗi `PKIX path building failed` tại TLS.

## 2. Chọn đúng thế hệ Spring-WS và Apache HttpClient

Tên các class HTTP sender khá giống nhau nhưng **không thể thay thế theo tên**:

| Thành phần | Hệ sinh thái | Khi dùng |
| --- | --- | --- |
| `HttpUrlConnectionMessageSender` | API HTTP URLConnection | Client cơ bản, yêu cầu transport đơn giản |
| `HttpComponentsMessageSender` | Apache HttpClient **4.x**, package `org.apache.http.*` | Hệ thống Spring-WS cũ tương ứng |
| **`HttpComponents5MessageSender`** | Apache HttpClient **5.x**, package `org.apache.hc.*` | Client sử dụng HttpClient 5 và Spring-WS tương thích |
| **`SimpleHttpComponents5MessageSender`** | Spring-WS **4.1+** với HttpClient 5 do ứng dụng cung cấp | Khi tự build HttpClient 5 hoặc dùng `HttpComponents5ClientFactory` |

Theo JavaDoc Spring-WS, `HttpComponents5MessageSender` có từ **Spring-WS 4.0.5**. Trong nhánh **4.0.x**, có constructor nhận `org.apache.hc.client5.http.classic.HttpClient`. **Từ Spring-WS 4.1.0**, constructor đó và `setHttpClient(...)` được đánh dấu **deprecated, dự kiến loại bỏ**, và tài liệu khuyên dùng `SimpleHttpComponents5MessageSender` khi muốn cung cấp HTTP client đã cấu hình sẵn.

Vì vậy bài dùng hai hướng:

1. **Cấu hình cơ bản:** `new HttpComponents5MessageSender()` rồi gọi các setter được hỗ trợ, để Spring-WS quản lý việc dựng HTTP client.
2. **Cấu hình nâng cao trên Spring-WS 4.1+:** xây dựng qua `HttpComponents5ClientFactory.withDefaults()` rồi cung cấp cho `SimpleHttpComponents5MessageSender`, hoặc tự xây `CloseableHttpClient` và truyền cho Simple sender.

**Không dùng `new HttpComponents5MessageSender(customClient)` làm ví dụ khuyến nghị chung**: nó vẫn tồn tại ở 4.0.x, nhưng đã bị deprecated trong 4.1. Ngoài ra, truyền một client tự dựng **không tự thêm** bộ lọc các HTTP headers xung đột, và không tự áp các setter timeout của sender.

### 2.1. Dependencies Maven

Trong dự án Spring Boot có BOM/dependency management tương thích với Spring-WS:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.apache.httpcomponents.client5</groupId>
        <artifactId>httpclient5</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **đoạn dependencies**, không phải POM hoàn chỉnh. Nếu BOM không quản lý một dependency, phải chọn version tương thích theo ma trận của Spring-WS/Spring Boot; không xóa version bừa mà không có dependency management. JAXB/OXM, SAAJ và các phần WS-Security có thể đòi những dependency khác theo dự án.

Apache HttpClient 5 dùng `org.apache.hc.client5.*` và HttpCore 5 dùng `org.apache.hc.core5.*`. Không copy imports kiểu `org.apache.http.client.*` (HttpClient 4) vào code HttpClient 5.

## 3. Cấu hình HttpComponents5MessageSender đơn giản

Ví dụ dưới đây dành cho **Spring-WS 4.1.x**, sử dụng setter có kiểu `java.time.Duration` và pool mặc định được Spring-WS xây dựng:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.HttpComponents5MessageSender;

@Configuration
public class PartnerTransportConfiguration {

    @Bean
    public HttpComponents5MessageSender partnerMessageSender() {
        HttpComponents5MessageSender sender =
                new HttpComponents5MessageSender();

        sender.setConnectionTimeout(Duration.ofSeconds(3));
        sender.setReadTimeout(Duration.ofSeconds(12));
        sender.setMaxTotalConnections(80);
        sender.setMaxConnectionsPerHost(
                Map.of("https://partner.example.org:443", "20"));
        return sender;
    }
}
~~~

Các giá trị `3s`, `12s`, `80`, `20` chỉ để minh họa; chọn theo SLA, kích thước SOAP payload, số lượng worker và giới hạn rate/concurrency của đối tác.

**Giải thích:**

- Constructor không tham số tạo sender với **HTTP client/pooling connection manager mặc định**.
- `setConnectionTimeout(Duration)` đặt giới hạn kết nối theo API sender.
- `setReadTimeout(Duration)` đặt giới hạn đọc socket theo API sender.
- `setMaxTotalConnections(int)` đặt số connection tối đa trong manager mặc định.
- `setMaxConnectionsPerHost(Map<String,String>)` cấu hình giới hạn theo host/route. API này nhận **map các chuỗi**, không phải `Map<String,Integer>`; hostname nên được ghi theo định dạng URI được JavaDoc của version hỗ trợ.
- Spring gọi `afterPropertiesSet()` cho bean khi khởi tạo, để sender tạo client theo cấu hình.

**Không thay `setMaxConnectionsPerHost(...)` bằng `setMaxConnPerRoute(...)` trên sender**: phương thức thứ hai thuộc connection manager Apache, không phải API trực tiếp của Spring-WS sender. Phân biệt rõ cấp cấu hình giúp tránh lỗi biên dịch.

### 3.1. Gắn sender vào WebServiceTemplate

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;
import org.springframework.ws.transport.http.HttpComponents5MessageSender;

@Bean
public WebServiceTemplate partnerWebServiceTemplate(
        SaajSoapMessageFactory soap11Factory,
        Jaxb2Marshaller ordersOxm,
        HttpComponents5MessageSender partnerMessageSender) {

    WebServiceTemplate template =
            new WebServiceTemplate(soap11Factory);
    template.setMessageSender(partnerMessageSender);
    template.setMarshaller(ordersOxm);
    template.setUnmarshaller(ordersOxm);
    template.setDefaultUri("https://partner.example.org/soap");
    return template;
}
~~~

Ví dụ giả định `soap11Factory` và `ordersOxm` là bean đã được cấu hình đúng SOAP version/JAXB packages. Không đăng ký hai template beans có cùng tên hoặc dùng URL `.wsdl` làm `defaultUri`. Trong ứng dụng thật, lấy endpoint URL, timeout, pool limit từ **configuration có kiểm soát**, không hardcode secret trong source.

**Chỉ chọn một sender/configuration cho mỗi template theo nhu cầu.** Nếu code tiếp tục chạy `sender.setHttpClient(customClient)` sau khi set timeout/pool trong nhánh 4.1, bạn đang thay mô hình ownership và có thể làm các setter trước đó không còn tác dụng như dự kiến; hãy chuyển sang Simple sender khi cần custom client.

## 4. HTTP POST và SOAP binding: sender nhận gì, gửi gì?

Ví dụ SOAP 1.1 gửi một request `GetOrderRequest`:

~~~http
POST /soap HTTP/1.1
Host: partner.example.org
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:GetOrder"
Accept: text/xml

<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là minh họa **HTTP wire format**, không phải toàn bộ headers sẽ xuất hiện đúng nguyên văn: Apache HttpClient có thể thêm `Content-Length`, `Transfer-Encoding`, connection headers và tùy cơ chế nén/keep-alive. SOAP factory/callback, không phải pool manager, quyết định Envelope/Content-Type/action đúng binding.

| Thành phần trên dây | Nguồn kiểm soát chính |
| --- | --- |
| `POST /soap`, host, proxy | `WebServiceTemplate` URI và Apache HTTP sender |
| TLS/mTLS, certificate verification | SSL/TLS stack của HTTP client, cấu hình mạng |
| `Content-Type: text/xml` hay `application/soap+xml` | SOAP version/binding và message factory |
| `SOAPAction` theo SOAP 1.1 | `SoapActionCallback`/SOAP message API và WSDL |
| SOAP Header `wsse:Security` | WS-Security interceptor/policy, không phải HTTP sender |
| SOAP Body `ord:GetOrderRequest` | JAXB/OXM và XSD contract |

**Không sửa `Content-Type` thủ công thành SOAP 1.2 chỉ để qua một HTTP 415** khi Envelope do factory vẫn là SOAP 1.1. Hãy chọn đúng WSDL port, SOAP version, endpoint URL, JAXB namespace và sender settings.

## 5. Hiểu đúng các loại timeout của Apache HttpClient 5

Một lời gọi HTTP/SOAP có thể chờ ở **nhiều điểm**:

~~~mermaid
flowchart LR
    A["Client gọi"] --> B["Chờ lease trong pool<br/>connectionRequestTimeout"]
    B --> C["Mở TCP/TLS connection<br/>connectTimeout, TLS config"]
    C --> D["Ghi request SOAP"]
    D --> E["Chờ response<br/>responseTimeout"]
    E --> F["Đọc bytes<br/>socket/read timeout"]
    F --> G["Unmarshal JAXB"]
~~~

| Timeout | Ý nghĩa | Không kiểm soát được điều gì? |
| --- | --- | --- |
| **Connection request timeout** | Thời gian chờ được cấp connection từ pool | Không tự giới hạn network connect |
| **Connect timeout** | Thời gian tạo connection mới; TLS negotiation có đặc thù theo client/TLS config | Không bao phủ mọi thời gian xử lý SOAP |
| **Response timeout** | Chờ phản hồi từ server theo cách RequestConfig của HttpClient 5 hiểu | Không tự là deadline tổng hợp cho tất cả bước |
| **Socket/read timeout** | Thời gian chờ hoạt động I/O/đọc socket | Không đảm bảo toàn bộ request kết thúc trong một thời lượng tuyệt đối |
| **Overall business deadline** | Ngân sách thời gian của cả thao tác nghiệp vụ | Phải được thiết kế ở application/call boundary, không tự có từ một setter |

Đừng gộp mọi loại vào một biến `timeout=10000` mà không xác định setter đang điều chỉnh **giai đoạn** nào. Trong Apache HttpClient 5, kiểu giá trị thường là `Timeout`/`TimeValue`, còn sender Spring-WS 4.x dùng `Duration` cho một số setter; mỗi phiên bản có API riêng.

### 5.1. Khi pool hết connection

Nếu `max per route=20` nhưng 30 request đến cùng lúc, có thể có 20 request đang dùng connection và 10 request **đợi lease**. `connectTimeout` 3 giây không nhất thiết bảo vệ 10 request đang đợi pool. Cần cấu hình **connectionRequestTimeout** tại HttpClient 5 `RequestConfig` và giám sát pending requests/leased connections.

### 5.2. Timeout khi server đã xử lý request

Nếu `PlaceOrder` đã ghi database rồi server chậm trả response, client có thể nhận **response timeout**. Timeout chứng minh client **không nhận phản hồi đúng hạn**, không chứng minh server **chưa thực hiện thao tác**. Chính sách retry chỉ được áp dụng với operation idempotent, hoặc phải có **idempotency key** và khả năng đối soát trạng thái.

### 5.3. Đừng cấu hình timeout vô hạn để “hết lỗi”

Một số API coi giá trị zero là vô hạn; cấu hình bất hợp lý có thể giữ threads hoặc connection lease rất lâu. Với client gọi đối tác:

1. Đặt connect, lease và response/read timeout hữu hạn.
2. Đặt giới hạn tổng của workflow (nếu ứng dụng yêu cầu).
3. Giới hạn concurrency và bulkhead để một đối tác chậm không khóa toàn bộ service.
4. Phân loại timeout theo vị trí: pool wait, network connect, TLS handshake, response read.
5. Ghi metrics/correlation ID nhưng không log SOAP Security Header hoặc dữ liệu nhạy cảm.

## 6. Connection pooling: vì sao mặc định chưa đủ cho production?

Apache HttpClient 5 có `PoolingHttpClientConnectionManager`, giữ các kết nối có thể tái sử dụng theo **route**. Một route phụ thuộc đích (scheme, host, port) và có thể bao gồm proxy/tunnel. Pool hoạt động tốt khi nhiều SOAP calls đến cùng một đối tác, tránh liên tục thiết lập TCP/TLS.

| Khái niệm pool | Ý nghĩa thực tế |
| --- | --- |
| **Max total connections** | Trần số connection trong toàn manager |
| **Max connections per route** | Trần số connection cho một đường tới đích/proxy cụ thể |
| **Leased** | Connection hiện được request sử dụng |
| **Available** | Connection nhàn rỗi có thể tái sử dụng |
| **Pending** | Request đang đợi connection từ pool |
| **TTL** | Thời gian sống tối đa của connection |
| **Idle eviction** | Đóng connection nhàn rỗi theo chính sách |
| **Validate after inactivity** | Kiểm tra khả năng tái sử dụng connection nhàn rỗi trước khi dùng lại |

**Ví dụ sizing:** Nếu đối tác xử lý 40 requests/s và latency trung bình là 0,5 s, số request đồng thời trung bình xấp xỉ **20** (định luật Little, dưới giả định hệ thống ổn định). Pool per-route 20 chỉ vừa đủ **trung bình**, chưa tính đỉnh tải, đuôi latency, TLS connection churn và headroom. Cần đo `p95/p99 latency` và load test thay vì lấy công thức này làm kích thước pool mặc định.

### 6.1. Quy tắc sizing thực hành

- **Max per-route không được vượt max total** nếu chỉ có một route và muốn cấu hình dễ hiểu.
- Đừng tăng pool vô hạn: mỗi connection tiêu tốn socket/file descriptors, server-side resources và có thể làm đối tác quá tải.
- Pool lớn nhưng thread pool/request concurrency không được giới hạn vẫn có thể gây hàng đợi lớn.
- Theo dõi **leased/available/pending**; pending kéo dài là tín hiệu pool nhỏ, slow upstream hoặc connection leak.
- Đặt chính sách TTL/idle eviction phù hợp với load balancer và idle timeout của đối tác, để giảm “connection reset by peer” trên connection cũ.
- Nếu nhiều partner dùng certificate/trust khác nhau, cân nhắc **tách HTTP clients/pools** để không gửi credentials/transport identity nhầm đích.

### 6.2. Pooling không có nghĩa multiplexing SOAP

Classic `CloseableHttpClient` chủ yếu sử dụng request/response chặn luồng. Reuse nhiều TCP connections không đồng nghĩa **tất cả request cùng chạy trên một socket**. Đừng suy luận “tăng max total=100 là server sẽ xử lý 100 requests đồng thời”; còn giới hạn thread, tuyến mạng, proxy, rate limit và khả năng đáp ứng của đối tác.

## 7. Spring-WS 4.1+: dùng HttpComponents5ClientFactory để tùy biến

Khi cần **lease timeout**, response timeout, lựa chọn retry/redirect hoặc custom connection manager, tài liệu Spring-WS 4.1 hướng đến `HttpComponents5ClientFactory` và **`SimpleHttpComponents5MessageSender`**.

Ví dụ sau dùng API có trong **Spring-WS 4.1.x** và Apache HttpClient 5:

~~~java
import java.time.Duration;
import java.util.Map;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.HttpComponents5ClientFactory;
import org.springframework.ws.transport.http.SimpleHttpComponents5MessageSender;

@Configuration
public class PartnerAdvancedHttpConfiguration {

    @Bean
    public SimpleHttpComponents5MessageSender partnerAdvancedSender() {
        HttpComponents5ClientFactory factory =
                HttpComponents5ClientFactory.withDefaults();

        factory.setConnectionTimeout(Duration.ofSeconds(3));
        factory.setReadTimeout(Duration.ofSeconds(12));
        factory.setMaxTotalConnections(80);
        factory.setMaxConnectionsPerHost(
                Map.of("https://partner.example.org:443", "20"));

        factory.addClientBuilderCustomizer(builder -> {
            RequestConfig requestConfig = RequestConfig.custom()
                    .setConnectionRequestTimeout(Timeout.ofSeconds(2))
                    .setResponseTimeout(Timeout.ofSeconds(12))
                    .build();
            builder.setDefaultRequestConfig(requestConfig);

            // Tránh retry/redirect ngoài ý muốn với SOAP POST.
            builder.disableAutomaticRetries();
            builder.disableRedirectHandling();
        });

        return new SimpleHttpComponents5MessageSender(factory);
    }
}
~~~

**Điểm đáng chú ý:**

1. `withDefaults()` của Spring-WS 4.1 thiết lập các tùy chỉnh mặc định cho SOAP, trong đó có `RemoveSoapHeadersInterceptor` (xem phần 9).
2. `setConnectionTimeout`, `setReadTimeout` và pool settings điều chỉnh factory tạo Apache client.
3. `RequestConfig.setConnectionRequestTimeout(...)` giới hạn thời gian đợi **connection lease trong pool**.
4. `RequestConfig.setResponseTimeout(...)` đặt giới hạn đợi response theo Apache HttpClient 5.
5. `disableAutomaticRetries()`/`disableRedirectHandling()` là lựa chọn minh họa để SOAP POST không bị tự gửi lại hoặc chuyển đích mà không có chính sách nghiệp vụ.
6. `SimpleHttpComponents5MessageSender` nhận factory và dùng client được tạo từ cấu hình đó. **Không gọi thêm `setHttpClient(...)` trên `HttpComponents5MessageSender`** để thay đổi client sau khi đã cấu hình.

**Chú ý sự khác nhau giữa “read timeout” và “response timeout”:** ở ví dụ có cả hai để người học nhìn thấy API của Spring-WS lẫn Apache. Không mặc định hai thông số này đồng nhất trên mọi nhánh HttpClient 5; hãy kiểm tra provider/request config thực tế và test tình huống server trả headers chậm, body chậm. Tránh đặt các giá trị mâu thuẫn.

### 7.1. Vì sao dùng withDefaults thay vì new HttpComponents5ClientFactory()?

Spring-WS cung cấp `HttpComponents5ClientFactory.withDefaults()` để cấu hình các mặc định liên quan tương thích SOAP. Đặc biệt, khi tự xây client mà bỏ qua cơ chế loại bỏ HTTP headers do SOAP implementation thêm trước đó, Apache có thể từ chối request khi gặp headers như `Content-Length`/`Transfer-Encoding` không hợp lệ hoặc bị đặt hai lần.

Vì vậy, **withDefaults giúp giảm lỗi cấu hình thủ công**, nhưng không tự cài chính sách mTLS, truststore hay WS-Security cho doanh nghiệp. Cấu hình an toàn vẫn do ứng dụng chịu trách nhiệm.

## 8. Tự xây Apache CloseableHttpClient 5: kiểm soát sâu

Trong một số dự án cần tùy chỉnh trực tiếp connection manager, socket options hoặc HTTP execution chain. Với Spring-WS 4.1+, cung cấp `CloseableHttpClient` cho `SimpleHttpComponents5MessageSender`.

Ví dụ sau **cố ý tách khỏi ví dụ factory ở phần 7**; đây là một phương án thay thế, không đăng ký cả hai sender bean cho cùng client khi chưa dùng qualifier:

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.ws.transport.http.HttpComponents5ClientFactory;
import org.springframework.ws.transport.http.SimpleHttpComponents5MessageSender;

@Bean
public SimpleHttpComponents5MessageSender customApache5Sender() {
    PoolingHttpClientConnectionManager manager =
            PoolingHttpClientConnectionManagerBuilder.create()
                    .setMaxConnTotal(80)
                    .setMaxConnPerRoute(20)
                    .setDefaultConnectionConfig(ConnectionConfig.custom()
                            .setConnectTimeout(Timeout.ofSeconds(3))
                            .setSocketTimeout(Timeout.ofSeconds(12))
                            .setTimeToLive(TimeValue.ofMinutes(5))
                            .build())
                    .build();

    RequestConfig requests = RequestConfig.custom()
            .setConnectionRequestTimeout(Timeout.ofSeconds(2))
            .setResponseTimeout(Timeout.ofSeconds(12))
            .build();

    CloseableHttpClient client = HttpClients.custom()
            .setConnectionManager(manager)
            .setDefaultRequestConfig(requests)
            .addRequestInterceptorFirst(
                    new HttpComponents5ClientFactory.RemoveSoapHeadersInterceptor())
            .disableAutomaticRetries()
            .disableRedirectHandling()
            .build();

    return new SimpleHttpComponents5MessageSender(client);
}
~~~

**Phạm vi phiên bản:** đoạn này minh họa API Apache HttpClient 5 hỗ trợ `ConnectionConfig`/`setDefaultConnectionConfig` (đặc biệt các bản **5.2+**) và Spring-WS **4.1+**. Nếu dùng HttpClient 5.0/5.1 hoặc Spring-WS 4.0.x, tên API/cách cấu hình một số timeout khác; hãy đối chiếu JavaDoc đúng phiên bản thay vì copy máy móc.

**Đặc điểm:**

- `PoolingHttpClientConnectionManagerBuilder` xây pool theo policy.
- `ConnectionConfig` đặt connect/socket timeout và connection TTL.
- `RequestConfig` đặt timeout chờ pool lease và response.
- `HttpClients.custom()` xây **classic blocking** HTTP client.
- `addRequestInterceptorFirst(...)` bảo đảm interceptor loại bỏ hai header truyền tải xung đột được gắn khi tự xây Apache client.
- `SimpleHttpComponents5MessageSender` nhận đúng client tự tạo.

### 8.1. Vòng đời đóng client và pool

`CloseableHttpClient` giữ tài nguyên như socket/pool và cần được **đóng khi ứng dụng dừng**, không tạo mới cho mỗi SOAP request. Nếu Spring-WS sender quản lý vòng đời và đóng client, không khai báo thêm những bean khác **cùng đóng một instance** mà chưa hiểu ownership. Nếu ứng dụng tự quản lý một `CloseableHttpClient` dùng chung, cần xác định rõ **một chủ thể đóng** client/pool khi shutdown và tránh đóng trong lúc request đang chạy.

Không viết:

~~~java
public Object callPartner(Object request) {
    CloseableHttpClient client = HttpClients.createDefault();
    // Tạo client + pool mới mỗi request rồi bỏ quên đóng.
    // Đây không phải mẫu triển khai production.
    throw new UnsupportedOperationException("Ví dụ cần tránh");
}
~~~

Tái sử dụng template/sender/client đã cấu hình sau khởi tạo; đừng thay cấu hình `defaultUri`, SSLContext hoặc pool giữa những request đồng thời khi dùng singleton.

## 9. RemoveSoapHeadersInterceptor: lỗi nhỏ nhưng rất phổ biến

**Vấn đề:** một số SOAP message implementations (trong đó có SAAJ) có thể đặt sẵn HTTP transport headers như:

~~~http
Content-Length: 423
Transfer-Encoding: chunked
~~~

Apache HttpClient 5 phải quản lý chính xác encoding và độ dài entity. Khi các header này được đặt sẵn hoặc bị đặt trùng/trái quy tắc, client có thể ném lỗi HTTP trước khi gửi request.

Spring-WS cung cấp:

~~~java
new HttpComponents5ClientFactory.RemoveSoapHeadersInterceptor()
~~~

Interceptor này loại bỏ hai headers **`Content-Length`** và **`Transfer-Encoding`** khỏi request trước khi Apache HTTP client áp cách truyền thực tế. Nó **không** thay thế SOAP Header, không xóa `wsse:Security` hay `CorrelationId`, và không phải một `ClientInterceptor` của Spring-WS; đây là **Apache HTTP request interceptor**.

| Loại interceptor | Tầng hoạt động |
| --- | --- |
| `ClientInterceptor` của Spring-WS | Trước/sau SOAP message, SOAP Fault, logging/security |
| `HttpRequestInterceptor` của Apache | HTTP request processing, headers/connection behavior |
| `RemoveSoapHeadersInterceptor` | HTTP headers `Content-Length` và `Transfer-Encoding`; không xử lý XML |

**Nguyên tắc:** nếu dùng `HttpComponents5MessageSender()` với cấu hình mặc định hoặc `HttpComponents5ClientFactory.withDefaults()`, Spring-WS có thể áp các customizations cần thiết. Nếu tự cung cấp `HttpClient`, bạn chịu trách nhiệm bảo đảm interceptor/headers tương thích. Đừng tìm cách “fix” bằng cách xóa tất cả HTTP headers hoặc biến XML SOAP Header thành HTTP header.

## 10. TLS/mTLS với Apache HttpClient 5

Một SOAP client production thường bắt buộc HTTPS. TLS/mTLS bao gồm **trust material**, **client identity** và **policy xác minh hostname**, là trách nhiệm của HTTP client/transport:

| Dữ liệu hoặc kiểm tra | Chức năng |
| --- | --- |
| **Truststore / trust anchors** | Quyết định máy chủ/certificate chain nào đáng tin |
| **Hostname verification** | Chứng chỉ server có hợp với hostname của endpoint không? |
| **Keystore + private key client** | Xác thực client khi đối tác yêu cầu mTLS |
| **TLS protocol/cipher policy** | Chỉ cho phép phiên bản/thuật toán TLS phù hợp chính sách |
| **Certificate rotation** | Đổi chứng chỉ/khóa an toàn mà không ngắt tích hợp |

### 10.1. Tạo SSLContext từ truststore và keystore

Ví dụ **ý tưởng cấu hình** với Apache HttpCore 5, giả định `serverTrustStore` và `clientKeyStore` đã được tải bằng `KeyStore` từ vị trí bí mật an toàn:

~~~java
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import org.apache.hc.core5.ssl.SSLContexts;

public SSLContext partnerSslContext(
        KeyStore serverTrustStore,
        KeyStore clientKeyStore,
        char[] clientKeyPassword) throws Exception {

    return SSLContexts.custom()
            .loadTrustMaterial(serverTrustStore, null)
            .loadKeyMaterial(clientKeyStore, clientKeyPassword)
            .build();
}
~~~

Điều kiện an toàn:

- `serverTrustStore` chứa **đúng trust anchors đã phê duyệt**, không phải trust-all.
- `clientKeyStore` chứa certificate/private key hợp lệ cho **đúng đối tác/môi trường**.
- Quản lý passwords/keystore bằng secret management; không hardcode hoặc log chúng.
- Khôi phục và xóa dữ liệu bí mật tạm khi thích hợp; bảo đảm keystore/rotation policy.
- Dùng **hostname verifier bình thường**; không tắt xác minh hostname để “hết lỗi PKIX”.

### 10.2. Gắn SSLContext vào HttpClient 5

Apache HttpClient 5 có sự khác biệt giữa các phiên bản: một số bản cũ dùng `SSLConnectionSocketFactoryBuilder` qua `setSSLSocketFactory(...)`, còn các bản mới hơn có `TlsSocketStrategy` và `ClientTlsStrategyBuilder`. Vì vậy đoạn sau mô tả **cách dùng với các bản HttpClient 5 hỗ trợ `buildClassic()`/`setTlsSocketStrategy(...)`**, không áp dụng nguyên xi cho mọi 5.x:

~~~java
import javax.net.ssl.SSLContext;
import org.apache.hc.client5.http.ssl.ClientTlsStrategyBuilder;
import org.springframework.ws.transport.http.HttpComponents5ClientFactory;

HttpComponents5ClientFactory factory =
        HttpComponents5ClientFactory.withDefaults();

factory.addConnectionManagerBuilderCustomizer(managerBuilder -> {
    managerBuilder.setTlsSocketStrategy(
            ClientTlsStrategyBuilder.create()
                    .setSslContext(partnerSslContext)
                    .buildClassic());
});

// Sau đó dùng new SimpleHttpComponents5MessageSender(factory).
~~~

Biến `partnerSslContext` là `SSLContext` đã tạo và kiểm tra ở phần trước. **Đoạn cấu hình này chỉ dành cho phiên bản có API nêu trên**; với HttpClient 5.2.x, cần dùng chiến lược SSL socket factory phù hợp phiên bản. Không kết hợp một class từ HttpClient 4 với `PoolingHttpClientConnectionManagerBuilder` của HttpClient 5.

**Không dùng `TrustAllStrategy` hoặc `NoopHostnameVerifier` trong production.** Chúng vô hiệu hóa những xác minh mà TLS cần bảo đảm và có thể khiến SOAP request mang token/chữ ký được gửi cho máy chủ giả mạo.

### 10.3. Phân biệt mTLS và WS-Security certificate

SOAP request có thể cần hai cơ chế song song:

- **mTLS:** certificate client được gửi/xác minh khi thiết lập TLS connection.
- **WS-Security/X.509:** chứng chỉ/khóa dùng để ký hoặc mã hóa **SOAP message**, xác minh Header/Body theo policy.

Hai certificate có thể trùng hoặc khác tùy thiết kế, nhưng **mTLS thành công không tự chứng minh SOAP Body đã ký đúng**. Ngược lại, chữ ký SOAP hợp lệ không thay thế HTTPS/hostname verification khi hợp đồng yêu cầu.

## 11. Proxy, HTTP authentication và giới hạn đích

Trong mạng doanh nghiệp, client có thể gửi qua outbound proxy và dùng HTTP authentication. Apache HttpClient 5 có các cấu hình proxy, credentials provider và auth scope; nơi đặt chúng cần được kiểm soát.

### 11.1. Proxy cần thống nhất với DNS và TLS

~~~mermaid
flowchart LR
    A["SOAP client"] --> B["Corporate proxy<br/>CONNECT tunnel / policy"]
    B --> C["TLS tới partner"]
    C --> D["partner.example.org/soap"]
~~~

Khi dùng HTTPS proxy:

- Kết nối tới proxy và kết nối TLS tới server có thể dùng các chứng chỉ/hostname khác nhau.
- Mô hình tunnel `CONNECT` có yêu cầu proxy authentication riêng.
- Thứ tự resolve DNS/proxy, NO_PROXY và truststore có thể ảnh hưởng khả năng kết nối.
- Chứng chỉ mTLS có thể đi tới **server đích thực** qua tunnel hoặc bị kết thúc bởi proxy nếu kiến trúc chọn, cần xác nhận phạm vi tin cậy.

Đừng chuyển hướng SOAP message sang một host bất kỳ khi nhận HTTP 301/302: có thể vô tình gửi Header chứa token hoặc dữ liệu doanh nghiệp sang đích không tin cậy. Trong ví dụ custom factory, `disableRedirectHandling()` giúp chủ động kiểm soát đường đích; với nhu cầu redirect hợp lệ, hãy định nghĩa allowlist và test.

### 11.2. Authentication không tự là SOAP authorization

| Kiểu xác thực | Tầng | Cần chú ý |
| --- | --- | --- |
| HTTP Basic/Digest | HTTP headers/auth challenge | Chỉ truyền qua TLS; scope credentials chặt |
| Proxy authentication | HTTP proxy | Không gửi nhầm credentials proxy cho server |
| mTLS | TLS handshake | Identity certificate và trust chính sách |
| WS-Security UsernameToken/Signature | SOAP Header | Kiểm tra token, timestamp, signature và signed parts |
| Authorization nghiệp vụ | Server domain/application | Caller có quyền với tài nguyên được yêu cầu |

Spring-WS `HttpComponents5MessageSender` có API `setCredentials(...)` và `setAuthScope(...)` liên quan Apache HttpClient 5. **Tên kiểu ở HttpClient 5** thường thuộc `org.apache.hc.client5.http.auth.*`, không phải `org.apache.http.auth.*` của HttpClient 4. Không cấu hình auth scope quá rộng hoặc ép Basic Auth preemptive đến mọi đích nếu chưa có hợp đồng an toàn.

### 11.3. Chống SSRF khi URI được cung cấp động

Một `WebServiceTemplate` cho phép truyền URI mỗi lần gọi, nhưng **không được chấp nhận URI tùy ý do người dùng bên ngoài nhập**. Có thể bị lợi dụng để gửi SOAP/authorization header tới metadata service, mạng nội bộ hoặc domain không thuộc partner.

Biện pháp:

1. Đặt endpoint URL vào allowlist/config trung tâm, không lấy thẳng từ payload người dùng.
2. Không cho redirect sang scheme/host ngoài tập được phép.
3. Giới hạn DNS/IP nội bộ theo policy nếu client có thể gọi nhiều đích.
4. Ràng buộc certificate, credentials và pool theo đúng partner/tenant.
5. Log host/route đã lọc thay vì log password/HTTP Authorization header.

## 12. Retry, idempotency và lỗi “unknown outcome”

Apache HttpClient 5 có thể có cơ chế retry ở tầng transport, nhưng SOAP operation có hai loại:

| Operation | Ví dụ | Retry sau timeout? |
| --- | --- | --- |
| Read-only/idempotent về nghiệp vụ | `GetOrder`, tra cứu số dư có điều kiện | Có thể retry với giới hạn, backoff và rate policy |
| Có tác dụng phụ | `PlaceOrder`, `CancelPayment`, `TransferFunds` | Chỉ theo idempotency/business recovery đã thiết kế |

### 12.1. Tại sao không tự retry mọi POST SOAP?

Giả sử:

~~~text
Client gửi PlaceOrder (requestId=REQ-42).
Server nhận và ghi đơn hàng O-100.
Response bị mất do proxy/connection reset.
Client nhận IOException.
Client tự gửi lại request vì "chưa thấy response".
Server có thể ghi thêm đơn hàng O-101.
~~~

HTTP client không thể kết luận side effect có xảy ra chưa chỉ từ lỗi I/O. Một Fault `Server`/`Receiver` cũng không đủ chứng minh rollback hoàn toàn, nhất là khi service gọi hệ thống khác.

**Thiết kế đúng** cần:

- Business idempotency key có scope theo caller/tenant.
- Unique constraint hoặc cơ chế atomic để chỉ thực thi một ý định nghiệp vụ.
- Kiểm tra cùng key có cùng payload/fingerprint.
- Query status/reconciliation endpoint khi không rõ kết quả.
- Retry có giới hạn, exponential backoff và jitter, tôn trọng rate limits.
- Không bỏ qua WS-Security signature/timestamp/replay policy cho request retry mới.

### 12.2. Tách retry HTTP, retry SOAP Fault và retry nghiệp vụ

| Tầng lỗi | Dữ liệu client biết được | Xử lý gợi ý |
| --- | --- | --- |
| Không mở được kết nối TCP | Có thể request chưa gửi tới server đích | Chính sách retry transport có giới hạn |
| Timeout khi đọc response | Request **có thể đã được xử lý** | Cần idempotency/reconciliation |
| SOAP Fault `Sender/Client` | Request thường cần sửa, theo code/detail | Không retry mù quáng |
| SOAP Fault `Receiver/Server` | Sự cố phía nhận, có thể tạm thời | Kiểm tra idempotency và mã lỗi chi tiết |
| TLS handshake/certificate mismatch | Sai cấu hình trust hoặc danh tính | Sửa certificate/policy, không retry không giới hạn |
| Pool lease timeout | Local saturation/slow upstream | Điều chỉnh concurrency/pool, tránh bão retry |

Trong ví dụ Apache factory, `disableAutomaticRetries()` là lựa chọn an toàn để kiểm soát retry ở application với SOAP POST. Nếu muốn bật lại, phải hiểu retry strategy, idempotency, việc repeat request entity và các lỗi được phép thử lại trong bản HttpClient 5 cụ thể.

## 13. SOAP Fault, HTTP status và response parsing

Sender chuyển dữ liệu HTTP response vào Spring-WS; `WebServiceTemplate` và SOAP message factory quyết định cách xử lý SOAP Body/Fault.

| Đầu ra của HTTP transport | Ý nghĩa |
| --- | --- |
| HTTP 200 với SOAP response hợp lệ | Client có thể unmarshal Body thành JAXB response |
| HTTP 500 với SOAP 1.1 Fault hợp lệ | SOAP 1.1 HTTP binding thường dùng 500 cho Fault; client cần đọc Fault |
| HTTP error với SOAP 1.2 Fault | Cần xem HTTP mapping theo SOAP 1.2 binding; parse đúng `Code`/`Reason` |
| HTTP 502/504 HTML từ proxy | **Không phải SOAP Fault** dù status có 5xx |
| TCP reset / TLS fail không có response | Không có SOAP Envelope để parse |
| HTTP 200 nhưng response XML sai schema | Vấn đề contract/OXM/server, không phải do pool manager |

Trên client Spring-WS, SOAP Fault có thể xuất hiện dưới dạng `SoapFaultClientException`; lỗi HTTP I/O có thể được báo bằng họ exception transport như `WebServiceIOException`. **Không bắt một exception duy nhất rồi kết luận mọi lỗi đều là SOAP Fault.**

### SOAPAction và HTTP headers

Với SOAP 1.1, `SOAPAction` thường đến từ `SoapActionCallback` hoặc `SoapMessage.setSoapAction(...)`; SOAP 1.2 dùng action semantics khác theo media type/binding. Không chèn một SOAP Header block tên `SOAPAction` để thay thế HTTP action, và không ép `Content-Length` thủ công.

### Không tin body chỉ vì có HTTP 200

Client phải kiểm tra schema, SOAP version và typed JAXB response theo contract. Nếu đối tác trả một trang HTML login hoặc proxy error với HTTP 200, unmarshalling có thể thất bại; nguyên nhân cần truy về **transport/auth/proxy**, không sửa XSD vô cớ.

## 14. Bảo mật XML và WS-Security khi dùng HttpClient 5

HTTP sender không tự biến SOAP message thành an toàn. Cần phối hợp:

~~~mermaid
flowchart TD
    A["Java DTO"] --> B["JAXB marshal theo XSD"]
    B --> C["SOAP message factory"]
    C --> D["WS-Security outbound<br/>ký/mã hóa Header/Body"]
    D --> E["Apache HttpClient 5<br/>TLS/mTLS + HTTP"]
    E --> F["SOAP partner"]
    F --> E
    E --> G["WS-Security inbound<br/>xác minh/giải mã"]
    G --> H["XSD validation / JAXB unmarshal"]
~~~

Lưu ý:

1. **XML parsing an toàn:** SOAP message factory, JAXB unmarshaller và custom XML parser phải chặn external entities/DTD không cần thiết, giới hạn kích thước/depth và dùng resolver schema đáng tin cậy.
2. **Signature coverage:** WS-Security phải xác minh đúng SOAP Body/Header đang được client tiêu thụ, không chỉ thấy phần tử `ds:Signature`.
3. **Certificate trust:** certificate mTLS ở HTTP sender và certificate WS-Security của message có thể thuộc hai policy khác nhau.
4. **Outbound order:** bổ sung Header nghiệp vụ trước khi ký nếu Header đó phải được ký; sửa Header/Body sau khi ký có thể làm chữ ký không hợp lệ.
5. **Inbound order:** giải mã/xác minh theo security policy rồi kiểm tra XML nghiệp vụ theo XSD; không unmarshal và tin dữ liệu chưa được bảo vệ đúng yêu cầu.

Không bật `TrustAllStrategy` hoặc bỏ qua WS-Security signature để “vượt lỗi tích hợp”. Thay vào đó kiểm tra từng policy tại đúng tầng và dùng chứng chỉ test được quản lý.

## 15. Spring configuration theo môi trường, không hardcode secrets

Ví dụ file cấu hình application:

~~~yaml
soap:
  partner:
    endpoint: "https://partner.example.org/soap"
    connect-timeout: 3s
    read-timeout: 12s
    pool-max-total: 80
    pool-max-per-route: 20
    retries-enabled: false
~~~

Một record cấu hình Spring Boot 3+ có thể được bind qua `@ConfigurationProperties` (khi đăng ký bằng `@EnableConfigurationProperties` hoặc cấu hình tương đương):

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "soap.partner")
public record PartnerSoapProperties(
        String endpoint,
        Duration connectTimeout,
        Duration readTimeout,
        int poolMaxTotal,
        int poolMaxPerRoute,
        boolean retriesEnabled) {
}
~~~

Sử dụng trong config:

~~~java
@EnableConfigurationProperties(PartnerSoapProperties.class)
@Configuration
public class ManagedPartnerSenderConfig {
    @Bean
    public HttpComponents5MessageSender managedSender(
            PartnerSoapProperties props) {
        HttpComponents5MessageSender sender =
                new HttpComponents5MessageSender();
        sender.setConnectionTimeout(props.connectTimeout());
        sender.setReadTimeout(props.readTimeout());
        sender.setMaxTotalConnections(props.poolMaxTotal());
        sender.setMaxConnectionsPerHost(
                Map.of("https://partner.example.org:443",
                        Integer.toString(props.poolMaxPerRoute())));
        return sender;
    }
}
~~~

**Đây là biến thể minh họa cho bản Spring-WS 4.1**, cần bổ sung imports và bean OXM/message factory khi dùng trong ứng dụng đầy đủ. Đối với sản xuất, nên **chuẩn hóa endpoint thành URI**, lấy host/scheme/port từ `props.endpoint()` và validate URI nằm trong allowlist thay vì lặp literal host như trong ví dụ. `retriesEnabled` là policy flag của ứng dụng, không tự có hiệu lực với `HttpComponents5MessageSender` nếu bạn không sử dụng nó trong factory/retry component.

### Những giá trị nhạy cảm không nằm trong application.yml công khai

- Keystore/truststore passwords, private key password.
- HTTP Basic/Proxy credentials.
- WS-Security UsernameToken password, signing keystore secret.
- Access tokens hoặc thông tin tenant nhạy cảm.

Đưa secrets vào secret manager/environment được kiểm soát; cấu hình rotation, audit và quyền truy cập. Giữ timeout/pool/URI trong cấu hình versioned không đồng nghĩa lưu luôn secrets trong repository.

## 16. Logging, tracing và metrics của HTTP client

Muốn chẩn đoán một request “chậm”, tối thiểu cần tách thời gian:

~~~text
requestId=req-8f21
partner=orders-partner
stage=HTTP_SEND
elapsedMs=814
httpStatus=200
soapOutcome=SUCCESS
poolLeased=17
poolPending=3
~~~

Đây là **log mẫu của ứng dụng**, không phải định dạng mặc định của Apache/Spring-WS. Cần thiết kế cách thu metrics từ client/connection manager thực tế và từ `WebServiceTemplate` hoặc tracing framework.

| Metric | Câu hỏi |
| --- | --- |
| `http.client.requests` theo partner/operation/outcome | Đối tác nào tăng lỗi? |
| Latency p50/p95/p99 | Tốc độ dịch vụ có ổn định không? |
| Pool leased/available/pending | Pool có bị nghẽn không? |
| Connect/TLS errors | Có vấn đề đường truyền/chứng chỉ? |
| Lease timeout | Pending vì connection bị giữ quá lâu? |
| Response/read timeout | Đối tác xử lý chậm hay network bị treo? |
| SOAP Fault code/detail | Lỗi hợp đồng/nghiệp vụ hay server? |
| Retry attempts và idempotency outcomes | Retry có đang làm tăng tải/side effects? |

**Không bật log raw HTTP/SOAP body hoặc `org.apache.hc.*` ở TRACE trên production lâu dài** khi payload có thông tin khách hàng, WS-Security headers hoặc authorization credentials. Nếu cần debug, dùng môi trường cô lập, mẫu dữ liệu giả và bộ lọc che dữ liệu nhạy cảm.

## 17. Kiểm thử ba cấp: OXM, SOAP client và transport thực

### 17.1. Unit/integration test với MockWebServiceServer

`MockWebServiceServer` kiểm thử `WebServiceTemplate` ở phía client: request XML được tạo có QName đúng và response/Fault được xử lý. Ví dụ rút gọn:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

MockWebServiceServer server =
        MockWebServiceServer.createServer(webServiceTemplate);

server.expect(payload(new StringSource(
        "<ord:GetOrderRequest xmlns:ord='urn:example:orders:v1'>" +
        "<ord:orderId>ORD-1024</ord:orderId>" +
        "</ord:GetOrderRequest>")))
    .andRespond(withPayload(new StringSource(
        "<ord:GetOrderResponse xmlns:ord='urn:example:orders:v1'>" +
        "<ord:orderId>ORD-1024</ord:orderId>" +
        "<ord:status>CONFIRMED</ord:status>" +
        "</ord:GetOrderResponse>")));

Object response =
        webServiceTemplate.marshalSendAndReceive(
                newOrderRequest("ORD-1024"));

// Assert response theo JAXB binding thực tế.
server.verify();
~~~

Đoạn test giả định `webServiceTemplate` đã cấu hình OXM và `newOrderRequest` là fixture. **Không kết luận test này chứng minh pool/timeout/TLS**: `MockWebServiceServer` thay phần transport bằng mock sender, không mở HTTPS connection thật.

### 17.2. Test HTTP thực bằng mock SOAP endpoint

Để kiểm tra `HttpComponents5MessageSender`, cần một HTTP(S) server test thực (ví dụ embedded server hoặc wire-level test fixture), phục vụ SOAP response có kiểm soát.

Ma trận:

| Tình huống | Thiết lập test server | Kỳ vọng |
| --- | --- | --- |
| Happy path | SOAP 1.1 đúng XML | HTTP POST + SOAPAction + Body hợp lệ |
| SOAP 1.2 | Envelope/Content-Type 1.2 | Đúng binding, không 415/VersionMismatch |
| Lease timeout | Pool per-route nhỏ, nhiều request chậm | Chờ pool quá hạn và lỗi được phân loại |
| Connect timeout | Đích không reachable trong môi trường test có kiểm soát | Không giữ thread vô hạn |
| Response timeout | Server cố ý trễ response | Timeout theo cấu hình, không retry mù quáng |
| Stale connection | Server/Proxy đóng keep-alive sớm | Pool xử lý/khôi phục đúng policy |
| Proxy route | Qua proxy test | Đúng host, port, CONNECT/auth policy |
| HTTP 502 HTML | Proxy giả lập response non-SOAP | Client phân biệt HTTP/transport error với SOAP Fault |
| HTTP 500 SOAP Fault | SOAP 1.1 Fault hợp lệ | Spring-WS nhận và phân loại Fault |
| Redirect | Server trả 302 đến host khác | Không tự gửi secrets sang host ngoài allowlist |
| HTTP header conflict | SOAP implementation đặt length/transfer headers | Apache xử lý nhờ RemoveSoapHeadersInterceptor |
| Concurrent load | Nhiều SOAP POST cùng route | Pool giới hạn theo total/per-route, không leak |

**Quan trọng:** Một mock HTTP endpoint không thay thế việc kiểm thử với **đối tác thật**, nhưng nó kiểm tra được sender/pool/timeout mà `MockWebServiceServer` không mô phỏng chính xác.

### 17.3. Test TLS/mTLS và chứng chỉ

Để xác minh HTTPS transport:

1. Tạo test CA và certificate có SAN hợp hostname test.
2. Khởi chạy HTTPS test server tin cậy trên keystore riêng.
3. Test **truststore đúng**: handshake thành công.
4. Test **truststore sai/hostname sai**: handshake phải bị từ chối.
5. Nếu dùng mTLS, test thiếu client certificate, certificate hết hạn và certificate không thuộc issuer được chấp nhận.
6. Test certificate rotation và connection pool: connection cũ và mới xử lý thế nào khi server/keys thay đổi?
7. Test riêng WS-Security signature nếu hợp đồng yêu cầu; TLS test không đủ.

Không bật trust-all/hostname-ignore trong test rồi tuyên bố đã xác minh TLS policy.

### 17.4. Phân biệt test client và server

- `MockWebServiceServer`: kiểm thử **SOAP client** dùng `WebServiceTemplate`.
- `MockWebServiceClient`: kiểm thử **Spring-WS server endpoint**.
- HTTP mock/embedded HTTPS: kiểm thử **Apache HttpClient 5 transport**.
- End-to-end partner staging: kiểm thử **WSDL/XSD, proxy, TLS/mTLS, WS-Security và khả năng tương thích thật**.

## 18. Chẩn đoán lỗi HttpComponents5MessageSender

| Triệu chứng | Nghi ngờ chính | Kiểm tra |
| --- | --- | --- |
| `NoClassDefFoundError: org/apache/hc/...` | Thiếu/mismatch Apache HttpClient 5 hoặc HttpCore 5 | Dependency graph, BOM, runtime classpath |
| Không tìm thấy `HttpComponents5MessageSender` | Spring-WS version không có class này | API version (có từ 4.0.5) |
| Không tìm thấy `SimpleHttpComponents5MessageSender` | Đang dùng Spring-WS 4.0.x | Class được giới thiệu trong 4.1 |
| IDE báo constructor custom client deprecated | Spring-WS 4.1+ | Chuyển sang `SimpleHttpComponents5MessageSender` |
| `Content-Length header already present` hoặc lỗi transfer header | Custom client thiếu SOAP HTTP interceptor | `HttpComponents5ClientFactory.withDefaults()` hoặc thêm RemoveSoapHeadersInterceptor |
| Lease timeout / pool pending cao | Hết connection, slow partner, leak | Pool metrics, concurrency, request duration |
| `ConnectTimeoutException` | Đích không reachable, firewall/proxy/DNS | Endpoint URL, network, connect timeout |
| `SocketTimeoutException` | Chờ response/socket I/O quá hạn | Read/response timeout, upstream latency |
| `SSLHandshakeException` | Trust, hostname, cipher/protocol hoặc mTLS | Truststore, SAN, certificate chain, TLS handshake |
| `PKIX path building failed` | Certificate chain không được trust | Đối chiếu CA/truststore, không dùng trust-all |
| HTTP 407 | Proxy yêu cầu authentication | Proxy credentials/scope/tunnel config |
| HTTP 401/403 | HTTP auth/authorization sai | HTTP credentials, scope, server policy |
| HTTP 404/405 khi GET WSDL vẫn thành công | POST SOAP tới sai URL | `defaultUri`, proxy rewrite, WSDL `soap:address` |
| HTTP 415 | SOAP version/Content-Type không khớp | SOAP factory, binding 1.1/1.2 |
| HTTP 502/504, body HTML | Gateway/proxy lỗi | Proxy logs, upstream health, không parse như SOAP Fault |
| SOAP Fault `VersionMismatch` | Envelope namespace sai | Saaj factory/SoapVersion |
| JAXB unmarshal fail | Response Body namespace/schema sai | JAXB/OXM, XSD; không sửa pool trước |
| Retry tạo đơn trùng | HTTP/application retry thiếu idempotency | Retry strategy, business idempotency key |
| Connection leak/high file descriptors | Client/pool bị tạo lặp hoặc không đóng | Bean lifecycle, pool manager ownership |

### Quy trình chẩn đoán theo thứ tự

~~~mermaid
flowchart TD
    A["SOAP call lỗi"] --> B{"Có thể mở HTTPS connection?"}
    B -->|Không| C["Sender, DNS, proxy, TLS/mTLS"]
    B -->|Có| D{"Có lấy được lease từ pool?"}
    D -->|Không| E["Pool max, pending, timeout, leaks"]
    D -->|Có| F{"HTTP POST đến đúng URL?"}
    F -->|Không| G["defaultUri, redirect, proxy route"]
    F -->|Có| H{"SOAP version / Content-Type đúng?"}
    H -->|Không| I["SAAJ factory và WSDL binding"]
    H -->|Có| J{"Body, SOAPAction và WS-Security đúng?"}
    J -->|Không| K["OXM, Header, signature policy"]
    J -->|Có| L{"Response SOAP hay HTTP error?"}
    L -->|SOAP Fault| M["Đọc Fault Code/Detail, business/security"]
    L -->|HTTP error| N["Status, proxy, upstream timeout"]
    L -->|SOAP success| O["Unmarshal JAXB, schema validation"]
~~~

Đây là **luồng chẩn đoán** chứ không phải trình tự nội bộ bất biến của Spring-WS. Nếu HTTP 502 do proxy, sửa generated JAXB class không có tác dụng. Nếu không đọc được SOAP response XML, tăng `maxTotalConnections` chưa chắc giải quyết được. Luôn tìm lỗi ở **tầng đầu tiên không đạt**.

## 19. Bài tập thực hành

### Bài 1 — Cấu hình sender mặc định

Tạo bean `HttpComponents5MessageSender` với connect timeout 3 giây, read timeout 12 giây, max total 80, max per route 20 cho một partner. Gắn vào `WebServiceTemplate` cùng JAXB marshaller. Gửi `GetOrderRequest` và quan sát SOAP Body đúng QName.

### Bài 2 — Thực nghiệm cạn pool

Dùng HTTP test server xử lý chậm 2 giây. Đặt pool per-route 2, phát 10 requests đồng thời và theo dõi `leased`/`pending`. Thêm `connectionRequestTimeout` 1 giây bằng `HttpComponents5ClientFactory`. Giải thích vì sao connect timeout không phải lease timeout.

### Bài 3 — So sánh Spring-WS 4.0.x và 4.1.x

Đọc JavaDoc đúng phiên bản để xác định khi nào constructor `HttpComponents5MessageSender(HttpClient)` bị deprecated và khi nào có `SimpleHttpComponents5MessageSender`. Viết một cấu hình dùng `withDefaults()` của 4.1 và giải thích ý nghĩa `RemoveSoapHeadersInterceptor`.

### Bài 4 — Kết nối TLS/mTLS

Tạo HTTPS test server với certificate có SAN đúng. Cấu hình truststore an toàn và thử thay truststore sai; nếu đối tác yêu cầu mTLS, bổ sung client keystore. Không dùng trust-all và phân biệt mTLS certificate với SOAP signature certificate.

### Bài 5 — Retry và idempotency

Giả lập server đã tạo đơn hàng nhưng response bị ngắt kết nối. Cho client gửi lại `PlaceOrder`. Thiết kế idempotency key và cơ chế query status để không tạo đơn thứ hai, đồng thời không tắt WS-Security timestamp/replay policy.

### Bài 6 — Content-Length/Transfer-Encoding

Tự xây `CloseableHttpClient` không có SOAP remove-header interceptor rồi kiểm tra request gây lỗi với SOAP implementation có đặt sẵn HTTP transfer headers. Bổ sung `HttpComponents5ClientFactory.RemoveSoapHeadersInterceptor` và so kết quả. Giải thích vì sao interceptor này hoạt động ở tầng HTTP chứ không xử lý SOAP XML Header.

### Bài 7 — Kiểm thử các tầng

Dùng `MockWebServiceServer` test payload JAXB và SOAP Fault. Sau đó dùng embedded HTTP(S) server để test timeout/pooling/redirect. Cuối cùng test staging partner với WSDL công bố, TLS/mTLS, WS-Security và certificate trust thật.

### Bài 8 — Nhiều đối tác

Thiết kế hai SOAP clients: Partner A dùng SOAP 1.1, mTLS; Partner B dùng SOAP 1.2, WS-Security và MTOM. Quyết định những thành phần nào tách riêng (marshaller, factory, sender, SSLContext, pool) và các giới hạn tài nguyên để Partner B quá tải không làm Partner A chậm.

## 20. Checklist production

| Nhóm | Điều kiện cần đạt |
| --- | --- |
| **Phiên bản** | Spring-WS hỗ trợ HttpComponents5MessageSender; Apache HttpClient 5/Core 5 cùng thế hệ |
| **API** | 4.1+ dùng Simple sender khi cung cấp custom HttpClient; không dựa vào constructor deprecated |
| **Contract** | SOAP version, WSDL port, QName, SOAPAction và endpoint URL đúng |
| **Pool** | Max total/per-route, lease timeout, TTL/idle eviction, metrics leased/available/pending |
| **Timeout** | Connect, response/read, pool lease và overall deadline hữu hạn, hợp SLA |
| **HTTP headers** | Có RemoveSoapHeadersInterceptor tương ứng khi tự dựng Apache client |
| **Retry** | Không tự retry SOAP POST có side effects; idempotency/reconciliation hợp đồng |
| **TLS/mTLS** | Truststore, keystore, hostname verification, certificate rotation và policy phù hợp |
| **Proxy/auth** | Đích và proxy allowlist; auth scope chặt; không lộ credentials qua redirect |
| **SOAP security** | WS-Security signature/encryption/timestamp/replay policy riêng với TLS |
| **XML** | XML parser/OXM an toàn, XSD validation và giới hạn payload/attachments |
| **Resource lifecycle** | Client/pool dùng lại, đóng một lần khi shutdown, không tạo mỗi request |
| **Observability** | Latency p95/p99, connection metrics, SOAP Fault code, correlation ID, log đã lọc |
| **Testing** | MockWebServiceServer cho SOAP payload; HTTP(S) integration cho sender/pool; partner interop |

## 21. Tài liệu chuẩn để đối chiếu API

Tên setter, constructor và vị trí classes có thể thay đổi theo version. Khi áp dụng vào dự án, đối chiếu trực tiếp:

- [Spring-WS 4.1 — HttpComponents5MessageSender](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/transport/http/HttpComponents5MessageSender.html): constructor, `Duration` timeout, pool settings, các API deprecated.
- [Spring-WS 4.1 — SimpleHttpComponents5MessageSender](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/transport/http/SimpleHttpComponents5MessageSender.html): nhận Apache `HttpClient` hoặc `HttpComponents5ClientFactory`.
- [Spring-WS 4.1 — HttpComponents5ClientFactory](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/transport/http/HttpComponents5ClientFactory.html): `withDefaults()`, builder customizers, timeout/pool và SOAP HTTP header interceptor.
- [Spring-WS 4.0 — HttpComponents5MessageSender](https://docs.spring.io/spring-ws/docs/4.0.12/api/org/springframework/ws/transport/http/HttpComponents5MessageSender.html): so sánh API khi dự án chưa nâng lên 4.1.
- [Apache HttpClient 5 — migration to classic APIs](https://hc.apache.org/httpcomponents-client-5.6.x/migration-guide/migration-to-classic.html): HTTP connection manager, pool, TLS, timeout và request config.

**Kết luận:** `HttpComponents5MessageSender` đưa **Apache HttpClient 5** vào chuỗi gửi SOAP của **SPRING_WEB_SERVICES**, giải quyết HTTP connection pooling, timeout, TLS/mTLS, proxy và cấu hình transport. Với **Spring-WS 4.1+**, dùng sender mặc định và setter cho nhu cầu phổ biến; khi cần custom Apache `HttpClient`, ưu tiên **`SimpleHttpComponents5MessageSender` kết hợp `HttpComponents5ClientFactory.withDefaults()`** hoặc một client tự cấu hình và có interceptor HTTP phù hợp. Dù transport được tối ưu, SOAP client vẫn phải tuân WSDL/XSD, JAXB/OXM, SOAP Fault và WS-Security policy. Khả năng tích hợp bền vững đến từ việc **đặt đúng cấu hình ở đúng tầng, giới hạn tài nguyên và kiểm thử cả SOAP lẫn kết nối HTTP(S) thực tế**.
