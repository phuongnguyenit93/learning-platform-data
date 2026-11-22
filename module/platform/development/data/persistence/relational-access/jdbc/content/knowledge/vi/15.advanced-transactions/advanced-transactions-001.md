# Tạo savepoint có tên và không có tên trong JDBC

Khi xử lý một giao dịch JDBC, đôi khi ứng dụng cần giữ lại những thao tác đã thành công nhưng hủy một phần thao tác phát sinh sau đó. **Savepoint** (điểm lưu trong giao dịch) cho phép đặt một mốc để `rollback` về mốc đó mà chưa hủy toàn bộ giao dịch. JDBC cung cấp hai cách tạo mốc: **có tên** và **không có tên**.

Bài học thuộc chương **Giao dịch nâng cao** của **JDBC (Java Database Connectivity)**, API Java dùng để truy cập cơ sở dữ liệu quan hệ. Trọng tâm là cách quản lý savepoint thông qua `java.sql.Connection` và `java.sql.Savepoint`, ý nghĩa của mỗi cách đặt mốc, và cách xử lý lỗi an toàn.

## 1. Savepoint giải quyết vấn đề gì?

Giả sử một đơn hàng có ba thao tác trong cùng giao dịch:

1. Tạo đơn hàng — bắt buộc thành công.
2. Lưu ghi chú giao hàng — có thể bỏ qua nếu dữ liệu ghi chú không hợp lệ **và nghiệp vụ cho phép**.
3. Ghi sự kiện tạo đơn — bắt buộc thành công.

Nếu đặt savepoint ngay sau thao tác 1, khi thao tác 2 gặp lỗi, ta có thể quay về mốc đó, bỏ những thay đổi của thao tác 2 rồi tiếp tục thao tác 3. Cuối cùng, `commit()` sẽ ghi nhận các thay đổi còn lại.

```text
BEGIN TRANSACTION       (connection.setAutoCommit(false))
    |
    +-- Tạo đơn hàng             [thành công]
    |
    +-- SAVEPOINT before_note   [đặt mốc]
    |
    +-- Lưu ghi chú             [thất bại]
    |
    +-- ROLLBACK TO before_note [chỉ hủy thay đổi sau mốc]
    |
    +-- Ghi sự kiện đơn hàng    [thành công]
    |
    +-- COMMIT                  [lưu đơn hàng + sự kiện]
```

Khác với `Connection.rollback()` (hủy toàn bộ phần việc chưa commit của giao dịch), `Connection.rollback(savepoint)` chỉ yêu cầu cơ sở dữ liệu hoàn tác đến mốc được chỉ định.

> **Lưu ý:** Savepoint không tạo một giao dịch độc lập và không phải một lệnh commit từng phần. Tất cả thay đổi còn lại chỉ thực sự được xác nhận khi giao dịch ngoài gọi `commit()`.

## 2. Điều kiện cần trước khi tạo savepoint

Savepoint hoạt động trong **giao dịch được quản lý thủ công**. Trước khi tạo, cần tắt chế độ tự động commit:

```java
connection.setAutoCommit(false);
```

Với kết nối JDBC ở `autoCommit = true`, từng câu SQL thường được commit ngay khi hoàn tất; gọi `setSavepoint()` trong chế độ này sẽ phát sinh `SQLException` theo hợp đồng JDBC. Ngoài ra, không phải mọi hệ quản trị hoặc driver đều hỗ trợ savepoint.

Có thể kiểm tra khả năng hỗ trợ qua metadata:

```java
boolean supported = connection.getMetaData().supportsSavepoints();
if (!supported) {
    throw new IllegalStateException("Driver/database không hỗ trợ savepoint");
}
```

Trong ứng dụng sử dụng Spring, JTA hoặc framework quản lý transaction, việc tạo và rollback savepoint còn phải tuân theo quyền sở hữu giao dịch của framework. Không nên tự ý đổi `autoCommit` hay gọi `commit()` trên một kết nối đang được transaction manager quản lý.

## 3. Hai cách tạo savepoint

JDBC biểu diễn cả hai loại bằng interface `java.sql.Savepoint`; cách tạo mốc là điểm khác nhau.

### 3.1. Savepoint không có tên

Gọi `Connection.setSavepoint()` **không truyền tham số**:

```java
import java.sql.Savepoint;

Savepoint checkpoint = connection.setSavepoint();

// Có thể lấy ID do driver/database gán cho savepoint không tên.
int id = checkpoint.getSavepointId();

// Khi cần, hoàn tác đến checkpoint.
connection.rollback(checkpoint);
```

