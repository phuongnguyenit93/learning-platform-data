# ApplicationListener, @EventListener và xử lý sự kiện

## 1. Mục tiêu và phạm vi

Trong chương **Sự kiện aggregate** của module **Spring Data Commons**, bài này tập trung vào phía nhận sự kiện: đăng ký listener, chọn đúng kiểu dữ liệu và xử lý sự kiện theo yêu cầu nghiệp vụ.

Sau bài học, bạn cần làm được các việc sau:

- Viết listener bằng interface `ApplicationListener` hoặc annotation `@EventListener`.
- Nhận đúng payload khi aggregate phát một object hoặc record thông thường.
- Phân biệt publication, xử lý đồng bộ, xử lý bất đồng bộ và xử lý sau commit.
- Kiểm soát điều kiện lọc, thứ tự gọi và lỗi của listener.
- Kiểm tra việc định tuyến sự kiện bằng một Spring context nhỏ.

Ví dụ xuyên suốt là sự kiện xác nhận đơn hàng. Việc aggregate tạo sự kiện thuộc trách nhiệm domain; việc nhận sự kiện và gọi tác vụ ứng dụng thuộc trách nhiệm listener.

Các kiểu listener trong bài thuộc **Spring Framework**. Spring Data Commons cung cấp điểm tích hợp phát sự kiện từ aggregate qua repository. Mapping, khả năng repository và transaction vẫn phụ thuộc store.

## 2. Đặt listener vào đúng luồng xử lý

Có thể hình dung đường đi của một domain event như sau:

~~~text
Aggregate thực hiện hành vi
    -> đăng ký sự kiện chờ
    -> repository đi qua điểm tích hợp phát sự kiện
    -> ApplicationEventPublisher
    -> multicaster định tuyến tới các listener phù hợp
    -> listener gọi tác vụ ứng dụng
~~~

Một phương thức `@DomainEvents` cung cấp sự kiện cho hạ tầng repository; `@AfterDomainEventPublication` có thể dọn danh sách sau publication. Không cần đặt listener bên trong entity chỉ để nhận sự kiện đó.

Các điểm phát qua repository được mô tả trong [Spring Data Commons: Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html).

Để chẩn đoán một listener không chạy, cần tách hai câu hỏi: sự kiện đã được publication chưa, và listener có được đăng ký với kiểu phù hợp không.

Không phải mọi thay đổi ở database đều tạo domain event. Ví dụ, một query update trực tiếp không tự gọi phương thức nghiệp vụ trên aggregate.

## 3. Payload dùng trong các ví dụ

Các public type dưới đây được đặt trong file Java riêng khi đưa vào project. Ví dụ dùng Java 17 trở lên.

~~~java
package com.example.orderevents;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        String channel,
        Instant occurredAt) {

    public OrderConfirmed {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(channel, "channel");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (channel.isBlank()) {
            throw new IllegalArgumentException(
                    "channel must not be blank");
        }
    }
}
~~~

Payload có đủ dữ liệu cho các ví dụ: id sự kiện, id đơn, kênh bán và thời điểm nghiệp vụ. Nó không chứa một entity mutable hoặc một quan hệ lazy.

Tác vụ được listener gọi có hợp đồng:

~~~java
package com.example.orderevents;

public interface OrderConfirmationHandler {

    void handle(OrderConfirmed event);
}
~~~

Ứng dụng cần cung cấp một bean triển khai interface này. Nó có thể cập nhật dữ liệu phục vụ đọc hoặc thực hiện tác vụ khác theo thiết kế. Phần kiểm tra ở cuối bài cung cấp một implementation ghi nhận lời gọi, nên có thể chạy độc lập với database.

Cách tách này giúp listener tập trung vào tiếp nhận sự kiện; logic xử lý nằm trong một thành phần có thể kiểm tra riêng.

## 4. Cách một: triển khai ApplicationListener

### 4.1. Hiểu ràng buộc kiểu

`ApplicationListener<E>` yêu cầu `E` kế thừa `ApplicationEvent`. Nếu tự định nghĩa một class sự kiện kế thừa `ApplicationEvent`, có thể dùng class đó trực tiếp làm tham số kiểu.

Nhưng `OrderConfirmed` ở trên là record thông thường. Vì vậy, khai báo `ApplicationListener<OrderConfirmed>` không thỏa ràng buộc generic.

