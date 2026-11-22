# Cô lập ngữ cảnh trong các chuỗi con với Reactor Context

## 1. Bài toán: cùng một luồng, nhiều chuỗi con nhưng không được lẫn ngữ cảnh

Trong ứng dụng Spring WebFlux, một request có thể mang tenant ID, correlation ID, trace ID hoặc thông tin phục vụ logging/quan trắc. Bên trong service, một `Flux` có thể dùng `flatMap`, `concatMap` hoặc `switchIfEmpty` để tạo những `Mono`/`Flux` con. Ta muốn các chuỗi con **đọc được ngữ cảnh chung của request**, nhưng một thay đổi cục bộ trong một chuỗi con **không làm thay đổi ngữ cảnh của chuỗi cha hay các chuỗi con bên cạnh**.

Đó là ý nghĩa của **cô lập ngữ cảnh trong các chuỗi con (inner sequences)** với Reactor Context.

Ví dụ nghiệp vụ:

- Request thuộc tenant `shop-7`, có correlation ID `req-123`.
- Một pipeline xử lý ba mã đơn hàng.
- Mỗi mã có chuỗi con truy vấn dữ liệu, đặt thêm `operationId` riêng.
- Mọi chuỗi con được dùng chung `tenant` và `correlationId` của request.
- `operationId` của đơn hàng A không được chảy sang đơn hàng B.
- Khi chuỗi con kết thúc, chuỗi cha vẫn giữ ngữ cảnh ban đầu.

Mô hình mong muốn:

~~~text
                        Context của subscription cha
                       {tenant=shop-7, trace=req-123}
                                    |
                             concatMap/flatMap
                    +---------------+---------------+
                    |               |               |
                inner A         inner B          inner C
            +operation=A     +operation=B     +operation=C
               tenant=shop-7    tenant=shop-7    tenant=shop-7
               trace=req-123    trace=req-123    trace=req-123
                    |               |               |
                    +---------------+---------------+
                                    |
                     Cha vẫn chỉ có tenant và trace
                    Không bị đổi thành operation=A/B/C
~~~

**Kết luận cốt lõi:** Reactor Context gắn với **Subscriber**, không gắn với một thread toàn cục và không được truyền như một trường dữ liệu `onNext`. Những chỉnh sửa bằng `contextWrite` tạo **Context mới cho phần upstream của phạm vi tương ứng**. Vì vậy, một `contextWrite` chỉ nằm **bên trong publisher con** không làm ô nhiễm publisher cha hay các publisher con khác.

## 2. Reactor Context là gì?

Reactor cung cấp:

- **`reactor.util.context.Context`**: kho khóa–giá trị bất biến (immutable) dành cho thông tin liên quan subscription. Phương thức `put` và `delete` trả về Context mới, không sửa Context cũ.
- **`reactor.util.context.ContextView`**: giao diện chỉ đọc, dùng để lấy dữ liệu ở thời điểm pipeline được đăng ký/thực thi.
- **`contextWrite(...)`**: đặt hoặc biến đổi Context cho phần upstream của operator, khi subscription đi từ downstream lên upstream.
- **`Mono.deferContextual(...)` / `Flux.deferContextual(...)`**: đọc ContextView ở thời điểm subscription để tạo Publisher thích hợp.
- **`transformDeferredContextual(...)`**: truy cập ContextView cùng một publisher tại thời điểm subscribe khi muốn biến đổi pipeline theo Context.

Có thể hiểu Context như một `Map<Object, Object>` nhỏ dùng cho thông tin **orthogonal** với dữ liệu nghiệp vụ chính. Khác với một `HashMap` có thể sửa:

~~~java
Context first = Context.of("scope", "parent");
Context second = first.put("scope", "child");

// first vẫn chứa "parent"; second chứa "child".
~~~

Đây là ví dụ ngắn trong một phương thức Java có import `reactor.util.context.Context`. Nó diễn tả tính bất biến của **cấu trúc Context**. Lưu ý: nếu đặt **đối tượng mutable** (ví dụ `ArrayList`) làm value, việc thay đổi chính object ấy vẫn có thể bị các chuỗi khác quan sát; tính bất biến của Context **không tự deep-copy từng value**.

Reactor Context đặc biệt phù hợp với correlation ID, tenant/capability metadata, logging baggage và thông tin ngữ cảnh của từng request. Nó không phải nơi nên lưu toàn bộ request body, đối tượng khổng lồ, secret không được kiểm soát hoặc state mutable dùng chung.

## 3. Cơ chế quan trọng nhất: Context đi từ downstream lên upstream

Nhiều người mới học Reactor tưởng Context chảy theo giá trị `onNext` từ trên xuống dưới mã Java. Thực tế **subscription đi ngược** và Context được liên kết với từng Subscriber. Tại lúc subscribe, `contextWrite` cung cấp một Context mới cho phần pipeline nằm **trước nó**.

Ví dụ:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just("tenant=" + ctx.getOrDefault("tenant", "guest")))
    .contextWrite(ctx -> ctx.put("tenant", "shop-7"));

// result.block() -> "tenant=shop-7"
~~~

Trong biểu thức trên, `contextWrite` xuất hiện **sau** `deferContextual` theo thứ tự code, nhưng khi subscribe nó giúp phía upstream nhìn thấy `tenant=shop-7`.

Sơ đồ:

~~~text
assembly (chiều đọc source Java):
deferContextual(read tenant) ---> contextWrite(put tenant=shop-7)

