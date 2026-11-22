# Chỉ số tham số JDBC bắt đầu từ 1

Trong JDBC, khi một câu SQL có các dấu hỏi `?` dùng làm **parameter marker**, phương thức `PreparedStatement.setXxx(parameterIndex, value)` gán giá trị theo **chỉ số bắt đầu từ 1**, không phải 0. Dấu `?` đầu tiên là tham số số **1**, dấu `?` thứ hai là số **2**, và cứ thế tăng dần theo thứ tự xuất hiện trong câu SQL.

Quy tắc tưởng nhỏ này là nguyên nhân phổ biến của lỗi *off-by-one*: lập trình viên quen với mảng Java đánh chỉ số từ 0, rồi vô tình truyền 0 vào `setString(0, ...)` hoặc lệch một vị trí khi dùng nhiều điều kiện `WHERE`, `INSERT`, `UPDATE`. Với ứng dụng Spring Framework – data-access, bạn cần hiểu quy tắc này khi viết JDBC thuần, `PreparedStatementSetter`, các câu query động và khi đọc lỗi SQL.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Đếm đúng thứ tự các dấu `?` trong SQL và lập bảng ánh xạ *parameter index → cột/biểu thức → giá trị Java*.
2. Viết `setString(1, ...)`, `setLong(2, ...)`, `setNull(3, ...)` đúng vị trí trong `PreparedStatement`.
3. Phân biệt **chỉ số tham số JDBC (1-based)** với **index của array/List Java (0-based)**.
4. Nhận biết việc `ResultSet.getXxx(int columnIndex)` và `ParameterMetaData` cũng đánh chỉ số từ 1, nhưng dùng cho khái niệm khác.
5. Sửa các lỗi `SQLException` do parameter index = 0, index vượt số marker, thiếu binding hoặc bind sai thứ tự.
6. Áp dụng quy tắc với `SELECT`, `INSERT`, `UPDATE`, `CallableStatement`, `batch` và danh sách `IN (...)` động.
7. Hiểu khi nào Spring `JdbcTemplate` xử lý thứ tự bind thay bạn và khi nào code callback vẫn phải dùng 1-based.
8. Kiểm thử bằng một chương trình Java 17+ chạy độc lập và bằng integration test có database.

## 2. Vì sao JDBC dùng 1-based?

Xét câu SQL:

~~~sql
SELECT id, email
FROM account
WHERE status = ? AND created_at >= ? AND email = ?;
~~~

Đọc các **dấu `?` thực sự là parameter marker** theo thứ tự từ trái sang phải:

| Dấu marker | Chỉ số truyền cho JDBC | Biểu thức SQL nhận giá trị | Setter minh họa |
| --- | ---: | --- | --- |
| `?` thứ nhất | **1** | `status = ?` | `ps.setString(1, "ACTIVE")` |
| `?` thứ hai | **2** | `created_at >= ?` | `ps.setTimestamp(2, timestamp)` |
| `?` thứ ba | **3** | `email = ?` | `ps.setString(3, email)` |

Quy tắc trong API JDBC: **parameterIndex = 1 là tham số đầu tiên, 2 là tham số thứ hai, ...**. JDBC thiết kế các phương thức bind quanh một dãy vị trí tính từ 1; không được suy luận rằng vì Java array dùng index 0 thì API JDBC cũng vậy.

~~~text
Java List/array:     values[0]   values[1]   values[2]
                         |           |           |
SQL:                     ?           ?           ?
JDBC parameterIndex:     1           2           3
                         ^           ^           ^
                       setX(1)     setX(2)     setX(3)
~~~

Chỉ số này là **thứ tự marker trong SQL**, không phải thứ tự cột của bảng, tên cột, thứ tự bảng trong schema hay vị trí argument của một phương thức service. Nếu đổi thứ tự điều kiện trong SQL, cần xét lại thứ tự bind.

### Điều gì được tính là một marker?

Dấu `?` xuất hiện trong câu SQL được driver chấp nhận như **parameter marker** mới tạo vị trí bind. Dấu hỏi nằm trong **chuỗi literal** như `'?'` không phải một marker của `PreparedStatement`:

~~~sql
SELECT id
FROM ticket
WHERE text_value = '?' AND owner_id = ?;
~~~

Ở đây dấu hỏi trong `'?'` là văn bản so sánh; dấu hỏi sau `owner_id =` mới là marker **số 1**. Với SQL dialect có toán tử chứa dấu `?` (chẳng hạn một số toán tử JSON), cách parser/escaping tương tác với JDBC driver có thể khác; kiểm tra tài liệu driver thay vì đếm ký tự `?` bằng một biểu thức chuỗi đơn giản.

## 3. PreparedStatement: ví dụ đúng và sai

Mã ví dụ nằm trong method đã có một `java.sql.Connection connection`:

~~~java
String sql =
        "SELECT id, email FROM account WHERE status = ? AND email = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "ACTIVE");
    ps.setString(2, "an@example.test");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id") + " " +
                               rs.getString("email"));
        }
    }
}
~~~

Đây là đoạn **minh họa tích hợp**; cần JDBC imports, database, bảng `account` và kết nối thực để chạy. `try-with-resources` đóng `ResultSet` và `PreparedStatement`. Khi method sở hữu cả connection thì cũng cần release connection đúng vòng đời, thường bằng `try-with-resources` hoặc cơ chế Spring transaction.

**Sai chỉ số 0:**

~~~java
ps.setString(0, "ACTIVE"); // SAI: không có tham số JDBC số 0.
~~~

