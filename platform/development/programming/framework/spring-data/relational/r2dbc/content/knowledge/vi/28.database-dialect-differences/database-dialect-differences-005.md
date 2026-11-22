# H2: lợi ích thử nghiệm và khác biệt với cơ sở dữ liệu thật

## 1. H2 trong bối cảnh Spring Data Relational R2DBC

H2 là một hệ quản trị cơ sở dữ liệu quan hệ được viết bằng Java. Nó có thể chạy embedded trong tiến trình ứng dụng, lưu dữ liệu trong bộ nhớ hoặc trên file, và cung cấp SQL để tạo bảng, truy vấn, cập nhật và xóa dữ liệu. Nhờ khởi động nhanh và không cần một database server riêng, H2 thường được dùng trong unit test mở rộng và integration test của ứng dụng Spring.

Với Spring Data R2DBC, H2 có thể được truy cập qua R2DBC driver. Repository, R2dbcEntityTemplate và DatabaseClient vẫn được sử dụng theo API quen thuộc của Spring Data. Điều này giúp kiểm tra nhiều phần của ứng dụng mà không phải dựng PostgreSQL, MySQL hoặc database server khác cho từng lần chạy test.

Tuy nhiên, H2 không phải bản sao hoàn chỉnh của database production. Mỗi hệ quản trị có dialect SQL, kiểu dữ liệu, quy tắc constraint, transaction, locking, index và query planner riêng. Một test chạy thành công trên H2 chỉ chứng minh hành vi trong môi trường H2; nó không tự chứng minh câu SQL và mapping sẽ hoạt động giống hệt trên PostgreSQL, MySQL, SQL Server hoặc Oracle.

Cách dùng hợp lý là xem H2 như một database thử nghiệm nhanh cho những hành vi relational phổ thông, sau đó dùng đúng hệ quản trị của production cho các integration test cần xác nhận tính tương thích.

## 2. Vì sao H2 hữu ích cho kiểm thử?

H2 đem lại một số lợi ích thực tế:

- **Khởi động nhanh:** test có thể tạo database mới mà không phải khởi động container hoặc dịch vụ riêng.
- **Ít phụ thuộc môi trường:** developer và CI không cần cài một database server chỉ để chạy nhóm test cơ bản.
- **Database cô lập:** mỗi test suite có thể dùng database in-memory riêng để tránh dữ liệu còn sót từ lần chạy trước.
- **Kiểm tra SQL relational:** có thể kiểm tra CREATE TABLE, INSERT, SELECT, UPDATE, DELETE, constraint và nhiều biểu thức SQL phổ thông.
- **Kiểm tra Spring Data mapping:** có thể xác nhận entity metadata, @Table, @Column, @Id, converter và repository query trong môi trường thật hơn mock.
- **Phản hồi nhanh:** lỗi mapping hoặc điều kiện truy vấn đơn giản thường được phát hiện sớm.
- **Dễ tạo fixture:** test có thể nạp schema và dữ liệu mẫu từ script.

H2 phù hợp để kiểm tra những câu hỏi như:

- Repository có trả đúng entity theo ID không?
- Criteria có tạo điều kiện lọc đúng không?
- Insert có lưu các property và generated ID theo cấu hình H2 không?
- DTO được map đúng từ query phổ thông không?
- Unique constraint có từ chối dữ liệu trùng trong H2 không?
- Một transaction có rollback dữ liệu khi một bước ghi thất bại trong môi trường H2 không?

Những câu hỏi liên quan đến cú pháp riêng, concurrency, locking hoặc kiểu dữ liệu đặc thù của production cần được kiểm thử thêm bằng database tương ứng.

## 3. H2 không phải database production giả lập hoàn chỉnh

Giả sử ứng dụng production dùng PostgreSQL. Một test H2 có thể chạy:

~~~sql
SELECT id, name
FROM customers
WHERE status = 'ACTIVE'
ORDER BY id
LIMIT 20;
~~~

Đây là truy vấn phổ thông mà nhiều hệ quản trị hỗ trợ. Nhưng khi ứng dụng dùng kiểu PostgreSQL-specific như JSONB, array operator, ON CONFLICT, RETURNING, extension hoặc function riêng, H2 có thể không hỗ trợ cú pháp đó hoặc có semantics khác.

Ngay cả khi H2 cung cấp một tính năng có tên tương tự, chi tiết triển khai có thể khác. Ví dụ, cách cast kiểu, so sánh chuỗi, xử lý timestamp, generated value và transaction lock có thể không giống production.

Vì vậy, cần phân biệt:

| Mục tiêu kiểm thử | H2 có phù hợp? |
|---|---|
| Kiểm tra mapping entity cơ bản | Thường phù hợp |
| Kiểm tra CRUD và repository query phổ thông | Thường phù hợp |
| Kiểm tra constraint relational đơn giản | Phù hợp trong phạm vi semantics H2 |
| Kiểm tra custom SQL theo dialect production | Không đủ |
| Kiểm tra JSONB, array hoặc function riêng của PostgreSQL | Không đủ |
| Kiểm tra locking/deadlock/concurrency production | Không đủ |
| Kiểm tra query plan và hiệu năng production | Không đủ |
| Kiểm tra migration trên đúng engine production | Không đủ |
| Kiểm tra hành vi driver R2DBC production | Không đủ |

