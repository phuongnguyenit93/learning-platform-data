# Text block trong Java 17: giải quyết bài toán chuỗi nhiều dòng trong mã nguồn

Khi viết chương trình Java, không phải mọi chuỗi đều chỉ dài một dòng. Một câu lệnh SQL, thông báo email, tài liệu HTML, JSON mẫu hay nội dung kiểm thử thường có **nhiều dòng, dấu nháy kép và cấu trúc thụt lề**. Nếu biểu diễn chúng bằng các string literal truyền thống, mã nguồn dễ trở nên khó đọc vì phải ghép nhiều đoạn và tự thêm ký tự xuống dòng.

**Text block** giúp viết trực tiếp nội dung nhiều dòng trong mã nguồn Java theo cách gần với hình thức văn bản thực tế. Tính năng này đã được chuẩn hóa từ Java 15 (JEP 378) và sử dụng bình thường trong **Java 17**, không cần bật preview.

Bài này tập trung vào vấn đề text block giải quyết, cú pháp cơ bản, cách Java xử lý xuống dòng và khoảng trắng, những trường hợp nên sử dụng, và các lưu ý khi đưa dữ liệu nhiều dòng vào ứng dụng.

## 1. Vấn đề: chuỗi nhiều dòng trước khi có text block

Hãy tưởng tượng một chương trình cần lưu câu SQL sau:

```sql
SELECT id, title, author
FROM books
WHERE published = ?
ORDER BY title
```

Với string literal thông thường, có thể viết:

```java
String sql = "SELECT id, title, author\n"
        + "FROM books\n"
        + "WHERE published = ?\n"
        + "ORDER BY title\n";
```

Đoạn mã vẫn hợp lệ, nhưng người đọc phải phân biệt **cấu trúc của chuỗi thực** với các phần phụ trợ trong mã Java: dấu nháy, dấu cộng, ký tự `\n` và thụt lề cho biểu thức nối chuỗi.

Một ví dụ khác là HTML:

```java
String html = "<div class=\"card\">\n"
        + "    <h2>Thông báo</h2>\n"
        + "    <p>Đơn hàng đã sẵn sàng.</p>\n"
        + "</div>\n";
```

Ngoài việc thêm `\n`, người viết còn phải thoát dấu `"` bằng `\"`. Khi HTML dài hơn, chỉ một dấu nháy hoặc dấu cộng đặt sai cũng khiến đoạn mã trở nên khó sửa.

Vấn đề nằm ở **khả năng biểu diễn và bảo trì văn bản nhiều dòng trong mã nguồn**:

| Khó khăn | Hệ quả |
| --- | --- |
| Phải nối nhiều string literal bằng `+` | Văn bản thực bị chia nhỏ bởi cú pháp Java. |
| Phải tự chèn `\n` ở từng dòng | Dễ quên hoặc thừa ký tự xuống dòng. |
| Phải thoát nhiều dấu nháy kép | HTML/JSON/SQL có thể khó nhìn và khó chép từ tài liệu gốc. |
| Muốn căn lề mã Java mà không làm đổi dữ liệu | Phải tự kiểm soát các khoảng trắng trong từng literal. |
| Sửa một đoạn văn bản lớn | Dễ tạo lỗi ở ranh giới các literal hoặc ký tự escape. |

**Text block** được thiết kế để làm đoạn văn bản đó dễ nhìn hơn, chứ không thay đổi bản chất của kiểu `String`.

## 2. Cú pháp text block trong Java 17

Text block bắt đầu bằng **ba dấu nháy kép** `"""`, ngay sau đó phải có một dấu xuống dòng. Nội dung nằm trên các dòng tiếp theo và kết thúc bằng ba dấu nháy kép `"""`:

```java
String sql = """
        SELECT id, title, author
        FROM books
        WHERE published = ?
        ORDER BY title
        """;
```

Trong ví dụ này, dấu mở `"""` đứng ở dòng khai báo; phần nội dung bắt đầu từ dòng kế tiếp. Độ thụt lề dùng để bố trí mã nguồn sẽ được xử lý theo quy tắc text block, nên chuỗi kết quả có thể là:

```text
SELECT id, title, author
FROM books
WHERE published = ?
ORDER BY title
```