subscription/context (chiều truyền nhu cầu từ downstream):
subscribe ---> contextWrite tạo Context ---> deferContextual đọc Context

data signals (onNext):
deferContextual phát "tenant=shop-7" ---> downstream
~~~

Đảo vị trí có thể thay kết quả:

~~~java
Mono<String> result = Mono.just("ok")
    .contextWrite(ctx -> ctx.put("tenant", "shop-7"))
    .flatMap(value -> Mono.deferContextual(ctx ->
        Mono.just(value + ":" + ctx.getOrDefault("tenant", "guest"))));

// result.block() -> "ok:guest"
~~~

`contextWrite` ở đây quá **cao** so với `flatMap` cần đọc. Nó chỉ thay Context cho upstream của chính mình (`Mono.just("ok")`); phần `flatMap` ở phía dưới không thấy giá trị đó. Không phải do Reactor “làm mất” tenant; nó đơn giản nằm **ngoài phạm vi** của thao tác ghi.

Cách sửa:

~~~java
Mono<String> result = Mono.just("ok")
    .flatMap(value -> Mono.deferContextual(ctx ->
        Mono.just(value + ":" + ctx.getOrDefault("tenant", "guest"))))
    .contextWrite(ctx -> ctx.put("tenant", "shop-7"));

// result.block() -> "ok:shop-7"
~~~

**Quy tắc thực hành:** khi muốn nhiều operator cùng đọc context, thường đặt `contextWrite` đủ **về phía downstream** để bao trùm phạm vi của những operator đó.

## 4. Chuỗi con nhận context cha như thế nào?

Một operator như `flatMap` nhận phần tử đầu vào rồi tạo Publisher con. Khi subscribe một Publisher con theo cách chuẩn của Reactor, nó nhận **Context hiện có tại ranh giới operator**. Publisher con có thể đọc các key từ Context này thông qua `deferContextual`.

~~~java
Mono<String> message = Mono.just("order-42")
    .flatMap(orderId ->
        Mono.deferContextual(ctx ->
            Mono.just(orderId + " belongs to " + ctx.get("tenant"))))
    .contextWrite(Context.of("tenant", "shop-7"));

// message.block() -> "order-42 belongs to shop-7"
~~~

Điều đó có nghĩa child **có thể kế thừa** các key của parent. Nhưng đây không phải một `Map` mutable global: child nhận view của Context trong **subscription scope của mình**.

### Nếu child viết cùng key thì sao?

~~~java
Mono<String> message = Mono.just("hello")
    .flatMap(word ->
        Mono.deferContextual(ctx ->
            Mono.just(word + ":" + ctx.get("scope")))
            .contextWrite(ctx -> ctx.put("scope", "child")))
    .contextWrite(ctx -> ctx.put("scope", "parent"));

// message.block() -> "hello:child"
~~~

Tại publisher con, `contextWrite` gần phần đọc hơn nên child nhìn thấy `scope=child`. **Không có thao tác cập nhật ngược lên parent**. Parent vẫn giữ `scope=parent`, và một child khác không tự nhìn thấy `scope=child`.

Hãy phân biệt:

- **Kế thừa**: child thấy giá trị sẵn có của parent nếu chưa bị shadow/ghi đè.
- **Shadow (ghi đè cục bộ)**: child tạo Context mới có giá trị mới dưới cùng key.
- **Không phát tán ngược**: thay đổi trong child không tự sửa Context của parent.
- **Không phát tán ngang**: sibling B không tự nhìn thấy Context mà sibling A ghi cục bộ.

Đây là cơ chế cô lập rất hữu ích khi cùng một request xử lý nhiều đối tượng nghiệp vụ.

## 5. Ví dụ kinh điển: hai flatMap, chỉ flatMap thứ hai có Context cục bộ

~~~java
Mono<String> result = Mono.just("Hello")
    .flatMap(text ->
        Mono.deferContextual(ctx ->
            Mono.just(text + " " + ctx.get("word"))))
    .flatMap(text ->
        Mono.deferContextual(ctx ->
            Mono.just(text + " " + ctx.get("word")))
            .contextWrite(ctx -> ctx.put("word", "Child")))
    .contextWrite(ctx -> ctx.put("word", "Parent"));

// result.block() -> "Hello Parent Child"
~~~

**Diễn giải từng bước:**

1. `contextWrite` cuối cùng tạo Context cha có `word=Parent` cho phần pipeline ở phía trên.
2. Trong `flatMap` thứ nhất, inner Publisher đọc `word` từ Context cha: tạo `Hello Parent`.
3. Trong `flatMap` thứ hai, inner Publisher có `contextWrite` riêng đặt `word=Child` cho **nội bộ inner đó**: tạo `Hello Parent Child`.
4. Context cục bộ của inner thứ hai **không quay lại sửa inner thứ nhất**.
5. Không phải `Hello Child Child` và cũng không phải `Hello Parent Parent`.

Đây là ví dụ đặc trưng được giải thích trong Reactor Core Reference Guide. Nó cho thấy Context **không đi kèm từng giá trị onNext**; thay đổi cục bộ ở inner không làm đổi Context của toàn tuyến.

## 6. Cô lập nhiều child với concatMap

Giả sử có hai order A và B, mỗi order có `operationId` riêng. Dùng `concatMap` để thứ tự đầu ra của ví dụ dễ dự đoán:

