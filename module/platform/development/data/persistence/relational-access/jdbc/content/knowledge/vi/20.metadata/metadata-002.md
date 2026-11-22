# Đọc catalog, schema, bảng và cột theo phạm vi cần thiết trong JDBC

Trong chương **Siêu dữ liệu**, một ứng dụng JDBC đôi khi cần tìm hiểu cấu trúc cơ sở dữ liệu trước khi thực hiện CRUD: bảng `customer` có tồn tại không, cột `email` là kiểu gì, bảng thuộc schema nào, hoặc driver đang kết nối tới catalog nào? Thay vì tự đoán từ tên cơ sở dữ liệu hay chạy `SELECT *` để thăm dò, JDBC cung cấp `DatabaseMetaData` để truy vấn thông tin về **catalog, schema, bảng và cột**.

Điểm quan trọng là **chỉ đọc đúng phạm vi cần thiết**. Truy vấn metadata trên toàn bộ server có thể trả về hàng nghìn bảng/cột, làm tốn tài nguyên và phơi bày những thông tin mà chức năng hiện tại không cần biết. Bài học tập trung vào cách giới hạn phạm vi bằng tham số của `getCatalogs()`, `getSchemas(...)`, `getTables(...)` và `getColumns(...)`; đồng thời giải thích ý nghĩa của `null`, chuỗi rỗng, mẫu tìm kiếm và khác biệt giữa các driver JDBC.

## 1. Catalog, schema, bảng và cột là gì?

Một cách hình dung thường gặp:

```text
Kết nối JDBC
└── Catalog (ví dụ: sales_db)
    └── Schema (ví dụ: public)
        ├── Bảng customer
        │   ├── id        BIGINT
        │   ├── email     VARCHAR
        │   └── created_at TIMESTAMP
        └── Bảng orders
            ├── id          BIGINT
            └── customer_id BIGINT
```

Đây là mô hình khái niệm, **không phải cấu trúc bắt buộc của mọi DB**. Tên và vai trò của catalog/schema khác nhau tùy hệ quản trị:

| Khái niệm | Ý nghĩa khi đọc metadata | Lưu ý |
| --- | --- | --- |
| **Catalog** | Nhóm hoặc phạm vi chứa đối tượng DB ở cấp cao hơn theo mô hình driver | Một số DB xem database là catalog; DB khác không dùng catalog |
| **Schema** | Không gian tên cho các đối tượng như bảng, view | Có DB hỗ trợ nhiều schema trong một catalog; có DB không hỗ trợ schema |
| **Table** | Bảng, view hoặc loại đối tượng dạng bảng tùy giá trị `TABLE_TYPE` | `getTables` có thể trả cả view/system table nếu không lọc |
| **Column** | Cột thuộc một bảng/view | Có kiểu JDBC, kiểu DB, kích thước, nullability, vị trí... |

Ví dụ phổ biến: PostgreSQL thường dùng **database** làm catalog và `public` hoặc schema do ứng dụng tạo làm schema. MySQL thường diễn giải **database** dưới dạng catalog và có thể không có schema độc lập trong metadata. Không nên suy diễn rằng tên catalog và schema luôn trùng nhau hoặc luôn khác nhau.

Đường dẫn JDBC hoặc tên database trong URL **chưa đủ** để suy ra cách driver cung cấp metadata. Hãy đọc giá trị thực tế qua `Connection` và `DatabaseMetaData`.

## 2. Bắt đầu từ `DatabaseMetaData` của đúng `Connection`

`DatabaseMetaData` được lấy trực tiếp từ kết nối đang hoạt động:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public void inspectConnection(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData meta = connection.getMetaData();

        System.out.println("Catalog hiện tại: " + connection.getCatalog());
        System.out.println("Schema hiện tại: " + connection.getSchema());
        System.out.println("DB: " + meta.getDatabaseProductName());
        System.out.println("Driver: " + meta.getDriverName());
    }
}
```

Ví dụ dùng `DataSource` để mượn kết nối và `try-with-resources` để trả kết nối về pool. `Connection.getSchema()` có trong JDBC 4.1; một driver cũ có thể không hỗ trợ hoặc báo lỗi. `getCatalog()` và `getSchema()` cũng có thể trả `null`; điều đó không có nghĩa DB không có bảng.

**Nguyên tắc phạm vi:** Nếu ứng dụng đã biết catalog/schema từ cấu hình triển khai, dùng chính tên ấy để hỏi metadata. Nếu chưa biết, xác minh catalog/schema của kết nối hoặc tra cứu danh mục một lần trong công cụ quản trị; không mặc định đọc toàn bộ catalog, schema và bảng vào mỗi request HTTP.

## 3. Đọc danh sách catalog với `getCatalogs()`

`DatabaseMetaData.getCatalogs()` trả một `ResultSet` có cột `TABLE_CAT`. Mỗi hàng là một tên catalog mà driver cung cấp.

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    try (ResultSet catalogs = meta.getCatalogs()) {
        while (catalogs.next()) {
            String catalog = catalogs.getString("TABLE_CAT");
            System.out.println("Catalog: " + catalog);
        }
    }
}
```