H2 là một tầng kiểm thử hữu ích, nhưng không nên là bằng chứng duy nhất cho tính tương thích của ứng dụng với database production.

## 4. Dùng H2 qua R2DBC driver

Để Spring Data R2DBC truy cập H2, dự án cần R2DBC driver tương ứng. Dependency thường dùng là io.r2dbc:r2dbc-h2, với phiên bản được quản lý tương thích bởi dependency management của Spring Boot hoặc cấu hình dự án.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'

    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Nếu chỉ dùng H2 qua R2DBC, không nhất thiết phải thêm JDBC driver H2. JDBC driver chỉ cần khi một thành phần khác như Flyway hoặc Liquibase được cấu hình kết nối H2 bằng JDBC.

Hãy dùng phiên bản driver H2 R2DBC tương thích với phiên bản Spring Boot, Spring Data Relational và R2DBC SPI trong dự án. Tránh tự nâng riêng một dependency vượt khỏi phiên bản mà dependency management đã kiểm soát nếu chưa kiểm tra compatibility.

### 4.1. Cấu hình database in-memory

Một cấu hình R2DBC H2 in-memory có dạng:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:h2:mem:///testdb
    username: sa
    password:
~~~

URL cụ thể và các tham số giữ database sống phụ thuộc phiên bản R2DBC H2 driver. Hãy xác nhận cú pháp với tài liệu của driver đang dùng.

Database in-memory thường gắn với tên database và vòng đời connection. Nếu database bị đóng khi connection cuối cùng được giải phóng, test có thể gặp tình huống schema biến mất giữa các lần lấy connection. Với một số cấu hình H2, có thể cần tùy chọn giữ database tồn tại trong suốt vòng đời test context. Không sao chép tùy chọn JDBC URL sang R2DBC URL mà không kiểm tra cách driver R2DBC nhận tham số.

### 4.2. Tên database và phạm vi cô lập

Nếu nhiều test context dùng cùng tên database in-memory trong cùng process, dữ liệu có thể được chia sẻ tùy cách driver tạo và giữ database. Để test độc lập, hãy chọn một trong các cách:

- Dùng database name riêng theo test suite.
- Dọn dữ liệu và reset sequence theo setup test.
- Đóng context/connection theo vòng đời rõ ràng.
- Dùng database container riêng cho nhóm test cần engine production.

Không để test phụ thuộc vào thứ tự chạy hoặc dữ liệu còn sót của test trước.

## 5. Khởi tạo schema và dữ liệu test

Có thể dùng script SQL để tạo schema:

~~~text
src/test/resources/
├── schema.sql
└── data.sql
~~~

Ví dụ schema.sql:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(320) NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE UNIQUE INDEX uq_customers_email
    ON customers(email);
~~~

Ví dụ data.sql:

~~~sql
INSERT INTO customers (name, email, status)
VALUES
    ('An Nguyen', 'an@example.test', 'ACTIVE'),
    ('Binh Tran', 'binh@example.test', 'INACTIVE');
~~~

Spring Boot hỗ trợ SQL script initialization cho R2DBC. Cấu hình thường dùng:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
      data-locations: classpath:data.sql
~~~

Trong test, script có thể giúp mỗi context có schema và fixture nhất quán. Cần cấu hình initialization chạy đúng thứ tự trước test truy cập repository.

Nếu dự án dùng Flyway hoặc Liquibase để quản lý schema, hãy quyết định một nguồn tạo schema thống nhất. Có thể dùng migration tool trong test để kiểm tra migration thật; không nên vô tình chạy đồng thời migration và schema.sql trên cùng schema nếu cả hai cùng tạo một bảng.

## 6. Kiểm tra entity mapping bằng H2

Ví dụ entity:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        String email,
        String status
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);
}
~~~

Test:

~~~java
@DataR2dbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void shouldFindActiveCustomers() {
        StepVerifier.create(repository.findByStatus("ACTIVE"))
                .expectNextMatches(customer ->
                        customer.name().equals("An Nguyen"))
                .verifyComplete();
    }
}
~~~

Ví dụ minh họa kiểm tra repository và mapping qua R2DBC. Cấu hình test thực tế cần cung cấp ConnectionFactory H2 và schema fixture tương ứng. Tùy phiên bản Spring Boot, cách cấu hình test slice và SQL initialization có thể khác; không giả định annotation tự chọn H2 nếu classpath hoặc cấu hình database không đáp ứng điều kiện.

Test này có thể phát hiện:

- Tên bảng hoặc cột mapping sai.
- Repository method không tạo điều kiện như mong đợi.
- Kiểu dữ liệu không tương thích với entity.
- Fixture thiếu cột bắt buộc.
- Generated ID hoặc mapping cơ bản không hoạt động trong H2.

