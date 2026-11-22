# Hiểu vai trò của Ref và RowId khi hệ quản trị hỗ trợ

JDBC cung cấp hai kiểu ít gặp hơn `INTEGER`, `VARCHAR` hay `TIMESTAMP`: `java.sql.Ref` và `java.sql.RowId`. Chúng đều có thể trông giống như một “định danh để tìm lại dữ liệu”, nhưng biểu diễn **hai khái niệm khác nhau**. `Ref` là tham chiếu SQL tới **đối tượng có kiểu cấu trúc** trong mô hình đối tượng–quan hệ; `RowId` là **định danh/định vị hàng do hệ quản trị cấp**. Cả hai đều chỉ hữu ích khi cơ sở dữ liệu và JDBC driver thực sự hỗ trợ.

Trong chương **Kiểu SQL nâng cao** của module **JDBC**, mục tiêu là nhận biết khi nào dùng `ResultSet.getRef()`, `PreparedStatement.setRef()`, `ResultSet.getRowId()` và `PreparedStatement.setRowId()`; cách kiểm tra `DatabaseMetaData.getRowIdLifetime()`; giới hạn về transaction, vòng đời, bảo mật và khả năng di chuyển giữa các DB; cũng như lý do **khóa chính và khóa ngoại thông thường vẫn là lựa chọn mặc định** cho phần lớn CRUD.

Bài học sử dụng các API chuẩn của JDBC, `DataSource`, `PreparedStatement` và `ResultSet`. Các ví dụ SQL dựa trên cú pháp kiểu Oracle khi cần minh họa `REF`/`ROWID`, bởi nhiều hệ quản trị như PostgreSQL, MySQL và SQLite không có mô hình tương ứng trong JDBC theo cùng cách. **Cú pháp hoặc tính năng của DB cụ thể phải được xác nhận trên driver và phiên bản đang dùng**, không suy ra khả năng chỉ từ việc Java có interface tương ứng.

## 1. Phân biệt nhanh SQL REF và ROWID

| Tiêu chí | SQL `REF` / `java.sql.Ref` | SQL `ROWID` / `java.sql.RowId` |
| --- | --- | --- |
| Trỏ tới | Giá trị **đối tượng SQL có kiểu cấu trúc** trong hệ đối tượng–quan hệ | Một hàng theo cơ chế định vị/nhận diện của DB |
| Mục đích | Giữ và truy xuất tham chiếu tới đối tượng SQL đã được định kiểu | Tìm lại một hàng theo định danh nội bộ khi DB cho phép |
| Thông tin Java | `Ref.getBaseTypeName()`, `getObject()`, `setObject()` | `RowId.getBytes()`, giá trị opaque do driver biểu diễn |
| Đọc từ JDBC | `ResultSet.getRef(...)` | `ResultSet.getRowId(...)` |
| Bind tham số | `PreparedStatement.setRef(...)` | `PreparedStatement.setRowId(...)` |
| Kiểu JDBC | `Types.REF` | `Types.ROWID` |
| Vòng đời | Phụ thuộc cấu trúc đối tượng và quy tắc DB | `DatabaseMetaData.getRowIdLifetime()` cung cấp thông tin thời hạn |
| Thay thế được khóa ngoại/khóa chính? | Không phải sự thay thế có thể di chuyển cho foreign key | Không nên coi là primary key nghiệp vụ lâu dài |
| Mức phổ biến | Chủ yếu ở một số hệ DB đối tượng–quan hệ | Đặc thù từng DB; cách tạo và độ ổn định không đồng nhất |

Tên gọi dễ gây nhầm:

- `java.sql.Ref` **không phải** `java.lang.ref.Reference`, `WeakReference`, Java reference của một object trong JVM hoặc một biến chứa địa chỉ bộ nhớ.
- `java.sql.Ref` **không phải** `REF_CURSOR` dùng để trả cursor/result set từ stored procedure. `DatabaseMetaData.supportsRefCursors()` nói về **ref cursor**, không chứng minh DB hỗ trợ cột SQL `REF`.
- `RowId` **không phải** `ResultSet.getRow()`. `getRow()` trả số thứ tự của hàng *trong cursor hiện tại*, còn `getRowId()` trả một giá trị do DB/driver cung cấp.
- Chuỗi khóa chính như `customer_id = 42` là **định danh dữ liệu trong schema**; nó khác với RowId nội bộ của hệ quản trị.

## 2. Ref: một tham chiếu SQL có kiểu tới structured object

Trong SQL đối tượng–quan hệ, cơ sở dữ liệu có thể cho phép định nghĩa một kiểu cấu trúc, tạo những đối tượng thuộc kiểu đó, rồi lưu **tham chiếu được định kiểu** tới các đối tượng. Điều này khác việc lưu `customer_id BIGINT` để tham chiếu bảng `customers` thông thường.

Hình dung hai cách mô hình hóa:

```text
Mô hình quan hệ phổ thông:
orders.customer_id -> customers.id         (FOREIGN KEY)

Mô hình đối tượng–quan hệ khi DB hỗ trợ:
order_links.customer_ref -> SQL object thuộc kiểu CUSTOMER_OBJECT (REF)
```

Ví dụ cú pháp *minh họa cho Oracle*, không phải SQL chuẩn chạy nguyên vẹn trên mọi DB:

```sql
CREATE TYPE customer_object AS OBJECT (
    customer_id NUMBER,
    full_name   VARCHAR2(120)
);
/

CREATE TABLE customer_objects OF customer_object (
    PRIMARY KEY (customer_id)
);

CREATE TABLE customer_links (
    link_id      NUMBER PRIMARY KEY,
    customer_ref REF customer_object SCOPE IS customer_objects
);
```

