# Truyền mã tương quan và thông tin yêu cầu bằng Reactor Context

## 1. Vì sao ứng dụng WebFlux cần Reactor Context?

Trong Spring WebFlux, một HTTP request có thể đi qua WebFilter, controller, service, database, WebClient và nhiều toán tử Reactor. Trong quá trình đó, các callback không nhất thiết chạy trên cùng một thread. Nếu dùng ThreadLocal hoặc SLF4J MDC theo cách thủ công để giữ **correlation ID** (mã tương quan), một callback chạy sau **publishOn**, **subscribeOn** hoặc I/O bất đồng bộ có thể không nhìn thấy metadata ban đầu.

**Reactor Context** là cơ chế truyền metadata **theo subscription**, giúp những thành phần trong cùng một chuỗi reactive có thể đọc correlation ID và một số thông tin request mà không phải thêm tham số vào từng method.

Ví dụ: request HTTP mang mã **REQ-2026-A**, đi qua handler lấy thông tin đơn hàng, gọi dịch vụ vận chuyển rồi ghi lỗi. Chúng ta muốn log tại từng tầng mang cùng ID để dễ tìm toàn bộ sự kiện liên quan. Reactor Context cho phép gắn ID ở một ranh giới có chủ đích và đọc lại ở những operator nằm trong đúng phạm vi.

Bài học này giúp bạn:

- Hiểu **Context**, **ContextView**, **contextWrite** và **deferContextual**.
- Giải thích cách Context đi từ **downstream tới upstream** khi subscribe.
- Truyền correlation ID qua service, nested Publisher, scheduler và pipeline bất đồng bộ.
- Tạo ID tại **WebFilter**, đọc ở service và gắn lên **WebClient outbound header**.
- Phân biệt Reactor Context với **ThreadLocal**, **MDC**, Micrometer Context Propagation và distributed tracing.
- Thiết kế metadata an toàn, kiểm thử sự cô lập giữa các request và tránh mất Context do subscribe thủ công.

## 2. Context là dữ liệu của subscription, không phải dữ liệu của thread

Những khái niệm chính:

| Thành phần | Mục đích |
| --- | --- |
| **reactor.util.context.Context** | Bản đồ key-value bất biến về cấu trúc, gắn với Subscriber |
| **ContextView** | Giao diện chỉ đọc; dùng để truy cập metadata từ pipeline |
| **contextWrite(ContextView)** | Ghép một ContextView vào Context của Subscriber ở phía downstream rồi tạo Context mới cho upstream |
| **contextWrite(Function<Context,Context>)** | Biến đổi Context hiện có, thường dùng **ctx.put(key,value)** |
| **Mono.deferContextual** | Tạo Mono khi subscribe, có quyền đọc ContextView hiện tại |
| **Flux.deferContextual** | Tương tự với Flux |
| **transformDeferredContextual** | Dùng ContextView khi biến đổi một pipeline tại thời điểm subscription |
| **Signal.getContextView()** | Đọc Context khi quan sát tín hiệu qua operator phù hợp như doOnEach |

**Context bất biến:** **ctx.put(KEY, value)** trả một Context mới; nó không sửa object ctx trước đó. Nhưng nếu value là một object mutable, thuộc tính của object đó vẫn có thể bị sửa. Vì thế nên giữ các giá trị Context nhỏ và bất biến.

**Từng subscriber có Context riêng:** cùng một Mono định nghĩa sẵn có thể được subscribe nhiều lần với correlation ID khác nhau. Điều này tránh lẫn metadata giữa hai HTTP request, miễn là ứng dụng không dùng một mutable static variable bên ngoài để giữ ID.

**Không phụ thuộc thread:** Context là metadata của quan hệ subscription và được truyền qua các operator Reactor. Việc chuyển thread bằng **publishOn** không tự làm mất Reactor Context, nhưng có thể làm mất dữ liệu ThreadLocal chưa được bridge.

**Không tự vượt ranh giới tiến trình:** Reactor Context ở service A không tự truyền tới service B qua mạng. Muốn liên kết request xuyên dịch vụ, phải truyền correlation ID qua header HTTP, message metadata hoặc cơ chế tracing được cấu hình.

## 3. Chiều lan truyền Context và vị trí contextWrite

Dữ liệu chạy theo chiều upstream → downstream. Việc khởi tạo subscription, bao gồm truyền Context, đi theo chiều ngược lại: từ downstream → upstream.

~~~text
                  onNext / onError / onComplete ↓

