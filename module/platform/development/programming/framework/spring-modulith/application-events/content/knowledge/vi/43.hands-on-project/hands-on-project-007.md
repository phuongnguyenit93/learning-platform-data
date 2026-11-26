# Lưu publication

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi publisher phát event trong một transaction, hệ thống cần ghi nhận listener nào phải xử lý event và listener đã hoàn tất hay chưa. **Lưu publication** là bài thực hành xây dựng một modular monolith có Event Publication Registry được lưu bền vững trong database, để ứng dụng phát hiện publication chưa hoàn tất và tiếp tục xử lý sau lỗi hoặc restart.

Kết quả của dự án là một luồng đặt hàng có thể kiểm tra được: module Order lưu đơn hàng và phát OrderPlaced trong cùng transaction; module Inventory nhận event sau commit; publication được lưu trong registry; khi listener thất bại, publication vẫn incomplete để phục hồi. Bài thực hành dùng JPA làm persistence provider minh họa. Artifact, schema và API cần được đồng bộ với phiên bản Spring Boot/Spring Modulith của ứng dụng.

## 1. Mục tiêu dự án

Sau khi hoàn thành, bạn có thể:

- Phân biệt event được publish với publication được listener xử lý hoàn tất.
- Cấu hình Event Publication Registry dùng persistence bền vững.
- Phát event trong transaction nghiệp vụ.
- Xử lý event sau commit bằng listener thuộc module nhận.
- Quan sát publication incomplete và completed.
- Tái hiện listener failure, restart ứng dụng và resubmit publication.
- Bảo đảm handler idempotent để chịu redelivery.
- Kiểm thử commit, rollback, persistence và recovery bằng database thật.

Phạm vi tập trung vào publication đến transactional listener trong Spring Modulith. Registry không thay thế Kafka offset, broker retry topic, outbox, inbox hoặc event store. Nếu ứng dụng phát event ra hệ thống bên ngoài, cần thiết kế thêm cơ chế giao nhận tương ứng.

## 2. Bài toán thực tế

Một khách hàng đặt hàng. Module Order lưu đơn hàng ở trạng thái PLACED và phát OrderPlaced. Module Inventory nhận event để giữ hàng. Nếu Inventory database tạm thời lỗi, listener thất bại sau khi transaction đặt hàng đã commit.

Nếu chỉ dùng event listener trong bộ nhớ, process dừng có thể làm mất cơ hội xử lý tiếp. Khi có Event Publication Registry bền vững, ứng dụng lưu một publication cho listener Inventory. Khi listener xử lý thành công, registry đánh dấu publication completed. Nếu listener lỗi, publication vẫn incomplete và có thể được resubmit theo chính sách recovery.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant O as Order module
    participant DB as Application database
    participant R as Event Publication Registry
    participant I as Inventory listener
    API->>O: placeOrder()
    O->>DB: Save Order
    O->>R: Register publication
    O->>DB: Commit transaction
    DB-->>I: Deliver OrderPlaced after commit
    I->>DB: Reserve inventory in listener transaction
    I->>R: Mark publication completed
~~~

Publication được đăng ký trong cùng transaction với thao tác phát event và dữ liệu nghiệp vụ. Nếu transaction đặt hàng rollback, dữ liệu đơn hàng và publication record thuộc transaction đó cũng rollback. Sau commit, listener xử lý độc lập; lỗi ở listener không làm transaction đặt hàng đã commit quay ngược.

## 3. Thiết kế module và dữ liệu

Tổ chức ví dụ thành hai module:

| Module | Trách nhiệm | Dữ liệu sở hữu |
| --- | --- | --- |
| Order | Nhận yêu cầu đặt hàng, lưu đơn và phát OrderPlaced. | Order và OrderLine. |
| Inventory | Nhận OrderPlaced, kiểm tra và giữ hàng. | InventoryItem và Reservation. |

Order không gọi trực tiếp InventoryService. Order chỉ công bố event contract. Inventory đăng ký listener cho event đó và quản lý dữ liệu của mình.

~~~text
com.example.shop
  order
    Order.java
    OrderRepository.java
    OrderService.java
    OrderPlaced.java
  inventory
    InventoryItem.java
    InventoryRepository.java
    Reservation.java
    ReservationRepository.java
    InventoryEventListener.java
    InventoryReservationService.java
  ShopApplication.java
