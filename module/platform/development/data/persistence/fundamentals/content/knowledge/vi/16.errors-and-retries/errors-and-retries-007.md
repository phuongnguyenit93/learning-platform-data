# Chọn phạm vi thử lại cho một câu lệnh hoặc toàn giao dịch

Khi một thao tác với cơ sở dữ liệu thất bại, ứng dụng Java thường có ba lựa chọn: chạy lại **một câu SQL**, hủy và chạy lại **toàn bộ giao dịch**, hoặc **dừng để xác minh kết quả** trước khi làm gì tiếp. Chọn sai phạm vi thử lại (*retry scope*) có thể khiến dữ liệu bị trừ hai lần, kiểm tra nghiệp vụ dựa trên giá trị cũ, phát sự kiện trùng hoặc làm tình trạng quá tải trầm trọng hơn.

Ví dụ, hai người cùng đặt chiếc ghế cuối cùng. Mỗi yêu cầu đọc số ghế còn trống, kiểm tra điều kiện, giảm tồn kho và tạo bản ghi đặt chỗ trong một giao dịch. Nếu một giao dịch bị hủy do xung đột cô lập, chỉ chạy lại câu `INSERT` hoặc `UPDATE` cuối cùng là sai: quyết định “còn ghế” phải được tính lại từ đầu. Ngược lại, khi một truy vấn chỉ đọc độc lập gặp lỗi tạm thời trước khi trả kết quả, việc chạy lại đúng truy vấn đó trên kết nối mới đôi khi đã đủ.

Trong chương **Lỗi và thử lại** thuộc **DATA_PERSISTENCE_FUNDAMENTALS**, mục tiêu là nhận diện trạng thái giao dịch sau lỗi, thiết kế phạm vi retry phù hợp với ranh giới persistence Java và phân biệt **lỗi chắc chắn đã hủy thao tác** với **kết quả commit chưa biết**.

## 1. Ba quyết định khác nhau sau một lỗi

| Quyết định | Khi nào cân nhắc | Điều kiện phải đúng |
| --- | --- | --- |
| **Retry một câu lệnh** | Một câu đọc độc lập gặp lỗi tạm thời; hoặc một câu SQL trong giao dịch được DB cho phép thử lại sau khi phục hồi trạng thái thích hợp. | Lần thử trước chắc chắn không tạo tác động nghiệp vụ không thể lặp, hoặc thao tác có cơ chế idempotency; transaction vẫn hợp lệ nếu dùng lại. |
| **Retry toàn giao dịch** | Deadlock victim, serialization failure, một transaction đã bị rollback hoặc mọi bước đọc–quyết định–ghi phải dùng dữ liệu nhất quán mới. | Hủy/xác nhận đã hủy giao dịch cũ; mở transaction mới; chạy lại cả kiểm tra, tính toán và ghi. |
| **Dừng và đối soát** | Mất kết nối/timeout đúng lúc `COMMIT`; không biết lệnh ghi hoặc thao tác ngoài đã thành công chưa. | Tra cứu kết quả theo mã yêu cầu duy nhất, idempotency key hoặc cơ chế đối soát trước khi phát sinh tác động lần nữa. |

Ba quyết định này không trùng với ba loại exception Java. Chẳng hạn, một `SQLException` báo timeout có thể xuất hiện **trước khi SQL được thực thi**, **đang chờ khóa**, **khi server đang ghi**, hoặc **sau khi DB đã commit nhưng phản hồi thất lạc**. Không thể quyết định retry chỉ bằng thông điệp “timeout”.

Sơ đồ ra quyết định ở mức khái niệm:

```text
Thao tác DB báo lỗi
        |
        v
Có chắc thao tác/giao dịch trước đã thất bại
và không còn tác động chưa rõ kết quả?
        |
    +---+---+
   Không    Có
    |       |
    v       v
Đối soát  DB còn giữ transaction hợp lệ?
trước khi      |
thử lại     +--+-----------------+
           Không               Có
             |                  |
             v                  v
      Retry toàn transaction   Có thể retry
      nếu lỗi được phân loại   statement nếu
      và nghiệp vụ cho phép    an toàn, hữu ích
```