Đối với `PreparedStatement` chuẩn, index 0 không hợp lệ và driver thường ném `SQLException`. Chuỗi thông báo, kiểu con của exception và thời điểm kiểm tra có thể khác theo driver; không phụ thuộc vào một thông điệp lỗi cố định.

**Sai thứ tự dù index hợp lệ:**

~~~java
ps.setString(1, "an@example.test"); // SAI NGHĨA: marker 1 là status.
ps.setString(2, "ACTIVE");          // SAI NGHĨA: marker 2 là email.
~~~

Hai giá trị đều là `String`, nên driver có thể không báo lỗi cú pháp hay kiểu dữ liệu. Truy vấn vẫn chạy nhưng không tìm đúng kết quả. Đây là lỗi nguy hiểm hơn off-by-one dễ nhận thấy vì **không chắc có exception**.

**Index vượt số marker:**

~~~java
ps.setString(3, "EXTRA"); // SQL chỉ có 2 marker.
~~~

Một `PreparedStatement` cho SQL trên chỉ có index 1 và 2. Gán index 3 có thể gây `SQLException` vì không khớp parameter marker. Không nhầm với việc statement có thể trả rất nhiều **cột** hoặc **hàng**; số hàng/cột kết quả không quyết định số parameter markers.

**Quên bind một marker:**

~~~java
ps.setString(1, "ACTIVE");
ps.executeQuery(); // Marker số 2 chưa được gán trong lượt dùng này.
~~~

Với statement yêu cầu đầy đủ hai tham số, việc thiếu binding thường gây lỗi khi thực thi hoặc ở điểm driver kiểm tra tham số. Thông báo thường mô tả parameter chưa có giá trị; hành vi chi tiết phụ thuộc driver. Để tránh trạng thái binding cũ, lập trình rõ ràng và gán **mọi marker** trước mỗi lượt cần thực thi.

## 4. Ví dụ Java 17+ chạy độc lập, không cần database

JDK cung cấp `javax.sql.rowset.CachedRowSet`, một implementation của `RowSet` cho phép cấu hình SQL command và set các tham số positional. Ví dụ sau minh họa quy tắc **index 1, 2 hợp lệ; index 0 không hợp lệ** mà không cần kết nối tới database.

Lưu đúng file `RowSetParameterProbe.java`:

~~~java
import java.sql.SQLException;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;