Đoạn ví dụ giả định đã import `java.sql.Connection`, `DatabaseMetaData`, `ResultSet` và có `DataSource dataSource`. `getCatalogs()` **không có tham số thu hẹp phạm vi**; do đó, chỉ gọi khi thật sự cần khám phá các catalog được driver nhìn thấy. Nếu đã biết catalog đích, bỏ qua bước liệt kê này.

Không phải DB nào cũng trả danh sách catalog. `ResultSet` rỗng không đủ để kết luận kết nối không có bảng; có thể driver không hỗ trợ khái niệm catalog hoặc không cung cấp danh mục đó.

## 4. Đọc schema trong catalog cần thiết

JDBC cung cấp:

- `getSchemas()`: liệt kê schema theo khả năng driver, có thể rộng.
- `getSchemas(String catalog, String schemaPattern)`: yêu cầu schema trong catalog và theo mẫu tên, phù hợp hơn khi phạm vi đã xác định.

```java
String selectedCatalog = connection.getCatalog(); // Có thể null.
String selectedSchema = "public";                  // Ví dụ cấu hình ứng dụng.

try (ResultSet schemas = meta.getSchemas(
        selectedCatalog, selectedSchema)) {
    while (schemas.next()) {
        System.out.printf("catalog=%s, schema=%s%n",
                schemas.getString("TABLE_CATALOG"),
                schemas.getString("TABLE_SCHEM"));
    }
}
```

Đoạn mã giả định `connection`/`meta` còn mở. `TABLE_SCHEM` là tên schema; `TABLE_CATALOG` là catalog chứa schema (nếu driver cung cấp). Một số driver có thể không hỗ trợ overload lọc theo catalog/schema; hãy xử lý `SQLException` hoặc `SQLFeatureNotSupportedException` theo khả năng cụ thể.

**Chú ý mẫu tên:** `schemaPattern` là một *search pattern*, không phải tên định danh thuần túy. Nếu schema tên `tenant_01`, ký tự `_` có thể được hiểu là ký tự đại diện cho **một ký tự bất kỳ**. Khi cần tên chính xác, phải escape wildcard như phần 6.

## 5. Đọc bảng bằng `getTables(...)` và giới hạn loại bảng

Chữ ký API:

```java
ResultSet getTables(
        String catalog,
        String schemaPattern,
        String tableNamePattern,
        String[] types) throws SQLException;
```

| Tham số | Vai trò | Ví dụ dùng |
| --- | --- | --- |
| `catalog` | Giới hạn catalog theo tên, **không phải pattern** | `"sales_db"` |
| `schemaPattern` | Giới hạn schema bằng mẫu tìm kiếm | `"public"` |
| `tableNamePattern` | Giới hạn tên bảng bằng mẫu tìm kiếm | `"customer"`, `"order_%"` |
| `types` | Chỉ lấy những loại đối tượng bảng yêu cầu | `new String[]{"TABLE"}` hoặc `{"TABLE","VIEW"}` |

Ví dụ chỉ đọc những bảng người dùng trong schema `public` có tên bắt đầu bằng `customer_`:

```java
String catalog = connection.getCatalog();
String schemaPattern = "public";

try (ResultSet tables = meta.getTables(
        catalog, schemaPattern, "customer_%", new String[] {"TABLE"})) {
    while (tables.next()) {
        System.out.printf("%s.%s [%s]%n",
                tables.getString("TABLE_SCHEM"),
                tables.getString("TABLE_NAME"),
                tables.getString("TABLE_TYPE"));
    }
}
```

