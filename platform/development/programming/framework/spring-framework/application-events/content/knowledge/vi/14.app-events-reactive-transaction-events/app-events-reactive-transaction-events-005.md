# Khác biệt giữa ThreadLocal và Reactor Context trong Reactive Transaction Events

## 1. Vì sao xử lý sự kiện trong giao dịch reactive cần cách giữ ngữ cảnh khác?

Trong ứng dụng Spring thông thường, một phương thức `@Transactional` có thể cập nhật dữ liệu rồi gọi `ApplicationEventPublisher.publishEvent(...)`. Với transaction đồng bộ do `PlatformTransactionManager` quản lý, Spring gắn trạng thái giao dịch với **luồng Java đang thực thi (thread)**. Listener đồng bộ thường chạy trên cùng luồng, nên có thể thấy ngữ cảnh giao dịch đang gắn với luồng đó.

Nhưng trong ứng dụng WebFlux/R2DBC dùng Reactor, một chuỗi `Mono` hoặc `Flux` có thể tiếp tục trên thread khác sau `publishOn(...)`, `subscribeOn(...)` hay một thao tác I/O bất đồng bộ. Thread được tái sử dụng giữa nhiều công việc, vì vậy “đang chạy trên thread nào?” không còn xác định đáng tin một transaction của chuỗi reactive.

Spring giải quyết bằng **Reactor Context**: ngữ cảnh gắn với **subscriber/subscription của chuỗi reactive**, không gắn với danh tính thread. `ReactiveTransactionManager` lưu và truy xuất thông tin transaction thông qua context này. Từ Spring Framework 6.1, `@TransactionalEventListener` còn hỗ trợ giao dịch reactive, nhưng khi phát sự kiện cần đưa transaction context vào **event source** để listener xác định đúng giao dịch.

Đường đi ý tưởng:

~~~text
Imperative (ví dụ Spring MVC + JDBC/JPA)

Thread T1
  |
  +-- @Transactional -> PlatformTransactionManager
  |      +-- TransactionSynchronizationManager (thread-bound)
  |
  +-- repository.save(...)
  +-- publishEvent(event)
           +-- @TransactionalEventListener đăng ký theo transaction T1
  |
  +-- commit / rollback trên transaction của T1


Reactive (ví dụ WebFlux + R2DBC)

Subscription S1 + Reactor Context chứa TransactionContext
  |
  +-- @Transactional Mono/Flux -> ReactiveTransactionManager
  +-- databaseClient.sql(...).then(...)
  |
  +-- có thể đổi thread T1 -> T2, vẫn thuộc Subscription S1
  |
  +-- TransactionalEventPublisher.publishEvent(payload)
           +-- sự kiện mang TransactionContext của S1 trong source
           +-- @TransactionalEventListener đăng ký theo transaction S1
  |
  +-- hoàn tất pipeline -> commit / rollback
~~~

**Điểm quyết định:** `ThreadLocal` theo thread, còn `Reactor Context` theo **chuỗi subscriber**. Đổi thread không đương nhiên làm mất Reactor Context; nhưng tạo một subscription độc lập cũng không đương nhiên thừa hưởng ngữ cảnh của subscription ban đầu.

## 2. ThreadLocal là gì? Spring dùng nó ra sao?

`java.lang.ThreadLocal<T>` cho phép mỗi thread có một giá trị riêng của cùng biến:

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

public void handleRequest() {
    REQUEST_ID.set("req-123");
    try {
        // Mã chạy trên chính thread hiện tại có thể đọc REQUEST_ID.get().
    } finally {
        REQUEST_ID.remove(); // Tránh lưu sót dữ liệu trong thread pool.
    }
}
~~~

Đoạn trên minh họa một biến tự định nghĩa, **không phải** mã dùng để tạo Spring transaction. Đối với giao dịch imperative, Spring sử dụng lớp `org.springframework.transaction.support.TransactionSynchronizationManager` để giữ tài nguyên và các transaction synchronization gắn với thread. `PlatformTransactionManager` chịu trách nhiệm thiết lập và dọn ngữ cảnh đó khi giao dịch bắt đầu, commit hoặc rollback.

