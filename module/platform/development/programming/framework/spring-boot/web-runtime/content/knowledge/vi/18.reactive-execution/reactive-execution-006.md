# Reactor Context và dữ liệu gắn với yêu cầu khi đổi luồng trong Spring Boot WebFlux

## 1. Vấn đề: một HTTP request không luôn chạy trên một thread

Trong mô hình Servlet đồng bộ, lập trình viên thường hình dung một request được xử lý bởi một worker thread và có thể tạm gắn dữ liệu vào `ThreadLocal`: mã truy vết (`requestId`), thông tin người dùng, locale hoặc giá trị MDC để ghi log.

Trong **Spring WebFlux + Project Reactor**, một chuỗi xử lý bất đồng bộ là các `Publisher` (`Mono`/`Flux`) được *subscribe*; các operator có thể chạy tại thời điểm và trên thread khác nhau. Nhiều request chia sẻ event-loop; một request có thể chuyển từ event-loop sang scheduler khác (ví dụ qua `publishOn`), rồi quay về thread khác. Do đó **thread không phải định danh ổn định của request**.

~~~text
HTTP request A                 HTTP request B
     |                              |
     v                              v
Reactor Netty event-loop-1  Reactor Netty event-loop-1
     |                              |
     +-- publishOn(...)             +-- xử lý async
             |                              |
             v                              v
       parallel-2                    parallel-1
             |                              |
      requestId = A                  requestId = B
       (Reactor Context)            (Reactor Context)
~~~

Sơ đồ chỉ minh họa; tên thread và lịch chạy thực tế có thể khác. **Điều cần bảo toàn là đúng dữ liệu theo từng subscription**, bất kể operator chạy ở thread nào.

**Reactor `Context`** giải quyết bài toán truyền *metadata theo chuỗi phản ứng*: thay vì cất thông tin vào biến toàn cục hoặc dựa vào `ThreadLocal`, dữ liệu đi cùng **`Subscriber` và quan hệ subscription**. Ví dụ điển hình là correlation ID, metadata tracing, tenant ID đã xác minh hoặc thông tin bổ trợ phục vụ thư viện. Nó không phải bộ nhớ dùng chung toàn ứng dụng và không thay thế các tham số nghiệp vụ chính.

## 2. Ba khái niệm rất dễ nhầm

| Cơ chế | Gắn với đối tượng nào? | Có theo qua `publishOn`? | Dùng lúc nào? |
| --- | --- | --- | --- |
| `ThreadLocal<T>` | Một thread Java | **Không mặc định**; cần cầu nối/cơ chế khôi phục được cấu hình | Thư viện imperative, MDC truyền thống |
| `ServerWebExchange.getAttributes()` | Một HTTP exchange của WebFlux | Dữ liệu vẫn thuộc exchange nếu còn tham chiếu đến **cùng exchange** | Trao đổi dữ liệu giữa WebFilter/handler khi có exchange |
| Reactor `Context`/`ContextView` | **Subscriber** trong chuỗi Reactor | **Có**, qua các operator Reactor giữ đúng quan hệ subscription | Metadata đi qua service, `flatMap`, `publishOn`, `subscribeOn`, client/filter reactive |

Một biến `ThreadLocal` có thể chứa giá trị của request A trên thread hiện tại; khi B dùng lại thread đó, giá trị A có nguy cơ bị đọc nhầm nếu code quản lý sai. Với Reactor Context, mỗi subscription nhận một ngữ cảnh logic riêng, vì thế không cần buộc tất cả bước xử lý về cùng một thread.

**Không đánh đồng Reactor Context với "HTTP request scope" tuyệt đối**: context gắn với subscriber; một request thường tạo chuỗi subscription thích hợp, nhưng một request có thể sinh các publisher khác, và việc tự gọi `subscribe()` hoặc nhảy sang cơ chế bất đồng bộ không phải Reactor có thể tạo ranh giới mới. Chỉ dữ liệu được gắn/lan truyền đúng tại ranh giới đó mới tiếp tục xuất hiện.

## 3. API cốt lõi của Reactor Context

`reactor.util.context.Context` là cấu trúc giống map, chứa cặp **key → value**; key và value thuộc kiểu `Object`. `Context` **immutable**: các thao tác ghi trả về một Context **mới**, không sửa bản đã có.

- `Context.empty()`: tạo context rỗng.
- `Context.of(key, value)`: tạo context ban đầu.
- `context.put(key, value)`: trả Context mới có key/value đó.
- `context.delete(key)`: trả Context mới không có key đó.
- `context.putAll(otherContextView)`: tạo Context sau khi kết hợp dữ liệu.
- `ContextView`: giao diện chỉ đọc với `get(key)`, `getOrDefault(key, defaultValue)`, `getOrEmpty(key)`, `hasKey(key)`.

`ContextView` chính là thứ nên đưa cho tầng đọc, tránh để code lầm tưởng có thể sửa context hiện tại trực tiếp.

Có hai thao tác Reactor quan trọng nhất:

~~~java
// Ghi: áp dụng Context cho các operator nằm PHÍA TRÊN trong chain.
Mono<String> result = someMono
    .contextWrite(ctx -> ctx.put("requestId", "req-101"));

// Đọc: trì hoãn tới thời điểm subscribe để lấy Context đang hiệu lực.
Mono<String> requestId = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("requestId", "missing")));
~~~

