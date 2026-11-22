# Số lượng listener và chi phí chọn listener trong Spring Framework Application Events

## 1. Mục tiêu: nhiều listener có làm publishEvent chậm?

Trong nhóm **Hiệu năng** của **Spring Framework Application Events**, câu hỏi không chỉ là “đã đăng ký bao nhiêu listener?”, mà là **khi một event được publish, Spring cần chọn những listener nào, mất bao lâu để chọn và sau đó tốn bao nhiêu thời gian để thực thi chúng?**

Giả sử ứng dụng có 250 listener:
- 180 listener xử lý các sự kiện liên quan đến thanh toán;
- 50 listener xử lý các sự kiện kho hàng;
- 17 listener xử lý các sự kiện tài khoản;
- 3 listener xử lý `OrderPlaced`.

Khi publish một `OrderPlaced`, điều mong muốn không phải gọi cả 250 callback rồi để chúng tự kiểm tra `if (event instanceof OrderPlaced)`. Spring có cơ chế **lọc listener theo kiểu event** và có **cache kết quả lựa chọn** cho những tổ hợp kiểu event/source phù hợp. Nếu chỉ 3 listener thực sự phù hợp, chi phí chạy handler thường gắn với **3 listener**, không phải với tất cả 250.

Nhưng không nên kết luận “nhiều listener luôn không có chi phí”:
- Lần gặp **kiểu event mới** có thể phải xem xét nhiều listener để xây tập phù hợp.
- Kiểu listener quá rộng, ví dụ nhận `ApplicationEvent` hoặc `Object`, có thể được chọn cho nhiều event không cần thiết.
- Mỗi listener phù hợp vẫn tạo ra invocation, phân giải argument/điều kiện, logging/tracing và side effect.
- Nếu dùng async multicaster, một event có thể sinh nhiều executor tasks.
- Nếu đăng ký/hủy listener động liên tục, hiệu quả cache có thể bị giảm.
- Khởi tạo bean, xử lý annotation và quản lý nhiều registration vẫn có chi phí startup/bộ nhớ.

**Mục tiêu học tập:** hiểu quy trình chọn listener, phân biệt chi phí **lọc ứng viên** với chi phí **chạy handler**, biết vì sao cold/warm lookup khác nhau, viết được ví dụ Java 17+ để kiểm chứng cơ chế type matching và thiết kế benchmark có ý nghĩa.

## 2. Mô hình chi phí: tổng N, phù hợp K và tần suất F

Đặt:

- `N`: tổng số listener được đăng ký trong application context.
- `K(e)`: số listener thực sự phù hợp với event `e`; luôn có `0 ≤ K(e) ≤ N`.
- `F(e)`: số lần event `e` được publish trong một khoảng đo.
- `S(e)`: chi phí lựa chọn danh sách listener phù hợp, gồm tra cache hoặc lọc khi cần.
- `H_i(e)`: thời gian thực thi listener thứ `i`.
- `D(e)`: chi phí hạ tầng dispatch, ví dụ gọi adapter, logging, instrumentation, submit executor.

Với multicaster **đồng bộ**, mô hình trực giác:

```text
T_publish_sync(e)
    ≈ S(e) + D(e) + SUM[H_i(e) for i in matched listeners]
```

Đây là mô hình phân rã, **không phải công thức cam kết chính xác của Spring**. Trong thực tế, JIT, lock contention, GC, class loading và code của từng handler cũng có thể ảnh hưởng.

Khi cache đã được làm nóng và không có thay đổi đăng ký, `S(e)` thường nhỏ hơn lần lookup mới vì có thể tái sử dụng danh sách phù hợp. Tuy nhiên, Spring vẫn phải thực thi/điều phối mỗi listener **được chọn**, nên tổng thời gian không tự trở thành hằng số độc lập với `K(e)`.

Với multicaster **async**, caller có thể chỉ thấy:

```text
T_publish_async(e)
    ≈ lựa chọn listener + tạo/submit task + listener bắt buộc sync
```

Công việc thật sau đó diễn ra trên executor:

```text
T_listener_end_to_end
    = queue_wait + handler_execution + các bước downstream thực tế
```

**Đừng đo `publishEvent()` rồi gọi con số đó là latency của async listener.** Nó có thể chỉ phản ánh tốc độ enqueue.

## 3. Spring chọn listener như thế nào?

Luồng khái niệm:

```text
ApplicationEventPublisher.publishEvent(event)
                       |
                       v
          ApplicationEventMulticaster
                       |
             xác định ResolvableType
                       |
             xét kiểu event / source
                       |
         tìm danh sách listener phù hợp
              /                 \
        cache hit           cần lọc ứng viên
              \                 /
                       v
            danh sách listener đã chọn
                       |
                sắp thứ tự khi cần
                       |
               dispatch từng listener
                  /            \
              đồng bộ       task executor
```

