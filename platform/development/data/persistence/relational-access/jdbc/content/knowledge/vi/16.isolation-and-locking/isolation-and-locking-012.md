# Kiểm chứng tính cô lập bằng nhiều kết nối độc lập

Trong JDBC, **tính cô lập (isolation)** quyết định một transaction quan sát được thay đổi nào từ các transaction đồng thời. Gọi `Connection.setTransactionIsolation(...)` chỉ yêu cầu driver/DBMS áp dụng một mức cô lập; để biết hệ thống thực sự hành xử thế nào, ta phải tạo **ít nhất hai kết nối độc lập**, điều phối rõ thứ tự đọc, ghi, `commit`, `rollback` và kiểm tra trạng thái cuối cùng.

Bài học thuộc chương **Cô lập và khóa** của module **JDBC**. Các ví dụ dùng API chuẩn `DataSource`, `Connection`, `PreparedStatement` và `ResultSet` để kiểm chứng hiện tượng dirty read, non-repeatable read, phantom read, xung đột ghi và các trường hợp transaction bị chặn hoặc hủy do serialization.

Sau khi học, bạn có thể:

- Thiết lập hai JDBC session độc lập, tránh dùng chung một `Connection` hoặc một transaction của framework.
- Tạo lịch thao tác có thể lặp lại để kiểm chứng visibility giữa các transaction.
- Phân biệt mức cô lập **được cấu hình** với hành vi quan sát được trên từng DBMS.
- Sử dụng thread, latch/barrier và timeout khi thử nghiệm có thể bị khóa.
- Viết kiểm thử tích hợp có fixture riêng, ranh giới transaction chính xác và dọn dẹp đáng tin cậy.
- Diễn giải kết quả bị chặn, deadlock hoặc serialization failure như một phần hành vi isolation.

## 1. Tại sao một connection là chưa đủ?

Một `Connection` thường biểu diễn một ngữ cảnh transaction tại một thời điểm. Khi `autoCommit=false`, các câu SQL trên cùng connection tham gia cùng transaction cho tới khi `commit()` hoặc `rollback()`.

~~~java
connection.setAutoCommit(false);
updateAmount(connection, 9001L, new BigDecimal("200.00"));
BigDecimal value = readAmount(connection, 9001L);
connection.rollback();
~~~

Nếu `value` phản ánh bản cập nhật chưa commit, đó là **transaction tự đọc thay đổi của chính nó**. Đây không phải dirty read vì không có transaction khác tham gia.

Muốn kiểm chứng isolation cần tối thiểu hai connection đang mở đồng thời:

~~~mermaid
sequenceDiagram
    participant A as Connection A / Transaction A
    participant DB as Database
    participant B as Connection B / Transaction B
    A->>DB: SELECT amount (lần 1)
    B->>DB: UPDATE amount
    B->>DB: COMMIT
    A->>DB: SELECT amount (lần 2)
    A->>DB: ROLLBACK
    Note over A,B: So sánh kết quả hai lần đọc của A
~~~

Trong Java:

~~~java
try (Connection reader = dataSource.getConnection();
     Connection writer = dataSource.getConnection()) {
    // Hai connection đang được mượn đồng thời.
    // Transaction A và B phải có phiên DB độc lập.
}
~~~

Một `DataSource` dùng connection pool phải có ít nhất hai kết nối hoạt động. `reader != writer` chỉ chứng minh hai đối tượng Java khác nhau, **không đủ để xác minh hai session vật lý** với mọi proxy/transaction manager. Nếu cần kiểm chứng sâu, tra mã session bằng câu SQL **riêng của DBMS đang thử** và kiểm tra rằng cả hai connection còn mở. Trong môi trường có transaction manager, tránh để hai lần `getConnection()` bị gắn lại vào cùng transaction theo cơ chế quản lý của framework.

**Một luồng Java cũng có thể điều phối hai connection** nếu câu SQL không chặn nhau. Đối với thao tác có khả năng chờ khóa, cần ít nhất hai luồng hoặc một cơ chế điều phối tương đương.

## 2. Bốn mức isolation và các hiện tượng

JDBC định nghĩa những mức thông dụng bằng hằng số trên `java.sql.Connection`:

