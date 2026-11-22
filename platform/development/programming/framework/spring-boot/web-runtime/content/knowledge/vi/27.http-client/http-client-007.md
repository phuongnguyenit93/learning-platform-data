# Cấu hình thời gian kết nối, đọc và chờ lấy kết nối trong HTTP client của Spring Boot

## 1. Ba loại timeout khác nhau, ba tình huống lỗi khác nhau

Một dịch vụ Spring Boot gọi HTTP API của dịch vụ khác có thể gặp các triệu chứng rất giống nhau: request “đứng” vài giây, rồi `ResourceAccessException`, `WebClientRequestException`, `SocketTimeoutException` hoặc lỗi hết thời gian chờ pool. Nếu chỉ thấy chữ **timeout** rồi tăng tất cả cấu hình lên 60 giây thì chưa xác định được vấn đề nằm ở mạng, máy chủ đối tác hay **pool kết nối của chính ứng dụng**.

Bài học này phân biệt ba loại thời gian chờ quan trọng:

1. **Connection timeout (connect timeout):** thời gian tối đa cho việc thiết lập một **kết nối mới** tới peer, thường là TCP connect. Nó không phải thời gian chờ server xử lý một request đã kết nối thành công.
2. **Read/response timeout:** thời gian chờ **phản hồi hoặc hoạt động đọc dữ liệu** sau khi đã gửi request, với semantics khác nhau tùy thư viện. Nó không mặc nhiên là deadline từ đầu đến cuối của cả lời gọi.
3. **Connection acquisition timeout (connection request/lease/pending acquire timeout):** thời gian chờ **mượn một kết nối từ connection pool** khi chưa có kết nối sẵn sàng và pool đang chạm giới hạn. Lỗi này có thể xảy ra khi server đích vẫn khỏe và kết nối TCP chưa hề được thử.

Phạm vi: **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**, hai kiểu HTTP client chính là `RestClient`/`RestTemplate` (blocking) và `WebClient` (reactive). Ví dụ chạy được sử dụng **Spring Boot 3.3.13, Java 21, Apache HttpClient 5.x**; phần WebFlux sử dụng Reactor Netty thuộc thế hệ tương thích Spring Boot 3.3. Các phiên bản mới hơn có API/property khác; khi áp dụng phải kiểm tra version thực tế.

**Sơ đồ một lời gọi với connection pool:**

```text
RestClient / WebClient gọi GET https://partner.example/api
       |
       +-- [1] Chờ pool cấp connection / connection lease
       |          -> timeout: connection-request / pending-acquire
       |
       +-- Nếu không có idle connection: DNS + TCP connect
       |          -> timeout: connect; DNS và TLS có ranh giới riêng
       |
       +-- TLS handshake nếu HTTPS + gửi HTTP request
       |
       +-- [2] Chờ response/đọc bytes
       |          -> timeout: read/response/socket
       |
       +-- Đọc/đóng response body và trả connection về pool
       |
       +-- Ứng dụng dùng kết quả, có thể qua retry/circuit breaker
```

Sơ đồ là mô hình logic. HTTP/2 có multiplexing, proxy có thể thêm kết nối trung gian, các protocol stacks khác nhau có cách triển khai riêng. **Không suy rằng `connectTimeout=2s` và `readTimeout=4s` luôn làm toàn bộ call kết thúc trong đúng 6 giây**: còn DNS, pool wait, TLS, upload body, nhiều lần đọc, retry, redirect, scheduler và queue ở tầng khác.

## 2. Ví dụ thời gian để nhìn thấy ba điểm chờ

Giả sử client có một connection pool tối đa **2 connections cho một route**, API downstream xử lý mỗi request trong khoảng 3 giây.

```text
t = 0.0s    Request A lấy connection #1, server đang xử lý
t = 0.1s    Request B lấy connection #2, server đang xử lý
t = 0.2s    Request C đến; cả hai connections đều bận
t = 1.0s    Request C vẫn chưa mượn được connection
t = 1.2s    Request C hết acquisition timeout 1s -> FAIL
t = 3.0s    Request A hoàn thành và trả connection #1 về pool
```

Request C **chưa chắc đã thử tạo TCP connection mới**, bởi pool đã đủ giới hạn. Tăng connect timeout hoặc read timeout không giải quyết được việc **không có connection rảnh**. Cần xem request concurrency, thời gian downstream giữ connection, cấu hình pool và timeout cho lease.

Một tình huống khác:

```text
t = 0.0s   Pool cấp được connection
t = 0.1s   TCP connect hoàn tất
t = 0.2s   HTTP request gửi xong
t = 4.2s   Server chưa phát response trong khi response timeout 3s
           -> FAIL ở pha chờ response/đọc
```

Khi client gọi một địa chỉ IP không phản hồi SYN hoặc mạng chặn gói TCP, **connect timeout** mới là nghi phạm chính. Nếu server lập tức trả HTTP 503/429/500, đó là **HTTP response hợp lệ với status lỗi**, không phải timeout; phải phân biệt hai nhóm trước khi chọn retry.

## 3. Bảng thuật ngữ theo các thư viện thường dùng

| Giai đoạn | Apache HttpClient 5 + Spring `RestClient` | Reactor Netty + Spring `WebClient` | Ý nghĩa |
| --- | --- | --- | --- |
| Chờ pool | `RequestConfig.setConnectionRequestTimeout(...)` | `ConnectionProvider.pendingAcquireTimeout(...)` | Chờ lease/acquire |
| Tạo TCP connection | `ConnectionConfig.setConnectTimeout(...)` hoặc phiên bản API tương ứng | `ChannelOption.CONNECT_TIMEOUT_MILLIS` | Chờ kết nối TCP mới |
| Chờ response | `RequestConfig.setResponseTimeout(...)` | `HttpClient.responseTimeout(...)` | Đợi/phát hiện response bị chậm theo semantics HTTP client |
| Socket read inactivity | `ConnectionConfig.setSocketTimeout(...)` | `ReadTimeoutHandler` khi thực sự cần | Phát hiện I/O đọc im lặng theo stack |
| Deadline toàn lời gọi | Thêm deadline ở tầng nghiệp vụ/resilience phù hợp | `Mono.timeout(Duration)` khi operator bao trùm lời gọi | Bao cả những pha đã thực thi trong phạm vi operation |
| Pool capacity | `setMaxConnTotal`, `setMaxConnPerRoute` | `maxConnections`, `pendingAcquireMaxCount` | Quyết định khả năng phục vụ request đồng thời |

`setResponseTimeout` của Apache và `responseTimeout` của Reactor Netty **không có nghĩa hoàn toàn đồng nhất**, và chúng đều khác deadline nghiệp vụ. Apache `responseTimeout` không nhất thiết là đồng hồ tổng cho toàn bộ streaming response/retry; Reactor Netty áp đặt response timeout ở phần handling HTTP response. Không mặc định thay chúng cho nhau theo cùng tên.

Cũng không nhầm `connectionRequestTimeout` trong Apache với **HTTP request timeout**. Tên “connection request” là **yêu cầu một connection từ pool**, không phải thời gian tối đa để server xử lý HTTP request.

## 4. Cách hình dung connection pool trước khi cấu hình timeout

