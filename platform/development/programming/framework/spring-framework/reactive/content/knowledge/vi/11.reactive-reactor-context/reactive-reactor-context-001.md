# Vì sao ThreadLocal không đủ cho chuỗi đổi luồng

Trong **Spring WebFlux** và **Project Reactor**, dữ liệu gắn với một yêu cầu — chẳng hạn `requestId`, `traceId`, thông tin kiểm toán hoặc ngữ cảnh bảo mật — thường phải đi qua nhiều bước bất đồng bộ. Các bước ấy **không được bảo đảm chạy trên cùng một Java thread**. Vì vậy, lưu dữ liệu vào `ThreadLocal` tại đầu request rồi đọc nó ở mọi bước phía sau là một giả định không an toàn.

**`ThreadLocal` gắn giá trị với thread hiện tại; Reactor `Context` gắn giá trị với subscription và truyền ngữ cảnh theo chuỗi subscriber.** Một subscription có thể chuyển qua nhiều thread mà vẫn truy cập được Context thông qua các API phù hợp. Đây là lý do Reactor cung cấp `Context`, `ContextView`, `contextWrite` và `deferContextual`.

Bài này tập trung vào **tại sao ThreadLocal không đủ khi pipeline đổi luồng**, cách Reactor Context giải quyết và những giới hạn cần hiểu để áp dụng đúng trong WebFlux.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác `ThreadLocal` lưu giá trị ở đâu, vì sao thread pool và event loop làm nó trở nên không đáng tin cho ngữ cảnh request kéo dài.
2. Chỉ ra lúc nào pipeline Reactor có thể đổi thread do `publishOn`, `subscribeOn`, nguồn I/O và callback bất đồng bộ.
3. Hiểu vì sao `Context` gắn với **Subscriber/Subscription**, có phạm vi theo từng lần subscribe và được truyền từ downstream về upstream khi subscription diễn ra.
4. Viết `contextWrite` để thêm dữ liệu, `Mono.deferContextual` hoặc `Flux.deferContextual` để đọc dữ liệu, và dùng `ContextView` đúng cách.
5. Phân biệt `Context` của Reactor với `ThreadLocal`, HTTP headers, `SecurityContextHolder` kiểu imperative và `ApplicationContext` của Spring.
6. Sử dụng ngữ cảnh trong `flatMap`, `publishOn` và WebFlux filter/service mà không dựa vào một thread cố định.
7. Hiểu cách Micrometer Context Propagation có thể hỗ trợ những thư viện cũ phụ thuộc `ThreadLocal`, nhưng không tự động giải quyết mọi ranh giới bất đồng bộ.
8. Kiểm thử sự hiện diện, tính cô lập và phạm vi của Context bằng `StepVerifier`.

## 2. ThreadLocal thực sự hoạt động ra sao?

`ThreadLocal<T>` cho phép cùng một đối tượng `ThreadLocal` trả về **một giá trị riêng cho từng Java thread**:

~~~java
ThreadLocal<String> correlationId = new ThreadLocal<>();

correlationId.set("req-100");
String value = correlationId.get(); // "req-100" trên thread hiện tại.
correlationId.remove();            // Gỡ giá trị khỏi thread hiện tại.
~~~

Cơ chế này hữu ích khi toàn bộ đoạn công việc luôn chạy trên cùng một thread và có điểm bắt đầu/kết thúc rõ ràng. Chẳng hạn một ứng dụng imperative có thể đặt metadata vào `ThreadLocal` trong một filter, chạy logic đồng bộ trên cùng request thread, rồi gọi `remove()` trong `finally`.

**Nhưng `ThreadLocal` không “thuộc về request”**. Nó thuộc về **thread đang thực thi**. Khi thread đó rời request A để xử lý request B, giá trị gắn với A có thể tồn tại nếu không được cleanup đúng. Khi request A chuyển sang thread khác, thread mới không tự thấy giá trị đã đặt trên thread cũ.

Hình dung hai thread và hai request:

~~~text
Thread event-loop-1:
  Request A: ThreadLocal.set("A")
      |
      +-- Bắt đầu công việc bất đồng bộ
      |
      +-- Worker quay về xử lý Request B

Thread worker-2:
  Công việc của Request A tiếp tục
      |
      +-- ThreadLocal.get() => thường là null,
          hoặc giá trị riêng đã được gắn vào worker-2

Thread event-loop-1:
  Sau đó tiếp nhận sự kiện của Request C
      |
      +-- Nếu quên remove(), giá trị "A" có thể còn ở đây
~~~

Đây là **sơ đồ rủi ro**, không phải mọi hệ thống đều sẽ bị rò ngữ cảnh. Nếu thư viện/framework đã thiết lập cơ chế capture/restore/cleanup phù hợp thì `ThreadLocal` có thể được khôi phục tại một số vị trí. Tuy nhiên chỉ dùng `set/get` thủ công **không tạo ra cơ chế đó**.

### Tại sao InheritableThreadLocal cũng không phải giải pháp chung?

`InheritableThreadLocal` hỗ trợ sao chép giá trị khi **tạo child thread**, không có nghĩa nó hiểu các task được đưa vào một thread pool đã chạy từ trước. Event-loop worker và scheduler worker thường được tái sử dụng giữa nhiều request. Vì vậy nó không giải quyết đúng vấn đề scope theo subscription, có thể còn làm tăng nguy cơ ngữ cảnh không đúng nếu áp dụng thiếu kiểm soát.

