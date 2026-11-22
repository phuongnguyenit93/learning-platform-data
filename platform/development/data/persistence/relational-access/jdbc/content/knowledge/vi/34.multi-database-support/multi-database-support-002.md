# Kiểm tra quy tắc định danh, chữ hoa chữ thường và schema trong JDBC

Một repository JDBC chạy đúng trên PostgreSQL có thể báo “table not found” khi chuyển sang Oracle, MySQL hoặc SQL Server, dù SQL và tên bảng nhìn qua gần như giống nhau. Nguyên nhân có thể nằm ở **quy tắc định danh SQL** (*identifier*), cách xử lý **chữ hoa/chữ thường**, **dấu bao tên** hoặc **schema/catalog hiện hành**, chứ không chỉ do lỗi kết nối.

Ví dụ, tên bảng không đặt trong dấu nháy `CustomerAccount` có thể được DB lưu thành `customeraccount` hoặc `CUSTOMERACCOUNT`. Trong khi đó, tên đã bao trong dấu nháy `"CustomerAccount"` có thể được lưu chính xác, phân biệt chữ hoa/chữ thường. Nếu ứng dụng luôn tự gọi `toUpperCase()`, luôn thêm dấu nháy đôi hoặc giả định `schema` đồng nghĩa với `database`, mã sẽ khó di chuyển giữa các DBMS.

Bài thuộc chương **Đa hệ quản trị** của module **JDBC**. Mục tiêu là sử dụng `DatabaseMetaData`, `Connection`, `PreparedStatement` và các API chuẩn để kiểm tra tên đối tượng thực tế, xác định quy tắc đặt tên, truy vấn đúng bảng trong đúng schema, đồng thời tránh SQL injection khi phải dựng tên bảng động.

Sau bài học, bạn có thể:

- Phân biệt **identifier** với **giá trị dữ liệu** được gán qua dấu `?`.
- Giải thích định danh **không quote** và **có quote** có thể được DB xử lý khác nhau như thế nào.
- Kiểm tra quy tắc case, quote, schema/catalog bằng `DatabaseMetaData`.
- Tìm đúng bảng/cột qua `getTables`/`getColumns` và hiểu các metadata search patterns.
- Phân biệt `catalog`, `schema`, default schema và `search_path` theo DBMS.
- Xây dựng SQL có schema/table an toàn và kiểm tra kết nối được tái sử dụng từ pool.
- Thiết kế integration test phát hiện sai khác giữa PostgreSQL, Oracle, SQL Server, MySQL/MariaDB và H2.

## 1. Identifier khác gì giá trị tham số?

Trong SQL, identifier là tên schema, catalog, bảng, view, cột, index, sequence hoặc đối tượng khác. Xét truy vấn:

```sql
SELECT account_id, email
FROM app_data.customer_account
WHERE account_id = ?;
```

| Thành phần | Vai trò |
| --- | --- |
| `app_data` | Tên schema nếu DBMS hỗ trợ cấu trúc tương ứng |
| `customer_account` | Tên bảng |
| `account_id`, `email` | Tên cột |
| `?` | Chỗ đặt **giá trị** của điều kiện |

Ứng dụng bind giá trị bằng `PreparedStatement`:

```java
String sql = """
        SELECT account_id, email
        FROM app_data.customer_account
        WHERE account_id = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 501L);
    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getString("email"));
        }
    }
}
```

Ngược lại, `SELECT ... FROM ? WHERE ...` **không phải cách portable để truyền tên bảng**: dấu `?` biểu diễn giá trị dữ liệu, không thay được phần cấu trúc SQL. Điều này đúng cả khi dùng `PreparedStatement.setString(...)`. Nếu tên bảng cần thay đổi, phải chọn từ những tên **được cho phép** và dựng đúng cú pháp identifier theo DB, rồi tiếp tục bind các **giá trị** bằng `?`.

## 2. Unquoted và quoted identifiers

Một định danh SQL có hai cách viết chủ yếu:

1. **Unquoted identifier:** `customer_account`, `AccountId`.
2. **Quoted/delimited identifier:** `"CustomerAccount"`, `"AccountId"` trên DB dùng dấu nháy đôi chuẩn SQL.

Ví dụ hai lệnh tạo bảng minh họa, **không nên chạy liên tiếp** nếu chưa kiểm tra có đụng tên hay không:

```sql
-- Không quote: DB có thể chuyển tên sang một dạng case thống nhất.
CREATE TABLE CustomerAccount (AccountId BIGINT PRIMARY KEY);

-- Có quote: DB có thể giữ chính xác case của identifier.
CREATE TABLE "CustomerAccount" ("AccountId" BIGINT PRIMARY KEY);
```

Ở một DB gấp unquoted identifier về chữ thường, bảng đầu tiên có thể được lưu là `customeraccount`; bảng thứ hai giữ `CustomerAccount`. Khi ấy:

```sql
SELECT AccountId FROM CustomerAccount;        -- Tìm tên unquoted.
SELECT "AccountId" FROM "CustomerAccount";  -- Tìm tên quoted.
```

**Đừng tự động đặt dấu nháy quanh mọi identifier** trong một ứng dụng cũ. Nếu bảng được tạo unquoted và DB đã fold tên sang chữ thường hoặc chữ hoa, câu SQL có quote với chữ hoa/thường khác có thể không tìm đúng đối tượng.

### Dấu nháy đôi không phải dấu nháy đơn

```sql
SELECT "email" FROM "customer_account" WHERE account_id = ?;
```

Trong DB hỗ trợ quoted identifier bằng dấu nháy đôi, `"email"` là tên cột. `'email'` thông thường là string literal. MySQL có kiểu quoting thường dùng backtick và có SQL mode ảnh hưởng đến dấu nháy đôi; SQL Server hỗ trợ bracket quoting và quy tắc `QUOTED_IDENTIFIER`. Không thay dấu quote tùy tiện khi đổi driver.

## 3. Các hệ quản trị phổ biến khác nhau ra sao?

| DBMS | Quy tắc unquoted thường gặp | Quoted identifier | Điểm cần kiểm tra về schema/catalog |
| --- | --- | --- | --- |
| **PostgreSQL** | Gấp về **chữ thường** | Dấu `"..."`; thường giữ và phân biệt case | Schema như `public`, `sales` và `search_path` |
| **Oracle Database** | Gấp về **chữ hoa** | Dấu `"..."`; giữ tên được quote | Schema chủ sở hữu đối tượng; quyền và synonym |
| **MySQL/MariaDB** | Tên database/table chịu ảnh hưởng `lower_case_table_names`, hệ điều hành; quy tắc tên cột có thể khác | Thường là dấu backtick; dấu `"..."` phụ thuộc SQL mode | Database thường được đưa vào `catalog` ở JDBC metadata |
| **SQL Server** | Tính nhạy case có thể phụ thuộc collation và cấu hình | `[...]` hoặc `"..."` theo điều kiện hỗ trợ | Database/catalog và schema (ví dụ `dbo`), default schema theo user |
| **H2** | Thường gấp unquoted về chữ hoa theo mặc định, có thể cấu hình khác | Có quoted identifier | Compatibility mode không bảo đảm giống DB sản xuất |

