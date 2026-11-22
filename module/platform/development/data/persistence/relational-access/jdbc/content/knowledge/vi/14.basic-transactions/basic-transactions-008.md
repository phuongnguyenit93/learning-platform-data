# Khôi phục trạng thái kết nối trước khi trả quyền sử dụng trong JDBC

Trong ứng dụng Java dùng **JDBC**, một `Connection` không chỉ giữ đường truyền tới cơ sở dữ liệu. Nó còn mang **trạng thái phiên làm việc**: `autoCommit`, transaction đang mở, mức cô lập, chế độ chỉ đọc, schema/catalog đang chọn và những thiết lập khác. Nếu một đoạn mã mượn kết nối từ `DataSource`, thay đổi trạng thái rồi trả kết nối về pool mà không dọn dẹp, yêu cầu tiếp theo có thể nhận lại một phiên với trạng thái ngoài dự kiến.

Bài học thuộc chương **Giao dịch cơ bản**, tập trung vào trách nhiệm của đoạn mã **sở hữu quyền sử dụng kết nối**: xác định ranh giới transaction, thực hiện `commit()` hoặc `rollback()`, khôi phục những thuộc tính đã thay đổi và gọi `close()` đúng lúc. Đây là nền tảng để triển khai CRUD, xử lý lỗi và transaction bằng các API chuẩn `java.sql` và `javax.sql.DataSource`.

## 1. Kết nối được mượn không phải kết nối mới tinh

Với một `DataSource` có connection pool, mỗi lần gọi `getConnection()` thường nhận một **kết nối logic** trỏ tới một kết nối vật lý có thể đã phục vụ yêu cầu trước đó. Tùy cấu hình pool, `close()` trên kết nối logic sẽ **trả quyền sử dụng về pool** để yêu cầu khác mượn tiếp, thay vì đóng ngay kết nối vật lý.

```text
Yêu cầu A
   │
   ▼
dataSource.getConnection()
   │  Mượn Connection từ pool
   ▼
Thực hiện SQL / transaction
   │
   ├─ Kết thúc transaction: commit hoặc rollback
   ├─ Khôi phục trạng thái đã thay đổi
   ▼
connection.close()
   │  Trả quyền sử dụng
   ▼
Pool ──────────────► Yêu cầu B mượn kết nối tiếp theo
```

Giả sử yêu cầu A đặt `setAutoCommit(false)` rồi đóng kết nối mà không kết thúc transaction hoặc không phục hồi `autoCommit`. Yêu cầu B có thể gặp lỗi, chờ khóa, không thấy dữ liệu được commit như kỳ vọng hoặc thực thi SQL dưới chế độ transaction không mong muốn. Pool tốt thường có biện pháp làm sạch trạng thái, nhưng **không nên coi cơ chế đó là lý do để bỏ qua trách nhiệm của mã sử dụng JDBC**.

Với `DriverManager.getConnection(...)` không có pool, `close()` thường đóng kết nối vật lý. Việc rollback và đóng đúng lúc vẫn quan trọng: nó giải phóng tài nguyên, khóa và đảm bảo hành vi khi gặp lỗi.

## 2. Những trạng thái nào có thể rò rỉ sang lần sử dụng tiếp?

| Thuộc tính hoặc tài nguyên | API JDBC tiêu biểu | Tác động nếu để sai trạng thái |
| --- | --- | --- |
| Transaction chưa kết thúc | `commit()`, `rollback()` | Có thể còn thay đổi chưa commit và khóa đang giữ; hành vi khi `close()` phụ thuộc driver/pool. |
| Chế độ auto-commit | `getAutoCommit()`, `setAutoCommit(boolean)` | Các câu SQL về sau có thể không được commit tự động hoặc có ranh giới transaction khác dự kiến. |
| Chế độ chỉ đọc | `isReadOnly()`, `setReadOnly(boolean)` | Thao tác ghi về sau có thể bị từ chối, hoặc tối ưu hóa của driver/server khác đi; đây không phải cơ chế phân quyền bảo mật. |
| Mức cô lập | `getTransactionIsolation()`, `setTransactionIsolation(int)` | Yêu cầu sau có thể quan sát tính nhất quán và hiện tượng khóa khác dự kiến. |
| Catalog hoặc schema | `getCatalog()`/`setCatalog()`, `getSchema()`/`setSchema()` | Câu SQL không ghi đầy đủ schema có thể đọc/ghi sang phạm vi dữ liệu khác. |
| Cách giữ cursor khi commit | `getHoldability()`, `setHoldability(int)` | Vòng đời `ResultSet` có thể thay đổi; không phải driver nào cũng hỗ trợ mọi chế độ. |
| Thuộc tính phiên khác | `setClientInfo()`, `setNetworkTimeout()`, SQL `SET ...`, role, bảng tạm | Có thể còn các thiết lập đặc thù mà `setAutoCommit(true)` không thể xóa. |

