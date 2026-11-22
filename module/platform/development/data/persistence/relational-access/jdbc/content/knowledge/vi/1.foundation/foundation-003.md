# Phân biệt JDBC, SQL, driver và hệ quản trị cơ sở dữ liệu

Khi ứng dụng Java cần lưu hoặc đọc dữ liệu từ cơ sở dữ liệu quan hệ, bốn khái niệm thường xuất hiện cùng lúc: **JDBC**, **SQL**, **JDBC driver** và **hệ quản trị cơ sở dữ liệu (DBMS)**. Chúng liên quan chặt chẽ nhưng đảm nhiệm những phần việc khác nhau. Nhận diện đúng ranh giới giúp chọn thư viện, thiết kế truy vấn và chẩn đoán lỗi kết nối chính xác.

Trong chương *Nền tảng*, bài này tập trung vào **JDBC — Java Database Connectivity API for relational database access** — và giải thích cách một ứng dụng Java gửi yêu cầu tới cơ sở dữ liệu quan hệ.

## 1. Bốn khái niệm và nhiệm vụ của từng thành phần

| Thành phần | Bản chất | Trách nhiệm chính | Ví dụ |
| --- | --- | --- | --- |
| **JDBC** | API chuẩn phía Java | Cung cấp giao diện để mở kết nối, truyền tham số, thực thi lệnh và đọc kết quả | `Connection`, `PreparedStatement`, `ResultSet`, `SQLException` |
| **SQL** | Ngôn ngữ làm việc với dữ liệu quan hệ | Diễn đạt truy vấn, thay đổi dữ liệu, khai báo cấu trúc và điều khiển giao dịch/quyền theo khả năng DBMS | `SELECT`, `INSERT`, `UPDATE`, `CREATE TABLE` |
| **JDBC driver** | Thành phần phần mềm triển khai JDBC để giao tiếp với một hệ cơ sở dữ liệu | Chuyển lời gọi JDBC thành giao tiếp phù hợp với database và trả kết quả cho API JDBC | PostgreSQL JDBC Driver, MySQL Connector/J, Microsoft JDBC Driver for SQL Server |
| **DBMS** | Phần mềm quản lý cơ sở dữ liệu | Phân tích, thực thi SQL; quản lý lưu trữ, chỉ mục, giao dịch, khóa, quyền và ràng buộc | PostgreSQL, MySQL, SQL Server, Oracle Database |

Có thể ghi nhớ bằng bốn câu ngắn:

- **JDBC:** Chương trình Java *gọi qua giao diện nào?*
- **SQL:** Chương trình *yêu cầu xử lý dữ liệu gì?*
- **Driver:** Lời gọi Java *đi tới DBMS bằng cách nào?*
- **DBMS:** *Ai thực sự quản lý dữ liệu và thực thi yêu cầu?*

**Cơ sở dữ liệu (database)** là tập dữ liệu được tổ chức và quản lý; **DBMS** là phần mềm quản trị tập dữ liệu đó. Trong hội thoại kỹ thuật, từ “database” đôi khi được dùng để nói tắt cả DBMS, nhưng hai khái niệm không đồng nhất.

## 2. Sơ đồ tương tác từ ứng dụng Java tới dữ liệu

Đối với một hệ quản trị cơ sở dữ liệu chạy trên máy chủ, luồng phổ biến là:

```text
+---------------------------+
| Ứng dụng Java             |
| logic nghiệp vụ           |
| SQL và các giá trị đầu vào|
+-------------+-------------+
              |
              | Gọi API JDBC:
              | getConnection, prepareStatement,
              | setXxx, executeQuery, ...
              v
+---------------------------+
| API JDBC                  |
| java.sql / javax.sql      |
| Hợp đồng giao diện Java   |
+-------------+-------------+
              |
              | Phương thức do driver hiện thực
              v
+---------------------------+
| JDBC driver               |
| Giao thức/định dạng phù hợp|
| với DBMS cụ thể           |
+-------------+-------------+
              |
              | Kết nối/giao tiếp với DBMS
              | (thường qua mạng TCP)
              v
+---------------------------+
| DBMS                      |
| Phân tích và thực thi SQL |
| Quyền, giao dịch, khóa,   |
| ràng buộc và lưu trữ      |
+-------------+-------------+
              |
              v
       Dữ liệu trong database
```