public class RowSetParameterProbe {
    public static void main(String[] args) throws Exception {
        try (CachedRowSet rowSet =
                     RowSetProvider.newFactory().createCachedRowSet()) {
            rowSet.setCommand(
                    "SELECT * FROM account WHERE id = ? AND state = ?"
            );

            rowSet.setLong(1, 42L);
            rowSet.setString(2, "ACTIVE");
            System.out.println("bound parameters 1 and 2");

            try {
                rowSet.setLong(0, 99L);
                System.out.println("unexpected success for index zero");
            } catch (SQLException error) {
                System.out.println("index 0 rejected");
            }
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 RowSetParameterProbe.java
java RowSetParameterProbe
~~~

Stdout trong môi trường Java 17 được dùng để kiểm chứng:

~~~text
bound parameters 1 and 2
index 0 rejected
~~~

Phần `setCommand(...)` chỉ lưu câu lệnh cho rowset; ví dụ **không thực thi SQL** và không đòi hỏi bảng `account` thật. Nó chứng minh hành vi của implementation `CachedRowSet` trong JDK dùng để thực hành API set parameter, chứ không thay kiểm thử tích hợp với driver JDBC đang chạy ở dự án.

Không nên suy ra rằng mọi `SQLException` từ driver đều in cùng dòng `index 0 rejected`: đây là thông báo do chương trình `catch` và in ra cố định để bài học độc lập với thông điệp của driver.

## 5. Ví dụ JDBC thật với DataSource: ánh xạ rõ từng tham số

Giả sử schema minh họa:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    email VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL
);
~~~

Class `AccountDao.java` sau đây dùng **Java 17**, các interface JDBC/JDK, một `DataSource` được inject, và đọc theo vị trí parameter đúng 1-based.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class AccountDao {
    public record Account(long id, String email) {}

    private final DataSource dataSource;

    public AccountDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<Account> findByEmailAndActive(
            String email, boolean active) throws SQLException {
        String sql = """
                SELECT id, email
                FROM account
                WHERE email = ? AND active = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, email);       // WHERE email = ? thứ nhất
            ps.setBoolean(2, active);     // WHERE active = ? thứ hai

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Account(
                        rs.getLong("id"),
                        rs.getString("email")
                ));
            }
        }
    }
}
~~~

Class này **biên dịch với Java 17** nhưng không phải chương trình CLI độc lập vì chưa có `main`; chạy thực tế cần `DataSource`, driver và database/schema phù hợp. Nếu cột `email` không có unique constraint, truy vấn có thể trả nhiều hàng và method chỉ lấy hàng đầu; khi hợp đồng nghiệp vụ yêu cầu unique, bổ sung ràng buộc phù hợp hoặc kiểm tra `rs.next()` lần hai để từ chối kết quả sai cardinality.

Tại đây có hai khái niệm tách biệt:

- `ps.setString(1, email)`: **bind marker số 1** trong SQL.
- `rs.getLong("id")`: **đọc cột** trên hàng kết quả hiện tại; không liên quan tới index của parameter.

Việc method nhận hai argument Java theo thứ tự `email, active` không tự ràng buộc SQL. Chính hai lời gọi `setXxx(1, ...)` và `setXxx(2, ...)` ánh xạ chúng vào các vị trí query. Nếu sửa SQL thành `WHERE active = ? AND email = ?`, phải đổi code bind tương ứng:

~~~java
ps.setBoolean(1, active);
ps.setString(2, email);
~~~

**Mẹo đọc mã:** Trước mỗi khối bind phức tạp, viết bảng ngắn *marker 1 → email, marker 2 → active* hoặc giữ câu SQL và setter gần nhau. Tránh sao chép marker số 2 cho hai cột rồi quên marker số 1.

## 6. Phân biệt ba hệ chỉ số: Java, parameter và ResultSet

Ba nơi sau nhìn giống nhau nhưng mỗi nơi có quy tắc riêng:

| Cơ chế | Index bắt đầu ở | Điều được đánh index |
| --- | ---: | --- |
| Mảng Java `args[i]`, `List.get(i)` | **0** | Phần tử trong collection |
| `PreparedStatement.setXxx(parameterIndex, value)` | **1** | Dấu `?` trong SQL |
| `ResultSet.getXxx(columnIndex)` | **1** | Cột trong tập kết quả `SELECT` |
| `ResultSetMetaData.getColumnName(column)` | **1** | Cột trong metadata của tập kết quả |
| `ParameterMetaData.getParameterType(param)` | **1** | Marker parameter của statement |
| `CallableStatement.registerOutParameter(parameterIndex, ...)` | **1** | Vị trí parameter/return slot trong callable syntax |

Ví dụ câu SQL:

~~~sql
SELECT email, id
FROM account
WHERE id = ? AND active = ?;
~~~

Giả sử có:

~~~java
Object[] values = {42L, true}; // values[0] và values[1]
ps.setLong(1, (Long) values[0]);    // Marker 1: id
ps.setBoolean(2, (Boolean) values[1]); // Marker 2: active

try (ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        String email = rs.getString(1); // Cột 1 trong SELECT: email
        long id = rs.getLong(2);       // Cột 2 trong SELECT: id
    }
}
~~~

Nhìn vào `ps.setLong(1, ...)` và `rs.getString(1)`: **cùng số 1 nhưng trỏ đến hai đối tượng khác nhau** (parameter thứ nhất vs cột kết quả thứ nhất). Đừng dựa trên số thứ tự cột trong `CREATE TABLE` để giả định chỉ số của `ResultSet`; vị trí cột ResultSet do **SELECT list** quyết định. Dùng label/tên cột với `rs.getString("email")` thường đọc dễ hơn, đặc biệt khi query thay đổi thứ tự cột.

## 7. Khi lặp trên Java List, hãy dùng i + 1

Nếu có dãy giá trị trong array/List Java, loop bắt đầu `i = 0` để lấy phần tử đầu. Tuy nhiên JDBC cần parameter đầu tiên mang chỉ số 1:

~~~java
List<Long> ids = List.of(10L, 20L, 30L);
for (int i = 0; i < ids.size(); i++) {
    ps.setLong(i + 1, ids.get(i));
}
~~~

Bảng quy đổi:

| `i` của Java | `ids.get(i)` | JDBC `parameterIndex = i+1` |
| ---: | ---: | ---: |
| 0 | 10 | 1 |
| 1 | 20 | 2 |
| 2 | 30 | 3 |

Loop này chỉ đúng nếu SQL thực sự có đúng ba marker và cả ba marker nhận lần lượt ID theo thứ tự đó. Nó không tự thêm dấu `?` cho câu SQL. Phải chuẩn bị câu SQL có đúng số marker tương ứng:

~~~sql
SELECT id, email FROM account WHERE id IN (?, ?, ?);
~~~

### Danh sách IN có số lượng thay đổi

JDBC positional parameter không có nghĩa mọi driver sẽ tự “bung” một `List` thành nhiều marker khi bạn viết `IN (?)`. Với plain JDBC, cách portable dễ hiểu là tạo chính xác một dấu hỏi trên mỗi giá trị rồi bind theo chỉ số `i+1`:

~~~java
import java.util.Collections;
import java.util.List;

List<Long> ids = List.of(10L, 20L, 30L);
String markers = String.join(
        ", ", Collections.nCopies(ids.size(), "?")
);
String sql = "SELECT id, email FROM account WHERE id IN (" + markers + ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setLong(i + 1, ids.get(i));
    }
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc các hàng kết quả.
        }
    }
}
~~~

Kết quả `sql` có ba marker `IN (?, ?, ?)`; giá trị không bao giờ được nối trực tiếp vào SQL. Đây là đoạn tích hợp, cần `Connection connection` và JDBC imports phù hợp.

**Trường hợp danh sách rỗng:** `nCopies(0, "?")` tạo chuỗi rỗng, dẫn tới `IN ()`, không portable và có thể sai cú pháp SQL. Nên quyết định rõ nghiệp vụ: nếu đầu vào rỗng, trả danh sách kết quả rỗng trước khi chạy query, hoặc xây câu SQL có điều kiện luôn false theo dialect. Không chạy câu SQL với `IN ()` mà không kiểm soát.

### Khi có marker đứng trước dãy IN

Giả sử SQL:

~~~sql
SELECT id
FROM account
WHERE active = ?
  AND id IN (?, ?, ?);
~~~

Marker 1 dành cho `active`; các ID phải bắt đầu từ marker **2**, không phải 1:

~~~java
ps.setBoolean(1, true);
for (int i = 0; i < ids.size(); i++) {
    ps.setLong(i + 2, ids.get(i));
}
~~~

Đây là quy tắc tổng quát: nếu có `offset` marker đã dùng trước danh sách, index JDBC tại phần tử Java thứ `i` là `offset + i + 1`. Tránh hardcode offset nếu câu SQL có thể được xây từ nhiều thành phần; lúc đó cần một chiến lược quản lý binding rõ ràng hoặc dùng thư viện hỗ trợ named parameters.

## 8. INSERT: thứ tự marker trong VALUES

Giả sử bảng:

~~~sql
INSERT INTO account (id, email, active)
VALUES (?, ?, ?);
~~~

Cách bind:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO account (id, email, active) VALUES (?, ?, ?)")) {
    ps.setLong(1, 101L);
    ps.setString(2, "an@example.test");
    ps.setBoolean(3, true);
    int rows = ps.executeUpdate();
}
~~~

Thứ tự marker theo phần `VALUES` khớp với cột `id, email, active` đã chỉ định. Nếu đổi thứ tự cột:

~~~sql
INSERT INTO account (email, active, id)
VALUES (?, ?, ?);
~~~

thì marker 1 nay là email, marker 2 là active, marker 3 là id. Các setter cũng phải thay đổi đúng:

~~~java
ps.setString(1, "an@example.test");
ps.setBoolean(2, true);
ps.setLong(3, 101L);
~~~

**Không có quy tắc** “parameter số 1 luôn là khóa chính” hay “parameter index trùng thứ tự cột schema”. Các con số chỉ biểu diễn vị trí marker của **câu statement đang được prepare**.

## 9. UPDATE: marker ở SET xuất hiện trước marker ở WHERE

Một nguồn lỗi điển hình là ưu tiên bind ID trước vì ID là khóa, nhưng SQL lại có marker cho dữ liệu cần cập nhật nằm trước:

~~~sql
UPDATE account
SET email = ?, active = ?
WHERE id = ?;
~~~

Thứ tự chính xác:

~~~java
ps.setString(1, "new@example.test"); // email ở SET
ps.setBoolean(2, true);             // active ở SET
ps.setLong(3, 101L);                // id ở WHERE
int count = ps.executeUpdate();
~~~

**Sai ngữ nghĩa** khi bind `id` vào index 1 vì nhớ đó là định danh của account, rồi tiếp tục bind email/active vào 2/3. Khi có thể ép kiểu, driver có thể thực thi câu SQL với giá trị sai mà không báo lỗi tức thời; khi không thể ép kiểu, có thể thấy SQLException về type mismatch.

Nếu một câu SQL dùng cùng một giá trị ở hai vị trí, hai dấu `?` vẫn là **hai marker riêng biệt**:

~~~sql
SELECT id FROM account WHERE email = ? OR recovery_email = ?;
~~~

Dù cả hai đều nhận cùng email, phải bind hai lần:

~~~java
ps.setString(1, email);
ps.setString(2, email);
~~~

JDBC positional parameter không tự gắn danh tính/biến cho hai marker vì chúng trông cùng ý nghĩa.

## 10. SQL NULL và các phương thức setter

Chỉ số vẫn bắt đầu từ 1 khi giá trị truyền vào là NULL. Với cột `nickname VARCHAR NULL`:

~~~sql
UPDATE account_profile
SET nickname = ?
WHERE account_id = ?;
~~~

Code Java:

~~~java
if (nickname == null) {
    ps.setNull(1, java.sql.Types.VARCHAR);
} else {
    ps.setString(1, nickname);
}
ps.setLong(2, accountId);
~~~

`setNull(1, Types.VARCHAR)` gán SQL NULL ở **marker 1**, chỉ rõ kiểu SQL mong đợi. `setString(1, null)` có thể được nhiều driver xử lý, nhưng với SQL NULL typed, `setNull` làm ý định và kiểu dữ liệu rõ hơn, đặc biệt trong các truy vấn/driver nhạy về suy luận kiểu.

Một lựa chọn khác là `setObject(1, null, Types.VARCHAR)` theo overload có `targetSqlType`, nếu driver hỗ trợ kiểu tương ứng. Tránh dựa vào `setObject(1, null)` khi driver không đủ thông tin suy luận kiểu để xử lý nhất quán.

**NULL không phải “không bind gì”.** Nếu cột nullable và muốn truyền SQL NULL, vẫn phải gọi một setter cho vị trí đó. Bỏ qua setter không đồng nghĩa với truyền NULL; nó có thể dẫn tới lỗi chưa có giá trị parameter, hoặc tệ hơn tái sử dụng binding cũ nếu statement được dùng lại.

### Phân biệt setter, getter và wasNull

Ở chiều **ghi/bind**: `ps.setNull(1, Types.VARCHAR)` chỉ định tham số số 1 là SQL NULL.

Ở chiều **đọc kết quả**: `rs.getString(1)` đọc cột kết quả số 1 và trả Java `null` nếu nó là SQL NULL. Với getter primitive như `rs.getInt(1)`, cần `rs.wasNull()` để phân biệt 0 với SQL NULL. Quy tắc 1-based xuất hiện ở cả setter và getter, nhưng ngữ nghĩa khác nhau.

## 11. Một PreparedStatement có thể được dùng nhiều lần

Khi reuse một `PreparedStatement` cho nhiều giá trị, **các marker giữ nguyên chỉ số** của SQL đã prepare. Lần thực thi tiếp theo có thể thay đổi giá trị, chứ không tạo ra marker 0 hay tự tăng marker 1 thành 3.

Ví dụ update theo từng ID:

~~~java
String sql = "UPDATE account SET active = ? WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (long id : List.of(10L, 20L, 30L)) {
        ps.setBoolean(1, false);
        ps.setLong(2, id);
        ps.executeUpdate();
    }
}
~~~

Mỗi vòng đều bind **1 → active**, **2 → id**. Không viết `setLong(i + 2, id)` với biến đếm vòng lặp; đó là nhầm vị trí parameter với số thứ tự iteration.

### clearParameters và binding cũ

`ps.clearParameters()` xóa các giá trị parameter đang được gán trên statement nhưng **không đổi số marker hay chỉ số**. Nếu muốn đổi tập tham số và tránh dữ liệu cũ còn lưu, có thể gọi `clearParameters()` trước lượt bind mới, rồi gán đủ mọi marker. Tùy nhu cầu, code đơn giản nhất là luôn gán lại tất cả marker ở mỗi lượt.

~~~java
ps.clearParameters();
ps.setBoolean(1, true);
ps.setLong(2, 20L);
ps.executeUpdate();
~~~

Đừng gọi `clearParameters()` sau khi bind đủ rồi trước lúc thực thi: nó có thể khiến các giá trị bị xóa. Cần nhớ một statement được chuẩn bị cho SQL cụ thể; nếu muốn thay số marker hoặc cấu trúc SQL, phải tạo statement phù hợp.

### executeBatch: index reset về vị trí, không phải thành số batch

Một `PreparedStatement` có thể thực thi nhiều bộ tham số với `addBatch()`:

~~~java
String sql = "UPDATE account SET active = ? WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (long id : List.of(10L, 20L, 30L)) {
        ps.setBoolean(1, true);
        ps.setLong(2, id);
        ps.addBatch();
    }
    int[] affected = ps.executeBatch();
}
~~~

Mỗi lần `addBatch()` thêm một bộ giá trị cho cùng **hai marker**. Các chỉ số vẫn là 1 và 2 trong mọi batch item. Kết quả `executeBatch()` có thể chứa update counts hoặc mã đặc biệt theo JDBC cho từng command; không suy luận rằng mọi phần tử bắt buộc là số hàng dương.

## 12. CallableStatement: tham số IN, OUT và return position

`CallableStatement` mở rộng `PreparedStatement` để gọi stored procedures/functions. Các tham số theo **vị trí** cũng bắt đầu từ 1:

~~~java
try (CallableStatement call =
        connection.prepareCall("{call update_balance(?, ?)}")) {
    call.setLong(1, accountId);
    call.setBigDecimal(2, delta);
    call.execute();
}
~~~

Nếu stored procedure có hai positional IN parameters, `accountId` là index 1 và `delta` là index 2. Trình điều khiển có thể hỗ trợ binding theo tên tham số trong một số trường hợp, nhưng không nên xem các overload có tên là portable trên mọi database.

### Function return nằm ở vị trí số 1 trong JDBC escape syntax

Một số JDBC driver hỗ trợ dạng function call:

~~~sql
{? = call calculate_points(?)}
~~~

Trong cú pháp này, **marker đầu tiên biểu diễn kết quả trả về** của function, còn argument đầu tiên là marker số **2**. Mẫu code:

~~~java
try (CallableStatement call =
        connection.prepareCall("{? = call calculate_points(?)}")) {
    call.registerOutParameter(1, java.sql.Types.INTEGER);
    call.setLong(2, accountId);
    call.execute();
    int points = call.getInt(1);
}
~~~

Đây là **mẫu minh họa**: cú pháp, đăng ký type, giá trị trả và việc hỗ trợ stored function phụ thuộc database/driver cụ thể. Nhưng nguyên tắc positional index của JDBC vẫn đúng: không có tham số số 0. Không gán `accountId` vào marker 1 trong cú pháp `{? = call ...}`, vì vị trí đó đã dành cho function return.

## 13. ParameterMetaData: kiểm tra số marker và kiểu tham số

JDBC cung cấp `ParameterMetaData` để tìm thông tin về các parameter marker:

~~~java
ParameterMetaData metadata = ps.getParameterMetaData();
int parameterCount = metadata.getParameterCount();
System.out.println("parameterCount=" + parameterCount);
~~~

Với SQL `WHERE email = ? AND active = ?`, số marker mong đợi là **2**. Các API metadata dùng index từ 1 khi truy vấn **thông tin của một parameter**:

~~~java
int typeFirst = metadata.getParameterType(1);
int typeSecond = metadata.getParameterType(2);
~~~

Tuy nhiên, **mức độ hỗ trợ parameter metadata không đồng đều giữa driver**, nhất là khi server chưa chuẩn bị statement thật, SQL chứa kiểu khó suy luận hoặc stored procedure phức tạp. Một số driver có thể ném `SQLFeatureNotSupportedException` hoặc trả thông tin không đủ. Vì vậy:

- `getParameterCount()` hữu ích khi driver hỗ trợ, nhưng không thay kiểm thử SQL.
- Không yêu cầu metadata hoạt động đầy đủ để bind một câu SQL đơn giản.
- Không dùng `getParameterType(0)` vì metadata parameter index cũng 1-based.
- Không nhầm `ParameterMetaData` với `ResultSetMetaData`, vốn nói về **cột kết quả** và cũng dùng index 1-based.

## 14. Spring JdbcTemplate: khi nào vẫn cần tự dùng 1-based?

Spring JDBC cung cấp API tiện lợi giảm việc lặp mã `Connection`, `PreparedStatement` và `ResultSet`. Nhưng có hai nhóm tình huống rất khác nhau:

### 14.1. Các overload nhận argument theo thứ tự

Trong ứng dụng đã có `JdbcTemplate jdbc`:

~~~java
List<Long> ids = jdbc.query(
        "SELECT id FROM account WHERE active = ? AND email = ?",
        (rs, rowNum) -> rs.getLong("id"),
        true,
        "an@example.test"
);
~~~

Đây là ví dụ **Spring JDBC tích hợp**; cần bean `JdbcTemplate`, DataSource và schema. Bạn đưa các argument Java `true` rồi `"an@example.test"` theo thứ tự marker trong SQL. Spring thực hiện công việc bind vào JDBC, nên **caller không tự gọi `setBoolean(1, ...)`**.

Về mặt Java, khi xử lý varargs hay một mảng argument, phần tử `args[0]` vẫn là phần tử đầu của array. Điều này không mâu thuẫn với JDBC 1-based: **Spring chuyển vị trí argument Java sang vị trí marker JDBC** ở tầng binding của nó.

Không xem cách dùng `RowMapper` này là minh họa cho việc chỉ số cột trả về: `rs.getLong("id")` đọc theo label. `rowNum` trong callback là **chỉ số hàng do Spring cung cấp** và bắt đầu từ 0 theo hợp đồng `RowMapper.mapRow(rs, rowNum)`, không phải parameterIndex JDBC. Đó là một bẫy index khác cần phân biệt.

### 14.2. PreparedStatementSetter callback: code của bạn gọi JDBC trực tiếp

Khi dùng `PreparedStatementSetter`, callback nhận chính `PreparedStatement`. Bạn phải tuân thủ quy tắc 1-based:

~~~java
List<Long> ids = jdbc.query(
        "SELECT id FROM account WHERE active = ? AND email = ?",
        ps -> {
            ps.setBoolean(1, true);
            ps.setString(2, "an@example.test");
        },
        (rs, rowNum) -> rs.getLong("id")
);
~~~

Đoạn này dùng overload `JdbcTemplate.query(String sql, PreparedStatementSetter pss, RowMapper<T> rowMapper)` khi thư viện Spring JDBC phù hợp; nó là ví dụ tích hợp, không phải chương trình độc lập. Callback không được dùng `ps.setBoolean(0, ...)` chỉ vì `rowNum` bắt đầu từ 0.

Nếu vừa dùng `JdbcTemplate` có varargs vừa dùng callback `PreparedStatementSetter`, phải chọn **một cơ chế binding** phù hợp với overload đang gọi; không tự bind lại tùy tiện ở nhiều chỗ.

### 14.3. NamedParameterJdbcTemplate loại bỏ việc đếm marker trong code gọi

Khi SQL nhiều tham số hoặc thứ tự dễ nhầm, có thể dùng `NamedParameterJdbcTemplate`:

~~~java
String sql = """
        SELECT id FROM account
        WHERE email = :email AND active = :active
        """;

var params = new org.springframework.jdbc.core.namedparam
        .MapSqlParameterSource()
        .addValue("email", "an@example.test")
        .addValue("active", true);

List<Long> ids = namedJdbc.query(
        sql, params, (rs, rowNum) -> rs.getLong("id")
);
~~~

Ở đây `namedJdbc` là bean `NamedParameterJdbcTemplate`. Đoạn minh họa dùng **tên** `:email` và `:active` thay vì viết con số 1, 2 tại call site. Spring phân tích SQL và ánh xạ tên thành các vị trí JDBC phù hợp khi thực thi. **Không có nghĩa PreparedStatement chuyển thành 0-based**; sự chuyển đổi được framework xử lý.

Tên một parameter có thể xuất hiện nhiều lần trong SQL; framework có thể bind cùng giá trị vào nhiều vị trí. Với `IN (:ids)`, `NamedParameterJdbcTemplate` có khả năng mở rộng danh sách thành nhiều placeholder theo cơ chế thư viện, tiện hơn plain JDBC tự nối marker. Vẫn cần xử lý danh sách rỗng theo quy tắc nghiệp vụ và SQL dialect; không coi mọi SQL shape đều được hỗ trợ tự động.

## 15. Parameter marker chỉ bind **giá trị**, không bind tên bảng/cột

Cách dùng đúng:

~~~sql
SELECT id FROM account WHERE email = ?;
~~~

Dấu `?` đại diện cho một **giá trị** truyền từ Java, không phải một đoạn mã SQL bất kỳ.

Ví dụ sai ý định:

~~~sql
SELECT ? FROM account WHERE id = ?;
~~~

Nếu muốn truyền **tên cột** vào dấu hỏi đầu tiên, statement không tự biến nó thành identifier. Driver sẽ coi parameter đó là một giá trị biểu thức nếu cú pháp SQL cho phép, dẫn đến kết quả không như mong đợi. Tương tự, dùng `FROM ?` để gán tên bảng thường không hợp lệ.

Nếu người dùng được chọn cột sort hoặc tên trường, hãy kiểm tra lựa chọn bằng **allowlist các identifier cố định** rồi tạo SQL có kiểm soát; các giá trị như email/id vẫn phải bind bằng `?`. Đừng ghép trực tiếp input vào SQL chỉ để né index. PreparedStatement đúng cách giúp tách giá trị khỏi câu lệnh và giảm rủi ro SQL injection.

## 16. Lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `SQLException` nêu `parameter index 0` không hợp lệ | Java index 0 truyền thẳng vào JDBC | Dùng 1 cho marker đầu; trong loop chuyển `i + 1` |
| Driver báo parameter index vượt phạm vi | SQL có ít dấu marker hơn số được bind | Đếm marker thật; soát SQL đã prepare, có literal `'?'` không |
| Báo parameter chưa được gán khi `execute` | Thiếu một lời gọi setter / đã `clearParameters()` | Bind đủ mọi marker trước lượt execute |
| Query chạy nhưng sai dữ liệu | Hai giá trị khác marker order, nhưng type vẫn phù hợp | Lập bảng marker → expression → setter, kiểm tra SQL |
| Update tác động 0 hàng | `WHERE` nhận sai giá trị hoặc không có bản ghi | Log SQL template và argument được mask; kiểm tra thứ tự |
| Conversion/type mismatch | Marker được bind bằng sai setter/kiểu | Đối chiếu kiểu SQL mục tiêu và giá trị Java |
| `CallableStatement` trả sai vị trí | Function return slot và IN args bị nhầm | Với `{? = call ...}`, return ở 1, IN đầu ở 2 |
| Dynamic `IN (...)` có index không đúng | Lặp Java index 0 hoặc quên offset trước list | Dùng `offset + i + 1`, bảo đảm số marker |
| `ParameterMetaData` không hỗ trợ | Driver thiếu khả năng introspection | Đọc thông báo driver; không coi đó là lỗi index |
| Spring query overload không khớp | Nhầm callback setter, mapper và varargs | Chọn overload có chữ ký đúng; thử compile code tích hợp |

**Đọc stack trace đúng tầng:** Với `PreparedStatement.setXxx`, lỗi index thường xuất hiện tại đoạn bind. Nhưng JDBC driver cũng có thể trì hoãn kiểm tra cho tới `executeQuery()`/`executeUpdate()`. Cần xem thông điệp và root cause cụ thể, không cố đoán rằng lỗi luôn nổ ngay ở dòng setter.

### Đừng nhầm tham số SQL với cột ResultSet

SQL:

~~~sql
SELECT email, id
FROM account
WHERE active = ? AND id = ?;
~~~

Parameter 1 và 2 thuộc `active`/`id`; ResultSet column 1 và 2 thuộc `email`/`id`. Khi có lỗi kiểu `Invalid column index: 0` lúc gọi `rs.getString(0)`, đây là **lỗi chỉ số cột của ResultSet**, không phải lỗi binding `PreparedStatement`.

### Quan sát parameter values an toàn

Khi debug, có thể log số marker, tên trường nghiệp vụ và loại giá trị được bind (ví dụ `marker 1=status, marker 2=email`). Tránh log mật khẩu, access token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Một số driver/framework hỗ trợ SQL logs kèm bind values; bật theo chính sách bảo mật, dùng môi trường test và masking cần thiết.

## 17. Phương pháp thực hành sửa lỗi off-by-one

Giả sử một hàm cần query:

~~~sql
SELECT id FROM transaction_record
WHERE account_id = ?
  AND amount >= ?
  AND created_at < ?;
~~~

Hãy làm theo trình tự:

1. Viết SQL hoàn chỉnh và đánh số marker từ trái qua phải: **1 = account_id, 2 = amount, 3 = created_at**.
2. Chọn setter khớp loại dữ liệu: `setLong(1, accountId)`, `setBigDecimal(2, minAmount)`, `setTimestamp(3, cutoff)`.
3. Bảo đảm không có marker nào bị bỏ qua hay gán lặp ngoài chủ đích.
4. Nếu tham số đến từ `List`/array, kiểm tra cẩn thận phép cộng 1 và offset.
5. Chạy test có dữ liệu đầu vào khác biệt rõ rệt để phát hiện trường hợp bind đảo thứ tự mà không phát sinh SQLException.

Code mẫu:

~~~java
String sql = """
        SELECT id FROM transaction_record
        WHERE account_id = ?
          AND amount >= ?
          AND created_at < ?
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, accountId);
    ps.setBigDecimal(2, minimumAmount);
    ps.setTimestamp(3, cutoff);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long transactionId = rs.getLong(1);
            // Xử lý transactionId.
        }
    }
}
~~~