Các thành phần cần biết:

- `ApplicationEventPublisher` là API publish từ code ứng dụng.
- `ApplicationEventMulticaster` là abstraction điều phối listener.
- `SimpleApplicationEventMulticaster` là triển khai thường dùng trong một `ApplicationContext`.
- `AbstractApplicationEventMulticaster` cung cấp logic quản lý, tìm listener và cơ chế cache nội bộ cho việc truy xuất ứng viên.
- `ResolvableType` giúp Spring giữ/đọc thông tin kiểu generic của event/listener.
- `@EventListener` được Spring nhận diện, đăng ký thành adapter thích hợp; code ứng dụng không cần trực tiếp gọi từng listener.
- Các listener có thể tự biểu diễn điều kiện phù hợp qua `ApplicationListener<E>`, `SmartApplicationListener` hoặc `GenericApplicationListener`.

Khi event là một object thông thường không kế thừa `ApplicationEvent`, Spring có thể bọc nó thành `PayloadApplicationEvent` để dispatch. Khi dùng `@EventListener` với argument là payload, Spring vẫn xác định kiểu event cần nghe; đừng kết luận rằng mọi object event sẽ kích hoạt mọi listener.

**Lưu ý về implementation:** chi tiết cache/khóa cache thay đổi theo phiên bản framework. Ở dòng Spring Framework 6.1, việc truy xuất listener có xét kiểu event và kiểu source; cơ chế cache được dùng cho những trường hợp có thể tái sử dụng an toàn. Không giả định mọi lần publish hoặc mọi combination đều chắc chắn đi qua cùng một cache-hit path.

## 4. So khớp kiểu event và chi phí

### 4.1. Listener generic cụ thể

Ví dụ:

```java
public final class OrderPlacedListener
        implements ApplicationListener<OrderPlaced> {

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        // Chỉ xử lý các event OrderPlaced phù hợp.
    }
}
```

Đây là **mã trích đoạn**, với `OrderPlaced extends ApplicationEvent` và các import thích hợp. Khi Spring phân giải generic `ApplicationListener<OrderPlaced>`, framework có đủ thông tin để chọn listener cho `OrderPlaced`, không cần gọi listener của những loại event không liên quan.

### 4.2. Listener rộng được chọn nhiều hơn

Một listener cho mọi sự kiện:

```java
@Component
public class GeneralAuditListener
        implements ApplicationListener<ApplicationEvent> {

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof OrderPlaced orderPlaced) {
            auditOrder(orderPlaced);
        }
    }

    private void auditOrder(OrderPlaced event) {
        // Tác vụ minh họa, không phải file độc lập.
    }
}
```

Ví dụ là **đoạn tích hợp**. Dù có `if (event instanceof OrderPlaced)`, listener nhận loại `ApplicationEvent` rất rộng nên có thể được chọn/called cho nhiều event, kể cả sự kiện lifecycle do Spring phát. Nó đưa một phần công việc lọc từ multicaster vào code ứng dụng và làm tăng `K(e)` cho nhiều event.

Nếu thực tế chỉ cần `OrderPlaced`, hãy đăng ký listener typed đúng loại đó. Listener rộng có thể phù hợp cho audit/diagnostics cấp framework, nhưng cần ý thức rằng nó thực thi trên nhiều event.

### 4.3. Kiểu cha, kế thừa và generic

Một listener typed theo **supertype** có thể nhận nhiều subtype; điều đó đúng với semantics Java và cách Spring xử lý event type. Ví dụ nếu có `DomainEvent extends ApplicationEvent` và `OrderPlaced extends DomainEvent`, listener cho `DomainEvent` có thể nhận cả `OrderPlaced`.

Cần cân nhắc:
- Sử dụng một supertype rộng để tập trung logic có thể làm **nhiều event** đi qua cùng một listener.
- Dùng một listener generic có kiểu quá tổng quát hoặc dùng raw type có thể khiến khả năng lọc sớm kém rõ ràng hơn.
- Proxy và generic type resolution có thể phức tạp với class phân cấp, `@Async`, AOP hoặc đăng ký bean qua interface. Nên test đúng kiểu event được dispatch.

Đừng ép mọi event kế thừa một base class chung chỉ vì muốn “đơn giản hóa” nếu việc đó tạo các listener broad-scope vô ích.

### 4.4. SmartApplicationListener / GenericApplicationListener

Spring hỗ trợ các listener cung cấp điều kiện phù hợp nâng cao, gồm:
- `supportsEventType(...)`: listener hỗ trợ event type nào.
- `supportsSourceType(...)`: listener hỗ trợ class nguồn nào, khi có ý nghĩa.
- `getOrder()`/`@Order`: độ ưu tiên khi sắp listener.

