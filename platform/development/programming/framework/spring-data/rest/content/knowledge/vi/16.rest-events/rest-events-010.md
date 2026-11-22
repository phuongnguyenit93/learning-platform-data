# Phân biệt REST event, repository domain event và callback của JPA

Trong ứng dụng Spring Data REST, một thao tác tạo, sửa hoặc xóa entity có thể kích hoạt nhiều cơ chế sự kiện. Ba cơ chế thường bị nhầm lẫn là **Spring Data REST event**, **Spring Data repository domain event** và **JPA lifecycle callback**.

Chúng khác nhau ở nơi phát sinh và mục đích:

- **REST event** do Spring Data REST exporter phát khi xử lý request qua REST resource.
- **Repository domain event** do Spring Data phát khi repository thao tác với aggregate root có công bố domain event.
- **JPA callback** do persistence provider gọi khi entity được persist, update, remove hoặc load.

Một request REST có thể đi qua cả ba cơ chế. Nhưng một lần gọi repository từ service có thể phát domain event và JPA callback mà không có REST event. Một thao tác JPA trực tiếp cũng có thể chạy callback mà không đi qua Spring Data repository.

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận biết nguồn phát và phạm vi của ba loại event/callback.
- Dùng **@RepositoryEventHandler** và các annotation **@Handle...** để xử lý REST event.
- Công bố domain event bằng **@DomainEvents**, **@AfterDomainEventPublication** hoặc **AbstractAggregateRoot**.
- Dùng JPA callback như **@PrePersist**, **@PostPersist**, **@PreUpdate**, **@PreRemove** và **@PostLoad**.
- Chọn đúng cơ chế cho validation, business rule, audit và side effect.
- Phân biệt thời điểm “đã save” với thời điểm transaction đã commit.

## 1. So sánh nhanh

| Tiêu chí | Spring Data REST event | Spring Data repository domain event | JPA lifecycle callback |
| --- | --- | --- | --- |
| Ai phát? | REST exporter | Spring Data repository infrastructure | JPA persistence provider |
| Khi nào? | Request đi qua REST exporter và xử lý repository/association resource | Repository gọi thao tác được hỗ trợ trên aggregate root có domain event | Entity đi qua lifecycle persistence |
| Phụ thuộc REST? | Có | Không | Không |
| Phụ thuộc repository? | Có | Có | Không |
| Đối tượng quan tâm | Entity đang được REST exporter xử lý | Aggregate root và sự kiện nghiệp vụ do aggregate ghi nhận | Entity hoặc mapped superclass |
| API tiêu biểu | @RepositoryEventHandler, @HandleBeforeSave | @DomainEvents, @AfterDomainEventPublication, AbstractAggregateRoot | @PrePersist, @PostPersist, @PreUpdate, @PostUpdate, @PreRemove, @PostRemove, @PostLoad |
| Ví dụ mục đích | Chuẩn hóa dữ liệu nhận qua REST | Phát OrderPaid hoặc OrderPlaced | Gán timestamp, xử lý đơn giản theo lifecycle entity |

Có thể nhớ theo ba câu hỏi:

- “Request REST đang làm gì với resource?” → REST event.
- “Aggregate vừa phát sinh sự kiện nghiệp vụ nào?” → Domain event.
- “Persistence provider đang làm gì với entity?” → JPA callback.

## 2. Spring Data REST event

Spring Data REST exporter phát các Spring application event trong quá trình xử lý entity qua REST. Tài liệu Spring Data REST 5.1 liệt kê tám event chính:

| Event | Thời điểm |
| --- | --- |
| BeforeCreateEvent | Trước khi entity mới được lưu lần đầu qua REST |
| AfterCreateEvent | Sau khi entity mới được lưu qua REST |
| BeforeSaveEvent | Trước khi entity hiện có được lưu qua REST |
| AfterSaveEvent | Sau khi entity được lưu qua REST |
| BeforeLinkSaveEvent | Trước khi lưu hoặc cập nhật liên kết tới entity liên quan |
| AfterLinkSaveEvent | Sau khi lưu hoặc cập nhật liên kết |
| BeforeDeleteEvent | Trước khi xóa entity qua REST |
| AfterDeleteEvent | Sau khi xóa entity qua REST |

