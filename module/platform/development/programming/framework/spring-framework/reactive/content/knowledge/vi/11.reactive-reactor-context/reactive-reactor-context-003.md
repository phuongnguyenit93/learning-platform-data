# Ghi ngữ cảnh bằng `contextWrite` trong Project Reactor

## 1. Mục tiêu và ngữ cảnh sử dụng

Trong Spring Framework Reactive và Spring WebFlux, các chuỗi `Mono<T>` và `Flux<T>` có thể chạy qua nhiều toán tử, nhiều thread và nhiều tầng thư viện. Đôi khi nhiều lớp cùng cần một thông tin kỹ thuật đi kèm mỗi yêu cầu — ví dụ **request ID**, correlation ID, tenant ID đã xác thực hoặc ngôn ngữ ưu tiên — nhưng ta không muốn thêm các tham số đó vào mọi phương thức xử lý dữ liệu.

**Reactor Context** là cơ chế lưu dữ liệu key–value **gắn với một subscription**, độc lập với nội dung của các tín hiệu `onNext`. Để **ghi/bổ sung/sửa các giá trị Context** cho phần upstream của một pipeline, dùng toán tử `contextWrite`.

Sau bài học, bạn cần:

1. Tạo và ghi `Context` bằng `contextWrite(ContextView)` hoặc `contextWrite(Function<Context, Context>)`.
2. Giải thích tại sao Context đi **từ downstream lên upstream khi subscribe**, trái với chiều dữ liệu `onNext`.
3. Hiểu vị trí `contextWrite` quyết định những toán tử nào đọc được khóa.
4. Áp dụng quy tắc **immutable**, key trùng, ghi đè, xóa khóa và tách biệt theo subscriber.
5. Đọc Context tại thời điểm đúng bằng `Mono.deferContextual`, `Flux.deferContextual` hoặc `transformDeferredContextual` để kiểm chứng việc ghi.
6. Tránh nhầm Context với Java `ThreadLocal`, dữ liệu business đi qua `map`/`flatMap` hoặc biến toàn cục.
7. Dùng Context có chủ đích trong Spring WebFlux mà không tự tạo subscription ngoài vòng đời request.

### Bài toán ví dụ

~~~java
Mono<String> greeting = Mono.deferContextual(ctx ->
    Mono.just("Hello " + ctx.<String>get("name"))
).contextWrite(ctx -> ctx.put("name", "Linh"));
~~~

Khi `greeting` được subscribe và hoàn tất, nó phát `Hello Linh`. Dù `contextWrite` đứng **sau** `deferContextual` trong mã, phần đọc phía trên vẫn nhận `name=Linh`. Lý do là **Context được cung cấp theo chiều subscription**, không theo chiều dữ liệu.

## 2. Phân biệt dữ liệu Publisher, Context và ThreadLocal

Giả sử một HTTP request cần trả về `Order`. Đối tượng `Order` là **dữ liệu nghiệp vụ** của Publisher, còn `traceId` là thông tin kỹ thuật giúp log các bước cùng một request.

| Cơ chế | Gắn với | Cách truy cập | Hạn chế/ý nghĩa |
| --- | --- | --- | --- |
| `Mono<Order>` / `Flux<Order>` | Tín hiệu dữ liệu `onNext` | `map`, `flatMap`, `subscribe` | Biểu diễn dữ liệu mà ứng dụng xử lý |
| `Context` / `ContextView` | Một subscription Reactor | `contextWrite` để ghi, `deferContextual` để đọc | Truyền metadata riêng của subscription |
| `ThreadLocal<T>` | Một thread Java cụ thể | `get`/`set` | Không tự theo dữ liệu khi `publishOn`/`subscribeOn` đổi thread |
| Biến `static` / global | Toàn tiến trình | Truy cập trực tiếp | Dễ lộ/chồng dữ liệu giữa nhiều request concurrent |

Một đối tượng `Mono` có thể được subscribe nhiều lần; mỗi subscriber có thể mang **Context khác nhau** dù dùng chung cùng một Publisher.

~~~text
                       cùng Publisher
                    Mono.deferContextual(...)
                      /            \
             subscription A      subscription B
             Context: rid=A      Context: rid=B
               đọc rid=A           đọc rid=B
~~~

Điều này đặc biệt quan trọng trong WebFlux vì nhiều HTTP request có thể dùng cùng singleton service. Không lưu request ID của từng người dùng trong một field mutable của singleton.

**Context không thay thế dữ liệu business.** Nếu hàm `save(order)` cần chính đối tượng `Order` để làm việc, hãy truyền nó qua `flatMap`/`map` hoặc tham số hợp đồng rõ ràng. Context nên chứa metadata có tính *orthogonal*, ví dụ trace/correlation data, không phải kho dữ liệu tùy tiện cho toàn ứng dụng.

## 3. API cốt lõi: `Context` và `ContextView`

Reactor cung cấp:

- `reactor.util.context.Context`: interface lưu key–value không thể sửa trực tiếp. Có `put`, `putAll`, `delete` nhưng **mỗi thao tác tạo Context mới**.
- `reactor.util.context.ContextView`: interface chỉ đọc. Các hàm đọc như `Mono.deferContextual` nhận `ContextView` thay vì cung cấp quyền ghi tùy ý.