~~~java
Flux<String> orders = Flux.just("A", "B")
    .concatMap(orderId ->
        Mono.deferContextual(ctx -> Mono.just(
            orderId +
            " tenant=" + ctx.get("tenant") +
            " operation=" + ctx.get("operation")))
        .contextWrite(ctx -> ctx.put("operation", "read-" + orderId)))
    .contextWrite(ctx -> ctx.put("tenant", "shop-7")
                            .put("operation", "parent"));

// Khi subscribe, phát:
// A tenant=shop-7 operation=read-A
// B tenant=shop-7 operation=read-B
~~~

Các child đều đọc được `tenant=shop-7`. Nhưng mỗi child có `operation` khác nhau. Dù cùng một instance của Flux nguồn, value `read-A` **không chảy sang child B** và cũng không đổi parent.

Nếu dùng `flatMap` với các child bất đồng bộ, **thứ tự kết quả có thể thay đổi** do concurrency; sự cô lập Context vẫn theo phạm vi subscription, không dựa vào thứ tự kết quả. Nếu yêu cầu xử lý tuần tự theo thứ tự nguồn, chọn `concatMap`; nếu cần concurrency nhưng vẫn muốn sắp thứ tự đầu ra theo source, cân nhắc `flatMapSequential`. **Không dùng concatMap chỉ để “sửa rò rỉ Context”**; cơ chế scope không đòi hỏi chạy tuần tự.

## 7. Hai subscription độc lập từ cùng một Mono

Reactor Context gắn với **subscription**, nên hai request có thể dùng cùng một mô tả pipeline mà mang hai Context khác nhau:

~~~java
Mono<String> readTenant = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("tenant")));

String first = readTenant
    .contextWrite(Context.of("tenant", "tenant-A"))
    .block();

String second = readTenant
    .contextWrite(Context.of("tenant", "tenant-B"))
    .block();

// first = "tenant-A"
// second = "tenant-B"
~~~

Hai lần `block()` tạo hai subscription, không có biến tĩnh nào bị gán lại. `tenant-A` không phải default global được lưu cho subscription sau.

### Sự cô lập không phụ thuộc cùng hay khác thread

Hai pipeline reactive có thể chạy trên cùng một thread event-loop theo những khoảng thời gian khác nhau, hoặc chuyển thread khi dùng `publishOn`, `subscribeOn` hay scheduler của `Mono.delay`. Reactor Context được gắn với subscriber trong pipeline, chứ không phải tự lưu trong `ThreadLocal`. Nhờ đó, một pipeline dùng Context đúng cách không phải phụ thuộc thread bất biến để xác định tenant.

Tuy nhiên, điều đó **không bảo đảm các thư viện callback bất kỳ biết cách đọc Reactor Context**. Reactor Context cần được đọc qua những API của Reactor hoặc được truyền một cách tường minh tại boundary.

## 8. Full demo Java 17+ có thể biên dịch và chạy

Ví dụ dưới đây trình bày bốn quan sát độc lập:

1. Hai subscription nhìn thấy tenant khác nhau.
2. Các child có scope riêng và parent không đổi trước/sau child.
3. Thứ tự `contextWrite` quyết định phần pipeline nào nhìn thấy key.
4. Context vẫn có thể được đọc trong một công việc reactive có scheduler đổi thread.

### Cấu trúc và dependency

Yêu cầu **JDK 17+**, **Maven 3.9+**.

~~~text
reactor-context-isolation/
  pom.xml
  src/main/java/example/ContextIsolationDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-context-isolation</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.17</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/ContextIsolationDemo.java**

~~~java
package example;

import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class ContextIsolationDemo {
    private static final String TENANT = "tenant";
    private static final String SCOPE = "scope";

    public static void main(String[] args) {
        // 1) Cùng một Mono, hai subscription với Context khác nhau.
        Mono<String> probe = Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get(TENANT)));

        System.out.println("first=" +
            probe.contextWrite(Context.of(TENANT, "tenant-A")).block());
        System.out.println("second=" +
            probe.contextWrite(Context.of(TENANT, "tenant-B")).block());

        // 2) Cha có scope=root; mỗi child shadow scope riêng.
        Mono<String> parentProbe = Mono.deferContextual(ctx ->
            Mono.just("parent:" + ctx.get(SCOPE)));

        Flux<String> children = Flux.just("A", "B")
            .concatMap(id ->
                Mono.deferContextual(ctx ->
                    Mono.just(
                        "child-" + id +
                        ":tenant=" + ctx.get(TENANT) +
                        ",scope=" + ctx.get(SCOPE)))
                .contextWrite(ctx -> ctx.put(SCOPE, "local-" + id)));

        List<String> scopes = Flux.concat(
                parentProbe.flux(),
                children,
                parentProbe.flux())
            .contextWrite(Context.of(
                TENANT, "shop-7",
                SCOPE, "root"))
            .collectList()
            .block();

        System.out.println("scopes=" + scopes);

        // 3) contextWrite chỉ tác động lên phía upstream của nó.
        Mono<String> tooHigh = Mono.just("data")
            .contextWrite(ctx -> ctx.put(TENANT, "hidden"))
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just("downstream=" +
                        ctx.getOrDefault(TENANT, "none"))));

        Mono<String> correct = Mono.just("data")
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just("upstream=" +
                        ctx.getOrDefault(TENANT, "none"))))
            .contextWrite(ctx -> ctx.put(TENANT, "visible"));

        System.out.println(tooHigh.block());
        System.out.println(correct.block());

        // 4) ContextView đọc ở subscription rồi dùng trong async work.
        Mono<String> asynchronous = Mono.deferContextual(ctx ->
                Mono.delay(Duration.ofMillis(5))
                    .map(tick -> "async=" + ctx.<String>get(TENANT)))
            .contextWrite(Context.of(TENANT, "across-thread"));

        System.out.println(asynchronous.block());

        // 5) Một contextWrite ở inner không đổi inner khác.
        Mono<String> nested = Mono.just("Hello")
            .flatMap(s -> Mono.deferContextual(ctx ->
                Mono.just(s + " " + ctx.get("word"))))
            .flatMap(s ->
                Mono.deferContextual(ctx ->
                    Mono.just(s + " " + ctx.get("word")))
                .contextWrite(ctx -> ctx.put("word", "Child")))
            .contextWrite(ctx -> ctx.put("word", "Parent"));

        System.out.println(nested.block());
    }
}
~~~

