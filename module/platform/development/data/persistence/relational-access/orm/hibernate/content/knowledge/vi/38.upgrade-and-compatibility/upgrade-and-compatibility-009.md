# Chạy kiểm thử hồi quy về dữ liệu, SQL, đồng thời và hiệu năng trong Hibernate

## 1. Vì sao nâng cấp Hibernate cần kiểm thử hồi quy nhiều lớp?

Một lần nâng Hibernate, Spring Boot, JDBC driver hoặc database có thể làm ứng dụng vẫn khởi động và unit tests vẫn xanh, nhưng hành vi persistence đã thay đổi ở những điểm khó thấy:

- Một enum được lưu bằng ordinal thay vì string, hoặc converter đổi cách biểu diễn dữ liệu.
- SQL được Hibernate sinh ra thay đổi JOIN, predicate, pagination hoặc kiểu bind.
- Một association trước đây được tải trong một query nay phát thêm SELECT.
- Một transaction gặp optimistic-lock conflict ở thời điểm khác.
- Truy vấn chạy nhanh trên H2 nhưng chậm hoặc lỗi trên PostgreSQL/MySQL production.
- Timestamp bị làm tròn theo precision khác, UUID đổi representation hoặc sequence allocation tạo khoảng ID khác.
- Bulk update bypass entity lifecycle và làm audit/version/cache không còn như mong đợi.
- Thời gian response tăng dù kết quả trả về vẫn chính xác.

Vì vậy, kiểm thử hồi quy cho Hibernate phải kiểm tra **cả dữ liệu, SQL, đồng thời và hiệu năng** theo từng use case. Chỉ kiểm tra ứng dụng có compile hoặc repository có trả về đúng một entity là chưa đủ.

Một regression suite tốt trả lời bốn câu hỏi:

1. Dữ liệu sau khi ghi và đọc có giữ đúng ý nghĩa nghiệp vụ không?
2. Hibernate có phát SQL và thao tác database đúng như ứng dụng mong đợi không?
3. Khi nhiều transaction cùng hoạt động, dữ liệu có nhất quán và lỗi cạnh tranh có được xử lý đúng không?
4. Chi phí truy vấn, thời gian và tài nguyên có nằm trong giới hạn chấp nhận được không?

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xây baseline trước và sau khi nâng cấp Hibernate/driver/database.
2. Kiểm tra round-trip dữ liệu, schema migration, converters, enum, timestamp, UUID và numeric precision.
3. Kiểm thử SQL semantics mà không phụ thuộc alias hoặc whitespace của một phiên bản Hibernate.
4. Phân biệt query executions, JDBC statement executions, batch operations và database round trips.
5. Kiểm tra transaction boundaries, flush/commit/rollback và generated values.
6. Viết concurrency tests cho optimistic locking, pessimistic locking và isolation behavior.
7. Đo query count, N+1, latency, throughput, rows, memory và connection pool usage.
8. Sử dụng Testcontainers để kiểm thử trên database/driver gần production.
9. Thiết kế CI regression gates có ngưỡng hợp lý, tránh flaky tests.
10. Chuẩn bị rollout và rollback khi nâng cấp ORM trong hệ thống đang có dữ liệu.

## 2. Phạm vi của một regression suite

Không nên gom tất cả kiểm thử vào một test class khổng lồ. Mỗi lớp test bảo vệ một loại hợp đồng khác nhau.

| Lớp kiểm thử | Câu hỏi cần trả lời | Công cụ thường dùng |
|---|---|---|
| Unit test domain | Quy tắc nghiệp vụ có đúng không? | JUnit, AssertJ, Mockito |
| Repository integration test | Mapping và query có đúng trên database không? | Spring Boot Test, EntityManager |
| Data migration test | Schema và dữ liệu cũ có chuyển đúng không? | Flyway/Liquibase, Testcontainers |
| SQL regression test | Query shape, bind type, row count có hợp lý không? | Hibernate Statistics, datasource proxy |
| Transaction test | Flush, commit, rollback có đúng không? | TransactionTemplate, database |
| Concurrency test | Conflict và isolation có đúng không? | Nhiều threads/transactions, latches |
| Performance test | Latency/throughput/resource có đạt mục tiêu không? | JMH phù hợp, Gatling, k6, profiler |
| API integration test | Serialization và endpoint có kích hoạt SQL ngoài ý muốn không? | MockMvc/WebTestClient |
| Compatibility matrix | Các phiên bản ORM/driver/database được hỗ trợ có hoạt động không? | CI matrix, Testcontainers |

Một số test có thể kiểm tra nhiều khía cạnh cùng lúc, nhưng nên giữ assertion rõ. Ví dụ một integration test có thể xác nhận giá trị tiền sau round-trip và query count của read service; không nên biến nó thành benchmark toàn hệ thống.

### 2.1. Regression test khác test mới như thế nào?

Regression test bảo vệ hành vi đã được xác nhận trước một thay đổi. Nó thường có:

- Một use case cụ thể.
- Fixture tái hiện được.
- Kết quả kỳ vọng được xác định trước.
- Một chỉ số hoặc invariant có thể đo.
- Một lý do rõ ràng vì sao thay đổi sai sẽ làm test fail.

Ví dụ: “Khi tải trang Order detail có 100 lines, số SELECT không tăng một câu cho mỗi line.” Đây là hợp đồng có thể kiểm chứng.

Ngược lại, “repository chạy nhanh” không phải assertion đủ cụ thể.

## 3. Lập baseline trước khi nâng cấp

Trước khi thay Hibernate version, JDBC driver hoặc database engine, hãy ghi lại hành vi hiện tại của những use cases quan trọng.

### 3.1. Ghi nhận dependency và môi trường

Baseline cần lưu:

- Java runtime và JVM flags.
- Spring Boot version.
- Hibernate ORM Core version.
- Hibernate Envers version nếu sử dụng.
- Jakarta Persistence API version.
- JDBC driver name/version.
- Database engine/version và dialect.
- Connection pool và cấu hình pool.
- Transaction isolation mặc định.
- Schema migration version.
- Cache provider và cấu hình L1/L2/query cache.
- Các Hibernate properties ảnh hưởng SQL, batching, fetch và schema.
- Logging/metrics instrumentation đang bật.

Ví dụ bảng baseline:

| Thành phần | Trước nâng cấp | Sau nâng cấp |
|---|---|---|
| Java | 21.x | 21.x |
| Spring Boot | 3.x.y | 3.x.z |
| Hibernate ORM | 6.x.y | 6.x.z |
| JDBC driver | 42.x | 42.x |
| Database | PostgreSQL 16.x | PostgreSQL 16.x |
| Schema | migration V42 | migration V42 |
| Batch size | 32 | 32 |
| L2 cache | bật | bật |

Các version trên chỉ minh họa cách ghi nhận. Dự án cần dùng version thật từ dependency lock/BOM và môi trường triển khai.

### 3.2. Cố định workload

So sánh trước/sau chỉ có ý nghĩa nếu workload tương đương:

- Cùng dữ liệu fixture hoặc cùng snapshot đã khử danh tính.
- Cùng số lượng orders/customers/lines.
- Cùng query filters và page sizes.
- Cùng số concurrent users/threads.
- Cùng cache warm/cold state.
- Cùng connection pool limits.
- Cùng database resource allocation.
- Cùng JVM heap/GC settings.

Nếu trước nâng cấp chạy 1.000 rows và sau nâng cấp chạy 10 rows, không thể so sánh latency trực tiếp.

### 3.3. Chọn use cases đại diện

Không cần benchmark mọi repository method. Chọn các luồng quan trọng hoặc có rủi ro ORM cao:

1. Tải danh sách có phân trang và sort.
2. Tải aggregate detail với to-one và to-many associations.
3. Tìm kiếm có nhiều predicates và optional filters.
4. Tạo aggregate có nhiều children.
5. Cập nhật entity có @Version.
6. Xóa mềm hoặc xóa có cascade.
7. Báo cáo có aggregate/grouping.
8. Batch import/update.
9. Đọc lịch sử Envers nếu dùng.
10. Transaction có nhiều writers cùng sửa một record.