Vì `ThreadLocal` thuộc về **từng thread**, các tình huống sau có hệ quả:

- Gọi phương thức trực tiếp trên cùng thread thường vẫn truy cập được ThreadLocal.
- Chuyển việc sang thread mới hoặc executor khác không tự chuyển giá trị của `ThreadLocal` thông thường.
- Các thread trong pool được tái sử dụng, nên tự dùng ThreadLocal mà quên `remove()` có thể làm rò dữ liệu từ công việc trước sang công việc sau.
- `InheritableThreadLocal` chỉ hỗ trợ kế thừa theo điều kiện khi tạo thread con, không giải quyết tổng quát việc chuyển qua các thread có sẵn trong pool và không phải giải pháp quản lý reactive transaction.

**Không phải mọi lời gọi Spring đều tự có transaction.** `ThreadLocal` chỉ là nơi framework lưu ngữ cảnh cho transaction imperative đang hoạt động. Tạo một `ThreadLocal` bất kỳ, hoặc kiểm tra thread hiện tại, không tự tạo transaction và không đảm bảo commit.

## 3. Reactor Context hoạt động như thế nào?

Trong Project Reactor, `reactor.util.context.Context` là tập cặp khóa–giá trị **bất biến** (immutable); thao tác `put(...)` trả về Context mới. `ContextView` cho phép đọc ngữ cảnh. Context được liên kết với subscriber và truyền theo cơ chế subscription của Reactor.

Hai API nền tảng:

- `contextWrite(...)`: bổ sung/chỉnh context cho phần thích hợp của chuỗi reactive tại lúc có subscription.
- `Mono.deferContextual(ctx -> ...)`: lấy `ContextView` đang có tại thời điểm thực thi phần chuỗi đó.

Ví dụ tối giản:

~~~java
Mono<String> greeting = Mono.deferContextual(ctx ->
        Mono.just("Xin chào " + ctx.get("user")))
    .contextWrite(ctx -> ctx.put("user", "Lan"));
~~~

*Đoạn mã minh họa đặt trong chương trình có Reactor Core; `Mono` là `reactor.core.publisher.Mono`.*

Khi có subscription, chuỗi trên phát `"Xin chào Lan"`. Dù `contextWrite(...)` nằm dưới trong cách viết chuỗi, thông tin context được đưa từ phía subscriber xuống các toán tử upstream trong giai đoạn subscribe. Điều này giải thích vì sao **vị trí `contextWrite(...)` có ý nghĩa**; đặt nó ở một nhánh khác hoặc quá sớm trong chuỗi không có nghĩa mọi toán tử đều thấy cùng giá trị.

Một subscription khác của một publisher không có thao tác ghi context phù hợp có thể không tìm thấy khóa `"user"`. Reactor Context **không phải biến toàn cục** và cũng không phải một bản sao tự động của mọi ThreadLocal.

### Bảng so sánh trọng tâm

| Tiêu chí | `ThreadLocal` | `Reactor Context` |
| --- | --- | --- |
| Nơi gắn ngữ cảnh | Đối tượng `Thread` hiện hành. | `Subscriber` / subscription trong pipeline reactive. |
| API tiêu biểu | `set`, `get`, `remove`. | `contextWrite`, `deferContextual`, `ContextView.get`. |
| Chuyển sang thread khác | Không tự kế thừa ThreadLocal thông thường. | Vẫn truy cập được nếu tiếp tục trong chuỗi và phạm vi Context phù hợp. |
| Chuỗi reactive độc lập | Có thể chạy cùng thread nhưng không đồng nghĩa cùng nghiệp vụ. | Có subscription/context riêng, không tự mang context của chuỗi khác. |
| Cách thay đổi giá trị | Gán giá trị cho thread hiện tại. | Tạo Context mới; phạm vi hiển thị theo cấu trúc chuỗi. |
| Bài toán transaction Spring | `PlatformTransactionManager`, JDBC/JPA. | `ReactiveTransactionManager`, R2DBC và API reactive tương ứng. |
| Nguy cơ nhầm phổ biến | Tin rằng executor khác vẫn thấy transaction. | Tin rằng mọi `subscribe()` hoặc `block()` mới đều dùng lại transaction hiện tại. |

