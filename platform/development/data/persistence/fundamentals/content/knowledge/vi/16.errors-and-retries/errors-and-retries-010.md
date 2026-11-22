# Đối soát trạng thái sau kết quả ghi không rõ ràng

Trong chương **Lỗi và thử lại** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, có một tình huống nguy hiểm hơn câu lệnh SQL trả lỗi rõ ràng: **ứng dụng Java gửi một thao tác ghi, nhưng mất phản hồi trước khi biết giao dịch đã được commit hay chưa**. Nếu coi mọi timeout là thất bại rồi ghi lại từ đầu, ứng dụng có thể trừ tiền hai lần, tạo hai đơn hàng hoặc gửi cùng một tác vụ nhiều lần. Nếu coi timeout là thành công, ứng dụng lại có thể báo đã ghi nhận một thay đổi chưa từng được lưu.

Giải pháp là **đối soát trạng thái** (*reconciliation*): dùng một định danh nghiệp vụ ổn định để kiểm tra kết quả đã được ghi bền vững, phân biệt kết quả xác nhận với trạng thái còn chưa rõ, rồi mới quyết định trả lời người dùng hoặc thử lại. Đây là kỹ năng quan trọng khi thiết kế ranh giới persistence cho Java, xử lý lỗi kết nối, giao dịch, độ cô lập và độ bền.

## 1. Khi nào kết quả ghi trở nên không rõ ràng?

Giả sử một API chuyển 500.000 đồng từ tài khoản A sang B. Ứng dụng đã chạy các câu lệnh cập nhật và gửi `COMMIT`. Ngay sau đó, kết nối TCP bị đứt:

```text
Ứng dụng Java                  Database
     |                            |
     | BEGIN                      |
     |--------------------------->|
     | UPDATE A, UPDATE B         |
     |--------------------------->|
     | COMMIT                     |
     |--------------------------->|
     |                       WAL được ghi
     |                       COMMIT hoàn tất
     |               X  Mất kết nối trước phản hồi
     |<--------- không nhận ACK --|
     |
     | SQLException / timeout
     | Nhưng giao dịch có thể ĐÃ COMMIT!
```

Ứng dụng chỉ biết **không nhận được xác nhận**. Điều đó khác với việc **database đã từ chối hoặc rollback**. Sau một lỗi kết nối, có thể tồn tại những khả năng sau:

| Khả năng | Thực tế ở database | Ứng dụng quan sát được |
| --- | --- | --- |
| Yêu cầu chưa đến server | Không có giao dịch nào được thực hiện | Timeout/lỗi mạng |
| Server nhận yêu cầu nhưng lỗi trước commit | Transaction bị rollback hoặc không hoàn tất | Timeout/lỗi kết nối |
| Server đang xử lý khi kết nối bị ngắt | Giao dịch có thể còn đang chạy hoặc đang được giải quyết | Timeout/lỗi kết nối |
| Server commit thành công nhưng ACK bị mất | Thay đổi đã được commit theo chính sách độ bền | Timeout/lỗi kết nối |
| Server commit, sau đó xảy ra failover | Kết quả phụ thuộc chính sách replication và nút được chọn | Timeout, gián đoạn hoặc dữ liệu đọc có vẻ không nhất quán |

Các trường hợp này có thể **giống hệt nhau từ góc nhìn client**. Vì vậy, một ngoại lệ I/O không phải bằng chứng đủ mạnh để khẳng định thao tác đã thất bại.

Không chỉ `COMMIT` mới gây mơ hồ. Khi gọi API database ở chế độ auto-commit, một câu `INSERT` hoặc `UPDATE` đơn lẻ có thể được commit ngay trước khi phản hồi của câu lệnh bị mất. Đối với lệnh ghi qua message broker hoặc dịch vụ ngoài, ACK cũng có thể bị thất lạc theo cách tương tự.

## 2. Ba nhóm kết quả cần phân biệt

Một hệ thống có cơ chế phục hồi rõ ràng nên phân biệt ít nhất ba nhóm:

| Nhóm | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| **Đã xác nhận thành công** | Có bằng chứng từ nguồn dữ liệu có thẩm quyền rằng nghiệp vụ đã được commit. | Trả kết quả đã lưu; không thực hiện lại tác dụng phụ. |
| **Đã xác nhận bị từ chối/thất bại** | Có bằng chứng rằng nghiệp vụ không được chấp nhận, ví dụ kết quả từ chối đã được ghi bền vững hoặc transaction bị rollback xác định. | Trả lý do; chỉ tạo yêu cầu mới nếu nghiệp vụ cho phép. |
| **Chưa rõ** (*unknown/indeterminate*) | Client chưa có bằng chứng đáng tin cậy cho hai trường hợp trên. | Đối soát, chờ có giới hạn hoặc thử lại **cùng định danh** qua giao thức an toàn. |

**Trạng thái chưa rõ là một kết quả hợp lệ của hệ thống phân tán.** Không nên buộc chương trình biến nó thành `SUCCESS` hay `FAILED` chỉ để trả HTTP 200 hoặc 500 nhanh hơn.

Một mô hình ở tầng API có thể tách trạng thái **đang xử lý** khỏi **chưa xác định được**:

```text
                  POST nghiệp vụ với request_id
                              |
                              v
                      RECEIVED / PROCESSING
                         /           \
                        v             v
                  APPLIED          REJECTED
                       \             /
                        \           /
                 Trạng thái cuối bền vững

Nếu mất ACK hoặc nguồn tra cứu chưa sẵn sàng:
  UNKNOWN → đối soát → APPLIED / REJECTED / tiếp tục UNKNOWN
```

Các trạng thái `RECEIVED`, `PROCESSING` hoặc `UNKNOWN` có thể là trạng thái **điều phối ở ứng dụng**; không nhất thiết là những hàng đã commit trong database. Khi thiết kế lưu trạng thái trung gian, cần quy định ai được phép tiếp quản yêu cầu bỏ dở và khi nào hết hạn quyền xử lý.

## 3. Muốn đối soát phải có định danh nghiệp vụ ổn định

