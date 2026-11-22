# Thiết kế quy ước null thống nhất ở biên truy cập dữ liệu

## 1. Vì sao cần một quy ước `NULL` xuyên suốt?

**JDBC (Java Database Connectivity)** là API Java để truy cập cơ sở dữ liệu quan hệ. Trong một ứng dụng thực tế, dữ liệu đi qua nhiều lớp: HTTP hoặc giao diện người dùng, đối tượng nghiệp vụ Java, lớp repository, JDBC driver và bảng SQL. Nếu mỗi lớp hiểu “không có giá trị” theo một cách khác nhau, chương trình rất dễ ghi sai dữ liệu hoặc hiểu sai kết quả truy vấn.

Ví dụ, hệ thống khách hàng có cột `reward_points INTEGER NULL`:

- `NULL` có thể nghĩa là **chưa xác định số điểm**.
- `0` có thể nghĩa là **đã xác định và không có điểm**.
- Không tìm thấy **hàng khách hàng** là tình huống thứ ba, khác với việc hàng tồn tại nhưng `reward_points` là `NULL`.
- Trong yêu cầu cập nhật từng phần, **không gửi trường `rewardPoints`** có thể nghĩa là “giữ nguyên”, còn gửi `"rewardPoints": null` có thể nghĩa là “xóa giá trị”.

Nếu repository đọc `NULL` bằng `ResultSet.getInt()` rồi trả thẳng `0`, bốn trường hợp trên rất dễ bị trộn lẫn.

Mục tiêu của quy ước thống nhất là mô tả rõ **ý nghĩa, cách biểu diễn, cách đọc, cách ghi và cách chuyển đổi** `NULL` ở mỗi biên; không mặc định mọi dữ liệu thiếu đều phải biến thành `0`, `false` hoặc chuỗi rỗng.

## 2. Phân biệt `NULL` SQL, `null` Java và các giá trị thường

| Trường hợp | Ý nghĩa thường gặp | Điều phải tránh |
|---|---|---|
| SQL `NULL` | Chưa có hoặc không áp dụng giá trị cho cột | Coi là số `0`, `false`, `''` hoặc chuỗi `'NULL'` |
| Java `null` | Tham chiếu đối tượng không trỏ tới đối tượng nào | Dùng cho mọi trường hợp “không có”, kể cả chưa truyền tham số và không tìm thấy hàng |
| SQL `0` | Giá trị số bằng không | Dùng thay `NULL` khi “chưa xác định” khác “bằng không” |
| SQL `FALSE` | Giá trị logic sai | Dùng thay `NULL` khi nghiệp vụ có trạng thái “chưa biết” |
| SQL `''` | Chuỗi rỗng trên các DBMS phân biệt nó với `NULL` | Giả định mọi hệ quản trị xử lý giống nhau; Oracle có đặc điểm riêng với chuỗi rỗng |
| Không có hàng trong `ResultSet` | Truy vấn không trả bản ghi tương ứng | Coi là một hàng có mọi cột đều `NULL` |
| Không có field trong request | Client không gửi dữ liệu cho trường đó | Coi mặc định là yêu cầu đặt SQL `NULL` |

Mỗi cột phải có **quy ước nghiệp vụ cụ thể**. Ví dụ, một số điện thoại phụ có thể hợp lệ khi `NULL`, còn tên tài khoản dùng để đăng nhập thường cần `NOT NULL`. Thiết kế nên bắt đầu từ ý nghĩa dữ liệu và ràng buộc schema, không bắt đầu bằng kiểu Java tiện dùng nhất.

## 3. Định nghĩa hợp đồng dữ liệu từ database đến domain

Một quy ước dễ kiểm chứng gồm bốn quyết định cho mỗi trường:

1. **Có được thiếu không?** Xác định cột `NULL`/`NOT NULL` và ý nghĩa khi thiếu.
2. **Đọc thế nào?** Chọn getter JDBC và kiểu Java có thể biểu diễn `NULL` mà không mất thông tin.
3. **Ghi thế nào?** Chọn setter tương ứng, dùng `setNull(index, Types.X)` khi thật sự muốn ghi SQL `NULL`.
4. **Biên API biểu diễn ra sao?** Phân biệt không tìm thấy tài nguyên, trường dữ liệu có thể thiếu, và trường bị bỏ qua khi cập nhật.

