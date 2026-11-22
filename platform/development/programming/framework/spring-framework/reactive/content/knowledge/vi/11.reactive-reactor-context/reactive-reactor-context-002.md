# `Context` và `ContextView` gắn với subscription trong Project Reactor

## 1. Vì sao Reactor cần Context?

Trong Spring WebFlux, một luồng xử lý phản ứng có thể đi qua nhiều operator, dùng nhiều worker thread và đồng thời phục vụ nhiều HTTP request. Dữ liệu nghiệp vụ như `User` hoặc `Order` nên truyền rõ ràng qua `onNext`, nhưng một số **thông tin phụ trợ** lại cần dùng ở nhiều lớp: mã tương quan (correlation ID), metadata phục vụ tracing, thông tin request không nhạy cảm, ngữ cảnh của thư viện.

Ở lập trình đồng bộ, người ta thường dùng `ThreadLocal`. Cách này dễ sai trong reactive: **một subscription có thể đổi thread, còn một thread có thể phục vụ nhiều subscription**. Reactor cung cấp một cơ chế chuyên biệt:

- **`Context`**: kho key/value **bất biến** (immutable) cho phép tạo phiên bản mới bằng `put`, `delete`, `putAll`.
- **`ContextView`**: giao diện **chỉ đọc**, cho phép xem và trích xuất dữ liệu trong Context.
- **`contextWrite(...)`**: bổ sung hoặc biến đổi Context ở **thời điểm subscription**; tác động đến những operator ở phía **upstream**.
- **`Mono.deferContextual(...)` / `Flux.deferContextual(...)`**: đọc `ContextView` của subscription tại thời điểm cần tạo nguồn.
- **Mỗi subscription có ngữ cảnh riêng**: cùng một publisher có thể được đăng ký nhiều lần với dữ liệu Context khác nhau mà không sửa publisher gốc.

Đây là bài về **phạm vi của ngữ cảnh**, không phải cách lưu một biến global. `Context` không phải bản sao của HTTP session, không phải Java `ThreadLocal`, không được gửi tự động qua mạng, cũng không phải một `Map` có thể sửa tại chỗ.

## 2. Mô hình tư duy: Context đi theo Subscriber, không đi theo Thread

Xét pipeline:

~~~java
Mono<String> greeting = Mono.deferContextual(ctx ->
    Mono.just("Xin chào " + ctx.getOrDefault("user", "khách"))
);

Mono<String> forMai = greeting.contextWrite(
    Context.of("user", "Mai")
);
~~~

Đây là snippet Java (cần import `Mono` và `Context`). Khi chỉ tạo các biến, chưa có subscription nên chưa đọc Context. Khi một subscriber đăng ký vào `forMai`:

~~~text
Assembly:    tạo greeting -------- tạo contextWrite -------- chưa có dữ liệu

Subscription:
  subscriber cuối
          |
          v
    contextWrite("user"="Mai")      <-- tạo Context mới cho upstream
          |
          v
    deferContextual(ctx)           <-- đọc ContextView: user=Mai
          |
          v
    Mono.just("Xin chào Mai")
          |
          v
   subscriber cuối nhận onNext / onComplete
~~~

Context được lưu và truy xuất qua **chuỗi Subscriber**. Khi cần đọc, operator lấy Context từ subscriber nằm **phía downstream** của nó. Vì vậy dữ liệu Context được **đưa lên upstream trong giai đoạn subscription**, trái với tín hiệu `onNext` được phát **từ upstream xuống downstream**.

Có ba hệ quả trọng tâm:

1. Một publisher không có một Context toàn cục cố định; **Context gắn với subscription** (và với các subscriber trong chuỗi operator).
2. `contextWrite` viết bên dưới vị trí đọc sẽ được operator phía trên nhìn thấy. Viết ở phía trên mà đọc ở phía dưới không cho kết quả ngược chiều.
3. Chuyển thread bằng `publishOn` hoặc `subscribeOn` **không tự xóa Context** của một chuỗi Reactor được nối đúng cách. Nó không phụ thuộc vào việc thread trước đó có chứa giá trị `ThreadLocal` nào.

**Cần phân biệt:** Context truyền **metadata** theo subscription, còn phần tử nghiệp vụ được truyền qua `onNext`. Context không phải một kênh phát sự kiện khác.

## 3. API của `Context` và `ContextView`

Cả hai đều chứa các cặp `Object key → Object value`. `Context` **kế thừa** `ContextView`, nên một Context có thể được truyền tới API chỉ nhận ContextView. Ngược lại, một ContextView không có phương thức thay đổi giá trị.

| API | Có trên | Ý nghĩa |
| --- | --- | --- |
| `Context.empty()` | Factory của `Context` | Tạo Context rỗng |
| `Context.of(key, value)` | Factory của `Context` | Tạo Context đã có dữ liệu |
| `put(key, value)` | `Context` | Trả về **Context mới** có key/value được thêm hoặc thay |
| `delete(key)` | `Context` | Trả về **Context mới** bỏ key |
| `putAll(contextView)` | `Context` | Trả Context mới được merge dữ liệu |
| `get(key)` | `ContextView` | Lấy giá trị; nếu thiếu key thì ném `NoSuchElementException` |
| `getOrDefault(key, fallback)` | `ContextView` | Có key thì lấy giá trị, thiếu thì trả fallback |
| `getOrEmpty(key)` | `ContextView` | Trả `Optional<T>` |
| `hasKey(key)` | `ContextView` | Kiểm tra key có tồn tại không |
| `size()`, `stream()` | `ContextView` | Quan sát số cặp và các entry hiện có |