Xem [ApplicationListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationListener.html).

Khi publication một object không kế thừa `ApplicationEvent`, Spring bọc nó trong `PayloadApplicationEvent`. Listener theo interface có thể nhận wrapper với kiểu payload cụ thể.

### 4.2. Listener cho payload dạng record

~~~java
package com.example.orderevents;

import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.stereotype.Component;

@Component
public class InterfaceOrderListener
        implements ApplicationListener<
                PayloadApplicationEvent<OrderConfirmed>> {

    private final OrderConfirmationHandler handler;

    public InterfaceOrderListener(
            OrderConfirmationHandler handler) {
        this.handler = handler;
    }

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderConfirmed> event) {

        handler.handle(event.getPayload());
    }
}
~~~

Generic cụ thể giúp Spring định tuyến theo loại sự kiện. Không cần nhận mọi `ApplicationEvent` rồi tự ép kiểu trong thân method.

`getPayload()` trả về `OrderConfirmed`. Trong khi đó, `getSource()` thuộc wrapper và không có hợp đồng rằng nó là aggregate đã xác nhận đơn.

Tương tự, thời gian của wrapper không thay cho `occurredAt` do domain cung cấp. Hai mốc có thể đại diện cho hai thời điểm khác nhau.

Xem [PayloadApplicationEvent API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/PayloadApplicationEvent.html).

## 5. Cách hai: dùng @EventListener

Với annotation, method có thể nhận trực tiếp payload:

~~~java
package com.example.orderevents;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedOrderListener {

    private final OrderConfirmationHandler handler;

    public AnnotatedOrderListener(
            OrderConfirmationHandler handler) {
        this.handler = handler;
    }

    @EventListener
    public void onOrderConfirmed(
            OrderConfirmed event) {

        handler.handle(event);
    }
}
~~~

Không cần tự lấy `PayloadApplicationEvent` trong method này. Spring hỗ trợ listener nhận object được publication dù object đó không kế thừa `ApplicationEvent`.

Một method nhận một loại sự kiện dùng một tham số sự kiện. Dependency khác, như repository hoặc service, nên được inject vào bean thay vì thêm tùy ý vào danh sách tham số của method nhận sự kiện.

Xem [EventListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html).

### 5.1. Điều kiện để method được đăng ký

Class phải là bean được Spring quản lý, chẳng hạn được component scan hoặc khai báo trong cấu hình. Đặt annotation trên một object tự tạo bằng `new` rồi không đăng ký vào context chưa tạo được listener.

Tên method có thể tùy chọn; kiểu tham số mới là một phần của hợp đồng định tuyến.

### 5.2. Chọn cách viết cho cùng một tác vụ

| Tiêu chí | ApplicationListener | @EventListener |
| --- | --- | --- |
| Hợp đồng Java | Triển khai interface | Đánh dấu method trên bean |
| Method tiếp nhận | `onApplicationEvent` | Tên method tùy chọn |
| Record trong ví dụ | Nhận qua wrapper có kiểu | Nhận trực tiếp record |
| Nhiều loại sự kiện | Cần thiết kế kiểu listener phù hợp | Có thể tổ chức nhiều method |
| Điều khiển transaction, executor | Cần xét cấu hình liên quan | Cần xét cấu hình liên quan |

Hai class trong bài là **hai phương án thay thế cho cùng một vai trò**. Nếu cùng đăng ký cả hai và cùng trỏ tới một handler, handler sẽ được gọi hai lần cho một publication phù hợp.

Có nhiều listener độc lập cho một sự kiện là hợp lệ. Điều cần tránh là vô tình đăng ký trùng cùng một tác vụ rồi cho rằng framework tự chọn một listener.

## 6. Phát thử sự kiện và nối với aggregate

Trong một bean đã inject `ApplicationEventPublisher publisher`, có thể phát thử:

~~~java
publisher.publishEvent(new OrderConfirmed(
        UUID.randomUUID(),
        UUID.randomUUID(),
        "WEB",
        Instant.parse("2026-02-10T08:30:00Z")));
~~~

Đoạn này kiểm tra đường tiếp nhận của listener, chưa chứng minh đường repository đã tạo và phát đúng domain event.

`publishEvent` chuyển giao cho hạ tầng multicaster; bản thân hợp đồng publisher không cam kết mọi cấu hình đều thực thi đồng bộ hoặc ngay lập tức. Object thông thường được bọc thành payload event. Xem [ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html).

