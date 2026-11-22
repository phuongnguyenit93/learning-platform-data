# Phân tách listener bắt buộc và listener phụ trong Spring Application Events

## 1. Bài toán và mục tiêu

Một sự kiện nghiệp vụ có thể kích hoạt nhiều tác vụ. Ví dụ, khi đơn hàng được xác nhận, hệ thống phải kiểm tra điều kiện hợp lệ/cập nhật trạng thái nhất quán, đồng thời có thể gửi thông báo, cập nhật thống kê và ghi nhận dữ liệu phân tích. Các tác vụ ấy không nên có cùng chính sách thất bại.

- **Listener bắt buộc (critical/required):** kết quả của tác vụ là điều kiện để thao tác chính được coi là thành công. Nếu lỗi, luồng chính phải biết và thường phải dừng hoặc rollback giao dịch. Ví dụ: kiểm tra quy tắc nghiệp vụ còn thiếu trước khi xác nhận đơn.
- **Listener phụ (auxiliary/best effort):** bổ sung hiệu ứng bên ngoài hoặc phục vụ quan sát, không quyết định tính hợp lệ của thao tác chính. Ví dụ: gửi email, đo lường, cập nhật cache có thể tái tạo. Lỗi phải được ghi nhận và xử lý theo chính sách riêng.
- **Tác vụ không thể mất (eventual but required):** không cần hoàn thành trước phản hồi chính, nhưng *phải được thực hiện cuối cùng*. Loại này cần cơ chế bền vững như transactional outbox và hàng đợi có retry, chứ không chỉ gắn nhãn “phụ” rồi dùng luồng bất đồng bộ trong bộ nhớ.

Mục tiêu của phân tách là xác định rõ: **ai có quyền làm thao tác chính thất bại, khi nào listener được gọi, khi nào tác vụ thực sự hoàn thành, và điều gì xảy ra khi transaction rollback**.

## 2. Nền tảng Spring: thứ tự gọi khác thứ tự hoàn thành

Spring phát sự kiện trong ứng dụng bằng **ApplicationEventPublisher.publishEvent(...)**. Bean có phương thức **@EventListener** nhận loại sự kiện phù hợp. Với **SimpleApplicationEventMulticaster** mặc định, listener thông thường chạy **đồng bộ trên thread phát sự kiện**. Nếu listener đồng bộ ném RuntimeException và không có cơ chế xử lý lỗi riêng, lỗi truyền về publisher và việc dispatch các listener còn lại dừng tại đó.

**@Order(n)** điều khiển thứ tự *gọi listener* của cùng một event trong multicaster: số nhỏ được ưu tiên trước (ví dụ 10 trước 100). Không nên dựa vào thứ tự đăng ký bean hay vào thứ tự ngẫu nhiên của những listener có cùng order. **@Order không tạo một giao dịch, không buộc tất cả tác vụ thành công và không tự quản lý retry.**

**@Async** (khi cấu hình **@EnableAsync**) làm phương thức listener chạy trên executor: publisher thường chỉ cần lên lịch tác vụ rồi tiếp tục. Khi dùng **@Order(10)** cho listener bắt buộc đồng bộ và **@Order(100)** cho listener phụ **@Async**, multicaster mặc định sẽ gọi xong listener bắt buộc trước khi *lên lịch* listener phụ. Điều này **không** bảo đảm tác vụ phụ hoàn thành sau mọi công việc khác, hay kết quả phụ xuất hiện theo thứ tự giữa nhiều event.

| Khía cạnh | Bắt buộc đồng bộ | Phụ bất đồng bộ |
| --- | --- | --- |
| Vai trò | Bảo vệ tính đúng đắn của thao tác chính | Thông báo, phân tích, cập nhật có thể phục hồi |
| Thời điểm | Trước khi publisher trả về, nếu được dispatch | Có thể tiếp tục sau khi publisher trả về |
| Lỗi RuntimeException | Truyền về publisher theo cấu hình mặc định | Không truyền trực tiếp về publisher; cần log, monitor, retry |
| Transaction ở thread phát | Có thể tham gia transaction đang mở | Không tự kế thừa transaction/thread context |
| @Order | Giúp định thứ tự gọi listener đồng bộ | Chỉ giúp định thứ tự dispatch/lên lịch; không đảm bảo thứ tự kết thúc |
| Độ bền | Phụ thuộc giao dịch và nơi thực hiện hiệu ứng | Mất việc nếu tiến trình dừng hoặc tác vụ chưa được lưu bền vững |

