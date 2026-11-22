# Giải phóng savepoint và kiểm tra hỗ trợ trong JDBC

Trong một giao dịch JDBC dài, ứng dụng đôi khi muốn thử một nhóm thao tác rồi **quay lại một mốc** nếu kết quả không đạt yêu cầu, trong khi vẫn giữ những thay đổi hợp lệ xảy ra trước mốc đó. JDBC cung cấp `Savepoint` để thực hiện kiểu rollback một phần này. Khi mốc không còn cần thiết, ứng dụng có thể gọi `Connection.releaseSavepoint(...)` để giải phóng nó.

Tuy nhiên, không phải hệ quản trị cơ sở dữ liệu và JDBC driver nào cũng hỗ trợ savepoint hoặc thao tác giải phóng savepoint theo cùng cách. Vì thế, ngoài việc gọi đúng API, cần biết **kiểm tra khả năng hỗ trợ**, quản lý vòng đời savepoint và lựa chọn hành vi an toàn khi driver không hỗ trợ.

Bài học thuộc chương **Giao dịch nâng cao** của **JDBC**. Kiến thức nền là `DataSource`, `Connection`, `PreparedStatement`, `SQLException`, `commit()` và `rollback()`; phần trọng tâm ở đây là **`releaseSavepoint` và `DatabaseMetaData.supportsSavepoints()`**. Ví dụ dùng các API JDBC chuẩn để thao tác với cơ sở dữ liệu quan hệ, không cần ORM.

Sau bài này, bạn có thể:

- Phân biệt `rollback(savepoint)`, `releaseSavepoint(savepoint)` và `commit()`.
- Xác định thời điểm có thể tạo, sử dụng và giải phóng một savepoint.
- Kiểm tra khả năng hỗ trợ savepoint bằng `DatabaseMetaData` và xử lý ngoại lệ khi thực thi.
- Viết transaction có phần thay đổi tùy chọn và giải phóng savepoint đúng thứ tự.
- Chọn cách xử lý khi việc release không được hỗ trợ, mà vẫn bảo toàn tính nhất quán của transaction.

## 1. Savepoint là mốc trong một giao dịch, không phải giao dịch độc lập

Một `Savepoint` là điểm được ghi nhận **bên trong transaction hiện tại**. Nếu cần, `Connection.rollback(savepoint)` có thể hoàn tác những thay đổi thuộc transaction được thực hiện **sau** mốc đó, thay vì hoàn tác toàn bộ transaction.

```text
BEGIN TRANSACTION
    INSERT đơn hàng                    (A)
    SAVEPOINT before_note              (S)
    INSERT ghi chú tạm                 (B)
    Kiểm tra quy tắc nghiệp vụ
    ROLLBACK TO SAVEPOINT before_note  (hoàn tác B, giữ A)
    INSERT dòng hàng bắt buộc          (C)
COMMIT                                  (lưu A và C)
```

Một savepoint không tạo transaction con độc lập. `rollback(savepoint)` chỉ lùi về mốc, còn **transaction bên ngoài vẫn hoạt động** và cần được `commit()` hoặc `rollback()` toàn phần. Ngay cả khi một phần đã được “chấp nhận”, lỗi ở bước sau vẫn có thể khiến toàn bộ transaction bị rollback.

Trong JDBC, các thao tác thường gặp là:

```java
connection.setAutoCommit(false);

Savepoint checkpoint = connection.setSavepoint("before_optional_step");
// ... các câu lệnh SQL dùng chính connection này ...

connection.rollback(checkpoint);       // Lùi về mốc, nếu cần.
connection.releaseSavepoint(checkpoint); // Bỏ mốc khi không cần nữa.

connection.commit();                   // Kết thúc transaction thành công.
```

Đoạn mã này minh họa **thứ tự API**, chưa phải thao tác nghiệp vụ hoàn chỉnh. `rollback(checkpoint)` chỉ cần gọi khi thực sự muốn hủy thay đổi sau mốc; không bắt buộc phải rollback trước mỗi lần release.

## 2. `releaseSavepoint` thực sự làm gì?

`Connection.releaseSavepoint(Savepoint savepoint)` yêu cầu cơ sở dữ liệu loại bỏ savepoint khỏi transaction hiện tại. Đó là thao tác **quản lý mốc giao dịch**, không phải thao tác xác nhận hay hoàn tác dữ liệu.

