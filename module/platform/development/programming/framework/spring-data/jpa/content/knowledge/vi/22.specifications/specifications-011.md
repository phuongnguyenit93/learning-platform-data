# Giới hạn thao tác xóa theo Specification và tác động của bulk delete trong Spring Data JPA

Spring Data JPA cho phép dùng Specification để xây dựng điều kiện xóa động mà không cần viết một repository method cho từng tổ hợp bộ lọc. Phương thức `delete(spec)` sử dụng JPA CriteriaDelete và thực hiện bulk delete trực tiếp tại database.

Bulk delete rất hiệu quả khi cần xóa nhiều hàng theo cùng một điều kiện, nhưng nó có ngữ nghĩa khác với việc gọi `EntityManager.remove(entity)` cho từng entity. Nó không đồng bộ persistence context, không chạy lifecycle callback của từng entity và không thực hiện cascade REMOVE/orphan removal theo quan hệ JPA. Vì vậy, chọn API xóa phải dựa trên cả hiệu năng lẫn những hành vi nghiệp vụ cần được giữ lại.

Bài này trình bày cách dùng Specification để giới hạn tập dữ liệu được xóa, khác biệt API giữa Spring Data JPA 3.5 và 4.x, giới hạn của CriteriaDelete, tác động của bulk delete và cách kiểm thử một thao tác xóa an toàn.

## 1. Specification trong thao tác xóa

Specification biểu diễn một predicate trên entity bằng JPA Criteria API. Repository cần mở rộng `JpaSpecificationExecutor` để thực thi các điều kiện đó:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                JpaSpecificationExecutor<PurchaseOrder> {
}
~~~

Với truy vấn đọc, ta thường gọi:

~~~java
List<PurchaseOrder> orders = repository.findAll(specification);
~~~

Với thao tác xóa theo điều kiện, Spring Data JPA cung cấp:

~~~java
long deleted = repository.delete(specification);
~~~

Phương thức này tạo CriteriaDelete và chuyển điều kiện Specification thành WHERE của câu DELETE. Nó trả về số hàng entity bị xóa theo điều kiện. Các entity phù hợp không cần được tải thành object Java trước khi database xóa chúng.

Ví dụ về nghiệp vụ: chỉ xóa đơn hàng đã hủy, thuộc đúng tenant và được tạo trước một mốc thời gian. Ba điều kiện này phải cùng có mặt trong predicate:

~~~sql
DELETE FROM purchase_orders
WHERE tenant_id = ?
  AND status = 'CANCELLED'
  AND created_at < ?
~~~

Đây là SQL minh họa ngữ nghĩa. SQL thực tế do JPA provider và database dialect sinh ra.

## 2. Khác biệt API giữa Spring Data JPA 3.5 và 4.x

Cần đối chiếu phiên bản Spring Data JPA mà dự án đang dùng. Tên và kiểu Specification cho thao tác xóa thay đổi ở dòng 4.x.

### 2.1. Spring Data JPA 3.5: delete(Specification<T>)

Trong Spring Data JPA 3.5, `JpaSpecificationExecutor` có phương thức:

~~~java
long delete(Specification<T> spec);
~~~

Ví dụ:

~~~java
Specification<PurchaseOrder> belongsToTenant(UUID tenantId) {
    return (root, query, cb) ->
            cb.equal(root.get("tenantId"), tenantId);
}

Specification<PurchaseOrder> hasStatus(OrderStatus status) {
    return (root, query, cb) ->
            cb.equal(root.get("status"), status);
}

Specification<PurchaseOrder> createdBefore(Instant cutoff) {
    return (root, query, cb) ->
            cb.lessThan(root.get("createdAt"), cutoff);
}
~~~

Ghép các điều kiện:

~~~java
Specification<PurchaseOrder> target =
        Specification.allOf(
                belongsToTenant(tenantId),
                hasStatus(OrderStatus.CANCELLED),
                createdBefore(cutoff)
        );

long deleted = repository.delete(target);
~~~

Điểm đặc biệt của API 3.5 là `Specification.toPredicate` nhận tham số `CriteriaQuery<?> query`, nhưng khi được gọi từ `delete(spec)`, tham số query là null. Spring Data tạo CriteriaDelete; CriteriaDelete không phải CriteriaQuery.

Do đó, Specification dùng cho xóa chỉ nên tạo predicate từ `root` và `CriteriaBuilder`. Không gọi các thao tác dành riêng cho truy vấn SELECT như:

