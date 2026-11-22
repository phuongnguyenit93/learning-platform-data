# deleteAllInBatch, deleteAllByIdInBatch và trạng thái PersistenceContext trong Spring Data JPA

Spring Data JPA cung cấp các phương thức xóa theo entity và các phương thức **bulk delete** để xóa nhiều hàng bằng một thao tác truy vấn. Hai phương thức `deleteAllInBatch()` và `deleteAllByIdInBatch(Iterable<ID>)` có thể giảm số lần đọc entity và số câu lệnh so với việc tải từng entity rồi gọi remove. Tuy nhiên, bulk delete chạy trực tiếp trên database, bỏ qua nhiều cơ chế lifecycle của JPA và không tự đồng bộ PersistenceContext đang mở.

Điểm cần nhớ nhất: **bulk delete không tự cập nhật các entity đang được quản lý trong first-level cache**. Nếu tiếp tục dùng những object đó sau khi xóa hàng trong database, ứng dụng có thể đọc dữ liệu cũ hoặc gặp lỗi khi flush. Trong transaction cần giữ consistency, hãy cân nhắc quy trình `flush → bulk delete → clear`, hiểu rõ ảnh hưởng của clear và kiểm thử trên database thực tế.

Tài liệu dùng Jakarta Persistence (`jakarta.persistence`) và Spring Data JPA trong Spring Boot 3 / Spring Framework 6 trở lên. Các ví dụ giả định repository kế thừa `JpaRepository`.

## 1. Xóa từng entity và bulk delete khác nhau thế nào?

Có hai cách tiếp cận:

1. **Entity-by-entity removal:** tải hoặc nhận từng entity, gọi `EntityManager.remove()` thông qua repository. JPA quản lý trạng thái entity và áp dụng cascade/lifecycle theo mapping.
2. **Bulk delete:** gửi một câu JPQL DELETE hoặc thao tác bulk tương đương tới database. Database xóa hàng trực tiếp mà không tải từng entity vào PersistenceContext.

| Tiêu chí | `deleteAll()` / `deleteAllById()` | `deleteAllInBatch()` | `deleteAllByIdInBatch(ids)` |
|---|---|---|---|
| Cách thực hiện | Xóa từng entity theo lifecycle | Bulk delete toàn bộ entity type | Bulk delete theo tập ID |
| Tải entity vào PersistenceContext | Thường có, tùy implementation và trạng thái | Không cần tải toàn bộ entity | Không cần tải entity theo từng ID |
| Số thao tác database | Có thể nhiều SELECT/DELETE | Một bulk operation; provider có thể sinh nhiều SQL do mapping | Một bulk operation; provider có thể sinh nhiều SQL do mapping |
| `@PreRemove` / entity listener | Được gọi khi entity thực sự bị remove qua lifecycle | Không được gọi cho từng entity | Không được gọi cho từng entity |
| JPA cascade REMOVE | Có áp dụng theo quan hệ entity | Không áp dụng | Không áp dụng |
| `orphanRemoval` | Áp dụng khi thay đổi quan hệ được quản lý theo mapping | Không tự chạy | Không tự chạy |
| `@Version` optimistic locking | Có thể được kiểm tra theo entity lifecycle/provider | Không tự kiểm tra version từng entity | Không tự kiểm tra version từng entity |
| PersistenceContext | Được cập nhật theo remove từng entity | Có thể còn entity stale | Có thể còn entity stale |
| Phù hợp | Xóa cần lifecycle, cascade, callback, kiểm soát từng entity | Xóa số lượng lớn khi chấp nhận semantics bulk | Xóa số lượng lớn theo ID khi chấp nhận semantics bulk |

Tên phương thức có chữ “batch” không có nghĩa provider luôn gửi đúng một SQL statement trong mọi mapping. Với entity inheritance nhiều bảng, provider có thể cần nhiều câu SQL để xóa các hàng trong hierarchy. Ý nghĩa chính là không cần load và remove từng entity theo vòng lặp Java.

