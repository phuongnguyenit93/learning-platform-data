# Reactor Context và sự khác biệt với ThreadLocal

## Mục tiêu học tập

Sau bài học, bạn có thể:
- Giải thích vì sao dữ liệu gắn với luồng xử lý (như mã truy vết, tenant, thông tin xác thực) không nên dựa mặc định vào `ThreadLocal` trong ứng dụng reactive.
- Mô tả `reactor.util.context.Context`, `ContextView`, phạm vi theo `Subscriber` và hướng truyền context khi subscribe.
- Sử dụng `contextWrite(...)`, `deferContextual(...)` và đọc đúng phạm vi context, kể cả khi đổi scheduler hoặc có `flatMap`.
- Liên hệ Reactor Context với `ReactiveSecurityContextHolder` của Spring Security WebFlux; nhận diện khi nào cần cầu nối với thư viện dùng `ThreadLocal`.

## 1. Bài toán: một request không đồng nghĩa với một thread

Trong chương trình đồng bộ kiểu servlet, cùng một luồng thường xử lý một đoạn request từ đầu đến cuối. Lập trình viên có thể đặt `requestId` vào `ThreadLocal`, sau đó lấy lại ở tầng service mà không truyền tham số qua mọi hàm. Tuy nhiên, cách làm này gắn dữ liệu với **thread vật lý**, không gắn với **request logic**.

Trong Reactor, một `Mono` hoặc `Flux` có thể thực thi trên nhiều thread do `publishOn`, `subscribeOn`, nguồn bất đồng bộ hoặc các thao tác I/O. Đồng thời, một thread trong event loop có thể phục vụ nhiều subscription khác nhau theo thời gian. Vì vậy:

- Đặt giá trị vào `ThreadLocal` tại thread A không bảo đảm callback tại thread B đọc được giá trị đó.
- Nếu dùng thread pool và quên `remove()`, một tác vụ về sau trên cùng thread có thể nhìn thấy trạng thái cũ.
- Kể cả khi các bước tình cờ chạy trên cùng thread, điều đó không phải hợp đồng bảo đảm tính đúng đắn của pipeline.

Reactor Context giải bài toán truyền **metadata gắn với luồng xử lý reactive** mà không cần nhét nó vào dữ liệu nghiệp vụ `T` của `Mono<T>`/`Flux<T>`.

## 2. Reactor Context thực chất là gì?

`reactor.util.context.Context` là cấu trúc ánh xạ **key → value** bất biến ở cấp cấu trúc (immutable map). `ContextView` là giao diện chỉ đọc. Dữ liệu thường được đặt theo key kiểu `String` hoặc key đối tượng riêng; giá trị có thể là đối tượng bất kỳ nhưng nên nhỏ, có ngữ nghĩa rõ và an toàn khi chia sẻ.

Các điểm cốt lõi:

1. **Gắn với Subscriber, không gắn với Thread.** Context là một phần của quan hệ subscription; Reactor chuyển nó qua chuỗi operator trong quá trình subscribe. Một publisher có thể được subscribe nhiều lần với các context khác nhau.
2. **Ghi ở thời điểm subscribe.** `contextWrite` nhận context từ phía downstream và tạo context mới cho phần upstream của operator đó. `Context.put`/`delete` trả về instance mới; chúng không sửa trực tiếp context cũ.
3. **Tín hiệu subscription đi từ dưới lên; dữ liệu thường đi từ trên xuống.** Trong chuỗi viết theo thứ tự từ trên xuống, `contextWrite` ở phía sau có thể cấp dữ liệu cho `deferContextual` ở phía trước.
4. **Phạm vi do vị trí operator quyết định.** Operator downstream của một `contextWrite` không tự thấy phần ghi mới của operator ấy. Khi ghi trùng key, lần ghi gần phía reader hơn trên nhánh upstream sẽ quyết định giá trị mà reader thấy.
5. **Bất biến của map không làm đối tượng value bất biến.** Không dùng Context như kho chứa trạng thái mutable phải được đồng bộ hóa.

Mô hình trực quan:

~~~text
Lắp ráp pipeline (assembly): Mono.deferContextual(...).map(...).contextWrite(...)
Subscribe/context:              subscriber -> contextWrite -> map -> deferContextual
Dữ liệu onNext:                  deferContextual -> map -> subscriber
~~~

Không có một `Context` toàn cục cho mọi request. Không thể chỉ gọi `Context.of(...)` rồi mong các luồng xử lý khác tự thấy; nó phải được ghép vào **subscription cụ thể**.

