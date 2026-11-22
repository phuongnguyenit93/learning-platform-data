# Đọc thông tin kiểu dữ liệu và giới hạn được công bố trong JDBC

Trong chương **Siêu dữ liệu**, ứng dụng JDBC không chỉ cần đọc dữ liệu của bảng mà còn cần biết **cơ sở dữ liệu nhận những kiểu SQL nào, cột đang có kiểu gì và hệ quản trị công bố các giới hạn nào**. Những thông tin này hữu ích khi xây công cụ quản trị, nhập dữ liệu động, kiểm tra lược đồ, sinh biểu mẫu, viết trình kiểm thử tương thích nhiều DBMS hoặc đánh giá khả năng của một driver.

JDBC cung cấp các API chuẩn để Java truy cập cơ sở dữ liệu quan hệ qua driver và `DataSource`. Ngoài `PreparedStatement`, `ResultSet` và các thao tác CRUD, hai nhóm metadata đặc biệt quan trọng là:

- **`DatabaseMetaData`**: mô tả khả năng, các kiểu dữ liệu SQL, cấu trúc bảng/cột và giới hạn do DBMS/driver công bố.
- **`ResultSetMetaData`**: mô tả các cột của **một kết quả truy vấn cụ thể**, kể cả nhãn cột và kiểu của biểu thức trong `SELECT`.

Bài học tập trung vào cách đọc và **diễn giải đúng** những thông tin đó. Metadata là thông tin mà driver/DBMS cung cấp tại thời điểm truy vấn; nó **không phải cam kết tuyệt đối** rằng mọi cấu hình, bảng, quyền truy cập hoặc truy vấn đều có đúng cùng giới hạn.

## 1. Chọn đúng nguồn metadata

Một câu hỏi có thể cần một API khác nhau:

| Bạn muốn biết | API phù hợp | Ví dụ |
| --- | --- | --- |
| DBMS/driver công bố những kiểu SQL nào? | `DatabaseMetaData.getTypeInfo()` | Có kiểu tên `DECIMAL`, `VARCHAR`, mã JDBC tương ứng không? |
| Cột thực tế trong bảng có kiểu, độ dài và nullable ra sao? | `DatabaseMetaData.getColumns(...)` | `catalog_items.title` là `VARCHAR(120) NOT NULL`? |
| Các cột kết quả của một câu `SELECT` có kiểu và nhãn gì? | `ResultSet.getMetaData()` | `SELECT price * quantity AS total` trả cột nhãn `total` với kiểu gì? |
| DBMS/driver công bố độ dài tên bảng hoặc giới hạn số cột thế nào? | Các phương thức `DatabaseMetaData.getMax...()` | Số cột tối đa trong bảng là bao nhiêu? |
| DBMS hỗ trợ tính năng nhất định không? | Các phương thức `supports...()` | Có hỗ trợ transaction, batch, savepoint không? |
| Driver mô tả tham số `?` của câu SQL ra sao? | `PreparedStatement.getParameterMetaData()` | Tham số thứ nhất có kiểu JDBC nào? |

**Không nên thay thế các nguồn cho nhau.** `getTypeInfo()` liệt kê **loại SQL mà hệ thống tuyên bố hỗ trợ**, nhưng không nói cột `title` đang khai báo bao nhiêu ký tự. `getColumns()` mô tả **cột bảng**, nhưng không mô tả chính xác kiểu của biểu thức tính toán `price * quantity` trong kết quả một câu `SELECT`. Với biểu thức truy vấn, dùng `ResultSetMetaData`.

`ParameterMetaData` là API bổ trợ, nhưng mức độ hỗ trợ và độ chính xác của thông tin tham số `?` phụ thuộc driver và cú pháp truy vấn; không nên dùng nó làm nguồn duy nhất để kiểm tra dữ liệu đầu vào.

## 2. Lấy `DatabaseMetaData` từ một `Connection`

Mẫu mở đầu:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class MetadataIntro {
    public static void inspect(DataSource dataSource) throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            DatabaseMetaData meta = conn.getMetaData();

            System.out.println("DBMS: " + meta.getDatabaseProductName());
            System.out.println("DBMS version: " + meta.getDatabaseProductVersion());
            System.out.println("Driver: " + meta.getDriverName());
            System.out.println("Driver version: " + meta.getDriverVersion());

            System.out.println("Supports transactions: "
                + meta.supportsTransactions());
            System.out.println("Supports batch updates: "
                + meta.supportsBatchUpdates());
        }
    }
}
~~~

`Connection.getMetaData()` trả về metadata gắn với **kết nối hiện tại**. Một số thuộc tính phản ánh cả môi trường server, driver và cấu hình kết nối; vì thế hai phiên bản driver hoặc hai máy chủ có thể cung cấp kết quả khác nhau.

Dùng `try-with-resources` để đóng/trả kết nối đúng lúc. Các phương thức metadata có thể truy vấn hệ thống catalog và phát sinh I/O, vì vậy không nên gọi hàng nghìn lần cho mỗi bản ghi. Với các công cụ khám phá lược đồ, có thể cache metadata theo **đúng DBMS, schema, phiên bản và thời điểm cần làm mới**, đồng thời làm mất hiệu lực cache khi cấu trúc bảng thay đổi.

> Nhiều lời gọi metadata chỉ đọc thông tin và không cần transaction cập nhật dữ liệu. Tuy nhiên, việc quan sát catalog vẫn phụ thuộc quyền truy cập, độ nhất quán của DBMS và hành vi driver. Không cần vô hiệu auto-commit chỉ để chạy một vài lời gọi metadata.