## 2. deleteAllInBatch()

`deleteAllInBatch()` xóa tất cả entity thuộc repository tương ứng bằng bulk operation. Ví dụ:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Service:

```java
@Service
public class ProductMaintenanceService {

    private final ProductRepository productRepository;

    public ProductMaintenanceService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public void removeAllProducts() {
        productRepository.deleteAllInBatch();
    }
}
```

Về mặt khái niệm, thao tác tương đương bulk JPQL:

```sql
delete from Product
```

Đây là JPQL minh họa theo entity name, không phải SQL table name. Provider chuyển thành câu lệnh phù hợp database và mapping.

Phương thức này phù hợp khi:

- Thực sự muốn xóa toàn bộ entity type.
- Không cần gọi callback hoặc cascade JPA cho từng entity.
- Không cần kiểm tra `@Version` trên từng hàng.
- Có thể xử lý foreign key và các quan hệ phụ thuộc ở database/schema.
- Có kế hoạch xử lý PersistenceContext sau bulk operation.

Cẩn thận khi gọi trong transaction nghiệp vụ đang có các entity cùng loại đã được load. Bulk delete không tự đánh dấu những instance đó là removed hoặc detach chúng.

## 3. deleteAllByIdInBatch(Iterable<ID> ids)

Phương thức này xóa các entity có ID nằm trong danh sách được truyền vào:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Service:

```java
@Transactional
public void removeProducts(Collection<Long> ids) {
    productRepository.deleteAllByIdInBatch(ids);
}
```

Về mặt ý tưởng, JPQL tương đương:

```sql
delete from Product p
where p.id in :ids
```

Khác với cách gọi `findAllById(ids)` rồi xóa từng entity, bulk method không cần dựng toàn bộ object graph chỉ để xóa.

Các điểm cần lưu ý:

- ID không tồn tại không tương ứng với hàng cần xóa; method không cung cấp kết quả cho từng ID đã bị bỏ qua.
- Không có entity instance để gọi callback `@PreRemove` cho từng ID.
- Cascade REMOVE của JPA không chạy.
- PersistenceContext có thể đang giữ instance có ID vừa bị xóa.
- Danh sách ID quá lớn có thể vượt giới hạn số bind parameter của database/driver hoặc làm query plan kém hiệu quả.

Nếu danh sách ID lớn, chia thành các nhóm nhỏ theo giới hạn đã kiểm thử. Mỗi nhóm có thể là một bulk operation riêng. Hãy cân nhắc transaction size, số round trip và khả năng rollback khi một nhóm thất bại.

## 4. PersistenceContext là gì?

PersistenceContext là phạm vi EntityManager quản lý các entity instance. Nó hoạt động như first-level cache và identity map:

- Theo dõi entity đang managed.
- Duy trì định danh entity theo entity type và primary key.
- Phát hiện thay đổi bằng dirty checking.
- Đồng bộ thay đổi qua flush.
- Duy trì trạng thái nhất quán giữa các thao tác trong cùng context.

Ví dụ:

```java
Product product = entityManager.find(Product.class, 10L);
product.setName("Updated");
```

Nếu entity đang managed, JPA ghi nhận thay đổi. Khi flush, provider tạo UPDATE. Nếu transaction commit thành công, thay đổi trở nên bền vững.

Khi xóa qua `entityManager.remove(product)`, entity được đánh dấu removed trong PersistenceContext. Nhưng bulk DELETE hoạt động trực tiếp trên database; nó không đi qua từng instance đang managed. Đây là nguyên nhân gây stale state.

## 5. Vì sao bulk delete làm PersistenceContext stale?

Giả sử một transaction đã load Product ID 10:

```java
@Transactional
public void example() {
    Product product = entityManager.find(Product.class, 10L);

    productRepository.deleteAllByIdInBatch(List.of(10L));

    // product vẫn có thể còn là managed instance trong context.
    System.out.println(product.getName());
}
```

Sau bulk DELETE:

- Hàng ID 10 đã bị xóa khỏi database trong transaction.
- Object `product` vẫn có thể còn trong first-level cache.
- `entityManager.contains(product)` có thể vẫn trả về true.
- Gọi `find(Product.class, 10L)` trong cùng context có thể trả về instance đang được quản lý mà không đọc lại database.
- Thay đổi object stale sau đó có thể gây lỗi khi flush hoặc làm logic nghiệp vụ dựa trên trạng thái không còn tồn tại.

Bulk query không tự tìm mọi instance đang managed rồi đồng bộ trạng thái cho chúng. JPA specification quy định bulk update/delete không đồng bộ trạng thái PersistenceContext.

Điều này không chỉ xảy ra với delete. Bulk UPDATE cũng có thể làm entity trong context giữ giá trị cũ. Tuy nhiên, topic này tập trung vào hai bulk delete method.

## 6. Quy trình flush → bulk delete → clear

Một mẫu phổ biến khi bulk delete trong một transaction có PersistenceContext đang mở:

1. **Flush:** ghi các thay đổi pending trước bulk operation để chúng không bị bỏ sót hoặc xung đột thứ tự.
2. **Bulk delete:** chạy DELETE trực tiếp trên database.
3. **Clear:** detach toàn bộ entity đang managed để tránh dùng state cũ.

Ví dụ:

```java
@Service
public class ProductMaintenanceService {

    private final ProductRepository productRepository;
    private final EntityManager entityManager;

    public ProductMaintenanceService(
            ProductRepository productRepository,
            EntityManager entityManager) {
        this.productRepository = productRepository;
        this.entityManager = entityManager;
    }

    @Transactional
    public void removeProducts(Collection<Long> ids) {
        entityManager.flush();

        productRepository.deleteAllByIdInBatch(ids);

        entityManager.clear();
    }
}
```

Với Spring, EntityManager được inject thường là shared proxy; có thể inject bằng `@PersistenceContext`:

```java
@PersistenceContext
private EntityManager entityManager;
```

### 6.1. Vì sao flush trước?

Giả sử một entity đang được persist nhưng chưa flush, hoặc một entity liên quan có thay đổi pending. Flush bảo đảm các thao tác đã chờ được đồng bộ theo thứ tự trước khi bulk DELETE chạy.

Flush cũng có thể phát hiện lỗi constraint hoặc optimistic locking trước khi tới bulk operation. Nếu flush thất bại, transaction có thể bị đánh dấu rollback-only; không tiếp tục coi transaction đó là bình thường.

Flush không commit. Nếu bulk delete hoặc thao tác sau đó thất bại, transaction vẫn có thể rollback toàn bộ các thay đổi chưa commit.

### 6.2. Vì sao clear sau?

`entityManager.clear()` detach **tất cả** entity đang managed trong PersistenceContext hiện tại. Sau clear:

- Entity đã bị bulk delete không còn được giữ như managed instance.
- Các entity khác cũng trở thành detached.
- Tham chiếu Java mà code đang giữ vẫn tồn tại nhưng không còn được dirty checking.
- Muốn đọc trạng thái mới phải load lại entity trong context thích hợp.

Clear toàn bộ có thể ảnh hưởng nhiều logic trong service. Nếu cần giữ các entity khác đang managed, có thể detach các instance cụ thể mà ứng dụng đã biết, hoặc tách bulk operation sang một transaction/persistence context riêng. Không có API JPA chuẩn để tự động clear chỉ những ID bị xóa.

### 6.3. Khi nào không cần clear?

Nếu bulk operation chạy trong transaction riêng, kết thúc transaction và PersistenceContext transaction-scoped được đóng ngay sau đó, không còn code nào trong context đó tiếp tục dùng entity stale, vấn đề có thể không xuất hiện trong luồng hiện tại.

Tuy nhiên, khi bulk delete tham gia một transaction lớn hơn, phải cân nhắc trạng thái của PersistenceContext đang dùng chung. Đừng mặc định method repository tự clear context.

