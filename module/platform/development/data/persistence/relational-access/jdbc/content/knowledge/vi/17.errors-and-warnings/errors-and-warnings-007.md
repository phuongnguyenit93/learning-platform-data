# Xử lý BatchUpdateException cùng số đếm từng lệnh

Trong **JDBC**, thực thi nhiều thao tác ghi theo lô (*batch*) giúp giảm số lần trao đổi giữa ứng dụng Java và cơ sở dữ liệu quan hệ. Thay vì gọi `executeUpdate()` cho từng câu lệnh, ứng dụng đưa nhiều bộ tham số vào `PreparedStatement.addBatch()` rồi gọi `executeBatch()`. Tuy nhiên, khi một lệnh giữa lô thất bại, ứng dụng phải biết **lệnh nào đã được xử lý, lệnh nào thất bại, có thể kết luận gì từ số đếm trả về, và nên kết thúc transaction ra sao**.

Trong chương **Lỗi và cảnh báo**, bài này đi sâu vào `java.sql.BatchUpdateException`, một lớp con của `SQLException`. Trọng tâm là `getUpdateCounts()`, hai mã đặc biệt `Statement.SUCCESS_NO_INFO` và `Statement.EXECUTE_FAILED`, sự khác biệt giữa các driver khi gặp lỗi, cùng cách rollback và ghi nhận thông tin chẩn đoán. Các ví dụ sử dụng `DataSource`, `Connection`, `PreparedStatement`, SQL tham số hóa và các API JDBC chuẩn.

## 1. Vì sao số đếm của batch cần được xử lý riêng?

Một lô gồm bốn yêu cầu cập nhật tồn kho có thể trông như sau:

| Vị trí trong batch (chỉ số Java) | Yêu cầu | Kết quả mong đợi |
| ---: | --- | --- |
| `0` | Trừ 2 sản phẩm khỏi kho mã `101` | Cập nhật 1 hàng |
| `1` | Trừ 1 sản phẩm khỏi kho mã `102` | Cập nhật 1 hàng |
| `2` | Trừ 5 sản phẩm khỏi kho mã `103` | Có thể lỗi hoặc không đủ hàng |
| `3` | Trừ 1 sản phẩm khỏi kho mã `104` | Cập nhật 1 hàng |

Nếu mọi lệnh hoàn tất, `executeBatch()` trả về một mảng `int[]` theo **thứ tự các lệnh đã thêm bằng `addBatch()`**. Với driver có thể đếm số hàng, kết quả minh họa là:

```java
int[] updateCounts = {1, 1, 1, 1};
```

Nếu một lệnh thất bại, `executeBatch()` có thể ném `BatchUpdateException`. Khác với `executeUpdate()` chỉ trả về một số đếm, ngoại lệ này cung cấp **thông tin số đếm của các phần tử trong lô** để ứng dụng phân tích.

**Cần tách ba khái niệm:** (1) driver báo câu lệnh đã được thực thi hay thất bại, (2) số hàng bị tác động, và (3) giao dịch đã `commit` hay chưa. Một lệnh có số đếm `1` **chưa chắc đã được commit**; ngược lại, một lệnh `UPDATE` hợp lệ có thể tác động `0` hàng vì `WHERE` không khớp, dù không xảy ra lỗi SQL.

## 2. Cách bắt ngoại lệ và lấy số đếm

`BatchUpdateException` kế thừa `SQLException` nên có thể đọc `SQLState`, mã lỗi riêng của DBMS và chuỗi ngoại lệ tiếp theo. Đặc biệt, nó cung cấp:

| API | Ý nghĩa |
| --- | --- |
| `BatchUpdateException.getUpdateCounts()` | Mảng `int[]` ghi kết quả của những lệnh trong batch theo thông tin driver cung cấp khi lỗi xảy ra. |
| `BatchUpdateException.getLargeUpdateCounts()` | Mảng `long[]` dành cho trường hợp cần số đếm lớn; thường dùng cùng `executeLargeBatch()` khi driver hỗ trợ. |
| `SQLException.getSQLState()` | Mã trạng thái SQL, hữu ích để phân loại lỗi theo chuẩn và đặc thù DBMS. |
| `SQLException.getErrorCode()` | Mã lỗi vendor-specific, nếu driver cung cấp. |
| `SQLException.getNextException()` | Ngoại lệ SQL tiếp theo trong chuỗi do driver tạo, có thể chứa nguyên nhân chi tiết của phần tử thất bại. |

