# Xây dựng lớp SQL dùng chung và kiểm thử từng phương ngữ

## 1. Mục tiêu và phạm vi

Một ứng dụng có thể hỗ trợ PostgreSQL, MySQL, SQL Server, Oracle hoặc SQLite. Các DBMS đều hiểu SQL nhưng khác nhau ở cú pháp phân trang, upsert, generated key, kiểu dữ liệu, JSON, UUID, Boolean, identifier, transaction và mã lỗi.

Lớp SQL dùng chung cần giữ **cùng hợp đồng nghiệp vụ** trên các hệ được hỗ trợ. Nó không bắt buộc mọi hệ chạy một chuỗi SQL giống hệt nhau. Truy vấn portable có thể viết một lần; cú pháp riêng được render bởi dialect tương ứng.

Ví dụ, yêu cầu lấy trang đơn hàng mới nhất có cùng ý nghĩa trên mọi hệ, nhưng SQL phân trang khác nhau. Repository gọi một API chung; dialect tạo phần SQL phù hợp.

~~~text
Application / Service
        |
        v
Repository contract
        |
        +--------------------------+
        |                          |
        v                          v
Shared SQL core               Dialect capabilities
- bind values                 - pagination
- map rows                    - upsert
- transaction                 - generated keys
- resource lifecycle          - UUID / JSON / Boolean
        |                          |
        +-------------+------------+
                      |
                      v
                 JDBC / Driver
                      |
        PostgreSQL / MySQL / SQL Server
                Oracle / SQLite
~~~

Bài này dùng Java/JDBC để minh họa, nhưng nguyên tắc kiến trúc và kiểm thử cũng áp dụng cho các ngôn ngữ, ORM và framework khác.

## 2. Xác định hợp đồng trước khi viết dialect

Đừng bắt đầu bằng một interface lớn. Trước tiên hãy mô tả hành vi mà ứng dụng cần.

Ví dụ:

~~~text
OrderRepository
  findById(id)
    - trả một đơn nếu tồn tại
    - trả empty nếu không có
    - không trả nhiều hơn một đơn

  findPage(customerId, cursor, pageSize)
    - lọc theo khách hàng
    - sắp xếp ordered_at DESC, order_id DESC
    - trả tối đa pageSize hàng
    - cursor không làm trùng hoặc bỏ sót hàng

  markPaid(orderId)
    - chỉ chuyển PENDING thành PAID
    - trả số hàng đã cập nhật
    - không thay đổi trạng thái khác
~~~

Hợp đồng phải làm rõ:

1. Cardinality: không hàng, một hàng hay nhiều hàng?
2. Nullability: cột nào có thể NULL?
3. Ordering: có thứ tự ổn định và tie-breaker duy nhất không?
4. Pagination: offset hay keyset? Có yêu cầu snapshot không?
5. Concurrency: hai request cùng cập nhật thì kết quả mong đợi là gì?
6. Atomicity: thao tác nào phải cùng commit hoặc rollback?
7. Error semantics: duplicate key, deadlock và timeout được ánh xạ thế nào?
8. Type mapping: UUID, Boolean, decimal, timestamp và JSON có contract gì?
9. Compatibility: DBMS và driver version nào được hỗ trợ?
10. Performance: kích thước dữ liệu, latency và concurrency mục tiêu?

Một API không định nghĩa những điểm này chỉ che giấu khác biệt chứ không giải quyết chúng.

## 3. Chia portable SQL và SQL theo dialect

| Nhóm | Ví dụ | Cách tổ chức |
| --- | --- | --- |
| Portable SQL | SELECT, INSERT, UPDATE, DELETE, JOIN, EXISTS, bind parameters | Viết một lần nếu schema tương thích |
| Dialect SQL | LIMIT/OFFSET, upsert, generated key, lock clause | Một implementation theo DBMS |
| Vendor-specific | JSONB, SQL Server OUTPUT, Oracle hints | Adapter/repository riêng có contract và test |

Ưu tiên SQL chuẩn khi nó đủ rõ:

~~~sql
SELECT order_id, order_status
FROM orders
WHERE customer_id = ?
ORDER BY order_id
~~~

Không ép mọi DBMS vào một câu SQL “đa năng” có nhiều nhánh điều kiện, implicit cast hoặc hàm giả lập. Cách đó có thể khó tối ưu và khó hiểu.

Tránh rải kiểm tra tên DBMS trong từng repository:

~~~java
if (databaseName.contains("PostgreSQL")) {
    // SQL riêng
} else if (databaseName.contains("MySQL")) {
    // SQL riêng
}
~~~

Hãy chọn một dialect ở composition root rồi inject vào persistence layer.

## 4. Phân chia trách nhiệm

Cấu trúc tham khảo:

~~~text
domain/
  Order.java
  OrderStatus.java
repository/
  OrderRepository.java
  JdbcOrderRepository.java
persistence/
  DataSourceFactory.java
  JdbcExecutor.java
  RowMapper.java
  SqlParameter.java
  TransactionRunner.java
  dialect/
    SqlDialect.java
    PostgreSqlDialect.java
    MySqlDialect.java
    SqlServerDialect.java
    OracleDialect.java
    SqliteDialect.java
test/
  dialect/
  repository-contract/
  integration/
  migration/
~~~

- **Domain:** mô hình và quy tắc nghiệp vụ, không chứa SQL.
- **Repository interface:** mô tả thao tác dữ liệu theo ngôn ngữ nghiệp vụ.
- **Repository implementation:** phối hợp query và mapping.
- **JdbcExecutor:** bind, execute, map và đóng Statement/ResultSet.
- **SqlDialect:** tạo cú pháp phụ thuộc DBMS.
- **TransactionRunner:** quản lý transaction nếu chưa dùng transaction manager của framework.
- **Integration tests:** xác minh contract trên database/driver thật.