Nó không chứng minh cùng entity sẽ hoạt động giống hệt với mọi kiểu dữ liệu và driver production.

## 7. Kiểm thử DatabaseClient và SQL tường minh

Với DatabaseClient, test H2 có thể xác nhận SQL phổ thông và row mapping:

~~~java
@Test
void shouldReadCustomerSummary() {
    Flux<CustomerSummary> result =
            databaseClient.sql("""
                    SELECT id, name, status
                    FROM customers
                    WHERE status = :status
                    ORDER BY id
                    """)
                .bind("status", "ACTIVE")
                .map((row, metadata) -> new CustomerSummary(
                        row.get("id", Long.class),
                        row.get("name", String.class),
                        row.get("status", String.class)
                ))
                .all();

    StepVerifier.create(result)
            .expectNextCount(1)
            .verifyComplete();
}
~~~

Đây là kiểm thử hữu ích khi SQL không phụ thuộc dialect đặc thù. H2 có thể giúp phát hiện lỗi cú pháp phổ thông, sai alias, sai tên cột và mapping kiểu dữ liệu cơ bản.

Nếu SQL sử dụng ON CONFLICT, JSONB operator, PostgreSQL array, RETURNING hoặc function riêng, test H2 có thể thất bại dù SQL đúng trên PostgreSQL, hoặc ngược lại nếu compatibility mode chấp nhận một cú pháp nhưng semantics khác. Những query này nên được kiểm thử trên database production tương ứng.

## 8. Khác biệt về SQL dialect

Mỗi database có dialect riêng. H2 hỗ trợ một tập SQL khá rộng, nhưng không có nghĩa nó triển khai mọi cú pháp của database khác.

Một số vùng dễ khác nhau:

- Pagination và limit syntax.
- Upsert và conflict handling.
- Generated key và RETURNING/OUTPUT.
- CTE và recursive query.
- Window function.
- JSON operator và function.
- Array, enum và domain type.
- Sequence và identity column.
- Function ngày giờ, chuỗi và toán học.
- Locking clause như FOR UPDATE.
- Cú pháp index và partial index.