## 3. So sánh với ThreadLocal

| Tiêu chí | `ThreadLocal<T>` | Reactor `Context` |
|---|---|---|
| Đơn vị gắn dữ liệu | Một thread Java | Subscriber/subscription trong chuỗi Reactor |
| Ghi/đọc | `set/get/remove` | `contextWrite` / `deferContextual`, `ContextView` |
| Đổi thread bằng scheduler | Không tự bảo toàn giá trị | Context vẫn được truyền trong chuỗi Reactor phù hợp |
| Hướng và phạm vi | Các lệnh chạy trên thread hiện tại | Reader ở upstream của thao tác `contextWrite` tương ứng |
| Vòng đời | Cho đến khi `remove()` hoặc thread kết thúc | Gắn với subscription và các nhánh của nó |
| Rủi ro thường gặp | Mất context khi đổi thread; lộ trạng thái trên thread pool nếu không dọn | Đặt `contextWrite` sai vị trí; mất scope khi tạo subscription độc lập |
| Ứng dụng Spring Security | `SecurityContextHolder` kiểu thread-bound trong mô hình imperative | `ReactiveSecurityContextHolder` dùng Reactor Context trong WebFlux |

**Không hiểu nhầm:** `ThreadLocal` vẫn có thể được nối với reactive pipeline bằng cơ chế context propagation có cấu hình. Điểm khác nhau là Reactor Context có mô hình phạm vi theo subscriber, còn `ThreadLocal` nguyên bản có mô hình theo thread.

## 4. API quan trọng và hướng đọc/ghi

### 4.1. Ghi metadata bằng contextWrite

~~~java
Mono<String> task = Mono.deferContextual(view ->
    Mono.just("traceId=" + view.<String>get("traceId"))
).contextWrite(context -> context.put("traceId", "req-123"));
~~~

`contextWrite(Function<Context, Context>)` tạo context mới để các operator **upstream** thấy giá trị `traceId`. Cũng có overload `contextWrite(ContextView)`, thuận tiện khi đã có một context cần ghép:

~~~java
Mono<String> task = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("locale", "vi").toString())
).contextWrite(Context.of("locale", "en"));
~~~

`Context.of(key, value)` tạo map mới; `put`, `putAll`, `delete` trả về context mới. Không cần và không nên giả định có thể gọi `set` lên Context.

### 4.2. Đọc metadata bằng deferContextual

`Mono.deferContextual(view -> ...)` (tương tự `Flux.deferContextual`) chỉ thực hiện lambda trong ngữ cảnh của subscription. Dùng `view.get(key)` khi key **bắt buộc phải có**; nếu thiếu, thao tác đọc phát sinh lỗi. Dùng `getOrDefault(key, fallback)` hoặc `hasKey(key)` khi metadata có thể thiếu.

Nếu cần dùng context cùng phần tử của một pipeline, có thể đặt `deferContextual` bên trong `flatMap`:

~~~java
Mono<String> result = Mono.just("order-7")
    .flatMap(orderId -> Mono.deferContextual(view ->
        Mono.just(orderId + "@" + view.getOrDefault("tenantId", "public"))
    ))
    .contextWrite(Context.of("tenantId", "tenant-a"));
~~~

Kết quả là `order-7@tenant-a`. `Mono.just(...)` tự nó không cung cấp API đọc Context; hãy đọc ở điểm cần thiết bằng một operator có hỗ trợ contextual access.

### 4.3. Vị trí contextWrite thay đổi kết quả

~~~java
Mono<String> visible = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("key", "missing").toString())
).contextWrite(Context.of("key", "visible"));  // "visible"

Mono<String> invisible = Mono.just("start")
    .contextWrite(Context.of("key", "hidden"))
    .flatMap(s -> Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("key", "missing").toString())
    ));                                         // "missing"
~~~

Ở ví dụ thứ hai, `flatMap` nằm **downstream** của `contextWrite`, nên inner publisher đọc context của subscriber downstream và không nhận lần ghi `hidden` phía trên. Đây là lỗi phổ biến khi nhìn pipeline giống như các câu lệnh thực thi tuần tự.

## 5. Ví dụ Java 17 chạy độc lập

Tạo dự án Gradle Java nhỏ. Ví dụ dưới đây dùng Reactor Core 3.8.7 (Java 17+), không bật tích hợp ThreadLocal tự động.