Trong thực tế, quyết định “DB còn giữ transaction hợp lệ?” và “có chắc thất bại?” phụ thuộc **hệ quản trị, phiên bản, SQLSTATE/mã lỗi, cấu hình và vị trí xảy ra lỗi**. Nếu không chứng minh được điều kiện an toàn, không tự động retry thao tác ghi.

## 2. Phân biệt phạm vi câu lệnh, giao dịch và yêu cầu nghiệp vụ

Một **câu SQL** là đơn vị mà ứng dụng gửi qua `PreparedStatement.executeQuery()` hoặc `executeUpdate()`. Một **giao dịch** có thể gồm nhiều câu SQL và các quyết định dựa trên dữ liệu vừa đọc. Một **yêu cầu nghiệp vụ** còn có thể gồm cả HTTP, email hoặc broker nằm ngoài transaction của DB.

Ví dụ quy trình đặt chỗ:

```text
Yêu cầu đặt chỗ R-123
  |
  +-- BEGIN transaction
  |     SELECT seats_left
  |     Quyết định còn đủ ghế?
  |     UPDATE seats_left = seats_left - 1
  |     INSERT booking(request_id = R-123)
  |     COMMIT
  |
  +-- Gửi email xác nhận sau commit / qua outbox
```

Nếu `COMMIT` báo serialization failure, toàn bộ transaction cũ đã thất bại theo quy tắc của DB, nên chạy lại từ `SELECT` và tính lại quyết định. Nếu `UPDATE` đã commit nhưng client mất phản hồi, chạy lại toàn bộ yêu cầu có thể giữ thêm một ghế nếu không có khóa idempotency. Nếu email đã gửi rồi một phần DB thất bại, retry không thể “thu hồi” email.

Vì vậy, trước khi viết vòng lặp retry, cần xác định ba ranh giới:

1. **Ranh giới atomicity của DB:** các câu nào bắt buộc cùng commit hoặc cùng rollback?
2. **Ranh giới quyết định nghiệp vụ:** phép đọc, kiểm tra và tính toán nào phải chạy lại khi dữ liệu thay đổi?
3. **Ranh giới side effect ngoài DB:** các hành động nào không thể hoàn tác bằng `ROLLBACK` và cần idempotency/outbox?

Chỉ khi trả lời được ba câu hỏi này mới xác định đúng phạm vi thử lại.

## 3. Retry một câu lệnh: phù hợp trong những trường hợp nào?

### 3.1. Câu đọc độc lập, không có side effect

Một câu `SELECT` chỉ đọc, chạy ngoài transaction nghiệp vụ dài, thường là ứng viên dễ xét nhất. Giả sử màn hình chỉ cần lấy trạng thái hiện tại của đơn:

```sql
SELECT status, updated_at
FROM orders
WHERE order_id = ?;
```

Nếu kết nối mất trước khi trả kết quả, service có thể mở kết nối khác và chạy lại khi chính sách nhận diện đây là lỗi tạm thời. Lần đọc mới **có thể thấy trạng thái khác**, bởi giao dịch khác có thể đã commit ở giữa; điều đó chấp nhận được nếu yêu cầu là “đọc trạng thái hiện tại”.

Tuy nhiên, **không phải mọi câu bắt đầu bằng `SELECT` đều vô hại**: nó có thể gọi hàm có side effect, lấy khóa `FOR UPDATE` hoặc nằm giữa một chuỗi quyết định transaction. Nếu kết quả đọc là đầu vào của một transaction đang mở, chỉ retry riêng `SELECT` có thể làm trộn các snapshot hoặc gây sai logic.

### 3.2. Ghi có điều kiện hoặc khóa idempotency

Không nên coi câu ghi này là idempotent:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42;
```

Nếu server đã commit lần đầu nhưng client không nhận được phản hồi, gửi lại sẽ trừ thêm 100. Điều kiện `balance >= 100` có thể ngăn âm số dư, **nhưng không ngăn trừ tiền hai lần**.

Ngược lại, một lệnh đặt trạng thái cố định:

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = ? AND status = 'PENDING';
```

có thể đưa bản ghi về cùng một trạng thái khi lặp, nhưng ứng dụng vẫn phải hiểu số hàng cập nhật `0` và cân nhắc trigger, audit, sự kiện, kiểm tra quyền và những hành động đi kèm. “Idempotent về trạng thái một hàng” không tự động là “yêu cầu nghiệp vụ idempotent”.