Ví dụ upsert PostgreSQL:

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES (:sku, :quantity)
ON CONFLICT (sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

Một cú pháp H2 có thể dùng MERGE theo cách riêng:

~~~sql
MERGE INTO inventory (sku, quantity)
KEY (sku)
VALUES (:sku, :quantity);
~~~

Hai câu lệnh đều có thể diễn tả một số dạng insert/update theo khóa, nhưng không nên coi chúng là tương đương hoàn toàn. Semantics khi có nhiều unique constraint, trigger, affected-row count, concurrency và generated values có thể khác.

Nếu ứng dụng production dùng PostgreSQL ON CONFLICT, hãy kiểm thử câu lệnh đó trên PostgreSQL thay vì viết một câu H2 khác rồi kết luận tính năng upsert đã được kiểm chứng.

## 9. Khác biệt về identifier và tên bảng/cột

Database có quy tắc riêng về cách xử lý identifier không đặt trong dấu quote và identifier có quote.

Ví dụ, PostgreSQL chuyển identifier không quote về chữ thường; H2 có quy tắc chuẩn hóa tên identifier riêng, thường hiển thị identifier không quote theo dạng chữ hoa trong metadata. Identifier có quote có thể phân biệt hoa/thường theo cách khác.

Điều này có thể làm lộ lỗi khi:

- Entity dùng @Column("createdAt") nhưng schema dùng created_at.
- Raw SQL quote tên cột khác casing.
- Một migration tạo tên bảng có quote.
- Mapping metadata và tên cột trong query không đồng nhất.
- Test H2 chạy được nhưng query metadata hoặc native SQL production thất bại.

Nên dùng naming convention nhất quán, thường là snake_case không quote cho tên bảng/cột, và khai báo rõ @Table/@Column khi cần. Đối với raw SQL, dùng đúng identifier theo database đích và kiểm thử trên engine đó.

## 10. Khác biệt về kiểu dữ liệu

Kiểu Java và kiểu SQL được ánh xạ thông qua R2DBC driver và Spring Data converter. Cùng một kiểu Java có thể được biểu diễn bằng kiểu SQL khác nhau giữa các database.

Những kiểu cần chú ý:

| Nhóm dữ liệu | Ví dụ khác biệt cần kiểm tra |
|---|---|
| Boolean | Cách biểu diễn và chuyển đổi boolean |
| UUID | Kiểu UUID native hay chuỗi/binary |
| Timestamp | Timestamp có timezone và không timezone |
| Decimal | Precision, scale và rounding |
| JSON | JSON text, JSON native hoặc JSONB |
| Array | Hỗ trợ array và cách đọc/ghi qua driver |
| Enum | Enum native hay VARCHAR |
| Binary | BLOB/BYTEA và mapping byte array |
| Identity/sequence | Cách sinh và trả generated ID |
| Large text | TEXT, CLOB hoặc giới hạn độ dài |

Ví dụ PostgreSQL có kiểu UUID native và JSONB. H2 cũng có hỗ trợ một số kiểu tương tự, nhưng cách driver trả về Java type, cú pháp function và semantics có thể khác. Một test H2 không đủ để xác nhận mapping JSONB của PostgreSQL.

### 10.1. Timestamp và timezone

Không nên giả định LocalDateTime, Instant, OffsetDateTime và ZonedDateTime có cùng semantics ở mọi database.

- LocalDateTime biểu diễn ngày giờ không kèm timezone.
- Instant biểu diễn một thời điểm trên timeline UTC.
- OffsetDateTime mang offset.
- Kiểu SQL timestamp with time zone của từng database có semantics riêng.

Ví dụ PostgreSQL TIMESTAMPTZ chuẩn hóa thời điểm theo semantics của PostgreSQL; cách hiển thị phụ thuộc session timezone. H2 có kiểu timestamp with time zone riêng. Test nên xác nhận thời điểm sau round-trip thay vì chỉ so sánh chuỗi hiển thị.

Nếu nghiệp vụ cần một thời điểm tuyệt đối, xác định rõ kiểu Java, kiểu SQL và cách serialize. Đừng để test H2 mặc định timezone máy developer che khuất lỗi production.

### 10.2. Decimal và tiền tệ

Với BigDecimal, hãy khai báo precision/scale rõ ràng trong schema:

~~~sql
amount DECIMAL(19, 4) NOT NULL
~~~

Kiểm tra rounding, scale và giá trị vượt giới hạn. H2 và production database có thể khác ở cách ép kiểu hoặc báo lỗi khi scale vượt quá định nghĩa. Unit test phép tính Java không thay thế integration test lưu và đọc decimal qua driver thật.

## 11. Khác biệt về constraint và tính toàn vẹn dữ liệu

H2 hỗ trợ primary key, unique constraint, foreign key, check constraint và not-null constraint. Tuy nhiên, semantics chi tiết có thể khác database production.

Cần kiểm tra:

- Unique constraint khi một hoặc nhiều cột là NULL.
- Foreign key với ON DELETE CASCADE/RESTRICT/SET NULL.
- Deferrable constraint nếu database production hỗ trợ.
- Check constraint và biểu thức function.
- Partial unique index.
- Constraint validation khi thêm vào bảng đã có dữ liệu.
- Thứ tự thực thi constraint trong transaction.
- Thông tin lỗi và SQLState mà driver trả về.

Ví dụ:

~~~sql
CREATE TABLE customer_addresses (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    address_line VARCHAR(200) NOT NULL,
    CONSTRAINT fk_address_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
        ON DELETE CASCADE
);
~~~

H2 có thể xác nhận quan hệ khóa ngoại và cascade trong test. Nhưng nếu production dùng partial index hoặc deferrable constraint, cần test trên engine đó vì H2 có thể không hỗ trợ hoặc có behavior khác.

Không chỉ kiểm tra rằng thao tác ném exception. Nếu ứng dụng phân loại lỗi theo SQLState, vendor error code hoặc constraint name, cần kiểm tra trên driver production.

## 12. Khác biệt về transaction và isolation

Transaction là một trong những vùng không nên suy luận từ H2 sang production.

Các hệ quản trị có thể khác về:

- Mức isolation được hỗ trợ và semantics thực tế.
- MVCC và snapshot visibility.
- Lock granularity.
- Row lock và table lock.
- Deadlock detection.
- Serialization failure.
- DDL transaction.
- Behavior khi transaction bị cancel hoặc connection mất.
- Thời điểm constraint được kiểm tra.

Ví dụ hai transaction cùng đọc một quantity rồi cập nhật có thể tạo race khác nhau tùy isolation và locking. H2 test đơn giản có thể không tái hiện được deadlock hoặc serialization failure của PostgreSQL/MySQL dưới tải đồng thời.

Nếu nghiệp vụ dựa vào optimistic locking với @Version, pessimistic locking, SELECT ... FOR UPDATE hoặc isolation cụ thể, hãy kiểm thử bằng database production engine. Cần tạo concurrency test thực sự với nhiều connection/transaction, không chỉ gọi repository tuần tự trong một test.

## 13. Khác biệt về index và query planner

H2 có query optimizer và index riêng. Nó có thể chọn execution plan khác với PostgreSQL, MySQL hoặc SQL Server.

Vì vậy:

- Query chạy nhanh trên H2 không chứng minh nhanh trên production.
- Index được dùng trên H2 không chứng minh production dùng cùng index.
- Số hàng ước lượng và cost model khác nhau.
- Statistics và cách thu thập statistics khác nhau.
- Partial/covering index và expression index có thể không được hỗ trợ giống nhau.
- Join order và join algorithm có thể khác.

Không dùng H2 để benchmark hiệu năng database production. Hãy chạy EXPLAIN hoặc công cụ tương ứng trên đúng engine, với dữ liệu có quy mô và phân bố gần thực tế.

H2 vẫn hữu ích để kiểm tra logic truy vấn ở mức chức năng. Đánh giá performance cần môi trường phù hợp hơn.

## 14. Khác biệt về collation và so sánh chuỗi

Kết quả lọc và sắp xếp chuỗi phụ thuộc collation, case sensitivity và cách xử lý dấu.

Ví dụ:

~~~sql
SELECT id, name
FROM customers
WHERE name = :name
ORDER BY name;
~~~

H2 và production có thể khác ở việc so sánh An, AN, án hoặc các chuỗi có dấu. Một query dùng LOWER(name) có thể giúp chuẩn hóa một phần nhưng vẫn không đảm bảo mọi collation giống nhau.

Cần kiểm tra:

- So sánh phân biệt hoa/thường.
- So sánh dấu.
- Thứ tự sort theo locale.
- LIKE và wildcard.
- Hàm LOWER/UPPER.
- Unique constraint trên chuỗi theo collation.
- Index trên expression hoặc collation cụ thể.

Nếu nghiệp vụ yêu cầu tên hoặc email không phân biệt hoa/thường, hãy xác định rõ quy tắc chuẩn hóa và unique constraint trên database production. H2 test có thể kiểm tra code normalization, nhưng không đủ để chứng minh collation production.

## 15. Khác biệt về generated ID, sequence và RETURNING

Spring Data R2DBC có thể hỗ trợ generated ID qua mapping metadata và dialect. Nhưng cách database sinh và trả ID khác nhau.

Một số database dùng identity column; một số dùng sequence; có database hỗ trợ RETURNING, database khác có cơ chế generated key hoặc câu lệnh khác.

Ví dụ:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL
);
~~~