Trong luồng dùng aggregate events, một phương thức nghiệp vụ có thể đăng ký `OrderConfirmed`, sau đó service lưu root qua repository phù hợp. Listener ở mục 4 hoặc 5 nhận cùng kiểu payload.

Không phát thủ công lại cùng sự kiện sau `repository.save` nếu repository đã publication nó. Nếu làm vậy, lỗi xử lý hai lần nằm ở thiết kế nguồn phát chứ không phải ở bộ lọc kiểu của listener.

## 7. Đồng bộ: thời gian chạy và lỗi cùng ảnh hưởng caller

Với `SimpleApplicationEventMulticaster` mặc định, listener được gọi trên thread publication. Khi không có executor hay cấu hình bất đồng bộ khác, công việc của listener góp vào thời gian chờ của caller.

~~~text
Caller publication
    -> listener A
    -> listener B
    -> publication trả về
~~~

Sơ đồ chỉ minh họa xử lý tuần tự theo cấu hình đồng bộ, chưa chỉ định thứ tự A/B nếu chưa có quy tắc sắp xếp.

Theo cấu hình mặc định không có error handler tùy biến, exception của listener có thể dừng lượt multicast và truyền về publisher. Xem [SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html).

Ví dụ handler từ chối xử lý một xác nhận do dữ liệu không hợp lệ. Với listener đồng bộ, caller có thể nhận lỗi từ publication. Nếu publication đang nằm trong một transaction, kết quả rollback còn chịu quy tắc transaction áp dụng cho lỗi đó.

Không giả định tất cả listener luôn được chạy hết sau khi một listener trước đã ném lỗi. Cũng không cho rằng một tác động ngoài database, như một request HTTP đã thành công, sẽ tự được hoàn tác khi transaction database rollback.

Listener nên có trách nhiệm và chính sách lỗi rõ ràng:

| Loại xử lý | Câu hỏi cần trả lời |
| --- | --- |
| Tác vụ là điều kiện của thao tác hiện tại | Lỗi có phải làm thao tác hiện tại thất bại không? |
| Tác vụ phụ, có thể chạy sau | Caller có cần chờ kết quả không? |
| Giao tiếp tới hệ thống khác | Cần lưu ý định gửi, retry và chống trùng thế nào? |

## 8. Lọc sự kiện và kiểm soát thứ tự

### 8.1. Dùng kiểu cụ thể trước

Method nhận `OrderConfirmed` thể hiện rõ sự quan tâm. Method nhận `Object` rộng hơn nhiều và có thể nhận những sự kiện ngoài nghiệp vụ đơn hàng.

Chọn kiểu đủ cụ thể giúp tránh kiểm tra và ép kiểu thủ công ở nhiều nơi.

### 8.2. Dùng condition cho điều kiện đơn giản

Một phương án thay cho listener không có điều kiện:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void onWebOrderConfirmed(
        OrderConfirmed event) {

    handler.handle(event);
}
~~~

`#a0` chỉ tham số đầu tiên, nên không phụ thuộc tên tham số có được giữ trong bytecode hay không. Method record `channel()` trả về kênh của payload.

Với payload thông thường, `#root.event` là sự kiện Spring nền bên dưới; nó không luôn là cùng object với tham số payload của method. Dùng `#a0` làm cho ý định lọc payload rõ hơn.

Cơ chế điều kiện được mô tả trong [Spring Framework: Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation).

Nếu quy tắc có nhiều nhánh, cần tra cứu dữ liệu hoặc có ý nghĩa nghiệp vụ quan trọng, hãy đặt nó trong mã xử lý có thể kiểm tra trực tiếp. Một chuỗi SpEL dài khiến việc theo dõi quyết định xử lý khó hơn.

### 8.3. Order là thứ tự gọi, không phải workflow bền vững

Có thể đặt thứ tự cho method listener:

~~~java
import org.springframework.core.annotation.Order;

@Order(20)
@EventListener
public void observeConfirmation(
        OrderConfirmed event) {

    handler.handle(event);
}
~~~

Giá trị order nhỏ hơn có độ ưu tiên trước. Với listener theo interface, có thể triển khai `Ordered` để cung cấp thứ tự.

Thứ tự gọi không tự bảo đảm thứ tự hoàn tất khi công việc được chuyển sang executor. Nó cũng không tạo thứ tự toàn cục giữa nhiều request hoặc nhiều instance ứng dụng.