Với nghiệp vụ có tác động một lần, mã yêu cầu duy nhất như `request_id` và ràng buộc `UNIQUE` thường giúp đối soát chắc chắn hơn. Mã đó phải liên kết với **nội dung yêu cầu**: hai yêu cầu mang cùng key nhưng khác số tiền không được mặc nhiên coi là một.

### 3.3. Câu lệnh bên trong transaction

Khi một câu SQL thất bại, không thể mặc định connection vẫn ở trạng thái cho phép chạy câu tiếp theo. Trong **PostgreSQL**, phần lớn lỗi SQL làm transaction hiện hành bị đánh dấu lỗi; các lệnh thông thường sau đó sẽ không chạy cho tới khi `ROLLBACK` toàn bộ hoặc `ROLLBACK TO SAVEPOINT` hợp lệ.

```sql
BEGIN;
SAVEPOINT before_optional_write;

-- Giả sử câu sau vi phạm khóa ngoại và báo SQLSTATE 23503:
INSERT INTO order_tags(order_id, tag_id) VALUES (1001, 999999);

-- Ứng dụng phải xử lý lỗi trước khi tiếp tục SQL:
ROLLBACK TO SAVEPOINT before_optional_write;
RELEASE SAVEPOINT before_optional_write;

-- Chỉ tiếp tục phần nghiệp vụ vẫn hợp lệ rồi COMMIT.
COMMIT;
```

Ở đây, savepoint cho phép **hủy riêng nhóm thao tác tùy chọn** và tiếp tục transaction cha. Nhưng lỗi khóa ngoại vì mã `tag_id` không tồn tại **không phải** lý do hợp lý để lập tức thử lại cùng câu `INSERT` với cùng tham số. Phải xử lý nguyên nhân, chọn phương án nghiệp vụ (bỏ nhãn, báo lỗi hoặc nạp lại dữ liệu), và chỉ retry câu SQL nếu thực sự có khả năng thành công sau khi phục hồi.

Đối với một số DB khác, hành vi của lock timeout, deadlock và transaction sau lỗi khác PostgreSQL. Chẳng hạn, **MySQL/InnoDB** mặc định thường rollback **toàn transaction** khi là deadlock victim, còn lock wait timeout thông thường rollback **câu lệnh** (cấu hình `innodb_rollback_on_timeout` có thể thay đổi phạm vi). Không viết một nhánh xử lý chung cho mọi lỗi “lock” mà chưa xác minh DB đích.

## 4. Retry toàn giao dịch: khi các quyết định phải được tính lại

Một giao dịch thường thực hiện chuỗi **đọc → kiểm tra → ghi**. Nếu hệ quản trị hủy transaction do deadlock hoặc serialization failure, các phép đọc cũ không còn là cơ sở hợp lệ để ghi. Hãy bắt đầu transaction mới với snapshot/khóa mới, chạy lại mọi bước.

Ví dụ hai bác sĩ cùng kiểm tra quy tắc “luôn có ít nhất một người trực” rồi mỗi bên cập nhật **hàng của chính mình**. Dưới một mức cô lập không ngăn write skew, cả hai có thể commit và cùng rời ca. Ở PostgreSQL `SERIALIZABLE`, bộ máy có thể phát hiện lịch thực thi không khả tuần tự và hủy một giao dịch với SQLSTATE `40001`. Khi retry, bên bị hủy phải đếm lại số bác sĩ còn trực; chỉ lặp câu `UPDATE` cuối sẽ phá ý nghĩa của cơ chế cô lập.

Các tình huống thường dẫn đến retry toàn transaction:

| Tín hiệu | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Serialization failure | PostgreSQL SQLSTATE `40001` | Rollback nếu còn cần/khả thi, mở transaction mới, chạy lại toàn bộ logic, giới hạn số lần. |
| Deadlock victim | PostgreSQL `40P01`; SQL Server error `1205`; MySQL error `1213` | Transaction bị chọn làm nạn nhân; phục hồi theo DB/driver rồi retry cả đơn vị nghiệp vụ trong DB. |
| Optimistic lock conflict | `UPDATE ... WHERE version = ?` trả về `0` hàng | Tải lại trạng thái, kiểm tra lại nghiệp vụ; có thể báo “dữ liệu đã thay đổi” thay vì tự retry. |
| Giao dịch chứa nhiều bước phụ thuộc | Kiểm tra số dư rồi ghi hai tài khoản | Nếu phải chạy lại, cần làm lại cả điều kiện kiểm tra và toàn bộ nhóm ghi. |

