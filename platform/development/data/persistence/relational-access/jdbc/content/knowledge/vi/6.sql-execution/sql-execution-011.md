# Tách cấu trúc SQL khỏi giá trị dữ liệu do người dùng cung cấp

Khi ứng dụng Java thực thi SQL, dữ liệu nhập từ biểu mẫu, URL, tệp hoặc dịch vụ khác thường được đưa vào điều kiện truy vấn. Nếu ghép trực tiếp những giá trị này vào chuỗi SQL, dữ liệu có thể vô tình hoặc cố ý trở thành **một phần cú pháp**: dấu nháy đơn kết thúc chuỗi, toán tử thay đổi điều kiện `WHERE`, hoặc một đoạn SQL được chèn thêm. Đó là nền tảng của nhiều lỗi **SQL injection**.

Trong **JDBC (Java Database Connectivity API for relational database access)**, cách xử lý chuẩn là **cố định cấu trúc câu SQL và truyền giá trị riêng qua `PreparedStatement`**. Bài thuộc chương *Thực thi SQL* này giải thích ranh giới giữa cấu trúc và dữ liệu, những giới hạn của dấu `?`, cùng các cách xử lý truy vấn động như `ORDER BY`, `IN` và `LIKE`.

## 1. Cấu trúc SQL và giá trị dữ liệu khác nhau thế nào?

Xét một yêu cầu: tìm tài khoản đang hoạt động theo địa chỉ email do người dùng nhập.

```sql
SELECT id, email
FROM app_account
WHERE email = ?
  AND active = ?;
```

| Thành phần | Ví dụ | Có nên lấy nguyên văn từ đầu vào người dùng? |
| --- | --- | --- |
| **Từ khóa và cú pháp SQL** | `SELECT`, `FROM`, `WHERE`, `AND` | Không: ứng dụng kiểm soát cấu trúc |
| **Tên bảng, tên cột** | `app_account`, `email`, `active` | Không: dùng tên cố định hoặc danh sách cho phép |
| **Toán tử và biểu thức** | `=`, `AND`, `ORDER BY` | Không: chỉ ghép các lựa chọn cấu trúc đã kiểm soát |
| **Giá trị dữ liệu** | `"an@example.com"`, `true` | Có: truyền riêng qua tham số ràng buộc |
| **Tham số JDBC** | `?` ở vị trí 1, 2 | Là vị trí chứa **giá trị**, không phải tên bảng hoặc đoạn SQL |

Đối với `PreparedStatement`, ứng dụng khai báo **mẫu câu lệnh SQL** trước, sau đó gọi `setXxx(index, value)` để liên kết giá trị vào từng dấu `?`. Driver và hệ quản trị cơ sở dữ liệu (DBMS) xử lý các giá trị đó theo nghĩa **dữ liệu của biểu thức**, thay vì nối chúng vào mã SQL do người dùng có thể điều khiển.

Đây là nguyên tắc cần ghi nhớ:

> **SQL do ứng dụng quyết định cấu trúc; dữ liệu bên ngoài chỉ được cung cấp như giá trị tham số.**

Sự phân tách này giúp phòng chống SQL injection khi dùng đúng cách, đồng thời làm rõ cách chuyển đổi kiểu và xử lý dấu nháy trong chuỗi.

## 2. Vì sao ghép chuỗi SQL trực tiếp nguy hiểm?

Đây là cách viết **không an toàn**:

```java
String email = userInput;
String sql =
        "SELECT id FROM app_account WHERE email = '" + email + "'";

try (Statement statement = connection.createStatement();
     ResultSet result = statement.executeQuery(sql)) {
    // ...
}
```

Nếu người dùng nhập địa chỉ bình thường `an@example.com`, chuỗi SQL được tạo trông có vẻ đúng. Nhưng giả sử một người nhập:

```text
' OR '1'='1
```

Câu SQL sau khi ghép sẽ thành:

```sql
SELECT id
FROM app_account
WHERE email = '' OR '1'='1';
```

