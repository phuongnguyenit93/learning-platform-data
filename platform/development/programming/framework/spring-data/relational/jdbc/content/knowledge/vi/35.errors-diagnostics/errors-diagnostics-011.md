# Quy trình tái hiện lỗi tối thiểu bằng SQL log và integration test

Khi một truy vấn Spring Data JDBC chạy sai, lỗi có thể đến từ nhiều tầng: tên property trong derived query, SQL được tạo bởi dialect, bind parameter, mapping ResultSet, quan hệ aggregate, transaction, schema migration hoặc JDBC driver. Chỉ nhìn exception cuối cùng thường chưa đủ để xác định tầng gây lỗi.

Một quy trình tái hiện đáng tin cậy cần thu thập được:

1. **Thông tin môi trường:** phiên bản Spring Data JDBC, Spring Framework/Spring Boot, JDBC driver, database và dialect.
2. **SQL thực tế:** statement đã chạy, thứ tự statement và parameter values cần thiết để tái hiện.
3. **Dữ liệu tối thiểu:** các hàng trong bảng đủ để làm lỗi xuất hiện.
4. **Transaction context:** method nào mở transaction, isolation level, rollback/commit và các thao tác trước khi lỗi xảy ra.
5. **Integration test:** test độc lập chạy được trên cùng database engine, khẳng định lỗi và kết quả mong đợi.

Mục tiêu là biến một lỗi khó tái hiện trong ứng dụng thành một ví dụ nhỏ có thể chạy lặp lại. Khi test thất bại, ta có bằng chứng về query, mapping hoặc transaction đang sai; khi sửa xong, test trở thành regression test để ngăn lỗi quay lại.

## 1. Xác định chính xác triệu chứng trước khi bật log

Trước khi thay đổi cấu hình logging, ghi lại hành vi cụ thể:

- Repository method nào được gọi?
- Input/parameter nào làm lỗi xuất hiện?
- Lỗi xảy ra với mọi dữ liệu hay chỉ một nhóm record?
- Lỗi xảy ra ở SELECT, INSERT, UPDATE hay DELETE?
- Exception là Spring DataAccessException, MappingException, OptimisticLockingFailureException hay SQLException?
- Lỗi xảy ra ngay khi execute statement hay chỉ khi commit?
- Có transaction hay method chạy autocommit?
- Có khác biệt giữa local, CI và production không?

Ví dụ mô tả chưa đủ:

> Query repository bị lỗi.

Mô tả có thể tái hiện:

> Khi gọi findByStatusAndCreatedAtAfter("PAID", 2026-01-01T00:00), PostgreSQL trả SQLState 42703 do câu SQL tham chiếu cột createdAt. Lỗi chỉ xuất hiện sau migration V18; H2 test vẫn pass.

Mô tả thứ hai đã thu hẹp phạm vi: method, input, database, SQLState và thời điểm thay đổi schema.

## 2. Thu thập phiên bản và metadata database

Cùng một code có thể tạo SQL hoặc bind type khác nhau theo dialect/driver. Hãy ghi lại tối thiểu:

| Thông tin | Ví dụ |
|---|---|
| Spring Boot | Phiên bản đang chạy |
| Spring Framework | Phiên bản được dependency management chọn |
| Spring Data Relational/JDBC | Phiên bản thực tế |
| JDBC driver | PostgreSQL/MySQL/SQL Server driver và version |
| Database product | PostgreSQL, MySQL, Oracle, SQL Server... |
| Database version | Major/minor version |
| Dialect | JdbcDialect được Spring Data JDBC resolve |
| Schema version | Flyway/Liquibase migration cuối cùng |
| Transaction isolation | READ_COMMITTED, REPEATABLE_READ... |
| Connection pool | HikariCP hoặc pool khác |
| SQL mode/collation/timezone | Khi có liên quan đến lỗi |

Không chỉ ghi JDBC URL. Một URL có thể trỏ qua proxy hoặc endpoint khác; cần biết database product/version mà connection thực sự kết nối.

### Đọc metadata qua JdbcTemplate

~~~java
@Component
public class DatabaseDiagnostics {

    private final JdbcTemplate jdbcTemplate;

