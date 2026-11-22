# Đọc nhãn cột và kiểu cột qua ResultSetMetaData

Một câu truy vấn JDBC có thể trả về nhiều cột với tên, bí danh và kiểu dữ liệu khác nhau. Nếu ứng dụng chỉ biết trước tên cột hoặc luôn đoán kiểu Java từ tên SQL, việc viết công cụ xuất báo cáo, hiển thị bảng động hay kiểm tra thay đổi lược đồ sẽ dễ gặp lỗi. **`ResultSetMetaData`** cho phép xem **cấu trúc các cột trong kết quả truy vấn** ngay trên `ResultSet`, không cần tự phân tích chuỗi SQL.

Trong chương **Siêu dữ liệu** của module **JDBC**, bài này tập trung vào hai thông tin quan trọng: **nhãn cột** mà truy vấn trả về (`getColumnLabel`) và **kiểu SQL của cột** (`getColumnType`, `getColumnTypeName`). Bạn sẽ kết hợp chúng với `DataSource`, `PreparedStatement`, `ResultSet` và các API chuẩn để xử lý kết quả có cấu trúc linh hoạt, đồng thời hiểu giới hạn của metadata giữa các driver và hệ quản trị cơ sở dữ liệu (DBMS).

## 1. ResultSetMetaData trả lời những câu hỏi gì?

`java.sql.ResultSetMetaData` mô tả **các cột trong tập kết quả** của một truy vấn. Bạn lấy nó từ `ResultSet.getMetaData()`:

```java
try (ResultSet rs = statement.executeQuery()) {
    ResultSetMetaData md = rs.getMetaData();
    int numberOfColumns = md.getColumnCount();

    for (int i = 1; i <= numberOfColumns; i++) {
        System.out.println(md.getColumnLabel(i) + " : "
                + md.getColumnTypeName(i));
    }
}
```

Đây là **đoạn mã minh họa bên trong ngữ cảnh đã có `statement`**, không phải lớp Java độc lập. `getColumnCount()` trả tổng số cột; `getColumnLabel(i)` cho biết tiêu đề nên dùng để trình bày; `getColumnTypeName(i)` cho biết tên kiểu dữ liệu do driver cung cấp.

Đáng chú ý:

- **Chỉ số cột JDBC bắt đầu từ `1`**, không bắt đầu từ `0` như chỉ số mảng/`List` của Java.
- Metadata mô tả **cột được chọn bởi câu SQL**, không nhất thiết mô tả toàn bộ cột của bảng cơ sở.
- Có thể gọi `getMetaData()` **trước `rs.next()`**, kể cả khi truy vấn trả về **0 hàng**, vì định nghĩa cột và số hàng là hai thông tin khác nhau.
- `ResultSetMetaData` cho biết kiểu và các thuộc tính được driver báo cáo; nó **không tự đọc giá trị** của từng ô. Muốn lấy dữ liệu, gọi `rs.next()` và `rs.getObject(i)` hoặc các getter có kiểu.

Ví dụ một câu truy vấn:

```sql
SELECT p.id AS product_id,
       p.name AS product_name,
       p.unit_price AS display_price
FROM products p
WHERE p.category_id = ?;
```

Kết quả có ba cột, bất kể bảng `products` còn bao nhiêu cột khác. Tiêu đề mà màn hình hoặc tệp xuất nên hiển thị có thể là `product_id`, `product_name` và `display_price` theo các bí danh `AS`.

## 2. Phân biệt nhãn cột với tên cột

Hai phương thức dễ nhầm nhất là:

| Phương thức | Ý nghĩa | Nên dùng khi |
| --- | --- | --- |
| `getColumnLabel(index)` | **Nhãn gợi ý để hiển thị** của cột trong kết quả. Thường là bí danh `AS` nếu truy vấn khai báo; nếu không, thông thường là tên cột. | Dựng tiêu đề bảng, header CSV, tên trường trong kết quả động. |
| `getColumnName(index)` | **Tên cột SQL** mà driver báo cáo. Với cột bắt nguồn từ một bảng, có thể là tên cột gốc; với biểu thức/bí danh, hành vi có thể khác giữa driver. | Công cụ phân tích metadata khi có thể xác định cột gốc và đã kiểm chứng driver. |