Ví dụ, client gửi:

~~~http
POST /orders
Content-Type: application/json
Accept: application/hal+json

{
  "customerName": "An",
  "status": "NEW"
}
~~~

REST exporter có thể phát BeforeCreateEvent, thực hiện thao tác lưu qua repository rồi phát AfterCreateEvent.

Nếu service gọi trực tiếp:

~~~java
orderRepository.save(order);
~~~

thì REST event không tự phát sinh chỉ vì repository được Spring Data REST export. Luồng này không đi qua REST exporter.

### 2.1. Xử lý bằng @RepositoryEventHandler

Tạo một Spring bean và đặt các annotation @Handle... trên method:

~~~java
import org.springframework.data.rest.core.annotation.HandleAfterCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler(Order.class)
public class OrderRestEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Order order) {
        if (order.getCustomerName() == null
                || order.getCustomerName().isBlank()) {
            throw new IllegalArgumentException(
                    "Customer name is required");
        }
    }

    @HandleBeforeSave
    public void beforeSave(Order order) {
        order.normalizeCustomerName();
    }

    @HandleAfterCreate
    public void afterCreate(Order order) {
        // Xử lý hậu tạo riêng cho luồng REST.
    }
}
~~~

Điểm cần nhớ:

- @RepositoryEventHandler(Order.class) giới hạn handler cho domain type Order.
- Nếu bỏ đối số domain type, Spring Data REST xác định loại entity từ kiểu tham số đầu tiên của method handler.
- Method handler nhận entity đang được xử lý.
- Bean phải được Spring quản lý, ví dụ dùng @Component hoặc khai báo bằng @Bean.
- Có thể khai báo nhiều method handler cho nhiều event hoặc domain type.

REST event phù hợp với logic gắn riêng với HTTP boundary, ví dụ chuẩn hóa payload hoặc kiểm tra quy tắc chỉ áp dụng cho request REST. Không đặt business rule cốt lõi duy nhất trong REST handler nếu service, batch job hoặc message consumer cũng cần dùng quy tắc đó.

### 2.2. Phạm vi và tính đồng bộ

REST event chỉ chạy khi thao tác đi qua Spring Data REST exporter. Nó không tự bắt thay đổi từ service, batch job, message consumer hoặc repository call trực tiếp.

Theo mặc định, Spring application event được xử lý đồng bộ trong thread phát event, trừ khi ứng dụng cấu hình executor hoặc chuyển event qua một ranh giới xử lý khác. Vì vậy handler có thể ảnh hưởng thời gian phản hồi của request.

AfterCreateEvent và AfterSaveEvent có nghĩa là REST exporter đã đi qua bước save tương ứng. Chúng không chứng minh transaction đã commit thành công.

## 3. Spring Data repository domain event

Spring Data hỗ trợ aggregate root công bố **domain event**. Đây là sự kiện mô tả điều đã xảy ra trong nghiệp vụ, chẳng hạn OrderPlaced, OrderPaid, ShipmentDispatched hoặc AccountClosed.

Domain event được tạo từ hành vi của aggregate root. Spring Data repository infrastructure đọc các event đó khi repository gọi những thao tác được hỗ trợ và phát chúng dưới dạng Spring application event.

Cơ chế này không phụ thuộc request HTTP. Nếu service gọi repository.save(order), domain event vẫn có thể được phát miễn là aggregate root đã ghi nhận event và repository call thuộc nhóm được hỗ trợ.

### 3.1. Dùng @DomainEvents và @AfterDomainEventPublication

Một aggregate root có thể tự quản lý danh sách event:

~~~java
@Entity
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Transient
    private final List<Object> events = new ArrayList<>();

    public void markPaid() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                    "Only pending orders can be paid");
        }

        status = OrderStatus.PAID;
        events.add(new OrderPaid(id));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return events;
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        events.clear();
    }
}
~~~

Trong ví dụ:

- Method có @DomainEvents không nhận tham số.
- Method có thể trả về một event đơn lẻ hoặc một collection event.
- Spring Data lấy các event từ aggregate root khi gọi repository method được hỗ trợ.
- Sau khi publish xong, method có @AfterDomainEventPublication được gọi; ví dụ dùng nó để xóa các event đã phát khỏi danh sách.

Trường events là trạng thái tạm thời trong bộ nhớ, không phải dữ liệu nghiệp vụ cần persist. Có thể dùng @Transient của JPA để loại nó khỏi mapping persistence khi entity dùng field access; điều chỉnh theo access strategy của entity.

### 3.2. Dùng AbstractAggregateRoot

Spring Data cung cấp **AbstractAggregateRoot** để không phải tự viết danh sách event và hai method annotation:

~~~java
@Entity
public class Order
        extends AbstractAggregateRoot<Order> {

    @Id
    @GeneratedValue
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    public void markPaid() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                    "Only pending orders can be paid");
        }

        status = OrderStatus.PAID;
        andEvent(new OrderPaid(id));
    }
}
~~~

andEvent(…) đăng ký event để Spring Data publish khi repository lưu hoặc xóa aggregate root. AbstractAggregateRoot cũng cung cấp registerEvent(…), andEventsFrom(…) và clearDomainEvents() cho các trường hợp cần kiểm soát cụ thể hơn.

Ví dụ event là kiểu dữ liệu bất biến:

~~~java
public record OrderPaid(Long orderId) {
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

Service thay đổi trạng thái rồi lưu aggregate:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void markPaid(Long id) {
        Order order = repository.findById(id)
                .orElseThrow();

        order.markPaid();
        repository.save(order);
    }
}
~~~

Spring Data đọc và publish domain event đã đăng ký trên aggregate root khi repository xử lý save.

### 3.3. Lắng nghe domain event

Domain event được publish dưới dạng Spring application event. Có thể nhận bằng @EventListener:

~~~java
@Component
public class OrderDomainEventHandler {

    @EventListener
    public void on(OrderPaid event) {
        // Cập nhật read model hoặc xử lý logic nội bộ.
    }
}
~~~

Nếu xử lý cần chờ transaction commit thành công, dùng **@TransactionalEventListener**:

~~~java
@Component
public class OrderNotificationHandler {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPaid event) {
        // Gửi thông báo sau khi transaction đã commit.
    }
}
~~~

Mặc định, @TransactionalEventListener gắn với phase AFTER_COMMIT. Các phase khác gồm BEFORE_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION. Nếu không có transaction đang chạy, listener không được gọi theo mặc định; chỉ bật fallbackExecution khi có chủ đích rõ ràng.

**@AfterDomainEventPublication không có nghĩa là AFTER_COMMIT.** Annotation đó chỉ đánh dấu rằng Spring Data đã publish các domain event lấy từ aggregate. Nó không xác nhận database transaction đã commit.

### 3.4. Repository method nào phát domain event?

Tài liệu Spring Data mô tả việc kiểm tra domain event cho các thao tác repository như save(…), saveAll(…), delete(…) và một số biến thể delete nhận aggregate root hoặc tập aggregate root.

**deleteById(…) không nằm trong danh sách được hỗ trợ cho domain event publication.** Một số implementation có thể thực hiện xóa bằng query trực tiếp mà không nạp aggregate instance; khi đó Spring Data không có object để đọc domain event từ aggregate.

Nếu nghiệp vụ cần phát OrderCancelled hoặc OrderDeleted, hãy thực hiện thao tác trên aggregate root rồi gọi repository method nhận chính aggregate đó, thay vì giả định mọi lệnh delete đều tự phát domain event.

