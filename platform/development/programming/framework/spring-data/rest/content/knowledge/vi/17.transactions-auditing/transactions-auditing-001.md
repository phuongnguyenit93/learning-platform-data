# Ranh giới transaction của repository và luồng gọi REST exporter

## Mục tiêu

Sau bài này, bạn có thể:

- Hiểu Spring Data REST ánh xạ HTTP request thành lời gọi repository như thế nào.
- Xác định transaction được mở ở repository method hay service method.
- Phân biệt transaction của một repository call với transaction của toàn bộ use case.
- Cấu hình transaction cho CRUD method và query method.
- Dùng service có @Transactional để phối hợp nhiều repository trong một đơn vị công việc.
- Hiểu vị trí của repository events, auditing và transaction-bound events.
- Kiểm tra commit, rollback và dữ liệu audit trong luồng REST.

## 1. REST exporter và repository có vai trò gì?

Spring Data REST xuất bản repository thành HTTP resource. Khi client gọi endpoint, REST exporter chuyển request thành thao tác repository phù hợp. Ví dụ với repository quản lý Order:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Các thao tác thường được ánh xạ như sau:

| HTTP request | Repository operation thường được gọi |
|---|---|
| GET /api/orders | findAll(Pageable), findAll(Sort) hoặc findAll() |
| GET /api/orders/42 | findById(42) |
| POST /api/orders | save(order mới) |
| PUT /api/orders/42 | save(order đã bind từ request) |
| PATCH /api/orders/42 | save(order sau khi áp dụng thay đổi) |
| DELETE /api/orders/42 | delete(...) tương ứng |

REST exporter còn phát các repository lifecycle event như BeforeCreate, AfterCreate, BeforeSave, AfterSave, BeforeDelete và AfterDelete. Những event này cho phép ứng dụng kiểm tra entity, bổ sung dữ liệu hoặc phản ứng với thao tác được thực hiện qua REST API.

Điểm quan trọng: REST exporter là lớp điều phối HTTP và representation. Transaction của dữ liệu được quyết định bởi transaction manager cùng các lời gọi repository/service thực tế. Không nên mặc định mỗi HTTP request tự động trở thành một transaction bao trùm mọi bước của exporter, event handler và các repository khác.

## 2. Transaction mặc định của Spring Data JPA repository

Các CRUD method kế thừa từ CrudRepository thường nhận cấu hình transaction từ SimpleJpaRepository:

- Các thao tác đọc được cấu hình với **readOnly = true**.
- Các thao tác ghi được cấu hình với **@Transactional** thông thường.
- Các repository fragment có transaction attribute riêng sẽ dùng cấu hình của method fragment tương ứng.

Ví dụ:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Các method kế thừa như findById, findAll, save và delete đã có transaction attribute theo implementation của Spring Data JPA. Khi REST exporter gọi repository proxy, transaction interceptor áp dụng cấu hình của method được gọi.

**readOnly = true** là một hint cho transaction manager, JDBC driver và persistence provider để tối ưu thao tác đọc. Nó không phải cơ chế phân quyền và cũng không phải một kiểm tra tuyệt đối ngăn mọi câu lệnh ghi.

Nếu cần thay đổi cấu hình của một CRUD method, có thể khai báo lại method trong repository:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Override
    @Transactional(timeout = 10)
    List<Order> findAll();
}
~~~

Method findAll trong ví dụ được cấu hình timeout 10 giây và không còn readOnly=true theo khai báo mới.

## 3. Query method không mặc định có transaction

Một điểm dễ bỏ sót là query method do ứng dụng khai báo không tự nhận transaction attribute chỉ vì repository kế thừa JpaRepository.

Ví dụ:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);
}
~~~

Nếu query method cần chạy trong transaction, hãy khai báo rõ:

~~~java
@Transactional(readOnly = true)
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    @Modifying
    @Transactional
    @Query("delete from Order o where o.status = :status")
    int deleteByStatus(@Param("status") OrderStatus status);
}
~~~

Trong ví dụ:

- Các query method đọc dữ liệu tham gia transaction read-only.
- Method xóa được đánh dấu @Modifying và có @Transactional ghi dữ liệu.
- Cấu hình cụ thể của method có thể ghi đè cấu hình ở cấp interface.

Hãy kiểm tra loại method và transaction attribute thực tế. Đừng suy luận rằng mọi method có trong repository đều tự động chạy trong một transaction giống nhau.

## 4. Một repository call khác với một use case

Giả sử khi tạo đơn hàng, hệ thống cần:

1. Lưu Order.
2. Giảm tồn kho trong Inventory.
3. Ghi một bản ghi audit.
4. Lưu lịch sử thanh toán.

Nếu REST exporter chỉ gọi OrderRepository.save(), transaction mặc định của method save không tự động bao trùm các thao tác ở ba repository còn lại. Nếu mỗi repository call tự mở transaction riêng, một bước có thể commit trong khi bước khác thất bại.

Ví dụ rủi ro:

~~~java
orderRepository.save(order);
inventoryRepository.reserve(order.getProductId(), order.getQuantity());
auditRepository.save(auditEntry);
~~~

Nếu bước reserve thất bại sau khi Order đã commit, database có thể ở trạng thái không nhất quán.

Đối với một use case cần tính nguyên tử, hãy đặt transaction ở service/facade điều phối toàn bộ các thao tác:

~~~java
@Service
public class OrderWorkflowService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;
    private final AuditRepository auditRepository;

    public OrderWorkflowService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Order createOrder(Order order) {
        Order saved = orderRepository.save(order);

        inventoryRepository.reserve(
            saved.getProductId(),
            saved.getQuantity()
        );

        auditRepository.save(
            AuditEntry.orderCreated(saved.getId())
        );

        return saved;
    }
}
~~~

Transaction của createOrder bao trùm các repository call bên trong nếu chúng tham gia cùng transaction manager và propagation mặc định. Nếu một thao tác ném exception làm transaction rollback, các thay đổi database trong cùng transaction được rollback cùng nhau.

## 5. REST exporter không tự gọi service orchestration

Repository resource mặc định của Spring Data REST gọi repository method đã được công bố. Việc tạo một service có @Transactional không tự động khiến POST /api/orders đi qua service đó.

Nếu use case tạo đơn hàng cần nhiều bước, có thể cung cấp một custom endpoint bằng @RepositoryRestController hoặc controller phù hợp để gọi service:

~~~java
@RepositoryRestController
public class OrderWorkflowController {

    private final OrderWorkflowService workflowService;

    public OrderWorkflowController(OrderWorkflowService workflowService) {
        this.workflowService = workflowService;
    }

    @PostMapping(
        path = "/orders/checkout",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_HAL_JSON_VALUE
    )
    public ResponseEntity<?> checkout(@RequestBody Order order) {
        Order saved = workflowService.createOrder(order);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }
}
~~~

Đây là ví dụ cấu trúc; response thực tế nên dùng representation/assembler phù hợp với API của ứng dụng. @RepositoryRestController giúp controller sử dụng base path và hạ tầng Spring Data REST. Phần quyết định transaction vẫn nằm trong service được gọi.

Một lựa chọn khác là giữ endpoint repository đơn giản cho CRUD và xây dựng endpoint nghiệp vụ riêng cho các thao tác cần phối hợp nhiều aggregate/repository. Hãy đặt transaction tại ranh giới của use case mà ứng dụng cần bảo đảm nguyên tử.

## 6. Propagation: repository call tham gia transaction hiện có

Propagation mặc định của @Transactional là **REQUIRED**:

- Nếu đã có transaction, method tham gia transaction hiện có.
- Nếu chưa có transaction, method tạo một transaction mới.

Ví dụ:

~~~java
@Service
public class OrderWorkflowService {

    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;

    public OrderWorkflowService(
            OrderRepository orderRepository,
            PaymentRepository paymentRepository) {
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
    }

    @Transactional
    public void confirmOrder(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        paymentRepository.markReady(orderId);
    }
}
~~~

Các repository method được gọi từ confirmOrder sẽ tham gia transaction của service nếu dùng cùng transaction manager và propagation tương thích.

