# WebClient.Builder, ClientHttpConnector và thư viện HTTP nền

## 1. Mục tiêu và bức tranh tổng thể

`WebClient` là HTTP client trong Spring WebFlux: ứng dụng dùng nó để gọi API bên ngoài theo mô hình reactive, với kết quả thường là `Mono<T>` (0–1 phần tử) hoặc `Flux<T>` (nhiều phần tử). Ba lớp trách nhiệm quan trọng cần tách biệt:

- **`WebClient.Builder`** cấu hình API client ở mức Spring: base URL, header/cookie mặc định, filter, codec, connector và quan sát (observability); `build()` tạo một `WebClient` để tái sử dụng.
- **`ClientHttpConnector`** là hợp đồng kết nối của Spring (`org.springframework.http.client.reactive.ClientHttpConnector`). Nó nối WebClient với thư viện HTTP thực tế và biến thao tác gửi/nhận thành các `ClientHttpRequest`/`ClientHttpResponse` reactive.
- **Thư viện HTTP nền (transport/engine)** thực hiện I/O thật: TCP/TLS, proxy, connection pool, event loop hoặc executor, timeout, HTTP/1.1–HTTP/2 tùy khả năng và cấu hình của engine.

Luồng đơn giản:

```text
Code ứng dụng
  → WebClient (URI, header, filter, encoder/decoder)
    → ExchangeFunction
      → ClientHttpConnector
        → Reactor Netty / JDK HttpClient / Jetty / Apache HttpComponents
          → mạng HTTP(S) và máy chủ đích
```

**Điểm mấu chốt:** `WebClient.Builder` quyết định *cách client được cấu hình*; `ClientHttpConnector` quyết định *transport nào được dùng*; engine quyết định *cách kết nối và I/O hoạt động*. Chọn connector không thay thế codec JSON, còn tăng giới hạn codec không thay đổi connect timeout.

## 2. Khi nào dùng và cần dependency gì?

WebClient phù hợp với các cuộc gọi HTTP bất đồng bộ, chuỗi xử lý reactive, gọi nhiều dịch vụ, hoặc tải dữ liệu dạng stream. Có thể dùng nó trong ứng dụng Spring MVC nhưng tuyệt đối không gọi `block()` trên luồng event loop của WebFlux/Reactor Netty. Với ứng dụng chỉ cần API đồng bộ, `RestClient` có thể đơn giản hơn.

Tối thiểu cần Spring WebFlux (`org.springframework:spring-webflux`), Project Reactor và một transport HTTP tương thích. Trong ứng dụng Spring Boot, `spring-boot-starter-webflux` là cách thông dụng để có WebClient cùng Reactor Netty. Nếu dự án đã có bộ quản lý phiên bản (Spring Boot BOM), hãy để BOM chọn các phiên bản tương thích. Không trộn ngẫu nhiên Spring, Reactor, Netty, Jetty hoặc HttpComponents khác thế hệ.

| Engine | Connector Spring | Trường hợp phù hợp | Lưu ý |
| --- | --- | --- | --- |
| Reactor Netty | `ReactorClientHttpConnector` | Lựa chọn phổ biến cho ứng dụng WebFlux; event loop và pooling mạnh | Cần `reactor-netty-http`; cấu hình bằng `reactor.netty.http.client.HttpClient` |
| Java JDK HttpClient | `JdkClientHttpConnector` | Muốn dùng `java.net.http.HttpClient` có sẵn trong JDK hiện đại | Không đồng nghĩa với bỏ Reactor ở tầng API WebClient |
| Jetty | `JettyClientHttpConnector` | Hệ thống đã dùng Jetty hoặc cần tùy chỉnh Jetty client | Cần thư viện Jetty Reactive HTTP client thích hợp, quản lý lifecycle |
| Apache HttpComponents | `HttpComponentsClientHttpConnector` | Đã chuẩn hóa Apache HttpClient 5 async | Dùng **async** client và phụ thuộc Apache tương ứng |

Spring Boot có thể tự nhận biết connector dựa vào classpath; ở các phiên bản Boot hỗ trợ các lựa chọn trên, ưu tiên phổ biến là Reactor Netty → Jetty → Apache → JDK. **Đó là hành vi auto-configuration của Boot**, không nên coi là hợp đồng cố định của mọi phiên bản Spring Framework hay của `WebClient.builder()` thuần. Khi yêu cầu bắt buộc một transport, hãy cấu hình tường minh.

