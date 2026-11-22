# Chuỗi event dài và độ khó theo dõi trong Spring Application Events

## 1. Tại sao chuỗi event càng dài càng khó kiểm soát?

Trong Spring, `ApplicationEventPublisher.publishEvent(...)` cho phép một thành phần công bố sự kiện và các listener phản ứng mà không cần producer gọi trực tiếp từng listener. Cơ chế này rất hữu ích khi sự kiện biểu thị một **domain fact** như `OrderPlaced` hoặc `PaymentAuthorized`.

Nhưng một listener cũng có thể publish sự kiện khác. Sau vài lần mở rộng, một quy trình nhỏ có thể thành chuỗi nhiều tầng:

~~~text
PlaceOrder command
      |
      v
OrderPlaced
      |
      v
PaymentAuthorized
      |
      v
InventoryReserved
      |
      v
FulfillmentReady
      |
      v
CustomerNotificationRequested
~~~

Sự kiện ở mỗi bước có thể hợp lệ, nhưng việc xử lý phân tán qua nhiều class tạo ra câu hỏi khó: ai là chủ quy trình, chuyện gì làm bước tiếp theo chạy, transaction nào đã commit, exception ở đâu, thứ tự nào được bảo đảm, và một phép replay có làm side effect bị thực thi thêm lần nữa?

Một chuỗi event dài thường làm tăng **độ sâu phụ thuộc gián tiếp (implicit control flow)**. Khi controller chỉ gọi `orderService.placeOrder()`, người đọc có thể không thấy các listener nằm ở module khác đã gọi payment, reservation và notification. Phân tách module không tự đồng nghĩa với tách biệt trách nhiệm.

Mục tiêu bài này là biết **cách nhận diện event chain, vẽ topology, thêm correlation/causation, chặn vòng lặp, xử lý transaction và replay**, cũng như khi nào cần chuyển từ choreography sang orchestration.

## 2. Cơ chế dispatch tạo ra chuỗi event trong Spring

### 2.1. Chuỗi đồng bộ mặc định

Với `SimpleApplicationEventMulticaster` mặc định, những listener thông thường không được cấu hình async thường chạy trên **thread gọi publish**. Nếu listener lại gọi `publishEvent`, lần phát tiếp theo được thực hiện lồng trong lời gọi trước.

~~~text
OrderService.placeOrder()
  -> publish(OrderPlaced)
     -> listener A onOrderPlaced()
        -> publish(PaymentAuthorized)
           -> listener B onPaymentAuthorized()
              -> publish(InventoryReserved)
                 -> listener C onInventoryReserved()
                    -> ...
     <- các listener trả về
  <- publish(OrderPlaced) trả về
~~~

Trong một chuỗi tuyến tính chỉ có một listener cho mỗi loại, hành vi quan sát thường giống **depth-first recursion**. Đây là điểm cần nhớ vì lỗi từ cuối chuỗi có thể truyền ngược lên use case qua call stack, và thời gian xử lý của chuỗi đồng bộ có thể cộng dồn vào độ trễ request.

Nếu một event có nhiều listener, `@Order` có thể tác động thứ tự **gọi listener cho event đó**, nhưng khi listener đầu publish một event lồng, các listener của event lồng có thể chạy trước listener tiếp theo của event ban đầu. Vì vậy không thể suy từ `@Order` ra một trật tự tổng thể cho toàn bộ graph.

### 2.2. Chuỗi bất đồng bộ

`@Async` trên listener (khi được kích hoạt bằng `@EnableAsync` và proxy phù hợp) hoặc cấu hình `TaskExecutor` cho event multicaster có thể chuyển công việc sang thread khác. Khi đó:

- Publisher có thể trở về trước khi listener hoàn tất.
- Listener con và listener anh em có thể chạy song song hoặc đảo thứ tự.
- Exception trong **thân task đã chạy async** không tự truyền ngược về call stack publisher.
- Lỗi **lên lịch** như executor từ chối task vẫn có thể xuất hiện ngay khi publish.
- MDC, security context hoặc transaction của thread nguồn **không tự được chuyển** sang mọi executor.

Vì vậy thêm async vào một chuỗi dài làm **thứ tự và causal path** khó theo dõi hơn; nó không tự biến chuỗi thành workflow đáng tin cậy.

### 2.3. Một nguồn phát chuỗi dễ bị bỏ sót: return value

Spring cho phép phương thức `@EventListener` đồng bộ có kiểu trả về khác `void` được diễn giải là event mới để publish. Một collection/array có thể sinh nhiều event. Ví dụ minh họa trong bean Spring đã có type và service:

~~~java
@EventListener
public PaymentAuthorized onOrderPlaced(OrderPlaced event) {
    return paymentService.authorize(event);
}
~~~

Không thấy `publisher.publishEvent(...)` trong phương thức vẫn có một cạnh event graph. Với listener `@Async`, cơ chế phát event qua return value như vậy **không được hỗ trợ**; muốn phát tiếp thì dùng `ApplicationEventPublisher` tường minh.