## 3. Vì sao pipeline Reactor không bị ràng buộc vào một thread?

`Mono` và `Flux` mô tả quá trình phát/biến đổi tín hiệu. Bản thân việc tạo `Mono` hay `Flux` không bắt buộc tạo thread; nhưng publisher nguồn, scheduler và ranh giới bất đồng bộ có thể thay đổi nơi callback được chạy.

Ví dụ:

~~~java
Mono<String> pipeline = Mono.just("start")
    .map(value -> value + "-mapped")
    .publishOn(Schedulers.parallel())
    .map(value -> value + "-processed");
~~~

Đây là **snippet tích hợp**; cần import `reactor.core.publisher.Mono` và `reactor.core.scheduler.Schedulers`. `publishOn` chuyển việc xử lý các tín hiệu phía sau nó sang worker của scheduler được chọn. Nếu code đặt `ThreadLocal.set(...)` trước ranh giới, callback sau `publishOn` thường chạy trên worker khác và không thấy giá trị đã đặt ở thread cũ.

`subscribeOn(scheduler)` lại ảnh hưởng quá trình subscription và cách thực thi source upstream. Ví dụ `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` thường dùng để cô lập lời gọi đồng bộ/blocking khỏi event loop.

Trong WebFlux, ranh giới đổi thread còn có thể đến từ:

- Reactor Netty khi I/O sẵn sàng và tín hiệu được phát trên event-loop worker.
- `publishOn` và `subscribeOn` được ứng dụng hoặc thư viện sử dụng.
- `flatMap` gọi các publisher bất đồng bộ, ví dụ WebClient, database driver hoặc timer.
- `Mono.delay` phát tín hiệu trên scheduler dành cho timer.
- Adapter sang `CompletableFuture`, thư viện callback hoặc executor bên ngoài (cần xét riêng cách nối Context).

**Không nên nghĩ “một request = một thread” hay “một Mono = một thread”.** Cùng request có thể đi qua nhiều thread; cùng thread có thể phục vụ nhiều request khác nhau theo thời gian. Ngay cả khi một lần chạy thử tình cờ dùng cùng thread từ đầu tới cuối, đó không phải là hợp đồng chung của Reactive Streams.

### Một ví dụ về kết quả sai khi phụ thuộc ThreadLocal

~~~text
T0: event-loop-1 -> request A: ThreadLocal.set("trace-A")
T1: event-loop-1 -> subscribe publisher WebClient
T2: event-loop-1 -> tiếp nhận sự kiện request B
T3: worker khác -> callback response của A chạy
T4: worker khác -> ThreadLocal.get() không có "trace-A"
~~~

Một thư viện log dựa trên MDC — thường được cài đặt bằng `ThreadLocal` — cũng có thể in thiếu/mất mã tương quan nếu chưa có cơ chế truyền/khôi phục dữ liệu. Tệ hơn, nếu một thread được tái sử dụng và dữ liệu cũ chưa cleanup, log có thể gắn **sai request ID**.

## 4. Reactor Context: ngữ cảnh đi cùng subscription

Reactor cung cấp hai kiểu quan trọng:

| Kiểu | Vai trò |
| --- | --- |
| `reactor.util.context.Context` | Giao diện ghi/đọc theo key-value; các thao tác `put`, `delete`, `putAll` tạo một Context mới, không sửa trực tiếp bản cũ. |
| `reactor.util.context.ContextView` | Giao diện **chỉ đọc**, dùng để truy xuất các giá trị trong một Context đang hiển thị cho operator. |

Các API phổ biến:

- `Context.of("traceId", "t-1")`: tạo Context có key/value.
- `contextWrite(Context.of(...))` hoặc `contextWrite(ctx -> ctx.put(key, value))`: cung cấp Context mới cho các operator **upstream**.
- `Mono.deferContextual(view -> ...)` / `Flux.deferContextual(view -> ...)`: đọc Context hiện hành **khi subscribe**, rồi tạo publisher phù hợp.
- `view.get(key)`: lấy giá trị, có thể ném `NoSuchElementException` nếu key không tồn tại.
- `view.getOrDefault(key, fallback)` hoặc `view.hasKey(key)`: xử lý key có thể vắng mặt mà không dựa vào exception.

**Context có phạm vi subscription**, không phải một Map global dùng chung cho mọi request. Hai lần subscribe vào cùng một pipeline có thể nhận Context khác nhau. Điều này cho phép xử lý nhiều request đồng thời mà không chia sẻ ngẫu nhiên dữ liệu của nhau.

Reactor Context thường dùng cho thông tin phụ trợ như correlation ID, trace span, security context hoặc transaction context. Dữ liệu nghiệp vụ chính vẫn nên đi qua tín hiệu `onNext` dưới dạng `Mono<Order>`, `Flux<Item>`, DTO... Khi một phương thức phải có dữ liệu để tính toán nghiệp vụ, đừng đặt mọi thứ vào Context chỉ để tránh khai báo tham số.

### Context khác Spring ApplicationContext

- `ApplicationContext` của Spring là container quản lý bean và cấu hình ứng dụng; thường tồn tại lâu hơn một request.
- Reactor `Context` chứa metadata cho subscription, được truy cập qua subscriber chain.
- HTTP request attributes/headers là metadata của HTTP và không tự trở thành Reactor Context nếu ứng dụng/framework không chuyển chúng vào.
- `ThreadLocal` là dữ liệu gắn với thread; tự nó không biết subscription nào đang hoạt động.