**Chú ý:** `"customer_%"` trong ví dụ trên là pattern: dấu `_` khớp một ký tự bất kỳ và `%` khớp chuỗi ký tự. Nếu cần **tiền tố chữ `customer_` theo nghĩa đen**, hãy escape dấu `_`. Nếu chỉ cần đúng bảng `customer`, truyền **tên bảng đã escape** làm `tableNamePattern` để tránh quét nhiều bảng.

Các cột thường dùng trong kết quả:

- `TABLE_CAT`: catalog chứa bảng, có thể `null`.
- `TABLE_SCHEM`: schema chứa bảng, có thể `null`.
- `TABLE_NAME`: tên bảng/view.
- `TABLE_TYPE`: loại đối tượng, chẳng hạn `TABLE` hoặc `VIEW`.
- `REMARKS`: mô tả, có thể rỗng hoặc `null` tùy driver/DB.

Không giả định mọi driver dùng chính xác các loại `TABLE`, `VIEW` hoặc cung cấp đủ loại hệ thống. Khi cần khám phá các loại hợp lệ, gọi `meta.getTableTypes()` và đọc cột `TABLE_TYPE`. Với chức năng thông thường chỉ kiểm tra một bảng nghiệp vụ, không cần liệt kê system table hoặc mọi view.

## 6. Hiểu đúng `null`, `""`, `%` và ký tự escape

Đây là nguồn lỗi rất phổ biến khi truy vấn metadata. Các tham số **catalog** và **pattern** có ý nghĩa khác nhau:

| Giá trị | Với `catalog` | Với `schemaPattern`, `tableNamePattern` hoặc `columnNamePattern` |
| --- | --- | --- |
| `null` | Không dùng catalog để thu hẹp phạm vi | Không dùng tiêu chí tương ứng để thu hẹp phạm vi |
| `""` | Yêu cầu đối tượng **không có catalog** | Yêu cầu đối tượng **không có schema/tên tương ứng** theo ngữ nghĩa API |
| `"%"` | Tên catalog chứa ký tự `%` theo nghĩa đen, nếu có | Wildcard: khớp chuỗi bất kỳ, bao gồm rỗng |
| `"_"` | Tên catalog chứa ký tự `_` theo nghĩa đen, nếu có | Wildcard: khớp đúng một ký tự |

Đối với `getTables` và `getColumns`, các trường có chữ `Pattern` dùng cú pháp tìm kiếm tương tự `LIKE`. Khi tên bảng hoặc schema có dấu `_`, `%` hoặc ký tự escape, việc truyền thẳng tên có thể làm truy vấn rộng hơn dự kiến.

Lấy ký tự escape từ driver bằng `meta.getSearchStringEscape()`. Ví dụ hàm chuyển một tên định danh thành pattern khớp **chính xác tên đó**:

```java
import java.sql.SQLException;

static String exactNamePattern(String name, String escape) throws SQLException {
    if (name == null) {
        return null; // Có chủ đích: không lọc theo tiêu chí này.
    }
    if (escape == null || escape.isEmpty()) {
        if (name.contains("%") || name.contains("_")) {
            throw new SQLException(
                    "Driver không cung cấp escape cho tên chứa wildcard");
        }
        return name;
    }
    return name.replace(escape, escape + escape)
               .replace("%", escape + "%")
               .replace("_", escape + "_");
}
```

Với driver dùng dấu `\` làm escape, tên `customer_order` cần được truyền dưới dạng pattern `customer\_order` để dấu gạch dưới được hiểu đúng theo nghĩa đen. **Không hard-code dấu `\` cho mọi DB**; dùng chuỗi driver cung cấp và kiểm thử tên định danh có ký tự đặc biệt.

Đây là **escape cho tìm kiếm metadata**, không phải cơ chế bảo vệ SQL injection cho câu SQL thực thi. Nếu sau đó dùng tên bảng để tạo câu `SELECT`, `INSERT` hoặc `UPDATE`, tên bảng/cột là **identifier**, không thể thay bằng dấu `?` của `PreparedStatement`. Hãy dùng danh sách định danh cho phép và quy tắc trích dẫn identifier phù hợp với DB, thay vì ghép dữ liệu người dùng trực tiếp vào SQL.

## 7. Đọc cột bằng `getColumns(...)`

API cung cấp:

```java
ResultSet getColumns(
        String catalog,
        String schemaPattern,
        String tableNamePattern,
        String columnNamePattern) throws SQLException;