Mỗi use case có thể có baseline riêng về kết quả, SQL count, latency và concurrency.

## 4. Kiểm thử dữ liệu sau nâng cấp

Mục tiêu là xác nhận giá trị được lưu và đọc lại vẫn giữ đúng ý nghĩa. Không chỉ kiểm tra object Java trước khi persist.

### 4.1. Round-trip test

Ví dụ entity Product:

```java
@Entity
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    @Column(nullable = false, precision = 18, scale = 4)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private ProductStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    protected Product() {}

    public Product(
            Long id,
            BigDecimal price,
            ProductStatus status,
            Instant createdAt) {
        this.id = id;
        this.price = price;
        this.status = status;
        this.createdAt = createdAt;
    }

    // getters...
}
```

Test:

```java
@Test
void persistsAndReadsProductValues() {
    Instant createdAt = Instant.parse("2026-01-15T10:20:30Z");
    BigDecimal price = new BigDecimal("123.4500");

    Long id = transactionTemplate.execute(status -> {
        Product product = new Product(
            101L, price, ProductStatus.ACTIVE, createdAt
        );
        entityManager.persist(product);
        entityManager.flush();
        return product.getId();
    });

    Product reloaded = transactionTemplate.execute(status ->
        entityManager.find(Product.class, id)
    );

    assertThat(reloaded.getPrice())
        .isEqualByComparingTo("123.4500");
    assertThat(reloaded.getStatus())
        .isEqualTo(ProductStatus.ACTIVE);
    assertThat(reloaded.getCreatedAt())
        .isEqualTo(createdAt);
}
```

Ví dụ giả định fixture và transaction manager đã được cấu hình. Khi test dùng TransactionTemplate, đảm bảo transaction ghi đã kết thúc trước khi mở transaction đọc mới. Nếu dùng một outer test transaction, find có thể trả lại object từ L1 cache và không chứng minh dữ liệu được đọc từ database.

### 4.2. So sánh BigDecimal đúng cách

`BigDecimal.equals` xét cả giá trị và scale:

```java
new BigDecimal("10.0").equals(new BigDecimal("10.00"))
// false
```

`compareTo` xét giá trị số:

```java
new BigDecimal("10.0").compareTo(new BigDecimal("10.00"))
// 0
```

Với cột DECIMAL/NUMERIC, database có thể chuẩn hóa scale theo schema hoặc dialect. Test cần xác định contract:

- Giá trị số có đúng không?
- Scale có phải một phần của business representation không?
- Có rounding policy không?
- Có overflow hoặc truncation khi precision vượt giới hạn không?

Không tự động dùng compareTo nếu scale là một phần bắt buộc của nghiệp vụ; cũng không dùng equals nếu database không bảo toàn scale và business chỉ quan tâm giá trị.

### 4.3. Timestamp, timezone và precision

Các kiểu thời gian cần được kiểm tra riêng:

- Instant: một thời điểm trên timeline UTC.
- LocalDateTime: ngày giờ địa phương, không chứa timezone.
- OffsetDateTime: ngày giờ kèm offset.
- LocalDate: ngày lịch, không có thời gian.

Database column có thể lưu timestamp với precision microseconds/milliseconds thay vì nanoseconds. Ví dụ một Instant có nanoseconds 123456789 có thể được lưu với precision thấp hơn.

Test nên xác định precision contract. Nếu database chỉ bảo toàn microseconds, fixture nên dùng giá trị đã căn chỉnh hoặc assert theo precision được hỗ trợ. Không bỏ qua khác biệt bằng tolerance quá rộng, vì có thể che lỗi timezone.

### 4.4. Enum mapping

Nếu dùng:

```java
@Enumerated(EnumType.ORDINAL)
private ProductStatus status;
```

giá trị enum được lưu theo ordinal. Thêm hoặc đổi thứ tự enum constants có thể làm dữ liệu cũ mang ý nghĩa khác.

Thông thường, nếu schema cho phép, EnumType.STRING ổn định hơn về thứ tự:

```java
@Enumerated(EnumType.STRING)
private ProductStatus status;
```

Nhưng đổi từ ORDINAL sang STRING là migration dữ liệu, không phải chỉ sửa annotation. Regression test phải đọc dữ liệu được tạo bằng representation cũ và xác nhận migration đổi đúng.

Nếu dùng AttributeConverter, test cả hai chiều Java ↔ database representation, bao gồm null, giá trị chưa biết và backward compatibility.

### 4.5. UUID, Boolean, JSON và binary types

Các kiểu dữ liệu này phụ thuộc dialect/driver:

- UUID có thể lưu native UUID, binary hoặc varchar.
- Boolean có thể được biểu diễn bằng BOOLEAN, BIT, CHAR hoặc số.
- JSON có thể là native JSON/JSONB hoặc text.
- Binary/LOB có thể có giới hạn và semantics streaming khác nhau.

Tạo round-trip tests trên database thật của dự án, kiểm tra cả giá trị rỗng, null, Unicode, nested JSON và kích thước lớn hợp lý.

### 4.6. Unicode và collation

Kiểm tra tên có dấu, ký tự supplementary Unicode, case folding và accent-sensitive comparisons. Query equality có thể có kết quả khác theo collation của database. H2 không đại diện đầy đủ cho collation production. Dùng Testcontainers với database thực tế khi so sánh semantics.

## 5. Kiểm thử schema migration và dữ liệu cũ

Một ứng dụng có thể hoạt động với schema mới tạo từ đầu nhưng lỗi khi nâng một database đã có dữ liệu nhiều năm.

### 5.1. Test từ schema phiên bản trước

Quy trình:

1. Tạo database theo migration version cũ.
2. Seed dữ liệu đại diện bằng schema cũ.
3. Chạy Flyway/Liquibase migrations.
4. Khởi động ứng dụng với Hibernate schema validation.
5. Đọc các records cũ qua entity mapping mới.
6. Ghi records mới.
7. Kiểm tra constraints, indexes, defaults và relationships.
8. Kiểm tra dữ liệu không bị mất hoặc đổi nghĩa.

Không chỉ tạo schema mới nhất từ đầu rồi gọi đó là migration regression test.

### 5.2. Kiểm tra expand-and-contract

Trong rolling deployment, có thể có phiên bản ứng dụng cũ và mới chạy đồng thời. Migration nên chia pha nếu schema thay đổi không tương thích ngay:

- **Expand:** thêm cột/bảng/index mới theo cách code cũ vẫn hoạt động.
- **Deploy compatible code:** code mới có thể đọc/ghi theo giai đoạn chuyển tiếp.
- **Backfill:** chuyển dữ liệu cũ theo batch có kiểm soát.
- **Switch reads/writes:** chuyển logic sang schema mới sau khi dữ liệu sẵn sàng.
- **Contract:** loại bỏ cột/constraint cũ khi không còn writer nào dùng.

Regression test nên kiểm tra trạng thái giữa các pha, không chỉ trạng thái cuối.

### 5.3. Kiểm tra defaults và nullability

Nếu thêm cột deleted BOOLEAN NOT NULL DEFAULT FALSE, test cần xác nhận:

- Rows cũ được backfill đúng.
- Inserts từ ứng dụng mới có indicator đúng.
- Inserts từ writer cũ trong giai đoạn chuyển tiếp không tạo NULL.
- Constraint NOT NULL được áp dụng đúng.
- Query predicate không loại nhầm rows NULL.

SQL NULL có logic ba giá trị. Predicate deleted = false không trả rows có deleted NULL.

### 5.4. Kiểm tra unique constraints và indexes

Migration có thể tạo partial unique index, composite index hoặc thay đổi collation. Test:

- Duplicate active keys bị chặn.
- Các records đã archived/soft-deleted được xử lý theo business rule.
- Restore không tạo duplicate active records.
- Query filters có thể dùng index theo execution plan phù hợp.
- Migration không vô tình làm mất constraint cũ.

### 5.5. Dữ liệu baseline và audit history