Điều kiện `'1'='1'` luôn đúng; kết quả có thể bao gồm nhiều tài khoản thay vì chỉ một địa chỉ email. **Đoạn này chỉ minh họa cơ chế lỗi**: tác động thực tế còn phụ thuộc câu SQL đầy đủ, quyền tài khoản database, cách driver/DBMS xử lý và dữ liệu.

Vấn đề không nằm ở riêng dấu nháy đơn. Bất cứ khi nào một giá trị bên ngoài được chèn vào **cấu trúc SQL**, ứng dụng có nguy cơ trao quyền điều khiển cú pháp cho nguồn dữ liệu đó.

Việc tự loại bỏ vài ký tự, thay dấu nháy thủ công hoặc dùng biểu thức chính quy để “làm sạch” mọi đầu vào **không phải cách thay thế tổng quát cho tham số hóa**. Quy tắc escape, encoding và cú pháp có thể khác nhau giữa các hệ quản trị.

## 3. Giải pháp chuẩn: `PreparedStatement` và dấu `?`

Thay vì ghép chuỗi, cố định SQL và gán giá trị bằng phương thức tương ứng:

```java
String sql = "SELECT id FROM app_account WHERE email = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, userInput);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getLong("id"));
        }
    }
}
```

Với cùng đầu vào `' OR '1'='1`, giá trị đó được truyền như **một chuỗi email cần so khớp**, không biến thành toán tử `OR` của truy vấn. Thông thường truy vấn sẽ không tìm thấy địa chỉ nào đúng bằng chuỗi đó.

Một vài chi tiết quan trọng:

1. Chỉ số tham số JDBC bắt đầu từ **1**, không phải 0.
2. `?` đứng **trong biểu thức SQL**, không bọc trong dấu nháy: dùng `WHERE email = ?`, không dùng `WHERE email = '?'`.
3. Mỗi dấu `?` đại diện cho một vị trí tham số. Nếu câu SQL có hai vị trí, phải gán các vị trí cần thiết trước khi thực thi.
4. `setString()` dành cho giá trị chuỗi; `setLong()`, `setInt()`, `setBoolean()`, `setBigDecimal()` và `setDate()` dành cho những kiểu tương ứng. Tránh chuyển mọi giá trị thành chuỗi rồi dựa vào DBMS tự ép kiểu.
5. `executeQuery()` dùng khi câu lệnh trả `ResultSet`; `executeUpdate()` dùng cho nhiều thao tác thêm/sửa/xóa và trả về số hàng bị ảnh hưởng.
6. `try-with-resources` đóng `ResultSet` và `PreparedStatement` ngay cả khi xảy ra `SQLException`.

JDBC cung cấp **giao diện tham số hóa chuẩn**. Việc driver dùng prepared statement thực sự phía máy chủ, mô phỏng cách truyền tham số hoặc dùng cơ chế cache nào là chi tiết triển khai; tính đúng của mã phải dựa trên hợp đồng truyền **giá trị riêng** của API, không dựa trên một giả định về giao thức.

## 4. Ví dụ hoàn chỉnh: tìm tài khoản theo email và trạng thái

Giả sử database PostgreSQL có bảng minh họa:

```sql
CREATE TABLE app_account (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL
);

INSERT INTO app_account (email, active)
VALUES ('an@example.com', TRUE),
       ('binh@example.com', FALSE);
```

Ứng dụng có `DataSource` đã cấu hình hợp lệ và cần tìm ID của một tài khoản **đang hoạt động**. Repository có thể viết:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.OptionalLong;
import javax.sql.DataSource;

public final class AccountRepository {
    private final DataSource dataSource;

