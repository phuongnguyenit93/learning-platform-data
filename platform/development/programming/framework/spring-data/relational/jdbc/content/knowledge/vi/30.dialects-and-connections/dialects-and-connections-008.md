# Kiểm chứng tính tương thích trên H2, PostgreSQL và MySQL

Spring Data JDBC hỗ trợ nhiều hệ quản trị quan hệ thông qua cơ chế **dialect**. H2, PostgreSQL và MySQL đều có dialect được hỗ trợ trực tiếp, nhưng điều đó không có nghĩa một ứng dụng chạy thành công trên H2 chắc chắn sẽ chạy giống hệt trên PostgreSQL hoặc MySQL.

Dialect giúp Spring Data JDBC xử lý những khác biệt SQL phổ biến như cách biểu diễn identifier, giới hạn kết quả, lấy generated key và một số khả năng đặc thù của database. Dialect không làm cho mọi kiểu dữ liệu, DDL, constraint, collation, transaction behavior hoặc câu SQL tùy chỉnh trở nên giống nhau.

Vì vậy, cần kiểm chứng trên chính hệ quản trị mà ứng dụng sẽ triển khai. H2 rất hữu ích cho kiểm thử nhanh và phản hồi sớm, còn PostgreSQL và MySQL nên được chạy trong integration test bằng database thật, thường thông qua Testcontainers.

Bài học trình bày cách Spring Data JDBC chọn dialect, những khác biệt dễ gây lỗi giữa H2, PostgreSQL và MySQL, cách tổ chức test theo từng database và quy trình xác nhận ứng dụng tương thích trước khi phát hành.

## 1. Tương thích database gồm những lớp nào?

Một ứng dụng Spring Data JDBC có thể chạy được trên nhiều database nếu các lớp sau tương thích:

1. **JDBC driver:** driver phải kết nối được, cung cấp metadata và ánh xạ kiểu dữ liệu đúng.
2. **Dialect:** Spring Data JDBC phải chọn đúng dialect để sinh SQL phù hợp.
3. **Schema và migration:** DDL, kiểu cột, identity, sequence, index và constraint phải hợp lệ trên database đích.
4. **Mapping:** tên bảng/cột, quoting, converter, embedded object và collection phải ánh xạ đúng.
5. **Query:** derived query và dynamic Query cần hoạt động; SQL tùy chỉnh phải phù hợp cú pháp từng vendor.
6. **Transaction và concurrency:** rollback, isolation, generated key và optimistic locking phải đáp ứng nghiệp vụ.
7. **Dữ liệu thực tế:** collation, timezone, precision, nullability và hành vi của driver phải phù hợp.
8. **Vận hành:** cấu hình connection pool, timeout, encoding, SQL mode và phiên bản server phải được xác nhận.

Có thể hình dung:

~~~text
Spring Data JDBC application
          |
          v
     JDBC driver
          |
          v
    JDBC metadata
          |
          v
   DialectResolver
          |
          v
  H2 / PostgreSQL / MySQL
          |
          v
  SQL + schema + transaction
          |
          v
  Kết quả trên database thật
~~~

Một bài test chỉ kiểm tra repository save/load trên H2 mới xác nhận được một phần của chuỗi này. Nó chưa chứng minh migration, SQL tùy chỉnh, kiểu dữ liệu hoặc concurrency hoạt động giống trên database production.

## 2. Spring Data JDBC sử dụng dialect như thế nào?

Dialect là thành phần trừu tượng hóa các hành vi SQL phụ thuộc database hoặc JDBC driver. Spring Data JDBC có các implementation riêng cho H2, PostgreSQL và MySQL, trong đó các lớp JDBC dialect tương ứng nằm trong package:

~~~java
org.springframework.data.jdbc.core.dialect
~~~

Một số implementation:

| Database | JDBC dialect |
| --- | --- |
| H2 | §JdbcH2Dialect§ |
| PostgreSQL | §JdbcPostgresDialect§ |
| MySQL | §JdbcMySqlDialect§ |

Tên implementation có thể thay đổi theo phiên bản Spring Data Relational; hãy đối chiếu API của phiên bản dự án đang dùng.

### 2.1. Dialect được tự động phát hiện

Trong cấu hình thông thường, §AbstractJdbcConfiguration§ tạo bean §JdbcDialect§ bằng cách xem thông tin từ §NamedParameterJdbcOperations§. §DialectResolver§ lấy JDBC connection và kiểm tra metadata do driver cung cấp.

Với Spring Boot, khi dùng §spring-boot-starter-data-jdbc§ và cấu hình §DataSource§, auto-configuration thiết lập hạ tầng Spring Data JDBC và dialect phù hợp.

Ví dụ cấu hình PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_app
spring.datasource.password=secret
~~~

Ví dụ cấu hình MySQL:

~~~properties
spring.datasource.url=jdbc:mysql://localhost:3306/shop
spring.datasource.username=shop_app
spring.datasource.password=secret
~~~

Ví dụ cấu hình H2:

~~~properties
spring.datasource.url=jdbc:h2:mem:shop;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
~~~

Ứng dụng không cần tự chọn dialect bằng một chuỗi tên database trong code. Hãy để Spring Data JDBC phát hiện từ connection metadata trong cấu hình thông thường.

### 2.2. Kiểm tra database metadata

Khi cần điều tra môi trường, có thể đọc metadata từ JDBC:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import javax.sql.DataSource;

import org.springframework.stereotype.Component;

@Component
public class DatabaseMetadataLogger {

    public DatabaseMetadataLogger(DataSource dataSource)
            throws Exception {

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();

            System.out.println(
                    "Database: " + metadata.getDatabaseProductName()
            );
            System.out.println(
                    "Database version: " + metadata.getDatabaseProductVersion()
            );
            System.out.println(
                    "Driver: " + metadata.getDriverName()
            );
            System.out.println(
                    "Driver version: " + metadata.getDriverVersion()
            );
        }
    }
}
~~~

Ví dụ trên minh họa cách xem database và driver thực tế mà ứng dụng đang kết nối. Trong ứng dụng production, nên đưa thông tin này vào startup diagnostics hoặc health/observability phù hợp, thay vì tạo kết nối trong constructor bean.

