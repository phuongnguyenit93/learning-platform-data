# Yêu cầu type và concurrency khi tạo Statement trong JDBC

Khi truy vấn dữ liệu bằng JDBC, nhiều ví dụ dùng `connection.createStatement()` hoặc `connection.prepareStatement(sql)` rồi duyệt `ResultSet` bằng `next()`. Đây là cách phù hợp cho phần lớn truy vấn. Nhưng một số ứng dụng cần **di chuyển con trỏ về hàng trước, tới một hàng bất kỳ**, hoặc **cập nhật hàng ngay qua `ResultSet`**. JDBC cho phép *yêu cầu* những khả năng đó khi tạo `Statement` hoặc `PreparedStatement`.

Hai tham số quan trọng là **result-set type** (kiểu di chuyển và độ nhạy của con trỏ) và **result-set concurrency** (khả năng đọc hoặc cập nhật hàng qua `ResultSet`). Không phải mọi driver hay mọi câu SQL đều hỗ trợ mọi tổ hợp. Vì vậy, ứng dụng phải kiểm tra khả năng driver, xem thuộc tính của `ResultSet` thực tế và xử lý trường hợp không được hỗ trợ.

Bài học thuộc chương **ResultSet nâng cao** của module JDBC. Ta sẽ đi từ các hằng chuẩn JDBC đến ví dụ Java dùng `DataSource`, `Statement`, `PreparedStatement`, `ResultSet`, các bước kiểm tra metadata, quản lý transaction và các giới hạn thực tế khi chọn type/concurrency.

## 1. Type và concurrency điều khiển điều gì?

Hãy hình dung `ResultSet` như một con trỏ đặt tại vị trí trong tập kết quả truy vấn. Có hai câu hỏi khác nhau:

- **Type:** Có thể đi theo hướng nào và kết quả có thể phản ánh thay đổi của dữ liệu bên dưới như thế nào?
- **Concurrency:** Chỉ đọc các hàng hay có thể dùng những phương thức cập nhật của `ResultSet` để sửa dữ liệu?

Hai chiều này độc lập về mặt API: một `ResultSet` có thể cho phép cuộn nhưng chỉ đọc, hoặc có thể cập nhật dù chỉ tiến về phía trước, nếu driver và truy vấn hỗ trợ.

```text
                         CONCURRENCY
                     READ_ONLY    UPDATABLE
                    +-----------+-----------+
 TYPE_FORWARD_ONLY  |  đọc xuôi  | đọc/cập  |
                    +-----------+-----------+
 TYPE_SCROLL_       |  cuộn,     | cuộn,    |
 INSENSITIVE        |  chỉ đọc   | cập nhật |
                    +-----------+-----------+
 TYPE_SCROLL_       |  cuộn, có  | cuộn, có |
 SENSITIVE          |  độ nhạy   | độ nhạy, |
                    |  thay đổi  | cập nhật |
                    +-----------+-----------+

Mọi ô đều phải được driver và câu SQL cụ thể hỗ trợ.
```

**“Concurrency” ở đây không phải số luồng Java được dùng chung `Statement` hay `Connection`.** Các hằng `CONCUR_READ_ONLY` và `CONCUR_UPDATABLE` mô tả khả năng cập nhật dữ liệu qua `ResultSet`, không bảo đảm an toàn khi nhiều thread cùng dùng một object JDBC. Transaction isolation và locking cũng là vấn đề riêng.

## 2. Các giá trị type của `ResultSet`

JDBC định nghĩa ba giá trị type cơ bản:

| Hằng | Di chuyển con trỏ | Ý nghĩa đối với thay đổi dữ liệu từ bên ngoài |
|---|---|---|
| `ResultSet.TYPE_FORWARD_ONLY` | Tiến về phía trước, chủ yếu bằng `next()` | Không hứa khả năng cuộn hoặc một ảnh chụp cố định của dữ liệu |
| `ResultSet.TYPE_SCROLL_INSENSITIVE` | Tiến/lùi, nhảy tới vị trí khi được hỗ trợ | Thông thường không phản ánh các thay đổi từ transaction khác xảy ra sau khi result set được tạo |
| `ResultSet.TYPE_SCROLL_SENSITIVE` | Tiến/lùi, nhảy tới vị trí khi được hỗ trợ | Có khả năng phản ánh những thay đổi dữ liệu trong khi result set còn mở; mức độ thực tế tùy driver/DBMS |

### 2.1. `TYPE_FORWARD_ONLY`

Đây thường là kiểu mặc định trong ví dụ JDBC căn bản. Con trỏ ban đầu đứng **trước hàng đầu tiên**, sau đó gọi `rs.next()` để dịch sang hàng kế tiếp:

```java
try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(
             "SELECT id, name FROM customers")) {

    while (rs.next()) {
        long id = rs.getLong("id");
        String name = rs.getString("name");
        System.out.println(id + " - " + name);
    }
}
```

