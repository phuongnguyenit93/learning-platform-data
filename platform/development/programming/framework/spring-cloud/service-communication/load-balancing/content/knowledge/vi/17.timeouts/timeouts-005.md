# Timeout của từng HTTP transport và sự khác biệt về ý nghĩa

Trong hệ thống microservices dùng **Spring Cloud LoadBalancer**, một request từ **order-service** tới **inventory-service** có thể phải chờ **khám phá bản sao**, lấy connection từ pool, phân giải DNS, thiết lập TCP, thương lượng TLS, gửi request, đợi backend xử lý và đọc body. Mỗi giai đoạn có thể có **timeout khác nhau**. Một cấu hình tên **readTimeout** ở RestTemplate không nhất thiết tương đương **responseTimeout** của Reactor Netty hoặc **readTimeout** của OpenFeign.

Hiểu sai timeout dẫn tới nhiều sự cố: worker thread bị giữ quá lâu, request reactive bị hủy trước khi kịp lấy connection, retry kéo dài vượt SLA, hoặc client báo timeout dù server đã hoàn tất một giao dịch ghi. Bài này so sánh timeout **theo HTTP transport thực thi**, không chỉ theo API bề mặt **RestTemplate, RestClient, WebClient, OpenFeign**.

**Mục tiêu học tập:**

1. Phân biệt pool acquire, DNS, TCP connect, TLS handshake, read/response timeout và **end-to-end deadline**.
2. Biết timeout nào phải cấu hình trên **HTTP engine thực tế** (JDK HttpURLConnection, JDK HttpClient, Apache HttpClient 5, Reactor Netty, Feign).
3. Cấu hình và kiểm chứng RestTemplate/RestClient, WebClient, OpenFeign khi gọi qua Spring Cloud LoadBalancer.
4. Hiểu quan hệ giữa timeout, retry, service discovery, health check và ngữ nghĩa lỗi.
5. Thiết kế ngân sách thời gian, kiểm thử chậm mạng/pool bão hòa và theo dõi nguyên nhân timeout.

**Lưu ý phiên bản:** Spring Framework 6.x/7.x, Spring Cloud và các HTTP engine không luôn có cùng overload hoặc mặc định. Những đoạn code dùng API theo dòng phiên bản được nêu; trước khi áp dụng phải đối chiếu BOM đang chạy. Các con số trong bài là **ví dụ thiết kế**, không phải giá trị tối ưu cho mọi môi trường.

## 1. Tên gọi “timeout” che giấu nhiều đồng hồ khác nhau

Hình dung một lời gọi có các bước:

~~~mermaid
flowchart LR
    A["Caller: tạo request"] --> B["Discovery + LoadBalancer"]
    B --> C["Pool: acquire connection"]
    C --> D["DNS"]
    D --> E["TCP connect"]
    E --> F["TLS handshake (HTTPS)"]
    F --> G["Gửi headers/body"]
    G --> H["Đợi response headers"]
    H --> I["Đọc response body"]
    I --> J["Decode + trả DTO"]
~~~

Một thực thi cụ thể có thể **không đi qua mọi bước**: HTTP keep-alive dùng lại connection đang mở, không cần TCP connect hoặc TLS handshake mới; ServiceInstance từ cache không cần gọi registry mỗi lần; HTTP/2 có thể truyền nhiều stream trên cùng một connection. Vì vậy, mỗi lần chọn instance không nhất thiết đi kèm một lần thiết lập kết nối.

| Loại timeout | Đo khoảng nào? | Tác dụng khi vượt | Không tự bảo vệ khỏi |
| --- | --- | --- | --- |
| **Pool acquire / connection request** | Chờ lấy connection từ pool | Ngừng đợi khi pool bão hòa | Backend trả response chậm sau khi đã có connection |
| **DNS query / resolve** | Chờ phân giải hostname thành địa chỉ | Ngừng truy vấn DNS quá lâu | TCP connect/response |
| **Connect** | Thiết lập kết nối mới, phạm vi tùy engine | Chặn TCP connect bị treo | Pool wait và response chậm; có thể không bao gồm TLS |
| **TLS handshake** | Thương lượng TLS sau TCP connect | Giới hạn HTTPS handshake | HTTP body/read chậm |
| **Write** | Chờ gửi bytes hoặc một khoảng không có tiến triển ghi | Giới hạn upload chậm | Server xử lý chậm sau khi nhận request |
| **Response/read/socket** | Chờ response hoặc một khoảng không có dữ liệu inbound, tùy engine | Ngắt luồng khi backend im lặng | Thường không phải giới hạn **tổng** thời gian HTTP call |
| **Request/overall deadline** | Toàn bộ lời gọi hoặc một attempt, tùy API | Ngừng tác vụ còn lại khi hết ngân sách | Không tự đảo ngược side effect trên server |
| **Retry backoff** | Khoảng nghỉ giữa attempts | Điều tiết retry | Không phải timeout HTTP, nhưng cộng vào latency |

Tên thuộc tính **không phải hợp đồng đủ chính xác**. Cần hỏi: đồng hồ bắt đầu lúc nào, dừng lúc nào, tính theo **khoảng chờ giữa hai lần đọc** hay **thời gian từ đầu đến cuối**, có reset khi nhận chunk không, và có bao gồm retry không?

## 2. Timeout nào gắn với từng phase?

### 2.1. Chờ lấy connection trong pool

Khi nhiều lời gọi đồng thời hơn số connection cho phép, request có thể nằm trong hàng đợi. **Pool acquire timeout** giới hạn thời gian chờ **trước khi** request có socket để sử dụng.

Ví dụ pool có 20 connections, cả 20 đang được dùng bởi request chậm; request thứ 21 phải chờ. Dù connect timeout chỉ 200 ms, nó vẫn có thể nằm trong hàng đợi 2 giây nếu pool acquire timeout cho phép. Connect timeout chỉ có tác dụng khi thực sự cần **kết nối mới**.

Với Apache HttpClient 5, khái niệm này là **connection request timeout**; với Reactor Netty, thường là **pendingAcquireTimeout**.

### 2.2. Phân giải DNS

HTTP client có thể phải phân giải một hostname như inventory-a.internal. Kết quả DNS có thể được cache bởi resolver, JVM, operating system hoặc HTTP engine. DNS query timeout thường **độc lập** với TCP connect timeout.

Đối với URI logic **http://inventory-service/...** có **@LoadBalanced**, host inventory-service là **service ID**. Sau khi LoadBalancer chọn ServiceInstance, transport kết nối bằng host/port vật lý của instance. Nếu instance có hostname inventory-a.internal, DNS có thể chạy cho hostname **đích thật**, không phải cho service ID logic. Nếu instance có IP, có thể không cần DNS cho đích đó.

### 2.3. TCP connect

Connect timeout thường giới hạn việc mở một TCP connection mới. Nó hữu ích khi SYN không được trả lời do mạng bị drop. Nhưng nếu đích chủ động trả connection refused, lỗi có thể xảy ra **ngay lập tức**, không cần đợi hết connect timeout.

Khi keep-alive tái sử dụng một connection, **không có TCP connect mới**, nên connect timeout không phải giới hạn cho request trên connection đó.

### 2.4. TLS handshake

Sau TCP connect, HTTPS cần handshake TLS (đôi khi có proxy tunnel trước đó). Một số transport có handshake timeout riêng; một số connect timeout có thể bao phủ handshake hoặc không. Không suy đoán chỉ từ tên connectTimeout.

TLS handshake còn phụ thuộc certificate validation, SNI, proxy, TLS version và network delay. Nếu handshake lỗi vì certificate sai, tăng timeout **không sửa** vấn đề trust/hostname.

### 2.5. Response/read timeout

Server có thể kết nối ngay nhưng mất 10 giây để chạy query. Connect timeout **không bảo vệ** khỏi tình huống này. Response/read timeout mới liên quan đến thời gian chờ phản hồi.

- **Socket read timeout** của một số blocking transport thường giới hạn **thời gian chờ của một lần đọc**. Nếu server cứ gửi vài bytes trước khi hết timeout, tổng request có thể rất lâu.
- **Response timeout** của Apache HttpClient 5 áp dụng trong request exchange; tài liệu Apache cảnh báo **không phải total deadline**, có thể bị vượt khi HTTP client tự thực thi lại request.
- **Reactor Netty responseTimeout** bảo vệ tầng HTTP response, không phải giới hạn chắc chắn cho mọi giai đoạn trước đó hoặc tổng nhiều retries.
- **JDK HttpClient HttpRequest.Builder.timeout** là timeout của *request*, khác với socket read timeout thuần túy; phạm vi bao phủ response body có chi tiết theo phiên bản JDK.