**Không cần lưu và đặt lại mọi thuộc tính ở mọi phương thức.** Hãy ghi nhận **những gì phương thức thực sự sửa**, trạng thái ban đầu của chúng và trách nhiệm làm sạch tương ứng. Ví dụ: nếu không bao giờ thay đổi schema hay mức cô lập, không có lý do để mỗi CRUD đơn giản đều gọi `setSchema()` hoặc `setTransactionIsolation()`.

Một số thông số là gợi ý dành cho server hoặc có hỗ trợ tùy driver. Cơ chế reset của pool cũng khác nhau. Khi dùng session SQL như `SET ROLE`, thay đổi múi giờ, biến session hoặc bảng tạm, cần giải pháp dọn dẹp theo hệ quản trị và pool đang triển khai; các setter chuẩn của JDBC không bao quát hết.

## 3. Quy tắc quan trọng nhất: kết thúc transaction trước khi phục hồi `autoCommit`

Theo hợp đồng JDBC, nếu gọi `setAutoCommit(...)` làm **thay đổi giá trị của `autoCommit` khi đang có transaction**, transaction hiện tại sẽ được **commit**. Do đó, một cách dọn dẹp tưởng như vô hại có thể biến lỗi nghiệp vụ thành dữ liệu được ghi ngoài ý muốn:

```java
connection.setAutoCommit(false);
// Thực thi một số câu INSERT / UPDATE...

// Sai: nếu transaction vẫn đang hoạt động, chuyển sang true
// có thể COMMIT cả các thay đổi chưa được rollback.
connection.setAutoCommit(true);
```

Thứ tự cần giữ là:

```text
Mượn kết nối, ghi nhận trạng thái ban đầu
                  │
                  ▼
      Bắt đầu transaction có chủ đích
                  │
             Thực thi SQL
              /         \
          Thành công    Có lỗi
             │            │
          commit()      rollback()
              \         /
                  ▼
       Transaction đã kết thúc
                  │
                  ▼
     Phục hồi autoCommit / các thuộc tính đã sửa
                  │
                  ▼
            close() kết nối
```

Chú ý ba điểm:

1. `Connection.close()` **không thay thế** việc chủ động `rollback()` hoặc `commit()`. Đóng kết nối khi transaction còn hoạt động có hành vi phụ thuộc triển khai; ứng dụng nên xác định rõ kết quả transaction.
2. Sau `rollback()`, các thay đổi chưa commit của transaction được hoàn tác theo khả năng của cơ sở dữ liệu; điều này không bảo đảm mọi giá trị sequence/identity đã cấp phát sẽ được tái sử dụng.
3. Nếu `rollback()` **thất bại**, không được mặc nhiên gọi `setAutoCommit(true)` vì transaction có thể vẫn đang hoạt động và sẽ bị commit. Phải coi trạng thái kết nối là **không chắc chắn** và yêu cầu pool loại bỏ hoặc vô hiệu hóa kết nối theo cơ chế mà pool hỗ trợ.

## 4. Ví dụ thực tế: chuyển tiền và khôi phục `autoCommit`

Giả sử có bảng `bank_accounts`:

```sql
CREATE TABLE bank_accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL
);
```

Chuyển tiền giữa hai tài khoản là nghiệp vụ có **hai lệnh `UPDATE` phải thành công hoặc thất bại cùng nhau**. Nếu trừ tiền thành công nhưng cộng tiền thất bại, transaction phải rollback.

