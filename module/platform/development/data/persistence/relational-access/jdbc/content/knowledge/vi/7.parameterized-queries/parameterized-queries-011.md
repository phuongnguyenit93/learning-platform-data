# Phân biệt chuẩn bị câu lệnh phía driver và phía máy chủ

Khi viết `connection.prepareStatement(sql)` trong Java, lập trình viên nhận một đối tượng `PreparedStatement` để truyền giá trị qua `?` và thực thi SQL. Tên gọi *prepared statement* dễ tạo ra một giả định: ngay thời điểm gọi `prepareStatement()`, hệ quản trị cơ sở dữ liệu đã phân tích câu SQL, tối ưu kế hoạch rồi lưu kế hoạch trên máy chủ. **Điều đó không được bảo đảm bởi API JDBC**.

Trong **JDBC (Java Database Connectivity API for relational database access)**, việc *chuẩn bị câu lệnh* có thể diễn ra chủ yếu **ở JDBC driver phía ứng dụng**, **ở máy chủ cơ sở dữ liệu (DBMS)**, hoặc kết hợp cả hai. Chế độ cụ thể phụ thuộc driver, cấu hình, cách kết nối, câu SQL và số lần thực thi. Bài thuộc chương *Truy vấn tham số* này giúp phân biệt các cơ chế, hiểu tác động đến tính đúng đắn, hiệu năng và vòng đời tài nguyên.

## 1. Phân biệt ba khái niệm thường bị gọi chung là “prepare”

| Khái niệm | Diễn ra ở đâu? | Có ý nghĩa gì? |
| --- | --- | --- |
| **JDBC `PreparedStatement`** | API Java và đối tượng do driver triển khai | Gắn câu SQL có dấu `?` với các phương thức `setXxx()`, `executeQuery()`, `executeUpdate()`... |
| **Chuẩn bị hoặc mô phỏng phía driver** (*client-side preparation / emulation*) | Trong tiến trình chạy ứng dụng Java | Driver giữ cấu trúc SQL, kiểu/giá trị tham số và xử lý cách gửi câu lệnh tới server; có thể tự tạo biểu diễn truy vấn cho mỗi lần chạy |
| **Chuẩn bị phía máy chủ** (*server-side prepared statement*) | Trong phiên kết nối ở DBMS | Server giữ một dạng câu lệnh đã được phân tích/chuẩn bị để có thể thực thi lại với tham số khác; cách lưu/tái sử dụng kế hoạch tùy DBMS |

**Chuẩn bị phía server không đồng nghĩa luôn lưu một kế hoạch thực thi cố định.** Một DBMS có thể phân tích câu SQL và giữ cấu trúc, nhưng lựa chọn lập kế hoạch lại theo giá trị tham số, phiên bản schema, thống kê hoặc chiến lược tối ưu. Chi tiết của PostgreSQL, MySQL, SQL Server và Oracle không hoàn toàn giống nhau.

### Hai luồng xử lý ở mức khái niệm

```text
                 Ứng dụng Java
            PreparedStatement(sql)
                    |
               setXxx(...), execute()
                    |
                JDBC driver
                    |
     +--------------+----------------+
     |                               |
     v                               v
 A. Chuẩn bị phía driver      B. Chuẩn bị phía máy chủ
 Driver quản lý mẫu SQL       Driver gửi yêu cầu prepare/
 và cách biểu diễn giá trị     parse cho server (có thể
 khi gửi sang server          ở lần execute đầu tiên)
     |                               |
     v                               v
 DBMS nhận lệnh phù hợp       Server giữ trạng thái
 và thực thi                  prepared theo cơ chế DBMS
                                     |
                                     v
                             Bind tham số, execute
                             (có thể lặp nhiều lần)
     |                               |
     +---------------+---------------+
                     |
               ResultSet / update count
                     |
                 Ứng dụng Java
```

Sơ đồ chỉ thể hiện **trách nhiệm logic**. Một số giao thức, như PostgreSQL extended query protocol, còn phân biệt thông điệp Parse, Bind và Execute; một statement không có tên (*unnamed*) vẫn có thể được phân tích phía server trong một lần thực thi mà **không** trở thành prepared statement có tên để tái sử dụng lâu dài.

## 2. `prepareStatement()` cam kết điều gì?

JDBC định nghĩa giao diện Java và cách truyền tham số. Một đoạn mã dùng API tiêu chuẩn:

```java
String sql = "SELECT id, total_amount FROM orders WHERE customer_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            long id = result.getLong("id");
            java.math.BigDecimal total =
                    result.getBigDecimal("total_amount");
            // Xu ly du lieu theo nghiep vu.
        }
    }
}
```