### 2.6. End-to-end deadline

Endpoint của Order Service có SLA 2 giây không thể chỉ đặt readTimeout=2s rồi coi là đã đáp ứng SLA. Tổng elapsed time còn gồm:

~~~text
T_call = T_lookup/LB + T_pool + T_DNS + T_connect
       + T_TLS + T_upload + T_response + T_decode
       + T_retry_backoffs + T_additional_attempts
~~~

Đây là **mô hình cộng giai đoạn**, không phải công thức chính xác cho mọi engine vì một số bước chồng lấp hoặc bị bỏ qua. Nhưng nó nhắc rằng cần một **deadline độc lập** cho lời gọi logic nếu phải giới hạn latency từ đầu đến cuối.

## 3. Spring Cloud LoadBalancer không phải HTTP transport

LoadBalancer nhận service ID, lấy danh sách instance (discovery, cache, health, filters) rồi chọn một bản sao. HTTP transport bắt đầu vai trò của mình khi gọi URI vật lý sau lựa chọn.

~~~text
Order -> GET http://inventory-service/api/stock/BOOK-01
          |
          | Spring Cloud LoadBalancer chọn ServiceInstance
          v
        http://10.10.1.22:8080/api/stock/BOOK-01
          |
          | ClientHttpRequestFactory / ClientHttpConnector / Feign client
          v
        TCP, TLS, request, response
~~~

| Trường hợp | Có kết nối đến Inventory? | Timeout HTTP transport xử lý? |
| --- | --- | --- |
| Không có ServiceInstance | Không | Không giải quyết được bằng tăng connect/read timeout |
| DiscoveryClient chậm | Có thể chưa | Deadline toàn lời gọi có thể áp dụng, transport timeout không bao phủ chắc chắn |
| Chờ connection pool | Chưa lease được connection | Pool acquire timeout |
| TCP SYN bị drop | Đang cố kết nối | Connect timeout |
| TLS handshake bị treo | TCP đã kết nối | TLS/handshake timeout hoặc deadline |
| Backend xử lý chậm | Đã kết nối, chờ response | Response/read timeout |
| Backend trả HTTP 503 ngay | Có HTTP response | Không phải timeout |
| Backend đã xử lý xong nhưng client timeout | Có thể đã có side effect | Timeout không thể rollback backend |

Trong Spring Cloud LoadBalancer, **ServiceInstanceListSupplier** có thể dùng cache và health check bất đồng bộ. Tăng timeout của RestClient hoặc WebClient **không làm registry cập nhật nhanh hơn**, cũng không tự loại instance đang chết khỏi danh sách.

## 4. API HTTP cao cấp khác với transport thực thi

| API Spring/Cloud | Kiểu I/O | HTTP engine có thể dùng | Nơi cấu hình timeout |
| --- | --- | --- | --- |
| RestTemplate | Blocking | HttpURLConnection, Apache HC5, JDK HttpClient qua factory | ClientHttpRequestFactory + engine |
| RestClient | Blocking | JDK HttpClient, Apache HC5, Jetty hoặc Reactor Netty qua factory | ClientHttpRequestFactory + engine |
| WebClient | Reactive | Reactor Netty, Jetty reactive hoặc JDK HttpClient connector | ClientHttpConnector, engine, Reactor operator |
| Spring Cloud OpenFeign | Thường blocking | Feign default client, HC5, OkHttp hoặc JDK theo cấu hình | Feign Request.Options và underlying HTTP client |

Hai ứng dụng cùng viết RestClient.get().retrieve() có thể dùng transport khác nhau nếu classpath hoặc bean request factory khác. Spring Framework còn chọn request factory mặc định theo thư viện hiện diện. Vì vậy **không dùng một khối YAML timeout chung rồi giả định mọi HTTP client đều chịu tác dụng**.

Quy tắc vận hành: **xác minh loại HTTP engine và bean được inject, sau đó mới cấu hình timeout**. Cùng một giá trị 2 giây có thể đo hai khoảng khác nhau trên hai transport.

## 5. RestTemplate/RestClient với SimpleClientHttpRequestFactory

**SimpleClientHttpRequestFactory** sử dụng JDK HttpURLConnection. Nó minh họa hai timeout:

- **setConnectTimeout**: timeout khi mở connection của URLConnection.
- **setReadTimeout**: timeout khi đợi đọc dữ liệu từ URLConnection.

Ví dụ cho RestTemplate (Spring Framework 6.1+ có overload Duration):

~~~java
import java.time.Duration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Bean
@LoadBalanced
RestTemplate inventoryRestTemplate() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(500));
    factory.setReadTimeout(Duration.ofSeconds(2));
    return new RestTemplate(factory);
}
~~~

Ví dụ tương tự với RestClient:

~~~java
@Bean
@LoadBalanced
RestClient.Builder inventoryRestClientBuilder() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(500));
    factory.setReadTimeout(Duration.ofSeconds(2));
    return RestClient.builder().requestFactory(factory);
}
~~~

Sau khi Spring Cloud LoadBalancer cấu hình builder, ứng dụng có thể dùng URI logic:

~~~java
StockResponse stock = restClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

**Bẫy:** với HttpURLConnection, read timeout là giới hạn cho việc chờ dữ liệu ở các thao tác đọc, **không đương nhiên là thời gian tối đa từ khi gửi GET đến lúc deserialize xong toàn bộ JSON**. Server gửi từng ít dữ liệu có thể kéo dài lời gọi hơn 2 giây.

Javadoc SimpleClientHttpRequestFactory quy định giá trị **0 là không timeout** cho hai setter này và mặc định lấy từ hệ thống; đừng đặt 0 để biểu đạt “thật nhanh” hoặc giả định timeout mặc định đã an toàn.

SimpleClientHttpRequestFactory không có cùng bộ cấu hình pool acquisition và reuse như Apache HC5 hoặc Reactor Netty. Nếu cần throughput lớn và kiểm soát nhiều giai đoạn, nên chọn transport phù hợp hơn thay vì cố nhét mọi timeout vào hai setter.

## 6. RestClient/RestTemplate với JDK HttpClient (Java 11+)

Không nhầm **SimpleClientHttpRequestFactory** (HttpURLConnection) với **JdkClientHttpRequestFactory** (java.net.http.HttpClient). Đây là hai cơ chế HTTP khác nhau của JDK.

JDK HttpClient có:

- **HttpClient.Builder.connectTimeout(Duration)**: giới hạn việc tạo **connection mới**; khi tái sử dụng connection không có tác dụng cho request đó.
- **HttpRequest.Builder.timeout(Duration)**: timeout **của một request**. Javadoc JDK mô tả HttpTimeoutException khi response không tới trong giới hạn; phạm vi bao phủ body có chi tiết theo phiên bản JDK/implementation.
- **JdkClientHttpRequestFactory.setReadTimeout(Duration)**: Spring ánh xạ giá trị này sang **HttpRequest.Builder.timeout**, không phải socket idle read timeout giống HttpURLConnection.

Ví dụ:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

HttpClient jdkClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(500))
        .build();

JdkClientHttpRequestFactory factory =
        new JdkClientHttpRequestFactory(jdkClient);
factory.setReadTimeout(Duration.ofSeconds(2));

RestClient restClient = RestClient.builder()
        .requestFactory(factory)
        .build();
~~~

Đây là RestClient **trực tiếp**. Nếu muốn dùng service ID với Spring Cloud LoadBalancer, phải đưa factory vào builder/bean **@LoadBalanced** hoặc tích hợp LoadBalancer phù hợp; chỉ dùng requestFactory không tự gắn LoadBalancer.

### 6.1. Vì sao không gọi mọi readTimeout là “chờ giữa hai bytes”?

Ở JdkClientHttpRequestFactory, API tên setReadTimeout nhưng thực hiện qua timeout của **HTTP request** do JDK tạo. Không thể suy diễn nó cùng điểm bắt đầu/kết thúc với HttpURLConnection.setReadTimeout.

Khi chạy Java 17, 21 hoặc JDK mới, kiểm tra Javadoc tương ứng của HttpRequest.Builder.timeout và integration test với **response headers nhanh nhưng body gửi chậm**. Không sao chép bảng timeout của transport này cho transport khác chỉ vì tên setter giống nhau.

## 7. Apache HttpClient 5: tách pool, connect, socket và response