Nếu cần kiểm tra dialect đã được cấu hình, có thể inject bean §JdbcDialect§ trong một integration test hoặc cấu hình chẩn đoán. Không nên dùng tên class dialect như một điều kiện nghiệp vụ trong service.

### 2.3. Khi nào phải tự cấu hình dialect?

Thông thường không cần. Chỉ can thiệp khi:

- Database hoặc JDBC driver không được resolver nhận diện.
- Ứng dụng dùng database tương thích một phần với vendor khác nhưng metadata không phù hợp.
- Có implementation dialect tùy chỉnh.
- Cần cấu hình đặc biệt theo môi trường hoặc yêu cầu AOT.

§AbstractJdbcConfiguration§ cho phép tùy chỉnh §jdbcDialect(NamedParameterJdbcOperations)§. Với database chưa được hỗ trợ, ứng dụng có thể cần implementation §JdbcDialect§ riêng và provider để resolver phát hiện.

Không nên ép một dialect chỉ vì database có chế độ compatibility mode. Compatibility mode của H2 không biến H2 thành PostgreSQL hoặc MySQL thật.

## 3. H2, PostgreSQL và MySQL được hỗ trợ nhưng không đồng nhất

Spring Data JDBC có hỗ trợ dialect trực tiếp cho cả ba database. Điều đó có nghĩa framework có thể điều chỉnh những khác biệt SQL mà dialect biết. Nó không có nghĩa database có cùng semantics.

| Khía cạnh | H2 | PostgreSQL | MySQL |
| --- | --- | --- | --- |
| Vai trò thường gặp | Database nhúng, test nhanh | Database production phổ biến | Database production phổ biến |
| JDBC driver | H2 JDBC | PostgreSQL JDBC | MySQL Connector/J |
| Identity | Hỗ trợ identity và sequence | Identity và sequence | Thường dùng AUTO_INCREMENT |
| Quoting identifier | Dùng quy tắc identifier của H2 | Identifier không quote được fold về lowercase; quoted identifier phân biệt hoa/thường | Thường dùng backtick; case table name còn phụ thuộc hệ điều hành và cấu hình |
| Boolean | Có kiểu BOOLEAN | Có kiểu BOOLEAN | BOOLEAN là alias của TINYINT(1) |
| Array | Có hỗ trợ array | Có kiểu array riêng | Không có kiểu SQL array tổng quát tương đương PostgreSQL |
| JSON | Có kiểu JSON | JSON và JSONB | Có kiểu JSON |
| Timezone | Có kiểu thời gian với timezone | TIMESTAMP WITH TIME ZONE lưu instant theo semantics PostgreSQL | TIMESTAMP chịu ảnh hưởng session timezone; DATETIME không lưu timezone |
| Collation | Phụ thuộc cấu hình/collation | Mặc định so sánh chuỗi có phân biệt hoa/thường trong nhiều trường hợp | Collation mặc định thường có thể không phân biệt hoa/thường |
| Upsert | Cú pháp và semantics riêng | ON CONFLICT | ON DUPLICATE KEY UPDATE |
| Transaction/DDL | Có hành vi riêng của H2 | PostgreSQL hỗ trợ transactional DDL trong nhiều trường hợp | Nhiều DDL có implicit commit |
| Locking | Khác với database server production | MVCC và row-level lock | Thường dùng InnoDB với MVCC và row-level lock |

Bảng này là định hướng các điểm cần kiểm thử, không phải bảng thay thế tài liệu từng phiên bản database. Phiên bản server, driver, SQL mode, collation và cấu hình có thể làm thay đổi hành vi.

## 4. Những khác biệt dễ làm test H2 pass nhưng production fail

### 4.1. Kiểu dữ liệu

Các database có thể dùng tên kiểu giống nhau nhưng semantics, precision hoặc cách driver chuyển đổi khác nhau.

Ví dụ:

- BOOLEAN trong PostgreSQL là kiểu boolean thực.
- MySQL biểu diễn BOOLEAN như alias của TINYINT(1).
- NUMERIC/DECIMAL có precision và scale cần khai báo rõ.
- TIMESTAMP, DATETIME, TIMESTAMP WITH TIME ZONE không có cùng semantics.
- JSON, JSONB và kiểu JSON của MySQL khác nhau về operator, index và cách bind parameter.
- Array column không được hỗ trợ đồng nhất; PostgreSQL có kiểu array native, trong khi MySQL không có kiểu SQL array tổng quát tương tự.

Không nên chỉ kiểm tra rằng một giá trị được ghi rồi đọc lại thành công trên H2. Hãy kiểm tra giá trị ở database production, đặc biệt với số tiền, thời gian, JSON, UUID và dữ liệu nhị phân.

Ví dụ schema tiền tệ:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Kiểm thử cần xác nhận:

- Giá trị có nhiều hơn hai chữ số thập phân được xử lý theo quy tắc nào.
- Giá trị vượt precision có bị từ chối hay làm tròn.
- Driver trả về §BigDecimal§ với scale như mong đợi.
- Dữ liệu cũ được migration sang schema mới mà không mất độ chính xác.

### 4.2. Date/time và timezone

Một ứng dụng có thể lưu §Instant§, §LocalDateTime§, §OffsetDateTime§ hoặc §LocalDate§ tùy ngữ nghĩa.

Không được xem tất cả các kiểu này là tương đương:

| Java type | Ý nghĩa |
| --- | --- |
| §Instant§ | Một thời điểm tuyệt đối trên timeline UTC. |
| §LocalDateTime§ | Ngày và giờ địa phương, không có timezone/offset. |
| §OffsetDateTime§ | Ngày giờ cùng offset. |
| §LocalDate§ | Ngày lịch, không có giờ. |

PostgreSQL có semantics riêng cho §timestamp with time zone§; MySQL phân biệt §TIMESTAMP§ và §DATETIME§, trong đó session timezone có thể ảnh hưởng cách đọc/ghi §TIMESTAMP§. H2 có thể chấp nhận kiểu và phép chuyển đổi khác.

Để kiểm chứng:

1. Chọn một timezone chính sách, thường lưu instant theo UTC.
2. Cấu hình JDBC driver và session timezone phù hợp.
3. Ghi thời điểm có offset khác UTC.
4. Đọc lại trên database đích.
5. Kiểm tra cùng một instant được giữ nguyên.
6. Kiểm tra ngày lịch không bị dịch sang ngày trước/sau khi chuyển timezone.

Ví dụ test:

~~~java
@Test
void preservesInstantAcrossDatabaseRoundTrip() {
    Instant expected = Instant.parse("2026-11-13T08:30:00Z");

    Event event = repository.save(
            new Event(null, "CREATED", expected)
    );

    Event loaded = repository.findById(event.id())
            .orElseThrow();

    assertEquals(expected, loaded.occurredAt());
}
~~~

Test này cần chạy trên từng database được hỗ trợ, không chỉ H2.

### 4.3. Identifier, quoting và chữ hoa/chữ thường

Spring Data Relational mặc định dùng quoted identifier cho tên bảng/cột được suy ra từ mapping. Có thể tùy chỉnh hành vi qua mapping context, nhưng không nên đổi chỉ để làm một test database pass.

PostgreSQL chuyển identifier không quote về lowercase. Identifier đã quote giữ nguyên case và trở nên case-sensitive. MySQL thường dùng backtick cho identifier và việc so sánh tên bảng còn phụ thuộc hệ điều hành, filesystem và cấu hình server. H2 có quy tắc riêng.

Tên như §Order§, §User§, §Group§, §Rank§ có thể trùng reserved keyword trên một hoặc nhiều database.

Khuyến nghị:

- Dùng tên bảng/cột rõ ràng, tránh reserved keyword.
- Không dựa vào case của tên identifier.
- Dùng §@Table§ và §@Column§ khi cần tên ổn định.
- Kiểm thử schema migration trên cả ba database.
- Không viết SQL tùy chỉnh giả định mọi vendor dùng cùng quote character.

Ví dụ mapping:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,

        @Column("order_status")
        String status
) {
}
~~~

Tránh đặt bảng là §order§ rồi trông chờ mọi database xử lý giống nhau.

### 4.4. Identity, sequence và generated key

Các database không có cùng chiến lược sinh ID:

- H2 hỗ trợ identity và sequence.
- PostgreSQL hỗ trợ identity và sequence.
- MySQL thường dùng §AUTO_INCREMENT§.

Spring Data JDBC và dialect hỗ trợ lấy generated key theo khả năng của driver. Tuy nhiên, DDL migration và cách cấu hình ID vẫn cần phù hợp database đích.

Ví dụ entity:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name
) {
}
~~~

Test cần xác nhận:

1. Insert không cung cấp ID.
2. Database tạo ID.
3. Repository trả về aggregate có ID đã được gán.
4. Có thể đọc lại bằng ID đó.
5. ID không bị mất hoặc sai khi insert nhiều bản ghi.
6. Cách tạo ID khi batch insert phù hợp với database/driver nếu ứng dụng dùng batch.

Nếu dùng sequence riêng với §@Sequence§, kiểm tra sequence tồn tại sau migration và quyền truy cập sequence của database user.

### 4.5. Generated SQL và pagination

Dialect giúp Spring Data JDBC tạo SQL tương ứng cho các thao tác phổ biến, nhưng SQL tùy chỉnh vẫn thuộc trách nhiệm của ứng dụng.

Ví dụ:

~~~java
@Query("""
        SELECT id, name, price
        FROM products
        WHERE status = :status
        ORDER BY created_at DESC
        """)
List<ProductSummary> findByStatus(String status);
~~~

SQL trên có thể chạy trên cả ba database nếu schema và kiểu dữ liệu tương thích. Nhưng nếu thêm function, JSON operator, upsert, returning clause hoặc cú pháp vendor-specific, khả năng tương thích sẽ thay đổi.

Với dynamic §Query§, dùng §Sort§, §limit§ và §offset§ để framework sinh phần SQL theo dialect. Với string-based §@Query§, hãy viết và kiểm thử SQL trên từng database đích.

### 4.6. Upsert và native SQL

PostgreSQL, MySQL và H2 có các cú pháp upsert khác nhau. Ví dụ:

~~~sql
-- PostgreSQL
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-01', 10)
ON CONFLICT (sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

~~~sql
-- MySQL
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-01', 10)
ON DUPLICATE KEY UPDATE quantity = VALUES(quantity);
~~~

Cú pháp MySQL có thể thay đổi/deprecate một số cách tham chiếu giá trị trong các phiên bản mới; hãy dùng cú pháp phù hợp phiên bản MySQL mục tiêu.

Không đưa một câu SQL native như trên vào repository rồi giả định nó chạy trên H2 và PostgreSQL/MySQL cùng lúc. Nếu cần hỗ trợ nhiều database:

- Dùng API persistence portable nếu nó đáp ứng use case.
- Tách SQL theo database/dialect khi thực sự cần.
- Dùng repository fragment hoặc adapter riêng cho từng vendor.
- Chạy test trên tất cả database được hỗ trợ.
- Không làm phức tạp domain service bằng các nhánh kiểm tra tên database.

### 4.7. Collation và so sánh chuỗi

Một truy vấn tìm kiếm có thể trả kết quả khác nhau do collation:

~~~sql
SELECT id, email
FROM customers
WHERE email = 'AN@example.com';
~~~

Một database có thể so sánh không phân biệt hoa/thường theo collation mặc định; database khác có thể phân biệt. Kết quả truy vấn và unique constraint trên chuỗi cũng có thể khác.

Đối với email hoặc mã định danh cần so sánh không phân biệt hoa/thường:

- Chuẩn hóa dữ liệu khi ghi, ví dụ lowercase theo quy tắc domain.
- Xác định rõ collation hoặc kiểu so sánh cần dùng.
- Tạo unique constraint/index phù hợp.
- Test các trường hợp §AN@example.com§ và §an@example.com§.
- Không dựa vào collation mặc định của H2.

### 4.8. Constraint và transaction behavior

H2 có thể không tái hiện chính xác:

- Thời điểm database kiểm tra constraint.
- Hành vi DDL trong transaction.
- Locking và deadlock.
- Isolation level mặc định.
- Cách xử lý concurrent update.
- Cascade delete và foreign key.
- Các lỗi cụ thể do driver trả về.

MySQL có thể thực hiện implicit commit với nhiều câu lệnh DDL. PostgreSQL hỗ trợ transactional DDL rộng hơn. Do đó, một migration chạy trong transaction trên H2 chưa chắc có cùng semantics trên MySQL.

Các test rollback, optimistic locking, unique constraint và migration cần chạy trên database production target.

## 5. H2 compatibility mode có thay thế được PostgreSQL/MySQL không?

H2 hỗ trợ các compatibility mode nhằm mô phỏng một số hành vi của database khác, ví dụ:

~~~properties
spring.datasource.url=jdbc:h2:mem:shop;MODE=PostgreSQL;DB_CLOSE_DELAY=-1
~~~

Hoặc:

~~~properties
spring.datasource.url=jdbc:h2:mem:shop;MODE=MySQL;DB_CLOSE_DELAY=-1
~~~

Compatibility mode có thể hữu ích khi:

- Phát hiện một số cú pháp SQL không portable.
- Hỗ trợ migration test nhanh.
- Giảm khác biệt trong một số quy tắc parser hoặc function.
- Duy trì test cũ trong giai đoạn chuyển đổi.

Nhưng nó không thay thế database gốc. H2 vẫn là H2:

- JDBC metadata vẫn mô tả H2.
- Spring Data JDBC vẫn nhận diện H2 dialect.
- Driver vẫn là H2 driver.
- Kiểu dữ liệu, collation, locking, transaction và optimizer vẫn có khác biệt.
- Compatibility mode không mô phỏng toàn bộ behavior của server PostgreSQL/MySQL.

Không nên xem test pass trên §MODE=PostgreSQL§ là bằng chứng tương thích PostgreSQL. Hãy dùng PostgreSQL thật trong Testcontainers để xác nhận.

## 6. Chiến lược kiểm thử theo nhiều tầng

Một chiến lược thực tế kết hợp test nhanh với test trên database thật.

| Tầng | Database | Mục tiêu | Tốc độ |
| --- | --- | --- | --- |
| Unit test | Không cần database | Domain logic, validation, converter thuần Java | Nhanh |
| Repository smoke test | H2 | Mapping cơ bản, CRUD, phản hồi nhanh | Nhanh |
| Integration test | PostgreSQL Testcontainer | Migration, dialect, SQL, transaction, driver và semantics production | Trung bình |
| Integration test | MySQL Testcontainer | Xác nhận riêng hành vi MySQL và Connector/J | Trung bình |
| Staging verification | Database cùng loại/phiên bản production | Kiểm chứng cấu hình, workload và migration thực tế | Chậm hơn |

Không nhất thiết mọi unit test phải chạy ba lần. Hãy dùng một bộ integration test contract chung để xác nhận những behavior persistence quan trọng trên từng database.

### 6.1. Unit test không phụ thuộc database

Các hành vi domain nên được kiểm thử không cần Spring hoặc JDBC:

~~~java
class InventoryItemTest {

    @Test
    void rejectsReservationGreaterThanAvailableQuantity() {
        InventoryItem item = new InventoryItem(
                1L,
                "SKU-01",
                3,
                1L
        );

        assertThrows(
                InsufficientStockException.class,
                () -> item.reserve(4)
        );
    }
}
~~~

Unit test xác nhận quy tắc nghiệp vụ. Nó không kiểm tra dialect, SQL hoặc driver.

### 6.2. H2 cho phản hồi nhanh

H2 có thể dùng cho một số test repository đơn giản:

~~~properties
spring.datasource.url=jdbc:h2:mem:shop_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
~~~

Hãy giữ các test H2 cho mục đích phù hợp:

- Kiểm tra context và repository khởi tạo.
- CRUD cơ bản.
- Mapping đơn giản.
- Converter thuần.
- Derived query portable.
- Feedback nhanh trong quá trình phát triển.

Đừng chỉ dựa vào H2 cho migration production, SQL tùy chỉnh hoặc concurrency semantics.

## 7. Kiểm thử PostgreSQL bằng Testcontainers

Testcontainers tạo một PostgreSQL server dùng tạm trong Docker. Integration test kết nối đến database thật với JDBC driver PostgreSQL.

### 7.1. Dependencies

Ví dụ Maven dependencies (version nên được quản lý thống nhất bằng BOM của dự án):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Dùng Testcontainers BOM để các module có version tương thích. Phiên bản artifact có thể thay đổi theo major release của Testcontainers; hãy theo dependency guide của phiên bản đang dùng.

### 7.2. Integration test với @DynamicPropertySource

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class PostgreSqlRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("shop")
                    .withUsername("shop")
                    .withPassword("shop");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    CustomerRepository repository;

    @Test
    void savesAndLoadsCustomer() {
        Customer saved = repository.save(
                new Customer(null, "Nguyễn An")
        );

        Customer loaded = repository.findById(saved.id())
                .orElseThrow();

        assertEquals("Nguyễn An", loaded.name());
    }
}
~~~

Trong ví dụ, tag §postgres:16-alpine§ là phiên bản server được chọn rõ ràng cho test. Hãy dùng cùng major/minor hoặc image digest phù hợp với môi trường production cần kiểm chứng.

§@DynamicPropertySource§ đưa JDBC URL, username và password từ container vào Spring Environment trước khi context được khởi tạo.

### 7.3. Chú ý vòng đời container và Spring context cache

JUnit Testcontainers extension quản lý vòng đời container theo test class hoặc test method. Spring TestContext có thể cache ApplicationContext và dùng lại sau khi test class đã kết thúc. Nếu context còn giữ bean kết nối tới container đã bị dừng, test class sau có thể thất bại.

Với bộ test Spring Boot lớn, cân nhắc:

- Quản lý container như Spring bean để vòng đời container đi cùng context.
- Dùng cấu hình container dùng chung được import cho các test.
- Tránh để context cache giữ connection tới container đã dừng.
- Dùng §@DirtiesContext§ có chủ đích khi cấu hình test yêu cầu đóng context.
- Không tạo quá nhiều container không cần thiết cho từng method.

