# DatabaseMetaData và phát hiện khả năng hỗ trợ

## 1. DatabaseMetaData dùng để làm gì?

Một ứng dụng Java có thể kết nối nhiều hệ quản trị cơ sở dữ liệu (DBMS): PostgreSQL, MySQL, Oracle Database, SQL Server hoặc một DBMS khác. Các hệ thống này cùng dùng JDBC nhưng **không có cùng mọi tính năng, kiểu dữ liệu, giới hạn, quy tắc đặt tên, metadata schema và hành vi câu lệnh**. Một driver JDBC còn có thể bổ sung, mô phỏng hoặc giới hạn một khả năng của DBMS.

`java.sql.DatabaseMetaData` là **hợp đồng chuẩn** để ứng dụng hỏi driver/DBMS về:

- Tên và phiên bản sản phẩm database; tên, phiên bản và mức JDBC driver báo cáo.
- Khả năng có transactions, savepoints, batch updates, generated keys, stored procedures, result-set types/concurrency, isolation levels...
- Cách dùng catalog, schema, identifier quoting, wildcard escaping và giới hạn tên/kiểu.
- Những đối tượng đã tồn tại: catalogs, schemas, tables, views, columns, primary keys, foreign keys, indexes, data types...
- Những khác biệt có thể ảnh hưởng công cụ quản trị schema, import/export, code generator và query builder chạy trên nhiều DBMS.

**Cần nhớ:** đối tượng `DatabaseMetaData` mô tả khả năng của **cặp driver + DBMS mà `Connection` hiện tại đang sử dụng**, không phải chân lý chung của tất cả driver cùng hãng hay mọi kết nối trong cụm database. Oracle Java SE 26 mô tả API theo chính cách hiểu này.

### Mục tiêu học tập

1. Lấy `DatabaseMetaData` từ một `Connection` đang mở và đọc đúng thông tin phiên bản.
2. Chọn nhánh xử lý dựa trên `supportsTransactions`, `supportsBatchUpdates`, `supportsSavepoints`, `supportsResultSetType` và `supportsResultSetConcurrency`.
3. Đọc bảng/cột/khóa từ những `ResultSet` metadata; xử lý `null`, pattern, `getSearchStringEscape` và tài nguyên cần đóng.
4. Hiểu **metadata là khả năng được báo cáo**, không bảo đảm mọi SQL statement hoặc mọi tính năng luôn chạy thành công.
5. Chạy demo Java 17+ **không cần database ngoài** để kiểm thử logic phát hiện khả năng; sau đó dùng một inspector thật với `DataSource` khi đã cấu hình driver và database.

### Vị trí của API trong lịch sử JDBC

`DatabaseMetaData` đã có từ **JDBC 1.1**, tức **trước Java 6/JDBC 4.0**. Các phương thức về generated keys, savepoints, JDBC version và holdability đã được bổ sung trong các phiên bản JDBC khác nhau; JDBC 4.1 (Java 7) còn thêm `getPseudoColumns` và `generatedKeyAlwaysReturned`. Vì vậy **không nói rằng DatabaseMetaData được tạo mới trong JDBC 4.0**.

Bài này thuộc mạch Java 6/JDBC nhưng chỉ hướng dẫn **hợp đồng vẫn còn được hỗ trợ trong JDK hiện đại**. Ví dụ dùng Java 17+ và try-with-resources (JDBC 4.1/Java 7 trở lên). Không sử dụng `Class.forName` như bước mặc định cho mọi driver, không hard-code hành vi của một hãng thành quy tắc chung.

## 2. Lấy metadata từ Connection

Cách chuẩn:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

// Đoạn trích trong một phương thức nhận DataSource source:
try (Connection connection = source.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();
    System.out.println(meta.getDatabaseProductName());
    System.out.println(meta.getDriverName());
}
~~~

Đây là **đoạn minh họa**, không phải chương trình có `main` độc lập; cần một `DataSource` được cấu hình đúng với driver/DBMS thực.

Luồng thường gặp:

~~~text
DataSource / DriverManager
        |
        v
Connection đang mở
        |
        +--> connection.getMetaData()
        |           |
        |           +--> Thông tin DBMS và driver
        |           +--> supports... (boolean)
        |           +--> getTables/getColumns/getPrimaryKeys...
        |                           |
        |                           v
        |                        ResultSet
        |                           |
        |                           v
        |                     Đọc + đóng cursor
        |
        +--> Dùng khả năng đã phát hiện để chọn SQL/tính năng
        |
        v
Đóng logical Connection (trả về pool nếu dùng pooling)
~~~

**Không tự `new DatabaseMetaData()`**: nó là **interface** được driver triển khai và trả về qua `Connection.getMetaData()`.

### 2.1. Tuổi thọ và chi phí

Một số lời gọi metadata có thể cần gửi truy vấn đến DBMS qua mạng, đặc biệt các phương thức liệt kê schema/tables/columns. Vì vậy:

- Lấy metadata trong lúc `Connection` còn hợp lệ.
- Đóng những `ResultSet` metadata qua try-with-resources.
- Không gọi `getTables(...)` trên mọi request nếu schema hiếm khi thay đổi.
- Có thể cache một **snapshot do ứng dụng xây dựng**, với chính sách refresh/invalidate khi schema hoặc driver version đổi; không giữ một `ResultSet` mở trong cache.
- Giới hạn phạm vi discovery theo catalog/schema/table cần thiết, vì quyền DB và metadata catalog lớn có thể khiến toàn bộ scan rất tốn chi phí.
- Không giả định connection metadata cho biết khả năng của **mọi connection khác** khi hệ thống dùng nhiều tenant, nhiều pool, replica hoặc driver versions khác nhau.

### 2.2. DriverManager hay DataSource?

`DatabaseMetaData` lấy được từ `Connection` tạo bằng cả `DriverManager` lẫn `DataSource`. Trong ứng dụng production, `DataSource` thường được ưu tiên vì có thể tích hợp cấu hình, pooling và transaction management; `DriverManager` vẫn hợp lệ cho công cụ nhỏ và bài lab.

Đừng vì bài này nói về khả năng hỗ trợ mà tự tạo hàng chục physical connections chỉ để thử từng `supports...`. Thay vào đó dùng connection thích hợp từ pool/repository và đo chi phí truy vấn metadata trên hệ thống thật.

## 3. Nhóm phương thức nhận diện database và driver

| Method | Kết quả | Phân biệt quan trọng |
| --- | --- | --- |
| `getDatabaseProductName()` | Tên sản phẩm DBMS | Ví dụ có thể là tên vendor, không phải ID ổn định để chọn mọi SQL |
| `getDatabaseProductVersion()` | Chuỗi version của DBMS | Thường vendor-specific; đừng parse cứng để quyết định tính năng |
| `getDatabaseMajorVersion()/getDatabaseMinorVersion()` | Thành phần version DBMS | Chỉ là version DB, không phải version JDBC driver |
| `getDriverName()` | Tên JDBC driver | Driver hoặc wrapper có thể báo tên khác |
| `getDriverVersion()` | Version string của driver | Không đồng nghĩa DB server version |
| `getDriverMajorVersion()/getDriverMinorVersion()` | Thành phần version driver | Phải đọc theo driver |
| `getJDBCMajorVersion()/getJDBCMinorVersion()` | Phiên bản JDBC driver khai báo hỗ trợ | Không đủ chứng minh mọi optional feature đều khả dụng |
| `getURL()` | JDBC URL | Có thể chứa thông tin nhạy cảm; hạn chế log |
| `getUserName()` | User name của database connection | Có thể lộ định danh hoặc bí mật nghiệp vụ; không tự log |
| `getIdentifierQuoteString()` | Chuỗi quote SQL identifier theo DB | Có thể là dấu cách `" "` khi quote identifiers không được hỗ trợ |

