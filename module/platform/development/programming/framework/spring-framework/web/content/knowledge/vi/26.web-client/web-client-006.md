# WebClient: Timeout, Connection Pool, TLS và giới hạn bộ nhớ codec

## 1. Bức tranh tổng thể

`WebClient` của Spring WebFlux là HTTP client bất đồng bộ, non-blocking. Khi sử dụng **Reactor Netty** làm HTTP connector (mặc định phổ biến khi có `spring-boot-starter-webflux`), một request chịu tác động từ nhiều tầng:

```text
WebClient (Spring)
    │  mã hóa request / giải mã response bằng HTTP message codecs
    ▼
ReactorClientHttpConnector
    ▼
Reactor Netty HttpClient
    ├── ConnectionProvider: kết nối tái sử dụng, số lượng tối đa, hàng đợi chờ
    ├── DNS, TCP connect, proxy (nếu có)
    ├── TLS handshake + xác thực chứng chỉ/hostname (HTTPS)
    └── Gửi HTTP request → chờ/đọc HTTP response
    ▼
Spring codecs: đọc/chuyển body → Mono<T> / Flux<T>
```

Bốn nhóm cấu hình trong bài bảo vệ **bốn loại tài nguyên/trạng thái khác nhau**:

- **Timeout:** tránh request treo khi chờ kết nối, TLS, byte phản hồi hoặc vượt hạn tổng thể.
- **Connection pool:** giới hạn số kết nối và số request đợi, giảm chi phí thiết lập TCP/TLS nhiều lần.
- **TLS:** mã hóa đường truyền, xác thực server bằng certificate chain/hostname; khi cần có thể thêm chứng chỉ client cho mTLS.
- **`maxInMemorySize` của codec:** hạn chế lượng dữ liệu được gom trong bộ nhớ trong lúc decode; tránh tiêu tốn bộ nhớ vô hạn vì response lớn.

Các thông số mẫu dưới đây là **giá trị minh họa để học**. Chọn cấu hình production từ SLO, đặc điểm upstream, kích thước payload và kết quả load test, không lấy con số mẫu làm mặc định cho mọi hệ thống.

## 2. Các loại timeout: hiểu đúng phạm vi trước khi cấu hình

| Loại | Bắt đầu/kết thúc, ý nghĩa | Cấu hình tiêu biểu |
| --- | --- | --- |
| Chờ lấy kết nối từ pool | Đợi connection rảnh/có thể tạo connection mới; quá hạn thì acquire thất bại | `ConnectionProvider.pendingAcquireTimeout(Duration)` |
| TCP connect | Đợi bắt tay TCP tới địa chỉ remote; không bao gồm toàn bộ HTTP response | `HttpClient.option(ChannelOption.CONNECT_TIMEOUT_MILLIS, ms)` |
| TLS handshake | Đợi bắt tay TLS khi dùng HTTPS; độc lập với timeout kết nối TCP | `HttpClient.secure(ssl -> ssl.handshakeTimeout(...))` |
| Đọc HTTP response | Giới hạn khoảng lặng **giữa các lần đọc dữ liệu từ network** trong một response, không phải deadline cho toàn bộ giao dịch | `HttpClient.responseTimeout(Duration)` |
| Read/Write I/O tùy chọn | Giám sát khoảng thời gian không đọc/ghi theo Netty handler; phạm vi có thể khác `responseTimeout` | `ReadTimeoutHandler` / `WriteTimeoutHandler` |
| Tổng pipeline reactive | Một `Mono`/`Flux` không phát tín hiệu tiếp theo đúng hạn thì bị hủy, phụ thuộc chỗ đặt operator | `mono.timeout(Duration)`, hoặc một chiến lược deadline xuyên nhiều bước |

**Quan trọng:** `responseTimeout(Duration)` trong Reactor Netty mô tả khoảng thời gian tối đa giữa các lần *network read* khi đọc response. Một stream liên tục nhận chunk nhỏ có thể chạy lâu hơn giá trị này mà không timeout. Nếu nghiệp vụ yêu cầu “toàn bộ lời gọi hoàn thành trong 3 giây”, cần timeout tổng trên publisher hoàn tất toàn bộ request (và cân nhắc nhiều lần retry cùng chia sẻ một ngân sách thời gian). `CONNECT_TIMEOUT_MILLIS` không giới hạn thời gian DNS, pool acquisition hoặc đọc response; tùy môi trường, DNS/proxy cũng có timeout riêng.

