# Cấu hình catalog, schema và thông số phiên làm việc

## 1. Vị trí của catalog, schema trong kiến trúc JDBC

**JDBC (Java Database Connectivity)** là API Java cho phép ứng dụng truy cập cơ sở dữ liệu quan hệ thông qua driver. Sau khi lấy được một `java.sql.Connection`, ứng dụng cần biết câu SQL sẽ truy cập đối tượng ở **không gian tên** nào và những **thiết lập phiên làm việc** nào đang có hiệu lực.

Hai khái niệm quan trọng để xác định đối tượng dữ liệu là:

- **Catalog**: cấp nhóm đối tượng dữ liệu mà JDBC nhận diện qua các API về catalog. Trên một số hệ quản trị, catalog gần với khái niệm *database*.
- **Schema**: không gian tên dùng để tổ chức các đối tượng như bảng, view hoặc thủ tục; thường nằm bên trong một catalog hoặc database theo mô hình của hệ quản trị.

Ví dụ minh họa một hệ thống bán hàng có cấu trúc phân cấp:

```text
Catalog: commerce
  ├── Schema: sales
  │     ├── orders
  │     └── order_items
  └── Schema: inventory
        └── products
```

Trong mô hình này, bảng `orders` thuộc schema `sales`; còn `products` thuộc `inventory`. Khi dùng `SELECT * FROM orders`, hệ quản trị cần xác định **schema hiện hành hoặc quy tắc tra cứu tên** để biết bảng nào được nhắc tới.

> **Lưu ý:** Sơ đồ trên là mô hình khái niệm. Không phải mọi DBMS đều có cả hai cấp theo cùng cách hoặc cho phép chuyển catalog/schema trên một kết nối. Tên gọi và cú pháp phụ thuộc hệ quản trị cùng JDBC driver.

## 2. Catalog và schema khác nhau thế nào giữa các hệ quản trị?

JDBC cung cấp các phương thức thống nhất, nhưng ý nghĩa catalog/schema vẫn chịu ảnh hưởng của DBMS:

| Hệ quản trị | Cách hiểu thường gặp | Điều cần lưu ý |
|---|---|---|
| **PostgreSQL** | Catalog thường tương ứng database đang kết nối; bên trong database có nhiều schema | Việc đổi sang database khác thường cần kết nối mới; schema và `search_path` chi phối cách tìm tên bảng chưa đủ điều kiện |
| **MySQL** | Cái thường được gọi là database hay được driver ánh xạ thành catalog | Khả năng hỗ trợ `setSchema()` và cách ánh xạ schema phụ thuộc driver; không giả định giống PostgreSQL |
| **SQL Server** | Database là catalog; schema (như `dbo`, `sales`) nằm trong database | Có thể gặp tên nhiều phần dạng `database.schema.table`, tùy ngữ cảnh và quyền |
| **Oracle Database** | Schema gắn với người sở hữu đối tượng; nhiều hệ thống không sử dụng catalog theo cách trên | Không tự mặc định tài khoản kết nối có quyền hoặc khả năng đổi schema hiện hành |

Vì vậy, `setCatalog("commerce")` và `setSchema("sales")` **không có nghĩa** là JDBC đã tạo catalog hay schema. Chúng là các thao tác yêu cầu thay đổi ngữ cảnh làm việc của kết nối, nếu driver và hệ quản trị hỗ trợ. Việc tạo database, tạo schema và cấp quyền là các thao tác khác.

## 3. Tên đầy đủ và tên không đủ điều kiện của bảng

Giả sử có hai schema, `sales` và `archive`, cùng chứa một bảng tên `orders`:

```text
sales.orders        ← đơn hàng đang hoạt động
archive.orders      ← đơn hàng đã lưu trữ
```

Khi câu lệnh chỉ ghi:

```sql
SELECT order_id FROM orders;
```

DBMS sẽ phân giải `orders` theo ngữ cảnh hiện tại, chẳng hạn schema mặc định hoặc danh sách schema tìm kiếm. Nếu ngữ cảnh không đúng, câu lệnh có thể tìm sai bảng hoặc báo không tìm thấy bảng.

Khi hệ quản trị hỗ trợ cách viết đủ điều kiện theo schema, có thể ghi rõ:

```sql
SELECT order_id FROM sales.orders;
```

Một số hệ quản trị còn hỗ trợ tên gồm catalog, schema và bảng, ví dụ `commerce.sales.orders`, nhưng **không có một cú pháp tên ba phần duy nhất dùng được cho mọi DBMS**. Ngoài ra, cách viết hoa/thường và quy tắc quote tên định danh có thể khác nhau.