    public AccountRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public OptionalLong findActiveIdByEmail(String email)
            throws SQLException {
        if (email == null || email.isBlank() || email.length() > 254) {
            throw new IllegalArgumentException("Email khong hop le");
        }

        final String sql =
                "SELECT id FROM app_account " +
                "WHERE email = ? AND active = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setString(1, email);
            statement.setBoolean(2, true);

            try (ResultSet result = statement.executeQuery()) {
                return result.next()
                        ? OptionalLong.of(result.getLong("id"))
                        : OptionalLong.empty();
            }
        }
    }
}
```

Phương thức dùng `email` như một **giá trị**. `true` cũng là một giá trị được gán vào vị trí thứ hai. Với dữ liệu mẫu, `an@example.com` có thể cho kết quả chứa ID; `binh@example.com` không được trả về vì `active = FALSE`.

Đoạn kiểm tra `null`/rỗng/độ dài là **kiểm tra hợp lệ theo nghiệp vụ**, không phải phần thay thế cho `PreparedStatement`. Việc email có đúng định dạng, có được phép truy cập hay không và người gọi có quyền xem tài khoản nào là những vấn đề khác cần thiết kế riêng.

### Kiểu dữ liệu và giá trị `NULL`

Hãy gán tham số theo loại dữ liệu:

```java
statement.setLong(1, accountId);
statement.setBigDecimal(2, totalAmount);
statement.setBoolean(3, active);
```

Đây là ví dụ các lời gọi trên một `PreparedStatement` có ba tham số tương ứng; các biến đã có kiểu phù hợp. Nếu muốn truyền **SQL `NULL`**, dùng `setNull(index, sqlType)` hoặc overload `setObject()` phù hợp:

```java
statement.setNull(1, java.sql.Types.VARCHAR);
```

Cần phân biệt **giá trị `NULL`** với **biểu thức kiểm tra `NULL`**. Trong SQL, điều kiện `column = NULL` không có cùng ý nghĩa với `column IS NULL`. Nếu yêu cầu tìm hàng có cột rỗng, viết cấu trúc `IS NULL` do ứng dụng lựa chọn:

```sql
SELECT id FROM app_account WHERE deleted_at IS NULL;
```

Truyền `null` vào `WHERE deleted_at = ?` thường **không** tìm được các hàng có `deleted_at IS NULL`, vì quy tắc logic ba giá trị của SQL.

## 5. `PreparedStatement` bảo vệ được phần nào, không bảo vệ phần nào?

Tham số JDBC là **vị trí giá trị** trong câu SQL, không phải nơi chứa tùy ý một đoạn cú pháp.

| Mong muốn | Có thể dùng `?`? | Cách làm phù hợp |
| --- | --- | --- |
| So khớp email, số lượng, ngày tháng | **Có** | `WHERE email = ?`, `WHERE quantity >= ?` |
| Gán dữ liệu khi `INSERT` hoặc `UPDATE` | **Có** | `VALUES (?, ?)`, `SET quantity = ?` |
| Giá trị cho `LIMIT`/`OFFSET` | **Tùy SQL dialect/driver** | Dùng placeholder nếu DBMS cho phép, kiểm tra miền trước |
| Chọn tên bảng | **Không** | Tên cố định hoặc ánh xạ từ danh sách cho phép |
| Chọn tên cột trong `ORDER BY` | **Không** | Dùng `enum`/switch ánh xạ sang tên cột cố định |
| Chọn `ASC` hoặc `DESC` | **Không** | Chuyển lựa chọn đã kiểm tra thành từ khóa cố định |
| Thay `AND` thành `OR` | **Không** | Chọn nhánh cấu trúc do ứng dụng định nghĩa |
| Truyền nguyên câu SQL để driver chạy như lệnh | **Không** | Xây dựng câu SQL từ các mẫu an toàn đã kiểm soát |

Ví dụ lỗi hiểu nhầm:

```sql
-- Khong hop le cho muc tieu chon ten bang bang tham so.
SELECT * FROM ? WHERE id = ?;

