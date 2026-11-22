# Thực hành đo và phân loại từng loại thời gian chờ

Một request từ `order-service` tới `catalog-service` có thể thất bại sau 300 ms vì **không mượn được kết nối từ pool**, sau 800 ms vì **không thiết lập được TCP**, hoặc sau 1.000 ms vì **server chưa trả phản hồi**. Cùng được gọi là “timeout”, nhưng ba lỗi này có nguyên nhân và cách khắc phục hoàn toàn khác nhau.

Trong **Spring Cloud LoadBalancer**, cần phân biệt thêm giai đoạn **tìm danh sách `ServiceInstance` và chọn bản sao** với giai đoạn HTTP client thực thi request. Tăng `readTimeout` thường không giải quyết được vấn đề discovery; còn tăng timeout của pool có thể chỉ che khuất hiện tượng thiếu connection hoặc request chưa được giải phóng.

Bài thực hành thuộc chương **Thời gian chờ** sẽ xây dựng một môi trường đo nhỏ, dùng `RestClient` với Apache HttpClient 5 làm bài chính, sau đó đối chiếu `WebClient`/Reactor Netty và Spring Cloud OpenFeign. Mục tiêu là **tạo được một triệu chứng có kiểm soát, đo được thời gian thực tế, nhận diện đúng tầng và chọn đúng tham số cần sửa**.

> Các cấu hình, endpoint và ngưỡng thời gian trong bài chỉ để thử nghiệm ở môi trường local/test. Không dùng các endpoint tạo độ trễ hoặc kỹ thuật làm rớt kết nối trong production.

## 1. Bản đồ thời gian của một lần gọi dịch vụ

Một lời gọi HTTP có thể đi qua các chặng sau:

~~~mermaid
flowchart TD
    A["Ứng dụng tạo request theo service ID"]
    B["Discovery / cache / lọc danh sách ServiceInstance"]
    C["LoadBalancer chọn instance"]
    D["Chờ connection pool cấp kết nối"]
    E["DNS nếu endpoint dùng hostname"]
    F["Kết nối TCP mới"]
    G["TLS handshake nếu HTTPS"]
    H["Gửi request"]
    I["Chờ response headers / byte đầu"]
    J["Đọc response body"]
    K["Decode, trả kết quả cho nghiệp vụ"]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J --> K
~~~

Sơ đồ diễn tả **các giai đoạn có thể xảy ra**, không nói rằng mọi request đều thực hiện tất cả. Khi connection pool trả về một kết nối đang sống, một số bước DNS, TCP và TLS có thể được **bỏ qua ở lần gọi đó**. Với HTTP/2 và proxy, đường đi còn có thêm các khác biệt về multiplexing hoặc route.

| Giai đoạn | Giới hạn thường gặp | Ai quản lý chủ yếu? | Khi lỗi, hỏi điều gì? |
|---|---|---|---|
| Discovery/selection | Discovery timeout hoặc timeout ở nguồn dữ liệu | Spring Cloud LoadBalancer, discovery client, supplier | Có tìm ra instance nào chưa? |
| Chờ pool cấp kết nối | Pool acquisition/lease timeout | Apache HttpClient, Reactor Netty connection provider | Pool có bị hết slot hoặc connection bị giữ quá lâu? |
| DNS | Resolver query timeout | DNS resolver/transport | Host của instance có phân giải được không? |
| TCP connect | Connect timeout | HTTP transport | Địa chỉ/port có thể thiết lập kết nối không? |
| TLS handshake | SSL/TLS handshake timeout | TLS stack/HTTP transport | Đã bắt tay bảo mật hoàn tất chưa? |
| Đợi phản hồi | Response/read timeout tùy thư viện | HTTP transport | Server có bắt đầu hoặc tiếp tục gửi response không? |
| Đọc response body | Socket read inactivity/response timeout | HTTP transport và body decoder | Body có bị ngắt quãng quá lâu? |
| Tổng một operation | End-to-end deadline | Tầng ứng dụng hoặc reactive pipeline | Tất cả attempts đã vượt ngân sách nghiệp vụ chưa? |

**Không có một “timeout chung của LoadBalancer” điều khiển toàn bộ các giai đoạn này.** Một thuộc tính timeout cụ thể luôn phải được gắn với API, HTTP client và phiên bản thư viện đang sử dụng.

## 2. Chuẩn bị môi trường thử nghiệm

Để quan sát rõ nhất, bắt đầu với **một bản sao** `catalog-service` ở cổng `8081` và một `order-service` làm client. Khi chỉ có một instance, việc mượn pool không bị phân tán qua các route khác nhau. Sau khi đã phân loại từng lỗi, thêm instance thứ hai ở `8082` để xem tác động của cân bằng tải.

