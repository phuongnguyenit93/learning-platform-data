# Dùng flush và clear để xác minh dữ liệu thực trong cơ sở dữ liệu

## 1. Vì sao test JPA cần flush và clear?

Khi kiểm thử repository, một test có thể lưu Entity rồi đọc lại ngay và nhận đúng giá trị, dù chưa có câu SQL INSERT/UPDATE nào được gửi xuống database. Nguyên nhân là JPA giữ Entity trong first-level cache, còn gọi là persistence context.

Persistence context quản lý các Entity đang được theo dõi. Với cùng một Entity type và ID, một persistence context thường chỉ giữ một managed instance. Khi gọi `find()` hoặc repository `findById()` lần nữa, JPA có thể trả lại instance đang được quản lý mà không truy vấn database.

Điều này có lợi cho ứng dụng nhưng có thể làm test cho kết quả sai lệch nếu mục tiêu là xác minh dữ liệu đã thực sự được ghi xuống database hoặc kiểm tra mapping khi đọc lại.

Hai thao tác cần hiểu rõ:

- `flush()` đồng bộ các thay đổi đang chờ trong persistence context thành câu lệnh SQL gửi tới database.
- `clear()` detach toàn bộ Entity đang được quản lý khỏi persistence context hiện tại, buộc lần đọc Entity sau phải đi qua quá trình nạp lại.

Chuỗi thường dùng trong integration test là:

```text
persist/save
    -> flush()
    -> clear()
    -> find/read again
    -> assert
```

## 2. flush() làm gì?

`EntityManager.flush()` yêu cầu JPA đồng bộ các thay đổi đang chờ với database trong transaction hiện tại. Tùy trạng thái Entity, provider có thể phát INSERT, UPDATE hoặc DELETE.

```java
entityManager.persist(order);
entityManager.flush();
```

Trước `flush()`, Entity mới có thể chỉ tồn tại trong persistence context. Sau `flush()`, SQL tương ứng đã được gửi và thực thi trong transaction của database.

Điều quan trọng: **flush không phải commit**. Transaction vẫn mở và có thể rollback. Những transaction khác thông thường chưa nhìn thấy thay đổi chưa commit theo isolation của database.

`flush()` cũng có thể làm lộ lỗi database sớm hơn, ví dụ:

- Vi phạm unique constraint hoặc foreign key.
- Giá trị NULL ở cột NOT NULL.
- Kiểu dữ liệu hoặc độ dài cột không hợp lệ.
- Lỗi SQL do mapping hoặc câu lệnh sinh ra.

Với constraint được database trì hoãn đến cuối transaction, lỗi vẫn có thể chỉ xuất hiện ở commit. Vì vậy flush không thay thế việc kiểm tra commit khi nghiệp vụ phụ thuộc vào kết quả commit.

## 3. clear() làm gì?

`EntityManager.clear()` detach tất cả Entity đang managed khỏi persistence context hiện tại.

```java
entityManager.clear();
```

Sau khi clear:

- Các object Java mà code đang giữ vẫn tồn tại trong bộ nhớ.
- Những object đó không còn được JPA theo dõi trong persistence context vừa clear.
- Thay đổi tiếp theo trên object detached không tự động được ghi xuống database.
- Lần `find()` tiếp theo phải tìm một managed instance mới trong persistence context.

`clear()` không xóa hàng dữ liệu trong database và cũng không xóa second-level cache. Nó chỉ làm rỗng first-level cache của EntityManager hiện tại.

Nếu chỉ muốn detach một Entity, dùng `entityManager.detach(entity)`. Nếu muốn nạp lại trạng thái database vào một Entity vẫn managed, cân nhắc `entityManager.refresh(entity)` thay vì clear toàn bộ context.

## 4. Vì sao phải flush trước khi clear?

Thứ tự rất quan trọng. Nếu clear trước khi flush, các thay đổi chưa được đồng bộ có thể bị mất khỏi persistence context và không được gửi xuống database.

```java
// Đúng: gửi thay đổi đang chờ xuống database trước.
entityManager.flush();
entityManager.clear();

// Đọc lại sau khi persistence context đã được làm sạch.
PurchaseOrder reloaded = entityManager.find(PurchaseOrder.class, orderId);
```