## 3. Đọc danh sách kiểu dữ liệu qua `getTypeInfo()`

`DatabaseMetaData.getTypeInfo()` trả một `ResultSet`. Mỗi hàng mô tả **một kiểu SQL** mà driver/DBMS công bố. Những cột thường dùng gồm:

| Tên trường trong `ResultSet` | Ý nghĩa |
| --- | --- |
| `TYPE_NAME` | Tên kiểu SQL do DBMS/driver công bố, ví dụ `VARCHAR`, `DECIMAL`, `TIMESTAMP` |
| `DATA_TYPE` | Mã kiểu JDBC, thường là hằng từ `java.sql.Types` |
| `PRECISION` | Độ chính xác tối đa hoặc quy mô kiểu do driver công bố; cách hiểu cụ thể tùy họ kiểu |
| `LITERAL_PREFIX`, `LITERAL_SUFFIX` | Ký tự bao quanh literal SQL nếu có, chẳng hạn dấu nháy |
| `CREATE_PARAMS` | Các tham số được khai báo khi tạo kiểu, ví dụ `length` hoặc `precision,scale` |
| `NULLABLE` | Kiểu có cho phép `NULL` theo metadata không |
| `CASE_SENSITIVE` | Kiểu có phân biệt chữ hoa/thường khi so sánh không |
| `SEARCHABLE` | Mức hỗ trợ sử dụng kiểu trong điều kiện tìm kiếm |
| `UNSIGNED_ATTRIBUTE` | Có phải kiểu không dấu hay không; giá trị có thể chưa xác định |
| `FIXED_PREC_SCALE` | Kiểu có số chữ số thập phân cố định, theo định nghĩa metadata |
| `AUTO_INCREMENT` | Kiểu có thể dùng cho cột tự tăng hay không |
| `MINIMUM_SCALE`, `MAXIMUM_SCALE` | Khoảng scale được công bố cho kiểu |
| `NUM_PREC_RADIX` | Cơ số của giá trị precision, thường gặp 10 hoặc 2 |

### Ví dụ in các kiểu dữ liệu được công bố

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

static void listSupportedTypes(Connection conn) throws SQLException {
    DatabaseMetaData meta = conn.getMetaData();

    try (ResultSet rs = meta.getTypeInfo()) {
        while (rs.next()) {
            String typeName = rs.getString("TYPE_NAME");
            int jdbcType = rs.getInt("DATA_TYPE");
            String createParams = rs.getString("CREATE_PARAMS");

            int precision = rs.getInt("PRECISION");
            String precisionText = rs.wasNull()
                ? "không công bố" : Integer.toString(precision);

            int nullableFlag = rs.getInt("NULLABLE");
            String nullable = switch (nullableFlag) {
                case DatabaseMetaData.typeNoNulls -> "NO";
                case DatabaseMetaData.typeNullable -> "YES";
                default -> "UNKNOWN";
            };

            System.out.printf(
                "%s | JDBC=%d | precision=%s | params=%s | nullable=%s%n",
                typeName, jdbcType, precisionText,
                createParams, nullable
            );
        }
    }
}
~~~

`ResultSet` trả về từ metadata cũng là một tài nguyên JDBC cần đóng. Các tên trường như `TYPE_NAME` và `DATA_TYPE` là tên cột được chuẩn hóa cho kết quả của `getTypeInfo()`, **không phải tên cột trong bảng nghiệp vụ**.

### Các giá trị có thể là SQL `NULL`

Một số trường metadata không có giá trị cụ thể. Với `ResultSet.getInt(...)`, SQL `NULL` được chuyển thành `0`, nên cần gọi `wasNull()` ngay sau khi đọc giá trị để phân biệt. Với `getBoolean(...)`, SQL `NULL` có thể được trả về như `false` và cũng phải kiểm tra `wasNull()`.

Ví dụ:

~~~java
boolean unsigned = rs.getBoolean("UNSIGNED_ATTRIBUTE");
String unsignedText = rs.wasNull()
    ? "UNKNOWN"
    : Boolean.toString(unsigned);
~~~

Đừng hiển thị `UNKNOWN` thành `NO`: “không có thông tin” không tương đương “chắc chắn không hỗ trợ”.

### `getTypeInfo()` không phải câu lệnh tạo bảng

Ví dụ metadata cho thấy có `DECIMAL` với `CREATE_PARAMS = "precision,scale"`. Điều đó gợi ý có thể khai báo kiểu như:

~~~sql
unit_price DECIMAL(12, 2)
~~~

Tuy nhiên:

- `TYPE_NAME` có thể là **tên riêng của DBMS**, kiểu đồng nghĩa hoặc kiểu có hành vi đặc biệt.
- Việc driver công bố một kiểu **không xác nhận** mọi biến thể `CREATE TABLE` đều hợp lệ với mọi precision/scale.
- Mỗi DBMS có thể hỗ trợ các giới hạn giá trị, scale, collation, unsigned hoặc auto-increment khác nhau.
- Kiểu dữ liệu có thể chỉ khả dụng ở một phiên bản hoặc khi bật extension/tính năng cụ thể.

Khi sinh DDL, hãy xác minh quy tắc của DBMS đích, không ghép tên kiểu bất kỳ do người dùng cung cấp vào SQL.

## 4. Đọc kiểu và thuộc tính của cột thật bằng `getColumns()`

Cho bảng minh họa:

~~~sql
CREATE TABLE catalog_items (
    id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    note VARCHAR(500)
);
~~~