Không để domain phụ thuộc vào kiểu UUID, JSONB hoặc mã lỗi riêng của một DBMS.

## 5. Thiết kế SqlDialect và capability

### 5.1. Bắt đầu với interface nhỏ

~~~java
public interface SqlDialect {
    String name();
    String paginationClause();
    GeneratedKeyMode generatedKeyMode();
}
~~~

Khi có use case thực tế, có thể tách capability:

~~~java
public interface PaginationDialect {
    String renderPage(PageRequest page);
}

public interface UuidDialect {
    void bindUuid(PreparedStatement statement,
                  int index,
                  UUID value) throws SQLException;

    UUID readUuid(ResultSet resultSet,
                  String column) throws SQLException;
}
~~~

Không bắt buộc mọi dialect implement mọi capability. Nếu một DBMS không hỗ trợ tính năng được yêu cầu, hãy báo unsupported rõ ràng thay vì render SQL sai.

### 5.2. Mô tả capability đúng mức

~~~java
public enum GeneratedKeyMode {
    JDBC_GENERATED_KEYS,
    RETURNING_CLAUSE,
    OUTPUT_CLAUSE,
    OUT_PARAMETER,
    APPLICATION_GENERATED
}
~~~

Một record capability có thể hữu ích:

~~~java
public record DialectCapabilities(
    boolean supportsNativeBoolean,
    boolean supportsNativeUuid,
    boolean supportsSavepoints,
    boolean supportsReturning
) {}
~~~

Đừng dùng một cờ quá rộng như supportsJson để đại diện cho mọi tính năng JSON. JSON type, JSON aggregation, JSON path và JSON indexing là các khả năng khác nhau.

Khả năng phải gắn với **DBMS version, driver version và cấu hình**; không chỉ dựa vào tên sản phẩm.

### 5.3. Chọn dialect tại composition root

~~~java
public final class PersistenceConfiguration {
    public static SqlDialect createDialect(String name) {
        return switch (name.toLowerCase(Locale.ROOT)) {
            case "postgresql" -> new PostgreSqlDialect();
            case "mysql" -> new MySqlDialect();
            case "sqlserver" -> new SqlServerDialect();
            case "oracle" -> new OracleDialect();
            case "sqlite" -> new SqliteDialect();
            default -> throw new IllegalArgumentException(
                "Unsupported SQL dialect: " + name
            );
        };
    }
}
~~~

Có thể xác minh cấu hình bằng JDBC DatabaseMetaData:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();
    String product = metadata.getDatabaseProductName();
    String version = metadata.getDatabaseProductVersion();

    // So khớp với cấu hình; từ chối khởi động nếu không tương thích.
}
~~~

Cấu hình là nguồn chọn dialect; metadata giúp phát hiện cấu hình sai hoặc driver không đúng.

## 6. Lớp thực thi JDBC dùng chung

### 6.1. RowMapper và SqlParameter

~~~java
@FunctionalInterface
public interface RowMapper<T> {
    T map(ResultSet resultSet) throws SQLException;
}

public record SqlParameter(Object value, int jdbcType) {}
~~~

Bind tham số:

~~~java
private void bind(
        PreparedStatement statement,
        List<SqlParameter> parameters) throws SQLException {

    for (int i = 0; i < parameters.size(); i++) {
        SqlParameter parameter = parameters.get(i);
        int index = i + 1;

        if (parameter.value() == null) {
            statement.setNull(index, parameter.jdbcType());
        } else {
            statement.setObject(
                index,
                parameter.value(),
                parameter.jdbcType()
            );
        }
    }
}
~~~

Với UUID, JSON, array, timestamp hoặc kiểu vendor-specific, setObject có thể cần driver hỗ trợ riêng. Có thể dùng ParameterBinder do dialect cung cấp. Không giả định mọi driver ánh xạ cùng một Java type giống nhau.

### 6.2. Query và mapping

~~~java
public <T> List<T> query(
        Connection connection,
        String sql,
        List<SqlParameter> parameters,
        RowMapper<T> mapper) throws SQLException {

    List<T> rows = new ArrayList<>();

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

        bind(statement, parameters);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                rows.add(mapper.map(resultSet));
            }
        }
    }

    return rows;
}
~~~

Trong mẫu này, caller sở hữu Connection và transaction; executor sở hữu PreparedStatement và ResultSet. Mapper chỉ đọc hàng hiện tại, không giữ ResultSet sau khi trả về.

Nếu executor tự mượn connection từ DataSource, phương thức đó phải tự đóng connection. Không trộn hai kiểu ownership.

### 6.3. Execute update

~~~java
public int update(
        Connection connection,
        String sql,
        List<SqlParameter> parameters) throws SQLException {

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {
        bind(statement, parameters);
        return statement.executeUpdate();
    }
}
~~~

Repository diễn giải update count theo contract: 0 có thể là không tìm thấy hoặc trạng thái không phù hợp; 1 có thể là thành công; lớn hơn 1 có thể vi phạm giả định khóa duy nhất.

### 6.4. Không trả ResultSet ra ngoài

ResultSet phụ thuộc Statement và Connection. Hãy map sang DTO/List khi tập vừa phải, hoặc dùng callback/stream có lifecycle rõ. Không giữ connection khi chờ HTTP response hoặc gọi dịch vụ bên ngoài.

## 7. Bind giá trị và whitelist identifier

