# Reactor Context, truyền mã đối chiếu và hủy yêu cầu đang chạy trong WebClient

## 1. Bài toán và mô hình hoạt động

Ứng dụng Spring WebFlux thường nhận một HTTP request rồi dùng `WebClient` gọi một hay nhiều dịch vụ khác. Khi tìm nguyên nhân lỗi, ta cần nối những log và lời gọi HTTP thuộc cùng yêu cầu gốc bằng **mã đối chiếu (correlation ID)**. Nếu người gọi ngừng cần kết quả, ta cũng muốn dừng các công việc còn đang chạy để tránh tiêu tốn tài nguyên vô ích.

Hai cơ chế giải quyết hai vấn đề khác nhau:

- **Reactor Context:** truyền dữ liệu nhỏ, không phụ thuộc thread, gắn với một subscription của `Mono`/`Flux`.
- **Cancellation:** subscriber phát tín hiệu `cancel` đến nguồn upstream; HTTP client có thể dừng nhận/gửi trao đổi đang diễn ra tùy connector và thời điểm.
- **HTTP header:** muốn dịch vụ phía xa nhìn thấy correlation ID, phải chủ động đưa ID từ Context vào header của outbound request. Reactor Context không tự vượt qua mạng.

Ví dụ kiến trúc:

```text
HTTP client
   |
   v
WebFlux server A: WebFilter nhận/tạo correlation ID
   |
   +-- chain.filter(exchange).contextWrite(c -> c.put(KEY, id))
   |
   v
A: service -> Mono/Flux của nghiệp vụ
   |                         |
   +--> WebClient -> B       +--> flatMap -> WebClient -> C
         |                                 |
         v                                 v
   filter đọc Context                 filter đọc Context
         |                                 |
         v                                 v
   Header X-Correlation-ID           Header X-Correlation-ID
   |
   v
Kết quả / lỗi / cancellation trở về subscriber của A
```

**Cần phân biệt:** correlation ID giúp nhóm những sự kiện của một công việc; trace ID/span ID từ một hệ thống distributed tracing còn mô tả quan hệ giữa các bước xử lý. Correlation ID không xác thực danh tính, không bảo đảm tất cả hành động đều nguyên tử và không tự kiểm soát vòng đời của request ở server từ xa.

Mục tiêu bài học: hiểu chiều truyền của Context, cách đọc/ghi Context trong WebClient, lan truyền qua `flatMap`, tạo header một cách an toàn, xem xét ngữ nghĩa cancel và timeout, kiểm thử hành vi mà không cần mạng thật.

## 2. Reactor Context là gì?

`Context` của Project Reactor là một tập key/value bất biến theo ngữ nghĩa API: `put` tạo Context mới, không sửa trực tiếp Context cũ. `ContextView` là giao diện chỉ đọc. Dữ liệu được gắn với **subscriber** và truyền qua các toán tử reactive hỗ trợ Context; nó không mặc định gắn với thread cụ thể.

| Cơ chế | Nơi dữ liệu được lưu | Phạm vi |
| --- | --- | --- |
| `Reactor Context` | Ngữ cảnh của subscription `Mono`/`Flux` | Những toán tử/publisher cùng chuỗi reactive, kể cả publisher lồng nhau được kết hợp đúng cách |
| `ClientRequest.attribute(...)` | Thuộc tính nội bộ của một request WebClient | Filter của **request đó**, không tự chuyển sang request khác |
| HTTP header | Dữ liệu gửi qua mạng | Dịch vụ nhận request có thể đọc được |
| `ThreadLocal` | Biến gắn với thread hiện tại | Không đáng tin để đại diện một request reactive có thể chuyển thread |
| MDC của logger | Thông thường là trạng thái theo thread | Muốn kết nối với Reactor Context cần tích hợp propagation đúng phiên bản |

Một subscription có thể nhận Context của riêng nó. Chẳng hạn, cùng một `Mono` đọc được hai giá trị khác nhau khi subscribe hai lần:

**Tệp `ContextBasics.java` (chạy với Java 17+ và Reactor trên classpath):**