Không làm theo thứ tự ngược:

```java
// Nguy hiểm: thay đổi chưa flush có thể bị bỏ khi clear detach Entity.
entityManager.clear();
entityManager.flush();
```

Trong đoạn sai, sau `clear()` persistence context không còn quản lý Entity vừa thay đổi; `flush()` tiếp theo không còn thay đổi đó để đồng bộ. Vì vậy hãy luôn flush trước khi clear nếu mục tiêu là lưu thay đổi rồi đọc lại.

## 5. Integration test với EntityManager

Ví dụ Entity có trạng thái đơn hàng:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    public Long getId() { return id; }
    public OrderStatus getStatus() { return status; }
    public void setStatus(OrderStatus status) { this.status = status; }
}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

Test dùng `flush()` rồi `clear()` trước khi đọc lại:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void readsPersistedStateAfterFlushAndClear() {
        PurchaseOrder order = new PurchaseOrder();
        order.setStatus(OrderStatus.PENDING);

        PurchaseOrder saved = repository.save(order);
        entityManager.flush();
        Long id = saved.getId();

        entityManager.clear();

        PurchaseOrder reloaded = repository.findById(id).orElseThrow();
        assertEquals(OrderStatus.PENDING, reloaded.getStatus());
    }
}
```

Đây là integration test minh họa; cần có constructor hoặc factory phù hợp với Entity, enum `OrderStatus`, schema và import JUnit/Spring Test tương ứng. `@DataJpaTest` thường chạy trong transaction và rollback sau test. Việc đọc lại sau clear xác minh database đã thực thi SQL và transaction hiện tại nhìn thấy thay đổi của chính nó, dù test chưa commit.

## 6. save(), saveAndFlush() và flush() khác nhau

`JpaRepository` cung cấp một số method có tên gần nhau nhưng semantics khác:

| Method | Ý nghĩa |
| --- | --- |
| `save(entity)` | Persist Entity mới hoặc merge Entity detached theo trạng thái; thay đổi có thể vẫn chờ flush |
| `flush()` | Flush toàn bộ thay đổi đang chờ trong persistence context |
| `saveAndFlush(entity)` | Save Entity rồi flush persistence context |
| `saveAll(entities)` | Save một nhóm Entity; không cam kết tự flush ngay tại lời gọi |
| `saveAllAndFlush(entities)` | Save nhóm Entity rồi flush |

Ví dụ:

```java
PurchaseOrder saved = repository.saveAndFlush(order);
```

`saveAndFlush()` bảo đảm flush sau khi save, nhưng Entity vẫn có thể đang managed. Nếu ngay sau đó gọi `findById()` trong cùng persistence context, kết quả vẫn có thể là instance đã được quản lý. Muốn kiểm tra đường đọc mới, gọi `entityManager.clear()` sau flush hoặc dùng một persistence context khác.

`saveAndFlush()` cũng không commit transaction. Khi test kết thúc bằng rollback, dữ liệu sẽ bị rollback dù SQL đã được thực thi.

## 7. flush mode và thời điểm SQL được gửi

JPA có `FlushModeType.AUTO` và `FlushModeType.COMMIT`. Với AUTO, provider phải bảo đảm các thay đổi có thể ảnh hưởng kết quả query được đồng bộ trước khi query thực thi; provider có thể flush ở những thời điểm khác theo implementation.

Với COMMIT, flush được yêu cầu trước commit; query trong transaction có thể không nhìn thấy thay đổi chưa flush tùy provider/semantics.

Trong test cần xác định chính xác thời điểm SQL được gửi, hãy gọi `entityManager.flush()` tường minh thay vì phụ thuộc vào việc một query tình cờ kích hoạt auto-flush.

Không gọi flush sau từng setter hoặc từng field. Flush có chi phí SQL và round-trip; chỉ flush tại ranh giới cần kiểm tra constraint, cần đọc lại hoặc cần giới hạn bộ nhớ.

## 8. Xác minh UPDATE chứ không chỉ INSERT

Flush/clear cũng hữu ích để xác nhận dirty checking tạo UPDATE đúng:

```java
PurchaseOrder order = repository.findById(id).orElseThrow();
order.setStatus(OrderStatus.PAID);

entityManager.flush();
entityManager.clear();

