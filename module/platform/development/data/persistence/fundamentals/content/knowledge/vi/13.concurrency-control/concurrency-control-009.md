# Thống nhất thứ tự truy cập để giảm nguy cơ deadlock

Khi nhiều giao dịch cùng sửa dữ liệu, cơ sở dữ liệu thường dùng khóa để ngăn các thao tác xung đột làm hỏng tính nhất quán. Đôi khi hai giao dịch đều còn khả năng chạy nhưng mỗi bên lại đang chờ một tài nguyên do bên kia nắm giữ. Tình huống này gọi là **deadlock** (*bế tắc*): các giao dịch tạo thành một vòng chờ và không bên nào tự tiến lên được nếu hệ quản trị không can thiệp.

Một cách phòng ngừa quan trọng là quy định **thứ tự lấy khóa thống nhất** giữa mọi đường ghi dữ liệu. Ví dụ, khi chuyển tiền giữa hai tài khoản, luôn khóa tài khoản có mã nhỏ trước rồi đến tài khoản có mã lớn, bất kể hướng chuyển. Nếu mọi giao dịch tuân thủ thứ tự đó, chúng không thể tạo một vòng chờ *chỉ từ hai khóa tài khoản ấy*. Kỹ thuật không loại bỏ mọi dạng deadlock, vì còn khóa ngầm, ràng buộc, nhiều loại tài nguyên và các đường truy cập khác.

Bài học thuộc chương **Kiểm soát đồng thời** của **DATA_PERSISTENCE_FUNDAMENTALS** tập trung vào lý do thứ tự khóa quan trọng, cách thiết kế quy tắc chung, cách áp dụng ở tầng persistence Java, và cách kiểm chứng hiệu quả trong cơ sở dữ liệu thật. Mục tiêu là **giảm xác suất deadlock, giữ đúng nghiệp vụ và xử lý an toàn khi deadlock vẫn xảy ra**.

## 1. Vì sao deadlock xuất hiện?

Giả sử có hai tài khoản `10` và `20`. Mỗi giao dịch cần khóa cả hai tài khoản để cập nhật số dư:

```text
Giao dịch T1                          Giao dịch T2
---------------                      ---------------
Khóa tài khoản 10                    Khóa tài khoản 20
Yêu cầu khóa tài khoản 20            Yêu cầu khóa tài khoản 10
     |                                      |
     +---- chờ T2 nhả khóa 20              |
                 |                          |
                 +------ T2 chờ T1 nhả 10 --+

T1 giữ 10, chờ 20.
T2 giữ 20, chờ 10.
=> Có một chu trình chờ: T1 -> T2 -> T1.
```

Đây là **vòng chờ**, không chỉ là truy vấn chậm. Nếu T2 chỉ chờ T1 giải phóng một khóa còn T1 không chờ T2, đó là *blocking* thông thường; T1 có thể hoàn tất và T2 tiếp tục. Deadlock đòi hỏi một chu trình trong đồ thị chờ tài nguyên.

Nhiều hệ quản trị như PostgreSQL, MySQL/InnoDB và SQL Server có cơ chế phát hiện bế tắc và chọn một giao dịch làm nạn nhân. Giao dịch bị hủy hoặc được yêu cầu rollback để những giao dịch khác tiếp tục. Vì vậy deadlock thường biểu hiện bằng **một lỗi giao dịch** thay vì hai yêu cầu đứng im vĩnh viễn.

Một số điều kiện thường góp phần tạo deadlock:

- Các giao dịch cùng cần **nhiều khóa** hoặc nhiều tài nguyên.
- Mỗi giao dịch **giữ ít nhất một khóa trong khi xin khóa khác**.
- Thứ tự xin khóa khác nhau giữa các luồng xử lý.
- Các khóa không được giải phóng ngay và có khả năng tạo thành chu trình chờ.

Deadlock có thể xảy ra ngay cả ở mức cô lập `READ COMMITTED`. Hạ mức cô lập không thay thế việc thiết kế thứ tự truy cập và không bảo đảm loại bỏ deadlock.

## 2. Quy tắc thứ tự toàn cục phá vòng chờ như thế nào?