Một result set forward-only không hứa hỗ trợ `previous()`, `absolute(...)`, `first()` hoặc `last()`. Đừng gọi chúng rồi dựa vào hành vi riêng của một driver nếu ứng dụng cần portable.

### 2.2. `TYPE_SCROLL_INSENSITIVE`

Ứng dụng có thể đi lại trong tập kết quả:

```java
Statement statement = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);
```

Trong một `ResultSet` thực sự có kiểu scrollable:

- `next()`: tới hàng sau.
- `previous()`: tới hàng trước.
- `first()` và `last()`: tới hàng đầu/cuối.
- `absolute(n)`: tới hàng thứ `n`, đếm từ 1; số âm đếm từ cuối.
- `relative(n)`: di chuyển tương đối từ vị trí hiện tại.
- `beforeFirst()` và `afterLast()`: đặt vị trí ngoài tập kết quả.
- `getRow()`: trả vị trí hàng hiện tại theo quy tắc API.

Tính “insensitive” nói về khả năng quan sát thay đổi của nguồn dữ liệu trong khi result set mở, **không phải cam kết toàn bộ transaction có snapshot isolation**. Việc thấy các thay đổi do chính result set tạo ra cũng phụ thuộc driver và chế độ cập nhật.

### 2.3. `TYPE_SCROLL_SENSITIVE`

Nếu được hỗ trợ, con trỏ vừa cuộn được vừa có khả năng nhận biết những thay đổi ở dữ liệu nền sau khi result set được tạo. Nhưng không thể khẳng định mọi `UPDATE`, `DELETE` hay `INSERT` của connection khác luôn xuất hiện ngay trong `ResultSet`; khả năng nhìn thấy thay đổi chịu ảnh hưởng của:

- DBMS, JDBC driver và kiểu cursor được hiện thực.
- Mức cô lập của transaction và thời điểm transaction khác commit.
- Cách driver fetch/cache hàng.
- Truy vấn cụ thể và khả năng nhận diện hàng.

Nhiều driver không hỗ trợ `TYPE_SCROLL_SENSITIVE` hoặc chỉ hỗ trợ một số điều kiện. Không chọn kiểu này chỉ vì muốn “dữ liệu tự cập nhật realtime”; nếu nghiệp vụ cần dữ liệu mới nhất, hãy thiết kế chiến lược truy vấn lại và ranh giới transaction phù hợp.

## 3. Hai giá trị concurrency của `ResultSet`

| Hằng | Có thể làm gì? | Giới hạn |
|---|---|---|
| `ResultSet.CONCUR_READ_ONLY` | Duyệt và đọc các cột bằng `getXxx(...)` | Không được dùng giao diện cập nhật hàng của `ResultSet` |
| `ResultSet.CONCUR_UPDATABLE` | Có thể gọi `updateXxx(...)`, `updateRow()` và các thao tác khác theo khả năng driver/query | Không tự bảo đảm truy vấn cụ thể có thể cập nhật hoặc tránh được xung đột đồng thời |

Một `ResultSet` được yêu cầu `CONCUR_UPDATABLE` thường phải được tạo từ truy vấn **đủ đơn giản để driver xác định được hàng nguồn**, ví dụ:

```sql
SELECT id, status
FROM inventory_items
WHERE id = ?
```

Truy vấn JOIN, GROUP BY, tổng hợp như `COUNT(*)`, `DISTINCT`, UNION hoặc truy vấn không có khóa định danh rõ ràng thường không updatable tùy driver. Ngay cả truy vấn đơn bảng cũng có thể không updatable nếu driver thiếu tính năng hoặc điều kiện khác chưa đạt.

Đừng đồng nhất `CONCUR_UPDATABLE` với `TRANSACTION_SERIALIZABLE`. Concurrency chỉ cho phép **cập nhật qua API của `ResultSet`**; isolation điều khiển các hiện tượng đọc/ghi giữa các transaction.

## 4. Yêu cầu type và concurrency khi tạo `Statement`

`Connection` cung cấp các overload:

```java
// Mặc định thường là forward-only, read-only:
Statement basic = connection.createStatement();

// Yêu cầu result set cuộn được, chỉ đọc:
Statement scrollable = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);

// Yêu cầu result set cuộn được và có thể cập nhật:
Statement updatable = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_UPDATABLE);
```

Đây là các đối tượng cần được đóng, nên trong code hoàn chỉnh hãy dùng `try-with-resources` thay vì tạo ba statement rồi để mở như đoạn minh họa.

Chú ý: lời gọi `createStatement(type, concurrency)` là **yêu cầu tại thời điểm tạo statement**. Nó không có nghĩa mọi query thực thi qua statement đó đều chắc chắn tạo đúng kiểu result set đã yêu cầu. Driver có thể không hỗ trợ tổ hợp hoặc không tạo được result set updatable cho một câu SQL cụ thể.

