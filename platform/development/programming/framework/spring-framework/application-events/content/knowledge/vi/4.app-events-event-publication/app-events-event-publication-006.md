# Phát nhiều event theo thứ tự nghiệp vụ trong Spring

Một use case có thể tạo ra nhiều sự kiện nghiệp vụ liên tiếp. Ví dụ, một đơn hàng được kiểm tra hợp lệ, tồn kho được giữ chỗ và đơn hàng được xác nhận. Khi phát nhiều event, thứ tự phát phải phản ánh đúng những sự việc đã thực sự xảy ra.

Trong Spring, có thể gọi ApplicationEventPublisher.publishEvent() nhiều lần theo trình tự mong muốn. Với ApplicationEventMulticaster mặc định chạy đồng bộ, mỗi lần publishEvent() sẽ dispatch event và hoàn tất các listener đồng bộ trước khi lời gọi tiếp theo được thực hiện. Tuy nhiên, **thứ tự gọi publishEvent() không đồng nghĩa mọi listener luôn hoàn tất theo cùng thứ tự**: async, nhiều thread và transaction-bound listener làm thay đổi thời điểm xử lý.

Cần phân biệt ba câu hỏi:

1. Các sự kiện được phát theo thứ tự nào?
2. Listener của từng sự kiện được gọi và hoàn tất theo thứ tự nào?
3. Nếu một bước thất bại, nghiệp vụ phải dừng, rollback, retry hay tiếp tục ra sao?

## 1. Event phải mô tả sự việc đã xảy ra

Tên event nên mô tả một sự thật đã xảy ra trong miền nghiệp vụ, thường dùng dạng quá khứ:

- OrderValidated: đơn hàng đã vượt qua kiểm tra nghiệp vụ.
- InventoryReserved: tồn kho đã được giữ chỗ thành công.
- OrderConfirmed: đơn hàng đã được xác nhận.

Tên như ValidateOrder, ReserveInventory hoặc ConfirmOrder mô tả mệnh lệnh. Nếu mục tiêu là yêu cầu một service thực hiện hành động và cần biết kết quả, hãy gọi service đó trực tiếp. Event thích hợp để thông báo kết quả hoặc sự thay đổi đã xảy ra cho các thành phần quan tâm.

Điều này rất quan trọng khi phát nhiều event. Không nên phát InventoryReserved trước khi thao tác giữ chỗ thật sự thành công. Nếu phát event trước rồi thao tác thất bại, listener có thể nhận một thông báo không đúng với trạng thái nghiệp vụ.

Một chuỗi event tốt biểu diễn các mốc đã hoàn thành, chẳng hạn:

    OrderValidated
        -> InventoryReserved
            -> OrderConfirmed

Mũi tên biểu thị thứ tự nghiệp vụ. Nó không nhất thiết có nghĩa listener của event trước phải thực hiện hành động để tạo ra event sau. Các bước bắt buộc của use case vẫn nên được điều phối bằng service hoặc workflow có kết quả rõ ràng.

## 2. Phát event tuần tự bằng ApplicationEventPublisher

ApplicationEventPublisher là API để công bố event trong ApplicationContext. Từ Spring Framework 4.2, có thể publish một object Java bất kỳ; không bắt buộc phải kế thừa ApplicationEvent. Với Java 17+, record là cách gọn để biểu diễn event bất biến.

Ví dụ định nghĩa ba event:

~~~java
import java.util.UUID;

public record OrderValidatedEvent(
    UUID orderId,
    long sequence
) {}

public record InventoryReservedEvent(
    UUID orderId,
    long sequence
) {}

public record OrderConfirmedEvent(
    UUID orderId,
    long sequence
) {}
~~~

Trường sequence giúp quan sát thứ tự các mốc của cùng một đơn hàng. Nó không tự tạo ra cơ chế sắp thứ tự hoặc bảo đảm giao nhận; nó chỉ là metadata để log, kiểm tra hoặc consumer phát hiện event đến sai thứ tự.

