# FlushModeType.AUTO, COMMIT và ảnh hưởng đến truy vấn trong Spring Data JPA

Trong JPA, **flush** là quá trình đồng bộ những thay đổi đang được quản lý trong persistence context thành các câu lệnh SQL gửi tới database. **Commit** là thao tác xác nhận transaction. Hai khái niệm này không giống nhau: một transaction có thể đã flush nhiều lần nhưng vẫn chưa commit và vẫn có thể rollback.

`FlushModeType.AUTO` và `FlushModeType.COMMIT` điều khiển thời điểm provider cần đồng bộ thay đổi trước khi thực thi truy vấn. Lựa chọn flush mode ảnh hưởng tới việc truy vấn có nhìn thấy những thay đổi chưa commit trong persistence context hay không, số lần SQL được phát ra, thời điểm constraint error xuất hiện và hiệu năng.

Tài liệu dùng Jakarta Persistence (`jakarta.persistence`) trong Spring Boot 3 / Spring Framework 6 trở lên. Với dự án Spring Boot 2 cũ, package JPA thường là `javax.persistence`.

## 1. Persistence context và flush

Persistence context là phạm vi JPA quản lý entity instance. Entity có thể ở trạng thái:

- **New/transient:** đối tượng Java mới, chưa được quản lý.
- **Managed:** đang được persistence context theo dõi; thay đổi thuộc tính có thể được dirty checking phát hiện.
- **Detached:** từng được quản lý nhưng đã tách khỏi persistence context.
- **Removed:** được đánh dấu xóa và sẽ được đồng bộ khi flush.

Ví dụ:

```java
Product product = entityManager.find(Product.class, 10L);
product.setPrice(new BigDecimal("125.00"));
```

Nếu `product` là managed, JPA nhận biết thuộc tính price đã thay đổi. Thông thường không cần gọi `save()` hoặc `merge()` chỉ để cập nhật entity đang managed. Provider sẽ tạo SQL UPDATE khi flush.

Flush có thể phát sinh:

- INSERT cho entity mới đã persist.
- UPDATE cho entity managed có thay đổi.
- DELETE cho entity đã remove.
- Kiểm tra constraint và lỗi database tương ứng.

Flush **không kết thúc transaction**. Sau flush, các thay đổi đã được gửi tới database trong transaction hiện tại nhưng chưa được commit. Transaction vẫn có thể rollback; khi rollback thành công, các thay đổi chưa commit sẽ không trở thành dữ liệu bền vững.

## 2. Hai FlushModeType chuẩn của JPA

Jakarta Persistence định nghĩa hai giá trị portable:

| Flush mode | Ý nghĩa chính | Hành vi khi truy vấn |
|---|---|---|
| `AUTO` | Provider phải bảo đảm kết quả truy vấn phản ánh các thay đổi trong persistence context có thể ảnh hưởng tới kết quả đó | Provider có thể flush trước query hoặc dùng cách khác để bảo đảm kết quả đúng |
| `COMMIT` | Provider phải flush trước khi transaction commit | Ảnh hưởng của thay đổi chưa flush lên kết quả query là không được đặc tả rõ; không nên dựa vào việc query thấy các thay đổi đó |

### 2.1. AUTO

`AUTO` là flush mode mặc định theo JPA cho EntityManager/query nếu không có cấu hình khác. Khi thực thi query, provider phải bảo đảm query nhìn thấy những thay đổi trong persistence context có thể ảnh hưởng tới kết quả.

Provider có thể thực hiện điều đó bằng cách flush trước query. Đặc tả không yêu cầu mọi provider phải gửi SQL trước mọi query; điều bắt buộc là kết quả truy vấn phải có ngữ nghĩa phù hợp với những thay đổi liên quan trong persistence context.

Ví dụ: đổi trạng thái một sản phẩm từ active sang inactive, sau đó truy vấn danh sách sản phẩm active. Query phải phản ánh thay đổi vừa thực hiện nếu thay đổi đó ảnh hưởng tới kết quả.

### 2.2. COMMIT

`COMMIT` yêu cầu provider flush trước khi commit transaction. Trước thời điểm đó, ứng dụng không được giả định query sẽ nhìn thấy các thay đổi chưa flush.

Với COMMIT:

- Provider có thể trì hoãn UPDATE/INSERT/DELETE tới gần commit.
- Query có thể đọc dữ liệu database chưa phản ánh thay đổi đang chờ trong persistence context.
- Provider vẫn có thể flush sớm vì lý do nội bộ; COMMIT không phải lời hứa “không flush cho tới commit”.
- Kết quả query khi có thay đổi chưa flush là không được đặc tả rõ theo JPA. Không viết logic nghiệp vụ phụ thuộc vào việc query có hoặc không thấy thay đổi đó.

Do đó, COMMIT có thể giảm flush không cần thiết trong một số luồng, nhưng đổi lại ứng dụng phải kiểm soát rõ khi nào cần đồng bộ.

## 3. AUTO ảnh hưởng tới query như thế nào?

Giả sử bảng product có ba sản phẩm active. Trong một transaction, ứng dụng tắt một sản phẩm rồi đếm số sản phẩm active:

```java
@Transactional
public long deactivateAndCount(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.setActive(false);

    return entityManager.createQuery("""
        select count(p)
        from Product p
        where p.active = true
        """, Long.class)
        .getSingleResult();
}
```

Với `AUTO`, vì thay đổi `Product.active` có thể ảnh hưởng query đọc Product, provider phải bảo đảm query phản ánh thay đổi đó. Một cách thường gặp là flush UPDATE trước SELECT:

```sql
select id, name, active
from product
where id = ?;

update product
set active = false
where id = ?;

select count(p.id)
from product p
where p.active = true;
```

Nếu ban đầu có ba sản phẩm active, kết quả đếm sau khi tắt một sản phẩm là hai.

Đây là SQL minh họa. SQL thực tế còn phụ thuộc dialect, mapping, cách provider hydrate entity và tối ưu query.

### 3.1. Query không liên quan tới entity đã thay đổi

Giả sử persistence context có một Product đang dirty, nhưng ứng dụng truy vấn một bảng AuditLog không liên quan. Provider có thể biết thay đổi Product không ảnh hưởng kết quả query AuditLog và không cần flush trước query đó.

Hibernate thường dùng khái niệm query spaces để xác định những bảng mà query phụ thuộc. Nếu query không giao với bảng có thay đổi đang chờ, Hibernate có thể bỏ qua flush. Đây là hành vi tối ưu của provider, không nên diễn giải rằng AUTO luôn flush trước mọi câu SELECT.

Khi query có JOIN tới Product hoặc phụ thuộc vào dữ liệu Product theo cách provider nhận diện được, flush có thể cần thiết.

## 4. COMMIT ảnh hưởng tới query như thế nào?

Có thể đặt flush mode ở EntityManager:

```java
@Transactional
public long deactivateAndCount(Long id) {
    entityManager.setFlushMode(FlushModeType.COMMIT);

    Product product = entityManager.find(Product.class, id);
    product.setActive(false);

    return entityManager.createQuery("""
        select count(p)
        from Product p
        where p.active = true
        """, Long.class)
        .getSingleResult();
}
```

Trong ví dụ này, query chạy trước commit. Vì flush mode là COMMIT, JPA không bảo đảm query phải phản ánh thay đổi active=false chưa flush. Provider có thể trả kết quả dựa trên dữ liệu đã commit trong database, hoặc flush sớm vì lý do implementation. Ứng dụng không được dựa vào một kết quả cụ thể.

Nếu nghiệp vụ bắt buộc query phải thấy thay đổi đang chờ, có thể gọi explicit flush:

```java
entityManager.flush();

long count = entityManager.createQuery("""
    select count(p)
    from Product p
    where p.active = true
    """, Long.class)
    .getSingleResult();
```

Sau explicit flush, UPDATE đã được gửi trong transaction hiện tại trước SELECT. Transaction vẫn chưa commit. Nếu sau đó có exception khiến rollback, UPDATE vẫn có thể bị rollback.

## 5. Đặt flush mode ở EntityManager và Query

### 5.1. EntityManager.setFlushMode

```java
entityManager.setFlushMode(FlushModeType.AUTO);

// Hoặc:
entityManager.setFlushMode(FlushModeType.COMMIT);
```

Cách này đặt mode cho EntityManager hiện tại. Các query tạo từ EntityManager sẽ sử dụng mode đó trừ khi query được cấu hình riêng.

### 5.2. Query.setFlushMode

Có thể ghi đè mode cho một query cụ thể:

```java
TypedQuery<Long> query = entityManager.createQuery("""
    select count(p)
    from Product p
    where p.active = true
    """, Long.class);

query.setFlushMode(FlushModeType.AUTO);

Long count = query.getSingleResult();
```

Điều này hữu ích khi EntityManager đang dùng COMMIT nhưng một truy vấn cụ thể cần ngữ nghĩa AUTO. Ngược lại, có thể đặt COMMIT cho query không cần đồng bộ thay đổi trước khi đọc, nếu nghiệp vụ chấp nhận việc không nhìn thấy thay đổi chưa flush.

Không thay flush mode toàn EntityManager một cách tùy tiện ở service dùng chung. Nếu EntityManager được chia sẻ trong transaction, mode có thể ảnh hưởng tới các query tiếp theo trong cùng persistence context. Khi chỉ cần điều chỉnh một query, ưu tiên cấu hình query đó.

## 6. AUTO và COMMIT trong Hibernate

Hibernate triển khai JPA và có thể tối ưu flush dựa trên các bảng mà query sử dụng. Một số điểm cần hiểu:

- Với JPQL/HQL, Hibernate thường biết query space và có thể flush nếu pending changes giao với bảng query cần đọc.
- Query chỉ đọc bảng không liên quan có thể không kích hoạt flush.
- Native SQL khó phân tích phụ thuộc bảng hơn JPQL. Hành vi flush có thể phụ thuộc API đang dùng, synchronization/query-space metadata và phiên bản Hibernate.
- Gọi `EntityManager.flush()` là cách rõ ràng để yêu cầu đồng bộ trước một native query cần dữ liệu mới nhất trong transaction.
- Không nên suy luận từ một lần quan sát SQL rằng mọi provider hoặc phiên bản sẽ có cùng lịch flush.

Hibernate còn có các flush mode riêng ngoài hai mode portable của JPA, ví dụ `MANUAL` hoặc `ALWAYS` tùy API/phiên bản. Đây là extension của provider; code cần portable giữa các JPA provider nên dùng `FlushModeType.AUTO` và `FlushModeType.COMMIT`.

## 7. AUTO không có nghĩa flush trước mọi query

Một hiểu lầm phổ biến là mỗi khi gọi repository hoặc chạy SELECT thì Hibernate luôn gửi toàn bộ thay đổi đang chờ xuống database. Điều này không chính xác.

Ví dụ:

```java
@Transactional
public void updateAndRead(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.setPrice(new BigDecimal("125.00"));

    // Query đọc bảng audit_log, không liên quan Product.
    Long auditCount = entityManager.createQuery(
        "select count(a) from AuditLog a", Long.class
    ).getSingleResult();
}
```

Hibernate có thể không flush Product trước query AuditLog nếu query spaces không giao nhau. Tuy nhiên, khi query đọc Product, flush có thể được yêu cầu để bảo đảm kết quả đúng theo AUTO.

Điểm cốt lõi là AUTO bảo đảm ngữ nghĩa query, còn cách và thời điểm flush cụ thể thuộc implementation. Đừng viết logic dựa trên số lượng SQL chính xác trừ khi đã khóa provider/version và kiểm thử nó.

## 8. Explicit flush: khi nào cần?

Explicit flush hữu ích khi cần:

1. Phát hiện sớm lỗi NOT NULL, UNIQUE, FK hoặc optimistic locking trước khi kết thúc service method.
2. Đảm bảo query tiếp theo đọc được thay đổi vừa thực hiện trong cùng transaction.
3. Điều khiển thứ tự ghi trong một quy trình cần kết quả SQL trước bước tiếp theo.
4. Xử lý batch khi cần flush rồi clear để giới hạn persistence context.

Ví dụ:

```java
@Transactional
public void createAndVerify(String sku) {
    Product product = new Product(sku);
    entityManager.persist(product);

    entityManager.flush();

    boolean exists = entityManager.createQuery("""
        select count(p) > 0
        from Product p
        where p.sku = :sku
        """, Boolean.class)
        .setParameter("sku", sku)
        .getSingleResult();

    if (!exists) {
        throw new IllegalStateException("Product was not persisted");
    }
}
```

Đây là ví dụ minh họa; kiểu dữ liệu boolean trong JPQL và provider cần được xác nhận theo phiên bản. Trong thực tế, có thể dùng query trả về count hoặc truy vấn repository thích hợp.