| Mức JDBC | Dirty read | Non-repeatable read | Phantom read | Ý nghĩa điển hình |
| --- | --- | --- | --- | --- |
| `TRANSACTION_READ_UNCOMMITTED` | Có thể | Có thể | Có thể | Có thể thấy dữ liệu chưa commit, nếu DBMS cho phép |
| `TRANSACTION_READ_COMMITTED` | Ngăn chặn | Có thể | Có thể | Mỗi lần đọc có thể thấy bản commit mới |
| `TRANSACTION_REPEATABLE_READ` | Ngăn chặn | Ngăn chặn | Có thể theo chuẩn truyền thống | Giữ giá trị các dòng đã đọc ổn định |
| `TRANSACTION_SERIALIZABLE` | Ngăn chặn | Ngăn chặn | Ngăn chặn | Kết quả các giao dịch commit tương đương thứ tự tuần tự |

Đây là **mô hình khái niệm và các cam kết tối thiểu**, không phải dự đoán cứng cho mọi DBMS. PostgreSQL, MySQL InnoDB, SQL Server, Oracle và SQLite có chiến lược khóa/MVCC khác nhau. Một số mức được ánh xạ sang cơ chế mạnh hơn hoặc có thêm chế độ snapshot.

Các thuật ngữ:

- **Dirty read:** B đọc thay đổi **chưa commit** của A. A rollback khiến B đã thấy một giá trị chưa từng được commit.
- **Non-repeatable read:** A đọc cùng dòng hai lần trong một transaction; giữa hai lần, B commit cập nhật dòng đó; kết quả đọc của A thay đổi.
- **Phantom read:** A chạy lại cùng câu truy vấn theo điều kiện lọc; B commit thêm/xóa hoặc đổi dòng đủ để làm **tập kết quả** của A thay đổi.
- **Serialization anomaly:** Các transaction đồng thời tạo ra trạng thái không tương đương bất kỳ lịch chạy tuần tự hợp lệ nào. Ví dụ phổ biến là **write skew**.

**“Có thể xảy ra” không đồng nghĩa “chắc chắn xảy ra”.** Không thấy dirty read tại `READ_UNCOMMITTED` chưa chắc test sai; có DBMS không cung cấp dirty read dù chấp nhận hằng số đó. Ngược lại, một số DBMS ngăn phantom cả ở `REPEATABLE_READ` nhờ snapshot.

## 3. Chuẩn bị môi trường thử nghiệm

Dùng một **cơ sở dữ liệu thử nghiệm**, tốt nhất cùng DBMS/driver/version với hệ thống thực. Tạo bảng trước khi bắt đầu thí nghiệm, vì một số DBMS tự commit khi chạy DDL:

~~~sql
CREATE TABLE isolation_probe (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(12, 2) NOT NULL
);
~~~

Khởi tạo dữ liệu đã commit:

~~~sql
INSERT INTO isolation_probe (id, amount)
VALUES (9001, 100.00);
~~~

Sau phép thử, đóng/rollback các transaction còn mở rồi dọn fixture:

~~~sql
DELETE FROM isolation_probe WHERE id = 9001;
~~~

Mỗi phép thử nên dùng ID riêng hoặc một database/schema riêng, đồng thời reset fixture **trước** khi chạy lại. Không chạy các thí nghiệm cố tình giữ khóa trên dữ liệu production.

Điều kiện cần kiểm tra:

1. Hai connection cùng trỏ đến **một database/schema**, nhưng ở **hai session độc lập**.
2. Fixture đã **commit** trước khi transaction A thực hiện lần đọc đầu tiên.
3. Chọn isolation level **trước khi thực hiện SQL trong transaction**. Một số driver/DBMS không cho đổi isolation trong transaction đang mở.
4. Đặt `autoCommit(false)` trước các thao tác kiểm chứng. Nếu A tự commit sau lần đọc đầu tiên, hai lần đọc không còn ở cùng transaction.
5. Không sử dụng cache ORM/application hoặc replica có độ trễ khi muốn kiểm chứng trực tiếp database.
6. Mỗi thí nghiệm có cleanup và timeout; test không được giữ khóa vô hạn.

### Kiểm tra khả năng hỗ trợ của driver

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import javax.sql.DataSource;

try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData md = connection.getMetaData();

    if (!md.supportsTransactions()) {
        throw new IllegalStateException("Không hỗ trợ transaction");
    }

    int requested = Connection.TRANSACTION_READ_COMMITTED;

    if (!md.supportsTransactionIsolationLevel(requested)) {
        throw new IllegalStateException(
                "Không công bố hỗ trợ READ_COMMITTED");
    }

    connection.setTransactionIsolation(requested);
    int reported = connection.getTransactionIsolation();
    System.out.println("JDBC reported isolation = " + reported);
}
~~~

`getTransactionIsolation()` phản ánh cấu hình mà driver báo cáo. **Nó không tự chứng minh** khả năng thấy dữ liệu hay chiến lược khóa trong DBMS. Ta vẫn cần thí nghiệm thực tế bên dưới.