Ví dụ hợp đồng cho bảng khách hàng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    nickname VARCHAR(100),
    reward_points INTEGER,
    marketing_opt_in BOOLEAN,
    birth_date DATE
);
```

Đây là DDL minh họa; cú pháp `BOOLEAN` và các kiểu có thể cần điều chỉnh cho DBMS cụ thể.

| Cột | SQL | Kiểu Java trong mô hình đọc | Quy ước |
|---|---|---|---|
| `id` | `BIGINT NOT NULL` qua khóa chính | `long` | Luôn có giá trị khi hàng hợp lệ |
| `display_name` | `VARCHAR NOT NULL` | `String` không `null` | Bắt buộc; có thể kiểm tra thêm chuỗi trắng ở tầng nghiệp vụ |
| `nickname` | `VARCHAR NULL` | `String` có thể `null` | `null` nghĩa là chưa đặt tên hiển thị phụ |
| `reward_points` | `INTEGER NULL` | `Integer` có thể `null` | Phân biệt chưa biết với `0` |
| `marketing_opt_in` | `BOOLEAN NULL` | `Boolean` có thể `null` | Phân biệt chưa lựa chọn với đồng ý (`true`) và từ chối (`false`) |
| `birth_date` | `DATE NULL` | `LocalDate` có thể `null` | Phân biệt chưa cung cấp ngày sinh với một ngày hợp lệ |

Nếu nghiệp vụ thực ra **không cho phép** trạng thái chưa biết của `marketing_opt_in`, nên đổi thiết kế thành `NOT NULL` và quy ước giá trị mặc định rõ ràng, thay vì giữ một cột nullable chỉ vì tiện thao tác.

## 4. Đọc `NULL` từ `ResultSet`: điểm dễ mất dữ liệu nhất

Một số getter JDBC dùng kiểu nguyên thủy Java. Khi cột SQL chứa `NULL`, `getInt()`, `getLong()` và `getBoolean()` trả về giá trị nguyên thủy mặc định như `0` hoặc `false`. **Phải gọi `wasNull()` để phân biệt trường hợp cột thật sự là `NULL`.**

```java
int rawPoints = rs.getInt("reward_points");
Integer points = rs.wasNull() ? null : rawPoints;

boolean rawChoice = rs.getBoolean("marketing_opt_in");
Boolean choice = rs.wasNull() ? null : rawChoice;
```

`rs` trong ví dụ là một `ResultSet` đang đứng trên hàng hợp lệ. Gọi `wasNull()` **ngay sau getter cần kiểm tra**, trước khi đọc cột khác, vì phương thức này cho biết **cột được đọc gần nhất** có phải SQL `NULL` hay không.

Ví dụ **sai**:

```java
int points = rs.getInt("reward_points");
String nickname = rs.getString("nickname");

// Sai: wasNull() lúc này kiểm tra nickname, KHÔNG phải reward_points.
if (rs.wasNull()) {
    System.out.println("Điểm chưa được xác định");
}
```

Ví dụ đúng:

```java
int points = rs.getInt("reward_points");
boolean pointsWasNull = rs.wasNull();

String nickname = rs.getString("nickname");

