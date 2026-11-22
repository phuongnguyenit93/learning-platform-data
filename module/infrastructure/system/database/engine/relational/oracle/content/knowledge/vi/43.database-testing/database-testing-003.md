# Kiểm thử tích hợp với Oracle thật và khác biệt với H2

Ứng dụng Spring Boot dùng JPA có thể chạy unit test và một số repository test nhanh với H2. Tuy nhiên, H2 dù bật chế độ tương thích Oracle cũng không trở thành Oracle Database. Hai hệ quản trị có parser SQL, kiểu dữ liệu, transaction, locking, sequence, function, metadata và hành vi JDBC khác nhau.

Vì vậy, một bộ test chỉ chạy với H2 có thể xanh nhưng ứng dụng vẫn lỗi khi chạy trên Oracle thật. Những lỗi thường chỉ xuất hiện ở môi trường Oracle gồm SQL không hợp lệ, khác biệt DATE/TIMESTAMP, chuỗi rỗng được xử lý như NULL, sequence sai, migration DDL không tương thích, lock behavior khác và lỗi quyền schema.

Chiến lược phù hợp là dùng từng loại test cho mục tiêu riêng:

- Unit test kiểm tra logic nghiệp vụ độc lập với database.
- Test với H2 có thể kiểm tra nhanh một phần repository hoặc luồng đơn giản, nếu SQL nằm trong tập tương thích.
- Integration test với Oracle thật xác nhận SQL, JPA mapping, migration, transaction và hành vi driver trên đúng engine.
- End-to-end test xác nhận ứng dụng và các thành phần tích hợp phối hợp được trong môi trường gần production.

## 1. Vì sao H2 không thay thế Oracle?

H2 là một relational database chạy được trong JVM, thường rất thuận tiện cho test vì khởi động nhanh và có thể chạy in-memory. H2 cung cấp một số chế độ tương thích cú pháp, trong đó có Oracle mode. Chế độ này giúp H2 hiểu thêm một số cú pháp hoặc hành vi quen thuộc, nhưng không mô phỏng đầy đủ Oracle SQL, PL/SQL, optimizer, transaction engine, dictionary hay JDBC driver.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:testdb;MODE=Oracle;DB_CLOSE_DELAY=-1
    username: sa
    password:
    driver-class-name: org.h2.Driver
~~~

MODE=Oracle có thể hữu ích để chạy nhanh các test đơn giản, nhưng không chứng minh câu SQL sẽ chạy trên Oracle. H2 vẫn sử dụng engine và kiểu dữ liệu của H2; chế độ tương thích chỉ bao phủ một phần hành vi.

### Ví dụ về rủi ro

Một repository có thể dùng cú pháp H2 chấp nhận:

~~~sql
SELECT *
  FROM orders
 LIMIT 10;
~~~

Oracle Database không hỗ trợ LIMIT theo cú pháp này. Cách phân trang chuẩn trên Oracle hiện đại thường dùng OFFSET ... FETCH, hoặc Hibernate sinh SQL theo Oracle dialect:

~~~sql
SELECT *
  FROM orders
 ORDER BY order_id
 OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY;
~~~

Nếu test chỉ chạy H2, lỗi này có thể không được phát hiện. Tương tự, H2 có thể chấp nhận một phép chuyển kiểu mà Oracle từ chối, hoặc ngược lại.

## 2. Những khác biệt Oracle và H2 thường gặp

Không nên lập một danh sách cú pháp rồi cho rằng bật Oracle mode là đã xử lý hết. Các khác biệt có thể xuất hiện ở nhiều lớp.

| Chủ đề | Oracle Database | H2 / Oracle mode | Rủi ro khi chỉ test H2 |
|---|---|---|---|
| Chuỗi rỗng | Chuỗi rỗng trong VARCHAR2 được xử lý như NULL | Có thể phân biệt chuỗi rỗng với NULL | Sai validation, unique logic và truy vấn |
| Identifier | Identifier không quote được chuẩn hóa uppercase | Quy tắc và setting có thể khác | Sai tên table/column/schema |
| DATE | Lưu ngày và giờ đến giây | DATE thường chỉ biểu diễn ngày | Sai mapping và điều kiện thời gian |
| TIMESTAMP | Có fractional seconds và biến thể timezone | Semantics khác theo kiểu và setting | Lệch giờ, mất precision |
| NUMBER | Precision/scale theo Oracle | Numeric implementation khác | Tràn số hoặc làm tròn |
| Sequence | NEXTVAL, cache và semantics Oracle | Có hỗ trợ sequence nhưng không giống mọi chi tiết | Lỗi ID hoặc giả định thứ tự |
| PL/SQL | Package, procedure, trigger, cursor, exception | Không triển khai đầy đủ PL/SQL | Migration hoặc stored code thất bại |
| Function | NVL, DECODE, LISTAGG, CONNECT BY, ... | Chỉ hỗ trợ một phần | Native query lỗi |
| Phân trang | OFFSET/FETCH, ROWNUM, analytic function | SQL generation khác | Native query hoặc pagination sai |
| Transaction DDL | DDL thường implicit commit | Transaction DDL khác | Test rollback tạo cảm giác an toàn giả |
| Locking | Oracle row locks, FOR UPDATE, SKIP LOCKED | Engine và scheduling khác | Deadlock, timeout hoặc race condition |
| Metadata | Data dictionary, synonym, schema, grant | Metadata model khác | Test quyền và migration sai |
| LOB | CLOB/NCLOB/BLOB và locator semantics | LOB implementation khác | Lỗi mapping hoặc streaming |

Các mục dưới đây giải thích các khác biệt có ảnh hưởng trực tiếp đến Spring Data JPA.

## 3. Chuỗi rỗng và NULL

Trong Oracle, chuỗi có độ dài bằng 0 được xử lý như NULL đối với các kiểu ký tự như VARCHAR2. Điều này có thể làm kết quả khác với H2.