## 4. Ví dụ Java 17+ chạy được: đổi thread, so sánh hai context

Ví dụ này **chỉ dùng một khóa minh họa `flowId`** để chứng minh cơ chế lưu ngữ cảnh, **không tạo transaction thật**. Muốn có Spring reactive transaction thật, ứng dụng phải dùng `ReactiveTransactionManager` và tài nguyên reactive như R2DBC.

Tạo cấu trúc:

~~~text
context-comparison/
├── pom.xml
└── src/main/java/ContextComparisonDemo.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-comparison</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.11</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung `src/main/java/ContextComparisonDemo.java`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ContextComparisonDemo {

    private static final ThreadLocal<String> THREAD_VALUE = new ThreadLocal<>();

    public static void main(String[] args) {
        THREAD_VALUE.set("thread-main");
        Scheduler worker = Schedulers.newSingle("context-worker");

        try {
            System.out.println("Main ThreadLocal: " + THREAD_VALUE.get());

            String result = Mono.just("order-1")
                .publishOn(worker)
                .flatMap(orderId -> Mono.deferContextual(ctx ->
                    Mono.just(orderId
                        + " | ThreadLocal=" + THREAD_VALUE.get()
                        + " | ReactorContext=" + ctx.get("flowId"))))
                .contextWrite(Context.of("flowId", "subscription-42"))
                .block();

            System.out.println(result);

            String outside = Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("flowId", "absent")))
                .block();

            System.out.println("New subscription: " + outside);
        } finally {
            THREAD_VALUE.remove();
            worker.dispose();
        }
    }
}
~~~

Chạy với Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ContextComparisonDemo
~~~

Stdout do chương trình in ra trong ví dụ độc lập này (không tính thông báo riêng của Maven):

~~~text
Main ThreadLocal: thread-main
order-1 | ThreadLocal=null | ReactorContext=subscription-42
New subscription: absent
~~~

**Tại sao có kết quả đó?**

1. `THREAD_VALUE.set("thread-main")` chỉ đặt giá trị cho thread gọi `main`.
2. `Schedulers.newSingle(...)` tạo scheduler dùng một thread khác. Toán tử `publishOn(worker)` làm phần downstream chạy ở scheduler này. ThreadLocal thông thường trên thread mới không có giá trị đã đặt ở `main`, nên `get()` trả `null`.
3. `contextWrite(Context.of("flowId", "subscription-42"))` thêm khóa `flowId` cho subscription của pipeline. `Mono.deferContextual(...)` đọc được giá trị đó dù mã đang chạy trên thread worker.
4. Lời gọi `Mono.deferContextual(...).block()` thứ hai tạo một subscription khác, không có `contextWrite(...)` thiết lập `flowId`, nên đọc được `"absent"`.

**Không suy từ ví dụ rằng `ThreadLocal` luôn là `null` trong mọi ứng dụng reactive.** Một framework có thể chủ động sao chép một số giá trị qua cơ chế context propagation. Ví dụ minh họa mặc định của Reactor Core với một ThreadLocal tự định nghĩa và **không cấu hình cầu nối**; khác biệt bản chất vẫn là nơi lưu và phạm vi sống của ngữ cảnh.

## 5. Spring chọn transaction manager nào?

Spring có hai mô hình quản lý giao dịch, dùng những API khác nhau:

| Mô hình | Transaction manager | Kho lưu trạng thái |
| --- | --- | --- |
| Imperative, ví dụ JDBC/JPA | `PlatformTransactionManager`, như `DataSourceTransactionManager` hoặc `JpaTransactionManager`. | `ThreadLocal` do `org.springframework.transaction.support.TransactionSynchronizationManager` quản lý. |
| Reactive, ví dụ R2DBC | `ReactiveTransactionManager`, như `R2dbcTransactionManager`. | `TransactionContext` trong Reactor subscriber context, truy cập qua API giao dịch reactive. |