### 4.1. Ví dụ đầy đủ: tạo result set cuộn được

Schema minh họa:

```sql
CREATE TABLE customers (
    id   BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

INSERT INTO customers (id, name) VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');
```

Ví dụ Java:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.Statement;

public final class ScrollableCustomers {
    private ScrollableCustomers() {}

    public static void printFirstAndLast(DataSource dataSource)
            throws SQLException {

        String sql = "SELECT id, name FROM customers ORDER BY id";

        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement(
                     ResultSet.TYPE_SCROLL_INSENSITIVE,
                     ResultSet.CONCUR_READ_ONLY);
             ResultSet rs = statement.executeQuery(sql)) {

            if (rs.getType() == ResultSet.TYPE_FORWARD_ONLY) {
                throw new SQLFeatureNotSupportedException(
                        "Driver không cung cấp ResultSet cuộn được");
            }

            if (rs.first()) {
                System.out.println("Đầu: " + rs.getString("name"));
            }
            if (rs.last()) {
                System.out.println("Cuối: " + rs.getString("name"));
            }

            if (rs.absolute(2)) {
                System.out.println("Hàng 2: " + rs.getString("name"));
            }
        }
    }
}
```

Với ba hàng mẫu, kết quả lần lượt là `An`, `Chi`, `Binh`. Mã gọi `ORDER BY id` để kết quả có thứ tự ổn định; nếu không có `ORDER BY`, “hàng đầu” và “hàng thứ hai” không có thứ tự nghiệp vụ được bảo đảm.

`rs.first()` và `rs.last()` trả `false` nếu không có hàng để di chuyển tới. `rs.absolute(2)` trả `false` khi không có hàng thứ hai. Sau khi cursor di chuyển ra khỏi hàng hợp lệ, không gọi `rs.getXxx(...)` như thể vẫn đang đứng trên một hàng.

### 4.2. Không cần scroll chỉ để xử lý tuần tự

Nếu chỉ xuất danh sách theo thứ tự:

```java
try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(
             "SELECT id, name FROM customers ORDER BY id")) {

    while (rs.next()) {
        System.out.println(rs.getLong("id")
                + ": " + rs.getString("name"));
    }
}
```

`TYPE_FORWARD_ONLY` và `CONCUR_READ_ONLY` thường đơn giản hơn. Tùy driver và cấu hình, việc hỗ trợ scroll có thể yêu cầu buffer dữ liệu hoặc sử dụng cursor tài nguyên cao hơn. Không yêu cầu tính năng chỉ vì “có thể sẽ cần”.

## 5. `PreparedStatement` và `CallableStatement` cũng có overload

Khi SQL có tham số, vẫn nên dùng `PreparedStatement`; bạn có thể yêu cầu type và concurrency ngay lúc prepare:

```java
String sql = "SELECT id, name FROM customers WHERE id >= ? ORDER BY id";

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY)) {

    ps.setLong(1, 2L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.getType() == ResultSet.TYPE_FORWARD_ONLY) {
            throw new SQLFeatureNotSupportedException(
                    "Không hỗ trợ di chuyển con trỏ");
        }

        if (rs.first()) {
            System.out.println(rs.getString("name"));
        }
    }
}
```

Đoạn code nằm trong phương thức có `Connection connection` đang mở, cùng các import `java.sql.*` cần thiết. Dấu `?` vẫn được bind bằng `setLong` để tránh tự nối dữ liệu đầu vào vào SQL.

Tương tự, JDBC có overload:

```java
CallableStatement call = connection.prepareCall(
        "{call find_customers(?)}",
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);
```

Với stored procedure, tính năng thực tế còn phụ thuộc cách routine trả result set (kết quả trực tiếp hay con trỏ OUT) và driver. Không suy rằng việc yêu cầu type/concurrency cho `CallableStatement` nhất định áp đặt các thuộc tính ấy cho **mọi cursor trả qua tham số OUT**.

## 6. Kiểm tra khả năng của driver bằng `DatabaseMetaData`

Trước khi yêu cầu một kiểu result set nâng cao, có thể hỏi driver/database qua `DatabaseMetaData`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ResultSetSupport {
    private ResultSetSupport() {}

    public static void printCapabilities(DataSource dataSource)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            int[] types = {
                ResultSet.TYPE_FORWARD_ONLY,
                ResultSet.TYPE_SCROLL_INSENSITIVE,
                ResultSet.TYPE_SCROLL_SENSITIVE
            };

            int[] concurrencies = {
                ResultSet.CONCUR_READ_ONLY,
                ResultSet.CONCUR_UPDATABLE
            };

            for (int type : types) {
                System.out.println("Type " + type + " supported = "
                        + meta.supportsResultSetType(type));

                for (int concurrency : concurrencies) {
                    boolean supported = meta.supportsResultSetConcurrency(
                            type, concurrency);

                    System.out.println("  concurrency "
                            + concurrency + " supported = " + supported);
                }
            }
        }
    }
}
```

