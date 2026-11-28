# Phân biệt callback SDN, sự kiện nghiệp vụ và sự kiện sau commit

Spring Data Neo4j (SDN) có nhiều điểm mở rộng quanh vòng đời entity và nghiệp vụ. Một callback có thể chỉnh entity trước khi SDN ghi nó vào graph; một domain event mô tả điều đã xảy ra trong nghiệp vụ; một transactional event listener chỉ chạy khi transaction đạt đến một phase đã chọn, thường là sau commit.

Ba cơ chế này có thể xuất hiện trong cùng một use case nhưng phục vụ mục đích khác nhau. Dùng callback để chuẩn hóa dữ liệu persistence, dùng domain event để diễn đạt sự kiện của aggregate, và dùng transaction-bound event để kích hoạt công việc phụ thuộc vào kết quả commit.

## 1. Ba cơ chế, ba thời điểm

Giả sử ứng dụng tạo một Order, lưu node và relationship vào Neo4j, rồi cần gửi thông báo cho khách hàng.

| Cơ chế | Thời điểm | Trách nhiệm phù hợp | Không nên dùng để |
| --- | --- | --- | --- |
| SDN entity callback | Trước khi bind entity thành dữ liệu ghi hoặc sau khi hydrate entity | Chuẩn hóa, bổ sung giá trị dẫn xuất, điều chỉnh entity | Gửi email, gọi hệ thống ngoài hoặc phát sự kiện nghiệp vụ |
| Domain/application event | Khi nghiệp vụ phát sinh một sự kiện và ứng dụng công bố nó | Mô tả sự kiện như OrderCreated, OrderCancelled | Khẳng định transaction đã commit |
| Transaction-bound event listener | Tại phase của transaction, ví dụ AFTER_COMMIT | Gửi thông báo hoặc khởi chạy công việc chỉ được phép sau commit | Thay thế cơ chế lưu trữ sự kiện bền vững |

Có thể hình dung thứ tự điển hình:

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant A as Aggregate
    participant C as SDN callback
    participant R as Repository
    participant E as Event listener
    participant DB as Neo4j

    S->>A: Tạo Order / thay đổi trạng thái
    S->>R: save(order)
    R->>C: BeforeBindCallback
    C-->>R: Entity đã chuẩn hóa
    R->>DB: Ghi node và relationship
    DB-->>R: Kết quả ghi
    R->>E: Publish domain event khi save hoàn tất
    E-->>R: @EventListener có thể chạy đồng bộ
    R-->>S: Order đã lưu
    S->>E: Publish application event nếu service chủ động phát
    Note over S,E: Application listener có thể chạy trước commit
    S->>DB: Commit transaction
    DB-->>S: Commit thành công
    Note over E: @TransactionalEventListener(AFTER_COMMIT)
    E->>E: Gửi thông báo
~~~

Sơ đồ thể hiện luồng khái niệm. Thời điểm publish event phụ thuộc nơi ứng dụng công bố sự kiện; điều quan trọng là callback persistence, thời điểm publish và transaction phase không phải cùng một điểm trong vòng đời.

## 2. SDN entity callback: hook trong vòng đời ánh xạ

Entity callback thuộc Spring Data callback infrastructure. SDN gọi callback tại một checkpoint xác định trong quá trình persistence hoặc hydration. Callback có thể trả lại cùng entity hoặc một instance đã được chỉnh sửa.

Hai callback thường dùng trong SDN:

- BeforeBindCallback<T>: được gọi trước khi entity được bind thành record/property map để ghi vào Neo4j.
- AfterConvertCallback<T>: được gọi sau khi record Neo4j đã được chuyển thành entity và các association của entity đã được xử lý.

Với reactive persistence, SDN có ReactiveBeforeBindCallback<T> thay cho BeforeBindCallback<T>. AfterConvertCallback hiện không có reactive variant riêng và được dùng cho cả imperative lẫn reactive workload.

### 2.1. BeforeBindCallback: chuẩn hóa trước khi ghi