Trong giao dịch reactive, có lớp **`org.springframework.transaction.reactive.TransactionSynchronizationManager`** (khác package với lớp imperative cùng tên) và `TransactionContextManager`. Chẳng hạn API `TransactionContextManager.currentContext()` trả về `Mono<TransactionContext>`, cho phép lấy transaction context từ subscriber hiện tại; nếu thiếu transaction context, nó phát lỗi thích hợp.

Không nên dùng API đồng bộ `TransactionSynchronizationManager.isActualTransactionActive()` thuộc package `org.springframework.transaction.support` để kết luận một reactive transaction có tồn tại hay không. API đó quan sát trạng thái gắn với thread, trong khi reactive transaction được lưu ở context của subscription.

Khi áp dụng `@Transactional`:

- Với phương thức synchronous trả về giá trị thường hoặc `void`, Spring dùng luồng quản lý giao dịch imperative và cần `PlatformTransactionManager` thích hợp.
- Với phương thức trả `Mono`, `Flux` hay kiểu Reactive Streams `Publisher` và dùng `ReactiveTransactionManager`, Spring mở giao dịch khi pipeline được **subscribe**, không phải chỉ lúc tạo đối tượng `Mono`.
- Những thao tác dữ liệu muốn tham gia cùng reactive transaction phải nằm trong cùng pipeline/context thích hợp và sử dụng API dữ liệu reactive có hỗ trợ giao dịch, chẳng hạn `DatabaseClient` hoặc repository R2DBC.

Gọi JPA/JDBC chặn luồng bên trong một `Mono` không tự biến nó thành thao tác R2DBC và cũng không khiến nó tham gia reactive transaction. Nếu ứng dụng dùng cả JDBC/JPA và R2DBC, cần chọn transaction manager và ranh giới xử lý rõ ràng cho từng bên.

## 6. Vì sao reactive transaction event cần TransactionContext làm event source?

Đây là liên hệ trực tiếp với Spring Application Events.

Trong trường hợp imperative, multicaster gọi một `@TransactionalEventListener` trong lúc thread hiện tại còn có transaction synchronization. Listener adapter có thể dựa vào ngữ cảnh transaction **gắn với thread hiện tại** để đăng ký callback đúng pha.

Trong trường hợp reactive, lúc Spring nhận sự kiện thông qua API `ApplicationEventPublisher` (một API thông thường, trả `void`), **Reactor Context không tự xuất hiện như một ThreadLocal của thread hiện hành**. Vì vậy, Spring yêu cầu thông tin `TransactionContext` được đưa vào `ApplicationEvent.getSource()` của sự kiện đã phát nếu muốn listener gắn với reactive transaction.

Từ Spring Framework 6.1, `org.springframework.transaction.reactive.TransactionalEventPublisher` giúp tạo event đúng cách:

~~~java
@Bean
TransactionalEventPublisher transactionalEventPublisher(
        ApplicationEventPublisher delegate) {
    return new TransactionalEventPublisher(delegate);
}
~~~

*Đây là bean cấu hình đặt trong lớp `@Configuration`, không phải toàn bộ ứng dụng. Import `org.springframework.context.ApplicationEventPublisher`, `org.springframework.transaction.reactive.TransactionalEventPublisher` và `org.springframework.context.annotation.Bean`.*

Có hai cách gọi chính:

~~~java
// Đơn giản: truyền một payload không kế thừa ApplicationEvent.
Mono<Void> eventTask = transactionalEventPublisher.publishEvent(
        new OrderCreated("ORD-7"));

// Tùy biến event: nhận TransactionContext làm source.
Mono<Void> customEventTask = transactionalEventPublisher.publishEvent(
        source -> new OrderCreatedApplicationEvent(source, "ORD-7"));