Với hệ thống RestClient/RestTemplate blocking có lưu lượng lớn, **Apache HttpClient 5 (HC5)** cung cấp connection pool và những timeout khác nhau:

| Cấu hình HC5 | Ý nghĩa | Tầng |
| --- | --- | --- |
| RequestConfig.connectionRequestTimeout | Chờ lease connection từ pool | Connection manager |
| ConnectionConfig.connectTimeout | Chờ tạo connection, chi tiết TLS phụ thuộc transport | Connection configuration |
| ConnectionConfig.socketTimeout | Chờ hoạt động I/O trên socket | Connection/I/O |
| RequestConfig.responseTimeout | Chờ response trong quá trình request exchange | Request execution |
| TlsConfig.handshakeTimeout | Chờ TLS handshake | TLS |
| ConnectionConfig.timeToLive/idleTimeout | Tuổi thọ/nhàn rỗi tối đa của connection để quản lý reuse | Pool lifecycle, **không phải deadline HTTP request** |

### 7.1. Ví dụ Apache HC5 có pool

Đây là cấu hình minh họa cho **Apache HttpClient 5.2+** với Spring Framework dùng HttpComponentsClientHttpRequestFactory:

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

ConnectionConfig connection = ConnectionConfig.custom()
        .setConnectTimeout(Timeout.ofMilliseconds(500))
        .setSocketTimeout(Timeout.ofSeconds(2))
        .build();

PoolingHttpClientConnectionManager manager =
        PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(100)
                .setMaxConnPerRoute(30)
                .setDefaultConnectionConfig(connection)
                .build();

RequestConfig request = RequestConfig.custom()
        .setConnectionRequestTimeout(Timeout.ofMilliseconds(300))
        .setResponseTimeout(Timeout.ofSeconds(2))
        .build();

CloseableHttpClient apache = HttpClients.custom()
        .setConnectionManager(manager)
        .setDefaultRequestConfig(request)
        .build();

HttpComponentsClientHttpRequestFactory factory =
        new HttpComponentsClientHttpRequestFactory(apache);

RestClient restClient = RestClient.builder()
        .requestFactory(factory)
        .build();
~~~

**Phạm vi ví dụ:** cấu hình bean/lifecycle, exception mapping và Spring Cloud LoadBalancer được lược bỏ để tập trung vào timeout. Trong ứng dụng thật, dùng một bean HTTP client dùng chung, cho Spring quản lý việc đóng pool, và gắn factory vào **@LoadBalanced RestClient.Builder/RestTemplate** nếu gọi theo service ID.

Một điểm phiên bản quan trọng: một số dòng Spring Framework 6.x có **HttpComponentsClientHttpRequestFactory.setConnectTimeout(...)**; Javadoc Spring Framework **7.0.10** không còn setter connect timeout trên factory này. Hãy cấu hình connect qua **ConnectionConfig của Apache HC5** như ví dụ để tránh viết code giả định phương thức tồn tại ở mọi phiên bản.

### 7.2. Response timeout không phải deadline toàn request

Apache HC5 mô tả RequestConfig.responseTimeout là khoảng chờ response và cảnh báo **không phải absolute deadline**; nó có thể bị vượt khi HTTP client tự thực thi lại request. Ngoài ra, thời gian chờ acquire và thiết lập connection phải đo riêng.

~~~text
pool acquire = 300ms
connect      = 500ms
response     = 2s
~~~

Không được kết luận “mọi request chắc chắn kết thúc trong 2 giây”. Request có thể chờ pool rồi mới kết nối, sau đó lại chờ response; timeout mỗi phase bảo vệ **phase đó**, không đồng thời xác lập deadline tổng.

### 7.3. Khi pool đang bão hòa

Nếu pool chỉ cho phép 30 connections đến inventory-service nhưng có 60 request đồng thời, một nửa có thể phải chờ. Khi request đang chờ pool, connect/read timeout thường **chưa phải đồng hồ chính**; connectionRequestTimeout mới là giới hạn cần quan sát.

Tăng connectTimeout không giải quyết queue pool cạn; tăng maxConnPerRoute có thể giúp một số trường hợp nhưng cũng có nguy cơ làm backend quá tải. Cần đánh giá concurrency, latency, keep-alive và giới hạn server trước khi thay pool size.

## 8. WebClient với Reactor Netty: các lớp timeout cần phân biệt

**WebClient** là API reactive của Spring Framework; **Reactor Netty** là một transport phổ biến đằng sau WebClient. Cấu hình timeout nên đặt trên **HttpClient**, **ConnectionProvider** và, khi cần, operator **Mono/Flux**.

Các nhóm được Reactor Netty tài liệu hóa:

| Nhóm | API tiêu biểu | Bảo vệ |
| --- | --- | --- |
| Pool acquire | ConnectionProvider.pendingAcquireTimeout | Chờ pool cấp một connection |
| TCP connect | ChannelOption.CONNECT_TIMEOUT_MILLIS | Tạo connection mới |
| HTTP response | HttpClient.responseTimeout | Chờ tiến triển đọc response ở tầng HTTP |
| TLS | SSL provider handshakeTimeout | Handshake HTTPS |
| DNS | Resolver queryTimeout | Thời gian chờ từng DNS query |
| Proxy | ProxyProvider.connectTimeoutMillis | Thời gian thiết lập kết nối qua proxy |
| Tổng publisher | Mono.timeout / Flux.timeout | Thời gian chờ theo tín hiệu reactive, tùy operator |

### 8.1. Cấu hình Reactor Netty và @LoadBalanced WebClient.Builder

Ví dụ dành cho Spring Cloud LoadBalancer:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Bean
ConnectionProvider inventoryConnectionPool() {
    return ConnectionProvider.builder("inventory-http")
            .maxConnections(80)
            .maxIdleTime(Duration.ofSeconds(25))
            .pendingAcquireTimeout(Duration.ofMillis(300))
            .build();
}

@Bean
@LoadBalanced
WebClient.Builder inventoryWebClientBuilder(ConnectionProvider pool) {
    HttpClient netty = HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
            .resolver(spec ->
                    spec.queryTimeout(Duration.ofSeconds(1)))
            .responseTimeout(Duration.ofSeconds(2));

    return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(netty));
}
~~~

Giả định có **spring-cloud-starter-loadbalancer** và một discovery source. Client có thể gọi:

~~~java
Mono<StockResponse> stock = builder.build()
        .get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);
~~~

**Chú ý vòng đời:** ConnectionProvider và các tài nguyên event loop nên được dùng chung, quản lý khi ApplicationContext đóng; không tạo một pool/HttpClient mới trên mỗi request. Nếu tự tạo pool tách khỏi tài nguyên mặc định, cần thiết kế lifecycle/dispose phù hợp. Với Spring Boot, đừng đánh mất các WebClientCustomizer, tracing, authentication hoặc cấu hình connector có sẵn chỉ vì tạo một builder mới.

### 8.2. pendingAcquireTimeout không phải connectTimeout

Ví dụ:

~~~text
12:00:00.000  subscribe
12:00:00.005  chờ connection pool, tất cả channel đang bận
12:00:00.305  pendingAcquireTimeout=300ms -> lỗi acquire
               chưa hề thử TCP connect mới
~~~

Tăng CONNECT_TIMEOUT_MILLIS từ 500 lên 2000 **không làm giảm lỗi này**. Cần kiểm tra active/idle/pending connections, giới hạn concurrency, tốc độ response và có leak connection hay không.

Tài liệu Reactor Netty 1.3.x nêu **pendingAcquireTimeout mặc định 45 giây**, nhưng không nên dựa vào mặc định này để đáp ứng SLO ngắn. Dù pool còn khả năng tạo connection mới, connect timeout có thể áp dụng trong nhánh thiết lập TCP sau khi acquire; mỗi đồng hồ đo một giai đoạn khác nhau.

### 8.3. CONNECT_TIMEOUT_MILLIS chỉ nói tới connection mới

~~~java
HttpClient netty = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500);
~~~

Giá trị tính theo **milliseconds**. Trong Reactor Netty 1.3.x, tài liệu nêu mặc định connect timeout 30 giây; giá trị có thể phụ thuộc transport và phiên bản, vì vậy nên đặt rõ theo latency budget.

Khi tái sử dụng socket keep-alive, không có một lần TCP connect mới để bị ràng buộc bởi thuộc tính này. Nếu endpoint vẫn phản hồi chậm trên connection hiện có, phải dựa vào response timeout và deadline phù hợp.

### 8.4. responseTimeout và timeout riêng cho request

~~~java
HttpClient netty = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(2));
~~~