Ví dụ dependency Gradle Kotlin DSL cho **server mô phỏng**, với Spring Boot và Spring Cloud BOM tương thích được cấu hình ở dự án:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Cho **client thử nghiệm dùng RestClient và Apache HttpClient 5**:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.apache.httpcomponents.client5:httpclient5")
}
~~~

Các snippet giả định Java 17+ và Spring Framework có `RestClient` (từ 6.1). Dependency không bao gồm một hệ thống service registry riêng vì bài thử nghiệm sử dụng `SimpleDiscoveryClient`.

### Cấu hình một instance tĩnh

Tại ứng dụng client:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
~~~

Đường dẫn `127.0.0.1` chỉ đúng khi server và client chạy trong cùng máy hoặc cùng network namespace. Trong container, phải thay bằng hostname/IP mà client có thể truy cập.

Dùng danh sách tĩnh giúp tách việc chọn `ServiceInstance` khỏi các biến động của registry. Tuy nhiên, khi server dừng, `SimpleDiscoveryClient` **không tự xóa** endpoint khỏi cấu hình.

## 3. Tạo backend mô phỏng phản hồi nhanh, chậm và ngắt quãng

Tạo controller **chỉ bật trong môi trường lab**:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class TimeoutLabController {

    @GetMapping("/lab/fast")
    String fast() {
        return "fast-ok";
    }

    @GetMapping("/lab/delay-headers")
    String delayHeaders(
            @RequestParam(defaultValue = "2500") long ms
    ) throws InterruptedException {
        long delay = Math.max(0, Math.min(ms, 5000));
        Thread.sleep(delay);
        return "delayed-ok";
    }

    @GetMapping(value = "/lab/gap-body",
                produces = MediaType.TEXT_PLAIN_VALUE)
    void gapBody(
            @RequestParam(defaultValue = "2500") long ms,
            HttpServletResponse response
    ) throws Exception {
        long delay = Math.max(0, Math.min(ms, 5000));

        response.getOutputStream().write(
                "part-1\n".getBytes(StandardCharsets.UTF_8));
        response.flushBuffer(); // Đẩy headers và phần body đầu ra.
        Thread.sleep(delay);
        response.getOutputStream().write(
                "part-2\n".getBytes(StandardCharsets.UTF_8));
        response.getOutputStream().flush();
    }
}
~~~

Ba đường dẫn tạo ba tình huống:

| Endpoint | Hành vi server | Dùng để đo |
|---|---|---|
| `/lab/fast` | Trả phản hồi ngay | Đường cơ sở và xác nhận kết nối |
| `/lab/delay-headers?ms=2500` | Chờ trước khi tạo response | Thời gian chờ response đầu tiên |
| `/lab/gap-body?ms=2500` | Gửi phần đầu, flush, chờ rồi gửi phần sau | Khoảng trống khi đọc response body |

`Thread.sleep` cố tình giữ servlet worker thread để mô phỏng backend chậm; không dùng pattern này trong ứng dụng production. Một số proxy, buffer hoặc runtime có thể làm thay đổi thời điểm byte thực sự tới client; với `gap-body` nên xác nhận bằng packet/network trace hoặc log client nếu kết quả không khớp.

### Đường cơ sở trước khi đo timeout

Gửi thử `GET /lab/fast` và kiểm tra:

- Server nhận request, trả HTTP 200.
- Client giải quyết `catalog-service` về đúng instance `127.0.0.1:8081`.
- Không có retry, circuit breaker hoặc proxy trung gian bất ngờ ảnh hưởng phép đo.

Nếu chưa có đường cơ sở thành công, không dùng các lỗi sau đó để suy ra tác động của timeout.

## 4. Cấu hình RestClient với từng loại giới hạn rõ ràng