Dấu hỏi trong PreparedStatement chỉ đại diện **giá trị**, không đại diện tên bảng/cột.

Không dùng:

~~~sql
SELECT ? FROM orders
ORDER BY ?
~~~

để bind tên cột. Nếu cần sort động, chọn fragment từ enum/whitelist:

~~~java
public enum OrderSort {
    NEWEST("ordered_at DESC, order_id DESC"),
    OLDEST("ordered_at ASC, order_id ASC"),
    STATUS("order_status ASC, order_id ASC");

    private final String sql;

    OrderSort(String sql) {
        this.sql = sql;
    }

    public String sql() {
        return sql;
    }
}
~~~

Chỉ fragment được định nghĩa trong code mới được nối vào SQL. Giá trị lọc vẫn bind bằng PreparedStatement.

### 7.1. Danh sách IN

Một placeholder không đại diện cho cả danh sách:

~~~sql
WHERE order_id IN (?)
~~~

Bind chuỗi "1,2,3" vẫn là một giá trị duy nhất. Hãy tạo đúng số placeholder và bind từng ID:

~~~java
String placeholders = ids.stream()
    .map(id -> "?")
    .collect(Collectors.joining(", "));

String sql = "SELECT order_id FROM orders WHERE order_id IN ("
    + placeholders + ")";
~~~

Xử lý danh sách rỗng trước khi tạo SQL; không sinh IN rỗng. Contract thường có thể định nghĩa list rỗng trả ngay danh sách rỗng mà không truy vấn DB.

Với danh sách rất lớn, cân nhắc temporary table, table-valued parameter của SQL Server, array parameter hoặc bulk loading theo dialect.

### 7.2. LIKE

Bind tham số LIKE vẫn ngăn SQL injection, nhưng % và _ còn mang ý nghĩa wildcard. Nếu cần tìm literal, escape wildcard theo quy tắc DBMS và dùng ESCAPE phù hợp.

## 8. Phân trang theo dialect

### 8.1. Hợp đồng

~~~java
public record PageRequest(int pageSize, long offset) {
    public PageRequest {
        if (pageSize < 1 || pageSize > 500) {
            throw new IllegalArgumentException("Invalid page size");
        }
        if (offset < 0) {
            throw new IllegalArgumentException("Invalid offset");
        }
    }
}
~~~

Hợp đồng phân trang cần thứ tự ổn định, page size hợp lệ và bind giá trị. Dialect thay cú pháp chứ không thay ý nghĩa.

### 8.2. PostgreSQL, MySQL và SQLite

~~~sql
SELECT order_id, order_status
FROM orders
WHERE customer_id = ?
ORDER BY ordered_at DESC, order_id DESC
LIMIT ? OFFSET ?
~~~

Việc bind LIMIT/OFFSET và kiểu tham số cần xác nhận theo driver/version. Nếu render số nguyên trực tiếp, chỉ dùng giá trị đã validate và do code kiểm soát.

### 8.3. SQL Server

~~~sql
SELECT order_id, order_status
FROM dbo.orders
WHERE customer_id = ?
ORDER BY ordered_at DESC, order_id DESC
OFFSET ? ROWS
FETCH NEXT ? ROWS ONLY
~~~

OFFSET/FETCH yêu cầu ORDER BY. Phiên bản cũ có thể cần ROW_NUMBER() hoặc TOP.

### 8.4. Oracle

Oracle 12c trở lên hỗ trợ:

~~~sql
SELECT order_id, order_status
FROM orders
WHERE customer_id = ?
ORDER BY ordered_at DESC, order_id DESC
OFFSET ? ROWS
FETCH NEXT ? ROWS ONLY
~~~

Oracle cũ có thể dùng ROWNUM hoặc ROW_NUMBER(). Hãy kiểm tra minimum version.

### 8.5. Keyset pagination

Offset lớn có thể khiến database phải bỏ qua nhiều hàng. Keyset dùng khóa cuối trang trước:

~~~sql
SELECT order_id, ordered_at, order_status
FROM orders
WHERE customer_id = ?
  AND (
      ordered_at < ?
      OR (ordered_at = ? AND order_id < ?)
  )
ORDER BY ordered_at DESC, order_id DESC
LIMIT ?
~~~

Điều kiện cursor phải khớp ORDER BY và có tie-breaker duy nhất. Nếu cột sort nullable, cần quy định vị trí NULL và điều kiện cursor tương ứng.

Test trên từng DBMS: page size 1, page cuối, tập rỗng, timestamp trùng, NULL ordering và insert/delete giữa hai request.

## 9. Upsert theo dialect

### 9.1. Định nghĩa contract

Trước khi viết upsert, xác định:

- Unique/business key;
- Cột được phép update;
- Cột phải giữ nguyên;
- Kết quả insert/update;
- Hành vi khi hai request cùng tạo key;
- Cách xử lý duplicate, deadlock và retry.

Không tạo một hàm upsert tổng quát cho mọi bảng mà không có spec rõ ràng.

### 9.2. PostgreSQL

~~~sql
INSERT INTO feature_flags (flag_key, is_enabled)
VALUES (?, ?)
ON CONFLICT (flag_key)
DO UPDATE SET is_enabled = EXCLUDED.is_enabled
~~~

Cần unique constraint/index phù hợp. EXCLUDED đại diện hàng được đề xuất insert.

### 9.3. MySQL

~~~sql
INSERT INTO feature_flags (flag_key, is_enabled)
VALUES (?, ?)
ON DUPLICATE KEY UPDATE
    is_enabled = VALUES(is_enabled)
~~~