Domain event phù hợp để diễn đạt sự kiện nghiệp vụ ở cấp aggregate. Không dùng nó chỉ để phát tín hiệu “Hibernate vừa chạy câu SQL UPDATE”; đó là khái niệm khác.

## 4. JPA lifecycle callback

JPA callback được persistence provider gọi khi entity trải qua các giai đoạn trong vòng đời persistence. Callback có thể được khai báo trực tiếp trên entity, mapped superclass hoặc entity listener class.

Các annotation chuẩn:

| Callback | Khi được gọi |
| --- | --- |
| @PrePersist | Trước khi entity được persist |
| @PostPersist | Sau khi entity đã được insert vào database |
| @PreUpdate | Trước thao tác update dữ liệu entity |
| @PostUpdate | Sau thao tác update dữ liệu entity |
| @PreRemove | Trước khi entity bị remove |
| @PostRemove | Sau khi entity bị remove |
| @PostLoad | Sau khi entity được load hoặc refresh |

Các callback này do JPA provider quản lý. Chúng có thể chạy dù entity được thay đổi từ Spring Data REST, service gọi repository, EntityManager trực tiếp hoặc một luồng persistence khác.

### 4.1. Khai báo callback trên entity

Ví dụ tự gán timestamp:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private Instant createdAt;
    private Instant updatedAt;

    @PrePersist
    protected void beforeInsert() {
        createdAt = Instant.now();
        updatedAt = createdAt;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
~~~

JPA gọi beforeInsert khi entity được persist lần đầu và beforeUpdate trước thao tác update dữ liệu entity.

Callback method đặt trên entity hoặc mapped superclass có chữ ký không tham số và trả về void. Method có thể dùng mức truy cập public, protected, package-private hoặc private; không được khai báo static hoặc final.

### 4.2. Tách callback vào EntityListener

Có thể tách logic dùng chung sang listener:

~~~java
public class CustomerAuditListener {

    @PrePersist
    public void beforePersist(Customer customer) {
        Instant now = Instant.now();
        customer.setCreatedAt(now);
        customer.setUpdatedAt(now);
    }

    @PreUpdate
    public void beforeUpdate(Customer customer) {
        customer.setUpdatedAt(Instant.now());
    }
}
~~~

Gắn listener vào entity:

~~~java
@Entity
@EntityListeners(CustomerAuditListener.class)
public class Customer {

    // Entity fields and methods.
}
~~~

Method trong entity listener nhận entity instance làm tham số. Listener có thể áp dụng cho nhiều entity tương thích nếu được khai báo ở mapped superclass hoặc cấu hình listener phù hợp.

### 4.3. Thời điểm callback và flush

Không phải mọi callback đều chạy đúng tại thời điểm ứng dụng gọi repository.save():

- @PrePersist được gọi đồng bộ trong thao tác persist hoặc merge khi entity mới được tạo managed instance.
- @PostPersist chạy sau thao tác INSERT. INSERT có thể xảy ra ngay trong persist hoặc muộn hơn khi persistence context flush, ví dụ gần cuối transaction.
- @PreUpdate và @PostUpdate gắn với thao tác UPDATE; thời điểm SQL chạy có thể là lúc flush.
- @PreRemove và @PostRemove gắn với quá trình xóa entity.
- @PostLoad chạy sau khi entity được nạp vào persistence context hoặc sau refresh.

Với chiến lược IDENTITY, khóa chính sinh tự động chưa có trong @PrePersist; khóa chính đã có trong @PostPersist. Với SEQUENCE, TABLE hoặc UUID, ID có thể đã có trước @PrePersist tùy chiến lược sinh khóa theo đặc tả.

### 4.4. Giới hạn của JPA callback

JPA callback được thiết kế cho logic gắn với lifecycle persistence của entity. Không nên biến callback thành nơi điều phối nghiệp vụ phức tạp.

Theo đặc tả Jakarta Persistence:

- Callback có thể thay đổi trạng thái không phải quan hệ của chính entity đang được callback.
- Nhìn chung, callback portable không nên gọi EntityManager hoặc query, truy cập entity khác hay thay đổi relationship trong cùng persistence context.
- Runtime exception từ callback trong transaction có thể khiến transaction bị đánh dấu rollback.
- Thứ tự callback giữa các entity liên quan trong quá trình cascade có phần phụ thuộc implementation; không viết logic dựa vào thứ tự không được đặc tả bảo đảm.

Các lệnh bulk JPQL update/delete hoặc SQL trực tiếp không đi qua lifecycle của từng managed entity theo cách thông thường. Không nên kỳ vọng @PreUpdate hoặc @PostRemove chạy cho mỗi dòng bị thay đổi bởi bulk statement.

Nếu cần phản ứng với thao tác bulk, hãy phát application/domain event ở tầng thực hiện lệnh hoặc dùng cơ chế audit phù hợp với database.

## 5. Không nhầm “after save” với “after commit”

Đây là điểm dễ gây lỗi khi gửi email, gọi dịch vụ ngoài, phát message hoặc cập nhật hệ thống khác.

| Mốc | Điều được xác nhận |
| --- | --- |
| AfterSaveEvent | Spring Data REST đã đi qua bước save của REST exporter |
| @AfterDomainEventPublication | Spring Data đã publish domain event lấy từ aggregate |
| @PostPersist / @PostUpdate | Persistence provider đã thực hiện thao tác INSERT/UPDATE tương ứng |
| TransactionPhase.AFTER_COMMIT | Transaction đã commit thành công |

Một thao tác save có thể chỉ đồng bộ entity vào persistence context; SQL thực tế có thể chạy khi flush. Ngay cả khi INSERT/UPDATE đã chạy, transaction vẫn có thể rollback sau đó.

Spring application event mặc định được xử lý đồng bộ trong thread phát event. Vì thế, listener chạy ngay sau khi event được publish có thể vẫn đang ở trong transaction của publisher. Nếu listener gửi email hoặc gọi API ngoài trước khi transaction commit, hệ thống bên ngoài có thể nhận thông báo về một thay đổi cuối cùng bị rollback.

Khi chỉ cần chạy side effect sau commit, dùng @TransactionalEventListener với phase AFTER_COMMIT. Với yêu cầu phát message đáng tin cậy qua ranh giới database và broker, cân nhắc transactional outbox hoặc giải pháp tích hợp transaction tương đương; không coi callback/event đồng bộ là cơ chế bảo đảm delivery.

## 6. Chọn cơ chế cho từng công việc

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Chuẩn hóa dữ liệu chỉ áp dụng cho request Spring Data REST | @HandleBeforeCreate hoặc @HandleBeforeSave | Logic gắn với luồng REST exporter |
| Kiểm tra payload trước khi REST exporter lưu entity | REST event handler hoặc Validator integration | Chạy tại biên REST, có thể trả lỗi cho request |
| Phát OrderPaid khi aggregate chuyển sang trạng thái PAID | @DomainEvents hoặc AbstractAggregateRoot | Sự kiện phản ánh hành vi nghiệp vụ, không phụ thuộc HTTP |
| Cập nhật read model khi aggregate phát sự kiện | Listener nhận domain event | Phản ứng với sự kiện nghiệp vụ từ các luồng repository phù hợp |
| Gửi thông báo sau khi transaction thành công | @TransactionalEventListener(AFTER_COMMIT) | Tránh gửi side effect cho transaction rollback |
| Gán createdAt/updatedAt theo lifecycle persistence | @PrePersist, @PreUpdate | Logic đơn giản gắn với trạng thái entity |
| Tính giá trị tạm sau khi entity được load | @PostLoad, nếu phù hợp mô hình | Callback được gọi sau khi entity được nạp |
| Ghi audit cho mọi thay đổi SQL, kể cả bulk SQL | Database audit/CDC hoặc giải pháp chuyên biệt | Entity callback không bao phủ bulk statement và SQL ngoài entity lifecycle |
| Xử lý mọi lần entity được lưu, bất kể REST hay service | Service/domain layer, repository domain event hoặc JPA callback tùy mục đích | REST event không bao phủ các entry point khác |

Không có một cơ chế duy nhất thay thế được hai cơ chế còn lại. Chọn theo nguồn phát mà nghiệp vụ thực sự quan tâm.

## 7. Một luồng có thể đi qua cả ba cơ chế

Giả sử client gửi POST tạo đơn hàng qua Spring Data REST:

~~~http
POST /orders
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": 42,
  "status": "NEW"
}
~~~