Đây là cấu hình mặc định cho các request trên HttpClient đó. Đối với endpoint cần nhiều thời gian hơn, Spring WebClient có thể tùy chỉnh per-request khi native transport là Reactor Netty:

~~~java
Mono<String> result = webClient.get()
        .uri("http://inventory-service/reports/{id}", reportId)
        .httpRequest(httpRequest -> {
            reactor.netty.http.client.HttpClientRequest nativeRequest =
                    httpRequest.getNativeRequest();
            nativeRequest.responseTimeout(Duration.ofSeconds(5));
        })
        .retrieve()
        .bodyToMono(String.class);
~~~

**Đây là API phụ thuộc Reactor Netty**, không portable sang JdkClientHttpConnector hoặc JettyClientHttpConnector. Nếu đổi connector, phần tùy chỉnh native request phải được kiểm tra hoặc thay thế.

Đừng hiểu responseTimeout=2s là **mọi request kết thúc sau tối đa 2 giây**. Pool wait, DNS, TCP/TLS, request upload, decode và retry có thể cộng thêm thời gian; response có thể streaming và từng giai đoạn có cách đo khác.

### 8.5. Đọc/ghi dữ liệu so với response timeout

Spring Framework cũng cho phép gắn Netty **ReadTimeoutHandler** và **WriteTimeoutHandler**:

~~~java
HttpClient netty = HttpClient.create()
        .doOnConnected(connection -> connection
                .addHandlerLast(new ReadTimeoutHandler(10))
                .addHandlerLast(new WriteTimeoutHandler(10)));
~~~

Đây là Netty I/O handlers, có ngữ nghĩa **không có tiến triển đọc/ghi** và giá trị constructor trên là **giây**. Chúng khác với HttpClient.responseTimeout ở phạm vi/lifecycle. Chỉ thêm handler khi thực sự cần bảo vệ ở mức connection; nếu gắn không đúng có thể ảnh hưởng request streaming dài, connection dùng lại hoặc TLS.

Với WebClient thông thường, **responseTimeout** thường là điểm bắt đầu phù hợp hơn so với tùy ý gắn handler read/write rồi giả định hai cơ chế tương đương.

### 8.6. TLS handshake, DNS và proxy cần giới hạn riêng khi cần

Reactor Netty có cấu hình handshake timeout khi dùng HTTPS:

~~~java
HttpClient httpsClient = HttpClient.create()
        .secure(spec ->
                spec.handshakeTimeout(Duration.ofSeconds(4)));
~~~

Đoạn này bật TLS cho client HTTPS trong ví dụ; không gắn nguyên cấu hình HTTPS vào một connector chuyên gọi **HTTP thuần** rồi mặc định rằng mọi scheme vẫn đúng. Với SSL setup phức tạp, cấu hình SslContextSpec/truststore và hostname verification theo chính sách bảo mật.

Tài liệu Reactor Netty nêu SSL handshake timeout mặc định 10 giây, DNS query timeout mặc định 5 giây cho dòng 1.3.x. **Đây là mặc định ở cấp engine**, không phải SLO của ứng dụng. Một DNS resolver có thể thử nhiều nameserver/record hoặc cache, nên không kết luận tổng thời gian phân giải đúng bằng giá trị của **một DNS query timeout**.

Nếu đi qua HTTP proxy, proxy connect timeout cũng có thể là một đồng hồ riêng. Đừng nhầm độ trễ kết nối tới proxy với thời gian backend xử lý request.

## 9. WebClient + Reactor timeout: hai cách giới hạn khác nhau

Reactor cung cấp operator **timeout(Duration)** cho Mono/Flux:

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .timeout(Duration.ofMillis(900));
~~~

Với **bodyToMono**, timeout này giới hạn thời gian chờ tín hiệu giá trị/hoàn thành kể từ subscription; trong pipeline cold thông thường nó có thể bao gồm **chọn ServiceInstance, acquire pool, connect, gửi request và decode body**, nên thường gần hơn với deadline cho một lần subscribe. Nó không tự bao gồm **các lần retry đặt ở bên ngoài operator**.

Thứ tự operator là một khác biệt quan trọng:

~~~java
// Timeout 900ms cho mỗi lần subscribe vào attempt;
// retry phía ngoài có thể làm tổng kéo dài hơn 900ms.
Mono<StockResponse> perAttempt = source
        .timeout(Duration.ofMillis(900))
        .retryWhen(Retry.max(1));

// Timeout 1500ms bao quanh cả retries và backoff phía trong.
Mono<StockResponse> wholeOperation = source
        .retryWhen(Retry.fixedDelay(1, Duration.ofMillis(100)))
        .timeout(Duration.ofMillis(1500));
~~~

Trong ví dụ, **source** là Mono cold có khả năng thực hiện lại HTTP request khi re-subscribe; không phải Publisher hot đã hoàn thành trước đó. Retry.max(1) nghĩa là tối đa **một retry ngoài lần đầu**, không phải tổng một lần gọi.

**Flux.timeout(Duration)** lại là timeout theo **khoảng chờ tín hiệu onNext tiếp theo**, không mặc nhiên là tổng thời gian tuyệt đối của một stream. Với SSE/NDJSON, dòng dữ liệu liên tục có thể chạy nhiều giờ mà vẫn không timeout nếu mỗi event đến đúng hạn. Nếu muốn giới hạn vòng đời của stream, cần một deadline/hủy subscription độc lập.

### 9.1. Timeout ở tầng Reactor không thay thế timeout transport

Nếu chỉ đặt Mono.timeout(2s) mà pool acquire vẫn có mặc định 45s, operator có thể hủy subscription sau 2s, nhưng việc hủy tài nguyên vật lý phụ thuộc connector và giai đoạn request. Các timeout vận hành cụ thể ở transport vẫn cần cấu hình để:

- Phát hiện nguyên nhân rõ ràng: pool timeout, connect timeout, response timeout.
- Tránh để một kết nối/operation bị treo lâu hơn chính sách nội bộ.
- Hỗ trợ cleanup và pool health khi caller đã cancel.

Ngược lại, chỉ đặt transport timeout mà **không có deadline logic** có thể khiến tổng nhiều retries hoặc nhiều downstream calls vượt SLO.

## 10. OpenFeign: connectTimeout/readTimeout theo client name

Spring Cloud OpenFeign cho phép cấu hình **connectTimeout** và **readTimeout** cho từng Feign client:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          default:
            connectTimeout: 500
            readTimeout: 2000
          inventory-service:
            connectTimeout: 300
            readTimeout: 1500
~~~