**Không gọi `Context.of(...)` là đã tự gắn dữ liệu vào một request.** Đó chỉ là một đối tượng bất biến; cần operator `contextWrite(...)` ở vị trí đúng để đưa vào subscription.

### 3.1. `contextWrite` ghi như thế nào?

Hai dạng phổ biến:

~~~java
// Một ContextView được merge với context đi từ downstream.
source.contextWrite(Context.of("requestId", "req-101"));

// Hàm tạo bản Context mới dựa vào Context hiện hành.
source.contextWrite(ctx -> ctx.put("requestId", "req-101"));
~~~

Dạng hàm có ưu điểm giữ lại khóa của thư viện khác, chẳng hạn thông tin tracing/security mà hệ thống đã đặt. **Tránh** tạo `Context.empty()` và trả về nó tùy tiện vì có thể làm mất metadata downstream; đừng tự xóa khóa của framework.

### 3.2. `deferContextual` đọc đúng lúc

~~~java
Mono<String> readId = Mono.deferContextual(contextView ->
    Mono.just(contextView.getOrDefault("requestId", "missing")));
~~~

`deferContextual` nhận ContextView tại **thời điểm subscription**, không phải khi khai báo biến `readId`. Đặt nó trong các phép nối chuỗi như `flatMap` giúp đọc context ở bước thực hiện bất đồng bộ, không phụ thuộc vào thread đang chạy.

Nếu có khả năng thiếu khóa, nên dùng `getOrDefault` hoặc `getOrEmpty` và quy định rõ hành vi; `get(key)` khi thiếu sẽ phát sinh lỗi, phù hợp khi hợp đồng yêu cầu giá trị bắt buộc. Key không bảo đảm an toàn kiểu tại compile time: tránh lạm dụng string key không gian tên chung; tạo constant/kiểu key dùng nhất quán và ép kiểu cẩn thận.

## 4. Quy tắc quan trọng nhất: **Context đi từ downstream về upstream khi subscribe**

Đây là điểm khác trực giác so với luồng dữ liệu:

- Tín hiệu dữ liệu (`onNext`, `onError`, `onComplete`) thường đi **từ nguồn xuống subscriber**.
- Context được subscriber cung cấp cho operator thông qua quá trình subscription, theo hướng **từ downstream lên upstream**.
- Vì vậy, một `contextWrite` gần phía cuối chuỗi có thể cung cấp giá trị cho `deferContextual` phía đầu chuỗi, dù mã nguồn ghi `contextWrite` ở dòng dưới.

Ví dụ **đúng**:

~~~java
Mono<String> result =
    Mono.deferContextual(ctx ->
        Mono.just("id=" + ctx.get("requestId")))
    .contextWrite(ctx -> ctx.put("requestId", "req-101"));

// subscribe/block -> "id=req-101"
~~~

~~~text
Khi subscribe:
Subscriber --> contextWrite [put requestId=req-101] --> deferContextual
                 ^ thêm context cho operator phía upstream

Khi phát tín hiệu:
deferContextual --> contextWrite --> Subscriber
~~~

Ví dụ **đặt sai vị trí**:

~~~java
Mono<String> wrong =
    Mono.just("begin")
        .contextWrite(ctx -> ctx.put("requestId", "req-101"))
        .flatMap(ignore -> Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("requestId", "missing"))));

// block -> "missing"
~~~

`flatMap` ở **dưới** `contextWrite` nằm ngoài phạm vi mà lần ghi đó tác động. Không hiểu quy tắc này thường khiến developer tưởng `publishOn` làm mất context, trong khi nguyên nhân là thứ tự operator.

### 4.1. Ghi đè khóa và giới hạn của chuỗi con

~~~java
Mono<String> value =
    Mono.deferContextual(ctx -> Mono.just(ctx.get("requestId")))
        .contextWrite(ctx -> ctx.put("requestId", "inner"))
        .contextWrite(ctx -> ctx.put("requestId", "outer"));

// result: "inner"
~~~

Giá trị `inner` được ghi ở `contextWrite` **gần operator đọc hơn về phía downstream**, nên operator đọc thấy `inner`. Hai contextWrite không đồng nghĩa một map mutable dùng chung.

Với `flatMap`, `contextWrite` ở **publisher con** chỉ làm thay đổi context mà publisher con nhìn thấy:

~~~java
Mono<String> example =
    Mono.just("item")
        .flatMap(item ->
            Mono.deferContextual(ctx ->
                Mono.just(item + ":" + ctx.get("requestId")))
                .contextWrite(ctx -> ctx.put("requestId", "local")))
        .flatMap(result ->
            Mono.deferContextual(ctx ->
                Mono.just(result + ":" + ctx.get("requestId"))))
        .contextWrite(ctx -> ctx.put("requestId", "request"));

// result: "item:local:request"
~~~

Lần ghi `local` chỉ thuộc publisher con đầu tiên; lần đọc trong `flatMap` kế tiếp vẫn thấy `request` của chuỗi bên ngoài. Đây là đặc tính **phạm vi**, không phải Reactor "rơi mất" dữ liệu.

## 5. Chuyển thread qua `publishOn` và `subscribeOn` có làm mất Context không?

**Thông thường không**, nếu bạn giữ một chuỗi Reactor được composition đúng và không tự tạo subscription độc lập. Context đi theo subscriber, không theo thread hiện tại.