- `query.distinct(true)`.
- `query.orderBy(...)`.
- `query.groupBy(...)` hoặc `query.having(...)`.
- `root.fetch(...)` để tải quan hệ.
- `query.subquery(...)`, vì đối số query ở đây là null.

Một Specification vốn được viết cho `findAll` có thể hoạt động với `delete` nếu nó chỉ tạo predicate đơn giản. Nếu nó sửa cấu trúc CriteriaQuery hoặc tạo fetch join, dùng lại cho delete có thể gây NullPointerException hoặc lỗi Criteria API.

### 2.2. Spring Data JPA 4.x: PredicateSpecification và DeleteSpecification

Spring Data JPA 4.0 bổ sung các kiểu Specification gắn với loại query:

- `PredicateSpecification<T>`: predicate không phụ thuộc loại query.
- `Specification<T>`: predicate cho truy vấn đọc.
- `UpdateSpecification<T>`: điều kiện và nội dung cho CriteriaUpdate.
- `DeleteSpecification<T>`: predicate cho CriteriaDelete.

Với điều kiện đơn giản, `PredicateSpecification` có thể dùng trực tiếp:

~~~java
PredicateSpecification<PurchaseOrder> belongsToTenant =
        (from, cb) ->
                cb.equal(from.get("tenantId"), tenantId);

PredicateSpecification<PurchaseOrder> isCancelled =
        (from, cb) ->
                cb.equal(from.get("status"), OrderStatus.CANCELLED);

PredicateSpecification<PurchaseOrder> createdBefore =
        (from, cb) ->
                cb.lessThan(from.get("createdAt"), cutoff);

long deleted = repository.delete(
        belongsToTenant.and(isCancelled).and(createdBefore)
);
~~~

Nếu muốn biểu đạt rõ đây là điều kiện xóa, chuyển PredicateSpecification thành DeleteSpecification:

~~~java
DeleteSpecification<PurchaseOrder> deleteSpec =
        DeleteSpecification.where(belongsToTenant)
                .and(isCancelled)
                .and(createdBefore);

long deleted = repository.delete(deleteSpec);
~~~

`DeleteSpecification.toPredicate` nhận trực tiếp `Root<T>`, `CriteriaDelete<T>` và `CriteriaBuilder`. Nhờ đó, code không phải giả định rằng tham số CriteriaQuery có tồn tại.

`PredicateSpecification` phù hợp với predicate chỉ đọc thuộc tính từ root và tạo biểu thức. `DeleteSpecification` phù hợp khi cần làm việc với API CriteriaDelete, chẳng hạn tạo subquery cho một điều kiện liên quan. Cả hai đều thực hiện bulk delete khi truyền vào `JpaSpecificationExecutor.delete`.

### 2.3. Bảng đối chiếu

| Phiên bản | API xóa | Tham số predicate | Ghi chú |
|---|---|---|---|
| Spring Data JPA 3.5 | `delete(Specification<T>)` | `Root`, `CriteriaQuery` (null trong đường xóa), `CriteriaBuilder` | Chỉ dùng phần tạo predicate; không truy cập CriteriaQuery |
| Spring Data JPA 4.x | `delete(PredicateSpecification<T>)` | `From`, `CriteriaBuilder` | Predicate độc lập loại query |
| Spring Data JPA 4.x | `delete(DeleteSpecification<T>)` | `Root`, `CriteriaDelete`, `CriteriaBuilder` | API dành riêng cho CriteriaDelete |

Đừng copy code DeleteSpecification vào dự án còn dùng Spring Data JPA 3.5. Hãy kiểm tra dependency thực tế trong Maven/Gradle trước khi chọn ví dụ.

## 3. Thiết kế Specification xóa có điều kiện bắt buộc

Xóa là thao tác phá hủy dữ liệu. Điều kiện bắt buộc như tenant, chủ sở hữu hoặc phạm vi thời gian phải luôn được đưa vào predicate. Không nên để bộ lọc tùy chọn từ request quyết định toàn bộ phạm vi xóa.

