# ClientHttpRequestFactory và lựa chọn thư viện HTTP nền trong Spring

## 1. Bối cảnh: cùng một RestClient, nhiều HTTP engine khác nhau

Trong Java/Spring, lời gọi đến dịch vụ HTTP bên ngoài có thể viết ở cấp cao:

~~~java
Order order = restClient.get()
        .uri("/orders/{id}", 42)
        .retrieve()
        .body(Order.class);
~~~

Đây là fragment có `RestClient restClient` và class/record `Order` được cấu hình ở nơi khác. Đoạn code mô tả **cái gì cần gọi**: GET, URI template, đổi JSON sang DTO. Nhưng để thật sự gửi request qua TCP/TLS, Spring cần một **HTTP transport implementation**.

Trục kỹ thuật:

~~~text
Code nghiệp vụ
     |
     v
RestClient / RestTemplate              (API HTTP đồng bộ)
     |
     v
HttpMessageConverter + Interceptors   (JSON, headers, logging)
     |
     v
ClientHttpRequestFactory              (SPI chọn transport)
     |
     +-- JdkClientHttpRequestFactory  --> java.net.http.HttpClient
     +-- HttpComponentsClientHttpRequestFactory --> Apache HttpClient 5
     +-- JettyClientHttpRequestFactory --> Jetty HttpClient
     +-- ReactorNettyClientRequestFactory --> Reactor Netty HttpClient
     +-- SimpleClientHttpRequestFactory --> HttpURLConnection
     |
     v
DNS -> connection acquire -> TCP -> TLS -> HTTP write/read -> response
~~~

**`ClientHttpRequestFactory` là abstraction của Spring cho việc tạo một HTTP request có thể thực thi, không phải factory tạo RestClient.** Đổi factory có thể đổi connection pooling, HTTP versions, redirect/proxy, TLS, các loại timeout, hiệu năng và error behavior nhưng không nhất thiết cần sửa toàn bộ code nghiệp vụ.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích interface `ClientHttpRequestFactory` và vai trò của `ClientHttpRequest`/`ClientHttpResponse`.
2. Biết cách `RestClient` và `RestTemplate` chọn request factory.
3. So sánh `SimpleClientHttpRequestFactory`, `JdkClientHttpRequestFactory`, Apache HttpClient 5, Jetty và Reactor Netty.
4. Chọn HTTP transport phù hợp workload: tần suất request, nhiều host, pooling, HTTP/2, proxy, mTLS, TLS và retry policy.
5. Cấu hình timeout **đúng tầng**: connection acquisition, TCP connect, TLS handshake, response/read, overall deadline.
6. Hiểu giới hạn Spring Framework **6.1** so với **6.2+**, không copy API chưa tồn tại.
7. Cấu hình bean `RestClient` với explicit factory và Java 17.
8. Xây demo chạy được bằng Spring Boot 3.3.5, server địa phương và kiểm thử JUnit HTTP thật.
9. Tránh resource leaks, thread starvation, SSRF, credential leakage, redirect surprises và giả định mặc định transport bất biến.

Bối cảnh cha: **HTTP client đồng bộ**. `RestClient` có từ Spring Framework 6.1. Ví dụ dưới dùng **Java 17 + Spring Boot 3.3.5**, không tự áp dụng các Spring 7/Boot 4 API mới cho code demo.

## 2. Interface `ClientHttpRequestFactory` thực sự định nghĩa gì?

Ở Spring Framework 6.1, interface thuộc package:

~~~java
org.springframework.http.client.ClientHttpRequestFactory
~~~

Phương thức cốt lõi:

~~~java
ClientHttpRequest createRequest(
        URI uri, HttpMethod httpMethod) throws IOException;
~~~

- `URI` xác định destination và path cần gọi.
- `HttpMethod` xác định GET/POST/PUT/PATCH/DELETE...
- Kết quả là một `ClientHttpRequest` với headers/body có thể chuẩn bị rồi thực thi.
- `IOException` có thể phát sinh khi không tạo request được; lỗi khi thật sự gửi/đọc thường xuất hiện muộn hơn.
- `ClientHttpRequest.execute()` trả `ClientHttpResponse` khi request được gửi và response sẵn có.

### 2.1. Luồng đồng bộ dạng thấp

~~~text
factory.createRequest(uri, GET)
  -> request.getHeaders().setAccept(...)
  -> request.execute()                 [network có thể block]
  -> response.getStatusCode()
  -> response.getBody()                [I/O có thể block]
  -> close response/body resources
~~~

Đây là mô tả khái niệm, không đề nghị viết HTTP business code bằng SPI thấp này. `RestClient`/`RestTemplate` thường quản lý phần lớn headers, converters, error handling và đóng response đúng lifecycle. Khi tự dùng `ClientHttpRequest` trực tiếp, ứng dụng phải có chính sách đóng `ClientHttpResponse`.

### 2.2. Request factory có làm HTTP client non-blocking không?

**Không.** Một factory nền có engine nội bộ hỗ trợ asynchronous I/O (ví dụ Reactor Netty hoặc JDK HttpClient) vẫn phục vụ **synchronous request/response contract** khi dùng qua `RestClient`/`RestTemplate`. Thread gọi `restClient.get()...retrieve()...body(...)` có thể chờ kết quả.

Nếu đang ở Spring WebFlux event-loop thread, **đừng** dùng `RestClient` trực tiếp trong handler rồi cho rằng có Reactor Netty factory là non-blocking. Để non-blocking end-to-end, dùng reactive `WebClient` và trả `Mono/Flux`, tránh `block()`. Nếu phải gọi legacy synchronous API trong WebFlux, cô lập qua bounded worker, nhưng phải đo queue/timeout.

### 2.3. Factory khác message converter

`HttpMessageConverter` chuyển đổi Java object ↔ HTTP payload (Jackson JSON, String, form...). Nó không quyết định connection pool hoặc TLS protocol. `ClientHttpRequestFactory` quyết định cách gửi/nhận bytes qua HTTP. Thay factory không tự động thay Jackson serializer, DTO version, retry policy hay API error schema.

## 3. ClientHttpRequestFactory là SPI, RestClient là API sử dụng

### 3.1. `RestClient`

`RestClient` là HTTP client **đồng bộ, fluent**, giới thiệu trong Spring 6.1:

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://service.example.test")
        .requestFactory(factory)
        .build();
~~~

`factory` là bean `ClientHttpRequestFactory` được inject hoặc dựng riêng. Các thao tác:
- `get()`/`post()` chọn method.
- `uri(...)` hỗ trợ template variables.
- `header(...)`, `accept(...)`, `contentType(...)` thêm HTTP metadata.
- `body(...)` gửi body.
- `retrieve()` đọc response theo mô hình thông dụng, có default status handling.
- `exchange(...)` cho xử lý raw response/status custom; cần quản lý error/status theo cách bạn chọn.

### 3.2. `RestTemplate`

`RestTemplate` vẫn tồn tại và được dùng nhiều trong code cũ:

~~~java
RestTemplate template = new RestTemplate(factory);

Order order = template.getForObject(
        "https://service.example.test/orders/{id}",
        Order.class, 42);
~~~

Hai API có thể dùng **cùng một factory**. Việc chuyển `RestTemplate` → `RestClient` không bắt buộc đổi HTTP engine ngay lập tức; tách hai quyết định để migration giảm rủi ro.

### 3.3. Không nhầm WebClient và ClientHttpConnector

`WebClient` (reactive) dùng abstraction `ClientHttpConnector`, ví dụ `ReactorClientHttpConnector`, chứ **không** sử dụng `ClientHttpRequestFactory` làm extension point chủ yếu. `ReactorNettyClientRequestFactory` là adapter để dùng Reactor Netty trong synchronous client; nó không làm API của RestClient trở thành reactive.

