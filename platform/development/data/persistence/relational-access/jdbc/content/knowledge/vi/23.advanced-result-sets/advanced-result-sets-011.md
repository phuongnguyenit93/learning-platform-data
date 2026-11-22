# Xác minh cấu hình yêu cầu và cấu hình thực tế được cấp trong JDBC

Khi cần `ResultSet` có thể cuộn qua các hàng, cập nhật trực tiếp hoặc giữ mở sau `commit()`, lập trình viên JDBC thường truyền thêm tham số lúc gọi `Connection.createStatement(...)` hoặc `Connection.prepareStatement(...)`. Tuy nhiên, **cấu hình yêu cầu không đồng nghĩa với khả năng thực tế của `ResultSet` được trả về**: JDBC driver, hệ quản trị cơ sở dữ liệu (DBMS), câu SQL và trạng thái transaction đều có thể ảnh hưởng kết quả.

Ví dụ, ứng dụng yêu cầu `TYPE_SCROLL_INSENSITIVE` và `CONCUR_UPDATABLE`, nhưng truy vấn `SELECT` có `JOIN` khiến driver chỉ cấp một tập kết quả **chỉ đọc**. Nếu chương trình tin hoàn toàn vào các tham số đã truyền mà không kiểm tra `rs.getConcurrency()`, lỗi có thể chỉ xuất hiện khi gọi `updateRow()` ở bước nghiệp vụ sau.

Bài học thuộc chương **ResultSet nâng cao** của module JDBC. Mục tiêu là biết cách **yêu cầu → kiểm tra khả năng → đối chiếu cấu hình được cấp → xử lý khác biệt** qua các API chuẩn: `DataSource`, `Connection`, `DatabaseMetaData`, `Statement`, `PreparedStatement`, `CallableStatement` và `ResultSet`.

## 1. Ba lớp thông tin phải phân biệt

Khi tạo một result set nâng cao, có ba nguồn thông tin riêng:

1. **Yêu cầu của ứng dụng:** các hằng truyền vào `createStatement(...)`, `prepareStatement(...)` hoặc `prepareCall(...)`.
2. **Khả năng được công bố:** các phương thức `DatabaseMetaData.supportsResultSetType(...)`, `supportsResultSetConcurrency(...)` và `supportsResultSetHoldability(...)`.
3. **Cấu hình thực tế:** giá trị đọc từ `Statement` và, quan trọng nhất, từ **`ResultSet` được trả về sau khi thực thi câu SQL cụ thể**.

Bảng đối chiếu:

| Thuộc tính | Giá trị ứng dụng yêu cầu | Kiểm tra tổng quát trước khi chạy | Kiểm tra đối tượng thực tế |
|---|---|---|---|
| Type | `TYPE_FORWARD_ONLY`, `TYPE_SCROLL_INSENSITIVE` hoặc `TYPE_SCROLL_SENSITIVE` | `meta.supportsResultSetType(type)` | `rs.getType()` |
| Concurrency | `CONCUR_READ_ONLY` hoặc `CONCUR_UPDATABLE` | `meta.supportsResultSetConcurrency(type, concurrency)` | `rs.getConcurrency()` |
| Holdability | `HOLD_CURSORS_OVER_COMMIT` hoặc `CLOSE_CURSORS_AT_COMMIT` | `meta.supportsResultSetHoldability(holdability)` | `rs.getHoldability()` |
| Fetch direction | `FETCH_FORWARD`, `FETCH_REVERSE`, `FETCH_UNKNOWN` | Không có bảo đảm chung rằng mọi hướng đều được hỗ trợ cho mọi type | `rs.getFetchDirection()`, kiểm thử hành vi khi cần |
| Fetch size | Số hàng **gợi ý** cho mỗi đợt lấy dữ liệu | Khả năng thực thi do driver quyết định | `rs.getFetchSize()` và đo fetch thực tế |

Một số tài liệu hoặc cấu hình gọi chung là *requested settings* và *effective settings*. Ở JDBC, không có một object chuẩn duy nhất chứa tất cả các thuộc tính được cấp; phải xem **đúng cấp** của từng API.

**Nguyên tắc quan trọng:** `DatabaseMetaData` chỉ cho biết khả năng **nói chung** của driver/DBMS. Một tổ hợp được công bố là hỗ trợ vẫn có thể không phù hợp với **một truy vấn SQL cụ thể**. Cách kiểm chứng cuối cùng là kiểm tra `ResultSet` thật, đồng thời xử lý ngoại lệ và cảnh báo.

## 2. Type, concurrency và holdability có ý nghĩa gì?

### 2.1. Type: khả năng di chuyển và mức độ nhạy dữ liệu

JDBC có ba kiểu `ResultSet` cơ bản:

| Hằng | Di chuyển con trỏ | Đặc tính |
|---|---|---|
| `ResultSet.TYPE_FORWARD_ONLY` | Chủ yếu gọi `next()` để duyệt một chiều | Không bảo đảm `previous()`, `absolute()`, `first()` |
| `ResultSet.TYPE_SCROLL_INSENSITIVE` | Có thể di chuyển tiến/lùi và đến vị trí cụ thể | Thông thường không phản ánh thay đổi từ transaction khác sau khi tạo result set |
| `ResultSet.TYPE_SCROLL_SENSITIVE` | Có thể di chuyển tiến/lùi | Có khả năng phản ánh một số thay đổi của dữ liệu nền; mức độ thực tế phụ thuộc DBMS/driver/isolation |

