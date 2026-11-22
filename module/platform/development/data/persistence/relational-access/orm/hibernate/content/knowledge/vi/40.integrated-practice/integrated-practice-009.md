# Bổ sung lịch sử bằng Envers và đánh giá yêu cầu xóa mềm

## 1. Hai yêu cầu thường bị nhầm lẫn

Trong một ứng dụng quản lý đơn hàng, nhóm nghiệp vụ có thể yêu cầu:

1. Khi nhân viên sửa đơn, hệ thống phải lưu giá trị cũ, giá trị mới và người thực hiện để có thể tra cứu lịch sử.
2. Khi người dùng xóa đơn, dữ liệu không nhất thiết phải biến mất khỏi database ngay; ứng dụng cần ẩn đơn khỏi danh sách thông thường và có thể khôi phục.

Yêu cầu thứ nhất là **audit history**. Hibernate Envers lưu các revisions của những entity được đánh dấu audit.

Yêu cầu thứ hai là **soft delete**. Thay vì xóa vật lý row, ứng dụng đánh dấu row đã bị xóa. Hibernate ORM có annotation `@SoftDelete` trong các phiên bản hỗ trợ; hệ thống cũ có thể dùng cơ chế mapping khác.

Hai yêu cầu có thể xuất hiện cùng lúc nhưng trả lời hai câu hỏi khác nhau:

| Câu hỏi nghiệp vụ | Cơ chế phù hợp |
|---|---|
| Ai đã sửa đơn hàng? Giá trị cũ là gì? | Envers hoặc audit/event log |
| Đơn hàng còn hoạt động không? | Soft delete hoặc business status |
| Có thể xem dữ liệu tại một revision trước không? | Envers |
| Có thể khôi phục bản ghi đã xóa không? | Restore workflow |
| Sau thời hạn phải xóa dữ liệu thật không? | Retention, purge hoặc anonymization |

Không nên bật cả hai theo thói quen. Trước tiên cần làm rõ yêu cầu lịch sử, quyền truy cập, khả năng khôi phục và chính sách lưu giữ.

## 2. Phân biệt audit history, soft delete và physical purge

### 2.1. Audit history

Audit history trả lời câu hỏi **dữ liệu đã thay đổi như thế nào qua các lần commit?**

```text
Order #42
  Revision 10: status = DRAFT, total = 100.00
  Revision 14: status = CONFIRMED, total = 100.00
  Revision 18: status = CANCELLED, total = 100.00
```

Envers lưu snapshot theo revision, cho phép truy vấn phiên bản entity tại một revision và tìm các revisions liên quan.

### 2.2. Soft delete

Soft delete trả lời câu hỏi **entity còn được coi là đang hoạt động trong hệ thống hay không?**

```text
Before:
  id = 42
  deleted = false

After logical deletion:
  id = 42
  deleted = true
```

Row vẫn tồn tại trong bảng chính nhưng bị ẩn khỏi các truy vấn ORM thông thường theo soft-delete mapping.

### 2.3. Physical purge

Physical purge trả lời câu hỏi **dữ liệu có cần bị xóa hoặc anonymize khỏi kho lưu trữ chính sau thời hạn nào đó không?**

Soft delete không tự làm row biến mất. Envers còn có thể giữ snapshot cũ trong audit tables. Vì vậy, yêu cầu xóa dữ liệu cá nhân hoặc retention không thể được đáp ứng chỉ bằng một cờ deleted.

## 3. Đánh giá yêu cầu trước khi chọn công nghệ

Hãy biến yêu cầu thành quyết định cụ thể:

| Câu hỏi | Ví dụ câu trả lời | Ảnh hưởng thiết kế |
|---|---|---|
| Có cần xem giá trị cũ của từng field không? | Có, trong 7 năm | Audit snapshots hoặc event history |
| Có cần biết người thay đổi? | Có, user và service account | Revision metadata |
| Có cần biết lý do thay đổi? | Có, reason code | Command/audit event metadata |
| Xóa có cần khôi phục không? | Có trong 30 ngày | Soft delete + restore flow |
| Ai được xem lịch sử? | Auditor và admin cùng tenant | Authorization cho audit APIs |
| Ai được khôi phục? | Support có quyền riêng | Restore permission + conflict checks |
| Có dữ liệu nhạy cảm không? | Email, địa chỉ | Access, retention, masking |
| Sau thời hạn phải làm gì? | Anonymize một số fields | Retention workflow |
| Có writer ngoài Hibernate không? | ETL và SQL jobs | Policy cho mọi đường ghi |
| Có nhiều tenant không? | Có | Tenant-aware audit metadata và isolation |

Một quyết định kỹ thuật đúng phải phục vụ policy đã thống nhất, không chỉ làm cho remove hoặc @Audited hoạt động.

## 4. Envers nằm ở đâu trong Hibernate?

Hibernate ORM quản lý entity state và thực hiện persistence operations. Envers tích hợp với Hibernate để ghi revisions tương ứng vào audit tables.

```text
Application service
      |
      v
EntityManager / Hibernate Session
      |
      +---- INSERT / UPDATE / DELETE entity
      |
      v
Hibernate event lifecycle
      |
      +---- Envers audit listeners
      |          |
      |          v
      |     Audit entity row
      |     Revision metadata row
      |
      v
Database transaction
      |
      +---- Business table
      +---- Audit tables
      +---- Revision table
```

Trong cùng database transaction, Envers thường ghi audit data cùng thay đổi entity. Nếu transaction rollback, audit revision tương ứng cũng phải rollback. Đây là một lý do quan trọng để kiểm thử bằng transaction thực.

Envers là extension của Hibernate, không phải tính năng audit tự động của mọi JPA provider.

## 5. Thêm Hibernate Envers dependency

Maven:

```xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-envers</artifactId>
</dependency>
```

Gradle:

```kotlin
implementation("org.hibernate.orm:hibernate-envers")
```

Trong dự án Spring Boot, để BOM/dependency management quản lý version phù hợp với Hibernate ORM đang dùng. Không tự đặt một Envers version khác với Hibernate core nếu không có lý do và kiểm chứng compatibility.

Nếu không tìm thấy `org.hibernate.envers.Audited` hoặc gặp lỗi API/binary mismatch, kiểm tra dependency tree và runtime classpath.

## 6. Đánh dấu entity bằng @Audited

Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.envers.Audited;

@Entity
@Table(name = "purchase_orders")
@Audited
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private String status;
    private BigDecimal total;

    protected PurchaseOrder() {}
}
```

Khi entity được persist, update hoặc delete qua các Hibernate event paths được Envers hỗ trợ, Envers ghi lịch sử tương ứng.

Không cần tạo một entity Java riêng cho từng bảng audit nếu chỉ sử dụng Envers API. Tuy nhiên schema audit tables vẫn cần được quản lý bằng migration.

## 7. Envers tạo những bảng nào?

Giả sử entity table:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(80) NOT NULL,
    status VARCHAR(30) NOT NULL,
    total NUMERIC(19, 2) NOT NULL
);
```

Envers thường tạo audit table có tên như `purchase_orders_AUD`:

```sql
CREATE TABLE purchase_orders_AUD (
    id BIGINT NOT NULL,
    REV INTEGER NOT NULL,
    REVTYPE SMALLINT,
    order_number VARCHAR(80),
    status VARCHAR(30),
    total NUMERIC(19, 2),
    PRIMARY KEY (id, REV)
);
```

Revision table mặc định thường là `REVINFO`, chứa revision number và timestamp:

```sql
CREATE TABLE REVINFO (
    REV INTEGER PRIMARY KEY,
    REVTSTMP BIGINT
);
```

DDL trên là sơ đồ minh họa. Kiểu revision ID, tên bảng/cột, foreign keys, indexes và các chi tiết khác phụ thuộc Envers version, dialect, naming strategy và cấu hình. Hãy sinh/kiểm tra schema trên đúng version rồi quản lý bằng Flyway/Liquibase.

## 8. Revision là gì?

Một revision là một mốc thay đổi audit được Envers ghi nhận. Nhiều entity changes trong cùng một transaction có thể thuộc cùng một revision.

