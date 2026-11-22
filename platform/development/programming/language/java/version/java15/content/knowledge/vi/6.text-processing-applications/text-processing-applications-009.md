# Tránh nối dữ liệu chưa kiểm tra vào cú pháp truy vấn hay markup

Ứng dụng Java thường tạo văn bản từ dữ liệu nhận qua biểu mẫu, API, file hoặc database: câu SQL, nội dung HTML, URL, JSON hay thông báo. **Không được ghép dữ liệu chưa tin cậy thẳng vào vị trí mà một hệ thống khác sẽ diễn giải thành cú pháp có khả năng thay đổi hành vi.** Một dấu nháy đơn có thể thay đổi điều kiện SQL; ký tự `<` và `>` trong bình luận có thể được trình duyệt hiểu như thẻ HTML.

Nguyên tắc này áp dụng cho **Java 15 trở lên**, bao gồm Java hiện đại. Phép nối `+`, `StringBuilder`, `String.format(...)`, `String.formatted(...)` (có từ Java 15) và text block `"""` **đều chỉ tạo chuỗi**. Chúng không tự làm sạch dữ liệu, không tự bind giá trị SQL và không tự mã hóa HTML. Muốn an toàn, cần chọn API xử lý dữ liệu phù hợp với **ngữ cảnh mà chuỗi sẽ được sử dụng**.

## 1. Dữ liệu nào cần coi là chưa tin cậy?

Nguồn dữ liệu bao gồm thông số URL, HTTP request, tên người dùng, bình luận, từ khóa tìm kiếm, file tải lên, message queue, API dịch vụ khác và cả nội dung đã được lưu trong database nhưng ban đầu do bên ngoài cung cấp. Một giá trị có thể hoàn toàn hợp lệ để hiển thị, nhưng lại có ký tự đặc biệt đối với SQL hoặc HTML.

Ví dụ:

```java
String username = "alice' OR '1'='1";
String comment = "<img src=x onerror=alert(1)>";
```

Hai biến chỉ là `String` trong Java. Vấn đề xảy ra **khi ứng dụng giao chúng cho bộ phân tích cú pháp SQL hoặc HTML ở vị trí không phù hợp**. Hãy tách hai khái niệm:

- **Dữ liệu**: giá trị cần tìm kiếm, lưu trữ hoặc hiển thị nguyên văn.
- **Cú pháp**: cấu trúc lệnh SQL, tên bảng/cột, thẻ HTML, thuộc tính, đoạn script và quy tắc URL do ứng dụng kiểm soát.

Quy tắc nền tảng là **để dữ liệu ở vị trí dữ liệu**, sử dụng cơ chế binding, escaping hoặc rendering của đích nhận; không biến nội dung nhập vào thành một đoạn lệnh mới.

## 2. Vì sao nối chuỗi vào SQL có thể gây lỗi?

Ví dụ **không an toàn**:

```java
String username = "alice' OR '1'='1";
String sql = "SELECT id FROM users WHERE username = '" + username + "'";

System.out.println(sql);
```

Kết quả:

```sql
SELECT id FROM users WHERE username = 'alice' OR '1'='1'
```

Chuỗi `OR '1'='1'` có thể bị database hiểu là một phần điều kiện lọc, thay vì là ký tự trong tên đăng nhập. Trong trường hợp này, dữ liệu không còn được tách khỏi cú pháp SQL.

Cách viết bằng text block hoặc `.formatted(...)` **vẫn gặp cùng vấn đề**:

```java
String sql = """
        SELECT id
        FROM users
        WHERE username = '%s'
        """.formatted(username); // KHÔNG AN TOÀN
```

`%s` chỉ thay bằng `String`; nó không thực hiện SQL escaping hay parameter binding. `String.format` và text block hữu ích cho việc trình bày, nhưng **không phải cơ chế chống SQL injection**.

Việc tự thay ký tự `'` thành một chuỗi escape bằng `replace(...)` không phải giải pháp chung đáng tin cậy vì quy tắc SQL khác nhau theo dialect và cấu hình. Với **giá trị dữ liệu** trong SQL, hãy dùng tham số.

