# Thiết kế thứ tự cập nhật để giảm xung đột khóa trong JDBC

Khi nhiều giao dịch cùng sửa dữ liệu, hiệu năng và tính đúng đắn phụ thuộc không chỉ vào câu lệnh `UPDATE` mà còn vào **thứ tự các bản ghi được đọc có khóa và được cập nhật**. Hai giao dịch tác động cùng một tập bản ghi nhưng theo thứ tự trái ngược có thể chờ nhau theo vòng, dẫn đến *deadlock*. Ngay cả khi cơ sở dữ liệu phát hiện deadlock và hủy một giao dịch để phá vòng chờ, ứng dụng vẫn phải chịu chi phí thực thi lại, tăng độ trễ và có thể ảnh hưởng đến trải nghiệm người dùng.

Trong **JDBC**, ứng dụng có thể chủ động sắp xếp khóa bản ghi trước khi lấy khóa và cập nhật chúng trong **cùng một `Connection` và transaction**. Bài thuộc chương **Cô lập và khóa**, tập trung vào cách thiết kế thứ tự cập nhật nhất quán, cách thực hiện qua `DataSource`, `PreparedStatement`, `ResultSet` và các API transaction chuẩn, cũng như giới hạn cần kiểm chứng trên hệ quản trị cơ sở dữ liệu (*DBMS*) và JDBC driver thực tế.

Sau bài học, bạn có thể:

- Giải thích vì sao hai giao dịch cập nhật cùng hai hàng theo thứ tự ngược nhau dễ bị deadlock.
- Xác định một thứ tự khóa **chung, ổn định và xác định được**, ví dụ theo khóa chính tăng dần.
- Viết phương thức JDBC lấy khóa và cập nhật theo thứ tự đó, đồng thời bảo đảm `commit`/`rollback` đúng ranh giới.
- Phân biệt giảm deadlock với giảm thời gian chờ khóa và tăng thông lượng.
- Nhận biết các giới hạn liên quan isolation level, `SELECT ... FOR UPDATE`, index, batch, foreign key và retry giao dịch.

## 1. Xung đột khóa và deadlock phát sinh như thế nào?

Giả sử bảng tài khoản có hai hàng `account_id = 10` và `account_id = 20`. Hai giao dịch chuyển tiền đồng thời:

- Giao dịch **T1** chuyển từ tài khoản `10` sang `20`.
- Giao dịch **T2** chuyển từ tài khoản `20` sang `10`.

Một hiện thực ngây thơ có thể cập nhật tài khoản nguồn trước, sau đó cập nhật tài khoản đích:

```text
Thời điểm    T1: chuyển 10 -> 20          T2: chuyển 20 -> 10
---------    --------------------------  --------------------------
t1           Khóa / sửa hàng 10          —
t2           —                           Khóa / sửa hàng 20
t3           Muốn khóa hàng 20: CHỜ      —
t4           —                           Muốn khóa hàng 10: CHỜ

             T1 đợi T2                   T2 đợi T1
                        → DEADLOCK
```

Vòng chờ có thể biểu diễn như sau:

```mermaid
flowchart LR
    T1[Giao dịch T1] -->|chờ khóa hàng 20| T2[Giao dịch T2]
    T2 -->|chờ khóa hàng 10| T1
```

DBMS thường có cơ chế phát hiện deadlock và chọn một giao dịch làm *victim* để hủy hoặc rollback. Tùy hệ quản trị, thời điểm phát hiện, loại lỗi và phạm vi rollback có thể khác nhau. Trong Java, thao tác có thể ném `SQLException` với SQLState hay mã lỗi riêng. Việc DBMS có thể tự phát hiện deadlock **không phải lý do để chủ động tạo ra vòng chờ**.

### Ba hiện tượng cần phân biệt

| Hiện tượng | Bản chất | Thứ tự cập nhật giúp được gì? |
| --- | --- | --- |
| **Lock contention** (tranh chấp khóa) | Nhiều giao dịch cần cùng một tài nguyên | Sắp xếp thứ tự có thể giảm một số kiểu chờ nhưng không loại bỏ việc tranh chấp |
| **Deadlock** | Các giao dịch chờ nhau thành vòng, không bên nào tự tiến tiếp | Thứ tự lấy khóa thống nhất có thể loại bỏ vòng chờ trong một tập khóa đã biết |
| **Lock timeout** | Chờ khóa vượt ngưỡng hệ thống cho phép | Có thể vẫn xảy ra khi mọi giao dịch lấy khóa đúng thứ tự nếu một bên giữ khóa quá lâu |

Một giao dịch giữ hàng `10` suốt hai phút vẫn có thể chặn giao dịch khác hai phút dù không hề có deadlock. Vì vậy, thứ tự khóa là một công cụ trong thiết kế giao dịch, không thay thế tối ưu truy vấn, index và thời gian giữ transaction.