Ví dụ dưới đây dùng `DataSource`, `PreparedStatement`, `BigDecimal` và một `Connection` cho toàn bộ giao dịch. Điều kiện `balance >= ?` ngăn trừ tiền khi số dư không đủ; trong hệ thống tài chính thật cần thêm yêu cầu kiểm soát đồng thời, kiểm toán và quy tắc nghiệp vụ phù hợp.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long sourceId, long targetId, BigDecimal amount)
            throws SQLException {
        if (amount == null || amount.signum() <= 0 || sourceId == targetId) {
            throw new IllegalArgumentException("Invalid transfer arguments");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();

            // Phương thức này sở hữu transaction của kết nối mượn từ pool.
            // Nếu có transaction do thành phần khác quản lý, phải dùng API
            // của transaction manager đó thay vì tự commit/rollback.
            if (!originalAutoCommit) {
                throw new SQLException(
                        "Expected an idle connection with autoCommit=true");
            }

            boolean transactionStarted = false;
            boolean transactionEnded = false;
            Throwable primaryFailure = null;

            try {
                connection.setAutoCommit(false);
                transactionStarted = true;

                String debitSql =
                        "UPDATE bank_accounts SET balance = balance - ? " +
                        "WHERE id = ? AND balance >= ?";
                try (PreparedStatement debit =
                             connection.prepareStatement(debitSql)) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, sourceId);
                    debit.setBigDecimal(3, amount);

                    if (debit.executeUpdate() != 1) {
                        throw new SQLException(
                                "Source account missing or insufficient funds");
                    }
                }

                String creditSql =
                        "UPDATE bank_accounts SET balance = balance + ? " +
                        "WHERE id = ?";
                try (PreparedStatement credit =
                             connection.prepareStatement(creditSql)) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, targetId);

                    if (credit.executeUpdate() != 1) {
                        throw new SQLException("Target account does not exist");
                    }
                }

                connection.commit();
                transactionEnded = true;

            } catch (SQLException | RuntimeException | Error failure) {
                primaryFailure = failure;

                if (transactionStarted && !transactionEnded) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }

                throw failure;

            } finally {
                // Chỉ bật lại autoCommit khi commit hoặc rollback
                // đã được xác nhận thành công.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(originalAutoCommit);
                    } catch (SQLException restoreFailure) {
                        if (primaryFailure != null) {
                            primaryFailure.addSuppressed(restoreFailure);
                        } else {
                            throw restoreFailure;
                        }
                    }
                }
            }
        }
    }
}
```

Ví dụ gọi:

```java
transferService.transfer(10L, 20L, new BigDecimal("250.00"));
```

**Diễn giải vòng đời:**

- **Trước khi đổi trạng thái:** lưu giá trị `getAutoCommit()`. Vì phương thức tự quản lý transaction trên một kết nối mượn mới, ví dụ chủ động yêu cầu trạng thái ban đầu là `true`. Một kết nối có `autoCommit=false` có thể thuộc transaction khác; không thể tùy tiện nhận quyền `commit()` của nó.
- **Khi bắt đầu:** gọi `setAutoCommit(false)` và đánh dấu `transactionStarted`. Cả hai lệnh cập nhật dùng **cùng `Connection`**, nên tham gia một transaction.
- **Khi thành công:** `commit()` thành công thì đánh dấu `transactionEnded=true` và khôi phục `autoCommit` như ban đầu.
- **Khi lỗi:** cố gắng `rollback()`; chỉ xem transaction đã kết thúc khi lời gọi thành công. `getSuppressed()` cho phép giữ thông tin về lỗi rollback/khôi phục mà không làm mất ngoại lệ nghiệp vụ đầu tiên.
- **Khi rời phương thức:** `try-with-resources` gọi `close()`, nên kết nối được giải phóng hoặc trả về pool theo cơ chế `DataSource`. Không trả `ResultSet` hoặc `PreparedStatement` còn mở cho tầng gọi.

Ví dụ này **không tuyên bố rằng rollback lỗi vẫn có thể phục hồi kết nối**. Nếu `rollback()` thất bại, mã sẽ bỏ qua `setAutoCommit(true)` để tránh commit ngoài ý muốn. Tuy nhiên, `close()` có thể đi qua proxy của pool; một hệ thống sản phẩm cần cấu hình pool để **loại bỏ/vô hiệu hóa** kết nối có transaction không rõ trạng thái thay vì tái sử dụng nó. Cơ chế này phụ thuộc thư viện connection pool và không thể thể hiện chung bằng một lời gọi JDBC tương thích mọi pool.

Một lưu ý nữa: nếu `commit()` ném `SQLException` do lỗi mạng, ứng dụng có thể không xác định được server đã commit hay chưa. Thử `rollback()` là bước dọn dẹp hợp lý, nhưng **không chứng minh** nghiệp vụ chưa được ghi. Với thao tác có tác động kinh doanh, cần cách đối soát hoặc khóa idempotency theo thiết kế riêng.

## 5. Khi thay đổi nhiều thuộc tính: ghi nhận và phục hồi đúng phần mình sửa

Một số nghiệp vụ cần đọc nhiều dữ liệu với mức cô lập nhất định, bật chế độ chỉ đọc hoặc thay schema. Lúc này, phương thức phải lưu trạng thái gốc **trước khi thay đổi**:

```java
boolean oldAutoCommit = connection.getAutoCommit();
boolean oldReadOnly = connection.isReadOnly();
int oldIsolation = connection.getTransactionIsolation();
String oldSchema = connection.getSchema();
```

Ví dụ một luồng xử lý độc lập có thể yêu cầu:

```java
// Đặt những thuộc tính này trước khi bắt đầu transaction,
// theo khả năng hỗ trợ của hệ quản trị và JDBC driver.
connection.setReadOnly(true);
connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ);
connection.setSchema("reporting");
connection.setAutoCommit(false);

