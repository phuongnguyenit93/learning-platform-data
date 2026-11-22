# Lập kiểm thử hồi quy khi nâng phiên bản Spring Data hoặc driver

Nâng phiên bản Spring Data JDBC hoặc JDBC driver có thể làm thay đổi hành vi persistence dù code nghiệp vụ không đổi. Framework có thể thay đổi cách ánh xạ aggregate, phát lifecycle callback, quản lý transaction hoặc diễn giải metadata; driver có thể thay đổi cách bind/đọc kiểu dữ liệu, lấy generated key, xử lý timestamp, exception hay batch statement. Một ứng dụng vẫn compile và khởi động thành công nhưng có thể ghi sai dữ liệu, đọc khác kiểu, rollback không như mong đợi hoặc chậm hơn sau khi nâng cấp.

Kiểm thử hồi quy cho upgrade cần trả lời một câu hỏi cụ thể: **những hợp đồng nào ứng dụng đang phụ thuộc phải tiếp tục đúng trên phiên bản framework, driver và database mới?** Bài học này trình bày cách lập phạm vi nâng cấp, thiết lập baseline, xây dựng integration test, kiểm tra tương thích database/driver, đánh giá transaction và migration, rồi triển khai nâng cấp theo từng bước có thể kiểm soát.

## 1. Phân biệt các thành phần có thể được nâng cấp

Một ứng dụng Spring Data JDBC thường có nhiều lớp phiên bản liên quan:

| Thành phần | Vai trò | Rủi ro khi thay đổi |
| --- | --- | --- |
| Spring Boot | Quản lý dependency và auto-configuration nếu dự án dùng Boot. | Thay đổi BOM, cấu hình mặc định, bean auto-configured và phiên bản framework được quản lý. |
| Spring Data JDBC | Mapping aggregate, repository, callbacks, auditing và SQL persistence. | Thay đổi API, mapping, lifecycle behavior, query generation hoặc optimistic locking. |
| Spring Data Relational / Commons | Hạ tầng mapping và abstraction dùng chung. | Thay đổi metadata, converter, repository infrastructure hoặc callback contracts. |
| Spring Framework | Transaction, bean lifecycle, proxy và JDBC support. | Thay đổi transaction interception, exception translation, resource management. |
| JDBC driver | Cầu nối giữa Java và database. | Thay đổi type mapping, parameter binding, generated keys, metadata, timeout và lỗi SQL. |
| Database server | Thực thi SQL và quản lý transaction/storage. | Thay đổi dialect, optimizer, constraint, isolation, precision hoặc behavior của SQL. |
| Connection pool | Quản lý physical connections. | Thay đổi validation, timeout, leak detection, session state và connection lifecycle. |
| Migration tool | Áp dụng schema/data migrations. | Thay đổi cách chạy migration, transaction support, checksum hoặc thứ tự migration. |

Không coi một lần nâng dependency là một thay đổi đơn lẻ nếu nhiều thành phần cùng thay phiên bản. Nếu ứng dụng đồng thời nâng Spring Boot, Spring Data JDBC, JDBC driver và database server, một test thất bại khó chỉ ra nguyên nhân thuộc lớp nào.

### Xác định chính xác phạm vi thay đổi

Trước khi sửa dependency, ghi lại:

- Phiên bản hiện tại và phiên bản mục tiêu của Spring Boot/Spring Data.
- Phiên bản Spring Framework được dependency management chọn.
- JDBC driver hiện tại và driver mục tiêu.
- Database engine và phiên bản server ở môi trường production.
- Connection pool, migration tool và Java runtime.
- Các converter, custom dialect, repository fragment và SQL tự viết.
- Cấu hình datasource, transaction manager, timezone, schema và pool.

Nếu dùng Spring Boot, ưu tiên nâng theo dependency management/BOM tương thích của Boot. Không tự ép riêng một module Spring Data lên phiên bản khác với bộ phiên bản mà Boot quản lý nếu chưa xác nhận compatibility matrix. Với ứng dụng không dùng Boot, quản lý phiên bản các module Spring Data/Framework theo bộ tương thích được công bố.

## 2. Xác định hợp đồng cần bảo vệ

Không cần viết test cho mọi implementation detail của framework. Hãy liệt kê hành vi mà ứng dụng phụ thuộc, rồi kiểm tra chúng qua API công khai và kết quả quan sát được.

Một inventory hữu ích:

| Khu vực | Hợp đồng cần giữ |
| --- | --- |
| Aggregate mapping | Root và child được insert, load, update và delete đúng cấu trúc. |
| ID generation | Generated ID được trả về đúng sau insert. |
| Type conversion | Enum, UUID, decimal, date/time, JSON hoặc custom type round-trip đúng. |
| Null/default | Null, default database và primitive/wrapper được xử lý đúng. |
| Optimistic locking | Version tăng đúng; stale update bị phát hiện. |
| Transactions | Nhiều lệnh cùng commit hoặc rollback theo use case. |
| Repository queries | Derived query, @Query, pagination, sorting và custom SQL trả kết quả đúng. |
| Lifecycle/auditing | Callback, event và audit fields xuất hiện theo hợp đồng ứng dụng. |
| Database constraints | Unique, foreign key, check và generated columns vẫn được tôn trọng. |
| Driver behavior | Parameter binding, ResultSet mapping, generated keys, metadata và exception translation đúng. |
| Migrations | Database cũ được nâng lên schema mới và ứng dụng vẫn đọc/ghi được. |
| Performance | Query quan trọng không phát sinh N+1 hoặc suy giảm vượt ngưỡng chấp nhận. |