VALUES(column) đã deprecated trong các phiên bản MySQL mới; alias của hàng mới được khuyến nghị ở các bản hỗ trợ. Dialect phải tuân theo minimum version của ứng dụng.

### 9.4. SQLite

~~~sql
INSERT INTO feature_flags (flag_key, is_enabled)
VALUES (?, ?)
ON CONFLICT(flag_key)
DO UPDATE SET is_enabled = excluded.is_enabled
~~~

Cần xác định minimum SQLite version hỗ trợ UPSERT.

### 9.5. SQL Server

MERGE là cú pháp riêng và cần kiểm thử theo version/workload. Một lựa chọn khác là UPDATE rồi INSERT trong transaction:

~~~sql
UPDATE dbo.feature_flags
SET is_enabled = ?
WHERE flag_key = ?;

-- Nếu không có hàng phù hợp:
INSERT INTO dbo.feature_flags(flag_key, is_enabled)
VALUES (?, ?);
~~~

Cách này cần xử lý race condition và unique violation. Unique constraint vẫn là lớp bảo vệ cuối. Không giả định update count 0 luôn đồng nghĩa bản ghi không tồn tại, vì driver/DBMS có thể báo số hàng khác nhau khi giá trị mới bằng giá trị cũ.

### 9.6. Oracle

~~~sql
MERGE INTO feature_flags target
USING (
    SELECT ? AS flag_key, ? AS is_enabled
    FROM dual
) source
ON (target.flag_key = source.flag_key)
WHEN MATCHED THEN
    UPDATE SET target.is_enabled = source.is_enabled
WHEN NOT MATCHED THEN
    INSERT (flag_key, is_enabled)
    VALUES (source.flag_key, source.is_enabled)
~~~

Đây là cú pháp Oracle; concurrency, unique constraint và output cần được kiểm thử trên version đích.

### 9.7. Test upsert cạnh tranh

Dùng hai connection/transaction cùng upsert một khóa mới. Kiểm tra số hàng cuối, unique constraint, transaction thắng/thua, lỗi được ánh xạ và retry có tạo duplicate hay không. Unit test render SQL không kiểm chứng được điều này.

## 10. Generated keys

Cùng một contract trả ID có thể dùng các cách khác nhau:

- JDBC getGeneratedKeys();
- PostgreSQL RETURNING;
- SQL Server OUTPUT INSERTED;
- Oracle sequence và RETURNING INTO;
- MySQL auto-increment;
- SQLite RETURNING ở phiên bản hỗ trợ hoặc cơ chế driver tương ứng.

JDBC generated keys:

~~~java
try (PreparedStatement statement =
         connection.prepareStatement(
             "INSERT INTO orders(customer_id, order_status) VALUES (?, ?)",
             Statement.RETURN_GENERATED_KEYS
         )) {

    statement.setLong(1, customerId);
    statement.setString(2, "NEW");
    statement.executeUpdate();

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Generated key was not returned");
        }
        long id = keys.getLong(1);
    }
}
~~~

PostgreSQL:

~~~sql
INSERT INTO orders(customer_id, order_status)
VALUES (?, ?)
RETURNING order_id, order_status
~~~

SQL Server:

~~~sql
INSERT INTO dbo.orders(customer_id, order_status)
OUTPUT INSERTED.order_id, INSERTED.order_status
VALUES (?, ?)
~~~

Oracle có thể dùng sequence NEXTVAL và RETURNING INTO/OUT parameter theo driver. Không dùng SELECT MAX(id) sau INSERT: transaction khác có thể tạo ID mới giữa hai câu lệnh.

Generated keys của batch và số lượng khóa trả về phụ thuộc driver; cần integration test.

## 11. Kiểu dữ liệu và hàm cần mapping theo dialect

| Khái niệm | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Boolean | BOOLEAN | TINYINT alias | BIT | NUMBER(1)/CHAR(1); BOOLEAN ở bản mới | INTEGER 0/1 |
| UUID | UUID | CHAR(36)/BINARY(16) | UNIQUEIDENTIFIER | RAW(16)/CHAR(36) | TEXT/BLOB |
| JSON | JSON/JSONB | JSON | FOR JSON, JSON functions | SQL/JSON | JSON functions tùy build/version |
| Empty string | Khác NULL | Khác NULL | Khác NULL | Character empty string được xem như NULL | Khác NULL |

Nếu dùng UUID binary, định nghĩa byte order và test round-trip. Nếu dùng Boolean nullable, phân biệt false và NULL. Nếu cần phân biệt empty string với NULL, Oracle VARCHAR2 không thể lưu cả hai trạng thái riêng.

Ngày giờ cũng cần contract rõ: DATE là ngày lịch; timestamp không timezone có thể là local date-time; timestamp có offset biểu diễn instant. Chọn LocalDate, LocalDateTime hoặc OffsetDateTime theo ngữ nghĩa, không chỉ theo tên cột.

Khác biệt giữa ||, +, CONCAT, CONCAT_WS và NULL có thể làm output khác nhau. Đặt biểu thức quan trọng trong dialect và kiểm thử với NULL, empty string, whitespace và Unicode.

## 12. Identifier, schema và naming

Tên bảng/cột không phải value nên không bind bằng dấu hỏi. Quy tắc quote khác nhau:

- PostgreSQL thường dùng dấu nháy kép;
- MySQL thường dùng backtick, hoặc ANSI_QUOTES theo cấu hình;
- SQL Server dùng ngoặc vuông hoặc dấu nháy kép theo QUOTED_IDENTIFIER;
- Oracle và SQLite dùng dấu nháy kép theo quy tắc tương ứng.