Giả sử có SQL:

```sql
SELECT id AS product_id,
       unit_price AS listed_price,
       unit_price * 0.9 AS discount_price
FROM products
WHERE id = ?;
```

Bạn có thể kỳ vọng nhãn `product_id`, `listed_price` và `discount_price`. Trong nhiều driver, `getColumnName` đối với hai cột đầu có thể trả `id`, `unit_price`, còn cột biểu thức có thể không có tên cột gốc rõ ràng. **Không khẳng định mọi DBMS/driver trả một kết quả `getColumnName` cố định cho biểu thức hoặc alias**.

Để xây giao diện theo kết quả SQL, dùng `getColumnLabel` làm tiêu đề. Nếu ứng dụng cần biết cột thực sự thuộc bảng nào, `getColumnTableName` không phải API JDBC: có thể thử `getTableName(index)`, `getSchemaName(index)` hoặc `getCatalogName(index)` của `ResultSetMetaData`, nhưng các phương thức này có thể trả chuỗi rỗng khi nguồn không xác định hoặc driver không cung cấp đủ metadata.

### Hai cột có thể có cùng nhãn

```sql
SELECT a.id AS id,
       b.id AS id
FROM accounts a
JOIN branches b ON a.branch_id = b.id;
```

Cả hai cột đều có nhãn `id`. Nếu tạo `Map<String, Object>` bằng cách dùng nhãn làm key, giá trị thứ hai có thể ghi đè giá trị thứ nhất. Khi cần xuất dữ liệu động, **giữ cả chỉ số cột** hoặc quy định bí danh duy nhất như `account_id` và `branch_id`.

Không giả định nhãn cột luôn giữ đúng chữ hoa/chữ thường như khi viết SQL: cách DBMS và driver chuẩn hóa tên không đặt trong dấu quote có thể khác nhau. Khi hợp đồng API yêu cầu tên chính xác, nên dùng bí danh rõ ràng và kiểm tra kết quả thực tế.

## 3. Ba loại thông tin về kiểu cột

Ngoài nhãn, `ResultSetMetaData` cung cấp nhiều cách mô tả kiểu của một cột:

| API | Kiểu trả về | Vai trò |
| --- | --- | --- |
| `getColumnType(index)` | `int` | **Mã kiểu SQL JDBC** tương ứng với các hằng `java.sql.Types`. |
| `getColumnTypeName(index)` | `String` | **Tên kiểu dữ liệu do DBMS/driver báo cáo**, ví dụ `VARCHAR`, `DECIMAL` hoặc tên vendor-specific. |
| `getColumnClassName(index)` | `String` | Tên đầy đủ của lớp Java mà driver dự kiến dùng để biểu diễn giá trị qua `ResultSet.getObject(index)`. |

Ví dụ mã JDBC thường gặp:

| Kiểu SQL thường gặp | Mã hằng `java.sql.Types` | Giá trị Java thường gặp khi đọc |
| --- | --- | --- |
| `INTEGER` | `Types.INTEGER` | `Integer` |
| `BIGINT` | `Types.BIGINT` | `Long` |
| `VARCHAR` | `Types.VARCHAR` | `String` |
| `DECIMAL` hoặc `NUMERIC` | `Types.DECIMAL` hoặc `Types.NUMERIC` | `BigDecimal` |
| `DATE` | `Types.DATE` | `java.sql.Date` qua ánh xạ truyền thống; có thể yêu cầu `LocalDate` với `getObject(i, LocalDate.class)` khi hỗ trợ. |
| `TIMESTAMP` | `Types.TIMESTAMP` | `java.sql.Timestamp` qua ánh xạ truyền thống; có thể yêu cầu `LocalDateTime` khi driver hỗ trợ. |
| `TIMESTAMP WITH TIME ZONE` | `Types.TIMESTAMP_WITH_TIMEZONE` | Có thể dùng `OffsetDateTime` với driver JDBC 4.2 hỗ trợ. |