Hai kiểm tra quan trọng nhất:

- `supportsResultSetType(type)`: liệu DBMS/driver có hỗ trợ loại result set đó nói chung không?
- `supportsResultSetConcurrency(type, concurrency)`: liệu tổ hợp type và concurrency được hỗ trợ nói chung không?

**Metadata xác nhận một khả năng tổng quát, không bảo đảm mọi câu SELECT đều updatable.** Tùy cấu trúc SQL, DBMS và quy tắc của driver, truy vấn cụ thể vẫn có thể bị từ chối hoặc bị hạ concurrency về `CONCUR_READ_ONLY`.

Nếu `supportsResultSetType(...)` trả `false`, không nên gọi tiếp rồi kỳ vọng loại con trỏ ấy hoạt động như mong muốn. Nếu trả `true`, vẫn cần kiểm tra result set được tạo.

## 7. Kiểm tra type/concurrency thực tế sau `executeQuery()`

Có thể xem thuộc tính ở hai cấp:

```java
int requestedType = ResultSet.TYPE_SCROLL_INSENSITIVE;
int requestedConcurrency = ResultSet.CONCUR_UPDATABLE;

try (Statement statement = connection.createStatement(
        requestedType, requestedConcurrency);
     ResultSet rs = statement.executeQuery(
             "SELECT id, status FROM inventory_items")) {

    System.out.println("Statement type: "
            + statement.getResultSetType());
    System.out.println("Statement concurrency: "
            + statement.getResultSetConcurrency());

    System.out.println("Actual ResultSet type: " + rs.getType());
    System.out.println("Actual ResultSet concurrency: "
            + rs.getConcurrency());
}
```

`Statement.getResultSetType()` và `getResultSetConcurrency()` cho biết thuộc tính được gắn với statement theo driver; `ResultSet.getType()` và `getConcurrency()` mô tả chính đối tượng kết quả được trả về. **Khi cần hành vi của tập kết quả cụ thể, hãy kiểm tra `ResultSet` thực tế**.

Nếu cần cuộn mà kết quả chỉ là `TYPE_FORWARD_ONLY`, phải có phương án dự phòng: đọc xuôi rồi lưu dữ liệu vào danh sách Java, thay đổi luồng nghiệp vụ, phân trang bằng truy vấn mới hoặc báo tính năng không được hỗ trợ. Nếu cần cập nhật mà kết quả là `CONCUR_READ_ONLY`, dùng `PreparedStatement` với `UPDATE ... WHERE ...` hoặc thông báo không hỗ trợ, thay vì gọi `updateRow()` rồi bỏ qua lỗi.

### 7.1. SQLWarning và hạ cấp tính năng

Khi driver không thể đáp ứng type/concurrency đã yêu cầu, hành vi có thể là **trả về khả năng yếu hơn kèm cảnh báo** hoặc **ném `SQLException`/`SQLFeatureNotSupportedException`**, tùy API, driver và trường hợp.

```java
import java.sql.SQLWarning;

for (SQLWarning warning = statement.getWarnings();
     warning != null;
     warning = warning.getNextWarning()) {

    System.err.println("JDBC warning: SQLState="
            + warning.getSQLState()
            + ", message=" + warning.getMessage());
}
```

Đây là mã chạy trong phạm vi có `Statement statement`. Khi chẩn đoán có thể xem `Connection.getWarnings()` hoặc cảnh báo ở `ResultSet` nếu driver cung cấp. Nhưng **không dựa chỉ vào cảnh báo** để biết tính năng thực tế: một số driver không phát cảnh báo đủ rõ; hãy đối chiếu `rs.getType()` và `rs.getConcurrency()`.

## 8. Cập nhật hàng qua `CONCUR_UPDATABLE`

Đối với result set updatable, quy trình là:

1. Truy vấn những cột/hàng mà driver có thể ánh xạ về bảng nguồn.
2. Đảm bảo `rs.getConcurrency() == CONCUR_UPDATABLE`.
3. Di chuyển cursor tới hàng mong muốn.
4. Dùng `rs.updateXxx(column, value)` để đặt giá trị cập nhật trong vùng cập nhật của hàng hiện tại.
5. Gọi `rs.updateRow()` để yêu cầu áp dụng thay đổi cho hàng đó.
6. Quản lý `commit()`/`rollback()` nếu đây là một phần của transaction nghiệp vụ.

`updateString(...)` **không tự đồng nghĩa với SQL UPDATE đã được áp dụng**. Cần gọi `updateRow()` để ghi những cập nhật đang chờ của hàng hiện tại.