`connection` là một `java.sql.Connection` đã mở, `customerId` là `long`; đoạn mã nằm trong phương thức xử lý `SQLException` và import `java.sql.PreparedStatement`, `java.sql.ResultSet`. Bảng `orders` cùng các cột phải tồn tại trong DBMS.

Ở mức API, ứng dụng có thể tin vào những điều sau khi driver tuân thủ hợp đồng JDBC:

- `prepareStatement(sql)` trả về một đối tượng có thể gán tham số và thực thi câu SQL được hỗ trợ.
- Dấu `?` đại diện cho **vị trí giá trị**; các chỉ số bắt đầu từ **1**.
- `setLong()`, `setString()`, `setBigDecimal()`, `setNull()`... liên kết giá trị vào các vị trí tương ứng.
- Cùng một đối tượng `PreparedStatement` có thể được dùng để thực thi lại với các giá trị tham số mới trong phạm vi vòng đời của statement.
- `executeQuery()`, `executeUpdate()` và `execute()` xử lý kết quả theo hợp đồng JDBC và khả năng của driver.

Ngược lại, **API không hứa rằng** `prepareStatement()` sẽ lập tức gửi SQL đến server, tạo một tên statement trên DBMS, tái sử dụng một execution plan cố định hoặc giảm thời gian chạy trong mọi trường hợp.

Một driver có thể **trì hoãn công việc chuẩn bị** đến lần `execute()` đầu tiên. Vì vậy khi tìm nguyên nhân lỗi cú pháp hoặc lỗi kiểu dữ liệu, không được mặc định lỗi sẽ xuất hiện chính xác ở dòng gọi `prepareStatement()`.

## 3. Chuẩn bị phía driver: xử lý tham số ở phía client

Trong một số chế độ, driver xây dựng đối tượng prepared statement trong tiến trình ứng dụng. Khi thực thi, driver có thể:

1. Lưu câu SQL mẫu cùng các vị trí tham số.
2. Ghi nhận giá trị và kiểu do các lệnh `setXxx()` cung cấp.
3. Chuyển thành một yêu cầu phù hợp với giao thức DBMS. Với chế độ mô phỏng client-side, việc gửi có thể sử dụng câu SQL đã được driver mã hóa/escape giá trị theo quy tắc riêng của sản phẩm.
4. Nhận kết quả do server thực thi và cung cấp lại qua các đối tượng JDBC.

Ví dụ, một driver có thể sử dụng cách mô phỏng `PreparedStatement` bằng giao thức truy vấn SQL thông thường trong một cấu hình nhất định. Khi đó server có thể phải phân tích câu lệnh ở mỗi lần thực thi thay vì giữ một statement đã chuẩn bị giữa các lần gọi.

**Không đồng nhất mô phỏng chuẩn bị ở driver với việc nối chuỗi thủ công trong ứng dụng.** Đoạn code Java dùng `setString()` vẫn giao trách nhiệm biểu diễn dữ liệu cho driver theo hợp đồng JDBC; không biến đầu vào thành cú pháp SQL trong mã ứng dụng. Để được an toàn, driver phải hiện thực đúng việc mã hóa và truyền tham số. Ứng dụng vẫn phải dùng API có tham số và cập nhật driver khi có bản sửa lỗi.

### Điểm mạnh và giới hạn

| Điểm cần xét | Chế độ chuẩn bị phía driver |
| --- | --- |
| Chi phí tạo đối tượng JDBC | Có thể tương đối thấp, vì không nhất thiết cần trao đổi chuẩn bị với server ngay |
| Trạng thái prepared trên server | Có thể không có trạng thái tái sử dụng giữa các lần chạy |
| Tái sử dụng kế hoạch | Phụ thuộc khả năng cache/kế hoạch của server và cách gửi truy vấn; không mặc nhiên được giữ lại |
| Khả năng tương thích SQL | Driver có thể hỗ trợ những câu SQL không thể chuẩn bị server-side theo một giao thức/chế độ nhất định |
| Lưu lượng/protocol | Có thể gửi yêu cầu chứa phần câu lệnh SQL đã biểu diễn cho từng lần chạy |
| Lỗi cú pháp/kiểu | Có thể chỉ xuất hiện lúc `execute()` nếu driver chưa gửi câu SQL trước đó |

Không thể kết luận chế độ client-side luôn chậm: với truy vấn chỉ chạy một lần, tránh một số lượt trao đổi chuẩn bị hoặc chi phí quản lý trạng thái phía server đôi khi có lợi.