Apache HttpClient 5 có thể phân biệt **chờ mượn connection**, **connect**, **socket I/O** và **response**. Cấu hình sau đặt một connection cho mỗi route để dễ tạo pool contention.

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class TimeoutLabClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient timeoutLabApacheClient() {
        var connectionManager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(2)
                        .setMaxConnPerRoute(1)
                        .setDefaultConnectionConfig(
                                ConnectionConfig.custom()
                                        .setConnectTimeout(
                                                Timeout.ofMilliseconds(800))
                                        .setSocketTimeout(
                                                Timeout.ofSeconds(5))
                                        .build())
                        .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(300))
                .setResponseTimeout(Timeout.ofSeconds(1))
                .build();

        return HttpClients.custom()
                .setConnectionManager(connectionManager)
                .setDefaultRequestConfig(requestConfig)
                .disableAutomaticRetries()
                .build();
    }

    @Bean("timeoutLabRestClientBuilder")
    @LoadBalanced
    RestClient.Builder timeoutLabRestClientBuilder(
            CloseableHttpClient timeoutLabApacheClient) {
        return RestClient.builder().requestFactory(
                new HttpComponentsClientHttpRequestFactory(
                        timeoutLabApacheClient));
    }

    @Bean("timeoutLabRestClient")
    RestClient timeoutLabRestClient(
            @Qualifier("timeoutLabRestClientBuilder")
            RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Giá trị đã đặt:

| Tham số Apache HttpClient 5 | Giá trị trong lab | Ý nghĩa |
|---|---|---|
| `setConnectionRequestTimeout` | 300 ms | Chờ lấy slot kết nối từ pool |
| `ConnectionConfig#setConnectTimeout` | 800 ms | Thiết lập kết nối mới |
| `ConnectionConfig#setSocketTimeout` | 5 s | Giá trị socket read/I/O nền |
| `setResponseTimeout` | 1 s | Chờ response theo ngữ nghĩa của HttpClient 5; có thể thay thế timeout socket trong message exchange |
| `setMaxConnPerRoute` | 1 | Dễ tái hiện nghẽn pool khi nhiều request tới cùng endpoint |
| `setMaxConnTotal` | 2 | Giới hạn tổng connection của manager |
| `disableAutomaticRetries` | Bật | Tránh transport tự chạy lại request và làm sai phép đo đơn lẻ |

**Ghi nhớ:** trên Apache HttpClient 5 mới, `RequestConfig#setConnectTimeout` đã deprecated; dùng `ConnectionConfig#setConnectTimeout` để cấu hình connect timeout. `RequestConfig#setResponseTimeout` **không phải deadline tổng** cho toàn bộ operation, đặc biệt khi có retry hoặc nhiều bước I/O.

Trong ví dụ, `@LoadBalanced` gắn vào `RestClient.Builder` để chọn instance; Apache client vẫn chịu trách nhiệm HTTP và pool. Nếu dự án cần các customizer của Spring Boot, xem xét tích hợp `RestClientBuilderConfigurer` thay vì tạo builder thô mà vô tình bỏ mất observability hoặc converter được Boot cài đặt.

## 5. Đo elapsed time và ghi chuỗi nguyên nhân lỗi

Dùng `System.nanoTime()` để đo thời gian đã trôi qua từ lúc gọi đến khi nhận kết quả/exception. Đây là **thời gian tổng nhìn từ ứng dụng**, không phải phép đo riêng giai đoạn TCP hay DNS.

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class TimeoutLabProbe {

    private final RestClient client;

    TimeoutLabProbe(
            @Qualifier("timeoutLabRestClient") RestClient client) {
        this.client = client;
    }

    void run(String relativeUri) {
        long started = System.nanoTime();

        try {
            String body = client.get()
                    .uri(relativeUri)
                    .retrieve()
                    .body(String.class);

            System.out.printf(
                    "OK uri=%s elapsedMs=%d body=%s%n",
                    relativeUri,
                    elapsedMillis(started),
                    body);
        } catch (Exception error) {
            System.out.printf(
                    "FAILED uri=%s elapsedMs=%d%n",
                    relativeUri,
                    elapsedMillis(started));

            Throwable current = error;
            while (current != null) {
                System.out.println(
                        "  cause=" + current.getClass().getName()
                        + " message=" + current.getMessage());
                current = current.getCause();
            }
        }
    }

    private static long elapsedMillis(long start) {
        return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
    }
}
~~~

Ví dụ chạy các đường dẫn từ ứng dụng kiểm thử:

~~~java
probe.run("/lab/fast");
probe.run("/lab/delay-headers?ms=2500");
probe.run("/lab/gap-body?ms=2500");
~~~

Giá trị đo phụ thuộc scheduling, network, load của máy, proxy và transport. Không đặt tiêu chí “bằng đúng 1.000 ms”; hãy so sánh phạm vi và loại exception.

### Mẫu nhật ký cần thu thập

~~~text
traceId=lab-001
serviceId=catalog-service
selectedInstance=127.0.0.1:8081
endpoint=/lab/delay-headers
elapsedMs=1008
error=...timeout...
attempt=1
~~~

Đây là **mẫu log do người học tự thiết kế**, không phải field mặc định của Spring Cloud. Các thông tin `selectedInstance` và `attempt` phải được instrument từ LoadBalancer/HTTP layer nếu muốn ghi đúng giá trị thực.

## 6. Thực hành A — Phản hồi chậm: response timeout

**Mục tiêu:** thấy khác biệt giữa server trả chậm và lỗi connect.

Điều kiện: server ở `8081` đang chạy, client chỉ có một instance, `responseTimeout = 1 s`.

Thực hiện:

1. Gọi `/lab/fast` để xác minh đường kết nối hoạt động.
2. Gọi `/lab/delay-headers?ms=2500`, cho server chờ 2,5 s trước khi gửi response.
3. Ghi thời gian elapsed, exception chain và log server có nhận request hay không.
4. Trong lần đo riêng, nâng response timeout thành 4 s và gọi lại endpoint tương tự.
5. So sánh thành công/thất bại khi chỉ thay đổi timeout phản hồi.

Kết quả thường quan sát:

| Request | Response timeout | Kỳ vọng |
|---|---|---|
| `/lab/fast` | 1 s | Thành công, nhanh hơn timeout |
| `/lab/delay-headers?ms=2500` | 1 s | Client thường timeout khi chờ phản hồi |
| `/lab/delay-headers?ms=2500` | 4 s | Có thể thành công nếu network và server ổn định |

Nếu server đã ghi nhận request nhưng client không nhận được response đúng hạn, nghi vấn chính nằm ở giai đoạn backend/proxy phản hồi hoặc đọc HTTP, **không phải LoadBalancer không tìm thấy bản sao**.

Không dùng phép đo này để khẳng định server chậm nhất đúng 2,5 giây trong production: đây là một server mô phỏng, chưa có DB, queue, GC, thread pool hay dependency phía sau.

## 7. Thực hành B — Body bị ngắt quãng: read/socket inactivity

**Mục tiêu:** phân biệt “đã nhận response headers/byte đầu” với “đã đọc xong toàn bộ body”.

Gọi:

~~~http
GET http://catalog-service/lab/gap-body?ms=2500
~~~

Server gửi `part-1`, flush rồi chờ 2,5 s mới gửi `part-2`. Với `retrieve().body(String.class)`, lời gọi chỉ kết thúc khi nội dung body được đọc và giải mã xong hoặc khi có lỗi.

Nếu transport áp dụng giới hạn đọc/response ngắn hơn khoảng ngừng gửi body, client **có thể timeout giữa chừng**, dù request đã được server tiếp nhận và headers đã đến nơi.

Để xác định đó là timeout khi đọc body, không chỉ nhìn tổng elapsed:

- Ghi thời điểm server gửi phần đầu và phần sau.
- Kiểm tra log HTTP client hoặc packet trace xem headers/`part-1` đã đến chưa.
- So sánh với `/lab/delay-headers` (trường hợp server chưa gửi gì).
- Kiểm tra liệu `responseTimeout` đang ghi đè `socketTimeout` trong phiên bản/transport được dùng.

**Cảnh báo:** Apache HttpClient 5 định nghĩa response timeout ở cấp trao đổi HTTP và có thể áp dụng cho giai đoạn đọc; không nên mặc định rằng nó chỉ giới hạn “time to first byte”. Muốn đo **TTFB** chính xác, cần marker ở HTTP transport hoặc network trace; `System.nanoTime()` bao quanh `body(String.class)` chỉ cho biết thời gian nhận **đầy đủ body**.

## 8. Thực hành C — Chờ connection pool: pool acquisition timeout

**Mục tiêu:** tạo timeout trước khi request thứ hai được gửi tới backend.

Giữ `maxConnPerRoute = 1`, `connectionRequestTimeout = 300 ms` và chỉ một instance ở `8081`. Trong bài test này cần **tăng response timeout lên 5 giây**, để request thứ nhất có thể giữ connection đủ lâu.

1. Gửi request thứ nhất tới `/lab/delay-headers?ms=3000` trong một thread.
2. Khi server đã log request thứ nhất được nhận, gửi ngay request thứ hai từ một thread khác tới cùng endpoint.
3. Vì pool chỉ có một connection cho route, request thứ hai phải chờ slot.
4. Quan sát request thứ hai hết hạn chờ mượn pool khoảng 300 ms, trong khi server có thể **chưa nhận** request thứ hai.
5. Đo lại sau khi tăng `maxConnPerRoute` lên 2; lúc đó cả hai request có cơ hội chạy đồng thời.

~~~mermaid
sequenceDiagram
    participant A as Thread A
    participant B as Thread B
    participant Pool as HTTP connection pool
    participant Server as catalog-service
    A->>Pool: Xin connection
    Pool-->>A: Cấp slot duy nhất
    A->>Server: GET /delay-headers 3000ms
    B->>Pool: Xin connection cùng route
    Note over B,Pool: Chờ trên 300ms
    Pool-->>B: Pool lease timeout
    Server-->>A: HTTP 200 sau 3000ms
    A->>Pool: Trả connection vào pool
~~~

Trong tình huống này, kết quả lỗi ở B không chứng minh backend bị chậm trả response cho B: B còn chưa có connection để gửi. **Tăng connect timeout không sửa được thiếu slot trong pool.**

Việc cho hai thread khởi động cùng lúc chưa bảo đảm thread nào mượn connection trước; để lặp lại ổn định, chờ server nhận request thứ nhất hoặc quan sát `leased=1` rồi mới gửi request thứ hai.

### Đo pool như thế nào?

Với Apache HttpClient 5, có thể đo `PoolingHttpClientConnectionManager.getTotalStats()` và `getStats(route)` ở lớp connection manager để xem số connection đang `leased`, `pending` và `available`. Nếu muốn quan sát, cần giữ tham chiếu đến manager đã tạo làm bean hoặc instrument nó; đoạn cấu hình ban đầu chỉ cho thấy cách tạo pool, không tự xuất các metric này.

## 9. Thực hành D — TCP connect timeout và lỗi kết nối bị từ chối

**Mục tiêu:** không nhầm kết nối tới port đã đóng với kết nối bị drop.

Hai kịch bản khác nhau:

| Thí nghiệm | Cách tạo | Kết quả thường gặp |
|---|---|---|
| **Connection refused** | Dừng server trên một port vẫn được discovery trả về | Hệ điều hành có thể trả lỗi từ chối rất nhanh, **không cần chờ hết connect timeout** |
| **Connect timeout** | Ở mạng thử nghiệm, dùng proxy/network fault injection để **drop** các gói thiết lập TCP mà không trả RST | Kết nối chờ tới connect timeout hoặc tới giới hạn khác của hệ thống |

Không dựa vào một IP “trông có vẻ không tồn tại” để khẳng định chắc chắn sẽ có connect timeout: tùy mạng, kết quả có thể là `Network unreachable`, `No route to host` hoặc từ chối ngay lập tức.

Quy trình:

1. Giữ `connectTimeout = 800 ms` và bảo đảm pool phải tạo **kết nối mới** (không tái sử dụng socket cũ).
2. Kiểm tra kịch bản `Connection refused` với server đã dừng.
3. Dùng công cụ fault injection trong mạng lab để mô phỏng drop SYN; đo thời gian và exception.
4. Gỡ fault injection; xác nhận gọi `/lab/fast` thành công trở lại.

Ở bước này, kiểm tra packet/network trace giúp chứng minh giai đoạn TCP chưa thiết lập, thay vì chỉ dựa vào `elapsedMs`.

## 10. Thực hành E — DNS và TLS handshake timeout

Hai giai đoạn này cũng nằm trước lúc HTTP request nghiệp vụ nhận phản hồi, nhưng **không được giả định chúng chịu cùng `connectTimeout`** trong mọi client.

### DNS

Nếu instance có URI dạng `http://catalog.internal:8081`, HTTP transport có thể phải phân giải hostname `catalog.internal`. Ngược lại, với URI `http://127.0.0.1:8081`, không có truy vấn DNS cho hostname đích.

- Domain sai hoặc không tồn tại có thể gây `UnknownHostException`/name resolution error rất nhanh; **đó không mặc nhiên là DNS timeout**.
- DNS timeout thực sự cần DNS resolver không trả lời hoặc truy vấn bị drop trong môi trường thử nghiệm.
- Java/JDK HTTP transport, Apache HttpClient và Reactor Netty có resolver cùng cơ chế timeout khác nhau. Không có một thuộc tính Spring Cloud LoadBalancer duy nhất quản lý DNS timeout cho mọi adapter.

Với Reactor Netty, DNS resolver có tùy chọn `queryTimeout` và có thể quan sát metric resolver timing. Không đưa cấu hình của Reactor Netty vào Apache HttpClient hoặc Feign dùng transport khác.

### TLS handshake

Với endpoint HTTPS, sau khi mở TCP còn có giai đoạn thương lượng TLS. Có thể phân biệt:

- `SSLHandshakeException` do chứng chỉ sai, protocol mismatch hoặc trust store: đây là **lỗi TLS**, không nhất thiết là timeout.
- TLS handshake timeout: hai bên không hoàn tất thương lượng đúng hạn, cần kiểm tra timeout handshake của transport và trace.
- Connect timeout có thể bao gồm một phần chi phí transport-security tùy implementation; không nên suy luận tất cả phiên bản cùng tính thời gian như nhau.

Để thực hành TLS timeout, sử dụng **TLS proxy thử nghiệm** được cấu hình giữ kết nối nhưng không trả lời handshake, không phá/disable certificate validation ở production. Với Reactor Netty có thể đặt `handshakeTimeout` cho SSL provider; Apache HttpClient có API/lifecycle kết nối TLS riêng.

## 11. WebClient/Reactor Netty: so sánh cùng bài thử nghiệm

Nếu sử dụng `WebClient` với Reactor Netty, có thể cấu hình pool, connect timeout và response timeout bằng các API của Netty, thay vì sao chép cấu hình Apache HttpClient 5.

Ví dụ client dùng Spring WebFlux và Spring Cloud LoadBalancer:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
class ReactiveTimeoutLabConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider timeoutLabConnectionProvider() {
        return ConnectionProvider.builder("timeout-lab")
                .maxConnections(1)
                .pendingAcquireTimeout(Duration.ofMillis(300))
                .build();
    }

    @Bean
    @LoadBalanced
    WebClient.Builder timeoutLabWebClientBuilder(
            ConnectionProvider timeoutLabConnectionProvider) {

        HttpClient httpClient = HttpClient
                .create(timeoutLabConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800)
                .responseTimeout(Duration.ofSeconds(1));

        return WebClient.builder().clientConnector(
                new ReactorClientHttpConnector(httpClient));
    }
}
~~~