| Thao tác | Thay đổi dữ liệu sau savepoint | Trạng thái transaction | Khả năng dùng lại savepoint |
| --- | --- | --- | --- |
| `rollback(savepoint)` | Hoàn tác những thay đổi sau mốc theo ngữ nghĩa DB | Transaction vẫn mở | Thường còn dùng được; cần kiểm tra driver/DB khi xây dựng logic phức tạp |
| `releaseSavepoint(savepoint)` | **Không** tự hoàn tác thay đổi | Transaction vẫn mở | Mốc đã bị giải phóng, không còn được dùng để rollback |
| `commit()` | Xác nhận các thay đổi chưa rollback | Kết thúc transaction hiện tại | Savepoint của transaction cũ không còn hợp lệ |
| `rollback()` | Hoàn tác toàn bộ thay đổi chưa commit | Kết thúc transaction hiện tại | Savepoint của transaction cũ không còn hợp lệ |

Ví dụ: nếu đã thêm một dòng ghi chú, sau đó gọi `releaseSavepoint(beforeNote)`, **dòng ghi chú vẫn nằm trong transaction**. Nếu câu lệnh thêm dòng hàng bắt buộc xảy ra lỗi và toàn bộ transaction `rollback()`, dòng ghi chú cũng bị hoàn tác. `releaseSavepoint` không làm phần dữ liệu trước hoặc sau mốc trở thành “đã commit”.

Hai luồng thao tác đúng về mặt ý nghĩa:

```text
Luồng 1: giữ thay đổi tùy chọn
BEGIN -> A -> SAVEPOINT S -> B -> RELEASE S -> C -> COMMIT
Kết quả: A, B, C được lưu.

Luồng 2: bỏ thay đổi tùy chọn
BEGIN -> A -> SAVEPOINT S -> B -> ROLLBACK TO S -> RELEASE S -> C -> COMMIT
Kết quả: A, C được lưu; B bị hoàn tác.
```

Trong cả hai luồng, nếu bước C thất bại và ứng dụng gọi `rollback()` toàn phần, **không có A/B/C nào của transaction được commit**, với giả định các bảng và câu lệnh đều tham gia giao dịch đúng cách.

### Khi nào nên giải phóng mốc?

Giải phóng ngay sau khi đã quyết định **không còn cần quay lại mốc ấy**. Với một transaction dài có nhiều bước thử, việc giải phóng mốc không dùng nữa có thể giúp DB giảm phần trạng thái phải giữ cho savepoint. Lợi ích và cách hiện thực phụ thuộc cơ sở dữ liệu.

Không giải phóng savepoint nếu chương trình vẫn có thể cần `rollback(savepoint)` về chính mốc đó. Khi đã release thành công, gọi `rollback(savepoint)` hay release lại cùng đối tượng là **sử dụng mốc không còn hợp lệ** và có thể nhận `SQLException`.

`Savepoint` không phải `AutoCloseable`; không thể quản lý bằng `try (Savepoint point = ...)`. Phải gọi `releaseSavepoint` tường minh khi muốn giải phóng sớm, hoặc để transaction kết thúc làm các mốc hết hiệu lực. `try-with-resources` vẫn dùng cho `Connection`, `PreparedStatement` và `ResultSet`.

## 3. Kiểm tra khả năng hỗ trợ bằng `DatabaseMetaData`

JDBC cung cấp `DatabaseMetaData.supportsSavepoints()` để hỏi driver về khả năng sử dụng savepoint của cơ sở dữ liệu.

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public static boolean canUseSavepoints(DataSource dataSource)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData metadata = connection.getMetaData();
        return metadata.supportsSavepoints();
    }
}
```

`true` cho biết DB/driver **báo có hỗ trợ savepoint**; `false` nghĩa là không nên thiết kế luồng bắt buộc phải rollback một phần dựa vào savepoint trên môi trường đó. Truy vấn metadata có thể phát sinh `SQLException`, vì vậy phải xử lý cả lỗi đọc metadata.

Trong một thao tác transaction thực sự, nên kiểm tra trực tiếp trên **chính kết nối sẽ chạy các câu lệnh**:

```java
import java.sql.SQLFeatureNotSupportedException;