Các interface nâng cao hữu ích cho thư viện hoặc framework integration, nhưng không nên dùng chúng chỉ để làm mọi handler trở nên phức tạp. Với đa số ứng dụng, `@EventListener` có argument type rõ hoặc `ApplicationListener<MyEvent>` đã đủ.

**Điểm hiệu năng:** điều kiện matching càng rộng hoặc càng đắt, càng cần đo lúc có cache miss, nhất là khi rất nhiều event types hiếm được publish. Tuy nhiên, không đưa logic truy cập DB, network hoặc tính toán lớn vào cơ chế chọn listener; selection nên là thao tác metadata/kiểu nhẹ.

## 5. @EventListener: chọn theo kiểu khác với điều kiện SpEL

Ví dụ:

```java
@EventListener(condition = "#event.totalCents() > 100000")
public void onLargeOrder(OrderPlacedPayload event) {
    // Chỉ xử lý đơn lớn.
}
```

Đây là **mẫu tích hợp**, giả định `OrderPlacedPayload` là kiểu được Spring nhận diện và có method `totalCents()`; cần import `@EventListener`, bean và Spring expression infrastructure.

Có hai cấp quyết định khác nhau:

1. **Lựa chọn theo kiểu event:** Spring tìm những adapter/listener hỗ trợ `OrderPlacedPayload`.
2. **Kiểm tra `condition`:** adapter kiểm tra biểu thức SpEL tương ứng khi nhận event; nếu false thì không thực thi body method.

Một điều kiện false **không nhất thiết loại được hoàn toàn chi phí dispatch và đánh giá điều kiện**. Nếu event được phát hàng chục nghìn lần/giây với nhiều handler có SpEL phức tạp, tổng thời gian đánh giá condition có thể đáng kể.

Khuyến nghị:
- Ưu tiên loại event rõ ràng và logic nghiệp vụ nằm trong handler khi cần.
- Tránh condition phức tạp, gọi object graph lớn hoặc getter có side effect.
- Cân nhắc tạo **event type chuyên biệt** nếu một điều kiện thực sự phân biệt hai loại fact nghiệp vụ khác nhau; đừng tạo nhiều event types chỉ để tối ưu vi mô mà làm sai domain model.
- Tách benchmark cho cost của adapter/condition và cost của business method khi cần tối ưu cụ thể.

## 6. Cache listener: cold lookup, warm lookup và thay đổi đăng ký

Trong `AbstractApplicationEventMulticaster`, Spring quản lý danh sách listener và có cơ chế lưu kết quả truy xuất phù hợp cho các combination event type/source. Ý nghĩa thực tế:

### 6.1. Cold path

Lần đầu một loại event (hoặc tổ hợp kiểu/source phù hợp) xuất hiện, framework có thể phải:
- Xác định `ResolvableType` của event.
- Xét các listener instance và listener beans đã đăng ký.
- Kiểm tra hỗ trợ event type/source type, kể cả generic metadata khi cần.
- Tạo danh sách kết quả, chuẩn bị thứ tự invocation theo policy.
- Lưu cache nếu trường hợp đó đủ điều kiện.

Chi phí ban đầu có thể phụ thuộc vào `N`, số bean, số loại event, complexity của generic/proxy và môi trường warmup JVM. Vì vậy, một sự kiện chỉ publish **một lần khi khởi động** có profile khác một loại event nóng được publish hàng triệu lần.

### 6.2. Warm path

Khi cùng kiểu event/source xuất hiện lặp lại và cache hợp lệ, framework có thể tái dùng retrieval result thay vì lọc toàn bộ listener từ đầu. Nhưng vẫn phải:
- Đi qua mỗi listener được chọn.
- Thực thi callback/adapters hoặc submit task.
- Xử lý lỗi, instrumentation, logging và business work.

Đó là lý do **N lớn nhưng K nhỏ** không nhất thiết tạo chi phí lớn cho sự kiện hot. Mặt khác, **K lớn** khiến mỗi event phải dispatch nhiều lần dù cache đã ấm.

### 6.3. Đăng ký/hủy listener động

`ApplicationEventMulticaster.addApplicationListener(...)`, `removeApplicationListener(...)` và thay đổi tập listener có thể làm cache cần cập nhật/xóa. Nếu ứng dụng liên tục tạo listener động theo từng request/session, nó có thể:
- Tăng số object tồn tại và chi phí quản lý.
- Làm giảm cơ hội tái sử dụng cache ổn định.
- Tạo retention/memory leak nếu quên remove.
- Gây race hoặc hành vi quan sát không nhất quán nếu lifecycle listener không được quản lý tốt.

**Đừng đăng ký một Spring application listener mới cho mỗi đơn hàng.** Thay vì vậy, dùng một listener bean ổn định có payload chứa `orderId`/`correlationId` và phân phối theo nhu cầu bên trong tầng nghiệp vụ.

Khi cần listener động thật, có chính sách đăng ký/hủy rõ ràng và load test vì đây là đường đi khác so với listener bean cố định.