Service điều phối có thể phát các event sau khi mỗi bước nghiệp vụ hoàn thành:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWorkflow {

    private final ApplicationEventPublisher publisher;
    private final OrderValidator validator;
    private final InventoryService inventoryService;

    public OrderWorkflow(
            ApplicationEventPublisher publisher,
            OrderValidator validator,
            InventoryService inventoryService) {
        this.publisher = publisher;
        this.validator = validator;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public void confirm(Order order) {
        validator.validate(order);
        publisher.publishEvent(
            new OrderValidatedEvent(order.getId(), 1)
        );

        inventoryService.reserve(order);
        publisher.publishEvent(
            new InventoryReservedEvent(order.getId(), 2)
        );

        order.confirm();
        publisher.publishEvent(
            new OrderConfirmedEvent(order.getId(), 3)
        );
    }
}
~~~

Order, OrderValidator và InventoryService là các kiểu miền nghiệp vụ của ứng dụng, cần được cung cấp trong dự án. Ví dụ giả định các thao tác dữ liệu thuộc cùng transaction; nếu inventory nằm ở hệ thống ngoài, transaction database cục bộ không thể tự rollback thao tác ở hệ thống đó.

Điểm quan trọng của ví dụ là publisher phát event sau khi bước tương ứng thành công. Nếu validate thất bại, không có event nào được phát. Nếu reserve thất bại, OrderValidatedEvent có thể đã được phát, nhưng các bước tiếp theo và hai event sau không được chạy. Khi đó cần quyết định listener của OrderValidatedEvent có được phép quan sát trạng thái tạm thời hay phải đợi transaction commit; phần transaction được trình bày ở mục 6.

## 3. Thứ tự dispatch với multicaster mặc định

SimpleApplicationEventMulticaster là implementation mặc định thường được ApplicationContext sử dụng nếu ứng dụng không cung cấp multicaster khác. Mặc định, nó không dùng executor riêng để gọi listener, nên listener được gọi đồng bộ trên thread đang publish event.

Giả sử có listener cho cả ba event:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventLogger {

    @EventListener
    public void on(OrderValidatedEvent event) {
        System.out.println("1. validated " + event.orderId());
    }

    @EventListener
    public void on(InventoryReservedEvent event) {
        System.out.println("2. inventory reserved " + event.orderId());
    }

    @EventListener
    public void on(OrderConfirmedEvent event) {
        System.out.println("3. confirmed " + event.orderId());
    }
}
~~~

Nếu các listener đồng bộ hoàn thành bình thường, thứ tự xử lý tương ứng với ba lệnh publishEvent() trong service:

1. Publisher phát OrderValidatedEvent; các listener phù hợp được dispatch.
2. Sau khi lời gọi publishEvent() đầu tiên trở về, service thực hiện reserve rồi phát InventoryReservedEvent.
3. Sau khi dispatch event thứ hai trở về, service xác nhận đơn hàng rồi phát OrderConfirmedEvent.

Đây là bảo đảm theo luồng gọi tuần tự trong một thread với multicaster đồng bộ. Nó không phải bảo đảm thứ tự toàn cục giữa các request, giữa nhiều thread hoặc giữa các hệ thống.

### @Order sắp listener, không sắp chuỗi nghiệp vụ

Nếu nhiều listener cùng quan tâm đến một event, có thể dùng @Order hoặc triển khai Ordered để sắp thứ tự gọi các listener trong cùng một multicaster.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    @EventListener
    @Order(10)
    public void audit(OrderConfirmedEvent event) {
        System.out.println("Audit order " + event.orderId());
    }
}

@Component
class OrderMetricsListener {

    @EventListener
    @Order(20)
    public void recordMetric(OrderConfirmedEvent event) {
        System.out.println("Metric order " + event.orderId());
    }
}
~~~

Trong ví dụ, audit listener được gọi trước metrics listener cho cùng OrderConfirmedEvent. @Order không làm InventoryReservedEvent đợi một listener của OrderValidatedEvent chạy xong nếu listener đó được thực thi bất đồng bộ. Nó cũng không tạo một workflow giữa các event type khác nhau.

Nếu thứ tự giữa nhiều phản ứng là yêu cầu nghiệp vụ bắt buộc, hãy đặt chúng trong một service điều phối hoặc một listener duy nhất gọi các bước theo trình tự rõ ràng.