Ví dụ entity đơn hàng:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private UUID tenantId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @Version
    private long version;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            UUID tenantId,
            OrderStatus status,
            Instant createdAt) {
        this.tenantId = tenantId;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public UUID getTenantId() {
        return tenantId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED,
    COMPLETED
}
~~~

Các Specification chỉ tạo điều kiện:

~~~java
public final class PurchaseOrderSpecs {

    private PurchaseOrderSpecs() {
    }

    public static Specification<PurchaseOrder> belongsToTenant(
            UUID tenantId) {
        return (root, query, cb) ->
                cb.equal(root.get("tenantId"), tenantId);
    }

    public static Specification<PurchaseOrder> hasStatus(
            OrderStatus status) {
        return (root, query, cb) ->
                cb.equal(root.get("status"), status);
    }

    public static Specification<PurchaseOrder> createdBefore(
            Instant cutoff) {
        return (root, query, cb) ->
                cb.lessThan(root.get("createdAt"), cutoff);
    }
}
~~~

Service kiểm tra tham số bắt buộc và thực thi trong transaction:

~~~java
@Service
public class PurchaseOrderCleanupService {

    private final PurchaseOrderRepository orders;
    private final EntityManager entityManager;

    public PurchaseOrderCleanupService(
            PurchaseOrderRepository orders,
            EntityManager entityManager) {
        this.orders = orders;
        this.entityManager = entityManager;
    }

    @Transactional
    public long deleteOldCancelledOrders(
            UUID tenantId,
            Instant cutoff) {

        Objects.requireNonNull(tenantId, "tenantId is required");
        Objects.requireNonNull(cutoff, "cutoff is required");

        Specification<PurchaseOrder> target =
                Specification.allOf(
                        PurchaseOrderSpecs.belongsToTenant(tenantId),
                        PurchaseOrderSpecs.hasStatus(
                                OrderStatus.CANCELLED),
                        PurchaseOrderSpecs.createdBefore(cutoff)
                );

        entityManager.flush();

        long deleted = orders.delete(target);

        entityManager.clear();

        return deleted;
    }
}
~~~

Ví dụ trên dùng API Spring Data JPA 3.5. `EntityManager.flush()` đẩy các thay đổi đang chờ xuống database trước khi chạy bulk delete. `clear()` detach toàn bộ entity khỏi persistence context sau khi xóa để caller không tiếp tục dùng các object có thể đã lỗi thời.

`clear()` tác động đến tất cả entity đang managed trong persistence context, không chỉ PurchaseOrder. Vì vậy, nên đặt thao tác xóa hàng loạt trong một service/transaction chuyên biệt. Nếu transaction đang giữ các entity khác còn cần cập nhật, đừng clear tùy tiện; hãy cân nhắc persistence context mới hoặc tải lại các entity cần dùng.

Nếu dự án dùng Spring Data JPA 4.x, thay phần khai báo Specification bằng PredicateSpecification/DeleteSpecification như phần trước; các nguyên tắc transaction và persistence context vẫn giữ nguyên.

## 4. Giới hạn của CriteriaDelete

`CriteriaDelete` biểu diễn một thao tác DELETE trực tiếp trên database. Nó không phải một CriteriaQuery dùng để lấy danh sách entity.

Các giới hạn quan trọng:

1. Một CriteriaDelete có một root entity làm đối tượng đích.
2. Không có SELECT list để chọn DTO hoặc entity graph.
3. Không có fetch plan để tải association.
4. Không có cơ chế phân trang kết quả xóa như Pageable.
5. Không dùng ORDER BY, GROUP BY hoặc HAVING như một truy vấn SELECT thông thường.
6. Kết quả là số hàng bị ảnh hưởng, không phải danh sách entity đã bị xóa.
7. Persistence context không được tự đồng bộ với kết quả xóa.

Điều kiện thường dựa trên thuộc tính của root, ví dụ tenant, trạng thái, ngày tạo hoặc khóa chính. Khi điều kiện liên quan đến entity khác phức tạp, có thể cần biểu thức đường dẫn hoặc subquery. Với Spring Data JPA 4.x, DeleteSpecification cung cấp đối tượng CriteriaDelete để xây dựng subquery. Với API 3.5, tham số CriteriaQuery trong Specification bị null ở đường delete; nếu cần CriteriaDelete phức tạp, hãy viết custom repository method nhận CriteriaDelete trực tiếp thay vì cố dùng lại logic SELECT.

Ví dụ khung custom repository cho một thao tác CriteriaDelete:

~~~java
@Transactional
public long deleteByCustomCriteria(
        UUID tenantId,
        Instant cutoff) {

    CriteriaBuilder cb = entityManager.getCriteriaBuilder();
    CriteriaDelete<PurchaseOrder> delete =
            cb.createCriteriaDelete(PurchaseOrder.class);

    Root<PurchaseOrder> root = delete.from(PurchaseOrder.class);

    delete.where(
            cb.equal(root.get("tenantId"), tenantId),
            cb.equal(root.get("status"), OrderStatus.CANCELLED),
            cb.lessThan(root.get("createdAt"), cutoff)
    );

    return entityManager.createQuery(delete).executeUpdate();
}
~~~

Đây là mã minh họa phần custom repository. Trong code production, vẫn cần validate tham số bắt buộc, giới hạn tenant, transaction, kiểm soát persistence context và test trên provider thực tế.

## 5. Không có điều kiện không được đồng nghĩa với xóa toàn bộ

Đây là lỗi nguy hiểm nhất khi xây dựng bộ lọc động.

Trong Spring Data JPA 3.5, `delete(null)` có thể được hiểu là xóa mọi entity thuộc loại repository. Trong các phiên bản mới, `Specification.unrestricted()`, `PredicateSpecification.unrestricted()` hoặc `DeleteSpecification.unrestricted()` là điều kiện không tham gia vào WHERE. Khi không còn predicate nào, thao tác xóa có thể áp dụng cho toàn bộ bảng entity đích.

Đặc biệt, API `DeleteSpecification.allOf(...)` và `anyOf(...)` trả về unrestricted khi danh sách đầu vào rỗng. Một danh sách filter rỗng không có nghĩa là “không xóa gì”; trong ngữ cảnh này, nó có thể có nghĩa là “không giới hạn”.

Các quy tắc an toàn:

- Không truyền null Specification vào thao tác xóa.
- Không dùng unrestricted làm fallback khi thiếu tham số request.
- Không gọi allOf/anyOf với danh sách filter có thể rỗng mà không kiểm tra.
- Luôn giữ predicate bắt buộc như tenant ID hoặc owner ID.
- Từ chối request nếu thiếu cutoff/status/phạm vi cần thiết.
- Không biến mọi filter tùy chọn thành unrestricted rồi dùng kết quả cho delete.
- Viết test xác nhận dữ liệu thuộc tenant khác hoặc trạng thái khác vẫn còn nguyên.

Ví dụ kiểm tra fail-closed:

~~~java
if (tenantId == null) {
    throw new IllegalArgumentException("Tenant is required");
}

if (cutoff == null) {
    throw new IllegalArgumentException("Cutoff is required");
}
~~~

Không dùng một Specification trống để thay thế hai điều kiện bắt buộc trên.

### 5.1. Cẩn thận khi kết hợp AND và OR

Giả sử yêu cầu là xóa đơn hàng đã hủy hoặc quá hạn, nhưng chỉ trong tenant hiện tại. Predicate đúng có dạng:

~~~text
tenantId = currentTenant
AND
(status = CANCELLED OR createdAt < cutoff)
~~~

Không viết logic thành:

~~~text
(tenantId = currentTenant AND status = CANCELLED)
OR
createdAt < cutoff
~~~

Biểu thức thứ hai có thể xóa đơn hàng quá hạn của tenant khác. Hãy nhóm các điều kiện OR bên trong điều kiện tenant bắt buộc và kiểm tra generated SQL.

## 6. Bulk delete ảnh hưởng đến persistence context như thế nào?

Persistence context theo dõi entity đang managed và trạng thái của chúng. Khi gọi `EntityManager.remove(entity)`, entity được đánh dấu removed. Provider thực hiện DELETE khi flush hoặc theo thời điểm phù hợp.

Bulk delete hoạt động khác: database xóa các hàng trực tiếp bằng một câu lệnh set-based. JPA provider không phải tải từng entity và cũng không phải cập nhật từng object đang nằm trong persistence context.

Ví dụ:

~~~java
PurchaseOrder managed =
        entityManager.find(PurchaseOrder.class, orderId);

long deleted = repository.delete(specification);
~~~

Sau câu lệnh bulk delete, biến `managed` vẫn là một object Java đã được tải trước đó. Trạng thái của object không tự biến thành “đã xóa” theo kết quả database. Nếu code tiếp tục đọc hoặc sửa object này, nó có thể đang làm việc với dữ liệu lỗi thời.

Cách xử lý:

- Chạy bulk delete trong transaction riêng hoặc persistence context không chứa các entity cần dùng tiếp.
- Gọi `flush()` trước khi xóa nếu có thay đổi đang chờ cần được ghi.
- Gọi `clear()` sau khi xóa nếu có thể detach toàn bộ entity trong context.
- Nếu chỉ một entity bị ảnh hưởng và cần tiếp tục dùng, có thể `refresh()` hoặc tải lại entity phù hợp sau khi xử lý trạng thái; không refresh một entity đã bị xóa khỏi database.
- Không giữ tham chiếu đến entity bị ảnh hưởng để dùng cho nghiệp vụ tiếp theo.

Bulk delete không tự gọi `EntityManager.clear()`. Đây là trách nhiệm của code gọi hoặc kiến trúc transaction.

### 6.1. Vì sao cần flush trước khi clear?

`clear()` detach tất cả entity và loại bỏ trạng thái đang được persistence context theo dõi. Nếu có thay đổi chưa flush, những thay đổi đó có thể không được ghi như mong muốn.

Thứ tự thường dùng trong một transaction chuyên biệt:

~~~java
entityManager.flush();
long deleted = repository.delete(specification);
entityManager.clear();
~~~

Không gọi `clear()` trước `flush()` nếu còn thay đổi cần lưu. Nếu persistence context đang chứa nhiều aggregate khác, hãy cân nhắc dùng transaction/context riêng thay vì detach toàn bộ.

## 7. Bulk delete không chạy lifecycle callback và JPA cascade

Một thao tác `EntityManager.remove(entity)` thực hiện vòng đời xóa entity. Nó có thể kích hoạt:

- `@PreRemove`.
- `@PostRemove`.
- Entity listener tương ứng.
- Quan hệ có `CascadeType.REMOVE` hoặc `CascadeType.ALL`.
- Quy tắc `orphanRemoval = true` trong các thao tác quan hệ thích hợp.

Bulk delete theo Specification không gọi `remove()` cho từng entity. Vì thế, không có callback `@PreRemove`/`@PostRemove` cho từng hàng và không có JPA cascade REMOVE/orphan removal.

Ví dụ callback:

~~~java
@Entity
public class PurchaseOrder {

    @PreRemove
    void beforeRemove() {
        // Không được gọi cho từng entity khi dùng bulk delete.
    }
}
~~~

Nếu logic nghiệp vụ quan trọng nằm trong callback, chẳng hạn ghi audit log, thu hồi tài nguyên hoặc phát domain event, bulk delete sẽ bỏ qua logic đó.

### 7.1. JPA cascade khác database cascade

Hai cơ chế cần phân biệt:

| Cơ chế | Bulk delete có thực hiện không? |
|---|---|
| `CascadeType.REMOVE` | Không |
| `CascadeType.ALL` bao gồm REMOVE | Không |
| `orphanRemoval = true` | Không được kích hoạt bởi bulk delete |
| Foreign key `ON DELETE CASCADE` | Database vẫn thực hiện |
| Database trigger | Trigger vẫn chạy theo cấu hình database |
| `@PreRemove` / `@PostRemove` | Không |
| Entity listener gắn với lifecycle remove | Không |

Nếu bảng con có FK trỏ đến bảng đơn hàng mà không có `ON DELETE CASCADE`, database có thể từ chối xóa đơn hàng cha do vi phạm FK. Khi đó, ứng dụng phải xóa các hàng con trước, dùng database cascade đã được thiết kế rõ ràng, hoặc chuyển sang xóa từng entity để JPA cascade hoạt động.

Không nhầm `CascadeType.REMOVE` với `ON DELETE CASCADE`: một cơ chế thuộc JPA lifecycle, cơ chế còn lại thuộc database constraint.

### 7.2. Audit và soft delete

Nếu audit dựa trên `@PreRemove`, entity listener hoặc domain event phát ra từ thao tác xóa entity, bulk delete không thực hiện các bước đó.

Nếu hệ thống cần audit cho một đợt purge, có thể ghi một bản ghi audit tổng hợp trong cùng transaction, gồm tenant, điều kiện, người thực hiện, thời điểm và số hàng bị xóa. Nếu cần audit từng entity, hãy chọn cách xóa có lifecycle hoặc một cơ chế audit ở database.

Nếu soft delete được triển khai bằng callback trước khi remove để đổi cờ deleted, bulk DELETE không gọi callback đó; database sẽ nhận thao tác xóa vật lý. Có thể dùng bulk UPDATE để đặt cờ/xóa mềm, hoặc gọi remove từng entity theo thiết kế soft-delete của provider. Phải kiểm tra đúng cơ chế soft-delete đang dùng trước khi thay đổi API.

## 8. Cơ chế optimistic locking, version và tính nhất quán

Entity có thể khai báo `@Version` để phát hiện xung đột khi cập nhật hoặc xóa từng entity managed. Bulk delete không tải và xử lý từng entity theo vòng đời đó. Vì vậy, không nên dựa vào cơ chế xóa từng entity để bảo vệ concurrency khi dùng CriteriaDelete.

Nếu nghiệp vụ cần giới hạn theo trạng thái/version, đưa điều kiện đó vào predicate:

~~~java
Specification<PurchaseOrder> expectedVersion =
        (root, query, cb) ->
                cb.equal(root.get("version"), expectedVersionValue);
~~~

Sau khi xóa, kiểm tra số hàng trả về:

~~~java
long deleted = repository.delete(target);

if (deleted != expectedCount) {
    throw new ConcurrentModificationException(
            "The matching rows changed before deletion");
}
~~~

Đây là cách kiểm tra số hàng bị ảnh hưởng, nhưng `expectedCount` được lấy trước đó không tự tạo bảo đảm nguyên tử. Giữa thao tác đếm và xóa vẫn có thể có transaction khác thay đổi dữ liệu. Nếu yêu cầu concurrency nghiêm ngặt, cần thiết kế isolation/locking hoặc dùng điều kiện version trong chính DELETE và xử lý kết quả affected rows.

Đừng coi `count(spec)` rồi `delete(spec)` là một thao tác nguyên tử nếu không có chiến lược đồng thời phù hợp.

## 9. Bulk delete khác gì derived delete và delete từng entity?

Các cách xóa trông giống nhau nhưng có hành vi khác nhau:

| Cách xóa | Cách thực hiện | Callback/cascade JPA | Bộ nhớ và hiệu năng |
|---|---|---|---|
| `repository.delete(spec)` | CriteriaDelete trực tiếp ở database | Không | Thường hiệu quả với tập lớn |
| `@Modifying @Query("delete ...")` | Một bulk JPQL DELETE | Không | Thường hiệu quả với tập lớn |
| `deleteAllInBatch()` | Bulk delete theo repository API | Không | Không tải từng entity |
| Derived `deleteByStatus(...)` | Tìm entity phù hợp rồi xóa từng entity | Có | Có thể tải nhiều entity vào memory |
| `repository.delete(entity)` | EntityManager.remove cho entity | Có | Phù hợp khi cần lifecycle |
| Lặp qua `findAll(spec)` rồi delete từng entity | Tải entity và remove từng object | Có | Tốn query, memory và thời gian hơn |

Spring Data JPA phân biệt derived delete với bulk delete. Một derived delete như `deleteByRoleId(...)` tìm các entity phù hợp rồi xóa từng entity để provider có thể gọi lifecycle callback. Ngược lại, một câu JPQL DELETE hoặc `delete(spec)` thực hiện một thao tác bulk trực tiếp tại database.

Nếu cần callback/cascade, chọn xóa entity. Nếu cần xóa hàng loạt hiệu quả và đã xử lý các tác động lifecycle, chọn bulk delete.

## 10. Xóa nhiều dữ liệu lớn: một câu lệnh hay chia batch?

`delete(spec)` không nhận Pageable để xóa từng trang. CriteriaDelete được thiết kế cho một thao tác set-based; không nên giả định có thể thêm LIMIT/OFFSET portable vào nó.

Bulk delete một lần có thể phù hợp nếu số hàng vừa phải và database xử lý tốt. Với tập dữ liệu rất lớn, một transaction duy nhất có thể:

- Giữ lock lâu.
- Tạo transaction log/WAL/undo lớn.
- Tạo áp lực lên replication và cleanup.
- Tăng thời gian rollback nếu lỗi.
- Làm chậm các request khác trên cùng bảng.

Có thể chia theo ID hoặc khoảng thời gian:

1. Query lấy một nhóm ID phù hợp theo thứ tự ổn định.
2. Xóa nhóm ID đó trong một transaction.
3. Commit để giải phóng tài nguyên.
4. Lặp đến khi hết dữ liệu.
5. Ghi checkpoint để có thể tiếp tục sau lỗi.

Ví dụ repository lấy ID theo keyset:

~~~java
@Query("""
       select p.id
       from PurchaseOrder p
       where p.tenantId = :tenantId
         and p.status = :status
         and p.createdAt < :cutoff
         and p.id > :afterId
       order by p.id
       """)
List<Long> findNextIds(
        @Param("tenantId") UUID tenantId,
        @Param("status") OrderStatus status,
        @Param("cutoff") Instant cutoff,
        @Param("afterId") Long afterId,
        Pageable pageable);
~~~

Sau đó có thể dùng `deleteAllByIdInBatch(ids)` nếu muốn bulk delete theo nhóm ID. Phương thức batch vẫn có ngữ nghĩa bulk: không gọi callback/cascade JPA và persistence context không tự đồng bộ.

Nếu cần lifecycle cho từng entity, tải từng batch entity rồi gọi `EntityManager.remove()` cho từng object. Sau mỗi batch, flush và clear theo chiến lược transaction phù hợp. Cách này tốn tài nguyên hơn nhưng giữ được semantics của entity lifecycle.

Khi chia batch, cần xác định cách xử lý dữ liệu thay đổi trong lúc job chạy. Keyset theo ID giúp tránh chi phí OFFSET lớn, nhưng không tự tạo snapshot nhất quán cho toàn bộ job.

## 11. Kiểm thử thao tác xóa theo Specification

Test nên xác nhận cả số hàng bị xóa và những hàng phải được giữ lại.

Ví dụ với Spring Data JPA 3.5 và `@DataJpaTest`:

~~~java
@DataJpaTest
class PurchaseOrderDeleteSpecificationTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private PurchaseOrderRepository orders;

    @Test
    void deletesOnlyCancelledOrdersInsideTenantAndBeforeCutoff() {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        Instant cutoff = Instant.parse("2026-01-01T00:00:00Z");

        entityManager.persist(new PurchaseOrder(
                tenantA,
                OrderStatus.CANCELLED,
                Instant.parse("2025-10-01T00:00:00Z")
        ));

        entityManager.persist(new PurchaseOrder(
                tenantA,
                OrderStatus.PAID,
                Instant.parse("2025-10-01T00:00:00Z")
        ));

        entityManager.persist(new PurchaseOrder(
                tenantB,
                OrderStatus.CANCELLED,
                Instant.parse("2025-10-01T00:00:00Z")
        ));

        entityManager.persist(new PurchaseOrder(
                tenantA,
                OrderStatus.CANCELLED,
                Instant.parse("2026-02-01T00:00:00Z")
        ));

        entityManager.flush();
        entityManager.clear();

        Specification<PurchaseOrder> target =
                Specification.allOf(
                        PurchaseOrderSpecs.belongsToTenant(tenantA),
                        PurchaseOrderSpecs.hasStatus(
                                OrderStatus.CANCELLED),
                        PurchaseOrderSpecs.createdBefore(cutoff)
                );

        long deleted = orders.delete(target);

        entityManager.clear();

        assertThat(deleted).isEqualTo(1);
        assertThat(orders.count()).isEqualTo(3);
    }
}
~~~