## 4. Thí nghiệm 1: Non-repeatable read

Giả sử fixture có `id=9001, amount=100.00`.

Lịch kiểm thử:

~~~text
Transaction A (reader)             Transaction B (writer)
----------------------------       ------------------------------
BEGIN, READ_COMMITTED
SELECT amount -> 100.00
                                   BEGIN, READ_COMMITTED
                                   UPDATE amount = 150.00
                                   COMMIT
SELECT amount -> ? (chưa kết thúc A)
ROLLBACK
~~~

Nếu A đọc `100.00` ở lần đầu và `150.00` ở lần sau, đã **quan sát** một non-repeatable read. Việc B commit trước lần đọc thứ hai là điều kiện thiết yếu; nếu B chưa commit thì kịch bản đang thử lại là dirty read.

### 4.1. Repository thử nghiệm bằng JDBC

Đây là ví dụ Java 8+ có thể dùng với `DataSource` được cấu hình sẵn và bảng `isolation_probe` đã tạo.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class IsolationProbe {
    private final DataSource dataSource;

    public IsolationProbe(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public static final class Observation {
        public final BigDecimal first;
        public final BigDecimal second;

        public Observation(BigDecimal first, BigDecimal second) {
            this.first = first;
            this.second = second;
        }

        public boolean changed() {
            return first.compareTo(second) != 0;
        }
    }

    public Observation observeReadCommitted(
            long id, BigDecimal nextValue) throws SQLException {

        Objects.requireNonNull(nextValue);

        // Giữ cả A và B mở đồng thời từ đầu đến cuối phép thử.
        try (Connection a = dataSource.getConnection();
             Connection b = dataSource.getConnection()) {

            int level = Connection.TRANSACTION_READ_COMMITTED;
            if (!a.getMetaData()
                  .supportsTransactionIsolationLevel(level)) {
                throw new IllegalStateException(
                        "Driver không công bố READ_COMMITTED");
            }

            // Đặt isolation trước khi bắt đầu transaction.
            a.setTransactionIsolation(level);
            b.setTransactionIsolation(level);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            try {
                // A đọc giá trị gốc.
                BigDecimal first = readAmount(a, id);

                // B ghi rồi commit trên connection riêng.
                int affected = updateAmount(b, id, nextValue);
                if (affected != 1) {
                    throw new SQLException(
                            "Fixture không có đúng một dòng");
                }
                b.commit();

                // A vẫn trong transaction cũ, đọc lần hai.
                BigDecimal second = readAmount(a, id);
                a.rollback(); // Kết thúc transaction đọc.

                return new Observation(first, second);

            } catch (SQLException | RuntimeException failure) {
                try {
                    a.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                try {
                    b.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }

    private static BigDecimal readAmount(
            Connection c, long id) throws SQLException {

        String sql = "SELECT amount FROM isolation_probe WHERE id = ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Thiếu fixture");
                }
                BigDecimal value = rs.getBigDecimal("amount");
                if (value == null) {
                    throw new SQLException("amount NULL bất thường");
                }
                return value;
            }
        }
    }

    private static int updateAmount(
            Connection c, long id, BigDecimal value)
            throws SQLException {

        String sql = "UPDATE isolation_probe SET amount = ? "
                   + "WHERE id = ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setBigDecimal(1, value);
            ps.setLong(2, id);
            return ps.executeUpdate();
        }
    }
}
~~~

Ví dụ sử dụng sau khi fixture `(9001, 100.00)` đã commit:

~~~java
IsolationProbe probe = new IsolationProbe(dataSource);
IsolationProbe.Observation observed =
        probe.observeReadCommitted(
                9001L, new BigDecimal("150.00"));

System.out.println(observed.first);  // Ví dụ: 100.00
System.out.println(observed.second); // Ví dụ: 150.00
System.out.println(observed.changed()); // Ví dụ: true
~~~

**Nhận xét về ví dụ:**