Tránh tên cột trùng keyword. Chọn naming convention ổn định; không trộn quoted và unquoted identifier tùy tiện.

Schema, catalog và database name không có cùng ý nghĩa ở mọi DBMS. Nếu schema/tenant name động, lấy từ cấu hình hoặc whitelist; không nối trực tiếp request vào SQL.

## 13. Transaction, isolation và lỗi

JDBC có transaction API chung:

~~~java
connection.setAutoCommit(false);
try {
    // Thực hiện các câu SQL cùng nghiệp vụ.
    connection.commit();
} catch (SQLException | RuntimeException e) {
    connection.rollback();
    throw e;
}
~~~

Nhưng DBMS khác nhau về isolation mặc định, lock behavior, deadlock, DDL transactionality và retryable errors.

Với deadlock/serialization failure:

- Nhận diện SQLState/vendor code theo driver;
- Rollback toàn transaction;
- Retry có giới hạn với backoff/jitter;
- Giữ transaction ngắn;
- Dùng idempotency key hoặc thao tác idempotent;
- Không retry syntax error, constraint error hoặc lỗi nghiệp vụ như thể lỗi tạm thời.

DDL có thể không rollback giống nhau giữa các DBMS. Migration cần được chạy thử trên đúng engine/version, database rỗng và database đang có dữ liệu.

Các cú pháp FOR UPDATE, NOWAIT, SKIP LOCKED và cách lấy khóa khác nhau. Nếu dùng queue worker hoặc locking, coi đó là capability riêng, không chỉ thay tên câu SQL.

## 14. Migration và version compatibility

Tổ chức migration tham khảo:

~~~text
db/migration/
  common/
    V001__create_core_tables.sql
  postgresql/
    V002__postgresql_indexes.sql
  mysql/
    V002__mysql_indexes.sql
  sqlserver/
    V002__sqlserver_objects.sql
  oracle/
    V002__oracle_sequences.sql
  sqlite/
    V002__sqlite_constraints.sql
~~~

Công cụ như Flyway/Liquibase có quy tắc chọn migration riêng; đây chỉ là cách phân chia ý tưởng. Không để hai migration cùng version chạy nhầm vào một database.

Ghi rõ minimum version và driver version cho mỗi hệ. Không dùng latest làm hợp đồng lâu dài. CI cần chạy cả phiên bản tối thiểu và phiên bản production dự kiến.

Khi đổi schema, có thể dùng expand-and-contract:

1. Expand: thêm cấu trúc tương thích code cũ.
2. Backfill: chuyển dữ liệu.
3. Switch: phát hành code đọc/ghi cấu trúc mới.
4. Validate: xác nhận dữ liệu và metrics.
5. Contract: bỏ cấu trúc cũ ở release sau.

Online DDL, lock và rollback phụ thuộc DBMS. Đo trên dữ liệu gần production.

## 15. Chiến lược kiểm thử từng phương ngữ

### 15.1. Các tầng test

| Tầng | Mục tiêu | Công cụ/đối tượng |
| --- | --- | --- |
| Unit domain | Quy tắc nghiệp vụ độc lập SQL | JUnit, object thuần |
| Unit dialect | SQL fragment, bind order, capability | JUnit |
| Repository contract | Cùng hành vi repository trên từng DBMS | Integration test thật |
| Migration | DDL, migration và schema drift | Database đúng version |
| Performance/concurrency | Query plan, lock, race và latency | DBMS thật, dữ liệu đại diện |

Mock Connection có ích cho nhánh điều khiển nhưng không tái hiện parser, optimizer, type conversion, constraint hoặc concurrency của DBMS.

### 15.2. Unit test SQL renderer

~~~java
@Test
void postgresPaginationUsesLimitOffset() {
    SqlDialect dialect = new PostgreSqlDialect();
    assertEquals("LIMIT ? OFFSET ?", dialect.paginationClause());
}

@Test
void sqlServerPaginationUsesOffsetFetch() {
    SqlDialect dialect = new SqlServerDialect();
    assertEquals(
        "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        dialect.paginationClause()
    );
}
~~~

Kiểm tra SQL fragment, thứ tự/số lượng placeholder, kiểu bind, whitelist identifier và unsupported capability. Đừng chỉ snapshot một chuỗi dài nếu có thể kiểm tra từng thành phần rõ ràng.

### 15.3. Repository contract test

Định nghĩa một bộ test hành vi chạy với từng DataSource:

~~~java
abstract class OrderRepositoryContractTest {
    protected abstract DataSource dataSource();
    protected OrderRepository repository;

    @BeforeEach
    void setUp() throws Exception {
        resetSchema(dataSource());
        repository = createRepository(dataSource());
    }

    @Test
    void returnsEmptyWhenOrderDoesNotExist() throws Exception {
        assertTrue(repository.findById(999999L).isEmpty());
    }

    @Test
    void findsOrderById() throws Exception {
        insertOrder(dataSource(), 1001L, 1L, "PENDING");
        Order order = repository.findById(1001L).orElseThrow();

        assertEquals(1001L, order.id());
        assertEquals(OrderStatus.PENDING, order.status());
    }
}
~~~

Mỗi DBMS có lớp cấu hình DataSource/migration riêng. Mẫu trên là cấu trúc minh họa; mỗi test phải dùng schema/database độc lập hoặc fixture reset an toàn khi chạy song song.

### 15.4. Database thật trong CI

Testcontainers có thể khởi tạo DBMS trong container; CI cũng có thể dùng managed database. Cần:

- Pin image và version;
- Chờ database ready trước migration;
- Dùng driver tương thích;
- Cleanup dữ liệu;
- Không dùng tag latest cho compatibility gate;
- Test đúng engine, không chỉ dùng H2 thay thế.

H2 hữu ích cho test nhanh nhưng không chứng minh SQL tương thích PostgreSQL, SQL Server, Oracle hoặc MySQL.

### 15.5. Ma trận CI

~~~text
               Unit   PostgreSQL   MySQL   SQL Server   Oracle   SQLite
Domain           X
Dialect          X
Repository               X           X         X          X        X
Migration                X           X         X          X        X
Concurrency              X           X         X          X
~~~

Có thể chạy một phần matrix trên pull request và toàn bộ vào nightly/release candidate. Mọi dialect được tuyên bố hỗ trợ phải được xác minh định kỳ; thay đổi dialect nào phải chạy contract test của dialect đó.

## 16. Bộ dữ liệu và trường hợp biên

Fixture nên có:

- Không hàng, một hàng và nhiều hàng;
- NULL, chuỗi rỗng, whitespace và Unicode;
- UUID hợp lệ/invalid và round-trip;
- Boolean TRUE/FALSE/NULL nếu nullable;
- Decimal ở biên precision/scale;
- Timestamp trùng và khác offset;
- Duplicate key, FK thiếu, CHECK fail;
- Giá trị sort trùng và sort nullable.

Transaction tests nên kiểm tra commit, rollback, savepoint, deadlock, timeout, concurrent update và upsert race.

Pagination tests cần page size 1, trang cuối, dữ liệu thay đổi giữa request, tie-breaker và không duplicate/skip theo contract.

Generated key/type tests cần insert đơn, batch, UUID mapping, Boolean NULL, BigDecimal, date/time và JSON serialization.

## 17. Tránh test phụ thuộc môi trường

- **Timezone:** cố định timezone/session hoặc so sánh theo UTC/offset contract.
- **Locale/collation:** test case, accent và Unicode trên DBMS thật.
- **Identifier casing:** dùng alias ổn định, không dựa vào driver tự đổi case.
- **Clock:** inject Clock và dùng thời điểm cố định.
- **UUID:** inject generator hoặc dùng UUID cố định trong test.
- **Concurrency:** dùng barrier/latch để tạo interleaving, không dùng sleep cố định.

Không phụ thuộc thứ tự hàng khi SELECT thiếu ORDER BY.

## 18. Migration và schema drift

Test migration từ database rỗng và từ schema phiên bản cũ. Kiểm tra:

- PK, UNIQUE, FK;
- Nullability, CHECK, DEFAULT;
- Precision/scale;
- Cascade behavior;
- Index và generated columns;
- Dữ liệu legacy và các trường hợp biên.

DDL text giữa các DBMS không cần giống nhau. So sánh **contract và hành vi**, không so sánh nguyên văn câu DDL.

Một số khác biệt vật lý có thể chấp nhận: PostgreSQL UUID so với MySQL BINARY(16), SQL Server BIT so với PostgreSQL BOOLEAN, Oracle sequence so với identity. Điều quan trọng là cùng semantics mà ứng dụng yêu cầu.

## 19. Performance test theo engine

SQL generation đúng không chứng minh query nhanh. Trên từng DBMS cần xem:

- Execution plan và index usage;
- Estimated/actual rows;
- Logical/physical reads;
- Lock waits và deadlocks;
- CPU và I/O;
- Latency p50/p95/p99;
- Thời gian chờ connection pool.

Dữ liệu test phải có phân bố gần thực tế: skew theo tenant, tỷ lệ NULL, cardinality khóa ngoại, kích thước text/JSON và tần suất ghi.

Index không portable tuyệt đối: partial/filtered index, expression index, included columns, clustered index, GIN/GiST và online build khác nhau. Đặt chúng trong migration riêng và đo query plan trên engine đích.

## 20. Chọn thư viện hay tự xây dialect?

| Lựa chọn | Phù hợp khi | Đánh đổi |
| --- | --- | --- |
| JDBC thuần + vài dialect | Ứng dụng nhỏ, ít DBMS, SQL có kiểm soát | Tự quản lý mapping/resource |
| jOOQ | SQL phức tạp, cần DSL/type-safe | Dependency, code generation/licensing theo edition |
| Spring JDBC | Ứng dụng Spring cần template và transaction integration | Phụ thuộc abstraction Spring |
| MyBatis | Muốn SQL tường minh và mapping linh hoạt | Mapper và dialect vẫn cần tổ chức |
| Hibernate/JPA | CRUD theo domain/entity | SQL generated và query đặc thù vẫn cần test |
| Query DSL khác | Cần dựng query có cấu trúc | Phải xác minh dialect coverage |

Thư viện không xóa khác biệt DBMS. Đánh giá minimum version, dialect coverage, generated SQL, transaction/resource lifecycle, migration integration, licensing và cách debug.