if (pointsWasNull) {
    System.out.println("Điểm chưa được xác định");
} else {
    System.out.println("Điểm: " + points);
}
```

Với những getter trả về **đối tượng tham chiếu**, `getString()` và `getBigDecimal()` thường trả trực tiếp Java `null` khi cột là SQL `NULL`. Không cần gọi `wasNull()` chỉ để phân biệt `null` trong những trường hợp này. Chẳng hạn:

```java
String nickname = rs.getString("nickname"); // SQL NULL → Java null.
BigDecimal amount = rs.getBigDecimal("amount"); // SQL NULL → Java null.
```

Các ví dụ `BigDecimal` giả định đã import `java.math.BigDecimal` và bảng có cột thích hợp. Đọc và ghi dữ liệu thập phân nên dùng kiểu chính xác, không ngầm biến `NULL` thành số `0` hoặc chuyển qua `double` khi nghiệp vụ yêu cầu chính xác.

### `getObject()` và getter có kiểu

`getObject(column)` trả về `null` khi cột có SQL `NULL`, nhưng kiểu đối tượng Java cho giá trị khác `NULL` do driver quyết định theo ánh xạ JDBC.

```java
Object pointsValue = rs.getObject("reward_points");
if (pointsValue == null) {
    System.out.println("Chưa có điểm");
}
```

JDBC hiện đại có phương thức `getObject(column, Class<T>)`, thuận tiện để đọc các kiểu được hỗ trợ:

```java
Integer points = rs.getObject("reward_points", Integer.class);
LocalDate birthDate = rs.getObject("birth_date", LocalDate.class);
```

Ví dụ trên cần `import java.time.LocalDate;`. `LocalDate` thuộc ánh xạ thời gian từ JDBC 4.2; hành vi của getter có kiểu còn phụ thuộc **phiên bản và mức hỗ trợ của driver**. Nếu driver không hỗ trợ một ánh xạ cụ thể, có thể dùng getter JDBC tương ứng và chuyển đổi có kiểm soát, ví dụ `getDate()` rồi `toLocalDate()` sau khi kiểm tra `null`.

## 5. Đọc “không có hàng” khác đọc “hàng có cột `NULL`”

Xem truy vấn:

```sql
SELECT id, nickname
FROM customers
WHERE id = ?;
```

`ResultSet.next()` trả `false` nghĩa là **không có bản ghi phù hợp**; trong khi `next()` trả `true` và `getString("nickname") == null` nghĩa là **có bản ghi nhưng nickname chưa được đặt**.

```java
try (ResultSet rs = statement.executeQuery()) {
    if (!rs.next()) {
        // Không tìm thấy khách hàng.
    } else {
        String nickname = rs.getString("nickname");
        if (nickname == null) {
            // Có khách hàng, nhưng chưa có nickname.
        }
    }
}
```

Quy ước repository được khuyến nghị là: **dùng `Optional<Customer>` cho kết quả tìm kiếm có thể không tồn tại**, còn các trường nullable bên trong `Customer` biểu diễn giá trị cột thiếu theo hợp đồng domain. `Optional.empty()` không có nghĩa một hàng chứa toàn `NULL`.

Không dùng giá trị giả như `Customer(id=0)` hoặc chuỗi `"NOT_FOUND"` để biểu diễn không tìm thấy hàng; chúng có thể trùng với dữ liệu hợp lệ hoặc làm sai kiểu của mô hình.

## 6. Ví dụ repository đầy đủ: ánh xạ có và không có `NULL`

Ví dụ sau sử dụng **Java 17** (cú pháp `record`) và một `DataSource` đã cấu hình. Bảng sử dụng cấu trúc ở mục 3. Đoạn mã phân biệt ba thứ: khách hàng không tồn tại, khách hàng tồn tại nhưng thiếu một số trường, và khách hàng có các giá trị như `0` hoặc `false`.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.Optional;
import javax.sql.DataSource;

record CustomerRow(
        long id,
        String displayName,
        String nickname,          // Có thể null.
        Integer rewardPoints,     // Có thể null; 0 là giá trị thật.
        Boolean marketingOptIn,   // Có thể null; false là giá trị thật.
        LocalDate birthDate       // Có thể null.
) {}

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<CustomerRow> findById(long customerId) throws SQLException {
        String sql = "SELECT id, display_name, nickname, reward_points, " +
                     "marketing_opt_in, birth_date FROM customers WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, customerId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty(); // Không có hàng.
                }

                long id = rs.getLong("id"); // Khóa chính NOT NULL.
                String name = rs.getString("display_name");
                String nickname = rs.getString("nickname");

                int pointsValue = rs.getInt("reward_points");
                Integer points = rs.wasNull() ? null : pointsValue;

                boolean optInValue = rs.getBoolean("marketing_opt_in");
                Boolean optIn = rs.wasNull() ? null : optInValue;

                LocalDate birthDate = rs.getObject("birth_date", LocalDate.class);

                return Optional.of(new CustomerRow(
                        id, name, nickname, points, optIn, birthDate));
            }
        }
    }
}
```