## 3. Cách đúng: PreparedStatement bind giá trị SQL

JDBC cung cấp `java.sql.PreparedStatement`. Mẫu câu SQL do ứng dụng xác định chứa dấu `?` tại vị trí giá trị; đối số được truyền riêng bằng `setString`, `setInt`, `setLong` và các phương thức tương ứng.

Đoạn sau là **phương thức Java 17+ hợp lệ trong một class**, cần một `Connection` đang hoạt động, JDBC driver và bảng `users(id, username)` thực tế. Vì phải truy cập database nên đây là ví dụ tích hợp, **không có stdout cố định**:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class UserQueries {
    private UserQueries() {}

    public static void findIds(Connection connection, String username)
            throws SQLException {
        String sql = """
                SELECT id
                FROM users
                WHERE username = ?
                """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, username);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    System.out.println(rows.getLong("id"));
                }
            }
        }
    }
}
```

Trong ví dụ:

1. Text block chỉ chứa **cấu trúc SQL cố định** cùng dấu `?`.
2. `statement.setString(1, username)` gắn giá trị của biến ở vị trí tham số **thứ nhất**; JDBC đánh số tham số từ 1.
3. Giá trị có dấu nháy hoặc từ khóa SQL vẫn là **giá trị cần so sánh**, không trở thành đoạn điều kiện mới.
4. `try-with-resources` đóng `PreparedStatement` và `ResultSet` đúng cách.

Ví dụ trên là lớp Java có thể biên dịch với Java 17 trở lên, nhưng để gọi `findIds` cần một kết nối database thật. Không nên giả định rằng cú pháp `?` tự bảo vệ truy vấn chỉ vì xuất hiện trong một chuỗi: nó phát huy tác dụng khi được truyền cho `connection.prepareStatement(sql)` và được **bind** bằng API.

## 4. Ranh giới của tham số SQL: tên cột và ORDER BY

Tham số `?` dành cho **giá trị**, không thể tự do thay thế tên bảng, tên cột hoặc các từ khóa như `ASC`/`DESC`. Nếu người dùng được phép chọn cột sắp xếp, hãy **ánh xạ** lựa chọn của họ sang một số tên cột cố định do ứng dụng quyết định:

```java
public static String allowedSortColumn(String requested) {
    return switch (requested) {
        case "name" -> "username";
        case "recent" -> "created_at";
        default -> throw new IllegalArgumentException("Unsupported sort column");
    };
}
```

Sau đó có thể ghép một giá trị từ allowlist:

```java
String column = allowedSortColumn(requestedSort);
String sql = "SELECT id, username FROM users ORDER BY " + column;
```

Ở đây chỉ có `username` hoặc `created_at` do **code viết sẵn** xuất hiện trong cú pháp SQL, không phải chuỗi bất kỳ do người dùng nhập. Nếu chiều sắp xếp cũng thay đổi, ánh xạ input vào đúng hai lựa chọn cú pháp cố định `ASC`/`DESC`.

**Không dùng allowlist để thay thế bind cho giá trị trong `WHERE`.** Tùy chọn cấu trúc cần allowlist, còn giá trị tìm kiếm vẫn cần `PreparedStatement`.

Lưu ý: dùng `LIKE ?` với giá trị chứa `%` hoặc `_` vẫn tránh SQL injection, nhưng wildcard có thể khiến kết quả rộng hơn mong đợi. Nếu nghiệp vụ muốn tìm chuỗi nguyên văn, phải xử lý wildcard theo cách database hỗ trợ (ví dụ mệnh đề `ESCAPE`); đây là vấn đề về **ngữ nghĩa tìm kiếm**, tách biệt với an toàn cấu trúc SQL.

## 5. Markup: đừng để văn bản người dùng trở thành HTML

Ví dụ không an toàn nếu chuỗi kết quả được dùng làm HTML:

```java
String comment = "<img src=x onerror=alert(1)>";
String html = "<p>" + comment + "</p>";
```

Chuỗi kết quả là:

```html
<p><img src=x onerror=alert(1)></p>
```

Khi trình duyệt phân tích chuỗi đó như HTML, phần bình luận có thể được hiểu là thẻ `img` có thuộc tính xử lý sự kiện. Đây là một dạng rủi ro XSS (*cross-site scripting*) hay chèn markup.

Nếu mục đích là **hiển thị bình luận như văn bản** giữa hai thẻ HTML thường, nội dung cần được encode theo **HTML text context**. Giá trị:

```html
<p>&lt;img src=x onerror=alert(1)&gt;</p>
```

được hiển thị với dấu `<` và `>` như chữ, thay vì tạo thẻ `img`.

Trong ứng dụng thực tế, ưu tiên hệ thống template **tự escape output**, hoặc thư viện output encoder phù hợp. Nếu dữ liệu được chèn vào DOM bằng JavaScript, nên dùng thuộc tính `textContent` của **phần tử HTML thông thường**:

```javascript
const element = document.getElementById("comment");
element.textContent = userComment; // Đặt text node, không phân tích HTML.
```

Không chuyển thẳng `userComment` vào `innerHTML` nếu mong muốn chỉ hiển thị văn bản. Khi sử dụng `textContent`, truyền dữ liệu gốc; không cần encode HTML trước, vì API này đã xử lý như text.

## 6. HTML phải được xử lý theo ngữ cảnh

**Không có một hàm escape duy nhất đủ cho mọi vị trí trong HTML.** Tùy vị trí chèn, trình duyệt áp dụng những quy tắc khác nhau:

| Nơi dùng dữ liệu | Cách xử lý phù hợp |
| --- | --- |
| Phần văn bản giữa thẻ HTML thông thường, ví dụ `<p>... </p>` | Auto-escape của template hoặc HTML text encoder |
| Giá trị thuộc tính văn bản, ví dụ `title="..."` | Dùng HTML attribute encoder, bọc trong dấu nháy, cố định tên thuộc tính |
| URL trong `href`/`src` | Xác thực scheme/đích URL được phép **và** encode cho ngữ cảnh thuộc tính |
| Nội dung tạo bằng JavaScript DOM API | Dùng `textContent` cho text; tránh `innerHTML` với dữ liệu chưa tin cậy |
| Chuỗi trong `<script>`, xử lý sự kiện hoặc CSS | Tránh chèn trực tiếp; dùng API dữ liệu và encoder theo đúng ngữ cảnh nếu bất khả kháng |
| Nội dung HTML phong phú do người dùng viết | Dùng sanitizer được duy trì với allowlist các tag/attribute cho phép |
| Chuỗi JSON trả từ backend | Dùng JSON serializer, không tự ghép cú pháp, trả `Content-Type: application/json` |

Ví dụ, encode dấu `<` thành `&lt;` **không đủ** để bảo vệ mọi trường hợp: giá trị URL còn có scheme như `javascript:`; giá trị thuộc tính HTML có quy tắc dấu nháy; nội dung CSS/JavaScript có parser riêng. Dùng sai bộ mã hóa ở sai vị trí vẫn có thể tạo lỗi bảo mật.

Nếu thực sự muốn cho người dùng nhập HTML có thẻ, **encoding tất cả thành text sẽ làm mất khả năng hiển thị thẻ**. Khi đó dùng HTML sanitizer theo chính sách allowlist thay vì để nguyên toàn bộ HTML chưa kiểm tra.

## 7. Hàm xử lý HTML text chỉ để minh họa nguyên lý

Trong một **HTML text node thông thường**, các ký tự `&`, `<`, `>` mang ý nghĩa đặc biệt đối với parser. Ví dụ Java thuần sau cho thấy cách biến chúng thành entity:

```java
static String encodeHtmlTextOnly(String value) {
    return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;");
}
```

Phải thay `&` **trước**, nếu không ký tự `&` mới tạo trong `&lt;` có thể bị encode lại. Kết quả khi truyền `"<img src=x onerror=alert(1)>"` là `"&lt;img src=x onerror=alert(1)&gt;"`.

**Giới hạn bắt buộc:** đây là hàm minh họa **chỉ cho HTML text context**, không phải encoder HTML tổng quát và không nên dùng thay cho thư viện được duy trì trong dự án. Nó không giải quyết an toàn ở HTML attribute, URL, JavaScript, CSS hoặc trường hợp người dùng được phép nhập HTML phong phú. Trong sản phẩm thực tế nên ưu tiên template engine auto-escaping, thư viện như OWASP Java Encoder, hoặc sanitizer phù hợp.

Ngoài ra, output encoding không thay thế việc kiểm tra **giá trị** và **quyền truy cập**: một đường dẫn được encode chính xác vẫn có thể trỏ đến trang không được phép, và một tài khoản database cần tuân thủ quyền tối thiểu.

## 8. Chương trình Java 17+ độc lập có đầu ra chính xác

Chương trình sau **chỉ in chuỗi**, không thực thi SQL và không đưa HTML lên trình duyệt. Nó giúp nhận biết sự khác biệt giữa **cấu trúc cú pháp** và **giá trị dữ liệu**. Cách thi hành truy vấn đúng là ví dụ `PreparedStatement` ở mục 3.

Tạo file `InjectionBoundaryDemo.java` với UTF-8:

```java
public class InjectionBoundaryDemo {
    // Chỉ minh họa HTML text context, không thay thư viện encoder.
    private static String htmlText(String raw) {
        return raw.replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;");
    }