    public DatabaseDiagnostics(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void logMetadata() {
        jdbcTemplate.execute((ConnectionCallback<Void>) connection -> {
            DatabaseMetaData metadata = connection.getMetaData();

            log.info("Database product: {}", metadata.getDatabaseProductName());
            log.info("Database version: {}", metadata.getDatabaseProductVersion());
            log.info("JDBC driver: {}", metadata.getDriverName());
            log.info("JDBC driver version: {}", metadata.getDriverVersion());

            return null;
        });
    }
}
~~~

Đây là code chẩn đoán. Không ghi password, token hoặc toàn bộ JDBC URL nếu URL có chứa credential. Chỉ log metadata cần thiết.

Có thể inject JdbcDialect để kiểm tra dialect Spring Data JDBC đã chọn:

~~~java
@Component
public class DialectDiagnostics {

    public DialectDiagnostics(JdbcDialect dialect) {
        log.info("Spring Data JDBC dialect: {}", dialect.getName());
    }
}
~~~

## 3. Bật SQL logging của Spring JDBC

Spring Data JDBC sử dụng hạ tầng Spring JDBC để thực thi statement. Vì vậy, để xem SQL được chạy, hãy bật logging cho package Spring JDBC.

Trong application.yaml:

~~~yaml
logging:
  level:
    org.springframework.jdbc: DEBUG
~~~

Hoặc application.properties:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Tài liệu Spring Data JDBC hướng dẫn bật DEBUG cho org.springframework.jdbc để xem các statement do NamedParameterJdbcTemplate/JdbcTemplate thực thi. Spring Data JDBC tự thân có rất ít logging SQL; phần thực thi query nằm ở Spring JDBC.

Khi log bật, tìm các dòng theo thời điểm request/test xảy ra. Ghi lại:

- SQL statement.
- Thứ tự SELECT/INSERT/UPDATE/DELETE.
- Số lần cùng một query được gọi.
- Exception ngay sau statement nào.
- Transaction begin/commit/rollback nếu transaction logging được bật.

### Khi cần bind parameter values

SQL log không phải lúc nào cũng hiển thị đầy đủ giá trị parameter. Nếu cần biết chính xác giá trị được bind:

- Dùng datasource-proxy hoặc P6Spy trong môi trường local/test.
- Hoặc instrument JDBC layer để ghi statement và parameter theo cách có kiểm soát.
- Nếu bật logger chi tiết cho binding, chỉ bật trong thời gian điều tra và kiểm tra output trước khi chia sẻ.

Không đưa dữ liệu cá nhân, access token, password, email nhạy cảm hoặc payload bí mật vào log. Mask giá trị hoặc thay bằng fixture giả nhưng giữ nguyên kiểu dữ liệu/độ dài có thể gây lỗi.

Ví dụ cấu hình datasource-proxy/P6Spy phải phù hợp dependency và phiên bản ứng dụng; không cài thêm công cụ logging vào production chỉ để chẩn đoán một lỗi ngắn hạn nếu chưa đánh giá chi phí và rủi ro lộ dữ liệu.

## 4. Đọc SQL log theo thứ tự, không chỉ nhìn câu cuối cùng

Một aggregate load có thể tạo nhiều statement. Ví dụ:

~~~text
1. SELECT purchase_order WHERE id = ?
2. SELECT order_line WHERE order_id = ?
3. SELECT line_note WHERE order_line_id IN (...)
~~~

Nếu statement thứ ba thất bại, câu SELECT root đầu tiên có thể hoàn toàn đúng. Cần biết lỗi nằm ở:

- SQL được tạo sai.
- Parameter bind sai kiểu hoặc sai giá trị.
- Tên cột/bảng không khớp schema.
- Một query collection được tạo theo mapping không mong đợi.
- Database constraint/permission.
- ResultSet không map được vào constructor/property.
- Transaction đã bị đánh dấu rollback-only trước đó.

Đánh số các statement theo thời gian và gắn với request/test ID để biết chúng thuộc cùng một lần thực thi.

### Phân biệt lỗi SQL và lỗi mapping

| Dấu hiệu | Tầng cần kiểm tra |
|---|---|
| SQLSyntaxErrorException, undefined column/table | SQL, schema, dialect, naming strategy |
| ConstraintViolationException/DataIntegrityViolationException | Dữ liệu, FK, unique/check constraint |
| ConversionFailedException/MappingException | JDBC type, converter, constructor/property mapping |
| IncorrectResultSizeDataAccessException | Method mong một kết quả nhưng SQL trả nhiều hàng |
| EmptyResultDataAccessException | Caller yêu cầu một hàng nhưng không có kết quả |
| OptimisticLockingFailureException | Version stale hoặc update/delete không còn khớp |
| TransactionSystemException khi commit | Lỗi xuất hiện lúc commit/rollback |
| QueryTimeoutException | Query/statement timeout hoặc database bị chậm |

Đừng chỉ sửa exception message cuối cùng. Tìm SQL/operation đầu tiên tạo ra trạng thái lỗi.

## 5. Chạy SQL độc lập trên database

Sau khi lấy được SQL và parameters, hãy chuyển nó thành một câu SQL có thể chạy trong database client.

Ví dụ log:

~~~sql
SELECT id, status, created_at
FROM purchase_order
WHERE status = ?
  AND created_at > ?
ORDER BY created_at DESC, id DESC;
~~~

Parameter được bind:

~~~text
1 = "PAID" (VARCHAR)
2 = 2026-01-01T00:00:00 (TIMESTAMP)
~~~

Khi chạy độc lập:

~~~sql
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'PAID'
  AND created_at > TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC, id DESC;
~~~

Giữ đúng:

- Database engine/version.
- Schema và search_path.
- User/permissions.
- Kiểu parameter (VARCHAR, BIGINT, TIMESTAMP, UUID...).
- Timezone và collation nếu liên quan.
- Transaction isolation nếu lỗi liên quan concurrency.
- Dữ liệu fixture tương ứng.

Nếu SQL chạy độc lập vẫn lỗi, điều tra SQL/schema/database. Nếu SQL chạy độc lập đúng nhưng Spring Data JDBC lỗi, tập trung vào bind type, mapping, transaction context, connection/session hoặc thứ tự query.

Không copy parameter nhạy cảm từ production log vào ticket hoặc test fixture. Tạo dữ liệu giả có cùng kiểu và đặc điểm làm lỗi xuất hiện.

## 6. Thu nhỏ dữ liệu để có minimal reproduction

Một minimal reproduction nên có ít nhất:

- Một entity/aggregate root liên quan.
- Chỉ các bảng thực sự cần cho query.
- Một vài fixture đủ làm lỗi xuất hiện.
- Một repository method hoặc service method.
- Một test duy nhất tái hiện lỗi.
- Schema/migration cần thiết.
- Phiên bản dependency/database rõ ràng.

Ví dụ nếu lỗi xảy ra khi tải một order có collection:

~~~text
purchase_order
  id = 100
  status = PAID

order_line
  id = 1, order_id = 100
  id = 2, order_id = 100
~~~

Không cần nhập toàn bộ database production với hàng triệu hàng nếu hai hàng child đã đủ tái hiện. Nhưng nếu lỗi chỉ xảy ra khi có duplicate, NULL, chuỗi Unicode, timestamp cùng timezone hoặc cardinality lớn, fixture phải giữ lại đặc điểm đó.

### Giữ lại điều kiện gây lỗi

Khi rút gọn, không vô tình loại bỏ:

- Cột nullable hoặc dữ liệu NULL.
- Duplicate business key.
- Một root có 0 child so với một root có nhiều child.
- Tên cột trùng SQL reserved word.
- Kiểu UUID/JSON/array/vendor-specific.
- Precision/scale của decimal.
- Timestamp có timezone/offset.
- Version stale hoặc concurrent update.
- Transaction đang mở và thứ tự gọi repository.

Minimal reproduction không phải fixture ít hàng nhất bằng mọi giá; đó là tập dữ liệu nhỏ nhất vẫn làm lỗi xảy ra ổn định.

## 7. Tạo integration test bằng @DataJdbcTest

@DataJdbcTest phù hợp để kiểm thử repository và mapping Spring Data JDBC. Trong Spring Boot, test slice thường cấu hình DataSource, JdbcTemplate, Spring Data JDBC repositories và transaction test. Test mặc định thường rollback khi kết thúc.

Ví dụ:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryReproductionTest {

    @Autowired PurchaseOrderRepository repository;
    @Autowired JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setUp() {
        jdbcTemplate.update("""
                INSERT INTO purchase_order(id, customer_id, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                100L,
                10L,
                "PAID",
                Timestamp.valueOf("2026-01-10 09:00:00")
        );
    }

    @Test
    void reproducesTheUnexpectedResult() {
        List<PurchaseOrder> result = repository.findByStatus("PAID");

        assertThat(result)
                .extracting(PurchaseOrder::getId)
                .containsExactly(100L);
    }
}
~~~

Test này minh họa cách cô lập repository query. Nếu lỗi phụ thuộc migration/schema, để test chạy migration hoặc cung cấp schema SQL giống ứng dụng. Nếu lỗi phụ thuộc custom converter/RowMapper, import configuration tương ứng bằng @Import.

### Chỉ load những gì test cần

Test slice giúp loại bỏ web server, controller và nhiều bean không liên quan. Nếu lỗi chỉ xuất hiện trong repository mapping, không cần khởi động toàn bộ application context.

Dùng @SpringBootTest khi reproduction cần:

- Application service và transaction proxy.
- Nhiều repository phối hợp.
- Custom application configuration mà slice không nạp.
- Transaction manager hoặc nhiều DataSource wiring.
- Một use case đi qua nhiều tầng.

Không dùng mock repository/JdbcTemplate để tái hiện lỗi SQL thật. Mock hữu ích cho unit test logic, nhưng không kiểm tra SQL syntax, JDBC binding, database constraints, dialect hoặc ResultSet mapping.

## 8. Tái hiện lỗi transaction và rollback

Nếu lỗi xảy ra khi nhiều thao tác phải cùng commit/rollback, hãy gọi service Spring qua proxy và xác nhận trạng thái database sau khi transaction kết thúc.

Service:

~~~java
@Service
public class OrderWorkflow {

    private final PurchaseOrderRepository repository;
    private final JdbcTemplate jdbcTemplate;

    public OrderWorkflow(
            PurchaseOrderRepository repository,
            JdbcTemplate jdbcTemplate) {
        this.repository = repository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void createOrderThenFail(PurchaseOrder order) {
        PurchaseOrder saved = repository.save(order);

        jdbcTemplate.update("""
                INSERT INTO order_audit(order_id, event_type)
                VALUES (?, ?)
                """,
                saved.getId(),
                "CREATED"
        );

        throw new IllegalStateException("Reproduction failure");
    }
}
~~~

Integration test:

~~~java
@SpringBootTest
class OrderWorkflowTransactionReproductionTest {

    @Autowired OrderWorkflow workflow;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackAllWritesAfterFailure() {
        assertThatThrownBy(() ->
                workflow.createOrderThenFail(
                        new PurchaseOrder(10L, "DRAFT", LocalDateTime.now())
                )
        ).isInstanceOf(IllegalStateException.class);

        Integer orderCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM purchase_order WHERE customer_id = ?",
                Integer.class,
                10L
        );

        Integer auditCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM order_audit WHERE event_type = ?",
                Integer.class,
                "CREATED"
        );

        assertThat(orderCount).isZero();
        assertThat(auditCount).isZero();
    }
}
~~~

Test minh họa cần schema, constructor và fixture phù hợp với ứng dụng. Điểm quan trọng là test không tự mở transaction ngoài che mất kết quả của service. Gọi service bean qua Spring proxy để transaction của service kết thúc trước khi assertion đọc dữ liệu.

Nếu test method cũng có @Transactional, assertion có thể vẫn nằm trong transaction ngoài; hãy kiểm soát transaction test rõ ràng khi kiểm tra commit/rollback thực tế.

## 9. Dùng Testcontainers khi lỗi phụ thuộc database/driver

H2 không phải bản thay thế hoàn hảo cho PostgreSQL, MySQL, SQL Server hoặc Oracle. Các engine có thể khác nhau về:

- SQL syntax và dialect.
- Generated keys/identity/sequence.
- UUID, JSON, array và timestamp binding.
- Case sensitivity và identifier quoting.
- Unique/FK/check constraints.
- Locking, isolation và transaction behavior.
- Window functions và execution plan.

Nếu lỗi chỉ xuất hiện trên production database, dùng Testcontainers để chạy cùng engine và JDBC driver trong integration test.

Ví dụ PostgreSQL:

~~~java
@Testcontainers
@SpringBootTest
class PurchaseOrderPostgresReproductionTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("sales")
                    .withUsername("app")
                    .withPassword("secret");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add(
                "spring.datasource.driver-class-name",
                postgres::getDriverClassName
        );
    }
}
~~~

Chạy migration/schema của ứng dụng trên container trước test. Nếu lỗi phụ thuộc version, pin image về major/minor phù hợp; không dùng tag trôi nổi khi cần reproduction ổn định.

Testcontainers giúp kiểm tra database thật trong môi trường tự động hóa, nhưng không tự tạo ra dữ liệu giống production. Fixture vẫn phải giữ điều kiện gây lỗi.

## 10. Phân tích execution plan khi query chậm

Nếu query đúng nhưng chậm, lấy execution plan trên cùng database và parameter có tính đại diện.

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Quan sát:

- Estimated rows so với actual rows.
- Sequential scan hay index scan.
- Join order và join algorithm.
- Sort có spill ra disk không.
- Buffer hits/reads.
- Thời gian từng node.
- Filter loại bỏ bao nhiêu rows.

EXPLAIN ANALYZE thực thi query thật. Cẩn thận với statement ghi dữ liệu; dùng transaction rollback hoặc chỉ phân tích SELECT phù hợp. Trên production, dùng kế hoạch có kiểm soát và quyền phù hợp.

Nếu query chậm chỉ ở một nhóm parameter, so sánh selectivity và execution plan với parameter nhanh. Đừng thêm index chỉ dựa vào việc thấy một query chậm; xác định predicate, sort và workload ghi trước.

## 11. Ghi lại exception chain và SQLState

Spring JDBC dịch SQLException thành hệ thống DataAccessException. Exception ngoài cùng thường cho biết loại lỗi ở mức Spring; SQLException cause có thể cung cấp SQLState và vendor error code.

Khi log lỗi, ghi:

- Exception class ngoài cùng.
- Cause chain.
- SQLState nếu có.
- Vendor error code.
- Repository/service method.
- Request/test ID.
- Database product/version và driver version.
- Transaction boundary và rollback status.

Ví dụ xử lý ở tầng service/logging:

~~~java
try {
    repository.findByStatus("PAID");
} catch (DataAccessException ex) {
    log.error("Database operation failed", ex);
    throw ex;
}
~~~

Không bắt DataAccessException rồi trả danh sách rỗng hoặc giá trị mặc định nếu điều đó che giấu lỗi dữ liệu. Hãy giữ exception và context đủ để điều tra.

Nếu lỗi chỉ xuất hiện lúc commit, xem cả exception từ transaction manager. Một số lỗi deadlock/serialization có thể được database báo ở cuối transaction thay vì tại statement đầu tiên.

## 12. Kiểm tra mapping và schema

Nếu SQL chạy độc lập nhưng repository mapping lỗi, so sánh ResultSet với entity metadata:

- Cột có tên khớp @Column/NamingStrategy không?
- Constructor của entity có nhận đủ cột cần thiết không?
- Kiểu JDBC trả về có converter tương ứng không?
- Embedded property có prefix alias đúng không?
- Collection có FK/key column đúng không?
- Version property có cột version và giá trị hợp lệ không?
- SQL custom có trả đủ cột cho default RowMapper không?

Với @Query trả aggregate root, cột dùng trong constructor phải có mặt. Property set bằng field/setter/wither có thể không được gán nếu query không trả cột tương ứng. Với one-to-one/embedded, alias cần theo quy tắc mapping; collection entity được tải bằng query riêng.

Nếu dùng custom RowMapper hoặc ResultSetExtractor, test mapper riêng bằng ResultSet mẫu nếu có thể, sau đó chạy integration test xác nhận JDBC driver trả kiểu dữ liệu như mong đợi.

## 13. Log an toàn và có thể chia sẻ

SQL log có thể chứa dữ liệu người dùng hoặc business data. Trước khi gửi log cho người khác:

- Mask email, phone, address, token, password và dữ liệu cá nhân.
- Thay ID production bằng ID giả nhưng giữ quan hệ tương ứng.
- Không gửi JDBC URL có credential.
- Xóa thông tin kết nối nội bộ không cần thiết.
- Giữ SQLState, vendor code, tên bảng/cột và kiểu dữ liệu nếu chúng cần cho chẩn đoán.
- Giữ timestamp/offset khi timezone là nguyên nhân.
- Ghi rõ parameter đã được mask hay thay bằng fixture.

Không bật TRACE hoặc logging parameter values lâu dài trong production nếu chưa có chính sách bảo vệ log.

## 14. Mẫu báo cáo minimal reproduction

Khi tạo reproduction để gửi cho nhóm khác hoặc báo issue, dùng cấu trúc:

~~~text
Title:
Một câu mô tả hành vi sai.

Environment:
- Spring Boot:
- Spring Framework:
- Spring Data Relational:
- JDBC driver:
- Database product/version:
- Dialect:
- Schema migration:
- Transaction isolation:

Expected:
Kết quả đúng cần có.

Actual:
Kết quả/exception thực tế.

Repository/service method:
Tên method và input tối thiểu.

SQL:
Statement thực tế đã được log.

Parameters:
Tên, giá trị giả đã mask và JDBC type.

Fixture:
DDL và số hàng tối thiểu để tái hiện.

Transaction:
Có/không, boundary, commit/rollback.

Reproduction:
Lệnh chạy một integration test duy nhất.

Failure:
Assertion/exception và SQLState/vendor code.

Notes:
Khác biệt giữa database local và production.
~~~

Một reproduction tốt không cần cả source code ứng dụng. Nó cần đủ schema, fixture, dependency/version, SQL và test để người khác chạy và nhìn thấy cùng một lỗi.

## 15. Quy trình tái hiện từ đầu đến cuối

1. **Ghi nhận triệu chứng:** method, input, exception và thời điểm.
2. **Thu thập môi trường:** framework, driver, database version, dialect, schema migration và isolation.
3. **Bật SQL logging:** dùng org.springframework.jdbc=DEBUG; bổ sung datasource-proxy/P6Spy trong test nếu cần bind values/query count.
4. **Gắn tương quan:** đánh dấu request/test ID và thứ tự statements.
5. **Phân loại lỗi:** SQL, binding, mapping, constraint, transaction, concurrency hay performance.
6. **Rút gọn fixture:** giữ lại đúng dữ liệu/kiểu/quan hệ làm lỗi xuất hiện.
7. **Chạy SQL độc lập:** cùng database, schema, parameter type và transaction semantics.
8. **Tạo integration test:** dùng @DataJdbcTest cho repository hoặc @SpringBootTest cho service/transaction.
9. **Dùng database thật nếu cần:** Testcontainers với cùng engine/driver/version.
10. **Giữ regression test:** assert kết quả hoặc exception cụ thể để lỗi không quay lại.
11. **Ghi báo cáo:** environment, SQL, parameters đã mask, fixture, command chạy test và expected/actual.

### Bảng quyết định nhanh

| Triệu chứng | Bước điều tra đầu tiên |
|---|---|
| SQL syntax/column/table error | Bật SQL log, kiểm tra DDL, dialect và chạy SQL độc lập |
| Kết quả rỗng hoặc sai hàng | Ghi parameter, fixture và điều kiện WHERE |
| Mapping/conversion error | So sánh ResultSet columns/types với entity/RowMapper |
| Lỗi FK/unique/check | Tái hiện bằng fixture nhỏ và ghi vendor error code |
| Optimistic locking failure | Ghi ID/version và thứ tự transaction cập nhật |
| Rollback không như mong đợi | Tạo service integration test và kiểm tra transaction manager/DataSource |
| Query count bất thường | Instrument statement count và xác định N+1 |
| Query chậm | EXPLAIN/ANALYZE, rows, index, buffers và parameter selectivity |
| Chỉ lỗi trên production DB | Testcontainers với đúng engine/driver/version |

**Điểm cốt lõi:** tái hiện lỗi bằng cách ghi lại SQL và môi trường thật, thu nhỏ dữ liệu nhưng giữ nguyên điều kiện gây lỗi, rồi khóa hành vi bằng integration test. SQL log cho biết framework đã chạy gì; chạy SQL độc lập giúp tách lỗi database khỏi lỗi Spring mapping/transaction; Testcontainers xác nhận lỗi trên đúng engine. Luôn mask dữ liệu nhạy cảm và giữ reproduction nhỏ, xác định, chạy lặp lại được.

## Tài liệu tham khảo chính thức

- [Spring Data Relational — Getting Started: Logging](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): logging SQL thông qua Spring JDBC và logger org.springframework.jdbc.
- [Spring Framework — JDBC Core Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcTemplate, exception handling và logging SQL.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình logging.level theo package/logger.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): @DataJdbcTest, @SpringBootTest và test slices.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): chạy PostgreSQL trong integration test.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): phân tích execution plan và hiệu năng query.