**Tính bất biến (immutable):**

~~~java
Context original = Context.of("traceId", "T-01");
Context updated = original.put("traceId", "T-02");

System.out.println(original.get("traceId")); // T-01
System.out.println(updated.get("traceId"));  // T-02
~~~

`put` **không sửa `original`**; nó trả một đối tượng Context mới. Nếu quên gán kết quả `put` thì phiên bản ban đầu vẫn giữ nguyên:

~~~java
Context ctx = Context.empty();
ctx.put("traceId", "T-01");          // tạo Context mới nhưng không sử dụng
System.out.println(ctx.hasKey("traceId")); // false
~~~

**Key/value:** Không dùng `null` làm key hoặc value trong `Context`. Khi thiếu dữ liệu, chọn `getOrDefault`, `getOrEmpty` hoặc chính sách xử lý lỗi cụ thể. Ưu tiên đặt tên key rõ nghĩa, ví dụ `"app.traceId"`, để giảm va chạm với thư viện khác. Khi cần type-safety, có thể dùng một key object chuyên biệt do ứng dụng quản lý và một record/type rõ ràng làm value.

**Lưu ý về bảo mật:** Context có thể truyền metadata cần thiết cho xử lý nội bộ nhưng không thay thế cơ chế xác thực, phân quyền hoặc kiểm tra trust boundary. Không in toàn bộ Context ra log nếu có token/PII.

## 4. `contextWrite`: ghi ở downstream để upstream đọc

Hai overload thường gặp:

~~~java
Mono<String> a = source.contextWrite(
    Context.of("app.traceId", "T-01")
);

Mono<String> b = source.contextWrite(
    ctx -> ctx.put("app.traceId", "T-01")
);
~~~

Đây là snippet, giả định `source` là `Mono<String>`:

- `contextWrite(ContextView)` merge Context được truyền vào với Context hiện tại của downstream, rồi cho phần **upstream** nhìn thấy Context mới; dữ liệu từ `ContextView` được thêm lên trên, có thể ghi đè giá trị trùng key.
- `contextWrite(Function<Context,Context>)` nhận Context đang có tại thời điểm subscription và trả một Context mới, thường bằng `ctx.put(...)`.
- `contextWrite(...)` **không emit một phần tử dữ liệu**, không tự gọi `subscribe()` và không biến publisher thành hot.
- Context được áp dụng theo **vị trí operator**; không có “put toàn cục cho cả JVM”.

Ví dụ đúng:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("app.traceId"))
).contextWrite(ctx -> ctx.put("app.traceId", "T-01"));
~~~

Một subscriber của `result` nhận `"T-01"`. Do `contextWrite` ở **dưới** `deferContextual`, bước đọc có thể nhìn thấy key.

Ví dụ không nhìn thấy vì đặt `contextWrite` sai phía:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
    Mono.just("upstream=" + ctx.getOrDefault("app.traceId", "-"))
)
.contextWrite(ctx -> ctx.put("app.traceId", "T-01"))
.flatMap(value -> Mono.deferContextual(ctx ->
    Mono.just(value + "; downstream="
        + ctx.getOrDefault("app.traceId", "-"))
));
~~~

Khi subscription bắt đầu trong Context rỗng, output là `upstream=T-01; downstream=-`. Trong `flatMap` **phía sau** `contextWrite`, reader không nhìn thấy Context chỉ được đưa **ngược lên upstream** của đoạn trước.

Nguyên tắc: **đọc gần nguồn, ghi từ phía subscriber**. Hãy vẽ vị trí trong chuỗi thay vì suy đoán Context “đi cùng onNext”.

## 5. Hai lần viết cùng một key: giá trị nào thắng?

Xét:

~~~java
Mono<String> message = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("env"))
)
.contextWrite(ctx -> ctx.put("env", "near"))
.contextWrite(ctx -> ctx.put("env", "far"));
~~~

Subscription bắt đầu từ dưới cùng:

1. `contextWrite(... "far")` tạo Context chứa `env=far`.
2. Khi subscription tiến về nguồn, `contextWrite(... "near")` nhận Context đã có và tạo Context mới chứa `env=near`.
3. `deferContextual` trên cùng đọc `env=near`.

Vì vậy, kết quả là **`near`**, không phải `far`. Khi có nhiều lần ghi cùng key, **giá trị được viết gần reader hơn về phía upstream** là giá trị reader thấy.

Đây không phải race condition hay biến mutable “được sửa lần lượt”: hai operator tạo hai phiên bản Context bất biến, và reader lấy Context do subscriber trực tiếp phía dưới nó cung cấp.

Một trường hợp khác: nếu chỉ dùng `contextWrite(Context.of(...))` để bổ sung key, các key không bị ghi đè có thể vẫn tồn tại trong bản merge. Đừng tạo một Context hoàn toàn mới trong hàm `contextWrite(ctx -> Context.empty().put(...))` trừ khi bạn chủ ý xóa mọi metadata có sẵn của downstream; làm vậy có thể phá context của tracing/security hoặc thư viện khác.

## 6. Chương trình Java 17+ hoàn chỉnh: chứng minh Context gắn với mỗi subscription