Ví dụ tạo `HttpClient` dùng chung:

```java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
    .responseTimeout(Duration.ofSeconds(5));
```

Sau đó gắn qua Spring:

```java
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
    .baseUrl("https://api.example.com")
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();

Mono<String> result = webClient.get()
    .uri("/health")
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(8)); // Deadline cho publisher này
```

Đây là đoạn minh họa; thêm import `reactor.core.publisher.Mono` nếu dùng độc lập và thay server bằng endpoint thật. `timeout()` phát lỗi timeout reactive khi hết hạn và hủy subscription, **không thay** cấu hình connect/pool/TLS/read ở tầng transport. Khi cùng đặt nhiều timeout, giới hạn nào đạt trước sẽ quyết định biểu hiện thực tế. Không phân biệt nguyên nhân bằng cách chỉ nhìn tên một exception; cần xem *cause chain* và metrics.

### Per-request timeout và nguy cơ dùng nhầm ReadTimeoutHandler

`HttpClient.responseTimeout(...)` đặt mức mặc định cho các request của `HttpClient`. Reactor Netty cũng hỗ trợ ghi đè ở mức `HttpClientRequest` (trong callback `doOnRequest`/`httpRequest`, khi API/connector cho phép). Điều này phù hợp khi phần lớn endpoint nhanh nhưng một endpoint streaming cần read interval lớn hơn.

Một số ví dụ trên mạng dùng:

```java
HttpClient client = HttpClient.create()
    .doOnConnected(connection -> connection
        .addHandlerLast(new io.netty.handler.timeout.ReadTimeoutHandler(10))
        .addHandlerLast(new io.netty.handler.timeout.WriteTimeoutHandler(10)));
```

Hai handler giám sát tình trạng I/O của **channel** (tham số trên là giây), có thể ảnh hưởng tới kết nối tái sử dụng và luồng streaming. Nếu mục tiêu chỉ là chờ/đọc HTTP response, ưu tiên `responseTimeout` của Reactor Netty; thêm I/O handler khi có yêu cầu riêng và đã hiểu lifecycle của chúng.

## 3. Connection pool: chia sẻ, giới hạn và tái sử dụng

Mỗi lần mở TCP/TLS mới có chi phí thời gian, CPU và socket. Connection pool giữ connection đủ điều kiện sau một response để request khác có thể sử dụng lại (tuân thủ keep-alive và HTTP protocol). Tái sử dụng giúp giảm kết nối mới, nhưng pool không tự làm upstream xử lý nhanh hơn.

Cấu hình mẫu:

```java
import java.time.Duration;
import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;

ConnectionProvider provider = ConnectionProvider.builder("partner-api-pool")
    .maxConnections(100)
    .pendingAcquireMaxCount(200)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .maxIdleTime(Duration.ofSeconds(20))
    .maxLifeTime(Duration.ofMinutes(5))
    .evictInBackground(Duration.ofSeconds(30))
    .build();

HttpClient httpClient = HttpClient.create(provider)
    .responseTimeout(Duration.ofSeconds(5));
```

Giải thích:

- `maxConnections(100)`: tối đa 100 kết nối hoạt động trong **mỗi pool key** (ví dụ remote authority/proxy tùy cấu hình); không hiểu là đúng 100 kết nối tổng toàn bộ JVM cho mọi host.
- `pendingAcquireMaxCount(200)`: số yêu cầu chờ lấy kết nối tối đa trong queue khi pool đã bận. Đây là hàng đợi admission, không phải 200 kết nối bổ sung.
- `pendingAcquireTimeout(2s)`: sau 2 giây mà chưa lấy được connection, yêu cầu thất bại; timeout này khác TCP connect.
- `maxIdleTime(20s)`: connection rảnh quá lâu đủ điều kiện loại bỏ. Chọn phù hợp, thường không dài hơn idle timeout của server/load balancer.
- `maxLifeTime(5m)`: tuổi thọ tối đa của connection trước khi cần loại khỏi pool. Không đồng nghĩa một request đang chạy sẽ bị ngắt đúng khi chạm mốc.
- `evictInBackground(30s)`: dọn các connection đủ điều kiện loại bỏ theo chu kỳ; nếu không bật, việc kiểm tra còn diễn ra tại các thời điểm acquire/release theo triển khai.