Kết quả đi ngược chiều: **DBMS** trả trạng thái/kết quả qua **driver**, driver cung cấp dữ liệu theo **API JDBC**, còn ứng dụng đọc dữ liệu qua `ResultSet` hoặc nhận số hàng bị ảnh hưởng, tham số OUT và ngoại lệ tương ứng.

Đây là **mô hình điển hình** cho DBMS máy chủ như PostgreSQL. Một số hệ cơ sở dữ liệu nhúng (ví dụ SQLite hoặc H2 ở chế độ nhúng) có thể chạy ngay trong tiến trình ứng dụng, không cần đường truyền mạng riêng. Sơ đồ vì thế giải thích **vai trò logic**, không bắt buộc mọi thành phần phải là một tiến trình hoặc máy tính khác nhau.

### Theo dõi một truy vấn cụ thể

Giả sử chương trình cần tìm tài khoản đang hoạt động:

```sql
SELECT id, full_name
FROM app_user
WHERE active = TRUE;
```

1. Ứng dụng Java tạo hoặc lấy `Connection` qua JDBC.
2. Ứng dụng cung cấp câu SQL và các tham số cho `PreparedStatement`.
3. Driver tương tác với DBMS theo giao thức và khả năng của sản phẩm tương ứng.
4. DBMS kiểm tra cú pháp, quyền truy cập, xây dựng/thực hiện kế hoạch truy vấn và tạo kết quả.
5. Driver cung cấp kết quả thông qua `ResultSet`; ứng dụng đọc từng dòng.

**SQL không tự mở kết nối**, **JDBC không tự lưu trữ dữ liệu**, **driver không thay thế DBMS**. Sự phân công này là cơ sở để xác định lỗi xảy ra ở đâu.

## 3. JDBC là API, không phải một hệ cơ sở dữ liệu

JDBC gồm các giao diện và lớp tiêu chuẩn trong Java, chủ yếu ở `java.sql` và `javax.sql`. Nó giúp ứng dụng tương tác với nhiều DBMS thông qua những cách gọi Java tương tự nhau.

| API | Mục đích |
| --- | --- |
| `DriverManager` | Tìm driver phù hợp với JDBC URL và mở kết nối |
| `DataSource` | Nguồn cung cấp `Connection`, thường được dùng với connection pool |
| `Connection` | Đại diện cho phiên kết nối; tạo statement, quản lý autocommit và giao dịch |
| `Statement` | Thực thi câu SQL trực tiếp |
| `PreparedStatement` | Thực thi SQL có tham số `?` và gán giá trị bằng `setXxx()` |
| `CallableStatement` | Gọi stored procedure/function khi DBMS và driver hỗ trợ |
| `ResultSet` | Duyệt dữ liệu dạng hàng/cột từ truy vấn |
| `SQLException` | Thông báo lỗi truy cập dữ liệu hoặc thực thi SQL |

Ví dụ, `Connection` là một giao diện thuộc JDBC. Đối tượng `Connection` cụ thể thường được driver triển khai. Nhờ đó cùng một đoạn mã thao tác `prepareStatement()`, `setLong()` và `executeQuery()` có thể sử dụng với nhiều loại DBMS, **nếu** driver tương ứng được cài đặt và câu SQL/schema phù hợp.

### JDBC chịu trách nhiệm đến đâu?

JDBC quy định **hợp đồng API** và các kiểu kết quả Java thường dùng. Nó không quyết định cấu trúc bảng, chỉ mục, tài khoản được phép truy vấn hay kế hoạch thực thi trong database. Những công việc đó thuộc về DBMS và thiết kế schema. JDBC cũng không tự bảo đảm một câu SQL của PostgreSQL sẽ chạy nguyên vẹn trên SQL Server.

Ứng dụng thường dùng JDBC qua thư viện/framework như Spring JDBC hoặc JPA/Hibernate. Các tầng trừu tượng đó có thể giúp giảm mã lặp lại, nhưng khi sử dụng một cơ sở dữ liệu quan hệ thông qua JDBC, phía dưới vẫn cần driver và DBMS phù hợp.

## 4. SQL là ngôn ngữ diễn đạt yêu cầu dữ liệu

**Structured Query Language (SQL)** diễn tả các thao tác đối với dữ liệu quan hệ. SQL là **ngôn ngữ**, không phải một thư viện Java hay một driver.