Ví dụ tối thiểu:

```java
import java.sql.BatchUpdateException;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;

try {
    int[] counts = statement.executeBatch();
    // Dùng counts để kiểm tra các điều kiện nghiệp vụ.
} catch (BatchUpdateException failure) {
    int[] partialCounts = failure.getUpdateCounts();

    System.err.println("SQLState: " + failure.getSQLState());
    System.err.println("Mã lỗi DBMS: " + failure.getErrorCode());
    System.err.println("Số kết quả đã báo: "
            + (partialCounts == null ? 0 : partialCounts.length));

    // Lệnh rollback thuộc về phần quản lý Connection/transaction.
    throw failure;
}
```

Trong đoạn mã trên, `statement` là `PreparedStatement` đã được tạo và nạp batch từ trước. Đoạn mã chỉ minh họa nhánh bắt lỗi; phần quản lý transaction hoàn chỉnh nằm ở mục 5. Khi phân loại lỗi, **bắt `BatchUpdateException` trước `SQLException`** vì đây là kiểu con của `SQLException`.

## 3. Cách diễn giải từng phần tử của getUpdateCounts()

Một phần tử của mảng kết quả có những giá trị quan trọng sau:

| Giá trị | Ý nghĩa theo JDBC | Cách diễn giải an toàn |
| --- | --- | --- |
| `0` | Lệnh đã thực thi nhưng không có hàng nào bị tác động (đối với thao tác cập nhật). | Không mặc nhiên là lỗi SQL; có thể là `WHERE` không khớp. Xem quy tắc nghiệp vụ có đòi 1 hàng hay không. |
| `1`, `2`, … | Số hàng bị tác động mà driver báo. | Có thể dùng kiểm tra số hàng mong đợi; chưa đồng nghĩa `commit`. |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Lệnh đã thực thi thành công nhưng driver không cho biết số hàng. | Không được coi là `0` hoặc `1`; nếu bắt buộc biết chính xác 1 hàng thì không đủ thông tin để xác nhận. |
| `Statement.EXECUTE_FAILED` (`-3`) | Lệnh thất bại, có thể xuất hiện trong mảng của ngoại lệ khi driver tiếp tục xử lý sau lỗi. | Đánh dấu thất bại tại đúng vị trí; không tính là thành công. |

Ví dụ khi kiểm tra từng giá trị:

```java
import java.sql.Statement;

static String describeCount(int count) {
    if (count == Statement.SUCCESS_NO_INFO) {
        return "Thành công, không rõ số hàng";
    }
    if (count == Statement.EXECUTE_FAILED) {
        return "Thất bại";
    }
    if (count >= 0) {
        return "Đã tác động " + count + " hàng";
    }
    return "Giá trị không nhận diện: " + count;
}
```

**Không cộng thẳng mọi phần tử trong mảng** để tính tổng số hàng: nếu có `-2` hoặc `-3`, phép cộng cho ra số vô nghĩa. Chỉ cộng các số không âm, đồng thời ghi riêng số lệnh thành công không rõ số hàng, số lệnh thất bại và số vị trí chưa có kết quả.

### Khi driver dừng ngay hoặc tiếp tục sau lỗi

Đặc tả JDBC cho phép driver có hai cách xử lý khi một lệnh trong batch thất bại:

**Trường hợp A — dừng ở lệnh lỗi:** Nếu lệnh có chỉ số `2` là lệnh thất bại, mảng có thể chỉ chứa kết quả của các lệnh trước đó:

```java
int[] partialCounts = {1, 1};
```

Ở trường hợp này, `partialCounts.length == 2`. Lệnh tại vị trí `2` đã gây lỗi; lệnh tại vị trí `3` không có kết quả được báo trong mảng. **Không tự động xem các vị trí thiếu trong mảng là đã thành công hay đã commit**.