## 7. Ví dụ Java 17+ chạy được: 203 listener nhưng chỉ đúng loại được gọi

Ví dụ sau kiểm chứng **type-based listener selection**, không cố benchmark nanoseconds. Ta đăng ký:
- 200 listener cho `OrderCancelled`.
- 3 listener cho `OrderPlaced`.
- Publish hai `OrderPlaced` và một `OrderCancelled`.

Nếu mỗi `OrderPlaced` gọi đúng 3 listener và `OrderCancelled` gọi đúng 200 listener, các count sẽ mang tính xác định bất kể tốc độ máy. Code dùng **Spring Framework 6.1.21** và không cần Spring Boot/database.

### 7.1. Cấu trúc

```text
listener-selection-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ListenerSelectionDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'listener-selection-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.ListenerSelectionDemo'
}
```

`src/main/java/demo/ListenerSelectionDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class ListenerSelectionDemo {

    public static final class OrderPlaced extends ApplicationEvent {
        public OrderPlaced(String orderId) {
            super(orderId);
        }
        public String orderId() {
            return (String) getSource();
        }
    }

    public static final class OrderCancelled extends ApplicationEvent {
        public OrderCancelled(String orderId) {
            super(orderId);
        }
        public String orderId() {
            return (String) getSource();
        }
    }

    public static final class PlacedListener
            implements ApplicationListener<OrderPlaced> {

        private final AtomicInteger calls;

        public PlacedListener(AtomicInteger calls) {
            this.calls = calls;
        }

        @Override
        public void onApplicationEvent(OrderPlaced event) {
            calls.incrementAndGet();
        }
    }

    public static final class CancelledListener
            implements ApplicationListener<OrderCancelled> {

        private final AtomicInteger calls;

        public CancelledListener(AtomicInteger calls) {
            this.calls = calls;
        }

        @Override
        public void onApplicationEvent(OrderCancelled event) {
            calls.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        AtomicInteger placedCalls = new AtomicInteger();
        AtomicInteger cancelledCalls = new AtomicInteger();

        try (var context = new AnnotationConfigApplicationContext()) {
            // Đăng ký listener instance trước khi refresh.
            for (int i = 0; i < 200; i++) {
                context.addApplicationListener(
                    new CancelledListener(cancelledCalls)
                );
            }
            for (int i = 0; i < 3; i++) {
                context.addApplicationListener(
                    new PlacedListener(placedCalls)
                );
            }

            context.refresh();

            context.publishEvent(new OrderPlaced("ORD-1"));
            context.publishEvent(new OrderPlaced("ORD-2"));
            context.publishEvent(new OrderCancelled("ORD-3"));

            System.out.println("registered=203");
            System.out.println("placed_calls=" + placedCalls.get());
            System.out.println(
                "cancelled_calls=" + cancelledCalls.get()
            );
        }
    }
}
```

Chạy với JDK 17+ và Gradle:

```bash
gradle run --quiet
```

**Stdout nghiệp vụ kỳ vọng:**

```text
registered=203
placed_calls=6
cancelled_calls=200
```

Giải thích:

1. `AnnotationConfigApplicationContext` nhận 203 `ApplicationListener` instance trước `refresh()`. Mỗi instance dùng identity object riêng, nên không bị gộp lại do trùng kiểu class.
2. Khi `refresh()`, context có thể phát các lifecycle events nội bộ. Hai nhóm listener typed `OrderPlaced`/`OrderCancelled` **không** nhận `ContextRefreshedEvent`; vì vậy chúng không làm sai count.
3. Hai `OrderPlaced` được publish đồng bộ. Mỗi event chỉ có 3 `PlacedListener` phù hợp, nên `placed_calls = 2 × 3 = 6`.
4. Một `OrderCancelled` kích hoạt 200 `CancelledListener`, nên `cancelled_calls = 200`.
5. Các listener typed cho cancellation **không** chạy rồi tự kiểm tra `instanceof OrderPlaced`: Spring lọc ứng viên theo event type trước khi gọi.
6. Không cấu hình executor, nên `SimpleApplicationEventMulticaster` dùng dispatch đồng bộ mặc định và các counters đã được cập nhật trước khi các `publishEvent()` trả về.

**Giới hạn phép thử:** output chứng minh type matching/invocation count, **không đo trực tiếp cache hit hoặc thời gian lọc**. Dù có thể đặt `System.nanoTime()` quanh publish, con số đó còn gồm class loading, type resolution, callback increments và JIT warmup; không nên dùng một lượt chạy làm benchmark kết luận “mỗi listener tốn X nanoseconds”.

Bài toán thực tế cần thử với tỷ lệ `N`/`K` và tần suất event tương tự production, sau đó đo bằng công cụ phù hợp.

## 8. Đo performance đúng cách: tránh benchmark ngộ nhận

