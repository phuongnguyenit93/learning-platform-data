# Bảo toàn định danh dạng chuỗi có số 0 đầu

## 1. Số 0 đầu có thể là một phần của định danh

Trong ứng dụng Java truy cập cơ sở dữ liệu quan hệ bằng **JDBC**, một giá trị trông như số chưa chắc là *số để tính toán*. Mã tài khoản `"0000456789"`, mã bưu chính `"00123"` hay mã hồ sơ `"0007"` có thể là **định danh**: các ký tự và thứ tự của chúng tạo nên danh tính của đối tượng. Vì thế, `"0007"` và `"7"` có thể là hai mã khác nhau theo quy tắc nghiệp vụ, dù cả hai biểu diễn cùng giá trị số học là `7`.

**Nguyên tắc:** Nếu không cần cộng, trừ, nhân, chia hay so sánh theo giá trị số học, và số 0 ở đầu có ý nghĩa, hãy xử lý giá trị đó như **chuỗi từ đầu đến cuối**: đầu vào → Java → tham số JDBC → cột SQL → `ResultSet` → đầu ra.

Ví dụ, giả sử hệ thống quy định mã tài khoản gồm đúng **10 chữ số ASCII**:

| Biểu diễn | Giá trị | Đánh giá |
| --- | --- | --- |
| Java `String` | `"0000456789"` | Giữ đủ 10 ký tự, đúng định dạng |
| Java `int` | `456789` | Đã mất bốn số 0 ở đầu |
| SQL `VARCHAR(10)` | `'0000456789'` | Lưu được nguyên chuỗi |
| SQL `INTEGER` / `BIGINT` | `456789` | Chỉ lưu giá trị số, không lưu số 0 đầu |

Độ dài **10** trong bài chỉ là một quy tắc ví dụ. Mã thực tế có thể có độ dài khác, chữ cái, dấu gạch ngang hoặc chữ số kiểm tra; hãy lấy quy tắc từ nghiệp vụ, không tự áp đặt tất cả định danh đều là chuỗi chỉ chứa chữ số.

## 2. Chọn đúng kiểu dữ liệu ở từng lớp

| Lớp | Nên dùng | Tránh khi cần giữ nguyên số 0 đầu |
| --- | --- | --- |
| Java/domain model | `String accountCode` | `int`, `long`, `BigInteger`, `BigDecimal` |
| Cơ sở dữ liệu | `VARCHAR(n)` hoặc kiểu văn bản phù hợp | `INTEGER`, `BIGINT`, `DECIMAL` cho định danh |
| Ghi qua JDBC | `PreparedStatement.setString(...)` | `setInt(...)`, `setLong(...)` |
| Đọc qua JDBC | `ResultSet.getString(...)` | `getInt(...)`, `getLong(...)` |
| JSON / API | `{"accountCode": "0000456789"}` | `{"accountCode": 456789}` |
| Nhập/xuất tệp | Cột được khai báo là **text/string** | Tự động suy kiểu số từ CSV hoặc bảng tính |

`VARCHAR(n)` thường thích hợp hơn `CHAR(n)` cho mã có độ dài biến thiên: `CHAR` có thể thêm khoảng trắng đệm, và cách trả về/so sánh khoảng trắng tùy hệ quản trị cơ sở dữ liệu. `VARCHAR` cũng không tự bảo đảm “đúng 10 chữ số”; cần thêm kiểm tra ở ranh giới ứng dụng và, khi phù hợp, ràng buộc tại cơ sở dữ liệu theo cú pháp của hệ quản trị đang dùng.

> Đổi kiểu lấy dữ liệu sang `getString()` **không cứu được** số 0 đầu nếu dữ liệu đã được lưu trong cột kiểu số. Khi ấy các ký tự số 0 ban đầu đã không còn trong dữ liệu.

## 3. Thiết kế bảng để lưu định danh dạng chuỗi

Với mã tài khoản 10 chữ số, có thể tạo bảng như sau:

```sql
CREATE TABLE account_codes (
    account_code VARCHAR(10) NOT NULL PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);
```

Một giá trị hợp lệ có dạng:

```sql
-- Ví dụ minh họa biểu diễn bằng literal SQL.
INSERT INTO account_codes (account_code, display_name)
VALUES ('0000456789', 'Nguyen An');

SELECT account_code, display_name
FROM account_codes
WHERE account_code = '0000456789';
```

Dấu nháy đơn trong SQL thể hiện đây là **chuỗi**. Với dữ liệu đầu vào từ người dùng hoặc ứng dụng, hãy dùng **`PreparedStatement` và tham số `?`** như phần tiếp theo, thay vì ghép trực tiếp giá trị vào câu SQL.

Khóa chính trên `account_code` giúp bảo đảm tính duy nhất và hỗ trợ tìm kiếm theo mã. Trong ví dụ này, `"0000456789"` phải được lưu và tra cứu đúng như vậy. Một chuỗi có độ dài ngắn hơn, chẳng hạn `"456789"`, không tự động trở thành mã 10 chữ số; nếu quy tắc thực tế yêu cầu đúng 10 ký tự, ứng dụng phải từ chối đầu vào đó.