Mono.deferContextual(view -> ...)
            │
        .map(...)
            │
      .flatMap(...)
            │
.contextWrite(ctx -> ctx.put(KEY, "REQ-101"))
            │
          Subscriber

                  subscription / Context ↑
~~~

Vì vậy đoạn sau hợp lệ:

~~~java
Mono<String> result = Mono.deferContextual(view ->
        Mono.just("cid=" + view.get("cid"))
    )
    .contextWrite(ctx -> ctx.put("cid", "REQ-101"));
~~~

Kết quả sau khi subscribe:

~~~text
cid=REQ-101
~~~

Ngược lại, cách đặt dưới đây làm người đọc không thấy giá trị vừa được ghi:

~~~java
Mono<String> result = Mono.just("item")
    .contextWrite(ctx -> ctx.put("cid", "REQ-101"))
    .flatMap(item -> Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("cid", "MISSING"))
    ));
~~~

Operator **flatMap** nằm phía downstream của lần contextWrite. Vì Context đi từ downstream lên upstream, Context mới chỉ tác động lên phần **Mono.just("item")** phía trên. flatMap đọc Context của chính nhánh downstream, cho ra **MISSING**.

**Quy tắc nhớ:** **contextWrite thường đặt phía dưới nơi cần đọc trong biểu thức chain**. Nó ảnh hưởng các operator **upstream**; không phát một giá trị metadata theo chiều onNext.

### 3.1. Hai lần ghi cùng key

~~~java
Mono<String> result = Mono.deferContextual(view ->
        Mono.just(view.get("cid"))
    )
    .contextWrite(ctx -> ctx.put("cid", "INNER"))
    .contextWrite(ctx -> ctx.put("cid", "OUTER"));
~~~

Kết quả là **INNER**. Khi subscription đi lên, OUTER được ghi trước, rồi contextWrite gần người đọc hơn tạo Context với INNER. Nên có **một chính sách thống nhất** để tránh service con vô tình ghi đè correlation ID của request.

### 3.2. Context của nhánh con được cô lập

~~~java
Mono<String> result = Mono.just("A")
    .flatMap(value ->
        Mono.deferContextual(view ->
            Mono.just(value + view.getOrDefault("cid", "?"))
        )
        .contextWrite(ctx -> ctx.put("cid", "INNER"))
    )
    .flatMap(value ->
        Mono.deferContextual(view ->
            Mono.just(value + view.getOrDefault("cid", "?"))
        )
    );
~~~

Nhánh flatMap đầu thấy INNER; nhánh kế tiếp không tự thừa hưởng lần ghi cục bộ của nhánh trước. Nếu không có cid ở Context bên ngoài, kết quả là **AINNER?**. Context cục bộ của một inner Publisher không tự thay đổi Context ở nhánh ngoài.

## 4. Đọc Context an toàn và tổ chức key

Một thành phần có thể được gọi bởi HTTP request hoặc bởi job không có HTTP context. Khi key là tùy chọn, dùng **getOrDefault**:

~~~java
Mono<String> readCid = Mono.deferContextual(view -> {
    String cid = view.getOrDefault("app.correlationId", "unknown");
    return Mono.just("cid=" + cid);
});
~~~

Các phương thức đọc:

- **view.get(key)**: lấy giá trị nếu key có mặt; thiếu key thì báo lỗi.
- **view.getOrDefault(key, defaultValue)**: trả default khi thiếu key.
- **view.hasKey(key)**: kiểm tra key có mặt.
- **view.getOrEmpty(key)**: nhận Optional cho giá trị có thể vắng mặt.
- **Context.of(...)**: tạo Context có một số cặp key-value.
- **Context.empty()**: tạo Context rỗng.
- **ctx.put(key,value)** và **ctx.delete(key)**: trả Context mới, không sửa tại chỗ.

Context không chấp nhận key hoặc value null. Đừng dùng null để diễn tả “chưa có request”.

### Key dùng chung

Key String có thể dễ va chạm giữa thư viện hoặc module. Có thể dùng enum hoặc object được định nghĩa tập trung:

~~~java
public enum RequestContextKey {
    CORRELATION_ID,
    REQUEST_METHOD
}
~~~

Các nơi đọc và ghi phải dùng **chính xác cùng key**, không tạo Object riêng dù tên hiển thị giống nhau. Không ghi đè các key của Spring Security hoặc tracing nếu không hiểu hợp đồng của chúng.

### Nên lưu dữ liệu nào?