Ví dụ JDK có API JDBC mới không đồng nghĩa driver đang dùng hỗ trợ một feature cụ thể. Tương tự, một driver tự báo JDBC 4.x không đủ để khẳng định mọi kiểu `SQLXML`, `RowId`, scrollable/updatable ResultSet hay transaction isolation tương thích.

### 3.1. Không dùng tên vendor làm feature flag nếu có supports... cụ thể

Phản ví dụ:

~~~java
// Không nên suy luận khả năng savepoints chỉ từ tên sản phẩm.
boolean savepoints = meta.getDatabaseProductName().contains("VendorX");
~~~

Đây là **đoạn trích phản ví dụ**, `meta` là biến `DatabaseMetaData` đã có. Code trên khó đúng nếu driver version khác, wrapper khác hoặc DBMS cấu hình khác.

Tốt hơn:

~~~java
boolean savepoints = meta.supportsSavepoints();
~~~

Nhưng kiểm tra feature flag vẫn chỉ là **bước chọn nhánh xử lý**: lúc thực thi có thể nhận `SQLException` hoặc `SQLFeatureNotSupportedException` và phải xử lý, rollback hoặc phản hồi theo nghiệp vụ.

## 4. Khám phá hỗ trợ giao dịch

Những phương thức đáng học:

| API | Câu hỏi trả lời |
| --- | --- |
| `supportsTransactions()` | DBMS/driver có hỗ trợ transactions không? |
| `supportsSavepoints()` | Có hỗ trợ JDBC `Savepoint` không? |
| `supportsTransactionIsolationLevel(int level)` | Hỗ trợ isolation level cụ thể? |
| `getDefaultTransactionIsolation()` | Isolation level mặc định do metadata báo cáo? |
| `supportsDataDefinitionAndDataManipulationTransactions()` | DDL và DML có thể cùng trong transaction không? |
| `supportsDataManipulationTransactionsOnly()` | Chỉ DML transaction? |
| `dataDefinitionCausesTransactionCommit()` | DDL có thể gây commit ngầm không? |
| `dataDefinitionIgnoredInTransactions()` | DDL trong transaction có bị bỏ qua không? |

Các isolation constants nằm trong `java.sql.Connection`:

~~~java
Connection.TRANSACTION_READ_UNCOMMITTED
Connection.TRANSACTION_READ_COMMITTED
Connection.TRANSACTION_REPEATABLE_READ
Connection.TRANSACTION_SERIALIZABLE
~~~

Đây là **các constant để tham khảo**, không phải source file độc lập.

### 4.1. Chọn savepoints một cách có điều kiện

~~~java
if (meta.supportsTransactions() && meta.supportsSavepoints()) {
    // Có thể thử transaction + savepoint với Connection thật.
} else {
    // Chọn một workflow không phụ thuộc savepoint,
    // hoặc báo yêu cầu tính năng không được hỗ trợ.
}
~~~

**Đoạn minh họa**; `meta` chỉ là metadata. Không thể giả định “thiếu savepoints thì cứ bỏ qua rollback một phần mà logic vẫn đúng”: nếu ứng dụng **bắt buộc** có partial rollback, hãy từ chối hoạt động hoặc thiết kế lại transaction boundaries.

Trên connection thật, savepoints phải được tạo trong transaction và thường không được dùng dưới auto-commit. Có thể dùng `connection.setSavepoint()`, `rollback(savepoint)`, `releaseSavepoint(savepoint)` nếu DB/driver hỗ trợ. Nhưng hãy xét semantics DDL, nested operations và framework transaction manager.

### 4.2. Metadata không thay kiểm thử ACID

`supportsTransactions()==true` không chứng minh toàn bộ use case đang có isolation/durability như bạn tưởng. Một DB có thể áp dụng MVCC, read phenomena hoặc isolation semantics riêng. Dùng `supportsTransactionIsolationLevel(...)` để kiểm tra khả năng về mặt API, sau đó thực hiện **integration tests** đúng workload với nhiều connections, concurrent transactions và lỗi network.

Không tự động thay isolation level trên connection vừa mượn từ pool mà quên khôi phục hoặc kiểm soát transaction lifecycle; với transaction do framework quản lý cần dùng API framework tương ứng.

## 5. Batch updates và generated keys

### 5.1. supportsBatchUpdates()

~~~java
boolean batching = meta.supportsBatchUpdates();
~~~

Nếu `true`, driver báo hỗ trợ batch updates, thường qua `Statement.addBatch/executeBatch` và `PreparedStatement.addBatch/executeBatch`.

**Không có nghĩa:**

- Mọi SQL trong batch đều được thực thi như một transaction atomic.
- Driver sẽ chạy nhanh hơn mọi phương án khác.
- Mọi hàng đều có một update count chính xác.
- Network driver sẽ gom tất cả thành một round-trip.
- Một lệnh `executeBatch` bị lỗi thì DB tự rollback toàn bộ.

Batch có thể ném `BatchUpdateException`, có mảng update counts với các giá trị đặc biệt `Statement.SUCCESS_NO_INFO` và `Statement.EXECUTE_FAILED` theo contract. Để đảm bảo atomicity, dùng **transaction rõ ràng** khi có hỗ trợ, rồi xử lý lỗi/rollback; vẫn phải hiểu trạng thái từng statement khi connection mất.

### 5.2. supportsGetGeneratedKeys()

~~~java
boolean generatedKeys = meta.supportsGetGeneratedKeys();
~~~

Khi `true`, driver báo có thể lấy auto-generated keys sau lệnh insert, ví dụ `Connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)` và `PreparedStatement.getGeneratedKeys()`.

**Không có nghĩa** DB luôn tạo ID, mọi statement trả key, hoặc thứ tự/số lượng keys luôn giống nhau giữa vendors. Cần đúng schema, SQL và driver. `supportsGetGeneratedKeys` là khả năng JDBC **đã có từ JDBC 3.0**, không phải lần đầu ở JDBC 4.0.

## 6. ResultSet: type, concurrency và holdability

### 6.1. supportsResultSetType

Một số constants:

| Constant | Ý nghĩa |
| --- | --- |
| `ResultSet.TYPE_FORWARD_ONLY` | Cursor di chuyển tiến tới; lựa chọn phổ biến |
| `ResultSet.TYPE_SCROLL_INSENSITIVE` | Có thể di chuyển tới/lùi, không phản ánh thay đổi dữ liệu ngoài theo mức định nghĩa type |
| `ResultSet.TYPE_SCROLL_SENSITIVE` | Có thể phản ánh một số thay đổi từ bên ngoài theo cách driver/DB hỗ trợ |

Kiểm tra:

~~~java
boolean canScroll = meta.supportsResultSetType(
        ResultSet.TYPE_SCROLL_INSENSITIVE);
~~~

**Không suy rằng scrollable = updatable.** Một result set có thể scroll được nhưng chỉ read-only.

### 6.2. supportsResultSetConcurrency

Để yêu cầu đúng **cặp** type và concurrency, dùng:

~~~java
boolean canUpdateScrollable =
        meta.supportsResultSetConcurrency(
            ResultSet.TYPE_SCROLL_INSENSITIVE,
            ResultSet.CONCUR_UPDATABLE);