Nếu driver chưa hỗ trợ `getObject("birth_date", LocalDate.class)`, có thể chuyển từ `java.sql.Date`:

```java
java.sql.Date sqlDate = rs.getDate("birth_date");
LocalDate birthDate = sqlDate == null ? null : sqlDate.toLocalDate();
```

Không áp dụng hai đoạn đọc `birth_date` liên tiếp trong cùng một phương thức như một hành vi bắt buộc; đây là **hai lựa chọn thay thế** tùy driver.

Trên biên domain/API, hãy ghi rõ các thành phần `nickname`, `rewardPoints`, `marketingOptIn`, `birthDate` có thể `null`. Có thể dùng annotation nullable theo thư viện dự án, kiểu kết quả riêng hoặc quy tắc kiểm tra khi tạo đối tượng. Quan trọng là **mọi repository tuân thủ cùng một hợp đồng**, thay vì nơi trả `null`, nơi tự biến thành `0`, nơi ném ngoại lệ.

## 7. Ghi SQL `NULL` đúng kiểu với `PreparedStatement`

Với tham số có thể thiếu, JDBC cung cấp `setNull(index, sqlType)`. Cần chỉ định kiểu SQL mong muốn bằng `java.sql.Types`:

```java
import java.sql.Types;

if (nickname == null) {
    statement.setNull(1, Types.VARCHAR);
} else {
    statement.setString(1, nickname);
}

if (rewardPoints == null) {
    statement.setNull(2, Types.INTEGER);
} else {
    statement.setInt(2, rewardPoints);
}

if (marketingOptIn == null) {
    statement.setNull(3, Types.BOOLEAN);
} else {
    statement.setBoolean(3, marketingOptIn);
}
```

Ví dụ giả định `statement` là `PreparedStatement` đang mở, các biến có kiểu `String`, `Integer`, `Boolean` tương ứng, và schema dùng `VARCHAR`, `INTEGER`, `BOOLEAN`. Với một số DBMS ánh xạ boolean sang kiểu khác, cần chọn mã `Types` theo cột thực tế và khả năng driver.

Không dựa vào `statement.setObject(index, null)` như một quy tắc portable cho mọi câu SQL. `null` Java không mang sẵn kiểu SQL, đặc biệt với câu lệnh chưa đủ ngữ cảnh hoặc tham số stored procedure. Một số driver chấp nhận cách này, một số có thể không suy ra kiểu mong muốn.

Cũng có thể dùng `setObject(index, null, Types.INTEGER)` hoặc biến thể dùng `JDBCType`, nếu driver hỗ trợ. Quy ước nhóm nên chọn **một cách rõ ràng** để việc đọc code và chẩn đoán lỗi dễ hơn; với các kiểu SQL thông dụng, `setNull(index, Types.X)` rất dễ hiểu.

### Ví dụ lưu hồ sơ khách hàng

```java
public int updateProfile(long id, String nickname, Integer rewardPoints)
        throws SQLException {
    String sql = "UPDATE customers SET nickname = ?, reward_points = ? " +
                 "WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(sql)) {

        if (nickname == null) {
            ps.setNull(1, Types.VARCHAR);
        } else {
            ps.setString(1, nickname);
        }

        if (rewardPoints == null) {
            ps.setNull(2, Types.INTEGER);
        } else {
            ps.setInt(2, rewardPoints);
        }

        ps.setLong(3, id);
        return ps.executeUpdate();
    }
}
```

Đoạn này là **phương thức minh họa thuộc một lớp repository có field `dataSource`** và import các lớp JDBC, `Types` cần thiết. Hợp đồng của phương thức là: tham số `null` nghĩa là **ghi SQL `NULL`**, không phải “giữ giá trị cũ”. Do đó đây là thao tác thay thế hai trường được nêu, **không phải PATCH**. Giá trị trả về là update count; `0` có thể nghĩa không có hàng phù hợp (hoặc hành vi tương ứng tùy DBMS).

## 8. `INSERT`: không gửi cột, dùng `DEFAULT`, và gửi `NULL` là ba quyết định khác nhau