Hợp lý: correlation ID, request ID, HTTP method, mã locale, route template đã chuẩn hóa, metadata nhỏ bất biến. Nếu cần nhiều trường có liên hệ, cân nhắc một **record** bất biến.

Không nên tự đặt vào Context: raw Authorization header, mật khẩu, access token, request body, toàn bộ ServerWebExchange, dữ liệu cá nhân không cần thiết, object lớn hoặc mutable shared state. Context là cơ chế truyền metadata, không phải nơi lưu trạng thái nghiệp vụ bền vững.

**Correlation ID không chứng minh danh tính.** Giá trị do client cung cấp có thể bị giả mạo. Không sử dụng nó làm căn cứ cấp quyền hoặc xác định tenant. Dùng hệ thống xác thực và security context chính thức cho mục đích bảo mật.

## 5. Java 17+: ví dụ Maven chạy được

Chương trình sau sử dụng **Reactor Core 3.6.6** và minh họa các điểm quan trọng: Context theo từng subscription, sự ưu tiên của contextWrite, giá trị sau publishOn, missing key và nested Publisher. Đầu ra được chọn để không phụ thuộc tên thread hoặc thời gian scheduler.

Tạo cấu trúc:

~~~text
reactor-context-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── ReactorContextDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-context-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
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

Tệp **src/main/java/ReactorContextDemo.java**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {

    enum Key {
        CORRELATION_ID,
        REQUEST
    }

    static Mono<String> describe() {
        return Mono.deferContextual(view ->
            Mono.just(
                "cid=" + view.getOrDefault(Key.CORRELATION_ID, "none")
                + "; request=" + view.getOrDefault(Key.REQUEST, "none")
            )
        );
    }

    public static void main(String[] args) {
        System.out.println("=== 1. Two subscriptions ===");

        Mono<String> definition = describe();

        System.out.println(
            definition.contextWrite(
                Context.of(
                    Key.CORRELATION_ID, "CID-A",
                    Key.REQUEST, "GET /orders"
                )
            ).block()
        );

        System.out.println(
            definition.contextWrite(
                Context.of(
                    Key.CORRELATION_ID, "CID-B",
                    Key.REQUEST, "POST /orders"
                )
            ).block()
        );

        System.out.println("=== 2. Position ===");

        System.out.println(
            Mono.deferContextual(view ->
                    Mono.just(
                        "closest=" + view.getOrDefault(
                            Key.CORRELATION_ID, "missing"
                        )
                    )
                )
                .contextWrite(ctx ->
                    ctx.put(Key.CORRELATION_ID, "INNER")
                )
                .contextWrite(ctx ->
                    ctx.put(Key.CORRELATION_ID, "OUTER")
                )
                .block()
        );

        System.out.println(
            Mono.just("value")
                .contextWrite(ctx ->
                    ctx.put(Key.CORRELATION_ID, "TOO-HIGH")
                )
                .flatMap(value ->
                    Mono.deferContextual(view ->
                        Mono.just(
                            "downstream=" + view.getOrDefault(
                                Key.CORRELATION_ID, "missing"
                            )
                        )
                    )
                )
                .block()
        );

        System.out.println("=== 3. Scheduler ===");

        System.out.println(
            Mono.just("order-7")
                .publishOn(Schedulers.parallel())
                .flatMap(order ->
                    Mono.deferContextual(view ->
                        Mono.just(
                            order + " cid=" + view.getOrDefault(
                                Key.CORRELATION_ID, "missing"
                            )
                        )
                    )
                )
                .contextWrite(ctx ->
                    ctx.put(Key.CORRELATION_ID, "CID-HOP")
                )
                .block()
        );

        System.out.println("=== 4. Missing context ===");
        System.out.println(describe().block());

        System.out.println("=== 5. Inner publishers ===");

        Flux.just("A", "B")
            .concatMap(item ->
                Mono.deferContextual(view ->
                    Mono.just(
                        item + ":" + view.getOrDefault(
                            Key.CORRELATION_ID, "missing"
                        )
                    )
                )
            )
            .contextWrite(ctx ->
                ctx.put(Key.CORRELATION_ID, "CID-LIST")
            )
            .doOnNext(System.out::println)
            .blockLast();
    }
}
~~~

Tại thư mục có **pom.xml**, yêu cầu JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ReactorContextDemo
~~~

Stdout mong đợi:

~~~text
=== 1. Two subscriptions ===
cid=CID-A; request=GET /orders
cid=CID-B; request=POST /orders
=== 2. Position ===
closest=INNER
downstream=missing
=== 3. Scheduler ===
order-7 cid=CID-HOP
=== 4. Missing context ===
cid=none; request=none
=== 5. Inner publishers ===
A:CID-LIST
B:CID-LIST
~~~

Đọc ví dụ:

1. **Two subscriptions:** Một định nghĩa Mono được dùng lại nhưng Context được cấp riêng cho từng subscription. Không có ID của request A bị giữ trong biến static để request B đọc nhầm.
2. **Position:** Operator gần người đọc hơn ghi INNER nên kết quả là INNER. Phép ghi TOO-HIGH nằm upstream của flatMap đọc key, vì vậy downstream nhận missing.
3. **Scheduler:** Sau publishOn, Mono.deferContextual vẫn nhận CID-HOP; Context đi theo subscription, không phụ thuộc cùng thread.
4. **Missing context:** Khi không có key, getOrDefault đưa ra giá trị an toàn.
5. **Inner publishers:** Mono được tạo trong concatMap là nested Publisher; nó đọc Context của chain cha và phát dữ liệu gắn CID-LIST. concatMap giữ thứ tự A, B.

**block()** và **blockLast()** chỉ để chờ trong CLI; trong WebFlux controller, trả Mono/Flux và để framework subscribe, không chặn event-loop.

## 6. Tạo mã tương quan tại WebFilter

**WebFilter** nằm ở ranh giới HTTP trong Spring WebFlux. Nó có thể đọc header đầu vào, chuẩn hóa ID, thêm header vào response và đưa metadata vào Reactor Context cho toàn bộ chuỗi xử lý request.

Một quy tắc minh họa:

- Chấp nhận **X-Correlation-ID** có độ dài từ 1 tới 64, chỉ gồm chữ, số, dấu gạch dưới, gạch ngang hoặc dấu chấm.
- Nếu thiếu hoặc không hợp lệ, sinh UUID mới.
- Không sử dụng header từ client để quyết định quyền truy cập.
- Giữ cùng ID qua các tầng xử lý của request.
- Hạn chế log raw path/query hoặc thông tin nhạy cảm.

Dùng enum RequestContextKey ở phần 4. Đây là **snippet của một ứng dụng Spring WebFlux**:

~~~java
@Component
public class CorrelationIdFilter implements WebFilter {
    private static final String HEADER = "X-Correlation-ID";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String incoming = exchange.getRequest()
            .getHeaders()
            .getFirst(HEADER);

        String cid = incoming != null
            && incoming.matches("[A-Za-z0-9._-]{1,64}")
                ? incoming
                : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders().set(HEADER, cid);

        String method = exchange.getRequest()
            .getMethod()
            .name();

        return chain.filter(exchange)
            .contextWrite(ctx ->
                ctx.put(RequestContextKey.CORRELATION_ID, cid)
                   .put(RequestContextKey.REQUEST_METHOD, method)
            );
    }
}
~~~

Phần này giả định enum được đặt tên:

~~~java
public enum RequestContextKey {
    CORRELATION_ID,
    REQUEST_METHOD
}
~~~

Imports chính: **java.util.UUID**, **org.springframework.stereotype.Component**, **org.springframework.web.server.WebFilter**, **WebFilterChain**, **ServerWebExchange**, **reactor.core.publisher.Mono**.

**Vì sao contextWrite nằm sau chain.filter(exchange)?** Trong biểu thức trả về, chain.filter là Publisher upstream; đặt contextWrite phía dưới đưa Context vào đường subscription khi framework thực thi chain. Nếu gắn metadata lên một Mono khác không bao trùm pipeline HTTP, service có thể không đọc được.

Response header giúp client nêu ID khi cần hỗ trợ. Trong hệ thống có proxy/gateway, cần thống nhất chính sách trust, giới hạn kích thước và tránh cùng một header có nhiều ý nghĩa khác nhau.

## 7. Đọc metadata ở service và ghi log

Giả sử một repository reactive trả Mono<Order>. Service có thể đọc Context rồi truyền cid trực tiếp vào lời gọi logger:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;
    private final Logger log =
        LoggerFactory.getLogger(OrderService.class);

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Mono<Order> findById(String orderId) {
        return Mono.deferContextual(view -> {
            String cid = view.getOrDefault(
                RequestContextKey.CORRELATION_ID,
                "unknown"
            );

            return repository.findById(orderId)
                .doOnNext(order ->
                    log.info("cid={} order fetched", cid)
                )
                .doOnError(error ->
                    log.warn("cid={} order lookup failed", cid, error)
                );
        });
    }
}
~~~