## 4. Điều gì xảy ra khi listener thất bại?

Với multicaster mặc định và listener đồng bộ, exception không được xử lý có thể truyền ngược về nơi publishEvent() được gọi. Với SimpleApplicationEventMulticaster không cấu hình ErrorHandler, một listener ném exception có thể làm gián đoạn lần dispatch hiện tại và khiến service không chạy tới lệnh publishEvent() kế tiếp.

Ví dụ:

~~~java
publisher.publishEvent(new OrderValidatedEvent(orderId, 1));

// Nếu listener phía trên ném exception và exception thoát ra,
// các lệnh phía dưới có thể không được thực hiện.
publisher.publishEvent(new InventoryReservedEvent(orderId, 2));
publisher.publishEvent(new OrderConfirmedEvent(orderId, 3));
~~~

Điều này có thể hữu ích nếu listener là một phần của cùng luồng xử lý và lỗi phải làm use case thất bại. Nhưng nếu listener chỉ ghi metric hoặc audit phụ trợ, việc để lỗi phụ trợ chặn toàn bộ quy trình có thể không phải điều mong muốn.

Cần xác định chính sách lỗi cho từng listener:

- **Lỗi phải chặn use case:** để exception truyền về caller hoặc chuyển thành lỗi nghiệp vụ phù hợp.
- **Lỗi phụ trợ không được chặn use case:** xử lý lỗi có chủ đích, ghi log/metric và giám sát. Nếu dùng ErrorHandler của multicaster, hiểu rằng exception được xử lý tại đó có thể không còn truyền về publisher.
- **Công việc phải retry:** lưu công việc vào cơ chế bền vững hoặc dùng outbox/broker; không chỉ dựa vào một callback trong bộ nhớ.
- **Listener async:** cấu hình cơ chế quan sát lỗi của executor hoặc AsyncUncaughtExceptionHandler; không giả định publisher sẽ nhận exception của listener.

Đừng nuốt mọi exception chỉ để chuỗi publish tiếp tục. Nếu bỏ qua lỗi, trạng thái nghiệp vụ phải được ghi nhận để có thể phát hiện và khôi phục.

## 5. Khi listener chạy bất đồng bộ

Có thể dùng @Async với @EventListener hoặc cấu hình executor cho SimpleApplicationEventMulticaster. Khi đó, lời gọi publishEvent() có thể chỉ gửi công việc đến executor rồi trở về; listener chưa chắc đã bắt đầu hoặc hoàn tất.

Ví dụ:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
class AsyncNotificationListener {

    @Async
    @EventListener
    public void on(OrderConfirmedEvent event) {
        sendNotification(event.orderId());
    }

    private void sendNotification(java.util.UUID orderId) {
        // Gửi thông báo ở đây.
    }
}
~~~

Cần bật async processing bằng @EnableAsync và cấu hình executor phù hợp. Các điểm cần nhớ:

- Publisher không đợi listener async hoàn tất như với listener đồng bộ.
- Hai event được publish lần lượt không đồng nghĩa hai listener async hoàn tất theo cùng thứ tự.
- Nhiều executor thread có thể xử lý event đồng thời.
- Exception trong listener async không được trả về cho publisher như exception của lời gọi đồng bộ.
- Transaction context của thread publish không tự chuyển sang thread executor.

Ví dụ, service có thể publish OrderValidatedEvent rồi InventoryReservedEvent. Listener async cho event thứ hai có thể hoàn tất trước listener async cho event thứ nhất nếu công việc thứ nhất chậm hơn. Nếu nghiệp vụ yêu cầu phản ứng B chỉ được chạy sau khi phản ứng A hoàn tất, @Async độc lập cho hai listener không đáp ứng yêu cầu đó.

### Muốn giữ thứ tự khi xử lý async

Trước tiên hãy xác định phạm vi thứ tự cần bảo đảm:

- Theo một đơn hàng hay theo toàn bộ ứng dụng?
- Chỉ cần nhận event theo thứ tự hay cần listener hoàn tất theo thứ tự?
- Có cần giữ thứ tự qua retry, restart và nhiều instance không?

