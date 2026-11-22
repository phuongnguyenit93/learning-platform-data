# Tránh truy vấn, gửi mạng hoặc tạo thay đổi đệ quy trong callback của Hibernate ORM

## 1. Một callback nhỏ có thể tạo lỗi rất lớn

Giả sử ứng dụng bán hàng dùng Spring Data JPA và Hibernate ORM. Lập trình viên muốn gửi thông báo khi đơn hàng được tạo và viết:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @PostPersist
    void notifyCustomer() {
        emailGateway.sendOrderCreated(id);
    }
}
~~~

Ý tưởng nghe hợp lý: khi INSERT thành công, gửi email. Nhưng **@PostPersist không có nghĩa giao dịch đã commit**. Callback thường chạy trong tiến trình Hibernate đồng bộ entity với cơ sở dữ liệu; một lỗi xảy ra sau INSERT vẫn có thể làm toàn transaction rollback.

Kịch bản:

~~~text
T1  Transaction bắt đầu
T2  Hibernate INSERT order
T3  @PostPersist chạy -> gửi email "Đã tạo đơn #101"
T4  Một INSERT khác vi phạm UNIQUE constraint
T5  Transaction rollback
T6  Người dùng nhận email về đơn #101 không tồn tại
~~~

Ba loại thao tác khác cũng đặc biệt nguy hiểm trong callback:

- **Truy vấn database qua EntityManager/Repository**: có thể khiến Hibernate tự flush trong lúc nó đang thực hiện flush, gây recursion, lỗi state hoặc query không phản ánh thời điểm nghiệp vụ mong đợi.
- **Gọi mạng hoặc thực hiện I/O chậm**: khiến transaction giữ connection/lock lâu, dễ timeout; tác dụng phụ ngoài DB không rollback cùng transaction.
- **Sửa entity/collection hoặc gọi persist, save, remove lặp lại**: có thể làm phát sinh thay đổi đệ quy trong quá trình Hibernate đang xử lý action queue và lifecycle callbacks.

Bài học thuộc chương **Sự kiện và mở rộng**, tập trung vào nguyên tắc:

> Callback JPA/Hibernate chỉ nên làm công việc cục bộ, ngắn, có tính xác định và không tạo thêm chuỗi tác dụng phụ khó kiểm soát. Truy vấn nghiệp vụ, điều phối giao dịch và giao tiếp với hệ thống ngoài nên đặt ở tầng thích hợp khác.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện các lifecycle callback và thời điểm tương đối với INSERT/UPDATE/DELETE, flush và commit.
2. Giải thích vì sao @PostPersist, @PostUpdate và @PostRemove không đồng nghĩa after-commit.
3. Phân tích rủi ro khi callback gọi Repository, EntityManager, lazy association hoặc truy vấn.
4. Tránh đệ quy khi callback thực hiện save, persist, remove, flush hoặc tự kích hoạt cập nhật.
5. Phân biệt thay đổi local scalar state an toàn với thay đổi quan hệ/collection và hệ thống bên ngoài.
6. Chọn giữa application service, domain event, @TransactionalEventListener và transactional outbox.
7. Hiểu tính nhất quán khi có rollback, optimistic locking, retry và nhiều node.
8. Sử dụng callback cho auditing đơn giản khi phù hợp và nhận biết giới hạn của nó.
9. Kiểm thử rollback, phát sự kiện, callback recursion và SQL statement count.
10. Thiết kế một hệ thống không gửi thông báo hoặc tạo dữ liệu phụ sai chỉ vì callback chạy trước commit.

Ngữ cảnh ví dụ: Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Boot 3.x, Spring Data JPA và PostgreSQL. Chi tiết lifecycle timing hoặc Hibernate event SPI có thể thay đổi theo version/provider; những ví dụ dựa trên tính chất chung của JPA/Hibernate và cần được xác nhận trên runtime mục tiêu.

## 2. Phân biệt callback entity với domain event và transaction event

Ba khái niệm có tên gần nhau nhưng chức năng khác nhau:

| Cơ chế | Thời điểm | Dùng để làm gì? | Có bảo đảm transaction commit thành công? |
|---|---|---|---|
| JPA entity lifecycle callback | Khi provider xử lý chuyển trạng thái/load/flush | Tác động cục bộ lên state của entity, observability nhẹ | Không |
| Hibernate event listener/interceptor | Trong pipeline nội bộ của Hibernate theo loại event | Mở rộng ORM chuyên sâu | Không mặc định |
| Domain/application event | Khi code nghiệp vụ chủ động phát | Diễn tả việc đã xảy ra ở tầng domain/application | Không tự bảo đảm |
| Spring @TransactionalEventListener(AFTER_COMMIT) | Sau commit transaction gắn với event, nếu listener được đăng ký và dispatch thành công | Công việc hậu commit không yêu cầu độ bền tuyệt đối | Event in-memory không bền vững |
| Transactional outbox | Ghi event vào DB trong cùng transaction nghiệp vụ, gửi ra ngoài về sau | Tích hợp đáng tin cậy với queue/email/webhook | Có thể chịu retry và bảo toàn event đã commit theo thiết kế |

**Một lifecycle callback không phải một event bus.** Callback được Hibernate/JPA gọi khi thực hiện công việc ORM; nó không có quyền tự quyết định khi nào đơn hàng thực sự được xem là hoàn tất nghiệp vụ.

Ví dụ một Order có thể được INSERT trong transaction, rồi toàn transaction rollback. Cả @PostPersist và listener tương đương trong ORM có thể đã được gọi, nhưng nghiệp vụ “đơn hàng được tạo thành công” cuối cùng **chưa xảy ra ở trạng thái committed**.

## 3. Các JPA lifecycle callback quan trọng

Jakarta Persistence định nghĩa các sự kiện thường dùng:

| Annotation | Ý nghĩa điển hình | Chú ý |
|---|---|---|
| @PrePersist | Trước khi entity mới được persist vào database | Có thể được gọi ở persist hoặc trong flush theo provider; không giả định SQL đã chạy |
| @PostPersist | Sau thao tác INSERT cho entity | Transaction có thể chưa commit |
| @PreUpdate | Trước thao tác UPDATE phát sinh cho entity | Thường liên quan dirty checking/flush; không chạy cho mọi entity chỉ vì save |
| @PostUpdate | Sau thao tác UPDATE entity | Không phải after-commit |
| @PreRemove | Trước khi xóa entity qua lifecycle ORM | Có thể còn pending SQL |
| @PostRemove | Sau thao tác DELETE entity | Rollback vẫn có thể xảy ra |
| @PostLoad | Sau khi entity được tải từ persistence store hoặc refresh theo lifecycle | Không nhất thiết mỗi lần find đều gọi lại |

Cũng có entity listener khai báo ngoài entity class:

~~~java
@Entity
@EntityListeners(OrderLifecycleListener.class)
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "created_at")
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;
}
~~~

~~~java
public class OrderLifecycleListener {
    @PrePersist
    public void beforeInsert(PurchaseOrder order) {
        // Chỉ làm công việc local phù hợp.
    }

    @PostLoad
    public void afterLoad(PurchaseOrder order) {
        // Không mặc định truy vấn cả graph.
    }
}
~~~

Entity callback method trong chính entity thường không có tham số; listener method thường nhận đối tượng entity đúng kiểu. Mỗi lifecycle annotation có các quy tắc signature/accessibility theo JPA; không tự chọn một overload bất kỳ rồi tin rằng provider sẽ gọi.

### 3.1. Callback không phải API CRUD chủ động

Thông thường application service gọi:

~~~java
entityManager.persist(order);
order.markPaid();
entityManager.remove(order);
~~~

Hibernate quyết định callback nào phù hợp với lifecycle và khi nào chúng chạy trong quá trình xử lý thao tác. Application không nên gọi thủ công method annotate @PreUpdate để “ép cập nhật”.

### 3.2. Không phải mọi thay đổi Java đều tạo @PreUpdate

Nếu entity không dirty, Hibernate có thể không phát UPDATE và do đó không gọi @PreUpdate/@PostUpdate. Chỉ gọi repository.save(order) không đồng nghĩa chắc chắn có UPDATE.

Tương tự, một câu HQL bulk UPDATE hoặc native SQL UPDATE không đi qua lifecycle update của từng entity đang managed theo cùng cách với dirty checking. Điều này ảnh hưởng trực tiếp thiết kế auditing nếu phụ thuộc callback.

### 3.3. @PostLoad có thể xảy ra trong nhiều đường đọc

@PostLoad có thể chạy sau khi provider load entity từ database, second-level cache hoặc refresh tùy lifecycle. Nó không nhất thiết chạy cho mỗi lần entity được truy cập: identity map của persistence context có thể trả ngay instance đang managed.

Vì vậy không sử dụng @PostLoad để làm một thao tác “được gọi một lần cho mỗi request” hoặc dùng nó như authorization hook cho mọi lần đọc.

## 4. Callback diễn ra trong lifecycle ORM, không ở ranh giới commit

Một giao dịch đơn giản:

~~~mermaid
sequenceDiagram
    participant A as Application service
    participant H as Hibernate/EntityManager
    participant DB as Database
    participant X as Hệ thống ngoài
    A->>H: persist(order)
    H->>H: @PrePersist theo lifecycle
    A->>H: flush / auto-flush / commit flow
    H->>DB: INSERT order
    DB-->>H: INSERT thành công
    H->>H: @PostPersist
    Note over H,X: Callback không phải commit boundary
    A->>H: Thao tác thứ hai
    H->>DB: UPDATE/INSERT khác
    DB-->>H: Constraint error
    A->>DB: ROLLBACK
    Note over X: Nếu đã gửi email ở callback, không thể rollback email
~~~

Trình tự thực tế của @PrePersist và INSERT có thể thay đổi theo generator và flush timing. Điểm không đổi là: **callback được gọi trong chu trình persistence, không phải một chứng nhận rằng toàn bộ transaction thành công**.

### 4.1. Flush khác commit

~~~java
@Transactional
public void placeOrder() {
    repository.saveAndFlush(order);
    // @PostPersist có thể đã chạy.

    throw new IllegalStateException("Hủy nghiệp vụ");
}
~~~

Trong cấu hình Spring @Transactional thông thường, unchecked exception khiến transaction rollback. Việc saveAndFlush gọi flush chỉ đẩy SQL pending xuống database trong transaction; nó không commit outer transaction.

### 4.2. @PostUpdate cũng không phải after-commit

Giả sử @PostUpdate gọi thanh toán ngoài:

~~~java
@PostUpdate
void notifyPaid() {
    paymentClient.capturePayment(id);
}
~~~

Một UPDATE thành công ở flush chưa đảm bảo giao dịch sẽ commit. Hơn nữa @PostUpdate có thể chạy với các cập nhật không liên quan trạng thái thanh toán, ví dụ đổi ghi chú. Nếu callback không biết **transition nghiệp vụ** cụ thể, nó có thể gửi nhiều request thanh toán ngoài ý muốn.