Ứng dụng giữ đối tượng `Savepoint` trả về để tham chiếu mốc. Với savepoint không tên, `getSavepointId()` trả về ID của mốc; **không** gọi `getSavepointName()` vì phương thức đó phát sinh `SQLException` cho savepoint không tên.

Cách này phù hợp khi chỉ cần một mốc nội bộ, không có yêu cầu thể hiện tên mốc trong mã nguồn hoặc thông tin chẩn đoán.

### 3.2. Savepoint có tên

Gọi `Connection.setSavepoint(String name)` và đặt tên thể hiện ý nghĩa nghiệp vụ:

```java
import java.sql.Savepoint;

Savepoint beforeOptionalNote = connection.setSavepoint("before_optional_note");

// Với savepoint có tên, tên có thể được lấy lại từ đối tượng.
String name = beforeOptionalNote.getSavepointName();

// Hoàn tác các thay đổi xảy ra sau mốc này.
connection.rollback(beforeOptionalNote);
```

Với savepoint có tên, dùng `getSavepointName()`; **không** gọi `getSavepointId()` vì phương thức đó phát sinh `SQLException` cho savepoint có tên. Tên nên ngắn, rõ nghĩa và tương thích quy tắc định danh của cơ sở dữ liệu/driver. Tránh tự ý dùng lại một tên trong cùng giao dịch vì cách xử lý tên trùng có thể khác nhau giữa các hệ quản trị.

Quan trọng: dù savepoint được đặt tên, lời gọi rollback của JDBC vẫn nhận **đối tượng `Savepoint`**, không nhận chuỗi tên:

```java
connection.rollback(beforeOptionalNote); // Đúng
// connection.rollback("before_optional_note"); // Không có overload này
```

### 3.3. So sánh nhanh

| Tiêu chí | Không có tên | Có tên |
|---|---|---|
| Cách tạo | `connection.setSavepoint()` | `connection.setSavepoint("before_note")` |
| Giá trị trả về | `Savepoint` | `Savepoint` |
| Thuộc tính có thể lấy | `getSavepointId()` | `getSavepointName()` |
| Cách rollback | `connection.rollback(savepoint)` | `connection.rollback(savepoint)` |
| Trường hợp phù hợp | Mốc tạm, phạm vi nhỏ | Mốc có ý nghĩa nghiệp vụ, dễ đọc mã |

**Hai cách có cùng khả năng rollback**. Tên chỉ giúp định danh và diễn đạt mục đích; nó không làm savepoint bền vững hơn hay tạo thêm mức cô lập giao dịch.

## 4. Ví dụ thực tế: tạo đơn hàng với bước ghi chú tùy chọn

Giả sử cơ sở dữ liệu đã có các bảng `purchase_orders(id, status)`, `order_notes(order_id, note)` và `order_events(order_id, event_name)`. Ví dụ dùng `DataSource` để lấy kết nối và `PreparedStatement` để truyền tham số an toàn.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Savepoint;
import java.sql.SQLException;

public final class OrderSavepointExample {

    public static void createOrder(DataSource dataSource, long orderId, String note)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();