Ví dụ, ứng dụng muốn bỏ khoảng trắng thừa ở tên Person trước khi SDN tạo dữ liệu ghi:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;

@Configuration
public class PersonCallbackConfiguration {

    @Bean
    BeforeBindCallback<Person> normalizePersonName() {
        return person -> {
            person.setName(person.getName().trim());
            return person;
        };
    }
}
~~~

Callback được đăng ký như một bean trong ApplicationContext. SDN tự phát hiện bean callback phù hợp; không cần gọi callback thủ công từ repository hoặc service.

Callback nhận entity trước khi SDN chuyển nó thành cấu trúc dữ liệu để bind. Giá trị trả về là entity mà SDN tiếp tục dùng để ghi. Vì vậy, nếu callback tạo instance mới cho immutable entity, phải trả về instance đó; không được bỏ qua giá trị trả về.

Ví dụ này phù hợp với chuẩn hóa dữ liệu persistence đơn giản. Quy tắc nghiệp vụ như tên có được phép đổi hay không, người dùng có quyền đổi tên hay không vẫn thuộc domain/service.

### 2.2. ReactiveBeforeBindCallback: callback trong reactive pipeline

Với repository reactive, triển khai ReactiveBeforeBindCallback<T> và trả về Publisher<T>:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.ReactiveBeforeBindCallback;
import reactor.core.publisher.Mono;

@Configuration
public class ReactivePersonCallbackConfiguration {

    @Bean
    ReactiveBeforeBindCallback<Person> normalizePersonName() {
        return person -> Mono.fromSupplier(() -> {
            person.setName(person.getName().trim());
            return person;
        });
    }
}
~~~

Reactive callback được thực thi khi publisher được subscribe, trước khi entity được bind để lưu. Nó có thể kết hợp một thao tác reactive cần thiết để tạo phiên bản entity sẽ được ghi, nhưng nên giữ callback ngắn và dễ dự đoán.

Không gọi subscribe() hoặc block() trong callback. Hãy trả publisher để SDN ghép nó vào luồng reactive persistence. Tránh gọi dịch vụ bên ngoài hoặc thực hiện side effect khó hoàn tác trong callback, vì callback là một phần của quá trình lưu entity.

### 2.3. AfterConvertCallback: chỉnh entity sau khi hydrate

AfterConvertCallback được gọi sau khi SDN đọc record Neo4j, ánh xạ property và xử lý association. Nó có thể bổ sung giá trị dẫn xuất mà ứng dụng không lưu thành property graph.

Ví dụ entity có một field chỉ phục vụ ứng dụng:

~~~java
import org.springframework.data.annotation.Transient;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    @Transient
    private String displayLabel;

    public String getName() {
        return name;
    }

    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }

    // Các constructor và accessor khác được lược bỏ.
}
~~~

Callback thiết lập displayLabel sau khi entity đã được hydrate:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.mapping.callback.AfterConvertCallback;
import java.util.Locale;

@Configuration
public class PersonReadCallbackConfiguration {

    @Bean
    AfterConvertCallback<Person> deriveDisplayLabel() {
        return (person, entityMetadata, source) -> {
            person.setDisplayLabel(person.getName().toUpperCase(Locale.ROOT));
            return person;
        };
    }
}
~~~

Callback nhận ba thông tin: entity đã hydrate, metadata của persistent entity và record nguồn từ Neo4j. Nó trả về instance được SDN sử dụng tiếp.

AfterConvertCallback không phải callback sau commit và cũng không phải sự kiện sau khi ghi. Nó chạy sau khi một record được ánh xạ thành entity. Theo API SDN hiện hành, callback này không có reactive variant riêng và có thể được dùng trong cả imperative lẫn reactive workload. Vì vậy, không đặt thao tác blocking hoặc I/O đồng bộ dài trong callback này.

### 2.4. Đăng ký, thứ tự và phạm vi callback

SDN phát hiện các callback bean trong ApplicationContext. Nếu có nhiều callback cùng áp dụng cho một entity, có thể xác định thứ tự bằng Ordered hoặc @Order.

~~~java
import org.springframework.core.annotation.Order;