### 4.3. @PostRemove không có nghĩa xóa vĩnh viễn

Một @PostRemove gửi HTTP DELETE tới dịch vụ khác có thể thành công, sau đó transaction database rollback và entity trong DB vẫn tồn tại. Tạo distributed side effect trước commit theo cách này dẫn tới trạng thái lệch giữa các hệ thống.

## 5. Quy tắc portability của JPA lifecycle callbacks

Theo mô hình JPA, callback dùng cho một số thao tác nhẹ trên chính entity. Với ứng dụng cần tính portable, **không nên gọi EntityManager hoặc query operations, truy cập các entity khác hoặc sửa relationship trong cùng persistence context từ lifecycle callback**. Callback có thể sửa **non-relationship state** của chính entity khi phù hợp.

Điều này không chỉ là lời khuyên về performance. Provider có thể đang ở một pha flush hoặc materialization mà những thao tác ORM lồng nhau không được thiết kế để re-enter.

### 5.1. Bảng quyết định nhanh

| Việc muốn thực hiện trong callback | Mức phù hợp | Lý do |
|---|---|---|
Gán createdAt nếu chưa có | Thường phù hợp ở @PrePersist | Thay đổi scalar cục bộ |
Chuẩn hóa một mã chuỗi bằng hàm thuần | Có thể phù hợp | Không truy cập persistence khác |
Gán updatedAt trước UPDATE | Thường phù hợp nếu kiểm thử provider | Scalar state trên chính entity |
Kiểm tra invariant local, không cần DB | Có thể phù hợp | Không phát I/O |
Tính transient display label từ scalar fields | Có thể phù hợp ở @PostLoad | Cục bộ và không đụng association |
Gọi repository.findById()/existsBy... | Tránh | Query/EntityManager trong lifecycle callback |
Gọi entityManager.flush() | Tránh tuyệt đối | Flush reentrancy/recursive flush |
Gọi repository.save(otherEntity) | Tránh | Thay đổi persistence context trong lifecycle |
Thêm/xóa phần tử @OneToMany | Tránh | Cascade, orphan, action queue có thể thay đổi bất ngờ |
Truy cập lazy collection để tính tổng | Tránh | Có thể sinh SQL khi load/flush |
Gửi HTTP/email/Kafka trong callback | Tránh | Mạng ngoài transaction, không rollback được |
Ghi file, gọi shell, ngủ/chờ retry | Tránh | Latency, lock, non-transactional side effect |
Đọc SecurityContext/RequestContext sâu trong entity | Tránh | Coupling với thread/request, async không ổn định |

“Có thể phù hợp” vẫn cần xét business semantics, callback timing và loại field. Chẳng hạn việc thay đổi timestamp trong @PreUpdate là pattern phổ biến nhưng không nên dùng callback để tái cấu trúc graph liên kết đang được Hibernate flush.

## 6. Truy vấn ngay trong callback nguy hiểm như thế nào?

Một ví dụ sai:

~~~java
public class OrderLifecycleListener {
    @PersistenceContext
    private EntityManager em;

    @PreUpdate
    public void beforeUpdate(PurchaseOrder order) {
        Long count = em.createQuery("""
            select count(o)
            from PurchaseOrder o
            where o.customer.id = :customerId
            """, Long.class)
            .setParameter("customerId", order.getCustomerId())
            .getSingleResult();

        order.setCustomerOrderCount(count);
    }
}
~~~

Các getter/setter và việc injection EntityManager ở trên chỉ để minh họa anti-pattern; listener JPA mặc định còn có ràng buộc về dependency injection tùy môi trường tích hợp. Không áp dụng đoạn code này vào production.

### 6.1. Vấn đề reentrant flush

Một tình huống:

~~~text
Service sửa Order
  -> Hibernate bắt đầu flush
     -> Gọi @PreUpdate(Order)
        -> Callback chạy SELECT qua EntityManager
           -> AUTO flush xem xét thay đổi pending
              -> Có nguy cơ kích hoạt flush/processing lồng nhau
                 -> Exception, hành vi không được bảo đảm hoặc recursion
~~~

Provider có thể ngăn reentrant flush hoặc trì hoãn hoạt động khác nhau; không cam kết một exception cụ thể trên mọi Hibernate version. Điều đáng tránh là **đặt query vào pha mà ORM đang xử lý thay đổi chưa hoàn tất**.

### 6.2. Query có thể nhìn thấy trạng thái không như mong đợi

Một entity đang được flush có thể đã được dirty-check nhưng SQL chưa hoàn tất. Callback truy vấn số đơn/giá trị aggregate và cho rằng “database đã thấy tất cả thay đổi” là giả định nguy hiểm. Thứ tự action queue, cascade và transaction isolation ảnh hưởng kết quả.

### 6.3. Callback bị gọi rất nhiều lần

Nếu một batch cập nhật 10.000 Order, @PreUpdate có thể được gọi cho nhiều entity. Một SELECT trong mỗi callback có thể biến một batch dự kiến vài statement thành hàng nghìn SELECT:

~~~text
10.000 Order updates
  + 10.000 callbacks
  + 10.000 SELECT count(...)
~~~

Ngay cả khi không gây recursion, đây là dạng N+1 gây tải database và làm transaction kéo dài.

### 6.4. Truy vấn kiểm tra uniqueness trong callback không tránh race

Sai:

~~~java
@PrePersist
void checkEmail() {
    if (customerRepository.existsByEmail(email)) {
        throw new IllegalArgumentException("Email đã tồn tại");
    }
}
~~~

Hai transaction có thể đồng thời thấy chưa có email rồi đều INSERT. Chỉ database UNIQUE constraint mới bảo đảm uniqueness trong mọi writer. Validation nghiệp vụ có thể được thực hiện ở service để có thông báo sớm, nhưng DB constraint vẫn bắt buộc.

### 6.5. Query trong callback còn gây coupling kiến trúc

Entity lifecycle xảy ra khi Hibernate load/flush qua nhiều đường: REST, batch job, import, tests, scheduled job. Nếu callback giả định một HTTP request/user context hoặc repository bean luôn sẵn có, một batch không có request vẫn bị phụ thuộc vào logic ấy.

**Đưa query nghiệp vụ ra application service hoặc repository method được gọi ở thời điểm rõ ràng.**

## 7. Lazy loading trong @PostLoad cũng có thể tạo truy vấn ẩn

Một listener có thể trông vô hại:

~~~java
@PostLoad
void afterLoad() {
    this.itemCount = items.size();
}
~~~

Nếu items là LAZY collection và không được fetch sẵn, gọi size() có thể khiến Hibernate truy vấn collection hoặc thực hiện thao tác đặc biệt tùy mapping/extra-lazy. Giả sử một trang tải 100 Order, @PostLoad có thể kích hoạt hàng trăm query.

### 7.1. Vì sao @PostLoad đặc biệt nhạy cảm?

@PostLoad chạy khi ORM hydrate entity. Khi callback truy cập một association chưa initialized, nó tạo thêm bước load trong quá trình load. Nếu đối tượng liên quan cũng có @PostLoad truy cập ngược association, các callback có thể nối tiếp bất ngờ.

Ví dụ:

~~~text
Load Order #101
  -> @PostLoad(Order) đọc customer.getOrders()
     -> Load Customer / Orders
        -> @PostLoad(Customer) đọc Orders từng phần
           -> Thêm query/callback...
~~~

Provider có cơ chế identity map/proxy để tránh một số vòng tham chiếu, nhưng **không nên thiết kế callback như cơ chế duyệt graph**.

### 7.2. Derived transient field từ scalar local

Một trường hợp nhẹ và tương đối an toàn:

~~~java
@Transient
private String displayReference;

@PostLoad
void computeReference() {
    displayReference = orderCode == null
        ? "(chưa có mã)"
        : orderCode.strip();
}
~~~

Ở đây chỉ dùng scalar orderCode đã có trên entity, không truy vấn hoặc chạm lazy association. Tuy nhiên cần xác định liệu displayReference có nên là getter tính toán thay vì cache vào transient field; nếu orderCode được đổi sau load, transient field có thể trở nên cũ.

### 7.3. Đừng dùng @PostLoad để kiểm tra quyền truy cập

Kiểm tra authorization ở @PostLoad có nhiều vấn đề:

- Có thể không chạy khi entity đã nằm trong L1.
- Có thể chạy ngoài HTTP request khi batch job load entity.
- Không thích hợp cho bulk native SQL hoặc projection DTO.
- Có nguy cơ lấy dữ liệu trước khi quyền được xác nhận.

Quyền truy cập nên được thực thi trong service/repository query hoặc database policy phù hợp, không phụ thuộc một entity callback.

## 8. Sửa entity trong callback: những trường hợp nào an toàn?

JPA cho phép callback sửa **non-relationship state của chính entity** trong phạm vi phù hợp. Ví dụ phổ biến là thời gian tạo/cập nhật:

~~~java
@MappedSuperclass
public abstract class AuditedEntity {
    @Column(name = "created_at", nullable = false,
            updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    protected void beforeInsert() {
        Instant now = Instant.now();
        if (createdAt == null) {
            createdAt = now;
        }
        updatedAt = now;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
~~~

Đây là callback **cục bộ**: không repository, không EntityManager, không network, không mutation collection. Chức năng tương tự có thể được hỗ trợ bằng Spring Data auditing hoặc annotation timestamp của Hibernate; chọn một cơ chế để tránh conflict.

### 8.1. @PreUpdate chỉ chạy khi có update thực sự

Không nên giả định @PreUpdate được gọi mỗi khi một endpoint POST/PATCH đi qua service. Nếu Hibernate không phát UPDATE vì entity không dirty, @PreUpdate có thể không chạy. Để lưu một business event “user đã xem đơn” dù entity không thay đổi, không dựa vào @PreUpdate.

### 8.2. Thay đổi ở @PreUpdate phụ thuộc flush processing

Trong nhiều trường hợp Hibernate lấy state dùng cho UPDATE sau callback và có thể đưa thay đổi scalar vào câu SQL. Nhưng hành vi với những thao tác như đổi ID, đổi quan hệ, thao tác collection hoặc sửa nhiều field sau khi dirty check đã bắt đầu là phức tạp. Chỉ dùng callback cho scalar đơn giản và viết integration test đối chiếu giá trị thật trong DB.

### 8.3. Không cập nhật trường id hoặc version tùy tiện

~~~java
@PreUpdate
void beforeUpdate() {
    this.id = generateAnotherId(); // Sai: identity không được thay tùy ý.
    this.version++;                 // Sai: provider quản lý @Version.
}
~~~

ID là định danh persistent object; version phục vụ optimistic locking. Tự đổi chúng từ callback có thể phá vỡ identity map, SQL WHERE version và concurrency protocol.

### 8.4. Không biến callback thành nơi enforce invariant cần DB

Nếu tổng tiền phải bằng tổng các OrderItem, callback @PreUpdate đọc toàn bộ items để tính lại có thể load collection và thay đổi state khi flush. Một cách rõ hơn là method domain trong transaction:

~~~java
@Transactional
public void changeQuantity(Long orderId, Long itemId, int quantity) {
    PurchaseOrder order = repository.findById(orderId)
        .orElseThrow();
    order.changeItemQuantity(itemId, quantity);
    order.recalculateTotal();
}
~~~

Nếu collection lớn, tính toán có thể dựa vào query/projection thích hợp **trước** flush hoặc dùng cơ chế DB. Dù chọn cách nào, invariant cần được kiểm chứng ở application/DB level, không giấu vào callback.

## 9. Đệ quy khi callback tự gọi save, flush hoặc persist

Một anti-pattern:

~~~java
@PostUpdate
void updateAudit() {
    auditRepository.save(
        new AuditLog("ORDER_UPDATED", id));
}
~~~

Nếu listener được gọi trong flush, auditRepository.save() có thể thay đổi action queue trong khi Hibernate đang xử lý action queue. Tùy transaction/cascade/generator, nó có thể tạo SQL bất ngờ hoặc gây reentrancy.

Tệ hơn:

~~~java
@PostUpdate
void afterUpdate() {
    this.lastProcessedAt = Instant.now();
    orderRepository.saveAndFlush(this);
}
~~~

Hệ quả có thể là:

~~~text
Flush
  -> UPDATE Order
     -> @PostUpdate
        -> sửa Order
        -> saveAndFlush
           -> Flush
              -> UPDATE Order
                 -> @PostUpdate
                    -> ...
~~~

Không có bảo đảm Hibernate sẽ để vòng lặp chạy đến stack overflow; nó có thể ném exception về flush/session state trước đó. Nhưng mã đã tạo **phụ thuộc đệ quy giữa callback và chính cơ chế gọi callback**.

### 9.1. Không tự gọi EntityManager.flush trong callback

~~~java
@PreUpdate
void beforeUpdate() {
    entityManager.flush(); // Không làm.
}
~~~

Lệnh flush trong khi Hibernate đang flush có thể tạo lỗi trạng thái nội bộ. Nó cũng không giải quyết vấn đề “muốn dữ liệu mới nhất”, vì callback đang ở một thời điểm không thích hợp để điều khiển flush boundary.

### 9.2. Gọi persist một entity khác cũng nguy hiểm

~~~java
@PostPersist
void afterInsert() {
    entityManager.persist(new Notification(...));
}
~~~

Ngay cả khi một Hibernate version cho phép một số thay đổi được xếp lịch vào context, ứng dụng sẽ phụ thuộc vào hành vi không portable và thứ tự action queue/cascade khó dự đoán. Với nghiệp vụ có yêu cầu Notification row, **tạo cả Order và Notification trong application service trước commit**, không trong callback.

### 9.3. Việc đặt boolean recursionGuard không giải quyết bản chất

~~~java
private boolean inCallback;

@PostUpdate
void afterUpdate() {
    if (inCallback) return;
    inCallback = true;
    repository.saveAndFlush(this);
}
~~~

Flag tạm thời chỉ che vòng lặp nhất định; vẫn có flush reentrancy, transaction boundaries và detached/object lifecycle. Ngoài ra entity có thể được hydrate/serialized qua contexts khác, khiến guard không có semantics đáng tin cậy. **Sửa vị trí thực hiện side effect**, không chỉ thêm guard.

## 10. Thay đổi quan hệ và collection trong callback

Giả sử Order có:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderItem> items = new ArrayList<>();
~~~

Một callback:

~~~java
@PreUpdate
void normalizeItems() {
    items.removeIf(item -> item.getQuantity() <= 0);
}
~~~

đang làm thay đổi collection trong lúc Hibernate có thể đã chuẩn bị snapshot, dirty collection actions, cascade và orphan deletion. Nó không chỉ sửa scalar trên chính entity.

### 10.1. Rủi ro với cascade

Thêm OrderItem mới trong callback có thể yêu cầu cascade PERSIST, định danh generated ID, FK owning side, INSERT ordering và dirty checking lại. Không nên dựa vào việc Hibernate tự phát hiện đầy đủ một association vừa được thay đổi sau khi pipeline flush đã bắt đầu.

### 10.2. Rủi ro với orphanRemoval

Xóa phần tử khỏi collection trong callback có thể khiến Hibernate lên lịch DELETE ngoài dự kiến. Nếu callback chỉ được thiết kế để “chuẩn hóa state trước lưu”, một bug nhỏ có thể xóa row thật.

### 10.3. Cách đúng: method domain trước flush

~~~java
@Transactional
public void removeInvalidItems(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();

    order.removeInvalidItems();
    order.recalculateTotal();
    // Hibernate xử lý collection changes ở flush sau service mutation.
}
~~~

Method removeInvalidItems phải cập nhật đúng owning side của quan hệ và các invariant. Việc gọi ở service trước flush làm thời điểm thay đổi rõ ràng, có thể test trực tiếp.

### 10.4. Cẩn thận callback trên cả parent và child

Nếu cả PurchaseOrder và OrderItem có @PrePersist/@PreUpdate và mỗi callback lại sửa entity kia, việc cascade lưu graph có thể tạo thứ tự side effects không rõ. Thiết kế aggregate root làm nơi điều phối thay đổi, tránh vòng phụ thuộc hai chiều giữa callbacks.

## 11. Gửi HTTP, email, message broker trong callback vì sao không an toàn?

Xét:

~~~java
@PostPersist
void sendWelcomeEmail() {
    emailClient.send(...);
}
~~~

Có ít nhất năm nhóm rủi ro độc lập.

### 11.1. Tác dụng phụ không rollback cùng database

Database rollback không thu hồi email đã gửi, request HTTP đã đến đích hoặc message broker đã nhận sự kiện. Đặc biệt với thanh toán/fulfillment, kết quả có thể gây tranh chấp nghiệp vụ.

### 11.2. Gọi mạng giữ transaction mở

Trong lúc chờ HTTP 2 giây, DB transaction có thể đang giữ connection, row locks hoặc snapshot. Khi service ngoài bị chậm:

- DB connection pool bị chiếm lâu.
- Các transaction khác có thể chờ lock.
- Thời gian response tăng.
- Deadlock/timeout và retry trở nên khó phân tích.

Callback thường nằm sâu trong ORM internals nên người đọc service không thấy trực tiếp network call, khiến hiệu năng khó chẩn đoán.

### 11.3. Retry gây gửi trùng

Nếu transaction gặp deadlock/optimistic conflict và application retry, callback có thể chạy nhiều lần. Một webhook payment capture không có idempotency key có thể bị thực hiện hai lần.

### 11.4. Ngoại lệ mạng có thể rollback transaction không chủ ý

HTTP timeout trong @PreUpdate hoặc @PostPersist ném unchecked exception ra ngoài có thể khiến transaction rollback. Khi business chỉ cần gửi thông báo, lỗi mạng đáng lẽ không phải lúc nào cũng có quyền hủy giao dịch chính.

Ngược lại, bắt exception rồi nuốt sẽ làm đơn hàng commit nhưng thông báo thất bại mà không có cơ chế retry. Cả hai hướng đều khó vận hành nếu không có explicit contract.

### 11.5. Callback chạy cả trong batch/import

Một job import 100.000 Orders có thể vô tình phát 100.000 HTTP calls trong cùng batch transaction. Điều này làm job chậm, tăng áp lực mạng và tạo side effects trước khi toàn bộ import được commit.

## 12. Những tác vụ phù hợp với callback

Callback vẫn có giá trị khi phạm vi đúng.

### 12.1. Gán createdAt và updatedAt

~~~java
@PrePersist
void onCreate() {
    Instant now = Instant.now();
    if (createdAt == null) createdAt = now;
    updatedAt = now;
}

@PreUpdate
void onUpdate() {
    updatedAt = Instant.now();
}
~~~

Không I/O, không query và không sửa association. Nếu cần thời gian có thể kiểm thử với Clock, cân nhắc gán trong service hoặc provider-aware auditing thay vì gọi system clock trực tiếp trong entity.

### 12.2. Chuẩn hóa scalar cục bộ

~~~java
@PrePersist
@PreUpdate
void normalizeCode() {
    if (externalCode != null) {
        externalCode = externalCode.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

Việc chuẩn hóa nên có tính quyết định, không phụ thuộc dịch vụ ngoài. Tuy vậy nếu normalize ảnh hưởng unique key hoặc comparison semantics, DB constraints và input validation vẫn phải nhất quán.

### 12.3. Kiểm tra invariant local

~~~java
@PrePersist
@PreUpdate
void assertValidLocalState() {
    if (totalAmount == null || totalAmount.signum() < 0) {
        throw new IllegalStateException(
            "totalAmount phải không âm");
    }
}
~~~

Đây là validation không cần DB; callback có thể là một lớp phòng vệ bổ sung. Nhưng thông báo lỗi cuối cùng còn phụ thuộc transaction/exception translation. Cần thể hiện invariant trong domain method/service và DB CHECK constraint nếu mọi writer phải tuân thủ.

### 12.4. Derived transient scalar sau load

~~~java
@PostLoad
void buildDisplayCode() {
    displayCode = code == null ? "" : code.strip();
}
~~~

Nếu chỉ dựa trên scalar đã load thì chi phí nhỏ. Nếu displayCode phụ thuộc collection/association, để việc tính toán ở DTO projection hoặc service thay vì kích hoạt lazy queries.

## 13. Điều không nên đưa vào callback: transaction và quyền truy cập

### 13.1. Không mở transaction mới từ entity callback

~~~java
@PostUpdate
void afterUpdate() {
    auditService.saveInNewTransaction(...);
}
~~~

Ngay cả khi một Spring bean được inject và method có REQUIRES_NEW, transaction mới có thể commit audit row **trước khi transaction chính hoàn tất**. Nếu transaction chính rollback, audit đã commit về một thay đổi chưa tồn tại.

REQUIRES_NEW không biến callback thành after-commit; nó chỉ tách transaction, còn sự kiện được kích hoạt quá sớm.

### 13.2. Không dựa vào SecurityContext trong entity listener

Một callback đọc:

~~~java
SecurityContextHolder.getContext()
    .getAuthentication().getName();
~~~

có thể không có principal khi batch job, scheduler, async worker hoặc migration thực hiện write. Entity cũng trở nên phụ thuộc vào hạ tầng Spring Security.

Nếu cần createdBy/updatedBy, cân nhắc Spring Data auditing với AuditorAware có policy rõ cho system actor, hoặc truyền actor từ application service. Đừng mặc định mọi persistence operation có HTTP user.

### 13.3. Không bắt exception mạng rồi tự gọi flush tiếp

Nếu một callback đã làm Hibernate/JDBC transaction lỗi, cố phục hồi bằng repository.saveAndFlush hoặc EntityManager.clear ngay trong callback không phải một chiến lược rollback an toàn. Để exception propagate tới transaction boundary; retry phải bắt đầu bằng transaction mới khi thích hợp.

## 14. Giải pháp 1: điều phối hoàn toàn ở application service

Với một nghiệp vụ tạo Order và tạo Notification row trong **cùng DB transaction**, không cần callback:

~~~java
@Service
public class OrderService {
    private final PurchaseOrderRepository orders;
    private final NotificationRepository notifications;

    public OrderService(
            PurchaseOrderRepository orders,
            NotificationRepository notifications) {
        this.orders = orders;
        this.notifications = notifications;
    }

    @Transactional
    public Long placeOrder(CreateOrderCommand cmd) {
        PurchaseOrder order = PurchaseOrder.create(cmd);
        PurchaseOrder saved = orders.save(order);

        Notification notice = Notification.pendingOrderCreated(
            saved.getId(),
            cmd.customerId()
        );
        notifications.save(notice);

        return saved.getId();
    }
}
~~~

Các class command/entity/helper là khung minh họa cho domain; không phải API Spring có sẵn.

Ưu điểm:

- Hai repository tham gia cùng transaction theo mặc định.
- Lý do tạo Notification hiển thị rõ tại use case.
- Không có EntityManager/query lồng trong callback.
- Nếu transaction rollback, cả Order và Notification DB row rollback.
- Dễ kiểm thử quyền truy cập và business state.

### 14.1. Notification row khác gửi email thật

Đoạn code trên tạo một bản ghi trong DB, **chưa gửi email**. Một worker riêng có thể đọc Notification sau khi commit rồi giao tiếp email provider. Đó là phần quan trọng khi cần side effect đáng tin cậy.

### 14.2. Trường hợp callback là lựa chọn kém

Một entity PurchaseOrder có thể được persist bởi nhiều use case khác nhau: đặt đơn thủ công, import lịch sử, migration, phục hồi dữ liệu hoặc tạo bản nháp. Không phải trường hợp nào cũng muốn gửi email. Application service biết ngữ cảnh nghiệp vụ và có thể chọn khi nào tạo thông báo; @PostPersist không phân biệt được mọi ý định.

## 15. Giải pháp 2: domain event + Spring transaction event sau commit

Đối với tác vụ nhẹ, có thể phát event ở application service và xử lý sau commit bằng Spring:

~~~java
public record OrderPlacedEvent(
    Long orderId,
    Long tenantId,
    String eventId
) {}
~~~

~~~java
@Service
public class PlaceOrderService {
    private final PurchaseOrderRepository orders;
    private final ApplicationEventPublisher events;

    public PlaceOrderService(
            PurchaseOrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public Long place(CreateOrderCommand command, Long tenantId) {
        PurchaseOrder order = PurchaseOrder.create(command, tenantId);
        PurchaseOrder saved = orders.save(order);

        events.publishEvent(new OrderPlacedEvent(
            saved.getId(),
            tenantId,
            UUID.randomUUID().toString()
        ));
        return saved.getId();
    }
}
~~~

Listener:

~~~java
@Component
public class OrderPlacedListener {
    private final EmailGateway emailGateway;

    public OrderPlacedListener(EmailGateway emailGateway) {
        this.emailGateway = emailGateway;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(OrderPlacedEvent event) {
        emailGateway.sendOrderConfirmation(
            event.orderId(),
            event.eventId()
        );
    }
}
~~~

Những class/interface khác cần được import/triển khai theo project. Mã minh họa cách tách **thời điểm thay đổi domain** khỏi **thời điểm chạy tác vụ ngoài DB**.

### 15.1. AFTER_COMMIT giải quyết điều gì?

Nếu transaction rollback, listener đăng ký cho phase AFTER_COMMIT sẽ không thực thi như một sự kiện commit thành công. Nếu transaction commit xong, listener có thể được gọi sau commit.

Điều này giải quyết vấn đề email được gửi từ @PostPersist **trước khi biết transaction thành công**.

### 15.2. Nhưng AFTER_COMMIT không bền vững

Một rủi ro:

~~~text
T1  COMMIT Order thành công
T2  Process JVM crash ngay trước khi listener gửi email
T3  Order đã có trong DB
T4  Không còn event in-memory để retry
~~~

Spring application event trong memory không tự là một message queue bền vững. Event có thể mất nếu process crash, listener chưa chạy hoặc lỗi mạng không có retry/dedup.

Vì vậy @TransactionalEventListener(AFTER_COMMIT) thích hợp cho công việc hậu commit có thể chấp nhận thất lạc hoặc có cơ chế bù từ nguồn dữ liệu khác. Với thông báo thanh toán/fulfillment cần bảo đảm, transactional outbox là lựa chọn mạnh hơn.

### 15.3. Event chỉ được publish khi có transaction phù hợp

Mặc định của @TransactionalEventListener thường không chạy listener khi không có transaction đang hoạt động, trừ khi thiết lập fallbackExecution. Nếu service vô tình không đi qua Spring @Transactional proxy (self-invocation), event behavior có thể khác.

Hãy kiểm thử event dispatch trong chính cấu hình transaction của dự án. Không bật fallbackExecution chỉ để mọi event “chạy bằng mọi giá” nếu nó làm mất ngữ nghĩa AFTER_COMMIT.

### 15.4. AFTER_COMMIT và DB writes cần transaction mới

Ở callback phase AFTER_COMMIT của Spring, tài nguyên transaction có thể vẫn còn được bind trong quá trình hoàn tất transaction. Nếu listener cần ghi thêm DB row, **không giả định ghi đó sẽ được commit trong transaction cũ đã kết thúc**.

Có thể gọi một service riêng với @Transactional(propagation = REQUIRES_NEW) khi thật sự cần một transaction mới. Nhưng nếu mục tiêu là bảo đảm một DB task không bị mất giữa commit và handler, hãy ghi một outbox record **trong transaction nghiệp vụ ban đầu**, không trì hoãn việc ghi record quan trọng tới AFTER_COMMIT.

### 15.5. Listener đồng bộ hay bất đồng bộ?

@TransactionalEventListener không tự có nghĩa một thread nền luôn xử lý. Cách dispatch phụ thuộc Spring event multicaster, @Async và cấu hình executor. Nếu handler làm HTTP call đồng bộ sau commit, response vẫn có thể bị kéo dài hoặc lỗi handler có thể được phản ánh vào lời gọi service tùy dispatch/error handling, dù DB đã commit.

Nếu dùng @Async, cần hiểu rằng thread mới không có sẵn EntityManager/transaction/request context của thread cũ. Event nên chứa dữ liệu immutable tối thiểu (ID, tenant, eventId), không giữ entity managed/lazy proxy.

## 16. Giải pháp 3: transactional outbox cho tích hợp đáng tin cậy

Khi cần gửi Kafka message, webhook, email hoặc gọi dịch vụ khác **không được bị mất sau khi transaction commit**, outbox là pattern quan trọng.

Ý tưởng:

1. Trong cùng transaction DB, ghi thay đổi nghiệp vụ và một **outbox event row**.
2. Commit cả hai atomically.
3. Một worker riêng đọc outbox đã commit.
4. Worker gửi message/network call ngoài transaction nghiệp vụ.
5. Nếu lỗi, retry; consumer/gateway phải hỗ trợ idempotency.

~~~mermaid
flowchart TD
    A[Application service @Transactional] --> B[UPDATE/INSERT Order]
    B --> C[INSERT outbox_event]
    C --> D{Commit transaction?}
    D -->|Rollback| E[Không có Order và outbox event đã commit]
    D -->|Thành công| F[(Database: Order + Outbox)]
    F --> G[Outbox publisher worker]
    G --> H[Email / Kafka / HTTP]
    H --> I{Đích trả kết quả?}
    I -->|Thành công| J[Đánh dấu SENT bằng transaction mới]
    I -->|Thất bại| K[Retry có backoff]
    K --> G
~~~

Outbox không làm một transaction database và một message broker trở thành một distributed transaction atomic. Nó chuyển bài toán thành **at-least-once delivery** có retry/dedup đáng tin cậy hơn.

### 16.1. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'READY',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_by VARCHAR(80),
    claimed_until TIMESTAMPTZ,
    CONSTRAINT ck_outbox_status
      CHECK (status IN ('READY', 'CLAIMED', 'SENT', 'DEAD'))
);

CREATE INDEX idx_outbox_ready
ON outbox_events(status, next_attempt_at, occurred_at);
~~~

Trong production, schema có thể thêm partitioning, retry metadata, retention và unique business event constraint. payload_json dùng TEXT để minh họa portable mapping; có thể dùng PostgreSQL JSONB với cấu hình Hibernate/JDBC phù hợp.

### 16.2. Outbox entity

~~~java
@Entity
@Table(name = "outbox_events")
public class OutboxEvent {
    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "aggregate_type", nullable = false)
    private String aggregateType;

    @Column(name = "aggregate_id", nullable = false)
    private Long aggregateId;

    @Column(name = "event_type", nullable = false)
    private String eventType;

    @Column(name = "payload_json", nullable = false)
    private String payloadJson;

    @Column(nullable = false)
    private String status;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    protected OutboxEvent() {}

    public static OutboxEvent orderPlaced(
            UUID eventId, Long tenantId, Long orderId,
            String payloadJson) {
        OutboxEvent out = new OutboxEvent();
        out.id = eventId;
        out.tenantId = tenantId;
        out.aggregateType = "PurchaseOrder";
        out.aggregateId = orderId;
        out.eventType = "OrderPlaced";
        out.payloadJson = payloadJson;
        out.status = "READY";
        out.occurredAt = Instant.now();
        return out;
    }
}
~~~

Repository.save(outbox) trong transaction chung không phải callback. Các field mặc định từ DB như attempt_count/next_attempt_at có thể được bỏ qua khi insert nếu mapping chỉ ghi các field đã khai báo; khi cần đọc chúng qua entity, phải bổ sung mapping/generated-value handling rõ ràng.

### 16.3. Service ghi nghiệp vụ và event cùng transaction

~~~java
@Service
public class PlaceOrderService {
    private final PurchaseOrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper json;

    public PlaceOrderService(
            PurchaseOrderRepository orders,
            OutboxRepository outbox,
            ObjectMapper json) {
        this.orders = orders;
        this.outbox = outbox;
        this.json = json;
    }

    @Transactional
    public Long place(CreateOrderCommand command, Long tenantId) {
        PurchaseOrder order = PurchaseOrder.create(command, tenantId);
        PurchaseOrder saved = orders.save(order);

        UUID eventId = UUID.randomUUID();
        String payload = serializePayload(
            json, saved.getId(), tenantId, eventId);

        outbox.save(OutboxEvent.orderPlaced(
            eventId, tenantId, saved.getId(), payload
        ));

        return saved.getId();
    }
}
~~~

serializePayload là helper ứng dụng cần triển khai; JSON nên có schema/version và chỉ chứa dữ liệu tối thiểu cần cho consumer. Không nhúng toàn bộ entity graph hoặc dữ liệu nhạy cảm không cần thiết.

### 16.4. Vì sao outbox tốt hơn gửi mạng ngay trong transaction?

Với cùng DB transaction:

~~~text
Order INSERT thành công + Outbox INSERT thành công
    -> Commit cả hai
    hoặc rollback cả hai
~~~

Worker chỉ thấy outbox đã commit, nên không gửi thông báo về một Order bị rollback (giả định transaction isolation/read policy phù hợp).

Nếu JVM crash sau commit, outbox row vẫn tồn tại cho worker xử lý khi hệ thống khởi động lại.

## 17. Publisher outbox: claim, gửi, đánh dấu, retry

Worker không nên giữ transaction và row lock trong suốt một HTTP request có thể kéo dài nhiều giây.

Một quy trình production-oriented:

1. **Transaction ngắn A:** claim một batch outbox rows đến hạn, gắn claimed_by, claimed_until và attempt_count; commit.
2. **Ngoài transaction A:** gửi tới Kafka/email/webhook với eventId làm idempotency key.
3. **Transaction ngắn B:** đánh dấu SENT nếu claim token còn hợp lệ; hoặc ghi trạng thái retry/backoff nếu lỗi.
4. Nếu worker chết, lease hết hạn cho worker khác claim lại.

### 17.1. Claim đồng thời bằng SKIP LOCKED

PostgreSQL SQL minh họa:

~~~sql
WITH picked AS (
    SELECT id
    FROM outbox_events
    WHERE (
        status = 'READY'
        OR (
            status = 'CLAIMED'
            AND claimed_until < CURRENT_TIMESTAMP
        )
    )
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY occurred_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE outbox_events e
SET status = 'CLAIMED',
    claimed_by = :worker_token,
    claimed_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = e.attempt_count + 1
FROM picked
WHERE e.id = picked.id
RETURNING
    e.id, e.tenant_id, e.event_type, e.payload_json;
~~~

Đây là SQL thiết kế minh họa; có thể phải điều chỉnh theo JDBC/native query API và PostgreSQL version. Thời hạn lease phải dựa trên thời gian xử lý, retry và SLA; hai phút không phải mặc định chung.

### 17.2. Không giữ lock khi gọi mạng

~~~text
BEGIN
claim 20 rows + commit

call external gateway (có timeout, idempotency key)

BEGIN
mark rows SENT/retry + commit
~~~

Tránh:

~~~text
BEGIN
SELECT ... FOR UPDATE
HTTP request chờ 30 giây
UPDATE status
COMMIT
~~~

Mẫu sau giữ DB locks/connections trong lúc mạng chậm, tạo nguy cơ contention tương tự việc gửi mạng trong JPA callback.

### 17.3. Exactly-once không xuất hiện tự nhiên

Worker có thể gửi event thành công rồi crash trước khi đánh dấu SENT. Khi lease hết hạn, event được gửi lại. Đây là cơ chế **at-least-once**, không phải exactly-once end-to-end.

Giải pháp:

- Mỗi event có eventId ổn định.
- Consumer lưu dấu processed eventId hoặc dùng idempotent API.
- Với thanh toán, dùng idempotency key mà gateway hỗ trợ.
- Việc mark SENT kiểm tra claimed_by/token để tránh worker cũ ghi đè state sau khi lease đã được worker mới nhận.
- Retry có exponential backoff, giới hạn attempts và dead-letter/dead state.

### 17.4. Thứ tự event

Nếu một aggregate phát OrderCreated rồi OrderPaid, worker song song có thể giao event không đúng thứ tự tuyệt đối. Nếu consumer yêu cầu ordering, thiết kế per-aggregate sequence/version, partition key hoặc publisher serialization phù hợp. Không mặc định ORDER BY occurred_at trong một batch bảo đảm thứ tự gửi toàn hệ thống.

### 17.5. Outbox cũng cần monitoring

Theo dõi:

- Số event READY/CLAIMED/DEAD.
- Tuổi của event chưa gửi lâu nhất.
- Tỷ lệ gửi thành công/thất bại.
- Số lần retry, latency gateway.
- Worker crashes và lease expiry.
- Dung lượng outbox và retention sau khi SENT.

Không để outbox tích lũy hàng triệu row SENT vô hạn vì điều đó làm index, vacuum/maintenance và query claim chậm.

## 18. Domain event cần phản ánh chuyển trạng thái nghiệp vụ, không chỉ lifecycle CRUD

Một PurchaseOrder có thể trải qua:

~~~text
DRAFT -> CONFIRMED -> PAID -> SHIPPED
             \-> CANCELLED
~~~

@PostUpdate chỉ nói entity được update. Nó không phân biệt:

- Đổi địa chỉ giao hàng.
- Cập nhật ghi chú.
- Thanh toán thành công.
- Hủy đơn.

Nếu mọi @PostUpdate đều gửi OrderPaid, hệ thống sẽ sai.

### 18.1. Thay đổi domain trong method có ý nghĩa

~~~java
public class PurchaseOrder {
    public void markPaid(PaymentReference payment) {
        if (status != OrderStatus.CONFIRMED) {
            throw new IllegalStateException(
                "Trạng thái không cho phép thanh toán");
        }
        status = OrderStatus.PAID;
        paymentReference = payment.value();
    }
}
~~~

Application service biết lúc nào markPaid được gọi thành công và có thể tạo event OrderPaid cho outbox trong cùng transaction. Nó cũng có nơi để kiểm tra @Version, quyền và idempotency.

### 18.2. Không publish event ở mọi setter

Một entity được hydrate bởi Hibernate, merge detached state hoặc sửa trong batch có thể gọi nhiều setters/field access. Nếu setter tự gửi network/event, tác dụng phụ có thể xảy ra từ quá trình mapping chứ không phải hành động domain được chấp thuận.

Đặt event creation ở domain operation rõ nghĩa hoặc application service orchestration. Không biến field setter thành một gateway tích hợp.

### 18.3. Domain event trong entity có thể được lưu tạm, nhưng không gửi trực tiếp

Một aggregate có thể lưu danh sách domain events transient khi method nghiệp vụ chạy; application service lấy chúng và ghi outbox trước commit. Phải xác định lúc nào clear events, retry và duplicate handling. Không dùng @PostPersist để tự gọi publisher mạng chỉ vì entity giữ danh sách events.

## 19. Auditing: chọn công cụ đúng thay vì tự INSERT audit trong callback

Auditing gồm nhiều mức độ:

| Nhu cầu | Giải pháp thường phù hợp |
|---|---|
createdAt/updatedAt | Callback scalar, Spring Data auditing, Hibernate timestamps hoặc DB defaults/triggers |
createdBy/updatedBy | Spring Data auditing + AuditorAware/service actor |
Lịch sử phiên bản entity | Hibernate Envers hoặc audit model có chủ đích |
Mọi thay đổi do nhiều writer kể cả native SQL/ETL | Database trigger hoặc audit tại nguồn ghi chung |
Sự kiện nghiệp vụ có thể gửi ra ngoài | Domain event + transactional outbox |
Operational log không yêu cầu bền vững | Logging/telemetry tại service boundary |

### 19.1. Spring Data JPA auditing

Spring Data cung cấp AuditingEntityListener và các annotation:

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Customer {
    @Id
    private Long id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;
}
~~~

Cần cấu hình auditing, ví dụ @EnableJpaAuditing và AuditorAware phù hợp. Các annotation này không tự bảo đảm record được audit khi thay đổi bằng native SQL hoặc hệ thống ngoài; auditing listener vẫn chịu lifecycle semantics.

### 19.2. Hibernate @CreationTimestamp/@UpdateTimestamp

~~~java
@CreationTimestamp
private Instant createdAt;

@UpdateTimestamp
private Instant updatedAt;
~~~

Hibernate cung cấp các annotation timestamp với cơ chế/time source theo phiên bản. Chúng có thể phù hợp hơn một callback tự gọi Instant.now trong một số trường hợp. Không chồng nhiều cơ chế tự cập nhật cùng column (callback, auditing listener, generated DB trigger) mà không xác định rõ ai sở hữu giá trị.

### 19.3. Hibernate Envers

Envers có thể lưu các revision của entity đã được audit qua Hibernate ORM. Nó phục vụ **lịch sử state**, không giống event bus gửi thông báo. Nó cũng có phạm vi các thao tác qua ORM; không mặc định mọi native SQL/ETL bypass ORM đều tạo revision.

### 19.4. Database trigger

Nếu audit phải bao phủ nhiều writers, trigger ở database có thể là lựa chọn:

~~~sql
CREATE TRIGGER trg_orders_audit
AFTER INSERT OR UPDATE OR DELETE
ON purchase_orders
FOR EACH ROW
EXECUTE FUNCTION audit_order_row();
~~~

Phải có migration định nghĩa function audit_order_row(), schema audit và quyền. Trigger chạy trong transaction DB (theo semantics database), có thể rollback cùng transaction nhưng cũng ảnh hưởng latency/locking. Không cho trigger gọi mạng nếu muốn tránh vấn đề side effect tương tự callback.

### 19.5. Audit kỹ thuật khác event nghiệp vụ

Revision cho biết status từ CONFIRMED thành PAID; một OrderPaid event có thể cần payment reference, tenant ID, correlation ID và contract cho consumer. Không dùng audit table như queue một cách ngẫu nhiên trừ khi thiết kế rõ cơ chế delivery, idempotency và ordering.

## 20. Hibernate event listener/interceptor không tự miễn nhiễm rủi ro

Ngoài JPA callbacks, Hibernate có các extension points như EventListenerRegistry, EventType.PRE_INSERT, POST_INSERT, PRE_UPDATE, POST_UPDATE, và các interceptor/event mechanisms khác tùy phiên bản.

Ví dụ dạng minh họa:

~~~java
public class OrderPostInsertListener
        implements PostInsertEventListener {

    @Override
    public void onPostInsert(PostInsertEvent event) {
        Object entity = event.getEntity();
        if (entity instanceof PurchaseOrder order) {
            // Không gửi email, không query hay flush đệ quy ở đây.
            metrics.incrementOrderInsertObserved();
        }
    }

    @Override
    public boolean requiresPostCommitHandling(
            EntityPersister persister) {
        return false;
    }
}
~~~

Các import, registration và API callback cụ thể phải được căn với Hibernate version. Đây không phải class copy-paste hoàn chỉnh; ưu tiên dùng phiên bản SPI đã được dự án kiểm thử.

### 20.1. Listener cấp thấp có thể can thiệp sâu hơn

Hibernate SPI có thể cho phép thao tác với state arrays/event data mà JPA callbacks không hỗ trợ trực tiếp. Quyền can thiệp sâu hơn cũng có rủi ro cao hơn:

- Thứ tự flush/actions phụ thuộc Hibernate internals.
- SPI có thể thay đổi giữa các major/minor version.
- Event listener có thể được dùng ở mọi code path persistence.
- Thao tác query hoặc flush lồng nhau vẫn không trở thành an toàn chỉ vì dùng SPI.

### 20.2. Post-commit Hibernate event vẫn không phải durable queue

Một số Hibernate event interfaces có cơ chế post-commit handling. Tuy vậy callback in-process sau commit **không phải một outbox bền vững**; process vẫn có thể crash trước khi handler hoàn tất. Nếu yêu cầu tích hợp bên ngoài có tính giao dịch, dùng outbox/event log đáng tin cậy.

### 20.3. Không lạm dụng interceptor để thi hành business workflow

Interceptor thích hợp hơn cho instrumentation, extension kỹ thuật hoặc biến đổi rất có kiểm soát. Một logic “khi Order PAID thì đặt vé vận chuyển và trừ tiền” là nghiệp vụ đa hệ thống, nên nằm trong service/workflow với transaction, retry và idempotency rõ ràng.

## 21. Callback, lỗi và transaction rollback

Một callback có thể ném runtime exception:

~~~java
@PrePersist
void ensureValid() {
    if (amount == null || amount.signum() < 0) {
        throw new IllegalStateException("Amount không hợp lệ");
    }
}
~~~

Khi callback thất bại, thao tác persistence/transaction thường bị coi là thất bại và cần rollback theo JPA/Spring semantics. Đừng catch exception rồi tiếp tục sử dụng EntityManager như chưa có lỗi.

### 21.1. Không dùng callback để swallow lỗi nghiệp vụ quan trọng

~~~java
@PostPersist
void afterInsert() {
    try {
        emailGateway.send(...);
    } catch (Exception ignored) {
        // Sai: không có retry, không có record lỗi.
    }
}
~~~

Nếu email thất bại, nghiệp vụ có thể commit mà không có dấu vết để retry. Nếu throw exception, DB có thể rollback dù lỗi mạng không liên quan tới database state. Thiết kế outbox hoặc một failure-handling workflow rõ ràng hơn cả hai cách.

### 21.2. Checked vs unchecked không nên là cách điều khiển commit ở callback

Callback signature và exception handling bị ràng buộc bởi JPA/provider; Spring @Transactional rollback rules áp dụng ở transaction boundary. Không dùng một cách tùy tiện các kiểu exception để “cho DB vẫn commit” khi callback thất bại. Quan trọng hơn là **đừng đặt side effect không transactional trong callback**.

### 21.3. DB constraint vẫn là lớp bảo vệ

Callback có thể kiểm tra totalAmount >= 0, nhưng SQL native/JDBC từ hệ thống khác bypass callback. Nếu invariant phải đúng với mọi writer:

~~~sql
ALTER TABLE purchase_orders
ADD CONSTRAINT ck_orders_amount
CHECK (total_amount >= 0);
~~~

Constraint giúp giữ integrity khi callback không được gọi; migration/schema thuộc quy trình DB riêng.

## 22. Tránh callback đệ quy khi có nhiều tầng auditing

Giả sử:

~~~text
Order @PostUpdate -> ghi AuditLog
AuditLog @PostPersist -> cập nhật Statistics
Statistics @PostUpdate -> chỉnh Order
Order @PostUpdate -> ...
~~~

Đây là một vòng phụ thuộc giữa entities/listeners. Dù Hibernate chặn được flush lồng nhau, hệ thống đã khó kiểm thử và có nguy cơ gây state inconsistent.

### 22.1. Vẽ dependency graph

~~~mermaid
flowchart LR
    O[Order callback] --> A[AuditLog persist]
    A --> S[Statistics update]
    S --> O
~~~

Nếu một callback tạo write tới entity khác, rồi write đó có callback quay lại, đã có vòng lặp. Tránh ngay ở thiết kế bằng cách để application service định nghĩa thứ tự operations trong transaction.

### 22.2. Tách dữ liệu derived khỏi entity callback

Nếu Statistics là bảng tổng hợp của Order, có thể:

- Tính qua query aggregate khi đọc.
- Cập nhật bằng một application service explicit transaction.
- Dùng database trigger nếu mọi writer cần đồng bộ và semantics rõ.
- Dùng domain event/outbox và eventual consistency nếu được phép.

Không dùng vòng callback tự cập nhật để duy trì một materialized aggregate mà chưa đánh giá concurrency và consistency.

### 22.3. Derived values không tự cần write

Nếu chỉ hiển thị itemCount, có thể SELECT COUNT(OrderItem) hoặc DTO projection. Không cập nhật Order.itemCount trong @PostLoad rồi save chỉ để cache một phép đếm; nó biến read thành write ngoài dự kiến.

## 23. Giới hạn và rủi ro với @PreRemove/@PostRemove

Xóa entity có thể lan theo cascade REMOVE hoặc orphanRemoval. Một @PreRemove gọi repository để xóa thêm entity khác có thể gây:

- Thay đổi action queue trong flush.
- Thứ tự DELETE/FK không dự đoán được.
- Vòng cascade và callback đệ quy.
- Lỗi nếu một entity đang được xóa lại được yêu cầu xóa hoặc persist.

### 23.1. Dọn dữ liệu phụ trong transaction bằng mapping/SQL

Nếu OrderItem phải bị xóa cùng Order, cân nhắc:

- Cascade remove/orphanRemoval đúng aggregate semantics.
- FK ON DELETE CASCADE ở database nếu kiến trúc phù hợp.
- Application service explicit operations trước remove.

Không viết @PreRemove lặp query rồi remove từng row nếu mapping/database có thể xử lý đúng một cách rõ ràng.

### 23.2. Xóa file trên object storage

Ví dụ OrderDocument lưu S3 object key. Nếu @PostRemove xóa file S3 rồi transaction rollback, database vẫn trỏ tới file đã biến mất.

Một workflow tốt hơn:

1. Trong transaction đánh dấu Document deleted và ghi outbox event.
2. Commit DB.
3. Worker idempotent xóa object storage.
4. Ghi nhận kết quả/retention, retry nếu lỗi.

Một file deletion không có rollback tự nhiên; chọn eventual cleanup hoặc saga phù hợp thay vì callback.

## 24. Tránh network call trong validation listener

Một lớp Bean Validation có thể gọi external service để kiểm tra mã giảm giá:

~~~java
@PrePersist
void validateCoupon() {
    couponApi.check(couponCode); // Không nên.
}
~~~

Ngoài rủi ro transaction, external API có thể unavailable, chậm hoặc giới hạn rate. Với mã giảm giá cần xác minh:

- Gọi API trước khi bắt đầu write transaction nếu có thể.
- Cache reference data có policy rõ nếu thích hợp.
- Dùng conditional DB write/lock nếu số lượt sử dụng cần atomicity.
- Ghi event/outbox nếu phải xác nhận với hệ thống khác sau commit.
- Dùng saga/compensation nếu không thể atomically commit hai hệ thống.

**Validation cần nguồn dữ liệu bên ngoài** là một bước application workflow, không phải lifecycle callback thuần.

## 25. Callback và batch imports: tác động nhân lên

Khi xử lý 100.000 entities:

~~~java
for (ImportRow row : rows) {
    entityManager.persist(toEntity(row));
}
entityManager.flush();
~~~

Nếu mỗi @PrePersist có HTTP call 200 ms, riêng network có thể tiêu tốn rất nhiều thời gian và tạo áp lực lên dịch vụ ngoài. Nếu callback query COUNT theo từng row, batch dễ trở thành N+1 query.

### 25.1. Callback nhẹ và batch size

Một @PrePersist chỉ gán createdAt là O(1) cục bộ và thường phù hợp hơn. Batch service có thể định kỳ flush/clear để quản lý persistence context:

~~~java
int batchSize = 100;
for (int i = 0; i < rows.size(); i++) {
    entityManager.persist(toEntity(rows.get(i)));
    if ((i + 1) % batchSize == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
entityManager.flush();
entityManager.clear();
~~~

Flush/clear ở **service**, không ở callback. clear detach mọi entity managed của context; trong một transaction lớn chưa tạo commit từng batch. Nếu cần transaction theo batch, thiết kế các service methods được gọi qua proxy với ranh giới riêng.

### 25.2. Hibernate StatelessSession

StatelessSession không quản lý persistence context/dirty checking giống Session thông thường và thường bỏ qua nhiều lifecycle features (bao gồm các event/cascade mong đợi ở stateful Session). Do đó một import chạy bằng StatelessSession có thể không kích hoạt callback auditing như thao tác repository thông thường.

Đừng phụ thuộc callback làm bước chuẩn hóa dữ liệu bắt buộc với mọi đường ghi. Đặt invariant ở domain/data normalization pipeline và DB constraints; test riêng đường import/StatelessSession theo Hibernate version.

## 26. Bulk HQL/native SQL có thể bỏ qua entity callbacks

Ví dụ:

~~~java
entityManager.createQuery("""
    update PurchaseOrder o
    set o.status = 'CANCELLED'
    where o.createdAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

Bulk HQL update làm DML ở database, không cần hydrate và update từng managed entity, nên các @PreUpdate/@PostUpdate trên từng Order **không phải cơ chế audit chắc chắn được chạy**.

Tương tự:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE created_at < :cutoff;
~~~

được chạy từ JDBC/native SQL hoặc hệ thống khác bypass lifecycle listeners.

### 26.1. Hệ quả đối với updatedAt

Nếu updatedAt chỉ được gán ở @PreUpdate, một câu bulk UPDATE có thể không đổi updated_at. Nếu nghiệp vụ cần mọi writer cập nhật timestamp, bulk DML phải SET updated_at có chủ đích hoặc DB trigger quản lý.

### 26.2. Hệ quả với outbox

Nếu ứng dụng hủy 50.000 Orders bằng bulk UPDATE, không thể tin mỗi @PostUpdate tự phát OrderCancelled event. Workflow cần thiết kế việc tạo các outbox events tương ứng hoặc một batch-level event có contract rõ, tất cả theo transaction/data semantics phù hợp.

### 26.3. Persistence context có thể stale sau bulk DML

Một Order đã managed có thể giữ status cũ sau bulk UPDATE. Cần lựa chọn refresh, clear, context riêng hoặc transaction boundary trước khi đọc lại. Không gọi saveAndFlush trong callback để giải quyết vấn đề state lệch; flush có thể thậm chí ghi state cũ đè lên database.

## 27. Spring Data repository callbacks so với entity callbacks

Trong Spring Data JPA, việc gọi repository.save(order) không có nghĩa một sự kiện repository-level sẽ chạy tách biệt với @PrePersist. Repository chuyển lời gọi tới EntityManager, rồi lifecycle callbacks chạy theo state/flush.

Ngoài ra, một vài hệ sinh thái Spring Data có domain events từ aggregate roots, repository events hoặc transaction events. Những cơ chế đó có lifecycle/dispatch rules riêng. Không gộp tất cả vào tên chung “callback” rồi cho rằng chúng đều chạy sau commit.

### 27.1. Tách domain intent khỏi JPA lifecycle

Nên:

~~~text
Controller
  -> ApplicationService @Transactional
      -> Load/check/modify Order
      -> Persist Order và Outbox
  -> Commit
  -> Outbox worker
      -> Send message/network
~~~

Không nên:

~~~text
Controller
  -> repository.save()
      -> @PostPersist
          -> repository query
          -> save other entity
          -> send HTTP
          -> flush...
~~~

Flow thứ hai giấu mọi tác dụng phụ trong ORM internals, khiến transaction/tracing/rollback khó hiểu.

## 28. Quan sát lỗi callback trong SQL logs và tracing

Bật SQL log ở môi trường test:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger bind parameter có thể lộ email, số điện thoại, token hoặc dữ liệu thanh toán; không bật TRACE mặc định trong production.

### 28.1. Dấu hiệu callback đang làm quá nhiều việc

- Một INSERT lại kéo theo nhiều SELECT không được gọi rõ trong service.
- Một SELECT trang danh sách phát nhiều SQL phụ do @PostLoad.
- Flush/commit gây lỗi stack recursion hoặc illegal Session/flush state.
- SQL xuất hiện trong thời gian dài với connection pool exhausted.
- Network spans nằm **bên trong** database transaction span.
- Một lỗi email provider khiến database transaction rollback.
- Khi import, số HTTP calls tăng theo số entities.
- UPDATE một entity kích hoạt cascade/DELETE khác bất ngờ.

### 28.2. Hibernate Statistics

~~~java
SessionFactory sf =
    entityManagerFactory.unwrap(SessionFactory.class);
Statistics stats = sf.getStatistics();

long before = stats.getPrepareStatementCount();
// Thực thi một use case cô lập.
long after = stats.getPrepareStatementCount();

long statementDelta = after - before;
~~~

Statistics là bộ đếm cấp SessionFactory; test cần cô lập khỏi thread khác. Statement delta không nói callback nào tạo query; cần kết hợp SQL capture, application tracing và code path.

### 28.3. Timeouts và transaction duration

Theo dõi:

- Thời gian transaction, p95/p99 latency.
- DB connection pool active/queued connections.
- SQL execution time và lock wait.
- Network calls theo transaction span.
- Outbox oldest event age.
- Retry/duplicate rate.

Nếu callback kéo transaction dài, việc chỉ tăng HikariCP pool size thường che triệu chứng mà không sửa nguyên nhân.

## 29. Kiểm thử lifecycle callback và rollback

Đừng chỉ kiểm tra callback method “đã được gọi”. Phải kiểm chứng semantics khi transaction rollback, nhiều writer và concurrency.

### 29.1. Test callback scalar an toàn

Entity:

~~~java
@PrePersist
void initializeTimestamps() {
    if (createdAt == null) createdAt = Instant.now();
}
~~~

Test:

1. Bắt đầu transaction.
2. Persist entity.
3. Flush và commit.
4. Dùng EntityManager mới load entity.
5. Assert createdAt đã được lưu trong database.

Không chỉ assert field Java khác null sau persist mà bỏ qua khả năng mapping column không được insert.

### 29.2. Test @PreUpdate không chạy chỉ vì save()

1. Persist entity, commit.
2. Load managed entity, **không sửa field nào**.
3. Gọi repository.save(entity) nếu muốn tái hiện.
4. Flush và kiểm tra callback/SQL.
5. Sau đó sửa một scalar thật, flush lại và quan sát khác biệt.

Kết quả cụ thể phụ thuộc provider/version; bài học quan trọng là không xây logic nghiệp vụ dựa trên giả định save luôn kéo theo @PreUpdate.

### 29.3. Test after-commit listener không chạy khi rollback

~~~java
@Test
void doesNotSendEventWhenTransactionRollsBack() {
    assertThrows(IllegalStateException.class, () ->
        placeOrderService.placeThenFail(testCommand));

    verify(emailGateway, never())
        .sendOrderConfirmation(any(), any());
}
~~~

Các test methods/fixtures cần được triển khai. Đảm bảo service method thật sự được Spring proxy bọc transaction và listener thuộc phase AFTER_COMMIT. Nếu test method tự @Transactional rồi rollback cuối test, behavior phase có thể khác mong đợi; dùng TransactionTemplate hoặc service boundary thực tế.

### 29.4. Test after-commit listener chạy khi commit

1. Gọi service @Transactional từ test không giữ outer transaction.
2. Commit thành công.
3. Xác nhận listener được gọi theo cấu hình dispatch.
4. Nếu listener async, dùng synchronization/test await có timeout hợp lý, không ngủ một khoảng thời gian tùy tiện.
5. Kiểm tra listener nhận immutable ID/eventId, không phụ thuộc lazy entity.

### 29.5. Test outbox atomicity

Rollback:

~~~text
Order service bắt đầu transaction
Order INSERT + Outbox INSERT
Throw unchecked exception
ROLLBACK
Assert: không có Order, không có Outbox
~~~

Commit:

~~~text
Order service commit
Assert: Order tồn tại, Outbox READY tồn tại
Worker claim và gửi
Assert: Outbox SENT hoặc retry state phù hợp
~~~

Nếu transaction thành công mà outbox row không có, đó là lỗi nghiêm trọng về transaction boundary/implementation.

### 29.6. Test duplicate delivery

Giả lập:

1. Worker gửi event thành công.
2. Crash trước khi update trạng thái SENT.
3. Lease hết hạn.
4. Worker khác gửi lại cùng eventId.
5. Consumer xử lý idempotently và không thực hiện nghiệp vụ hai lần.

Đây là test cốt lõi của outbox, không chỉ test “gửi thành công một lần”.

### 29.7. Test multi-node và concurrency

Với hai workers:

- Cả hai claim outbox qua SKIP LOCKED/lease.
- Không claim cùng row đồng thời khi lease còn hợp lệ.
- Khi worker chết, event có thể được claim lại.
- Old worker không được mark SENT nếu đã mất ownership.
- Retry sau timeout không tạo tác dụng phụ trùng nếu consumer idempotent.

### 29.8. Test bulk update bypass callback

1. Cập nhật một Order qua managed entity và quan sát @PreUpdate.
2. Cập nhật cùng field qua bulk HQL/native UPDATE.
3. Xác nhận callback không phải cơ chế được gọi cho từng row của bulk update.
4. Bổ sung logic audit/outbox đúng ở workflow bulk nếu cần.

## 30. Một anti-pattern tổng hợp và cách refactor

### 30.1. Thiết kế ban đầu nguy hiểm

~~~java
@Entity
@EntityListeners(OrderListener.class)
public class PurchaseOrder {
    @Id
    private Long id;

    private String status;
}

@Component
public class OrderListener {
    @Autowired OrderRepository orders;
    @Autowired AuditRepository audits;
    @Autowired EmailGateway emails;

    @PostUpdate
    public void changed(PurchaseOrder order) {
        long paidCount = orders.countByStatus("PAID");
        audits.save(new AuditLog(order.getId(), paidCount));
        emails.sendOrderPaid(order.getId());
    }
}
~~~

Vấn đề:

1. @PostUpdate không chỉ dành cho chuyển trạng thái PAID.
2. Query bên trong callback có thể kích hoạt flush/reentrancy.
3. Save AuditLog phát sinh write trong callback.
4. Email gửi trước khi transaction commit.
5. Một Order update có thể gửi email nhiều lần.
6. Callback có thể chạy từ nhiều use cases, gồm import.
7. Injection của listener phụ thuộc integration, không nên xem mặc định portable.
8. Audit row có thể không đồng nhất với committed domain state.

### 30.2. Refactor theo application service

~~~java
@Service
public class PayOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public PayOrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void pay(Long orderId, Long trustedTenantId,
                    String paymentReference) {
        PurchaseOrder order = orders
            .findVisibleById(orderId, trustedTenantId)
            .orElseThrow();

        order.markPaid(paymentReference);

        outbox.save(OutboxEvent.orderPaid(
            UUID.randomUUID(),
            trustedTenantId,
            order.getId(),
            paymentReference
        ));
    }
}
~~~

Phương thức findVisibleById, markPaid và factory orderPaid phải được triển khai theo domain; code chỉ minh họa cấu trúc. Không cần orders.save(order) nếu order đang managed trong transaction và dirty checking áp dụng.

Ưu điểm:

- Transition PAID được định nghĩa cụ thể và có thể idempotent.
- Query và validation chạy **trước flush**, không trong callback.
- Outbox được ghi cùng transaction với Order.
- Network chạy ở worker sau commit.
- Dễ kiểm thử concurrency, rollback và quyền tenant.
- Thống kê paidCount nếu cần có thể được tính ở một reporting read model/workflow khác, không phải side effect của @PostUpdate.

### 30.3. Giữ callback tối giản

Nếu entity vẫn cần createdAt/updatedAt:

~~~java
@PrePersist
void beforePersist() {
    Instant now = Instant.now();
    if (createdAt == null) createdAt = now;
    updatedAt = now;
}

@PreUpdate
void beforeUpdate() {
    updatedAt = Instant.now();
}
~~~

Chỉ còn state scalar cục bộ, không gọi repository hoặc mạng.

## 31. Các tình huống đặc biệt cần đánh giá

### 31.1. Tạo event khi ID chỉ có sau INSERT

Với GenerationType.IDENTITY, ID thường được tạo khi INSERT chạy. Một số ứng dụng muốn có orderId để tạo outbox payload.

Những hướng có thể cân nhắc:

- Dùng ID sinh ở application (UUID/ULID) để có ID trước persist.
- Với IDENTITY, save/persist và để Hibernate lấy generated key trong transaction; kiểm tra thời điểm ID sẵn có.
- Nếu cần, gọi flush **ở application service**, không trong callback, rồi tạo outbox row cùng transaction.

Flush trong service vẫn không commit, nhưng giúp bảo đảm ID/SQL đã được tạo trong những mapping yêu cầu. Chỉ dùng khi có phụ thuộc thật, không flush mọi entity theo mặc định.

### 31.2. Tạo event sau merge detached entity

Merge có thể sao chép state cũ vào managed entity; không rõ đã có transition domain hay chưa nếu chỉ so sánh thông tin trong @PostUpdate. Một service nên load managed entity, kiểm tra status hiện tại, gọi method domain và ghi outbox khi transition thật sự xảy ra.

### 31.3. Một transaction làm nhiều lần update cùng entity

Code có thể thay đổi Order nhiều lần trước một flush. Hibernate có thể gộp thành một UPDATE, nên số callback không tương đương số business operations. Ngược lại, flush nhiều lần có thể tạo nhiều @PostUpdate cho một transaction. Không dùng callback count như bộ đếm “số lần user thực hiện hành động”.

### 31.4. Transaction retry

Nếu Spring Retry hoặc tầng orchestration retry toàn bộ use case sau deadlock, logic tạo eventId mới mỗi attempt có thể gây trùng business event nếu một attempt thực tế đã commit nhưng response bị mất. Dùng business idempotency key và transaction result reconciliation khi có thể.

### 31.5. Multi-tenant

Outbox event phải chứa tenant ID đáng tin cậy từ auth/domain context. Worker có thể chạy không có HTTP principal nên không suy ra tenant bằng ThreadLocal từ callback. Payload và consumer routing cần giữ isolation; không gửi nhầm event qua tenant khác.

### 31.6. Không đồng nhất process event với gửi network

Một domain event có thể dẫn đến nhiều actions: email, SMS, inventory reservation, analytics. Hãy định nghĩa consumer riêng, idempotency và retry policy theo từng action; không nhét tất cả vào một @PostPersist method.

## 32. Bảng triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
|---|---|---|
| Stack overflow hoặc lỗi flush reentrancy | Callback gọi saveAndFlush/flush lại | Bỏ ORM mutation khỏi callback, điều phối ở service |
| INSERT kéo theo hàng loạt SELECT | Query trong @PrePersist/@PostPersist | Tách truy vấn ra khỏi lifecycle, batch trước |
| Trang danh sách bị N+1 dù repository query đơn giản | @PostLoad truy cập lazy association | Chỉ dùng scalar local; DTO/fetch plan phù hợp |
| Email gửi dù Order không tồn tại | @PostPersist trước rollback | AFTER_COMMIT hoặc transactional outbox |
| Một update status bất kỳ gửi OrderPaid | @PostUpdate dùng thay domain transition | Ghi event tại markPaid use case |
| Một callback làm xóa OrderItems | Sửa collection + orphanRemoval trong callback | Sửa aggregate ở service trước flush |
| Giao dịch kéo dài hoặc connection pool cạn | HTTP/network chờ trong callback/transaction | Worker/outbox ngoài write transaction |
| Lỗi mail provider khiến DB rollback | Side effect throw trong lifecycle | Tách transaction DB và delivery workflow |
| Mail lỗi bị mất không có retry | Nuốt exception trong callback | Outbox retry/dead-letter/metrics |
| Spring event mất khi JVM crash sau commit | AFTER_COMMIT in-memory | Transactional outbox |
| Listener AFTER_COMMIT ghi DB nhưng dữ liệu không commit | Dùng resource transaction đã hoàn tất | REQUIRES_NEW rõ ràng hoặc ghi outbox từ transaction gốc |
| Callback dùng @Autowired null | Entity/listener không được Spring quản lý như giả định | Dùng integration được hỗ trợ hoặc service orchestration |
| Bulk UPDATE không gọi @PreUpdate từng row | Bypass entity lifecycle | Explicit bulk audit/DB trigger/outbox |
| updatedAt không thay sau native UPDATE | Timestamp chỉ được gán ở callback | SET field trong SQL hoặc DB trigger |
| Callback count không khớp số thao tác user | Flush lifecycle khác domain operation | Đếm business event trong service |
| Outbox gửi trùng | Crash sau send trước mark SENT | Idempotency key và consumer dedup |
| Outbox row kẹt CLAIMED | Worker crash không có lease | Lease expiry/claim retry |
| Order từ tenant khác xuất hiện trong event | Lấy tenant từ context sai | Tenant từ service trusted input và kiểm tra quyền |
| Lỗi uniqueness dù đã query exists trong callback | Race condition | UNIQUE DB constraint và conflict handling |

## 33. Bài thực hành

### Bài A — Quan sát callback trước commit

1. Tạo Order entity với @PrePersist và @PostPersist chỉ ghi trace nội bộ.
2. Tạo service @Transactional gọi persist/flush.
3. Sau flush, ném unchecked exception để rollback.
4. Quan sát callback đã chạy nhưng row không tồn tại sau rollback.
5. Giải thích vì sao @PostPersist không thể được dùng như AFTER_COMMIT.

### Bài B — Truy vấn trong @PostLoad gây N+1

1. Tạo 100 Order có lazy collection items.
2. Viết @PostLoad đọc items.size(), chỉ trong môi trường test.
3. Bật SQL logging, đo statements.
4. Bỏ lazy access khỏi callback.
5. Thay bằng DTO projection cho itemCount hoặc batch fetch theo use case.
6. So sánh số SQL và thời gian.

### Bài C — Đệ quy cập nhật

1. Tạo một test-only @PostUpdate gọi saveAndFlush trên cùng entity.
2. Quan sát exception hoặc hành vi không ổn định trong transaction cô lập.
3. Không chạy thử trên production DB.
4. Di chuyển mutation sang service method trước flush.
5. Xác nhận update chỉ phát sinh theo business operation.

### Bài D — Callback an toàn

1. Tạo @PrePersist đặt createdAt.
2. Tạo @PreUpdate đặt updatedAt.
3. Persist rồi load lại bằng EntityManager mới.
4. Chỉ sửa một scalar để kích hoạt update thật.
5. Assert timestamp được lưu; không gọi repository từ callback.

### Bài E — Spring transaction event

1. Tạo OrderPlacedEvent có orderId và eventId.
2. Publish ở service @Transactional.
3. Tạo listener @TransactionalEventListener(AFTER_COMMIT).
4. Test commit gọi listener, rollback không gọi.
5. Mô phỏng JVM crash giữa commit và handler (bằng thiết kế/tách thành worker test) để giải thích giới hạn in-memory delivery.

### Bài F — Transactional outbox

1. Tạo bảng outbox_events qua migration.
2. Trong cùng transaction, persist Order và Outbox event.
3. Test rollback: cả hai rows biến mất.
4. Test commit: cả hai rows tồn tại.
5. Viết worker claim batch trong transaction ngắn.
6. Gửi eventId làm idempotency key.
7. Mô phỏng crash sau gửi trước SENT và chứng minh consumer dedup.
8. Thêm backoff, lease expiry và dead-letter monitoring.

### Bài G — Auditing và bulk update

1. Gắn @PreUpdate gán updatedAt vào entity.
2. Update managed entity và xác nhận updatedAt.
3. Thực hiện bulk HQL UPDATE trên nhiều rows.
4. Xác nhận callback không thay thế được auditing cho bulk operation.
5. Viết SQL SET updated_at hoặc DB trigger nếu mọi writer đều cần timestamp.
6. Cân nhắc Envers khi mục tiêu là revision history.

### Bài H — Thiết kế event nghiệp vụ

1. Xây method markPaid với invariant trạng thái.
2. Tạo OrderPaid event trong service thay vì @PostUpdate.
3. Không tạo event khi user chỉ đổi ghi chú.
4. Tạo test hai requests markPaid đồng thời với @Version.
5. Thiết kế idempotency khi request bị retry.
6. Kiểm tra multi-tenant isolation trong event payload/consumer.

## 34. Checklist trước khi thêm callback mới

1. Callback được chọn có phải @PrePersist/@PreUpdate/@PostLoad hay event khác không?
2. Tác vụ có thật sự gắn với **lifecycle ORM** hay là một **business transition**?
3. Có gọi EntityManager, Repository hoặc truy vấn database không? Nếu có, chuyển ra ngoài.
4. Có thể kích hoạt lazy association trong callback không? Nếu có, chuyển ra ngoài.
5. Có sửa quan hệ, collection, ID, version hoặc entity khác không? Nếu có, chuyển ra ngoài.
6. Có gọi save, persist, remove, merge, flush đệ quy không? Nếu có, đây là lỗi thiết kế.
7. Có gửi HTTP/email/Kafka, ghi file hoặc gọi dịch vụ ngoài không? Nếu có, dùng after-commit/outbox.
8. Nếu transaction rollback sau callback, tác dụng phụ có được đảo ngược không?
9. Nếu callback chạy 100.000 lần trong batch, chi phí có chấp nhận được không?
10. Nếu callback chạy từ scheduler/import không có HTTP context, code có còn đúng không?
11. Callback có thể bị gọi nhiều lần cho một business operation hoặc không được gọi trong bulk DML không?
12. Scalar state được sửa có được flush đúng theo mapping không?
13. Ràng buộc dữ liệu quan trọng có được enforce ở database không?
14. Có tránh dùng @PostUpdate làm event OrderPaid/OrderCancelled chung chung không?
15. Nếu cần side effect hậu commit, AFTER_COMMIT có đủ độ tin cậy không?
16. Nếu cần delivery bền vững, outbox có retry/idempotency/lease/monitoring không?
17. Có kiểm thử rollback, concurrency, bulk updates và multi-node behavior không?
18. Có observability cho SQL count, transaction duration, external-call latency và event backlog không?

## 35. Tổng kết: callback càng ngắn, ranh giới nghiệp vụ càng rõ

~~~mermaid
flowchart TD
    A[Muốn thực hiện thao tác khi entity thay đổi] --> B{Chỉ sửa scalar local, không I/O?}
    B -->|Có| C[Callback JPA nhẹ hoặc auditing support]
    B -->|Không| D{Cần truy vấn/đổi graph trong DB?}
    D -->|Có| E[Application service @Transactional trước flush]
    D -->|Không| F{Cần gửi ra ngoài sau commit?}
    F -->|Không| G[Thiết kế domain service/read model]
    F -->|Có| H{Có cần không được mất event?}
    H -->|Không, best effort| I[TransactionalEventListener AFTER_COMMIT]
    H -->|Có| J[Transactional outbox + worker + idempotency]
~~~

Các nguyên tắc cần ghi nhớ:

1. **Lifecycle callback không phải after-commit hook.** @PostPersist, @PostUpdate và @PostRemove có thể chạy trước khi transaction thành công.
2. **Không gọi ORM query, EntityManager hoặc Repository bên trong callback** nếu muốn tránh reentrant flush, SQL bất ngờ và vi phạm giới hạn portability của JPA.
3. **Không tự gọi flush, persist, save hoặc remove lồng nhau** trong một callback đang được Hibernate xử lý.
4. **Không sửa association/collection từ callback.** Đặt thay đổi aggregate graph tại service/domain method trước flush.
5. **Không gửi mạng hoặc external side effects trước commit.** Network chậm kéo dài DB transaction, còn email/webhook đã gửi không được rollback.
6. **Callback thích hợp nhất cho việc nhẹ, cục bộ:** createdAt/updatedAt, chuẩn hóa scalar đơn giản, invariant local.
7. **Domain event biểu diễn nghiệp vụ**, không phải mọi UPDATE bất kỳ; @PostUpdate không đồng nghĩa OrderPaid.
8. **@TransactionalEventListener(AFTER_COMMIT) giúp tránh hành động trước commit nhưng không bền vững khi process crash.**
9. **Transactional outbox** ghi event cùng business row, giao tiếp ngoài transaction và dùng retry/idempotency để tránh mất hoặc xử lý trùng.
10. **Bulk HQL, native SQL và external writers có thể bỏ qua JPA entity callbacks**, nên auditing/invariants quan trọng phải có thiết kế riêng.
11. **Kiểm thử bằng transaction thật**, gồm rollback sau flush, event duplicates, lazy loading, concurrency, bulk updates và nhiều node.

Khi một hành động cần truy vấn dữ liệu khác, gửi thông báo, thay đổi quan hệ hoặc điều phối nhiều hệ thống, nó đã vượt ra ngoài trách nhiệm của callback đơn giản. Đặt hành động đó vào **application service, transaction event hoặc outbox worker** giúp Hibernate tập trung vào quản lý persistence context, còn nghiệp vụ có ranh giới transaction, khả năng retry, quan sát và kiểm thử rõ ràng.