Đặt ra một **thứ tự tổng thể** cho mọi tài nguyên mà một nhóm giao dịch có thể cần. Với giao dịch chỉ khóa các hàng trong bảng `accounts`, quy tắc đơn giản là:

> Luôn lấy khóa tài khoản theo `account_id` tăng dần, bất kể tài khoản nào là nguồn hay đích.

Ví dụ:

| Yêu cầu nghiệp vụ | Thứ tự khóa dễ gây xung đột | Thứ tự khóa thống nhất |
| --- | --- | --- |
| Chuyển từ tài khoản 10 sang 20 | Khóa nguồn 10 → đích 20 | Khóa 10 → 20 |
| Chuyển từ tài khoản 20 sang 10 | Khóa nguồn 20 → đích 10 | **Khóa 10 → 20** |
| Cập nhật ba tài khoản 20, 5, 10 | Khóa theo thứ tự dữ liệu đầu vào | Khóa **5 → 10 → 20** |
| Cập nhật cùng một tài khoản | Có thể cố xin hai khóa hoặc xử lý lặp | Chỉ xét **một hàng**; kiểm tra nghiệp vụ tương ứng |

Vì sao quy tắc này hữu ích? Với tập khóa mà **mọi giao dịch chỉ xin theo chiều tăng**, một giao dịch đang giữ khóa `10` rồi chờ `20` sẽ không có giao dịch khác đang giữ `20` mà quay lại xin `10`. Vòng chờ chỉ do các khóa ấy gây ra không thể hình thành. Hình thức lập luận này áp dụng khi quy tắc được tuân thủ cho **toàn bộ** những khóa liên quan.

Khi có nhiều loại tài nguyên, có thể xây dựng thứ tự từ hai phần:

1. **Thứ tự loại tài nguyên:** chẳng hạn `Account` trước `Inventory` trước `Order` nếu đúng với toàn bộ workflow.
2. **Thứ tự trong cùng loại:** khóa hàng theo khóa định danh tăng dần, có quy tắc ổn định cho các trường hợp cùng khóa.

Quy tắc phải được thống nhất giữa các repository, background job, API, batch và các thao tác khác đụng cùng dữ liệu. Nếu một đường ghi còn lấy khóa theo thứ tự ngược thì bảo đảm phòng vòng chờ không còn đúng.

### Vì sao không chỉ gọi ORDER BY trong câu UPDATE?

Một câu `UPDATE` với điều kiện `WHERE account_id IN (10, 20)` không tự cam kết rằng hệ quản trị sẽ xin khóa theo thứ tự tăng dần. Kế hoạch thực thi, thứ tự index, cách quét hàng và cấu trúc câu lệnh có thể quyết định thứ tự thực tế. Nhiều hệ quản trị thậm chí không cho dùng `ORDER BY` trực tiếp với `UPDATE` theo cùng một cú pháp.

Ngay cả khi viết `SELECT ... ORDER BY account_id FOR UPDATE`, cần hiểu đặc tả và kế hoạch của hệ quản trị trước khi coi đó là hợp đồng về thứ tự lấy khóa; cách phối hợp sort và row locking có thể phụ thuộc vào DB và câu truy vấn. Với tập khóa nhỏ, phương án dễ kiểm chứng nhất là **sắp xếp danh sách ID trong ứng dụng, rồi lấy khóa từng hàng theo đúng thứ tự bằng các câu lệnh riêng**.

## 3. Thí nghiệm PostgreSQL: tạo deadlock với hai phiên