Bài này sử dụng Project Reactor Core và Gradle. Ví dụ cố tình in **giá trị Context**, không in tên thread/timing, để output ổn định.

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
}

application {
    mainClass = 'ContextSubscriptionDemo'
}
~~~

Tạo `src/main/java/ContextSubscriptionDemo.java`:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class ContextSubscriptionDemo {
    private static final String USER = "app.user";
    private static final String LABEL = "app.label";

    public static void main(String[] args) {
        Mono<String> greeting = Mono.deferContextual(ctx ->
            Mono.just("hello " + ctx.getOrDefault(USER, "guest"))
        );

        System.out.println("without context=" + greeting.block());

        System.out.println("first=" +
            greeting.contextWrite(Context.of(USER, "Mai")).block());

        System.out.println("second=" +
            greeting.contextWrite(Context.of(USER, "An")).block());

        Mono<String> precedence = Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get(LABEL))
        )
        .contextWrite(ctx -> ctx.put(LABEL, "near"))
        .contextWrite(ctx -> ctx.put(LABEL, "far"));

        System.out.println("precedence=" + precedence.block());

        Mono<String> visibility = Mono.deferContextual(ctx ->
                Mono.just("upstream=" +
                    ctx.getOrDefault(LABEL, "-"))
            )
            .contextWrite(ctx -> ctx.put(LABEL, "inside"))
            .flatMap(text -> Mono.deferContextual(ctx ->
                Mono.just(text + ", downstream=" +
                    ctx.getOrDefault(LABEL, "-"))
            ));

        System.out.println("visibility=" + visibility.block());

        Mono<String> nested = Mono.deferContextual(ctx ->
                Mono.just("outer=" + ctx.get(LABEL))
            )
            .flatMap(text -> Mono.deferContextual(ctx ->
                Mono.just(text + ", inner=" + ctx.get(LABEL))
            ).contextWrite(ctx -> ctx.put(LABEL, "inner-value")))
            .contextWrite(ctx -> ctx.put(LABEL, "outer-value"));

        System.out.println("nested=" + nested.block());
    }
}
~~~

Chạy bằng `gradle run --quiet` hoặc `./gradlew run --quiet` nếu dự án có Gradle Wrapper. Stdout xác định:

~~~text
without context=hello guest
first=hello Mai
second=hello An
precedence=near
visibility=upstream=inside, downstream=-
nested=outer=outer-value, inner=inner-value
~~~

**Điểm cần quan sát:**

- Cùng một `greeting` đã được lắp ráp một lần nhưng hai subscription với `Context.of(USER, "Mai")` và `Context.of(USER, "An")` **đọc hai giá trị khác nhau**.
- Không có `contextWrite` thì `getOrDefault` trả `guest`. Tránh `ctx.get(USER)` nếu key là tùy chọn.
- Hai lần viết cùng key cho `precedence`: reader thấy `near` (gần reader hơn).
- `visibility` chứng minh Context từ `contextWrite` chỉ nhìn thấy upstream.
- `nested` chứng minh Context viết **bên trong inner publisher của `flatMap`** tác động đến inner, trong khi Context ngoài là `outer-value`; việc viết inner không làm đổi giá trị Context của outer.

**`block()` chỉ được dùng trong `main` demo console.** Nó tạo một subscription và chặn thread gọi để đợi kết quả; không dùng `block()` trong controller reactive WebFlux. Mục đích demo là kiểm chứng chính xác ngữ nghĩa Context, không phải khuyến nghị blocking trong ứng dụng.

## 7. Context không gắn với biến publisher và không tự chia sẻ giữa các subscribers

Một số người viết:

~~~java
Mono<String> source = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("id", "missing"))
);
~~~

rồi nghĩ rằng `source` chứa một trường `Context` chung có thể set/get từ bất cứ nơi nào. Điều đó **sai**: `source` là một mô tả pipeline; Context cụ thể được cung cấp theo **subscription downstream**.

~~~java
Mono<String> a = source.contextWrite(Context.of("id", "A"));
Mono<String> b = source.contextWrite(Context.of("id", "B"));
~~~

Nếu `a` và `b` được subscribe, mỗi subscription đọc giá trị do nhánh của nó cung cấp. Ngay cả khi scheduler cùng một thread hoặc hai subscription chạy xen kẽ, Reactor không phải dựa vào `ThreadLocal` để phân biệt A/B.

Đây là lý do Context thích hợp cho **correlation ID của từng request**, nếu mỗi request sinh ra một chuỗi subscription riêng. Cũng là lý do không được cache một ContextView “đọc ở request A” vào biến `static` để dùng ở request B: làm vậy tự phá cô lập metadata.

### Lưu ý về `cache()`, `share()` và hot publisher

Ngữ nghĩa của Context phụ thuộc vào **subscription thực tế**. Các operator như `cache()` hoặc `share()` có thể khiến nhiều downstream subscriber dùng chung một lần upstream subscription hoặc một kết quả đã lưu:

- Với một **cold publisher** thông thường, mỗi downstream subscribe có thể tạo một lượt thực thi upstream riêng.
- Với một publisher đã `cache()`, upstream có thể đã chạy theo Context của **người đăng ký khởi phát cache**; subscriber sau chỉ đọc kết quả cache, không làm upstream tái đọc Context của mình.
- Với hot source phát dữ liệu ngoài vòng đời của một subscriber cụ thể, không thể mặc định rằng producer đang có “Context của subscriber hiện tại”.