```text
Transaction T1
  update Order #42
  update Customer #7
  insert Payment #99
  commit

Revision 120
  Order #42 changed
  Customer #7 changed
  Payment #99 added
```

Revision không đồng nghĩa với một request HTTP, một entity ID, một lần gọi repository, một dòng SQL hay một event nghiệp vụ được phát qua broker.

Nếu transaction không tạo audit changes, không nên giả định luôn có revision mới chỉ vì transaction đã commit.

## 9. Ý nghĩa của REVTYPE

Envers dùng revision type để mô tả loại thay đổi:

| Revision type | Ý nghĩa |
|---|---|
| `ADD` | Entity được thêm |
| `MOD` | Entity được sửa |
| `DEL` | Entity bị xóa theo lifecycle audit |

Ví dụ lịch sử:

```text
id   REV   REVTYPE   status
42   10    ADD       DRAFT
42   14    MOD       CONFIRMED
42   18    DEL       CANCELLED
```

Hàng audit của deletion thường ghi revision type `DEL`; dữ liệu field trong audit row khi delete còn phụ thuộc cấu hình Envers và mapping/version. Không giả định mọi field đều được lưu theo một cách giống nhau trong mọi cấu hình.

## 10. Truy vấn lịch sử bằng AuditReader

Lấy AuditReader từ EntityManager:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.envers.AuditReader;
import org.hibernate.envers.AuditReaderFactory;

@Transactional(readOnly = true)
public PurchaseOrder loadAtRevision(
        EntityManager entityManager,
        Long orderId,
        Number revision) {

    AuditReader reader =
        AuditReaderFactory.get(entityManager);

    return reader.find(
        PurchaseOrder.class,
        orderId,
        revision);
}
```

`find()` trả về trạng thái entity tại revision được yêu cầu theo Envers semantics. Nếu entity chưa tồn tại ở thời điểm đó hoặc đã bị xóa trước thời điểm đó, kết quả có thể không có entity.

Đây là historical state, không phải managed current entity để cập nhật như một lệnh restore. Dùng nó để đọc/so sánh và map thành audit DTO.

## 11. Lấy danh sách revisions của một entity

```java
AuditReader reader = AuditReaderFactory.get(entityManager);

List<Number> revisions = reader.getRevisions(
    PurchaseOrder.class,
    orderId);
```

Ví dụ kết quả:

```text
[10, 14, 18]
```

Sau đó đọc từng revision:

```java
for (Number revision : revisions) {
    PurchaseOrder snapshot = reader.find(
        PurchaseOrder.class,
        orderId,
        revision);
    // Map snapshot thành AuditEntry DTO.
}
```

Với entity có rất nhiều revisions, không nên tải tất cả rồi serialize một response lớn. Cần phân trang/giới hạn hoặc query audit metadata phù hợp.

## 12. Lấy thời điểm và metadata của revision

Envers cung cấp revision metadata API. Có thể đọc revision entity:

```java
Object revisionEntity = reader.findRevision(
    DefaultRevisionEntity.class,
    revisionNumber);
```

Revision entity mặc định chứa revision number và timestamp. Có thể lấy ngày revision bằng API tương ứng:

```java
Date revisionDate =
    reader.getRevisionDate(revisionNumber);
```

Timestamp mặc định không tự nói ai thực hiện thay đổi hoặc request nào. Muốn có actor, tenant và reason, cần custom revision entity.

## 13. Custom revision entity để lưu người thay đổi

Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import org.hibernate.envers.DefaultRevisionEntity;
import org.hibernate.envers.RevisionEntity;

@Entity
@Table(name = "audit_revision")
@RevisionEntity(AuditRevisionListener.class)
public class AuditRevision extends DefaultRevisionEntity {

    private String actorId;
    private String tenantId;
    private String reasonCode;

    public String getActorId() { return actorId; }
    public void setActorId(String actorId) {
        this.actorId = actorId;
    }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public String getReasonCode() { return reasonCode; }
    public void setReasonCode(String reasonCode) {
        this.reasonCode = reasonCode;
    }
}
```

Ví dụ này kế thừa `DefaultRevisionEntity`, vốn đã cung cấp revision identity/timestamp. Không khai báo lại các trường revision number/timestamp nếu không có thiết kế riêng.

Listener:

```java
import org.hibernate.envers.RevisionListener;

public class AuditRevisionListener
        implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        AuditRevision revision = (AuditRevision) revisionEntity;
        revision.setActorId(AuditContext.actorId());
        revision.setTenantId(AuditContext.tenantId());
        revision.setReasonCode(AuditContext.reasonCode());
    }
}
```

`AuditContext` là abstraction do ứng dụng định nghĩa, ví dụ lấy principal đã xác thực và command metadata. Không lấy actor/tenant từ raw request field mà chưa authorize.

## 14. Listener và context propagation

Revision listener thường được gọi trong quá trình Envers tạo revision. Cần bảo đảm audit context có sẵn trước khi persistence operation/flush tạo revision.

Một request boundary có thể thiết lập context:

```java
try {
    AuditContext.set(
        authenticatedUserId,
        authorizedTenantId,
        commandReason);
    chain.doFilter(request, response);
} finally {
    AuditContext.clear();
}
```

Đây là mã khái niệm cho synchronous request processing. Với async jobs, message consumers và thread pools, context phải được truyền rõ và clear trong mọi đường thoát. Không dựa vào ThreadLocal cũ được giữ lại giữa requests.

System job có thể ghi actor là service account cùng operation name. Không để actor rỗng rồi gán một user mặc định giả.

## 15. Revision metadata không phải audit event nghiệp vụ đầy đủ

Revision entity có thể ghi actor ID, tenant ID, timestamp, reason code và correlation/request ID. Nhưng nó không tự ghi đầy đủ:

- Ai đã phê duyệt theo workflow.
- Vì sao business decision được đưa ra.
- IP/device/session details theo policy.
- Event được gửi tới hệ thống ngoài.
- Payload trước/sau theo định dạng domain-specific.

Nếu cần những thông tin này, có thể tạo bảng domain audit event hoặc transactional outbox riêng. Không nhồi mọi business history vào revision entity.

## 16. Chọn entity nào cần @Audited?

Không nhất thiết đánh dấu tất cả entities:

| Entity | Có thể audit? | Lý do |
|---|---|---|
| PurchaseOrder | Có | Cần lịch sử trạng thái và giá trị |
| CustomerProfile | Có chọn lọc | Cần truy vết thay đổi hồ sơ |
| SessionToken | Thường không audit toàn bộ | Secret và dữ liệu thay đổi liên tục |
| TemporaryCacheRow | Thường không | Dữ liệu kỹ thuật ngắn hạn |
| ReferenceCountry | Tùy yêu cầu | Ít thay đổi, có thể cần audit khi sửa |
| PaymentInstruction | Có thể cần audit mạnh | Dữ liệu tài chính và trách nhiệm |

Audit mọi thứ làm tăng dung lượng, write amplification và rủi ro lưu dữ liệu nhạy cảm quá lâu. Chọn theo requirement và retention policy.

## 17. @NotAudited cho thuộc tính không cần lịch sử

Ví dụ:

```java
@Entity
@Audited
public class CustomerProfile {

    @Id
    private Long id;

    private String displayName;

    @NotAudited
    private String transientUiPreference;
}
```

`@NotAudited` loại thuộc tính khỏi audit mapping. Cần cân nhắc:

- Nếu field thay đổi mà không được audit, lịch sử không thể tái tạo toàn bộ state.
- Không nên loại field chỉ vì audit schema khó quản lý.
- Secret/token không nên được audit nguyên văn; có thể không lưu, lưu fingerprint hoặc lưu event redacted.

Audit exclusions phải được ghi nhận trong thiết kế để auditor biết lịch sử không bao gồm field nào.

## 18. Quan hệ giữa các audited entities

Ví dụ:

```java
@Entity
@Audited
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne
    private Customer customer;
}

@Entity
@Audited
public class Customer {
    @Id
    private Long id;

    private String displayName;
}
```