```

Ví dụ: đã xác định được catalog `sales_db`, schema `public` và bảng `customer`, cần lấy **mọi cột của đúng bảng đó**:

```java
String escape = meta.getSearchStringEscape();

try (ResultSet columns = meta.getColumns(
        "sales_db",
        exactNamePattern("public", escape),
        exactNamePattern("customer", escape),
        null)) { // null: không lọc thêm tên cột trong bảng đã chọn.
    while (columns.next()) {
        System.out.printf("%d. %s — %s (%s)%n",
                columns.getInt("ORDINAL_POSITION"),
                columns.getString("COLUMN_NAME"),
                columns.getString("TYPE_NAME"),
                columns.getString("IS_NULLABLE"));
    }
}
```

Ví dụ sử dụng `exactNamePattern(...)` ở phần trước và giả định `meta` còn mở. Tên catalog `sales_db` chỉ để minh họa; cần thay bằng catalog thật. Nếu DB không có schema, giá trị `schemaPattern` phải được chọn theo ngữ nghĩa driver, chẳng hạn `""` để yêu cầu đối tượng không có schema; `null` có nghĩa **không lọc schema**, nên không phải từ đồng nghĩa của “schema hiện tại”.

Các cột metadata quan trọng:

| Cột trả về | Ý nghĩa | Lưu ý khi đọc |
| --- | --- | --- |
| `TABLE_CAT`, `TABLE_SCHEM`, `TABLE_NAME` | Xác định bảng chứa cột | Dùng để xác minh cột thuộc đúng đối tượng |
| `COLUMN_NAME` | Tên cột | Có thể có quy tắc chữ hoa/chữ thường theo DB |
| `DATA_TYPE` | Mã số kiểu JDBC trong `java.sql.Types` | Phù hợp cho xử lý kiểu có tính di động |
| `TYPE_NAME` | Tên kiểu gốc do DB/driver cung cấp | Có thể khác nhau giữa PostgreSQL, MySQL, SQL Server... |
| `COLUMN_SIZE` | Kích thước/độ chính xác theo định nghĩa JDBC của kiểu | Ý nghĩa phụ thuộc kiểu cột; có thể là SQL `NULL` |
| `DECIMAL_DIGITS` | Số chữ số thập phân đối với kiểu liên quan | Có thể là `NULL` nếu không áp dụng |
| `NULLABLE` | Mã `columnNoNulls`, `columnNullable`, `columnNullableUnknown` | Không ép mã unknown thành “không cho NULL” |
| `IS_NULLABLE` | Chuỗi `YES`, `NO` hoặc chuỗi rỗng nếu không xác định | Dễ hiển thị nhưng cần xử lý unknown |
| `COLUMN_DEF` | Giá trị mặc định nếu driver cung cấp | Không đảm bảo cú pháp giống nhau giữa DB |
| `ORDINAL_POSITION` | Vị trí cột trong bảng, bắt đầu từ 1 | Dùng khi cần trình bày theo thứ tự schema |

Một số trường có thể chứa SQL `NULL`. Nếu gọi getter kiểu nguyên thủy như `getInt("COLUMN_SIZE")`, JDBC trả `0` cho SQL `NULL`; phải dùng `wasNull()` **ngay sau lời gọi getter** nếu cần phân biệt giá trị thiếu với 0.

```java
int rawSize = columns.getInt("COLUMN_SIZE");
Integer size = columns.wasNull() ? null : rawSize;