PurchaseOrder reloaded = repository.findById(id).orElseThrow();
assertEquals(OrderStatus.PAID, reloaded.getStatus());
```

Ở đây Entity được tải và managed; thay đổi field được dirty checking phát hiện. `flush()` gửi UPDATE, `clear()` loại instance cũ khỏi first-level cache, và lần đọc sau nạp lại trạng thái đã ghi.

Không cần gọi `repository.save(order)` cho một Entity đã managed trong cùng transaction chỉ để kích hoạt dirty checking; JPA sẽ tự phát hiện thay đổi khi flush. Tuy nhiên, gọi `save()` có thể vẫn hợp lệ theo abstraction của repository.

## 9. refresh() khác clear()

`entityManager.refresh(entity)` nạp lại trạng thái của một Entity đang managed từ database và ghi đè trạng thái trong bộ nhớ:

```java
entityManager.flush();
entityManager.refresh(order);
```

Khác biệt:

| Thao tác | Phạm vi | Kết quả |
| --- | --- | --- |
| `flush()` | Toàn bộ thay đổi đang chờ trong persistence context | Gửi SQL xuống database; Entity vẫn managed |
| `clear()` | Toàn bộ persistence context | Detach mọi Entity; lần đọc sau cần nạp lại |
| `detach(entity)` | Một Entity | Detach riêng Entity đó |
| `refresh(entity)` | Một Entity đang managed | Đọc lại trạng thái database và ghi đè trạng thái trong bộ nhớ |

Nếu gọi `refresh()` khi Entity có thay đổi chưa flush, các thay đổi chưa ghi có thể bị ghi đè. Nếu muốn refresh sau chính thay đổi của mình, flush trước. `refresh()` không phải cách để commit transaction.

## 10. Bulk UPDATE/DELETE và persistence context cũ

JPQL bulk DML cập nhật trực tiếp database, không cập nhật từng managed Entity đang có trong persistence context:

```java
@Modifying
@Query("update PurchaseOrder p set p.status = :status where p.id = :id")
int updateStatus(
    @Param("id") Long id,
    @Param("status") OrderStatus status
);
```

Nếu một `PurchaseOrder` đã được load trước bulk update, object đó có thể vẫn giữ status cũ sau khi câu UPDATE chạy. Bulk DML không đồng bộ tự động trạng thái từng Entity trong first-level cache.

Có thể cấu hình Spring Data để flush trước và clear sau bulk DML:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("update PurchaseOrder p set p.status = :status where p.id = :id")
int updateStatusAndClear(
    @Param("id") Long id,
    @Param("status") OrderStatus status
);
```

`flushAutomatically = true` tránh mất các thay đổi đang chờ trước khi chạy bulk update. `clearAutomatically = true` detach Entity sau update để code không tiếp tục dùng trạng thái cũ trong persistence context.

Sau method này, các tham chiếu Entity mà service giữ có thể đã detached. Nếu cần tiếp tục thao tác, hãy đọc lại Entity trong persistence context mới.

## 11. First-level cache và second-level cache

`flush()` và `clear()` xử lý tương tác với first-level cache, nhưng clear không đảm bảo mọi lần đọc sau đều lấy trực tiếp database.

Nếu Hibernate second-level cache được bật, lần `find()` sau clear có thể lấy Entity từ shared cache. Query cache cũng có thể tham gia với các query được cấu hình cacheable.

Nếu mục tiêu chỉ là xác minh mapping và khả năng đọc lại qua JPA, flush/clear thường là bước kiểm tra hữu ích. Nếu mục tiêu là xác minh giá trị thực đang nằm trong database, cần xét cả second-level cache.

Có thể yêu cầu bỏ qua second-level cache cho một lần đọc:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode", CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode", CacheStoreMode.BYPASS
);