Audit relation có thể lưu reference/identifier để truy vấn lịch sử association, nhưng behavior phụ thuộc relation type và Envers mapping.

Nếu target entity không được audit, Envers có thể cần cấu hình relation target auditing phù hợp, ví dụ `targetAuditMode = RelationTargetAuditMode.NOT_AUDITED` trong những trường hợp được hỗ trợ.

Không giả định việc đánh dấu Order `@Audited` tự động audit mọi entity reachable trong graph. Chọn rõ những entities có history riêng và những references chỉ cần current state.

## 19. NOT_AUDITED cho target reference data

Ví dụ Order cần audit thay đổi, nhưng Country là reference data không cần version history:

```java
@ManyToOne
@Audited(targetAuditMode = RelationTargetAuditMode.NOT_AUDITED)
private Country country;
```

Ý nghĩa là historical Order giữ association tới target không được audit theo mode này; khi đọc lịch sử, target có thể được resolve theo trạng thái hiện tại thay vì snapshot lịch sử.

Điều này phù hợp với một số reference data ổn định, nhưng không phù hợp nếu cần biết “Country label tại thời điểm tạo Order”. Trong trường hợp đó, có thể lưu snapshot label hoặc audit cả target.

## 20. Audit collection và relation tables

Một entity có:

```java
@ElementCollection
@CollectionTable(
    name = "order_tags",
    joinColumns = @JoinColumn(name = "order_id"))
@Column(name = "tag")
private Set<String> tags;
```

Nếu collection thuộc audited entity, Envers có thể tạo audit table tương ứng cho collection/relation theo mapping. Việc thêm, xóa hoặc đổi phần tử có thể tạo revision ngay cả khi scalar fields không đổi.

Kiểm tra collection có cần historical state không, audit join table có tăng nhanh không, có composite keys/unique constraints không, phần tử có identity riêng không và historical query có tải collection quá lớn không.

Với collection rất lớn hoặc quan hệ thay đổi liên tục, một domain event/association entity riêng có thể phù hợp hơn.

## 21. Audit strategy: Default và Validity

Envers có các audit strategies khác nhau để lưu/truy vấn revisions:

| Strategy | Ý tưởng | Trade-off |
|---|---|---|
| Default | Lưu row audit theo revision, tìm phiên bản có revision lớn nhất không vượt mốc cần đọc | Write tương đối đơn giản; historical lookup có thể cần truy vấn revision |
| Validity | Bổ sung thông tin revision kết thúc của phiên bản | Có thể hỗ trợ truy vấn khoảng hiệu lực; update audit row trước đó khi có revision mới |

Trong Validity strategy, các cột như REVEND hoặc timestamp tương ứng có thể được dùng để xác định khoảng thời gian một snapshot có hiệu lực. Tên/cấu hình cụ thể phụ thuộc Envers version.

Chọn strategy theo workload: tỷ lệ ghi audit, tỷ lệ truy vấn lịch sử, số revisions/entity, indexes, DBMS và retention. Không đổi strategy trên database hiện có chỉ bằng cách đổi property; cần migration audit schema và kiểm tra dữ liệu.

## 22. Query revisions và loại thay đổi

Envers có API audit query:

```java
AuditReader reader = AuditReaderFactory.get(entityManager);

List<Object[]> results = reader.createQuery()
    .forRevisionsOfEntity(
        PurchaseOrder.class,
        false,
        true)
    .add(AuditEntity.id().eq(orderId))
    .getResultList();
```

Với `selectEntitiesOnly=false`, kết quả thường có dạng chứa entity snapshot, revision entity và revision type. Cấu trúc tuple cần được đọc theo API/version đang dùng.

Có thể lọc:

```java
.add(AuditEntity.revisionType().eq(RevisionType.MOD))
```

Hoặc theo revision number:

```java
.add(AuditEntity.revisionNumber().ge(100))
```

Query audit không phải query entity hiện tại. Không trộn `AuditEntity` predicates với JPQL query thông thường.

## 23. Xem ai đã thay đổi một entity

Với custom revision entity:

```java
List<Object[]> rows = reader.createQuery()
    .forRevisionsOfEntity(
        PurchaseOrder.class,
        false,
        true)
    .add(AuditEntity.id().eq(orderId))
    .getResultList();

for (Object[] row : rows) {
    PurchaseOrder snapshot = (PurchaseOrder) row[0];
    AuditRevision revision = (AuditRevision) row[1];
    RevisionType type = (RevisionType) row[2];

    // Map snapshot + revision metadata thành DTO.
}
```

Ví dụ giả định custom revision entity đã được cấu hình và query trả tuple theo Envers API tương ứng. Không trả thẳng audit entity/revision entity qua API; map thành DTO và áp dụng quyền xem lịch sử.

## 24. Envers không tự tạo diff dễ đọc cho người dùng

Audit snapshot cho biết trạng thái entity ở mỗi revision. Nó không nhất thiết cung cấp một JSON diff business-friendly sẵn cho UI.

Có thể so sánh hai snapshots:

```java
PurchaseOrder before =
    reader.find(PurchaseOrder.class, id, previousRevision);

PurchaseOrder after =
    reader.find(PurchaseOrder.class, id, currentRevision);
```

Sau đó tạo DTO:

```java
public record FieldChange(
    String field,
    String oldValue,
    String newValue
) {}
```

Diff cần định nghĩa field nào được hiển thị, cách phân biệt null/empty, format enum/number/date, cách biểu diễn collection changes, masking PII và cách thể hiện field không được audit.

Không so sánh toString() của toàn entity; nó có thể chứa proxy, fields nhạy cảm và thứ tự không ổn định.

## 25. Soft delete với @SoftDelete

Trong Hibernate ORM có hỗ trợ built-in (được giới thiệu từ dòng Hibernate 6.4), có thể khai báo:

```java
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "purchase_orders")
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Với strategy `DELETED`, giá trị logic true biểu thị đã xóa; false biểu thị còn hoạt động. `ACTIVE` đảo ý nghĩa cột theo strategy tương ứng.

`@SoftDelete` là Hibernate-specific API, không thuộc Jakarta Persistence chuẩn. Kiểm tra Hibernate runtime version, dialect, mapping location và các restrictions trong tài liệu đúng version.

## 26. Cột soft-delete và DDL

Schema minh họa:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(80) NOT NULL,
    status VARCHAR(30) NOT NULL,
    total NUMERIC(19, 2) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE
);
```

Khi gọi:

```java
entityManager.remove(order);
```

Hibernate có thể thực hiện logical deletion bằng UPDATE indicator thay vì physical DELETE cho entity mapping được hỗ trợ. Câu SQL thực tế phụ thuộc version, strategy, version column và dialect; hãy xem SQL generated trong integration test.

Các truy vấn ORM thông thường được soft-delete mapping hỗ trợ sẽ ẩn những rows đã deleted. Native SQL/JDBC do ứng dụng viết vẫn phải tuân theo policy riêng.

## 27. Soft delete trước Hibernate 6.4

Ở những version chưa có built-in `@SoftDelete`, một cách legacy thường gặp:

```java
@Entity
@SQLDelete(
    sql = "UPDATE purchase_orders SET deleted = true WHERE id = ?")
@Where(clause = "deleted = false")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Đây là minh họa cho cách thay SQL DELETE và thêm predicate cố định. Annotation/capabilities có thể deprecated hoặc thay đổi theo version; phải kiểm tra placeholder order, `@Version`, association, bulk operations và dialect.

Không dùng cùng lúc nhiều cơ chế soft delete trên một entity mà không hiểu chúng phối hợp ra sao.

## 28. Envers và soft delete có thể cùng tham gia một lifecycle

Giả sử:

```text
PurchaseOrder #42
  active:
    status = CONFIRMED
    deleted = false

User requests deletion
  |
  v
EntityManager.remove(order)
  |
  +-- Soft-delete mapping changes logical state
  |
  +-- Envers may record deletion revision
  |
  v