## 4. Ghi và đọc nguyên vẹn qua JDBC

Ví dụ sau dùng `DataSource` để lấy kết nối, `PreparedStatement` để truyền tham số an toàn và `ResultSet.getString` để đọc mã. `DataSource` được cấu hình ở phần hạ tầng của ứng dụng; lớp này chỉ phụ trách thao tác với bảng đã tạo ở trên.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountCodeRepository {
    private final DataSource dataSource;

    public AccountCodeRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(String accountCode, String displayName)
            throws SQLException {
        requireAccountCode(accountCode);

        String sql = "INSERT INTO account_codes "
                   + "(account_code, display_name) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, accountCode);
            statement.setString(2, displayName);
            statement.executeUpdate();
        }
    }

    public String findAccountCode(String accountCode) throws SQLException {
        requireAccountCode(accountCode);

        String sql = "SELECT account_code FROM account_codes "
                   + "WHERE account_code = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, accountCode);

            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next()
                        ? resultSet.getString("account_code")
                        : null;
            }
        }
    }

    private static void requireAccountCode(String accountCode) {
        if (accountCode == null || !accountCode.matches("[0-9]{10}")) {
            throw new IllegalArgumentException(
                    "Mã tài khoản phải gồm đúng 10 chữ số ASCII");
        }
    }
}
```

Luồng sử dụng:

```java
String original = "0000456789";
AccountCodeRepository repository = new AccountCodeRepository(dataSource);

repository.insert(original, "Nguyen An");
String restored = repository.findAccountCode(original);

if (!original.equals(restored)) {
    throw new IllegalStateException("Mã tài khoản đã bị thay đổi");
}
```

Ví dụ gọi `insert` giả định bản ghi chưa tồn tại; gọi lại với cùng khóa chính sẽ phát sinh lỗi trùng khóa. Khi tìm không thấy bản ghi, `findAccountCode` trả về `null`. Ứng dụng thực tế có thể trả về `Optional<String>` hoặc một đối tượng domain để biểu diễn trường hợp không tìm thấy.

Các chi tiết cần chú ý:

1. **`setString(1, accountCode)`** truyền đủ ký tự, kể cả số 0 đầu. Chỉ mục tham số JDBC bắt đầu từ **1**.
2. **`getString("account_code")`** lấy giá trị cột văn bản dưới dạng chuỗi. Đừng đổi sang `getLong` hoặc `getInt` chỉ vì tất cả ký tự đều là chữ số.
3. **`try-with-resources`** đóng `ResultSet`, `PreparedStatement` và `Connection` kể cả khi xảy ra `SQLException`. Với connection pool, thao tác `close()` thường trả kết nối về pool theo cách `DataSource` được cấu hình.
4. **`matches("[0-9]{10}")`** kiểm tra toàn bộ chuỗi gồm đúng 10 chữ số từ `0` đến `9`. Đây là kiểm tra theo **quy tắc ví dụ**, không phải tiêu chuẩn chung cho mọi loại định danh.

## 5. Các lỗi làm mất số 0 đầu

### Chuyển chuỗi sang kiểu số rồi chuyển ngược lại

```java
String input = "0000456789";

long numeric = Long.parseLong(input);     // 456789
String damaged = Long.toString(numeric);  // "456789"

System.out.println(input.equals(damaged)); // false
```

`Integer.parseInt`, `Long.parseLong` hoặc các kiểu số học khác không giữ định dạng ký tự ban đầu. Với mã dài, chuyển đổi kiểu số còn có thể gây lỗi tràn phạm vi. Cũng không nên định dạng lại bằng `String.format("%010d", numeric)` để “sửa” dữ liệu khi chưa biết quy tắc độ dài: từ số `123` không thể xác định mã gốc là `"123"`, `"0123"` hay `"00123"`.

### Chọn cột kiểu số hoặc dùng sai setter

```java
// Sai khi account_code cần bảo toàn ký tự "0000456789":
statement.setLong(1, 456789L);

