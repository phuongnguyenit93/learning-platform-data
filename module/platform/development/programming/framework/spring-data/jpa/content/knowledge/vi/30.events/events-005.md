# Phân biệt sự kiện miền, Entity callback và auditing

## 1. Ba khái niệm, ba trách nhiệm

Khi một entity được tạo, cập nhật hoặc xóa trong Spring Data JPA, ứng dụng có thể cần chạy thêm logic. Ví dụ, khi đơn hàng được xác nhận, hệ thống cần phát thông báo cho kho; trước khi lưu sản phẩm, ứng dụng cần chuẩn hóa mã SKU; khi khách hàng được cập nhật, hệ thống cần ghi lại thời điểm và người thực hiện.

Ba cơ chế thường gặp là:

- **Domain event (sự kiện miền):** biểu diễn một sự thật nghiệp vụ đã xảy ra, để những phần khác của hệ thống có thể phản ứng.
- **JPA entity lifecycle callback:** hook vào một thời điểm trong vòng đời persistence của entity, như trước INSERT hoặc sau khi load.
- **Spring Data auditing:** tự động ghi metadata tạo và cập nhật như thời gian và actor.

Chúng không phải ba cách viết khác nhau cho cùng một việc. Domain event trả lời “nghiệp vụ nào vừa xảy ra?”. Entity callback trả lời “entity đang ở giai đoạn nào của quá trình persistence?”. Auditing trả lời “ai tạo/sửa bản ghi và vào lúc nào?”.

Một ứng dụng có thể dùng cả ba: service xác nhận đơn hàng và phát `OrderPlaced`; callback chuẩn hóa một trường của entity; auditing cập nhật `createdAt`, `lastModifiedAt` và actor. Mỗi cơ chế giữ một trách nhiệm riêng giúp code dễ hiểu và dễ kiểm thử.

## 2. Domain event: mô tả sự thật nghiệp vụ

Domain event là một đối tượng bất biến mô tả điều đã xảy ra trong miền nghiệp vụ. Tên event thường ở thì quá khứ, ví dụ `OrderPlaced`, `PaymentReceived`, `CustomerActivated` hoặc `InventoryReserved`.

Event nên chứa dữ liệu đủ để handler hiểu và xử lý sự kiện, thường là ID aggregate, mã tương quan và những giá trị nghiệp vụ cần thiết. Tránh truyền cả entity JPA đang managed vào event: entity có thể detached khi handler chạy, chứa lazy association, hoặc bị thay đổi sau khi event được tạo. DTO/record bất biến giúp nội dung event rõ ràng và ổn định hơn.

Ví dụ:

```java
public record OrderPlaced(
    UUID orderId,
    Instant occurredAt
) {}
```

Một aggregate có thể phát sinh event khi chuyển trạng thái nghiệp vụ:

```java
@Entity
public class Order {

    @Id
    private UUID id;

    private boolean placed;

    @Transient
    private final List<Object> domainEvents = new ArrayList<>();

    protected Order() {
    }

    public Order(UUID id) {
        this.id = id;
    }

    public void place(Clock clock) {
        if (placed) {
            throw new IllegalStateException("Order already placed");
        }

        placed = true;
        domainEvents.add(new OrderPlaced(id, clock.instant()));
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
```

Đây là ví dụ tích hợp cần có import, Spring Data repository, JPA provider và Spring context tương ứng. `@Transient` ở đây là annotation JPA, bảo đảm danh sách event không được ánh xạ thành cột. ID được cấp trước giúp event có ID hợp lệ ngay khi phương thức nghiệp vụ phát event; nếu ID chỉ có sau INSERT, hãy chọn thời điểm phát event hoặc định danh khác phù hợp.

### Công bố event bằng Spring Data

Spring Data hỗ trợ lấy và công bố event từ aggregate root qua `@DomainEvents`. Khi các phương thức repository được hỗ trợ thao tác trên aggregate root (chẳng hạn `save`, `saveAll`, `delete`, `deleteAll`), Spring Data có thể gọi phương thức được đánh dấu để lấy event rồi công bố qua Spring application event infrastructure. Sau khi công bố, phương thức được đánh dấu `@AfterDomainEventPublication` được gọi để aggregate dọn danh sách event.

Ví dụ service:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {}

@Service
public class OrderService {

    private final OrderRepository repository;
    private final Clock clock;