Các đối tượng đều có chữ “Context” nhưng **không hoán đổi vai trò cho nhau**.

## 5. Hướng truyền của Context: downstream -> upstream

Một điểm dễ gây nhầm lẫn: **tín hiệu dữ liệu** thường di chuyển từ source qua operator đến subscriber, nhưng **Context được truyền trong quá trình subscription theo hướng từ downstream ngược lên upstream**.

~~~text
Assembly (viết pipeline):
source -> map -> flatMap -> contextWrite -> subscriber

Lúc subscribe:
subscriber -- Context --> contextWrite -- Context mới --> flatMap --> map --> source

Lúc dữ liệu phát:
source -- onNext/onError/onComplete --> map --> flatMap --> subscriber
~~~

`contextWrite` sửa **Context mà các operator upstream nhìn thấy** tại vị trí đặt nó. Nó không phải một lệnh “đặt ThreadLocal cho mọi code phía dưới” và không tự sửa Context của các operator downstream.

Ví dụ:

~~~java
static final String KEY = "demo.traceId";

Mono<String> source = Mono.deferContextual(view -> {
    String trace = view.getOrDefault(KEY, "missing");
    return Mono.just(trace);
});

Mono<String> result = source
    .contextWrite(Context.of(KEY, "trace-17"));
~~~

Khi `result` được subscribe, `source` thấy `trace-17`. `Mono.deferContextual` lấy Context của subscriber khi chạy; việc xây dựng pipeline trước đó **không đọc** được Context theo cách thông thường.

### Nếu nhiều contextWrite cùng đặt một key?

~~~java
Mono<String> source = Mono.deferContextual(view ->
    Mono.just(view.<String>get("demo.key"))
);

Mono<String> result = source
    .contextWrite(ctx -> ctx.put("demo.key", "near-source"))
    .contextWrite(ctx -> ctx.put("demo.key", "near-subscriber"));
~~~

Nguồn thấy `"near-source"` vì thao tác ghi **gần source hơn** được thực hiện khi Context truyền ngược lên và có thể ghi đè giá trị cùng key đã đặt ở phía downstream. Điều này hữu ích để cung cấp cấu hình riêng cho một nhánh, nhưng có thể gây nhầm nếu không vẽ ra vị trí các operator.

**Quy tắc:** xác định operator nào cần đọc Context; đặt `contextWrite` ở phía **downstream của đoạn cần đọc**, và sử dụng key rõ namespace để tránh vô tình đè dữ liệu. Đừng dựa vào thứ tự trực quan của luồng `onNext` để suy ra phạm vi Context.

## 6. Ví dụ Java 17 chạy được: ThreadLocal bị mất, Context vẫn có

Ví dụ độc lập này cố ý dùng `boundedElastic` để bảo đảm `Callable` chạy trên worker khác thread gọi `main`. Không bật Micrometer context-propagation hay hook khôi phục ThreadLocal; vì vậy có thể quan sát trực tiếp sự khác nhau giữa hai cơ chế.