Nếu cấu hình **applicationEventMulticaster** với executor chạy bất đồng bộ cho mọi listener, giả định “required chạy trước, lỗi trả về publisher” có thể không còn đúng. Với bất biến quan trọng, giữ listener bắt buộc đồng bộ hoặc gọi logic bắt buộc trực tiếp trong service. Không đặt **@Async** lên listener bắt buộc.

## 3. Luồng xử lý và chính sách thất bại

~~~text
publisher.publishEvent(OrderAccepted)
        |
        v
@EventListener @Order(10): REQUIRED, đồng bộ
        |-- lỗi --> exception về publisher, dừng dispatch tiếp
        |
        | thành công
        v
@EventListener @Order(100) @Async: AUXILIARY
        |-- lịch chạy trên executor --> publisher có thể tiếp tục
                                      |
                                      +--> lỗi phụ được ghi log/retry riêng
~~~

Trong mô hình trên, listener phụ được *lên lịch* sau khi listener bắt buộc trả về thành công. Nếu listener phụ tự phát sinh lỗi, lỗi đó không được biến thành “đơn hàng không hợp lệ”. Nếu chính việc đưa tác vụ vào executor bị từ chối (ví dụ hàng đợi đầy), đó vẫn có thể là lỗi tại thời điểm dispatch; phải đặt chính sách chống quá tải rõ ràng và quan sát lỗi submit.

**Ranh giới trách nhiệm nên được xác định trước khi viết code:**

1. Quy tắc hợp lệ, kiểm tra bắt buộc và thay đổi trạng thái nhất quán: xử lý đồng bộ trong luồng nghiệp vụ và transaction tương ứng.
2. Gửi thông báo chỉ khi dữ liệu đã commit: xử lý sau commit bằng **@TransactionalEventListener(phase = AFTER_COMMIT)**.
3. Tác vụ phụ được phép thất bại tạm thời: chạy bất đồng bộ có giám sát, hoặc dùng hệ thống queue nếu cần retry lâu dài.
4. Hiệu ứng bên ngoài không thể quay lui (email/API bên thứ ba): không giả định rollback cơ sở dữ liệu sẽ hoàn tác hiệu ứng đó.

## 4. Ví dụ Java 17+ chạy độc lập với Spring Framework

Ví dụ dưới đây dùng **Spring Framework 6.2.9**, Java 17 và Gradle. Nó minh họa **thứ tự dispatch** và đường truyền exception; *chưa sử dụng transaction hay cơ sở dữ liệu*. Một listener bắt buộc kiểm tra đơn; listener phụ chạy trên executor. Latch chỉ phục vụ demo để đợi log phụ, không phải cơ chế triển khai nghiệp vụ.

Cấu trúc:

~~~text
event-demo/
  build.gradle
  src/main/java/demo/EventSplitDemo.java
~~~

Nội dung **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.EventSplitDemo'
}
~~~

