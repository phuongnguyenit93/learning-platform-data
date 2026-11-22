# Tránh biến siêu dữ liệu thành giả định tuyệt đối về hành vi thực thi trong JDBC

Trong **JDBC**, siêu dữ liệu (*metadata*) giúp ứng dụng Java hỏi driver và cơ sở dữ liệu về cấu trúc bảng, kiểu cột, tên sản phẩm, phiên bản, mức cô lập và những tính năng được công bố là có hỗ trợ. Nhờ `DatabaseMetaData`, `ResultSetMetaData` và `ParameterMetaData`, ứng dụng có thể kiểm tra thông tin lúc chạy mà không phải viết cố định mọi đặc điểm của database vào mã nguồn.

Tuy vậy, có một ranh giới quan trọng: **siêu dữ liệu mô tả cấu trúc hoặc khả năng được công bố, không phải lời bảo đảm tuyệt đối về cách mọi câu SQL sẽ thực thi trong mọi điều kiện**. Ví dụ, `supportsBatchUpdates() == true` không đồng nghĩa mọi batch đều nguyên tử; `supportsGetGeneratedKeys() == true` không đảm bảo driver trả đúng một khóa theo đúng thứ tự cho từng phần tử batch; còn `supportsTransactionIsolationLevel(...) == true` không mô tả toàn bộ cơ chế khóa, snapshot và xung đột của hệ quản trị.

Bài học thuộc chương **Siêu dữ liệu** của module **JDBC**. Ta sẽ phân biệt thông tin metadata với hành vi thực thi, học cách quan sát cấu trúc bảng và kết quả truy vấn bằng các API chuẩn, đánh giá các giới hạn của metadata, rồi thiết kế quy trình kiểm chứng trên cơ sở dữ liệu thật. Nội dung gắn với `DataSource`, `PreparedStatement`, `ResultSet`, CRUD, transaction, batching, xử lý lỗi và hiệu năng.

## 1. Metadata trả lời câu hỏi nào?

JDBC có ba nhóm metadata quan trọng:

| API | Nguồn lấy | Câu hỏi thích hợp |
| --- | --- | --- |
| `DatabaseMetaData` | `connection.getMetaData()` | Database và driver tên gì, phiên bản nào? Những tính năng nào được công bố hỗ trợ? Bảng, cột, khóa và chỉ mục nào được nhìn thấy? |
| `ResultSetMetaData` | `resultSet.getMetaData()` | Kết quả của câu truy vấn này có bao nhiêu cột, tên nhãn cột là gì, kiểu SQL và đặc tính được báo cáo là gì? |
| `ParameterMetaData` | `preparedStatement.getParameterMetaData()` | Statement có bao nhiêu tham số `?`, kiểu SQL hay chế độ tham số nào được driver mô tả? |

Một số ví dụ về câu hỏi mà metadata **không tự trả lời đầy đủ**:

- Một `INSERT` cụ thể có thành công dưới quyền của tài khoản hiện tại và trigger hiện có không?
- Một `UPDATE` đang cạnh tranh có bị chặn, deadlock hoặc hủy do serialization không?
- `executeBatch()` có đảm bảo tất cả phần tử cùng thành công hoặc rollback khi gặp lỗi không?
- Với câu lệnh `INSERT` nhiều hàng, khóa sinh ra có được trả đầy đủ và đúng thứ tự tương ứng đầu vào không?
- Một `SELECT` nhất định có thực sự dùng chỉ mục, streaming hay cursor trên server không?
- Giá trị SQL `NULL` hay dữ liệu Unicode/decimal cụ thể có được chuyển thành kiểu Java như dự tính không?
- Nếu schema vừa được migrate, thông tin metadata đã phản ánh tất cả thay đổi trên kết nối đang dùng chưa?

Đó là các câu hỏi về **quyền truy cập, dữ liệu, kế hoạch thực thi, trạng thái transaction, cấu hình server và hành vi của driver**. Cần kiểm tra tại đúng tầng liên quan.

### Ba mức độ chắc chắn

```text
Metadata / hợp đồng JDBC
       │  Cho biết thông tin hoặc tính năng được công bố
       ▼
Tài liệu driver + hệ quản trị + cấu hình
       │  Giải thích điều kiện hỗ trợ, ngoại lệ và ngữ nghĩa
       ▼
Thực thi và kiểm thử với SQL, schema, dữ liệu thực
          Xác nhận hành vi trong môi trường sẽ triển khai
```

Ba mức độ bổ sung cho nhau. Metadata rất hữu ích để **phát hiện khả năng**, tài liệu giúp hiểu **điều kiện sử dụng**, còn kiểm thử và quan sát runtime xác nhận **hành vi cho trường hợp cụ thể**.

## 2. Đọc `DatabaseMetaData`: một bản khảo sát, chưa phải chứng nhận