## 21. Các lỗi kiến trúc thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Ép một SQL cho mọi DBMS | Query khó tối ưu và khó đọc | Portable core + dialect fragment |
| Rải if databaseName | Logic phân tán, dễ lệch | Chọn dialect tại composition root |
| Interface khổng lồ chưa dùng | Abstraction phức tạp | Chỉ thêm capability có use case |
| supportsJson quá rộng | Hiểu sai tính năng engine | Capability theo use case |
| Bind tên cột bằng ? | Placeholder là value | Whitelist identifier |
| Nối input vào SQL | SQL injection | PreparedStatement |
| IN (?) với chuỗi CSV | Chỉ bind một value | Sinh placeholder hoặc table parameter |
| Không xử lý list rỗng | SQL sai hoặc semantics mơ hồ | Định nghĩa empty-list contract |
| Upsert thiếu unique key | Duplicate khi concurrent | Unique constraint + transaction |
| Dùng MERGE mà không test race | Hành vi cạnh tranh bất ngờ | Test engine/version |
| SELECT MAX(id) | Có thể lấy ID transaction khác | Generated keys/RETURNING/OUTPUT |
| Giả định UUID mapping giống nhau | Sai byte order | Binder/mapper theo dialect |
| Chỉ test H2 | Bỏ lọt khác biệt engine | Integration test thật |
| Test chỉ trên latest | Mất minimum-version compatibility | Pin và chạy minimum version |
| Không ORDER BY | Test flaky | Sort ổn định có tie-breaker |
| Retry mọi SQLException | Duplicate hoặc lặp lỗi vĩnh viễn | Error translation + idempotency |
| Chỉ kiểm tra SQL text | Bỏ qua semantics/performance | Contract + integration + plan |
| Domain biết vendor detail | Domain phụ thuộc DBMS | Giữ vendor detail trong persistence |

## 22. Lộ trình triển khai

1. Lập danh sách DBMS, version và driver được hỗ trợ.
2. Định nghĩa repository contract: cardinality, ordering, nullability, transaction và error.
3. Viết portable SQL trước, bind giá trị và alias rõ.
4. Tách pagination, upsert, generated key, UUID/Boolean/JSON và lock clause vào dialect.
5. Chọn DataSource, transaction manager và resource ownership.
6. Viết unit test cho renderer, bind order và whitelist.
7. Chạy repository contract trên database thật.
8. Chạy migration từ database rỗng và database cũ.
9. Kiểm tra concurrency, deadlock, timeout, rollback và retry.
10. Đo query plan và latency trên dữ liệu đại diện.
11. Ghi compatibility matrix và duy trì CI.
12. Triển khai schema theo expand-and-contract.

## 23. Bài tập thực hành có đáp án

### Bài 1 — Portable SQL

SELECT theo customer_id và ORDER BY order_id có cần dialect riêng không?

**Đáp án:** thường không nếu schema tương thích. Phần phân trang có thể cần dialect.

### Bài 2 — Pagination

Vì sao LIMIT/OFFSET không thể sao chép nguyên văn sang SQL Server?

**Đáp án:** SQL Server dùng ORDER BY ... OFFSET ... ROWS FETCH NEXT ... ROWS ONLY ở phiên bản hỗ trợ; bản cũ cần chiến lược khác.

### Bài 3 — Dialect selection

Nên kiểm tra tên DBMS trong từng repository hay inject một dialect được chọn lúc khởi động?

**Đáp án:** chọn và inject ở composition root; dùng metadata xác minh cấu hình.

### Bài 4 — Placeholder

Có thể bind tên cột bằng ORDER BY ? không?

**Đáp án:** không. Placeholder là value. Identifier phải lấy từ whitelist.

### Bài 5 — SQL injection

Trim input có làm cho nối chuỗi SQL an toàn không?

**Đáp án:** không. Dùng PreparedStatement bind giá trị.

### Bài 6 — IN list

Vì sao IN (?) với parameter "1,2,3" không tương đương ba placeholder?

**Đáp án:** driver bind một chuỗi. Sinh từng placeholder và bind từng ID, hoặc dùng array/table parameter.

### Bài 7 — Empty list

Repository nhận list ID rỗng nên làm gì?

**Đáp án:** định nghĩa contract; thường trả list rỗng ngay và không chạy SQL.

### Bài 8 — Upsert contract

Cần xác định gì trước khi triển khai upsert?

**Đáp án:** business key, cột update, cột giữ nguyên, race behavior, kết quả insert/update và lỗi cần xử lý.

### Bài 9 — PostgreSQL upsert

Cú pháp xử lý conflict trong INSERT?

**Đáp án:** ON CONFLICT (...) DO UPDATE hoặc DO NOTHING.

### Bài 10 — MySQL upsert

Cú pháp duplicate key của MySQL?

**Đáp án:** ON DUPLICATE KEY UPDATE. Theo dõi cú pháp alias theo version; VALUES(column) đã deprecated trong các bản mới.

### Bài 11 — SQL Server

MERGE có phải cú pháp portable không?

**Đáp án:** không. Đây là cú pháp riêng; cần test concurrency/version. Có thể dùng UPDATE + INSERT trong transaction với unique constraint và xử lý race.

### Bài 12 — Generated key

Vì sao SELECT MAX(id) sau INSERT không an toàn?

**Đáp án:** transaction khác có thể insert trước SELECT MAX. Dùng generated keys/RETURNING/OUTPUT/sequence.

### Bài 13 — UUID binary

MySQL BINARY(16) và PostgreSQL UUID có thể dùng chung mà không kiểm tra byte order không?

**Đáp án:** không. Dùng test vector và round-trip trên từng driver.

### Bài 14 — Boolean mapping

Vì sao cần binder/mapper Boolean theo dialect?

**Đáp án:** kiểu cột, literal, JDBC getter/setter và NULL semantics có thể khác.

### Bài 15 — Oracle empty string

Oracle VARCHAR2 có lưu riêng empty string và NULL không?

**Đáp án:** không. Empty character string được xem như NULL; cần đổi contract hoặc lưu trạng thái bổ sung.

### Bài 16 — Contract test

Unit test SQL string có chứng minh repository chạy trên SQL Server không?

**Đáp án:** không. Cần integration test trên SQL Server và driver tương ứng.