Test này tạo bốn trường hợp: đúng tenant và trạng thái; sai trạng thái; sai tenant; và đúng tenant/trạng thái nhưng chưa đến cutoff. Chỉ hàng đầu tiên được xóa.

`flush()` ghi fixture xuống database trước khi chạy bulk DELETE. `clear()` sau khi xóa giúp truy vấn kiểm tra đọc lại dữ liệu database thay vì dựa vào entity instance đã nằm trong persistence context.

### 11.1. Kiểm thử lifecycle callback

Nếu entity có `@PreRemove`, hãy viết test riêng để chứng minh callback không được gọi bởi `delete(spec)`. Có thể dùng entity listener với bộ đếm trong test hoặc một test double phù hợp.

Đừng kiểm thử callback bằng cách chỉ quan sát hàng đã biến mất. Database có thể xóa thành công dù callback không chạy.

### 11.2. Kiểm thử persistence context stale

Tạo một entity managed trước bulk delete, thực hiện xóa, rồi kiểm tra lại bằng persistence context mới sau khi clear. Test này giúp phát hiện code vô tình tiếp tục dùng entity object cũ sau thao tác bulk.

### 11.3. Kiểm thử FK và cascade

Tạo dữ liệu cha/con có quan hệ FK và chạy bulk delete:

- Nếu FK không có ON DELETE CASCADE, xác nhận database từ chối xóa khi còn hàng con.
- Nếu database có ON DELETE CASCADE, xác nhận hàng con bị xóa bởi database.
- Không dùng test này để kết luận JPA CascadeType.REMOVE đã chạy; đó là cơ chế khác.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Xóa toàn bộ bảng | Specification null hoặc unrestricted | Bắt buộc tenant/filter và fail closed |
| NullPointerException trong toPredicate | Code truy cập CriteriaQuery trong đường delete 3.5 | Không dùng query param; chuyển sang DeleteSpecification/custom CriteriaDelete nếu cần |
| Entity vẫn đọc được sau khi xóa | Persistence context không được đồng bộ | Clear hoặc tải trong context mới |
| @PreRemove không chạy | Bulk delete bỏ qua entity lifecycle | Xóa từng entity nếu callback là bắt buộc |
| Entity con còn lại hoặc FK violation | Bulk delete không chạy JPA cascade | Xóa con rõ ràng hoặc dùng FK cascade đã thiết kế |
| Soft-delete trở thành physical delete | Logic soft-delete nằm trong callback/entity remove | Dùng bulk UPDATE hoặc entity remove phù hợp |
| Không phát domain event/audit từng hàng | Không có lifecycle event cho từng entity | Ghi audit/outbox rõ ràng hoặc dùng per-entity remove |
| Count trước và số xóa thực tế khác nhau | Dữ liệu thay đổi giữa hai thao tác | Kiểm tra affected rows và thiết kế concurrency |
| Xóa quá nhiều trong một transaction | Tập dữ liệu lớn, lock/log/rollback tốn kém | Chia batch và commit theo nhóm |
| Test thấy entity cũ sau delete | Đang đọc object/persistence context cũ | Clear rồi query lại database |