## 4. Chuẩn bị phía máy chủ: trạng thái gắn với phiên DBMS

Với chế độ **server-side preparation**, driver dùng khả năng của giao thức/DBMS để đăng ký một câu lệnh được chuẩn bị ở server. Tùy sản phẩm, server có thể giữ dạng cú pháp đã phân tích, thông tin kiểu tham số và/hoặc kế hoạch thực thi để dùng lại.

Một luồng điển hình:

```text
Lần dùng đầu:
Driver ---- prepare/parse câu SQL ----> DBMS
Driver <--- xác nhận hoặc mô tả ------ DBMS
Driver ---- bind + execute tham số ---> DBMS
Driver <--- kết quả ------------------- DBMS

Các lần sau trên cùng phiên/statement:
Driver ---- bind + execute tham số ---> DBMS
Driver <--- kết quả ------------------- DBMS

Khi kết thúc hoặc bị loại khỏi cache:
Driver ---- deallocate/close (nếu có) -> DBMS
```

Trong nhiều DBMS, trạng thái server-side prepared statement gắn với **một phiên kết nối vật lý**. Nó thường không được chia sẻ tự động giữa các connection độc lập. Vì vậy, chuẩn bị một câu SQL trên connection A không có nghĩa connection B đã có cùng statement được chuẩn bị.

### Vì sao cần cân nhắc?

- **Lợi ích tiềm năng:** giảm công việc lặp lại để phân tích cú pháp/chuẩn bị, giảm một số dữ liệu giao tiếp giữa client và server hoặc dùng lại thông tin prepared giữa nhiều lần execute.
- **Chi phí tiềm năng:** thao tác chuẩn bị ban đầu, bộ nhớ/trạng thái trên server, việc giữ nhiều câu SQL khác nhau, invalidation do thay đổi schema và quản lý vòng đời.
- **Phụ thuộc tối ưu hóa:** DBMS có thể chọn kế hoạch khác nhau theo tham số. Kế hoạch dùng chung có thể không tối ưu cho mọi giá trị; một số hệ quản trị tự lập kế hoạch lại khi cần.
- **Điều kiện tái sử dụng:** cần cùng câu SQL hợp lệ, driver và connection có trạng thái tương ứng, và prepared statement còn hiệu lực.

Do đó, lợi ích thường xuất hiện rõ hơn khi một mẫu SQL được thực thi **nhiều lần** trên các kết nối được tái sử dụng. Không có bảo đảm server-side luôn nhanh hơn.

## 5. Mã JDBC giống nhau, chế độ thực thi có thể khác

Ứng dụng không cần dùng hai loại API khác nhau cho hai chế độ. Ví dụ sau cố định một mẫu truy vấn và thay giá trị tham số:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;

public final class RepeatedQueryExample {
    private RepeatedQueryExample() {}