~~~

Đây là **đoạn trích**, biến `meta` phải có. Nếu `false`, dùng kiểu đơn giản hơn `TYPE_FORWARD_ONLY + CONCUR_READ_ONLY` nếu được hỗ trợ; hoặc dùng `UPDATE/DELETE` qua `PreparedStatement` thay vì một updatable ResultSet.

Ngay cả khi `true`, khả năng cập nhật một kết quả cụ thể còn phụ thuộc SQL (join/aggregate), loại cột, khóa chính và driver. Metadata nói về **khả năng chung của combination**, không bảo đảm mọi query cho phép `updateRow()`.

### 6.3. Holdability

`supportsResultSetHoldability(int holdability)` và `getResultSetHoldability()` cho biết cursor có thể tồn tại sau commit hay không:

- `ResultSet.HOLD_CURSORS_OVER_COMMIT`.
- `ResultSet.CLOSE_CURSORS_AT_COMMIT`.

Không dùng cursor sau transaction commit nếu driver đã đóng nó. Khi một công cụ đọc dữ liệu dài hạn, quyết định fetch, transaction scope và resource closing cần dựa trên driver/DB integration test; đừng chỉ tin vào tên constant.

## 7. Schema discovery: các bảng metadata quan trọng

Một trong những ứng dụng mạnh nhất của `DatabaseMetaData` là **khám phá schema của database không biết trước vendor**.

| API | Khám phá | Những cột thường đọc từ ResultSet |
| --- | --- | --- |
| `getCatalogs()` | Catalogs | `TABLE_CAT` |
| `getSchemas()` / `getSchemas(catalog, schemaPattern)` | Schemas | `TABLE_SCHEM`, `TABLE_CATALOG` |
| `getTableTypes()` | Các loại table | `TABLE_TYPE` |
| `getTables(catalog, schemaPattern, tableNamePattern, types)` | Tables/views theo bộ lọc | `TABLE_CAT`, `TABLE_SCHEM`, `TABLE_NAME`, `TABLE_TYPE` |
| `getColumns(catalog, schemaPattern, tableNamePattern, columnNamePattern)` | Các columns | `COLUMN_NAME`, `DATA_TYPE`, `TYPE_NAME`, `COLUMN_SIZE`, `NULLABLE`, `IS_NULLABLE`, `ORDINAL_POSITION` |
| `getPrimaryKeys(catalog, schema, table)` | Primary key | `COLUMN_NAME`, `KEY_SEQ`, `PK_NAME` |
| `getImportedKeys(catalog, schema, table)` | Foreign keys mà table đang tham chiếu | `PKTABLE_NAME`, `PKCOLUMN_NAME`, `FKTABLE_NAME`, `FKCOLUMN_NAME`, `KEY_SEQ` |
| `getExportedKeys(catalog, schema, table)` | Foreign keys của bảng khác tham chiếu PK của table | Các cột PK/FK tương ứng |
| `getIndexInfo(catalog, schema, table, unique, approximate)` | Indexes | `INDEX_NAME`, `NON_UNIQUE`, `ORDINAL_POSITION`, `COLUMN_NAME` |
| `getTypeInfo()` | SQL types DB hỗ trợ | `TYPE_NAME`, `DATA_TYPE` và metadata type khác |
| `getProcedures/getProcedureColumns`, `getFunctions/getFunctionColumns` | Stored procedures/functions | Tên, schema, tham số, kiểu |

### 7.1. ResultSet metadata có hợp đồng cột riêng

~~~java
try (ResultSet tables = meta.getTables(
        catalog, schemaPattern, "%", new String[]{"TABLE"})) {
    while (tables.next()) {
        String schema = tables.getString("TABLE_SCHEM");
        String table = tables.getString("TABLE_NAME");
        System.out.println(schema + "." + table);
    }
}
~~~

Đây là **đoạn minh họa** trong một method nhận `meta`, `catalog` và `schemaPattern`. Kết quả trong DB thật **phụ thuộc quyền truy cập và schema hiện hữu**. Không gán stdout mẫu của demo fake cho mọi DB.

`getTables(...)` trả một `ResultSet` do metadata method định nghĩa, với các **column labels chuẩn**. Driver có thể thêm cột vendor-specific. Khi metadata không có cho một dạng yêu cầu, API có thể trả **ResultSet rỗng**; không nên cứ 0 rows là kết luận chắc chắn schema không tồn tại hoặc ứng dụng có quyền nhìn mọi đối tượng.

Cột `TABLE_SCHEM`, `TABLE_CAT` có thể `null`. Dùng các column labels chuẩn thay vì dựa vào thứ tự hay assumptions về tên schema.

### 7.2. Column metadata: SQL type và nullability

`getColumns(...)` có:

- `DATA_TYPE`: mã int tương ứng với constants `java.sql.Types`, ví dụ `Types.INTEGER`, `Types.VARCHAR`, `Types.BIGINT`.
- `TYPE_NAME`: tên SQL type **theo DBMS**, có thể khác qua vendors.
- `COLUMN_SIZE`, `DECIMAL_DIGITS`, `CHAR_OCTET_LENGTH`: kích thước/độ chính xác theo kiểu, không dùng một công thức cho tất cả.
- `NULLABLE`: các constants `DatabaseMetaData.columnNoNulls`, `columnNullable`, `columnNullableUnknown`.
- `IS_NULLABLE`: thông thường là `YES`, `NO` hoặc chuỗi rỗng nếu không biết.
- `ORDINAL_POSITION`: thứ tự cột trong bảng (bắt đầu từ 1).

**Không nhầm** SQL `NULL` với Java `null` của một metadata field. Nếu dùng `getInt` cho cột metadata có giá trị SQL NULL, cần gọi `rs.wasNull()` để phân biệt với số 0 khi contract đòi hỏi.

### 7.3. Key metadata

`getPrimaryKeys` trả nhiều hàng nếu primary key gồm nhiều cột, với `KEY_SEQ`. Không giả định mỗi bảng chỉ có một cột PK.

`getImportedKeys` mô tả các FK của bảng làm **foreign-key table**; `getExportedKeys` cho biết nơi khác tham chiếu khóa chính của bảng đang xét. Cần xử lý composite keys, schema/catalog và `UPDATE_RULE/DELETE_RULE` chứ không chỉ ghép hai column names bằng string.

### 7.4. Table types không chỉ có TABLE

Một số DB trả `TABLE`, `VIEW`, `SYSTEM TABLE`, `GLOBAL TEMPORARY` hoặc tên vendor-specific khác. Muốn tìm một loại cụ thể, trước hết có thể đọc `getTableTypes()` và lọc `getTables(..., new String[]{"TABLE"})`. Nếu bỏ filter `types` hoặc đặt `null`, cần hiểu contract là **không thu hẹp theo table types**, có thể nhận rất nhiều đối tượng không mong muốn.

## 8. Pattern, catalog, schema và identifier quoting

Các phương thức `getTables/getColumns` dùng đối số `schemaPattern`, `tableNamePattern`, `columnNamePattern`.

### 8.1. Phân biệt null, chuỗi rỗng và wildcard

Theo Javadoc:

| Đối số | Ý nghĩa |
| --- | --- |
| `null` ở catalog/schema criterion | **Không dùng tiêu chí ấy để hạn chế tìm kiếm** |
| `""` ở catalog/schema criterion | Tìm đối tượng **không có catalog/schema** theo hợp đồng tương ứng |
| `"%"` trong *pattern* | 0 hoặc nhiều ký tự bất kỳ |
| `"_"` trong *pattern* | Đúng một ký tự bất kỳ |
| `"customer%"` | Các tên bắt đầu với `customer` |
| `"customer_2026"` | `_` có thể là wildcard, **không phải dấu gạch dưới literal** |

Tránh gọi `getTables(null,null,"%",null)` trên database nhiều triệu objects trong mỗi HTTP request. Giới hạn permissions, schema, table type và số rows phù hợp.

### 8.2. Escaping wildcard literal qua getSearchStringEscape

Nếu tên bảng thật là `order_%`, truyền `"order_%"` trực tiếp là **pattern**, có thể match nhiều tên khác. `meta.getSearchStringEscape()` báo chuỗi dùng để escape metadata search wildcard theo DBMS. Ví dụ mock trả ký tự backslash:

~~~text
Input literal:        order_%
Search pattern:       order\_\%
~~~

Hàm bên dưới xuất hiện trong demo runnable, xử lý cả escape token nếu literal chứa chính token ấy:

~~~java
static String literalPattern(DatabaseMetaData meta, String literal)
        throws SQLException {
    String escape = meta.getSearchStringEscape();
    if (escape == null || escape.isEmpty()) {
        throw new SQLFeatureNotSupportedException("No metadata pattern escape");
    }
    StringBuilder out = new StringBuilder();
    for (int i = 0; i < literal.length();) {
        if (literal.startsWith(escape, i)) {
            out.append(escape).append(escape);
            i += escape.length();
        } else {
            char ch = literal.charAt(i++);
            if (ch == '%' || ch == '_') out.append(escape);
            out.append(ch);
        }
    }
    return out.toString();
}
~~~

Đây là **đoạn trích method** nằm trong `MetadataContractsDemo`. Nó minh họa cách quote các wildcard **cho metadata search patterns**, **không phải cách escape giá trị SQL**.

Nếu driver trả escape rỗng/không hỗ trợ, đừng âm thầm khẳng định đã escape được pattern; phải từ chối việc exact-match dựa trên pattern hoặc triển khai chiến lược phù hợp như scan giới hạn rồi so sánh literal ở phía application.

### 8.3. getIdentifierQuoteString không phải SQL escaping toàn năng

`getIdentifierQuoteString()` trả chuỗi quote SQL identifier (có thể là `" "` khi không hỗ trợ quote). Ví dụ có DB dùng dấu `"`, DB khác dùng delimiter khác.

**Không trộn ba thứ:**

1. **Metadata search pattern escaping:** `getSearchStringEscape()`, khi tên chứa `%` hoặc `_`.
2. **SQL identifier quoting:** tên table/schema/column trong SQL, dùng quy tắc identifier của vendor/JDBC.
3. **SQL value binding:** `PreparedStatement.setString/...?` để truyền dữ liệu, **không tự quote/escape bằng string concatenation**.

Nếu table name hoặc column name do người dùng nhập, **không** chỉ lấy `getIdentifierQuoteString` rồi nối quanh input mà cho rằng an toàn; cần allowlist/validation và xử lý embedded quote/qualified names theo vendor. JDBC trên JDK hiện đại có `Statement.enquoteIdentifier`/`isSimpleIdentifier` ở các đời mới hơn, nhưng cũng cần hiểu áp dụng tới identifiers nào và driver có hỗ trợ không.

### 8.4. Catalog và schema khác nhau qua vendor

Một số DBMS dùng nhiều catalog, DB khác tập trung schema; `Connection.getCatalog()` có thể null. `Connection.getSchema()` là API **JDBC 4.1/Java 7**, vẫn dùng được trong Java 17+, không phải mới ở JDBC 4.0.

Nếu `schema` chứa ký tự wildcard, khi dùng nó làm `schemaPattern` cần escape với `getSearchStringEscape`. Không được lấy tên schema một cách mù quáng rồi truyền vào *pattern argument* mà chắc chắn tìm đúng tên literal. Với một inspector đơn giản, dùng `null` ở schemaPattern để không lọc cũng có thể phù hợp, rồi giới hạn kết quả và lọc tên cụ thể trong code.

### 8.5. Quy tắc chữ hoa/chữ thường của identifiers

Một số phương thức:

- `storesUpperCaseIdentifiers()`, `storesLowerCaseIdentifiers()`, `storesMixedCaseIdentifiers()`.
- `supportsMixedCaseIdentifiers()`, `supportsMixedCaseQuotedIdentifiers()`.
- `storesUpperCaseQuotedIdentifiers()`, `storesLowerCaseQuotedIdentifiers()`.

Tên class/table có thể được DBMS lưu dưới một casing khác với text nguồn. Với schema introspection, **không tự `toLowerCase(Locale.ROOT)` rồi coi là tên thật**. Hãy đọc tên thực từ metadata và hiểu quy tắc quoted identifiers của DB trước khi xây query.

## 9. Demo Java 17+: tự kiểm thử metadata không cần database server

Không phải người học nào cũng có sẵn PostgreSQL/MySQL/Oracle Database. Demo này dựng một **fixture bằng Java dynamic proxies** để minh họa cách code đọc `DatabaseMetaData` và `ResultSet`, chọn nhánh dựa trên `supports...`, xử lý metadata patterns và đóng connection.

**Phạm vi rất rõ:** các giá trị `TrainingDB`, `FixtureDriver`, `jdbc=4.0` và toàn bộ flags/rows **được fixture tự khai báo**, **không được đo từ database thật**. Demo **không** chứng minh một vendor driver hay server nào hỗ trợ batch, savepoint hoặc transactions. Nó là **contract/unit test cho mã ứng dụng**, không phải integration test.

### 9.1. File MetadataContractsDemo.java (độc lập, chạy được)

~~~java
import java.lang.reflect.*;
import java.sql.*;
import java.util.*;

public final class MetadataContractsDemo {
    private static void require(boolean ok, String detail) {
        if (!ok) throw new AssertionError(detail);
    }

    static String literalPattern(DatabaseMetaData meta, String literal)
            throws SQLException {
        String escape = meta.getSearchStringEscape();
        if (escape == null || escape.isEmpty()) {
            throw new SQLFeatureNotSupportedException("No metadata pattern escape");
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < literal.length();) {
            if (literal.startsWith(escape, i)) {
                out.append(escape).append(escape);
                i += escape.length();
            } else {
                char ch = literal.charAt(i++);
                if (ch == '%' || ch == '_') out.append(escape);
                out.append(ch);
            }
        }
        return out.toString();
    }

    static ResultSet rows(List<Map<String, Object>> entries) {
        InvocationHandler h = new InvocationHandler() {
            int index = -1;
            boolean closed;

            public Object invoke(Object proxy, Method method, Object[] args)
                    throws Throwable {
                switch (method.getName()) {
                    case "next":
                        if (closed) throw new SQLException("ResultSet closed");
                        index++;
                        return index < entries.size();
                    case "getString":
                    case "getInt":
                        if (closed || index < 0 || index >= entries.size())
                            throw new SQLException("Cursor not on row");
                        Object value = entries.get(index).get((String) args[0]);
                        if ("getString".equals(method.getName()))
                            return value == null ? null : String.valueOf(value);
                        return value == null ? 0 : ((Number) value).intValue();
                    case "close": closed = true; return null;
                    case "isClosed": return closed;
                    default: throw new SQLFeatureNotSupportedException(
                            "Fixture ResultSet: " + method.getName());
                }
            }
        };
        return (ResultSet) Proxy.newProxyInstance(
                ResultSet.class.getClassLoader(), new Class<?>[]{ResultSet.class}, h);
    }