Hai giá trị trong cấu hình Feign phổ biến này được diễn giải theo **milliseconds**. Với **@FeignClient(name = "inventory-service")**, cấu hình theo tên inventory-service ghi đè giá trị mặc định cho client đó.

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {
    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

**Connect timeout** của Feign liên quan tới thiết lập kết nối. **Read timeout** liên quan tới chờ dữ liệu phản hồi sau khi kết nối, nhưng chi tiết thực thi do HTTP client được Feign sử dụng quyết định. Spring Cloud OpenFeign có thể dùng Apache HttpClient 5, OkHttp hoặc client mặc định theo classpath/configuration; vì vậy **không đồng nhất tên cấu hình Feign với một timer duy nhất của mọi underlying transport**.

### 10.1. Timeout Feign không bao gồm mọi chi phí khác

Tổng elapsed time có thể gồm:

- Discovery/LoadBalancer chọn bản sao.
- Chờ connection pool khi dùng Apache HC5/OkHttp.
- DNS và TCP/TLS.
- Nhận HTTP response và decode body.
- Retry do Feign hoặc các lớp khác.

Spring Cloud OpenFeign mặc định đăng ký **Retryer.NEVER_RETRY**, khác với Feign core có thể retry một số lỗi I/O. Tuy vậy, ứng dụng có thể tự cấu hình retryer, circuit breaker hoặc proxy retry: phải kiểm kê toàn bộ tầng trước khi tính timeout budget.

### 10.2. Connection pool và socket timeout riêng của HC5 dưới Feign

Spring Cloud OpenFeign có các thuộc tính HTTP engine riêng, ví dụ cấu hình **HC5 connection-request-timeout** và **socket-timeout**. Nhưng không được gán các giá trị đó một cách máy móc nếu Feign thực tế dùng OkHttp/default client: chúng có thể **không được áp dụng**.

Trong sản phẩm thực tế, cần:

1. Xác định implementation của Feign Client (HC5, OkHttp, JDK...).
2. Cấu hình Feign connect/readTimeout theo tên client.
3. Cấu hình pool acquire/socket/TLS ở HTTP engine nếu ứng dụng cần.
4. Kiểm thử timeout riêng cho từng phase và log root cause.

## 11. Jetty và các transport khác: cùng API nhưng tên timeout có thể khác

Ngoài Reactor Netty, WebClient có **JettyClientHttpConnector** và **JdkClientHttpConnector**. RestClient có thể được cấp **JettyClientHttpRequestFactory** hoặc **ReactorNettyClientRequestFactory**. Mỗi transport giữ bộ tùy chỉnh HTTP engine của nó:

| Transport | Cấu hình cần kiểm tra | Không nên giả định |
| --- | --- | --- |
| Jetty HTTP client | connect timeout, request/idle timeout, connection pool | Cùng ý nghĩa read timeout với Netty |
| JDK HttpClient | connectTimeout của client, timeout của HttpRequest | Cùng ngữ nghĩa socket read của URLConnection |
| Reactor Netty dùng cho RestClient blocking | Client request factory bao ngoài Netty | Cùng profile thread/concurrency với WebClient reactive |
| OkHttp dưới Feign | connect/read/write/call timeout, dispatcher/connection pool tùy cấu hình | Spring Cloud OpenFeign readTimeout là total call timeout |

Ví dụ với **JettyClientHttpRequestFactory** trong các dòng Spring Framework hiện hành, factory có setter connect/read timeout, nhưng chúng dựa trên Jetty HttpClient. Nếu cần tổng request timeout hoặc idle timeout riêng của Jetty, phải kiểm tra Jetty API và Spring wrapper của phiên bản thực tế.

**Điều quan trọng:** thay từ JDK HttpClient sang Apache HC5 hoặc Reactor Netty có thể đổi mặc định timeout, pool size, redirect, TLS và cách biểu diễn exception dù **business method** vẫn chỉ gọi RestClient.get().retrieve(). Hãy coi việc đổi transport là một thay đổi cần regression test, không chỉ là tối ưu hiệu năng.

## 12. Bảng so sánh ý nghĩa các timeout

| Transport | Timeout khi connect | Timeout chờ response/read | Pool-acquire | Giới hạn toàn request |
| --- | --- | --- | --- | --- |
| HttpURLConnection | URLConnection.connectTimeout | URLConnection.readTimeout: chờ thao tác đọc | Không có API pool-acquire cùng kiểu HC5 | Không có tổng deadline riêng qua hai setter |
| JDK HttpClient | HttpClient.connectTimeout | HttpRequest.timeout khi Spring JdkClientHttpRequestFactory.setReadTimeout | Không có setter pool-acquire chung như HC5 | HttpRequest.timeout cho một request, xem phiên bản JDK và body semantics |
| Apache HC5 | ConnectionConfig.connectTimeout | RequestConfig.responseTimeout + ConnectionConfig.socketTimeout | RequestConfig.connectionRequestTimeout | Cần deadline ứng dụng nếu muốn bao cả retries |
| Reactor Netty | CONNECT_TIMEOUT_MILLIS | HttpClient.responseTimeout và optional Netty I/O handlers | ConnectionProvider.pendingAcquireTimeout | Mono/Flux timeout hoặc deadline khác được áp dụng đúng vị trí |
| Spring Cloud OpenFeign | connectTimeout (Feign options) | readTimeout (Feign options), hiện thực phụ thuộc client | Tùy HC5/OkHttp | Không mặc nhiên bao nhiều attempts |
| Jetty | Cấu hình Jetty HttpClient/factory | Response/request/idle tùy Jetty API | Tùy Jetty connection management | Cần kiểm tra request timeout và deadline ở phiên bản cụ thể |

Đây là bảng **ánh xạ khái niệm**, không phải bảng cam kết chúng bằng nhau. Tài liệu source/Javadoc và thử nghiệm ở tầng transport đang chạy mới là căn cứ để xác định thời điểm tính và cách phát sinh ngoại lệ.

## 13. Connect, response và total deadline: ví dụ có số

Giả sử Order Service có thời gian tối đa 2.000 ms để thực hiện một lời gọi Inventory. Một attempt diễn ra:

| Giai đoạn | Thời gian minh họa |
| --- | ---: |
| LoadBalancer/discovery | 30 ms |
| Chờ pool acquire | 180 ms |
| DNS | 60 ms |
| TCP connect | 120 ms |
| TLS handshake | 180 ms |
| Gửi request | 50 ms |
| Backend xử lý/đợi header | 950 ms |
| Đọc body/deserialize | 90 ms |
| **Tổng** | **1.660 ms** |

Nếu chỉ cấu hình responseTimeout=1.000 ms, attempt này vẫn có thể hoàn thành trong **1.660 ms**, bởi nó đã tốn thời gian ở các giai đoạn trước. Nếu caller còn retry một attempt tương tự, tổng thời gian có thể vượt **3.320 ms**, chưa tính backoff.

Ngược lại, nếu deadline toàn lời gọi **2.000 ms**, attempt đầu dùng 1.660 ms thì chỉ còn 340 ms. Nếu retry cần 100 ms backoff và có thể dùng tối đa 240 ms cho attempt sau, việc thử lại một backend thường cần khoảng 1 giây có thể **không còn hữu ích**. Policy nên dừng thay vì retry khi ngân sách còn lại quá nhỏ.

### 13.1. Deadline và các timeout nhỏ hơn phải nhất quán

Ví dụ mục tiêu thiết kế (không phải default):

~~~text
Budget end-to-end:              1800ms
Pool acquire per attempt:        150ms
Connect per new connection:      250ms
TLS handshake:                   400ms
Response inactivity per attempt: 900ms
Maximum retry attempts:         1 (thêm 1 lần sau lần đầu)
Backoff:                         100ms
~~~

Không cần mọi timeout phase cộng đúng bằng end-to-end deadline, vì có phase bỏ qua khi reuse connection và một số hoạt động chồng lấp. Nhưng **deadline tổng phải là giới hạn cuối cùng**, đặc biệt khi có retry.

Nếu nhiều dependency được gọi nối tiếp trong cùng một inbound request, cần **phân bổ deadline cho từng dependency** và chừa ngân sách để caller xử lý response. Nếu gọi song song, thời gian chờ tổng có thể phụ thuộc nhánh chậm nhất, nhưng connection pool và server load lại chịu tổng số request đồng thời.

## 14. Retry nhân thời gian và làm đổi bản sao

Khi timeout xảy ra, Spring Cloud LoadBalancer hoặc HTTP client có thể chọn lại ServiceInstance theo chính sách retry. Điều này đặc biệt nguy hiểm với thao tác ghi:

~~~text
Attempt 1:
  Order -> Inventory A : POST /reservations
  Inventory A commit transaction thành công
  Response bị trễ hoặc mất
  Caller timeout

Attempt 2:
  Order -> Inventory B : POST /reservations
  Có nguy cơ đặt chỗ lần hai nếu backend không deduplicate
~~~

**Timeout không chứng minh request thất bại ở server.** Vì vậy:

- Retry GET thường đơn giản hơn retry POST có side effect, nhưng vẫn phải đánh giá backend.
- Với POST tạo đơn/thanh toán/giữ tồn kho, dùng **Idempotency-Key** cùng một giá trị trên mọi attempts và server phải thực thi deduplication.
- Đặt giới hạn **max attempts**, backoff, total deadline và điều kiện retryable status/exception.
- Phân biệt retry **trên cùng instance** với retry **sang instance khác**; thay instance không đảm bảo transaction trước chưa hoàn tất.
- Tránh retry lồng nhau (HTTP client + LoadBalancer + service mesh + business layer).

Ví dụ tính tổng một cách bảo thủ:

~~~text
Tổng ~ attempt1(900ms) + backoff(100ms) + attempt2(900ms)
     = 1900ms
~~~

Nếu SLO chỉ 1.500 ms, cấu hình này đã không phù hợp ngay từ đầu. Một **deadline wrapper** đặt ở đúng tầng cần giới hạn **cả retries**; nếu đặt timeout ở bên trong retry operator, mỗi lần thử có thể được cấp lại đồng hồ.

## 15. Streaming và phản hồi “nhỏ giọt” là ngoại lệ quan trọng

Một API trả SSE, NDJSON hoặc dữ liệu tải xuống lớn có thể chạy lâu dù connection hoàn toàn khỏe:

~~~text
0s:  HTTP 200 + headers
1s:  event 1
2s:  event 2
3s:  event 3
...
60s: event 60
~~~

Nếu transport dùng **read inactivity timeout 5s**, stream có thể tiếp tục vì mỗi giây vẫn có dữ liệu. Nếu áp đặt **total Mono timeout 5s** lên một Mono chỉ hoàn thành khi toàn body đã đọc xong, request sẽ bị hủy dù stream đang hoạt động đúng thiết kế.

Với Reactor:

~~~java
Flux<InventoryEvent> events = webClient.get()
        .uri("http://inventory-service/api/events")
        .retrieve()
        .bodyToFlux(InventoryEvent.class)
        .timeout(Duration.ofSeconds(15));
~~~

**Flux.timeout(Duration)** kiểm tra độ trễ giữa các tín hiệu phát ra, không phải tổng thời lượng tuyệt đối của luồng SSE. Nó hữu ích để phát hiện stream im lặng quá lâu nếu contract yêu cầu heartbeats/events đều đặn; nhưng sẽ ngắt stream bình thường nếu khoảng cách hợp lệ giữa hai sự kiện có thể lớn hơn 15 giây.

Một giải pháp tốt thường phân biệt:

1. Timeout thiết lập kết nối.
2. Timeout chờ response headers đầu tiên.
3. Idle timeout khi không nhận network bytes hoặc application events.
4. Giới hạn vòng đời tối đa **nếu** nghiệp vụ yêu cầu.
5. Chính sách reconnect/resume bằng event ID khi stream mất kết nối.

Tùy transport, một HTTP chunk có thể được nhận nhưng chưa tạo đủ JSON/SSE event để phát ra Flux. Vì vậy, **network read timeout** và **Flux event timeout** có thể quan sát những khoảng im lặng khác nhau.

## 16. Lỗi timeout xuất hiện dưới những exception nào?

Không có một **TimeoutException duy nhất** cho mọi HTTP transport:

| Client/transport | Exception hoặc root cause thường gặp | Cần phân biệt |
| --- | --- | --- |
| RestTemplate/RestClient + HttpURLConnection | ResourceAccessException bọc SocketTimeoutException, ConnectException... | Có thể là connect/read/network |
| RestClient + JDK HttpClient | ResourceAccessException với cause từ java.net.http, ví dụ HttpTimeoutException/HttpConnectTimeoutException | Timeout của request hay connect tùy cause |
| RestClient + Apache HC5 | ResourceAccessException hoặc wrapper HTTP client, root cause socket/pool/handshake | Đọc chuỗi cause để tìm giai đoạn |
| WebClient + Reactor Netty | WebClientRequestException, root cause ConnectTimeoutException, pool acquire timeout, SSLException... | I/O error trước hoặc trong response |
| WebClient + Mono.timeout | java.util.concurrent.TimeoutException phát bởi operator | Có thể không phải lỗi connector |
| OpenFeign | RetryableException/FeignException hoặc cause từ transport | Có thể khác theo Feign Client implementation |
| Bất kỳ client nào có HTTP 408/504 | HTTP response với status từ server/gateway | **Không đồng nghĩa** client-side socket timeout |
| Không tìm thấy ServiceInstance | Lỗi/response do LoadBalancer adapter tạo | Có thể chưa có bất kỳ socket connection nào |

Các tên exception thuộc nhiều thư viện và phiên bản; bảng là **định hướng phân loại**, không phải cam kết class chính xác cho mọi stack. Khi diagnostic:

1. Ghi nhận **loại exception cao nhất và root cause**.
2. Xác minh có HTTP response status/headers hay chưa.
3. Xác minh đã chọn ServiceInstance hay chưa.
4. Xác minh có kết nối TCP và backend nhận request không.
5. Xác minh pool acquisition, DNS, TLS hay read thực sự đang chờ.
6. Xác minh retry attempt và deadline đã hết hay chưa.

### 16.1. HTTP 408 hoặc 504 không phải nhất thiết là timeout của client

- **HTTP 408 Request Timeout**: server hoặc một thành phần trung gian trả mã HTTP vì không nhận được request đúng hạn theo chính sách của nó.
- **HTTP 504 Gateway Timeout**: gateway/proxy báo không nhận response từ upstream đúng thời gian.
- **Client-side response timeout**: client tự ngừng chờ; có thể không có HTTP response status.

Cả ba đều chứa từ “timeout”, nhưng nguồn phát sinh, hành động vận hành và retry policy khác nhau. **Không dựng một HTTP 504 giả** cho mọi client timeout rồi bỏ qua nguyên nhân gốc.

### 16.2. Exception mapping nên giữ cause và phase

Ở lớp adapter, có thể sử dụng domain taxonomy:

~~~java
sealed interface InventoryFailure
        permits PoolBusy, ConnectFailed, ResponseTimedOut,
                HttpFailure, InvalidResponse {}

record PoolBusy(String serviceId) implements InventoryFailure {}
record ConnectFailed(String serviceId) implements InventoryFailure {}
record ResponseTimedOut(String serviceId) implements InventoryFailure {}
record HttpFailure(String serviceId, int status)
        implements InventoryFailure {}
record InvalidResponse(String serviceId) implements InventoryFailure {}
~~~

Đây là **mô hình dữ liệu minh họa Java 17+**, không phải lỗi mà Spring tự tạo. Trong code thật, exception translator cần truy nguyên cause theo transport và giữ trace ID/cause để chẩn đoán; không bắt một **ResourceAccessException** rồi tự đoán nó luôn là read timeout.

## 17. Kiểm thử timeout theo từng phase, không đoán từ elapsed time

Một test chỉ báo “lệnh gọi thất bại sau 2 giây” **chưa chứng minh read timeout đã hoạt động**. Cần cố tình làm chậm **đúng phase** cần kiểm tra và xác nhận exception/root cause/nhật ký phía server.

### 17.1. MockWebServer: response body bị trì hoãn cho client blocking

Ví dụ JUnit và OkHttp MockWebServer 4.x:

~~~java
@Test
void blockingClientTimesOutWhenBodyIsDelayed() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        server.start();
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "text/plain")
                .setBody("late-response")
                .setBodyDelay(2, TimeUnit.SECONDS));

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(1));
        factory.setReadTimeout(Duration.ofMillis(300));

        RestClient client = RestClient.builder()
                .requestFactory(factory)
                .build();

        assertThrows(ResourceAccessException.class, () ->
                client.get()
                        .uri(server.url("/delayed").toString())
                        .retrieve()
                        .body(String.class));

        RecordedRequest received =
                server.takeRequest(1, TimeUnit.SECONDS);
        assertNotNull(received);
        assertEquals("/delayed", received.getPath());
    }
}
~~~