Spring Boot cũng hỗ trợ service connection qua §@ServiceConnection§ khi có module §spring-boot-testcontainers§. Đây là lựa chọn khác với §@DynamicPropertySource§; không cần dùng cả hai cho cùng một datasource nếu không có lý do cụ thể.

## 8. Kiểm thử MySQL bằng Testcontainers

MySQL cần được kiểm thử riêng vì driver, DDL, collation và một số semantics khác PostgreSQL.

### 8.1. Dependencies

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mysql</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Hãy dùng version MySQL Connector/J phù hợp với server MySQL và Spring version của dự án.

### 8.2. Integration test với MySQLContainer

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class MySqlRepositoryIntegrationTest {

    @Container
    static final MySQLContainer<?> mysql =
            new MySQLContainer<>("mysql:8.4")
                    .withDatabaseName("shop")
                    .withUsername("shop")
                    .withPassword("shop");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }

    @Autowired
    CustomerRepository repository;

    @Test
    void savesAndLoadsCustomer() {
        Customer saved = repository.save(
                new Customer(null, "Nguyễn An")
        );

        Customer loaded = repository.findById(saved.id())
                .orElseThrow();

        assertEquals("Nguyễn An", loaded.name());
    }
}
~~~

Chọn version image đúng với MySQL production. Nếu production sử dụng MySQL 8.0, test MySQL 8.4 không tự động chứng minh tương thích ngược hoặc tương thích đầy đủ với 8.0.

Nếu ứng dụng dùng MariaDB, hãy kiểm thử MariaDB riêng. MySQL và MariaDB có nguồn gốc gần nhau nhưng không phải cùng một sản phẩm; driver metadata và dialect có thể khác.

## 9. Dùng chung contract test cho nhiều database

Để tránh viết lại cùng một test logic cho H2, PostgreSQL và MySQL, có thể tách bộ kiểm thử repository thành contract test.

Một contract test định nghĩa các behavior bắt buộc:

- Insert aggregate.
- Đọc aggregate.
- Update aggregate.
- Delete aggregate.
- Lưu và đọc collection con.
- Kiểm tra optimistic locking.
- Kiểm tra query/sort/pagination.
- Kiểm tra transaction rollback.
- Kiểm tra converter và kiểu dữ liệu quan trọng.

Ví dụ một abstract contract:

~~~java
abstract class CustomerRepositoryContract {

    protected abstract CustomerRepository repository();

    @Test
    void persistsCustomer() {
        Customer saved = repository().save(
                new Customer(null, "Nguyễn An")
        );

        Customer loaded = repository()
                .findById(saved.id())
                .orElseThrow();

        assertEquals("Nguyễn An", loaded.name());
    }
}
~~~

Test class cho từng database kế thừa contract và cung cấp repository được cấu hình bằng database tương ứng:

~~~java
@SpringBootTest
class PostgreSqlCustomerRepositoryTest
        extends CustomerRepositoryContract {

    @Autowired
    CustomerRepository customerRepository;

    @Override
    protected CustomerRepository repository() {
        return customerRepository;
    }
}
~~~

~~~java
@SpringBootTest
class MySqlCustomerRepositoryTest
        extends CustomerRepositoryContract {

    @Autowired
    CustomerRepository customerRepository;

    @Override
    protected CustomerRepository repository() {
        return customerRepository;
    }
}
~~~

Đây là cấu trúc minh họa. Trong dự án thực tế, cấu hình container có thể được đặt trong các test configuration riêng hoặc base class dùng chung. Đảm bảo mỗi test class thực sự kết nối tới database mong muốn, không vô tình dùng H2 từ test profile mặc định.

Không ép mọi behavior thành contract chung nếu behavior đó phụ thuộc vendor. Ví dụ PostgreSQL JSONB query và MySQL JSON query có thể cần test riêng.

## 10. Những test nên chạy trên cả PostgreSQL và MySQL

Một bộ test compatibility có thể được chia theo nhóm.

### 10.1. Dialect và khởi tạo context

Kiểm tra:

- ApplicationContext khởi tạo thành công.
- §DataSource§ kết nối đúng database.
- Dialect được resolver chọn đúng.
- Repository proxy được tạo.
- Generated SQL chạy được.
- Driver metadata cho đúng product name/version.

Nếu context không khởi tạo được, kiểm tra trước hết JDBC URL, driver, credentials, network và database startup logs.

### 10.2. Mapping và CRUD

Kiểm tra:

- §@Table§, §@Column§, §@Id§.
- Naming strategy.
- Quoted identifiers.
- Generated IDs.
- Embedded object.
- One-to-one và collection mapping.
- Null/default values.
- Custom converters.
- §@Version§.

Đặc biệt kiểm tra các bảng có tên hoặc cột dễ trùng reserved word và mapping có chữ hoa/chữ thường.

### 10.3. Migration và schema

Chạy Flyway hoặc Liquibase trên database thật:

- Tạo schema mới từ đầu.
- Upgrade từ phiên bản schema cũ.
- Tạo index và unique constraint.
- Tạo foreign key và cascade rule.
- Kiểm tra identity/sequence.
- Kiểm tra default value.
- Kiểm tra precision/scale.
- Kiểm tra migration có DDL cần vendor-specific hay không.

Không chỉ chạy §schema.sql§ đơn giản trong test rồi bỏ qua migration thật của production.

### 10.4. Query và SQL tùy chỉnh

Kiểm tra:

- Derived query methods.
- Criteria và dynamic §Query§.
- Sort và pagination.
- Projection và DTO.
- Custom §@Query§.
- Native SQL.
- Query có join hoặc aggregate expression.
- SQL sử dụng JSON, array hoặc function riêng.

Mỗi câu SQL native cần có test trên database vendor tương ứng.

### 10.5. Transaction và concurrency

Kiểm tra:

- Nhiều repository trong cùng transaction.
- Rollback khi bước sau thất bại.
- Optimistic locking với §@Version§.
- Hai transaction cập nhật cùng aggregate.
- Unique constraint dưới concurrent insert.
- Lock timeout và deadlock nếu nghiệp vụ có liên quan.
- Isolation level cần thiết.

H2 không phải bằng chứng đủ cho behavior concurrency trên PostgreSQL/MySQL.

### 10.6. Kiểu dữ liệu và biên giá trị