Các key và value là kiểu `Object`. Tên key nên rõ ràng, ít xung đột; thông tin cần typed access thì có thể dùng key dạng đối tượng riêng/constant. **Không truyền key hoặc value `null`** vào Context.

Ví dụ dựng Context thường gặp:

~~~java
Context empty = Context.empty();

Context one = Context.of("requestId", "REQ-1");

Context two = Context.of(
    "requestId", "REQ-1",
    "tenantId", "tenant-A"
);

Context edited = two.put("locale", "vi-VN");
Context withoutTenant = edited.delete("tenantId");
~~~

`two` **không thay đổi** sau `put`; `edited` cũng không đổi sau `delete`. Nếu muốn giữ kết quả, phải dùng giá trị trả về.

~~~java
Context c = Context.of("mode", "old");
c.put("mode", "new"); // Không gán lại!
System.out.println(c.<String>get("mode")); // old

c = c.put("mode", "new");
System.out.println(c.<String>get("mode")); // new
~~~

### Đọc giá trị và xử lý khóa thiếu

~~~java
Mono<String> read = Mono.deferContextual(ctx -> {
    boolean present = ctx.hasKey("requestId");
    String requestId = ctx.getOrDefault("requestId", "unknown");
    return Mono.just(present + ":" + requestId);
});
~~~

- `ctx.get(key)`: lấy giá trị, có thể ném `NoSuchElementException` nếu khóa không tồn tại; dùng khi **hợp đồng** yêu cầu khóa phải có.
- `ctx.getOrDefault(key, fallback)`: lấy giá trị hoặc fallback, thích hợp với metadata không bắt buộc.
- `ctx.getOrEmpty(key)`: trả `Optional<T>`.
- `ctx.hasKey(key)`: kiểm tra tồn tại.
- `ctx.stream()` hoặc `size()` có thể dùng cho chẩn đoán, nhưng không nên tự in toàn bộ Context vì có thể chứa metadata nhạy cảm.

Lưu ý: **immutable ở cấp cấu trúc Context** không khiến các object value tự trở thành bất biến. Nếu đưa một `HashMap` mutable vào Context, hai phần cùng tham chiếu map đó vẫn có thể thay đổi trạng thái của nó. Ưu tiên giá trị nhỏ, bất biến như ID, enum, record, hoặc cấu trúc chỉ đọc.

## 4. Hai overload của `contextWrite`

Cả `Mono` và `Flux` đều hỗ trợ ghi Context ở ranh giới `contextWrite`.

### 4.1. `contextWrite(ContextView)`: thêm một tập key–value đã biết

~~~java
Mono<String> requestId = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId")))
    .contextWrite(Context.of("requestId", "REQ-42"));
~~~

`Context.of(...)` là một `ContextView`, nên overload này bổ sung các cặp key–value đã biết cho phần upstream.

Ngữ nghĩa chính xác: `contextWrite(ContextView additional)` **kết hợp** các cặp từ `additional` với Context của subscriber downstream, tạo Context mới cho upstream. Các key trong Context được thêm vào có thể **ghi đè cùng key của downstream** trong phạm vi upstream, chứ không vứt bỏ mọi key khác theo mặc định.

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId") + "/"
                 + ctx.<String>get("locale")))
    .contextWrite(Context.of("locale", "vi"))
    .contextWrite(Context.of("requestId", "REQ-42"));
~~~

Trong ví dụ, downstream cung cấp `requestId`, ranh giới gần nguồn bổ sung `locale`; phần đọc phía trên thấy cả hai. Nếu mỗi lần subscribe cần một request ID khác nhau, có thể tạo Publisher mới với `Context.of(...)` tương ứng hoặc dùng factory dạng `Function` cho việc tính metadata dựa vào Context downstream.

### 4.2. `contextWrite(Function<Context, Context>)`: chỉnh sửa dựa trên Context downstream

~~~java
Mono<String> message = Mono.deferContextual(ctx ->
        Mono.just("trace=" + ctx.<String>get("traceId")))
    .contextWrite(ctx -> ctx.put("traceId", "T-123"));
~~~

Lambda nhận Context downstream (dạng đối tượng không sửa trực tiếp) và **phải trả lại một Context mới** cho upstream. Vì `put` trả Context mới, biểu thức `ctx -> ctx.put(...)` là cách đúng.

Ví dụ ghi nhiều key:

~~~java
.contextWrite(ctx ->
    ctx.put("requestId", "R-1")
       .put("locale", "vi-VN")
       .put("channel", "api"))
~~~

Ví dụ xóa một key với ý định cụ thể:

~~~java
.contextWrite(ctx -> ctx.delete("temporaryFlag"))
~~~

Ví dụ thay đổi có điều kiện từ context downstream:

~~~java
.contextWrite(ctx -> {
    String current = ctx.getOrDefault("traceId", "not-set");
    return ctx.put("traceId", current + "-child");
})
~~~

Điểm quan trọng: **không trả `null`, không đánh rơi các khóa khác nếu không có chủ đích**. Vì function nhận context downstream, một lựa chọn như `ctx -> Context.of("traceId", "R")` làm mất các key khác của Context đã tồn tại. Thường nên dùng `ctx.put(...)`/`ctx.delete(...)` để preserve metadata thư viện khác.

### 4.3. Chọn overload nào?

