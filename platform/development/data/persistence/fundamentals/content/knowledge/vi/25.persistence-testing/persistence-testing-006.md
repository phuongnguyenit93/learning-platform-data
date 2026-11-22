# Kiểm thử đồng thời bằng lịch thực thi có kiểm soát

Một lỗi về transaction có thể chỉ xuất hiện khi hai request Java cùng đọc một bản ghi, cùng quyết định cập nhật và đi đến cơ sở dữ liệu theo một thứ tự rất cụ thể. Nếu bài test tạo hai thread rồi cho chạy tự do, có lần lỗi xuất hiện và có lần không; chạy thử hàng nghìn lần cũng không bảo đảm gặp đúng cửa sổ tranh chấp.

**Kiểm thử đồng thời bằng lịch thực thi có kiểm soát** (*controlled interleaving/concurrency testing*) chủ động tạo những điểm hẹn giữa các thao tác để kiểm tra kết quả tại các thứ tự thực thi quan trọng. Thay vì chỉ hỏi “chạy song song có lỗi không?”, bài test phải xác định: **mỗi transaction đọc gì, nó bị chặn ở đâu, transaction nào có thể commit, điều gì phải bị từ chối và bất biến dữ liệu nào vẫn phải đúng**.

Trong chương **Kiểm thử lưu trữ** của **DATA_PERSISTENCE_FUNDAMENTALS**, nội dung này kết nối nguyên lý persistence của Java với transaction, mức cô lập, khóa, kiểm soát đồng thời, JDBC connection pool, lỗi retry và độ bền của cơ sở dữ liệu. Ta sử dụng PostgreSQL làm ví dụ chính, xây lịch thực thi bằng `CountDownLatch`/`CyclicBarrier`, viết test JUnit 5 + JDBC, phân biệt lỗi dữ liệu với xung đột hợp lệ, và chỉ ra giới hạn của các bài test như vậy.

## 1. Tại sao bài test tuần tự không đủ?

Giả sử kho còn **2 sản phẩm**, hai người đặt hàng đồng thời, mỗi người muốn lấy 1 sản phẩm. Code ngây thơ:

```java
int stock = repository.readStock(productId);
if (stock > 0) {
    repository.setStock(productId, stock - 1);
}
```

Nếu hai yêu cầu lần lượt thực hiện toàn bộ method, kết quả là `2 → 1 → 0`. Nhưng nếu cả hai đều đọc `2` rồi mới ghi, cả hai đều ghi `1`: một lần giảm tồn kho bị mất dù cả hai yêu cầu có thể báo thành công.

```text
Ban đầu stock = 2

T1 (đặt hàng A)                 T2 (đặt hàng B)
-------------------------      -------------------------
SELECT stock -> 2              |
                               SELECT stock -> 2
UPDATE stock = 1               |
COMMIT                         |
                               UPDATE stock = 1
                               COMMIT

Kết thúc stock = 1 (sai: đã chấp nhận hai lượt lấy 1).
```

Đây là một dạng **lost update** do ứng dụng tính giá trị mới từ dữ liệu cũ rồi ghi đè vô điều kiện. Một test đơn luồng sẽ không chứng minh được code an toàn trước lịch thực thi này.

**Lưu ý quan trọng:** không phải mọi `UPDATE` đồng thời đều gây lost update. Câu `UPDATE stock = stock - 1 WHERE stock > 0` thực hiện phép giảm và kiểm tra điều kiện ngay trong DB, có hành vi khác với `SELECT` rồi `UPDATE stock = giá_trị_đã_tính`. Hãy kiểm thử **câu SQL thật sự được ứng dụng phát ra**, không kiểm thử một mô hình suy đoán của repository.

## 2. Mô tả lịch thực thi bằng các sự kiện có thể kiểm tra

Một **lịch thực thi** (*schedule*) mô tả thứ tự tương đối giữa các thao tác của các transaction. Với hai transaction T1 và T2:

- `R1(x)`: T1 đọc bản ghi x.
- `W1(x)`: T1 ghi x.
- `C1`: T1 commit; `A1`: T1 abort/rollback.
- `R2(x)`, `W2(x)`, `C2` tương tự cho T2.

Ví dụ lịch làm mất cập nhật:

```text
R1(stock=2) -> R2(stock=2) -> W1(stock=1)
            -> C1 -> W2(stock=1) -> C2
```

Điều cần kiểm soát thường là **quan hệ xảy ra-trước** (*happens-before*), chẳng hạn:

```text
T1 hoàn thành SELECT ───┐
                        ├── cả hai đã đọc xong mới được UPDATE
T2 hoàn thành SELECT ───┘
```

Ta không nhất thiết phải điều khiển thread nào được CPU chạy trước ở từng nanosecond. Với test lost update, chỉ cần ép **hai SELECT hoàn thành trước bất kỳ UPDATE nào**. Sau đó hệ quản trị sẽ tự quyết định ai giữ khóa ghi trước; cả hai vẫn có cùng giá trị đọc cũ.