            try {
                connection.setAutoCommit(false);

                try {
                    // (1) Thao tác bắt buộc: tạo đơn hàng.
                    try (PreparedStatement statement = connection.prepareStatement(
                            "INSERT INTO purchase_orders (id, status) VALUES (?, 'CREATED')")) {
                        statement.setLong(1, orderId);
                        statement.executeUpdate();
                    }

                    // (2) Savepoint CÓ TÊN trước thao tác tùy chọn.
                    Savepoint beforeNote = connection.setSavepoint("before_optional_note");

                    try (PreparedStatement statement = connection.prepareStatement(
                            "INSERT INTO order_notes (order_id, note) VALUES (?, ?)")) {
                        statement.setLong(1, orderId);
                        statement.setString(2, note);
                        statement.executeUpdate();
                    } catch (SQLException noteError) {
                        // Chỉ tiếp tục nếu quy tắc nghiệp vụ cho phép bỏ qua ghi chú.
                        connection.rollback(beforeNote);
                        System.err.println("Bỏ qua ghi chú: " + noteError.getMessage());
                    }

                    // (3) Thao tác bắt buộc tiếp theo.
                    try (PreparedStatement statement = connection.prepareStatement(
                            "INSERT INTO order_events (order_id, event_name) VALUES (?, 'CREATED')")) {
                        statement.setLong(1, orderId);
                        statement.executeUpdate();
                    }

                    // Xác nhận tất cả thay đổi còn lại của giao dịch.
                    connection.commit();
                } catch (SQLException | RuntimeException error) {
                    // Lỗi ngoài nhánh tùy chọn: rollback toàn bộ giao dịch.
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }
                    throw error;
                }
            } finally {
                // Trả lại cấu hình ban đầu, hữu ích khi dùng connection pool.
                connection.setAutoCommit(originalAutoCommit);
            }
        }
    }
}
```

**Diễn giải luồng chạy:**

- Ghi chú thành công: cả ba câu lệnh `INSERT` được commit cùng nhau.
- Ghi chú thất bại và được nghiệp vụ cho phép bỏ qua: rollback đến `before_optional_note`, giữ phần tạo đơn hàng và vẫn thử ghi sự kiện. Nếu sự kiện thành công, `commit()` ghi đơn hàng và sự kiện, không ghi ghi chú.
- Tạo đơn hàng hoặc ghi sự kiện thất bại: nhánh xử lý lỗi ngoài gọi `rollback()` không tham số để hủy toàn bộ giao dịch.

Ví dụ minh họa cơ chế savepoint; nhánh bỏ qua ghi chú cần được giới hạn cho **những lỗi đã được nghiệp vụ chấp nhận**. Trong ứng dụng thực tế nên phân loại lỗi theo SQLState/mã lỗi phù hợp với DBMS, ghi log qua hệ thống logging và ném lại các lỗi không dự kiến. Không được bỏ qua lỗi của thao tác bắt buộc chỉ vì đã có savepoint.

Để dùng **savepoint không tên** trong cùng ví dụ, thay đúng lời gọi tạo mốc:

```java
Savepoint beforeNote = connection.setSavepoint();
// Các lời gọi rollback(beforeNote), commit() và xử lý lỗi giữ nguyên.
```

`DataSource`, kết nối và các bảng dữ liệu là các phụ thuộc giả định của ví dụ; bạn cần cấu hình JDBC URL, driver và schema phù hợp trước khi chạy.

## 5. Nhiều savepoint trong cùng giao dịch

Có thể tạo nhiều mốc liên tiếp để lựa chọn mức hoàn tác:

```java
connection.setAutoCommit(false);

// Thao tác A đã hoàn tất.
Savepoint afterA = connection.setSavepoint("after_A");

// Thao tác B đã hoàn tất.
Savepoint afterB = connection.setSavepoint();

// Thao tác C đã hoàn tất.
connection.rollback(afterB); // Hủy C, giữ A và B.

// Giả sử sau đó cần hủy thêm B:
connection.rollback(afterA); // Hủy B, giữ A.

