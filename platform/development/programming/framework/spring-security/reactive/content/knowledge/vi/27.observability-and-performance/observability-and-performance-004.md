# Liên kết Reactor Context với quan sát, trace và MDC có kiểm soát

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) giải thích vì sao `ThreadLocal`/MDC không tự đi theo một luồng xử lý WebFlux; (2) đặt và đọc dữ liệu theo *subscription* bằng Reactor `Context`; (3) phân biệt correlation ID ứng dụng với trace ID/span ID và `SecurityContext` của Spring Security reactive; (4) dùng Micrometer Observation/Tracing để quan sát pipeline mà không làm rò rỉ dữ liệu; (5) chỉ đưa một số giá trị an toàn vào MDC trong phạm vi callback rồi khôi phục trạng thái cũ; (6) kiểm tra sự lan truyền ngữ cảnh qua scheduler, request đồng thời và nhánh lỗi.

**Bối cảnh:** Spring Security chạy trên Spring WebFlux, lập trình bất đồng bộ với `Mono`/`Flux`; các ví dụ Java dùng Java 17+. Những đoạn mã tích hợp Spring là thành phần của một ứng dụng có sẵn Spring Boot WebFlux, còn ví dụ `ContextDemo` bên dưới là một chương trình độc lập.

## 1. Vì sao cần Reactor Context?

Giả sử `GET /orders/42` đi qua bộ lọc bảo mật, gọi dịch vụ, gọi HTTP tới dịch vụ kho và ghi log khi có kết quả. Trong mô hình servlet truyền thống, nhiều thư viện lưu dữ liệu theo request trong `ThreadLocal`. Trong WebFlux, một request có thể chuyển từ thread xử lý sự kiện sang thread khác khi gặp `publishOn`, bộ hẹn giờ, I/O hoặc callback; ngược lại, một thread có thể phục vụ nhiều request. Vì vậy, dùng thread ID để suy ra request hay giữ `MDC.put(...)` xuyên suốt toàn bộ chuỗi là không an toàn.

Ba khái niệm có mục đích riêng:

| Thành phần | Dùng để làm gì? | Ranh giới/lưu ý |
| --- | --- | --- |
| Reactor `Context` / `ContextView` | Mang dữ liệu nhỏ, bất biến theo một *subscription*: requestId, khóa tương quan, ngữ cảnh bảo mật/quan sát do thư viện lưu | Gắn vào subscriber, không gắn vào thread; đi theo chuỗi Reactor còn giữ nguyên ngữ cảnh |
| Micrometer `Observation` và tracing | Đo thời gian, kết quả, tạo/ghép span và trace giữa các dịch vụ | Cần instrumentation, tracer bridge và exporter thích hợp; không phải mọi giá trị trong Reactor Context đều tự trở thành span |
| SLF4J MDC | Bổ sung trường vào một dòng log như `traceId`, `spanId`, `requestId` | Là trạng thái theo thread của logging backend; cần phục hồi/xóa sau phạm vi sử dụng |
| Spring Security `ReactiveSecurityContextHolder` | Truy xuất `Authentication` của luồng reactive | Dùng Reactor Context; tránh lấy user từ `SecurityContextHolder` kiểu servlet |

**Phân biệt ID:** `requestId` là khóa tương quan do ứng dụng định nghĩa; `traceId` định danh một distributed trace, còn `spanId` định danh một hoạt động trong trace. Không tự gán `requestId` vào `traceId` hay tạo trace giả từ một header tự do. Một request có thể mang cả ba nhưng chúng có vòng đời và độ tin cậy khác nhau.

Sơ đồ luồng điển hình:

```text
HTTP request
  -> WebFilter: xác thực/chuẩn hóa X-Request-ID
  -> contextWrite: thêm app.requestId vào Reactor Context
  -> Spring Security: cung cấp Reactive SecurityContext
  -> Controller/Service: deferContextual + getContext
  -> Observation/Tracing: ghi thời gian, trạng thái, span
  -> logger: đọc Context rồi gắn MDC đúng lúc ghi một dòng
  -> HTTP response: trả lại requestId đã chọn (nếu chính sách cho phép)
```

## 2. Cách Reactor Context lan truyền