Ví dụ này yêu cầu JUnit Jupiter, Spring Web và **MockWebServer 4.x**, với imports như **java.time.Duration**, **java.util.concurrent.TimeUnit**, **MockResponse**, **RecordedRequest** và **ResourceAccessException**. Nó được thiết kế để kiểm tra **body read chậm** qua HttpURLConnection. Khi dùng trong dự án, phải kiểm tra API mock server/lifecycle của phiên bản đang dùng và xem root cause thực tế, không chỉ dừng ở assertThrows chung.

**Quan trọng:** ở đây URI là URL vật lý của server test, nên bài test kiểm chứng HTTP transport, **không kiểm chứng Spring Cloud LoadBalancer**. Cần một integration test riêng dùng service ID và @LoadBalanced để bảo đảm request được chọn đúng đích.

### 17.2. WebClient: timeout của Reactor operator

~~~java
@Test
void reactorDeadlineCancelsSlowCall() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        server.start();
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "text/plain")
                .setBody("late")
                .setBodyDelay(2, TimeUnit.SECONDS));

        WebClient client = WebClient.create();

        Mono<String> response = client.get()
                .uri(server.url("/slow").toString())
                .retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofMillis(400));

        StepVerifier.create(response)
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify(Duration.ofSeconds(4));
    }
}
~~~

Test dùng **Reactor StepVerifier**, không gọi block(). Đây là timeout của **Mono operator**, không phải bằng chứng rằng Reactor Netty responseTimeout hoặc CONNECT_TIMEOUT_MILLIS đã nổ. Muốn kiểm tra đúng tầng Netty, cấu hình một connector riêng và ghi nhận root cause.

Với test quá ngắn, event loop có thể chưa khởi tạo xong trước khi deadline nổ. Hãy **warm up client** hoặc tăng ngưỡng đủ an toàn để test đo tình huống mong muốn, không đo độ trễ khởi tạo fixture.

### 17.3. Kiểm thử pool acquire timeout

Để buộc request đợi pool (Reactor Netty hoặc Apache HC5):