Ví dụ sau sử dụng `DataSource` và một `Connection` để in thông tin cơ sở dữ liệu cùng các khả năng JDBC công bố:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class MetadataInspector {
    private MetadataInspector() {
    }

    public static void inspect(DataSource dataSource) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData md = connection.getMetaData();

            System.out.println("Database: "
                    + md.getDatabaseProductName() + " "
                    + md.getDatabaseProductVersion());
            System.out.println("Driver: "
                    + md.getDriverName() + " " + md.getDriverVersion());

            System.out.println("Transactions supported: "
                    + md.supportsTransactions());
            System.out.println("Batch updates supported: "
                    + md.supportsBatchUpdates());
            System.out.println("Generated keys supported: "
                    + md.supportsGetGeneratedKeys());
            System.out.println("Stored procedures supported: "
                    + md.supportsStoredProcedures());

            System.out.println("REPEATABLE_READ advertised: "
                    + md.supportsTransactionIsolationLevel(
                            Connection.TRANSACTION_REPEATABLE_READ));
            System.out.println("Database default isolation: "
                    + md.getDefaultTransactionIsolation());
            System.out.println("Connection current isolation: "
                    + connection.getTransactionIsolation());
            System.out.println("Connection current autoCommit: "
                    + connection.getAutoCommit());
        }
    }
}
```

Điểm quan trọng trong cách đọc kết quả:

1. `getDatabaseProductName()` và `getDriverVersion()` giúp nhận diện môi trường, nhưng một phiên bản driver có thể kết nối với nhiều phiên bản server hoặc chạy dưới cấu hình khác nhau.
2. Các phương thức `supports...()` mô tả **khả năng hỗ trợ được công bố**. Giá trị `true` không chứng minh mọi cú pháp, kiểu cột hoặc tình huống đồng thời đều hoạt động giống nhau. `false` là tín hiệu không nên thiết kế chức năng dựa vào tính năng đó theo cách đang yêu cầu.
3. `getDefaultTransactionIsolation()` là thông tin mặc định được metadata báo cáo; `connection.getTransactionIsolation()` là giá trị **hiện được kết nối báo về**. Với connection pool, trạng thái hiện tại có thể đã được cấu hình khác mặc định.
4. `getAutoCommit()` cung cấp **trạng thái kết nối**, không phải năng lực database. Ngay cả cùng một mức cô lập, `autoCommit=true` và một transaction nhiều câu lệnh có thể cho kết quả quan sát khác nhau.
5. Lấy metadata tự nó cũng có thể liên quan giao tiếp với driver/server và ném `SQLException`. Không nên giả định mọi lần introspection là miễn phí.

Khi kết quả khảo sát được dùng để chọn tính năng quan trọng, hãy ghi nhận **database, phiên bản, driver, cấu hình pool và câu SQL thực tế** trong tài liệu triển khai. Một `boolean` đơn lẻ không thể thay thế những thông tin này.

## 3. Những suy diễn sai phổ biến từ metadata

| Tín hiệu metadata | Suy diễn hấp tấp | Cách hiểu và kiểm chứng |
| --- | --- | --- |
| `supportsTransactions() == true` | Mọi câu SQL và mọi bảng đều có thể rollback | Kiểm tra storage engine, loại DDL, tính chất transaction của câu lệnh và cách driver/server xử lý commit. |
| `supportsBatchUpdates() == true` | Batch luôn nhanh, nguyên tử và trả số hàng đầy đủ | Thử `executeBatch()`, `getUpdateCounts()`, lỗi giữa batch, `autoCommit` và transaction. |
| `supportsGetGeneratedKeys() == true` | Luôn có một khóa cho mỗi `INSERT`, kể cả batch, theo đúng thứ tự | Yêu cầu khóa đúng cách, kiểm tra `getGeneratedKeys()` với câu SQL và driver cụ thể; kiểm tra số lượng/thứ tự. |
| `supportsTransactionIsolationLevel(REPEATABLE_READ)` | Không có phantom, write skew hay lỗi cạnh tranh | Thử với nhiều `Connection` độc lập; xem ngữ nghĩa snapshot/locking của sản phẩm. |
| `supportsResultSetType(TYPE_SCROLL_INSENSITIVE)` | Mọi câu query đều cho `ResultSet` cuộn tự do | Thử request cụ thể khi `prepareStatement(...)`, kiểm tra type thực tế và trường hợp driver hạ cấp. |
| `getColumns(...)` trả `IS_NULLABLE = NO` | Ứng dụng chẳng cần kiểm tra giá trị | Bản ghi vẫn có thể bị chặn bởi các ràng buộc hoặc chuyển kiểu khác; metadata có thể phản ánh schema khác thời điểm thực thi. |
| `getTables(...)` không có bảng đang tìm | Bảng chắc chắn không tồn tại | Xem catalog/schema, chữ hoa-thường, pattern, quyền truy cập, loại đối tượng và schema hiện hành. |
| `getColumnClassName(...)` trả `java.lang.Integer` | Mọi giá trị phải được ánh xạ bằng `getInt()` và không thể `NULL` | Đọc đúng kiểu SQL/Java, xử lý `NULL`; class name là thông tin driver báo cho `getObject()`, không là bảo đảm cho mọi mapper. |
| `supportsStoredProcedures() == true` | `CallableStatement` gọi được mọi function/procedure không cần điều chỉnh | Kiểm tra cú pháp `CALL`/function, tham số `OUT`, cursor và quy tắc transaction riêng hệ quản trị. |

Đây là khác biệt giữa **có tính năng** và **đáp ứng một yêu cầu nghiệp vụ cụ thể**. Đặc biệt, dữ liệu không được ghi đúng hoặc transaction bị bỏ dở không thể được “sửa” bằng việc metadata báo `true`.

## 4. `ResultSetMetaData` cho biết hình dạng kết quả, không chứng minh giá trị thực

Khi mapper xây dựng đối tượng Java từ `ResultSet`, `ResultSetMetaData` giúp phân tích số cột, nhãn, kiểu SQL và các thuộc tính do driver báo cáo. Giả sử có bảng:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL,
    note VARCHAR(200)
);
```

