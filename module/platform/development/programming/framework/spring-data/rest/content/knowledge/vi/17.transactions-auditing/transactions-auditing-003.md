# Thực thi tác vụ sau commit bằng cơ chế transaction phù hợp

## 1. Vì sao phải chờ transaction commit?

Trong ứng dụng Spring Data REST, một request có thể tạo hoặc cập nhật entity thông qua repository được exporter công bố. Nhiều thao tác cần chạy tiếp sau khi dữ liệu đã được commit, ví dụ:

- Gửi email xác nhận hoặc thông báo.
- Gửi message tới broker hoặc gọi hệ thống khác.
- Ghi audit bổ sung, cập nhật chỉ mục tìm kiếm hoặc cache.
- Khởi chạy quy trình xử lý tiếp theo.

Nếu thực hiện các tác vụ này ngay sau lệnh repository.save() nhưng trước khi transaction kết thúc, hệ thống bên ngoài có thể nhận thông tin về một thay đổi sau đó bị rollback. Ví dụ: message đã được gửi nhưng bản ghi order không tồn tại vì transaction thất bại.

Spring cung cấp transaction-bound event để gắn listener với một phase cụ thể. Với tác vụ chỉ được chạy khi dữ liệu đã commit thành công, lựa chọn thông dụng là @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT).

## 2. Phân biệt Spring Data REST repository event và transaction phase

Spring Data REST exporter phát các event trong vòng đời thao tác entity:

| Event | Thời điểm theo vòng đời exporter |
|---|---|
| BeforeCreateEvent | Trước khi tạo entity |
| AfterCreateEvent | Sau bước tạo entity |
| BeforeSaveEvent | Trước khi lưu entity |
| AfterSaveEvent | Sau bước lưu entity |
| BeforeLinkSaveEvent | Trước khi lưu association |
| AfterLinkSaveEvent | Sau bước lưu association |
| BeforeDeleteEvent | Trước khi xóa entity |
| AfterDeleteEvent | Sau bước xóa entity |

Có thể nhận các event này bằng ApplicationListener, AbstractRepositoryEventListener hoặc handler được đánh dấu @RepositoryEventHandler và các annotation như @HandleBeforeSave, @HandleAfterSave.

Tên AfterSaveEvent mô tả vị trí trong lifecycle của Spring Data REST. Nó không phải một transaction phase và không tự nó chứng minh rằng transaction bao quanh request đã commit. Tương tự, việc Spring application event được phát đồng bộ chỉ nói rằng listener được gọi trên luồng phát event; điều đó không đồng nghĩa database transaction đã hoàn tất.

Khi cần bảo đảm tác vụ chỉ chạy sau commit, phải xác định event được publish trong một transaction đang hoạt động. Nếu không có transaction, @TransactionalEventListener mặc định không chạy. Không bật fallbackExecution=true chỉ để che giấu việc thiếu transaction, vì khi đó listener có thể chạy ngay cả khi không có commit nào.

## 3. Cách khuyến nghị: publish event trong một service có @Transactional

Ví dụ dùng một service làm ranh giới transaction. Service lưu Order và publish event trong cùng một transaction. Listener đăng ký với phase AFTER_COMMIT sẽ chỉ chạy sau khi transaction commit thành công.

Event nên là dữ liệu bất biến và chứa ID hoặc snapshot tối thiểu cần thiết:

~~~java
public record OrderCreated(Long orderId) {
}
~~~

Service thực hiện thao tác nghiệp vụ:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        Order saved = orderRepository.save(order);

        eventPublisher.publishEvent(new OrderCreated(saved.getId()));

        return saved.getId();
    }
}
~~~

Listener chạy sau commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCreatedListener {

    private final OrderNotificationService notificationService;

    public OrderCreatedListener(OrderNotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderCreated event) {
        notificationService.sendConfirmation(event.orderId());
    }
}
~~~

Luồng xử lý:

1. Request gọi OrderApplicationService qua Spring bean proxy.
2. Transaction bắt đầu.
3. Repository lưu entity.
4. ApplicationEventPublisher phát OrderCreated; listener được đăng ký chờ phase AFTER_COMMIT.
5. Nếu transaction commit, listener được gọi.
6. Nếu transaction rollback, listener AFTER_COMMIT không được gọi.

Nếu có nhiều transaction manager, cần bảo đảm service và event listener gắn với đúng transaction chứa thao tác lưu dữ liệu. Có thể chỉ định transactionManager trên @Transactional khi ứng dụng có nhiều manager.

## 4. Chọn phase phù hợp

@TransactionalEventListener hỗ trợ bốn phase:

| Phase | Khi listener chạy | Trường hợp sử dụng |
|---|---|---|
| BEFORE_COMMIT | Trước khi commit | Kiểm tra hoặc chuẩn bị công việc cần hoàn thành trước commit |
| AFTER_COMMIT | Sau khi commit thành công; đây là mặc định | Gửi thông báo, phát sự kiện ra ngoài sau khi dữ liệu đã được lưu |
| AFTER_ROLLBACK | Sau khi rollback | Ghi nhận hoặc thông báo về giao dịch thất bại |
| AFTER_COMPLETION | Sau khi transaction kết thúc, bất kể commit hay rollback | Dọn dẹp tài nguyên hoặc xử lý cần biết transaction đã kết thúc |

Ví dụ chỉ chạy khi rollback:

~~~java
@Component
public class OrderRollbackListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void handle(OrderCreated event) {
        // Ghi nhận metric hoặc log phù hợp.
    }
}
~~~

Nếu không có transaction đang chạy tại thời điểm publish, listener transaction-bound bị bỏ qua theo mặc định. Thuộc tính fallbackExecution=true cho phép xử lý cả trường hợp không có transaction:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void handle(OrderCreated event) {
    // Chỉ dùng khi việc xử lý ngoài transaction cũng hợp lệ.
}
~~~

Với yêu cầu nghiêm ngặt là chỉ chạy sau commit, giữ fallbackExecution ở giá trị mặc định false và sửa nơi publish để bảo đảm có transaction.

## 5. Kết nối với Spring Data REST

### 5.1. Dùng @RepositoryEventHandler khi cần hook vào request của exporter

Có thể publish application event từ annotated repository handler:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.rest.core.annotation.HandleAfterCreate;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler
public class OrderRepositoryEventHandler {

    private final ApplicationEventPublisher eventPublisher;

    public OrderRepositoryEventHandler(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @HandleAfterCreate
    public void afterCreate(Order order) {
        eventPublisher.publishEvent(new OrderCreated(order.getId()));
    }
}
~~~

Sau đó dùng OrderCreatedListener ở phần trên để xử lý theo transaction phase. Cách này chỉ đáp ứng cam kết AFTER_COMMIT khi event handler publish trong transaction đang hoạt động. Hãy kiểm tra luồng request thực tế của phiên bản Spring Data REST và transaction manager đang dùng. Nếu handler được gọi ngoài transaction, listener sẽ không chạy khi fallbackExecution=false.

Không gọi email, HTTP API hoặc broker trực tiếp trong @HandleAfterCreate hay @HandleAfterSave nếu yêu cầu là chỉ thực hiện sau commit. Handler repository là hook lifecycle; @TransactionalEventListener mới là cơ chế gắn listener với transaction phase.

### 5.2. Dùng @DomainEvents trên aggregate root

Spring Data hỗ trợ aggregate root publish domain event khi các method repository phù hợp được gọi. @DomainEvents đánh dấu method trả về một event hoặc collection event; @AfterDomainEventPublication đánh dấu callback dọn danh sách sau khi publish.

Ví dụ rút gọn:

~~~java
import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class Order {

    private Long id;
    private final List<Object> domainEvents = new ArrayList<>();

    public void markCreated() {
        domainEvents.add(new OrderCreated(id));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(domainEvents);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        domainEvents.clear();
    }
}
~~~

Spring Data gọi các method này khi những repository operation được hỗ trợ như save, saveAll, delete và deleteAll được gọi với aggregate instance. deleteById không có trong danh sách vì implementation có thể xóa bằng query mà không nạp aggregate instance.

Domain event giúp gom sự kiện phát sinh từ hành vi của aggregate. Để listener chỉ chạy sau commit, vẫn phải bảo đảm event được publish trong transaction đang hoạt động và xử lý bằng @TransactionalEventListener. Với endpoint do Spring Data REST exporter tạo, hãy kiểm thử cả đường HTTP thực tế thay vì chỉ kiểm thử repository riêng lẻ.

### 5.3. Dùng custom controller/service khi cần ranh giới transaction rõ ràng

Nếu endpoint nghiệp vụ cần nhiều thao tác, custom @RepositoryRestController có thể gọi service @Transactional. Service đó thực hiện các thay đổi repository và publish event trong cùng transaction. Đây là cách dễ kiểm soát khi cần chắc chắn rằng thao tác lưu và event publication thuộc cùng một transaction.

Không đặt @Transactional lên một method rồi gọi method đó từ method khác trong cùng instance để kỳ vọng proxy mở transaction mới. Với proxy mode mặc định, self-invocation không đi qua proxy. Gọi service qua Spring bean khác hoặc tổ chức transaction ở public method được gọi từ bên ngoài.

## 6. Các lưu ý về dữ liệu và transaction sau commit

### 6.1. Chỉ truyền dữ liệu cần thiết qua event

Nên truyền ID hoặc immutable snapshot thay vì giữ nguyên entity JPA có quan hệ lazy. Sau commit, persistence context có thể đã đóng; listener đọc lazy association có thể gặp LazyInitializationException hoặc truy vấn dữ liệu ngoài ý muốn.

Ví dụ event có thể chứa orderId, customerId, eventId và phiên bản dữ liệu cần xử lý. Listener có thể nạp lại dữ liệu bằng một service riêng nếu cần.

### 6.2. Ghi database trong listener cần transaction mới

Sau callback AFTER_COMMIT, transaction gốc đã commit. Tuy nhiên, tài nguyên transaction có thể vẫn đang được bind và truy cập được trong callback. Một thao tác ghi database mới có thể tham gia vào resource cũ nhưng không có commit tiếp theo.

Nếu listener cần ghi database, gọi một bean service riêng với propagation REQUIRES_NEW:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderAuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordPublished(Long orderId) {
        // Ghi audit trong transaction mới.
    }
}
~~~