Ví dụ:

~~~sql
INSERT INTO customers(customer_code)
VALUES ('');
~~~

Trên Oracle, giá trị customer_code được xem là NULL. Một truy vấn:

~~~sql
SELECT *
  FROM customers
 WHERE customer_code = '';
~~~

không có nghĩa là tìm chuỗi rỗng theo cách nhiều hệ quản trị khác hiểu. So sánh với NULL cần dùng IS NULL.

Trong Java, chuỗi rỗng và null là hai giá trị khác nhau. Nếu ứng dụng gửi chuỗi rỗng xuống Oracle, database có thể lưu thành NULL, khiến dữ liệu đọc lại khác với object ban đầu.

Nên kiểm thử rõ:

- Form gửi chuỗi rỗng.
- Form bỏ trống trường.
- Chuỗi chỉ có dấu cách.
- NULL trong unique key hoặc composite key.
- Predicate dùng =, IS NULL, NVL hoặc COALESCE.

Không tự động trim chuỗi nếu nghiệp vụ yêu cầu giữ dấu cách. Hãy xác định chính sách chuẩn hóa ở tầng ứng dụng.

## 4. Identifier, schema và chữ hoa/chữ thường

Oracle chuẩn hóa identifier không đặt trong dấu nháy kép thành chữ hoa:

~~~sql
CREATE TABLE order_items (
  item_id NUMBER
);
~~~

Tên thực tế được lưu là ORDER_ITEMS và ITEM_ID. Nếu tạo identifier có dấu nháy kép:

~~~sql
CREATE TABLE "orderItems" (
  "itemId" NUMBER
);
~~~

thì phải tham chiếu đúng chính tả và đúng case bằng dấu nháy kép trong các câu SQL tương ứng.

Trong ứng dụng JPA, tránh tạo tên bảng/cột mixed-case có quote nếu không có lý do rõ ràng. Mapping có thể khác giữa Hibernate dialect, naming strategy và database.

### Schema không giống database

Trong Oracle, schema gắn với user sở hữu object. Khi kết nối bằng user APP_RUNTIME, schema mặc định thường là APP_RUNTIME, nhưng user có thể được cấp quyền đọc object ở schema khác.

Một số khác biệt cần kiểm tra:

- CURRENT_SCHEMA và user đăng nhập không phải cùng khái niệm.
- Synonym có thể che tên schema thật.
- Quyền object và quyền system khác nhau.
- Một query chạy với DBA account có thể thất bại với application account.
- Tên object có thể được resolve khác khi CURRENT_SCHEMA thay đổi.

Integration test nên chạy bằng user tương tự ứng dụng production, không chỉ chạy bằng SYSTEM hoặc SYS.

## 5. DATE, TIMESTAMP và timezone

Đây là một trong những nguồn lỗi phổ biến khi chuyển từ H2 sang Oracle.

### Oracle DATE có cả thời gian

Oracle DATE lưu năm, tháng, ngày, giờ, phút và giây. Nó không lưu fractional seconds hoặc timezone. H2 DATE thường chỉ biểu diễn phần ngày. Do đó, một cột DATE của Oracle được map vào Java LocalDate có thể làm mất phần thời gian nếu schema thực tế có chứa giờ.

Nếu cột Oracle DATE lưu thời điểm đầy đủ đến giây, cân nhắc mapping phù hợp như LocalDateTime và kiểm tra Hibernate/JDBC mapping. Nếu cột chỉ có ngày nghiệp vụ, chuẩn hóa dữ liệu về nửa đêm và dùng LocalDate theo quy ước rõ ràng.

### TIMESTAMP và các kiểu timezone

Oracle có:

- TIMESTAMP: ngày giờ có fractional seconds, không kèm timezone.
- TIMESTAMP WITH TIME ZONE: có timezone offset/region.
- TIMESTAMP WITH LOCAL TIME ZONE: chuẩn hóa theo database timezone và hiển thị theo session timezone.

Các kiểu này không tương đương hoàn toàn với LocalDateTime, OffsetDateTime, ZonedDateTime hoặc Instant.

Ví dụ DDL:

~~~sql
CREATE TABLE event_log (
  event_id NUMBER PRIMARY KEY,
  created_at TIMESTAMP(6) NOT NULL,
  occurred_at TIMESTAMP(6) WITH TIME ZONE
);
~~~

Java mapping minh họa:

~~~java
@Entity
public class EventLog {
    @Id
    private Long eventId;

    private LocalDateTime createdAt;

    private OffsetDateTime occurredAt;
}
~~~

Mapping chính xác phụ thuộc Hibernate version, Oracle JDBC driver và column type. Hãy kiểm tra bằng integration test cả chiều insert lẫn đọc lại.

### NLS và implicit conversion

Không dựa vào implicit conversion theo NLS_DATE_FORMAT hoặc NLS_TIMESTAMP_FORMAT. Tránh SQL:

~~~sql
WHERE created_at = '14-11-2026'
~~~

Hãy bind typed parameter từ JDBC/JPA hoặc dùng literal có format rõ:

~~~sql
WHERE created_at >= DATE '2026-11-14'
~~~

Với timestamp, dùng bind parameter hoặc TO_TIMESTAMP với format mask phù hợp. Test phải chạy với session NLS khác nhau để phát hiện dependency vào cấu hình mặc định.

## 6. NUMBER, precision và scale

Oracle NUMBER(p,s) có precision và scale rõ ràng. Ví dụ:

~~~sql
CREATE TABLE payment (
  payment_id NUMBER(18,0) PRIMARY KEY,
  amount     NUMBER(12,2) NOT NULL
);
~~~

Java mapping thường dùng Long cho số nguyên trong miền phù hợp và BigDecimal cho tiền tệ hoặc số cần precision. Tránh dùng double cho số tiền vì floating-point có thể tạo sai số.