```java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public class ContextBasics {
    static final String KEY = "correlationId";

    public static void main(String[] args) {
        Mono<String> work = Mono.deferContextual(view -> {
            String id = view.getOrDefault(KEY, "missing");
            return Mono.just("id=" + id);
        });

        System.out.println(work
                .contextWrite(Context.of(KEY, "request-A"))
                .block());

        System.out.println(work
                .contextWrite(Context.of(KEY, "request-B"))
                .block());
    }
}
```

**Stdout:**

```text
id=request-A
id=request-B
```

`Mono.deferContextual` đọc Context **lúc có subscription**, không đọc một biến mutable toàn cục lúc dựng pipeline. `Context.of(KEY, value)` là cách cấp Context cho một subscription; `contextWrite(c -> c.put(KEY, value))` là cách cập nhật dựa trên Context đã có.

### 2.1 Vì sao contextWrite đặt ở phía cuối?

Dữ liệu thông thường đi từ nguồn tới subscriber; Context đi theo phía subscriber **ngược lên upstream** trong quá trình subscription.

```java
Mono<String> example =
        Mono.deferContextual(view ->
                Mono.just(view.getOrDefault("label", "absent")))
            .map(String::toUpperCase)
            .contextWrite(ctx -> ctx.put("label", "visible"));

System.out.println(example.block()); // VISIBLE
```

Mặc dù `contextWrite` được viết sau `deferContextual`, phần upstream vẫn thấy `label`. Một `contextWrite` đặt giữa chuỗi chỉ ảnh hưởng những đoạn upstream trong phạm vi đó; nó không tạo “biến toàn cục mới” cho mọi publisher và không tự phát HTTP.

Phân biệt ba thời điểm:

1. **Assembly:** tạo đối tượng mô tả các thao tác, ví dụ `client.get().retrieve().bodyToMono(...)`.
2. **Subscription:** WebFlux runtime, `subscribe()` hoặc `block()` đăng ký publisher; lúc này Context được chuyển, filter có thể chạy và HTTP được thực hiện.
3. **Signals:** dữ liệu, lỗi, hoàn thành hoặc `cancel` đi qua pipeline.

`block()` trong ví dụ `main` chỉ giúp minh họa đồng bộ. Không dùng `block()` trên event loop của WebFlux.

### 2.2 Key, kiểu và giá trị Context

Có thể dùng chuỗi khóa cố định (`"correlationId"`) hoặc khóa riêng theo class/module để tránh xung đột. Một filter có thể đọc `view.get(KEY)` nếu chắc chắn có khóa, hoặc `view.getOrDefault(KEY, fallback)` khi cần hoạt động an toàn lúc thiếu dữ liệu. Kiểu trả về phải phù hợp kiểu giá trị đã lưu.

Nên lưu chuỗi ID ngắn, đối tượng bất biến hoặc metadata nhỏ; tránh bỏ body, stream, mật khẩu, mutable request/session object hay dữ liệu lớn vào Context. Không dùng correlation ID làm bằng chứng đăng nhập hoặc phân quyền.

## 3. Truyền Context sang WebClient bằng ExchangeFilterFunction

Để gửi mã ra ngoài, filter của `WebClient` phải đọc Context và **tạo request mới** chứa HTTP header.

**Tệp `CorrelationFilter.java`:**

```java
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

public final class CorrelationFilter {
    public static final String KEY = "correlationId";
    public static final String HEADER = "X-Correlation-ID";

    private CorrelationFilter() {}

    public static ExchangeFilterFunction create() {
        return (request, next) -> Mono.deferContextual(view -> {
            String id = view.getOrDefault(KEY, "");

            if (id.isBlank()) {
                return next.exchange(request);
            }

            ClientRequest updated = ClientRequest.from(request)
                    .headers(headers -> headers.set(HEADER, id))
                    .build();

            return next.exchange(updated);
        });
    }
}
```

Filter trả `Mono<ClientResponse>`; `next.exchange(request)` tiếp tục tới filter sau hoặc HTTP transport. `ClientRequest.from(request)` giữ các thuộc tính khác và cho phép chỉnh header trên bản request mới. `headers.set` thay thế giá trị cũ của header. Trong ví dụ này **ID lấy từ Context được ưu tiên** hơn header do request đặt trước đó; nếu muốn header cụ thể thắng thì phải thay đổi chính sách một cách tường minh.