**Trường hợp B — tiếp tục sau lệnh lỗi:** Driver tiếp tục xử lý các lệnh còn lại và cung cấp một phần tử cho mỗi lệnh:

```java
int[] partialCounts = {
    1, 1, Statement.EXECUTE_FAILED, 1
};
```

Ở trường hợp này, phần tử `2` ghi rõ thất bại, phần tử `3` báo kết quả xử lý tiếp theo. Tuy nhiên, nhiều DBMS có cơ chế khiến toàn transaction bị đánh dấu lỗi sau một câu SQL thất bại; **không suy diễn từ mảng số đếm rằng mọi lệnh được báo thành công sẽ tồn tại trong DB sau khi kết thúc transaction**.

Khi driver tiếp tục sau lỗi, `getUpdateCounts()` có số phần tử tương ứng toàn bộ lệnh trong batch và đánh dấu những lệnh thất bại bằng `EXECUTE_FAILED`. Khi driver dừng ở lỗi đầu tiên, mảng thường chỉ phản ánh những lệnh thành công trước đó. Vì vậy **không viết logic phụ thuộc vào giả định mọi driver luôn chọn cùng một cách**.

## 4. Ghép số đếm với đúng lệnh và tham số

Thứ tự các phần tử trong `getUpdateCounts()` khớp với thứ tự các lần `addBatch()` được thêm vào `Statement` hoặc `PreparedStatement`. Các giá trị trong mảng được truy cập bằng **chỉ số bắt đầu từ 0**, khác với chỉ số tham số `?` trong `PreparedStatement.setXxx(...)` bắt đầu từ **1**.

```java
String sql = "UPDATE inventory "
           + "SET available = available - ? "
           + "WHERE product_id = ? AND available >= ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    // Batch phần tử số 0: trừ 2 sản phẩm mã 101.
    ps.setInt(1, 2);
    ps.setLong(2, 101L);
    ps.setInt(3, 2);
    ps.addBatch();

    // Batch phần tử số 1: trừ 1 sản phẩm mã 102.
    ps.setInt(1, 1);
    ps.setLong(2, 102L);
    ps.setInt(3, 1);
    ps.addBatch();

    int[] counts = ps.executeBatch();
    // counts[0] phản ánh yêu cầu mã 101, counts[1] phản ánh mã 102.
}
```

Cần giữ một danh sách dữ liệu đầu vào **cùng thứ tự** với các lần `addBatch()` nếu muốn báo “yêu cầu thứ 3 có vấn đề”. Dùng chỉ số để truy ra **mã yêu cầu nội bộ hoặc mã sản phẩm** khi ghi log, tránh ghi toàn bộ câu SQL đã nội suy tham số, mật khẩu, thông tin thanh toán hoặc dữ liệu cá nhân vào log.

Nếu batch có câu SQL với điều kiện `available >= ?`, một số đếm `0` có thể là tín hiệu nghiệp vụ “không đủ hàng” hoặc “không tồn tại sản phẩm”, **không phải `BatchUpdateException`**. Do vậy, ngay cả khi `executeBatch()` trả về bình thường, vẫn phải xem `counts[i]` có đáp ứng điều kiện nghiệp vụ hay không.

## 5. Ví dụ hoàn chỉnh: rollback toàn bộ batch khi có lỗi