Chuỗi kết quả còn có ký tự xuống dòng `\n` sau `ORDER BY title` vì dấu đóng `"""` nằm ở **dòng riêng** bên dưới nội dung.

### 2.1. Text block vẫn có kiểu `String`

Text block không tạo ra một kiểu dữ liệu mới:

```java
String text = """
        Xin chào!
        Đây là nội dung nhiều dòng.
        """;

System.out.println(text.length());
System.out.println(text.contains("nhiều dòng"));
System.out.println(text.isBlank());
```

Các phương thức quen thuộc của `String` vẫn hoạt động. Có thể truyền text block cho phương thức nhận `String`, ghép với chuỗi khác, so sánh bằng `equals()`, hoặc dùng với các API xử lý văn bản.

### 2.2. Phải xuống dòng sau dấu mở

Đúng:

```java
String message = """
        Xin chào Java 17
        """;
```

Sai cú pháp:

```java
// Ví dụ cố ý KHÔNG biên dịch được:
// String message = """Xin chào Java 17""";
```

Với text block, Java yêu cầu một **line terminator** sau dấu mở, có thể có khoảng trắng trước khi xuống dòng. Điều này giúp phân biệt rõ text block với string literal `"..."` thông thường.

Nếu nội dung chỉ là một dòng ngắn, `"Xin chào Java 17"` thường đơn giản hơn và không có lợi ích rõ ràng khi chuyển thành text block.

## 3. So sánh trực tiếp trước và sau

Ví dụ tạo dữ liệu JSON mẫu:

**String literal thông thường**

```java
String jsonOld = "{\n"
        + "  \"name\": \"Lan\",\n"
        + "  \"active\": true,\n"
        + "  \"roles\": [\"student\", \"editor\"]\n"
        + "}\n";
```

**Text block**

```java
String jsonNew = """
        {
          "name": "Lan",
          "active": true,
          "roles": ["student", "editor"]
        }
        """;
```

Hai cách trên có thể tạo ra **cùng nội dung ký tự**:

```java
System.out.println(jsonOld.equals(jsonNew)); // true
```

Điểm khác biệt lớn nhất là khả năng đọc, sao chép và chỉnh sửa. Ở bản text block, các dòng JSON giống một tài liệu JSON thực, trong khi mã Java vẫn có thể được thụt lề theo cấu trúc lớp và phương thức.

**Text block không tự phân tích JSON hoặc bảo đảm JSON hợp lệ.** Nó chỉ là cách khai báo một chuỗi. Nếu nội dung cần được kiểm tra, ánh xạ thành đối tượng hoặc tạo theo dữ liệu động, ứng dụng vẫn cần cách xử lý JSON phù hợp.

## 4. Java xử lý xuống dòng và thụt lề như thế nào?

Một text block không đơn thuần giữ nguyên từng ký tự từ vùng nhìn thấy trong trình soạn thảo. Java 17 có quy tắc xử lý để văn bản nhiều dòng dễ sử dụng trong mã nguồn đã được thụt lề.

Về mặt khái niệm, quá trình xử lý gồm:

1. **Chuẩn hóa dấu kết thúc dòng:** các dạng kết thúc dòng trong nội dung text block được chuẩn hóa thành `\n` (LF).
2. **Loại bỏ khoảng trắng thụt lề không cần thiết:** xác định mức lề chung rồi bỏ phần lề dùng chỉ để căn mã nguồn; đồng thời xử lý khoảng trắng cuối dòng theo quy tắc của text block.
3. **Xử lý escape sequence:** sau bước xử lý khoảng trắng, Java diễn giải các escape như `\n`, `\t`, `\s` hoặc dấu `\` dùng để nối dòng.

Thứ tự này quan trọng: một số escape được dùng chính để **giữ khoảng trắng** hoặc **loại bỏ dấu xuống dòng** mà bước xử lý mặc định sẽ không giữ lại.

### 4.1. Thụt lề mã nguồn không đồng nghĩa thụt lề chuỗi

Ví dụ:

```java
String text = """
        Mục chính
          Mục con
        Kết thúc
        """;
```

Nội dung kết quả:

```text
Mục chính
  Mục con