~~~

Các lớp persistence nội bộ không nên được module khác truy cập trực tiếp. Event contract nên chứa định danh và dữ liệu cần thiết để module nhận xử lý, không mang theo JPA entity hoặc persistence context của module phát.

## 4. Chuẩn bị dependency

Dùng Spring Boot và Spring Modulith tương thích với nhau. Quản lý phiên bản Spring Modulith bằng BOM để các module cùng phiên bản:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>SPRING_MODULITH_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Các dependency chính trong ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Artifact starter và phiên bản cụ thể cần đối chiếu với dòng Spring Boot của dự án. Nếu dự án dùng persistence provider khác, chọn integration tương ứng được Spring Modulith hỗ trợ. Không thêm JPA starter nếu ứng dụng không dùng JPA.

## 5. Cấu hình database

Trong local development, có thể cấu hình PostgreSQL như sau:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: SHOP_DB_PASSWORD_VALUE
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
  modulith:
    events:
      republish-outstanding-events-on-restart: true
~~~

Property republish outstanding events bật cơ chế Spring Modulith xem xét và phát lại publication chưa hoàn tất khi ứng dụng khởi động, theo khả năng và cấu hình của phiên bản đang dùng. Kiểm tra property reference của đúng phiên bản trước khi đưa vào production. Không dựa vào restart như cơ chế retry duy nhất; vẫn cần quan sát, kiểm soát recovery và xử lý poison event.

Với production, quản lý schema bằng Flyway hoặc Liquibase. Không dùng Hibernate create/update để âm thầm thay đổi schema registry trong production. Persistence provider cần có bảng và index phục vụ publication; dùng migration/schema script được cung cấp cho đúng phiên bản Spring Modulith. Không tự đoán cấu trúc bảng hoặc sửa trực tiếp bảng nội bộ.

## 6. Tạo event contract

Event chỉ chứa dữ liệu cần cho Inventory xử lý. Dùng immutable record:

~~~java
public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

eventId giúp nhận diện một lần phát event và giữ nguyên qua retry/resubmit. orderId cho phép Inventory tải dữ liệu cần thiết qua public contract hoặc repository thuộc module Inventory. occurredAt ghi thời điểm nghiệp vụ phát sinh.

Không truyền Order JPA entity vào event. Entity có thể chứa lazy association, proxy, dữ liệu nhạy cảm hoặc cấu trúc thay đổi theo persistence model. Event contract cần ổn định và có thể serialize/deserialize qua thời gian.

## 7. Tạo entity và repository của Order

~~~java
@Entity
@Table(name = "orders")
class Order {

    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected Order() {}

    Order(UUID id) {
        this.id = id;
        this.status = OrderStatus.DRAFT;
    }

    void place() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is not draft");
        }
        status = OrderStatus.PLACED;
    }

    UUID getId() {
        return id;
    }
}
~~~

~~~java
interface OrderRepository extends JpaRepository<Order, UUID> {}
~~~

Trong dự án thật, entity cần các field giá trị, kiểm tra invariant và mapping phù hợp. Bài thực hành giữ phần domain gọn để tập trung vào publication.

## 8. Phát event trong transaction nghiệp vụ

OrderService lưu đơn và phát event trong cùng transaction:

~~~java
@Service
@RequiredArgsConstructor
class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    @Transactional
    public UUID placeOrder(UUID orderId) {
        Order order = new Order(orderId);
        order.place();
        orders.save(order);

        events.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            order.getId(),
            clock.instant()
        ));

        return order.getId();
    }
}
~~~

Event được công bố trong transaction đang hoạt động. Spring Modulith đăng ký publication cho transactional listener tương ứng. Khi transaction commit, listener được kích hoạt theo phase đã cấu hình. Nếu transaction rollback, publication record được đăng ký trong transaction đó cũng không tồn tại như một publication đã commit.

Không gọi publish event sau khi transaction đã kết thúc nếu muốn registry liên kết publication với transaction nghiệp vụ. Cũng không tự tạo một bản ghi registry thủ công song song với cơ chế framework.

## 9. Tạo dữ liệu của Inventory