~~~

*`OrderCreated` là record payload và `OrderCreatedApplicationEvent` là lớp `ApplicationEvent` tùy chỉnh do ứng dụng định nghĩa; đây là đoạn mô tả API, không phải chương trình độc lập.*

Với payload thông thường, publisher bọc nó vào `PayloadApplicationEvent` với **`TransactionContext` làm source**. Với event tùy chỉnh kế thừa `ApplicationEvent`, dùng overload nhận hàm để cung cấp source; không truyền trực tiếp đối tượng `ApplicationEvent` vào overload `publishEvent(Object)` vì overload đó dành cho payload và có thể từ chối `ApplicationEvent`.

**Quan trọng:** `publishEvent(...)` của `TransactionalEventPublisher` trả một `Mono<Void>`. Nếu chỉ gọi phương thức rồi bỏ qua `Mono`, công việc phát event chưa được subscribe nên **không thực sự chạy**. Phải nối publisher vào pipeline đang được thực thi, ví dụ bằng `then(...)`.

## 7. Mẫu Spring R2DBC: phát sự kiện trong reactive transaction

Đây là đoạn **mã tích hợp minh họa** cho một ứng dụng Spring Framework/Spring Boot đã cấu hình R2DBC, `ReactiveTransactionManager`, bean `TransactionalEventPublisher` ở phần 6 và bảng `orders`. Nó không phải chương trình Maven độc lập; ví dụ Java 17+ có thể chạy ngay nằm ở phần 4.

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import reactor.core.publisher.Mono;

record OrderCreated(String id) {}

@Service
class ReactiveOrderService {

    private final DatabaseClient db;
    private final TransactionalEventPublisher events;

    ReactiveOrderService(DatabaseClient db,
                         TransactionalEventPublisher events) {
        this.db = db;
        this.events = events;
    }

    @Transactional
    public Mono<Void> createOrder(String id) {
        return db.sql("INSERT INTO orders(id, status) VALUES (:id, :status)")
            .bind("id", id)
            .bind("status", "CREATED")
            .fetch()
            .rowsUpdated()
            .then(events.publishEvent(new OrderCreated(id)));
    }
}

@Component
class OrderCommittedListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        System.out.println("Đã commit đơn hàng " + event.id());
    }
}
~~~

### Giải thích luồng xử lý

1. Ứng dụng gọi `reactiveOrderService.createOrder("ORD-7")` **qua Spring proxy** và thực sự subscribe pipeline, chẳng hạn ở controller WebFlux bằng cách trả `Mono` cho framework. Bản thân việc tạo `Mono` chưa thực thi SQL hay publish event.
2. Interceptor của `@Transactional` và `ReactiveTransactionManager` gắn `TransactionContext` vào Reactor subscriber context.
3. `DatabaseClient` thực hiện `INSERT` bằng kết nối R2DBC nằm trong transaction reactive.
4. `then(events.publishEvent(new OrderCreated(id)))` khiến việc phát event diễn ra **sau khi `INSERT` phát thành công và trước khi pipeline transaction kết thúc/commit**, trong cùng reactive context. Nhờ đó listener được đăng ký theo transaction đang hoạt động.
5. `TransactionalEventPublisher` lấy transaction context hiện tại, tạo `PayloadApplicationEvent` có source là context đó, rồi chuyển tới `ApplicationEventPublisher`.
6. `@TransactionalEventListener(AFTER_COMMIT)` được gọi khi transaction hoàn tất bằng commit thành công; nếu rollback, listener pha này không chạy.

Vì sự kiện được phát **trước commit** nhưng listener được đăng ký **sau commit**, cần phân biệt thời điểm publish và thời điểm callback xử lý. Đây là hành vi cốt lõi của transaction-bound events.

### Nếu dùng ApplicationEventPublisher trực tiếp thì sao?

Thay `events.publishEvent(...)` bằng:

~~~java
Mono.fromRunnable(() ->
        applicationEventPublisher.publishEvent(new OrderCreated(id)));
~~~