Khi rà soát code, tìm cả `publishEvent(...)` lẫn các listener có giá trị trả về mang kiểu event.

## 3. Độ phức tạp của chuỗi: depth, fan-out, fan-in và cycle

Không có một con số “quá dài” cố định cho mọi hệ thống. Nên nhìn vào các đặc trưng:

| Khái niệm | Diễn giải | Dấu hiệu rủi ro |
| --- | --- | --- |
| **Depth** | Số cạnh event nối tiếp từ sự kiện gốc | Latency tích lũy, call stack sâu, nhiều bước để truy lỗi |
| **Fan-out** | Một event tạo nhiều nhánh qua listener hoặc event con | Nhiều tác vụ/side effect cùng lúc, tăng tải |
| **Fan-in** | Nhiều nhánh cần hoàn tất để kích hoạt bước tiếp | Race condition, không biết “đã đủ điều kiện” |
| **Cycle** | Chuỗi đi vòng trở lại event/trạng thái trước đó | Loop, recursion, event storm |
| **Cross-thread hop** | Bước sau chạy trên thread/executor khác | Mất ngữ cảnh, kết quả có thể đảo thứ tự |
| **Cross-transaction hop** | Bước sau dùng transaction riêng/after-commit | Không thể rollback toàn chuỗi như một transaction |
| **Retry/replay** | Event được nhận lại hoặc cố tình phát lịch sử | Tác động trùng nếu thiếu idempotency |

Fan-out có thể tăng nhanh: nếu một tầng tạo trung bình ba event và các tầng tiếp theo lại tạo ba event, số tác vụ có thể tăng theo lũy thừa độ sâu. Đây chỉ là **mô hình minh họa về khuếch đại**, không phải công thức bắt buộc của Spring. Nhưng nó giải thích tại sao một thay đổi nhỏ trong listener có thể làm queue/executor quá tải.

### Những triệu chứng thực tế

- Endpoint trả chậm dù code controller rất ngắn.
- Log ghi “failed in InventoryReserved” nhưng không biết request hoặc event nào gây ra.
- Đơn hàng rollback vì một listener thông báo phụ trợ bị lỗi.
- Một nghiệp vụ gửi email nhiều lần dù chỉ có một request.
- Projection bị ghi lùi do hai handler hoàn thành đảo thứ tự.
- Replay dữ liệu lịch sử vô tình chạy lại thao tác payment.
- Nhiều module có `@EventListener` nhưng không ai biết toàn bộ quy trình.

Khi có các triệu chứng này, việc tăng timeout không giải quyết được nguyên nhân kiến trúc.

## 4. Vẽ event graph với publisher, listener và transaction boundary

Một sơ đồ hữu ích cần chỉ rõ **ai phát, ai nghe, có phát tiếp không, đang ở thread và transaction nào**.

~~~text
[HTTP PlaceOrder]
       |
       v
[OrderService] -- publish --> (OrderPlaced)
                                  |
                  +---------------+----------------+
                  |               |                |
                  v               v                v
               [Audit]       [Payment]        [Search index]
                                  |             async?
                                  v
                           (PaymentAuthorized)
                                  |
                                  v
                           [Inventory handler]
                                  |
                                  v
                           (InventoryReserved)
~~~

Không nên vẽ duy nhất các tên event mà bỏ qua chỗ business state thực sự thay đổi. Để thiết kế hoàn chỉnh, đặt thêm các ghi chú `sync/async`, `BEFORE_COMMIT/AFTER_COMMIT`, transaction manager, retry, broker và tài nguyên dữ liệu.

Các câu hỏi cần trả lời khi thêm một listener:

1. Sự kiện đầu vào có phản ánh một fact đã xảy ra hay chỉ là command?
2. Listener chỉ xử lý fact, hay nó quyết định business workflow và phát event con?
3. Có listener khác cũng nghe event này không; các nhánh có cạnh tranh cập nhật cùng aggregate không?
4. Điều gì xảy ra nếu một bước giữa chuỗi thất bại?
5. Có đường nào quay lại event đã xử lý không?
6. Một lần replay sẽ đi qua những listener nào và gây side effect gì?
7. Có metadata giúp nối event hiện tại với nguyên nhân trực tiếp không?

Một danh sách publisher/listener có thể tự động tạo từ code, nhưng sơ đồ nghiệp vụ và quyền sở hữu workflow vẫn cần được review.

## 5. Ví dụ Java 17+ chạy được: truy vết chuỗi bốn tầng

Ví dụ sử dụng **Spring Framework 6.2.8**, JDK 17+ và Maven, không cần Spring Boot. Ta mô phỏng:

~~~text
OrderPlaced (event e1, hop 0)
  -> PaymentAuthorized (event e2, hop 1)
     -> InventoryReserved (event e3, hop 2)
        -> FulfillmentReady (event e4, hop 3)
~~~

Đây là **mô phỏng luồng sự kiện**, không gọi cổng thanh toán hoặc hệ thống kho thật. Trong sản phẩm thực tế, không được phát `PaymentAuthorized` nếu chưa có bằng chứng nghiệp vụ rằng authorization thành công, và tương tự với `InventoryReserved`.

