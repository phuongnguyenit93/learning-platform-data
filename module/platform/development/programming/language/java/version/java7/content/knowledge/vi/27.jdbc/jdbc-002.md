# Thứ tự phụ thuộc tài nguyên trong một lần truy vấn JDBC

## Mục tiêu

Khi thực hiện một truy vấn bằng JDBC, các đối tượng không tồn tại độc lập: `ResultSet` được tạo bởi `Statement`/`PreparedStatement`, còn statement được tạo từ một `Connection`. Hiểu mối phụ thuộc này giúp đọc kết quả đúng lúc, giải phóng tài nguyên sớm, tránh rò rỉ kết nối và tránh trả về một cursor đã bị đóng.

Phạm vi bài: **một lần thực thi truy vấn SQL qua JDBC đồng bộ trên Java 17+**, đặc biệt là `SELECT` trả về nhiều hàng. Những nguyên tắc vòng đời này vẫn có hiệu lực trong JDBC hiện nay, kể cả khi connection được cấp bởi pool hoặc framework.

## 1. Chuỗi phụ thuộc và quyền sở hữu

~~~text
DataSource / connection pool  (quản lý ở cấp ứng dụng)
         |
         | getConnection()
         v
Connection                      (được mượn cho đơn vị công việc)
         |
         | prepareStatement(sql)
         v
PreparedStatement               (gắn với Connection)
         |
         | setXxx(...) -> executeQuery()
         v
ResultSet                       (kết quả gắn với Statement)
         |
         | next(), getXxx(...)
         v
Giá trị Java / DTO / List       (dữ liệu đã tách khỏi JDBC)
~~~

- **`DataSource` hoặc pool** cung cấp `Connection`. Với pool, lời gọi `Connection.close()` thường hoàn trả connection về pool. Không tạo/đóng cả pool cho từng truy vấn.
- **`Connection`** đại diện phiên làm việc JDBC với cơ sở dữ liệu; dùng nó để tạo statement và quản lý transaction khi chính phạm vi hiện tại sở hữu transaction.
- **`PreparedStatement`** kế thừa `Statement`, được tạo bởi `Connection.prepareStatement(sql)`. Nó lưu câu SQL có tham số, cho phép gán giá trị và chạy truy vấn.
- **`ResultSet`** là đối tượng duyệt dữ liệu của một lần thực thi tạo ra kết quả. Nó phụ thuộc vào statement sinh ra nó; đọc các hàng bằng `next()` và `getXxx(...)` trong lúc result set còn mở.
- **DTO/record/List** được tạo từ dữ liệu đã đọc là đối tượng Java thông thường. Sau khi copy dữ liệu cần thiết, chúng không còn phụ thuộc vào connection, statement hay result set.

Hãy phân biệt **quan hệ tạo ra/phụ thuộc** với **quyền đóng tài nguyên**: phương thức tự gọi `dataSource.getConnection()` thường phải đóng `Connection` nó vừa mượn; nếu một phương thức nhận `Connection` do caller hoặc transaction manager cấp, caller/manager mới là chủ sở hữu connection.

## 2. Mở theo chiều từ cha xuống con; đóng theo chiều ngược lại

| Thứ tự mở | Hành động | Tài nguyên có sau bước này |
| --- | --- | --- |
| 1 | `dataSource.getConnection()` hoặc `DriverManager.getConnection(...)` | `Connection` |
| 2 | `connection.prepareStatement(sql)` | `PreparedStatement` |
| 3 | `statement.setInt(...), setString(...), ...` | Các tham số đã được gán; chưa có `ResultSet` |
| 4 | `statement.executeQuery()` | `ResultSet` |
| 5 | `resultSet.next()` và `getXxx(...)` | Dữ liệu được xử lý khi cả ba tài nguyên còn hợp lệ |

Trình tự giải phóng mong muốn sau khi đã xử lý xong dữ liệu:

~~~text
Đóng ResultSet
    -> đóng PreparedStatement
        -> đóng Connection (chỉ nếu phạm vi này sở hữu)
~~~

**Vì sao phải đóng theo chiều ngược?** Đối tượng con có thể cần đối tượng cha trong khi đọc dữ liệu hoặc giải phóng tài nguyên. Đóng `Connection` sớm có thể làm statement/result set không dùng được; đóng statement sớm sẽ đóng result set hiện tại của nó. Dù JDBC có cơ chế đóng dây chuyền, đóng rõ từng tài nguyên đã mở vẫn giúp scope và trách nhiệm dễ kiểm chứng.