*Đoạn minh họa chỉ mô tả cách đưa API đồng bộ vào pipeline, chưa bảo đảm transactional event semantics.*

Việc đặt một thao tác phát event thông thường vào `Mono.fromRunnable(...)` **không tự gắn `TransactionContext` vào event source**. `@TransactionalEventListener` cho giao dịch reactive do đó có thể không tìm thấy transaction hợp lệ và bỏ qua event (khi `fallbackExecution` mặc định là `false`). Sử dụng `TransactionalEventPublisher` hoặc tự tạo `ApplicationEvent` có source là `TransactionContext` nếu thực sự cần callback theo pha reactive transaction.

## 8. Reactor Context không có nghĩa mọi luồng/phân nhánh đều chia sẻ transaction

Reactor Context đi theo subscription và phạm vi operator; **không phải kho dữ liệu toàn cục của ứng dụng**. Cần hiểu những trường hợp sau:

| Thao tác | Tác động cần lưu ý |
| --- | --- |
| `publishOn(...)` / `subscribeOn(...)` trong pipeline | Có thể đổi thread; context thích hợp vẫn theo subscriber/pipeline reactive. |
| `contextWrite(...)` | Chỉ có hiệu lực với phần chuỗi nằm trong phạm vi được phép nhìn thấy context; vị trí operator rất quan trọng. |
| `flatMap(...)` tạo inner publisher | Inner publisher có thể nhận context từ subscription hiện tại khi được compose đúng cách; context được ghi cục bộ ở một nhánh không tự lan sang các nhánh anh em. |
| Tự gọi `subscribe()` trong service | Tạo subscription riêng, không tự giữ đúng transaction của pipeline đang chạy; làm luồng xử lý khó kiểm soát. |
| Gọi `block()` giữa mã reactive | Có thể tạo subscription/ranh giới thực thi riêng và chặn thread, làm mất ý nghĩa xử lý non-blocking; tránh trong pipeline WebFlux/R2DBC. |
| `CompletableFuture` hoặc executor thông thường | Không tự mang Reactor subscriber context sang một công việc Java tách khỏi pipeline, trừ khi có cơ chế chuyển ngữ cảnh rõ ràng. |
| Cơ chế Micrometer Context Propagation | Có thể liên kết một số giá trị context với ThreadLocal khi được cấu hình phù hợp; đây là cầu nối có chọn lọc, không phải đổi nơi lưu transaction reactive về ThreadLocal. |

Để đưa thêm logic vào cùng transaction, hãy **compose** các `Mono`/`Flux` cần thiết và để Spring quản lý subscription. Ví dụ:

~~~java
return repository.save(order)
    .flatMap(saved -> eventPublisher.publishEvent(
        new OrderCreated(saved.getId())).thenReturn(saved));
~~~

*Đây là đoạn minh họa trong method đang được `@Transactional` quản lý; `repository` là repository reactive và `eventPublisher` là `TransactionalEventPublisher`.*

Không nên viết:

~~~java
repository.save(order).subscribe();
eventPublisher.publishEvent(new OrderCreated(order.getId())).subscribe();
return Mono.empty();
~~~

Đoạn sai về mặt thiết kế ở trên tạo hai subscription độc lập và trả về một pipeline khác, khiến thứ tự lưu/publish, ranh giới giao dịch và lỗi không còn được kiểm soát như mong muốn. Nó cũng có thể phát event ngoài transaction reactive.

## 9. Phân biệt Reactor Context, TransactionContext và event source

Ba khái niệm gần nhau nhưng vai trò khác nhau:

**Reactor Context** là cơ chế lưu khóa–giá trị gắn với subscriber. Người dùng có thể tự lưu `requestId`, tên tenant hoặc dữ liệu đọc xuyên các operator qua `contextWrite(...)`.

**Spring TransactionContext** là đối tượng nội bộ lưu trạng thái giao dịch reactive, tài nguyên và synchronization. Spring `ReactiveTransactionManager` điều phối nó trong Reactor Context; ứng dụng thường không tự tạo một `TransactionContext` và đặt vào Reactor Context như cách thủ công để giả lập transaction.