Nội dung **src/main/java/demo/EventSplitDemo.java**:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EventSplitDemo {
    public record OrderAccepted(String orderId, boolean reject) {}

    public static class DoneSignal {
        final CountDownLatch finished = new CountDownLatch(1);
    }

    public static class RequiredListener {
        @EventListener
        @Order(10)
        public void on(OrderAccepted event) {
            System.out.println("required: " + event.orderId());
            if (event.reject()) {
                throw new IllegalStateException("mandatory check failed");
            }
        }
    }

    public static class AuxiliaryListener {
        private final DoneSignal signal;

        public AuxiliaryListener(DoneSignal signal) {
            this.signal = signal;
        }

        @EventListener
        @Order(100)
        @Async("auxiliaryExecutor")
        public void on(OrderAccepted event) {
            try {
                System.out.println("auxiliary: " + event.orderId());
            } finally {
                signal.finished.countDown();
            }
        }
    }

    @Configuration
    @EnableAsync
    public static class DemoConfig {
        @Bean
        DoneSignal doneSignal() {
            return new DoneSignal();
        }

        @Bean
        RequiredListener requiredListener() {
            return new RequiredListener();
        }

        @Bean
        AuxiliaryListener auxiliaryListener(DoneSignal signal) {
            return new AuxiliaryListener(signal);
        }

        @Bean("auxiliaryExecutor")
        ThreadPoolTaskExecutor auxiliaryExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(100);
            executor.setThreadNamePrefix("aux-");
            executor.initialize();
            return executor;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {

            context.publishEvent(new OrderAccepted("ORD-1", false));

            boolean completed = context.getBean(DoneSignal.class)
                    .finished.await(5, TimeUnit.SECONDS);
            if (!completed) {
                throw new IllegalStateException("auxiliary timeout");
            }
            System.out.println("optional-completed=true");

            try {
                context.publishEvent(new OrderAccepted("ORD-2", true));
            } catch (IllegalStateException ex) {
                System.out.println("publisher-caught=" + ex.getMessage());
            }
        }
    }
}
~~~

Từ thư mục **event-demo**, chạy bằng Gradle 8.x với JDK 17+ đã cài:

~~~bash
gradle --console=plain -q run
~~~

Các dòng do chương trình in ra khi executor xử lý bình thường:

~~~text
required: ORD-1
auxiliary: ORD-1
optional-completed=true
required: ORD-2
publisher-caught=mandatory check failed
~~~

Giải thích:

- Với **ORD-1**, required listener hoàn tất; sau đó auxiliary được lên lịch. Main đợi latch nên dòng xác nhận chỉ xuất hiện sau khi auxiliary đã in thông báo.
- Với **ORD-2**, required listener ném **IllegalStateException**; publisher bắt được exception. Auxiliary không được dispatch cho **ORD-2** vì listener bắt buộc lỗi trước, trong cấu hình mặc định và hai listener của ví dụ.
- Nếu xóa latch, dòng log auxiliary có thể xuất hiện trước hoặc sau khi publisher làm việc kế tiếp; **@Order(100)** không biến async thành sync.
- Nếu required listener đã ghi dữ liệu bên ngoài transaction, exception ở đây **không tự hoàn tác** những gì đã ghi. Muốn rollback DB cần một transaction thật và điều kiện rollback phù hợp.

## 5. Khi có transaction: tách bước bắt buộc khỏi hiệu ứng sau commit

Trong hệ thống có **@Transactional**, rủi ro thường gặp là phát event ngay khi đang lưu đơn hàng, rồi listener phụ gửi email khi transaction chưa commit. Nếu lưu DB rollback, người dùng có thể đã nhận email xác nhận cho đơn không tồn tại.

Thiết kế ưu tiên: service thực hiện tác vụ bắt buộc trong cùng transaction; event công bố thông tin đã xảy ra và listener phụ chạy **AFTER_COMMIT**. Ví dụ sau là **đoạn minh họa kiến trúc**, giả định đã có **OrderRepository**, **OrderRequest**, **OrderPlaced**, **ValidationService** và cấu hình transaction/executor thích hợp; không phải chương trình độc lập như mục 4.

