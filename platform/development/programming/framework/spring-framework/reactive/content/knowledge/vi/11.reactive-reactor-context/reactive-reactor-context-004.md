# Đọc ngữ cảnh bằng `deferContextual` trong Project Reactor

## 1. Reactor Context dùng để làm gì?

Trong ứng dụng Spring WebFlux, một request thường đi qua nhiều tầng: controller, service, repository và các lời gọi HTTP khác. Các tầng này có thể chạy trên nhiều thread khác nhau, nhưng vẫn cần truy cập một số **metadata gắn với subscription/request hiện tại**, chẳng hạn:

- `traceId` hoặc `correlationId` để nối log và distributed trace.
- `tenantId` để xác định tenant trong hệ thống multi-tenant.
- Thông tin xác thực/ủy quyền mà framework hỗ trợ.
- Metadata giao dịch reactive hoặc thông tin phục vụ quan sát.

Project Reactor cung cấp **Reactor Context** để truyền metadata theo **subscription** xuyên suốt một pipeline reactive. Để đọc dữ liệu trong Context khi Publisher được đăng ký, dùng `deferContextual`.

Ví dụ ngắn:

```java
Mono<String> tenant = Mono.deferContextual(context ->
        Mono.just(context.get("tenantId"))
).contextWrite(context -> context.put("tenantId", "tenant-a"));
```

Khi có subscriber, `deferContextual` đọc `tenantId` từ Context của subscription và phát `"tenant-a"`.

Cần phân biệt:

- **Reactor Context** là cấu trúc metadata gắn với subscription, được truyền qua các operator Reactor.
- **Java `ThreadLocal`** gắn giá trị với một thread. Thread có thể thay đổi trong pipeline reactive, nên không thể mặc định metadata trong ThreadLocal sẽ theo request.
- **Method parameter** là cách truyền dữ liệu tường minh giữa các hàm. Với dữ liệu nghiệp vụ chính, truyền qua tham số thường dễ đọc và dễ kiểm thử hơn Context.
- **`deferContextual`** là cách tạo Publisher dựa trên Context tại thời điểm subscribe; nó không tự thêm dữ liệu vào Context và cũng không tự tạo thread.

Context phù hợp với **metadata xuyên suốt nhiều tầng**, không nên biến thành một kho chứa mọi dữ liệu nghiệp vụ của request.

## 2. `ContextView` và cách đọc giá trị

`deferContextual` nhận một `ContextView`, là giao diện chỉ đọc của Reactor Context. Các thao tác phổ biến:

| API | Ý nghĩa | Khi nào dùng |
|---|---|---|
| `context.get(key)` | Lấy giá trị theo key; ném lỗi nếu key không tồn tại | Key bắt buộc, thiếu key là lỗi cấu hình |
| `context.getOrDefault(key, defaultValue)` | Lấy giá trị hoặc dùng mặc định | Metadata tùy chọn |
| `context.hasKey(key)` | Kiểm tra key có tồn tại không | Chọn nhánh xử lý |
| `context.isEmpty()` | Kiểm tra Context có rỗng không | Chẩn đoán hoặc logic mặc định |
| `context.stream()` | Duyệt các entry của Context | Debug có kiểm soát; tránh log thông tin nhạy cảm |

`ContextView` là **read-only**. Không gọi `put` trên `ContextView`; muốn thêm hoặc thay giá trị, dùng `contextWrite` với `Context`.

Ví dụ đọc key bắt buộc:

```java
Mono<String> traceId = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
);
```

Nếu subscriber không cung cấp `"traceId"`, `get` ném `NoSuchElementException` trong lúc tạo Publisher bên trong `deferContextual`; Reactor chuyển exception đó thành `onError`.

Với key tùy chọn:

```java
Mono<String> traceId = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("traceId", "trace-unknown"))
);
```

Hoặc kiểm tra tường minh:

```java
Mono<String> traceId = Mono.deferContextual(context -> {
    if (context.hasKey("traceId")) {
        return Mono.just(context.get("traceId"));
    }
    return Mono.just("trace-unknown");
});
```