Ví dụ sử dụng PostgreSQL và một bảng riêng trên cơ sở dữ liệu thử nghiệm:

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance    NUMERIC(18, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (account_id, balance)
VALUES (10, 1000.00), (20, 1000.00);
```

Mở **hai phiên kết nối khác nhau** (A và B), tắt chế độ tự động commit của từng bước bằng cách mở transaction rõ ràng, rồi thực hiện theo lịch sau:

| Bước | Phiên A | Phiên B |
| --- | --- | --- |
| 1 | `BEGIN;` | |
| 2 | `SELECT account_id FROM accounts WHERE account_id = 10 FOR UPDATE;` → giữ khóa hàng 10 | |
| 3 | | `BEGIN;` |
| 4 | | `SELECT account_id FROM accounts WHERE account_id = 20 FOR UPDATE;` → giữ khóa hàng 20 |
| 5 | `SELECT account_id FROM accounts WHERE account_id = 20 FOR UPDATE;` → **chờ** | |
| 6 | | `SELECT account_id FROM accounts WHERE account_id = 10 FOR UPDATE;` → phát sinh **vòng chờ** |

Khi phát hiện vòng chờ, PostgreSQL sẽ hủy một trong hai giao dịch với lỗi `deadlock detected`, SQLSTATE `40P01`. Không thể bảo đảm phiên A hay B luôn là bên nhận lỗi: phụ thuộc vào thời điểm phát hiện và lịch chạy. Giao dịch lỗi cần `ROLLBACK`; giao dịch còn lại có thể được tiếp tục rồi `COMMIT` hoặc `ROLLBACK` theo mục tiêu thử nghiệm.

Vì bước 5 phải chờ, **không gửi liên tiếp cả hai tập lệnh trong một phiên duy nhất** rồi kỳ vọng tái hiện deadlock. Phải có hai kết nối hoạt động đồng thời và sắp lịch xen kẽ. Sau thử nghiệm, xác nhận không còn transaction mở hoặc khóa bị giữ ngoài ý muốn.

Đây là ví dụ về **row-level lock** do `FOR UPDATE` yêu cầu. Trong thực tế, deadlock cũng có thể liên quan đến khóa trên index, khóa kiểm tra khóa ngoại, cập nhật khóa unique, khóa phạm vi, khóa bảng hoặc những cơ chế nội bộ khác của DB.

## 4. Thay đổi thứ tự: giao dịch phải chờ, nhưng không tạo vòng từ hai hàng này

Giữ nguyên bảng `accounts` và đổi cả hai luồng theo cùng quy tắc:

```sql
BEGIN;

-- Bất kể hướng chuyển tiền, luôn khóa ID nhỏ trước.
SELECT account_id FROM accounts WHERE account_id = 10 FOR UPDATE;
SELECT account_id FROM accounts WHERE account_id = 20 FOR UPDATE;

-- Sau khi đã giữ đủ hai khóa, thực hiện nghiệp vụ.
-- COMMIT hoặc ROLLBACK khi xử lý xong.
COMMIT;
```

Nếu A đang giữ khóa hàng 10, B phải chờ ngay ở lần xin khóa đầu tiên. B chưa giữ khóa hàng 20, do đó A vẫn có thể khóa 20, hoàn tất công việc rồi commit. Sau đó B lấy khóa theo thứ tự 10 → 20 và tiếp tục.

Điều này chứng minh lợi ích của một thứ tự nhất quán **đối với hai hàng cụ thể**. Không có nghĩa mọi cuộc tranh chấp khóa đều biến mất: việc chờ vẫn tồn tại, và một hệ thống có nhiều tài nguyên hoặc khóa ngầm vẫn có thể gặp deadlock ở nơi khác.

## 5. Áp dụng trong Java/JDBC: chuyển tiền đúng thứ tự khóa

Trong hệ thống Java, có thể để service sở hữu transaction và quy định thứ tự truy cập ngay tại ranh giới persistence. Ví dụ dưới đây:

- Chuyển một số tiền dương từ tài khoản nguồn sang tài khoản đích khác.
- Khóa **cả hai tài khoản theo ID tăng dần** trước khi kiểm tra/cập nhật số dư.
- Trừ tiền có điều kiện để không âm số dư và cộng tiền trong **cùng một giao dịch**.
- Nếu PostgreSQL phát hiện deadlock (`40P01`), rollback rồi thử lại **toàn bộ giao dịch** trong giới hạn số lần.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class AccountTransferService {
    private static final int MAX_ATTEMPTS = 3;
    private final DataSource dataSource;

    public AccountTransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long sourceId, long targetId, BigDecimal amount)
            throws SQLException {
        if (sourceId == targetId) {
            throw new IllegalArgumentException("Hai tài khoản phải khác nhau");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }

        long firstId = Math.min(sourceId, targetId);
        long secondId = Math.max(sourceId, targetId);

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try (Connection connection = dataSource.getConnection()) {
                connection.setAutoCommit(false);
                try {
                    // Thứ tự khóa độc lập với chiều chuyển tiền.
                    lockAccount(connection, firstId);
                    lockAccount(connection, secondId);

                    debit(connection, sourceId, amount);
                    credit(connection, targetId, amount);

                    connection.commit();
                    return;
                } catch (SQLException | RuntimeException failure) {
                    boolean rollbackSucceeded = false;
                    try {
                        connection.rollback();
                        rollbackSucceeded = true;
                    } catch (SQLException rollbackError) {
                        failure.addSuppressed(rollbackError);
                    }

                    // PostgreSQL SQLSTATE 40P01: deadlock; chỉ retry
                    // sau khi rollback đã thành công.
                    if (rollbackSucceeded
                            && failure instanceof SQLException sqlError
                            && "40P01".equals(sqlError.getSQLState())
                            && attempt < MAX_ATTEMPTS) {
                        continue;
                    }
                    throw failure;
                }
            }
        }
        throw new IllegalStateException("Đã vượt quá số lần thử giao dịch");
    }

    private static void lockAccount(Connection connection, long id)
            throws SQLException {
        String sql = "SELECT account_id FROM accounts " +
                     "WHERE account_id = ? FOR UPDATE";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalArgumentException(
                        "Không tồn tại tài khoản " + id);
                }
            }
        }
    }

    private static void debit(Connection connection, long sourceId,
                              BigDecimal amount) throws SQLException {
        String sql = """
            UPDATE accounts
            SET balance = balance - ?
            WHERE account_id = ? AND balance >= ?
            """;
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, sourceId);
            ps.setBigDecimal(3, amount);
            if (ps.executeUpdate() != 1) {
                throw new IllegalStateException("Số dư không đủ");
            }
        }
    }

    private static void credit(Connection connection, long targetId,
                               BigDecimal amount) throws SQLException {
        String sql = """
            UPDATE accounts
            SET balance = balance + ?
            WHERE account_id = ?
            """;
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, targetId);
            if (ps.executeUpdate() != 1) {
                throw new IllegalStateException("Không tìm thấy tài khoản đích");
            }
        }
    }
}
```

Mẫu code này hướng đến Java 17+ (text block và pattern matching cho `instanceof`), PostgreSQL và schema ví dụ ở trên. Các điểm cần chú ý:

1. **Khóa theo khóa chính:** mỗi lần gọi `lockAccount` xin khóa đúng một hàng. Việc gọi hai lần theo thứ tự ID giúp quan sát rõ ranh giới khóa; cột `account_id` có primary key để tìm nhanh.
2. **Kiểm tra nghiệp vụ sau khi khóa:** nguồn có thể đủ tiền ở lần đọc ban đầu nhưng thiếu tiền khi đến lượt xử lý. Lệnh `UPDATE ... WHERE balance >= ?` vẫn bảo vệ số dư không âm trong cùng transaction. Giá trị số dư và số hàng cập nhật cần được xử lý đúng.
3. **Atomicity:** nếu trừ tiền thành công nhưng cộng tiền thất bại, transaction bị rollback và cả hai thay đổi đều bị hủy. `commit()` chỉ xuất hiện khi mọi bước đã thành công.
4. **Retry toàn transaction:** deadlock có thể xảy ra ở lúc lấy khóa hoặc lúc cập nhật. Mỗi lần retry phải mở transaction mới và chạy lại các thao tác kiểm tra, cập nhật; không lặp riêng câu SQL đang lỗi trên transaction cũ.
5. **Giới hạn lỗi có thể retry:** ví dụ chỉ nhận diện mã `40P01` của PostgreSQL và chỉ retry khi rollback thành công. Lỗi nghiệp vụ (thiếu tiền, không tồn tại tài khoản), lỗi ràng buộc khác hoặc mất kết nối cần chính sách riêng.
6. **Phạm vi sở hữu:** service chủ động mở connection và quyết định commit/rollback. Nếu transaction được Spring hoặc tầng gọi quản lý, repository phải tham gia transaction đó và không tự thay `autoCommit` hoặc tự `commit`.

Để minh họa ngắn gọn, code chưa thêm xác thực người dùng, kiểm tra hạn mức, loại tiền, làm tròn theo quy định tiền tệ, bản ghi sổ cái, khóa yêu cầu idempotency hoặc chính sách retry có backoff. Hệ thống tài chính thực tế phải bảo đảm các bất biến ấy. Đặc biệt, nếu kết nối mất ngay sau khi gửi `COMMIT`, ứng dụng có thể **không biết chắc** giao dịch đã thành công hay chưa; không được tự động chuyển lại tiền chỉ dựa trên một lỗi kết nối.

## 6. Khi có nhiều bảng hoặc khóa không hiển thị trực tiếp

Quy tắc khóa theo ID chỉ giải quyết được các khóa mà ta đã xét. Trên thực tế, một lệnh SQL có thể lấy thêm khóa do:

- **Khóa ngoại:** ghi bảng con có thể cần xác minh và/hoặc khóa liên quan ở bảng cha. Hai luồng cập nhật cha/con theo thứ tự khác nhau có thể tạo vòng chờ.
- **Unique index:** hai giao dịch ghi các giá trị có ràng buộc duy nhất có thể phải chờ giao dịch đang sở hữu mục index liên quan.
- **Trigger, cascade, stored procedure:** một lệnh tưởng như chỉ sửa một bảng có thể cập nhật nhiều bảng khác phía sau.
- **Truy vấn theo phạm vi:** các cơ chế gap/next-key lock của InnoDB hoặc range lock của những DB khác có thể mở rộng vùng khóa so với danh sách ID được thấy trong ứng dụng.
- **Nhiều nhóm đối tượng:** API thanh toán khóa `Account → Order` nhưng job đối soát lại khóa `Order → Account` thì vẫn có thể deadlock dù từng nhóm tự sắp ID tăng dần.

Vì thế, thiết kế thứ tự thường cần áp dụng cho **toàn bộ chuỗi tương tác ghi**, kể cả những bước bị ẩn sau ORM, cascade và trigger. Có thể lập bảng quyết định chung:

| Luồng nghiệp vụ | Các tài nguyên cần sửa | Thứ tự được thống nhất |
| --- | --- | --- |
| Chuyển tiền | Nhiều hàng `Account` | `Account` tăng dần theo `account_id` |
| Xác nhận đơn hàng, trừ tiền | `Account` và `Order` | `Account` trước, sau đó `Order` theo ID |
| Hoàn tiền đơn hàng | `Order` và `Account` | **Cũng `Account` trước**, sau đó `Order` |
| Job cập nhật hàng loạt | Nhiều `Account` | Loại trùng ID, sort tăng dần, khóa từng hàng theo thứ tự |

Thứ tự trong bảng chỉ là **ví dụ một quy ước**; cần kiểm tra ràng buộc và thao tác thật của ứng dụng trước khi chuẩn hóa. Không nên thay đổi thứ tự chỉ ở một endpoint rồi kết luận đã hết deadlock.

### Có nên khóa trước toàn bộ dữ liệu?

Khóa trước tập hàng xác định và nhỏ thường làm quy tắc rõ ràng hơn, nhưng **giữ nhiều khóa lâu hơn** cũng có thể tăng chờ đợi, giảm throughput hoặc gây starvation. Không nên mở transaction rồi gọi mạng, gửi email, chờ người dùng hoặc xử lý CPU kéo dài trong khi giữ khóa.

Khi bài toán chỉ cập nhật **một hàng**, một lệnh nguyên tử có điều kiện như `UPDATE accounts SET balance = balance - ? WHERE account_id = ? AND balance >= ?` có thể đơn giản hơn việc lấy khóa trước. Với nhiều hàng, cần cân nhắc tính đúng đắn, contention và thứ tự khóa; tránh thêm các bước khóa thừa mà không có lý do.

## 7. Thứ tự cố định không thay thế các biện pháp xử lý deadlock khác

| Biện pháp | Khi hữu ích | Giới hạn |
| --- | --- | --- |
| Thống nhất thứ tự khóa | Nhiều giao dịch cần cùng một tập loại tài nguyên | Cần mọi đường ghi tuân thủ; khóa ngầm vẫn có thể tạo vòng khác |
| Giao dịch ngắn, ít tài nguyên | Giảm khoảng thời gian giữ khóa | Không tự ngăn vòng chờ nếu hai luồng lấy khóa đảo ngược |
| Index phù hợp với `WHERE` | Tránh quét và khóa nhiều bản ghi không cần thiết ở một số engine | Kế hoạch/khóa phụ thuộc DB; index cũng có chi phí cập nhật |
| Retry có giới hạn | Xử lý các deadlock hiếm còn xảy ra | Không thay thế sửa nguyên nhân; có thể lặp tác động bên ngoài nếu thiếu idempotency |
| Lock timeout | Giới hạn thời gian chờ của request | Timeout không chứng minh có deadlock; không sửa thứ tự khóa |
| `NOWAIT` hoặc `SKIP LOCKED` | Tác vụ xếp hàng chấp nhận bỏ qua/để lại công việc đang bị khóa | Có thể làm thay đổi kết quả nghiệp vụ; không phù hợp với mọi thao tác chuyển tiền |

**Deadlock khác serialization failure.** Tùy hệ quản trị, deadlock và xung đột mức cô lập có mã lỗi khác nhau; chúng có thể đều cần retry toàn giao dịch, nhưng không nên gộp chúng vào một xử lý không phân loại. Ví dụ:

| Hệ quản trị | Dấu hiệu deadlock thường gặp |
| --- | --- |
| PostgreSQL | SQLSTATE `40P01` (`deadlock_detected`) |
| MySQL/InnoDB | Error `1213`, SQLSTATE thường là `40001` |
| SQL Server | Error `1205` (*deadlock victim*) |
| Oracle Database | `ORA-00060` (*deadlock detected*) |

Hãy dựa vào **mã lỗi của DB/driver đang chạy**, đồng thời xem transaction còn hợp lệ không và cần rollback ở phạm vi nào. Một lỗi chờ khóa hết thời gian, deadlock và kết nối bị ngắt có thể đòi hỏi ba cách phục hồi khác nhau.

## 8. Chẩn đoán deadlock thay vì chỉ tăng retry

Khi có nhiều lỗi `deadlock detected`, cần tìm **những giao dịch nào giữ và xin khóa**, cùng câu SQL dẫn đến vòng chờ.

Một quy trình điều tra hữu ích:

1. **Thu thập lỗi:** mã lỗi, transaction/request ID, loại thao tác, thời điểm và số lần thử lại; không ghi lộ số dư hoặc dữ liệu nhạy cảm vào log.
2. **Đọc mô tả vòng chờ từ DB:** ở PostgreSQL có thể xem thông tin deadlock trong log máy chủ khi được cấu hình phù hợp; SQL Server có deadlock graph; InnoDB cung cấp dữ liệu chẩn đoán deadlock.
3. **Xác định thứ tự khóa thực tế:** truy ngược các SQL statements trong từng transaction, kể cả thao tác từ ORM/trigger/foreign key.
4. **So sánh với quy ước:** có luồng nào khóa `Order` trước `Account`, hoặc lấy hai ID theo thứ tự đầu vào?
5. **Sửa đường truy cập:** thống nhất thứ tự, rút ngắn transaction hoặc tối ưu truy vấn/index sau khi biết nút thắt.
6. **Kiểm thử hai phiên và theo dõi:** tái hiện lịch xen kẽ gây lỗi, áp dụng sửa đổi, rồi kiểm tra cả kết quả nghiệp vụ, thời gian chờ và tần suất lỗi.

Trong PostgreSQL, để **quan sát phiên đang chờ khóa**, có thể dùng truy vấn:

```sql
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

Kết quả cho biết PID đang chờ và PID đang chặn tại thời điểm quan sát; nó không thay thế bản ghi deadlock đã được phát hiện và giải quyết. Với một deadlock ngắn, khi truy vấn giám sát chạy thì nạn nhân có thể đã bị hủy. Thời gian phát hiện, lỗi và thông tin log giúp giải thích diễn biến. Các quyền truy cập và cài đặt log cũng ảnh hưởng mức độ chi tiết có thể xem.

Về đo lường, nên theo dõi **deadlock/1000 giao dịch**, tỷ lệ retry thành công, p95/p99 latency, thời gian chờ khóa, thời lượng transaction và số hàng bị tác động. Nếu giảm deadlock nhưng tăng mạnh thời gian chờ hoặc thông lượng giảm, cần đánh giá lại phạm vi khóa.

## 9. Bài tập thực hành

### Bài tập 1: nhận diện vòng chờ

Ba transaction chạy đồng thời:

```text
T1: giữ khóa A, chờ khóa B
T2: giữ khóa B, chờ khóa C
T3: giữ khóa C, chờ khóa A
```

**Câu hỏi:** có deadlock không? Nếu đặt quy tắc chung `A → B → C`, T3 có được lấy C trước A không?

**Đáp án:** có chu trình `T1 → T2 → T3 → T1`. Theo quy tắc chung, giao dịch cần cả A và C phải xin A trước C; T3 không được lấy C trước A. Cần áp dụng cùng quy tắc cho mọi transaction có liên quan.

### Bài tập 2: tìm lỗi trong chuyển tiền

```java
// Hai lần gọi đồng thời: transfer(10, 20) và transfer(20, 10)
lockAccount(connection, sourceId);
lockAccount(connection, targetId);
```

**Câu hỏi:** đâu là vấn đề và sửa thế nào?  
**Đáp án:** hai lời gọi có thứ tự khóa đảo nhau. Tính `firstId = Math.min(sourceId, targetId)`, `secondId = Math.max(sourceId, targetId)`, rồi khóa `firstId` trước `secondId` trong cùng transaction.

### Bài tập 3: mở rộng sang hai bảng

API A xác nhận đơn hàng: khóa `Account 10` rồi `Order 50`. API B hoàn tiền: khóa `Order 50` rồi `Account 10`.

**Câu hỏi:** chỉ sort ID trong mỗi bảng đã đủ chưa?  
**Đáp án:** chưa. Hai API vẫn đảo **thứ tự loại tài nguyên**. Cần quy định cùng một thứ tự xuyên bảng, chẳng hạn `Account` trước `Order`, rồi kiểm tra các thao tác ORM, foreign key và trigger.

### Bài tập 4: chiến lược retry

Giao dịch nhận lỗi PostgreSQL `40P01` sau khi đã gửi email cho khách hàng nhưng trước khi commit.

**Câu hỏi:** có thể retry toàn bộ method một cách trực tiếp không?  
**Đáp án:** không an toàn vì email đã gửi không bị rollback và sẽ có nguy cơ gửi lặp. Nên thiết kế outbox/idempotency hoặc phát thông báo sau khi có kết quả commit được xác nhận.

### Checklist áp dụng

- Đã liệt kê những bảng, hàng và **khóa ngầm** mà luồng nghiệp vụ có thể truy cập chưa?
- Mọi đường ghi có tuân thủ cùng quy tắc **loại tài nguyên trước, ID trong loại sau** không?
- Thứ tự lấy khóa có được bảo đảm bằng cách gọi thực tế, hay chỉ dựa trên một giả định về `UPDATE`/query planner?
- Transaction có đủ ngắn và giữ tập khóa tối thiểu không? Có thao tác I/O ngoài DB trong lúc đang giữ khóa không?
- Khi gặp deadlock, ứng dụng có rollback, phân loại lỗi, retry giới hạn trên transaction mới và tránh lặp side effect không?
- Đã dùng lịch chạy hai phiên để xác minh không mất dữ liệu, không mất bất biến và đo tác động đến độ trễ chưa?

**Kết luận:** Thống nhất thứ tự truy cập tạo ra một quy tắc đơn giản có thể kiểm tra bằng code review và thí nghiệm đồng thời. Nó đặc biệt hiệu quả khi nhiều transaction phải khóa cùng một tập hàng, nhưng hiệu quả phụ thuộc vào việc mọi đường ghi tuân thủ quy tắc và việc hiểu những khóa thực tế do DB lấy. Thiết kế tốt kết hợp **thứ tự khóa nhất quán, giao dịch ngắn, thao tác nguyên tử và retry có kiểm soát**.