## 2. Nguyên tắc cốt lõi: cùng tài nguyên, cùng thứ tự

Với một thao tác cần khóa nhiều hàng, hãy định nghĩa **thứ tự tổng quát** (*total order*) trên các tài nguyên có thể tranh chấp và buộc tất cả luồng code tuân thủ. Ví dụ, dùng `account_id` tăng dần:

```text
T1: chuyển 10 -> 20     lấy khóa 10, sau đó 20
T2: chuyển 20 -> 10     lấy khóa 10, sau đó 20

T1 giữ 10 -> T2 chờ 10 -> T1 lấy 20 -> T1 commit
                                   -> T2 lấy 10, rồi 20 -> T2 commit
```

T2 có thể phải **chờ** khóa 10, nhưng giữa hai giao dịch đang chỉ truy cập các hàng này theo quy tắc thống nhất sẽ không hình thành vòng “T1 chờ T2, T2 chờ T1” như ví dụ trước.

Các bước thiết kế:

1. Xác định **toàn bộ bản ghi** có thể cần sửa hoặc khóa trong một thao tác.
2. Chọn khóa định danh ổn định, thường là **khóa chính có index**.
3. Chuẩn hóa, loại trùng và sắp xếp danh sách định danh trước khi bắt đầu truy cập các hàng có khóa.
4. Lấy khóa **từng hàng theo thứ tự tăng dần** trên cùng kết nối và transaction khi cần kiểm soát thứ tự chính xác.
5. Sau khi có đủ khóa và kiểm tra điều kiện nghiệp vụ, thực hiện `UPDATE` theo thứ tự nhất quán; `commit` ngay khi công việc DB hoàn thành.

**Quy tắc phải được áp dụng ở mọi đường ghi vào cùng loại tài nguyên.** Nếu luồng chuyển tiền khóa hàng theo ID tăng dần nhưng một luồng điều chỉnh số dư khác luôn sửa tài khoản nhận trước, hệ thống vẫn có thể sinh deadlock giữa hai luồng ấy. Tài liệu thiết kế hoặc một hàm repository dùng chung là nơi phù hợp để ghi rõ quy ước.

### Với nhiều hơn hai hàng

Giả sử người dùng chọn các ID `[40, 10, 20, 10]`. Danh sách khóa thực sự cần duyệt là `[10, 20, 40]` sau khi loại trùng và sắp xếp. Trong Java:

```java
List<Long> orderedIds = requestedIds.stream()
        .distinct()
        .sorted()
        .toList();
```

Nếu giá trị cập nhật phụ thuộc từng ID, vẫn cần lưu ánh xạ `id → thay đổi` riêng. **Chỉ thay đổi thứ tự thực thi, không thay đổi ngữ nghĩa của số tiền, số lượng hoặc phép tính gắn với mỗi hàng.** `distinct()` chỉ phù hợp để loại khóa lấy lặp; không được tự ý bỏ các thao tác nghiệp vụ có cùng ID nếu chúng cần cộng dồn.

## 3. Mô hình dữ liệu và thao tác chuyển tiền

Một ví dụ có tác động rõ ràng là chuyển một số tiền từ tài khoản nguồn sang tài khoản đích:

```sql
CREATE TABLE bank_account (
    account_id BIGINT PRIMARY KEY,
    balance    DECIMAL(18, 2) NOT NULL CHECK (balance >= 0)
);
```

Lược đồ trên minh họa `DECIMAL(18,2)` để giữ chính xác tiền thập phân và `CHECK` để tránh số dư âm. Cú pháp `CHECK`, cú pháp khóa hàng và mức độ thực thi ràng buộc phụ thuộc DBMS. Trong ví dụ Java, `account_id` do ứng dụng cung cấp; chủ đề chính ở đây là **thứ tự truy cập** chứ không phải sinh khóa chính.

Một thao tác chuyển tiền hợp lệ cần bảo đảm:

- Nguồn và đích là **hai tài khoản khác nhau**.
- Số tiền dương và tương thích với hai chữ số sau dấu thập phân.
- Tài khoản nguồn tồn tại và có đủ số dư.
- Cả hai số dư được cập nhật trong **một transaction**, hoặc không số dư nào thay đổi.
- Hai tài khoản luôn được **khóa theo `account_id` tăng dần**, bất kể hướng chuyển tiền.

Để đọc số dư trong khi giữ khóa ghi dự kiến, một số DBMS hỗ trợ cú pháp:

```sql
SELECT balance
FROM bank_account
WHERE account_id = ?
FOR UPDATE;
```

Đây là ví dụ thường áp dụng được với PostgreSQL và MySQL/InnoDB; **không phải mọi DBMS đều dùng cú pháp hoặc ngữ nghĩa giống nhau**. SQL Server, chẳng hạn, có cú pháp lock hint riêng thay cho `FOR UPDATE` theo cách này. Nếu môi trường không hỗ trợ cơ chế khóa hàng tương đương, cần điều chỉnh chiến lược SQL theo DB đích.