Commit
```

Điểm cần kiểm chứng theo Hibernate/Envers version:

- Remove qua ORM có tạo Envers revision hay không.
- Revision type được ghi là `DEL` hay behavior cụ thể khác trong integration đó.
- Snapshot trước khi xóa có được giữ đầy đủ theo cấu hình không.
- Indicator `deleted` có được audit như property không, nhất là khi indicator do `@SoftDelete` quản lý và không phải entity property thông thường.
- Rollback có rollback cả soft-delete update và audit row không.
- Restore bằng SQL ngoài ORM có tạo Envers revision không; không nên giả định là có.

**Không coi @SoftDelete tự động là audit history.** Hãy viết test trên đúng dependency versions để xác nhận interaction thực tế, rồi quyết định có cần thêm domain audit event hay không.

## 29. Vì sao cần test Envers + @SoftDelete cùng nhau?

Một test chỉ xác nhận `deleted=true` trong bảng chính không chứng minh audit history đúng.

Một test chỉ xác nhận có audit row `REVTYPE=DEL` cũng không chứng minh entity đã bị ẩn khỏi các API/repositories thông thường.

Cần kiểm tra riêng:

1. Current table: row còn tồn tại và indicator có giá trị mong muốn.
2. ORM current read: entity đã deleted không còn xuất hiện trong luồng thông thường.
3. Audit table: revision và snapshot đúng policy.
4. Historical query: có thể đọc trạng thái trước khi xóa theo yêu cầu.
5. Rollback: không để lại soft-delete state hoặc audit revision chưa commit.
6. Restore: state hiện tại được khôi phục và lịch sử phản ánh đúng hành động restore theo policy.

## 30. Thiết kế entity có audit và soft delete

Một entity minh họa:

```java
@Entity
@Table(name = "purchase_orders")
@Audited
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal total;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only draft orders can be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }
}
```

Đây là ví dụ định hướng. Việc kết hợp `@Version`, `@Audited` và `@SoftDelete` cần được kiểm tra trên Hibernate version thực tế, đặc biệt SQL update/delete và revision behavior.

## 31. Xóa entity qua service

Một service:

```java
@Service
public class OrderCommandService {
    private final PurchaseOrderRepository orders;

    public OrderCommandService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void delete(long id) {
        PurchaseOrder order = orders.findById(id)
            .orElseThrow(OrderNotFoundException::new);

        orders.delete(order);
    }
}
```

Nếu repository gọi JPA/Hibernate remove path và entity được cấu hình soft delete, Hibernate có thể đánh dấu logic thay vì xóa vật lý. Envers integration phải được kiểm thử riêng như phần trước.

Không trả response thành công trước khi transaction commit thành công. Cần hiểu Spring transaction boundary và proxy invocation để biết lúc nào commit thật sự diễn ra.

## 32. Xóa mềm và trạng thái nghiệp vụ

Không dùng `@SoftDelete` thay mọi status:

| Trạng thái | Entity còn được truy cập thông thường? | Ý nghĩa |
|---|---|---|
| DRAFT | Có | Đang soạn |
| CONFIRMED | Có | Đã xác nhận |
| CANCELLED | Có | Hủy nghiệp vụ nhưng vẫn cần xem |
| ARCHIVED | Tùy policy | Lưu trữ, có thể vẫn cần tra cứu |
| Soft-deleted | Thường bị ẩn khỏi ORM path thông thường | Entity bị loại khỏi hoạt động |

Một đơn hàng bị hủy có thể vẫn cần xuất hiện trong lịch sử và báo cáo. Soft delete thường dành cho thao tác xóa/loại bỏ entity khỏi current view, còn status nghiệp vụ mô tả lifecycle domain.

Nếu dùng soft delete để biểu diễn CANCELLED, repository thông thường có thể không tải được đơn hàng để xem lý do hủy hoặc xử lý hoàn tiền.

## 33. Lưu deletedAt, deletedBy và reason

Indicator Boolean không tự cung cấp thời điểm xóa, người xóa, lý do hoặc request/correlation ID.

Có thể dùng một domain closure event:

```java
@Entity
public class OrderDeletionEvent {
    @Id
    @GeneratedValue
    private Long id;

    private Long orderId;
    private String actorId;
    private String reasonCode;
    private Instant occurredAt;
    private String requestId;
}
```

Service ghi event và remove entity trong cùng transaction nếu cả hai dùng cùng database transaction:

```java
@Transactional
public void deleteOrder(
        long id, String actorId, String reason) {

    PurchaseOrder order = orders.findById(id)
        .orElseThrow(OrderNotFoundException::new);

    deletionEvents.save(
        OrderDeletionEvent.create(
            id, actorId, reason, clock.instant()));

    orders.delete(order);
}
```

Đây là một lựa chọn thiết kế. Có thể dùng Envers custom revision metadata để ghi actor/tenant/reason chung cho revision; domain event riêng phù hợp khi cần event schema và query business-specific. Tránh ghi cùng metadata ở nhiều nơi mà không có nguồn sự thật rõ ràng.

## 34. Khôi phục bản ghi đã soft delete

Entity đã deleted thường bị ẩn khỏi `findById()`/repository path thông thường trong Session mới. Vì vậy, repository lookup có thể không tải được row deleted.

Không thể mặc định làm:

```java
order.setDeleted(false);
repository.save(order);
```

vì indicator có thể do Hibernate `@SoftDelete` quản lý và không được map thành property writable.

Restore cần một đường truy cập quản trị có authorization, có thể dùng native SQL/read model hoặc một API phù hợp với Hibernate version nếu có hỗ trợ.

## 35. Restore và lịch sử Envers

Restore là một thay đổi trạng thái mới trong thời gian hiện tại; nó không nên xóa revision lịch sử.

Mô hình mong muốn:

```text
Revision 10: ADD    Order #42, DRAFT
Revision 14: MOD    Order #42, CONFIRMED
Revision 18: DEL    Order #42
Revision 25: restore action (revision type depends on implementation)
```

Dòng cuối chỉ là ý tưởng minh họa. Loại revision Envers thực tế khi restore phụ thuộc cách restore được thực hiện và integration/version. Nếu restore bằng native SQL, Envers event listeners có thể không được gọi và không tự ghi revision.

Nếu yêu cầu bắt buộc có “Order restored by actor X” trong audit, hãy ghi domain event/audit record trong cùng transaction, hoặc thiết kế restore qua một Hibernate-supported lifecycle path và kiểm thử revision type/snapshot.

## 36. Restore bằng SQL có kiểm soát

Ví dụ strategy `DELETED` với cột Boolean:

```sql
UPDATE purchase_orders
SET deleted = FALSE
WHERE id = :id
  AND deleted = TRUE;
```

SQL này chỉ là thao tác database. Nó có thể bypass Envers listeners, Hibernate persistence context, optimistic version handling, L2/query cache invalidation, domain callbacks và outbox events.

Nếu phải dùng native restore:

1. Chỉ expose qua admin service có authorization.
2. Kiểm tra tenant/ownership.
3. Kiểm tra affected row count.
4. Xử lý unique conflicts và association validity.
5. Cập nhật version/audit metadata theo policy.
6. Evict/clear cache thích hợp.
7. Ghi recovery event trong cùng transaction nếu yêu cầu.

Với strategy `ACTIVE` hoặc converter Y/N, SQL phải thay đổi tương ứng. Không copy câu lệnh `deleted = FALSE` cho mọi mapping.

## 37. Unique constraints và restore conflict

Giả sử order number được phép tái sử dụng sau khi xóa:

```text
Order A: number = ORD-100, deleted = true
Order B: number = ORD-100, deleted = false

Admin tries to restore A
```

Restore A có thể vi phạm unique index active-only vì B đang sử dụng cùng key.

Các quyết định:

- Không cho tái sử dụng key sau soft delete.
- Cho phép tái sử dụng nhưng restore cần quy trình conflict.
- Đổi business key của bản ghi cũ trước restore nếu policy cho phép.
- Merge records bằng workflow được audit.

Trên PostgreSQL, active-only unique index có thể là:

```sql
CREATE UNIQUE INDEX uq_active_order_number
ON purchase_orders (order_number)
WHERE deleted = FALSE;
```

Đây là PostgreSQL-specific. Unique constraint toàn bảng vẫn giữ cả deleted rows và có semantics khác. Hãy thiết kế theo business rule, không chỉ theo tiện lợi của restore.

## 38. Quan hệ và cascade khi xóa mềm

Giả sử Order có OrderLines:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true)
private List<OrderLine> lines;
```