Trong luồng này:

1. REST exporter xử lý request và phát BeforeCreateEvent; handler có @HandleBeforeCreate có thể chạy.
2. REST exporter gọi repository để lưu aggregate.
3. Spring Data repository infrastructure có thể đọc và publish domain event đã đăng ký trên aggregate root.
4. JPA persistence provider gọi callback tương ứng khi persist/remove/update/load; thao tác SQL có thể diễn ra ngay hoặc khi flush.
5. REST exporter phát AfterCreateEvent sau bước save của nó.
6. Transaction có thể commit hoặc rollback ở ranh giới transaction do ứng dụng quản lý.

Các bước trên cho thấy phạm vi của từng cơ chế, không phải cam kết về thứ tự tuyệt đối giữa mọi callback và event. SQL có thể được trì hoãn tới flush; transaction boundary có thể do service hoặc cấu hình ứng dụng quyết định; listener cũng có thể được cấu hình chạy bất đồng bộ.

Nếu service gọi repository.save(order) thay vì REST request, phần REST exporter không chạy. Domain event và JPA callback vẫn có thể chạy theo cấu hình tương ứng.

## 8. Kiểm thử ba cơ chế

Nên kiểm thử từng cơ chế ở đúng tầng của nó.

**REST event**

- Dùng integration test gọi endpoint REST.
- Xác nhận handler trước create/save được gọi.
- Xác nhận dữ liệu được chuẩn hóa hoặc request bị từ chối như mong muốn.
- Gọi repository trực tiếp trong test riêng để xác nhận REST handler không bị kích hoạt ngoài REST exporter.

