# Tính nguyên tử, nhất quán, cô lập và bền vững trong ACID

Trong chương **Giao dịch** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, ta xem giao dịch (transaction) là ranh giới để một thao tác nghiệp vụ trên tầng lưu trữ dữ liệu có kết quả đáng tin cậy. Khi lập trình Java, việc gọi được câu lệnh SQL mới chỉ là bước đầu: ứng dụng còn phải xử lý mất kết nối, cập nhật đồng thời, vi phạm ràng buộc, lỗi khi ghi và sự cố máy chủ.

**ACID** là tên viết tắt của bốn tính chất cần hiểu khi thiết kế ranh giới persistence:

| Tính chất | Câu hỏi cốt lõi | Ý nghĩa |
| --- | --- | --- |
| **A — Atomicity (nguyên tử)** | Nếu một bước thất bại thì sao? | Các thay đổi thuộc một giao dịch được chấp nhận như một đơn vị hoặc không được chấp nhận. |
| **C — Consistency (nhất quán)** | Dữ liệu có còn hợp lệ sau khi hoàn tất? | Giao dịch đưa cơ sở dữ liệu từ trạng thái thỏa các bất biến đã định nghĩa sang trạng thái cũng thỏa các bất biến ấy. |
| **I — Isolation (cô lập)** | Hai giao dịch đồng thời nhìn thấy và ảnh hưởng nhau thế nào? | Hệ quản trị hạn chế các tương tác gây sai lệch giữa các giao dịch; mức bảo đảm phụ thuộc mức cô lập và cơ chế sử dụng. |
| **D — Durability (bền vững)** | Sau khi báo thành công, dữ liệu có tồn tại qua sự cố không? | Giao dịch đã commit được giữ theo bảo đảm độ bền của hệ quản trị và cấu hình lưu trữ. |

Một giao dịch ngân hàng chuyển 500.000 đồng từ tài khoản A sang B là ví dụ xuyên suốt. Ứng dụng cần trừ tiền ở A, cộng tiền ở B và ghi lịch sử chuyển khoản. Nếu ứng dụng dừng giữa chừng hoặc hai người dùng cùng chi tiêu trên một tài khoản, tính đúng đắn phải được giữ ở **toàn bộ giao dịch**, không chỉ ở từng câu lệnh.

## 1. Atomicity — hoặc tất cả, hoặc không có gì

Atomicity yêu cầu các thay đổi của **một giao dịch** được commit cùng nhau. Nếu giao dịch thất bại trước khi commit, những thay đổi chưa commit phải bị hủy; không được để lại trạng thái chỉ trừ tiền ở A mà chưa cộng tiền ở B.

Một giao dịch SQL thường có vòng đời:

```text
BEGIN
  ├─ Thao tác 1
  ├─ Thao tác 2
  └─ Thao tác 3
       ├─ Tất cả thành công → COMMIT
       └─ Có lỗi          → ROLLBACK
```

Ví dụ với PostgreSQL và đơn vị tiền được mô hình hóa bằng `NUMERIC(19,2)`:

```sql
CREATE TABLE accounts (
    id      BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL CHECK (balance >= 0)
);

CREATE TABLE transfer_history (
    request_id    UUID PRIMARY KEY,
    from_account  BIGINT NOT NULL REFERENCES accounts(id),
    to_account    BIGINT NOT NULL REFERENCES accounts(id),
    amount        NUMERIC(19, 2) NOT NULL CHECK (amount > 0),
    CHECK (from_account <> to_account)
);

BEGIN;

UPDATE accounts
SET balance = balance - 500000.00
WHERE id = 101 AND balance >= 500000.00;
-- Ứng dụng phải kiểm tra số hàng cập nhật = 1.
-- Nếu = 0: ROLLBACK và báo tài khoản không hợp lệ hoặc không đủ tiền.

UPDATE accounts
SET balance = balance + 500000.00
WHERE id = 202;
-- Nếu số hàng cập nhật khác 1: ROLLBACK.

INSERT INTO transfer_history
    (request_id, from_account, to_account, amount)
VALUES
    ('a1e9341c-7ae5-4e60-b9ce-5e9a8a394db7', 101, 202, 500000.00);

COMMIT;
```