Một **optimistic conflict** không nhất thiết là lỗi hạ tầng: nếu người dùng đang sửa dữ liệu mà người khác đã cập nhật, việc báo xung đột và yêu cầu quyết định lại có thể đúng hơn tự thử mãi. Với tác vụ tự động, có thể thử lại hữu hạn khi nghiệp vụ cho phép tính lại trên bản mới.

**Không đưa HTTP, gửi email, gọi cổng thanh toán hoặc các side effect không thể hoàn tác vào vòng retry transaction**. Mọi lần thử có thể chạy lại chúng, kể cả khi DB cuối cùng chỉ commit một lần. Hãy tách chúng qua outbox/idempotency/state machine theo yêu cầu.

## 5. Ví dụ Java/JDBC: retry đúng toàn bộ transaction

Xét dịch vụ đặt chỗ của một sự kiện. Bảng `event_inventory` giữ số chỗ còn lại; `bookings` lưu mã đặt chỗ duy nhất. Ví dụ hướng tới **PostgreSQL**, Java 17+, JDBC driver tương thích. Trong thực tế, cần định nghĩa thêm khóa ngoại, trạng thái thanh toán và chính sách giữ chỗ phù hợp.

```sql
CREATE TABLE event_inventory (
    event_id   BIGINT PRIMARY KEY,
    seats_left INTEGER NOT NULL CHECK (seats_left >= 0)
);

CREATE TABLE bookings (
    booking_id UUID PRIMARY KEY,
    event_id   BIGINT NOT NULL REFERENCES event_inventory(event_id)
);
```

Logic một lần thử gồm đọc tồn, kiểm tra hết chỗ, giảm số chỗ bằng lệnh có điều kiện, ghi booking, rồi commit. Vòng thử lại nằm **bên ngoài ranh giới kết nối và giao dịch**. Chỉ các lỗi PostgreSQL báo transaction abort vì serialization/deadlock mới được tự động retry trong ví dụ:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

public final class BookingService {
    private static final int MAX_ATTEMPTS = 3;
    private final DataSource dataSource;