**Đây là định hướng, không phải bảng luật bất biến cho mọi phiên bản/driver.** Đặc biệt, trên MySQL/MariaDB, `lower_case_table_names` có thể ảnh hưởng đến tên **database/table** theo hệ điều hành; không suy ra mọi loại tên cột, alias và trigger cùng tuân theo một quy tắc duy nhất. Với SQL Server, không kết luận “luôn không phân biệt case” nếu chưa biết collation và cách cấu hình.

Một thiết kế cần chạy đa DB không nên phụ thuộc khả năng tạo đồng thời `users` và `Users` như hai bảng riêng biệt. Tên đơn giản, thống nhất như `customer_account` và `account_id` thường giảm đáng kể chi phí chuyển hệ quản trị.

## 4. `DatabaseMetaData`: hỏi DB/driver thay vì đoán

`Connection.getMetaData()` trả `DatabaseMetaData`, giao diện JDBC công bố thông tin driver/DB. Các phương thức cần biết:

| API | Dùng để kiểm tra |
| --- | --- |
| `getIdentifierQuoteString()` | Chuỗi dùng để quote identifier; có thể trả **một dấu cách** nếu không hỗ trợ |
| `supportsMixedCaseIdentifiers()` | DB có xem unquoted identifiers mixed case là case-sensitive không |
| `storesUpperCaseIdentifiers()` | Unquoted identifiers được lưu bằng chữ hoa theo hợp đồng DB |
| `storesLowerCaseIdentifiers()` | Unquoted identifiers được lưu bằng chữ thường |
| `storesMixedCaseIdentifiers()` | Unquoted identifiers được lưu mixed case trong chế độ không phân biệt case |
| `supportsMixedCaseQuotedIdentifiers()` | Quoted identifiers có phân biệt mixed case không |
| `storesUpperCaseQuotedIdentifiers()` | Quoted identifiers có được lưu chữ hoa không |
| `storesLowerCaseQuotedIdentifiers()` | Quoted identifiers có được lưu chữ thường không |
| `storesMixedCaseQuotedIdentifiers()` | Quoted identifiers có được lưu mixed case không |
| `getSchemaTerm()`, `getCatalogTerm()` | Tên khái niệm schema/catalog do DBMS công bố |
| `supportsSchemasInDataManipulation()` | Hỗ trợ schema qualification trong DML |
| `supportsCatalogsInDataManipulation()` | Hỗ trợ catalog qualification trong DML |
| `getSearchStringEscape()` | Chuỗi escape cho pattern tìm kiếm trong metadata |

**Ví dụ Java 17+**, đặt phương thức sau vào một lớp tiện ích:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void printIdentifierRules(DataSource dataSource)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData meta = connection.getMetaData();

        System.out.println("DBMS: " + meta.getDatabaseProductName()
                + " " + meta.getDatabaseProductVersion());
        System.out.println("Driver: " + meta.getDriverName()
                + " " + meta.getDriverVersion());
        System.out.println("Quote: [" + meta.getIdentifierQuoteString() + "]");

        System.out.println("Unquoted case-sensitive: "
                + meta.supportsMixedCaseIdentifiers());
        System.out.println("Unquoted upper: "
                + meta.storesUpperCaseIdentifiers());
        System.out.println("Unquoted lower: "
                + meta.storesLowerCaseIdentifiers());
        System.out.println("Unquoted mixed: "
                + meta.storesMixedCaseIdentifiers());

        System.out.println("Quoted case-sensitive: "
                + meta.supportsMixedCaseQuotedIdentifiers());
        System.out.println("Quoted upper: "
                + meta.storesUpperCaseQuotedIdentifiers());
        System.out.println("Quoted lower: "
                + meta.storesLowerCaseQuotedIdentifiers());
        System.out.println("Quoted mixed: "
                + meta.storesMixedCaseQuotedIdentifiers());

        System.out.println("Schema term: " + meta.getSchemaTerm());
        System.out.println("Catalog term: " + meta.getCatalogTerm());
        System.out.println("Schema in DML: "
                + meta.supportsSchemasInDataManipulation());
        System.out.println("Catalog in DML: "
                + meta.supportsCatalogsInDataManipulation());
        System.out.println("Metadata escape: ["
                + meta.getSearchStringEscape() + "]");
    }
}
```

Mã dùng `DataSource` được cấu hình sẵn qua driver hoặc pool; không hardcode mật khẩu. Thông tin metadata có thể không đầy đủ ở một số driver hoặc thay đổi theo phiên bản/config. **Không lấy riêng một cờ case làm kết luận cho mọi loại identifier.**

### Unquoted và quoted có nhóm thuộc tính khác nhau

Nếu `storesUpperCaseIdentifiers()` trả `true`, thông tin này nói về **unquoted identifiers**, không có nghĩa các tên được tạo bằng `"MixedCase"` cũng được lưu uppercase. Để xét quoted identifiers, phải kiểm tra các method có chữ `Quoted`. Tương tự, `supportsMixedCaseIdentifiers()` không chỉ đơn giản nghĩa “có thể gõ tên cột chứa chữ hoa”; nó mô tả cách DB đối xử với case của unquoted identifiers.

## 5. Catalog và schema không phải từ đồng nghĩa

Một mô hình phổ biến:

```text
Database server
  |
  +-- Catalog / database
        |
        +-- Schema
              |
              +-- Table
                    |
                    +-- Column