Xóa Order có thể cascade remove tới children theo mapping. Tuy nhiên:

- Parent có `@SoftDelete` không tự đảm bảo child cũng soft-delete.
- Child không có soft-delete mapping có thể bị physical delete khi remove cascade.
- Child có `@Audited` và Envers có thể tạo revision riêng nếu lifecycle event được xử lý.
- `orphanRemoval=true` là một lifecycle rule khác với soft-delete policy.
- Database `ON DELETE CASCADE` không tự chạy chỉ vì parent nhận UPDATE indicator.

Hãy quyết định lifecycle của từng entity. Với OrderLine là dữ liệu chứng từ, có thể cần giữ lịch sử độc lập và không muốn cascade physical delete.

## 39. Envers và cascade audit

Khi một aggregate thay đổi:

```text
Order #42
  |
  +-- status changes
  |
  +-- OrderLine #1 quantity changes
  |
  +-- OrderLine #2 removed
```

Envers có thể ghi revisions cho audited entities/relations tham gia thay đổi. Nhưng audit mapping của parent không tự bảo đảm mọi child được audit nếu child không được cấu hình tương ứng.

Kiểm tra parent/child entity nào có `@Audited`, association có được audit không, collection table có audit table riêng không, cascade remove có đúng aggregate lifecycle không và thay đổi child tạo revision như thế nào.

Một transaction có thể có cùng revision number cho nhiều audited entity changes; không suy luận mỗi row audit có revision khác nhau.

## 40. Audit và soft delete trong multi-tenancy

Nếu bảng chính có tenant_id, audit design phải giữ tenant scope:

```text
purchase_orders
  tenant_id | id | status | deleted

purchase_orders_AUD
  tenant_id | id | REV | REVTYPE | status | ...

REVINFO / custom revision
  REV | timestamp | actor | tenant
```

Các chi tiết cột/keys phụ thuộc mapping Envers và chiến lược ID. Điều quan trọng:

- Audit API phải giới hạn tenant.
- Revision metadata phải lấy tenant từ context đã authorize.
- Không chỉ lọc theo entity ID nếu ID trùng giữa tenants.
- Native SQL trên audit tables phải có tenant predicate.
- Custom revision metadata không thay thế row-level tenant isolation.

Nếu dùng schema-per-tenant/database-per-tenant, audit tables cần được migrate/provision cùng tenant schema/database và routing đúng Session.

## 41. Truy vấn lịch sử cũng là dữ liệu nhạy cảm

Audit table có thể chứa thông tin cũ mà current entity đã thay đổi hoặc đã xóa:

```text
Current customer email: new@example.test
Historical email: old@example.test
```

Người dùng không được quyền xem current profile chưa chắc được quyền xem historical snapshots. Audit API cần authorization riêng cho lịch sử, tenant/ownership checks, field-level masking, pagination/retention và logging việc đọc audit records nếu policy yêu cầu.

Không expose AuditReader trực tiếp qua controller hoặc cho client tự truyền arbitrary revision/entity ID mà không kiểm tra quyền.

## 42. Envers không tự giải quyết yêu cầu privacy erase

Khi user yêu cầu xóa dữ liệu:

- Current entity có thể bị soft-delete.
- Envers audit rows vẫn lưu các giá trị trước đó.
- Custom revision entity có thể chứa actor/tenant/request metadata.
- Logs, backups, replicas, search indexes và outbox có thể còn dữ liệu.

Vì vậy cần xác định dữ liệu nào phải giữ vì legal/accounting obligations, dữ liệu nào có thể anonymize, audit history có thể purge theo retention không, có cần giữ record tối thiểu không chứa PII và backup expiration xử lý yêu cầu xóa thế nào.

Không hứa “đã xóa hoàn toàn” chỉ vì current row được đánh dấu deleted.

## 43. Anonymization và audit snapshots

Giả sử Customer có name, email, phone và tax identifier. Nếu policy yêu cầu anonymize PII nhưng vẫn giữ Order audit history, cần xác định cách xử lý các audit snapshots chứa PII cũ.

Các lựa chọn:

- Anonymize current row và các audit rows có field tương ứng.
- Không audit một số secret/PII fields ngay từ đầu.
- Lưu reference token hóa thay cho raw data nếu nghiệp vụ cho phép.
- Giữ dữ liệu đã mask trong audit projection riêng.
- Purge toàn bộ historical data sau legal retention period.

Việc sửa audit tables trực tiếp có thể làm thay đổi khả năng chứng minh lịch sử. Đây là quyết định compliance/domain, cần có migration/audit record về thao tác anonymization và policy được phê duyệt.

## 44. Retention cho business tables và audit tables

| Kho dữ liệu | Câu hỏi |
|---|---|
| Current business table | Soft-deleted row giữ bao lâu? |
| Envers audit tables | Revisions giữ bao lâu? |
| Revision metadata | Actor/tenant metadata giữ bao lâu? |
| Domain audit/event tables | Có retention độc lập không? |
| Outbox/inbox | Event payload được purge lúc nào? |
| Search/cache | Khi nào invalidated/deleted? |
| Backups/replicas | Thời hạn hết hạn và restore policy? |

Nếu chỉ purge bảng chính mà giữ audit table vô thời hạn, dữ liệu có thể vẫn tồn tại trong historical snapshots.

Nếu purge audit trước current row, khả năng giải thích các thay đổi cũ sẽ bị giới hạn. Hãy chọn retention per data class và ghi lại quyết định.

## 45. Audit table growth và indexing

Envers tạo thêm write workload: mỗi entity change có thể tạo audit row, collection changes có thể tạo nhiều audit rows, revision table tăng theo revisions và indexes cần phục vụ history queries.

Các query thường gặp:

```text
History of one order:
  WHERE id = ?
  ORDER BY REV

Entities changed in revision:
  WHERE REV = ?

Revision range:
  REV >= ? AND REV <= ?
```

Indexes phù hợp phụ thuộc audit strategy và DBMS. Composite key (id, REV) có thể hỗ trợ một số truy vấn entity history; index theo REV có thể hỗ trợ revision-centric lookup. Đo execution plans trên dữ liệu thật.

Không thêm index mọi cột audit một cách tự động; mỗi index tăng chi phí insert và storage.

## 46. Migration schema khi bật Envers

Một quy trình an toàn:

1. Chọn entities/relations được audit.
2. Chạy schema generation trên đúng Hibernate/Envers version ở môi trường dev để xem audit table shape.
3. Review tên bảng/cột, types, keys, indexes và FK.
4. Viết Flyway/Liquibase migrations cho audit tables.
5. Triển khai schema trước hoặc theo rollout tương thích với application.
6. Bật Envers trong application.
7. Kiểm tra audit revision khi insert/update/delete.
8. Kiểm tra rollback và historical queries.

Không dùng `ddl-auto=update` trên production để tạo hàng loạt audit tables không qua review.

## 47. Migration khi entity đã có dữ liệu trước khi bật audit

Khi bật Envers hôm nay, Envers không tự tạo historical snapshots cho mọi thay đổi trước đây.

```text
Order #42 existed before Envers was enabled.

Revision 100:
  first audited update

Audit history can begin at revision 100.
It does not prove the original state at creation time.
```

Nếu cần baseline snapshot:

- Thiết kế migration/backfill audit rows có chủ đích.
- Hoặc lưu mốc “history starts at” rõ ràng.
- Không giả mạo revision dates cũ nếu không có nguồn dữ liệu chứng minh.
- Thông báo cho audit users rằng lịch sử trước thời điểm bật feature không đầy đủ.

Backfill audit tables thủ công cần tuân thủ Envers schema và revision semantics; đây là migration đặc biệt, không phải một câu INSERT tùy ý.

