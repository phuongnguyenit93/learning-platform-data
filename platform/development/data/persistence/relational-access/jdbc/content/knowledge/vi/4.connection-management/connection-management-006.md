# Thiết lập readOnly, catalog và schema trong quản lý kết nối JDBC

## 1. Ba thuộc tính cấu hình trên một kết nối

**JDBC (Java Database Connectivity)** cung cấp API trong `java.sql` và `javax.sql` để Java truy cập cơ sở dữ liệu quan hệ. Sau khi nhận một đối tượng `Connection`, ứng dụng có thể thiết lập một số thuộc tính ảnh hưởng đến cách driver và hệ quản trị cơ sở dữ liệu (DBMS) sử dụng kết nối đó.

Trong nhóm **quản lý kết nối**, ba thuộc tính thường gặp là:

- **`readOnly`:** cho driver biết ứng dụng dự định dùng kết nối chủ yếu để đọc.
- **`catalog`:** chỉ định phạm vi tên đối tượng ở cấp catalog theo cách hệ quản trị định nghĩa.
- **`schema`:** chỉ định không gian tên schema mặc định để phân giải các tên đối tượng không ghi đầy đủ.

Chúng phục vụ ba mục đích khác nhau. Một kết nối có thể được đánh dấu `readOnly=true` mà không đổi catalog/schema; ngược lại, đổi schema **không tự** biến truy vấn thành chỉ đọc hay cấp thêm quyền.

| Thuộc tính | Phương thức ghi | Phương thức đọc | Mục đích |
| --- | --- | --- | --- |
| Read-only hint | `Connection.setReadOnly(boolean)` | `Connection.isReadOnly()` | Thông báo ý định đọc, có thể hỗ trợ tối ưu hoặc lựa chọn chính sách do driver/DBMS triển khai. |
| Catalog hiện tại | `Connection.setCatalog(String)` | `Connection.getCatalog()` | Chọn catalog/ngữ cảnh tên ở mức mà DBMS và driver hỗ trợ. |
| Schema hiện tại | `Connection.setSchema(String)` | `Connection.getSchema()` | Chọn schema mặc định để phân giải tên bảng, view và các đối tượng khác. |

> **Phân biệt quan trọng:** Đây là các thuộc tính của **kết nối JDBC**, không phải cơ chế phân quyền. Việc driver công bố đã bật `readOnly` không thay thế quyền tài khoản SQL, transaction read-only do DBMS thực thi hoặc kiểm soát truy cập ở database.

## 2. Catalog và schema khác nhau như thế nào?

JDBC mô tả cấu trúc tên dữ liệu theo các cấp *catalog → schema → object*, nhưng ý nghĩa cụ thể phụ thuộc DBMS. Một tên đối tượng có thể được thể hiện như:

~~~text
catalog.schema.table
~~~

Không phải mọi hệ quản trị đều hỗ trợ cả ba cấp hoặc dùng dấu phân cách như nhau. Nhiều hệ thống cho phép bỏ bớt catalog/schema và dựa vào ngữ cảnh mặc định của kết nối.

~~~mermaid
flowchart TD
    C[Catalog: phạm vi đối tượng] --> S1[Schema: sales]
    C --> S2[Schema: reporting]
    S1 --> T1[(orders)]
    S1 --> T2[(customers)]
    S2 --> T3[(monthly_summary)]
~~~

**Ví dụ theo từng họ DBMS (mang tính định hướng):**

| DBMS | Catalog thường tương ứng | Schema thường tương ứng | Lưu ý khi đổi ngữ cảnh |
| --- | --- | --- | --- |
| PostgreSQL | Database đang kết nối. | Namespace trong database, ví dụ `public`, `sales`. | Không thể chuyển sang database PostgreSQL khác chỉ bằng đổi schema; thông thường cần một kết nối khác tới database đó. |
| MySQL / MariaDB | Database được chọn. | Khái niệm *schema* thường được dùng gần như đồng nghĩa với *database*. | Cách driver ánh xạ `setCatalog`/`setSchema` cần xác minh theo phiên bản cụ thể. |
| Microsoft SQL Server | Database trong instance. | Namespace trong database, ví dụ `dbo`, `sales`. | Việc đổi database và lựa chọn default schema là hai hành vi khác nhau; cần xem driver và quyền tài khoản. |
| Oracle Database | Không có ánh xạ đơn giản sang database theo nghĩa PostgreSQL. | Namespace gắn với user/schema, có thể chọn ngữ cảnh tên hiện tại theo cơ chế DBMS. | Không nên suy từ tên catalog sang tên service, instance hoặc pluggable database. |

