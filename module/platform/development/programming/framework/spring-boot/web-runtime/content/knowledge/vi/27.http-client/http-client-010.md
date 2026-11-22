# Giới hạn kích thước phản hồi, giải phóng nội dung và xử lý lỗi từ dịch vụ đích

> **Phạm vi:** Spring Boot web-runtime, chủ đề **HTTP client**. Bài học dùng **Java 17+, Spring Boot 3.3.x và Spring Framework 6.1.x** để giải thích cách một ứng dụng gọi dịch vụ HTTP đích mà không giữ response vô hạn trong bộ nhớ, không rò rỉ `DataBuffer`/connections, và không chuyển raw upstream errors tới người gọi. Ví dụ chạy trên Spring MVC/Tomcat nhưng dùng `WebClient` cho outbound I/O; đối chiếu thêm `RestClient` và `RestTemplate`.

## 1. Những kiến thức cần đạt

Sau khi học xong, bạn có thể:

1. Phân biệt **response size trên dây**, **decoded body size**, **codec aggregation limit**, **streaming total-byte limit** và **connection/concurrency budget**.
2. Giải thích vì sao `bodyToMono(String.class)`, `bodyToMono(byte[].class)`, JSON object/list lớn thường cần gom dữ liệu, còn `Flux<DataBuffer>` cho phép xử lý theo đoạn.
3. Đặt `WebClient` codec `maxInMemorySize` và hiểu chính xác khi nào `DataBufferLimitException` phát sinh; không coi limit này là total size cap của một stream.
4. Dùng `retrieve()` hoặc `exchangeToMono()` để phân nhánh HTTP statuses, tiêu thụ hay giải phóng body và map lỗi thành contract của API hiện tại.
5. Giải phóng pooled `DataBuffer` đúng ownership, kể cả khi vượt giới hạn, cancel/discard hoặc timeout, tránh double-release.
6. Đếm số byte thực nhận để giới hạn toàn body bất kể `Content-Length` được khai báo, thiếu hay thay đổi do nén.
7. Trả `HTTP 502`/503/504 hoặc status nghiệp vụ đúng thay vì echo HTML lỗi, stack trace, access token hay thông tin nội bộ của upstream.
8. Biết sự khác nhau giữa `RestClient` (blocking) và `WebClient` (reactive) về xử lý stream, đóng response, thời gian chờ, thread, connection pool.
9. Kiểm thử được 200 nhỏ, body quá lớn, 503 có body nhạy cảm, chunked response, timeout, redirect, client cancel và nhiều kết nối đồng thời.

## 2. Mô hình một ứng dụng gọi HTTP tới dịch vụ đích

Giả sử API của shop cần lấy thông tin từ catalog service:

~~~text
Browser / client A
       |
       | GET /api/product
       v
Spring Boot API (service A)
       |
       | outbound HTTP GET
       v
Catalog service (B)
       |
       +----> 200 / JSON nhỏ
       |
       +----> 200 / body lớn bất thường
       |
       +----> 404, 429, 500, 503 + error page
       |
       +----> timeout / reset / TLS error
       |
       v
Service A xử lý body, status, resource, deadline
       |
       v
Public HTTP response với schema và lỗi an toàn
~~~

Nếu B bất ngờ trả 800 MiB HTML thay vì 4 KiB JSON, code gọi `bodyToMono(String.class)` có nguy cơ cần giữ lượng dữ liệu lớn trong RAM nếu không có limit codec; code dùng `bodyToFlux(DataBuffer.class)` có thể giữ bộ nhớ hữu hạn nhưng lại đọc lượng dữ liệu vô hạn nếu không có **total-byte cap**. Nếu B trả 503 kèm raw database connection string, việc log/return `responseBody` sẽ gây rò rỉ dù request nội bộ đang dùng TLS.

**Nguyên tắc thiết kế:** mỗi outbound call cần hợp đồng về content type, tổng byte size, duration, retry, concurrency, status mapping, memory và quyền sở hữu response body.

## 3. Các giới hạn tài nguyên không thay thế nhau

| Giới hạn | Dùng để kiểm soát | Không bảo đảm |
|---|---|---|
| HTTP `Content-Length` | Kích thước body server **khai báo**, có thể giúp reject sớm | Không luôn hiện diện; không thay byte counter và không nói chính xác decoded size |
| `spring.codec.max-in-memory-size` | Dung lượng aggregation của một số codec WebClient/WebFlux | Không phải tổng dung lượng của mọi response dạng Flux<DataBuffer> |
| `WebClient.Builder.codecs(...maxInMemorySize...)` | Hạn mức codec cụ thể trên một WebClient | Không tự chặn streaming chunks cộng dồn vô hạn |
| Total bytes counted | Tổng decoded bytes thực đi qua operator của client | Không tự hạn chế network wire bytes, time, redirect hay CPU JSON parser |
| Connect/read/overall timeouts | Tài nguyên thời gian và connection chờ | Không ngăn một response lớn về rất nhanh |
| Connection pool, bulkhead | Số calls/streams có thể hoạt động cùng lúc | Không giới hạn số bytes của một call |
| Content-Type/schema constraints | Loại nội dung client kỳ vọng | Không thay bytes cap, validation hoặc bảo mật đầu ra |
| Compressed/decoded ratio | Bảo vệ trước dữ liệu nén cực mạnh | Không tự giới hạn số requests đồng thời |

Ví dụ 200 requests cùng decode mỗi response 8 MiB thành một `byte[]` có thể tốn **1.600 MiB** chỉ cho một bản payload của mỗi request, trước khi tính copies, JSON objects, buffer pools và GC. Nếu xử lý theo đoạn 8 KiB hoặc 64 KiB rồi giải phóng, nhu cầu giữ toàn body trong bộ nhớ giảm mạnh, nhưng vẫn phải đo pooled native/direct memory và hàng đợi dưới concurrency.

### Content-Length không phải nguồn xác thực duy nhất

Một response có thể dùng `Transfer-Encoding: chunked` mà không có Content-Length hoặc HTTP/2 framing khác HTTP/1.1. Nếu dùng gzip/br, body encoded trên mạng có thể nhỏ hơn nhiều so với bytes sau giải nén. Reverse proxy cũng có thể biến đổi body/headers. Do đó:

1. Đọc Content-Length như **fast-reject hint** nếu hiện diện và đáng tin trong context.
2. Luôn dùng **byte counter** tại tầng đang xử lý content nếu contract cần hard cap.
3. Nếu có auto-decompression, kiểm giới hạn **decoded** payload; khi cần thêm wire quota ở connector/proxy.
4. Không cấp phát mảng theo một Content-Length cực lớn do peer khai báo.

