# Xử lý mẫu tìm kiếm và ký tự thoát khi tra cứu siêu dữ liệu trong JDBC

Ứng dụng Java có thể dùng `DatabaseMetaData` để tìm bảng, cột, schema, procedure và các đối tượng khác trong cơ sở dữ liệu quan hệ. Các API này thường nhận tham số có tên `tableNamePattern`, `schemaPattern` hay `columnNamePattern`. Dù trông giống tên đối tượng thông thường, những tham số đó là **mẫu tìm kiếm (search pattern)**, không nhất thiết là tên chính xác.

Ví dụ, khi muốn kiểm tra bảng `order_2026` có tồn tại hay không, truyền thẳng `"order_2026"` vào `getTables(...)` có thể trả cả bảng `orderX2026` vì ký tự gạch dưới `_` trong pattern đại diện cho **một ký tự bất kỳ**. Nếu tên bảng chứa `%`, kết quả còn có thể rộng hơn dự kiến.

Bài học thuộc chương **Siêu dữ liệu** của module JDBC. Nội dung hướng dẫn sử dụng đúng `%`, `_` và `DatabaseMetaData.getSearchStringEscape()`; phân biệt tên đối tượng chính xác với pattern; kiểm soát catalog/schema, chữ hoa chữ thường và tài nguyên `ResultSet`; đồng thời xây dựng những hàm tra cứu có thể dùng với `DataSource` trong ứng dụng Java.

## 1. Pattern trong `DatabaseMetaData` là gì?

Nhiều phương thức metadata tìm đối tượng theo quy tắc **tương tự SQL `LIKE`**. Hai ký tự đặc biệt quan trọng:

| Ký tự | Ý nghĩa trong search pattern | Ví dụ | Phạm vi kết quả |
|---|---|---|---|
| `%` | Đại diện cho **không hoặc nhiều ký tự** | `order%` | `order`, `orders`, `order_2026`, ... |
| `_` | Đại diện cho **đúng một ký tự** | `order_2026` | `order_2026`, `orderX2026`, `orderA2026`, ... |
| Ký tự thường | Khớp chính ký tự đó, theo quy tắc của DB/driver | `orders` | Tên tương ứng với các ký tự được chỉ định |
| Ký tự thoát + `%` hoặc `_` | Yêu cầu khớp **ký tự % hoặc _ theo nghĩa đen** | `order\_2026` nếu escape là `\` | Tên có gạch dưới thật tại vị trí đó |

Đây là **search pattern của JDBC**, không phải biểu thức chính quy Java. `.*`, `^` hay `$` không mang ý nghĩa regex trong pattern JDBC. Dấu `*` cũng không phải ký tự đại diện chuẩn của JDBC metadata.

### Ví dụ dễ nhầm

Giả sử database có các bảng:

```text
order_2026
orderX2026
orders
order%archive
```

Khi driver dùng ký tự thoát `\`, các mẫu có ý nghĩa:

| Pattern truyền vào `getTables` | Điều được yêu cầu |
|---|---|
| `order%` | Tên bắt đầu bằng `order` |
| `order_2026` | `order` + một ký tự bất kỳ + `2026` |
| `order\_2026` | Tên có **dấu gạch dưới thật**, chính xác `order_2026` |
| `order\%%` | Tên bắt đầu bằng chuỗi thật `order%`, sau đó có thể thêm ký tự |
| `order\%archive` | Chính xác tên `order%archive` |

Ví dụ trong bảng **giả sử** escape là `\`. Không nên tự điền ký tự này cho mọi DBMS, vì JDBC cung cấp phương thức để hỏi driver phải dùng escape nào.

**Quy tắc cốt lõi:** khi người dùng nhập **tên đối tượng chính xác**, mọi ký tự wildcard nằm trong tên phải được thoát. Chỉ giữ `%` hoặc `_` dưới nghĩa wildcard khi chức năng thực sự chủ ý tìm theo mẫu.

## 2. Lấy ký tự thoát từ `getSearchStringEscape()`

`DatabaseMetaData.getSearchStringEscape()` trả về chuỗi ký tự mà driver quy định để thoát ký tự đặc biệt trong **metadata search pattern**.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class MetadataEscapeDemo {
    private MetadataEscapeDemo() {
    }

    public static void showEscape(DataSource dataSource)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();

            String escape = metadata.getSearchStringEscape();
            System.out.println("Metadata search escape: [" + escape + "]");
        }
    }
}
```