## 3. WebClient.Builder: cấu hình ứng dụng

Ví dụ trong một Spring application đã có WebFlux:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class CatalogClientConfig {

    @Bean
    WebClient catalogClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example.org")
                .defaultHeader("Accept", MediaType.APPLICATION_JSON_VALUE)
                .defaultHeader("X-Client", "spring-learning")
                .codecs(config -> config.defaultCodecs()
                        .maxInMemorySize(1024 * 1024))
                .build();
    }
}
```

Đoạn trên là cấu hình trong ứng dụng Spring có bean `WebClient.Builder`; host `catalog.example.org` chỉ là địa chỉ minh họa, không phải endpoint chạy thử. Các thành phần quan trọng:

- `baseUrl(...)` làm gốc cho URI tương đối, ví dụ `.uri("/books/{id}", 7)`. URI tuyệt đối có thể ghi đè base URL. Quản lý slash/path có chủ đích, đặc biệt khi base URL chứa path.
- `defaultHeader(...)` và `defaultCookie(...)` cung cấp giá trị mặc định; header của request cụ thể có thể được cấu hình riêng.
- `defaultUriVariables(...)` và `uriBuilderFactory(...)` giúp định nghĩa quy tắc mở rộng URI, encoding và biến URI; không nối thẳng đầu vào chưa kiểm soát vào URL.
- `defaultRequest(...)` chỉnh mỗi request; `filter(...)` thêm `ExchangeFilterFunction` xử lý xuyên suốt, ví dụ thêm correlation ID, authentication, đo thời gian và lỗi.
- `codecs(...)` / `exchangeStrategies(...)` điều chỉnh bộ mã hóa/giải mã body; `maxInMemorySize` liên quan kích thước *buffer nội dung*, không phải dung lượng pool kết nối.
- `clientConnector(...)` gắn trực tiếp transport được cấu hình; `observationRegistry(...)` phục vụ metrics/tracing nếu cần.

**Tính thay đổi:** Builder là đối tượng **mutable/stateful**; gọi thêm `defaultHeader`/`filter` lên cùng builder ảnh hưởng các client được `build()` sau đó. WebClient đã build được thiết kế bất biến để chia sẻ giữa các thread; dùng `webClient.mutate().filter(...).build()` tạo một client **mới**, không sửa client cũ. Nếu cần tạo nhiều cấu hình từ một builder dùng lại, cân nhắc `builder.clone()`. Đừng tạo WebClient mới cho từng request.

**Trong Spring Boot:** nên inject `WebClient.Builder` được Boot auto-configure để nhận codec, tài nguyên HTTP, customizer và observability đã được cấu hình. Boot thường cung cấp builder scope prototype, nhưng bản thân từng builder vẫn mutable. Tạo bằng `WebClient.create()` hay `WebClient.builder()` trực tiếp sẽ không tự nhận toàn bộ tùy chỉnh Boot.

Ví dụ thay đổi client mà giữ nguyên bản gốc:

```java
WebClient publicApi = WebClient.builder()
        .baseUrl("https://example.org")
        .build();

WebClient privateApi = publicApi.mutate()
        .defaultHeader("X-Api-Version", "2")
        .build();
// publicApi giữ cấu hình ban đầu; privateApi có thêm header mặc định.
```

## 4. ClientHttpConnector hoạt động như thế nào?

Interface `ClientHttpConnector` định nghĩa thao tác cấp thấp mang dạng:

```java
Mono<ClientHttpResponse> connect(
        HttpMethod method,
        URI uri,
        Function<? super ClientHttpRequest, Mono<Void>> requestCallback);
