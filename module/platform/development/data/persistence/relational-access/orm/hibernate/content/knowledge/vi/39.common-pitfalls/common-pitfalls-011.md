# Gọi flush sau từng thao tác và làm mất lợi ích của batching

Một batch job cần ghi 10.000 dòng. Code gọi `persist()` cho từng entity rồi gọi `flush()` ngay sau mỗi lần. Kết quả vẫn đúng, nhưng Hibernate không có cơ hội gom nhiều câu INSERT giống nhau thành JDBC batch đủ lớn. Ứng dụng tạo ra nhiều lần đồng bộ ORM/JDBC, giảm throughput và tăng overhead.

Lỗi tương tự xuất hiện khi dùng `repository.saveAndFlush()` trong vòng lặp, gọi `EntityManager.flush()` sau từng thay đổi nhỏ, hoặc chạy một query khiến Hibernate tự động flush thường xuyên mà developer không để ý.

Để xử lý đúng, cần phân biệt ba khái niệm:

- **Flush:** đồng bộ các thay đổi đang pending trong Persistence Context xuống database thông qua SQL, trong transaction hiện tại.
- **JDBC batching:** gom nhiều executions của cùng prepared statement thành một batch ở JDBC driver.
- **Commit:** kết thúc transaction và xác nhận thay đổi thành công theo transaction semantics của database.

`flush()` không phải `commit()`, và gọi flush thường xuyên không tự làm database commit nhanh hơn. Trong workload ghi nhiều rows có cùng SQL shape, flush quá sớm có thể chia nhỏ các nhóm statement và làm mất lợi ích của batching.

~~~text
Không tốt: flush từng entity

persist(A) -> flush -> INSERT A
persist(B) -> flush -> INSERT B
persist(C) -> flush -> INSERT C
...

Tốt hơn: gom một nhóm rồi flush

persist(A)
persist(B)
persist(C)
...
persist(N)
       |
       v
     flush
       |
       v
JDBC batches theo SQL shape
       |
       v
     commit
~~~

**Nguyên tắc cốt lõi:** Để Hibernate tích lũy đủ các thao tác tương thích trước khi flush; cấu hình JDBC batch size phù hợp; chỉ flush ở những boundary có lý do rõ ràng như cuối một chunk, trước query cần đồng bộ, hoặc trước khi clear để giới hạn Persistence Context.

> **Phạm vi:** Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA, JDBC và relational database là bối cảnh minh họa. Tên property, flush modes, batching behavior và hỗ trợ generated keys phụ thuộc Hibernate version, dialect và JDBC driver. Các ví dụ cần được xác nhận trên đúng stack của dự án.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt flush, commit và JDBC statement batching.
2. Giải thích vì sao flush sau mỗi `persist()` hoặc `saveAndFlush()` làm nhỏ batch.
3. Hiểu Hibernate tích lũy INSERT/UPDATE/DELETE actions trong Persistence Context như thế nào.
4. Nhận biết explicit flush và automatic flush.
5. Cấu hình `hibernate.jdbc.batch_size` và các tùy chọn ordering.
6. Hiểu ảnh hưởng của IDENTITY, SEQUENCE, versioning và SQL statement shape.
7. Dùng Spring Data `save`, `saveAll`, `saveAndFlush`, `saveAllAndFlush` đúng semantics.
8. Chọn flush/clear intervals và transaction chunk size riêng biệt.
9. Đo JDBC batch executions thay vì chỉ đếm số lần gọi repository.
10. Viết integration tests chứng minh dữ liệu đúng và batching thực sự hoạt động.

## 2. Flush là gì?

Persistence Context theo dõi entity state và những thao tác cần đồng bộ với database. Hibernate thường trì hoãn SQL để có thể gom và sắp xếp actions.

~~~java
@Transactional
public void createOrder() {
    Order order = new Order("ORD-100");
    entityManager.persist(order);

    // SQL INSERT chưa nhất thiết đã được gửi tại dòng persist().
}
~~~

Khi flush:

~~~java
entityManager.flush();
~~~

Hibernate đồng bộ pending state:

- INSERT entities mới.
- UPDATE managed entities đã thay đổi.
- DELETE entities đã remove.
- Collection/association table changes.
- Các actions khác cần thiết để đồng bộ mapping state.

Flush có thể thực thi nhiều SQL statements. Nó không chỉ tác động entity gần nhất vừa được thay đổi; về cơ bản nó đồng bộ Persistence Context hiện tại theo flush semantics.

## 3. Flush không phải commit

~~~java
@Transactional
public void updateOrder(Long id) {
    Order order = entityManager.find(Order.class, id);
    order.confirm();

    entityManager.flush();

    // SQL UPDATE đã được gửi trong transaction.
    // Transaction vẫn có thể rollback sau đó.
}
~~~

Sau `flush()`:

- SQL có thể đã chạy thành công.
- Constraint errors có thể đã xuất hiện.
- Locks có thể đã được lấy.
- Database transaction vẫn còn mở.
- Transaction có thể rollback.
- Các thay đổi chưa trở thành committed data cho các transactions khác theo isolation semantics.

~~~text
Managed state
     |
   flush()
     |
     v
SQL executes inside transaction
     |
     +---- commit ----> transaction committed
     |
     +---- rollback --> database changes undone
~~~

Vì vậy, gọi flush nhiều lần không tương đương commit từng phần. Nếu muốn commit từng chunk, phải tạo transaction boundary riêng.

## 4. Hibernate trì hoãn SQL để làm gì?

Một lợi ích quan trọng của ORM write-behind là Hibernate có thể:

- Nhóm nhiều INSERT cùng loại.
- Nhóm nhiều UPDATE có cùng SQL shape.
- Sắp xếp actions theo thứ tự phù hợp.
- Thực hiện dirty checking tại flush.
- Phối hợp FK dependencies và collection changes.
- Gom prepared statement executions thành JDBC batches.

Ví dụ:

~~~java
for (int i = 0; i < 100; i++) {
    entityManager.persist(new Product("SKU-" + i));
}
~~~

Trong một transaction và với ID strategy/mapping phù hợp, Hibernate có cơ hội tích lũy nhiều INSERT actions trước khi flush.

Nếu thêm `flush()` sau từng lần persist, mỗi lần flush chỉ có thể nhìn thấy một entity insert mới ở thời điểm đó; batch không thể tích lũy đủ các inserts qua những flush boundaries riêng biệt.

## 5. Vì sao flush từng thao tác làm batching kém hiệu quả?

Code:

~~~java
for (Product product : products) {
    entityManager.persist(product);
    entityManager.flush();
}
~~~

Nếu `hibernate.jdbc.batch_size=50`, điều bạn muốn là nhiều executions của cùng INSERT statement được gom lại. Nhưng mỗi vòng lặp lại yêu cầu Hibernate đồng bộ ngay.