Chọn test từ nghiệp vụ và dữ liệu thật mà ứng dụng lưu. Ví dụ, nếu aggregate có collection con, test cần chứng minh update root không làm mất child ngoài ý muốn. Nếu audit timestamp được lưu bằng `Instant`, test phải xác nhận round-trip theo precision của column.

## 3. Tách baseline và phiên bản mục tiêu

Baseline là kết quả quan sát được trên tổ hợp phiên bản đang chạy ổn định. Phiên bản mục tiêu là tổ hợp dependency mới cần xác nhận. Dùng cùng test fixtures và cùng database engine/version để so sánh.

```text
Baseline:
  Application commit: <known-good commit>
  Spring Data JDBC:    <current version>
  JDBC driver:         <current version>
  Database:            <engine and version>
  Java runtime:        <current version>

Target:
  Application commit: <upgrade branch>
  Spring Data JDBC:    <target version>
  JDBC driver:         <target version>
  Database:            <same engine/version for first comparison>
  Java runtime:        <same runtime unless Java is also upgraded>
```

Khi muốn nâng database server cùng lúc, trước hết so sánh framework/driver mới trên cùng database version nếu compatibility cho phép. Sau đó chạy ma trận riêng cho database server mới. Cách tách này giúp phân biệt lỗi do framework, driver hay database engine.

### Giữ fixture ổn định

- Dùng dữ liệu có null, Unicode, giá trị biên, decimal, timestamp và collection con.
- Cố định clock và timezone cho test liên quan thời gian.
- Không phụ thuộc thứ tự row nếu query không có ORDER BY.
- Dùng ID rõ ràng khi cần kiểm tra quan hệ; nếu ID do database sinh, kiểm tra giá trị được trả về thay vì giả định sequence bắt đầu từ một con số cố định.
- Tạo schema mới cho mỗi test suite hoặc reset database một cách xác định.
- Không dùng dữ liệu production có thông tin cá nhân; tạo fixture tổng hợp phản ánh hình dạng dữ liệu thực.

Baseline không nhất thiết phải lưu snapshot của toàn bộ database. Hãy lưu kết quả test, log phiên bản, migration version, query plan quan trọng và các số liệu hiệu năng cần so sánh.

## 4. Thiết kế test theo tầng

Một bộ hồi quy tốt kết hợp test nhỏ, integration test và một số kiểm thử vận hành. Mỗi tầng trả lời một loại câu hỏi.

| Tầng | Kiểm tra | Có thể phát hiện |
| --- | --- | --- |
| Unit test | Domain rule, converter thuần, policy routing. | Thay đổi logic ứng dụng hoặc xử lý kiểu. |
| Repository integration test | Mapping, generated key, query và aggregate lifecycle. | Thay đổi framework/driver/database interaction. |
| Transaction integration test | Commit, rollback, isolation và optimistic locking. | Thay đổi transaction/resource behavior. |
| Migration test | Nâng schema từ version cũ và đọc/ghi bằng code mới. | Schema incompatibility và data loss. |
| Contract/API test | JSON, timestamp, enum và error contract. | Thay đổi kiểu dữ liệu lộ ra ngoài ứng dụng. |
| Performance test | Query count, latency, throughput và pool behavior. | N+1, plan regression và resource contention. |
| Staging/canary | Kết nối thật, credentials, network, pool và observability. | Sai khác môi trường không thể mô phỏng bằng unit test. |

`@DataJdbcTest` có thể hữu ích cho repository slice test. Tuy nhiên, nó không tự chứng minh toàn bộ ứng dụng đã được cấu hình đúng. Các kiểm thử transaction, security, custom configuration, migration và datasource routing cần context phù hợp hoặc full integration test.

## 5. Dùng đúng database engine trong integration test

H2 hoặc một database in-memory khác hữu ích cho test nhanh, nhưng không phải lúc nào cũng mô phỏng đúng dialect production. SQL syntax, generated key, type conversion, locking, JSON, array, timestamp, sequence và constraint behavior có thể khác.

Nếu production dùng PostgreSQL, MySQL hoặc SQL Server, nên chạy integration test chính trên cùng engine và một phiên bản tương thích với production. Testcontainers là một lựa chọn để khởi chạy database thật trong pipeline CI; có thể dùng image pin theo version thay vì tag thay đổi theo thời gian.

Ví dụ JUnit với PostgreSQL Testcontainers (cấu hình dependency và property theo phiên bản Spring Boot/Testcontainers của dự án):

```java
@Testcontainers
@DataJdbcTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PurchaseOrderRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name",
            postgres::getDriverClassName);
    }

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void savesAndLoadsAggregate() {
        // Test contract của aggregate trên PostgreSQL thật.
    }
}
```

Ví dụ chỉ minh họa cấu trúc; cần bảo đảm migration schema được áp dụng trong test context và dependency Testcontainers tương thích với Java, JUnit và Spring Boot đang dùng. Pin cả database image và JDBC driver version để kết quả có thể lặp lại.
## 6. Kiểm thử aggregate mapping và quan hệ con

Spring Data JDBC quản lý aggregate theo root. Một upgrade cần bảo đảm object được ghi và đọc lại vẫn giữ đúng quan hệ, thứ tự collection, nullability và khóa ngoại.

Ví dụ aggregate:

```java
@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    @Version Long version,
    String reference,
    String status,
    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    List<OrderLine> lines
) {}

public record OrderLine(
    Long productId,
    int quantity,
    BigDecimal unitPrice
) {}
```