### 8.1. Ví dụ đầy đủ: sửa trạng thái bản ghi

Giả sử có bảng:

```sql
CREATE TABLE inventory_items (
    id     BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

INSERT INTO inventory_items (id, status)
VALUES (7, 'NEW'), (8, 'NEW');
```

Ví dụ Java dùng `PreparedStatement` để truyền ID, đồng thời yêu cầu updatable result set. Vì một số driver chỉ hỗ trợ updatable cursor cho những dạng SELECT đơn bảng nhất định, đoạn mã kiểm tra khả năng thực tế và ném lỗi rõ ràng khi không được hỗ trợ.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;

public final class UpdatableResultSetDemo {
    private UpdatableResultSetDemo() {}

    public static void changeStatus(
            DataSource source, long itemId, String newStatus)
            throws SQLException {

        if (newStatus == null || newStatus.isBlank()) {
            throw new IllegalArgumentException("Trạng thái không hợp lệ");
        }

        String sql =
                "SELECT id, status FROM inventory_items WHERE id = ?";

        try (Connection connection = source.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement ps = connection.prepareStatement(
                        sql,
                        ResultSet.TYPE_FORWARD_ONLY,
                        ResultSet.CONCUR_UPDATABLE)) {

                    ps.setLong(1, itemId);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.getConcurrency()
                                != ResultSet.CONCUR_UPDATABLE) {
                            throw new SQLFeatureNotSupportedException(
                                    "Query không cung cấp updatable ResultSet");
                        }

                        if (!rs.next()) {
                            throw new SQLException(
                                    "Không tìm thấy bản ghi id=" + itemId);
                        }

                        rs.updateString("status", newStatus);
                        rs.updateRow();
                    }
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
}
```

Gọi:

```java
UpdatableResultSetDemo.changeStatus(dataSource, 7L, "ACTIVE");
```

Nếu driver hỗ trợ dạng query này và cập nhật thành công, `status` của hàng ID 7 là `ACTIVE` sau commit. Nếu không hỗ trợ updatable result set, lỗi phải được xử lý theo chính sách ứng dụng.

**Với CRUD thông thường, câu SQL `UPDATE` tham số hóa vẫn là lựa chọn đơn giản và dễ kiểm soát hơn.** Đặc biệt, nếu cần điều kiện cập nhật dựa trên phiên bản bản ghi hoặc trạng thái cũ, `PreparedStatement.executeUpdate()` cho phép diễn đạt ràng buộc một cách minh bạch.

### 8.2. Các thao tác updatable khác

Tùy driver và query, các phương thức còn có:

| Phương thức | Mục đích | Cần lưu ý |
|---|---|---|
| `updateXxx(...)` | Gán giá trị cột của hàng hiện tại để chuẩn bị cập nhật | Chưa đồng nghĩa dữ liệu DB đã được cập nhật |
| `updateRow()` | Áp dụng các thay đổi đang chờ của hàng hiện tại | Có thể ném `SQLException` nếu không hợp lệ/không hỗ trợ |
| `cancelRowUpdates()` | Hủy các thay đổi đang chờ trên hàng hiện tại trước `updateRow()` | Không rollback các update đã thực hiện |
| `moveToInsertRow()`, `insertRow()` | Chuẩn bị và chèn hàng bằng result set | Chỉ áp dụng cho result set và driver cho phép |
| `deleteRow()` | Xóa hàng hiện tại qua result set | Có thể bị giới hạn bởi driver và khóa/ràng buộc |
| `refreshRow()` | Yêu cầu làm mới giá trị hàng hiện tại | Không bảo đảm giống nhau giữa mọi DBMS/isolation |
| `rowUpdated()`, `rowDeleted()`, `rowInserted()` | Hỏi trạng thái thay đổi hàng khi được hỗ trợ | Không mặc định các cờ phát hiện được driver hỗ trợ |

**`cancelRowUpdates()` không phải `Connection.rollback()`**. Nó chỉ hủy những giá trị chưa được áp dụng bằng `updateRow()` trên hàng đang xét. Nếu cần hủy những lệnh SQL đã được áp dụng nhưng chưa commit, dùng rollback ở phạm vi transaction.

## 9. Giới hạn query updatable và an toàn đồng thời

Một số lý do driver có thể từ chối `CONCUR_UPDATABLE` cho một query dù DatabaseMetaData báo hỗ trợ tổ hợp:

- Truy vấn JOIN nhiều bảng khiến driver không xác định được một hàng nguồn cần cập nhật.
- Truy vấn `GROUP BY`, `DISTINCT`, phép tổng hợp hoặc tập hợp khác.
- Không có thông tin khóa/định danh hàng cần cập nhật, hoặc không chọn đủ cột mà driver yêu cầu.
- View không hỗ trợ cập nhật.
- Driver không có khả năng cập nhật thông qua `ResultSet`, hoặc chỉ hỗ trợ một dạng SQL đơn giản.
- Quyền truy cập DB không cho phép `UPDATE`/`DELETE` tương ứng.

Nếu ứng dụng cần cập nhật bền vững trên nhiều DBMS, cân nhắc SQL cập nhật tường minh:

```java
String sql =
        "UPDATE inventory_items SET status = ? WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, newStatus);
    ps.setLong(2, itemId);

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new SQLException("Không cập nhật đúng một bản ghi");
    }
}
```

Khi cần ngăn **lost update**, có thể dùng cột `version` và điều kiện `WHERE id = ? AND version = ?` cùng việc tăng phiên bản trên một lệnh `UPDATE`. Concurrency `CONCUR_UPDATABLE` tự nó **không thay thế** optimistic locking, mức cô lập giao dịch hoặc cách giải quyết xung đột.

Một số DBMS/driver có thể dùng khóa trên hàng trong quá trình tạo hoặc cập nhật cursor; loại khóa và thời điểm giữ khóa không được bảo đảm thống nhất chỉ từ hai hằng type/concurrency. Để kiểm soát transaction và lock contention, cần hiểu cách driver thực thi và cấu hình isolation của hệ quản trị.

## 10. Type, concurrency và holdability là ba thuộc tính khác nhau

Ngoài hai tham số của bài học, JDBC còn có **holdability**, tức hành vi giữ hoặc đóng cursor qua commit:

| Thuộc tính | Ví dụ hằng | Quyết định điều gì? |
|---|---|---|
| Type | `TYPE_SCROLL_INSENSITIVE` | Có thể di chuyển con trỏ và mức độ thấy dữ liệu thay đổi |
| Concurrency | `CONCUR_READ_ONLY` | Chỉ đọc hay có thể cập nhật thông qua result set |
| Holdability | `HOLD_CURSORS_OVER_COMMIT` hoặc `CLOSE_CURSORS_AT_COMMIT` | Cursor được giữ hay đóng khi commit theo khả năng driver/DBMS |

JDBC hỗ trợ overload ba đối số:

```java
Statement statement = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY,
        ResultSet.CLOSE_CURSORS_AT_COMMIT);