Không được suy rằng `TYPE_SCROLL_INSENSITIVE` là một bản sao dữ liệu bất biến trong mọi điều kiện transaction. Tương tự, `TYPE_SCROLL_SENSITIVE` không có nghĩa mọi thay đổi từ một kết nối khác sẽ ngay lập tức hiện lên trong Java; snapshot, khóa, caching và cách driver fetch dữ liệu vẫn có vai trò.

### 2.2. Concurrency: chỉ đọc hay có thể cập nhật qua `ResultSet`

- `ResultSet.CONCUR_READ_ONLY`: đọc hàng, không dùng API cập nhật hàng của `ResultSet`.
- `ResultSet.CONCUR_UPDATABLE`: driver có thể cho phép `updateXxx(...)`, `updateRow()`, `insertRow()` và `deleteRow()` trên result set phù hợp.

**Concurrency ở đây không phải thread-safety** và cũng không phải mức cô lập giao dịch. `CONCUR_UPDATABLE` không ngăn *lost update* trong mọi trường hợp và không thay thế optimistic locking hay `Connection.setTransactionIsolation(...)`.

### 2.3. Holdability: ảnh hưởng của `commit()` đến cursor

Hai hằng:

- `ResultSet.HOLD_CURSORS_OVER_COMMIT`: yêu cầu giữ cursor mở sau commit.
- `ResultSet.CLOSE_CURSORS_AT_COMMIT`: yêu cầu đóng cursor khi commit.

Đây là thuộc tính tách biệt với type/concurrency. Driver có thể có giới hạn khi kết hợp holdability với server-side cursor, scrollability hoặc updatability. Dù báo hỗ trợ, ứng dụng vẫn phải kiểm thử vòng đời cursor sau commit trong hoàn cảnh cụ thể.

Chú ý **`Connection.getHoldability()` là giá trị mặc định hiện tại của connection**, không đương nhiên là thuộc tính của mọi `ResultSet` được tạo bằng overload có tham số holdability riêng.

## 3. Cách yêu cầu cấu hình khi tạo statement

### 3.1. `Statement`

`Connection.createStatement(...)` có các overload:

```java
// Dùng mặc định của driver/connection:
Statement basic = connection.createStatement();

// Yêu cầu type + concurrency:
Statement scrollReadOnly = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);

// Yêu cầu type + concurrency + holdability:
Statement scrollUpdatable = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_UPDATABLE,
        ResultSet.CLOSE_CURSORS_AT_COMMIT);
```

Các dòng trên chỉ minh họa chữ ký API. Trong ứng dụng, hãy **đóng từng `Statement`** bằng `try-with-resources`; không sao chép đoạn trên để giữ ba statement mở cùng lúc.

### 3.2. `PreparedStatement`

Khi SQL có tham số, vẫn nên ưu tiên `PreparedStatement`:

```java
String sql = "SELECT id, status FROM inventory_items WHERE id >= ?";

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY,
        ResultSet.CLOSE_CURSORS_AT_COMMIT)) {

    ps.setLong(1, 10L);

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc cấu hình thực tế và xử lý dữ liệu ở đây.
    }
}
```

Các overload cấu hình này không làm mất lợi ích tham số hóa. Giá trị `10L` được truyền bằng `setLong(...)`, không được nối thẳng vào chuỗi SQL.

### 3.3. `CallableStatement`

`Connection.prepareCall(...)` cũng có các overload nhận type, concurrency và holdability:

```java
CallableStatement call = connection.prepareCall(
        "{call list_inventory(?)}",
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY,
        ResultSet.CLOSE_CURSORS_AT_COMMIT);
```

Nhưng với stored procedure, driver có thể xử lý *result set trực tiếp* và *cursor được trả qua tham số OUT* theo những cơ chế khác nhau. Yêu cầu cho `CallableStatement` **không phải cam kết rằng mọi REF_CURSOR OUT** cũng có đúng các thuộc tính ấy. Phải kiểm tra từng `ResultSet` được trả ra.

## 4. Kiểm tra hỗ trợ trước khi tạo statement