Module Inventory quản lý tồn kho và reservation:

~~~java
@Entity
@Table(
    name = "inventory_item",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_inventory_sku",
        columnNames = "sku"
    )
)
class InventoryItem {

    @Id
    private String sku;

    private int available;

    protected InventoryItem() {}

    int available() {
        return available;
    }

    void reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new IllegalStateException("Insufficient inventory");
        }
        available -= quantity;
    }
}
~~~

~~~java
@Entity
@Table(
    name = "inventory_reservation",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_reservation_order",
        columnNames = "order_id"
    )
)
class Reservation {

    @Id
    private UUID id;

    @Column(name = "order_id", nullable = false)
    private UUID orderId;

    protected Reservation() {}

    Reservation(UUID id, UUID orderId) {
        this.id = id;
        this.orderId = orderId;
    }
}
~~~

Unique constraint trên order_id là một lớp bảo vệ idempotency cho ví dụ một reservation trên mỗi order. Với đơn có nhiều SKU, khóa idempotency cần bao gồm orderId và dòng hàng hoặc một reservation key ổn định.

## 10. Tạo handler idempotent

Listener có thể được giao lại sau lỗi hoặc restart. Vì vậy, xử lý cần an toàn khi cùng event đến nhiều lần. Một service của Inventory thực hiện reservation trong transaction:

~~~java
@Service
@RequiredArgsConstructor
class InventoryReservationService {

    private final InventoryRepository inventory;
    private final ReservationRepository reservations;

    @Transactional
    public void reserveFor(UUID orderId) {
        if (reservations.existsByOrderId(orderId)) {
            return;
        }

        InventoryItem item = inventory.findById("SKU-BOOK")
            .orElseThrow();

        item.reserve(1);
        reservations.save(new Reservation(
            UUID.randomUUID(),
            orderId
        ));
    }
}
~~~

Kiểm tra existsByOrderId giúp xử lý redelivery thông thường. Trong môi trường có thể có hai delivery đồng thời, unique constraint vẫn là lớp bảo vệ cuối; code cần xử lý duplicate key theo cách an toàn và kiểm tra transaction rollback. Một chiến lược inbox với eventId cũng phù hợp nếu một nghiệp vụ có nhiều event khác nhau cùng tác động đến aggregate.

## 11. Đăng ký transactional listener

Sử dụng @ApplicationModuleListener để xử lý sau commit trong một luồng bất đồng bộ và transaction riêng theo semantics của Spring Modulith:

~~~java
@Component
@RequiredArgsConstructor
class InventoryEventListener {

    private final InventoryReservationService reservations;

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        reservations.reserveFor(event.orderId());
    }
}
~~~

@ApplicationModuleListener là shortcut dành cho application module event listener; nó kết hợp xử lý bất đồng bộ và transaction listener sau commit theo cấu hình framework. Nếu dùng @TransactionalEventListener trực tiếp, phải chọn phase phù hợp và tự thiết kế executor/transaction cho nhu cầu của ứng dụng.

Không chia sẻ transaction hoặc EntityManager của publisher sang listener. Listener xử lý độc lập và phải commit/rollback side effect của module nhận theo transaction boundary riêng.

## 12. Registry lưu những gì?

Với transactional listener, registry theo dõi publication cho từng listener target. Một event có nhiều transactional listener có thể có nhiều publication record. Mỗi record thể hiện event, listener đích, thời điểm publication và trạng thái completion.

| Trạng thái | Ý nghĩa |
| --- | --- |
| Incomplete | Publication đã được đăng ký nhưng listener chưa được đánh dấu hoàn tất. |
| Completed | Listener xử lý thành công và registry đã ghi nhận completion. |
| Resubmitted | Publication incomplete được phát lại để listener xử lý lần nữa; sau đó có thể trở thành completed hoặc tiếp tục incomplete. |

Registry lưu trạng thái giao event đến transactional listener. Nó không phải event store để truy vấn lịch sử nghiệp vụ vô hạn, cũng không phải Kafka consumer offset. Retention của completed publication cần được cấu hình theo yêu cầu vận hành và API của phiên bản thư viện.

## 13. Xác minh persistence qua database