PurchaseOrder reloaded = entityManager.find(
    PurchaseOrder.class, id, hints
);
```

Ví dụ dùng Jakarta Persistence. `CacheRetrieveMode.BYPASS` bỏ qua shared cache khi đọc; `CacheStoreMode.BYPASS` không lưu kết quả đọc vào shared cache. Các hint này không vô hiệu hóa first-level cache: nếu Entity đã managed trong cùng persistence context, `find()` vẫn có thể trả instance đó. Vì vậy cần `clear()` trước khi dùng cách đọc này.

Với các tình huống cần xác nhận database độc lập với JPA cache, đọc bằng JDBC là cách kiểm tra trực tiếp hơn.

## 12. Dùng JdbcTemplate để kiểm tra hàng trong database

`JdbcTemplate` đọc trực tiếp qua JDBC, không lấy Entity từ first-level persistence context hay second-level Entity cache:

```java
@DataJpaTest
class PurchaseOrderDatabaseStateTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void verifiesDatabaseColumnAfterFlush() {
        PurchaseOrder order = new PurchaseOrder();
        order.setStatus(OrderStatus.PENDING);
        PurchaseOrder saved = repository.save(order);

        entityManager.flush();

        String storedStatus = jdbcTemplate.queryForObject(
            "select order_status from purchase_order where id = ?",
            String.class,
            saved.getId()
        );

        assertEquals("PENDING", storedStatus);
    }
}
```

Ví dụ giả định enum được lưu bằng `EnumType.STRING`, tên bảng/cột khớp mapping và JdbcTemplate tham gia cùng transaction/DataSource với JPA. Trong Spring, cấu hình transaction manager và DataSource phù hợp để JDBC và JPA cùng nhìn thấy thay đổi chưa commit của transaction hiện tại.

JDBC kiểm tra giá trị cột vật lý và có thể phát hiện lỗi mapping/converter mà việc đọc Entity không dễ bộc lộ. Nếu database trigger hoặc default column thay đổi dữ liệu, JDBC có thể xác nhận giá trị thực sau flush.

Không dùng JDBC qua một connection độc lập để kỳ vọng thấy dữ liệu chưa commit từ transaction khác. Một transaction riêng thường không nhìn thấy thay đổi chưa commit do isolation của database.

## 13. Kiểm tra giá trị do database sinh ra

Database có thể tự sinh hoặc sửa giá trị qua:

- DEFAULT column.
- Trigger BEFORE/AFTER INSERT hoặc UPDATE.
- Generated column.
- Sequence hoặc function database.

JPA Entity trong bộ nhớ không nhất thiết tự cập nhật các giá trị do database sinh ra sau flush. Ví dụ trigger sửa `last_modified_at`, nhưng field trong object Java vẫn giữ giá trị cũ.

Có thể đọc lại sau flush:

```java
entityManager.flush();
entityManager.refresh(order);
```

Hoặc dùng JDBC query để kiểm tra trực tiếp cột. Nếu muốn Hibernate tự nhận giá trị generated trong Entity, cần mapping generated property phù hợp với Hibernate/JPA version và kiểm tra SQL thực tế; không giả định mọi trigger/default đều tự đồng bộ vào object.

## 14. Flush/clear trong kiểm thử batch và bộ nhớ

Khi persist hàng nghìn Entity trong một transaction test hoặc batch job, persistence context giữ các Entity managed và snapshot để dirty checking. Bộ nhớ có thể tăng theo số lượng object.

Chiến lược thường dùng là flush và clear theo từng batch:

```java
int batchSize = 50;