Tạo file `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'ReactorContextDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo `src/main/java/ReactorContextDemo.java`:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {
    static final String CONTEXT_KEY = "demo.requestId";
    static final ThreadLocal<String> LEGACY_REQUEST_ID =
        new ThreadLocal<>();

    public static void main(String[] args) {
        LEGACY_REQUEST_ID.set("req-42");
        try {
            Mono<String> pipeline = Mono.deferContextual(view ->
                Mono.fromCallable(() -> {
                    String fromThreadLocal = LEGACY_REQUEST_ID.get();
                    String fromContext =
                        view.getOrDefault(CONTEXT_KEY, "missing");

                    return "worker ThreadLocal="
                        + (fromThreadLocal == null
                            ? "<missing>" : fromThreadLocal)
                        + "; Reactor Context=" + fromContext;
                }).subscribeOn(Schedulers.boundedElastic())
            ).contextWrite(Context.of(CONTEXT_KEY, "req-42"));

            System.out.println(
                "caller ThreadLocal=" + LEGACY_REQUEST_ID.get()
            );
            System.out.println(
                pipeline.block(Duration.ofSeconds(5))
            );

            Mono<String> shared = Mono.deferContextual(view -> {
                String value =
                    view.getOrDefault(CONTEXT_KEY, "missing");
                return Mono.just(value);
            });

            System.out.println("subscription A="
                + shared.contextWrite(
                    Context.of(CONTEXT_KEY, "A")).block());
            System.out.println("subscription B="
                + shared.contextWrite(
                    Context.of(CONTEXT_KEY, "B")).block());
        } finally {
            LEGACY_REQUEST_ID.remove();
        }
    }
}
~~~

Chạy tại thư mục dự án: `gradle run` (hoặc `./gradlew run` nếu có Gradle Wrapper; trên Windows dùng `gradlew.bat run`). Bốn dòng stdout của **chính chương trình** là:

~~~text
caller ThreadLocal=req-42
worker ThreadLocal=<missing>; Reactor Context=req-42
subscription A=A
subscription B=B
~~~

**Vì sao output này đáng tin?**

1. `LEGACY_REQUEST_ID.set("req-42")` gắn giá trị vào **thread chạy `main`**. Dòng log đầu đọc trên chính thread này nên thấy giá trị.
2. `Mono.deferContextual` đọc `ContextView` của subscription. `contextWrite` ở cuối pipeline đã đặt `demo.requestId = req-42` cho đoạn upstream.
3. `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` thực thi callable trên một worker của `boundedElastic`. `ThreadLocal` thông thường không tự được truyền từ thread `main` sang worker, nên `get()` trả `null`. Ví dụ độc lập không kích hoạt cơ chế tự khôi phục ThreadLocal.
4. `ContextView` đã được Reactor cung cấp theo subscriber chain và có thể được đọc trong callable qua tham chiếu capture hợp lệ. Vì vậy giá trị `req-42` vẫn có mặt dù callable chạy ở thread khác.
5. Hai lần subscribe tiếp theo dùng **cùng một `Mono<String> shared`** nhưng ghi Context khác nhau; kết quả lần lượt là `A`, `B`. Điều này thể hiện tính cô lập theo subscription.
6. `remove()` trong `finally` làm sạch `ThreadLocal` của thread `main`; không thay đổi giá trị Context của các subscription đã dùng.

`block(Duration)` chỉ có mặt trong chương trình console để đợi và in kết quả. **Không sao chép cách gọi `block()` vào WebFlux controller đang chạy trên event loop**. Hãy trả publisher cho framework subscribe.

Trong dự án Spring Boot, nên để **Spring Boot BOM** quản lý phiên bản Reactor tương thích. Ví dụ cố định một phiên bản Reactor chỉ để dự án nhỏ chạy độc lập.

## 7. Đọc Reactor Context sau ranh giới đổi thread

Ví dụ sau dùng `publishOn` trước một `flatMap`. Bên trong inner publisher, `Mono.deferContextual` vẫn đọc được key của subscription:

~~~java
Mono<String> message = Mono.just("start")
    .publishOn(Schedulers.parallel())
    .flatMap(unused -> Mono.deferContextual(view -> {
        String traceId =
            view.getOrDefault("demo.traceId", "missing");
        return Mono.just("trace=" + traceId);
    }))
    .contextWrite(Context.of("demo.traceId", "trace-8"));
~~~

Đây là **snippet Reactor có thể đặt trong một phương thức** với import cho `Mono`, `Schedulers` và `Context`. Khi subscribe và đợi thành công, publisher phát `"trace=trace-8"`. Không có yêu cầu rằng `flatMap` phải chạy trên cùng thread đã tạo `Mono.just("start")`.

**Điều quan trọng:** Context vẫn theo subscription **không phải** vì `publishOn` sao chép mọi biến `ThreadLocal`, mà vì các operator Reactor chuyển metadata của subscriber qua cơ chế Context. Nếu một đoạn code tự tách việc xử lý sang thread hoặc hệ thống callback không dùng subscriber chain của Reactor, cần truyền metadata qua API thích hợp.

Không cần gắn `contextWrite` tại từng operator. Với phạm vi rõ ràng, một vị trí đặt ở downstream của đoạn xử lý cần dùng là đủ. Tuy nhiên nếu lồng pipeline hoặc ghép nhiều subscription riêng biệt, phải kiểm tra Context thực sự thuộc subscription nào.

## 8. Context là bất biến, và giá trị bên trong có thể không phải

`Context` dùng cấu trúc bất biến: các thao tác tạo Context mới, không sửa trực tiếp bản cũ:

~~~java
Context first = Context.of("demo.traceId", "A");
Context second = first.put("demo.traceId", "B");

// first vẫn chứa "A"; second chứa "B".
~~~

Điều này phù hợp khi nhiều phần của pipeline dùng Context mà không cần một Map có thể bị sửa tùy tiện từ thread khác.

Nhưng **đối tượng được lưu làm value không nhất thiết bất biến**. Nếu đặt một `HashMap` có thể thay đổi, một builder hoặc đối tượng có trạng thái chia sẻ vào Context, nhiều callback vẫn có thể tranh chấp hoặc nhìn thấy trạng thái sai.

Nên ưu tiên:

- Giá trị nhỏ, không đổi: trace ID, correlation ID, mã định danh tenant đã xác thực, cấu hình scoped.
- Key có namespace hoặc key type riêng để tránh trùng tên với thư viện khác.
- Dữ liệu bảo mật/nhạy cảm theo đúng boundary đã thiết kế; không tự sao chép toàn bộ headers, token hay payload lớn vào Context.
- Tính toán nghiệp vụ thuần túy dùng tham số hoặc `onNext` thay vì biến Context thành kho state tùy ý.

Ví dụ key có type riêng thay vì chuỗi chung:

~~~java
static final Object REQUEST_ID_KEY = new Object();

Mono<String> action = Mono.deferContextual(view ->
    Mono.just(view.get(REQUEST_ID_KEY))
).contextWrite(Context.of(REQUEST_ID_KEY, "req-42"));
~~~

Đây là snippet tích hợp cần import `Mono` và `Context`. Khi cả bên ghi lẫn bên đọc dùng **cùng một đối tượng key**, nguy cơ trùng key với thư viện khác giảm. Trong thực tế hãy đặt key là một `static final` có thể truy cập nhất quán; không tạo `new Object()` riêng ở hai lớp rồi kỳ vọng chúng khớp.

## 9. Reactor Context không phải “MDC tự chạy đúng”

MDC của SLF4J/Logback thường dựa trên `ThreadLocal`. Vì vậy những lệnh:

~~~java
MDC.put("traceId", "trace-A");
// Một operator chạy bất đồng bộ...
log.info("Đang xử lý");
~~~

không đủ để bảo đảm dòng log được in với đúng `traceId` khi tín hiệu đã đổi thread. Trong hệ thống đa request, còn có nguy cơ một worker tái sử dụng giữ giá trị MDC cũ nếu code quên cleanup.

Các cách áp dụng phù hợp:

1. **Ưu tiên integration observability chính thức** của Spring Boot/Micrometer Tracing và các instrumentation tương thích với Reactor. Kiểm tra version, cấu hình context propagation và các key/accessor được đăng ký thay vì tự giả định MDC luôn được phục hồi.
2. Khi cần tự làm, lấy correlation ID từ Reactor `ContextView` tại điểm xử lý và **đặt/khôi phục/xóa MDC trong phạm vi callback cụ thể**, ví dụ dùng cơ chế scope hoặc `try/finally`. Không đặt một lần rồi để MDC lưu trên worker vô thời hạn.
3. Nếu chỉ cần correlation ID trong bản ghi nghiệp vụ hoặc response, truyền nó thành tham số/DTO thường dễ kiểm thử hơn việc phụ thuộc MDC ẩn.

Ví dụ thiết kế đơn giản, khi không cần MDC:

~~~java
Mono<String> result = Mono.deferContextual(view -> {
    String traceId =
        view.getOrDefault("demo.traceId", "unknown");

    return service.fetch()
        .map(value -> "trace=" + traceId + "; value=" + value);
});
~~~

Đây là **đoạn tích hợp**; `service.fetch()` trả `Mono<String>`. Ở đây trace ID được lấy từ Context và dùng rõ ràng trong logic, không phụ thuộc thread hay logging framework.

**Đừng đưa một `ContextView` vào biến global dùng chung cho request khác**. Lấy đúng context cho subscription hiện tại; dùng dữ liệu cần thiết trong scope đó.

## 10. Micrometer Context Propagation: cầu nối cho ThreadLocal cũ

Từ Reactor Core 3.5+, Reactor hỗ trợ tích hợp với SPI của thư viện `io.micrometer:context-propagation`. Mục đích là giúp kết nối các dạng Context với những thư viện vẫn sử dụng `ThreadLocal` (ví dụ tracing/MDC). Cơ chế này **bổ sung khả năng bridge**, không thay đổi bản chất của `ThreadLocal`.

Các khái niệm:

| Thành phần | Vai trò |
| --- | --- |
| `ThreadLocalAccessor` | Định nghĩa cách đọc/ghi/xóa một `ThreadLocal` cụ thể, gắn với một key. |
| `ContextRegistry` | Đăng ký các accessor để thư viện biết cách chuyển state. |
| `contextCapture()` | Capture những giá trị `ThreadLocal` đã đăng ký tại thời điểm subscription và đưa vào Reactor Context cho phần upstream. |
| `Hooks.enableAutomaticContextPropagation()` | Bật chế độ tự khôi phục `ThreadLocal` từ Reactor Context ở các ranh giới hỗ trợ, áp dụng cho những subscription mới. |
| Chế độ mặc định (limited) | Một số operator như `handle` và `tap` có thể tạo scope khôi phục ThreadLocal khi tích hợp phù hợp đã có mặt. |

**Điều kiện phải rõ:** có đúng thư viện `context-propagation` trên classpath, các `ThreadLocalAccessor` cần thiết đã đăng ký, đúng thời điểm bật hook và đúng phạm vi subscription. Chỉ gọi `Hooks.enableAutomaticContextPropagation()` mà không có accessor tương ứng **không làm mọi `ThreadLocal` tùy ý tự động di chuyển**.

Ví dụ cấu hình minh họa ở điểm khởi động ứng dụng:

~~~java
import reactor.core.publisher.Hooks;

// Chỉ sử dụng khi ứng dụng đã cấu hình Context Propagation
// và các ThreadLocalAccessor cần thiết.
Hooks.enableAutomaticContextPropagation();
~~~

Đoạn trên **không phải chương trình độc lập** và không đề xuất bật hook chỉ để xử lý một biến ThreadLocal tự tạo. Đây là thiết lập **toàn cục**, nên phải được cấu hình theo kiến trúc observability và đo tác động hiệu năng.

### Chế độ mặc định và tự động

Ở chế độ mặc định, không nên giả định bất kỳ callback `map` nào trên thread mới cũng thấy cùng MDC/ThreadLocal. Trong chế độ tự động, Reactor cố gắng khôi phục state đã đăng ký từ Context tại những vị trí thực thi thích hợp, bao gồm khi có chuyển thread; nó cũng cần dọn state đúng scope để tránh rò dữ liệu giữa các subscription.

Tài liệu Reactor khuyến nghị bật hook sớm khi ứng dụng khởi động vì thay đổi này áp dụng cho **subscription được tạo sau đó**. Việc capture ThreadLocal của thread hiện tại vào Context cũng là một bước riêng; tùy chế độ và API subscription (chẳng hạn một số blocking terminal API) có thể có capture tự động. Không suy ra hook tự động capture bất kỳ biến nào tại mọi thời điểm.

**Vẫn ưu tiên thiết kế Reactor Context đúng:** coi Reactor Context là nguồn ngữ cảnh của subscription; dùng bridge khi cần tương thích với thư viện Java/observability dựa trên ThreadLocal. Bridge có chi phí và giới hạn; hãy đo trong môi trường có tải thực.

## 11. Một số ranh giới Context có thể mất hoặc không có sẵn

### 11.1. Tự tạo subscription riêng

~~~java
public Mono<String> wrong() {
    innerService.doWork().subscribe();
    return Mono.just("accepted");
}
~~~

Đây là đoạn tích hợp. Việc gọi `subscribe()` nội bộ tạo một **subscription mới** với lifecycle riêng; tác vụ có thể tiếp tục sau khi caller nhận response, và lỗi/cancellation/ngữ cảnh của caller không tự được truyền theo cách bạn mong đợi.

Thay bằng:

~~~java
public Mono<String> correct() {
    return innerService.doWork()
        .thenReturn("accepted");
}
~~~

Bây giờ caller hoặc WebFlux framework subscribe vào một pipeline duy nhất, nên completion, error, cancel và Reactor Context được ghép theo đúng mô hình. Nếu `innerService.doWork()` đã là một publisher reactive hợp chuẩn, không cần tự `subscribe()` ở mỗi tầng service.

### 11.2. Đi ra Java executor hoặc CompletableFuture thuần

Một task tự đưa vào `ExecutorService.submit` hoặc `CompletableFuture.supplyAsync` có thể chạy trên thread không tham gia subscriber chain. Không thể trong callback thuần đó gọi `Mono.deferContextual` để “đọc Context hiện tại” nếu không có subscription tương ứng.

Hướng giải quyết là **truyền dữ liệu cần thiết qua tham số**, hoặc dùng bridge/context-propagation được cấu hình đúng:

~~~java
Mono<String> result = Mono.deferContextual(view -> {
    String traceId =
        view.getOrDefault("demo.traceId", "missing");

    return Mono.fromFuture(
        java.util.concurrent.CompletableFuture.supplyAsync(
            () -> "processed-" + traceId
        )
    );
});
~~~

Đây là snippet tích hợp minh họa **capture một String từ Reactor Context trước khi gửi công việc sang CompletableFuture**. Phần callback dùng biến `traceId` đã được capture rõ ràng; không dựa vào ThreadLocal. Trong ứng dụng thực, cần dùng executor được quản lý và giới hạn phù hợp. `CompletableFuture.supplyAsync` trên common pool không phải lựa chọn mặc định tốt cho lời gọi I/O blocking có thể kéo dài.

### 11.3. Gửi qua network hoặc message broker

Reactor Context chỉ tồn tại bên trong pipeline của tiến trình/subscription tương ứng. Nó **không tự biến thành HTTP header, Kafka header hay một thông điệp qua mạng**. Nếu muốn trace ID đi qua ranh giới dịch vụ, phải dùng instrumentation tương thích (tracing propagation) hoặc tự ánh xạ dữ liệu sang header/metadata theo hợp đồng.

Tương tự, khi xử lý message nhận từ broker, phải **tái thiết lập ngữ cảnh** cho subscription xử lý message bằng nguồn metadata đã được xác thực. Đừng kỳ vọng Context của tiến trình gửi còn nguyên trong tiến trình nhận.

## 12. Đưa Context vào pipeline WebFlux ở một WebFilter

Trong WebFlux, `WebFilter` có thể gắn correlation ID mới vào Reactor Context cho quá trình xử lý request downstream. Đoạn sau dùng UUID do server tự tạo:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class CorrelationFilter implements WebFilter {
    public static final String TRACE_KEY = "app.traceId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();

        return chain.filter(exchange)
            .contextWrite(ctx -> ctx.put(TRACE_KEY, traceId));
    }
}
~~~

Đây là **đoạn tích hợp vào ứng dụng Spring Boot WebFlux**, không phải chương trình chạy độc lập. Cần dependency `spring-boot-starter-webflux` và cơ chế scan bean phù hợp.

**Giải thích:**

1. WebFilter tạo trace ID riêng cho lần xử lý request.
2. `chain.filter(exchange)` trả `Mono<Void>` đại diện cho quá trình xử lý tiếp theo.
3. `contextWrite` tạo ngữ cảnh cho các subscriber/operator upstream trong chain khi framework subscribe publisher.
4. Controller/service bên trong có thể đọc trace ID qua `Mono.deferContextual` mà không phải giả định đang chạy cùng thread với filter.
5. `Mono<Void>` cho biết chain hoàn tất hoặc lỗi, không phát một giá trị trace ID; Context đóng vai trò metadata đi kèm subscription.

Đoạn này chỉ cho thấy **cơ chế truyền Context**. Nếu muốn trả trace ID qua HTTP header, thêm dữ liệu vào response cần một thao tác riêng trên `ServerHttpResponse`. Nếu muốn gửi trace ID ra dịch vụ khác, phải ánh xạ sang header tại `WebClient` hoặc dùng tracing instrumentation.

### Đọc Context trong service hoặc controller

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CorrelationService {
    public Mono<String> currentTrace() {
        return Mono.deferContextual(view -> {
            String traceId = view.getOrDefault(
                CorrelationFilter.TRACE_KEY, "missing");
            return Mono.just(traceId);
        });
    }
}
~~~

Phương thức `currentTrace()` **không gọi ThreadLocal.get()`. Nó tạo một publisher đọc Context của subscription tại thời điểm chạy. Nếu gọi nó trong chain được bao bởi `CorrelationFilter`, giá trị từ filter có thể tới được service. Nếu service được subscribe độc lập ngoài WebFlux filter, kết quả fallback là `"missing"` theo hợp đồng code.