Một pool giữ kết nối HTTP đã mở để tái sử dụng; tạo mới TLS/TCP cho từng request thường tốn tài nguyên. Với Apache HttpClient 5 classic, `PoolingHttpClientConnectionManager` quản lý connection limits theo **toàn bộ pool** và **từng route**; route có thể phụ thuộc target host/proxy/TLS config.

Các trạng thái cần phân biệt:

- **Available/idle:** connection đang rảnh có thể cấp ngay nếu còn sống và phù hợp route.
- **Leased/active:** connection đã cấp cho request và còn được giữ đến khi response được tiêu thụ/đóng.
- **Pending:** request đang chờ pool có thể cấp connection.
- **Max total/per route:** giới hạn kết nối đã cấu hình; một endpoint nóng có thể đạt per-route limit dù tổng pool còn khả năng cấp cho route khác.

Một HTTP call có thể **bị giữ connection lâu hơn lúc nhận response headers** nếu code stream body nhưng không đọc hết/đóng response. Vì vậy pool starvation có thể bắt nguồn từ **response body/resource leak**, không chỉ server chậm.

Tăng pool size là giải pháp có điều kiện: tăng quá nhiều connections có thể làm downstream quá tải, gây TCP connect failure và che vấn đề leak hoặc latency xấu. Đặt giới hạn theo capacity downstream và đo **pending, leased, available, latency percentiles**.

## 5. Spring Boot 3.3 không có một property chung cho mọi HTTP client

Các property sau thuộc **server đang nhận request**, không điều khiển HTTP client gọi ra ngoài:

```properties
server.port=8080
server.tomcat.connection-timeout=20s
```

Chúng không thay thế timeout của `RestClient`, `RestTemplate` hoặc `WebClient`. Trong **Spring Boot 3.3**, cách cấu hình outbound HTTP client thường đi qua builder, underlying `ClientHttpRequestFactory` hoặc `ClientHttpConnector`.

Cảnh báo về phiên bản: trên tài liệu mới có nhóm properties như `spring.http.clients.connect-timeout` và các builder API mới. **Không mặc nhiên áp dụng chúng cho Spring Boot 3.3.** Ở Boot 3.3, `RestTemplateBuilder` dùng:

```java
new RestTemplateBuilder()
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(4));
```

Đây là ví dụ **chỉ cho hai timeout phổ thông và còn phụ thuộc request factory được dùng**. Nó không đưa ra timeout chờ pool. `RestTemplateBuilder` không phải bean `RestTemplate` tự tạo; Boot cung cấp builder và ứng dụng cần build một client của mình.

`RestClient.Builder` của Spring Framework 6.1 không có các method `.connectTimeout(...)`/`.readTimeout(...)` theo cách một số tài liệu mới mô tả cho builder tầng Boot. Với `RestClient` Spring 6.1, một cách rõ ràng là cấu hình `ClientHttpRequestFactory` rồi gắn bằng `.requestFactory(...)`.

## 6. Chọn HTTP engine trước khi chọn đúng API

`RestClient`, `RestTemplate` và `WebClient` là **API ở tầng Spring**. Timeout thực hiện bởi client request factory/connector và thư viện nền tảng:

| Client Spring | Nền tảng có thể sử dụng | Có connection pool mà ứng dụng có thể chỉnh lease timeout? |
| --- | --- | --- |
| `RestClient` | Apache HttpClient 5, Jetty, JDK URLConnection, JDK HttpClient... tùy version/classpath | Có, khi chọn engine có pool config rõ như Apache |
| `RestTemplate` | `HttpComponentsClientHttpRequestFactory`, `SimpleClientHttpRequestFactory`, `JdkClientHttpRequestFactory`... | Phụ thuộc factory |
| `WebClient` | Reactor Netty, Jetty, JDK connector... | Có, khi chọn Reactor Netty provider/pool |

Apache HttpClient 5 (không phải `org.apache.http.*` của HttpClient 4) dùng packages `org.apache.hc.client5.*` và `org.apache.hc.core5.*`. Reactor Netty dùng `reactor.netty.*`, `io.netty.*`.

Đặc biệt với `SimpleClientHttpRequestFactory` dựa trên `HttpURLConnection`, không có **một API pool lease timeout tương đương Apache**; set connect/read timeout không làm xuất hiện pool manager. Đừng thêm property tự đặt tên `connectionRequestTimeout` rồi nghĩ framework sẽ tự xử lý.

Một thư viện khác được thêm vào classpath có thể thay engine được Boot tự chọn. Với nhu cầu chính xác ba timeouts, nên **cấu hình engine/factory tường minh** và dùng test kiểm chứng.

## 7. Apache HttpClient 5 và Spring Framework 6.1: điểm khác biệt phiên bản rất quan trọng

Ở **Spring Framework 6.1**, `HttpComponentsClientHttpRequestFactory` có:

```java
factory.setConnectTimeout(Duration.ofSeconds(2));
factory.setConnectionRequestTimeout(Duration.ofMillis(800));
```

Nhưng API của factory 6.1 **không có** `setReadTimeout(...)` như một số ví dụ thuộc Spring Framework mới hơn. Nếu copy:

```java
// Không biên dịch trên HttpComponentsClientHttpRequestFactory của Spring 6.1:
factory.setReadTimeout(Duration.ofSeconds(4));
```

thì mã sẽ lỗi `cannot find symbol` (không tìm thấy method). Không phải tên bean sai hay import thiếu: **method thực sự không có ở version ấy**.

Để cấu hình đầy đủ và rõ nghĩa với Apache HttpClient 5 thế hệ Spring Boot 3.3, bài này dùng:

- `ConnectionConfig.custom().setConnectTimeout(...)`: thời gian tạo kết nối mới.
- `ConnectionConfig.custom().setSocketTimeout(...)`: timeout I/O socket mặc định.
- `RequestConfig.custom().setConnectionRequestTimeout(...)`: chờ mượn connection từ pool.
- `RequestConfig.custom().setResponseTimeout(...)`: chờ response ở tầng HttpClient.
- `PoolingHttpClientConnectionManagerBuilder`: giới hạn total/per-route và connection configuration.
- `HttpClients.custom()`: tạo `CloseableHttpClient` chia sẻ được giữa các caller.

Đây là cách kiểm soát rõ engine, giúp người học nhìn thấy ranh giới từng loại timeout. Nếu nâng lên Spring 6.2/Boot 3.4+, **kiểm tra lại API** trước khi chuyển sang factory setters/builder property mới.

## 8. Ví dụ Spring Boot MVC chạy được với ba timeout Apache HttpClient 5

Ví dụ dùng **Java 21, Spring Boot 3.3.13**, project Gradle có Wrapper. Nó chạy HTTP server local và tạo một outbound `RestClient` gọi **trở lại chính server local** để mô phỏng downstream. Việc self-call chỉ để thử timeout; production hãy dùng URL service đích thực và không tạo vòng lặp gọi vô hạn.

Thông số minh họa:

| Cấu hình | Giá trị |
| --- | --- |
| Connection pool tổng | Tối đa 4 |
| Connection pool theo route | Tối đa 1 |
| Pool lease wait | 800 ms |
| TCP connect | 2 giây |
| Response wait | 3 giây |
| Socket inactivity | 3 giây |