Tách sang bean khác giúp lời gọi đi qua transaction proxy. Không tự gọi method REQUIRES_NEW trong cùng object và kỳ vọng proxy được kích hoạt.

### 6.3. Lỗi listener không thể rollback dữ liệu đã commit

Khi listener AFTER_COMMIT chạy, dữ liệu gốc đã được commit. Nếu gửi email hoặc gọi API ngoài thất bại, transaction gốc không thể rollback. Với listener đồng bộ, exception có thể truyền ngược về caller dù database đã commit, khiến HTTP request có thể trả lỗi trong khi dữ liệu đã được lưu.

Vì vậy:

- Xác định rõ lỗi hậu commit có được phép ảnh hưởng response HTTP hay không.
- Bắt và ghi log lỗi có context/correlation ID; không giả vờ rằng transaction gốc đã rollback.
- Với công việc có thể retry, dùng cơ chế retry có giới hạn, backoff và dead-letter/failed state.
- Làm listener idempotent để một event được xử lý lại không tạo tác dụng phụ trùng lặp.

### 6.4. Chạy bất đồng bộ khi công việc tốn thời gian

Có thể kết hợp @Async với listener transaction-bound để đưa phần xử lý nặng sang executor sau khi transaction commit:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AsyncOrderCreatedListener {

    @Async("applicationTaskExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderCreated event) {
        // Xử lý tác vụ chậm sau commit.
    }
}
~~~

Bật async processing bằng @EnableAsync và cấu hình executor có giới hạn thread, queue, shutdown policy và monitoring phù hợp. @Async không tự cung cấp durable queue hoặc bảo đảm retry. Nếu process dừng sau commit nhưng trước khi task được thực thi, event trong bộ nhớ có thể mất.

## 7. Khi nào cần Transactional Outbox?

@TransactionalEventListener phù hợp cho tác vụ hậu commit trong cùng ứng dụng, khi chấp nhận được rủi ro listener thất bại hoặc process dừng sau khi dữ liệu đã commit.

Nếu cần bảo đảm một thay đổi database sẽ được chuyển thành message bền vững, cân nhắc Transactional Outbox:

1. Trong cùng transaction nghiệp vụ, lưu entity và thêm một bản ghi outbox chứa event ID, type, payload, createdAt và trạng thái.
2. Transaction commit làm cho cả entity và outbox record cùng tồn tại hoặc cùng rollback.
3. Một worker/CDC publisher đọc các outbox record chưa gửi và chuyển message tới broker.
4. Sau khi gửi thành công, cập nhật trạng thái hoặc offset theo thiết kế.
5. Consumer xử lý idempotent theo event ID vì retry có thể tạo giao nhận ít nhất một lần.

Outbox không biến việc gửi broker và database commit thành một transaction phân tán duy nhất; nó lưu lại ý định gửi trong cùng database transaction để có thể retry sau sự cố. Với email, webhook hoặc message quan trọng, outbox thường đáng tin cậy hơn một callback chỉ tồn tại trong bộ nhớ.

## 8. TransactionSynchronization khi cần callback mức thấp

Nếu cần đăng ký callback bằng code thay vì application event, Spring cung cấp TransactionSynchronization:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Chạy sau commit thành công.
            }
        }
    );
}
~~~

Cách này hữu ích cho integration ở mức thấp, nhưng cần tự quản lý việc chỉ đăng ký khi synchronization đang hoạt động và tránh giữ entity/resource không cần thiết. Với domain event và listener độc lập, @TransactionalEventListener thường rõ ràng hơn.

## 9. Kiểm thử commit và rollback

