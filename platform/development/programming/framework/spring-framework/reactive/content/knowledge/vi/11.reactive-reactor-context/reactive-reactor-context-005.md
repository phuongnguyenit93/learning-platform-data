# Reactor Context: hướng truyền ngữ cảnh và ảnh hưởng vị trí toán tử

Trong Spring Reactive, một request có thể đi qua WebFilter, controller, service, repository, WebClient và nhiều toán tử Reactor. Những lớp này đôi khi cần cùng truy cập metadata xuyên suốt quá trình bất đồng bộ: correlation ID, tenant ID, thông tin bảo mật hoặc transaction state. Truyền các giá trị đó bằng tham số ở mọi phương thức có thể làm chữ ký API cồng kềnh. Dựa vào ThreadLocal theo kiểu lập trình đồng bộ lại không an toàn khi pipeline chuyển thread hoặc nhiều request dùng chung event-loop thread.

**Reactor Context** là cấu trúc key-value bất biến gắn với Subscriber của một subscription. Quy tắc quan trọng nhất là: **Context được truyền ngược từ downstream về upstream khi subscription được thiết lập**, trong khi dữ liệu vẫn phát xuôi từ upstream về downstream. Vì vậy, vị trí của **contextWrite** quyết định toán tử nào đọc được giá trị. Đặt **contextWrite** sớm trong dòng code chưa chắc làm Context nhìn thấy ở những toán tử nằm sau nó.

Bài học thuộc chủ đề **Reactor Context**, tập trung vào **hướng truyền ngữ cảnh và ảnh hưởng vị trí toán tử**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Context gắn với Subscriber và subscription thay vì gắn trực tiếp với thread hoặc từng item.
- Phân biệt hướng truyền **Context** với hướng truyền **data signal**.
- Dùng **contextWrite**, **deferContextual** và **ContextView** đúng vị trí.
- Dự đoán giá trị đọc được khi có nhiều **contextWrite** ghi cùng một key.
- Hiểu Context đi vào inner publisher trong **flatMap** như thế nào và cách ghi Context cục bộ trong nhánh con.
- Tránh lỗi do đặt **contextWrite** phía upstream của toán tử cần đọc, tự gọi **subscribe()** hoặc dựa vào ThreadLocal.
- Áp dụng Context cho correlation ID, WebFilter, reactive security và reactive transaction.
- Viết chương trình Java 17+ chạy được và kiểm thử vị trí Context bằng StepVerifier.

## 2. Context là gì?

**Context** là cấu trúc key-value bất biến (immutable) của Reactor. Nó gắn với Subscriber trong một subscription và có thể được các toán tử Reactor truy cập thông qua **ContextView**.

Ví dụ tối giản:

~~~java
Mono<String> greeting =
    Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.get("name")))
    .contextWrite(ctx -> ctx.put("name", "Reactor"));
~~~

Khi subscribe, **contextWrite** đặt **name=Reactor** vào Context dành cho upstream. **deferContextual** đọc giá trị đó tại thời điểm subscription và tạo kết quả **Hello Reactor**.

Các đặc điểm cần nhớ:

- **Theo subscription:** hai subscriber của cùng một publisher có thể có Context khác nhau.
- **Bất biến:** **put** và **delete** trả về một Context mới; chúng không sửa instance cũ.
- **Đọc qua ContextView:** toán tử đọc thường nhận **ContextView**, không phải Context có thể sửa.
- **Không phải ThreadLocal:** Context đi theo subscription và hoạt động qua các ranh giới scheduler của Reactor-native operators.
- **Không tự truyền qua mạng:** nếu gọi service khác, phải chuyển metadata cần thiết qua HTTP header, message header hoặc giao thức tương ứng.
- **Không phải kho lưu trữ payload:** nên giữ metadata nhỏ, ổn định; tránh đặt request body, danh sách lớn hoặc mutable application state vào Context.

Context không phải biến toàn cục. Nó không làm rò rỉ giá trị giữa các request nếu mỗi request tạo subscription riêng và ghi Context theo đúng phạm vi.

## 3. Hai hướng truyền khác nhau

Trong một pipeline, dữ liệu và Context di chuyển theo hai hướng:

~~~text
                    Subscription / Context
                 <----------------------------