    public BookingService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean reserve(long eventId, UUID bookingId)
            throws SQLException, InterruptedException {
        if (bookingId == null) {
            throw new IllegalArgumentException("bookingId không được null");
        }

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            boolean shouldRetry = false;

            try (Connection connection = dataSource.getConnection()) {
                // Đặt isolation trước khi bắt đầu transaction.
                connection.setTransactionIsolation(
                        Connection.TRANSACTION_SERIALIZABLE);
                connection.setAutoCommit(false);

                try {
                    int seatsLeft = readSeatsLeft(connection, eventId);
                    if (seatsLeft < 1) {
                        connection.rollback();
                        return false;
                    }

                    int updated = decrementIfAvailable(connection, eventId);
                    if (updated != 1) {
                        // Có thể đã hết chỗ; không xác nhận booking.
                        connection.rollback();
                        return false;
                    }

                    insertBooking(connection, bookingId, eventId);
                    connection.commit();
                    return true;
                } catch (SQLException failure) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        failure.addSuppressed(rollbackError);
                        // Không tiếp tục khi chưa xác định được
                        // trạng thái kết nối/giao dịch cũ.
                        throw failure;
                    }

                    if (isTransactionAbort(failure)
                            && attempt < MAX_ATTEMPTS) {
                        shouldRetry = true;
                    } else {
                        throw failure;
                    }
                } catch (RuntimeException failure) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        failure.addSuppressed(rollbackError);
                    }
                    throw failure;
                }
            } // Trả connection về pool trước khi chờ lần thử mới.

            if (shouldRetry) {
                // Backoff ngắn + jitter, bên ngoài transaction.
                long delayMillis =
                        ThreadLocalRandom.current().nextLong(30L, 121L)
                        * attempt;
                try {
                    Thread.sleep(delayMillis);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }
            }
        }
        throw new IllegalStateException("Không thể tới nhánh này");
    }

    private static boolean isTransactionAbort(SQLException error) {
        String state = error.getSQLState();
        return "40001".equals(state) || "40P01".equals(state);
    }

    private static int readSeatsLeft(Connection connection, long eventId)
            throws SQLException {
        String sql =
                "SELECT seats_left FROM event_inventory WHERE event_id = ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, eventId);
            try (ResultSet rows = ps.executeQuery()) {
                if (!rows.next()) {
                    throw new IllegalArgumentException("Không có sự kiện");
                }
                return rows.getInt(1);
            }
        }
    }

    private static int decrementIfAvailable(Connection connection, long eventId)
            throws SQLException {
        String sql = """
                UPDATE event_inventory
                SET seats_left = seats_left - 1
                WHERE event_id = ? AND seats_left > 0
                """;
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, eventId);
            return ps.executeUpdate();
        }
    }

    private static void insertBooking(Connection connection, UUID bookingId,
                                      long eventId) throws SQLException {
        String sql =
                "INSERT INTO bookings(booking_id, event_id) VALUES (?, ?)";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setObject(1, bookingId);
            ps.setLong(2, eventId);
            ps.executeUpdate();
        }
    }
}
```

Trong đoạn mã này:

1. **Đọc lại toàn bộ dữ liệu khi retry:** mỗi lần thử gọi `readSeatsLeft()` và quyết định lại. Không giữ kết quả lần trước trong biến để sử dụng ở transaction mới.
2. **Atomicity:** lệnh giảm tồn và lệnh insert booking cùng một transaction; nếu insert thất bại, rollback hoàn tác cả việc giảm tồn.
3. **Retry giới hạn:** chỉ `40001` và `40P01` được lặp ở ví dụ PostgreSQL. Sau số lần tối đa, lỗi được trả cho tầng gọi; không có vòng lặp vô hạn.
4. **Giải phóng tài nguyên:** `try-with-resources` đóng connection sau mỗi lần thử; chỉ `Thread.sleep` **sau khi** đã thoát phạm vi mượn connection. Tránh giữ khóa DB khi backoff. Do code thay `autoCommit` và isolation của connection, cần bảo đảm pool/driver khôi phục đúng cấu hình trước khi kết nối được người khác mượn lại.
5. **Kết quả thất bại rõ ràng:** thiếu chỗ hoặc không có dữ liệu hợp lệ là tình huống nghiệp vụ; không retry như lỗi hạ tầng.
6. **Mốc commit không rõ:** code không retry timeout/mất kết nối với SQLSTATE khác `40001`/`40P01`, vì một lỗi sau khi gửi `COMMIT` có thể không cho biết booking đã được tạo hay chưa.

**Giới hạn của ví dụ:** `booking_id` là khóa duy nhất để ứng dụng **đối soát khi kết quả không rõ**. Đây chưa phải toàn bộ API idempotent: nếu client gửi lại một booking đã thành công, tùy thời điểm có thể gặp unique conflict `23505` hoặc nhìn thấy hết chỗ. Tầng API cần tra cứu `booking_id`, kiểm tra nó thuộc đúng `event_id` và trả về kết quả của cùng yêu cầu; không đơn giản coi `23505` là tín hiệu phải retry. Nếu đã có booking hợp lệ với cùng ID nhưng khác tham số, phải báo xung đột yêu cầu.

Trong ứng dụng thực tế, mã lỗi có thể nằm ở nguyên nhân lồng trong exception của framework. Cần phân loại dựa trên error code và SQLSTATE từ driver thực tế, không chỉ tìm chuỗi trong exception message. Nếu server abort transaction nhưng connection vẫn dùng được, ứng dụng vẫn nên bắt đầu lần thử trên một transaction mới với trạng thái tài nguyên sạch.

## 6. Khi nào retry riêng câu lệnh trong Java?

Một service đọc độc lập có thể để mỗi lần thử mượn connection mới:

```java
// Phác thảo cách tổ chức; isRetryableReadError là chính sách
// phân loại lỗi DB/driver được ứng dụng tự triển khai.
for (int attempt = 1; attempt <= 3; attempt++) {
    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(
                 "SELECT status FROM orders WHERE order_id = ?")) {
        ps.setLong(1, orderId);
        try (ResultSet rows = ps.executeQuery()) {
            return rows.next() ? rows.getString(1) : null;
        }
    } catch (SQLException error) {
        if (attempt == 3 || !isRetryableReadError(error)) {
            throw error;
        }
        // Backoff hữu hạn ở đây, khi connection đã được đóng.
    }
}
```

Đây là **phác thảo**, không phải một phương thức Java hoàn chỉnh: nó giả định `dataSource`, `orderId` và bộ phân loại `isRetryableReadError` đã tồn tại ở tầng ứng dụng. Việc thử lại câu đọc như trên chỉ đúng nếu giao diện cho phép nhận trạng thái **mới nhất ở lần thử lại**, và truy vấn không có side effect.

Với một câu ghi trong transaction dài, không áp dụng máy móc vòng lặp tương tự quanh `executeUpdate()`. Trước hết phải biết:

- SQL trước đó đã được commit chưa? Nếu chưa rõ, cần đối soát.
- Transaction đang mở đã bị DB đánh dấu abort chưa? Nếu có, phải rollback toàn bộ hoặc về savepoint khi phù hợp.
- Câu SQL đó có thể lặp mà không gây tác động kép không?
- Những câu đọc và kiểm tra nghiệp vụ trước nó có còn đúng sau khi dữ liệu thay đổi không?

Nếu bất kỳ câu trả lời nào chưa được xác định, việc retry đúng **một câu SQL** có thể là sai phạm vi.

## 7. Khi không biết COMMIT đã thành công hay chưa

Một trong những lỗi nguy hiểm nhất là client không nhận được phản hồi khi commit:

```text
Ứng dụng                    DB
   |                        |
   | ------- COMMIT ------> |
   |                        | Ghi log / xác nhận commit
   |  X (mất kết nối)        |
   |                        |
   |   Không nhận được ACK   |