Kết quả thường gần với:

~~~text
flush 1: INSERT 1 row
flush 2: INSERT 1 row
flush 3: INSERT 1 row
...
flush 1000: INSERT 1 row
~~~

Thay vì:

~~~text
flush:
  JDBC batch 1: up to 50 INSERTs
  JDBC batch 2: up to 50 INSERTs
  ...
~~~

JDBC driver vẫn có thể tối ưu protocol riêng, nhưng ứng dụng đã không cho Hibernate tích lũy statement executions theo batch size dự kiến.

## 6. Một flush có thể tạo nhiều JDBC batches

Giả sử:

~~~properties
hibernate.jdbc.batch_size=50
~~~

Trong một flush có 230 INSERT statements cùng SQL shape và cùng batching conditions, Hibernate có thể chia thành các batches có kích thước tối đa 50, với phần dư ở batch cuối.

~~~text
230 compatible INSERT executions
       |
       v
Batch 1: 50
Batch 2: 50
Batch 3: 50
Batch 4: 50
Batch 5: 30
~~~

Đây là mô hình minh họa. Số lượng thực tế phụ thuộc action ordering, entity types, SQL shape, driver, generated keys và các giới hạn khác.

Một flush có nhiều loại entity hoặc statement shapes khác nhau sẽ tạo nhiều nhóm batch riêng, không phải một batch duy nhất cho mọi SQL.

## 7. JDBC batch chỉ gom statement tương thích

Hibernate không thể gom tùy ý mọi SQL vào một JDBC batch. Các executions thường cần cùng prepared statement/SQL shape và cùng batching context.

Ví dụ có thể batch tốt:

~~~sql
INSERT INTO product (sku, name, price) VALUES (?, ?, ?)
INSERT INTO product (sku, name, price) VALUES (?, ?, ?)
INSERT INTO product (sku, name, price) VALUES (?, ?, ?)
~~~

Các SQL khác shape:

~~~sql
INSERT INTO product (sku, name) VALUES (?, ?)
INSERT INTO product (sku, name, price) VALUES (?, ?, ?)
UPDATE product SET price = ? WHERE id = ?
~~~

thuộc các nhóm khác nhau.

Các nguyên nhân làm giảm khả năng batching:

- Entity types khác nhau.
- SQL khác số/cấu trúc columns.
- Dynamic insert/update tạo nhiều SQL shapes.
- ID generator cần INSERT ngay.
- Mapping hoặc operation không hỗ trợ batching.
- Flush xen kẽ quá thường xuyên.
- Driver/dialect limitations.

## 8. Cấu hình JDBC batching

Hibernate property thường dùng:

~~~properties
hibernate.jdbc.batch_size=50
~~~

Trong Spring Boot:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Ý nghĩa:

- `hibernate.jdbc.batch_size`: số statement executions tối đa Hibernate cố gắng gom trong JDBC batch.
- `hibernate.order_inserts`: sắp xếp insert actions để tăng cơ hội nhóm cùng SQL.
- `hibernate.order_updates`: sắp xếp update actions tương tự và có thể cải thiện batching/lock ordering ở workload phù hợp.

Đây là giới hạn/cấu hình batching, không phải cam kết mọi flush sẽ có đúng 50 statements hoặc mọi thao tác sẽ batch được.

Bắt đầu bằng một giá trị vừa phải như 25 hoặc 50 rồi đo. Đừng chọn batch size lớn chỉ vì muốn giảm số lần gọi JDBC.

## 9. Flush interval và JDBC batch size là hai thứ khác nhau

| Tham số | Ý nghĩa |
|---|---|
| JDBC batch size | Tối đa bao nhiêu statement executions được gom trong một batch |
| Flush interval | Sau bao nhiêu thao tác/records ứng dụng gọi flush |
| Clear interval | Sau bao nhiêu records ứng dụng detach toàn bộ entities |
| Transaction chunk size | Bao nhiêu records được commit trong một transaction |

Ví dụ:

~~~text
Transaction chunk = 1,000 records
Flush/Clear interval = 100 entities
JDBC batch size = 50 statements
~~~

Một transaction có thể chứa 10 flushes; mỗi flush có thể tạo một hoặc nhiều JDBC batches. Các giá trị có thể khác nhau và cần tuning riêng.

## 10. Ví dụ batch insert đúng cách

~~~java
@Transactional
public void importProducts(List<ProductInput> inputs) {
    int batchSize = 50;
    int count = 0;

    for (ProductInput input : inputs) {
        entityManager.persist(toEntity(input));

        if (++count % batchSize == 0) {
            entityManager.flush();
        }
    }

    entityManager.flush();
}
~~~

Đây là ví dụ minh họa cho một transaction. Các entities được persist thành nhóm rồi flush, tạo cơ hội cho Hibernate batch compatible statements.

Nếu danh sách rất lớn, Persistence Context có thể tích lũy quá nhiều managed entities. Khi đó, dùng `flush()` rồi `clear()` ở interval phù hợp, với điều kiện code không còn cần managed references cũ.

## 11. Flush rồi clear khi cần giới hạn Persistence Context