| Công cụ Java | Ý nghĩa khi xây lịch | Cần chú ý |
| --- | --- | --- |
| `CountDownLatch` | Một thread báo đã đạt mốc, thread khác chờ tín hiệu mở cổng | Bộ đếm chỉ giảm; không tái dùng sau khi về 0 |
| `CyclicBarrier` | N thread phải cùng đến một điểm hẹn rồi mới tiếp tục | Nếu thiếu một thread, cả nhóm có thể bị treo; luôn có timeout |
| `Phaser` | Đồng bộ nhiều pha có thể thay đổi số bên tham gia | Phức tạp hơn, cần ghi rõ bên nào đăng ký/deregister |
| `Future.get(timeout)` | Giới hạn thời gian toàn test/thread | Timeout của Future **khác** timeout SQL/lock; cancel không luôn cắt được JDBC call |
| DB locks, `NOWAIT`, lock timeout | Tạo/quan sát tranh chấp thực tại DB | Chỉ dùng khi test cần semantics khóa của engine |

**Không dùng `Thread.sleep(...)` làm điểm đồng bộ chính.** Sleep chỉ tạo một khoảng thời gian ước lượng, không chứng minh transaction kia đã đọc hàng hoặc đã lấy khóa. CI chậm hoặc máy nhiều CPU có thể làm lịch thay đổi.

## 3. Điều kiện để lịch điều khiển có ý nghĩa

Một test tin cậy cần những điều kiện sau:

1. **Ít nhất hai connection vật lý/transaction độc lập.** Nếu cả hai worker chia sẻ một `Connection`, chúng không đại diện hai giao dịch tách biệt. Pool chỉ có một connection cũng có thể làm worker thứ hai chờ mãi trong khi worker đầu đợi tại barrier.
2. **DB thực hoặc tương đương engine cần kiểm tra.** Mô phỏng bằng map trong RAM, mock repository hoặc thay PostgreSQL bằng một DB nhúng khác không bảo đảm giống isolation/lock/SQLSTATE của PostgreSQL.
3. **Trạng thái đầu cố định.** Mỗi test bắt đầu với số dư/tồn kho/phiên bản xác định; không kế thừa dữ liệu từ test trước.
4. **Điểm đồng bộ nằm đúng giữa thao tác có rủi ro.** Với lost update, barrier phải nằm **sau SELECT và trước UPDATE** của cả hai transaction.
5. **Giới hạn thời gian và thu dọn.** Bất kỳ thread nào lỗi trước barrier cũng phải khiến test thất bại rõ ràng, không treo cả pipeline.
6. **Assertion trên DB sau khi cả hai transaction kết thúc.** Không chỉ assert giá trị trả về từ method; phải đọc lại trạng thái đã commit và kiểm tra bất biến.

Test cần tách biệt khỏi environment production: dùng container/DB test, dữ liệu không nhạy cảm, role quyền hạn đủ dùng và cleanup sau khi chạy. Không cố ý gây deadlock hay khóa bảng trên database dùng chung với ứng dụng thật.

## 4. Ví dụ đầy đủ: JUnit 5, Testcontainers và JDBC

Ta kiểm thử bằng **PostgreSQL thật trong container**. Mẫu dưới giả định project test đã có JUnit Jupiter, Testcontainers PostgreSQL/JUnit Jupiter, PostgreSQL JDBC driver và HikariCP. Đây là tài liệu minh họa để tích hợp vào một project Java 17+; **không chạy container hoặc build** trong bước soạn tài liệu.

Schema test:

```sql
CREATE TABLE stock_test (
    product_id BIGINT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

INSERT INTO stock_test(product_id, stock, version)
VALUES (42, 2, 0);
```

Chỉ có một hàng `product_id=42` để dễ chứng minh kết quả. Trong ứng dụng thật, nhiều mặt hàng và transaction đồng thời có thể tạo thêm deadlock/độ lệch truy cập; test một hàng là **bước chứng minh một rủi ro cụ thể**, không phải chứng nhận toàn hệ thống an toàn.