| Trường hợp | Nên dùng |
| --- | --- |
| Gắn vài giá trị đã biết cho subscription | `contextWrite(Context.of("key", value))` |
| Ghi một key dựa trên dữ liệu downstream hiện có | `contextWrite(ctx -> ctx.put("key", ...))` |
| Xóa hoặc sửa có điều kiện | `contextWrite(ctx -> ctx.delete("key"))` / lambda |
| Cần merge nhiều key đang nằm trong một ContextView | `contextWrite(contextView)` hoặc `ctx.putAll(contextView)` |
| Cần lấy dữ liệu từ Context để tạo `onNext` | `Mono.deferContextual(...)`; **không phải** `contextWrite` |
| Cần đổi payload `T` thành `R` | `map`/`flatMap`; **không phải** `contextWrite` |

Một `contextWrite` không biến `Mono<T>` thành `Mono<Context>`: kiểu phần tử `T` của Publisher được giữ nguyên. Chỉ metadata có sẵn cho upstream thay đổi.

## 5. Chiều truyền Context: downstream → upstream

### 5.1. Hai chiều khác nhau trong một pipeline

~~~text
             Chiều dữ liệu (onNext): trên → dưới

     Mono.deferContextual(ctx -> ...)   [ĐỌC]
                    |
                  map(...)
                    |
      contextWrite(ctx -> ctx.put(...)) [GHI]
                    |
              subscribe()

             Chiều Context: dưới → trên
                 lúc subscribe
~~~

`subscribe()` ở cuối thiết lập chuỗi `Subscriber`. Khi subscription được xây dựng từ phía downstream lên upstream, mỗi `contextWrite` **đóng góp một Context mới** cho Subscriber phía trên nó. Khi dữ liệu đi xuống (`onNext`), Context **không phải** một object chạy theo mỗi item; các toán tử có thể truy vấn Context của subscriber bên dưới theo vị trí/quan hệ của mình.

Do đó, khi đọc mã từ trên xuống, bạn có thể thấy `contextWrite` ở cuối nhưng metadata đã sẵn sàng cho `deferContextual` phía trên.

### 5.2. Ghi ở dưới, đọc ở trên: đúng

~~~java
Mono<String> correct = Mono.deferContextual(ctx ->
        Mono.just("trace=" + ctx.getOrDefault("traceId", "missing")))
    .contextWrite(ctx -> ctx.put("traceId", "T-1"));

// Khi subscribe: trace=T-1
~~~

### 5.3. Ghi ở trên, đọc ở dưới: không nhìn thấy

~~~java
Mono<String> notVisible = Mono.just("payload")
    .contextWrite(ctx -> ctx.put("traceId", "T-1"))
    .flatMap(ignored ->
        Mono.deferContextual(ctx ->
            Mono.just("trace=" + ctx.getOrDefault("traceId", "missing"))));

// Khi subscribe: trace=missing
~~~

Ở đây `contextWrite` ở vị trí **upstream** của `flatMap`, nên nó chỉ thay đổi Context cho upstream của chính nó; phần `deferContextual` được tạo trong `flatMap` **ở downstream** không nhận key này.

Đây là lỗi vị trí phổ biến nhất: người học nghĩ Context được “gắn vào dữ liệu payload” rồi tự đi theo `onNext`. Thực tế **đặt toán tử ở đâu** quyết định phạm vi có hiệu lực.

### 5.4. Quy tắc vị trí nhanh

Nếu muốn **nguồn và phần lớn pipeline** đọc được request ID, đặt `contextWrite` gần cuối chuỗi, ngay trước điểm subscribe do ứng dụng hoặc framework quản lý:

~~~java
Mono<Response> response = service.process(command)
    .contextWrite(ctx -> ctx.put("requestId", requestId));
~~~

`Response`, `command`, `service` và `requestId` trong đoạn là tên nghiệp vụ minh họa, không phải chương trình độc lập. `contextWrite` không cần đặt ở mọi toán tử; một vị trí đúng đủ để cung cấp key cho upstream của phạm vi đó.

## 6. Khóa trùng và thứ tự nhiều lần `contextWrite`

### 6.1. “Gần chỗ đọc hơn” có thể ghi đè “xa hơn”

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("color")))
    .contextWrite(ctx -> ctx.put("color", "blue"))
    .contextWrite(ctx -> ctx.put("color", "red"));

// Kết quả: blue
~~~

Diễn tiến lúc subscribe (đọc **từ dưới lên**):

1. `contextWrite(color=red)` ở cuối tạo Context `red`.
2. `contextWrite(color=blue)` phía trên nhận Context `red`, tạo Context **mới** với `blue`.
3. `deferContextual` phía trên nữa đọc `blue`.

Do đó cùng một key có thể có giá trị khác nhau theo từng **đoạn của pipeline**, không có nghĩa mọi toán tử chia sẻ một mutable map toàn cục.

### 6.2. Hai đoạn đọc ở hai phía thấy hai giá trị

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just("upper=" + ctx.<String>get("key")))
    .contextWrite(ctx -> ctx.put("key", "NEAR_SOURCE"))
    .flatMap(upper ->
        Mono.deferContextual(ctx ->
            Mono.just(upper + ", lower=" + ctx.<String>get("key"))))
    .contextWrite(ctx -> ctx.put("key", "NEAR_SUBSCRIBER"));

// upper=NEAR_SOURCE, lower=NEAR_SUBSCRIBER
~~~