Trước khi gửi lệnh ghi, client hoặc tầng API cần tạo một **mã yêu cầu duy nhất** (*request ID* hoặc *idempotency key*). Mã này biểu thị **một ý định nghiệp vụ**, ví dụ “chuyển 500.000 đồng từ A sang B một lần”.

Ví dụ yêu cầu HTTP:

```http
POST /transfers HTTP/1.1
Idempotency-Key: 18d7e862-283a-4ae1-9d52-b2a277d1f96d
Content-Type: application/json

{
  "fromAccount": 101,
  "toAccount": 202,
  "amount": "500000.00"
}
```

Nếu client gặp timeout, **lần thử lại phải dùng chính mã này và cùng nội dung nghiệp vụ**. Tạo mã ngẫu nhiên mới cho mỗi lần retry sẽ khiến server nhìn thấy các yêu cầu khác nhau và có thể thực hiện chuyển khoản nhiều lần.

Một khóa idempotency tốt có các thuộc tính:

1. **Ổn định qua các lần thử:** tạo trước lần gửi đầu tiên; giữ lại khi ứng dụng khởi động lại nếu cần phục hồi.
2. **Duy nhất trong phạm vi rõ ràng:** theo toàn hệ thống hoặc kết hợp với tenant/account tùy thiết kế; database có `UNIQUE` hay `PRIMARY KEY` tương ứng.
3. **Gắn với nội dung yêu cầu:** nếu cùng khóa được gửi với số tiền hoặc tài khoản khác, phải từ chối và báo xung đột; không được âm thầm áp dụng nội dung mới.
4. **Được lưu bền vững cùng kết quả nghiệp vụ:** không chỉ giữ trong RAM hay Redis cache có thể mất trước khi giao dịch được đối soát.
5. **Có chính sách giữ dữ liệu:** thời gian giữ khóa phải bao phủ tối đa khoảng có thể retry, trễ hàng đợi và thời gian cần tra soát; với giao dịch tài chính có thể cần lưu lịch sử lâu hơn.

**Request ID khác trace ID.** Trace ID có ích khi tìm log và theo dõi một đường gọi, nhưng từng lần retry có thể có trace riêng. Request ID xác định **nghiệp vụ không được thực hiện trùng**.

Không dùng mỗi timestamp, số thứ tự cục bộ của một process hoặc ID sinh lại sau restart làm khóa chống trùng nếu chúng không được đảm bảo duy nhất trong phạm vi hệ thống.

## 4. Ghi bằng chứng và thay đổi nghiệp vụ trong cùng transaction

Đối soát chỉ đáng tin nếu **bản ghi kết quả** và **thay đổi nghiệp vụ** có cùng số phận commit. Giả sử cập nhật số dư được commit trước, nhưng dòng trạng thái thao tác được ghi bằng transaction khác:

```text
Transaction 1: trừ tiền, cộng tiền → COMMIT
Ứng dụng sập
Transaction 2: INSERT request_status → chưa chạy
```

Khi retry, không thấy `request_status`; hệ thống có thể chuyển tiền **lần thứ hai**. Đây là lỗi thiết kế điểm đối soát.

Mẫu đáng tin cậy hơn là:

```text
Một transaction database
  ├─ Chặn trùng bằng UNIQUE(request_id)
  ├─ Ghi bản ghi kết quả / ý định đã xử lý
  ├─ Thay đổi dữ liệu nghiệp vụ
  └─ (Nếu cần) ghi outbox event
          |
          v
      COMMIT tất cả
```

Nếu transaction rollback, bản ghi kết quả và thay đổi nghiệp vụ đều không tồn tại. Nếu commit, chúng cùng xuất hiện từ một điểm quan sát đã commit phù hợp. Điều này **không biến hai database hoặc một API bên ngoài thành một transaction chung**; phạm vi atomicity vẫn là những tài nguyên được quản lý trong cùng transaction đó.

### Thiết kế bảng ví dụ trên PostgreSQL

Giả sử đây là chuyển tiền nội bộ giữa hai tài khoản nằm trong **cùng một database**:

```sql
CREATE TABLE accounts (
    id      BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL CHECK (balance >= 0)
);

CREATE TABLE transfer_operations (
    request_id        UUID PRIMARY KEY,
    from_account_id   BIGINT NOT NULL REFERENCES accounts(id),
    to_account_id     BIGINT NOT NULL REFERENCES accounts(id),
    amount            NUMERIC(19, 2) NOT NULL CHECK (amount > 0),
    status            TEXT NOT NULL
                      CHECK (status IN ('APPLIED', 'REJECTED')),
    rejection_code    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_account_id <> to_account_id),
    CHECK (
        (status = 'APPLIED' AND rejection_code IS NULL)
        OR
        (status = 'REJECTED' AND rejection_code IS NOT NULL)
    )
);
```

Đây là schema minh họa để học giao dịch, chưa phải một sổ cái kế toán đầy đủ. Hệ thống tài chính thật còn cần ledger bất biến, quyền truy cập, giới hạn, kiểm toán, quy tắc tiền tệ và đối chiếu số dư.

Trong bảng này, **hàng đã commit** với `APPLIED` nghĩa là chuyển tiền thành công; hàng đã commit với `REJECTED` nghĩa là yêu cầu đã bị từ chối theo quy tắc cụ thể. Mã `request_id` là khóa duy nhất, và các cột `from_account_id`, `to_account_id`, `amount` cho phép kiểm tra lại nội dung khi cùng khóa được gửi lần nữa.

### Quy trình ghi có bảo vệ trùng lặp

Ứng dụng dùng một transaction và chạy các bước sau. Các nhánh `if/else` là **logic của ứng dụng**, không phải cú pháp SQL chạy nguyên khối:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