## 4. Các HTTP backend có sẵn trong Spring 6.1

| Factory | Library HTTP nền | Khi phù hợp | Điểm cần xem xét |
| --- | --- | --- | --- |
| `SimpleClientHttpRequestFactory` | `java.net.HttpURLConnection` | Demo, tích hợp đơn giản, dependency tối thiểu | Giới hạn/quirks legacy JDK API, status/error path, tính năng |
| `JdkClientHttpRequestFactory` | `java.net.http.HttpClient` (Java 11+) | Java 17, không thêm thư viện thứ ba, HTTP/2 nếu peer hỗ trợ | Pool knobs hạn chế hơn Apache; JDK TLS/proxy/redirect semantics |
| `HttpComponentsClientHttpRequestFactory` | Apache HttpClient **5.x** | Pool tuning, enterprise proxy, nhiều outbound calls, connection management | Phải thêm Apache HttpClient 5, quản lý pooling/lifecycle/timeouts |
| `JettyClientHttpRequestFactory` | Jetty HttpClient | Đội ngũ đã chuẩn hóa Jetty, HTTP features của Jetty | Thêm dependencies, lifecycle, timeout/proxy riêng |
| `ReactorNettyClientRequestFactory` | Reactor Netty HttpClient | Hệ thống đã dùng Reactor Netty và muốn share/tối ưu resources có chủ đích | Client API gọi vẫn đồng bộ; event loops/pool ownership cần rõ |
| `BufferingClientHttpRequestFactory` | Wrapper của factory khác | Có nhu cầu đọc request/response body nhiều lần | Buffer toàn bộ body trong RAM; nguy hiểm với payload lớn |
| `InterceptingClientHttpRequestFactory` | Wrapper hỗ trợ interceptors | Headers, tracing, request hooks | Không thay transport; log raw body có rủi ro |

Không nên coi các factory là những tính năng hoàn toàn tương đương: TLS/proxy/redirect/HTTP protocol, exception wrapping và connection reuse có thể khác. Khi chuyển transport, **cần regression tests** với downstream và gateway thật.

### 4.1. `SimpleClientHttpRequestFactory`

Adapter cũ nhất, dùng `HttpURLConnection`:

~~~java
SimpleClientHttpRequestFactory f =
        new SimpleClientHttpRequestFactory();
f.setConnectTimeout(Duration.ofSeconds(2));
f.setReadTimeout(Duration.ofSeconds(5));
~~~

Đây là Java fragment (imports ở tài liệu chính thức). Đơn giản nhưng không nên chọn chỉ vì nghĩ tất cả backend khác đều phức tạp không cần thiết. Trong một số môi trường, `HttpURLConnection` có hành vi không thuận lợi khi truy cập status của error response; Spring reference khuyên thử factory khác nếu gặp lỗi.

**Spring 6.1:** `setBufferRequestBody(boolean)` và `setOutputStreaming(boolean)` trên Simple factory đã deprecated/for removal vì request body **không còn buffered theo lựa chọn đó**. Đừng sao chép bài viết cũ hướng dẫn `setBufferRequestBody(false)` như tối ưu mới bắt buộc; cần đọc javadoc đúng version.

### 4.2. `JdkClientHttpRequestFactory`

Dựa trên `java.net.http.HttpClient` của JDK:

~~~java
HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .version(HttpClient.Version.HTTP_1_1)
        .build();

JdkClientHttpRequestFactory f =
        new JdkClientHttpRequestFactory(httpClient);
f.setReadTimeout(Duration.ofSeconds(3));
~~~

Ưu điểm:
- Có sẵn trong Java 17, không thêm Apache/Jetty dependency.
- HTTP/1.1 hoặc thử HTTP/2 tùy `HttpClient.Version` và server hỗ trợ.
- Reuse client cho nhiều requests, JDK quản lý connections và executors theo implementation.
- Có APIs cấu hình proxy, authenticator, SSLContext/SSLParameters đúng JDK.

**Không có nghĩa JDK HttpClient có cùng mức tùy chỉnh** cho pool per-route/max total/lease timeout như Apache HttpClient 5. Nếu cần giới hạn outbound concurrency, vẫn có thể dùng semaphore/bulkhead/application limits, nhưng chúng không tương đương chỉnh internal pool knobs.

### 4.3. `HttpComponentsClientHttpRequestFactory`

Dựa trên **Apache HttpClient 5.1+** với thư viện `org.apache.httpcomponents.client5:httpclient5`, không phải Apache HttpClient 4.x/`org.apache.http.client.HttpClient`.

~~~java
HttpComponentsClientHttpRequestFactory f =
        new HttpComponentsClientHttpRequestFactory();
f.setConnectTimeout(Duration.ofSeconds(2));
f.setConnectionRequestTimeout(Duration.ofMillis(500));
~~~

Đây là fragment. `setConnectionRequestTimeout` quan trọng khi dùng connection manager: giới hạn thời gian **chờ mượn connection** từ pool. `setConnectTimeout` giới hạn giai đoạn connect ở lớp cấu hình của request, nhưng javadoc Spring 6.1 nói rõ nó **không bao trùm toàn bộ TLS handshake/CONNECT proxy**; cần socket/TLS config riêng nếu yêu cầu timeout chặt.

**Điểm khác biệt phiên bản dễ gây lỗi biên dịch: Spring Framework 6.1 không có `HttpComponentsClientHttpRequestFactory.setReadTimeout(...)`.** API này có ở các dòng mới hơn như Spring 6.2. Với Boot 3.3.5/Framework 6.1, dùng Apache `RequestConfig.setResponseTimeout(...)` qua cấu hình underlying HttpClient.

### 4.4. `JettyClientHttpRequestFactory`

Dùng Jetty HTTP client:

~~~java
JettyClientHttpRequestFactory f =
        new JettyClientHttpRequestFactory();
~~~

Fragment này chưa xử lý lifecycle, dependencies/transport configuration. Phù hợp nếu hệ thống đã dùng Jetty client features, không phải lựa chọn mặc định cho mọi app mới. Khởi tạo nhiều Jetty clients độc lập có thể tạo nhiều worker/executor resources. Xem API 6.1, chọn factory/client bean dùng chung, đóng đúng shutdown.

### 4.5. `ReactorNettyClientRequestFactory`

Dùng Reactor Netty trong sync framework interface. Cần dependency/runtime Reactor Netty tương ứng. Có thể dùng khi ecosystem sẵn có Reactor Netty nhưng phải biết:
- Các networking resources có event loops và connection pools.
- RestClient call **vẫn blocking đối với caller**.
- Reuse resources và HTTP client lifecycle cần chiến lược nếu app tạo nhiều factories.
- Không nên chỉ thêm WebFlux starter vào Spring MVC app để chọn transport; dependency graph có thể ảnh hưởng Boot web application type hoặc auto-config. Chọn reactor-netty dependency/boot platform một cách chủ đích.

## 5. Spring RestClient chọn factory mặc định thế nào?

### 5.1. Đừng dựa vào giả định HttpURLConnection luôn là default

Tài liệu Spring Framework 6.1 cho `RestClient.Builder.requestFactory(...)` giải thích rằng khi không chỉ định factory, framework xét sự hiện diện của Apache/Jetty clients trên classpath; nếu JDK HTTP client sẵn có, sử dụng JDK client; cuối cùng mới tới simple fallback.

**Tùy ứng dụng và cách khởi tạo**, Spring Boot có thể can thiệp thêm vào auto-detection qua auto-configured builder, và classpath quyết định lựa chọn. Thêm một thư viện HTTP qua một dependency transitively có thể làm backend mặc định thay đổi mà bạn không sửa một dòng HTTP call nào.