### Chạy chương trình

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.ContextIsolationDemo
~~~

**Các dòng chương trình in** (không tính thông báo Maven/JVM nếu môi trường thêm):

~~~text
first=tenant-A
second=tenant-B
scopes=[parent:root, child-A:tenant=shop-7,scope=local-A, child-B:tenant=shop-7,scope=local-B, parent:root]
downstream=none
upstream=visible
async=across-thread
Hello Parent Child
~~~

Giải thích output:

- **first/second**: cùng source `probe` nhưng Context được cấp riêng cho hai subscription.
- **scopes**: trước và sau các child, parent vẫn `scope=root`; child A/B đọc tenant chung nhưng shadow scope khác nhau.
- **downstream=none**: `contextWrite` quá cao, không bao phủ phần đọc phía sau `flatMap`.
- **upstream=visible**: chuyển `contextWrite` xuống sau `flatMap` giúp phần đọc nhìn thấy key.
- **async=across-thread**: ngữ cảnh được lấy trong `deferContextual` rồi được sử dụng khi `Mono.delay` phát trên scheduler; không phải dựa vào một ThreadLocal của thread gốc.
- **Hello Parent Child**: ghi đè ở inner thứ hai không làm thay đổi kết quả của inner thứ nhất.

Các lời gọi `block()` chỉ dùng tại **ranh giới chương trình CLI để quan sát kết quả**. Trong controller WebFlux, thường nên **trả Mono/Flux** để framework subscribe, không gọi `block()` trên Netty event-loop.

## 9. contextWrite ở inner khác với contextWrite ở pipeline cha

Cùng nhìn hai mẫu:

**Mẫu A — Context chung cho cả chuỗi:**

~~~java
Flux<String> result = Flux.just("x", "y")
    .flatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(id + ":" + ctx.get("traceId"))))
    .contextWrite(ctx -> ctx.put("traceId", "request-1"));
~~~

Cả hai inner Publisher được tạo qua `flatMap` có thể đọc `traceId=request-1`. `contextWrite` này nằm ở phần downstream của toàn operator `flatMap`.

**Mẫu B — Context cục bộ cho từng chuỗi con:**

~~~java
Flux<String> result = Flux.just("x", "y")
    .flatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(id + ":" + ctx.get("scope")))
        .contextWrite(ctx -> ctx.put("scope", "local-" + id)))
    .contextWrite(ctx -> ctx.put("scope", "parent"));
~~~

Mỗi inner nhìn thấy scope riêng; parent không bị sửa. Kết quả dữ liệu là hai chuỗi `x:local-x` và `y:local-y`, nhưng **thứ tự phát có thể thay đổi** vì dùng `flatMap`. Nếu cần output cố định cho test, dùng `concatMap`.

**Điều cần phân biệt:** Context được **ghi theo scope của Subscriber**, không phải truyền qua việc gán biến `id`. Cả hai mẫu đều dùng một Publisher cha, nhưng vị trí của `contextWrite` quyết định phạm vi ghi.

## 10. Vì sao không thể “set Context” trong map rồi mong nó lan đi?

Một hiểu nhầm thường gặp là tạo Context mới bên trong `map`, như sau:

~~~java
Mono<String> wrong = Mono.just("x")
    .map(value -> {
        Context ignored = Context.of("scope", "new");
        return value;
    })
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("scope", "missing"))));
~~~

Đoạn này chỉ **tạo một object Context trong lambda** rồi bỏ đi. Nó không gắn Context đó vào Subscriber. Vì vậy phần `deferContextual` bên dưới vẫn đọc `missing` nếu không có `scope` từ nguồn khác.

Tương tự, kể cả nếu đang có một biến `Context old` và gọi `Context newer = old.put("scope","new")`, cũng không có cơ chế tự động đưa `newer` vào subscription đang chạy. `put` tạo một object mới; **chỉ cấu trúc pipeline qua `contextWrite` và các API propagation phù hợp mới quyết định Context được nhìn thấy ở đâu**.

Khi cần ngữ cảnh phụ thuộc một phần tử đang xử lý, hãy đưa giá trị phụ thuộc đó vào một **Publisher con** và đặt `contextWrite` cục bộ lên publisher con:

~~~java
Flux<String> result = Flux.just("A", "B")
    .concatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(ctx.get("scope") + ":" + id))
        .contextWrite(ctx -> ctx.put("scope", "op-" + id)));
~~~

Đây là pattern chính của cô lập ngữ cảnh theo từng item.

## 11. Tránh subscribe() thủ công trong chuỗi con

Một anti-pattern phổ biến là mở một subscription **độc lập** ngay trong `doOnNext` hoặc callback:

~~~java
Flux.just("A")
    .doOnNext(id -> {
        Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("traceId", "missing")))
            .subscribe(System.out::println); // subscription độc lập
    })
    .contextWrite(ctx -> ctx.put("traceId", "request-1"))
    .subscribe();
~~~

Đoạn trên dùng `subscribe()` thủ công bên trong callback; vì đây là subscription mới, nó **không tự được gắn** vào Context của subscription cha. Inner có thể in `missing` thay vì `request-1`. Ngoài chuyện mất Context, pattern này làm khó propagation của **error, cancellation, backpressure và completion**; framework không còn sở hữu công việc inner.

Cách ghép đúng:

~~~java
Flux<String> result = Flux.just("A")
    .flatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(id + ":" + ctx.get("traceId"))))
    .contextWrite(ctx -> ctx.put("traceId", "request-1"));

// Khi subscribe: A:request-1
~~~

`flatMap` subscribe Publisher con **như một phần của pipeline** nên các tín hiệu và Context được kết hợp theo contract của Reactor.

Đừng dùng một `Mono` hoặc `Flux` ở callback async rồi lập tức `subscribe()` chỉ để “kick off” tác vụ. Hãy trả Publisher đó cho operator thích hợp như `flatMap`, `concatMap` hoặc `then`.

## 12. ContextView: đọc đúng key và quản lý collision

Ví dụ đọc một key bắt buộc:

~~~java
Mono<String> value = Mono.deferContextual(ctx ->
    Mono.just(ctx.<String>get("tenantId")));
~~~

Nếu không tồn tại key này, `get` sẽ ném exception khi source được subscribe. Với key tùy chọn, dùng `getOrDefault` hoặc `getOrEmpty`:

~~~java
Mono<String> value = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("traceId", "not-provided")));
~~~

Các điểm cần lưu ý:

- Key và value là kiểu `Object`, nên **không có type safety tổng quát** cho mọi cặp key/value.
- Có thể dùng key kiểu riêng (typed/unique key object) hoặc tên có namespace rõ ràng để tránh va chạm giữa library.
- Nếu hai component cùng dùng `"tenant"` cho ý nghĩa khác nhau, một `contextWrite` có thể shadow giá trị của component kia.
- Với key bắt buộc, nên phát lỗi có ý nghĩa và test trường hợp thiếu key. Với key tùy chọn, dùng default an toàn.
- Không đặt `null` làm key/value; Context không được dùng để phát phần tử null.
- Không gửi toàn bộ Context vào log hay HTTP response; có thể chứa thông tin quan trắc hoặc bảo mật nội bộ.

Ví dụ dùng key object duy nhất để giới hạn collision:

~~~java
static final Object TENANT_KEY = new Object();

Mono<String> value = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get(TENANT_KEY)))
    .contextWrite(ctx -> ctx.put(TENANT_KEY, "shop-7"));
~~~

Đây là **đoạn minh họa trong một class Java**, không phải mã độc lập; cần định nghĩa TENANT_KEY ở class level. Bên ghi và bên đọc phải sử dụng **cùng một object key**.

## 13. Đừng nhầm immutable Context với việc cô lập object mutable

Nguy hiểm lớn nhất là đặt một object mutable có thể được chia sẻ vào Context:

~~~java
List<String> shared = new ArrayList<>();
Context base = Context.of("audit", shared);

Context childA = base.put("scope", "A");
Context childB = base.put("scope", "B");

// Không nên làm nếu cùng một List được cả A/B sử dụng:
((List<String>) childA.get("audit")).add("from-A");
System.out.println(childB.<List<String>>get("audit"));
// Có thể in [from-A] vì hai Context chứa cùng reference shared.
~~~

Đây là **đoạn minh họa**, cần import `java.util.List`, `ArrayList` và `Context`; cast mẫu không phải style khuyến khích. Dù `childA` và `childB` là các Context khác nhau, cùng key `audit` đang trỏ tới **một List**. Vì vậy **cô lập cấu trúc Context không đồng nghĩa tự động deep isolation của object**.

Nên:

- Dùng value bất biến như `String`, ID, enum hoặc Java record bất biến.
- Chọn context key ổn định, số lượng key nhỏ.
- Không chia sẻ container mutable giữa request/inner Publisher nếu chưa có đồng bộ và thiết kế vòng đời rõ ràng.
- Nếu thật sự cần state theo mỗi child, tạo **mỗi child một state riêng** qua `Mono.defer`/`Flux.defer` và chỉ đặt reference đó vào phạm vi child.
- Nếu dữ liệu là một phần của thuật toán xử lý item, ưu tiên truyền nó trong giá trị nghiệp vụ/record hơn là lạm dụng Reactor Context.

Ví dụ value bất biến phù hợp:

~~~java
record RequestMeta(String tenantId, String correlationId) {}

Mono<String> value = Mono.deferContextual(ctx -> {
    RequestMeta meta = ctx.get("requestMeta");
    return Mono.just(meta.tenantId() + "/" + meta.correlationId());
});
~~~

Đây là **đoạn bên trong một method hoặc class Java**, cần Java 17+ và Context chứa RequestMeta. Record giúp value dễ hiểu nhưng bản thân các field phải là loại bất biến nếu cần deep isolation.

## 14. Context và scheduler: tại sao ThreadLocal không thay thế trực tiếp được?

Trong servlet truyền thống, một request thường gắn với một thread trong suốt nhiều bước, nên có thể đặt request ID vào `ThreadLocal` hoặc MDC. Trong WebFlux, một thread Netty có thể phục vụ nhiều subscription luân phiên; pipeline còn có thể nhảy qua scheduler khác.