Nếu bật Envers hoặc soft delete sau khi bảng đã có dữ liệu, lịch sử không tự xuất hiện cho các thay đổi trước ngày bật. Migration test phải xác định baseline policy, revision metadata và cách đọc history sau cutover. Không khẳng định audit trail đầy đủ từ lúc entity ra đời nếu chưa tạo baseline.

## 6. Kiểm thử SQL regression: kiểm tra semantics, không đóng đinh alias

Hibernate có thể thay đổi SQL text giữa các version mà không làm thay đổi kết quả. Ví dụ alias p1_0 có thể đổi thành p0_, whitespace và thứ tự columns cũng có thể thay đổi.

### 6.1. Tránh snapshot toàn bộ SQL nếu không có lý do

Một assertion so sánh toàn bộ SQL string dễ fail khi Hibernate đổi alias, quoting, column order hoặc formatting dù semantics không đổi.

Thay vào đó, test những hợp đồng có ý nghĩa:

- Query trả đúng rows và ordering.
- Predicate tenant/status không bị mất.
- Pagination có LIMIT/OFFSET hoặc cú pháp tương đương đúng.
- Query không tạo N+1.
- Statement count nằm trong budget.
- Bind types tương thích column types.
- DML ảnh hưởng đúng số rows.
- Native SQL vẫn tương thích schema.

### 6.2. Khi nào nên kiểm tra SQL shape?

Có những trường hợp SQL shape là một phần quan trọng của regression contract:

- Không được join collection lớn trong query phân trang.
- Phải có tenant predicate.
- Query phải dùng keyset predicate đúng.
- Không được phát SELECT riêng cho từng association.
- Phải dùng parameter placeholders thay vì nối literal.
- Một bulk operation phải tác động đúng scope.

Khi cần kiểm tra SQL, normalize các phần không có ý nghĩa như alias/whitespace một cách thận trọng. Đừng dùng regex đơn giản làm SQL parser tổng quát.

### 6.3. SQL text và bind parameters

SQL log với dấu ? cho biết query shape, không cho biết giá trị. Để kiểm tra bind type, dùng JDBC instrumentation hoặc test driver behavior trên dữ liệu synthetic. Tránh bật bind TRACE trên dữ liệu production vì email, tenant IDs, account identifiers hoặc secrets có thể bị ghi vào logs.

### 6.4. Native queries và stored procedures

Native SQL không được Hibernate rewrite như HQL. Khi nâng dialect hoặc driver, kiểm tra:

- Tên cột/bảng và quoting.
- Named/positional parameter binding.
- ResultSet mapping.
- Scalar type conversion.
- Pagination syntax.
- Stored procedure result sets/update counts.
- Generated keys và output parameters.

Một native query có thể vẫn compile trong Java nhưng lỗi ở runtime khi driver hoặc database thay đổi.

## 7. Kiểm tra thứ tự, pagination và null semantics

### 7.1. Ordering phải deterministic

Nếu query dùng:

```hql
select o
from PurchaseOrder o
order by o.createdAt desc
```

nhiều rows có cùng createdAt có thể đổi thứ tự giữa các lần chạy hoặc sau nâng cấp database. Nếu API cần thứ tự ổn định, thêm tie-breaker:

```hql
select o
from PurchaseOrder o
order by o.createdAt desc, o.id desc
```

Regression test nên assert thứ tự theo contract, không dựa vào incidental row order của database.

### 7.2. Pagination boundaries

Kiểm tra:

- Page đầu, page giữa, page cuối.
- Page rỗng.
- Page size 1 và giới hạn tối đa.
- Records có sort key trùng nhau.
- Insert/delete đồng thời giữa hai lần lấy page.
- Count query và content query.
- Collection fetch không làm phân trang trong memory.

Nếu dùng keyset pagination, test cả boundary value, duplicate sort keys và direction ASC/DESC.

### 7.3. NULL semantics

Các database có thể khác nhau về null ordering mặc định và function behavior. Nếu thứ tự null là một phần API, chỉ định rõ bằng query/case expression hoặc hỗ trợ dialect thích hợp, rồi test trên database production.

Kiểm tra cả:

- IS NULL/IS NOT NULL.
- Optional associations.
- LEFT JOIN và predicates trong WHERE so với ON.
- Aggregate COUNT, SUM, AVG khi không có rows.
- Empty IN collection.
- Null parameter binding.

### 7.4. Count query của Page

Spring Data Page có thể chạy data query và count query riêng. Sau nâng cấp, query parser hoặc generated count query có thể khác. Kiểm tra totalElements, totalPages, content và filters đồng nhất. Với GROUP BY/HAVING hoặc joins, cân nhắc khai báo count query tường minh.

## 8. Kiểm thử mapping và lifecycle

### 8.1. Identifier generation

Kiểm tra các chiến lược:

- IDENTITY.
- SEQUENCE.
- TABLE.
- UUID/application-assigned IDs.

Với SEQUENCE, allocationSize và sequence increment trong database phải tương thích. Thay đổi generator có thể ảnh hưởng số lần lấy sequence và khoảng ID. Không giả định ID liên tục; rollback hoặc pooled allocation có thể tạo gaps.

### 8.2. Optimistic version

Với thuộc tính @Version, test xác nhận:

- INSERT tạo version ban đầu theo provider.
- UPDATE thành công tăng version.
- UPDATE stale version bị từ chối.
- Rollback không commit state/version mới.
- Bulk JPQL DML không tự thực hiện optimistic locking như từng managed entity update.
- Custom SQL update/delete giữ version predicate và row-count semantics phù hợp.

Không hard-code giá trị version ban đầu nếu provider contract không yêu cầu; assert monotonic/change behavior phù hợp.

### 8.3. Cascade và orphan removal

Tạo test cho từng aggregate operation:

- Persist parent với children.
- Thêm child vào collection và đồng bộ owning side.
- Remove child khi orphanRemoval bật.
- Remove parent với CascadeType.REMOVE.
- Thay đổi owning side/inverse side.
- Rollback giữa transaction.
- Soft delete nếu có mapping tương ứng.

Nâng cấp Hibernate có thể làm lộ mapping sai trước đó. Kiểm tra cả database rows lẫn object graph sau flush/reload.

### 8.4. Entity callbacks và listeners

Nếu ứng dụng dùng @PrePersist, @PreUpdate, @PreRemove, Hibernate event listeners hoặc Envers, test side effects:

- Callback chạy đúng operation.
- Không chạy khi bulk DML bypass lifecycle.
- Timestamp/actor fields được ghi đúng.
- Listener không gọi lazy association gây N+1.
- Exceptions trong callback làm transaction rollback theo kỳ vọng.
- Revision metadata tương ứng với audit events.

### 8.5. Generated columns và database defaults

Khi database tự sinh cột hoặc trigger cập nhật values, kiểm tra cách Hibernate lấy generated values sau INSERT/UPDATE. Mapping insertable=false, updatable=false, @Generated hoặc provider-specific generated properties có thể ảnh hưởng refresh behavior.

Test cần đọc lại từ database, không chỉ assert Java object trước flush.

## 9. Kiểm thử transaction, flush, commit và rollback

### 9.1. Flush không phải commit

```java
@Transactional
public void updateName(Long id, String name) {
    Product product = entityManager.find(Product.class, id);
    product.rename(name);
    entityManager.flush();
    // SQL đã được gửi, transaction vẫn có thể rollback.
}
```

Regression test cần phân biệt:

- State trong persistence context.
- State đã flush tới transaction.
- State đã commit và nhìn thấy từ transaction khác.
- State sau rollback.

### 9.2. Test rollback bằng transaction mới để đọc lại

Ví dụ dùng TransactionTemplate:

```java
transactionTemplate.executeWithoutResult(status -> {
    Product product = entityManager.find(Product.class, productId);
    product.rename("Temporary");
    entityManager.flush();
    status.setRollbackOnly();
});

String persistedName = transactionTemplate.execute(status ->
    entityManager.find(Product.class, productId).getName()
);

assertThat(persistedName).isEqualTo("Original");
```