Giả sử cơ sở dữ liệu có bảng:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
```

Ứng dụng muốn trừ hàng tồn theo nhiều yêu cầu, nhưng **chỉ chấp nhận khi mỗi yêu cầu cập nhật chính xác một hàng**. Nếu một lệnh vi phạm ràng buộc SQL, không khớp điều kiện, hoặc driver không cung cấp đủ số đếm để xác minh, toàn bộ giao dịch phải `rollback`.

```java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class InventoryBatchService {
    private final DataSource dataSource;

    public InventoryBatchService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void reserve(List<Reservation> requests) throws SQLException {
        Objects.requireNonNull(requests, "requests");
        if (requests.isEmpty()) {
            return;
        }
        // Kiểm tra đầu vào trước khi mượn Connection.
        for (Reservation request : requests) {
            Objects.requireNonNull(request, "Phần tử batch không được null");
            if (request.productId <= 0 || request.quantity <= 0) {
                throw new IllegalArgumentException("Mã hoặc số lượng không hợp lệ");
            }
        }

        String sql = "UPDATE inventory "
                   + "SET available = available - ? "
                   + "WHERE product_id = ? AND available >= ?";

        try (Connection connection = dataSource.getConnection()) {
            // Ví dụ này sở hữu transaction và kỳ vọng pool trả autoCommit=true.
            if (!connection.getAutoCommit()) {
                throw new SQLException("Ví dụ yêu cầu autoCommit=true lúc bắt đầu");
            }
            connection.setAutoCommit(false);

            boolean transactionEnded = false;
            Throwable originalFailure = null;
            try {
                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {
                    for (Reservation request : requests) {
                        statement.setInt(1, request.quantity);
                        statement.setLong(2, request.productId);
                        statement.setInt(3, request.quantity);
                        statement.addBatch();
                    }

                    int[] counts = statement.executeBatch();
                    if (counts.length != requests.size()) {
                        throw new SQLException("Thiếu số đếm cho batch");
                    }
                    for (int i = 0; i < counts.length; i++) {
                        // Yêu cầu nghiệp vụ: phải biết chắc đúng 1 hàng.
                        // SUCCESS_NO_INFO (-2) không đủ để xác nhận điều này.
                        if (counts[i] != 1) {
                            throw new SQLException(
                                    "Lệnh batch vị trí " + i
                                    + " không cập nhật đúng 1 hàng: " + counts[i]);
                        }
                    }
                }

                connection.commit();
                transactionEnded = true;
            } catch (BatchUpdateException failure) {
                originalFailure = failure;
                reportBatchFailure(failure, requests.size());
                transactionEnded = rollbackPreserving(connection, failure);
                throw failure;
            } catch (SQLException | RuntimeException failure) {
                originalFailure = failure;
                transactionEnded = rollbackPreserving(connection, failure);
                throw failure;
            } finally {
                if (transactionEnded) {
                    // Chỉ đổi về true sau khi đã kết thúc giao dịch.
                    try {
                        connection.setAutoCommit(true);
                    } catch (SQLException resetError) {
                        if (originalFailure != null) {
                            originalFailure.addSuppressed(resetError);
                        } else {
                            throw resetError;
                        }
                    }
                }
                // Nếu commit/rollback không xác nhận được trạng thái,
                // không ép autoCommit=true; pool phải quản lý kết nối lỗi.
            }
        }
    }

    private static boolean rollbackPreserving(
            Connection connection, Throwable failure) {
        try {
            connection.rollback();
            return true;
        } catch (SQLException rollbackError) {
            failure.addSuppressed(rollbackError);
            return false;
        }
    }

    private static void reportBatchFailure(
            BatchUpdateException failure, int batchSize) {
        int[] counts = failure.getUpdateCounts();
        int available = (counts == null) ? 0 : counts.length;
        System.err.println("Batch thất bại, SQLState="
                + failure.getSQLState()
                + ", vendorCode=" + failure.getErrorCode());

        for (int i = 0; i < batchSize; i++) {
            String result;
            if (i >= available) {
                result = "Không có số đếm; cần xem ngữ cảnh lỗi";
            } else if (counts[i] == Statement.SUCCESS_NO_INFO) {
                result = "Thành công, không rõ số hàng";
            } else if (counts[i] == Statement.EXECUTE_FAILED) {
                result = "Thất bại";
            } else if (counts[i] >= 0) {
                result = "Số hàng: " + counts[i];
            } else {
                result = "Mã không nhận diện: " + counts[i];
            }
            System.err.println("Batch[" + i + "]: " + result);
        }
    }

    public static final class Reservation {
        public final long productId;
        public final int quantity;

        public Reservation(long productId, int quantity) {
            this.productId = productId;
            this.quantity = quantity;
        }
    }
}
```

Ví dụ gọi dịch vụ (với `dataSource` đã được cấu hình):

```java
import java.util.Arrays;