Giải thích: lần đọc ở đầu chuỗi nhìn Context đã được ghi đè **gần source**; lần đọc trong `flatMap` downstream nhìn key từ Context **gần subscriber cuối**. Không có lỗi race condition ở đây: mỗi vị trí có cái nhìn Context phù hợp với quan hệ subscriber.

### 6.3. Cảnh giác xung đột key giữa các thư viện

`Context` cho phép key là `Object`. Dùng chuỗi phổ biến như `"user"`, `"id"` hoặc `"token"` có thể đụng với key do thư viện khác dùng.

~~~java
final class TraceKeys {
    private TraceKeys() {}
    static final Object CORRELATION_ID = new Object();
}
~~~

Dùng cùng một **key object constant** để ghi và đọc trong cùng subsystem sẽ hạn chế va chạm với thư viện khác:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get(TraceKeys.CORRELATION_ID)))
    .contextWrite(ctx -> ctx.put(TraceKeys.CORRELATION_ID, "R-1"));
~~~

Lưu ý `TraceKeys` ở đây là class minh họa cần được định nghĩa cùng code ứng dụng; key Object dùng **identity** theo equals/hashCode của Java `Object`, nên không được tạo `new Object()` riêng cho mỗi lần đọc.

## 7. Ghi theo từng subscription, không ghi một lần cho cả Publisher

### 7.1. Một nguồn, hai subscriber, hai Context

~~~java
Mono<String> shared = Mono.deferContextual(ctx ->
    Mono.just("rid=" + ctx.<String>get("rid")));

Mono<String> first = shared.contextWrite(Context.of("rid", "REQ-A"));
Mono<String> second = shared.contextWrite(Context.of("rid", "REQ-B"));

// first phát rid=REQ-A
// second phát rid=REQ-B
~~~

`shared` là cùng một Publisher source, nhưng `first` và `second` là hai pipeline với Context được gắn cho **mỗi subscription**. Đừng đặt một biến mutable global để lưu `rid` mỗi lần request: người dùng A có thể đọc trúng rid của B.

### 7.2. Function được gọi theo vòng đời subscribe

~~~java
Mono<String> source = Mono.deferContextual(ctx ->
    Mono.just(ctx.<String>get("rid")));

Mono<String> prepared = source.contextWrite(ctx ->
    ctx.put("rid", java.util.UUID.randomUUID().toString())
);
~~~

Việc tính UUID nằm **bên trong** function của `contextWrite`, được thực hiện lúc tạo context của subscription, thay vì khi tạo biến `prepared`. Khi ứng dụng đăng ký lại với một subscription độc lập, function có thể tạo UUID mới.

Tuy nhiên, đừng suy ra “mỗi lần `onNext` có UUID riêng”: Context không phải cơ chế cấp giá trị theo từng item. Nếu muốn ID cho từng phần tử thì tạo trong `map`/`flatMap` hoặc toán tử dữ liệu tương ứng.

### 7.3. Ghi trong nhánh `flatMap`: phạm vi cục bộ

~~~java
Mono<String> nested = Mono.just("start")
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just("inner=" + ctx.<String>get("scope")))
        .contextWrite(ctx -> ctx.put("scope", "INNER")))
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + ", outer=" + ctx.<String>get("scope"))))
    .contextWrite(ctx -> ctx.put("scope", "OUTER"));

// Kết quả: inner=INNER, outer=OUTER
~~~

`contextWrite(scope=INNER)` áp dụng cho inner Publisher của `flatMap` đầu; nó không “đổi Context toàn cục” của các downstream/sibling branches. `contextWrite(scope=OUTER)` ở ngoài ảnh hưởng main subscription và được kế thừa ở nhánh con cho tới khi nhánh con ghi đè.

Nhận biết rõ phạm vi này giúp tránh việc một thành phần thư viện vô tình làm thay đổi metadata của thành phần khác.

## 8. Đọc lại để kiểm chứng: `deferContextual` và `transformDeferredContextual`

### 8.1. Đọc ở đầu nguồn với `Mono.deferContextual`

~~~java
Mono<String> publisher = Mono.deferContextual(ctx ->
        Mono.just("tenant=" + ctx.getOrDefault("tenantId", "public")))
    .contextWrite(Context.of("tenantId", "tenant-42"));
~~~

Mọi access phải diễn ra trong lambda ở **subscription time**, vì Context không phải một biến mà bạn lấy trước rồi lưu vào field tùy ý ở assembly time.

Nếu cần đọc trong một `flatMap`, cũng dùng `Mono.deferContextual` bên trong nhánh:

~~~java
Mono<String> decorated = Mono.just("payload")
    .flatMap(payload ->
        Mono.deferContextual(ctx ->
            Mono.just(payload + "@" + ctx.<String>get("requestId"))))
    .contextWrite(Context.of("requestId", "REQ-1"));
~~~

### 8.2. Đọc trên một Flux với `Flux.deferContextual`

~~~java
Flux<String> rows = Flux.deferContextual(ctx -> {
    String prefix = ctx.getOrDefault("prefix", "row");
    return Flux.range(1, 3)
        .map(i -> prefix + "-" + i);
}).contextWrite(Context.of("prefix", "record"));
~~~

Nguồn này phát `record-1`, `record-2`, `record-3`. `ContextView` có thể được chụp trong lambda và dùng bên trong những thao tác được tạo từ nhánh đó; tránh đặt một biến ngữ cảnh toàn cục rồi tái sử dụng qua nhiều subscription.