Đoạn này là snippet trong Spring project có **Order**, **OrderRepository** và logger SLF4J phù hợp. **Không cần MDC** để cid xuất hiện trong log vì nó được truyền tường minh thành argument.

Controller:

~~~java
@GetMapping("/orders/{id}")
public Mono<Order> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Spring WebFlux subscribe vào Mono trả về trong quá trình xử lý HTTP. Các operator của service thấy Context nếu nó được gắn đúng ranh giới WebFilter. Không gọi **subscribe()** thủ công trong controller chỉ để khởi động công việc: nó tạo subscription riêng, khó liên kết với cancellation/lỗi của HTTP request và có thể không thừa hưởng Context hiện tại.

### Ghi log theo signal

Trong vài trường hợp muốn quan sát từng tín hiệu bằng **doOnEach**:

~~~java
Flux<Order> data = repository.findAll()
    .doOnEach(signal -> {
        if (signal.isOnNext()) {
            String cid = signal.getContextView()
                .getOrDefault(
                    RequestContextKey.CORRELATION_ID,
                    "unknown"
                );
            log.info("cid={} order emitted", cid);
        }
    });
~~~

**Signal** có thể là onNext, onError hoặc onComplete; kiểm tra **isOnNext()** trước khi dựa vào dữ liệu phần tử. **doOnEach** nằm trong phạm vi Context ở phía upstream của contextWrite tương ứng. Callback log nên tránh ghi toàn bộ payload nhạy cảm.

## 8. Truyền ID qua WebClient sang dịch vụ khác

Reactor Context không tự đi qua mạng. Nếu một request ở service A gọi service B, cần thêm correlation ID vào header outbound hoặc để bộ distributed tracing được cấu hình thực hiện propagation.

Một filter WebClient có thể lấy Context ở đúng thời điểm subscribe:

~~~java
@Bean
WebClient downstreamClient(WebClient.Builder builder) {
    return builder
        .filter((request, next) ->
            Mono.deferContextual(view -> {
                String cid = view.getOrDefault(
                    RequestContextKey.CORRELATION_ID,
                    ""
                );

                ClientRequest.Builder outbound =
                    ClientRequest.from(request);

                if (!cid.isBlank()) {
                    outbound.headers(headers ->
                        headers.set("X-Correlation-ID", cid)
                    );
                }

                return next.exchange(outbound.build());
            })
        )
        .build();
}
~~~

Imports chính: **WebClient**, **ClientRequest**, **Mono**, **@Bean** và RequestContextKey. Snippet nằm trong một class cấu hình phù hợp.

**Mono.deferContextual** bảo đảm việc đọc Context xảy ra ở subscription của outbound request. **next.exchange** duy trì chuỗi filter của WebClient. Header được set tường minh ở boundary HTTP; service B phải đọc, kiểm tra rồi đặt vào Reactor Context mới của request mà nó nhận.

**Không dùng correlation ID thay trace/span ID.** Với Micrometer Tracing/OpenTelemetry, header **traceparent/tracestate** và span context có semantics riêng. Nếu thư viện tracing đang quản lý các header đó, không tự ghi đè chúng bằng mã ID nghiệp vụ. Một ứng dụng có thể giữ correlation ID riêng để hỗ trợ tra cứu, đồng thời duy trì trace/span do instrumentation cấp.

Với broker hoặc background job, nguyên tắc tương tự: đưa ID vào **message metadata** khi gửi và tái tạo Context cho subscription của consumer theo chính sách của hệ thống. Reactor Context của producer không tự truyền qua process khác.

## 9. ThreadLocal, MDC và Micrometer Context Propagation

| Tiêu chí | Reactor Context | ThreadLocal/MDC thông thường |
| --- | --- | --- |
| Gắn với | Subscriber / subscription | Thread đang chạy |
| Đọc qua | **deferContextual**, **ContextView** | **ThreadLocal.get**, **MDC.get** |
| Ghi qua | **contextWrite** | **ThreadLocal.set**, **MDC.put** |
| Qua publishOn | Context vẫn được cung cấp trong pipeline Reactor | Không tự chuyển giá trị sang thread mới |
| Quản lý vòng đời | Theo subscription và phạm vi operator | Cần restore/clear theo thread |
| Qua mạng | Không tự truyền | Cũng không tự truyền |

Ví dụ rủi ro:

~~~java
MDC.put("correlationId", cid);