    public static long countMatchingOrders(
            Connection connection, List<Long> customerIds)
            throws SQLException {

        String sql =
                "SELECT COUNT(*) FROM orders " +
                "WHERE customer_id = ? AND status = ?";

        long total = 0;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            for (long customerId : customerIds) {
                statement.setLong(1, customerId);
                statement.setString(2, "ACTIVE");

                try (ResultSet result = statement.executeQuery()) {
                    if (result.next()) {
                        total = Math.addExact(total, result.getLong(1));
                    }
                }
            }
        }
        return total;
    }
}
```

Ví dụ giả định `orders` có `customer_id`, `status` và đã kiểm tra `customerIds` khác `null`, không có phần tử `null`. Lời gọi `Math.addExact()` có thể ném `ArithmeticException` nếu tổng vượt miền `long`. Nếu danh sách ID chứa giá trị trùng, kết quả của phương thức **cộng số đơn nhiều lần** theo danh sách đầu vào; tên hàm và cách sử dụng cần phù hợp nghiệp vụ.

Ở đây, **một `PreparedStatement` được tạo một lần rồi thực thi nhiều lần**. Đây là thói quen sử dụng tài nguyên hợp lý khi cùng một mẫu truy vấn được lặp lại. Nhưng **driver vẫn có quyền chọn** chuẩn bị ở phía client, ở phía server, hoặc chuyển đổi cơ chế theo cấu hình/số lần chạy.

Nếu gọi `connection.prepareStatement(sql)` mới trong mỗi vòng lặp, ứng dụng có thể làm giảm cơ hội tái sử dụng đối tượng JDBC và cache của driver. Dù vậy, việc tạo `PreparedStatement` mới không luôn đồng nghĩa driver mất hết cache: một số driver hoặc pool có thể giữ metadata/prepared statements theo cấu hình riêng.

## 6. PostgreSQL: extended protocol, unnamed và named prepared statement

**PostgreSQL** là ví dụ tốt để tránh hiểu nhầm rằng chỉ có hai chế độ tuyệt đối “prepare ở client” và “prepare ở server”.

Trong PostgreSQL extended query protocol, các bước **Parse**, **Bind**, **Execute** tách nhau về mặt giao thức. Driver có thể dùng một **unnamed statement** để gửi truy vấn có tham số: SQL được server parse/bind/execute, nhưng unnamed statement **không phải một prepared statement có tên được giữ ổn định qua nhiều lần thực thi** theo cùng nghĩa với named prepared statement.

PostgreSQL JDBC Driver (pgJDBC) có cơ chế chuyển sang dùng **named server-side prepared statement** cho các câu SQL được lặp lại khi đạt ngưỡng cấu hình. Thuộc tính thường gặp là `prepareThreshold`; giá trị và hành vi mặc định phải đối chiếu **đúng phiên bản driver**. Driver cũng có những cấu hình ảnh hưởng đường đi của protocol và khả năng cache.

| Trường hợp | Điều nên hiểu |
| --- | --- |
| Gọi `prepareStatement(sql)` lần đầu | Chỉ chắc chắn đã tạo đối tượng JDBC; chưa thể suy luận đã có named prepared statement ở server |
| Dùng extended protocol với unnamed statement | Server vẫn có thể thực hiện Parse/Bind/Execute; chưa nhất thiết tái sử dụng prepared statement có tên |
| Driver dùng named server-side prepared statement | Statement được quản lý trong phiên PostgreSQL; có cơ hội tái sử dụng giữa các lần execute |
| Driver hoặc kết nối không còn giữ statement | Có thể phải chuẩn bị lại khi dùng tiếp |

### SQL `PREPARE` của PostgreSQL khác lời gọi JDBC như thế nào?

PostgreSQL có lệnh SQL độc lập `PREPARE` và `EXECUTE`:

```sql
PREPARE count_active_orders(bigint) AS
SELECT COUNT(*)
FROM orders
WHERE customer_id = $1 AND status = 'ACTIVE';

EXECUTE count_active_orders(42);
EXECUTE count_active_orders(43);