Một controller có thể:

~~~java
@GetMapping("/debug/correlation")
public Mono<String> correlation() {
    return correlationService.currentTrace();
}
~~~

Đây là snippet controller cần khai báo `correlationService` và các annotation/import WebFlux tương ứng. **Đừng tự gọi `subscribe()` trong controller**; WebFlux framework sẽ subscribe vào giá trị trả về.

## 13. Reactor Context và Spring Security/transaction reactive

Các framework reactive cũng dựa vào ngữ cảnh theo subscriber thay vì chỉ dựa vào thread.

### Spring Security reactive

Trong WebFlux với Spring Security reactive, ngữ cảnh xác thực có thể được truy cập qua:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(securityContext ->
            securityContext.getAuthentication().getName()
        );
~~~

Đây là **đoạn tích hợp**, cần Spring Security reactive đã cấu hình và một `Authentication` hợp lệ. Không đồng nhất nó với `SecurityContextHolder.getContext()` kiểu imperative: khi pipeline đổi thread, một `ThreadLocal` theo thread truyền thống có thể vắng mặt nếu không có bridge thích hợp.

Không nên tự sửa các key Context nội bộ của Spring Security nếu không có API/hợp đồng rõ ràng. Ưu tiên `ReactiveSecurityContextHolder` và các security filter chính thức.