| Operator | Ảnh hưởng lịch chạy | Ảnh hưởng Context |
| --- | --- | --- |
| `publishOn(scheduler)` | Chuyển việc phát signal/ xử lý phía **downstream** sang scheduler được chọn (cho đến một ranh giới mới) | Context vẫn nhìn thấy trong phạm vi subscription |
| `subscribeOn(scheduler)` | Ảnh hưởng thời điểm/luồng subscription và thực thi nguồn upstream; vị trí trong chain thường ít quyết định tác động thread hơn `publishOn` | Context vẫn được truyền theo subscription |
| `flatMap` | Có thể có publisher con bất đồng bộ, xử lý xen kẽ | Publisher con được Reactor subscribe trong chain thường nhận context phù hợp; ghi riêng ở con có phạm vi riêng |
| `delayElement` / `Mono.delay` | Có thể dùng scheduler/timer để phát tín hiệu sau | Không khiến Context biến mất chỉ vì đổi thread |
| `subscribe()` gọi thủ công | Tạo một subscription **mới**, có vòng đời riêng | Có thể không còn context của luồng request ban đầu nếu không truyền chủ động |
| `CompletableFuture` / `ExecutorService` | Chạy theo cơ chế ngoài Reactor | Không tự động truyền Reactor Context chỉ nhờ nộp task |

Ví dụ:

~~~java
Mono<String> switched =
    Mono.just("work")
        .publishOn(Schedulers.parallel())
        .flatMap(value -> Mono.deferContextual(ctx ->
            Mono.just(value + "@" + ctx.get("requestId"))))
        .contextWrite(ctx -> ctx.put("requestId", "req-101"));

// block -> "work@req-101"
~~~

`flatMap` ở đây chạy sau `publishOn`; `deferContextual` vẫn thấy ID. Thử thêm một `publishOn(Schedulers.boundedElastic())` ở chuỗi thích hợp cũng không làm ID biến mất theo cơ chế mặc định.

**Đừng gọi blocking I/O trực tiếp trên event-loop Netty**, kể cả khi Context đã đúng. Với tác vụ blocking buộc phải tích hợp, dùng API bất đồng bộ hoặc bọc phần blocking bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và giới hạn tài nguyên hợp lý. **Context không biến code blocking thành non-blocking**.

## 6. Ví dụ Reactor độc lập, Java 17+: chứng minh tính biệt lập theo subscription

Tệp `src/main/java/demo/context/ReactorContextDemo.java` (thuộc dự án đã có dependency `io.projectreactor:reactor-core`, chẳng hạn một dự án Spring Boot WebFlux). Code Java đầy đủ:

~~~java
package demo.context;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {
    private static final String REQUEST_ID = "demo.requestId";

    public static void main(String[] args) {
        Mono<String> read = Mono.deferContextual(ctx ->
                Mono.just(ctx.get(REQUEST_ID)));

        // Cùng một Publisher được subscribe hai lần với hai context khác nhau.
        String first = read
                .contextWrite(Context.of(REQUEST_ID, "req-A"))
                .block();
        String second = read
                .contextWrite(Context.of(REQUEST_ID, "req-B"))
                .block();

        Mono<String> switched = Mono.just("work")
                .publishOn(Schedulers.parallel())
                .flatMap(value -> Mono.deferContextual(ctx ->
                        Mono.just(value + "@" + ctx.get(REQUEST_ID))))
                .contextWrite(ctx -> ctx.put(REQUEST_ID, "req-C"));

        Mono<String> wrongScope = Mono.just("start")
                .contextWrite(ctx -> ctx.put(REQUEST_ID, "req-D"))
                .flatMap(value -> Mono.deferContextual(ctx ->
                        Mono.just(ctx.getOrDefault(REQUEST_ID, "missing"))));

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("switched=" + switched.block());
        System.out.println("wrongScope=" + wrongScope.block());
    }
}
~~~

**stdout chính xác của các dòng `System.out.println`** (không tính log framework nếu có):

~~~text
first=req-A
second=req-B
switched=work@req-C
wrongScope=missing
~~~

Giải thích:

1. `read` không cố định ID khi khai báo. Mỗi lần `block()` tạo subscription mới với Context riêng, nên hai kết quả là `req-A` và `req-B`, không bị lẫn.
2. `switched` đọc ID từ Context **sau ranh giới `publishOn`** nhưng vẫn trả `req-C`.
3. `wrongScope` minh họa lỗi thứ tự: `contextWrite` quá sớm về vị trí trong chain nên `flatMap` phía sau không nhìn thấy `req-D`.
4. `block()` chỉ được dùng ở **hàm main/ứng dụng demo** để chờ kết quả và in ra console. **Không copy `block()` vào controller/handler WebFlux** vì có nguy cơ khóa event-loop.

Nếu dự án dùng Gradle và đã có Reactor Core trên classpath, hãy chạy class này theo cấu hình `application`/JavaExec phù hợp. Trong dự án Spring Boot, ví dụ HTTP tiếp theo cho thấy cách vận dụng cùng nguyên lý mà không cần `block()`.

## 7. Gắn request ID từ WebFilter vào Reactor Context của Spring Boot WebFlux