**Không đọc Context một lần khi xây dựng client:** `WebClient` thường được dùng lại cho nhiều request chạy đồng thời. Đặt `Mono.deferContextual` trong filter bảo đảm mỗi subscription lấy dữ liệu tương ứng.

### 3.1 Đăng ký filter vào builder

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class RemoteClientConfiguration {
    @Bean
    WebClient inventoryClient(WebClient.Builder sharedBuilder) {
        return sharedBuilder.clone()
                .baseUrl("https://inventory.example")
                .filter(CorrelationFilter.create())
                .build();
    }
}
```

Đây là cấu hình mẫu trong Spring Boot với `WebClient.Builder` được cung cấp; Spring Framework thuần có thể tự tạo `WebClient.builder()` hoặc tự khai báo bean. URL minh họa phải được thay bằng cấu hình của dịch vụ thật. `clone()` tránh việc thêm filter hoặc đổi `baseUrl` vô tình ảnh hưởng những client khác sử dụng cùng builder.

Trong service, chỉ cần trả `Mono`/`Flux` cho caller:

```java
Mono<String> response = inventoryClient.get()
        .uri("/stock/{sku}", "SKU-7")
        .retrieve()
        .bodyToMono(String.class)
        .contextWrite(ctx ->
                ctx.put(CorrelationFilter.KEY, "request-A"));
```

Đoạn này giả định `inventoryClient` đã được inject và API trả body String; nó không phải chương trình Java hoàn chỉnh. Khi có subscription, filter sẽ thêm `X-Correlation-ID: request-A` lên outbound HTTP request.

### 3.2 Vì sao request lồng nhau vẫn nhận cùng mã?

```java
Mono<String> workflow =
        inventoryClient.get()
                .uri("/items/{sku}", "SKU-7")
                .retrieve().bodyToMono(String.class)
                .flatMap(item ->
                        inventoryClient.get()
                                .uri("/stock/{sku}", "SKU-7")
                                .retrieve().bodyToMono(String.class))
                .contextWrite(ctx ->
                        ctx.put(CorrelationFilter.KEY, "request-A"));
```

Hai HTTP request trên cùng chuỗi đều có thể thấy `request-A`, vì `flatMap` subscribe publisher bên trong bằng context của chuỗi reactive phù hợp. Đây là trường hợp tiêu biểu nên dùng Reactor Context hơn request attribute. `ClientRequest.attribute` chỉ thuộc về một request và không tự chuyển sang request sau.

Không làm như sau trong controller/service:

```java
// Anti-pattern minh họa trong một phương thức:
inventoryClient.get().uri("/items/SKU-7")
        .retrieve().bodyToMono(String.class)
        .subscribe(); // Bắt đầu subscription tách khỏi pipeline caller.