### Spring reactive transaction

Reactive transaction manager của Spring sử dụng ngữ cảnh liên kết với reactive execution thay vì mặc định gắn transaction vào một request thread như cách imperative. Khi dùng `TransactionalOperator` hoặc cấu hình `@Transactional` áp dụng cho reactive method đúng cách, transaction có thể theo pipeline reactive.

Tránh tự gọi `subscribe()` trong service đang dùng transaction reactive: tạo subscription phụ có thể tách khỏi phạm vi transaction dự kiến. Không tự copy hoặc chỉnh transaction context key bằng `contextWrite` nếu không có API chính thức.

**Nguyên lý chung:** context chỉ theo **subscriber chain mà framework quản lý**. Một bước công việc chạy ngoài chain cần một cơ chế nối phạm vi rõ ràng.

## 14. Quan sát và kiểm thử Context trong Reactor

Thay vì chỉ quan sát tên thread, nên kiểm thử **dữ liệu ngữ cảnh được nhìn thấy đúng ở subscription nào**. Ví dụ: cùng một pipeline được dùng bởi hai request thì Context không được lẫn nhau, và đổi scheduler không làm mất key.

Tạo `src/test/java/ReactorContextTest.java` trong dự án ở mục 6:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ReactorContextTest {
    private static final String KEY = "demo.requestId";

    @Test
    void contextSurvivesPublishOn() {
        Mono<String> pipeline = Mono.just("work")
            .publishOn(Schedulers.parallel())
            .flatMap(value ->
                Mono.deferContextual(view -> {
                    String id = view.getOrDefault(KEY, "missing");
                    return Mono.just(id);
                })
            )
            .contextWrite(Context.of(KEY, "req-7"));

        StepVerifier.create(pipeline)
            .expectNext("req-7")
            .verifyComplete();
    }

    @Test
    void twoSubscriptionsHaveIndependentValues() {
        Mono<String> shared = Mono.deferContextual(view -> {
            String id = view.getOrDefault(KEY, "missing");
            return Mono.just(id);
        });

        StepVerifier.create(
                shared.contextWrite(Context.of(KEY, "A")))
            .expectNext("A")
            .verifyComplete();

        StepVerifier.create(
                shared.contextWrite(Context.of(KEY, "B")))
            .expectNext("B")
            .verifyComplete();
    }

    @Test
    void contextWriteClosestToSourceOverridesSameKey() {
        Mono<String> pipeline = Mono.deferContextual(view -> {
            String id = view.getOrDefault(KEY, "missing");
            return Mono.just(id);
        })
        .contextWrite(ctx -> ctx.put(KEY, "near-source"))
        .contextWrite(ctx -> ctx.put(KEY, "near-subscriber"));

        StepVerifier.create(pipeline)
            .expectNext("near-source")
            .verifyComplete();
    }

    @Test
    void missingKeyCanBeHandledExplicitly() {
        Mono<String> pipeline = Mono.deferContextual(view ->
            Mono.just(view.getOrDefault(KEY, "missing"))
        );

        StepVerifier.create(pipeline)
            .expectNext("missing")
            .verifyComplete();
    }
}
~~~