## 7. Bulk delete và lifecycle callbacks

Khi xóa từng entity qua `EntityManager.remove()`, JPA có thể gọi lifecycle callback và listener:

```java
@Entity
public class Product {

    @Id
    private Long id;

    @PreRemove
    public void beforeRemove() {
        // Ví dụ: kiểm tra hoặc cập nhật state trong entity lifecycle.
    }
}
```

Với bulk JPQL DELETE hoặc các repository batch delete method, provider không load từng entity và không gọi `@PreRemove` / `@PostRemove` cho từng hàng. Entity listener cũng không được chạy theo lifecycle từng entity. JPA cascade remove và orphanRemoval không được áp dụng cho bulk operation.

Điều này có nghĩa nếu hệ thống dựa vào callback để:

- Ghi audit log trong ứng dụng.
- Phát domain event.
- Xóa file hoặc tài nguyên ngoài database.
- Cập nhật bảng phụ thông qua logic Java.
- Thực hiện soft delete.

Thì bulk delete sẽ bỏ qua những hành vi đó.

Database trigger vẫn có thể chạy vì database thực sự nhận DELETE. Nhưng trigger là cơ chế ở database, không thay thế hoàn toàn event hoặc logic trong application layer.

Nếu cần lifecycle semantics, hãy xóa từng entity hoặc thiết kế một quy trình bulk riêng thực hiện đầy đủ các tác động cần thiết.

## 8. Bulk delete và cascade / orphanRemoval

Xét quan hệ:

```java
@Entity
public class Order {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order",
               cascade = CascadeType.REMOVE,
               orphanRemoval = true)
    private List<OrderItem> items = new ArrayList<>();
}
```

Nếu gọi `entityManager.remove(order)`, JPA cascade REMOVE có thể lan truyền tới OrderItem theo mapping; orphanRemoval xử lý child bị loại khỏi quan hệ được quản lý theo ngữ nghĩa tương ứng.

Nếu gọi bulk DELETE:

```java
entityManager.createQuery("delete from Order o").executeUpdate();
```

JPA không đi qua từng Order và không cascade REMOVE tới OrderItem. Database có thể từ chối DELETE vì FK từ order_item tới orders vẫn còn.

Có ba hướng thiết kế:

1. Xóa child trước rồi xóa parent bằng bulk operation.
2. Dùng database FK với `ON DELETE CASCADE` nếu đây là chính sách được chủ động thiết kế và kiểm thử.
3. Xóa từng entity qua lifecycle JPA khi cần cascade, callback và quy tắc domain.

`ON DELETE CASCADE` là hành vi database, khác với `CascadeType.REMOVE` của JPA. Nếu database cascade xóa hàng con trong khi PersistenceContext đang giữ OrderItem, context có thể stale và cần được xử lý.

## 9. Bulk delete và @Version / optimistic locking

Entity có thể dùng `@Version` để phát hiện cập nhật/xóa xung đột:

```java
@Entity
public class Product {

    @Id
    private Long id;

    @Version
    private Long version;
}
```

Khi xóa một entity managed bằng `remove()`, provider có thể dùng version trong câu DELETE để bảo đảm không xóa một phiên bản đã bị thay đổi bởi transaction khác.

Bulk DELETE không tự kiểm tra version của từng entity như lifecycle remove thông thường. Nó cũng không tự áp dụng optimistic locking theo từng instance. Nếu nghiệp vụ yêu cầu xóa có điều kiện theo version, cần viết predicate rõ ràng hoặc xóa từng entity.

Ví dụ custom bulk query có version predicate:

```java
@Modifying
@Query("""
    delete from Product p
    where p.id = :id
      and p.version = :version
    """)
int deleteIfVersionMatches(
    @Param("id") Long id,
    @Param("version") Long version
);
```

Số hàng bị xóa bằng 1 nghĩa là predicate khớp; 0 có thể nghĩa là ID không tồn tại hoặc version không còn khớp. Ứng dụng có thể chuyển trường hợp này thành lỗi optimistic conflict theo nghiệp vụ.

