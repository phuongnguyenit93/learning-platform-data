# Phân biệt kiểm thử nghiệp vụ với kiểm thử tích hợp lưu trữ

Một bài kiểm thử có thể xác nhận **“không được tạo đơn hàng với số lượng âm”** chỉ bằng Java service và một repository giả. Một bài khác cần xác nhận **“khi lưu dòng hàng thứ hai thất bại, đơn hàng vừa được INSERT trước đó cũng phải rollback trên PostgreSQL”**. Cả hai đều góp phần bảo đảm tính đúng của tầng persistence, nhưng chúng kiểm tra **những rủi ro khác nhau**.

Bài thuộc chương **Kiểm thử lưu trữ** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu chung của mô-đun là hiểu và thiết kế lưu trữ dữ liệu bền vững trong ứng dụng Java: mô hình dữ liệu, SQL, chỉ mục, giao dịch, cô lập, xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Ở đây, trọng tâm là **khi nào kiểm thử quy tắc nghiệp vụ bằng code thuần**, **khi nào phải chạy qua SQL/driver/database thật**, và cách kết hợp cả hai để tránh tự tin sai.

Ví dụ sử dụng **Java 17+, JUnit Jupiter, JDBC và PostgreSQL**. Một số đoạn mã minh họa từng phần của dự án; các dependency, file Java, fixture và schema phải được ghép đúng trong dự án thực tế.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt mục đích của **kiểm thử nghiệp vụ (business tests)** với **kiểm thử tích hợp lưu trữ (persistence integration tests)**.
2. Hiểu **test intent** và **test scope** là hai trục khác nhau: không phải mọi business test đều là unit test, cũng không phải mọi integration test đều chỉ kiểm tra hạ tầng.
3. Chọn fake/mock/stub repository cho các quy tắc domain, không nhầm kết quả fake với độ bền dữ liệu DBMS.
4. Viết test JDBC/PostgreSQL xác minh SQL, mapping, constraint, commit/rollback và dữ liệu sau thao tác lỗi.
5. Biết khi nào cần Testcontainers, migration thật, test concurrency, isolation, retry và pool.
6. Tránh test sai do database giả khác production, transaction test tự rollback, fixture dùng chung hoặc assertion chỉ kiểm tra exception.
7. Thiết kế môi trường test cô lập, kiểm tra dữ liệu, cleanup và pipeline CI ổn định.
8. Xây dựng ma trận test theo **rủi ro persistence** thay vì viết nhiều bài test trùng chức năng.

## 2. Hai câu hỏi không được đánh đồng

**Kiểm thử đang chứng minh điều gì?** Đây là **intent**. Ví dụ: số tiền phải tính đúng, không tạo đơn trống, không ghi nửa chừng một nghiệp vụ.

**Test đang chạy những thành phần thật nào?** Đây là **scope**. Ví dụ: Java service với fake repository, hay service/repository/JDBC driver/PostgreSQL thật.

Vì vậy, câu “business test = unit test; integration test = không kiểm tra nghiệp vụ” là quá đơn giản.

| Kịch bản | Mục tiêu | Thành phần thật | Cách gọi hữu ích |
|---|---|---|---|
| CreateOrderService từ chối đơn trống với fake repo | Business validation | Java service | Business-focused unit test |
| Service tính tổng tiền đúng với fake repo | Quy tắc domain | Java service | Business-focused unit test |
| JdbcOrderRepository chèn rồi đọc lại hàng | Hợp đồng SQL/mapping | JDBC + PostgreSQL | Persistence integration test |
| Child INSERT lỗi, kiểm tra parent rollback | Tính nguyên tử lưu trữ | JDBC + PostgreSQL | Persistence integration test |
| HTTP API đặt đơn qua PostgreSQL thật | Nghiệp vụ đầu-cuối và persistence | Controller, service, DB | Business integration/end-to-end test |
| Mockito ném SQLException giả để service báo lỗi phù hợp | Nhánh xử lý lỗi | Java, mock | Unit test của error handling |

Một integration test vẫn có thể kiểm chứng business invariant; một unit test vẫn có thể kiểm tra một hàm mapper. Phân loại tốt nhất dựa trên **bằng chứng mà test thực sự cung cấp**.

## 3. So sánh hai nhóm kiểm thử thường dùng

| Khía cạnh | Business-focused unit test | Persistence integration test |
|---|---|---|
| Câu hỏi chính | Service/domain quyết định đúng không? | Ghi/đọc qua SQL, driver và database có đúng không? |
| Repository | Fake/mock/stub | Adapter thật |
| Database | Không cần | Database thật, ưu tiên cùng engine với production |
| Tốc độ | Thường rất nhanh | Chậm hơn vì setup DB/schema/I/O |
| Độ ổn định | Cao nếu code thuần, không dùng clock ngẫu nhiên | Cần kiểm soát data fixture, timing và transaction |
| SQL syntax/dialect | Không kiểm tra | Phát hiện nếu SQL thật được thực thi |
| Constraint/foreign key | Chỉ mô phỏng bằng code giả | Kiểm tra constraint thật |
| Commit/rollback | Không chứng minh kết quả trên DB | Kiểm tra trạng thái thực sau commit/rollback |
| Lock/isolation/deadlock | Không mô phỏng đáng tin bằng map | Có thể kiểm tra trong DB thật với nhiều Connection |
| Connection leak/timeouts | Không mô phỏng chính xác | Có thể kiểm tra cùng driver/pool/DB |
| Lỗi công thức nghiệp vụ | Rất phù hợp, chỉ rõ nguyên nhân | Cũng có thể bắt, nhưng chậm và phạm vi rộng |
| Điểm mạnh | Nhanh, phủ nhiều biên, dễ định vị lỗi | Bắt lỗi ở ranh giới hệ thống thật |

**Fake trả đúng dữ liệu là bằng chứng fake hoạt động như đã viết**, không phải bằng chứng lệnh SQL production sẽ thành công.

## 4. Sơ đồ hai đường kiểm thử

~~~text
           HTTP / Scheduler
                  |
            Application Service
             (business rules)
                  |
             Repository Port
                 /    \
                /      \
        Fake Repository  JDBC Repository
               |              |
         Unit tests       DataSource/Driver
                                |
                           PostgreSQL
                                |
                      Integration tests
~~~

Repository port là interface mà domain/service phụ thuộc. Adapter hiện thực port bằng SQL/JDBC.

Với fake, kiểm thử có thể xác nhận service truyền dữ liệu đã được validate và tính tổng đúng. Với database thật, test xác nhận cách adapter dùng transaction, mapping và ràng buộc của DBMS.

**HashMap trong JVM không có WAL, SQLSTATE, index, lock hay failover.** Test chỉ thấy dữ liệu được lưu trong một HashMap không thể chứng minh dữ liệu bền vững qua crash.

## 5. Ví dụ xuyên suốt: tạo đơn hàng có nhiều dòng

Giả sử nghiệp vụ tạo đơn của một tenant:

- Tenant ID và operation ID phải hợp lệ.
- Có ít nhất một dòng hàng.
- SKU không trống, quantity lớn hơn 0, unitPrice không âm.
- **total = tổng quantity × unitPrice** tính chính xác bằng BigDecimal.
- Dữ liệu không hợp lệ phải bị từ chối **trước khi gọi repository**.
- Khi lưu thật, bản ghi đơn và **toàn bộ các dòng hàng** phải commit/rollback nguyên tử.

Như vậy có hai hợp đồng khác nhau:

**Hợp đồng nghiệp vụ:** validation và tính total.

**Hợp đồng lưu trữ:** INSERT parent/child đúng, khóa ngoại và unique được thực thi, rollback toàn transaction khi một dòng hàng lỗi.

### 5.1. Domain types và repository port

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderLine(
        String sku, int quantity, BigDecimal unitPrice) {}

public record NewOrder(
        long tenantId, String operationId, List<OrderLine> lines) {}

public interface OrderRepository {
    long create(NewOrder request, BigDecimal total);
}
~~~

Các khai báo được đặt trong những file Java phù hợp khi triển khai. **operationId** là định danh ổn định cho yêu cầu; nó chưa đủ chống ghi trùng nếu repository/database không có unique constraint và giao thức đối soát.

### 5.2. Service sở hữu business rules

~~~java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;

public final class CreateOrderService {
    private final OrderRepository repository;

    public CreateOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public long create(NewOrder request) {
        if (request == null || request.tenantId() <= 0
                || request.operationId() == null
                || request.operationId().isBlank()
                || request.lines() == null
                || request.lines().isEmpty()) {
            throw new IllegalArgumentException("Đơn hàng không hợp lệ");
        }

        BigDecimal total = BigDecimal.ZERO;
        Set<String> seenSku = new HashSet<>();

        for (OrderLine line : request.lines()) {
            if (line == null || line.sku() == null
                    || line.sku().isBlank()
                    || line.quantity() <= 0
                    || line.unitPrice() == null
                    || line.unitPrice().signum() < 0
                    || !seenSku.add(line.sku())) {
                throw new IllegalArgumentException("Dòng hàng không hợp lệ");
            }

            total = total.add(line.unitPrice()
                    .multiply(BigDecimal.valueOf(line.quantity())));
        }

        return repository.create(request, total);
    }
}
~~~

Service không import JDBC, không mở Connection, không biết tên bảng PostgreSQL. Nó có thể kiểm thử nhanh bằng Java thuần.

**Giới hạn ví dụ:** hệ thống thật cần thêm currency, rounding policy, quyền tenant, sản phẩm tồn tại hay không, discount/tax và trạng thái order. Đây cũng là những business rules nên có test riêng.

## 6. Business unit test với fake repository

Fake tối giản để ghi lại lời gọi:

~~~java
import java.math.BigDecimal;

public final class CapturingOrderRepository implements OrderRepository {
    int calls;
    NewOrder lastRequest;
    BigDecimal lastTotal;

    @Override
    public long create(NewOrder request, BigDecimal total) {
        calls++;
        lastRequest = request;
        lastTotal = total;
        return 1001L;
    }
}
~~~

JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class CreateOrderServiceTest {
    @Test
    void sumsPriceAndCallsRepositoryOnce() {
        var fake = new CapturingOrderRepository();
        var service = new CreateOrderService(fake);

        long id = service.create(new NewOrder(
            7L, "request-001", List.of(
                new OrderLine("BOOK", 2, new BigDecimal("12.50")),
                new OrderLine("PEN", 3, new BigDecimal("1.20"))
            )
        ));

        assertEquals(1001L, id);
        assertEquals(1, fake.calls);
        assertEquals(0, fake.lastTotal.compareTo(
                new BigDecimal("28.60")));
        assertEquals("request-001", fake.lastRequest.operationId());
    }

    @Test
    void rejectsZeroQuantityWithoutCallingRepository() {
        var fake = new CapturingOrderRepository();
        var service = new CreateOrderService(fake);

        assertThrows(IllegalArgumentException.class, () ->
            service.create(new NewOrder(
                7L, "request-002", List.of(
                    new OrderLine("BOOK", 0, new BigDecimal("12.50"))
                )
            ))
        );

        assertEquals(0, fake.calls);
    }

    @Test
    void rejectsDuplicateSkuBeforePersistence() {
        var fake = new CapturingOrderRepository();
        var service = new CreateOrderService(fake);

        assertThrows(IllegalArgumentException.class, () ->
            service.create(new NewOrder(
                7L, "request-003", List.of(
                    new OrderLine("BOOK", 1, BigDecimal.ONE),
                    new OrderLine("BOOK", 2, BigDecimal.ONE)
                )
            ))
        );

        assertEquals(0, fake.calls);
    }
}
~~~

Các test này chứng minh service **tính đúng total**, từ chối input sai và không gọi repository khi invalid.

Chúng **không chứng minh** SQL INSERT chạy được, khóa ngoại đúng, NUMERIC không mất giá trị khi lưu, Connection được đóng, hoặc transaction rollback nếu INSERT dòng hàng thứ hai lỗi.

### 6.1. Fake, mock, stub và spy

- **Stub:** cung cấp phản hồi cố định để test một nhánh.
- **Fake:** implementation đơn giản hoạt động được, ví dụ lưu map trong bộ nhớ.
- **Mock:** theo dõi và xác minh những tương tác mong đợi.
- **Spy:** quan sát cuộc gọi trên implementation thật hoặc đối tượng được bọc.

Không cần dùng Mockito cho mọi thứ. Fake ngắn thường dễ đọc. Nếu dùng mock, hãy verify **tương tác có ý nghĩa**, không kiểm tra mọi lời gọi nội bộ khiến test gãy vì refactor vô hại.

## 7. Các câu hỏi buộc phải chạy database thật

Muốn chứng minh các vấn đề sau, test phải đi qua các thành phần liên quan:

1. Cú pháp PostgreSQL, placeholder, generated key có đúng không?
2. Mapping Java BigDecimal và PostgreSQL NUMERIC có giữ giá trị chính xác không?
3. Ràng buộc UNIQUE, FOREIGN KEY, CHECK có thực sự chặn dữ liệu sai?
4. Lỗi child INSERT có rollback parent và mọi child trước đó không?
5. PreparedStatement dùng tham số có chống SQL injection ở vị trí giá trị không?
6. READ COMMITTED, SERIALIZABLE, SELECT FOR UPDATE tác động thật ra sao?
7. Transaction retry có mở **attempt mới** và đọc lại dữ liệu không?
8. Migration production có tạo bảng/constraint mà repository cần không?
9. Connection pool có trả slot sau exception và không rò session settings không?
10. Query có dùng index phù hợp với dữ liệu và statistics thực tế không?

Một unit test của fake không thể xác minh hợp đồng JDBC driver hoặc cơ chế transaction của DBMS.

### 7.1. Database giả khác engine có thể khiến test xanh sai

H2/in-memory database có thể rất tiện cho test đơn giản, nhưng không nhất thiết giống PostgreSQL về:

- INSERT ... RETURNING, ON CONFLICT, JSONB, array và cú pháp đặc thù.
- Generated keys, sequence, type casting, timestamp/timezone.
- Ràng buộc, collation, isolation, row lock, deadlock và SQLSTATE.
- DDL transactional, CREATE INDEX CONCURRENTLY và migration.
- Optimizer, statistics, execution plan và hiệu năng.

H2 không vô dụng; chỉ **không dùng kết quả H2 để khẳng định chắc những tính năng đặc thù PostgreSQL đã đúng**. Với rủi ro cần xác minh trên PostgreSQL, dùng chính PostgreSQL ở môi trường test cô lập.

## 8. Schema minh họa để test JDBC adapter

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    total_amount NUMERIC(14, 2) NOT NULL
        CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL
        CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, sku)
);

CREATE INDEX orders_tenant_id_idx
    ON orders (tenant_id, id);
~~~

**Những rủi ro thật cần test:**