Vì vậy, với service yêu cầu timeout/pooling/TLS behavior cụ thể:
- Dùng explicit `requestFactory(factory)` khi muốn đảm bảo loại transport.
- Không suy từ request vẫn 200 rằng connection policy không thay.
- Kiểm dependency tree trước/sau khi thêm starter/library.
- Viết integration tests timeout/redirect/proxy và quan sát connection pools ở staging.

### 5.2. Boot 3.3 khác các Boot phiên bản mới hơn

Spring Boot 3.3 có `RestClient.Builder` và `RestTemplateBuilder` auto-configurations. Các Spring Boot docs “current” hoặc Boot 3.4+/4.x có thể đổi package/import của builder, property tên mới hoặc cách chọn HTTP client. **Đừng chép `spring.http.clients.imperative.factory` hay Spring Boot 4 builder imports vào ứng dụng Boot 3.3.5 mà không kiểm version.**

Trong demo, ta dùng `RestClient.Builder` do Boot cung cấp nhưng **gắn explicit JDK factory**, tránh phụ thuộc auto-detection. Nếu muốn dùng `RestTemplateBuilder` của Boot 3.3, package đúng là `org.springframework.boot.web.client.RestTemplateBuilder`, không phải package mới của Boot 4.

## 6. Điều gì khiến một HTTP backend phù hợp?

Không có một HTTP client library luôn tối ưu cho mọi ứng dụng. Hãy quyết định bằng **yêu cầu thực tế**:

| Yêu cầu | Câu hỏi chọn transport |
| --- | --- |
| Dễ đóng gói | Java 17/JDK client đã đủ tính năng chưa? |
| Outbound concurrency lớn | Cần max total, per-route pools, lease timeout, queue depth không? |
| HTTP/2 | Client/server/proxy có thương lượng HTTP/2 và fallback đúng không? |
| Enterprise proxies | Có HTTP CONNECT proxy, custom authentication, allowlists không? |
| TLS/mTLS | Có cần client certificate, custom trust bundle, hostname verification? |
| Latency limits | Có bao phủ connect, TLS, pool wait, first-byte/read và overall deadline? |
| Redirect | Có được phép follow redirects? Có nguy cơ rời trusted origin không? |
| Payload lớn | Có streaming upload/download thực sự, không buffer vô hạn? |
| Observability | Có metrics active/idle/pending connections, TLS errors, status/latency không? |
| Operation | Pool đóng đúng lifecycle, hỗ trợ keep-alive/idle eviction, DNS rotation không? |
| Dependencies | Security patches, CVEs, compatibility và BOM được quản lý không? |
| Team | Debug/tooling hiện có phù hợp Apache, JDK, Jetty hay Reactor Netty? |

### 6.1. Trường hợp nên bắt đầu bằng JDK HttpClient

- Service có outbound requests ở mức vừa phải.
- Java 17 đã là baseline.
- Không cần tuning phức tạp của connection manager.
- Muốn giảm third-party dependency.
- Muốn rõ explicit redirect policy và JDK SSL configuration.
- Có integration tests chứng minh TLS/proxy/timeouts đủ dùng.

JDK client không đồng nghĩa “không có pooling” — nó có cơ chế connection reuse nội bộ, nhưng pool controls khác Apache. Không tạo một `HttpClient` mới cho mỗi request.

### 6.2. Trường hợp Apache HttpClient 5 đáng cân nhắc

- Đa dạng downstream hosts và concurrency cao.
- Cần max connections/per-route và connection leasing timeout.
- Cần custom proxy route planner, authentication hoặc TLS/socket controls.
- Muốn kiểm tra pool saturation/eviction bằng Apache manager APIs.
- Hệ thống đã chuẩn hóa HttpClient 5.

Đổi sang Apache không tự nâng throughput nếu bottleneck là downstream 429, database hoặc giới hạn server. Tăng pool total không được phép vượt rate limit của partner API.

### 6.3. Có khi nên dùng Spring MVC thay vì WebFlux

Nếu ứng dụng chủ yếu là JDBC/JPA + RestClient sync, Spring MVC blocking request model có thể phù hợp. Dùng WebFlux nhưng bọc gần như toàn bộ operations vào boundedElastic sẽ thêm complexity mà không chắc có lợi. Chọn stack dựa trên dependencies và concurrency thực, không theo tên framework.

## 7. Những giai đoạn timeout khác nhau

Một “timeout 3 giây” nghe đơn giản nhưng có thể ứng với các giai đoạn:

~~~text
time -->
[DNS lookup] [pool wait] [TCP connect] [TLS handshake]
                                  [send body] [wait response header]
                                             [read response body]
|------------------------- overall request deadline -------------|
~~~

| Timeout/budget | Giai đoạn | Ví dụ cách cấu hình |
| --- | --- | --- |
| Pool acquire / connection request | Chờ connection từ pool | Apache `setConnectionRequestTimeout` |
| Connect | Kết nối TCP | JDK `HttpClient.Builder.connectTimeout` hoặc Simple `setConnectTimeout` |
| TLS handshake | Thương lượng TLS | Client/socket-specific SSL settings |
| Response/read | Chờ response/đọc dữ liệu | JDK factory `setReadTimeout`; Apache 5 `RequestConfig.responseTimeout` |
| Whole-call deadline | End-to-end operation | Policy bên ngoài HTTP factory, deadline/cancellation tùy API |
| Caller's deadline | Thời gian caller sẵn sàng chờ | Request SLA/gateway timeout, thread budget |

**Không cộng/trừ các giá trị tùy tiện rồi gọi chúng là toàn bộ end-to-end SLA.** DNS lookup và TLS handshake có thể có semantics riêng; JDK/Apache/Jetty không hoàn toàn giống nhau.

### 7.1. Connect timeout

Khi downstream host không phản hồi TCP handshake, connect timeout giảm khả năng giữ thread mãi. Nhưng:
- DNS lookup có thể dùng cơ chế resolver riêng.
- Connection reuse có thể bỏ qua TCP connect mới.
- TLS handshake là giai đoạn khác.
- Proxy CONNECT có thể thêm một tầng kết nối.

### 7.2. Connection request timeout ở Apache

Nếu pool giới hạn max 20 connections per route, request thứ 21 có thể phải chờ. `setConnectionRequestTimeout(Duration.ofMillis(500))` kiểm thời gian chờ **lấy connection từ pool**, không phải network read timeout và không làm server phản hồi nhanh hơn.

Khi ứng dụng có 100 server threads và Apache pool 10 connections:
- 10 requests có thể đang dùng connections.
- 90 threads còn lại có thể đợi pool acquire và chiếm servlet worker.
- Nếu không có acquire timeout và queue budget, một đợt downstream chậm kéo theo server thread exhaustion.

Pool cần được dimension theo concurrency, latency, downstream quotas và backpressure/admission control; không cứ nâng lên 1.000 connections là tốt.

### 7.3. Response timeout khác deadline tổng

Apache `RequestConfig` có response timeout. JDK factory `setReadTimeout` có semantics gắn với underlying `HttpRequest.Builder.timeout` theo Javadoc Spring. Các cơ chế này không nhất thiết đồng nghĩa socket SO_TIMEOUT cho từng read byte, và cần kiểm thực nghiệm trên streaming/slow-body endpoints.

Nếu business deadline bắt buộc 2 s, nên dùng client support end-to-end timeout/deadline phù hợp, operation-level cancellation hoặc pool/driver/proxy policy; kiểm DNS, connect, headers và body chứ không chỉ gọi `setReadTimeout(2s)` rồi coi là tuyệt đối.

### 7.4. Giá trị 0 không phải luôn "tắt timeout an toàn"