Đây là ví dụ bulk query; cần có transaction phù hợp và xử lý PersistenceContext. Nếu cần semantics version chuẩn cho nhiều entity, cân nhắc xóa từng entity.

## 10. Foreign key và thứ tự xóa

Bulk delete vẫn chịu mọi constraint của database:

- Foreign key có thể chặn xóa parent khi child còn tham chiếu.
- Unique constraint và trigger có thể tác động tới kết quả.
- Database cascade có thể xóa hàng liên quan nếu schema định nghĩa.
- Thứ tự xóa phải phù hợp với dependency giữa các bảng.

Ví dụ nếu muốn xóa các Order cũ và OrderItem:

```java
@Transactional
public void purgeOrders(Collection<Long> ids) {
    entityManager.flush();

    orderItemRepository.deleteByOrderIdIn(ids);
    orderRepository.deleteAllByIdInBatch(ids);

    entityManager.clear();
}
```

Child được xóa trước parent để tránh FK violation. Các repository query phải được khai báo đúng; ví dụ này giả định OrderItem có association order và custom bulk query tương ứng.

Nếu dùng database `ON DELETE CASCADE`, có thể chỉ cần xóa parent, nhưng phải hiểu trigger, audit và persistence context. Không bật cascade database một cách tùy tiện chỉ để che lỗi FK.

## 11. Soft delete và batch delete

Soft delete thường có nghĩa cập nhật một cột như `deleted_at` hoặc `active = false` thay vì DELETE vật lý.

Nếu entity dùng `@PreRemove`, Hibernate custom SQL delete hoặc listener để thực hiện soft delete, các bulk delete method không nên được giả định sẽ gọi cùng logic. JPQL bulk DELETE xóa hàng theo semantics bulk DML; nó không chạy callback từng entity.