Một số nhóm thao tác quen thuộc:

| Nhóm thường gọi | Ví dụ | Công dụng |
| --- | --- | --- |
| DDL (Data Definition Language) | `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` | Định nghĩa và thay đổi cấu trúc |
| DML (Data Manipulation Language) | `INSERT`, `UPDATE`, `DELETE` | Thay đổi bản ghi |
| Truy vấn dữ liệu | `SELECT` | Đọc và tính toán trên dữ liệu |
| Điều khiển giao dịch | `COMMIT`, `ROLLBACK` | Xác nhận hoặc hủy giao dịch tùy hệ quản trị |
| Điều khiển quyền | `GRANT`, `REVOKE` | Cấp và thu hồi quyền nếu DBMS hỗ trợ |

SQL có chuẩn và cũng có **phương ngữ (dialect)** riêng theo từng DBMS. Ví dụ các cách phân trang, cú pháp tạo cột tự tăng, kiểu JSON và cú pháp stored procedure có thể khác nhau. Driver chịu trách nhiệm truyền/diễn giải lời gọi JDBC phù hợp, **không tự động chuyển toàn bộ SQL của hệ này thành SQL hợp lệ của hệ khác**.

Trong `PreparedStatement`, dấu `?` biểu thị *vị trí giá trị tham số*, không phải chỗ thay tùy ý cả cú pháp SQL:

```java
String sql = "SELECT id FROM app_user WHERE active = ?";
try (PreparedStatement stmt = connection.prepareStatement(sql)) {
    stmt.setBoolean(1, true);
    // executeQuery() ...
}
```

Không dùng `?` để thay tên bảng, tên cột hoặc từ khóa SQL:

```sql
-- Sai ý nghĩa tham số JDBC: placeholder không đại diện tên bảng.
SELECT id FROM ? WHERE active = ?;
```

Khi tên bảng/cột cần thay đổi động, ứng dụng phải lựa chọn từ danh sách định danh **được cho phép** và xây dựng cú pháp có kiểm soát. Tránh ghép trực tiếp đầu vào tùy ý của người dùng thành SQL.

## 5. JDBC driver là cầu nối thực thi API

Một driver triển khai hợp đồng JDBC cho một hệ database cụ thể. Nó thường:

- Nhận JDBC URL và thông tin xác thực để thiết lập kết nối phù hợp với sản phẩm.
- Hiện thực các đối tượng JDBC như `Connection`, `PreparedStatement` và `ResultSet`.
- Chuyển yêu cầu và dữ liệu tham số sang định dạng/giao thức được DBMS hỗ trợ.
- Chuyển dữ liệu, trạng thái và lỗi từ DBMS thành kết quả hoặc ngoại lệ JDBC.

Chẳng hạn, để kết nối PostgreSQL, ứng dụng thường cần **PostgreSQL JDBC Driver** (thư viện có class `org.postgresql.Driver`) trên runtime classpath. Với MySQL dùng **MySQL Connector/J**; với SQL Server dùng driver JDBC tương ứng. Chỉ có các lớp trong `java.sql` của JDK **không đủ** để Java tự giao tiếp với mọi DBMS.

### JDBC URL có mục đích gì?

JDBC URL cung cấp thông tin để driver xác định cách kết nối:

```text
jdbc:postgresql://localhost:5432/demo
jdbc:mysql://localhost:3306/demo
jdbc:sqlserver://localhost:1433;databaseName=demo
```

Các chuỗi trên minh họa **định dạng riêng của từng driver**, không phải ba địa chỉ có thể hoán đổi lẫn nhau. Địa chỉ máy chủ, cổng, tên database, tùy chọn TLS và thông tin xác thực phải phù hợp với môi trường triển khai.

Từ JDBC 4, driver đóng gói đúng chuẩn thường có thể tự đăng ký qua cơ chế Java service provider khi thư viện hiện diện trên classpath/module path thích hợp. Vì thế, với driver hiện đại thường **không cần** gọi `Class.forName("org.postgresql.Driver")` thủ công. Cần tra tài liệu driver nếu cơ chế nạp tự động không hoạt động.

### Driver và phiên bản JDBC