InventoryBatchService service = new InventoryBatchService(dataSource);
service.reserve(Arrays.asList(
        new InventoryBatchService.Reservation(101L, 2),
        new InventoryBatchService.Reservation(102L, 1),
        new InventoryBatchService.Reservation(103L, 5)
));
```

Những điểm then chốt trong ví dụ:

1. `setAutoCommit(false)` **trước khi gửi batch** để mọi thay đổi thuộc cùng transaction. Nếu `autoCommit=true`, một số lệnh có thể đã được commit riêng và một `rollback` sau đó không thể hủy các commit trước.
2. Khi `executeBatch()` trả về bình thường, chương trình vẫn kiểm tra `counts.length` và từng phần tử. Ở đây, cả `0` và `SUCCESS_NO_INFO` đều không đáp ứng yêu cầu “chắc chắn cập nhật đúng một hàng”.
3. Khi ném `BatchUpdateException`, chương trình đọc `getUpdateCounts()` để chẩn đoán, cố gắng `rollback` và ném lại ngoại lệ. **Không retry riêng lệnh có số đếm lỗi trong transaction đang hỏng**.
4. Nhánh bắt `SQLException | RuntimeException` xử lý cả lỗi kiểm tra số hàng, `commit` và các lỗi JDBC khác. Nếu rollback cũng lỗi, `addSuppressed` giữ lại lỗi gốc.
5. Chỉ phục hồi `autoCommit=true` sau khi biết transaction đã kết thúc bằng `commit` hoặc `rollback` thành công. Lỗi khi phục hồi cấu hình được gắn vào lỗi gốc nếu có; với connection pool thật, cần dùng cơ chế reset/loại bỏ kết nối theo thư viện pool.

**Giới hạn quan trọng:** nếu `commit()` ném lỗi mất kết nối, kết quả `commit` có thể **chưa xác định**. Ngay cả khi gọi `rollback()` sau đó, ứng dụng cũng không thể tự suy luận giao dịch chắc chắn chưa được xác nhận. Với nghiệp vụ quan trọng, cần mã định danh yêu cầu và cơ chế kiểm tra/idempotency trước khi thử lại. Ví dụ cũng giả định ứng dụng tự quản lý transaction; khi dùng transaction manager của framework, phải giao quyền `commit`/`rollback` cho thành phần đó.

## 6. Đọc chuỗi SQLException để tìm nguyên nhân gốc

`getUpdateCounts()` chỉ cho biết **trạng thái thực thi**. Để hiểu nguyên nhân như khóa ngoại sai, trùng khóa chính hoặc mất kết nối, còn cần kiểm tra chuỗi `SQLException`:

```java
import java.sql.BatchUpdateException;
import java.sql.SQLException;

static void reportSqlExceptions(BatchUpdateException failure) {
    SQLException current = failure;
    int index = 0;
    while (current != null) {
        System.err.println("SQLException[" + index + "]: "
                + "SQLState=" + current.getSQLState()
                + ", vendorCode=" + current.getErrorCode());
        current = current.getNextException();
        index++;
    }
}
```

Ví dụ các nhóm `SQLState` thường gặp: `23` (vi phạm ràng buộc toàn vẹn), `08` (lỗi kết nối) và `40` (rollback giao dịch theo nhóm mã SQL tiêu chuẩn). Đây **không phải một bảng ánh xạ đầy đủ cho mọi driver**; nhiều DBMS có mã vendor-specific hoặc quy tắc riêng. Phân loại lỗi dựa trên tài liệu DBMS đang dùng, thay vì chỉ dựa vào vị trí có số đếm `-3`.

Chuỗi `getNextException()` khác với `Throwable.getCause()` và danh sách `getSuppressed()`. Trong lúc xử lý JDBC, đôi khi cần xem cả ba nguồn để tìm lỗi gốc, thông tin chi tiết của driver, và lỗi phát sinh trong quá trình rollback/đóng tài nguyên.

Khi đưa vào hệ thống logging thực tế, nên log **mã sự kiện, SQLState, vendor code, chỉ số batch, số đếm và correlation ID**. Hạn chế log dữ liệu tham số nhạy cảm; nội dung `getMessage()` đôi khi chứa SQL hoặc giá trị dữ liệu do driver tạo và cần được kiểm soát trước khi đưa vào log.

## 7. Khi nào dùng executeLargeBatch và getLargeUpdateCounts?

Từ JDBC 4.2, `Statement.executeLargeBatch()` trả về `long[]` để biểu diễn số hàng lớn hơn giới hạn `int`. Khi lệnh này ném `BatchUpdateException`, có thể đọc `getLargeUpdateCounts()`:

```java
import java.sql.BatchUpdateException;
import java.sql.Statement;