## 4. Các HTTP client phổ biến của Spring

| Client | Kiểu I/O | API phù hợp | Rủi ro |
|---|---|---|---|
| `RestClient` (Spring 6.1+) | Synchronous/blocking | `retrieve()` cho body nhỏ; `exchange((req, resp) -> ...)` để kiểm status/stream | Thread bị giữ khi network chậm; gom body quá lớn |
| `RestTemplate` | Synchronous/blocking | `execute` với `ResponseExtractor` cho streaming | ErrorHandler mặc định, response body lifecycle và thread budget |
| `WebClient` | Reactive; non-blocking khi connector hỗ trợ | `retrieve`, `exchangeToMono`, `bodyToFlux(DataBuffer.class)` | Aggregate không có cap, pooled buffer leaks, blocking trong event loop |
| `@HttpExchange` proxy | Interface abstraction | Adapter dùng RestClient/WebClient | Không tự có byte cap/timeout: phụ thuộc underlying client |
| JDK `HttpClient` | Sync/async Java API | `BodyHandlers.ofInputStream()` | Cần xử lý stream/close/limits đúng contract |

Spring Boot có thể dùng **Spring MVC/Tomcat server** cùng **WebClient/Reactor Netty outbound client**. Có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` không có nghĩa server mặc định biến thành WebFlux; Boot thường ưu tiên Servlet MVC khi cả hai cùng có. Một ứng dụng WebFlux thuần thì cần thận trọng hơn khi dùng RestClient blocking trong event loop.

## 5. maxInMemorySize thực sự giới hạn điều gì?

WebClient dùng các `HttpMessageReader` và `Decoder` để chuyển response thành Java objects. Nhiều decoder có mức mặc định khoảng **256 KiB** cho một phần dữ liệu cần buffer/aggregate (phụ thuộc phiên bản và loại codec). Trong Spring Boot 3.3, có thể đặt global property cho các codecs được Boot cấu hình:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Hoặc đặt riêng cho một client:

~~~java
// Mảnh cấu hình trong một Spring @Bean, không phải file độc lập.
WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.test")
    .codecs(configurer -> configurer.defaultCodecs()
        .maxInMemorySize(64 * 1024))
    .build();
~~~

Với:

~~~java
Mono<String> body = webClient.get()
    .uri("/document")
    .retrieve()
    .bodyToMono(String.class);
~~~

Spring cần decode/aggregate thành một String. Nếu buffer limit bị vượt, có thể gặp `org.springframework.core.io.buffer.DataBufferLimitException`. Đây là **biện pháp chống memory aggregation vô hạn**; không phải lý do để đặt limit 1 GiB chỉ vì dữ liệu 1 GiB. Nên thay contract thành pagination/streaming nếu kích thước vượt budget.

Ngược lại:

~~~java
Flux<DataBuffer> parts = webClient.get()
    .uri("/download")
    .retrieve()
    .bodyToFlux(DataBuffer.class);
~~~

mỗi `DataBuffer` là một đoạn bytes. Tổng dữ liệu có thể lớn hơn `maxInMemorySize` nhiều lần khi không có operator aggregate. Chính ứng dụng phải tự đặt **giới hạn tổng bytes**. Ngay cả `Flux<MyDto>` khi decode nhiều JSON objects có thể cần buffer tới ngưỡng theo từng object, nên không được suy ra mọi kiểu Flux miễn nhiễm với aggregation.

## 6. retrieve() so với exchangeToMono()

### 6.1. retrieve(): tiện lợi với response nhỏ có schema rõ

~~~java
Mono<Item> item = webClient.get()
    .uri("/items/{id}", 42)
    .retrieve()
    .bodyToMono(Item.class);
~~~

Đoạn này là **snippet**, cần class `Item` và WebClient. `retrieve()` mặc định xử lý nhiều phản hồi 4xx/5xx bằng `WebClientResponseException` hoặc subclass. Khi cần mapping riêng, dùng `onStatus(...)`:

~~~java
Mono<Item> item = webClient.get()
    .uri("/items/{id}", 42)
    .retrieve()
    .onStatus(status -> status.value() == 404,
        response -> response.releaseBody()
            .then(Mono.error(
                new ItemMissingException())))
    .bodyToMono(Item.class);
~~~

Ở đây `ItemMissingException` là exception do ứng dụng định nghĩa. Không cần đọc nguyên upstream error page nếu không dùng nó. Nếu cần đọc error code từ body, phải áp **giới hạn bytes nhỏ**, validate schema và tránh log/expose thông tin không được phép.

### 6.2. exchangeToMono(): tự quyết định cách dùng response

~~~java
Mono<String> content = webClient.get()
    .uri("/data")
    .exchangeToMono(response -> {
        if (!response.statusCode().is2xxSuccessful()) {
            return response.releaseBody()
                .then(Mono.error(
                    new IllegalStateException(
                        "Upstream not available")));
        }
        return response.bodyToMono(String.class);
    });
~~~

`exchangeToMono` và `exchangeToFlux` giúp xử lý status/headers trước khi chọn giải mã, release hay stream body. Sau khi publisher do callback trả về hoàn tất, Spring kiểm tra và giải phóng body chưa tiêu thụ. **Không** giữ `ClientResponse` rồi decode sau khi callback-publisher đã kết thúc. WebClient `exchange()` kiểu cũ không nên được áp dụng như pattern mặc định vì dễ quên consume/release body trên các nhánh lỗi.

`ClientResponse.releaseBody()` là cách **consume và release content không cần dùng**, không phải biện pháp xóa ngay bytes trên mạng. Nếu upstream gửi một error body vô hạn hoặc rất chậm, việc drain có thể tốn thời gian và network: cần overall deadline, network controls và cancel/abort policy. Có thể chấp nhận không reuse connection đang có body chưa đọc thay vì kéo về hàng GiB dữ liệu chỉ để giữ keep-alive.

## 7. DataBuffer và trách nhiệm giải phóng

Trên Reactor Netty, `DataBuffer` có thể bọc Netty `ByteBuf` dùng **pooled direct/native memory** với reference count. Rác Java được GC không tự bảo đảm trả mọi pooled buffers đúng lúc. Khi tự xử lý `Flux<DataBuffer>`:

- Nhận buffer rồi đọc/xử lý: **release đúng một lần** sau khi không cần dữ liệu.
- Chuyển buffer tới writer/HTTP response: xác định ai **sở hữu** và sẽ release, không release hai lần.
- Các buffers bị operator discard khi cancel/error: dùng `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` ở vị trí phù hợp với các operator có discard support.
- Nếu `DataBufferUtils.write(Publisher<DataBuffer>, Path)` đang quản lý nguồn trong writer, đọc đúng overload contract. Các overload `write(..., OutputStream/Channel)` trả `Flux<DataBuffer>` **không tự release** buffers, cần xử lý khác.
- Khi dùng `retrieve().bodyToMono(String.class)` theo API chuẩn, framework decoder quản lý buffer theo contract; không tự can thiệp release buffers mà bạn không nhận.
- Khi client request bị cancel, unread HTTP content có thể khiến connection đóng/không được reuse; không phải luôn là leak, nhưng cần đo resource metrics.

### Mẫu giới hạn bytes đúng ranh giới

~~~java
// Snippet trong pipeline; "source" cần là Flux<DataBuffer>.
AtomicLong bytes = new AtomicLong();

Mono<Long> total = source
    .<Long>handle((buffer, sink) -> {
        try {
            int n = buffer.readableByteCount();
            if (n > 4096L - bytes.get()) {
                sink.error(new IllegalStateException(
                    "Too large"));
            } else {
                sink.next(bytes.addAndGet(n));
            }
        } finally {
            DataBufferUtils.release(buffer);
        }
    })
    .doOnDiscard(DataBuffer.class,
            DataBufferUtils::release)
    .then(Mono.fromSupplier(bytes::get));
~~~

Mọi `DataBuffer` đi vào callback đều được release trong `finally`, kể cả khi vượt limit. Nếu một operator discard buffer trước callback do cancellation, hook hỗ trợ cleanup. `handle` phát ra `Long`, **không** chuyển tiếp buffer đã release. Với code thực, không bắt mọi exception vào log raw chứa secrets; chuyển error sang public response đã sanitize và đo số lần oversized rejection.

**Anti-pattern:**

~~~java
// Không dùng cho payload lớn.
webClient.get().uri("/archive")
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .collectList();
~~~

`collectList()` giữ toàn bộ buffer objects; nó không cấp một tổng byte limit tự động. Tương tự, `DataBufferUtils.join()` không giới hạn có thể aggregate lớn. Nếu cần sum/checksum, xử lý theo đoạn; nếu cần lưu, stream tới file tạm hoặc object store qua API rõ ownership.

## 8. Mapping lỗi từ dịch vụ đích

Một upstream status không nhất thiết được forward nguyên trạng: service A phải có hợp đồng riêng cho public client.

| Tình huống ở B | Lựa chọn ở A | Giải thích |
|---|---|---|
| 2xx + body hợp lệ | 200/201/204 theo contract A | Vẫn kiểm bytes, Content-Type/schema |
| 404 | 404 nếu cùng resource contract; không thì 502 | Không lộ sự tồn tại của resource nội bộ khi không phù hợp |
| 400 | 400 nếu caller A thực sự gửi dữ liệu sai; không thì 502 | Có thể là bug trong request A→B |
| 401/403 | 401/403 chỉ nếu phản ánh quyền caller; khác thì 502/503 | Không tự trả internal authentication details |
| 409 | 409 khi có domain conflict thực sự | Public detail ổn định, không gửi raw upstream JSON |
| 429 | 429 hoặc 503, kèm policy backoff hợp lý | Không retry đồng loạt; xem Retry-After |
| 500/502/503 | 502 hoặc 503 | Không trả nguyên stack/SQL/HTML từ B |
| Connect/DNS/TLS failure | 502 hoặc 503 | Không tắt TLS certificate verification cho nhanh |
| Overall timeout | 504 khi gateway-like; hoặc 503 theo contract | Có deadline, không retry vô hạn |
| Response 2xx quá lớn | **HTTP 502**/domain error phù hợp | 413 thường áp dụng cho **request** quá lớn, không phải downstream response |
| Client A hủy request | Cancel outbound publisher/cleanup | Không phải lúc nào còn cơ hội viết HTTP error body |

Ví dụ B trả:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain

INTERNAL_DB_HOST=db.private; token=topsecret
~~~

A không nên trả `INTERNAL_DB_HOST` và `token` ra ngoài dưới body, custom header, logs công khai hoặc response exception message. Nên trả một public error code và thông điệp cố định, có correlation ID nếu cần. Trên server-side logs được kiểm soát, log **service label, route template, status, latency, exception type, requestId** với redaction, không log raw Authorization/Cookie/response body.

## 9. Timeout và retry không thay thế body cap

Có nhiều loại timeout:

- **Connect timeout**: chờ TCP connection.
- **TLS handshake timeout**: xác minh peer và thiết lập TLS.
- **Response/read timeout**: chờ response hoặc các network reads, semantics tùy connector.
- **Pending acquire timeout**: chờ lấy connection từ pool.
- **Whole-operation deadline**: thời gian tối đa cho cả DNS/connect/TLS/request/body/processing ở tầng application.

Đặt 3 giây timeout không ngăn payload 400 MiB được chuyển trong 1 giây. Ngược lại, body chỉ 20 byte cũng có thể giữ kết nối nếu upstream gửi rất chậm. Dùng **byte cap + deadline + concurrency cap** cùng nhau.

Ví dụ Reactor Netty configuration **mang tính minh họa**:

~~~java
// Cần imports reactor.netty.http.client.HttpClient,
// io.netty.channel.ChannelOption,
// org.springframework.http.client.reactive.ReactorClientHttpConnector,
// java.time.Duration.
HttpClient http = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
    .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(http))
    .build();
~~~

`responseTimeout` của connector khác `Mono.timeout` ở cấp toàn reactive operation. Khi có retries/backoff, nên tính mọi lần thử vào **tổng deadline budget**.

**Retry policy:**

- Retry chỉ những lỗi transient đã phân loại và phù hợp contract (ví dụ GET idempotent gặp 503/connection reset), có **số lần tối đa**, exponential backoff, jitter.
- Đừng retry `DataBufferLimitException` hoặc response too large: cùng request thường cho cùng payload.
- Đừng retry 400/401/403 hoặc TLS verification failure như thể chúng là lỗi mạng tạm thời.
- POST/PUT mutation chỉ retry khi có bảo đảm idempotency hoặc domain protocol.
- Nếu gateway, service A và mesh đều retry, số outbound calls có thể nhân nhiều lần và làm B quá tải.
- Bulkhead/circuit breaker giúp hạn chế lan truyền lỗi, không thay size cap.

## 10. Ví dụ chạy được: Spring Boot 3.3 Java 17 + WebClient

Lab chạy **một process** với hai nhóm endpoints:

~~~text
curl --> Spring MVC/Tomcat :8080
            |
            +-- /target/small  : fake B trả "hello"
            +-- /target/large  : fake B trả 128 KiB "A"
            +-- /target/error  : fake B trả 503 + internal marker
            |
            +-- /proxy/text/{mode}
            |      WebClient -> fake B -> decode String (32 KiB cap)
            |
            +-- /proxy/count/{mode}
                   WebClient -> fake B -> DataBuffer byte counter (4 KiB cap)
~~~

Fake B nằm trong cùng app **chỉ để chạy độc lập trên laptop**. Production dùng hostname B ở network khác và xác thực/TLS phù hợp; không tạo open proxy dựa trên URL từ user.

### 10.1. Project structure

~~~text
outbound-limit-lab/
  pom.xml
  src/main/java/example/limits/OutboundLimitApplication.java
  src/main/resources/application.properties
~~~

### 10.2. File pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>outbound-limit-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` cung cấp MVC/Tomcat server, còn `spring-boot-starter-webflux` cung cấp WebClient/Reactor Netty client. Trong Boot 3.3 khi có cả hai, Servlet MVC là web application type mặc định, nên controller có thể trả `Mono` được Spring MVC adapt async mà server không đổi thành Reactor Netty.