~~~text
Subscription A: event-loop-1 ---> parallel-2 ---> event-loop-1
Subscription B: event-loop-1 ---> boundedElastic-3
Subscription C: event-loop-1 ---> parallel-1

ThreadLocal chỉ là dữ liệu của từng Thread.
Reactor Context là dữ liệu logic theo Subscriber/subscription.
~~~

Không giả định `ThreadLocal.get()` trong một callback sau `delayElement`, `publishOn` hoặc I/O bất đồng bộ sẽ đọc được ThreadLocal của callback trước. Và không giả định vì hai request đang dùng chung event-loop thì chúng được phép có cùng tenant.

Reactor có cơ chế **context-propagation** tích hợp qua Micrometer Context Propagation, `contextCapture` và (khi được cấu hình) `Hooks.enableAutomaticContextPropagation()`. Các cơ chế này giúp tương tác với thư viện dùng ThreadLocal/MDC, nhưng **phụ thuộc dependency, registry, accessor và chế độ cấu hình**. Không tự suy ra ThreadLocal luôn được bridge trong mọi ứng dụng.

Với bài toán đọc tenant/trace trong một pipeline Reactor, cách minh bạch nhất thường là:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
    client.fetch(ctx.<String>get("tenantId")));
~~~

Đoạn này minh họa, giả định `client.fetch` trả `Mono<String>` và được thiết kế non-blocking. `deferContextual` lấy tenant theo subscription rồi **truyền tường minh** vào API của client. Không cần ThreadLocal.

## 15. Khi nào cần transformDeferredContextual?

Nếu muốn biến đổi một Flux dựa trên Context hiện tại, thay vì tự tạo `deferContextual` ở mỗi child, có thể dùng `transformDeferredContextual`:

~~~java
Flux<String> labels = Flux.just("A", "B")
    .transformDeferredContextual((source, ctx) ->
        source.map(id ->
            ctx.getOrDefault("tenant", "guest") + ":" + id))
    .contextWrite(ctx -> ctx.put("tenant", "shop-7"));

// Khi subscribe: "shop-7:A", "shop-7:B"
~~~

Đây là ví dụ biểu thức Java có import `Flux`, không phải class độc lập. Khác với `map` thông thường, transformDeferredContextual có thể truy cập `ContextView` tại thời điểm subscription. Nó hữu ích khi phép biến đổi cần đọc metadata của cả subscription.

Cần phân biệt:

- `Mono.deferContextual` / `Flux.deferContextual`: tạo nguồn phụ thuộc Context.
- `transformDeferredContextual`: biến đổi publisher hiện có với ContextView tại subscription.
- `contextWrite`: ghi/ghép Context cho phần upstream.
- `flatMap` và `concatMap`: ghép những Publisher con đã tạo một cách reactive.

Không cần dùng `transformDeferredContextual` trong mọi service; dùng đúng operator làm code rõ ràng nhất.

## 16. Áp dụng trong Spring WebFlux: tenant và correlation ID

Ở ranh giới HTTP, một WebFilter có thể xác định tenant từ **nguồn tin cậy** như authenticated principal hoặc cơ chế xác thực nội bộ, sau đó đưa giá trị vào Reactor Context của phần pipeline xử lý request.

**Minh họa kiến trúc** (cần các thành phần ứng dụng và imports):

~~~java
@Component
class TenantContextFilter implements WebFilter {
    static final String TENANT_KEY = "app.tenantId";

    private final TrustedTenantResolver tenantResolver;

    TenantContextFilter(TrustedTenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        return tenantResolver.resolve(exchange)
            .flatMap(tenantId ->
                chain.filter(exchange)
                    .contextWrite(ctx -> ctx.put(TENANT_KEY, tenantId)));
    }
}
~~~

Đây là **mẫu tích hợp**, chưa độc lập: cần định nghĩa `TrustedTenantResolver` với `Mono<String> resolve(ServerWebExchange)` và import `@Component`, `WebFilter`, `ServerWebExchange`, `WebFilterChain`, `Mono`. Không lấy tenant từ header tùy ý mà client có thể giả mạo nếu đó là cơ sở kiểm soát truy cập. Tùy cơ chế security, cần tương thích với cách Spring Security quản lý Reactor Context và thứ tự filters.

Ở service:

~~~java
Mono<Order> loadOrder(String orderId) {
    return Mono.deferContextual(ctx -> {
        String tenant = ctx.get(TenantContextFilter.TENANT_KEY);
        return orderRepository.findByTenantAndId(tenant, orderId);
    });
}
~~~

Đây là ví dụ giả định `Order` và `orderRepository` tồn tại. Đối với một request xử lý nhiều đơn hàng, có thể thêm metadata cục bộ theo inner:

~~~java
Flux<Order> loadOrders(Flux<String> orderIds) {
    return orderIds.flatMap(orderId ->
        loadOrder(orderId)
            .contextWrite(ctx ->
                ctx.put("app.operationId", "load:" + orderId)));
}
~~~

Mỗi inner có operation ID riêng. Nhưng nó không được phép thay đổi tenant của request cha hoặc sibling; đồng thời repository luôn cần **dùng tenant từ nguồn đáng tin cậy để lọc dữ liệu**, không coi chỉ việc có Context là đủ kiểm soát quyền.

**Đừng truyền nguyên Context ra network.** Nếu cần propagation sang downstream HTTP service, nên lấy những trường được phép (ví dụ trace/correlation ID) và gắn vào headers qua WebClient filter/client adapter theo contract, có kiểm soát dữ liệu và security.