DEALLOCATE count_active_orders;
```

Đây là **SQL do PostgreSQL hỗ trợ trong phiên hiện tại**; placeholder `$1` là cú pháp tham số của SQL `PREPARE` trên PostgreSQL. Nó **không phải** cú pháp dấu `?` của `PreparedStatement` trong Java:

```java
String sql =
        "SELECT COUNT(*) FROM orders WHERE customer_id = ? AND status = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 42L);
    statement.setString(2, "ACTIVE");
    try (ResultSet result = statement.executeQuery()) {
        // Doc COUNT(*).
    }
}
```

Vì vậy không cần tự viết `PREPARE ...` hoặc `EXECUTE ...` vào chuỗi SQL Java để dùng prepared statement chuẩn JDBC. Hãy để driver quyết định giao thức phù hợp với cấu hình và tính năng DBMS.

PostgreSQL có view `pg_prepared_statements` để quan sát **những prepared statement có tên của phiên hiện tại**, nhưng không nên dùng kết quả từ một connection khác để suy ra chính xác trạng thái của connection ứng dụng. Một unnamed statement hoặc một chế độ mô phỏng không nhất thiết xuất hiện theo cách bạn kỳ vọng trong view này.

## 7. MySQL Connector/J: client-side và server-side preparation

Với **MySQL Connector/J**, cách driver xử lý `PreparedStatement` có thể phụ thuộc các thuộc tính kết nối và phiên bản driver. Các tên thuộc tính thường gặp:

| Thuộc tính (minh họa) | Vai trò |
| --- | --- |
| `useServerPrepStmts` | Yêu cầu driver sử dụng server-side prepared statements khi khả dụng |
| `cachePrepStmts` | Cho phép cơ chế cache prepared statement của driver |
| `prepStmtCacheSize` | Giới hạn số lượng mục trong prepared-statement cache theo cơ chế driver |
| `prepStmtCacheSqlLimit` | Ngưỡng độ dài SQL mà driver cho phép đưa vào cache |

Ví dụ một JDBC URL *có thuộc tính dành cho Connector/J*:

```text
jdbc:mysql://localhost:3306/shop?useServerPrepStmts=true&cachePrepStmts=true
```

**Không sao chép chuỗi cấu hình trên cho PostgreSQL hoặc SQL Server**: các thuộc tính này là cách cấu hình driver MySQL. Hỗ trợ, giá trị mặc định và cách driver fallback khi SQL không thể chuẩn bị server-side có thể đổi theo phiên bản. Trong môi trường production, cần kiểm tra **tài liệu chính xác của phiên bản Connector/J** và xác minh hành vi thực tế.

Một số câu lệnh hoặc tính năng không được hỗ trợ bằng server-side prepare theo cách driver mong muốn có thể được driver xử lý theo đường đi khác. Việc viết `PreparedStatement` ở Java không giúp loại bỏ giới hạn cú pháp SQL/khả năng của server MySQL.

## 8. Chuẩn bị và cache nằm ở những đâu?

Từ “cache prepared statement” cũng có thể chỉ **nhiều cache khác nhau**:

| Cấp độ | Có thể giữ gì? | Phạm vi thường gặp |
| --- | --- | --- |
| **Đối tượng JDBC** | SQL và trạng thái tham số của một `PreparedStatement` Java | Vòng đời đối tượng statement |
| **Cache trong JDBC driver** | Thông tin câu SQL, metadata hoặc handle server-side prepared | Thường gắn với connection vật lý/driver; tùy cấu hình |
| **Cache của connection pool** (nếu có) | Tái sử dụng connection; một số pool/driver quản lý thêm statement cache | Phụ thuộc thư viện pool, không mặc định |
| **Trạng thái prepared trên DBMS** | Dạng câu lệnh đã chuẩn bị và thông tin server quản lý | Thường gắn với session/connection |
| **Plan cache của DBMS** | Thông tin về kế hoạch thực thi được lưu/tái sử dụng theo quy tắc DBMS | Phụ thuộc engine, tham số, schema, thống kê và chính sách cache |

**Connection pool không đồng nghĩa prepared-statement cache.** Pool có thể tái sử dụng cùng connection vật lý cho nhiều request, nhưng không phải mọi pool đều cache đối tượng `PreparedStatement`. Driver và DBMS có thể có cache riêng.

Ví dụ: ứng dụng nhận connection logic từ HikariCP, thực thi một `PreparedStatement` rồi đóng cả hai trong `try-with-resources`. Nếu connection được trả về pool, **connection vật lý có thể còn tồn tại**; trạng thái prepared ở driver/server cũng có thể được giữ nếu triển khai cho phép. Tuy nhiên, ứng dụng **không được giữ đối tượng statement đã đóng để dùng lại**.

### Trường hợp cache kém hiệu quả

Nếu mỗi request tạo một câu SQL khác nhau bằng cách ghép giá trị trực tiếp, số mẫu SQL tăng nhanh và khả năng tái sử dụng giảm:

```java
// Khong nen: moi ID tao ra mot SQL text khac nhau.
String badSql = "SELECT * FROM orders WHERE customer_id = " + customerId;