return service.find()
    .publishOn(Schedulers.parallel())
    .doOnNext(value -> log.info("done"));
~~~

Ở đây MDC được ghi trên thread ban đầu, còn callback log có thể chạy trên scheduler khác. Không có cấu hình bridge, không thể bảo đảm log sẽ có cid. Nếu MDC không được clear đúng lúc, thread tái sử dụng còn có nguy cơ mang dữ liệu của request khác.

**Cách chắc chắn nhất khi cần chỉ một vài log:** đọc Reactor Context qua deferContextual rồi đưa cid trực tiếp vào log arguments như ở phần 7.

### Có thể tự đồng bộ Context với MDC không?

Reactor 3.5+ hỗ trợ tích hợp với **io.micrometer:context-propagation** nếu dependency hiện diện. Hai chế độ cần phân biệt:

- **Default/limited mode**: hỗ trợ khôi phục ThreadLocal qua một số operator và cơ chế nhất định, ví dụ handle hoặc tap theo hợp đồng tích hợp.
- **Automatic mode**: có thể bật **Hooks.enableAutomaticContextPropagation()** lúc ứng dụng khởi động. Cơ chế này sử dụng các **ThreadLocalAccessor** được đăng ký với key tương ứng để khôi phục/clear ThreadLocal khi chạy các subscription mới.

**Không chỉ cần gọi contextWrite là MDC tự xuất hiện ở mọi thread.** Cần có thư viện propagation, accessor, cấu hình tracing/observation và vòng đời đúng. Một ứng dụng Spring Boot có thể cấu hình sẵn một phần, nhưng phải kiểm chứng thực tế. Nếu hệ thống đã dùng tracing framework, nên để nó quản lý MDC và trace context, tránh tự bật nhiều bộ bridge không nhất quán.

## 10. Những ranh giới có thể làm mất Context

### 10.1. Tự subscribe trong code ứng dụng

~~~java
// Không nên: subscription thứ hai tách rời.
return Mono.deferContextual(view -> {
    String cid = view.get("cid");
    asynchronousSideEffect().subscribe();
    return Mono.just(cid);
});
~~~

Subscription của asynchronousSideEffect **không tự thừa hưởng Context cha**, và lỗi/cancel của nó có thể không gắn vào HTTP request. Cần ghép cùng pipeline:

~~~java
return Mono.deferContextual(view ->
    asynchronousSideEffect()
        .thenReturn(view.get("cid"))
);
~~~

Đây là snippet giả định asynchronousSideEffect trả Mono<Void> hoặc Publisher phù hợp. Tác vụ được **chờ trong cùng luồng**, và Reactor quản lý lỗi/cancellation cùng nhau.

Nếu thật sự cần fire-and-forget, hãy thiết kế một job độc lập có chủ sở hữu vòng đời, logging/error handling và correlation ID **truyền tường minh**, không dựa vào việc lệnh subscribe nằm trong callback của request.

### 10.2. CompletableFuture và thread tự tạo

**CompletableFuture.supplyAsync** hoặc **ExecutorService** không tự có Reactor Context của caller. Có thể đọc Context ở phía Reactor, rồi truyền dữ liệu cần thiết cho API ngoài:

~~~java
Mono<Result> result = Mono.deferContextual(view -> {
    String cid = view.getOrDefault("cid", "unknown");

    return Mono.fromFuture(
        startExternalCall(cid)
    );
});
~~~

Đây là snippet với kiểu Result và phương thức startExternalCall nhận cid rồi trả CompletableFuture<Result>. Việc truyền tham số tường minh giúp code ngoài Reactor không cần giả định Context có mặt ở thread của nó.

### 10.3. Override ở inner Publisher

Một contextWrite nằm bên trong một nhánh flatMap có thể ảnh hưởng inner Publisher đó nhưng không tự tác động lên những nhánh sibling hoặc operator downstream bên ngoài. Nếu thấy correlation ID khác nhau giữa các nhánh, hãy kiểm tra có code tự put cùng key không.

### 10.4. Publisher bên thứ ba

Reactor Context là cơ chế đặc thù của Reactor và những operator hỗ trợ nó. Một thư viện chỉ triển khai Reactive Streams cơ bản không bắt buộc cung cấp cùng trải nghiệm Context bên trong code của thư viện. Nếu cần metadata tại boundary đó, kiểm tra hợp đồng tích hợp hoặc truyền tường minh.

## 11. Test và kiểm chứng