Kết thúc
```

Mức lề chung trước ba dòng được loại bỏ; **hai dấu cách tương đối** trước `Mục con` vẫn được giữ. Nhờ vậy, bạn có thể đặt text block bên trong một phương thức có nhiều cấp thụt lề mà nội dung thực không phải mang toàn bộ khoảng trắng của mã Java.

### 4.2. Vị trí dấu đóng ảnh hưởng đến lề

Dấu đóng `"""` cũng tham gia vào việc xác định lượng khoảng trắng được xem là thụt lề không cần thiết.

```java
String withoutExtraIndent = """
        A
          B
        """;

String withExtraIndent = """
        A
          B
    """;
```

Ở trường hợp đầu, dấu đóng cùng cột lề với `A`, nên lề chung được bỏ và kết quả là `"A\n  B\n"`. Ở trường hợp sau, dấu đóng nằm **sang trái** của nội dung; một phần lề trước `A` và `B` được giữ trong chuỗi. Điều này cho phép chủ động giữ thụt lề khi cần.

Để tránh bất ngờ khi chỉnh sửa mã nguồn, hãy chọn một cách bố trí dấu đóng nhất quán. Nếu muốn giữ chính xác một lượng lề cụ thể, cần quan sát sự tương quan giữa các dòng nội dung và dấu đóng.

### 4.3. Có hay không ký tự xuống dòng ở cuối chuỗi?

Đây là một khác biệt dễ bị bỏ sót:

```java
String withTrailingNewline = """
        first
        second
        """;

String withoutTrailingNewline = """
        first
        second""";

System.out.println(withTrailingNewline.endsWith("\n"));    // true
System.out.println(withoutTrailingNewline.endsWith("\n")); // false
```

Khi dấu đóng ở **dòng riêng** sau dòng nội dung, dấu kết thúc dòng trước nó thuộc về chuỗi. Khi đặt dấu đóng **ngay sau nội dung cuối**, không có thêm dấu xuống dòng cuối cùng.

Điều này ảnh hưởng đến so sánh chuỗi, kiểm thử, nội dung HTTP, lệnh SQL hoặc cấu hình mà dấu xuống dòng cuối có ý nghĩa. Hãy quyết định chủ đích thay vì giả định hai cách khai báo luôn tạo ra chuỗi giống nhau.

### 4.4. Kết thúc dòng được chuẩn hóa

Text block sử dụng `\n` làm ký tự xuống dòng trong nội dung được tạo ra, ngay cả khi tệp nguồn được lưu với kiểu xuống dòng CRLF trên Windows. Vì thế:

```java
String lines = """
        one
        two
        """;

System.out.println(lines.equals("one\ntwo\n")); // true
```

Đừng mặc định text block sẽ sinh `System.lineSeparator()` ở từng dòng. Nếu một giao thức hoặc định dạng cần ký tự kết thúc dòng khác (ví dụ CRLF), hãy xử lý một cách tường minh theo hợp đồng của giao thức đó.

## 5. Escape trong text block: không phải raw string

Text block làm giảm lượng ký tự phải escape, nhưng **không phải chuỗi thô hoàn toàn**. Các escape hợp lệ của Java vẫn được xử lý.

### 5.1. Dấu nháy kép thông thường

Trong text block, không cần thoát từng dấu `"`:

```java
String html = """
        <a href="https://example.com" title="Trang chủ">Mở trang</a>
        """;
```

Đây là lợi ích rõ ràng với HTML và JSON. Chỉ khi nội dung có **ba dấu nháy kép liên tiếp** có thể bị hiểu thành dấu đóng, bạn mới cần escape phù hợp, chẳng hạn dùng `\"""` để tạo bộ ba dấu nháy trong văn bản mà không kết thúc text block.

### 5.2. Các escape thông dụng

| Cú pháp trong text block | Ý nghĩa |
| --- | --- |
| `\n` | Chèn một ký tự xuống dòng LF ở vị trí chỉ định. |
| `\t` | Chèn ký tự tab. |
| `\\` | Chèn một dấu gạch chéo ngược `\`. |
| `\"` | Chèn dấu nháy kép khi cần escape, dù đa số dấu `"` trong nội dung không cần. |
| `\s` | Chèn một dấu cách; hữu ích để giữ khoảng trắng cuối dòng. |
| Dấu `\` ngay trước xuống dòng trong nguồn | Nối hai dòng của text block thành một dòng kết quả, không thêm ký tự xuống dòng ở chỗ đó. |

Ví dụ về ký tự escape:

```java
String message = """
        Dòng đầu\nDòng sau
        Cột A\tCột B
        """;
```

Ở đây `\n` trong dòng thứ nhất chèn thêm một LF, còn việc xuống dòng thật trong mã nguồn cũng tạo ra một LF riêng. Cần tính cả hai khi mong muốn nội dung chính xác.

### 5.3. Giữ dấu cách ở cuối dòng bằng `\s`

Khoảng trắng ở cuối các dòng text block thường bị loại bỏ trong quá trình xử lý khoảng trắng. Nếu nội dung thực sự cần có dấu cách ngay trước dấu xuống dòng, có thể dùng `\s`:

```java
String text = """
        A\s
        B
        """;

System.out.println(text.equals("A \nB\n")); // true
```

Dấu cách được tạo từ `\s` **sau** khi Java xử lý khoảng trắng của text block, vì vậy nó được giữ trong chuỗi kết quả. Cách này rõ ràng hơn việc đặt một dấu cách vô hình ở cuối dòng trong trình soạn thảo.

### 5.4. Nối dòng nguồn mà không xuống dòng kết quả

Khi một câu quá dài nhưng bạn muốn mã nguồn gọn, đặt `\` ở cuối dòng:

```java
String sentence = """
        Đây là một câu được chia \
        thành hai dòng trong mã nguồn.
        """;

System.out.println(sentence);
```

Kết quả:

```text
Đây là một câu được chia thành hai dòng trong mã nguồn.
```

Dấu `\` cuối dòng loại bỏ ký tự kết thúc dòng tương ứng. Trong ví dụ, dấu cách trước `\` được giữ để hai từ không dính liền. Kỹ thuật này phù hợp khi cần **chia dòng để đọc mã** nhưng kết quả phải là một dòng duy nhất.

### 5.5. Dấu gạch chéo ngược trong nội dung

Text block vẫn xử lý escape Java. Nếu cần một ký tự gạch chéo ngược trong chuỗi, thường phải viết `\\`:

```java
String windowsPath = """
        C:\\work\\notes
        """;

System.out.println(windowsPath);
// C:\work\notes
```

Nếu đưa nguyên một đường dẫn với `\n` vào mã mà không escape, `\n` có thể bị diễn giải thành dấu xuống dòng và kết quả khác điều mong muốn. Với các chuỗi chứa nhiều dấu `\`, cần chú ý quy tắc này ngay cả khi đã dùng text block.

## 6. Các bài toán thực tế nên dùng text block

### 6.1. SQL có nhiều dòng

```java
String sql = """
        SELECT id, name, created_at
        FROM customers
        WHERE status = ?
          AND created_at >= ?
        ORDER BY created_at DESC
        """;
```

Câu truy vấn dễ đọc gần như khi viết trong công cụ SQL. Java giữ nguyên các dòng và khoảng trắng tương đối có ý nghĩa.

Khi dữ liệu tìm kiếm đến từ người dùng, **không ghép trực tiếp vào SQL**:

```java
// Giả sử connection, status và startDate đã được khai báo.
try (java.sql.PreparedStatement statement =
        connection.prepareStatement(sql)) {
    statement.setString(1, status);
    statement.setDate(2, java.sql.Date.valueOf(startDate));
    try (java.sql.ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            System.out.println(rows.getString("name"));
        }
    }
}
```

Text block giúp **đọc và bảo trì SQL**, còn `PreparedStatement` giúp **gắn tham số** theo cách dành cho dữ liệu động. Text block không tự phòng chống SQL injection. Các định danh SQL động như tên bảng hoặc tên cột cần cơ chế xác thực/danh sách cho phép riêng, không xử lý bằng dấu `?` thông thường.

### 6.2. HTML hoặc nội dung email dạng mẫu

```java
String html = """
        <!doctype html>
        <html lang="vi">
          <body>
            <h1>Đơn hàng đã xác nhận</h1>
            <p>Cảm ơn bạn đã mua hàng.</p>
          </body>
        </html>
        """;
```

Ở đây việc giữ cấu trúc lồng nhau của HTML mang lại lợi ích đọc hiểu lớn hơn cách nối chuỗi.

Nếu nội dung cần chèn dữ liệu động, có thể dùng `formatted()`:

```java
String template = """
        <p>Xin chào %s!</p>
        <p>Đơn hàng của bạn: %s</p>
        """;

String htmlForCustomer = template.formatted("Lan", "A-102");
```

**Lưu ý:** `formatted()` chỉ định dạng chuỗi theo các placeholder kiểu `String.format`; nó **không tự escape HTML**. Với dữ liệu đến từ người dùng, cần escape/encode phù hợp với ngữ cảnh HTML hoặc dùng công cụ template có hỗ trợ escape.

### 6.3. JSON mẫu trong test và ví dụ API

```java
String payload = """
        {
          "userId": 17,
          "name": "Mai",
          "permissions": ["read", "write"]
        }
        """;
```

Khi viết unit test hoặc thử một API có payload cố định, khai báo JSON bằng text block giúp mẫu dữ liệu sát với JSON nhìn thấy trong tài liệu.

Nếu chương trình cần tạo JSON từ các object có dữ liệu động hoặc cấu trúc phức tạp, hãy ưu tiên thư viện JSON phù hợp thay vì tự nối các giá trị Java thành JSON; text block không xử lý escape ký tự đặc biệt hay bảo đảm cấu trúc JSON được tạo ra hợp lệ.

### 6.4. Thông báo đa dòng và nội dung trợ giúp dòng lệnh

```java
String help = """
        Cách sử dụng:
          app --input <file>
          app --help

        Tùy chọn:
          --input  Đường dẫn tệp cần xử lý
          --help   Hiển thị trợ giúp
        """;

System.out.print(help);
```

Các dòng trống, độ thụt lề tương đối và thứ tự nội dung được thể hiện rõ ràng trong mã. Với chuỗi có nhiều hướng dẫn hoặc danh sách lựa chọn, đây là cách khai báo dễ chỉnh sửa.

## 7. Chương trình Java 17 hoàn chỉnh

Tạo tệp `TextBlockDemo.java`:

```java
public class TextBlockDemo {
    public static void main(String[] args) {
        String traditional = "Xin chào,\n"
                + "Đơn hàng của bạn đã sẵn sàng.\n"
                + "Cảm ơn bạn.\n";

        String textBlock = """
                Xin chào,
                Đơn hàng của bạn đã sẵn sàng.
                Cảm ơn bạn.
                """;

        System.out.println("Hai cách giống nhau: "
                + traditional.equals(textBlock));
        System.out.println("Có LF cuối chuỗi: "
                + textBlock.endsWith("\n"));

        String noFinalLf = """
                Dòng 1
                Dòng 2""";
        System.out.println("Không có LF cuối chuỗi: "
                + !noFinalLf.endsWith("\n"));

        String json = """
                {
                  "id": 17,
                  "status": "ready"
                }
                """;
        System.out.println("JSON mẫu:");
        System.out.print(json);

        String template = """
                Chào %s,
                Trạng thái: %s
                """;
        System.out.print(template.formatted("An", "Hoàn tất"));
    }
}
```

Biên dịch và chạy bằng **JDK 17**:

```bash
javac TextBlockDemo.java
java TextBlockDemo
```

Kết quả:

```text
Hai cách giống nhau: true
Có LF cuối chuỗi: true
Không có LF cuối chuỗi: true
JSON mẫu:
{
  "id": 17,
  "status": "ready"
}
Chào An,
Trạng thái: Hoàn tất
```

Thông qua ví dụ này, bạn có thể nhìn thấy text block vẫn là `String` thông thường; điều khác biệt là **cách khai báo chuỗi nhiều dòng trong mã nguồn** và các quy tắc khoảng trắng đi kèm.

## 8. Khi nào text block không phải lựa chọn tốt nhất?

Text block phù hợp với những đoạn văn bản **cố định** có ý nghĩa khi trình bày qua nhiều dòng. Nhưng nó không thay thế mọi hình thức quản lý nội dung:

| Tình huống | Lựa chọn thường phù hợp |
| --- | --- |
| Chuỗi ngắn một dòng | String literal `"..."` thông thường. |
| SQL, HTML, JSON mẫu cố định và vừa phải | Text block để mã nguồn dễ đọc. |
| Dữ liệu lớn hoặc nội dung cần biên tập không qua sửa mã Java | Tệp tài nguyên ngoài mã nguồn, đọc bằng API phù hợp. |
| Nội dung cần dịch nhiều ngôn ngữ | Resource bundle hoặc hệ thống bản địa hóa. |
| Trang HTML động, nhiều nhánh hiển thị | Template engine hoặc công cụ dựng giao diện. |
| JSON/XML sinh từ object có dữ liệu động | Serializer hoặc thư viện xử lý dữ liệu chuyên dụng. |
| Truy vấn SQL có tham số dữ liệu không tin cậy | Text block kết hợp `PreparedStatement` và kiểm tra dữ liệu. |

Nếu một văn bản nhiều dòng chứa nhiều biến động hoặc được người không phải lập trình viên chỉnh sửa thường xuyên, việc lưu nó thành tệp tài nguyên riêng có thể hợp lý hơn để phân tách nội dung khỏi logic Java.

## 9. Lỗi thường gặp khi dùng text block

### 9.1. Bỏ quên xuống dòng ngay sau `"""`

```java
// Không hợp lệ:
// String wrong = """hello""";