try (Connection connection = dataSource.getConnection()) {
    if (!connection.getMetaData().supportsSavepoints()) {
        throw new SQLFeatureNotSupportedException(
                "The configured database/driver does not support savepoints");
    }

    connection.setAutoCommit(false);
    Savepoint marker = connection.setSavepoint("my_marker");
    // ... thực hiện thao tác trong transaction ...
    connection.releaseSavepoint(marker);
    connection.commit();
}
```

Đoạn này chỉ minh họa việc kiểm tra hỗ trợ và gọi API; với mã có nhiều thao tác ghi, vẫn cần khối `catch` để rollback khi thất bại (xem ví dụ hoàn chỉnh ở phần sau). Tránh chỉ kiểm tra hỗ trợ một lần trên DB phát triển rồi mặc định mọi môi trường chạy sẽ giống hệt nhau.

**Giới hạn quan trọng:** `supportsSavepoints()` không phải phép kiểm tra riêng cho **`releaseSavepoint()`**. JDBC không cung cấp một phương thức metadata chuẩn tên `supportsReleaseSavepoint()`. Một driver có thể hỗ trợ tạo và rollback về savepoint nhưng hạn chế thao tác release, hoặc báo ngoại lệ khi gọi. Vì thế, phải kiểm tra cả hành vi thật bằng integration test với đúng phiên bản DB/driver sử dụng.

### Khi metadata báo không hỗ trợ

Có hai chính sách thường gặp:

1. **Savepoint là yêu cầu bắt buộc:** dừng thao tác trước khi thực hiện DML và báo lỗi rõ ràng, như `SQLFeatureNotSupportedException`.
2. **Savepoint chỉ là tối ưu hóa hoặc thao tác tùy chọn:** thiết kế luồng thay thế có thể chạy an toàn mà không có rollback một phần, ví dụ bỏ hẳn bước ghi thử hoặc rollback **toàn bộ** transaction nếu bước tùy chọn thất bại.

Không được xử lý `supportsSavepoints() == false` bằng cách giả vờ `rollback(savepoint)` đã thành công. Nếu nghiệp vụ đòi khả năng hoàn tác riêng phần, việc thiếu savepoint có thể làm **thay đổi tính đúng đắn** của quy trình; cần một phương án nghiệp vụ khác hoặc một DB hỗ trợ.

## 4. Ví dụ hoàn chỉnh: lưu đơn hàng, thử ghi chú và giải phóng savepoint

Giả sử ứng dụng tạo một đơn hàng và một dòng hàng bắt buộc. Ngoài ra, hệ thống thử thêm một ghi chú chưa được phê duyệt. Nếu người dùng chấp thuận, ghi chú được giữ; nếu không, ghi chú bị rollback về savepoint, còn đơn hàng và dòng hàng vẫn được ghi.

Schema ví dụ (cú pháp thực tế có thể cần điều chỉnh theo DB):

```sql
CREATE TABLE sales_order (
    order_id    BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
);

CREATE TABLE sales_order_note (
    order_id  BIGINT PRIMARY KEY,
    note_text VARCHAR(300) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES sales_order(order_id)
);

CREATE TABLE sales_order_item (
    order_id   BIGINT NOT NULL,
    line_no    INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES sales_order(order_id)
);
```

Ví dụ cố tình dùng `order_id` do tầng gọi cung cấp, để chỉ tập trung vào **savepoint** thay vì mở rộng sang vấn đề khóa tự sinh. Trong ứng dụng thực tế, `order_id` cũng có thể lấy từ `getGeneratedKeys()` trên chính kết nối đang dùng. Điều kiện tiên quyết là các bảng và engine đều hỗ trợ transaction.

Tệp minh họa `OrderWithOptionalNoteWriter.java` (Java 17 trở lên):

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.Savepoint;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderWithOptionalNoteWriter {
    private final DataSource dataSource;

    public OrderWithOptionalNoteWriter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public void create(
            long orderId,
            long customerId,
            long productId,
            String proposedNote,
            boolean acceptNote) throws SQLException {

        if (orderId <= 0 || customerId <= 0 || productId <= 0) {
            throw new IllegalArgumentException("IDs must be positive");
        }

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getMetaData().supportsSavepoints()) {
                throw new SQLFeatureNotSupportedException(
                        "Savepoints are required for this operation");
            }

            connection.setAutoCommit(false);
            try {
                insertOrder(connection, orderId, customerId);

                if (proposedNote != null && !proposedNote.isBlank()) {
                    Savepoint beforeNote = connection.setSavepoint("before_note");

                    // Thử ghi chú bên trong cùng transaction.
                    insertNote(connection, orderId, proposedNote);

                    if (!acceptNote) {
                        // Chỉ bỏ ghi chú; giữ INSERT đơn hàng trước mốc.
                        connection.rollback(beforeNote);
                    }

                    // Mốc không còn cần dùng nữa; hành vi fail-fast nếu
                    // driver không hỗ trợ release được phân tích bên dưới.
                    connection.releaseSavepoint(beforeNote);
                }

                // Bước bắt buộc sau release vẫn thuộc cùng transaction.
                insertRequiredItem(connection, orderId, productId);
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

    private static void insertOrder(
            Connection connection, long orderId, long customerId)
            throws SQLException {
        String sql = "INSERT INTO sales_order (order_id, customer_id) VALUES (?, ?)";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, orderId);
            statement.setLong(2, customerId);
            requireOneRow(statement.executeUpdate(), "sales_order");
        }
    }

    private static void insertNote(
            Connection connection, long orderId, String note)
            throws SQLException {
        String sql = "INSERT INTO sales_order_note (order_id, note_text) VALUES (?, ?)";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, orderId);
            statement.setString(2, note);
            requireOneRow(statement.executeUpdate(), "sales_order_note");
        }
    }

    private static void insertRequiredItem(
            Connection connection, long orderId, long productId)
            throws SQLException {
        String sql = """
                INSERT INTO sales_order_item
                    (order_id, line_no, product_id, quantity)
                VALUES (?, ?, ?, ?)
                """;
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, orderId);
            statement.setInt(2, 1);
            statement.setLong(3, productId);
            statement.setInt(4, 1);
            requireOneRow(statement.executeUpdate(), "sales_order_item");
        }
    }

    private static void requireOneRow(int count, String table)
            throws SQLException {
        if (count != 1) {
            throw new SQLException("Expected 1 inserted row in " + table
                    + ", got " + count);
        }
    }
}
```