Theo JDBC, `Statement.close()` đóng cả `ResultSet` hiện tại nếu có; việc chạy lại statement cũng tự đóng result set hiện tại theo mặc định. Vì vậy, **không giữ một `ResultSet` để tiếp tục đọc sau khi đóng hoặc tái thực thi statement đã sinh ra nó**.

## 3. Quy tắc nên dùng: `try-with-resources`

Cả `Connection`, `Statement`/`PreparedStatement` và `ResultSet` đều hỗ trợ `AutoCloseable`. Java `try-with-resources` tự gọi `close()` khi thoát scope, kể cả khi có `return` hoặc lỗi; các tài nguyên cùng khai báo trong header được đóng **từ phải sang trái**, tức ngược thứ tự mở.

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT id, name FROM employee WHERE id >= ? ORDER BY id")) {

    statement.setInt(1, 2);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            int id = resultSet.getInt("id");
            String name = resultSet.getString("name");
            // Xử lý id và name ngay trong scope của resultSet.
        }
    } // 1. resultSet.close()
}     // 2. statement.close(); 3. connection.close()
~~~

Đây là **đoạn minh họa trong ứng dụng đã có `DataSource` và bảng `employee`**, không phải chương trình chạy độc lập. Đặt `ResultSet` trong khối `try` lồng nhau vì cần gán tham số cho `PreparedStatement` trước khi gọi `executeQuery()`. `PreparedStatement` và `Connection` được khai báo cùng header: tạo connection trước, tạo statement sau; Java tự đóng statement trước rồi đến connection.

Nếu `prepareStatement` thất bại, connection đã mở vẫn được đóng. Nếu `executeQuery` hoặc `resultSet.next()` thất bại, các tài nguyên đã mở trong các scope tương ứng vẫn được đóng. Nếu cả phần xử lý lẫn `close()` ném lỗi, lỗi đóng thường xuất hiện trong `Throwable.getSuppressed()` thay vì thay thế lỗi chính; đừng bỏ qua chúng khi chẩn đoán.

## 4. Ví dụ đầy đủ Java 17+ có thể chạy

Ví dụ dùng **H2 in-memory** để tạo dữ liệu thử, sau đó thực hiện **một lần SELECT** trong `findEmployees`. H2 chỉ phục vụ minh họa: quan hệ `Connection → PreparedStatement → ResultSet` là JDBC chuẩn, không phụ thuộc H2. JDK có JDBC API nhưng cần thêm JDBC driver của cơ sở dữ liệu.

Tạo cấu trúc:

~~~text
jdbc-resource-order/
├── pom.xml
└── src/main/java/JdbcResourceDemo.java
~~~