    public OrderService(OrderRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Transactional
    public void place(UUID orderId) {
        Order order = repository.findById(orderId).orElseThrow();
        order.place(clock);
        repository.save(order);
    }
}
```

Việc gọi repository là một phần của cơ chế công bố domain event trong Spring Data. Gọi trực tiếp `EntityManager.persist()` hoặc chỉ sửa object trong bộ nhớ mà không đi qua repository operation phù hợp không tự động kích hoạt `@DomainEvents`. Nếu ứng dụng dùng đường ghi khác, hãy công bố event tường minh hoặc xây dựng một cơ chế thống nhất và kiểm thử nó.

`@AfterDomainEventPublication` chỉ dọn event sau khi Spring Data đã công bố chúng. Nó không chứng minh listener đã hoàn tất, cũng không có nghĩa transaction database đã commit. Vì thế, đừng dùng callback này làm tín hiệu rằng side effect bên ngoài đã an toàn để thực hiện.

### Xử lý event theo transaction

Spring cho phép listener gắn với vòng đời transaction bằng `@TransactionalEventListener`:

```java
@Component
public class OrderPlacedHandler {

    private final NotificationService notificationService;

    public OrderPlacedHandler(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        notificationService.notifyCustomer(event.orderId());
    }
}
```

Các phase thường dùng:

| Phase | Thời điểm xử lý |
|---|---|
| `BEFORE_COMMIT` | Trước khi transaction commit |
| `AFTER_COMMIT` | Sau khi transaction commit thành công; đây là mặc định |
| `AFTER_ROLLBACK` | Sau khi transaction rollback |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, dù commit hay rollback |

Nếu event được phát ngoài transaction, listener mặc định không chạy. Chỉ bật `fallbackExecution = true` khi nghiệp vụ cho phép handler chạy cả khi không có transaction.

Application event trong Spring thường được xử lý đồng bộ theo cấu hình mặc định. Nếu handler dùng `@Async` hoặc event multicaster chạy bất đồng bộ, công việc sẽ ở luồng khác và không kế thừa transaction context của luồng phát event. Phần ghi database trong worker cần transaction riêng, thường được đặt ở một service bean khác với `@Transactional`.

Sau `AFTER_COMMIT`, transaction gốc đã hoàn tất. Nếu handler cần ghi thêm dữ liệu bằng JPA, hãy đặt thao tác đó trong service có transaction mới, ví dụ propagation `REQUIRES_NEW`, để thay đổi được commit độc lập. Không dựa vào việc tài nguyên transaction cũ có thể còn được truy cập trong callback để thực hiện một lần ghi mà không có transaction commit tiếp theo.

### Event trong bộ nhớ và Transactional Outbox

`@TransactionalEventListener(AFTER_COMMIT)` bảo đảm handler chỉ được gọi sau khi transaction commit thành công. Tuy nhiên, event Spring trong bộ nhớ không phải hàng đợi bền vững. Nếu tiến trình dừng sau khi database commit nhưng trước khi handler hoàn tất, side effect có thể bị mất.

Với tích hợp quan trọng, dùng Transactional Outbox:

1. Trong cùng transaction nghiệp vụ, lưu thay đổi aggregate và một bản ghi outbox chứa event.
2. Một worker đọc các bản ghi outbox chưa gửi.
3. Worker gửi message đến broker hoặc hệ thống ngoài.
4. Worker đánh dấu đã gửi hoặc lưu trạng thái retry.
5. Consumer xử lý trùng an toàn bằng idempotency key hoặc event ID.

Outbox bảo đảm event và dữ liệu nghiệp vụ được ghi nguyên tử trong cùng database transaction. Việc gửi message vẫn có thể được lặp lại, vì vậy consumer cần xử lý idempotent; không nên tuyên bố hệ thống đạt exactly-once chỉ vì dùng outbox.

## 3. JPA entity lifecycle callback: hook vào vòng đời lưu trữ

Jakarta Persistence cung cấp callback để thực thi logic ở các thời điểm cụ thể trong vòng đời entity:

| Callback | Thời điểm |
|---|---|
| `@PrePersist` | Trước khi entity được persist |
| `@PostPersist` | Sau khi INSERT được thực hiện |
| `@PreUpdate` | Trước khi UPDATE được thực hiện |
| `@PostUpdate` | Sau khi UPDATE được thực hiện |
| `@PreRemove` | Trước khi DELETE được thực hiện |
| `@PostRemove` | Sau khi DELETE được thực hiện |
| `@PostLoad` | Sau khi entity được nạp vào persistence context |

Callback có thể đặt trên entity hoặc trong lớp listener được khai báo qua `@EntityListeners`.

Ví dụ chuẩn hóa SKU:

```java
@Entity
@EntityListeners(ProductLifecycleListener.class)
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    protected Product() {
    }

    public Product(String sku) {
        this.sku = sku;
    }