INSERT INTO transfer_operations (
    request_id, from_account_id, to_account_id,
    amount, status, rejection_code
)
VALUES (
    :request_id, :from_id, :to_id,
    :amount, 'REJECTED', 'INSUFFICIENT_FUNDS'
)
ON CONFLICT (request_id) DO NOTHING
RETURNING request_id;
```

**Nếu câu INSERT trả 0 hàng:**

- Một transaction khác đã chấp nhận hoặc đang giải quyết cùng khóa. Với PostgreSQL, kiểm tra unique có thể phải **đợi** transaction cạnh tranh kết thúc.
- Kết thúc transaction hiện tại và **truy vấn lại theo `request_id` trên primary** bằng một câu lệnh mới, rồi kiểm tra các tham số nghiệp vụ có khớp không.
- Nếu tham số khớp, trả **kết quả đã commit**. Nếu khác, trả **xung đột khóa idempotency**. Nếu vẫn không đọc được kết quả đáng tin cậy, trạng thái là **chưa rõ** và cần tiếp tục đối soát.

**Nếu câu INSERT trả 1 hàng:** ứng dụng sở hữu quyền xử lý khóa trong transaction hiện tại; thực hiện cập nhật số dư có điều kiện:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :from_id
  AND balance >= :amount;
```

Nếu câu lệnh trên cập nhật **0 hàng**, database không trừ tiền. Ứng dụng có thể `COMMIT` transaction với bản ghi `REJECTED / INSUFFICIENT_FUNDS` đã tạo, khiến kết quả từ chối trở thành **kết quả cuối ổn định** cho cùng `request_id`. Một lần gửi lại cùng khóa vẫn nhận từ chối, kể cả tài khoản được nạp tiền sau đó. Nếu sản phẩm muốn người dùng thử lại sau khi nạp tiền, đó phải là **một ý định mới với request ID mới**.

Nếu câu lệnh trên cập nhật **1 hàng**, tiếp tục:

```sql
UPDATE accounts
SET balance = balance + :amount
WHERE id = :to_id;
-- Yêu cầu chính xác 1 hàng; nếu không thì ROLLBACK.

UPDATE transfer_operations
SET status = 'APPLIED', rejection_code = NULL
WHERE request_id = :request_id;
-- Yêu cầu chính xác 1 hàng trong cùng transaction.

COMMIT;
```

Nếu bất kỳ bước bắt buộc nào thất bại, **rollback cả transaction**, kể cả hàng `transfer_operations` và lần trừ tiền. Bản ghi được INSERT tạm lúc đầu có trạng thái `REJECTED` nhưng **chưa commit**, nên giao dịch khác không nhìn thấy một kết quả từ chối giả trong lúc giao dịch vẫn đang thực hiện chuyển tiền.

Một số chi tiết quan trọng:

- Các giá trị `:request_id`, `:from_id`, `:to_id`, `:amount` là **tham số ràng buộc** do ứng dụng truyền qua PreparedStatement hoặc thư viện SQL; không ghép chuỗi từ dữ liệu người dùng.
- Ràng buộc tham chiếu trong ví dụ giúp bảo đảm cả hai tài khoản tồn tại khi tạo thao tác. Kiểm tra quyền thực hiện và hạn mức vẫn thuộc logic nghiệp vụ.
- Mọi câu SQL phải dùng **cùng connection/transaction**. Không lấy connection mới để ghi bản ghi kết quả sau khi đã commit số dư.
- Câu `ON CONFLICT DO NOTHING` chỉ là công cụ chặn trùng; **kiểm tra các trường yêu cầu trùng khóa** mới bảo vệ khỏi việc dùng lại khóa cho nội dung khác.
- Nếu muốn lưu thêm lịch sử chuyển tiền hoặc outbox event, ghi chúng trong cùng transaction trước `COMMIT`.
- Cơ chế chống trùng này bảo đảm trong phạm vi **một primary/database với tính duy nhất và độ bền phù hợp**. Nó không tự giải quyết mất dữ liệu khi failover sang replica chưa nhận commit.

## 5. Khi mất phản hồi commit, đối soát ra sao?

Giả sử client không nhận ACK sau lần gửi đầu với `request_id = X`. Một quy trình đối soát an toàn bắt đầu bằng việc **truy vấn nguồn dữ liệu có thẩm quyền**, không dựa vào biến RAM của request cũ:

```text
Client timeout sau yêu cầu ghi X
              |
              v
Truy vấn trạng thái X từ nguồn đọc có tính nhất quán phù hợp
              |
       +------+-------+
       |              |
   Có bản ghi      Chưa thấy bản ghi
       |              |
       v              v
 So tham số         Không kết luận thất bại ngay
       |              |
  +----+----+         v
  |         |     Có thể còn giao dịch in-flight,
Khớp       Khác    replica lag hoặc failover
  |         |         |
  v         v         v
Trả kết  Từ chối    Thử lại CÙNG request_id
quả đã   key trùng  qua giao thức chặn trùng,
commit   khác nội   hoặc tiếp tục chờ/đối soát
         dung       với deadline hữu hạn
```

**Có bản ghi APPLIED đã commit** và tham số khớp: trả thành công dựa trên bản ghi hiện có, không chạy lại chuyển tiền. **Có bản ghi REJECTED**: trả lý do từ chối đã lưu. **Có bản ghi nhưng tham số khác**: trả xung đột, không dùng khóa đó cho yêu cầu mới.

**Không thấy bản ghi** là quan sát “chưa thấy kết quả đã commit ở nguồn vừa đọc”, **không tự động chứng minh lần ghi ban đầu đã rollback**. Transaction cũ có thể còn chạy hoặc bản đọc có thể chưa nhìn thấy commit. Vì vậy, bước tiếp theo phải được thiết kế để **an toàn ngay cả khi lần ghi trước thực ra đã thành công**.

Với sơ đồ trong phần 4, thử lại **cùng request ID trên primary** sẽ đi qua ràng buộc unique của cùng database. Nếu lần trước đã commit, yêu cầu sau không chạy lại cập nhật; nếu lần trước chưa từng commit, một yêu cầu có thể thực hiện nghiệp vụ. Nếu giao dịch trước còn đang giữ khóa unique, yêu cầu sau có thể phải chờ hoặc gặp timeout rồi tiếp tục ở trạng thái chưa rõ.

### Chọn nguồn đọc đúng khi đối soát

Với hệ thống có replica bất đồng bộ, truy vấn một read replica rồi thấy “không có request X” **không chứng minh** primary chưa commit. Replica có thể chỉ đang chậm.

Nguyên tắc:

1. Khi cần xác định **kết quả cuối của một thao tác ghi**, ưu tiên primary hoặc đường đọc được cấu hình bảo đảm độ mới/nhất quán tương ứng.
2. Nếu phải đọc replica, cần một cơ chế **đợi tới mốc WAL/LSN hoặc commit watermark đã biết** rồi mới diễn giải kết quả; cách thực hiện tùy DBMS và topology.
3. Khi failover, phải xác minh primary mới đã có các commit thuộc phạm vi cam kết; với replication bất đồng bộ, một commit từng được ACK trên primary cũ **có thể bị mất** sau khi primary cũ không còn truy cập được.
4. Không tuyên bố “exactly once qua mọi thảm họa” chỉ vì có khóa unique trên một node; điều đó còn phụ thuộc độ bền và cơ chế failover của hệ thống lưu trữ.

Trong PostgreSQL thông thường, một truy vấn mới ở mức `READ COMMITTED` trên primary thấy dữ liệu đã commit trước thời điểm snapshot của câu lệnh. Tuy nhiên, nếu transaction nguồn **đang tiếp tục**, truy vấn trạng thái có thể chưa thấy kết quả; cần lặp đối soát có giới hạn hoặc để lần gửi lại cùng khóa đối đầu với cơ chế unique.

## 6. Java/JDBC: viết và truy vấn theo cùng mã yêu cầu

Ví dụ tiếp theo minh họa cách tổ chức API persistence. Trước tiên, đặt câu lệnh kiểm tra kết quả tách riêng khỏi thao tác ghi; nó phải kết nối đến **nguồn primary có thẩm quyền**, không vô tình qua read replica chỉ vì đây là một câu `SELECT`.

### 6.1. Đọc bản ghi kết quả đã commit

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;

public final class TransferReconciliationRepository {
    private final DataSource primaryDataSource;

    public TransferReconciliationRepository(DataSource primaryDataSource) {
        this.primaryDataSource = primaryDataSource;
    }

    public record StoredOutcome(
            UUID requestId,
            long fromAccount,
            long toAccount,
            BigDecimal amount,
            String status,
            String rejectionCode
    ) {
        public boolean matches(long from, long to, BigDecimal requestedAmount) {
            return fromAccount == from
                    && toAccount == to
                    && amount.compareTo(requestedAmount) == 0;
        }
    }

    public Optional<StoredOutcome> findCommitted(UUID requestId)
            throws SQLException {
        String sql = """
            SELECT request_id, from_account_id, to_account_id,
                   amount, status, rejection_code
            FROM transfer_operations
            WHERE request_id = ?
            """;

        // DataSource được cấu hình định tuyến tới primary.
        try (Connection connection = primaryDataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, requestId);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(new StoredOutcome(
                        (UUID) rows.getObject("request_id"),
                        rows.getLong("from_account_id"),
                        rows.getLong("to_account_id"),
                        rows.getBigDecimal("amount"),
                        rows.getString("status"),
                        rows.getString("rejection_code")
                ));
            }
        }
    }
}
```

Mã ví dụ dùng Java hỗ trợ `record` và text block. `Optional.empty()` có nghĩa **chưa thấy hàng đã commit tại thời điểm truy vấn**. Nó không được tự động chuyển thành kết quả “giao dịch cũ chắc chắn thất bại”. Nếu chính truy vấn đối soát ném `SQLException`, trạng thái vẫn **chưa rõ**, cần xử lý lỗi đọc rồi thử lại theo giới hạn.

Trong hệ thống nhiều tenant, truy vấn phải có điều kiện quyền sở hữu/tenant phù hợp; không cho người dùng đoán `request_id` của người khác để đọc kết quả chuyển tiền. Việc so tham số ở `matches()` cũng nên dùng biểu diễn tiền chuẩn hóa và kiểm tra cả những trường nghiệp vụ khác có thể ảnh hưởng kết quả.

### 6.2. Xử lý ngoại lệ ở ranh giới commit

Mẫu JDBC cho một transaction ghi:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        // 1. Đăng ký request_id bằng UNIQUE trong transaction này.
        // 2. Kiểm tra nhánh trùng: không chạy lại nghiệp vụ.
        // 3. Thay đổi dữ liệu, ghi trạng thái và outbox nếu cần.
        connection.commit();
        // Chỉ ở đây mới coi commit đã được server xác nhận.
    } catch (SQLException | RuntimeException error) {
        try {
            connection.rollback(); // Cố gắng dọn transaction chưa kết thúc.
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
}
```

**Lưu ý quyết định:** `rollback()` sau lỗi `commit()` là cách dọn dẹp tốt nhất có thể, **không phải bằng chứng rằng commit trước đó chưa xảy ra**. Tầng ứng dụng cần nhận ra trường hợp mất kết nối/timeout quanh thời điểm commit, đưa request vào luồng đối soát thay vì tự ý phát lại nghiệp vụ với mã mới.

Một giao dịch đã được database từ chối rõ ràng bằng lỗi serialization hoặc deadlock thường cần rollback và thử lại **toàn bộ transaction**. Trường hợp **mất ACK commit** có tính chất khác: phải kiểm tra theo request ID hoặc dùng giao thức idempotent đủ mạnh trước khi thử lại.

### 6.3. Logic điều phối đối soát

Giả mã sau nhấn mạnh sự khác nhau giữa **quan sát trạng thái** và **thực hiện lại nghiệp vụ**:

```text
reconcile(request_id, original_payload):
    retry_budget = hữu hạn

    trong khi còn retry_budget:
        thử đọc từ nguồn primary có thẩm quyền
        nếu thấy kết quả đã commit:
            nếu payload khác: trả CONFLICT
            nếu APPLIED: trả APPLIED từ bản ghi hiện có
            nếu REJECTED: trả REJECTED từ bản ghi hiện có

        nếu chưa thấy kết quả:
            có thể gọi lại submit(original_payload, CÙNG request_id)
            submit phải dùng UNIQUE(request_id) trong transaction ghi
            và không tạo thêm tác dụng phụ nếu request_id đã tồn tại

        nếu bị timeout, mạng lỗi hoặc giao dịch vẫn đang chạy:
            đợi theo backoff + jitter, rồi đối soát tiếp

    trả UNKNOWN / PROCESSING kèm request_id và điểm kiểm tra sau
```