Tệp `build.gradle`:

~~~groovy
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

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ReactorContextDemo'
}
~~~

Tệp `src/main/java/ReactorContextDemo.java`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {
    private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    public static void main(String[] args) {
        TENANT.set("tenant-a");

        String threadLocalValue = Mono.fromSupplier(() -> {
                String value = TENANT.get();
                return value == null ? "<null>" : value;
            })
            .subscribeOn(Schedulers.parallel())
            .block();
        System.out.println("ThreadLocal=" + threadLocalValue);

        Mono<String> preserved = Mono.deferContextual(view ->
                Mono.just("tenant=" + view.<String>get("tenantId")))
            .publishOn(Schedulers.parallel())
            .contextWrite(Context.of("tenantId", "tenant-a"));
        System.out.println(preserved.block());

        Mono<String> scope = Mono.deferContextual(view ->
                Mono.just("upstream=" + view.getOrDefault("key", "none")))
            .contextWrite(ctx -> ctx.put("key", "inner"))
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just(value + ", downstream=" +
                    view.getOrDefault("key", "none"))))
            .contextWrite(Context.of("key", "outer"));
        System.out.println(scope.block());

        Mono<String> reusable = Mono.deferContextual(view ->
            Mono.just("request=" + view.<String>get("requestId")));
        System.out.println(
            reusable.contextWrite(Context.of("requestId", "r1")).block());
        System.out.println(
            reusable.contextWrite(Context.of("requestId", "r2")).block());

        TENANT.remove();
    }
}
~~~

Lệnh chạy từ thư mục dự án (có Gradle Wrapper):

~~~bash
./gradlew run --quiet
~~~

Trên Windows dùng `gradlew.bat run --quiet`; nếu không có wrapper nhưng đã cài Gradle, dùng `gradle run --quiet`.

Stdout dự kiến:

~~~text
ThreadLocal=<null>
tenant=tenant-a
upstream=inner, downstream=outer
request=r1
request=r2
~~~

Giải thích từng dòng:

- `TENANT.set` chạy ở main thread; `subscribeOn(Schedulers.parallel())` chuyển việc lấy `ThreadLocal` sang thread khác, nơi `TENANT` của thread đó chưa được đặt.
- `publishOn` thay đổi nơi xử lý tín hiệu, nhưng giá trị `tenantId` vẫn truy cập được thông qua Reactor Context.
- `contextWrite("outer")` cấp context cho `flatMap`; `contextWrite("inner")` nằm gần source hơn và ghi đè key cho reader upstream. Reader bên trong `flatMap` nhìn `outer`.
- Hai lần subscribe publisher `reusable` nhận `requestId` khác nhau; không có chuyện sửa một biến context chung.

`block()` chỉ có mặt để minh họa ứng dụng console. **Trong WebFlux controller/service đang xử lý reactive request, hãy trả về `Mono`/`Flux` và tránh gọi `block()`**: ngoài việc chặn thread, `block()` tạo một subscription riêng và có thể làm mất context mong đợi.

## 6. Phạm vi trong nhánh con, nhiều subscription và scheduler

**Publisher không đồng nghĩa với subscription.** Một `Mono<String>` được tái sử dụng có thể xử lý nhiều request; giá trị trong Reactor Context thường được cung cấp khi từng request subscribe. Đừng gắn thông tin request vào field singleton mutable để thay thế.

**`flatMap` tạo inner publisher.** Context hiện hành có thể được sử dụng bởi nhánh con Reactor khi nó được subscribe bởi operator; tuy nhiên một `contextWrite` đặt *bên trong* nhánh con chỉ tác động đến phần upstream của nhánh đó, không sửa context của toàn bộ chuỗi ngoài. Ví dụ:

~~~java
Mono<String> flow = Mono.just("item")
    .flatMap(item ->
        Mono.deferContextual(view ->
            Mono.just(item + ":" + view.<String>get("scope")))
        .contextWrite(Context.of("scope", "inner"))
    )
    .flatMap(value ->
        Mono.deferContextual(view ->
            Mono.just(value + ":" + view.<String>get("scope"))))
    .contextWrite(Context.of("scope", "outer"));
// item:inner:outer
~~~