return Mono.just("started");
```

`subscribe()` thủ công có thể làm mất quyền kiểm soát lỗi, Context, thời hạn và cancellation của caller. Thường nên **trả về publisher** hoặc kết hợp với `flatMap`/`then` thay vì phát tác vụ rời rạc.

### 3.3 Truyền ID an toàn

Correlation ID là metadata vận hành, không phải token xác thực. Chỉ nhận những ký tự có thể đưa vào HTTP header an toàn, giới hạn độ dài (ví dụ cho phép chữ, số, dấu chấm, gạch dưới và gạch ngang, tối đa 64 ký tự) và không cho CR/LF.

Một ID do bên ngoài gửi có thể bị giả mạo. Trong hệ thống có biên tin cậy, có thể luôn tạo ID mới ở cổng vào hoặc chỉ tin gateway đã xác thực; **regex chỉ kiểm tra định dạng**. Không chuyển header chứa ID hoặc credential sang host ngoài danh sách tin cậy mà không có chính sách rõ ràng. Với dự án đã dùng OpenTelemetry hoặc Micrometer Tracing, nên ưu tiên trace propagation tiêu chuẩn như `traceparent` để có đầy đủ quan hệ span; correlation ID tùy chỉnh chỉ là một lớp bổ sung.

## 4. Đưa ID inbound vào Context của WebFlux server

`WebFilter` chạy phía **server inbound**; `ExchangeFilterFunction` chạy phía **client outbound**. Một `WebFilter` có thể đọc/tạo ID rồi đưa vào Reactor Context để những lời gọi WebClient trong downstream dùng được:

**Tệp `IncomingCorrelationWebFilter.java`:**

```java
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class IncomingCorrelationWebFilter implements WebFilter {
    private static final String HEADER = "X-Correlation-ID";
    private static final String KEY = "correlationId";
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        String incoming = exchange.getRequest()
                .getHeaders().getFirst(HEADER);

        String id = incoming != null && SAFE.matcher(incoming).matches()
                ? incoming : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders().set(HEADER, id);

        return chain.filter(exchange)
                .contextWrite(ctx -> ctx.put(KEY, id));
    }
}
```

Ứng dụng cần bật Spring WebFlux và component scanning cho class trên. `contextWrite` bọc chuỗi do `chain.filter(exchange)` trả về nên những thành phần ở upstream trong chain có thể đọc `id`. Response header ở đây được đặt trước khi response được commit; caller nhìn thấy ID của lần xử lý hiện tại nếu response được trả qua filter.

Nếu không tin tưởng ID inbound, hãy **thay nhánh chọn incoming bằng tạo ID mới** theo chính sách hệ thống. Nên quy định điểm khởi tạo, truyền tiếp và điểm thay đổi ID trong kiến trúc đa dịch vụ để tránh log từ cùng công việc bị rời rạc.

Ví dụ đọc ngữ cảnh ở tầng nghiệp vụ:

```java
Mono<Void> auditedWork = Mono.deferContextual(view -> {
    String id = view.getOrDefault("correlationId", "missing");
    System.out.println("processing id=" + id);
    return Mono.empty();
});
```

Đây là đoạn minh họa; trong production dùng logger được cấu hình, chỉ log ID/method/status/đường dẫn đã làm sạch. `MDC` của SLF4J thường dựa vào thread và không tự đồng bộ với Reactor Context ở mọi toán tử/scheduler. Muốn đưa ID vào MDC, dùng tích hợp context propagation/observability phù hợp Spring, Reactor và Micrometer phiên bản thực tế, đồng thời kiểm tra hành vi khi chuyển thread.

## 5. Ví dụ hoàn chỉnh: hai lời gọi WebClient cùng Context

Chương trình dưới dùng `ExchangeFunction` giả tạo HTTP response trong bộ nhớ; **không kết nối mạng**. Một chuỗi `flatMap` gửi hai request mô phỏng, đọc cùng mã; cuối chương trình hủy một `Mono` không hoàn tất.

**Tệp `ContextCancelDemo.java` (Java 17+, Spring WebFlux và Reactor):**

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public class ContextCancelDemo {
    private static final String KEY = "correlationId";
    private static final String HEADER = "X-Correlation-ID";

    public static void main(String[] args) {
        ExchangeFunction fakeTransport = request -> {
            System.out.println("fake HTTP " + request.method()
                    + " " + request.url().getPath()
                    + " id=" + request.headers().getFirst(HEADER));
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE,
                            MediaType.TEXT_PLAIN_VALUE)
                    .body("ok")
                    .build());
        };

        ExchangeFilterFunction correlation =
                (request, next) -> Mono.deferContextual(view -> {
                    String id = view.getOrDefault(KEY, "missing");
                    ClientRequest newRequest = ClientRequest.from(request)
                            .headers(h -> h.set(HEADER, id))
                            .build();
                    return next.exchange(newRequest);
                });

        WebClient client = WebClient.builder()
                .baseUrl("https://example.invalid")
                .exchangeFunction(fakeTransport)
                .filter(correlation)
                .build();

        String result = client.get()
                .uri("/first")
                .retrieve()
                .bodyToMono(String.class)
                .flatMap(first -> client.get()
                        .uri("/second")
                        .retrieve()
                        .bodyToMono(String.class))
                .contextWrite(Context.of(KEY, "request-42"))
                .block();

        System.out.println("response=" + result);

        AtomicBoolean cancelled = new AtomicBoolean();
        Disposable subscription = Mono.<String>never()
                .doOnCancel(() -> {
                    cancelled.set(true);
                    System.out.println("upstream cancel observed");
                })
                .subscribe();

        subscription.dispose();
        System.out.println("cancelled=" + cancelled.get());
    }
}
```