## 13. Checklist trước khi chạy bulk delete

- [ ] Đã xác định đúng Spring Data JPA version và API tương ứng.
- [ ] Specification có điều kiện bắt buộc, ví dụ tenant hoặc owner.
- [ ] Không truyền null hoặc unrestricted làm điều kiện xóa.
- [ ] Không dùng danh sách Specification rỗng mà không kiểm tra.
- [ ] Điều kiện AND/OR được nhóm đúng theo nghiệp vụ.
- [ ] Với Spring Data JPA 3.5, toPredicate không truy cập CriteriaQuery vì query là null trong đường delete.
- [ ] Không đặt fetch join, order, group hoặc select-specific logic trong Specification dùng để xóa.
- [ ] Có transaction bao quanh thao tác.
- [ ] Đã quyết định cách xử lý persistence context sau bulk delete.
- [ ] Đã xác định callback, audit, domain event và soft-delete có cần chạy hay không.
- [ ] Đã kiểm tra CascadeType.REMOVE, orphanRemoval và database FK cascade.
- [ ] Đã cân nhắc version/concurrency và kiểm tra số hàng bị xóa.
- [ ] Đã đánh giá kích thước tập dữ liệu và nhu cầu chia batch.
- [ ] Có test chứng minh hàng đúng bị xóa và hàng ngoài phạm vi vẫn còn.
- [ ] Có test riêng cho callback, FK và trạng thái persistence context nếu use case cần.