Ví dụ sau truy vấn tập rỗng để xem **hình dạng kết quả**. Cú pháp `WHERE 1 = 0` được nhiều hệ quản trị SQL hỗ trợ; không nên cho rằng mọi hệ có cùng cú pháp cho mọi truy vấn phức tạp.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

public final class ResultShapeInspector {
    private ResultShapeInspector() {
    }

    public static void inspect(DataSource dataSource) throws SQLException {
        String sql =
                "SELECT id AS account_id, balance AS available_balance, note " +
                "FROM accounts WHERE 1 = 0";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql);
             ResultSet result = statement.executeQuery()) {

            ResultSetMetaData md = result.getMetaData();
            for (int i = 1; i <= md.getColumnCount(); i++) {
                System.out.println(
                        "column=" + i
                        + " label=" + md.getColumnLabel(i)
                        + " sqlType=" + md.getColumnType(i)
                        + " typeName=" + md.getColumnTypeName(i)
                        + " javaClass=" + md.getColumnClassName(i)
                        + " nullable=" + md.isNullable(i)
                        + " precision=" + md.getPrecision(i)
                        + " scale=" + md.getScale(i));
            }
        }
    }
}
```

**Những giới hạn cần ghi nhớ:**

- `getColumnLabel(i)` là **nhãn hiển thị của cột kết quả**, có thể là alias sau `AS`; `getColumnName(i)` có thể khác. Khi ánh xạ `ResultSet` theo tên, dùng alias ổn định và không mặc định cả hai là một.
- `getColumnType(i)` trả mã kiểu từ `java.sql.Types`; `getColumnTypeName(i)` trả tên kiểu do driver báo. Với kiểu đặc thù như JSON, enum, UUID hoặc array, ánh xạ sang Java có thể khác nhau theo driver.
- `getColumnClassName(i)` mô tả lớp Java mà driver dự kiến sử dụng khi gọi `getObject(i)`. Nó **không phải hợp đồng rằng mọi phương thức `getXxx()`, mọi conversion và mọi giá trị đều tương đương**.
- `ResultSetMetaData.isNullable(i)` trả một trong `columnNoNulls`, `columnNullable` hoặc `columnNullableUnknown`. Kết quả `columnNullableUnknown` không chứng minh cột có hoặc không cho `NULL`. Với expression, phép tính, join hoặc view, tính nullable còn phức tạp hơn mô tả bảng gốc.
- `getPrecision()`/`getScale()` giúp hiểu giới hạn được báo, nhưng không thay thế việc thử với `BigDecimal` cụ thể, quy tắc làm tròn hoặc ép kiểu của server.
- Với phép nối nhiều bảng, `getTableName()` hay `getSchemaName()` có thể rỗng hoặc không đủ để truy nguồn dữ liệu của một biểu thức; không suy từ đó ra tính toàn vẹn của nghiệp vụ.
- Một truy vấn trả `0` hàng vẫn có metadata của các cột kết quả, nhưng không chứng minh truy vấn thật với dữ liệu đầu vào khác sẽ không phát sinh lỗi runtime.

### Ví dụ: metadata kiểu số và giá trị `NULL`

```java
// Giả sử đã có ResultSet rs ở dòng hiện tại:
long id = rs.getLong("account_id");
BigDecimal balance = rs.getBigDecimal("available_balance");
String note = rs.getString("note");

// getBigDecimal/getString trả null cho SQL NULL.
// getLong trả 0 cho SQL NULL, nên phải kiểm tra khi cột có thể NULL:
boolean idWasNull = rs.wasNull(); // Chú ý: đã đọc cột khác nên SAI.
```

Đoạn trên minh họa **một lỗi có chủ đích**: `wasNull()` chỉ mô tả **cột vừa được đọc gần nhất** (trong trường hợp này là `note`), không mô tả lại `id`. Nếu cần xác định `id` có `NULL`, phải gọi ngay sau `getLong(...)`:

```java
long id = rs.getLong("account_id");
if (rs.wasNull()) {
    throw new SQLException("Unexpected NULL account ID");
}

