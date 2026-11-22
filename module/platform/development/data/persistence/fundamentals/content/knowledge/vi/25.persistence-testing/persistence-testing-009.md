# Dùng môi trường cô lập với hệ lưu trữ đại diện

Trong chương **Kiểm thử lưu trữ** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một bài kiểm thử Java có thể chạy xanh trên cơ sở dữ liệu giả hoặc H2 nhưng thất bại khi dùng PostgreSQL thật. Nguyên nhân không chỉ nằm ở cú pháp SQL: **transaction isolation, khóa, unique constraint, cách xử lý kiểu dữ liệu, driver, connection pool, migration, quyền truy cập, WAL và hành vi khi mất kết nối** đều có thể khác nhau.

Giải pháp không phải bỏ unit test để mọi bài kiểm thử đều kết nối production. Giải pháp là **tạo môi trường kiểm thử cô lập, có hệ lưu trữ đủ đại diện cho những rủi ro cần chứng minh**, rồi chạy integration test và fault-injection test trong phạm vi đó. Với Java, một lựa chọn thường dùng là PostgreSQL chạy trong container ngắn hạn và Testcontainers/JUnit; với hệ thống lớn hơn có thể cần thêm broker, cache, replica hoặc môi trường staging riêng.

“Cô lập” bảo đảm phép thử không làm thay đổi dữ liệu, tài nguyên hoặc hành vi của môi trường đang phục vụ người dùng. “Đại diện” bảo đảm những đặc tính ảnh hưởng tính đúng đắn được thử bằng công nghệ và cấu hình phù hợp. **Cần cả hai**: môi trường giống production nhưng có thể xóa dữ liệu thật là không an toàn; môi trường hoàn toàn tách biệt nhưng mô phỏng sai SQL/khóa lại không đem lại bằng chứng đáng tin.

## 1. Hiểu đúng hai yêu cầu: cô lập và đại diện

**Môi trường cô lập** có ranh giới rõ về:

- **Dữ liệu:** chỉ chứa fixture hoặc bản sao đã được phép dùng; không truy cập/chỉnh sửa dữ liệu khách hàng thực.
- **Kết nối:** ứng dụng test không vô tình dùng JDBC URL, DNS, secret hoặc tài khoản của production.
- **Quyền:** test dùng role riêng; bài test phá hủy dữ liệu chỉ chạy trên database dành cho test.
- **Tài nguyên:** bảng, schema, volume, container, hàng đợi và cache được phân định cho một suite hoặc một worker.
- **Tác dụng phụ:** email, thanh toán, webhook, outbox relay và scheduler không gọi hệ thống thật.
- **Vòng đời:** có cách khởi tạo, reset, thu gom và tái tạo sau khi test thất bại.

**Môi trường đại diện** giữ được những yếu tố quan trọng của nơi hệ thống sẽ chạy:

- Cùng **họ DBMS** và phiên bản chính gần production khi behavior phụ thuộc version.
- Schema, constraint, index, migration, extension, collation và kiểu dữ liệu cần thiết.
- JDBC driver, persistence stack (JDBC/Spring JDBC/JPA), transaction manager và cách cấu hình pool tương thích.
- Isolation level, timezone, encoding, role, RLS và các cấu hình ảnh hưởng câu SQL đang kiểm thử.
- Mẫu dữ liệu đủ đa dạng: có bản ghi trùng logic, giá trị biên, unicode, quan hệ nhiều hàng.
- Với tính năng phân tán: giả lập được retry, sự kiện trùng, mất ACK, replica lag và khôi phục theo mục tiêu riêng.

Đại diện **không có nghĩa mọi test phải có cùng dung lượng dữ liệu, số replica hay loại máy với production**. Những khác biệt được chấp nhận nếu chúng **không làm sai kết luận** mà test đang cố chứng minh.

## 2. Vì sao mock repository hoặc in-memory database chưa đủ?

Xét use case giữ hàng: nếu tồn kho chỉ còn 5, hai giao dịch đồng thời cùng yêu cầu 4 đơn vị thì tối đa một giao dịch được chấp nhận.

Một unit test dùng mock có thể kiểm tra Application Service gọi `reserveIfAvailable` và xử lý kết quả `true/false` đúng. Nhưng mock **không thực thi** câu `UPDATE`, không có lock hoặc MVCC, không nhận biết transaction deadlock và không cưỡng chế ràng buộc.

Tương tự, một bài test dùng H2 có thể kiểm tra CRUD cơ bản, nhưng không đủ chứng minh:

- PostgreSQL thực thi `INSERT ... ON CONFLICT ... RETURNING` đúng như dự kiến.
- Kiểu `JSONB`, `UUID`, `TIMESTAMPTZ` và biểu thức/extension được ánh xạ đúng.
- `SELECT ... FOR UPDATE SKIP LOCKED` có hành vi mong muốn trong worker queue.
- Lỗi trùng `UNIQUE`, deadlock và serialization failure có mã lỗi/transaction state như production.
- Row-level security hoặc quyền cột của PostgreSQL chặn một role runtime.
- Cách Hibernate sinh SQL, flush, optimistic lock hoặc native bulk update tương thích dialect thật.

Điều này không làm unit test vô ích. **Unit test kiểm tra quy tắc và orchestration nhanh; integration test kiểm tra ranh giới thật với DBMS; end-to-end test kiểm tra các dịch vụ phối hợp.** Mỗi lớp chứng minh một điều khác nhau.

## 3. Chọn độ trung thực của môi trường theo câu hỏi kiểm thử

| Câu hỏi cần chứng minh | Môi trường nhỏ nhất phù hợp | Lý do |
| --- | --- | --- |
| Domain policy từ chối số lượng âm? | Unit test Java thuần. | Không cần DB để xác định bất biến thuần. |
| Repository bind tham số và mapping đúng? | PostgreSQL test container. | Cần SQL/driver/dialect thật. |
| Migration tạo đủ bảng/constraint/index? | PostgreSQL mới, chạy migration thật. | Không được dùng schema tự dựng khác migration. |
| Hai transaction không bán vượt tồn kho? | PostgreSQL với hai connection/transaction độc lập. | Cần khóa, isolation và lịch xen kẽ thực. |
| Runtime role bị cấm xóa bảng? | PostgreSQL với GRANT/RLS và credential runtime. | Chỉ DB thực mới thể hiện quyền hiệu lực. |
| Redis stale và outbox giao trùng? | PostgreSQL + cache/broker hoặc fake có điều khiển phù hợp mục tiêu. | Cần giả lập event/order/failure ở ranh giới tương ứng. |
| Failover có thể khiến kết quả commit không rõ? | Test topology/fault injection được thiết kế và kiểm soát. | Một container DB đơn không mô phỏng failover thật. |
| p99 với 50 triệu hàng và 1.000 client? | Môi trường benchmark/staging đại diện tải và dữ liệu. | Container nhỏ không cho kết luận hiệu năng production. |