@Bean
@Order(10)
BeforeBindCallback<Person> normalizeName() {
    return person -> {
        person.setName(person.getName().trim());
        return person;
    };
}

@Bean
@Order(20)
BeforeBindCallback<Person> normalizeEmail() {
    return person -> {
        person.setEmail(person.getEmail().trim().toLowerCase());
        return person;
    };
}
~~~

Thứ tự rõ ràng giúp callback sau nhận entity đã được callback trước xử lý. Tránh tạo nhiều callback cùng sửa một field mà không có quy tắc ưu tiên.

Callback được gắn với kiểu domain qua generic type. Hãy giữ callback tập trung vào một thay đổi kỹ thuật cụ thể và tránh để callback phụ thuộc vào một use case lớn.

## 3. Domain event: diễn đạt sự kiện nghiệp vụ

Domain event mô tả một sự kiện có ý nghĩa trong domain, thường được phát ra khi aggregate thay đổi trạng thái hợp lệ. Ví dụ:

- OrderCreated: một đơn hàng đã được tạo.
- OrderConfirmed: đơn hàng đã được xác nhận.
- MembershipRevoked: thành viên đã bị thu hồi quyền tham gia.
- AccountSuspended: tài khoản đã bị khóa.

Event nên mang dữ liệu cần thiết để listener hiểu điều gì đã xảy ra, thường gồm ID aggregate, thời điểm và các giá trị nghiệp vụ cần thiết. Event không nên mang cả entity graph lớn hoặc một repository để listener tự truy cập tùy ý.

### 3.1. Đăng ký domain event trong aggregate root

Spring Data hỗ trợ @DomainEvents và @AfterDomainEventPublication trên aggregate root. Ví dụ có thể dùng AbstractAggregateRoot để lưu event chờ publish:

~~~java
import org.springframework.data.domain.AbstractAggregateRoot;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Order")
public class Order extends AbstractAggregateRoot<Order> {

    @Id
    private String id;

    private String status;

    public void confirm() {
        if (!"PENDING".equals(status)) {
            throw new IllegalStateException(
                "Chỉ đơn hàng đang chờ mới được xác nhận"
            );
        }

        this.status = "CONFIRMED";
        registerEvent(new OrderConfirmed(this.id));
    }

    public String getId() {
        return id;
    }
}
~~~

Event là một kiểu dữ liệu độc lập:

~~~java
public record OrderConfirmed(String orderId) {}
~~~

Khi repository thực hiện save(order), Spring Data đọc các domain event mà aggregate cung cấp và publish chúng. AbstractAggregateRoot cung cấp registerEvent(...) để giữ event, domainEvents() để trả các event đang chờ và cơ chế xóa event sau khi publish.

Có thể triển khai cơ chế tương tự trực tiếp bằng annotation:

~~~java
import java.util.Collection;
import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

@DomainEvents
Collection<Object> domainEvents() {
    return pendingEvents;
}

@AfterDomainEventPublication
void clearPublishedEvents() {
    pendingEvents.clear();
}
~~~

Phương thức @DomainEvents không nhận tham số và có thể trả một event hoặc collection event. @AfterDomainEventPublication được gọi sau khi các event đã được publish, thường dùng để dọn danh sách event chờ.

Tên @AfterDomainEventPublication dễ gây nhầm lẫn: annotation này nói về việc dọn event sau khi Spring Data đã publish event, không có nghĩa transaction Neo4j đã commit.

### 3.2. Repository nào kích hoạt domain event?

Spring Data publish domain events khi gọi các phương thức repository có aggregate instance làm đầu vào, chẳng hạn save, saveAll, delete và các biến thể delete nhận entity.

Các phương thức chỉ nhận ID như deleteById không có aggregate instance để đọc domain events. Vì vậy, không nên dựa vào @DomainEvents để phát sự kiện từ thao tác xóa chỉ có ID.

Domain event được publish trong quá trình gọi repository. Nếu repository được gọi bên trong một transaction, event có thể được publish trước khi transaction commit. Bản thân @DomainEvents không trì hoãn publication đến sau commit.