BigDecimal balance = rs.getBigDecimal("available_balance");
String note = rs.getString("note");
```

Metadata khai báo khóa chính `NOT NULL` hữu ích nhưng mapper vẫn cần đọc dữ liệu đúng hợp đồng, nhất là khi kết quả là expression, join hoặc cột có thể null. Và đừng bao giờ dựa vào `getColumnClassName()` để bỏ các phép kiểm tra giá trị thực.

## 5. `ParameterMetaData`: hữu ích để thăm dò, không phải bộ xác thực phổ quát

`PreparedStatement.getParameterMetaData()` có thể báo số lượng và kiểu tham số `?` được driver suy ra. Tuy nhiên không phải driver nào cũng cung cấp thông tin đầy đủ trước khi thực thi, nhất là với SQL phức tạp, biểu thức chưa rõ kiểu hoặc cú pháp riêng.

```java
import java.sql.Connection;
import java.sql.ParameterMetaData;
import java.sql.PreparedStatement;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLException;

// Đoạn mã nằm trong scope đã sở hữu Connection connection.
String sql = "SELECT id FROM accounts WHERE id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    try {
        ParameterMetaData parameters =
                statement.getParameterMetaData();

        System.out.println("Parameter count: "
                + parameters.getParameterCount());
        System.out.println("Parameter SQL type: "
                + parameters.getParameterType(1));
    } catch (SQLFeatureNotSupportedException unsupported) {
        System.out.println(
                "Driver does not expose parameter metadata here");
    }
}
```

Không thể suy từ `getParameterType(1)` rằng giá trị người dùng truyền luôn hợp lệ. Một số driver trả kiểu tổng quát hoặc không xác định, và việc database chấp nhận phép chuyển kiểu còn phụ thuộc ngữ cảnh dữ liệu thực tế. Ứng dụng vẫn cần:

- Chọn setter rõ ràng như `setLong()`, `setBigDecimal()`, `setString()`, `setObject()` theo hợp đồng schema.
- Gán tham số hóa bằng `?` để tránh ghép trực tiếp dữ liệu người dùng vào SQL.
- Kiểm tra dữ liệu đầu vào và các ràng buộc ở tầng phù hợp.
- Bắt và xử lý `SQLException` khi `executeQuery()` hoặc `executeUpdate()` thực sự chạy.

Lưu ý `getParameterMetaData()` hoặc getter của đối tượng đó có thể ném các `SQLException` khác ngoài `SQLFeatureNotSupportedException`. Nếu báo lỗi bất thường, cần điều tra; không nên bắt mọi `SQLException` rồi bỏ qua như thể đó chỉ là “không hỗ trợ”.

## 6. Batch updates: `supportsBatchUpdates()` không có nghĩa “all or nothing”

Ví dụ ghi một nhóm đơn hàng bằng `PreparedStatement`:

```java
String sql =
        "INSERT INTO order_lines (order_id, product_id, quantity) " +
        "VALUES (?, ?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (OrderLine line : lines) {
        statement.setLong(1, line.getOrderId());
        statement.setLong(2, line.getProductId());
        statement.setInt(3, line.getQuantity());
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();
    // Chỉ diễn giải counts theo hợp đồng JDBC và driver thực tế.
}
```

Đây là đoạn lõi giả định `connection` và các đối tượng `OrderLine`/`lines` đã tồn tại, không phải một chương trình độc lập. `DatabaseMetaData.supportsBatchUpdates()` cho biết driver/database công bố hỗ trợ API batch, nhưng:

1. **Nguyên tử hay không** phụ thuộc transaction, storage engine và cách batch được xử lý; `executeBatch()` không tự định nghĩa một transaction nguyên tử cho mọi sản phẩm.
2. `executeBatch()` có thể ném `BatchUpdateException`. `getUpdateCounts()` chứa kết quả theo quy tắc JDBC; driver có thể dừng ngay khi lỗi hoặc tiếp tục các phần tử sau lỗi.
3. `Statement.SUCCESS_NO_INFO` nghĩa là thành công nhưng không biết số hàng tác động; `Statement.EXECUTE_FAILED` biểu thị phần tử thất bại khi driver tiếp tục xử lý và có thông tin tương ứng.
4. Driver có thể tối ưu hoặc viết lại batch thành SQL khác theo cấu hình. Khả năng hỗ trợ batch không chứng minh độ trễ thấp hơn từng câu SQL trong mọi workload.
5. Khi dùng `autoCommit=false`, tầng sở hữu transaction cần quyết định `commit()`/`rollback()`. Với batch một phần thất bại, hãy kiểm tra tác động của transaction, không chỉ số phần tử đã được báo thành công.

**Không tự fallback bằng cách gửi lại tất cả lệnh nếu chưa biết các phần tử trước đó đã chạy hay chưa.** Re-execution có thể chèn trùng, ghi đè dữ liệu hoặc tạo tác dụng phụ từ trigger.

## 7. Generated keys: có hỗ trợ API không đồng nghĩa có ánh xạ chính xác

`supportsGetGeneratedKeys() == true` thường được dùng để quyết định có gọi `getGeneratedKeys()` sau `INSERT`. Nhưng cần phân biệt:

```java
String sql = "INSERT INTO customers (name) VALUES (?)";