Trong WebFlux, nguồn request thường ở `ServerWebExchange`. WebFilter có thể lấy header `X-Request-Id`, kiểm tra định dạng, tự sinh ID khi thiếu, thêm response header để dễ đối chiếu, rồi **gắn ID vào Reactor Context cho toàn bộ chain**. Controller/service đọc ID bằng `deferContextual` ngay cả sau khi chuyển scheduler.

**Điều kiện ví dụ:** Java 17+, Spring Boot 3.x, dependency `spring-boot-starter-webflux`; để dùng Reactor Netty mặc định, tránh đồng thời thêm `spring-boot-starter-web` nếu muốn Boot tự chọn `REACTIVE`. Tệp độc lập:

`src/main/java/demo/context/ReactiveContextApplication.java`

~~~java
package demo.context;

import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebFilter;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveContextApplication {
    static final String REQUEST_ID_KEY = "demo.requestId";

    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }

    @Bean
    WebFilter requestIdContextFilter() {
        return (exchange, chain) -> {
            String supplied = exchange.getRequest()
                    .getHeaders().getFirst("X-Request-Id");

            // Chỉ nhận ID có định dạng an toàn cho demo;
            // header do client gửi chưa phải định danh đáng tin.
            String requestId = supplied != null
                    && supplied.matches("[A-Za-z0-9_-]{1,64}")
                    ? supplied
                    : UUID.randomUUID().toString();

            exchange.getResponse().getHeaders()
                    .set("X-Request-Id", requestId);

            // Đặt contextWrite dưới chain để handler đọc được ở upstream.
            return chain.filter(exchange)
                    .contextWrite(ctx ->
                            ctx.put(REQUEST_ID_KEY, requestId));
        };
    }

    public record TraceResponse(String requestId, String stage) {}
}

@RestController
class TraceController {
    @GetMapping("/context")
    Mono<ReactiveContextApplication.TraceResponse> contextInfo() {
        return Mono.just("request")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> Mono.deferContextual(ctx -> {
                    String id = ctx.get(
                            ReactiveContextApplication.REQUEST_ID_KEY);

                    return Mono.just(
                            new ReactiveContextApplication.TraceResponse(
                                    id, "after-publishOn"));
                }));
    }
}
~~~

Các bước đi của một HTTP request:

~~~text
GET /context
X-Request-Id: req-101
       |
       v
WebFilter đọc/kiểm tra header, quyết định requestId=req-101
       |
       v
chain.filter(exchange)
       |
       +-- .contextWrite(ctx -> ctx.put("demo.requestId", "req-101"))
                       |
                       | Context đưa về phía upstream lúc subscribe
                       v
          @GetMapping("/context")
                       |
                 Mono.just(...)
                       |
               publishOn(parallel)
                       |
               flatMap + deferContextual
                       |
         đọc demo.requestId = req-101
                       |
                       v
                HTTP response JSON
~~~

**Cách chạy:** trong dự án Spring Boot 3.x đã cấu hình Gradle wrapper, dùng `./gradlew bootRun` (Windows PowerShell: `.\gradlew.bat bootRun`). Với cấu hình port mặc định, gọi:

~~~bash
curl -i "http://localhost:8080/context" \
  -H "X-Request-Id: req-101"
~~~

Những thông tin cần kiểm tra trong response:

~~~http
HTTP/1.1 200 OK
X-Request-Id: req-101
Content-Type: application/json

{"requestId":"req-101","stage":"after-publishOn"}
~~~

Đây là **các dòng mang ý nghĩa cần kiểm tra**, không phải toàn bộ response byte-for-byte: header khác, thứ tự header và cách framework truyền body có thể thay đổi. Vì ví dụ có `publishOn` trước `flatMap`, ID vẫn xuất hiện sau bước đổi scheduler là bằng chứng Context theo đúng subscription. Tên thread chạy thực tế có thể khác giữa các lần chạy, nên output không cố định tên thread.

Thử gửi thêm một request với `X-Request-Id: req-202`. Response của request mới phải mang `req-202`; dữ liệu không phải biến static toàn cục bị ghi đè. Nếu bỏ header, filter tạo UUID; response header và JSON body phải cùng mang **UUID của request ấy**.

### 7.1. Vì sao dùng `WebFilter` nhưng controller vẫn nhận Context?

`WebFilter` nhận `ServerWebExchange` và trả `Mono<Void>` từ `chain.filter(exchange)`. Khi gắn `contextWrite` **sau** publisher của toàn bộ filter chain, Context chứa request ID có thể truyền về các operator upstream thuộc handler/controller và các service được composition bên trong chain ấy.

Đừng gọi:

~~~java
// SAI: subscribe() riêng trong filter, không trả đúng chain cho WebFlux.
// chain.filter(exchange).subscribe();
// return Mono.empty();
~~~

Việc subscribe thủ công có thể tách xử lý khỏi vòng đời HTTP, mất điều phối error/completion/cancellation và phá ranh giới context. Hãy **trả publisher** cho framework.

### 7.2. Tạo key và đánh giá dữ liệu đầu vào

Dùng constant có không gian tên rõ (`demo.requestId`), hoặc key object chuyên dụng mà các tầng cùng tham chiếu. Reactor Context cho phép key bất kỳ kiểu Object; cùng key bị ghi đè theo phạm vi. Header `X-Request-Id` trong ví dụ được giới hạn độ dài và ký tự để dễ demo/tránh log injection cơ bản; trong ứng dụng thật hãy có chính sách sinh/cấp mã truy vết, độ tin cậy proxy và tiêu chuẩn observability phù hợp. **Không bao giờ coi requestId do client tự gửi là bằng chứng đã xác thực/ủy quyền**.