```

Có thể kiểm tra:

```java
DatabaseMetaData meta = connection.getMetaData();

boolean holdSupported = meta.supportsResultSetHoldability(
        ResultSet.CLOSE_CURSORS_AT_COMMIT);

int connectionHoldability = connection.getHoldability();
```

Holdability không quyết định liệu result set có updatable hay scrollable. Trên một số DBMS/driver, cursor phía server có thể bị ràng buộc vào transaction, nên các tham số holdability cần được kiểm thử thực tế; chúng không phải phương thức thay thế quản lý connection và transaction đúng cách.

Với đa số code đọc dữ liệu, nên **đóng `ResultSet` và `Statement` trước khi commit hoặc đóng connection** nếu không cần giữ cursor qua biên transaction. Không nên để một result set tồn tại lâu chỉ vì driver tuyên bố hỗ trợ holdability.

## 11. Tác động hiệu năng và tài nguyên

Lựa chọn type/concurrency có thể ảnh hưởng tài nguyên và cách driver truyền dữ liệu, nhưng **không có quy tắc universal** rằng mọi scrollable result set đều chậm, hay mọi forward-only result set đều stream trên server.

| Nhu cầu | Lựa chọn thường phù hợp | Điều cần xác minh |
|---|---|---|
| Đọc tuần tự nhiều hàng | `TYPE_FORWARD_ONLY` + `CONCUR_READ_ONLY` | Cách fetch, memory, transaction, `setFetchSize(...)` |
| Hiển thị vài trang dữ liệu nhỏ và cần duyệt qua lại | `TYPE_SCROLL_INSENSITIVE` + `CONCUR_READ_ONLY` nếu hỗ trợ | Driver có nạp dữ liệu vào memory không, dữ liệu có thay đổi trong lúc mở không |
| Phát hiện thay đổi từ các transaction khác trong một result set đang mở | `TYPE_SCROLL_SENSITIVE` nếu hỗ trợ thật sự | Metadata visibility, isolation và kiểm thử đồng thời |
| Cập nhật hàng qua cursor | `CONCUR_UPDATABLE` nếu query updatable | Kiểu SQL, khóa định danh, locking, transaction, phép cập nhật |
| Phân trang dữ liệu lớn | `PreparedStatement` với phân trang phù hợp DBMS | Thứ tự ổn định, index và chi phí offset/keyset |

Lưu ý về `Statement.setFetchSize(int)`: đây thường là **gợi ý** về số hàng driver nên fetch mỗi lần, không phải giới hạn cứng số hàng của `ResultSet` và không biến một result set forward-only thành cursor streaming trong mọi driver. Một số driver chỉ áp dụng fetching từng đợt khi auto-commit, transaction và các tùy chọn riêng đáp ứng yêu cầu của chúng.

Nếu mục tiêu là hiển thị một trang thứ 10 trong bảng hàng triệu dòng, đừng tự động đọc toàn bộ result set scrollable vào memory rồi gọi `absolute(...)`. Phân trang trên DB với `ORDER BY` và kỹ thuật offset/keyset thường phù hợp hơn.

## 12. Cảnh báo driver và cách fallback rõ ràng

Ứng dụng nên phân biệt ba kết quả khi yêu cầu tính năng nâng cao:

1. **Driver đáp ứng đúng yêu cầu:** result set thực tế có type/concurrency phù hợp.
2. **Driver trả result set khả năng thấp hơn:** có thể kèm `SQLWarning`; ứng dụng phải chọn fallback rõ ràng.
3. **Driver báo không hỗ trợ:** `SQLException` hoặc `SQLFeatureNotSupportedException`; code xử lý theo yêu cầu nghiệp vụ.

Mẫu quyết định:

```java
int requestedType = ResultSet.TYPE_SCROLL_INSENSITIVE;
int requestedConcurrency = ResultSet.CONCUR_READ_ONLY;