```

Chữ ký trên là **trích đoạn API để hiểu hợp đồng**, không phải chương trình chạy độc lập. WebClient gọi connector qua tầng exchange khi một request được subscribe. Connector chuẩn bị native HTTP request, để callback ghi header/body, gửi qua engine rồi chuyển response trở lại dạng Spring reactive.

Connector **không** quyết định cách serialize DTO JSON, business error mapping, hay retry policy. Việc đó nằm ở WebClient codecs, filter và pipeline Reactor. Các lỗi có thể phát sinh ở lớp khác nhau:

- Lỗi tạo URI hoặc codec: thường do mã ứng dụng/dữ liệu.
- `WebClientResponseException`: HTTP server đã trả status lỗi 4xx/5xx khi dùng `retrieve()` mặc định.
- `WebClientRequestException`: lỗi I/O/transport, DNS, kết nối, TLS… trước khi có HTTP response hợp lệ.
- `DataBufferLimitException`: body cần buffer vượt giới hạn decoder; tăng `maxInMemorySize` chỉ khi có lý do, cân nhắc streaming cho dữ liệu lớn.

## 5. Cấu hình Reactor Netty: pooling, connect timeout và response timeout

`ReactorClientHttpConnector` là lựa chọn quen thuộc. Với Reactor Netty, có thể cấu hình `HttpClient` trước rồi truyền vào Builder:

```java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class PaymentsHttpConfig {

    @Bean
    WebClient paymentsClient(WebClient.Builder builder) {
        ConnectionProvider pool = ConnectionProvider.builder("payments-pool")
                .maxConnections(100)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .build();

        HttpClient httpClient = HttpClient.create(pool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
                .responseTimeout(Duration.ofSeconds(5));

        return builder
                .baseUrl("https://payments.example.org")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Đây là **ví dụ cấu hình Spring bean**, không gửi request tới host ví dụ. Trong hệ thống thật, phải **quản lý vòng đời `ConnectionProvider` tùy chỉnh** (dispose lúc application shutdown), tránh tạo pool riêng vô hạn theo số request/bean. Với nhiều ứng dụng Spring Boot, cho client dùng tài nguyên Reactor Netty được chia sẻ và quản lý sẵn còn phù hợp hơn; chỉ tách pool khi cần giới hạn độc lập giữa các upstream. Nếu dùng `ReactorResourceFactory` với tài nguyên riêng, kết nối lifecycle vào `ApplicationContext`.

Phân biệt timeout:

| Thiết lập | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `CONNECT_TIMEOUT_MILLIS` (Netty) | Giới hạn thời gian thiết lập kết nối TCP | 3 giây |
| `pendingAcquireTimeout` (pool) | Chờ cấp kết nối khi pool bận | 2 giây |
| `responseTimeout` (Reactor Netty) | Timeout xử lý/đọc response ở tầng transport theo định nghĩa engine | 5 giây |
| `Mono.timeout(Duration)` | Giới hạn thời gian của **publisher** theo đồng hồ Reactor; không thay thế cấu hình socket/pool | `.timeout(Duration.ofSeconds(8))` |

Các timeout không bảo đảm tổng thời gian từ lúc gọi tới lúc có kết quả là phép cộng cố định. DNS, TLS, streaming và retry có đặc tính riêng. Hãy cấu hình ngân sách timeout rõ ràng theo SLA, đo đạc và xử lý thất bại. Với stream kéo dài (SSE), timeout cố định quá ngắn có thể cắt kết nối hợp lệ.

**Không nhầm `reactor.netty.http.client.HttpClient` với `java.net.http.HttpClient`**: chúng là hai kiểu khác nhau, dành cho hai connector khác nhau.

## 6. Đổi engine sang JDK HttpClient

Khi cần JDK HTTP engine, không phải viết lại code gọi API; thay connector:

```java
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.http.client.reactive.JdkClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient jdk = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

WebClient client = WebClient.builder()
        .baseUrl("https://example.org")
        .clientConnector(new JdkClientHttpConnector(jdk))
        .build();
```

Đây là đoạn cấu hình Java 17+ trong project có Spring WebFlux; client chỉ thực hiện I/O khi gọi và subscribe request. JDK client có quy tắc cấu hình timeout, proxy, SSL, redirect riêng; không thể bê `ChannelOption` hay `ConnectionProvider` của Netty sang JDK. Chọn connector theo nhu cầu vận hành, môi trường, tính tương thích và benchmark thực tế thay vì suy đoán connector này luôn nhanh hơn connector kia.

## 7. Ví dụ chạy trọn vẹn: HTTP server cục bộ → WebClient → Reactor Netty

Ví dụ độc lập sau chứng minh Builder gắn connector và thực sự nhận dữ liệu HTTP, **không phụ thuộc Internet**. Dùng Gradle với Java 17+, thư mục dự án:

```text
build.gradle
src/main/java/demo/WebClientDemo.java
```

`build.gradle` (Groovy DSL; dùng BOM để đồng bộ phiên bản):

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework:spring-webflux'
    implementation 'io.projectreactor.netty:reactor-netty-http'
}

application {
    mainClass = 'demo.WebClientDemo'
}
```

`src/main/java/demo/WebClientDemo.java`:

```java
package demo;

import com.sun.net.httpserver.HttpServer;
import io.netty.channel.ChannelOption;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

public final class WebClientDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/hello", exchange -> {
            byte[] data = "Hello WebClient".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, data.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        });
        server.start();

        try {
            HttpClient transport = HttpClient.create()
                    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
                    .responseTimeout(Duration.ofSeconds(3));

            WebClient webClient = WebClient.builder()
                    .baseUrl("http://127.0.0.1:"
                            + server.getAddress().getPort())
                    .clientConnector(
                            new ReactorClientHttpConnector(transport))
                    .defaultHeader("X-Lesson", "webclient")
                    .build();

            String result = webClient.get()
                    .uri("/hello")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block(Duration.ofSeconds(5)); // chỉ tại main demo

            System.out.println(result);
        } finally {
            server.stop(0);
        }
    }
}
```

Chạy bằng Gradle trong thư mục ví dụ:

```bash
./gradlew run
```

Trên Windows PowerShell dùng `.\gradlew.bat run`; cần Gradle wrapper đã được tạo sẵn, hoặc dùng lệnh `gradle run` nếu đã cài Gradle. Phần stdout do chương trình tự in là **chính xác**:

```text
Hello WebClient
```

Gradle và logging thư viện có thể in thêm dòng riêng. JDK HTTP server mở cổng ngẫu nhiên trên loopback, tránh phụ thuộc API công cộng và đóng khi hoàn tất. Kết quả được nhận khi `block(...)` subscribe publisher; **không dùng `block()` trong request handler WebFlux đang chạy trên event loop**.

Nếu dựng dự án Java theo module path thay vì classpath truyền thống, có thể cần khai báo thêm module `jdk.httpserver`; ví dụ Gradle trên dùng classpath thông thường.

## 8. Cách sử dụng client đã cấu hình

Giả sử có `WebClient catalogClient` trỏ tới API trả JSON. DTO Java record:

```java
record Book(long id, String title) {}
```

Ví dụ truy vấn và xử lý status:

```java
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