Giả sử định nghĩa:

```sql
CREATE TABLE tasks (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) DEFAULT 'NEW',
    note VARCHAR(200)
);
```

Ba câu lệnh minh họa:

```sql
-- A: Bỏ qua cột status, DBMS có thể áp dụng DEFAULT 'NEW'.
INSERT INTO tasks (id, note) VALUES (1, 'Ghi chú');

-- B: Gửi SQL NULL tường minh cho status.
INSERT INTO tasks (id, status, note) VALUES (2, NULL, 'Ghi chú');

-- C: Yêu cầu DEFAULT tường minh nếu DBMS hỗ trợ cú pháp này.
INSERT INTO tasks (id, status, note) VALUES (3, DEFAULT, 'Ghi chú');
```

Trong mô hình SQL thông thường, A sử dụng giá trị mặc định, B ghi `NULL` (vì cột đang nullable) và C yêu cầu giá trị mặc định. Khi cột khai báo `NOT NULL`, B có thể bị từ chối. **Không giả định `NULL` được tự động thay bằng `DEFAULT`**; quy tắc và một số chế độ đặc thù của DBMS có thể khác, cần kiểm tra môi trường thực tế.

Nếu API cho phép “giữ mặc định”, repository phải biết **có cần bỏ cột ra khỏi câu `INSERT`** hoặc sử dụng cú pháp mặc định của DBMS, thay vì bind `NULL` một cách máy móc.

## 9. `UPDATE` từng phần: cần ba trạng thái, không chỉ `null`

Với yêu cầu HTTP PATCH, ba ý nghĩa có thể khác nhau:

| Nội dung request | Ý định phổ biến |
|---|---|
| Không có thuộc tính `nickname` | **Không thay đổi** nickname hiện tại |
| `"nickname": null` | **Xóa** nickname đang có, nếu schema và quyền cho phép |
| `"nickname": "An"` | **Thay** nickname thành `"An"` |

Nếu chỉ sử dụng một biến Java `String nickname`, thì cả “không gửi field” và “gửi null” có thể cùng biến thành Java `null`, làm mất thông tin. `Optional<String>` tự nó cũng chỉ có `empty` hoặc `present`; `Optional.ofNullable(null)` là `empty`, nên **không đủ để phân biệt ba trạng thái** nếu chỉ dùng một `Optional`.

Một mô hình rõ ràng hơn là **đánh dấu field có được gửi không**, và nếu gửi thì giá trị có thể `null`:

```java
// Java 17: minh họa giá trị của một trường trong PATCH.
public record FieldPatch<T>(boolean supplied, T value) {
    public static <T> FieldPatch<T> omitted() {
        return new FieldPatch<>(false, null);
    }

    public static <T> FieldPatch<T> supplied(T value) {
        return new FieldPatch<>(true, value);
    }
}

FieldPatch<String> unchanged = FieldPatch.omitted();
FieldPatch<String> cleared = FieldPatch.supplied(null);
FieldPatch<String> renamed = FieldPatch.supplied("An");
```

Ví dụ các biến `unchanged`, `cleared`, `renamed` có ba trạng thái khác nhau. Bộ phân tích JSON/controller phải **giữ được sự khác biệt giữa field vắng mặt và field chứa JSON `null`**; không phải mọi thư viện binding mặc định đều làm điều đó nếu chỉ dùng POJO nullable.

Ở tầng repository, có thể xây dựng câu `UPDATE` từ **những tên cột cố định được ứng dụng cho phép**, chỉ thêm cột nào có `supplied() == true`, rồi bind giá trị tương ứng. Không nối trực tiếp tên cột do client gửi vào SQL. Nếu không có field nào được cung cấp, có thể bỏ qua `UPDATE` hoặc trả kết quả “không có thay đổi” theo hợp đồng API.

Khi một field được gửi với `null`, kiểm tra schema có cho phép `NULL` và người gọi có quyền xóa giá trị đó không. **Một `NULL` hợp lệ về SQL chưa chắc hợp lệ theo quy tắc nghiệp vụ.**

## 10. SQL sử dụng logic ba giá trị: `TRUE`, `FALSE`, `UNKNOWN`