## 17. Những điều cần biết khi dùng cache, share và hot source

Cô lập theo subscriber **không đồng nghĩa** một pipeline có cache/share luôn thực thi toàn bộ source riêng cho từng subscriber.

Ví dụ:

~~~java
Mono<String> once = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("tenant")))
    .cache();
~~~

Nếu object `once` này được chia sẻ cho nhiều request khác tenant, `cache()` có thể khiến nguồn chỉ được subscribe/tính kết quả cho một subscription và phát lại kết quả cho subscriber sau. Đây là rủi ro **cross-tenant data leakage** nếu nội dung phụ thuộc tenant mà cache không được khóa theo tenant.

Không mặc định rằng mọi source hot, `share` hay `cache` đều sẽ tạo Context mới tương ứng với mỗi subscriber ở tầng upstream. Phạm vi subscription thật sự, điểm share và cách cache operator hoạt động rất quan trọng.

Biện pháp:

- Đặt Context-sensitive computation **trong subscription scope phù hợp**, không cache toàn ứng dụng một kết quả chứa dữ liệu theo request.
- Nếu cần cache, thiết kế **cache key bao gồm tenant và các tham số quyền truy cập cần thiết**, cùng chính sách xóa/hết hạn.
- Với nguồn hot, xác định Context của **upstream subscription thực sự**, đừng giả định Context của mọi downstream subscriber được tổng hợp lại.
- Test bằng nhiều tenant/subscriber song song thay vì chỉ test một request.
- Không lưu secret hay dữ liệu người dùng vào shared mutable context value.

## 18. Kiểm thử isolation với StepVerifier

Thư viện `reactor-test` cung cấp `StepVerifier`; để test Reactor Context, thêm dependency test tương ứng phiên bản reactor-core:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.6.17</version>
    <scope>test</scope>
</dependency>
~~~

Ví dụ kiểm thử, cần đặt trong phương thức test đã import `reactor.test.StepVerifier`, `Flux`, `Mono`, `Context`:

~~~java
Flux<String> sequence = Flux.just("A", "B")
    .concatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(id + ":" + ctx.<String>get("scope")))
        .contextWrite(ctx -> ctx.put("scope", "inner-" + id)))
    .contextWrite(Context.of("scope", "parent"));

StepVerifier.create(sequence)
    .expectNext("A:inner-A", "B:inner-B")
    .verifyComplete();
~~~

Có thể dùng `StepVerifierOptions.withInitialContext(...)` để cấp context ngay tại subscriber cho bài kiểm thử:

~~~java
StepVerifier.create(
        Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("tenant"))),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("tenant", "tenant-A")))
    .expectNext("tenant-A")
    .verifyComplete();
~~~

Đây cũng là đoạn test minh họa cần import `reactor.test.StepVerifierOptions`. Sử dụng initial Context trong test giúp xác nhận behavior của library/service khi consumer chính là bên cấp Context, không phải lúc nào cũng cần đặt `contextWrite` vào production pipeline.

Các test nên bao gồm:

1. Cùng Publisher, hai subscriber với Context khác nhau không nhìn thấy dữ liệu của nhau.
2. Một child ghi đè key, parent và sibling vẫn giữ giá trị cũ.
3. Child không ghi đè key thì kế thừa key từ parent.
4. Khi thiếu key bắt buộc, publisher báo lỗi dự đoán được; optional key có default.
5. Nhiều child thực thi đồng thời với flatMap không trộn operation ID.
6. Scheduler switch không làm logic phụ thuộc ThreadLocal một cách tình cờ.
7. Tình huống cache/share có nguy cơ phát lại kết quả theo tenant khác.
8. Không xuất dữ liệu nhạy cảm trong log hoặc response.

Nếu test với `flatMap` async, không khẳng định thứ tự bằng `expectNext(A, B)` khi thứ tự có thể khác; chọn `concatMap` cho ví dụ cần thứ tự hoặc kiểm tra tập dữ liệu theo cách phù hợp.

## 19. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Xem Reactor Context như một HashMap mutable chung cho cả ứng dụng | Context gắn với Subscriber, `put` tạo instance mới | Dùng `contextWrite` trong phạm vi pipeline cần thiết |
| Cho rằng contextWrite ảnh hưởng mọi operator phía dưới | Ghi Context tác động lên **upstream** của vị trí operator | Đặt contextWrite về phía downstream của các phép đọc |
| Ghi contextWrite ở inner rồi mong parent đổi | Inner chỉ thay Context của subscription con | Ghi ở cha nếu muốn chia sẻ cho cả nhánh |
| Ghi operation ID ở parent cho mọi item | Các child sẽ cùng thấy một ID, không cô lập theo item | Đặt contextWrite trong Publisher con do flatMap/concatMap tạo |
| Gọi subscribe() thủ công trong callback | Subscription mới không tự kế thừa Context cha; mất lifecycle | Trả Publisher con và ghép bằng flatMap/concatMap |
| Dùng ThreadLocal làm nguồn chân lý tenant trong pipeline async | Thread có thể đổi hoặc phục vụ nhiều subscription | Reactor Context hoặc truyền tham số tường minh |
| Đặt List mutable dùng chung trong Context | Immutable map không làm List thành immutable | Dùng value bất biến hoặc tạo state riêng per child |
| Ghi đè key cùng tên giữa các thư viện | Collision và shadow ngoài ý muốn | Namespace/typed key và hợp đồng rõ ràng |
| Dùng get(key) khi key có thể không có | Thiếu key dẫn đến lỗi runtime | getOrDefault/getOrEmpty hoặc validation |
| Dùng cache() cho kết quả phụ thuộc tenant | Cache có thể phát lại dữ liệu sai phạm vi | Cache theo tenant/key đúng hoặc không share |
| Tưởng flatMap luôn giữ thứ tự A, B, C | FlatMap có thể chạy inner đồng thời, order khác | ConcatMap nếu cần thứ tự, tách yêu cầu concurrency/isolation |
| Nhúng toàn Context vào header/log | Có thể lộ dữ liệu không dành cho client | Chỉ truyền key được phép và redaction |
| Dùng Context để thực hiện authorization mà không validate identity | Key có thể bị cấp sai ở boundary | Lấy tenant/identity từ nguồn tin cậy và kiểm tra quyền |
| Tưởng mọi thư viện ngoài Reactor đều tự thấy Context | Context không tự được biết bởi mọi callback/library | Đọc rồi truyền rõ ràng hoặc dùng bridge chuẩn |