Trong ứng dụng Spring, nếu việc đếm marker thủ công trở nên phức tạp, cân nhắc `NamedParameterJdbcTemplate` cho query cần nhiều tham số có tên. Khi phải viết callback `PreparedStatementSetter`, vẫn giữ quy tắc **index đầu tiên bằng 1**.

## 18. Kiểm thử đúng và sai

Một bộ test nên có cả **mã lỗi dễ thấy** lẫn **mã lỗi âm thầm**:

| Test | Cách thực hiện | Kết quả cần xác minh |
| --- | --- | --- |
| Index 1 hợp lệ | `setLong(1, 42L)` khi SQL có marker | Bind thành công |
| Index 0 không hợp lệ | `setLong(0, 42L)` | SQLException hoặc hành vi reject đúng JDBC |
| Index quá lớn | `setLong(3, 42L)` với SQL chỉ 2 markers | Driver reject, không thể bind marker không tồn tại |
| Thiếu binding | SQL có 2 markers nhưng chỉ gán 1 | Driver không thực thi hợp lệ với parameter còn thiếu |
| Đảo thứ tự type tương thích | Hai `String` gán sai marker | Test nghiệp vụ bắt kết quả sai, không chỉ assert “không exception” |
| SQL `UPDATE` có `SET` trước `WHERE` | Bind data ở 1/2, id ở 3 | Update đúng record, count đúng kỳ vọng |
| List 3 phần tử | Loop Java `i = 0..2`, bind `i + 1` | Index 1,2,3 nhận đúng phần tử |
| List có marker offset | Marker `active` ở 1, list bắt đầu 2 | Không ghi đè parameter 1 |
| Callable function | Return marker ở 1, IN argument ở 2 | Đăng ký và bind đúng vị trí |
| Spring callback | `PreparedStatementSetter` dùng 1-based | Compile và chạy query đúng |
| Spring varargs | `jdbc.query(..., true, email)` | Argument map đúng thứ tự marker |