`NULL` trong SQL không hoạt động như Java `null` trong mọi biểu thức. Khi so sánh với `NULL`, kết quả thông thường là **`UNKNOWN`**, không phải `TRUE` hoặc `FALSE`.

```sql
-- Không đúng để tìm các hàng có nickname NULL:
SELECT id FROM customers WHERE nickname = NULL;

-- Đúng:
SELECT id FROM customers WHERE nickname IS NULL;

-- Tìm hàng có nickname khác NULL:
SELECT id FROM customers WHERE nickname IS NOT NULL;
```

Trong mệnh đề `WHERE`, chỉ các hàng có điều kiện là `TRUE` được giữ lại; hàng có điều kiện `FALSE` **hoặc `UNKNOWN`** đều bị loại.

| Biểu thức SQL | Khi cột chứa `NULL` | Kết quả logic |
|---|---|---|
| `nickname = 'An'` | Không có giá trị để so sánh | `UNKNOWN` |
| `nickname <> 'An'` | Không có giá trị để so sánh | `UNKNOWN` |
| `nickname = NULL` | So sánh với `NULL` bằng `=` | `UNKNOWN` |
| `nickname IS NULL` | Kiểm tra tình trạng thiếu giá trị | `TRUE` |
| `nickname IS NOT NULL` | Kiểm tra có giá trị | `FALSE` |

Khi cần trả tất cả khách hàng **không có nickname hoặc có nickname khác `"An"`**, phải viết rõ:

```sql
SELECT id
FROM customers
WHERE nickname <> 'An' OR nickname IS NULL;
```

Một bẫy đáng nhớ là `NOT IN` khi danh sách con chứa `NULL`: biểu thức có thể cho kết quả `UNKNOWN` ở những hàng tưởng rằng phải thỏa. Khi cần phép lọc loại trừ, nên xem xét `NOT EXISTS` và xử lý rõ điều kiện có `NULL` theo nghiệp vụ, thay vì mặc định `NOT IN` luôn cho kết quả mong muốn.

### `COALESCE` không phải phép thay thế `NULL` tùy ý

`COALESCE(nickname, '(chưa đặt)')` chọn giá trị không `NULL` đầu tiên, hữu ích cho **trình bày dữ liệu**:

```sql
SELECT id, COALESCE(nickname, '(chưa đặt)') AS display_nickname
FROM customers;
```

Nhưng câu SQL này đã biến trạng thái `NULL` thành chuỗi biểu diễn. Nếu repository dùng kết quả đó làm giá trị domain và quên phân biệt `NULL`, ứng dụng sẽ mất khả năng nhận ra khách hàng chưa đặt nickname. Chỉ dùng fallback khi **đúng phạm vi và ý nghĩa**, ví dụ ở view báo cáo hoặc giao diện, không mặc định ngay tại tầng truy cập dữ liệu.

## 11. Chọn một quy ước ở biên và áp dụng nhất quán

Một bộ quy ước thực tế cho dự án Java + JDBC có thể là:

| Tình huống | Quy ước đề xuất |
|---|---|
| Truy vấn tìm một bản ghi không thấy hàng | Repository trả `Optional.empty()` hoặc một loại kết quả “not found” rõ ràng |
| Truy vấn có hàng, cột `NULL` | Mapper giữ trạng thái thiếu trong kiểu Java phù hợp (`Integer`, `Boolean`, `String`, `LocalDate` nullable) |
| Cột SQL `NOT NULL` | Ánh xạ sang trường Java bắt buộc; kiểm tra tính hợp lệ khi xây dựng domain nếu cần |
| Bind tham số `NULL` | Dùng `setNull(index, Types.X)` theo kiểu SQL cột/tham số |
| Ghi một giá trị được chọn là `0` hoặc `false` | Bind giá trị thật, không đồng nhất với `NULL` |
| Request cập nhật từng phần | Biểu diễn riêng `omitted`, `clear`, `set`; không dùng một Java `null` cho cả ba |
| Hiển thị giá trị thiếu | Chọn fallback ở biên trình bày, không âm thầm thay đổi giá trị domain |
| Lỗi hoặc dữ liệu thiếu trái schema | Báo lỗi/chẩn đoán rõ ràng, không tự bịa giá trị thay thế |