    public static void main(String[] args) {
        String username = "alice' OR '1'='1";
        String comment = "<img src=x onerror=alert(1)>";

        // Câu SQL không an toàn nếu đem thực thi.
        String unsafeSql =
                "SELECT id FROM users WHERE username = '" + username + "'";

        // Mẫu cố định: khi thực thi phải dùng PreparedStatement và setString.
        String query = """
                SELECT id FROM users WHERE username = ?""";

        String unsafeMarkup = "<p>" + comment + "</p>";
        String encodedMarkup = "<p>" + htmlText(comment) + "</p>";

        System.out.println("SQL unsafe: " + unsafeSql);
        System.out.println("SQL template: " + query);
        System.out.println("Parameter 1: " + username);
        System.out.println("HTML unsafe: " + unsafeMarkup);
        System.out.println("HTML text: " + encodedMarkup);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 InjectionBoundaryDemo.java
java InjectionBoundaryDemo
```

Đầu ra đã kiểm tra với JDK hiện đại:

```text
SQL unsafe: SELECT id FROM users WHERE username = 'alice' OR '1'='1'
SQL template: SELECT id FROM users WHERE username = ?
Parameter 1: alice' OR '1'='1
HTML unsafe: <p><img src=x onerror=alert(1)></p>
HTML text: <p>&lt;img src=x onerror=alert(1)&gt;</p>
```

Ở dòng `SQL template`, dấu `?` chỉ có ý nghĩa tham số SQL khi được dùng thông qua JDBC. Dòng `Parameter 1` chỉ in giá trị cần bind; chương trình không có database nên cũng không giả lập kết quả truy vấn.

## 9. Input validation cần đi kèm với cơ chế tại đích dùng

Kiểm tra dữ liệu giúp bảo đảm đúng quy tắc nghiệp vụ: độ dài trường, email hợp lệ, tên tệp thuộc dạng hỗ trợ, giá trị ngày giờ hay kiểu số. Tuy nhiên, **validation là điều kiện bổ sung, không thay thế binding hay encoding**.

Ví dụ:

- Tên hợp lệ có thể chứa dấu `'`, như `O'Reilly`; vẫn phải bind trong SQL.
- Bình luận về mã web có thể chứa `<script>`; vẫn cần hiển thị như text khi không cho phép markup.
- Một chuỗi đã lưu trong database có thể được dùng lại trong trang khác; vẫn cần encode khi xuất ra.
- Dù `username` đã vượt qua giới hạn độ dài, vẫn phải dùng `PreparedStatement`.
- Nếu cho phép chọn cột sắp xếp, chỉ chấp nhận các **tùy chọn đã ánh xạ** vào cú pháp do ứng dụng kiểm soát.

Luồng có thể hình dung:

```text
Dữ liệu ngoài → Kiểm tra kiểu / định dạng / nghiệp vụ
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Truy vấn SQL             Render ra HTML
       (bind giá trị)           (encode đúng ngữ cảnh)
             |                       |
             v                       v
       Database nhận            Browser nhận
       cú pháp cố định          markup do ứng dụng kiểm soát
```

## 10. Lỗi thường gặp và hướng khắc phục

| Nhầm lẫn | Thực tế | Cách làm đúng |
| --- | --- | --- |
| Text block an toàn hơn phép nối chuỗi về SQL injection | Text block chỉ tạo `String` | Viết SQL cố định, bind giá trị bằng `PreparedStatement` |
| `.formatted(userText)` đã escape HTML | `formatted` không có khả năng đó | Template auto-escape hoặc encoder đúng ngữ cảnh |
| `replace("'", "''")` đủ cho mọi database | Escape SQL phụ thuộc dialect/config | Dùng tham số cho giá trị |
| `?` thay được cả tên bảng và cột | Parameter marker đại diện cho giá trị | Ánh xạ allowlist cho SQL identifiers |
| Chỉ cần lọc input lúc nhập form | Dữ liệu sau đó có thể đi vào nhiều parser khác | Bảo vệ tại điểm sử dụng: SQL, HTML, URL, JSON |
| HTML text escaping dùng được cho mọi thuộc tính | Mỗi ngữ cảnh có quy tắc riêng | Chọn đúng encoder/validator |
| `textContent` và `innerHTML` tương đương | `innerHTML` phân tích HTML; `textContent` tạo text node | Dùng API khớp ý định |
| Đã encode URL như HTML là an toàn | URL scheme/đích vẫn có thể nguy hiểm | Xác thực URL và encode khi đưa vào HTML |
| Giá trị từ database luôn đáng tin | Dữ liệu đã lưu cũng có thể xuất phát từ người dùng | Tiếp tục kiểm soát theo ngữ cảnh |

## 11. Bài tập tự kiểm tra

Chọn cách xử lý tốt nhất cho các tình huống:

1. Tìm người dùng có tên `O'Reilly` bằng một truy vấn `WHERE username = ...`.
2. Hiển thị nguyên văn bình luận `<b>Hello</b>` trong một khối `<p>`, không cho phép người dùng tạo markup.
3. Cho phép chọn `sort=recent` để sắp xếp theo cột `created_at`.
4. Hiển thị đường dẫn người dùng cung cấp trong thuộc tính `href`.
5. Gọi `htmlTemplate.formatted(comment)` rồi trả chuỗi về client dưới dạng HTML.

**Đáp án:**

1. Dùng `PreparedStatement` và `setString`; dấu `'` phải được coi là dữ liệu.
2. Dùng HTML text encoding hoặc `textContent`; đừng để bình luận được parse thành thẻ `b`.
3. Ánh xạ `recent` sang tên cột cố định `created_at`, không nối trực tiếp input.
4. Kiểm tra scheme và đích được phép, rồi encode cho giá trị thuộc tính HTML được trích dẫn đúng cách.
5. `.formatted(...)` không mã hóa HTML; phải dùng template có auto-escape hoặc encoder theo đúng ngữ cảnh trước khi render.

## Tài liệu còn áp dụng

- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized queries, allowlist và giới hạn của escape thủ công.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): các ngữ cảnh HTML, `textContent`, output encoding và HTML sanitizer.
- [Oracle Java SE 25 — PreparedStatement API](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html): parameter binding và các phương thức JDBC.
- [Oracle Java SE 25 — String API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): String, `format`, `formatted`.