Các cột trong bảng này là **ví dụ ánh xạ phổ biến**, không phải bảo đảm mọi driver trả đúng một lớp Java như nhau. Một số kiểu DBMS đặc thù (như JSON, UUID, array, enum, kiểu hình học) có thể được báo là `Types.OTHER` hoặc có kiểu riêng; đôi khi `getColumnClassName` không khớp với lớp Java bạn kỳ vọng. Vì vậy:

1. Dùng `getColumnType` khi logic cần kiểm tra **nhóm kiểu theo chuẩn JDBC**.
2. Dùng `getColumnTypeName` khi muốn **hiển thị hoặc chẩn đoán tên kiểu gốc** của DBMS.
3. Dùng `getColumnClassName` khi cần biết kiểu đối tượng mặc định mà driver quảng bá; nếu nghiệp vụ cần kiểu Java cụ thể, nên gọi getter có kiểu và kiểm tra hỗ trợ.

Không lấy `getColumnTypeName()` làm đầu vào của `Class.forName(...)`. Giá trị như `NUMERIC` hay `JSONB` là tên kiểu SQL, **không phải** tên lớp Java. Và cũng không nên mặc định mọi mã kiểu đều có một lớp Java duy nhất.

### Cách so sánh kiểu bằng mã hằng

```java
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Types;

static boolean isDecimalColumn(ResultSetMetaData meta, int index)
        throws SQLException {
    int sqlType = meta.getColumnType(index);
    return sqlType == Types.DECIMAL || sqlType == Types.NUMERIC;
}
```

Nếu ứng dụng yêu cầu cột tiền dạng decimal, cách kiểm tra này hữu ích hơn việc so sánh chuỗi `"DECIMAL"` vì một số DBMS gọi kiểu đó là `NUMERIC`, `NUMBER` hoặc tên khác. Dù vậy, một kiểu vendor-specific có thể cần chiến lược nhận diện khác và kiểm tra với driver thực tế.

## 4. Ví dụ JDBC đầy đủ: đọc nhãn, tên, kiểu của kết quả truy vấn

Giả sử bảng `products` được tạo bằng một lược đồ minh họa:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    category_id BIGINT NOT NULL
);
```

Mã dưới đây dùng `DataSource` và `PreparedStatement` để thực hiện SQL tham số hóa, lấy `ResultSetMetaData`, in mô tả từng cột rồi mới đọc các hàng. Nó **không phụ thuộc việc truy vấn thực sự có trả về dữ liệu hay không** để biết số cột, nhãn và kiểu.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;
import java.util.Objects;

public final class ProductMetadataReader {
    private final DataSource dataSource;

    public ProductMetadataReader(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void inspectCategory(long categoryId) throws SQLException {
        String sql = "SELECT id AS product_id, "
                   + "name AS product_name, "
                   + "unit_price AS display_price "
                   + "FROM products WHERE category_id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, categoryId);

            try (ResultSet rs = statement.executeQuery()) {
                ResultSetMetaData md = rs.getMetaData();
                int columns = md.getColumnCount();

                // Metadata đọc được trước rs.next(), kể cả 0 hàng.
                for (int index = 1; index <= columns; index++) {
                    System.out.printf(
                            "#%d label=%s, name=%s, jdbcType=%d, "
                            + "dbType=%s, javaClass=%s%n",
                            index,
                            md.getColumnLabel(index),
                            md.getColumnName(index),
                            md.getColumnType(index),
                            md.getColumnTypeName(index),
                            md.getColumnClassName(index));
                }

                // Phần đọc giá trị là bước riêng, không phải metadata.
                while (rs.next()) {
                    for (int index = 1; index <= columns; index++) {
                        Object value = rs.getObject(index);
                        System.out.printf("%s=%s%s",
                                md.getColumnLabel(index),
                                value,
                                index == columns ? "\n" : ", ");
                    }
                }
            }
        }
    }
}
```

Ví dụ sử dụng khi ứng dụng đã cấu hình `dataSource`:

```java
ProductMetadataReader reader = new ProductMetadataReader(dataSource);
reader.inspectCategory(10L);
```

**Diễn giải:**