Một lời gọi minh họa:

```java
OrderWithOptionalNoteWriter writer =
        new OrderWithOptionalNoteWriter(dataSource);

// Ghi chú được ghi tạm, sau đó hủy; đơn hàng và dòng hàng vẫn commit.
writer.create(501L, 42L, 1001L, "Gói quà", false);

// Ghi chú được ghi và giữ, toàn bộ được commit cùng nhau.
writer.create(502L, 42L, 1002L, "Giao sau 18 giờ", true);
```

Tình huống dùng cờ `acceptNote` chỉ để minh họa rõ hai nhánh **giữ** và **hủy** một thay đổi đã thử trong cùng transaction. Trong nghiệp vụ thực tế, quyết định này có thể đến từ quy tắc kiểm tra sau một bước ghi thử hoặc kết quả xử lý trong transaction; không nhất thiết luôn cần ghi rồi rollback nếu đã biết từ đầu rằng sẽ bỏ ghi chú.

### Đọc đường đi của dữ liệu

| Bước | `acceptNote = false` | `acceptNote = true` |
| --- | --- | --- |
| `insertOrder` | Thêm cha | Thêm cha |
| `setSavepoint("before_note")` | Tạo mốc sau khi có cha | Tạo mốc sau khi có cha |
| `insertNote` | Thêm ghi chú tạm | Thêm ghi chú |
| `rollback(beforeNote)` | **Có**: bỏ ghi chú | Không gọi |
| `releaseSavepoint(beforeNote)` | Giải phóng mốc đã dùng | Giải phóng mốc không còn cần |
| `insertRequiredItem` | Thêm dòng hàng bắt buộc | Thêm dòng hàng bắt buộc |
| `commit()` | Lưu cha + dòng hàng | Lưu cha + ghi chú + dòng hàng |

Điểm mấu chốt: trong hai trường hợp, `releaseSavepoint` đều **không phải commit**. Nếu `insertRequiredItem` thất bại, khối `catch` vẫn gọi `rollback()` **toàn phần**, kể cả khi đã giải phóng mốc.

Ví dụ chọn chính sách **fail-fast** khi lệnh `releaseSavepoint` không được hỗ trợ: một `SQLException` từ release sẽ dẫn tới rollback toàn bộ. Chính sách này có tính bảo thủ và phù hợp khi ứng dụng chưa kiểm chứng cách driver xử lý tình huống đó. Nếu cơ sở dữ liệu đã được xác minh là hỗ trợ savepoint nhưng không có thao tác release an toàn, có thể chọn phương án bỏ lời gọi release và để mốc hết hiệu lực khi transaction kết thúc (phần 6).

## 5. Vòng đời savepoint và các lỗi sử dụng phổ biến

Một savepoint chỉ có ý nghĩa trên **`Connection` và transaction đã tạo ra nó**. `Savepoint` không phải một mã định danh có thể lấy từ kết nối A rồi sử dụng trên kết nối B.

| Tình huống | Hệ quả hoặc cách xử lý |
| --- | --- |
| `setSavepoint()` khi `autoCommit = true` | Không phải ngữ cảnh hợp lệ cho savepoint theo JDBC; có thể nhận `SQLException` |
| Gọi `rollback(point)` sau `releaseSavepoint(point)` | Mốc đã bị giải phóng; không được dựa vào nó để quay lại |
| Gọi `releaseSavepoint(point)` hai lần | Lần thứ hai tham chiếu mốc không còn hợp lệ |
| Gọi `rollback(point)` bằng `Savepoint` của kết nối khác | Sai quyền sở hữu mốc, có thể nhận `SQLException` |
| Dùng mốc cũ sau `commit()` hoặc `rollback()` toàn phần | Giao dịch cũ đã kết thúc; mốc không còn hợp lệ |
| Release mốc sớm nhưng sau đó vẫn cần quay lại nó | Mất khả năng rollback về mốc; cần chỉnh lại thời điểm release |
| Gọi `releaseSavepoint` ở driver không hỗ trợ | Có thể phát sinh `SQLFeatureNotSupportedException` hoặc `SQLException` khác |