Kiểm tra:

- §BigDecimal§ ở precision/scale tối đa.
- Timestamp gần ranh giới ngày và timezone.
- Unicode và ký tự nhiều byte.
- Empty string và NULL.
- Boolean.
- Enum.
- UUID.
- JSON hoặc binary nếu dùng.
- Giá trị rất lớn hoặc rất nhỏ.
- Chuỗi có dấu, ký tự escape và ký tự đặc biệt.

## 11. Kiểm thử migration trên từng database

Migration là một trong những nguyên nhân phổ biến khiến ứng dụng pass test H2 nhưng fail khi triển khai.

Ví dụ migration tạo bảng:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Câu lệnh này không nhất thiết portable nguyên vẹn giữa mọi database và phiên bản. Cần kiểm tra:

- Identity syntax.
- Sequence behavior.
- Kiểu timestamp.
- Cú pháp index.
- Cú pháp constraint.
- Default expressions.
- Function và operator.
- DDL transaction behavior.

### 11.1. Dùng migration tool như nguồn schema chính

Nếu ứng dụng dùng Flyway, hãy chạy migration thực tế trong integration test:

~~~properties
spring.flyway.enabled=true
spring.sql.init.mode=never
~~~

Không nên đồng thời duy trì hai nguồn schema không đồng bộ, chẳng hạn Flyway cho production nhưng một §schema.sql§ khác cho H2 test.

Nếu cần schema riêng cho từng database, có thể dùng Flyway locations theo vendor:

~~~properties
spring.flyway.locations=classpath:db/migration/common,classpath:db/migration/postgresql
~~~

Với MySQL, cấu hình location tương ứng:

~~~properties
spring.flyway.locations=classpath:db/migration/common,classpath:db/migration/mysql
~~~

Cần bảo đảm chỉ migration đúng vendor được chạy trong từng profile. Migration chung nên chứa phần portable; migration vendor-specific cần được đặt tên và quản lý rõ ràng.

### 11.2. Kiểm thử upgrade, không chỉ clean install

Một database trống chỉ kiểm tra chuỗi migration từ đầu. Production thường đã có dữ liệu và schema cũ.

Hãy tạo test:

1. Khởi tạo database ở phiên bản migration cũ.
2. Thêm dữ liệu đại diện.
3. Chạy migration mới.
4. Xác nhận dữ liệu cũ vẫn giữ nguyên.
5. Xác nhận schema mới đúng.
6. Chạy repository query và update trên schema mới.

Migration cần được kiểm chứng trên PostgreSQL và MySQL độc lập.

## 12. Quản lý cấu hình theo database

Có thể dùng Spring profiles để chọn JDBC URL và thông số kết nối.

§application-h2.yml§:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:shop;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
    driver-class-name: org.h2.Driver
~~~

§application-postgresql.yml§:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
~~~

§application-mysql.yml§:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/shop
    username: shop_app
    password: ${DB_PASSWORD}
    driver-class-name: com.mysql.cj.jdbc.Driver
~~~

Chạy profile:

~~~bash
./mvnw test -Dspring.profiles.active=postgresql
~~~

Hoặc:

~~~bash
./mvnw test -Dspring.profiles.active=mysql
~~~

Đây là ví dụ cấu hình profile. Khi dùng Testcontainers, thường không cần hard-code host/port; §@DynamicPropertySource§ ghi đè datasource properties bằng địa chỉ container được cấp runtime.

Không lưu password production trong file cấu hình hoặc repository. Dùng secret manager hoặc biến môi trường.

## 13. Ma trận compatibility trong CI

Một pipeline có thể chạy các nhóm test như sau:

| Job | Database | Bộ test | Mục tiêu |
| --- | --- | --- | --- |
| §unit§ | Không cần DB | Unit tests | Domain behavior |
| §jdbc-h2§ | H2 | Repository smoke tests | Feedback nhanh |
| §jdbc-postgresql§ | PostgreSQL container | Migration + repository integration | Production compatibility |
| §jdbc-mysql§ | MySQL container | Migration + repository integration | Production compatibility |
| §migration-upgrade§ | Mỗi DB mục tiêu | Upgrade tests | An toàn dữ liệu hiện hữu |

Nếu production chỉ dùng PostgreSQL, ưu tiên PostgreSQL integration tests. Nếu sản phẩm cam kết hỗ trợ cả PostgreSQL và MySQL, cả hai phải là required checks.

Ví dụ GitHub Actions dạng khái niệm:

~~~yaml
jobs:
  test-postgresql:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./mvnw verify -Ppostgresql

  test-mysql:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./mvnw verify -Pmysql
~~~

Testcontainers sẽ cần Docker runtime khả dụng trong runner. Cấu hình thực tế cần điều chỉnh Java version, Maven profile và cache dependency theo dự án.

### 13.1. Pin version database

Không nên dùng tag image không cố định như §postgres:latest§ hoặc §mysql:latest§ cho integration test quan trọng.

Hãy pin version gần production:

~~~text
Production PostgreSQL: 16.x
Test PostgreSQL:       16.x

Production MySQL:      8.4.x
Test MySQL:            8.4.x
~~~

Có thể pin image digest nếu pipeline yêu cầu tính tái lập cao hơn. Khi nâng database version, thay đổi image trong CI và chạy lại toàn bộ compatibility suite trước khi rollout.

## 14. Quan sát SQL được sinh ra

Khi một test fail, hãy phân biệt lỗi từ:

- Dialect.
- Mapping metadata.
- SQL sinh tự động.
- SQL tùy chỉnh.
- Driver conversion.
- Schema migration.
- Database constraint.
- Transaction behavior.

Spring Data JDBC sử dụng cơ chế của Spring JDBC để thực thi SQL. Có thể bật logging:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Log SQL giúp thấy câu lệnh và tham số được thực thi. Cần tránh log giá trị nhạy cảm ở production.

Khi điều tra lỗi:

1. Xem database product/version và driver version.
2. Xem SQL thực tế.
3. Chạy SQL tương ứng trên database container.
4. Kiểm tra schema bằng §information_schema§ hoặc công cụ vendor.
5. Xem execution plan nếu vấn đề là hiệu năng.
6. So sánh kết quả với H2 để xác định khác biệt.
7. Tạo test regression trên database gây lỗi.