// Thực thi các truy vấn, sau đó commit() hoặc rollback()
// transaction thành công trước khi phục hồi trạng thái.
```

Sau khi transaction đã **chắc chắn kết thúc**, cần phục hồi các thuộc tính đã sửa, chẳng hạn:

```java
// Minh họa bước cleanup, chỉ chạy khi transaction không còn hoạt động.
connection.setAutoCommit(oldAutoCommit);
connection.setTransactionIsolation(oldIsolation);
connection.setReadOnly(oldReadOnly);
connection.setSchema(oldSchema);
```

Đây là các **đoạn minh họa thứ tự thao tác**, không phải một phương thức có thể copy nguyên xi để xử lý mọi lỗi. Trong mã thực tế, mỗi setter ở bước phục hồi có thể ném `SQLException`; cần cố gắng dọn dẹp các thuộc tính còn lại và báo đầy đủ lỗi thay vì dừng sau setter đầu tiên. Đặt lại `setSchema(null)` hoặc một giá trị schema cụ thể chỉ khi driver và chính sách pool hỗ trợ. Việc chuyển schema, read-only hoặc isolation **khi transaction đang mở** có thể bị cấm hoặc có ngữ nghĩa khác giữa các hệ quản trị; hãy cấu hình trước khi bắt đầu transaction và khôi phục sau khi kết thúc.

Phương thức chỉ đọc được thiết kế tốt thường **không thay đổi thuộc tính nào nếu không cần thiết**. Ví dụ: nếu `DataSource` đã cung cấp kết nối với cấu hình phù hợp, không nên gọi lại `setTransactionIsolation(...)` trên mọi lần `SELECT` vì có thể phát sinh round trip hoặc thay đổi hành vi khóa.

### Vì sao thứ tự phục hồi và lỗi setter quan trọng?

| Sự kiện | Cách xử lý |
| --- | --- |
| `rollback()` thành công | Transaction kết thúc; có thể phục hồi `autoCommit` và các thuộc tính đã thay đổi. |
| `commit()` thành công | Transaction kết thúc; có thể phục hồi trạng thái. |
| `rollback()` thất bại | Trạng thái transaction không rõ; **không** chuyển `autoCommit` sang `true` theo thói quen; phải loại bỏ kết nối nghi vấn. |
| Một setter phục hồi thất bại | Coi kết nối chưa được phục hồi đầy đủ; ghi nhận ngoại lệ và yêu cầu pool vô hiệu hóa theo cách tương ứng. |
| Kết nối đã bị hỏng | Việc gọi getter/setter có thể tiếp tục thất bại; tránh kỳ vọng mọi bước cleanup đều thành công. |
| Thành phần khác sở hữu transaction | Không tự `commit()`, `rollback()` hay khôi phục thuộc tính ngoài hợp đồng của bên sở hữu. |

## 6. Phân biệt việc của ứng dụng, transaction manager và connection pool

Ba thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm chính |
| --- | --- |
| **Mã JDBC trực tiếp** | Gán tham số, thực thi SQL, xác định phạm vi transaction mà nó sở hữu, đóng tài nguyên và phục hồi trạng thái nó sửa. |
| **Transaction manager** (nếu sử dụng) | Quyết định commit/rollback và ranh giới transaction cho nhiều lệnh hoặc repository. |
| **Connection pool** | Quản lý vòng đời kết nối vật lý, cho mượn/trả lại, kiểm tra hợp lệ và có thể reset một số thuộc tính hoặc loại bỏ kết nối lỗi. |

**Không để hai thành phần cùng tự ý sở hữu transaction.** Nếu ứng dụng đang dùng transaction manager của framework, một repository thường nhận kết nối gắn với transaction hiện tại, và **không được tự ý** gọi `setAutoCommit(true)`, `commit()` hoặc `rollback()`. Bài này áp dụng trực tiếp cho mã JDBC **tự quản lý transaction** và các trường hợp lập trình viên có trách nhiệm trả lại trạng thái kết nối mượn.

Khi pool hỗ trợ reset `autoCommit`, read-only, isolation hoặc schema, nên cấu hình và kiểm chứng tính năng đó như **lớp bảo vệ bổ sung**. Không giả định pool nào cũng reset mọi câu lệnh phiên SQL, role, biến session, bảng tạm hoặc đối tượng LOB. Nếu thuộc tính quan trọng không thể khôi phục, kết nối không nên được đưa trở lại phục vụ yêu cầu khác.

Một điểm dễ nhầm: `Connection.setReadOnly(true)` chỉ là gợi ý hoặc chế độ do cơ sở dữ liệu áp dụng tùy trường hợp; nó **không thay thế** quyền `SELECT`/`INSERT`/`UPDATE` ở hệ quản trị. Không dựa vào thuộc tính này để cách ly tenant hoặc thực thi phân quyền.

## 7. Các lỗi phổ biến khi trả kết nối

### Lỗi 1: Chỉ gọi `close()` sau một chuỗi cập nhật

```java
connection.setAutoCommit(false);
debit.executeUpdate();
credit.executeUpdate();
connection.close(); // Thiếu commit/rollback và phục hồi trạng thái.
```

Nếu `Connection` do pool cung cấp, hành vi khi đóng lúc có transaction đang mở phụ thuộc pool và driver. Cần kết thúc transaction rõ ràng trước khi trả lại kết nối.

### Lỗi 2: Phục hồi `autoCommit` trước khi rollback

```java
try {
    connection.setAutoCommit(false);
    update.executeUpdate();
} catch (SQLException error) {
    connection.setAutoCommit(true); // Có thể commit thao tác đã chạy.
    connection.rollback();           // Quá muộn.
}
```

Thứ tự cần là **rollback trước, sau đó mới phục hồi `autoCommit`** nếu rollback thành công.

### Lỗi 3: Làm mất lỗi gốc trong `finally`

```java
try {
    connection.setAutoCommit(false);
    // Thực thi SQL có thể ném SQLException.
} finally {
    connection.setAutoCommit(true); // Nếu câu này lỗi, có thể che lỗi SQL gốc.
}
```

Khi rollback hoặc phục hồi cũng ném lỗi, ứng dụng nên lưu lỗi bổ sung bằng `Throwable.addSuppressed(...)` hoặc cơ chế tổng hợp lỗi tương đương. `try-with-resources` tự động gắn một số lỗi `close()` thành suppressed exception nếu đã có lỗi chính, nhưng **không tự xử lý** những ngoại lệ phát sinh bên trong `finally` do ta viết.

### Lỗi 4: Thay schema mà quên trả lại

```java
connection.setSchema("tenant_a");
// ... query ...
// Quên khôi phục schema hoặc hủy kết nối nếu không thể phục hồi.
```

Yêu cầu sau có thể chạy câu SQL không ghi rõ tên schema dưới phạm vi khác. Trong hệ thống nhiều tenant, đây là lỗi nghiêm trọng. Lưu schema ban đầu, khôi phục khi transaction đã kết thúc và kiểm tra chính sách reset/eviction của pool.

### Lỗi 5: Tự commit khi đang tham gia transaction của bên gọi

Một phương thức repository nhận `Connection` từ tầng nghiệp vụ không nên tự gọi `commit()` nếu bên gọi đang gộp nhiều repository trong một transaction. Thông thường quy định rõ hợp đồng: **phương thức tự mượn kết nối thì tự quản lý** transaction của nó, còn phương thức **nhận kết nối do bên ngoài sở hữu** thì để bên ngoài quyết định ranh giới transaction.

## 8. Thực hành kiểm chứng với connection pool

Có thể tự xây dựng kịch bản nhỏ trên cơ sở dữ liệu thử nghiệm:

1. Tạo bảng `accounts(id, balance)` và dùng `DataSource` có pool, cấu hình số kết nối nhỏ để dễ quan sát việc tái sử dụng.
2. Đọc `getAutoCommit()` trước khi chạy nghiệp vụ; thử transaction thành công với hai `UPDATE`, kiểm tra cả hai thay đổi đã commit.
3. Chủ động làm câu `UPDATE` thứ hai thất bại; xác nhận sau `rollback()`, số dư của cả hai tài khoản không đổi và trạng thái `autoCommit` được phục hồi trước khi `close()`.
4. Mượn kết nối ở lượt tiếp theo và xem `getAutoCommit()`, `isReadOnly()`, `getTransactionIsolation()`; không suy diễn rằng đó là **cùng một kết nối vật lý** nếu pool không cung cấp bằng chứng.
5. Thử đổi read-only hoặc isolation trong một scope độc lập, sau đó phục hồi. Quan sát hành vi bằng driver và pool thực tế; không đổi thuộc tính trong transaction đang mở nếu driver không cho phép.
6. Mô phỏng lỗi rollback hoặc mất kết nối trong môi trường thử nghiệm và kiểm tra cơ chế pool dùng để loại bỏ kết nối không rõ trạng thái. Không gây lỗi cố ý trên kết nối chứa dữ liệu quan trọng.

Các tình huống cần kiểm tra:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Hai lệnh `UPDATE` thành công | `commit()` được gọi; số dư cập nhật; `autoCommit` được phục hồi. |
| Lệnh thứ hai lỗi | `rollback()` được gọi; không ghi một nửa giao dịch; trạng thái được phục hồi khi rollback thành công. |
| Lỗi xảy ra ngay khi bắt đầu transaction | Báo lỗi; không giả định trạng thái kết nối đã sạch nếu setter thay đổi dở dang. |
| Phục hồi `autoCommit` thất bại | Lỗi không bị nuốt; kết nối được coi là nghi vấn và cần bị loại bỏ theo cơ chế pool. |
| `rollback()` thất bại | Không gọi `setAutoCommit(true)` chỉ để dọn dẹp; điều tra kết quả giao dịch và loại bỏ kết nối nghi vấn. |
| Repository nhận kết nối từ transaction manager | Repository không thay đổi quyền sở hữu transaction của bên gọi. |

## 9. Checklist cho phương thức JDBC tự quản lý transaction

- Xác định rõ **ai sở hữu kết nối và ai sở hữu transaction** trước khi gọi `setAutoCommit(false)`.
- Ghi nhận giá trị ban đầu của những thuộc tính sẽ sửa, đặc biệt `autoCommit`.
- Dùng **cùng một `Connection`** cho mọi lệnh SQL thuộc transaction.
- Khi hoàn thành, gọi `commit()`; khi có lỗi, cố gắng `rollback()` và giữ lỗi chính cùng lỗi dọn dẹp bổ sung.
- Chỉ khôi phục `autoCommit` và các thiết lập khác sau khi transaction đã kết thúc; không commit ngầm trong cleanup.
- Nếu rollback hoặc phục hồi trạng thái thất bại, đánh dấu kết nối không an toàn để tái sử dụng và xử lý theo khả năng của pool.
- Đóng `ResultSet`, `PreparedStatement` và kết nối bằng `try-with-resources`; không dùng kết nối sau khi đã trả quyền sử dụng.

**Ghi nhớ:** với JDBC, `close()` là bước trả tài nguyên, còn **kết thúc transaction và khôi phục trạng thái** là những trách nhiệm riêng. Một phương thức đáng tin cậy phải biết mình đã thay đổi những gì, kết thúc thành công hoặc hoàn tác giao dịch trước khi phục hồi, và không đưa kết nối có trạng thái không rõ ràng trở lại phục vụ yêu cầu tiếp theo.