Với WebClient này, các API có ý nghĩa:

| Reactor Netty | Mục đích |
|---|---|
| `pendingAcquireTimeout` | Thời gian chờ mượn connection |
| `CONNECT_TIMEOUT_MILLIS` | Thời gian thiết lập kết nối TCP |
| `responseTimeout(Duration)` | Giới hạn thời gian chờ/đọc phản hồi theo Netty |
| SSL provider `handshakeTimeout` | Giới hạn TLS handshake |
| DNS resolver `queryTimeout` | Giới hạn mỗi truy vấn DNS |
| Reactor `Mono.timeout(Duration)` | Giới hạn thời gian ở cấp publisher đã được subscribe |

Ví dụ một deadline trên **toàn bộ publisher**:

~~~java
WebClient client = timeoutLabWebClientBuilder
        .baseUrl("http://catalog-service")
        .build();

String body = client.get()
        .uri("/lab/delay-headers?ms=2500")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2))
        .block();
~~~

Trong ví dụ, `responseTimeout(1s)` ở tầng Netty có thể xảy ra **trước** `Mono.timeout(2s)`. Để quan sát riêng `Mono.timeout`, hãy tăng response timeout trong một lần chạy riêng, rồi so sánh kết quả.

Nếu có `retryWhen(...)`, vị trí đặt `timeout(...)` rất quan trọng: đặt timeout **bên ngoài** toàn bộ chuỗi retry có thể giới hạn tổng thời gian subscription, trong khi đặt timeout ở trong nhánh được retry có thể áp dụng lại cho từng attempt. Cũng cần cân nhắc việc cancel request phía client không bảo đảm backend đã dừng công việc.