### 8.1. Ba đại lượng nên đo riêng

| Đại lượng | Câu hỏi | Cách quan sát |
| --- | --- | --- |
| **Selection cost** | Tìm đúng danh sách listener tốn bao lâu? | Profiling multicaster/type filtering, benchmark cold vs warm có kiểm soát |
| **Dispatch/adapter cost** | Gọi mỗi listener hoặc submit task tốn bao nhiêu? | Listener no-op, số K khác nhau, profiler hoặc benchmark |
| **Business handler cost** | Mỗi handler làm việc bao lâu? | Micrometer `Timer`/tracing quanh handler; profiling SQL/I/O |
| **Queue wait** | Async task mất bao lâu trước khi chạy? | Instrument executor khi submit và lúc task start |
| **End-to-end latency** | Từ fact đến kết quả hoàn tất? | Domain event lifecycle, tracing/outbox/consumer metrics |

`publishEvent()` không luôn cho phép đo riêng selection; để phân rã chính xác cần profiler/JFR/JMH hoặc instrumentation tại tầng phù hợp. Không “lấy duration tổng trừ duration handler” một cách tùy tiện nếu các phép đo dùng clock, thread hoặc scope khác nhau.

### 8.2. Benchmark cold và warm lookup

Tạo hai kịch bản:
- **Cold:** tạo context với tập listener cố định, publish một type chưa từng được dispatch (hoặc một combination source/type chưa được tra), quan sát startup/classloading separately.
- **Warm:** giữ context ổn định, publish nhiều lần **cùng event type/source** sau warmup đủ để giảm ảnh hưởng JIT và class loading.

Đo các nhóm:

```text
Case A: N=20,    K=2, listener no-op
Case B: N=200,   K=2, listener no-op
Case C: N=2000,  K=2, listener no-op
Case D: N=2000,  K=200, listener no-op
Case E: N=2000,  K=200, mỗi handler làm việc thực tế
```

Những số N/K này là thiết kế **thử nghiệm minh họa**, không phải kết quả đo. So sánh A→C cho thấy ảnh hưởng của tổng registrations khi K cố định (đặc biệt cold path). So sánh C→D cho thấy chi phí dispatch tăng khi nhiều listener thực sự phù hợp. So sánh D→E cho thấy business work lấn át framework overhead như thế nào.

Đừng tạo mới Spring context **bên trong mỗi vòng benchmark warm** trừ khi chính startup cost là đối tượng đo; nếu không, bạn đang đo creation/refresh/classpath scanning hơn là publish hot path.

### 8.3. Dùng JMH thay vì vòng for đo thủ công

JMH hỗ trợ warmup, measurement iterations, forks, tránh nhiều loại benchmark sai do JIT/optimization/measurement noise. Một skeleton (không phải file biên dịch độc lập):

```java
@State(Scope.Benchmark)
public class EventPublishBenchmark {
    private AnnotationConfigApplicationContext context;
    private OrderPlaced event;

    @Setup(Level.Trial)
    public void setUp() {
        // Khởi tạo context và đăng ký listener cố định.
        // Publish warmup events nếu mục tiêu là warm selection.
    }

    @Benchmark
    public void publish() {
        context.publishEvent(event);
    }

    @TearDown(Level.Trial)
    public void close() {
        context.close();
    }
}
```

Đây là **mẫu cấu trúc**: phải thêm dependencies/plugin JMH, class event/listener, imports và một `setUp()` đầy đủ. Không có stdout benchmark cố định đáng tin để bịa ra trước khi chạy.

Khi benchmark:
- Bảo đảm listener có observable effect nếu cần tránh compiler loại công việc không quan sát được.
- Cố định số listener và cấu hình executor; mô tả phần cứng/JDK/GC trong báo cáo.
- Xem phân phối/variance, không chỉ một số trung bình từ một máy.
- Tách thời gian **context startup** khỏi publish hot path.
- Kiểm soát alloc/GC và JFR profile để biết bottleneck thật.

### 8.4. Đo trong production bằng Micrometer và tracing

Metric thường hữu ích:

| Metric | Mục đích | Tag khuyến nghị |
| --- | --- | --- |
| `application.events.publish.duration` | Đo lời gọi publish | `event_type` hữu hạn |
| `application.events.listener.duration` | Đo handler invocation | `event_type`, `listener`, `outcome` |
| `application.events.listener.errors` | Số lỗi khi handler xử lý | `listener`, `exception_category` hữu hạn |
| `application.events.executor.queue.wait` | Thời gian task chờ | `executor` |
| `application.events.executor.rejected` | Số lượt từ chối enqueue | `executor`, `reason` |

Không dùng `eventId`, `orderId`, `correlationId` hoặc exception message làm metric tags: **high cardinality** có thể đắt hơn chính công việc cần đo. Đặt các ID đó trong log/trace để điều tra một lần xử lý cụ thể.