Đối với SQL cần truy cập chính xác một bảng bất kể cấu hình phiên, **tên bảng đủ điều kiện** thường giúp mã dễ hiểu hơn. Nếu phải chọn schema/catalog động từ đầu vào, cần kiểm tra bằng danh sách cho phép: tham số `?` trong `PreparedStatement` dùng cho **giá trị**, không thay thế trực tiếp tên schema, bảng hay cột.

## 4. Các phương thức JDBC để đọc và đặt catalog, schema

`Connection` cung cấp các phương thức sau:

| Phương thức | Ý nghĩa | Lưu ý |
|---|---|---|
| `getCatalog()` | Đọc tên catalog hiện hành theo driver | Có thể trả `null` nếu không có hoặc không áp dụng được |
| `setCatalog(String catalog)` | Yêu cầu thay đổi catalog hiện hành | Có thể thất bại hoặc không có hiệu lực theo cách mong muốn nếu DBMS/driver không hỗ trợ |
| `getSchema()` | Đọc schema hiện hành theo driver | Có thể trả `null` hoặc ném lỗi nếu chức năng không được hỗ trợ |
| `setSchema(String schema)` | Yêu cầu thay đổi schema hiện hành | Khả năng hỗ trợ và cách ánh xạ sang DBMS phụ thuộc driver |

`getSchema()` và `setSchema()` được bổ sung vào JDBC 4.1. Khi môi trường chạy bằng JDBC driver cũ hoặc không triển khai đủ tính năng, có thể gặp `SQLFeatureNotSupportedException` (một loại `SQLException`). Các thao tác cũng có thể thất bại do quyền, tên không tồn tại hoặc lỗi truy cập cơ sở dữ liệu.

Ví dụ đọc thông tin ngữ cảnh mà driver báo về:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class SessionInspector {
    private final DataSource dataSource;

    public SessionInspector(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printNamespace() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            System.out.println("Catalog: " + connection.getCatalog());
            System.out.println("Schema : " + connection.getSchema());
        }
    }
}
```

Ví dụ giả định `DataSource` đã được cấu hình và driver hỗ trợ các phương thức trên. `getCatalog()`/`getSchema()` phản ánh **cách driver nhận diện ngữ cảnh**; không nhất thiết liệt kê đầy đủ một danh sách tìm kiếm schema hay mọi thông số phiên riêng của DBMS.

### Đổi schema trong phạm vi một công việc

Ví dụ sau giả định DBMS/driver hỗ trợ `setSchema("sales")`, schema này tồn tại và có bảng `orders(order_id)`. Ứng dụng đặt schema trước khi chạy câu SQL chưa đủ điều kiện, sau đó khôi phục schema cũ trước khi trả kết nối:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class SalesOrderReader {
    private final DataSource dataSource;

    public SalesOrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printOrderIds() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            String previousSchema = connection.getSchema();

            try {
                connection.setSchema("sales");

                try (PreparedStatement statement = connection.prepareStatement(
                        "SELECT order_id FROM orders ORDER BY order_id");
                     ResultSet rs = statement.executeQuery()) {

                    while (rs.next()) {
                        System.out.println(rs.getLong("order_id"));
                    }
                }
            } finally {
                connection.setSchema(previousSchema);
            }
        }
    }
}
```

`getSchema()` được dùng để lưu giá trị trước khi thay đổi. Khối `finally` cố gắng khôi phục schema ngay cả khi truy vấn ném ngoại lệ; sau đó `try-with-resources` đóng `Connection`. Mã giả định driver chấp nhận cả việc khôi phục giá trị schema ban đầu (kể cả `null` nếu đó là giá trị trả về). Trong ứng dụng dùng connection pool hoặc framework quản lý phiên/giao dịch, phải tuân theo chính sách reset trạng thái của hệ thống; lỗi khôi phục schema cần được ghi nhận và xử lý, vì nó có thể che mất lỗi truy vấn ban đầu.

Nếu driver không hỗ trợ đổi schema, một phương án thường gặp là dùng tên bảng đủ điều kiện trong SQL, chẳng hạn `sales.orders` trên hệ quản trị hỗ trợ cú pháp này. **Không áp dụng mù quáng** `setSchema()` hoặc cú pháp SQL đặc thù cho tất cả các loại database.

## 5. Tìm hiểu khả năng hỗ trợ bằng `DatabaseMetaData`