**`publishOn`/`subscribeOn` tự chúng không xóa Reactor Context.** Nhưng khi rời khỏi chuỗi Reactor bằng callback tùy ý, tự gọi `subscribe()`, tạo task trên `Executor` không có cầu nối, hoặc chuyển sang API không quản lý Reactor Context, bạn có thể tạo ranh giới subscription/context mới. Muốn giữ ngữ nghĩa, ưu tiên **trả về publisher và kết hợp bằng operator** (`flatMap`, `then`, `zipWhen`, ...) thay vì subscribe thủ công bên trong service.

## 7. Liên hệ trực tiếp với Spring Security WebFlux

Trong ứng dụng Servlet đồng bộ, `SecurityContextHolder` mặc định thường được triển khai dựa trên `ThreadLocal`. Trong ứng dụng reactive, Spring Security cần lấy `Authentication` chính xác theo subscriber dù nhiều request dùng chung event-loop thread. Vì vậy Spring Security cung cấp `ReactiveSecurityContextHolder` đặt/đọc `Mono<SecurityContext>` trong Reactor Context.

Các phương thức cần nhớ:

- `ReactiveSecurityContextHolder.getContext()`: trả về `Mono<SecurityContext>` của subscription hiện hành; khi không có context, publisher có thể rỗng.
- `ReactiveSecurityContextHolder.withAuthentication(authentication)`: tạo `Context` chứa security context mới với `Authentication` được cung cấp.
- `ReactiveSecurityContextHolder.withSecurityContext(Mono<? extends SecurityContext>)`: tạo `Context` từ một publisher security context.
- `ReactiveSecurityContextHolder.clearContext()`: trả về hàm xóa entry security context khỏi Reactor Context cho phạm vi upstream tương ứng.

Trong WebFlux đã cấu hình Spring Security, các web filter xác thực/khôi phục context cho luồng request; ứng dụng thường **đọc** context hiện hành thay vì tự dựng một `Authentication` để giả làm người dùng thật.

Ví dụ method trong một Spring WebFlux service (đoạn tích hợp; yêu cầu dependency Spring Security reactive tương thích với Spring Boot của ứng dụng):

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");
}
~~~

Cần để `Mono` này được subscribe **trong luồng xử lý request đã qua Spring Security filter chain**. Đường dẫn có quy tắc bảo mật chặn request chưa xác thực có thể trả HTTP 401/403 trước khi method chạy; giá trị `anonymous` chỉ là fallback ở tầng publisher, không biến endpoint thành public.

Khi cần viết unit test cho service, có thể cung cấp một `Authentication` thử nghiệm trong đúng subscription:

~~~java
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Authentication testUser =
    new TestingAuthenticationToken("alice", "unused", "ROLE_READER");

Mono<String> tested = ReactiveSecurityContextHolder.getContext()
    .map(security -> security.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(testUser));

// tested phát ra "alice" khi được subscribe.
~~~

Đây là minh họa kiểm thử/cấp context có chủ đích, **không phải thao tác đăng nhập thực tế**. Xóa entry bằng `clearContext()` cũng không tương đương thu hồi JWT, xóa session hoặc thực hiện đầy đủ quy trình logout. Không dùng `SecurityContextHolder.getContext()` kiểu imperative để suy đoán danh tính request trong reactive pipeline.

## 8. Nếu một thư viện vẫn yêu cầu ThreadLocal/MDC thì sao?

Các thư viện logging MDC, tracing hoặc mã cũ có thể dùng `ThreadLocal`. Reactor Context **không tự động chép mọi key vào mọi ThreadLocal**. Có hai cách tiếp cận:

1. **Ưu tiên API reactive/context-aware** nếu thư viện có hỗ trợ: giữ correlation ID trong Context và đọc tại đúng operator hoặc chuyển metadata thành tham số tường minh khi đi vào API nghiệp vụ.
2. **Dùng cầu nối được cấu hình**, chẳng hạn Micrometer Context Propagation. Reactor Core hỗ trợ `contextCapture()` để chụp các `ThreadLocal` có `ThreadLocalAccessor` đăng ký tại thời điểm subscribe, và `Hooks.enableAutomaticContextPropagation()` cho chế độ phục hồi ThreadLocal tự động trên các subscription mới. Phải có dependency/đăng ký accessor phù hợp; nên bật hook sớm khi ứng dụng khởi động và đo chi phí hiệu năng thực tế.

Chế độ mặc định (limited) và chế độ automatic có mức độ phục hồi `ThreadLocal` khác nhau. Không giả định `publishOn` tự khôi phục MDC, cũng không giả định `contextCapture()` có thể chụp biến chưa được đăng ký accessor. Nếu tự dùng `ThreadLocal` để tương tác với thư viện ngoài, cần khôi phục và dọn trạng thái chắc chắn, nhất là với thread pool.