Nguồn Publisher  ---> map ---> flatMap ---> Subscriber
                 ---------------------------->
                         onNext / onError / onComplete
                              Data signals
~~~

- **Data signal:** **onNext**, **onError**, **onComplete** đi từ nguồn (upstream) về subscriber (downstream).
- **Context:** khi subscriber đăng ký, Context được yêu cầu từ phía downstream rồi truyền ngược lên upstream qua subscription.
- **contextWrite:** tạo Context mới cho các toán tử nằm về phía upstream của chính nó.
- **deferContextual:** đọc Context mà subscriber của nó nhìn thấy tại thời điểm subscribe.

Có thể ghi nhớ: **Context được đọc từ downstream về upstream; dữ liệu được xử lý từ upstream về downstream**. Trong bài này, upstream luôn là phía gần nguồn hơn và downstream là phía gần subscriber hơn.

### Vì sao Context gắn với Subscriber?

Reactive Streams truyền Subscription từ Publisher tới Subscriber. Reactor tận dụng quá trình thiết lập subscription để làm Context của subscriber sẵn có cho các operator ở upstream. Vì vậy, Context không cần được đóng gói vào từng **onNext** như một phần của payload. Một chuỗi có thể phát hàng nghìn item mà mỗi operator vẫn đọc metadata của subscription tương ứng.

## 4. contextWrite chỉ ảnh hưởng về phía upstream

Hãy xem pipeline:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just("source sees " + ctx.get("traceId")))
    .contextWrite(ctx -> ctx.put("traceId", "request-42"));
~~~

Khi subscribe, Context được ghi ở **contextWrite**, sau đó được cung cấp cho **deferContextual**. Kết quả là **source sees request-42**.

Ngược lại:

~~~java
Mono<String> result = Mono.just("data")
    .contextWrite(ctx -> ctx.put("traceId", "request-42"))
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just("inner sees " +
                ctx.getOrDefault("traceId", "missing"))));
~~~

Ở đây **contextWrite** nằm **trước flatMap theo thứ tự ghép pipeline**. Nó chỉ thay đổi Context mà phần upstream của nó nhìn thấy. Subscriber của **flatMap** nằm downstream của **contextWrite**; inner publisher do **flatMap** tạo ra kế thừa Context của subscriber đó. Vì vậy, inner không thấy **request-42** và kết quả là **inner sees missing**.

Cách sửa là đặt **contextWrite** ở phía downstream của **flatMap**:

~~~java
Mono<String> result = Mono.just("data")
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just("inner sees " +
                ctx.getOrDefault("traceId", "missing"))))
    .contextWrite(ctx -> ctx.put("traceId", "request-42"));
~~~

Lúc này Context được cung cấp cho subscriber của **flatMap**, nên inner publisher kế thừa **traceId=request-42**.

**Quy tắc thực hành:** đặt **contextWrite** sau (về phía downstream của) phần pipeline cần đọc Context. Nếu cần truyền giá trị vào source-like operator như **deferContextual**, hãy đặt **contextWrite** ở cuối chuỗi đó.

## 5. Nhiều contextWrite cùng ghi một key

Context truyền ngược từ cuối pipeline lên đầu. Khi cùng một key được ghi nhiều lần, toán tử đọc sẽ thấy giá trị cuối cùng mà nó nhận được trên đường truyền Context — thường là giá trị được ghi ở **contextWrite** gần source hơn trong chuỗi.

Ví dụ:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("message")))
    .contextWrite(ctx -> ctx.put("message", "Reactor"))
    .contextWrite(ctx -> ctx.put("message", "World"));
~~~

Kết quả là **Reactor**, không phải **World**.

Diễn biến khi subscribe:

1. Subscriber bắt đầu với Context rỗng.
2. **contextWrite** ở cuối pipeline ghi **message=World**.
3. Subscription tiếp tục đi upstream; **contextWrite** gần source hơn nhận Context đó và ghi đè thành **message=Reactor**.
4. **deferContextual** đọc **message=Reactor**.

~~~text
Subscriber Context={}
       |
       v
contextWrite("World")       Context={message: World}
       |
       v
contextWrite("Reactor")     Context={message: Reactor}
       |
       v
deferContextual             đọc "Reactor"
~~~