Thực tế nên đặt **deadline tổng thể**, giới hạn số lần truy vấn, số lần submit, mức chờ khóa, bảo vệ khi primary không sẵn sàng và cơ chế để tiếp tục đối soát sau khi process khởi động lại. Không giữ một JDBC connection xuyên suốt thời gian đợi giữa các lần đối soát.

## 7. Lập quy tắc thử lại theo loại lỗi

Không phải lỗi SQL nào cũng cần retry, và không phải kết quả không rõ nào cũng an toàn để retry tự do:

| Tình huống | Điều có thể kết luận | Hướng xử lý |
| --- | --- | --- |
| Kiểm tra nghiệp vụ từ chối và ghi `REJECTED` thành công | Đã có trạng thái cuối | Trả từ chối theo request ID, không gửi lại như một thao tác mới. |
| Trùng `request_id` | Khóa đã hoặc đang được một transaction khác sử dụng | Đợi/đối soát và so sánh payload; không ghi đè dữ liệu cũ. |
| PostgreSQL `40001` (*serialization_failure*) | Transaction bị từ chối và cần chạy lại | Rollback, retry toàn transaction với giới hạn, giữ nguyên request ID. |
| PostgreSQL `40P01` (*deadlock_detected*) | Database đã hủy một transaction xung đột | Rollback và xem xét retry toàn transaction nếu nghiệp vụ an toàn. |
| Lỗi validation/constraint xác định | Dữ liệu không hợp lệ theo ràng buộc | Trả lỗi phù hợp; chỉ tạo yêu cầu mới sau khi sửa dữ liệu. |
| Timeout khi đợi lấy connection trước khi bắt đầu SQL | Chưa mượn được kết nối từ pool để thực hiện thao tác này | Có thể thử sau, nhưng vẫn phải giữ request ID ổn định. |
| Đứt kết nối hoặc timeout trong lúc gửi lệnh ghi/commit | Có thể chưa chạy, đã rollback, vẫn chạy hoặc đã commit | Đối soát và chỉ retry qua giao thức idempotent. |
| Query đối soát không truy cập được primary | Chưa biết kết quả | Giữ `UNKNOWN`, không chuyển thành `FAILED`. |
| Replica không có bản ghi nhưng primary có | Replica bị trễ | Không kết luận thất bại dựa trên replica. |

Một số driver/gateway cung cấp SQLSTATE hoặc mã lỗi cụ thể, nhưng **không nên suy ra chính xác trạng thái commit chỉ từ thông báo ngoại lệ mạng**. Cùng một timeout có thể xuất hiện ở những thời điểm khác nhau trên đường truyền.

### Retry an toàn cần những điều kiện gì?

- **Cùng ý định:** request ID và payload không đổi; không tạo yêu cầu mới chỉ vì chưa nhận ACK.
- **Ràng buộc chống trùng bền vững:** database từ chối hoặc nhận diện lại cùng khóa ngay trong transaction.
- **Không thực hiện tác dụng phụ trước khi biết kết quả:** gửi mail, gọi cổng thanh toán, phát message phải có cơ chế phối hợp riêng.
- **Giới hạn và backoff:** tránh làm quá tải hệ thống đang gặp lỗi; tính cả timeout của pool, truy vấn và HTTP.
- **Có cách truy vấn kết quả:** nếu client không thể lấy lại trạng thái theo request ID, người dùng dễ bấm gửi lại bằng yêu cầu khác.
- **Theo dõi và cảnh báo:** yêu cầu `UNKNOWN` quá hạn cần một quy trình tiếp quản/đối soát hoặc xử lý thủ công.

## 8. Cẩn thận với trạng thái PROCESSING được commit trước

Một số hệ thống chọn ghi bản ghi `PROCESSING` trong transaction riêng, rồi gọi dịch vụ khác, cuối cùng cập nhật `SUCCEEDED` hoặc `FAILED`. Mẫu này không sai, nhưng **trạng thái PROCESSING tồn tại bền vững chưa chứng minh nghiệp vụ đã hoặc chưa được áp dụng**.

Ví dụ nguy hiểm:

```text
T1: INSERT operation(status='PROCESSING'); COMMIT
T2: gọi cổng thanh toán; cổng có thể đã thu tiền
Ứng dụng sập trước UPDATE operation(status='SUCCEEDED')
```

Sau restart, trạng thái vẫn là `PROCESSING`. Nếu tự động “xử lý lại mọi PROCESSING” bằng một yêu cầu thu tiền mới, khách hàng có thể bị thu hai lần.

Muốn thiết kế worker có thể tiếp quản, cần:

1. **Lease/quyền xử lý có thời hạn** hoặc cơ chế khóa để tránh nhiều worker cùng xử lý một operation.
2. **Mã yêu cầu ổn định gửi cho hệ thống bên ngoài**, nếu hệ thống đó hỗ trợ idempotency.
3. **API tra cứu kết quả bên ngoài** để đối soát khi mất phản hồi.
4. **Quy tắc chuyển trạng thái có điều kiện** và cách xử lý operation quá hạn; không coi “lease hết hạn” là chứng minh bên ngoài chưa thực hiện.
5. **Bản ghi kết quả cuối** được lưu bền và không bị một worker chậm ghi đè sau khi worker khác đã hoàn tất.

Trường hợp xử lý có thể hoàn tất trong **một transaction của cùng database**, mẫu ở phần 4 đơn giản hơn vì không cần commit một trạng thái trung gian rồi tự phục hồi công việc ở giữa.

## 9. Nếu thao tác còn liên quan API thanh toán hoặc message broker

Tính nguyên tử của database **không bao trùm** một API thanh toán, email hoặc message broker chạy độc lập.

### 9.1. Thu tiền qua nhà cung cấp bên ngoài

Giả sử bước thu tiền sử dụng một provider hỗ trợ mã idempotency và API kiểm tra giao dịch:

```text
Ứng dụng đặt hàng
    |
    +-- Tạo order_id / payment_request_id ổn định
    |
    +-- Gọi provider với payment_request_id
    |        |
    |        +-- Provider thực thi, ACK bị mất
    |
    +-- Không biết đã thu tiền chưa
             |
             +-- Tra cứu provider theo payment_request_id
             +-- Nếu chưa rõ: thử lại cùng id theo hợp đồng provider
             +-- Lưu kết quả cuối tại database của ứng dụng
```

Phải đọc hợp đồng của provider về **phạm vi và thời hạn hiệu lực của idempotency key**, trạng thái giao dịch, retry và webhook. Không mặc định mọi API đều hỗ trợ chính xác một lần thu tiền trên mọi khoảng thời gian. Nếu provider không có cơ chế đối soát đáng tin, yêu cầu `UNKNOWN` có thể cần đội vận hành xử lý thủ công trước khi thử một hành động có khả năng thu tiền lần nữa.

Nếu webhook đến trước phản hồi API hoặc được gửi lại nhiều lần, xử lý webhook theo **event ID hoặc transaction ID duy nhất** và cập nhật trạng thái theo các bước hợp lệ. Không để một webhook cũ ghi đè trạng thái mới hơn.

### 9.2. Phát sự kiện sau commit và transactional outbox

Nếu ứng dụng commit đơn hàng rồi gọi broker, có khoảng trống:

```text
COMMIT đơn hàng thành công
Ứng dụng sập
Chưa gửi OrderCreated tới broker
```

**Transactional outbox** lưu cùng lúc dữ liệu nghiệp vụ và sự kiện chờ gửi trong **một database transaction**:

```sql
CREATE TABLE outbox_events (
    event_id    UUID PRIMARY KEY,
    request_id  UUID NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL,
    sent_at     TIMESTAMPTZ
);

-- Trong cùng transaction áp dụng nghiệp vụ:
INSERT INTO outbox_events (
    event_id, request_id, event_type, payload
)
VALUES (
    :event_id, :request_id, 'TransferApplied', :event_payload
);
```

Một worker đọc outbox để gửi message. Nếu gửi thành công rồi sập trước khi đánh dấu `sent_at`, worker có thể gửi lại. Vì vậy consumer phải **xử lý idempotent theo event ID**. Outbox giúp tránh bỏ sót sự kiện khi ứng dụng sập sau commit, nhưng không tự cam kết broker/consumer nhận sự kiện đúng một lần trên mọi đường lỗi.

### 9.3. Saga và trạng thái từng bước

Khi nghiệp vụ gồm nhiều hệ độc lập như giữ kho → thu tiền → tạo vận đơn, cần lưu **trạng thái từng bước** và một ID xuyên suốt. Nếu bước thứ hai không rõ kết quả, không được lập tức chạy bước bù trừ hoặc chạy lại thu tiền trước khi đối soát. Với hệ phân tán, “rollback toàn bộ” có thể không tồn tại; cần workflow, bù trừ có điều kiện và idempotency riêng cho từng bước.

## 10. Thiết kế API để client tiếp tục được khi kết quả chưa rõ

Một API tốt cho thao tác ghi có tác dụng phụ nên giúp client **lấy lại kết quả theo request ID**:

```http
POST /transfers
Idempotency-Key: 18d7e862-283a-4ae1-9d52-b2a277d1f96d

GET /transfer-operations/18d7e862-283a-4ae1-9d52-b2a277d1f96d
```

Một phương án trạng thái:

| Kết quả nghiệp vụ | HTTP có thể sử dụng | Nội dung trả về |
| --- | --- | --- |
| Đã áp dụng | `200 OK` hoặc `201 Created` tùy hợp đồng | `requestId`, `status=APPLIED`, mã giao dịch |
| Đã từ chối | `200` kèm kết quả nghiệp vụ hoặc mã `4xx` phù hợp | `requestId`, `status=REJECTED`, mã lý do |
| Đang xử lý/chờ đối soát | `202 Accepted` | `requestId`, trạng thái, URL kiểm tra lại hoặc `Retry-After` |
| Cùng idempotency key nhưng payload khác | `409 Conflict` là một lựa chọn | Mã xung đột, không áp dụng yêu cầu khác |
| Không thể truy vấn trạng thái vì DB gián đoạn | `503` hoặc `504` tùy tầng và hợp đồng | Mã yêu cầu ổn định và hướng tiếp tục đối soát |

Đây là **gợi ý thiết kế API**, không phải một ánh xạ HTTP duy nhất bắt buộc. Quan trọng là client **không hiểu một lỗi mạng hoặc `5xx` như bằng chứng thao tác chắc chắn chưa chạy**. Khi nhận timeout, client phải giữ nguyên request ID.

Nếu API trả `202` nhưng worker chưa chạy xong, endpoint tra cứu phải có ý nghĩa nhất quán và được bảo vệ phân quyền. Không để một operation của người dùng khác được đọc qua URL đoán được.

Một giao diện người dùng cũng nên hiển thị “Đang kiểm tra kết quả” khi chưa có kết luận, thay vì vừa hiện “Thất bại” vừa cho người dùng bấm lại bằng một mã mới. Với nghiệp vụ nhạy cảm, trạng thái kéo dài cần một đường hỗ trợ tra soát.

## 11. Điều kiện để đối soát đáng tin cậy sau failover

Đối soát thường được trình bày với một primary ổn định. Khi có sự cố mất máy chủ, định nghĩa “nguồn có thẩm quyền” cần được xem lại:

- **Commit bền trên một nút** không bảo đảm một replica bất đồng bộ đã nhận commit ấy.
- Nếu ứng dụng đã báo thành công trên primary cũ nhưng failover sang replica chưa bắt kịp, hàng `transfer_operations` và dữ liệu nghiệp vụ có thể cùng biến mất trên primary mới.
- Việc không tìm thấy request sau failover có thể là vấn đề **mất commit đã xác nhận**, không phải chỉ là “lần gửi đầu chưa đến”.
- Để cam kết không mất giao dịch đã ACK qua một kiểu failover cụ thể, cần chính sách replication/synchronous acknowledgment, cơ chế chọn primary và cấu hình durability phù hợp.
- Backup, point-in-time recovery, log độc lập và đối soát với hệ thống bên ngoài giúp ứng phó thảm họa nhưng không thay thế mọi bảo đảm đồng bộ thời gian thực.