Test H2 có thể xác nhận ID được sinh và entity trả về có ID. Nhưng nếu production dùng PostgreSQL sequence riêng, trigger hoặc default expression, cần test trên PostgreSQL.

Đừng viết SQL lấy generated key theo giả định của H2 rồi triển khai nguyên trạng sang database khác. Kiểm tra dialect và driver của production.

## 16. Compatibility mode của H2 có giới hạn

H2 có các compatibility mode để điều chỉnh một số hành vi theo database khác, ví dụ chế độ tương thích PostgreSQL hoặc MySQL tùy phiên bản.

Compatibility mode có thể giúp chạy một số câu SQL hoặc cách xử lý quen thuộc hơn. Nhưng nó không biến H2 thành PostgreSQL/MySQL thật.

Nó không tái tạo đầy đủ:

- Internal storage engine.
- Query planner và statistics.
- Locking/MVCC implementation.
- Tất cả data type và operator.
- Extension và function.
- Constraint semantics.
- Driver behavior.
- Replication và failover.
- Permission model.
- Migration edge cases.

Không dùng compatibility mode làm lý do bỏ qua test trên database production. Hãy coi nó là tiện ích giảm khác biệt cho một số cú pháp, không phải bảo đảm tương đương.

## 17. Khác biệt giữa H2 JDBC và H2 R2DBC

H2 có JDBC driver và R2DBC driver. Hai driver giao tiếp với cùng họ database H2 nhưng sử dụng API và lifecycle khác nhau.

- JDBC dùng DataSource, Connection, PreparedStatement và API blocking.
- R2DBC dùng ConnectionFactory, Connection, Statement và Publisher reactive.
- Spring Data R2DBC cần R2DBC driver để tạo ConnectionFactory.
- Flyway hoặc một số cấu hình Liquibase thường cần JDBC driver để chạy migration.

Nếu test đang kiểm tra repository R2DBC, hãy dùng H2 R2DBC driver. Dùng H2 JDBC cho schema setup không tự chứng minh R2DBC repository đang được kiểm thử; cần xác nhận hai driver cùng nhìn thấy đúng database/schema nếu chia sẻ một database in-memory.

Khi vừa dùng Flyway JDBC vừa dùng R2DBC H2, phải cấu hình hai URL trỏ cùng một database H2 và giữ vòng đời database đủ lâu để cả hai kết nối cùng truy cập. Cú pháp URL và tùy chọn lifecycle phụ thuộc driver. Nếu chỉ cần test repository cơ bản, có thể khởi tạo schema bằng R2DBC SQL initializer để tránh thêm JDBC path.

## 18. Test H2 không xác nhận migration production

Một migration có thể hợp lệ trên PostgreSQL nhưng thất bại trên H2 vì cú pháp hoặc kiểu dữ liệu khác. Chiều ngược lại cũng có thể xảy ra: migration chạy được trên H2 nhưng production từ chối.

Ví dụ migration có thể sử dụng:

- JSONB.
- CREATE INDEX CONCURRENTLY.
- Partial index với WHERE.
- ALTER TYPE.
- Sequence hoặc extension.
- Function/procedure riêng.
- Cú pháp generated column đặc thù.
- Lock/transaction behavior riêng của database.