Danh sách domain event trong AbstractAggregateRoot hoặc field do aggregate tự quản lý là trạng thái trong bộ nhớ; @DomainEvents không tự lưu event thành node trong Neo4j. Sau khi event được publish, danh sách thường được dọn ngay cả khi transaction bao ngoài sau đó rollback. Vì vậy, domain event giúp phát tín hiệu trong ứng dụng nhưng không thay thế outbox khi cần bảo đảm giao nhận bền vững.

## 4. Application event và @EventListener

Ứng dụng cũng có thể publish một application event trực tiếp qua ApplicationEventPublisher. Ví dụ dưới đây dùng ManualReviewRequested, một sự kiện riêng của luồng ứng dụng; nó không phải OrderConfirmed đã được aggregate đăng ký ở phần trước:

~~~java
public record ManualReviewRequested(String orderId) {}
~~~

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
    public Order requestManualReview(String orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();

        // Phương thức domain này kiểm tra điều kiện và đổi trạng thái,
        // nhưng không đăng ký ManualReviewRequested qua registerEvent().
        order.requestManualReview();
        Order saved = orderRepository.save(order);

        eventPublisher.publishEvent(new ManualReviewRequested(saved.getId()));

        return saved;
    }
}
~~~

Listener thông thường dùng @EventListener:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMetricsListener {

    @EventListener
    public void onManualReviewRequested(ManualReviewRequested event) {
        // Cập nhật metric hoặc xử lý logic ứng dụng phù hợp.
    }
}
~~~

Mặc định, Spring application event listener chạy đồng bộ trên thread publish event. Vì vậy, khi event được publish bên trong một transaction, listener thông thường có thể chạy ngay trong lúc transaction vẫn đang mở, trước khi commit diễn ra.

Nếu transaction rollback sau đó, listener đã chạy vẫn không tự được hoàn tác. Ví dụ, email đã gửi hoặc HTTP request đã thực hiện không biến mất chỉ vì Neo4j rollback.

Có thể cấu hình listener bất đồng bộ, chẳng hạn dùng @Async, nhưng khi đó listener chạy ở thread khác và không được mặc định kế thừa transaction context hoặc trạng thái bảo mật/logging context của thread publish. Không xem asynchronous event listener là cách bảo đảm listener chỉ chạy sau commit.

## 5. Sự kiện sau commit với @TransactionalEventListener

Khi listener chỉ được chạy nếu transaction commit thành công, dùng @TransactionalEventListener:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    private final NotificationService notificationService;

    public OrderNotificationListener(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmed event) {
        notificationService.sendConfirmation(event.orderId());
    }
}
~~~

Nếu không khai báo phase, mặc định là AFTER_COMMIT. Listener chỉ được gọi sau khi transaction chứa event commit thành công. Nếu transaction rollback, listener AFTER_COMMIT không chạy.

Spring hỗ trợ các phase sau:

| Phase | Thời điểm |
| --- | --- |
| BEFORE_COMMIT | Ngay trước khi transaction commit |
| AFTER_COMMIT | Sau khi commit thành công; mặc định |
| AFTER_ROLLBACK | Sau khi transaction rollback |
| AFTER_COMPLETION | Sau khi transaction hoàn tất, bất kể commit hay rollback |

Nếu không có transaction đang hoạt động, transactional event listener mặc định không được gọi. Có thể đặt fallbackExecution = true để cho phép xử lý cả khi event không được publish trong transaction, nhưng hãy dùng khi nghiệp vụ thực sự chấp nhận cả hai trường hợp.

### 5.1. Ghi database từ listener sau commit

Sau AFTER_COMMIT, transaction ban đầu đã hoàn tất. Spring lưu ý tài nguyên transaction có thể vẫn còn khả dụng trong quá trình callback hoàn tất, nhưng thay đổi database phát sinh lúc này không được commit vào transaction cũ.

Nếu listener cần ghi thêm vào Neo4j, hãy gọi một service khác mở transaction mới, thường bằng propagation REQUIRES_NEW:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateProjection(OrderConfirmed event) {
        // Ghi projection hoặc dữ liệu phụ trong transaction mới.
    }
}
~~~