Một số APIs dùng 0 = infinite timeout; timeout defaults có thể từ JVM/system/client. Một deadline vô hạn gây thread starvation khi downstream treo. Trong production, luôn có time budget được phê duyệt, deadline propagation và circuit breaker/rate limit theo đường gọi.

## 8. Vòng đời connections và pooling

### 8.1. Reuse một client/factory dài hạn

**Không tạo RestClient+HttpClient trong mỗi request handler**:

~~~java
@GetMapping("/orders/{id}")
Order bad(@PathVariable long id) {
    HttpClient newHttpClient = HttpClient.newHttpClient();
    RestClient newRestClient = RestClient.builder()
            .requestFactory(
                    new JdkClientHttpRequestFactory(newHttpClient))
            .build();

    return newRestClient.get()
            .uri("https://trusted.example.test/orders/{id}", id)
            .retrieve()
            .body(Order.class);
}
~~~

Đây là **anti-pattern**: tạo object/client resources liên tục, giảm reuse connections/executors, làm metrics và shutdown khó hơn. Sample còn thiếu method/class context và không phải runnable hoàn chỉnh.

Đúng hơn là inject singleton `RestClient` (hoặc typed Gateway) với configured request factory. Không có nghĩa một RestClient dùng cho mọi downstream cần cùng auth/timeouts; có thể tạo **một RestClient bean per upstream service** khi requirements khác nhau.

### 8.2. Apache pool lifecycle

Apache `CloseableHttpClient` và `PoolingHttpClientConnectionManager` cần được đóng/evicted theo owner. Spring `HttpComponentsClientHttpRequestFactory` implement `DisposableBean` ở 6.1 và có thể đóng underlying client khi factory được destroy; **đừng vô ý để nhiều factories đồng sở hữu cùng một Apache client rồi mỗi factory cùng close nó ở thời điểm khó dự đoán**.

Nếu bạn tạo manager/client riêng để inject nơi khác, xác định ai có quyền đóng; tránh double-shutdown của shared pools. Không để test case trước đóng một client singleton khiến test sau không còn connection.

### 8.3. Keep-alive và idle connections

Connection reuse giảm TCP/TLS setup overhead, nhưng có trade-offs:
- Server/load balancer có thể đóng idle connections.
- DNS IP thay đổi có thể tương tác với keep-alive.
- TLS certificates/rotation và proxy config thay đổi cần test.
- Pool stale connection retry có thể xảy ra; không tự retry operations không idempotent.
- Connection max life/idle eviction cần phù hợp infrastructure.

### 8.4. Chỉ có 1 factory không có nghĩa chỉ 1 connection

Một singleton factory có thể quản lý nhiều pooled connections. Tài nguyên cần đo là **connections active/idle, pending acquires, request latency**, không đếm factory objects và suy ra “chỉ có 1 TCP socket”.

## 9. HTTP status, lỗi mạng và RestClient

### 9.1. Network failure khác HTTP 4xx/5xx

- **HTTP 404**: server đã trả HTTP response; đây là application/protocol response, không mặc định là TCP failure.
- **HTTP 503/429**: downstream báo quá tải/chính sách, có thể cần backoff theo Retry-After.
- **Connection refused/reset, DNS failure, TLS handshake failure**: không nhận response HTTP hợp lệ.
- **Read timeout**: client chờ quá giới hạn được cấu hình; không phải bằng chứng server chưa thực hiện tác dụng của POST.

Trong `RestClient.retrieve()`, Spring mặc định ánh xạ status lỗi HTTP (4xx/5xx) thành nhóm exception tương ứng. Nếu muốn một gateway/domain mapping khác, dùng `onStatus(...)` hoặc `exchange(...)` và trả response hợp đồng của chính ứng dụng, không catch Throwable rồi coi mọi thứ là 404.

### 9.2. Ví dụ xử lý 404 ở gateway

~~~java
public Optional<Order> maybeGet(URI uri) {
    try {
        Order order = restClient.get()
                .uri(uri)
                .retrieve()
                .body(Order.class);
        return Optional.ofNullable(order);
    } catch (HttpClientErrorException.NotFound notFound) {
        return Optional.empty();
    }
}
~~~

Đây là method fragment trong class có `RestClient restClient`; `HttpClientErrorException.NotFound` thuộc `org.springframework.web.client`. Chỉ bắt 404; không nuốt 401/403/429/500, connect timeout, JSON decode error hay SSL error thành Optional.empty.

### 9.3. Đóng response khi dùng `exchange` raw

Khi dùng low-level `ClientHttpRequest.execute()`, đóng response đúng cách để trả pooled connection và tránh leak. Với `RestClient.exchange(...)`, framework quản lý execution callback/closing theo contract, nhưng **đừng giữ raw InputStream/response body sau khi callback đã kết thúc** rồi kỳ vọng đọc tiếp.

~~~java
int status = restClient.get()
        .uri(uri)
        .exchange((request, response) ->
                response.getStatusCode().value());
~~~

Fragment này chỉ đọc status và không giữ reference của response object ngoài callback; khác `retrieve()`, `exchange()` không tự áp status handlers theo cùng cách, nên bạn phải tự xác định status interpretation.

## 10. Bảo mật khi chọn HTTP transport

### 10.1. SSRF (Server-Side Request Forgery)

Sai:

~~~java
@GetMapping("/proxy")
String unsafe(@RequestParam String url) {
    return restClient.get()
            .uri(url)
            .retrieve()
            .body(String.class);
}
~~~

**Không bao giờ** để người dùng chỉ định URL tùy ý rồi server gọi trực tiếp nếu không có SSRF protections. User có thể nhắm tới loopback, cloud metadata IP, internal control plane, DNS rebinding hoặc redirect sang private destination.

Đúng hơn:
- Base URL cố định được lấy từ trusted server config.
- Path/ID được encode qua URI template.
- Allowlist schemes/host/port và DNS/redirect policy nếu phải cho dynamic destinations.
- Network egress/firewall chặn private/internal endpoints không được phép.
- Không follow redirects không kiểm soát tới origins khác.
- Test resolution và effective destination, kể cả IPv6, punycode và redirects.

Việc `RestClient` tự encode URI không tự là SSRF protection; encoding chỉ xử lý syntax.

### 10.2. TLS verification không được tắt

Khi chọn JDK/Apache/Jetty, giữ CA trust validation và hostname verification. Các snippets “trust-all SSLContext” hoặc `NoopHostnameVerifier` có thể khiến credentials rò rỉ qua MITM; không triển khai chúng ở production, kể cả “tạm thời để fix handshake”. Với mTLS, dùng client certificate/keystore hoặc Spring Boot SSL bundles (theo version) và test rotation/expiry.

### 10.3. Không log Authorization hoặc raw body

Interceptors/logging có thể quan sát headers và request/response bodies. Tránh:
- Log `Authorization`, `Cookie`, `Set-Cookie`, API keys.
- Dump raw request body chứa passwords, cards, tokens hoặc PII.
- Đặt unbounded user IDs/URLs thành metric labels.
- Giữ raw response bodies trong memory để debug quá lâu.

Ưu tiên logging method, trusted host, path template, status, elapsed, bytes/size và trace IDs đã được kiểm soát.

### 10.4. Redirect policy và credentials

JDK `HttpClient.Redirect.NEVER` là một default có chủ đích trong demo. Redirect có thể đi tới host khác hoặc đổi method theo HTTP status/client implementation. Nếu bật followRedirects:
- Kiểm trusted destinations và không rò Authorization khi đổi origin.
- Cẩn thận 301/302/303 vs 307/308 cho POST.
- Đặt giới hạn redirect hop và tối đa response size.
- Không retry side-effect POST mù quáng.

### 10.5. Proxy authentication và trust boundary