- `prepareStatement(sql)` tạo một truy vấn có tham số `?`; `setLong(1, categoryId)` truyền giá trị an toàn, tránh nối tham số vào câu SQL.
- `executeQuery()` trả về `ResultSet`. `rs.getMetaData()` lấy mô tả cột **của kết quả này**, không lấy danh sách cột của mọi bảng trong schema.
- Vòng lặp metadata chạy từ `1` đến `getColumnCount()` **bao gồm cả cột cuối**. Vòng lặp hàng dùng `rs.next()` và `rs.getObject(index)` để lấy giá trị.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` ngay cả khi xảy ra `SQLException`. Với connection pool, `close()` thường trả kết nối về pool.
- `getColumnLabel(index)` được in cho tiêu đề; `getColumnName(index)` phục vụ tham khảo. Kết quả chính xác của `getColumnName`/`getColumnTypeName` phụ thuộc driver.

Đây là ví dụ dạy về metadata. Khi xây hệ thống thật, đừng in toàn bộ dữ liệu truy vấn hoặc nội dung lỗi nhạy cảm ra stdout/log. Với cột nhị phân, `Blob`, `Clob` hoặc tập kết quả cực lớn, `String.valueOf(rs.getObject(index))` có thể vô ích hoặc tốn tài nguyên; cần lựa chọn getter và cách xử lý giá trị theo kiểu SQL.

## 5. Khám phá thêm precision, scale và khả năng NULL

Hai cột có cùng `Types.DECIMAL` có thể khác nhau nhiều về số chữ số và phần thập phân. `ResultSetMetaData` còn mô tả:

| Phương thức | Nội dung |
| --- | --- |
| `getPrecision(index)` | Độ chính xác mà driver báo cáo, với kiểu số thường là tổng số chữ số có nghĩa. |
| `getScale(index)` | Với số thập phân thường là số chữ số sau dấu thập phân. |
| `isNullable(index)` | Trạng thái cho phép `NULL`: `columnNoNulls`, `columnNullable` hoặc `columnNullableUnknown`. |
| `isAutoIncrement(index)` | Cột có được driver báo là tự sinh giá trị tăng hay không. |
| `isSigned(index)` | Cột số có dấu theo metadata driver. |
| `getColumnDisplaySize(index)` | Độ rộng hiển thị đề xuất (theo ký tự) do driver báo cáo; không phải độ rộng UI bắt buộc. |
| `getTableName(index)` / `getSchemaName(index)` | Tên bảng/schema nguồn nếu driver xác định được, có thể là chuỗi rỗng. |

Ví dụ:

```java
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

static void describeColumn(ResultSetMetaData md, int i)
        throws SQLException {
    String nullability;
    switch (md.isNullable(i)) {
        case ResultSetMetaData.columnNoNulls:
            nullability = "NOT NULL";
            break;
        case ResultSetMetaData.columnNullable:
            nullability = "có thể NULL";
            break;
        default:
            nullability = "chưa xác định";
    }

    System.out.printf(
            "%s: %s, precision=%d, scale=%d, %s%n",
            md.getColumnLabel(i),
            md.getColumnTypeName(i),
            md.getPrecision(i),
            md.getScale(i),
            nullability);
}
```

Với cột `unit_price DECIMAL(12,2)`, metadata **thường** báo precision `12`, scale `2`. Nhưng đừng áp dụng cách diễn giải đó cho mọi kiểu: `getPrecision`/`getScale` có quy ước phụ thuộc loại dữ liệu, driver và DBMS; một số thông tin có thể không xác định. `isNullable` cũng cho phép trạng thái **không rõ**, đặc biệt với cột biểu thức hay kết quả tính toán.

Nếu chương trình cần biết một giá trị **thực sự là `NULL`**, hãy đọc giá trị từ `ResultSet`: `Object value = rs.getObject(i); if (value == null) ...`. Metadata `isNullable` chỉ diễn tả tính chất **có thể** chứa `NULL` theo driver, không xác nhận hàng đang đọc có giá trị `NULL` hay không.

## 6. Dùng metadata để tạo bảng hoặc xuất dữ liệu động

Một ứng dụng xuất kết quả SQL tổng quát có thể xây danh sách cột từ metadata trước, rồi đọc hàng theo chỉ số:

```java
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

