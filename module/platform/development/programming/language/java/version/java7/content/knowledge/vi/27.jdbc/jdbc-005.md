# Lấy hoặc đặt schema của kết nối JDBC

## Mục tiêu

Một cơ sở dữ liệu quan hệ có thể tổ chức bảng, view và các đối tượng khác thành nhiều **schema**. Khi truy vấn bằng JDBC, cần biết **schema hiện tại của `Connection`** và khi nào nên thay đổi nó để câu SQL tham chiếu đúng đối tượng.

Sau bài này, bạn có thể:

- Dùng `Connection.getSchema()` để đọc schema hiện tại và `Connection.setSchema(String)` để yêu cầu đổi schema cho kết nối.
- Hiểu tác động của schema mặc định lên tên bảng có hoặc không có tiền tố schema.
- Chọn đúng thời điểm đổi schema so với `Statement`/`PreparedStatement`, kiểm tra hỗ trợ từ JDBC driver.
- Quản lý trạng thái schema an toàn khi dùng connection pool, transaction và ứng dụng đa tenant.
- Chạy chương trình Java 17+ chứng minh hai schema có bảng trùng tên nhưng trả về hai kết quả khác nhau.

Đây là kiến thức thuộc **JDBC API hiện hành**: `getSchema()` và `setSchema()` có từ JDBC 4.1 (Java 7) và vẫn được cung cấp trong Java 17+.

## 1. Schema của kết nối là gì?

Trong ngữ cảnh này, **schema** là không gian tên dành cho đối tượng SQL, ví dụ:

~~~text
Một cơ sở dữ liệu
├── PUBLIC
│   └── BOOKS
└── SALES
    └── BOOKS
~~~

Hai bảng `PUBLIC.BOOKS` và `SALES.BOOKS` có thể có cấu trúc tương tự nhưng chứa dữ liệu khác nhau. Khi viết tên đầy đủ `SALES.BOOKS`, câu SQL chỉ rõ schema. Khi viết `BOOKS`, DBMS dùng quy tắc phân giải tên của **session/kết nối hiện tại**, trong đó schema mặc định có vai trò quan trọng.

Ví dụ minh họa với H2:

~~~sql
SELECT TITLE FROM BOOKS WHERE ID = 1;
SELECT TITLE FROM SALES.BOOKS WHERE ID = 1;
~~~

Truy vấn thứ nhất có thể đọc `PUBLIC.BOOKS` hoặc `SALES.BOOKS` tùy schema hiện hành; truy vấn thứ hai chỉ rõ bảng trong `SALES`. Một số hệ quản trị hỗ trợ **schema search path** gồm nhiều schema và các quy tắc phân giải phức tạp hơn; không mặc định rằng mọi DBMS luôn tìm ở đúng một schema.

Schema của kết nối **không phải**:

- Tên cơ sở dữ liệu/catalog: JDBC có API riêng `getCatalog()`/`setCatalog()`; ý nghĩa catalog và schema tùy DBMS.
- Cấu trúc JSON, XML hay kiểu dữ liệu validation schema.
- Quyền truy cập: chọn schema **không tự cấp quyền** đọc/ghi bảng.
- Lệnh tạo schema: `setSchema("SALES")` không thay thế `CREATE SCHEMA SALES`.

## 2. Hai API JDBC cần nhớ

Các phương thức trong `java.sql.Connection`:

~~~java
String currentSchema = connection.getSchema();
connection.setSchema("SALES");
~~~

| API | Mục đích | Giá trị / kết quả cần nhớ |
| --- | --- | --- |
| `String getSchema() throws SQLException` | Đọc tên schema hiện tại của connection | Trả `String` hoặc `null` khi không có schema hiện tại |
| `void setSchema(String schema) throws SQLException` | Yêu cầu connection chuyển sang schema được chỉ định | Không trả giá trị; ảnh hưởng phụ thuộc JDBC driver/DBMS |
| `String getCatalog()` / `setCatalog(String)` | Làm việc với catalog | Không đồng nghĩa với schema trên mọi DBMS |
| `DatabaseMetaData.getSchemas()` | Liệt kê metadata schema mà driver báo cáo | Dùng để khám phá metadata, không chứng minh quyền truy cập bảng |