Reactor Netty có metrics theo phase như `reactor.netty.http.client.connect.time`, `...tls.handshake.time`, `...address.resolver` và `reactor.netty.connection.provider.pending.connections.time` khi bật Micrometer instrumentation tương ứng. Không nên suy ra số đo phase chỉ từ đồng hồ quanh `block()`.

## 12. OpenFeign: connectTimeout/readTimeout và giới hạn của phép đo

Spring Cloud OpenFeign cung cấp hai thuộc tính timeout thông dụng ở mức named client:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            connectTimeout: 800
            readTimeout: 1000
~~~

Các giá trị trên sử dụng **milliseconds** theo cấu hình Feign. Mã Feign có thể khai báo:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogProbeFeignClient {

    @GetMapping("/lab/fast")
    String fast();

    @GetMapping("/lab/delay-headers")
    String slow(@RequestParam("ms") long ms);
}
~~~

`connectTimeout` giới hạn kết nối mới; `readTimeout` tác động giai đoạn nhận response theo Feign/transport. Chúng không tách rõ tất cả các giai đoạn pool lease, DNS hay TLS khi bạn chỉ nhìn cấu hình Feign. Nếu Feign dùng Apache HttpClient 5 bên dưới, những giai đoạn đó còn chịu các tùy chọn của connection manager.