try {
    long[] counts = statement.executeLargeBatch();
    for (long count : counts) {
        if (count == Statement.SUCCESS_NO_INFO) {
            System.out.println("Thành công, không rõ số hàng");
        } else if (count >= 0) {
            System.out.println("Số hàng: " + count);
        }
    }
} catch (BatchUpdateException failure) {
    long[] counts = failure.getLargeUpdateCounts();
    // Diễn giải theo đúng thứ tự batch; EXECUTE_FAILED vẫn là -3.
    throw failure;
}
```

`statement` ở đây là `Statement` hoặc `PreparedStatement` đã được nạp batch. Dùng `getLargeUpdateCounts()` khi xử lý kết quả của `executeLargeBatch()` để tránh phụ thuộc mảng `int[]` trong những trường hợp số hàng có thể lớn; driver vẫn phải hỗ trợ các API liên quan. Những giá trị đặc biệt `SUCCESS_NO_INFO` và `EXECUTE_FAILED` giữ nguyên ý nghĩa.

Nếu dùng `executeLargeBatch()`, cần kiểm tra đầy đủ các giá trị `long` và xử lý lỗi/rollback giống `executeBatch()`; đoạn mã trên chỉ minh họa đọc số đếm lớn.

## 8. Những bẫy thường gặp khi xử lý batch lỗi

| Sai lầm | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| Đọc `getUpdateCounts()` rồi xem mọi vị trí thiếu là lỗi chắc chắn. | Mảng có thể bị rút ngắn khi driver dừng; thiếu kết quả không thể thay thế thông tin rollback/commit. | Ghi nhận rõ “không có số đếm”, kiểm tra driver và trạng thái transaction. |
| Xem `-2` như `0` hàng. | `SUCCESS_NO_INFO` nghĩa là lệnh **thành công** nhưng không có số hàng chính xác. | Xử lý như kết quả không biết số lượng. |
| Xem `-3` như số hàng âm để cộng tổng. | `EXECUTE_FAILED` là mã thất bại, không phải số lượng. | Phân nhánh theo hằng `Statement` trước khi tổng hợp. |
| Chỉ bắt `SQLException` và bỏ qua số đếm của `BatchUpdateException`. | Mất thông tin vị trí/bộ tham số đã được driver báo. | Bắt kiểu con trước, phân tích `getUpdateCounts()`, rồi rethrow hoặc báo lên service. |
| Gọi `commit` dù một câu lệnh thất bại nhưng các lệnh khác thành công. | Có thể tạo batch được áp dụng một phần. | Nếu nghiệp vụ yêu cầu all-or-nothing, dùng một transaction và rollback toàn bộ. |
| Để `autoCommit=true` rồi nghĩ có thể rollback mọi lệnh trước đó. | Một số lệnh có thể đã commit riêng. | Đặt transaction thủ công **trước** batch nếu cần tính nguyên tử. |
| Giả định `executeBatch()` bình thường nghĩa là cập nhật đúng một hàng. | `0` và `SUCCESS_NO_INFO` có thể không đạt quy tắc nghiệp vụ. | Kiểm tra từng số đếm theo kỳ vọng. |
| Retry mù quáng sau lỗi mất kết nối/`commit`. | Có thể tạo hiệu ứng trùng khi kết quả commit chưa rõ. | Dùng cơ chế idempotency, kiểm tra trạng thái và retry có giới hạn. |
| Dùng lại batch cũ sau lỗi mà không kiểm soát trạng thái. | Có thể lặp lại những câu đã thực thi hoặc không rõ thứ tự. | Đóng/recreate statement; nếu cần retry, tạo **transaction mới** với dữ liệu đầu vào được xác minh lại. |
| Log toàn bộ tham số, SQL nội suy và dữ liệu nghiệp vụ. | Làm lộ thông tin nhạy cảm trong log. | Log mã tham chiếu, chỉ số và mã lỗi; bảo vệ dữ liệu nhạy cảm. |

### BatchUpdateException khác SQLWarning như thế nào?

`SQLWarning` thể hiện cảnh báo JDBC và thường được đọc qua `getWarnings()` trên `Connection`, `Statement` hoặc `ResultSet`. Cảnh báo **không đồng nghĩa một batch đã thất bại**. Ngược lại, `BatchUpdateException` là ngoại lệ báo lỗi khi xử lý lô và thường cần quyết định rollback hoặc xử lý phục hồi rõ ràng. Đừng bỏ qua ngoại lệ chỉ vì những lệnh khác trong lô có số đếm dương.

Nếu cần quản lý cảnh báo, dùng `clearWarnings()` theo vòng đời xử lý của JDBC để tránh đọc lại cảnh báo cũ; không dùng nó để “xóa” hay phục hồi một transaction đã lỗi.

## 9. Tình huống thực hành và tự kiểm tra

Giả sử ứng dụng có bốn lệnh `UPDATE` trong một batch và yêu cầu **tất cả đều phải cập nhật đúng một hàng**. Sau `executeBatch()`, chương trình bắt được `BatchUpdateException`.

**Trường hợp 1:**

```java
int[] counts = {1, 1};
```

**Trường hợp 2:**

```java
int[] counts = {1, Statement.SUCCESS_NO_INFO,
                Statement.EXECUTE_FAILED, 1};