Điều này quan trọng khi nhiều lớp cùng đặt metadata như **tenantId**, **traceId** hoặc **locale**. Cần quy ước rõ lớp nào được phép ghi đè key. Đừng giả định “ghi sau trong code” luôn thắng: subscription đi qua các toán tử theo chiều ngược với thứ tự dòng dữ liệu.

### Dùng Context có sẵn và cập nhật Context

Có thể đặt một Context đã tạo:

~~~java
.contextWrite(Context.of("traceId", "trace-123"))
~~~

Hoặc cập nhật bằng hàm:

~~~java
.contextWrite(ctx -> ctx.put("traceId", "trace-123"))
~~~

**Context.of** phù hợp khi tạo Context nhỏ với các cặp key-value đã biết. Hàm **contextWrite** hữu ích khi muốn giữ các key đã có và thêm/xóa một key:

~~~java
.contextWrite(ctx -> ctx
    .put("tenantId", "tenant-7")
    .put("traceId", "trace-123")
    .delete("temporaryKey"))
~~~

Vì Context bất biến, phải **trả về** kết quả của **put** hoặc **delete**. Đoạn dưới sai vì bỏ qua Context mới:

~~~java
.contextWrite(ctx -> {
    ctx.put("traceId", "trace-123"); // kết quả bị bỏ
    return ctx;
})
~~~

## 6. deferContextual: đọc Context đúng thời điểm

**Mono.deferContextual** nhận một **ContextView** khi subscriber đăng ký. Nó phù hợp khi publisher cần đọc metadata để tạo thao tác tiếp theo:

~~~java
Mono<String> message = Mono.deferContextual(ctx -> {
    String traceId = ctx.getOrDefault("traceId", "no-trace");
    return Mono.just("processing " + traceId);
});
~~~

Nếu gọi **ctx.get("traceId")** mà key không tồn tại, Reactor ném lỗi vì không thể tìm thấy key. Khi giá trị có thể vắng mặt, hãy dùng:

- **ctx.hasKey("traceId")** để kiểm tra.
- **ctx.getOrDefault("traceId", "no-trace")** để lấy giá trị mặc định.
- **ctx.getOrEmpty("traceId")** nếu muốn làm việc với Optional.

**ContextView** là giao diện chỉ đọc. Nếu cần thay đổi Context, dùng **contextWrite**; không tìm cách ép kiểu ContextView rồi sửa nó.

### Đọc Context ở giữa pipeline

Khi cần đọc Context không phải ở source, Reactor có **transformDeferredContextual**:

~~~java
Flux<String> result = Flux.just("a", "b")
    .transformDeferredContextual((values, ctx) ->
        values.map(value ->
            value + "-" + ctx.getOrDefault("tenant", "public")))
    .contextWrite(ctx -> ctx.put("tenant", "tenant-7"));
~~~

**transformDeferredContextual** nhận publisher ở vị trí toán tử và ContextView của subscriber nhìn thấy tại vị trí đó. Nó hữu ích cho thư viện hoặc toán tử tái sử dụng cần kết hợp cả luồng dữ liệu lẫn metadata. Với logic đơn giản ở source hoặc inner publisher, **deferContextual** thường dễ đọc hơn.

## 7. Context trong flatMap và publisher con

Một điểm tinh tế là inner publisher trong **flatMap** nhận Context từ subscriber của **flatMap**. Context được ghi ở phía downstream của **flatMap** có thể được inner đọc. Context được ghi bên trong một inner publisher chỉ có phạm vi của inner đó, không tự động sửa Context của chuỗi chính.

Ví dụ:

~~~java
Mono<String> result = Mono.just("Hello")
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + " " + ctx.get("message"))))
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + " " + ctx.get("message")))
            .contextWrite(ctx -> ctx.put("message", "Reactor")))
    .contextWrite(ctx -> ctx.put("message", "World"));
~~~

Kết quả là **Hello World Reactor**.

Giải thích:

1. **contextWrite** cuối cùng đặt **message=World** cho chuỗi chính.
2. Inner của **flatMap** thứ nhất kế thừa Context chính, nên đọc **World**.
3. Inner của **flatMap** thứ hai có một **contextWrite** cục bộ, nên đọc **Reactor**.
4. Việc ghi **Reactor** không làm thay đổi Context chính; nó chỉ áp dụng cho phần upstream trong inner publisher đó.