Nhiều driver trả về chuỗi chứa một ký tự backslash (`\`), nhưng đó là **ví dụ**, không phải quy định bắt buộc cho tất cả driver.

Nếu chuỗi escape có giá trị `\`, một tên bảng Java `"order_2026"` cần được biểu diễn thành pattern chứa **một backslash thật trước dấu gạch dưới**. Trong source Java, ký tự backslash phải được viết thành `\\` trong string literal:

```java
String tableNamePattern = "order\\_2026";
// Chuỗi runtime chứa: order\_2026
```

Đừng nhầm **escape trong source Java** với **escape khi tìm metadata**:

- `"\\"` trong Java là một ký tự backslash runtime.
- `"order\\_2026"` trong Java chứa `order` + backslash + `_2026`; JDBC nhận backslash theo quy ước của driver.

Trong code thực tế, nên **lấy escape từ metadata rồi xây pattern bằng hàm**, thay vì tự viết các string literal chứa backslash và hy vọng chúng đúng với mọi database.

## 3. Hàm tạo pattern cho một tên chính xác

Nếu input là **tên literal**, cần xử lý tối thiểu ba loại chuỗi con:

1. Chính chuỗi escape do driver cung cấp, nếu nó xuất hiện trong tên.
2. Dấu `%`.
3. Dấu `_`.

Thứ tự xử lý rất quan trọng: nếu dùng nhiều lần `String.replace(...)` không cẩn thận, lần replace sau có thể thoát lại những escape vừa được thêm vào ở lần trước.

Hàm dưới đây duyệt từ trái sang phải; nếu gặp chính chuỗi escape trong tên thì ghi **hai lần escape**, còn nếu gặp ký tự wildcard thì thêm escape trước nó.

```java
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Objects;

public final class MetadataPatterns {
    private MetadataPatterns() {
    }

    /**
     * Chuyển tên identifier theo nghĩa đen thành search pattern
     * theo escape string do DatabaseMetaData cung cấp.
     */
    public static String literal(String identifier, String escape)
            throws SQLException {

        Objects.requireNonNull(identifier, "identifier");

        // Trường hợp driver không cung cấp escape hữu dụng.
        if (escape == null || escape.isEmpty()) {
            if (identifier.indexOf('%') >= 0
                    || identifier.indexOf('_') >= 0) {
                throw new SQLFeatureNotSupportedException(
                        "Driver không cung cấp escape cho metadata pattern");
            }
            return identifier;
        }

        StringBuilder result = new StringBuilder();

        for (int i = 0; i < identifier.length();) {
            if (identifier.startsWith(escape, i)) {
                // Một ký tự/chuỗi escape thuộc tên thật:
                // thoát chính chuỗi escape đó.
                result.append(escape).append(escape);
                i += escape.length();
                continue;
            }

            int cp = identifier.codePointAt(i);
            if (cp == '%' || cp == '_') {
                result.append(escape);
            }
            result.appendCodePoint(cp);
            i += Character.charCount(cp);
        }

        return result.toString();
    }

    /**
     * Muốn tìm tên bắt đầu bằng tiền tố literal:
     * chỉ ký tự % thêm vào cuối đóng vai trò wildcard.
     */
    public static String startsWith(String prefix, String escape)
            throws SQLException {
        return literal(prefix, escape) + "%";
    }
}
```

Ví dụ, nếu `escape` đúng bằng `"\\"`:

```java
String escape = "\\";

System.out.println(MetadataPatterns.literal("order_2026", escape));
// order\_2026

System.out.println(MetadataPatterns.literal("order%archive", escape));
// order\%archive

System.out.println(MetadataPatterns.startsWith("order_", escape));
// order\_%

System.out.println(MetadataPatterns.literal("team\\metrics", escape));
// team\\metrics   (hai backslash runtime, thể hiện escape của chính nó)
```

**Lưu ý về tính tương thích:** một số driver hoặc DBMS có khác biệt trong cách áp dụng escape cho chính ký tự escape, đặc biệt nếu chuỗi escape không phải ký tự đơn. Hãy kiểm thử hàm với metadata thật của hệ quản trị đang dùng. Trường hợp driver không cung cấp escape, hàm không âm thầm chuyển wildcard từ input thành tìm kiếm diện rộng; với tên không chứa wildcard, nó vẫn có thể truyền tên trực tiếp.

Đây là một phép biến đổi **mẫu tìm kiếm**, không phải hàm escape SQL để xây câu truy vấn động. Không dùng kết quả của `MetadataPatterns.literal(...)` thay cho bind parameter hoặc cơ chế quote identifier khi tự viết SQL.

## 4. Phương thức nào nhận pattern, phương thức nào nhận tên chính xác?

Không phải mọi tham số kiểu `String` của `DatabaseMetaData` đều có ý nghĩa giống nhau.

| Phương thức | Tham số pattern | Tham số không phải pattern |
|---|---|---|
| `getTables(catalog, schemaPattern, tableNamePattern, types)` | `schemaPattern`, `tableNamePattern` | `catalog`, `types` |
| `getColumns(catalog, schemaPattern, tableNamePattern, columnNamePattern)` | `schemaPattern`, `tableNamePattern`, `columnNamePattern` | `catalog` |
| `getProcedures(catalog, schemaPattern, procedureNamePattern)` | `schemaPattern`, `procedureNamePattern` | `catalog` |
| `getFunctions(catalog, schemaPattern, functionNamePattern)` | `schemaPattern`, `functionNamePattern` | `catalog` |
| `getProcedureColumns(catalog, schemaPattern, procedureNamePattern, columnNamePattern)` | Ba tham số có hậu tố `Pattern` | `catalog` |
| `getSchemas(catalog, schemaPattern)` | `schemaPattern` | `catalog` |
| `getPrimaryKeys(catalog, schema, table)` | **Không có tham số pattern** | `catalog`, `schema`, `table` |
| `getIndexInfo(catalog, schema, table, unique, approximate)` | **Không có tham số pattern** | `catalog`, `schema`, `table` |
| `getImportedKeys(catalog, schema, table)` | **Không có tham số pattern** | `catalog`, `schema`, `table` |

**Chỉ thoát wildcard ở những tham số thực sự là pattern.** Chẳng hạn, `getPrimaryKeys(null, "public", "order_2026")` nhận tên bảng chính xác; truyền `"order\\_2026"` vào tham số `table` có thể làm driver đi tìm tên thực sự chứa backslash.

Tương tự, tham số `types` của `getTables` là mảng loại đối tượng như `"TABLE"`, `"VIEW"`; nó không phải chuỗi `LIKE`. Kiểm tra danh sách loại bảng mà driver hỗ trợ bằng `getTableTypes()` nếu cần, vì các DBMS có thể báo những loại riêng.

### Quy tắc `null` và chuỗi rỗng

Đối với nhiều phương thức metadata, JDBC quy định ý nghĩa đặc biệt:

- `catalog == null`: không dùng catalog để thu hẹp tìm kiếm.
- `catalog.equals("")`: tìm các đối tượng **không có catalog**, khi driver/DB có khái niệm phù hợp.
- `schemaPattern == null`: không dùng schema để thu hẹp tìm kiếm.
- `schemaPattern.equals("")`: tìm các đối tượng **không có schema**.
- Với tham số pattern khác, `null` thường có nghĩa không áp dụng điều kiện thu hẹp theo tên đó; `""` là pattern rỗng, không giống `"%"`.

Đọc hợp đồng của **từng phương thức** trước khi áp dụng một quy tắc cho mọi tham số. Đặc biệt, `getPrimaryKeys(...)` nhận `schema` và `table` theo nghĩa tên, **không phải `schemaPattern`/`tableNamePattern`**.

Ví dụ, `getTables(null, null, "%", null)` có thể duyệt rất nhiều loại bảng và view mà ứng dụng có quyền xem; trong khi `getTables(null, "public", "orders", new String[]{"TABLE"})` giới hạn hơn nhưng `orders` vẫn có thể chứa wildcard nếu tên thực tế khác. Khi ứng dụng chỉ cần một bảng, nên truyền cả schema đã biết, loại bảng và **tên đã escape**.

## 5. Ví dụ đầy đủ: kiểm tra bảng có tồn tại theo tên chính xác

Ví dụ sau dùng `DataSource`, `DatabaseMetaData`, `getTables(...)` và hàm `MetadataPatterns.literal(...)` ở phần 3. Điều quan trọng là **tên schema và bảng đều được coi như literal**, và sau khi nhận `ResultSet`, mã kiểm tra chính xác tên trả về để tránh kết quả rộng hoặc khác quy ước.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class TableMetadataLookup {
    private TableMetadataLookup() {
    }

    /**
     * catalog = null hoặc schema = null nghĩa là không giới hạn
     * theo thành phần tương ứng.
     *
     * tableName phải là tên thực tế như DB lưu trong metadata;
     * không phải wildcard pattern do người dùng tự nhập.
     */
    public static boolean existsTable(
            DataSource dataSource,
            String catalog,
            String schema,
            String tableName) throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();
            String escape = meta.getSearchStringEscape();

            String schemaPattern = schema == null
                    ? null
                    : MetadataPatterns.literal(schema, escape);

            String tablePattern =
                    MetadataPatterns.literal(tableName, escape);

            String[] types = {"TABLE"};

            try (ResultSet rs = meta.getTables(
                    catalog, schemaPattern, tablePattern, types)) {

                while (rs.next()) {
                    String foundCatalog = rs.getString("TABLE_CAT");
                    String foundSchema = rs.getString("TABLE_SCHEM");
                    String foundTable = rs.getString("TABLE_NAME");

                    boolean matchingCatalog = catalog == null
                            || catalog.equals(foundCatalog);
                    boolean matchingSchema = schema == null
                            || schema.equals(foundSchema);

                    if (matchingCatalog && matchingSchema
                            && tableName.equals(foundTable)) {
                        return true;
                    }
                }
            }
        }
        return false;
    }
}
```

Dùng như sau, sau khi cung cấp `dataSource` đã cấu hình đúng driver/DB:

```java
boolean exists = TableMetadataLookup.existsTable(
        dataSource,
        null,           // Không giới hạn catalog
        "public",       // Schema thực tế (ví dụ PostgreSQL)
        "order_2026");  // Tìm dấu gạch dưới thật
```

**Vì sao phải kiểm tra lại `TABLE_NAME`?** Pattern theo `LIKE` có thể chịu quy tắc so khớp/collation của database và đặc điểm driver. Kiểm tra lại kết quả theo hợp đồng ứng dụng giúp tránh trả `true` cho tên khác. Ví dụ trên yêu cầu **khớp tên metadata phân biệt hoa/thường** bằng `String.equals()`. Nếu ứng dụng muốn nhận tên theo cách không phân biệt hoa/thường, phải xác định rõ chính sách và quy tắc lưu identifier của DBMS thay vì thay bằng `equalsIgnoreCase` một cách tùy tiện.

Cũng cần hiểu đây là một **phép kiểm tra snapshot metadata tại thời điểm tra cứu**. Bảng có thể được thêm/xóa/đổi tên sau đó bởi connection khác. Không dùng `existsTable` để thay thế xử lý `SQLException` của thao tác SQL thực tế hay làm cơ chế đồng bộ DDL.

## 6. Tìm theo tiền tố: thoát phần literal, giữ wildcard có chủ đích

Nhiều giao diện quản trị cần liệt kê tất cả bảng bắt đầu bằng `"audit_"`, ví dụ `audit_events` và `audit_2026`. Nếu truyền `"audit_%"` trực tiếp, dấu `_` sẽ khớp **bất kỳ một ký tự**, dẫn tới trả cả `auditXlogs`.

Muốn “bắt đầu bằng chuỗi thật `audit_`”, hãy dùng:

```java
String escape = meta.getSearchStringEscape();
String tableNamePattern =
        MetadataPatterns.startsWith("audit_", escape);

// Nếu escape = "\\", runtime pattern sẽ là:
// audit\_%
```

Hàm `startsWith` thoát `_` trong tiền tố và **chỉ thêm một dấu `%` ở cuối** để chủ đích tìm tiếp những ký tự bất kỳ.

Mẫu hàm liệt kê tên bảng:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class TablePrefixSearch {
    private TablePrefixSearch() {
    }

    public static List<String> find(
            DataSource source, String schema, String literalPrefix)
            throws SQLException {

        List<String> found = new ArrayList<>();

        try (Connection connection = source.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();
            String escape = meta.getSearchStringEscape();

            String schemaPattern = schema == null
                    ? null
                    : MetadataPatterns.literal(schema, escape);
            String tablePattern =
                    MetadataPatterns.startsWith(literalPrefix, escape);

            try (ResultSet rs = meta.getTables(
                    null, schemaPattern, tablePattern,
                    new String[]{"TABLE"})) {

                while (rs.next()) {
                    String actualSchema = rs.getString("TABLE_SCHEM");
                    String actualName = rs.getString("TABLE_NAME");

                    if ((schema == null || schema.equals(actualSchema))
                            && actualName != null
                            && actualName.startsWith(literalPrefix)) {
                        found.add(actualName);
                    }
                }
            }
        }
        return found;
    }
}
```

Một ví dụ gọi trong ứng dụng:

```java
List<String> names = TablePrefixSearch.find(
        dataSource, "public", "audit_");
```

`List<String>` ở đây chỉ chứa tên bảng, nên khi tìm trong **nhiều schema**, có thể gặp các tên trùng nhau. Nếu ứng dụng cần phân biệt đầy đủ, hãy trả cấu trúc chứa `TABLE_CAT`, `TABLE_SCHEM` và `TABLE_NAME` thay vì chỉ `TABLE_NAME`.

**Không đặt `clearParameters()`, `getMoreResults()` hoặc `Statement.executeQuery()` vào cách giải quyết này:** đây là thao tác của `DatabaseMetaData` và `ResultSet`; metadata API tự phát truy vấn thích hợp thông qua driver. Khi dùng `PreparedStatement` để truy vấn dữ liệu nghiệp vụ, vẫn dùng bind parameter như bình thường.

## 7. Lọc cột với `getColumns()`: cần thoát cả tên bảng lẫn tên cột

`DatabaseMetaData.getColumns(catalog, schemaPattern, tableNamePattern, columnNamePattern)` hỗ trợ pattern ở ba tham số sau catalog.

Giả sử muốn tra loại SQL của cột `created_at` trong bảng `order_2026`. Nếu truyền thẳng hai tên đó, mỗi dấu gạch dưới đều bị coi là wildcard. Đúng hơn:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void showColumnType(
        Connection connection,
        String schema,
        String table,
        String column) throws SQLException {

    DatabaseMetaData meta = connection.getMetaData();
    String escape = meta.getSearchStringEscape();

    String schemaPattern =
            MetadataPatterns.literal(schema, escape);
    String tablePattern =
            MetadataPatterns.literal(table, escape);
    String columnPattern =
            MetadataPatterns.literal(column, escape);

    try (ResultSet rs = meta.getColumns(
            null, schemaPattern, tablePattern, columnPattern)) {

        while (rs.next()) {
            String foundTable = rs.getString("TABLE_NAME");
            String foundColumn = rs.getString("COLUMN_NAME");
            String foundSchema = rs.getString("TABLE_SCHEM");

            if (!schema.equals(foundSchema)
                    || !table.equals(foundTable)
                    || !column.equals(foundColumn)) {
                continue;
            }

            int jdbcType = rs.getInt("DATA_TYPE");
            String databaseType = rs.getString("TYPE_NAME");
            int position = rs.getInt("ORDINAL_POSITION");

            System.out.println(
                    foundColumn + " at #" + position
                    + ": JDBC type=" + jdbcType
                    + ", DB type=" + databaseType);
        }
    }
}
```

Đoạn trên là một phương thức tĩnh có thể đặt trong một lớp Java sử dụng `MetadataPatterns` đã định nghĩa. Mọi `ResultSet` đều được đóng bằng `try-with-resources`; `Connection` do bên gọi sở hữu và phải được đóng sau đó. Dữ liệu có thể chứa nhiều cột cùng tên từ nhiều bảng/schema nếu không thu hẹp đúng các tham số pattern.

Để tìm **tất cả cột của bảng**, có thể dùng `columnNamePattern = "%"` khi muốn rõ ràng một wildcard bất kỳ; hoặc dùng `null` khi hợp đồng của phương thức cho phép không thu hẹp tên cột. Không nên truyền `MetadataPatterns.literal("%", escape)` vì việc đó có nghĩa tìm một **tên cột chứa ký tự % thật**, không phải mọi cột.

## 8. Catalog, schema và identifier case: lý do escape đúng vẫn có thể không tìm thấy

### 8.1. Catalog không phải schema

Trong JDBC, `catalog` và `schema` đại diện những mức định danh khác nhau, nhưng cách DBMS sử dụng phụ thuộc hệ quản trị.

- **PostgreSQL:** database thường gắn với catalog trong metadata; schema có thể là `public` hoặc một schema ứng dụng.
- **MySQL:** tên database thường được trình bày dưới dạng catalog, còn schema trong metadata có thể không được sử dụng tương tự PostgreSQL, tùy driver và cấu hình.
- **Oracle:** tên schema thường liên hệ với user sở hữu đối tượng; quy tắc catalog có thể khác.

Không nên sao chép mặc định `catalog=null, schema="public"` sang mọi hệ quản trị. Cần xác định catalog/schema thực tế mà driver trả về:

```java
DatabaseMetaData meta = connection.getMetaData();

try (ResultSet rs = meta.getTables(
        null, null, "order%", new String[]{"TABLE"})) {

    while (rs.next()) {
        System.out.println(
                "catalog=" + rs.getString("TABLE_CAT")
                + ", schema=" + rs.getString("TABLE_SCHEM")
                + ", table=" + rs.getString("TABLE_NAME"));
    }
}
```

Đoạn này cố ý dùng wildcard rộng để **khám phá** khi phát triển; trong request thông thường nên giới hạn phạm vi tra cứu. Không suy rằng `catalog=null` nhất định nghĩa là “database hiện tại” ở mọi driver: về hợp đồng metadata, nó thường chỉ mang nghĩa không dùng catalog để lọc.

### 8.2. Tên viết hoa, tên viết thường và tên được quote

Cùng SQL `CREATE TABLE Orders (...)` có thể được DBMS lưu trong metadata thành `ORDERS`, `orders` hoặc giá trị khác theo quy tắc của hệ quản trị. Tên được trích dẫn bằng dấu quote identifier như `"Orders"` trên PostgreSQL/Oracle lại có thể giữ kiểu chữ khác tên không quote.

JDBC cho phép hỏi driver về quy tắc lưu identifier:

```java
DatabaseMetaData meta = connection.getMetaData();

System.out.println(
        "storesUpperCaseIdentifiers="
        + meta.storesUpperCaseIdentifiers());

System.out.println(
        "storesLowerCaseIdentifiers="
        + meta.storesLowerCaseIdentifiers());

System.out.println(
        "storesMixedCaseIdentifiers="
        + meta.storesMixedCaseIdentifiers());

System.out.println(
        "storesMixedCaseQuotedIdentifiers="
        + meta.storesMixedCaseQuotedIdentifiers());
```

Những API này mô tả khả năng và quy tắc của database cho **tên định danh**. Để tra cứu chính xác, hãy dùng **tên theo cách nó được lưu/hiển thị trong metadata**. Không tự động gọi `toUpperCase()` hoặc `toLowerCase()` trên mọi identifier, đặc biệt nếu database hỗ trợ tên quoted phân biệt kiểu chữ.

### 8.3. `getIdentifierQuoteString()` không thay `getSearchStringEscape()`

Đây là hai API có mục đích khác nhau:

| API | Dùng để làm gì? | Ví dụ |
|---|---|---|
| `getSearchStringEscape()` | Thoát wildcard `%`, `_` trong **metadata search pattern** | `order\_2026` nếu escape là `\` |
| `getIdentifierQuoteString()` | Hỏi ký tự bao tên định danh khi viết SQL theo cú pháp DBMS | `"order_2026"` trên DB dùng dấu quote `"` |

Ví dụ, `getTables(null, "public", "\"order_2026\"", types)` **không** có nghĩa tìm bảng `order_2026` đã được trích dẫn trong SQL: dấu ngoặc kép lúc này có thể là ký tự tên thật trong pattern, khiến truy vấn không khớp.

Tương tự, không dùng `getSearchStringEscape()` để biến một tên bảng do người dùng nhập thành SQL như `SELECT * FROM ...`. Muốn xây câu SQL có identifier động, cần whitelist/kiểm tra identifier và quote/escape theo quy tắc SQL của DBMS; phần **giá trị dữ liệu** phải đi qua `PreparedStatement` với `?`. Đây là bài toán khác với metadata pattern.

## 9. `null`, `""` và `"%"` cho các tham số pattern

Một số bug metadata xuất hiện do dùng ba giá trị này như thể tương đương.

| Giá trị | Chủ ý thông thường trong tham số *pattern* | Lưu ý |
|---|---|---|
| `null` | **Không dùng thuộc tính này để thu hẹp** (nếu phương thức cho phép) | Hữu ích khi không biết schema hoặc tên |
| `""` | Mẫu rỗng hoặc đối tượng **không có schema** tùy tham số và hợp đồng API | Không đồng nghĩa wildcard; có thể không trả gì |
| `"%"` | Khớp mọi chuỗi tên có thể áp dụng | Vẫn là **điều kiện pattern**; có thể gây scan metadata rộng |
| `"_"` | Khớp tên dài đúng một ký tự | Không phải “tất cả tên” |
| `MetadataPatterns.literal("_", escape)` | Tìm tên có đúng dấu `_` theo nghĩa đen | Cần driver hỗ trợ escape |

Ví dụ:

```java
// Mọi tên bảng trong mọi schema mà driver cho tra cứu:
meta.getTables(null, null, "%", null);

// Tìm bảng tên thật "orders_2026" trong schema đã biết:
meta.getTables(
        null,
        MetadataPatterns.literal("public", escape),
        MetadataPatterns.literal("orders_2026", escape),
        new String[]{"TABLE"});
```

`meta` và `escape` ở ví dụ này được lấy từ `connection.getMetaData()` và `meta.getSearchStringEscape()`. Khi DBMS dùng catalog/schema khác nhau, phải chọn giá trị phù hợp. Không giả định mọi database hiển thị tên theo đúng kiểu chữ mà code gửi.

Đặc biệt, tham số `types == null` của `getTables` yêu cầu không giới hạn theo loại đối tượng theo hợp đồng JDBC; không được hiểu nó là tên bảng null. Mảng `types` rỗng cũng không nhất thiết tương đương null trong mọi driver.

## 10. Tên bảng chứa chính escape character

Tên identifier có thể chứa ký tự mà driver dùng để escape metadata pattern, nếu DBMS cho phép tạo tên đó bằng cú pháp quote phù hợp. Ví dụ trên một driver có escape là backslash, một bảng mang tên thật `team\metrics` cần pattern có **hai backslash runtime** để không khiến backslash trong tên bị diễn giải như bắt đầu escape của ký tự kế tiếp.

Hàm `MetadataPatterns.literal(...)` đã xử lý trường hợp này bằng:

```java
if (identifier.startsWith(escape, i)) {
    result.append(escape).append(escape);
    i += escape.length();
    continue;
}
```

Sự khác nhau giữa **một** và **hai** backslash runtime dễ bị che khuất bởi source literal Java, JSON, log hoặc công cụ SQL. Khi debug, có thể in dạng từng ký tự/code point thay vì chỉ nhìn chuỗi hiển thị:

```java
String runtimePattern = MetadataPatterns.literal(
        "team\\metrics", "\\");

for (int i = 0; i < runtimePattern.length(); i++) {
    char ch = runtimePattern.charAt(i);
    System.out.printf("%d : U+%04X%n", i, (int) ch);
}
```

Ví dụ này kiểm tra **chuỗi runtime** mà JDBC nhận. Khi viết một literal SQL `LIKE` bằng tay trong công cụ quản trị database, có thể xuất hiện thêm quy tắc escaping của SQL string literal và mệnh đề `ESCAPE`. Đó là lý do không nên kết luận cách escape của JDBC metadata chỉ bằng việc copy pattern từ Java sang SQL console mà không xét cú pháp chuỗi của database.

## 11. Một ví dụ kiểm thử có thể lặp lại

Trên PostgreSQL (môi trường thử nghiệm riêng), có thể tạo các bảng sau:

```sql
CREATE SCHEMA IF NOT EXISTS metadata_lab;

CREATE TABLE metadata_lab."order_2026" (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMP
);

CREATE TABLE metadata_lab."orderX2026" (
    id BIGINT PRIMARY KEY
);

CREATE TABLE metadata_lab."order%archive" (
    id BIGINT PRIMARY KEY
);
```

Các tên được đặt trong dấu `"..."` để minh họa rõ sự khác biệt; thực hiện với quyền và schema phù hợp môi trường thử nghiệm.

Tiếp đó, qua JDBC hãy kiểm tra:

| Truy vấn metadata | Kết quả mong đợi trên dữ liệu mẫu |
|---|---|
| `getTables(null, literal("metadata_lab", escape), "order_2026", {"TABLE"})` | Có thể trả **hai** bảng `order_2026` và `orderX2026` |
| `getTables(null, literal("metadata_lab", escape), literal("order_2026", escape), {"TABLE"})` | Trả **một** bảng `order_2026` |
| `getTables(null, literal("metadata_lab", escape), startsWith("order_", escape), {"TABLE"})` | Trả tên bắt đầu bằng chuỗi thật `order_` |
| `getTables(null, literal("metadata_lab", escape), literal("order%archive", escape), {"TABLE"})` | Trả bảng có dấu `%` thật |
| `getColumns(null, literal("metadata_lab", escape), literal("order_2026", escape), literal("created_at", escape))` | Trả đúng cột `created_at` của bảng `order_2026` |

Trong bảng, `escape` là giá trị thực từ `getSearchStringEscape()` và `literal`/`startsWith` là các phương thức đã định nghĩa ở phần 3. Những mô tả trên là **kỳ vọng kiểm thử** với driver hỗ trợ đúng escaping; nên đối chiếu danh sách thực tế thay vì mặc định.

Có thể dùng test JUnit với `DataSource` test:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

// Đoạn trong một phương thức @Test có dataSource test đã cấu hình:
assertTrue(TableMetadataLookup.existsTable(
        dataSource, null, "metadata_lab", "order_2026"));

assertTrue(TableMetadataLookup.existsTable(
        dataSource, null, "metadata_lab", "order%archive"));

assertFalse(TableMetadataLookup.existsTable(
        dataSource, null, "metadata_lab", "orderZ2026"));
```

Nếu test thứ ba trả `true`, có thể mã đã dùng pattern `order_2026` mà không xác thực `TABLE_NAME` thực tế, hoặc đang lọc tên không đúng ngữ nghĩa. Một kiểm thử bổ sung nên đặt tên schema có `_`, chẳng hạn `metadata_lab`, và thêm schema thứ hai có phần tên chỉ khác ở vị trí wildcard để đảm bảo cả `schemaPattern` được escape.

## 12. Hiệu năng và an toàn khi cho người dùng tìm metadata

Tra cứu metadata không chỉ phục vụ IDE hoặc công cụ quản trị; một hệ thống multi-tenant có thể dùng metadata để xác minh schema/bảng trước khi thực thi SQL. Khi nhận đầu vào từ người dùng:

1. **Phân biệt chế độ tra cứu.** Chế độ “tên chính xác” phải gọi `literal(...)`; chế độ “tiền tố” thoát phần prefix rồi thêm `%`. Không cho dữ liệu người dùng âm thầm đóng vai trò wildcard.
2. **Giới hạn catalog/schema và loại đối tượng.** Tránh truy vấn `getTables(null, null, "%", null)` trong đường nóng của một HTTP request nếu chỉ cần một bảng.
3. **Không dùng metadata như cơ chế phân quyền.** Kết quả driver trả phụ thuộc quyền của tài khoản DB và chính sách DBMS; xác minh tồn tại không đồng nghĩa người dùng ứng dụng được phép truy cập.
4. **Đóng ResultSet kịp thời.** Metadata query có thể dùng statement và tài nguyên DB phía dưới; dùng `try-with-resources` cho cả `ResultSet` và connection.
5. **Tránh gọi metadata lặp vô ích.** Có thể cache thông tin schema tương đối ổn định nếu ứng dụng quản lý được invalidation khi migration/DDL thay đổi.
6. **Ghi log tiết chế.** Log tên pattern đã tạo, schema đã chọn, driver version và số kết quả nếu cần chẩn đoán; không đưa thông tin xác thực kết nối hoặc dữ liệu nhạy cảm vào log.
7. **Không giả định mọi tên đều nhìn thấy.** Một số DBMS/driver chỉ liệt kê các đối tượng mà user có quyền, hoặc không liệt kê schema hệ thống theo cùng cách.
8. **Không ghép tên bảng từ metadata trực tiếp vào SQL chưa kiểm soát.** Kết quả là dữ liệu tra cứu, vẫn cần chính sách whitelist/quote identifier khi sinh truy vấn thực thi.

Nếu cần nhiều dữ liệu cấu trúc, `DatabaseMetaData` có những phương thức chuyên biệt như `getColumns`, `getPrimaryKeys`, `getImportedKeys` và `getIndexInfo`. Chỉ những API nhận tham số pattern mới cần xử lý wildcard; tránh viết một hàm chung tự thoát **mọi** tham số String không phân biệt API.

## 13. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Tìm `order_2026` lại thấy `orderX2026` | Dấu `_` được hiểu là wildcard | Escape tên bằng `getSearchStringEscape()` |
| Tìm bảng có dấu `%` trả nhiều tên | Dấu `%` đang khớp nhiều ký tự | Escape dấu `%` trong tên literal |
| Không thấy bảng dù SQL query trực tiếp hoạt động | Sai catalog/schema hoặc quy tắc hoa/thường | Xem `TABLE_CAT`, `TABLE_SCHEM`, `TABLE_NAME` và identifier case của driver |
| Escape có tác dụng với `getTables` nhưng `getPrimaryKeys` không thấy bảng | Tham số `table` của `getPrimaryKeys` là tên chính xác | Truyền tên thật, không thêm escape pattern |
| Prefix `audit_` trả `auditXlogs` | Không escape `_` ở phần prefix | `literal("audit_", escape) + "%"` |
| Tên có backslash không khớp | Escape của driver xuất hiện ngay trong identifier | Thoát chính escape character, kiểm thử runtime pattern |
| Dùng `getIdentifierQuoteString()` làm escape `LIKE` | Nhầm quote identifier với search escape | Dùng `getSearchStringEscape()` cho metadata pattern |
| Dùng regex `.*` hoặc glob `*` làm wildcard | JDBC metadata dùng `%` và `_` | Chuyển ý định tìm kiếm sang cú pháp pattern phù hợp |
| API trả rất nhiều kết quả/chậm | Dùng `%` quá rộng, không lọc schema/type | Thu hẹp tìm kiếm, tránh gọi lặp trên request nóng |
| Tên schema chứa `_` mà tra không đúng | Chỉ escape tên bảng, quên `schemaPattern` | Escape **mọi tham số pattern** được truyền từ tên literal |
| `ResultSet` metadata lỗi sau khi connection đóng | Trả result set ra ngoài phạm vi tài nguyên | Materialize thông tin cần dùng trước khi đóng |
| Đúng trên môi trường này nhưng sai trên môi trường khác | Khác driver, case-folding hoặc catalog/schema | Kiểm thử tích hợp và đọc quy tắc metadata từng DBMS |

## 14. Checklist áp dụng trong dự án JDBC

Trước khi đưa tính năng tra cứu siêu dữ liệu vào ứng dụng, hãy tự kiểm tra:

- Input đang là **tên chính xác**, **tiền tố literal** hay **pattern người dùng chủ ý cung cấp**?
- Đã gọi `DatabaseMetaData.getSearchStringEscape()` thay vì hard-code `\` chưa?
- Có thoát `%`, `_` và cả escape character nằm trong tên đối tượng không?
- Đã xác định những tham số **có hậu tố Pattern** và tránh escape nhầm tham số tên chính xác chưa?
- `null`, `""` và `"%"` có đang được dùng đúng ý nghĩa của từng phương thức không?
- Catalog, schema và loại bảng có được giới hạn đúng với DBMS đang chạy không?
- Đã xét quy tắc hoa/thường và tên quoted identifier theo metadata thật chưa?
- Đã dùng `try-with-resources` cho `ResultSet`/connection và tránh trả `ResultSet` sống ra khỏi DAO chưa?
- Có kiểm tra kết quả trả về thực tế (`TABLE_NAME`, `TABLE_SCHEM`, `COLUMN_NAME`) khi nghiệp vụ yêu cầu tên chính xác không?
- Đã chạy test với tên chứa dấu `_`, `%`, escape character, tên khác case và schema khác nhau trên driver thật chưa?

## Ghi nhớ

- **`%`** đại diện cho không hoặc nhiều ký tự, **`_`** đại diện cho đúng một ký tự trong **JDBC metadata search pattern**.
- **`getSearchStringEscape()`** cho biết chuỗi escape dùng để tìm `%`/`_` theo nghĩa đen; không mặc định mọi driver dùng backslash.
- **`getTables`, `getColumns` và nhiều API khác nhận tham số pattern**; còn `getPrimaryKeys`, `getIndexInfo` và `getImportedKeys` dùng tên đối tượng chính xác.
- **Tên chính xác phải được escape trước khi đưa vào tham số pattern**. Muốn tìm theo tiền tố, escape phần prefix rồi mới nối `%` chủ đích.
- **Quote identifier và escape metadata pattern là hai bài toán khác nhau.** `getIdentifierQuoteString()` không thay cho `getSearchStringEscape()`.
- **Catalog, schema, kiểu chữ và quyền truy cập** đều ảnh hưởng kết quả; không thể dựa riêng vào pattern để xác nhận chính xác tên.
- **Đóng tài nguyên và kiểm thử trên JDBC driver thực tế** để tránh lỗi do khác biệt DBMS hoặc phương thức metadata không được hỗ trợ đầy đủ.

Xử lý đúng mẫu tìm kiếm giúp các công cụ JDBC tra cứu bảng, cột và routine chính xác, tránh quét metadata quá rộng và làm cho logic kiểm tra schema bền vững khi triển khai qua những cơ sở dữ liệu khác nhau.