Driver phải tương thích với phiên bản Java/JDBC, DBMS và các tính năng đang dùng. Hỗ trợ `getObject(..., SomeClass.class)`, stored procedure, kiểu dữ liệu đặc thù và cách xử lý batch có thể khác nhau theo phiên bản. Việc có đủ API JDBC trong JDK không đồng nghĩa mọi driver hỗ trợ hoàn toàn mọi phương thức tùy chọn.

Driver dạng **Type 4** (pure Java giao tiếp trực tiếp với giao thức database) rất phổ biến ở ứng dụng Java hiện đại. Đây là một cách triển khai driver; khái niệm driver nói chung không bắt buộc phải là một tiến trình tách riêng.

## 6. DBMS thực sự làm những gì?

**DBMS** là phần mềm quản lý dữ liệu và tài nguyên truy cập dữ liệu. Sau khi nhận yêu cầu, DBMS thường đảm nhiệm:

1. **Xác thực và phân quyền:** kết nối có được phép đọc/ghi bảng hoặc gọi routine không?
2. **Phân tích SQL:** cú pháp có hợp lệ và bảng/cột có tồn tại không?
3. **Tối ưu và thực thi:** dùng chỉ mục hay quét bảng, chọn thứ tự join và kế hoạch truy vấn nào?
4. **Bảo đảm toàn vẹn:** áp dụng khóa chính, khóa ngoại, `NOT NULL`, `UNIQUE`, `CHECK` theo schema.
5. **Giao dịch và đồng thời:** phối hợp các thao tác commit/rollback, khóa hoặc cơ chế đồng thời tùy sản phẩm.
6. **Lưu trữ và phục hồi:** tổ chức dữ liệu trên bộ nhớ/đĩa, ghi log và thực hiện các cơ chế phục hồi phù hợp.

Ví dụ, lỗi **vi phạm khóa ngoại** phát sinh khi DBMS thực thi ràng buộc. JDBC driver chuyển thông tin lỗi về Java dưới dạng `SQLException`; bản thân JDBC không phải nơi quyết định khóa ngoại có hợp lệ hay không.

Trong hệ thống máy chủ, DBMS thường là một dịch vụ trên máy khác. Trong hệ nhúng, DBMS có thể hoạt động trong cùng tiến trình với ứng dụng. Dù ở mô hình nào, nhiệm vụ quản lý dữ liệu vẫn thuộc về DBMS.

## 7. Ví dụ thực tế: từ SQL tới Java bằng JDBC và PostgreSQL

Giả sử ứng dụng cần lấy danh sách người dùng đang hoạt động. Ví dụ này chọn **PostgreSQL** để có một trường hợp cụ thể; các câu lệnh, tên driver và URL cần điều chỉnh nếu dùng DBMS khác.

### Bước 1: Tạo dữ liệu ở phía DBMS

Thực thi SQL sau trong database `demo` đã được tạo:

```sql
CREATE TABLE app_user (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    active BOOLEAN NOT NULL
);

INSERT INTO app_user (full_name, active)
VALUES ('An', TRUE), ('Bình', FALSE);
```

Đây là **SQL** mà PostgreSQL phân tích và thực thi. PostgreSQL lưu bảng và kiểm soát ràng buộc khóa chính cùng `NOT NULL`; JDBC không tạo schema hay dữ liệu trừ khi ứng dụng chủ động gửi câu lệnh tương ứng.

### Bước 2: Chuẩn bị driver và cấu hình

Ứng dụng cần có PostgreSQL JDBC Driver trong dependency/runtime classpath và môi trường chứa ba biến:

```text
APP_DB_URL=jdbc:postgresql://localhost:5432/demo
APP_DB_USER=<tài khoản đã được cấp quyền SELECT>
APP_DB_PASSWORD=<mật khẩu tài khoản>
```

Các giá trị trong dấu góc chỉ là chỗ điền cấu hình thực tế. Không ghi trực tiếp mật khẩu trong mã nguồn và không đưa thông tin xác thực vào log. Cổng `5432` chỉ là cổng PostgreSQL thường gặp; cổng thực tế do hệ thống quyết định.