Nếu yêu cầu soft delete hàng loạt, nên viết bulk UPDATE rõ ràng:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Product p
    set p.deleted = true
    where p.id in :ids
    """)
int softDeleteByIds(@Param("ids") Collection<Long> ids);
```

Đây là ví dụ cho entity có thuộc tính boolean `deleted`. Sau bulk UPDATE, clearAutomatically giúp tránh dùng entity stale trong PersistenceContext. Nếu muốn ghi thời điểm xóa, có thể cập nhật thêm `deletedAt`.

Bulk soft delete cũng bỏ qua lifecycle callbacks và dirty checking từng entity. Nếu cần audit event hoặc logic ngoài database, phải thực hiện riêng.

## 12. @Modifying và bulk query tùy chỉnh

Spring Data JPA cho phép định nghĩa bulk DELETE bằng `@Query` và `@Modifying`:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        delete from Product p
        where p.expiredAt < :cutoff
        """)
    int deleteExpiredBefore(@Param("cutoff") Instant cutoff);
}
```

Hai thuộc tính có ý nghĩa:

- `flushAutomatically = true`: flush EntityManager trước khi thực thi modifying query.
- `clearAutomatically = true`: clear PersistenceContext sau khi query chạy.

Mặc định hai thuộc tính này là false. Nếu không đặt chúng, ứng dụng cần tự kiểm soát flush và clear.

`@Modifying` dùng cho query UPDATE/DELETE/INSERT dạng modifying query, không phải query SELECT. Method cần chạy trong transaction. Nếu dùng inherited `deleteAllInBatch()` hoặc `deleteAllByIdInBatch()`, không thể truyền hai flag này vào method; hãy điều khiển EntityManager ở service boundary hoặc dùng custom repository/query.

## 13. Batch size và danh sách ID lớn

`deleteAllByIdInBatch(ids)` thuận tiện khi danh sách ID vừa phải. Nhưng một câu `IN (...)` rất lớn có thể gặp:

- Giới hạn số bind parameter của database hoặc JDBC driver.
- SQL dài, parse time tăng.
- Query plan không ổn định.
- Bộ nhớ tăng khi giữ danh sách ID.
- Transaction giữ lock quá lâu.

Giải pháp là chia ID thành các chunk phù hợp:

```java
@Transactional
public void deleteInChunks(List<Long> ids, int chunkSize) {
    for (int start = 0; start < ids.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, ids.size());
        List<Long> chunk = ids.subList(start, end);

        entityManager.flush();
        repository.deleteAllByIdInBatch(chunk);
        entityManager.clear();
    }
}
```

Chunk size cần được đo trên database thật. Flush/clear mỗi chunk giúp quản lý PersistenceContext nhưng clear detach mọi entity đang managed, không chỉ các Product bị xóa. Nếu transaction kéo dài quá lâu, cân nhắc commit theo từng chunk; khi đó semantics là nhiều transaction và có thể chỉ một số chunk thành công nếu lỗi xảy ra giữa chừng. Đây là quyết định nghiệp vụ, không chỉ tối ưu kỹ thuật.

Nếu chunk size không hợp lệ (0 hoặc âm), cần validate input trước vòng lặp. Không dùng subList từ danh sách bị thay đổi đồng thời.

## 14. Entity inheritance và nhiều bảng

Bulk delete entity có inheritance có thể phức tạp hơn một bảng đơn. Với JOINED inheritance, một entity subtype được lưu trong bảng cha và bảng con. Xóa entity theo JPQL có thể cần xóa hàng trong nhiều bảng theo thứ tự đáp ứng foreign key.

Provider có thể dùng nhiều câu SQL, temporary table hoặc chiến lược khác tùy dialect và phiên bản. Vì vậy, đừng suy luận rằng `deleteAllInBatch()` luôn tạo đúng một DELETE statement nếu entity mapping có JOINED inheritance hoặc các cấu trúc multi-table.

Khi xóa entity root, hãy kiểm tra provider có xóa đúng mọi hàng subtype hay không. Với foreign key từ bảng khác tham chiếu tới bảng root/subtype, database constraint vẫn có thể chặn thao tác.

Bulk delete trong inheritance cũng không gọi callback của từng entity subtype. Nếu mỗi subtype có soft-delete hoặc audit logic riêng trong lifecycle callback, bulk method có thể không phù hợp.

## 15. So sánh với xóa theo vòng lặp

Ví dụ xóa từng entity:

```java
@Transactional
public void deleteProductsOneByOne(Collection<Long> ids) {
    for (Long id : ids) {
        productRepository.findById(id)
            .ifPresent(productRepository::delete);
    }
}
```

Cách này có thể thực hiện nhiều SELECT và DELETE, nhưng mỗi entity được đưa qua lifecycle JPA. Cascade, callback và version semantics có thể được áp dụng.

Bulk:

```java
@Transactional
public void deleteProductsInBatch(Collection<Long> ids) {
    entityManager.flush();
    productRepository.deleteAllByIdInBatch(ids);
    entityManager.clear();
}
```

Cách này tránh load từng entity và giảm overhead ở application layer. Đổi lại, ứng dụng chịu trách nhiệm bảo đảm các hành vi bị bỏ qua, tính toàn vẹn tham chiếu và PersistenceContext.

| Nhu cầu | Cách nên cân nhắc |
|---|---|
| Cần `@PreRemove`, listener hoặc domain event theo từng entity | Xóa từng entity |
| Cần cascade REMOVE/orphanRemoval của JPA | Xóa từng entity |
| Cần optimistic locking theo từng entity | Xóa từng entity hoặc custom version predicate có kiểm soát |
| Xóa nhiều hàng đơn giản, không cần lifecycle | Bulk delete |
| Xóa theo danh sách ID lớn | Bulk delete theo chunk và đo giới hạn parameter |
| Cần soft delete qua callback | Xóa từng entity hoặc custom bulk UPDATE với logic bổ sung |
| Có FK phụ thuộc | Xóa child trước, hoặc thiết kế DB cascade có chủ đích |

## 16. Kiểm thử trạng thái PersistenceContext

Nên có integration test chứng minh bulk delete làm context stale và cách xử lý.

Ví dụ kiểm tra clear sau bulk delete:

```java
@DataJpaTest
class ProductBulkDeleteTest {