Tránh nhét dữ liệu mang tính request/user-specific vào một pipeline **được cache/chia sẻ toàn cục** nếu nó có thể làm lộ kết quả giữa các request. Context không phải cơ chế bảo vệ dữ liệu khi bạn chủ động chia sẻ publisher hay kết quả giữa subscriptions.

## 8. Đọc Context ở nguồn, ở giữa chuỗi và trong `flatMap`

### 8.1. Đọc khi tạo nguồn: `deferContextual`

~~~java
Mono<String> audit = Mono.deferContextual(ctx -> {
    String traceId = ctx.getOrDefault("app.traceId", "unknown");
    return Mono.just("trace=" + traceId);
});
~~~

Đây là snippet. `deferContextual` chỉ gọi factory khi có subscription, và cấp một `ContextView` phù hợp với subscription tại vị trí ấy. Có thể dùng `Flux.deferContextual(...)` khi cần trả một `Flux<T>`.

### 8.2. Đọc giữa chuỗi: `transformDeferredContextual`

Khi có một `Flux<T>` đã tạo và cần đọc metadata phục vụ việc dựng một nhánh biến đổi tại thời điểm subscription:

~~~java
Flux<String> output = Flux.just("a", "b")
    .transformDeferredContextual((source, ctx) -> {
        String prefix = ctx.getOrDefault("app.prefix", "x");
        return source.map(value -> prefix + ":" + value);
    })
    .contextWrite(Context.of("app.prefix", "trace"));
~~~

Đây là snippet, cần import `Flux` và `Context`. Khi subscribe, output là `trace:a` rồi `trace:b`. `transformDeferredContextual` nhận cả publisher hiện tại và ContextView, cho phép chọn biến đổi theo metadata của subscription. Khác với `transform` thông thường chạy việc dựng phép biến đổi khi assembly, phiên bản `DeferredContextual` lấy Context tại thời điểm subscribe.

### 8.3. Đọc bên trong `flatMap`

~~~java
Mono<String> output = Mono.just("data")
    .flatMap(data -> Mono.deferContextual(ctx -> {
        String trace = ctx.getOrDefault("app.traceId", "missing");
        return Mono.just(data + ":" + trace);
    }))
    .contextWrite(Context.of("app.traceId", "T-01"));
~~~

Khi subscribe, output là `data:T-01`. Vì inner publisher được ghép vào chuỗi Reactor tại thời điểm subscription, `deferContextual` trong inner có thể đọc Context được truyền vào nhánh ấy.

**Quan trọng:** Ghi Context trong **một inner publisher** chỉ làm thay đổi ngữ cảnh nhìn thấy **bên trong inner publisher đó**, không “đẩy” ngược ngữ cảnh ra ngoài để các operator ngang hàng hoặc outer pipeline tự thấy. Bài demo ở mục 6 có output `nested=...` thể hiện chính xác điều này.

## 9. Bản chất read-only của `ContextView`

Khi một thư viện cần biết correlation ID để thêm HTTP header hoặc enrich log, thư viện thường **chỉ nên đọc** metadata. API của thư viện có thể nhận `ContextView` thay vì `Context` để không gợi ý rằng nó được phép sửa ngữ cảnh.

~~~java
static String describe(reactor.util.context.ContextView view) {
    return view.getOrDefault("app.traceId", "no-trace");
}
~~~

Đây là method snippet. `ContextView` **không có `put`, `delete`**. Nếu cần biến đổi Context cho upstream, hãy làm rõ tại vị trí `contextWrite`; không cố ép `ContextView` thành `Map` mutable.

Về ý nghĩa:

- `Context` là khả năng tạo ra một **phiên bản dữ liệu ngữ cảnh mới**.
- `ContextView` là khả năng **quan sát** dữ liệu ngữ cảnh hiện tại.
- Bản thân object Context bất biến; tuy nhiên **value bên trong có thể là object mutable**. Nếu lưu một `ArrayList`/`HashMap` rồi sửa object ấy, bạn có thể tạo ra chia sẻ trạng thái không an toàn. Ưu tiên `String`, number, record/immutable value; nếu buộc dùng object mutable, phải tự thiết kế thread safety và lifetime.

Không dựa vào generic cast của `ctx.get("key")` mà không kiểm tra contract của thư viện: các key/value có type `Object`, đặt nhầm loại value có thể dẫn tới `ClassCastException` ở nơi sử dụng. Khi viết thư viện, sử dụng key được định nghĩa nhất quán và loại value rõ ràng.

## 10. `ThreadLocal`, MDC và chuyển Scheduler

So sánh:

| Đặc điểm | `ThreadLocal` | Reactor `Context` |
| --- | --- | --- |
| Phạm vi | Thread hiện tại | Subscriber/subscription ở chuỗi Reactor |
| Khi đổi thread | Không tự mang dữ liệu sang thread mới | Context vẫn có thể truy xuất qua subscriber ở các operator Reactor |
| Khi thread tái sử dụng | Dễ còn dữ liệu cũ nếu quên cleanup | Context của subscription khác được thiết lập riêng |
| Khi đọc | `threadLocal.get()` | `deferContextual(ctx -> ...)` hoặc API đọc Context |
| Khi ghi | `threadLocal.set(...)`, mutate state | `contextWrite(ctx -> ctx.put(...))` tạo Context mới |
| Use case | Thư viện đồng bộ theo thread | Correlation/tracing metadata trong chain Reactor |