Không đặt mật khẩu, raw access token, dữ liệu thanh toán hay toàn bộ request body vào Context chỉ để "tiện dùng" hoặc ghi log. Context không tự mã hóa, không tự cấp quyền và không phải kho lưu session lâu dài.

## 8. WebFlux: Service đọc Context mà không phụ thuộc vào HTTP controller

Một ưu điểm của Context là service không cần nhận thêm tham số `requestId` ở mọi method chỉ phục vụ logging/tracing. Ví dụ **đoạn minh họa**, dùng key giống ứng dụng ở mục 7:

~~~java
import reactor.core.publisher.Mono;

class AuditService {
    Mono<String> audit(String action) {
        return Mono.deferContextual(ctx -> {
            String requestId = ctx.getOrDefault(
                    ReactiveContextApplication.REQUEST_ID_KEY, "unknown");

            return Mono.just("action=" + action + ", requestId=" + requestId);
        });
    }
}
~~~

Controller có thể **compose** service:

~~~java
// Nằm trong một reactive chain đã được WebFilter cung cấp Context:
return auditService.audit("read-book")
        .flatMap(logLine -> someReactiveOperation(logLine));
~~~

Đây là snippet minh họa, không phải controller chạy độc lập: `auditService` và `someReactiveOperation` phải được định nghĩa/inject trong lớp thực tế. Context được service đọc ở subscription, kể cả khi service nằm ở module khác, miễn là chain vẫn nối đúng.

**Cân nhắc thiết kế:** requestId, trace context, locale cho logging/observability thường là metadata xuyên tầng; còn `bookId`, số lượng mua, số tiền, đầu vào nghiệp vụ nên đi bằng tham số hoặc model rõ ràng. Tránh dùng Context thành một `Map<String,Object>` chứa mọi thứ: khó xác định dependency và lỗi thiếu key.

## 9. Phân biệt với `ServerWebExchange`, request attributes và SecurityContext

### 9.1. Dùng exchange attributes khi còn exchange

~~~java
// Trong WebFilter hoặc handler có ServerWebExchange:
exchange.getAttributes().put("auditMarker", "checked");
Object marker = exchange.getAttribute("auditMarker");
~~~

`ServerWebExchange` giữ dữ liệu gắn với HTTP exchange cụ thể. Khi mọi code cần đọc đều có cùng exchange (truyền tham số hoặc tham chiếu), attributes rất tiện. **Không tự động có exchange ở mọi service không nhận exchange** và đừng lưu exchange vào context nếu chỉ cần một metadata nhỏ, vì giữ đối tượng request lớn có thể kéo dài vòng đời tham chiếu.

### 9.2. WebClient và cuộc gọi HTTP đi ra

Một lời gọi `WebClient` được **compose** trong chuỗi Reactor có thể đọc Reactor Context ở filter bằng `Mono.deferContextual`. Tuy nhiên **Reactor Context không tự biến thành HTTP header gửi sang service khác**. Muốn correlation ID đi qua network, phải chủ động đặt header theo hợp đồng/tracing framework.

Đoạn minh họa cấu hình filter outbound (cần imports `WebClient`, `ClientRequest`, `Mono` trong lớp cấu hình):

~~~java
WebClient client = WebClient.builder()
        .filter((request, next) ->
            Mono.deferContextual(ctx -> {
                String id = ctx.getOrDefault(
                        ReactiveContextApplication.REQUEST_ID_KEY,
                        "unknown");

                ClientRequest outbound = ClientRequest.from(request)
                        .headers(headers -> headers.set("X-Request-Id", id))
                        .build();

                return next.exchange(outbound);
            }))
        .build();
~~~

Trong ứng dụng thật, nên quy định chuẩn trace/propagation liên dịch vụ và chỉ gửi header tới đích hợp lệ. Một thư viện observability có thể xử lý W3C Trace Context hoặc header khác; không tự trộn nhiều cơ chế gây xung đột.

### 9.3. Security: đừng tự làm lại cơ chế framework

Spring Security cho WebFlux có `ReactiveSecurityContextHolder`, dùng ngữ cảnh reactive của chính security framework để truy xuất `SecurityContext`. Ví dụ:

~~~java
Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(sc -> sc.getAuthentication().getName());
~~~

Đoạn minh họa này cần Spring Security reactive dependency và context xác thực tương ứng; khi chưa xác thực, publisher có thể rỗng hoặc authentication không tồn tại theo cấu hình. Đừng tự đặt `"principal"` vào Reactor Context rồi xem nó là nguồn xác thực đáng tin; dùng cơ chế authentication/authorization chính thức.

## 10. `ThreadLocal` / MDC khi đổi thread: vì sao mất dữ liệu và cách xử lý đúng

MDC của các thư viện logging phổ biến thường dựa trên `ThreadLocal`. Trong request reactive, một đoạn code có thể chạy trên event-loop, sau đó tín hiệu chuyển sang thread của scheduler khác. **`ThreadLocal.get()` trên thread mới không mặc nhiên trả dữ liệu đã set ở thread cũ**.

~~~java
// CÁCH DỄ LỖI trong reactive app:
MDC.put("requestId", "req-101");