### 8.3. Đọc tại đoạn giữa bằng `transformDeferredContextual`

~~~java
Flux<String> output = Flux.range(1, 3)
    .transformDeferredContextual((flux, ctx) ->
        flux.map(i -> ctx.getOrDefault("prefix", "item") + "-" + i))
    .contextWrite(Context.of("prefix", "P"));
~~~

Khi subscribe, downstream nhận `P-1`, `P-2`, `P-3`. Toán tử này có ích khi muốn một đoạn xử lý đang ở giữa chuỗi truy cập `ContextView` theo subscription mà không cần tự biến mọi item thành một `Mono.deferContextual`.

**Phân biệt:** `transformDeferredContextual` là công cụ **đọc Context và xây biến đổi dữ liệu**; nó không phải lệnh ghi metadata. `contextWrite` vẫn giữ vai trò ghi.

## 9. Chương trình Java 17+ hoàn chỉnh, output xác định

Ví dụ dùng **Project Reactor Core 3.8.8**, JDK 17+, Maven. Chúng ta dùng nguồn hữu hạn, đồng bộ, không tự thay đổi scheduler để stdout ổn định.

Cấu trúc dự án:

~~~text
reactor-context-write-demo/
├── pom.xml
└── src/main/java/example/ContextWriteDemo.java
~~~

### 9.1. Tệp `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-context-write-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ContextWriteDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. Tệp `src/main/java/example/ContextWriteDemo.java`

~~~java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class ContextWriteDemo {

    public static void main(String[] args) {
        // A. Ghi bằng function, đọc phía trên.
        Mono<String> greeting = Mono.deferContextual(ctx ->
                Mono.just("Hello " + ctx.<String>get("name")))
            .contextWrite(ctx -> ctx.put("name", "Linh"));
        System.out.println("A: " + greeting.block());

        // B. Ghi quá cao: flatMap downstream không nhìn thấy.
        Mono<String> wrong = Mono.just("ready")
            .contextWrite(ctx -> ctx.put("trace", "T-1"))
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just("trace=" + ctx.getOrDefault("trace", "missing"))));
        System.out.println("B: " + wrong.block());

        // C. Đặt write phía dưới flatMap: đọc thấy.
        Mono<String> right = Mono.just("ready")
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just("trace=" + ctx.getOrDefault("trace", "missing"))))
            .contextWrite(Context.of("trace", "T-1"));
        System.out.println("C: " + right.block());

        // D. Hai write cùng key: đoạn gần source ghi đè.
        Mono<String> precedence = Mono.deferContextual(ctx ->
                Mono.just("region=" + ctx.<String>get("region")))
            .contextWrite(ctx -> ctx.put("region", "near"))
            .contextWrite(ctx -> ctx.put("region", "far"));
        System.out.println("D: " + precedence.block());

        // E. Hai subscription của cùng source có context riêng.
        Mono<String> shared = Mono.deferContextual(ctx ->
            Mono.just("rid=" + ctx.<String>get("rid")));
        System.out.println("E1: " +
            shared.contextWrite(Context.of("rid", "A")).block());
        System.out.println("E2: " +
            shared.contextWrite(Context.of("rid", "B")).block());

        // F. Ghi cho Flux, đọc từ đoạn giữa chuỗi.
        Flux<String> transformed = Flux.range(1, 3)
            .transformDeferredContextual((flux, ctx) ->
                flux.map(i ->
                    ctx.getOrDefault("prefix", "item") + "-" + i))
            .contextWrite(Context.of("prefix", "row"));
        System.out.println("F: " + transformed.collectList().block());

        // G. Xóa key ở một ranh giới cho upstream.
        Mono<String> removed = Mono.deferContextual(ctx ->
                Mono.just("has secret=" + ctx.hasKey("secret")))
            .contextWrite(ctx -> ctx.delete("secret"))
            .contextWrite(Context.of("secret", "old"));
        System.out.println("G: " + removed.block());

        // H. Ghi trong inner publisher chỉ ảnh hưởng inner.
        Mono<String> nested = Mono.just("start")
            .flatMap(value -> Mono.deferContextual(ctx ->
                    Mono.just("inner=" + ctx.<String>get("scope")))
                .contextWrite(ctx -> ctx.put("scope", "INNER")))
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(value + ", outer=" + ctx.<String>get("scope"))))
            .contextWrite(Context.of("scope", "OUTER"));
        System.out.println("H: " + nested.block());
    }
}
~~~

Chạy từ thư mục `reactor-context-write-demo`:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến:**

~~~text
A: Hello Linh
B: trace=missing
C: trace=T-1
D: region=near
E1: rid=A
E2: rid=B
F: [row-1, row-2, row-3]
G: has secret=false
H: inner=INNER, outer=OUTER
~~~

Diễn giải theo kết quả:

- **A:** `contextWrite` đứng phía dưới `deferContextual` nên key `name` đi tới chỗ đọc.
- **B:** write nằm phía trên `flatMap`, do đó inner read downstream không nhìn thấy `trace`.
- **C:** đổi lại vị trí giúp `flatMap` nhìn thấy `trace`.
- **D:** Context gần reader hơn ghi đè giá trị ở đoạn xa reader.
- **E:** mỗi subscription độc lập có metadata của riêng nó dù nguồn `shared` giống nhau.
- **F:** `transformDeferredContextual` đọc Context ở giữa một `Flux`.
- **G:** `delete` tạo Context mới không còn `secret` cho upstream.
- **H:** context của nhánh con không thay đổi context của nhánh downstream khác.