Ví dụ:

~~~java
@Column(name = "AMOUNT", precision = 12, scale = 2)
private BigDecimal amount;
~~~

Kiểm thử:

- Giá trị lớn nhất và nhỏ nhất hợp lệ.
- Giá trị có nhiều chữ số thập phân.
- Làm tròn và scale khi persist.
- Giá trị âm nếu nghiệp vụ cho phép.
- Giá trị vượt precision.
- Nullability.

Không chỉ kiểm tra entity sau khi set field. Hãy persist, flush, clear persistence context và đọc lại từ Oracle để xác nhận giá trị thực lưu.

## 7. Sequence, identity và chiến lược sinh ID

Oracle hỗ trợ sequence:

~~~sql
CREATE SEQUENCE order_seq
  START WITH 1
  INCREMENT BY 1
  CACHE 100;
~~~

Lấy giá trị:

~~~sql
SELECT order_seq.NEXTVAL
  FROM dual;
~~~

Hibernate có thể dùng sequence generator:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_seq_gen"
)
@SequenceGenerator(
    name = "order_seq_gen",
    sequenceName = "ORDER_SEQ",
    allocationSize = 1
)
private Long id;
~~~

allocationSize cần đồng bộ với cách Hibernate cấp phát ID và increment của sequence theo generator strategy. Nếu không khớp, có thể gặp ID nhảy bất thường hoặc lỗi mapping/sequence increment tùy Hibernate version và cấu hình.

Oracle sequence không bảo đảm số ID liên tục:

- Rollback không hoàn lại sequence value.
- Cache có thể làm mất một số giá trị khi instance restart.
- RAC có thể cấp sequence value từ nhiều instance.
- Sequence đảm bảo giá trị được cấp, không bảo đảm thứ tự commit transaction.

Test không nên assert ID liên tiếp không có khoảng trống. Hãy kiểm tra ID tồn tại, unique và mapping đúng.

### Identity column

Các phiên bản Oracle hiện đại hỗ trợ identity column:

~~~sql
CREATE TABLE audit_event (
  event_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  event_type VARCHAR2(50) NOT NULL
);
~~~

Khả năng identity và cách Hibernate sinh SQL phụ thuộc phiên bản Oracle, dialect và JDBC driver. Nếu production schema dùng sequence, đừng để test H2 tự tạo identity column rồi coi migration production đã được xác nhận.

## 8. SQL riêng của Oracle và native query

JPA JPQL có tính portable hơn native SQL, nhưng vẫn cần kiểm tra mapping và SQL được Hibernate sinh ra. Native query gắn trực tiếp với engine.

Một số cú pháp/hàm thường gặp trong Oracle:

- DUAL.
- NVL, DECODE.
- LISTAGG.
- CONNECT BY.
- ROWNUM.
- ROW_NUMBER() OVER (...).
- MERGE.
- REGEXP_LIKE.
- SYS_GUID().
- SYSTIMESTAMP.
- JSON operators/functions tùy phiên bản.

Ví dụ truy vấn phân cấp:

~~~sql
SELECT employee_id,
       manager_id,
       LEVEL AS hierarchy_level
  FROM employees
 START WITH manager_id IS NULL
 CONNECT BY PRIOR employee_id = manager_id;
~~~

H2 Oracle mode không đảm bảo hỗ trợ đầy đủ Oracle hierarchical query, package, optimizer hint hoặc mọi function version-specific. Các truy vấn này cần test trên Oracle thật.

### Phân trang

Native SQL dùng ROWNUM, OFFSET/FETCH hoặc analytic function có quy tắc khác nhau. Nếu dùng Spring Data Pageable, hãy để Hibernate Oracle dialect sinh SQL khi có thể, rồi kiểm tra generated SQL và kết quả thực tế trên Oracle.

Không viết native query với LIMIT rồi kỳ vọng Oracle hiểu.

### MERGE và concurrent update

Oracle MERGE rất hữu ích cho upsert, nhưng kết quả khi nhiều transaction cùng insert/update một key cần được kiểm thử. H2 có thể có semantics hoặc lock scheduling khác.

Nếu upsert là luồng quan trọng, hãy chạy test concurrency trên Oracle với unique constraint thật và xác định cách xử lý duplicate key/retry.

## 9. PL/SQL, package, trigger và stored procedure

Oracle ứng dụng thực tế có thể dùng:

- PL/SQL package.
- Stored procedure/function.
- Trigger.
- Sequence và trigger sinh ID.
- Scheduler job.
- Synonym.
- Database link.
- Virtual column.
- Function-based index.
- Partitioned table.

H2 không triển khai PL/SQL như Oracle. Một test H2 không thể xác nhận package compile, trigger chạy đúng hoặc procedure xử lý exception như Oracle.

Ví dụ procedure:

~~~sql
CREATE OR REPLACE PROCEDURE close_order(
  p_order_id IN NUMBER
) AS
BEGIN
  UPDATE orders
     SET status = 'CLOSED'
   WHERE order_id = p_order_id;
END;
/
~~~

Integration test nên gọi procedure qua JDBC hoặc EntityManager trên Oracle thật, sau đó kiểm tra trạng thái dữ liệu và lỗi Oracle trả về.

### Kiểm tra object invalid

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
  FROM all_objects
 WHERE status = 'INVALID'
 ORDER BY owner, object_type, object_name;
~~~

Test migration nên xác nhận package, view, trigger và procedure được compile thành công. Không chỉ xác nhận Flyway/Liquibase báo migration hoàn tất.

## 10. Transaction và DDL: khác biệt quan trọng

Oracle DDL như CREATE TABLE, ALTER TABLE, DROP TABLE, CREATE INDEX thường gây implicit commit trước và sau DDL. Vì vậy, DDL không được rollback giống DML trong một transaction thông thường.

Ví dụ:

~~~sql
BEGIN
  INSERT INTO test_log(id) VALUES (1);
  CREATE TABLE sample_table(id NUMBER);
  ROLLBACK;
END;
~~~

Không nên kỳ vọng insert trước DDL sẽ được rollback như một transaction DML thuần. Oracle DDL có thể commit phần transaction trước khi thực hiện DDL.

Điều này ảnh hưởng trực tiếp đến test:

- @Transactional test không hoàn tác mọi DDL đã chạy.
- Migration tạo bảng/index có thể tồn tại sau khi test rollback.
- @Sql script chứa DDL có thể để lại trạng thái cho test sau.
- Cleanup bằng TRUNCATE cũng là DDL và có implicit commit.

Với integration test, dùng database/schema cô lập và migration có thể chạy lặp lại trên database mới. DML test có thể rollback bằng transaction; DDL phải được quản lý qua migration hoặc cleanup riêng.

## 11. Isolation, locking và concurrency

Oracle mặc định dùng READ COMMITTED với read consistency theo statement. Mỗi câu query nhìn thấy snapshot nhất quán tại thời điểm câu lệnh bắt đầu, thay vì một snapshot cố định cho toàn bộ transaction như một số người có thể kỳ vọng từ hệ quản trị khác.

Các tình huống cần test trên Oracle:

- Hai transaction cùng cập nhật một hàng.
- SELECT ... FOR UPDATE.
- NOWAIT và WAIT n.
- SKIP LOCKED.
- Unique constraint khi hai transaction insert cùng key.
- Deadlock giữa các bảng theo thứ tự lock khác nhau.
- Transaction đọc trong khi transaction khác cập nhật.
- Isolation SERIALIZABLE nếu ứng dụng sử dụng.

Ví dụ:

~~~sql
SELECT order_id,
       status
  FROM orders
 WHERE order_id = :order_id
 FOR UPDATE WAIT 5;
~~~

H2 có thể có kết quả khác về thời điểm block, lock timeout, deadlock và error code. Nếu ứng dụng xử lý hàng đợi bằng FOR UPDATE SKIP LOCKED, phải test trên Oracle.

### Không chỉ test bằng một connection

Một test repository chạy tuần tự không phát hiện race condition. Với luồng ghi quan trọng, cần dùng nhiều thread/connection thực sự, barrier/latch để điều phối và assert trạng thái cuối cùng trên Oracle.

Không dùng Thread.sleep() làm đồng bộ chính trong concurrency test. Dùng latch, barrier hoặc cơ chế đồng bộ xác định để test ổn định hơn.

## 12. LOB, JSON và kiểu dữ liệu chuyên biệt

Oracle có các kiểu và cách xử lý riêng:

- CLOB và NCLOB.
- BLOB.
- BFILE.
- RAW và LONG RAW trong hệ thống legacy.
- XMLTYPE theo phiên bản/option.
- JSON native hoặc JSON stored as text tùy release.
- INTERVAL.
- TIMESTAMP WITH TIME ZONE.

Mapping Hibernate/JDBC cần được test với dữ liệu thực tế:

- LOB lớn có được stream hay bị materialize toàn bộ vào memory?
- Unicode và national character set có giữ nguyên không?
- JSON constraint/function có compile không?
- BLOB có được đọc/ghi đúng kích thước không?
- JDBC driver có trả về đúng Java type không?

H2 có thể hỗ trợ một số kiểu tương tự nhưng không chứng minh locator, streaming, conversion và performance giống Oracle.

## 13. Migration schema: Flyway hoặc Liquibase

Nếu production schema được tạo bằng Flyway hoặc Liquibase, integration test với Oracle phải chạy chính các migration đó.

Ví dụ Flyway:

~~~yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Với cách này:

1. Database test khởi động ở trạng thái sạch.
2. Flyway chạy migration.
3. Hibernate kiểm tra mapping với schema đã tạo.
4. Test thực thi repository/service trên Oracle thật.
5. Dữ liệu test được rollback hoặc cleanup theo chiến lược riêng.

Không dùng ddl-auto: create-drop để thay thế migration production nếu mục tiêu là xác nhận migration. Hibernate DDL có thể tạo schema khác với script Flyway/Liquibase.

### Không để migration test và production lệch nhau

Các migration cần được version control và chạy giống nhau ở CI/staging/production. Không tạo một schema H2 riêng với DDL giản lược rồi xem đó là bằng chứng migration Oracle đúng.

Nếu dự án có migration riêng cho từng database, cần có test suite cho từng dialect/engine. Nếu chỉ hỗ trợ Oracle, nên để Oracle là engine chuẩn của integration test.

## 14. Cấu hình Spring Boot test dùng Oracle thật

Có thể chạy integration test với một Oracle database dành riêng cho test, chẳng hạn database ephemeral trong container hoặc database test được cấp riêng.

Ví dụ cấu hình test:

~~~yaml
spring:
  datasource:
    url: ${ORACLE_TEST_JDBC_URL}
    username: ${ORACLE_TEST_USERNAME}
    password: ${ORACLE_TEST_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
  jpa:
    hibernate:
      ddl-auto: validate
    open-in-view: false
  flyway:
    enabled: true
~~~

Các giá trị trên là placeholder được cấp từ CI secret hoặc cấu hình local an toàn. Không ghi password thật vào repository, test log hoặc file YAML được commit. Trong cấu hình thực tế, dùng cơ chế property placeholder/environment binding của Spring.

### Ngăn Spring thay DataSource bằng H2

@DataJpaTest có thể tự cấu hình embedded database nếu tìm thấy H2. Khi muốn test Oracle thật, cần tắt hành vi thay thế:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class OrderRepositoryOracleTest {
    // Repository tests use the configured Oracle DataSource.
}
~~~

Nếu không đặt Replace.NONE, test có thể âm thầm chạy H2 dù application test profile khai báo Oracle. Hãy xác nhận JDBC URL trong test context hoặc log startup.

### Integration test với Spring Boot

~~~java
@SpringBootTest
@ActiveProfiles("oracle-test")
class OrderServiceOracleIT {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void persistsOrderUsingOracleSchema() {
        Long id = orderService.createOrder("ORD-1001");

        Order stored = orderRepository.findById(id)
            .orElseThrow();

        assertThat(stored.getOrderCode()).isEqualTo("ORD-1001");
    }
}
~~~

Test này kiểm tra service/repository trên DataSource Oracle được cấu hình bởi profile. Đảm bảo profile không fallback về H2 khi thiếu biến môi trường.

## 15. Dùng Testcontainers để chạy Oracle trong CI

Testcontainers có thể tạo database container trong vòng đời test, giúp mỗi CI run có môi trường độc lập hơn. Với Oracle, cần chọn image Oracle Database được phép sử dụng, phiên bản phù hợp và module Testcontainers tương thích.

Một lựa chọn thường gặp cho test là Oracle XE image hoặc Oracle Database Free image. Image, version, biến môi trường, license/terms và giới hạn tính năng phải được xác nhận từ tài liệu của image/provider và Oracle trước khi dùng. XE/Free có giới hạn edition; không thay thế hoàn toàn Enterprise Edition production.

### Dependency minh họa

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>oracle-xe</artifactId>
    <scope>test</scope>
</dependency>
~~~

Version được quản lý bằng Testcontainers BOM tương thích với JDK và Spring Boot của dự án. Artifact/module và class container có thể thay đổi theo release Testcontainers; kiểm tra tài liệu version đang dùng trước khi copy code.

### Mẫu test với OracleContainer

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.OracleContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OracleDatabaseIntegrationTest {

    @Container
    static final OracleContainer ORACLE =
        new OracleContainer("gvenzl/oracle-xe:21-slim-faststart");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", ORACLE::getJdbcUrl);
        registry.add("spring.datasource.username", ORACLE::getUsername);
        registry.add("spring.datasource.password", ORACLE::getPassword);
    }

    @Test
    void applicationConnectsToOracle() {
        // Execute repository/service assertions against Oracle.
    }
}
~~~

Đây là mẫu minh họa dựa trên API OracleContainer thường được cung cấp bởi Testcontainers Oracle XE module và image tương ứng. Cần pin image tag, Testcontainers version và kiểm tra class/API theo dependency thực tế. Không dùng tag latest trong CI vì engine có thể thay đổi mà không có thay đổi source code.

Nếu môi trường CI không cho phép Docker-in-Docker hoặc không có Docker socket, dùng Oracle test database được cấp riêng và truyền URL/credential qua secret.

### Testcontainers và schema

Sau khi container sẵn sàng:

1. Tạo user/schema ứng dụng.
2. Tạo tablespace hoặc cấu hình quota nếu migration yêu cầu.
3. Chạy Flyway/Liquibase.
4. Chạy test.
5. Hủy container sau test.

Container mới giúp cách ly database giữa các pipeline, nhưng không tự động làm test song song an toàn nếu nhiều test class cùng chia sẻ một container/schema.

## 16. Dùng Oracle Free/XE và giới hạn edition

Oracle XE hoặc Oracle Database Free có thể hữu ích để chạy integration test cục bộ và CI với chi phí thấp hoặc miễn phí theo điều kiện sản phẩm. Tuy nhiên:

- Có giới hạn tài nguyên và tính năng theo edition.
- Một số option Enterprise hoặc HA không có sẵn.
- RAC/FAN/FCF behavior không thể được xác nhận chỉ bằng một instance XE đơn lẻ.
- Partitioning, advanced security, Data Guard hoặc feature khác có thể không có cùng khả năng như production.
- Cấu hình storage, memory, character set và parameter có thể khác.

Nếu production dùng Enterprise Edition với RAC, test Oracle Free/XE vẫn xác nhận được nhiều SQL, migration, JPA mapping và JDBC behavior cơ bản, nhưng không chứng minh RAC failover hoặc mọi option production.

Đối với tính năng edition-specific, cần test trên môi trường có feature tương ứng được cấp phép và cấu hình.

## 17. Test profile riêng và tránh fallback H2

Nên tách cấu hình rõ:

- application.yml: cấu hình mặc định theo môi trường.
- application-test.yml: H2 nếu dùng cho unit/repository test đơn giản.
- application-oracle-test.yml: Oracle test database.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: ${ORACLE_TEST_JDBC_URL}
    username: ${ORACLE_TEST_USERNAME}
    password: ${ORACLE_TEST_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
~~~

Kích hoạt profile:

~~~java
@ActiveProfiles("oracle-test")
~~~

Đặt guard để test Oracle thất bại rõ ràng khi thiếu URL/credential, thay vì tự chuyển sang H2. Một integration test được gắn tên Oracle nhưng chạy nhầm H2 tạo ra cảm giác an toàn giả.

Có thể assert database product trong test:

~~~java
@Autowired
DataSource dataSource;

@Test
void testUsesOracleDatabase() throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        String product =
            connection.getMetaData().getDatabaseProductName();

        assertThat(product).containsIgnoringCase("Oracle");
    }
}
~~~

Đây là guard đơn giản để xác nhận test đang dùng đúng engine.

## 18. Kiểm thử repository trên Oracle thật

Một repository test cần xác nhận cả SQL và mapping:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@ActiveProfiles("oracle-test")
class CustomerRepositoryOracleTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerByNormalizedCode() {
        Customer customer = new Customer();
        customer.setCustomerCode("CUS-001");
        customer.setCustomerName("Acme");
        repository.saveAndFlush(customer);

        Optional<Customer> found =
            repository.findByCustomerCode("CUS-001");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().getCustomerName())
            .isEqualTo("Acme");
    }
}
~~~