### 10.3. File application.properties

~~~properties
server.port=8080

# Không để default Boot error page hiện stacktrace/exception message:
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-exception=false
~~~

### 10.4. File Java hoàn chỉnh

Tạo `src/main/java/example/limits/OutboundLimitApplication.java`:

~~~java
package example.limits;

import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class OutboundLimitApplication {

    public static void main(String[] args) {
        SpringApplication.run(OutboundLimitApplication.class, args);
    }

    @Configuration
    static class HttpClientConfiguration {

        @Bean
        WebClient destinationClient(WebClient.Builder builder) {
            return builder
                .baseUrl("http://localhost:8080")
                .codecs(c -> c.defaultCodecs()
                    .maxInMemorySize(32 * 1024))
                .build();
        }
    }

    @RestController
    static class FakeDestination {
        @GetMapping(value = "/target/{mode}",
                    produces = MediaType.TEXT_PLAIN_VALUE)
        ResponseEntity<String> target(@PathVariable String mode) {
            return switch (mode) {
                case "small" -> ResponseEntity.ok("hello");
                case "large" -> ResponseEntity.ok(
                        "A".repeat(128 * 1024));
                case "error" -> ResponseEntity
                        .status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body("UPSTREAM_INTERNAL_ONLY=db.private");
                default -> ResponseEntity.notFound().build();
            };
        }
    }

    @RestController
    static class ProxyController {
        private static final long MAX_STREAM_BYTES = 4096L;
        private static final Duration TOTAL_DEADLINE =
                Duration.ofSeconds(5);

        private final WebClient client;

        ProxyController(WebClient destinationClient) {
            this.client = destinationClient;
        }

        @GetMapping("/proxy/text/{mode}")
        public Mono<ResponseEntity<?>> text(
                @PathVariable String mode) {
            if (!allowed(mode)) {
                return Mono.just(problem(HttpStatus.BAD_REQUEST,
                    "Chế độ thử nghiệm không hợp lệ."));
            }

            Mono<ResponseEntity<?>> request = client.get()
                .uri("/target/{mode}", mode)
                .exchangeToMono(response -> {
                    if (!response.statusCode().is2xxSuccessful()) {
                        int status = response.statusCode().value();
                        return response.releaseBody()
                            .then(Mono.<ResponseEntity<?>>error(
                                new RemoteFailure(status)));
                    }

                    // Aggregate String: codec cap là 32 KiB.
                    return response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .<ResponseEntity<?>>map(body ->
                            ResponseEntity.ok(
                                Map.of("text", body)));
                });

            return guarded(request);
        }

        @GetMapping("/proxy/count/{mode}")
        public Mono<ResponseEntity<?>> count(
                @PathVariable String mode) {
            if (!allowed(mode)) {
                return Mono.just(problem(HttpStatus.BAD_REQUEST,
                    "Chế độ thử nghiệm không hợp lệ."));
            }

            Mono<ResponseEntity<?>> request = client.get()
                .uri("/target/{mode}", mode)
                .exchangeToMono(response -> {
                    if (!response.statusCode().is2xxSuccessful()) {
                        int status = response.statusCode().value();
                        return response.releaseBody()
                            .then(Mono.<ResponseEntity<?>>error(
                                new RemoteFailure(status)));
                    }

                    AtomicLong total = new AtomicLong();
                    return response.bodyToFlux(DataBuffer.class)
                        .<Long>handle((buffer, sink) -> {
                            try {
                                int n = buffer.readableByteCount();
                                if (n > MAX_STREAM_BYTES - total.get()) {
                                    sink.error(new ResponseTooLarge());
                                } else {
                                    sink.next(total.addAndGet(n));
                                }
                            } finally {
                                DataBufferUtils.release(buffer);
                            }
                        })
                        .doOnDiscard(DataBuffer.class,
                            DataBufferUtils::release)
                        .then(Mono.<ResponseEntity<?>>fromSupplier(
                            () -> ResponseEntity.ok(
                                Map.of("bytes", total.get()))));
                });

            return guarded(request);
        }

        private static boolean allowed(String mode) {
            // Mode allowlist thay vì cho phép URL tùy ý.
            return Set.of("small", "large", "error")
                    .contains(mode);
        }

        private static Mono<ResponseEntity<?>> guarded(
                Mono<ResponseEntity<?>> request) {
            return request.timeout(TOTAL_DEADLINE)
                .onErrorResume(ResponseTooLarge.class, ignored ->
                    Mono.just(problem(HttpStatus.BAD_GATEWAY,
                        "Phản hồi dịch vụ đích vượt giới hạn.")))
                .onErrorResume(DataBufferLimitException.class,
                    ignored -> Mono.just(problem(
                        HttpStatus.BAD_GATEWAY,
                        "Phản hồi dịch vụ đích quá lớn.")))
                .onErrorResume(RemoteFailure.class, failure ->
                    Mono.just(problem(
                        failure.status == 503
                            ? HttpStatus.SERVICE_UNAVAILABLE
                            : HttpStatus.BAD_GATEWAY,
                        "Dịch vụ đích không sẵn sàng.")))
                .onErrorResume(TimeoutException.class, ignored ->
                    Mono.just(problem(HttpStatus.GATEWAY_TIMEOUT,
                        "Dịch vụ đích phản hồi quá chậm.")))
                .onErrorResume(WebClientRequestException.class,
                    ignored -> Mono.just(problem(
                        HttpStatus.BAD_GATEWAY,
                        "Không kết nối được dịch vụ đích.")))
                .onErrorResume(Exception.class, ignored ->
                    Mono.just(problem(HttpStatus.BAD_GATEWAY,
                        "Không xử lý được phản hồi dịch vụ đích.")));
        }

        private static ResponseEntity<?> problem(
                HttpStatus status, String message) {
            ProblemDetail body =
                    ProblemDetail.forStatusAndDetail(status, message);
            body.setTitle("Lỗi gọi dịch vụ đích");
            return ResponseEntity.status(status)
                    .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                    .cacheControl(CacheControl.noStore())
                    .body(body);
        }

        private static final class ResponseTooLarge
                extends RuntimeException {
        }

        private static final class RemoteFailure
                extends RuntimeException {
            final int status;

            RemoteFailure(int status) {
                super("remote status");
                this.status = status;
            }
        }
    }
}
~~~