Đối với correlation ID, ít nhất cần kiểm tra: đọc đúng khi có key, xử lý được khi thiếu key, và hai subscription độc lập không trao đổi nhầm metadata.

Trong test project có **reactor-test** và JUnit:

~~~java
@Test
void correlationIdIsVisible() {
    Mono<String> value = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("cid", "missing"))
    );

    StepVerifier.create(
            value.contextWrite(Context.of("cid", "CID-TEST"))
        )
        .expectNext("CID-TEST")
        .verifyComplete();
}
~~~

Đây là snippet test (không thuộc main class phần 5). Cần dependency **io.projectreactor:reactor-test** tương thích reactor-core và JUnit Jupiter.

Trường hợp thiếu key:

~~~java
StepVerifier.create(
        Mono.deferContextual(view ->
            Mono.just(view.getOrDefault("cid", "missing"))
        )
    )
    .expectNext("missing")
    .verifyComplete();
~~~

Với WebFlux, **WebTestClient** có thể gửi header **X-Correlation-ID**, kiểm tra response header được chuẩn hóa, rồi xác minh service đọc đúng Context khi request thực sự chạy. Test trên service riêng lẻ có contextWrite chưa đủ chứng minh WebFilter gắn Context đúng vị trí trong HTTP chain.

Với MDC/automatic context propagation, cần chạy test khi cấu hình accessor/hook thực tế được bật. Global hook có ảnh hưởng tới những subscription khác; test phải quản lý reset/khôi phục trạng thái để tránh tác động chéo.

## 12. Debug khi correlation ID biến mất

Nếu log ở service in **unknown** hoặc **missing**, hãy kiểm tra theo thứ tự:

1. **WebFilter có chạy cho endpoint này không?** Mã được lấy từ header hay được sinh UUID?
2. **contextWrite có đặt downstream của chain.filter không?** Nó phải bao phủ phần service cần đọc.
3. **Các tầng dùng cùng key enum/object/string không?** Key khác nhau không tìm thấy nhau.
4. **Operator đọc đang nằm upstream hay downstream so với contextWrite?** Ghi Context ở phía trên người đọc trong code không có tác dụng như mong muốn.
5. **Có một lần subscribe thủ công tạo luồng mới không?** Luồng mới không tự lấy Context từ luồng đang chạy.
6. **Có callback của CompletableFuture hoặc custom executor cần truyền metadata tường minh không?**
7. **Có nhánh con ghi đè cùng key không?** Operator gần chỗ đọc có thể quyết định giá trị cuối.
8. **Bạn đang đọc Reactor Context hay MDC?** MDC trống trên thread hiện tại không chứng minh Reactor Context trống.
9. **Pipeline đã được subscribe chưa?** deferContextual không chạy khi chỉ lắp ráp Mono.
10. **Có cancellation/timeout trước callback log không?** doOnNext sẽ không chạy khi phần tử không đến.

Khi debug, thêm một điểm đọc Context ngay ở đầu service:

~~~java
return Mono.deferContextual(view -> {
    String cid = view.getOrDefault(
        RequestContextKey.CORRELATION_ID, "MISSING"
    );
    log.debug("cid={} service entry", cid);
    return performOperation();
});
~~~

Nếu log đầu service có cid đúng nhưng callback khác không có MDC, vấn đề thường liên quan bridge ThreadLocal. Nếu log đầu service đã thiếu key, tập trung vào WebFilter, vị trí contextWrite, key và subscription boundary.

## 13. Bảo mật và lựa chọn kiến trúc

Reactor Context giúp truyền **metadata**, nhưng không thay cho bảo mật, transaction hay distributed tracing.

- **Không tin header tùy ý:** kiểm tra độ dài/định dạng, phân biệt ID do gateway đáng tin cậy phát và ID do người dùng tự gửi.
- **Không lấy ID để xác thực user/tenant:** dùng Spring Security và ReactiveSecurityContextHolder khi cần security context; correlation ID là công cụ tra cứu.
- **Không truyền nguyên request body hoặc token vào Context:** tránh giữ tham chiếu lớn và rò rỉ thông tin qua log.
- **Không tự tạo ID mới trong mỗi service:** nếu mục tiêu là một request xuyên nhiều tầng, giữ một ID nhất quán.
- **Không gửi raw query string nhạy cảm vào logs:** dùng route template và metadata đã tối giản.
- **Không nhầm correlation với trace/span:** traceparent và các thông tin tracing có cơ chế propagation độc lập.
- **Không tự coi subscribe thủ công là một luồng con được quản lý:** tạo chain reactive hoặc truyền metadata vào tác vụ tách rời theo hợp đồng riêng.
- **Không coi Context là cache bền vững:** nó tồn tại trong vòng đời subscription.
- **Không dựa vào cùng một thread:** dùng ContextView để đọc, hoặc cấu hình context-propagation theo tài liệu.
- **Chú ý các lỗi đã được phục hồi:** khi onErrorResume chuyển sang fallback thành công, doOnError đặt sau recovery không thấy lỗi chính. Đặt logging/metrics ở vị trí cần thiết để liên kết lỗi với cùng correlation ID.