Các câu lệnh trên **chỉ là mẫu quy trình**; để an toàn, ứng dụng phải kiểm tra kết quả hai lệnh `UPDATE` và chỉ thực hiện `COMMIT` sau khi mọi điều kiện được thỏa mãn. Nếu câu lệnh thứ hai hoặc `INSERT` thất bại, một lần `ROLLBACK` hủy cả việc trừ tiền trước đó. Với nhiều hệ quản trị, một lỗi SQL còn có thể làm giao dịch rơi vào trạng thái lỗi và buộc phải rollback trước khi tiếp tục.

**Atomicity không đồng nghĩa với việc mọi hệ thống bên ngoài cùng rollback.** Nếu trong giao dịch này chương trình đã gửi email, gọi API thanh toán hoặc ghi trực tiếp sang một dịch vụ khác, `ROLLBACK` của cơ sở dữ liệu không thu hồi được hành động ấy. Các luồng liên hệ hệ thống ngoài thường cần **transactional outbox**, thao tác **idempotent** (lặp lại không tạo tác dụng phụ mới), hoặc một quy trình bù trừ phù hợp.

**Savepoint** giúp khôi phục một phần thao tác *bên trong* giao dịch nhưng không làm thay đổi ranh giới commit cuối cùng:

```sql
BEGIN;
UPDATE accounts SET balance = balance + 100 WHERE id = 101;
SAVEPOINT optional_step;
-- Thao tác tùy chọn có thể thất bại.
ROLLBACK TO SAVEPOINT optional_step;
COMMIT;
```

Lệnh `ROLLBACK TO SAVEPOINT` chỉ hủy các thay đổi kể từ savepoint; thay đổi trước đó vẫn có thể được commit. Không nên nhầm cơ chế này với việc cam kết một phần giao dịch độc lập.

## 2. Consistency — giữ đúng các bất biến dữ liệu

Consistency nói về **điều kiện luôn phải đúng** trước và sau mỗi giao dịch thành công. Trong ví dụ chuyển khoản, một số bất biến có thể là:

- Số dư mỗi tài khoản không âm, nếu sản phẩm không cho phép thấu chi.
- Lịch sử chuyển tiền tham chiếu tới tài khoản tồn tại.
- Số tiền chuyển lớn hơn 0 và tài khoản gửi khác tài khoản nhận.
- Với chuyển tiền nội bộ không có phí, tổng số dư của hai tài khoản trước và sau bằng nhau.

Cơ sở dữ liệu có thể bảo vệ nhiều quy tắc bằng `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, `CHECK` hoặc trigger. Những ràng buộc này đặc biệt có giá trị vì chúng được áp dụng cho mọi đường ghi dữ liệu, kể cả khi nhiều ứng dụng cùng truy cập.

Tuy nhiên, không phải mọi bất biến nghiệp vụ đều có thể biểu diễn bằng `CHECK` trên một hàng. Ví dụ: “mỗi lớp học có tối đa 30 chỗ”, “một bác sĩ luôn trực” hoặc “tổng hạn mức của nhóm tài khoản không vượt ngân sách” thường liên quan nhiều hàng. Ứng dụng và cơ sở dữ liệu cần phối hợp qua cấu trúc dữ liệu, truy vấn điều kiện, khóa hoặc mức cô lập đủ mạnh.

**Tính nguyên tử không tự bảo đảm tính nhất quán.** Một giao dịch trừ 500.000 đồng ở A nhưng do lỗi lập trình lại cộng 50.000 đồng ở B vẫn có thể commit nguyên tử: nó hoàn tất cả hai lệnh nhưng vi phạm quy tắc bảo toàn tiền. Ngược lại, một `CHECK (balance >= 0)` ngăn số dư âm, nhưng không thay thế kiểm tra các quy tắc liên quan đến nhiều hàng.

Sơ đồ trách nhiệm:

```text
Quy tắc nghiệp vụ
    ├─ Cấu trúc và ràng buộc CSDL: ngăn trạng thái bất hợp lệ có thể mô tả được
    ├─ Logic ứng dụng: xác định thao tác nào được phép
    └─ Cơ chế đồng thời: bảo đảm các kiểm tra còn đúng lúc ghi/commit
                         ↓
                  Trạng thái hợp lệ