**Stdout:**

```text
fake HTTP GET /first id=request-42
fake HTTP GET /second id=request-42
response=ok
upstream cancel observed
cancelled=true
```

Mỗi request giả lập chỉ in header và trả body `ok`. Sau khi `block()` subscribe chuỗi, filter đọc `request-42` của subscription; `flatMap` giữ context cho lần gọi thứ hai. `Mono.never()` không phát dữ liệu và không hoàn thành; `dispose()` thông báo hủy, làm `doOnCancel` được gọi. Đó là minh chứng về **tín hiệu hủy trong Reactor**, không phải minh chứng một server HTTP từ xa ngừng xử lý.

Để chạy, đưa class vào project Spring Boot 3.x với Java 17+ và dependency (ví dụ Gradle):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Chạy phương thức `main` từ IDE dùng Gradle classpath, hoặc cung cấp đầy đủ JAR Spring/Reactor vào classpath cho `javac`/`java`. Không thể dùng `javac ContextCancelDemo.java` trong thư mục trống vì `org.springframework.*` và `reactor.*` không thuộc JDK. `block()` trong chương trình `main` dành cho thực nghiệm đồng bộ, không đặt trong code xử lý request trên event loop WebFlux.

## 6. Hủy một yêu cầu đang chạy thực sự nghĩa là gì?

Reactive Streams cho phép subscriber gửi `cancel` qua `Subscription.cancel()`. Ở Reactor, `subscribe()` thường trả một `Disposable`; gọi `dispose()` yêu cầu dừng subscription.

```text
Caller / WebFlux runtime
         |
         | cancel
         v
bodyToMono() hoặc bodyToFlux()
         |
         v
retrieve() / trao đổi WebClient
         |
         v
Client HTTP connector / network
         |
         v
Remote server (có thể đã nhận và xử lý request)
```

Ví dụ chủ thể sở hữu một subscription và muốn hủy nó:

```java
Disposable running = client.get()
        .uri("/long-running")
        .retrieve()
        .bodyToMono(String.class)
        .doFinally(kind -> System.out.println("finished=" + kind))
        .subscribe(
                body -> System.out.println("body=" + body),
                error -> System.err.println(error.getMessage())
        );

// Khi người gọi hủy tác vụ:
running.dispose();
```

Đây là đoạn minh họa trong thành phần có quyền giữ `running`. Với WebFlux controller, thường **trả `Mono` cho framework** để runtime sở hữu subscription và quản lý nó; không tự subscribe rồi tách công việc khỏi yêu cầu.

Các giới hạn quan trọng:

1. Tín hiệu cancel chỉ là **yêu cầu hủy theo giao thức reactive**. Nếu HTTP request đã rời client, remote server vẫn có thể đang chạy hoặc đã ghi dữ liệu.
2. HTTP connector có thể dừng nhận body, hủy trao đổi/đóng kết nối hoặc giải phóng tài nguyên tùy thời điểm, nhưng không bảo đảm hoàn tác tác dụng phụ ở server.
3. Một API thanh toán, tạo đơn hoặc ghi dữ liệu cần khóa idempotency/truy vấn trạng thái để xử lý kết quả mơ hồ, đặc biệt khi caller timeout rồi retry.
4. Thao tác blocking hoặc thư viện ngoài không hỗ trợ cancel có thể tiếp tục làm việc sau khi reactive subscriber hủy.
5. Một publisher hot/chia sẻ (`cache()`, `share()` hoặc nguồn quản lý độc lập) có vòng đời riêng; hủy một subscriber không nhất thiết dừng nguồn chung.