try (PreparedStatement statement = connection.prepareStatement(
        sql, java.sql.Statement.RETURN_GENERATED_KEYS)) {

    statement.setString(1, "Lan");
    int affected = statement.executeUpdate();

    if (affected != 1) {
        throw new SQLException("Expected exactly one inserted customer");
    }

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException(
                    "INSERT succeeded but no generated key was returned");
        }

        long id = keys.getLong(1);
        if (keys.wasNull()) {
            throw new SQLException("Generated customer ID is NULL");
        }

        // Sử dụng id trong hợp đồng của một INSERT thành công.
    }
}
```

Trong ví dụ, `connection` được tạo và quản lý ở tầng bên ngoài. Bảng `customers` cần có cột khóa do database sinh và driver phải hỗ trợ đọc khóa dạng `long`; với khóa chuỗi/UUID, thay getter phù hợp. Ngay cả khi `supportsGetGeneratedKeys()` trả `true`:

- Statement vẫn phải được chuẩn bị **yêu cầu trả khóa**, chẳng hạn với `RETURN_GENERATED_KEYS` hoặc tên cột cụ thể.
- `getGeneratedKeys()` có thể không trả dòng nào với một kiểu SQL, driver hoặc bảng nhất định.
- Nhãn, kiểu và số cột trong `ResultSet` khóa sinh có thể khác giữa driver.
- Sau `INSERT` nhiều hàng hoặc `executeBatch()`, không mặc định **một khóa trên mỗi phần tử theo đúng thứ tự** khi tài liệu driver chưa cam kết.
- Có thể cần cú pháp riêng của database như `RETURNING` và chiến lược ánh xạ khác; khi chuyển sang cú pháp riêng, tính khả chuyển SQL giảm.

Nếu `INSERT` đã thực thi nhưng việc đọc khóa thất bại, **không tự chạy lại `INSERT`** để “lấy ID lần nữa”: có thể tạo bản ghi thứ hai. Cần thiết kế transaction và cơ chế truy xuất/đối soát khóa an toàn.

## 8. Mức cô lập: metadata hỗ trợ mức nào vẫn cần thử nghiệm đồng thời

`DatabaseMetaData.supportsTransactionIsolationLevel(...)` và `getDefaultTransactionIsolation()` hữu ích cho cấu hình. Tuy nhiên, hai hệ quản trị cùng quảng bá `REPEATABLE READ` vẫn có thể khác ở cách đọc snapshot, mức khóa và lỗi xung đột.

| Metadata | Điều được biết | Điều cần kiểm chứng thêm |
| --- | --- | --- |
| `supportsTransactions()` | Database/driver công bố hỗ trợ transaction | Những bảng và câu SQL cụ thể có rollback đúng không? |
| `supportsTransactionIsolationLevel(REPEATABLE_READ)` | Mức cô lập này được công bố là hỗ trợ | Phantom, lost update, write skew, blocking, serialization failure như thế nào? |
| `getDefaultTransactionIsolation()` | Mức mặc định được báo cáo | Kết nối hiện tại/pool có đặt mức khác không? |
| `connection.getTransactionIsolation()` | Mức kết nối hiện báo về | Server triển khai mức này qua snapshot, khóa hay chính sách khác? |
| `connection.isReadOnly()` | Trạng thái read-only của kết nối theo API | Server thực sự từ chối các lệnh ghi nào? |

Cách tự xác minh ở môi trường thử nghiệm:

1. Tạo hai `Connection` **độc lập**, đều đặt `autoCommit=false` và mức cô lập cần thử **trước khi bắt đầu transaction**.
2. Cho kết nối A đọc một hàng; kết nối B thay đổi hàng và thử `commit()`.
3. Kết nối A đọc lại trong cùng transaction; ghi nhận giá trị, blocking, timeout hoặc lỗi.
4. Thử một truy vấn theo điều kiện (`WHERE status = 'PENDING'`), cho B thêm hàng khớp điều kiện rồi commit, xem A có quan sát phantom không.
5. Thử bất biến liên hàng (ví dụ hai bác sĩ trực, mỗi transaction cho một người nghỉ) để phát hiện kiểu xung đột không thể suy từ bảng dirty/non-repeatable/phantom truyền thống.

Phân biệt kết quả `supports...()` với thử nghiệm: **không thấy phantom trong một lần chạy** có thể do snapshot cố định, do B chưa commit hoặc do B đang bị khóa chặn. Cần ghi lại lịch chạy và mã lỗi để diễn giải đúng.

Trong ứng dụng JDBC sử dụng pool, sau khi transaction kết thúc phải phục hồi mức cô lập nếu phương thức đã thay đổi trước khi trả quyền sử dụng. Không thay mức isolation giữa transaction và không dùng `setAutoCommit(true)` để “dọn dẹp” khi rollback chưa thành công: thao tác thay đổi auto-commit có thể commit transaction đang mở.

## 9. Thông tin về `ResultSet` và hành vi cursor

`DatabaseMetaData` còn có các phương thức như:

```java
boolean scrollable = md.supportsResultSetType(
        ResultSet.TYPE_SCROLL_INSENSITIVE);