`block()` trong ví dụ chỉ giúp hàm `main` quan sát kết quả cuối. **Không** gọi `block()` trong thread xử lý non-blocking của Spring WebFlux; trong server, hãy trả hoặc ghép Publisher để framework xử lý subscription.

## 10. Spring WebFlux: gắn request ID với `contextWrite`

Một ví dụ điển hình là correlation ID để log hoặc trace nhiều lớp trong cùng HTTP request. Nếu dùng `WebFilter`, ta có thể bổ sung ID vào Context của pipeline được framework subscribe.

### 10.1. Gắn ở ranh giới request bằng `WebFilter`

Đây là **mã minh họa** thuộc một ứng dụng đã có dependency `spring-boot-starter-webflux`, các import Spring tương ứng và cấu hình bean; **không nằm trong chương trình Reactor Core độc lập ở mục 9**:

~~~java
@Configuration
public class RequestContextConfig {

    @Bean
    public WebFilter requestIdFilter() {
        return (exchange, chain) -> {
            String requestId = java.util.UUID.randomUUID().toString();

            return chain.filter(exchange)
                .contextWrite(ctx ->
                    ctx.put("requestId", requestId));
        };
    }
}
~~~

`chain.filter(exchange)` trả về Publisher đại diện cho việc xử lý request. `contextWrite` ở phía downstream của chain này cung cấp `requestId` cho các operator đọc Context ở bên trong phần upstream của request.

Trong một service reactive, có thể đọc bằng:

~~~java
public Mono<String> identifyRequest() {
    return Mono.deferContextual(ctx ->
        Mono.just("requestId=" +
            ctx.getOrDefault("requestId", "not-provided")));
}
~~~

Một controller có thể trả về `identifyRequest()` như một phần response, hoặc dùng request ID cho log/tracing. **Không gọi `subscribe()` riêng trong handler** để đọc Context, vì điều đó tạo subscription khác và có thể không kế thừa Context của HTTP request.

### 10.2. Tránh đặt metadata nhạy cảm tùy tiện

Context có thể đi qua nhiều toán tử/thư viện trên cùng subscription. Không xem Context như kho bí mật tự động được mã hóa hay có phân quyền. Với token hoặc danh tính:

- Chỉ đưa metadata đã xác thực và thực sự cần thiết; tránh log raw token/password.
- Dùng cơ chế bảo mật chính thức như **Reactive Spring Security Context** khi ứng dụng có Spring Security, thay vì tùy ý tạo khóa `"user"` hoặc `"role"` rồi coi đó là chứng thực.
- Giữ ownership key rõ ràng để tránh thư viện khác ghi đè ngoài ý muốn.
- Nếu bắt buộc mang dữ liệu có vòng đời/tài nguyên phức tạp, dùng cấu trúc dữ liệu và cơ chế cleanup phù hợp; đừng coi Context là một transaction hoặc resource scope đầy đủ.

### 10.3. Vì sao `contextWrite` hữu ích hơn `ThreadLocal` trong reactive pipeline?

Trong WebFlux, chuỗi công việc có thể chạy qua `publishOn`, `subscribeOn`, I/O callback và các thread khác nhau. `ThreadLocal` gắn với **thread**, nên nếu set trên thread HTTP ban đầu, một toán tử ở thread khác không tự thấy giá trị. Reactor Context gắn với **subscription**, giúp các operator Reactor đọc metadata đúng phạm vi theo `ContextView`.

~~~java
Mono<String> acrossThreads = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId")))
    .publishOn(reactor.core.scheduler.Schedulers.parallel())
    .contextWrite(ctx -> ctx.put("requestId", "R-42"));
~~~

Ở đây ví dụ đọc Context theo subscriber, nên chuyển thread không làm mất metadata của Context trong phạm vi đúng. **Không suy ra ThreadLocal cũng được truyền tự động.** Reactor/Micrometer có cơ chế context propagation riêng và có thể cấu hình automatic mode, nhưng đó là tích hợp khác; không phải tác dụng mặc định của một lời gọi `contextWrite` đơn lẻ.

## 11. Hạn chế và hành vi cần hiểu rõ

### 11.1. `contextWrite` không thay đổi giá trị phát ra

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
    .contextWrite(Context.of("traceId", "T-1"));
~~~

`numbers` vẫn phát 1, 2, 3. Dữ liệu Context không biến thành phần tử `onNext` mới và không khiến `Flux` trả thêm một giá trị `traceId`. Muốn payload chứa traceId thì phải tự tạo payload mới bằng `map`/`flatMap` kết hợp đọc Context.

### 11.2. Metadata đi ngược chiều, không lan xuống mọi nhánh một cách ma thuật

`contextWrite` chỉ ảnh hưởng **phần upstream được nối với subscription đó**. Nó không tự ảnh hưởng tới một dòng lệnh `repository.save(...).subscribe()` mà bạn gọi riêng biệt trong callback và không ghép nó thành nguồn con của Publisher.

Đối với `flatMap`, context của upstream/nhánh con được quyết định bởi subscriber của nhánh con; `contextWrite` bên trong nhánh này không tự biến đổi Context của phần main pipeline phía ngoài.