### Savepoint có tên và không tên

Hai cách tạo savepoint:

```java
Savepoint anonymous = connection.setSavepoint();
Savepoint named = connection.setSavepoint("before_note");
```

Cả hai đều có thể truyền vào `rollback(savepoint)` và `releaseSavepoint(savepoint)`. Đối tượng có tên có thể trả tên qua `getSavepointName()`, còn đối tượng không tên có thể trả số định danh qua `getSavepointId()`. Gọi getter không tương ứng với loại savepoint có thể phát sinh `SQLException`; không dùng `getSavepointId()` với mốc có tên để tự tạo logic nghiệp vụ. Cách đặt tên và giới hạn độ dài tên phụ thuộc DB. Tên mốc nên là hằng số nội bộ dễ đọc, tránh dựng tên tùy tiện từ dữ liệu do người dùng nhập.

### Nhiều savepoint lồng nhau

```text
BEGIN
  thao tác A
  SAVEPOINT S1
  thao tác B
  SAVEPOINT S2
  thao tác C
  ROLLBACK TO S2  -- bỏ C
  RELEASE S2
  thao tác D
  RELEASE S1
COMMIT             -- lưu A, B, D
```

Đây vẫn là **một transaction**. Việc rollback về mốc trước có thể khiến các mốc tạo sau mốc đó không còn hợp lệ tùy ngữ nghĩa DB; việc release một mốc cũng có thể ảnh hưởng tới các mốc lồng bên trong theo sản phẩm. Với luồng nhiều mốc, nên thiết kế thứ tự sử dụng rõ ràng, tránh lưu giữ những đối tượng `Savepoint` đã lỗi thời và kiểm chứng trên DB đích.

## 6. Xử lý khác biệt driver và fallback khi không release được

Về thiết kế, việc **tạo mốc và rollback một phần** có thể là yêu cầu nghiệp vụ, còn **release sớm** chủ yếu là bước dọn trạng thái của mốc. Để hỗ trợ nhiều DB, phải tách hai yêu cầu này:

| Khả năng thực tế | Hướng xử lý |
| --- | --- |
| Không hỗ trợ savepoint | Dừng trước DML nếu nghiệp vụ cần rollback một phần; hoặc thay đổi luồng nghiệp vụ |
| Hỗ trợ tạo/rollback và release | Gọi `releaseSavepoint` khi mốc không còn cần |
| Hỗ trợ tạo/rollback nhưng release không được hỗ trợ | Có thể **không gọi release** và kết thúc transaction bình thường, nếu đã xác minh hành vi an toàn trên DB/driver đó |
| Gặp lỗi SQL không rõ nguyên nhân khi release | Xem là lỗi transaction, rollback toàn phần thay vì bỏ qua |

Nếu việc release là tùy chọn và phiên bản driver đã được kiểm thử, ứng dụng có thể dùng cấu hình khả năng riêng để quyết định có gọi `releaseSavepoint` hay không:

```java
// Cấu hình này phải được xác minh bằng integration test cho driver/DB đích.
boolean releaseSupported = configuration.isReleaseSavepointSupported();

Savepoint marker = connection.setSavepoint("after_required_step");
// ... phần SQL tùy chọn và quyết định rollback về marker nếu cần ...

if (releaseSupported) {
    connection.releaseSavepoint(marker);
}

// Dù không release, mốc vẫn hết hiệu lực khi transaction kết thúc.
```

`configuration` trong đoạn mã là đối tượng cấu hình minh họa do ứng dụng cung cấp, không phải API JDBC. Không có phương thức metadata JDBC tiêu chuẩn xác nhận riêng cho thao tác release, nên giá trị này phải dựa trên khả năng đã kiểm chứng của môi trường.

Khi gọi API, một driver có thể ném `SQLFeatureNotSupportedException` nếu không hiện thực tính năng. Nhưng **không nên bắt mọi `SQLException` từ `releaseSavepoint` rồi tiếp tục commit**: lỗi có thể xuất phát từ transaction đã hỏng, mất kết nối hoặc đối tượng savepoint không hợp lệ. Ngay cả khi bắt riêng `SQLFeatureNotSupportedException`, chỉ nên tiếp tục nếu đã xác minh việc gọi API không làm trạng thái transaction trên server trở nên lỗi. Nếu không chắc chắn, rollback toàn phần và báo lỗi là lựa chọn an toàn.