Một bước *preflight* hữu ích là gọi `DatabaseMetaData` trên **đúng connection của ứng dụng**:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ResultSetCapabilityCheck {
    private ResultSetCapabilityCheck() {}

    public static void printCapabilities(DataSource dataSource)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            int type = ResultSet.TYPE_SCROLL_INSENSITIVE;
            int concurrency = ResultSet.CONCUR_UPDATABLE;
            int holdability = ResultSet.CLOSE_CURSORS_AT_COMMIT;

            System.out.println("Scroll type supported: "
                    + meta.supportsResultSetType(type));

            System.out.println("Type/concurrency supported: "
                    + meta.supportsResultSetConcurrency(
                            type, concurrency));

            System.out.println("Holdability supported: "
                    + meta.supportsResultSetHoldability(holdability));

            System.out.println("Connection default holdability: "
                    + connection.getHoldability());

            System.out.println("DatabaseMetaData default holdability: "
                    + meta.getResultSetHoldability());
        }
    }
}
```

Cần đọc đúng ý nghĩa của các giá trị:

- `supportsResultSetType(type)`: khả năng tổng quát cho loại result set.
- `supportsResultSetConcurrency(type, concurrency)`: khả năng tổng quát của **tổ hợp**, không chỉ concurrency riêng lẻ.
- `supportsResultSetHoldability(holdability)`: mức hỗ trợ chính sách giữ cursor.
- `getResultSetHoldability()` của `DatabaseMetaData` và `getHoldability()` của `Connection`: thông tin **mặc định**, không phản ánh một yêu cầu override của statement.
- Ba kết quả hỗ trợ `true` **không bảo đảm** mọi kết hợp ba thuộc tính đều khả dụng cho mọi câu SQL. Vì JDBC cung cấp phép kiểm tra riêng, cần xử lý trường hợp kết hợp cụ thể bị từ chối lúc tạo hoặc thực thi.

Nếu driver báo `false`, ứng dụng nên chọn cấu hình khác hoặc từ chối tính năng. Nếu driver báo `true`, hãy tiếp tục đo **kết quả thực tế**, không coi như đã xác minh xong.

## 5. Đối chiếu ba cấp: yêu cầu, statement và result set

Sau khi `createStatement(...)` hoặc `prepareStatement(...)` thành công, có thể kiểm tra thuộc tính statement:

- `statement.getResultSetType()`;
- `statement.getResultSetConcurrency()`;
- `statement.getResultSetHoldability()`.

Sau khi chạy `executeQuery()`, hãy kiểm tra ngay trên result set:

- `rs.getType()`;
- `rs.getConcurrency()`;
- `rs.getHoldability()`.

Ví dụ quan trọng là **không gộp hai nhóm getter này thành một**. `Statement` cho biết trạng thái/cấu hình mà driver gắn cho statement; `ResultSet` mô tả chính đối tượng kết quả tạo bởi SQL đó.

| Cấp | Thời điểm | Điều có thể kết luận |
|---|---|---|
| Biến `requestedType`, `requestedConcurrency`, `requestedHoldability` | Trước khi tạo statement | Ứng dụng **muốn gì** |
| `DatabaseMetaData` | Trước khi thực thi | Driver/DBMS **báo có thể hỗ trợ gì nói chung** |
| `Statement.getResultSet...()` | Sau khi tạo statement | Statement **đang có thuộc tính gì** theo driver |
| `ResultSet.getType()/getConcurrency()/getHoldability()` | Sau `executeQuery()` | Result set **thực tế được cấp thuộc tính gì** |
| Thực nghiệm `previous()`, `updateRow()`, commit | Khi cần khẳng định hành vi đặc biệt | Hành vi **thực tế trong ngữ cảnh SQL/isolation/driver** |

Một số driver có thể **hạ cấp (downgrade)** type hoặc concurrency; một số khác ném `SQLFeatureNotSupportedException` hay `SQLException`. Không viết code dựa trên giả định “nếu tạo statement thành công thì mọi thuộc tính đều đúng”.

## 6. Ví dụ hoàn chỉnh: kiểm tra nghiêm ngặt cấu hình thực tế

Giả sử ta cần **đọc kết quả có thể cuộn**, không cập nhật hàng qua `ResultSet`, và muốn cursor bị đóng khi commit. Yêu cầu của tính năng là **bắt buộc**: nếu driver không cấp đúng, service phải báo lỗi có ý nghĩa thay vì tự chạy sai.

Bảng ví dụ (SQL chung, có thể cần chỉnh kiểu dữ liệu theo DBMS):

```sql
CREATE TABLE inventory_items (
    id       BIGINT PRIMARY KEY,
    sku      VARCHAR(80) NOT NULL,
    status   VARCHAR(30) NOT NULL
);

INSERT INTO inventory_items (id, sku, status)
VALUES (1, 'A-100', 'NEW'),
       (2, 'A-200', 'READY'),
       (3, 'B-300', 'NEW');
```

Mã Java sau lưu **giá trị đã yêu cầu** trong các biến, đọc thuộc tính statement/result set rồi kiểm tra khớp:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLWarning;

public final class VerifiedScrollableQuery {
    private VerifiedScrollableQuery() {}

    public static void printFirstAndLast(DataSource dataSource)
            throws SQLException {

        final int requestedType =
                ResultSet.TYPE_SCROLL_INSENSITIVE;
        final int requestedConcurrency =
                ResultSet.CONCUR_READ_ONLY;
        final int requestedHoldability =
                ResultSet.CLOSE_CURSORS_AT_COMMIT;

        String sql = "SELECT id, sku, status " +
                "FROM inventory_items ORDER BY id";

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            if (!meta.supportsResultSetType(requestedType)
                    || !meta.supportsResultSetConcurrency(
                            requestedType, requestedConcurrency)
                    || !meta.supportsResultSetHoldability(
                            requestedHoldability)) {

                throw new SQLFeatureNotSupportedException(
                        "Driver không công bố hỗ trợ cấu hình yêu cầu");
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    sql, requestedType, requestedConcurrency,
                    requestedHoldability)) {

                System.out.println("Statement: "
                        + ps.getResultSetType() + " / "
                        + ps.getResultSetConcurrency() + " / "
                        + ps.getResultSetHoldability());

                printWarnings("statement before query", ps.getWarnings());

                try (ResultSet rs = ps.executeQuery()) {
                    printWarnings("statement after query",
                            ps.getWarnings());
                    printWarnings("result set", rs.getWarnings());

                    int actualType = rs.getType();
                    int actualConcurrency = rs.getConcurrency();
                    int actualHoldability = rs.getHoldability();

                    System.out.println("Requested: "
                            + requestedType + " / "
                            + requestedConcurrency + " / "
                            + requestedHoldability);

                    System.out.println("Actual ResultSet: "
                            + actualType + " / "
                            + actualConcurrency + " / "
                            + actualHoldability);

                    if (actualType != requestedType
                            || actualConcurrency != requestedConcurrency
                            || actualHoldability != requestedHoldability) {

                        throw new SQLFeatureNotSupportedException(
                                "ResultSet thực tế không đúng cấu hình yêu cầu");
                    }

                    // Chỉ gọi thao tác cuộn sau khi đã xác minh type.
                    if (rs.first()) {
                        System.out.println("First: "
                                + rs.getString("sku"));
                    }

                    if (rs.last()) {
                        System.out.println("Last: "
                                + rs.getString("sku"));
                    }
                }
            }
        }
    }

    private static void printWarnings(
            String source, SQLWarning first) {

        for (SQLWarning warning = first;
             warning != null;
             warning = warning.getNextWarning()) {

            System.out.println(source + ": "
                    + warning.getSQLState() + " - "
                    + warning.getMessage());
        }
    }
}
```