### 10.5. Giải thích cơ chế của code

**Bean WebClient:** giới hạn 32 KiB áp dụng cho codec aggregate. Cả phần client builder và `WebClient` có thể tái sử dụng qua nhiều requests; không tạo WebClient mới cho mỗi request. Base URL được hardcode để lab chạy một process; production thay bằng cấu hình **trusted** và không cho user tùy ý truyền URL.

**Fake destination:** `small` trả `hello` gồm **5 byte ASCII**; `large` trả 128 KiB text 'A' để mô phỏng body lớn; `error` trả 503 với marker nội bộ. Fake B ở cùng JVM cố ý tạo một chuỗi 128 KiB, không đại diện cho hệ production có service độc lập.

**text route:** dùng `bodyToMono(String.class)`, không stream toàn bộ nội dung. `/proxy/text/large` vượt 32 KiB codec limit, nên được chuyển thành public error 502 mà không giữ body 128 KiB thành một String lớn.

**count route:** dùng `bodyToFlux(DataBuffer.class)` và counter 4096 bytes. `handle` xử lý từng buffer và `finally` release buffer đã nhận dù lỗi xảy ra. `doOnDiscard` bảo vệ thêm khi operator hỗ trợ discard/cancel các buffers chưa qua callback. Toán tử cuối chỉ trả số bytes, không giữ nội dung body trong List/String.