**Event source** là trường có sẵn trong `ApplicationEvent` (`getSource()`). Spring dùng source là `TransactionContext` để listener transaction-bound có thể đăng ký đồng bộ hóa với **giao dịch reactive gốc**, khi event được chuyển qua API sự kiện thông thường.

~~~text
Reactor subscriber Context (S1)
    |
    +-- key tùy ứng dụng: requestId=R-10
    |
    +-- Spring TransactionContext
            |-- resource: kết nối R2DBC
            |-- transaction state / synchronizations
            |
            +--> TransactionalEventPublisher
                      |
                      +--> PayloadApplicationEvent(
                               source = TransactionContext,
                               payload = OrderCreated(...))
                                    |
                                    +--> @TransactionalEventListener
                                         đăng ký callback theo phase
~~~

Đừng nhầm event source với payload nghiệp vụ. Khi dùng `TransactionalEventPublisher.publishEvent(new OrderCreated(id))`, listener vẫn có thể khai báo tham số `OrderCreated` vì Spring nhận payload qua `PayloadApplicationEvent`. Phần source dành cho framework định danh transaction.

## 10. Ảnh hưởng đến lỗi, rollback và callback AFTER_COMMIT

Với `@TransactionalEventListener`, mặc định `phase = AFTER_COMMIT`. Những pha khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.

- Nếu `INSERT` trong pipeline reactive thất bại khiến transaction rollback, listener chỉ đăng ký cho `AFTER_COMMIT` sẽ không chạy.
- Nếu lỗi xảy ra **trước** khi publisher Mono được thực thi, event chưa được phát và không có callback nào đăng ký.
- Nếu event được phát ngoài transaction và `fallbackExecution` giữ mặc định `false`, listener không chạy.
- Nếu xử lý sau commit ném lỗi hoặc tiến trình dừng, Application Events không tự cung cấp hàng đợi bền vững và bảo đảm phát lại. Không nên thiết kế nghiệp vụ bắt buộc dựa vào mỗi callback trong bộ nhớ.

Đặc biệt, việc `AFTER_COMMIT` được gọi **sau commit** không làm transaction cũ có thể commit lại. Với một số transaction manager, tài nguyên có thể còn truy cập được trong khoảng callback hoàn tất; nếu cần ghi dữ liệu mới, hãy tạo một transaction độc lập có hỗ trợ reactive và compose xử lý đúng cách. Đừng chuyển kiểu `ThreadLocal` sang reactive bằng cách sao chép một biến rồi tưởng rằng đã có commit mới.

`@TransactionalEventListener` gắn **thời điểm** phản ứng với transaction. Nó không tự có nghĩa là xử lý bất đồng bộ hay bảo đảm giao nhận. Việc listener có chạy trên thread nào và công việc có bền vững hay không là những vấn đề riêng.

## 11. Lỗi phổ biến và cách sửa