~~~text
Main sequence Context: {message: World}
      |
      +-- flatMap #1 inner đọc World
      |
      +-- flatMap #2 inner Context riêng:
             contextWrite(message=Reactor)
             deferContextual đọc Reactor
~~~

Điều này giúp một thư viện tạo Context cục bộ cho một lời gọi con mà không làm rò rỉ giá trị sang nhánh khác. Ngược lại, nếu muốn một key áp dụng cho toàn bộ inner publisher, hãy đặt Context ở phía downstream của operator tạo inner, không chỉ bên trong source con.

### Nhiều inner publisher độc lập

Nếu **flatMap** tạo nhiều nhánh, mỗi nhánh có thể kế thừa Context subscription chính. Một **contextWrite** đặt riêng bên trong một nhánh chỉ ảnh hưởng nhánh đó. Không dùng Context để chia sẻ mutable state giữa các nhánh; nếu nhiều nhánh cùng cập nhật một object mutable được đặt trong Context, race condition vẫn xảy ra như bình thường.

## 8. Context khác ThreadLocal như thế nào?

**ThreadLocal** lưu giá trị theo thread. Trong WebFlux, một request có thể đi qua nhiều thread hoặc scheduler; nhiều request cũng có thể dùng chung một event-loop thread tại các thời điểm khác nhau. Vì vậy, việc đọc **ThreadLocal** trực tiếp không phải cách đáng tin để mang metadata qua pipeline bất đồng bộ.

| Tiêu chí | Reactor Context | ThreadLocal |
| --- | --- | --- |
| Gắn với | Subscriber/subscription | Thread |
| Cách truyền | Theo cơ chế Context của Reactor | Theo thread hiện tại |
| Qua publishOn/subscribeOn | Reactor Context vẫn được operator Reactor truyền theo subscriber | ThreadLocal không tự động đi theo khi đổi thread |
| Cách đọc | deferContextual, transformDeferredContextual | ThreadLocal.get() |
| Phù hợp | Metadata của một reactive flow | Trạng thái đồng bộ gắn với một thread |
| Vòng đời | Theo subscription và Context được thiết lập | Phải tự quản lý set/remove |

Không nên hiểu bảng này là **ThreadLocal** luôn sai. Nó vẫn hữu ích trong code đồng bộ và thư viện cũ. Vấn đề là **không tự giả định ThreadLocal sẽ được bảo toàn trong reactive pipeline**.

### MDC và logging

SLF4J MDC thường dựa trên ThreadLocal. Nếu muốn log **traceId** trong ứng dụng reactive:

1. Lưu trace/correlation ID trong Reactor Context.
2. Dùng tracing/observability integration của Spring và Micrometer khi có thể.
3. Nếu cần bridge Context sang ThreadLocal/MDC, dùng cơ chế context-propagation được cấu hình và kiểm thử phù hợp với phiên bản Reactor/Micrometer.
4. Không tự set MDC ở một operator rồi quên clear; thread có thể được tái sử dụng cho request khác.

**Hooks.enableAutomaticContextPropagation()** và các integration liên quan là tính năng cấu hình theo phiên bản; không nên bật một hook toàn cục chỉ vì muốn một log có trace ID mà chưa đánh giá tác động. Trong code nghiệp vụ, ưu tiên đọc Context trực tiếp hoặc dùng API tracing đã tích hợp.

## 9. Context qua scheduler và ranh giới bất đồng bộ

**subscribeOn** và **publishOn** thay đổi nơi một phần pipeline được thực thi. Chúng không biến Context thành ThreadLocal. Context gắn với subscription nên Reactor-native operators vẫn có thể truy cập nó sau khi chuyển scheduler.

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.delay(Duration.ofMillis(10))
            .map(ignored ->
                "trace=" + ctx.get("traceId")))
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .contextWrite(ctx -> ctx.put("traceId", "trace-99"));
~~~

Khi subscribe, **traceId** vẫn có thể được đọc sau bước bất đồng bộ. **ContextView** được lấy trong **deferContextual** và đóng trong lambda; không cần đọc một ThreadLocal trên thread khác.

Có hai lưu ý:

- Context chỉ được truyền tự động qua các operator tích hợp với Reactor. Nếu gọi thư viện callback ngoài Reactor hoặc tự tạo một subscription độc lập, phải dùng bridge/API thích hợp.
- **subscribe()** lồng bên trong **map/flatMap** tạo một subscriber mới. Subscriber mới không mặc nhiên kế thừa Context của pipeline cha. Hãy compose publisher và trả kết quả về chuỗi chính.

## 10. Context là theo subscription, không theo đối tượng Publisher

Một publisher có thể được tái sử dụng nhiều lần với Context khác nhau:

~~~java
Mono<String> trace = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("traceId", "missing")));

String first = trace
    .contextWrite(Context.of("traceId", "request-A"))
    .block();

String second = trace
    .contextWrite(Context.of("traceId", "request-B"))
    .block();
~~~

Kết quả là **request-A** và **request-B**. Publisher được tạo một lần nhưng mỗi lần **block()** tạo một subscription riêng và Context riêng. **block()** ở đây chỉ dùng để minh họa trong chương trình console; trong WebFlux handler không dùng **block()**.

### Cẩn trọng với cache

**cache()** có thể chia sẻ tín hiệu đã được phát giữa nhiều subscriber. Nếu publisher tạo kết quả phụ thuộc Context, không được mặc định mỗi subscriber sẽ có kết quả riêng sau khi cache đã được lấp đầy. Ví dụ một publisher đọc **tenantId** rồi cache kết quả có thể làm ranh giới tenant sai nếu dùng chung một instance cache. Hãy thiết kế cache key có đủ tenant/identity hoặc đặt cache ở ranh giới phù hợp; không dùng Context để che một cache key thiếu thông tin.

### Context không tự truyền sang process khác

Khi gọi WebClient, Reactor Context không tự trở thành HTTP header trên wire. Cần lấy trace/correlation metadata và đưa vào header theo giao thức, hoặc dùng tracing integration hỗ trợ việc đó. Tương tự, gửi message sang broker phải đưa metadata cần thiết vào message header. Process nhận tạo Context mới từ metadata đã nhận và áp dụng quy tắc xác thực/ủy quyền của chính nó.

## 11. Áp dụng trong Spring WebFlux bằng WebFilter

Một **WebFilter** có thể đưa request ID vào Context cho toàn bộ pipeline của request:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.WebFilter;

@Configuration
public class RequestContextConfiguration {

    public static final String TRACE_ID = "traceId";

    @Bean
    WebFilter requestContextFilter() {
        return (exchange, chain) ->
            chain.filter(exchange)
                .contextWrite(ctx ->
                    ctx.put(TRACE_ID, exchange.getRequest().getId()));
    }
}
~~~

Đây là code tích hợp trong một ứng dụng Spring WebFlux; cần dependency WebFlux và cấu hình component scan. **exchange.getRequest().getId()** là ID của request do server cung cấp. Nếu ứng dụng chấp nhận correlation ID từ client, phải validate độ dài/ký tự và quyết định rõ tin cậy nguồn nào trước khi ghi vào Context.

Service có thể đọc Context ở thời điểm xử lý:

~~~java
import reactor.core.publisher.Mono;

public class ProfileService {

    private final ProfileRepository repository;

    public ProfileService(ProfileRepository repository) {
        this.repository = repository;
    }

    public Mono<Profile> findById(String id) {
        return Mono.deferContextual(ctx -> {
            String traceId = ctx.getOrDefault(
                RequestContextConfiguration.TRACE_ID, "no-trace");

            return repository.findById(id)
                .doOnNext(profile ->
                    log.info("traceId={} profileLoaded={}",
                        traceId, profile.id()));
        });
    }
}
~~~

Đây là fragment minh họa, cần khai báo **Profile**, **ProfileRepository** và logger. Trong dự án thực tế, không nhất thiết truyền request ID qua từng method parameter; Context giúp service hoặc thư viện reactive đọc metadata ở ranh giới phù hợp.

### Spring Security và reactive transaction

Spring Security dùng Reactor Context để giữ **SecurityContext** trong reactive execution; API **ReactiveSecurityContextHolder.getContext()** trả về publisher để đọc thông tin bảo mật. Không tự đưa một object authentication tùy ý vào Context để bỏ qua cơ chế xác thực/ủy quyền của framework.