### 4.1. Dựng fixture với hai transaction độc lập

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class ControlledStockIT {
    @Container
    static final PostgreSQLContainer<?> DB =
            new PostgreSQLContainer<>("postgres:16-alpine");

    private HikariDataSource dataSource;

    @BeforeEach
    void createFixture() throws SQLException {
        HikariConfig cfg = new HikariConfig();
        cfg.setJdbcUrl(DB.getJdbcUrl());
        cfg.setUsername(DB.getUsername());
        cfg.setPassword(DB.getPassword());
        cfg.setMaximumPoolSize(4);   // cần ít nhất 2 connection đồng thời
        cfg.setConnectionTimeout(5_000);
        dataSource = new HikariDataSource(cfg);

        try (Connection c = dataSource.getConnection();
             Statement s = c.createStatement()) {
            s.execute("""
                CREATE TABLE IF NOT EXISTS stock_test (
                    product_id BIGINT PRIMARY KEY,
                    stock INTEGER NOT NULL CHECK (stock >= 0),
                    version BIGINT NOT NULL DEFAULT 0
                )
                """);
            s.execute("TRUNCATE stock_test");
            s.execute("""
                INSERT INTO stock_test(product_id, stock, version)
                VALUES (42, 2, 0)
                """);
        }
    }

    @AfterEach
    void closePool() {
        if (dataSource != null) dataSource.close();
    }

    private int stock() throws SQLException {
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(
                     "SELECT stock FROM stock_test WHERE product_id=42");
             ResultSet rs = ps.executeQuery()) {
            assertTrue(rs.next());
            return rs.getInt(1);
        }
    }

    // Các phương thức test và worker được bổ sung ở các phần tiếp theo.
}
```

Ví dụ các phần kế tiếp là **thành viên của cùng class `ControlledStockIT`**. Để đọc độc lập, từng đoạn code hiển thị riêng nhưng khi thực hành cần chép vào class đó, không đặt method rời bên ngoài class. Các test này không được chạy song song trên **cùng** fixture/bảng; nếu bật parallel execution, cấp database/schema/hàng riêng cho mỗi test.

### 4.2. Tạo lịch lost update ở READ COMMITTED

Worker cố ý mắc lỗi: đọc tồn kho bằng một SELECT, hai worker **cùng đợi tại barrier**, sau đó ghi giá trị được tính từ kết quả đọc cũ:

```java
// Thành viên của ControlledStockIT:
private int unsafeDecrement(CyclicBarrier bothRead) throws Exception {
    try (Connection c = dataSource.getConnection()) {
        c.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
        c.setAutoCommit(false);

        try {
            int observed;
            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT stock FROM stock_test WHERE product_id=42");
                 ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) throw new SQLException("Thiếu stock_test/42");
                observed = rs.getInt(1);
            }

            // Cả T1 và T2 phải đọc giá trị cũ trước khi UPDATE.
            bothRead.await(10, TimeUnit.SECONDS);

            try (PreparedStatement ps = c.prepareStatement("""
                    UPDATE stock_test SET stock = ?
                    WHERE product_id=42
                    """)) {
                ps.setInt(1, observed - 1);
                ps.setQueryTimeout(10);
                if (ps.executeUpdate() != 1) {
                    throw new SQLException("Không cập nhật được stock_test");
                }
            }
            c.commit();
            return observed;
        } catch (Exception failure) {
            try {
                c.rollback();
            } catch (SQLException rollbackError) {
                failure.addSuppressed(rollbackError);
            }
            throw failure;
        }
    }
}

@Test
void exposesLostUpdateWithControlledSchedule() throws Exception {
    CyclicBarrier bothRead = new CyclicBarrier(2);
    ExecutorService workers = Executors.newFixedThreadPool(2);
    try {
        Future<Integer> first = workers.submit(
                () -> unsafeDecrement(bothRead));
        Future<Integer> second = workers.submit(
                () -> unsafeDecrement(bothRead));

        assertEquals(2, first.get(30, TimeUnit.SECONDS));
        assertEquals(2, second.get(30, TimeUnit.SECONDS));

        // Hai lệnh thành công nhưng chỉ giảm được 1 đơn vị:
        // đây là kết quả CHỨNG MINH lỗi của code cố ý unsafe.
        assertEquals(1, stock());
    } finally {
        workers.shutdownNow();
        assertTrue(workers.awaitTermination(15, TimeUnit.SECONDS));
    }
}
```

**Vì sao lịch này tạo lỗi?** PostgreSQL ở `READ COMMITTED` cho phép mỗi transaction đọc giá trị `2` trước khi bên kia cập nhật. Hai câu UPDATE đều ghi **literal 1** được tính ngoài database. PostgreSQL có thể bắt một UPDATE chờ khóa hàng cho đến khi transaction kia commit, nhưng câu SQL thứ hai vẫn ghi cùng giá trị `1` — không có điều kiện version hay phép giảm nguyên tử.

Không nên viết `assertEquals(0, stock())` trong test **chỉ để kỳ vọng code sai tự đúng**. Test ở trên cố ý mô tả và tái hiện defect, nên khẳng định **hành vi lỗi quan sát được**. Khi sửa production code, thay test bằng assertion của invariant mong muốn và kiểm tra nó không bị phá vỡ theo lịch cũ.

### 4.3. Sửa bằng một UPDATE nguyên tử

Với yêu cầu chỉ giảm một đơn vị khi kho còn hàng, không cần đọc giá trị trước rồi gửi lại; có thể dùng **câu lệnh cập nhật có điều kiện tại DB**:

```sql
UPDATE stock_test
SET stock = stock - 1, version = version + 1
WHERE product_id = 42 AND stock > 0;
```

Hai câu UPDATE cạnh tranh trên cùng hàng được DB phối hợp khóa và kiểm tra lại điều kiện phù hợp với isolation. Với kho ban đầu 2, cả hai có thể cập nhật thành công, trạng thái cuối phải là 0. Với kho ban đầu 1, chỉ một cập nhật thành công, request còn lại thấy số hàng ảnh hưởng bằng 0. Không được bỏ qua kết quả `executeUpdate()`.

```java
// Thành viên của ControlledStockIT:
private int atomicDecrement(CyclicBarrier beforeUpdate) throws Exception {
    try (Connection c = dataSource.getConnection()) {
        c.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
        c.setAutoCommit(false);
        try {
            // Ép cả hai worker đến gần thời điểm UPDATE.
            beforeUpdate.await(10, TimeUnit.SECONDS);
            int changed;
            try (PreparedStatement ps = c.prepareStatement("""
                    UPDATE stock_test
                    SET stock = stock - 1, version = version + 1
                    WHERE product_id=42 AND stock > 0
                    """)) {
                ps.setQueryTimeout(10);
                changed = ps.executeUpdate();
            }
            c.commit();
            return changed;
        } catch (Exception failure) {
            try {
                c.rollback();
            } catch (SQLException rollbackError) {
                failure.addSuppressed(rollbackError);
            }
            throw failure;
        }
    }
}

