# Khác biệt khi thay MySQL bằng H2 hoặc database giả lập

H2 và database giả lập giúp kiểm thử nhanh, nhưng chúng không tái hiện đầy đủ hành vi của MySQL. H2 là một hệ quản trị cơ sở dữ liệu khác, có cú pháp tương thích một phần; mock repository hoặc JDBC chỉ mô phỏng lời gọi trong mã Java và không thực thi SQL. Vì vậy, một bài test chạy xanh trên H2 hoặc mock vẫn có thể thất bại khi chạy trên MySQL do khác biệt về kiểu dữ liệu, collation, SQL mode, khóa, transaction, optimizer hoặc DDL.

Bài học này thuộc chương **Kiểm thử** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, kiểm thử cần xác nhận hành vi trên đúng database mà ứng dụng sẽ sử dụng. Bài này phân biệt phạm vi của mock, H2 và MySQL thật, đồng thời hướng dẫn chọn công cụ theo loại rủi ro cần kiểm tra.

## 1. Ba loại môi trường kiểm thử không tương đương

| Môi trường | Thực thi SQL? | Điều kiểm tra tốt | Điều không chứng minh được |
|---|---|---|---|
| Mock bằng Mockito hoặc fake repository | Không | Logic service, nhánh xử lý, phản ứng với kết quả/lỗi giả lập | SQL hợp lệ, mapping JPA, constraint, transaction, lock và hành vi MySQL |
| H2 in-memory | Có, bằng engine H2 | Repository đơn giản, mapping cơ bản, truy vấn SQL portable, kiểm thử nhanh | Tương thích hoàn toàn với MySQL, collation, SQL mode, optimizer, DDL và concurrency của InnoDB |
| MySQL thật hoặc MySQL Testcontainers | Có, bằng MySQL Server | SQL, schema, migration, kiểu dữ liệu, constraint, transaction, lock, driver và hành vi server | Tự động chứng minh production an toàn nếu cấu hình, dữ liệu và tải thử khác production |

Chọn môi trường theo câu hỏi của bài test:

- Nếu cần kiểm tra service gọi repository đúng với tham số nào, mock có thể đủ.
- Nếu cần kiểm tra một mapping JPA đơn giản hoặc truy vấn portable nhanh, H2 có thể hữu ích.
- Nếu cần xác nhận MySQL có chấp nhận DDL/SQL, áp dụng collation, enforce foreign key, cấp AUTO_INCREMENT, xử lý transaction hoặc chọn plan như mong đợi, hãy chạy MySQL thật.

Một test không cần kiểm tra mọi thứ cùng lúc. Hãy phân lớp test để có tốc độ phản hồi nhanh mà vẫn có bằng chứng tương thích với MySQL ở các ranh giới quan trọng.

## 2. Mock database không phải database

Mock là một đối tượng giả thay thế dependency trong mã Java. Ví dụ, service gọi `CustomerRepository.findByEmail()`; test có thể cấu hình mock trả về một customer hoặc ném exception.

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {
    @Mock
    private CustomerRepository customerRepository;

    @InjectMocks
    private CustomerService customerService;

    @Test
    void returnsCustomerWhenEmailExists() {
        Customer customer = new Customer();
        customer.setEmail("linh@example.com");

        when(customerRepository.findByEmail("linh@example.com"))
            .thenReturn(Optional.of(customer));

        Customer result =
            customerService.findByEmail("linh@example.com");

        assertEquals("linh@example.com", result.getEmail());
        verify(customerRepository).findByEmail("linh@example.com");
    }
}
~~~

Test này kiểm tra logic service và hợp đồng gọi repository. Nó không chạy câu SQL, không khởi tạo Hibernate, không kiểm tra tên cột, không enforce unique key và cũng không chứng minh phương thức repository có thể truy vấn được MySQL.

Nếu mock repository trả về kết quả mong muốn, test vẫn xanh ngay cả khi:

- JPQL tham chiếu sai tên thuộc tính hoặc SQL native sai tên cột.
- Entity mapping sai kiểu `BIGINT UNSIGNED`, `DECIMAL`, `JSON` hoặc timestamp.
- Migration chưa tạo index/constraint cần thiết.
- Query thực tế vi phạm SQL mode hoặc cú pháp MySQL.
- Foreign key từ chối insert.
- Transaction rollback hoặc deadlock khác với giả định của service.

Không dùng mock để kiểm tra database semantics. Dùng nó cho logic ứng dụng nằm phía trên repository, nơi mục tiêu là kiểm tra cách service phản ứng với kết quả và lỗi mà dependency có thể trả về.

### Fake repository cũng có giới hạn

Một fake repository có thể lưu object trong Map hoặc List để test service mà không cần mock framework. Cách này có thể làm test dễ đọc, nhưng fake chỉ mô phỏng hành vi do người viết định nghĩa. Nếu fake tự kiểm tra uniqueness hoặc quan hệ theo logic Java, nó vẫn không chứng minh MySQL thực thi constraint giống như vậy.

Hãy giữ fake đơn giản và chỉ mô phỏng hợp đồng cần thiết. Không xây một “MySQL giả” trong mã test bằng cách viết lại optimizer, transaction hoặc constraint engine.

## 3. H2 MySQL compatibility mode chỉ tương thích một phần

H2 có chế độ tương thích MySQL, thường bật qua JDBC URL:

~~~text
jdbc:h2:mem:testdb;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1
~~~

- `MODE=MySQL` yêu cầu H2 mô phỏng một số hành vi/cú pháp của MySQL.
- `DATABASE_TO_LOWER=TRUE` điều khiển cách H2 lưu tên identifier không đặt trong dấu quote; lựa chọn này có thể giúp tránh một số khác biệt chữ hoa/chữ thường trong test.
- `DB_CLOSE_DELAY=-1` giữ database in-memory tồn tại sau khi connection cuối cùng đóng, cho đến khi JVM kết thúc hoặc database được đóng rõ ràng.

Các tùy chọn trên chỉ điều chỉnh hành vi của H2. Chúng không cài MySQL Server, không sử dụng InnoDB, không thay optimizer của H2 bằng MySQL optimizer và không làm cho mọi cú pháp/kiểu dữ liệu MySQL trở nên tương đương.

H2 có thể chấp nhận một phần cú pháp MySQL nhưng vẫn khác về:

- Quy tắc so sánh chuỗi và collation.
- Kiểu số unsigned, JSON, ENUM, SET và các kiểu mở rộng.
- AUTO_INCREMENT/identity và cách cấp ID.
- Hàm built-in, toán tử, cú pháp upsert và DDL.
- Transaction isolation, lock và deadlock.
- Metadata trong information_schema.
- Index, execution plan và thống kê optimizer.
- SQL mode, implicit conversion và warning.

Chế độ tương thích là công cụ hỗ trợ chạy một số ứng dụng SQL đơn giản trên H2. Không dùng nó làm bằng chứng rằng ứng dụng đã tương thích với MySQL.

## 4. Khác biệt về kiểu dữ liệu và chuyển đổi

Kiểu dữ liệu là một trong những nguồn lỗi phổ biến nhất khi thay MySQL bằng H2.

| Khả năng của MySQL | Rủi ro khi kiểm thử bằng H2 |
|---|---|
| `BIGINT UNSIGNED` | Miền giá trị có thể khác; Java `long` cũng không biểu diễn hết miền unsigned 64-bit |
| `DECIMAL(p,s)` | Quy tắc chuyển đổi, làm tròn và ép kiểu cần được kiểm tra trên MySQL |
| `JSON` và JSON functions | H2 không có cùng cách lưu trữ và tập hàm JSON như MySQL |
| `ENUM`, `SET` | Kiểu và quy tắc kiểm tra giá trị có thể không tương đương |
| `TIMESTAMP`, `DATETIME` | Chuyển đổi timezone và độ chính xác thời gian có thể khác |
| Generated columns | Cú pháp, biểu thức và index phụ thuộc MySQL |
| Spatial types | Hàm và index không nhất thiết tương đương |
| Character set/collation | So sánh, uniqueness và sort order có thể khác |