Để thử nghiệm cho kết quả dễ giải thích:

- Chạy một request `fast()` làm đường cơ sở.
- Chạy `slow(2500)` và ghi thời gian, exception chain.
- Bật/tắt cấu hình URL cố định chỉ khi cần so sánh transport trực tiếp với lời gọi theo service ID.
- Kiểm tra có đang dùng `FeignBlockingLoadBalancerClient` hay Feign `Client` tùy biến khác.
- Đảm bảo retry được xác định rõ. Spring Cloud OpenFeign thường đăng ký `Retryer.NEVER_RETRY` theo cấu hình mặc định, nhưng LoadBalancer hoặc lớp resilience khác có thể bổ sung retries tùy dependency và thiết lập.

**Đừng kết luận rằng `readTimeout: 1000` đồng nghĩa toàn bộ business call luôn kết thúc trong 1 giây** nếu có queue, DNS, nhiều attempts hoặc xử lý trước/sau HTTP.

## 13. Discovery/LoadBalancer delay khác network timeout

Một lời gọi theo service ID có thể chậm **trước khi HTTP client có đích vật lý**:

~~~text
order-service
  -> lấy danh sách instance cho catalog-service
  -> lọc theo health/zone/hint
  -> chọn ServiceInstance
  -> mượn connection / DNS / TCP / TLS
  -> gửi HTTP và chờ response
~~~