Sau khi gọi placeOrder và transaction commit, kiểm tra database có publication record cho listener Inventory. Sau khi listener thành công, record đó phải được đánh dấu completed.

Trong môi trường học tập, có thể xem schema registry được tạo bởi persistence provider để hiểu dữ liệu được lưu. Tên bảng, cột và kiểu serialization phụ thuộc provider/phiên bản. Dùng bảng để quan sát hoặc điều tra; không viết logic nghiệp vụ dựa trên tên bảng nội bộ.

Để chứng minh dữ liệu bền vững:

1. Khởi động ứng dụng với database persistent.
2. Gọi placeOrder và xác nhận transaction commit.
3. Tạm làm listener thất bại để giữ publication incomplete.
4. Dừng process ứng dụng hoặc mô phỏng restart.
5. Khởi động lại với cùng database.
6. Xác minh publication incomplete còn tồn tại và recovery được kích hoạt theo cấu hình.
7. Xác minh listener hoàn tất và publication được đánh dấu completed.

Restart process với database vẫn giữ nguyên là phép thử durability. Nếu dùng database trong bộ nhớ, restart database cùng ứng dụng sẽ xóa trạng thái và không chứng minh persistence.

## 14. Quan sát publication bằng API

EventPublicationRegistry cung cấp API để truy vấn publication chưa hoàn tất và resubmit theo điều kiện. Ví dụ minh họa:

~~~java
@Service
@RequiredArgsConstructor
class PublicationOperations {

    private final EventPublicationRegistry registry;

    public Collection<EventPublication> findIncomplete() {
        return registry.findIncompletePublications();
    }

    public void resubmitOrderPlaced() {
        registry.resubmitIncompletePublications(publication ->
            publication.getEvent() instanceof OrderPlaced
        );
    }
}
~~~

Các kiểu trả về và method có thể thay đổi theo phiên bản Spring Modulith. Đối chiếu API Javadoc của dependency đang dùng trước khi triển khai adapter vận hành. Không expose endpoint resubmit công khai cho người dùng cuối; thao tác recovery cần authorization, audit, giới hạn phạm vi và kiểm tra idempotency.

Trong production, thường nên cung cấp màn hình hoặc command vận hành read-only để xem số lượng incomplete, tuổi publication lâu nhất và listener đích. Thao tác resubmit cần tách quyền và ghi nhận người thực hiện.

## 15. Mô phỏng listener failure

Tạo một dependency có thể điều khiển lỗi trong profile test hoặc môi trường local:

~~~java
@Component
class InventoryFailureSwitch {

    private final AtomicBoolean enabled = new AtomicBoolean(false);

    void enable() {
        enabled.set(true);
    }

    void disable() {
        enabled.set(false);
    }

    void failIfEnabled() {
        if (enabled.get()) {
            throw new IllegalStateException(
                "Simulated inventory outage"
            );
        }
    }
}
~~~

Gọi failIfEnabled trong InventoryReservationService trước khi ghi side effect. Khi switch bật, listener ném exception và transaction listener rollback. Publication chưa được đánh dấu completed.

Chỉ dùng failure switch trong test hoặc profile local được bảo vệ. Không đưa endpoint bật lỗi vào production. Khi chạy test song song, trạng thái switch phải được cô lập theo test context để không làm ảnh hưởng listener khác.

## 16. Kiểm thử thành công

Test tích hợp cần dùng database thật hoặc container database tương thích với môi trường chạy:

~~~java
@SpringBootTest
class PublicationPersistenceIntegrationTest {

    @Autowired
    OrderService orders;

    @Autowired
    EventPublicationRegistry registry;

    @Test
    void completesPublicationAfterListenerSucceeds() {
        UUID orderId = UUID.randomUUID();

        orders.placeOrder(orderId);

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
            assertThat(registry.findIncompletePublications())
                .noneMatch(publication ->
                    publication.getEvent() instanceof OrderPlaced event
                        && event.orderId().equals(orderId)
                )
        );
    }
}
~~~

Đoạn test minh họa điều kiện sau xử lý. Trong dự án thực tế, nên xác minh cả reservation tồn tại và inventory giảm đúng một đơn vị. Chỉ thấy incomplete list rỗng chưa đủ nếu listener không được đăng ký hoặc event chưa tạo publication; cần assert business outcome để chứng minh luồng thực sự chạy.