```

Chữ **C trong ACID** nói về bất biến của dữ liệu giao dịch; nó khác khái niệm “consistency” trong định lý **CAP**, vốn liên quan tới quan sát nhất quán giữa các nút của một hệ phân tán khi có phân hoạch mạng.

## 3. Isolation — điều gì xảy ra khi các giao dịch chồng lấn?

Trên hệ thống thực, hai phiên làm việc có thể cùng đọc và ghi một tập dữ liệu. Nếu mỗi phiên đọc số dư 1.000.000 đồng rồi tự tính số dư mới, hai lần rút 300.000 và 500.000 đồng có thể dẫn đến kết quả sai:

| Thời điểm | Giao dịch T1 | Giao dịch T2 |
| --- | --- | --- |
| 1 | Đọc số dư = 1.000.000 | |
| 2 | | Đọc số dư = 1.000.000 |
| 3 | Ghi số dư = 700.000 | |
| 4 | | Ghi số dư = 500.000 |
| 5 | Commit | Commit |

Số dư đúng phải là **200.000**, nhưng lần ghi cuối đã ghi đè kết quả của giao dịch trước. Đây là một dạng **lost update** (mất cập nhật). Lịch sử thực tế tùy mức cô lập, kiểu `UPDATE` và cơ chế kiểm tra xung đột của hệ quản trị; ví dụ cho thấy rủi ro của cách “đọc → tính trong ứng dụng → ghi đè”.

Một cách giảm rủi ro cho phép trừ tiền là thực hiện **thay đổi có điều kiện ngay trong SQL**, để cơ sở dữ liệu kiểm tra và cập nhật cùng lúc:

```sql
UPDATE accounts
SET balance = balance - 300000.00
WHERE id = 101 AND balance >= 300000.00;
-- Thành công chỉ khi số hàng được cập nhật = 1.
```

Với việc cập nhật trực tiếp cột đang lưu trữ, hàng bị ghi thường được khóa trong thời gian giao dịch. Kỹ thuật này tránh kiểu ghi đè một giá trị đã đọc cũ trong ví dụ trên. Trường hợp nhiều hàng hoặc nhiều quy tắc vẫn cần thiết kế đồng thời riêng.

### Các hiện tượng bất thường cần phân biệt

| Hiện tượng | Mô tả ngắn | Ví dụ |
| --- | --- | --- |
| **Dirty read** | Đọc thay đổi chưa commit của giao dịch khác. | Thấy số dư vừa cộng nhưng giao dịch kia sau đó rollback. |
| **Non-repeatable read** | Đọc lại cùng một hàng trong một giao dịch nhưng nhận giá trị mới do giao dịch khác commit. | Hai lần xem số dư cho hai kết quả. |
| **Phantom read** | Lặp lại truy vấn theo điều kiện, số hàng khớp thay đổi do giao dịch khác commit. | Đếm đơn hàng chưa xử lý lần sau nhiều hơn lần trước. |
| **Lost update** | Một lần ghi làm mất thay đổi hợp lệ của lần ghi khác. | Hai phiên cùng sửa số dư dựa trên giá trị đọc cũ. |
| **Write skew** | Hai giao dịch cập nhật các hàng khác nhau dựa trên một điều kiện chung, khiến điều kiện sai sau khi cả hai commit. | Hai bác sĩ đều xin nghỉ vì mỗi người nhìn thấy người kia còn trực. |

**Write skew** đáng chú ý vì ngay cả cơ chế đọc ảnh chụp nhất quán (*snapshot isolation*) vẫn có thể gặp hiện tượng này. Chẳng hạn T1 và T2 đều kiểm tra còn hai bác sĩ đang trực; T1 cho bác sĩ A nghỉ, T2 cho bác sĩ B nghỉ. Vì chúng cập nhật hai hàng khác nhau, một số hệ thống ở mức cô lập thấp hơn serializable có thể cho cả hai commit, để lại không ai trực.

### Các mức cô lập

SQL định nghĩa bốn mức cô lập thường gặp; cách hiện thực và các hiện tượng được ngăn chặn có khác nhau giữa các hệ quản trị:

| Mức cô lập | Ý nghĩa thực hành | Điều cần lưu ý |
| --- | --- | --- |
| `READ UNCOMMITTED` | Mức yêu cầu cô lập yếu nhất. | Theo mô hình chuẩn, có thể thấy dữ liệu chưa commit; một số CSDL không thực sự cho phép dirty read. |
| `READ COMMITTED` | Chỉ đọc dữ liệu đã commit. | Các lần đọc có thể thấy trạng thái khác nhau; vẫn phải chống cập nhật mất và sai lệch nghiệp vụ tùy cách viết truy vấn. |
| `REPEATABLE READ` | Giữ tính ổn định khi đọc lại hàng theo mô hình chuẩn. | Quy tắc phantom và write skew phụ thuộc cơ chế triển khai; không thể mặc định tương đương serializable. |
| `SERIALIZABLE` | Kết quả các giao dịch thành công tương đương một thứ tự thực thi tuần tự nào đó. | Có thể gây chờ khóa hoặc từ chối một giao dịch để tránh lịch sử không hợp lệ; ứng dụng phải xử lý retry. |

Theo cách mô tả mức cô lập trong chuẩn SQL, `REPEATABLE READ` vẫn có thể xuất hiện phantom. **Riêng PostgreSQL**, `REPEATABLE READ` dựa trên snapshot và tránh được kiểu phantom thông thường, nhưng vẫn có thể xảy ra write skew; `SERIALIZABLE` bổ sung kiểm tra để ngăn lịch sử không thể tuần tự hóa. PostgreSQL cũng xử lý `READ UNCOMMITTED` như `READ COMMITTED`. Các hệ quản trị khác có hành vi và cấu hình mặc định khác nhau; luôn kiểm tra tài liệu của phiên bản đang sử dụng.

Trong SQL có thể đặt mức cô lập cho giao dịch (cú pháp ví dụ PostgreSQL):

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Đọc dữ liệu, kiểm tra điều kiện nghiệp vụ, cập nhật dữ liệu.

COMMIT;
```