-- Tham so dau tien la gia tri chu khong thanh ten cot sap xep.
SELECT id, email FROM app_account ORDER BY ?;
```

Trường hợp thứ hai có thể được một số DBMS chấp nhận như sắp xếp theo **biểu thức hằng được truyền**, nhưng **không** có nghĩa nó sẽ sắp xếp theo cột có tên bằng chuỗi tham số.

## 6. `ORDER BY` động: ánh xạ tên cột bằng danh sách cho phép

Giả sử giao diện cho phép chọn cách sắp xếp theo `id` hoặc `email`, tăng hoặc giảm dần. Giá trị lựa chọn từ HTTP vẫn là đầu vào không đáng tin cậy. Đừng làm thế này:

```java
// Sai: sortBy den tu nguoi dung, bi ghep vao cau truc SQL.
String sql = "SELECT id, email FROM app_account ORDER BY " + sortBy;
```

Thay vào đó, ánh xạ các giá trị chấp nhận được sang **đoạn SQL cố định**:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void listAccounts(
        Connection connection, String sortBy, boolean descending)
        throws SQLException {

    final String column;
    switch (sortBy) {
        case "id":
            column = "id";
            break;
        case "email":
            column = "email";
            break;
        default:
            throw new IllegalArgumentException("Cot sap xep khong hop le");
    }

    String direction = descending ? "DESC" : "ASC";
    String sql = "SELECT id, email FROM app_account " +
                 "WHERE active = ? ORDER BY " + column + " " + direction;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setBoolean(1, true);

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getLong("id") + " "
                        + rs.getString("email"));
            }
        }
    }
}
```

Ứng dụng **chỉ có hai tên cột hợp lệ** do code quyết định; chuỗi bất kỳ từ người dùng không bao giờ được nối trực tiếp vào SQL. Từ khóa `ASC`/`DESC` cũng chỉ được tạo từ hai hằng số. Nếu tham số `sortBy` có thể là `null`, cần kiểm tra `null` trước `switch` hoặc đặt giá trị mặc định rõ ràng.

Nguyên tắc tương tự áp dụng cho tên bảng, schema, alias, hàm SQL hoặc điều kiện nối động. Nếu không thể dùng placeholder cho một phần cấu trúc, **chỉ tạo nó từ các lựa chọn đã kiểm tra**. Quy tắc quote tên định danh có thể khác giữa DBMS nên không có một phép escape tự viết nào đảm bảo an toàn và đúng cho mọi sản phẩm.

## 7. Danh sách `IN` biến độ dài: tạo placeholder, không ghép giá trị