### Bước 3: Viết mã Java sử dụng JDBC

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JdbcFoundationExample {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("APP_DB_URL");
        String user = System.getenv("APP_DB_USER");
        String password = System.getenv("APP_DB_PASSWORD");

        if (url == null || user == null || password == null) {
            throw new IllegalStateException("Thieu cau hinh ket noi database");
        }

        String sql =
                "SELECT id, full_name FROM app_user " +
                "WHERE active = ? ORDER BY id";

        try (Connection connection =
                     DriverManager.getConnection(url, user, password);
             PreparedStatement stmt = connection.prepareStatement(sql)) {

            stmt.setBoolean(1, true);

            try (ResultSet rs = stmt.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("id");
                    String name = rs.getString("full_name");
                    System.out.println(id + ": " + name);
                }
            }
        }
    }
}
```

Khi bảng chỉ có hai bản ghi mẫu trên, chương trình in ra **một hàng** với tên `An`; giá trị ID được DBMS tạo. Kết quả thực tế phụ thuộc dữ liệu đang có và quyền truy cập.

### Phân tích vai trò từng thành phần

| Trong ví dụ | Thuộc trách nhiệm của |
| --- | --- |
| `Connection`, `PreparedStatement`, `ResultSet`, `setBoolean()`, `executeQuery()` | **JDBC API** quy định cách Java gọi và nhận dữ liệu |
| `SELECT id, full_name FROM app_user WHERE active = ?` | **SQL** diễn đạt truy vấn |
| PostgreSQL JDBC Driver được nạp trong ứng dụng | **Driver** triển khai API và trao đổi với PostgreSQL |
| PostgreSQL xác thực, tìm hàng `active = TRUE`, trả kết quả | **DBMS** thực thi và quản lý dữ liệu |
| `System.getenv(...)`, in kết quả, quy tắc chọn `active = true` | **Ứng dụng Java** quyết định yêu cầu nghiệp vụ |

`try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` sau khi dùng. Trong ứng dụng thực tế có tải cao, người ta thường sử dụng `DataSource` cùng **connection pool** thay vì mở kết nối vật lý mới cho mỗi truy vấn; đây là lựa chọn về cách quản lý kết nối, không làm thay đổi các khái niệm JDBC/SQL/driver/DBMS.

## 8. Phân biệt lỗi theo lớp chịu trách nhiệm

Cùng là một `SQLException` ở Java, nhưng nguyên nhân có thể ở các tầng khác nhau. Chẩn đoán bằng **điểm phát sinh lỗi và cấu hình liên quan**, thay vì kết luận mọi lỗi đều là “JDBC hỏng”.

| Hiện tượng | Thành phần nên kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| `No suitable driver found` | Driver và JDBC URL | Đưa đúng driver vào runtime classpath, xác minh tiền tố URL và cơ chế đăng ký driver |
| Không kết nối được máy chủ, timeout kết nối | Mạng, địa chỉ/cổng, trạng thái DBMS, TLS và cấu hình driver | Kiểm tra DBMS có chạy và được phép truy cập hay không |
| Sai tài khoản/mật khẩu hoặc thiếu quyền `SELECT` | Xác thực/phân quyền trong DBMS | Kiểm tra quyền tài khoản và cấu hình kết nối |
| Cú pháp SQL không hợp lệ | Câu SQL, dialect của DBMS | Xem thông báo lỗi, phiên bản DBMS và tên bảng/cột |
| Vi phạm `UNIQUE` hoặc khóa ngoại | Dữ liệu và ràng buộc trong DBMS | Điều chỉnh dữ liệu nghiệp vụ hoặc quy trình ghi |
| `ResultSet` không chứa tên cột mong đợi | Câu `SELECT`, alias và mã ánh xạ Java | Đối chiếu các cột trả về với `rs.getXxx(...)` |
| Lỗi chỉ xảy ra khi đổi từ PostgreSQL sang MySQL | Driver, URL, kiểu SQL và schema | Thay đúng driver/URL và điều chỉnh cú pháp, kiểu dữ liệu, tính năng đặc thù |

Các driver thường chuyển lỗi database thành `SQLException`. Khi xử lý lỗi, có thể tham khảo `getSQLState()`, `getErrorCode()` và chuỗi exception nguyên nhân; mã lỗi cụ thể có thể khác theo hệ quản trị.

## 9. Các hiểu nhầm thường gặp

**“Có Java và JDBC là kết nối được mọi database.”** Chưa đủ. Ứng dụng cần driver phù hợp và thông tin kết nối hợp lệ. Một số database còn yêu cầu cấu hình TLS, xác thực riêng hoặc thư viện phụ thuộc.

**“JDBC chính là SQL.”** Không đúng. JDBC là tập API Java; SQL là ngôn ngữ yêu cầu xử lý dữ liệu. Một ứng dụng Python hay C# cũng có thể gửi SQL, nhưng không dùng giao diện JDBC của Java.

**“Driver là DBMS.”** Không đúng. Driver là thành phần tích hợp phía client; DBMS quản lý lưu trữ, truy vấn, chỉ mục và giao dịch ở phía dữ liệu. Với mô hình nhúng, chúng có thể nằm gần nhau về mặt triển khai nhưng vẫn khác vai trò.

**“Đổi driver là tự động đổi được hệ cơ sở dữ liệu.”** Chỉ thay driver thường không đủ. Cần kiểm tra lại SQL dialect, DDL, kiểu cột, khóa, hàm, transaction, JDBC URL và quyền trong DBMS mới.

**“`PreparedStatement` luôn khiến truy vấn nhanh hơn.”** Không thể khẳng định cho mọi trường hợp. `PreparedStatement` giúp truyền tham số có cấu trúc và giảm nguy cơ SQL injection qua giá trị tham số, còn hiệu năng phụ thuộc driver, DBMS, cache, kế hoạch truy vấn và số lần thực thi. Một số driver có thể chọn cách chuẩn bị hoặc thực thi khác nhau.

**“JDBC tự bảo đảm toàn bộ truy vấn chạy trong một transaction.”** JDBC cho phép điều khiển `setAutoCommit(false)`, `commit()` và `rollback()` trên `Connection`; cách DBMS thực thi transaction, mức cô lập và tính chất DDL vẫn do hệ quản trị quyết định.

## 10. Kiểm tra kiến thức

**Tình huống 1:** Ứng dụng dùng `DriverManager.getConnection("jdbc:postgresql://...")` nhưng báo `No suitable driver`. Cần kiểm tra SQL trước hay driver?

*Trả lời:* Kiểm tra driver PostgreSQL có trong runtime classpath và JDBC URL hợp lệ hay chưa. Lỗi có thể xảy ra trước khi SQL được gửi đi.

**Tình huống 2:** Câu `SELECT ... LIMIT 10` chạy trên PostgreSQL nhưng không hợp lệ trong một DBMS khác. Đây có phải lỗi của JDBC không?

*Trả lời:* Trước hết phải đối chiếu **dialect SQL** và cú pháp được DBMS đích chấp nhận. JDBC không tự dịch mọi phương ngữ SQL.

**Tình huống 3:** PostgreSQL trả lỗi vi phạm khóa ngoại khi thêm đơn hàng. Thành phần nào quyết định dữ liệu vi phạm ràng buộc?

*Trả lời:* **DBMS** thực thi ràng buộc; driver truyền lỗi về ứng dụng dưới dạng thông tin JDBC, thường là `SQLException`.

**Tình huống 4:** Đổi từ `DriverManager` sang `DataSource` và connection pool thì có còn dùng JDBC không?

*Trả lời:* Có. `DataSource` thuộc `javax.sql`; ứng dụng vẫn sử dụng `Connection`, `PreparedStatement` và các giao diện JDBC khác. Cách lấy và quản lý kết nối thay đổi, còn bản chất API JDBC vẫn giữ nguyên.

**Tình huống 5:** Khi viết `stmt.setBoolean(1, true)`, ai quyết định hàng nào thỏa mãn điều kiện `WHERE active = ?`?

*Trả lời:* Ứng dụng truyền giá trị qua **API JDBC**, driver đưa yêu cầu tới **DBMS**, và **DBMS** đánh giá điều kiện SQL dựa trên dữ liệu.

## Ghi nhớ

Một ứng dụng Java kết nối cơ sở dữ liệu quan hệ thường kết hợp **JDBC (API phía Java)**, **SQL (ngôn ngữ mô tả thao tác)**, **driver (triển khai cầu nối)** và **DBMS (phần mềm thực thi, quản lý dữ liệu)**. Khi lập trình, xác định đúng lớp chịu trách nhiệm sẽ giúp chọn đúng dependency, tạo đúng JDBC URL, viết câu SQL tương thích, quản lý giao dịch và giải quyết lỗi nhanh hơn.