Chạy `gradle test` hoặc lệnh Gradle Wrapper tương ứng. **Bốn test kỳ vọng PASS**:

- `contextSurvivesPublishOn`: Context vẫn đọc được sau khi tín hiệu chuyển scheduler.
- `twoSubscriptionsHaveIndependentValues`: cùng nguồn `shared` nhưng hai lần subscribe nhận A và B độc lập.
- `contextWriteClosestToSourceOverridesSameKey`: vị trí ghi quyết định giá trị operator upstream nhìn thấy.
- `missingKeyCanBeHandledExplicitly`: key không có được xử lý rõ ràng bằng default thay vì ném exception.

**Giới hạn:** các test này xác nhận hành vi Reactor Core, chưa xác nhận integration tracing/MDC, security, transaction hoặc truyền ngữ cảnh qua external executor. Với những integration đó cần test cụ thể cùng dependencies, cấu hình accessor/hook và ranh giới runtime thật.

## 15. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao dễ lỗi | Cách sửa |
| --- | --- | --- |
| `ThreadLocal.set(...)` ở WebFilter rồi đọc `get()` ở mọi bước | Pipeline có thể đổi thread; worker được chia sẻ giữa nhiều request | Dùng Reactor `contextWrite` và `deferContextual` hoặc integration chính thức |
| Dùng `InheritableThreadLocal` để truyền qua thread pool | Chỉ có semantics khi tạo child thread, không theo từng task/subscription | Truyền context per subscription hoặc capture/restore đúng scope |
| Xem `Mono`/`Flux` là tự chạy ở thread mới | Reactive API không tự đảm bảo scheduler | Hiểu nguồn và các operator `publishOn`/`subscribeOn` |
| Đặt `contextWrite` phía upstream của vị trí cần đọc | Context đi từ downstream lên upstream lúc subscribe | Đặt `contextWrite` phía downstream của đoạn cần đọc |
| Gọi `contextWrite` mà tưởng nó mutate một Map global | Context bất biến và theo subscription | Xem `put` là tạo Context mới cho upstream |
| Dùng `view.get(KEY)` với key không chắc tồn tại | Có thể ném `NoSuchElementException` | Dùng `hasKey`/`getOrDefault` hoặc định nghĩa invariant bắt buộc |
| Tạo `new Object()` key khác nhau ở nơi ghi/đọc | Hai key không khớp | Dùng cùng constant/key object đã chia sẻ |
| Đưa mutable object vào Context và sửa từ nhiều worker | Dữ liệu bên trong có thể race dù Context bất biến | Ưu tiên immutable values và scope rõ ràng |
| Tự `subscribe()` trong service hoặc controller | Tạo subscription/lifecycle mới, khó truyền lỗi và ngữ cảnh | Trả publisher đã ghép cho caller/framework subscribe |
| Nghĩ Context tự thành HTTP header hoặc Kafka header | Metadata chỉ tồn tại trong phạm vi reactive subscription | Ánh xạ rõ sang protocol metadata hay dùng tracing instrumentation |
| Nghĩ `Hooks.enableAutomaticContextPropagation()` bảo vệ mọi ThreadLocal | Phụ thuộc thư viện, accessor, mode, thời điểm subscribe và phạm vi đã đăng ký | Cấu hình và test bridge có chủ đích |
| Quên cleanup MDC/ThreadLocal trên worker tái sử dụng | Rò metadata qua request khác | Dùng scope được quản lý và cleanup bằng `finally`/integration |
| Dùng `block()` trong WebFlux handler để lấy Context/data | Có thể chặn hoặc bị từ chối trên non-blocking thread | Giữ xử lý trong `Mono`/`Flux`, trả publisher |
| Chỉ kiểm tra log tên thread mà không kiểm tra trace ID | Thread name không xác nhận đúng giá trị request | Test Context per subscription, quan sát trace/correlation end-to-end |