## 14. Tài liệu tham khảo

- [Spring Data JPA 3.5 — JpaSpecificationExecutor Javadoc](https://docs.spring.io/spring-data/jpa/reference/3.5/api/java/org/springframework/data/jpa/repository/JpaSpecificationExecutor.html) — delete(Specification), kết quả số hàng, CriteriaDelete và việc persistence context không được đồng bộ.
- [Spring Data JPA 3.5 — Specification Javadoc](https://docs.spring.io/spring-data/jpa/reference/3.5/api/java/org/springframework/data/jpa/domain/Specification.html) — toPredicate, unrestricted và khả năng query argument null.
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html) — PredicateSpecification, UpdateSpecification và DeleteSpecification trong Spring Data JPA 4.x.
- [Spring Data JPA 4.1 — DeleteSpecification Javadoc](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/domain/DeleteSpecification.html) — CriteriaDelete predicate, composition, unrestricted và hành vi allOf/anyOf rỗng.
- [Spring Data JPA 4.0 — Derived Delete Queries](https://docs.spring.io/spring-data/data-jpa/reference/4.0/jpa/query-methods.html) — khác biệt giữa derived delete và bulk DELETE.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html) — bulk update/delete, cascade, lifecycle và persistence context.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — remove, cascade và quản lý persistence context.

Specification giúp tái sử dụng điều kiện xóa, còn CriteriaDelete giúp database xử lý nhiều hàng trong một thao tác. Đổi lại, bulk delete bỏ qua vòng đời remove của từng entity và không tự đồng bộ persistence context. Hãy luôn giữ điều kiện phạm vi bắt buộc, kiểm tra phiên bản API, quyết định rõ cascade/audit/soft-delete và kiểm thử dữ liệu còn lại sau khi xóa.