**Error branch:** kiểm status trước decode. Khi không phải 2xx, code gọi `releaseBody()` để loại nội dung lỗi và phát exception chỉ chứa status, không mang response body. Public mapping trả ProblemDetail an toàn, no-store; marker `UPSTREAM_INTERNAL_ONLY` không đi ra từ proxy.

**Deadline:** `timeout(5 giây)` bao quanh request publisher. Chỉ dùng trong lab; production thêm timeout từng giai đoạn, connection pool/concurrency limits và retry budget.

**Contract:** Một upstream response quá lớn là lỗi **đối với dịch vụ đích**, nên ví dụ trả `502 Bad Gateway`, không lẫn với `413 Content Too Large` dành cho **request** body của API.

**Exception safety:** `onErrorResume` cuối cùng tránh để raw library exception chảy vào public body. Hệ thực cần structured error logs/traces nội bộ với request ID, nhưng phải tránh log token/PII, raw query URL hoặc upstream stack.

## 11. Chạy và kiểm chứng bằng curl

Từ thư mục gốc của project đã có Maven/JDK:

~~~bash
mvn spring-boot:run
~~~

Gọi:

~~~bash
curl -i http://localhost:8080/proxy/text/small
curl -i http://localhost:8080/proxy/count/small

curl -i http://localhost:8080/proxy/text/large
curl -i http://localhost:8080/proxy/count/large

curl -i http://localhost:8080/proxy/text/error
curl -i http://localhost:8080/proxy/count/error
curl -i http://localhost:8080/proxy/text/unknown
~~~

Kỳ vọng:

| Endpoint | HTTP status | Body có ý nghĩa |
|---|---|---|
| `/proxy/text/small` | 200 | `{"text":"hello"}` |
| `/proxy/count/small` | 200 | `{"bytes":5}` |
| `/proxy/text/large` | 502 | ProblemDetail: response vượt codec aggregation limit |
| `/proxy/count/large` | 502 | ProblemDetail: decoded bytes vượt hard cap 4096 |
| `/proxy/text/error` | 503 | ProblemDetail: dependency unavailable, **không có internal marker** |
| `/proxy/count/error` | 503 | Tương tự |
| `/proxy/text/unknown` | 400 | Mode không được allowlist |

Dòng `Content-Type`, JSON field order, Date và connection headers tùy HTTP runtime; kiểm **status + semantics**, không so toàn bộ response byte-by-byte nếu không có yêu cầu.

**Chứng minh không lộ error body:**

~~~bash
curl -s http://localhost:8080/proxy/text/error
~~~

Output **không chứa** `UPSTREAM_INTERNAL_ONLY` hay `db.private`. Nếu gọi trực tiếp `/target/error` để quan sát simulator, bạn sẽ thấy marker; chính proxy đang loại bỏ dữ liệu đó. Đừng public fake target service này ở production.

Nếu muốn kiểm ngưỡng 4096/4097 byte, mở rộng fake destination trong **một bản lab riêng** với hai text responses có đúng 4096 và 4097 ký tự ASCII, sau đó gọi `/proxy/count/...` và kiểm 200 vs 502. Không đổi cấu hình sản phẩm chỉ để chạy test này.

## 12. RestClient: xử lý blocking response theo stream

`RestClient` của Spring Framework 6.1 có API fluent cho synchronous HTTP I/O. Với JSON nhỏ và có giới hạn, `retrieve().body(MyDto.class)` đơn giản. Với file/tệp hoặc body không đáng tin cậy:

~~~java
// Anti-pattern cho response lớn, có thể gom toàn body vào RAM.
byte[] huge = restClient.get().uri("/archive")
    .retrieve().body(byte[].class);
~~~

Thay bằng `exchange(...)` với body `InputStream` và đọc theo từng block:

~~~java
// Snippet đặt trong method có RestClient client.
// Cần imports InputStream, RestClient và các exception phù hợp.
long bytes = client.get().uri("/archive")
    .exchange((request, response) -> {
        // exchange không tự dùng default retrieve status handlers.
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new IllegalStateException(
                "Upstream response failed");
        }

        long total = 0;
        byte[] block = new byte[8192];
        try (InputStream in = response.getBody()) {
            int n;
            while ((n = in.read(block)) != -1) {
                if (n == 0) {
                    continue;
                }
                if (n > 4L * 1024 * 1024 - total) {
                    throw new IllegalStateException(
                        "Response too large");
                }
                total += n;
            }
        }
        return total;
    });