Nếu discovery chậm hoặc supplier thực hiện health/refetch đồng bộ với request, thời gian chờ ở giai đoạn này có thể làm tăng thời gian tổng. Spring Cloud LoadBalancer có thuộc tính liên quan như `spring.cloud.loadbalancer.service-discovery.timeout` trong những phiên bản hỗ trợ, nhưng phải kiểm tra **nó áp dụng cho luồng discovery nào** và không đánh đồng với connect timeout của Apache/Netty.

Ba tình huống cần phân biệt:

| Triệu chứng | Khả năng |
|---|---|
| Không có `ServiceInstance` sau lookup | Discovery/supplier rỗng hoặc lọc hết ứng viên; không nhất thiết có HTTP request tới backend |
| Có instance được chọn, HTTP connect bị timeout | Lỗi kết nối transport đến instance đã chọn |
| Có instance được chọn, server nhận request nhưng response chậm | Lỗi/độ trễ backend, proxy hoặc đọc response |

Một code đo `start` trước khi gọi Feign/RestClient và `end` sau khi nhận body **gộp tất cả**: discovery, pool, connect, response, decoding, có thể cả retry. Để tách giai đoạn, cần instrumentation tại điểm lựa chọn instance và tại HTTP transport.

## 14. Tránh sai lệch phép đo do retry và các giới hạn chồng nhau

Một request có thể bị timeout rồi tự gửi lại ở nhiều tầng:

- HTTP client có retry riêng.
- Spring Cloud LoadBalancer có cơ chế retry nếu dependency/chính sách phù hợp.
- Spring Retry hoặc Resilience4j áp dụng retry/circuit breaker phía application.
- Gateway hoặc proxy cũng có thể retry tùy cấu hình.

Khi đo **một loại timeout**, nên tắt hoặc kiểm soát rõ retry ở từng tầng. Nếu không, `elapsedMs` có thể phản ánh ba attempts, mỗi attempt chờ tối đa một ngưỡng khác nhau.

Ví dụ tổng thời gian minh họa:

~~~text
Attempt 1:  response timeout ~1000ms
Backoff:                          100ms
Attempt 2:  response timeout ~1000ms
Backoff:                          200ms
Attempt 3:  response thành công   300ms
Tổng thao tác:                   ~2600ms + overhead
~~~

Đây không phải công thức tổng quát: acquisition, connect, retry/backoff, lịch CPU, truyền body và các giới hạn khác có thể làm kết quả chênh lệch.

Với `POST` tạo đơn hàng hoặc thanh toán, timeout không chứng minh request chưa được server xử lý. Mọi thiết kế retry cần đánh giá idempotency và sử dụng idempotency key hoặc logic chống trùng nếu thích hợp.

### Deadline tổng phải được đặt theo ngân sách nghiệp vụ

Ví dụ gọi dịch vụ giá có ngân sách 2 giây:

1. Xác định budget cho **cả nghiệp vụ**, không chỉ một attempt.
2. Phân phối ngân sách giữa discovery/pool, connect, response và retry.
3. Trừ thời gian đã sử dụng trước khi bắt đầu attempt tiếp theo.
4. Nếu không đủ thời gian để có kết quả hữu ích, dừng retry và trả lỗi rõ ràng.

Các giá trị cấu hình nên được đo trên p95/p99 thực tế và khả năng backend, không chọn chỉ theo cảm giác. Deadline cần có cơ chế hủy/phối hợp ở phía client; backend vẫn có thể tiếp tục xử lý nếu không hỗ trợ cancellation.

## 15. Bảng nhận diện lỗi sau thí nghiệm

| Tình huống | Dấu hiệu có thể thấy | Cách xác minh | Không nên sửa bằng cách |
|---|---|---|---|
| Pool lease timeout | Leased đạt giới hạn, pending tăng; request chưa tới backend | Pool stats/metrics theo route | Tăng connect timeout |
| TCP connect timeout | Không hoàn tất TCP handshake trong hạn | Packet trace, exception liên quan connect | Tăng read timeout |
| Connection refused | Host trả RST hoặc không lắng nghe port; thường lỗi nhanh | Kiểm tra server listener, kết nối mạng | Chờ hết connect timeout rồi kết luận |
| DNS resolution error/timeout | Không có IP đích hoặc resolver không trả lời | Resolver logs/metrics, DNS test | Chỉ tăng LoadBalancer TTL |
| TLS handshake error/timeout | TCP có thể đã mở, SSL chưa hoàn tất | TLS trace, SSL exception hoặc handshake timer | Bỏ xác thực chứng chỉ |
| Response headers chậm | Server đã nhận request, chưa gửi response đúng hạn | Log server, HTTP transport tracing | Tăng connection pool vô hạn |
| Body read gap | Đã nhận một phần response rồi đợi dữ liệu tiếp | Log từng chunk, packet trace | Gọi đó là connect timeout |
| End-to-end deadline | Tổng operation vượt budget, có thể gồm retries | Trace spans và số attempts | Coi một readTimeout là deadline tổng |
| Không có instance | Supplier/LoadBalancer chưa chọn đích | Discovery logs, selected instance=null | Tăng socket timeout |