`Context` là cấu trúc bất biến: `put` trả về context mới, không thay đổi đối tượng cũ. `contextWrite(...)` cung cấp context cho các operator **nằm phía trên nó khi subscription diễn ra**; `Mono.deferContextual(...)`/`Flux.deferContextual(...)` đọc context tại thời điểm đăng ký, thay vì đọc biến toàn cục tại thời điểm xây pipeline. Ngữ cảnh truyền qua `publishOn` và `subscribeOn` trong luồng Reactor chuẩn, dù thread thay đổi.

Ví dụ độc lập. Tạo hai tệp:

```groovy
// build.gradle
plugins {
    id 'java'
    id 'application'
}
repositories {
    mavenCentral()
}
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.7'
}
application {
    mainClass = 'demo.ContextDemo'
}
```

```java
// src/main/java/demo/ContextDemo.java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public final class ContextDemo {
    public static void main(String[] args) {
        var values = Flux.just("A", "B")
                .publishOn(Schedulers.parallel())
                .concatMap(item -> Mono.deferContextual(ctx ->
                        Mono.just(item + ": " + ctx.<String>get("requestId"))))
                .contextWrite(Context.of("requestId", "req-42"))
                .collectList()
                .block();

        System.out.println(values);
    }
}
```

Chạy `gradle run` (hoặc `./gradlew run` nếu dự án có Gradle wrapper). Dòng do chương trình in ra:

```text
[A: req-42, B: req-42]
```

`concatMap` giữ thứ tự A rồi B; `publishOn` chuyển phần xử lý phía sau sang scheduler nhưng `requestId` vẫn có vì nó thuộc subscription. `block()` ở đây chỉ phục vụ ví dụ chạy từ `main`; **không gọi `block()` trong request handler WebFlux**. Đưa `contextWrite` lên phía trên `deferContextual` có thể khiến đoạn đọc không thấy khóa vì context truyền từ downstream lên upstream. Hai lần `subscribe()` khác nhau là hai subscription; đừng dùng biến mutable chung để chia sẻ context giữa các request.

## 3. Đặt requestId an toàn trong Spring WebFlux

Một `WebFilter` có thể xác định request ID tại biên HTTP, cho phép ký tự đã chọn và đặt nó vào Reactor Context cho phần xử lý bên trong:

```java
// RequestIdWebFilter.java - nằm trong package được Spring quét
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public final class RequestIdWebFilter implements WebFilter {
    public static final String KEY = "app.requestId";
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String incoming = exchange.getRequest().getHeaders()
                .getFirst("X-Request-ID");
        String requestId = incoming != null && SAFE.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders().set("X-Request-ID", requestId);
        return chain.filter(exchange)
                .contextWrite(ctx -> ctx.put(KEY, requestId));
    }
}
```

Giải thích:

1. Giá trị đi từ client là **đầu vào chưa đáng tin**: regex trên loại xuống dòng và các ký tự điều khiển; nên giới hạn độ dài. Nếu không tin nguồn header, hãy luôn tạo ID mới ở biên đáng tin thay vì tái sử dụng ID client. Đừng dùng ID này làm bằng chứng xác thực.
2. Mỗi lần gọi `filter` tạo một `requestId` riêng. `contextWrite` không sửa shared state; các request chạy đồng thời không phải giành nhau một biến static.
3. Bộ lọc có thể đặt header phản hồi trước khi trả về `Mono<Void>`; chỉ phản hồi một opaque ID đã qua kiểm tra. Tùy hệ thống có thể để reverse proxy/API gateway chịu trách nhiệm tạo ID.
4. Khi truy xuất từ code không thuộc pipeline gốc (callback ngoại vi, `new Thread(...)`, `CompletableFuture` tự tạo), phải truyền dữ liệu/ngữ cảnh một cách có chủ đích; không giả định Context sẽ tự lan qua mọi API.

Trong service hoặc controller, đọc ID ở thời điểm subscription:

```java
import reactor.core.publisher.Mono;

public Mono<String> currentRequestId() {
    return Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault(RequestIdWebFilter.KEY, "missing")));
}
```

Đây là một **method minh họa trong bean/service**, không phải file Java độc lập. Không dùng `ThreadLocal` để lưu ID của request; không gọi `subscribe()` thủ công ở controller vì có thể tách vòng đời subscription và làm mất xử lý lỗi/cancellation của WebFlux.

## 4. Giữ đúng ngữ cảnh Spring Security reactive