@Test
void atomicUpdatePreservesStockInvariant() throws Exception {
    CyclicBarrier beforeUpdate = new CyclicBarrier(2);
    ExecutorService workers = Executors.newFixedThreadPool(2);
    try {
        Future<Integer> a = workers.submit(
                () -> atomicDecrement(beforeUpdate));
        Future<Integer> b = workers.submit(
                () -> atomicDecrement(beforeUpdate));

        assertEquals(1, a.get(30, TimeUnit.SECONDS));
        assertEquals(1, b.get(30, TimeUnit.SECONDS));
        assertEquals(0, stock());  // Hai lần giảm đều được ghi nhận.
    } finally {
        workers.shutdownNow();
        assertTrue(workers.awaitTermination(15, TimeUnit.SECONDS));
    }
}
```

Ở ví dụ này barrier đặt **trước UPDATE**, không phải sau một SELECT cũ. Vì thao tác giảm và điều kiện tồn kho nằm trong **một câu SQL**, bài test kiểm tra kết quả đã commit chứ không cần ép một lần đọc riêng nào thành stale.

### 4.4. Sửa bằng optimistic locking

Khi nghiệp vụ cần đọc nhiều thuộc tính, xác minh quy tắc rồi cập nhật, **version** giúp nhận biết quyết định đã dựa trên dữ liệu cũ:

```sql
SELECT stock, version FROM stock_test WHERE product_id=42;

UPDATE stock_test
SET stock = ?, version = version + 1
WHERE product_id=42
  AND version = ?
  AND stock > 0;
```

Nếu cả hai transaction đọc `stock=2, version=0` trước khi ghi, chỉ một câu UPDATE được phép đổi version từ `0` sang `1`; câu còn lại cập nhật **0 hàng** dưới PostgreSQL `READ COMMITTED` sau khi điều kiện được đánh giá lại. Đây là **conflict được phát hiện đúng**, không phải lỗi test. Nếu ứng dụng muốn cả hai yêu cầu cuối cùng được phục vụ khi kho vẫn đủ, cần retry request bị conflict bằng **một transaction mới, đọc lại version mới**, có giới hạn số lần và không lặp side effect ngoài DB.

Nếu barrier nằm **bên trong mọi lần retry**, hai transaction mới có thể lại cùng chờ dù chỉ còn một worker retry, khiến test treo. Chỉ dùng barrier để ép cạnh tranh **lần đầu**, còn vòng retry sau đó phải có cơ chế điều phối riêng hoặc chạy theo trạng thái đã được xác minh.

## 5. Kiểm thử bất biến, không chỉ kiểm thử exception

Một test đồng thời nên diễn đạt chính xác **kết quả nào được phép**:

| Bài toán | Kết quả đúng cần assert |
| --- | --- |
| Hai yêu cầu lấy mỗi yêu cầu 1 món, tồn kho bắt đầu 2 | Cả hai thành công và tồn kho cuối bằng 0; hoặc conflict/retry có chính sách rõ |
| Hai yêu cầu lấy mỗi yêu cầu 1 món, tồn kho bắt đầu 1 | Tối đa một yêu cầu được chấp nhận; tồn kho không âm |
| Hai request thanh toán cùng `idempotency_key` | Một lần ghi nhận thanh toán nghiệp vụ, một kết quả nhất quán khi gửi lại |
| Hai giao dịch cùng cập nhật version 5 | Tối đa một ghi thành công tại version 5; yêu cầu còn lại phát hiện conflict hoặc retry |
| Hai transfer rút từ cùng số dư | Tổng ledger/balance thỏa invariant; không có tiền được tạo hoặc mất vì lost update |
| Hai worker cùng claim một outbox event | Một ownership hợp lệ tại một thời điểm theo lease/token; redelivery vẫn có thể xảy ra và consumer phải idempotent |

Đếm số exception thôi là chưa đủ. Ví dụ cả hai request đều trả HTTP 200 nhưng tồn kho chỉ giảm một lần — **không có exception nhưng dữ liệu sai**. Ngược lại, một transaction bị serialization failure do DB chủ động ngăn anomaly là **cơ chế bảo vệ đúng**, không nhất thiết là test thất bại.

Một kết quả test có thể được phân loại:

```text
SUCCESS      -> commit hợp lệ, invariant đúng
CONFLICT     -> bị từ chối có chủ đích (version, trạng thái, lock)
RETRYABLE    -> transaction abort vì deadlock/serialization theo DB
TIMEOUT      -> vượt deadline; kết quả commit có thể chưa rõ tùy điểm lỗi
BUG          -> commit thành công nhưng invariant bị phá
INFRA_ERROR  -> container/connection/pool/test harness thất bại
```

Việc phân loại giúp test tránh hiểu nhầm “cứ ném exception là sai” hoặc “không ném exception thì đúng”.

## 6. Kiểm thử write skew dưới snapshot isolation

**Lost update** không phải anomaly duy nhất. Một ví dụ khác là **write skew**: hai transaction đọc một bất biến trên nhiều hàng, rồi cập nhật **hai hàng khác nhau**, không đụng cùng khóa ghi.

Giả sử luôn phải có **ít nhất một bác sĩ trực**:

```sql
CREATE TABLE on_call (
    doctor_id BIGINT PRIMARY KEY,
    is_on_call BOOLEAN NOT NULL
);