Listener AFTER_COMMIT gọi OrderProjectionService qua bean Spring được inject. Tránh tự gọi method REQUIRES_NEW trong cùng object bằng this vì self-invocation không đi qua transaction proxy mặc định.

## 6. Ghép domain event với sự kiện sau commit

Một cách tổ chức rõ ràng là để aggregate phát ra domain event, repository publish event và listener quyết định thời điểm xử lý.

Luồng ví dụ:

1. Order.confirm() kiểm tra quy tắc domain, đổi trạng thái và đăng ký OrderConfirmed.
2. OrderRepository.save(order) ghi entity và publish domain event.
3. Một listener @EventListener có thể xử lý ngay trong luồng publish.
4. Một listener @TransactionalEventListener(AFTER_COMMIT) chỉ xử lý khi transaction commit thành công.

Cùng một domain event có thể có nhiều listener với mục đích khác nhau. Hãy tránh để listener đồng bộ thực hiện side effect không thể hoàn tác nếu nghiệp vụ yêu cầu chỉ hành động sau commit.

Domain event giúp domain không phải phụ thuộc trực tiếp vào ApplicationEventPublisher. Transaction-bound listener quyết định thời điểm xử lý theo transaction outcome. Hai cơ chế có thể kết hợp nhưng không thay thế nhau.

## 7. Reactive transaction và transactional event

Reactive transaction của Spring dùng Reactor Context thay vì thread-bound transaction. Từ Spring Framework 6.1, @TransactionalEventListener hỗ trợ cả transaction imperative và reactive, nhưng event phát trong reactive transaction cần mang TransactionContext trong event source.

Với reactive flow, có thể dùng TransactionalEventPublisher. Đây là delegate giúp tạo event có Reactor-managed TransactionContext làm source:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.reactive.TransactionalEventPublisher;

@Configuration
public class TransactionalEventConfiguration {

    @Bean
    TransactionalEventPublisher transactionalEventPublisher(
            ApplicationEventPublisher publisher) {
        return new TransactionalEventPublisher(publisher);
    }
}
~~~

Service reactive publish event và nối publisher vào pipeline. Ví dụ này dùng ReactiveOrder không đăng ký OrderConfirmed qua @DomainEvents; sự kiện được publish tường minh bằng TransactionalEventPublisher. Nếu aggregate đã tự đăng ký cùng event qua registerEvent(), không publish lại cùng payload:

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface ReactiveOrderRepository
        extends ReactiveNeo4jRepository<ReactiveOrder, String> {
}
~~~

ReactiveOrder trong ví dụ này có phương thức confirm() chỉ đổi trạng thái domain; nó không gọi registerEvent().

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;
    private final TransactionalEventPublisher eventPublisher;

    public ReactiveOrderService(
            ReactiveOrderRepository orderRepository,
            TransactionalEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Mono<ReactiveOrder> confirm(String orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Không tìm thấy Order")
            ))
            .flatMap(order -> {
                order.confirm();

                return orderRepository.save(order)
                    .flatMap(saved ->
                        eventPublisher.publishEvent(
                            new OrderConfirmed(saved.getId())
                        ).thenReturn(saved)
                    );
            });
    }
}
~~~

Listener có thể dùng @TransactionalEventListener(AFTER_COMMIT) như trường hợp imperative. Event publisher phải được gọi bên trong reactive transaction context và publisher trả về cần được nối vào pipeline. Không gọi subscribe() thủ công để publish event ngoài chuỗi transaction.

Nếu dùng Spring Framework trước 6.1, không giả định @TransactionalEventListener có thể liên kết với reactive transaction. Hãy kiểm tra phiên bản Spring Framework đang được SDN/Spring Boot quản lý.

## 8. Sau commit không đồng nghĩa với giao nhận bền vững

@TransactionalEventListener(AFTER_COMMIT) giúp tránh xử lý event khi transaction rollback, nhưng event vẫn là cơ chế in-process. Nó không tự lưu event vào một hàng đợi bền vững và không bảo đảm listener sẽ hoàn tất nếu tiến trình dừng ngay sau commit.