Với một quy trình nhỏ trong cùng ứng dụng, có thể dùng một worker tuần tự hoặc một service điều phối duy nhất. Với nhiều đơn hàng độc lập, có thể xử lý song song giữa các đơn hàng nhưng tuần tự trong từng order ID. Với message broker, thường dùng partition key theo aggregate ID và sequence number để giữ thứ tự trong cùng partition; vẫn cần xử lý duplicate và retry.

Chỉ cấu hình một thread executor không tự giải quyết mọi vấn đề: nhiều publisher, nhiều executor, retry hoặc nhiều instance vẫn có thể làm thứ tự nghiệp vụ phức tạp. Hãy chọn cơ chế dựa trên phạm vi thứ tự cần bảo đảm.

## 6. Phát nhiều event trong transaction

Khi phương thức publish event được gọi bên trong @Transactional, cần phân biệt listener thông thường với @TransactionalEventListener.

### @EventListener thông thường

Listener đồng bộ của @EventListener chạy khi event được dispatch. Nếu publish trước khi transaction commit, listener có thể chạy trong lúc transaction còn mở và quan sát dữ liệu chưa commit.

Nếu transaction sau đó rollback, các tác dụng phụ mà listener đã thực hiện bên ngoài transaction có thể vẫn tồn tại. Ví dụ, một email đã gửi không thể được thu hồi chỉ vì database rollback.

Vì vậy, không nên dùng listener thông thường để thực hiện tác dụng phụ không thể đảo ngược khi event được phát trước commit, trừ khi đó là hành vi có chủ đích.

### @TransactionalEventListener

Nếu listener chỉ được phép chạy sau khi transaction commit, dùng @TransactionalEventListener:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderConfirmationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderConfirmedEvent event) {
        // Gửi thông báo sau khi transaction commit thành công.
    }
}
~~~

Các phase chính:

- BEFORE_COMMIT: chạy trước khi transaction commit.
- AFTER_COMMIT: chạy sau khi commit thành công; đây là phase mặc định.
- AFTER_ROLLBACK: chạy sau rollback.
- AFTER_COMPLETION: chạy khi transaction hoàn tất, bất kể commit hay rollback.

Mặc định, transactional listener cần một transaction đang hoạt động tại thời điểm event được phát. Nếu không có transaction, listener không được gọi trừ khi bật fallbackExecution = true.

Khi một transaction phát ba event liên tiếp, các transactional listener sẽ được gắn với vòng đời transaction và chỉ chạy tại phase đã chọn. Tuy nhiên, đừng biến nhiều listener độc lập thành một chuỗi bước bắt buộc dựa vào thứ tự callback. Nếu nghiệp vụ cần xác nhận A hoàn tất rồi mới thực hiện B, hãy dùng một handler/orchestrator có trình tự rõ ràng.

Một lỗi listener AFTER_COMMIT không thể rollback transaction đã commit. Vì vậy, AFTER_COMMIT giải quyết vấn đề thời điểm, nhưng không tự cung cấp retry hoặc bảo đảm công việc sẽ được thực hiện.

## 7. Khi cần độ bền và không được mất event

ApplicationEventPublisher là cơ chế thông báo nội bộ trong một tiến trình. Nó không phải message broker và không tự lưu event qua lần restart.

Giả sử database đã commit trạng thái OrderConfirmed nhưng tiến trình dừng trước khi listener gửi thông báo. Event trong bộ nhớ có thể bị mất và không có bản ghi nào để khôi phục công việc.

Nếu event cần được giao nhận đáng tin cậy, cân nhắc transactional outbox:

1. Trong cùng transaction nghiệp vụ, cập nhật đơn hàng và ghi một bản ghi outbox cho mỗi event cần phát.
2. Sau commit, một worker đọc các bản ghi outbox chưa gửi.
3. Worker publish message lên broker hoặc chuyển tới consumer.
4. Sau khi gửi thành công, ghi nhận trạng thái đã gửi; nếu lỗi, retry theo chính sách.
5. Consumer xử lý idempotent vì message có thể được gửi lại.