Các ví dụ này giúp hình dung, nhưng **không phải cam kết** rằng `setCatalog` hoặc `setSchema` hoạt động tương tự trên mọi DBMS. API JDBC chuẩn hóa cách gọi; driver và server quyết định ngữ nghĩa và giới hạn thực tế.

### 2.1. Tên không đầy đủ và tên đầy đủ

Giả sử đang làm việc trong schema `sales`:

~~~sql
-- Tên không đầy đủ: phụ thuộc ngữ cảnh tìm kiếm đối tượng.
SELECT id, total_amount
FROM orders
WHERE id = ?;

-- Tên có schema: ít phụ thuộc schema mặc định hơn.
SELECT id, total_amount
FROM sales.orders
WHERE id = ?;
~~~

Tên `sales.orders` vẫn có thể không đầy đủ nếu DBMS dùng nhiều cấp namespace. Cú pháp tên đủ cấp, quy tắc chữ hoa/chữ thường và dấu nháy identifier khác nhau tùy DBMS.

**Quy tắc lựa chọn:** Nếu ứng dụng phải chạy trên một schema ổn định, có thể thiết lập schema lúc tạo kết nối hoặc viết rõ schema trong SQL. Nếu cùng ứng dụng truy cập nhiều tenant/schema, cần bảo đảm ngữ cảnh không rò rỉ từ request trước sang request sau.

## 3. Vòng đời của thuộc tính trên `Connection`

Một kết nối thường trải qua những bước sau:

~~~mermaid
flowchart LR
    A[Lấy Connection từ DataSource] --> B[Thiết lập readOnly / catalog / schema]
    B --> C[Tạo PreparedStatement]
    C --> D[Thực thi SQL và đọc ResultSet]
    D --> E[Đóng ResultSet / Statement]
    E --> F[Khôi phục trạng thái cần thiết]
    F --> G[close / trả về pool]
~~~

Thời điểm thay đổi thuộc tính có ý nghĩa:

1. **Thiết lập trước khi tạo statement cần dùng.** Statement đã được chuẩn bị có thể gắn với schema/catalog tại thời điểm prepare; đổi schema sau đó không bảo đảm mọi statement cũ tự phân giải lại tên.
2. **Thiết lập `readOnly` trước khi transaction bắt đầu.** Theo contract JDBC, không gọi `setReadOnly(...)` khi đang ở trong một transaction.
3. **Không đổi catalog/schema giữa transaction để thay thế cơ chế kiểm soát transaction.** Hiệu lực có thể không xác định hoặc khác nhau giữa DBMS. Chọn ngữ cảnh trước khi thực hiện công việc trong transaction.
4. **Khôi phục trạng thái trước khi trả connection về pool.** `close()` ở connection do pool cấp thường trả proxy về pool thay vì đóng ngay kết nối vật lý; một thuộc tính còn sót lại có thể ảnh hưởng request khác nếu pool không khôi phục đầy đủ.

Ở ứng dụng sử dụng Spring hoặc framework transaction, nên cấu hình các thuộc tính bằng cơ chế **cùng tầng đang quản lý transaction và connection**, tránh tự đổi trạng thái giữa lúc framework đang giữ connection.

## 4. Thiết lập `readOnly`: chỉ là tín hiệu ý định đọc

### 4.1. Cách gọi

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setReadOnly(true);

    System.out.println("Read-only hint = "
            + connection.isReadOnly());

    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT id, name FROM app_user WHERE id = ?")) {
        statement.setLong(1, 101L);

        try (ResultSet rs = statement.executeQuery()) {
            if (rs.next()) {
                System.out.println(rs.getString("name"));
            }
        }
    }
}
~~~

Ở đây `dataSource` là một `javax.sql.DataSource` đã được cấu hình với JDBC driver. `getConnection()` cấp connection; `setReadOnly(true)` thông báo ý định chỉ đọc; `try-with-resources` đảm bảo đóng statement, result set và connection.

**`isReadOnly() == true` chỉ xác nhận trạng thái mà JDBC driver báo về**, không phải bằng chứng rằng DBMS chắc chắn chặn mọi câu `INSERT`, `UPDATE` hoặc `DELETE`. Tùy driver, cờ có thể là hint tối ưu, có thể ảnh hưởng đến transaction/định tuyến hoặc có thể bị giới hạn.

### 4.2. Vì sao readOnly không phải hàng rào bảo mật?