JDBC cung cấp `java.sql.DatabaseMetaData` để ứng dụng khám phá cách driver mô tả catalog, schema và tên đối tượng.

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public static void printNameRules(Connection connection) throws SQLException {
    DatabaseMetaData meta = connection.getMetaData();

    System.out.println("Tên gọi catalog: " + meta.getCatalogTerm());
    System.out.println("Tên gọi schema : " + meta.getSchemaTerm());
    System.out.println("Dấu phân cách catalog: " + meta.getCatalogSeparator());
    System.out.println("Schema trong DML: " +
            meta.supportsSchemasInDataManipulation());
    System.out.println("Catalog trong DML: " +
            meta.supportsCatalogsInDataManipulation());
}
```

Ở ví dụ này, `connection` là một kết nối JDBC đang mở. Một số phương thức hữu ích khác là `getCatalogs()` và `getSchemas()` để tra các catalog/schema có thể nhìn thấy, hoặc `getTables(catalog, schemaPattern, tableNamePattern, types)` để tìm bảng.

Chẳng hạn, việc liệt kê bảng thuộc một schema có thể thực hiện qua metadata:

```java
try (ResultSet tables = connection.getMetaData().getTables(
        null, "sales", "%", new String[] {"TABLE"})) {
    while (tables.next()) {
        System.out.println(tables.getString("TABLE_NAME"));
    }
}
```

Ở đây `connection` là kết nối đang mở và `ResultSet` là `java.sql.ResultSet`. Tham số đầu `null` có nghĩa là **không dùng catalog để thu hẹp phạm vi tìm kiếm**; `"sales"` là mẫu tên schema, `"%"` là ký tự đại diện cho tên bảng trong mẫu tìm kiếm metadata. Kết quả phụ thuộc quyền truy cập, driver và cách DBMS ánh xạ catalog/schema; `null` không có nghĩa là “catalog tên `null`”.

Metadata hữu ích để **khảo sát khả năng hỗ trợ và các tên thực tế**, nhưng không thay thế việc đọc tài liệu driver khi cần biết chính xác cách `setCatalog()` hoặc `setSchema()` ảnh hưởng tới phiên.

## 6. Thông số phiên làm việc ngoài catalog và schema

Một `Connection` còn chứa hoặc tác động tới nhiều thuộc tính của **phiên truy cập cơ sở dữ liệu**. Các thuộc tính này ảnh hưởng trực tiếp tới giao dịch, tính nhất quán, hiệu suất và cách câu SQL được thực hiện.

| Thiết lập JDBC | API thường dùng | Ý nghĩa và lưu ý |
|---|---|---|
| Chế độ tự commit | `getAutoCommit()` / `setAutoCommit(boolean)` | Khi `true`, mỗi câu lệnh có thể được commit theo quy tắc JDBC; đặt `false` để điều khiển giao dịch bằng `commit()` và `rollback()` |
| Mức cô lập giao dịch | `getTransactionIsolation()` / `setTransactionIsolation(int)` | Chọn mức như `TRANSACTION_READ_COMMITTED`, nếu DBMS/driver hỗ trợ; tác động tới hiện tượng đồng thời |
| Gợi ý chỉ đọc | `isReadOnly()` / `setReadOnly(boolean)` | Có thể giúp driver/DBMS tối ưu; **không phải cơ chế cấp quyền bảo mật** |
| Catalog hiện hành | `getCatalog()` / `setCatalog(String)` | Điều chỉnh ngữ cảnh catalog theo khả năng driver |
| Schema hiện hành | `getSchema()` / `setSchema(String)` | Điều chỉnh ngữ cảnh schema theo khả năng driver |
| Chế độ giữ con trỏ khi commit | `getHoldability()` / `setHoldability(int)` | Kiểm soát con trỏ `ResultSet` có thể đóng hay giữ sau commit, tùy loại kết quả và driver |
| Thông tin client | `getClientInfo()` / `setClientInfo(...)` | Đặt thuộc tính client được driver hỗ trợ; không nên dùng để xác thực hay phân quyền |
| Timeout mạng | `getNetworkTimeout()` / `setNetworkTimeout(Executor, int)` | Thời gian tối đa chờ trong một số thao tác mạng của `Connection`; phụ thuộc driver và môi trường |

Đối với isolation và holdability, các hằng số được định nghĩa trong `Connection` và `ResultSet`, ví dụ `Connection.TRANSACTION_REPEATABLE_READ`, `ResultSet.HOLD_CURSORS_OVER_COMMIT`. Không phải hệ quản trị nào cũng hỗ trợ mọi lựa chọn. Có thể hỏi metadata bằng `supportsTransactionIsolationLevel(...)` hoặc `supportsResultSetHoldability(...)`.

**Một số thiết lập dễ bị hiểu sai:**

- `setReadOnly(true)` chỉ là gợi ý JDBC về mục đích chỉ đọc; muốn ngăn ghi dữ liệu phải dùng quyền của cơ sở dữ liệu hoặc cơ chế kiểm soát phù hợp.
- `setClientInfo("ApplicationName", "order-service")` chỉ hoạt động nếu driver công nhận thuộc tính này; có thể phát sinh `SQLClientInfoException`.
- `setNetworkTimeout(...)` không giống `Statement.setQueryTimeout(...)`. Cái thứ nhất liên quan tới thời gian chờ thao tác mạng của kết nối, cái thứ hai yêu cầu giới hạn thời gian thực thi câu lệnh theo API/driver.
- Một số thuộc tính phiên như múi giờ, ngôn ngữ xử lý ngày giờ, `search_path`, vai trò SQL hoặc optimizer settings **không có API `Connection` chung** cho mọi DBMS. Chúng thường phải cấu hình bằng thuộc tính driver, URL kết nối hoặc câu lệnh SQL riêng của nhà cung cấp.

## 7. Thời điểm thay đổi cấu hình và ranh giới giao dịch

Nên thiết lập catalog, schema, mức cô lập, read-only và chế độ auto-commit **trước khi bắt đầu các thao tác SQL phụ thuộc những thuộc tính đó**. Việc thay đổi một số thuộc tính khi giao dịch đang diễn ra có thể bị từ chối, có tác dụng theo quy tắc riêng hoặc tạo ra hành vi khó dự đoán giữa các driver.

Ví dụ giao dịch JDBC với mức cô lập xác định:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public void updateCustomer(DataSource dataSource, long id, String fullName)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        // Cấu hình trước khi bắt đầu giao dịch.
        connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement statement = connection.prepareStatement(
                    "UPDATE customers SET full_name = ? WHERE id = ?")) {
                statement.setString(1, fullName);
                statement.setLong(2, id);
                statement.executeUpdate();
            }

            connection.commit();
        } catch (SQLException | RuntimeException failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                failure.addSuppressed(rollbackError);
            }
            throw failure;
        }
    }
}
```