Một giao dịch serializable có thể bị từ chối khi phát hiện xung đột. Ứng dụng cần **thực hiện lại toàn bộ giao dịch** từ bước đọc điều kiện, thay vì chỉ lặp lại lệnh SQL cuối cùng. Retry phải có giới hạn, có độ trễ hợp lý và bảo đảm các hiệu ứng bên ngoài không bị lặp ngoài ý muốn.

### Ba kỹ thuật kiểm soát đồng thời phổ biến

**1. Khóa bi quan (pessimistic locking).** Đọc và khóa các hàng sẽ sửa trước khi quyết định:

```sql
BEGIN;
SELECT id, balance
FROM accounts
WHERE id = 101
FOR UPDATE;
-- Kiểm tra điều kiện và cập nhật trong cùng giao dịch.
COMMIT;
```

`SELECT ... FOR UPDATE` thường khiến giao dịch khác muốn cập nhật cùng hàng phải chờ. Việc khóa nhiều hàng cần thứ tự nhất quán để giảm nguy cơ deadlock. Đừng giữ giao dịch mở trong lúc chờ lời gọi HTTP hoặc thao tác người dùng.

**2. Khóa lạc quan (optimistic locking).** Tăng cột phiên bản mỗi khi sửa, và chỉ ghi nếu phiên bản vẫn như lúc đọc:

```sql
UPDATE documents
SET content = ?, version = version + 1
WHERE id = ? AND version = ?;
-- Nếu cập nhật 0 hàng: dữ liệu đã đổi, tải lại rồi quyết định thử tiếp.
```

Đây là kỹ thuật phù hợp với trường hợp ít xung đột và có thể yêu cầu người dùng giải quyết sửa đổi đồng thời; nó không thay thế các bất biến xuyên nhiều hàng.

**3. Ràng buộc và cập nhật có điều kiện.** Dùng `UNIQUE`, `FOREIGN KEY`, `CHECK`, `UPDATE ... WHERE ...` và số hàng bị ảnh hưởng để đưa phép kiểm tra vào CSDL. Với quy tắc tổng hợp nhiều hàng, có thể cần khóa hàng đại diện, thiết kế lại schema hoặc dùng mức `SERIALIZABLE`.