Enterprise proxy có thể yêu cầu authentication, TLS interception hoặc mTLS. Dùng APIs của JDK/Apache để cấu hình proxy có kiểm soát; không nhúng password vào HTTP URI hoặc source code. Xác định cả proxy connect timeout, CONNECT/TLS handshake và certificate trust chain.

## 11. Ví dụ chạy được: RestClient + explicit JDK factory

Ứng dụng Spring Boot nhỏ có:
- Một **HTTP endpoint địa phương** `GET /downstream/orders/{id}` trả JSON đơn hàng hoặc 404.
- Một bean `ClientHttpRequestFactory` lựa chọn **JdkClientHttpRequestFactory** và JDK `HttpClient`.
- Một bean `RestClient` sử dụng chính factory đó, không phụ thuộc classpath auto-detection.
- Một `OrderGateway` để API nghiệp vụ không phụ thuộc transport implementation.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` tạo HTTP server thật và tests dùng `@LocalServerPort` để client gọi vào local test server.
- JUnit tests xác minh 200/404, HTTP factory bean và URI/template đúng; không cần Internet.

**Vì tests dùng random port**, chúng không dựa trên cổng 8080 cứng. Demo chạy được nếu có Java 17, Gradle 8.x tương thích và dependencies tải được từ Maven Central. Các file dưới đây không bao gồm scripts Gradle wrapper; tạo wrapper nếu repository chưa có.

~~~text
http-factory-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/httpfactory/
    │   ├── HttpFactoryApplication.java
    │   ├── config/HttpClientConfig.java
    │   ├── domain/Order.java
    │   ├── gateway/OrderGateway.java
    │   └── web/DownstreamDemoController.java
    └── test/java/com/example/httpfactory/
        └── HttpFactoryIntegrationTest.java
~~~

### 11.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'http-factory-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` ở đây chỉ dựng một **HTTP test server bằng Spring MVC/Tomcat**. Điều đó hoàn toàn phù hợp với client **đồng bộ** `RestClient`; không cần WebFlux dependency.

### 11.2. Main application

`src/main/java/com/example/httpfactory/HttpFactoryApplication.java`:

~~~java
package com.example.httpfactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpFactoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpFactoryApplication.class, args);
    }
}
~~~

### 11.3. Order DTO

`src/main/java/com/example/httpfactory/domain/Order.java`:

~~~java
package com.example.httpfactory.domain;

public record Order(long id, String state) {}
~~~

Record Java 17 được Jackson Spring Boot mặc định encode/decode thành JSON. `state` là chuỗi để ví dụ dễ hiểu; hệ sản xuất có thể chọn enum/validation theo hợp đồng riêng.

### 11.4. HTTP factory được xác định tường minh

`src/main/java/com/example/httpfactory/config/HttpClientConfig.java`:

~~~java
package com.example.httpfactory.config;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfig {

    @Bean
    public ClientHttpRequestFactory orderRequestFactory() {
        HttpClient jdkClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(Duration.ofSeconds(3));
        return factory;
    }

    @Bean
    public RestClient orderRestClient(
            RestClient.Builder builder,
            ClientHttpRequestFactory orderRequestFactory) {

        return builder
                .requestFactory(orderRequestFactory)
                .build();
    }
}
~~~

Giải thích:
1. `@Bean ClientHttpRequestFactory` là một singleton trong Spring context.
2. HTTP engine underlying được tạo từ `java.net.http.HttpClient` của JDK 17.
3. Connect timeout 2 s và read/request timeout 3 s là **hai knobs khác nhau**, không phải global 5-second SLA.
4. `Redirect.NEVER` tránh tự follow redirects trong demo; ứng dụng sẽ có thể nhận 3xx status hoặc xử lý theo policy của `RestClient`.
5. HTTP/1.1 được chọn để test đơn giản với embedded Tomcat. Nếu thử HTTP/2, cần cả server/proxy/TLS support và regression tests.
6. `RestClient.Builder` được Boot cung cấp; gọi `requestFactory` explicit để giữ transport nhất quán dù classpath có thêm Apache/Jetty.
7. Dùng bean RestClient để tái sử dụng configuration/HTTP resources, không tạo trong mỗi handler method.

**Lưu ý:** Nếu dự án có nhiều `ClientHttpRequestFactory` beans, hãy dùng `@Qualifier("orderRequestFactory")` ở injection point để tránh ambiguity. Demo chỉ có một factory, nên Spring inject trực tiếp được.

### 11.5. Gateway bọc HTTP API

`src/main/java/com/example/httpfactory/gateway/OrderGateway.java`:

~~~java
package com.example.httpfactory.gateway;

import com.example.httpfactory.domain.Order;
import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OrderGateway {

    private final RestClient client;

    public OrderGateway(RestClient orderRestClient) {
        this.client = orderRestClient;
    }

    public Order fetch(URI trustedResourceUri) {
        return client.get()
                .uri(trustedResourceUri)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Order.class);
    }
}
~~~

Tên `trustedResourceUri` nhấn mạnh **giá trị phải đến từ application configuration hoặc code đáng tin**, không truyền raw `?url=...` do người dùng nhập. Trong demo, test tạo URI từ `localhost/random port` do embedded server cấp, nên không có chức năng SSRF public.

Trong production:
- Inject cấu hình trusted `baseUrl` vào Gateway và chỉ nhận business ID.
- Dùng `uri("/orders/{id}", id)` để encode path variable.
- Quy định 404/401/429/5xx mapping, timeouts và retries ở gateway/domain layer.
- Không coi `OrderGateway.fetch` là một method non-blocking: thread gọi sẽ chờ response.

### 11.6. HTTP server endpoint để test transport

`src/main/java/com/example/httpfactory/web/DownstreamDemoController.java`:

~~~java
package com.example.httpfactory.web;

import com.example.httpfactory.domain.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/downstream/orders")
public class DownstreamDemoController {

    @GetMapping("/{id}")
    public ResponseEntity<Order> find(@PathVariable long id) {
        if (id == 1L) {
            return ResponseEntity.ok(new Order(1L, "CONFIRMED"));
        }
        return ResponseEntity.notFound().build();
    }
}
~~~

Local downstream server phản hồi:
- `GET /downstream/orders/1` → 200 + JSON `{"id":1,"state":"CONFIRMED"}`.
- `GET /downstream/orders/999` → 404, không có JSON Order.
- Không có database, authentication hay external service.

Không phải production design để một app gọi HTTP vào chính nó; **đây là test fixture tiện chạy thật qua network stack** và kiểm request factory trên loopback. Ứng dụng thật gọi downstream service khác theo domain/trust boundary.

### 11.7. Integration tests trên local port

`src/test/java/com/example/httpfactory/HttpFactoryIntegrationTest.java`:

~~~java
package com.example.httpfactory;

import com.example.httpfactory.domain.Order;
import com.example.httpfactory.gateway.OrderGateway;
import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.HttpClientErrorException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpFactoryIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    OrderGateway gateway;

    @Autowired
    ClientHttpRequestFactory factory;

    URI url(long id) {
        return URI.create(
                "http://127.0.0.1:" + port + "/downstream/orders/" + id);
    }

    @Test
    void usesExplicitJdkRequestFactory() {
        assertInstanceOf(JdkClientHttpRequestFactory.class, factory);
    }

    @Test
    void convertsResponseToOrderRecord() {
        Order result = gateway.fetch(url(1L));
        assertEquals(1L, result.id());
        assertEquals("CONFIRMED", result.state());
    }

    @Test
    void mapsHttp404ToRestClientException() {
        assertThrows(HttpClientErrorException.NotFound.class,
                () -> gateway.fetch(url(999L)));
    }
}
~~~