INSERT INTO on_call(doctor_id, is_on_call)
VALUES (1, TRUE), (2, TRUE);
```

Lịch cần kiểm tra:

```text
T1 (bác sĩ 1)                    T2 (bác sĩ 2)
-----------------------         -----------------------
BEGIN REPEATABLE READ           BEGIN REPEATABLE READ
SELECT count(*) WHERE on_call   SELECT count(*) WHERE on_call
 -> 2                            -> 2
          [barrier: cả hai đã kiểm tra]
UPDATE doctor 1 -> FALSE        UPDATE doctor 2 -> FALSE
COMMIT                          COMMIT

Kết quả có thể: 0 bác sĩ trực, vi phạm invariant >= 1.
```

Trong PostgreSQL, `REPEATABLE READ` cung cấp snapshot isolation và có thể **cho phép write skew** trên hai hàng khác nhau vì không có xung đột ghi cùng hàng. Ở `SERIALIZABLE` của PostgreSQL, cơ chế Serializable Snapshot Isolation (SSI) có thể phát hiện chu trình phụ thuộc và abort ít nhất một transaction với `SQLSTATE 40001` trong lịch điển hình này.

Thiết kế test theo hai kỳ vọng khác nhau:

1. **Test phơi bày rủi ro ở REPEATABLE READ:** ép cả hai đọc `COUNT=2` trước khi một bên cập nhật; sau cả hai commit, kiểm tra `COUNT=0` là tình huống lỗi nghiệp vụ có thể tái hiện.
2. **Test biện pháp bảo vệ ở SERIALIZABLE:** ép cùng lịch đọc; **không giả định bác sĩ nào bị abort**. Kiểm tra DB không commit được trạng thái không hợp lệ; một giao dịch có thể nhận `40001`, ứng dụng phải rollback và chỉ retry nếu an toàn.

Nếu muốn dùng isolation thấp hơn mà vẫn bảo vệ invariant, có thể thiết kế một **hàng khóa chung** hoặc một cơ chế cập nhật có điều kiện để các quyết định phải tuần tự hóa trên cùng nguồn chân lý; việc chỉ dùng `SELECT FOR UPDATE` trên **hai hàng khác nhau** không đủ cho invariant xuyên nhiều hàng. Tối ưu đồng thời phải gắn với **đối tượng bảo vệ bất biến**, không chỉ đối tượng đang được sửa.

## 7. Lịch thực thi cho deadlock, NOWAIT và lock timeout

### 7.1. Deadlock: đan chéo thứ tự khóa

Giả sử hai transaction cùng sửa hai tài khoản:

```text
T1                              T2
---------------------------     --------------------------
BEGIN                           BEGIN
UPDATE account A   (lock A)     UPDATE account B   (lock B)
           [barrier: cả hai giữ khóa thứ nhất]
UPDATE account B   (đợi B)      UPDATE account A   (đợi A)
             \                    /
              \---- deadlock -----/
```

PostgreSQL có thể phát hiện vòng chờ và abort một transaction với SQLSTATE `40P01` (*deadlock_detected*), cho transaction còn lại tiếp tục sau khi khóa được giải phóng. Test cần assert:

- Không có transaction nào âm thầm được coi là commit nếu DB đã abort nó.
- Ít nhất một giao dịch phải thất bại như một **victim** của deadlock trong lịch đã dựng đúng; không cố định “T1 chắc chắn thua”.
- Giao dịch sống sót có thể hoàn tất; dữ liệu sau khi cả hai kết thúc phải tuân thủ quy tắc nghiệp vụ.
- Nếu application retry deadlock, phải retry **đơn vị transaction hoàn chỉnh** và chỉ thực hiện external side effect sau commit.

Trong thực tế có thể giảm deadlock bằng **thứ tự khóa nhất quán**, ví dụ luôn cập nhật tài khoản có ID nhỏ trước rồi tài khoản lớn. Đây là hành vi nên có một test đối chứng: chạy cùng các transaction nhưng với thứ tự khóa chuẩn hóa và kiểm tra không xuất hiện deadlock do riêng hai hàng này.

### 7.2. NOWAIT và timeout khác nhau

Để test tình huống không chờ lock, có thể:

1. T1 `BEGIN`, khóa hàng `A` bằng `SELECT ... FOR UPDATE`; dùng latch báo “đã khóa” **sau khi SQL trả về**.
2. T2 chỉ được chạy sau tín hiệu đó, thử `SELECT ... FOR UPDATE NOWAIT` trên A.
3. Ở PostgreSQL, T2 thường nhận SQLSTATE `55P03` (*lock_not_available*) khi không thể lấy khóa ngay.
4. T1 rollback/commit, rồi thử lại T2 để chứng minh tài nguyên đã được thả.

Một timeout do `lock_timeout`, lỗi `statement_timeout`, timeout chờ pool và timeout của `Future.get()` **không phải cùng sự kiện**. Chúng xảy ra ở các tầng khác nhau và có thể đòi hỏi cách xử lý khác nhau. Khi timeout xảy ra ngay lúc `COMMIT`, kết quả commit có thể không rõ; không tự retry một command không có idempotency key.

## 8. So sánh mức cô lập theo hành vi thật

| Lịch kiểm thử | PostgreSQL READ COMMITTED | PostgreSQL REPEATABLE READ | PostgreSQL SERIALIZABLE |
| --- | --- | --- | --- |
| T1 đọc, T2 cập nhật và commit, T1 đọc lại | Có thể thấy giá trị khác | T1 tiếp tục thấy snapshot đã thiết lập | T1 có snapshot phù hợp, kiểm tra ràng buộc serializable |
| Hai T cùng đọc rồi ghi đè literal vào **cùng hàng** | Lost update có thể xảy ra nếu không có guard | Một transaction ghi cạnh tranh có thể bị abort bởi cập nhật hàng từ transaction đồng thời | Một transaction có thể bị abort theo SSI/serialization |
| Hai T đọc invariant rồi ghi **hai hàng khác nhau** | Write skew có thể xảy ra | Write skew có thể xảy ra | SSI có thể abort để ngăn lịch không serializable |
| Hai T lấy khóa A/B trái thứ tự | Deadlock có thể xảy ra | Deadlock có thể xảy ra | Deadlock cũng có thể xảy ra; ngoài ra có serialization failure |

Các dòng mô tả **hành vi điển hình của PostgreSQL**, không phải lời hứa mọi DB có cùng tên isolation sẽ giống hệt. Trong hệ khác, `REPEATABLE READ` có thể được triển khai bằng khóa/giao thức khác, và phép đọc snapshot có thể có khác biệt. Test nên dùng **engine + phiên bản + schema + SQL** gần môi trường triển khai thực tế.

Không nên tạo test “serializable = không còn bất kỳ lỗi nào”. Serializable có thể bảo vệ tính tương đương với một lịch tuần tự **bằng cách abort một transaction**; ứng dụng vẫn phải quyết định retry, backoff, deadline và cách trả thông báo cho người dùng.

## 9. Thiết kế bộ test theo các pha điều khiển

Mẫu tổng quát cho một lịch T1/T2:

```text
SETUP:
  seed fixture; version=0; kiểm tra dữ liệu ban đầu