```

Hai khả năng đều phù hợp với điều ứng dụng quan sát: transaction **đã commit** nhưng phản hồi mất, hoặc **chưa commit** do sự cố trước khi xác nhận. Gọi `rollback()` trên connection đã hỏng không thể chứng minh transaction bên server đã bị hủy. Việc một lệnh `commit()` ném exception cũng **không đủ** để suy ra mọi câu ghi trước đó đã rollback.

Với booking có `booking_id` duy nhất, một quy trình xử lý an toàn hơn:

1. Giữ nguyên `booking_id` của yêu cầu ban đầu; **không** tạo ID mới khi retry hoặc đối soát.
2. Sau khi kết nối khôi phục, tra cứu trạng thái booking theo ID trên nguồn dữ liệu đủ nhất quán với quyết định (thường là primary DB).
3. Nếu tồn tại booking với đúng `event_id`, trả về kết quả đã được ghi; nếu tồn tại với tham số khác, báo xung đột idempotency.
4. Nếu không thấy booking, cân nhắc chính sách retry dựa trên đặc tính nhất quán của nguồn đọc và cơ chế khóa/idempotency của thiết kế. Không kết luận “chắc chắn chưa từng commit” chỉ từ một lần đọc ở replica có độ trễ.
5. Nếu hệ thống còn thanh toán, email hoặc broker, thực hiện đối soát những tác động đó bằng request ID tương ứng.

Ranh giới này phân biệt hai loại lỗi: **server xác nhận transaction đã bị abort** thì có thể retry trên transaction mới; **client không nhận được kết quả commit** thì phải xử lý tính bất định trước.

## 8. Timeout, backoff và giới hạn retry

Không có phạm vi retry nào an toàn nếu lặp không giới hạn hoặc giữ tài nguyên trong lúc chờ. Khi ứng dụng chịu tải cao, hàng nghìn request cùng lỗi có thể đồng thời retry và tạo thêm áp lực lên DB.

| Biện pháp | Mục đích | Lưu ý |
| --- | --- | --- |
| **Giới hạn số lần và tổng thời gian** | Tránh giữ request vô thời hạn | Cân nhắc deadline từ HTTP/gRPC hoặc hàng đợi phía trên. |
| **Backoff có jitter** | Giãn các lần thử, giảm đồng bộ tranh chấp | Chờ sau khi đã rollback và trả connection/khóa DB. |
| **Phân loại lỗi** | Chỉ retry loại lỗi có khả năng phục hồi | Timeout, deadlock, unique violation và connection loss cần các chính sách khác nhau. |
| **Idempotency key** | Tránh tạo lại tác động đã hoàn tất | Lưu trạng thái/đầu ra theo khóa duy nhất, kiểm tra tham số trùng khớp. |
| **Circuit breaker và bulkhead** | Ngăn lỗi lan rộng khi phụ thuộc ngoài/DB đang suy giảm | Không làm thay đổi trạng thái transaction hay thay thế rollback. |
| **Log/metric** | Phân biệt retry có ích với retry storm | Theo dõi tỷ lệ lỗi gốc, số lần retry, thời gian chờ, độ trễ và số trường hợp không rõ commit. |

Cũng cần tránh **retry lồng nhau**. Nếu repository retry ba lần, service retry thêm ba lần và HTTP gateway retry tiếp ba lần, một yêu cầu có thể phát sinh tối đa 27 lần thử dưới giả định mỗi tầng kích hoạt đủ số lần. Phải xác định tầng nào **sở hữu retry của một đơn vị nghiệp vụ**; tầng dưới có thể chỉ phân loại lỗi và trả lên.

Một hệ thống hàng đợi nên cân nhắc retry bất đồng bộ với hàng đợi trì hoãn hoặc dead-letter queue khi yêu cầu không cần kết quả ngay. Nhưng worker chạy lại tác vụ cũng phải có idempotency và ranh giới transaction được kiểm soát.

## 9. Khác biệt hệ quản trị cần kiểm tra

Không chỉ tên exception, **phạm vi rollback thực tế** và thời điểm sinh lỗi mới quyết định mức retry.

| Hệ quản trị | Hành vi cần xác nhận |
| --- | --- |
| **PostgreSQL** | SQLSTATE `40001` (serialization failure) và `40P01` (deadlock) thường cần retry **toàn bộ transaction**. Sau lỗi SQL trong transaction, các câu tiếp theo thường bị từ chối cho đến `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` hợp lệ. |
| **MySQL/InnoDB** | Deadlock victim thường rollback toàn transaction; lock wait timeout mặc định chỉ rollback statement trừ khi cấu hình `innodb_rollback_on_timeout` thay đổi. Mã MySQL 1213/1205 và SQLSTATE cần phân biệt. |
| **SQL Server** | Deadlock victim thường được báo bằng error 1205; cần bắt đầu lại transaction. Sau lỗi khác, kiểm tra trạng thái transaction, chẳng hạn bằng `XACT_STATE()` trong T-SQL, trước khi tiếp tục. |
| **Oracle Database** | Lỗi không tuần tự hóa, deadlock hoặc rollback statement có quy tắc riêng; không suy từ hành vi PostgreSQL rằng cả transaction luôn hoặc chỉ statement bị hủy. |
| **SQLite** | `SQLITE_BUSY`, `SQLITE_BUSY_SNAPSHOT`, chế độ journal/WAL và thời điểm nâng cấp read transaction lên write transaction có thể đòi hỏi retry ngoài transaction hiện tại. |

Ngay cả trong cùng một DB, mức cô lập, cấu hình lock timeout, chế độ auto-commit, savepoint và transaction manager có thể thay đổi kết quả. Một chiến lược triển khai phù hợp cần đọc tài liệu DB/driver đang dùng và kiểm chứng bằng các lịch chạy hai phiên, không dựa vào bảng mã lỗi tổng quát trên Internet.

Trong **Spring**, `@Transactional` thiết lập ranh giới giao dịch qua transaction manager. Nếu exception đã làm transaction bị đánh dấu `rollback-only`, việc gọi lại riêng repository method **trong cùng transaction** không tạo ra một transaction sạch. Hãy đặt retry bên ngoài proxy hoặc boundary bắt đầu transaction mới, ví dụ qua tầng điều phối tách biệt hoặc `TransactionTemplate` theo cấu hình thực tế. Phương thức `@Retryable` và `@Transactional` đặt trên cùng method cần kiểm tra **thứ tự advice/interceptor**, vì thứ tự này quyết định mỗi attempt có transaction mới hay dùng lại transaction đã hỏng.

## 10. Bài tập thực hành

### Bài tập 1 — Chọn phạm vi

Một transaction làm ba bước:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
SELECT seats_left FROM event_inventory WHERE event_id = 10;
UPDATE event_inventory
SET seats_left = seats_left - 1 WHERE event_id = 10;
INSERT INTO bookings(booking_id, event_id) VALUES ('00000000-0000-0000-0000-000000000010', 10);
COMMIT;
```