saveAndFlush() buộc Hibernate gửi SQL xuống database ngay trong test, giúp phát hiện constraint/type/SQL error sớm hơn việc chỉ gọi save(). Tuy nhiên, test cần đọc lại sau flush và clear persistence context để tránh chỉ nhận entity còn trong persistence context.

Ví dụ:

~~~java
repository.saveAndFlush(customer);
entityManager.clear();

Customer stored = repository.findById(customer.getId())
    .orElseThrow();
~~~

Khi test một native query, hãy gọi đúng repository method chứa native SQL trên Oracle, không thay bằng query khác chỉ dành cho H2.

## 19. Kiểm thử migration DDL

Migration cần được chạy trên Oracle thật từ trạng thái database sạch. Ví dụ:

~~~text
V1__create_customer.sql
V2__add_customer_status.sql
V3__create_customer_search_index.sql
~~~

Test cần xác nhận:

- Migration chạy theo đúng thứ tự.
- Object được tạo trong đúng schema.
- Datatype, precision, scale đúng.
- Constraint và index được tạo.
- Sequence/identity khớp entity mapping.
- View, trigger, package compile.
- Migration có thể nâng cấp từ schema phiên bản trước.
- Migration thất bại có log rõ và không để database ở trạng thái không thể hiểu.

Với Oracle, DDL implicit commit làm rollback behavior khác H2. Nếu migration giữa chừng thất bại, không giả định toàn bộ DDL trước đó đã được rollback. Flyway/Liquibase có tracking và behavior riêng; hãy đọc trạng thái migration và xây dựng recovery procedure.

Không chỉnh sửa migration đã được áp dụng ở môi trường chia sẻ. Tạo migration mới để sửa schema.

## 20. Test data và cleanup

Test data phải tái lập và không phụ thuộc thứ tự test.

Các cách thường dùng:

- @Sql để nạp dữ liệu fixture.
- Builder/factory Java để tạo entity.
- Flyway migration chỉ tạo schema và dữ liệu reference bất biến.
- Transaction rollback cho test chỉ thay đổi DML.
- Xóa dữ liệu theo test run ID hoặc schema riêng.
- Tạo schema/container riêng cho từng worker khi chạy song song.

### Transaction rollback

@DataJpaTest thường chạy trong transaction và rollback sau mỗi test. Điều này hữu ích cho DML nhưng không hoàn tác Oracle DDL. Sequence value cũng không được trả lại khi transaction rollback.

Không assert rằng sequence luôn bắt đầu từ 1 hoặc không có khoảng trống. Nếu test phụ thuộc ID cố định, tạo dữ liệu bằng ID được chỉ định trong fixture hoặc query ID vừa tạo.

### TRUNCATE không phải cleanup transactional

Oracle TRUNCATE TABLE là DDL và implicit commit. Không dùng TRUNCATE trong một test transaction rồi kỳ vọng rollback khôi phục dữ liệu.

Nếu dùng cleanup script:

- Chạy ở schema/database riêng.
- Kiểm tra foreign key dependency.
- Thực hiện ngoài transaction test hoặc theo lifecycle rõ ràng.
- Không trỏ test cleanup vào production.

## 21. Kiểm thử transaction rollback và propagation

Test trên Oracle thật các tình huống:

- Exception runtime làm rollback.
- Checked exception theo cấu hình rollback rule.
- REQUIRES_NEW commit độc lập.
- NESTED nếu transaction manager/driver hỗ trợ đúng semantics.
- Constraint violation.
- Deadlock hoặc lock timeout.
- Giao dịch cập nhật nhiều bảng.

Ví dụ:

~~~java
@Test
void rollsBackOrderWhenAuditInsertFails() {
    assertThatThrownBy(() ->
        orderService.createOrderWithAudit("ORD-ROLLBACK")
    ).isInstanceOf(RuntimeException.class);

    assertThat(orderRepository.existsByOrderCode("ORD-ROLLBACK"))
        .isFalse();
}
~~~

Test method có thể đang nằm trong transaction riêng của test framework. Nếu service dùng propagation khác, cần hiểu transaction nào đang được commit/rollback và kiểm tra dữ liệu bằng connection/context độc lập khi cần.

Một test chỉ assert exception không chứng minh dữ liệu đã rollback. Đọc lại database sau khi transaction kết thúc.

## 22. Kiểm thử locking và race condition

Nếu ứng dụng có nghiệp vụ giữ chỗ, thanh toán, phân bổ tồn kho hoặc xử lý queue, cần test concurrency với Oracle thật.

Ví dụ SQL locking:

~~~sql
SELECT inventory_id,
       available_quantity
  FROM inventory
 WHERE inventory_id = :id
 FOR UPDATE;
~~~

Test nên tạo hai transaction độc lập:

1. Transaction A lock hàng.
2. Transaction B cố gắng cập nhật cùng hàng.
3. Xác nhận B chờ, timeout hoặc nhận lỗi theo cấu hình.
4. A commit/rollback.
5. Xác nhận B tiếp tục hoặc thất bại theo expected behavior.

Không dùng cùng một EntityManager hoặc Connection cho hai thread. Mỗi transaction cần tài nguyên riêng.

Với test SKIP LOCKED, xác nhận hai worker không nhận cùng một record. Với unique constraint, xác nhận một trong hai insert cạnh tranh bị từ chối hoặc retry đúng quy tắc.

## 23. Kiểm thử native SQL và Hibernate dialect

Hibernate dialect quyết định SQL được sinh ra cho pagination, sequence, identity, locking và một số function. Phiên bản Hibernate/Spring Boot có thể thay đổi dialect class và SQL generation.

Trong Hibernate hiện đại, dialect Oracle thường được tự nhận diện từ JDBC metadata. Nếu cần khai báo tường minh, dùng dialect phù hợp với Hibernate version đang chạy, không copy class cũ như Oracle12cDialect nếu version hiện tại đã thay đổi.

Kiểm tra:

- SQL pagination.
- Sequence generation.
- SELECT FOR UPDATE.
- Bulk update/delete.
- RETURNING hoặc generated key nếu ứng dụng dùng.
- Native query có hint.
- Function và operator Oracle-specific.

Bật SQL logging ở test khi cần điều tra:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Bind logging có thể lộ dữ liệu nhạy cảm. Chỉ bật tạm ở môi trường test và không ghi credential/PII vào log CI.

## 24. Kiểm thử quyền thực tế

Test bằng user DBA có thể che giấu lỗi privilege. Nên tạo application schema/user và integration account giống production:

- User chạy ứng dụng chỉ có quyền cần thiết.
- Migration user có quyền DDL theo quy trình riêng.
- Application runtime user không cần quyền tạo table nếu migration chạy bằng user khác.
- Read-only integration user chỉ được đọc view cần thiết.
- Không dùng SYS, SYSTEM hoặc DBA role cho test application thông thường.

Một cách triển khai phổ biến:

| User | Vai trò |
|---|---|
| APP_OWNER | Sở hữu table, sequence, view và package |
| APP_MIGRATOR | Chạy migration trong cửa sổ triển khai |
| APP_RUNTIME | Quyền DML/EXECUTE cần thiết cho ứng dụng |
| APP_TEST_READER | Đọc view/API phục vụ kiểm thử tích hợp |

Tùy cách triển khai, user owner và runtime có thể là một user, nhưng test nên phản ánh đúng mô hình production để phát hiện lỗi quyền.

## 25. Kiểm tra character set và Unicode

H2 và Oracle có thể khác nhau về encoding, collation và so sánh chuỗi. Oracle database có database character set và national character set. Kiểm tra:

~~~sql
SELECT parameter,
       value
  FROM nls_database_parameters
 WHERE parameter IN (
   'NLS_CHARACTERSET',
   'NLS_NCHAR_CHARACTERSET'
 );
~~~

Test với:

- Tiếng Việt có dấu.
- Ký tự kết hợp Unicode.
- Emoji nếu hệ thống hỗ trợ.
- Ký tự ngoài Basic Multilingual Plane.
- Chuỗi dài sát giới hạn cột.
- So sánh không phân biệt hoa/thường nếu nghiệp vụ cần.

Không giả định VARCHAR2 và NVARCHAR2 có cùng giới hạn byte/character hoặc cùng semantics. Chọn kiểu cột dựa trên database character set và yêu cầu dữ liệu.

## 26. Kiểm thử thời gian và NLS session

Oracle session có thể có các NLS setting khác nhau. Test chỉ chạy với một session mặc định có thể bỏ sót lỗi implicit conversion.

Kiểm tra session:

~~~sql
SELECT parameter,
       value
  FROM nls_session_parameters
 ORDER BY parameter;
~~~

Các tình huống nên thử:

- Date format khác nhau.
- Decimal separator khác nhau.
- Time zone session khác database timezone.
- Daylight saving transition.
- Timestamp có fractional seconds.
- TIMESTAMP WITH LOCAL TIME ZONE đọc ở hai session timezone.

Ưu tiên bind parameter typed thay vì chuyển date/number thành string rồi ghép vào SQL.

## 27. Kiểm thử hiệu năng và giới hạn tài nguyên

Integration test functional với Oracle Free/XE có thể xác nhận tính đúng, nhưng không đại diện hiệu năng production. Edition, CPU, memory, storage, concurrency và cấu hình database khác nhau.

Performance test nên dùng môi trường gần production:

- Cùng major Oracle version và tương thích patch.
- Cùng kiểu storage hoặc đặc tính I/O tương đương.
- Cùng connection pool và JDBC driver.
- Dữ liệu có phân bố và kích thước thực tế đã được làm sạch/mask.
- Concurrency và think time gần workload thật.
- Warm-up và measurement tách biệt.

Không đo benchmark bằng một container đơn lẻ rồi suy ra số connection tối ưu cho RAC production.

## 28. CI pipeline cho Oracle integration test

Một pipeline điển hình:

~~~text
Compile
  |
  v
Unit tests
  |
  v
Build application
  |
  v
Start disposable Oracle
  |
  v
Create application schema
  |
  v
Run Flyway/Liquibase migrations
  |
  v
Run Oracle integration tests
  |
  v
Collect logs and test reports
  |
  v
Destroy disposable database
~~~

Các nguyên tắc:

- Pin Oracle image tag và dependency version.
- Không dùng tag latest.
- Chờ database thật sự sẵn sàng, không chỉ container đang running.
- Dùng healthcheck hoặc wait strategy phù hợp.
- Mỗi CI run có database/schema cô lập.
- Không dùng dữ liệu production chưa được mask.
- Giữ log startup, migration và Oracle alert log khi test thất bại.
- Giới hạn số job Oracle chạy song song theo tài nguyên CI.
- Thu dọn container/volume sau khi job hoàn tất.

Nếu Oracle startup mất nhiều thời gian, có thể tái sử dụng service container trong một job CI hoặc dùng database test được quản lý. Đổi lại, phải có cleanup dữ liệu và isolation giữa pipeline.

## 29. Phân tầng test trong dự án Spring Boot

Không cần chạy toàn bộ test suite trên Oracle nếu test chỉ kiểm tra logic thuần Java. Một cấu trúc hợp lý:

| Nhóm test | Công cụ | Mục tiêu |
|---|---|---|
| Unit | JUnit, Mockito | Logic nghiệp vụ, validation, mapping thuần |
| Web slice | @WebMvcTest | Controller, serialization, HTTP contract |
| Repository slice nhanh | H2 nếu query portable | Test cơ bản, feedback nhanh |
| Repository Oracle | Oracle Testcontainers/test DB | SQL, mapping, constraint, sequence và dialect |
| Service integration | Oracle + Spring context | Transaction, JPA, JDBC và migration |
| End-to-end | Môi trường tích hợp | Kết nối service, queue, API và workflow |
| Performance/concurrency | Oracle gần production | Throughput, lock, pool, query plan |