Đặt mã trong `VerifiedScrollableQuery.java`, cung cấp `DataSource` hợp lệ và gọi:

```java
VerifiedScrollableQuery.printFirstAndLast(dataSource);
```

Với ba hàng mẫu, nếu driver hỗ trợ đúng, kết quả dữ liệu là `First: A-100` và `Last: B-300`.

**Điểm cần nhớ trong ví dụ:**

1. `supportsResultSet...` chỉ là kiểm tra tổng quát, không phải bằng chứng cuối.
2. Truy vấn có `ORDER BY id` để khái niệm hàng đầu và cuối ổn định.
3. So sánh dùng hằng chuẩn JDBC, không dùng giá trị số viết cứng; các hằng là mã API, không phải mã thứ tự ưu tiên.
4. Cảnh báo được ghi lại cho chẩn đoán, nhưng quyết định hợp lệ dựa trên thuộc tính `ResultSet` **thật**.
5. Khi cấu hình không đủ, chương trình dừng trước khi gọi `first()` hoặc `last()` và `try-with-resources` đóng kết quả/statement/connection.
6. Không có `setAutoCommit(false)` vì ví dụ chỉ đọc kết quả trong cùng một phạm vi tài nguyên và **không thử giữ cursor qua commit**. Khi cần kiểm thử holdability tại runtime, phải tổ chức transaction phù hợp.

Một số driver không trả được `rs.getHoldability()` hoặc không hỗ trợ chính xác overload này; lúc đó việc ném `SQLFeatureNotSupportedException` hay `SQLException` là kết quả cần xử lý, không nên lặng lẽ bỏ bước xác minh nếu holdability là yêu cầu bắt buộc.

## 7. Nếu cấu hình được cấp khác cấu hình yêu cầu

Có ba chiến lược hợp lệ tùy nghiệp vụ:

### 7.1. Fail fast: tính năng bắt buộc

Nếu UI cần thao tác `previous()` hoặc chương trình cần cập nhật qua `ResultSet`, không thể giả vờ hoạt động khi driver chỉ cấp `TYPE_FORWARD_ONLY` hay `CONCUR_READ_ONLY`.

Mẫu kiểm tra:

```java
if (rs.getType() == ResultSet.TYPE_FORWARD_ONLY) {
    throw new SQLFeatureNotSupportedException(
            "ResultSet không hỗ trợ duyệt ngược");
}

if (rs.getConcurrency() != ResultSet.CONCUR_UPDATABLE) {
    throw new SQLFeatureNotSupportedException(
            "ResultSet không hỗ trợ cập nhật hàng");
}
```

Đây là các kiểm tra độc lập minh họa, không phải câu lệnh phải dùng đồng thời cho mọi query. Chỉ kiểm tra thuộc tính mà nghiệp vụ thật sự cần. Không nhất thiết đòi `TYPE_SCROLL_SENSITIVE` khi `TYPE_SCROLL_INSENSITIVE` đã đủ cho chức năng.

### 7.2. Fallback: dùng khả năng đơn giản hơn

Nếu ứng dụng chỉ cần đọc dữ liệu nhưng có thể tự lưu danh sách trong memory, hãy chuyển sang `TYPE_FORWARD_ONLY` và `CONCUR_READ_ONLY` khi scrollable không khả dụng:

```java
import java.util.ArrayList;
import java.util.List;

List<String> skus = new ArrayList<>();

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT sku FROM inventory_items ORDER BY id");
     ResultSet rs = ps.executeQuery()) {

    while (rs.next()) {
        skus.add(rs.getString("sku"));
    }
}

// Đã đóng ResultSet; giờ có thể truy cập phần tử theo index:
if (!skus.isEmpty()) {
    String lastSku = skus.get(skus.size() - 1);
    System.out.println(lastSku);
}
```

Đây là fallback phù hợp **khi tập dữ liệu nhỏ và việc materialize được phép**. Với hàng triệu bản ghi, không nên đưa tất cả vào `ArrayList` chỉ để giả lập `last()`; cân nhắc truy vấn sắp xếp/phân trang trên database.