Lựa chọn mức cô lập là một **quyết định theo bất biến cần bảo vệ**. Tăng tất cả giao dịch lên `SERIALIZABLE` không tự sửa lỗi logic ứng dụng; dùng mức quá yếu mà không thiết kế khóa/ràng buộc cũng có thể gây sai lệch khó phát hiện.

## 4. Durability — commit thành công rồi thì sao?

Durability nghĩa là sau khi hệ quản trị **xác nhận commit thành công**, các thay đổi phải tồn tại qua những kiểu sự cố mà hệ quản trị và cấu hình đã cam kết chịu được, chẳng hạn tiến trình cơ sở dữ liệu đột ngột dừng và khởi động lại.

Các CSDL quan hệ thường sử dụng **write-ahead log (WAL)** hoặc cơ chế tương đương: ghi thông tin phục hồi cần thiết vào log bền vững trước khi xác nhận commit, rồi có thể ghi dữ liệu trang ra thiết bị theo lịch khác. Khi khởi động lại, hệ thống dựa trên log để phục hồi giao dịch đã commit và loại bỏ thay đổi chưa commit. Chi tiết đồng bộ xuống thiết bị (`fsync`, chế độ commit, pin lưu trữ và bộ điều khiển đĩa) ảnh hưởng trực tiếp tới bảo đảm thực tế.

Hãy phân biệt các mốc:

```text
Ứng dụng gửi COMMIT
       ↓
CSDL hoàn tất cơ chế commit theo cấu hình
       ↓
CSDL trả kết quả thành công
       ↓
Ứng dụng ghi nhận nghiệp vụ hoàn tất
```

**Sự cố mạng ở ranh giới commit có thể tạo kết quả không xác định đối với ứng dụng.** Ví dụ máy chủ đã commit nhưng mất kết nối trước khi client nhận được phản hồi. Client không được mặc định “chưa lưu” rồi chuyển tiền thêm lần nữa. Một `request_id` duy nhất được lưu cùng giao dịch cho phép tra cứu kết quả trước khi thử lại.

Durability **không đồng nghĩa** với “không bao giờ mất dữ liệu trong bất kỳ thảm họa nào”:

- **WAL/redo log** bảo vệ việc phục hồi từ một số lỗi tiến trình hoặc máy chủ theo cấu hình.
- **Replica** tăng khả năng sẵn sàng, nhưng bản sao **bất đồng bộ** có thể chưa nhận được commit cuối khi chuyển đổi máy chủ.
- **Sao lưu và phục hồi** bảo vệ trước xóa nhầm, hỏng dữ liệu diện rộng hoặc mất cả cụm lưu trữ; cần kiểm tra restore định kỳ và đặt mục tiêu RPO/RTO phù hợp.
- **Thiết lập độ bền** như chế độ ghi đồng bộ, xác nhận commit và chất lượng phần cứng quyết định phạm vi rủi ro thực tế.

Nếu dịch vụ chỉ xác nhận giao dịch sau khi nhiều nút lưu bền thì khả năng mất commit khi failover khác với trường hợp chỉ xác nhận trên nút chính. Cần đọc rõ hợp đồng độ bền của sản phẩm và cấu hình vận hành, không suy ra từ từ “ACID” rằng mọi replica hay bản backup đều có dữ liệu mới nhất.

## 5. Kết hợp ACID trong ranh giới persistence của Java

Với JDBC, mặc định kết nối thường ở chế độ `autoCommit = true`: mỗi câu lệnh tự tạo ranh giới commit riêng. Nếu nghiệp vụ cần nhiều lệnh cùng thành công, phải mở giao dịch bằng `setAutoCommit(false)` và commit sau khi mọi bước hợp lệ.