### 6.1 Quan sát complete, error và cancel

| Tình huống | Signal | API theo dõi |
| --- | --- | --- |
| Nguồn hoàn thành bình thường | `onComplete` | `doOnSuccess` (Mono), `doOnComplete` (Flux), `doFinally(ON_COMPLETE)` |
| Nguồn phát lỗi | `onError` | `doOnError`, `doFinally(ON_ERROR)` |
| Subscriber yêu cầu ngừng | `cancel` | `doOnCancel`, `doFinally(CANCEL)` |

`doFinally` được gọi khi chuỗi kết thúc bằng một trong ba cách. `doOnTerminate` phản ứng với complete/error, không đại diện đầy đủ cho cancellation.

```java
Mono<String> operation = client.get()
        .uri("/report")
        .retrieve()
        .bodyToMono(String.class)
        .doFinally(signalType -> {
            switch (signalType) {
                case CANCEL -> System.out.println("cancelled");
                case ON_ERROR -> System.out.println("failed");
                case ON_COMPLETE -> System.out.println("completed");
                default -> { }
            }
        });
```

Tạo biến `operation` chưa kích hoạt HTTP; phải có subscription. Những callback trên phục vụ quan sát/tài nguyên, không dùng để thay thế `onErrorResume`, `flatMap` hay cơ chế chuyển đổi dữ liệu của luồng.

### 6.2 Cancel khác timeout và status 4xx/5xx

- **Cancel:** một subscriber hoặc toán tử ở downstream yêu cầu ngừng. Subscriber đã cancel thường không được gửi thêm `onError` chỉ để báo “đã cancel”.
- **Reactor timeout:** `timeout(Duration)` làm hết thời gian chờ tín hiệu, **cancel upstream**, và phát `TimeoutException` xuống downstream khi không có fallback.
- **HTTP 404/500:** là trạng thái response HTTP; `retrieve()` có logic chuyển một số response status thành lỗi. Đây không đồng nghĩa cancel.
- **Timeout ở connector:** connect timeout, response timeout hoặc read timeout kiểm soát từng giai đoạn của transport; không thay thế deadline nghiệp vụ tổng thể.

```java
Mono<String> timed = client.get()
        .uri("/slow")
        .retrieve()
        .bodyToMono(String.class)
        .doFinally(kind -> System.out.println("beforeTimeout=" + kind))
        .timeout(java.time.Duration.ofSeconds(2))
        .doFinally(kind -> System.out.println("afterTimeout=" + kind));
```

Khi quá hạn trước khi có kết quả, `doFinally` **phía nguồn** có thể thấy `CANCEL`, còn `doFinally` phía dưới `timeout` thấy `ON_ERROR`. Đó là hai góc nhìn của cùng một sự kiện timeout, không phải kết quả mâu thuẫn. Thứ tự thời gian in log có thể tùy scheduler; không viết test dựa vào thứ tự callback nếu không được API bảo đảm.

Một `Flux.take(1)` có thể cancel upstream sau khi nhận phần tử đầu; `switchMap` có thể hủy tác vụ cũ khi có giá trị mới. Với streaming HTTP, cần hiểu đóng/giải phóng body sau khi dừng sớm để không giữ connection ngoài ý muốn.

## 7. Quản lý vòng đời trong controller và service

Một WebFlux controller nên mô tả công việc bằng publisher, ví dụ:

```java
@GetMapping("/product/{sku}")
public Mono<String> product(@PathVariable String sku) {
    return inventoryClient.get()
            .uri("/products/{sku}", sku)
            .retrieve()
            .bodyToMono(String.class)
            .timeout(Duration.ofSeconds(3));
}
```

Đoạn này nằm bên trong class `@RestController` đã inject `inventoryClient`; cần import `@GetMapping`, `@PathVariable`, `Mono` và `Duration`. WebFlux runtime subscribe publisher và có thể phát tín hiệu cancel khi kết nối với caller đóng, tùy giai đoạn xử lý. Vì vậy service không cần `subscribe()` thủ công để “chạy ngay” request.