Spring Security WebFlux dùng `ReactiveSecurityContextHolder` để đọc `SecurityContext` từ Reactor Context. Ví dụ khi cần lấy tên principal **bên trong một luồng đã được xác thực**:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> auth.getName())
            .defaultIfEmpty("anonymous");
}
```

Đây cũng là method minh họa cần đặt trong một component của ứng dụng. `defaultIfEmpty` xử lý trường hợp không có SecurityContext; nếu Spring Security có tạo `AnonymousAuthenticationToken`, tên principal có thể là `anonymousUser`. Quyền truy cập thực tế phải quyết định bằng cấu hình authorization, không bằng việc chuỗi tên có bằng `anonymous` hay không.

Trong ứng dụng WebFlux có cấu hình Spring Security, filter bảo mật thường thiết lập context cho pipeline; trong unit test có thể dùng `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))` để cung cấp đối tượng xác thực thử nghiệm. **Không lấy token, mật khẩu, cookie, thông tin nhận diện cá nhân hoặc toàn bộ `Authentication` rồi đặt vào MDC, metrics tags, trace attributes, baggage hay header phản hồi.** Khi cần ghi log nghiệp vụ, chỉ ghi trạng thái an toàn đã được chính sách cho phép; việc có `requestId` không cấp thêm quyền truy cập.

## 5. Kết nối Observation và distributed tracing

Trong ứng dụng Spring Boot WebFlux sử dụng Actuator, Micrometer Observation cung cấp mô hình đo hoạt động HTTP; Micrometer Tracing (khi có bridge) ánh xạ observation thành span để nối một distributed trace. Bộ dependency minh họa cho Gradle trong ứng dụng **đang dùng Spring Boot BOM quản lý phiên bản**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
    implementation 'io.projectreactor:reactor-core-micrometer'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Cần cấu hình exporter/collector OTLP thích hợp với môi trường. Ví dụ cấu hình sampling cho triển khai thử nghiệm hoặc tải thấp:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

`0.1` là tỷ lệ lấy mẫu 10%; thay đổi theo tải, mục tiêu quan sát và chi phí. Bật sampling 100% trong môi trường kiểm thử khi cần quan sát từng request, không mặc định coi đó là thiết lập production. Tracing cần có tracer bridge; chỉ thêm Actuator chưa đồng nghĩa mọi trace sẽ được export. Khi Micrometer Tracing hoạt động, Spring Boot có thể đưa `traceId` và `spanId` vào phần correlation của log. Không cần tạo thủ công các giá trị này từ header `X-Request-ID`.

Với một pipeline mà bạn muốn theo dõi riêng, Reactor cung cấp `tap` cộng với `Micrometer.observation` từ `reactor-core-micrometer`:

```java
// Đoạn mã tích hợp trong một service có repository và observationRegistry
import reactor.core.observability.micrometer.Micrometer;

return repository.findById(orderId)
        .name("orders.find")
        .tap(Micrometer.observation(observationRegistry));
```

Khi publisher được subscribe, listener quản lý vòng đời observation theo tín hiệu complete/error/cancel. Không đo một `Mono` bất đồng bộ bằng cách mở `Observation.Scope` trên thread hiện tại, trả về `Mono`, rồi đóng scope ngay: thao tác thực tế chưa diễn ra. Hãy dùng công cụ instrumentation hiểu Reactor hoặc lifecycle gắn với subscription; không tạo span cho từng phần tử nếu chỉ cần đo request hay thao tác chính.

Khi gọi HTTP ra ngoài, sử dụng `WebClient.Builder` được Spring Boot tự cấu hình để có các observation/tracing customization và propagation phù hợp. Ví dụ:

```java
// Thành phần Spring; builder được inject qua constructor
this.webClient = builder.baseUrl("https://inventory.example").build();
```

Đừng tùy tiện `WebClient.create(...)` rồi kỳ vọng tự động có trace propagation y hệt cấu hình của Boot. Các HTTP headers chuẩn của trace như `traceparent` nên được instrumentation quản lý theo chính sách tin cậy của hệ thống; các request ID ứng dụng có thể là header riêng nếu được phép.

Về tags: `method=GET`, `route=/orders/{id}`, `outcome=SUCCESS` có miền giá trị hữu hạn, phù hợp làm **low-cardinality tags** cho metrics. ID đơn hàng, ID người dùng, URL đầy đủ có biến động vô hạn là **high-cardinality**; không đẩy chúng thành nhãn metrics vì làm bùng nổ chuỗi thời gian. Ngay cả khi gắn một giá trị high-cardinality vào trace span, phải xét chính sách quyền riêng tư và retention.

## 6. MDC có kiểm soát: chỉ đặt trong phạm vi ghi log

MDC là `ThreadLocal` theo logging backend, vì vậy chống mẫu sai sau:

```java
// Anti-pattern: KHÔNG sử dụng trong WebFilter reactive
MDC.put("requestId", requestId);
return chain.filter(exchange);
```

MDC được đặt trên thread chạy filter, trong khi callback sau đó có thể ở thread khác; giá trị còn lại có thể ảnh hưởng request khác sử dụng lại thread. Cách thủ công an toàn khi cần log một signal là **đọc Reactor Context ngay trong callback, đặt MDC, log, rồi khôi phục giá trị cũ bằng finally**:

```java
// SafeMdcLogger.java - utility trong cùng package với RequestIdWebFilter
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import reactor.core.publisher.Signal;