Nếu dự án dùng nhiều native query hoặc PL/SQL, tỷ trọng test Oracle phải đủ lớn để bao phủ các phần phụ thuộc engine. H2 vẫn có thể giữ vai trò test nhanh cho phần portable.

## 30. Các lỗi thường gặp khi chuyển test từ H2 sang Oracle

| Lỗi | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| ORA-00904 invalid identifier | Tên cột, case, alias hoặc SQL dialect | Đọc SQL sinh ra, kiểm tra dictionary |
| ORA-00933 SQL command not properly ended | Cú pháp SQL không đúng Oracle | Tìm LIMIT, quoting hoặc syntax riêng engine |
| ORA-00942 table or view does not exist | Sai schema, thiếu grant, object chưa được tạo | Kiểm tra user, schema, synonym và migration |
| ORA-01400 cannot insert NULL | Entity không set giá trị hoặc empty string thành NULL | Kiểm tra mapping, validation và dữ liệu |
| ORA-00001 unique constraint violated | Sequence/ID hoặc dữ liệu trùng | Kiểm tra generator, seed và constraint |
| ORA-02291 parent key not found | Thiếu parent row hoặc thứ tự insert | Kiểm tra fixture, cascade và FK |
| ORA-02292 child record found | Delete parent còn child | Kiểm tra thứ tự cleanup và cascade |
| ORA-01861 literal does not match format string | Date string/implicit conversion | Dùng bind parameter hoặc format rõ |
| ORA-01555 snapshot too old | Undo không đủ cho query/export dài | Kiểm tra undo và thời gian transaction |
| ORA-00054 resource busy | Lock/DDL cạnh tranh | Kiểm tra transaction, lock timeout và test parallel |

Không sửa bằng cách nới quyền hoặc bỏ constraint trước khi hiểu nguyên nhân. Một test H2 xanh không phải bằng chứng schema Oracle đã đúng.

## 31. Ví dụ kiểm tra SQL sinh ra và kết quả Oracle

Khi repository query lỗi:

1. Bật Hibernate SQL log trong profile test.
2. Ghi nhận bind type/value ở môi trường test an toàn.
3. Chạy SQL tương ứng trực tiếp trên Oracle test.
4. Xác nhận current schema, service, NLS và privilege.
5. Kiểm tra execution plan nếu query chạy nhưng chậm.
6. Sửa query hoặc mapping ở tầng đúng.
7. Giữ integration test Oracle để ngăn lỗi quay lại.

Không thay query Oracle bằng một query H2-only trong cùng test method. Nếu cần hai engine, tách test contract theo profile và ghi rõ phần nào portable, phần nào database-specific.

## 32. Checklist kiểm thử tích hợp Oracle

### Môi trường

- [ ] Xác nhận JDBC URL trỏ đúng Oracle service/PDB.
- [ ] Test không tự fallback sang H2.
- [ ] Pin Oracle image/database version.
- [ ] Dùng schema/user riêng cho test.
- [ ] Không sử dụng dữ liệu production chưa được mask.
- [ ] Ghi nhận database product/version khi test bắt đầu.

### Schema và migration

- [ ] Chạy Flyway/Liquibase migrations trên Oracle.
- [ ] Dùng ddl-auto=validate khi migration là nguồn tạo schema.
- [ ] Kiểm tra datatype, precision, scale và nullability.
- [ ] Kiểm tra sequence/identity và allocation size.
- [ ] Kiểm tra index, constraint, trigger, view và PL/SQL.
- [ ] Xác nhận migration failure/recovery behavior.

### Repository và transaction

- [ ] Test native SQL và pagination.
- [ ] Test empty string/NULL.
- [ ] Test DATE/TIMESTAMP/timezone.
- [ ] Test LOB/Unicode/NUMBER nếu có.
- [ ] Test rollback, propagation và constraint error.
- [ ] Test locking/concurrency cho nghiệp vụ quan trọng.
- [ ] Test bằng runtime user có quyền tương tự production.

### CI và vận hành

- [ ] Chờ Oracle sẵn sàng trước khi chạy migration.
- [ ] Cô lập database/schema giữa pipeline.
- [ ] Thu log migration, Hibernate và Oracle khi fail.
- [ ] Dọn container/volume theo lifecycle.
- [ ] Tách functional test khỏi performance test.
- [ ] Không coi XE/Free là bằng chứng cho RAC hoặc option production.

## 33. Kết luận

H2 với Oracle mode hữu ích cho feedback nhanh, nhưng chỉ mô phỏng một phần cú pháp và hành vi. Oracle có khác biệt quan trọng về chuỗi rỗng/NULL, identifier, DATE/TIMESTAMP, NUMBER, sequence, PL/SQL, native SQL, DDL implicit commit, transaction isolation và locking. Những khác biệt này có thể làm test H2 xanh nhưng ứng dụng lỗi trên production.

Với Spring Boot/JPA, hãy giữ unit test nhanh, dùng H2 cho phần SQL portable và bổ sung integration test trên Oracle thật cho migration, repository, native query, transaction, sequence, quyền và concurrency. Oracle Testcontainers hoặc một database test cô lập có thể cung cấp môi trường lặp lại; pin version, chạy đúng Flyway/Liquibase và tránh fallback H2. Dùng Oracle Free/XE để kiểm tra engine cơ bản, nhưng kiểm thử RAC, Active Data Guard hoặc option production-specific trên môi trường có cấu hình tương ứng.

Khi test thất bại, kiểm tra SQL sinh ra, bind type, schema, service, NLS, privilege và Oracle error code. Mục tiêu là xác nhận ứng dụng hoạt động trên đúng engine mà production sử dụng, không chỉ trên một database tương thích cú pháp.