```

Nhưng không phải mọi DB đều dùng đủ các tầng như nhau:

| DBMS | Ví dụ tên đầy đủ hoặc tương đối | Cách hiểu |
| --- | --- | --- |
| PostgreSQL | `sales.customer_account` | `sales` là schema của database đang kết nối |
| Oracle | `SALES.CUSTOMER_ACCOUNT` | `SALES` là schema của chủ sở hữu đối tượng |
| SQL Server | `SalesDb.dbo.CustomerAccount` | `SalesDb` là database/catalog, `dbo` là schema |
| MySQL | `shop_db.customer_account` | `shop_db` là database, thường ánh xạ catalog trong JDBC |

`DatabaseMetaData.getTables(...)` dùng các cột metadata:

- `TABLE_CAT`: catalog, có thể là `NULL` nếu không áp dụng.
- `TABLE_SCHEM`: schema, có thể là `NULL` nếu không áp dụng.
- `TABLE_NAME`: tên bảng do driver công bố.
- `TABLE_TYPE`: loại đối tượng như `TABLE`, `VIEW`, tùy driver.

```java
try (Connection connection = dataSource.getConnection()) {
    System.out.println("Catalog: " + connection.getCatalog());
    System.out.println("Schema: " + connection.getSchema());
}
```

`Connection.getSchema()` là API JDBC 4.1; driver có thể không hỗ trợ hoặc báo thông tin chưa đủ để mô tả **search path**. `getCatalog()` và `getSchema()` không liệt kê tất cả schema mà tài khoản có quyền đọc. Muốn khám phá, dùng `DatabaseMetaData.getCatalogs()` và `getSchemas()` theo khả năng driver.

## 6. Tìm tên bảng thật bằng `getTables()`

Trước khi sửa SQL vì lỗi “table not found”, hãy đọc metadata để biết DB đang công bố tên bảng theo dạng nào:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void listAccountTables(DataSource dataSource)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData meta = connection.getMetaData();
        try (ResultSet tables = meta.getTables(
                connection.getCatalog(),
                null,                       // Mọi schema trong phạm vi có thể.
                "%ACCOUNT%",                 // Search pattern, KHÔNG phải tên exact.
                new String[] { "TABLE", "VIEW" })) {

            while (tables.next()) {
                System.out.println("catalog="
                        + tables.getString("TABLE_CAT")
                        + ", schema=" + tables.getString("TABLE_SCHEM")
                        + ", name=" + tables.getString("TABLE_NAME")
                        + ", type=" + tables.getString("TABLE_TYPE"));
            }
        }
    }
}
```

Pattern `%ACCOUNT%` là cách **khám phá tên** và có thể không khớp nếu driver dùng case-sensitive pattern khác. Khi đã biết tên thực tế, nên thu hẹp bằng catalog/schema/name pattern tương ứng; không lấy dòng đầu tiên nếu có hai bảng trùng tên ở nhiều schema.

**Metadata không bảo đảm quyền truy vấn:** bảng có thể xuất hiện nhưng user không được `SELECT`, hoặc object truy cập qua synonym/view không xuất hiện dưới kiểu `TABLE`. Vì vậy, sau khi biết tên, cần thử SQL có qualification phù hợp bằng chính tài khoản ứng dụng.

## 7. `%` và `_` trong metadata search pattern

Tên `audit_log` trông giống một chuỗi literal, nhưng khi được truyền vào `getTables(..., tableNamePattern, ...)`, ký tự `_` có thể được hiểu là **wildcard khớp một ký tự**; `%` khớp một chuỗi ký tự. Vì vậy, pattern `audit_log` có thể khớp cả tên gần giống `auditXlog` ở DB/driver áp dụng quy tắc pattern đó.

**`DatabaseMetaData.getSearchStringEscape()`** trả chuỗi escape dùng cho wildcard trong **metadata**. Không mặc định nó luôn là backslash. Một helper thận trọng cho driver báo **escape đúng một ký tự**:

```java
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public static String exactMetadataPattern(
        DatabaseMetaData metadata, String name) throws SQLException {

    if (name == null) {
        throw new IllegalArgumentException("name must not be null");
    }
    String escape = metadata.getSearchStringEscape();

    if (escape == null || escape.length() != 1) {
        // Fail closed: không đoán quy tắc escape khi chưa biết.
        throw new SQLException(
                "Unsupported metadata pattern escape: [" + escape + "]");
    }

    char escapeChar = escape.charAt(0);
    StringBuilder pattern = new StringBuilder();
    for (int i = 0; i < name.length(); i++) {
        char ch = name.charAt(i);
        if (ch == '%' || ch == '_' || ch == escapeChar) {
            pattern.append(escapeChar);
        }
        pattern.append(ch);
    }
    return pattern.toString();
}
```

Helper này **không phải API JDBC có sẵn** và cố ý từ chối driver có escape rỗng hoặc nhiều ký tự. Nếu driver trả quy tắc đặc biệt, cần adapter/kiểm thử riêng. Sau khi escape, vẫn nên so sánh **`TABLE_NAME` thực tế** với tên dự kiến vì cách xử lý pattern và chữ hoa/thường có thể khác.

| Vị trí | Ý nghĩa |
| --- | --- |
| `statement.setString(1, value)` | Gán **giá trị dữ liệu** cho SQL |
| `getTables(catalog, schemaPattern, tableNamePattern, types)` | Tìm **tên đối tượng qua metadata pattern** |
| `FROM schema.table` | **SQL identifier** được parser DB phân tích |

Không dùng helper escape metadata pattern để “sanitize” tên bảng trong SQL; đó là hai ngữ cảnh hoàn toàn khác nhau.

## 8. Khám phá schema và catalog