// Nen: cau truc SQL on dinh, tham so thay doi.
String goodSql = "SELECT * FROM orders WHERE customer_id = ?";
```

Tuy nhiên, số lượng mẫu SQL vẫn có thể thay đổi khi câu truy vấn có cấu trúc động hợp lệ như `IN (?, ?, ?)` với nhiều độ dài. Cần cân nhắc giới hạn cache và số lượng mẫu truy vấn thực tế; không cố gắng tối ưu bằng cách ghép dữ liệu vào SQL.

## 9. Server-side prepare có luôn nhanh hơn không?

**Không.** Hiệu năng phụ thuộc mẫu truy vấn, số lần gọi, chi phí round trip, kế hoạch thực thi, driver và DBMS.

| Tình huống | Cân nhắc thực tế |
| --- | --- |
| Một câu SQL chỉ thực thi một lần | Chi phí chuẩn bị phía server có thể lớn hơn lợi ích tái sử dụng |
| Cùng mẫu SQL chạy hàng nghìn lần trên một connection | Có thể có lợi từ cơ chế tái sử dụng parse/metadata/handle |
| Query chạy chậm chủ yếu vì đọc hàng triệu dòng | Tối ưu chỉ mục, lọc, phân trang và SQL thường quan trọng hơn prepare |
| Các giá trị tham số có phân bố rất khác nhau | Kế hoạch chung có thể không tốt cho mọi giá trị; tùy DBMS có tái tối ưu |
| Nhiều câu SQL động hiếm khi lặp lại | Cache có thể tốn bộ nhớ mà ít hit |
| Pool có nhiều connection vật lý | Cùng SQL có thể cần chuẩn bị riêng trên từng connection |
| Server có giới hạn số prepared statements | Cần chú ý đến ngưỡng và cơ chế đóng/loại khỏi cache |

**Không đánh đồng tái sử dụng kế hoạch với kết quả truy vấn.** Server-side prepared statement không biến kết quả `SELECT` cũ thành dữ liệu cache mặc định. Mỗi lần execute phải quan sát dữ liệu theo ngữ nghĩa giao dịch và mức cô lập của DBMS.

### Ví dụ về kế hoạch phụ thuộc tham số

Giả sử cột `status` trong bảng có 99% dòng `'ACTIVE'` và 1% dòng `'ARCHIVED'`:

```sql
SELECT id FROM orders WHERE status = ?;
```

Kế hoạch tốt cho `'ACTIVE'` có thể khác với `'ARCHIVED'` vì độ chọn lọc và chỉ mục. Một số DBMS lựa chọn giữa kế hoạch theo giá trị tham số và kế hoạch chung; vì thế **không được giả định server-side preparation luôn giữ một execution plan duy nhất**.

## 10. Cách kiểm tra thực tế: quan sát, đo và đối chiếu

Để đánh giá tác dụng của cấu hình prepare, thực hiện một phép đo có thể lặp lại:

1. **Cố định môi trường:** cùng phiên bản JDK, driver, DBMS, cùng schema/chỉ mục, dữ liệu và cấu hình pool.
2. **Xác định kịch bản:** truy vấn một lần, lặp trên một connection, lặp qua pool, tham số có độ chọn lọc khác nhau.
3. **Ghi cấu hình driver:** ví dụ `prepareThreshold` trong pgJDBC hoặc `useServerPrepStmts` trong MySQL Connector/J, cùng chế độ cache hiện tại.
4. **Làm nóng hệ thống hợp lý:** đo riêng giai đoạn kết nối/prepare ban đầu và giai đoạn thực thi lặp lại; tránh so sánh lần đầu chưa có cache với lần sau đã được làm nóng.
5. **Theo dõi thời gian và tài nguyên:** latency theo phân vị, throughput, CPU server, số round trip, số statement được chuẩn bị, cache hit/miss, connection đang hoạt động.
6. **Kiểm tra kế hoạch thực thi:** dùng công cụ `EXPLAIN`/thống kê do DBMS cung cấp cho các tham số đại diện; không chỉ nhìn thời gian chạy một lần.
7. **Đánh giá tính đúng:** đối chiếu số hàng, kiểu dữ liệu, lỗi, quyền, transaction và khả năng chạy với các giá trị biên.

Có thể dùng `System.nanoTime()` để lấy thời gian đo thô, nhưng các phép đo vi mô dễ bị ảnh hưởng bởi JIT, GC, connection, mạng và cache. Trong sản phẩm thực, nên kết hợp benchmark được kiểm soát với số liệu quan sát từ môi trường có tải tương tự production.

### Quan sát trạng thái DBMS

- **PostgreSQL:** view `pg_prepared_statements` có ích với prepared statements có tên **trong chính phiên kết nối đang truy vấn**; `EXPLAIN` và thống kê truy vấn giúp đánh giá kế hoạch/chi phí.
- **MySQL:** các bộ đếm lệnh prepared statement hoặc công cụ Performance Schema có thể hỗ trợ quan sát đường đi server prepare/execute; ý nghĩa từng chỉ số, phạm vi toàn cục và quyền truy cập cần được kiểm tra theo phiên bản.
- **Các DBMS khác:** dùng quan sát/kế hoạch thực thi đặc thù của sản phẩm; không suy đoán từ tên lớp `PreparedStatement` trong Java.

Lưu ý rằng một `DataSource` có pool có thể cấp cho thao tác đo một connection vật lý khác, làm sai kết luận “đã chuẩn bị ở lần trước”. Khi so sánh, cần biết rõ bạn đang dùng **cùng một connection**, hay nhiều connection trong pool.

## 11. Bảo mật: lựa chọn prepare phía nào có thay đổi nguyên tắc parameterization?

Không. Ở cấp độ mã ứng dụng, **cố định SQL và bind giá trị bằng `PreparedStatement.setXxx()` vẫn là nguyên tắc chính** để ngăn dữ liệu đầu vào trở thành cú pháp SQL.

```java
String sql = "SELECT id FROM accounts WHERE email = ? AND enabled = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, inputEmail);
    statement.setBoolean(2, true);
    try (ResultSet rows = statement.executeQuery()) {
        // Doc cac hang duoc phep.
    }
}
```

Mã này không tự nối `inputEmail` vào câu SQL. Driver chịu trách nhiệm truyền/biểu diễn tham số an toàn theo hợp đồng JDBC, dù chế độ hiện tại là client-side hay server-side.

**Server-side preparation không phải điều kiện duy nhất để dùng `PreparedStatement` an toàn.** Tuy nhiên, không vì thế mà chọn bất kỳ driver cũ hoặc tự mô phỏng việc escape chuỗi SQL: phải dùng driver được duy trì, cập nhật các bản sửa lỗi và kiểm tra dữ liệu/kiểu SQL.

Tham số hóa không thay thế các kiểm soát khác:

- Dấu `?` **không đại diện cho tên bảng/tên cột, từ khóa `ORDER BY` hoặc toàn bộ mệnh đề SQL**. Phần cấu trúc động cần ánh xạ từ danh sách cho phép.
- Giá trị truyền qua `LIKE ?` vẫn có thể chứa ký tự đại diện `%`/`_` theo ngữ nghĩa SQL; escape wildcard nếu bài toán muốn khớp ký tự nguyên văn.
- Tài khoản kết nối và người dùng vẫn cần phân quyền. Một truy vấn đúng tham số nhưng thiếu điều kiện bảo vệ tenant/tài khoản vẫn có thể đọc dữ liệu trái phép.
- Stored procedure xây dựng dynamic SQL không an toàn bên trong DBMS vẫn có thể có SQL injection, dù lời gọi ngoài dùng `CallableStatement`.

**Đừng bật/tắt server-side prepare với mục tiêu thay thế kiểm tra bảo mật.** Cấu hình prepare nên được chọn dựa trên tương thích và số đo hiệu năng; parameter binding phải được dùng đúng trong mọi chế độ.

## 12. Vòng đời `PreparedStatement` và tài nguyên phía server

`PreparedStatement` triển khai `AutoCloseable` qua `Statement`. Hãy dùng `try-with-resources` để đóng nó sau khi hoàn tất:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "UPDATE stock SET quantity = ? WHERE id = ?")) {

    statement.setInt(1, newQuantity);
    statement.setLong(2, stockId);
    int updated = statement.executeUpdate();
    if (updated != 1) {
        throw new SQLException("Khong tim thay dong can cap nhat");
    }
}
```