// Đặt trong một phương thức/service đã nhận catalogClient từ Spring.
Mono<Book> request = catalogClient.get()
        .uri("/books/{id}", 42)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new IllegalArgumentException(
                                "Không tìm thấy book 42: " + body)))
        .bodyToMono(Book.class);

return request;
```

Đây là **fragment bên trong phương thức trả `Mono<Book>`**, không phải file Java độc lập. Khi cần return trong Java service, đặt record ở package/scope thích hợp. `retrieve()` mặc định chuyển HTTP 4xx/5xx thành `WebClientResponseException`; `onStatus(...)` chỉ tùy biến trường hợp xác định. Khi cần xem cả status/header/body, xem `exchangeToMono` / `exchangeToFlux` và tiêu thụ hoặc giải phóng response body đúng cách.

Gọi `get().uri(...).retrieve().bodyToMono(...)` chỉ **tạo publisher**; cần subscriber do WebFlux quản lý, `subscribe()` ở ranh giới ứng dụng phù hợp, hoặc `block()` trong chương trình đồng bộ/demo mới thực thi I/O. Trong controller WebFlux, trả thẳng `Mono` để runtime subscribe; không tự `subscribe()` cho mỗi request rồi bỏ qua tín hiệu lỗi.

### Filters: logic chung cho nhiều request

```java
WebClient client = WebClient.builder()
        .filter((request, next) -> {
            // Không log Authorization, Cookie hoặc body nhạy cảm.
            System.out.println("HTTP " + request.method()
                    + " " + request.url().getPath());
            return next.exchange(request);
        })
        .build();