~~~

`RestClient.exchange` đưa request/response vào callback rồi quản lý vòng đời response sau callback; status handlers của `retrieve()` **không tự chạy trong exchange callback**. Vì thế phải check status trước khi đọc. `InputStream` chỉ được dùng **trong phạm vi callback**, đóng qua try-with-resources. Nếu đóng/bỏ response chưa đọc hết, connection có thể không được reuse; đó đôi khi là lựa chọn đúng để không drain một error body vô tận.

Đường này **blocking**: thread gọi sẽ chờ network reads. Với ứng dụng MVC, cần sizing worker/pool và timeouts. Trong WebFlux, không gọi RestClient sync trực tiếp trên Netty event loop; nếu SDK bắt buộc blocking, tách sang `Schedulers.boundedElastic()` và giới hạn queue/concurrency, biết rằng offload không làm byte cap tự xuất hiện.

### RestTemplate

`RestTemplate` còn được dùng ở nhiều hệ thống và có `execute(..., ResponseExtractor)` để đọc streaming response. `getForObject(..., byte[].class)` cho body lớn có vấn đề tương tự. Cần lưu ý default `ResponseErrorHandler` có thể phát exception cho 4xx/5xx **trước** khi extractor thực thi; nếu tự đổi handler, phải giữ resource lifecycle và giới hạn error body.

Trong Spring 6.1+, `RestClient` phù hợp cho code synchronous mới; `WebClient` phù hợp khi cần reactive composition/streaming và connector non-blocking. Không thay toàn bộ RestTemplate chỉ để có tên API mới nếu hệ thống hiện tại đã có timeout, limit, monitoring và tests tốt.

## 13. Ghi response lớn ra file: phải xác định ownership

Với WebClient, một đường hợp lý để tải archive là:

~~~text
GET upstream
  |
  | check status, Content-Type, optional declared length
  v
Flux<DataBuffer>
  |
  | count actual bytes; reject > MAX
  v
DataBufferUtils.write(..., tempPath)
  |
  | write complete -> verify size/checksum/format
  v
publish file / metadata; cleanup temp on error/cancel
~~~

Ví dụ minh họa về writer:

~~~java
// Pseudocode, không phải một endpoint hoàn chỉnh.
Mono<Void> write = DataBufferUtils.write(
    boundedDataBufferStream, temporaryPath);
~~~

Ở overload `DataBufferUtils.write(Publisher<DataBuffer>, Path)`, writer quản lý các buffers được nhận theo API phù hợp; không tự release buffer **trước** khi đưa cho writer. Với overload trả `Flux<DataBuffer>` viết vào OutputStream hoặc Channel, contract khác: các buffers nguồn **không tự được release** và consumer phải giải phóng khi thích hợp.

Một implementation file download thực sự cần cấp phát file tạm ngoài event loop nếu file operations blocking, giới hạn byte size, kiểm status trước stream, cleanup trên complete/error/cancel, chặn path traversal, quota disk, checksum/scan và chỉ publish file khi hoàn chỉnh. Java `Files.move` không mặc định bảo đảm atomicity/durability trên mọi filesystem.

## 14. Nén, chunked response và parser limits

Một body gzip nhỏ có thể nở ra rất lớn sau decompress. `Content-Length` có thể nói về encoded representation chứ không nói về decoded JSON. Khi client/connector bật decompression, xác định tại bước nào bạn đếm bytes, và nếu cần áp thêm hạn mức **wire bytes** cùng **decoded bytes**.

Các trường hợp đặc biệt:

- **Chunked HTTP/1.1**: không có Content-Length cố định; dùng byte counter.
- **HTTP/2**: các DATA frames được transport quản lý, không suy ra tổng response từ một header duy nhất.
- **gzip/br**: decoded size có thể vượt encoded length; phòng compression bombs và giữ max decode ratio nếu dùng nguồn không tin cậy.
- **JSON array lớn**: `bodyToMono(List.class)` có thể gom cả danh sách; chuyển sang phân trang/stream per-item, giới hạn item count, depth, string length.
- **SSE/NDJSON**: stream có thể dài theo thời gian; cần per-event limit, idle timeout và lifetime policy, không giả định “streaming” nghĩa là memory-free.
- **HTML error page**: upstream/gateway có thể trả HTML thay cho JSON. Không cố parse như domain DTO rồi log toàn body khi thất bại.

Byte cap chỉ là một lớp: còn CPU parsing, schema/type validation, file extensions, nested objects và per-request object count.

## 15. Timeout, retry, circuit breaker và resource budgets

**Connect timeout**, **TLS handshake timeout**, **response/read timeout**, **pending connection acquire timeout** và **overall deadline** có nghĩa khác nhau. Một small response có thể chờ hàng phút nếu dependency treo, còn một 100 MiB body có thể đến nhanh hơn timeout. Thiết kế cả **time budget** lẫn **byte budget**.

Một ví dụ nâng cao với Reactor Netty (snippet, cần imports đúng):

~~~java
HttpClient netty = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
    .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(netty))
    .build();
~~~

`responseTimeout` là timeout ở cấp connector/response reads theo contract; `Mono.timeout` là deadline từ lúc subscription của publisher. Không suy ra hai cơ chế tương đương.

Retry phải **hữu hạn và có chọn lọc**: GET idempotent gặp một transient 503 có thể retry với exponential backoff, jitter và tổng deadline; HTTP 400/401/403 do request sai, TLS certificate verification failure hay oversized response **không** nên retry cùng payload vô hạn. POST/PUT mutation cần idempotency key hoặc mô hình xác nhận để tránh duplicate effects.

**Circuit breaker** ngăn gọi tiếp khi dependency liên tục lỗi; **bulkhead** giới hạn concurrency dành cho một downstream; **rate limiter** ngăn quá tải; **timeout + byte cap** ngăn calls chiếm connection/memory quá lâu. Không một biện pháp nào thay thế được các biện pháp còn lại.

## 16. Redirects, SSRF và trust boundary

WebClient/RestClient chạy **server-side**, không chịu browser SOP/CORS. Nếu backend cho người dùng nhập một URL bất kỳ rồi gọi:

~~~java
// Anti-pattern: user tự điều khiển đích network.
webClient.get().uri(userSuppliedUrl)
    .retrieve().bodyToMono(String.class);
~~~