## 48. Cấu hình Envers hữu ích

Một số cấu hình có thể gặp:

```properties
spring.jpa.properties.org.hibernate.envers.audit_table_suffix=_AUD
spring.jpa.properties.org.hibernate.envers.revision_field_name=REV
spring.jpa.properties.org.hibernate.envers.revision_type_field_name=REVTYPE
```

Tên property và khả năng hỗ trợ cần đối chiếu Envers version. Có thể cấu hình audit table naming, default schema, revision table và audit strategy.

Không đổi tên các cột audit sau khi đã có dữ liệu mà không viết migration đồng bộ với ứng dụng và tooling truy vấn lịch sử.

## 49. Kiểm soát auditing ở field level

Có thể đánh dấu entity audit toàn bộ rồi loại một số field:

```java
@Entity
@Audited
public class UserProfile {
    @Id
    private Long id;

    private String displayName;

    @NotAudited
    private String passwordHash;
}
```

Với secret credentials, tốt hơn thường là không lưu raw secret vào audit. Nếu cần chứng minh password đã thay đổi, có thể audit event PASSWORD_CHANGED không chứa hash/password cũ.

Audit field selection phải được review cùng security/privacy team khi dữ liệu nhạy cảm.

## 50. Ghi lý do thay đổi

Một yêu cầu “lưu ai thay đổi gì và vì sao” có hai phần:

- Envers lưu entity snapshots và revision metadata.
- Application command cung cấp reason/business context.

Ví dụ command:

```java
public record ChangeOrderStatusCommand(
    long orderId,
    OrderStatus newStatus,
    String reasonCode
) {}
```

Service:

```java
@Transactional
public void changeStatus(ChangeOrderStatusCommand command) {
    AuditContext.setReasonCode(command.reasonCode());
    PurchaseOrder order = orders.findById(command.orderId())
        .orElseThrow(OrderNotFoundException::new);
    order.changeStatus(command.newStatus());
}
```

Đây là mã minh họa. Nếu revision listener đọc context khi flush/commit, context phải còn tồn tại tới lúc Envers tạo revision. Clear context ngay khi method body kết thúc có thể quá sớm tùy flush timing. Hãy quản lý context ở transaction boundary/transaction synchronization phù hợp hoặc ghi domain event rõ ràng để tránh mất reason.

Không tin reason do client gửi nếu business yêu cầu reason code được kiểm soát; validate danh mục và quyền.

## 51. Transaction boundary cho Envers

Ví dụ:

```java
@Transactional
public void confirmOrder(long id) {
    PurchaseOrder order = orders.findById(id)
        .orElseThrow(OrderNotFoundException::new);
    order.confirm();
}
```

Khi transaction commit, Hibernate flush changes và Envers có thể ghi revision tương ứng.

```text
BEGIN
  UPDATE purchase_orders ...
  INSERT INTO purchase_orders_AUD ...
  INSERT INTO audit_revision ...
ROLLBACK
```

Các thay đổi cùng transaction resource phải rollback cùng nhau. Nếu audit được gửi qua một service/database khác thay vì Envers local tables, consistency problem sẽ khác và cần outbox/distributed workflow.

Không gọi audit repository ở một transaction REQUIRES_NEW chỉ để “bảo đảm luôn có log” mà chưa quyết định có muốn audit một business change đã rollback hay không.

## 52. Không nhầm Envers với event log ngoài transaction

Envers ghi lịch sử entity state theo transaction lifecycle. Nó không tự phát message Kafka hoặc gửi notification sau commit.

Nếu cần:

```text
Order status changed
  -> persist entity
  -> Envers audit revision
  -> publish OrderConfirmed event
```

thì event publish nên có consistency strategy riêng, ví dụ transactional outbox. Không phát message trước commit rồi để consumers xử lý một thay đổi đã rollback.

| Envers | Outbox |
|---|---|
| Lịch sử entity snapshots | Message/event cần chuyển cho hệ thống khác |
| Truy vấn historical revisions | Relay/retry/consumer delivery |
| ORM event integration | Application/domain event contract |
| Không tự publish message | Được relay tới broker |

## 53. Kiểm thử Envers qua nhiều transactions

Không tạo mọi thay đổi trong một transaction nếu muốn test nhiều revisions.

Ví dụ:

```java
Long id = tx.execute(status -> {
    PurchaseOrder order = new PurchaseOrder();
    order.setOrderNumber("ORD-42");
    order.setStatus(OrderStatus.DRAFT);
    order.setTotal(new BigDecimal("100.00"));
    entityManager.persist(order);
    entityManager.flush();
    return order.getId();
});

tx.executeWithoutResult(status -> {
    PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, id);
    order.setStatus(OrderStatus.CONFIRMED);
});

tx.executeWithoutResult(status -> {
    PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, id);
    order.setTotal(new BigDecimal("125.00"));
});
```

Đây là pseudo integration test dùng `TransactionTemplate`; mỗi lần execute cần chạy trong transaction độc lập. EntityManager injection/helper phải phù hợp test setup.

Sau đó dùng AuditReader để kiểm tra revisions và historical snapshots. Đừng dùng một persistence context giữ state giữa các bước rồi nghĩ rằng đã kiểm tra DB history độc lập.

## 54. Kiểm thử rollback

Test cần chứng minh một transaction thất bại không để lại revision đã commit:

```java
assertThrows(RuntimeException.class, () ->
    tx.executeWithoutResult(status -> {
        PurchaseOrder order =
            entityManager.find(PurchaseOrder.class, id);
        order.setStatus(OrderStatus.CANCELLED);
        entityManager.flush();
        throw new RuntimeException("force rollback");
    }));
```

Trong transaction mới, kiểm tra current entity vẫn có state trước transaction, revision list không có revision của thay đổi rollback và audit table không còn row mới đã rollback.

Test này quan trọng nếu service có nhiều repositories, custom revision metadata hoặc event tables.

## 55. Kiểm thử @SoftDelete

Một test phải kiểm tra cả database và ORM visibility:

```java
Long id = tx.execute(status -> {
    PurchaseOrder order = new PurchaseOrder(...);
    entityManager.persist(order);
    entityManager.flush();
    return order.getId();
});

tx.executeWithoutResult(status -> {
    PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, id);
    entityManager.remove(order);
});

Boolean deleted = jdbcTemplate.queryForObject(
    "select deleted from purchase_orders where id = ?",
    Boolean.class,
    id);

assertEquals(Boolean.TRUE, deleted);

Boolean visible = tx.execute(status ->
    entityManager.find(PurchaseOrder.class, id) != null);

assertEquals(Boolean.FALSE, visible);
```

Ví dụ giả định strategy `DELETED`, Boolean column `deleted`, entity mapping và transaction helper đúng. Đọc ORM trong transaction mới để tránh first-level cache cũ.

## 56. Kiểm thử kết hợp Envers và soft delete

Một test tích hợp nên có các bước:

1. Persist Order và commit.
2. Đọc revision tạo mới, xác nhận snapshot DRAFT.
3. Update status thành CONFIRMED, commit.
4. Xóa mềm qua EntityManager.remove(), commit.
5. Xác nhận current row còn tồn tại và indicator đã đổi.
6. Xác nhận ORM repository thông thường không trả row.
7. Dùng AuditReader.getRevisions() lấy lịch sử.
8. Kiểm tra revision type/snapshot cho delete trên version cụ thể.
9. Dùng audit find() ở revision trước delete để xác nhận historical state.
10. Rollback một thao tác xóa khác và xác nhận không có committed audit revision.

Đừng hard-code REVTYPE=DEL cho built-in soft delete trước khi integration test đã xác nhận behavior của dependency stack thực tế.

## 57. Kiểm thử revision metadata

Nếu dùng custom revision entity, xác nhận actor ID lấy từ authenticated principal/service account, tenant ID đúng với transaction, reason code được gắn đúng thời điểm revision được tạo, background job không kế thừa context của request trước và không ghi secret/raw token vào revision metadata.

Test xen kẽ hai tenants và hai actors trong thread pool để phát hiện ThreadLocal leakage.

## 58. TestContainers với DBMS đích