Kiểm thử production-like cần driver/database thật, vì `CachedRowSet` độc lập ở phần 4 không chứng minh mọi behavior của driver. Với `INSERT/UPDATE`, nên chạy test trong transaction rồi rollback khi thích hợp để không làm bẩn dữ liệu. Với database/driver cụ thể, assert loại exception ổn định theo contract của thư viện đang dùng, không phụ thuộc nguyên văn thông báo có thể đổi qua phiên bản.

## 19. Bài tập tự kiểm tra

**Câu 1.** SQL `SELECT * FROM product WHERE category = ? AND price >= ?` có mấy marker, và marker đầu có chỉ số gì?  
**Đáp án:** Hai marker; marker đầu có chỉ số **1**, marker hai có chỉ số **2**.

**Câu 2.** Tại sao `ps.setString(0, "BOOK")` sai dù `String[] filters` có phần tử đầu ở index 0?  
**Đáp án:** Java array/List đánh chỉ số từ 0, nhưng `PreparedStatement` đánh index parameter từ 1; phải dùng `ps.setString(1, filters[0])`.

**Câu 3.** Với `UPDATE product SET name = ? WHERE id = ?`, marker số 1 có phải id không?  
**Đáp án:** Không. Marker 1 là `name` ở `SET`; marker 2 mới là `id` ở `WHERE`.