Tùy DBMS, `getColumns(...)` có thể trả metadata với những giá trị tương đương:

| Cột | Kiểu SQL khai báo | `COLUMN_SIZE` dự kiến | `DECIMAL_DIGITS` | Nullable |
| --- | --- | ---: | ---: | --- |
| `id` | `BIGINT` | Phụ thuộc cách driver mô tả precision | Thường 0 | NO |
| `title` | `VARCHAR(120)` | 120 ký tự | Thường không áp dụng | NO |
| `unit_price` | `DECIMAL(12,2)` | 12 chữ số precision | 2 chữ số scale | NO |
| `note` | `VARCHAR(500)` | 500 ký tự | Thường không áp dụng | YES |

Bảng minh họa ý nghĩa các trường; **không khẳng định driver nào cũng xuất ra cùng giá trị**, đặc biệt đối với giá trị không áp dụng/không biết, kiểu số và kiểu đặc thù DBMS.

### Các tham số của `getColumns()`

~~~java
ResultSet columns = meta.getColumns(
    catalog,           // catalog, null nghĩa là không lọc
    schemaPattern,     // mẫu schema
    tableNamePattern,  // mẫu tên bảng
    columnNamePattern  // mẫu tên cột
);
~~~

`schemaPattern`, `tableNamePattern`, `columnNamePattern` là **search patterns**, không đơn thuần là chuỗi tên chính xác. Thông thường:

- `%` đại diện cho nhiều ký tự.
- `_` đại diện cho một ký tự.
- Dùng `DatabaseMetaData.getSearchStringEscape()` để escape hai wildcard khi chúng là **một phần của tên thật**.
- Catalog/schema và quy tắc chuyển chữ hoa/thường của identifier khác nhau theo DBMS.
- Giá trị `null` cho tham số lọc phù hợp nghĩa “không dùng tiêu chí này để thu hẹp kết quả” theo hợp đồng JDBC.

Nếu bảng tên `order_items`, truyền trực tiếp chuỗi này làm pattern có thể khớp cả tên khác vì dấu gạch dưới `_` là wildcard. Nên escape nó hoặc xác minh chính xác `TABLE_NAME` trong dữ liệu trả về.

### Trường metadata của cột cần biết

| Tên trường | Ý nghĩa |
| --- | --- |
| `TABLE_CAT`, `TABLE_SCHEM`, `TABLE_NAME`, `COLUMN_NAME` | Định danh bảng/cột |
| `DATA_TYPE` | Kiểu JDBC dưới dạng mã số `java.sql.Types` |
| `TYPE_NAME` | Tên kiểu SQL của DBMS |
| `COLUMN_SIZE` | Độ dài/precision theo họ kiểu; thường số ký tự cho kiểu chuỗi, precision cho kiểu số |
| `DECIMAL_DIGITS` | Số chữ số phần thập phân hoặc scale đối với kiểu thích hợp |
| `NUM_PREC_RADIX` | Cơ số precision đối với kiểu số |
| `NULLABLE`, `IS_NULLABLE` | Khả năng nhận `NULL`: dạng mã số và dạng chuỗi |
| `COLUMN_DEF` | Giá trị mặc định nếu được công bố; SQL `NULL` có thể mang nghĩa không có thông tin |
| `CHAR_OCTET_LENGTH` | Độ dài tối đa theo **byte** cho kiểu ký tự, khi có thông tin |
| `ORDINAL_POSITION` | Vị trí cột trong bảng, bắt đầu từ 1 |
| `IS_AUTOINCREMENT` | Có phải cột tự tăng theo metadata; có thể là `YES`, `NO` hoặc chưa rõ |
| `IS_GENERATEDCOLUMN` | Có phải cột tính toán/sinh theo metadata; có thể chưa rõ |
| `REMARKS` | Mô tả/comment nếu driver công bố |

**Không nhầm `COLUMN_SIZE` và `CHAR_OCTET_LENGTH`.** Với chuỗi Unicode, số ký tự tối đa và số byte lưu trữ tối đa có thể khác. `VARCHAR(120)` không phải cam kết rằng mọi chuỗi Unicode chỉ cần tối đa 120 byte. Khi kiểm tra giới hạn lưu trữ hoặc truyền dữ liệu, cần kết hợp encoding, collation, kiểu cột và quy tắc DBMS.

Với `DECIMAL(12,2)`, precision 12 nghĩa là tổng số chữ số có nghĩa, scale 2 liên quan số chữ số phần thập phân; **không** có nghĩa được lưu 12 byte. Các họ kiểu thời gian, nhị phân hoặc LOB cần diễn giải `COLUMN_SIZE` theo quy tắc của driver/DBMS.

### Ví dụ Java đọc cột bảng

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