`SELECT ... FOR UPDATE` thông thường xin khóa phục vụ cập nhật, giữ khóa liên quan đến khi transaction kết thúc, tùy cách hiện thực và isolation level. `PreparedStatement` giúp truyền ID an toàn qua tham số `?`. Với `WHERE account_id = ?` trên khóa chính có index, truy vấn xác định đúng hàng cần tranh chấp, thay vì quét và khóa một tập lớn không chủ đích.

## 4. Triển khai JDBC: khóa theo ID, cập nhật theo ID

Ví dụ Java 17 sau có thể dùng trực tiếp trên hệ DB/driver hỗ trợ cú pháp `FOR UPDATE` và transaction của bảng mẫu. Mã dùng `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, `BigDecimal` và `try-with-resources`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class TransferRepository {
    private static final String LOCK_ACCOUNT = """
            SELECT balance FROM bank_account
            WHERE account_id = ? FOR UPDATE
            """;

    private static final String UPDATE_BALANCE = """
            UPDATE bank_account SET balance = ?
            WHERE account_id = ?
            """;

    private final DataSource dataSource;

    public TransferRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public void transfer(long fromId, long toId, BigDecimal requestedAmount)
            throws SQLException {
        if (fromId <= 0 || toId <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Accounts must be distinct positive IDs");
        }

        BigDecimal amount = Objects.requireNonNull(requestedAmount, "amount")
                .setScale(2, RoundingMode.UNNECESSARY);
        if (amount.signum() <= 0 || amount.precision() > 18) {
            throw new IllegalArgumentException("Invalid transfer amount");
        }

        long firstId = Math.min(fromId, toId);
        long secondId = Math.max(fromId, toId);

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement lock = connection.prepareStatement(LOCK_ACCOUNT);
                     PreparedStatement update = connection.prepareStatement(UPDATE_BALANCE)) {

                    // Mọi giao dịch đều lấy khóa tài khoản có ID nhỏ trước.
                    BigDecimal firstBalance = lockBalance(lock, firstId);
                    BigDecimal secondBalance = lockBalance(lock, secondId);

                    BigDecimal fromBalance = fromId == firstId
                            ? firstBalance : secondBalance;
                    BigDecimal toBalance = toId == firstId
                            ? firstBalance : secondBalance;

                    if (fromBalance.compareTo(amount) < 0) {
                        throw new IllegalStateException("Insufficient funds");
                    }

                    BigDecimal nextFrom = fromBalance.subtract(amount);
                    BigDecimal nextTo = toBalance.add(amount);

                    // Sau khi có đủ khóa, vẫn cập nhật theo cùng thứ tự.
                    BigDecimal firstNext = firstId == fromId ? nextFrom : nextTo;
                    BigDecimal secondNext = secondId == fromId ? nextFrom : nextTo;
                    updateBalance(update, firstId, firstNext);
                    updateBalance(update, secondId, secondNext);
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private static BigDecimal lockBalance(PreparedStatement statement, long id)
            throws SQLException {
        statement.setLong(1, id);
        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new SQLException("Account not found: " + id);
            }
            BigDecimal balance = result.getBigDecimal(1);
            if (balance == null) {
                throw new SQLException("NULL balance for account " + id);
            }
            return balance;
        }
    }

    private static void updateBalance(
            PreparedStatement statement, long id, BigDecimal balance)
            throws SQLException {
        statement.setBigDecimal(1, balance);
        statement.setLong(2, id);
        int affected = statement.executeUpdate();
        if (affected != 1) {
            throw new SQLException("Expected one account update for ID " + id);
        }
    }
}
```

Gọi phương thức:

```java
TransferRepository transfers = new TransferRepository(dataSource);

// Hai lời gọi này có thể xảy ra ở hai request đồng thời.
transfers.transfer(10L, 20L, new BigDecimal("25.00"));
transfers.transfer(20L, 10L, new BigDecimal("10.00"));
```

Hai lời gọi trên được viết tuần tự để dễ đọc; trong ứng dụng, chúng có thể thực thi ở **hai thread khác nhau**. Dù chiều chuyển tiền ngược nhau, cả hai đều lấy khóa `10` trước khóa `20`. Chúng có thể chờ nhau, nhưng không tự tạo vòng chờ theo hai hàng như ví dụ mở đầu nếu mọi tác nhân ghi cùng tập hàng đều tuân thủ quy ước.

### Tại sao phải lấy cả hai khóa trước khi sửa?