Khi chưa biết đối tượng nằm trong catalog hay schema nào, có thể liệt kê những phạm vi mà driver công bố:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    try (ResultSet catalogs = meta.getCatalogs()) {
        while (catalogs.next()) {
            System.out.println(
                    "Catalog: " + catalogs.getString("TABLE_CAT"));
        }
    }

    try (ResultSet schemas = meta.getSchemas()) {
        while (schemas.next()) {
            System.out.println(
                    "Schema: " + schemas.getString("TABLE_SCHEM")
                    + ", catalog: " + schemas.getString("TABLE_CATALOG"));
        }
    }
}
```

`getCatalogs`/`getSchemas` có thể trả dữ liệu giới hạn theo quyền hoặc thiếu một số loại đối tượng. Nếu kết quả trống, không tự kết luận DB không tồn tại schema/catalog. Cũng cần phân biệt:

- `null` trong tham số `catalog` hoặc `schemaPattern` thường nghĩa **không dùng giá trị đó để thu hẹp tìm kiếm** theo hợp đồng API.
- Chuỗi rỗng `""` có thể có ý nghĩa khác `null`, ví dụ yêu cầu những đối tượng **không có catalog/schema**.
- `tableNamePattern` là **pattern**, không phải tên bảng exact nếu chưa escape.

Với database lớn, không chạy `getTables(null, null, null, null)` trên mọi request: quét metadata có thể tốn chi phí và trả rất nhiều đối tượng. Nên thực hiện introspection lúc khởi động, migration, công cụ chẩn đoán hoặc cache có kiểm soát.

## 9. Ví dụ hoàn chỉnh: kiểm tra tên bảng/cột theo JDBC metadata

Khi làm việc với nhiều DBMS, một lớp **introspection** có thể hỗ trợ xác định:

- Bảng được lưu dưới tên nào sau khi tạo **không quote**.
- Bảng thuộc catalog/schema nào trong metadata.
- Các cột có tên, `DATA_TYPE`, `TYPE_NAME` và vị trí như thế nào.

Ví dụ sau **không thực hiện DML** và không tự thay đổi schema. Nó đọc metadata từ cùng một connection, đóng mọi `ResultSet` sau khi sử dụng. Để tránh nhầm `getTables` với `getColumns`, đoạn mã **thu thập các bảng trước, đóng ResultSet của `getTables` rồi mới đọc chi tiết cột**.

**Tệp minh họa `JdbcIdentifierInspector.java`** (Java 17+):

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import javax.sql.DataSource;

public final class JdbcIdentifierInspector {
    public record TableRef(
            String catalog, String schema, String table) {
    }

    public record ColumnInfo(
            String name, int jdbcType,
            String sqlTypeName, int position) {
    }

    public record TableInfo(
            TableRef ref, List<ColumnInfo> columns) {
    }

    private final DataSource dataSource;

    public JdbcIdentifierInspector(DataSource dataSource) {
        this.dataSource =
                Objects.requireNonNull(dataSource, "dataSource");
    }

    public List<TableInfo> inspectUnquotedTable(
            String catalog, String schema, String table)
            throws SQLException {

        Objects.requireNonNull(table, "table");
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            // Chỉ dùng cho tên được TẠO KHÔNG QUOTE.
            String storedTable = foldUnquoted(meta, table);
            String storedSchema = schema == null
                    ? null : foldUnquoted(meta, schema);

            String tablePattern = escapePattern(meta, storedTable);
            String schemaPattern = storedSchema == null
                    ? null : escapePattern(meta, storedSchema);

            List<TableRef> candidates = new ArrayList<>();
            try (ResultSet rs = meta.getTables(
                    catalog, schemaPattern, tablePattern,
                    new String[] { "TABLE" })) {
                while (rs.next()) {
                    String actualCatalog = rs.getString("TABLE_CAT");
                    String actualSchema = rs.getString("TABLE_SCHEM");
                    String actualTable = rs.getString("TABLE_NAME");

                    // So sánh chính xác SAU khi tìm bằng pattern.
                    if (!storedTable.equals(actualTable)) {
                        continue;
                    }
                    if (storedSchema != null
                            && !storedSchema.equals(actualSchema)) {
                        continue;
                    }
                    if (catalog != null
                            && !catalog.equals(actualCatalog)) {
                        continue;
                    }

                    candidates.add(new TableRef(
                            actualCatalog, actualSchema, actualTable));
                }
            }

            List<TableInfo> result = new ArrayList<>();
            for (TableRef ref : candidates) {
                List<ColumnInfo> columns = columnsOf(meta, ref);
                result.add(new TableInfo(
                        ref, List.copyOf(columns)));
            }
            return List.copyOf(result);
        }
    }

    private static List<ColumnInfo> columnsOf(
            DatabaseMetaData meta, TableRef ref)
            throws SQLException {

        String schemaPattern = ref.schema() == null
                ? null : escapePattern(meta, ref.schema());
        String tablePattern = escapePattern(meta, ref.table());
        List<ColumnInfo> result = new ArrayList<>();

        try (ResultSet rs = meta.getColumns(
                ref.catalog(), schemaPattern, tablePattern, null)) {
            while (rs.next()) {
                if (!Objects.equals(
                        ref.catalog(), rs.getString("TABLE_CAT"))
                        || !Objects.equals(
                                ref.schema(), rs.getString("TABLE_SCHEM"))
                        || !ref.table().equals(
                                rs.getString("TABLE_NAME"))) {
                    continue;
                }
                result.add(new ColumnInfo(
                        rs.getString("COLUMN_NAME"),
                        rs.getInt("DATA_TYPE"),
                        rs.getString("TYPE_NAME"),
                        rs.getInt("ORDINAL_POSITION")));
            }
        }
        return result;
    }

    private static String foldUnquoted(
            DatabaseMetaData meta, String identifier)
            throws SQLException {
        if (meta.storesUpperCaseIdentifiers()) {
            return identifier.toUpperCase(Locale.ROOT);
        }
        if (meta.storesLowerCaseIdentifiers()) {
            return identifier.toLowerCase(Locale.ROOT);
        }
        return identifier;
    }

    private static String escapePattern(
            DatabaseMetaData meta, String name)
            throws SQLException {

        String escape = meta.getSearchStringEscape();
        if (escape == null || escape.length() != 1) {
            throw new SQLException(
                    "Unsupported metadata escape: [" + escape + "]");
        }
        char escapeChar = escape.charAt(0);
        if (escapeChar == '%' || escapeChar == '_') {
            throw new SQLException("Ambiguous metadata escape character");
        }

        StringBuilder pattern = new StringBuilder();
        for (int i = 0; i < name.length(); i++) {
            char ch = name.charAt(i);
            if (ch == '%' || ch == '_' || ch == escapeChar) {
                pattern.append(escapeChar);
            }
            pattern.append(ch);
        }
        return pattern.toString();
    }
}
```

Sử dụng:

```java
JdbcIdentifierInspector inspector =
        new JdbcIdentifierInspector(dataSource);

// PostgreSQL: tên được tạo KHÔNG QUOTE trong schema app_data.
var tables = inspector.inspectUnquotedTable(
        null, "app_data", "customer_account");

for (var table : tables) {
    var ref = table.ref();
    System.out.printf("catalog=%s, schema=%s, table=%s%n",
            ref.catalog(), ref.schema(), ref.table());

    for (var column : table.columns()) {
        System.out.printf("  #%d: %s [%s / JDBC %d]%n",
                column.position(), column.name(),
                column.sqlTypeName(), column.jdbcType());
    }
}
```

### Giới hạn của helper

1. `inspectUnquotedTable` dựa trên cờ cách **lưu unquoted identifier**. Với bảng được tạo bằng quote, phải tìm **tên đã lưu chính xác**, không tự `foldUnquoted`.
2. Một DB có thể lưu mixed case nhưng so sánh identifier không phân biệt case. Khi `storesUpperCaseIdentifiers` và `storesLowerCaseIdentifiers` đều không đúng, fallback giữ nguyên tên input **không thay thế việc khám phá metadata thực tế**.
3. `catalog` và `schema` có thể là `null`; kết quả có nhiều bảng cùng tên ở các schema khác nhau, nên method trả `List`.
4. Một số driver có quy tắc metadata escape khác ký tự đơn; helper **từ chối** thay vì đoán.
5. `getColumns` có thể công bố tên/type theo cách vendor-specific; hãy dùng `DATA_TYPE` và `TYPE_NAME` để kiểm tra nhưng đừng xem metadata như bản sao hoàn hảo của DDL.
6. Nếu DB có synonym hoặc view, cần logic riêng cho loại object; ở ví dụ chỉ tìm `TABLE`.
7. Metadata không tự kiểm tra quyền `SELECT`/`INSERT` thực tế và không bảo đảm table resolution khi SQL bỏ tên schema.