Ví dụ dưới đây dùng schema ở phần Atomicity. Giá trị tiền dùng `BigDecimal`; định danh `requestId` là khóa duy nhất để phát hiện yêu cầu lặp lại:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long from, long to, BigDecimal amount, UUID requestId)
            throws SQLException {
        if (amount == null || amount.signum() <= 0 || from == to || requestId == null) {
            throw new IllegalArgumentException("Thong tin chuyen tien khong hop le");
        }

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                try (PreparedStatement debit = c.prepareStatement(
                        "UPDATE accounts SET balance = balance - ? " +
                        "WHERE id = ? AND balance >= ?")) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, from);
                    debit.setBigDecimal(3, amount);
                    if (debit.executeUpdate() != 1) {
                        throw new IllegalStateException("Tai khoan gui khong du tien");
                    }
                }

                try (PreparedStatement credit = c.prepareStatement(
                        "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, to);
                    if (credit.executeUpdate() != 1) {
                        throw new IllegalStateException("Tai khoan nhan khong ton tai");
                    }
                }

                try (PreparedStatement log = c.prepareStatement(
                        "INSERT INTO transfer_history " +
                        "(request_id, from_account, to_account, amount) " +
                        "VALUES (?, ?, ?, ?)")) {
                    log.setObject(1, requestId);
                    log.setLong(2, from);
                    log.setLong(3, to);
                    log.setBigDecimal(4, amount);
                    log.executeUpdate();
                }

                c.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

Đoạn mã minh họa cách đặt **hai cập nhật và ghi lịch sử trong cùng một transaction**. Trước khi áp dụng cho hệ thống thật, cần thêm xác thực quyền chuyển tiền, kiểm tra hạn mức, quy tắc làm tròn tiền, kiểm soát thời gian chờ, giám sát, phân loại lỗi nghiệp vụ và xử lý idempotency hoàn chỉnh.

Một số chi tiết triển khai quan trọng:

1. **Lệnh `UPDATE` có điều kiện** ngăn ghi số dư âm. Kiểm tra `executeUpdate() == 1` quan trọng vì SQL có thể chạy thành công nhưng cập nhật 0 hàng.
2. **Ràng buộc trong CSDL** bắt lỗi không hợp lệ kể cả khi lập trình viên quên một bước kiểm tra ở Java.
3. **Rollback trong khối `catch`** làm sạch thay đổi chưa commit khi gặp lỗi. Nếu commit bị mất phản hồi, rollback được gọi ở phía client không đủ chứng minh rằng giao dịch chưa commit; phải đối chiếu `requestId`.
4. **Khóa hàng do các cập nhật tạo ra** có thể khiến hai lượt chuyển khoản ngược chiều deadlock. Hệ thống cần thiết kế thứ tự khóa ổn định và retry phù hợp với lỗi xung đột.
5. **Lịch sử có khóa duy nhất `request_id`** giúp nhận ra yêu cầu trùng. Khi bị từ chối vì trùng khóa, phải đọc giao dịch đã lưu và so khớp tham số, thay vì coi mọi lỗi trùng là thành công.

Trong ứng dụng Spring, `@Transactional` có thể quản lý ranh giới này ở lớp service khi gọi qua cơ chế proxy phù hợp. Cần nhớ mặc định của Spring thường rollback với `RuntimeException` và `Error`; ngoại lệ checked không mặc định dẫn đến rollback nếu không cấu hình `rollbackFor` hoặc quy tắc tương đương. Gọi nội bộ một phương thức `@Transactional` trong cùng đối tượng cũng có thể không đi qua proxy. Hãy kiểm tra đúng cách quản lý transaction của framework và không trộn các giao dịch cục bộ độc lập mà tưởng chúng là một.

### Khi giao dịch phải phát sinh sự kiện

Giả sử sau khi chuyển tiền, ứng dụng cần phát `TransferCompleted` tới message broker. Nếu commit xong rồi ứng dụng sập trước khi gửi sự kiện, bản ghi chuyển tiền đã có nhưng hệ khác không nhận thông báo. Nếu gửi thông báo trước commit thì bên nhận có thể thấy giao dịch thực tế bị rollback.

Mẫu **transactional outbox** giải bài toán về *sự kiện bị bỏ sót*:

```text
Transaction tại CSDL chính
  ├─ Cập nhật số dư
  ├─ Ghi lịch sử chuyển tiền
  └─ INSERT outbox_event(request_id, type, payload)
               ↓ COMMIT
Worker đọc outbox → gửi tới broker → đánh dấu đã gửi
               ↓
Consumer xử lý idempotent theo event_id
```

Outbox và dữ liệu nghiệp vụ được lưu nguyên tử cùng nhau. Worker có thể gửi lặp nếu sập sau khi gửi mà trước khi đánh dấu, nên phía nhận phải xử lý trùng. Mẫu này không biến hai hệ thống thành một giao dịch ACID toàn cục; nó kết hợp giao dịch cục bộ với khả năng gửi lại đáng tin cậy.

## 6. Diễn giải các tình huống lỗi bằng ACID

| Tình huống | Tính chất liên quan | Cách xử lý kỳ vọng |
| --- | --- | --- |
| Lệnh trừ tiền thành công, lệnh cộng tiền lỗi trước commit | Atomicity | Rollback toàn bộ, không để lại số dư bị trừ đơn lẻ. |
| Chuyển tiền vượt số dư và vi phạm `CHECK` hoặc cập nhật có điều kiện | Consistency | Chặn trạng thái không hợp lệ; trả lỗi nghiệp vụ thích hợp. |
| Hai người cùng rút trên một tài khoản | Isolation | Dùng cập nhật có điều kiện, khóa hoặc phiên bản để tránh ghi đè và kiểm tra sai. |
| Hai bác sĩ đồng thời xin nghỉ dù mỗi người thấy người kia trực | Isolation + Consistency | Bảo vệ bất biến nhiều hàng bằng thiết kế khóa/serializable hoặc mô hình ràng buộc thích hợp. |
| CSDL sập sau khi trả COMMIT thành công | Durability | Phục hồi giao dịch đã commit theo bảo đảm lưu trữ và cấu hình. |
| Kết nối đứt lúc COMMIT, client không nhận phản hồi | Durability + idempotency | Truy vấn bằng mã yêu cầu duy nhất trước khi quyết định retry. |
| Commit thành công nhưng ứng dụng sập trước khi gửi sự kiện | Atomicity giới hạn trong CSDL | Ghi outbox cùng transaction, worker gửi lại, consumer xử lý trùng. |
| Chuyển sang replica bất đồng bộ ngay sau sự cố nút chính | Durability ở cấp hệ thống | Đánh giá độ trễ sao chép, cơ chế failover, RPO và chiến lược khôi phục. |

## 7. Quy tắc thiết kế và kiểm tra giao dịch

Khi xây persistence cho một use case Java, hãy bắt đầu bằng câu hỏi: “**Những thay đổi nào buộc phải cùng thành công?**” Sau đó:

1. Định nghĩa **bất biến** nghiệp vụ cụ thể, gồm những quy tắc trên một hàng và trên nhiều hàng.
2. Chọn ranh giới transaction bao quanh tất cả các thay đổi dữ liệu bắt buộc đi cùng nhau; giữ transaction ngắn.
3. Đưa ràng buộc dữ liệu quan trọng xuống CSDL; dùng SQL cập nhật có điều kiện khi hợp lý.
4. Xác định các thao tác có thể **đồng thời**, những giá trị đọc cần bảo vệ và mức cô lập/khóa cần thiết.
5. Kiểm tra số hàng cập nhật, ngoại lệ SQL, deadline/timeout và lỗi commit không rõ kết quả.
6. Chuẩn bị mã yêu cầu duy nhất và retry có kiểm soát cho các luồng có thể được gọi lại.
7. Tách việc gọi dịch vụ ngoài khỏi transaction dài; dùng outbox hoặc cơ chế phối hợp phù hợp khi cần.
8. Xác nhận độ bền thực tế qua cấu hình commit, giám sát lưu trữ, backup, restore và cơ chế replication.

Có thể kiểm tra một thiết kế bằng bốn câu hỏi cùng một kịch bản: **Nếu lỗi xảy ra giữa hai lệnh, dữ liệu còn đúng không (A)? Nếu cả hai lệnh chạy xong nhưng công thức nghiệp vụ sai, ai phát hiện (C)? Nếu hai người làm cùng lúc, kết quả nào được phép (I)? Nếu đã báo thành công rồi máy chủ sập, lấy lại dữ liệu từ đâu (D)?**

ACID là nền tảng để hiểu giao dịch, nhưng độ tin cậy của một hệ thống persistence còn đến từ cách Java xác định ranh giới nghiệp vụ, dùng ràng buộc và mức cô lập đúng, xử lý lỗi rõ ràng, triển khai sao lưu và kết nối các hệ thống ngoài an toàn. Bốn tính chất này phải được xét **cùng nhau** khi thiết kế một luồng ghi dữ liệu quan trọng.