Nếu bước B bắt buộc dùng kết quả của bước A trong cùng một nghiệp vụ, service điều phối tường minh thường giúp thể hiện quan hệ đó rõ hơn là phụ thuộc ngầm giữa hai listener.

## 9. Cẩn thận với giá trị trả về của @EventListener

Một listener thường có kiểu trả về khác `void` có thể tạo sự kiện tiếp theo từ kết quả trả về. Ví dụ, với record:

~~~java
public record OrderConfirmationHandled(
        UUID sourceEventId,
        UUID orderId) {
}
~~~

Một phương án listener đồng bộ:

~~~java
@EventListener
public OrderConfirmationHandled onConfirmed(
        OrderConfirmed event) {

    handler.handle(event);

    return new OrderConfirmationHandled(
            event.eventId(),
            event.orderId());
}
~~~

Đây là phương án thay cho method `void` của cùng vai trò, không phải method cần đăng ký thêm để xử lý lại cùng tác vụ.

Dùng kết quả trả về như một giá trị đáp ứng HTTP thông thường sẽ gây hiểu nhầm: ở đây kết quả tham gia cơ chế event. Array hoặc collection trả về có thể được publication thành từng sự kiện riêng.

Đặc biệt, nếu listener nhận một loại sự kiện rồi trả lại chính sự kiện đó, có thể tạo vòng publication lặp. Chỉ trả về sự kiện tiếp theo khi đó là chủ đích thiết kế; dùng `void` khi chỉ cần thực hiện tác vụ.

Cơ chế phát qua giá trị trả về này không áp dụng cho method listener bất đồng bộ. Nếu cần phát tiếp trong công việc bất đồng bộ, phải dùng publisher tường minh và thiết kế vòng đời riêng.

## 10. Bất đồng bộ là một lựa chọn thực thi riêng

Để method chạy qua hạ tầng `@Async`, ứng dụng cần bật hỗ trợ async và cung cấp executor phù hợp. Cấu hình minh họa:

~~~java
package com.example.orderevents;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class OrderEventsAsyncConfiguration {

    @Bean("orderEventsExecutor")
    public ThreadPoolTaskExecutor orderEventsExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-events-");

        return executor;
    }
}
~~~

Các con số ở đây chỉ minh họa pool và queue có giới hạn; ứng dụng cần chọn theo tải và thời gian xử lý. Spring quản lý lifecycle của executor bean.

Một phiên bản method listener bất đồng bộ:

~~~java
import org.springframework.scheduling.annotation.Async;

@Async("orderEventsExecutor")
@EventListener
public void onOrderConfirmed(
        OrderConfirmed event) {

    handler.handle(event);
}
~~~

Dùng method này thay cho bản đồng bộ tương ứng. Nó cần đi qua bean/proxy được Spring quản lý; gọi nội bộ trực tiếp một method không tương đương với việc đi qua hạ tầng async.

Xem [Spring Framework: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).

Các câu hỏi mới cần giải quyết:

- Khi task bị từ chối do executor không nhận thêm, caller và hệ thống giám sát phản ứng thế nào?
- Lỗi trong thân method `void` bất đồng bộ được ghi nhận ở đâu?
- Các dependency của handler có an toàn khi nhiều sự kiện được xử lý đồng thời không?
- Có cần giữ thứ tự xử lý cho cùng một đơn không?

Lỗi xảy ra trong thân task bất đồng bộ không truyền ngược như lời gọi đồng bộ. Có thể cấu hình `AsyncUncaughtExceptionHandler` cho lỗi của method async trả `void`; lỗi lúc submit task là một tình huống khác cần xem xét.

Không dựa vào ThreadLocal của request hoặc transaction ở caller để xử lý trên worker thread. Payload cần mang dữ liệu cần thiết, và thành phần xử lý phải có ranh giới truy cập dữ liệu phù hợp.

Chuyển thread cũng không tự lưu event xuống database. Queue trong bộ nhớ của executor có vòng đời khác với một hàng đợi thông điệp bền vững.

## 11. Transaction: @EventListener không mặc định chờ commit

Một listener đồng bộ thông thường có thể chạy khi transaction lưu aggregate vẫn chưa commit. Nếu nó gửi một thông báo ra ngoài rồi transaction rollback, bên ngoài có thể đã nhận thông tin cho một thay đổi chưa được lưu thành công.