return Mono.just("x")
        .publishOn(Schedulers.parallel())
        .doOnNext(x -> log.info("processing {}", x));
// MDC trên thread của publishOn có thể trống/khác.
// Ngoài ra MDC đặt ở thread cũ có nguy cơ leak nếu không clear đúng.
~~~

Đây là snippet minh họa lỗi, không phải ví dụ nên copy vào handler. Không suy diễn rằng mọi trường hợp đều mất MDC: thư viện hoặc framework có thể đã kích hoạt **context propagation**. Cần hiểu rõ cơ chế đang dùng.

### 10.1. Hai tầng khác nhau

1. **Reactor Context propagation**: `contextWrite` và `deferContextual` vận hành trực tiếp trong Reactor; thông tin đi theo subscription và thường vẫn còn qua `publishOn`/`subscribeOn` **không cần bật tính năng bridge ThreadLocal**.
2. **ThreadLocal ↔ Reactor Context propagation**: thư viện Micrometer Context Propagation có thể *capture* và *restore* một số ThreadLocal **được đăng ký bằng `ThreadLocalAccessor`**. Đây là tính năng bổ sung để tích hợp code imperative, MDC/observability và reactive pipeline.

Reactor hiện đại hỗ trợ chế độ **limited/default** (khôi phục tại một số vị trí/operator nhất định) và **automatic** (khôi phục rộng hơn). Với Spring Boot 3.2/3.3 có thể cấu hình:

~~~properties
# Chỉ khi ứng dụng đã có thành phần context-propagation phù hợp
spring.reactor.context-propagation=auto
~~~

Cấu hình này dành cho việc khôi phục ThreadLocal đã **có accessor/bridge**; **không** có nghĩa mọi biến `new ThreadLocal<>()` bất kỳ tự động xuất hiện trong Reactor Context. Tính năng có chi phí; cân nhắc benchmark và mức tải trước khi áp dụng rộng. Nếu bật trực tiếp Reactor hook (`Hooks.enableAutomaticContextPropagation()`), nên bật lúc startup **trước khi tạo subscription mới**, đồng thời đảm bảo dependency `io.micrometer:context-propagation` và accessor phù hợp.

**`contextCapture()`** dùng để chụp các giá trị ThreadLocal được đăng ký ở thời điểm subscription đưa vào Context, khi thật sự cần bắc cầu từ đoạn imperative. Việc chuyển qua một `ExecutorService`, `@Async`, `CompletableFuture` hay callback ngoài Reactor không tự động mang Context qua lại; phải dùng cơ chế propagation/adapter tương ứng hoặc truyền dữ liệu tường minh. Không bật `auto` với kỳ vọng nó chữa tất cả ranh giới bất đồng bộ.

### 10.2. Logging request ID: lựa chọn ưu tiên

Nếu chỉ cần một ID khi ghi log trong một operator reactive, **đọc trực tiếp `ContextView`** rồi dùng ID trong thông điệp log hoặc field structured logging. Nếu bắt buộc phục hồi MDC cho thư viện log cũ, dùng **tracing/observability framework** hoặc cầu nối có accessor và dọn ThreadLocal đúng cách, thay vì tự `MDC.put` trong event-loop rồi giả định thread không đổi.

Một mã ví dụ dùng context trực tiếp, không phụ thuộc MDC:

~~~java
Mono<Void> audited =
    Mono.deferContextual(ctx -> {
        String id = ctx.getOrDefault("demo.requestId", "unknown");
        System.out.println("received requestId=" + id);
        return Mono.empty();
    });
~~~

Code production nên dùng logger thay vì `System.out`, nhưng ý tưởng là **lấy ID từ Context ở thời điểm xử lý**, nên không lệ thuộc tên thread.

## 11. Phạm vi và vòng đời: ranh giới nào làm mất Context?

### 11.1. Đúng: compose publisher, để framework subscribe

~~~java
Mono<String> response =
    repository.findById(id)
        .flatMap(entity -> service.enrich(entity))
        .flatMap(entity -> Mono.deferContextual(ctx ->
            Mono.just("requestId=" + ctx.get("demo.requestId"))));
~~~

Đây là đoạn minh họa; `repository`, `service`, `id` và các kiểu dữ liệu do ứng dụng định nghĩa. Các publisher con được compose bởi `flatMap` thuộc chuỗi reactive, nên có thể đọc Context thích hợp khi subscription diễn ra.

### 11.2. Sai: tự subscribe để "fire and forget"

~~~java
// SAI trong request handler:
auditRepository.save(event).subscribe();
return Mono.just("ok");
~~~

`subscribe()` tạo một subscription độc lập mà caller không kiểm soát completion/error/cancellation; metadata request có thể không truyền đúng, lỗi bị tách khỏi phản hồi, và tác vụ có thể còn chạy sau response. Nếu tác vụ phải nằm trong request, compose và trả publisher:

~~~java
// Ví dụ khi muốn chờ lưu audit trước khi trả body:
return auditRepository.save(event)
        .thenReturn("ok");
~~~

Đối với job thật sự phải tách khỏi request, đẩy sự kiện/metadata cần thiết vào queue hoặc hệ thống xử lý riêng với hợp đồng rõ ràng về trace, retry, idempotency; đừng ngầm dựa vào Context của HTTP request sau khi nó đã kết thúc.