- `a` và `b` là **hai connection mở đồng thời**. Không cần hai Java thread cho kịch bản này nếu các câu SQL không chặn.
- `a` đọc hai lần khi `autoCommit=false` và không có `commit`/`rollback` xen giữa. Đóng `ResultSet` **không** đồng nghĩa với commit transaction.
- `b.commit()` làm thay đổi của B trở nên khả kiến theo chính sách isolation; `a.rollback()` kết thúc A mà không thay đổi dữ liệu B đã commit.
- Phương thức **để lại bản cập nhật đã commit** trong fixture. Kiểm thử phải reset dữ liệu về `100.00` hoặc xóa fixture sau khi đóng kết nối.
- `BigDecimal.compareTo` so sánh giá trị số; `equals` có thể cho kết quả khác nếu scale khác nhau.
- Phương thức xử lý rollback khi có lỗi theo **best effort**. Nếu `b.commit()` đã thành công rồi A gặp lỗi, `b.rollback()` không thể hoàn tác bản cập nhật đã commit. Nếu commit gặp lỗi mạng, trạng thái commit có thể bất định và cần kiểm tra riêng.

Một số isolation/DBMS dùng khóa đọc giữ tới cuối transaction. Khi đó B có thể bị chặn bởi A, khiến kịch bản **một luồng** không thể tiến tới `a.rollback()`. Với `REPEATABLE_READ`, `SERIALIZABLE` hoặc locking reads, dùng hai thread và timeout như phần 8.

### 4.2. Diễn giải quan sát đúng cách

| Kết quả A | Diễn giải |
| --- | --- |
| `100.00 → 150.00` | Đã quan sát non-repeatable read |
| `100.00 → 100.00` | Không thấy non-repeatable read trong phép thử này; có thể do snapshot/khóa/mức isolation mạnh |
| B bị chặn trước commit | Cần đo wait/lock, thay thiết kế điều phối |
| A/B bị hủy với lỗi serialization | DBMS có thể đã bảo vệ isolation bằng cách abort một transaction |
| A báo lỗi kết nối/statement | Lỗi thực thi JDBC, không đủ bằng chứng về visibility |

`READ_COMMITTED` thường cho phép đọc lại thấy dữ liệu mới commit, nhưng **không bắt buộc** mọi phép chạy đều trả khác nhau. Khi báo cáo, ghi lại mức isolation, driver, DBMS, dạng SQL và thời điểm commit.

## 5. Thí nghiệm 2: Dirty read

Giá trị đã commit ban đầu là `100.00`. A cập nhật thành `999.00` nhưng không commit. B đọc ngay trong khoảng đó. A rollback.

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant B as Transaction B
    A->>A: UPDATE amount = 999.00 (chưa COMMIT)
    B->>B: SELECT amount
    Note over B: Nếu thấy 999.00, B đã đọc dữ liệu bẩn
    A->>A: ROLLBACK
    Note over A,B: Giá trị commit thực vẫn là 100.00
~~~

Thiết lập B bằng `TRANSACTION_READ_UNCOMMITTED` nếu driver/DBMS hỗ trợ; A có thể dùng mức phù hợp. Đọc bằng câu SQL có tham số, không sử dụng chính connection A cho B.

**Nếu B đọc `999.00` trước khi A commit, rồi A rollback, đó là bằng chứng dirty read.** Nếu B đọc `100.00` hoặc phải chờ, không thể kết luận mức cô lập được cấu hình sai. Chẳng hạn PostgreSQL áp dụng ngữ nghĩa `READ_COMMITTED` khi yêu cầu `READ_UNCOMMITTED`.

Vì B có thể bị chặn bởi A, nên chạy B ở thread riêng với timeout. Nếu dùng một thread và gọi `SELECT` của B khi A đang giữ khóa ghi, không có luồng nào tiến tới `rollback()` của A, khiến phép thử có thể treo.

## 6. Thí nghiệm 3: Phantom read

Phantom xảy ra khi **tập dòng thỏa điều kiện** thay đổi giữa hai lần đọc trong cùng transaction.

Thêm fixture đã commit:

~~~sql
INSERT INTO isolation_probe (id, amount)
VALUES (9101, 100.00), (9102, 200.00);
~~~

Kịch bản:

~~~text
Transaction A                         Transaction B
---------------------------------     -----------------------------
BEGIN
SELECT COUNT(*) WHERE amount >= 150
=> 1
                                      BEGIN
                                      INSERT (9103, 300.00)
                                      COMMIT
SELECT COUNT(*) WHERE amount >= 150
=> 2 (nếu phantom xuất hiện)
ROLLBACK
~~~

Mẫu JDBC để đếm:

~~~java
static long countMatching(
        Connection connection, BigDecimal threshold)
        throws SQLException {

    String sql = "SELECT COUNT(*) AS total "
               + "FROM isolation_probe WHERE amount >= ?";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setBigDecimal(1, threshold);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Thiếu kết quả COUNT");
            }
            return rs.getLong("total");
        }
    }
}
~~~