Reactive transaction management cũng gắn transaction state với Reactor Context thông qua **ReactiveTransactionManager/TransactionalOperator**. Vì thế, một reactive transaction có thể tiếp tục qua các thread mà không cần dựa trên ThreadLocal kiểu transaction đồng bộ. Không tự gọi **subscribe()** tách khỏi pipeline transaction; làm vậy có thể tạo một subscription không còn nằm trong transaction scope mong muốn.

## 12. Ví dụ Java 17+ chạy được: quan sát vị trí Context

Tạo project Maven:

~~~text
reactor-context-position/
├── pom.xml
├── src/main/java/ContextPositionDemo.java
└── src/test/java/ContextPositionTest.java
~~~

Nội dung **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-context-position</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>3.6.9</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
      <scope>test</scope>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
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

Nội dung **src/main/java/ContextPositionDemo.java**:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public class ContextPositionDemo {

    private static Mono<String> readTrace() {
        return Mono.deferContextual(ctx ->
            Mono.just("source sees " +
                ctx.getOrDefault("traceId", "missing")));
    }

    public static void main(String[] args) {
        String precedence = readTrace()
            .contextWrite(ctx -> ctx.put("traceId", "near-source"))
            .contextWrite(ctx -> ctx.put("traceId", "near-subscriber"))
            .block();

        Mono<String> visibleToInner = Mono.just("item")
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just("inner sees " +
                    ctx.getOrDefault("traceId", "missing"))))
            .contextWrite(Context.of("traceId", "request-42"));

        Mono<String> misplaced = Mono.just("item")
            .contextWrite(Context.of("traceId", "upstream-only"))
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just("inner sees " +
                    ctx.getOrDefault("traceId", "missing"))));

        System.out.println(precedence);
        System.out.println(visibleToInner.block());
        System.out.println(misplaced.block());
    }
}
~~~

Chạy từ thư mục dự án:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ContextPositionDemo
~~~

Stdout:

~~~text
source sees near-source
inner sees request-42
inner sees missing
~~~

Giải thích:

1. **near-subscriber** được ghi trước khi subscription đi tiếp upstream; **near-source** được ghi gần source hơn và ghi đè cùng key, nên source thấy **near-source**.
2. **contextWrite** ở cuối chuỗi thứ hai cung cấp Context cho subscriber của **flatMap**; inner publisher kế thừa **request-42**.
3. **contextWrite** ở trước **flatMap** chỉ ảnh hưởng phía upstream của chính nó; subscriber của **flatMap** không nhận key đó, nên inner thấy **missing**.

**block()** chỉ xuất hiện trong **main** để in kết quả demo. Trong ứng dụng WebFlux, hãy return **Mono/Flux** và để framework quản lý subscription.

## 13. Kiểm thử vị trí Context bằng StepVerifier

Trong project Maven ở trên, tạo **src/test/java/ContextPositionTest.java**:

~~~java
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

class ContextPositionTest {

    @Test
    void subscriberInitialContextIsVisibleUpstream() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get("traceId")));

        StepVerifier.create(
                source,
                StepVerifierOptions.create()
                    .withInitialContext(Context.of("traceId", "test-123")))
            .expectNext("test-123")
            .verifyComplete();
    }

    @Test
    void contextWriteAfterFlatMapIsVisibleToInner() {
        Mono<String> source = Mono.just("item")
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("traceId", "missing"))))
            .contextWrite(Context.of("traceId", "visible"));

        StepVerifier.create(source)
            .expectNext("visible")
            .verifyComplete();
    }

    @Test
    void contextWriteBeforeFlatMapIsNotVisibleToItsInner() {
        Mono<String> source = Mono.just("item")
            .contextWrite(Context.of("traceId", "upstream-only"))
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("traceId", "missing"))));

        StepVerifier.create(source)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void innerContextWriteIsScopedToThatInner() {
        Mono<String> source = Mono.just("item")
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.get("traceId")))
                .contextWrite(ctx -> ctx.put("traceId", "inner")))
            .contextWrite(ctx -> ctx.put("traceId", "outer"));

        StepVerifier.create(source)
            .expectNext("inner")
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
mvn -q test
~~~