## 17. Kiểm thử rollback của publisher

Nếu transaction nghiệp vụ rollback, event publication không được tồn tại như một publication đã commit:

~~~java
@Test
void doesNotPersistPublicationWhenOrderTransactionRollsBack() {
    UUID orderId = UUID.randomUUID();

    transactionTemplate.executeWithoutResult(status -> {
        orders.placeOrder(orderId);
        status.setRollbackOnly();
    });

    assertThat(orderRepository.findById(orderId)).isEmpty();
    assertThat(registry.findIncompletePublications())
        .noneMatch(publication ->
            publication.getEvent() instanceof OrderPlaced event
                && event.orderId().equals(orderId)
        );
}
~~~

Đây là skeleton để minh họa ranh giới transaction; cách wiring TransactionTemplate và service cần bảo đảm lời gọi placeOrder tham gia transaction ngoài. Nếu service mở transaction riêng với propagation REQUIRES_NEW, rollback bên ngoài không hủy transaction đó. Nếu dùng transaction mặc định REQUIRED, service tham gia transaction do TransactionTemplate tạo.

Không dùng flush thay cho commit. Flush chỉ đồng bộ SQL trong transaction hiện tại; transactional listener AFTER_COMMIT chỉ được gọi khi transaction thực sự commit.

## 18. Kiểm thử listener thất bại và publication incomplete

Kịch bản:

1. Bật failure switch.
2. Gọi placeOrder và để transaction publisher commit.
3. Chờ listener được gọi và thất bại.
4. Xác minh Order vẫn tồn tại ở trạng thái PLACED.
5. Xác minh Inventory không bị trừ và Reservation không được tạo.
6. Xác minh publication cho Inventory vẫn incomplete.

Publisher transaction đã commit trước khi listener chạy. Vì vậy, lỗi listener không được làm mất đơn hàng hoặc rollback dữ liệu Order. Publication incomplete là tín hiệu cần recovery.

Nếu listener catch exception rồi return bình thường, registry có thể đánh dấu completed. Test này cũng giúp phát hiện handler đang nuốt lỗi và làm mất tín hiệu failure.

## 19. Kiểm thử recovery sau khi dependency phục hồi

Sau khi tắt failure switch, có thể resubmit publication incomplete theo API được hỗ trợ:

~~~java
failureSwitch.disable();

registry.resubmitIncompletePublications(publication ->
    publication.getEvent() instanceof OrderPlaced event
        && event.orderId().equals(orderId)
);
~~~

Test chờ Reservation xuất hiện, Inventory giảm đúng một đơn vị và publication không còn incomplete. Nếu listener đã tạo side effect trước khi process dừng nhưng registry chưa kịp ghi completion, resubmit có thể giao event lần nữa; idempotency phải ngăn tạo reservation thứ hai.

Không resubmit toàn bộ publication incomplete nếu chưa phân loại event và listener. Một publication có thể lỗi do payload không hợp lệ hoặc lỗi code cố định; replay liên tục sẽ tạo vòng lặp thất bại.

## 20. Kiểm thử restart với cùng database

Đây là bài kiểm thử chứng minh mục tiêu lưu publication:

| Giai đoạn | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Trước restart | Publisher commit, listener thất bại. | Publication incomplete được lưu trong database. |
| Dừng process | Dừng ứng dụng, giữ nguyên database volume. | Publication record còn nguyên. |
| Khởi động lại | Dùng cùng datasource và schema. | Registry tải được publication incomplete. |
| Recovery | Cơ chế republish hoặc thao tác resubmit được kích hoạt. | Listener được gọi lại. |
| Hoàn tất | Dependency hoạt động và handler thành công. | Side effect được commit, publication completed. |

Integration test tự động có thể khởi động hai ApplicationContext nối tiếp cùng một database container, hoặc dùng test harness quản lý process riêng. Không dùng một context cache vẫn đang sống để giả lập restart hoàn toàn; context đó có thể giữ listener, executor hoặc connection pool cũ.

## 21. Xử lý nhiều listener

Một event có thể được nhận bởi nhiều transactional listener:

~~~java
@ApplicationModuleListener
void updateInventory(OrderPlaced event) { ... }