static List<String> columnHeaders(ResultSet rs) throws SQLException {
    ResultSetMetaData md = rs.getMetaData();
    List<String> headers = new ArrayList<>();
    for (int i = 1; i <= md.getColumnCount(); i++) {
        headers.add(md.getColumnLabel(i));
    }
    return headers;
}

static List<Object> readCurrentRow(ResultSet rs) throws SQLException {
    ResultSetMetaData md = rs.getMetaData();
    List<Object> values = new ArrayList<>();
    for (int i = 1; i <= md.getColumnCount(); i++) {
        values.add(rs.getObject(i));
    }
    return values;
}
```

`columnHeaders(rs)` có thể được gọi trước `rs.next()`; `readCurrentRow(rs)` chỉ được gọi sau khi `rs.next()` trả về `true`. Cả hai là **đoạn hàm tiện ích** có thể dùng bên trong lớp Java, giả định `ResultSet` còn mở. Danh sách giữ nguyên **thứ tự và số lượng cột**, kể cả khi hai cột có cùng nhãn; nếu dùng `Map` cần tự giải quyết nhãn trùng.

Đối với CSV hoặc bảng web, metadata chỉ giúp **xác định tiêu đề và kiểu**, chưa hoàn thành khâu xuất an toàn:

- CSV cần escape dấu phẩy, dấu quote, xuống dòng và quy định encoding. Nếu dữ liệu có thể bắt đầu bằng `=`, `+`, `-` hoặc `@`, cần chính sách phòng tránh **CSV formula injection** khi mở bằng ứng dụng bảng tính; phương pháp xử lý phụ thuộc định dạng xuất và phần mềm đích.
- Giao diện HTML phải escape giá trị và nhãn động trước khi hiển thị; nhãn cột không phải nội dung đã được làm sạch.
- Các kiểu `BLOB`, `CLOB`, `ARRAY`, kiểu đặc thù DBMS và thời gian có timezone cần serializer thích hợp; không giả định mọi `getObject` có `toString` thân thiện.
- Khi tập kết quả rất lớn, nên xử lý **từng hàng qua luồng**, giữ thời gian sử dụng kết nối hợp lý và không gom toàn bộ bản ghi vào `List` chỉ vì metadata đã có sẵn.

**Giới hạn về bảo mật:** Metadata không biến một câu SQL tùy ý thành an toàn. `PreparedStatement` tham số hóa **giá trị**, không tham số hóa tên bảng/cột hoặc đoạn SQL. Khi ứng dụng cho phép người dùng chọn trường hiển thị, phải chọn tên cột từ **danh sách cho phép**, không nối tên cột người dùng cung cấp trực tiếp vào `SELECT`.

## 7. Metadata vẫn có ích khi truy vấn trả về 0 hàng

Giả sử cần biết cấu trúc của một báo cáo trước khi lấy dữ liệu. Với câu SQL:

```sql
SELECT id AS product_id,
       name AS product_name,
       unit_price AS display_price