Nếu exception bị Spring bọc trong `ResourceAccessException`, cần duyệt **cause chain**. Loại exception sâu bên trong và timestamp các giai đoạn quan trọng hơn một dòng “Request timed out” chung chung.

## 16. Ghi số liệu và đánh giá kết quả

Sử dụng cùng một bảng kết quả cho mỗi lần chạy, thay đổi **một tham số mỗi lần**:

| Lần thử | Client | Endpoint/điều kiện | Timeout đang khảo sát | Elapsed thực tế | Instance đã chọn | Exception/cause | Kết luận |
|---|---|---|---|---|---|---|---|
| 1 | RestClient | `/lab/fast` | Baseline | Tự đo | Tự ghi | — | Đường đi hoạt động |
| 2 | RestClient | `/delay-headers?ms=2500` | Response 1 s | Tự đo | Tự ghi | Tự ghi | Xác định response timeout |
| 3 | RestClient | `/gap-body?ms=2500` | Body read gap | Tự đo | Tự ghi | Tự ghi | Đối chiếu headers/body |
| 4 | RestClient | 2 request cùng route, pool=1 | Lease 300 ms | Tự đo | Tự ghi | Tự ghi | Pool contention |
| 5 | RestClient | Port đã đóng | Connect/refused | Tự đo | Tự ghi | Tự ghi | Lỗi nhanh không phải timeout |
| 6 | WebClient | Chờ pool / delay-headers | Acquire/response | Tự đo | Tự ghi | Tự ghi | So sánh Reactor Netty |
| 7 | Feign | `slow(2500)` | Read timeout 1 s | Tự đo | Tự ghi | Tự ghi | So sánh cấu hình Feign |

**Lưu ý:** `/delay-headers` và `/gap-body` trong bảng dùng tiền tố `/lab` theo controller ở mục 3; khi gọi thật hãy sử dụng đường dẫn đầy đủ `/lab/delay-headers` và `/lab/gap-body`.

Để kết luận có cơ sở:

1. Chạy vài lần để phân biệt nhiễu scheduling/network với lỗi tái hiện ổn định.
2. Ghi cấu hình và version của HTTP transport cho mỗi lần đo.
3. Xác minh đã chọn được `ServiceInstance` trước khi quy trách nhiệm cho HTTP.
4. Với pool/TCP/TLS/DNS, dùng metrics hoặc trace đúng giai đoạn; **elapsed bên ngoài là bằng chứng hỗ trợ, không phải bằng chứng duy nhất**.
5. Khi thử lại với cấu hình mới, chỉ thay đổi một yếu tố và giữ nguyên tải, số instance, endpoint và trạng thái connection pool nếu có thể.

## 17. Checklist khi tối ưu timeout thực tế

- Lời gọi theo service ID có thực sự đi qua Spring Cloud LoadBalancer không?
- Discovery đã tìm được instance và có cần một timeout riêng cho truy vấn discovery?
- HTTP transport hiện tại là Apache HttpClient 5, Reactor Netty, JDK HttpClient hay một Feign delegate khác?
- Đã đo riêng **pool acquisition**, **TCP connect**, **TLS handshake**, **response** và **body read** nếu cần chưa?
- Có đang nhầm `Connection refused` hoặc `UnknownHostException` với một timeout được đợi hết hạn?
- Connection pool có bị nghẽn do giới hạn mỗi route hoặc response không được giải phóng?
- Proxy/gateway có timeout riêng ngắn hơn hoặc retry gây nhiễu kết quả không?
- Có cần deadline tổng cho nghiệp vụ, thay vì chỉ các timeout riêng lẻ?
- Số attempts, backoff và idempotency đã được xem xét trước khi bật retry chưa?
- Metrics, tracing và correlation ID có đủ để liên hệ instance được chọn với lỗi HTTP không?

**Kết luận:** “Request timeout” không phải một loại lỗi duy nhất. Thí nghiệm có kiểm soát phải chứng minh request đang **chờ dữ liệu discovery**, **chờ pool**, **mở kết nối**, **bắt tay TLS**, **chờ phản hồi**, **đọc body** hay **vượt deadline tổng**. Khi đã xác định đúng giai đoạn, ta mới có thể chọn tham số phù hợp cho `RestClient`, `WebClient` hoặc OpenFeign mà không tăng thời gian chờ một cách mù quáng.

**Tài liệu tham khảo chính thức:**

- [Apache HttpClient 5 – RequestConfig.Builder](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/RequestConfig.Builder.html)
- [Apache HttpClient 5 – ConnectionConfig.Builder](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/ConnectionConfig.Builder.html)
- [Reactor Netty – HTTP Client: Timeout Configuration và Metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Spring Cloud OpenFeign – Timeout Handling](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)