`pom.xml` (Maven, Java 17; driver H2 2.5.252):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jdbc-resource-order</artifactId>
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
            <scope>runtime</scope>
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
                    <mainClass>JdbcResourceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/JdbcResourceDemo.java`:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

public class JdbcResourceDemo {
    record Employee(int id, String name) {}

    static List<Employee> findEmployees(String url, int minimumId)
            throws SQLException {
        String sql = "SELECT id, name FROM employee "
                   + "WHERE id >= ? ORDER BY id";

        // Mở cha -> con: Connection -> PreparedStatement.
        try (Connection connection = DriverManager.getConnection(url);
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setInt(1, minimumId);
            List<Employee> employees = new ArrayList<>();

            // ResultSet tồn tại trong scope của statement.
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    employees.add(new Employee(
                            rows.getInt("id"),
                            rows.getString("name")));
                }
            } // Đóng ResultSet trước.

            return employees; // Dữ liệu đã được copy sang record.
        } // Đóng PreparedStatement, rồi Connection.
    }

    public static void main(String[] args) throws SQLException {
        // Giữ DB in-memory qua nhiều connection cho riêng demo.
        String url = "jdbc:h2:mem:jdbc_order;DB_CLOSE_DELAY=-1";

        // Chỉ chuẩn bị dữ liệu ví dụ; không thuộc lần SELECT cần học.
        try (Connection connection = DriverManager.getConnection(url);
             Statement setup = connection.createStatement()) {
            setup.executeUpdate(
                    "CREATE TABLE employee "
                    + "(id INT PRIMARY KEY, name VARCHAR(40) NOT NULL)");
            setup.executeUpdate(
                    "INSERT INTO employee (id, name) VALUES "
                    + "(1, 'An'), (2, 'Binh'), (3, 'Chi')");
        }

        for (Employee employee : findEmployees(url, 2)) {
            System.out.println(employee.id() + ": " + employee.name());
        }
    }
}
~~~

Từ thư mục `jdbc-resource-order` chạy:

~~~bash
mvn -q compile exec:java
~~~

`stdout` của chương trình:

~~~text
2: Binh
3: Chi
~~~

Giải thích đường đi của **lần `SELECT`**: `findEmployees` mở connection, tạo prepared statement, gán `minimumId = 2`, chạy SQL để nhận `ResultSet`, đọc từng hàng sang `Employee`, đóng result set, rồi tự đóng statement và connection trước khi trả `List<Employee>`. Ứng dụng vẫn sử dụng danh sách sau khi JDBC đã đóng vì các giá trị `id` và `name` đã được lấy ra khỏi cursor. Lệnh `ORDER BY id` làm thứ tự output xác định; tham số `?` được bind bằng `setInt`, không nối trực tiếp giá trị đầu vào vào SQL.

Ở ứng dụng thật, thường thay `DriverManager.getConnection(url)` bằng `dataSource.getConnection()` từ pool hoặc dùng cơ chế JDBC do framework quản lý. Hãy giữ nguyên quy tắc vòng đời; không tự đóng `DataSource` của toàn ứng dụng sau từng query.

## 5. Phụ thuộc tài nguyên ảnh hưởng đến thiết kế API

**API an toàn:** trả về dữ liệu đã đọc hết trong scope (`List<Employee>`, `Optional<Employee>`, record/DTO hoặc tổng hợp số liệu), sau đó đóng JDBC.

~~~java
// Ý tưởng dùng trong repository; phương thức findEmployees ở ví dụ trên
// đã làm đúng theo nguyên tắc này.
List<Employee> employees = findEmployees(url, 2);
// Tại đây không cần ResultSet/Connection còn mở.
~~~

**API dễ lỗi:** tạo `ResultSet` trong phương thức rồi trả nó cho caller trong khi connection hoặc statement đã đóng:

~~~java
// SAI: ví dụ phương thức không nên đưa vào ứng dụng.
static ResultSet brokenQuery(Connection connection) throws SQLException {
    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT id, name FROM employee")) {
        return ps.executeQuery();
    } // ps đóng tại đây, ResultSet đã trả về bị đóng theo.
}
~~~

Trong đoạn sai, dù caller có giữ connection mở thì việc `PreparedStatement` đóng khi thoát `try` vẫn làm `ResultSet` không còn dùng được. Nếu cả connection cũng nằm trong `try-with-resources`, sự phụ thuộc còn bị cắt ở cấp cao hơn. **Không trả `ResultSet` ra ngoài phạm vi sở hữu statement.**

Nếu kết quả rất lớn, đừng máy móc đưa toàn bộ vào `List`: hãy xử lý từng hàng ngay trong scope `ResultSet` hoặc dùng API streaming có hợp đồng đóng rõ ràng, bảo đảm connection và statement còn mở trong suốt quá trình tiêu thụ. `setFetchSize(...)` chỉ là gợi ý cho driver và không đảm bảo mọi database đều stream theo cách giống nhau.

## 6. Khi connection được cấp từ bên ngoài

Một repository có thể nhận `Connection` đã được caller mở để cùng tham gia transaction. Trong trường hợp đó, phương thức **chỉ sở hữu statement và result set**, không đóng connection:

~~~java
static int countEmployees(Connection connection, int minimumId)
        throws SQLException {
    String sql = "SELECT COUNT(*) FROM employee WHERE id >= ?";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setInt(1, minimumId);

        try (ResultSet rs = ps.executeQuery()) {
            rs.next();
            return rs.getInt(1);
        }
    } // Chỉ đóng ResultSet/PreparedStatement.
       // Caller quyết định commit/rollback và close Connection.
~~~

Đoạn trên là phương thức dùng trong ứng dụng đã có connection và bảng; nó không tự chạy độc lập. Đừng lồng `try (connection)` vào phương thức này nếu hợp đồng nói connection do caller quản lý. Nếu transaction được framework (ví dụ Spring) quản lý, hãy dùng API tích hợp với framework và để transaction manager điều phối kết nối; tránh tự ý `commit`, `rollback` hoặc `close` connection đang được nó sở hữu.

Với transaction thủ công, chỉ gọi `commit()` khi tất cả thao tác cần thiết đã thành công; lỗi phải kích hoạt `rollback()` theo hợp đồng transaction. Đặc biệt, đừng dựa vào `Connection.close()` để thay cho `commit()` hoặc `rollback()` khi còn transaction đang hoạt động: kết quả có thể phụ thuộc driver. Xử lý transaction trước khi trả connection về pool.

## 7. Các trường hợp vòng đời thường gây lỗi

| Tình huống | Hậu quả hoặc điểm cần nhớ | Cách xử lý |
| --- | --- | --- |
| Đóng connection trước khi đọc hết result set | Cursor/statement không còn dùng đáng tin cậy | Đọc trong scope của connection và statement |
| Trả `ResultSet` ra ngoài `try-with-resources` của statement | Result set đã đóng trước khi caller sử dụng | Trả DTO/record/List hoặc callback có scope rõ |
| Gọi `executeQuery()` lần hai trên cùng statement khi vẫn đọc result set cũ | JDBC mặc định đóng result set hiện tại của statement | Đọc xong kết quả thứ nhất hoặc dùng statement khác cho hai cursor đồng thời |
| Quên đóng statement/result set lúc lỗi | Có thể giữ cursor, handle và tài nguyên DB lâu hơn cần thiết | `try-with-resources` cho từng tài nguyên được sở hữu |
| Đóng connection do caller/transaction manager cấp | Làm hỏng phạm vi transaction lớn hơn | Ghi rõ chủ sở hữu; chỉ đóng tài nguyên do mình mở |
| Ghép tham số đầu vào bằng nối chuỗi SQL | Lỗi escape và nguy cơ SQL injection | Dùng `PreparedStatement` với placeholder `?` và `setXxx` |
| Giữ result set lâu trong xử lý chậm/I/O khác | Chiếm connection/cursor, giảm dung lượng pool | Đọc hoặc chuyển đổi dữ liệu xong sớm, rồi giải phóng |
| Giữ `Blob`/`Clob` hoặc stream đọc từ cột sau khi đã đóng scope | Một số dữ liệu phụ thuộc tài nguyên DB/transaction | Tiêu thụ trong scope, đóng stream và gọi `free()` cho LOB khi phù hợp |

Lưu ý: riêng `SELECT` thường không cần tự gọi `commit()` trong ví dụ đơn giản, nhưng nếu connection đang ở transaction thủ công thì quy tắc transaction của caller vẫn áp dụng. `ResultSet` không phải ảnh chụp dữ liệu có thể sử dụng tùy ý sau khi kết nối đóng.

## 8. Checklist cho một lần truy vấn JDBC

1. Xác định ai sở hữu `Connection`: phương thức hiện tại hay caller/framework.
2. Mở `Connection` trước khi tạo `PreparedStatement`; gán mọi tham số trước `executeQuery()`.
3. Giữ `ResultSet` bên trong scope của statement và đọc/ánh xạ hết phần dữ liệu cần thiết ở đó.
4. Dùng `try-with-resources` để đóng các tài nguyên do scope hiện tại sở hữu theo thứ tự `ResultSet → PreparedStatement → Connection`.
5. Không trả cursor JDBC đã đóng; trả dữ liệu Java hoặc định nghĩa API streaming quản lý scope rõ ràng.
6. Nếu có transaction, xử lý `commit/rollback` đúng quyền sở hữu trước khi kết thúc connection.
7. Trong ứng dụng dùng pool, đóng connection mượn đúng lúc để hoàn trả nó; không đóng cả pool ở cuối query.

**Ghi nhớ:** `DataSource` cấp `Connection`; `Connection` tạo `PreparedStatement`; `PreparedStatement` tạo `ResultSet`. **Mở từ ngoài vào trong, đọc khi toàn chuỗi còn sống, đóng từ trong ra ngoài.**

## Tài liệu tham khảo hiện hành

- [Java SE 17 — `Statement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): quan hệ giữa statement và result set, cơ chế đóng result set.
- [Java SE 17 — `ResultSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): thời điểm đóng và cách đọc cursor.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): tài nguyên trong `try-with-resources`.
- [H2 Database](https://github.com/h2database/h2database): driver H2 dùng riêng cho ví dụ chạy độc lập.