Flush có thể ném exception do constraint hoặc optimistic locking. Khi lỗi xuất hiện, transaction có thể đã bị đánh dấu rollback-only. Không tiếp tục sử dụng transaction đó như thể vẫn hợp lệ.

Không gọi flush sau mọi `persist` hoặc `setX` chỉ để “chắc chắn”. Flush thường tạo round trip và làm mất cơ hội batching.

## 9. Flush và commit: vòng đời trong transaction

Một transaction có thể diễn ra như sau:

```text
BEGIN
  |
  |-- load entity
  |
  |-- modify managed entity
  |
  |-- query (AUTO có thể flush nếu thay đổi ảnh hưởng query)
  |
  |-- explicit flush (nếu ứng dụng yêu cầu)
  |
  |-- thêm thay đổi khác
  |
  |-- COMMIT
        |
        |-- provider flush thay đổi còn lại
        |-- database commit
        |-- persistence context transaction-scoped kết thúc
        |-- connection được trả về pool
```

Các điểm cần nhớ:

- Flush gửi SQL, commit xác nhận transaction.
- Một transaction có thể flush nhiều lần.
- Rollback sau flush vẫn hủy thay đổi chưa commit.
- Lỗi constraint có thể xuất hiện ở flush hoặc commit.
- Commit thường kích hoạt flush cuối cùng đối với thay đổi còn lại.
- Persistence context transaction-scoped kết thúc theo transaction; entity giữ lại bên ngoài sẽ detached.

## 10. Spring Data JPA repository và flush

Các repository của Spring Data JPA thường có method như:

- `save(entity)`: persist hoặc merge tùy entity được nhận diện là mới hay đã tồn tại.
- `saveAndFlush(entity)`: save và yêu cầu flush ngay.
- `flush()`: yêu cầu flush persistence context.
- `delete(entity)`: đánh dấu/xử lý xóa theo repository và EntityManager.
- `deleteAllInBatch()`: có thể thực hiện bulk operation, có ngữ nghĩa khác so với xóa từng entity.

`save()` không đồng nghĩa SQL đã được gửi ngay. Trong transaction, thay đổi có thể được flush sau đó. `saveAndFlush()` giúp đồng bộ sớm nhưng không commit transaction.

Ví dụ:

```java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Product create(Product product) {
        return repository.saveAndFlush(product);
    }
}
```

Chỉ dùng saveAndFlush khi cần thời điểm flush cụ thể, ví dụ phát hiện constraint violation ngay trong method hoặc cần truy vấn tiếp theo nhìn thấy thay đổi. Nếu không, save thường đủ và cho provider tự tối ưu.

## 11. Bulk JPQL update/delete và persistence context

Bulk update/delete có hành vi đặc biệt: chúng chạy trực tiếp trên database, không đi qua lifecycle của từng entity như dirty checking thông thường. Persistence context có thể còn giữ entity cũ.

Ví dụ:

```java
@Modifying
@Query("""
    update Product p
    set p.active = false
    where p.expiredAt < :now
    """)
int deactivateExpired(@Param("now") Instant now);
```

Sau khi query chạy, một Product đang managed trong persistence context có thể vẫn giữ `active = true` dù database đã cập nhật thành false. Cần đồng bộ/clear persistence context khi thích hợp.