1. **Dùng API transaction imperative trong reactive flow.** Ví dụ gọi `org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()` rồi kết luận “không có transaction” trong lúc R2DBC vẫn có reactive transaction. Cần dùng API reactive và quan sát pipeline subscription đúng chỗ.
2. **Tin rằng cùng thread thì cùng transaction.** Thread pool có thể chạy nhiều subscription độc lập trên một thread theo thời điểm khác nhau; định danh transaction dựa trên subscriber context chứ không dựa vào tên thread.
3. **Tin rằng đổi thread luôn làm mất transaction.** Với các toán tử Reactor còn nằm trong cùng chuỗi/context, đổi thread không phải lý do mất reactive transaction.
4. **Bỏ qua `Mono<Void>` do `TransactionalEventPublisher.publishEvent(...)` trả về.** Không có subscription, công việc publish không chạy. Hãy dùng `then(...)`, `flatMap(...)` hoặc cách compose tương đương.
5. **Phát event bằng publisher thông thường mà không có transaction source.** `@TransactionalEventListener` reactive có thể không đăng ký được callback; dùng `TransactionalEventPublisher`.
6. **Tự tạo `subscribe()` trong method `@Transactional`.** Subscription mới có thể chạy ngoài ranh giới transaction dự kiến; nối mọi thao tác vào pipeline được transaction manager quản lý.
7. **Gọi blocking JPA/JDBC trong chuỗi reactive và nghĩ nó tham gia R2DBC transaction.** Hai mô hình khác transaction manager và tài nguyên; dùng API dữ liệu tương ứng hoặc thiết kế ranh giới chuyển đổi rõ ràng.
8. **Tự cho rằng `Context.put(...)` tạo transaction.** Context có thể chứa mọi khóa tùy ý; transaction thật phải do `ReactiveTransactionManager` mở và quản lý.
9. **Cho rằng callback sau commit là hàng đợi đáng tin cậy.** Nếu cần chuyển sự kiện liên tiến trình, retry, tránh mất sự kiện khi tiến trình dừng, hãy cân nhắc transactional outbox và broker phù hợp.

## 12. Tự kiểm tra

**Câu 1.** Một pipeline R2DBC dùng `@Transactional` chuyển từ thread A sang B qua `publishOn(...)`. Có bắt buộc phải mất transaction không?

**Đáp án:** Không. Reactive transaction nằm trong Reactor Context của pipeline/subscription, không phụ thuộc vào việc luôn chạy trên thread A.

**Câu 2.** Hai subscription chạy nối tiếp trên cùng thread pool có tự dùng chung transaction không?

**Đáp án:** Không. Cùng thread không đồng nghĩa cùng subscriber context; mỗi subscription có phạm vi riêng.

**Câu 3.** Vì sao `applicationEventPublisher.publishEvent(new OrderCreated(id))` bên trong pipeline reactive có thể không kích hoạt `@TransactionalEventListener(AFTER_COMMIT)`?

**Đáp án:** Event thông thường không tự chứa `TransactionContext` làm source, trong khi listener transaction-bound cần nguồn ngữ cảnh đó để đăng ký callback với reactive transaction. Dùng `TransactionalEventPublisher` hoặc tạo event source đúng cách.

**Câu 4.** `transactionalEventPublisher.publishEvent(payload)` trả `Mono<Void>`. Nếu gọi mà không nối vào pipeline thì sao?

**Đáp án:** Mono là mô tả công việc; không được subscribe thì thao tác phát event không được thực hiện.

**Câu 5.** Có thể dùng `ThreadLocal.set(...)` rồi cho rằng Spring đã tạo reactive transaction không?

**Đáp án:** Không. Reactive transaction phải được `ReactiveTransactionManager` mở và quản lý; trạng thái được gắn với Reactor subscriber context. Giá trị ThreadLocal tự định nghĩa không tạo transaction.

**Câu 6.** Trong ví dụ Java 17+, vì sao `ThreadLocal=null` nhưng `ReactorContext=subscription-42`?

**Đáp án:** `publishOn` chuyển phần xử lý sang thread riêng chưa được gán ThreadLocal. Context được thiết lập bởi `contextWrite` và vẫn nhìn thấy trong subscription dù đổi thread.

## Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` với transaction imperative và reactive; yêu cầu event source cho reactive.
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): `PlatformTransactionManager`/`ReactiveTransactionManager` và nơi giữ transaction state.
- [Spring Framework Javadoc — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html): hai overload `publishEvent(...)` và cách gắn `TransactionContext` làm event source.
- [Spring Framework Javadoc — TransactionContextManager](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/reactive/TransactionContextManager.html): truy cập context giao dịch reactive.
- [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.6.11/reference/advancedFeatures/context.html): `Context`, `contextWrite`, `deferContextual` và phạm vi subscriber.
- [Spring Blog — Reactive Transactions with Spring](https://spring.io/blog/2019/05/16/reactive-transactions-with-spring/): vì sao ThreadLocal không phù hợp để giữ reactive transaction.