`lockBalance` được gọi trên `firstId` rồi `secondId`; hai phép đọc đều chạy trong cùng transaction. Sau khi đã lấy đủ các khóa, mã mới kiểm tra số dư và tính hai giá trị mới. Điều này giúp phép đọc, kiểm tra và ghi dùng cùng trạng thái đã được bảo vệ bằng khóa trong DB có hỗ trợ ngữ nghĩa tương ứng.

`updateBalance` vẫn được gọi với `firstId` rồi `secondId`, chứ không tự động trở lại thứ tự “nguồn trước, đích sau”. Giữ cùng thứ tự giúp dễ kiểm tra khi về sau ứng dụng bổ sung ràng buộc hoặc câu lệnh cập nhật khác.

`BigDecimal` giữ chính xác giá trị thập phân; `setScale(2, RoundingMode.UNNECESSARY)` không tự làm tròn sai giá trị tiền đầu vào. Ràng buộc `DECIMAL(18,2)` của DB vẫn có thể từ chối kết quả cộng vượt phạm vi; trường hợp đó cần rollback toàn bộ, không được giữ riêng số dư đã trừ.

### Ranh giới transaction và xử lý lỗi

`connection.setAutoCommit(false)` được gọi trước khi lấy khóa. Các khóa giữ trong transaction theo cơ chế của DB; `connection.commit()` chỉ được gọi sau khi **cả hai** phép cập nhật thành công. Nếu thiếu tài khoản, thiếu số dư, gặp lỗi khóa, lỗi dữ liệu hay `SQLException`, mã thử `rollback()` để hoàn tác phần thay đổi chưa commit; ngoại lệ rollback được gắn vào lỗi gốc bằng `addSuppressed`.

`try-with-resources` bảo đảm các `ResultSet`, `PreparedStatement` và kết nối được đóng. Nếu `DataSource` dùng connection pool, `Connection.close()` thường trả kết nối về pool. Không mở một `Connection` mới giữa bước lấy khóa và cập nhật: khóa từ kết nối thứ nhất không bảo vệ một transaction độc lập trên kết nối thứ hai.

**Giả định phạm vi:** phương thức tự sở hữu transaction. Nếu mã nghiệp vụ lớn hơn đã sở hữu `Connection` hoặc transaction manager, repository nên nhận cùng kết nối từ tầng gọi và để tầng ấy chịu trách nhiệm `commit`/`rollback`. Không tự đổi `autoCommit` trên kết nối do người khác quản lý.

## 5. `ORDER BY` trong SQL có đảm bảo thứ tự khóa không?

Một giải pháp trông có vẻ gọn hơn là truy vấn cả hai hàng:

```sql
SELECT account_id, balance
FROM bank_account
WHERE account_id IN (?, ?)
ORDER BY account_id
FOR UPDATE;
```

Kết quả truy vấn có thể **được trả theo thứ tự `account_id`**. Nhưng thứ tự hàng trả về và **thứ tự DB thực sự lấy khóa** không nhất thiết là một, vì optimizer có thể chọn kế hoạch truy vấn, quét index hoặc khóa hàng trước bước sắp xếp. Các DB/phiên bản có thể khác nhau về cách `ORDER BY`, `LIMIT` và `FOR UPDATE` tương tác. Bởi vậy, không được mặc định chỉ thêm `ORDER BY` là đủ để bảo đảm thứ tự lấy khóa ở mọi DB.

Ví dụ Java ở trên cố ý phát ra **hai câu lệnh khóa hàng riêng biệt theo khóa chính**: chỉ sau khi lệnh đầu hoàn tất mới thực thi lệnh thứ hai. Cách này tăng số lượt gửi lệnh so với khóa nhiều hàng cùng lúc, nhưng diễn đạt thứ tự yêu cầu một cách trực tiếp. Khi cần tối ưu cho hàng trăm hoặc hàng nghìn ID, hãy cân nhắc chiến lược khóa theo lô phù hợp với **DBMS cụ thể** và xác minh thực nghiệm thứ tự khóa, tránh khẳng định tính đúng đắn chỉ từ thứ tự hiển thị của `ResultSet`.

Tương tự, `UPDATE ... WHERE id IN (...)` không hứa cập nhật từng hàng theo thứ tự một danh sách `IN` của Java. `PreparedStatement.addBatch()` có thể giúp giảm chi phí truyền lệnh nhưng driver/DB có thể tối ưu hoặc viết lại batch. Nếu tính đúng đắn yêu cầu một thứ tự khóa được kiểm soát, cần xác nhận hành vi của các tối ưu đó thay vì mặc nhiên dựa vào thứ tự `addBatch()`.

## 6. Thiết kế thứ tự cho nhiều bảng và nhiều loại tài nguyên

Thứ tự theo ID tăng dần trong **một** bảng là một điểm bắt đầu tốt. Với nghiệp vụ tác động nhiều bảng, chỉ quy ước theo ID chưa đủ: cần thứ tự giữa **loại tài nguyên** rồi đến ID trong từng loại.