Outbox tránh khoảng hở giữa commit dữ liệu nghiệp vụ và việc ghi nhận ý định phát event. Tuy vậy, hệ thống vẫn cần xử lý duplicate, retry, thứ tự và dead-letter theo yêu cầu. Nếu cần thứ tự theo từng đơn hàng, ghi sequence number trong outbox và đảm bảo consumer xử lý đúng thứ tự cho cùng aggregate ID.

Không cần triển khai outbox cho mọi event nội bộ. Dùng nó khi hậu quả của việc mất event đủ lớn để cần độ bền và khả năng phục hồi.

## 8. Phát event trong vòng lặp và nhiều publisher đồng thời

Có thể phát event cho từng phần tử trong một danh sách:

~~~java
for (Order order : orders) {
    publisher.publishEvent(
        new OrderValidatedEvent(order.getId(), 1)
    );
}
~~~

Với multicaster đồng bộ, mỗi event được dispatch theo thứ tự vòng lặp trong thread hiện tại. Nhưng nếu listener async, thứ tự hoàn thành giữa các order không được bảo đảm.

Nếu nhiều thread cùng publish event, không có một thứ tự nghiệp vụ toàn cục tự xuất hiện. Thứ tự quan sát có thể phụ thuộc vào thời điểm thread chạy, executor, transaction và tải hệ thống.

Nếu thứ tự chỉ cần giữ trong từng đơn hàng, hãy dùng aggregate ID và sequence number. Nếu phải xử lý tuần tự theo từng aggregate, cần serialize công việc theo khóa aggregate hoặc dùng partitioned message stream. Không dùng timestamp đơn thuần làm bằng chứng tuyệt đối về thứ tự khi nhiều máy hoặc nhiều thread cùng phát event.

## 9. Chọn một event tổng hợp hay nhiều event?

Không phải lúc nào cũng cần phát một event cho từng bước nội bộ.

### Dùng nhiều event khi từng mốc có ý nghĩa độc lập

Ví dụ InventoryReserved và OrderConfirmed có thể được nhiều module quan tâm vì mỗi sự việc có ý nghĩa riêng. Khi đó, phát từng event sau khi sự việc tương ứng xảy ra giúp các module phản ứng đúng phạm vi.

### Dùng một event tổng hợp khi chỉ cần thông báo kết quả cuối

Nếu các bước kiểm tra, giữ chỗ và xác nhận chỉ là chi tiết nội bộ của một use case, và không module nào cần biết từng mốc, một event OrderConfirmed với payload mô tả kết quả cuối có thể đơn giản hơn.

### Dùng orchestration khi có thứ tự bắt buộc giữa hành động

Nếu bước B chỉ được thực hiện khi bước A thành công và bước C cần kết quả của B, service điều phối nên gọi các service theo trình tự, kiểm tra kết quả và xử lý lỗi. Event có thể được phát sau từng mốc để thông báo cho bên quan tâm, nhưng không nên dùng các listener rời rạc làm bộ điều khiển chính của workflow.

## 10. Kiểm tra thứ tự event

Một kiểm tra có ích là ghi lại thứ tự dispatch và completion riêng biệt. Không chỉ ghi một dòng log trong publisher rồi suy ra listener đã hoàn tất.

Có thể ghi các trường sau:

- eventType: loại event.
- aggregateId: ID đơn hàng hoặc đối tượng nghiệp vụ.
- sequence: thứ tự nghiệp vụ trong aggregate.
- eventId: ID duy nhất để phát hiện duplicate.
- publishedAt: thời điểm publisher phát event.
- listenerName: listener đang xử lý.
- startedAt và completedAt: thời gian xử lý listener.
- outcome: thành công, thất bại hoặc retry.

Khi kiểm tra, xác nhận:

1. Các bước nghiệp vụ được gọi theo đúng thứ tự.
2. Mỗi event chỉ được publish sau khi sự việc tương ứng xảy ra.
3. Với multicaster đồng bộ, listener hoàn tất trước khi lệnh publishEvent() tương ứng trở về.
4. Nếu bật async, kiểm tra riêng thứ tự bắt đầu và hoàn tất.
5. Nếu dùng transaction-bound listener, xác nhận listener chỉ chạy ở phase mong muốn.
6. Nếu transaction rollback, xác nhận listener AFTER_COMMIT không chạy.
7. Nếu có lỗi listener, xác nhận quy trình dừng hoặc tiếp tục đúng chính sách đã thiết kế.
8. Với nhiều publisher đồng thời, xác nhận thứ tự được giữ trong phạm vi aggregate cần thiết.