Ví dụ MySQL dùng kiểu unsigned và JSON:

~~~sql
CREATE TABLE api_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  payload JSON NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id)
) ENGINE=InnoDB;
~~~

Một test H2 có thể phải đổi schema hoặc kiểu cột để chạy được. Khi đó test đang xác minh một schema khác với schema production. Điều này đặc biệt nguy hiểm nếu test vẫn được xem như bằng chứng cho migration hoặc mapping JPA.

Với `DECIMAL`, hãy kiểm tra cả precision và scale. Ví dụ cột `DECIMAL(12,2)` có thể lưu giá trị tiền tệ với hai chữ số thập phân; test cần xác minh giá trị được ghi và đọc đúng, không bị chuyển sang floating point hoặc làm tròn ngoài quy tắc nghiệp vụ.

Với `BIGINT UNSIGNED`, kiểm tra miền giá trị thật sự mà hệ thống sử dụng. Nếu dữ liệu có thể vượt `Long.MAX_VALUE`, Java `long` không đủ; cần quy ước biểu diễn như `BigInteger` và kiểm thử chuyển đổi với Connector/J.

## 5. Collation, charset và quy tắc so sánh chuỗi

MySQL thường dùng collation không phân biệt hoa/thường cho nhiều schema. Ví dụ một collation có hậu tố `_ci` có thể coi `Linh@example.com` và `linh@example.com` là bằng nhau. Một collation có hậu tố `_ai` có thể bỏ qua khác biệt dấu trong so sánh.

Điều này ảnh hưởng trực tiếp đến:

- Kết quả `WHERE email = ?`.
- `ORDER BY` và `GROUP BY`.
- Unique index và duplicate key.
- Join trên cột chuỗi.
- Phân trang theo giá trị chuỗi.

Ví dụ MySQL:

~~~sql
CREATE TABLE accounts (
  email VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NOT NULL,
  PRIMARY KEY (email)
) ENGINE=InnoDB;
~~~

Với collation trên, hai email chỉ khác hoa/thường có thể xung đột khóa chính. Nếu H2 test dùng phép so sánh khác, test có thể cho phép insert cả hai hàng và vẫn xanh, trong khi MySQL từ chối hàng thứ hai.

Kiểm thử uniqueness trên MySQL:

~~~sql
INSERT INTO accounts (email)
VALUES ('Linh@example.com');

-- Dự kiến duplicate key theo collation đã chọn
INSERT INTO accounts (email)
VALUES ('linh@example.com');
~~~

Không kết luận email luôn phải không phân biệt hoa/thường; đó là quy tắc nghiệp vụ cần quyết định. Điểm quan trọng là test phải dùng đúng charset/collation của schema đích.

Tên bảng cũng có thể khác hành vi theo hệ điều hành và cấu hình `lower_case_table_names`. Trên một số hệ thống Linux, tên bảng phân biệt hoa/thường; trên môi trường khác có thể không. H2 có quy tắc chuẩn hóa identifier riêng. Dùng đúng cách viết tên bảng/cột trong entity, native query và migration, rồi kiểm tra trên MySQL với cấu hình gần production.

## 6. SQL mode và cú pháp riêng của MySQL

SQL mode điều khiển cách MySQL xử lý giá trị ngoài miền, ngày không hợp lệ, GROUP BY và các trường hợp khác. H2 không tái tạo đầy đủ các SQL mode của MySQL.