Ví dụ giao dịch tạo đơn và trừ tồn kho đồng thời liên quan:

```text
Resource order: 1. inventory(product_id tăng dần)
                2. reservation(reservation_id tăng dần)
                3. order_state(order_id tăng dần)
```

Đó chỉ là **một ví dụ quy ước**, không phải thứ tự bắt buộc cho mọi hệ thống. Mục tiêu là mọi code path cùng thao tác trên các tài nguyên đó dùng một quy tắc nhất quán. Nếu luồng A khóa tồn kho rồi trạng thái đơn, còn luồng B khóa trạng thái đơn rồi tồn kho, deadlock vẫn có thể phát sinh mặc dù mỗi luồng tự sắp xếp ID trong từng bảng.

Một cách diễn đạt thứ tự tổng quát là khóa dạng `(loại_tài_nguyên, khóa_chính)` với thứ tự so sánh đã công bố. Khi truy cập nhiều tenant, có thể thêm `tenant_id` vào định danh nếu nó là một phần của khóa thực tế. **Quy ước phải phản ánh đúng những hàng DB thực sự khóa**, không chỉ những đối tượng ứng dụng đang xử lý.

### Các khóa phát sinh gián tiếp

Lệnh `UPDATE` hoặc `INSERT` có thể tương tác thêm với:

- Khóa **foreign key** hoặc hàng ở bảng cha được kiểm tra khi sửa bảng con.
- Index phụ, unique index và phạm vi giá trị (*range/gap locks*) theo isolation level và DBMS.
- Trigger, stored procedure và cơ chế cascade thay đổi những hàng không hiển thị trực tiếp trong câu SQL.
- Những tác vụ kiểm tra ràng buộc hoặc cập nhật tổng hợp do cơ sở dữ liệu thực hiện.

Vì vậy, sắp xếp hai tài khoản theo `account_id` **giảm một nguồn deadlock**, nhưng không chứng minh mọi transaction trong ứng dụng chắc chắn không thể deadlock. Nếu DB dùng khóa ở cấp trang, bảng, phạm vi index hoặc có trigger cập nhật bảng khác, các vòng chờ khác vẫn có thể hình thành.

### Index quyết định phạm vi tranh chấp

`UPDATE bank_account WHERE account_id = ?` có thể tìm đúng hàng bằng index khóa chính. Ngược lại, cập nhật theo cột không có index, hoặc truy vấn điều kiện phạm vi rộng, có thể phải quét rất nhiều hàng và giữ các khóa rộng hơn kỳ vọng. Tùy DB và isolation level, câu lệnh còn có thể khóa phạm vi index để chống phantom.

Thứ tự nhất quán không thay thế việc thiết kế index phù hợp. Khi điều tra tranh chấp, cần xem **execution plan** và thông tin khóa thực tế trên DB, không suy đoán chỉ dựa vào SQL được viết trong Java.

## 7. Thời gian giữ khóa quan trọng không kém thứ tự

Thứ tự khóa ngăn một số vòng chờ; còn **transaction ngắn** giúp giảm thời gian giao dịch khác phải chờ. Trong ứng dụng JDBC, nên:

1. **Chuẩn bị và xác thực đầu vào** trước khi mở transaction, nếu có thể kiểm tra độc lập với trạng thái DB hiện tại.
2. **Chỉ truy vấn cột cần thiết**, sử dụng `WHERE` có thể dùng index.
3. **Lấy khóa càng muộn càng hợp lý** nhưng vẫn trước bước cần tính đúng đắn về đồng thời; cập nhật xong thì commit sớm.
4. **Không gọi HTTP API, gửi email, chờ người dùng hoặc chạy xử lý CPU kéo dài** trong khi đang giữ khóa DB.
5. **Không giữ `ResultSet` mở lâu** sau khi đã lấy đủ dữ liệu; đóng câu lệnh và result set theo `try-with-resources`.
6. **Không trì hoãn commit để ghi log hoặc làm công việc phụ không thuộc transaction**; nếu cần đảm bảo phát thông điệp theo dữ liệu vừa commit, cân nhắc outbox theo yêu cầu hệ thống.

Với khối lượng lớn, một transaction khóa hàng nghìn ID có thể gây thời gian chờ đáng kể dù thứ tự là nhất quán. Cần cân đối giữa tính nguyên tử của nghiệp vụ và phạm vi transaction. Không chia một thao tác **bắt buộc nguyên tử** thành nhiều commit độc lập chỉ để giảm lock timeout, vì làm vậy thay đổi tính đúng đắn khi có lỗi giữa chừng.

### Khóa trước hay cập nhật trước?