Hai lần đếm phải chạy trên **connection A và trong cùng transaction A**, với cùng tham số `150.00`. B phải **commit** trước lần đếm thứ hai. Đừng chạy test khác đồng thời dùng chung `isolation_probe` và cùng phạm vi lọc, vì dữ liệu ngoài test có thể tạo phantom giả.

Một số khác biệt quan trọng:

- PostgreSQL `REPEATABLE_READ` dựa trên snapshot nhất quán, vì vậy hai truy vấn `SELECT` thường có thể tiếp tục thấy cùng tập kết quả.
- MySQL InnoDB `REPEATABLE_READ` thường giữ snapshot cho `SELECT` thường; `SELECT ... FOR UPDATE` là locking read với ngữ nghĩa có thể khác.
- SQL Server `REPEATABLE_READ` có thể giữ khóa dòng đã đọc nhưng không khóa toàn bộ khoảng giá trị; khi đó phantom có thể xuất hiện.
- `SERIALIZABLE` có thể chặn việc chèn của B hoặc hủy một transaction. Kiểm thử phải ghi nhận kết quả commit **và lỗi**, không chỉ giá trị COUNT.

Với các mức có khóa phạm vi, dùng **hai luồng độc lập và timeout** để tránh A đợi B commit trong khi B lại đang đợi khóa A.

## 7. Kiểm chứng xung đột ghi: lost update và write skew

Ba kiểu read anomaly ở trên chưa đủ để chứng minh hệ thống bảo vệ mọi ràng buộc nghiệp vụ.

### Lost update

Hai transaction cùng đọc `stock=10` rồi cùng tính `stock-1` trong Java:

~~~text
A SELECT stock -> 10
B SELECT stock -> 10
A UPDATE stock = 9
A COMMIT
B UPDATE stock = 9
B COMMIT
Kết quả cuối = 9, dù hai lần giảm tồn kho đã diễn ra.
~~~

Đây là ví dụ lost update **nếu DBMS cho phép cả hai commit**. Trên một số DBMS/isolation, B có thể bị chặn hoặc hủy với lỗi xung đột. Phép thử phải ghi nhận **cả kết quả ghi lẫn trạng thái commit** của hai transaction.

Có thể giảm rủi ro bằng câu SQL cập nhật nguyên tử:

~~~sql
UPDATE products
SET stock = stock - 1
WHERE product_id = ? AND stock > 0;
~~~

Hoặc dùng optimistic locking:

~~~sql
UPDATE products
SET stock = ?, version = version + 1
WHERE product_id = ? AND version = ?;
~~~

Sau câu `UPDATE`, kiểm tra `executeUpdate() == 1`. Kết quả `0` nghĩa là điều kiện không còn thỏa hoặc dòng đã biến mất; tầng nghiệp vụ quyết định retry bằng cách **đọc lại và tính lại**, không ghi đè giá trị cũ vô điều kiện.

### Write skew

Giả sử bảng `doctor_on_call` có quy tắc **ít nhất một bác sĩ đang trực**. Ban đầu A và B đều trực.

~~~text
T1 đọc: hai bác sĩ đang trực
T2 đọc: hai bác sĩ đang trực

T1 cập nhật bác sĩ A -> off duty
T2 cập nhật bác sĩ B -> off duty

Nếu T1 và T2 đều commit:
không còn bác sĩ trực (vi phạm bất biến).
~~~

Hai transaction cập nhật **hai dòng khác nhau** nên một số cơ chế snapshot isolation có thể cho cả hai commit. Muốn kiểm chứng, sử dụng barrier để buộc cả T1 và T2 **đều đọc trạng thái cũ trước khi bên nào ghi**, sau đó thu thập kết quả commit. Ở `SERIALIZABLE` đúng nghĩa, DBMS có thể hủy một trong hai transaction thay vì chấp nhận trạng thái vi phạm.

Kiểm soát xung đột bằng isolation mạnh, khóa một thực thể chung, ràng buộc thích hợp hoặc giao thức nghiệp vụ phải dựa trên khả năng của DBMS. Chỉ tăng isolation mà không kiểm thử lịch thao tác thực tế là chưa đủ.

## 8. Điều phối đồng thời và ngăn kiểm thử bị treo

Nếu một statement có thể phải chờ khóa, điều phối tuần tự trên một thread sẽ dễ tạo tình huống chờ vô hạn. Dùng hai worker thread, `CountDownLatch` hoặc `CyclicBarrier` để sắp thứ tự thao tác.

Ví dụ khung điều phối theo hai latch (phần helper SQL cần được hiện thực trong test):

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

