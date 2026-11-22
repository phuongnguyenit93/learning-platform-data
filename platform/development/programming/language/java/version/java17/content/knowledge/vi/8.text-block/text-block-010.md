# Tổ chức mẫu JSON, SQL và HTML dễ đọc bằng Text Block trong Java 17

## 1. Text block giải quyết vấn đề gì?

Khi một chương trình Java cần tạo nội dung nhiều dòng như JSON, câu lệnh SQL hoặc tài liệu HTML, cách viết chuỗi thông thường thường khiến mã nguồn khó đọc:

~~~java
String json = "{\n"
        + "  \"name\": \"Lan\",\n"
        + "  \"active\": true\n"
        + "}";
~~~

Mỗi dòng phải ghép bằng dấu cộng, ký tự xuống dòng phải viết thành `\n`, và dấu nháy kép trong nội dung phải escape. Khi mẫu lớn lên, cấu trúc JSON hoặc HTML bị che khuất bởi cú pháp chuỗi Java.

**Text block** cho phép viết trực tiếp chuỗi nhiều dòng giữa cặp dấu ba nháy kép `"""`. Tính năng này được hoàn thiện và trở thành tính năng ổn định từ Java 15, vì vậy dùng bình thường trong **Java 17**, không cần bật preview:

~~~java
String json = """
        {
          "name": "Lan",
          "active": true
        }
        """;
~~~

Nội dung nhìn gần với định dạng JSON thực tế hơn. Text block vẫn tạo ra một `String`; nó không tự phân tích JSON, không tự chạy SQL, không render HTML và cũng không tự escape dữ liệu động.

Trong bài này, ta sử dụng text block để tổ chức ba loại nội dung thường gặp:

- **JSON:** cấu trúc dữ liệu trao đổi giữa ứng dụng và API.
- **SQL:** câu lệnh truy vấn nhiều dòng, dễ đọc và dễ rà soát.
- **HTML:** cấu trúc trang hoặc email HTML có nhiều phần tử lồng nhau.

Điểm quan trọng là phân biệt **định dạng chuỗi trong mã nguồn** với **quy tắc an toàn của định dạng đích**. Text block giúp phần mẫu dễ đọc; JSON serializer, JDBC `PreparedStatement` và HTML escaping vẫn chịu trách nhiệm xử lý dữ liệu đúng cách.

## 2. Cú pháp cơ bản

Một text block có dạng:

~~~java
String message = """
    Đây là dòng thứ nhất.
    Đây là dòng thứ hai.
    Đây là dòng thứ ba.
    """;
~~~

Một số quy tắc cú pháp:

1. Dấu mở `"""` phải được theo sau bởi một ký tự kết thúc dòng. Không đặt nội dung ngay sau dấu mở trên cùng một dòng.
2. Nội dung có thể trải trên nhiều dòng và chứa dấu nháy kép đơn hoặc kép đôi mà không cần escape như chuỗi thông thường.
3. Dấu đóng `"""` xác định kết thúc nội dung. Vị trí thụt lề của dấu đóng có ảnh hưởng đến việc loại bỏ khoảng trắng đầu dòng.
4. Text block là biểu thức tạo ra một `String`, nên có thể gán biến, trả về từ phương thức hoặc truyền làm đối số như mọi chuỗi khác.

Ví dụ **không hợp lệ**:

~~~java
// Không hợp lệ: dấu mở phải có line terminator ngay sau nó.
String invalid = """Hello""";
~~~

Viết đúng:

~~~java
String valid = """
        Hello
        """;
~~~

### Text block không phải một loại dữ liệu riêng

~~~java
String text = """
        Java
        17
        """;

System.out.println(text instanceof String); // true
~~~

Bạn vẫn dùng được các phương thức của `String`, ví dụ `length()`, `contains()`, `strip()` hoặc `formatted()`. Kiểu dữ liệu của biến là `String`, không phải `TextBlock`.

## 3. Khoảng trắng đầu dòng và vị trí dấu đóng