Ví dụ, MySQL với `ONLY_FULL_GROUP_BY` có thể từ chối một truy vấn chọn cột không nằm trong GROUP BY và không phụ thuộc hàm vào cột nhóm. Một test H2 có thể chấp nhận truy vấn hoặc xử lý khác, vì vậy test đó không chứng minh query hợp lệ theo SQL mode production.

Một số cú pháp/hàm đặc thù cần chạy trên MySQL:

- `INSERT ... ON DUPLICATE KEY UPDATE`.
- `INSERT IGNORE` và `REPLACE`.
- `LAST_INSERT_ID()`.
- `GROUP_CONCAT()`.
- Hàm JSON của MySQL.
- `LOAD DATA [LOCAL] INFILE`.
- Cú pháp index, generated column, partition và DDL riêng của MySQL.

Ví dụ upsert:

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-001', 10)
ON DUPLICATE KEY UPDATE
  quantity = quantity + VALUES(quantity);
~~~

Cú pháp và cảnh báo deprecation của biểu thức có thể phụ thuộc phiên bản MySQL. Hãy kiểm thử với đúng phiên bản server mục tiêu và dùng cú pháp được hỗ trợ cho phiên bản đó. H2 MySQL mode không phải oracle cho hành vi upsert của MySQL.

Khi test, ghi nhận `@@SESSION.sql_mode` và các thiết lập liên quan. Nếu production bật strict mode, test MySQL cũng nên chạy với mode tương ứng; nếu test container dùng mặc định khác, kết quả có thể vẫn lệch.

## 7. Constraint và hành vi khóa

MySQL InnoDB enforce PRIMARY KEY, UNIQUE, FOREIGN KEY, NOT NULL và các ràng buộc CHECK theo phiên bản. Một fake repository không enforce bất kỳ constraint database nào trừ khi người viết fake tự mô phỏng. H2 có constraint engine riêng và có thể khác ở cú pháp, thời điểm kiểm tra hoặc chi tiết thực thi.

Ví dụ, nếu entity có quan hệ `Order.customer`, test mock có thể lưu một Order tham chiếu tới Customer ID không tồn tại. MySQL với foreign key sẽ từ chối INSERT:

~~~sql
CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (id),
  KEY idx_orders_customer_id (customer_id),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;
~~~

Kiểm tra foreign key phải được thực hiện trên MySQL thật nếu ứng dụng dựa vào tính toàn vẹn do InnoDB bảo vệ. Không chỉ kiểm tra object graph Java vì dữ liệu có thể được ghi qua native SQL, batch job hoặc ứng dụng khác.

MySQL InnoDB còn có row lock, gap lock và next-key lock tùy isolation level, index và câu truy vấn. H2 không tái hiện chính xác cơ chế locking của InnoDB. Một test H2 chạy hai transaction không deadlock không chứng minh MySQL sẽ không deadlock.

## 8. Transaction, isolation và concurrency

MySQL InnoDB mặc định dùng REPEATABLE READ trong nhiều cấu hình phổ biến. H2 có mặc định isolation khác và cách triển khai lock khác. Khi test transaction, cần biết đang kiểm tra điều gì:

- Rollback có hoàn tác DML hay không?
- Transaction thứ hai có nhìn thấy dữ liệu chưa commit không?
- Hai transaction cùng cập nhật một hàng xử lý ra sao?
- Có deadlock hoặc lock wait timeout không?
- Unique/foreign key violation xuất hiện ở thời điểm nào?
- Connection pool có trả connection với transaction đã kết thúc không?

Không dùng H2 để xác nhận chính xác hành vi lock của InnoDB. Với bài test concurrency, dùng MySQL thật, hai connection độc lập và đồng bộ thời điểm thực thi bằng latch/barrier thay vì dựa vào `Thread.sleep()`.

Ví dụ nguyên tắc test hai transaction:

~~~text
Thread A                         Thread B
   |                                |
   | BEGIN                          | BEGIN
   | UPDATE account id=1            |
   |                                | UPDATE account id=1
   | giữ row lock                   | chờ lock
   | COMMIT                         |
   |                                | tiếp tục hoặc timeout
   v                                v
Đối chiếu kết quả, thời gian chờ và lỗi MySQL
~~~

Dùng hai physical connections để hai thread thực sự là hai session MySQL. Nếu test framework mở transaction ở test thread và repository dùng cùng transaction-bound connection, hai lời gọi có thể không tạo ra concurrency như mong muốn.

Với Spring, test có `@Transactional` thường được rollback khi kết thúc. Điều đó hữu ích để cô lập dữ liệu, nhưng không tự kiểm tra được mọi hành vi sau commit, transaction synchronization hoặc tương tác giữa nhiều transaction. Các test cần commit thật nên điều khiển transaction rõ ràng bằng `TransactionTemplate`, transaction manager hoặc các connection riêng; sau đó dọn dữ liệu có kiểm soát.

## 9. Index và execution plan không thể suy ra từ H2

Cùng một câu SQL và index có thể tạo plan khác trên H2 và MySQL. Hai engine có optimizer, thống kê, cost model và cách lưu trữ khác nhau.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);

EXPLAIN
SELECT id, total_amount
FROM orders
WHERE customer_id = 1001
ORDER BY created_at DESC
LIMIT 20;
~~~

Plan H2 không chứng minh MySQL sẽ dùng index đó. Để kiểm tra MySQL:

~~~sql
EXPLAIN FORMAT=JSON
SELECT id, total_amount
FROM orders
WHERE customer_id = 1001
ORDER BY created_at DESC
LIMIT 20;
~~~

Trên MySQL 8.0.18 trở lên, có thể dùng `EXPLAIN ANALYZE` cho truy vấn đọc an toàn để xem thời gian và số hàng thực tế ở các iterator. Đánh giá plan trên dữ liệu có phân bố gần production; bảng chỉ có vài hàng không đại diện cho bảng hàng triệu bản ghi.

Các yếu tố làm plan khác nhau gồm:

- Kích thước bảng và phân bố dữ liệu.
- Cardinality của index và histogram.
- Thứ tự cột trong composite index.
- Collation và kiểu dữ liệu của điều kiện join.
- LIMIT, ORDER BY, GROUP BY và subquery.
- Thống kê optimizer và phiên bản MySQL.

Dùng H2 để test logic kết quả truy vấn portable; dùng MySQL để kiểm tra plan và hiệu năng MySQL.

## 10. DDL, migration và stored program

Migration có thể chạy thành công trên H2 nhưng thất bại trên MySQL do khác cú pháp hoặc khác semantics:

- Kiểu `JSON`, `ENUM`, `UNSIGNED` hoặc generated column.
- Cú pháp index và foreign key.
- `AUTO_INCREMENT` và default expression.
- Stored procedure, function, trigger và event.
- `DEFINER`, `SQL SECURITY` và quyền.
- Partitioning, tablespace và online DDL.
- Implicit commit và metadata lock.

MySQL có quy tắc implicit commit với nhiều lệnh DDL. H2 có transaction/DDL behavior riêng. Một migration runner có thể thực thi các file theo cách khác nhau trên hai engine; test H2 không xác nhận migration sẽ chạy đúng trên MySQL.

Nếu ứng dụng dùng Flyway hoặc Liquibase, chạy migration trên MySQL trong CI. Xác minh cả đường đi từ database rỗng và đường nâng cấp từ schema phiên bản trước. Không dùng H2 làm bước duy nhất để kiểm tra DDL production.

Ví dụ kiểm tra schema sau migration:

~~~sql
SHOW CREATE TABLE orders;
SHOW INDEX FROM orders;
SELECT
  TABLE_NAME,
  CONSTRAINT_NAME,
  CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE();
~~~

Các truy vấn metadata nên được chạy trên MySQL mục tiêu vì schema và cột trong information_schema có thể khác engine.