`customer_ref` ở đây mang ngữ nghĩa SQL `REF`, có kiểu đối tượng đích. Phép dereference (ví dụ cú pháp `DEREF(...)` ở DB hỗ trợ) có thể truy cập giá trị đối tượng được tham chiếu. SQL ở trên phụ thuộc đặc tính object table của Oracle, quyền tạo kiểu/đối tượng, và công cụ chạy SQL có xử lý dấu `/`; khi dùng công cụ khác hoặc DB khác cần điều chỉnh DDL.

Trong khi đó, schema quan hệ thông thường thường biểu diễn cùng yêu cầu đơn giản hơn:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE order_links (
    link_id BIGINT PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(id)
);
```

Khóa ngoại này có khả năng hỗ trợ rộng hơn, dễ quản lý constraint, backup, migration, schema change và tích hợp giữa các dịch vụ. **Đừng tạo SQL REF chỉ vì Java có `Ref`**; cần một yêu cầu cụ thể về mô hình đối tượng–quan hệ và một DB/driver đã được kiểm chứng.

## 3. Những phương thức quan trọng của `java.sql.Ref`

`Ref` là một interface trong package `java.sql`. Các phương thức chính:

| Phương thức | Vai trò | Lưu ý |
| --- | --- | --- |
| `getBaseTypeName()` | Trả tên kiểu SQL có cấu trúc được tham chiếu | Có thể gồm tên schema theo quy ước DB/driver |
| `getObject()` | Lấy biểu diễn Java của đối tượng SQL mà `Ref` trỏ tới | Kết quả thường là `Struct` hoặc kiểu Java đã được ánh xạ; phụ thuộc driver và type map |
| `getObject(Map<String, Class<?>> map)` | Lấy đối tượng với ánh xạ kiểu SQL → kiểu Java được cung cấp | Chỉ hữu ích khi driver hỗ trợ ánh xạ kiểu tùy chỉnh |
| `setObject(Object value)` | Yêu cầu đặt giá trị structured object được tham chiếu | Có tác động phụ thuộc DB; **không** nên mặc định gọi như setter Java thông thường |

Các API liên quan:

- `ResultSet.getRef(int columnIndex)` và `getRef(String columnLabel)` đọc giá trị `REF` từ kết quả.
- `CallableStatement.getRef(...)` có thể dùng với tham số tương ứng của stored procedure khi driver hỗ trợ.
- `PreparedStatement.setRef(int parameterIndex, Ref value)` bind một tham chiếu vào tham số SQL.
- `ResultSet.getObject(...)` có thể được driver dùng để cung cấp đối tượng khác; nếu muốn ngữ nghĩa `Ref` rõ ràng, dùng `getRef(...)` trên cột thực sự là SQL `REF`.
- `PreparedStatement.setNull(index, Types.REF)` biểu thị SQL `NULL` cho tham số kiểu `REF`, với điều kiện DB/driver hỗ trợ loại cột và binding đó.

`Ref.getObject()` có thể yêu cầu một lần truy cập DB để lấy đối tượng đích; nó có thể ném `SQLException` do quyền, đối tượng đích đã thay đổi, kết nối lỗi hoặc thao tác không được hỗ trợ. Vì vậy, **đọc một Ref không đồng nghĩa đã tải toàn bộ dữ liệu đối tượng**. Không duyệt một nghìn tham chiếu rồi tự gọi `getObject()` cho từng phần tử mà không đo số lượt truy cập thực tế.

Nếu cần chuyển giá trị Java thành SQL structured object, JDBC còn có `java.sql.Struct` và `Connection.createStruct(typeName, attributes)` ở driver hỗ trợ. **Struct và Ref không giống nhau**: `Struct` biểu diễn giá trị có cấu trúc, còn `Ref` biểu diễn tham chiếu đến giá trị có cấu trúc. Tạo `Struct` không tự tạo ra một `Ref` hợp lệ tới một đối tượng trong DB.

## 4. Đọc một REF qua DataSource, PreparedStatement và ResultSet

Giả sử DB đã cung cấp bảng `customer_links(link_id, customer_ref)` như phần trước. Ví dụ dưới đây trả kết quả phân biệt **không tìm thấy hàng**, **tìm thấy hàng nhưng cột REF là NULL**, và **REF có giá trị**.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Ref;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerRefReader {
    private CustomerRefReader() {}

    public record RefSummary(
            boolean sqlNull, String referencedSqlType, String javaObjectType) {}

    public static Optional<RefSummary> inspect(
            DataSource source, long linkId) throws SQLException {
        String sql = """
                SELECT customer_ref
                FROM customer_links
                WHERE link_id = ?
                """;

        try (Connection con = source.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setLong(1, linkId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty(); // Không có hàng.
                }

                Ref ref = rs.getRef("customer_ref");
                if (ref == null) {
                    return Optional.of(new RefSummary(true, null, null));
                }

                String sqlTypeName = ref.getBaseTypeName();
                Object referencedObject = ref.getObject();
                String javaTypeName = referencedObject == null
                        ? null : referencedObject.getClass().getName();

                return Optional.of(new RefSummary(
                        false, sqlTypeName, javaTypeName));
            }
        }
    }
}
```