### 11.3. Context không thay thế quản lý concurrency

Một Context chứa `userId` không khiến hai tác vụ cùng user được chạy tuần tự, không cấp lock, không có transaction, không cấp backpressure và không quyết định Scheduler. Nó chỉ cung cấp key–value tại vị trí thích hợp trong pipeline.

### 11.4. `subscribeOn`/`publishOn` không phải phương pháp ghi Context

- `publishOn` chuyển thread xử lý tín hiệu downstream.
- `subscribeOn` thay đổi nơi thực hiện subscription/upstream tương ứng.
- `contextWrite` cung cấp Context cho upstream.
- `deferContextual` đọc Context tại subscribe.

Có thể kết hợp chúng trong cùng pipeline, nhưng mỗi toán tử phục vụ một mục tiêu riêng. Thay đổi Scheduler không sửa hoặc xóa Context theo định nghĩa, dù các tích hợp dựa trên ThreadLocal cần cầu nối thích hợp.

### 11.5. Ghi Context không tự tạo thông tin ở upstream đã hoàn tất

Nếu một thư viện đã **tách subscription** bằng `subscribe()` riêng, hoặc bạn đã thực hiện side effect **trước khi assembly**, đặt `contextWrite` sau đó không thể “gắn lại” metadata vào sự kiện đã chạy. Tương tự, đặt `Mono.just(blockingCall())` rồi ghi Context không trì hoãn được `blockingCall`: Java đánh giá đối số `just` ngay.

### 11.6. Lỗi, cancel và request không bị `contextWrite` đổi bản chất

`contextWrite` không nuốt `onError`, không đổi nguồn vô hạn thành hữu hạn, không tăng số request và không tạo subscriber độc lập. Nó cung cấp metadata theo quan hệ subscription; lifecycle và backpressure vẫn do Publisher/Subscriber/toán tử khác quản lý. Nếu upstream lỗi, lỗi vẫn truyền xuống như bình thường trừ khi có toán tử xử lý lỗi riêng.

### 11.7. Context không được truyền tự động qua mọi API bất kỳ

Với thư viện không tích hợp Reactor, callback từ `CompletableFuture`, Executor hoặc framework khác không tự hiểu `ContextView` của Reactor. Có thể cần truyền dữ liệu tường minh hoặc dùng cầu nối context propagation phù hợp. Đừng kỳ vọng `contextWrite` tự biến toàn bộ ứng dụng Java thành context-aware.

## 12. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Đặt `contextWrite` ở trên điểm cần đọc.** Reactor Context truyền từ subscriber cuối lên upstream; đặt write dưới reader hoặc trong nhánh đúng phạm vi.

**Lỗi 2 — Cho rằng `contextWrite` “thêm trường vào từng item”.** Không. Nó thay đổi Context, không đổi phần tử `T`. Muốn thay payload dùng `map`/`flatMap`.

**Lỗi 3 — Bỏ qua giá trị trả về của `Context.put`.** Context immutable: `ctx.put(...)` tạo Context mới. Trong `contextWrite(Function)` phải `return ctx.put(...)`.

**Lỗi 4 — Trả Context hoàn toàn mới, làm mất metadata của downstream.** `contextWrite(ctx -> Context.of("id", "X"))` có thể bỏ các khóa do thư viện khác đã gắn. Dùng `ctx.put(...)` để bảo toàn phần không thay đổi.

**Lỗi 5 — Dùng `ctx.get("key")` khi khóa có thể vắng.** Có thể nhận lỗi từ quá trình đọc Context. Dùng `getOrDefault`/`getOrEmpty` hoặc kiểm tra `hasKey` nếu key tùy chọn.

**Lỗi 6 — Nhầm “gần nguồn” và “gần subscriber”.** Hai lần contextWrite cùng key: giá trị ở write gần reader hơn, được thực thi sau khi có Context downstream, có thể ghi đè giá trị trước.

**Lỗi 7 — Lưu request ID trong field của singleton Spring service.** Nhiều request có thể đan xen và lộ/cướp ID. Dùng Context gắn subscription.

**Lỗi 8 — Coi Context là ThreadLocal.** `ThreadLocal` thay đổi theo thread, còn Context gắn với subscriber. Chuyển thread không tự vận chuyển mọi ThreadLocal; phải dùng cầu nối nếu cần.

**Lỗi 9 — Đặt `contextWrite` trong một inner `flatMap` rồi chờ mọi nhánh khác đổi theo.** Context ở nhánh con có phạm vi cục bộ; không phải một mutable map chung cho toàn luồng.

**Lỗi 10 — Dùng khóa chuỗi chung như `"id"` hoặc `"token"` trong thư viện.** Dễ va chạm với subsystem khác. Dùng constant/key object riêng và quy ước namespace.

**Lỗi 11 — Đưa object mutable vào Context rồi nghĩ nó an toàn concurrent.** Context immutable ở cấp bản đồ key–value, không copy sâu value; cần giữ value bất biến hoặc quản lý đồng bộ hóa riêng.

**Lỗi 12 — In toàn bộ Context vào log.** Có thể lộ thông tin nhạy cảm. Chỉ log những key được phép, với kỹ thuật che dữ liệu phù hợp.

**Lỗi 13 — Tự `subscribe()` trong controller để đọc metadata.** Subscription mới có Context riêng và dễ mất liên kết với request. Trả Publisher cho WebFlux xử lý.