T1: begin -> thao tác A1 -> signal "T1 reached phase A"
T2: begin -> wait phase A -> thao tác B1 -> signal "T2 reached phase B"
T1: wait phase B -> thao tác A2 -> commit/rollback
T2: thao tác B2 -> commit/rollback

VERIFY:
  đợi cả hai worker kết thúc (bounded timeout)
  ghi nhận outcome/SQLSTATE, đọc DB bằng connection mới
  kiểm tra invariant, cleanup và đóng pool
```

Đừng lạm dụng barrier theo cùng một pattern cho mọi test. Nếu cần **một bên chạy xong rồi mới mở bên kia**, `CountDownLatch` hoặc một điều phối viên chính thích hợp hơn `CyclicBarrier`. Nếu test cần **cả hai đọc trước khi ghi**, barrier hai bên là giải pháp rõ ràng. Nếu test cần **một worker giữ khóa trong khi worker kia thử NOWAIT**, dùng latch tín hiệu sau khi SQL đã lấy khóa.

Một lịch tốt thường kèm ba thông tin:

- **Tiền điều kiện:** giá trị row, version, isolation, số connection, index/constraint.
- **Điểm chờ:** lời gọi SQL nào đã hoàn thành trước khi phát tín hiệu; ai mở cổng cho ai.
- **Hậu điều kiện:** transaction nào được phép commit/abort, invariant nào cần giữ và mã lỗi nào được chấp nhận.

### Không điều khiển được mọi thứ chỉ bằng Java barrier

Barrier điều khiển vị trí của code ứng dụng, **không điều khiển chính xác** thời điểm DB lấy row lock, flush WAL, xếp hàng lock waiter hay phát hiện deadlock. Nếu bài test cần chứng minh transaction T2 **đã bắt đầu chờ khóa**, có thể dùng truy vấn trạng thái phiên như `pg_stat_activity`/`pg_locks` và correlation ID hoặc một hook điều phối có kiểm soát; nhưng những phép quan sát ấy cũng có race và yêu cầu quyền DB. Dùng chúng khi cần chứ không biến mọi test thành một bộ quan sát internal engine mong manh.

## 10. Chống flaky test và ngộ nhận khi test vượt thời gian

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chạy hai thread rồi `sleep(100)` | Không biết hai thread đã thật sự đọc/giữ khóa chưa | Barrier/latch có chứng cứ sau SQL |
| Pool có 1 connection, barrier đợi 2 | Worker đầu giữ connection trong khi đợi worker còn lại không thể borrow | Pool đủ lớn, dùng connection độc lập |
| Barrier không timeout | Worker lỗi sớm làm test treo mãi | Timeout tại barrier, Future và statement |
| Worker thất bại nhưng test không gọi `Future.get()` | Exception bị giấu trong Future | Thu outcome cả hai worker |
| Test chỉ assert mã trả về | DB có thể vẫn vi phạm invariant dù cả hai báo thành công | Query trạng thái đã commit sau khi mọi worker kết thúc |
| Test chỉ chấp nhận một worker thắng cụ thể | Scheduler/DB không bảo đảm bên nào thắng | Assert tập kết quả hợp lệ, không ép tên thread |
| Test fixture dùng chung giữa các test chạy song song | Test tự tranh nhau, reset/truncate chéo | Isolate schema/DB/hàng hoặc tắt parallel cho fixture |
| Mở `@Transactional` quanh toàn test method | Connection/test transaction có thể che commit/visibility của các worker | Quản lý transaction rõ trong worker, verify bằng connection mới |
| Dùng H2 thay cho PostgreSQL để test lock/SQLSTATE | Engine khác dẫn đến test xanh giả | Testcontainers/DB engine thực |
| Mỗi worker tự retry bên trong barrier | Retry đơn lẻ tới barrier không còn đủ bên, treo | Barrier cho attempt có chủ đích; retry ở tầng riêng |
| Hủy Future và giả định JDBC đã dừng ngay | Statement đang block có thể chưa ngừng | Statement timeout/DB lock timeout, rollback, cleanup có kiểm chứng |
| Chỉ chạy test khi CI rất rảnh | Không phát hiện lỗi theo tải, cấu hình pool và deadline thật | Chạy lịch bắt buộc ổn định, thêm stress test bổ sung |

**Test deterministic schedule và stress test phục vụ hai mục tiêu khác nhau.** Lịch có kiểm soát bắt đúng một interleaving đã biết; stress test với nhiều thread/request giúp tìm các lịch **chưa biết**, cạnh tranh tài nguyên, bottleneck và lỗi vận hành. Cả hai hữu ích, nhưng không thay thế nhau. Một suite tốt có test điều khiển ổn định trong CI và các vòng tải/chaos test riêng với observability đầy đủ.

## 11. Kiểm thử retry, commit chưa rõ và external side effect

Nhiều ứng dụng Java sử dụng `@Transactional`/JPA hoặc JDBC để ghi nhiều bảng, rồi gọi email/broker/payment. Trong test đồng thời, cần xác định **ranh giới transaction** chứ không chỉ các dòng Java:

```text
Request A
  TX1: đọc -> ghi -> COMMIT
  Side effect sau commit: publish event/outbox worker