Không sửa code bằng cách thêm nhánh kiểm tra tên database trước khi xác định khác biệt thực tế nằm ở dialect, schema hay SQL custom.

## 15. Ví dụ một test compatibility quan trọng: optimistic locking

Giả sử aggregate:

~~~java
@Table("inventory_items")
public record InventoryItem(
        @Id Long id,
        String sku,
        int availableQuantity,
        @Version Long version
) {
}
~~~

Test stale update:

~~~java
@SpringBootTest
class InventoryVersionIntegrationTest {

    @Autowired
    InventoryRepository repository;

    @Test
    void rejectsUpdateUsingStaleVersion() {
        InventoryItem created = repository.save(
                new InventoryItem(
                        null,
                        "SKU-01",
                        10,
                        null
                )
        );

        InventoryItem firstRead = repository.findById(created.id())
                .orElseThrow();

        InventoryItem secondRead = repository.findById(created.id())
                .orElseThrow();

        InventoryItem firstChange = new InventoryItem(
                firstRead.id(),
                firstRead.sku(),
                8,
                firstRead.version()
        );

        repository.save(firstChange);

        InventoryItem staleChange = new InventoryItem(
                secondRead.id(),
                secondRead.sku(),
                7,
                secondRead.version()
        );

        assertThrows(
                OptimisticLockingFailureException.class,
                () -> repository.save(staleChange)
        );
    }
}
~~~

Chạy cùng contract test này trên PostgreSQL và MySQL. Nó kiểm tra semantics optimistic locking qua JDBC driver và database thực tế.

Nếu test được đặt trong transaction do framework test mở sẵn, hãy thiết kế transaction boundaries phù hợp để lần save đầu thực sự được nhìn thấy bởi thao tác stale save. Có thể dùng test không có transaction ngoài hoặc tách hai thao tác qua transaction riêng.

## 16. Ví dụ kiểm tra migration và constraint

Giả sử database cần bảo đảm SKU duy nhất và số lượng không âm:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT chk_inventory_quantity
        CHECK (available_quantity >= 0)
);
~~~

Một số database/phiên bản có khác biệt về thời điểm hoặc mức độ hỗ trợ constraint. Test trên từng database:

~~~java
@Test
void databaseRejectsDuplicateSku() {
    repository.save(new InventoryItem(
            null, "SKU-01", 10, null
    ));

    assertThrows(
            DataIntegrityViolationException.class,
            () -> repository.save(new InventoryItem(
                    null, "SKU-01", 5, null
            ))
    );
}
~~~

Ngoài exception, nên xác nhận số hàng và dữ liệu cuối cùng trong database. Với constraint violation, transaction có thể bị đánh dấu rollback-only tùy database và transaction manager; không tiếp tục sử dụng transaction đó như thể chưa có lỗi.

## 17. Kiểm tra hành vi cụ thể theo vendor

Không phải mọi tính năng cần test trên cả ba database nếu ứng dụng không dùng chúng. Hãy lập danh sách tính năng thực sự xuất hiện trong schema/domain/query.

| Tính năng | Câu hỏi kiểm chứng |
| --- | --- |
| JSON | Converter bind kiểu gì? Query operator có chạy trên database đích? |
| Array | Database có hỗ trợ kiểu array và JDBC driver có mapping phù hợp? |
| UUID | Kiểu cột native hay chuỗi? Converter có round-trip? |
| Sequence | Sequence được tạo và cấp quyền đúng? |
| Identity | Insert trả generated key đúng? |
| Upsert | SQL có portable hay phải tách theo vendor? |
| Collation | So sánh và unique constraint có phân biệt hoa/thường đúng? |
| Timezone | Instant có giữ nguyên qua round-trip? |
| DDL | Migration có chạy đúng với transaction behavior của server? |
| Pagination | Sort tie-breaker và limit/offset có kết quả ổn định? |
| Locking | Optimistic/pessimistic locking có đúng semantics? |
| Stored procedure | Parameter và result mapping có tương thích driver? |

Hãy ưu tiên test các tính năng có tác động đến tính đúng đắn dữ liệu trước các tính năng chỉ ảnh hưởng cú pháp hoặc hiệu năng.

## 18. Các dấu hiệu ứng dụng chưa thực sự portable

Một ứng dụng có thể đang phụ thuộc database mà không nhận ra. Một số dấu hiệu:

- Test H2 pass nhưng integration test PostgreSQL/MySQL fail.
- Migration dùng identity hoặc sequence syntax riêng mà không có migration theo vendor.
- Repository có nhiều §@Query§ dùng function hoặc operator đặc thù.
- Tên bảng/cột chứa reserved keyword.
- Query tìm email cho kết quả khác giữa các môi trường.
- Timestamp lệch vài giờ khi chuyển database.
- Giá trị decimal bị round khác nhau.
- Test optimistic locking chỉ pass trên H2.
- Dữ liệu JSON/array chỉ hoạt động với một driver.
- Production có unique constraint hoặc collation khác H2.
- Một số thao tác DDL commit ngoài transaction trên MySQL.
- Ứng dụng tự ép dialect nhưng JDBC metadata lại nhận database khác.

Khi gặp các dấu hiệu này, cần xác định rõ ứng dụng cam kết hỗ trợ database nào. Không phải mọi dự án đều cần portable trên ba vendor; điều quan trọng là test và tài liệu phải phản ánh chính xác phạm vi hỗ trợ.

## 19. Quy trình kiểm chứng tính tương thích

Có thể tổ chức quá trình kiểm chứng theo thứ tự sau:

1. **Chốt database mục tiêu:** H2, PostgreSQL, MySQL hoặc tổ hợp thực sự cần hỗ trợ.
2. **Chốt phiên bản server và driver:** pin version gần production.
3. **Kiểm tra dialect discovery:** xác nhận Spring Data JDBC nhận đúng database qua JDBC metadata.
4. **Chạy migration từ database trống:** bảo đảm DDL tạo schema thành công.
5. **Chạy migration upgrade:** xác nhận dữ liệu hiện hữu được giữ nguyên.
6. **Chạy mapping contract tests:** CRUD, aggregate, collection, embedded, converter, ID generation.
7. **Chạy query tests:** derived query, Criteria, sorting, pagination và custom SQL.
8. **Chạy data type tests:** decimal, time, timezone, UUID, JSON, Unicode và NULL.
9. **Chạy transaction tests:** rollback, optimistic locking, constraint và concurrency.
10. **Chạy vendor-specific tests:** upsert, JSON operator, sequence hoặc function đặc thù.
11. **Quan sát SQL và metadata:** khi fail, lưu SQL/error để tạo regression test.
12. **Đưa database container vào CI:** required checks cho mọi database được cam kết hỗ trợ.
13. **Đối chiếu staging:** dùng cùng major version, collation, timezone và cấu hình gần production.
14. **Kiểm tra trước khi nâng version:** cập nhật server/driver/dialect và chạy lại toàn bộ compatibility suite.

~~~mermaid
flowchart TD
    A["Chọn database và version mục tiêu"] --> B["Cấu hình JDBC driver + DataSource"]
    B --> C["Xác nhận dialect được phát hiện"]
    C --> D["Chạy schema migration"]
    D --> E["Chạy mapping và repository contract tests"]
    E --> F["Chạy query và data type tests"]
    F --> G["Chạy transaction/concurrency tests"]
    G --> H{"Có lỗi tương thích?"}
    H -->|Có| I["Kiểm tra SQL, metadata, schema và driver"]
    I --> J["Sửa mapping/migration/query"]
    J --> E
    H -->|Không| K["Đưa test vào CI"]
    K --> L["Xác nhận trên staging cùng loại DB"]
~~~

## 20. Bài tập thực hành

Tạo một ứng dụng Spring Data JDBC có aggregate §Customer§ và §InventoryItem§.

### Bài 1: Chạy cùng repository trên H2

1. Cấu hình H2 in-memory.
2. Tạo repository cho §Customer§.
3. Kiểm tra insert, findById, update và delete.
4. Kiểm tra generated ID.
5. Ghi nhận SQL và database metadata.

### Bài 2: Chuyển integration test sang PostgreSQL

1. Thêm PostgreSQL JDBC driver.
2. Thêm Testcontainers JUnit và PostgreSQL module.
3. Khởi chạy PostgreSQL container.
4. Dùng §@DynamicPropertySource§ cấu hình datasource.
5. Chạy migration và repository tests.
6. So sánh generated ID, timestamp, constraint và SQL với H2.

### Bài 3: Kiểm tra MySQL

1. Thêm MySQL Connector/J và MySQL Testcontainers module.
2. Khởi chạy MySQL container.
3. Chạy cùng contract test.
4. Kiểm tra identity, collation và Boolean mapping.
5. Xác nhận migration thực tế chạy được.

### Bài 4: Kiểm tra dữ liệu biên

1. Lưu §BigDecimal§ có precision tối đa.
2. Lưu Unicode tiếng Việt.
3. Lưu timestamp có offset khác UTC.
4. Lưu NULL và empty string.
5. Đọc lại trên cả ba database và so sánh semantics.

### Bài 5: Kiểm tra concurrency

1. Tạo aggregate có §@Version§.
2. Đọc cùng aggregate trong hai transaction.
3. Save lần đầu.
4. Save object có version cũ.
5. Xác nhận §OptimisticLockingFailureException§ trên PostgreSQL và MySQL.
6. Kiểm tra trạng thái cuối cùng của database.

### Bài 6: Kiểm tra migration upgrade

1. Tạo schema ở phiên bản migration cũ.
2. Chèn dữ liệu mẫu.
3. Chạy migration mới.
4. Xác nhận dữ liệu không mất.
5. Kiểm tra index, foreign key, unique constraint và default.
6. Lặp lại với PostgreSQL và MySQL.

## 21. Ghi nhớ

- Spring Data JDBC hỗ trợ dialect trực tiếp cho H2, PostgreSQL và MySQL.
- §DialectResolver§ phát hiện dialect thông qua JDBC connection metadata; Spring Boot tự cấu hình khi có starter và §DataSource§.
- Dialect xử lý khác biệt SQL phổ biến, không biến các database thành cùng một engine.
- H2 hữu ích cho test nhanh nhưng không thay thế PostgreSQL/MySQL thật.
- H2 compatibility mode không phải bằng chứng tương thích với database vendor tương ứng.
- Kiểu dữ liệu, timezone, precision, collation, identifier quoting, generated key và transaction semantics có thể khác nhau.
- Derived query và dynamic §Query§ có thể dùng abstraction của Spring Data JDBC; SQL tùy chỉnh phải được kiểm chứng theo từng vendor.
- Chạy Flyway/Liquibase migration trên database thật, cả clean install và upgrade.
- Testcontainers cho phép integration test với database server tạm thời trong Docker.
- Kiểm thử MySQL và PostgreSQL riêng; nếu dùng MariaDB thì kiểm thử MariaDB riêng.
- Pin version database và JDBC driver gần production để test có tính tái lập.
- Tạo contract test chung cho CRUD, mapping, query, transaction và optimistic locking; bổ sung test riêng cho vendor-specific features.
- Đưa PostgreSQL/MySQL integration tests vào CI nếu ứng dụng cam kết hỗ trợ các database đó.
- Quan sát SQL, metadata và lỗi database để tạo regression test.
- Xác nhận trên staging với version, collation, timezone và cấu hình gần production.

**H2 giúp phát hiện lỗi sớm; database production mới xác nhận được tính tương thích thực tế.** Hãy để dialect xử lý phần SQL chung, còn migration, kiểu dữ liệu, query tùy chỉnh, transaction và concurrency phải được kiểm chứng trên đúng database mà ứng dụng sẽ vận hành.

## Tài liệu tham khảo

- [Spring Data Relational 4.1.2 — Getting Started and Dialects](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html)
- [Spring Data Relational 4.1.2 — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Data JDBC 4.1.2 — DialectResolver API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/dialect/DialectResolver.html)
- [Spring Data JDBC 4.1.2 — AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html)
- [Spring Boot 4.1.2 — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers for Java — JDBC Support](https://java.testcontainers.org/modules/databases/jdbc/)