for (int i = 0; i < orders.size(); i++) {
    entityManager.persist(orders.get(i));

    if ((i + 1) % batchSize == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}

entityManager.flush();
entityManager.clear();
```

Flush ghi các thay đổi của batch hiện tại; clear giải phóng các Entity khỏi persistence context để giảm bộ nhớ. Khi dùng `IDENTITY`, Hibernate có thể phải INSERT sớm để lấy ID, và JDBC batching có thể bị giới hạn tùy strategy. Cấu hình batch size và thứ tự insert/update cần đo trên database thực tế.

Không clear giữa batch nếu còn cần sửa các Entity cũ đang managed hoặc dựa vào dirty checking của chúng. Sau clear, muốn cập nhật object đó phải merge hoặc đọc lại theo cách phù hợp.

## 15. Transaction và khả năng nhìn thấy dữ liệu

Flush chỉ gửi SQL trong transaction hiện tại. Khả năng nhìn thấy thay đổi phụ thuộc transaction:

| Người đọc | Có thấy dữ liệu sau flush nhưng trước commit? |
| --- | --- |
| Cùng transaction/persistence context sau clear | Thường có, vì transaction nhìn thấy write của chính nó |
| Transaction khác | Thông thường không, cho tới khi transaction ghi commit thành công |
| Connection JDBC cùng transaction Spring | Có thể thấy write của transaction hiện tại nếu dùng chung transaction/DataSource |
| Replica đọc bất đồng bộ | Có thể chưa thấy ngay sau commit do replication lag |

Trong `@DataJpaTest`, test thường được bọc trong transaction và rollback khi kết thúc. Điều đó không ngăn test flush và đọc lại dữ liệu trong cùng transaction. Nhưng nếu muốn xác minh một transaction khác hoặc một service bất đồng bộ nhìn thấy dữ liệu, phải commit transaction trước rồi mới đọc từ transaction khác.

Không dùng `entityManager.flush()` để chứng minh dữ liệu đã commit hoặc đã được replica nhận. Đó là các mốc khác nhau trong vòng đời dữ liệu.

## 16. Lỗi thường gặp

**Save rồi find vẫn trả dữ liệu dù chưa có SQL INSERT.** Persistence context đang giữ managed Entity. Bật SQL log và dùng flush/clear khi cần kiểm chứng database.

**Clear rồi dữ liệu biến mất.** Có thể đã clear trước flush, khiến thay đổi chưa đồng bộ bị detach. Thực hiện flush trước clear.

**Sau clear, object cũ sửa nhưng database không đổi.** Object đã detached. Đọc lại Entity hoặc merge đúng cách trong transaction.

**Bulk update xong getter vẫn trả trạng thái cũ.** Bulk DML bỏ qua managed Entity. Clear hoặc refresh persistence context sau bulk update.

**Flush không làm transaction khác nhìn thấy dữ liệu.** Flush không phải commit. Commit thành công rồi mới đọc ở transaction khác.

**Đã clear nhưng đọc vẫn không thấy giá trị database mới.** Kiểm tra second-level/query cache, transaction isolation, replica lag và nguồn đọc. Có thể dùng cache bypass hoặc JDBC để đối chiếu.

**Trigger cập nhật cột nhưng Entity vẫn giữ giá trị cũ.** Refresh Entity sau flush hoặc đọc cột bằng JDBC; cấu hình generated property nếu cần tự đồng bộ.

**Unique/FK constraint chỉ lỗi lúc commit.** Một số constraint được defer tới commit. Flush không bảo đảm phát hiện mọi lỗi transaction.

**Batch test tăng bộ nhớ.** Flush và clear theo lô, đồng thời tránh dùng lại các object đã detached như Entity managed.

## 17. Checklist xác minh dữ liệu thực

- Xác định test đang kiểm tra persistence context, SQL đã flush, hay dữ liệu sau commit.
- Gọi `flush()` trước khi đọc lại nếu cần buộc SQL được gửi.
- Gọi `clear()` sau flush để tránh first-level cache trả lại instance cũ.
- Không clear trước khi flush nếu vẫn cần lưu thay đổi đang chờ.
- Nếu cần giữ một Entity managed và nạp lại trạng thái database, cân nhắc `refresh()`.
- Với bulk JPQL DML, xem xét `flushAutomatically` và `clearAutomatically`.
- Kiểm tra second-level/query cache nếu mục tiêu là xác minh database trực tiếp.
- Dùng JdbcTemplate cùng transaction/DataSource để xác minh giá trị cột vật lý khi cần.
- Phân biệt flush với commit; test rollback vẫn có thể flush và đọc lại trong cùng transaction.
- Kiểm tra trigger/default/generated columns sau flush bằng refresh hoặc JDBC.
- Dùng flush/clear theo batch khi persistence context tăng quá lớn.
- Bật SQL logging hoặc Hibernate statistics khi cần chẩn đoán hành vi thực tế.

`flush()` buộc JPA gửi thay đổi đang chờ xuống database; `clear()` loại managed Entity khỏi first-level cache để lần đọc tiếp theo không bị che bởi instance cũ. Kết hợp đúng thứ tự giúp integration test xác minh mapping và SQL đáng tin cậy. Khi cần xác nhận giá trị vật lý, trigger hoặc cập nhật ngoài JPA, kiểm tra thêm bằng JDBC và luôn phân biệt flush với commit.