Chọn một chính sách nhất quán. Nếu thiếu `tenantId` có thể gây truy cập sai tenant, không nên lặng lẽ dùng một tenant mặc định; hãy xác định đó là lỗi bắt buộc và trả lỗi phù hợp.

## 3. `Mono.deferContextual` hoạt động như thế nào?

Dạng sử dụng:

```java
static <T> Mono<T> Mono.deferContextual(
        Function<ContextView, ? extends Mono<? extends T>> factory);
```

Đây là **chữ ký rút gọn để giải thích generic**, không phải đoạn khai báo method để copy vào class. Factory nhận ContextView và trả về một `Mono` khác. Factory được gọi **khi có subscription**, với Context của subscriber đó.

Chuỗi xử lý:

```text
Subscriber
    |
    | subscribe với Context riêng
    v
deferContextual(contextView -> ...)
    |
    | đọc key từ ContextView
    | tạo Mono phù hợp
    v
Publisher được trả về từ factory
    |
    | onNext / onComplete hoặc onError
    v
Downstream Subscriber
```

Ví dụ:

```java
Mono<String> greeting = Mono.deferContextual(context -> {
    String name = context.getOrDefault("userName", "guest");
    return Mono.just("Hello, " + name);
});
```

Lúc khai báo `greeting`, factory chưa chạy. Khi subscriber đăng ký, Reactor cung cấp ContextView thuộc subscription đó, rồi factory tạo Publisher tương ứng.

**Mỗi subscription có thể nhìn thấy Context khác nhau** dù dùng chung một biến Publisher:

```java
Mono<String> greeting = Mono.deferContextual(context ->
        Mono.just("Hello, " + context.getOrDefault("userName", "guest"))
);

String first = greeting
        .contextWrite(context -> context.put("userName", "An"))
        .block();

String second = greeting
        .contextWrite(context -> context.put("userName", "Binh"))
        .block();
```

Kết quả lần lượt là `"Hello, An"` và `"Hello, Binh"`. Đây là hai subscription độc lập; `contextWrite` không sửa một biến Context dùng chung cho tất cả subscriber.

`block()` trong ví dụ chỉ giúp minh họa lấy kết quả trong chương trình console/test. Không gọi `block()` trong controller hoặc service WebFlux để chờ kết quả reactive.

## 4. `Flux.deferContextual` để đọc Context trong luồng nhiều phần tử

Với `Flux`, factory có thể trả về một `Publisher<T>` và đọc metadata một lần để tạo cả chuỗi:

```java
Flux<String> events = Flux.deferContextual(context -> {
    String requestId = context.getOrDefault("requestId", "anonymous");

    return Flux.just("accepted", "processing", "completed")
            .map(event -> requestId + ":" + event);
});
```

Khi subscriber đặt `requestId = "req-42"` trong Context, các giá trị được phát là:

```text
req-42:accepted
req-42:processing
req-42:completed
```

Context được đọc tại lúc tạo inner Publisher cho subscription. Nếu nhiều phần tử trong cùng một luồng cần dùng cùng metadata, có thể đọc Context một lần ở factory rồi đóng giá trị vào lambda `map`. Nếu cần đọc Context ở từng Publisher con hoặc từng subscription con, đặt `deferContextual` tại đúng ranh giới đó.

Không nhầm `Flux.deferContextual` với việc tự động thêm Context vào từng object. Giá trị phát ra vẫn là `T`; Context được truy cập riêng qua subscription.

## 5. `defer` và `deferContextual` khác nhau ra sao?

Hai API đều trì hoãn việc tạo Publisher, nhưng mục đích khác nhau:

| API | Factory nhận gì? | Khi nào phù hợp |
|---|---|---|
| `Mono.defer(() -> publisher)` | Không nhận đối số | Cần tạo Publisher mới theo mỗi subscription, không cần đọc Context |
| `Mono.deferContextual(ctx -> publisher)` | Nhận `ContextView` của subscription | Cần tạo Publisher dựa trên metadata subscriber |
| `Flux.defer(() -> publisher)` | Không nhận đối số | Tạo Flux theo mỗi subscription |
| `Flux.deferContextual(ctx -> publisher)` | Nhận `ContextView` | Tạo Flux theo Context |

Ví dụ `defer`:

```java
Mono<String> value = Mono.defer(() -> {
    String generated = createValue();
    return Mono.just(generated);
});
```

`createValue()` được gọi khi subscribe, nhưng không có cách đọc Context qua tham số factory này.

Ví dụ `deferContextual`:

```java
Mono<String> value = Mono.deferContextual(context -> {
    String tenant = context.get("tenantId");
    return Mono.just(createValueForTenant(tenant));
});
```

Ở đây factory vừa được trì hoãn vừa có thể đọc `tenantId` của subscriber.

Nếu chỉ cần đọc Context trong một operator, có thể dùng các toán tử hỗ trợ Context khác hoặc lồng `deferContextual` ở đúng vị trí. Không cần bọc toàn bộ pipeline trong `deferContextual` nếu không có lý do.

## 6. `contextWrite`: đưa dữ liệu vào Context

`deferContextual` chỉ đọc; để thêm metadata, dùng `contextWrite`.

### 6.1. Thêm một key

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
).contextWrite(context ->
        context.put("traceId", "trace-001")
);
```

`Context` là cấu trúc **immutable**: `put` trả về một Context mới. Hãy trả Context mới từ lambda `contextWrite`; không coi thao tác này như sửa một map mutable.

### 6.2. Thêm nhiều key bằng `Context.of`

```java
import reactor.util.context.Context;

Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("tenantId") + "/" + context.get("traceId"))
).contextWrite(Context.of(
        "tenantId", "tenant-a",
        "traceId", "trace-001"
));
```

`Context.of` có các overload tạo Context từ các cặp key/value. Với nhiều key hoặc cần logic merge, dùng lambda `contextWrite`.

### 6.3. Thêm key có sẵn điều kiện

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("locale", "vi"))
).contextWrite(context -> {
    if (context.hasKey("locale")) {
        return context;
    }
    return context.put("locale", "vi");
});
```

Đoạn trên giữ giá trị `locale` đã có, nếu chưa có mới thêm mặc định. Vì Context immutable, cả hai nhánh đều trả về một Context hợp lệ.

### 6.4. Ghi đè key trùng

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("tenantId"))
).contextWrite(context -> context.put("tenantId", "tenant-local"));
```

`put` với cùng key thay giá trị key đó trong Context mới được trả về. Cẩn thận với key do framework quản lý: ghi đè một key bảo mật hoặc transaction ngoài ý muốn có thể làm thay đổi hành vi ứng dụng.

## 7. Hướng truyền Context: từ downstream ngược lên upstream

Đây là quy tắc quan trọng nhất khi đọc code: **Context được truyền từ subscriber ngược lên phía upstream**, ngược chiều dữ liệu `onNext`.

```text
Dòng dữ liệu:
source ── onNext ──> map ── onNext ──> subscriber

Dòng Context:
source <── Context ── map <── Context ── subscriber
```

Vì thế:

```java
Mono<String> source = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
);

Mono<String> result = source
        .contextWrite(context -> context.put("traceId", "req-100"));
```

`contextWrite` nằm **phía downstream** so với `deferContextual` trong thứ tự khai báo chain. Khi subscription đi vào, `contextWrite` bổ sung key trước khi Context tới nguồn, vì vậy `deferContextual` đọc được `"req-100"`.

Đừng suy luận Context truyền cùng chiều với `onNext`. Ví dụ sau dễ gây nhầm:

```java
Mono<String> source = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("traceId", "missing"))
);

Mono<String> result = source
        .contextWrite(context -> context.put("traceId", "req-100"))
        .map(value -> value);
```

Ở đây `map` nằm sau `contextWrite` theo hướng dữ liệu. Context mà `contextWrite` thiết lập được dùng cho phần upstream của nó; `map` ở phía downstream không phải nơi đọc key từ thao tác đó. Nếu muốn đọc Context, đặt `deferContextual` ở upstream thích hợp và đặt `contextWrite` downstream của nó.

Khi có nhiều `contextWrite`, thứ tự khai báo và key trùng có ảnh hưởng đến giá trị mà nguồn nhìn thấy. Tránh nhiều tầng ghi cùng key nếu không có quy ước rõ ràng. Hãy viết test cho giá trị cuối cùng thay vì dựa vào trực giác về thứ tự.

## 8. Context không phải ThreadLocal

Reactor Context được truyền theo subscription, không gắn chặt vào một thread. Vì vậy, trong một pipeline Reactor, dữ liệu Context có thể được đọc qua các operator kể cả khi việc thực thi đổi thread do scheduler.

Ví dụ:

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just("trace=" + context.get("traceId"))
).publishOn(reactor.core.scheduler.Schedulers.parallel())
 .map(value -> value + " processed")
 .contextWrite(context -> context.put("traceId", "trace-77"));
```