Các biện pháp sau có vai trò khác nhau:

| Biện pháp | Công dụng chính | Có thể thay thế quyền database không? |
| --- | --- | --- |
| `Connection.setReadOnly(true)` | Hint hoặc thiết lập trạng thái theo driver/DBMS. | **Không.** |
| Tài khoản chỉ có quyền `SELECT` | Giới hạn quyền SQL ở phía database. | Chính là một biện pháp kiểm soát quyền. |
| Transaction được DBMS đặt ở chế độ read-only | Hạn chế thao tác thay đổi dữ liệu theo ngữ nghĩa của DBMS. | Bổ sung kiểm soát theo transaction, không thay thế quản lý tài khoản. |
| Truy cập bản sao chỉ đọc | Đưa tải đọc đến một database được cấu hình phục vụ đọc. | Phụ thuộc cơ chế vận hành và phân quyền thực tế. |

Nếu một endpoint tuyệt đối không được sửa dữ liệu, hãy **sử dụng quyền tối thiểu ở database** và transaction hoặc endpoint được bảo vệ phù hợp. Đừng dựa vào `setReadOnly(true)` để ngăn mã lỗi hay kẻ tấn công thực hiện ghi.

### 4.3. Khi nào nên bật?

- Trong các thao tác truy vấn thuần đọc, khi driver và hạ tầng có lợi từ hint.
- Khi framework transaction yêu cầu định nghĩa rõ một luồng đọc, ví dụ cấu hình transaction read-only tương ứng.
- Khi có chiến lược điều phối kết nối đọc/ghi **đã xác minh** tương thích với driver, proxy và pool.

Không giả định rằng chỉ cần bật `readOnly` là driver tự chuyển mọi request sang read replica. Một số giải pháp triển khai cơ chế định tuyến riêng, số khác không.

## 5. Thiết lập `catalog`: chọn ngữ cảnh ở cấp catalog

### 5.1. Cách gọi và đọc lại

~~~java
try (Connection connection = dataSource.getConnection()) {
    String originalCatalog = connection.getCatalog();
    System.out.println("Original catalog: " + originalCatalog);

    connection.setCatalog("appdb");

    System.out.println("Current catalog: "
            + connection.getCatalog());
}
~~~

Đây là ví dụ minh họa thao tác API. Tên `appdb` chỉ có ý nghĩa nếu DBMS/driver đích hỗ trợ một catalog đó và tài khoản có quyền truy cập.

Một số driver không hỗ trợ thay đổi catalog qua JDBC hoặc chỉ hỗ trợ trong phạm vi hiện tại; chúng có thể **bỏ qua yêu cầu** hoặc báo lỗi theo contract và cách triển khai cụ thể. Vì vậy, **phải đọc lại và thử hành vi truy vấn**, thay vì mặc định `setCatalog("appdb")` luôn chuyển được database vật lý.

### 5.2. Không nhầm catalog với JDBC URL

JDBC URL thường xác định database/server khi thiết lập kết nối:

~~~text
jdbc:postgresql://db.example.com:5432/appdb
jdbc:mysql://db.example.com:3306/appdb
jdbc:sqlserver://db.example.com:1433;databaseName=appdb
~~~

Trong PostgreSQL, cơ sở dữ liệu đã được chọn khi mở kết nối; không thể dùng `setCatalog` để biến cùng kết nối thành kết nối tới database PostgreSQL khác. Nếu nghiệp vụ cần database khác, thường phải chọn URL hoặc `DataSource` phù hợp.

Trong hệ DBMS có hỗ trợ chọn database hiện tại sau khi kết nối, `setCatalog` có thể tác động đến các tên không đủ cấp. Tuy nhiên, đừng dùng nó như cơ chế chuyển server, thay credential hoặc vượt quyền.

## 6. Thiết lập `schema`: chọn namespace mặc định

### 6.1. Cách gọi

~~~java
try (Connection connection = dataSource.getConnection()) {
    String originalSchema = connection.getSchema();
    System.out.println("Original schema: " + originalSchema);

    connection.setSchema("sales");
    System.out.println("Current schema: "
            + connection.getSchema());

    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT id, total_amount FROM orders WHERE id = ?")) {
        ps.setLong(1, 501L);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                System.out.println(rs.getBigDecimal("total_amount"));
            }
        }
    }
}
~~~