Đây là phần cần hiểu rõ nhất khi tạo mẫu có thụt lề. Trình biên dịch Java áp dụng quy tắc **incidental indentation** (*thụt lề không mang ý nghĩa nội dung*) để loại bỏ phần thụt lề chung, nhờ đó mã nguồn có thể được đặt trong một lớp mà chuỗi kết quả không bị thêm toàn bộ khoảng trắng của mã Java.

Ví dụ:

~~~java
String html = """
        <section>
            <h1>Orders</h1>
        </section>
        """;
~~~

Giá trị chuỗi có dạng:

~~~text
<section>
    <h1>Orders</h1>
</section>
~~~

Bốn dấu cách chung trước mỗi dòng nội dung đã được loại bỏ; phần thụt lề tương đối của `<h1>` vẫn được giữ.

### 3.1. Dấu đóng tham gia xác định mức thụt lề

Hãy so sánh hai cách đặt dấu đóng.

**Dấu đóng thẳng hàng với nội dung:**

~~~java
String first = """
        alpha
        beta
        """;
~~~

Kết quả:

~~~text
alpha
beta
~~~

**Dấu đóng ở cột đầu tiên:**

~~~java
String second = """
        alpha
        beta
""";
~~~

Trong trường hợp thứ hai, dấu đóng không có khoảng trắng đầu dòng. Mức thụt lề chung nhỏ nhất trở thành 0, nên phần tám dấu cách trước `alpha` và `beta` được giữ lại trong giá trị chuỗi.

Do đó, khi muốn nội dung text block không có khoảng trắng đầu dòng ngoài ý muốn, hãy đặt dấu đóng ở mức thụt lề phù hợp với nội dung.

### 3.2. Dòng trống và khoảng trắng cuối dòng

Java xử lý các dòng trống khi tính mức thụt lề; dòng chỉ chứa khoảng trắng không làm mức thụt lề chung bị giảm theo cách một dòng có nội dung sẽ làm. Khoảng trắng cuối dòng được loại bỏ khỏi nội dung text block. Điều này giúp mẫu không vô tình mang theo các khoảng trắng do căn chỉnh trong editor.

Nếu một khoảng trắng ở cuối dòng **có ý nghĩa**, không nên gõ một dấu cách rồi hy vọng editor giữ nguyên nó. Hãy biểu diễn tường minh bằng escape `\s`:

~~~java
String withTrailingSpace = """
        value\s
        next
        """;
~~~

Ký tự `\s` tạo ra đúng một dấu cách trong chuỗi kết quả. Đây là escape sequence của Java, không phải ký hiệu đặc biệt của JSON hay SQL.

### 3.3. Chuẩn hóa ký tự xuống dòng

Trong text block, ký tự kết thúc dòng của nội dung được chuẩn hóa thành line feed `\n` trong chuỗi kết quả. Vì vậy, mã nguồn có thể được checkout trên Windows hoặc Linux mà nội dung chuỗi không phụ thuộc trực tiếp vào kiểu line ending của file.

Nếu một giao thức hoặc định dạng đầu ra yêu cầu CRLF cụ thể, hãy chủ động chuyển đổi line ending ở bước xuất dữ liệu. Đừng giả định text block sẽ giữ nguyên CRLF từ file nguồn.

## 4. Escape sequence trong text block

Text block giảm nhu cầu escape dấu nháy kép, nhưng **không tắt quy tắc escape của Java**. Các escape sequence vẫn được xử lý để tạo chuỗi kết quả.