### 8.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.httpcomponents.client5:httpclient5'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management lựa phiên bản tương thích của `httpclient5`; không tự chọn Apache HttpClient 4 vì classes/packages khác. Nếu dự án có BOM tự quản lý, xác minh Apache API của version được chọn trước khi biên dịch.

### 8.2. `src/main/java/com/example/httpclient/HttpClientApplication.java`

```java
package com.example.httpclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpClientApplication.class, args);
    }
}
```

### 8.3. `src/main/java/com/example/httpclient/OutboundClientConfig.java`

```java
package com.example.httpclient;

import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class OutboundClientConfig {

    @Bean(destroyMethod = "close")
    CloseableHttpClient outboundApacheClient() {
        ConnectionConfig connection = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(3))
                .build();

        PoolingHttpClientConnectionManager pool =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(4)
                        .setMaxConnPerRoute(1)
                        .setDefaultConnectionConfig(connection)
                        .build();

        RequestConfig request = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofMilliseconds(800))
                .setResponseTimeout(Timeout.ofSeconds(3))
                .build();

        return HttpClients.custom()
                .setConnectionManager(pool)
                .setDefaultRequestConfig(request)
                .build();
    }

    @Bean
    RestClient downstreamRestClient(
            RestClient.Builder builder,
            CloseableHttpClient outboundApacheClient,
            @Value("${demo.downstream.base-url}") String baseUrl) {

        HttpComponentsClientHttpRequestFactory factory =
                new HttpComponentsClientHttpRequestFactory(
                        outboundApacheClient);

        return builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    @Bean
    RestTemplate legacyRestTemplate(
            CloseableHttpClient outboundApacheClient) {
        return new RestTemplate(
                new HttpComponentsClientHttpRequestFactory(
                        outboundApacheClient));
    }
}
```

**Vì sao cần từng bean?**

- Một `CloseableHttpClient` dùng chung cho `RestClient` và `RestTemplate`, không xây một pool mới cho từng request.
- `PoolingHttpClientConnectionManager` đặt per-route limit 1 để thí nghiệm pool saturation dễ thấy. Production phải chọn capacity phù hợp, không lấy 1 làm mặc định đề xuất.
- `RequestConfig` gồm `setConnectionRequestTimeout(800ms)` và `setResponseTimeout(3s)`; chúng thuộc **hai pha độc lập**.
- `ConnectionConfig` gồm `setConnectTimeout(2s)` và `setSocketTimeout(3s)`; `socketTimeout` là tầng I/O và không nên coi là deadline tổng.
- `@Bean(destroyMethod="close")` giúp Spring đóng `CloseableHttpClient` và connection manager mà client sở hữu khi context đóng. Không tự tạo một `CloseableHttpClient` mới trong method handler.
- Cấu hình giữ `RestClient.Builder` đã được Spring Boot chuẩn bị (converters/observability/customizers nếu có) rồi **chỉ thay request factory** cho client được đặt tên.

**Chú ý:** Bản Apache HttpClient 5 có các API cũ/mới khác nhau quanh connect timeout; dùng `ConnectionConfig` rõ ràng theo Apache 5.3. Không dựa vào factory `.setReadTimeout()` của Spring Framework 6.1 vì method không tồn tại.

### 8.4. `src/main/java/com/example/httpclient/SlowController.java`

```java
package com.example.httpclient;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class SlowController {

    @GetMapping("/slow")
    public String slow(@RequestParam(defaultValue = "0") long delayMs)
            throws InterruptedException {

        if (delayMs < 0 || delayMs > 12_000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "delayMs is out of range");
        }

        Thread.sleep(delayMs);
        return "slow-ok";
    }
}
```

Đây là **server giả lập chậm**, không phải cách viết server production. `Thread.sleep` giữ servlet thread trong suốt thời gian chờ; dùng trong demo giới hạn cục bộ để tạo response delay có thể tái hiện.

### 8.5. `src/main/java/com/example/httpclient/ProxyController.java`

```java
package com.example.httpclient;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class ProxyController {
    private final RestClient client;

    public ProxyController(RestClient downstreamRestClient) {
        this.client = downstreamRestClient;
    }

    @GetMapping("/call")
    public String call(@RequestParam(defaultValue = "0") long delayMs) {
        return client.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/slow")
                        .queryParam("delayMs", delayMs)
                        .build())
                .retrieve()
                .body(String.class);
    }
}
```

Không có `@ControllerAdvice` trong demo này: khi outbound call timeout, exception có thể trở thành **HTTP 500** và được ghi log. Đó là cách quan sát thí nghiệm, **không phải thiết kế xử lý lỗi production**. Hệ thống thật nên mapping lỗi downstream hợp lý (ví dụ 502/503/504 tùy gateway policy), không lộ exception nội bộ, và có traces/metrics.

### 8.6. `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
server.port=8080
demo.downstream.base-url=http://127.0.0.1:8080
```

Chạy từ project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Từ terminal khác:

```bash
curl -i "http://127.0.0.1:8080/call?delayMs=0"
curl -i "http://127.0.0.1:8080/call?delayMs=1000"
```

Trong điều kiện máy không quá tải và không có lỗi network, hai response sẽ là HTTP 200 với body **chính xác**:

```text
slow-ok
```

Nếu gửi:

```bash
curl -i "http://127.0.0.1:8080/call?delayMs=5000"
```

`RestClient` dự kiến gặp response timeout khoảng 3 giây và request `/call` có thể trả HTTP 500 trong demo; loại exception/cấu trúc log tùy version và root cause. **Không cố khẳng định đúng một dòng stdout hoặc đúng mili giây** vì thời gian scheduling/network thay đổi.

## 9. Tái hiện timeout chờ pool, không nhầm với read timeout

Trong ví dụ, Apache pool cho cùng route `/slow` tối đa **1 connection**; khi request A đang giữ connection đó, B phải chờ mượn connection.

Trên Linux/macOS/Bash, thử gần đồng thời:

```bash
curl -sS "http://127.0.0.1:8080/call?delayMs=2500" \
  -o /tmp/call-a.txt &

sleep 0.2

curl -i "http://127.0.0.1:8080/call?delayMs=0"
wait
```

Khi A đã lấy connection và server còn xử lý, B có thể hết **800ms connection acquisition timeout** trước khi A hoàn thành. Nếu hai request đến khác thứ tự do scheduling hoặc curl/client cache, kết quả có thể khác; muốn test deterministic cần đồng bộ việc A đã thực sự nắm connection trước khi gửi B.

Quan sát log và pool state để xác nhận lỗi thuộc **lease wait**, không suy chỉ từ request B thất bại:

- Kết nối A đã được pool cấp và chưa release.
- `available=0`, `leased=1`, `pending>=1` cho route khi B đợi.
- Failure của B liên quan lease/connection request timeout, không phải TCP connect.
- Khi A trả body và đóng response đúng cách, connection được pool dùng lại.

Nếu tăng `setConnectionRequestTimeout` lên 5 giây, B có thể chờ A xong rồi thành công; **nhưng tail latency của B tăng**. Nếu tăng `maxConnPerRoute` lên 2, cả A và B có thể chạy đồng thời, với điều kiện downstream có đủ capacity. **Không chọn cả hai thay đổi chỉ để xóa lỗi mà không xem throughput và queueing.**

Lưu ý môi trường Windows PowerShell không có semantics Bash `&`/`wait` tương ứng; dùng hai terminal hoặc jobs có kiểm soát. Tránh chạy test tải cao vào production service không được phép.

## 10. RestTemplateBuilder: cấu hình đơn giản và giới hạn của nó

Trong Spring Boot 3.3, code sau tạo `RestTemplate` có timeout phổ thông khi request factory được chọn hỗ trợ:

```java
import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