Envers audit tables, composite keys, Boolean indicators, partial indexes và dialect SQL đều có thể khác giữa DBMS. Test H2 không chứng minh schema production đúng.

Ví dụ PostgreSQL Testcontainers:

```java
@Testcontainers
@SpringBootTest
class OrderAuditIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Đây là khung ví dụ; cần dependencies/imports, Flyway/Liquibase migrations và test methods. Dùng đúng major version của DBMS production nếu behavior phụ thuộc version.

## 59. API xem lịch sử nên trả DTO

Không trả trực tiếp audit entity hoặc Envers tuple:

```java
public record OrderRevisionResponse(
    Long orderId,
    Number revision,
    Instant changedAt,
    String actorId,
    String tenantId,
    String revisionType,
    String status,
    BigDecimal total
) {}
```

Service truy vấn lịch sử, kiểm tra authorization, map từng tuple thành DTO và phân trang/giới hạn. Nếu lịch sử có PII, mask fields theo role.

API có thể có:

```text
GET /api/orders/{id}/history
GET /api/orders/{id}/history/{revision}
POST /api/orders/{id}/restore
```

Đây là API shape minh họa. Restore là command có side effects và quyền riêng; không dùng GET để thay đổi state.

## 60. Audit query và pagination

Một entity có thể có hàng nghìn revisions. Tránh tải tất cả revisions rồi snapshots vào memory nếu endpoint chỉ hiển thị 20 revisions gần nhất.

Có thể dùng Envers audit query với ordering/restrictions theo API version và paginate theo revision. Với workload lớn, cân nhắc repository/read model riêng cho audit history.

Phân trang phải ổn định: order by revision rõ, dùng revision number làm cursor nếu phù hợp, không chỉ dùng timestamp nếu nhiều revisions có timestamp gần nhau và kiểm tra query plan/indexes.

## 61. Audit history và soft delete ảnh hưởng tìm kiếm thế nào?

Current repository thường chỉ trả active entities khi soft delete được cấu hình:

```java
orders.findAll();
```

Audit query là đường đọc lịch sử:

```java
reader.getRevisions(PurchaseOrder.class, id);
```

Không dùng audit tables để làm danh sách active orders. Không dùng current repository để tìm deleted records nếu mapping cố ý ẩn chúng.

| Use case | Data access |
|---|---|
| Danh sách đơn đang hoạt động | Current entity repository/projection |
| Chi tiết đơn đang hoạt động | Current entity query |
| Lịch sử thay đổi | Envers AuditReader/query |
| Danh sách đã xóa cho admin | Admin read model/query có quyền |
| Restore | Dedicated command service |
| Purge/retention | Controlled maintenance job |

## 62. Admin read path cho deleted records

Vì soft-delete mapping ẩn row, admin screen có thể cần truy cập deleted data qua một đường riêng:

- Native SQL có tenant/authorization predicates.
- Database view dành cho admin/reporting.
- Read model được cập nhật bởi deletion events.
- Một cơ chế Hibernate/version-specific nếu provider hỗ trợ include-deleted behavior.

Đừng thêm query parameter `includeDeleted=true` vào endpoint công khai mà không có permission check. Deleted data có thể nhạy cảm hơn current data.

## 63. Xử lý restore trong một service có kiểm soát

Workflow:

```text
Admin request
    |
    v
Authorize RESTORE_ORDER for tenant
    |
    v
Load deleted row via admin read path
    |
    v
Check restore window / legal hold
    |
    v
Check unique keys and relationships
    |
    v
Restore indicator in controlled transaction
    |
    +-- Write recovery event
    +-- Record audit metadata
    +-- Evict affected caches
    |
    v
Commit
    |
    v
Verify current ORM visibility
```

Nếu dùng native SQL restore, Envers không nhất thiết ghi revision. Domain recovery event có thể là nguồn lịch sử cho restore. Nếu yêu cầu restore phải tạo Envers revision, cần thiết kế đường thực thi được Envers quan sát và kiểm chứng.

## 64. Purge job phải xử lý cả current và audit data

Ví dụ retention:

```text
Soft-deleted for 30 days
   |
   +-- Restore requested? -> controlled restore
   |
   +-- Legal hold? -> retain
   |
   +-- Retention expired
           |
           v
     Anonymize/purge policy
           |
           +-- Current tables
           +-- Envers audit tables
           +-- Domain audit/event data
           +-- Search/cache/outbox as applicable