**Tests thực sự kiểm gì?**
- Test 1 xác nhận bean request factory type do cấu hình explicit cung cấp.
- Test 2 chứng minh JDK factory gửi HTTP thật, nhận 200 và JSON converter tạo `Order`.
- Test 3 chứng minh `RestClient.retrieve()` xử lý 404 theo mặc định thành `HttpClientErrorException.NotFound` thay vì trả Order null.
- Server dùng random port để tránh conflict với service địa phương.
- Không cần Internet hay credentials; host là 127.0.0.1 từ test, không bị lấy từ user input.
- Chưa có test timeout, TLS/mTLS, proxy, connection pool saturation hoặc HTTP/2: phải bổ sung riêng theo deployment thật.
- Test không đo QPS, latency p99 hoặc độ hiệu quả pooling.

### 11.8. Chạy project

Ở thư mục có Gradle wrapper phù hợp:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Với server chạy default port 8080, thử:

~~~bash
curl -i 'http://localhost:8080/downstream/orders/1'
curl -i 'http://localhost:8080/downstream/orders/999'
~~~

Dự kiến (response 200):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"state":"CONFIRMED"}
~~~

Response 404 dự kiến:

~~~http
HTTP/1.1 404 Not Found
~~~

Headers như Date, Content-Length, transfer-encoding, charset có thể khác theo server; test xác nhận status/JSON, không assert byte-for-byte toàn bộ raw HTTP headers. Lệnh curl gọi server fixture, còn JUnit kiểm **RestClient gọi chính fixture này qua JDK request factory**.

## 12. Tùy chọn Apache HttpClient 5 khi cần connection pool

Đây là **một lựa chọn thay thế**, không đặt cùng vào project demo JDK ở mục 11 trừ khi bạn chủ động chuyển cấu hình.

### 12.1. Thêm dependency đúng thế hệ

Trong Gradle (Spring Boot 3.3 quản lý version qua BOM):

~~~groovy
dependencies {
    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
~~~

Nếu dependency tree đã có Apache HttpClient 4, **đừng** cố inject `org.apache.http.client.HttpClient` vào Spring 6 `HttpComponentsClientHttpRequestFactory`; class này yêu cầu Apache HttpClient **5.1+**.

### 12.2. Cấu hình pool + response timeout đúng Spring 6.1

~~~java
import java.time.Duration;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;

public final class ApacheFactoryExample {

    public static ClientHttpRequestFactory create() {
        var manager = PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(60)
                .setMaxConnPerRoute(20)
                .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofMilliseconds(500))
                .setResponseTimeout(Timeout.ofSeconds(3))
                .build();

        CloseableHttpClient client = HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .disableRedirectHandling()
                .build();

        HttpComponentsClientHttpRequestFactory factory =
                new HttpComponentsClientHttpRequestFactory(client);
        factory.setConnectTimeout(Duration.ofSeconds(2));
        return factory;
    }
}
~~~

Đây là class Java 17 dùng Apache HttpClient 5 APIs tương ứng Spring 6.1. Để Spring quản lý lifecycle, tạo factory trong một `@Bean` và để context destroy; đừng tạo class/factory mới mỗi HTTP request. Nếu được thiết kế ownership khác, bảo đảm `CloseableHttpClient.close()` và connection manager giải phóng đúng một lần.

**Vì sao có ba timeout/limit khác nhau?**
1. `MaxConnTotal(60)`: trần connections của pool (demo).
2. `MaxConnPerRoute(20)`: trần theo route.
3. `ConnectionRequestTimeout(500ms)`: chờ mượn connection.
4. `ResponseTimeout(3s)`: chờ response theo Apache config.
5. `ConnectTimeout(2s)`: giới hạn TCP connect theo Spring factory.

Số trên là **demo**, không phải defaults hay thông số production khuyến nghị. TCP connect/TLS handshake/proxy còn phải kiểm theo client implementation; Spring 6.1 `setConnectTimeout` có giới hạn phạm vi.

### 12.3. Tại sao không dùng `factory.setReadTimeout`?

Ở **Spring Framework 6.1**, `HttpComponentsClientHttpRequestFactory` không có method đó. Đoạn:

~~~java
factory.setReadTimeout(Duration.ofSeconds(3));
~~~

là **ví dụ sai** nếu `factory` có kiểu `HttpComponentsClientHttpRequestFactory` trên Framework 6.1. Phải cấu hình response timeout trên Apache `RequestConfig` như đoạn code trước. JDK `JdkClientHttpRequestFactory` và Simple `SimpleClientHttpRequestFactory` lại có `setReadTimeout` trong 6.1. Không suy từ tên gần giống rằng mọi request factories có bộ setters chung.

### 12.4. Pool sizing theo Little's Law

Giả sử một downstream trung bình mất 200 ms, cần 100 calls/s sustained. Số in-flight requests trung bình theo Little's Law vào khoảng **100 × 0,2 = 20** (với hệ ổn định, chưa xét queue và tails). Nếu per-route max 10, requests có thể xếp hàng ngay cả khi server có nhiều worker threads.

Tuy nhiên dùng pool 20 là **không đủ kết luận thiết kế**: p95/p99 response times, retries, burst, tenant quotas, downstream max connections và TLS overhead đều cần headroom/limits. Benchmark trên workload thật và quan sát pool pending/acquire wait thay vì chỉ đếm peak QPS.

## 13. RestTemplate cũng dùng factory, nhưng API khác RestClient

Trong Spring Boot 3.3, có thể cấu hình RestTemplate:

~~~java
@Bean
RestTemplate customRestTemplate(
        ClientHttpRequestFactory factory) {

    return new RestTemplate(factory);
}
~~~

Hoặc dùng Boot 3.3 `RestTemplateBuilder` để tận dụng customizers/converters:

~~~java
@Bean
RestTemplate customRestTemplate(RestTemplateBuilder builder) {
    return builder
            .requestFactory(JdkClientHttpRequestFactory.class)
            .build();
}
~~~

Đây là fragments trong `@Configuration` với các imports. Chú ý `RestTemplateBuilder.requestFactory(Class<? extends ClientHttpRequestFactory>)` yêu cầu factory có constructor phù hợp; nếu cần JDK `HttpClient` cấu hình tùy biến và timeout cụ thể, dùng supplier/function hoặc explicit factory bean phù hợp.

**Không tự thay toàn bộ RestTemplateBuilder bean** nếu muốn giữ Boot auto-configuration/customizers đang áp dụng. Khi cung cấp builder custom, cần `RestTemplateBuilderConfigurer` đúng Boot 3.3 để giữ thiết lập của Boot, hoặc đơn giản inject builder do Boot cung cấp.

### 13.1. Migration RestTemplate → RestClient

Một chiến lược:
1. Ghi lại timeout, proxy, TLS, redirects, default headers, interceptors, auth và error mapping hiện hữu.
2. Giữ cùng factory/client backend khi chuyển syntax để cô lập rủi ro.
3. So contract với tests 200/4xx/5xx, JSON, content type, malformed body.
4. Xác minh `RestClient.retrieve()` default error mapping khác các wrappers/custom ResponseErrorHandler cũ như thế nào.
5. Sau đó mới thay transport nếu có lý do: performance, pooling, TLS, HTTP/2, proxy.
6. Đo latency/pool/retries trên staging, dùng feature flag/rollout nếu call path trọng yếu.

### 13.2. Tránh cấu hình bị lặp giữa các clients

Có thể dùng một @Configuration quản lý shared HTTP factory settings cho nhiều RestClients, nhưng đừng ép mọi downstream dùng cùng trust store, connection pool, proxy hoặc retry budget. Client cho payment API và client cho public metadata API có thể cần security/timeouts khác nhau.

## 14. Interceptors, request initializers và request factory wrappers