public final class SafeMdcLogger {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeMdcLogger.class);

    private SafeMdcLogger() {}

    public static <T> Consumer<Signal<T>> logOnNext(String event) {
        return signal -> {
            if (!signal.isOnNext()) {
                return;
            }
            String requestId = signal.getContextView()
                    .getOrDefault(RequestIdWebFilter.KEY, "missing");
            String previous = MDC.get("requestId");
            try {
                MDC.put("requestId", requestId);
                LOG.info("event={} resultReceived=true", event);
            } finally {
                if (previous == null) {
                    MDC.remove("requestId");
                } else {
                    MDC.put("requestId", previous);
                }
            }
        };
    }
}
```

Áp dụng trên pipeline, ví dụ `repository.findById(id).doOnEach(SafeMdcLogger.logOnNext("order-read"))`. Với Logback, mẫu log phải chứa `%X{requestId}` thì trường MDC này mới hiện thành văn bản; nếu dùng structured logging, cấu hình encoder theo stack hiện hành. Đặt `MDC` trong một callback đồng bộ như trên chỉ đảm bảo giá trị đúng **khi callback đó thực thi**, không biến `MDC` thành dữ liệu lan truyền xuyên suốt cả request. Không gọi thao tác bất đồng bộ bên trong `try` rồi mong MDC còn nguyên ở thread khác.

Nếu log không cần định dạng dựa trên MDC, giải pháp đơn giản hơn là đưa ID thành tham số rõ ràng: `log.info("requestId={} action=read", requestId)`. Điều này tránh chi phí thao tác ThreadLocal. Tránh log toàn bộ payload, bearer token hay `SecurityContext` khi debug.

### Tự động context propagation với Micrometer

Reactor tích hợp với `io.micrometer:context-propagation`. Ở **default mode**, việc phục hồi `ThreadLocal` từ Reactor Context được hỗ trợ trong một số operator (đặc biệt `handle`/`tap`) khi có accessor tương ứng; không nên coi mọi callback đều có sẵn MDC. `contextCapture()` chụp các `ThreadLocal` đã được đăng ký accessor vào Reactor Context lúc subscription.

Nếu hệ thống thực sự cần tự động chuyển đổi giữa Reactor Context và các `ThreadLocal` đã đăng ký, có thể bật sớm lúc khởi động:

```java
import reactor.core.publisher.Hooks;

// Gọi lúc khởi động, trước khi có các subscription ứng dụng:
Hooks.enableAutomaticContextPropagation();
```

Chế độ này cần thư viện `context-propagation` và `ThreadLocalAccessor` tương ứng; hook **chỉ tác động đến subscription tạo sau khi bật**. Nó không tự động biến mọi key như `app.requestId` thành MDC: phải có accessor/chiến lược mapping đúng và tránh đăng ký trùng với instrumentation Boot đang quản lý. Cơ chế phục hồi còn phải xóa trạng thái khi key vắng mặt để tránh leak. Vì can thiệp toàn cục có thể thêm chi phí và đụng tới hành vi thư viện, hãy ưu tiên cơ chế do Spring Boot/Micrometer cấu hình, kiểm thử trước khi bật thêm hook thủ công, và so sánh throughput/latency.

## 7. Thử nghiệm hành vi và QA

Với `reactor-test`, kiểm tra dữ liệu vẫn có sau một đoạn xử lý bất đồng bộ:

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ReactorContextTest {
    @Test
    void requestIdSurvivesAsyncBoundary() {
        Mono<String> pipeline = Mono.delay(Duration.ofMillis(5))
                .flatMap(tick -> Mono.deferContextual(ctx ->
                        Mono.just(ctx.<String>get("requestId"))))
                .contextWrite(Context.of("requestId", "req-test"));

        StepVerifier.create(pipeline)
                .expectNext("req-test")
                .verifyComplete();
    }
}
```