Ví dụ, transaction commit thành công nhưng ứng dụng dừng trước khi listener gửi email. Không có record bền vững nào để một worker khác biết rằng email còn phải gửi.

Nếu cần bảo đảm xử lý eventual delivery, dùng Transactional Outbox:

1. Trong transaction Neo4j, ghi thay đổi nghiệp vụ và tạo node OutboxEvent.
2. Commit cả aggregate và outbox node cùng lúc.
3. Worker đọc các outbox event chưa xử lý.
4. Worker gửi message/email tới hệ thống ngoài bằng idempotency key.
5. Đánh dấu event đã xử lý hoặc lưu trạng thái retry.
6. Nếu worker lỗi, event vẫn còn để thử lại.

Outbox tạo một nguồn dữ liệu bền vững cho việc giao nhận. Listener AFTER_COMMIT có thể được dùng để đánh thức worker hoặc phát tín hiệu tối ưu, nhưng worker vẫn cần đọc outbox để không phụ thuộc vào một lần gọi in-process duy nhất.

## 9. Chọn đúng cơ chế theo nhu cầu

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Chuẩn hóa tên trước khi ghi | BeforeBindCallback hoặc ReactiveBeforeBindCallback | Chạy đúng checkpoint trước khi bind entity |
| Bổ sung field dẫn xuất sau khi đọc graph | AfterConvertCallback | Entity và association đã được hydrate |
| Ghi nhận sự kiện domain khi aggregate đổi trạng thái | @DomainEvents hoặc AbstractAggregateRoot | Sự kiện được phát ra từ hành vi domain |
| Listener xử lý ngay khi event được publish | @EventListener | Xử lý application event thông thường |
| Gửi thông báo chỉ sau commit | @TransactionalEventListener(AFTER_COMMIT) | Không chạy khi transaction rollback |
| Phản ứng với rollback | @TransactionalEventListener(AFTER_ROLLBACK) | Chỉ xử lý khi transaction rollback |
| Ghi database mới từ listener sau commit | Service với REQUIRES_NEW | Tạo transaction mới độc lập |
| Giao message bền vững cho hệ thống khác | Transactional Outbox | Event tồn tại qua restart và có thể retry |

## 10. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gửi email trong BeforeBindCallback | Callback persistence tạo side effect trước khi biết transaction có commit | Dùng event sau commit hoặc outbox |
| Dùng AfterConvertCallback như callback sau save | Nhầm thời điểm hydrate với thời điểm ghi | Chọn callback đúng lifecycle |
| Nghĩ @AfterDomainEventPublication là AFTER_COMMIT | Event queue được dọn trước khi transaction hoàn tất | Dùng @TransactionalEventListener cho transaction phase |
| Dùng @EventListener cho thông báo chỉ được gửi sau commit | Listener có thể chạy trước khi transaction rollback | Chuyển sang AFTER_COMMIT |
| Listener sau commit ghi database trong transaction cũ | Thay đổi mới có thể không được commit | Gọi service dùng REQUIRES_NEW |
| Gọi callback reactive bằng subscribe() thủ công | Tách thao tác khỏi pipeline SDN | Trả Publisher từ ReactiveBeforeBindCallback |
| Dùng callback để chứa quy tắc domain | Logic nghiệp vụ bị ẩn trong persistence infrastructure | Chuyển quy tắc vào aggregate/service |
| Dựa vào event in-process để bảo đảm giao message | Có thể mất event nếu tiến trình dừng sau commit | Dùng Transactional Outbox |

## 11. Kiểm thử callback và event theo đúng thời điểm

Mỗi cơ chế cần một loại kiểm thử riêng:

**Entity callback**

- Lưu entity và xác nhận BeforeBindCallback đã chuẩn hóa giá trị trước khi ghi.
- Đọc entity và xác nhận AfterConvertCallback chạy sau khi association được hydrate.
- Với reactive repository, xác nhận ReactiveBeforeBindCallback được thực thi khi subscription chạy.
- Nếu có nhiều callback, xác nhận thứ tự theo @Order hoặc Ordered.