DatabaseMetaData meta = connection.getMetaData();

if (!meta.supportsResultSetType(requestedType)
        || !meta.supportsResultSetConcurrency(
                requestedType, requestedConcurrency)) {

    // Chiến lược ứng dụng: sử dụng read-forward hoặc báo lỗi.
    throw new SQLFeatureNotSupportedException(
            "Driver không hỗ trợ result set yêu cầu");
}
```

Khi dùng fallback dạng đọc xuôi, hãy **tạo statement mới với khả năng đã chọn**, vì một object `ResultSet` đang mở không được “đổi type tại chỗ” bằng việc đổi tham số sau `executeQuery()`.

Đừng coi `TYPE_SCROLL_INSENSITIVE` là một cơ chế cache nghiệp vụ đáng tin cậy khi cần nhất quán dữ liệu. Cache có TTL, chiến lược làm mới và isolation phải được thiết kế riêng theo yêu cầu.

## 13. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi `rs.previous()` trên `TYPE_FORWARD_ONLY` | `SQLException` hoặc chức năng không hoạt động | Yêu cầu scrollable và kiểm tra `rs.getType()` |
| Dùng `rs.absolute(n)` mà không có `ORDER BY` | “Hàng thứ n” không ổn định theo nghiệp vụ | Dùng thứ tự SQL tường minh |
| Chỉ tin `supportsResultSetConcurrency(...)` mà không kiểm tra result set | Một query cụ thể vẫn có thể read-only | Kiểm tra `rs.getConcurrency()` sau execute |
| Coi `CONCUR_UPDATABLE` là tránh được lost update | Xung đột cập nhật dữ liệu có thể không được giải quyết | Dùng isolation/locking, optimistic version và điều kiện UPDATE phù hợp |
| Nghĩ `updateString(...)` đã ghi SQL UPDATE | Thay đổi chưa được áp dụng qua cursor | Gọi `updateRow()` rồi commit nếu cần |
| Dùng `cancelRowUpdates()` để hủy một UPDATE đã chạy | Dữ liệu chưa commit vẫn bị thay đổi | Sử dụng `Connection.rollback()` theo phạm vi |
| Yêu cầu scroll-sensitive vì muốn đồng bộ realtime | Driver/DBMS có thể không phản ánh mọi thay đổi | Truy vấn lại hoặc thiết kế cơ chế đồng bộ thích hợp |
| Tạo scrollable cursor cho hàng triệu dòng | Memory và tài nguyên có thể tăng mạnh | Ưu tiên forward-only hoặc phân trang |
| Nhầm concurrency với thread safety | Có thể chia sẻ JDBC object sai cách giữa nhiều thread | Quản lý connection/statement theo phạm vi sử dụng |
| Thấy `createStatement(...)` không lỗi nên chắc chắn result set updatable | Driver có thể downgrade hoặc query không phù hợp | Xem `rs.getType()` và `rs.getConcurrency()` |
| Để `ResultSet` còn mở khi connection bị đóng | Không thể đọc tiếp, tài nguyên rò rỉ | Dùng `try-with-resources` và ánh xạ dữ liệu trong scope |
| Dùng `setAutoCommit(true)` để dọn transaction trước khi rollback | Có thể commit transaction đang hoạt động | Kết thúc transaction tường minh trước khi đổi cấu hình |

## 14. Bài thực hành và kiểm thử tích hợp

Có thể dùng bảng `customers` và `inventory_items` ở các phần trên, chạy trên chính DBMS/driver của ứng dụng.

**Bài 1 — xác minh mặc định.** Tạo `Statement` bằng `createStatement()`, thực hiện SELECT và in `rs.getType()`, `rs.getConcurrency()`. Không tự đoán rằng mọi driver mặc định cùng hành vi nếu chưa kiểm tra phiên bản đang dùng.

**Bài 2 — di chuyển con trỏ.** Yêu cầu `TYPE_SCROLL_INSENSITIVE`, `CONCUR_READ_ONLY`; chạy `SELECT ... ORDER BY id`, thử `first()`, `last()`, `absolute(2)`, `previous()` và `beforeFirst()`. Kiểm tra cả tập 0 hàng và 1 hàng.

**Bài 3 — driver không hỗ trợ.** Xem `supportsResultSetType(TYPE_SCROLL_SENSITIVE)` và `supportsResultSetConcurrency(TYPE_SCROLL_SENSITIVE, CONCUR_UPDATABLE)`. Nếu không hỗ trợ, xác minh ứng dụng báo lỗi rõ ràng hoặc chuyển sang đường xử lý khác.

**Bài 4 — cập nhật qua `ResultSet`.** Dùng `CONCUR_UPDATABLE` trên một query đơn bảng. Sau `updateString(...)` và `updateRow()`, commit rồi mở connection mới để xác minh trạng thái. Lặp lại với rollback để đảm bảo cập nhật chưa commit được hủy.

**Bài 5 — truy vấn không updatable.** Dùng JOIN hoặc truy vấn tổng hợp, yêu cầu `CONCUR_UPDATABLE` và quan sát `SQLException`, cảnh báo hoặc kết quả `CONCUR_READ_ONLY`. Ghi rõ driver có hành vi nào, không viết test giả định tất cả DBMS phản ứng giống nhau.

**Bài 6 — hai transaction đồng thời.** Giữ một `TYPE_SCROLL_SENSITIVE` nếu được hỗ trợ ở connection A, cập nhật hàng từ connection B và commit. Quan sát liệu A có thấy giá trị mới hay không tại isolation đã chọn. So sánh với `TYPE_SCROLL_INSENSITIVE`. Đây là phép thử **tùy nền tảng**, không phải kết quả bắt buộc chung.

**Bài 7 — chi phí tài nguyên.** Đo thời gian tạo/result set, memory và thời gian duyệt 100, 10.000, 100.000 hàng giữa forward-only, scrollable và phân trang SQL. Kiểm tra `setFetchSize(...)` có thay đổi hành vi trên driver đang dùng hay không.

**Bài 8 — quản lý tài nguyên.** Xác nhận `ResultSet`, `Statement` và `Connection` được đóng khi code thành công hoặc ném exception. Nếu dùng connection pool, kiểm tra không có connection bị giữ lâu do quên đóng cursor.

Trong báo cáo kiểm thử nên ghi **DBMS**, **driver/version**, **SQL**, **type/concurrency yêu cầu**, **type/concurrency thực tế**, **SQLWarning**, **isolation**, **holdability** và kết quả quan sát. Một ví dụ chạy đúng trên H2 hoặc một database test không bảo đảm hoạt động y hệt trên driver của production.

## Ghi nhớ

- **Type** quyết định khả năng di chuyển và mức độ nhạy với thay đổi của `ResultSet`: `TYPE_FORWARD_ONLY`, `TYPE_SCROLL_INSENSITIVE`, `TYPE_SCROLL_SENSITIVE`.
- **Concurrency** quyết định khả năng cập nhật qua `ResultSet`: `CONCUR_READ_ONLY` hoặc `CONCUR_UPDATABLE`.
- Yêu cầu type/concurrency ngay lúc gọi **`Connection.createStatement(type, concurrency)`** hoặc các overload tương ứng của `prepareStatement`/`prepareCall`.
- **Kiểm tra `DatabaseMetaData` trước, kiểm tra `rs.getType()` và `rs.getConcurrency()` sau**: driver và query cụ thể có thể không đáp ứng tổ hợp yêu cầu.
- Cập nhật qua cursor cần `updateXxx(...)` rồi `updateRow()`; transaction vẫn cần `commit()`/`rollback()` đúng phạm vi.
- **Holdability**, **transaction isolation**, **locking** và **thread safety** là những khái niệm khác với type/concurrency.
- Mặc định **forward-only, read-only** thường phù hợp khi đọc tuần tự. Chỉ chọn tính năng nâng cao khi nghiệp vụ cần và driver hỗ trợ được xác minh.

Hiểu rõ hai tham số này giúp ứng dụng JDBC sử dụng `ResultSet` nâng cao đúng cách, tránh giả định sai về khả năng của driver và giữ việc truy cập, cập nhật dữ liệu rõ ràng về tài nguyên lẫn transaction.