## 11. Những lỗi thiết kế thường gặp

**Phát event trước khi sự việc xảy ra.** Phát InventoryReserved rồi mới gọi reserve() có thể khiến listener tin rằng tồn kho đã được giữ chỗ dù thao tác thất bại. Hãy phát event sau khi xác nhận thành công.

**Cho rằng nhiều lệnh publishEvent luôn có nghĩa listener hoàn tất tuần tự.** Điều này chỉ đúng với dispatch đồng bộ trong cùng luồng gọi. Async và executor có thể làm các listener chạy chồng lấn.

**Dùng @Order để sắp nhiều loại event.** @Order sắp listener trong một multicaster, không điều phối chuỗi nghiệp vụ giữa các lần publish khác nhau.

**Dùng event listener để thay bước nghiệp vụ bắt buộc.** Nếu use case cần kết quả hoặc cần dừng ngay khi một bước thất bại, gọi service trực tiếp và điều phối rõ ràng.

**Phát event trong transaction rồi gửi email ngay bằng listener đồng bộ.** Transaction có thể rollback sau khi email đã được gửi. Hãy cân nhắc AFTER_COMMIT hoặc outbox tùy mức bảo đảm cần thiết.

**Cho rằng AFTER_COMMIT bảo đảm không mất event.** Listener có thể lỗi hoặc tiến trình có thể dừng sau commit. Công việc bắt buộc cần lưu bền và retry.

**Không xử lý duplicate.** Outbox, broker và retry có thể giao cùng message nhiều lần. Consumer nên idempotent và nhận diện event bằng ID duy nhất.

**Bỏ qua thứ tự giữa các publisher.** Hai request cùng cập nhật một aggregate có thể publish event đồng thời. Cần transaction/concurrency control và sequence theo aggregate nếu thứ tự là điều kiện nghiệp vụ.

**Gộp quá nhiều sự việc vào một event chung chung.** Event tên ProcessFinished hoặc DataChanged với payload mơ hồ khiến listener khó hiểu ý nghĩa. Hãy dùng tên và dữ liệu thể hiện rõ sự kiện miền.

## 12. Quy tắc chọn nhanh

- Cần thực hiện một bước bắt buộc và biết kết quả: gọi service trực tiếp.
- Cần thông báo nhiều mốc nghiệp vụ đã xảy ra: phát nhiều event theo trình tự sau mỗi mốc.
- Cần listener đồng bộ hoàn tất trước bước tiếp theo: dùng dispatch đồng bộ và để exception đi theo chính sách lỗi đã chọn.
- Chỉ cần phản ứng sau commit: dùng @TransactionalEventListener với AFTER_COMMIT.
- Cần xử lý async: thiết kế rõ executor, lỗi, thứ tự và transaction.
- Cần không mất event khi tiến trình dừng: dùng outbox hoặc cơ chế lưu bền.
- Cần giữ thứ tự trong từng aggregate: dùng aggregate ID, sequence và xử lý tuần tự theo aggregate.
- Chỉ cần thông báo kết quả cuối: cân nhắc một event tổng hợp thay vì nhiều event không có consumer riêng.

**Ghi nhớ:** thứ tự publishEvent() thể hiện thứ tự publisher phát event. Với multicaster đồng bộ, listener của mỗi event được dispatch trước khi lời gọi tiếp theo chạy. Khi dùng async, nhiều thread hoặc transaction-bound listener, phải thiết kế riêng thứ tự hoàn tất và độ bền. Event thông báo điều đã xảy ra; service orchestration điều khiển các bước bắt buộc.

## Tài liệu tham khảo

- [ApplicationEventPublisher — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [ApplicationEventMulticaster — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [SimpleApplicationEventMulticaster — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [TransactionalEventListener — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework Application Events — Reference](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)