1. Tạo pool tối đa **1 connection** đến một host/route.
2. Request A lấy connection và giữ nó đủ lâu (ví dụ server trì hoãn body).
3. Chỉ khi xác nhận request A đang giữ connection, khởi động request B.
4. Đặt pool acquire timeout của B ngắn hơn thời gian A giữ connection.
5. Xác minh B lỗi **trong lúc chờ pool**; backend chưa nhận request B.
6. Cleanup/cancel A, rồi kiểm tra pool hoạt động trở lại.

Tránh chỉ dùng hai request đồng thời và giả định A luôn thắng race. Cần latch/dispatcher/observable lifecycle để kiểm soát thời điểm A đã chiếm slot. Cũng cần tắt retry ở test này để số request không bị che bởi attempt bổ sung.

### 17.4. Kiểm thử connect timeout không giống connection refused

Một mock server đóng port ngay thường tạo **connection refused** rất nhanh, **không chứng minh connect timeout**. Kiểm thử TCP SYN không nhận phản hồi cần môi trường mạng có thể kiểm soát (Toxiproxy, network namespace hoặc network fault injection), và phải tránh phụ thuộc IP “đen” có thể được mạng xử lý khác nhau.

Các ca nên tách:

| Ca test | Phương pháp tạo lỗi | Assertion |
| --- | --- | --- |
| Connection refused | Không có listener ở port đã biết | Lỗi kết nối thường đến nhanh |
| Connect timeout | Proxy mạng drop kết nối trong test cô lập | Connect timeout đúng phase |
| TLS handshake chậm | Proxy/TLS test endpoint trì hoãn handshake | Handshake timeout hoặc deadline |
| Response headers chậm | Server nhận request nhưng trì hoãn headers | Response timeout |
| Response body chậm | Server trả headers rồi trì hoãn body | Read/response timeout theo engine |
| Trickle response | Server gửi bytes theo chu kỳ gần ngưỡng | Xác minh idle timeout khác tổng deadline |
| Pool cạn | Pool=1, request A giữ connection | Pool acquire timeout, không phải connect |
| DNS chậm | Resolver giả hoặc network test kiểm soát DNS | Resolver timeout, không phải response |

### 17.5. Kiểm thử timeout cùng LoadBalancer

Một test tích hợp thực tế cần:

- Hai MockWebServer trả instance ID khác nhau.
- SimpleDiscoveryClient hoặc supplier giả cung cấp hai ServiceInstance.
- RestClient/WebClient có **@LoadBalanced** hoặc OpenFeign được tích hợp LoadBalancer.
- Client gọi **http://inventory-service/...**, không gọi trực tiếp localhost.
- Bản sao A trả chậm, bản sao B trả nhanh.
- Tắt hoặc cấu hình retry rõ ràng rồi đếm **RecordedRequest** trên cả hai server.

Các điều phải xác nhận:

~~~text
serviceId = inventory-service
selected  = inventory-a
physical  = localhost:<portA>
transport = Reactor Netty (hoặc JDK/HC5...)
failure   = response timeout
attempt   = 1
~~~

Nếu bật retry, cần tiếp tục xác minh attempt thứ hai có chọn instance B hay không. Chỉ thấy caller nhận HTTP 200 sau retry **chưa chứng minh LoadBalancer đã đổi instance**.

## 18. Observability: phân biệt latency với loại timeout

Một log cảnh báo đơn giản:

~~~text
WARN downstream timeout after 2000ms
~~~

không đủ. Nên thu thập những trường hợp có thể:

| Trường | Ý nghĩa |
| --- | --- |
| traceId / spanId | Nối lời gọi xuyên dịch vụ |
| serviceId | Tên downstream logic |
| instanceId / host:port | Bản sao thực tế được chọn |
| transport | Reactor Netty, Apache HC5, JDK... |
| method / path template | Endpoint và tính an toàn khi retry |
| attempt | Lần thử thứ mấy |
| elapsedTotalMs | Thời gian cả lời gọi logic |
| poolAcquireMs | Thời gian chờ connection pool, nếu engine đo được |
| connectMs | Thời gian tạo connection mới |
| tlsHandshakeMs | Handshake HTTPS |
| responseWaitMs | Chờ response/header/body theo engine |
| timeoutType | pool/connect/TLS/read/operator/deadline |
| httpStatus | Chỉ ghi khi có response thật |
| rootCause | Loại exception thấp nhất có ích |

Spring Boot/Micrometer, Reactor Netty và Apache HC5 có những hook/metrics tương ứng nhưng tên metric và khả năng bật mặc định khác nhau. Đây là **bộ trường observability khuyến nghị**, không phải tên metric có sẵn cho mọi connector.

Khi dùng Spring Cloud LoadBalancer, cần quan sát thêm:

- Danh sách ServiceInstance trước/sau cache, health, zone/hint filter.
- Instance được chọn ở attempt đầu và retry.
- Cache TTL, health-check poll interval, số lần không có instance.
- Số 503 từ chính backend hoặc gateway, tách khỏi lỗi chọn instance.
- Số lần request bị hủy sau khi caller hết deadline.

### 18.1. Không log nội dung nhạy cảm để debug timeout

Khi lỗi xuất hiện, không bật log toàn bộ Authorization, Cookie, query token, request body chứa dữ liệu khách hàng hoặc response body nhạy cảm trên môi trường production. Dùng **path template**, instance ID, status, error category, trace ID và số liệu thời gian đã được làm sạch.

Nếu dùng wire logging của Netty/HTTP client trong môi trường test, hãy tắt hoặc giới hạn phạm vi trước khi triển khai production. Logs của transport có thể chứa header hoặc dữ liệu nhạy cảm.

## 19. Chọn timeout theo SLO, không sao chép con số ngẫu nhiên

Một quy trình thiết kế có thể áp dụng cho mỗi downstream:

1. Xác định **SLO inbound**: Order API phải trả trong bao lâu ở P95/P99?
2. Trừ ngân sách dành cho xử lý trong Order Service và serialization response.
3. Phân bổ ngân sách cho các downstream tuần tự/đồng thời.
4. Đo latency thực tế theo zone, kích thước payload, cold connection vs keep-alive và tải peak.
5. Xác định pool size, số request concurrent và pool acquire timeout.
6. Đặt connect timeout dựa trên mạng nội bộ/thực tế.
7. Đặt response/read timeout theo loại endpoint (GET ngắn, export dài, SSE).
8. Thiết kế retry attempts/backoff trong ngân sách còn lại.
9. Đặt deadline cuối cho toàn lời gọi logic.
10. Kiểm thử bằng network fault injection, pool saturation và real client metrics.

Ví dụ: Order API có deadline 2.500 ms; cần 300 ms cho xử lý nội bộ, 200 ms cho serialization và margin. Ngân sách downstream còn khoảng **2.000 ms**. Nếu Inventory yêu cầu P99 700 ms, hai attempts 800 ms cùng backoff 100 ms có thể phù hợp, nhưng phải kiểm tra overhead/pool và khả năng thiếu deadline ở attempt sau. Đây là **minh họa phân bổ**, không phải đề xuất một cấu hình cứng cho mọi hệ thống.

### 19.1. Timeout quá ngắn cũng nguy hiểm

Đặt mọi connect timeout 50 ms và response timeout 100 ms có thể giảm số request bị treo, nhưng khiến:

- TLS/cold start thất bại nhiều hơn.
- Lưu lượng cross-zone có jitter bị cắt đột ngột.
- Retry khuếch đại tải backend.
- Công việc lớn nhưng hợp lệ bị hủy liên tục.
- Người dùng thấy lỗi mặc dù backend vẫn có thể hoàn thành trong SLO hợp lý.

Không tối ưu chỉ theo “thời gian lỗi càng ngắn càng tốt”. Cần cân bằng **latency, availability, tải và tính đúng đắn nghiệp vụ**.

### 19.2. Timeout quá dài làm cạn tài nguyên

Ngược lại, đặt response timeout 60 giây cho endpoint GET nhỏ có thể giữ connection/worker thread lâu, kéo dài queue pool và làm lỗi lan sang các downstream khác. Trong WebFlux, I/O non-blocking giảm số thread chờ, nhưng **connection, buffer, pending acquire queue và tài nguyên backend** vẫn bị chiếm.

Một timeout quá dài có thể làm circuit breaker thấy quá nhiều slow calls trước khi phản ứng; timeout và circuit breaker giải quyết các rủi ro liên quan nhưng **không thay thế nhau**.

## 20. Những hiểu lầm thường gặp và cách sửa