Một truy vấn cần tìm nhiều bản ghi theo các ID mà người dùng chọn. SQL có thể cần số dấu `?` thay đổi theo kích thước danh sách. **Tạo động số lượng placeholder** là hợp lý vì chính ứng dụng kiểm soát cấu trúc đó:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public static List<Long> findIds(
        Connection connection, List<Long> ids) throws SQLException {

    if (ids == null) {
        throw new IllegalArgumentException("ids khong duoc null");
    }
    if (ids.isEmpty()) {
        return List.of(); // Khong tao bieu thuc IN ().
    }
    if (ids.size() > 500 || ids.contains(null)) {
        throw new IllegalArgumentException("Danh sach ID khong hop le");
    }

    String placeholders = String.join(
            ", ", Collections.nCopies(ids.size(), "?"));
    String sql = "SELECT id FROM app_account WHERE id IN (" +
                 placeholders + ") ORDER BY id";

    List<Long> found = new ArrayList<>();
    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        for (int i = 0; i < ids.size(); i++) {
            statement.setLong(i + 1, ids.get(i));
        }

        try (ResultSet result = statement.executeQuery()) {
            while (result.next()) {
                found.add(result.getLong("id"));
            }
        }
    }
    return found;
}
```

Giả sử `ids = List.of(10L, 20L, 30L)`, ứng dụng tạo:

```sql
SELECT id FROM app_account WHERE id IN (?, ?, ?) ORDER BY id;
```

Ba giá trị `10`, `20`, `30` được truyền riêng qua `setLong()`. Ví dụ chọn giới hạn 500 ID như một **quy tắc minh họa của ứng dụng**, không phải giới hạn chung của JDBC. Từng DBMS có giới hạn số tham số hoặc độ dài SQL riêng; với danh sách rất lớn, cân nhắc batch, bảng tạm, array parameter hoặc kỹ thuật đặc thù được driver hỗ trợ.

**Không** dùng `ids.toString()` hoặc `String.join()` trên các giá trị từ request để đưa trực tiếp vào `IN (...)`. Nếu cần danh sách cấu trúc động, thay đổi **số dấu `?`**, không thay giá trị vào chuỗi SQL.

## 8. Tìm kiếm với `LIKE`: tham số hóa chưa quyết định nghĩa của ký tự đại diện

`PreparedStatement` ngăn một chuỗi đầu vào thay đổi cú pháp SQL, nhưng ký tự `%` và `_` vẫn là **wildcard có ý nghĩa trong `LIKE`**. Điều này không nhất thiết là SQL injection; đó là vấn đề **ngữ nghĩa tìm kiếm**.

Ví dụ:

```java
String sql = "SELECT id FROM app_account WHERE email LIKE ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "%" + keyword + "%");
    // ...
}
```

Nếu `keyword` chứa `%`, người dùng có thể khiến điều kiện khớp nhiều hàng hơn dự kiến. Nếu ứng dụng muốn tìm đúng chuỗi con **bao gồm cả ký tự `%` và `_` theo nghĩa ký tự thông thường**, cần escape wildcard theo dialect SQL đang dùng.

Ví dụ với cú pháp `LIKE ... ESCAPE '!'` được DBMS hỗ trợ:

```java
String rawKeyword = userInput;
String escapedKeyword = rawKeyword
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");