## 20. Bài tập tự kiểm tra

**Câu 1.** Khi gọi `contextWrite(ctx -> ctx.put("scope", "child"))` trong Publisher của một `flatMap`, Publisher cha có chuyển thành scope=child không?

**Không.** Context mới có phạm vi upstream của Publisher con đó. Cha và sibling không tự bị cập nhật.

**Câu 2.** Nếu cùng một `Mono.deferContextual` được subscribe hai lần với tenant A và tenant B, nó phải trả tenant nào?

**Mỗi lần trả tenant tương ứng với Context của subscription đó**, trừ khi pipeline được thay đổi bằng cache/share hoặc cách tạo nguồn có semantics khác.

**Câu 3.** Vì sao đặt contextWrite trước flatMap có thể khiến inner không đọc được key?

Vì Context được truyền từ downstream lên upstream. contextWrite chỉ thay Context của các operator **ở phía trên nó**, không bắt buộc ảnh hưởng phần flatMap nằm sau nó.

**Câu 4.** Vì sao không nên dùng `doOnNext(id -> mono.subscribe())` để tạo child nghiệp vụ?

Vì subscribe() đó tạo **subscription độc lập**, không mặc nhiên nhận Context/lifecycle của parent, khiến error/cancel/backpressure không còn được ghép đúng.

**Câu 5.** Context bất biến có bảo đảm value kiểu `ArrayList` không bị các child sửa chung không?

**Không.** Hai Context có thể trỏ tới cùng một List mutable. Cần dùng value immutable hoặc state riêng.

**Câu 6.** Một ứng dụng WebFlux có thể đọc tenant qua ThreadLocal cố định sau `publishOn` không?

**Không nên giả định** như vậy. Dùng Reactor Context hoặc cấu hình context propagation phù hợp và kiểm thử trong môi trường thực.

**Câu 7.** Khi muốn child A/B giữ được tenant chung nhưng có operation ID riêng, đặt hai key ở đâu?

Đặt **tenant tại phạm vi request/parent**, còn **operation ID ở Publisher con** bên trong flatMap/concatMap.

**Câu 8.** Cần xử lý nhiều child song song nhưng yêu cầu operation ID không bị lẫn. Có bắt buộc dùng concatMap không?

**Không.** Cô lập Context theo Publisher con vẫn áp dụng với flatMap. ConcatMap chỉ là lựa chọn khi cần thứ tự và giới hạn thực thi tuần tự.

**Câu 9.** Context có tự biến thành HTTP header khi gọi WebClient không?

**Không.** Cần một adapter/filter đọc các key được phép và gắn chúng vào request theo hợp đồng; phải chú ý thông tin nhạy cảm.

**Câu 10.** Vì sao việc cache một Mono đọc tenant trong Context có thể nguy hiểm?

Vì source có thể chỉ chạy cho một subscription và phát lại cùng kết quả cho nhiều subscriber; nếu kết quả phụ thuộc tenant, đó là rủi ro lẫn dữ liệu giữa request.

## 21. Tài liệu tham khảo

- [Project Reactor Reference Guide — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): định nghĩa Context, hướng propagation, contextWrite, deferContextual và ví dụ cô lập trong flatMap.
- [Reactor Core API — Context](https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html): immutability, các phương thức put, delete và putAll.
- [Reactor Core API — ContextView](https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html): đọc get, getOrDefault, getOrEmpty và hasKey.
- [Reactor Core Reference Guide — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): phân biệt Reactor Context với ThreadLocal và các chế độ propagation.
- [Reactor Core API — Mono](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html) và [Flux](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html): deferContextual, contextWrite và các toán tử tạo inner Publisher.
- [Reactor Test API — StepVerifierOptions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html): thiết lập initial Context khi test.

**Ghi nhớ:** Reactor Context là **kho metadata bất biến gắn với Subscriber**, truyền theo chiều **subscription từ downstream lên upstream**. `contextWrite` tạo Context mới trong phạm vi nơi nó được đặt; khi nằm **bên trong một Publisher con**, nó không tự sửa Context của parent hay sibling. `deferContextual` cho phép đọc metadata tại thời điểm subscription. Dùng Context để mang tenant/trace chung, đặt metadata riêng cho từng inner bằng contextWrite cục bộ, tránh subscribe thủ công, tránh state mutable dùng chung và luôn kiểm tra ranh giới cache/share, scheduler cũng như HTTP security.