`Connection.setSchema(String)` và `getSchema()` có mặt từ **JDBC 4.1 (Java 7)**. Driver có thể không hỗ trợ schema hoặc có cách ánh xạ đặc thù; kiểm tra tài liệu và kết quả đọc lại. Đối với một số driver, thay đổi có thể được bỏ qua nếu không hỗ trợ tính năng.

**Điểm cần chú ý:** Đổi schema có thể ảnh hưởng tên bảng, view, sequence hoặc procedure không ghi đủ cấp trong SQL. Nó **không tạo schema**, không cấp quyền truy cập schema và không bảo đảm thay đổi cách phân giải tên của các statement đã được chuẩn bị trước.

### 6.2. Dùng schema như cách cô lập tenant?

Giả sử tenant A và B có hai schema khác nhau: `tenant_a` và `tenant_b`. Chuyển schema có thể giúp SQL tái sử dụng tên bảng `orders` nhưng **không tự đảm bảo cách ly dữ liệu**.

Một thiết kế multi-tenant an toàn cần đồng thời:

- Ràng buộc tenant từ phía xác thực và kiểm soát quyền truy cập ở DBMS.
- Chọn schema từ danh sách/tuyến định danh được kiểm duyệt, không tin trực tiếp dữ liệu do người dùng gửi.
- Khôi phục context khi trả connection về pool; tránh tenant A đọc nhầm schema của tenant B.
- Kiểm thử cả trường hợp transaction lỗi, timeout, rollback và pool tái sử dụng cùng kết nối.
- Kiểm tra cách framework cache statement, tên bảng và metadata theo schema.

Trong JDBC, placeholder `?` của `PreparedStatement` áp dụng cho **giá trị dữ liệu**, không áp dụng trực tiếp cho tên schema/table. Khi cần xây SQL chứa tên identifier, phải dùng mapping tin cậy hoặc cơ chế quote identifier đúng DBMS; không ghép chuỗi từ input tùy ý.

## 7. Ví dụ tích hợp: thiết lập cả ba thuộc tính rồi truy vấn

Ví dụ sau thể hiện trình tự mượn kết nối → lưu trạng thái ban đầu → cấu hình → truy vấn → khôi phục. Nó dành cho một driver/DBMS **đã được xác nhận hỗ trợ `getSchema/setSchema` và `getCatalog/setCatalog`** trên namespace mục tiêu.

Giả sử bảng `app_user(id, name)` có trong schema `sales` của catalog `appdb`, và pool trả về connection ở trạng thái `autoCommit=true`.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class JdbcConnectionSettings {
    private JdbcConnectionSettings() {}

    public record UserRow(long id, String name) {}

    public static List<UserRow> findUsers(
            DataSource dataSource,
            String targetCatalog,
            String targetSchema,
            long minId) throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Ví dụ yêu cầu connection ở autoCommit=true; "
                        + "không tự thay trạng thái transaction đang quản lý");
            }

            boolean oldReadOnly = connection.isReadOnly();
            String oldCatalog = connection.getCatalog();
            String oldSchema = connection.getSchema();

            try {
                // Chọn namespace trước khi tạo statement.
                connection.setCatalog(targetCatalog);
                connection.setSchema(targetSchema);

                // Thiết lập trước khi thực thi câu SQL/transaction.
                connection.setReadOnly(true);

                // Readback để phát hiện ngữ cảnh thực tế của driver.
                System.out.println("readOnly=" + connection.isReadOnly());
                System.out.println("catalog=" + connection.getCatalog());
                System.out.println("schema=" + connection.getSchema());

                List<UserRow> result = new ArrayList<>();

                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT id, name FROM app_user WHERE id >= ?")) {
                    ps.setLong(1, minId);

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            result.add(new UserRow(
                                    rs.getLong("id"),
                                    rs.getString("name")));
                        }
                    }
                }

                return List.copyOf(result);
            } finally {
                // Dữ liệu đã đọc và statement đã đóng trước khi reset.
                // Khôi phục namespace theo đúng catalog/schema ban đầu.
                connection.setCatalog(oldCatalog);
                connection.setSchema(oldSchema);
                connection.setReadOnly(oldReadOnly);
            }
        }
    }
}
~~~

Sử dụng:

~~~java
List<JdbcConnectionSettings.UserRow> rows =
        JdbcConnectionSettings.findUsers(
                dataSource, "appdb", "sales", 1L);

System.out.println("Số hàng: " + rows.size());
~~~

### 7.1. Các giả định cần biết trước khi dùng ví dụ