### 11.3. Khi tạo lại Publisher, cache, share hoặc boundary ngoại vi

- **`Mono.defer` không tương đương `Mono.deferContextual`**: loại đầu trì hoãn tạo publisher nhưng không cung cấp ContextView.
- **`cache`/`share`/hot publisher** có thể khiến nhiều subscriber dùng chung kết quả hoặc nguồn đã chạy. Context là metadata theo subscriber, nhưng dữ liệu đã cache/đẩy từ nguồn dùng chung không tự biến thành giá trị riêng cho từng HTTP request. Không cache kết quả phụ thuộc tenant/requestId mà thiếu khóa cache phù hợp.
- **Callback của API ngoài Reactor** không tự đọc được Context trừ khi bạn bọc callback vào publisher và truyền dữ liệu/bridge thích hợp.
- **`CompletableFuture.supplyAsync(...)`** không tự nhận subscriber context. Thay vì cố đọc `ThreadLocal` ở task, hãy chủ động lấy metadata từ Context trong chain rồi truyền làm tham số cho API khác.
- **Thay đổi context trong một nhánh** không có nghĩa các nhánh khác hoặc tất cả operator downstream đều thấy giá trị mới. Quan sát bằng sơ đồ vị trí `contextWrite` và ranh giới publisher.

## 12. Kiểm thử tự động: Context phải đúng dù chuyển scheduler và có nhiều request

### 12.1. Unit test thuần Reactor với StepVerifier

Tệp `src/test/java/demo/context/ReactorContextTest.java` (cần `io.projectreactor:reactor-test` và JUnit 5):

~~~java
package demo.context;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ReactorContextTest {
    private static final String KEY = "demo.requestId";

    @Test
    void keepsRequestIdAfterPublishOn() {
        Mono<String> pipeline = Mono.just("event")
                .publishOn(Schedulers.parallel())
                .flatMap(value -> Mono.deferContextual(ctx ->
                        Mono.just(value + ":" + ctx.get(KEY))))
                .contextWrite(Context.of(KEY, "req-101"));

        StepVerifier.create(pipeline)
                .expectNext("event:req-101")
                .verifyComplete();
    }

    @Test
    void subscriptionsDoNotShareRequestIds() {
        Mono<String> lookup =
                Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)));

        StepVerifier.create(lookup.contextWrite(Context.of(KEY, "A")))
                .expectNext("A")
                .verifyComplete();

        StepVerifier.create(lookup.contextWrite(Context.of(KEY, "B")))
                .expectNext("B")
                .verifyComplete();
    }

    @Test
    void contextWriteMustBeDownstreamFromReader() {
        Mono<String> misplaced = Mono.just("start")
                .contextWrite(ctx -> ctx.put(KEY, "A"))
                .flatMap(ignore -> Mono.deferContextual(ctx ->
                        Mono.just(ctx.getOrDefault(KEY, "missing"))));

        StepVerifier.create(misplaced)
                .expectNext("missing")
                .verifyComplete();
    }
}
~~~

Ba test xác minh ba thuộc tính tách biệt: qua scheduler, biệt lập các subscription và phạm vi `contextWrite`. Chạy với Gradle đã cấu hình JUnit Platform:

~~~bash
./gradlew test --tests demo.context.ReactorContextTest
~~~

Những test này được thiết kế **không dựa vào tên thread** và không cần điều kiện timing, nên ổn định hơn việc đo thời gian sleep.

### 12.2. Integration test Spring WebFlux với WebTestClient

Khi chạy ứng dụng mục 7, tệp `src/test/java/demo/context/ReactiveContextApplicationTest.java`:

~~~java
package demo.context;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveContextApplicationTest {
    @Autowired
    WebTestClient client;

    @Test
    void readsSameRequestIdAfterSchedulerSwitch() {
        client.get().uri("/context")
                .header("X-Request-Id", "req-101")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Request-Id", "req-101")
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-101")
                .jsonPath("$.stage").isEqualTo("after-publishOn");
    }

    @Test
    void eachHttpRequestHasItsOwnId() {
        client.get().uri("/context")
                .header("X-Request-Id", "first")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("first");

        client.get().uri("/context")
                .header("X-Request-Id", "second")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("second");
    }
}
~~~

`RANDOM_PORT` khởi động HTTP server thực tế ở cổng động, còn `WebTestClient` thực hiện request và kiểm tra response. Với test này, chứng minh cả việc filter gắn Context trong vòng đời HTTP, controller đọc sau `publishOn` và request độc lập. Trong test chạy song song, cần bổ sung tình huống concurrency để kiểm tra sự độc lập dưới tải; hai request tuần tự ở đây chứng minh đường đi chính, **không thay thế** kiểm thử tải.