RestTemplate client = new RestTemplateBuilder()
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(4))
        .build();
```

Đây là **mã minh họa để đặt timeout trên builder**, không phải chương trình độc lập: cần dependencies của Spring Boot và một bean/entrypoint sử dụng `client`. Khi dùng trong Spring Boot, nên **inject `RestTemplateBuilder` đã auto-configured** thay vì `new RestTemplateBuilder()` nếu muốn giữ customizers/SSL/converters/observability.

**Điểm thiếu:** Builder trên không có tham số tường minh cho **pool lease timeout**. Nếu không bảo đảm engine đã có pool, không có “connection acquisition timeout” nào để chỉnh. Với use case của bài này, cấu hình Apache trực tiếp ở mục 8 rõ hơn.

Khác biệt phiên bản: với Boot 3.3, method là `setConnectTimeout` và `setReadTimeout`. Một số tài liệu mới hơn dùng tên `connectTimeout`/`readTimeout` và properties tự động khác. **Không trộn version** khi học/copy code.

Nếu sử dụng `SimpleClientHttpRequestFactory`:

```java
import java.time.Duration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

SimpleClientHttpRequestFactory simple =
        new SimpleClientHttpRequestFactory();
simple.setConnectTimeout(Duration.ofSeconds(2));
simple.setReadTimeout(Duration.ofSeconds(4));
```

`SimpleClientHttpRequestFactory` dựa vào JDK `HttpURLConnection`; nó có các timeout liên quan connect/read nhưng **không cung cấp pool leasing API như Apache**. Hai đoạn trên là **mẫu tích hợp**, không phải Java source file có method `main`.

## 11. `RestClient` và `RestTemplate` dùng chung request factory có nghĩa gì?

`RestClient` mới trong Spring Framework 6.1 là blocking/fluent API; `RestTemplate` vẫn được hỗ trợ cho ứng dụng đang có code cũ. Cả hai đều có thể gọi **cùng một Apache client/pool** khi sử dụng các factory trỏ tới cùng `CloseableHttpClient`.

```text
RestClient        -> HttpComponentsClientHttpRequestFactory ----+
                                                               |
RestTemplate      -> HttpComponentsClientHttpRequestFactory ----+--> CloseableHttpClient
                                                                      |
                                                                      v
                                                       PoolingHttpClientConnectionManager
```

Việc dùng chung pool giúp quản lý tổng số connections nhưng cũng tạo **cạnh tranh capacity giữa các callers**. Nếu API A chậm và giữ hết connections, API B dùng cùng route/manager có thể chịu queue; phân nhóm pool theo downstream/service tier khi cần isolation.

Trong Spring, đặt một `CloseableHttpClient` là bean singleton được quản lý lifecycle và tái sử dụng. Đừng tạo một client mới mỗi HTTP request hoặc đóng `CloseableHttpClient` sau từng call khi muốn connection reuse.

Đảm bảo response body được đọc/đóng. Với `RestClient.retrieve().body(String.class)` cho response nhỏ, framework tiêu thụ/đóng body phù hợp. Nếu dùng `exchange(...)` để trả `InputStream` hoặc tự giữ `ClientHttpResponse`, cần hiểu lifecycle và đóng resource; leak sẽ làm **leased connections** không trở lại pool.

## 12. WebClient + Reactor Netty: ba timeout tương ứng

`WebClient` là API reactive của Spring WebFlux. Khi dùng **Reactor Netty** làm engine, timeout chờ pool và response được cấu hình bằng API khác Apache:

- `ConnectionProvider.pendingAcquireTimeout(Duration)` = thời gian chờ khi chưa lấy được pooled connection.
- `ConnectionProvider.maxConnections(int)` và `pendingAcquireMaxCount(int)` = capacity và độ dài queue.
- `HttpClient.option(ChannelOption.CONNECT_TIMEOUT_MILLIS, int)` = TCP connect timeout.
- `HttpClient.responseTimeout(Duration)` = response timeout.
- `Mono.timeout(Duration)` trên pipeline bao trùm call có thể đặt deadline từ lúc subscribe tới lúc Mono hoàn thành; **không thay thế** cấu hình phase-specific.

Ví dụ **độc lập về cấu hình WebClient**, áp dụng trong một Spring Boot project đã thêm `spring-boot-starter-webflux`:

**`src/main/java/com/example/reactive/RemoteWebClientConfig.java`:**

```java
package com.example.reactive;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class RemoteWebClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider remoteConnectionProvider() {
        return ConnectionProvider.builder("remote-service-pool")
                .maxConnections(30)
                .pendingAcquireMaxCount(60)
                .pendingAcquireTimeout(Duration.ofMillis(800))
                .maxIdleTime(Duration.ofSeconds(20))
                .build();
    }

    @Bean
    WebClient remoteWebClient(
            WebClient.Builder builder,
            ConnectionProvider remoteConnectionProvider) {

        HttpClient netty = HttpClient.create(remoteConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
                .responseTimeout(Duration.ofSeconds(3));

        return builder
                .clientConnector(new ReactorClientHttpConnector(netty))
                .baseUrl("https://partner.example")
                .build();
    }
}
```

Đây là **mẫu cấu hình có thể biên dịch với các dependencies phù hợp**, không phải toàn bộ một application vì còn thiếu `@SpringBootApplication`, controller và một endpoint thật. `partner.example` là placeholder host tài liệu; thay bằng URL đối tác có thật và chính sách TLS hợp lệ. Reactor Netty `ConnectionProvider` được Spring đóng khi context dừng nếu bean expose `dispose()`; không tự tạo pool mới trong mỗi subscription.

Ví dụ call reactive:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<String> result = remoteWebClient.get()
        .uri("/api/health")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(6));
```

Đoạn trên dùng biến `remoteWebClient` được inject từ bean ở trên, **không phải chương trình Java độc lập**. `timeout(6s)` đặt deadline ở pipeline `Mono<String>` (gồm acquire/connect/response/body trong phạm vi subscription), nhưng kết quả lỗi/việc cancel thực tế phụ thuộc async transport. Không dùng `.block()` trên Reactor event-loop; trong reactive request handler nên trả `Mono`/`Flux`.

**Lưu ý đặc biệt:** Nếu một project có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường suy ra **SERVLET** application type, nhưng `WebClient` vẫn có thể dùng làm outbound reactive client. Điều đó không biến toàn bộ MVC controller thành reactive server.

## 13. `responseTimeout`, `ReadTimeoutHandler` và `Mono.timeout` khác nhau

Trong Reactor Netty, có ba cơ chế liên quan “đọc”:

| Cơ chế | Áp dụng vào đâu? | Điều cần nhớ |
| --- | --- | --- |
| `HttpClient.responseTimeout(...)` | HTTP response handling của Reactor Netty | Phase-specific; khuyến nghị cấu hình khi chờ response |
| `ReadTimeoutHandler` từ Netty | I/O inactivity trên channel | Có thể ảnh hưởng cả read operations khác nếu handler gắn rộng; dùng khi thật sự cần |
| `Mono.timeout(...)` | Reactor Publisher được wrap | Deadline/liveness của pipeline, không riêng TCP/response |

Spring Framework docs có ví dụ:

```java
import io.netty.handler.timeout.ReadTimeoutHandler;
import io.netty.handler.timeout.WriteTimeoutHandler;

HttpClient configured = HttpClient.create()
        .doOnConnected(connection -> connection
                .addHandlerLast(new ReadTimeoutHandler(10))
                .addHandlerLast(new WriteTimeoutHandler(10)));
```

Đây là **mẫu tích hợp**: cần `reactor.netty.http.client.HttpClient` import và `ReactorClientHttpConnector` nếu dùng cùng `WebClient`. Constructor `ReadTimeoutHandler(10)` dùng đơn vị **giây**; không phải 10 mili giây. Read inactivity handler cấp channel có thể ảnh hưởng streaming/chunking và connection reuse theo ngữ cảnh.

Nói đơn giản: nếu mục tiêu là HTTP response không được chờ mãi, ưu tiên `responseTimeout(...)`; khi cần **giới hạn toàn bộ một call** (và đã hiểu tác động retry), đặt thêm deadline tầng nghiệp vụ. Không “bù” thiếu pool acquire timeout bằng cách chỉ tăng `responseTimeout`.

## 14. Giá trị mặc định: đọc đúng version, không dựa vào trí nhớ

Một số thư viện có defaults rất dài, một số timeout mặc định là “không khai báo”. Ví dụ tài liệu Reactor Netty thế hệ 1.1 ghi:

- `pendingAcquireTimeout`: mặc định khoảng **45 giây**.
- `CONNECT_TIMEOUT_MILLIS`: mặc định khoảng **30 giây**.
- `HttpClient.responseTimeout`: mặc định không được chỉ định.
- `pendingAcquireMaxCount`: mặc định khoảng **2 × số connections tối đa**.

Những giá trị này là **default của engine trong phiên bản tài liệu cụ thể**, không phải SLA mặc định của Spring Boot cho mọi HTTP client. Engine, client version và Spring Boot auto-configuration có thể thay đổi defaults; không nên dựa vào chúng khi thiết kế thời gian chờ production.

Đối với Apache HttpClient 5.x, `RequestConfig`, `ConnectionConfig` và pooling manager cũng có defaults riêng. Hãy kiểm tra effective `RequestConfig`/`ConnectionConfig` và các pool limits thực tế của instance đang chạy. **Cấu hình tường minh giúp người đọc code không phải đoán defaults**, nhưng đừng biến timeout quá nhỏ thành lỗi ngẫu nhiên dưới tải.

Khi đọc tài liệu online, bảo đảm đang nhìn phiên bản tương ứng Spring Boot 3.3/Spring Framework 6.1/Apache HttpClient 5, không copy property từ Spring Boot 4.x.

## 15. HTTPS, DNS và proxy tạo thêm pha chờ

Ba timeout không bao trùm mọi chi tiết mạng.

**DNS:** Trước TCP connect, hostname phải được resolve. Trong nhiều client/JVM/resolver, DNS latency không nằm hoàn toàn dưới TCP connect timeout. Nếu nghi DNS chậm, quan sát DNS lookup bằng metric/log theo resolver và cân nhắc timeout chuyên biệt.

**TLS handshake:** TCP connect thành công không chứng minh TLS đã hoàn tất. Với Apache/Spring `HttpComponentsClientHttpRequestFactory`, Javadoc 6.1 lưu ý connect timeout setter của factory **không nhất thiết điều khiển SSL handshake hoặc HTTP CONNECT tunnel**; phải cấu hình socket/TLS layer phù hợp. Không đặt connect 2s rồi khẳng định mọi HTTPS handshake phải xong trong 2s.

**HTTP proxy:** Khi gọi qua forward proxy, connect timeout có thể áp dụng đến **proxy** chứ không trực tiếp tới server cuối. CONNECT tunnel, proxy auth hoặc proxy responses có timeout và status riêng. Chẩn đoán phải chỉ rõ URL, proxy hop và connection route.

**Connection reuse:** Nếu lấy được idle TCP connection từ pool, request **không phải kết nối TCP mới** nên connect timeout có thể không được chạm tới ở mỗi call. Read/response timeout vẫn rất quan trọng khi server ngừng phản hồi trên connection đã tái sử dụng.

**Retries/redirects:** Mỗi lần retry hoặc theo redirect có thể phát sinh các pha chờ mới. Một timeout cho **mỗi attempt** không tự đặt upper bound cho tổng nhiều attempts.

## 16. Timeout toàn thao tác (deadline) khác tổng các timeout từng pha

Giả sử một HTTP call cho endpoint báo cáo có SLA tổng **5 giây**. Cấu hình:

```text
pool acquisition <= 0.8s
connect          <= 2.0s
response         <= 3.0s
```

**Không thể tính 0.8 + 2.0 + 3.0 = 5.8 giây rồi khẳng định call luôn kết thúc sau 5.8 giây**, vì DNS, TLS, body streaming, retries và semantics của từng timeout còn tác động. Cần **end-to-end deadline** nếu nghiệp vụ có budget chặt chẽ.

Một mô hình time budgeting:

```text
Inbound request deadline (ví dụ 5s)
    |
    +--> auth/business logic 0.3s
    +--> outbound HTTP call <= 4.2s
    +--> serialization, logging, response 0.5s
```

Trong reactive code:

```java
Mono<String> body = webClient.get()
        .uri("/api/resource")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofMillis(4_200));
```

Với blocking `RestClient`, cần một cơ chế deadline/cancellation/resilience phù hợp tầng application, còn timeouts cấp engine phải được cấu hình để tránh thread chờ vô hạn. **Không dùng `CompletableFuture.orTimeout` như bảo đảm socket I/O blocking đã bị hủy ngay**: nó có thể chỉ làm future kết thúc lỗi trong khi network call chạy tiếp nếu không có cancellation/interrupt support thích hợp.

Nếu áp dụng retry ba lần mỗi attempt 3 giây, tổng thời gian có thể vượt SLA rất xa nếu không có deadline chung. Dùng retry budget, backoff có jitter và idempotency policy; đừng retry vô điều kiện các thao tác POST có side effects.

## 17. Chọn timeout theo latency và dependency SLO

Không có một bộ “2s/3s/1s” đúng cho mọi dịch vụ. Một quy trình hiệu quả:

1. Xác định **deadline của request đến** và phần thời gian dành cho outbound dependency.
2. Đo latency của dependency theo p50/p95/p99, khu vực địa lý, request payload và tải đồng thời.
3. Chọn response timeout đủ đáp ứng SLO và tránh chờ quá dài khi downstream lỗi; tránh quá thấp gây false timeouts.
4. Chọn connect timeout phù hợp LAN/WAN, DNS, proxy/TLS và chất lượng mạng; đừng dùng quá lớn cho API nội bộ nhanh mà không có lý do.
5. Chọn pool acquisition timeout ngắn vừa đủ để **phản ánh overload**, tránh queueing kéo dài khi capacity hết.
6. Chọn `maxConnPerRoute/maxConnections/pendingAcquireMaxCount` theo concurrency budget, throughput và downstream rate limit.
7. Test cả warm connections, cold starts, TLS rotation, proxy failover, packet loss và long-tail response.
8. Giám sát timeout rate, retries, pool pending và hiệu năng downstream, điều chỉnh dựa trên bằng chứng.

**Little’s Law (mô hình gần đúng):** số request đồng thời trung bình \(L \approx \lambda W\), với \(\lambda\) là throughput request/giây và \(W\) là thời gian xử lý trung bình/giây. Ví dụ 100 request/giây × 0,2 giây ≈ 20 requests đang xử lý. Đây là gợi ý capacity, **không tự là kích thước pool bắt buộc**: HTTP/2 multiplexing, burstiness, tài nguyên khác và per-route contention có thể làm kết quả khác.

Đặt queue chờ quá lớn không tạo thêm capacity; nó chỉ tích tụ requests, tăng p99 latency, tiêu thụ bộ nhớ và gây cascading failures.

## 18. Quan sát pool: available, leased, pending, max

Với Apache HttpClient 5, connection manager có số liệu pool, ví dụ:

```java
// Mã minh họa bên trong một lớp đã giữ tham chiếu đến manager:
var stats = manager.getTotalStats();
System.out.println("leased=" + stats.getLeased());
System.out.println("pending=" + stats.getPending());
System.out.println("available=" + stats.getAvailable());
System.out.println("max=" + stats.getMax());
```

Đoạn này **không độc lập** vì `manager` phải là `PoolingHttpClientConnectionManager` đang phục vụ các requests thật, không phải một manager mới được tạo chỉ để đọc stats. Để có metrics, giữ connection manager dưới dạng bean hoặc field được chia sẻ và export qua Micrometer/Actuator theo policy.

Đối với Reactor Netty, connection pool có metrics như active/idle/pending connections khi bật `metrics(true)` và môi trường có recorder/Micrometer phù hợp:

```java
ConnectionProvider provider = ConnectionProvider.builder("orders-pool")
        .maxConnections(30)
        .pendingAcquireMaxCount(60)
        .pendingAcquireTimeout(Duration.ofMillis(800))
        .metrics(true)
        .build();
```

Các metric names và tag labels phụ thuộc Reactor Netty/Micrometer phiên bản đang chạy. Không công khai các Actuator endpoints nội bộ cho Internet chỉ để debug timeout.

**Điểm cần vẽ đồ thị:** connect timeout count, response timeout count, pool acquire timeout count, currently leased, pending queue length, remaining capacity, latency percentiles, throughput, retries và downstream error rate. Những metric này cho biết lỗi thuộc **kết nối mạng**, **chờ server** hay **tắc pool**.

## 19. Đọc exception và root cause theo đúng pha

| Dấu hiệu/exception (minh họa) | Khả năng nổi bật | Kiểm tra tiếp |
| --- | --- | --- |
| `ConnectTimeoutException` | TCP connection attempt quá lâu | Host/IP, firewall, network, connect timeout |
| `UnknownHostException` | DNS resolution | DNS, resolver, hostname; không phải luôn connect timeout |
| `Connection refused` | TCP peer từ chối/không lắng nghe | Host/port/service health, không phải timeout |
| `SocketTimeoutException: Read timed out` | Không có dữ liệu phản hồi trong thời gian read timeout | Slow response, idle stream, socket timeout |
| `java.net.http.HttpTimeoutException` | HTTP request timeout của JDK client | JDK request timeout semantics và underlying factory |
| Apache pool lease timeout / `ConnectionRequestTimeoutException` | Pool không cấp connection trong thời gian chờ | Leased/pending/per-route limits; response close |
| `PoolAcquireTimeoutException` trong Reactor Netty | Chờ acquire pooled connection quá lâu | Pool pending, max connections, event-loop load |
| `PoolAcquirePendingLimitException` | Queue chờ acquire đã đầy | `pendingAcquireMaxCount`, burst, backpressure |
| `WebClientRequestException` | Wrapper lỗi outbound network/timeout | Đọc `getCause()` và toàn bộ cause chain |
| `ResourceAccessException` | Wrapper I/O của `RestClient`/`RestTemplate` | Đọc root cause, không khẳng định ngay read/connect |
| HTTP `429`, `502`, `503`, `504` | HTTP status do downstream/proxy/gateway trả | Header, response body, gateway logs; có thể timeout ở hop khác |

Các tên class exception có thể khác theo Apache HttpClient/Reactor Netty version và đường xử lý; không viết logic business phụ thuộc cứng vào **message string** của exception. Trong Spring, nhiều lỗi được bọc qua `RestClientException` hoặc WebClient errors; đọc cause chain mới nhận diện đúng tầng.

`HTTP 504 Gateway Timeout` là **response HTTP do một gateway tạo**, không đồng nghĩa chính HTTP client của bạn tự hết `readTimeout`. Cần phân biệt gateway timeout, upstream timeout và local client timeout trước khi đặt lại cấu hình.

**Cách lập timeline:** ghi `t0=outbound start`, thời điểm acquire connection, DNS/connect/TLS nếu có, first byte và end body; thêm trace IDs để đối chiếu proxy/downstream. Không log secrets, Authorization header, toàn bộ response payload hoặc địa chỉ nhạy cảm chỉ vì debug.

## 20. Không sửa pool starvation bằng việc tăng read timeout

Một lỗi vận hành quen thuộc:

```text
Leased connections = max
Available = 0
Pending queue tăng liên tục
Timeouts xuất hiện ở pending acquire
```

Lúc này **read timeout thường không phải nguyên nhân trực tiếp**. Các hướng xử lý:

- Tìm code không đóng `ClientHttpResponse`, `InputStream`, streaming body hoặc request cancel thiếu cleanup.
- Xem downstream latency p99 tăng khiến connection bị giữ quá lâu.
- So sánh `maxConnPerRoute` với traffic: total pool 100 nhưng per-route 2 vẫn có thể làm một service nóng tắc nghẽn.
- Giảm số in-flight requests bằng bulkhead/backpressure/queue limits, thay vì tăng queue vô hạn.
- Tăng pool size **nếu** downstream chịu được và load test chứng minh throughput tăng.
- Đặt acquisition timeout hợp lý để fail fast khi hệ thống đã quá tải, nhưng trả HTTP lỗi có kiểm soát và quan sát metrics.

Nếu lỗi xảy ra trên **connections đang rảnh rất lâu**, có thể là stale connections bị load balancer đóng. Khi ấy cần `maxIdleTime`, `validateAfterInactivity`, keepalive hoặc eviction tương ứng, không chỉ connect/read timeout.

## 21. Connection lifetime, idle timeout và eviction không phải ba timeout chính

Nhiều người nhầm thêm các thời hạn:

| Setting | Mục đích |
| --- | --- |
| Pool `maxIdleTime` | Đóng connection rảnh quá lâu |
| Pool `maxLifeTime` | Giới hạn tuổi thọ connection |
| Validation after inactivity | Kiểm tra connection cũ có còn dùng được khi lease lại |
| TCP keepalive | Probe transport sau thời gian idle dài theo OS/network policy |
| HTTP keep-alive | Tái sử dụng connection theo protocol |
| Read/response timeout | Giới hạn chờ hoạt động đọc/response cho request |
| Acquisition timeout | Giới hạn thời gian request chờ **mượn connection** |

Ví dụ Reactor Netty:

```java
ConnectionProvider provider = ConnectionProvider.builder("partner-pool")
        .maxConnections(40)
        .maxIdleTime(Duration.ofSeconds(25))
        .maxLifeTime(Duration.ofMinutes(3))
        .pendingAcquireTimeout(Duration.ofMillis(800))
        .build();
```

Đặt `maxIdleTime` bằng hoặc thấp hơn idle timeout được load balancer/server phía đối tác quảng cáo có thể giảm lỗi “connection reset” khi tái sử dụng connection cũ. Nhưng timeout vẫn cần đo theo traffic thật; eviction quá gắt làm tăng TCP/TLS handshakes và CPU.

Không đồng nhất việc tăng `maxLifeTime` với tăng thời gian cho HTTP call. Một connection đang leased không nhất thiết bị đóng ngay khi chạm idle/lifetime limit; pool implementation có lifecycle rules cụ thể.

## 22. HTTP/2, streaming và long polling cần cấu hình riêng

Với HTTP/1.1 classic, một connection thường xử lý một request tại một thời điểm. Với HTTP/2, một TCP connection có thể multiplex nhiều streams, nên **số TCP connections không bằng số HTTP requests đồng thời**. Pool sizing, limits và timeout semantics phải xét đúng transport/version.

**Server-Sent Events (SSE)/streaming:** một stream có thể kéo dài hàng phút hoặc hàng giờ nhưng vẫn liên tục gửi dữ liệu. Read inactivity timeout không nên thấp hơn khoảng heartbeat mong đợi; deadline tổng 5s sẽ cắt stream dù hoạt động đúng. Dùng policy riêng cho streaming endpoints.

**Long polling:** một request đợi dữ liệu có chủ ý lâu hơn REST request thông thường. Chọn read/response timeout lớn hơn thời gian server long-poll plus network margin, đồng thời bảo đảm connection capacity phù hợp. Không đặt mọi outbound calls cùng một 2s read timeout nếu có long polling/large downloads.

**Large uploads/downloads:** timeout cho connect khác timeout chờ body bytes; HTTP client có thể có write timeout riêng, `ReadTimeoutHandler`, retry policy và streaming backpressure. Nếu service đọc nhiều chunks liên tiếp dưới giới hạn inactivity, tổng thời gian lớn hơn read timeout mà vẫn không lỗi — chính là lý do cần hiểu **semantics thời gian chờ**, không cộng đại số một cách mù quáng.

## 23. Thử nghiệm có kiểm soát: phân biệt chậm response và chờ pool

Trong ví dụ Spring MVC mục 8:

**Kịch bản A — downstream nhanh**

```bash
curl -i "http://127.0.0.1:8080/call?delayMs=100"
```

Mong đợi HTTP 200 và body `slow-ok`.

**Kịch bản B — downstream chậm hơn response timeout**

```bash
curl -i "http://127.0.0.1:8080/call?delayMs=5000"
```

Mong đợi outbound HTTP client không tiếp tục chờ response sau giới hạn cấu hình; exception được Spring bọc và sample `/call` có thể trả lỗi 500. Không dùng mã status 500 từ sample làm hợp đồng production.

**Kịch bản C — tắc pool**

Chạy đồng thời ít nhất hai requests `/call` khi `maxConnPerRoute=1` và `delayMs` của request đầu > `connectionRequestTimeout`; đo thời gian và xem pool pending/leased. Nếu B thất bại trước khi có outbound TCP connect mới, đó là lease timeout.

**Kịch bản D — TCP connect không thành công**

Dùng host:port nằm dưới **kiểm soát của môi trường test** và mạng được cấu hình cố ý drop SYN (không phải `127.0.0.1` port không lắng nghe, vì nó thường gây `Connection refused` ngay). Ghi TCP connect duration và error. Không quét IP công cộng ngẫu nhiên để “thử connect timeout”.

**Kịch bản E — timeout của gateway trước client**

Nếu có load balancer giữa client và downstream, kiểm tra trường hợp gateway trả HTTP 504 **trước** client response timeout. Khi ấy local client nhận 504 bình thường; đừng diễn giải là nó bị lỗi local read timeout.

Tất cả kiểm thử tải/chậm nên ở dev/staging hoặc môi trường đã cho phép, không cố gây pool exhaustion trên hệ thống production chung.

## 24. Viết kiểm thử HTTP thực thay vì chỉ nhìn bean config

Ví dụ kiểm thử tích hợp cho kịch bản nhanh, dựa trên project ở mục 8. Test gọi HTTP qua cổng ngẫu nhiên; vì `demo.downstream.base-url` của project mẫu cố định `localhost:8080`, **không dùng nguyên cấu hình mặc định ấy cho RANDOM_PORT** khi `/call` self-call.

Cách đơn giản, phù hợp bài học là test endpoint downstream `/slow` trực tiếp trong `@SpringBootTest`:

**`src/test/java/com/example/httpclient/SlowControllerHttpTest.java`:**

```java
package com.example.httpclient;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SlowControllerHttpTest {

    @Autowired
    TestRestTemplate client;

    @Test
    void slowEndpointReturnsExpectedBody() {
        ResponseEntity<String> response =
                client.getForEntity("/slow?delayMs=0", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("slow-ok");
    }
}
```

Chạy:

```bash
./gradlew test
```

Test này xác nhận phần **downstream giả lập** của ví dụ qua HTTP server thật, không xác nhận tự động cả ba timeout của Apache client. Để test ba timeout, cần tạo **controlled server** và định lượng thời gian/tình trạng pool, chẳng hạn JDK `HttpServer` trên random port hoặc WireMock/MockWebServer và synchronize requests bằng latch. Tránh assertions như “exactly 800ms” vì CI scheduling không ổn định; dùng biên độ hợp lý, xác nhận exception type/cause và pool metrics.

Một kiểm thử pool lease đáng tin nên giữ **một connection đang leased** bằng server response chưa hoàn thành và `CountDownLatch`, rồi gửi request thứ hai, xác minh lỗi đến từ acquisition timeout; test read timeout thì chỉ gửi một request tới server đã nhận connect nhưng trì hoãn first response byte.

## 25. Giám sát trong production: ba loại lỗi cần ba nhãn metric

Một dashboard hữu ích tách ba nhóm:

```text
client_connect_timeouts_total{downstream="inventory"}
client_response_timeouts_total{downstream="inventory"}
client_pool_acquire_timeouts_total{downstream="inventory"}

client_pool_leased{downstream="inventory"}
client_pool_pending{downstream="inventory"}
client_pool_available{downstream="inventory"}

client_latency_seconds{downstream="inventory",outcome="success|error"}
```

Đây là **tên metric gợi ý**, không khẳng định Spring Boot/Apache tự xuất đúng các tên này. Khi dùng Micrometer/Reactor Netty, hãy tra metric names của version runtime và chủ động map exception causes ra nhóm.