FROM products
WHERE 1 = 0;
```

Kết quả thông thường có **0 hàng** nhưng vẫn định nghĩa ba cột. Mã Java có thể đọc:

```java
try (PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    ResultSetMetaData md = rs.getMetaData();
    System.out.println(md.getColumnCount()); // 3
    for (int i = 1; i <= md.getColumnCount(); i++) {
        System.out.println(md.getColumnLabel(i));
    }
    System.out.println(rs.next()); // false: không có bản ghi
}
```

Trong ví dụ này, `connection` và `sql` đã được thiết lập ở phạm vi bên ngoài. Cách sử dụng một truy vấn trả 0 hàng có thể giúp xác minh **hình dạng kết quả**. Tuy nhiên, đây vẫn là truy vấn được thực thi: quyền truy cập bảng, cú pháp SQL và logic DBMS vẫn được kiểm tra; không nên cho chạy SQL do người dùng chưa được tin cậy cung cấp.

Trên một số driver, `PreparedStatement.getMetaData()` cũng có thể cung cấp metadata của kết quả **trước khi thực thi**, nhưng có thể trả `null` nếu driver không cung cấp được. Khi cần hành vi chắc chắn hơn và có thể thực thi truy vấn an toàn, lấy metadata từ `ResultSet` thực tế sau `executeQuery()` thường dễ kiểm soát.

## 8. Phân biệt ResultSetMetaData với hai loại metadata khác

JDBC có những API metadata dễ bị nhầm mục đích:

| API | Lấy từ đâu? | Mô tả điều gì? |
| --- | --- | --- |
| **`ResultSetMetaData`** | `ResultSet.getMetaData()` | Số cột, nhãn, kiểu và thuộc tính các **cột trong kết quả truy vấn**. |
| **`DatabaseMetaData`** | `Connection.getMetaData()` | Khả năng DBMS/driver và thông tin cấu trúc như bảng, cột, khóa, schema, giới hạn hỗ trợ. |
| **`ParameterMetaData`** | `PreparedStatement.getParameterMetaData()` | Thông tin về các **tham số `?`** nếu driver hỗ trợ cung cấp. |

Ví dụ: muốn in tiêu đề của câu `SELECT a.id AS customer_id` thì dùng `ResultSetMetaData.getColumnLabel(1)`. Muốn tìm các cột hiện có trong bảng `customers`, có thể dùng `DatabaseMetaData.getColumns(...)`. Muốn hỏi số tham số `?` của một `PreparedStatement`, dùng `ParameterMetaData.getParameterCount()` nếu hỗ trợ. Không dùng `getColumnCount()` để đo số tham số của truy vấn.

**Nhãn của kết quả không phải cấu trúc bảng gốc:** một câu `SELECT` có thể chứa `JOIN`, biểu thức, `COUNT(*)`, `CAST`, phép tính và bí danh. `ResultSetMetaData` mô tả **sản phẩm của truy vấn**, không thể dùng thay thế hoàn toàn cho `DatabaseMetaData` khi xây công cụ migration hoặc kiểm kê schema.

## 9. Giới hạn driver/DBMS và xử lý lỗi

Một số kết quả metadata phụ thuộc mạnh vào driver:

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| `getColumnLabel` đúng alias nhưng `getColumnName` không phải tên cột gốc mong đợi. | Truy vấn có biểu thức/`JOIN` hoặc driver ánh xạ alias khác nhau. | Dùng label cho trình bày; kiểm thử thuộc tính cột gốc trên driver cụ thể nếu thật sự cần. |
| `getColumnTypeName` trả tên khác kiểu viết trong DDL. | DBMS chuẩn hóa/đặt tên loại dữ liệu khác hoặc kiểu vendor-specific. | Dùng `getColumnType` để phân nhánh theo chuẩn khi phù hợp, dùng tên kiểu để chẩn đoán. |
| `getColumnClassName` trả lớp khác kiểu Java muốn dùng. | Driver chọn ánh xạ `getObject` mặc định khác hoặc hỗ trợ loại SQL đặc thù. | Sử dụng getter có kiểu rõ ràng, kiểm tra driver; không ép kiểu tùy tiện. |
| `getTableName`/`getSchemaName` trả chuỗi rỗng. | Cột là biểu thức, nguồn không xác định hoặc driver không có thông tin. | Chấp nhận metadata không đủ; dùng `DatabaseMetaData` khi cần schema của bảng. |
| `isNullable` trả `columnNullableUnknown`. | Driver không xác định được tính nullable của kết quả. | Không suy ra cột chắc chắn `NOT NULL`; xử lý `NULL` khi đọc hàng. |
| `SQLException` hoặc `SQLFeatureNotSupportedException` khi gọi metadata. | Tính năng không được hỗ trợ hoặc kết nối/statement lỗi. | Ghi nhận `SQLState`/mã lỗi, kiểm tra phiên bản driver và cách khai thác metadata. |
| Kết quả thay đổi sau khi nâng cấp DBMS/driver. | Cơ chế ánh xạ tên/kiểu hoặc schema đã thay đổi. | Kiểm tra hợp đồng cột trong bài integration test trên đúng hệ triển khai. |

Trong mã ứng dụng, nên bắt `SQLException` tại ranh giới truy cập dữ liệu, bảo toàn nguyên nhân và dùng `getSQLState()`/`getErrorCode()` khi phân loại. Không bỏ qua lỗi metadata rồi im lặng xuất dữ liệu theo sai cột. Việc đóng `ResultSet` hoặc `Connection` quá sớm cũng khiến thao tác metadata sau đó có thể thất bại; nên thu thập cấu trúc cần dùng khi tài nguyên còn mở.

### Kiểm tra hợp đồng cột khi ứng dụng cần schema ổn định

Metadata có thể giúp phát hiện sớm việc ai đó sửa alias hoặc kiểu dữ liệu của câu SQL:

```java
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Types;