static void inspectTable(
        Connection conn, String schema, String table
) throws SQLException {
    DatabaseMetaData meta = conn.getMetaData();

    // Escape wildcard khi tên schema/table có % hoặc _.
    String escape = meta.getSearchStringEscape();
    String schemaPattern = schema == null
        ? null : asLiteralPattern(schema, escape);
    String tablePattern = asLiteralPattern(table, escape);

    try (ResultSet rs = meta.getColumns(
            null, schemaPattern, tablePattern, "%")) {

        while (rs.next()) {
            String actualTable = rs.getString("TABLE_NAME");
            if (!table.equalsIgnoreCase(actualTable)) {
                // Phòng trường hợp driver không escape pattern như mong đợi.
                continue;
            }

            String column = rs.getString("COLUMN_NAME");
            int jdbcType = rs.getInt("DATA_TYPE");
            String sqlType = rs.getString("TYPE_NAME");

            int sizeValue = rs.getInt("COLUMN_SIZE");
            String size = rs.wasNull()
                ? "UNKNOWN" : Integer.toString(sizeValue);

            int scaleValue = rs.getInt("DECIMAL_DIGITS");
            String scale = rs.wasNull()
                ? "N/A" : Integer.toString(scaleValue);

            int nullable = rs.getInt("NULLABLE");
            String nullableText = switch (nullable) {
                case DatabaseMetaData.columnNoNulls -> "NO";
                case DatabaseMetaData.columnNullable -> "YES";
                default -> "UNKNOWN";
            };

            System.out.printf(
                "%s | JDBC=%d | SQL=%s | size=%s | scale=%s | nullable=%s%n",
                column, jdbcType, sqlType, size, scale, nullableText
            );
        }
    }
}

static String asLiteralPattern(String identifier, String escape) {
    if (identifier == null) {
        throw new IllegalArgumentException("Tên không được null");
    }
    if (escape == null || escape.isEmpty()) {
        // Nếu driver không công bố escape, cần kiểm tra
        // kết quả bằng định danh thực tế sau khi tra metadata.
        return identifier;
    }
    return identifier
        .replace(escape, escape + escape)
        .replace("%", escape + "%")
        .replace("_", escape + "_");
}
~~~

Ví dụ sử dụng:

~~~java
try (Connection conn = dataSource.getConnection()) {
    inspectTable(conn, "public", "catalog_items");
}
~~~

`public` là ví dụ về schema trong PostgreSQL; **không** phải tên schema mặc định của mọi DBMS. Nếu DBMS không sử dụng schema theo cách này, truyền `null` hoặc lựa chọn catalog/schema thích hợp.

Trong thực tế, cần lưu ý thêm:

1. Nếu driver trả tên identifier đã được chuẩn hóa chữ hoa/chữ thường, việc tìm metadata có thể cần tên **đúng như trong catalog**; có thể dùng `storesUpperCaseIdentifiers()`, `storesLowerCaseIdentifiers()` hoặc kiểm tra `getTables(...)` khi thiết kế công cụ tương thích.
2. `equalsIgnoreCase` ở trên chỉ nhằm minh họa việc tránh khớp bảng sai do wildcard; nó **không phải bộ so sánh identifier chuẩn cho mọi DBMS**, nhất là tên được đặt trong dấu nháy phân biệt hoa/thường. Công cụ thực tế nên thực hiện so sánh theo quy tắc định danh của DBMS.
3. Quyền truy cập có thể giới hạn những schema hoặc bảng được nhìn thấy; một kết quả rỗng **không luôn chứng minh bảng không tồn tại**.
4. Metadata có thể bị thay đổi bởi migration đang chạy; đừng giả định lược đồ không đổi xuyên suốt thời gian cache dài.

## 5. `java.sql.Types` và tên kiểu SQL của DBMS

Trường `DATA_TYPE` thường chứa **mã JDBC**, ví dụ:

| Kiểu logic | Mã JDBC tiêu biểu | Lưu ý |
| --- | --- | --- |
| Chuỗi ngắn | `Types.VARCHAR`, `Types.NVARCHAR` | Encoding/collation và giới hạn cụ thể tùy DBMS |
| Số nguyên | `Types.INTEGER`, `Types.BIGINT` | Miền giá trị và khả năng unsigned có thể khác |
| Số thập phân | `Types.DECIMAL`, `Types.NUMERIC` | Chú ý precision/scale |
| Nhị phân | `Types.VARBINARY`, `Types.BLOB` | Giới hạn byte và cơ chế streaming |
| Ngày | `Types.DATE` | Thường tương ứng phần ngày, không đồng nghĩa timestamp |
| Thời gian | `Types.TIME`, `Types.TIME_WITH_TIMEZONE` | Hỗ trợ kiểu có múi giờ phụ thuộc DBMS/driver |
| Mốc thời gian | `Types.TIMESTAMP`, `Types.TIMESTAMP_WITH_TIMEZONE` | Cần chọn API Java time đúng ngữ nghĩa |
| Boolean | `Types.BOOLEAN`, `Types.BIT` | Một số DBMS ánh xạ qua kiểu khác |
| Kiểu mở rộng | `Types.OTHER` | Thường phải đọc thêm `TYPE_NAME` và tài liệu driver |

Có thể chuyển mã sang tên để log hoặc quyết định cách ràng buộc giá trị:

~~~java
import java.sql.Types;

static String jdbcTypeName(int type) {
    return switch (type) {
        case Types.VARCHAR -> "VARCHAR";
        case Types.NVARCHAR -> "NVARCHAR";
        case Types.INTEGER -> "INTEGER";
        case Types.BIGINT -> "BIGINT";
        case Types.DECIMAL -> "DECIMAL";
        case Types.NUMERIC -> "NUMERIC";
        case Types.DATE -> "DATE";
        case Types.TIMESTAMP -> "TIMESTAMP";
        case Types.TIMESTAMP_WITH_TIMEZONE -> "TIMESTAMP_WITH_TIMEZONE";
        case Types.OTHER -> "OTHER / DBMS-specific";
        default -> "JDBC type code " + type;
    };
}
~~~

**`DATA_TYPE` không chứa độ dài khai báo.** Hai cột `VARCHAR(50)` và `VARCHAR(500)` có thể cùng mã `Types.VARCHAR`; để phân biệt, phải đọc `COLUMN_SIZE` từ metadata cột.