### 14.1. Gắn header/correlation đúng chỗ

~~~java
RestClient client = RestClient.builder()
        .requestFactory(factory)
        .defaultHeader("X-App-Client", "catalog")
        .requestInterceptor((request, body, execution) -> {
            long started = System.nanoTime();
            try {
                return execution.execute(request, body);
            } finally {
                long nanos = System.nanoTime() - started;
                // Export metric với low-cardinality labels.
            }
        })
        .build();
~~~

Đây là fragment có `factory`. Interceptor chạy quanh HTTP execution, có thể quan sát call duration. Không ghi request body bằng mặc định; body trong interceptor có thể là byte[] toàn payload, rủi ro memory/privacy.

### 14.2. BufferingClientHttpRequestFactory

Spring có wrapper:

~~~java
ClientHttpRequestFactory buffering =
        new BufferingClientHttpRequestFactory(factory);
~~~

Nó cho phép lưu request/response streams trong bộ nhớ để có thể đọc lại theo use case. **Tuy nhiên buffering mọi payload** rất nguy hiểm với downloads/uploads lớn và PII. Chỉ bật cho workloads bounded, hoặc tránh entirely bằng metadata-only tracing. Không nghĩ rằng Buffering factory tự giải quyết body streaming/backpressure.

### 14.3. Ghi trace ID nhưng không tin header raw

Nếu lấy correlation ID từ inbound request, validate format/length và sanitize trước khi forward. Không forward Authorization token của user sang một arbitrary URL hoặc redirect target; dùng service-to-service credentials/scopes đúng domain. Với Micrometer/OpenTelemetry, tận dụng integrations và propagation policy thay vì copy mọi headers indiscriminately.

## 15. Request body lớn, streaming và memory pressure

### 15.1. Synchronous không đồng nghĩa luôn buffer

Spring 6.1 đã thay đổi cách buffering request bodies trong nhiều factories. Một `RestClient` call có thể stream bytes tới transport, nhưng:
- `HttpMessageConverter` có thể tự tạo byte[]/String trước khi gửi.
- Interceptors có thể nhận entire serialized byte[].
- Buffering factory có thể lưu request/response body.
- HTTP client backend có buffering/flow control của riêng nó.
- `body(InputStream)` không tự là API streaming chuẩn cho mọi Spring converter.

Nếu cần stream một tệp rất lớn:
1. Chọn factory backend hỗ trợ streaming thực tế.
2. Dùng body writer/input stream/resource API tương thích.
3. Không log/buffer toàn body.
4. Giới hạn request/response bytes, timeouts và disk/memory quotas.
5. Đóng resource kể cả error/cancel.
6. Test với file kích thước thực và server phản hồi chậm.

### 15.2. Synchronous response stream chiếm thread

Đọc một download nhiều GB bằng `RestClient` có thể giữ thread caller trong toàn bộ thời gian đọc. Không nhầm “streaming network bytes” với “non-blocking API”; connection pooling và worker threads vẫn cần dimension. Nếu nhu cầu là fan-out/thousands concurrent downloads, cân nhắc reactive WebClient hoặc async JDK HttpClient với architecture phù hợp.

## 16. Diagnostics: xác định transport và lỗi thực tế

### 16.1. Đừng suy từ dependency tree rằng factory đúng đã được sử dụng

Classpath là một dấu hiệu, không phải bằng chứng; client bean có thể explicitly set khác default. Hãy:
- Kiểm cấu hình bean `requestFactory` của từng RestClient.
- Log loại factory **không chứa secrets** khi khởi động ở môi trường debug.
- Với Apache, đo pool stats (leased, available, pending).
- Với JDK, dùng metrics/tracing ở cấp application và JDK HTTP client logs khi cần (tránh bật body).
- Test redirect/timeout/proxy và TLS thực thay vì chỉ ping HTTP 200.

### 16.2. Spring exception mapping

Một số exception layers:
- `RestClientException`: Spring HTTP client abstraction.
- `RestClientResponseException`: có HTTP error response/status/body.
- `ResourceAccessException`: thường lỗi I/O/transport.
- `HttpClientErrorException`, `HttpServerErrorException`: nhóm lỗi 4xx/5xx từ `retrieve()`.
- Underlying `IOException`/`SocketTimeoutException`/TLS exceptions có thể nằm trong cause chain.

Không rely vào exact exception message theo JDK version. Error handling cần phân loại **retryable vs non-retryable** dựa trên method, status, idempotency và nguyên nhân mạng.

### 16.3. Timeout và retry thường phối hợp sai

Một retry policy có tối đa 3 attempts, mỗi attempt timeout 2 s cộng backoff 1 s có thể vượt HTTP request SLA 3 s. Cần:
- Overall deadline và per-attempt limits.
- Retry only transient failures và HTTP methods/safety phù hợp.
- Exponential backoff + jitter; theo `Retry-After` khi có.
- Circuit breaker, bulkhead, rate limiter.
- Budget cho caller thread và downstream request quotas.
- Correlation IDs/idempotency keys cho POST commands.

Client timeout không chứng minh downstream chưa xử lý request trước khi connection đứt. Với POST có side effects, retry cần idempotency contract hoặc status reconciliation.

### 16.4. Kiểm status 401/403 khi dùng Simple factory

Nếu khi chuyển từ JDK/Apache sang Simple factory nhận exception bất thường ở `HttpURLConnection` error status, kiểm Spring reference note về hành vi Simple implementation. Không chữa bằng cách vô hiệu hóa HTTP error checking hoặc trả default 200; chọn factory phù hợp và có regression test error statuses.

## 17. Các lỗi phổ biến và hướng sửa

| Lỗi / nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “RestClient luôn dùng HttpURLConnection” | Backend chọn theo classpath/builder | Gắn explicit `requestFactory` |
| “Reactor Netty factory giúp RestClient non-blocking” | RestClient là synchronous API | Dùng `WebClient` nếu cần reactive |
| Copy Spring 6.2 Apache `setReadTimeout` sang 6.1 | API chưa tồn tại | Apache 5 `RequestConfig.responseTimeout` |
| Dùng Apache HttpClient 4 với Spring 6 factory | Spring 6 yêu cầu 5.1+ | `httpclient5` và đúng imports |
| Chỉ đặt connect timeout | Không chặn read/pool wait vô hạn | Phân tầng timeouts |
| Timeout 0 ở mọi client | Có thể là infinite | Đặt budget/deadline rõ |
| Tạo HttpClient mỗi HTTP request | Mất connection reuse, resources nhiều | Reuse singleton beans |
| Pool max 500 cho downstream giới hạn 10 | Tăng overload phía đối tác | Align quotas, admission, pool sizing |
| Client 404 bị coi là socket failure | Status là HTTP response, không network error | Mapping 4xx/5xx riêng |
| Catch RuntimeException rồi trả empty Order | Giấu auth/timeout/5xx/bug | Typed status/error policy |
| Bật follow redirect mọi URL | Rủi ro SSRF/credential leak | Trusted destination checks |
| Tắt SSL hostname verification | Nguy cơ MITM | Trust chain đúng, mTLS/certs |
| Dùng user-supplied URL trực tiếp | SSRF | Fixed base URL, allowlist + egress controls |
| Interceptor log raw Authorization/body | Leak secrets | Redaction/metadata-only tracing |
| Buffering all responses | Heap pressure | Limit payload, avoid wrapper |
| Quên close Apache manager/client | Socket/resource leaks | Bean lifecycle/close ownership |
| Một bean factory bị nhiều owner close | Double shutdown shared resources | Single owner rõ ràng |
| Dùng RestClient trên WebFlux Netty loop | Blocking calls stall event loop | WebClient hoặc bounded worker |
| Chỉ test HTTP 200 localhost | Chưa test real TLS/proxy/timeout | Integration/load tests theo contract |
| Dùng Boot 4 property trên Boot 3.3 | Version mismatch | API/docs đúng platform |
| Suy từ error message để phân loại timeout | Message không ổn định | Exception types/root causes |
| Auto retries POST sau socket reset | Có thể duplicate side effects | Idempotency/reconciliation |