Nếu migration được viết cho PostgreSQL, hãy chạy migration trên PostgreSQL trong test. Không sửa migration production thành một phiên bản H2 khác rồi xem đó là cùng một kiểm thử.

Với migration cần hỗ trợ nhiều database, có thể duy trì changelog hoặc migration location riêng theo engine. Phải kiểm tra từng biến thể trên database tương ứng và tránh để hai bộ migration mất đồng bộ.

## 19. Dùng Testcontainers để kiểm thử database thật

Testcontainers cho phép khởi chạy database thật trong container trong thời gian test. Ví dụ nếu production dùng PostgreSQL, có thể dùng PostgreSQL container với phiên bản tương ứng.

Dependency test:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

Test có thể khởi tạo container và cấp URL cho R2DBC:

~~~java
@Testcontainers
@SpringBootTest
class CustomerPostgresIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://" +
                postgres.getHost() + ":" +
                postgres.getFirstMappedPort() + "/" +
                postgres.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }
}
~~~

Đây là ví dụ cấu hình khái quát; cần dùng đúng API container và R2DBC URL theo phiên bản Testcontainers/driver. Nếu dùng Flyway, cần cấp thêm JDBC URL, user và password trỏ cùng container để migration chạy trước test.

Testcontainers cần Docker hoặc runtime container tương thích. Nếu CI không có container runtime, có thể dùng một database test service được quản lý riêng, nhưng phải giữ phiên bản và cấu hình tương đương production.

### 19.1. Khi nào nên dùng H2 và khi nào dùng Testcontainers?

| Loại kiểm thử | H2 | Testcontainers với production DB |
|---|---|---|
| Repository CRUD phổ thông | Tốt, nhanh | Tốt nhưng tốn thời gian khởi động hơn |
| Mapping entity đơn giản | Phù hợp | Xác nhận driver production |
| SQL thuần portable | Có thể phù hợp | Nên có cho truy vấn quan trọng |
| SQL dialect-specific | Không đủ | Cần dùng |
| Migration production | Không đủ | Cần dùng |
| JSON/array/vendor type | Không đủ | Cần dùng |
| Locking và concurrency | Không đủ để kết luận | Cần dùng |
| Query plan/performance | Không đại diện | Gần thực tế hơn; vẫn cần dữ liệu phù hợp |
| Kiểm tra lỗi driver production | Không đủ | Cần dùng |

## 20. Chiến lược kiểm thử theo nhiều tầng

Không cần chọn duy nhất H2 hoặc Testcontainers cho mọi test. Có thể tổ chức nhiều tầng:

~~~text
                 Unit tests
             Domain / service logic
                      |
                      v
              H2 R2DBC tests
        Mapping / CRUD / SQL phổ thông
                      |
                      v
          Testcontainers integration
        Production dialect / driver /
          migrations / transactions
                      |
                      v
          Staging / production-like
        Load / concurrency / operations
~~~

### Tầng 1: Unit test

Mock dependency hoặc kiểm thử domain thuần để xác nhận:

- Quy tắc nghiệp vụ.
- Validation.
- Mapping DTO ở tầng service.
- Xử lý lỗi.
- Quyết định điều phối publisher.

Unit test không cần database nếu mục tiêu không liên quan persistence.

### Tầng 2: H2 R2DBC test

Dùng H2 để kiểm tra nhanh:

- Repository query phổ thông.
- Mapping entity.
- CRUD.
- Constraint đơn giản.
- Transaction rollback cơ bản.
- Row mapping của SQL portable.

### Tầng 3: Production database integration test

Dùng Testcontainers hoặc database test cùng loại để kiểm tra:

- Dialect SQL.
- Migration.
- Vendor-specific type.
- Generated ID và sequence.
- Transaction isolation.
- Locking và concurrency.
- Custom converter với driver thật.
- Constraint và error code.
- Query cần index hoặc execution plan cụ thể.

### Tầng 4: Staging/performance test

Dùng dữ liệu và cấu hình gần production để kiểm tra tải, connection pool, query plan, latency, replication và behavior khi database gặp sự cố.

H2 không thay thế các tầng sau.

## 21. Kiểm thử transaction trên H2 có giới hạn

H2 có thể kiểm tra một luồng transaction đơn giản: insert entity, sau đó phát lỗi, rồi xác nhận dữ liệu rollback.

Ví dụ:

~~~java
@Transactional
public Mono<Customer> createThenFail(Customer customer) {
    return customerRepository.save(customer)
            .flatMap(saved ->
                    Mono.error(new IllegalStateException("force rollback"))
            );
}
~~~

Test:

~~~java
StepVerifier.create(service.createThenFail(customer))
        .expectError(IllegalStateException.class)
        .verify();

StepVerifier.create(customerRepository.count())
        .expectNext(0L)
        .verifyComplete();
~~~

Test này xác nhận transaction flow trong cấu hình H2 hiện tại. Nó không chứng minh mọi trường hợp rollback, cancellation, lock hoặc isolation sẽ giống PostgreSQL/MySQL.