## 13. Các lỗi hay gặp khi tích hợp ứng dụng thật

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh / sửa |
| --- | --- | --- |
| `ctx.get("requestId")` báo thiếu key | Chưa có `contextWrite`, key sai hoặc operator đọc nằm ngoài phạm vi | Dò chuỗi từ vị trí subscribe; đặt `contextWrite` downstream của reader |
| ID mất sau `publishOn` | Thực ra có `subscribe()` thủ công, `ThreadLocal`/MDC bị nhầm là Reactor Context hoặc Context đặt sai | Phân biệt rõ nguồn giá trị; dùng `deferContextual` trong cùng chain |
| ID từ request A xuất hiện trong B | Dùng static mutable field, `ThreadLocal` không cleanup hoặc cache dữ liệu phụ thuộc request | Bỏ biến global; Context theo subscription và kiểm tra cache key |
| Log thiếu correlation ID nhưng `deferContextual` vẫn đọc đúng | MDC/ThreadLocal không được bridge/restore | Dùng logger nhận ID tường minh hoặc observability/context-propagation đã cấu hình |
| Service gọi qua `WebClient` không nhận correlation header | Context chỉ tồn tại **trong JVM/pipeline**, không tự gửi qua HTTP | Đặt outbound header trong WebClient filter/tracing |
| `Mono.block()` làm server chậm hoặc báo lỗi trên event-loop | Gọi blocking trong đường reactive | Trả Mono/Flux, dùng async driver hoặc chuyển công việc blocking đúng scheduler |
| Cùng một key có hai giá trị | `contextWrite` gần reader hơn ghi đè key ở phạm vi upstream | Quy ước ownership/key, tránh ghi đè context của framework |
| Test bình thường nhưng production lỗi khi concurrency cao | Dùng chung mutable state, tự subscribe, bridge ThreadLocal sai | Test đồng thời với ID khác nhau, tracing/log context, điều tra ranh giới ngoại vi |

### Checklist khi code review

1. Dữ liệu đang gắn với **thread**, **exchange** hay **subscription**? Có thể giải thích vòng đời của nó không?
2. Metadata được đặt ở một `WebFilter`, subscriber hoặc boundary đáng tin, có tên key thống nhất không?
3. Mọi service có trả `Mono`/`Flux` để framework compose, tránh `subscribe()`/`block()` ở handler không?
4. `contextWrite` nằm đúng **downstream** so với các operator đọc? Có nhánh con nào tự tạo subscriber riêng không?
5. Có `publishOn`, `subscribeOn`, `CompletableFuture`, `@Async`, `WebClient` hoặc message queue không? Cần bridge tại ranh giới nào?
6. Những giá trị đưa vào Context có đủ nhỏ, không nhạy cảm, không bị log lộ và không mang ý nghĩa xác thực sai không?
7. Test có chứng minh ID giữ nguyên sau scheduler change và không rò sang request khác không?

## 14. Bài tập tự kiểm tra

**Bài 1 — Đọc đúng thứ tự:** Vì sao kết quả sau đây là `missing`?

~~~java
Mono<String> m = Mono.just("x")
    .contextWrite(c -> c.put("id", "A"))
    .flatMap(v -> Mono.deferContextual(c ->
        Mono.just(c.getOrDefault("id", "missing"))));
~~~

**Đáp án:** `flatMap` nằm downstream của `contextWrite`, nên không nhìn thấy Context chỉ cấp cho upstream của operator ghi. Sửa bằng cách chuyển `contextWrite(c -> c.put("id", "A"))` xuống cuối chuỗi sau `flatMap`.

**Bài 2 — Chuyển thread:** Có `publishOn(Schedulers.parallel())` rồi `Mono.deferContextual(...)` trong cùng chain và `contextWrite` ở cuối. ID có mất không? → **Không**, Context đi theo subscriber của chuỗi. Nếu code đang dùng `ThreadLocal` hay MDC, cần quy tắc khác.

**Bài 3 — Hai request đồng thời:** Có nên gắn `currentRequestId` vào một biến `static String` để các service đọc không? → **Không**: mutable shared state sẽ bị request khác ghi đè. Gắn metadata theo Context/subscription hoặc truyền tham số rõ ràng.

**Bài 4 — Outbound WebClient:** Đặt `requestId` trong Reactor Context có khiến service bên ngoài nhận header `X-Request-Id` không? → **Không tự động**; phải dùng filter/header hoặc thư viện tracing đã cấu hình.

**Bài 5 — MDC:** Bật `spring.reactor.context-propagation=auto` có tự động chuyển mọi `ThreadLocal` do ứng dụng tùy ý tạo không? → **Không**; chỉ các giá trị có accessor/bridge phù hợp và trong ranh giới được hỗ trợ. Reactor Context đọc bằng `deferContextual` là cơ chế khác.

## 15. Tài liệu tham khảo chính thức

- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): định nghĩa Context, ContextView, `contextWrite`, `deferContextual` và phạm vi subscriber.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn` và scheduler.
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): cầu nối Reactor Context ↔ ThreadLocal, `contextCapture` và automatic mode.
- [Spring Framework — WebFlux WebClient Context](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html): dữ liệu Context trong chuỗi WebClient/filter.
- [Spring Framework — WebFlux Reactive Spring](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): request xử lý qua `WebHandler`, `WebFilter` và `ServerWebExchange`.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.reactor.context-propagation`.
- [Spring Boot — Observability / Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html): kết hợp Micrometer observability và context propagation.

**Ghi nhớ:** `ThreadLocal` theo **thread**; Reactor `Context` theo **subscriber**; `contextWrite` cấp dữ liệu cho **upstream ở subscription time**, `deferContextual` đọc dữ liệu tại lúc chạy. Vì thế dữ liệu của request có thể theo đúng chuỗi WebFlux khi `publishOn`/`subscribeOn` đổi thread, miễn là bạn giữ composition và truyền thông tin đúng qua mọi boundary.