**Domain event**

- Gọi hành vi aggregate và xác nhận event được đăng ký.
- Gọi repository save và xác nhận event được publish.
- Xác nhận danh sách event được dọn sau publication khi dùng @AfterDomainEventPublication hoặc AbstractAggregateRoot.
- Kiểm tra thao tác deleteById không dựa vào aggregate instance để phát domain event.

**Transactional event**

- Commit transaction và xác nhận AFTER_COMMIT listener chạy.
- Rollback transaction và xác nhận AFTER_COMMIT listener không chạy.
- Xác nhận AFTER_ROLLBACK listener chỉ chạy khi rollback.
- Publish event ngoài transaction và xác nhận listener mặc định không chạy nếu fallbackExecution không bật.
- Nếu listener cần ghi database, xác nhận transaction REQUIRES_NEW được mở.
- Với reactive transaction, kiểm tra event được publish bằng TransactionalEventPublisher trong cùng Reactor pipeline.

Trong integration test, gọi service thông qua bean Spring để transaction interceptor thực sự hoạt động. Không chỉ gọi trực tiếp method trên object được tạo bằng new. Với reactive code, dùng StepVerifier để subscribe publisher và kiểm tra kết quả; sau đó truy vấn Neo4j để xác nhận trạng thái graph và event listener.

## 12. Quy trình chọn cơ chế

Trước khi thêm callback hoặc event, hãy trả lời lần lượt:

1. Bạn cần thay đổi entity trong quá trình đọc/ghi hay phản ứng với một sự kiện nghiệp vụ?
2. Nếu là thay đổi entity, nó xảy ra trước khi bind hay sau khi hydrate?
3. Nếu là sự kiện nghiệp vụ, aggregate nào sở hữu hành vi phát sự kiện?
4. Listener có cần biết transaction đã commit hay rollback chưa?
5. Nếu listener chạy sau commit, nó có cần ghi thêm database không?
6. Event cần xử lý trong process hay cần giao nhận bền vững qua restart?
7. Use case đang imperative hay reactive, và event có mang đúng transaction context không?

Khi trả lời được các câu hỏi này, có thể chọn cơ chế phù hợp mà không làm lẫn logic persistence, domain và side effect.

## 13. Bài tập tự kiểm tra

1. BeforeBindCallback chạy ở thời điểm nào trong quá trình lưu entity?
2. AfterConvertCallback khác callback trước khi ghi như thế nào?
3. Vì sao SDN có ReactiveBeforeBindCallback nhưng AfterConvertCallback không có reactive variant riêng?
4. @DomainEvents được gọi thông qua những repository operation nào?
5. @AfterDomainEventPublication có nghĩa transaction đã commit không?
6. @EventListener khác @TransactionalEventListener(AFTER_COMMIT) ở thời điểm chạy như thế nào?
7. Nếu listener sau commit cần ghi thêm node vào Neo4j, nên dùng transaction propagation nào?
8. Vì sao AFTER_COMMIT listener không bảo đảm message được giao bền vững?
9. TransactionalEventPublisher giải quyết vấn đề gì khi publish event trong reactive transaction?
10. Khi nào nên dùng Transactional Outbox thay cho event listener in-process?

Khi hoàn thành bài học, bạn cần phân biệt được lifecycle callback của SDN, domain event của aggregate và transactional event listener. Bạn cũng cần biết đặt side effect đúng thời điểm, xử lý riêng imperative/reactive transaction và chọn outbox khi cần giao nhận sự kiện bền vững trong ứng dụng Spring Data Neo4j.

## Tài liệu tham khảo

- [Spring Data Neo4j – FAQ và callbacks](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – BeforeBindCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/BeforeBindCallback.html)
- [Spring Data Neo4j – AfterConvertCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/AfterConvertCallback.html)
- [Spring Data – Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/jpa/reference/repositories/core-domain-events.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring/reference/data-access/transaction/event.html)
- [Spring Framework – TransactionalEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)