- operation_id trùng sẽ bị unique constraint từ chối.
- Hai dòng của cùng order có cùng SKU vi phạm PRIMARY KEY(order_id, sku).
- order_items trỏ order không tồn tại vi phạm FOREIGN KEY.
- Đơn và dòng hàng phải cùng COMMIT/ROLLBACK.
- NUMERIC(14,2) không được ngầm coi như double trong Java.

Trên production, schema này nên xuất phát từ **versioned migrations thực**. DDL ở đây nhằm minh họa hợp đồng cần test, không thay thế test chạy chuỗi migration của dự án.

## 9. JDBC adapter: INSERT parent và child trong một transaction

Để test đúng transaction, cần một adapter thực sự dùng SQL, Connection và commit/rollback. Ví dụ này hiện thực OrderRepository bằng PostgreSQL với **INSERT ... RETURNING id**.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JdbcOrderRepository implements OrderRepository {
    private final DataSource dataSource;

    public JdbcOrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public long create(NewOrder request, BigDecimal total) {
        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new IllegalStateException(
                        "Adapter này yêu cầu transaction mới");
            }
            connection.setAutoCommit(false);

            boolean commitAttempted = false;
            boolean transactionEnded = false;
            try {
                long orderId;
                String insertOrder = """
                    INSERT INTO orders
                        (tenant_id, operation_id, total_amount)
                    VALUES (?, ?, ?)
                    RETURNING id
                    """;

                try (PreparedStatement stmt =
                             connection.prepareStatement(insertOrder)) {
                    stmt.setLong(1, request.tenantId());
                    stmt.setString(2, request.operationId());
                    stmt.setBigDecimal(3, total);

                    try (ResultSet rows = stmt.executeQuery()) {
                        if (!rows.next()) {
                            throw new IllegalStateException(
                                    "DB không trả order ID");
                        }
                        orderId = rows.getLong("id");
                    }
                }

                String insertItem = """
                    INSERT INTO order_items
                        (order_id, sku, quantity, unit_price)
                    VALUES (?, ?, ?, ?)
                    """;

                try (PreparedStatement stmt =
                             connection.prepareStatement(insertItem)) {
                    for (OrderLine line : request.lines()) {
                        stmt.setLong(1, orderId);
                        stmt.setString(2, line.sku());
                        stmt.setInt(3, line.quantity());
                        stmt.setBigDecimal(4, line.unitPrice());
                        stmt.executeUpdate();
                    }
                }

                commitAttempted = true;
                connection.commit();
                transactionEnded = true;
                return orderId;

            } catch (SQLException | RuntimeException failure) {
                if (!commitAttempted) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw new PersistenceException(
                        "Không thể lưu đơn hàng", failure);
            } finally {
                if (transactionEnded) {
                    connection.setAutoCommit(true);
                }
            }
        } catch (SQLException failure) {
            throw new PersistenceException(
                    "Lỗi kết nối hoặc cleanup JDBC", failure);
        }
    }
}

final class PersistenceException extends RuntimeException {
    PersistenceException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

**Ý nghĩa của ví dụ:**

- INSERT orders và INSERT từng order_items dùng **cùng một Connection/transaction**.
- Khi một child INSERT lỗi **trước commit**, adapter cố rollback và không để order parent đã chèn nằm lại.
- PreparedStatement bind giá trị, ResultSet đọc generated ID, try-with-resources đóng tài nguyên.
- Nếu lỗi xảy ra **khi commit**, kết quả có thể chưa rõ. Ví dụ không tự đánh dấu chắc chắn rollback hoặc retry vô điều kiện. Production phải phân loại unknown commit outcome, đối soát operation_id và quản lý connection không đáng tin theo pool/driver.
- Khi dùng Spring **@Transactional**, không tự gọi commit/rollback trên Connection được Spring transaction manager sở hữu. Cần adapter tham gia transaction của framework.

**Ví dụ tập trung vào hợp đồng JDBC**, chưa đủ để xử lý idempotency hoàn chỉnh trong nghiệp vụ đặt hàng. UNIQUE(operation_id) là một điều kiện cần; khi nhận request trùng phải so sánh nội dung và trả kết quả trước đó theo hợp đồng, không chỉ ném exception.

### 9.1. Sai lầm mà unit test không phát hiện

Nếu một adapter dùng:

~~~text
Connection A: INSERT orders -> COMMIT
Connection B: INSERT order_items dòng 1 -> COMMIT
Connection B: INSERT order_items dòng 2 -> lỗi UNIQUE
~~~

thì parent và dòng 1 có thể vẫn còn. Unit test chỉ thấy repository.create() được gọi một lần; nó **không chứng minh** dữ liệu thực có còn nhất quán hay không.

Một persistence integration test đúng phải kiểm tra **trạng thái database sau khi lỗi**, không dừng ở việc assertThrows đã nhận exception.

## 10. Môi trường PostgreSQL thật với Testcontainers

**Testcontainers** cho phép test runner tạo một PostgreSQL container cô lập rồi lấy JDBC URL, user/password và thực thi migrations/fixture. Có thể dùng một PostgreSQL test instance riêng thay thế, miễn là quản lý cô lập, reset và quyền an toàn.

~~~text
JUnit Jupiter
       |
       v
Testcontainers PostgreSQL
       |
       +-- Apply migration production
       +-- Seed fixture
       |
       v
JdbcOrderRepository -> JDBC Driver -> PostgreSQL
       |
       v
SELECT kiểm chứng bằng Connection riêng
       |
       v
Cleanup / Container stop
~~~

**Không chạy integration test phá dữ liệu trên production hoặc staging dùng chung**. Một lệnh TRUNCATE, DROP TABLE hoặc test deadlock chỉ phù hợp trong database test được cấp quyền riêng.

### 10.1. Dependencies minh họa

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.postgresql:postgresql")

    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
    runtimeOnly("org.postgresql:postgresql")
}

tasks.test {
    useJUnitPlatform()
}
~~~

**Lưu ý:** đây là ví dụ tên dependency, cần version/BOM tương thích và module PostgreSQL tương ứng với Flyway/Testcontainers thực tế. Một số major version Testcontainers thay đổi package/module của PostgreSQLContainer. Hãy kiểm tra imports theo phiên bản dự án. Database image nên được pin ở một phiên bản phù hợp với production, không dùng tag trôi nổi một cách vô ý.

### 10.2. Khởi động test database và chạy migration thật