1. **Đích hỗ trợ thay đổi namespace.** Với PostgreSQL, `setCatalog("appdb")` không giúp đổi database nếu connection không được tạo tới database đó. Nếu target đã nằm trong URL, chỉ nên thiết lập lại catalog khi thật sự cần và driver cho phép.
2. **Không có transaction đang được framework quản lý.** Ví dụ yêu cầu `autoCommit=true` để tránh đổi `readOnly` giữa transaction; khi dùng Spring/JTA, nên ủy quyền cấu hình kết nối cho tầng quản lý transaction.
3. **Readback chưa đủ để chứng minh dữ liệu đúng schema.** Driver có thể trả giá trị chuẩn hóa khác hoặc bỏ qua thay đổi; cần kiểm thử query/schema thật trên môi trường đích.
4. **Khôi phục trạng thái có thể thất bại.** Khối `finally` đơn giản nhằm làm rõ ý tưởng; trong production, cần quản lý lỗi restore cẩn thận, không để lỗi reset che mất exception gốc và bảo đảm pool loại bỏ connection không còn trạng thái đáng tin cậy.
5. **Không giới hạn số hàng.** Đây là ví dụ API; truy vấn thực tế cần phân trang/giới hạn theo nghiệp vụ nếu dữ liệu lớn.

**Đặc biệt:** Một pool có thể tự khôi phục một số thuộc tính, nhưng **không mặc định mọi pool đều reset catalog và schema**, nhất là khi driver quản lý namespace theo trạng thái session riêng. Nếu ứng dụng cần đổi context theo từng request, hãy xác minh hành vi của đúng pool và phiên bản driver.

### 7.2. Trình tự reset và bảo toàn lỗi

Khi khôi phục, nếu schema phụ thuộc catalog thì nên đưa catalog về ban đầu trước rồi mới đưa schema về ban đầu. Chỉ khi mọi trạng thái được khôi phục hoặc connection được loại bỏ an toàn, connection mới phù hợp để phục vụ một request/tenant khác.

Trong mã production, nên tách helper restore chuyên trách để:

- Thử khôi phục các thuộc tính cần thiết ngay cả khi một bước thất bại.
- Bảo toàn exception xử lý SQL ban đầu, bổ sung lỗi restore dưới dạng `suppressed exception` khi phù hợp.
- Đánh dấu/invalidate connection khi không còn tin trạng thái session.
- Để framework quản lý transaction/pool thực hiện reset nếu nó có hợp đồng hỗ trợ rõ ràng.

Nếu chuyển schema/catalog chỉ nhằm cấu hình mặc định cho toàn ứng dụng, lựa chọn đơn giản hơn là khai báo **ngữ cảnh khi cấu hình DataSource/URL/pool** theo cơ chế driver hỗ trợ, tránh thay đổi liên tục mỗi query.

## 8. Kiểm tra khả năng hỗ trợ và namespace hiện có

JDBC có `DatabaseMetaData` để kiểm tra thông tin driver/database trước khi dựa vào một tính năng.

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void inspectNamespaces(DataSource dataSource)
        throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData meta = connection.getMetaData();

        System.out.println("DBMS: "
                + meta.getDatabaseProductName());
        System.out.println("Driver: "
                + meta.getDriverName());

        System.out.println("Catalog term: "
                + meta.getCatalogTerm());
        System.out.println("Schema term: "
                + meta.getSchemaTerm());
        System.out.println("Catalog separator: "
                + meta.getCatalogSeparator());

        System.out.println("Catalog in DML: "
                + meta.supportsCatalogsInDataManipulation());
        System.out.println("Schema in DML: "
                + meta.supportsSchemasInDataManipulation());

        System.out.println("Current catalog: "
                + connection.getCatalog());
        System.out.println("Current schema: "
                + connection.getSchema());

        try (ResultSet catalogs = meta.getCatalogs()) {
            while (catalogs.next()) {
                System.out.println("Catalog: "
                        + catalogs.getString("TABLE_CAT"));
            }
        }

        try (ResultSet schemas = meta.getSchemas()) {
            while (schemas.next()) {
                System.out.println("Schema: "
                        + schemas.getString("TABLE_SCHEM"));
            }
        }
    }
}
~~~

**Ý nghĩa các phương thức:**