    void normalizeSku() {
        if (sku != null) {
            sku = sku.trim().toUpperCase(Locale.ROOT);
        }
    }
}

public class ProductLifecycleListener {

    @PrePersist
    @PreUpdate
    public void normalize(Product product) {
        product.normalizeSku();
    }
}
```

Đoạn mã minh họa dùng listener để chuẩn hóa trường của chính entity trước khi lưu. Phương thức callback phải tuân thủ chữ ký và quy tắc của Jakarta Persistence. Nếu muốn inject Spring bean vào entity listener, cần cấu hình tích hợp Spring/JPA phù hợp; không mặc định listener do JPA provider khởi tạo luôn được quản lý như một Spring bean.

### Callback phù hợp với logic nào?

Callback phù hợp với logic nhỏ, cục bộ, gắn với chính entity, ví dụ:

- Chuẩn hóa chuỗi trước khi lưu.
- Đặt giá trị mặc định cho một trường.
- Tính giá trị dẫn xuất đơn giản từ các trường của cùng entity.
- Tạo một giá trị kỹ thuật cần có khi entity đi qua vòng đời persistence.

Callback không phù hợp để gửi email, gọi HTTP, publish message ra broker, điều phối nhiều aggregate hoặc chạy quy trình nghiệp vụ nhiều bước. Các side effect này có thể xảy ra trước khi transaction commit; nếu transaction rollback, hệ thống ngoài vẫn có thể đã nhận tác động.

JPA đặt giới hạn đối với callback: nói chung, không gọi truy vấn hoặc thao tác EntityManager từ callback, không truy cập entity khác trong persistence context và không thay đổi quan hệ giữa các entity trong cùng persistence context. Hãy giữ callback ngắn và tránh phụ thuộc vào trạng thái của các object khác.

### Callback không đồng nghĩa với domain event

`@PostPersist` cho biết thao tác INSERT đã được thực hiện trong quá trình đồng bộ persistence. Nó không nói rằng đơn hàng đã được xác nhận, thanh toán đã thành công hoặc một quy tắc nghiệp vụ đã hoàn tất. Entity có thể được lưu ở trạng thái nháp, transaction có thể rollback sau đó, và cùng một entity có thể được persist/update vì nhiều lý do kỹ thuật.

Do đó, đừng phát event như `OrderPlaced` chỉ vì `@PostPersist` chạy. Hãy phát event ở phương thức nghiệp vụ xác nhận đặt hàng. Callback có thể chuẩn hóa dữ liệu cho entity; event mô tả điều đã xảy ra trong nghiệp vụ.

## 4. Spring Data auditing: ai tạo/sửa và thời điểm nào?

Auditing ghi metadata tạo và cập nhật của entity. Spring Data JPA cung cấp các annotation:

- `@CreatedDate`: thời điểm entity được tạo.
- `@LastModifiedDate`: thời điểm entity được sửa gần nhất.
- `@CreatedBy`: actor tạo entity.
- `@LastModifiedBy`: actor sửa entity gần nhất.

Các trường này hữu ích cho hiển thị, truy vết vận hành và quy trình kiểm tra cơ bản. Auditing không lưu toàn bộ phiên bản trước của entity và không giải thích lý do nghiệp vụ của thay đổi.

### Bật auditing và cung cấp actor

```java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {

    @Bean
    public AuditorAware<String> auditorAware() {
        return () -> Optional.ofNullable(
            SecurityContextHolder.getContext().getAuthentication()
        )
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
    }
}
```

Đây là ví dụ lấy actor từ Spring Security. Ứng dụng thực tế cần xác định rõ trường hợp anonymous, job nền, batch import và service account. Có thể trả về một định danh hệ thống theo quy ước hoặc `Optional.empty()` khi không có actor. Không để trường `createdBy` bị gán tên người dùng giả chỉ để tránh null.

Nếu cần nguồn thời gian riêng cho kiểm thử hoặc chuẩn thời gian của hệ thống, có thể cấu hình `DateTimeProvider`. Với dữ liệu thời điểm toàn cục, `Instant` thường là lựa chọn phù hợp; hãy thống nhất quy tắc hiển thị múi giờ ở API và giao diện.

### Khai báo trường audit trong lớp nền

```java
@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditedEntity {

    @CreatedDate
    @Column(updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
```

Entity nghiệp vụ kế thừa lớp nền:

```java
@Entity
public class Customer extends AuditedEntity {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Customer() {
    }
}
```

Cần có import Jakarta Persistence, Spring Data auditing và Spring Security tương ứng. `@MappedSuperclass` khiến các trường audit được ánh xạ vào bảng của entity con. `@EntityListeners(AuditingEntityListener.class)` đăng ký listener cập nhật các trường auditing; `@EnableJpaAuditing` bật hạ tầng auditing.

Nếu không cần actor, có thể bỏ `@CreatedBy`, `@LastModifiedBy` và `AuditorAware`, nhưng vẫn dùng date auditing. `@Column(updatable = false)` bảo vệ trường tạo khỏi được đưa vào câu UPDATE thông thường; đây là ràng buộc mapping, không phải cơ chế lưu lịch sử bất biến chống mọi kiểu ghi dữ liệu.

### Auditing có giới hạn gì?

Auditing tập trung vào trạng thái hiện tại: ai tạo, ai sửa lần gần nhất và thời gian tương ứng. Nó không tự lưu mọi phiên bản, không lưu diff từng trường và không ghi nguyên nhân nghiệp vụ. Nếu cần lịch sử đầy đủ, hãy xem xét Hibernate Envers, bảng audit riêng hoặc event log có chính sách lưu giữ phù hợp.

Các thao tác bulk JPQL hoặc SQL native cập nhật trực tiếp database mà không tải từng entity vào persistence context. Chúng không đi qua đầy đủ entity lifecycle callback như thao tác entity thông thường, vì vậy auditing cũng không tự cập nhật các trường trên từng bản ghi bulk. Nếu dùng bulk update, hãy chủ động cập nhật audit column trong câu lệnh hoặc chọn một đường ghi khác phù hợp.

## 5. So sánh theo tình huống thực tế

| Tình huống | Cơ chế phù hợp | Lý do |
|---|---|---|
| Đơn hàng được xác nhận, cần kích hoạt kho | Domain event `OrderPlaced` | Đây là sự thật nghiệp vụ cần nhiều thành phần phản ứng |
| Chuẩn hóa SKU trước khi ghi | `@PrePersist` / `@PreUpdate` | Logic nhỏ, gắn với entity đang lưu |
| Ghi thời gian tạo và sửa | Spring Data auditing | Metadata lặp lại ở nhiều entity |
| Gửi email sau khi đơn hàng commit | Domain event + `AFTER_COMMIT` | Tránh gửi khi transaction rollback |
| Lưu lịch sử tất cả thay đổi | Envers hoặc audit log | Auditing metadata chỉ giữ trạng thái tạo/sửa hiện tại |
| Cập nhật trường kỹ thuật sau khi entity load | `@PostLoad` nếu thực sự cần | Hook vào thời điểm entity được nạp |

Không nên dùng `@PostPersist` làm event “đơn hàng đã đặt”, không nên dùng auditing để điều phối quy trình, và không nên đưa truy vấn hoặc I/O ra ngoài vào callback.

## 6. Thiết kế luồng nghiệp vụ kết hợp ba cơ chế

Giả sử khách hàng được kích hoạt. Luồng xử lý có thể như sau:

1. Application service gọi phương thức nghiệp vụ `customer.activate()`.
2. Aggregate kiểm tra điều kiện và thay đổi trạng thái.
3. Aggregate tạo domain event `CustomerActivated`.
4. Repository lưu aggregate; Spring Data công bố event theo cơ chế `@DomainEvents`.
5. JPA callback thực hiện logic cục bộ như chuẩn hóa trường trước khi ghi.
6. Auditing listener gán `lastModifiedAt` và `lastModifiedBy`.
7. Sau khi transaction commit, handler xử lý `CustomerActivated`.

Cấu trúc này giúp tách rõ thay đổi nghiệp vụ, quy tắc vòng đời entity và metadata lưu trữ. Handler có thể được thêm hoặc thay đổi mà aggregate không cần biết tên hay cách hoạt động của nó.

Nếu handler cập nhật database sau commit, gọi một service riêng có transaction mới. Nếu handler gửi message ra ngoài và không được phép mất event khi tiến trình dừng, lưu outbox trong transaction nghiệp vụ rồi gửi bằng worker có retry. Nếu handler chạy bất đồng bộ, truyền ID/DTO bất biến và không truyền entity managed hoặc giả định transaction/security context được chia sẻ qua thread.

## 7. Kiểm thử đúng thời điểm

### Kiểm thử domain event

- Gọi phương thức nghiệp vụ và xác minh aggregate tạo đúng event.
- Kiểm tra thao tác không hợp lệ không phát event.
- Nếu dùng `@DomainEvents`, gọi repository method phù hợp và xác minh event được publish.
- Kiểm tra listener `AFTER_COMMIT` chỉ chạy sau commit và không chạy khi transaction rollback.

Test Spring thường được đánh dấu `@Transactional` và rollback khi kết thúc. Vì vậy, một test transaction bị rollback sẽ không kích hoạt listener `AFTER_COMMIT`. Muốn kiểm tra commit phase, có thể dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()`, hoặc gọi service từ một integration test không có transaction bao quanh.

### Kiểm thử lifecycle callback

Persist entity, flush và reload để xác minh giá trị do callback tạo ra. Ví dụ, nếu callback chuẩn hóa SKU, hãy lưu chuỗi có khoảng trắng/chữ thường rồi đọc lại và xác minh giá trị chuẩn hóa. Kiểm thử qua JPA provider giúp xác nhận callback thực sự được gọi đúng thời điểm.

### Kiểm thử auditing

- Bật `@EnableJpaAuditing` trong test context.
- Cung cấp `AuditorAware` giả định trả về actor cố định.
- Persist entity, flush và reload; kiểm tra `createdAt`, `createdBy`.
- Cập nhật entity trong lần transaction khác; kiểm tra `lastModifiedAt`, `lastModifiedBy`.
- Kiểm tra job nền không có SecurityContext và xác minh actor hệ thống được ghi theo quy ước.

Ví dụ kiểm thử auditing dạng khung:

```java
@DataJpaTest
class CustomerAuditingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void recordsCreationTime() {
        Customer customer = new Customer();
        // Thiết lập dữ liệu cần thiết cho Customer.

        entityManager.persist(customer);
        entityManager.flush();
        entityManager.clear();

        Customer reloaded =
            entityManager.find(Customer.class, customer.getId());

        assertThat(reloaded.getCreatedAt()).isNotNull();
    }
}
```

Đây là khung minh họa; cần có getter, constructor và cấu hình auditing trong test context. Việc clear trước khi đọc giúp tránh lấy lại cùng object đang managed từ persistence context.

## 8. Lỗi thường gặp và cách tránh

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gửi email trong `@PostPersist` | Email có thể được gửi dù transaction sau đó rollback | Phát domain event và xử lý sau commit |
| Phát event chỉ vì gọi `save()` | Save có thể chỉ là lưu trạng thái kỹ thuật, không phải sự kiện nghiệp vụ mới | Phát event tại phương thức nghiệp vụ xác nhận sự thật đó |
| Cho rằng `@AfterDomainEventPublication` nghĩa là handler thành công | Annotation chỉ dọn event sau khi công bố | Theo dõi handler, retry và dùng outbox nếu cần độ tin cậy |
| Dùng callback để truy vấn entity khác | Vi phạm nguyên tắc callback và tạo phụ thuộc persistence khó kiểm soát | Chuyển logic sang service hoặc handler |
| Không cấu hình `AuditorAware` nhưng mong có actor | Trường createdBy/lastModifiedBy không có danh tính mong muốn | Cấu hình actor người dùng hoặc service account |
| Dùng auditing như nhật ký đầy đủ | Không thể khôi phục các phiên bản trước | Dùng Envers hoặc audit log |
| Dùng bulk SQL và chờ auditing tự cập nhật | Bulk DML bỏ qua entity lifecycle thông thường | Cập nhật audit column tường minh hoặc dùng đường ghi entity |

## 9. Checklist chọn cơ chế

- [ ] Logic mô tả một sự thật nghiệp vụ? Dùng domain event.
- [ ] Logic chỉ xử lý trạng thái cục bộ đúng lúc entity persist/load? Cân nhắc lifecycle callback.
- [ ] Cần ghi ai tạo/sửa và thời điểm? Dùng Spring Data auditing.
- [ ] Handler chỉ được chạy sau khi dữ liệu commit? Dùng `@TransactionalEventListener(AFTER_COMMIT)`.
- [ ] Event cần được giao nhận bền vững? Dùng Transactional Outbox và consumer idempotent.
- [ ] Entity listener có giữ logic ngắn, không truy vấn entity khác hoặc gọi hệ thống ngoài?
- [ ] Test có kiểm tra commit/rollback thật và actor trong các luồng nền?

## 10. Ghi nhớ

Domain event thông báo một sự thật nghiệp vụ; JPA callback chạy tại mốc vòng đời persistence; Spring Data auditing ghi metadata tạo và cập nhật. Hãy phát event tại nơi nghiệp vụ được xác nhận, dùng callback cho logic nhỏ trên entity và để auditing quản lý các trường actor/thời gian. Chọn phase transaction cho handler và dùng outbox khi event cần độ tin cậy bền vững. Ba cơ chế phối hợp tốt khi mỗi cơ chế làm đúng phần việc của nó.