static void assertExpectedColumns(ResultSetMetaData md)
        throws SQLException {
    if (md.getColumnCount() != 3
            || !"product_id".equals(md.getColumnLabel(1))
            || !"product_name".equals(md.getColumnLabel(2))
            || !"display_price".equals(md.getColumnLabel(3))) {
        throw new SQLException("Hình dạng kết quả truy vấn đã thay đổi");
    }

    int type = md.getColumnType(3);
    if (type != Types.DECIMAL && type != Types.NUMERIC) {
        throw new SQLException("display_price không phải kiểu thập phân");
    }
}
```

Ví dụ trên dành cho **truy vấn sản phẩm đã quy ước ba bí danh cụ thể**, không phải bộ quy tắc phổ quát. Ứng dụng phải chủ động quyết định có chấp nhận các kiểu tương đương khác của DBMS hay không. Nếu hệ thống dùng nhiều DBMS, nên có integration test cho từng driver để xác nhận nhãn và kiểu trả về đúng như hợp đồng ứng dụng.

## 10. Bài tập thực hành

Giả sử dịch vụ JDBC thực thi:

```sql
SELECT c.id AS customer_id,
       c.full_name AS customer_name,
       COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.active = ?
GROUP BY c.id, c.full_name;
```

Hãy tự giải đáp:

1. `getColumnCount()` trả mấy cột? Chỉ số cột hợp lệ trong vòng lặp metadata là những số nào?
2. `getColumnLabel(2)` nên trả nhãn gì? Tại sao không nên dùng `getColumnName(2)` để quyết định tiêu đề UI trong mọi driver?
3. Kiểu của `order_count` được xác định bằng phương thức nào? Có thể mặc định nó luôn là `Types.INTEGER` và `Integer.class` không?
4. Nếu câu truy vấn không trả hàng nào, bạn có thể đọc số cột, nhãn và kiểu bằng `ResultSetMetaData` không?
5. Nếu hai cột đều có nhãn `id`, rủi ro gì xảy ra khi xuất thẳng vào `Map<String, Object>`? Bạn sẽ sửa SQL hoặc cấu trúc dữ liệu đầu ra như thế nào?

**Đáp án định hướng:** (1) Có `3` cột, chỉ số `1`, `2`, `3`. (2) `customer_name` theo bí danh `AS`; tên cột gốc/biểu thức không phải hợp đồng tiêu đề giữa mọi driver. (3) Dùng `getColumnType(3)` và `getColumnTypeName(3)`; `COUNT` thường là kiểu số nguyên lớn tùy DBMS và driver, không nên ép mặc định về `Integer`. (4) Có, metadata mô tả cấu trúc kết quả dù `rs.next()` trả `false`. (5) Key trùng có thể ghi đè; dùng alias khác nhau hoặc giữ cột theo chỉ số.

**Ghi nhớ:** `ResultSetMetaData.getColumnLabel(i)` trả **nhãn cột phục vụ hiển thị**, thường dựa trên `AS`; `getColumnType(i)` trả **mã JDBC `java.sql.Types`**, còn `getColumnTypeName(i)` trả **tên kiểu SQL do driver báo**. Luôn duyệt cột từ `1` đến `getColumnCount()`, phân biệt metadata với giá trị đọc qua `ResultSet`, và kiểm thử các khác biệt của driver khi ứng dụng phụ thuộc vào nhãn/kiểu cụ thể.