Kiểm thử cần xác nhận listener chỉ chạy sau commit và không chạy khi rollback. Một lỗi thường gặp là test được đánh dấu @Transactional: Spring Test mặc định rollback transaction của test khi kết thúc, nên AFTER_COMMIT listener không chạy.

Ví dụ dùng TestTransaction để chủ động commit:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Transactional
class OrderAfterCommitTests {

    @Autowired
    OrderApplicationService orderService;

    @Autowired
    OrderEventProbe eventProbe;

    @Test
    void listenerRunsOnlyAfterCommit() {
        Long orderId = orderService.createOrder(new CreateOrderCommand(/* fields */));

        assertThat(eventProbe.receivedOrderIds()).doesNotContain(orderId);

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertThat(eventProbe.receivedOrderIds()).contains(orderId);
    }
}
~~~

OrderEventProbe là test component ghi nhận event đã xử lý, được inject vào test. Bổ sung test rollback bằng cách tạo một transaction rồi đánh dấu rollback hoặc ném RuntimeException trước khi commit; xác nhận listener AFTER_COMMIT không được gọi.

Các điểm nên kiểm thử:

- Event được publish khi transaction đang hoạt động.
- Listener chạy sau commit và không chạy sau rollback.
- Không có transaction thì listener bị bỏ qua nếu fallbackExecution=false.
- Endpoint Spring Data REST thực tế phát event đúng đường đi dự kiến.
- Listener có thể chạy lại mà không gửi thông báo hoặc tạo bản ghi trùng.
- Nếu listener ghi database, transaction REQUIRES_NEW thực sự commit.
- Test không vô tình giữ transaction mở hoặc rollback ở cuối test.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| @TransactionalEventListener không chạy | Không có transaction tại thời điểm publish hoặc transaction chưa được bật | Kiểm tra transaction manager và nơi phát event; không bật fallbackExecution để che lỗi |
| Listener chạy trước khi dữ liệu commit | Dùng @EventListener hoặc gọi tác vụ trực tiếp trong repository handler | Chuyển sang @TransactionalEventListener(AFTER_COMMIT) |
| Listener vẫn chạy khi transaction rollback | Dùng listener thông thường hoặc phase sai | Dùng phase AFTER_COMMIT và test rollback |
| AfterSaveEvent bị hiểu nhầm là after commit | Nhầm lifecycle event với transaction synchronization | Kiểm tra transaction thực tế và bind listener theo phase |
| @Transactional không có tác dụng | Self-invocation, method không đi qua proxy, bean không do Spring quản lý hoặc thiếu transaction manager | Gọi qua bean proxy và kiểm tra cấu hình |
| Checked exception không rollback | Mặc định Spring rollback RuntimeException và Error; checked exception không tự rollback | Khai báo rollbackFor phù hợp hoặc thiết kế exception rõ ràng |
| Listener ghi database nhưng dữ liệu không được lưu | Callback sau commit dùng resource transaction cũ nhưng không có commit tiếp theo | Gọi service riêng với Propagation.REQUIRES_NEW |
| HTTP trả lỗi nhưng dữ liệu vẫn tồn tại | Listener đồng bộ ném exception sau khi database đã commit | Xử lý lỗi hậu commit, retry hoặc outbox; không coi response error là rollback |
| Gửi message trùng khi retry | Consumer hoặc listener không idempotent | Dùng event ID, unique constraint và deduplication |
| Event bị mất khi ứng dụng dừng | Callback hoặc @Async task chỉ nằm trong bộ nhớ | Dùng transactional outbox và worker/CDC có retry |
| Test không nhận event | Test transaction mặc định rollback | Dùng TestTransaction commit hoặc test không có transaction bao ngoài |

## 11. Checklist triển khai

1. Xác định transaction bao quanh thao tác ghi repository và transaction manager đang dùng.
2. Publish immutable application/domain event trong transaction đó.
3. Dùng @TransactionalEventListener với AFTER_COMMIT cho tác vụ chỉ chạy sau commit.
4. Giữ fallbackExecution=false nếu không có transaction thì không được phép xử lý.
5. Với Spring Data REST event handler, kiểm tra transaction đang hoạt động trên endpoint thực tế; không suy luận từ tên AfterSaveEvent.
6. Với tác vụ ghi database sau commit, gọi service riêng dùng REQUIRES_NEW.
7. Với tác vụ chậm, cấu hình executor và cơ chế retry/monitoring; với giao nhận quan trọng, dùng outbox.
8. Kiểm thử cả commit, rollback, thiếu transaction và đường HTTP Spring Data REST.

## Tài liệu chính thức

- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework – TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Data REST – Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST – RepositoryEventHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryEventHandler.html)
- [Spring Data Commons – Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html)
- [Spring Framework – @TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework – TransactionalEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventPublisher.html)