```

Purge job phải xác định dependency order và FK. Với Envers, audit rows có thể không được database cascade xóa cùng current row; cần retention process riêng theo entity ID/revision policy.

Không xóa audit rows bằng một câu DELETE chung mà không tính các entity relations và yêu cầu chứng từ.

## 65. So sánh Envers, soft delete và domain event log

| Tiêu chí | Envers | Soft delete | Domain event log |
|---|---|---|---|
| Mục tiêu | Lịch sử entity state | Ẩn entity khỏi luồng active | Ghi sự kiện nghiệp vụ |
| Lưu snapshot field | Có theo audited mapping | Không | Tùy event payload |
| Đánh dấu deleted | Có thể ghi deletion revision qua lifecycle được hỗ trợ | Có | Có thể có event Deleted |
| Ai thay đổi | Custom revision metadata | Không tự có actor | Event actor field |
| Lý do nghiệp vụ | Custom metadata/riêng | Không tự có | Có thể là field chính |
| Query as-of revision | Có API | Không | Phải replay/project events |
| Restore | Workflow riêng | Có thể đảo state theo policy | Event khôi phục mới |
| Publish integration event | Không tự làm | Không | Có thể kết hợp outbox |
| Retention | Audit policy riêng | Current row policy | Event retention riêng |

Ba cơ chế có thể cùng tồn tại nếu mỗi cơ chế có mục tiêu và retention rõ ràng.

## 66. Khi nào Envers không phải lựa chọn phù hợp?

Cân nhắc giải pháp khác nếu:

- Cần event sourcing với event là nguồn sự thật.
- Cần audit mọi SQL writer, kể cả ETL/JDBC ngoài Hibernate.
- Cần chứng cứ tamper-evident/cryptographic integrity.
- Cần lưu actor/reason/approval workflow rất chi tiết.
- Dữ liệu thay đổi với tần suất rất cao khiến snapshot audit quá tốn kém.
- Cần lịch sử across multiple databases/services như một business timeline.

Envers hữu ích cho entity history trong Hibernate, nhưng không phải hệ thống audit toàn tổ chức cho mọi nguồn dữ liệu.

Có thể kết hợp Envers với database audit, domain event log, CDC hoặc outbox tùy requirement.

## 67. Khi nào không nên dùng soft delete?

Không nên chọn soft delete mặc định nếu:

- Row chỉ là dữ liệu tạm, không có nhu cầu khôi phục.
- Database phải xóa dữ liệu ngay theo policy.
- References/unique constraints khiến deleted rows gây nhiều xung đột.
- Entity lifecycle thực chất là business status như CANCELLED/SUSPENDED.
- Mọi query/report phải đọc cả active và deleted nên visibility rule không mang lại lợi ích.
- Có yêu cầu hard delete/anonymization mà soft delete sẽ tạo hiểu nhầm.

Hard delete có thể là lựa chọn đúng khi dữ liệu không cần giữ và FK/retention policies đã được giải quyết.

## 68. Quyết định kiến trúc theo requirement

| Requirement | Thiết kế gợi ý |
|---|---|
| Chỉ cần ẩn khỏi danh sách | Soft delete có thể đủ |
| Cần khôi phục trong thời hạn | Soft delete + admin restore workflow |
| Cần biết ai sửa field nào | Envers + custom revision metadata hoặc domain audit |
| Cần lịch sử thay đổi nghiệp vụ | Domain events/audit records; Envers có thể bổ sung |
| Cần cả history và restore | Envers + soft delete + tested integration |
| Cần xóa PII sau retention | Anonymization/purge cho current + audit + copies |
| Cần audit SQL ngoài Hibernate | DB audit/CDC hoặc cơ chế bao phủ mọi writers |
| Cần event gửi sang services khác | Transactional outbox, không chỉ Envers |
| Cần lịch sử xuyên services | Event/audit architecture cấp hệ thống |

## 69. End-to-end workflow: cập nhật đơn hàng

Giả sử nhân viên xác nhận đơn:

```java
@Transactional
public void confirmOrder(
        long id, String actorId, String tenantId) {

    AuditContext.set(actorId, tenantId, "ORDER_CONFIRMED");
    PurchaseOrder order = orders.findById(id)
        .orElseThrow(OrderNotFoundException::new);
    order.confirm();
    outbox.save(OrderConfirmedEvent.from(order));
}
```

Đoạn trên nhấn mạnh thứ tự, nhưng chưa phải implementation hoàn chỉnh của context cleanup: nếu Envers tạo revision ở flush/commit sau khi method body kết thúc, clear context ngay tại đây có thể quá sớm. Hãy quản lý context ở transaction boundary/transaction synchronization phù hợp hoặc ghi actor/reason vào một mechanism có lifecycle rõ.

Kết quả mong muốn:

1. Current Order status đổi sang CONFIRMED.
2. Envers ghi revision trong cùng transaction.
3. Revision metadata có actor/tenant/reason đúng.
4. Outbox event được ghi cùng transaction.
5. Commit thành công rồi relay mới publish event.

Nếu commit thất bại, current state, Envers row và outbox row cùng rollback khi dùng chung local transaction.

## 70. End-to-end workflow: xóa đơn hàng

Command:

```java
@Transactional
public void deleteOrder(
        long id, String actorId, String reasonCode) {

    PurchaseOrder order = orders.findById(id)
        .orElseThrow(OrderNotFoundException::new);

    deletionEvents.save(
        OrderDeletionEvent.create(
            id, actorId, reasonCode, clock.instant()));

    orders.delete(order);
}
```

Kết quả cần được xác nhận:

- Current table row còn hay bị physical delete?
- Indicator deleted đổi thế nào?
- Repository current read có ẩn row?
- Envers có revision nào, revision type nào?
- Audit snapshot giữ field nào?
- Deletion event có actor/reason không?
- Transaction rollback có xóa cả event và revision không?

Không kết luận chỉ dựa trên annotation. Integration test là bằng chứng cho tổ hợp Hibernate/Envers version và mapping cụ thể.

## 71. End-to-end workflow: restore

Restore là command quản trị:

```java
public record RestoreOrderCommand(
    long orderId,
    String tenantId,
    String actorId,
    String reasonCode
) {}
```

Workflow:

1. Xác thực admin và quyền RESTORE_ORDER.
2. Đọc deleted row bằng admin path có tenant predicate.
3. Kiểm tra retention window/legal hold.
4. Kiểm tra unique constraints/association targets.
5. Thực hiện restore qua cơ chế đã thiết kế.
6. Ghi recovery event và audit metadata.
7. Đồng bộ caches/search/read models.
8. Commit và xác nhận current repository nhìn thấy entity.

Nếu restore bằng SQL, không tuyên bố Envers đã ghi revision nếu test chưa chứng minh điều đó. Domain recovery event có thể là bằng chứng bổ sung cho restore action.

## 72. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng Envers để thay soft delete | Current query vẫn thấy entity hoặc xóa vật lý | Tách audit history và visibility |
| Dùng soft delete để thay audit | Không biết giá trị cũ/ai sửa | Envers/domain audit |
| Nghĩ @Audited audit mọi writer | JDBC/ETL có thể bypass listeners | DB audit/CDC hoặc chuẩn hóa writers |
| Nghĩ @SoftDelete luôn tạo đúng Envers DEL | Revision behavior phụ thuộc integration/version | Test exact stack |
| Restore bằng native SQL rồi bỏ qua cache | Session/cache stale | Evict/clear và transaction policy |
| Audit mọi fields kể cả secret | Rủi ro lưu secret lâu dài | @NotAudited/redacted event |
| Chỉ purge current table | PII còn trong audit tables | Retention toàn bộ data copies |
| Audit API trả tuple trực tiếp | Lộ fields/contract không ổn định | Audit DTO + authorization |
| Bật ddl-auto=update để tạo audit tables | Schema production không được review | Migrations có kiểm soát |
| Không có baseline khi bật Envers | Lịch sử cũ bị hiểu sai | Ghi rõ history start/backfill |
| Coi revision là một HTTP request | Sai mô hình transaction | Hiểu revision theo audit transaction |
| Ghi reason vào ThreadLocal rồi clear sớm | Revision listener không thấy metadata | Context tới flush/commit |
| Cascade soft delete mù quáng | Child bị physical delete hoặc mất history | Xác định lifecycle từng entity |
| Không kiểm tra unique khi restore | Restore thất bại hoặc trùng business key | Restore conflict workflow |

## 73. Checklist đánh giá yêu cầu

- [ ] Entity nào cần audit và vì sao?
- [ ] Field nào bị loại khỏi audit vì secret/PII?
- [ ] Cần snapshot lịch sử hay business events?
- [ ] Cần actor, tenant, reason, request ID?
- [ ] Revision có cùng transaction với business update không?
- [ ] Xóa là cancel/status change, soft delete hay hard delete?
- [ ] Ai được restore và trong khoảng thời gian nào?
- [ ] Restore xử lý unique conflicts/relations ra sao?
- [ ] Audit history được đọc bởi role nào?
- [ ] Retention của current rows, audit rows, outbox, logs và backups là gì?
- [ ] Có native SQL/ETL writers bypass Envers không?
- [ ] Có multi-tenancy và audit isolation không?
- [ ] Có migration baseline cho dữ liệu trước khi bật Envers không?
- [ ] Có integration tests Envers + soft delete trên DBMS đích không?

## 74. Sơ đồ quyết định: cần history, soft delete hay cả hai?

```text
                    Yêu cầu xóa hoặc theo dõi thay đổi
                                  |
                                  v
                   Cần xem giá trị cũ/ai đã sửa?
                           /              \
                         CÓ                KHÔNG
                          |                  |
                          v                  v
                       Envers          Có cần giữ row để
                   hoặc domain audit   khôi phục/ẩn khỏi
                          |             current queries?
                          |              /        \
                          |            CÓ          KHÔNG
                          |             |            |
                          |             v            v
                          |        Soft delete    Hard delete
                          |             |         theo policy
                          +-------------+
                                |
                                v
                   Cần cả history và restore?
                                |
                                v
                    Envers + soft delete mapping
                    + tested lifecycle integration
                                |
                                v
                   Cần purge/anonymize sau retention?
                                |
                                v
                   Policy cho current + audit + copies
```

## 75. Tổng kết

Hibernate Envers và soft delete giải quyết hai phần khác nhau của lifecycle dữ liệu. **Envers** lưu revisions để truy vấn lịch sử entity: ai thay đổi (nếu có custom revision metadata), revision nào xảy ra và state tại một mốc. **Soft delete** giữ row nhưng đánh dấu entity không còn active để ORM queries thông thường ẩn nó. **Physical purge/anonymization** là bước riêng để đáp ứng retention và privacy.

Khi kết hợp, hãy kiểm tra đúng Hibernate/Envers versions và mapping: `@SoftDelete` có tạo revision gì, `REVTYPE` nào, snapshot nào được giữ, indicator có được audit không, rollback có rollback cả audit row không. Restore bằng native SQL có thể bypass Envers listeners, optimistic version và cache invalidation; cần recovery event hoặc một lifecycle path được kiểm chứng.

Một thiết kế vận hành được cần có revision metadata đáng tin, DTO/API audit có authorization, tenant isolation, unique/FK rules, migrations cho audit tables, indexes, retention cho cả current và historical data, cùng integration tests trên DBMS thật.

**Nguyên tắc cần nhớ:** dùng Envers để trả lời “đã thay đổi như thế nào”, soft delete để trả lời “còn hoạt động hay không”, và retention/purge để trả lời “dữ liệu được phép lưu đến khi nào”. Chỉ kết hợp chúng sau khi requirement cho cả ba câu hỏi đã rõ.