Đối với một hệ thống có Micrometer Tracing đã vận hành, có thể dùng trace/span ID làm công cụ liên kết trước; chỉ thêm correlation ID riêng khi có yêu cầu nghiệp vụ rõ, và bảo đảm không làm sai cơ chế header propagation chính thức.

## 14. Tổng hợp lựa chọn truyền dữ liệu yêu cầu

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Một hai tầng service, contract cần kiểm tra bằng compiler | Truyền tham số rõ ràng |
| Metadata cần đọc tại nhiều operator của cùng subscription Reactor | **Reactor Context** |
| Log cần correlation trực tiếp mà không muốn cấu hình MDC | **deferContextual** và tham số logger |
| Cần MDC hoạt động qua scheduler | **Micrometer Context Propagation** với accessor/config đúng |
| Truyền correlation sang service HTTP khác | **WebClient filter** thêm header hoặc tracing instrumentation |
| Truyền sang message consumer | Message header/metadata, dựng Context ở consumer |
| Phân tích trace xuyên nhiều service | Micrometer Tracing/OpenTelemetry và chuẩn propagation |
| Truyền thông tin xác thực, phân quyền | Cơ chế security context được framework quản lý |

## 15. Tự kiểm tra

**Câu 1.** Reactor Context gắn với thread hay subscription?  
**Đáp án:** Subscription và Subscriber của chuỗi Reactor.

**Câu 2.** Vì sao contextWrite đặt cuối pipeline vẫn được deferContextual phía trên nhìn thấy?  
**Đáp án:** Context đi cùng quá trình subscription từ downstream lên upstream.

**Câu 3.** Nếu deferContextual nằm downstream của contextWrite, nó có tự thấy key do contextWrite vừa ghi không?  
**Đáp án:** Không. Phải xét vị trí operator và hướng lan truyền Context.

**Câu 4.** Sau publishOn, ThreadLocal và Reactor Context có hành vi như nhau không?  
**Đáp án:** Không. Reactor Context có thể truy cập trong cùng chuỗi; ThreadLocal cần bridge/restoration nếu đổi thread.

**Câu 5.** Reactor Context có tự xuất hiện trong request HTTP ở service khác không?  
**Đáp án:** Không. Phải dùng header hoặc instrumentation propagation.

**Câu 6.** Vì sao không nên gọi subscribe trong controller để giữ một job nền?  
**Đáp án:** Nó tạo subscription riêng, mất quản lý lỗi/cancel của request và không tự thừa hưởng Context.

**Bài tập A:** Trong Java demo, đổi vị trí contextWrite INNER và OUTER; dự đoán kết quả rồi giải thích bằng chiều subscription.

**Bài tập B:** Tạo 20 subscription của cùng một Mono.deferContextual với 20 cid khác nhau, xử lý qua scheduler, xác minh không có CID của request này xuất hiện trong kết quả request kia.

**Bài tập C:** Cài WebFilter và WebClient filter; dùng WebTestClient cùng HTTP server giả lập để khẳng định cid đầu vào hợp lệ được truyền qua header outbound.

**Bài tập D:** Thêm một lỗi trong service rồi onErrorResume chuyển sang cache. Đo các log doOnError trước/sau recovery; kiểm tra hai nhánh vẫn ghi cùng correlation ID.

**Bài tập E:** Thử đọc MDC sau publishOn khi chưa cấu hình bridge, rồi bật Micrometer Context Propagation với accessor đúng key. So sánh kết quả và xác nhận ThreadLocal được clear/restore theo vòng đời.

## 16. Tài liệu tham khảo

- Reactor Reference — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor Reference — Context-Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Reactor API — Context: https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html
- Reactor API — ContextView: https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html
- Spring Framework — WebClient Context: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html
- Spring Framework — WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
- Micrometer — Observation Instrumentation: https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html
- Reactive Streams for the JVM: https://github.com/reactive-streams/reactive-streams-jvm