Đây là cách xác định một đơn vị công việc rõ ràng. Transaction attribute ở service bên ngoài quyết định transaction thực tế mà các repository call bên trong tham gia.

## 7. Rollback và exception

Một transaction chỉ bảo đảm rollback theo quy tắc của transaction manager. Với cấu hình Spring mặc định, RuntimeException và Error làm transaction rollback. Checked exception không mặc định làm rollback.

Ví dụ nếu nghiệp vụ có thể ném checked exception và cần rollback:

~~~java
@Transactional(rollbackFor = Exception.class)
public void createOrder(Order order) throws Exception {
    orderRepository.save(order);
    inventoryRepository.reserve(order.getProductId(), order.getQuantity());

    if (someBusinessConditionFailed()) {
        throw new Exception("Không thể hoàn tất đơn hàng");
    }
}
~~~

Nếu exception bị bắt và không được ném tiếp ra ngoài, transaction interceptor có thể không nhận biết rằng use case thất bại. Khi cần rollback dù đã xử lý exception, hãy chủ động đánh dấu transaction rollback-only hoặc ném exception phù hợp.

Không nên bắt mọi exception rồi trả về kết quả thành công. Điều đó có thể khiến transaction commit một phần thay đổi mà nghiệp vụ không mong muốn.

## 8. Repository events không phải transaction boundary

Spring Data REST phát các event như:

- BeforeCreate / AfterCreate.
- BeforeSave / AfterSave.
- BeforeLinkSave / AfterLinkSave.
- BeforeDelete / AfterDelete.

Có thể xử lý bằng ApplicationListener/AbstractRepositoryEventListener hoặc handler có @RepositoryEventHandler và các annotation như @HandleBeforeSave.

Ví dụ:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderEventHandler {

    @HandleBeforeSave
    public void beforeSave(Order order) {
        order.normalizeReference();
    }

    @HandleAfterSave
    public void afterSave(Order order) {
        // Phản ứng với lifecycle event của REST exporter.
    }
}
~~~

Các event này mô tả vòng đời thao tác của REST exporter. Chúng không tự tạo một transaction mới, không thay thế @Transactional và cũng không đồng nghĩa với transaction đã commit.

Spring Data REST events là Spring application events và mặc định được phát đồng bộ. Synchronous chỉ có nghĩa listener thường được gọi trên luồng phát event; điều đó không tự chứng minh rằng một database transaction đang hoạt động tại thời điểm listener chạy.

Vì vậy:

- Dùng BeforeSave để kiểm tra hoặc chuẩn hóa entity trước thao tác lưu của exporter.
- Dùng AfterSave để phản ứng với event lưu theo vòng đời REST exporter.
- Không giả định event handler luôn nằm trong cùng transaction với mọi repository call.
- Nếu handler cần nhiều repository call phải nguyên tử, hãy chuyển orchestration vào service có @Transactional.
- Nếu cần phản ứng chỉ sau khi commit thành công, hãy dùng cơ chế transaction-bound event với một event được phát trong transaction đang hoạt động.

## 9. Dùng @TransactionalEventListener khi cần biết kết quả commit

Spring Framework hỗ trợ @TransactionalEventListener để gắn listener với một phase của transaction:

| Phase | Thời điểm |
|---|---|
| BEFORE_COMMIT | Trước khi transaction commit |
| AFTER_COMMIT | Sau khi commit thành công; đây là mặc định |
| AFTER_ROLLBACK | Sau khi rollback |
| AFTER_COMPLETION | Sau khi transaction hoàn tất, dù commit hay rollback |

Ví dụ:

~~~java
public record OrderCreatedEvent(Long orderId) {
}
~~~

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher events;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher events) {
        this.orderRepository = orderRepository;
        this.events = events;
    }

    @Transactional
    public Order create(Order order) {
        Order saved = orderRepository.save(order);
        events.publishEvent(new OrderCreatedEvent(saved.getId()));
        return saved;
    }
}
~~~

Listener chỉ xử lý sau commit:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        // Gửi thông báo sau khi transaction tạo Order commit thành công.
    }
}
~~~