**Pool dùng cho ứng dụng:** thường tạo `WebClient`/`HttpClient`/`ConnectionProvider` dưới dạng bean chia sẻ, tái sử dụng giữa các request thay vì tạo pool mới cho mỗi HTTP call.

```java
@Configuration
class PartnerClientConfig {
    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerPool() {
        return ConnectionProvider.builder("partner-api-pool")
            .maxConnections(100)
            .pendingAcquireMaxCount(200)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .build();
    }

    @Bean
    WebClient partnerWebClient(ConnectionProvider partnerPool) {
        HttpClient http = HttpClient.create(partnerPool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(5));
        return WebClient.builder()
            .baseUrl("https://api.example.com")
            .clientConnector(new ReactorClientHttpConnector(http))
            .build();
    }
}
```

Đây là cấu hình minh họa, cần imports `org.springframework.context.annotation.*`, `WebClient`, `HttpClient`, `ConnectionProvider`, `ChannelOption`, `ReactorClientHttpConnector`, `Duration`. Khi dùng Spring Boot, có thể inject builder được Boot auto-configure để giữ các customizer của ứng dụng; nhớ gắn connector trước khi `build()`.

**Lifecycle:** chỉ dispose pool **do chính mình tạo và sở hữu** khi dừng ứng dụng; không dispose sau từng request. Spring WebClient với Reactor Netty mặc định dùng tài nguyên toàn cục được chia sẻ; không nên vô tình tắt global resources của thành phần khác. Khi tạo cấu hình resources riêng và đặt ứng dụng vào container có thể restart tại chỗ, quản lý tài nguyên bằng Spring bean/`ReactorResourceFactory` để tránh leak threads/connections.

### Quá tải pool và chẩn đoán

Nếu có 100 request dùng đồng thời mà `maxConnections=10`, chỉ 10 connection có thể đang phục vụ cùng lúc trong pool (giản lược HTTP/1.1); các request còn lại chờ, rồi có thể gặp acquire timeout hoặc queue limit. Tăng pool quá lớn có thể gây áp lực lên upstream, socket, file descriptors hoặc ephemeral ports. Nếu response body không được đọc/hủy đúng cách, connection cũng có thể bị giữ lâu.

Theo dõi ít nhất: số connection active/idle/pending theo pool, acquire latency, acquire timeout, connect/TLS timeout, response latency và error rate; dùng Reactor Netty metrics với Micrometer/Actuator nếu đã tích hợp. Điều chỉnh **cùng** concurrency giới hạn phía caller, rate limit và năng lực upstream. Không bật pending queue vô hạn để che một bottleneck; nó có thể tăng độ trễ và làm người dùng gặp timeout hàng loạt.

## 4. TLS: kết nối HTTPS an toàn và các timeout liên quan

Với URL `https://...`, TLS mang lại mã hóa và xác thực server. Cấu hình bình thường nên dùng trust anchors tin cậy, xác thực chain và hostname; không tắt kiểm tra chứng chỉ để “chạy được”. Đối với endpoint cần mutual TLS (mTLS), client còn phải xuất trình certificate/private key do hệ thống cấp.

Mẫu `HttpClient` cho HTTPS với handshake timeout:

```java
import java.time.Duration;
import reactor.netty.http.Http11SslContextSpec;
import reactor.netty.http.client.HttpClient;

HttpClient httpsHttpClient = HttpClient.create()
    .secure(ssl -> ssl
        .sslContext(Http11SslContextSpec.forClient())
        .handshakeTimeout(Duration.ofSeconds(8)))
    .responseTimeout(Duration.ofSeconds(5));

WebClient httpsWebClient = WebClient.builder()
    .baseUrl("https://api.example.com")
    .clientConnector(new ReactorClientHttpConnector(httpsHttpClient))
    .build();
```