Không gọi inspector ở mỗi request để quyết định SQL; metadata I/O có thể tốn thời gian. Nên kiểm tra ở startup/diagnostics, giữ kết quả theo phạm vi rõ ràng và làm mới khi schema migration thay đổi.

## 10. Default schema, search path và truy vấn không ghi tên schema

Giả sử có hai bảng:

```text
sales.customer_account
archive.customer_account
```

Một câu SQL không qualification:

```sql
SELECT account_id
FROM customer_account
WHERE account_id = ?;
```

phụ thuộc **cách DB giải quyết tên trong session hiện tại**. Nó có thể trỏ tới schema `sales` trong một connection nhưng trỏ tới `archive` ở connection khác.

### PostgreSQL

PostgreSQL sử dụng `search_path` để xác định thứ tự tìm kiếm schema đối với các đối tượng không qualification. Có thể khảo sát:

```sql
SHOW search_path;
SELECT current_schema();

SELECT account_id
FROM sales.customer_account
WHERE account_id = ?;
```

`current_schema()` hữu ích nhưng không thay thế toàn bộ danh sách `search_path`. Nếu ứng dụng đổi search path trên một session được pool tái sử dụng, request sau có thể đọc nhầm schema nếu pool không reset.

### Oracle

Tên unquoted thường được fold về uppercase; schema hiện hành và quyền/synonym ảnh hưởng đến cách SQL tìm đối tượng. Không giả định `Connection.getSchema()` bằng username trong mọi tình huống hoặc rằng synonym được `getTables(..., {"TABLE"})` liệt kê như bảng thật.

### SQL Server

Định danh có thể gồm **database.schema.table**. Default schema của database user, `dbo`, quyền truy cập và case/collation có thể ảnh hưởng việc giải quyết tên. Nếu schema của ứng dụng được xác định rõ, một tên dạng `dbo.CustomerAccount` hoặc schema tương ứng thường ít mơ hồ hơn tên bảng trần.

### MySQL/MariaDB

Tên `shop_db.customer_account` thường là **database.table**; database thường được ánh xạ qua `TABLE_CAT` trong JDBC metadata. Không chuyển máy móc tên database vào `schemaPattern` theo cách dùng với PostgreSQL.

## 11. `Connection.setSchema()` và trạng thái trong pool

JDBC có API `Connection.setSchema(String)` để thay đổi schema hiện tại nếu DB/driver hỗ trợ:

```java
try (Connection connection = dataSource.getConnection()) {
    String initial = connection.getSchema();
    connection.setSchema("sales");

    // Thực hiện các truy vấn theo ngữ nghĩa schema của DB.
    // ... PreparedStatement, ResultSet ...

    connection.setSchema(initial);
}
```

Đây là ví dụ minh họa, **không phải công thức portable tuyệt đối**: một số driver không hỗ trợ `getSchema/setSchema`, `initial` có thể là `null` và một schema hiện hành đơn lẻ có thể không phản ánh search path nhiều phần.

### Rủi ro khi trả connection về pool

`Connection.close()` ở một pool thường trả **logical connection** về pool, không nhất thiết phá hủy session vật lý. Nếu request A thay đổi schema, session variable hoặc search path mà pool không reset đúng, request B mượn lại cùng kết nối có thể chạy SQL trên **schema của A**. Điều này đặc biệt nghiêm trọng ở hệ thống nhiều tenant.

Các chiến lược:

- Ưu tiên SQL qualification rõ ràng khi schema/bảng được biết trước và quyền truy cập cho phép.
- Nếu phải đổi schema theo request, thiết lập và reset context theo cơ chế pool/driver đã được kiểm thử.
- Không dựa vào `close()` tự reset tất cả session variables trừ khi pool bảo đảm.
- Với nhiều tenant hoặc quyền khác nhau, có thể dùng DataSource/pool tách biệt và chính sách ủy quyền rõ.
- Không đổi schema trên `Connection` do transaction manager khác sở hữu nếu chưa có hợp đồng session/transaction.
- Kiểm tra cả trường hợp **exception**, rollback và timeout để phát hiện session state bị giữ lại.

Đừng nhầm `setSchema` với việc tạo bảng mới hoặc di chuyển dữ liệu giữa các schema. Nó thay đổi **ngữ cảnh resolution**, không sao chép bảng.

## 12. Xây tên schema/bảng động: bảo mật và cú pháp là hai vấn đề

Định danh động **không** được bind qua `?`. Để dựng SQL an toàn, cần thực hiện đồng thời:

1. **Ủy quyền/allowlist:** chỉ cho phép bảng, schema đã được ứng dụng phê duyệt, không nhận trực tiếp tên từ input không tin cậy.
2. **Tạo cú pháp SQL hợp lệ:** quote từng thành phần identifier theo dialect; không đặt dấu quote quanh toàn bộ `schema.table`.
3. **Giữ dữ liệu qua placeholder:** mọi giá trị tìm kiếm/cập nhật vẫn bind bằng `PreparedStatement`.

Ví dụ helper chỉ chấp nhận **simple ASCII identifiers** và hai kiểu dấu bao đối xứng quen thuộc:

```java
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;

public static String quoteSimpleIdentifier(
        DatabaseMetaData meta, String approvedName)
        throws SQLException {

    if (approvedName == null
            || !approvedName.matches("[A-Za-z_][A-Za-z0-9_]*")) {
        throw new IllegalArgumentException(
                "Only approved simple identifiers are accepted");
    }

    String raw = meta.getIdentifierQuoteString();
    String quote = raw == null ? "" : raw.trim();
    String backtick = Character.toString((char) 96);

    if (!quote.equals("\"") && !quote.equals(backtick)) {
        throw new SQLFeatureNotSupportedException(
                "Quote style requires DB-specific support: [" + raw + "]");
    }

    return quote + approvedName.replace(quote, quote + quote) + quote;
}
```

Hàm này có giới hạn **chủ ý**, cần đọc kỹ:

- Nó nhận tên từ **allowlist/cấu hình đáng tin cậy**, không thay thế authorization. Regex chỉ giới hạn ký tự; một tên hợp cú pháp vẫn có thể tham chiếu dữ liệu cấm.
- Nó từ chối tên có dấu chấm, khoảng trắng, Unicode hoặc quote bên trong. Những tên này không mặc nhiên bất hợp lệ với DB; chỉ nằm ngoài phạm vi helper đơn giản.
- Dấu bao `[name]` của SQL Server có **ký tự mở/đóng khác nhau**; helper này không cố đoán. Dùng dialect adapter riêng nếu driver cung cấp kiểu quoting đó.
- Khi cần quote tên chứa ký tự quote, phải escape đúng quy tắc DBMS; ví dụ chỉ minh họa tên đơn giản.
- Nếu DB lưu bảng unquoted uppercase nhưng code quote tên lowercase, SQL có thể không tìm thấy bảng. **Tên được quote phải khớp tên thực tế**, không tự suy từ cách developer gõ.

**Ghép tên đúng:**

```java
// connection đã mở; hai tên lấy từ cấu hình/allowlist.
DatabaseMetaData meta = connection.getMetaData();
String schema = "sales";
String table = "customer_account";

String qualified = quoteSimpleIdentifier(meta, schema)
        + "." + quoteSimpleIdentifier(meta, table);
String sql = "SELECT account_id, email FROM " + qualified
        + " WHERE account_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, requestedId);
    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            // Ánh xạ kết quả.
        }
    }
}
```

Đoạn trên minh họa bên trong một method đã có `Connection` và `requestedId`. Chỉ có phần **định danh được xác minh** được ghép chuỗi, còn `requestedId` vẫn truyền bằng `setLong`. Với MySQL, phần tên trước dấu chấm có thể là **catalog/database**, và không phải DBMS nào cũng hỗ trợ schema qualification giống nhau.

**Không làm như sau:**

```java
// Sai: chèn thẳng input của người dùng vào phần cấu trúc SQL.
String sql = "SELECT * FROM " + request.getParameter("table");

// Sai: parameter marker không phải tên bảng.
String sql2 = "SELECT * FROM ? WHERE account_id = ?";
```

### Trường hợp partition theo tháng

Nếu ứng dụng phải truy vấn một trong ba bảng `event_2026_10`, `event_2026_11`, `event_2026_12`, hãy chọn tên từ danh sách cho phép trước khi ghép SQL:

```java
Set<String> permitted = Set.of(
        "event_2026_10", "event_2026_11", "event_2026_12");
if (!permitted.contains(requestedTable)) {
    throw new IllegalArgumentException("Unknown partition");
}

String qualified = quoteSimpleIdentifier(meta, schema)
        + "." + quoteSimpleIdentifier(meta, requestedTable);
String sql = "SELECT event_id FROM " + qualified
        + " WHERE event_id > ?";
```

`Set` là `java.util.Set`; ví dụ giả định các biến `meta`, `schema` và `requestedTable` do ứng dụng quản lý. Khi DB có partitioning native, **một bảng logic** và cơ chế partition pruning thường giúp giữ SQL ổn định hơn tự ghép tên bảng cho từng tháng.

## 13. Tên cột, alias và `ResultSetMetaData`

Vấn đề case không chỉ xảy ra với bảng. Ví dụ, một schema được tạo với quoted identifiers:

```sql
-- Ví dụ trên DB hỗ trợ dấu nháy đôi chuẩn SQL:
CREATE TABLE "CustomerAccount" (
    "AccountId" BIGINT PRIMARY KEY,
    "DisplayName" VARCHAR(120)
);

SELECT "AccountId", "DisplayName"
FROM "CustomerAccount";
```

Nếu repository viết `SELECT accountid, displayname FROM customeraccount`, tên không quote có thể bị fold và không khớp với tên quoted đã tạo. Cách giải quyết không phải thay ngẫu nhiên `getString("DisplayName")` thành `getString("displayname")`: trước hết **SQL phải tham chiếu đúng cột**.

### Alias cho phép ổn định hợp đồng mapping

```sql
-- DB dùng dấu nháy đôi chuẩn SQL.
SELECT "AccountId" AS "account_id",
       "DisplayName" AS "display_name"
FROM "CustomerAccount"
WHERE "AccountId" = ?;
```

```java
try (ResultSet rs = statement.executeQuery()) {
    while (rs.next()) {
        long id = rs.getLong("account_id");
        String displayName = rs.getString("display_name");
        // Ánh xạ thành DTO/record của ứng dụng.
    }
}
```

Label của cột trong `ResultSet` và **tên SQL gốc** có thể khác nhau. JDBC cung cấp `ResultSetMetaData.getColumnLabel(index)` và `getColumnName(index)` để xem:

```java
ResultSetMetaData metadata = rs.getMetaData();
for (int i = 1; i <= metadata.getColumnCount(); i++) {
    System.out.println(
            "label=" + metadata.getColumnLabel(i)
            + ", name=" + metadata.getColumnName(i));
}
```

Với câu SQL có alias, `getColumnLabel` thường phản ánh tên dùng để đọc trong kết quả, còn `getColumnName` nhằm cung cấp tên gốc nếu có thể. **Đừng coi hai phương thức luôn trả chuỗi giống nhau.** JDBC có quy tắc tra cứu label riêng; chúng không nhất thiết đồng nhất với toàn bộ quy tắc case-sensitive của SQL identifier trong DB.

Đối với `JOIN` nhiều bảng, nên dùng alias **duy nhất** cho từng cột cần ánh xạ. Nếu hai cột đều tên `id`, `rs.getLong("id")` có thể lấy cột đầu tiên hoặc gây nhầm; đặt `customer_id`, `order_id` rõ ràng sẽ an toàn hơn.

## 14. Quy trình chẩn đoán lỗi “table/column not found”

Khi một DAO đột nhiên báo lỗi tên bảng/cột, không nên sửa mọi SQL bằng `toUpperCase()` theo cảm tính. Hãy kiểm tra theo thứ tự:

| Bước | Câu hỏi | Cách xác minh |
| --- | --- | --- |
| 1 | Đúng DBMS, server, database và user chưa? | `getDatabaseProductName`, `getDatabaseProductVersion`, cấu hình DataSource |
| 2 | Schema migration đã chạy đúng nơi chưa? | Lịch sử migration và `getTables`/`getColumns` |
| 3 | Bảng được tạo unquoted hay quoted? | DDL thực tế và `TABLE_NAME` từ metadata |
| 4 | Quy tắc lưu chữ hoa/thường là gì? | `storesUpperCaseIdentifiers`, `storesLowerCaseIdentifiers` và test thực tế |
| 5 | Identifier đang được quote theo cú pháp nào? | `getIdentifierQuoteString`, SQL dialect/session config |
| 6 | Đúng catalog/schema chưa? | `TABLE_CAT`, `TABLE_SCHEM`, `getCatalog/getSchema` |
| 7 | SQL không qualification đang resolve tên ra sao? | Default schema, `search_path`, quyền và user |
| 8 | Metadata có nhầm `%`, `_` thành wildcard không? | `getSearchStringEscape` và exact-match kết quả |
| 9 | User có quyền với đối tượng không? | Chạy SQL có qualification bằng user ứng dụng |
| 10 | Pool có giữ schema của request trước không? | Test mượn, thay đổi, trả, mượn lại connection |