Context được thiết lập bởi `contextWrite` có thể được `deferContextual` đọc; `publishOn` chuyển xử lý tín hiệu phía sau sang scheduler khác. Không cần tự sao chép `traceId` vào `ThreadLocal` để giữ Context trong pipeline Reactor.

Tuy nhiên:

- Không giả định Context tự động trở thành ThreadLocal cho mọi thư viện ngoài Reactor.
- Nếu gọi callback trong executor tùy chỉnh hoặc API không tích hợp Reactor, cần kiểm tra cơ chế truyền context của integration đó.
- ThreadLocal của MDC logging không tự đồng nghĩa với Reactor Context. Muốn đưa trace metadata vào log, dùng tích hợp logging/observability hoặc context-propagation phù hợp với phiên bản và cấu hình ứng dụng.
- Không dùng tên thread để xác định tenant hoặc người dùng. Thread có thể được tái sử dụng cho nhiều subscription.

Context và ThreadLocal giải quyết hai vấn đề khác nhau; không dùng một thứ thay thế một cách mù quáng cho thứ còn lại.

## 9. Ví dụ Java 17+ chạy được với Project Reactor

Ví dụ này dùng một Publisher `Mono` được tái sử dụng cho nhiều subscriber, mỗi subscriber cung cấp `traceId` và `tenantId` riêng. Ví dụ thứ hai dùng `Flux.deferContextual` để gắn request ID vào các sự kiện.

Cấu trúc thư mục:

```text
reactor-context-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-context-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class Main {
    public static void main(String[] args) {
        // Một pipeline dùng chung, Context khác nhau theo từng subscription.
        Mono<String> description = Mono.deferContextual(context -> {
            String traceId = context.getOrDefault("traceId", "no-trace");
            String tenantId = context.getOrDefault("tenantId", "public");
            return Mono.just("trace=" + traceId + ", tenant=" + tenantId);
        });

        String first = description
                .contextWrite(Context.of(
                        "traceId", "req-101",
                        "tenantId", "tenant-a"
                ))
                .block(Duration.ofSeconds(2));

        String second = description
                .contextWrite(Context.of(
                        "traceId", "req-202",
                        "tenantId", "tenant-b"
                ))
                .block(Duration.ofSeconds(2));

        System.out.println(first);
        System.out.println(second);

        // Flux.deferContextual đọc Context khi subscriber đăng ký.
        Flux<String> events = Flux.deferContextual(context -> {
            String requestId = context.getOrDefault(
                    "requestId", "anonymous"
            );
            return Flux.just("accepted", "completed")
                    .map(event -> requestId + ":" + event);
        });

        events.contextWrite(context ->
                context.put("requestId", "job-7")
        ).subscribe(System.out::println);
    }
}
```

Từ thư mục chứa `pom.xml`, cài JDK 17+ và Maven rồi chạy:

```bash
mvn -q compile exec:java
```

Stdout của chương trình:

```text
trace=req-101, tenant=tenant-a
trace=req-202, tenant=tenant-b
job-7:accepted
job-7:completed
```

Giải thích:

1. `description` được tạo một lần nhưng factory `deferContextual` chạy theo từng subscription.
2. Subscription đầu có `traceId=req-101`, `tenantId=tenant-a`; subscription thứ hai có giá trị riêng `req-202`, `tenant-b`.
3. Context của subscription thứ nhất không ghi đè hoặc làm rò sang subscription thứ hai.
4. `events` đọc `requestId` khi subscribe, rồi tạo hai phần tử có cùng metadata.
5. `block(Duration)` chỉ nằm trong `main()` của demo console để lấy giá trị cho stdout; không đưa cách chờ này vào controller WebFlux.