## 11. Kiểm thử repository với MySQL Testcontainers

Testcontainers khởi chạy MySQL Server trong container dùng cho test. Bài test gửi SQL qua Connector/J thật và có thể chạy migration, Hibernate, constraint, transaction và query như trên MySQL.

Ví dụ dưới đây dùng Spring Boot 3.1 trở lên với service connection:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class CustomerRepositoryMySqlTest {

    @Container
    @ServiceConnection
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4.4")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void enforcesUniqueEmailUsingMySqlCollation() {
        customerRepository.saveAndFlush(
            new Customer("Linh@example.com")
        );

        assertThrows(
            DataIntegrityViolationException.class,
            () -> customerRepository.saveAndFlush(
                new Customer("linh@example.com")
            )
        );
    }
}
~~~

Các import chính trong ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertThrows;
~~~

Để ví dụ kiểm tra collation có ý nghĩa, migration tạo cột email phải khai báo collation không phân biệt hoa/thường, chẳng hạn collation phù hợp với MySQL 8.4. Nếu cột dùng collation phân biệt hoa/thường, kết quả mong đợi phải được điều chỉnh theo schema thực tế.

Các annotation và dependency:

- `@Testcontainers` bật lifecycle tích hợp Testcontainers cho test.
- `@Container` quản lý vòng đời container.
- `@ServiceConnection` (Spring Boot 3.1+) cung cấp thông tin kết nối container cho auto-configuration.
- `@AutoConfigureTestDatabase(replace = NONE)` ngăn `@DataJpaTest` thay DataSource MySQL bằng embedded database.
- `MySQLContainer` cung cấp MySQL Server và JDBC URL động.

Thêm các dependency test tương ứng do Spring Boot quản lý version:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-testcontainers</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>mysql</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>junit-jupiter</artifactId>
  <scope>test</scope>
</dependency>
~~~

Cần có Docker runtime hoạt động trên máy chạy test hoặc CI runner. Nếu dùng Spring Boot cũ chưa có `@ServiceConnection`, có thể đăng ký URL, username và password bằng `@DynamicPropertySource`:

~~~java
@DynamicPropertySource
static void datasourceProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", mysql::getJdbcUrl);
    registry.add("spring.datasource.username", mysql::getUsername);
    registry.add("spring.datasource.password", mysql::getPassword);
}
~~~

Dù dùng cách nào, xác nhận test thực sự kết nối MySQL bằng cách kiểm tra `SELECT VERSION()` hoặc JDBC metadata. Không chỉ dựa vào tên class container.

## 12. Chọn phiên bản và cấu hình container giống production

Test trên MySQL 8.4 không tự động chứng minh ứng dụng tương thích với mọi MySQL 8.0.x hoặc một dịch vụ managed database có cấu hình khác. Ví dụ container dùng tag patch `8.4.4` để minh họa việc pin phiên bản; hãy thay bằng patch version hoặc image digest trùng với môi trường production hay phiên bản đích của đợt nâng cấp.

Cần đối chiếu:

- MySQL server version và patch release.
- Connector/J version và JDBC URL properties.
- SQL mode.
- Character set và collation của database/table/column.
- Timezone server và session.
- Authentication plugin và TLS nếu cần kiểm tra kết nối.
- Storage engine, isolation level và cấu hình liên quan.
- Migration version và schema.
- Các biến như `lower_case_table_names`, `auto_increment_increment` nếu ứng dụng phụ thuộc.

Không dùng tag container trôi nổi như `latest` trong test tương thích. Tag có thể trỏ tới phiên bản mới khi pipeline chạy lần sau và làm kết quả thay đổi. Pin patch version hoặc image digest để tái lập; cập nhật pin có chủ đích khi kiểm thử nâng cấp.