thì API có thể bị lợi dụng **SSRF** để gọi metadata endpoints, services nội bộ hoặc các host ngoài allowlist. Byte limit không ngăn việc request tới một URL nhạy cảm.

Chọn base URL từ trusted config/service discovery, chỉ chấp nhận path/IDs được allowlist và encode URI params. Nếu phải gọi URL external do user cung cấp, cần DNS/IP/host/scheme validation, mạng egress hạn chế, redirect limits và kiểm tra lại đích sau redirect/DNS resolution. Không tự chuyển Authorization/cookies qua cross-host redirect.

Trong lab, `mode` chỉ có `small`, `large`, `error`; nhờ vậy người dùng không thể ép client thành open proxy. Khi HTTP redirect 302/307 xảy ra, behavior tự follow phụ thuộc connector; kiểm status/Location và auth forwarding theo exact client configuration.

## 17. Tránh lộ thông tin từ lỗi downstream

Khi ứng dụng A nhận lỗi từ B, các giá trị **không nên xuất** trong public response:

- Raw exception class, stacktrace, SQL, database hostname/JDBC URL.
- Authorization/Bearer token, JWT, API key, Set-Cookie, signed URL hoặc session ID.
- User/tenant identifiers không thuộc hợp đồng API A, dữ liệu PII và request bodies.
- Internal service IP, pod name, port, filesystem path, debug/config dumps.
- HTML 502/503 page do reverse proxy sinh chứa deployment details.

Dùng `ProblemDetail` với public `status`, `title`, `detail` ổn định, có thể thêm correlation ID. Public error **không phải nơi để debug bằng throwable.toString()**. Logs/metrics nội bộ vẫn cần cung cấp tình trạng, nhưng phải allowlist fields và redact secrets; có quyền truy cập và retention phù hợp.

Nếu B trả 401/403, không máy móc chuyển sang 401/403 của A: có thể đó là **service-to-service token misconfiguration**, không phải khách hàng của A chưa đăng nhập. Nếu response vượt cap, `502 Bad Gateway` phù hợp khi A đóng vai trò gateway gọi B và B vi phạm contract, không nhất thiết `413 Content Too Large` vì incoming request của A rất nhỏ.

## 18. Connection pool và cancellation

HTTP client dùng keep-alive/HTTP2 pooling để tái sử dụng sockets. Khi response body không được consume, release hoặc hủy đúng, connection có thể bị giữ hoặc không thể reuse.

- `retrieve().bodyToMono(...)` với subscriber tiêu thụ bình thường: framework quản lý decode/lifecycle.
- `exchangeToMono(...)`: response body chưa tiêu thụ được giải phóng sau callback publisher completes.
- `ClientResponse.releaseBody()`: rõ ý định bỏ nội dung lỗi, nhưng có thể cần drain network.
- `Flux<DataBuffer>` tự xử lý: release theo ownership, doOnDiscard cho discard-enabled operators.
- Timeout/cancel giữa stream: có thể mất connection reuse; connector phải giải phóng native buffers và giữ pool không leak.
- `RestClient.exchange(...)`: chỉ dùng InputStream trong callback, không trả stream ra ngoài khi response scope đã đóng.
- Đừng gọi `subscribe()` thủ công trong controller mà không quản lý Disposable/cancellation; return Mono/Flux để framework quản lý request lifecycle.

Theo dõi connection pool active/idle/pending acquire, pool timeout, Netty direct memory, heap, GC, outstanding buffers, bytes/sec và cancellations. Nếu pending-acquire tăng, điều tra downstream latency và unconsumed bodies trước khi tăng pool size vô hạn.

## 19. Kiểm thử theo từng trục lỗi

| Test | Bằng chứng cần thấy |
|---|---|
| 200 small | Body hợp lệ, status 200, bytes/chars đúng |
| 200 body > codec cap | DataBufferLimitException được map thành public error; không OOM |
| 200 body > total stream cap | Counter reject đúng, pooled buffer cleanup |
| Body = đúng limit | Chấp nhận nếu contract cho phép; limit+1 phải reject |
| 503 với body marker nhạy cảm | Public 503 không có marker/stack/token |
| Chunked không Content-Length | Byte counter vẫn hoạt động |
| gzip tỉ lệ nén cao | Giới hạn decoded bytes và parsing |
| Timeout, slow chunk stream | Deadline/cancel, không giữ connections vô hạn |
| Connection reset giữa chừng | Error mapping, không leak buffers |
| TLS chain/SAN sai | Client fail có kiểm soát; không tắt verification |
| 429/Retry-After | Không retry storm; kiểm bounded backoff |
| 100 requests đồng thời | Heap/direct memory/pool/latency ổn định |
| Proxy tạo HTML 502 | Không echo HTML lỗi tới public body |
| Input URL lạ/redirect nội bộ | SSRF prevention, egress policy |
| Cancel request A | Outbound publisher hủy/cleanup, pool không kẹt |

### Những phép đo quan trọng

- **Error rate phân loại** HTTP 4xx/5xx, transport, timeout, parse, size-rejected.
- **Response bytes** encoded/decoded theo route template; không dùng user IDs làm metric labels.
- **Heap và native/direct memory**, pooled buffers, GC pauses.
- **Active/idle/pending connections**, connect latency, response latency và cancellation.
- **Retries per initial request**, total deadline vs retry backoff, downstream requests/sec.
- **p95/p99** latency của API A và của outbound HTTP B.

Thử một request nhỏ thành công không chứng minh độ an toàn bộ nhớ khi B liên tục trả 500 với body vài GiB, hoặc nhiều clients ngắt giữa chừng. Cần fault injection và soak tests ở môi trường kiểm soát.

## 20. Bảng anti-pattern và cách sửa