~~~java
@Transactional
public void importProducts(Iterable<ProductInput> inputs) {
    int batchSize = 50;
    int count = 0;

    for (ProductInput input : inputs) {
        entityManager.persist(toEntity(input));

        if (++count % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Thứ tự quan trọng:

1. Tích lũy một nhóm operations.
2. Flush để đồng bộ SQL và cho JDBC batch hoạt động.
3. Clear để detach managed entities và giảm L1 context.
4. Tiếp tục nhóm tiếp theo.

`flush()` không giải phóng managed entities. `clear()` trước flush có thể detach pending changes mà chưa đồng bộ. Nếu flush thất bại, rollback theo policy và không tiếp tục dùng Session như thể batch đã thành công.

## 12. Không clear sau từng entity

~~~java
for (ProductInput input : inputs) {
    entityManager.persist(toEntity(input));
    entityManager.flush();
    entityManager.clear();
}
~~~

Pattern này vừa flush từng entity vừa clear ngay. Nó có thể giữ memory thấp, nhưng làm batching mất cơ hội và tạo overhead flush liên tục.

Hãy clear theo interval đủ lớn để tạo batch hữu ích, chẳng hạn sau 50–100 entities trong workload thử nghiệm. Nếu entity graph lớn, interval nên tính theo tổng managed entities chứ không chỉ số root objects.

Không có một con số tối ưu cho mọi domain; cần benchmark.

## 13. Batch update managed entities

Ví dụ:

~~~java
@Transactional
public void increasePrices(List<Long> productIds) {
    int count = 0;

    for (Long id : productIds) {
        Product product = entityManager.find(Product.class, id);

        if (product != null) {
            product.increasePrice();
        }

        if (++count % 50 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Khi flush, Hibernate phát UPDATE cho các entities dirty. Nếu nhiều rows có cùng update SQL shape, JDBC batching có thể gom chúng.

Nhưng ví dụ này có thể có N SELECTs do `find()` từng ID. Batching UPDATE không tự giải quyết read-side N+1. Có thể tối ưu input IDs, load theo chunk hoặc dùng bulk update nếu domain semantics cho phép.

## 14. Batch update khác bulk update

**Batch update qua managed entities:**

~~~java
for (Product product : products) {
    product.setActive(false);
}
entityManager.flush();
~~~

Hibernate phát nhiều UPDATE statements có thể được gom bằng JDBC batching. Entity lifecycle, dirty checking và versioning vẫn tham gia theo mapping.

**Bulk JPQL update:**

~~~java
int changed = entityManager.createQuery(
    """
    update Product p
    set p.active = false
    where p.expiryDate < :cutoff
    """
)
.setParameter("cutoff", cutoff)
.executeUpdate();
~~~

Đây thường là một câu UPDATE set-based, không phải một batch entity update. Bulk DML bypass per-entity dirty checking/callbacks và có thể làm Persistence Context stale.

Chọn theo yêu cầu lifecycle và business rules, không chỉ theo tên “batch”.

## 15. Batch delete

Nếu cần entity removal semantics:

~~~java
@Transactional
public void deleteProducts(List<Long> ids) {
    int count = 0;

    for (Long id : ids) {
        Product product = entityManager.find(Product.class, id);
        if (product != null) {
            entityManager.remove(product);
        }

        if (++count % 50 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
}
~~~

Hibernate có thể batch compatible DELETE statements nếu mapping/provider/driver hỗ trợ.

Nếu dùng bulk `delete from Product`, per-entity callbacks/cascade/orphan removal và custom delete semantics có thể khác. Với soft delete hoặc audit requirements, test riêng từng delete path.

## 16. Spring Data save() không giống saveAndFlush()

Spring Data JPA:

~~~java
repository.save(product);
~~~

thường chọn `EntityManager.persist()` hoặc `merge()` tùy new-state detection. Nó không có nghĩa “flush ngay”.

Ngược lại:

~~~java
repository.saveAndFlush(product);
~~~

lưu entity rồi gọi flush trên Persistence Context hiện tại.

Vì vậy code:

~~~java
for (Product product : products) {
    repository.saveAndFlush(product);
}
~~~

có thể ép flush sau mỗi item, khiến Hibernate không gom đủ insert/update statements vào batch như mong muốn.

Trong transaction, thường gọi `save()` cho từng item hoặc persist theo chunk, rồi flush ở boundary đã chọn.

## 17. saveAll() không tự bảo đảm một JDBC batch

~~~java
repository.saveAll(products);
~~~

Spring Data JPA thường lặp qua entities và gọi save logic cho từng entity. Nó không tự bảo đảm database nhận đúng một batch, cũng không đảm bảo mọi entity được persist theo một JDBC batch duy nhất.

JDBC batching vẫn phụ thuộc:

- Transaction boundary.
- Hibernate batch configuration.
- ID generation strategy.
- SQL shape.
- Entity ordering.
- Driver support.
- Flush timing.

`saveAll()` thường tốt hơn việc caller gọi `saveAndFlush()` sau từng row, nhưng cần xem implementation/version và SQL thật.

## 18. saveAllAndFlush() flush một lần sau saveAll

~~~java
repository.saveAllAndFlush(products);
~~~

Spring Data JPA method này gọi saveAll và flush sau đó theo contract implementation của version đang dùng.

Nếu `products` là một List khổng lồ, tất cả entities có thể vẫn nằm trong Persistence Context đến khi flush. Method này không tự chia list thành các chunks hoặc clear context theo interval.

Dùng nó cho tập dữ liệu vừa phải; với import lớn, tự điều khiển chunking/flush/clear hoặc dùng Spring Batch writer phù hợp.

## 19. Đừng gọi flush chỉ để lấy ID nếu generator không yêu cầu

Một lý do phổ biến khiến code flush quá sớm là muốn đọc generated ID ngay sau persist.

~~~java
entityManager.persist(product);
entityManager.flush();
Long id = product.getId();
~~~

ID timing phụ thuộc `@GeneratedValue` strategy:

- `IDENTITY` thường cần INSERT để lấy database-generated key sớm.
- `SEQUENCE` có thể lấy sequence value trước INSERT.
- UUID/application-generated ID có thể có ngay.
- Các generator khác có semantics riêng.

Nếu ID đã có từ generator, không cần flush chỉ để lấy ID. Nếu IDENTITY cần INSERT ngay, đây là một giới hạn batching riêng của generator, không phải lý do để flush sau mọi entity.

## 20. IDENTITY có thể ngăn insert batching

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với IDENTITY, Hibernate thường phải INSERT row để lấy generated identity value. Điều này có thể ngăn hoặc hạn chế JDBC insert batching cho entity dùng generator đó.

Vì vậy, dù bạn bỏ `flush()` khỏi vòng lặp, insert batching có thể vẫn không đạt hiệu quả như mong muốn.

Sequence-based generation:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

có thể thuận lợi hơn cho JDBC insert batching vì ID có thể được cấp trước khi INSERT. Tuy nhiên behavior phụ thuộc database, sequence allocation, dialect và Hibernate version. Chỉ thay ID strategy khi schema/domain cho phép và đã benchmark.

## 21. Ordering giúp tăng cơ hội batching

Một flush có thể chứa:

~~~text
INSERT Product A
INSERT Category X
INSERT Product B
INSERT Category Y
INSERT Product C
~~~

Các SQL khác nhau làm batch grouping bị chia nhỏ. `hibernate.order_inserts=true` cho phép Hibernate sắp xếp insert actions để nhóm cùng entity/table/statement shape trong những trường hợp phù hợp.

Tương tự `hibernate.order_updates=true` có thể sắp xếp updates.

Đánh đổi:

- Hibernate cần thêm công việc sắp xếp.
- Thứ tự SQL thay đổi so với thứ tự gọi `persist()`.
- Có thể ảnh hưởng lock acquisition ordering và performance.
- Không đảm bảo mọi statements đều batch được.

Kiểm tra FK constraints, generated IDs, lifecycle assumptions và DB deadlocks sau khi bật.

## 22. Dynamic insert/update có thể tạo nhiều SQL shapes

Hibernate `@DynamicInsert`/`@DynamicUpdate` có thể tạo SQL chỉ gồm những columns cần thiết hoặc dirty columns.

Điều này giảm columns được ghi trong một số workload, nhưng các entities có tập dirty fields khác nhau có thể sinh SQL shapes khác nhau:

~~~sql
UPDATE product SET price = ? WHERE id = ?
UPDATE product SET name = ?, price = ? WHERE id = ?
UPDATE product SET active = ? WHERE id = ?
~~~

Mỗi shape là một nhóm batch khác nhau. Nếu mỗi entity thay đổi các fields khác nhau, khả năng gom batch có thể giảm.

Không bật dynamic SQL chỉ vì muốn UPDATE ít columns; đo cả SQL shape diversity và batching benefit.

## 23. Versioned entities và batching

Entity có optimistic version:

~~~java
@Version
private long version;
~~~

Hibernate có thể batch versioned UPDATE statements trong các cấu hình/driver hỗ trợ row counts đáng tin cậy. Cần xác minh `hibernate.jdbc.batch_versioned_data` theo Hibernate version và driver.

Batching không được làm mất optimistic-lock checking. Hibernate cần biết affected row counts để phát hiện stale updates. Nếu driver báo update counts không đúng hoặc batch result không đáng tin, behavior/version-specific settings có thể ảnh hưởng.

Test concurrent updates và xác nhận `OptimisticLockException`/provider exception vẫn được phát hiện đúng.

## 24. Flush có thể xảy ra tự động

Bạn có thể không gọi `entityManager.flush()` nhưng Hibernate vẫn flush theo flush mode.

Các thời điểm phổ biến:

- Trước transaction commit.
- Trước một JPQL/HQL query khi pending changes có thể ảnh hưởng kết quả query và flush mode là AUTO.
- Khi application gọi explicit `flush()`.
- Một số API/operations có semantics yêu cầu đồng bộ state.

Ví dụ:

~~~java
entityManager.persist(new Product("SKU-NEW"));

Long count = entityManager.createQuery(
    "select count(p) from Product p",
    Long.class
).getSingleResult();
~~~

Với flush mode AUTO, Hibernate có thể flush INSERT trước query count để kết quả phản ánh thay đổi pending trong cùng persistence context.

Nếu query không liên quan tới tables/query spaces đang pending, Hibernate có thể tránh flush trong một số trường hợp. Đừng giả định mọi query luôn flush hoặc không bao giờ flush; phụ thuộc provider, query spaces và API.

## 25. Query-triggered flush có thể chia batch ngoài dự kiến

Ví dụ:

~~~java
for (ProductInput input : inputs) {
    entityManager.persist(toProduct(input));

    // Query kiểm tra tồn tại sau mỗi insert.
    boolean exists = repository.existsBySku(input.sku());
}
~~~

Query có thể kích hoạt auto-flush nếu nó cần thấy pending changes. Khi đó Hibernate đồng bộ INSERT trước khi query chạy, làm batch bị chia nhỏ.

Giải pháp có thể là:

- Validate dữ liệu trước khi bắt đầu write batch.
- Dùng unique constraint để enforce uniqueness.
- Đưa checks vào query theo chunk.
- Tránh SELECT xen giữa từng persist nếu không cần.
- Thiết kế idempotent upsert/database-specific strategy nếu phù hợp.

Không hạ flush mode để che query-triggered flush nếu điều đó làm sai kết quả query hoặc consistency semantics.

## 26. FlushModeType.AUTO và COMMIT của Jakarta Persistence

JPA `FlushModeType` chuẩn có hai modes chính:

~~~java
entityManager.setFlushMode(FlushModeType.AUTO);
~~~

- `AUTO`: provider phải bảo đảm các pending changes có thể ảnh hưởng kết quả query được nhìn thấy theo semantics của specification; provider có thể flush.
- `COMMIT`: provider trì hoãn flush tới commit theo contract; query có thể không nhìn thấy pending changes chưa flush tùy semantics/provider.

Không dùng COMMIT để né flush từng query mà chưa kiểm tra correctness. Nếu query cần thấy pending inserts/updates, có thể phải gọi explicit flush.

## 27. Hibernate FlushMode có thêm lựa chọn provider-specific

Hibernate `Session` có flush modes riêng như `AUTO`, `COMMIT`, `ALWAYS`, `MANUAL` theo version/API.

~~~java
Session session = entityManager.unwrap(Session.class);
session.setHibernateFlushMode(FlushMode.MANUAL);
~~~

`MANUAL` có thể giảm auto-flush trong workload được kiểm soát, nhưng đòi hỏi application chịu trách nhiệm gọi flush đúng lúc. Nếu quên flush, dữ liệu pending có thể không được ghi theo kỳ vọng trước khi context kết thúc.

`ALWAYS` có thể flush trước mỗi query và làm tăng overhead đáng kể. Chỉ dùng các Hibernate-specific modes khi hiểu rõ query visibility, transaction lifecycle và version behavior.

Không nhầm Hibernate `FlushMode` với JPA `FlushModeType`; package/type khác nhau.

## 28. Native query và flush behavior cần kiểm tra riêng

Native SQL không nhất thiết có cùng query-space knowledge như JPQL/HQL. Behavior auto-flush có thể khác tùy:

- Gọi native query qua `EntityManager` hay Hibernate `Session`.
- Flush mode.
- Query synchronized spaces được khai báo hay không.
- Hibernate version.

Ví dụ Hibernate Session có thể khai báo synchronized query spaces cho native query để provider biết tables liên quan:

~~~java
NativeQuery<?> query = session.createNativeQuery(
    "select count(*) from product"
);
query.addSynchronizedEntityClass(Product.class);
~~~

API cụ thể phụ thuộc Hibernate version. Nếu native SQL phải thấy pending ORM writes, cách chắc chắn là thiết kế explicit flush/synchronized spaces phù hợp và test. Không dựa vào một behavior vô tình của test DB.

## 29. Vì sao không nên flush trong helper method tùy tiện?

Một helper:

~~~java
public void addLine(Order order, OrderLine line) {
    order.addLine(line);
    entityManager.flush();
}
~~~

có thể được gọi nhiều lần trong cùng transaction. Helper đang ép flush toàn bộ Persistence Context, không chỉ thay đổi OrderLine mới thêm.

Hệ quả:

- Các entities không liên quan cũng bị dirty-checked/flush.
- JDBC batches của nhiều aggregates bị chia.
- Constraint errors xuất hiện sớm hơn.
- SQL order thay đổi.
- Helper có side effect persistence khó nhìn thấy từ caller.

Đặt flush ở unit-of-work boundary có chủ đích thay vì rải trong domain/helper methods.

## 30. Flush từng item còn làm tăng dirty-checking work

Mỗi lần flush, Hibernate phải xử lý pending state trong Persistence Context. Với stateful Session, số managed entities tăng dần nếu không clear.

Nếu flush sau mỗi item:

- Hibernate có thể phải xét ngày càng nhiều managed entries.
- Action queue/collection changes được xử lý nhiều lần.
- Nhiều lần chuyển trạng thái ORM/JDBC.
- JDBC batches nhỏ.
- Tổng chi phí có thể tăng đáng kể khi job dài.

Chi phí chính xác phụ thuộc bytecode enhancement, entity mappings, dirty-checking optimizations và số managed entities. Không khẳng định mọi flush đều scan toàn bộ fields theo cùng một cách; hãy đo trên mapping thực tế.

## 31. Flush quá thường xuyên không giải phóng locks

Một số người gọi flush sau mỗi row với hy vọng database “xong” và giải phóng tài nguyên. Nhưng flush không commit transaction.

Các row/table locks có thể vẫn được giữ tới transaction completion. Connection vẫn có thể bị giữ; transaction log/MVCC resources vẫn tồn tại theo DB semantics.

Nếu muốn giải phóng locks giữa chunks, cần commit transaction chunk rồi bắt đầu transaction mới — và chấp nhận partial progress/restart semantics tương ứng.

## 32. Constraint errors xuất hiện tại flush

~~~java
entityManager.persist(new Product("DUPLICATE-SKU"));
entityManager.flush();
~~~

Unique constraint có thể bị phát hiện ngay khi INSERT được thực thi. Nếu không explicit flush, lỗi có thể chỉ xuất hiện tại auto-flush hoặc commit.

Gọi flush thường xuyên làm lỗi xuất hiện sớm hơn trong loop, nhưng không làm dữ liệu “an toàn hơn” một cách tự động.

Khi flush ném exception:

- Transaction có thể đã bị đánh dấu rollback-only hoặc database transaction ở trạng thái lỗi.
- Không tiếp tục ghi các rows còn lại như bình thường.
- Rollback theo transaction manager.
- Đóng/discard persistence context nếu provider state không còn an toàn.
- Retry chunk trong unit of work mới nếu lỗi transient và operation idempotent.

## 33. Không bắt lỗi flush rồi tiếp tục cùng transaction

Anti-pattern:

~~~java
for (Product product : products) {
    entityManager.persist(product);

    try {
        entityManager.flush();
    } catch (PersistenceException ex) {
        log.warn("Skip row", ex);
        // Tiếp tục sử dụng cùng EntityManager.
    }
}
~~~

Sau một persistence exception, transaction và Session thường không còn ở trạng thái an toàn để tiếp tục. Với DB như PostgreSQL, một statement error có thể khiến transaction aborted cho tới rollback.

Nếu cần skip bad records:

- Validate trước khi persist khi có thể.
- Tách record validation khỏi write transaction.
- Chia chunk nhỏ để lỗi rollback phạm vi giới hạn.
- Dùng savepoint strategy có hỗ trợ rõ ràng nếu thực sự cần.
- Ghi rejected record trong transaction riêng sau khi rollback.
- Không giả định catch exception là có thể tiếp tục cùng unit of work.

## 34. Spring Data: saveAndFlush trong loop

Không tốt:

~~~java
@Transactional
public void importProducts(List<Product> products) {
    for (Product product : products) {
        repository.saveAndFlush(product);
    }
}
~~~

Mỗi vòng gọi `saveAndFlush()` yêu cầu flush Persistence Context hiện tại. Nó có thể flush cả các changes khác đang pending trong cùng transaction, không chỉ entity truyền vào.

Cách phù hợp hơn cho dataset vừa phải:

~~~java
@Transactional
public void importProducts(List<Product> products) {
    for (Product product : products) {
        repository.save(product);
    }

    entityManager.flush();
}
~~~

Với dataset lớn, chia interval:

~~~java
@Transactional
public void importProducts(List<Product> products) {
    int count = 0;

    for (Product product : products) {
        repository.save(product);

        if (++count % 50 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
}
~~~

Cần đảm bảo code không giữ hoặc tiếp tục thay đổi các entities đã detach sau `clear()`.

## 35. saveAll() và saveAllAndFlush()

| Method | Ý nghĩa khái quát |
|---|---|
| `save(entity)` | Lưu entity qua persist/merge decision |
| `saveAll(entities)` | Lưu một iterable; không tự đảm bảo JDBC batch |
| `saveAndFlush(entity)` | Save rồi flush Persistence Context |
| `saveAllAndFlush(entities)` | Save cả iterable rồi flush |

Các method thuộc Spring Data JPA. Chi tiết implementation có thể đổi theo version, nhưng không nên xem `saveAllAndFlush()` là transaction commit hoặc automatic chunk processor.

Với batch import, có thể dùng `saveAll()` trong transaction và flush một lần hoặc theo chunks, đồng thời bật Hibernate JDBC batching. Kiểm tra generated SQL, entity state và memory.

## 36. Bulk DML không cần flush sau từng row

Nếu tất cả Products cũ cần inactive:

~~~java
int count = entityManager.createQuery(
    """
    update Product p
    set p.active = false
    where p.expiryDate < :cutoff
    """
)
.setParameter("cutoff", cutoff)
.executeUpdate();
~~~

Đây là set-based UPDATE. Database thực hiện một statement theo predicate thay vì application load/update từng entity.

Nếu có pending managed changes trước bulk query, cần xem flush semantics để tránh mất hoặc ghi đè thay đổi. Sau bulk DML, Persistence Context có thể stale; thường cần flush pending changes trước (nếu có) và clear sau theo đúng use case.

Bulk DML bypass per-entity callbacks/cascade/dirty checking và cần xử lý version/audit/cache riêng.

## 37. Transaction chunking khác flush intervals

Ví dụ:

~~~java
@Transactional
public void importOneMillion() {
    for (Product product : allProducts()) {
        entityManager.persist(product);

        if (count % 100 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }
}
~~~

Dù flush/clear mỗi 100 rows, toàn bộ một triệu rows vẫn có thể thuộc **một transaction**. Connection và transaction resources có thể bị giữ lâu; một lỗi cuối job có thể rollback toàn bộ.

Nếu domain cho phép partial commits:

~~~text
Chunk 1: BEGIN -> 1,000 rows -> COMMIT
Chunk 2: BEGIN -> 1,000 rows -> COMMIT
Chunk 3: BEGIN -> 1,000 rows -> COMMIT
~~~

Mỗi transaction chunk có thể chứa vài flush/clear intervals. Cần checkpoint/idempotency/retry để restart an toàn.

## 38. Một thiết kế batch import ba tầng

~~~text
Input chunk: 1,000 records
    |
    +-- ORM flush/clear every 100 entities
    |       |
    |       +-- flush
    |       +-- clear
    |       +-- next 100
    |
    +-- JDBC batch size: up to 50 compatible statements
    |
    +-- Transaction commit after chunk
    |
    +-- Save checkpoint after commit
~~~

Ba boundaries có mục đích riêng:

- Input chunk giới hạn số records đang giữ.
- Flush/clear interval điều khiển ORM context.
- JDBC batch size điều khiển statement grouping.
- Transaction chunk điều khiển atomicity và lock lifetime.
- Checkpoint theo sau commit để restart.

Không cần mọi interval dùng cùng một số.

## 39. Batch updates và SQL ordering

Với nhiều entities:

~~~java
for (Product product : products) {
    product.changeCategory(category);
    product.updatePrice(...);
}
entityManager.flush();
~~~

Hibernate có thể phát các UPDATE cùng SQL shape theo action queue. `hibernate.order_updates=true` có thể sắp xếp để tăng batching và có thể giảm một số deadlock patterns do update ordering khác nhau.

Tuy nhiên, ordering không bảo đảm DB không deadlock; transaction concurrency, indexes, FK locks và access pattern vẫn quan trọng.

Test với concurrent workload nếu ordering được bật để tối ưu production.

## 40. Batch inserts với parent-child associations

Khi insert graph:

~~~java
for (OrderInput input : inputs) {
    Order order = map(input);

    for (OrderLine line : order.getLines()) {
        line.setOrder(order);
    }

    entityManager.persist(order);
}
entityManager.flush();
~~~

Hibernate phải tuân thủ FK dependencies và mapping ownership. Nó có thể phát parent INSERT trước child INSERT, nhưng batching có thể chia theo entity/table.

Không flush sau từng child hoặc parent nếu không cần. Cũng không clear giữa lúc graph còn pending; flush đầy đủ ở aggregate/chunk boundary trước clear.

## 41. Batching không đồng nghĩa một network round trip

JDBC `executeBatch()` cho phép driver gửi nhiều executions theo cách batching. Nhưng:

- Driver có thể rewrite batch thành multi-row INSERT.
- Driver có thể gửi nhiều protocol messages.
- Database vẫn xử lý constraints/indexes từng row hoặc theo implementation.
- Batch có thể bị chia bởi packet/parameter limits.
- Generated keys có thể thay đổi behavior.

Vì vậy, đừng tính network round trips bằng cách đếm `persist()` hoặc flush calls. Dùng driver/DB metrics và benchmark thực tế.

## 42. Batching với versioned updates cần giữ row-count semantics

Với `@Version`, mỗi UPDATE có optimistic-lock predicate:

~~~sql
UPDATE product
SET price = ?, version = ?
WHERE id = ? AND version = ?
~~~

Batch execution phải trả update counts đủ để Hibernate phát hiện stale rows. Driver có thể trả `SUCCESS_NO_INFO` hoặc behavior riêng cho batch results; Hibernate version/configuration cần tương thích.

Test:

- Update thành công nhiều rows.
- Một row bị sửa đồng thời.
- Optimistic lock conflict xuất hiện.
- Batch rollback đúng transaction.
- Không mất concurrency checks vì bật batching.

## 43. Batch size quá lớn cũng có thể gây hại

Giá trị lớn có thể:

- Tăng memory cho parameter/batch buffers.
- Tăng thời gian mỗi flush/executeBatch.
- Tạo packet quá lớn hoặc vượt giới hạn driver.
- Làm transaction/lock duration dài.
- Tăng rollback cost.
- Tăng áp lực database CPU/IO.
- Tăng tail latency cho workload cạnh tranh.

Tuning theo các bước nhỏ: 0 (tắt), 10, 25, 50, 100. Giữ dataset, DB, concurrency và transaction boundaries giống nhau; so throughput, p95, heap, GC, batch size distribution và DB waits.

## 44. Batch size quá nhỏ hoặc flush interval quá ngắn

Nếu batch size 50 nhưng flush mỗi 2 entities, mỗi flush có thể kết thúc batch với chỉ 2 executions. Bạn đã cấu hình batch size 50 nhưng workload không tạo đủ cơ hội sử dụng nó.

Nếu flush interval 100 nhưng chỉ có 20 records mỗi transaction, batch thực tế tối đa vẫn bị giới hạn bởi số records trong transaction/chunk.

Hãy xét quan hệ:

~~~text
effective batch size <=
min(configured JDBC batch size,
    compatible statements available before batch boundary)
~~~

Đây là mô hình tư duy, không phải công thức bao quát mọi driver/provider implementation.

## 45. SQL logs giúp thấy flush boundaries

Hibernate 6 thường dùng:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

SQL logs có thể cho thấy INSERT/UPDATE xuất hiện sau từng record hay theo từng nhóm. Nhưng SQL log thường không đủ chứng minh driver đã gửi một JDBC batch thực sự.

Bind logging có thể lộ PII/secrets; chỉ bật có kiểm soát trên fake data hoặc có redaction/access policy.

Kết hợp datasource proxy, JDBC driver metrics, Hibernate Statistics và DB monitoring để quan sát batch execution.

## 46. Hibernate Statistics và batch observations

Có thể bật:

~~~properties
hibernate.generate_statistics=true
~~~

Statistics cung cấp các counters như entity inserts/updates, flush count, prepared statement count và cache statistics tùy version.

~~~java
Statistics stats = sessionFactory.getStatistics();

long flushesBefore = stats.getFlushCount();
long insertsBefore = stats.getEntityInsertCount();

// Run one isolated batch.

long flushes =
    stats.getFlushCount() - flushesBefore;
long inserts =
    stats.getEntityInsertCount() - insertsBefore;
~~~

`prepareStatementCount` không đồng nghĩa số network round trips hoặc batch executions. Statistics là SessionFactory-wide và workload song song có thể làm nhiễu; dùng test cô lập.

Datasource proxy hoặc JDBC instrumentation có thể giúp đếm `addBatch()`/`executeBatch()` và batch sizes thực tế.

## 47. Test chứng minh flush từng row tạo nhiều flushes

Một test có thể chạy hai strategies trên database test đã reset:

~~~java
@Test
void comparePerRowFlushWithChunkFlush() {
    // Strategy A: persist + flush per entity.
    // Capture flush count and JDBC batch executions.

    // Reset test data/statistics.

    // Strategy B: persist many entities, flush once per chunk.
    // Capture the same metrics.
}
~~~

Không assert một số tuyệt đối cố định nếu Hibernate/driver version khác nhau. Test nên xác nhận:

- Per-row strategy tạo nhiều flush boundaries hơn.
- Chunk strategy cho Hibernate cơ hội tạo batches lớn hơn.
- Số rows persisted cuối cùng giống nhau.
- Transaction outcome đúng.
- SQL/driver instrumentation cho thấy batching thực tế khi mapping hỗ trợ.

## 48. Test với IDENTITY và SEQUENCE

Tạo hai mappings trong test schema:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

và:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

Chạy cùng workload, cùng batch size và transaction settings. So sánh:

- INSERT timing.
- JDBC batch executions.
- Generated ID availability.
- SQL count.
- Throughput.
- DB sequence/identity behavior.

Không giả định mọi DBMS hỗ trợ SEQUENCE giống nhau; với MySQL có thể dùng identity/auto increment, còn PostgreSQL hỗ trợ sequences. Test trên dialect production.

## 49. Test automatic flush do query

Scenario:

~~~java
entityManager.persist(new Product("SKU-AUTO"));

Long count = entityManager.createQuery(
    "select count(p) from Product p",
    Long.class
).getSingleResult();
~~~

Với AUTO mode, query có thể cần thấy pending insert và kích hoạt flush.

Một test khác query entity/table không liên quan để quan sát provider có thể tránh flush theo query-space analysis. Cách thực hiện phụ thuộc Hibernate version.

Đừng viết test yêu cầu mọi query phải flush hoặc không flush. Hãy test behavior nghiệp vụ cần thiết: query có nhìn thấy pending state theo flush mode đang cấu hình không?

## 50. Test flush không phải commit

Test transaction:

1. Persist entity.
2. Gọi flush.
3. Ném exception hoặc rollback.
4. Mở transaction/EntityManager mới.
5. Xác nhận row không được commit.

Test này chứng minh explicit flush không làm thay đổi transaction outcome thành committed.

Nếu test framework tự rollback test transaction cuối method, hãy thiết kế commit/rollback boundary rõ ràng để không nhầm transaction của test với transaction của service.

## 51. Test flush interval và clear cho memory

Với batch lớn, so sánh:

- Persist toàn bộ rồi flush một lần.
- Flush theo chunks.
- Flush + clear theo chunks.
- Flush từng entity.

Quan sát:

- Peak heap và allocation rate.
- GC pauses.
- Managed entity count nếu có instrumentation.
- Flush duration.
- JDBC batch sizes.
- Transaction duration.
- Rows/second.

Clear làm giảm L1 context, nhưng application List vẫn có thể giữ references. Để test memory có ý nghĩa, dùng streaming input và không lưu tất cả entities đã xử lý trong một collection.

## 52. Không dùng System.gc() để bù cho flush design

~~~java
entityManager.flush();
System.gc();
~~~

`System.gc()` không giải quyết việc Persistence Context vẫn giữ managed entities, cũng không bảo đảm GC chạy ngay. Nếu cần giới hạn L1 memory, dùng clear ở boundary đúng; nếu heap vẫn tăng, phân tích retaining paths.

Không gọi GC sau mỗi batch trong production; có thể gây full-GC pauses và làm throughput kém hơn.

## 53. Khi nào flush sớm là hợp lý?

Flush sớm không phải lúc nào cũng sai. Có các trường hợp cần explicit flush:

- Muốn phát hiện constraint violation tại một boundary cụ thể.
- Cần DB-generated value/trigger result trước khi tiếp tục.
- Query native hoặc query khác cần nhìn thấy pending changes.
- Cần đồng bộ trước khi clear/detach.
- Muốn tách write phase và read-after-write phase trong cùng transaction.
- Cần bảo đảm statement order trước một thao tác phụ thuộc DB.

Hãy flush khi có yêu cầu correctness hoặc resource boundary rõ, không phải sau mọi setter/persist/save.

## 54. Flush trước clear là boundary phổ biến

Nếu cần giảm Persistence Context:

~~~java
entityManager.flush();
entityManager.clear();
~~~

Đây là một boundary hợp lý trong batch processing. Nó vẫn có thể tạo JDBC batches trong từng nhóm trước khi clear.

Chú ý:

- Clear detach tất cả managed entities trong context.
- Không dùng lại object cũ như managed.
- Không clear khi còn pending changes chưa flush.
- Nếu flush lỗi, rollback và xử lý Session theo lifecycle đúng.
- Không giữ graph lớn trong application memory rồi nghĩ clear đã giải phóng heap.

## 55. Spring Batch chunk writer

Spring Batch thường mô hình hóa một transaction cho mỗi chunk:

~~~text
ItemReader -> ItemProcessor -> ItemWriter
                         |
                    commit interval
                         |
                       commit
~~~

Ví dụ khái niệm:

~~~java
new StepBuilder("productImport", jobRepository)
    .<ProductInput, Product>chunk(1000, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .build();
~~~

Chunk size điều khiển transaction commit interval. Writer vẫn cần có chiến lược Hibernate/JPA flush phù hợp; không gọi saveAndFlush sau từng item trong writer nếu mục tiêu là batching.

Spring Batch writer implementations có thể flush theo contract/version riêng. Xem behavior của writer đang dùng trước khi thêm explicit flush/clear trùng lặp.

## 56. TransactionTemplate cho chunk boundaries

Với ứng dụng không dùng Spring Batch:

~~~java
for (List<ProductInput> chunk : chunks(inputs, 1000)) {
    transactionTemplate.executeWithoutResult(status -> {
        int count = 0;

        for (ProductInput input : chunk) {
            entityManager.persist(toEntity(input));

            if (++count % 100 == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
    });
}
~~~

Đây là pseudocode: cần bảo đảm EntityManager/persistence context transaction-scoped được Spring quản lý và mỗi callback có transaction mới theo transaction manager thực tế. Không chia sẻ managed entities giữa callbacks.

Chunk commit tạo partial progress; cần checkpoint/idempotency/retry nếu job có thể restart.

## 57. Một transaction lớn vẫn có thể chứa nhiều JDBC batches

Ví dụ:

~~~java
@Transactional
public void importAll() {
    for (int i = 0; i < 100_000; i++) {
        entityManager.persist(createProduct(i));

        if ((i + 1) % 100 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }
}
~~~

Mỗi 100 records được flush/clear, nhưng toàn bộ method vẫn có một transaction. JDBC batches hoạt động trong transaction đó; commit chỉ xảy ra khi method qua transaction interceptor.

Đây có thể là lựa chọn nếu cần all-or-nothing và DB chịu được transaction lớn. Nếu không, chia transaction chunks riêng.

## 58. Một số nguyên nhân batching không hoạt động dù đã bỏ flush

Nếu batch vẫn chỉ có một hoặc vài statements:

1. `hibernate.jdbc.batch_size` chưa được cấu hình vào runtime SessionFactory.
2. Entity dùng IDENTITY generator.
3. SQL shapes khác nhau do dynamic insert/update hoặc field sets.
4. Nhiều entity/table interleaving không được order.
5. Flush/query boundaries quá thường xuyên.
6. Driver/dialect không hỗ trợ hoặc có giới hạn.
7. Generated keys/result handling ngăn batching.
8. Versioned updates/row count behavior không tương thích.
9. Transaction không bao trùm các writes cần batch.
10. Code thực tế gọi `saveAndFlush()` hoặc query-triggered auto-flush.

Kiểm tra SQL và JDBC instrumentation trước khi đổi hàng loạt mapping.

## 59. Checklist thiết kế batch write

**Flush behavior**

- [ ] Có explicit flush sau từng item không?
- [ ] Có `saveAndFlush()` trong vòng lặp không?
- [ ] Có query xen giữa persist/update làm AUTO flush không?
- [ ] Flush mode được chọn có giữ đúng query visibility không?
- [ ] Flush chỉ xảy ra ở boundary cần thiết?

**JDBC batching**

- [ ] `hibernate.jdbc.batch_size` đã vào runtime config?
- [ ] SQL shapes đủ tương thích để gom?
- [ ] ID generator có cho phép insert batching?
- [ ] `order_inserts`/`order_updates` có lợi trên workload?
- [ ] Driver và dialect hỗ trợ?
- [ ] JDBC batch executions đã được đo thực tế?

**Memory và transaction**

- [ ] Persistence Context có cần flush+clear theo interval?
- [ ] Clear chỉ xảy ra sau flush thành công?
- [ ] Transaction chunk size có phù hợp?
- [ ] Connection/locks không bị giữ quá lâu?
- [ ] Checkpoint/idempotency có nếu commit từng phần?

**Correctness**

- [ ] Constraint errors được xử lý tại đúng boundary?
- [ ] Rollback chunk và Session lifecycle an toàn?
- [ ] Optimistic locking vẫn được kiểm tra?
- [ ] Cascade/FK ordering đúng?
- [ ] Bulk DML không phá callbacks/cache semantics?

## 60. Bài tập thực hành

1. Viết import 1.000 Products với `flush()` sau từng `persist()`; đo flush count.
2. Chuyển sang flush mỗi 50 entities; so SQL/throughput.
3. Bật `hibernate.jdbc.batch_size=50`; đo `executeBatch()` thật qua datasource proxy.
4. Thử `saveAndFlush()` trong loop và so với `saveAll()` trong một transaction.
5. Dùng `saveAllAndFlush()` với List lớn; quan sát Persistence Context và heap.
6. So sánh IDENTITY và SEQUENCE trên DB production-like.
7. Bật `order_inserts`/`order_updates`, đo batch sizes và lock behavior.
8. Tạo query xen giữa từng persist để quan sát auto-flush.
9. Thử `FlushModeType.COMMIT`, xác nhận query visibility và explicit flush requirements.
10. Tạo unique constraint violation ở giữa chunk; xác nhận rollback và Session disposal.
11. Flush + clear mỗi 100 entities trong transaction 1.000 rows; kiểm tra memory và commit behavior.
12. Chia transaction thành chunks 1.000 rows; test checkpoint/restart sau chunk lỗi.
13. So sánh managed entity batch update với bulk JPQL update; xác nhận callbacks/version/cache behavior.
14. Test batch update với `@Version` và concurrent transaction.
15. Benchmark batch sizes 0, 10, 25, 50, 100 trên cùng workload và báo cáo rows/second, p95, heap và DB waits.

## 61. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Nhiều thao tác ghi trong một use case"] --> B{"Có lý do correctness cần flush ngay?"}
    B -- "Có" --> C["Flush tại boundary cần thiết"]
    B -- "Không" --> D["Để Hibernate tích lũy pending actions"]
    C --> E{"Cần giới hạn Persistence Context?"}
    D --> E
    E -- "Có" --> F["Flush theo chunk rồi clear"]
    E -- "Không" --> G["Flush cuối unit of work"]
    F --> H["JDBC batch theo SQL shape/config"]
    G --> H
    H --> I{"Transaction quá dài?"}
    I -- "Có" --> J["Chia transaction chunks + checkpoint"]
    I -- "Không" --> K["Commit transaction"]
    J --> L["Đo SQL batches, heap, locks và throughput"]
    K --> L
~~~

## 62. Tài liệu tham khảo

- [Hibernate ORM User Guide — Batching](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — JDBC batching, ordering, identifier generation và batch processing.
- [Hibernate ORM User Guide — Flushing](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — Persistence Context synchronization và flush modes.
- [Hibernate ORM Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/) — `Session`, `FlushMode`, query APIs và version-specific behavior.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — `EntityManager.flush()` và `FlushModeType`.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — `save`, `saveAll`, `saveAndFlush`, modifying queries và repository transactions.
- [Spring Batch Reference](https://docs.spring.io/spring-batch/reference/) — chunk-oriented processing, commit intervals, retry và restart.
- [JDBC API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) — `addBatch`, `executeBatch` và batch update counts.

Tài liệu `current` có thể mô tả behavior mới hơn ứng dụng. Đặc biệt IDENTITY batching, native-query auto-flush, versioned batching và Hibernate flush modes cần được xác nhận bằng Javadocs/release notes của đúng version đang triển khai.

## 63. Tổng kết

**Gọi flush sau từng thao tác thường làm Hibernate mất cơ hội tích lũy đủ statement executions để tạo JDBC batches hiệu quả.**

- `flush()` đồng bộ toàn bộ pending state của Persistence Context vào SQL trong transaction hiện tại; nó không commit.
- `hibernate.jdbc.batch_size` chỉ tạo cơ hội gom các statement tương thích; không bảo đảm mọi SQL được batch.
- `flush()` sau mỗi `persist()` hoặc `saveAndFlush()` trong loop thường tạo batch nhỏ và tăng overhead.
- `save()`/`saveAll()` không tự đồng nghĩa JDBC batching; phải có transaction, SQL shapes phù hợp, ID strategy và driver support.
- `IDENTITY`, query-triggered auto-flush, dynamic SQL và statement ordering có thể làm giảm batching.
- Nếu cần giới hạn L1 memory, dùng `flush()+clear()` theo chunk; nếu cần giải phóng locks/connection giữa chunks, phải commit transaction riêng.
- Constraint errors có thể xuất hiện tại flush; sau persistence exception, rollback và dùng unit of work mới theo policy.
- Đo JDBC `executeBatch()`, batch sizes, SQL, heap, GC, connection pool và DB waits để chứng minh lợi ích.

Hãy đặt flush tại **boundary có ý nghĩa về correctness hoặc resource management**, không rải nó sau mỗi thao tác. Khi Hibernate có đủ operations tương thích để gom, JDBC batching mới có cơ hội giảm chi phí giao tiếp và tăng throughput cho tác vụ ghi hàng loạt.