| Hiểu lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Connect timeout = giới hạn toàn HTTP call | Chỉ liên quan connection mới | Thêm response timeout và deadline |
| Read timeout 2s = hoàn tất response trong 2s | Một số engine đo I/O idle, không phải tổng | Xem semantics của đúng factory/engine |
| JDK factory và Simple factory đều là JDK nên giống nhau | Một cái dùng HttpURLConnection, một cái dùng java.net.http.HttpClient | Đọc Javadoc và test riêng |
| Pool acquire timeout và connect timeout là một | Pool có thể chờ trước TCP connect | Đo pending connections |
| TLS handshake chắc chắn nằm trong connect timeout | Phụ thuộc transport, có thể có timeout riêng | Cấu hình và test TLS riêng |
| WebClient.responseTimeout bao luôn retry | Retry thường tạo thêm attempts ngoài response timer | Đặt deadline ở ngoài retries nếu muốn tổng |
| Flux.timeout là deadline cả stream | Thường kiểm tra khoảng cách giữa signals | Thiết kế stream lifetime riêng |
| Feign readTimeout áp dụng như nhau cho HC5 và OkHttp | Underlying client quyết định chi tiết | Kiểm tra Feign Client thực |
| Server trả 504 = client bị SocketTimeoutException | 504 là HTTP response từ gateway | Tách HTTP status khỏi lỗi I/O |
| Dừng server sẽ test connect timeout | Thường tạo connection refused ngay | Dùng fault proxy drop TCP có kiểm soát |
| Tăng timeout sửa lỗi No instances available | Không có instance trước khi gửi HTTP | Kiểm tra discovery/supplier/health |
| Retry timeout POST luôn an toàn | Server có thể đã commit trước timeout | Idempotency + operation-status API |
| Chỉ cần một global timeout cho mọi endpoint | Endpoint ngắn, streaming, tải file khác nhau | Per-client/per-request policy |
| Tăng pool size luôn chữa pendingAcquireTimeout | Có thể đẩy quá tải xuống backend | Đo saturation và giới hạn concurrency |

## 21. Bài thực hành: tạo bảng thời gian cho một request

Cho bối cảnh:

~~~text
Caller: order-service, request GET http://inventory-service/api/stock/X
LoadBalancer: chọn inventory-a.internal:8443
Transport: Reactor Netty, HTTPS, pool giới hạn 10 connections

T_lookup = 40ms
T_pool   = 260ms
T_dns    = 20ms
T_tcp    = 100ms
T_tls    = 140ms
T_upload = 10ms
T_wait   = 900ms
T_body   = 100ms
~~~

**Câu hỏi A:** tổng elapsed time xấp xỉ bao nhiêu nếu các bước diễn ra nối tiếp?

**Câu hỏi B:** với pendingAcquireTimeout=200ms, lỗi ở giai đoạn nào? ConnectTimeout=500ms có cứu được không?

**Câu hỏi C:** nếu pool acquire thành công và responseTimeout=1.000ms, caller có chắc kết thúc trong 1 giây không?

**Câu hỏi D:** nếu deadline tổng 1.500ms, retry cùng request sau 100ms backoff còn có ý nghĩa không?

### Gợi ý lời giải

- **A:** xấp xỉ **1.570 ms** (cộng các số đã cho; trong thực tế các giai đoạn có thể không tách tuyệt đối).
- **B:** pool acquire cần 260ms nhưng giới hạn 200ms, nên request có thể lỗi **trước TCP connect**. Tăng connect timeout không thay đổi thời gian chờ pool.
- **C:** không; response timeout không bao trọn pool/DNS/connect/TLS và decode. Tổng có thể dài hơn 1 giây.
- **D:** attempt đầu đã tiêu hết khoảng 1.570ms, nên deadline 1.500ms đã hết trước khi có thể retry. Chính sách đúng là ngừng và báo lỗi/khôi phục theo contract, không bắt đầu thêm attempt.

Để mở rộng thực hành, thay transport thành Apache HC5 rồi xác định phải đặt những thuộc tính nào để giới hạn pool, connect, TLS và response tương tự. Cuối cùng thực hiện integration test với MockWebServer/Toxiproxy để so sánh root cause.

## 22. Checklist trước khi đưa timeout policy vào production

- [ ] Xác minh **HTTP engine thực sự** của mỗi RestTemplate/RestClient/WebClient/Feign bean.
- [ ] Biết transport đó có pool hay không và pool acquire timeout được cấu hình ở đâu.
- [ ] Đặt connect timeout cho connection mới theo dữ liệu mạng thực tế.
- [ ] Có response/read timeout phù hợp với loại endpoint và kích thước body.
- [ ] Xác minh TLS handshake và DNS/proxy timeout nếu hạ tầng có sử dụng.
- [ ] Không nhầm read inactivity timeout với **total deadline**.
- [ ] Có deadline cho toàn lời gọi logic, bao gồm service lookup, retries, backoff và decode theo nhu cầu.
- [ ] Kiểm tra timeout áp dụng trên **cold connection** lẫn connection tái sử dụng.
- [ ] Khi dùng WebClient, phân biệt Mono.timeout, Flux.timeout và Reactor Netty responseTimeout.
- [ ] Khi dùng OpenFeign, xác minh named client config và underlying Feign HTTP client.
- [ ] Không retry lỗi validation; request có side effect phải có idempotency/duplicate handling.
- [ ] Có bài test pool saturation, response headers/body chậm, connection refused và transport timeout thực sự.
- [ ] Có bài test LoadBalancer riêng để biết instance nào được chọn.
- [ ] Observability tách pool/connect/TLS/response/deadline, HTTP status và no-instance.
- [ ] Có alert cho P95/P99, pool pending, timeout rate, retry amplification và error budget.
- [ ] Không bật logs chứa token/credential hoặc dữ liệu nhạy cảm.
- [ ] Ghi chú phiên bản HTTP library và Spring BOM vì ý nghĩa/mặc định có thể thay đổi.

## 23. Kết luận

**Timeout không phải một con số duy nhất mà là một bộ giới hạn theo giai đoạn.** Spring Cloud LoadBalancer chọn bản sao của service ID; HTTP transport quyết định cách chờ kết nối, response và body; tầng ứng dụng chịu trách nhiệm về **deadline** và retry an toàn.

Điểm cần nhớ khi so sánh transport:

- **HttpURLConnection** có connect/read timeout theo URLConnection.
- **JDK HttpClient** có connect timeout của client và request timeout; Spring JdkClientHttpRequestFactory đặt “read timeout” thông qua cơ chế timeout của request.
- **Apache HC5** tách pool acquire, connection config, socket và response timeout.
- **Reactor Netty** tách pendingAcquireTimeout, CONNECT_TIMEOUT_MILLIS, responseTimeout, SSL/DNS/proxy; Reactor Mono/Flux còn có operator timeout theo tín hiệu.
- **OpenFeign** công khai connectTimeout/readTimeout theo client name, nhưng cách thực thi phụ thuộc HTTP client nằm dưới.

Chỉ khi phân biệt được **đồng hồ nào đang chạy ở giai đoạn nào**, đo được root cause và kiểm thử trên transport thật, đội ngũ mới có thể thiết kế cấu hình timeout vừa bảo vệ SLO vừa tránh retry storm và lỗi dữ liệu.

## 24. Tài liệu tham khảo

- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): request factories cho RestClient/RestTemplate và cách chọn HTTP transport.
- [Spring Framework – SimpleClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): connect/read timeout của HttpURLConnection.
- [Spring Framework – JdkClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): setReadTimeout ánh xạ sang HttpRequest timeout.
- [Spring Framework – HttpComponentsClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html): HC5 connection request và response timeout.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): connector Reactor Netty, connect/response timeout và native request override.
- [Reactor Netty – HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#_timeout_configuration): pool, connect, response, TLS, DNS và proxy timeouts.
- [Apache HttpClient 5 – RequestConfig.Builder](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/RequestConfig.Builder.html): connection request timeout, response timeout và giới hạn không phải deadline.
- [Apache HttpClient 5 – ConnectionConfig](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/ConnectionConfig.html): socket/connect/idle/TTL settings.
- [Oracle Java – HttpClient.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): connectTimeout và phạm vi khi tái sử dụng connection.
- [Oracle Java – HttpRequest.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout và HttpTimeoutException.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): named client connectTimeout/readTimeout, retry behavior và HTTP engines.
- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): chọn ServiceInstance, retry và service discovery.
- [Reactor – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): timeout/retry và thứ tự operator.