int nullability = columns.getInt("NULLABLE");
boolean nullable = nullability == DatabaseMetaData.columnNullable;
boolean unknown = nullability == DatabaseMetaData.columnNullableUnknown;
```

`size` là `Integer` để có thể biểu diễn `null`. Với `NULLABLE`, cần phân biệt cả ba trạng thái; cách đặt hai boolean trong ví dụ chỉ minh họa việc không gộp `unknown` vào `false`.

## 8. Ví dụ hoàn chỉnh: chỉ mô tả bảng được yêu cầu

Ví dụ sau nhận phạm vi catalog, schema và tên bảng đã được ứng dụng xác định. Nó hỏi `getTables(...)` để kiểm tra đúng một bảng/view, **đóng `ResultSet` trước**, rồi mới gọi `getColumns(...)` nhằm tránh dựa vào khả năng driver giữ nhiều cursor metadata mở cùng lúc. Kết quả chứa các thông tin cần thiết cho hiển thị schema hoặc kiểm tra mapping JDBC.

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class TableMetadataReader {
    private final DataSource dataSource;

    public TableMetadataReader(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public record ColumnInfo(
            String name,
            int jdbcType,
            String dbType,
            Integer size,
            int position,
            String isNullable) {}

    public record TableInfo(
            String catalog,
            String schema,
            String name,
            String type,
            List<ColumnInfo> columns) {}

    public Optional<TableInfo> describe(
            String catalog, String schema, String tableName)
            throws SQLException {
        if (tableName == null || tableName.isBlank()) {
            throw new IllegalArgumentException("Cần tên bảng cụ thể");
        }

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();
            String escape = meta.getSearchStringEscape();
            String tablePattern = exactNamePattern(tableName, escape);
            String schemaPattern = exactNamePattern(schema, escape);

            String foundCatalog;
            String foundSchema;
            String foundName;
            String foundType;

            try (ResultSet tables = meta.getTables(
                    catalog, schemaPattern, tablePattern,
                    new String[] {"TABLE", "VIEW"})) {
                if (!tables.next()) {
                    return Optional.empty();
                }
                foundCatalog = tables.getString("TABLE_CAT");
                foundSchema = tables.getString("TABLE_SCHEM");
                foundName = tables.getString("TABLE_NAME");
                foundType = tables.getString("TABLE_TYPE");

                if (tables.next()) {
                    throw new SQLException(
                            "Nhiều bảng khớp; cần chọn catalog/schema cụ thể");
                }
            }

            List<ColumnInfo> columns = new ArrayList<>();
            try (ResultSet rs = meta.getColumns(
                    foundCatalog,
                    exactNamePattern(foundSchema, escape),
                    exactNamePattern(foundName, escape),
                    null)) {
                while (rs.next()) {
                    // Một tham số null có thể mở rộng phạm vi truy vấn:
                    // chỉ nhận cột thuộc chính bảng đã xác minh.
                    if (!Objects.equals(foundCatalog,
                                rs.getString("TABLE_CAT"))
                            || !Objects.equals(foundSchema,
                                rs.getString("TABLE_SCHEM"))
                            || !Objects.equals(foundName,
                                rs.getString("TABLE_NAME"))) {
                        continue;
                    }

                    int rawSize = rs.getInt("COLUMN_SIZE");
                    Integer size = rs.wasNull() ? null : rawSize;

                    columns.add(new ColumnInfo(
                            rs.getString("COLUMN_NAME"),
                            rs.getInt("DATA_TYPE"),
                            rs.getString("TYPE_NAME"),
                            size,
                            rs.getInt("ORDINAL_POSITION"),
                            rs.getString("IS_NULLABLE")));
                }
            }

            if (columns.isEmpty()) {
                throw new SQLException(
                        "Không nhận được metadata cột cho bảng " + foundName);
            }
            return Optional.of(new TableInfo(
                    foundCatalog, foundSchema, foundName,
                    foundType, List.copyOf(columns)));
        }
    }

    private static String exactNamePattern(String name, String escape)
            throws SQLException {
        if (name == null) {
            return null;
        }
        if (escape == null || escape.isEmpty()) {
            if (name.contains("%") || name.contains("_")) {
                throw new SQLException(
                        "Không thể escape tên chứa wildcard với driver này");
            }
            return name;
        }
        return name.replace(escape, escape + escape)
                   .replace("%", escape + "%")
                   .replace("_", escape + "_");
    }
}
```

Ví dụ sử dụng `record` và `List.copyOf` (Java 16+ là lựa chọn phù hợp cho cả hai). Cách gọi minh họa:

```java
TableMetadataReader reader = new TableMetadataReader(dataSource);

// Thay tên catalog và schema bằng phạm vi thật của kết nối.
reader.describe("sales_db", "public", "customer")
      .ifPresent(table -> {
          System.out.println("Bảng: " + table.name());
          table.columns().forEach(column ->
                  System.out.printf("%d %s %s%n",
                          column.position(),
                          column.name(),
                          column.dbType()));
      });
```