Ví dụ về chính sách **cần xác minh** trước khi dùng trong môi trường cụ thể:

```java
try {
    connection.releaseSavepoint(marker);
} catch (SQLFeatureNotSupportedException unsupported) {
    // Chỉ tiếp tục nếu driver đã được kiểm thử:
    // - API chưa làm transaction phía server bị lỗi;
    // - transaction vẫn có thể commit an toàn;
    // - để savepoint tồn tại đến cuối transaction là chấp nhận được.
    if (!knownSafeToOmitRelease) {
        throw unsupported;
    }
}
```

Ở đây `knownSafeToOmitRelease` cũng là quyết định cấu hình, không phải biến JDBC cung cấp sẵn. Thường cách đơn giản và ít bất ngờ hơn là **không gọi** một thao tác đã biết driver không hỗ trợ, thay vì trông chờ ngoại lệ rồi giả định trạng thái transaction vẫn tốt.

### Khi một câu lệnh SQL tùy chọn thất bại

Điều kiện quan trọng khác: có DB (ví dụ PostgreSQL) có thể đặt transaction vào trạng thái lỗi sau một câu lệnh thất bại, cho đến khi rollback về savepoint hoặc rollback toàn phần. Nếu bước tùy chọn có thể lỗi mà nghiệp vụ muốn tiếp tục, phải chuẩn bị mốc **trước** câu lệnh và **chỉ bỏ qua những lỗi đã được xác định an toàn để phục hồi**.

```java
Savepoint beforeOptional = connection.setSavepoint("before_optional");
try {
    performOptionalSql(connection);  // Có thể ném SQLException.
    connection.releaseSavepoint(beforeOptional);
} catch (SQLException failure) {
    // Với lỗi chưa được phân loại, xử lý fail-fast an toàn hơn:
    // truyền lỗi ra tầng giao dịch để rollback toàn phần.
    throw failure;
}
```

Đoạn trên minh họa **nhánh fail-fast**, không phải mẫu phục hồi lỗi: `performOptionalSql` là phương thức ứng dụng minh họa. Khi cần phục hồi một lỗi đã biết, ví dụ vi phạm một ràng buộc tùy chọn cụ thể, logic sẽ giống sau:

```java
Savepoint beforeOptional = connection.setSavepoint("before_optional");
try {
    insertOptionalRecord(connection);
} catch (SQLException failure) {
    if (!isExpectedRecoverableFailure(failure)) {
        throw failure; // Tầng ngoài rollback toàn phần.
    }
    connection.rollback(beforeOptional); // Khôi phục trạng thái trước bước tùy chọn.
    // Ghi nhận nhánh bỏ qua tùy chọn ở mức nghiệp vụ.
}

connection.releaseSavepoint(beforeOptional); // Nếu driver hỗ trợ.
```

Hai phương thức `insertOptionalRecord` và `isExpectedRecoverableFailure` là ví dụ giao diện nội bộ của ứng dụng. `isExpectedRecoverableFailure` phải dựa trên **mã lỗi/ràng buộc cụ thể của DB và chính sách nghiệp vụ**, không được mặc định coi mọi `SQLException` là lỗi có thể bỏ qua. Nếu `rollback(beforeOptional)` thất bại, ngoại lệ cũng phải được đẩy ra để tầng ngoài thử rollback toàn phần. Nếu release thất bại, áp dụng chính sách ở trên; không im lặng bỏ qua lỗi SQL không xác định.

## 7. Những lưu ý về giao dịch và tài nguyên

### `releaseSavepoint` không giải phóng `Connection`

Savepoint là mốc của transaction, còn `Connection`, `PreparedStatement` và `ResultSet` là các tài nguyên JDBC riêng biệt. Release mốc **không** đóng các câu lệnh hay kết nối. Vẫn cần dùng `try-with-resources` và chỉ đóng kết nối sau khi đã kết thúc hoặc cố gắng kết thúc transaction.

### Chỉ thao tác trên kết nối mình sở hữu

Ví dụ `OrderWithOptionalNoteWriter.create()` tự mở kết nối, tự tắt auto-commit và chịu trách nhiệm commit/rollback. Nếu ứng dụng dùng transaction manager hoặc caller truyền kết nối đã tham gia giao dịch lớn hơn, repository **không tự ý `commit`, `rollback` toàn phần, `close` hoặc đổi `autoCommit`**. Thay vào đó, tầng sở hữu transaction quyết định ranh giới, còn hàm con có thể đặt savepoint và rollback về mốc theo hợp đồng rõ ràng.

### Không bật `autoCommit` tùy tiện trong `finally`