Khi yêu cầu là xử lý sau commit, có thể dùng method sau trong một Spring bean:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(
        OrderConfirmed event) {

    handler.handle(event);
}
~~~

Method này thay thế lựa chọn tiếp nhận của cùng tác vụ. Nếu giữ cả listener thường và listener sau commit cùng gọi handler, cần chủ đích về việc xử lý hai lần.

`AFTER_COMMIT` là phase mặc định. Nếu publication không có transaction đang hoạt động, listener theo transaction bị bỏ qua theo cấu hình mặc định; `fallbackExecution` có thể thay đổi quy tắc đó.

Sau commit, nếu handler cần ghi database, hãy thiết kế một transaction mới phù hợp. Tài nguyên cũ có thể còn truy cập được nhưng không đồng nghĩa thay đổi mới sẽ được commit trong transaction đã kết thúc. Xem [TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html).

Hai lựa chọn transaction và async trả lời hai câu hỏi khác nhau:

| Lựa chọn | Câu hỏi được giải quyết |
| --- | --- |
| `@EventListener` thường | Nhận sự kiện theo publication thông thường |
| `@Async` | Chuyển công việc sang executor theo cấu hình |
| `@TransactionalEventListener` | Gắn việc xử lý với một phase của transaction |
| Lưu ý định gửi vào outbox | Giữ dữ liệu để có thể gửi lại theo thiết kế |

`@Async` không tự có nghĩa “sau commit”. Listener sau commit cũng không tự có nghĩa “gửi thành công dù tiến trình dừng”.

Ví dụ transaction ở đây là luồng đồng bộ với transaction gắn thread. Với transaction reactive, cần kiểm tra thêm cách truyền transaction context và khả năng của API đang dùng.

## 12. Kiểm tra định tuyến bằng context nhỏ

Các phép kiểm tra dưới đây dùng JUnit Jupiter và Spring context. Chúng xác minh hai cách đăng ký nhận cùng record, đồng thời bỏ qua payload không liên quan. Không cần database.

~~~java
package com.example.orderevents;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class OrderListenerRoutingTest {

    @Test
    void annotationListenerReceivesPlainPayload() {
        verifyRouting(AnnotatedOrderListener.class);
    }

    @Test
    void interfaceListenerReceivesWrappedPayload() {
        verifyRouting(InterfaceOrderListener.class);
    }

    private void verifyRouting(Class<?> listenerType) {
        RecordingHandler handler = new RecordingHandler();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(
                    OrderConfirmationHandler.class,
                    () -> handler);
            context.register(listenerType);
            context.refresh();

            OrderConfirmed event = new OrderConfirmed(
                    UUID.randomUUID(),
                    UUID.randomUUID(),
                    "WEB",
                    Instant.parse("2026-02-10T08:30:00Z"));

            context.publishEvent(event);
            context.publishEvent("unrelated-payload");

            assertEquals(
                    List.of(event),
                    handler.received);
        }
    }

    static class RecordingHandler
            implements OrderConfirmationHandler {

        private final List<OrderConfirmed> received =
                new ArrayList<>();

        @Override
        public void handle(OrderConfirmed event) {
            received.add(event);
        }
    }
}
~~~

Context trong mỗi test chỉ đăng ký **một** listener. Test dùng cấu hình đồng bộ cơ bản, nên kiểm tra ngay sau publication là phù hợp với phạm vi đó. `ArrayList` trong recorder cũng chỉ phục vụ tình huống đồng bộ này.

Không dùng nguyên test trên để kết luận listener `@Async` đã hoàn tất. Với async, cần recorder an toàn cho nhiều thread và cơ chế chờ theo điều kiện có thời hạn.

Các test cũng chưa chứng minh aggregate tạo đúng payload hoặc repository thực hiện publication. Đó là các kết quả cần kiểm tra riêng trong luồng tích hợp của store.

## 13. Kiểm tra lỗi và chẩn đoán thực tế