`COMMIT` trả SQLSTATE `40001`. Hỏi có nên chỉ retry câu `INSERT` không? **Đáp án:** không. Giao dịch cũ đã bị hủy do xung đột; phải bắt đầu transaction mới, đọc lại số chỗ, kiểm tra điều kiện và chạy các bước ghi cần thiết. Đồng thời, câu `UPDATE` trong ví dụ bài tập cần bổ sung điều kiện `seats_left > 0` để tránh giảm âm số chỗ.

### Bài tập 2 — Timeout và kết quả chưa biết

Ứng dụng gọi `COMMIT` cho thao tác trừ tiền, sau đó socket bị ngắt trước khi nhận phản hồi. Hỏi có thể thử lại nguyên lệnh trừ tiền ngay không? **Đáp án:** không. Phải xác minh yêu cầu theo mã idempotency duy nhất hoặc trạng thái giao dịch đã ghi, vì lần đầu có thể đã commit.

### Bài tập 3 — Savepoint

Một nhóm bước gắn nhãn tùy chọn nằm sau `SAVEPOINT optional_tag`. Câu `INSERT` vi phạm khóa ngoại PostgreSQL và trả `23503`. Hỏi nên retry statement, toàn transaction hay rollback về savepoint? **Đáp án:** nếu quy tắc nghiệp vụ cho phép bỏ nhãn, rollback về savepoint rồi tiếp tục phần bắt buộc. Retry cùng statement với mã nhãn sai không có ích; nếu lỗi khiến toàn bộ giao dịch không còn đáp ứng bất biến thì rollback toàn phần.