String sql =
        "SELECT id, email FROM app_account " +
        "WHERE email LIKE ? ESCAPE '!'";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "%" + escapedKeyword + "%");
    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getString("email"));
        }
    }
}
```

Đoạn mã giả định `rawKeyword` khác `null` và `connection` hợp lệ. Quy tắc `ESCAPE` và việc phân biệt chữ hoa/chữ thường thay đổi theo DBMS, collation và kiểu cột. **Escape wildcard nhằm đạt đúng ý nghĩa tìm kiếm**, còn **ràng buộc tham số** mới là cơ chế tách dữ liệu khỏi cú pháp SQL.

## 9. Đầu vào từ nơi khác vẫn là dữ liệu không đáng tin

Không chỉ văn bản gõ trên giao diện mới có thể gây SQL injection. Dữ liệu còn đến từ:

- Tham số HTTP, query string và JSON request.
- Tệp CSV/Excel, nội dung nhập từ đối tác hoặc hệ thống khác.
- Hàng trong database đã được lưu từ trước.
- Message queue, webhook và dữ liệu đồng bộ nền.

Ví dụ, một chuỗi có ký tự SQL đặc biệt được lưu hợp lệ trong cột `display_name`. Lần đọc sau, nếu ứng dụng lấy chuỗi đó rồi **nối vào truy vấn SQL khác**, lỗ hổng vẫn xuất hiện. Đây thường được gọi là **second-order SQL injection**: dữ liệu nguy hiểm được lưu ở một bước và trở thành cú pháp ở bước sau.

Giữ nguyên nguyên tắc `PreparedStatement` **tại mọi điểm xây dựng SQL**, kể cả khi giá trị đến từ database nội bộ. Đầu vào “đã qua kiểm tra” hoặc “đến từ hệ thống tin cậy” không mặc định an toàn khi đưa vào cấu trúc lệnh.

## 10. Tham số hóa không thay thế các kiểm soát khác

`PreparedStatement` giải quyết rất hiệu quả **ranh giới cú pháp/giá trị**, nhưng ứng dụng còn cần những kiểm soát riêng:

| Nhu cầu | Phương pháp bổ sung | Vì sao vẫn cần? |
| --- | --- | --- |
| Quyền đọc/sửa/xóa | Xác thực, phân quyền ở ứng dụng và DBMS | Một câu SQL an toàn về cú pháp vẫn có thể lấy dữ liệu trái phép |
| Giá trị hợp lệ | Kiểm tra độ dài, miền số, định dạng và quy tắc nghiệp vụ | Giá trị tham số có thể hợp lệ về SQL nhưng sai nghiệp vụ |
| Toàn vẹn dữ liệu | Khóa, `NOT NULL`, `CHECK`, `FOREIGN KEY` | Chặn dữ liệu không hợp lệ kể cả khi ghi từ nguồn khác |
| Tải hệ thống | Giới hạn kích thước danh sách, phân trang, timeout | Giá trị đầu vào vẫn có thể gây truy vấn quá tốn tài nguyên |
| Giao dịch | `setAutoCommit(false)`, `commit()`, `rollback()` khi cần | Hai thao tác đúng cú pháp có thể cần tính nguyên tử |
| Khả năng quan sát | Log mẫu truy vấn, mã lỗi, thời gian, số hàng | Cần chẩn đoán lỗi mà không lộ bí mật |

Ví dụ, một API nhận `accountId` không nên cho phép ai biết ID cũng đọc được mọi tài khoản chỉ vì truy vấn sử dụng `WHERE id = ?`. Ứng dụng phải áp dụng quy tắc quyền truy cập theo người dùng hiện tại, và DBMS nên cấp **quyền tối thiểu** cho tài khoản kết nối.

Không ghi nguyên mật khẩu, token hoặc dữ liệu cá nhân vào log. Nếu ghi log câu SQL và tham số để chẩn đoán, cần tuân thủ chính sách bảo vệ dữ liệu; nhiều thư viện hỗ trợ che giấu giá trị nhạy cảm.

## 11. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ghép trực tiếp `input` vào `WHERE` | Giá trị có thể thay đổi biểu thức SQL | Viết `WHERE col = ?` và dùng `setXxx()` |
| Viết `WHERE email = '?'` | Dấu `?` bị coi là ký tự trong chuỗi SQL | Để `?` độc lập, không đặt trong dấu nháy |
| Gọi `setString(1, "id DESC")` để chọn `ORDER BY` | Không biến chuỗi thành tên cột và từ khóa SQL | Ánh xạ lựa chọn sang đoạn SQL cố định |
| Ghép danh sách ID bằng `ids.toString()` | Không kiểm soát cú pháp và kiểu giá trị | Sinh đúng số placeholder rồi bind từng ID |
| Nghĩ `LIKE ?` sẽ khớp ký tự `%` theo nghĩa nguyên văn | Kết quả tìm kiếm rộng hơn mong đợi | Escape wildcard theo semantics DBMS nếu cần |
| Dùng `= ?` với tham số `NULL` để tìm hàng `NULL` | Không khớp do logic ba giá trị của SQL | Chọn `IS NULL` trong SQL cấu trúc |
| Bỏ kiểm tra quyền vì đã có `PreparedStatement` | Người dùng vẫn có thể truy cập dữ liệu không được phép | Kiểm soát quyền độc lập với SQL injection |
| Tin rằng chỉ dữ liệu từ web mới nguy hiểm | Dữ liệu từ database/file có thể được chèn vào SQL về sau | Parameterize tại mọi chỗ thực thi |
| Tự escape dấu nháy thay cho binding | Dễ sai quy tắc dialect, encoding, escape | Dùng `PreparedStatement` cho giá trị |
| Đánh đồng tham số hóa với hiệu năng luôn nhanh hơn | Kỳ vọng sai về execution plan và driver | Đo đạc theo DBMS, driver và tải thực tế |

## 12. Cách tổ chức mã để giữ cấu trúc SQL rõ ràng

Một kiến trúc dễ bảo trì thường có:

1. **Lớp service/controller** nhận yêu cầu, kiểm tra các lựa chọn nghiệp vụ và quyền truy cập.
2. **Lớp repository/DAO** quyết định câu SQL nào được thực thi và phần cấu trúc động nào nằm trong danh sách cho phép.
3. **`PreparedStatement`** truyền tất cả giá trị bên ngoài bằng `setXxx()`.
4. **`DataSource`/`Connection`** cấp phát và quản lý tài nguyên; `try-with-resources` đóng statement/result set.
5. **DBMS** áp dụng quyền, constraint và transaction phù hợp.

Ví dụ từ URL có `?sort=email&descending=true`, controller chỉ chuyển hai giá trị đó thành một kiểu lựa chọn hợp lệ. Repository ánh xạ `email` thành cột SQL cố định, `true` thành chuỗi cố định `DESC`, rồi bind các điều kiện tìm kiếm khác qua `PreparedStatement`. Tên cột và từ khóa **không bao giờ được lấy nguyên văn từ URL**.

Đây là cách làm rõ ranh giới giữa **cấu trúc do lập trình viên kiểm soát** và **giá trị từ người dùng**, kể cả khi ứng dụng cần xây dựng một phần SQL động.

## 13. Tự kiểm tra kiến thức

**Câu 1.** Người dùng nhập `' OR '1'='1` vào ô email. Sự khác biệt giữa ghép chuỗi SQL và `setString(1, email)` là gì?

*Gợi ý:* Ghép chuỗi có thể biến đầu vào thành toán tử `OR`; `setString` truyền nguyên chuỗi như một giá trị email để so sánh.

**Câu 2.** Có thể viết `SELECT * FROM ? WHERE id = ?` rồi bind `"app_account"` vào vị trí đầu tiên không?

*Gợi ý:* Không. Placeholder dành cho giá trị, không phải tên bảng. Tên bảng phải được xác định bởi mã ứng dụng hoặc một danh sách cho phép.

**Câu 3.** Danh sách tìm kiếm có 4 ID. Nên tạo `IN (1, 2, 3, 4)` bằng nối chuỗi hay `IN (?, ?, ?, ?)`?

*Gợi ý:* Tạo bốn placeholder, rồi gọi `setLong` bốn lần; xử lý riêng trường hợp danh sách rỗng.

**Câu 4.** Tại sao `WHERE nickname LIKE ?` có thể cần escape wildcard dù đã dùng `PreparedStatement`?

*Gợi ý:* Tham số hóa phòng đầu vào biến thành cú pháp SQL, còn `%` và `_` vẫn mang ý nghĩa ký tự đại diện trong mẫu `LIKE`.

**Câu 5.** Dữ liệu lấy từ một bảng nội bộ đã được “lưu an toàn”. Có thể nối trực tiếp nó vào câu SQL khác không?

*Gợi ý:* Không nên. Giá trị đọc từ database vẫn phải được bind làm tham số nếu xuất hiện ở vị trí giá trị của truy vấn mới.

**Câu 6.** `PreparedStatement` đã ngăn SQL injection trong điều kiện `WHERE id = ?`. Người dùng có mặc nhiên được phép xem bản ghi với mọi ID không?

*Gợi ý:* Không. Phải kiểm tra phân quyền và điều kiện nghiệp vụ độc lập với việc tham số hóa.

## Ghi nhớ

Trong JDBC, **`PreparedStatement` là công cụ chính để giữ giá trị dữ liệu tách khỏi cấu trúc SQL**. Viết mẫu SQL với các dấu `?` ở vị trí giá trị, rồi truyền chúng qua `setXxx()`; không nối nguyên đầu vào vào câu lệnh. Với phần cấu trúc động như tên cột, chiều sắp xếp hay tên bảng, dùng **tập lựa chọn cố định được phép**. Với `IN`, tạo số placeholder tương ứng; với `LIKE`, xử lý thêm wildcard nếu nghiệp vụ yêu cầu so khớp ký tự nguyên văn. Sau cùng, tiếp tục kiểm tra kiểu dữ liệu, quyền truy cập, transaction và tài nguyên JDBC như các trách nhiệm riêng.