boolean updatable = md.supportsResultSetConcurrency(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_UPDATABLE);
```

Các lời gọi trên hỏi khả năng hỗ trợ chung của driver/database. Không có nghĩa mọi câu `SELECT` cụ thể đều cung cấp cursor cuộn hoặc cập nhật theo yêu cầu. Một truy vấn JOIN nhiều bảng, tổng hợp dữ liệu hoặc thiếu khóa định danh có thể không phù hợp với `CONCUR_UPDATABLE`.

Khi thực sự cần loại `ResultSet` cụ thể, phải yêu cầu lúc tạo statement và kiểm tra kết quả:

```java
String sql = "SELECT id, balance FROM accounts ORDER BY id";

try (PreparedStatement statement = connection.prepareStatement(
        sql,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);
     ResultSet result = statement.executeQuery()) {

    int actualType = result.getType();
    int actualConcurrency = result.getConcurrency();

    if (actualType != ResultSet.TYPE_SCROLL_INSENSITIVE) {
        // Không dùng previous(), absolute() hoặc last()
        // với giả định cursor chắc chắn scrollable.
        throw new SQLException("Scrollable ResultSet was not provided");
    }

    // Có thể đọc và sử dụng cursor theo hợp đồng hiện được báo.
}
```

Đoạn minh họa giả định `connection` đang mở. `PreparedStatement` và `ResultSet` được đóng bằng `try-with-resources`. Một số driver có thể cảnh báo/hạ cấp yêu cầu type/concurrency hoặc ném ngoại lệ khi không hỗ trợ; cần đọc cả `SQLWarning` nếu ứng dụng quan tâm đến việc driver điều chỉnh cấu hình.

**Metadata không thay thế đo đạc hiệu năng cursor.** Một `ResultSet` được báo là `TYPE_FORWARD_ONLY` không tự chứng minh toàn bộ dữ liệu được streaming; fetch size, cấu hình auto-commit, khả năng server cursor và cách driver tải dữ liệu còn ảnh hưởng bộ nhớ, số round trip và độ trễ. Cần kiểm tra tài liệu driver và đo workload thật.

## 10. Metadata schema: dữ liệu có thể thiếu do phạm vi, quyền và cách đặt tên

`DatabaseMetaData.getTables()`, `getColumns()`, `getPrimaryKeys()`, `getImportedKeys()` hay `getIndexInfo()` là những công cụ hữu ích khi xây dựng hệ thống migration, explorer hoặc kiểm tra cấu hình schema. Ví dụ:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void printCustomerColumns(Connection connection)
        throws SQLException {

    DatabaseMetaData md = connection.getMetaData();

    try (ResultSet columns = md.getColumns(
            null,        // catalog: theo quy ước của driver
            null,        // schema pattern
            "customers", // tableNamePattern
            "%")) {     // columnNamePattern

        while (columns.next()) {
            System.out.println(
                    "schema=" + columns.getString("TABLE_SCHEM")
                    + " table=" + columns.getString("TABLE_NAME")
                    + " column=" + columns.getString("COLUMN_NAME")
                    + " type=" + columns.getString("TYPE_NAME")
                    + " nullable=" + columns.getInt("NULLABLE"));
        }
    }
}
```

Cách diễn giải cần thận trọng:

- `tableNamePattern` và `columnNamePattern` có quy tắc pattern kiểu SQL; `%` và `_` có ý nghĩa đặc biệt. Không truyền tên bảng chứa ký tự đặc biệt như thể nó luôn được hiểu là chuỗi khớp chính xác. `getSearchStringEscape()` giúp biết ký tự thoát pattern của driver.
- `null` cho catalog/schema có ý nghĩa theo hợp đồng JDBC và cách driver xử lý; không mặc định chỉ tìm trong **schema hiện hành**. Trên một số database, cần truyền schema/catalog cụ thể và xem trường hợp tên có chữ hoa/thường hoặc quoted identifier.
- `getTables()` có thể phân biệt `TABLE`, `VIEW` và loại đối tượng khác; đừng chỉ tìm `TABLE` rồi kết luận view không tồn tại.
- **Quyền truy cập** có thể giới hạn những bảng và cột được lộ ra qua metadata. Không trả về một hàng không chứng minh tài nguyên không tồn tại trên server.
- Schema có thể thay đổi giữa lúc introspection và thực thi SQL do migration hoặc thay đổi quyền. Tránh xem metadata là một snapshot cấu trúc vĩnh viễn.
- `getColumns().getInt("NULLABLE")` có giá trị kiểu `DatabaseMetaData.columnNoNulls`, `columnNullable` hoặc `columnNullableUnknown`. Nếu cần phân biệt chính xác, đừng coi giá trị `0` của cột kết quả là “unknown”.
- Metadata của view, expression, cột sinh tự động và khóa liên quan các bảng có thể phụ thuộc khả năng phản ánh catalog của driver; kiểm tra từ schema thật và trường hợp dữ liệu thực.