Maven trả exit code 0 khi bốn test pass. Các test xác minh **Context được nhìn thấy ở vị trí cụ thể**, thay vì chỉ kiểm tra pipeline trả một chuỗi. Điều này đặc biệt quan trọng vì lỗi đặt **contextWrite** sai vị trí có thể vẫn chạy thành công nhưng dùng giá trị mặc định hoặc metadata thiếu.

## 14. Lỗi phổ biến và cách khắc phục

1. **Đặt contextWrite trước toán tử cần đọc:** key chỉ được cung cấp cho phía upstream của nó. Hãy đặt Context về phía downstream của consumer cần đọc.
2. **Nghĩ Context đi cùng từng onNext:** Context gắn với subscriber/subscription, không phải payload.
3. **Nhầm Context với ThreadLocal:** Context đi theo Reactor chain; ThreadLocal đi theo thread.
4. **Quên tính bất biến:** ctx.put(...) trả Context mới. Nếu không return kết quả, key không được thêm.
5. **Dùng get cho key tùy chọn:** có thể phát lỗi khi thiếu key; dùng getOrDefault hoặc hasKey.
6. **Ghi cùng key ở nhiều lớp mà không quy ước:** giá trị gần source hơn có thể ghi đè giá trị được đặt phía downstream trước đó.
7. **Nghĩ inner flatMap tự động chia sẻ mọi thay đổi ngược ra ngoài:** Context viết trong inner được cô lập trong phạm vi inner.
8. **Tự gọi subscribe() lồng:** tạo subscription độc lập, không mặc nhiên kế thừa Context và lifecycle của pipeline cha. Hãy compose publisher.
9. **Lưu mutable object lớn vào Context:** các nhánh có thể chia sẻ tham chiếu và tạo race condition/giữ bộ nhớ lâu.
10. **Đưa thông tin nhạy cảm vào Context rồi log toàn bộ:** chỉ lưu metadata cần thiết; tránh log token, credential hoặc dữ liệu cá nhân.
11. **Cho rằng Context tự truyền qua WebClient/broker:** phải chuyển metadata sang HTTP/message headers hoặc dùng tracing integration.
12. **Dùng cache cho kết quả phụ thuộc tenant mà cache key thiếu tenant:** subscriber khác có thể nhận kết quả đã cache của subscriber trước.
13. **Coi publishOn là lý do Context biến mất:** Reactor-native operators giữ Context theo subscriber; nếu dữ liệu mất ở thư viện ngoài, cần bridge phù hợp.
14. **Dùng Context thay cho tham số nghiệp vụ:** dữ liệu cần thiết để hiểu/kiểm soát kết quả hàm vẫn nên nằm trong API; Context dành cho metadata xuyên suốt.
15. **Tự sửa SecurityContext trong Context:** dùng API Spring Security reactive và giữ nguyên quy trình xác thực/ủy quyền.
16. **Bật automatic context propagation mà không hiểu tác động:** cấu hình bridge ThreadLocal/MDC theo phiên bản, đo và kiểm thử trước khi áp dụng toàn ứng dụng.

## 15. Checklist khi thiết kế Context

Trước khi thêm một key vào Reactor Context, hãy xác định:

- **Mục đích:** đây là metadata xuyên suốt như trace ID, tenant hay security context, hay thực chất là dữ liệu nghiệp vụ nên truyền qua tham số?
- **Ai ghi key?** WebFilter, adapter, service hay thư viện? Có một nơi sở hữu rõ ràng không?
- **Ai đọc key?** Toán tử đọc nằm ở vị trí nào so với contextWrite?
- **Phạm vi:** key cần cho toàn pipeline, một inner publisher hay một request con?
- **Mặc định:** key có thể vắng mặt không? Cần getOrDefault, hasKey hay fail-fast?
- **Trùng key:** nhiều lớp ghi cùng key có thể ghi đè nhau không? Có namespace/key constant rõ ràng?
- **Đồng thời:** có đặt object mutable vào Context và dùng chung giữa các nhánh không?
- **Thread:** có đoạn nào dùng ThreadLocal/MDC hoặc thư viện callback ngoài Reactor không?
- **Ranh giới process:** metadata nào phải chuyển qua HTTP header/message header?
- **Cache:** kết quả có phụ thuộc Context nhưng được chia sẻ giữa subscriber không?
- **Bảo mật:** key có chứa thông tin nhạy cảm hoặc có thể bị client giả mạo không?
- **Vòng đời:** có subscribe() lồng, cache hoặc publisher được giữ lâu khiến Context sống lâu ngoài dự kiến không?