### Bài 17 — H2

Vì sao H2 không thay được test PostgreSQL/MySQL?

**Đáp án:** parser, kiểu dữ liệu, hàm, transaction và optimizer của H2 khác engine đích.

### Bài 18 — Minimum version

Vì sao CI cần chạy minimum DBMS version?

**Đáp án:** tính năng mới có thể không tồn tại ở bản cũ; chỉ chạy latest sẽ bỏ lọt lỗi tương thích.

### Bài 19 — Ordering

SELECT thiếu ORDER BY có bảo đảm hàng đầu tiên không?

**Đáp án:** không. SQL không đảm bảo thứ tự nếu thiếu ORDER BY.

### Bài 20 — Pagination tie

Hai đơn có cùng ordered_at. Cursor chỉ chứa ordered_at có đủ không?

**Đáp án:** không. Thêm khóa duy nhất như order_id vào sort và cursor predicate.

### Bài 21 — Transaction boundary

Hai repository cùng nghiệp vụ nhưng mỗi cái tự mở connection có cùng transaction không?

**Đáp án:** không. Cần cùng connection hoặc transaction context do transaction manager quản lý.

### Bài 22 — Retry

INSERT có thể đã commit nhưng phản hồi bị mất. Có nên retry mù?

**Đáp án:** không. Dùng idempotency key/unique constraint và cách xác định kết quả trước retry.

### Bài 23 — Migration

Có nên chạy DDL PostgreSQL nguyên văn trên mọi DBMS?

**Đáp án:** không nếu có kiểu/cú pháp riêng. Tách migration portable và migration theo dialect.

### Bài 24 — Unsupported capability

Dialect không hỗ trợ JSON aggregation nhưng repository yêu cầu thì sao?

**Đáp án:** báo unsupported rõ ràng hoặc chọn implementation thay thế có semantics được định nghĩa. Không âm thầm tạo SQL sai.

### Bài 25 — Upsert concurrency

Làm sao test hai request cùng upsert một business key?

**Đáp án:** hai connection/transaction độc lập, barrier đồng bộ, chạy trên DBMS thật; kiểm tra unique constraint, số hàng cuối và lỗi được ánh xạ.

### Bài 26 — UUID round-trip

Test nào chứng minh mapping UUID binary đúng?

**Đáp án:** ghi UUID cố định, đọc lại, chuyển về canonical text và so sánh; kiểm tra 16 byte nếu contract lưu binary.

### Bài 27 — Performance

Unit test renderer pass có chứng minh query dùng index tốt không?

**Đáp án:** không. Cần query plan và benchmark trên dữ liệu đại diện.

### Bài 28 — Vendor extension

Có nên cấm mọi SQL vendor-specific?

**Đáp án:** không nhất thiết. Dùng tính năng riêng khi có lợi ích rõ, encapsulate trong dialect/repository và kiểm thử riêng.

## 24. Checklist công bố hỗ trợ DBMS

1. DBMS version và driver version tối thiểu đã ghi rõ?
2. Dialect được chọn tập trung và xác minh bằng metadata?
3. Portable SQL tránh syntax vendor-specific?
4. Capability có implementation hoặc unsupported behavior rõ?
5. Mọi value được bind; identifier động có whitelist?
6. Boolean, UUID, decimal, date/time, JSON và NULL có contract?
7. Pagination có sort ổn định, tie-breaker và cursor đúng?
8. Upsert có unique key và test race?
9. Generated key được lấy đúng theo driver?
10. Transaction, isolation, rollback và DDL semantics đã thử?
11. SQLState/vendor code được ánh xạ có kiểm soát?
12. Retry có giới hạn và idempotency?
13. Connection/Statement/ResultSet có ownership và close rõ?
14. Migration từ database rỗng và cũ đều chạy?
15. Unit tests cho renderer và parameter order?
16. Repository contract tests trên DBMS thật?
17. CI chạy minimum và production version?
18. Edge cases NULL, empty string, Unicode và cardinality?
19. Concurrency, deadlock và upsert race?
20. Performance plan và latency trên dữ liệu đại diện?
21. Log có đủ thông tin nhưng không lộ bí mật?
22. Backup, recovery và migration operations đã thử?
23. Unsupported features được tài liệu hóa?
24. Chỉ công bố hỗ trợ sau khi test bắt buộc pass?

## 25. Tổng kết

Một lớp SQL dùng chung tốt giữ **hợp đồng nghiệp vụ chung** và cô lập phần khác biệt theo DBMS:

- Viết portable SQL cho truy vấn thông dụng;
- Dùng dialect/capability cho pagination, upsert, generated keys, JSON, UUID, Boolean và lock syntax;
- Chọn dialect ở composition root, xác minh với metadata;
- Bind mọi giá trị bằng PreparedStatement; whitelist identifier động;
- Quản lý Connection, Statement, ResultSet và transaction theo ownership rõ;
- Viết unit test cho SQL generation nhưng xác minh hành vi bằng integration tests trên DBMS/driver thật;
- Pin minimum version và chạy compatibility matrix trong CI;
- Kiểm thử NULL, empty string, ordering, concurrency, migration và performance theo từng engine.

**Nguyên tắc cốt lõi:** cùng một nghiệp vụ phải có cùng contract ở mọi DBMS được hỗ trợ; phần SQL khác nhau được đặt ở đúng dialect và được kiểm chứng trên chính engine/version đó. Một abstraction chỉ đáng dùng khi nó làm rõ ranh giới khác biệt, giữ SQL dễ đọc và phát hiện sớm khi một phương ngữ không đáp ứng yêu cầu.