Phần `WebClient` cần imports như ở phần 2. `Http11SslContextSpec` ở đây chủ động cấu hình TLS cho HTTP/1.1; các trường hợp HTTP/2/ALPN dùng cấu hình tương thích protocol tương ứng. Cấu hình TLS chỉ nên dùng cho endpoint HTTPS. Một số connector/version có cấu hình mặc định khác; ví dụ trong bài dựa trên **Spring Framework 6.x + Reactor Netty 1.1.x**.

### Trust store, custom CA, mTLS

- **Public CA:** trong hầu hết tình huống HTTPS chuẩn, ưu tiên trust configuration mặc định do client/JDK/Netty cung cấp, tránh tự quản lý cert không cần thiết.
- **Internal CA/self-signed test CA:** cài CA tin cậy vào trust store phù hợp runtime, hoặc truyền custom trust manager một cách có kiểm soát. Cert phải đúng hostname/SAN của URL. Không nhầm lỗi “unknown CA” với timeout.
- **mTLS:** cấu hình thêm client certificate và private key hợp lệ bằng SSL context, đồng thời vẫn kiểm tra server certificate. Bảo vệ secret/password/key; tránh đưa private key vào mã nguồn, log hoặc ảnh Docker công khai.
- **TLS handshake timeout:** chỉ giới hạn giai đoạn handshake, không thay connect timeout hay response timeout. Nếu server từ chối TLS version/cipher hoặc cert sai, tăng timeout thường không giải quyết được.
- **Không dùng** `InsecureTrustManagerFactory.INSTANCE` hoặc tắt hostname verification trong môi trường thật; cách này biến HTTPS thành đường truyền dễ bị giả mạo đích.

Khi gặp `SSLHandshakeException`/`SSLException`, kiểm tra nguyên nhân là expired/unknown CA, thiếu intermediate certificate, SAN/hostname không khớp, protocol/cipher incompatibility, server yêu cầu client certificate, hoặc thời hạn handshake. Nên bật debug TLS có kiểm soát trong môi trường kiểm thử; không bật wiretap/body logging chứa secrets ở production.

## 5. Giới hạn bộ nhớ codec: `maxInMemorySize` là gì?

`WebClient` dùng HTTP message codecs để chuyển JSON, text, XML… giữa byte stream và object. Một số decoder cần gom dữ liệu vào bộ nhớ để xử lý một value/segment. Mặc định theo tài liệu Spring, giới hạn thường là **256 KiB (262.144 bytes)**. Khi vượt ngưỡng liên quan, có thể gặp:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Tăng giới hạn cho **WebClient cụ thể**:

```java
WebClient client = WebClient.builder()
    .codecs(configurer ->
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
    .build();
```

Con số trên tương ứng **2 MiB**, minh họa cho endpoint trả về object JSON cần gom hơn mức mặc định. Đừng tăng tất cả client lên hàng trăm MiB khi chỉ một endpoint có payload lớn; giới hạn cao nhân với số request song song có thể gây áp lực heap/off-heap và GC.

**Điều dễ nhầm:** `maxInMemorySize` là giới hạn buffering của **decoder/message reader áp dụng**, không phải quota dung lượng toàn ứng dụng, không giới hạn tổng HTTP bytes truyền qua mạng và không phải biện pháp phòng mọi dạng memory exhaustion. Với stream NDJSON/SSE được decode từng item, giới hạn thường áp dụng trên phần cần đệm cho *một item/frame*; `collectList()` vẫn có thể giữ rất nhiều item trong RAM. Với `bodyToMono(String.class)` hoặc JSON object lớn, thường cần gom nội dung và chạm giới hạn.

Nếu nhận response lớn:

1. Kiểm tra **định dạng response** và schema trước: JSON object khổng lồ có thực sự cần tải trọn? Có thể đổi API sang pagination, NDJSON hoặc streaming.
2. Đặt giới hạn theo yêu cầu nghiệp vụ và kích thước payload thực tế, gồm cả response lỗi do `onStatus` đọc thành String; đừng chỉ đổi max size để “hết lỗi”.
3. Khi tải file lớn, cân nhắc truyền `Flux<DataBuffer>` vào file sink thích hợp (ví dụ `DataBufferUtils.write`), tránh `bodyToMono(byte[].class)` hoặc `collectList` mọi buffer. Cẩn thận ownership/release nếu xử lý `DataBuffer` thủ công; decoder framework thường quản lý việc này.
4. Dùng pagination/backpressure/concurrency bound để giới hạn lượng đối tượng tồn tại cùng lúc. Codec limit không thay thế size cap tại reverse proxy/gateway hoặc giới hạn tổng request/response theo hợp đồng API.

Cấu hình ở **client** không tự thay đổi codec limit của **server**. Spring MVC khác Spring WebFlux ở nhiều tầng body parsing; cần xác định chính xác phía phát `DataBufferLimitException`.

## 6. Ví dụ Java 17+ chạy tại localhost: pool, timeout và codec limit

Ví dụ tạo Reactor Netty HTTP server ngay trong `main`, nên **không cần internet hoặc upstream ngoài** khi chạy. Client được cấu hình pool, TCP connect timeout, response read timeout và giới hạn codec 1 KiB. Endpoint `/ok` trả ngắn; endpoint `/large` trả 4 KiB text và được mong đợi gây `DataBufferLimitException` khi decode thành `String`.

Cấu trúc:

```text
webclient-resources-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/WebClientResourcesDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'webclient-resources-demo'
```

**`build.gradle`** (Java 17+, Gradle 8.x)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux:3.3.13'
}

application {
    mainClass = 'demo.WebClientResourcesDemo'
}
```

**`src/main/java/demo/WebClientResourcesDemo.java`**

```java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.client.HttpClient;
import reactor.netty.http.server.HttpServer;
import reactor.netty.resources.ConnectionProvider;

public class WebClientResourcesDemo {
    public static void main(String[] args) {
        DisposableServer server = HttpServer.create()
            .host("127.0.0.1")
            .port(0) // Hệ điều hành chọn port còn trống
            .route(routes -> routes
                .get("/ok", (request, response) ->
                    response.header("Content-Type", "text/plain; charset=UTF-8")
                        .sendString(Mono.just("OK")))
                .get("/large", (request, response) ->
                    response.header("Content-Type", "text/plain; charset=UTF-8")
                        .sendString(Mono.just("x".repeat(4096)))))
            .bindNow();

        ConnectionProvider pool = ConnectionProvider.builder("lesson-pool")
            .maxConnections(4)
            .pendingAcquireMaxCount(8)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(15))
            .maxLifeTime(Duration.ofMinutes(1))
            .build();

        try {
            HttpClient http = HttpClient.create(pool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
                .responseTimeout(Duration.ofSeconds(2));

            WebClient client = WebClient.builder()
                .baseUrl("http://127.0.0.1:" + server.port())
                .clientConnector(new ReactorClientHttpConnector(http))
                .codecs(config -> config.defaultCodecs().maxInMemorySize(1024))
                .build();

            String result = client.get().uri("/ok")
                .retrieve()
                .bodyToMono(String.class)
                .block();
            System.out.println("ok: " + result);

            try {
                client.get().uri("/large")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();
                System.out.println("large: unexpected success");
            } catch (RuntimeException error) {
                if (!hasCause(error, DataBufferLimitException.class)) {
                    throw error;
                }
                System.out.println("large: DataBufferLimitException");
            }
        } finally {
            pool.disposeLater().block();
            server.disposeNow();
        }
    }