Ví dụ giả định mỗi execute chạy transaction mới và không có outer test transaction bao trùm. Khi dùng EntityManager proxy của Spring, mỗi transaction sẽ nhận persistence context phù hợp.

### 9.3. Transaction propagation

Nếu service dùng REQUIRES_NEW, NESTED hoặc MANDATORY, regression test nên xác nhận đúng propagation:

- Inner transaction commit có tồn tại khi outer rollback không?
- Exception có đánh dấu rollback-only không?
- Có UnexpectedRollbackException không?
- Audit/outbox records có cùng transaction với business data không?

Không suy luận transaction behavior chỉ từ annotation; gọi bean qua Spring proxy và kiểm tra database sau khi transaction hoàn tất.

### 9.4. Isolation level

Isolation có thể ảnh hưởng đọc lặp lại, phantom rows, lost updates và locking. Database khác nhau có semantics mặc định khác nhau. Nếu business phụ thuộc isolation, khai báo và test trên database thật thay vì dựa vào H2.

## 10. Kiểm thử đồng thời: optimistic locking

Giả sử hai người cùng chỉnh sửa Product. Cả hai đọc version 5. Người thứ nhất cập nhật giá và commit version 6. Người thứ hai vẫn ghi dựa trên version 5.

Hibernate dùng @Version để ngăn ghi đè âm thầm.

### 10.1. Entity và SQL

```java
@Entity
public class Product {
    @Id
    private Long id;

    @Version
    private long version;

    private BigDecimal price;

    public void changePrice(BigDecimal value) {
        this.price = value;
    }
}
```

Khi Hibernate update, SQL thường có predicate tương đương:

```sql
UPDATE product
SET price = ?, version = ?
WHERE id = ? AND version = ?;
```

Nếu version trong database không còn khớp, affected row count bằng 0 và Hibernate báo optimistic-lock failure theo provider/Spring exception translation.

### 10.2. Test cần hai transaction độc lập

Không thể kiểm tra concurrency chỉ bằng hai lần gọi service tuần tự. Cần hai persistence contexts và hai database transactions chạy trên các threads khác nhau.

Mẫu test khái niệm với latches:

```java
CountDownLatch bothLoaded = new CountDownLatch(2);
CountDownLatch allowCommit = new CountDownLatch(1);

Callable<Void> worker = () -> {
    transactionTemplate.executeWithoutResult(status -> {
        Product product = entityManager.find(Product.class, productId);

        bothLoaded.countDown();
        await(allowCommit);

        product.changePrice(new BigDecimal("150.00"));
    });
    return null;
};

Future<Void> first = executor.submit(worker);
Future<Void> second = executor.submit(worker);

bothLoaded.await();
allowCommit.countDown();

List<Future<Void>> results = List.of(first, second);
```

Đoạn trên minh họa đồng bộ hóa, cần hoàn thiện helper await, executor lifecycle và thu exception từ Futures trong test thực tế. Hai workers phải chạy với EntityManager transaction-scoped proxy của Spring hoặc EntityManager riêng; không chia sẻ một EntityManager instance giữa threads.

### 10.3. Assertion mong đợi

Với hai transaction cùng đọc một version và cùng ghi:

- Một transaction commit thành công.
- Transaction còn lại bị optimistic-lock conflict.
- Giá cuối cùng là giá của transaction thắng.
- Version tăng đúng theo số update đã commit.
- Không có trạng thái ghi đè im lặng.
- Exception có thể xuất hiện ở flush hoặc commit, nên thu từ Future.get().

Không assert transaction nào luôn thắng; lịch scheduling không deterministic.

### 10.4. Test retry

Nếu ứng dụng có retry cho optimistic lock:

1. Xác nhận retry chỉ chạy cho exception phù hợp.
2. Transaction retry phải đọc state/version mới.
3. Không retry vô hạn.
4. Không lặp lại side effects ngoài database như gửi email/thanh toán.
5. Dùng idempotency key/outbox khi cần bảo vệ external effects.

Không retry một transaction đã bị đánh dấu rollback-only bên trong cùng transaction.

## 11. Kiểm thử pessimistic locking

Với thao tác cần serialize writers, có thể dùng:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select p from Product p where p.id = :id")
Optional<Product> findForUpdate(@Param("id") Long id);
```

Database có thể tạo lock tương đương SELECT ... FOR UPDATE, tùy dialect.

Test cần xác nhận:

- Transaction A lấy lock.
- Transaction B cố lấy cùng lock.
- B bị block hoặc timeout theo lock timeout policy.
- A commit/rollback thì B tiếp tục hoặc thất bại phù hợp.
- Lock được release khi transaction kết thúc.
- Deadlock được xử lý theo policy, không làm request treo vô hạn.

### 11.1. Đừng viết test dựa trên sleep cố định

Thread.sleep(100) không chứng minh transaction B đã chờ lock. Dùng latches/barriers và database-observable state để đồng bộ; giới hạn timeout để test không treo CI.

### 11.2. Lock timeout và dialect

JPA lock timeout hints, Hibernate settings và database lock timeout có thể không được hỗ trợ giống nhau. Testcontainers nên chạy trên database cùng engine/version gần production. Xác nhận timeout behavior thay vì chỉ kiểm tra annotation tồn tại.

### 11.3. Pessimistic lock không thay invariant

Nếu business yêu cầu quantity không âm, vẫn cần conditional update/constraint hoặc validation phù hợp. Locking giảm race nhưng không thay mọi lớp bảo vệ dữ liệu.

## 12. Kiểm thử isolation anomalies

Tùy business, regression tests có thể mô phỏng:

- **Lost update:** hai writers ghi đè nhau.
- **Non-repeatable read:** cùng transaction đọc một row hai lần nhưng thấy giá trị khác.
- **Phantom read:** cùng predicate query thấy thêm/bớt rows.
- **Write skew:** hai transactions cùng kiểm tra invariant trên nhiều rows rồi cập nhật các rows khác nhau khiến invariant bị phá.
- **Dirty read:** đọc dữ liệu chưa commit nếu isolation cho phép.

### 12.1. Ví dụ invariant tồn kho

Giả sử không cho phép tổng reservations vượt inventory. Hai transactions cùng đọc available quantity = 1 và mỗi transaction đặt thêm 1 reservation. Nếu không có lock/atomic conditional update/constraint, cả hai có thể cùng thành công.

Giải pháp có thể là:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = ?
  AND available >= 1;
```

Kiểm tra affected row count bằng 1 mới coi là thành công. Đây là atomic conditional update, tránh read-then-write race cho một row.

### 12.2. Test race bằng barrier

Cả hai transactions đọc/đến barrier rồi cùng thực hiện thao tác. Assert rằng chỉ một thao tác thành công nếu inventory ban đầu là 1. Sau cùng:

- Available không âm.
- Chỉ một reservation được tạo.
- Không có transaction thành công nhưng thiếu reservation hoặc ngược lại.
- Rollback không để lại partial state.

### 12.3. Isolation behavior là database-specific

Không copy kết quả isolation test từ H2 sang PostgreSQL/MySQL/SQL Server. Mức READ_COMMITTED, REPEATABLE_READ hoặc SERIALIZABLE có semantics và locking implementation khác nhau. Test trên engine thực tế và ghi rõ isolation configuration.

## 13. Kiểm thử SQL count và phát hiện N+1 trong regression suite

Một lần nâng Hibernate có thể thay đổi fetch behavior hoặc SQL generation. Đặt query budget cho các use cases quan trọng.

### 13.1. Hibernate Statistics

Cấu hình test:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.open-in-view=false
```

Đo:

```java
Statistics stats = entityManagerFactory
    .unwrap(SessionFactory.class)
    .getStatistics();

stats.setStatisticsEnabled(true);
stats.clear();

OrderDetailDto result = orderQueryService.getDetail(orderId);