    @Autowired
    private ProductRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void clearContextAfterBulkDelete() {
        Product product = repository.saveAndFlush(
            new Product("SKU-1")
        );
        Long id = product.getId();

        Product managed = entityManager.find(Product.class, id);
        assertThat(entityManager.contains(managed)).isTrue();

        entityManager.flush();
        repository.deleteAllByIdInBatch(List.of(id));
        entityManager.clear();

        assertThat(entityManager.contains(managed)).isFalse();
        assertThat(repository.findById(id)).isEmpty();
    }
}
```

Ví dụ giả định Product có constructor nhận SKU và repository đã cấu hình đúng. Trong test transaction do `@DataJpaTest` quản lý, bulk DELETE và clear diễn ra trong cùng transaction. Sau clear, truy vấn repository phải đọc lại trạng thái database trong persistence context mới hoặc đã được làm sạch.

Để chứng minh rủi ro stale state, có thể viết test riêng không clear, nhưng không nên tiếp tục sửa hoặc flush entity stale sau khi hàng đã bị xóa. Test nên làm rõ hành vi provider cụ thể và không dựa vào chi tiết implementation không portable.

Các kiểm thử bổ sung:

- Callback `@PreRemove` không chạy khi bulk delete.
- Cascade REMOVE không xóa entity liên quan khi bulk delete.
- FK constraint từ chối xóa nếu còn child và không có database cascade.
- Bulk delete bỏ qua version check mặc định.
- Flush trước bulk query ghi các thay đổi pending.
- Clear detach mọi entity trong PersistenceContext.
- Bulk delete với ID không tồn tại không làm hỏng dữ liệu khác.
- Danh sách ID rỗng được xử lý theo API contract của phiên bản đang dùng.
- Xóa hierarchy JOINED được kiểm thử trên database thực tế.

## 17. Quan sát SQL và đo hiệu năng

Bật log SQL trong môi trường phát triển:

```properties
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind logging có thể chứa dữ liệu nhạy cảm; chỉ bật trong môi trường an toàn, hạn chế quyền truy cập và tắt khi hoàn tất.

Khi benchmark, so sánh cùng dữ liệu và cùng điều kiện:

1. Xóa từng entity bằng find/remove.
2. `deleteAllInBatch()`.
3. `deleteAllByIdInBatch(ids)`.
4. Bulk delete theo chunk.
5. Thời gian database, thời gian application, số round trip, số hàng bị xóa.
6. Kích thước PersistenceContext và memory usage.
7. Lock duration, transaction duration và ảnh hưởng của FK/index.
8. Hành vi khi có concurrent update hoặc delete.

Không chỉ đo thời gian của repository method nếu transaction commit xảy ra sau đó. SQL có thể đã được gửi nhưng transaction chưa commit. Hãy đo toàn bộ transaction boundary nếu muốn đánh giá thời gian người dùng thực sự chờ.

## 18. Kết luận

`deleteAllInBatch()` xóa toàn bộ entity type bằng bulk operation; `deleteAllByIdInBatch(ids)` xóa theo danh sách ID. Cả hai giảm nhu cầu load và remove từng entity, nhưng bỏ qua JPA lifecycle callbacks, cascade REMOVE, orphanRemoval và optimistic locking theo từng entity. Chúng cũng không tự đồng bộ PersistenceContext.

Khi bulk delete trong transaction có context đang mở, cân nhắc flush trước để đồng bộ pending changes và clear sau để tránh stale entities. Clear detach toàn bộ entity trong context, nên phải đặt bulk operation ở ranh giới phù hợp. Nếu nghiệp vụ phụ thuộc callback, cascade, version hoặc soft delete, hãy chọn cách xóa từng entity hoặc xây dựng bulk workflow có các tác động tương đương được kiểm soát rõ ràng.