Nếu hệ thống dựa vào SELECT FOR UPDATE, optimistic locking, transaction propagation hoặc isolation cụ thể, hãy viết integration test trên engine production. Cần tạo concurrency test thực sự với nhiều connection/transaction, không chỉ gọi repository tuần tự trong một test.

## 22. Kiểm tra repository và query với H2 mà không phụ thuộc thứ tự test

Một test tốt cần tự chuẩn bị dữ liệu và không dựa vào thứ tự chạy.

Ví dụ:

~~~java
@BeforeEach
void setUp() {
    // Xóa dữ liệu test cũ và tạo fixture cho test hiện tại.
}
~~~

Trong reactive test, setup cần được subscribe và hoàn tất trước khi assertion bắt đầu. Có thể dùng @BeforeEach reactive theo cách phù hợp với framework, hoặc đưa setup vào chính pipeline của test:

~~~java
Mono<Void> arrange = customerRepository.deleteAll()
        .thenMany(Flux.just(
                new Customer(null, "An", "an@example.test", "ACTIVE"),
                new Customer(null, "Binh", "binh@example.test", "INACTIVE")
        ))
        .thenMany(customerRepository.saveAll(
                Flux.just(
                        new Customer(null, "An", "an@example.test", "ACTIVE"),
                        new Customer(null, "Binh", "binh@example.test", "INACTIVE")
                )
        ))
        .then();

StepVerifier.create(
        arrange.thenMany(customerRepository.findByStatus("ACTIVE"))
)
.expectNextMatches(customer -> customer.name().equals("An"))
.verifyComplete();
~~~

Đoạn minh họa cần được điều chỉnh theo API repository và entity thực tế; tránh gọi subscribe() trong setup rồi chạy assertion trước khi dữ liệu được tạo xong.

Nếu dùng database in-memory chung cho cả suite, test có thể chạy song song và xóa dữ liệu của nhau. Hãy dùng database riêng theo context/suite hoặc tắt parallel execution cho nhóm test dùng chung schema nếu chưa có isolation phù hợp.

## 23. H2 và Spring Boot test slice

@DataR2dbcTest có thể dùng để tập trung kiểm tra repository và cấu hình R2DBC mà không khởi tạo toàn bộ ứng dụng. Test slice thường chỉ nạp các bean persistence cần thiết và có thể dùng cấu hình database test.

Ví dụ:

~~~java
@DataR2dbcTest
@Import(CustomerRepositoryConfiguration.class)
class CustomerRepositoryTest {
    // Inject repository và kiểm tra truy vấn.
}
~~~

Cấu hình chính xác phụ thuộc Spring Boot version, dependency có trên classpath và cách dự án khai báo ConnectionFactory. Nếu H2 không được tự chọn hoặc test cần cấu hình rõ, khai báo spring.r2dbc.url trong src/test/resources/application.yml hoặc test property.

Với test cần toàn bộ service, transaction manager, migration hoặc security context, dùng @SpringBootTest có thể phù hợp hơn nhưng thời gian khởi động sẽ lớn hơn.

Không dùng annotation test slice để suy ra rằng migration production đã được kiểm tra. Nếu slice không khởi chạy Flyway/Liquibase, schema có thể đến từ schema.sql và test không đi qua migration thực tế.

## 24. Kiểm tra custom conversion và kiểu dữ liệu

Spring Data R2DBC có thể dùng custom converters để chuyển đổi domain type. H2 hữu ích để kiểm tra converter ở các kiểu SQL phổ thông, nhưng vẫn cần test với driver production nếu kiểu dữ liệu đặc thù.

Ví dụ domain value object:

~~~java
public record EmailAddress(String value) {}
~~~

Converter ghi:

~~~java
@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Converter đọc:

~~~java
@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Test H2 có thể xác nhận String round-trip. Nhưng nếu production lưu EmailAddress dưới kiểu native hoặc driver trả một Java type khác, converter có thể cần điều chỉnh. Hãy test converter với đúng SQL type và R2DBC driver production.

## 25. Không dùng H2 để benchmark production

Một câu query có thể chạy trong vài mili giây trên H2 và chậm hơn nhiều trên database production. Điều đó không nhất thiết là do code ứng dụng thay đổi; engine, network, connection pool, storage, index, statistics và concurrency đều khác.

Không nên:

- So sánh latency H2 với PostgreSQL rồi kết luận query production nhanh.
- Dựa vào H2 execution plan để tạo index production.
- Đánh giá throughput R2DBC production từ H2 in-memory.
- Dùng H2 để kiểm tra pool saturation hoặc network timeout.
- Dùng H2 làm bằng chứng về khả năng scale của database thật.

Benchmark cần chạy trên database cùng engine/version và cấu hình gần production, với dữ liệu đại diện, số connection và concurrency phù hợp. H2 chỉ phù hợp để kiểm tra logic chức năng nhanh.