Trong JDBC, đổi từ `autoCommit = false` sang `true` khi transaction đang hoạt động có thể khiến transaction bị commit. Đừng dùng `setAutoCommit(true)` vô điều kiện như một bước dọn tài nguyên nếu rollback vừa thất bại. Với connection pool, dựa vào hợp đồng quản lý và reset kết nối của pool; khi trạng thái transaction không rõ, cần coi kết nối là đáng ngờ và xử lý theo cơ chế loại bỏ kết nối hỏng của pool.

### Savepoint không thay đổi mức cô lập giao dịch

Savepoint không tự tăng isolation level và không thay thế khóa, điều kiện `UPDATE`, version check hoặc ràng buộc uniqueness khi có tranh chấp đồng thời. `rollback(savepoint)` có thể tác động đến khóa đã lấy sau mốc theo quy tắc từng DB, còn `releaseSavepoint` không hứa giải phóng mọi khóa hay đảm bảo tài nguyên transaction lập tức trở về mức trước đó. Nếu thao tác cần tính đúng đắn khi nhiều transaction cùng cập nhật, phải thiết kế concurrency riêng.

### Không dùng savepoint để “rollback” tác động bên ngoài DB

Savepoint chỉ áp dụng cho thay đổi thuộc transaction của kết nối cơ sở dữ liệu hỗ trợ. Nó không thu hồi email đã gửi, file đã ghi, API bên ngoài đã gọi hoặc thông điệp đã phát tới hệ thống khác. Với thao tác xuyên nhiều hệ thống, có thể cần outbox, cơ chế bù trừ hoặc thiết kế luồng khác.

## 8. Kiểm thử thực tế với JDBC driver

Do sự khác biệt giữa DB/driver, một bộ integration test nên xác nhận cả **hỗ trợ được báo cáo** và **hành vi thật**. Kiểm thử trên đúng loại DB, driver và kiểu bảng sẽ chạy trong môi trường triển khai.

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Metadata hỗ trợ savepoint | Gọi `connection.getMetaData().supportsSavepoints()` | Trả giá trị phù hợp với môi trường kiểm thử |
| Release khi vẫn muốn giữ thay đổi | `INSERT A` → savepoint → `INSERT B` → release → commit | Cả A và B đều tồn tại |
| Rollback về mốc rồi release | `INSERT A` → savepoint → `INSERT B` → rollback về mốc → release → commit | A tồn tại; B không tồn tại |
| Full rollback sau release | Thêm A/B → release → thêm C gây lỗi → full rollback | Không hàng nào thuộc transaction được commit |
| Sử dụng savepoint đã release | Release rồi gọi `rollback(savepoint)` | Thao tác bị từ chối; không được dựa vào mốc đó nữa |
| Không hỗ trợ savepoint | Môi trường/driver báo false hoặc không hỗ trợ API | Thao tác bắt buộc savepoint dừng an toàn trước DML |
| Không hỗ trợ release | Cấu hình DB/driver không hiện thực release | Chọn fail-fast, hoặc bỏ release theo chính sách đã kiểm thử |
| SQL lỗi sau mốc | Gây vi phạm ràng buộc **sau** khi đặt savepoint | Rollback đến mốc cho lỗi dự kiến; lỗi bất thường dẫn tới full rollback |
| Commit lỗi hoặc mất kết nối | Mô phỏng lỗi tại thời điểm commit | Caller nhận lỗi; không tự khẳng định kết quả commit chắc chắn thất bại |

Ví dụ xác minh sau khi gọi `create(501L, 42L, 1001L, "Gói quà", false)` thành công:

```sql
SELECT * FROM sales_order WHERE order_id = 501;
SELECT * FROM sales_order_note WHERE order_id = 501;
SELECT * FROM sales_order_item WHERE order_id = 501;
```

Kỳ vọng có **một** hàng `sales_order`, **không có** hàng `sales_order_note` và có **một** hàng `sales_order_item`. Với `acceptNote = true`, có cả ghi chú. Nếu sau khi release mốc mà câu lệnh thêm dòng hàng gặp lỗi, kiểm tra lại qua kết nối khác để xác nhận **không** có dữ liệu nào của giao dịch vừa rollback.