connection.commit();         // Chỉ xác nhận A.
```

Các dòng “thao tác A/B/C” là vị trí giả định cho các câu SQL. Chúng minh họa thứ tự thay đổi, không phải câu lệnh Java có thể chạy độc lập.

Thông thường, khi rollback về một savepoint cũ, những savepoint được tạo **sau** mốc đó cũng không còn hợp lệ; vì vậy sau `rollback(afterA)` không nên tiếp tục sử dụng `afterB`. Tùy hệ quản trị, các thay đổi như DDL có thể có quy tắc giao dịch riêng, nên cần kiểm tra đặc tính DBMS mục tiêu.

Khi mốc không còn cần thiết, JDBC còn cung cấp:

```java
connection.releaseSavepoint(afterA);
```

`releaseSavepoint` giải phóng mốc để không thể rollback về mốc ấy nữa; **nó không commit dữ liệu**. Một số driver hoặc DBMS có thể không hỗ trợ thao tác giải phóng và trả về `SQLException`/`SQLFeatureNotSupportedException`. Trong ví dụ trên, lệnh release chỉ nên gọi khi `afterA` vẫn hợp lệ và giao dịch còn mở.

## 6. Vòng đời và các lỗi cần tránh

| Tình huống | Ảnh hưởng / cách xử lý |
|---|---|
| `autoCommit = true` khi đặt mốc | Không có giao dịch thủ công phù hợp; `setSavepoint` có thể ném `SQLException`. Hãy tắt auto-commit trước. |
| Driver/database không hỗ trợ | Kiểm tra `supportsSavepoints()`; có phương án thay thế như rollback toàn bộ và thực hiện lại transaction. |
| Gọi `getSavepointName()` trên mốc không tên | `SQLException`; thay bằng `getSavepointId()`. |
| Gọi `getSavepointId()` trên mốc có tên | `SQLException`; thay bằng `getSavepointName()`. |
| Gọi `rollback()` không tham số | Hoàn tác toàn bộ giao dịch hiện tại, không chỉ đến savepoint. |
| `commit()` hoặc rollback toàn bộ xong | Savepoint của giao dịch cũ hết hiệu lực; phải tạo mốc mới trong giao dịch mới. |
| Dùng savepoint đã release hoặc đã bị vô hiệu hóa | Có thể nhận `SQLException`; không giữ đối tượng `Savepoint` để tái sử dụng qua các transaction. |
| Hai luồng dùng chung `Connection` | Trạng thái transaction/savepoint có thể bị can thiệp lẫn nhau; không chia sẻ một kết nối đang giao dịch giữa các luồng. |
| Chỉ rollback đến mốc rồi quên `commit()` | Không có đảm bảo thay đổi còn lại được lưu; vẫn cần `commit()` hoặc `rollback()` toàn bộ ở điểm kết thúc giao dịch. |

Ngoài ra, **savepoint không thay thế cơ chế đồng thời**: mức cô lập (`TRANSACTION_READ_COMMITTED`, `TRANSACTION_REPEATABLE_READ`, v.v.), khóa và nguy cơ deadlock vẫn do cơ sở dữ liệu quản lý. Rollback đến savepoint có thể ảnh hưởng đến khóa tùy DBMS; không nên giả định mọi khóa sau mốc đều được giải phóng giống nhau trên mọi hệ.

## 7. Cách chọn loại savepoint và thực hành tốt

**Chọn không tên** khi muốn đánh dấu một vị trí phục hồi ngắn trong khối mã nhỏ, chẳng hạn trước một thao tác import phụ. Dùng **có tên** khi có nhiều mốc, luồng nghiệp vụ phức tạp hoặc cần tên rõ ràng để đọc log và code review. Cả hai loại đều nên được giữ bằng biến `Savepoint` và sử dụng trong phạm vi giao dịch đã tạo ra chúng.

Khi triển khai, nên nhớ bốn nguyên tắc:

1. **Ranh giới transaction rõ ràng:** cùng một `Connection`, `setAutoCommit(false)` trước khi đặt mốc, `commit()` ở đường thành công và `rollback()` toàn bộ ở đường lỗi bắt buộc.
2. **Rollback có chủ đích:** chỉ tiếp tục sau `rollback(savepoint)` nếu thao tác vừa thất bại là tùy chọn theo quy tắc nghiệp vụ; xử lý lỗi kỹ thuật không mong đợi bằng cách ném lại.
3. **Dọn tài nguyên đúng cách:** dùng `try-with-resources` cho `Connection`, `PreparedStatement`; nếu phục hồi `autoCommit` thì làm sau khi giao dịch đã kết thúc.
4. **Kiểm thử trên DBMS thật:** xác nhận driver hỗ trợ savepoint, phản ứng khi SQL lỗi, hiệu lực của các mốc sau rollback và hành vi `releaseSavepoint()`.

## 8. Tự kiểm tra kiến thức

**Câu 1.** Một transaction có A → savepoint S → B → C. Khi gọi `rollback(S)` rồi `commit()`, thao tác nào còn hiệu lực?  
**Đáp án:** A; B và C bị hoàn tác (giả sử toàn bộ là các thao tác có thể rollback trong DBMS đó).

**Câu 2.** Phương thức nào tạo savepoint không tên?  
**Đáp án:** `Connection.setSavepoint()`.

**Câu 3.** Savepoint có tên `after_import` có cho phép gọi `connection.rollback("after_import")` không?  
**Đáp án:** Không. JDBC dùng `connection.rollback(savepointObject)`, trong đó đối tượng được nhận từ `setSavepoint("after_import")`.

**Câu 4.** Sau khi `releaseSavepoint(s)`, dữ liệu trước mốc có được commit ngay không?  
**Đáp án:** Không. `releaseSavepoint` chỉ giải phóng mốc, còn `commit()` xác nhận transaction.

**Câu 5.** Vì sao không nên nuốt mọi `SQLException` khi rollback về mốc?  
**Đáp án:** Một lỗi kết nối, lỗi schema hoặc lỗi nghiệp vụ bắt buộc có thể khiến giao dịch không còn an toàn để tiếp tục; chỉ những lỗi tùy chọn đã được định nghĩa trước mới có thể bỏ qua sau khi phục hồi thành công.

Savepoint giúp điều khiển **phạm vi hoàn tác bên trong một transaction**. Điểm cốt lõi khi dùng JDBC là đặt mốc đúng lúc, giữ đúng đối tượng `Savepoint`, chọn rollback một phần hay toàn phần theo nghiệp vụ và vẫn kết thúc giao dịch bằng `commit()` hoặc `rollback()` phù hợp.