Một regression test nên xác nhận insert, load, update và delete theo hợp đồng domain:

```java
@Test
void persistsRootAndChildRowsAcrossLifecycle() {
    PurchaseOrder draft = new PurchaseOrder(
        null,
        null,
        "PO-REG-001",
        "CREATED",
        List.of(
            new OrderLine(101L, 2, new BigDecimal("12.50")),
            new OrderLine(202L, 1, new BigDecimal("99.00"))
        )
    );

    PurchaseOrder saved = orders.save(draft);

    assertThat(saved.id()).isNotNull();

    PurchaseOrder loaded = orders.findById(saved.id()).orElseThrow();

    assertThat(loaded.reference()).isEqualTo("PO-REG-001");
    assertThat(loaded.lines()).containsExactly(
        new OrderLine(101L, 2, new BigDecimal("12.50")),
        new OrderLine(202L, 1, new BigDecimal("99.00"))
    );
}
```

Đây là contract test minh họa. Điều chỉnh kiểu ID, constructor, mapping và repository theo domain thực tế. Nếu thứ tự child không có ý nghĩa nghiệp vụ, chỉ so sánh tập giá trị thay vì phụ thuộc thứ tự không được bảo đảm.

### Kiểm tra update không làm mất child ngoài ý muốn

Sau khi lưu lần đầu, thay đổi một thuộc tính root rồi lưu lại. Đọc lại và xác nhận child collection còn đúng theo trạng thái aggregate mới. Đồng thời kiểm tra thao tác xóa một child chỉ xóa đúng child đó, không xóa nhầm root hoặc các child khác.

Các trường hợp nên có:

- Aggregate không có child.
- Aggregate có một child và nhiều child.
- Child có field nullable.
- Collection rỗng sau update.
- Thay đổi thứ tự collection nếu thứ tự được lưu bằng key column.
- Foreign key constraint từ child về root.
- Xóa root và kiểm tra child rows theo semantics của mapping.

Không chỉ assert object trả về ngay sau `save`. Đọc lại từ database bằng một repository call mới để kiểm tra dữ liệu thực đã được lưu đúng.
## 7. Kiểm tra generated ID và optimistic locking

Driver upgrade có thể ảnh hưởng cách JDBC trả generated keys hoặc metadata của cột identity/sequence. Với aggregate có ID do database tạo, kiểm tra:

- ID sau insert khác null và đúng kiểu.
- Đọc lại bằng ID vừa nhận trả đúng aggregate.
- Batch insert hoặc saveAll (nếu ứng dụng dùng) trả ID cho từng phần tử theo đúng thứ tự/hợp đồng.
- Sequence/identity không bị reset ngoài ý muốn bởi migration.
- Rollback insert không để ứng dụng giữ một trạng thái giả định rằng row đã commit.

Ví dụ:

```java
@Test
void generatedIdentifierCanBeUsedToReloadAggregate() {
    PurchaseOrder saved = orders.save(newOrder("PO-REG-002"));

    assertThat(saved.id()).isPositive();
    assertThat(orders.findById(saved.id()))
        .isPresent()
        .get()
        .extracting(PurchaseOrder::reference)
        .isEqualTo("PO-REG-002");
}
```

Nếu ID là UUID do ứng dụng tạo, kiểm thử quy tắc UUID generation và mapping riêng. Đừng áp dụng giả định generated key cho mọi kiểu ID.

### Optimistic locking bằng @Version

Với `@Version`, framework giữ version để phát hiện update dựa trên aggregate cũ:

```java
@Test
void staleAggregateCannotOverwriteNewerVersion() {
    PurchaseOrder firstRead =
        orders.findById(orderId).orElseThrow();

    PurchaseOrder secondRead =
        orders.findById(orderId).orElseThrow();

    orders.save(firstRead.withStatus("CONFIRMED"));

    assertThatThrownBy(() ->
        orders.save(secondRead.withStatus("CANCELLED"))
    ).isInstanceOf(OptimisticLockingFailureException.class);
}
```

Test này cần transaction/fixture phù hợp để hai lần đọc thực sự đại diện cho hai snapshot độc lập. Tên exception cụ thể và cách tạo aggregate mới tùy version Spring Data; điều cần bảo vệ là stale write phải bị phát hiện thay vì âm thầm ghi đè thay đổi mới hơn.

Nếu ứng dụng có custom SQL update cùng bảng, thêm test xác nhận custom update cũng kiểm tra và tăng version. Một câu SQL tự viết có thể bypass optimistic locking mặc định.

## 8. Kiểm thử custom converter và type mapping

Driver mới có thể thay đổi kiểu Java mà `ResultSet.getObject(...)` trả về, cách bind `PreparedStatement` hoặc metadata của cột. Điều này đặc biệt đáng chú ý với UUID, JSON, enum, array, decimal, binary, date/time và các kiểu riêng của database.

Nếu ứng dụng có custom type như `Money`, dùng converter rõ ràng:

```java
@WritingConverter
public class MoneyWritingConverter
        implements Converter<Money, BigDecimal> {

    @Override
    public BigDecimal convert(Money source) {
        return source.amount();
    }
}

@ReadingConverter
public class MoneyReadingConverter
        implements Converter<BigDecimal, Money> {

    @Override
    public Money convert(BigDecimal source) {
        return new Money(source);
    }
}
```

Đăng ký converter qua cấu hình `JdbcCustomConversions` phù hợp với phiên bản Spring Data đang dùng. Sau đó kiểm thử round-trip trên database thật:

```java
@Test
void customMoneyTypeRoundTripsThroughDatabase() {
    Invoice invoice = invoices.save(
        new Invoice(null, new Money(new BigDecimal("1234.56")))
    );

    Invoice loaded = invoices.findById(invoice.id()).orElseThrow();

    assertThat(loaded.total())
        .isEqualTo(new Money(new BigDecimal("1234.56")));
}
```

Các giá trị biên nên bao gồm zero, số âm nếu được phép, scale khác nhau, giá trị lớn gần precision column và null nếu field nullable. Với tiền tệ, test cả scale/rounding; không để JDBC driver hoặc database âm thầm làm tròn vượt quy tắc domain.

### Những type nên kiểm tra riêng

| Type | Ca hồi quy nên có |
| --- | --- |
| UUID | Ghi/đọc, bind trong WHERE, null và dạng lưu binary/text theo schema. |
| Enum | Tên enum được lưu, behavior khi gặp giá trị cũ/không biết. |
| BigDecimal | Precision, scale, rounding và giá trị biên. |
| Instant/OffsetDateTime | UTC, offset, precision và timezone session. |
| Boolean | True/false, null và default của database. |
| JSON/JSONB | Serialization, query operator và mapping về domain object. |
| SQL array | Empty array, nhiều phần tử, null và thứ tự. |
| BLOB/CLOB | Kích thước lớn, stream lifecycle và encoding. |
| Custom value object | Converter đọc/ghi, null và tương thích dữ liệu cũ. |

Không phải ứng dụng nào cũng dùng tất cả các type. Chỉ thêm ca kiểm thử phù hợp với schema và API thực tế.

## 9. Kiểm tra null, default và metadata

Driver thay đổi có thể làm lộ giả định sai về SQL NULL, primitive mapping, default expression hoặc column metadata.

Kiểm tra:

- Cột nullable được đọc thành null đúng kiểu wrapper/reference.
- Cột NOT NULL không bị ghi null khi aggregate chưa khởi tạo field.
- Database default được áp dụng khi cột được bỏ khỏi INSERT theo đúng mapping.
- Generated/default timestamp không bị ghi đè bởi giá trị null do ứng dụng bind.
- Column label/alias trong custom query khớp với RowMapper.
- Metadata về precision, scale, column type và generated key không bị code phụ thuộc sai.

Với custom SQL, tránh `SELECT *` nếu mapping dựa trên tên cột không rõ ràng. Liệt kê cột và alias rõ ràng giúp test phát hiện thay đổi schema sớm hơn.

## 10. Kiểm thử repository query và custom SQL

Derived query, `@Query` và custom repository có thể chịu tác động từ query generation, SQL dialect hoặc driver behavior.

Một bộ test nên kiểm tra:

- Derived query theo ID, status, foreign key và null condition.
- `IN` với collection rỗng, một phần tử và nhiều phần tử.
- `LIKE`/case sensitivity/escape nếu nghiệp vụ phụ thuộc.
- Sort ổn định với tie-breaker.
- Pagination: nội dung từng trang và count query.
- `@Query` có named parameter và projection.
- Custom SQL join, aggregate function, CTE hoặc database-specific syntax.
- Update/delete có điều kiện và row count.
- Batch operation nếu ứng dụng dùng batch.
- Error behavior khi vi phạm unique/foreign key/check constraint.

Ví dụ test phân trang phải cố định thứ tự:

```java
@Test
void paginationHasStableOrderingAndCorrectTotal() {
    PageRequest page = PageRequest.of(
        0, 2, Sort.by(Sort.Order.asc("createdAt"),
                      Sort.Order.asc("id"))
    );

    Page<PurchaseOrder> result = orders.findByStatus("CREATED", page);

    assertThat(result.getTotalElements()).isEqualTo(5);
    assertThat(result.getContent()).hasSize(2);
}
```

Fixture cần có nhiều row cùng `createdAt` để test tie-breaker `id`. Không khẳng định thứ tự ổn định nếu query không khai báo `ORDER BY`.
## 11. Kiểm thử transaction, rollback và isolation

Một driver upgrade có thể ảnh hưởng cách connection xử lý autocommit, savepoint, isolation, timeout hoặc exception. Spring transaction abstraction che giấu nhiều chi tiết, nhưng ứng dụng vẫn cần xác nhận hợp đồng commit/rollback.

### Kiểm tra rollback của nhiều thao tác

Giả sử một use case lưu aggregate rồi ghi audit. Nếu bước ghi audit thất bại, cả hai thay đổi phải rollback khi cùng dùng datasource và transaction manager:

```java
@Test
void auditFailureRollsBackOrderUpdate() {
    String originalStatus = orders.findById(orderId)
        .orElseThrow()
        .status();

    assertThatThrownBy(() ->
        workflow.confirmWithAuditFailure(orderId, actorId)
    ).isInstanceOf(DataAccessException.class);

    PurchaseOrder reloaded = orders.findById(orderId).orElseThrow();

    assertThat(reloaded.status()).isEqualTo(originalStatus);
    assertThat(audits.existsFor(orderId, "CONFIRMED")).isFalse();
}
```

Lỗi audit cần xảy ra sau khi update aggregate. Việc đọc lại phải quan sát trạng thái từ transaction mới sau khi transaction nghiệp vụ đã kết thúc. Nếu test framework tự bọc test bằng transaction, hãy quản lý transaction test rõ ràng (ví dụ dùng `TransactionTemplate` hoặc full integration test) để không vô tình kiểm tra dữ liệu bên trong chính transaction đang chạy.

### Các hành vi transaction cần bảo vệ