Mỗi event mang metadata bất biến:

- `correlationId` giữ nguyên xuyên suốt một hành trình nghiệp vụ.
- `eventId` định danh event instance.
- `causationId` chỉ event đã kích hoạt trực tiếp event này.
- `hop` biểu thị số bước từ event gốc.

### 5.1. Cấu trúc thư mục

~~~text
event-chain-demo/
├── pom.xml
└── src/main/java/EventChainDemo.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <configuration>
                    <mainClass>EventChainDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. src/main/java/EventChainDemo.java

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class EventChainDemo {

    public record EventMeta(
            String correlationId,
            String eventId,
            String causationId,
            int hop
    ) {
        public EventMeta next(String nextId) {
            if (hop >= 3) {
                throw new IllegalStateException("Chain exceeds 3 hops");
            }
            return new EventMeta(
                correlationId, nextId, eventId, hop + 1
            );
        }
    }

    public record OrderPlaced(EventMeta meta, long orderId) { }
    public record PaymentAuthorized(EventMeta meta, long orderId) { }
    public record InventoryReserved(EventMeta meta, long orderId) { }
    public record FulfillmentReady(EventMeta meta, long orderId) { }

    private static void print(int number, String type, EventMeta meta) {
        System.out.printf(
            "%d %s corr=%s id=%s cause=%s hop=%d%n",
            number, type,
            meta.correlationId(), meta.eventId(),
            meta.causationId(), meta.hop()
        );
    }

    public static class Step1 {
        private final ApplicationEventPublisher publisher;

        public Step1(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            print(1, "OrderPlaced", event.meta());
            publisher.publishEvent(
                new PaymentAuthorized(
                    event.meta().next("e2"), event.orderId()
                )
            );
        }
    }

    public static class Step2 {
        private final ApplicationEventPublisher publisher;

        public Step2(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @EventListener
        public void onPaymentAuthorized(PaymentAuthorized event) {
            print(2, "PaymentAuthorized", event.meta());
            publisher.publishEvent(
                new InventoryReserved(
                    event.meta().next("e3"), event.orderId()
                )
            );
        }
    }

    public static class Step3 {
        private final ApplicationEventPublisher publisher;

        public Step3(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @EventListener
        public void onInventoryReserved(InventoryReserved event) {
            print(3, "InventoryReserved", event.meta());
            publisher.publishEvent(
                new FulfillmentReady(
                    event.meta().next("e4"), event.orderId()
                )
            );
        }
    }

    public static class Step4 {
        @EventListener
        public void onFulfillmentReady(FulfillmentReady event) {
            print(4, "FulfillmentReady", event.meta());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Step1 step1(ApplicationEventPublisher publisher) {
            return new Step1(publisher);
        }

        @Bean
        Step2 step2(ApplicationEventPublisher publisher) {
            return new Step2(publisher);
        }

        @Bean
        Step3 step3(ApplicationEventPublisher publisher) {
            return new Step3(publisher);
        }

        @Bean
        Step4 step4() {
            return new Step4();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(
                new OrderPlaced(
                    new EventMeta("order-42", "e1", "root", 0), 42L
                )
            );
            System.out.println("MAIN publishEvent returned");
        }
    }
}
~~~

Chạy bằng JDK 17+ và Maven từ thư mục `event-chain-demo`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chương trình in ra theo thứ tự, không kể log Maven:

~~~text
1 OrderPlaced corr=order-42 id=e1 cause=root hop=0
2 PaymentAuthorized corr=order-42 id=e2 cause=e1 hop=1
3 InventoryReserved corr=order-42 id=e3 cause=e2 hop=2
4 FulfillmentReady corr=order-42 id=e4 cause=e3 hop=3
MAIN publishEvent returned
~~~

### 5.4. Giải thích đầu ra

1. `main` phát `OrderPlaced` với `eventId=e1`, `causationId=root`, `hop=0`.
2. Listener `Step1` xử lý event và tạo `PaymentAuthorized`. `EventMeta.next("e2")` sao chép `correlationId`, đặt `causationId=e1` và tăng hop.
3. `Step2`/`Step3` tiếp tục, tạo các event có `causationId` trỏ đúng event cha.
4. `Step4` nhận `FulfillmentReady` và không phát tiếp, nên chuỗi dừng.
5. Do tất cả listener đều đồng bộ, mỗi loại có một listener, `MAIN publishEvent returned` xuất hiện sau bốn dòng log.

`EventMeta.next` kiểm tra không cho bước thứ tư **phát thêm event con** khi `hop>=3`. Giới hạn này mang tính minh họa: nó không chống retry, duplicate delivery hoặc vòng lặp khi một producer tự tạo lại metadata ở `hop=0`. Trong ứng dụng thật, event ID cần duy nhất mỗi event instance (UUID/ULID hoặc quy tắc ổn định), không dùng mã cố định e1/e2 cho mọi request.

### 5.5. Một cạnh thêm vào có thể tạo vòng lặp

Giả sử có listener khác nhận `InventoryReserved` rồi phát lại `OrderPlaced`:

~~~java
// Phản ví dụ minh họa - không thêm vào class demo.
@EventListener
public void onInventoryReserved(InventoryReserved event) {
    publisher.publishEvent(
        new OrderPlaced(
            event.meta().next("another-e1"), event.orderId()
        )
    );
}
~~~

Đồ thị lúc này có cạnh quay lại:

~~~text
OrderPlaced -> PaymentAuthorized -> InventoryReserved
      ^                                 |
      |---------------------------------|
~~~

Nếu thiếu guard, chuỗi đồng bộ có thể lồng sâu đến lỗi stack; chuỗi async có thể sinh quá nhiều tác vụ. Nhưng sửa tốt nhất không chỉ là thêm bộ đếm: về ngữ nghĩa, `InventoryReserved` không nên tự tuyên bố việc đặt đơn vừa xảy ra lần nữa. Hãy đưa bước tiếp theo vào orchestrator/command hoặc tạo **fact thực sự mới**.

## 6. Định danh để dựng lại quan hệ nguyên nhân–kết quả

Một listener nhận `InventoryReserved` không thể biết chính xác event nào gây ra nó nếu payload chỉ có `orderId`. Cùng đơn có thể có nhiều lần thử, retry, workflow song song hoặc thao tác bù.

| Metadata | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| `eventId` | Đối tượng event cụ thể nào? | `e3` |
| `correlationId` | Các event nào thuộc cùng một hành trình? | `order-42` |
| `causationId` | Event nào trực tiếp dẫn đến event này? | `e2` |
| `aggregateId` | Aggregate nghiệp vụ nào liên quan? | `42` |
| `hop` | Event đã đi qua bao nhiêu bước? | `2` |
| `occurredAt` | Fact nghiệp vụ được ghi nhận khi nào? | `2026-01-01T00:00:00Z` (ví dụ) |
| `schemaVersion` | Payload tuân theo phiên bản nào? | `v1` |
| `attempt` | Lần giao/thử xử lý thứ mấy? | `2` |

**Phân biệt ba ID quan trọng:** correlation ID nhóm cả workflow; causation ID chỉ event cha trực tiếp; event ID nhận diện chính event đang xét. Nếu nhiều event con do một event cha tạo ra, chúng có `eventId` khác nhau nhưng cùng `causationId`.

### 6.1. Log có cấu trúc

Log đơn giản như “handling event”, “payment done”, “inventory failed” không đủ để lần dấu. Nên ghi các trường:

~~~text
event=OrderPlaced eventId=e1 correlationId=order-42 causationId=root hop=0 status=handled
event=PaymentAuthorized eventId=e2 correlationId=order-42 causationId=e1 hop=1 status=handled
event=InventoryReserved eventId=e3 correlationId=order-42 causationId=e2 hop=2 status=failed
~~~

Nhóm theo `correlationId` và nối cạnh `causationId -> eventId` cho phép dựng causal graph, kể cả khi log đến không đúng thứ tự thời gian. Nên có log lúc publish, lúc handle bắt đầu, lúc handle thành công/thất bại và sau retry.

Trong production, dùng structured logging JSON và hệ thống tracing khi có. Không ghi token, số thẻ, payload nhạy cảm hoặc PII không cần thiết.

### 6.2. Phân biệt correlation với distributed tracing

`traceId`/`spanId` của OpenTelemetry hay Micrometer Observation phục vụ quan sát các khoảng thực thi. `correlationId` có thể là business workflow ID tồn tại lâu hơn một request/trace. Không giả định hai loại phải giống nhau.

Với `@Async`, message broker hoặc thread pool, Spring không tự chuyển **mọi** MDC/custom ThreadLocal/security context. Truyền tracing context có chọn lọc theo chính sách, nhưng **không sao chép transaction JDBC/JPA** sang worker thread.

Một log tốt có thể thêm `producer`, `consumer`, `thread`, `transactionPhase`, `durationMs`, `retryAttempt` và `topic/partition` khi thực sự tồn tại.

## 7. Vòng lặp và event storm: phòng ngừa từ topology

Có ba tình huống phổ biến.

### 7.1. Chu trình trực tiếp

~~~text
A -> B -> A -> B -> ...
~~~

Một handler nghe `OrderStatusChanged` rồi cập nhật lại cùng status và lại phát `OrderStatusChanged`. Nếu mọi lần xử lý đều tạo event mới, chuỗi không hội tụ.

### 7.2. Chu trình qua nhiều module

~~~text
OrderPlaced -> BillingRequested -> PaymentAuthorized
      ^                               |
      +---------- OrderUpdated -------+
~~~

Nếu mỗi module chỉ đọc code của mình, người viết có thể không nhận ra graph có chu trình.

### 7.3. Fan-out nhiều tầng

~~~text
                 +-> AuditRecorded
OrderPlaced -----+-> BillingRequested -> PaymentAuthorized
                 +-> NotificationQueued -> EmailAttempted
                 +-> ProjectionUpdated -> SearchIndexed
~~~

Không có vòng lặp vẫn có thể gây bùng nổ số task nếu mỗi handler tạo thêm nhiều event. Với queue/executor có giới hạn, cần chính sách backpressure, retry và xử lý trường hợp task bị từ chối.

### Những biện pháp quan trọng

1. **Chỉ publish khi có state transition mới.** Xử lý lại một event không tự là một fact nghiệp vụ mới.
2. **Vẽ và review đồ thị** khi thêm event/listener; phát hiện cycle trước khi triển khai.
3. **Giới hạn hop/TTL** theo workflow hoặc một số cạnh cụ thể, có log/alert khi vượt ngưỡng.
4. **Deduplicate theo event ID** ở consumer với lưu trữ bền vững khi cần; `Set` trong JVM không đủ cho nhiều node và restart.
5. **Dùng aggregate version/expected state** để chặn các transition lặp, ghi lùi hoặc cạnh tranh.
6. **Giới hạn retry** và có dead-letter/quarantine cho lỗi không thể phục hồi.
7. **Đặt giới hạn queue, worker, timeout**, có metrics và chính sách khi overload.
8. **Không publish event chỉ để báo “đã xử lý event”** trừ khi đó thật sự là domain fact có consumer cần đến.

Một bộ đếm hop chỉ là **cơ chế phòng vệ**, không thay thế mô hình nghiệp vụ đúng. Một vòng lặp có thể tự khởi tạo lại `hop=0` qua workflow mới nếu producer tùy tiện cấp ID.

## 8. Thứ tự listener, fan-in và điều kiện đồng bộ

Giả sử `OrderPlaced` có hai listener: một xử lý thanh toán, một xử lý kho. Cả hai phải hoàn tất trước khi đơn được giao cho vận hành.

~~~text
               +-> PaymentAuthorized --+
OrderPlaced ---+                       +-> FulfillmentReady
               +-> InventoryReserved --+
~~~

Không thể chỉ dùng `@Order` để biến hai nhánh thành “cùng thành công rồi mới phát”. `@Order` không thay cho một state machine có điều kiện. Trong async, thứ tự bắt đầu và hoàn tất còn không được bảo đảm chỉ vì annotation order.

Thay vào đó, một orchestrator/aggregate lưu trạng thái `paymentAuthorized` và `inventoryReserved`, áp dụng transition nguyên tử:

~~~text
if paymentAuthorized && inventoryReserved && !fulfillmentReady:
    markFulfillmentReady()
    emit(FulfillmentReady)
~~~

Đây là **pseudo-code**, không phải câu lệnh API Spring. Trong triển khai thật, cần bảo vệ race condition bằng transaction, optimistic locking, unique constraint hoặc cơ chế điều phối phù hợp. Tránh cả hai handler cùng thấy điều kiện đã đủ và phát event cuối hai lần.

## 9. Ranh giới transaction ảnh hưởng thế nào?

### 9.1. Chain đồng bộ trong một use case

Một method `@Transactional` có thể publish `OrderPlaced`, listener đồng bộ tiếp tục thao tác JDBC/JPA. Với cùng transaction manager và resource trên thread, các bước có thể **tham gia cùng transaction**. Nếu một handler sâu ném `RuntimeException` chưa xử lý, exception có thể truyền ngược về use case và gây rollback theo rollback rule.

Ví dụ:

~~~text
T1 BEGIN
  save(order)
  publish(OrderPlaced)
    -> auditListener
    -> paymentListener publishes PaymentAuthorized
       -> inventoryListener throws RuntimeException
T1 ROLLBACK (khi rule áp dụng)
~~~

Nhưng điều này **không tự đảm bảo** tất cả side effect đều rollback: email, HTTP, message broker, transaction `REQUIRES_NEW` và async worker có ranh giới riêng.

Nếu trừ tồn kho là điều kiện bắt buộc để tạo đơn, cân nhắc gọi service đồng bộ trong use case thay vì giấu nó trong một chuỗi listener mà lỗi có thể bị bắt/nuốt.

### 9.2. Sau commit

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` cho phép listener chỉ kích hoạt khi transaction đã commit thành công:

~~~java
@Component
public class SearchProjectionListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        projectionService.updateAfterCommit(event);
    }
}
~~~

Đây là mã **minh họa** cần kiểu event, bean và import tương ứng. Mặc định `@TransactionalEventListener` không gọi handler nếu event được publish **ngoài transaction**, trừ khi chọn `fallbackExecution=true`. Với tác vụ ghi DB trong after-commit, hãy mở transaction mới một cách có chủ đích, không giả định resource transaction gốc còn có thể commit thêm một lần.

Kết hợp `@Async` cho thân listener after-commit tạo công việc trên executor **không tự có transaction của publisher**. Exception task cũng không quay ngược làm rollback transaction nguồn đã commit.

### 9.3. Lỗi khi kết chuỗi các transactional listener

Một handler `AFTER_COMMIT` có thể publish event tiếp trong callback. Đừng tự động giả định một handler khác cũng dùng `@TransactionalEventListener(AFTER_COMMIT)` sẽ được kích hoạt cho event mới. Ở thời điểm callback, synchronization/transaction nguồn đã ở pha hoàn tất; event mới có thể **không được đăng ký vào một transaction active phù hợp**. Nên xác định rõ ranh giới hoặc mở transaction mới cho bước công việc tiếp theo theo đúng nghiệp vụ.

### 9.4. Nhiều transaction không phải một transaction tổng

~~~text
T1: OrderPlaced -> COMMIT
T2: PaymentAuthorized -> COMMIT
T3: InventoryReserved -> FAIL
~~~

Thất bại của T3 không tự rollback T1/T2 đã commit. Nếu business cần khôi phục, dùng retry hoặc **compensating action** theo quy trình rõ ràng. Một chuỗi event dài vượt nhiều transaction phù hợp với eventual consistency hoặc saga được điều phối, không thể mô tả như một lời gọi nguyên tử duy nhất.

## 10. Replay: Spring ApplicationEvent không tự lưu lịch sử

`ApplicationEventPublisher` dùng để phát event trong `ApplicationContext`. Nó **không tự là event store, không tự duy trì event log bền vững, không tự replay sau restart**. Khi muốn phát lại để dựng lại projection hoặc phục hồi workflow, cần nguồn dữ liệu đã lưu như event store, outbox hoặc log/broker có chính sách retention.

Hai loại replay rất khác:

- **Rebuild projection** từ những fact lịch sử đã xảy ra: cần chạy projector, không phát sinh side effect nghiệp vụ mới.
- **Resume workflow** đang dở: cần biết bước nào đã commit, bước nào đang thử, bước nào cần retry/compensate.

Nếu replay toàn bộ `OrderPlaced` qua cùng đường live và mọi listener lại phát các event con, một lần rebuild tìm kiếm có thể vô tình gửi email hoặc gọi thanh toán thêm lần nữa.

~~~text
Stored OrderPlaced (historical)
        |
        +-> Rebuild search projection    [mong muốn]
        +-> Send confirmation email     [không mong muốn]
        +-> Charge payment              [nguy hiểm]
~~~

Giải pháp thường đáng tin hơn là **tách pipeline replay projection** khỏi pipeline thực thi side effect. Một cờ `isReplay` trong payload không đủ nếu các listener quên kiểm tra hoặc vẫn chạy code gọi external API.

### 10.1. Event mới, duplicate và retry

- **Event mới:** một state transition mới với `eventId` mới.
- **Duplicate delivery:** cùng `eventId` được giao lại; không phải fact mới.
- **Retry:** thêm `attempt` hoặc delivery metadata, nhưng không tự đổi identity của fact gốc.
- **Replay lịch sử:** đọc lại event đã lưu, giữ identity phù hợp để projector khôi phục trạng thái.
- **Compensation:** tạo một fact mới, ví dụ `PaymentRefunded`, không xóa lịch sử `PaymentCaptured`.

Consumer cần thiết kế **idempotent**. Trong một số trường hợp có thể dùng bảng `processed_event` với unique key theo `consumer + eventId`, ghi trạng thái xử lý trong cùng transaction với cập nhật projection. Khi có side effect ngoài database, cần chính sách riêng vì transaction DB không rollback email/payment.

### 10.2. Checklist replay

| Vấn đề | Câu hỏi |
| --- | --- |
| Nguồn | Event lưu ở đâu, có đủ lịch sử không? |
| Thứ tự | Có sequence/version theo aggregate không? |
| Phạm vi | Replay theo aggregate, partition hay time window? |
| Schema | Handler mới đọc được các version cũ không? |
| Consumer | Handler nào được phép chạy khi rebuild? |
| Side effect | Đã ngăn gửi email/charge/reserve lại chưa? |
| Checkpoint | Có thể resume sau crash mà không bắt đầu lại toàn bộ? |
| Dedup | Có khóa bền vững để xử lý event nhận trùng? |
| Giám sát | Có replay run ID, progress và cảnh báo? |
| Rollback | Có thể quay lại projection cũ nếu rebuild sai không? |

**Đừng đánh đồng một integration test gọi `publishEvent` hai lần với chứng minh hệ thống replay an toàn.** Replay thật bao gồm data lịch sử, version, ordering, restart và idempotency.

## 11. Choreography và orchestration: khi nào nên đổi hướng?

**Choreography**: các listener tự phản ứng với fact và đôi khi publish event tiếp, không có một thành phần điều phối trung tâm. Nó hữu ích cho các side effect độc lập như audit, cập nhật cache hay thông báo phụ trợ.

**Orchestration**: một workflow owner/state machine nắm trạng thái, phát command tới các bước và nhận kết quả để quyết định bước tiếp. Nó hữu ích khi quy trình có nhiều điều kiện, retry, timeout, nhánh thất bại hoặc compensation.

| Nhu cầu | Hướng thiết kế nên cân nhắc |
| --- | --- |
| Một vài listener cập nhật view độc lập | Choreography qua domain event |
| Một bất biến bắt buộc trong cùng transaction | Direct service call trong use case |
| Chuỗi nhiều bước có nhánh rollback/bù | Orchestrator hoặc saga/state machine |
| Các bước qua nhiều service | Command/event qua broker, outbox, idempotency |
| Rebuild read model từ lịch sử | Projector riêng đọc event store |
| Gửi thông báo sau commit | Transaction-bound event và failure policy |
| Hai nhánh phải cùng thành công trước bước sau | Aggregate/workflow trạng thái rõ ràng |

Nếu phải mở hơn chục listener để hiểu một request hoàn tất như thế nào, hoặc không ai có trách nhiệm trả lời “nếu thanh toán thành công nhưng giữ kho thất bại thì sao”, event chain đang mang một workflow khó theo dõi. Không cần loại bỏ event; hãy xác định chủ sở hữu điều phối và giữ event làm **thông báo fact**, không phải cách giấu command.

## 12. Logging, metrics và tracing cho chuỗi dài

Một chiến lược quan sát tối thiểu gồm:

1. Ghi structured log tại **publish**, **handle start**, **handle success**, **handle failure**.
2. Log `eventId`, `correlationId`, `causationId`, `aggregateId` và `hop` để dựng graph.
3. Theo dõi latency **end-to-end** của workflow; latency HTTP không phản ánh các task async sau response.
4. Đếm event theo loại, listener exception, retry, dedup và event bỏ qua.
5. Đo executor queue depth, active workers, rejected tasks và dead-letter khi có.
6. Dùng tracing qua span cho handler và publish nếu công cụ hỗ trợ; truyền context đúng qua async boundary.
7. Cảnh báo số hop bất thường, fan-out quá lớn, cycle hoặc cùng event xử lý lặp nhiều lần.

Tên dưới đây là **ví dụ về metrics tự định nghĩa**, không phải các metric Spring tự sinh:

~~~text
app_event_published_total{type="OrderPlaced"}
app_event_listener_duration_seconds{listener="PaymentStep"}
app_event_listener_failures_total{type="InventoryReserved"}
app_event_chain_hops_max{workflow="order"}
app_event_deduplicated_total{consumer="projection"}
app_event_executor_rejections_total{executor="events"}
~~~

Không đặt `eventId` hoặc `orderId` làm Prometheus label vì sẽ tạo **high cardinality**. Các ID duy nhất nên nằm trong logs/traces, còn metric labels nên có tập giá trị nhỏ (event type, consumer, status).

### Dựng lại causal graph

Ví dụ từ log:

~~~text
e1 OrderPlaced
  |
  +-- e2 PaymentAuthorized
        |
        +-- e3 InventoryReserved
              |
              +-- e4 FulfillmentReady
~~~

Các cạnh được xây từ `causationId`, không suy đoán từ timestamp. Với fan-out, một parent có thể có nhiều event con. Với async, log có thể tới sai thứ tự nhưng graph vẫn mô tả được đường nguyên nhân.

## 13. Kiểm thử để phát hiện độ phức tạp ẩn

Ngoài unit test trực tiếp từng handler, cần integration test dùng Spring event dispatch thật.

| Test | Điều cần chứng minh |
| --- | --- |
| Chuỗi bốn tầng đồng bộ | Dòng log và metadata như ví dụ; event cuối dừng |
| Một listener ném exception | Có đúng policy xử lý lỗi và rollback nguồn không? |
| Có hai listener nghe cùng event | Không dựa sai vào thứ tự hoàn tất |
| Một listener chuyển sang `@Async` | Caller không mặc nhiên đợi task; lỗi task có giám sát |
| Thêm cạnh quay ngược graph | Guard phát hiện vòng lặp hoặc vượt hop |
| Phát lại cùng `eventId` | Consumer idempotent, không có side effect trùng |
| Hai event cùng aggregate đảo thứ tự | Projection kiểm tra version/sequence |
| Executor từ chối task | Có chính sách backpressure/failure rõ |
| Publish rồi rollback T1 | Handler `AFTER_COMMIT` không thực thi cho event đó |
| Crash sau commit | Outbox/retry phục hồi công việc cần giao |
| Fan-out nhiều tầng | Tải không vượt queue/worker budget |
| Rebuild projection từ log | Không vô tình gửi email/charge payment |

Không sử dụng `Thread.sleep(...)` rồi đoán listener async đã xong. Dùng latch, future, công cụ chờ có timeout hoặc tín hiệu hoàn tất từ hệ thống. Với test transaction, cần để transaction thực sự commit/rollback trước khi khẳng định dữ liệu đã bền vững.

### Kiểm tra topology bằng câu hỏi

- Listener nào tạo event mới qua `publishEvent` hoặc return value?
- Có path nào đi từ loại event A trở về A?
- Có bước nào được trigger nhiều lần với cùng aggregate version?
- Có handler gây side effect mà không kiểm tra duplicate?
- Có listener after-commit publish event mới rồi listener tiếp cũng đòi transaction-bound callback?
- Khi một nhánh lỗi, ai sở hữu trạng thái retry/compensation?
- Có dùng `@Order` như một bảo đảm sai về distributed ordering?

Tự động quét annotation có thể trợ giúp, nhưng không thể thay thế việc hiểu các publish phát sinh từ điều kiện runtime.

## 14. Lỗi thường gặp và cách sửa

1. **Chuỗi quá dài nhưng không có owner:** chuyển phần workflow có trạng thái sang orchestrator hoặc use case rõ ràng.
2. **Không có causation ID:** chỉ biết các event cùng đơn, không biết cha trực tiếp. Chuẩn hóa metadata.
3. **Dựa vào timestamp để suy thứ tự:** async có thể hoàn tất đảo chiều. Dùng causation, sequence và trace.
4. **Một event tự phát lại qua listener khác:** loop gây tràn stack hoặc storm task. Sửa graph và transition guard.
5. **Bỏ qua fan-out:** theo dõi số event/task được tạo từ một input và giới hạn tài nguyên.
6. **Nhầm `@Order` với thứ tự hoàn thành:** không có bảo đảm toàn chuỗi qua executor/broker.
7. **Cho rằng sync event chain tự atomic:** chỉ đúng khi resource và transaction phù hợp; external side effect không rollback.
8. **Cho rằng async listener cùng T1:** transaction imperative thường gắn thread; worker có ranh giới riêng.
9. **Cho rằng after-commit là durable delivery:** crash và lỗi executor vẫn có thể mất việc; dùng transactional outbox nếu không được mất.
10. **Replay qua pipeline live:** vô tình gọi lại payment/email. Tách projector rebuild.
11. **Không dedup khi retry:** consumer có thể cập nhật trùng. Lưu processed-event key hoặc policy idempotent.
12. **Chỉ dùng biến boolean của một JVM để chống duplicate cluster:** không bền vững hoặc liên tiến trình.
13. **Nuốt lỗi trong listener:** workflow im lặng thất bại. Có log, metric, retry và alert rõ.
14. **Không version event schema:** replay event cũ qua handler mới gây sai dữ liệu.
15. **Quá nhiều event kỹ thuật không có giá trị domain:** tên `RecordTouched` hoặc `CacheUpdated` có thể làm graph nhiễu; cần lý do consumer thật.
16. **Chỉ đo latency request:** task async sau response vẫn có thể chạy lâu.
17. **Không đánh dấu môi trường replay:** side effect bị kích hoạt sai và khó đối chiếu.
18. **Không có policy khi hop vượt budget:** event storm chỉ được phát hiện khi hệ thống nghẽn.

## 15. Bài tập thực hành

1. `OrderPlaced -> PaymentAuthorized -> OrderPlaced` là một chu trình. Điều gì có thể xảy ra trong dispatch đồng bộ và async?
2. Vì sao `correlationId` không thể thay thế `causationId` khi một event có hai event con?
3. Trong demo, tại sao `MAIN publishEvent returned` đứng sau bốn dòng log? Điều gì đổi nếu `Step2` được chạy async?
4. Một consumer nhận cùng `eventId` ba lần do retry. Đây là ba domain fact hay ba delivery attempt?
5. Một quy trình chỉ được ship sau khi cả payment và inventory thành công. Tại sao `@Order` không phải cơ chế fan-in phù hợp?
6. Nếu T1 commit, T2 commit nhưng T3 thất bại, có thể rollback cả ba bằng transaction của T3 không?
7. `@TransactionalEventListener(AFTER_COMMIT)` giải quyết thời điểm nào, và vì sao chưa đủ bảo đảm không mất event?
8. Khi replay một triệu `OrderPlaced` để xây lại search index, làm sao ngăn gửi email lần hai?
9. Vì sao `app_event_count{eventId="e1"}` là metric label không tốt?
10. Spring `ApplicationEventPublisher` có tự lưu event để replay sau restart không?

**Định hướng:** (1) tràn call stack hoặc event storm; (2) correlation nhóm workflow, causation chỉ parent; (3) nested sync dispatch, async làm caller không chờ; (4) ba lần giao của một fact; (5) cần aggregate/orchestrator và guard nguyên tử; (6) không, dùng compensation/retry; (7) chỉ sau commit nhưng không durable; (8) projector replay riêng, chặn side effect và idempotency; (9) cardinality cao; (10) không.

## 16. Tổng kết

Chuỗi event dài khó theo dõi vì đường điều khiển bị **phân tán qua nhiều listener**, các nhánh có thể chạy đồng bộ hoặc async và không nhất thiết chia sẻ transaction, ordering hay failure policy. Spring `@EventListener` giúp tách producer khỏi consumer, nhưng không tự cung cấp **causality, idempotency, replay, distributed tracing, durable delivery hoặc rollback toàn workflow**.

Các biện pháp có giá trị lớn nhất: giữ event là fact nghiệp vụ rõ, vẽ graph các publisher/listener, truyền `eventId`/`correlationId`/`causationId`, chặn cycle và fan-out, đặt ranh giới transaction rõ ràng, tách replay projection khỏi side effect, và dùng orchestration khi quy trình có trạng thái/nhánh bù phức tạp.

## Tài liệu tham khảo

- Spring Framework Reference — *Application Events and EventListener*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Javadoc — *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