Các phép thử cần có ở mức integration:

1. **Hai request đồng thời:** gán ID A/B, thực hiện `publishOn` và gọi downstream; mỗi dòng log chỉ chứa ID của request tương ứng, không thấy ID của request trước trên thread tái sử dụng.
2. **Đường lỗi/cancel:** gây `onError`/cancellation; observation được hoàn tất đúng lifecycle; MDC thủ công vẫn phục hồi nhờ `finally`; không để header/ID rò vào request kế tiếp.
3. **Security:** gọi endpoint với và không có xác thực; `ReactiveSecurityContextHolder` tuân theo chính sách 401/403; không lấy `Authentication` từ `SecurityContextHolder` servlet.
4. **Tracing:** gọi một endpoint qua `WebClient.Builder` Boot, kiểm tra trace có span cha/con và correlation trong log theo cấu hình; lưu ý sampling/exporter có thể làm trace không xuất hiện ở collector.
5. **Header không hợp lệ:** thử giá trị dài, xuống dòng, ký tự lạ; phải được thay ID mới. Không log trực tiếp header không tin cậy.
6. **Hiệu năng:** so sánh số log, độ trễ p95/p99 và CPU khi bật/tắt thêm scope MDC hoặc automatic propagation. Tránh ghi log mỗi phần tử của `Flux` tốc độ cao khi chỉ cần quan sát tổng thể.

### Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `deferContextual` không có `requestId` | `contextWrite` đặt sai vị trí, tạo subscription mới ngoài pipeline, hoặc mất ngữ cảnh tại API ngoại vi | Kiểm tra thứ tự operator; thêm ID tại downstream của đoạn đọc; truyền context rõ qua biên ngoại vi |
| MDC đúng ở đầu request nhưng sai sau `publishOn` | MDC thuộc thread, không được truyền qua scheduler | Chỉ đặt MDC tại thời điểm log và khôi phục; hoặc sử dụng propagation đã cấu hình, thử trên scheduler thật |
| Log có `requestId` nhưng không có `traceId` | Chưa có tracing bridge/observation đang hoạt động, thiếu log pattern hoặc scope tương ứng | Kiểm tra dependencies, instrumentation, logging và cấu hình sampling; không sửa bằng cách tạo traceId giả |
| Collector không thấy span | Exporter/endpoint sai, sampling thấp, mạng hoặc collector lỗi | Kiểm tra cấu hình exporter, xác nhận có span được tạo và kết nối tới backend |
| Request B xuất hiện ID của request A | MDC không được clear/restore, biến mutable/global hoặc scope bị giữ quá lâu | Tìm `MDC.put` không có `finally`, bỏ state global và thêm kiểm thử concurrent |
| Metrics có quá nhiều series | Dùng userId/orderId/raw URL làm metric tags | Dùng route template/status/operation có cardinality thấp; chuyển thông tin giàu chi tiết sang log/trace được kiểm soát |

## 8. Các nguyên tắc chốt

- Xem **Reactor Context là nguồn dữ liệu theo subscription**; đọc bằng `deferContextual`, thêm bằng `contextWrite`, không phụ thuộc thread.
- Để **Spring Security** quản lý ngữ cảnh xác thực qua `ReactiveSecurityContextHolder`; không copy đối tượng xác thực hay token vào hệ thống quan sát.
- Để **Micrometer Observation/Tracing** quản lý span, trace propagation, sampling và exporter. Correlation ID riêng là khóa tra log, không thay cho distributed trace.
- Dùng **MDC ngắn hạn**, khôi phục trạng thái cũ trong `finally`; nếu chỉ cần log một giá trị, truyền nó qua tham số log rõ ràng. Không để MDC tồn tại qua ranh giới async.
- Đo chi phí instrumentation, kiểm soát cardinality và dữ liệu nhạy cảm; kiểm thử concurrent, error/cancel, biên HTTP, scheduler và outbound HTTP trước khi áp dụng rộng.

## Tài liệu chính thức

- Reactor Context Propagation: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Reactor Micrometer instrumentation: https://projectreactor.io/docs/core/release/reference/metrics.html
- Spring Security `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Boot Actuator Tracing: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- Micrometer Observation: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