// Hợp lệ:
String right = """
        hello
        """;
```

Text block yêu cầu xuống dòng sau dấu mở. Đây là quy tắc cú pháp của Java 17, không phụ thuộc IDE.

### 9.2. Thừa hoặc thiếu LF ở cuối

```java
String a = """
        alpha
        """;

String b = """
        alpha""";

System.out.println(a.equals(b)); // false
```

Hai chuỗi trông giống nhau khi in bằng `println`, nhưng `a` có một LF cuối còn `b` thì không. Trong unit test, so sánh chuỗi hoặc truyền dữ liệu sang giao thức khác, khác biệt một ký tự cũng có thể quan trọng.

### 9.3. Giữ nguyên khoảng trắng đầu/cuối theo tưởng tượng

Độ thụt lề và khoảng trắng cuối dòng được Java xử lý. Nếu một tệp cấu hình hoặc định dạng có ý nghĩa với khoảng trắng, đừng chỉ nhìn phần mã đã căn lề mà kết luận byte đầu ra luôn giống như văn bản nguồn.

Nếu cần giữ dấu cách cuối dòng, dùng `\s` có chủ đích. Nếu cần giữ thêm thụt lề, bố trí dấu đóng và các dòng sao cho lề cần giữ là một phần của nội dung.

### 9.4. Nhầm text block với raw string hoặc template string

Text block **vẫn xử lý escape Java** và không tự chèn biến:

```java
String name = "Lan";
String message = """
        Xin chào, name!
        """;