Trong ví dụ, event được phát bên trong transaction của service. Listener AFTER_COMMIT chỉ chạy sau khi transaction đó commit thành công. Nếu transaction rollback, listener không chạy.

Nếu không có transaction đang hoạt động tại thời điểm event được phát, @TransactionalEventListener mặc định không được gọi. Thuộc tính fallbackExecution có thể thay đổi hành vi này, nhưng không nên bật nó nếu nghiệp vụ bắt buộc phải biết chắc transaction đã commit.

Không nên coi một Spring Data REST AfterSaveEvent là bằng chứng transaction đã commit. Nếu cần ngữ nghĩa commit rõ ràng, hãy phát domain event từ service bên trong transaction và kiểm tra đúng transaction manager.

## 10. Ghi audit cùng transaction hay sau commit?

Có hai loại auditing thường gặp:

**Auditing metadata trên entity** ghi lại ai tạo/sửa và thời điểm tạo/sửa. Spring Data hỗ trợ:

- @CreatedBy
- @LastModifiedBy
- @CreatedDate
- @LastModifiedDate

Ví dụ entity:

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    private String orderNumber;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
~~~

Bật auditing:

~~~java
@Configuration
@EnableJpaAuditing
public class JpaAuditConfiguration {
}
~~~

Nếu cần ghi tên người dùng qua @CreatedBy hoặc @LastModifiedBy, cung cấp AuditorAware để lấy principal hiện tại. Nếu chỉ ghi ngày giờ, không bắt buộc phải có AuditorAware.

**Audit log riêng** là bản ghi lịch sử nghiệp vụ, ví dụ ai thay đổi trạng thái đơn hàng, giá trị cũ và mới là gì. Nếu audit row phải tồn tại đúng khi Order commit, hãy ghi audit row trong cùng transaction service. Khi đó hai thay đổi cùng commit hoặc cùng rollback nếu cùng database và transaction manager.

Nếu chỉ cần gửi email, gọi webhook hoặc publish message sau commit, hãy thực hiện sau khi transaction thành công. Với tích hợp ngoài cần độ tin cậy cao, cân nhắc transactional outbox: ghi event/outbox row cùng transaction nghiệp vụ rồi một worker gửi ra hệ thống ngoài. Cách này tránh trường hợp database commit nhưng ứng dụng chết trước khi gửi message.

Nếu listener AFTER_COMMIT cần ghi thêm vào database, hãy thiết kế transaction riêng cho thao tác đó, thường qua service có propagation REQUIRES_NEW. Transaction gốc đã hoàn tất; không dựa vào listener để âm thầm tiếp tục ghi trong transaction đã commit.

## 11. Một transaction có thể bao phủ những gì?

| Thành phần | Có tự động nằm trong transaction của repository save? |
|---|---|
| Câu lệnh persistence bên trong save | Có, theo transaction attribute của repository method |
| Repository call khác từ service @Transactional cùng transaction manager | Có thể tham gia transaction hiện có |
| Repository call độc lập từ event handler không có outer transaction | Thường có transaction riêng theo method được gọi |
| Gửi email hoặc HTTP request ra hệ thống ngoài | Không được database transaction rollback tự động |
| Ghi database khác dùng transaction manager khác | Không tự động atomic với transaction hiện tại |
| Event listener chạy bất đồng bộ trên thread khác | Không kế thừa thread-bound transaction mặc định |

Transaction thông thường chỉ bảo vệ tài nguyên mà transaction manager quản lý. Một database transaction không thể tự rollback email đã gửi hoặc HTTP request đã được hệ thống khác xử lý.

Nếu một use case cập nhật nhiều database hoặc nhiều hệ thống ngoài, cần chọn kiến trúc phù hợp như outbox, saga hoặc distributed transaction khi hạ tầng thực sự hỗ trợ. Không nên gắn @Transactional rồi giả định mọi hệ thống liên quan đều trở thành một giao dịch nguyên tử.

## 12. Kiểm tra transaction trong luồng REST

Khi kiểm tra một endpoint Spring Data REST, hãy xác định:

1. HTTP method đang gọi repository method nào?
2. Method đó kế thừa CRUD transaction attribute hay là query method tự khai báo?
3. Có service/facade bên ngoài với @Transactional hay không?
4. Các repository dùng chung transaction manager và propagation phù hợp không?
5. Event handler có được gọi đồng bộ hay chuyển sang thread khác?
6. Audit row được ghi trước commit, sau commit hay qua outbox?
7. Exception nào khiến transaction rollback?

Có thể bật log transaction ở môi trường phát triển để theo dõi begin, commit, rollback và transaction participation. Với Spring Boot, có thể cấu hình log level cho transaction interceptor và transaction manager theo phiên bản Spring đang dùng.

Ví dụ log configuration minh họa:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.orm.jpa.JpaTransactionManager=DEBUG
~~~

Tên logger và mức log có thể khác theo phiên bản Spring, transaction manager và persistence technology. Kết hợp log ứng dụng với SQL log và kiểm tra dữ liệu trong database để xác nhận kết quả cuối cùng.

## 13. Những lỗi thường gặp

### Nghĩ mỗi HTTP request luôn là một transaction

REST exporter gọi repository method, nhưng không nên giả định mọi bước của request và mọi event handler đều nằm trong một transaction bao trùm. Xác định transaction boundary thực tế từ service/repository proxy.

### Query method chạy mà không có transaction

Method finder tự khai báo không mặc định có transaction attribute. Dùng @Transactional ở repository hoặc service phù hợp.

### Nhiều repository call commit riêng lẻ

Nếu nghiệp vụ yêu cầu tất cả thay đổi cùng thành công hoặc cùng thất bại, đặt transaction tại service điều phối thay vì dựa vào transaction riêng của từng repository method.

### AfterSave bị hiểu là AFTER_COMMIT

AfterSave là event vòng đời của REST exporter. Nó không phải transaction phase. Dùng @TransactionalEventListener với domain event được phát bên trong transaction nếu cần xử lý sau commit.

### Audit log bị lệch với dữ liệu nghiệp vụ

Nếu audit row phải atomic với entity, ghi nó trong cùng transaction. Nếu gửi message ra ngoài, dùng after-commit hoặc outbox phù hợp với mức độ tin cậy cần thiết.

### Bắt exception khiến transaction vẫn commit

Nếu exception bị nuốt và không đánh dấu rollback-only, transaction có thể commit. Kiểm tra rollback rule và cách xử lý exception.

### Dùng nhiều transaction manager nhưng mong atomic

@Transaction chỉ điều khiển transaction manager được chọn. Hai database hoặc hai hệ thống ngoài không tự động trở thành một transaction chung.

### Gọi method transactional qua self-invocation

Trong cấu hình proxy-based thông thường, một method trong cùng class gọi trực tiếp method @Transactional khác có thể bỏ qua proxy. Đặt ranh giới transaction ở public service method được gọi qua Spring bean proxy hoặc dùng cấu hình phù hợp.

## 14. Ghi nhớ

- Spring Data REST chuyển HTTP request thành lời gọi repository method; transaction được quyết định bởi repository/service và transaction manager.
- CRUD method kế thừa từ SimpleJpaRepository có transaction attribute mặc định; thao tác đọc thường read-only và thao tác ghi có @Transactional.
- Query method tự khai báo không mặc định có transaction.
- Một repository call không đồng nghĩa một use case nhiều repository đã được bao trong cùng transaction.
- Dùng service/facade có @Transactional để phối hợp nhiều repository trong một đơn vị công việc.
- Repository events mô tả vòng đời REST exporter; chúng không thay thế transaction boundary hoặc commit phase.
- Dùng @TransactionalEventListener khi event được phát trong transaction đang hoạt động và listener cần phản ứng theo commit/rollback.
- Ghi audit metadata bằng Spring Data Auditing; ghi audit log nghiệp vụ cùng transaction nếu cần atomic.
- External side effect cần after-commit, outbox hoặc kiến trúc tích hợp phù hợp.
- Kiểm tra rollback rule, propagation, transaction manager và thread boundary khi debug.

## Tài liệu tham khảo

- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