Một lỗi thường gặp là dùng từ **“integration test” như bằng chứng mọi điều đã được thử**. Thực tế, hãy ghi rõ **môi trường mô phỏng những yếu tố nào và không mô phỏng những yếu tố nào**.

## 4. Nguyên tắc an toàn trước khi chạy bất kỳ phép thử nào

Với bài kiểm thử có `DROP TABLE`, `TRUNCATE`, `DELETE`, migration hoặc lỗi mạng chủ động, ranh giới cô lập phải được kiểm chứng **trước** khi thực thi lệnh nguy hiểm.

Nên có những guardrail:

1. Cấu hình JDBC test nhận từ profile test riêng; không kế thừa tùy tiện URL production.
2. Chỉ cho phép host/container/network thuộc vùng test; từ chối các tên host được đánh dấu production.
3. Dùng database và user do test provision, không lấy credential runtime production.
4. Đặt tên database/schema test riêng, ví dụ `persistence_it` hoặc tên có run ID.
5. Với CI song song, mỗi worker có isolation để không xóa fixture của worker khác.
6. Không cho test container gọi ra cổng thanh toán, webhook, email hay broker production.
7. Cấm chạy SQL phá hủy trên environment không đạt kiểm tra safety.
8. Mọi dọn dẹp chỉ chạm tới tài nguyên do test tạo ra; gắn nhãn/run ID và giới hạn phạm vi.

**Không nên dựa chỉ vào biến môi trường có tên “TEST_MODE”**. Một biến flag có thể bật nhầm, trong khi URL vẫn trỏ production. Kiểm tra danh tính database, endpoint và quyền truy cập trước phép thử có tác dụng phụ là thực hành quan trọng.

## 5. Ví dụ nền tảng: Testcontainers PostgreSQL với JUnit 5

Testcontainers cho phép ứng dụng Java tạo một PostgreSQL instance ngắn hạn trên runtime container tương thích. Bài test kết nối qua JDBC URL được cung cấp khi container chạy.

Ví dụ với Spring Boot/JUnit 5, giả định dự án có những dependency phù hợp:

```text
Test dependencies (khái niệm):
  JUnit Jupiter
  Testcontainers JUnit Jupiter integration
  Testcontainers PostgreSQL module
  PostgreSQL JDBC driver
  Spring Boot test + Spring JDBC/JPA nếu dùng

Runtime test host:
  Docker hoặc container runtime được Testcontainers hỗ trợ
```

Một khung test Spring Boot:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class PostgreSqlSmokeIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void canReadServerVersion() {
        String version = jdbc.queryForObject(
                "SELECT current_setting('server_version')",
                String.class
        );
        org.junit.jupiter.api.Assertions.assertNotNull(version);
    }
}
```

**Lưu ý phiên bản:** ví dụ dùng API Testcontainers/Spring Boot/JUnit phổ biến, không khóa dependency version. Tùy phiên bản Spring Boot, Testcontainers và PostgreSQL module, cách khai báo dependency hoặc integration có thể khác. Cần pin image/digest phù hợp CI, version ứng dụng, driver và DBMS production; `postgres:17` chỉ là tag minh họa. Không bật tự động nâng sang image mới mà không kiểm tra tương thích.

Container này chứng minh **app mở connection tới PostgreSQL thật trong môi trường test**. Nó chưa chứng minh schema có đủ bảng hoặc role có quyền đúng: các bước đó cần migration và test riêng.

## 6. Khởi tạo schema bằng migration thật, không bằng một phiên bản “test riêng”

Nếu production dùng Flyway/Liquibase, integration test nên chạy **cùng tập migration đã được kiểm soát** trên database mới. Dùng `hibernate.hbm2ddl.auto=create-drop` trong test nhưng production dùng migration riêng có thể che lỗi:

- Migration quên index hoặc constraint.
- Tên cột, default value hay kiểu dữ liệu khác entity.
- Thứ tự migration không chạy được từ database trống.
- Script tạo function/extension không tương thích PostgreSQL version.
- Quyền cấp cho role runtime thiếu hoặc thừa.

Một quy trình test:

```text
Start fresh PostgreSQL test container
    |
    v
Create owner/migrator/runtime roles (nếu mô hình yêu cầu)
    |
    v
Run production migration chain
    |
    v
Validate DB schema, constraints, indexes, extensions
    |
    v
Connect using runtime principal
    |
    v