public final class InterleavingTest {
    public static void run(DataSource dataSource) throws Exception {
        CountDownLatch firstRead = new CountDownLatch(1);
        CountDownLatch writerDone = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> readerJob = executor.submit(() -> {
                try (Connection c = dataSource.getConnection()) {
                    c.setTransactionIsolation(
                            Connection.TRANSACTION_READ_COMMITTED);
                    c.setAutoCommit(false);

                    try {
                        readFixture(c, 9001L);
                        firstRead.countDown();

                        if (!writerDone.await(10, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                    "Writer chưa hoàn thành");
                        }
                        readFixture(c, 9001L);
                    } finally {
                        c.rollback();
                    }
                }
                return null;
            });

            Future<?> writerJob = executor.submit(() -> {
                if (!firstRead.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Reader chưa đọc lần đầu");
                }

                try (Connection c = dataSource.getConnection()) {
                    c.setTransactionIsolation(
                            Connection.TRANSACTION_READ_COMMITTED);
                    c.setAutoCommit(false);

                    try {
                        updateFixture(c, 9001L);
                        c.commit();
                        writerDone.countDown();
                    } catch (SQLException | RuntimeException failure) {
                        try {
                            c.rollback();
                        } catch (SQLException rollbackFailure) {
                            failure.addSuppressed(rollbackFailure);
                        }
                        throw failure;
                    }
                }
                return null;
            });

            readerJob.get(15, TimeUnit.SECONDS);
            writerJob.get(15, TimeUnit.SECONDS);
        } finally {
            executor.shutdownNow();
        }
    }

    // readFixture / updateFixture: helper JDBC sử dụng
    // PreparedStatement và Connection được truyền vào.
}
~~~

Đây là **khung minh họa**, chưa phải chương trình tự chạy: người học cần bổ sung `readFixture`, `updateFixture` và ghi lại kết quả hai lần đọc. Trong test hoàn chỉnh, cần thông báo lỗi/kết thúc qua latch ở nhánh `finally` để thread còn lại không chờ vô ích khi một worker lỗi.

**Quan trọng:** `Future.get(timeout)` chỉ giới hạn thời gian thread điều phối **chờ kết quả**. Nó không bảo đảm một truy vấn SQL đang chờ khóa sẽ dừng ngay khi Java thread bị interrupt. Kết hợp:

- `PreparedStatement.setQueryTimeout(seconds)` khi driver có hỗ trợ.
- Timeout khóa/statement ở DBMS và giới hạn thời gian kiểm thử.
- Cơ chế hủy câu SQL/đóng connection khi quá hạn, cùng cleanup dữ liệu.
- Thu thập kết quả của **cả hai Future**, gồm ngoại lệ do worker ném.

`Thread.sleep(...)` không thay thế latch/barrier: trên CI hoặc máy tải cao, thức dậy sau một khoảng thời gian không chứng minh được transaction kia đã tới bước mong muốn.

| Mục tiêu | Primitive/chiến lược |
| --- | --- |
| B chỉ chạy sau lần đọc 1 của A | `CountDownLatch` |
| A chỉ đọc lần 2 sau khi B commit | Latch báo commit của B thành công |
| Cả A và B đều đọc trước khi ghi | `CyclicBarrier` hoặc hai latch |
| Đo chờ khóa | Worker riêng + timeout của DBMS |
| Đo serialization failure | Thu kết quả commit/rollback của cả hai worker |

## 9. Hành vi phụ thuộc DBMS

Khi so sánh các mức cô lập, báo cáo **hệ quản trị, phiên bản, cấu hình và dạng câu SELECT**. Không được suy kết quả từ tên mức isolation đơn thuần.

| DBMS | Lưu ý khi thiết kế test |
| --- | --- |
| **PostgreSQL** | `READ_UNCOMMITTED` ứng xử như `READ_COMMITTED`. `REPEATABLE_READ` dùng snapshot nên `SELECT` thường không thấy phantom. `SERIALIZABLE` có thể báo SQLState `40001`. |
| **MySQL InnoDB** | `REPEATABLE_READ` thường dùng snapshot cho consistent read; locking read có hành vi khác. Gap/next-key locks có thể gây chặn hoặc ngăn phantom. |
| **SQL Server** | `READ_COMMITTED` có thể dùng khóa hoặc row versioning tùy `READ_COMMITTED_SNAPSHOT`. `SNAPSHOT` và `REPEATABLE_READ` không phải một cơ chế. `SERIALIZABLE` có thể lấy range locks. |
| **Oracle Database** | `READ_COMMITTED` thường đọc theo snapshot từng statement. `SERIALIZABLE` có thể phát hiện xung đột và từ chối một transaction; không giả định tất cả mức JDBC đều có hỗ trợ giống nhau. |
| **SQLite** | Journal/WAL, shared-cache và chế độ transaction chi phối khả năng đọc/ghi đồng thời. Hai connection `:memory:` thông thường có thể trỏ đến hai cơ sở dữ liệu khác nhau, làm hỏng giả định test. |