Spring Data JPA hỗ trợ:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Product p
    set p.active = false
    where p.expiredAt < :now
    """)
int deactivateExpired(@Param("now") Instant now);
```

- `flushAutomatically = true`: flush persistence context trước khi thực hiện modifying query để không bỏ sót các thay đổi đang chờ.
- `clearAutomatically = true`: clear persistence context sau query để entity managed cũ không tiếp tục được dùng với trạng thái lỗi thời.

Cần hiểu rằng clear sẽ detach tất cả entity trong persistence context hiện tại. Những thay đổi chưa flush có thể bị mất khỏi context, vì vậy flush trước khi clear nếu cần giữ các thay đổi đó.

Bulk update cũng không tự chạy đầy đủ cascade, entity callback và dirty checking như cập nhật từng entity. Nếu có version field, cần chú ý optimistic locking/version vì bulk query có thể phải cập nhật version tường minh theo thiết kế.

## 12. Read-only transaction và flush mode

Trong Spring, `@Transactional(readOnly = true)` biểu đạt transaction chỉ đọc như một hint cho transaction manager/provider. Với Hibernate, Spring có thể tối ưu flush behavior, ví dụ dùng flush mode phù hợp hoặc đánh dấu entity read-only tùy cấu hình/version.

Không nên coi readOnly=true là cơ chế bảo mật hoặc rào chắn database tuyệt đối ngăn mọi ghi. Nó cũng không đồng nghĩa với JPA `FlushModeType.COMMIT` trong mọi cấu hình. Hãy xem log và cấu hình transaction manager/provider thực tế nếu hành vi flush thay đổi.

Không đặt readOnly=true trên một service method rồi thực hiện ghi dữ liệu với kỳ vọng dirty checking sẽ luôn được flush như transaction ghi bình thường. Tách transaction read/write rõ ràng.

## 13. Hiệu năng: chọn AUTO hay COMMIT?

Không có mode nào luôn nhanh hơn. AUTO có thể flush sớm trước query liên quan, tạo thêm round trip ngay giữa luồng xử lý. COMMIT có thể trì hoãn flush và gom thay đổi, nhưng query trước commit không có bảo đảm nhìn thấy pending changes theo ngữ nghĩa JPA.

| Tình huống | Mode/hành động thường phù hợp | Lưu ý |
|---|---|---|
| Thay đổi entity rồi query có thể bị thay đổi ảnh hưởng | AUTO | Bảo đảm query phản ánh thay đổi liên quan |
| Chỉ thực hiện nhiều thay đổi rồi commit, không cần query trung gian | COMMIT có thể phù hợp | Chỉ dùng khi không dựa vào query đọc pending changes |
| Một query cụ thể bắt buộc nhìn thấy thay đổi vừa sửa | AUTO cho query hoặc explicit flush | Explicit flush đồng bộ mọi pending changes trong context |
| Batch ghi số lượng lớn | Kiểm soát flush/clear theo lô | Đừng flush quá thường xuyên; cấu hình batching |
| Bulk JPQL update/delete | Flush trước và clear sau nếu cần | Tránh persistence context chứa entity stale |
| Query đọc bảng không liên quan | Provider có thể bỏ qua flush trong AUTO | Phụ thuộc query spaces và provider |

Một cách tối ưu thường tốt hơn việc đổi flush mode toàn cục là giảm số entity không cần thiết được quản lý, dùng projection, gom thay đổi hợp lý và chỉ flush ở ranh giới có ý nghĩa.

## 14. Cấu hình log để quan sát flush

Với Hibernate trong Spring Boot, có thể cấu hình ở môi trường phát triển:

```properties
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
logging.level.org.hibernate.orm.transaction=DEBUG
```

Các logger có thể khác nhau theo phiên bản Hibernate. Bind logging có thể làm lộ dữ liệu cá nhân, token, email hoặc thông tin thanh toán; chỉ bật trong môi trường an toàn và tắt khi hoàn tất chẩn đoán.

Khi đọc log, phân biệt:

- SQL SELECT của query.
- SQL INSERT/UPDATE/DELETE do flush phát sinh trước query.
- SQL cuối transaction.
- COMMIT/ROLLBACK.
- Connection acquisition/release.

Đừng chỉ dựa vào log console của `show-sql` để kết luận transaction đã commit. SQL đã xuất hiện trong log có thể vẫn nằm trong transaction chưa commit.

## 15. Kiểm thử ngữ nghĩa flush

Nên kiểm thử bằng database tương thích với production, đặc biệt khi hành vi phụ thuộc Hibernate, native query, constraint và transaction.

Ví dụ kiểm tra AUTO với JPQL query liên quan:

```java
@DataJpaTest
class FlushModeTest {
    @Autowired
    private TestEntityManager testEntityManager;

    @Test
    void autoFlushMakesPendingChangesVisibleToRelatedQuery() {
        Product product = new Product("SKU-1", true);
        testEntityManager.persistAndFlush(product);

        product.setActive(false);

        Long activeCount = testEntityManager.getEntityManager()
            .createQuery("""
                select count(p)
                from Product p
                where p.active = true
                """, Long.class)
            .getSingleResult();

        assertThat(activeCount).isZero();
    }
}
```

Ví dụ giả định Product constructor và getter/setter đúng như project. TestEntityManager của Spring Boot test giúp thao tác persistence context. Query JPQL đọc cùng entity space nên AUTO phải bảo đảm kết quả phản ánh thay đổi liên quan.

Với COMMIT, không viết test khẳng định query luôn trả giá trị cũ hoặc luôn trả giá trị mới khi pending changes chưa flush; JPA không đặc tả kết quả đó. Nếu ứng dụng cần kết quả mới, gọi flush tường minh hoặc dùng AUTO cho query.

Kiểm thử thêm:

- Constraint violation xuất hiện tại flush/commit đúng như mong đợi.
- Rollback sau flush không để lại dữ liệu đã commit.
- Query trên bảng không liên quan không gây flush không cần thiết nếu provider tối ưu như dự kiến.
- Bulk update không để persistence context stale sau khi clear.
- Repository `save()` và `saveAndFlush()` có hành vi khác nhau về thời điểm SQL được gửi, nhưng đều không tự commit transaction bao ngoài.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Query trả kết quả không phản ánh thay đổi chưa flush | Dùng COMMIT và query chạy trước commit | Dùng AUTO hoặc explicit flush trước query |
| SQL UPDATE xuất hiện trước SELECT | AUTO cần bảo đảm query thấy thay đổi liên quan | Đây có thể là hành vi đúng; kiểm tra query space |
| AUTO flush nhiều hơn mong đợi | Query phụ thuộc các bảng có pending changes | Dùng projection/query khác nếu phù hợp; đo SQL trước khi đổi mode |
| Constraint error xuất hiện tại query | AUTO kích hoạt flush trước query | Kiểm tra entity state, validation và database constraint |
| Nghĩ save() đã ghi SQL ngay | Save chỉ đưa entity vào lifecycle phù hợp; flush có thể trì hoãn | Dùng saveAndFlush/flush khi thực sự cần |
| Nghĩ flush là commit | Nhầm đồng bộ SQL với xác nhận transaction | Hiểu transaction boundary; rollback vẫn có thể xảy ra sau flush |
| Entity stale sau bulk update | Bulk JPQL bỏ qua đồng bộ entity trong persistence context | Flush trước và clear sau khi phù hợp |
| Dữ liệu đọc trong readOnly transaction không như dự kiến | Provider tối ưu flush theo hint read-only | Không ghi trong read-only transaction; kiểm tra cấu hình Hibernate |
| SQL bind log lộ dữ liệu | Bật TRACE trong môi trường không an toàn | Hạn chế quyền truy cập log và tắt bind logging |

## 17. Checklist lựa chọn và review

- [ ] Query có cần nhìn thấy thay đổi chưa flush trong persistence context không?
- [ ] Query có phụ thuộc vào bảng mà entity đang dirty hay không?
- [ ] AUTO có gây flush sớm không cần thiết trong workload đã đo?
- [ ] COMMIT có an toàn với luồng nghiệp vụ không truy vấn pending changes?
- [ ] Có thể dùng Query.setFlushMode thay vì thay mode toàn EntityManager không?
- [ ] Explicit flush có lý do rõ ràng và có kiểm soát transaction?
- [ ] Có nhầm flush với commit hoặc nhầm SQL log với dữ liệu đã commit?
- [ ] Bulk JPQL update/delete có flush/clear đúng lúc?
- [ ] Read-only transaction có thực sự chỉ đọc?
- [ ] Integration test kiểm tra ngữ nghĩa trên provider/database production?
- [ ] SQL, bind parameter và transaction log được bật an toàn, chỉ khi cần?

## 18. Kết luận

`AUTO` yêu cầu provider bảo đảm query phản ánh các thay đổi chưa flush có thể ảnh hưởng tới kết quả; provider có thể flush trước query hoặc dùng cách khác. `COMMIT` yêu cầu flush trước commit, còn ảnh hưởng của thay đổi chưa flush lên kết quả query không được JPA đặc tả rõ.

Hãy dùng AUTO khi query cần ngữ nghĩa nhất quán với persistence context. Dùng COMMIT khi luồng ghi không phụ thuộc vào query trung gian nhìn thấy thay đổi chưa flush và đã được kiểm thử. Khi cần đồng bộ rõ ràng trước một thao tác, explicit flush là lựa chọn trực tiếp, nhưng nó không commit transaction. Tối ưu flush mode phải dựa trên SQL log, transaction boundary và benchmark thực tế, không dựa trên giả định rằng COMMIT luôn nhanh hơn AUTO.