### `getSchema()`

~~~java
try (Connection connection = dataSource.getConnection()) {
    String schema = connection.getSchema();
    System.out.println("Schema hiện tại: " + schema);
}
~~~

Đây là **đoạn trong ứng dụng đã có `DataSource`**, không phải chương trình độc lập. `getSchema()` đọc trạng thái của **chính connection đó**, không đọc một biến cấu hình toàn cục. Giá trị `null` là hợp lệ theo hợp đồng JDBC và phải được xử lý như trạng thái không có tên schema được báo cáo; đừng mặc định luôn nhận `PUBLIC` hoặc `dbo`.

### `setSchema(String)`

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setSchema("SALES");

    // Tạo statement sau khi chọn schema.
    try (PreparedStatement ps =
            connection.prepareStatement(
                    "SELECT ID, TITLE FROM BOOKS WHERE ID = ?")) {
        ps.setInt(1, 1);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getString("TITLE"));
            }
        }
    }
}
~~~

Đây cũng là đoạn minh họa với `DataSource`, schema `SALES` và bảng `BOOKS` đã tồn tại. `setSchema()` **chỉ đổi ngữ cảnh schema trên connection**, không tạo schema hoặc di chuyển bảng. DBMS có thể từ chối schema không tồn tại/không được phép qua `SQLException`.

**Giới hạn khả chuyển được Java API quy định:**

1. Nếu driver không hỗ trợ schema, `setSchema()` **có thể bị bỏ qua âm thầm**. Vì vậy, lệnh gọi thành công không đủ chứng minh ngữ cảnh đã đổi.
2. `setSchema()` **không tác động lên những `Statement` đã tạo hoặc chuẩn bị trước đó**. JDBC không buộc driver phải chuẩn bị SQL tại cùng một thời điểm. Để khả chuyển tốt nhất, **gọi `setSchema()` trước `createStatement()`/`prepareStatement()`/`prepareCall()`**.
3. `getSchema()` trả tên schema hiện tại hoặc `null`; lỗi truy cập DB hoặc connection đã đóng có thể gây `SQLException`.
4. Quy tắc đặt tên, chữ hoa/chữ thường, tên có dấu nháy kép và cách phân giải object là quy tắc **của DBMS/driver**. Trên H2, tên schema được tạo không trích dẫn thường ở dạng chữ hoa; `setSchema("SALES")` khác `setSchema("sales")`.

Để xác nhận việc đổi schema có hiệu lực, hãy kiểm tra `getSchema()` và thực hiện truy vấn thích hợp trong môi trường/driver thực tế; riêng `getSchema()` có thể chưa chứng minh mọi câu SQL phân giải đối tượng giống kỳ vọng nếu DBMS có search path phức tạp.

## 3. Thứ tự gọi đúng trong một đơn vị truy vấn

~~~text
Mượn / mở Connection
    |
    +-- getSchema() để biết schema đang dùng (nếu cần)
    |
    +-- setSchema("SALES") khi ứng dụng cần đổi
    |
    +-- prepareStatement("SELECT ... FROM BOOKS ...")
    |
    +-- Gán tham số -> executeQuery() -> đọc ResultSet
    |
    +-- Đóng ResultSet -> PreparedStatement
    |
    +-- Khôi phục schema cũ nếu hợp đồng connection yêu cầu
    |
    +-- Đóng / hoàn trả Connection cho pool
~~~

Không đổi schema trong khi còn dùng một statement hoặc result set được tạo dưới ngữ cảnh trước đó. Không chia sẻ một `Connection` đang bị thay schema giữa các luồng hay nhiều request độc lập; một request có thể làm request khác đọc nhầm schema.

Ví dụ thứ tự không nên dùng:

~~~java
// Không làm vậy nếu muốn statement chắc chắn chạy ở schema SALES.
PreparedStatement ps =
        connection.prepareStatement("SELECT * FROM BOOKS");