Nếu hệ thống có hai primary có thể đồng thời nhận ghi mà không có cơ chế đồng thuận/độc quyền phù hợp, cùng một request ID có thể được chấp nhận hai lần trên hai nhánh khác nhau. Khóa unique **trên một máy** không tự chống trùng **trên nhiều primary phân tách**.

Vì vậy, khi tài liệu kiến trúc nói “retry idempotent”, phải ghi rõ **phạm vi idempotency**, nơi lưu khóa, kiểu failover được bảo vệ và thời hạn lưu trạng thái.

## 12. Quan sát, đối soát định kỳ và tiếp quản yêu cầu treo

Để biết hệ thống có thật sự hoạt động khi xảy ra lỗi mạng, cần đo **nghiệp vụ chưa xác định được**, không chỉ lỗi SQL.

| Chỉ số hoặc dữ kiện | Điều cần quan sát |
| --- | --- |
| Số request kết thúc ở trạng thái `UNKNOWN` | Có bao nhiêu kết quả ghi chưa thể xác nhận? |
| Tuổi của request `UNKNOWN/PROCESSING` | Có operation treo lâu hơn deadline nghiệp vụ không? |
| Số lần retry theo một `request_id` | Có vòng lặp hoặc client tạo áp lực quá mức? |
| Kết quả `APPLIED/REJECTED` sau đối soát | Tỷ lệ phục hồi tự động có tốt không? |
| Xung đột cùng key nhưng payload khác | Client có đang tái sử dụng mã sai không? |
| Lỗi mạng lúc commit và lỗi tra cứu primary | Sự cố xảy ra ở đoạn nào của đường ghi? |
| Độ trễ replication, failover và tính sẵn sàng của primary | Việc không thấy trạng thái có phải do nguồn đọc không đủ mới? |
| Outbox pending và consumer duplicate count | Sự kiện ngoài DB có được gửi và xử lý đúng sau retry không? |

Log nên ghi `request_id`, mã giao dịch, mã lỗi/SQLSTATE, mốc thời gian quan trọng và bước xử lý; tránh ghi thông tin bí mật, thông tin thẻ hoặc dữ liệu cá nhân không cần thiết. Traces có thể có span cho `submit`, `commit`, `reconcile` và `retry` để phân biệt lần thử thứ mấy.

Một job đối soát định kỳ có thể tìm operation trung gian quá hạn, lấy lease và truy vấn nguồn có thẩm quyền. Job cần **idempotent**, có giới hạn tác vụ đồng thời và chính sách dừng khi không thể phân biệt thành công với thất bại.

Hệ thống cũng cần một **đường xử lý thủ công** khi nguồn ngoài không cung cấp trạng thái đáng tin, dữ liệu đã bị mất sau failover hoặc các bất biến bị vi phạm. Đối soát không phải lúc nào cũng là một lệnh `SELECT` đủ để khôi phục câu trả lời.

## 13. Kiểm thử các cửa sổ lỗi một cách có chủ đích

Một bài kiểm thử chỉ xác nhận rằng `COMMIT` thành công khi không có sự cố sẽ bỏ sót phần khó nhất. Hãy xây các kịch bản với **cùng request ID** và kiểm tra kết quả cuối của nghiệp vụ:

| Thời điểm chèn lỗi | Kết quả có thể có | Điều cần chứng minh |
| --- | --- | --- |
| Trước khi request đến database | Không có giao dịch | Thử lại cùng ID có thể thực hiện đúng một lần. |
| Sau `INSERT transfer_operations` nhưng trước thay đổi số dư, rồi rollback | Không có hàng kết quả đã commit, không có thay đổi số dư | Không lưu vết thành công giả hoặc cập nhật nửa chừng. |
| Sau khi trừ A nhưng trước khi cộng B, rồi rollback | Toàn transaction rollback | Tổng tiền/số dư không bị lệch. |
| Sau khi commit thành công nhưng trước khi gửi ACK | Đã có kết quả cuối trên primary | Đối soát trả kết quả cũ; không trừ tiền lần hai. |
| Hai request cùng mã đến đồng thời | Một transaction có quyền ghi, request kia đợi hoặc nhận conflict | Không thực thi tác dụng phụ hai lần. |
| Cùng mã nhưng số tiền hoặc tài khoản khác | Xung đột payload | Không trả kết quả của một yêu cầu khác như thể đúng ý định mới. |
| Đọc từ replica chậm | Chưa thấy record mới | Không kết luận giao dịch thất bại dựa trên replica. |
| Lỗi trong lúc truy vấn đối soát | Chưa có kết luận | Trạng thái giữ `UNKNOWN`; không báo FAILED chắc chắn. |
| Mất ACK từ provider thanh toán | Provider có thể đã thu tiền | Tra cứu bằng mã idempotency trước khi thử thu tiền tiếp. |
| Worker outbox gửi xong rồi sập | Broker có thể nhận sự kiện, outbox chưa đánh dấu | Consumer khử trùng theo event ID. |
| Failover không đồng bộ làm mất commit đã ACK | Primary mới có thể thiếu cả dữ liệu và record | Phát hiện khoảng trống bảo đảm, kích hoạt quy trình khôi phục/tra soát. |

### Một bộ kiểm thử đồng thời có ý nghĩa

Giả sử tài khoản A có 1.000.000 đồng và B có 0 đồng. Gửi **cùng một yêu cầu chuyển 300.000 đồng** qua hai client song song, sau đó cho một client mất ACK:

1. Cả hai client sử dụng **cùng UUID và cùng payload**.
2. Cơ sở dữ liệu phải commit **một** bản ghi kết quả cho UUID đó.
3. Số dư cuối hợp lệ là A = **700.000**, B = **300.000**; không phải A = 400.000, B = 600.000.
4. Client mất ACK truy vấn trạng thái, thấy kết quả đã commit và trả lại cùng một mã giao dịch.
5. Gửi lại UUID này sau khi khởi động lại ứng dụng vẫn không tạo chuyển khoản mới.
6. Gửi cùng UUID với amount = 400.000 phải bị báo **xung đột**, không thực hiện tiền mới.