Một ví dụ chứng minh chuyển worker không phá Context:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("app.traceId", "none"))
    )
    .publishOn(Schedulers.parallel())
    .map(trace -> "trace=" + trace)
    .contextWrite(Context.of("app.traceId", "T-01"));
~~~

Đây là snippet (import `Mono`, `Schedulers`, `Context`). Khi subscriber chờ hoàn tất, output là `trace=T-01` dù có `publishOn` trong chain. Nhưng **không suy ra `ThreadLocal` sẽ tự mang T-01 sang worker mới**.

**MDC logging:** Nhiều logging framework dùng `ThreadLocal` cho MDC. Gọi `MDC.put(...)` trong một operator rồi tin rằng mọi operator sau sẽ nhìn thấy trên mọi thread là sai. Cách tiếp cận đúng phụ thuộc phiên bản Reactor/Micrometer context-propagation và chế độ cấu hình:

- Có thể dùng thông tin trong Reactor Context để thêm correlation ID ở đúng vị trí log hoặc dựng một bridge có cleanup.
- Reactor có cơ chế **context-propagation tích hợp** khi cài đặt/cấu hình thích hợp. Chế độ mặc định và chế độ tự động có hành vi khác nhau; không được giả định rằng thêm `contextWrite` luôn tự động đồng bộ toàn bộ MDC.
- Nếu chuyển dữ liệu từ `ThreadLocal` vào Reactor Context, thời điểm capture, operator sử dụng và lifecycle đều quan trọng. Luôn xác minh cơ chế bằng test khi dùng thư viện tracing/observability cụ thể.

Chìa khóa: **Context là mô hình dữ liệu theo subscription**; context-propagation cho `ThreadLocal` là một cơ chế tích hợp khác, có thể được bật hoặc không.

## 11. Ứng dụng Spring WebFlux: truyền correlation ID đến service

Giả sử một HTTP handler lấy header `X-Correlation-ID` sau khi đã xác thực/kiểm tra hoặc tạo ID mới đáng tin cậy. Service có thể đọc ID từ Context mà không cần thêm tham số `traceId` vào mọi method.

**Đoạn code controller minh họa** (không phải chương trình standalone; cần Spring WebFlux, bean service và import):

~~~java
@RestController
class GreetingController {
    private final GreetingService service;

    GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greeting")
    Mono<String> greeting(ServerHttpRequest request) {
        String id = request.getHeaders()
            .getFirst("X-Correlation-ID");

        // Trong thực tế: validate/sanitize hoặc tự phát sinh ID đáng tin cậy.
        String correlationId = (id == null || id.isBlank())
            ? "generated-by-server"
            : id;

        return service.greeting()
            .contextWrite(ctx ->
                ctx.put("app.correlationId", correlationId)
            );
    }
}

@Service
class GreetingService {
    Mono<String> greeting() {
        return Mono.deferContextual(ctx -> {
            String id = ctx.getOrDefault(
                "app.correlationId", "unknown"
            );
            return Mono.just("correlationId=" + id);
        });
    }
}
~~~

**Các lớp/import**: `org.springframework.web.bind.annotation.RestController`, `GetMapping`, `org.springframework.http.server.reactive.ServerHttpRequest`, `org.springframework.stereotype.Service`, `reactor.core.publisher.Mono`. Ví dụ này chỉ minh họa Context propagation; production không nên tin header client chưa kiểm tra, và không nên dùng chuỗi hằng `generated-by-server` làm ID thật. Có thể dùng request ID sinh tại server, đồng thời áp chính sách độ dài/ký tự trước khi đưa header vào logging.

**Vì sao đặt `contextWrite` trên publisher trả về?** Spring WebFlux subscribe vào `Mono` ở đoạn cuối; subscription đi ngược qua `contextWrite` rồi đến `service.greeting()`, nơi `deferContextual` lấy được correlation ID. Không có một biến global/context tĩnh nào lưu ID của các request khác nhau.

Điều Context **không tự làm**:

- Không tự động gửi `app.correlationId` tới microservice khác qua WebClient; bạn cần thêm header hoặc chọn hệ thống tracing chuẩn có hỗ trợ propagation.
- Không biến giá trị từ HTTP header thành thông tin đáng tin cậy.
- Không tự động đồng bộ mọi `ThreadLocal`/MDC khi chưa có cầu nối và cấu hình thích hợp.
- Không thay thế cách lưu security context chuẩn của Spring Security. Reactive security sử dụng cơ chế riêng (ví dụ `ReactiveSecurityContextHolder`), nên thư viện không được tự giả định key hay tự tạo quyền truy cập từ một chuỗi Context do client cung cấp.

Nếu cần liên hệ ID với một outbound WebClient, có thể đọc Context tại thời điểm xây request trong một lớp thích hợp và map nó thành HTTP header theo hợp đồng hệ thống. Đó là một bước truyền metadata **qua ranh giới mạng**, không phải một đặc tính tự động của Reactor Context.

## 12. Context trong một thư viện dùng chung

Một lợi ích quan trọng là thư viện ở upstream có thể đọc metadata mà ứng dụng downstream thêm vào **khi subscribe**. Ví dụ service hiện thực một publisher đọc trace ID:

~~~java
public Mono<String> callLibraryOperation(String payload) {
    return Mono.deferContextual(ctx -> {
        String trace = ctx.getOrDefault(
            "app.traceId", "not-provided"
        );
        return Mono.just("payload=" + payload + ", trace=" + trace);
    });
}
~~~

Đây là snippet: method có thể sống trong thư viện. Caller không phải thay chữ ký method để truyền thêm ID:

~~~java
Mono<String> output = callLibraryOperation("hello")
    .contextWrite(Context.of("app.traceId", "T-42"));
~~~

Khi subscribe, thư viện đọc `T-42`. Cách này hữu ích cho logging/tracing/correlation, nhưng không nên lạm dụng để giấu các dependency nghiệp vụ bắt buộc: nếu một phương thức **cần** `userId` để tính kết quả và validate quyền truy cập, hãy cân nhắc truyền một đối tượng request/context nghiệp vụ rõ ràng thay vì giấu mọi thứ trong Reactor Context.

Khi viết thư viện:

1. Định nghĩa key có namespace và kiểu value rõ ràng.
2. Với metadata tùy chọn, dùng `getOrDefault`/`getOrEmpty`, không ném lỗi ngoài ý muốn chỉ vì key vắng mặt.
3. Nếu metadata bắt buộc, nêu rõ yêu cầu trong contract; xử lý thiếu key có chủ đích.
4. Tránh ghi đè những key framework đã định nghĩa.
5. Không dùng Context như nơi chứa tập dữ liệu lớn hoặc một cache nghiệp vụ.

## 13. Context ở `flatMap`, luồng con và ranh giới composition

Một pipeline có thể tạo **inner publisher**:

~~~java
Mono<String> chain = Mono.just("data")
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + ":" + ctx.get("k"))
        ).contextWrite(ctx -> ctx.put("k", "inner"))
    )
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + ":" + ctx.getOrDefault("k", "outer-default"))
        )
    )
    .contextWrite(ctx -> ctx.put("k", "outer"));
~~~

Khi subscribe, kết quả là **`data:inner:outer`**:

- Inner thứ nhất được thêm một Context local với `k=inner`.
- Context local đó chỉ tồn tại ở bên trong inner thứ nhất; không sửa outer.
- Inner thứ hai vẫn đọc `k=outer` từ Context của chuỗi bên ngoài.

Cần rất thận trọng với code dạng `flatMap(value -> ...)` và một loạt `contextWrite`: Context không vận chuyển theo giá trị `value`. Nó được truy vấn qua subscriber tại vị trí của inner/outer publisher, nên dùng Context để “đánh dấu” kết quả phần tử rồi mong operator ngang hàng nhận được dấu đó là sai mô hình.

Nếu metadata phải **đi theo chính từng phần tử**, ví dụ mỗi record có tenant khác nhau, tốt hơn là đưa metadata vào một kiểu dữ liệu rõ ràng như `record Envelope<T>(T value, TenantId tenantId)`, hoặc dùng cơ chế xử lý theo từng phần tử có key rõ. Context phù hợp với metadata **của subscription**, không phải thay cho metadata khác nhau trên mỗi item.

## 14. Retry, cancellation và Context

Với cold publisher:

~~~java
Mono<String> operation = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("app.traceId", "missing"))
);

Mono<String> retried = operation
    .retry(2)
    .contextWrite(Context.of("app.traceId", "T-01"));
~~~

Đây là snippet. Nếu `operation` lỗi, `retry(2)` có thể đăng ký lại vào phần upstream và Context của subscriber trong chuỗi phù hợp vẫn có thể được truy xuất khi xây subscription mới. Context **không phải nơi giữ bộ đếm retry mutable**, và `retry` không bảo đảm exactly-once cho side effect. Nếu cần thay đổi trạng thái qua attempts, phải dùng cách quản lý trạng thái chính xác và được giới hạn, không mutate một value trong Context một cách thiếu kiểm soát.

Khi một subscription bị hủy, thông tin Context gắn với nó không có vòng đời “biến global còn tồn tại để subscriber khác dùng”. Một lần subscribe mới sẽ có ngữ cảnh của lần subscribe mới. Việc nhà phát hành/hệ thống quản lý tài nguyên giải phóng bộ nhớ phụ thuộc reference/lifecycle bình thường của Java; không nên coi Context là bộ nhớ request bất tử hoặc session store.

**Quan hệ với `contextCapture`:** Trong một số tích hợp context-propagation, operator có thể capture các giá trị `ThreadLocal` đã đăng ký với cơ chế tương ứng vào Reactor Context tại subscription. Đây là công cụ tích hợp riêng, không phải cùng một thứ với `ContextView` hay lý do để ngầm kỳ vọng mọi ThreadLocal tự xuất hiện trong Context.

## 15. Kiểm thử bằng JUnit 5 và StepVerifier

