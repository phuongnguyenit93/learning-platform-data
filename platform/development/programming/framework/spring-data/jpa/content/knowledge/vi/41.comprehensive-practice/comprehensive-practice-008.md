# Kết hợp auditing, lịch sử thay đổi và sự kiện nghiệp vụ

Một ứng dụng Spring Data JPA thường cần trả lời ba câu hỏi: bản ghi hiện tại do ai tạo hoặc sửa, dữ liệu đã thay đổi qua những phiên bản nào, và nghiệp vụ nào vừa xảy ra để các thành phần khác phản ứng. Ba nhu cầu này liên quan với nhau nhưng không cùng một cơ chế.

- **Auditing metadata** lưu thông tin tạo/sửa hiện tại trên entity, chẳng hạn người tạo, thời điểm tạo, người sửa gần nhất và thời điểm sửa gần nhất.
- **Lịch sử thay đổi (history/audit history)** lưu các phiên bản hoặc dấu vết thay đổi để có thể xem lại dữ liệu ở một thời điểm trước.
- **Domain event** mô tả một sự kiện có ý nghĩa nghiệp vụ, chẳng hạn đơn hàng được xác nhận hoặc tài khoản bị khóa.

Thiết kế tốt phối hợp cả ba trong cùng ranh giới transaction khi cần tính nhất quán. Đồng thời, cần chọn cơ chế lưu bền vững nếu lịch sử hoặc thông điệp không được phép mất.

## 1. Phân biệt ba lớp dữ liệu

Ví dụ khi một đơn hàng được xác nhận:

| Nhu cầu | Ví dụ dữ liệu | Cơ chế phù hợp |
|---|---|---|
| Ai sửa gần nhất và sửa lúc nào? | `lastModifiedBy`, `lastModifiedDate` | Spring Data JPA Auditing |
| Trạng thái và các trường của đơn hàng đã thay đổi qua những phiên bản nào? | Revision 1: NEW; revision 2: CONFIRMED | Hibernate Envers hoặc bảng history riêng |
| Hệ thống khác cần phản ứng với việc xác nhận đơn hàng | `OrderConfirmed` | Domain event và listener |
| Thông điệp phải được gửi lại sau khi process bị dừng | Bản ghi chưa publish trong outbox | Transactional outbox |

Không nên dùng một trường `lastModifiedDate` để thay thế lịch sử. Trường này chỉ cho biết lần sửa gần nhất; sau lần sửa tiếp theo, giá trị cũ bị thay thế.

Tương tự, domain event không tự động là audit history. Event có thể chỉ chứa ID và trạng thái mới, không chứa toàn bộ dữ liệu trước/sau. Ngược lại, revision của entity không nhất thiết diễn đạt ý nghĩa nghiệp vụ mà các service khác cần biết.

## 2. Lưu metadata tạo và sửa bằng Spring Data JPA Auditing

Spring Data JPA Auditing dùng entity listener để điền các trường audit khi entity đi qua vòng đời JPA. Bốn annotation phổ biến:

- `@CreatedBy`: actor tạo entity.
- `@CreatedDate`: thời điểm tạo entity.
- `@LastModifiedBy`: actor sửa gần nhất.
- `@LastModifiedDate`: thời điểm sửa gần nhất.