Việc chọn sử dụng trường nullable trong record, `Optional` trong kết quả trả về, hay một kiểu đại số riêng cho trạng thái field là **quy ước kiến trúc**, không phải luật bắt buộc của JDBC. Điều quan trọng là hợp đồng thống nhất được tài liệu hóa và kiểm thử, không đòi hỏi mọi dự án phải có cùng mô hình Java.

## 12. Ràng buộc database phải phản ánh quy ước nghiệp vụ

Kiểm tra ở Java không thay thế ràng buộc SQL. Dữ liệu có thể được ghi qua dịch vụ khác, tác vụ nền, script quản trị hoặc một phiên bản ứng dụng chưa cập nhật.

```sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(12,2) NOT NULL,
    note VARCHAR(200)
);
```

Ở đây `amount` bắt buộc còn `note` có thể thiếu. Tầng Java nên từ chối `amount == null` trước khi gọi JDBC, nhưng DBMS vẫn cần `NOT NULL` để bảo vệ dữ liệu khi có lối ghi khác.

Mặt khác, đừng thêm `NOT NULL` cho một cột chỉ vì mã hiện tại không thích xử lý `null`. Nếu nghiệp vụ có trạng thái “chưa xác định”, việc dùng sentinel như ngày `1970-01-01`, số `-1` hoặc chuỗi `"UNKNOWN"` có thể tạo ra những giá trị gây hiểu lầm, trừ khi sentinel thực sự là một quy ước được định nghĩa và kiểm soát rõ.

Việc thay đổi cột từ nullable sang `NOT NULL` cần khảo sát dữ liệu cũ, kế hoạch chuyển đổi/điền dữ liệu và tương thích với các phiên bản ứng dụng đang chạy. Không chỉ đổi mapper rồi giả định database tự trở nên nhất quán.

## 13. Kiểm thử hợp đồng `NULL` từ đọc đến ghi

Một bộ kiểm thử tích hợp có giá trị nên bao gồm:

1. **Cột thực sự là SQL `NULL`:** `getInt` trả `0` nhưng `wasNull()` trả `true`; repository thu được `Integer null`.
2. **Cột có giá trị `0`:** `getInt` trả `0` và `wasNull()` trả `false`; repository giữ `Integer.valueOf(0)`.
3. **Cột boolean `NULL` và `FALSE`:** hai trường hợp được phân biệt thành `Boolean null` và `Boolean.FALSE`.
4. **Không tìm thấy hàng:** trả `Optional.empty()` chứ không dựng một đối tượng với các trường `null`.
5. **Ghi `NULL`:** setter dùng đúng `Types`, đọc lại nhận SQL `NULL` chứ không nhận chuỗi `'null'` hoặc số `0`.
6. **Không ghi cột có default:** xác minh trường hợp bỏ cột khác với truyền SQL `NULL` theo DBMS đang sử dụng.
7. **PATCH:** kiểm tra cả ba đường `omitted`, `supplied(null)` và `supplied(value)`.
8. **Ràng buộc `NOT NULL`:** việc cố ghi `NULL` vào cột bắt buộc bị xử lý như lỗi dữ liệu, không bị chuyển sang giá trị giả.
9. **Điều kiện `WHERE` với `NULL`:** kiểm tra `IS NULL`, `IS NOT NULL` và các điều kiện có logic ba giá trị.
10. **Mức hỗ trợ driver:** xác minh `getObject(..., LocalDate.class)` và các kiểu `setNull`/`Types` trên đúng JDBC driver và DBMS triển khai.

Các test chỉ so sánh **chuỗi JSON đầu ra** có thể bỏ sót lỗi giữa SQL `NULL` và `0` nếu đã có bước fallback ở tầng presentation. Nên có ít nhất một số test trực tiếp trên repository hoặc database để kiểm tra dữ liệu gốc.

## 14. Những lỗi thường gặp khi thiết kế quy ước `NULL`