| Metadata | Giúp trả lời | Không chứng minh |
| --- | --- | --- |
| `getCatalogTerm()` / `getSchemaTerm()` | DBMS gọi từng cấp namespace bằng thuật ngữ nào. | Mọi catalog/schema đều có thể chuyển giữa chúng. |
| `getCatalogSeparator()` | Dấu phân tách catalog trong tên đủ cấp theo driver. | Cú pháp identifier hoàn toàn tương đương giữa các DBMS. |
| `supportsCatalogsInDataManipulation()` | Có thể dùng catalog trong việc đặt tên đối tượng của câu lệnh DML không. | `setCatalog()` sẽ đổi database vật lý. |
| `supportsSchemasInDataManipulation()` | Có thể dùng schema trong việc đặt tên đối tượng của câu lệnh DML không. | `setSchema()` luôn được triển khai hoặc có hiệu lực. |
| `getCatalogs()` / `getSchemas()` | Danh sách namespace mà metadata công bố/thấy được. | Người dùng hiện tại có quyền truy cập mọi đối tượng trong đó. |
| `getCatalog()` / `getSchema()` | Ngữ cảnh connection được driver công bố. | Mọi prepared statement cũ tự đổi ngữ cảnh hoặc không có vấn đề phân quyền. |

`DatabaseMetaData.getSchemas()` có thể có biến thể tham số catalog/schema pattern cho việc lọc. Danh sách trả về còn phụ thuộc phiên bản driver và quyền của tài khoản, nên không kết luận schema không tồn tại chỉ dựa vào một kết quả rỗng nếu thiếu bằng chứng.

**Lưu ý phiên bản:** `getSchema()`/`setSchema()` có từ JDBC 4.1. Một số driver có thể ném `SQLException`/`SQLFeatureNotSupportedException` khi không hỗ trợ thao tác được gọi hoặc có thể bỏ qua thiết lập tùy contract. Mã cần có xử lý tương thích theo driver đích.

## 9. Thứ tự cấu hình khi dùng transaction

Các thuộc tính này tương tác với transaction theo các cách khác nhau:

| Thao tác | Nên thực hiện khi nào? | Nguy cơ nếu đổi giữa transaction |
| --- | --- | --- |
| `setReadOnly(true/false)` | **Trước khi transaction bắt đầu.** | Vi phạm contract JDBC hoặc gây `SQLException`. |
| `setCatalog(...)` | Trước khi prepare và bắt đầu luồng SQL cần catalog đích. | Không bảo đảm statement/transaction hiện tại dùng ngữ cảnh mới như mong muốn. |
| `setSchema(...)` | Trước khi prepare và thực thi các câu SQL dùng schema đích. | Có thể tạo hành vi không nhất quán giữa statement cũ và mới. |
| `setAutoCommit(false)` | Khi chủ sở hữu transaction quyết định mở transaction logic. | Framework có thể đã quản lý transaction; tự đổi state gây xung đột. |
| `commit()`/`rollback()` | Theo ranh giới nghiệp vụ và framework quản lý transaction. | Thay đổi trạng thái tùy tiện có thể làm mất atomicity. |