Nếu tính năng yêu cầu cập nhật dữ liệu nhưng `ResultSet` chỉ đọc, fallback đáng tin cậy thường là `PreparedStatement` với `UPDATE ... WHERE ...`, kiểm tra số hàng bị ảnh hưởng và bảo vệ đồng thời bằng version/điều kiện nghiệp vụ khi cần.

### 7.3. Từ chối tính năng hoặc cấu hình môi trường khác

Nếu việc giữ cursor qua commit, scroll-sensitive hay cập nhật cursor là một phần **hợp đồng nghiệp vụ**, nên báo rõ driver/DBMS không hỗ trợ thay vì ngầm giảm chất lượng. Có thể chọn driver khác hoặc thay kiến trúc truy cập dữ liệu, nhưng phải kiểm chứng trên môi trường triển khai.

Không nên thay đổi ngầm isolation level, auto-commit hay các tùy chọn driver để “ép” hỗ trợ một tính năng nếu không hiểu tác động đến transaction đang hoạt động.

## 8. Ví dụ thứ hai: yêu cầu `CONCUR_UPDATABLE` nhưng query không phù hợp

Một `DatabaseMetaData` có thể trả `true` cho:

```java
boolean supported =
        meta.supportsResultSetConcurrency(
                ResultSet.TYPE_FORWARD_ONLY,
                ResultSet.CONCUR_UPDATABLE);
```

Tuy nhiên, thử truy vấn tổng hợp:

```sql
SELECT status, COUNT(*) AS item_count
FROM inventory_items
GROUP BY status
```

Tập kết quả này **không chỉ rõ mỗi hàng tương ứng một hàng đơn của bảng gốc**. Driver có thể không tạo được updatable result set cho query đó, dù có thể tạo cho câu `SELECT id, status FROM inventory_items`.

Tạo statement:

```java
try (Statement statement = connection.createStatement(
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_UPDATABLE);
     ResultSet rs = statement.executeQuery(
             "SELECT status, COUNT(*) AS item_count " +
             "FROM inventory_items GROUP BY status")) {

    int actualConcurrency = rs.getConcurrency();

    if (actualConcurrency != ResultSet.CONCUR_UPDATABLE) {
        System.out.println(
                "Query aggregate chỉ cung cấp ResultSet read-only");
    }
}
```

Với một số driver, ngay bước `executeQuery()` có thể ném `SQLException` thay vì trả result set đã downgrade. Hai hành vi cần được xử lý. Không dùng `rs.updateRow()` trên tập tổng hợp như thể đang sửa một hàng bảng nền.

Những dạng truy vấn thường hạn chế khả năng update qua cursor còn có `JOIN`, `DISTINCT`, `UNION`, `GROUP BY`, các hàm tổng hợp, một số view và truy vấn không có khóa định danh hàng cần sửa. **Danh sách chính xác phụ thuộc DBMS/driver**, không chỉ vào JDBC.

### Đường thay thế bằng `UPDATE` tham số hóa

```java
String sql = "UPDATE inventory_items " +
        "SET status = ? WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "READY");
    ps.setLong(2, 2L);

    int updated = ps.executeUpdate();
    if (updated != 1) {
        throw new SQLException(
                "Không cập nhật đúng một hàng inventory_items");
    }
}
```

Nếu thao tác thuộc transaction nhiều bước, sử dụng `Connection` chung với `setAutoCommit(false)`, `commit()` và `rollback()` rõ ràng. Khả năng cập nhật qua câu SQL tham số hóa **không phụ thuộc** việc result set có `CONCUR_UPDATABLE` hay không.

## 9. Các getter của Statement không thay cho getter của ResultSet

Đây là một nguồn lỗi tinh vi trong code:

```java
Statement statement = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_UPDATABLE);

int typeAtStatement = statement.getResultSetType();
int concurrencyAtStatement = statement.getResultSetConcurrency();
```

Nếu hai getter trả đúng điều yêu cầu, ta **vẫn chưa kiểm tra một `SELECT` cụ thể**. Chỉ sau khi gọi `executeQuery(sql)` mới có đối tượng `ResultSet` và getter tương ứng:

```java
try (ResultSet rs = statement.executeQuery(sql)) {
    int effectiveType = rs.getType();
    int effectiveConcurrency = rs.getConcurrency();

    System.out.println(effectiveType);
    System.out.println(effectiveConcurrency);
}
```

Hai đoạn là minh họa trong phạm vi `connection` và `sql` đã khai báo; cần đóng `statement` ở scope phù hợp. Một số driver ghi nhận downgrade ở statement, một số phản ánh rõ hơn ở result set cụ thể. **Không bỏ qua kết quả `rs.getConcurrency()` nếu chuẩn bị gọi `updateRow()`.**

Tương tự, `getHoldability()` trên `Connection` là giá trị mặc định và có thể khác `statement.getResultSetHoldability()` hoặc `rs.getHoldability()` khi chương trình dùng overload ba tham số.

## 10. Fetch size và fetch direction: giá trị đọc lại vẫn chỉ là gợi ý

Ngoài các thuộc tính type/concurrency/holdability, JDBC còn cho đặt **fetch hints**:

```java
try (Statement statement = connection.createStatement(
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    statement.setFetchDirection(ResultSet.FETCH_FORWARD);
    statement.setFetchSize(200);

    System.out.println("Statement fetch direction: "
            + statement.getFetchDirection());
    System.out.println("Statement fetch size: "
            + statement.getFetchSize());

    try (ResultSet rs = statement.executeQuery(
            "SELECT id, sku FROM inventory_items ORDER BY id")) {

        System.out.println("ResultSet fetch direction: "
                + rs.getFetchDirection());
        System.out.println("ResultSet fetch size: "
                + rs.getFetchSize());

        while (rs.next()) {
            // Duyệt dữ liệu tuần tự.
        }
    }
}
```

Điểm cần phân biệt:

- `setFetchSize(200)` là **gợi ý** cho driver về số hàng mong muốn mỗi đợt lấy dữ liệu; không phải yêu cầu kết quả chỉ có tối đa 200 hàng.
- `getFetchSize() == 200` chỉ cho biết giá trị gợi ý đang được báo lại; **không chứng minh driver phát đúng từng lệnh fetch 200 hàng**.
- `FETCH_FORWARD`, `FETCH_REVERSE` và `FETCH_UNKNOWN` là các gợi ý hướng lấy dữ liệu. Driver có thể từ chối hoặc bỏ qua một số hướng tùy kiểu result set.
- `Statement.setMaxRows(n)` là một điều khiển khác: nó giới hạn số hàng tối đa một `ResultSet` từ statement được phép chứa theo hợp đồng JDBC, không phải fetch size.
- Tốc độ và mức dùng memory có thể chịu ảnh hưởng của auto-commit, cursor server, phương thức fetch và các tùy chọn đặc thù driver. Phải đo trên môi trường thật.

Vì vậy cần tách **“getter trả đúng giá trị cấu hình”** khỏi **“hành vi performance đã được xác minh”**. Với yêu cầu streaming lượng dữ liệu lớn, không chỉ kiểm tra `getFetchSize()` rồi kết luận tối ưu; cần benchmark bộ nhớ, số round trip và tổng thời gian truy vấn.

## 11. Kiểm chứng holdability bằng transaction thật

Giả sử một tính năng muốn duyệt `ResultSet` **sau khi commit** một transaction trên cùng connection. Nếu chỉ gọi:

```java
int configured = rs.getHoldability();
```

và thấy `HOLD_CURSORS_OVER_COMMIT`, ứng dụng mới biết **thuộc tính được báo của result set**. Để chắc chắn cursor còn có thể hoạt động trong kịch bản sử dụng, cần thử nghiệm có commit thực tế.