```

Kết quả có chữ `name` theo đúng nội dung, không thay bằng `Lan`. Muốn chèn giá trị, hãy dùng `formatted()` hoặc kỹ thuật dựng chuỗi phù hợp:

```java
String messageWithName = """
        Xin chào, %s!
        """.formatted(name);
```

Đồng thời, các dấu `\` không được giữ nguyên một cách tuyệt đối; vẫn phải tuân thủ quy tắc escape.

### 9.5. Cho rằng text block tự bảo vệ dữ liệu động

Text block không tự:

- chống SQL injection khi nội suy dữ liệu người dùng vào câu SQL;
- escape HTML để chống nội dung độc hại;
- tạo JSON đúng cú pháp từ dữ liệu người dùng;
- mã hóa URL, XML hoặc các định dạng dữ liệu khác;
- thực hiện localization hay quản lý template.

Tính năng này **giải quyết cách viết string literal nhiều dòng**, còn việc kiểm tra, mã hóa và xử lý dữ liệu phải dựa vào API đúng mục đích.

### 9.6. Phụ thuộc hoàn toàn vào line ending của hệ điều hành

Nếu cần `\r\n` cho giao thức hay định dạng cụ thể, text block có LF chuẩn hóa **không tự chuyển** sang CRLF chỉ vì mã chạy trên Windows. Hãy chỉ chuyển line ending khi hợp đồng đầu ra yêu cầu; đối với phần lớn văn bản trong mã nguồn, LF thông thường là đủ.

## 10. Bài tập thực hành

### Bài 1 — Chuyển đoạn nối chuỗi sang text block

Đoạn mã ban đầu:

```java
String menu = "Menu:\n"
        + "  1. Xem sách\n"
        + "  2. Mượn sách\n"
        + "  0. Thoát\n";