**Lỗi 14 — Nghĩ contextWrite đồng nghĩa cấp quyền truy cập.** Metadata tự ghi không phải một bằng chứng xác thực. Xác thực/ủy quyền phải từ cơ chế tin cậy.

**Lỗi 15 — Dùng một context với key mutable để truyền dữ liệu giữa hai subscriber.** Mỗi subscriber có Context riêng; nếu cần cơ chế chia sẻ dữ liệu thật, thiết kế một nguồn/đối tượng chung có kiểm soát và hợp đồng cụ thể.

**Lỗi 16 — Kiểm tra thread name thay cho Context.** Thread có thể tái sử dụng; request ID nên đến từ `ContextView` hoặc công cụ context propagation, không suy ra từ tên thread.

## 13. Bài tập tự kiểm tra

1. `Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("k","?"))).contextWrite(ctx -> ctx.put("k","X"))` phát gì? **`X`.**
2. Nếu đổi thứ tự thành `Mono.just("a").contextWrite(ctx -> ctx.put("k","X")).flatMap(v -> Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("k","?"))))` thì phát gì? **`?`**, vì write nằm upstream của vị trí reader.
3. `Context c = Context.of("k","a"); c.put("k","b");` sau đó `c.get("k")` trả gì? **`a`**; không gán lại `c`.
4. Hai lần `contextWrite` ghi cùng key: phía dưới ghi `A`, phía trên ghi `B`. Reader ở phía trên cả hai thấy gì? **`B`**, do write gần reader ghi đè.
5. Có thể dùng `Mono.deferContextual` để lấy giá trị ngay khi assembly, trước subscribe không? **Không**. Nó cung cấp dữ liệu khi subscription xảy ra.
6. Một `Mono` chung được hai subscriber dùng với `Context.of("rid","A")` và `Context.of("rid","B")`. Chúng có bắt buộc thấy cùng rid không? **Không**; theo subscription, chúng thấy lần lượt A và B.
7. `contextWrite(Context.of("trace","T-1"))` có làm `Flux.range(1,3)` phát thêm phần tử thứ tư mang trace không? **Không**.
8. Trong WebFlux, nên gọi `subscribe()` trong controller để ghi Context cho service chạy ngầm không? **Không**. Ghép Publisher và dùng `contextWrite` ở ranh giới thích hợp để framework duy trì lifecycle.
9. `publishOn` đổi thread có khiến Reactor Context mất theo hợp đồng không? **Không**; Context gắn subscriber. Nhưng ThreadLocal không tự truyền cùng với nó.
10. `ctx -> Context.of("newKey","V")` có thể gây vấn đề gì? **Làm mất key sẵn có từ downstream**. Ưu tiên `ctx.put("newKey","V")`.
11. `ctx.get("missing")` có kết quả nào? **Có thể ném `NoSuchElementException`**, nên xử lý khóa thiếu khi được phép.
12. Ghi một `HashMap` mutable làm value của Context có làm map tự immutable không? **Không**.
13. Vì sao dùng key object tĩnh thay cho một chuỗi quá phổ biến? **Giảm nguy cơ trùng key giữa các thư viện/phân hệ**; phải dùng cùng constant để đọc và ghi.
14. Có thể dùng `contextWrite` để tự động xác thực một request bằng cách ghi `role=ADMIN` không? **Không**. Dữ liệu context tự ghi không phải bằng chứng xác thực; dùng Spring Security reactive và hợp đồng được tin cậy.

## 14. Tóm tắt và tài liệu tham khảo

- **Ghi:** `contextWrite(Context.of("key", value))` hoặc `contextWrite(ctx -> ctx.put("key", value))`.
- **Đọc:** `Mono.deferContextual`, `Flux.deferContextual` hoặc `transformDeferredContextual`.
- **Thời điểm:** Context được thiết lập khi subscribe, qua đường Subscriber/Subscription.
- **Chiều truyền:** từ **downstream lên upstream**; write phải nằm phía dưới đoạn cần đọc.
- **Bất biến:** `put` và `delete` trả Context mới; đừng bỏ giá trị trả về.
- **Isolation:** Context gắn với subscription, không gắn với thread hoặc dùng chung toàn ứng dụng.
- **Phạm vi:** key được ghi ở một inner branch không tự thay đổi tất cả branch khác.
- **Giới hạn:** contextWrite không biến đổi payload, không tự non-blocking hóa I/O, không bảo đảm truyền ThreadLocal hoặc xác thực người dùng.

Tài liệu chính thức:

1. [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): `Context`, `ContextView`, hai overload của `contextWrite`, chiều subscription, ví dụ vị trí/toán tử.
2. [Project Reactor API — Mono.contextWrite và deferContextual](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): chữ ký, ghi context cho upstream, tạo Mono từ Context.
3. [Project Reactor API — Flux.contextWrite và transformDeferredContextual](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): cách ghi và đọc trong Flux.
4. [Project Reactor API — Context](https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html) và [ContextView](https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html): bất biến, put/delete/getOrDefault/getOrEmpty, quy tắc đọc key.
5. [Project Reactor Reference — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): cầu nối bổ sung giữa Context và ThreadLocal (tùy dependency/mode).
6. [Spring Framework — WebFlux Web Filters](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html): vị trí WebFilter trong vòng đời request.