```

Hãy trả lời:

1. Với trường hợp 1, mảng số đếm nói chắc điều gì về hai lệnh đầu? Có thể kết luận lệnh thứ tư đã chạy, hay tất cả thay đổi đã được commit không?
2. Với trường hợp 2, ý nghĩa của ba giá trị `1`, `-2` và `-3` là gì? Vị trí nào được driver báo thất bại?
3. Tại sao `SUCCESS_NO_INFO` không đáp ứng quy tắc “chắc chắn cập nhật đúng một hàng”, dù JDBC coi lệnh đó thực thi thành công?
4. Nếu `executeBatch()` không ném ngoại lệ nhưng trả về `{1, 0, 1, 1}`, dịch vụ có nên `commit` hay `rollback` theo quy tắc đã cho?
5. Nếu `rollback()` cũng ném `SQLException`, làm sao giữ lại cả lỗi batch ban đầu và lỗi rollback?

**Đáp án định hướng:** (1) Driver báo hai lệnh đầu đã xử lý với số đếm `1`; các vị trí còn lại không có số đếm trong ngoại lệ, không được coi là đã commit. (2) `1`: số hàng; `-2`: thành công không rõ số hàng; `-3`: thất bại tại vị trí `2`. (3) Thành công của câu SQL không chứng minh chính xác số hàng; nghiệp vụ phải quyết định có chấp nhận kết quả không rõ hay không. (4) `rollback` vì phần tử thứ hai cập nhật `0` hàng, trái điều kiện. (5) Dùng `addSuppressed(rollbackError)` vào ngoại lệ gốc, sau đó ném lại ngoại lệ gốc.

**Ghi nhớ:** `BatchUpdateException.getUpdateCounts()` là công cụ **chẩn đoán từng phần tử của batch**, với `Statement.SUCCESS_NO_INFO = -2`, `Statement.EXECUTE_FAILED = -3` và các số không âm là số hàng được báo. Cách xử lý khi gặp lỗi khác nhau giữa các driver nên phải giữ thứ tự lệnh, đọc đúng độ dài mảng, xem chuỗi `SQLException` và kết thúc transaction rõ ràng. **Số đếm không thay thế `commit`/`rollback`**, và rollback là lựa chọn phù hợp khi nghiệp vụ yêu cầu toàn bộ lô thành công cùng nhau.