```

Hãy khai báo lại bằng text block, bảo đảm giữ hai dấu cách trước mỗi mục menu và giữ LF cuối chuỗi.

Gợi ý:

```java
String menu = """
        Menu:
          1. Xem sách
          2. Mượn sách
          0. Thoát
        """;
```

### Bài 2 — Dự đoán dấu xuống dòng cuối

```java
String first = """
        A
        B
        """;

String second = """
        A
        B""";
```

Hai biểu thức sau trả về gì?

```java
first.endsWith("\n")
second.endsWith("\n")
```

**Đáp án:** `true` và `false`. Dấu đóng ở dòng riêng tạo LF cuối chuỗi; dấu đóng ngay sau ký tự cuối thì không.

### Bài 3 — Khi nào cần escape?

Viết một text block chứa JSON sau:

```json
{
  "file": "report.txt",
  "enabled": true
}
```

Hãy xác định dấu `"` trong tên key và value có cần escape không.

**Gợi ý:** Không cần escape dấu nháy kép đơn lẻ trong text block. Nếu giá trị JSON chứa ký tự gạch chéo ngược, hãy nhớ có thể cần escape theo **hai lớp quy tắc**: quy tắc của Java string và quy tắc của JSON.

### Bài 4 — Chuỗi dài trên một dòng kết quả