Ý tưởng kiểm thử trong **môi trường test**:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (Statement statement = connection.createStatement(
                ResultSet.TYPE_SCROLL_INSENSITIVE,
                ResultSet.CONCUR_READ_ONLY,
                ResultSet.HOLD_CURSORS_OVER_COMMIT);
             ResultSet rs = statement.executeQuery(
                     "SELECT id FROM inventory_items ORDER BY id")) {

            if (rs.getHoldability()
                    != ResultSet.HOLD_CURSORS_OVER_COMMIT) {
                throw new SQLFeatureNotSupportedException(
                        "Driver không cấp holdability mong muốn");
            }

            rs.next();         // Đọc thử trước commit.
            connection.commit();

            // Kiểm tra sau commit; nếu driver đóng cursor,
            // next() có thể ném SQLException.
            System.out.println("Closed after commit: "
                    + rs.isClosed());
            if (!rs.isClosed()) {
                System.out.println("Has next: " + rs.next());
            }
        }
    } catch (SQLException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đoạn trên giả định đã import `java.sql.*` và có `DataSource dataSource`. Đây là **thử nghiệm hành vi**, không phải một mẫu nghiệp vụ nên duy trì cursor qua nhiều commit trong mọi hệ thống. Mỗi DBMS/driver có thể có quy tắc riêng về cursor, snapshot và transaction; hãy kiểm tra dữ liệu lớn, thời gian giữ cursor và rò rỉ tài nguyên.

**Không suy** rằng `TYPE_SCROLL_INSENSITIVE` hoặc `CONCUR_READ_ONLY` tự làm cursor sống qua commit. Holdability là thuộc tính riêng; thành công của overload tạo statement cũng không tự bảo đảm cursor mở sau commit.

## 12. Kiểm tra SQLWarning và SQLException khi bị hạ cấp

Nếu driver không thể cung cấp đúng type/concurrency, ứng dụng có thể gặp:

- `SQLFeatureNotSupportedException`, một nhánh của `SQLException`, khi driver không hỗ trợ tính năng được gọi.
- Một `SQLException` khác khi câu SQL hoặc cấu hình khiến kết quả không khả dụng.
- Một result set có tính năng hạn chế hơn và, tùy driver, **`SQLWarning`** giải thích sự hạ cấp.

Có thể ghi chẩn đoán:

```java
import java.sql.SQLException;
import java.sql.SQLWarning;

public static void logWarnings(
        String where, SQLWarning first) {

    for (SQLWarning warning = first;
         warning != null;
         warning = warning.getNextWarning()) {

        System.err.println(where
                + " SQLState=" + warning.getSQLState()
                + ", vendorCode=" + warning.getErrorCode()
                + ", message=" + warning.getMessage());
    }
}

public static void logSqlFailure(SQLException error) {
    for (SQLException current = error;
         current != null;
         current = current.getNextException()) {

        System.err.println("SQLState=" + current.getSQLState()
                + ", vendorCode=" + current.getErrorCode()
                + ", message=" + current.getMessage());
    }
}
```

Những hàm tiện ích này không thay thế xử lý transaction. Với một truy vấn có cập nhật, khi `SQLException` xảy ra và ứng dụng đang dùng `autoCommit=false`, phải kết thúc transaction an toàn qua `rollback()` (nếu cần) trước khi bỏ connection.

**Một cảnh báo rỗng không chứng minh tính năng được cấp đầy đủ**. Phải đọc thuộc tính thực tế và thực nghiệm hành vi đúng nhu cầu. Ngược lại, khi driver trả exception, không được giả định driver đã tự cung cấp phương án thay thế; cần bắt lỗi và chọn đường xử lý khác rõ ràng.

## 13. Vì sao kết quả khác nhau giữa những môi trường?

Nhiều lý do có thể khiến code cùng yêu cầu nhưng thuộc tính thực tế khác nhau:

| Nguyên nhân | Biểu hiện | Cách kiểm tra |
|---|---|---|
| Phiên bản JDBC driver khác | Chỗ hỗ trợ scroll ở môi trường này nhưng không ở môi trường kia | Ghi `DatabaseMetaData.getDriverName()` và `getDriverVersion()` |
| DBMS/phiên bản server khác | Holdability hoặc updatable cursor có giới hạn riêng | `getDatabaseProductName()` và `getDatabaseProductVersion()` |
| SQL khác cấu trúc | Query đơn bảng updatable, query tổng hợp chỉ đọc | Ghi dạng SQL (tránh log dữ liệu nhạy cảm), kiểm tra `rs.getConcurrency()` |
| Connection pool thay đổi trạng thái | Auto-commit, isolation hoặc holdability khác mặc định | `connection.getAutoCommit()`, `getTransactionIsolation()`, `getHoldability()` |
| Mức cô lập khác | Scroll-sensitive quan sát khác khi connection khác commit | Kiểm thử hai transaction, ghi isolation |
| Driver dùng buffer hoặc cursor server | Fetch size gợi ý không tạo hành vi stream như mong đợi | Theo dõi memory, round trip, query timing |
| Thiếu quyền cập nhật | Được đọc dữ liệu nhưng `updateRow()` thất bại | Kiểm tra quyền database và `SQLException` |
| Câu SQL không đủ thông tin khóa | Driver không thể ánh xạ hàng để cập nhật | Dùng SELECT đơn bảng có khóa hoặc SQL UPDATE tường minh |

Đo môi trường bằng JDBC:

```java
DatabaseMetaData meta = connection.getMetaData();

System.out.println("DB: "
        + meta.getDatabaseProductName()
        + " " + meta.getDatabaseProductVersion());

System.out.println("Driver: "
        + meta.getDriverName()
        + " " + meta.getDriverVersion());

System.out.println("autoCommit: "
        + connection.getAutoCommit());

System.out.println("isolation: "
        + connection.getTransactionIsolation());

System.out.println("holdability default: "
        + connection.getHoldability());
```

Những câu lệnh in ra stdout này chỉ phù hợp cho ví dụ. Trong production, dùng hệ thống log có giới hạn mức độ, tránh ghi chuỗi chứa thông tin xác thực hoặc giá trị cá nhân.

## 14. Những ngộ nhận cần tránh

| Ngộ nhận | Thực tế |
|---|---|
| Truyền tham số `TYPE_SCROLL_INSENSITIVE` đồng nghĩa chắc chắn `previous()` hoạt động | Phải kiểm tra `rs.getType()` và driver có hỗ trợ thao tác |
| `supportsResultSetConcurrency(...)` trả `true` nghĩa là mọi truy vấn đều updatable | Nó chỉ mô tả khả năng chung; query có `JOIN`/`GROUP BY` có thể read-only |
| Getter của `Statement` đã đủ xác minh | Đối tượng `ResultSet` được tạo mới là nơi cần kiểm tra cuối cùng |
| `Connection.getHoldability()` luôn bằng `ResultSet.getHoldability()` | Connection có giá trị mặc định; statement/result set có thể được yêu cầu khác |
| `getFetchSize() == 200` chứng minh driver fetch từng 200 hàng | Đó là giá trị gợi ý; phải đo hành vi thực tế |
| `CONCUR_UPDATABLE` bảo vệ transaction khỏi lost update | Vẫn cần locking/isolation/version check phù hợp |
| `TYPE_SCROLL_SENSITIVE` bảo đảm dữ liệu realtime | Snapshot, driver và transaction có thể giới hạn thay đổi nhìn thấy |
| `SQLWarning` trống nghĩa là không có downgrade | Driver không bắt buộc phát cảnh báo dễ hiểu cho mọi trường hợp |
| Tắt auto-commit là đủ để giữ result set sau commit | Khả năng giữ cursor là holdability cùng đặc tính driver |
| Có thể dùng result set sau khi đóng statement/connection | Tài nguyên phụ thuộc scope của JDBC; phải kiểm soát vòng đời |
| Có thể biến một `ResultSet` đang mở thành scrollable bằng thay setter | Type/concurrency được xác định khi tạo; tạo statement và result set mới nếu cần |
| “Concurrency” là dùng result set đa luồng | Nó biểu thị khả năng cập nhật qua ResultSet, không phải thread safety |

## 15. Bài thực hành tích hợp

Dùng bảng `inventory_items` ở phần 6, kết nối bằng cùng `DataSource` mà ứng dụng sẽ sử dụng trên môi trường thực tế.

### Bài 1: Lập bảng khả năng

In kết quả của `supportsResultSetType(...)` cho cả ba type và `supportsResultSetConcurrency(type, concurrency)` cho cả hai concurrency. Đừng tự suy ra `TYPE_SCROLL_SENSITIVE` được hỗ trợ chỉ vì `TYPE_SCROLL_INSENSITIVE` được hỗ trợ.

### Bài 2: So sánh thông số được yêu cầu và thực tế

Tạo statement với `TYPE_SCROLL_INSENSITIVE`, `CONCUR_READ_ONLY`, `CLOSE_CURSORS_AT_COMMIT`. Ghi:

- Các hằng đã truyền.
- Giá trị ba getter trên `Statement`.
- Giá trị ba getter trên `ResultSet` sau khi execute.
- `SQLWarning`, nếu có.

Kiểm tra chương trình phản ứng đúng khi driver không đáp ứng.

### Bài 3: Truy vấn không thể cập nhật

Dùng `SELECT status, COUNT(*) ... GROUP BY status` và yêu cầu `CONCUR_UPDATABLE`. Quan sát driver trả exception hay result set read-only; không gọi `updateRow()` trên truy vấn tổng hợp.

### Bài 4: Fallback truy vấn

Nếu không có scrollable result set, chuyển sang `PreparedStatement` mặc định, đọc tuần tự rồi lưu danh sách nhỏ. Với bảng lớn, thay bằng truy vấn phân trang hoặc truy vấn chỉ lấy bản ghi cần thiết.

### Bài 5: Holdability qua commit

Trong môi trường test, yêu cầu `HOLD_CURSORS_OVER_COMMIT`, dùng `autoCommit=false`, đọc một hàng, commit, sau đó kiểm tra `rs.isClosed()` và thử duyệt tiếp nếu còn mở. Không suy từ getter rằng mọi truy vấn/driver đều thực hiện giống nhau.

### Bài 6: Fetch-size hint

Đặt `setFetchSize(50)`, đọc lại `Statement.getFetchSize()` và `ResultSet.getFetchSize()`. Tăng lên `200` và benchmark với 50.000 hàng. Kết quả cần đo memory và thời gian, không chỉ so sánh hai getter.

### Bài 7: Kiểm tra tài nguyên

Tạo nhiều statement/result set trong vòng lặp, cố tình gây `SQLException` ở một lượt, xác nhận `try-with-resources` đóng result set/statement/connection. Kiểm tra pool không bị cạn connection sau các lỗi.

## 16. Checklist sử dụng trong dự án

Trước khi đưa một result set nâng cao vào ứng dụng:

1. Đã phân biệt chính xác **cấu hình được yêu cầu** và **khả năng driver công bố** chưa?
2. Có kiểm tra `supportsResultSetType`, `supportsResultSetConcurrency`, `supportsResultSetHoldability` trên connection thực tế không?
3. Sau khi thực thi query, có đọc `rs.getType()`, `rs.getConcurrency()` và `rs.getHoldability()` trước khi dùng tính năng nâng cao không?
4. Có thiết kế cách xử lý rõ ràng khi driver ném lỗi, downgrade, hoặc không cung cấp hành vi cần thiết không?
5. Có phân biệt fetch hint với kết quả fetch thực tế, type/concurrency với isolation và holdability với vòng đời transaction không?
6. Với kết quả có thể cập nhật, SQL có đáp ứng điều kiện của driver và có chiến lược chống xung đột dữ liệu không?
7. Có giữ `ResultSet`, `Statement`, `Connection` trong scope phù hợp và đóng bằng `try-with-resources` không?
8. Đã kiểm thử trên **DBMS, JDBC driver, connection pool và câu SQL cụ thể** của hệ thống chưa?

## Ghi nhớ

- **Ứng dụng yêu cầu qua tham số**, **driver công bố hỗ trợ qua `DatabaseMetaData`**, còn **`ResultSet` thực tế phải được kiểm tra bằng các getter của chính nó**.
- `TYPE_SCROLL_INSENSITIVE`, `TYPE_SCROLL_SENSITIVE` và `CONCUR_UPDATABLE` **không được bảo đảm** cho mọi truy vấn hoặc mọi driver.
- `Connection.getHoldability()` là mặc định; `rs.getHoldability()` thể hiện thuộc tính của cursor cụ thể. Nếu cần cursor tồn tại sau commit, hãy kiểm thử hành vi sau commit.
- Giá trị trả bởi `getFetchSize()` là **gợi ý**, không chứng minh driver fetch theo đúng số hàng đó.
- Khi cấu hình thực tế không đáp ứng, **fail fast hoặc fallback minh bạch**; đừng tiếp tục gọi `previous()`, `absolute()` hoặc `updateRow()` trên result set không đủ khả năng.
- Với JDBC trong production, **tính đúng đắn, tính nhất quán và việc đóng tài nguyên** quan trọng hơn việc cố khai thác một tính năng cursor không chắc chắn.

Xác minh cấu hình được cấp là bước nối giữa API JDBC trên giấy và hành vi thật của driver/DBMS. Khi chủ động đối chiếu **requested → supported → actual → observed**, ứng dụng có thể lựa chọn con trỏ phù hợp, phát hiện hạ cấp sớm và tránh lỗi chỉ xuất hiện khi dữ liệu hoặc môi trường triển khai thay đổi.