Với công việc thực sự cần chạy độc lập vòng đời HTTP (ví dụ xử lý job dài), phải tạo cơ chế job riêng có danh tính, trạng thái, deadline và quyền hủy rõ ràng. Không giả định một `subscribe()` rời rạc là hệ thống quản lý tác vụ nền đáng tin cậy.

### 7.1 Cancellation và correlation ID liên hệ ra sao?

Mã đối chiếu giúp giải thích **request nào** đã hoàn thành, lỗi hoặc bị hủy. Filter có thể log metadata an toàn và ghi nhận loại kết thúc bằng `doFinally`, nhưng không nên đọc response body chỉ để log hoặc tạo thêm request phụ chỉ để ghi log.

Nếu dùng `doFinally` trong filter, cần lưu ý vị trí toán tử: đo thời gian cho một HTTP attempt khác với đo thời gian cho cả pipeline có `retry`, `timeout`, decode body. Khi cần observability xuyên nhiều tầng, sử dụng Micrometer Observation/Tracing hoặc instrument thích hợp để có số đo nhất quán, rồi gắn correlation ID làm thuộc tính bổ sung.

Không ghi token, cookie, authorization header, dữ liệu thanh toán hoặc raw query string có secret. Không coi cancel là lỗi nghiệp vụ nếu người dùng thực sự đã ngừng quan tâm kết quả.

## 8. Kiểm thử không cần kết nối mạng

Dùng `ExchangeFunction` giả, như ở phần 5, để ghi lại outbound header. Với JUnit 5 + `reactor-test`, test có thể kiểm tra ID thuộc đúng subscription:

```java
AtomicReference<String> seen = new AtomicReference<>();

ExchangeFunction fake = request -> {
    seen.set(request.headers().getFirst("X-Correlation-ID"));
    return Mono.just(ClientResponse.create(HttpStatus.OK)
            .body("done")
            .build());
};

WebClient client = WebClient.builder()
        .baseUrl("https://example.invalid")
        .exchangeFunction(fake)
        .filter(CorrelationFilter.create())
        .build();

StepVerifier.create(client.get()
                .uri("/test")
                .retrieve()
                .bodyToMono(String.class)
                .contextWrite(Context.of("correlationId", "test-123")))
        .expectNext("done")
        .verifyComplete();

assertEquals("test-123", seen.get());
```

Đây là **đoạn trong phương thức `@Test`**, cần import `AtomicReference`, `ExchangeFunction`, `ClientResponse`, `HttpStatus`, `WebClient`, `Mono`, `Context`, `StepVerifier` và `assertEquals`. Test dùng filter `CorrelationFilter` từ phần 3. Với Gradle, khai báo `testImplementation 'io.projectreactor:reactor-test'` và JUnit 5 tương thích.

Kiểm thử cancel thuần Reactor:

```java
AtomicBoolean cancelled = new AtomicBoolean();

StepVerifier.create(Mono.<String>never()
                .doOnCancel(() -> cancelled.set(true)))
        .thenCancel()
        .verify();

assertTrue(cancelled.get());
```

Test này xác minh giao thức Reactor, **không xác minh HTTP server thật dừng xử lý**. Muốn xác minh transport, dùng server giả điều khiển được thời điểm response/connection và theo dõi việc đóng kết nối, giải phóng body và các request thực tế.

Các trường hợp nên có test: không có Context, hai subscription có ID khác nhau, hai request lồng nhau, header không hợp lệ ở inbound, cancel trước và sau khi bắt đầu nhận response, timeout với lỗi downstream, retry sau một tác vụ gây tác dụng phụ, và tác vụ shared/hot không dừng như nguồn cold thông thường.

## 9. Lỗi thường gặp và cách khắc phục