**Câu 4.** Nếu `List<Long> ids` có ba phần tử và SQL `IN (?, ?, ?)`, loop `i=0..2` bind tại index nào?  
**Đáp án:** `i + 1` → 1, 2, 3.

**Câu 5.** SQL `WHERE active = ? AND id IN (?, ?)`: hai ID bind ở đâu?  
**Đáp án:** `active` ở 1; ID thứ nhất ở 2, ID thứ hai ở 3.

**Câu 6.** Hai câu `ps.setString(1, email)` và `rs.getString(1)` có cùng ý nghĩa không?  
**Đáp án:** Không. Câu đầu bind marker 1; câu sau đọc cột kết quả 1 trên hàng hiện tại.

**Câu 7.** SQL `WHERE message = '?' AND id = ?` có bao nhiêu marker?  
**Đáp án:** Một marker bind ở `id = ?`; `'?'` là chuỗi literal, không phải marker.

**Câu 8.** `{? = call calculate_points(?)}` nhận accountId ở parameter 1 hay 2?  
**Đáp án:** 2. Marker 1 dành cho function return.

**Câu 9.** Nếu `jdbc.queryForObject(sql, Long.class, email, true)` đang được dùng, có cần gọi `setString(1, email)` nữa ở service không?  
**Đáp án:** Không; overload convenience của Spring thực hiện binding từ các argument theo thứ tự. Khi dùng callback `PreparedStatementSetter` thì code callback mới gọi setter 1-based.