Ví dụ theo API thông dụng của **Testcontainers 1.x**. Với phiên bản mới hơn, các imports/API có thể khác.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.postgresql.ds.PGSimpleDataSource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class JdbcOrderRepositoryIntegrationTest {
    @Container
    static PostgreSQLContainer<?> pg =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static DataSource dataSource;

    @BeforeAll
    static void prepareDatabase() {
        PGSimpleDataSource ds = new PGSimpleDataSource();
        ds.setURL(pg.getJdbcUrl());
        ds.setUser(pg.getUsername());
        ds.setPassword(pg.getPassword());
        dataSource = ds;

        Flyway.configure()
                .dataSource(dataSource)
                .locations("classpath:db/migration")
                .load()
                .migrate();
    }

    @BeforeEach
    void clearBusinessTables() throws SQLException {
        try (Connection connection = dataSource.getConnection();
             Statement stmt = connection.createStatement()) {
            stmt.execute(
                "TRUNCATE TABLE order_items, orders RESTART IDENTITY CASCADE");
        }
    }

    @Test
    void insertsParentAndAllChildren() throws SQLException {
        var repo = new JdbcOrderRepository(dataSource);
        var draft = new NewOrder(
                7L, "op-success-1", List.of(
                    new OrderLine("BOOK", 2, new BigDecimal("12.50")),
                    new OrderLine("PEN", 3, new BigDecimal("1.20"))
                ));

        long id = repo.create(draft, new BigDecimal("28.60"));

        try (Connection c = dataSource.getConnection();
             PreparedStatement stmt = c.prepareStatement("""
                  SELECT o.total_amount, COUNT(i.sku) AS item_count
                  FROM orders o
                  LEFT JOIN order_items i ON i.order_id = o.id
                  WHERE o.id = ? AND o.tenant_id = ?
                  GROUP BY o.id, o.total_amount
                  """)) {
            stmt.setLong(1, id);
            stmt.setLong(2, 7L);
            try (ResultSet rows = stmt.executeQuery()) {
                assertTrue(rows.next());
                assertEquals(0, rows.getBigDecimal("total_amount")
                        .compareTo(new BigDecimal("28.60")));
                assertEquals(2L, rows.getLong("item_count"));
                assertFalse(rows.next());
            }
        }
    }

    @Test
    void rollsBackParentWhenChildViolatesUniqueKey()
            throws SQLException {
        var repo = new JdbcOrderRepository(dataSource);

        // Gọi trực tiếp adapter với input sai để kiểm tra
        // ràng buộc DB/rollback, không gọi service validation.
        var draft = new NewOrder(7L, "op-rollback-1", List.of(
                new OrderLine("BOOK", 1, BigDecimal.ONE),
                new OrderLine("BOOK", 2, BigDecimal.ONE)
        ));

        assertThrows(PersistenceException.class,
                () -> repo.create(draft, new BigDecimal("3.00")));

        try (Connection c = dataSource.getConnection();
             PreparedStatement stmt = c.prepareStatement(
                "SELECT COUNT(*) FROM orders WHERE operation_id = ?")) {
            stmt.setString(1, "op-rollback-1");
            try (ResultSet rows = stmt.executeQuery()) {
                assertTrue(rows.next());
                assertEquals(0L, rows.getLong(1));
            }
        }
    }
}
~~~

**Điều kiện quan trọng để ví dụ chạy:**

- Các kiểu NewOrder, OrderLine, JdbcOrderRepository, PersistenceException ở phần trước được đặt trong source/test classpath phù hợp.
- Migration trong **classpath:db/migration** thực sự tạo hai bảng/constraint như phần 8; ví dụ này **không tự tạo file migration**.
- Môi trường chạy test có engine container hỗ trợ Testcontainers và dependency/import phù hợp với phiên bản.
- Chạy class này **tuần tự hoặc có isolation riêng**; phương thức TRUNCATE trong BeforeEach không an toàn khi nhiều test cùng dùng database và chạy song song.
- Tài khoản test có quyền DDL/migration, TRUNCATE theo phạm vi test database; không sử dụng production credentials.

### 10.3. Bài test đã chứng minh điều gì?

Bài **insertsParentAndAllChildren** chứng minh adapter có thể ghi qua JDBC vào PostgreSQL với schema thực và một Connection đọc độc lập có thể đọc lại parent/child với amount đúng.

Bài **rollsBackParentWhenChildViolatesUniqueKey** chứng minh câu INSERT child trùng SKU bị DB từ chối và parent đã chèn trong transaction thất bại không còn tồn tại **sau khi method kết thúc và Connection đóng**.

**Chỉ kiểm tra assertThrows là chưa đủ**: một adapter bị lỗi transaction vẫn có thể ném exception trong khi parent đã commit. Assertion SELECT COUNT = 0 mới trực tiếp kiểm tra trạng thái sau lỗi.

Để chắc hơn, có thể kiểm tra riêng **SQLSTATE 23505** từ cause chain, số child bằng 0, và sau thất bại vẫn có thể ghi một đơn hợp lệ mới; nhưng không khóa test cứng vào thông điệp error có thể thay đổi giữa driver/localization.

## 11. Test schema migration cùng repository

Một schema test đúng không nên tạo một bảng tối giản hoàn toàn khác production. Nếu production dùng Flyway/Liquibase, test integration phải áp dụng **cùng chuỗi migration** mà application sẽ dùng khi deploy.

Hai hướng test cần thiết:

**Bootstrap test:** tạo database rỗng, chạy V1...Vn, xác nhận service/repository hoạt động và constraints đúng.

**Upgrade test:** bắt đầu từ schema/fixture đại diện production ở Vn-1 (hoặc mốc được hỗ trợ), chạy các migration còn thiếu, xác nhận dữ liệu cũ được giữ và code mới hoạt động.

Ví dụ những lỗi chỉ phát hiện khi upgrade từ dữ liệu cũ:

- Một cột mới chuyển thành NOT NULL trong khi hàng cũ vẫn NULL.
- Tạo UNIQUE index thất bại vì dữ liệu cũ trùng.
- ALTER COLUMN làm mất precision hoặc không cast được một số giá trị.
- View/trigger cũ phụ thuộc cột bị rename/drop.
- Backfill chưa hoàn tất mà app đã đọc cột mới.
- Có instance app cũ vẫn đang chạy trong giai đoạn expand-migrate-contract.

Nếu integration test chỉ chạy với schema được tự tạo trong BeforeEach mà không bao giờ chạy migration, nó **không chứng minh đường triển khai schema production hợp lệ**.

### 11.1. Khi nào cần kiểm tra read/write compatibility?

Trong rolling deployment, có thể có **App v1 và v2 cùng đọc/ghi một database**. Test nên có kịch bản:

1. App v1 hoạt động với schema mới mở rộng.
2. App v2 ghi cả cột cũ/mới hoặc có cơ chế đồng bộ đúng theo kế hoạch.
3. Dữ liệu đã backfill tương thích với hai phiên bản trong cửa sổ triển khai.
4. Chỉ sau khi app v1 và các job cũ không còn phụ thuộc, mới chạy migration contract.

Đây vừa là test về **hợp đồng nghiệp vụ giữa các phiên bản**, vừa là test tích hợp với schema thật.

## 12. Transaction test: điều gì có thể bị che khuất?

### 12.1. Test framework tự rollback không thay thế kiểm tra commit thật

Một số framework cho phép đánh dấu test bằng **@Transactional** và tự rollback transaction của test sau khi kết thúc. Điều này tiện để làm sạch dữ liệu nhưng có thể **che giấu lỗi commit-time** hoặc kiểm tra sai phạm vi transaction.

Ví dụ:

~~~java
// Minh họa với Spring Test.
// Nếu test đã ở transaction được tự rollback,
// nó có thể chưa từng kiểm tra COMMIT thật của ứng dụng.
@Transactional
@Test
void createsOrder() {
    service.create(...);
    // assert ngay trong transaction của test
}
~~~

Một transaction đang chạy có thể nhìn thấy chính dữ liệu chưa commit của nó. Nếu cần chứng minh khả năng nhìn thấy sau commit, hãy chạy **không bọc toàn bộ test trong một outer transaction tự rollback**, hoặc dùng cơ chế kết thúc transaction có chủ đích rồi kiểm tra bằng **Connection độc lập**.

### 12.2. Check trạng thái sau rollback bằng Connection khác

Đối với test transaction:

1. Gọi thao tác adapter có chủ đích gây lỗi ở giữa các câu SQL.
2. Bảo đảm adapter hoàn thành cleanup (hoặc trả lỗi).
3. Mở **Connection mới** đến cùng test DB.
4. Dùng SELECT kiểm tra parent/child thực sự không tồn tại.
5. Kiểm tra một thao tác hợp lệ tiếp theo vẫn chạy được.

Đừng coi “một mock đã nhận rollback()” là bằng chứng database thực rollback. Mock chỉ chứng minh method rollback() được gọi, không chứng minh các câu lệnh trước đó cùng sử dụng đúng Connection.

### 12.3. Nhiều Connection khác một transaction

Nếu service mở Connection A chèn order, Connection B chèn items, cả hai tự commit riêng, việc đặt cùng correlation ID không khiến chúng thuộc một transaction. Integration test với lỗi giữa hai câu INSERT có thể phát hiện dữ liệu được commit từng phần.

### 12.4. Lỗi gần COMMIT và kết quả chưa xác định

Khi client gửi COMMIT rồi mất kết nối, **SQLException không chứng minh DB chưa commit**. Test hủy mạng có thể tạo trạng thái không xác định; ứng dụng cần **operation_id ổn định, UNIQUE và đối soát**.

Nếu test chỉ mock commit() luôn ném exception, nó kiểm tra nhánh xử lý Java nhưng **không chứng minh** DB thật đã hay chưa commit. Để kiểm tra resilience, cần fault injection có kiểm soát và verify dữ liệu/operation ID sau khi cluster ổn định.

## 13. Kiểm thử SQL constraint, mapping và dữ liệu biên

Nên tạo bảng test case theo tính chất DB:

| Đối tượng | Dữ liệu/kịch bản | Assertion |
|---|---|---|
| BIGINT ID | Giá trị lớn hơn giới hạn int | Java đọc đúng long |
| NUMERIC money | 0.01, 999999.99, các scale khác nhau | BigDecimal chính xác, rounding đúng contract |
| VARCHAR/TEXT | Unicode có dấu, dấu nháy, emoji | Lưu/đọc đúng và PreparedStatement an toàn |
| Nullable column | NULL và 0/chuỗi rỗng | Không nhầm SQL NULL với giá trị mặc định |
| UNIQUE | Trùng operation_id | DB từ chối đúng và không ghi nửa chừng |
| FOREIGN KEY | Child trỏ parent không có | Không tạo orphan |
| CHECK | quantity = 0 hoặc âm | DB từ chối |
| TIMESTAMPTZ | Mốc thời gian ở các timezone khác nhau | Quy tắc Instant/timezone đúng |
| JSONB/array nếu có | Nested JSON, key thiếu, null | Mapping và truy vấn đúng PostgreSQL |
| Generated key | INSERT ... RETURNING | Đúng ID của bản ghi vừa lưu |
| ORDER BY/pagination | Nhiều hàng có cùng timestamp | Phân trang không mất/trùng hàng theo contract |
| Tenant filter | Hai tenant có ID entity giống nhau | Không đọc/sửa nhầm tenant |

Kiểm tra bằng **assertion trên giá trị đã đọc lại**, không chỉ dựa vào số dòng được JDBC báo là cập nhật. Với trường hợp cần đối soát money, không dùng double equality cho những giá trị thập phân có nghĩa tài chính.

### 13.1. SQL injection và query động

Một test dùng chuỗi chứa dấu nháy như **O'Brien** giúp phát hiện lỗi escaping; nhưng một test đi qua mock repository không chứng minh SQL injection đã được phòng. Test JDBC cần gọi query thật qua PreparedStatement và đọc đúng bản ghi.

Placeholder chuẩn JDBC dùng cho **giá trị**, không thay tên bảng/cột hoặc ORDER BY. Với query động, test input không nằm trong whitelist phải bị từ chối từ tầng ứng dụng trước khi tạo SQL.

### 13.2. Type mapping khác khi DBMS thay đổi

Nếu một test trên database giả cho rằng kiểu TIMESTAMP là LocalDateTime nhưng production dùng TIMESTAMPTZ với Instant, có thể xuất hiện sai lệch múi giờ. Test integration trên driver/DBMS thật và quy ước timezone cố định giúp nhận ra điều này.

## 14. Isolation và concurrency không thể kiểm chứng bằng một fake map đơn luồng

Các lỗi như **lost update, write skew, deadlock, serialization failure** yêu cầu quan sát nhiều transaction thật. Một unit test tuần tự với HashMap chỉ kiểm tra logic xử lý giá trị, không tái tạo được cơ chế khóa/snapshot của PostgreSQL.

### 14.1. Ví dụ hai lần trừ tồn kho

Một bảng:

~~~sql
CREATE TABLE inventory (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

INSERT INTO inventory(sku, quantity)
VALUES ('SKU-1', 1);
~~~

Hai request cùng muốn trừ một đơn vị. Câu SQL an toàn hơn mẫu đọc trước rồi ghi theo snapshot cũ:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = ?
  AND quantity >= 1
RETURNING quantity;
~~~

Dấu **?** là placeholder JDBC. Test concurrency cần bảo đảm:

- Hai request bắt đầu gần nhau trên **hai Connection độc lập**.
- Cả hai thử trừ SKU-1 khi quantity ban đầu = 1.
- Theo giao thức và isolation lựa chọn, chỉ một lần thực sự thành công trừ hàng; kết quả cuối không âm.
- Nếu một request không cập nhật được hàng hoặc gặp conflict, service phải xử lý theo contract thay vì báo thành công giả.

### 14.2. Điều phối bằng latch thay vì sleep

Trong Java concurrency test, dùng **CountDownLatch, CyclicBarrier hoặc CompletableFuture** để tổ chức thời điểm bắt đầu; không dùng Thread.sleep với giả định thread luôn chạy đúng thứ tự sau N mili giây.

Tuy nhiên, barrier ở tầng Java chưa đủ bảo đảm database đã lấy khóa. Với test lock-specific, có thể:

1. Transaction A UPDATE hàng và giữ transaction mở.
2. Xác nhận bước A đã thực thi UPDATE xong, chưa COMMIT.
3. Transaction B thử UPDATE cùng hàng với timeout có kiểm soát.
4. Quan sát chờ khóa qua pg_stat_activity/pg_blocking_pids nếu cần.
5. COMMIT A và kiểm tra B tiếp tục theo isolation được chọn.

Đặt timeout trên test để tránh suite treo vô hạn. Không gây deadlock/mất mạng trên database dùng chung.

## 15. Kiểm thử lỗi kết nối, pool và khả năng phục hồi

Những lỗi hạ tầng có thể bị bỏ sót nếu chỉ test business rules:

- Mượn Connection từ pool bị timeout khi mọi slot đang được sử dụng.
- Driver phát SQLException khi mạng bị reset.
- Connection đã đóng nhưng repository vẫn cố dùng lại.
- Transaction bị hủy bởi statement timeout hoặc deadlock.
- Connection bị giữ sau exception, khiến request tiếp theo không lấy được slot.
- COMMIT được gửi nhưng phản hồi bị mất, dẫn tới **unknown commit outcome**.
- Application retry quá nhiều lần, làm database đang chậm bị quá tải hơn.

### 15.1. Unit test cho chính sách lỗi, integration test cho sự kiện lỗi thật

Dùng mock/stub để ép một dependency ném lỗi là hợp lý khi muốn kiểm tra **chính sách tầng service**, ví dụ:

- Có retry tối đa 3 attempts hay không?
- Có backoff/jitter ngoài transaction hay không?
- Có dừng retry khi deadline hết?
- Có map lỗi cơ sở dữ liệu thành trạng thái HTTP phù hợp?
- Có giữ operation ID ổn định giữa các lần thử?

Nhưng một mock ném SQLException không chứng minh driver/DBMS thực tế trả SQLSTATE nào, pool có reset session state đúng, hoặc một transaction đã commit trước lúc kết nối đứt.

**Dùng cả hai:** unit test để phủ nhiều nhánh chính sách nhanh; integration/fault-injection test để xác nhận điều kiện thực gây ra được và cleanup đúng.

### 15.2. Những lỗi nào nên tạo bằng DB fixture?

| Rủi ro | Cách tạo trong test DB riêng | Kết quả cần chứng minh |
|---|---|---|
| Unique violation | INSERT cùng operation_id hai lần | Không nhân đôi nghiệp vụ |
| Foreign key violation | INSERT child không có parent | DB từ chối, không có orphan |
| Check violation | quantity âm hoặc amount âm | Constraint thực hoạt động |
| Statement timeout | Truy vấn chờ có kiểm soát và timeout ngắn | Timeout được phân loại, Connection được dọn |
| Lock wait | Giữ khóa ở Connection A, thao tác B chờ | Có giới hạn chờ, không treo test |
| Deadlock | Hai transaction lấy khóa theo thứ tự đảo ngược | DB phát hiện, app rollback/retry đúng |
| Serialization failure | Lịch đọc/ghi concurrent có kiểm soát | Retry toàn transaction khi an toàn |
| Pool exhaustion | Giữ đủ Connection trong pool test nhỏ | Borrow timeout và recovery đúng |
| Network disconnect | Proxy cắt network trong test được cô lập | Hệ thống xử lý connection lỗi; không retry COMMIT mù quáng |
| Read replica lag | Dùng kiến trúc replica test phù hợp | Luồng read-your-writes không đọc stale ngoài contract |

Không nên dùng random sleep hoặc tắt cả PostgreSQL khi chỉ muốn test CHECK constraint. Mỗi test nên có **failure mode cụ thể** và mức tác động nhỏ nhất có thể.

### 15.3. Kiểm tra Connection leak

Với pool test giới hạn, một ca có thể:

1. Gọi repository nhiều lần, xen kẽ lỗi và thành công.
2. Theo dõi số Connection active/pending.
3. Bảo đảm Connection được trả sau khi transaction hoàn tất.
4. Gọi một truy vấn mới sau các lần lỗi để xác nhận pool còn hoạt động.
5. Giới hạn thời gian test và đóng pool ở teardown.

**Kiểm tra việc method trả về không có exception không đủ.** Connection leak thường chỉ lộ ra sau nhiều lần gọi hoặc khi số request đồng thời đủ lớn.

### 15.4. Lỗi COMMIT cần một giao thức đối soát

Nếu client gửi COMMIT rồi timeout, trạng thái DB có thể đã commit. Một test chỉ assert rằng Java ném exception không chứng minh nghiệp vụ đã rollback.

Thiết kế mong muốn có **operation_id được lưu trong cùng transaction** và ràng buộc duy nhất. Sau lỗi có kết quả chưa rõ, application đối soát trên nguồn dữ liệu có thẩm quyền rồi trả trạng thái phù hợp. Khi dùng replica bất đồng bộ, một lần không tìm thấy trên replica chưa chắc có nghĩa không có commit ở primary trước đó.

Không giả định một proxy mạng có thể tạo xác suất 100% đúng thời điểm **server đã commit nhưng client chưa nhận phản hồi**. Nếu test không điều khiển chính xác thời điểm, ghi rõ nó chứng minh đường lỗi kết nối nào, không tự nhận đã chứng minh unknown commit outcome hoàn chỉnh.

## 16. Kiểm thử hiệu năng persistence khác benchmark nghiệp vụ

Một integration test chức năng không nên thất bại chỉ vì một truy vấn mất 12 ms thay vì 10 ms trên máy CI khác nhau. Ngược lại, những thay đổi tạo **N+1 queries**, bỏ chỉ mục hoặc giữ transaction hàng giây có thể gây lỗi production dù dữ liệu cuối cùng vẫn đúng.

Cần tách:

- **Functional persistence integration tests:** khẳng định dữ liệu, SQL, constraint, transaction đúng.
- **Performance/regression tests:** đo throughput, p95/p99, số query, lock wait, index plan và pool dưới tải đại diện.
- **Resilience tests:** kiểm tra recovery, idempotency, timeout và hành vi khi DB chậm/mất kết nối.

### 16.1. Bẫy N+1

~~~text
SELECT orders của 100 khách hàng: 1 truy vấn
SELECT items của từng order: 100 truy vấn
=> 101 lần round trip
~~~

Business unit test với fake thường không thấy 101 SELECT. Integration test có thể đếm SQL query bằng instrumentation, hoặc benchmark số round trip khi tăng số orders từ 1 lên 100, từ đó phát hiện N+1.

Không biến số query thành assertion quá cứng nếu thay đổi hợp lệ về batching/fetch plan không ảnh hưởng SLO. Quan trọng là phát hiện **tăng trưởng bất thường và nút thắt thực**.

### 16.2. EXPLAIN và dữ liệu đại diện

Ví dụ PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tenant_id, operation_id
FROM orders
WHERE tenant_id = 7
ORDER BY id DESC
LIMIT 20;
~~~

**EXPLAIN ANALYZE thực thi câu SQL**; với SELECT test thường không thay đổi dữ liệu, nhưng với DML có thể thay đổi dữ liệu và phải dùng transaction kiểm soát. Kế hoạch thực thi phụ thuộc thống kê, kích thước bảng và môi trường. Một bảng test chỉ có 3 hàng không phản ánh hành vi query trên bảng production hàng triệu hàng.

Thử với dữ liệu có phân bố và quy mô phù hợp, kiểm soát quyền và không chạy load test phá dữ liệu trên database chia sẻ.

### 16.3. Quan sát theo từng lớp

| Metric | Phát hiện |
|---|---|
| Query count mỗi request | N+1, query thừa |
| JDBC query duration | SQL chậm, mapping hoặc network |
| Pool connection acquire time | Cạn pool, connection leak |
| Transaction duration | Giữ khóa/snapshot quá lâu |
| Lock wait p95/p99 | Tranh chấp dữ liệu |
| Rows read/returned | Query quá rộng, phân trang không phù hợp |
| WAL/replication lag | Ảnh hưởng batch/transaction ghi lớn |
| API latency p95/p99 | Tác động mà người dùng cảm nhận |

Các tên metric là khái niệm quan sát, không phải tên mặc định của một framework. Mục tiêu là tách **sai logic**, **sai tích hợp** và **chậm vì workload**.

## 17. Dữ liệu test, isolation và cleanup

Một bài integration test xanh ở máy developer nhưng đỏ ngẫu nhiên trên CI thường do **chia sẻ trạng thái** hơn là do SQL sai.

### 17.1. Fixture phải xác định

Nên tạo dữ liệu test bằng mã hoặc migration/seed cố định, tránh phụ thuộc:

- Dữ liệu còn sót từ lần test trước.
- Thời gian hiện tại làm thay đổi điều kiện.
- ID identity luôn bằng 1 khi suite chạy song song.
- Thứ tự SELECT không có ORDER BY.
- Timezone mặc định của máy chạy CI.
- Random data không ghi seed để tái tạo.
- Các dịch vụ ngoài đang có dữ liệu không kiểm soát.

Ví dụ một test phân trang phải chỉ rõ ORDER BY theo cột ổn định và tie-breaker. Không thể khẳng định vị trí hàng nếu query không có thứ tự.

### 17.2. Bốn chiến lược isolation phổ biến

| Chiến lược | Ưu điểm | Điều cần lưu ý |
|---|---|---|
| Database/container riêng cho mỗi test class | Cách ly cao | Tốn thời gian và tài nguyên |
| Schema riêng cho mỗi test | Dễ chạy song song hơn | Migration và search_path phải cấu hình đúng |
| TRUNCATE/DELETE trong BeforeEach | Đơn giản khi suite chạy tuần tự | Cẩn thận foreign key, identity và test chạy song song |
| Rollback transaction test | Cleanup nhanh cho một số integration test | Có thể che commit thật và không bao phủ dữ liệu ghi ở Connection ngoài test |

Không chọn rollback mặc định cho **mọi** bài test. Test cần chứng minh COMMIT/rollback phải kết thúc transaction ứng dụng thật và dùng Connection độc lập để xác minh.

### 17.3. Test chạy song song

Nếu hai test cùng TRUNCATE orders trong một database chung, test A có thể xóa fixture của B giữa lúc B đang query. Kết quả dễ biến thành flaky test.

Cách xử lý: test database/schema riêng, hoặc disable parallel execution cho nhóm test chia sẻ DB. Không tăng retry số lần chạy JUnit để che mất lỗi isolation.

### 17.4. Cleanup khi test lỗi

Dùng lifecycle hook hoặc quản lý resource của framework để dọn Connection, DataSource, container, executor thread và network proxy **ngay cả khi assertion thất bại**.

Nếu cố ý giữ transaction mở để test lock wait, teardown cần rollback/close mọi Connection và hủy Future còn chạy, không để backend bị chặn ảnh hưởng test kế tiếp.

## 18. Kiểm thử repository contract và lựa chọn test doubles

Khi có nhiều adapter (JDBC, JPA, in-memory, remote store), có thể định nghĩa một **repository contract test** chung: mỗi implementation phải thỏa các quy tắc cơ bản như create/read, duplicate handling hoặc isolation theo hợp đồng.

Tuy vậy, contract chung chỉ nên chứa những đảm bảo thật sự **được cả hai implementation cam kết**. Không ép fake HashMap phải mô phỏng chính xác toàn bộ SQLSTATE, MVCC hay khả năng phục hồi sau crash. Những đặc tính đó cần integration tests chuyên biệt cho database adapter.

### 18.1. Ví dụ ma trận

| Hợp đồng | Fake | JdbcOrderRepository + PostgreSQL |
|---|---|---|
| Service chỉ gọi save khi dữ liệu hợp lệ | Có | Không cần lặp y hệt |
| Trả về ID đã được repository cấp | Có thể | Có |
| Lưu/read đúng amount | Có thể | Bắt buộc |
| UNIQUE operation_id | Fake có thể mô phỏng | Bắt buộc DB thật |
| Foreign key parent/child | Không mô phỏng đáng tin | Bắt buộc DB thật |
| Rollback sau lỗi thứ hai | Không chứng minh DB | Bắt buộc DB thật |
| SQL injection/mapping | Không | Bắt buộc DB thật |
| Pool cleanup/network error | Không | Test adapter/pool/resilience riêng |

**Nguyên tắc:** test ở tầng thấp nhất đủ chứng minh rủi ro, và thêm integration tests ở nơi ranh giới hạ tầng có thể sai.

## 19. Từ yêu cầu đến test case: ma trận đề xuất

Giả sử yêu cầu nghiệp vụ là **“đặt đơn hàng đúng giá trị và không tạo đơn thiếu dòng”**. Một ma trận đầy đủ hơn chỉ một bài test happy path:

| Yêu cầu/rủi ro | Test phù hợp | Vì sao |
|---|---|---|
| Không có dòng hàng phải bị từ chối | Unit business | Không cần DB để kiểm tra validation |
| Quantity <= 0 không được chấp nhận | Unit business + DB CHECK integration | Domain và DB là hai lớp bảo vệ |
| Tính tổng tiền chính xác | Unit business + mapping test | Công thức và chuyển kiểu NUMERIC |
| Chỉ một lần gọi repository từ service | Unit interaction | Kiểm tra quyết định của service |
| SQL tạo order và items đúng | Persistence integration | Cần PostgreSQL |
| Child lỗi phải rollback parent | Persistence integration | Cần transaction thật |
| Operation ID trùng không tạo hai nghiệp vụ | Integration + idempotency flow | Cần UNIQUE và xử lý request lặp |
| App cũ không lỗi khi migration expand | Upgrade/compatibility integration | Cần schema và hai code version |
| Hai request cạnh tranh không phá invariant | Concurrency integration | Cần nhiều Connection/isolation |
| Pool không leak sau lỗi | Pool integration/resilience | Cần driver/pool thật |
| Query nhanh ở dữ liệu lớn | Performance regression | Cần workload/plan/metric đại diện |

Một kịch bản business có thể được xác minh **ở nhiều tầng** khi có rủi ro khác nhau. Ví dụ quantity dương cần validation để phản hồi dễ hiểu và CHECK tại DB để không có đường ghi nào bỏ qua bất biến.

## 20. CI/CD: test nào chạy ở giai đoạn nào?

~~~text
Developer / Pull Request
       |
       +-- Unit tests domain/service
       |      nhanh, chạy thường xuyên
       |
       +-- Repository integration tests
       |      PostgreSQL/Testcontainers + migrations
       |
       +-- Static SQL/schema checks
       |      migration order, checksum, lint
       |
       v
Merge / Staging
       |
       +-- Upgrade test từ schema production đại diện
       +-- API + PostgreSQL end-to-end smoke test
       +-- Concurrency/transaction recovery tests
       |
       v
Release qualification
       |
       +-- Performance/lock/pool tests trên dữ liệu giả đại diện
       +-- Fault injection có kiểm soát
       +-- Backup/restore và migration recovery drills khi cần
~~~

Tần suất cụ thể phụ thuộc thời gian CI và mức rủi ro; không phải mọi pull request đều cần tạo cluster HA và inject network partition.

### 20.1. Tối ưu tốc độ mà không giảm bằng chứng

- Business unit tests không khởi động Spring context/DB nếu không cần.
- Reuse container **trong phạm vi suite đã kiểm soát** khi không làm test phụ thuộc nhau.
- Chạy database integration tests thành nhóm có thể theo dõi riêng.
- Giảm dữ liệu fixture xuống mức đủ bộc lộ rủi ro, nhưng performance tests cần dữ liệu đại diện.
- Cache dependency/image phù hợp; pin phiên bản DB/driver khi cần tính lặp lại.
- Dùng test tags như unit, integration, slow, resilience để điều phối pipeline.
- Khi test thất bại, lưu **SQLSTATE, query context an toàn, migration version và container logs**, không làm lộ password/PII.

### 20.2. Tiêu chí hoàn thành thay vì chỉ số lượng test

Số lượng JUnit methods cao không đồng nghĩa test tốt. Nên đánh giá:

1. Test có xác minh **bất biến quan trọng** hay chỉ verify method calls?
2. Ranh giới DB có chạy trên engine và schema production tương đương không?
3. Có kiểm tra **failure path** cùng với happy path không?
4. Có assert trạng thái **sau COMMIT/ROLLBACK** không?
5. Có thể tái tạo lỗi với fixture/seed/migration version không?
6. Test có chạy được độc lập, song song theo thiết kế và không dùng production data không?
7. Kết quả test có tạo ra bằng chứng phù hợp rủi ro cần phòng tránh không?

## 21. Những hiểu nhầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| “Test dùng mock repository đủ chứng minh SQL đúng.” | Mock không chạy JDBC/SQL | Integration test adapter với DB thật |
| “Mọi business test đều là unit test.” | Nghiệp vụ còn có test xuyên nhiều tầng | Tách intent khỏi scope |
| “Integration test không kiểm tra nghiệp vụ.” | Có thể chạy full business workflow | Xác định mục tiêu và phạm vi |
| “H2 xanh nghĩa là PostgreSQL chắc chạy.” | SQL dialect/isolation khác nhau | Test PostgreSQL thật cho rủi ro PG |
| “assertThrows chứng minh rollback.” | Có thể đã commit một phần trước lỗi | Query lại state qua Connection độc lập |
| “@Transactional test tự rollback chứng minh commit.” | Test có thể chưa bao giờ COMMIT thật | Dùng test không bị outer rollback che |
| “Một Connection đủ kiểm tra concurrency.” | Không có hai transaction độc lập | Dùng nhiều Connection và điều phối |
| “Sleep 100 ms làm test race condition ổn định.” | Scheduler/DB timing không xác định | Latch/barrier/timeout quan sát |
| “COUNT(*) = 0 luôn chứng minh rollback.” | Có thể query sai tenant/schema hoặc fixture sai | Dùng operation ID duy nhất, đúng DB và assert đầy đủ |
| “Migrations production không cần chạy trong test.” | Schema test có thể khác production | Chạy migration thật trong integration |
| “Test dùng chung DB vẫn an toàn khi parallel.” | TRUNCATE/fixture có thể đè nhau | Isolation schema/container hoặc chạy tuần tự |
| “Commit SQLException nghĩa là chưa lưu.” | Response có thể mất sau commit | Idempotency và đối soát |
| “Performance test nên assert SQL < 10 ms trên mọi CI.” | Nhiễu tài nguyên, máy chạy khác nhau | Đo regression theo workload/metric phù hợp |
| “Fake phải mô phỏng cả deadlock và MVCC.” | Dễ tạo mô hình sai engine thật | Unit test chính sách, integration test DB |
| “Test xanh thì production không cần quan sát.” | Tải, dữ liệu và hạ tầng có thể khác | Metrics, tracing, backup/restore và vận hành |

## 22. Bài tập tình huống

### Bài 1 — Mock đã đủ chưa?

Một JUnit test mock OrderRepository trả ID 101 và service trả ID 101. Có chứng minh được bảng orders có dữ liệu không?

**Gợi ý:** không. Test chỉ chứng minh lời gọi và giá trị trả theo mock. Cần integration test chạy SQL thật rồi SELECT.

### Bài 2 — Validation và CHECK

Service từ chối quantity = 0. Có cần DB CHECK(quantity > 0) và test constraint không?

**Gợi ý:** có thể cần vì có đường ghi ngoài service. Unit test bảo vệ quyết định nghiệp vụ; integration test chứng minh ràng buộc DB.

### Bài 3 — Lỗi child INSERT

Order INSERT thành công, item thứ nhất thành công, item thứ hai trùng SKU và lỗi. Chỉ assertThrows có đủ chưa?

**Gợi ý:** chưa. Query bằng Connection mới để xác nhận parent/child đều rollback.

### Bài 4 — @Transactional trên test

Một integration test Spring có @Transactional, gọi service.create rồi query thấy row và kết thúc bằng rollback tự động. Nó đã chứng minh COMMIT production đúng chưa?

**Gợi ý:** chưa chắc. Cần test kết thúc transaction thật và đọc qua Connection độc lập.

### Bài 5 — H2 và PostgreSQL

Repository dùng ON CONFLICT và JSONB PostgreSQL nhưng unit suite dùng H2. Vì sao vẫn cần PostgreSQL integration test?

**Gợi ý:** syntax, type và isolation có thể khác; H2 không đảm bảo tương thích PG.

### Bài 6 — Schema evolution

Ứng dụng đã thêm cột NOT NULL. Test chỉ khởi tạo database trống rồi INSERT dữ liệu mới thành công. Rủi ro gì chưa được kiểm tra?

**Gợi ý:** hàng cũ có NULL, migration upgrade có thể thất bại. Cần test từ schema/data phiên bản cũ.

### Bài 7 — Concurrent update

Một test dùng HashMap và hai method gọi tuần tự, khẳng định không có lost update. Vì sao chưa đủ?

**Gợi ý:** không có transaction/snapshot/lock thật. Cần hai Connection đồng thời và assert invariant.

### Bài 8 — Retry serialization

Unit test mock SQLException SQLSTATE 40001 để xác minh service retry 3 lần. Nó chứng minh câu SQL thật có thể retry an toàn chưa?

**Gợi ý:** chưa. Chỉ chứng minh chính sách; cần integration kiểm tra rollback, transaction mới và dữ liệu cuối.

### Bài 9 — Test data bị chia sẻ

Hai integration tests chạy song song, một test TRUNCATE orders trong BeforeEach, test kia đang SELECT orders. Test đỏ không ổn định. Sửa bằng cách nào?

**Gợi ý:** mỗi test có schema/database riêng hoặc chạy tuần tự nhóm dùng chung trạng thái; không che lỗi bằng retry JUnit.

### Bài 10 — Commit timeout

Client gửi COMMIT và mất phản hồi. Test assert rằng service ném PersistenceException. Còn điều gì phải xác minh?

**Gợi ý:** trạng thái nghiệp vụ có thể đã commit. Cần operation_id/idempotency, đối soát DB và không tạo ghi trùng.

## 23. Ghi nhớ và áp dụng

**Kiểm thử nghiệp vụ** hỏi *“ứng dụng có ra quyết định đúng theo quy tắc domain không?”*. **Kiểm thử tích hợp lưu trữ** hỏi *“các quyết định và thao tác đó có được hiện thực đúng khi đi qua JDBC, SQL, transaction, schema và DBMS thực tế không?”*. Đây là hai trục có thể giao nhau, không phải hai nhãn loại trừ nhau.

Hãy dùng **unit tests với fake/mock** để kiểm tra validation, tính toán và chính sách nhanh, rõ lỗi. Dùng **PostgreSQL integration tests** để chứng minh SQL, mapping, ràng buộc, rollback, migration và kiểm soát đồng thời; khi có failure path, hãy kiểm tra **dữ liệu thực sau lỗi**, không chỉ exception. Dùng môi trường cô lập, migrations thật, fixture có thể lặp lại và Connection độc lập khi cần kiểm tra commit.

**Không một loại test đơn lẻ đủ bảo vệ toàn bộ persistence**. Chiến lược tốt là đặt đúng bài test vào đúng rủi ro, bổ sung performance/resilience tests khi cần, và bảo đảm mọi kết luận từ test đều phù hợp với các thành phần thực sự đã chạy.

### 14.3. SQLSTATE có ý nghĩa hơn message

PostgreSQL có thể báo **40001** cho serialization failure và **40P01** cho deadlock. Test nên kiểm tra loại lỗi/state theo hợp đồng, không assert chính xác văn bản exception (có thể thay đổi theo driver, phiên bản và locale).

Retry phải chạy **toàn transaction trên Connection mới** nếu transaction cũ đã bị rollback; không retry riêng một UPDATE cuối rồi dùng dữ liệu đã đọc ở snapshot cũ.