### Debug có trình tự

1. Xác nhận Java, Spring Boot, Spring Framework versions và BOM.
2. Xem đúng factory bean và underlying HTTP library dependency.
3. Xác minh RestClient/RestTemplate đã gắn factory đó, không bị builder khác override.
4. Kiểm host/port, trusted URL, DNS resolution và proxy route.
5. Kiểm connect, pool acquire, TLS, response timeouts riêng.
6. Kiểm 2xx, 4xx, 5xx và malformed JSON bằng tests.
7. Nếu có concurrency, đo threads, active/pending/idle connections, queue.
8. Kiểm interceptors không buffer/log credentials.
9. Kiểm response/stream/client lifecycle, resource cleanup.
10. Test rollout staging với egress/TLS/proxy và failure injection.

## 18. Checklist trước production

- [ ] Chọn factory dựa trên workload/feature/security chứ không chỉ default.
- [ ] Java/Spring/HTTP client dependency versions tương thích.
- [ ] Apache HttpClient đúng 5.x cho Spring 6.x.
- [ ] Kiểm Spring 6.1/6.2 API khác nhau, nhất là Apache setReadTimeout.
- [ ] RestClient/RestTemplate beans dùng reusable factory và connection resources.
- [ ] Factory lifecycle/CloseableHttpClient ownership rõ.
- [ ] Connect, pool acquire, TLS, response/read và overall deadlines có budget.
- [ ] Không dùng 0/infinite timeout không chủ đích.
- [ ] Pool limits phù hợp downstream concurrency/rate limits.
- [ ] TLS trust/hostname verification không bị tắt.
- [ ] Proxy/mTLS/redirect policies được review.
- [ ] Không gọi URL do user chỉ định mà không có SSRF defenses.
- [ ] Credentials được scope theo destination, không forward tùy ý.
- [ ] Header/body logging redacted, tránh buffering large streams.
- [ ] Typed error handling 401/403/404/429/5xx/transport failures.
- [ ] POST retries có idempotency hoặc reconciliation.
- [ ] HTTP response resources được close đúng khi dùng API thấp.
- [ ] Không gọi synchronous RestClient trên reactive event loop.
- [ ] JUnit integration test HTTP thật trên random port.
- [ ] Có tests TLS/proxy/timeouts/redirect/pooling trên infrastructure tương ứng.
- [ ] Đo p95/p99, pool pending/acquire, exceptions và outbound retries.
- [ ] Duy trì transport config & dependency security patch policy.

### Câu hỏi tự kiểm tra

**1.** `ClientHttpRequestFactory` thuộc layer nào?

**Trả lời:** Abstraction tạo executable client HTTP request của Spring, nằm dưới `RestClient`/`RestTemplate` và message conversion, trên backend transport.

**2.** Nếu chuyển từ RestTemplate sang RestClient, bắt buộc đổi HTTP library không?

**Trả lời:** Không. Có thể giữ cùng ClientHttpRequestFactory để tách rủi ro migration API khỏi migration transport.

**3.** Vì sao JDK factory phù hợp Java 17 service đơn giản?

**Trả lời:** Có sẵn `java.net.http.HttpClient`, reuse connections, SSL/proxy/redirect configuration, không cần Apache dependency nếu workload không cần pool tuning đặc thù.

**4.** Khi nào Apache HttpClient 5 có lợi?

**Trả lời:** Khi cần pooling max total/per route, lease timeout, proxy/TLS và connection management sâu với tải outbound cao.

**5.** Spring 6.1 `HttpComponentsClientHttpRequestFactory` có `setReadTimeout` không?

**Trả lời:** Không. Cấu hình `RequestConfig.setResponseTimeout` trên underlying Apache HttpClient 5; `setReadTimeout` của HttpComponents factory thuộc phiên bản mới hơn.

**6.** ConnectionRequestTimeout khác ConnectTimeout ra sao?

**Trả lời:** ConnectionRequestTimeout giới hạn thời gian chờ mượn connection từ Apache pool; ConnectTimeout giới hạn giai đoạn tạo TCP connection theo client config.

**7.** Tại sao RestClient với ReactorNettyClientRequestFactory vẫn blocking?

**Trả lời:** RestClient có synchronous caller contract; backend có thể dùng event loops nội bộ nhưng caller vẫn phải chờ kết quả.

**8.** `RestClient.retrieve()` nhận HTTP 404 thì có bắt buộc nhận DTO null không?

**Trả lời:** Không. Mặc định 4xx/5xx thường phát HTTP status exception; phải mapping rõ hoặc dùng status handler/exchange.

**9.** Có nên dùng BufferingClientHttpRequestFactory cho mọi outbound request?

**Trả lời:** Không. Nó có thể buffer toàn payload trong memory, gây OOM và lộ dữ liệu nhạy cảm nếu log.

**10.** Vì sao redirect và URL từ user nguy hiểm khi dùng HTTP client server-side?

**Trả lời:** Có thể dẫn đến SSRF vào nội bộ/cloud metadata và rò credentials sang origin ngoài; cần fixed/allowlisted destinations, egress controls và redirect policy.

## 19. Tài liệu chính thức

- [Spring Framework 6.1 — ClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/ClientHttpRequestFactory.html): interface `createRequest(URI,HttpMethod)` và implementations.
- [Spring Framework 6.1 — JdkClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): constructors, `setReadTimeout`.
- [Spring Framework 6.1 — SimpleClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): HttpURLConnection, connect/read timeout và buffering deprecation.
- [Spring Framework 6.1 — HttpComponentsClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html): Apache HttpClient 5, connect/lease timeouts và pooling.
- [Spring Framework 6.1 — JettyClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/JettyClientHttpRequestFactory.html): Jetty HttpClient adapter.
- [Spring Framework 6.1 — ReactorNettyClientRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/ReactorNettyClientRequestFactory.html): Reactor Netty adapter cho sync clients.
- [Spring Framework 6.1 — RestClient.Builder](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html): `requestFactory` và builder configuration.
- [Spring Framework 6.1 — REST Clients Reference](https://docs.spring.io/spring-framework/reference/6.1/integration/rest-clients.html): RestClient, RestTemplate, request factories và selection.
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): RestClient.Builder, RestTemplateBuilder và auto configuration.
- [Apache HttpClient 5 — Classic Client](https://hc.apache.org/httpcomponents-client-5.4.x/current/httpclient5/apidocs/): connection manager, RequestConfig, response timeout.
- [JDK 17 — java.net.http.HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP/1.1/2, SSL, redirects, proxy, connection handling.
- [Spring Framework — HTTP Client Test Utilities](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): MockRestServiceServer khi cần mock behavior; integration với server thật bổ sung transport tests.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): allowlists, DNS, redirects và network restrictions.

**Ghi nhớ:** `RestClient`/`RestTemplate` là API đồng bộ; `ClientHttpRequestFactory` chọn HTTP backend. JDK HttpClient là lựa chọn khởi đầu hợp lý trên Java 17 nếu nhu cầu đơn giản; Apache HttpClient 5 phù hợp khi cần pool/timeout/proxy/TLS tuning sâu. Đừng để transport thay đổi ngoài ý muốn theo classpath, đừng nhầm sync với non-blocking, và luôn cấu hình deadlines, lifecycle, credentials, SSRF policy, logging cùng integration tests trước khi triển khai.