Ví dụ này không cần Spring Boot; nó sử dụng trực tiếp API của Reactor Core. Khi chạy với nguồn cold đồng bộ, thứ tự stdout như trên ổn định.

## 10. Ứng dụng Context trong Spring WebFlux

### 10.1. Gắn correlation ID vào pipeline

Giả sử một filter đã lấy `X-Correlation-Id` từ request HTTP. Có thể gắn metadata vào Context để các tầng reactive downstream/upstream phù hợp đọc được:

```java
// Minh họa trong WebFilter của ứng dụng WebFlux.
public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    String correlationId = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Correlation-Id");

    String safeId = correlationId == null
            ? UUID.randomUUID().toString()
            : correlationId;

    return chain.filter(exchange)
            .contextWrite(context ->
                    context.put("correlationId", safeId)
            );
}
```

Đây là **mã minh họa** cần các import Spring WebFlux và `java.util.UUID`; interface `WebFilter` có method `filter` trả `Mono<Void>`. `contextWrite` được gắn vào Publisher trả về từ filter để Context có thể được các thành phần reactive upstream trong quá trình xử lý request đọc theo đúng ranh giới subscription. Khi triển khai filter thực tế, cần xem vị trí các operator và cách framework ghép chain để bảo đảm Context tới đúng nguồn.

Đọc ở service:

```java
// Mã minh họa trong service reactive.
Mono<Customer> findCustomer(long id) {
    return Mono.deferContextual(context -> {
        String correlationId = context.get("correlationId");
        return repository.findById(id)
                .doOnNext(customer ->
                        log.info("correlationId={} customer={}",
                                correlationId, customer.getId())
                );
    });
}
```

Ở đây service lấy `correlationId` từ Context và dùng nó trong logging. Repository vẫn trả `Mono<Customer>`; Context không làm thay đổi kiểu dữ liệu nghiệp vụ.

### 10.2. Tenant metadata

Trong hệ thống multi-tenant, `tenantId` có thể được dùng bởi repository/service để lựa chọn schema hoặc bổ sung điều kiện truy vấn. Phải bảo đảm tenant được xác thực từ nguồn đáng tin cậy và mọi truy vấn đều áp dụng isolation đúng cách.

Không nên để client tùy ý truyền `tenantId` vào Context rồi coi đó là bằng chứng ủy quyền. Context là phương tiện truyền metadata trong pipeline; nó không thay thế authentication/authorization, kiểm tra quyền truy cập hay chính sách chống truy cập chéo tenant.

### 10.3. Spring Security và transaction reactive

Một số framework tích hợp Reactor Context để truyền SecurityContext hoặc thông tin giao dịch reactive. Với Spring Security, dùng cơ chế tích hợp như `ReactiveSecurityContextHolder` và cấu hình bảo mật chính thức; không tự tạo key rồi giả định nó thay thế security context chuẩn.

Với reactive transaction (ví dụ R2DBC), Spring quản lý transaction context trong reactive execution. Giữ nguyên Publisher chain, tránh `.block()` hoặc tách subscription tùy tiện trong transaction vì có thể làm mất ranh giới context/transaction. Không tự ghi đè các key nội bộ framework.

## 11. Key, kiểu dữ liệu và an toàn thông tin

### 11.1. Chọn key ổn định

Các ví dụ dùng String key như `"traceId"` và `"tenantId"` cho dễ đọc. Trong thư viện dùng chung, key có thể xung đột với thư viện khác. Có thể dùng một constant object hoặc kiểu key chuyên biệt do ứng dụng quản lý:

```java
static final Object TENANT_KEY = new Object();

Mono<String> tenant = Mono.deferContextual(context ->
        Mono.just(context.get(TENANT_KEY))
).contextWrite(context -> context.put(TENANT_KEY, "tenant-a"));
```

Nếu dùng class key, bảo đảm cùng một key instance hoặc quy tắc equality nhất quán khi ghi và đọc.

### 11.2. Context immutable nhưng value không nhất thiết immutable