    static DatabaseMetaData fixture() {
        InvocationHandler h = (proxy, method, args) -> {
            switch (method.getName()) {
                case "getDatabaseProductName": return "TrainingDB";
                case "getDatabaseProductVersion": return "1.0-fixture";
                case "getDriverName": return "FixtureDriver";
                case "getDriverVersion": return "0.1";
                case "getJDBCMajorVersion": return 4;
                case "getJDBCMinorVersion": return 0;
                case "supportsTransactions": return true;
                case "supportsSavepoints": return false;
                case "supportsBatchUpdates": return true;
                case "supportsGetGeneratedKeys": return true;
                case "supportsResultSetType":
                    return (Integer) args[0] == ResultSet.TYPE_FORWARD_ONLY
                            || (Integer) args[0] == ResultSet.TYPE_SCROLL_INSENSITIVE;
                case "supportsResultSetConcurrency":
                    return (Integer) args[0] == ResultSet.TYPE_FORWARD_ONLY
                            && (Integer) args[1] == ResultSet.CONCUR_READ_ONLY;
                case "supportsTransactionIsolationLevel":
                    return (Integer) args[0] == Connection.TRANSACTION_READ_COMMITTED;
                case "getIdentifierQuoteString": return "\"";
                case "getSearchStringEscape": return "\\";
                case "getTables":
                    require("%".equals(args[2]), "Expected table pattern");
                    return rows(List.of(
                            Map.of("TABLE_SCHEM", "public",
                                   "TABLE_NAME", "customers", "TABLE_TYPE", "TABLE"),
                            Map.of("TABLE_SCHEM", "public",
                                   "TABLE_NAME", "orders", "TABLE_TYPE", "TABLE")));
                case "getColumns":
                    return rows(List.of(Map.of(
                            "COLUMN_NAME", "id", "TYPE_NAME", "BIGINT",
                            "DATA_TYPE", Types.BIGINT,
                            "NULLABLE", DatabaseMetaData.columnNoNulls)));
                case "getPrimaryKeys":
                    return rows(List.of(Map.of("COLUMN_NAME", "id", "KEY_SEQ", 1)));
                default:
                    throw new SQLFeatureNotSupportedException(
                            "Fixture DatabaseMetaData: " + method.getName());
            }
        };
        return (DatabaseMetaData) Proxy.newProxyInstance(
                DatabaseMetaData.class.getClassLoader(),
                new Class<?>[]{DatabaseMetaData.class}, h);
    }

    static Connection connection(DatabaseMetaData meta) {
        InvocationHandler h = new InvocationHandler() {
            boolean closed;
            public Object invoke(Object proxy, Method method, Object[] args)
                    throws Throwable {
                switch (method.getName()) {
                    case "getMetaData":
                        if (closed) throw new SQLException("Connection closed");
                        return meta;
                    case "close": closed = true; return null;
                    case "isClosed": return closed;
                    default: throw new SQLFeatureNotSupportedException(
                            "Fixture Connection: " + method.getName());
                }
            }
        };
        return (Connection) Proxy.newProxyInstance(
                Connection.class.getClassLoader(),
                new Class<?>[]{Connection.class}, h);
    }