**Câu 10.** Gặp exception “parameter chưa có giá trị”, có nên gán `setNull(0, Types.VARCHAR)` để “bổ sung” không?  
**Đáp án:** Không. Tìm marker nào chưa được gán trong dãy **1..N**; nếu muốn SQL NULL ở marker đó, dùng `setNull(indexHợpLệ, sqlType)`.

## 20. Kết luận

Ghi nhớ câu duy nhất: **JDBC positional parameter bắt đầu từ 1; Java array/List bắt đầu từ 0.** Dấu `?` thứ nhất được bind bằng `setXxx(1, ...)`, dấu thứ hai bằng `setXxx(2, ...)`, bất kể thứ tự cột, khóa chính hay tên biến Java. Khi lặp qua collection, dùng `i + 1` (cộng offset nếu có marker đứng trước). Khi làm việc qua Spring callback `PreparedStatementSetter`, quy tắc vẫn giữ nguyên; còn overload `JdbcTemplate` nhận argument hoặc `NamedParameterJdbcTemplate` sẽ đảm nhận ánh xạ vị trí cho bạn.

Các lỗi index 0 hoặc vượt số marker thường dễ phát hiện. **Lỗi bind đảo thứ tự** mới đáng chú ý vì code có thể chạy không exception nhưng trả kết quả sai; vì thế cần lập bảng marker → giá trị, đọc SQL từ trái qua phải và kiểm thử dữ liệu có tính phân biệt.

### Tài liệu tham khảo

- [Oracle Java SE 17 — PreparedStatement API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): các phương thức `setString`, `setInt`, `setNull`, binding parameter và `execute`.
- [Oracle Java SE 17 — ParameterMetaData API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ParameterMetaData.html): số parameter và truy vấn metadata theo chỉ số.
- [Oracle Java SE 17 — CallableStatement API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html): đăng ký OUT parameter và positional JDBC escape syntax.
- [Oracle Java SE 17 — ResultSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): cột ResultSet có index bắt đầu từ 1.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `PreparedStatementSetter` và named parameters.
- [Spring Framework — NamedParameterJdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): SQL parameters theo tên và mở rộng list.