### Bài tập 4 — Lỗi khóa và backoff

Hai transaction tranh chấp dữ liệu; một transaction được PostgreSQL chọn làm deadlock victim (`40P01`). Ứng dụng giữ connection trong lúc `Thread.sleep(5000)` rồi mới thử lại. Có gì cần sửa?

**Đáp án:** rollback và đóng/trả connection trước khi chờ, thử lại **toàn transaction** trên transaction mới; giới hạn số lần và dùng backoff ngắn có jitter. Nếu chờ dài trong transaction cũ, các tài nguyên vẫn có thể bị giữ và làm tăng contention.

### Checklist trước khi triển khai retry

- Có xác định rõ lỗi **đã abort**, lỗi **chỉ hủy statement**, lỗi nghiệp vụ và trường hợp **commit không rõ** chưa?
- Các phép đọc, kiểm tra và ghi nào thuộc cùng một đơn vị nhất quán và phải chạy lại từ đầu?
- Bên ngoài transaction có email, HTTP, broker, file hoặc thanh toán nào có thể bị thực hiện lặp không?
- Retry có mở transaction sạch, rollback đúng cách và trả connection trước backoff không?
- Có mã idempotency/khóa nghiệp vụ cho trường hợp kết quả ghi chưa rõ, và có kiểm tra trùng tham số không?
- Có giới hạn lần thử, deadline, phân loại SQLSTATE/error code theo DB, metric và cách báo lỗi cuối cùng không?
- Đã kiểm thử đồng thời với serialization conflict, deadlock, optimistic conflict, mất kết nối lúc commit và khởi động lại chưa?

**Kết luận:** Phạm vi retry được quyết định bởi **tính nhất quán của cả quy trình**, trạng thái giao dịch sau lỗi và khả năng xác minh tác động đã xảy ra. Một câu đọc độc lập có thể chỉ cần thử lại statement; xung đột làm abort giao dịch đòi hỏi chạy lại toàn bộ bước đọc–quyết định–ghi; còn kết quả commit không rõ phải được đối soát trước khi tạo tác động lần nữa. Mọi chiến lược đều cần giới hạn retry, giải phóng tài nguyên và bảo vệ idempotency.