Với sync listener, `publish.duration` có thể tăng chỉ vì một handler gọi DB chậm; vì vậy metric **listener.duration** rất cần để tách bottleneck. Với async, đo **queue wait + handler duration** chứ không chỉ duration của publisher.

## 9. Khi K lớn: invocation thường đáng chú ý hơn lookup

Giả sử 100 listener đều nghe `OrderPlaced`. Sau khi lựa chọn có cache, framework vẫn phải xử lý 100 callback:
- Gọi method, adapter hoặc proxy.
- Kiểm tra `@EventListener(condition=...)` nếu được cấu hình.
- Tạo span/metric/log khi có instrumentation.
- Làm side effect thực tế (DB, HTTP, email, cache, broker).
- Nếu async, enqueue các task tương ứng, quản lý thread/queue và context propagation.

**Cache chỉ giảm chi phí chọn ứng viên**, không biến 100 listener phù hợp thành một lần xử lý. Nếu mỗi handler mất 10 ms và chạy đồng bộ tuần tự, tổng thời gian có thể rất lớn. Không nhân con số 100 × 10 ms như một công thức tuyệt đối khi có overhead/parallelism, nhưng đây là dấu hiệu phải đo từng handler.

Những lựa chọn:
1. **Giữ event semantics đúng:** mỗi listener độc lập xử lý một concern rõ.
2. **Đưa công việc chậm ra khỏi request:** sử dụng executor hoặc queue nếu business contract cho phép eventual consistency.
3. **Gom những thao tác thực sự cùng một trách nhiệm:** tránh 20 listener trùng lặp query cùng bảng chỉ vì tách file class.
4. **Batch I/O khi phù hợp:** nếu nhiều task cùng đọc một nguồn có thể phối hợp hoặc dùng projection phù hợp.
5. **Dùng transactional outbox** nếu side effect quan trọng không được phép mất sau commit.
6. **Không đổi event thành direct call chỉ để tăng tốc mà phá ranh giới domain** khi hệ thống cần extensibility/decoupling.

Cân nhắc theo dữ liệu đo, không theo một ngưỡng chung kiểu “trên 50 listener là chậm”.

## 10. Async multicaster: N/K ảnh hưởng số task và queue

Khi `SimpleApplicationEventMulticaster` có `TaskExecutor`:
- Những listener có thể chạy async thường được submit task thay vì xử lý toàn bộ trên thread publisher.
- **Số task được enqueue** có thể tỷ lệ với `K`, không phải `N`.
- Executor có giới hạn threads/queue; nhiều listener có thể làm hàng đợi lớn và tăng waiting time.
- Task nhỏ quá mức có thể chịu overhead queue/context switch lớn hơn business work.
- Task bị rejected có thể làm publish lỗi hoặc kích hoạt rejection policy tùy executor.

Ví dụ:

```text
event_type=OrderPlaced, K=40
     |
     +--> 40 listener tasks
             |
             +--> 8 worker threads đang chạy
             +--> phần còn lại chờ queue
             +--> nếu queue full: reject / policy khác
```

Đây là kịch bản minh họa, không phải capacity mặc định của Spring.

**Không được nghĩ async multicaster = mỗi event một task duy nhất** trong mọi cấu hình. Thiết kế multicaster dispatch theo listener phù hợp; số thao tác submit phụ thuộc listener nào cho phép async. Nếu thêm `@Async @EventListener`, đường async proxy có thể dùng executor riêng, tạo thêm tầng task/handoff.

### Điều chỉnh executor

Tuning có cân nhắc:
- `corePoolSize`, `maxPoolSize`, `queueCapacity` và rejection policy.
- Handler là CPU-bound hay blocking I/O.
- Thời gian chờ queue, active threads, submitted/completed/rejected tasks.
- Số event/giây × số listener phù hợp trên mỗi event.
- Mục tiêu latency và backpressure.

Không chỉ tăng thread pool vô hạn khi DB connection pool và downstream API là bottleneck. Pool quá lớn có thể làm contention, context switching và memory tăng mà throughput không tăng.

## 11. Transactional listener: chi phí chọn khác thời điểm chạy

`@TransactionalEventListener` thường dùng phase `AFTER_COMMIT`, và có thể chọn các phase `BEFORE_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`. Trong transaction imperative:
- Listener cần được liên kết với transaction synchronization khi event được phát.
- Phần body xử lý theo phase tương ứng, thường về sau so với `publishEvent()`.
- Nếu không có transaction, mặc định listener không chạy, trừ khi `fallbackExecution=true`.

Vì vậy, một benchmark `publishEvent()` trong transaction có thể đo **registration overhead**, nhưng không đo trọn `AFTER_COMMIT` body. Phải đo handler ở phase thực thi và đo transaction commit riêng nếu cần.