Ví dụ về trình tự **chỉ khi ứng dụng tự quản lý transaction, không có framework sở hữu connection**:

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Connection mới được mượn; chưa bắt đầu công việc SQL.
    connection.setReadOnly(true);
    connection.setSchema("reporting");

    connection.setAutoCommit(false);
    try {
        // Các câu SELECT trong transaction đọc.
        readReport(connection);
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

`readReport(connection)` là helper đọc dữ liệu do ứng dụng định nghĩa. Đoạn mã tập trung vào **thứ tự thiết lập**; dùng trong hệ thống có pool cần bổ sung khôi phục `autoCommit`, `readOnly`, `schema` theo hợp đồng pool/driver. Nếu câu rollback cũng có thể thất bại, hệ thống production cần giữ exception gốc và thêm lỗi rollback vào thông tin chẩn đoán.

**Một sắc thái:** Một số DBMS coi read-only transaction là chế độ riêng (SQL cấp server), khác với hint `Connection.setReadOnly(true)`. Muốn bảo đảm giao dịch không ghi, phải kiểm tra cơ chế thực thi của DBMS và quyền database thay vì tự suy diễn từ API.

## 10. Quản lý trạng thái trong connection pool

Trong ứng dụng web, `DataSource` thường dùng connection pool. Ví dụ hai request phục vụ hai tenant:

~~~text
Request A: mượn Connection #7 -> setSchema("tenant_a") -> query -> close()
Request B: mượn Connection #7 -> query không setSchema -> có thể thấy tenant_a
~~~

Nếu pool/driver không reset schema, B có thể chạy SQL dưới namespace của A. Đây là lỗi **trạng thái session bị rò rỉ**.

Biện pháp thiết kế:

1. **Ưu tiên cấu hình namespace cố định** cho một `DataSource` khi toàn bộ kết nối dùng cùng catalog/schema.
2. **Với nhiều tenant**, đảm bảo mỗi lần mượn connection đều thiết lập đầy đủ context trước câu SQL, kể cả sau lỗi.
3. **Xác minh reset** khi trả về pool. Có thể cần cơ chế framework/pool dành riêng cho schema/catalog, không chỉ gọi `close()`.
4. **Tách quyền truy cập dữ liệu tại DBMS**, ví dụ account theo tenant hoặc chính sách row-level security phù hợp. `setSchema` không phải hàng rào phân quyền.
5. **Kiểm thử ở mức tải đồng thời**, khi nhiều request dùng lại một connection vật lý; không chỉ kiểm tra trên một connection mới.
6. **Đối chiếu transaction lifecycle** để không thay schema/catalog giữa transaction đang hoạt động.

### 10.1. Tránh cache ngữ cảnh ngoài đời sống connection

Không lưu `Connection` vào biến static để chia sẻ giữa nhiều request hoặc thread. Không dùng một `PreparedStatement` được tạo dưới schema A để truy vấn tenant B với giả định rằng đổi schema sẽ cập nhật nội dung đã prepare.

Đối với statement cache, phải hiểu cache được liên kết với connection, SQL, thông tin schema/catalog và cách driver phân giải tên; cấu hình pool/driver không đúng có thể tạo kết quả bất ngờ. Nếu namespace có thể thay đổi, nên chọn cách quản lý rõ ràng và có kiểm thử tích hợp.

## 11. Kiểm tra sau khi thiết lập

Sau `setReadOnly`, `setCatalog` hoặc `setSchema`, ít nhất nên làm các bước sau:

1. **Đọc lại trạng thái JDBC** qua `isReadOnly()`, `getCatalog()` và `getSchema()`.
2. **Chạy truy vấn kiểm chứng** trên bảng/view đã biết ở namespace đích, với tài khoản và quyền tương đương production.
3. **Kiểm tra ngữ nghĩa thực tế** nếu tính năng quan trọng, ví dụ định tuyến read-only, default schema, quyền đọc/ghi và cách resolve unqualified table.
4. **Kiểm tra vòng đời qua pool:** đóng/mượn lại connection, tạo lỗi giữa luồng, chạy song song nhiều tenant.
5. **Ghi log phù hợp:** tên logical datasource, driver/database version, trạng thái đã được chuẩn hóa; không ghi mật khẩu hoặc URL chứa secret.

Ví dụ không nên chỉ xét:

~~~java
connection.setSchema("sales");
assert "sales".equals(connection.getSchema());
~~~

Bài kiểm tra đó có thể là tín hiệu tốt về cấu hình nhưng **không chứng minh** rằng câu `SELECT * FROM orders` đã truy cập đúng bảng theo nghiệp vụ, nhất là khi đường tìm kiếm schema, synonyms, cache statement hoặc quy tắc phân giải tên có khác biệt.

Để tránh nhầm dữ liệu giữa hai schema có bảng cùng tên, nên dùng dữ liệu kiểm thử phân biệt rõ schema A/B, và kiểm chứng rằng request A/B trả đúng dữ liệu của mình sau nhiều lần pool tái sử dụng.

## 12. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| `setReadOnly(true)` nhưng vẫn ghi được | Driver xử lý như hint, DBMS chưa cưỡng chế read-only, account vẫn có quyền ghi. | Quyền database, kiểu transaction, tài liệu driver. |
| `setReadOnly()` ném `SQLException` | Đổi trong transaction, driver không hỗ trợ hoặc trạng thái connection không hợp lệ. | Auto-commit, transaction lifecycle, SQLState và driver docs. |
| `setCatalog("x")` không đổi database | DBMS không hỗ trợ chuyển database bằng API này hoặc driver bỏ qua. | `getCatalog()`, JDBC URL, khả năng và giới hạn DBMS. |
| `setSchema("x")` không đổi kết quả SQL | Driver không áp dụng, statement được prepare trước đó, SQL đã dùng tên đầy đủ hoặc search path khác. | `getSchema()`, thời điểm prepare, query thực tế, cấu hình driver. |
| Bảng tồn tại nhưng `table not found` | Sai catalog/schema, identifier case, tên bảng hoặc quyền. | Tên đủ cấp, metadata, account/grants. |
| Request tenant B thấy dữ liệu tenant A | Rò rỉ session context từ connection pool, câu SQL không đủ định danh hoặc lỗi phân quyền. | Reset state, test pool reuse, tenant authorization tại DBMS. |
| Đổi namespace gây lỗi transaction | Thay đổi giữa transaction, framework transaction kiểm soát connection. | Thời điểm set, commit/rollback, chủ sở hữu transaction. |
| `getSchema()` không hỗ trợ | Driver/JDBC API mức cũ hoặc phương thức chưa được triển khai. | Runtime Java, driver version và hướng dẫn provider. |

Khi xử lý `SQLException`, ghi **`SQLState` và mã lỗi hãng** nếu hữu ích. Không cố gắng “sửa” bằng cách bắt mọi lỗi rồi bỏ qua trạng thái namespace; như vậy có thể khiến truy vấn chạy trên sai database/schema.

## 13. Ba tình huống thực hành

### 13.1. Service chỉ đọc báo cáo

**Yêu cầu:** Một API báo cáo chỉ chạy `SELECT` trên bảng `reporting.monthly_summary`.

Thiết kế phù hợp có thể dùng `DataSource` với account chỉ đọc, xác định schema `reporting` khi cấu hình connection và, nếu driver hỗ trợ, dùng `setReadOnly(true)`. Ưu tiên truy vấn có tên đủ cấp khi logic/schema ổn định. Kiểm chứng DBMS từ chối ghi theo quyền tài khoản; không coi cờ read-only là chứng nhận bảo mật.

### 13.2. Ứng dụng có nhiều schema theo tenant

**Yêu cầu:** Tenant A/B có hai namespace `tenant_a`/`tenant_b` dùng chung cấu trúc bảng.

Thiết kế cần quyết định mức cách ly DBMS, sau đó triển khai context propagation và restore theo đúng vòng đời connection/transaction. Kiểm thử request xen kẽ A–B–A trên cùng pool và đo khả năng sai namespace khi exception xảy ra. Có thể cần pool hoặc datasource riêng cho tenant tùy yêu cầu bảo mật và tải.

### 13.3. Ứng dụng kết nối hai PostgreSQL database

**Yêu cầu:** Service phải đọc một database `sales_db` và một database `analytics_db` trên cùng PostgreSQL server.

Dùng các kết nối có **JDBC URL/DataSource tương ứng** với từng database. `setSchema("analytics")` chỉ thay namespace *trong database đang kết nối*; `setCatalog("analytics_db")` không biến connection PostgreSQL đang ở `sales_db` thành kết nối đến database khác. Nếu cần tổng hợp xuyên database, ứng dụng phải có giải pháp kiến trúc thích hợp và kiểm tra transaction boundary giữa các nguồn.

## 14. Checklist áp dụng vào dự án

- [ ] Phân biệt rõ ý nghĩa **readOnly**, **catalog** và **schema** trong DBMS đích.
- [ ] Xác minh phiên bản JDBC driver và hỗ trợ `getSchema/setSchema`, `getCatalog/setCatalog` khi cần.
- [ ] Thiết lập trạng thái **trước khi prepare SQL** và trước transaction theo contract JDBC.
- [ ] Không dùng `setReadOnly(true)` thay quyền SQL hoặc chính sách transaction read-only tại DBMS.
- [ ] Xác minh `getCatalog()`, `getSchema()` và thử truy vấn thực tế; không tin readback đơn lẻ.
- [ ] Không dùng giá trị tenant/schema do client cung cấp trực tiếp vào tên SQL hay connection context.
- [ ] Hiểu rõ framework/pool đang quản lý và reset thuộc tính nào khi `Connection.close()`.
- [ ] Xử lý lỗi khi thiết lập/khôi phục trạng thái, không trả connection không đáng tin sang request khác.
- [ ] Kiểm thử transaction, statement cache, lỗi giữa request và pool reuse.
- [ ] Đối với các database vật lý khác nhau, chọn đúng URL/`DataSource` thay vì giả định `setCatalog` sẽ đổi server/database.

**Ghi nhớ:** `Connection.setReadOnly()` truyền ý định truy cập đọc; `setCatalog()` và `setSchema()` thay đổi ngữ cảnh tên theo khả năng của driver và DBMS. Cấu hình chúng **sớm trong vòng đời connection**, kiểm chứng hành vi thật và đảm bảo khôi phục trạng thái khi kết nối được tái sử dụng để giữ tính đúng đắn, bảo mật và khả năng vận hành của ứng dụng JDBC.