Reactor Context là **nguồn dữ liệu theo subscriber**; cầu nối chỉ là cách tích hợp với API có hợp đồng theo thread. Đối với thông tin xác thực trong WebFlux, ưu tiên cơ chế Spring Security reactive.

## 9. Thiết kế thực tế và lỗi phổ biến

**Những dữ liệu phù hợp:** trace/correlation ID, tenant ID đã xác minh, metadata cho thư viện, và security context do framework quản lý. Chỉ dùng Context cho thông tin phụ trợ; tham số ảnh hưởng trực tiếp đến kết quả nghiệp vụ thường nên được truyền rõ ràng trong hàm. Không lưu mật khẩu, token thô hoặc dữ liệu nhạy cảm không cần thiết vào context; tránh ghi trực tiếp object `Authentication` ra log.

**Lỗi 1 – đọc sai phía của `contextWrite`:** đặt reader downstream nên nhận giá trị mặc định hoặc lỗi thiếu key. Sửa bằng cách xác định chính xác subscriber nào cần key, sau đó đặt `contextWrite` ở downstream phù hợp.

**Lỗi 2 – gọi `Context.of` mà không gắn vào pipeline:** tạo `Context` đơn lẻ không làm thay đổi subscription; cần dùng `contextWrite` tại điểm tích hợp.

**Lỗi 3 – dùng `ThreadLocal` như biến request toàn cục:** lỗi xuất hiện khi đổi scheduler hoặc tái sử dụng event-loop thread. Sửa bằng `Context`, API reactive hoặc cầu nối context propagation đã kiểm soát.

**Lỗi 4 – gọi `subscribe()`/`block()` lồng trong service:** tạo subscription riêng và làm lệch phạm vi context, đồng thời phá luồng xử lý backpressure/lỗi. Sửa bằng trả về và kết hợp publisher.

**Lỗi 5 – dùng `get(key)` cho key tùy chọn:** vắng key có thể phát sinh lỗi. Dùng `getOrDefault`/`hasKey` hoặc cung cấp context bắt buộc tại biên request.

**Lỗi 6 – tưởng bất biến tức là mọi value đều bất biến:** `Context` không sửa bản đồ cũ, nhưng có thể chứa mutable object được nhiều operator cùng tham chiếu. Ưu tiên value nhỏ, immutable; không đặt mutable state dùng chung để theo dõi request.

**Lỗi 7 – đặt security context giả trong production:** `withAuthentication` chỉ ghép một giá trị context, không thay bước xác thực, phân quyền hay quản lý session/token. Dùng filter chain và cấu hình Spring Security để xác thực thật; chỉ dùng cấp trực tiếp trong test hoặc quy trình được thiết kế, kiểm soát rõ.

## 10. Kiểm thử và câu hỏi tự đánh giá

Trong dự án có dependency test `io.projectreactor:reactor-test` cùng phiên bản với Reactor Core, có thể kiểm thử trực tiếp một subscription:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

StepVerifier.create(
    Mono.deferContextual(view ->
        Mono.just(view.<String>get("traceId")))
    .contextWrite(Context.of("traceId", "req-9"))
)
.expectNext("req-9")
.verifyComplete();
~~~

Những case nên có trong test suite: có/thiếu key bắt buộc; `contextWrite` nằm sai/vừa đúng vị trí; hai subscription trên cùng publisher nhưng context khác nhau; switch scheduler; inner `flatMap`; security context có/không có authentication theo luồng request. Tránh dựa vào tên thread hay timing để chứng minh tính đúng đắn của context.

Tự trả lời ba câu hỏi:
1. Nếu `Mono.deferContextual(...)` nằm sau `contextWrite` trong chuỗi, liệu nó luôn thấy giá trị vừa ghi không? **Không**; phải xét vị trí upstream/downstream.
2. Hai request WebFlux lần lượt chạy trên cùng event-loop thread có bắt buộc cùng Reactor Context không? **Không**; context gắn với subscriber của từng subscription.
3. Khi dùng `ReactiveSecurityContextHolder.clearContext()`, token phía client có bị thu hồi không? **Không**; đây chỉ là thao tác trên entry context trong phạm vi reactive đang xét.

## Tài liệu chính thức

- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Context-Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Spring Security — `ReactiveSecurityContextHolder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