Ngoài việc định tuyến, hãy chọn các tình huống phản ánh hợp đồng ứng dụng:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Cả hai listener thay thế cùng được đăng ký | Handler được gọi hai lần, nếu đó là cấu hình đã chọn |
| Listener có điều kiện `WEB` nhận sự kiện kênh khác | Handler không chạy cho sự kiện bị lọc |
| Handler đồng bộ ném lỗi | Caller nhận lỗi theo cấu hình multicaster |
| Transaction commit hoặc rollback | Listener theo phase chạy đúng thời điểm |
| Publication không có transaction | Listener theo transaction tuân thủ cấu hình fallback |
| Task async thất bại | Có cơ chế ghi nhận lỗi thay vì chỉ nhìn kết quả caller |
| Cùng sự kiện được publication lại | Tác vụ quan trọng có chính sách xử lý lặp |
| Nhiều event cho cùng đơn chạy đồng thời | Không vô tình ghi đè hoặc đảo thứ tự nghiệp vụ |

Các dấu hiệu thường gặp:

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| Method có annotation nhưng không chạy | Bean registration, component scan, đúng context và đúng loại payload |
| Không biên dịch được `ApplicationListener<Record>` | Ràng buộc `ApplicationEvent`; cần wrapper cho record thường |
| Bị ép kiểu sai từ `getSource()` | Nhầm source của wrapper với dữ liệu domain trong payload |
| Tác vụ chạy hai lần | Hai listener cùng vai trò, hai nguồn phát hoặc lần retry |
| Caller chậm hơn sau khi thêm listener | Công việc đồng bộ đang nằm trên đường phản hồi |
| `@Async` không có tác dụng như mong đợi | Hạ tầng async, proxy và cách gọi method |
| Listener sau commit không chạy trong test | Test có thực sự commit transaction hay chỉ rollback |
| Trạng thái database rollback nhưng tác động ngoài vẫn xảy ra | Tác động đã thực hiện trước commit hoặc ngoài transaction database |

Không giải quyết mọi lỗi bằng cách thêm annotation. Trước hết hãy xác định sự kiện được phát ở đâu, bean nào nhận, thời điểm nào chạy và lỗi được chuyển về đâu.

## 14. Xử lý lặp và mức bảo đảm

Một lần publication có thể hợp lệ với nhiều listener. Đồng thời, cùng một thông tin nghiệp vụ cũng có thể xuất hiện lại do caller thực hiện lại yêu cầu hoặc do một cơ chế retry.

Nếu handler cộng điểm thưởng cho đơn hàng, việc cộng hai lần là lỗi nghiệp vụ. Handler cần cơ chế nhận diện đã xử lý, chẳng hạn một khóa duy nhất được lưu cùng kết quả thay đổi trong transaction phù hợp.

Chỉ có `eventId` trong record chưa tạo ra cơ chế đó. Việc giữ một tập id trong singleton memory cũng không bảo vệ được sau khi ứng dụng restart hoặc khi có nhiều instance.

Một thiết kế cần giao sự kiện ra ngoài có thể lưu ý định gửi cùng thay đổi nghiệp vụ, sau đó để bộ gửi riêng thực hiện retry và theo dõi kết quả. Listener và outbox có thể là các thành phần của thiết kế, nhưng Spring application events không tự cấu hình toàn bộ quy trình này.

Hãy chọn trách nhiệm rõ ràng cho từng listener, tránh việc nhiều listener sửa cùng aggregate rồi tạo chuỗi sự kiện quay lại nhau mà không có điểm kết thúc.

## 15. Bài thực hành

Hoàn thiện luồng nhận sự kiện xác nhận đơn hàng:

1. Định nghĩa record bất biến có id sự kiện và id đơn.
2. Cài đặt hai phương án listener và chọn một phương án cho cùng một vai trò.
3. Kiểm tra nhận đúng payload, bỏ qua loại không liên quan.
4. Thêm điều kiện kênh `WEB` và kiểm tra cả hai nhánh điều kiện.
5. Gây một lỗi trong handler đồng bộ, quan sát caller và transaction.
6. Tách riêng trường hợp cần sau commit với trường hợp cần chạy bất đồng bộ.
7. Kiểm tra việc vô tình đăng ký cả hai listener để hiểu nguyên nhân xử lý lặp.
8. Nêu cơ chế cần thêm nếu tác vụ phải tiếp tục được xử lý sau khi ứng dụng khởi động lại.

Bài thực hành đạt yêu cầu khi bạn lần theo được **nguồn publication**, **kiểu payload**, **bean nhận**, **thời điểm chạy**, **đường truyền lỗi** và **mức bảo đảm của tác vụ**, thay vì chỉ thấy một method có annotation được gọi.