| Sai lầm | Hậu quả | Cách tốt hơn |
|---|---|---|
| `bodyToMono(byte[].class)` cho archive hàng GiB | Heap/OOM | Stream ra file/SDK, hard byte cap |
| `collectList()` trên DataBuffer stream | Giữ mọi buffer object | Handle mỗi buffer, release, discard hook |
| Tăng maxInMemorySize tới 2 GiB | Giảm guard, tăng risk khi concurrency | Hạn chế aggregate, dùng streaming/pagination |
| Chỉ kiểm Content-Length | Có thể bypass bởi missing/chunked/compression | Count actual decoded bytes |
| Dùng `exchange()` cũ rồi bỏ response | Pool leak/body chưa release | retrieve hoặc exchangeToMono/Flux |
| `release()` hai lần | Reference count violation | Tuân theo buffer ownership |
| Luôn drain error body vô hạn | Kẹt connection và network | Deadline/abort policy có kiểm soát |
| Copy raw upstream error vào public body | Lộ nội bộ, secrets, PII | Stable sanitized ProblemDetail |
| Mọi lỗi đều trả 500 | Mất HTTP semantics, monitoring sai | Map 4xx/5xx/timeout/size theo domain |
| Tự retry 502/503 vô hạn | Cascading overload | Bounded retries, backoff, circuit breaker |
| Retry oversized body | Lỗi lặp lại, tốn bandwidth | Thay contract, reject/pagination |
| `block()` trên Netty event loop | Nghẽn reactive server | Return Mono/Flux, offload blocking SDK |
| Input URL nguyên từ người dùng | SSRF | Trusted fixed base URL và egress allowlist |
| Giữ InputStream sau RestClient.exchange | Response scope đã kết thúc | Đọc hết/đóng stream trong callback |
| Log raw Authorization/response error | Rò rỉ token, PII | Structured redacted logs |
| Chỉ test status 200 | Bỏ qua error/cancel/limit code paths | Integration tests đầy đủ |

## 21. Checklist triển khai production

1. Định nghĩa schema/Content-Type, maximum decoded body bytes, item count và pagination contract.
2. Chọn RestClient blocking hay WebClient reactive theo threads/latency/workload, không theo “trend”.
3. Đặt codec maxInMemorySize phù hợp cho những decode phải aggregate.
4. Thêm **total streaming byte cap** nếu đọc DataBuffer trực tiếp.
5. Phân biệt compressed/encoded và decoded bytes, giới hạn tỉ lệ nén nếu cần.
6. Đặt connect, TLS, read và overall deadlines cùng connection pool budgets.
7. Chỉ retry failures phù hợp, với backoff/jitter/idempotency và budget.
8. Xử lý status/error **trước** khi tin payload, không echo raw upstream body.
9. Release/drain/cancel response đúng ở cả success, error và timeout.
10. Đặt network allowlist/redirect safeguards, chống SSRF, xác minh TLS.
11. Dùng public error schema ổn định, giữ logs nội bộ có redaction và correlation ID.
12. Đo heap/native memory, pool, bytes, failures, latency và test dưới concurrency.
13. Kiểm tra các error pages do proxy/gateway tạo, không chỉ controller.
14. Với file lớn, dùng temp storage/object storage với quota, cleanup và checksum.
15. Soak/cancel tests trước khi khẳng định response handling không leak.

**Nguyên tắc ghi nhớ:** *Giới hạn nội dung mà codec gom vào RAM, giới hạn tổng bytes của nội dung streaming, giải phóng mọi buffer/response đúng ownership và không để lỗi từ dịch vụ đích rò rỉ qua API của mình.*

## 22. Câu hỏi ôn tập

**1. maxInMemorySize=256KB có nghĩa một streaming response 10 MiB sẽ bị chặn không?**  
Không tự động. Nó chủ yếu giới hạn codec aggregation, còn Flux<DataBuffer> có thể phát nhiều chunks. Cần đếm tổng bytes.

**2. Vì sao Content-Length chưa đủ?**  
Vì header có thể thiếu, phản ánh encoded length hoặc bị thay đổi bởi proxy; tổng decoded bytes phải được kiểm.

**3. bodyToMono(String.class) có thể cần giữ toàn response?**  
Có. Một String thường phải được decode từ body, nên có aggregation/buffer và chịu codec limit.

**4. Đã gọi exchangeToMono nhưng không đọc response body thì sao?**  
Spring tự xử lý unconsumed body sau khi callback publisher hoàn tất; nên explicit releaseBody khi bỏ body và thiết kế timeout.

**5. releaseBody() có đảm bảo zero network cost?**  
Không. Nó có thể drain/release body còn lại; deadline và hủy kết nối có thể cần thiết.

**6. Khi tự nhận DataBuffer, bao giờ release?**  
Sau khi xử lý xong và không chuyển ownership cho writer khác. Không release hai lần.

**7. Vì sao cần doOnDiscard?**  
Vì một số operator có thể bỏ buffer khi lỗi/cancel trước khi callback chính xử lý nó, và pooled buffer cần trả về pool.

**8. Status 503 upstream có nghĩa caller của service A phải nhận 503?**  
Không nhất thiết. A map lỗi theo contract, có thể chọn 502/503; không gửi raw error body.

**9. Khi B trả response quá lớn, A nên luôn trả 413?**  
Không. 413 thường là inbound request size; gateway gặp quá lớn downstream response có thể trả 502.

**10. RestClient.exchange có áp dụng default retrieve() status handlers không?**  
Không. Khi dùng exchange callback, bạn tự kiểm status/handle response.

**11. WebClient là reactive client thì Spring MVC server có tự chuyển sang Reactor Netty không?**  
Không. MVC/Tomcat có thể dùng WebClient outbound mà vẫn là Servlet server.

**12. Có thể gọi RestClient blocking từ Netty event loop không?**  
Không nên. Nó giữ event-loop thread khi chờ I/O; offload hoặc dùng WebClient.

**13. Tại sao retry lỗi body quá lớn không hữu ích?**  
Vì cùng response vẫn quá limit, làm tăng traffic và load lên B.

**14. Cookie/token của A có an toàn nếu forward tới redirect URL do B trả không?**  
Không mặc định. Phải kiểm destination, redirect và auth header forwarding để tránh leak/SSRF.

**15. Test 100 requests đồng thời cần theo dõi gì ngoài heap?**  
Netty native/direct memory, outstanding buffers, pool active/pending, thread/queue, errors và cancellations.

**16. Vì sao log raw upstream error payload nguy hiểm?**  
Payload có thể chứa database host, private paths, secrets hoặc PII; logs có thể được chia sẻ/retained lâu hơn mong muốn.

## 23. Tài liệu chuẩn

- [Spring Framework – WebClient configuration, maxInMemorySize](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): cấu hình codecs trên WebClient.
- [Spring Framework – WebClient exchangeToMono/Flux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): xử lý status/body và release unconsumed response.
- [Spring Framework – WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): default 4xx/5xx và onStatus.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): reference counting, ownership, release và doOnDiscard.
- [Spring Framework 6.1 – DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): release, join và các overload write.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, RestTemplate, WebClient, exchange status handling.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): spring.codec.max-in-memory-size và HTTP settings.
- [Project Reactor – Error handling and retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): onErrorResume, retry/backoff semantics.
- [Reactor Netty – HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): timeout, connection pools và outbound HTTP.
- [OWASP – SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): network allowlist và URL validation.
- [OWASP – Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): information disclosure và safe logging.