Phương thức sử dụng Java 17+ và kiểu `Optional<RefSummary>` để **không trộn** trạng thái thiếu hàng với cột SQL `NULL`. Khi Ref có giá trị nhưng `getObject()` không trả đối tượng đích (hoặc ném `SQLException`), mã không tự suy luận đã tìm thấy đối tượng hợp lệ. Phải xác định quy tắc tồn tại/tham chiếu đích theo DB và nghiệp vụ.

**Những tiền điều kiện của ví dụ:**

- SQL `REF` và câu `SELECT` chỉ chạy trên DB có hỗ trợ mô hình đó; nhiều driver trả `SQLFeatureNotSupportedException` hoặc `SQLException`.
- `getRef()` và `getObject()` được thực thi khi connection còn mở; không giữ `Ref` cho một request sau rồi mặc định có thể truy vấn ở connection hoặc transaction khác.
- Nếu ứng dụng chỉ cần `customer_id` và `full_name`, một `SELECT JOIN` dựa trên khóa ngoại thường dễ di chuyển và dự đoán chi phí hơn.
- Không ghi nội dung đối tượng đích vào log tùy tiện vì có thể chứa dữ liệu nhạy cảm; ví dụ chỉ ghi tên lớp Java phục vụ quan sát kỹ thuật.

### Khi `getObject()` trả về `Struct`

Trên một số driver, giá trị trả về có thể là `java.sql.Struct`:

```java
Object value = ref.getObject();
if (value instanceof java.sql.Struct struct) {
    String sqlType = struct.getSQLTypeName();
    Object[] attributes = struct.getAttributes();
    // Thứ tự và kiểu attributes tương ứng định nghĩa structured SQL type.
}
```

Để lấy thuộc tính có cấu trúc theo kiểu nghiệp vụ, nên có mapper riêng theo tên kiểu và thứ tự thuộc tính, kiểm soát `NULL` và kiểm tra driver/type map. Không ép trực tiếp mọi `Ref.getObject()` thành `Struct`: ánh xạ tùy chỉnh có thể trả một đối tượng Java khác; hỗ trợ giữa các driver không đồng nhất.

## 5. Bind và cập nhật REF: kết nối và tham chiếu phải tương thích

Khi ứng dụng đã nhận được một `Ref` hợp lệ, có thể dùng `PreparedStatement.setRef(...)` để ghi tham chiếu đó vào **một cột REF tương thích**, chẳng hạn thay người được liên kết trong bảng object-relational:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Ref;
import java.sql.SQLException;
import java.sql.Types;