@ApplicationModuleListener
void updateSalesProjection(OrderPlaced event) { ... }
~~~

Registry theo dõi publication theo listener target. Nếu Inventory thành công nhưng Sales Projection thất bại, publication của Inventory có thể completed trong khi publication của Sales vẫn incomplete. Không kết luận event đã hoàn tất toàn hệ thống chỉ dựa vào một listener.

Mỗi listener cần idempotency và quan sát riêng. Nếu có thứ tự phụ thuộc nghiệp vụ giữa các bước, hãy mô hình hóa bằng event kết quả hoặc process manager; không dựa vào thứ tự chạy của listener bất đồng bộ.

## 22. Lưu ý về serialization và thay đổi event class

Registry bền vững cần lưu event đủ để có thể phát lại sau khi process restart. Serializer phải có khả năng serialize payload lúc publish và deserialize payload khi recovery.

Các nguyên tắc:

- Event payload nên là DTO immutable với kiểu dữ liệu ổn định.
- Tránh JPA entity, lazy proxy, stream, file handle hoặc object gắn với request.
- Giữ tương thích schema khi event còn publication incomplete.
- Khi đổi package/class hoặc tên field, đánh giá khả năng deserialize record cũ.
- Có version hoặc adapter/upcaster khi cần hỗ trợ nhiều payload version.
- Kiểm thử recovery với event được lưu bởi phiên bản code trước.

Đừng xóa publication cũ chỉ vì class event đã đổi tên. Nếu event cũ không còn deserialize được, cần bridge migration hoặc quy trình xử lý record cũ có kiểm soát.

## 23. Listener identifier và refactor code

Publication record cần xác định listener đích để resubmit. Listener identifier thường được suy ra từ method/target mà framework đăng ký. Refactor package, class hoặc method có thể ảnh hưởng cách phiên bản thư viện nhận diện listener.

Trước khi đổi tên listener trong khi còn publication incomplete:

1. Kiểm tra publication còn tồn tại và listener identifier đang lưu.
2. Xác minh phiên bản mới vẫn có thể nhận diện target cũ hoặc có kế hoạch chuyển tiếp.
3. Xử lý hết publication cũ trước khi contract listener nếu an toàn.
4. Nếu cần, triển khai bridge listener trong giai đoạn chuyển tiếp.
5. Kiểm thử resubmit record được tạo bởi phiên bản trước.

Không coi listener identifier là API nghiệp vụ công khai, nhưng phải quản lý nó như dữ liệu vận hành có thể tồn tại qua nhiều lần deploy.

## 24. Retention và dọn publication completed

Publication completed hữu ích cho điều tra nhưng không nhất thiết cần lưu vô hạn. Xác định retention dựa trên:

- Thời gian cần để điều tra incident.
- Yêu cầu audit và compliance.
- Volume event và dung lượng database.
- Khả năng phục hồi và đối soát.
- Thời gian lưu event ở broker/outbox/event store khác.

Chỉ purge publication completed theo API được hỗ trợ bởi phiên bản Spring Modulith. Không xóa publication incomplete như một thao tác dọn dữ liệu thông thường. Nếu cần giữ audit lâu hơn registry, xuất thông tin cần thiết sang audit store riêng theo chính sách bảo mật và retention.

## 25. Observability cho publication

Dashboard tối thiểu nên có:

| Chỉ số | Ý nghĩa vận hành |
| --- | --- |
| Incomplete publication count | Số listener publication chưa hoàn tất. |
| Oldest incomplete age | Publication tồn tại lâu nhất. |
| Completion rate | Tốc độ hoàn tất publication theo thời gian. |
| Listener failure rate | Tỷ lệ xử lý thất bại theo listener/event type. |
| Resubmission count | Số lần recovery/resubmit. |
| Listener duration | Thời gian xử lý p50/p95/p99. |
| Database health | Kết nối, transaction latency, lock và dung lượng. |

Không dùng eventId, orderId hoặc customerId làm metric tag vì cardinality cao. Dùng những ID đó trong structured log hoặc trace có kiểm soát. Alert nên dựa vào tuổi publication và SLA, không chỉ count; vài publication mới phát sinh có thể bình thường.

## 26. Bảo mật và vận hành