| Cách làm dễ sai | Hậu quả | Cách xử lý |
|---|---|---|
| Đọc nullable `INTEGER` bằng `getInt()` mà không gọi `wasNull()` | `NULL` bị biến thành `0` | Đọc `wasNull()` ngay hoặc dùng getter đối tượng phù hợp |
| Gọi `wasNull()` sau khi đã đọc cột khác | Kiểm tra nhầm cột | Gọi ngay sau getter cần kiểm tra |
| Trả `null` cho cả “không thấy hàng” và “hàng có cột `NULL`” | API thiếu khả năng phân biệt | Dùng `Optional`/kiểu kết quả rõ nghĩa cho việc tìm bản ghi |
| Ghi `setString(index, "null")` | Lưu bốn ký tự `'null'`, không phải SQL `NULL` | Dùng `setNull(index, Types.VARCHAR)` |
| Dùng `setObject(index, null)` mà không xét kiểu SQL | Driver có thể không suy ra đúng kiểu | Dùng `setNull` hoặc setter có khai báo kiểu |
| Dùng `Optional.ofNullable(value)` làm đủ ba trạng thái PATCH | Không phân biệt field bị bỏ qua và field gửi JSON `null` | Dùng mô hình ba trạng thái với cờ `supplied` |
| Tự đổi mọi chuỗi rỗng thành `NULL` | Làm mất ý nghĩa chuỗi rỗng hợp lệ | Chuẩn hóa chỉ khi quy ước nghiệp vụ yêu cầu; xét DBMS cụ thể |
| Dùng `COALESCE` ở mọi câu `SELECT` | Domain mất dấu vết dữ liệu thiếu | Giữ giá trị gốc ở tầng data access, fallback ở biên hiển thị |
| Giả định cột nullable luôn được phép xóa theo nghiệp vụ | Ghi được về kỹ thuật nhưng vi phạm quy tắc nghiệp vụ | Kiểm tra quyền, workflow và ràng buộc trước khi ghi |

## 15. Bài tập tổng hợp

Giả sử bảng `subscriptions` có các cột:

```sql
CREATE TABLE subscriptions (
    id BIGINT PRIMARY KEY,
    renewal_day INTEGER,
    auto_renew BOOLEAN
);
```

Ba hàng minh họa:

| `id` | `renewal_day` | `auto_renew` |
|---:|---:|---|
| 1 | `NULL` | `NULL` |
| 2 | `0` | `FALSE` |
| 3 | `15` | `TRUE` |

Giả sử chương trình gọi `rs.getInt("renewal_day")` và `rs.getBoolean("auto_renew")` cho từng hàng, rồi đọc `wasNull()` **ngay sau mỗi getter**:

| Hàng | Giá trị `getInt` | `wasNull` sau `getInt` | Giá trị `getBoolean` | `wasNull` sau `getBoolean` |
|---:|---:|---|---|---|
| 1 | `0` | `true` | `false` | `true` |
| 2 | `0` | `false` | `false` | `false` |
| 3 | `15` | `false` | `true` | `false` |

Vì sao không thể chỉ kiểm tra `getInt() == 0` để xác định cột `renewal_day` bị thiếu? Vì cả hàng 1 và hàng 2 đều trả về `0` nhưng chỉ hàng 1 thực sự có SQL `NULL`. Tương tự, hàng 1 và 2 đều trả `false` từ `getBoolean` nhưng mang ý nghĩa nghiệp vụ khác nhau.

Nếu yêu cầu API gửi `"autoRenew": null`, cần biết đó là **lệnh xóa** hay biểu diễn **giá trị hiện tại chưa xác định** tùy loại request. Nếu trường này không xuất hiện trong một PATCH, đó thường là **yêu cầu giữ nguyên**, không phải đổi SQL thành `NULL`.

**Ghi nhớ:** Một quy ước `NULL` tốt phải phân biệt được **không tìm thấy hàng**, **cột có SQL `NULL`**, **giá trị hợp lệ như `0`/`false`** và **field bị bỏ qua trong cập nhật**. Với JDBC, dùng `wasNull()` đúng chỗ cho getter nguyên thủy, giữ kiểu Java có thể biểu diễn thiếu dữ liệu, bind SQL `NULL` bằng kiểu rõ ràng và bảo vệ hợp đồng bằng kiểm thử cùng ràng buộc database.