// Đúng với cột account_code VARCHAR(10):
statement.setString(1, "0000456789");
```

Không nên kỳ vọng driver JDBC hoặc cơ sở dữ liệu tự thêm số 0 đầu. Ngay cả khi truyền bằng `setString`, một **cột SQL kiểu số** vẫn có thể ép giá trị thành số và làm mất thông tin định dạng. Phải giữ đúng kiểu ở **cả hai phía**.

### Để hệ thống bên ngoài tự suy kiểu

Trong JSON, hãy xuất mã dưới dạng chuỗi:

```json
{
  "accountCode": "0000456789"
}
```

Khi nhập CSV hoặc dữ liệu qua phần mềm bảng tính, việc đặt giá trị trong dấu nháy đôi của CSV **không luôn ngăn** phần mềm tự nhận diện nó là số. Phải khai báo cột nhập là văn bản, kiểm tra dữ liệu sau nhập và bảo toàn chuỗi qua tất cả bước trung gian. Khi xuất dữ liệu cho hệ thống khác, hợp đồng API hoặc định dạng tệp cũng cần quy định rõ **kiểu chuỗi**.

### Tự ý chỉnh sửa giá trị định danh

Không tự động gọi `trim()`, thêm số 0, bỏ dấu gạch hay đổi chữ hoa/thường nếu các thao tác đó chưa được quy tắc nghiệp vụ cho phép. Nếu mã chỉ hợp lệ khi gồm 10 chữ số ASCII như ví dụ, hãy **từ chối** chuỗi sai định dạng và yêu cầu sửa đầu vào; âm thầm sửa có thể biến một mã thành mã khác.

## 6. So sánh, tìm kiếm và sắp xếp

Tra cứu nên so sánh chuỗi với chuỗi:

```sql
SELECT account_code
FROM account_codes
WHERE account_code = ?;
```

Gắn tham số bằng `setString`. Tránh ép `CAST(account_code AS INTEGER)` hay ép tham số thành số trong điều kiện tra cứu: việc ép kiểu có thể khiến nhiều định danh khác nhau trở nên không phân biệt được, gây lỗi khi mã quá dài và ảnh hưởng khả năng dùng chỉ mục.

**Sắp xếp chuỗi** khác sắp xếp số. Với các mã cùng độ dài chỉ gồm chữ số ASCII, thứ tự từ điển thường trùng thứ tự số học (ví dụ `"0002" < "0010"`). Với độ dài khác nhau, `"10"` có thể đứng trước `"2"` khi sắp xếp như chuỗi. Hãy chọn cách sắp xếp theo yêu cầu nghiệp vụ, nhưng không đổi kiểu lưu trữ chỉ để có thứ tự số.

Với mã có chữ cái hoặc khoảng trắng, cách so sánh còn phụ thuộc **collation** của cơ sở dữ liệu (phân biệt chữ hoa/thường, khoảng trắng cuối, v.v.). Nếu hệ thống yêu cầu so khớp chính xác từng ký tự, hãy xác định rõ quy tắc chuẩn hóa và cấu hình so sánh phù hợp trên hệ quản trị đang dùng. Ví dụ 10 chữ số ASCII ở đây tránh được phần lớn các trường hợp mơ hồ đó.

## 7. Nếu dữ liệu đã bị mất số 0 đầu

Giả sử cột `BIGINT` hiện lưu `456789`. Từ dữ liệu này **không thể khôi phục chắc chắn** chuỗi gốc: `"456789"`, `"0456789"` và `"0000456789"` đều có thể tạo ra cùng số đó. Có hai hướng xử lý:

- **Có nguồn gốc đáng tin cậy:** đọc lại mã từ bản ghi gốc, hệ thống nguồn hoặc bản sao lưu còn lưu chuỗi đầy đủ; đối chiếu trước khi chuyển sang cột văn bản.
- **Có quy tắc độ dài cố định được xác nhận:** có thể tạo mã theo quy tắc, chẳng hạn chèn số 0 bên trái đến đúng 10 chữ số, nhưng đây là **quy tắc xây dựng lại**, không phải chứng cứ về chuỗi gốc. Kiểm tra trùng mã, mã ngoại lệ và tác động tới các khóa liên kết trước khi cập nhật.

Khi chuyển schema từ cột số sang cột văn bản, chỉ `CAST` giá trị số sang `VARCHAR` thường vẫn cho `"456789"`; việc đổi kiểu đơn thuần không khôi phục số 0 bị mất.

## 8. Kiểm thử bảo toàn dữ liệu qua toàn bộ hành trình

Một bài kiểm tra tích hợp nên ghi mã qua `setString`, đọc lại qua `getString`, rồi so sánh **chính xác chuỗi** bằng `String.equals`. Hãy kiểm tra ít nhất những tình huống sau:

| Đầu vào | Kỳ vọng với quy tắc 10 chữ số của ví dụ |
| --- | --- |
| `"0000456789"` | Hợp lệ; đọc lại đúng `"0000456789"` |
| `"0000000000"` | Hợp lệ; không biến thành `"0"` |
| `"456789"` | Bị từ chối do chỉ có 6 chữ số |
| `"000045678A"` | Bị từ chối do chứa chữ cái |
| `" 0000456789"` | Bị từ chối do có khoảng trắng |
| `null` | Bị từ chối trước khi thao tác JDBC |

Ngoài đường JDBC, cần kiểm tra vòng đi qua API, thông điệp và tệp nhập/xuất nếu ứng dụng có các kênh đó. Đặc biệt, hãy thử với **nhiều số 0 ở đầu**, không chỉ một số 0, vì lỗi chuyển kiểu có thể không lộ rõ với dữ liệu thử không có số 0 đầu.

**Ghi nhớ:** Định danh là một giá trị nhận diện, không phải đại lượng. Với JDBC, sự nhất quán giữa `String` ở Java, `VARCHAR` ở SQL, `PreparedStatement.setString` khi ghi và `ResultSet.getString` khi đọc là nền tảng để giữ nguyên những số 0 đầu; việc xác thực và kiểm thử giúp bảo đảm tính đúng đắn trên toàn bộ hệ thống.