Publication store có thể chứa payload event hoặc dữ liệu đủ để tái tạo hành động nghiệp vụ. Bảo vệ database theo cùng tiêu chuẩn dữ liệu ứng dụng:

- Giới hạn quyền đọc publication store cho tài khoản vận hành cần thiết.
- Mã hóa kết nối database và dữ liệu lưu trữ theo policy.
- Không expose endpoint liệt kê payload publication cho người dùng công khai.
- Resubmit cần authorization, audit và giới hạn theo event/listener.
- Không log toàn bộ payload hoặc thông tin nhạy cảm.
- Giữ backup và kiểm tra restore.
- Theo dõi publication incomplete, không xóa để làm sạch dashboard.

Khi database publication store unavailable, ứng dụng có thể không ghi nhận được publication như mong muốn. Cần xác định behavior của phiên bản và persistence provider, kiểm tra health của database và tránh tiếp tục deploy thay đổi schema trong lúc store không ổn định.

## 27. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có publication record | Event phát ngoài transaction hoặc không có transactional listener phù hợp. | Kiểm tra transaction boundary và listener registration. |
| Publication luôn incomplete | Listener lỗi, nuốt/throw exception không đúng hoặc transaction listener rollback. | Kiểm tra log, handler và transaction. |
| Publication biến mất sau restart | Dùng in-memory store hoặc database không persistent. | Cấu hình persistence provider và database bền vững. |
| Resubmit không gọi listener | Listener identifier hoặc event deserialization không tương thích. | Kiểm tra version, listener target và serializer. |
| Side effect bị lặp | Handler không idempotent khi redelivery. | Thêm inbox/unique constraint và kiểm thử duplicate. |
| Registry tăng dung lượng | Completed publication retention chưa được quản lý. | Dọn completed theo API và policy được hỗ trợ. |
| Rollback publisher vẫn có log publish | Log được ghi trước khi transaction rollback. | Phân biệt publish invocation với commit outcome. |

## 28. Checklist hoàn thành dự án

- Dependency Spring Modulith JPA phù hợp với Spring Boot version.
- Database schema của publication registry được provision bằng migration phù hợp.
- Publisher lưu dữ liệu và phát event trong cùng transaction.
- Event contract là immutable DTO, không mang JPA entity.
- Transactional listener nhận event sau commit.
- Registry lưu publication theo từng listener.
- Listener failure giữ publication ở trạng thái incomplete.
- Listener thành công được đánh dấu completed.
- Publication còn tồn tại sau restart khi dùng cùng database persistent.
- Recovery/resubmit được giới hạn theo điều kiện và có audit.
- Handler idempotent để chịu redelivery.
- Test bao phủ commit, rollback, failure, restart và recovery.
- Dashboard theo dõi incomplete count, age, completion và listener failure.
- Retention chỉ purge completed publication theo API hỗ trợ.
- Không nhầm registry với broker offset, outbox, inbox hoặc event store.

## 29. Bài tập mở rộng

Sau khi hoàn thành luồng cơ bản, hãy thử:

1. Thêm listener thứ hai và chứng minh publication completion độc lập.
2. Thay JPA provider bằng JDBC nếu phù hợp, rồi so sánh schema và vận hành.
3. Thay đổi event payload trong khi còn publication incomplete và kiểm thử compatibility.
4. Tạo lỗi sau khi side effect commit nhưng trước khi completion được ghi nhận; chứng minh idempotency.
5. Viết command vận hành chỉ đọc để lọc publication incomplete theo listener.
6. Thêm metric tuổi publication và cảnh báo khi vượt SLA.
7. Xây dựng retention job cho completed publication theo policy.
8. Tạo integration test khởi động lại ApplicationContext với cùng database container.

Khi hoàn thành bài thực hành, bạn có một luồng application event có publication state được lưu bền vững, có thể quan sát và phục hồi sau lỗi. Điểm cốt lõi là transaction publisher ghi nhận publication cùng dữ liệu nghiệp vụ, listener xử lý trong transaction riêng sau commit, và registry giữ trạng thái incomplete cho đến khi listener hoàn tất. Redelivery vẫn có thể xảy ra, vì vậy idempotency và kiểm thử restart là phần bắt buộc của thiết kế.