Trường hợp ngoại lệ tại `commit()` cần phân biệt với lỗi trong một câu lệnh thông thường. Nếu mạng mất đúng lúc commit, ứng dụng có thể không biết DB đã commit hay chưa; không tự động thử lại một thao tác tạo mới mà không có khóa nghiệp vụ hoặc cơ chế chống trùng (idempotency) phù hợp.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng cần nhớ |
| --- | --- |
| “Release savepoint là commit phần trước đó” | Release chỉ bỏ mốc; toàn bộ transaction vẫn có thể rollback |
| “Release savepoint sẽ xóa các thay đổi sau mốc” | Muốn hoàn tác, gọi `rollback(savepoint)` **trước khi release** |
| “Đã `supportsSavepoints() == true` thì release chắc chắn chạy được” | Metadata không kiểm tra riêng release; vẫn có thể lỗi theo driver/DB |
| “Không release thì transaction tự sai” | Savepoint sẽ hết hiệu lực khi transaction kết thúc; release sớm có ích nhưng không luôn bắt buộc |
| “Có thể lấy savepoint từ connection A và rollback trên B” | Savepoint thuộc transaction và kết nối tạo ra nó |
| “`SQLException` nào sau savepoint cũng có thể bỏ qua” | Chỉ phục hồi những lỗi đã biết và phải rollback đúng mốc trước khi tiếp tục |
| “Bỏ qua lỗi `releaseSavepoint` là an toàn vì đây chỉ là cleanup” | Lỗi có thể chỉ ra transaction đã hỏng; cần phân loại và xác minh |
| “Savepoint bảo đảm mọi DB có cùng hành vi khóa và DDL” | Mỗi sản phẩm có khác biệt; chỉ dựa vào tính năng đã được thử nghiệm |

## 10. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Giữ hay xóa dữ liệu.** Trong một transaction, ứng dụng thêm A, đặt savepoint S, thêm B, gọi `releaseSavepoint(S)` rồi `commit()`. B có được lưu không? Nếu bước cuối đổi thành `rollback()` toàn phần thì sao?

**Đáp án:** Có, B được lưu nếu commit thành công. Nếu rollback toàn phần, cả A và B chưa commit đều bị hoàn tác; release không bảo vệ chúng khỏi rollback.

**Bài 2 — Thứ tự API.** Hãy sửa đoạn mã sai sau:

```java
Savepoint s = connection.setSavepoint();
insertOptionalRecord(connection);
connection.releaseSavepoint(s);
connection.rollback(s); // Sai: s đã được giải phóng.
```

**Gợi ý:** Nếu cần hủy phần tùy chọn, thực hiện `rollback(s)` **trước** `releaseSavepoint(s)`, hoặc không rollback nếu muốn giữ phần đó. Sau cùng vẫn cần commit hoặc rollback toàn phần.

**Bài 3 — Hỗ trợ tính năng.** Vì sao không đủ để chỉ kiểm tra `supportsSavepoints()` nếu ứng dụng bắt buộc phải gọi `releaseSavepoint()` trên nhiều DB khác nhau?

**Đáp án:** JDBC không có cờ metadata riêng cho release; hỗ trợ tạo/rollback savepoint không tự bảo đảm release hoạt động đúng. Cần xác minh bằng integration test và có chính sách khi không hỗ trợ.

**Bài 4 — Nhận diện lỗi có thể phục hồi.** Một lệnh `INSERT` tùy chọn gây lỗi trùng mã theo một ràng buộc đã biết. Ứng dụng muốn giữ thao tác cha và tiếp tục. Cần thực hiện những bước nào để tiếp tục an toàn?

**Gợi ý:** Đặt savepoint trước `INSERT`, phân loại đúng lỗi nghiệp vụ được phép bỏ qua, `rollback(savepoint)`, giải phóng mốc khi được hỗ trợ, rồi tiếp tục các lệnh bắt buộc. Nếu không rollback được về mốc, rollback toàn phần.

**Bài 5 — Không hỗ trợ savepoint.** DB báo `supportsSavepoints() == false`. Một tính năng yêu cầu hoàn tác riêng phần nhưng giữ dữ liệu trước mốc. Có nên thay bằng `rollback()` toàn phần rồi tiếp tục như thể thao tác thành công không?

**Đáp án:** Không. `rollback()` toàn phần làm mất cả phần trước mốc. Phải thay đổi luồng xử lý hoặc dùng DB/driver hỗ trợ yêu cầu, và báo lỗi khi không có phương án tương đương.

## Tổng kết

Trong JDBC, `Savepoint` giúp quản lý điểm rollback một phần **bên trong** transaction. `releaseSavepoint` loại bỏ một mốc không còn cần thiết, nhưng **không commit cũng không rollback dữ liệu**. Hãy đặt savepoint sau khi đã tắt `autoCommit`, dùng `rollback(savepoint)` nếu cần hủy thay đổi sau mốc, chỉ release khi đã xong với mốc đó, và tiếp tục quản lý toàn bộ transaction bằng `commit()` hoặc `rollback()`. Dùng `DatabaseMetaData.supportsSavepoints()` để kiểm tra hỗ trợ tổng quát; vì không có phép kiểm tra chuẩn riêng cho release, cần dựa vào integration test và xử lý ngoại lệ một cách bảo thủ trên đúng DB/driver triển khai.