    public static void main(String[] args) throws SQLException {
        Connection connection = connection(fixture());
        try (connection) {
            DatabaseMetaData meta = connection.getMetaData();
            System.out.println("database=" + meta.getDatabaseProductName());
            System.out.println("driver=" + meta.getDriverName());
            System.out.println("jdbc=" + meta.getJDBCMajorVersion()
                    + "." + meta.getJDBCMinorVersion());
            System.out.println("transactions=" + meta.supportsTransactions());
            System.out.println("savepoints=" + meta.supportsSavepoints());
            System.out.println("batch=" + meta.supportsBatchUpdates());
            System.out.println("generated-keys=" + meta.supportsGetGeneratedKeys());

            boolean scroll = meta.supportsResultSetType(
                    ResultSet.TYPE_SCROLL_INSENSITIVE);
            boolean updatable = meta.supportsResultSetConcurrency(
                    ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_UPDATABLE);
            System.out.println("scroll-insensitive=" + scroll);
            System.out.println("scroll-updatable=" + updatable);
            require(scroll && !updatable, "Unsupported concurrency must be gated");

            boolean isolation = meta.supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_READ_COMMITTED);
            System.out.println("read-committed=" + isolation);
            require(isolation, "Expected isolation support");

            String pattern = literalPattern(meta, "order_%");
            System.out.println("literal-pattern=" + pattern);
            require("order\\_\\%".equals(pattern), "Pattern escaping");

            try (ResultSet tables = meta.getTables(null, null, "%",
                    new String[]{"TABLE"})) {
                int count = 0;
                while (tables.next()) {
                    System.out.println("table=" + tables.getString("TABLE_SCHEM")
                            + "." + tables.getString("TABLE_NAME"));
                    count++;
                }
                require(count == 2, "Expected exactly two table metadata rows");
            }
            try (ResultSet columns = meta.getColumns(null, "public", "customers", "%")) {
                require(columns.next(), "No columns");
                System.out.println("column=" + columns.getString("COLUMN_NAME")
                        + ":" + columns.getString("TYPE_NAME"));
                require(columns.getInt("DATA_TYPE") == Types.BIGINT, "wrong SQL type");
                require(columns.getInt("NULLABLE") ==
                        DatabaseMetaData.columnNoNulls, "wrong nullability");
            }
            try (ResultSet keys = meta.getPrimaryKeys(null, "public", "customers")) {
                require(keys.next(), "no PK");
                System.out.println("pk=" + keys.getString("COLUMN_NAME"));
            }
        }
        require(connection.isClosed(), "try-with-resources did not close");
        System.out.println("closed=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 9.2. Chạy từ terminal

Lưu code trên vào `MetadataContractsDemo.java` trong thư mục trống, biên dịch bằng JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 MetadataContractsDemo.java
java MetadataContractsDemo
~~~

**Stdout chính xác** đã kiểm thử bằng **OpenJDK 24**, compile target `--release 17`:

~~~text
database=TrainingDB
driver=FixtureDriver
jdbc=4.0
transactions=true
savepoints=false
batch=true
generated-keys=true
scroll-insensitive=true
scroll-updatable=false
read-committed=true
literal-pattern=order\_\%
table=public.customers
table=public.orders
column=id:BIGINT
pk=id
closed=true
tests=PASS
~~~

### 9.3. Những điều bài test thực sự chứng minh

| Kiểm thử | Ý nghĩa |
| --- | --- |
| `database=TrainingDB` và `driver=FixtureDriver` | Code lấy product/driver name qua metadata API |
| `jdbc=4.0` | Fixture **báo cáo** version 4.0; không phải kết quả đo driver vendor |
| `transactions=true`, `savepoints=false` | Code phải phân biệt transaction support với savepoint support |
| `batch=true`, `generated-keys=true` | Capability flags có thể kiểm tra được, nhưng không có SQL nào thực thi |
| `scroll-insensitive=true`, `scroll-updatable=false` | Type support **khác** concurrency support |
| `read-committed=true` | API kiểm tra isolation level cụ thể |
| `literal-pattern=order\_\%` | Code xử lý `%`/`_` như các ký tự literal trong metadata search pattern |
| `table=public.customers`, `table=public.orders` | Đọc `getTables` qua `ResultSet.next/getString` |
| `column=id:BIGINT` | Đọc schema columns và kiểu SQL; assert `Types.BIGINT` |
| `pk=id` | Đọc primary key metadata |
| `closed=true` | Try-with-resources gọi `Connection.close()` |

**Giới hạn nghiêm ngặt:** dynamic proxy ở demo chỉ triển khai đúng các methods dùng trong test. Nó **không phải JDBC driver thực**, không có connection tới DB, và `getTables/getColumns/getPrimaryKeys` chỉ trả dữ liệu giả, không phải engine discovery đầy đủ. Không copy proxy này vào production hoặc dùng nó làm bằng chứng driver/database bất kỳ hỗ trợ chức năng gì.

### 9.4. Tại sao dùng mock thay vì viết "SQL tests" giả?

Nếu không có database, việc in `supportsTransactions=true` rồi khẳng định transaction đã commit là **sai**. Bài lab chỉ kiểm tra logic phát hiện khả năng và cách xử lý `ResultSet`. **Integration test có vendor driver và DB thực mới có thể kiểm tra** hành vi isolation, SQL types, errors, physical connection và metadata visibility.

## 10. Inspector dùng với DataSource thật (compile được, chạy cần DB)

Đây là code theo hướng production hơn: nhận một `javax.sql.DataSource` đã cấu hình bởi ứng dụng/framework, mở connection, in vài capability flags và liệt kê tối đa 10 bảng trong schema hiện tại.

Tệp `JdbcMetadataInspector.java`:

~~~java
import java.io.PrintStream;
import java.sql.*;
import java.util.Objects;
import javax.sql.DataSource;

public final class JdbcMetadataInspector {
    private JdbcMetadataInspector() {}

    public static void inspect(DataSource source, PrintStream out)
            throws SQLException {
        Objects.requireNonNull(source);
        Objects.requireNonNull(out);
        try (Connection connection = source.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            out.println("database=" + meta.getDatabaseProductName());
            out.println("database-version=" + meta.getDatabaseProductVersion());
            out.println("driver=" + meta.getDriverName());
            out.println("driver-version=" + meta.getDriverVersion());
            out.println("jdbc=" + meta.getJDBCMajorVersion()
                    + "." + meta.getJDBCMinorVersion());
            out.println("transactions=" + meta.supportsTransactions());
            out.println("savepoints=" + meta.supportsSavepoints());
            out.println("batch=" + meta.supportsBatchUpdates());
            out.println("generated-keys=" + meta.supportsGetGeneratedKeys());
            out.println("forward-read-only=" + meta.supportsResultSetConcurrency(
                    ResultSet.TYPE_FORWARD_ONLY, ResultSet.CONCUR_READ_ONLY));

            String catalog = connection.getCatalog();
            String schema = connection.getSchema(); // JDBC 4.1 (Java 7)
            out.println("catalog=" + catalog);
            out.println("schema=" + schema);

            try (ResultSet tables = meta.getTables(
                    catalog, schema, "%", new String[]{"TABLE"})) {
                int shown = 0;
                while (shown < 10 && tables.next()) {
                    out.println("table=" + tables.getString("TABLE_SCHEM")
                            + "." + tables.getString("TABLE_NAME"));
                    shown++;
                }
            }
        }
    }
}
~~~

Biên dịch độc lập:

~~~bash
javac -encoding UTF-8 --release 17 JdbcMetadataInspector.java
~~~

**Đã kiểm tra biên dịch thành công trên OpenJDK 24 với `--release 17`.** Tệp không có `main`, do đó không chạy được bằng `java JdbcMetadataInspector`. Ứng dụng phải tạo/cung cấp `DataSource` của vendor và gọi:

~~~java
// Đoạn minh họa bên trong ứng dụng đã tạo DataSource source:
JdbcMetadataInspector.inspect(source, System.out);
~~~

**Không có stdout cố định**: tên DB, JDBC version, support flags và danh sách tables hoàn toàn phụ thuộc kết nối thực. Không tuyên bố đã kiểm thử integration với DB vendor trong khi chỉ mới compile.

### 10.1. Giới hạn chủ ý của inspector

- `connection.getSchema()` có từ JDBC 4.1, hợp lệ với `--release 17`.
- `schema` được truyền trực tiếp như một `schemaPattern`. Nếu schema thật chứa `_` hoặc `%`, phải **escape bằng `getSearchStringEscape` trước khi dùng như pattern** để tránh match nhiều schema; hoặc chọn phạm vi `null` và lọc kết quả có giới hạn. Inspector là ví dụ cơ bản, chưa giải quyết hết trường hợp ấy.
- `getTables(..., new String[]{"TABLE"})` chỉ tìm type `TABLE`. Nếu DB dùng table types khác, có thể cần `getTableTypes()` trước.
- Giới hạn hiển thị 10 rows giúp giảm lượng output và xử lý phía client, **không đảm bảo driver/DB chỉ thực hiện tối đa 10 row network work**. Query metadata vẫn có thể tốn tài nguyên.
- Không in `getURL()` hoặc `getUserName()` vì có thể lộ thông tin cấu hình.
- Không cache `Connection`, `ResultSet` hoặc chính đối tượng metadata vượt vòng đời connection.
- `try-with-resources` đóng metadata ResultSet rồi trả connection về pool/đóng theo implementation.
- `getCatalog()`/`getSchema()` có thể null; console hiển thị `null` là bình thường. Tên catalog/schema không thống nhất giữa các DBMS.

### 10.2. Gợi ý tích hợp với vendor driver

Nếu dùng PostgreSQL, MySQL, Oracle Database hoặc SQL Server, chọn **JDBC driver hiện đại chính thức/được hỗ trợ**, đồng nhất với phiên bản Java và database server. Dùng `DataSource` của driver hoặc pool được cấu hình bởi framework. Không copy một JDBC URL, username hoặc password giả định từ bài học thành dữ liệu production.

Tạo integration test riêng với DB sandbox có schema/tables mẫu, quyền readonly thích hợp, rồi gọi `inspect` hoặc helper tương đương. Cần so sánh các flags và metadata rows trên **chính môi trường được hỗ trợ**.

## 11. Xử lý khả năng hỗ trợ trong ứng dụng đúng cách

### 11.1. Feature gate có nhánh dự phòng

Mẫu hợp lệ về ý tưởng:

~~~java
if (meta.supportsBatchUpdates()) {
    // Có thể dùng addBatch()/executeBatch() nếu workload phù hợp.
} else {
    // Thực thi từng PreparedStatement trong transaction thích hợp.
}
~~~

Đây là **đoạn minh họa**, không có SQL/transaction thực. Dù `supportsBatchUpdates() == true` vẫn cần `SQLException` handling khi thực thi. Còn nếu false, có thể chạy statements lẻ, nhưng **không được âm thầm làm mất yêu cầu atomicity**.

### 11.2. Không suy từ JDBC version

Phản ví dụ:

~~~java
boolean supportsEverything = meta.getJDBCMajorVersion() >= 4;
~~~

Đây là **đoạn phản ví dụ**. Một số JDBC features optional và phụ thuộc DBMS, SQL type, schema, settings và driver. Nếu cần `SQLXML` hoặc `RowId`, hãy đọc docs vendor, kiểm tra metadata chuyên biệt nếu có, và **thực thi integration test trên DB thật**.

### 11.3. Tính năng hỗ trợ còn tùy query

`supportsResultSetConcurrency(TYPE_SCROLL_INSENSITIVE, CONCUR_UPDATABLE)` nói về khả năng chung của combination. Nó không chứng minh một query `JOIN GROUP BY` sẽ tạo ResultSet updatable. Nếu application dựa vào updatable cursor, hãy test đúng loại SQL, permissions và type/primary key, không chỉ kiểm tra flag.

### 11.4. Các metadata calls có thể thất bại

`DatabaseMetaData` methods thường khai báo `throws SQLException`. Một số driver báo `SQLFeatureNotSupportedException` khi chưa triển khai tính năng. Trong công cụ đa DB, phân biệt:

- **Feature không được hỗ trợ:** chọn fallback an toàn hoặc thông báo rõ.
- **Kết nối/permission lỗi:** không coi là “database không có tables”.
- **Trả ResultSet rỗng:** có thể do không có objects, do filter quá hẹp, do quyền hoặc do metadata không khả dụng.
- **Metadata xung đột với thực thi:** ưu tiên xử lý lỗi thực thi và ghi nhận vendor + driver version trong diagnostics đã lọc.

Không viết `catch(SQLException e) { return Collections.emptyList(); }` cho mọi lỗi metadata, vì làm mất khả năng phân biệt “không có kết quả” với “không truy cập được”.

## 12. Bảo mật và vận hành khi khám phá schema

### 12.1. Metadata là thông tin nhạy cảm

Tên tables, columns, procedures, constraints và schemas có thể làm lộ cấu trúc nội bộ. Không xây một HTTP endpoint tự do trả `getTables(null,null,"%",null)` cho bất kỳ người dùng nào. Cần authentication, authorization, rate limits, scope filters và output minimization.

### 12.2. Metadata không phải bảng quyền

`getTablePrivileges/getColumnPrivileges` có thể hỗ trợ hiển thị quyền, nhưng **không phải oracle bảo đảm quyền truy cập**: driver, database roles, row-level security và execution context vẫn quyết định. Một bảng “được liệt kê” không đồng nghĩa người dùng hiện tại có quyền SELECT/UPDATE trên mọi rows.

### 12.3. SQL patterns khác SQL injection

Khi người dùng nhập `"customers_2026"` và ứng dụng đưa vào `getTables`, vấn đề đầu tiên là **pattern widening** (`_` là wildcard). Dùng `getSearchStringEscape` khi cần literal match.

Khi xây SQL thực như `SELECT * FROM <table>`, vấn đề là **SQL identifier injection**; cần allowlist identifier, quoting đúng chuẩn và phân quyền. `PreparedStatement` dấu `?` bảo vệ **giá trị**, không thay thế identifier. Không đem metadata wildcard escape làm SQL escaping.

### 12.4. Chi phí và availability

Schema discovery có thể tạo nhiều truy vấn hệ thống, lock/roundtrip tùy DB. Chạy metadata scan trong startup/migration/administration workflow có giới hạn hoặc cache, không quét toàn DB mỗi request. Nếu kết nối bị mất khi đang lặp ResultSet, xử lý SQLException và đóng tài nguyên ngay, không giữ cursor treo.

### 12.5. Đừng log secrets

`DatabaseMetaData.getURL()`, `getUserName()`, driver exceptions và các server diagnostics có thể tiết lộ host, tài khoản, thậm chí cấu hình kết nối. Log tối thiểu, lọc credentials, giữ bí mật trong secret manager và không gửi trực tiếp cho end users.

## 13. Những lỗi phổ biến

| Lỗi | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Coi `DatabaseMetaData` là API mới của JDBC 4.0 | Nó đã có từ JDBC 1.1 | Học lịch sử chính xác và dùng các contracts còn hỗ trợ |
| “JDBC version 4+” nghĩa tất cả features chạy | Optional capabilities và vendor differences | Dùng `supports...` cụ thể + integration test |
| Gọi `supportsResultSetType` rồi cho rằng updatable | Type khác concurrency | Dùng thêm `supportsResultSetConcurrency(type, mode)` |
| Dùng `isValid` thay metadata | `isValid` chỉ kiểm tra kết nối | Dùng `connection.getMetaData()` cho khả năng/khám phá |
| `supportsBatchUpdates()==true` nghĩa batch atomic | Batch support không đảm bảo transaction boundary | Quản lý transaction riêng và lỗi batch |
| `supportsSavepoints()==false` nhưng vẫn tạo savepoint | DB/driver không báo hỗ trợ | Fallback hợp lệ hoặc không cho chức năng cần savepoint |
| Đọc `getColumns` theo vị trí tùy ý | Metadata ResultSet có labels chuẩn | Dùng `COLUMN_NAME`, `DATA_TYPE`, `TYPE_NAME`... |
| Nhầm SQL type name với Java type | `TYPE_NAME` vendor-specific, `DATA_TYPE` là `Types` code | Xác định mapping bằng metadata/docs |
| `getTables(null,null,"%",null)` trong request UI | Scan có thể rất rộng, lộ schema | Scope table type/schema, cache và kiểm soát quyền |
| `"customers_2026"` là tên literal trong pattern | `_` là wildcard | Escape qua `getSearchStringEscape()` |
| Dùng `getIdentifierQuoteString` để escape SQL value | Identifier quoting khác value binding | `PreparedStatement` cho values; allowlist identifiers |
| Giả định catalog/schema luôn hiện hữu | DBMS có mô hình namespace khác nhau | Xử lý `null` và dùng metadata methods |
| Bỏ quên đóng ResultSet metadata | Cursor/resources có thể bị giữ | Try-with-resources |
| Cho `ResultSet` sống lâu hơn connection | Cursor phụ thuộc connection | Đọc và chuyển thành DTO/immutable snapshot |
| Trả danh sách rỗng với mọi SQLException | Che lỗi quyền/network | Phân biệt empty vs failure |
| Test mock nhưng tuyên bố DB thật hỗ trợ | Mock phản ánh dữ liệu lập trình viên tạo | Integration test với vendor driver và DB |
| Dùng Java17 và nói try-with-resources là tính năng Java6 | Nó có từ JDBC4.1/Java7 | Phân biệt API timeline |
| Dựa vào `TABLE_SCHEM` luôn khác null | Một số DB không có schema | Xử lý nullable labels |
| Tự thêm identifiers người dùng vào SQL | SQL injection/invalid identifier | Allowlist, quote/validate theo DB |
| Dùng metadata làm kiểm tra quyền tuyệt đối | Quyền thực còn phụ thuộc roles/RLS/context | Authorization và execution policy riêng |

## 14. Checklist kiểm thử với database thật

Khi có JDBC driver + database test, hãy kiểm tra tối thiểu:

1. **Kết nối:** `DataSource.getConnection()` thành công; `getMetaData()` không null, connection đóng đúng.
2. **Identity:** tên DB, driver, JDBC version được ghi nhận dưới dạng diagnostics đã lọc.
3. **Transactions:** `supportsTransactions` và `getDefaultTransactionIsolation` phù hợp, thử commit/rollback hai connections.
4. **Savepoints:** nếu `supportsSavepoints`, thử tạo, rollback và release đúng transaction.
5. **Batch:** `supportsBatchUpdates` tương ứng với `executeBatch` trên schema mẫu; xử lý partial results/BatchUpdateException.
6. **Generated keys:** nếu hỗ trợ, insert schema có generated ID rồi lấy key và kiểm chứng.
7. **ResultSet modes:** thử type và concurrency combinations đã báo hỗ trợ với query phù hợp.
8. **Schemas/catalogs:** `getCatalogs/getSchemas/getTableTypes` phản ánh objects/permissions mong đợi.
9. **Tables/columns:** tạo bảng có tên chứa `_` và thử `getSearchStringEscape`; kiểm tra `DATA_TYPE`, `COLUMN_SIZE` và nullability.
10. **Composite primary/foreign keys:** kiểm tra `KEY_SEQ` và tên bảng/cột hai phía.
11. **Limitations:** thử một feature không hỗ trợ, ghi nhận loại SQLException và fallback.
12. **Connection pooling:** metadata từ logical connection và lifecycle ResultSet không leak khi trả connection.
13. **Read permissions:** user bị hạn chế không thấy bảng nhạy cảm ngoài policy (thực nghiệm theo DB).
14. **Driver update:** chạy lại khi nâng phiên bản JDK/driver/database, ghi lại những thay đổi metadata.
15. **Performance:** đo thời gian/roundtrip của full discovery và query scoped vào catalog/schema/table.

Bài lab mock ở mục 9 **không thay thế checklist này**. Chỉ có test thật mới xác nhận khả năng của một DBMS và driver cụ thể dưới schema/permissions thực tế.

## 15. Câu hỏi tự đánh giá

**Câu 1.** `DatabaseMetaData` do DB server hay JDK tự tạo?

**Đáp án:** Nó là interface chuẩn của JDBC; **driver** triển khai và trả qua `Connection.getMetaData()`. Kết quả mô tả phối hợp driver + DBMS và connection hiện tại.

**Câu 2.** Có thể chỉ nhìn `getJDBCMajorVersion() == 4` rồi bật savepoints và generated keys cho mọi database không?

**Đáp án:** Không. Sử dụng `supportsSavepoints`, `supportsGetGeneratedKeys` và integration tests với DB thật. JDBC version không chứng minh mỗi capability optional.

**Câu 3.** `supportsResultSetType(TYPE_SCROLL_INSENSITIVE)==true` có đồng nghĩa với `CONCUR_UPDATABLE` không?

**Đáp án:** Không. Kiểm tra cặp `supportsResultSetConcurrency(type, concurrency)` riêng; cả khi true, một query cụ thể có thể không updatable.

**Câu 4.** Khi `getTables` trả ResultSet rỗng, kết luận chắc chắn không có bảng tương ứng được không?

**Đáp án:** Không. Phải kiểm tra catalog/schema/pattern/type filters, quyền truy cập, metadata availability và lỗi truy vấn; 0 rows không giải thích lý do.

**Câu 5.** Vì sao tên `customer_2026` phải escape khi dùng trong `getTables`?

**Đáp án:** Tham số là **pattern**, trong đó `_` match đúng một ký tự. Dùng `getSearchStringEscape()` để biểu diễn literal underscore.

**Câu 6.** Có được dùng `getSearchStringEscape()` để ngăn SQL injection trong `SELECT` không?

**Đáp án:** Không. Nó dành cho **metadata search patterns**; SQL values dùng prepared-statement parameters, identifiers cần validation/allowlist và quoting đúng DBMS.

**Câu 7.** `getColumns` trả `DATA_TYPE` và `TYPE_NAME` khác nhau thế nào?

**Đáp án:** `DATA_TYPE` là mã tương ứng `java.sql.Types`, `TYPE_NAME` là tên kiểu theo DBMS. Không suy tất cả vendor hỗ trợ mọi kiểu SQL theo cùng cách.

**Câu 8.** Vì sao phải đóng `ResultSet` metadata?

**Đáp án:** Nó có thể giữ cursor và tài nguyên phía driver/server. Dùng try-with-resources trong phạm vi connection còn mở và chuyển data cần dùng lâu dài thành immutable snapshot.

**Câu 9.** Demo in `transactions=true` thì có phải kiểm tra được một transaction đã commit không?

**Đáp án:** Không. Đó là fixture trong dynamic proxy, không có DB. Hãy chạy integration test với database thật.

**Câu 10.** `Connection.getSchema()` có phải JDBC 4.0/Java 6 không?

**Đáp án:** Không. API này bổ sung ở **JDBC 4.1/Java 7**; hợp lệ với ví dụ `--release 17` nhưng không nên gán là API Java 6.

### Bài tập thực hành

1. Sửa fixture `supportsSavepoints` thành true; viết test chọn đường savepoint, nhưng không tuyên bố mock thực hiện savepoint trên DB.
2. Sửa fixture `supportsResultSetConcurrency(TYPE_SCROLL_INSENSITIVE, CONCUR_UPDATABLE)` thành true, rồi viết feature gate chọn query mode tương ứng.
3. Thêm một `ResultSet` metadata rỗng và assert code không ném exception ở `while (rs.next())`.
4. Thêm `getImportedKeys` mock với hai cột composite FK và test `KEY_SEQ`/`FKCOLUMN_NAME`.
5. Thêm input `"order_%\\draft"` vào `literalPattern` và assert escape token, `_` và `%` đều được escape.
6. Dùng DataSource và database sandbox để tạo bảng tên có underscore; so sánh kết quả `getTables` trước/sau escape.
7. Thử `getTableTypes()` trên DB thật rồi lấy cả `TABLE` và `VIEW`; không giả định tên table types giống hệt qua vendors.
8. Viết DTO `TableInfo` cho metadata rows, đọc tất cả data trong try-with-resources rồi **đóng ResultSet trước khi trả danh sách**.
9. Thiết lập pool và thử `getMetaData` trên logical connection; xác minh không giữ cursor/connection lâu ngoài nhu cầu.
10. Lập bảng so sánh `getJDBCMajorVersion` với `supportsBatchUpdates`/`supportsSavepoints` của hai JDBC drivers hiện đại trên hai DBMS khác nhau và giải thích sự khác biệt.

## 16. Tài liệu chính thức còn áp dụng

- [Java SE 26 — DatabaseMetaData](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DatabaseMetaData.html): hợp đồng phát hiện DB/driver features, metadata result sets, search patterns, supports methods.
- [Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `getMetaData`, transactions, isolation, `getCatalog/getSchema`.
- [Java SE 26 — ResultSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): cursor, getters và lifecycle.
- [Java SE 26 — Statement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html): batch operations, generated keys, query modes.
- [Java SE 26 — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): parameter binding và batch.
- [Java SE 26 — SQLException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, exception chaining.
- [Java SE 26 — SQLFeatureNotSupportedException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): feature unsupported contract.
- [Java SE 26 — DatabaseMetaData package context](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): lịch sử JDBC 4.x và nguồn gốc các features.
- [Java SE 26 — javax.sql.DataSource](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): connection factory cho ứng dụng.
- [Java SE 26 — Types](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Types.html): SQL type codes được trả qua `DATA_TYPE`.
- [Java SE 17 — DatabaseMetaData](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html): đối chiếu API biên dịch `--release 17`.

**Ghi nhớ:** `DatabaseMetaData` là công cụ **khám phá khả năng và cấu trúc DB của cặp driver/DBMS thực tế**. Dùng `supports...` để quyết định nhánh hợp lệ, `getTables/getColumns/getPrimaryKeys` để đọc schema, `getSearchStringEscape` cho metadata patterns, và **đóng metadata ResultSet** đúng lifecycle. Kết quả hỗ trợ được báo cáo vẫn cần kiểm chứng bằng thao tác SQL thực trong integration tests; không dựa vào JDBC version hay một mock để khẳng định tính năng production.