## 26. Những lỗi thường gặp khi thay production database bằng H2

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Query chạy trên H2 nhưng lỗi trên production | Cú pháp hoặc function khác dialect | Chạy query trên database production bằng Testcontainers |
| Migration chạy trên H2 nhưng thất bại production | DDL, type hoặc index đặc thù | Test migration bằng đúng engine |
| Test không tìm thấy bảng sau khi context tạo mới | In-memory database bị đóng hoặc URL tạo database khác | Kiểm tra tên DB, lifecycle option và ConnectionFactory |
| H2 test pass nhưng timestamp lệch | Timezone/precision khác | Dùng kiểu thời gian rõ ràng và test trên driver production |
| Unique constraint behavior khác | Semantics NULL/collation/constraint khác | Kiểm tra unique rule trên production DB |
| Test không phát hiện lỗi JSONB | H2 không tái tạo kiểu/operator production | Dùng Testcontainers PostgreSQL |
| Test pass nhưng deadlock production | Locking/concurrency engine khác | Tạo concurrency test trên đúng DB |
| SQL mapping lỗi do tên cột | Identifier folding/quoting khác | Chuẩn hóa naming và test native SQL trên engine đích |
| H2 compatibility mode vẫn không chạy SQL | Mode không triển khai toàn bộ dialect | Không coi compatibility mode là emulator |
| Generated ID khác production | Identity/sequence/RETURNING khác | Test generated value với driver thật |
| Query plan production không dùng index | Planner/statistics khác | EXPLAIN trên production-like database |
| Test chạy riêng pass nhưng suite fail | Database state dùng chung hoặc test chạy song song | Cô lập database và fixture |
| Flyway không chạy trên H2 R2DBC | Thiếu JDBC driver/config | Cấp JDBC driver và JDBC URL nếu migration dùng JDBC |

## 27. Quy trình quyết định dùng H2 hay database thật

Trước khi chọn H2 cho một nhóm test, hãy xác định:

1. Test đang kiểm tra domain logic, mapping hay SQL dialect?
2. Query có dùng cú pháp hoặc kiểu dữ liệu riêng của production không?
3. Migration có chứa DDL/function/index đặc thù không?
4. Test có phụ thuộc transaction isolation, locking hoặc concurrency không?
5. Có cần xác nhận R2DBC driver production không?
6. Có cần kiểm tra generated key, sequence hoặc RETURNING không?
7. H2 database có được cô lập theo test context không?
8. Schema được tạo từ migration hay script riêng?
9. Test có thể chạy song song mà không chia sẻ dữ liệu không?
10. Có nhóm Testcontainers bao phủ các hành vi production-specific chưa?

Có thể chọn H2 khi câu hỏi kiểm thử nằm trong phạm vi SQL relational phổ thông và mục tiêu là phản hồi nhanh. Chọn database production qua Testcontainers khi test cần xác nhận dialect, driver, migration, type, transaction hoặc concurrency.

## 28. Một cấu trúc test thực tế

Dự án có thể tổ chức:

~~~text
src/test/
├── java/
│   └── com/example/
│       ├── unit/
│       │   └── CustomerServiceTest.java
│       ├── h2/
│       │   └── CustomerRepositoryH2Test.java
│       └── postgres/
│           ├── CustomerRepositoryPostgresTest.java
│           └── FlywayMigrationTest.java
└── resources/
    ├── application-h2-test.yml
    └── db/
        └── test-data.sql
~~~

Một cách phân loại:

- Unit test không cần database.
- H2 test chạy nhanh cho repository CRUD và mapping cơ bản.
- PostgreSQL Testcontainers test cho native query, migration, type và transaction.
- Staging test cho load, concurrency và vận hành.

Tên package/profile chỉ là gợi ý. Có thể dùng Gradle test task hoặc JUnit tags để chạy các nhóm test khác nhau trong CI, nhưng phải bảo đảm nhóm production database test không bị bỏ qua trong pipeline phát hành.

## 29. Kết luận

H2 là một lựa chọn hữu ích cho kiểm thử Spring Data R2DBC vì database có thể chạy nhanh, cô lập và không cần server riêng. Qua R2DBC driver, test có thể xác nhận repository, entity mapping, CRUD, Criteria, SQL phổ thông, constraint cơ bản và một số luồng transaction.

Giới hạn nằm ở khác biệt giữa các hệ quản trị. SQL dialect, identifier, data type, timezone, decimal, constraint, collation, generated ID, transaction isolation, locking, query planner và migration đều có thể khác với database production. Compatibility mode của H2 chỉ điều chỉnh một phần hành vi và không biến H2 thành bản sao của PostgreSQL, MySQL hoặc hệ quản trị khác.

Hãy dùng H2 để tăng tốc phản hồi cho các kiểm thử relational phổ thông. Với query native, migration, kiểu dữ liệu riêng, concurrency, locking và behavior của driver, hãy chạy Testcontainers hoặc một database test cùng loại/version với production. Kết hợp hai tầng giúp suite vừa nhanh trong phát triển hằng ngày vừa có bằng chứng đáng tin cậy về khả năng tương thích trước khi phát hành.