Khi tăng độ trễ, phân tích theo thứ tự:

1. Timeout có xảy ra **trước** TCP connect không? Nếu vậy xem pool.
2. Pool có cạn per-route/total connections và pending queue tăng không?
3. Nếu pool bình thường, connect latency có tăng hoặc DNS/TLS chậm không?
4. Nếu connect nhanh, downstream first-byte latency/processing time có tăng không?
5. Retry có khuếch đại tổng concurrency hoặc giữ connections quá lâu không?
6. Circuit breaker/bulkhead có từ chối call khi dependency quá tải không?

Đừng log raw Authorization tokens, TLS secrets, URL query chứa dữ liệu riêng tư hoặc response bodies trong metrics. Tags có cardinality cao như userId/requestId không phù hợp metric dimension; dùng trace IDs ở tracing/logging có kiểm soát.

## 26. Những lỗi cấu hình và hiểu nhầm thường gặp

**“Connect timeout là thời gian chờ HTTP response.”** Sai. Nó chủ yếu giới hạn **tạo TCP connection mới**; server có thể mất thêm thời gian mới trả response.

**“Read timeout là tổng thời gian request.”** Không mặc nhiên đúng. Semantics phụ thuộc engine, hoạt động đọc/chunking, response streaming và retry.

**“Connection request timeout là HTTP request timeout.”** Sai trong Apache HttpClient: nó giới hạn **chờ mượn connection từ pool**.

**“Chỉ cần `.setReadTimeout(...)` trên `HttpComponentsClientHttpRequestFactory` của Spring 6.1.”** API này **không có** trên factory 6.1. Dùng Apache `RequestConfig.setResponseTimeout` và các configs phù hợp.

**“`RestTemplateBuilder.setReadTimeout` sẽ luôn cấu hình pool lease timeout.”** Không. Lease timeout thuộc request factory/pool manager riêng.

**“Tăng pool lên vô hạn thì hết timeout.”** Không. Điều này có thể làm downstream quá tải, tăng TCP/TLS pressure và che leak.

**“`server.tomcat.connection-timeout` điều khiển outbound RestClient.”** Không. Đó là cấu hình web server inbound.

**“Mọi lỗi 504 là do local HTTP client read timeout.”** Không. 504 có thể do **gateway** trả dưới dạng HTTP status.

**“`Connection refused` chính là connect timeout.”** Không. Refused thường là từ chối ngay, còn timeout là hết thời hạn chờ thiết lập.

**“Chạy WebClient trong MVC chắc chắn là reactive server.”** Không. Có thể dùng WebClient outbound trong Servlet app.

**“`Mono.timeout` tự sửa mọi pool/network config.”** Không. Nó đặt thời hạn cho pipeline, nhưng cần tối ưu resource acquisition và cancellation riêng.

**“Timeout lâu hơn thì hệ thống ổn định hơn.”** Không nhất thiết. Timeout quá dài có thể làm request threads và pool connections bị giữ lâu hơn, khuếch đại cascading failure.

## 27. Checklist ứng dụng và câu hỏi tự kiểm tra

**Checklist:**

- Xác định rõ stack đang dùng: `RestClient`, `RestTemplate` hay `WebClient`, và underlying Apache/JDK/Reactor engine.
- Có giá trị tường minh cho **connect, response/read và acquire** khi dùng pool.
- Có total/per-route pool limits, pending queue bound và lifecycle đóng clients.
- Không có blocking I/O trên Netty event-loop.
- Có error handling theo cause và timeout stage, không dựa vào exception message.
- Có time budget cho toàn inbound request/call và retry/redirect.
- Có metrics/tracing cho pool pending, leased, connect latency, response latency, timeout rate.
- Có test server chậm, pool saturation, TLS/DNS/proxy tình huống kiểm soát.
- Có phân biệt config inbound server với outbound clients; có xác nhận API version thực.
- Có test staging đánh giá p95/p99/throughput chứ không chỉ manual curl một request.

**Câu hỏi ôn tập:**

1. A và B đang giữ hết connections pool, C chưa được cấp connection. Timeout nào quyết định khi C thất bại?
2. Connect TCP mất 100ms nhưng server đợi 10s mới trả headers. Timeout nào cần kiểm tra?
3. Vì sao `maxConnTotal=100` nhưng `maxConnPerRoute=2` vẫn có thể gây pool acquire timeout?
4. Phân biệt `RequestConfig.setConnectionRequestTimeout` và `ConnectionConfig.setConnectTimeout`.
5. Vì sao ví dụ Spring Boot 3.3 không gọi `.setReadTimeout()` trên `HttpComponentsClientHttpRequestFactory`?
6. Trong WebClient Reactor Netty, API nào đặt pending acquire timeout, API nào đặt connect timeout, API nào đặt response timeout?
7. Vì sao `HTTP 504` từ gateway không nhất thiết là exception read timeout ở client?
8. Khi response body không được đóng, trạng thái `leased/pending/available` có thể thay đổi thế nào?
9. Khi dùng retry ba lần, tại sao các timeout từng attempt không bảo đảm SLA 5 giây?
10. Tại sao `Mono.timeout(Duration.ofSeconds(5))` không thể thay thế điều chỉnh pool capacity?
11. Với SSE hoặc streaming download, vì sao read inactivity timeout và total deadline phải có policy khác REST request nhỏ?
12. Muốn tái hiện connect timeout, tại sao nên dùng môi trường mạng thử nghiệm có kiểm soát thay vì chỉ kết nối vào một port localhost không lắng nghe?

**Ghi nhớ:** một outbound HTTP call có thể **chờ connection từ pool**, **chờ tạo TCP connection** và **chờ response/đọc bytes**. Ba pha cần cấu hình và quan sát riêng. Với Spring Boot 3.3, đặt timeout ở **underlying HTTP engine/factory/connector** đúng version, dùng deadline nghiệp vụ cho toàn call khi cần, và kiểm soát pool/queueing để tránh cascade failures.

### Tài liệu tham khảo

- Spring Boot 3.3 — Calling REST Services, `RestClient`, `RestTemplate`, `WebClient`: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Boot 3.3 — HTTP Client how-to: https://docs.spring.io/spring-boot/3.3/how-to/http-clients.html
- Spring Framework 6.1 — `HttpComponentsClientHttpRequestFactory`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html
- Spring Framework 6.1 — `RestClient.Builder`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html
- Apache HttpClient 5.3 — `RequestConfig.Builder`: https://hc.apache.org/components/httpcomponents-client-5.3.x/5.3.1/httpclient5/apidocs/org/apache/hc/client5/http/config/RequestConfig.Builder.html
- Apache HttpClient 5.3 — `ConnectionConfig.Builder`: https://hc.apache.org/components/httpcomponents-client-5.3.x/5.3.1/httpclient5/apidocs/org/apache/hc/client5/http/config/ConnectionConfig.Builder.html
- Apache HttpClient 5.3 — Pooling Connection Manager builder: https://hc.apache.org/components/httpcomponents-client-5.3.x/5.3.1/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManagerBuilder.html
- Reactor Netty — HTTP Client timeout and connection provider: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Spring Framework — WebClient configuration and timeouts: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Java 17 — Duration API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html