Ví dụ chọn đúng một bảng bằng tên và từ chối tình huống nhiều đối tượng trùng tên. Nếu catalog/schema là `null`, API có thể tìm trên phạm vi rộng hơn; do đó trong production nên truyền phạm vi đã được cấu hình hoặc lấy từ kết nối khi đáng tin cậy. Việc lọc lại `TABLE_CAT`/`TABLE_SCHEM`/`TABLE_NAME` giúp tránh trộn cột khi driver trả kết quả rộng vì thiếu tham số.

Danh sách `types` ở ví dụ dùng `TABLE`/`VIEW`; trên driver có tên loại khác, có thể cần đọc `getTableTypes()` trước hoặc sửa danh sách theo hợp đồng sản phẩm. Khi trả `Optional.empty()`, cần phân biệt bảng thực sự không có với trường hợp phân quyền metadata hạn chế hoặc cách phân biệt chữ hoa/chữ thường khác nhau.

## 9. Chữ hoa/chữ thường và quoted identifier

Tên bảng `customer`, `CUSTOMER` và `"Customer"` không nhất thiết giống nhau giữa các hệ quản trị. Một số DB tự chuẩn hóa identifier không được trích dẫn thành chữ hoa hoặc chữ thường; identifier có dấu nháy có thể giữ nguyên kiểu chữ.

`DatabaseMetaData` có các phương thức mô tả quy tắc lưu identifier:

```java
System.out.println(meta.storesUpperCaseIdentifiers());
System.out.println(meta.storesLowerCaseIdentifiers());
System.out.println(meta.storesMixedCaseIdentifiers());
System.out.println(meta.supportsMixedCaseQuotedIdentifiers());
System.out.println(meta.getIdentifierQuoteString());
```

Không tự động chuyển mọi tên sang chữ hoa hoặc thường theo quy tắc của DB khác. Nếu `getTables(...)` trả rỗng, hãy kiểm tra chính xác tên và quy tắc quoted identifier ở DB đích; đừng sửa bằng cách mở rộng truy vấn thành `%` trên tất cả schema rồi lấy kết quả đầu tiên.

## 10. Phân biệt `DatabaseMetaData` và `ResultSetMetaData`

Hai API có mục đích khác nhau:

| API | Trả lời câu hỏi | Phạm vi |
| --- | --- | --- |
| `DatabaseMetaData` | Trong DB có catalog, schema, bảng, cột nào? | Cấu trúc cơ sở dữ liệu do driver cung cấp |
| `ResultSetMetaData` | Kết quả của **câu truy vấn SQL này** có mấy cột, tên/kiểu hiển thị ra sao? | Những cột trong kết quả cụ thể, kể cả biểu thức hoặc alias |