| Nhầm lẫn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “Reactor Context là ThreadLocal mới” | Trộn ID giữa những request khi scheduler đổi thread | Dùng `deferContextual`, `contextWrite`; tích hợp MDC rõ ràng |
| Gọi `ctx.put(KEY, id)` nhưng bỏ kết quả mới | Không thay đổi Context đang dùng | Trả về Context được `put` tạo, ví dụ `contextWrite(c -> c.put(...))` |
| Đặt `contextWrite` sai phía của đoạn đọc | Filter có thể không thấy giá trị | Kiểm tra vị trí upstream/downstream và subscription boundary |
| Tạo filter đọc ID khi build client | ID của user/request bị giữ cố định hoặc mất | Đọc Context trong `Mono.deferContextual` khi request được subscribe |
| Dùng `ClientRequest.attribute` rồi kỳ vọng tự sang API kế tiếp | Request thứ hai thiếu ID | Dùng Context và filter thêm HTTP header |
| Dùng `subscribe()` thủ công trong controller | Mất ràng buộc cancel/error/context của caller | Kết hợp publisher bằng `flatMap`/`then` và trả về runtime |
| Coi correlation ID là token tin cậy | Dễ bị giả mạo, dẫn đến quyết định phân quyền sai | Xác thực độc lập; chỉ dùng ID cho tương quan log |
| Cho rằng cancel dừng giao dịch ở server | Có thể lặp thanh toán/ghi dữ liệu khi retry | Idempotency key, deadline, kiểm tra trạng thái cuối |
| Chỉ dùng `doOnError` để đếm cancel | Thiếu nhiều lần hủy không phát lỗi | Quan sát `doOnCancel` / `doFinally(CANCEL)` |
| Nhầm Reactor `timeout` với mọi network timeout | Độ trễ kết nối/đọc không có chính sách rõ ràng | Kết hợp deadline nghiệp vụ và timeout connector |
| Trả lại `ClientResponse` sau khi filter đọc body | Downstream hết body/rò tài nguyên | Không tiêu thụ body để log; xử lý body đúng vòng đời nếu can thiệp |
| Ghi mọi header/body vào log | Lộ secret/PII | Chỉ ghi những trường đã cho phép, dùng tracing chuẩn |

## 10. Tự kiểm tra mức độ hiểu

1. Cùng một `Mono` đọc `Context` nhưng có hai subscriber mang ID khác nhau: filter nhìn thấy ID nào? **ID thuộc subscriber hiện tại.**
2. Vì sao `contextWrite` thường nằm gần cuối pipeline? **Context truyền từ subscriber lên upstream, nơi `deferContextual` và filter đọc nó.**
3. Đã gắn ID vào Reactor Context thì dịch vụ phía sau có tự nhận ID? **Không; phải ghi vào header hoặc dùng cơ chế truyền trace được cấu hình.**
4. `flatMap` gọi thêm WebClient có giữ Context? **Có khi publisher con được kết hợp đúng trong cùng chuỗi reactive; tự `subscribe()` rời rạc làm đứt mối liên hệ này.**
5. `timeout` thường tạo tín hiệu gì? **Hủy upstream và phát lỗi `TimeoutException` downstream nếu không có fallback.**
6. Hủy WebClient có đảo ngược việc server đã xử lý? **Không; cần quy tắc nghiệp vụ cho request có tác dụng phụ và kết quả mơ hồ.**
7. Dùng `ThreadLocal` thay Context cho mọi async request có an toàn? **Không; một request có thể chuyển thread, và thread có thể xử lý nhiều request khác nhau.**
8. Một correlation ID có đủ thay thế distributed tracing không? **Không; tracing còn cần span, quan hệ và ngữ cảnh truyền chuẩn.**

Trong triển khai thực, hãy thống nhất nơi tạo ID, cách kiểm tra ID inbound, cách mang ID trong Reactor Context, filter gắn outbound header, cách log/trace, deadline và điều kiện idempotency trước khi bật retry tự động.

## 11. Tài liệu tham khảo

- [Spring Framework — WebClient Context](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html): hướng dẫn `Mono.deferContextual` và `contextWrite` trong filter.
- [Spring Framework — WebClient Attributes](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-attributes.html): phạm vi thuộc tính của một request.
- [Spring Framework — WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): `ExchangeFilterFunction` và cấu hình filter.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): chiều truyền Context, ContextView, tính bất biến.
- [Project Reactor — Error Handling / doFinally](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): phân biệt kết thúc và hủy.
- [Project Reactor — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `doOnCancel`, `doFinally` và `timeout`.