Nếu production dùng cấu hình tùy chỉnh, khởi chạy container với file cấu hình test tương ứng hoặc tham số server rõ ràng. Tránh sao chép secret production hoặc dữ liệu cá nhân vào container test.

## 13. Các bài test nên chạy trên MySQL thật

Dùng MySQL integration test cho các hành vi phụ thuộc server:

| Nhóm | Ví dụ kiểm thử |
|---|---|
| Schema và migration | Flyway/Liquibase từ database rỗng và nâng cấp schema cũ |
| Kiểu dữ liệu | JSON, unsigned, decimal precision, timestamp precision, generated column |
| Constraint | Unique theo collation, foreign key, CHECK, NOT NULL |
| SQL đặc thù | Upsert, LAST_INSERT_ID, JSON function, GROUP_CONCAT |
| Transaction | Commit/rollback, isolation, read visibility |
| Concurrency | Row lock, deadlock, lock wait timeout, unique race |
| Index/plan | EXPLAIN, EXPLAIN ANALYZE, index selection trên dữ liệu đại diện |
| Stored program | Procedure, function, trigger, event, DEFINER và quyền |
| Driver | Generated keys, batch rewrite, timezone, reconnect |
| Bảo mật kết nối | Tài khoản, GRANT, role, TLS và authentication plugin |

Không cần chạy toàn bộ test chậm sau mỗi thay đổi nhỏ. Có thể tổ chức pipeline:

- Unit test với mock chạy ở mọi commit.
- Repository/JPA test nhanh chạy trên MySQL container trong CI.
- Migration, concurrency, performance và compatibility suite chạy ở pull request quan trọng hoặc lịch nightly.
- Smoke test trên staging sau khi triển khai phiên bản mới.

Testcontainers vẫn là test integration; nó không thay thế benchmark production-like hoặc kiểm thử failover của topology thật.

## 14. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| Mock repository rồi kết luận SQL đúng | Không có SQL nào được thực thi | Chạy repository test trên MySQL |
| Chỉ bật `MODE=MySQL` trong H2 | Chỉ mô phỏng một phần hành vi | Dùng H2 cho SQL portable; xác minh phần MySQL-specific trên server thật |
| Đổi kiểu JSON thành VARCHAR trong test | Schema test không còn giống production | Dùng MySQL container cho mapping và JSON function |
| Dùng H2 để kiểm tra collation | Quy tắc so sánh có thể khác | Tạo schema với collation thật trên MySQL |
| Dùng H2 để test deadlock | Lock engine khác InnoDB | Dùng hai MySQL sessions và transaction độc lập |
| Dùng H2 làm bước duy nhất cho Flyway | DDL và implicit commit có thể khác | Chạy migration trên MySQL mục tiêu |
| `@DataJpaTest` vô tình thay DataSource | Test chạy embedded DB dù cấu hình có MySQL | Dùng `replace = NONE` và xác minh server version |
| Dùng image `latest` | Kết quả test không tái lập | Pin phiên bản hoặc digest |
| Chỉ test trên database rỗng | Không phát hiện vấn đề cardinality và dữ liệu cũ | Seed dữ liệu đại diện, có duplicate và edge cases |
| Chạy concurrency trong một transaction test | Không tạo ra các session độc lập | Dùng connection/transaction riêng cho mỗi actor |

## 15. Quy trình thiết kế test theo rủi ro

Một quy trình hợp lý:

1. **Xác định hợp đồng cần kiểm tra:** logic service, mapping JPA, SQL, constraint, transaction hay performance.
2. **Chọn môi trường:** mock cho logic, H2 cho phần portable, MySQL container cho semantics MySQL.
3. **Giữ schema nhất quán:** dùng migration thật thay vì tạo một schema H2 đơn giản hóa nhưng khác production.
4. **Dùng dữ liệu có ý nghĩa:** gồm hàng bình thường, biên, NULL, duplicate, khóa ngoại và phân bố dữ liệu quan trọng.
5. **Chạy test trên đúng driver:** Connector/J version và properties cần khớp môi trường ứng dụng.
6. **Xác minh engine:** kiểm tra server version, SQL mode, collation, timezone và storage engine.
7. **Đối chiếu kết quả:** kiểm tra cả dữ liệu lưu trong DB và hành vi ứng dụng.
8. **Giữ test tái lập:** pin image, seed data, migration version và cấu hình.
9. **Phân loại tốc độ pipeline:** unit nhanh, integration MySQL ở CI, performance/upgrade suite theo lịch hoặc trước release.
10. **Ghi lại giới hạn:** test H2 không chứng minh hành vi MySQL nào; test container không thay thế kiểm thử trên production-like topology.

## 16. Checklist

**Khi dùng mock**

- [ ] Chỉ dùng để kiểm tra logic service và tương tác dependency.
- [ ] Không xem mock là bằng chứng SQL, JPA mapping hoặc constraint đúng.
- [ ] Có test integration tương ứng cho các hành vi repository quan trọng.

**Khi dùng H2**

- [ ] Xác định truy vấn và schema đang kiểm tra có portable hay không.
- [ ] Nếu dùng MySQL mode, ghi rõ đây chỉ là compatibility subset.
- [ ] Không dùng kết quả H2 để kết luận về collation, lock, optimizer hoặc MySQL DDL.
- [ ] Không âm thầm đổi schema production để phù hợp H2.

**Khi dùng MySQL thật**

- [ ] Chạy MySQL container với version gần hoặc đúng production.
- [ ] Dùng Connector/J thật và migration thật.
- [ ] Đặt đúng SQL mode, charset/collation và timezone.
- [ ] Kiểm tra constraint, transaction và generated keys.
- [ ] Dùng connection độc lập cho test concurrency.
- [ ] Pin image và seed dữ liệu để test có thể tái lập.

## 17. Ghi nhớ

- Mock kiểm tra logic gọi dependency; nó không chạy SQL và không mô phỏng InnoDB.
- H2 MySQL mode chỉ tương thích một phần, không phải MySQL Server.
- Khác biệt kiểu dữ liệu, collation, SQL mode, timezone, AUTO_INCREMENT và cú pháp có thể khiến test H2 xanh nhưng MySQL lỗi.
- Transaction isolation, row/gap lock và deadlock cần được kiểm tra trên InnoDB.
- Optimizer và execution plan của H2 không dự đoán plan MySQL.
- DDL và migration phải được chạy trên phiên bản MySQL mục tiêu.
- Dùng Testcontainers để kiểm thử Spring Data JPA, Connector/J, migration và constraint với MySQL thật.
- Với Spring Boot `@DataJpaTest`, ngăn thay DataSource bằng embedded database khi cần dùng MySQL container.
- Pin phiên bản MySQL, cấu hình và dữ liệu để kết quả test có thể tái lập.
- Chọn công cụ theo rủi ro; không yêu cầu mọi test phải khởi động database nhưng cũng không bỏ qua kiểm thử MySQL ở các ranh giới quan trọng.

Một bộ test đáng tin cậy dùng mock để kiểm tra logic ứng dụng, H2 cho những phần SQL thực sự portable và MySQL thật cho hành vi phụ thuộc MySQL. Khi schema, driver, cấu hình và dữ liệu test gần môi trường triển khai, kết quả kiểm thử mới cung cấp bằng chứng có giá trị cho việc phát hành.

## Tài liệu tham khảo

- [H2 Database Engine: Features and Compatibility Modes](https://www.h2database.com/html/features.html#compatibility)
- [Spring Boot Reference: Testing and Auto-configured Data JPA Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot Reference: Testcontainers Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers for Java: MySQL Module](https://java.testcontainers.org/modules/databases/mysql/)
- [MySQL 8.4 Reference Manual: InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual: Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset.html)
- [MySQL 8.4 Reference Manual: EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)