Để tái hiện trường hợp đang xử lý, dùng điểm đồng bộ trong kiểm thử để giữ transaction A mở trong khi B thử INSERT cùng khóa; xác minh B đợi/timeout phù hợp và không tạo kết quả trùng. Khi kiểm thử timeout, theo dõi tình huống **timeout của client không làm giao dịch database biến mất ngay lập tức**.

## 14. Các ngộ nhận thường gây lỗi nghiêm trọng

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Nhận `SQLException` là database chắc chắn không ghi.” | SQL có thể đã commit trước khi mất phản hồi. |
| “Gọi `rollback()` sau commit lỗi thì mọi thứ đã quay lại.” | Nếu commit đã hoàn tất, rollback phía client không thể đảo ngược nó. |
| “Không thấy request trong cache tức là chưa chạy.” | Cache có thể chưa cập nhật hoặc bị mất; cần nguồn bền vững. |
| “Replica trả 0 hàng nghĩa là primary chưa commit.” | Replica bất đồng bộ có thể chậm. |
| “Retry với UUID mới sẽ dễ theo dõi hơn.” | UUID mới có thể biến retry thành một thao tác nghiệp vụ mới. |
| “Có `UNIQUE(request_id)` là đủ dù lưu kết quả sau commit ở transaction khác.” | Phải ghi bằng chứng và tác dụng phụ trong cùng ranh giới atomicity, hoặc có protocol phục hồi phù hợp. |
| “`ON CONFLICT DO NOTHING` nghĩa là request lặp luôn có payload hợp lệ.” | Phải kiểm tra payload của yêu cầu đã tồn tại; cùng key khác tham số là lỗi. |
| “Không thấy hàng khi SELECT là chứng minh giao dịch trước đã rollback.” | Giao dịch cũ có thể còn chạy hoặc nguồn đọc chưa cập nhật. |
| “Đã có idempotency cho DB thì API thanh toán cũng đúng một lần.” | Hệ bên ngoài cần khóa và đối soát riêng theo hợp đồng của nó. |
| “Mọi trạng thái PROCESSING quá hạn đều có thể chạy lại.” | Tác dụng phụ ngoài DB có thể đã xảy ra; cần lease, idempotency và tra cứu kết quả. |
| “Một lần gửi sự kiện thành công chắc chắn consumer chỉ xử lý một lần.” | Broker/worker có thể giao trùng; consumer cần chống trùng. |
| “Async replica + unique key bảo đảm không mất commit sau failover.” | Unique key không thay thế cơ chế độ bền và đồng bộ dữ liệu giữa các nút. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Java gọi `connection.commit()` rồi nhận lỗi mất kết nối. Có được trả “chuyển tiền thất bại” và tạo một request ID mới để retry không?

**Không.** Commit có thể đã hoàn tất. Cần đối soát theo request ID ban đầu; nếu phải gửi lại thì dùng **cùng ID** với cơ chế ngăn trùng đáng tin cậy.

**Câu 2.** Sau lỗi trên, truy vấn trên replica trả không có hàng `transfer_operations`. Có thể kết luận transaction chưa commit không?

**Không.** Replica có thể trễ. Cần truy vấn primary hoặc đường đọc có bảo đảm đủ mới; ngay cả khi primary chưa thấy, giao dịch ban đầu có thể vẫn đang chạy.

**Câu 3.** Vì sao bản ghi thao tác phải cùng transaction với cập nhật số dư?

Vì nếu số dư commit nhưng bản ghi thao tác chưa được lưu, lần đối soát tiếp theo có thể tưởng chưa xử lý và thực hiện chuyển tiền thêm lần nữa.

**Câu 4.** Cùng request ID được gửi lại với số tiền khác thì nên làm gì?

**Từ chối xung đột.** Không thực hiện tiền mới, cũng không coi kết quả của yêu cầu cũ là xác nhận cho payload khác.

**Câu 5.** Nếu hai lần gửi cùng request ID đến cùng lúc, vì sao câu `INSERT ... ON CONFLICT DO NOTHING` trong một transaction có thể giúp?

Vì ràng buộc unique được kiểm tra ngay ở database và phối hợp các giao dịch cạnh tranh. Chỉ một transaction có thể tạo hàng cùng khóa; transaction còn lại phải nhận diện xung đột hoặc chờ rồi tra cứu kết quả đã lưu.

**Câu 6.** Một webhook thanh toán báo thành công nhưng ứng dụng đã nhận cùng sự kiện từ trước. Có nên cộng tiền thêm lần nữa?

**Không.** Webhook cần được nhận diện theo event/transaction ID và xử lý idempotent. Cùng một sự kiện có thể được giao lại.

**Câu 7.** Một transaction đã commit bền vững ở primary cũ, nhưng replica bất đồng bộ được thăng làm primary mới không chứa nó. Đây là lỗi gì?

Đó là khoảng trống của **bảo đảm dữ liệu qua failover**. Phải xem chính sách replication/ACK và thực hiện quy trình khôi phục, không kết luận một cách đơn giản rằng lần ghi đầu chưa từng xảy ra.

## Kết luận

**Kết quả ghi không rõ ràng không đồng nghĩa với thất bại.** Khi mất phản hồi quanh thời điểm ghi hoặc commit, ứng dụng phải phân biệt **thực tế ở hệ lưu trữ** với **điều client biết**, rồi đối soát bằng một request ID ổn định và nguồn dữ liệu có thẩm quyền.

Trong tầng persistence Java, một thiết kế đáng tin thường kết hợp: **khóa idempotency duy nhất**, **bản ghi kết quả được commit nguyên tử cùng nghiệp vụ**, **truy vấn đối soát phù hợp với replication**, **retry có giới hạn bằng cùng ID**, và **cơ chế riêng cho tác dụng phụ ở hệ thống bên ngoài**. Cần kiểm thử cả cửa sổ ACK bị mất, giao dịch đồng thời và failover để bảo đảm rằng một thao tác có thể được phục hồi mà không bị thực hiện sai hoặc lặp ngoài ý muốn.