```

Filter chạy theo chuỗi; thứ tự đăng ký có thể ảnh hưởng authentication, retry, logging. Nếu filter tự đọc response, phải xử lý/release body đúng cách; nếu chỉ truyền `ClientResponse` đi tiếp thì để WebClient tiêu thụ. Không cài filter log URL đầy đủ khi query string có secret hoặc dữ liệu cá nhân.

## 9. Vận hành và lỗi hay gặp

1. **Chỉ thêm `spring-webflux` nhưng thiếu HTTP engine tương thích:** khi chạy có thể không tìm được connector mong muốn hoặc không có tính năng của engine đã giả định. Kiểm tra dependency tree và connector thực tế, đặc biệt sau khi exclude Netty.
2. **Tưởng `build()` gửi request:** `build()` chỉ tạo client; pipeline Reactive được thực thi khi subscribe.
3. **Thay đổi lại một builder dùng chung:** cấu hình “rò” sang client khác được build sau; clone builder hoặc tạo bean client ổn định.
4. **Tạo `HttpClient`/pool theo từng request:** gây churn kết nối/thread/tài nguyên. Tái sử dụng WebClient và quản lý vòng đời pool/event loop.
5. **Chặn event loop bằng `block()` hoặc I/O blocking trong `map`:** mất throughput, có thể gặp lỗi `IllegalStateException`; giữ pipeline non-blocking hoặc chuyển công việc blocking sang scheduler phù hợp khi thực sự cần.
6. **Nhầm HTTP 500 với lỗi connect:** 500 là response từ server, còn connect/DNS/TLS là transport error; xử lý chính sách retry khác nhau và thận trọng với POST không idempotent.
7. **Chỉ đặt `Mono.timeout`:** điều đó không thay cấu hình connect/pool/response timeout của engine, và không tự thiết lập chính sách retry.
8. **Tăng `maxInMemorySize` vô hạn khi gặp `DataBufferLimitException`:** có nguy cơ tăng memory; với response lớn, ưu tiên streaming `Flux<DataBuffer>`/`Flux<T>` và release buffer khi tự xử lý.
9. **Tắt xác minh TLS để “sửa” chứng chỉ:** không an toàn. Cấu hình trust store/chứng chỉ đúng và tuân thủ chính sách proxy.
10. **Dùng input người dùng làm URL tùy ý:** mở nguy cơ SSRF; giới hạn host/scheme/IP theo chính sách trước khi gửi. Không ghi token hoặc dữ liệu nhạy cảm vào log.
11. **Tự cấu hình connector và quên auto-configuration:** những thay đổi về resource/SSL/metrics hoặc customizer có thể không còn đi qua cấu hình Boot như kỳ vọng. Kiểm tra bằng integration test và cấu hình thực tế.

### Checklist trước khi đưa vào production

- Xác định engine/connector thực tế trên classpath và cách Boot khởi tạo nó.
- Dùng `WebClient.Builder` do Spring Boot cấp nếu muốn thừa hưởng cấu hình chung; giữ client dưới dạng bean tái sử dụng.
- Định nghĩa connect, pending acquire, response và end-to-end timeout tương ứng với SLA.
- Định cỡ pool theo số upstream và tải; quản lý shutdown của tài nguyên tự tạo.
- Giới hạn codec/buffering, kiểm tra behavior với response lớn và streaming.
- Xử lý 4xx/5xx, transport error, retry có điều kiện; tránh retry request gây hiệu ứng phụ khi thiếu idempotency.
- Kiểm tra HTTPS, proxy, certificate, header bí mật, log, metrics/tracing, và SSRF.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Tăng `maxInMemorySize` có giải quyết lỗi connect timeout không?  
**Đáp án:** Không. Đây là giới hạn bộ đệm body ở tầng codec; connect timeout thuộc transport.

**Câu 2.** Tại sao hai WebClient dùng cùng `WebClient.Builder` có thể có cấu hình khác nhau?  
**Đáp án:** Builder mutable; mỗi lần `build()` chụp cấu hình hiện thời. Dùng `clone()` hoặc tạo builder riêng nếu muốn nhánh cấu hình độc lập.

**Câu 3.** Muốn chuyển từ Reactor Netty sang JDK HttpClient, phải sửa tất cả code `get()/retrieve()/bodyToMono()` không?  
**Đáp án:** Không. Thay `ClientHttpConnector` (và cấu hình engine). Bề mặt WebClient phía ứng dụng hầu như giữ nguyên.

**Câu 4.** Vì sao không nên `block()` trong WebFlux controller?  
**Đáp án:** Chặn luồng event loop đang xử lý nhiều request, làm mất lợi thế non-blocking và có thể bị Reactor từ chối. Trả `Mono`/`Flux` cho runtime.

## Tài liệu chính thức

- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Spring Framework — WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html)
- [Spring Framework — retrieve() và xử lý lỗi](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Boot — Calling REST Services / WebClient](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