public static int updateCustomerRef(
        Connection con, long linkId, Ref newRef) throws SQLException {

    String sql = "UPDATE customer_links "
               + "SET customer_ref = ? WHERE link_id = ?";

    try (PreparedStatement ps = con.prepareStatement(sql)) {
        if (newRef == null) {
            ps.setNull(1, Types.REF);
        } else {
            ps.setRef(1, newRef);
        }
        ps.setLong(2, linkId);
        return ps.executeUpdate();
    }
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp Java; caller chịu trách nhiệm đóng `Connection` và quyết định `commit()/rollback()`. Không áp dụng `setRef` cho cột khóa ngoại `BIGINT`, vì SQL `REF` và khóa ngoại số là hai loại khác nhau.

Đừng giả định `Ref` lấy từ **connection A** có thể được bind trên **connection B** hoặc chuyển sang một DB khác. Tính tương thích phụ thuộc driver, cùng loại SQL object và vòng đời tham chiếu. Giải pháp an toàn là thao tác trên cùng connection/transaction khi có thể, kiểm thử thực tế, hoặc dùng khóa nghiệp vụ để truy vấn lại thay vì lưu đối tượng `Ref` dài hạn.

`Ref.setObject(...)` khác với `PreparedStatement.setRef(...)`: một bên yêu cầu thay giá trị structured object được tham chiếu; bên còn lại bind **giá trị tham chiếu** làm tham số của câu SQL. Không dùng `setObject` để âm thầm sửa dữ liệu đích khi chỉ cần đổi quan hệ; hãy dùng câu lệnh SQL/transaction có semantics rõ ràng.

## 6. RowId: định danh hàng do cơ sở dữ liệu cung cấp

`java.sql.RowId` đại diện cho SQL `ROWID`, một giá trị **opaque** được tạo và diễn giải theo cơ chế của DB/driver. Nó có thể được triển khai dựa trên vị trí vật lý, cấu trúc lưu trữ hoặc định danh nội bộ khác; ứng dụng không được tự suy luận cấu trúc từ tên `ROWID`.

Trong một số DB, RowId giúp tìm lại nhanh một hàng đã biết mà không phải thiết kế lại phép tìm kiếm, nhưng đây là khả năng phụ thuộc sản phẩm. Nó khác với:

- **Khóa chính:** có ý nghĩa ổn định do schema/ứng dụng xác định và thường dùng cho quan hệ, REST API, event và báo cáo.
- **Offset hoặc số thứ tự hàng:** thứ tự trong `ResultSet` có thể đổi nếu tập dữ liệu thay đổi hoặc `ORDER BY` khác.
- **Mã ID bên ngoài:** RowId không nên mặc định được xuất ra JSON, đưa vào URL, cache dài hạn hay message gửi giữa các dịch vụ.

API tiêu biểu:

```java
RowId rowId = rs.getRowId("rid");         // Lấy giá trị từ cột ROWID phù hợp.
byte[] opaqueBytes = rowId.getBytes();   // Dữ liệu nhị phân do driver xác định.
ps.setRowId(1, rowId);                   // Bind vào tham số kiểu ROWID phù hợp.
```

`getBytes()` **không tạo ra định dạng trao đổi chung giữa các DB**. Đừng chuyển byte array sang chuỗi một cách tùy ý, tự sửa các byte rồi kỳ vọng có một RowId hợp lệ, hoặc coi kết quả `toString()` là định dạng bền vững. Với một RowId `NULL`, `getRowId()` có thể trả `null`; phải kiểm tra trước khi gọi `getBytes()`.

## 7. Kiểm tra vòng đời bằng `DatabaseMetaData.getRowIdLifetime()`

JDBC cung cấp một chỉ báo quan trọng: `Connection.getMetaData().getRowIdLifetime()`, trả về enum `java.sql.RowIdLifetime`.

| Giá trị | Ý nghĩa ở mức giao diện JDBC | Hệ quả thiết kế |
| --- | --- | --- |
| `ROWID_UNSUPPORTED` | DB/driver không hỗ trợ RowId | Không gọi `getRowId()/setRowId()` như một tính năng bắt buộc |
| `ROWID_VALID_TRANSACTION` | RowId có hiệu lực trong transaction | Không mặc định dùng lại sau `commit()` hoặc `rollback()` |
| `ROWID_VALID_SESSION` | RowId có hiệu lực trong session | Không mang RowId sang connection/session khác |
| `ROWID_VALID_FOREVER` | RowId được báo có thời hạn ổn định dài lâu | Vẫn cần xét row bị xóa, di chuyển, tái tổ chức, chính sách DB; không biến nó thành ID nghiệp vụ |
| `ROWID_VALID_OTHER` | DB có quy tắc thời hạn riêng | Đọc tài liệu nhà cung cấp và kiểm thử trước khi lưu/dùng lại |

Ví dụ đọc khả năng:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.RowIdLifetime;
import java.sql.SQLException;
import javax.sql.DataSource;

public static RowIdLifetime inspectRowIdLifetime(
        DataSource source) throws SQLException {
    try (Connection con = source.getConnection()) {
        DatabaseMetaData meta = con.getMetaData();
        return meta.getRowIdLifetime();
    }
}
```

`ROWID_VALID_FOREVER` là một thông tin hỗ trợ do driver báo, **không phải lời hứa RowId là khóa chính bất biến cho mọi nghiệp vụ**. Hàng đã xóa hoặc được tái cấu trúc có thể có những quy tắc riêng, và giữa hai DB khác nhau không có bảo đảm RowId của DB A tương thích với DB B.

Đặc biệt trong hệ thống có connection pool, nhiều lần gọi `dataSource.getConnection()` có thể trả **những session vật lý khác nhau**. Nếu metadata báo `ROWID_VALID_SESSION`, không được lưu RowId để dùng tùy tiện trong request sau trên một logical connection mới. Nếu báo `ROWID_VALID_TRANSACTION` thì càng phải giới hạn trong transaction hiện tại.

## 8. Ví dụ RowId với cú pháp ROWID của Oracle

Các cơ sở dữ liệu khác nhau về cách truy vấn RowId. Đoạn SQL sau là **ví dụ theo cú pháp Oracle** (pseudo-column `ROWID`):

```sql
SELECT ROWID AS rid, id, full_name
FROM customers
WHERE id = ?;

SELECT full_name
FROM customers
WHERE ROWID = ?;
```

Ví dụ Java dưới đây cố tình **nhận connection đang ở transaction do caller quản lý**; nó đọc RowId rồi dùng chính RowId đó trên **cùng connection**. Việc này tránh hiểu nhầm rằng RowId đọc từ một transaction có thể được sử dụng vô hạn:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.RowId;
import java.sql.RowIdLifetime;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Optional;

public final class CustomerRowIdReader {
    private CustomerRowIdReader() {}

    public static Optional<String> findNameInCurrentTransaction(
            Connection con, long customerId) throws SQLException {

        if (con.getAutoCommit()) {
            throw new IllegalStateException(
                    "Caller phải quản lý một transaction trên connection này");
        }
        RowIdLifetime lifetime = con.getMetaData().getRowIdLifetime();
        if (lifetime == RowIdLifetime.ROWID_UNSUPPORTED) {
            throw new SQLFeatureNotSupportedException(
                    "Driver không hỗ trợ SQL ROWID");
        }

        RowId rid;
        String findRowId = "SELECT ROWID AS rid FROM customers WHERE id = ?";
        try (PreparedStatement ps = con.prepareStatement(findRowId)) {
            ps.setLong(1, customerId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                rid = rs.getRowId("rid");
                if (rid == null) {
                    throw new SQLException("ROWID không được NULL với hàng này");
                }
            }
        }

        String findByRowId = "SELECT full_name FROM customers WHERE ROWID = ?";
        try (PreparedStatement ps = con.prepareStatement(findByRowId)) {
            ps.setRowId(1, rid);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    // RowId không còn định vị được hàng theo hợp đồng DB.
                    return Optional.empty();
                }
                return Optional.ofNullable(rs.getString("full_name"));
            }
        }
    }
}
```

**Điều kiện chạy ví dụ:** DB có pseudo-column `ROWID` và driver hỗ trợ `getRowId()/setRowId()` trên biểu thức/cột đó. `DatabaseMetaData.getRowIdLifetime()` chỉ là **tín hiệu ban đầu**; nhiều tổ hợp vendor/phiên bản vẫn có giới hạn cụ thể khi bind RowId hoặc dùng SQL dạng này. Caller phải mở transaction (ví dụ `setAutoCommit(false)`), quản lý `commit/rollback`, khôi phục state và đóng connection. Vì hàm chỉ đọc, nếu mục đích duy nhất là lấy `full_name` theo `customerId`, cách đơn giản nhất vẫn là **một câu `SELECT full_name WHERE id = ?`**.

Không dùng `Optional.empty()` của một hàm trả về RowId như bằng chứng chắc chắn bản ghi đã bị xóa nếu metadata hoặc driver cho phép RowId hết hạn. Khi cần nhận biết sự khác nhau giữa “hàng không tồn tại” và “RowId không còn hợp lệ”, hãy trả một kiểu kết quả nghiệp vụ có trạng thái rõ ràng và truy vấn lại bằng khóa chính để xác minh.

## 9. Khi nào RowId có ích, và vì sao thường không dùng làm khóa nghiệp vụ?

Một số ứng dụng có thể dùng RowId trong phạm vi **ngắn hạn, cùng DB, cùng session/transaction** khi driver hỗ trợ và một hàng đã được xác định:

- Tìm lại một hàng qua locator do DB cung cấp trong một quy trình nội bộ có kiểm chứng.
- Tối ưu một đường truy cập đặc thù theo khuyến nghị của nhà cung cấp DB, **sau khi đo hiệu năng** so với truy vấn theo chỉ mục khóa chính.
- Thao tác với tính năng DB mà RowId là một phần của giao thức SQL hoặc công cụ quản trị được cung cấp.

Nhưng RowId không phù hợp làm:

- Mã đơn hàng/khách hàng trả về từ REST API.
- Khóa ngoài của bảng nghiệp vụ theo mô hình quan hệ thông dụng.
- Khóa dùng để trao đổi giữa hai cơ sở dữ liệu khác nhau.
- Khóa cache dài hạn hay event ID bền vững nếu chưa có bảo đảm vendor rõ ràng.
- Chứng cứ phân quyền: người có RowId vẫn phải vượt qua kiểm soát truy cập và ràng buộc tenant.

Ví dụ nguy hiểm:

```java
// Không nên đưa opaque RowId ra API như một ID nghiệp vụ:
String publicCustomerId = rowId.toString();
```

Ngay cả khi RowId có chuỗi đọc được trên DB A, chuyển sang DB B, di chuyển dữ liệu hoặc nâng cấp driver có thể thay đổi cách biểu diễn. RowId còn không tự mang thông tin quyền sở hữu hay phiên bản bản ghi.

## 10. Phương án thông dụng: khóa chính và cập nhật có điều kiện

Nếu bài toán cần “cập nhật đúng hàng đã đọc”, phương án có khả năng di chuyển cao là **khóa chính** kết hợp kiểm soát phiên bản nếu có cạnh tranh ghi.

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    display_name VARCHAR(120),
    version BIGINT NOT NULL DEFAULT 0
);
```

Ví dụ optimistic locking qua SQL tham số hóa:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class CustomerUpdater {
    private CustomerUpdater() {}

    public static boolean renameIfUnchanged(
            DataSource source,
            long customerId,
            long expectedVersion,
            String displayName) throws SQLException {

        String sql = """
                UPDATE customers
                SET display_name = ?, version = version + 1
                WHERE id = ? AND version = ?
                """;

        try (Connection con = source.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setString(1, displayName);
            ps.setLong(2, customerId);
            ps.setLong(3, expectedVersion);
            return ps.executeUpdate() == 1;
        }
    }
}
```