Giả định bảng `customers(id, full_name)` đã có, `DataSource` được cấu hình phù hợp và DBMS hỗ trợ `TRANSACTION_READ_COMMITTED`. Ví dụ này minh họa cách đặt tham số **trước** giao dịch, commit khi thành công và rollback khi thao tác thất bại. Khi thực tế cần khôi phục các thuộc tính phiên trước khi trả vào pool, phải phối hợp với thư viện pool hoặc transaction manager; không thay đổi auto-commit giữa chừng một cách tùy tiện. Theo JDBC, việc chuyển `autoCommit` có thể kết thúc/commit giao dịch hiện hành.

**Phạm vi hiệu lực:** `setSchema()` ảnh hưởng tới các câu SQL tiếp theo trên **kết nối tương ứng**, không đồng loạt thay đổi mọi kết nối trong ứng dụng. Tương tự, `setTransactionIsolation()` là thuộc tính kết nối, còn chính sách toàn hệ thống có thể do DBMS hoặc framework quy định. Mở kết nối mới có thể nhận các giá trị mặc định khác, hoặc các giá trị đã được pool cấu hình.

## 8. Lệnh SQL thay đổi phiên: mạnh nhưng phụ thuộc nhà cung cấp

Ngoài API chung, nhiều DBMS có cú pháp riêng để thay đổi trạng thái phiên. Ví dụ:

| Hệ quản trị | Ví dụ loại lệnh | Lưu ý |
|---|---|---|
| PostgreSQL | `SET search_path TO sales, public` | Điều chỉnh thứ tự tìm schema cho các tên bảng chưa đủ điều kiện; cần cân nhắc rủi ro từ các schema nằm trong đường tìm kiếm |
| PostgreSQL | `SET LOCAL statement_timeout = '3s'` | Có hiệu lực trong giao dịch hiện tại khi dùng đúng ngữ cảnh; kết thúc giao dịch thì hết tác dụng |
| MySQL | `SET SESSION time_zone = '+00:00'` | Thay đổi múi giờ của phiên MySQL, tác động tới cách một số giá trị thời gian được xử lý |
| SQL Server | `USE SalesDb` | Chọn database trong phiên theo cú pháp SQL Server, nếu được phép |
| Oracle Database | `ALTER SESSION SET CURRENT_SCHEMA = SALES` | Đổi schema dùng để phân giải tên chưa đủ điều kiện; không tự cấp thêm quyền |