    private static boolean hasCause(Throwable error, Class<?> expectedType) {
        for (Throwable current = error; current != null;
             current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

Trong thư mục dự án, chạy bằng Gradle cài sẵn hoặc Gradle Wrapper nếu đã tạo:

```bash
gradle run --quiet
```

**Các dòng do chương trình in ở môi trường bình thường:**

```text
ok: OK
large: DataBufferLimitException
```

Có thể xuất hiện thêm log từ thư viện tùy cấu hình logger. `port(0)` để tránh xung đột cổng. `disposeNow()` dừng server; `disposeLater().block()` giải phóng pool do ví dụ tự tạo. `block()` chỉ có trong CLI `main` để quan sát kết quả; trong WebFlux request handler, trả `Mono`/`Flux` trực tiếp.

Ví dụ minh họa cách thiết lập timeout; vì localhost trả lời nhanh, **nó không cố gây TCP connect timeout hay response timeout**. Để kiểm chứng timeout độc lập, dùng upstream test có thể điều khiển độ trễ, đo thời gian và phân biệt loại lỗi. Với endpoint `/slow` phát body sau thời gian chờ lớn hơn `responseTimeout`, có thể kiểm tra response timeout trong integration test mà không phụ thuộc internet. TLS không được bật trên server `http://127.0.0.1` này; cấu hình HTTPS đã trình bày ở phần 4.

## 7. Chọn giới hạn theo tải và nhu cầu nghiệp vụ

Giả sử có 200 request đồng thời tới một dịch vụ ngoài, mỗi request tối đa 2 MiB response body:

- Nếu pool chỉ có 20 kết nối, phần còn lại có thể đợi. `pendingAcquireTimeout` cần đồng bộ với deadline toàn request; nếu deadline chỉ 2 giây mà acquisition cho phép 10 giây, yêu cầu có thể bị hủy trước khi tới giai đoạn HTTP.
- Nếu decoder có thể giữ 2 MiB cho mỗi response và nhiều response cùng giải mã, mức sử dụng RAM có thể tăng theo concurrency. Một con số đơn giản để nhắc thiết kế: 50 request đang buffer tối đa 2 MiB có thể tạo *khoảng* 100 MiB buffer theo trường hợp xấu; thực tế còn overhead object, networking và các buffer khác. Đây **không** phải ước lượng RAM toàn JVM.
- Nếu client stream nội dung liên tục, `responseTimeout=5s` là read idle timeout; thời gian hoàn thành có thể dài hơn 5 giây. Hạn tổng thể nên kiểm soát bằng publisher timeout/deadline nghiệp vụ.
- Tăng pool gấp 10 không làm upstream mạnh hơn. Cần đo độ trễ, throughput, tỉ lệ 429/503 và kiểm soát request concurrency/retry.

Một bộ giá trị thử nghiệm chỉ có nghĩa khi ghi rõ traffic profile và upstream SLO. Ví dụ cho API nội bộ có response thường dưới 500 ms, có thể **thử** connect 2 s, acquire 1 s, read 3 s, total 5 s và codec 1 MiB, sau đó load test để điều chỉnh; không dùng làm cấu hình khuyến nghị cho streaming, tải file hay liên vùng có latency cao.

## 8. Lỗi phổ biến và chẩn đoán theo tín hiệu

| Hiện tượng | Điều cần kiểm tra trước | Cách xử lý phù hợp |
| --- | --- | --- |
| Pool acquire timeout | Active/pending connections, queue length, response latency, số client/pool bị tạo | Giảm concurrency, tái sử dụng client, cân chỉnh pool, xử lý upstream chậm |
| TCP connect timeout | DNS, route, firewall, địa chỉ/port, proxy, sức tải server | Kiểm tra network path, đặt timeout đúng, retry có giới hạn nếu an toàn |
| TLS handshake error/timeout | CA, SAN hostname, cert hết hạn, mTLS, TLS versions, latency | Sửa trust/cert/protocol; chỉ tăng handshake timeout khi thực sự chậm |
| `ReadTimeoutException` hoặc lỗi response read timeout | Server có ngừng gửi byte? Streaming có heartbeat? Proxy buffering? | Điều chỉnh read timeout và heartbeat, điều tra upstream |
| `TimeoutException` từ Reactor `timeout()` | Pipeline nào đang chờ? `timeout` đặt trước hay sau retry? | Thiết kế deadline tổng, log stage và correlation ID |
| `DataBufferLimitException` | Codec nào decode, body một object lớn hay stream nhiều item, kích thước payload | Giảm payload, phân trang/stream, tăng `maxInMemorySize` có mục tiêu |
| OutOfMemoryError dù tăng codec limit | Nhiều request song song, `collectList`, byte[] lớn, off-heap Netty, memory leak | Giới hạn concurrency/tổng byte, streaming, profiling heap/direct memory |
| Lỗi ngẫu nhiên với keep-alive | Pool idle lâu hơn server/LB idle timeout, stale sockets, network reset | Cấu hình max idle, eviction, kiểm tra connection reuse |

Tối thiểu trong log/trace nên có endpoint logic (tránh lộ thông tin nhạy cảm), correlation ID, thời gian chờ pool/connect/response, loại lỗi, HTTP status khi có response, và kích thước/kiểu body nếu có số đo an toàn. Không ghi credentials, access token, dữ liệu cá nhân hoặc toàn bộ TLS payload.

**Các anti-pattern cần tránh:**

1. Dùng `Mono.timeout` rồi cho rằng đã cấu hình TCP connect/pool timeout chuẩn ở transport.
2. Tăng `maxConnections` và `pendingAcquireMaxCount` vô hạn để chữa latency; có thể làm quá tải upstream.
3. Khởi tạo `ConnectionProvider` mới mỗi lần gọi HTTP, làm mất reuse và rò rỉ tài nguyên.
4. Dùng `block()` trên Netty event loop trong WebFlux; pipeline non-blocking phải dùng operator `map`/`flatMap` và trả publisher.
5. Coi read timeout là thời gian tối đa download toàn file; traffic streaming cần deadline/idle policy riêng.
6. Tắt certificate validation để qua lỗi TLS; đây là lỗ hổng bảo mật, không phải xử lý timeout.
7. Coi limit codec là giới hạn tổng response/download hoặc tổng RAM; vẫn có các buffer/collection ngoài phạm vi này.
8. `onErrorResume(error -> Mono.empty())` trên tất cả lỗi khiến monitoring không phân biệt timeout, certificate failure, HTTP 500 hay payload vượt limit.
9. Retry mặc định tất cả thao tác POST không idempotent; cần giới hạn retry, backoff, idempotency key khi thích hợp và deadline chung.
10. Dùng số timeout rất ngắn trong môi trường có cold start, TLS handshake, DNS hoặc kết nối xuyên vùng mà chưa đo thực tế.

## 9. Câu hỏi tự kiểm tra

1. **Pool max 10, 30 request đến cùng lúc:** 20 request còn lại có nhất thiết là TCP connect timeout? → Không; có thể đang chờ connection trong pool, chịu giới hạn `pendingAcquireMaxCount`/`pendingAcquireTimeout`, không đi vào TCP connect.
2. **Một server trả về một chunk mỗi 2 giây trong 10 phút, `responseTimeout=5s`:** Có timeout vì tổng 10 phút? → Không nhất thiết; read interval đều dưới 5 giây. Muốn hạn tổng giao dịch cần deadline khác.
3. **HTTPS báo “unable to find valid certification path”:** Nên tăng handshake timeout? → Không; kiểm tra CA chain/trust store và hostname/khả năng mTLS trước.
4. **`bodyToMono(MyHugeDto.class)` gặp `DataBufferLimitException` nhưng `bodyToFlux(DataBuffer.class)` đọc được:** Có nghĩa RAM luôn an toàn? → Không; thao tác gom các buffer hoặc request concurrency cao vẫn có thể tiêu tốn bộ nhớ.
5. **SSE chạy liên tục:** Chọn 2 MiB codec limit có bảo vệ khỏi 1 triệu sự kiện bị `collectList()` gom lại? → Không; cần xử lý từng item và kiểm soát lưu trữ downstream.
6. **Vì sao cần dispose pool tự tạo khi dừng app?** → Pool quản lý connection/tài nguyên; giải phóng khi đóng lifecycle, không dispose cho từng request.

## 10. Tài liệu tham khảo

- Spring Framework, WebClient configuration (Reactor Netty, timeouts, codecs): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework, Reactive Core — Limits/streaming/DataBuffer: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Reactor Netty, HTTP Client (connection pool, TLS, timeout): https://projectreactor.io/docs/netty/release/reference/http-client.html
- Reactor Netty Javadoc, `HttpClient.responseTimeout`: https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClient.html