Run repository/service integration tests
```

Ví dụ cấu hình khi dùng Spring Boot với Flyway và JPA:

```yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
```

`ddl-auto: validate` chỉ áp dụng nếu dự án dùng Hibernate/JPA và cấu hình phù hợp. Nó kiểm tra mapping ở phạm vi hỗ trợ, **không thay thế** test quyền, constraint, mọi index và khả năng thực thi migration. Nếu không dùng JPA, bỏ phần cấu hình đó.

Không đưa SQL migration giả vào code bài học và mặc định nó đã tương ứng với schema thật. Đề tài này yêu cầu **test trên schema do dự án định nghĩa**, không phải một lược đồ khác được test tự chế.

## 7. Fixture phải có ý nghĩa và tái lập được

Một test phụ thuộc dữ liệu cũ trong database staging có thể chạy xanh hôm nay nhưng thất bại ngày mai. Mỗi test nên biết **trạng thái ban đầu mà nó sở hữu**.

Ví dụ fixture đơn hàng:

```sql
CREATE TABLE inventory (
    sku       TEXT PRIMARY KEY,
    active    BOOLEAN NOT NULL,
    available INTEGER NOT NULL CHECK (available >= 0),
    version   BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE reservations (
    request_id UUID PRIMARY KEY,
    sku        TEXT NOT NULL REFERENCES inventory(sku),
    quantity   INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO inventory(sku, active, available, version)
VALUES ('BOOK-TEST', TRUE, 5, 0);
```

Đây là **schema minh họa cho bài tập**, không thay thế migration production. Trong dự án thực, migration tạo bảng; fixture chỉ nạp dữ liệu kiểm thử vào bảng có sẵn.

Một fixture tốt cần:

- Có các giá trị biên: tồn kho = 0, vừa đủ, thiếu; ngày/giờ qua timezone; chuỗi Unicode; `NULL`/non-null.
- Có quan hệ 1-N, dữ liệu trùng logic và những trạng thái hợp lệ/không hợp lệ theo test.
- Không phụ thuộc kết quả từ test chạy trước.
- Dùng ID cố định có namespace hoặc generated ID được giữ trong test context; tránh đụng ID của suite khác.
- Tránh thời gian hiện tại nếu không cần; nếu cần, có clock/test fixture được kiểm soát.
- Đủ dữ liệu để kích hoạt đường index, pagination, mapping và constraint đang được kiểm tra.

**Dữ liệu thực không nên được copy thẳng vào CI** khi có thông tin cá nhân/secret. Khi cần profile hiệu năng đại diện, tạo dữ liệu tổng hợp có phân phối tương đương hoặc dùng bản sao đã được xử lý và được phê duyệt theo chính sách.

## 8. Reset dữ liệu: transaction rollback không giải quyết mọi bài test

Một số Spring integration test dùng `@Transactional` trên method test để rollback thay đổi cuối test. Đây là kỹ thuật tiện, nhưng không được giả định nó cô lập **mọi** thao tác:

| Kịch bản | Rollback quanh test có đủ không? | Lý do |
| --- | --- | --- |
| Repository được gọi đồng bộ cùng transaction của test | Có thể đủ trong phạm vi đó. | Cùng thread/transaction manager và connection phù hợp. |
| Service dùng `REQUIRES_NEW` | Không bảo đảm. | Transaction mới có thể commit độc lập. |
| HTTP request được test qua server thread khác | Không mặc nhiên. | Transaction test thread không bọc transaction ở server. |
| Async consumer, scheduler hoặc job nền | Không. | Chúng chạy transaction/thời điểm riêng. |
| Redis/broker/outbox bên ngoài database | Không. | Tài nguyên ngoài không rollback cùng DB. |
| Sequence tăng khi transaction rollback | Không khôi phục trạng thái sequence như dữ liệu hàng. | Nhiều DBMS không rollback cấp số sequence. |
| DDL/migration đặc thù | Tùy DBMS/công cụ. | Không phải mọi tác dụng DDL hoặc side effect đều theo transaction test. |

Chiến lược cô lập có thể gồm:

1. **Database/schema mới cho mỗi suite** với container độc lập.
2. **Fixture theo test** và cleanup các hàng do test sở hữu.
3. **Rollback per test** khi biết chính xác phạm vi transaction.
4. **Truncate/reset có kiểm soát trong DB test**, sau khi xác minh đúng môi trường; lưu ý foreign key/sequence và worker chạy song song.
5. **Container mới cho test có tác dụng phá hủy**, nhất là kiểm thử migration hoặc lỗi recovery.

Không để hai test đồng thời `TRUNCATE` cùng bảng trong một database chung. Điều này tạo bài test flaky không liên quan production behavior.

## 9. Bài test repository: kiểm tra SQL và mapping bằng database thật

Xét use case chỉ giữ hàng khi còn đủ tồn kho:

```sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE sku = :sku
  AND active = TRUE
  AND available >= :quantity;
```

Một test có ý nghĩa phải kiểm tra:

1. Câu lệnh đúng khi hàng tồn tại và có đủ tồn kho.
2. Không trừ khi hết hàng, SKU không tồn tại hoặc sản phẩm ngừng bán.
3. Số hàng cập nhật bằng 1 khi thành công, bằng 0 khi điều kiện không thỏa.
4. `available` và `version` sau commit là giá trị dự kiến.
5. `CHECK (available >= 0)` và `UNIQUE(request_id)` được DBMS cưỡng chế.
6. Nếu thêm bước ghi reservation bị lỗi, transaction rollback cập nhật tồn kho.

Một repository JDBC minh họa:

```java
import org.springframework.jdbc.core.JdbcTemplate;

public final class StockWriter {
    private final JdbcTemplate jdbc;

    public StockWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int reserve(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return jdbc.update("""
            UPDATE inventory
            SET available = available - ?,
                version = version + 1
            WHERE sku = ?
              AND active = TRUE
              AND available >= ?
            """, quantity, sku, quantity);
    }
}
```

Đây là **một phép ghi**, không phải giao dịch đặt hàng hoàn chỉnh. Một use case có `INSERT reservations` cần cùng transaction và cơ chế idempotency. Unit test `StockWriter` với mock `JdbcTemplate` không chứng minh PostgreSQL thật thực thi câu SQL hay constraint đúng; đó là mục đích của bài test với môi trường đại diện.

## 10. Kiểm thử đồng thời phải có nhiều transaction thật

Nếu chỉ chạy tuần tự `reserve("BOOK-TEST", 4)` hai lần, test thấy một thành công và một thất bại. Nhưng nó **chưa chứng minh** giao thức an toàn khi hai request cạnh tranh trong thời điểm đọc–ghi.

Một integration test thích hợp cho phép hai connection thực thi cùng lúc, rồi kiểm tra trạng thái cuối:

```text
Given: available = 5, active = true
Worker A: request quantity = 4
Worker B: request quantity = 4

Start both workers concurrently
Wait for both to finish (with timeout)

Assert:
  successful_updates = 1
  failed_condition_updates = 1
  final available = 1
  final version = initial_version + 1
  no negative inventory
```

Ví dụ JUnit/JDBC dùng hai connection độc lập, **không đặt `@Transactional` trên method test này**:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Future;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ConcurrentStockTest {
    private DataSource dataSource; // Inject datasource test thật.

    private int reserveFour() throws Exception {
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement("""
                 UPDATE inventory
                 SET available = available - 4,
                     version = version + 1
                 WHERE sku = 'BOOK-TEST'
                   AND active = TRUE
                   AND available >= 4
                 """)) {
            return ps.executeUpdate();
        }
    }

    @Test
    void cannotOversell() throws Exception {
        // Fixture available=5 đã được thiết lập/commit trước test.
        var pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<Integer> a = pool.submit(() -> {
                start.await();
                return reserveFour();
            });
            Future<Integer> b = pool.submit(() -> {
                start.await();
                return reserveFour();
            });
            start.countDown();
            int totalUpdated =
                    a.get(10, TimeUnit.SECONDS) +
                    b.get(10, TimeUnit.SECONDS);
            assertEquals(1, totalUpdated);
            // Test thực cần query thêm final available=1 và version.
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Đoạn code là **khung minh họa**, cần inject datasource, fixture và kiểm tra DB cuối. Trong chế độ auto-commit mặc định thông thường, mỗi `UPDATE` ở ví dụ là một transaction cục bộ. Nếu datasource test trả connection với cấu hình auto-commit khác hoặc có transaction manager điều phối, test phải chủ động xác lập và kiểm chứng ranh giới commit.

Để tái hiện chính xác một lỗi *lost update* hoặc *write skew*, thường cần **barrier giữa các bước đọc và ghi**, transaction dài hơn và điều kiện chờ có kiểm soát; chỉ bắn hai thread đồng thời không bảo đảm mọi lịch xen kẽ. Một bài test tốt ghi rõ lịch cạnh tranh nó muốn kích hoạt, timeout, mức isolation và kết quả chấp nhận được.

## 11. Dùng isolation level của đúng DBMS để thử anomaly

Các mức `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` có tên quen thuộc, nhưng hành vi cụ thể giữa PostgreSQL, MySQL/InnoDB và các engine khác **không hoàn toàn giống nhau**.

Với PostgreSQL, cần tạo nhiều connection/transaction riêng để kiểm tra:

- **Non-repeatable read** ở mức `READ COMMITTED` khi statement sau có snapshot mới.
- **Snapshot behavior** ở `REPEATABLE READ`.
- **Write skew** với bất biến trải nhiều hàng; các mô hình snapshot isolation không tự ngăn mọi anomaly.
- **Serialization failure (SQLSTATE `40001`)** khi dùng `SERIALIZABLE` và có lịch giao dịch xung đột phù hợp.
- **Deadlock (SQLSTATE `40P01`)** với thứ tự lấy khóa trái nhau.
- **Lock timeout/statement timeout** theo cấu hình test, không treo CI vô hạn.

Một phép thử concurrency cần ghi:

| Trường | Ví dụ |
| --- | --- |
| DBMS/version | PostgreSQL major version đã pin. |
| Isolation | `READ COMMITTED` hoặc `SERIALIZABLE`. |
| Số transaction | A và B, mỗi transaction có connection riêng. |
| Lịch | A đọc; B đọc; A ghi; B ghi; thứ tự commit có chủ đích. |
| Bất biến | Tồn kho không âm hoặc còn ít nhất một bác sĩ trực. |
| Kết quả hợp lệ | Một transaction rollback/xung đột hoặc trạng thái cuối thỏa bất biến. |
| Timeout | Từng bước chờ có giới hạn, cleanup trong `finally`. |

**Không dùng H2 để kết luận PostgreSQL SERIALIZABLE sẽ phát cùng loại lỗi**, vì cơ chế concurrency và SQLSTATE có thể khác. Cũng không giả định mọi lần chạy hai thread tự động sinh deadlock: phải sắp thứ tự lấy khóa tạo vòng chờ.

## 12. Test transaction rollback, commit và lỗi tại ranh giới ghi

Một service Java có thể cập nhật hai bảng rồi mới commit:

```text
BEGIN
  UPDATE inventory ... WHERE available >= quantity
  INSERT reservations(request_id, sku, quantity)
COMMIT
```

Để chứng minh atomicity, có thể cố ý tạo một lỗi ở lệnh thứ hai, ví dụ trùng `request_id`, rồi xác minh:

1. Lỗi SQL được phân loại đúng.
2. Transaction bị rollback; tồn kho không giảm.
3. Không có reservation mới ngoài bản đã tồn tại.
4. Connection trở lại trạng thái có thể dùng theo contract pool/transaction manager.
5. Cùng idempotency key được đối soát thay vì sinh ID mới và trừ thêm.

**Lỗi trước khi gọi `COMMIT`** khác với **mất ACK sau `COMMIT`**. Với trạng thái commit không rõ, test phải giả lập mất đường phản hồi đúng giai đoạn và quan sát dữ liệu từ **một connection mới**; chỉ mock `SQLException` từ repository không chứng minh được trạng thái database đã commit hay chưa.

Ví dụ kịch bản:

```text
T1: INSERT reservation + UPDATE inventory
T2: Database COMMIT thành công
T3: Mất mạng trước khi client nhận commit ACK
T4: Java ghi nhận exception / outcome unknown
T5: Reconnect, SELECT theo request_id ở primary
T6: Xác nhận đã có kết quả cũ; không áp dụng lại nghiệp vụ
```

Khi fault-injection ở ranh giới mạng, một container PostgreSQL đơn chỉ hỗ trợ **một phần** failure mode. Các test failover/replication cần topology có khả năng tạo sự cố đó hoặc môi trường chuyên biệt. Đừng khẳng định đã thử mất ACK của commit chỉ bằng cách ném exception trước khi lệnh commit chạy.

## 13. Test ràng buộc dữ liệu và schema thật

Các ràng buộc nên được test bằng SQL/driver thật:

| Cơ chế | Kịch bản |
| --- | --- |
| `PRIMARY KEY` | Chèn hai hàng có cùng khóa. |
| `UNIQUE` | Hai transaction cạnh tranh cùng business idempotency key. |
| `CHECK` | Chèn `available = -1`, đảm bảo bị từ chối. |
| `FOREIGN KEY` | Chèn reservation tới SKU không tồn tại. |
| `NOT NULL` | Gửi `NULL` vào cột bắt buộc. |
| Transaction | Lỗi lệnh thứ hai rollback lệnh thứ nhất. |
| `@Version`/optimistic locking | Hai entity đọc cùng version, chỉ update hợp lệ thành công. |
| Trigger/function | Kiểm tra side effect dự kiến, quyền và lỗi. |
| Collation/unique index | Kiểm tra trùng với Unicode/chữ hoa–thường theo quy tắc dữ liệu thực tế. |

Phải xác minh lỗi **ở thời điểm phù hợp**. Một số constraint trong PostgreSQL có thể khai báo deferred, nên lỗi xuất hiện ở `COMMIT` thay vì ngay `INSERT`. Với JPA, SQL có thể chỉ được gửi khi `flush()` hoặc transaction commit, nên test không nên mặc định lỗi xảy ra ngay ở `entityManager.persist(...)`.

Một bài test mà transaction test tự rollback cuối cùng có thể **không phát hiện lỗi vốn chỉ xuất hiện ở commit**, nếu không gọi flush/commit theo kịch bản tương ứng. Cần thiết kế riêng test kiểm tra thời điểm hoàn tất transaction.

## 14. Kiểm thử kiểu dữ liệu, thời gian và encoding

Một môi trường dùng sai dialect thường che những lỗi mapping khó:

- `TIMESTAMP WITH TIME ZONE`/`TIMESTAMPTZ` và chuyển đổi `Instant`, `OffsetDateTime`, timezone của JVM/DB.
- `UUID`, `JSONB`, `NUMERIC` và precision/scale của `BigDecimal`.
- Chuỗi Unicode có dấu tiếng Việt, emoji và collation/case folding.
- `NULL` ở cột boolean/numeric, giá trị mặc định và mapping sang primitive Java.
- Mảng, enum, custom type, extension hoặc binary/LOB.
- Thứ tự phân trang khi nhiều hàng có cùng `created_at`; thiếu `ORDER BY` ổn định.

Ví dụ PostgreSQL:

```sql
CREATE TABLE measurement (
    id         UUID PRIMARY KEY,
    amount     NUMERIC(18, 4) NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    metadata   JSONB NOT NULL
);

INSERT INTO measurement(id, amount, event_time, metadata)
VALUES (
    '7dbec00b-8705-4a6e-903e-af7685d190f8',
    12345.6789,
    '2026-11-22T09:30:00+07:00',
    '{"message":"Kiểm thử lưu trữ tiếng Việt"}'::jsonb
);
```

Một Java/JDBC test nên đọc lại `BigDecimal` và timestamp theo kiểu thích hợp, không so chuỗi timezone thô nếu nghiệp vụ đang so cùng thời điểm. Đặc biệt tránh `float/double` cho số tiền chỉ vì test in-memory trước đó không phát hiện sai số.

## 15. Kiểm thử phân quyền bằng chính role runtime

Nếu migration tạo schema dưới role owner nhưng service dùng role ít quyền, test chỉ chạy bằng owner sẽ **bỏ sót lỗi `GRANT`**.

Một môi trường đại diện nên có:

1. Role owner/migrator để tạo và thay schema.
2. Role runtime với chỉ quyền cần thiết trên bảng/cột.
3. Policy tenant/RLS nếu production có.
4. Connection pool dùng đúng role runtime cho integration test ứng dụng.
5. Negative tests: `DELETE`, `ALTER` hoặc truy vấn schema nhạy cảm phải bị từ chối.

Ví dụ kiểm tra nhận dạng:

```sql
SELECT current_user, session_user, current_database();

SELECT has_column_privilege(
    'shop_api', 'shop.orders', 'status', 'UPDATE'
) AS can_change_status;

SELECT has_table_privilege(
    'shop_api', 'shop.orders', 'DELETE'
) AS can_delete_orders;
```

Đây là SQL kiểm tra PostgreSQL, **không tạo được quyền** cho role nếu migration chưa thực hiện. Bài test cuối vẫn phải **thực thi thao tác bằng role runtime** và kiểm tra có đúng bị chặn hay không.

Đặc biệt với RLS theo `app.tenant_id` đặt trong session/transaction, cần thử nhiều yêu cầu dùng lại connection pool để phát hiện rò ngữ cảnh tenant. Một test chỉ đọc tenant A trên một connection mới không chứng minh tenant B an toàn.

## 16. Kiểm thử connection pool, timeout và tài nguyên

Môi trường container thường ít connection và ít tài nguyên hơn production. Điều này có thể hữu ích để phát hiện lỗi nhưng không đủ dự đoán throughput thực.

Những kiểm tra nên có:

- Connection được trả về pool cả khi SQL ném exception.
- Connection ở trạng thái transaction/auto-commit đúng sau rollback.
- Timeout lấy connection và statement không làm treo service vô hạn.
- Query giữ khóa lâu được phân loại thành lock timeout/serialization failure theo driver.
- Bài test không mở transaction rồi gọi HTTP chậm trong khi vẫn giữ connection.
- Không có leaked statement/result set sau khi stream dữ liệu lớn.
- Pool có thể khôi phục sau khi DB container restart theo hợp đồng của driver/pool.

Ví dụ một test giới hạn tài nguyên có thể đặt `maximumPoolSize=2` trong môi trường riêng, cho hai request giữ connection và yêu cầu thứ ba chờ/lỗi theo timeout. Nhưng **không tự lấy kết quả từ pool size=2 để suy ra giá trị tối ưu trong production**.

Ở PostgreSQL, nên xem cả số connection, lock waits, WAL/checkpoint và các giới hạn của máy test. Một phép thử performance chịu CPU contention từ máy CI đang chạy nhiều build sẽ nhiễu; không nên coi số đo đó là SLA production.

## 17. Kiểm thử lỗi hạ tầng bằng môi trường có thể hủy

Một lợi ích lớn của môi trường cô lập là được phép tạo lỗi mà không ảnh hưởng người dùng:

| Fault được tạo trong lab | Cần xác minh |
| --- | --- |
| Dừng PostgreSQL container giữa một query | Client nhận lỗi đúng, pool loại connection hỏng, không báo thành công giả. |
| Dừng sau một local commit đã xác nhận | Dữ liệu phục hồi theo độ bền đã cấu hình. |
| Ngắt mạng trước khi phản hồi commit | Không tự suy đoán rollback; đối soát request ID. |
| Gây deadlock có kiểm soát | Transaction bị từ chối được retry toàn bộ khi an toàn. |
| Khóa hàng khiến request timeout | Lỗi timeout đúng, không giữ connection/lock vô hạn. |
| Broker giao lặp event | Consumer có inbox/idempotency. |
| Worker sập sau DB commit trước broker publish | Outbox không mất và relay gửi lại. |
| Redis bị xóa/không sẵn sàng | Fallback không phá bất biến, không gây DB stampede. |
| WAL/backup bị thiếu trong bản test | Quy trình recovery phát hiện đúng, không báo DR ready. |

Fault injection có thể dùng proxy mạng, tính năng của container runtime hoặc công cụ chuyên dụng, **chỉ trong hạ tầng đã được phép**. Những test như giết DB đột ngột, thay firewall hoặc cắt storage cần được định nghĩa rõ cleanup và giới hạn tài nguyên.

Đừng đồng nhất `connection.close()` ở phía Java với “mất ACK sau DB commit”: đóng connection ở một thời điểm tùy ý không bảo đảm tái hiện đúng lịch sự cố cần kiểm tra.

## 18. Nhiều dịch vụ và hệ lưu trữ: cần cô lập toàn bộ tác dụng phụ

Một use case đặt hàng có thể dùng PostgreSQL, Redis, broker và một Payment Service. Nếu test container cho PostgreSQL riêng nhưng event consumer lại kết nối broker staging dùng chung, bài test **chưa cô lập**.

```text
Integration test suite
    |
    +-- PostgreSQL container (orders, outbox, inbox)
    |
    +-- Redis container (cache/TTL/invalidation)
    |
    +-- Broker container (events)
    |
    +-- Payment fake / sandbox đã được phê duyệt
    |
    +-- Java service dưới test
              |
              +-- Egress tới production: DENIED
```

Với hệ thống có API ngoài như thanh toán thật, một fake trong môi trường test có thể mô phỏng trả kết quả/thất bại; cần thêm contract test với sandbox chính thức nếu có. **Không dùng thẻ, tài khoản hay endpoint production** để chủ động tạo lỗi.

Những thứ cần cô lập và dọn:

- Topic/queue, consumer group, event retention và DLQ.
- Redis key prefix, TTL và cache region.
- Outbox relay/scheduler và thời gian chờ của job.
- External webhook, SMTP, storage bucket và API credentials.
- File tạm, volume, network và process còn chạy sau test.

Test happy path qua nhiều service là hữu ích, nhưng không thay test duplicate, out-of-order, partial commit và unknown outcome ở từng ranh giới.

## 19. Môi trường cô lập cho replica, failover và PITR có giới hạn riêng

**Một PostgreSQLContainer duy nhất không đại diện cho replication/failover.** Nếu cần chứng minh read-after-write trên replica, tình huống lag hoặc failover làm mất kết quả chưa đồng bộ, cần topology được thiết kế phù hợp:

- Primary và một hay nhiều standby với cấu hình replication rõ.
- Cơ chế failover/proxy/routing giống hoặc tương đương đường vận hành.
- Điều kiện phá mạng, lag WAL và kiểm tra freshness.
- Mốc xác định để kiểm tra RPO/RTO/khả năng đọc theo primary hoặc replica.
- Credential, roles, extension và cấu hình recovery tương thích.

Với backup/PITR, test phải có base backup, WAL archive và **restore thật vào cluster riêng**. Không thể tuyên bố backup an toàn chỉ vì unit test repository trên PostgreSQL container chạy xanh.

Một vài test failover có chi phí cao, nên tách khỏi PR feedback nhanh và chạy trong pipeline chuyên biệt định kỳ. Việc **phân tầng tần suất** không có nghĩa được bỏ test; cần xác định rủi ro và owner cho những kiểm chứng ít chạy.

## 20. Tối ưu tốc độ test nhưng không đánh đổi tính độc lập

Testcontainers hoặc một DB thật có chi phí khởi động. Cần tối ưu có chủ đích:

| Chiến lược | Lợi ích | Rủi ro cần quản lý |
| --- | --- | --- |
| Một container cho suite | Giảm startup cost. | Test chia sẻ state, cleanup khó, song song dễ nhiễu. |
| Container riêng mỗi test | Cô lập mạnh. | Tốn thời gian và tài nguyên. |
| Database/schema riêng mỗi test trong cùng DB server | Cân bằng tài nguyên/isolation. | Shared server vẫn có lock/system state; migration và role cần quản lý. |
| Transaction rollback per test | Nhanh ở đường đồng bộ. | Không bao phủ async, `REQUIRES_NEW`, sequence và external side effect. |
| Reusable container khi phát triển local | Giảm startup khi chạy nhiều lần. | Dễ có dữ liệu tồn và mất tính tái lập; không mặc định dùng trên CI. |
| Chỉ chạy unit test trên mỗi thay đổi nhỏ | Phản hồi nhanh. | Nếu bỏ integration CI, lỗi dialect/migration có thể lọt. |

Ưu tiên tính **deterministic** trước khi tối ưu vài giây: một suite test flaky do dùng chung database làm mất niềm tin vào CI và kéo dài thời gian sửa lỗi.

Nếu cần test chạy song song:

1. Gán run ID và database/schema/container riêng.
2. Không chia sẻ mutable fixture trừ khi thật sự read-only.
3. Đặt timeout/giới hạn CPU, RAM, connection rõ.
4. Không để cleanup của test A xóa dữ liệu test B.
5. Ghi rõ test nào có thể chạy parallel, test nào phải tuần tự.

## 21. Bảo mật môi trường kiểm thử và dữ liệu phục hồi

Một bản sao production dùng để kiểm thử có thể chứa **dữ liệu cá nhân, token, credential và thông tin tài chính**. “Không phải production” không làm dữ liệu tự nhiên mất tính nhạy cảm.

Biện pháp:

- Ưu tiên dữ liệu tổng hợp; nếu phải dùng dữ liệu thật, có phê duyệt, masking và chính sách retention phù hợp.
- Tách IAM/secret, không dùng mật khẩu production trong container hoặc log test.
- Chặn egress tới hệ thống thật, đặc biệt mail, payment, webhook, object storage.
- Không public database test ra internet hoặc để port mở không kiểm soát.
- Xóa dữ liệu tạm/volume và khóa thử theo quy trình; lưu artifact debug đã lọc thông tin nhạy cảm.
- Bảo đảm log SQL không ghi giá trị bind nhạy cảm; trace ID và tên use case thường đủ để điều tra.
- Kiểm tra quyền runtime và negative tests để phát hiện cấp quyền thừa.

Khi làm test restore, **tắt scheduler/outbox relay trước khi khởi động ứng dụng** để tránh phát lại sự kiện đã lưu từ snapshot tới hệ thống bên ngoài. Mạng cô lập phải được kiểm chứng, không chỉ được ghi trong tài liệu.

## 22. Tách bài test đúng đắn khỏi benchmark hiệu năng

Một bài test PostgreSQL chạy trong Docker trên laptop chứng minh SQL và concurrency theo điều kiện đã thiết kế; nó **không tự chứng minh** p99 latency hoặc throughput của cluster production.

Để benchmark đại diện cần xác định:

- Dung lượng, phân bố và độ lệch dữ liệu; tỷ lệ read/write, tập truy cập nóng/lạnh.
- Index, statistics, query planner, cache warmup và schema.
- Cấu hình CPU/RAM/storage/WAL, network latency, số connection và replica.
- Số client đồng thời, transaction length và pattern burst.
- Những thao tác nền như vacuum, checkpoint, backup, migration.
- Chỉ số p50/p95/p99, throughput, error rate, IOPS, lock wait, CPU và pool pending.

Một phép thử benchmark dùng snapshot có dữ liệu đại diện **phải được cô lập và bảo vệ dữ liệu**. Nếu CI bị CPU-throttling ngẫu nhiên, dùng nó để phát hiện hồi quy query count/N+1 thường đáng tin hơn dùng số millisecond tuyệt đối.

Nên ghi rõ trong báo cáo: “test correctness PASS trên PostgreSQL container” không tương đương “đã chứng minh SLO production”.

## 23. CI pipeline: nhiều lớp bằng chứng, một báo cáo dễ đọc

Một pipeline thực tế có thể chia:

```text
Commit / Pull Request
       |
       +--> Unit tests (domain, validation)
       |
       +--> Integration PostgreSQL
       |      - production migrations
       |      - JDBC/JPA mapping
       |      - constraints, permissions
       |      - transaction/concurrency
       |
       +--> Multi-service contract tests
       |      - outbox/inbox/idempotency
       |      - cache/broker
       |
       v
Merge gate / evidence
       |
       +--> Scheduled fault-injection / failover
       +--> Recovery drill / PITR
       +--> Load & performance benchmark
```

Mỗi nhóm cần ghi **đã thử gì, môi trường nào, tiêu chí PASS nào, điều gì nằm ngoài phạm vi**. Ví dụ:

| Kết quả | Phạm vi được chứng minh | Chưa chứng minh |
| --- | --- | --- |
| Unit test PASS | Domain policy và nhánh logic thuần. | SQL/DB khóa và transaction thật. |
| Repository IT PASS | Dialect/schema/constraint/mapping cho fixture. | Failover và RPO/RTO. |
| Concurrency IT PASS | Lịch cạnh tranh đã tạo ở DBMS test. | Mọi lịch giao dịch hoặc tải production. |
| Multi-service IT PASS | Workflow và side effect trong topology test. | Provider production có cùng hành vi mọi lúc. |
| Restore drill PASS | Backup set được restore đến mốc và smoke test. | Mọi backup tương lai cũng tự phục hồi được. |

Nếu CI không có container runtime, không nên âm thầm thay PostgreSQL bằng H2 rồi vẫn gọi đó là “PostgreSQL integration test”. Phải thay đổi hạ tầng CI hoặc báo rõ scope của test giảm, đồng thời giữ một pipeline có DBMS thật trước khi phát hành.

## 24. Debug test flaky: phân biệt lỗi hạ tầng và lỗi concurrency thật

Một số integration test lúc xanh lúc đỏ vì:

- Test dựa vào `Thread.sleep(...)` thay vì synchronization có điều kiện.
- Hàng fixture hoặc database được dùng chung giữa nhiều test chạy parallel.
- Async event chưa xử lý xong nhưng test đã assertion.
- Clock/timezone hoặc thứ tự truy vấn không ổn định.
- Connection pool không đủ cho số worker trong test.
- Container khởi động chưa sẵn sàng hoặc migration chưa hoàn tất.
- Network proxy/fault injection chưa reset sau test.
- Cache đã nóng từ test trước, che N+1 hoặc stale reads.

Hướng điều tra:

1. Gắn run ID và log an toàn cho transaction, SQLSTATE, connection, test case, image version.
2. Dùng latch/barrier/condition poll với deadline thay vì sleep thời gian tùy ý.
3. In trạng thái cuối của DB bằng query sau commit, không chỉ biến tạm trong test.
4. Thu thập thời gian chờ lock, pool pending và migration logs.
5. Chạy lại test ở nhiều lịch/seed có kiểm soát; nếu lỗi chỉ xuất hiện khi chạy parallel, kiểm tra state chia sẻ.
6. Không tăng timeout vô hạn để “xanh” nếu test thực chất đang deadlock.

Một test tốt có thể giải thích **vì sao nó PASS**. Một test chỉ thỉnh thoảng may mắn tạo lịch cạnh tranh cần được cải thiện thiết kế thay vì coi nhiều lần chạy xanh là đủ.

## 25. Bài tập thiết kế test cho dịch vụ đơn hàng Java

Giả sử hệ thống có ba chức năng:

1. `reserve(orderId, sku, quantity)` trừ tồn kho và ghi reservation.
2. `confirm(orderId)` chuyển trạng thái đơn nếu payment đã xác nhận.
3. Consumer nhận `PaymentConfirmed(eventId, paymentOperationId, orderId)` có thể nhận trùng.

**Yêu cầu:** mọi quyết định ghi được bảo vệ tại database; không giữ hàng quá tồn kho; một request ID không được áp dụng hai lần; event trùng không tạo hai confirmation/outbox; khi commit không rõ kết quả phải đối soát.

Thiết kế môi trường:

```text
PostgreSQL 17 test container (pin theo production)
    - schema/migrations của dự án
    - role order_api và order_worker
    - inventory, orders, reservations, inbox, outbox
    - unique request_id / event_id / payment_operation_id

Java:
    - Spring JDBC/JPA adapter thật
    - application service thật
    - clock/IDs/fixtures kiểm soát được
    - 2 hoặc nhiều connection độc lập khi test concurrent

Broker:
    - test broker hoặc fake có thể gửi duplicate/out-of-order

Safety:
    - không truy cập payment provider production
    - CI secrets test riêng, cleanup theo run ID
```

Ma trận bài test:

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Reserve hợp lệ | Tồn kho 5, yêu cầu 3. | Giảm còn 2, reservation commit cùng transaction. |
| Reserve cạnh tranh | Hai request mỗi bên lấy 4, tồn kho 5. | Tối đa một thành công, tồn kho không âm. |
| Duplicate request | Gửi cùng request ID hai lần. | Không trừ tồn kho hai lần; payload khác bị từ chối. |
| Lỗi insert reservation | Ép unique conflict sau cập nhật tồn kho. | Cả local transaction rollback. |
| DB permission negative | Role API thử `DELETE orders`. | Lỗi quyền, không sửa dữ liệu. |
| Event redelivery | Gửi hai lần cùng event ID. | Inbox ngăn xử lý trùng sau commit. |
| Hai event cùng operation | Hai event ID khác nhau, cùng payment operation. | Business idempotency ngăn tác dụng lặp. |
| Outbox crash | Commit DB rồi dừng relay trước publish. | Relay phục hồi phát lại event bền vững. |
| Unknown commit | Mất ACK sau commit và reconnect. | Đối soát cùng ID ở primary, không tạo thao tác mới. |
| Tenant isolation | Role A cố đọc đơn tenant B. | Không lộ dữ liệu B. |

Với mỗi test, ghi rõ **cách tạo lịch lỗi, bằng chứng quan sát và tài nguyên phải cleanup**. Không khẳng định đã test unknown commit nếu chỉ ném exception **trước khi ghi**.

## 26. Checklist review môi trường test persistence

1. **DBMS đại diện:** đúng engine/major version, dialect và driver quan trọng chưa?
2. **Schema thật:** migration production có chạy từ database trống và kiểm tra version chưa?
3. **Configuration:** isolation, timezone, collation, extension, RLS và pool có khác biệt ảnh hưởng bài test không?
4. **Dữ liệu:** fixture độc lập, có giá trị biên, Unicode, quan hệ và số lượng phù hợp chưa?
5. **An toàn:** JDBC URL/secret có chắc không thể trỏ vào production không?
6. **Role:** đã test bằng credential runtime và có negative tests chưa?
7. **Transaction:** biết khi nào commit/rollback, test thread có bao trùm async/REQUIRES_NEW không?
8. **Concurrency:** có hai connection riêng, barrier và assertion sau commit không?
9. **Error handling:** có thử unique conflict, deadlock, timeout và trạng thái commit chưa rõ không?
10. **External services:** broker/cache/payment/mail có cô lập và không gây side effect thật không?
11. **Cleanup:** test song song không xóa dữ liệu hoặc container của nhau?
12. **Observability:** SQLSTATE, transaction state, query count và logs được thu thập mà không lộ secrets?
13. **Reproducibility:** pin image/version, clock/seed và có thông tin tái hiện test thất bại?
14. **Scope:** đã ghi rõ phần nào không được mô phỏng, như failover nhiều nút hoặc tải production?

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao unit test của một `PurchasePolicy` không cần PostgreSQL, nhưng test `UPDATE ... WHERE available >= ?` nên chạy với PostgreSQL?

Vì policy thuần chỉ kiểm tra quy tắc Java, còn SQL phải được thực thi bởi DBMS với dialect, khóa, transaction và constraint thật để chứng minh bất biến tại thời điểm ghi.

**Câu 2.** Test dùng H2 chạy xanh với câu JPQL. Có thể kết luận migration PostgreSQL sẽ chạy được và RLS đúng không?

**Không.** H2 có SQL dialect, quyền, isolation và tính năng khác. Cần test PostgreSQL thực với migration và role/RLS tương ứng.

**Câu 3.** Vì sao `@Transactional` trên test method không đảm bảo mọi async consumer cũng rollback?

Vì consumer có thể chạy thread, connection và transaction riêng; local rollback của test không điều phối các tác dụng đã commit ở đó.

**Câu 4.** Hai thread cùng gọi `reserve`, cuối cùng tồn kho không âm. Đã chứng minh mọi lịch cạnh tranh đều an toàn chưa?

**Chưa.** Chỉ chứng minh lịch đã xảy ra trong lần chạy. Cần điều kiện cập nhật/constraint đúng và test lịch xen kẽ có kiểm soát, bổ sung review giao thức concurrency.

**Câu 5.** Vì sao nên dùng migration thật thay vì `ddl-auto: create-drop` trong integration test?

Vì schema test tự sinh có thể khác schema deploy: thiếu index/constraint/permission, sai loại cột hoặc bỏ qua thứ tự migration.

**Câu 6.** Một test PostgreSQL container chứng minh được RPO/RTO khi failover cluster production chưa?

**Chưa.** Cần topology replication/backup/recovery, fault injection và đo khôi phục riêng; container đơn không mô phỏng điều đó.

**Câu 7.** Vì sao reset database bằng `TRUNCATE` khi các test chạy song song có thể gây flaky?

Vì một test có thể xóa fixture của test khác; phải cô lập database/schema hoặc điều phối phù hợp.

**Câu 8.** Khi PostgreSQL role runtime báo permission denied trong test, có nên đổi testcase sang superuser để nó xanh không?

**Không.** Phải xác định GRANT/migration cần thiết; việc chạy bằng superuser sẽ che lỗi quyền của production.

**Câu 9.** Một bài test cố ý disconnect database trước `COMMIT` có chứng minh được mất ACK sau khi commit không?

**Không.** Cần xác lập đúng điểm lỗi: database đã commit nhưng phản hồi mất, rồi đối soát qua connection mới. Hai kịch bản có kết luận khác nhau.

**Câu 10.** Vì sao một môi trường “có PostgreSQL thật” vẫn có thể chưa đủ đại diện?

Vì schema, cấu hình isolation, role, extension, topology replica, driver, dữ liệu hoặc những tài nguyên ngoài DB có thể khác các yếu tố mà use case dựa vào.

## Kết luận

**Dùng môi trường cô lập với hệ lưu trữ đại diện** là cách biến bài kiểm thử persistence thành bằng chứng về SQL, transaction, isolation, khóa, schema, quyền và lỗi tại ranh giới ghi — chứ không chỉ là bằng chứng về hành vi của mock. Với Java, PostgreSQL/Testcontainers, migration thật, fixture độc lập, JUnit/Spring integration test và các phép thử nhiều transaction giúp phát hiện những lỗi mà unit test khó mô phỏng.

Hãy thiết kế môi trường theo **điều kiện cần chứng minh**, giữ nó tách biệt production và mọi hệ thống ngoài, đo được kết quả sau commit, ghi rõ những giới hạn còn chưa mô phỏng, rồi bổ sung fault-injection, failover, recovery drill và benchmark khi rủi ro yêu cầu. Một bộ test đáng tin không phải bộ có nhiều container nhất, mà là bộ **tái lập được, an toàn, đại diện đúng và trả lời rõ ràng một bất biến nghiệp vụ có được bảo vệ hay không**.