~~~java
@Service
class OrderService {
    private final ValidationService validation;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderService(ValidationService validation,
                 OrderRepository orders,
                 ApplicationEventPublisher events) {
        this.validation = validation;
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void place(OrderRequest request) {
        validation.checkAndReserve(request);   // bắt buộc, đồng bộ
        Order saved = orders.save(new Order(request));
        events.publishEvent(new OrderPlaced(saved.getId()));
    }
}

@Component
class OrderNotificationListener {
    @Async("auxiliaryExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        // Gửi thông báo; có log, theo dõi lỗi và chính sách retry riêng.
    }
}
~~~

Import tương ứng cho đoạn minh họa: **org.springframework.stereotype.Service**, **org.springframework.stereotype.Component**, **org.springframework.context.ApplicationEventPublisher**, **org.springframework.transaction.annotation.Transactional**, **org.springframework.transaction.event.TransactionalEventListener**, **org.springframework.transaction.event.TransactionPhase** và **org.springframework.scheduling.annotation.Async**.

Các mốc thời gian phải hiểu đúng:

| Mốc | Ý nghĩa đối với required và auxiliary |
| --- | --- |
| **Trong @Transactional** | Bước bắt buộc làm thay đổi DB tham gia transaction nếu dùng cùng transaction manager và luồng thực thi phù hợp. RuntimeException không bị nuốt thường dẫn tới rollback theo quy tắc mặc định của Spring. |
| **@TransactionalEventListener(BEFORE_COMMIT)** | Callback chạy trước commit; chỉ dùng khi thực sự cần ràng buộc vào giai đoạn này. Lỗi callback có thể làm commit thất bại. Không dùng để gửi email khó hoàn tác. |
| **@TransactionalEventListener(AFTER_COMMIT)** | Chỉ gọi sau commit thành công. Nếu transaction rollback, listener này không chạy. Đây là lựa chọn thường dùng cho side effect phụ. |
| **AFTER_ROLLBACK / AFTER_COMPLETION** | Phù hợp cho cleanup, metric hoặc bù trừ có kiểm soát; không coi là một lượt commit thành công. |

**Lưu ý quan trọng:** **@TransactionalEventListener** mặc định là **AFTER_COMMIT** và mặc định **không được gọi nếu không có transaction đang hoạt động**, trừ khi bật **fallbackExecution = true**. Không tùy tiện bật fallback chỉ để “listener luôn chạy”; như vậy có thể phá yêu cầu chỉ thực hiện sau commit.

Trong callback **AFTER_COMMIT**, transaction chính đã commit. Nếu callback cần **ghi DB bằng một transaction mới**, gọi một service qua Spring proxy có **@Transactional(propagation = Propagation.REQUIRES_NEW)** (hoặc thiết kế tương đương), vì tài nguyên giao dịch cũ có thể còn gắn thread nhưng không có lần commit tiếp theo. Với **@Async**, luồng phụ cũng không tự nhận transaction của thread phát event; cần xác định rõ transaction của thao tác ghi trên luồng đó.

**Không bảo đảm tuyệt đối:** Event nội bộ Spring không được lưu bền vững. Kể cả AFTER_COMMIT + @Async, tiến trình có thể chết ngay sau commit nhưng trước khi listener xử lý. Nếu “phải gửi thông báo ít nhất một lần” là yêu cầu thực, ghi **outbox record trong cùng DB transaction** với đơn hàng, rồi có worker/queue đọc outbox, retry, ghi trạng thái xử lý và dùng khóa idempotency để tránh xử lý trùng.

## 6. Chọn chính sách theo mức độ quan trọng

| Yêu cầu thật sự | Cách tổ chức phù hợp | Cách xử lý lỗi |
| --- | --- | --- |
| Đơn không được thành công nếu kiểm tra tồn kho thất bại | Gọi service đồng bộ trong transaction; hoặc listener bắt buộc đồng bộ có order rõ ràng | Ném lỗi cho publisher; rollback khi đã cấu hình transaction phù hợp |
| Thống kê/ghi log phụ không ảnh hưởng kết quả | Listener phụ độc lập, có thể @Async | Ghi log lỗi, metric, cảnh báo; tùy mức độ mà retry |
| Chỉ gửi email khi đơn commit thành công | AFTER_COMMIT; có thể kết hợp @Async | Email lỗi không đảo ngược commit; giám sát và retry |
| Phải giao việc cho hệ thống khác dù JVM bị dừng | Transactional outbox + queue/worker | Lưu bền vững, retry với backoff, idempotency, xử lý dead-letter |
| B cần dùng kết quả của A ngay lập tức | Gọi A rồi B tuần tự trong service; hoặc synchronous ordered listeners khi có lý do hợp lý | Không dùng @Async chỉ dựa vào @Order |

Với nhiều listener bắt buộc, **@Order(10), @Order(20), ...** diễn đạt thứ tự gọi. Nhưng nếu đầu ra của bước B phụ thuộc chặt vào A hoặc cần một kết quả trả về, orchestration trực tiếp trong service thường dễ đọc, test và bảo đảm hơn event listener. **@EventListener** phù hợp nhất cho các phản ứng tách rời, không phải thay thế mọi lời gọi hàm nghiệp vụ.

## 7. Lỗi thiết kế thường gặp

1. **Đặt @Async lên required listener:** lỗi xảy ra trên executor, publisher tưởng đã thành công; tính nhất quán bị phá vỡ.
2. **Cho rằng @Order bảo đảm thứ tự hoàn thành:** đúng về dispatch trong multicaster đồng bộ, không đúng về việc hai tác vụ async hoàn tất lúc nào.
3. **Cấu hình executor toàn cục cho applicationEventMulticaster mà quên tác động:** các listener thông thường có thể không còn chạy ở thread phát event và không còn chia sẻ transaction context.
4. **Nuốt exception của required listener:** nếu bắt mọi lỗi rồi chỉ log, publisher không có tín hiệu để hủy thao tác.
5. **Để optional listener ném lỗi đồng bộ trước listener khác:** mặc định lỗi có thể ngăn các listener sau; tách thành listener riêng, xếp order hợp lý và xử lý lỗi theo yêu cầu nghiệp vụ.
6. **Gửi thông báo trước commit:** transaction có thể rollback sau khi email/API bên ngoài đã thành công.
7. **Dùng AFTER_COMMIT rồi kỳ vọng ghi DB tiếp trong transaction cũ:** phải tạo transaction mới khi thực sự cần một lần commit mới.
8. **Xem @Async là hệ thống bảo đảm giao việc:** executor trong bộ nhớ không đủ khi mất tiến trình, quá tải hoặc restart.
9. **Bỏ qua retry/idempotency:** xử lý lại có thể gửi email trùng hoặc tăng metric nhiều lần; cần khóa sự kiện và quy tắc xử lý trùng.
10. **Phụ thuộc ThreadLocal ở tác vụ async:** security context, transaction context, MDC và correlation ID không tự truyền theo mặc định; truyền dữ liệu cần thiết trong event hoặc cấu hình context propagation có kiểm soát.

## 8. Cách kiểm thử đúng thứ tự và ranh giới lỗi

- **Required thành công:** kiểm tra required được gọi trước khi dispatch auxiliary; publisher không báo lỗi. Không dùng sleep mù để khẳng định thứ tự async.
- **Required thất bại:** với multicaster mặc định và required có order sớm hơn, kiểm tra publisher nhận exception và auxiliary của event đó chưa được dispatch.
- **Auxiliary thất bại:** kiểm tra nghiệp vụ chính vẫn thành công theo chính sách đã chọn, đồng thời có log/metric và retry thích hợp.
- **Transaction rollback:** publish event trong một transaction rồi chủ động rollback; xác nhận **AFTER_COMMIT** không chạy.
- **Transaction commit:** xác nhận listener AFTER_COMMIT chỉ xử lý khi giao dịch hoàn tất thành công.
- **Executor quá tải / shutdown:** kiểm thử hành vi reject, quan sát được lỗi và cơ chế phục hồi; không mặc định mọi công việc đều được nhận.
- **Retry và trùng event:** kiểm thử idempotency với cùng **eventId** phát hai lần.

Khi test với **@Async**, dùng **CountDownLatch**, Future hoặc cơ chế đồng bộ có giới hạn thời gian. Khi test transaction, chạy với transaction manager/DB thực tế hoặc integration test phù hợp; không kết luận từ một unit test chỉ gọi thẳng method listener.

## 9. Nguyên tắc ghi nhớ

**Bắt buộc = nằm trên đường quyết định thành công và cần truyền lỗi rõ ràng. Phụ = được cách ly khỏi kết quả chính nhưng vẫn có chính sách xử lý lỗi.** Dùng **@Order** để diễn đạt thứ tự *gọi*; dùng **@Async** khi chấp nhận hoàn thành sau; dùng **@TransactionalEventListener** để diễn đạt pha giao dịch; dùng **outbox/queue** nếu yêu cầu giao việc bền vững. Không nhầm lẫn bốn công cụ này với nhau.

### Tài liệu chính thức

- Spring Framework, *Application Events, Asynchronous Listeners, Ordering Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Javadoc, *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Javadoc, *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