Ví dụ:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlacedEvent event) {
    externalNotificationService.notify(event.orderId());
}
```

Đây là **đoạn tích hợp**, không phải chương trình độc lập. `OrderPlacedEvent`, service và imports cần được định nghĩa. Nó còn có ý nghĩa về reliability: callback sau commit không phải queue bền vững; crash sau DB commit có thể làm mất side effect nếu chưa gửi. Khi cần delivery đáng tin, dùng outbox và metric backlog/lag/retry.

**Không dùng `@Order` để giả định các listener async sẽ hoàn tất theo thứ tự.** Sắp thứ tự invocation hoặc registration không tự bảo đảm task completion, transaction ordering hay ordering trên broker.

## 12. Khi nào thực sự cần tối ưu selection?

Tối ưu selection đáng xét khi có các dấu hiệu:
- `publishEvent()` chiếm CPU đáng kể trong profiler nhưng handler hầu như no-op.
- Event rất thường xuyên (ví dụ trên hot path xử lý dữ liệu) và cần latency rất thấp.
- Có rất nhiều type/source combination hiếm, làm tỷ lệ lookup mới cao.
- Code tạo/hủy listener liên tục làm cache khó ổn định.
- Có listener generic quá rộng khiến nhiều event kích hoạt handler không liên quan.
- Có nhiều `@EventListener(condition=...)` phức tạp được đánh giá nhưng hiếm khi thực thi body.

Còn nếu profiler cho thấy 90% thời gian ở SQL/HTTP/serialization của listener, tối ưu generic matching gần như không giải quyết vấn đề. Hãy sửa bottleneck đúng tầng.

### Ma trận quyết định

| Quan sát | Giả thuyết cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Startup chậm, runtime publish ổn | Scanning/bean creation lớn | Lazy/lifecycle, giảm cấu hình trùng, profile startup |
| Cold publish chậm, warm nhanh | Type matching/class loading/cache | Warmup hoặc giảm dynamic registration nếu thực sự cần |
| Warm publish chậm, K lớn | Dispatch nhiều handler | Giảm listener trùng, xử lý I/O hiệu quả |
| Warm publish chậm, K nhỏ | Handler chậm hoặc adapter/proxy overhead | Profile per-handler, benchmark đúng path |
| Async publish nhanh nhưng side effect trễ | Executor queue/worker saturation | Đo queue wait, pool sizing, downstream latency |
| Lỗi tăng khi queue đầy | Rejection/capacity | Bounded queue, retry/outbox, backpressure |
| Cache hit thấp sau thay đổi cấu hình | Listener set thay đổi thường xuyên | Giữ registration ổn định và quản lý lifecycle |

**Không tối ưu bằng cách bỏ error handling, tắt tracing mọi nơi hoặc làm mất tính đúng đắn của domain** để có một con số latency thấp trên microbenchmark.

## 13. Kiểm thử type matching và khả năng mở rộng

### 13.1. Kiểm thử tính đúng đắn

Ví dụ mục 7 kiểm chứng:
- `OrderPlaced` chỉ gọi listener hỗ trợ `OrderPlaced`.
- `OrderCancelled` chỉ gọi listener hỗ trợ `OrderCancelled`.
- Số lần gọi đúng, không bị nhân bởi Spring lifecycle events.

Với `@EventListener`:
- Test cả event class và generic payload nếu có.
- Test subtype/supertype.
- Test condition SpEL đúng và sai.
- Test `supportsSourceType(...)` nếu tự viết listener nâng cao.
- Test listener bean đăng ký qua proxy/AOP nếu ứng dụng sử dụng.

### 13.2. Kiểm thử hiệu năng

Nên có suite benchmark riêng, không đặt ngưỡng nanosecond cứng trong unit test thông thường. Bộ benchmark nên:
- Giữ Java/JVM và context config ổn định giữa các variants.
- Đo cold và warm riêng; warmup trước khi lấy số hot-path.
- Thử N cố định K thay đổi và K cố định N thay đổi.
- Phân biệt sync/async, handler no-op và handler thật.
- Đảm bảo không có network/DB ngẫu nhiên trong microbenchmark selection.
- Ghi allocation rate, GC, CPU profile và confidence/variance khi so sánh.
- Không coi sai khác dưới noise level là cải tiến kiến trúc.

### 13.3. Test async và transaction riêng

Nếu bật multicaster executor, đợi listener bằng `CountDownLatch`, `CompletableFuture` hoặc tín hiệu completion thực tế, không dựa vào `Thread.sleep()` rồi assert. Nếu nghe `AFTER_COMMIT`, commit transaction thật trước khi đợi callback; Spring Test `@Transactional` thường rollback cuối test nên không tự kích hoạt AFTER_COMMIT.

### 13.4. Load test và observability

Theo dõi:
- Event volume và active handler count.
- p95/p99 `listener.duration` và `publish.duration`.
- Executor queue wait, queue depth, active threads, rejections.
- Success/error rate, retry count.
- GC pressure khi số event/tasks tăng.
- Outbox age nếu việc xử lý quan trọng chuyển sang durable messaging.

Một test có 2 listener đơn giản pass không chứng minh hệ thống với 200 listener, nhiều loại event và traffic đỉnh đạt SLA; cần load test với phân phối workload gần production.

## 14. Sai lầm phổ biến

1. **Cho rằng mỗi publish luôn duyệt/call toàn bộ listener.** Spring có type filtering và cơ chế cache retrieval; nên phân biệt selection với invocation.
2. **Cho rằng cache làm số lượng listener phù hợp không còn quan trọng.** Mỗi matched listener vẫn tạo work hoặc task.
3. **Đo một lần `System.nanoTime()` rồi tuyên bố benchmark framework.** Cold classloading/JIT/GC làm kết quả dễ sai.
4. **Không phân biệt N và K.** 500 listener tổng nhưng chỉ 2 matching khác 500 listener đều matching.
5. **Dùng listener nhận `ApplicationEvent` để lọc tay tất cả.** Có thể đưa rất nhiều event qua handler broad-scope.
6. **Tạo listener động cho mỗi request.** Tăng registrations, memory và cơ hội cache invalidation.
7. **Dùng SpEL condition rất phức tạp như một cách tránh mọi chi phí.** Adapter vẫn có thể phải evaluate condition.
8. **Cho rằng `@EventListener` scan method lại từ đầu mỗi lần event đến.** Annotation processing chủ yếu ở giai đoạn setup; runtime vẫn có adapter/invocation overhead.
9. **Đo publish async và kết luận handler xử lý rất nhanh.** Publish có thể chỉ submit task.
10. **Không quan sát queue wait/rejections.** Async làm request nhẹ hơn nhưng tạo backlog ngầm.
11. **Ép mọi listener thành async.** Thay đổi semantics transaction, ordering, error handling.
12. **Coi `@Order` bảo đảm hoàn tất tuần tự trong thread pool.** Thứ tự dispatch và completion khác nhau.
13. **Đánh đồng `AFTER_COMMIT` với async/durable.** Nó là transaction phase, không phải broker.
14. **Bật metrics với event ID/correlation ID làm tag.** High cardinality gây áp lực hệ thống giám sát.
15. **Tối ưu selection trước khi profile listener I/O.** Phần lớn thời gian đôi khi nằm ở DB/network chứ không ở multicaster.

## 15. Checklist thiết kế và review

- [ ] Biết tổng listener N và số listener phù hợp K với các event quan trọng?
- [ ] Listener typed rõ ràng, tránh nhận event quá rộng khi không cần?
- [ ] Hiểu cache hot lookup không loại bỏ chi phí invocation của K handler?
- [ ] Không tạo/hủy listener động theo mỗi request/event nếu không có lý do kiến trúc?
- [ ] Có phân biệt startup/first publish với warm steady state?
- [ ] Có đo `publish.duration` và `listener.duration` thành hai đại lượng riêng?
- [ ] Có test event type/subtype/source matching khi code dùng listener nâng cao?
- [ ] SpEL condition nhẹ, đúng semantics, không bị dùng làm nơi xử lý I/O?
- [ ] Không dùng một mẫu nanosecond duy nhất để quyết định tối ưu?
- [ ] Nếu async, có đo queue wait, active threads, rejection và handler completion?
- [ ] Nếu transactional, có phân biệt đăng ký listener với body ở commit phase?
- [ ] Có cơ chế lỗi/retry/idempotency tương ứng với mức độ quan trọng của event?
- [ ] Metrics chỉ dùng tags hữu hạn; event ID nằm trong logs/traces?
- [ ] Việc giảm số listener vẫn giữ đúng domain facts, isolation và khả năng bảo trì?

**Kết luận:** số lượng listener đăng ký (`N`) ảnh hưởng đến quản lý, cold matching và footprint; số listener **thực sự phù hợp** (`K`) quyết định số callback/task cần chạy cho mỗi event. Spring Framework Application Events có cơ chế chọn theo kiểu và cache retrieval nên không thể đơn giản coi mỗi publish là gọi toàn bộ N listener. Muốn tối ưu đúng, hãy đo selection, dispatch, handler, queue và transaction bằng **đúng ranh giới**, rồi điều chỉnh kiến trúc theo workload thực tế.

## Tài liệu tham khảo

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring 6.1 API — AbstractApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html)
- [Spring 6.1 API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring 6.1 API — GenericApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/GenericApplicationListener.html)
- [Spring 6.1 API — SmartApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SmartApplicationListener.html)
- [Spring 6.1 API — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring 6.1 API — EventListener annotation](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html)
- [OpenJDK Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