**Repository domain event**

- Tạo aggregate root, gọi method nghiệp vụ và đăng ký event.
- Gọi repository.save(aggregate).
- Dùng listener test hoặc ApplicationEventPublisher test hook để xác nhận event được phát đúng loại.
- Xác nhận @AfterDomainEventPublication dọn danh sách event để lần save sau không phát lặp.
- Kiểm tra riêng deleteById vì không nên giả định method này phát domain event.

**JPA callback**

- Dùng integration test với persistence provider thật hoặc test slice phù hợp.
- Gọi persist, sửa entity rồi flush, remove và load để kích hoạt các callback tương ứng.
- Dùng flush khi cần xác định thời điểm SQL và callback update/insert trong test.
- Kiểm tra callback không dựa vào việc một repository hoặc REST handler cụ thể đã được gọi.

**Transaction và side effect**

- Tạo test transaction commit và rollback.
- Xác nhận listener AFTER_COMMIT chỉ chạy sau commit.
- Xác nhận listener không chạy khi transaction rollback.
- Nếu listener gọi broker hoặc dịch vụ ngoài, kiểm tra khả năng retry/idempotency theo thiết kế tích hợp.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @RepositoryEventHandler không chạy khi service gọi repository.save | REST exporter không tham gia luồng này | Chuyển logic dùng chung sang service/domain event; giữ REST handler cho xử lý riêng ở REST boundary |
| REST event chạy nhưng domain event không chạy | Aggregate chưa đăng ký event hoặc method repository không thuộc nhóm hỗ trợ | Kiểm tra @DomainEvents, registerEvent/andEvent và repository method |
| Domain event bị phát lặp | Danh sách event không được dọn sau publish hoặc aggregate giữ lại event cũ | Dùng @AfterDomainEventPublication hoặc AbstractAggregateRoot đúng cách |
| deleteById không phát domain event | Repository có thể xóa bằng query mà không nạp aggregate instance | Nạp aggregate rồi gọi delete(entity) nếu cần domain event |
| @PostUpdate không chạy ngay sau save | SQL update được trì hoãn đến flush hoặc entity không thực sự dirty | Kiểm tra dirty checking và flush trong test |
| @PreUpdate không chạy với bulk update | Bulk statement không đi qua lifecycle từng managed entity | Phát event ở tầng command hoặc dùng audit ở database |
| Email đã gửi nhưng transaction rollback | Listener chạy đồng bộ trước commit | Dùng @TransactionalEventListener(AFTER_COMMIT) hoặc transactional outbox |
| Callback JPA gọi query gây lỗi hoặc side effect khó đoán | Callback làm quá nhiều việc ngoài lifecycle entity | Giữ callback ngắn, chỉ thay đổi trạng thái đơn giản của entity |
| REST AfterSaveEvent được coi là dữ liệu đã commit | Nhầm sau bước repository save với sau transaction commit | Dùng transaction-bound listener nếu nghiệp vụ cần mốc commit |