Đây là những **ví dụ minh họa của từng DBMS**, không phải SQL chuẩn có thể dùng chung cho mọi driver. Một số hệ quản trị cũng cung cấp tham số trong JDBC URL hoặc `Properties` khi tạo kết nối để thiết lập mặc định phiên. Tên tham số, hỗ trợ timezone/role và thứ tự áp dụng phụ thuộc driver.

Ví dụ PostgreSQL thực thi một câu lệnh cấu hình phiên bằng JDBC:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SET search_path TO sales, public")) {
    statement.execute();
    // Các câu lệnh SQL tiếp theo trên connection sẽ thấy search_path mới.
}
```

Ví dụ giả định `dataSource` và các schema đã được cấu hình đúng. Trên kết nối có pool, **thiết lập kiểu `SET` có thể còn tồn tại sau khi trả handle**, nếu pool không reset trạng thái phiên đó. Vì vậy, không đặt tùy tiện các `SET` lâu dài trên kết nối dùng chung. Cần thiết kế chính sách khởi tạo và làm sạch phiên, hoặc dùng thiết lập có phạm vi giao dịch khi DBMS cung cấp và phù hợp.

Tên schema và role là **định danh hoặc dữ liệu cấu hình có ảnh hưởng bảo mật**; không nối trực tiếp đầu vào chưa được kiểm tra vào câu lệnh SQL để thay đổi schema, role hoặc tham số phiên.

## 9. Connection pool và nguy cơ rò rỉ trạng thái phiên

Một ứng dụng thường mượn `Connection` từ `DataSource` có pool. Khi gọi `close()`, handle logic được trả về pool; **kết nối vật lý có thể được tái sử dụng** cho một yêu cầu khác. Vì vậy, cấu hình phiên trở thành vấn đề quan trọng:

```text
Yêu cầu A                       Connection pool                  Yêu cầu B
    │                                 │                              │
    ├── mượn Connection ─────────────►│                              │
    ├── setSchema("sales")             │                              │
    ├── chạy truy vấn                  │                              │
    └── close() ─────────────────────►│                              │
                                      ├── kiểm tra / reset trạng thái│
                                      └─────────────────────────────►│ mượn
                                                                     │
                                                   Kỳ vọng: schema mặc định