long statements = stats.getPrepareStatementCount();
long entityLoads = stats.getEntityLoadCount();
long collectionFetches = stats.getCollectionFetchCount();
```

Các counters tích lũy ở cấp SessionFactory. Đọc ngay sau operation, cô lập test khỏi requests khác và không chạy song song khi dùng stats.clear() toàn cục.

### 13.2. Seed trước, reset sau

Thứ tự:

1. Seed fixture trong transaction riêng và commit.
2. Tạo persistence context mới.
3. Evict L2/query cache nếu đang đo cold cache.
4. Reset Statistics.
5. Gọi use case qua Spring proxy.
6. Chụp counters sau khi transaction của service hoàn tất.
7. Assert query budget và output.

Nếu reset trước khi seed, INSERT/SELECT của fixture bị tính vào use case. Nếu outer test transaction giữ cùng EntityManager, L1 cache có thể che N+1.

### 13.3. Fixture phải có cardinality đủ lớn

Một fixture 1 order không phân biệt được 2 queries và N+1. Dùng 1, 10, 100 parent records với distinct association targets:

| Cardinality | Fetch plan cố định | N+1 to-one điển hình |
|---:|---:|---:|
| 1 | 1–2 statements | 2 |
| 10 | 1–2 statements | 11 |
| 100 | 1–2 statements | 101 |

Với batch fetching, số query có thể tăng theo số batches. Regression assertion nên kiểm tra growth theo thiết kế, không bắt buộc mọi số phải bằng nhau.

### 13.4. Đo riêng SELECT và DML

Trong create/update/delete, INSERTs theo số child entities có thể là hành vi bình thường. Đừng dùng một tổng query count duy nhất để kết luận N+1. Dùng JDBC proxy để phân loại SELECT, INSERT, UPDATE, DELETE và batch executions khi cần.

### 13.5. Query count ít không đảm bảo hiệu năng

Một JOIN có thể chỉ tạo một statement nhưng trả hàng chục nghìn rows lặp. Kết hợp query count với result rows, execution plan, DB time, memory và request latency.

## 14. Kiểm thử hiệu năng có thể so sánh trước và sau

### 14.1. Chọn chỉ số

Ít nhất nên theo dõi:

- Throughput (requests/second hoặc operations/second).
- Latency p50, p95, p99.
- Database execution time.
- Query/statement count.
- Rows returned/affected.
- Connection pool active/idle/wait.
- CPU, heap, allocation và GC.
- Lock waits, deadlocks và transaction retries.
- Cache hit/miss.
- Error/timeout rate.

Average latency đơn lẻ có thể che tail latency. Một vài requests rất chậm có thể làm trải nghiệm người dùng xấu dù mean vẫn thấp.

### 14.2. Cùng workload và cùng điều kiện

Để so sánh trước/sau:

- Dùng cùng hardware/container limits.
- Cùng database dataset và indexes.
- Cùng JVM heap và GC.
- Cùng connection pool size.
- Cùng concurrency, request mix và think time.
- Cùng warm-up và measurement duration.
- Cùng cache state.
- Cùng database statistics/maintenance state nếu có thể.

Nếu database container bị CPU throttling ở một run nhưng không ở run khác, benchmark không thể kết luận Hibernate version mới nhanh/chậm hơn.

### 14.3. Warm-up trước khi đo

JVM JIT, class loading, connection pool initialization và cache warm-up làm các request đầu tiên chậm hơn. Chạy warm-up đủ dài trước measurement, nhưng ghi rõ warm-up có bao gồm cache warming hay không.

Nên đo riêng:

- Cold start/cold cache.
- Warm steady-state.
- Cache miss workloads.
- Peak concurrency.

### 14.4. Lặp nhiều lần và báo phân bố

Chạy nhiều iterations, lưu raw results và báo p50/p95/p99 cùng độ biến thiên. Không kết luận từ một lần chạy. Dùng cùng duration/iteration count cho baseline và candidate.

### 14.5. Đặt ngưỡng regression

Ví dụ policy minh họa:

- p95 latency không tăng quá 10% trên workload ổn định.
- Query count của endpoint không tăng tuyến tính theo records.
- Error rate không tăng.
- Throughput không giảm quá ngưỡng đã thỏa thuận.
- Không phát sinh deadlocks hoặc timeouts ngoài budget.

Các ngưỡng phải dựa vào SLO và độ nhiễu của môi trường. Một test CI shared runner thường không phù hợp để fail vì chênh lệch latency 2–3 ms; có thể chạy query-count gates trong CI và benchmark chặt hơn trên dedicated performance environment.

### 14.6. Không trộn benchmark ORM với benchmark database

Nếu query chậm hơn, cần phân biệt:

- Hibernate tạo SQL khác.
- JDBC driver thay cách bind/execute.
- Database plan thay đổi.
- Index/statistics khác.
- Network hoặc pool wait.
- Hydration/result mapping tốn CPU.
- Logging/metrics overhead.

Dùng tracing/metrics để xác định phần chi phí, không quy mọi thay đổi cho Hibernate.

## 15. Kiểm thử batching sau nâng cấp

Hibernate có batching cho INSERT/UPDATE/DELETE:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Test:

- Tạo nhiều entities trong một transaction.
- Flush theo batch boundaries.
- Đếm batch executions và parameter sets.
- Kiểm tra generated IDs có tương thích generator không.
- Kiểm tra version columns và affected row counts.
- Đo memory và transaction duration.

### 15.1. IDENTITY có thể hạn chế insert batching

Generator IDENTITY thường yêu cầu INSERT để lấy generated key ngay, có thể hạn chế batching so với SEQUENCE tùy Hibernate/dialect. Nâng cấp có thể thay đổi chi tiết batching; đo trên database thật.

### 15.2. Flush/clear theo batch

Batch import lớn có thể dùng:

```java
for (int i = 0; i < records.size(); i++) {
    entityManager.persist(map(records.get(i)));

    if ((i + 1) % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
```

flush gửi pending SQL; clear detach entities để giảm persistence-context memory. Nếu còn references tới entities đã detach, không tiếp tục mutate chúng như managed state. Test cần xác nhận associations/IDs vẫn đúng sau mỗi batch.

### 15.3. Batch regression không chỉ là số INSERT log lines

SQL logger có thể in một dòng cho mỗi prepared statement trong khi driver gom executions bằng batch. Dùng JDBC instrumentation để phân biệt batch entries và executeBatch calls. Không bật bind TRACE hàng loạt chỉ để đếm.

## 16. Kiểm thử connection pool và transaction timeout

Nâng Hibernate/driver có thể thay đổi thời gian giữ connection, fetch behavior hoặc transaction duration.

Theo dõi:

- Active connections.
- Idle connections.
- Pending/waiting threads.
- Connection acquisition timeout.
- Connection leak detection.
- Transaction duration.
- Query timeout.
- Statement cancellation.

Một endpoint N+1 có thể giữ connection lâu hơn vì nhiều SELECT; pool cạn dù từng SELECT không quá chậm.

### 16.1. Stress test pool nhỏ

Chạy workload concurrency cao hơn pool size để kiểm tra:

- Requests chờ connection đúng giới hạn.
- Timeout trả lỗi có kiểm soát.
- Connection được trả lại sau exception/rollback.
- Không có leak khi lazy loading hoặc streaming result.
- Batch transaction không giữ connection quá lâu.

### 16.2. Streaming và cursor

Nếu dùng Stream từ Spring Data hoặc JDBC cursor, kiểm tra stream được đóng và tiêu thụ trong transaction phù hợp. Không giữ stream qua controller response hoặc sau khi transaction kết thúc nếu provider yêu cầu open cursor/connection.

## 17. Testcontainers cho database và driver thật

H2 hữu ích cho test nhanh nhưng không đại diện hoàn toàn cho PostgreSQL, MySQL, SQL Server hay Oracle.

Testcontainers có thể khởi động database thật trong container để test:

- SQL dialect.
- Timestamp/UUID/JSON mapping.
- Unique constraints và partial indexes.
- Locking/isolation.
- Pagination.
- Sequences/generated keys.
- JDBC batching.
- Native queries.
- Migration scripts.

### 17.1. Ví dụ PostgreSQL container

```java
@Testcontainers
@SpringBootTest
class ProductRepositoryPostgresIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Đây là ví dụ cấu hình phổ biến; cần dependency Testcontainers PostgreSQL/JUnit và Spring Boot tương ứng. Pin image version/digest để test reproducible, không dùng latest.

### 17.2. Driver version phải là driver cần kiểm thử

Container database không tự quyết định JDBC driver dependency. Chạy matrix với driver version trước/sau nâng cấp trên cùng database image để cô lập tác động driver.

### 17.3. Database version matrix

Nếu ứng dụng hỗ trợ nhiều database versions, chạy integration suite trên các phiên bản nằm trong support policy. Không nhất thiết chạy full performance suite trên mọi matrix; có thể chia smoke/data compatibility và performance-critical scenarios.

## 18. Kiểm thử compatibility matrix của Hibernate

Khi thay đổi Hibernate major/minor, ghi rõ tổ hợp được hỗ trợ:

| Thành phần | Matrix cần cân nhắc |
|---|---|
| Java | JDK tối thiểu và JDK production |
| Spring Boot | Boot versions được hỗ trợ |
| Hibernate ORM | Core versions trước/sau |
| Envers | Cùng dòng tương thích với ORM Core |
| Jakarta Persistence | API version do stack hỗ trợ |
| JDBC driver | Driver versions được hỗ trợ |
| Database | Engine và major versions |
| Cache provider | Provider/version và integration |
| Bytecode enhancement | Plugin/runtime configuration |
| Migration tool | Flyway/Liquibase version |

Không nâng riêng Envers xa khỏi Hibernate Core nếu không xác nhận compatibility. Spring Boot BOM thường quản lý một tập dependency tương thích; nếu override version, cần kiểm tra toàn bộ dependency tree.

### 18.1. Major upgrade cần đọc migration guide

Các thay đổi có thể ảnh hưởng:

- javax.persistence sang jakarta.persistence.
- Removed/deprecated APIs.
- HQL parser/semantic validation.
- SQL generation và dialect changes.
- Type system/JDBC type mappings.
- Identifier generator behavior.
- Fetch plan and pagination behavior.
- Event/listener APIs.
- Configuration property names/defaults.

Regression suite cần tập trung vào các vùng ứng dụng đang dùng, không chỉ chạy một test CRUD cơ bản.

### 18.2. Test compile-time và runtime riêng

Compile success không chứng minh SQL/mapping đúng. Runtime startup success không chứng minh data compatibility. Cần cả:

- Compile/architecture tests.
- Application context startup.
- Schema validation/migrations.
- Integration tests.
- Concurrency/performance tests.

## 19. Kiểm thử Envers, soft delete và các tính năng liên quan

Nếu ứng dụng dùng Envers:

- ADD/MOD/DEL revision type đúng.
- Revision metadata và timestamp đúng.
- Association history đúng.
- Rollback không để lại committed audit rows.
- Bulk/native mutations được xử lý theo policy.
- Schema migration audit tables đúng.

Nếu dùng soft delete:

- remove đổi indicator đúng.
- Default queries ẩn tombstones.
- Restore path có authorization.
- Unique constraints cho active records đúng.
- Bulk DML không bypass policy.
- Cache và association loads nhất quán.

Nâng Hibernate có thể thay SQL hoặc event behavior. Test dựa vào business contract và dữ liệu cuối cùng, không chỉ tên logger hoặc một alias SQL.

## 20. Test query plan và index regression

SQL text giống nhau không bảo đảm execution plan giống nhau. Database statistics, version, parameter types và index changes có thể làm optimizer chọn plan khác.

### 20.1. Kiểm tra EXPLAIN

Trên PostgreSQL, ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number
FROM purchase_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

EXPLAIN ANALYZE thực thi query; chỉ dùng trên dữ liệu/môi trường phù hợp, tránh query write hoặc workload nặng ngoài dự kiến.

### 20.2. Không snapshot plan text tuyệt đối

Plan có thể đổi cost estimates, node order, row estimates hoặc timing theo dữ liệu và database version. Kiểm tra các đặc tính quan trọng:

- Có dùng index kỳ vọng khi predicate/selectivity phù hợp không?
- Có full table scan trên bảng lớn ngoài dự kiến không?
- Estimated rows lệch actual rows quá lớn không?
- Có sort/hash spill không?
- Buffer reads tăng mạnh không?
- Join order có gây explosion không?

Không bắt buộc một plan phải giống từng dòng giữa database minor versions.

### 20.3. Dùng realistic cardinality và statistics

Fixture quá nhỏ khiến optimizer chọn sequential scan dù production dùng index. Performance test cần dữ liệu đủ lớn/đa dạng và database statistics được cập nhật phù hợp.

## 21. Kiểm thử regression của SQL và logging an toàn

Trong môi trường test:

```properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=OFF
logging.level.org.hibernate.orm.jdbc.extract=OFF
spring.jpa.properties.hibernate.generate_statistics=true
```

SQL DEBUG giúp xem query shape; Statistics giúp đếm. Không cần bind/extract TRACE để kiểm tra N+1.

Nếu cần điều tra bind type, chạy local test với dữ liệu synthetic và bật category tương ứng trong phạm vi ngắn. Không để parameter values, PII, tokens hoặc credentials lọt vào CI artifacts.

### 21.1. Không log toàn bộ SQL làm metric label

Dùng query key ổn định như OrderRepository.findPage, không dùng raw SQL hoặc parameter values làm metric labels vì cardinality cao và nguy cơ rò rỉ dữ liệu.

### 21.2. SQL comments

Nếu bật Hibernate SQL comments, chỉ dùng operation names tĩnh. Không đưa request body, email, tenant secret hoặc identifiers nhạy cảm vào comment.

## 22. Regression test cho các repository methods đặc biệt

### 22.1. Bulk JPQL update/delete

Bulk DML bypass per-entity dirty checking/lifecycle callbacks theo semantics JPA. Kiểm tra:

- Rows affected.
- Persistence context có stale không.
- Có cần clear/refresh không.
- @Version có được kiểm tra theo yêu cầu không.
- Envers/listeners/cascade có bị bypass không.

Sau bulk DML, test với EntityManager mới để đọc state từ database.

### 22.2. Native queries

Kiểm tra result mapping, scalar types, pagination, parameter binding và dialect-specific syntax. Native SQL không tự nhận mọi ORM filters hoặc soft-delete restrictions như HQL entity queries.

### 22.3. Stored procedures

Kiểm tra input/output parameters, cursor/result sets, transaction semantics, update counts và driver compatibility. Database procedure có thể thực hiện nhiều statements nội bộ mà JDBC instrumentation chỉ thấy một CALL.

### 22.4. Streaming queries

Kiểm tra stream lifecycle, transaction scope, connection release và memory. Một stream không được đóng có thể làm pool cạn; stream materialization có thể tải toàn bộ dữ liệu và gây memory spike.

### 22.5. Locking repository methods

Test query có @Lock, lock timeout, transaction requirement và behavior trên database production. Không chỉ assert method annotation.

## 23. Tổ chức test suite để CI ổn định

Một pipeline có thể chia:

**Pull request:**

- Unit tests.
- Repository integration tests nhanh.
- Migration smoke test.
- Query-count regression tests.
- Một số concurrency tests deterministic.

**Main/nightly:**

- Full Testcontainers matrix.
- Concurrency stress scenarios.
- Performance comparison trên môi trường được kiểm soát.
- Large data migration test.
- Cache warm/cold scenarios.

**Pre-release:**

- Staging smoke.
- Rolling deployment compatibility.
- Read/write compatibility giữa old/new app versions.
- Backup/restore rehearsal.
- Performance soak test.

### 23.1. Không chạy global counters song song

Hibernate Statistics thường là global theo SessionFactory. Nếu nhiều test cùng clear và đọc counters, kết quả bị nhiễu. Chạy suite đo query count tuần tự hoặc dùng JDBC listener có scope theo test/request.

### 23.2. Tránh performance thresholds quá nhạy trong shared CI

Shared runners có CPU/network noise. Có thể dùng query-count gates chặt trong PR, còn latency gates chạy trên dedicated runner với baseline nhiều lần và tolerance có cơ sở.

### 23.3. Lưu artifacts có ích

Lưu:

- Test report và failure details.
- Database engine/driver/Hibernate versions.
- Query key và counts.
- Benchmark raw samples/percentiles.
- Migration version/checksum.
- Container image version.
- Execution plan đã loại dữ liệu nhạy cảm.

Không lưu bind values hoặc production PII trong artifacts.

## 24. Kiểm thử rolling upgrade và backward compatibility

Trong deployment rolling, old nodes và new nodes có thể chạy cùng lúc. Schema phải hỗ trợ cả hai trong giai đoạn chuyển tiếp.

### 24.1. Read compatibility

- Old app có đọc được rows do new app ghi không?
- New app có đọc được rows cũ chưa backfill không?
- Enum mới có làm old app parse fail không?
- Cột nullable/default có giữ semantics cũ không?
- JSON payload versioning có backward compatible không?

### 24.2. Write compatibility

- Old app có bỏ qua cột mới và tạo NULL sai không?
- New app có ghi representation old app không hiểu không?
- Sequence/default behavior có tương thích không?
- Trigger mới có thay đổi behavior của old writers không?
- Soft delete có bị old nodes physical DELETE không?

### 24.3. Expand-contract test

Test ít nhất ba trạng thái:

1. Schema mở rộng, old app vẫn hoạt động.
2. New app hoạt động trên schema mở rộng trong khi old app vẫn tồn tại.
3. Sau khi old app rút hết, contract migration loại bỏ cấu trúc cũ.

Nếu không thể hỗ trợ mixed-version writers, deployment cần cutover/downtime hoặc biện pháp bảo vệ database rõ ràng.

## 25. Troubleshooting khi regression test fail

### 25.1. Dữ liệu khác trước/sau

Kiểm tra:

- Column precision/scale.
- Timestamp timezone/precision.
- Enum representation.
- AttributeConverter.
- Null/default values.
- Collation/case sensitivity.
- Generated columns/triggers.
- Schema migration/backfill.
- L1/L2 cache đang trả stale state không.

### 25.2. SQL count tăng

Kiểm tra:

- Association LAZY mới bị mapper truy cập.
- Fetch graph/query method thay đổi.
- EAGER association phát secondary SELECT.
- Count query của Page.
- Auto-flush trước query.
- Sequence/identifier generation.
- Filters/interceptors/listeners.
- L2/query cache khác baseline.
- JSON serialization và OSIV.

### 25.3. SQL lỗi sau nâng cấp

Kiểm tra:

- Hibernate dialect và database version.
- Reserved keywords/quoting.
- Native SQL.
- Type mapping/JDBC bind types.
- HQL parser/semantic changes.
- Column names/physical naming strategy.
- Schema migration và database permissions.
- Driver compatibility.

### 25.4. Concurrency test thất bại không ổn định

Kiểm tra:

- Hai transaction có thật sự độc lập không?
- Có dùng chung EntityManager không?
- Latch/barrier có đồng bộ đúng thời điểm đọc không?
- Test có outer transaction không?
- Exception xuất hiện ở flush hay commit?
- Database isolation/lock timeout có giống môi trường thật không?
- Thread pool có được shutdown và futures có được collect không?

Không thay concurrency test bằng Thread.sleep rồi giả định race đã xảy ra.

### 25.5. Performance giảm nhưng query count không đổi

Có thể do:

- SQL plan thay đổi.
- JOIN trả nhiều rows hơn.
- JDBC driver behavior/batching thay đổi.
- Hydration/type conversion tốn CPU hơn.
- Connection pool wait.
- Lock contention.
- GC/memory pressure.
- Logging/metrics overhead.
- Database statistics/indexes khác.

Query count ổn định không chứng minh performance ổn định.

## 26. Ví dụ test tổng hợp cho một read use case

Giả sử Order detail trả Customer và 50 OrderLines cùng Product. Service được gọi qua Spring proxy, OSIV tắt, fixture đã commit.

```java
@SpringBootTest(properties = {
    "spring.jpa.open-in-view=false",
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
class OrderDetailRegressionIT {

    @Autowired
    private OrderQueryService service;

    @Autowired
    private EntityManagerFactory emf;

    @Test
    void loadsDetailWithinQueryBudget() {
        Long orderId = seedCommittedOrderWithDistinctProducts(50);

        SessionFactory sessionFactory =
            emf.unwrap(SessionFactory.class);

        Statistics stats = sessionFactory.getStatistics();
        stats.setStatisticsEnabled(true);
        stats.clear();

        OrderDetailDto result = service.getDetail(orderId);

        long statementCount = stats.getPrepareStatementCount();
        long collectionFetches = stats.getCollectionFetchCount();

        assertThat(result.lines()).hasSize(50);
        assertThat(result.customerName()).isNotBlank();
        assertThat(statementCount).isLessThanOrEqualTo(3);
        assertThat(collectionFetches).isLessThanOrEqualTo(1);
    }
}
```

Budget là ví dụ cho fetch plan gồm header/customer và lines/product. Fixture helper phải commit trước khi reset; test không chạy song song với test khác dùng cùng Statistics. Nếu service method có count query/filter hợp lệ, điều chỉnh budget có giải thích.

## 27. Ví dụ test optimistic-lock regression

Mẫu test khái niệm:

```java
@Test
void concurrentUpdatesAllowOnlyOneWriter() throws Exception {
    Long id = seedCommittedProduct();

    CountDownLatch loaded = new CountDownLatch(2);
    CountDownLatch proceed = new CountDownLatch(1);

    Callable<Void> update = () -> {
        transactionTemplate.executeWithoutResult(status -> {
            Product product = entityManager.find(Product.class, id);
            loaded.countDown();
            await(proceed);
            product.changePrice(new BigDecimal("150.00"));
        });
        return null;
    };

    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
        Future<Void> first = pool.submit(update);
        Future<Void> second = pool.submit(update);

        assertThat(loaded.await(10, TimeUnit.SECONDS)).isTrue();
        proceed.countDown();

        int successes = 0;
        int optimisticFailures = 0;

        for (Future<Void> future : List.of(first, second)) {
            try {
                future.get(10, TimeUnit.SECONDS);
                successes++;
            } catch (ExecutionException ex) {
                if (hasOptimisticLockCause(ex)) {
                    optimisticFailures++;
                } else {
                    throw ex;
                }
            }
        }

        assertThat(successes).isEqualTo(1);
        assertThat(optimisticFailures).isEqualTo(1);
    } finally {
        proceed.countDown();
        pool.shutdownNow();
    }
}
```

Đây là cấu trúc minh họa, cần triển khai helpers await và hasOptimisticLockCause, inject TransactionTemplate và transaction-scoped EntityManager proxy. Mỗi thread có transaction và persistence context riêng. Không dùng @Transactional trên test method, vì outer transaction có thể làm sai isolation của hai workers.

Trong một số cấu hình, exception có thể được wrap qua Spring exception translation hoặc nằm trong cause chain. Test cần nhận diện cả provider exception và Spring wrapper phù hợp.

## 28. Checklist regression trước khi phát hành nâng cấp

### Dữ liệu

- Round-trip values quan trọng đúng.
- BigDecimal precision/scale đúng.
- Timestamp/timezone/precision đúng.
- Enum/converter/UUID/JSON mapping đúng.
- Unicode/collation đúng.
- Null/default/generated values đúng.
- Old data đọc được sau migration.
- Foreign keys, unique constraints và indexes đúng.

### SQL và ORM

- Repository queries trả đúng rows và ordering.
- Pagination/count query đúng.
- Native SQL/stored procedures hoạt động.
- Query budgets không tăng ngoài dự kiến.
- N+1 không xuất hiện ở associations/serialization.
- Batch fetching/DML batching được đo.
- Bulk DML và lifecycle/audit semantics đúng.
- Không có SQL literals hoặc bind values nhạy cảm trong logs.

### Transaction và đồng thời

- Flush/commit/rollback đúng.
- Optimistic-lock conflict được phát hiện.
- Pessimistic lock/timeout đúng.
- Invariants không bị phá bởi races.
- Isolation level đúng theo database.
- Retry không lặp external side effects.
- Connections/transactions được release khi lỗi.

### Hiệu năng và vận hành

- p95/p99 và throughput trong SLO.
- Query count, rows, DB time và execution plans hợp lý.
- Connection pool không cạn.
- Memory/GC không tăng bất thường.
- Test matrix đúng Java/Hibernate/driver/database versions.
- Rolling deployment tương thích.
- Backup/restore và rollback plan được diễn tập.

## 29. Bài tập thực hành

**Bài 1 — Baseline.** Chọn một endpoint Order list, ghi Hibernate/driver/database versions, fixture cardinality, query count và p50/p95/p99 trước nâng cấp.

**Bài 2 — Data round-trip.** Viết tests cho BigDecimal, Instant, enum, UUID, Unicode và JSON trên database thật.

**Bài 3 — Migration.** Tạo database theo schema version trước, seed dữ liệu cũ, chạy Flyway/Liquibase và xác nhận mapping mới đọc được.

**Bài 4 — SQL semantics.** Kiểm tra predicates, tenant conditions, ordering và pagination mà không snapshot alias/whitespace toàn câu SQL.

**Bài 5 — Query budget.** Đo SELECT statements cho 1/10/100 Orders với distinct Customers; phát hiện N+1.

**Bài 6 — Fetch regression.** So JOIN FETCH, EntityGraph, DTO projection và batch fetching; ghi cả statement count lẫn rows returned.

**Bài 7 — Transaction rollback.** Flush một update rồi rollback; đọc lại bằng transaction mới và xác nhận database giữ state cũ.

**Bài 8 — Optimistic locking.** Hai transactions đọc cùng version, cùng cập nhật; xác nhận chỉ một commit thành công.

**Bài 9 — Pessimistic locking.** Dùng PESSIMISTIC_WRITE và kiểm tra wait/timeout trên Testcontainers database.

**Bài 10 — Inventory race.** Hai requests cùng đặt sản phẩm khi available = 1; xác nhận chỉ một reservation thành công.

**Bài 11 — Isolation.** Mô phỏng non-repeatable read hoặc write skew theo database isolation level đang hỗ trợ.

**Bài 12 — JDBC batching.** Insert 1.000 records với batch size khác nhau; đo batch executions, throughput và memory.

**Bài 13 — Query plan.** So EXPLAIN ANALYZE trước/sau nâng cấp với cùng dataset và indexes.

**Bài 14 — Driver matrix.** Chạy cùng integration tests với JDBC driver version cũ và mới trên cùng database image.

**Bài 15 — Rolling compatibility.** Chạy old/new application versions trên schema expand và xác nhận read/write compatibility.

**Bài 16 — CI gate.** Tách query-count regression tests khỏi dedicated performance benchmarks; định nghĩa threshold và failure report.

## 30. Câu hỏi tự kiểm tra

**1. Vì sao một lần nâng Hibernate cần kiểm tra dữ liệu sau round-trip?**

Vì type mapping, converters, precision, enum representation, generated values và dialect behavior có thể thay đổi dù code vẫn compile.

**2. Vì sao không nên snapshot toàn bộ SQL text?**

Alias, whitespace, column order và formatting có thể đổi mà semantics không đổi. Nên assert query behavior và SQL shape có ý nghĩa.

**3. getPrepareStatementCount() có phải số network round trips không?**

Không nhất thiết. Đó là Hibernate Statistics counter; JDBC batch, driver protocol và database calls có semantics riêng.

**4. Vì sao phải seed và commit fixture trước khi reset counters?**

Để hoạt động tạo dữ liệu không bị tính vào use case và measured operation chạy trong persistence context mới.

**5. Vì sao concurrency test cần hai EntityManagers/transactions độc lập?**

Một persistence context không mô phỏng hai writers đồng thời; EntityManager không thread-safe và không nên chia sẻ giữa threads.

**6. Optimistic locking bảo vệ điều gì?**

Nó phát hiện update dựa trên version cũ, giúp tránh lost update theo mapping/version strategy.

**7. Pessimistic locking cần test trên database thật vì sao?**

Lock syntax, timeout, isolation và lock behavior phụ thuộc dialect/engine.

**8. Vì sao H2 không thay được Testcontainers database production?**

H2 có dialect, type, collation, locking, pagination và driver behavior khác database thực.

**9. Query count không tăng nhưng endpoint chậm hơn có thể do đâu?**

Execution plan, rows returned, hydration, driver, pool wait, locks, CPU, memory hoặc GC.

**10. Vì sao migration test phải bắt đầu từ schema cũ?**

Vì schema mới tạo từ đầu không kiểm tra được backfill, defaults, nullability và compatibility với dữ liệu tồn tại.

**11. Vì sao Page query có thể có hai SELECT mà không phải N+1?**

Một query lấy content và một query count có thể là behavior bình thường của Spring Data Page.

**12. Vì sao không nên bật bind TRACE trên production để benchmark?**

Nó có thể ghi PII/secrets, tạo log volume lớn và làm thay đổi chi phí thực thi được đo.

**13. Bulk JPQL update khác managed entity update thế nào?**

Bulk DML bypass per-entity dirty checking/lifecycle callbacks và có thể làm persistence context stale.

**14. Khi nào cần expand-and-contract migration?**

Khi old và new application versions phải cùng chạy trong rolling deployment hoặc schema change chưa thể áp dụng đồng thời.

**15. Một regression gate tốt nên bảo vệ điều gì?**

Business correctness, data compatibility, SQL/query budget, concurrency invariants và performance SLO với threshold có lý do.

## 31. Ghi nhớ

- Kiểm thử hồi quy khi nâng Hibernate phải bao phủ **dữ liệu, SQL, đồng thời và hiệu năng**, không chỉ compile/startup.
- Lập baseline version, schema, workload, query counts, latency, cache và pool trước khi nâng cấp.
- Kiểm tra dữ liệu bằng round-trip tests cho numeric precision, timestamp/timezone, enum, UUID, JSON, Unicode, converters và generated values.
- Migration tests phải bắt đầu từ schema cũ có dữ liệu đại diện, không chỉ tạo schema mới nhất.
- Assert SQL semantics, ordering, pagination, predicates và query budgets; tránh đóng đinh alias/whitespace của một Hibernate version.
- Phân biệt Hibernate query executions, prepared statements, JDBC executions, batch entries và database round trips.
- Flush không phải commit; dùng transaction mới để xác nhận state sau commit/rollback.
- Concurrency tests cần transaction/persistence context độc lập và synchronization bằng latches/barriers; không dựa vào sleep.
- Kiểm tra optimistic/pessimistic locking, isolation anomalies, retries và business invariants trên database thực.
- Query count ổn định không chứng minh performance ổn định; đo rows, plans, p95/p99, throughput, memory, GC và connection pool.
- Testcontainers giúp kiểm chứng dialect/driver/database thực; pin version để kết quả reproducible.
- CI nên có data/query/concurrency regression gates ổn định và performance benchmarks trên môi trường được kiểm soát.
- Rolling upgrades cần read/write compatibility và expand-contract migration khi old/new versions cùng tồn tại.
- Chỉ hoàn tất nâng cấp khi regression evidence chứng minh dữ liệu đúng, SQL hợp lý, concurrency an toàn và hiệu năng nằm trong SLO.

### Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html)
- [Hibernate ORM 6.6 Migration Guide](https://docs.hibernate.org/orm/6.6/migration-guide/)
- [Hibernate ORM 6.6 JavaDoc — Statistics](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/stat/Statistics.html)
- [Hibernate ORM 6.6 JavaDoc — LockOptions](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/LockOptions.html)
- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1)
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/)
- [Flyway Documentation](https://documentation.red-gate.com/flyway)
- [Liquibase Documentation](https://docs.liquibase.com/)
- [Testcontainers for Java](https://java.testcontainers.org/)
- [PostgreSQL Documentation — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PostgreSQL Documentation — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)