Nếu ứng dụng tạo SQL động từ metadata, **không dùng giá trị metadata như giấy phép nối trực tiếp tên bảng do người dùng nhập vào SQL**. Placeholder `?` áp dụng cho **giá trị**, không thay thế được identifier. Với tên bảng/cột động, chỉ chọn từ danh sách cho phép do hệ thống kiểm soát và quote theo cú pháp database đã xác minh.

## 11. Metadata có thể trở nên cũ hoặc tạo thêm tải

Metadata thường được coi như “một cú gọi getter”, nhưng mức chi phí thực tế phụ thuộc driver:

- Driver có thể truy vấn catalog hệ thống qua mạng hoặc lấy thêm thông tin từ server.
- Introspection schema lặp lại trên mỗi request có thể làm tăng latency và tải vào catalog.
- Driver/pool hoặc chính ứng dụng có thể lưu cache; cache giúp giảm chi phí nhưng làm tăng rủi ro dữ liệu cũ sau migration.
- Sau khi thay đổi schema, một statement đã chuẩn bị trước và metadata đã lấy trước đó có thể không còn mô tả đúng giả định của thao tác mới.
- Quyền xem metadata và đường dẫn tìm schema có thể khác nhau giữa các role, môi trường và tenant.

Vì vậy, nên phân biệt:

**Khám phá khả năng ở thời điểm khởi động hoặc cấu hình:** khảo sát database/driver, bật chức năng tương ứng và xác thực bằng kiểm thử tích hợp.

**Ánh xạ kết quả trong một truy vấn:** dùng `ResultSetMetaData` ngay trong phạm vi truy vấn nếu cần xử lý cấu trúc động; tránh gọi lại introspection không cần thiết cho mỗi dòng `ResultSet`.

**Kiểm tra schema sau migration:** chạy kiểm tra trong quy trình deploy hoặc điểm kiểm soát đã định nghĩa, thay vì để metadata cũ tồn tại vô thời hạn.

**Đánh giá hiệu năng:** đo chi phí của metadata khi chạy thực tế, nhất là nếu thông tin catalog được đọc hàng nghìn lần trong giây.

Dù metadata được cache, ứng dụng vẫn phải xử lý `SQLException` khi chạy SQL vì quyền, schema, dữ liệu hoặc kết nối có thể thay đổi.

## 12. Dùng metadata để quyết định có kiểm soát

Một cách triển khai an toàn là tách **thăm dò → lựa chọn → thực thi → xác minh → xử lý lỗi**:

```text
DatabaseMetaData
    │
    ▼
Tính năng được công bố hỗ trợ?
    ├── Không → chọn phương án đã kiểm thử khác
    └── Có
         │
         ▼
      Chọn SQL / API phù hợp driver + database
         │
         ▼
      Thực thi và kiểm tra kết quả thật
         ├── Thành công → xác minh số hàng, khóa, dữ liệu
         └── Lỗi → rollback/đối soát theo hợp đồng
                    trước khi xét retry hoặc fallback
```

Không phải tính năng nào cũng phù hợp với fallback tự động. Ví dụ, nếu `INSERT` đã thành công trên server rồi kết nối lỗi lúc lấy generated key, chạy lại `INSERT` bằng một chiến lược khác có thể tạo bản ghi trùng. Nếu `executeBatch()` đã chạy một phần, gửi lại toàn bộ batch có thể gây hiệu ứng lặp. Quyết định retry cần dựa trên **kết quả transaction, idempotency và khả năng xác định thao tác đã xảy ra chưa**, không chỉ giá trị `supports...()`.

### Bảng phương án xác minh theo tính năng

| Tính năng cần dùng | Metadata khởi đầu | Kiểm chứng thực tế |
| --- | --- | --- |
| Transaction | `supportsTransactions()` | Commit/rollback trên các bảng, loại lệnh và storage engine đang dùng |
| Isolation | `supportsTransactionIsolationLevel(level)` | Hai connection, snapshot, blocking, lỗi serialization, bất biến nhiều hàng |
| Batch | `supportsBatchUpdates()` | `executeBatch()` thành công/thất bại, `BatchUpdateException`, transaction |
| Generated keys | `supportsGetGeneratedKeys()` | `RETURN_GENERATED_KEYS`, số/type/thứ tự khóa trả về, batch/multirow |
| Scrollable cursor | `supportsResultSetType(type)` | `getType()` trên `ResultSet` thật, hành vi `previous()`/`absolute()` khi được hỗ trợ |
| Kiểu dữ liệu | `getTypeInfo()`/`ResultSetMetaData` | Chèn/đọc round-trip giá trị đại diện, `NULL`, Unicode, decimal, timezone |
| Stored procedures | `supportsStoredProcedures()` | `CallableStatement` với tham số `IN`/`OUT`, cursor, transaction, quyền và driver |
| Schema | `getTables()`/`getColumns()` | Truy vấn với đúng user/schema, tên quote, quyền và phiên bản migration |