Các lỗi có thể có nguyên nhân rất khác nhau:

- **Bảng tồn tại nhưng SQL không thấy:** schema mặc định khác, quote sai case, quyền thiếu, table chưa ở database hiện tại.
- **Metadata thấy bảng nhưng SQL không chạy:** bảng ở schema khác, thiếu quyền, synonym/view khác loại, SQL mode của session không tương thích.
- **Metadata không thấy bảng:** sai catalog, schema pattern, wildcard chưa escape, driver không hỗ trợ metadata đầy đủ hoặc đối tượng không thuộc loại `TABLE`.
- **Truy vấn chạy nhưng trả dữ liệu lạ:** tên ngắn được resolve sang một bảng cùng tên ở schema khác; đây là rủi ro dữ liệu nghiêm trọng hơn một exception rõ ràng.

Không nên bắt mọi `SQLException` rồi tự thử lần lượt các schema mà ứng dụng có quyền. Cách đó có thể che giấu lỗi cấu hình hoặc vô tình đọc dữ liệu của tenant khác. Tốt hơn là **fail fast** với catalog/schema được xác định, ghi log bối cảnh không nhạy cảm và sửa đúng nguyên nhân.

## 15. Kiểm thử tích hợp đa DB/driver

Mock `DatabaseMetaData` giúp kiểm tra helper gọi đúng API, nhưng **không chứng minh hành vi của DBMS thật**. Các bài kiểm thử quan trọng cần chạy trên đúng sản phẩm/phiên bản DB và JDBC driver mục tiêu, lý tưởng từ pipeline CI.

| Tình huống | Chuẩn bị | Điều cần xác minh |
| --- | --- | --- |
| Bảng unquoted tên thường | Tạo `customer_account` | Tên được lưu và `SELECT` đúng theo DB |
| Bảng unquoted viết mixed case | Tạo `CustomerAccount` không quote | DB fold/lưu tên đúng cờ metadata đã báo |
| Bảng quoted mixed case | Tạo `"CustomerAccount"` nếu DB hỗ trợ | Tên quoted khớp case, sai case không bị đoán |
| Cột quoted đặc biệt | Tạo `"AccountId"` | Query và alias/`getColumnLabel` đúng |
| Tên bảng chứa underscore | Có `audit_log` và tên gần giống | Escape metadata pattern không trả false positive |
| Tên có literal `%` | Quoted table chứa `%` nếu DB hỗ trợ | `getSearchStringEscape` và exact-match tìm đúng |
| Hai schema có cùng bảng | Tạo `sales.customer_account`, `archive.customer_account` | Qualification chọn đúng bảng |
| Default schema khác nhau | Hai connections/session có context khác | Không nhầm bảng khi SQL không qualification |
| Catalog vs schema | MySQL, SQL Server hoặc DB tương ứng | `TABLE_CAT`/`TABLE_SCHEM` đúng thực tế |
| Quyền khác nhau | Hai database users | Metadata và SQL thực tế được kiểm tra riêng |
| Đổi schema với connection pool | Mượn A, đổi context, trả, mượn B | Không rò rỉ schema A sang B |
| Tên bảng từ client không hợp lệ | Gửi tên ngoài allowlist | Bị từ chối **trước khi dựng SQL** |
| Nâng cấp DB/driver | Chạy lại cùng test suite | Phát hiện thay đổi naming/case/metadata |

### Test chỉ đọc metadata

Giả sử migration của môi trường test tạo **bảng không quote** với tên `customer_account`. Có thể kiểm tra thông tin và so sánh chính xác:

```java
try (Connection connection = testDataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    String expectedName = "customer_account";
    if (meta.storesUpperCaseIdentifiers()) {
        expectedName = expectedName.toUpperCase(Locale.ROOT);
    } else if (meta.storesLowerCaseIdentifiers()) {
        expectedName = expectedName.toLowerCase(Locale.ROOT);
    }

    String pattern = exactMetadataPattern(meta, expectedName);
    boolean found = false;

    try (ResultSet rs = meta.getTables(
            connection.getCatalog(), null,
            pattern, new String[] { "TABLE" })) {
        while (rs.next()) {
            if (expectedName.equals(rs.getString("TABLE_NAME"))) {
                found = true;
                System.out.println(
                        "Schema: " + rs.getString("TABLE_SCHEM"));
            }
        }
    }

    if (!found) {
        throw new AssertionError(
                "Expected table was not reported: " + expectedName);
    }
}
```

Đoạn minh họa giả định đã import các lớp `java.sql`, `java.util.Locale` và có helper `exactMetadataPattern` ở phần 7. Trong một môi trường có nhiều schema, test này nên được **bổ sung kiểm tra catalog/schema chính xác** thay vì chỉ tìm tên bảng. Nếu `storesUpperCaseIdentifiers`/`storesLowerCaseIdentifiers` không phản ánh đủ quy tắc DB, phải xem DDL và tên từ metadata theo môi trường thật.

Sau test metadata, cần chạy ít nhất một câu **`SELECT` có qualification** và bind tham số bằng `PreparedStatement` để xác minh quyền truy cập và cách resolve tên thật. Các bài tạo schema/bảng hoặc thay đổi search path nên chạy trong **database/schema test riêng**, không làm trên production. Không mặc định mọi DDL hoặc trạng thái session đều được rollback giống dữ liệu.

### Kiểm tra nhất quán khi dùng connection pool

Một bài kiểm thử có thể:

1. Mượn connection, ghi nhận schema và catalog ban đầu.
2. Đổi schema bằng cơ chế pool/driver được hỗ trợ.
3. Đóng logical connection và mượn lại một connection từ pool.
4. Chạy SQL unqualified và qualified lên bảng **chỉ dùng trong test**.
5. Xác minh schema được reset hoặc hành vi session đúng theo hợp đồng pool.
6. Lặp tình huống khi câu SQL ném `SQLException` và khi transaction rollback.

Không khẳng định test luôn mượn lại **cùng physical connection** nếu pool có nhiều kết nối; muốn quan sát chính xác cần cấu hình test pool và công cụ theo dõi được phép trong môi trường thử nghiệm.