Khi đã biết tập ID, có thể thực hiện `UPDATE` trực tiếp theo thứ tự ổn định và để DB lấy khóa ghi khi chạy lệnh. Nhưng nếu quyết định cập nhật phụ thuộc vào **giá trị hiện tại của nhiều hàng** (ví dụ kiểm tra số dư nguồn rồi cộng trừ cả hai), cần kiểm soát đồng thời giữa bước đọc và bước ghi. `SELECT ... FOR UPDATE` hoặc cơ chế điều kiện cập nhật/kiểm tra phiên bản (*optimistic locking*) giúp bảo vệ phần đọc-kiểm tra-ghi theo đặc tính DB.

Nếu cần chuyển một lượng tiền mà không muốn khóa hàng trước khi đọc, một phương án khác là **cập nhật có điều kiện**:

```sql
UPDATE bank_account
SET balance = balance - ?
WHERE account_id = ? AND balance >= ?;
```

Sau lệnh này, phải kiểm tra số hàng tác động; `0` nghĩa là không thỏa điều kiện hoặc không tìm thấy hàng. Nếu còn cần cập nhật tài khoản đích, hai cập nhật vẫn phải chạy trong **cùng transaction**. Hướng chuyển tiền có thể làm thứ tự ghi thay đổi, nên vẫn cần xem xét quy ước khóa chung, thứ tự cập nhật và cơ chế retry. Đừng xem điều kiện `balance >= ?` là bằng chứng tự động loại bỏ mọi deadlock.

## 8. Isolation level, lock timeout và xử lý deadlock

JDBC cho phép truy vấn hoặc thiết lập isolation level thông qua `Connection`:

```java
int currentLevel = connection.getTransactionIsolation();

// Khi cần thay đổi, thực hiện trước khi transaction bắt đầu
// và chỉ khi DB/driver hỗ trợ chính sách mong muốn:
connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
```

Các mức như `READ_COMMITTED`, `REPEATABLE_READ` và `SERIALIZABLE` có thể ảnh hưởng tới phạm vi khóa, thời gian giữ khóa, hiện tượng đọc lặp/phantom và khả năng bị từ chối giao dịch do tranh chấp. **Không có bảng ánh xạ hoàn toàn đồng nhất giữa mức isolation JDBC và cơ chế khóa nội bộ của mọi DBMS**. Ví dụ một DB dùng MVCC để đọc nhất quán, DB khác dùng khóa đọc nhiều hơn; `SELECT ... FOR UPDATE` cũng có hành vi cụ thể theo sản phẩm.

Không tùy tiện hạ isolation level chỉ để “giảm deadlock” nếu điều đó phá vỡ điều kiện nghiệp vụ. `DatabaseMetaData.supportsTransactionIsolationLevel(...)`, `supportsTransactions()` và `supportsSelectForUpdate()` giúp kiểm tra khả năng được driver báo cáo, nhưng vẫn cần integration test trên đúng phiên bản cơ sở dữ liệu.

### Deadlock vẫn phải có cách xử lý

Ngay cả khi đã thiết kế thứ tự nhất quán, transaction vẫn có thể bị deadlock hoặc lỗi serialization bởi các lệnh/triggers khác. Ứng dụng nên xác định **cách xử lý retry ở ranh giới toàn bộ transaction**, thay vì chỉ chạy lại câu `UPDATE` cuối cùng trên một transaction có thể đã hỏng.

Quy tắc cơ bản:

- **Rollback** transaction lỗi hoặc đóng/loại bỏ kết nối không còn dùng được; tạo transaction mới cho lần thử lại.
- Phân loại lỗi bằng `SQLException.getSQLState()`, mã lỗi theo vendor và chính sách cụ thể của DB. Các lớp `SQLTransactionRollbackException`, `SQLTransientException` có thể hữu ích nhưng không bao quát đồng nhất mọi driver.
- **Giới hạn số lần thử**, dùng backoff có jitter và ghi nhận số lần xảy ra xung đột để không lặp vô hạn.
- Chỉ retry khi thao tác **an toàn để thực thi lại**. Với API tạo đối tượng, thanh toán hoặc phát thông điệp ngoài DB, cần khóa yêu cầu duy nhất/idempotency key và tách tác động ngoài transaction.
- Khi mất kết nối **đúng lúc `commit()`**, kết quả commit có thể không rõ: không mặc nhiên coi đó là rollback và lặp lại một thao tác có thể tạo tác động trùng.