Ví dụ nằm trong một phương thức có biến `dataSource` (`javax.sql.DataSource`), `newQuantity` (`int`), `stockId` (`long`) và import các kiểu `java.sql` phù hợp.

Khi statement đóng, **đối tượng JDBC không còn được sử dụng tiếp**. Nhưng việc driver ngay lập tức gửi lệnh giải phóng prepared statement phía server hay giữ handle phục vụ cache là chi tiết triển khai. Không truy cập một statement sau `close()` chỉ vì cho rằng “server vẫn còn cache”.

Nếu một connection logic được trả về pool, kết nối vật lý có thể còn mở để tái sử dụng. Khi DBMS chấm dứt phiên vật lý, trạng thái prepared gắn với phiên đó thường cũng không còn. Các câu lệnh, driver cache và server resources cần được giới hạn hợp lý để tránh chiếm bộ nhớ quá mức.

Một số driver cung cấp `Statement.setPoolable(boolean)` theo API JDBC. Đây là **gợi ý cho driver về khả năng pooling của statement**, không phải lệnh bắt buộc biến mọi statement thành đối tượng được cache, cũng không thay thế `Connection` pooling.

## 13. Những hiểu nhầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`prepareStatement()` chắc chắn gửi `PREPARE` lên server ngay.” | Driver có thể xử lý ở client hoặc trì hoãn đến lần `execute()`. |
| “Dùng `PreparedStatement` nghĩa là đã tái sử dụng execution plan.” | Việc lưu/tái sử dụng kế hoạch phụ thuộc DBMS, driver, câu SQL và cấu hình. |
| “PostgreSQL Parse/Bind qua extended protocol luôn là named prepared statement.” | Unnamed statement cũng có thể được parse/bind, nhưng không có cùng vòng đời tái sử dụng như named statement. |
| “Client-side prepare đồng nghĩa ứng dụng phải nối chuỗi đầu vào vào SQL.” | Ứng dụng vẫn bind tham số; driver chịu trách nhiệm hiện thực an toàn. |
| “Server-side prepare luôn nhanh hơn.” | Chi phí ban đầu, số lần thực thi, plan, bộ nhớ/cache và DBMS quyết định. |
| “Tạo một `PreparedStatement` là đủ cho mọi connection.” | Statement gắn với connection tạo ra nó; không chia sẻ tùy tiện giữa các connection. |
| “Connection pool luôn cache prepared statement.” | Pool kết nối và cache statement là hai cơ chế khác nhau. |
| “Một prepared statement lưu lại dữ liệu truy vấn cũ.” | Trạng thái chuẩn bị SQL không đồng nghĩa cache kết quả trả về. |
| “Chỉ cần `setPoolable(true)` là bật server-side prepare.” | Đây là hint JDBC, driver có thể bỏ qua; chế độ server prepare cấu hình riêng. |
| “Mã SQL `PREPARE` trong PostgreSQL là cách phải dùng với JDBC.” | `PreparedStatement` dùng dấu `?`; driver có thể dùng protocol/server prepare mà ứng dụng không viết SQL `PREPARE`. |