## 16. Checklist áp dụng vào một ứng dụng WebFlux

Trước khi kết luận hệ thống đã truyền ngữ cảnh đúng, hãy kiểm tra:

1. **Ai tạo metadata?** Từ HTTP header đã validate, tracing instrumentation, security filter hay mã server tạo? Định nghĩa key và giá trị rõ.
2. **Subscription nào sử dụng nó?** Context phải được gắn vào chain mà WebFlux subscribe, không vào một subscription phụ vô tình tạo bằng `subscribe()`.
3. **Có đoạn đổi scheduler không?** Kiểm thử `publishOn`, `subscribeOn`, async I/O và các publisher lồng nhau với cùng correlation ID.
4. **Có ranh giới ngoài Reactor không?** Với callback library, `CompletableFuture`, executor, broker, HTTP, truyền metadata rõ hoặc cấu hình bridge tương thích.
5. **Có dùng MDC/legacy ThreadLocal không?** Kiểm tra Micrometer context-propagation, accessor, restore/cleanup và chi phí runtime; không dựa vào “tự có” nếu chưa test.
6. **Giá trị nhạy cảm hay mutable không?** Giới hạn dữ liệu trong Context, key có namespace, bảo vệ khỏi chia sẻ mutable state và ghi log thiếu kiểm soát.
7. **Có test được hai request song song không?** Dùng trace ID khác nhau và xác minh không lẫn dữ liệu khi worker được tái sử dụng.
8. **Framework có quản lý riêng không?** Spring Security reactive và reactive transaction có API hỗ trợ Context; ưu tiên API chính thức.

**Ghi nhớ:** `ThreadLocal` trả lời câu hỏi **“đang chạy trên thread nào?”**, còn Reactor `Context` giúp trả lời **“subscription nào đang xử lý tín hiệu này?”**. Với chuỗi reactive có thể đổi worker, ngữ cảnh của request phải được quản lý theo subscription và có boundary rõ ràng. ThreadLocal vẫn dùng được trong các scope được phục hồi/cleanup có kiểm soát, nhưng riêng `ThreadLocal.set/get` không đủ để bảo đảm dữ liệu đi đúng qua chuỗi đổi luồng.

## Tài liệu tham khảo

- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Context-Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Project Reactor — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — `Mono` API (`deferContextual`, `contextWrite`): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Security — Reactive Security Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Framework — Programmatic reactive transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