Cũng cần phân biệt `SELECT` thông thường với `SELECT ... FOR UPDATE`. Câu đọc có khóa có thể đợi, lấy phiên bản dữ liệu mới hơn hoặc giữ khóa đến cuối transaction tùy DBMS. Không trộn các dạng đọc này rồi kết luận mức isolation thay đổi.

## 10. Đọc lỗi như một phần của kết quả isolation

Đối với concurrency test, một transaction không thể commit cũng là thông tin có ý nghĩa:

| Hiện tượng | Cần kiểm tra |
| --- | --- |
| Query bị chặn | Ai giữ khóa? Statement timeout/lock timeout đang đặt là bao nhiêu? |
| Deadlock | DBMS đã hủy transaction nào? SQLState và cơ chế retry ra sao? |
| Serialization failure | Transaction nào bị từ chối? Có cần chạy lại **toàn transaction** không? |
| Writer commit thành công | Reader nhìn thấy gì trước/sau commit? |
| Lỗi kết nối | Kết quả commit có bất định không? Đã có idempotency chưa? |
| Rollback thất bại | Connection có còn dùng được không? Pool có loại bỏ session lỗi không? |

`SQLException.getSQLState()` hữu ích cho việc phân loại. SQLState `40001` thường liên quan serialization failure; `40P01` là mã deadlock của PostgreSQL. Không giả định tất cả driver/DBMS dùng cùng mã. Khi retry, nên **mở transaction mới, đọc lại snapshot và chạy lại toàn bộ nghiệp vụ**.

~~~java
for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        // Helper mở connection, chạy transaction, commit/rollback,
        // rồi đóng connection trước khi trả về hoặc ném lỗi.
        executeCompleteBusinessTransaction(dataSource);
        break;
    } catch (SQLException ex) {
        if (!"40001".equals(ex.getSQLState()) || attempt == 3) {
            throw ex;
        }
        // Có thể thêm backoff giới hạn ở tầng điều phối.
    }
}
~~~

`executeCompleteBusinessTransaction` trong ví dụ là helper giả định. Nếu transaction có hành động ngoài DB như gửi email hoặc thanh toán, retry phải áp dụng idempotency và cơ chế phối hợp phù hợp. Không retry một câu `UPDATE` riêng lẻ nếu logic của nó phụ thuộc các kết quả đọc từ transaction đã thất bại.

## 11. Kiểm thử tích hợp và cách đánh giá

Báo cáo một phép thử isolation nên ghi đầy đủ:

| Mục | Ví dụ |
| --- | --- |
| DBMS, phiên bản và driver | PostgreSQL X, JDBC driver Y |
| Mức yêu cầu và mức báo cáo | `TRANSACTION_READ_COMMITTED` |
| Cấu hình snapshot/locking | Chế độ row-versioning hoặc MVCC/lock hiện hành |
| Fixture gốc | `(9001, 100.00)` đã commit |
| Lịch thao tác | `A.SELECT1 → B.UPDATE → B.COMMIT → A.SELECT2` |
| Kết quả A | `100.00 → 150.00` |
| Kết quả B | Commit, timeout, deadlock hay serialization failure |
| Kết quả sau test | Dữ liệu đã reset, hai transaction đã kết thúc |

Một bộ kiểm thử tốt nên có các trường hợp sau:

1. **Non-repeatable read:** đọc hai lần trong A, B commit giữa hai lần; ghi nhận cả giá trị và lock wait.
2. **Dirty read:** B thử đọc dữ liệu chưa commit của A, sau đó A rollback; diễn giải theo DBMS.
3. **Phantom:** lặp lại cùng predicate trong A; B chèn/xóa dòng và commit; ghi nhận tập kết quả.
4. **Lost update:** cả hai đọc cùng giá trị cũ trước khi cập nhật; thu kết quả commit và giá trị cuối.
5. **Write skew:** hai transaction đọc cùng bất biến nhiều dòng trước khi cập nhật hai dòng khác nhau.
6. **Serializable conflict:** tạo lịch xung đột và xem DBMS chặn/abort để bảo vệ tính tuần tự.
7. **Timeout/deadlock:** test hoàn tất có giới hạn, cleanup không bỏ lại transaction.
8. **Connection pooling:** hai connection cùng được mượn, isolation/auto-commit được reset theo cấu hình khi trả về pool.
9. **Khả năng lặp lại:** mỗi test có fixture riêng, không dựa vào lịch chạy của test khác.
10. **Trạng thái cuối:** kiểm tra bảng sau khi cả A và B hoàn tất, không chỉ kiểm tra SELECT trung gian.