Ví dụ entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;
import java.util.UUID;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private UUID id;

    private String status;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;

    // constructors, getters and business methods
}
```

Bật auditing và cung cấp actor:

```java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware(CurrentActor currentActor) {
        return () -> currentActor.username();
    }
}
```

`CurrentActor` là abstraction của ứng dụng để lấy danh tính hiện tại, thường dựa trên Spring Security hoặc context của tác vụ nền. Cần có chính sách rõ cho batch job và service account; không nên để actor null hoặc dùng một tài khoản giả cho mọi thao tác nếu cần truy vết chính xác.

Một số lưu ý:

- Các trường audit phải được map vào entity và column phù hợp.
- `AuditorAware` trả về `Optional<T>`; kiểu `T` cần tương thích với kiểu trường `@CreatedBy` và `@LastModifiedBy`.
- `@EnableJpaAuditing` có tùy chọn `modifyOnCreate`; mặc định thông tin modified cũng có thể được điền khi tạo mới.
- Auditing listener chạy khi thao tác kích hoạt lifecycle callback của JPA. Bulk JPQL, native SQL, JDBC và SQL từ ứng dụng khác có thể bỏ qua listener.
- Các trường audit không phải cơ chế chống sửa đổi. Người có quyền cập nhật trực tiếp database vẫn có thể thay đổi chúng.

## 3. Lưu lịch sử entity bằng Hibernate Envers

Nếu cần xem lại trạng thái entity theo từng revision, Hibernate Envers là một lựa chọn phổ biến. Envers tích hợp với Hibernate và tạo bảng audit cho entity được đánh dấu `@Audited`.

Thêm dependency Envers tương thích với phiên bản Hibernate đang được Spring Boot quản lý. Không nên tự nâng riêng Hibernate Envers lên một phiên bản khác với Hibernate ORM trong ứng dụng.

Đánh dấu entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.envers.AuditTable;
import org.hibernate.envers.Audited;
import org.hibernate.envers.NotAudited;

@Entity
@Audited
@AuditTable(value = "purchase_order_aud")
public class PurchaseOrder {

    @Id
    private UUID id;

    private String status;

    private String customerReference;

    @NotAudited
    private String transientIntegrationCache;

    // mapping and business methods
}
```

Khi entity thay đổi qua Hibernate ORM trong transaction, Envers ghi revision vào bảng audit tương ứng. Thông thường Envers tạo bảng revision metadata (mặc định thường là `REVINFO`) và bảng audit entity với thông tin revision cùng loại thay đổi. Tên bảng, schema và cấu trúc có thể cấu hình.

Có thể truy vấn revision bằng `AuditReader`:

```java
AuditReader reader = AuditReaderFactory.get(entityManager);

List<Number> revisions =
        reader.getRevisions(PurchaseOrder.class, orderId);

PurchaseOrder oldVersion =
        reader.find(PurchaseOrder.class, orderId, revisions.get(0));
```

Đoạn code là phần minh họa cần chạy trong persistence context phù hợp và cần import `org.hibernate.envers.AuditReader`, `AuditReaderFactory`. `getRevisions()` trả danh sách revision của entity; `find()` đọc trạng thái entity tại một revision cụ thể. Với quan hệ, collection và entity liên quan, cần chọn chiến lược audit và fetch phù hợp để hiểu chính xác snapshot được lưu.

Envers hữu ích khi cần:

- Xem trạng thái entity ở revision trước.
- Truy vết ai thay đổi dữ liệu và revision xảy ra khi nào.
- So sánh dữ liệu qua các lần cập nhật.
- Hỗ trợ điều tra sự cố hoặc yêu cầu kiểm toán.

Envers không tự biến mọi thao tác database thành revision. Bulk DML, native SQL, JDBC trực tiếp, stored procedure hoặc công cụ ngoài Hibernate có thể bỏ qua cơ chế event của ORM và không tạo lịch sử Envers tương ứng. Nếu hệ thống có nhiều đường ghi, phải kiểm soát từng đường hoặc dùng audit ở tầng database.

## 4. Gắn actor vào revision history

Spring Data Auditing ghi actor vào các thuộc tính của entity. Envers có revision metadata riêng. Nếu cần biết ai tạo ra revision, có thể định nghĩa revision entity tùy chỉnh và revision listener để lấy actor từ context đáng tin cậy.

Ví dụ cấu trúc revision tùy chỉnh:

```java
@Entity
@Table(name = "audit_revision")
@RevisionEntity(AuditRevisionListener.class)
public class AuditRevision {

    @Id
    @GeneratedValue
    @RevisionNumber
    private int id;

    @RevisionTimestamp
    private long timestamp;

    private String actor;
}
```

Revision listener lấy actor tại thời điểm Hibernate tạo revision:

```java
public class AuditRevisionListener
        implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        AuditRevision revision = (AuditRevision) revisionEntity;
        revision.setActor(CurrentActorHolder.currentActor());
    }
}
```

Đây là skeleton minh họa; `CurrentActorHolder` là thành phần ứng dụng cần triển khai và phải xử lý an toàn cả request thread lẫn tác vụ nền. Cần import các annotation và interface từ `org.hibernate.envers` cùng JPA annotation thích hợp. Nếu dùng Spring Security, hãy lấy principal từ context hiện hành và xác định actor hệ thống cho job.

Để metadata nhất quán, nên dùng cùng một nguồn actor cho `AuditorAware` và Envers revision listener. Tuy nhiên, hai callback có thể chạy ở thời điểm khác nhau trong lifecycle; tránh thay đổi actor context giữa chừng trong cùng transaction.

Không đưa password, token, session ID hoặc dữ liệu định danh nhạy cảm không cần thiết vào revision. Chỉ lưu actor identifier ổn định theo chính sách bảo mật và retention của hệ thống.

## 5. Phát domain event từ aggregate root

Domain event biểu diễn một sự kiện có ý nghĩa nghiệp vụ. Ví dụ `OrderConfirmed` có thể yêu cầu gửi thông báo, cập nhật read model hoặc bắt đầu quy trình giao hàng.

Spring Data hỗ trợ event qua `AbstractAggregateRoot` hoặc hai annotation `@DomainEvents` và `@AfterDomainEventPublication`. Ví dụ dùng `AbstractAggregateRoot`:

```java
import org.springframework.data.domain.AbstractAggregateRoot;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.util.UUID;

@Entity
public class PurchaseOrder
        extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    private UUID id = UUID.randomUUID();

    private String status = "NEW";

    protected PurchaseOrder() {
    }

    public void confirm() {
        if (!"NEW".equals(status)) {
            throw new IllegalStateException(
                    "Only a new order can be confirmed");
        }

        status = "CONFIRMED";
        registerEvent(new OrderConfirmedEvent(id));
    }

    public UUID getId() {
        return id;
    }
}
```

Event nên là payload bất biến:

```java
public record OrderConfirmedEvent(UUID orderId) {
}
```

ID được tạo trước khi persist để event có thể tham chiếu aggregate ngay cả khi database chưa sinh ID. Nếu dùng ID sinh bởi database, cần thiết kế thời điểm tạo event sao cho ID đã tồn tại.

Repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
```

Spring Data publish domain event khi repository operation được hỗ trợ được gọi với aggregate root, chẳng hạn `save()` hoặc `saveAll()`. `AbstractAggregateRoot` quản lý danh sách event và xóa event sau khi publish. Với cách dùng `@DomainEvents` tự triển khai, method `@AfterDomainEventPublication` cũng chỉ báo rằng event đã được publish vào ApplicationContext; nó không chứng minh transaction đã commit.

## 6. Phối hợp auditing, Envers và domain event trong một transaction

Service là nơi phù hợp để xác định ranh giới nghiệp vụ:

```java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void confirm(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.confirm();

        // Repository save kích hoạt Spring Data domain-event publication.
        // Entity đang managed; JPA dirty checking ghi status khi flush.
        orders.save(order);
    }
}
```

Khi transaction commit thành công:

1. Service tải aggregate và thực hiện thay đổi trạng thái.
2. Spring Data repository publish domain event vào ApplicationContext.
3. Spring Data Auditing điền metadata tạo/sửa qua lifecycle callback của JPA.
4. Hibernate Envers ghi revision cho thay đổi entity.
5. Transaction commit xác nhận thay đổi entity và revision trong cùng transaction.
6. Listener `AFTER_COMMIT` được gọi sau khi commit thành công.

Auditing metadata và Envers revision đều được xử lý trong vòng đời Hibernate/JPA của transaction. Nếu transaction rollback, thay đổi entity và revision Envers trong transaction đó cũng rollback. Listener `AFTER_COMMIT` không chạy.

Có một chi tiết về thời điểm: `@LastModifiedDate` và `@LastModifiedBy` có thể được điền ở lifecycle callback khi flush. Domain event được publish tại lời gọi repository, có thể xảy ra trước flush. Vì vậy, không nên tạo event payload bằng cách đọc các trường audit vừa được JPA tự điền rồi giả định chúng đã có giá trị mới. Hãy đưa dữ liệu nghiệp vụ cần thiết vào event; nếu thực sự cần timestamp/actor của revision, hãy thiết kế một nguồn metadata rõ ràng hoặc đọc sau flush trong cùng transaction với hiểu biết về lifecycle.

Nếu entity đã managed, dirty checking thường đủ để lưu thay đổi; lời gọi `save()` không bắt buộc về mặt JPA. Tuy nhiên, Spring Data domain-event publication gắn với repository operation. Nếu dùng `AbstractAggregateRoot` để đăng ký event, hãy gọi repository operation hỗ trợ như `save()` để Spring Data thu thập và publish event.

## 7. Chỉ xử lý tác dụng phụ sau khi commit

Listener thông thường `@EventListener` chạy ngay khi event được publish. Nếu listener gửi email hoặc gọi API ngoài database rồi transaction nguồn rollback, tác dụng phụ đó không được tự hoàn tác.

Dùng `@TransactionalEventListener` khi listener phải phản ứng theo kết quả transaction:

```java
@Component
public class OrderConfirmedListener {

    private final NotificationService notifications;