| Viết trong mã nguồn | Ký tự/giá trị trong `String` |
|---|---|
| `\n` | Line feed (xuống dòng). |
| `\t` | Tab. |
| `\"` | Một dấu nháy kép. |
| `\\` | Một dấu gạch chéo ngược `\`. |
| `\s` | Một dấu cách U+0020. |
| `\` ngay trước line terminator | Nối dòng, bỏ line terminator và phần thụt lề đầu dòng tiếp theo sau xử lý. |

### 4.1. Nối dòng bằng dấu gạch chéo ngược

Khi muốn trình bày một dòng dài thành nhiều dòng trong mã nguồn nhưng kết quả chỉ là một dòng, dùng line continuation:

~~~java
String sql = """
        SELECT id, \
        status, \
        created_at
        FROM orders
        """;
~~~

Phần `SELECT` trong kết quả là một dòng:

~~~text
SELECT id, status, created_at
FROM orders
~~~

Line continuation xóa line terminator ngay sau dấu `\`; nó không tự thêm dấu cách. Vì vậy, nếu cần ngăn hai từ dính vào nhau, hãy đặt dấu cách **trước** dấu `\` như ví dụ trên. Với SQL, JSON hoặc HTML, thường nên để mỗi dòng logic trên một dòng kết quả để dễ đọc và debug; chỉ nối khi định dạng đích yêu cầu.

### 4.2. Dấu gạch chéo ngược trong JSON

JSON dùng dấu `\` để biểu diễn các escape như `\"`, `\\`, `\n`. Nhưng text block cũng xử lý escape của Java. Vì thế, muốn kết quả chuỗi chứa hai ký tự `\` và `n`, mã nguồn Java phải viết `\\n`.

Ví dụ:

~~~java
String json = """
        {
          "message": "first line\\nsecond line",
          "path": "C:\\\\temp\\\\orders"
        }
        """;
~~~

Trong chuỗi Java kết quả, phần JSON có nội dung:

~~~json
{
  "message": "first line\nsecond line",
  "path": "C:\\temp\\orders"
}
~~~

Ở đây, `\n` và `\\` vẫn là escape của **JSON** khi chuỗi được phân tích. Java đã xử lý một lớp escape trước đó:

- Java source `\\n` → Java String chứa `\n` (hai ký tự gạch chéo ngược và chữ n) → JSON parser hiểu đó là line feed bên trong giá trị.
- Java source `\\\\` → Java String chứa `\\` (hai dấu gạch chéo ngược) → JSON parser hiểu đó là một dấu `\` trong đường dẫn.

Đây là nguyên nhân thường gặp khi mẫu JSON có vẻ đúng trong mã nguồn nhưng khi parse lại sai: cần phân biệt escape của **ngôn ngữ Java** với escape của **JSON**.

### 4.3. Dấu nháy kép trong JSON, HTML và SQL

Trong text block, các dấu nháy kép đơn và đôi có thể viết trực tiếp:

~~~java
String json = """
        {
          "title": "Java 17",
          "description": "Text blocks make multiline strings readable"
        }
        """;
~~~

Bạn không cần viết `\"title\"` chỉ để bao quanh tên thuộc tính JSON. Java chỉ cần chú ý chuỗi ba dấu nháy kép liên tiếp dùng để đóng text block; nếu nội dung thực sự cần chứa chuỗi `"""`, phải escape ít nhất một dấu nháy để không vô tình kết thúc text block.

## 5. Tổ chức mẫu JSON

JSON thường có nhiều cấp object, array và giá trị nên text block làm mẫu dễ đọc hơn rõ rệt.

### 5.1. Mẫu JSON tĩnh

~~~java
String response = """
        {
          "id": 105,
          "status": "PAID",
          "items": [
            {
              "sku": "BOOK-17",
              "quantity": 2
            },
            {
              "sku": "PEN-02",
              "quantity": 5
            }
          ],
          "active": true
        }
        """;
~~~

Khi dữ liệu hoàn toàn cố định, text block là cách viết đơn giản. Bạn có thể truyền `response` cho HTTP client hoặc thư viện JSON để parse/kiểm tra.

### 5.2. Không ghép dữ liệu động tùy tiện vào JSON

Một cách dễ nghĩ tới là dùng `formatted()`:

~~~java
String json = """
        {
          "customer": "%s",
          "status": "PAID"
        }
        """.formatted(customerName);
~~~

Đoạn này chỉ an toàn nếu `customerName` là dữ liệu đã được kiểm soát và chắc chắn không chứa ký tự làm hỏng JSON. `String.formatted()` chỉ thay placeholder `%s`; nó **không escape chuỗi theo JSON**, không kiểm tra JSON và không biến dữ liệu thành giá trị JSON hợp lệ.

Ví dụ nếu `customerName` chứa dấu nháy kép, ký tự xuống dòng hoặc dấu gạch chéo ngược, chuỗi kết quả có thể trở thành JSON không hợp lệ hoặc mang cấu trúc khác dự kiến. Không giải quyết bằng cách tự thay vài ký tự theo cảm tính.

Với dữ liệu động trong ứng dụng thực tế, hãy dùng **JSON serializer** (ví dụ Jackson hoặc Gson) để thư viện xử lý việc escape và biểu diễn đúng kiểu dữ liệu. Text block phù hợp để:

- Viết payload mẫu cố định trong tài liệu, ví dụ hoặc test fixture.
- Tạo JSON tĩnh trong một công cụ nội bộ có đầu vào kiểm soát.
- Giữ cấu trúc minh họa gần với JSON thực tế để người đọc dễ so sánh.

### 5.3. JSON có giá trị động: phân biệt mẫu và serializer

Nếu cần tạo object response từ dữ liệu:

~~~java
record CustomerResponse(long id, String name, boolean active) {
}
~~~

hãy chuyển object đó qua thư viện JSON mà dự án đang dùng thay vì chèn từng trường vào text block. Serializer sẽ xử lý dấu nháy, escape, `null`, số, boolean, collection và object lồng nhau theo đúng quy tắc JSON.

Text block không thay thế thư viện JSON. JDK 17 không có một API JSON tổng quát trong Java SE để tự động serialize mọi object thành JSON.

### 5.4. Khi nào cần `formatted()`?

`String.formatted()` có từ Java 15 và dùng được trong Java 17:

~~~java
String template = """
        {
          "service": "%s",
          "version": %d
        }
        """;

String example = template.formatted("orders", 17);
~~~

Nó hữu ích cho mẫu hiển thị hoặc dữ liệu đã được kiểm soát. Hãy nhớ:

- `%s`, `%d`, `%f` là placeholder của formatter Java, không phải cú pháp JSON.
- Ký tự `%` muốn xuất hiện nguyên văn trong format string phải viết `%%`.
- Thứ tự đối số phải khớp placeholder.
- `formatted()` không phải serializer và không tự escape giá trị theo JSON.

## 6. Tổ chức câu lệnh SQL nhiều dòng

SQL thường có nhiều mệnh đề `SELECT`, `FROM`, `JOIN`, `WHERE`, `GROUP BY`, `ORDER BY`. Text block giúp mỗi mệnh đề ở một dòng, dễ rà soát điều kiện và phép nối.

### 6.1. Mẫu SQL tĩnh

~~~java
String sql = """
        SELECT
            o.id,
            o.status,
            o.created_at,
            c.name AS customer_name
        FROM orders o
        JOIN customers c
            ON c.id = o.customer_id
        WHERE o.created_at >= DATE '2026-01-01'
          AND o.status <> 'CANCELLED'
        ORDER BY o.created_at DESC
        """;
~~~

Text block không kiểm tra cú pháp SQL; cơ sở dữ liệu và JDBC driver vẫn là nơi xác nhận câu lệnh có hợp lệ với dialect đang dùng hay không. Ví dụ trên minh họa cấu trúc truy vấn và kiểu căn chỉnh, không giả định mọi hệ quản trị cơ sở dữ liệu hỗ trợ mọi cú pháp giống nhau.

### 6.2. Dùng `PreparedStatement` cho dữ liệu động

Khi giá trị lọc đến từ người dùng hoặc dữ liệu bên ngoài, **không nối chuỗi trực tiếp vào SQL**:

~~~java
// Không an toàn: tránh cách ghép input vào câu lệnh.
String sql = "SELECT id FROM users WHERE email = '" + email + "'";
~~~

Thay vào đó, dùng placeholder `?` và bind tham số qua JDBC:

~~~java
String sql = """
        SELECT id, email, display_name
        FROM users
        WHERE email = ?
        """;

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);

    try (var resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String displayName = resultSet.getString("display_name");
            System.out.println(id + ": " + displayName);
        }
    }
}
~~~

Trong ví dụ:

- Text block giữ câu SQL ở dạng nhiều dòng dễ đọc.
- Dấu `?` là tham số vị trí do JDBC hỗ trợ.
- `setString(1, email)` truyền giá trị cho placeholder thứ nhất.
- `PreparedStatement` tách dữ liệu khỏi cấu trúc SQL, giúp tránh SQL injection qua **giá trị tham số**.
- `try-with-resources` đóng statement và result set tự động.

`connection` là một `java.sql.Connection` đã được ứng dụng thiết lập trước. Đoạn mã minh họa phần truy vấn, không bao gồm cấu hình kết nối hay driver cụ thể.

### 6.3. Không thể dùng placeholder cho tên bảng hoặc tên cột

JDBC placeholder đại diện cho **giá trị**, không đại diện cho định danh SQL. Ví dụ:

~~~java
String sql = "SELECT * FROM ? WHERE id = ?";
~~~

không thể dùng tham số thứ nhất để truyền tên bảng. Nếu tên cột hoặc bảng phải thay đổi, hãy chọn từ một danh sách allowlist do chương trình định nghĩa:

~~~java
String sortColumn = switch (requestedSort) {
    case "date" -> "created_at";
    case "name" -> "display_name";
    default -> "created_at";
};

String sql = """
        SELECT id, display_name
        FROM users
        ORDER BY %s
        """.formatted(sortColumn);
~~~

Ví dụ này chỉ an toàn khi `sortColumn` được chọn hoàn toàn từ các hằng do chương trình kiểm soát như trên. Không đưa trực tiếp chuỗi tên cột tùy ý từ request vào `formatted()`. Với các giá trị như email, ID, ngày tháng, trạng thái, hãy dùng placeholder và bind tham số.

### 6.4. Text block không thay thế việc kiểm tra logic truy vấn

Mẫu SQL đẹp chưa chắc truy vấn đúng. Hãy kiểm tra:

- Các bảng và alias có đúng không.
- Điều kiện `JOIN` có thể làm nhân bản bản ghi ngoài ý muốn không.
- `WHERE` có đúng phạm vi dữ liệu và quyền truy cập không.
- Điều kiện lọc có xử lý `NULL` đúng theo logic SQL không (`= NULL` không tương đương `IS NULL`).
- Các giá trị động đã dùng placeholder hay allowlist phù hợp chưa.
- Truy vấn đã có index và giới hạn kết quả phù hợp chưa.

Text block chỉ làm **mã nguồn chứa SQL dễ đọc**; nó không tối ưu truy vấn và không tự bảo vệ khỏi injection.

## 7. Tổ chức mẫu HTML

HTML có nhiều thẻ lồng nhau và thường dài. Text block giữ cấu trúc tài liệu gần với nội dung trình duyệt nhận được.

### 7.1. Mẫu HTML tĩnh

~~~java
String html = """
        <!doctype html>
        <html lang="vi">
          <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Order report</title>
          </head>
          <body>
            <main>
              <h1>Order report</h1>
              <p class="status">PAID</p>
            </main>
          </body>
        </html>
        """;
~~~

Đây là mẫu cố định, phù hợp để minh họa hoặc tạo nội dung tĩnh. Các thẻ và khoảng thụt lề vẫn hiện rõ trong mã Java.

### 7.2. Dữ liệu động phải được escape theo ngữ cảnh HTML

Không chèn trực tiếp tên người dùng, nội dung bình luận, địa chỉ hoặc dữ liệu request vào HTML:

~~~java
// Không an toàn nếu customerName đến từ người dùng.
String html = """
        <h1>Welcome, %s</h1>
        """.formatted(customerName);
~~~

Nếu `customerName` chứa chuỗi giống thẻ HTML hoặc script, trình duyệt có thể diễn giải nó như markup thay vì văn bản. Đây là rủi ro XSS (*cross-site scripting*).

Trong ứng dụng web thực tế:

- Ưu tiên template engine có **auto-escaping** được bật, ví dụ engine được cấu hình an toàn cho HTML.
- Nếu tự dựng HTML, dùng thư viện escaping phù hợp với **ngữ cảnh** (nội dung text, thuộc tính HTML, URL, JavaScript hoặc CSS).
- Không dùng một hàm thay thế ký tự đơn giản cho mọi ngữ cảnh; quy tắc escape cho thuộc tính, URL và JavaScript khác nhau.
- Tránh đưa dữ liệu không tin cậy vào `<script>`, thuộc tính sự kiện như `onclick`, CSS hoặc URL nếu chưa có xử lý chuyên biệt.

Text block có thể chứa một **khung HTML tĩnh**; dữ liệu động nên được đưa vào bằng cơ chế template an toàn. `String.formatted()` không tự HTML-escape.

### 7.3. Ví dụ về ranh giới giữa mẫu và dữ liệu

Một template có thể được lưu trong text block:

~~~java
String template = """
        <!doctype html>
        <html lang="vi">
          <body>
            <h1>Order report</h1>
            <p class="customer">CUSTOMER_PLACEHOLDER</p>
          </body>
        </html>
        """;
~~~

Đây là ví dụ về cấu trúc. Trong ứng dụng thật, đừng thay placeholder bằng cách nối chuỗi tùy tiện nếu giá trị có thể không tin cậy. Hãy chuyển template qua template engine hoặc dùng HTML escaping phù hợp trước khi đưa dữ liệu vào vị trí tương ứng.

## 8. So sánh ba định dạng và cách dùng text block

| Định dạng | Text block hữu ích ở đâu? | Cần xử lý riêng điều gì? |
|---|---|---|
| JSON | Payload mẫu, fixture, nội dung nhiều object/array. | Serialize dữ liệu động và escape theo JSON; text block không phải JSON serializer. |
| SQL | Câu truy vấn nhiều mệnh đề, CTE, join và điều kiện. | `PreparedStatement` cho giá trị; allowlist cho tên bảng/cột động; kiểm tra dialect và quyền dữ liệu. |
| HTML | Tài liệu tĩnh, email template hoặc khung trang. | Auto-escaping/template engine; escape theo ngữ cảnh để tránh XSS. |

Một quy trình phù hợp:

1. Viết cấu trúc tĩnh bằng text block để dễ đọc.
2. Xác định vị trí nào là dữ liệu động và nguồn dữ liệu có đáng tin không.
3. Dùng serializer, prepared statement hoặc template engine tương ứng.
4. Kiểm tra kết quả bằng parser, database hoặc trình duyệt thực tế.
5. Viết test cho nội dung kết quả và các ký tự đặc biệt.

Không nên dùng cùng một cách thay chuỗi cho cả ba định dạng: JSON, SQL và HTML có cú pháp cũng như rủi ro khác nhau.

## 9. Kết hợp text block với phương thức và hằng số

Nếu mẫu được dùng ở nhiều nơi, hãy đặt nó trong hằng số hoặc phương thức để tránh lặp lại:

~~~java
public final class Templates {
    private Templates() {
    }

    public static final String HEALTH_RESPONSE = """
            {
              "status": "ok",
              "version": 17
            }
            """;

    public static String selectOrdersByStatus() {
        return """
                SELECT id, status
                FROM orders
                WHERE status = ?
                ORDER BY created_at DESC
                """;
    }
}
~~~

Chọn `static final` khi nội dung là hằng số dùng lại và không phụ thuộc dữ liệu lúc chạy. Dùng phương thức nếu cần trả mẫu theo một cấu hình hoặc biến thể cụ thể. Đừng lưu một mẫu chung quá lớn chỉ vì nó là text block; chia thành các hằng hoặc phương thức theo trách nhiệm để dễ thay đổi.

### 9.1. Kết hợp với `formatted()`

Text block có thể gọi phương thức ngay sau dấu đóng:

~~~java
String report = """
        Report: %s
        Total: %d
        """.formatted("Orders", 12);
~~~

Điều này tạo ra chuỗi kết quả có các placeholder đã được thay thế. Khi dùng format string, ký tự `%` trong nội dung tĩnh cần được viết `%%` nếu không muốn nó được hiểu là mở đầu placeholder. Chẳng hạn:

~~~java
String progress = """
        Completion: 100%%
        """.formatted();
~~~

`formatted()` vẫn chỉ là định dạng chuỗi. Nó không thay thế JSON serializer, SQL parameter binding hoặc HTML escaping.

## 10. Chạy thử bằng Java 17

Tạo tệp `TextBlockDemo.java`:

~~~java
public final class TextBlockDemo {
    private TextBlockDemo() {
    }

    public static void main(String[] args) {
        String json = """
                {
                  "service": "orders",
                  "enabled": true,
                  "version": 17
                }
                """;

        String sql = """
                SELECT id, status
                FROM orders
                WHERE status = ?
                ORDER BY created_at DESC
                """;

        String html = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <h1>Order report</h1>
                    <p>Static example</p>
                  </body>
                </html>
                """;

        String escapedJson = """
                {
                  "message": "first line\\nsecond line",
                  "path": "C:\\\\temp\\\\orders"
                }
                """;

        System.out.println("JSON:");
        System.out.println(json);
        System.out.println("SQL:");
        System.out.println(sql);
        System.out.println("HTML:");
        System.out.println(html);
        System.out.println("JSON with escapes:");
        System.out.println(escapedJson);
    }
}
~~~

Từ terminal tại thư mục chứa file, chạy:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
~~~

`--release 17` yêu cầu trình biên dịch tạo bytecode và dùng API tương thích Java 17. Nếu đang dùng JDK 17, có thể kiểm tra phiên bản trước bằng:

~~~text
java -version
javac -version
~~~

Ví dụ không cần Maven, Gradle hoặc thư viện bên thứ ba. Nó minh họa cách text block tạo chuỗi JSON, SQL và HTML tĩnh; phần dữ liệu động và tương tác với database/web vẫn cần cơ chế chuyên dụng đã nêu ở trên.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lỗi cú pháp tại `"""` | Dùng JDK/target cũ hơn Java 15 hoặc đặt nội dung ngay sau dấu mở. | Dùng Java 17 và đặt line terminator ngay sau dấu mở. |
| Chuỗi kết quả có nhiều dấu cách đầu dòng | Dấu đóng ở cột thấp hơn dự kiến, hoặc mức thụt lề chung là 0. | Căn chỉnh dấu đóng với phần thụt lề mong muốn. |
| Mẫu JSON có `\n` thành xuống dòng thật trong giá trị | Viết `\n` của Java trong khi muốn giữ escape JSON `\n`. | Viết `\\n` trong mã Java. |
| Đường dẫn Windows trong JSON không parse được | Chưa escape dấu `\` cho cả Java và JSON. | Viết đúng hai lớp escape, hoặc dùng JSON serializer. |
| SQL báo lỗi gần dấu `?` | Đưa placeholder vào vị trí tên bảng/cột hoặc không bind tham số. | Placeholder chỉ dành cho giá trị; dùng allowlist cho định danh. |
| SQL injection dù đã dùng text block | Nối dữ liệu không tin cậy trực tiếp vào chuỗi SQL. | Dùng `PreparedStatement` và bind giá trị. |
| HTML hiển thị thẻ/script từ dữ liệu người dùng | Dữ liệu động chưa được escape hoặc template engine không auto-escape. | Dùng template engine an toàn và escaping theo ngữ cảnh. |
| `formatted()` báo lỗi format | Placeholder `%` không khớp đối số hoặc `%` trong nội dung chưa viết thành `%%`. | Kiểm tra placeholder và đối số; tránh format chuỗi nếu không cần. |
| Nghĩ text block là raw string | Escape sequence Java vẫn được xử lý. | Phân biệt cú pháp chuỗi Java với escape của định dạng đích. |

### Phân biệt khoảng trắng và line continuation

Khi kết quả không như mong đợi, kiểm tra ba thứ theo thứ tự:

1. Vị trí dấu mở và dấu đóng.
2. Mức thụt lề của các dòng nội dung.
3. Escape `\s`, `\n`, `\\` hoặc dấu `\` nối dòng.

Không nên thêm hoặc xóa khoảng trắng ngẫu nhiên để "làm cho chạy". Hãy xác định chuỗi ký tự bạn muốn nhận được rồi điều chỉnh mã nguồn cho đúng.

## 12. Bài tập thực hành

### Bài tập 1 — Chuyển chuỗi ghép sang text block

Chuyển đoạn sau:

~~~java
String html = "<ul>\n"
        + "  <li>Java</li>\n"
        + "  <li>SQL</li>\n"
        + "</ul>";
~~~

thành một text block sao cho chuỗi kết quả giữ nguyên cấu trúc và không có khoảng trắng thừa ở đầu dòng.

### Bài tập 2 — Escape JSON hai lớp

Viết text block tạo JSON có:

- Thuộc tính `message` chứa hai dòng văn bản được phân cách bằng escape JSON `\n`.
- Thuộc tính `path` chứa đường dẫn Windows `D:\data\orders`.

Hãy giải thích vì sao trong mã nguồn Java số dấu `\` phải nhiều hơn số dấu `\` trong giá trị JSON.

### Bài tập 3 — SQL an toàn

Viết truy vấn nhiều dòng tìm đơn hàng theo `customer_id` và `status`, sắp xếp mới nhất trước. Dùng `?` cho hai giá trị, rồi viết phần `PreparedStatement` bind tham số đúng thứ tự. Giải thích vì sao không thể dùng `?` để truyền tên cột sắp xếp.

### Bài tập 4 — HTML có dữ liệu động

Viết text block làm khung HTML cho trang hiển thị tên khách hàng. Sau đó mô tả cách đưa tên khách hàng vào bằng template engine có auto-escaping hoặc thư viện escape phù hợp. Giải thích rủi ro nếu gọi `.formatted(customerName)` trực tiếp.

### Bài tập 5 — Thụt lề và dấu đóng

Tạo hai text block có nội dung `alpha` và `beta`, một cái đặt dấu đóng thẳng hàng với nội dung, một cái đặt dấu đóng ở cột đầu tiên. Dự đoán số dấu cách đầu dòng trong hai giá trị kết quả và kiểm tra bằng cách in dấu ngoặc vuông quanh chuỗi.

### Gợi ý tự đối chiếu

- Bài 1: Dùng một text block với dấu đóng căn theo mức thụt lề chung; kết quả gồm ba dòng HTML.
- Bài 2: Java source `\\n` tạo hai ký tự `\` và `n` cho JSON; Java source `\\` tạo một dấu `\` cho chuỗi thông thường, còn JSON cần `\\` để biểu diễn một dấu `\` trong giá trị.
- Bài 3: `WHERE customer_id = ? AND status = ?`; bind bằng `setLong(1, customerId)` và `setString(2, status)`. Tên cột là cấu trúc SQL, không phải giá trị.
- Bài 4: `.formatted()` không escape HTML; phải dùng cơ chế template/escaping an toàn.
- Bài 5: Dấu đóng tham gia tính mức thụt lề; ở cột đầu tiên, phần thụt lề nội dung có thể được giữ nguyên.

## 13. Nguyên tắc áp dụng trong dự án

- Dùng text block khi chuỗi có cấu trúc nhiều dòng và cần giữ cho mã nguồn gần với nội dung thực tế.
- Căn chỉnh dấu đóng để kiểm soát khoảng trắng đầu dòng; dùng `\s` khi một dấu cách cuối dòng có ý nghĩa.
- Phân biệt escape Java với escape JSON, SQL hoặc HTML.
- Với JSON động, dùng serializer; với SQL động, dùng `PreparedStatement`; với HTML động, dùng template engine có auto-escaping hoặc escaping theo ngữ cảnh.
- Không coi `formatted()` là một cơ chế bảo mật hay một serializer. Nó chỉ thay placeholder trong chuỗi.
- Kiểm tra kết quả cuối bằng parser JSON, database hoặc trình duyệt; một chuỗi dễ đọc trong mã nguồn chưa chắc hợp lệ ở hệ thống nhận.
- Java 17 đã hỗ trợ text block ổn định; không cần preview flag.

Text block giúp các mẫu JSON, SQL và HTML trở nên rõ ràng, dễ đọc và dễ sửa. Giá trị lớn nhất đến từ việc kết hợp cú pháp này với đúng công cụ xử lý dữ liệu: serializer cho JSON, tham số hóa cho SQL và escaping theo ngữ cảnh cho HTML.

### Tài liệu tham khảo

- [Java Language Specification, Java SE 17 — Section 3.10.6: Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6).
- [Oracle Java 17 — Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html).
- [JDBC API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html).
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