Hãy dùng `\` ở cuối một dòng trong text block để đoạn văn sau được chia thành hai dòng **mã nguồn** nhưng vẫn tạo ra **một dòng kết quả**:

```text
Đây là câu dài dùng để minh họa kỹ thuật nối dòng trong text block.
```

### Bài 5 — SQL rõ ràng và an toàn

Viết text block chứa:

```sql
SELECT id, email
FROM users
WHERE active = ?
  AND role = ?
```

Giải thích vì sao dữ liệu cho hai dấu `?` nên được truyền qua `PreparedStatement` thay vì nối trực tiếp thành SQL. Xác định xem chuỗi SQL có cần LF ở cuối hay không theo cách dùng của ứng dụng.

## 11. Ghi nhớ khi làm việc với chuỗi nhiều dòng

Text block là cú pháp chính thức trong **Java 17** để biểu diễn một `String` nhiều dòng dễ đọc và dễ bảo trì. Mở và đóng bằng `"""`, bắt buộc xuống dòng sau dấu mở; Java tự xử lý phần thụt lề không cần thiết và chuẩn hóa kết thúc dòng thành LF. Vị trí dấu đóng quyết định có giữ LF cuối chuỗi hay không. Text block vẫn hỗ trợ escape như `\n`, `\s` và dấu `\` nối dòng, đồng thời vẫn là chuỗi thông thường khi truyền cho API.

Đối với SQL, JSON, HTML, thông báo và dữ liệu mẫu cố định, text block giúp mã nguồn gần với nội dung được biểu diễn. Khi dữ liệu động hoặc yêu cầu định dạng phức tạp xuất hiện, hãy kết hợp với công cụ xử lý chuyên dụng thay vì coi text block là một hệ thống template hoặc serializer.

### Tài liệu tham khảo

- [JEP 378: Text Blocks](https://openjdk.org/jeps/378) — tính năng text block được chuẩn hóa.
- [Java Language Specification, Java SE 17 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6) — cú pháp, xử lý thụt lề và escape của text block.
- [Java SE 17 API — `String.stripIndent()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#stripIndent()) — cơ chế xử lý thụt lề trong chuỗi.
- [Java SE 17 API — `String.translateEscapes()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#translateEscapes()) — diễn giải escape của Java string.
- [Java SE 17 API — `String.formatted(Object...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)) — định dạng chuỗi, có thể dùng với text block.