Ví dụ mã giả (không gắn với mã SQLState cố định của một DB):

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        transferRepository.transfer(fromId, toId, amount);
        break; // Transaction đã commit thành công.
    } catch (SQLException ex) {
        if (!isKnownRetryableTransactionFailure(ex)
                || attempt == maxAttempts) {
            throw ex;
        }
        backoffBeforeRetry(attempt);
    }
}
```

`isKnownRetryableTransactionFailure` và `backoffBeforeRetry` là **hàm do ứng dụng thiết kế**, không phải API JDBC. Chúng cần được hiện thực bằng danh sách lỗi thực sự an toàn để thử lại cho DB/driver, chính sách idempotency của nghiệp vụ và cách chờ phù hợp môi trường. Mã ví dụ `TransferRepository.transfer()` đã sở hữu transaction và thử rollback khi lỗi; tầng retry chỉ gọi **lại toàn bộ phương thức**, không tái sử dụng `Connection` cũ.

`Statement.setQueryTimeout(int seconds)` có thể giới hạn thời gian thực thi một câu lệnh theo khả năng driver, nhưng **không phải một API khóa-thời-gian chuẩn cho mọi DB**. Thời gian chờ lock thường có cấu hình riêng của DBMS; không được nhầm query timeout với lock timeout và network timeout. Một transaction có thể hết hạn vì chờ khóa ngay cả khi không có deadlock.

## 9. Các lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Hướng sửa |
| --- | --- | --- |
| Luôn sửa nguồn trước đích | Hai giao dịch ngược chiều khóa hai hàng theo thứ tự trái nhau | Khóa theo ID tăng dần, bất kể chiều nghiệp vụ |
| Dùng `HashSet` rồi duyệt trực tiếp | Thứ tự duyệt không có hợp đồng ổn định | Sao chép ra danh sách và sắp xếp rõ ràng |
| Chỉ thêm `ORDER BY` cho một truy vấn `FOR UPDATE` nhiều hàng | Thứ tự kết quả không nhất thiết là thứ tự DB lấy khóa | Dùng chiến lược xác nhận được trên DB, hoặc khóa từng ID tuần tự |
| `UPDATE ... WHERE id IN (...)` và tin rằng thứ tự `IN` là thứ tự khóa | DB có thể chọn kế hoạch thực thi khác | Không dựa vào thứ tự tham số `IN` để chứng minh tránh deadlock |
| Khóa đúng thứ tự ở một repository nhưng luồng khác khóa ngược | Deadlock vẫn có thể phát sinh giữa các đường code | Quy ước chung trên mọi đường ghi liên quan |
| Xử lý HTTP/gửi email trong transaction | Giữ khóa quá lâu, tăng thời gian chờ | Đưa tác động bên ngoài ra ngoài transaction hoặc dùng outbox |
| Dùng nhiều `Connection` cho hai bước của cùng giao dịch | Không còn cùng ranh giới khóa và commit | Dùng cùng `Connection` hoặc transaction manager phù hợp |
| Catch `SQLException` rồi tiếp tục commit | Transaction có thể không còn hợp lệ; dữ liệu bị cập nhật một phần | Rollback toàn bộ thao tác và phân loại lỗi |
| Retry một câu lệnh giữa transaction bị deadlock | Không khôi phục được trạng thái nhất quán, nhiều DB đã hủy giao dịch | Retry **toàn transaction** khi xác định được an toàn |
| Thiếu index ở điều kiện tìm hàng | Có thể quét/khóa nhiều hàng hơn, tăng cạnh tranh | Thiết kế index và kiểm tra execution plan |

## 10. Kiểm thử đồng thời và quan sát thực tế

Một integration test đơn luồng chỉ xác nhận phép cộng trừ đúng; nó **không đủ** chứng minh chiến lược thứ tự khóa thực sự hữu ích. Kiểm thử trên DB/driver triển khai cần tạo các transaction đồng thời với cùng tập hàng.

Ví dụ kế hoạch kiểm thử:

| Tình huống | Cách chạy | Điều cần xác nhận |
| --- | --- | --- |
| Hai chuyển tiền ngược chiều | Chạy đồng thời `10 → 20` và `20 → 10` nhiều lần | Không sinh vòng chờ từ chính thứ tự khóa hai hàng; số dư tổng không đổi |
| Nhiều tài khoản chồng lấn | Các giao dịch xử lý tập `{10, 20, 30}` với thứ tự đầu vào khác nhau | Code luôn khóa cùng thứ tự xác định |
| Số dư không đủ | Hai giao dịch đồng thời trừ cùng tài khoản | Chỉ giao dịch đủ điều kiện được commit; số dư không âm |
| Lỗi câu lệnh thứ hai | Gây lỗi ràng buộc hoặc lỗi dữ liệu sau khi cập nhật hàng đầu | Rollback làm số dư cả hai tài khoản trở lại trước transaction |
| Giữ khóa lâu | Một transaction cố ý giữ khóa `10` trước khi commit | Transaction khác có thể chờ hoặc timeout nhưng không nhất thiết deadlock |
| Luồng khác lấy khóa ngược | Kết hợp với một đoạn code thử nghiệm khóa `20` trước `10` | Có thể tái hiện deadlock và xác nhận biện pháp phòng ngừa |
| Retry sau lỗi tạm thời | Tiêm một lỗi deadlock/serialization được nhận diện | Tạo transaction mới, giới hạn retry, không nhân đôi tác động |

Để kiểm chứng tính nhất quán tiền, trước khi bắt đầu lưu tổng số dư của các tài khoản đang thử. Sau khi tất cả các giao dịch được xác nhận commit hoặc rollback, tính tổng lại với một truy vấn mới: nếu bài toán chỉ chuyển tiền giữa các tài khoản này, tổng số dư không được thay đổi. Kiểm tra thêm từng số dư không âm và mỗi giao dịch thành công chỉ áp dụng một lần.

**Lưu ý về tính lặp lại của kiểm thử:** deadlock phụ thuộc lịch chạy, nên không thể khẳng định “không có deadlock” chỉ vì chạy thử vài lần không gặp. Có thể dùng hai kết nối riêng, hàng rào đồng bộ ở các mốc đã lấy khóa đầu tiên, và lock timeout vừa đủ trong môi trường test để quan sát đường chờ. Dùng công cụ quan sát khóa/transaction và deadlock log của DBMS để xem chính xác những tài nguyên nào đang bị khóa; không đoán chỉ từ số lượng câu `UPDATE`.

## 11. Bài tập tự kiểm tra

**Bài 1 — Tìm deadlock.** Giao dịch A khóa hàng `7` rồi `9`; giao dịch B khóa hàng `9` rồi `7`. Vẽ đồ thị chờ khi mỗi bên đã giữ khóa đầu tiên và đang chờ khóa còn lại.

**Gợi ý:** A chờ B vì khóa `9`; B chờ A vì khóa `7` → hình thành vòng chờ.

**Bài 2 — Sắp xếp định danh.** Một thao tác nhận các ID `[80, 20, 50, 20]`. Hãy tính thứ tự lấy khóa và giải thích tại sao không được bỏ qua hai thay đổi nghiệp vụ khác nhau cùng tác động ID `20` chỉ vì bước lấy khóa loại trùng.

**Gợi ý:** Thứ tự khóa là `20, 50, 80`; tổng hợp các thay đổi của ID `20` theo hợp đồng nghiệp vụ trước khi cập nhật.

**Bài 3 — Đọc `FOR UPDATE`.** Vì sao `SELECT ... WHERE account_id IN (?, ?) ORDER BY account_id FOR UPDATE` chưa đủ để chứng minh DB đã lấy khóa theo ID tăng dần?

**Gợi ý:** Optimizer có thể quyết định thứ tự đọc và khóa trước khi sắp xếp kết quả; ngữ nghĩa thực thi phụ thuộc DBMS.

**Bài 4 — Ranh giới giao dịch.** Trong `TransferRepository`, điều gì xảy ra nếu cập nhật nguồn thành công nhưng cập nhật đích bị lỗi ràng buộc? Vì sao không thể dùng hai kết nối độc lập cho hai cập nhật?

**Gợi ý:** `rollback()` phải hoàn tác cả bước đầu; hai kết nối có hai ranh giới transaction khác nhau.

**Bài 5 — Deadlock và timeout.** Mọi giao dịch đã lấy khóa theo thứ tự ID tăng dần, nhưng giao dịch X vẫn hết thời gian chờ khóa. Có phải quy tắc sắp xếp sai không?

**Gợi ý:** Không nhất thiết. Một giao dịch khác giữ khóa quá lâu cũng gây timeout mà không có vòng chờ.

**Bài 6 — Thiết kế đa bảng.** Luồng A cập nhật `inventory` rồi `order_state`, luồng B cập nhật `order_state` rồi `inventory`. Dù cả hai đều sắp xếp ID trong từng bảng, vấn đề gì vẫn có thể xảy ra? Đề xuất một thứ tự tài nguyên chung.

**Gợi ý:** Cần thống nhất cả thứ tự **bảng/tài nguyên** lẫn thứ tự **ID**, ví dụ luôn `inventory` trước `order_state`.

## Tổng kết

Trong JDBC, **thiết kế thứ tự cập nhật** là cách giảm một nguồn deadlock phổ biến khi nhiều giao dịch sửa những hàng giao nhau. Hãy xác định tập khóa, sắp xếp theo một định danh chung và yêu cầu mọi luồng truy cập các tài nguyên liên quan tuân thủ cùng quy ước. Khi cần đọc giá trị trước khi tính toán, dùng cơ chế khóa hàng phù hợp DB như `SELECT ... FOR UPDATE`, giữ việc đọc/ghi trên một `Connection` với `autoCommit = false`, và `commit` hoặc `rollback` toàn bộ thao tác. Thứ tự nhất quán không loại bỏ mọi tranh chấp; index, thời gian giữ khóa, isolation level, SQL do DB thực thi và xử lý retry vẫn quyết định tính ổn định khi chạy đồng thời trên hệ thống thực tế.