## 16. Bài tập tự kiểm tra

**Bài 1.** Vì sao **Mono.deferContextual(...).contextWrite(...)** thường đọc được key?  
**Đáp án:** Khi subscription đi từ downstream lên upstream, **contextWrite** cung cấp Context cho source-like operator **deferContextual**.

**Bài 2.** **Mono.just("x").contextWrite(put("id","A")).flatMap(v -> Mono.deferContextual(...))** có đảm bảo inner thấy A không?  
**Đáp án:** Không. **contextWrite** nằm phía upstream của **flatMap**; inner kế thừa Context của subscriber **flatMap**, không phải Context chỉ dành cho source ở trước nó.

**Bài 3.** Nếu hai **contextWrite** ghi cùng key, **deferContextual** thấy giá trị nào?  
**Đáp án:** Giá trị của lần ghi gần source hơn trên đường subscription, vì Context được truyền từ downstream lên upstream và lần ghi tiếp theo trong quá trình truyền có thể ghi đè.

**Bài 4.** Một inner publisher ghi **tenant=inner** trong Context. Nhánh khác của cùng **flatMap** có tự thấy **tenant=inner** không?  
**Đáp án:** Không. Context viết trong inner chỉ có phạm vi nhánh đó, không sửa Context của main sequence hoặc sibling inner.

**Bài 5.** **publishOn** đổi thread. Context có biến mất không?  
**Đáp án:** Không đối với Reactor-native operators; Context gắn với subscription chứ không gắn với thread. ThreadLocal thì không tự động được bảo toàn.

**Bài 6.** Có nên lưu toàn bộ đối tượng request vào Context để service nào cũng đọc được?  
**Đáp án:** Thường không. Context nên chứa metadata nhỏ và ổn định; dữ liệu nghiệp vụ nên truyền qua API/DTO phù hợp.

**Bài 7.** WebClient gọi service khác. Context **traceId** trong ứng dụng hiện tại có tự xuất hiện ở server bên kia không?  
**Đáp án:** Không tự động. Cần truyền qua HTTP header hoặc tracing integration.

**Bài 8.** Vì sao nested **subscribe()** nguy hiểm với Context?  
**Đáp án:** Nó tạo một subscription riêng, tách khỏi subscriber/lifecycle của chuỗi cha; Context và cancellation không tự kế thừa theo ý muốn.

**Bài 9.** Một publisher phụ thuộc **tenantId** được cache và dùng cho nhiều tenant. Điều gì cần xem xét?  
**Đáp án:** Cache có thể chia sẻ kết quả giữa subscriber; cache key và phạm vi cache phải bao gồm tenant hoặc publisher phải được tách theo tenant.

**Bài 10.** Vì sao **ctx.put("traceId","x")** trong lambda nhưng return **ctx** không có tác dụng?  
**Đáp án:** Context immutable; **put** tạo Context mới. Phải return Context mới hoặc viết **ctx -> ctx.put(...)**.

## 17. Ghi nhớ

Reactor Context là metadata **gắn với Subscriber**, được thiết lập khi subscribe và truyền **từ downstream về upstream**. Dữ liệu vẫn phát từ upstream về downstream. **contextWrite** cung cấp Context cho phần upstream của nó; **deferContextual** đọc Context tại vị trí subscriber tương ứng. Vì vậy, **vị trí toán tử là một phần của ngữ nghĩa**, không chỉ là chi tiết trình bày code.

Khi dùng Context với **flatMap**, inner kế thừa Context của subscriber tạo ra nhánh; Context được ghi bên trong inner chỉ ảnh hưởng nhánh đó. Context hoạt động qua các Reactor scheduler mà không dựa vào ThreadLocal, nhưng không tự truyền qua process hoặc qua một subscription độc lập. Giữ Context nhỏ, bất biến, có key rõ ràng và kiểm thử vị trí bằng StepVerifier để tránh lỗi metadata âm thầm.

### Tài liệu tham khảo

- Project Reactor, [Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- Project Reactor, [Context API](https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html) và [ContextView API](https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html).
- Project Reactor, [StepVerifier and testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework, [WebFlux Filters](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html).
- Spring Security, [Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html).