### Những sai lầm thường gặp

- **Dùng một connection:** hai biến trỏ đến cùng session; test chỉ kiểm tra read-your-writes.
- **Bật auto-commit ở A:** hai lần đọc thuộc hai transaction khác nhau nên không thể khẳng định non-repeatable read.
- **Cho B UPDATE nhưng quên COMMIT:** đang thử dirty read, không phải thay đổi đã commit.
- **Không tạo fixture mới:** test cũ đã đổi dữ liệu từ `100.00` thành `150.00`.
- **Dùng `sleep` để điều phối:** thứ tự chạy không ổn định, kết quả chập chờn.
- **Đợi writer commit trong một thread khi reader giữ khóa:** test có thể treo.
- **Cho rằng timeout ở Future dừng SQL:** driver có thể vẫn đang đợi khóa.
- **Coi serialization failure là thất bại vô nghĩa:** đó có thể là cơ chế bảo đảm isolation.
- **Kết luận mọi DBMS từ một kết quả:** cách dùng MVCC, khóa phạm vi và default isolation khác nhau.

## 12. Câu hỏi và bài tập tự luyện

**Bài 1 — Xác định lỗi trong phép thử.** Cho mã:

~~~java
connection.setAutoCommit(false);
BigDecimal oldValue = readAmount(connection, 9001L);
updateAmount(connection, 9001L, new BigDecimal("200.00"));
BigDecimal newValue = readAmount(connection, 9001L);
connection.rollback();
~~~

Tại sao `oldValue` khác `newValue` không chứng minh non-repeatable read?

**Bài 2 — Thiết kế lịch thao tác.** Với hai connection A và B, hãy mô tả đầy đủ các bước để quan sát dirty read. B phải đọc **trước hay sau** A commit? A phải làm gì sau đó để chứng minh giá trị B thấy là dữ liệu bẩn?

**Bài 3 — Tìm phantom.** A chạy `SELECT COUNT(*) FROM isolation_probe WHERE amount >= 150` hai lần. B thêm một dòng thỏa điều kiện. Phải đặt `B.COMMIT` ở đâu và hai lần SELECT của A phải thuộc bao nhiêu transaction?

**Bài 4 — Giải thích kết quả.** Test ở `REPEATABLE_READ` không thấy phantom nhưng test ở `READ_COMMITTED` thấy phantom. Có đủ bằng chứng để khẳng định mọi DBMS `REPEATABLE_READ` đều ngăn phantom không?

**Bài 5 — Tránh deadlock trong test.** B bị chặn bởi khóa của A, nhưng chương trình lại chờ `B.commit()` trước khi kết thúc A. Tại sao chương trình có thể không tiến triển? Nên dùng gì để điều phối?

**Bài 6 — Bảo vệ bất biến.** Hai bác sĩ đang trực, hai transaction cùng đọc thấy đủ người và lần lượt tắt trạng thái từng bác sĩ. Làm sao thiết kế lịch test để hai transaction chắc chắn **đều đọc dữ liệu gốc** trước khi cập nhật? Vì sao chỉ kiểm tra số dòng UPDATE thành công là chưa đủ?

**Gợi ý đáp án:** (1) Vì cùng một transaction tự đọc thay đổi của chính nó; (2) B đọc khi A chưa commit, A rollback sau đó; (3) B commit giữa hai SELECT nằm trong một transaction A; (4) Không, phải nêu DBMS, isolation và dạng SELECT; (5) Dùng hai thread, latch/barrier và timeout ở DBMS; (6) Dùng barrier sau pha đọc, rồi kiểm tra cả kết quả commit và bất biến cuối cùng.

**Nguyên tắc ghi nhớ:** Kiểm chứng isolation trong JDBC là dựng một **lịch thực thi có kiểm soát giữa nhiều transaction trên nhiều connection độc lập**, giữ ranh giới commit/rollback rõ ràng, đo cả dữ liệu quan sát lẫn khóa và lỗi, rồi đối chiếu với ngữ nghĩa của DBMS. Một lời gọi `setTransactionIsolation` hay một truy vấn đọc lại trên cùng connection **không thay thế** được thí nghiệm này.