## 10. Checklist nhanh

- [ ] Đã xác định event phát từ REST exporter, Spring Data repository hay JPA provider.
- [ ] Không đặt business rule cốt lõi duy nhất trong REST event handler nếu service/batch cũng cần dùng.
- [ ] Aggregate root đăng ký domain event đúng thời điểm trong hành vi nghiệp vụ.
- [ ] Method @DomainEvents không nhận tham số và trả event hoặc collection event.
- [ ] Đã dọn event sau khi publish bằng @AfterDomainEventPublication hoặc AbstractAggregateRoot.
- [ ] Không dựa vào deleteById để phát domain event.
- [ ] JPA callback có chữ ký và annotation phù hợp.
- [ ] Không gọi EntityManager/query hoặc sửa relationship phức tạp trong JPA callback.
- [ ] Không kỳ vọng callback chạy cho bulk JPQL/native SQL.
- [ ] Side effect cần transaction commit được gắn với AFTER_COMMIT hoặc outbox.
- [ ] Đã kiểm thử riêng REST request, repository call, persistence flush và transaction rollback.

## 11. Ghi nhớ

Ba cơ chế giải quyết ba lớp vấn đề:

1. **Spring Data REST event**: hook vào request/resource do REST exporter xử lý.
2. **Spring Data repository domain event**: aggregate root thông báo một sự kiện nghiệp vụ khi repository xử lý aggregate.
3. **JPA lifecycle callback**: persistence provider thông báo entity đang persist, update, remove hoặc load.

Chọn REST event cho logic thuộc HTTP boundary, domain event cho sự kiện nghiệp vụ, và JPA callback cho thao tác nhỏ gắn với vòng đời entity. Nếu công việc chỉ được thực hiện khi transaction commit thành công, hãy dùng transaction-bound listener hoặc outbox theo yêu cầu độ tin cậy.

## Tài liệu tham khảo

- Spring Data REST Reference — Events: https://docs.spring.io/spring-data/rest/reference/events.html
- Spring Data REST API — Repository event package: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/package-summary.html
- Spring Data Commons Reference — Publishing Events from Aggregate Roots: https://docs.spring.io/spring-data/jpa/reference/data-commons/repositories/core-domain-events.html
- Spring Data Commons API — DomainEvents: https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/DomainEvents.html
- Spring Data Commons API — AfterDomainEventPublication: https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/AfterDomainEventPublication.html
- Spring Data Commons API — AbstractAggregateRoot: https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/AbstractAggregateRoot.html
- Jakarta Persistence Specification 3.2 — Entity Listeners and Callback Methods: https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.pdf
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