Các thao tác `put`, `delete`, `putAll` tạo Context mới, nhưng object được lưu làm value có thể là mutable. Nếu nhiều operator cùng giữ một object mutable, vẫn có thể xảy ra race condition hoặc thay đổi trạng thái ngoài dự kiến.

Ưu tiên value nhỏ, immutable (String, ID, record bất biến hoặc object metadata không thay đổi). Không đặt một mutable HashMap dùng chung trong Context để biến nó thành nơi chia sẻ state.

### 11.3. Không lưu bí mật hoặc dữ liệu lớn tùy tiện

Context có thể được nhiều operator trong pipeline truy cập; không phải vùng lưu trữ bí mật riêng cho từng tầng. Tránh lưu password, access token thô, thông tin thẻ thanh toán hoặc dữ liệu cá nhân nhạy cảm nếu không thật sự cần. Cũng tránh lưu object lớn, request body hoặc entity graph vào Context.

Chỉ đưa metadata tối thiểu cần truyền. Nếu cần credential, dùng abstraction bảo mật chuyên dụng, kiểm soát scope và vòng đời; không log toàn bộ Context.

### 11.4. Context theo subscription, không phải theo user toàn cục

Không dùng Context để lưu “user hiện tại” ở biến static hoặc singleton. Một server có nhiều request đồng thời; mỗi subscription có Context riêng. Cách đọc qua `deferContextual` giữ ranh giới theo subscriber, còn biến mutable global có thể gây rò dữ liệu giữa request.

## 12. Lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Gọi `context.get("key")` khi không bảo đảm key tồn tại | Ném `NoSuchElementException`, phát `onError` | Dùng `getOrDefault` hoặc kiểm tra `hasKey`; với key bắt buộc, báo lỗi có chủ đích |
| Dùng `defer()` rồi mong factory đọc được Context | Supplier của `defer` không nhận `ContextView` | Dùng `deferContextual` |
| Đặt `contextWrite` ở phía upstream của operator cần đọc | Context truyền từ downstream lên upstream; key có thể không tới nơi cần | Đặt `contextWrite` downstream của đoạn `deferContextual` cần đọc |
| Coi Context như ThreadLocal | Thread có thể đổi; thư viện ngoài Reactor không tự đọc Context | Dùng `deferContextual`, integration context propagation phù hợp |
| Cho rằng `contextWrite` sửa Context dùng chung | Context immutable và theo subscription | Trả Context mới từ `put`, không chia sẻ mutable state |
| Ghi đè key của Spring Security/transaction | Có thể phá cơ chế bảo mật hoặc transaction | Dùng API framework, tránh key nội bộ |
| Dùng Context chứa toàn bộ request/entity | Tăng bộ nhớ, khó truy vết và khó kiểm thử | Chỉ lưu metadata nhỏ, cần thiết |
| Gọi `.block()` để đọc Context trong controller | Chặn thread, tách khỏi reactive flow | Trả Publisher và đọc Context bên trong chain |
| Mong ThreadLocal MDC tự động đồng bộ với Context | Hai cơ chế độc lập | Dùng integration logging/observability đúng phiên bản |
| Gọi `subscribe()` lồng trong service | Tạo subscription riêng, có thể mất context/transaction của chain gọi | Trả Publisher để caller ghép vào pipeline |

## 13. Kiểm thử Context bằng `StepVerifier`

Nếu dự án có dependency `reactor-test`, `StepVerifier` cho phép kiểm tra Context của subscriber mà không cần `.block()`:

```java
import reactor.test.StepVerifier;
import reactor.util.context.Context;

Mono<String> trace = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
);

StepVerifier.create(
        trace,
        StepVerifierOptions.create()
                .withInitialContext(Context.of("traceId", "test-123"))
)
.expectNext("test-123")
.verifyComplete();
```

Đây là **đoạn mã test**; cần import `reactor.test.StepVerifierOptions` và thêm dependency `io.projectreactor:reactor-test` trong scope test. `withInitialContext` cung cấp Context ban đầu cho subscriber. `verifyComplete()` xác nhận một phần tử đúng và kết thúc bình thường.

Có thể kiểm tra Context thiếu key:

```java
StepVerifier.create(trace)
        .expectError(java.util.NoSuchElementException.class)
        .verify();
```