`false` có nghĩa lệnh cập nhật không tác động đúng một hàng: có thể vì bản ghi không tồn tại hoặc version đã thay đổi; nếu caller cần phân biệt hai tình huống, phải truy vấn thêm theo hợp đồng nghiệp vụ. Đây là cách kiểm soát **lost update** rõ ràng mà không phải tin vào thời hạn của RowId. Với thao tác nhiều bước, bao các SQL liên quan trong transaction quản lý bằng `Connection.setAutoCommit(false)`, `commit()` và `rollback()`.

Nếu chỉ liên kết hai bảng, dùng `FOREIGN KEY`. Nếu cần truyền ID giữa các dịch vụ, dùng một mã nghiệp vụ ổn định (ví dụ UUID hoặc khóa chính được quản lý), không truyền đối tượng `Ref` hay byte của `RowId`.

## 11. Kiểm tra khả năng hỗ trợ SQL type và driver

`DatabaseMetaData.getRowIdLifetime()` là phép kiểm tra chuyên biệt cho RowId. Với SQL `REF`, JDBC **không có một phép kiểm tra duy nhất đủ để bảo đảm mọi thao tác `getRef/getObject/setRef` đều chạy**.

`DatabaseMetaData.getTypeInfo()` có thể cho biết các loại SQL mà driver quảng bá, thường có cột `DATA_TYPE` tương ứng hằng `java.sql.Types`:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public static void inspectAdvancedTypes(DataSource source)
        throws SQLException {

    try (Connection con = source.getConnection()) {
        DatabaseMetaData meta = con.getMetaData();
        System.out.println("RowId lifetime = " + meta.getRowIdLifetime());

        try (ResultSet types = meta.getTypeInfo()) {
            while (types.next()) {
                int jdbcType = types.getInt("DATA_TYPE");
                if (jdbcType == Types.REF || jdbcType == Types.ROWID) {
                    System.out.println(types.getString("TYPE_NAME")
                            + " maps to " + jdbcType);
                }
            }
        }
    }
}
```

**Giới hạn:** danh sách từ `getTypeInfo()` chỉ mô tả metadata được quảng bá; việc không có dòng `Types.REF` chưa chắc mô tả đầy đủ mọi cú pháp object-relational riêng của vendor, còn có dòng `Types.REF` cũng **không chứng minh** câu DDL, `getRef()`, `Ref.getObject()` hoặc `setRef()` sẽ hoạt động với mọi bảng/truy vấn.

Một cách kiểm tra đáng tin cậy cho tính năng bắt buộc:

1. Xác nhận phiên bản JDK, JDBC driver, DB server và đặc tả vendor của loại dữ liệu.
2. Kiểm tra `getRowIdLifetime()` với RowId; kiểm tra metadata kiểu SQL với `getTypeInfo()` khi hữu ích.
3. Tạo **schema tối thiểu đúng vendor** có cột SQL `REF` hoặc truy vấn `ROWID` trên DB thử nghiệm.
4. Kiểm tra round-trip **đọc bằng `getRef/getRowId`, bind bằng `setRef/setRowId` và truy vấn lại**, cùng connection/transaction theo yêu cầu.
5. Kiểm tra tình huống không hỗ trợ, `NULL`, hàng bị xóa/di chuyển, thay transaction/session và lỗi permission.
6. Có phương án dùng khóa chính/khóa ngoại và SQL tham số hóa khi tính năng này không khả dụng.

Không bắt `SQLException` rồi tiếp tục như thể đã thành công. `SQLFeatureNotSupportedException` (một nhánh của `SQLNonTransientException`) có thể cho biết tính năng không được hỗ trợ, nhưng một driver cũng có thể báo bằng `SQLException` khác; cần giữ `SQLState`, vendor error code và cause cho chẩn đoán.

## 12. Transaction, connection pool và batch: các giới hạn thực tế

### 12.1. Một connection không phải một kho tham chiếu vĩnh viễn

`Ref` và `RowId` được nhận từ tài nguyên JDBC gắn với **cơ sở dữ liệu và driver cụ thể**. Khi connection hoặc session bị đóng, transaction kết thúc hay dữ liệu được tái tổ chức, việc dùng lại chúng có thể lỗi hoặc mang ý nghĩa khác theo DB.

Nếu đang ở transaction, không kỳ vọng một lần `rollback()` “hoàn tác được” các hiệu ứng ngoài DB; riêng các câu SQL liên quan phải chạy cùng connection nếu cần atomicity. Khi `commit()` mất kết nối và trạng thái không rõ, không retry thao tác ghi chỉ vì còn giữ một `Ref` hoặc `RowId`; hãy xác minh bằng **khóa nghiệp vụ ổn định**.

Connection pool có thể cấp logical connection mới trỏ tới session vật lý khác. Ngay cả khi `RowIdLifetime` báo `ROWID_VALID_SESSION`, đó không phải bảo đảm có thể dùng RowId trong request bất kỳ sau này.

### 12.2. Bind tham số và xử lý NULL

Đặt `Ref`/`RowId` vào SQL cũng phải dùng `PreparedStatement` với tham số `?`. Không ghép chuỗi biểu diễn của đối tượng vào SQL.

```java
// Chỉ dùng trên cột/tham số thực sự là SQL REF hoặc ROWID được hỗ trợ.
if (ref == null) {
    ps.setNull(1, java.sql.Types.REF);
} else {
    ps.setRef(1, ref);
}