- `@Transactional` trên service bao trùm các repository call.
- Runtime exception rollback theo chính sách mặc định.
- Checked exception rollback khi có `rollbackFor` tương ứng.
- Exception bị bắt bên trong method không làm test giả định rollback tự động.
- Nested `REQUIRED` tham gia transaction hiện tại.
- `REQUIRES_NEW` có semantics commit độc lập như thiết kế.
- Savepoint/nested transaction nếu ứng dụng dùng và database/driver hỗ trợ.
- Isolation level và locking theo yêu cầu concurrency.
- Timeout, cancellation và connection release khi query thất bại.

Không giả định mọi database hỗ trợ cùng một mức isolation, savepoint hoặc transaction feature. Chạy test trên engine và driver thật mà production dùng.

## 12. Kiểm thử exception translation và lỗi database

Spring JDBC chuyển `SQLException` thành hệ exception `DataAccessException`. Driver mới có thể thay đổi SQLState, vendor error code hoặc message. Điều đó có thể ảnh hưởng exception translation và code ứng dụng nếu code phụ thuộc quá sâu vào message.

Kiểm tra:

- Vi phạm unique constraint được nhận diện đúng nhóm lỗi mà ứng dụng xử lý.
- Vi phạm foreign key/check constraint không bị nhầm thành lỗi kết nối.
- Deadlock/serialization failure có được phân loại phù hợp để retry hay trả lỗi.
- Connection timeout và query timeout được phân biệt.
- Connection reset/network failure không làm lộ trạng thái ghi chưa rõ ràng.
- Error mapping ra API vẫn giữ status/code ổn định theo hợp đồng ứng dụng.

Ưu tiên kiểm tra loại exception và mã lỗi ổn định (SQLState/vendor code) thay vì so khớp toàn bộ message của driver, vì message có thể đổi theo phiên bản hoặc locale.

Ví dụ kiểm tra unique constraint ở mức integration:

```java
@Test
void duplicateBusinessKeyIsRejected() {
    orders.save(orderWithReference("PO-UNIQUE-01"));

    assertThatThrownBy(() ->
        orders.save(orderWithReference("PO-UNIQUE-01"))
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

Nếu ứng dụng cần chuyển lỗi này thành `DuplicateOrderReferenceException`, test thêm service/API boundary để xác nhận mapping đó. Không để controller phụ thuộc vào message nguyên văn của PostgreSQL/MySQL/SQL Server.

## 13. Kiểm thử auditing và lifecycle callbacks

Upgrade Spring Data có thể ảnh hưởng thời điểm hoặc cách callback/auditing được áp dụng. Nếu ứng dụng phụ thuộc vào những hook này, viết test cho kết quả lưu được:

- `@CreatedDate` được gán khi insert.
- `@LastModifiedDate` được cập nhật theo cấu hình.
- `@CreatedBy` và `@LastModifiedBy` nhận đúng actor.
- `BeforeConvertCallback` thay đổi instance được dùng để lưu theo hợp đồng.
- `AfterSaveEvent` không bị hiểu nhầm là transaction đã commit.
- Domain event chỉ được publish trên đường persistence mà ứng dụng thực sự dùng.
- Custom SQL/bulk operation được audit bằng cơ chế riêng nếu không đi qua lifecycle pipeline.

Dùng clock cố định để test timestamp:

```java
@TestConfiguration
static class FixedClockConfiguration {

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2026-11-13T02:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Đọc lại row sau khi save để kiểm tra database đã lưu audit value. Không chỉ kiểm tra object đầu vào hoặc event đã được phát.

## 14. Kiểm thử connection, pool và driver behavior

Một số lỗi chỉ xuất hiện khi connection được mượn/trả từ pool hoặc khi workload chạy đồng thời. Nên kiểm tra:

- Connection được trả về pool sau cả success và exception.
- Connection leak detection không báo leak trong test workload bình thường.
- Validation query hoặc `Connection.isValid(...)` hoạt động với driver mới.
- Connection lifetime, idle timeout và max lifetime không gây ngắt query đang chạy ngoài dự kiến.
- Session state như timezone, schema/search_path, isolation và role được reset hoặc quản lý rõ.
- Prepared statement cache không tạo lỗi khi schema thay đổi.
- Batch insert/update trả update count theo semantics ứng dụng dựa vào.
- Fetch size/streaming result không giữ connection lâu ngoài dự kiến.
- LOB/stream được đóng đúng và không đọc sau khi connection đã trả pool.
- TLS, certificate validation và authentication plugin tương thích với driver mới.

Nếu dùng routing datasource, test thêm tenant/primary/replica route với physical connection thật. Một unit test cho `determineCurrentLookupKey()` không phát hiện việc repository vô tình dùng datasource khác hoặc physical connection được lấy trước khi routing context sẵn sàng.
## 15. Kiểm thử migration từ schema đang chạy

Upgrade framework/driver thường diễn ra cùng thời điểm với thay đổi schema. Cần kiểm tra migration độc lập với việc tạo database mới từ schema cuối cùng.

Một migration regression test nên:

1. Khởi tạo database ở schema version gần nhất của production.
2. Nạp một tập fixture đại diện cho dữ liệu cũ.
3. Chạy toàn bộ migration còn thiếu theo đúng thứ tự.
4. Xác nhận schema version mới được ghi nhận.
5. Kiểm tra dữ liệu cũ không mất hoặc bị biến đổi ngoài ý muốn.
6. Chạy repository read/write bằng phiên bản ứng dụng mới.
7. Kiểm tra constraint, index, default, sequence và view sau migration.

Nếu chỉ tạo database trống bằng schema mới nhất, test không phát hiện lỗi khi nâng dữ liệu từ schema cũ. Hãy giữ một fixture/database snapshot đã được làm sạch dữ liệu nhạy cảm hoặc tạo script seed thể hiện cấu trúc dữ liệu cũ.

### Kiểm tra expand-and-contract khi rolling deployment

Nếu ứng dụng được deploy nhiều instance, phiên bản cũ và mới có thể chạy đồng thời trong một khoảng thời gian. Migration nên tương thích với cả hai trong giai đoạn chuyển tiếp:

- **Expand:** thêm cột/bảng/index mới theo cách phiên bản cũ vẫn hoạt động.
- Deploy code mới có thể đọc/ghi cấu trúc mới, trong khi vẫn tương thích với code cũ khi cần.
- Backfill dữ liệu theo batch và xác nhận kết quả.
- Chuyển traffic/behavior sang cấu trúc mới.
- **Contract:** chỉ xóa cột/bảng cũ sau khi không còn instance hoặc job nào phụ thuộc.

Ví dụ, nếu đổi `customer_name` thành `display_name`, đừng xóa cột cũ trong cùng migration trước khi code đang chạy đã chuyển sang cột mới. Hãy thêm cột mới, dual-write hoặc backfill theo chiến lược đã chọn, deploy code tương thích, rồi mới loại bỏ cột cũ ở release sau.

Không phải mọi migration đều hỗ trợ transaction đầy đủ. Một số database có lệnh DDL không transactional hoặc giới hạn lock. Test migration trên đúng engine và quan sát thời gian chạy, lock, dung lượng log và khả năng phục hồi khi migration thất bại.

## 16. Kiểm tra tương thích dữ liệu sau migration

Ngoài việc migration hoàn tất, kiểm tra các invariant dữ liệu:

- Số lượng row trước/sau theo từng bảng quan trọng.
- Không có orphan child rows.
- Foreign key và unique constraint hợp lệ.
- Giá trị null/default được chuyển đúng.
- Decimal không bị mất precision.
- Timestamp giữ đúng instant hoặc quy tắc local time.
- Enum/string code cũ vẫn được diễn giải.
- Sequence/identity tiếp tục sinh ID không đụng dữ liệu cũ.
- Index và view tồn tại với definition mong muốn.
- Row count theo tenant hoặc phân vùng không thay đổi ngoài dự kiến.

Ví dụ kiểm tra orphan:

```sql
SELECT line.order_id
FROM order_line line
LEFT JOIN purchase_order po ON po.id = line.order_id
WHERE po.id IS NULL;
```

Query phải trả không có row nếu mô hình yêu cầu mọi dòng hàng thuộc một đơn hiện hữu. Với shared schema multi-tenant, join và constraint cần bao gồm tenant key nếu ID chỉ duy nhất trong phạm vi tenant.

Nếu migration có transform dữ liệu, kiểm tra cả số liệu tổng hợp trước/sau. Ví dụ tổng tiền theo currency, số bản ghi theo status hoặc min/max timestamp có thể giúp phát hiện sai lệch mà chỉ kiểm tra row count không tìm thấy.

## 17. Kiểm thử hiệu năng và query plan

Một upgrade có thể không làm thay đổi kết quả nhưng làm tăng số query, đổi SQL sinh ra hoặc khiến driver/pool hoạt động kém hơn. Hãy chọn một tập workload đại diện:

- Tải aggregate root có collection con.
- Lưu aggregate có nhiều child.
- Derived query phổ biến và pagination.
- Custom SQL join/report.
- Batch insert/update nếu có.
- Query có bind collection lớn.
- Transaction giữ connection trong thời gian dài.
- Workload đồng thời qua pool.

Theo dõi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Query count | Phát hiện N+1 hoặc số lệnh SQL tăng. |
| Latency p50/p95/p99 | Nhận diện chậm trung bình và tail latency. |
| Throughput | Số request/transaction xử lý mỗi giây. |
| Connection acquisition time | Phát hiện pool cạn hoặc connection chờ lâu. |
| Active/idle connection | Hiểu tải và cấu hình pool. |
| Lock wait/deadlock | Phát hiện thay đổi concurrency hoặc transaction duration. |
| Rows examined / query plan | Nhận diện index không được dùng hoặc plan thay đổi. |
| Allocation/heap/CPU | Phát hiện mapping hoặc serialization tốn tài nguyên hơn. |

So sánh trên cùng dataset, database version, hardware/container limits, pool configuration và concurrency. Không so sánh một lần chạy local nhỏ với benchmark production rồi kết luận có regression.

Query plan có thể thay đổi do statistics, database version hoặc data distribution, không nhất thiết do Spring Data. Lưu plan của các truy vấn quan trọng trước và sau upgrade; khi plan khác, kiểm tra index, bind parameter type, cardinality estimate và statistics.

### Đặt ngưỡng hồi quy

Không đặt một ngưỡng latency chung cho mọi query. Định nghĩa SLO theo use case và xác định mức suy giảm tối đa chấp nhận được. Nếu p95 tăng 20% nhưng vẫn nằm trong SLO và không tăng chi phí tài nguyên đáng kể, quyết định có thể khác trường hợp p99 vượt SLO hoặc pool liên tục bão hòa.

Dùng nhiều lần chạy và báo cáo median/percentile; loại bỏ ảnh hưởng startup, warm-up và cache khi so sánh.

## 18. Lập ma trận kiểm thử phiên bản

Không cần chạy mọi tổ hợp có thể. Chọn các tổ hợp được nhà cung cấp hỗ trợ và đủ để cô lập thay đổi.

Ví dụ ma trận:

| Lượt | Spring Data/Boot | JDBC driver | Database | Mục tiêu |
| --- | --- | --- | --- | --- |
| Baseline | Hiện tại | Hiện tại | Hiện tại | Xác nhận test và behavior gốc. |
| Framework only | Mục tiêu | Hiện tại | Giữ nguyên | Tìm thay đổi framework. |
| Driver only | Hiện tại | Mục tiêu | Giữ nguyên | Tìm thay đổi driver. |
| Combined target | Mục tiêu | Mục tiêu | Giữ nguyên | Xác nhận tổ hợp dự kiến deploy. |
| Database target | Mục tiêu | Mục tiêu tương thích | Mục tiêu | Xác nhận database server upgrade riêng. |

Nếu một tổ hợp không nằm trong compatibility matrix của vendor, không dùng nó như bằng chứng hỗ trợ. Có thể cần nâng Boot/Framework cùng nhau vì dependency management ràng buộc phiên bản.

### Kiểm tra dependency tree

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-data-jdbc \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency <jdbc-driver-artifact> \
  --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-jdbc
mvn dependency:tree -Dincludes=<driver-group-id>:<driver-artifact-id>
```

Xác nhận runtime thực sự dùng đúng driver version mong muốn, không chỉ nhìn version khai báo trực tiếp. Dependency transitively có thể chọn phiên bản khác do conflict resolution hoặc BOM.

## 19. Quy trình nâng cấp và phát hành có kiểm soát

Một quy trình thực tế có thể chia thành các chặng:

1. **Inventory:** ghi lại dependency, database, driver, Java runtime, schema và custom integration.
2. **Baseline:** chạy test suite hiện tại trên database/driver production-like; lưu kết quả và hiệu năng.
3. **Upgrade riêng lẻ:** nâng framework và driver theo các bước có thể tách nguyên nhân; giữ database cố định ở lượt đầu nếu có thể.
4. **Compile và static checks:** xử lý API deprecation/removal, dependency conflict và cấu hình đã đổi.
5. **Repository integration:** chạy aggregate, converter, query, generated key và lifecycle tests.
6. **Transaction/error tests:** chạy rollback, locking, exception translation và pool tests.
7. **Migration tests:** nâng database từ schema cũ có fixture dữ liệu đại diện.
8. **Performance tests:** so sánh query count, latency, pool và query plan.
9. **Staging:** chạy trên cấu hình gần production, bao gồm TLS, secrets, network và database permissions.
10. **Canary:** deploy một phần traffic, theo dõi error rate, latency, pool, deadlock và data correctness.
11. **Rollout:** mở rộng traffic khi các tín hiệu nằm trong ngưỡng đã định.
12. **Rollback/forward fix:** dùng phương án tương thích schema và dependency đã chuẩn bị trước.

Không coi compile thành công hoặc application startup thành công là đủ. Nhiều lỗi mapping/SQL chỉ xuất hiện khi thực hiện thao tác cụ thể trên database.
## 20. Chuẩn bị rollback và tương thích ngược

Rollback ứng dụng sau khi nâng dependency không phải lúc nào cũng an toàn. Nếu migration đã xóa cột hoặc đổi semantics dữ liệu, phiên bản ứng dụng cũ có thể không đọc được schema mới.

Trước khi deploy, xác định:

- Có thể quay lại binary/dependency cũ mà không cần restore database không?
- Migration có tương thích với cả code cũ và code mới trong giai đoạn rolling deployment không?
- Có thay đổi dữ liệu không thể đảo ngược không?
- Driver mới có ghi định dạng mà driver cũ đọc được không?
- Có thay đổi enum, JSON shape, timestamp precision hoặc encoding không?
- Có thể tắt feature mới bằng feature flag mà không cần rollback schema không?
- Nếu cần forward fix, có migration tiếp theo an toàn không?

### Không giả định downgrade dependency sẽ đảo ngược dữ liệu

Ví dụ, phiên bản mới ghi một enum value mới vào database. Nếu rollback ứng dụng về phiên bản cũ không nhận diện value đó, code cũ có thể lỗi khi đọc row. Tương tự, thay đổi JSON structure hoặc precision timestamp có thể khiến phiên bản cũ diễn giải sai dữ liệu đã ghi.

Nếu cần rollback ứng dụng nhanh, hãy giữ định dạng dữ liệu tương thích ngược trong giai đoạn chuyển tiếp. Chỉ bắt đầu ghi format mới khi tất cả instance đã có khả năng đọc format đó, hoặc dùng versioned payload và migration strategy phù hợp.

Rollback dependency và rollback schema là hai kế hoạch riêng. Một migration đã chạy có thể cần forward migration thay vì downgrade tự động.

## 21. Sắp xếp pipeline CI cho upgrade

Một pipeline có thể chạy từ nhanh đến chậm:

1. Resolve dependency và kiểm tra dependency convergence.
2. Compile main/test source và kiểm tra API deprecation/removal.
3. Chạy unit test domain/converter.
4. Khởi động database container đúng engine/version.
5. Chạy migration từ schema cũ.
6. Chạy repository integration tests.
7. Chạy transaction, locking và lifecycle tests.
8. Chạy custom SQL và driver type tests.
9. Chạy API/contract tests.
10. Chạy performance smoke test cho query trọng yếu.
11. Lưu test report, dependency tree, database version và driver metadata.

Không cần chạy benchmark dài ở mọi pull request nếu chi phí cao. Có thể chạy test hồi quy cốt lõi trên mỗi change, còn workload concurrency/performance dài chạy ở nightly hoặc release candidate. Tuy nhiên, trước khi phát hành cần có kết quả từ toàn bộ nhóm test đã xác định là bắt buộc.

### Lưu thông tin môi trường trong test report

Mỗi lần chạy nên ghi lại:

- Commit ứng dụng.
- Java runtime version.
- Spring Boot, Spring Framework và Spring Data JDBC versions.
- JDBC driver name/version.
- Database product/version.
- Connection pool name/version và các thông số quan trọng.
- Migration/schema version.
- Timezone JVM và timezone database session.
- Test suite, thời gian chạy và kết quả.

Khi một test chỉ thất bại trên CI hoặc staging, các thông tin này giúp phân biệt khác biệt môi trường với regression thật.

## 22. Theo dõi sau khi nâng cấp

Sau canary và rollout, theo dõi các tín hiệu có thể chỉ ra lỗi persistence:

| Tín hiệu | Điều cần chú ý |
| --- | --- |
| Error rate theo SQLState/vendor code | Tăng lỗi constraint, syntax, connection hoặc serialization. |
| Repository/service exception rate | Tăng `DataAccessException` hoặc lỗi optimistic locking bất thường. |
| Query latency p95/p99 | Query chậm hơn hoặc tail latency tăng. |
| Connection pool pending/active | Pool cạn, connection acquisition time tăng hoặc leak. |
| Deadlock/lock wait | Thay đổi transaction duration hoặc lock ordering. |
| Generated ID / sequence metrics | ID bất thường hoặc lỗi duplicate key. |
| Migration status | Instance không đồng nhất schema version. |
| Data invariants | Orphan row, null ngoài dự kiến, count/aggregate totals sai. |
| Replica lag | Read replica trễ hơn và ảnh hưởng read-your-writes. |

Không log toàn bộ parameter chứa thông tin nhạy cảm chỉ để debug driver. Ưu tiên SQLState, operation name, query identifier, correlation ID và metadata đã được làm sạch.

Có thể thêm canary query kiểm tra đọc/ghi một bản ghi kỹ thuật trong schema riêng, nhưng không để health check ghi liên tục vào bảng nghiệp vụ hoặc tạo tải đáng kể. Health check cũng cần kiểm tra đúng datasource route nếu ứng dụng dùng nhiều tenant hoặc primary/replica.

## 23. Ví dụ checklist cho một lần nâng cấp

Một checklist release có thể ghi rõ bằng chứng thay vì chỉ đánh dấu “đã test”:

| Hạng mục | Bằng chứng cần lưu |
| --- | --- |
| Dependency alignment | Dependency tree/runtime driver version. |
| Database compatibility | Database image/version và kết quả repository suite. |
| Aggregate mapping | Test report insert/load/update/delete root + child. |
| Type mapping | Round-trip tests cho các kiểu thực sự sử dụng. |
| Transactions | Commit/rollback, optimistic locking và isolation test. |
| Query behavior | Derived query, @Query, custom SQL, count và pagination tests. |
| Lifecycle/auditing | Callback, event, created/modified timestamp và actor tests. |
| Migration | Test nâng schema cũ cùng fixture; invariant data report. |
| Performance | Baseline/target query count, latency, pool và query plan. |
| Rollback | Kịch bản quay lại binary cũ hoặc forward-fix đã được diễn tập. |
| Staging/canary | Error rate, SQLState, latency, pool và data invariant. |

Chỉ ghi một mục hoàn thành khi có test report, log hoặc kết quả có thể truy lại. Nếu một loại database/driver không có trong môi trường test, ghi rõ giới hạn đó thay vì suy rộng từ một engine khác.

## 24. Câu hỏi tự kiểm tra

- Vì sao compile thành công không chứng minh Spring Data JDBC và driver mới tương thích với ứng dụng?
- Những thành phần nào có thể thay đổi trong một lần upgrade persistence?
- Vì sao cần tách baseline, framework-only, driver-only và combined target?
- Khi nào nên dùng database engine thật thay cho H2?
- Những test nào bảo vệ aggregate root và child collection?
- Vì sao generated ID và optimistic locking cần integration test?
- Driver có thể ảnh hưởng những kiểu dữ liệu và metadata nào?
- Vì sao cần kiểm tra SQL NULL, default và column alias?
- Làm thế nào chứng minh nhiều repository operation cùng rollback?
- Vì sao không nên phụ thuộc vào message nguyên văn của SQLException?
- Làm thế nào kiểm tra auditing và lifecycle callbacks sau upgrade?
- Vì sao migration test phải bắt đầu từ schema cũ có dữ liệu?
- Expand-and-contract giúp rolling deployment an toàn như thế nào?
- Những chỉ số nào có thể chỉ ra performance regression?
- Khi nào rollback binary cũ có thể không tương thích với schema/dữ liệu mới?
- Bằng chứng nào cần được lưu trong release report?

Kiểm thử hồi quy khi nâng Spring Data hoặc JDBC driver phải dựa trên các hợp đồng persistence mà ứng dụng thực sự sử dụng. Tách thay đổi framework, driver và database để dễ xác định nguyên nhân; chạy integration test trên đúng database engine; kiểm tra aggregate, generated ID, converter, query, transaction, lifecycle và migration; rồi so sánh hiệu năng và theo dõi canary. Chuẩn bị trước khả năng rollback ứng dụng cùng schema compatibility, vì dependency downgrade không tự đảo ngược dữ liệu đã ghi.