    public OrderConfirmedListener(
            NotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        notifications.sendConfirmation(event.orderId());
    }
}
```

Các phase chính:

| Phase | Hành vi |
|---|---|
| `BEFORE_COMMIT` | Chạy trước khi commit; transaction vẫn có thể rollback sau đó |
| `AFTER_COMMIT` | Chạy sau commit thành công; đây là phase mặc định |
| `AFTER_ROLLBACK` | Chạy sau khi transaction rollback |
| `AFTER_COMPLETION` | Chạy sau khi transaction hoàn tất, dù commit hay rollback |

Mặc định `@TransactionalEventListener` không chạy nếu event được publish khi không có transaction. `fallbackExecution = true` cho phép chạy ngay khi không có transaction, nhưng không tạo ra một lần commit và không cung cấp bảo đảm AFTER_COMMIT.

Nếu listener AFTER_COMMIT đồng bộ cần ghi database, hãy gọi một service transaction riêng dùng `Propagation.REQUIRES_NEW`. Transaction nguồn đã commit; không dựa vào tài nguyên transaction cũ để commit thêm thay đổi.

Có thể kết hợp `@Async` với `@TransactionalEventListener(AFTER_COMMIT)` để chuyển công việc sang executor sau commit. Transaction imperative gắn với thread hiện tại và không tự truyền sang thread async. Nếu worker cần ghi database, hãy mở transaction riêng trong service được gọi từ thread đó.

## 8. Khi nào cần transactional outbox?

`@TransactionalEventListener(AFTER_COMMIT)` đảm bảo thời điểm xử lý, nhưng không bảo đảm event được lưu bền vững. Có thể xảy ra tình huống:

1. Transaction đơn hàng và Envers revision commit thành công.
2. Process dừng ngay sau commit.
3. Listener chưa kịp gửi thông báo hoặc publish message.
4. Đơn hàng đã được lưu nhưng thông điệp không được gửi.

Nếu việc mất event không được chấp nhận, dùng transactional outbox. Trong cùng transaction nghiệp vụ, ghi thêm một bản ghi outbox:

```java
@Transactional
public void confirm(UUID orderId) {
    PurchaseOrder order = orders.findById(orderId)
            .orElseThrow();

    order.confirm();
    orders.save(order);

    outboxRepository.save(
            OutboxEvent.pending(
                    UUID.randomUUID(),
                    "OrderConfirmed",
                    orderId.toString()
            )
    );
}
```

Ví dụ trên minh họa ý tưởng; `OutboxEvent.pending(...)` và entity/repository outbox là thành phần ứng dụng cần định nghĩa. Bản ghi outbox và thay đổi đơn hàng commit hoặc rollback cùng nhau.

Một worker/relay đọc các bản ghi chưa gửi, publish đến message broker rồi đánh dấu đã gửi. Thiết kế cần có:

- Event ID duy nhất để consumer phát hiện message trùng.
- Trạng thái pending/published hoặc thời điểm publish.
- Số lần thử, thời điểm thử lại và cách xử lý lỗi lâu dài.
- Cơ chế claim/lock để nhiều worker không xử lý cùng bản ghi ngoài ý muốn.
- Consumer idempotent vì giao nhận thường là at-least-once.
- Chính sách lưu giữ và dọn dẹp outbox sau khi hoàn tất.

Outbox lưu ý định phát event bền vững trong cùng transaction với dữ liệu nghiệp vụ. Nó không tự bảo đảm exactly-once ở hệ thống nhận; consumer vẫn cần idempotency.

## 9. Bulk DML và cập nhật ngoài Hibernate tạo ra khoảng trống audit

JPQL bulk `UPDATE`/`DELETE`, native SQL, JDBC, stored procedure và ứng dụng khác có thể bỏ qua JPA lifecycle listener và Hibernate Envers. Điều này tạo ra ba rủi ro:

- `@LastModifiedBy` và `@LastModifiedDate` không được tự điền.
- Envers có thể không tạo revision cho thay đổi đó.
- Domain event không tự được tạo vì aggregate method và repository event publication không chạy.

Nếu dùng bulk update, hãy cập nhật audit columns rõ ràng trong câu lệnh và thiết kế lịch sử riêng nếu cần. Bulk DML cũng không tự đồng bộ entity đang nằm trong persistence context và không tự thực hiện optimistic locking theo `@Version` như cập nhật entity thông thường.

Nếu có nhiều ứng dụng hoặc công cụ cùng ghi một bảng và yêu cầu audit phải bao phủ mọi đường ghi, hãy cân nhắc trigger, temporal table, database audit log hoặc CDC. Những cơ chế này ghi nhận ở tầng database nhưng không tự suy ra ý nghĩa nghiệp vụ như `OrderConfirmed`. Có thể kết hợp database history với domain event do ứng dụng phát ra, nhưng cần xác định nguồn có thẩm quyền cho actor, timestamp và event semantics.

## 10. Quy tắc nhất quán cho actor, thời gian và dữ liệu lịch sử

Để có thể đối chiếu giữa bản ghi hiện tại, revision và event:

- Dùng một nguồn danh tính actor đáng tin cậy cho request, batch job và tác vụ nền.
- Chuẩn hóa thời gian, thường dùng `Instant` và lưu UTC.
- Đưa aggregate ID, event ID và correlation/trace ID vào event hoặc metadata phù hợp.
- Không sửa revision cũ để “sửa lại lịch sử”; nếu cần điều chỉnh, tạo một thay đổi mới có lý do và actor.
- Quy định rõ trường nào được Envers audit, trường nào dùng `@NotAudited`.
- Bảo vệ bảng audit và outbox bằng quyền truy cập riêng, retention và backup phù hợp.
- Tránh lưu bí mật, token hoặc dữ liệu cá nhân không cần thiết trong event payload và history.
- Định nghĩa chính sách lưu giữ/xóa dữ liệu lịch sử phù hợp nghĩa vụ pháp lý và nghiệp vụ.

Nếu cần lịch sử trước/sau có ngữ nghĩa riêng, ví dụ “ai đổi hạn mức từ 10 triệu lên 15 triệu vì lý do nào”, có thể tạo bảng business audit log bổ sung. Envers lưu trạng thái revision; business audit log lưu lý do và ngữ cảnh nghiệp vụ. Không nên nhồi toàn bộ nội dung nhạy cảm vào domain event chỉ để tiện debug.

## 11. Kiểm thử tích hợp ba cơ chế

Nên kiểm thử trên database thật hoặc Testcontainers với đúng loại engine dự kiến triển khai, đặc biệt nếu dùng Envers, trigger, native SQL hoặc outbox.

Các kịch bản quan trọng:

1. **Tạo entity:** `createdBy`/`createdDate` được điền; Envers tạo revision; event được publish và listener AFTER_COMMIT chạy sau commit.
2. **Cập nhật entity:** `lastModifiedBy`/`lastModifiedDate` thay đổi; Envers ghi revision mới; event phản ánh đúng hành động nghiệp vụ.
3. **Rollback:** entity và Envers revision của transaction rollback; listener AFTER_COMMIT không chạy; listener AFTER_ROLLBACK có thể chạy.
4. **Không có transaction:** listener AFTER_COMMIT mặc định không chạy; kiểm thử riêng nếu bật `fallbackExecution`.
5. **Process/event failure:** outbox vẫn tồn tại sau khi transaction commit; worker có thể retry; consumer xử lý message trùng an toàn.
6. **Bulk/native/JDBC:** xác minh auditing và Envers không tự ghi như đường Hibernate thông thường; kiểm tra cơ chế audit thay thế.
7. **Actor context:** request người dùng, batch job và async worker ghi đúng actor theo contract.
8. **Quyền và retention:** người dùng nghiệp vụ không thể tùy ý sửa/xóa lịch sử audit hoặc đọc dữ liệu không được phép.

Không chỉ kiểm tra method được gọi. Hãy đọc lại entity, revision và outbox từ transaction/persistence context mới để xác nhận dữ liệu đã commit đúng.

## 12. Chọn kiến trúc theo yêu cầu

| Yêu cầu | Thiết kế đề xuất |
|---|---|
| Chỉ cần người tạo và người sửa gần nhất | Spring Data JPA Auditing |
| Cần xem lại snapshot entity theo revision | Hibernate Envers |
| Cần biết nghiệp vụ nào vừa xảy ra | Domain event |
| Chỉ cần listener chạy sau commit trong cùng ứng dụng | `@TransactionalEventListener(AFTER_COMMIT)` |
| Cần xử lý nền sau commit | AFTER_COMMIT kết hợp `@Async`, có giám sát lỗi |
| Không được mất thông điệp khi process dừng | Transactional outbox và relay bền vững |
| Có nhiều đường ghi ngoài Hibernate | Trigger, temporal/audit table hoặc CDC; bổ sung event nghiệp vụ ở nơi hiểu được ý nghĩa nghiệp vụ |

## Kết luận

Spring Data JPA Auditing trả lời ai tạo hoặc sửa bản ghi hiện tại; Envers hoặc bảng history lưu các revision; domain event mô tả hành động nghiệp vụ để thành phần khác phản ứng. Đặt thay đổi entity, revision và outbox trong cùng transaction khi cần tính nhất quán. Dùng AFTER_COMMIT cho tác dụng phụ chỉ được thực hiện sau khi dữ liệu đã lưu thành công, và dùng transactional outbox khi thông điệp phải được giao bền vững. Hãy kiểm thử cả rollback, bulk DML, actor context và đường ghi ngoài Hibernate để biết chính xác phần nào được ghi nhận.