## 14. Tự kiểm tra kiến thức

**Câu 1.** `connection.prepareStatement(sql)` trả về đối tượng thành công. Có thể kết luận server đã tạo một named prepared statement không?

*Gợi ý:* Không. Có thể driver chưa gửi SQL lên server, đang mô phỏng phía client hoặc sẽ dùng unnamed statement.

**Câu 2.** Cùng SQL được thực thi 1.000 lần trên một connection và chỉ 1 lần trên connection khác. Trường hợp nào thường đáng cân nhắc server-side preparation hơn?

*Gợi ý:* Trường hợp thực thi lặp nhiều lần có cơ hội bù chi phí chuẩn bị ban đầu, nhưng vẫn cần đo hiệu năng.

**Câu 3.** MySQL Connector/J dùng `useServerPrepStmts=false`. Có nhất thiết phải đổi mã Java từ `PreparedStatement` sang `Statement` không?

*Gợi ý:* Không. Driver có thể hiện thực `PreparedStatement` bằng cách chuẩn bị/mô phỏng phía client; mã dùng `setXxx()` vẫn giữ nguyên.

**Câu 4.** Tại sao prepared statement đã có trên connection A không mặc nhiên dùng được ở connection B?

*Gợi ý:* Trạng thái server-side prepared thường gắn với **phiên kết nối vật lý**; hai connection có trạng thái riêng.

**Câu 5.** Tại sao driver cache và server-side prepare không phải cùng một thứ?

*Gợi ý:* Cache của driver có thể giữ metadata hoặc handle ở client; server-side preparation giữ trạng thái prepared trong DBMS. Hai cơ chế có thể phối hợp nhưng có vòng đời, cấu hình khác nhau.

**Câu 6.** Truy vấn theo `status` có phân bố dữ liệu rất lệch. Vì sao một kế hoạch dùng lại không nhất thiết tốt cho mọi giá trị?

*Gợi ý:* Độ chọn lọc của các giá trị khác nhau có thể làm DBMS ưu tiên các chiến lược quét/chỉ mục khác nhau; một số DBMS chọn kế hoạch chung hoặc theo tham số.

**Câu 7.** Nếu ứng dụng dùng `PreparedStatement` và bind tất cả giá trị đúng cách, có cần bật server-side prepare riêng để việc truyền tham số “mới” được an toàn không?

*Gợi ý:* Không. Mấu chốt ở mã ứng dụng là tách cấu trúc SQL khỏi dữ liệu; driver phải hiện thực tham số hóa theo hợp đồng JDBC. Chế độ prepare là quyết định về giao thức, hiệu năng và tương thích.

## Ghi nhớ

**JDBC `PreparedStatement` là hợp đồng lập trình để thực thi SQL có tham số; “chuẩn bị ở driver” và “chuẩn bị ở server” là hai cách hiện thực hợp đồng đó.** Lời gọi `prepareStatement()` không bảo đảm server đã lập tức lưu câu SQL hay execution plan. Server-side prepared statement có thể giúp khi truy vấn lặp lại, nhưng đem theo chi phí và trạng thái theo connection; client-side preparation vẫn có thể phù hợp với một số truy vấn và cấu hình. Hãy dùng `setXxx()` để bind giá trị trong mọi trường hợp, đóng tài nguyên đúng vòng đời, kiểm tra thông tin/khả năng của driver và DBMS cụ thể, rồi đo hiệu năng trước khi chọn ngưỡng hoặc bật cơ chế cache.