## 16. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Luôn chuyển tên bảng sang uppercase | PostgreSQL/quoted name có thể sai | Kiểm tra metadata và cách tạo tên thực tế |
| Luôn chuyển tên bảng sang lowercase | Oracle unquoted có thể dùng uppercase | Giữ convention và adapter theo DB |
| Luôn bao tên bằng dấu `"..."` | Một số SQL mode/dialect khác cách quote | Dùng quote string/dialect đã xác minh |
| Quote cả `schema.table` làm một identifier | DB coi dấu chấm là một phần tên | Quote từng thành phần riêng |
| Dùng `?` để thay tên table/column | Không phải vai trò của parameter marker | Chỉ bind giá trị; xác thực cấu trúc SQL riêng |
| Ghép thẳng tên bảng từ HTTP input | SQL injection hoặc vượt quyền truy cập | Allowlist và authorization |
| Truyền tên có `_` vào `getTables` không escape | Search pattern có thể khớp tên khác | `getSearchStringEscape` và exact-match |
| Gọi `getTables` không giới hạn schema rồi lấy dòng đầu | Có thể chọn sai bảng ở schema khác | Chỉ định catalog/schema và kiểm tra mọi kết quả |
| Coi catalog và schema giống nhau | MySQL/PostgreSQL/SQL Server không đồng nhất | Mapping theo DBMS |
| Tin `getSchema` phản ánh toàn bộ `search_path` | SQL không qualification có thể trỏ nơi khác | Quan sát session và dùng qualification |
| Thay đổi schema rồi trả connection về pool mà không reset | Có thể rò rỉ context giữa request/tenant | Quản lý session reset và test pool reuse |
| Chỉ kiểm tra metadata, không chạy SQL | Thiếu quyền, synonym hoặc SQL mode vẫn gây lỗi | Test SQL thật bằng user ứng dụng |
| Tên cột trùng nhau trong JOIN và dùng label không rõ | Ánh xạ `ResultSet` sai cột | Đặt alias rõ ràng, kiểm tra `getColumnLabel` |
| Dùng H2 mode tương thích thay mọi DB đích | Khác case, quote, schema, SQL dialect | Integration test trên DB/driver thật |
| Dùng metadata introspection ở mỗi request | Tốn I/O, chậm, khó cache | Kiểm tra ở startup/migration/diagnostics |

## 17. Bài tập tự kiểm tra

**Bài 1 — Định danh và tham số.** Trong `SELECT id FROM customer_account WHERE email = ?`, thành phần nào được bind bằng `setString`? Có thể dùng `?` thay tên bảng không?

**Đáp án:** Dấu `?` đại diện cho giá trị email, không phải identifier. Tên bảng phải được viết trong SQL hoặc xây từ danh sách cho phép và quote hợp lệ.

**Bài 2 — PostgreSQL và chữ hoa.** Bảng được tạo bằng `CREATE TABLE CustomerAccount (...)` không quote. Tại sao `FROM "CustomerAccount"` có thể thất bại nhưng `FROM customeraccount` thành công?

**Đáp án:** PostgreSQL thường gấp tên unquoted về chữ thường; tên quoted có thể được phân biệt case và yêu cầu khớp chính xác.

**Bài 3 — Oracle.** Một bảng được tạo không quote với tên `customer_account`. Metadata `TABLE_NAME` có thể trả gì trong Oracle thông thường?

**Đáp án:** Thường là `CUSTOMER_ACCOUNT`. Phải phân biệt với đối tượng được tạo bằng quote và kiểm tra metadata trên DB thật.

**Bài 4 — MySQL.** Vì sao không nên mặc định truyền `schemaPattern = "shop_db"` vào `getTables` để tìm bảng thuộc database `shop_db`?

**Đáp án:** MySQL thường ánh xạ database thành catalog trong JDBC metadata; phải kiểm tra `TABLE_CAT`, `TABLE_SCHEM` và driver.

**Bài 5 — Wildcard.** Tên bảng `audit_log` được truyền làm pattern vào `getTables`. Rủi ro là gì?

**Đáp án:** Ký tự `_` có thể được diễn giải là wildcard một ký tự. Dùng `getSearchStringEscape` và so sánh tên thực tế trong `TABLE_NAME`.

**Bài 6 — Pool và schema.** Request A đổi schema thành `sales` rồi trả connection. Request B mượn lại và truy vấn `customer_account`. Rủi ro nào có thể xảy ra?

**Đáp án:** Nếu session không được reset, B có thể truy cập nhầm bảng trong schema `sales`. Cần cấu hình reset, qualification hoặc tách DataSource theo chính sách.

**Bài 7 — Quote từng phần.** Vì sao `"sales.customer_account"` khác `"sales"."customer_account"` ở DB dùng quoted identifiers chuẩn?

**Đáp án:** Dạng đầu là **một identifier** chứa dấu chấm; dạng sau gồm **hai identifier** là schema và table.

**Bài 8 — Kiểm soát tên động.** API nhận `tableName` trực tiếp từ client. Chỉ gọi helper quote tên có đủ bảo mật không?

**Đáp án:** Không. Quoting giúp tạo cú pháp identifier nhưng không cấp quyền; cần allowlist/authorization và không ghép dữ liệu người dùng vào SQL.

**Bài 9 — Metadata thấy bảng nhưng SQL không thấy.** `getTables` trả bảng ở `archive`, nhưng `SELECT * FROM customer_account` báo không tồn tại. Cần kiểm tra gì?

**Gợi ý:** Schema mặc định/search path, quyền, catalog, quoting và cách SQL không qualification được resolve; thử `archive.customer_account` theo dialect thích hợp.

**Bài 10 — H2 và production.** Vì sao test xanh trên H2 chưa chứng minh repository chạy đúng trên SQL Server và PostgreSQL?

**Đáp án:** Quy tắc chữ hoa/thường, schema/catalog, quoting, collation, SQL dialect và JDBC driver khác nhau. Cần integration test trên từng DBMS mục tiêu.

## Tổng kết

Để **kiểm tra quy tắc định danh, chữ hoa chữ thường và schema** trong JDBC đa hệ quản trị, phải phân biệt **unquoted/quoted identifiers**, đọc các cờ case và quoting qua `DatabaseMetaData`, đồng thời xác minh tên bảng/cột thực tế qua `getTables` và `getColumns`. Không coi catalog với schema là một, không coi `%`/`_` trong metadata pattern là ký tự thường khi chưa escape, và không giả định SQL không qualification luôn trỏ đúng schema. Khi cần tạo SQL động, chỉ dùng identifier từ cấu hình/allowlist đáng tin cậy, quote **từng thành phần** theo dialect và luôn bind các **giá trị dữ liệu** qua `PreparedStatement`. Cuối cùng, kiểm thử trên đúng DBMS/driver, bao gồm trạng thái session khi connection pool tái sử dụng kết nối, để tránh lỗi “table not found”, lỗi chữ hoa/chữ thường và nguy cơ truy cập nhầm dữ liệu.