Ví dụ:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, email AS contact FROM customer WHERE id = ?")) {
    ps.setLong(1, 42L);
    try (ResultSet rs = ps.executeQuery()) {
        java.sql.ResultSetMetaData columns = rs.getMetaData();
        for (int i = 1; i <= columns.getColumnCount(); i++) {
            System.out.printf("%s (%d)%n",
                    columns.getColumnLabel(i),
                    columns.getColumnType(i));
        }
    }
}
```

`ResultSetMetaData` ở ví dụ trên sẽ mô tả hai cột kết quả và có thể hiển thị nhãn `contact` thay cho tên cột gốc `email`. Nó **không** cho biết toàn bộ cột của bảng `customer`. Nếu cần duyệt schema, dùng `DatabaseMetaData.getColumns(...)`.

## 11. Giới hạn khả chuyển và hiệu năng

- **Không có một phân cấp catalog/schema duy nhất:** cùng một lời gọi có thể trả tên catalog/schema khác nhau hoặc `null` tùy DB/driver.
- **Metadata có thể không đầy đủ:** driver có thể không điền `REMARKS`, `COLUMN_DEF`, độ chính xác hoặc schema ẩn; quyền của tài khoản cũng ảnh hưởng những đối tượng quan sát được.
- **Các tên `TABLE_TYPE` khác nhau:** không mặc định mọi hệ thống đều phân loại view, materialized view hay system table cùng một cách.
- **Không phải metadata luôn tức thời:** khi ứng dụng thay đổi schema bằng migration, cache ở tầng ứng dụng/driver hoặc phiên làm việc có thể cần được làm mới. Không dùng thông tin cũ để suy ra schema hiện tại.
- **Truy vấn rộng tốn chi phí:** tránh `getTables(null, null, "%", null)` và `getColumns(null, null, "%", "%")` trong đường xử lý thường xuyên. Dùng catalog/schema/bảng cụ thể và chỉ đọc các cột cần thiết.
- **Không xem metadata là cơ chế cấp quyền:** việc nhìn thấy hoặc không nhìn thấy đối tượng trong metadata không chứng minh tài khoản có thể thực hiện `SELECT`/`UPDATE`; quyền truy cập phải được DB thực thi.
- **Không cần dựng SQL thủ công để đọc tên cột:** `getColumns` trả thông tin cấu trúc mà không cần `SELECT *`. Nếu cần lấy dữ liệu thực tế, vẫn dùng `PreparedStatement` với tham số hóa giá trị và kiểm soát định danh SQL.

Trong ứng dụng khởi động thường xuyên kiểm tra cấu trúc, có thể đọc metadata một lần theo **tập bảng đã biết**, lưu cache có vòng đời rõ ràng và làm mới sau migration. Tuy nhiên, metadata của hai DB hoặc hai tenant không nên bị dùng chung chỉ vì tên bảng giống nhau.

## 12. Bài thực hành kiểm tra phạm vi

Giả sử ứng dụng quản lý khách hàng sử dụng catalog `sales_db`, schema `public` và bảng `customer`:

1. Lấy `DatabaseMetaData` từ kết nối của `DataSource`. In tên driver, DB, catalog/schema hiện tại, đồng thời ghi nhận khả năng giá trị `null`.
2. Chỉ dùng `getCatalogs()` nếu chưa biết catalog. Nếu đã biết `sales_db`, dùng trực tiếp tham số catalog trong `getSchemas(...)` và `getTables(...)`.
3. Gọi `getSchemas("sales_db", "public")` và kiểm tra `TABLE_CATALOG`/`TABLE_SCHEM`; sau đó dùng `getTables("sales_db", "public", "customer", new String[]{"TABLE"})`.
4. Gọi `getColumns(...)` cho **đúng bảng** và in `COLUMN_NAME`, `DATA_TYPE`, `TYPE_NAME`, `COLUMN_SIZE`, `DECIMAL_DIGITS`, `IS_NULLABLE` và `ORDINAL_POSITION`.
5. Tạo một bảng thử nghiệm `customer_log` hoặc `order_item` có ký tự `_`. So sánh kết quả tìm kiếm khi truyền tên trực tiếp và tên được tạo bằng `exactNamePattern(...)`; nhận diện wildcard mở rộng ngoài ý định.
6. Thử truyền `schemaPattern=null` và `schemaPattern=""` trên DB kiểm thử để hiểu khác biệt; ghi lại hành vi và liệu DB có khái niệm schema hay không.
7. Đổi tài khoản kết nối hoặc DB driver trong môi trường thử nghiệm. So sánh danh sách bảng, kiểu cột và cách lưu tên định danh; không kết luận một kết quả trên DB này là quy tắc chung cho mọi JDBC driver.

**Tự kiểm tra:**

- Vì sao `getTables(null, null, "%", null)` thường không phù hợp với một API chỉ cần kiểm tra bảng `customer`?
- Trong `getColumns(...)`, sự khác nhau giữa `columnNamePattern=null` và `columnNamePattern="%"` là gì khi chỉ cần mọi cột của một bảng đã biết?
- Vì sao tên `order_item` cần escape dấu `_` khi truyền vào tham số có chữ `Pattern`?
- Khi `TABLE_SCHEM` là `null`, có thể tự kết luận `schemaPattern=null` chỉ tìm schema hiện tại không?
- Vì sao `ResultSetMetaData` của `SELECT email AS contact` không thay thế được `DatabaseMetaData.getColumns(...)`?
- Vì sao cần đọc `wasNull()` ngay sau `getInt("COLUMN_SIZE")`?

**Ghi nhớ:** Muốn đọc cấu trúc database qua JDBC, bắt đầu từ `Connection.getMetaData()`, xác định đúng **catalog → schema → bảng → cột** theo cách driver thực sự cung cấp, rồi giới hạn `getSchemas`, `getTables` và `getColumns` vào phạm vi nghiệp vụ. Phân biệt `null` với chuỗi rỗng và wildcard, escape tên định danh khi dùng tham số `Pattern`, đóng `ResultSet` đúng lúc, và kiểm tra khác biệt giữa các DB trước khi dựa vào metadata cho thao tác CRUD hoặc công cụ quản trị.