```

Nếu pool không khôi phục cấu hình và mã ứng dụng cũng không chủ động dọn dẹp, B có thể vô tình chạy truy vấn trên schema mà A đã chọn. Tương tự, một kết nối có thể mang theo `autoCommit=false`, mức cô lập, read-only, thuộc tính client, thời gian chờ hoặc những cài đặt `SET` riêng của DBMS.

Một quy trình thực tế nên có các nguyên tắc sau:

1. **Cấu hình giá trị mặc định tại nơi tạo pool**: tài khoản, database, schema, isolation và các thiết lập mặc định phù hợp với ứng dụng.
2. **Thay đổi trong phạm vi hẹp**: chỉ đặt catalog/schema/thuộc tính phiên khi công việc thật sự cần, trước khi bắt đầu truy vấn hoặc giao dịch.
3. **Kết thúc giao dịch minh bạch**: `commit()` hoặc `rollback()` trước khi kết thúc lượt mượn; không giả định `close()` sẽ commit theo cách mong muốn.
4. **Khôi phục trạng thái đã đổi** hoặc dựa trên cơ chế reset đã được kiểm chứng của pool. Đặc biệt kiểm tra cả các tham số `SET` do DBMS quản lý, vì pool có thể chỉ reset một số thuộc tính JDBC.
5. **Đóng handle bằng `try-with-resources`** để tránh rò rỉ kết nối; không sử dụng handle đã đóng hoặc chia sẻ cùng một handle đồng thời giữa các yêu cầu.
6. **Kiểm chứng bằng thử nghiệm tích hợp**: mượn kết nối, đổi schema hoặc setting, trả lại, rồi mượn tiếp và kiểm tra trạng thái mong đợi trên chính hệ quản trị/driver/pool triển khai.

Trong hệ thống dùng framework quản lý giao dịch, các thao tác cấu hình kết nối có thể do framework sở hữu. Khi đó cần tôn trọng vòng đời transaction và quy ước của framework, tránh tự tạo một phiên cấu hình mâu thuẫn với giao dịch đang được quản lý.

## 10. Chẩn đoán lỗi cấu hình catalog, schema và phiên

| Hiện tượng | Nguyên nhân có thể xảy ra | Hướng kiểm tra |
|---|---|---|
| `Table not found`, `relation does not exist` | Schema mặc định hoặc search path khác dự kiến | In `getCatalog()`/`getSchema()` khi được hỗ trợ; kiểm tra tên đủ điều kiện, quyền và tên thực tế |
| `setSchema()` ném `SQLFeatureNotSupportedException` | Driver không hỗ trợ API hoặc tính năng tương ứng | Đọc tài liệu driver; cân nhắc SQL đủ điều kiện hoặc cấu hình phù hợp DBMS |
| `setCatalog()` không chuyển sang database khác | Giới hạn ánh xạ catalog hoặc chính sách kết nối | Xác nhận khả năng driver; có thể phải mở một kết nối mới tới database đích |
| Truy vấn chạy đúng ở request A nhưng sai ở B | Trạng thái phiên của kết nối pool không được reset | Kiểm tra schema, `search_path`, transaction, read-only, session `SET` sau khi mượn mới |
| `setTransactionIsolation()` thất bại | Mức cô lập không được hỗ trợ hoặc thay đổi không đúng thời điểm | Kiểm tra `DatabaseMetaData`, cấu hình DB và ranh giới giao dịch |
| `setReadOnly(true)` nhưng vẫn ghi được | Read-only có thể chỉ là gợi ý JDBC | Dùng chính sách phân quyền DBMS; không dùng cờ này làm lớp bảo mật |
| Thời gian truy vấn bất thường | Timeout hoặc cài đặt phiên không nhất quán giữa các kết nối | Kiểm tra `setQueryTimeout`, `setNetworkTimeout` và cài đặt timeout riêng của DBMS |

Khi điều tra, hãy ghi nhận driver, DBMS, `getCatalog()`, `getSchema()` (nếu hỗ trợ), chế độ auto-commit, isolation, thông tin lỗi `SQLException` và thời điểm lấy kết nối từ pool. Chỉ ghi log các dữ liệu cấu hình được phép tiết lộ; tránh lưu mật khẩu, token hoặc giá trị tham số nhạy cảm.

## 11. Bài tập tư duy: hai schema cùng có bảng `orders`

Giả sử cơ sở dữ liệu hỗ trợ schema `sales`, `archive`, mỗi schema đều có bảng `orders`. Hai công việc A và B dùng cùng một connection pool:

1. A mượn kết nối và gọi `setSchema("archive")` rồi chạy `SELECT * FROM orders`.
2. A gọi `close()` để trả handle logic cho pool.
3. B mượn một kết nối và chạy `SELECT * FROM orders`, với ý định đọc bảng của `sales`.

**Câu hỏi:** B có chắc chắn truy vấn vào `sales.orders` không?

**Trả lời:** Không. Nếu B nhận lại cùng kết nối vật lý và trạng thái schema của A chưa được khôi phục, B có nguy cơ đọc `archive.orders`. Mặt khác, pool có thể đã reset trạng thái hoặc cấp một kết nối vật lý khác; không thể suy đoán kết quả chỉ từ việc A đã `close()`.

**Cách phòng tránh:** B có thể dùng câu SQL đủ điều kiện `SELECT * FROM sales.orders` nếu DBMS hỗ trợ, hoặc ứng dụng bảo đảm schema mong muốn được đặt/khôi phục đúng lúc và pool reset trạng thái theo hợp đồng đã kiểm tra. Việc chọn chiến lược nào phụ thuộc thiết kế multi-tenant, quyền của tài khoản DB và khả năng driver.

**Ghi nhớ:** Catalog và schema xác định **bối cảnh phân giải tên đối tượng**; còn auto-commit, isolation, read-only và các cấu hình phiên quyết định **cách thao tác SQL vận hành**. Trong JDBC, `Connection` là nơi tiếp xúc với các cấu hình đó, nhưng hành vi cụ thể được quyết định bởi DBMS, driver và connection pool. Thiết lập rõ ràng trước khi sử dụng, kết thúc giao dịch đúng cách và kiểm tra việc khôi phục trạng thái sẽ giúp ứng dụng tránh lỗi truy cập nhầm schema và các sự cố khó tái hiện.