connection.setSchema("SALES");
try (ps; ResultSet rs = ps.executeQuery()) {
    // Không thể trông chờ setSchema áp dụng hồi tố lên ps.
}
~~~

Đoạn trên là **ví dụ phản diện về thứ tự gọi**, không phải code khuyến nghị. Thứ tự tốt hơn:

~~~java
connection.setSchema("SALES");
try (PreparedStatement ps =
        connection.prepareStatement("SELECT * FROM BOOKS");
     ResultSet rs = ps.executeQuery()) {
    // Đọc kết quả trong phạm vi tài nguyên còn mở.
}
~~~

Hai đoạn trên giả định `connection` do bên ngoài cung cấp, bảng đã có. Trong ứng dụng cần bind tham số, hãy gán bằng `ps.setXxx(...)` trước khi gọi `executeQuery()` và mở `ResultSet` bằng khối `try` lồng nhau.

## 4. Ví dụ Java 17+ chạy được: một database, hai schema

Ví dụ dùng H2 2.5.252 chạy trong bộ nhớ; mỗi lần chạy tạo mới dữ liệu. Chương trình có **hai bảng cùng tên `BOOKS`** ở `PUBLIC` và `SALES`, sau đó đọc `BOOKS` theo schema mặc định, đổi schema và đọc lại. H2 là database để thực hành; API `Connection.getSchema()`/`setSchema()` là JDBC chuẩn.

Cấu trúc thư mục:

~~~text
jdbc-schema-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── JdbcSchemaDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jdbc-schema-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.5.252</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>JdbcSchemaDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/JdbcSchemaDemo.java`:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class JdbcSchemaDemo {

    private static void printTitle(
            Connection connection, String label, String sql)
            throws SQLException {

        // PreparedStatement được tạo sau khi schema đã chọn xong.
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setInt(1, 1);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Khong tim thay BOOKS.ID = 1");
                }
                System.out.println(
                        label + ": " + rs.getString("TITLE"));
            }
        }
    }

    public static void main(String[] args) throws SQLException {
        // Cùng một connection suốt bài demo.
        // H2 in-memory không cần DB_CLOSE_DELAY vì connection còn mở.
        String url = "jdbc:h2:mem:jdbc_schema_demo";

        try (Connection connection = DriverManager.getConnection(url)) {

            // Chuẩn bị hai schema có bảng trùng tên.
            try (Statement setup = connection.createStatement()) {
                setup.execute("CREATE SCHEMA SALES");
                setup.execute("CREATE TABLE PUBLIC.BOOKS "
                        + "(ID INT PRIMARY KEY, TITLE VARCHAR(50))");
                setup.execute("CREATE TABLE SALES.BOOKS "
                        + "(ID INT PRIMARY KEY, TITLE VARCHAR(50))");
                setup.execute("INSERT INTO PUBLIC.BOOKS "
                        + "VALUES (1, 'Public book')");
                setup.execute("INSERT INTO SALES.BOOKS "
                        + "VALUES (1, 'Sales book')");
            }

            String originalSchema = connection.getSchema();
            System.out.println("Schema ban dau: " + originalSchema);

            // Tên BOOKS không có prefix: mặc định H2 là PUBLIC.
            printTitle(connection, "BOOKS mac dinh",
                    "SELECT TITLE FROM BOOKS WHERE ID = ?");

            try {
                connection.setSchema("SALES");
                System.out.println(
                        "Schema sau setSchema: " + connection.getSchema());

                // Được chuẩn bị sau setSchema -> phân giải sang SALES.
                printTitle(connection, "BOOKS sau khi doi",
                        "SELECT TITLE FROM BOOKS WHERE ID = ?");

                // Tên đầy đủ chỉ rõ schema PUBLIC.
                printTitle(connection, "PUBLIC.BOOKS",
                        "SELECT TITLE FROM PUBLIC.BOOKS WHERE ID = ?");
            } finally {
                // Bài demo H2 đảm bảo originalSchema là PUBLIC.
                // Khôi phục trước khi đóng/hoàn trả connection.
                connection.setSchema(originalSchema);
                System.out.println(
                        "Schema da khoi phuc: " + connection.getSchema());
            }
        }
    }
}
~~~

Yêu cầu: JDK 17+ và Maven có thể tải dependencies. Trong thư mục `jdbc-schema-demo`:

~~~bash
mvn -q compile exec:java
~~~

`stdout` mong đợi khi chạy với H2 2.5.252:

~~~text
Schema ban dau: PUBLIC
BOOKS mac dinh: Public book
Schema sau setSchema: SALES
BOOKS sau khi doi: Sales book
PUBLIC.BOOKS: Public book
Schema da khoi phuc: PUBLIC
~~~

Giải thích:

1. H2 dùng `PUBLIC` làm schema mặc định của connection mới. Chương trình tạo thêm `SALES` và tạo bảng `BOOKS` riêng trong mỗi schema.
2. Khi schema là `PUBLIC`, `SELECT ... FROM BOOKS` đọc hàng `Public book`.
3. Sau `connection.setSchema("SALES")`, chương trình **tạo PreparedStatement mới** và cùng câu SQL không có schema prefix trả về `Sales book`.
4. Câu `SELECT ... FROM PUBLIC.BOOKS` luôn chỉ rõ bảng `PUBLIC.BOOKS` trong demo, cho dù current schema là `SALES`.
5. Khối `finally` khôi phục schema trước khi thoát; các statement và result set đều được đóng qua `try-with-resources`.

Mỗi database có các quy tắc riêng. Output trên mô tả **H2 với cấu hình đã nêu**, không phải cam kết rằng mọi DBMS đều có schema mặc định `PUBLIC` hoặc xử lý chữ hoa/chữ thường giống H2. Với PostgreSQL, Oracle, SQL Server hoặc các hệ khác, hãy kiểm tra driver và cấu trúc database thực tế.

## 5. Cách đọc danh sách schema khi cần chẩn đoán

Nếu chưa biết tên schema đúng, `DatabaseMetaData` cung cấp metadata được driver hỗ trợ:

~~~java
// connection là JDBC Connection đang mở, thuộc phạm vi caller.
try (ResultSet schemas = connection.getMetaData().getSchemas()) {
    while (schemas.next()) {
        String name = schemas.getString("TABLE_SCHEM");
        String catalog = schemas.getString("TABLE_CATALOG");
        System.out.println(catalog + " / " + name);
    }
}
~~~

Đây là **đoạn minh họa**, không có output cố định vì danh sách tùy DBMS, user và driver. Có overload `getSchemas(String catalog, String schemaPattern)` để lọc khi driver hỗ trợ. Metadata giúp kiểm tra cách viết tên schema, nhưng **không thay thế kiểm soát quyền truy cập**, cũng không chứng minh người dùng có quyền SELECT/UPDATE trên mọi đối tượng trong schema.

Ví dụ chẩn đoán có thể kiểm tra lần lượt: `connection.getSchema()`, danh sách từ `getMetaData().getSchemas()`, quyền DB user, tên schema/bảng thực tế và câu SQL có prefix schema hay không.

## 6. Khi dùng `DataSource`, connection pool và transaction

Ứng dụng thực tế thường lấy connection từ `DataSource` (nhiều trường hợp do pool quản lý), thay vì gọi `DriverManager` cho từng request. **Schema là trạng thái của connection/session**, do đó cần đặc biệt quan tâm vòng đời.

- Nếu **chỉ một request** mượn connection, hãy chọn schema **ngay sau khi mượn và trước khi chuẩn bị SQL**.
- Sau truy vấn, đóng `ResultSet`/`PreparedStatement` và đóng connection do mình mượn để pool nhận lại. `close()` trên pooled connection thường có nghĩa trả về pool, không nhất thiết hủy kết nối vật lý.
- Nếu code thay schema tạm thời trên connection **do mình quản lý**, hãy lưu schema cũ và khôi phục trong `finally`. Nếu `getSchema()` trả `null` hoặc driver có quy tắc reset đặc biệt, xử lý theo driver/pool; **không giả định `setSchema(null)` luôn khôi phục an toàn**.
- Đừng cho rằng pool tự động reset schema trên mọi driver/cấu hình. Cần cấu hình, kiểm thử việc reset khi trả/mượn connection hoặc bảo đảm mọi request thiết lập trạng thái được phép trước khi truy vấn.
- Nếu connection được transaction manager/framework quản lý, **không tự đóng connection và không đổi schema tùy tiện bên ngoài hợp đồng quản lý transaction**. Dùng API của framework hoặc một phạm vi quản lý connection nhất quán.

Một hàm dùng connection được caller cấp có thể viết:

~~~java
// Chạy trong một lớp repository nhận connection từ bên ngoài.
// Caller quyết định schema, commit/rollback và close connection.
static int countBooks(Connection connection) throws SQLException {
    try (PreparedStatement ps =
            connection.prepareStatement("SELECT COUNT(*) FROM BOOKS");
         ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getInt(1);
    }
}
~~~

Trong hàm này, caller cần đặt schema **trước khi gọi** `countBooks`; hàm chỉ đóng các tài nguyên do nó tạo. Đây là đoạn trong ứng dụng đã có database/bảng, không chạy độc lập.

**Transaction và schema:** việc `setSchema()` có commit hay bị rollback làm đảo ngược thay đổi hay không là chi tiết DBMS/driver, không được JDBC bảo đảm chung. Ví dụ **H2** quy định `SET SCHEMA` không tự commit và rollback không hoàn tác lựa chọn schema. Đừng dùng `rollback()` thay cho bước reset schema, và tránh đổi schema giữa transaction đang có các statement hoạt động.

## 7. Bảo mật khi schema phụ thuộc người dùng hoặc tenant

Khi nhiều tenant cùng dùng một database nhưng có schema riêng, không nhận bất kỳ tên schema nào từ request rồi truyền thẳng vào `setSchema()`. Việc chọn schema có thể khiến truy vấn SQL không có prefix đọc dữ liệu sai tenant, nhất là khi connection được tái sử dụng trong pool.

Một cách kiểm soát là ánh xạ tenant đã xác thực sang danh sách schema được phép:

~~~java
// Minh họa ánh xạ cố định do ứng dụng quản lý.
static String schemaForTenant(String tenantId) {
    return switch (tenantId) {
        case "t1" -> "TENANT_ONE";
        case "t2" -> "TENANT_TWO";
        default -> throw new IllegalArgumentException("Tenant khong hop le");
    };
}

// Chọn schema rồi mới tạo PreparedStatement.
String schema = schemaForTenant(authenticatedTenantId);
connection.setSchema(schema);
~~~

Đoạn trên không chạy độc lập; `authenticatedTenantId` phải đến từ **ngữ cảnh định danh đã xác thực và phân quyền**, không lấy thẳng từ tham số do người dùng tự khai. Mỗi schema phải tồn tại và user DB cần có đúng quyền phù hợp. `setSchema()` **không phải ranh giới bảo mật**: kiểm soát quyền ở DB, kiểm soát ánh xạ tenant, giới hạn quyền tài khoản DB và kiểm thử việc reset trạng thái giữa request.

Dùng placeholder `?` trong `PreparedStatement` để bind **giá trị** trong điều kiện SQL; placeholder không thay cho **tên schema/bảng**. Nếu cần cấu trúc tên đối tượng động, dùng danh sách tên được phép hoặc cơ chế mapping đáng tin cậy, tuyệt đối không nối tên nhận tùy ý từ client vào câu SQL.

## 8. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| `getSchema()` trả `null` | Driver không xác định hoặc không báo tên schema hiện tại | Không gọi `equals` trên kết quả thiếu kiểm tra; xem tài liệu driver |
| Gọi `setSchema("SALES")` nhưng truy vấn vẫn vào schema cũ | Statement đã chuẩn bị trước khi đổi; driver bỏ qua schema; DBMS dùng search path riêng | Đổi schema trước `prepareStatement()`, kiểm tra `getSchema()` và truy vấn thực tế |
| `SQLException` sau `setSchema(...)` | Connection đóng, schema không tồn tại, không được phép hoặc lỗi driver/DBMS | Kiểm tra connection, metadata, tên schema và quyền |
| Không tìm thấy bảng khi SQL không có schema prefix | Schema mặc định không chứa bảng; tên hoặc cách phân giải không đúng | Kiểm tra `getSchema()`; dùng `SCHEMA.TABLE` đúng tên |
| Dữ liệu bị lẫn giữa hai request | Pool tái sử dụng connection còn trạng thái schema cũ | Reset schema theo pool/framework và kiểm thử cách ly tenant |
| Đặt `setSchema("sales")` thất bại trên H2 | H2 xử lý tên schema phân biệt chữ hoa/chữ thường; tên không quote thường lưu uppercase | Dùng tên chính xác, ví dụ `SALES` |
| Nhầm `setSchema` là tạo schema | Method chỉ đổi schema đang truy cập | Tạo/migrate schema bằng công cụ quản lý DB riêng |
| Nghĩ `rollback()` sẽ trả schema cũ | Quy tắc transaction của thay đổi schema không đồng nhất giữa DBMS | Khôi phục tường minh theo hợp đồng của connection |
| Đổi schema nhưng thiếu quyền SELECT | `setSchema` không cấp quyền trên bảng | Cấu hình quyền DB phù hợp nguyên tắc tối thiểu |

Nếu phải truy cập nhiều schema trong cùng luồng xử lý, có thể cân nhắc **tên bảng đầy đủ** (ví dụ `SALES.BOOKS`) để tránh thay đổi trạng thái connection, miễn là DBMS hỗ trợ và hợp đồng quyền truy cập cho phép. Việc dùng tên đầy đủ không thay thế việc đặt quyền đúng.

## 9. Checklist thực hành

1. Xác định tên schema tồn tại, cách viết chữ hoa/chữ thường và quyền của tài khoản kết nối.
2. Phân biệt `schema` và `catalog` theo database/driver đang dùng.
3. Mở hoặc mượn `Connection`; gọi `getSchema()` nếu cần ghi nhận trạng thái hiện tại.
4. Gọi `setSchema(target)` **trước khi tạo `Statement`/`PreparedStatement`**.
5. Xác minh việc đổi có hiệu lực với driver thực tế; xử lý `SQLException` và khả năng driver bỏ qua yêu cầu.
6. Đọc và xử lý `ResultSet` trong scope còn mở; dùng `try-with-resources` cho tài nguyên sở hữu.
7. Khi dùng pooled connection, có chiến lược reset hoặc khởi tạo trạng thái schema nhất quán cho mỗi đơn vị công việc.
8. Với multi-tenant, tên schema phải được quyết định từ danh tính đã xác thực, ánh xạ đã phê duyệt và quyền DB.
9. Không dựa vào `rollback` hoặc `close` để suy ra schema tự động khôi phục nếu chưa có bảo đảm của DBMS/pool.

**Điểm cần nhớ:** `getSchema()` đọc schema hiện tại của **một connection**; `setSchema(name)` yêu cầu đổi schema để những statement **tạo sau đó** sử dụng ngữ cảnh phù hợp. Kết quả còn tùy driver/DBMS, vì vậy hãy xác minh trên database thật và quản lý trạng thái connection cẩn thận.

## Tài liệu tham khảo

- [Java SE 17: `java.sql.Connection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html) — hợp đồng `getSchema()`, `setSchema()` và quy tắc statement đã chuẩn bị.
- [Java SE 17: `java.sql.DatabaseMetaData`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html) — `getSchemas()` và khả năng đọc metadata.
- [H2: JDBC `JdbcConnection`](https://h2database.github.io/javadoc/org/h2/jdbc/JdbcConnection.html) — cách H2 triển khai `setSchema()`/`getSchema()`, tên schema phân biệt chữ hoa/chữ thường.
- [H2: SQL commands](https://h2database.github.io/html/commands.html) — `CREATE SCHEMA`, `SET SCHEMA` và hành vi transaction trong H2.