**`TYPE_NAME` không phải kiểu Java.** Một tên kiểu SQL có thể ánh xạ tới nhiều kiểu đối tượng Java tùy driver, cấu hình và phương thức lấy dữ liệu. Với dữ liệu thời gian, ví dụ có thể dùng `ResultSet.getObject(index, LocalDate.class)` hoặc `LocalDateTime.class` khi driver hỗ trợ; cần kiểm tra kiểu SQL thực tế và ngữ nghĩa múi giờ trước khi chọn.

## 6. Đọc metadata của kết quả truy vấn bằng `ResultSetMetaData`

`DatabaseMetaData.getColumns(...)` mô tả cấu trúc bảng, còn `ResultSetMetaData` mô tả **các cột mà câu SELECT thực sự trả về**. Nó hữu ích khi:

- Viết trình hiển thị bảng kết quả động.
- Xử lý câu SQL có alias, join hoặc biểu thức tính toán.
- Sinh schema cho định dạng xuất dữ liệu.
- Kiểm tra kiểu cột trước khi gọi `ResultSet.getObject(...)`.

Ví dụ với bảng `catalog_items` ở trên:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

static void inspectQuery(Connection conn) throws SQLException {
    String sql = """
        SELECT id, title AS item_name,
               unit_price, unit_price * 2 AS double_price
        FROM catalog_items
        WHERE id = ?
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, -1L);

        try (ResultSet rs = ps.executeQuery()) {
            ResultSetMetaData columns = rs.getMetaData();

            for (int i = 1; i <= columns.getColumnCount(); i++) {
                System.out.printf(
                    "%d | label=%s | name=%s | JDBC=%d | SQL=%s"
                    + " | precision=%d | scale=%d | Java=%s%n",
                    i,
                    columns.getColumnLabel(i),
                    columns.getColumnName(i),
                    columns.getColumnType(i),
                    columns.getColumnTypeName(i),
                    columns.getPrecision(i),
                    columns.getScale(i),
                    columns.getColumnClassName(i)
                );
            }
        }
    }
}
~~~

Ở ví dụ trên, `id = -1` có thể không khớp bản ghi nào, nhưng metadata vẫn mô tả **các cột của kết quả truy vấn**, không đòi phải đọc được một hàng dữ liệu thật.

Một số điểm cần nhớ:

- **Chỉ số cột của `ResultSetMetaData` bắt đầu từ 1**, không bắt đầu từ 0.
- `getColumnLabel(i)` là nhãn hiển thị, thường phản ánh alias như `item_name` hoặc `double_price`. `getColumnName(i)` là tên cột theo metadata; với biểu thức, cách trả về có thể phụ thuộc driver.
- `getColumnType(i)` trả mã kiểu JDBC, còn `getColumnTypeName(i)` trả tên kiểu SQL mà driver công bố.
- `getPrecision(i)` và `getScale(i)` phải được diễn giải theo loại dữ liệu; không có nghĩa giống nhau với mọi kiểu.
- `getColumnClassName(i)` là tên lớp Java được dùng khi giá trị được lấy qua `getObject(i)` theo cách ánh xạ của driver; **không đảm bảo** cùng kiểu với một lời gọi `getObject(i, SomeClass.class)` cụ thể.
- `isNullable(i)` trả `columnNoNulls`, `columnNullable` hoặc `columnNullableUnknown`. Với biểu thức tính toán, JDBC có thể không xác định được chắc chắn khả năng `NULL`.

Nếu một trình xuất dữ liệu dùng `getColumnLabel(i)` làm tên cột trong JSON/CSV, cần xử lý các alias trùng nhau và định dạng nhất quán; không giả định nhãn là duy nhất.

## 7. Đọc các giới hạn qua `DatabaseMetaData.getMax...()`

Ngoài kiểu dữ liệu, `DatabaseMetaData` còn có nhiều phương thức cung cấp **giới hạn do DBMS/driver công bố**.

| API | Thông tin được công bố | Ứng dụng thường dùng để |
| --- | --- | --- |
| `getMaxColumnNameLength()` | Độ dài tối đa tên cột | Cảnh báo khi sinh tên cột từ schema |
| `getMaxTableNameLength()` | Độ dài tối đa tên bảng | Kiểm tra tên được tạo tự động |
| `getMaxColumnsInTable()` | Số cột tối đa trong một bảng | Kiểm tra giới hạn công cụ sinh bảng |
| `getMaxColumnsInSelect()` | Số cột tối đa trong danh sách SELECT | Tối ưu bộ dựng truy vấn |
| `getMaxColumnsInIndex()` | Số cột tối đa trong chỉ mục | Kiểm tra thiết kế chỉ mục nhiều cột |
| `getMaxTablesInSelect()` | Số bảng tối đa có thể tham gia SELECT | Cảnh báo truy vấn join rất lớn |
| `getMaxStatementLength()` | Độ dài tối đa câu SQL, thường tính theo ký tự theo hợp đồng JDBC | Đánh giá việc tạo SQL động quá dài |
| `getMaxCharLiteralLength()` | Độ dài tối đa literal ký tự | Tránh sinh literal quá dài trong SQL |
| `getMaxBinaryLiteralLength()` | Độ dài tối đa literal nhị phân | Cảnh báo việc nhúng nhị phân trực tiếp vào SQL |
| `getMaxRowSize()` | Kích thước hàng tối đa do DBMS công bố, tính bằng byte | Đánh giá thiết kế hàng rộng |
| `doesMaxRowSizeIncludeBlobs()` | Quy tắc tính BLOB trong kích thước hàng được báo | Diễn giải `getMaxRowSize()` |
| `getMaxConnections()` | Số kết nối hoạt động tối đa theo thông tin công bố | Lập kế hoạch sơ bộ về tài nguyên |
| `getMaxStatements()` | Số statement có thể mở đồng thời theo thông tin công bố | Quan sát giới hạn tài nguyên statement |

### Ví dụ đọc và trình bày giới hạn

~~~java
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

static void printLimits(DatabaseMetaData meta) throws SQLException {
    printLimit("Tên cột", meta.getMaxColumnNameLength());
    printLimit("Tên bảng", meta.getMaxTableNameLength());
    printLimit("Cột trong bảng", meta.getMaxColumnsInTable());
    printLimit("Cột trong SELECT", meta.getMaxColumnsInSelect());
    printLimit("Bảng trong SELECT", meta.getMaxTablesInSelect());
    printLimit("Độ dài câu SQL", meta.getMaxStatementLength());
    printLimit("Kết nối", meta.getMaxConnections());
    printLimit("Statement mở", meta.getMaxStatements());
    printLimit("Kích thước hàng (byte)", meta.getMaxRowSize());

    System.out.println(
        "Max row size includes BLOBs: "
        + meta.doesMaxRowSizeIncludeBlobs()
    );
}

static void printLimit(String label, int value) {
    // Theo hợp đồng của nhiều API getMax...:
    // 0 nghĩa là không có giới hạn hoặc chưa xác định.
    String text = value == 0
        ? "không giới hạn hoặc không rõ"
        : Integer.toString(value);
    System.out.printf("%s: %s%n", label, text);
}
~~~

### Vì sao `0` không có nghĩa giới hạn bằng 0?

Với nhiều phương thức `getMax...()` của `DatabaseMetaData`, giá trị **0** nghĩa là **không có giới hạn được công bố hoặc giới hạn chưa xác định**. Vì vậy:

~~~text
getMaxColumnsInTable() = 0

SAI:  "Không được tạo bất kỳ cột nào."
ĐÚNG: "Metadata không đưa ra một giới hạn dương cụ thể;
       có thể không giới hạn hoặc không biết."
~~~

Đừng dùng điều kiện như `if (columnCount > maxColumns)` khi `maxColumns == 0`; nó có thể từ chối mọi trường hợp hợp lệ. Hãy xử lý 0 như **không đủ thông tin để áp đặt ngưỡng**.

Khi metadata trả giá trị dương, nó cũng không đảm bảo một bảng sát ngưỡng chắc chắn tạo được: có thể còn ràng buộc bởi kiểu cột, kích thước dữ liệu, encoding, row format, index, cấu hình máy chủ, quyền truy cập hoặc giới hạn tài nguyên.

### Đơn vị đo và ngữ nghĩa rất quan trọng

- Độ dài **identifier** không luôn được DBMS đo giống độ dài chuỗi hiển thị; Unicode hoặc cách xử lý ký tự đặc biệt có thể khác.
- `getMaxRowSize()` tính theo byte trong hợp đồng JDBC, nhưng cần xem quy tắc đối với BLOB/LOB và cách lưu trữ của DBMS.
- `getMaxStatementLength()` là thông tin giới hạn cho câu SQL được công bố, **không phải** một công thức xác định kích thước batch tối ưu.
- `getMaxConnections()` không phải số connection hiện còn trống trong pool, cũng không bảo đảm ứng dụng được mở tới mức đó trong cấu hình server hiện tại.
- `getMaxStatements()` không có nghĩa số `PreparedStatement` được cache tự động hoặc số truy vấn trong một transaction.
- `getMaxCharLiteralLength()` mô tả literal **nhúng trong SQL**; với `PreparedStatement`, giá trị truyền qua tham số có thể có giới hạn truyền và kiểu SQL riêng.

Nên dùng metadata giới hạn như **tín hiệu lập kế hoạch hoặc cảnh báo**, sau đó xác minh với tài liệu, cấu hình thực tế và kiểm thử có kiểm soát của DBMS đích.

## 8. Hỏi khả năng hỗ trợ có thể quan trọng hơn giới hạn số

Nếu ứng dụng cần dùng transaction, batch hoặc savepoint, trước hết kiểm tra khả năng hỗ trợ:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

static void printCapabilities(Connection conn) throws SQLException {
    DatabaseMetaData meta = conn.getMetaData();

    System.out.println("Transactions: "
        + meta.supportsTransactions());

    System.out.println("Batch updates: "
        + meta.supportsBatchUpdates());

    System.out.println("Savepoints: "
        + meta.supportsSavepoints());

    System.out.println("Serializable: "
        + meta.supportsTransactionIsolationLevel(
            Connection.TRANSACTION_SERIALIZABLE
        ));

    System.out.println("Forward-only ResultSet: "
        + meta.supportsResultSetType(
            java.sql.ResultSet.TYPE_FORWARD_ONLY
        ));
}
~~~

Những phương thức `supports...()` mô tả **khả năng được công bố**, không bảo đảm mọi bảng hay mọi SQL cụ thể đều dùng được tính năng. Ví dụ:

- DBMS/driver báo hỗ trợ transaction, nhưng một bảng dùng storage engine không hỗ trợ rollback thì rollback có thể không có tác dụng như dự kiến.
- DBMS báo hỗ trợ batch, nhưng mức tối ưu hoặc hỗ trợ generated keys khi batch có thể khác nhau.
- `supportsSavepoints()` không cho biết **mọi loại lỗi** đều phục hồi được đến savepoint; deadlock có thể làm giao dịch bị DBMS hủy.
- Driver báo hỗ trợ `TRANSACTION_SERIALIZABLE` nhưng cách triển khai và xung đột thực tế có thể khác DBMS khác.

Cũng không nên thay đổi mức cô lập hay auto-commit giữa một transaction đang diễn ra chỉ để “thử” tính năng, vì có thể làm thay đổi ranh giới transaction.

## 9. Ứng dụng thực tế: kiểm tra lược đồ nhập dữ liệu động

Giả sử ứng dụng nhận tệp CSV với ba cột:

~~~text
title,unit_price,note
Bàn phím,890000.00,Bản có dây
Chuột,240000.00,
~~~

Yêu cầu: nhập vào bảng `catalog_items` mà không vượt giới hạn kiểu và không vi phạm `NOT NULL`.

Một quy trình hợp lý:

1. **Khám phá lược đồ** qua `getColumns(...)`, lấy `COLUMN_NAME`, `DATA_TYPE`, `TYPE_NAME`, `COLUMN_SIZE`, `DECIMAL_DIGITS`, `NULLABLE`.
2. **Ánh xạ cột** CSV vào danh sách tên cột được phép nhập; không lấy tên cột tùy ý từ người dùng ghép thẳng vào SQL.
3. **Kiểm tra trước** dữ liệu bắt buộc: `title` không rỗng, `unit_price` có số thập phân hợp lệ, `note` có thể `NULL`.
4. **Đo độ dài theo ngữ nghĩa cột** và encoding/DBMS phù hợp. Không mặc định `String.length()` của Java bằng số ký tự người dùng nhìn thấy hoặc số byte lưu trữ.
5. **Tham số hóa** giá trị bằng `PreparedStatement`, ví dụ `setString`, `setBigDecimal`, `setNull` với `java.sql.Types` phù hợp.
6. **Thực thi trong transaction** theo yêu cầu nghiệp vụ; dùng `executeBatch()` nếu cần nhưng kiểm tra update counts và rollback khi có lỗi bắt buộc.
7. **Để DBMS thực thi ràng buộc cuối cùng**. Metadata và validation ở Java giúp báo lỗi rõ, nhưng không thay thế `NOT NULL`, `CHECK`, `UNIQUE`, khóa ngoại hay kiểm tra trên server.

Ví dụ ánh xạ giá trị:

~~~java
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;

static void bindCatalogItem(
        PreparedStatement ps,
        long id,
        String title,
        BigDecimal unitPrice,
        String note
) throws SQLException {
    ps.setLong(1, id);
    ps.setString(2, title);
    ps.setBigDecimal(3, unitPrice);

    if (note == null) {
        ps.setNull(4, Types.VARCHAR);
    } else {
        ps.setString(4, note);
    }
}
~~~

Mẫu SQL tương ứng:

~~~sql
INSERT INTO catalog_items (id, title, unit_price, note)
VALUES (?, ?, ?, ?);
~~~

**Không suy ra toàn bộ validation chỉ từ metadata.** Ví dụ `COLUMN_SIZE = 120` đối với chuỗi không nói chính xác cách đếm grapheme hay giới hạn byte mà DBMS áp dụng. Trường giá mặc định hay độ chính xác tiền tệ cũng cần quy tắc nghiệp vụ riêng.

Nếu schema có thể thay đổi trong lúc import, cần chiến lược đồng bộ migration, kiểm tra version lược đồ hoặc quản lý thời điểm chạy import. Metadata đọc trước đó có thể đã cũ tại lúc `INSERT` được thực thi.

## 10. Những sai lầm dễ gặp

| Cách hiểu sai | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `getTypeInfo()` cho biết chính xác kiểu và độ dài **mọi cột hiện có** | Nó mô tả các kiểu DBMS công bố | Dùng `getColumns()` cho cột bảng |
| `DATA_TYPE` chính là tên SQL như `VARCHAR` | Đây là mã JDBC | Đọc thêm `TYPE_NAME`; dùng `java.sql.Types` |
| `COLUMN_SIZE` luôn là byte | Với kiểu ký tự thường là số ký tự; với số là precision | Diễn giải theo họ kiểu và dùng `CHAR_OCTET_LENGTH` khi thích hợp |
| `DECIMAL_DIGITS` có nghĩa chung cho mọi kiểu | Nhiều kiểu không áp dụng hoặc nghĩa khác | Kiểm tra JDBC type và `wasNull()` |
| `NULLABLE = 0` nghĩa là unknown | Với `getColumns()`, 0 là `columnNoNulls` | Dùng hằng `DatabaseMetaData.column...` |
| `getMax...() == 0` nghĩa là DBMS không hỗ trợ | Nhiều phương thức dùng 0 cho không giới hạn/không rõ | Không áp ngưỡng bằng 0 |
| Giới hạn metadata dương là khả năng chắc chắn ở mọi bảng | Cấu hình, engine, encoding và tài nguyên có thể hạn chế thêm | Kiểm thử trên môi trường đích |
| `ResultSetMetaData.getColumnName()` luôn bằng alias trong SELECT | Alias thường nằm ở column label | Dùng `getColumnLabel()` khi hiển thị |
| Metadata không cần đóng | `getTypeInfo()` và `getColumns()` trả `ResultSet` | Đóng bằng `try-with-resources` |
| Tên bảng đưa vào `getColumns()` là tên chính xác | Đây là pattern; `_` và `%` là wildcard | Escape pattern và xác minh tên thực |
| Driver hỗ trợ batch nên toàn bộ batch được commit nguyên tử | Batch và transaction là hai cơ chế khác | Quản lý `autoCommit`, `commit()`, `rollback()` |
| Metadata đủ để bảo vệ dữ liệu khỏi SQL injection | Metadata chỉ mô tả, không bảo vệ câu SQL động | Whitelist identifier, tham số hóa giá trị |

## 11. Thực hành và câu hỏi tự kiểm tra

**Tình huống A.** Bạn nhận `DATA_TYPE = Types.VARCHAR` ở hai cột nhưng một cột dài 50, một cột dài 500. Làm sao phân biệt?

**Đáp án:** Đọc `COLUMN_SIZE` của từng cột bằng `DatabaseMetaData.getColumns(...)`. `DATA_TYPE` không mang thông tin độ dài khai báo.

**Tình huống B.** `getMaxColumnsInTable()` trả `0`. Có được từ chối bảng có một cột không?

**Đáp án:** Không. Giá trị `0` trong trường hợp này có thể nghĩa là không giới hạn hoặc không biết; không phải giới hạn bằng không. Cần kiểm tra tài liệu hoặc thử trên DBMS khi cần xác định ngưỡng.

**Tình huống C.** Câu `SELECT unit_price * 2 AS double_price` cần sinh cột JSON tên `double_price`. Nên lấy tên ở đâu?

**Đáp án:** `ResultSetMetaData.getColumnLabel(i)` phản ánh nhãn/alias. `getColumnName(i)` có thể khác với biểu thức truy vấn.

**Tình huống D.** Kiểu `VARCHAR(120)` cho `COLUMN_SIZE = 120`. Có chắc luôn lưu được chuỗi dài 120 ký tự Unicode bất kỳ trong đúng 120 byte không?

**Đáp án:** Không. Kích thước theo ký tự và byte khác nhau. Cần xét encoding và quy tắc DBMS; `CHAR_OCTET_LENGTH` có thể cung cấp thêm thông tin khi driver công bố.

**Tình huống E.** `getColumns(null, null, "user_data", "%")` trả cả bảng `userXdata`. Nguyên nhân có thể là gì?

**Đáp án:** `_` trong tableNamePattern là wildcard một ký tự. Dùng `getSearchStringEscape()` để escape nếu muốn tra tên có dấu gạch dưới thật, rồi xác minh `TABLE_NAME`.

**Tình huống F.** Driver trả SQL `NULL` ở trường `DECIMAL_DIGITS`. Bạn gọi `getInt()` và nhận 0. Có được kết luận scale chắc chắn bằng 0 không?

**Đáp án:** Không. Phải kiểm tra `wasNull()` ngay sau `getInt()` để phân biệt SQL `NULL` với giá trị số 0 thật.

**Tình huống G.** `getTypeInfo()` trả kiểu tên `NUMERIC`, có thể sinh câu lệnh `CREATE TABLE ... NUMERIC(10000, 5000)` ngay không?

**Đáp án:** Không. Metadata công bố kiểu và tham số tạo kiểu, nhưng giới hạn precision/scale và cú pháp cụ thể phụ thuộc DBMS. Phải xác minh giới hạn được hỗ trợ và kiểm tra SQL trên hệ đích.

**Tình huống H.** DBMS báo `supportsBatchUpdates() = true`. Có được bỏ `commit()` khi muốn cả 1.000 dòng cùng nguyên tử?

**Đáp án:** Không. Batch hỗ trợ thực thi theo lô, còn transaction xác định đơn vị commit/rollback. Với yêu cầu nguyên tử, dùng connection hỗ trợ transaction và quản lý `autoCommit = false`.

**Tình huống I.** `getColumns(...)` không trả bảng cần tra. Có thể khẳng định bảng không tồn tại không?

**Đáp án:** Chưa chắc. Có thể do catalog/schema sai, quy tắc hoa/thường của identifier, wildcard pattern hoặc quyền truy cập metadata. Cần kiểm tra cách tra tên và môi trường trước khi kết luận.

## Ghi nhớ

- **`DatabaseMetaData.getTypeInfo()`** cho biết các kiểu dữ liệu SQL được công bố; **`getColumns()`** cho biết kiểu, kích thước và thuộc tính của cột trong bảng.
- **`ResultSetMetaData`** mô tả cấu trúc đầu ra của `SELECT`, kể cả alias và biểu thức tính toán; dùng `getColumnLabel()` cho nhãn hiển thị.
- **`DATA_TYPE` là mã `java.sql.Types`**, còn `TYPE_NAME` là tên kiểu SQL theo DBMS. Luôn kết hợp với `COLUMN_SIZE`, `DECIMAL_DIGITS` và thông tin nullable khi cần.
- **`COLUMN_SIZE` không mặc nhiên là byte**. Với dữ liệu chuỗi và Unicode, cần xem thêm encoding và `CHAR_OCTET_LENGTH` khi có thông tin.
- **Nhiều `getMax...()` trả 0 khi giới hạn không có hoặc chưa rõ**; đừng hiểu là cấm sử dụng. Giới hạn dương được công bố vẫn cần đối chiếu cấu hình DBMS đích.
- **Metadata chỉ hỗ trợ khám phá và kiểm tra trước**. Ràng buộc của DBMS, SQL tham số hóa, transaction và kiểm thử thực tế vẫn quyết định độ an toàn của thao tác CRUD.