Và kiểm tra Context riêng biệt theo subscription:

```java
Mono<String> trace = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
);

StepVerifier.create(
        trace,
        StepVerifierOptions.create()
                .withInitialContext(Context.of("traceId", "A"))
)
.expectNext("A")
.verifyComplete();

StepVerifier.create(
        trace,
        StepVerifierOptions.create()
                .withInitialContext(Context.of("traceId", "B"))
)
.expectNext("B")
.verifyComplete();
```

Trong test thực tế, cần xác minh cả trường hợp key bắt buộc, default, ghi đè key, Context qua `flatMap`/`publishOn`, và tích hợp framework. Đừng chỉ kiểm tra một pipeline đơn giản rồi kết luận mọi callback thư viện ngoài đều tự nhận Context.

## 14. Bài tập tự kiểm tra

**Câu 1.** `Mono.deferContextual(ctx -> Mono.just(ctx.get("traceId"))).contextWrite(ctx -> ctx.put("traceId", "r-1"))` phát gì?

**Đáp án:** `"r-1"`. `contextWrite` nằm downstream của `deferContextual` theo thứ tự khai báo và cung cấp key cho phần upstream.

**Câu 2.** Vì sao `Mono.defer(() -> Mono.just("x"))` không thể đọc `tenantId` trực tiếp từ factory?

**Đáp án:** Supplier của `defer` không nhận `ContextView`. Dùng `Mono.deferContextual(ctx -> ...)` nếu cần đọc Context.

**Câu 3.** `context.get("userId")` làm gì khi key không có?

**Đáp án:** Ném `NoSuchElementException`, khiến nguồn `deferContextual` phát `onError`. Dùng `getOrDefault` nếu key thực sự tùy chọn.

**Câu 4.** Hai subscriber cùng subscribe một biến `Mono` nhưng mỗi subscriber có Context khác nhau thì có dùng chung `tenantId` không?

**Đáp án:** Không. Mỗi subscription có Context riêng; cùng một pipeline cold có thể đọc giá trị khác nhau theo subscriber.

**Câu 5.** Context truyền theo chiều nào so với `onNext`?

**Đáp án:** Context được truyền từ downstream subscriber ngược lên upstream; dữ liệu `onNext` đi từ upstream xuống downstream.

**Câu 6.** `publishOn` chuyển thread thì Context có tự mất không?

**Đáp án:** Context của Reactor được truyền theo subscription qua các operator Reactor, không gắn với thread. Nhưng ThreadLocal và thư viện ngoài Reactor cần cơ chế tích hợp riêng.

**Câu 7.** Có nên lưu access token thô hoặc toàn bộ request body trong Context không?

**Đáp án:** Không nên. Chỉ lưu metadata tối thiểu cần thiết; dùng abstraction bảo mật và quản lý dữ liệu nhạy cảm đúng scope.

## 15. Quy tắc áp dụng

- Dùng **`deferContextual`** khi cần đọc Context tại thời điểm subscribe và tạo Publisher dựa trên metadata của subscriber.
- Dùng **`ContextView.get`** cho key bắt buộc; dùng `getOrDefault` hoặc `hasKey` cho key tùy chọn.
- Dùng **`contextWrite`** để thêm/thay metadata; nhớ Context immutable và truyền từ downstream lên upstream.
- Dùng Context cho trace ID, tenant metadata và thông tin xuyên tầng phù hợp; dữ liệu nghiệp vụ chính vẫn nên truyền qua tham số.
- Không đồng nhất Context với ThreadLocal; không giả định thư viện tùy ý ngoài Reactor tự đọc được Context.
- Không ghi đè key nội bộ Spring Security/transaction; sử dụng API tích hợp chính thức.
- Kiểm thử Context ở các ranh giới operator, subscription và scheduler bằng `StepVerifier` khi cần.

**Ghi nhớ:** `deferContextual` nhận `ContextView` của **subscription hiện tại** để tạo Publisher phù hợp. Context truyền ngược từ downstream lên upstream và độc lập với thread; `contextWrite` là cách cung cấp metadata, còn `deferContextual` là cách đọc metadata đó trong reactive pipeline.