## 13. Bài thực hành: một báo cáo metadata đi kèm bằng chứng thực thi

Giả sử bạn được giao xây dựng tính năng import nhiều khách hàng và trả về ID vừa tạo. Hãy thực hiện theo thứ tự:

1. Tạo bảng `customers` có khóa `id` tự sinh và cột `name`, dùng database/driver thật của môi trường học.
2. Viết `MetadataInspector` để ghi `getDatabaseProductName()`, `getDriverVersion()`, `supportsBatchUpdates()` và `supportsGetGeneratedKeys()`.
3. Dùng `PreparedStatement` với `RETURN_GENERATED_KEYS` để chèn một hàng, gọi `getGeneratedKeys()` và xác minh kết quả. Kiểm tra kiểu khóa và `keys.next()` thay vì tin metadata hoàn toàn.
4. Thử một batch gồm ba khách hàng. Kiểm tra `executeBatch()`, các update counts và số khóa sinh trả về; ghi rõ driver có cam kết ánh xạ thứ tự khóa với đầu vào không.
5. Cố ý tạo một phần tử lỗi, chẳng hạn tên vượt giới hạn cột. Quan sát `BatchUpdateException`, giao dịch ở chế độ `autoCommit=false`, rollback và tình trạng dữ liệu sau lỗi.
6. Đọc `ResultSetMetaData` từ câu `SELECT id AS customer_id, name FROM customers`; so sánh nhãn và tên cột, kiểu SQL/Java được báo và giá trị thật.
7. Chạy `getColumns()` bằng schema/user khác hoặc thử mẫu tên có chữ hoa, chữ thường, dấu gạch dưới; giải thích tại sao kết quả có thể khác nhau.
8. Lập bảng kết luận riêng cho **metadata công bố**, **hành vi quan sát**, **tài liệu driver** và **rủi ro còn lại**. Không ghi “hỗ trợ tuyệt đối” chỉ vì một lần thử thành công.

### Câu hỏi tự kiểm tra

- `supportsGetGeneratedKeys() == true` có bảo đảm `executeBatch()` trả một khóa cho mỗi phần tử theo cùng thứ tự không? Vì sao?
- Tại sao `getColumnClassName()` không thay thế việc kiểm tra `NULL`, kiểu SQL và giá trị trả về từ `ResultSet`?
- `getDefaultTransactionIsolation()` và `getTransactionIsolation()` có thể khác nhau trong hoàn cảnh nào?
- Nếu `getTables()` trả tập rỗng, bạn cần kiểm tra những yếu tố gì trước khi kết luận bảng không tồn tại?
- `supportsBatchUpdates()` có bảo đảm batch được commit nguyên tử không?
- Metadata báo `TYPE_SCROLL_INSENSITIVE` được hỗ trợ, nhưng statement không cung cấp cursor như yêu cầu. Mã Java cần làm gì?
- Khi schema migration vừa xảy ra, có thể có vấn đề gì nếu cache metadata không được làm mới?
- Vì sao không nên thực thi lại `INSERT` chỉ vì `getGeneratedKeys()` gặp lỗi sau khi SQL đã chạy?

## 14. Nguyên tắc cần ghi nhớ

1. **Đọc metadata đúng mục đích:** `DatabaseMetaData` là khả năng và catalog, `ResultSetMetaData` là hình dạng kết quả, `ParameterMetaData` là thông tin về placeholder.
2. **Phân biệt công bố hỗ trợ với hành vi thật:** giá trị `true` không thay thế điều kiện theo driver, kiểu SQL, transaction và dữ liệu.
3. **Giữ ranh giới hợp đồng rõ ràng:** xác định kết quả bằng số hàng, dòng `ResultSet`, mã lỗi và ràng buộc, thay vì suy từ metadata.
4. **Thử nghiệm các trường hợp cạnh tranh và thất bại:** isolation, batching, generated keys và rollback chỉ có thể đánh giá đủ khi chạy nhiều kịch bản thật.
5. **Không tự fallback hoặc retry thao tác ghi khi kết quả chưa rõ:** lỗi kết nối, timeout hoặc kết quả từng phần cần cơ chế đối soát và idempotency.
6. **Theo dõi quyền, schema và chi phí introspection:** metadata có thể bị giới hạn, trở nên cũ hoặc phát sinh nhiều lượt mạng; cache phải có chính sách làm mới.
7. **Ghi lại bằng chứng triển khai:** database, driver, phiên bản, cấu hình, SQL, dữ liệu thử và hành vi quan sát là phần quan trọng của quyết định kỹ thuật.

**Kết luận:** metadata là công cụ giúp ứng dụng JDBC thích ứng và tự quan sát tốt hơn. Dùng nó để đặt câu hỏi đúng, chọn chiến lược và tạo kiểm tra ban đầu; để quyết định **một thao tác có thực sự đúng và an toàn hay không**, vẫn phải đối chiếu tài liệu driver với SQL, dữ liệu, transaction và kết quả thực tế trên hệ quản trị được triển khai.