Request B
  TX2: đọc -> xung đột -> ROLLBACK
  Retry có giới hạn bằng TX3: đọc trạng thái mới -> quyết định lại
```

Các kịch bản đáng kiểm tra:

1. **Optimistic conflict:** hai request cùng version; một cập nhật, một nhận conflict; request thua không được phát outbox event thành công giả.
2. **Serialization failure `40001`:** hai transaction bị ép cạnh tranh; lỗi được phân loại và retry từ **đầu transaction** với dữ liệu đọc lại, không chạy lại riêng câu UPDATE.
3. **Deadlock `40P01`:** victim rollback toàn bộ thay đổi, retry có jitter/backoff giới hạn; invariant liên bảng vẫn đúng.
4. **Commit-result-unknown:** mô phỏng mất kết nối sau khi DB có thể đã commit; API dùng **idempotency key** và đối soát trên nguồn đủ nhất quán trước khi tạo tác động mới.
5. **Outbox/consumer:** hai worker tranh claim; event có thể được giao lại nhưng bảng processed-event/ledger chỉ ghi nhận hiệu ứng một lần.

Không nên giả lập commit-result-unknown bằng cách ném exception **trước** khi gọi `commit()` rồi kết luận đã kiểm thử được commit không rõ. Cần một fault injection ở lớp proxy/kết nối hoặc cơ chế test kiểm soát đường trả ACK **sau khi DB có thể đã commit**; đó là bài test khác, cần đo cả trạng thái DB và hệ thống ngoài.

Với Spring, nếu sử dụng proxy `@Transactional`, gọi phương thức annotated từ **cùng instance (self-invocation)** có thể không đi qua transaction interceptor. Test đồng thời nên xác nhận transaction thực sự bắt đầu theo dự định bằng log/trace hoặc kiểm tra hành vi, thay vì chỉ nhìn annotation.

## 12. Quy trình thêm test đồng thời vào CI

1. **Mô tả lỗi bằng một lịch ngắn:** ghi hai cột T1/T2 và giá trị mong đợi.
2. **Gắn lịch với một invariant:** tồn kho không âm, không có hai booking cùng ghế, tổng ledger bảo toàn, status chuyển hợp lệ.
3. **Seed dữ liệu độc lập:** DB/schema dành cho test; dùng migration/schema thật cần thiết cho câu SQL đang kiểm tra.
4. **Xác định engine/isolation:** lưu phiên bản PostgreSQL/driver, transaction manager và pool size như test manifest.
5. **Đặt barrier/latch sau bước đã xác minh:** không phụ thuộc vào sleep; bao bọc timeout.
6. **Thu cả hai outcome và SQLSTATE:** phân biệt conflict/retryable với lỗi dữ liệu.
7. **Verify bằng connection mới:** chờ worker hoàn tất, query DB và các bảng liên quan.
8. **Thu dọn có giới hạn:** rollback/close connection, shutdown executor, reset data; không để test sau chịu ảnh hưởng.
9. **Ghi log an toàn:** chỉ log transaction ID, tên pha, thời điểm, SQLSTATE và correlation ID; không log secret/PII/bind value nhạy cảm.
10. **Duy trì bài test nhỏ, có mục đích:** một test cho một lịch/anomaly, rồi stress/soak test ngoài bộ test bắt buộc nếu cần.

Khi có một bug production, biến dấu vết event/transaction đã quan sát thành **lịch điều khiển có thể tái hiện** trong integration test. Đây thường là giá trị dài hạn lớn nhất: sau khi sửa, bộ test ngăn chính interleaving đó tái xuất hiện khi refactor repository, ORM mapping, isolation hoặc retry policy.

## 13. Bài tập thực hành

### Bài tập 1: đặt barrier ở đâu?

Hai request đọc `stock=2` rồi cập nhật bằng giá trị `stock-1`. Muốn tái hiện lost update, barrier nên đặt trước SELECT hay sau SELECT?

**Gợi ý đáp án:** sau mỗi SELECT và trước mỗi UPDATE để cả hai transaction cùng quan sát giá trị cũ. Barrier trước SELECT không đủ để bảo đảm chúng đọc trước khi có cập nhật.

### Bài tập 2: sửa SQL mà không dùng optimistic version

Viết một câu SQL giúp hai request cùng lấy một đơn vị từ kho ban đầu 2 mà không mất cập nhật.

**Đáp án:**

```sql
UPDATE stock_test
SET stock = stock - 1
WHERE product_id = 42 AND stock >= 1;
```

Kiểm tra affected rows và đọc trạng thái đã commit; với hai request hợp lệ và ban đầu 2, cuối cùng phải bằng 0.

### Bài tập 3: version conflict có phải lỗi DB?

Hai giao dịch đọc version 8; một câu `UPDATE ... WHERE version=8` sửa được 1 hàng, câu kia sửa 0 hàng. Có nên cho test thất bại ngay vì một request không cập nhật?

**Đáp án:** chưa. Đây có thể là kết quả **phát hiện tranh chấp đúng**. Assertion phải theo chính sách nghiệp vụ: trả conflict rõ ràng, hoặc retry toàn transaction với dữ liệu mới và giới hạn đã đặt.

### Bài tập 4: write skew

Hai bác sĩ cùng thấy 2 người đang trực rồi mỗi người tự tắt trạng thái trực trên hai hàng khác nhau. Dưới PostgreSQL `REPEATABLE READ`, điều gì có thể xảy ra?

**Đáp án:** cả hai có thể commit vì cập nhật hai hàng khác nhau, kết quả không còn ai trực. Kiểm thử thêm với `SERIALIZABLE` và kiểm tra một transaction có thể nhận SQLSTATE `40001` thay vì chấp nhận trạng thái sai; hoặc bảo vệ invariant bằng khóa/quy tắc cập nhật phù hợp.

### Bài tập 5: deadlock và kết quả hợp lệ

T1 khóa A trước B, T2 khóa B trước A. Vì sao không nên assert “T1 luôn nhận 40P01”?

**Đáp án:** engine/scheduler quyết định victim theo trạng thái lúc phát hiện deadlock, không phải tên thread. Nên kiểm tra tập outcome hợp lệ, rollback của victim và invariant sau commit. Phương án giảm deadlock là các giao dịch lấy khóa theo thứ tự thống nhất.

### Bài tập 6: test treo ở CI

Hai worker có `CyclicBarrier(2)` nhưng pool DB chỉ cho phép một connection. Worker đầu đã borrow connection, đọc xong rồi đợi barrier. Worker thứ hai không mượn được connection. Vấn đề ở đâu?

**Đáp án:** lịch test tự tạo deadlock ở **connection pool** chứ chưa đến DB. Phải có ít nhất hai connection độc lập và deadline rõ, hoặc sửa fixture để không giữ tài nguyên trong lúc chờ một worker không thể bắt đầu.

### Checklist thiết kế kiểm thử đồng thời

- Test đã ghi **lịch T1/T2**, điểm chờ và invariant rõ ràng chưa?
- Hai transaction có connection riêng, pool đủ lớn và DB engine/isolation đúng mục tiêu chưa?
- Barrier/latch có đặt sau bước SQL thực sự đã hoàn thành, thay vì dựa trên `sleep()` chưa?
- Có timeout cho barrier, Future, JDBC/DB lock và cleanup khi worker lỗi không?
- Assertion có dựa trên **trạng thái đã commit** và outcome hợp lệ của cả hai giao dịch không?
- Test có phân loại `40001`, `40P01`, `55P03`, conflict và timeout theo đúng tầng không?
- Retry có dùng transaction mới và giữ idempotency, tránh phát side effect giả/chồng lặp không?
- Fixture/test có tách biệt, không chia sẻ bảng khi chạy parallel, không bị transaction wrapper của framework che khuất không?
- Suite đã có cả lịch có kiểm soát lẫn stress test bổ sung khi cần, với log pha/SQLSTATE đủ điều tra không?

**Kết luận:** Kiểm thử đồng thời đáng tin không phải là “thử chạy hai thread thật nhanh”, mà là **xây một lịch thực thi làm lộ rủi ro, buộc các transaction gặp nhau đúng điểm và kiểm tra invariant cuối cùng trên dữ liệu đã commit**. Barrier và latch giúp điều khiển thứ tự ở tầng Java; transaction, isolation và khóa của DB quyết định kết quả thật. Kết hợp lịch có kiểm soát, assertion đúng nghiệp vụ, timeout và test trên engine thực giúp biến những lỗi race khó tái hiện thành bài kiểm thử có thể kiểm chứng và duy trì trong CI.