Hãy kiểm tra **kết quả quan sát theo subscription**, không dựa vào tên thread hoặc tốc độ xử lý. Giữ dự án Gradle ở mục 6; thay khối `dependencies` bằng:

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
    testImplementation 'io.projectreactor:reactor-test:3.8.6'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Tạo `src/test/java/ContextSubscriptionTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

class ContextSubscriptionTest {
    @Test
    void twoSubscriptionsDoNotShareContext() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("app.user", "guest"))
        );

        StepVerifier.create(
                source.contextWrite(Context.of("app.user", "Mai"))
            )
            .expectNext("Mai")
            .verifyComplete();

        StepVerifier.create(
                source.contextWrite(Context.of("app.user", "An"))
            )
            .expectNext("An")
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext("guest")
            .verifyComplete();
    }

    @Test
    void lastWriteTowardUpstreamWinsForSameKey() {
        Mono<String> source = Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get("app.flag"))
            )
            .contextWrite(ctx -> ctx.put("app.flag", "near"))
            .contextWrite(ctx -> ctx.put("app.flag", "far"));

        StepVerifier.create(source)
            .expectNext("near")
            .verifyComplete();
    }

    @Test
    void testCanSupplyInitialSubscriberContext() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("app.traceId", "missing"))
        );

        StepVerifier.create(
                source,
                StepVerifierOptions.create()
                    .withInitialContext(Context.of("app.traceId", "T-100"))
            )
            .expectNext("T-100")
            .verifyComplete();
    }

    @Test
    void putCreatesNewImmutableContext() {
        Context original = Context.empty();
        Context updated = original.put("app.user", "Mai");

        assertFalse(original.hasKey("app.user"));
        assertEquals("Mai", updated.get("app.user"));
    }

    @Test
    void innerContextDoesNotReplaceOuter() {
        Mono<String> source = Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get("k"))
            )
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(value + ":" + ctx.<String>get("k"))
            ).contextWrite(ctx -> ctx.put("k", "inner")))
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(value + ":" + ctx.<String>get("k"))
            ))
            .contextWrite(ctx -> ctx.put("k", "outer"));

        StepVerifier.create(source)
            .expectNext("outer:inner:outer")
            .verifyComplete();
    }
}
~~~

Chạy `gradle test` hoặc `./gradlew test`. Kỳ vọng **cả năm test PASS**. Chúng xác minh cô lập subscription, thứ tự `contextWrite`, cách nạp Context ban đầu cho subscriber bằng `StepVerifierOptions`, tính bất biến, và phạm vi của contextWrite bên trong `flatMap`.

**Vì sao dùng `StepVerifierOptions.withInitialContext`?** Trong ứng dụng thực, subscriber/framework có thể cung cấp Context đầu tiên. Khi kiểm thử một library publisher, ta có thể mô phỏng việc đó **mà không buộc thư viện phải tự `contextWrite` cho mình**. Cách này kiểm tra đúng contract theo subscription, thay vì truyền Context qua một biến static.

## 16. Giới hạn hiệu năng và kiến trúc

Context được thiết kế cho **số lượng nhỏ** các cặp key/value. Đây không phải kho dữ liệu lớn:

- Không lưu một `List<Event>` gồm hàng triệu phần tử vào Context.
- Không xem Context là bộ nhớ chia sẻ mutable xuyên request.
- Không dùng Context làm global cache/session/database.
- Mỗi `put` tạo một phiên bản Context mới; với nhiều key, việc copy-on-write có thể tăng overhead.
- Không dùng một key chung như `"id"` giữa nhiều thư viện nếu có thể va chạm; đặt tên namespace hoặc key object chuyên biệt.
- Không đưa token/secret ra log bằng cách dump toàn Context.
- Không giả định Context luôn hiện diện trong callback bên ngoài Reactor; khi vượt ranh giới sang thư viện imperative, cần một cơ chế truyền metadata rõ ràng.

Context chỉ nên gánh những metadata **độc lập với dữ liệu nghiệp vụ** và được các thành phần upstream cần khi thực thi subscription. Với nghiệp vụ cần truyền bắt buộc, minh bạch, qua nhiều hệ thống, hãy ưu tiên tham số method, record hoặc header/protocol rõ ràng.

## 17. Những lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| “Context thuộc một thread” | Reactor gắn Context với subscriber/subscription; thread có thể đổi | Dùng `deferContextual`/`contextWrite` |
| “`Context.put` sửa object cũ” | Context immutable; `put` trả Context mới | Dùng giá trị trả về, ví dụ `ctx -> ctx.put(...)` |
| “`ContextView` có thể `put`” | Chỉ có API đọc | Viết trong `contextWrite` |
| “`contextWrite` truyền theo `onNext` xuống dưới” | Context đi ngược hướng subscription, không đi như data | Đặt `contextWrite` downstream của reader |
| “Reader phía dưới nhìn thấy mọi contextWrite phía trên” | Scope phụ thuộc vị trí operator | Vẽ chuỗi và kiểm thử giá trị mong đợi |
| “Một publisher chỉ có một Context toàn cục” | Nhiều subscriptions có thể có Context khác nhau | Test hai subscriptions cùng một source |
| “Đổi scheduler làm Context biến mất” | Reactor Context không phụ thuộc thread cụ thể | Đọc qua `ContextView` trong chain |
| “Có Context thì MDC tự động đầy đủ” | MDC là ThreadLocal, cần tích hợp/cấu hình propagation riêng | Xác minh Micrometer/Reactor bridge |
| “Thêm inner contextWrite sẽ đổi outer context” | Context trong inner publisher có phạm vi cục bộ | Truyền dữ liệu qua item nếu cần đổi outer logic |
| “`get("key")` luôn an toàn” | Key có thể thiếu, ném exception | `getOrDefault`/`getOrEmpty` nếu tùy chọn |
| “Có Context là mọi HTTP client tự gửi ID đi” | Context chỉ tồn tại ở chain Reactor | Map metadata thành headers/protocol theo chủ đích |
| “Value trong Context luôn immutable” | Context immutable nhưng value có thể mutable | Lưu immutable value, tránh trạng thái chia sẻ |
| “Dùng Context để xác thực user theo header tùy ý” | Metadata từ request chưa chắc đáng tin cậy | Dùng Spring Security và nguồn xác thực đáng tin |
| “Publisher cache toàn cục có Context riêng cho từng user” | Cached upstream có thể chạy một lần theo Context đầu | Không cache lẫn dữ liệu request-specific |

## 18. Câu hỏi tự kiểm tra kèm đáp án

**Câu 1.** Vì sao `ThreadLocal` kém phù hợp cho correlation ID trong một pipeline WebFlux có `publishOn`?

**Đáp án:** `ThreadLocal` gắn với thread, trong khi pipeline có thể chuyển worker. Reactor Context gắn với subscriber/subscription và có thể được truy xuất ở các operator Reactor xuyên qua chuyển thread.

**Câu 2.** Sau `Context a = Context.empty(); a.put("k","v");`, `a.hasKey("k")` trả gì?

**Đáp án:** `false`. `put` trả Context mới; nếu bỏ giá trị trả về, `a` vẫn là Context rỗng.

**Câu 3.** Vì sao `Mono.deferContextual(ctx -> Mono.just(ctx.get("k"))).contextWrite(Context.of("k","v"))` đọc được v?

**Đáp án:** `contextWrite` được áp dụng khi subscription truyền từ downstream về upstream và đưa giá trị `k=v` cho `deferContextual` ở trên.

**Câu 4.** Nếu `contextWrite` được đặt phía upstream của reader downstream, reader có luôn thấy key không?

**Đáp án:** Không. Context không tự trôi cùng `onNext`; reader downstream có thể không nhìn thấy Context chỉ được ghi cho upstream.

**Câu 5.** Hai subscriptions cùng một `Mono.deferContextual` nhưng `contextWrite` khác nhau có bắt buộc thấy cùng giá trị?

**Đáp án:** Không. Mỗi subscription có thể đọc giá trị riêng; đó là một mục đích chính của Context.

**Câu 6.** Vì sao `ContextView` không có `put`?

**Đáp án:** Nó là API chỉ đọc cho code tiêu thụ ngữ cảnh; sửa ngữ cảnh phải là một phép biến đổi có phạm vi rõ ràng qua `Context`/`contextWrite`.

**Câu 7.** `contextWrite(ctx -> ctx.put("k","inner"))` nằm trong inner của `flatMap` có đổi Context của inner `flatMap` khác không?

**Đáp án:** Không theo mô hình phạm vi bình thường. Context local chỉ tác động upstream của inner ấy; outer/inner ngang hàng không nhận một phép mutate global.

**Câu 8.** Một `Mono` chứa dữ liệu cá nhân được `cache()` toàn cục nhưng nguồn đọc Context của subscriber đầu. Các subscriber sau có chắc nhận dữ liệu riêng không?

**Đáp án:** Không. Cache có thể chia sẻ kết quả thực thi đầu tiên. Không trộn dữ liệu user-specific với publisher/cache dùng chung giữa các request.

**Câu 9.** Trong Spring WebFlux, muốn gửi correlation ID tới HTTP service bên ngoài, chỉ `contextWrite("id")` có đủ không?

**Đáp án:** Không. Context là metadata của subscription Reactor; cần thiết kế bước thêm HTTP header hoặc dùng cơ chế tracing propagation chuẩn đã cấu hình.

**Câu 10.** Khi test một thư viện đọc `ContextView` nhưng không tự viết Context, cách mô phỏng subscriber có sẵn key là gì?

**Đáp án:** Dùng `StepVerifierOptions.create().withInitialContext(Context.of(...))` hoặc bọc nguồn bằng `contextWrite` ở phía caller, rồi assert tín hiệu từ publisher.

## 19. Tổng kết và tài liệu chính thức

**Năm quy tắc cần nhớ:**

1. **Context gắn với subscription/subscriber, không phải thread hay một object publisher toàn cục.**
2. **`Context` bất biến và có phương thức tạo bản mới; `ContextView` chỉ đọc.**
3. **`contextWrite` đi từ downstream lên upstream trong lúc subscription**, vì vậy vị trí ghi/đọc quyết định khả năng nhìn thấy giá trị.
4. **`deferContextual`/`transformDeferredContextual` đọc Context tại đúng thời điểm subscription**, kể cả khi các bước xử lý được đổi worker.
5. **Context chỉ dùng cho metadata nhỏ, có phạm vi rõ ràng**; không thay thế thông tin nghiệp vụ, cơ chế bảo mật, truyền qua mạng hay state store.

Tài liệu chuẩn:

1. [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): `Context`/`ContextView`, subscription scope, thứ tự `contextWrite`, `flatMap` và ví dụ tracing.
2. [Reactor Context API](https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html): contract bất biến, `put`, `delete`, `Context.of`.
3. [Reactor ContextView API](https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html): `get`, `getOrDefault`, `getOrEmpty`, `hasKey`.
4. [Reactor Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `deferContextual`, `contextWrite`, `transformDeferredContextual`.
5. [Reactor Reference — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): tích hợp `ThreadLocal`/Micrometer và các chế độ propagation.
6. [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): mô hình lập trình không chặn trong Spring.