if (rowId == null) {
    ps.setNull(2, java.sql.Types.ROWID);
} else {
    ps.setRowId(2, rowId);
}
```

Đây là ví dụ binding **hai tham số** trong một câu SQL có loại tương ứng, không phải ví dụ có thể áp dụng bất kỳ bảng nào. Kiểu của cột phải khớp và driver phải hỗ trợ. Nếu cột cho phép `NULL`, giá trị `null` trong Java khác với tham chiếu có giá trị nhưng đối tượng đích đã bị xóa hoặc không được truy cập.

### 12.3. Không tự động giả định batch hoạt động với REF/ROWID

`PreparedStatement.addBatch()`/`executeBatch()` hoặc `executeLargeBatch()` vẫn là API JDBC xử lý theo lô, nhưng một driver hỗ trợ `setRef` ở câu lệnh đơn **chưa chắc hỗ trợ đầy đủ** cùng loại dữ liệu khi rewrite batch. Nếu yêu cầu batch cập nhật tham chiếu:

- Bind đủ các tham số `REF`/`ROWID` ở mỗi lượt rồi mới `addBatch()`.
- Kiểm tra kiểu SQL, thứ tự dữ liệu và transaction.
- Xem `BatchUpdateException.getUpdateCounts()` hoặc `getLargeUpdateCounts()` khi lỗi; một số driver có thể dừng tại lỗi đầu hoặc tiếp tục.
- Không retry toàn bộ batch khi `commit()` chưa rõ kết quả mà không có idempotency/đối soát.
- Khi cần độ di động, ưu tiên batch theo khóa chính thông thường.

## 13. Quyền truy cập, tính nhất quán và hiệu năng

Một tham chiếu nội bộ tới hàng **không phải giấy thông hành vượt qua phân quyền**. Khi thao tác với `Ref` hoặc `RowId`, DB vẫn áp dụng quyền SQL và ứng dụng phải áp dụng tenant/user authorization như với khóa chính.

Ví dụ cập nhật theo RowId **mà không kiểm tra khóa nghiệp vụ** có thể khiến ứng dụng khó xác nhận có đang cập nhật đúng người dùng hay không. Nếu DB hỗ trợ và ứng dụng buộc phải dùng RowId, hãy kiểm tra thêm điều kiện nghiệp vụ phù hợp (ID/tenant/version) trong SQL; tốt hơn là dùng trực tiếp khóa chính và optimistic locking như mục 10.

Một số vấn đề hiệu năng:

| Quyết định | Tác động có thể có | Cách kiểm chứng |
| --- | --- | --- |
| `Ref.getObject()` nhiều lần | Có thể phát sinh truy vấn/truy cập DB cho từng tham chiếu | Đo round-trip và số câu SQL phát sinh, cân nhắc JOIN |
| Lookup bằng RowId | Có thể nhanh trong tình huống được DB tối ưu | So sánh execution plan và latency với lookup theo PK |
| Giữ nhiều `Ref`/`RowId` lâu dài | Nguy cơ vượt vòng đời, khó migrate, khó kiểm soát connection | Giới hạn phạm vi dùng trong request/transaction |
| Truyền RowId qua API | Phụ thuộc cách mã hóa của vendor, khó quản lý an toàn | Thay bằng business ID/UUID |
| Bind `REF` trong batch | Hỗ trợ khác nhau giữa driver, có thể lỗi hoặc không rewrite | Benchmark và integration test thật |

**Không kết luận “RowId nhanh hơn primary key” như một quy luật.** Trên hệ quản trị có chỉ mục khóa chính phù hợp, cách truy vấn theo PK có thể rất hiệu quả, dễ duy trì hơn và ít phụ thuộc cách DB tổ chức hàng. Việc đo hiệu năng phải diễn ra với dữ liệu, thống kê và mô hình transaction đại diện.

## 14. Những lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách sửa |
| --- | --- | --- |
| `Ref` là foreign key thông thường | SQL `REF` tham chiếu structured object, không phải giá trị FK số | Dùng FK cho schema quan hệ phổ biến |
| `Ref` là Java reference hoặc weak reference | Đây là interface JDBC ánh xạ SQL `REF` | Giữ rõ ranh giới JVM và DB |
| Hỗ trợ `REF_CURSOR` nghĩa là hỗ trợ `Ref` | `REF_CURSOR` là cursor, khác SQL `REF` | Kiểm thử đúng cột REF |
| Có `getRef()` trong JDK nghĩa là DB nào cũng chạy | Driver/DB phải hỗ trợ kiểu SQL thực tế | Kiểm tra bằng integration test |
| `getObject()` của `Ref` luôn trả `Struct` | Có thể phụ thuộc type mapping/driver | Kiểm tra kiểu trước khi ép |
| `RowId.getBytes()` là ID có thể trao đổi liên DB | Dữ liệu opaque, không có định dạng portable | Dùng khóa chính/UUID |
| `RowIdLifetime.ROWID_VALID_FOREVER` tương đương business ID | Chỉ nói tính ổn định RowId theo DB, không nói ngữ nghĩa nghiệp vụ | Không dùng RowId làm ID công khai |
| `ResultSet.getRow()` là cùng một giá trị với RowId | `getRow()` là số thứ tự trong tập kết quả | Dùng `getRowId()` chỉ trên cột ROWID hỗ trợ |
| Có `getRowIdLifetime()` khác unsupported là mọi SQL dùng ROWID đều chạy | SQL và binding vẫn phụ thuộc vendor/cột/driver | Thử `getRowId/setRowId` thật |
| Có RowId thì không cần khóa chính | Khó làm quan hệ, phân quyền, optimistic locking | Dùng schema PK/FK rõ ràng |
| Giữ `Ref`/`RowId` sau khi đóng connection luôn an toàn | Thời hạn, session và driver có thể hạn chế | Giới hạn phạm vi, truy vấn lại bằng PK |
| `setRef` và `Ref.setObject` là cùng hành động | Một bên bind tham chiếu, bên kia thao tác trên structured object | Chọn API theo ngữ nghĩa cần ghi |

## 15. Kiểm thử trên DB và driver thật

Các API này phụ thuộc vendor mạnh hơn nhiều kiểu SQL cơ bản. Unit test với fake `RowId` hoặc fake `Ref` chỉ kiểm tra code ứng dụng; nó **không chứng minh** DB hỗ trợ RowId/SQL REF hoặc đối tượng còn hợp lệ sau transaction.

| Tình huống | Điều cần xác minh |
| --- | --- |
| `DatabaseMetaData.getRowIdLifetime()` | Driver trả giá trị nào; chính sách ứng dụng theo transaction/session có phù hợp |
| DB không hỗ trợ RowId | Nhánh fallback theo khóa chính được dùng; không làm hỏng CRUD |
| Đọc cột REF khác `NULL` | `getRef()`, `getBaseTypeName()`, `getObject()` hoạt động với structured type đã tạo |
| Cột REF = `NULL` | `getRef()` trả `null` khi được driver hỗ trợ; mapper không trộn với thiếu hàng |
| Đọc lại REF khi đối tượng đích bị xóa/di chuyển | Hành vi DB được xử lý theo nghiệp vụ, không đoán từ Java API |
| `PreparedStatement.setRef()` | Có thể cập nhật cột tham chiếu cùng kiểu, commit và đọc lại đúng |
| REF sang connection khác | Phát hiện và xử lý nếu driver không hỗ trợ |
| Đọc/bind RowId | `getRowId()` rồi `setRowId()` trên chính DB/transaction đã chọn |
| RowId sau `commit()/rollback()` | Tôn trọng `RowIdLifetime` thực tế, không dựa vào giả định |
| Hàng bị xóa và tạo lại | RowId cũ không được coi là bằng chứng định danh hàng mới |
| Driver nâng cấp | Thử lại type mapping, SQLState, cách biểu diễn RowId và vòng đời |
| Truy vấn theo PK thay thế | Cùng nghiệp vụ vẫn chạy trên DB không có REF/ROWID |
| Batch dùng `REF`/`ROWID` | Xác minh count, rollback và lỗi trước/sau commit |

### Mẫu test nghiệp vụ cần thiết

1. Chèn một khách hàng có khóa chính ổn định và một quan hệ tới khách hàng (dùng FK hoặc REF tùy DB).
2. Đọc tham chiếu bằng API tương ứng; kiểm tra `NULL`, quyền đọc và kiểu SQL được trả.
3. Thay đổi dữ liệu đích rồi truy vấn lại; xác định phạm vi nhìn thấy thay đổi theo transaction isolation.
4. Commit, lấy connection mới và thử lại theo **hợp đồng RowIdLifetime/Ref của vendor**; nếu không còn hợp lệ, ứng dụng phải truy vấn lại bằng PK.
5. Dùng optimistic locking theo khóa chính làm baseline; so sánh hành vi trong hai transaction đồng thời.
6. Cố tình cho `setRef/setRowId` ném lỗi hoặc mất kết nối; bảo toàn `SQLException`, `SQLState` và những lỗi rollback/close phụ thêm.

Không chạy test chuyển hàng/di chuyển dữ liệu trên môi trường sản xuất. Chỉ thực hiện thí nghiệm về RowId trong DB thử nghiệm có dữ liệu đại diện và quyền thao tác thích hợp.

## 16. Bài tập thực hành

**Bài 1 — Phân loại:** Với các nhu cầu “liên kết đơn hàng với khách”, “tìm lại một hàng trong cùng transaction” và “xuất ID khách cho API”, hãy chọn foreign key, SQL REF hay RowId. Giải thích yếu tố hỗ trợ DB và độ ổn định ID.

**Bài 2 — Kiểm tra RowId:** Viết mã dùng `DataSource` gọi `getRowIdLifetime()`, hiển thị giá trị enum, rồi chọn nhánh fallback khi nhận `ROWID_UNSUPPORTED`. Thử trên hai driver khác nhau và ghi lại kết quả.

**Bài 3 — Đọc REF:** Trên DB hỗ trợ SQL structured type/REF, tạo đối tượng và một hàng có cột REF. Dùng `ResultSet.getRef()`, `Ref.getBaseTypeName()` và `Ref.getObject()`; thử cả giá trị SQL `NULL`, hàng không tồn tại và đối tượng đích không còn truy cập được.

**Bài 4 — Binding:** Giả sử `Ref` đã được lấy trong một transaction hợp lệ. Viết `PreparedStatement` để đổi cột tham chiếu và xử lý rollback khi cập nhật thất bại. Lý giải vì sao không thể chỉ dùng `setLong()` như một khóa ngoại nếu cột thực sự là SQL REF.

**Bài 5 — Định danh bền vững:** Một dịch vụ định truyền `RowId.getBytes()` qua hàng đợi đến worker xử lý ngày hôm sau. Xác định rủi ro theo `ROWID_VALID_TRANSACTION`, `ROWID_VALID_SESSION`, chuyển connection và migration. Thiết kế lại bằng ID nghiệp vụ ổn định kèm version.

## 17. Checklist áp dụng

- [ ] Có thực sự cần SQL REF/ROWID hay PK/FK thông thường đã giải quyết đủ bài toán?
- [ ] Đã phân biệt SQL REF, RefCursor, Java reference, RowId và `ResultSet.getRow()`?
- [ ] Đã xác nhận DB/driver hỗ trợ loại cột và `getRef/getObject/setRef` hoặc `getRowId/setRowId` thực tế?
- [ ] Với RowId, đã đọc `DatabaseMetaData.getRowIdLifetime()` và giới hạn sử dụng theo transaction/session?
- [ ] Không lưu hoặc phát RowId ra ngoài hệ thống như ID bền vững khi thiếu bảo đảm vendor?
- [ ] Mapper phân biệt không có hàng, cột REF/ROWID `NULL` và tham chiếu không còn hợp lệ?
- [ ] Với `Ref.getObject()`, đã hiểu type mapping, quyền truy cập, khả năng thêm round-trip và trường hợp structured object không có sẵn?
- [ ] Giá trị tham số được bind bằng `PreparedStatement`; không nối biểu diễn nhị phân/chuỗi của RowId vào SQL?
- [ ] Transaction, rollback, connection pool và batch đã được kiểm chứng với tính năng SQL vendor đang dùng?
- [ ] Có fallback theo PK/FK và test tích hợp cho driver/DB thật, kể cả khi không hỗ trợ?

Trong **JDBC**, `Ref` cung cấp cách truy cập một **tham chiếu SQL có kiểu** tới structured object, còn `RowId` biểu diễn **định danh hàng phụ thuộc hệ quản trị** và có thời hạn sử dụng do driver báo. Hai API mở ra khả năng tích hợp với hệ quản trị có tính năng nâng cao, nhưng không làm thay đổi nguyên tắc thiết kế quan hệ cơ bản: **dùng khóa chính/khóa ngoại cho định danh nghiệp vụ, dùng PreparedStatement cho truy vấn và kiểm chứng khả năng driver trước khi phụ thuộc vào REF/ROWID**.
