# Dấu nháy, dấu gạch chéo và nội dung có ba dấu nháy trong Java Text Block

**Text block** là cú pháp tạo một giá trị `String` từ nội dung nhiều dòng trong mã nguồn Java. Tính năng này được chuẩn hóa từ Java 15 (JEP 378), vì vậy đã là tính năng chính thức trong **Java 17**. Text block hữu ích khi viết SQL, JSON, HTML, nội dung mẫu, thông điệp nhiều dòng hoặc đoạn văn bản có nhiều dấu nháy và dấu gạch chéo.

Điểm cần nhớ là text block **vẫn là một String Java thông thường**. Nó không phải raw string: các escape sequence như `\n`, `\t` và `\\` vẫn được xử lý; dấu nháy kép thường có thể viết trực tiếp, nhưng một chuỗi ba dấu nháy kép liên tiếp phải được xử lý để không bị hiểu nhầm là dấu kết thúc text block.

Ví dụ cơ bản:

```java
String message = """
        Xin chào,
        Java 17!
        """;
```

Giá trị của `message` chứa hai dòng văn bản và dấu xuống dòng cuối cùng trước dấu đóng. Không cần nối nhiều chuỗi bằng toán tử `+` hoặc đặt thủ công `\n` sau từng dòng.

## 1. Cú pháp text block và hai dấu phân cách

Một text block bắt đầu bằng **ba dấu nháy kép** `"""`, tiếp theo là một dấu kết thúc dòng. Phần nội dung nằm giữa dấu mở và dấu đóng; dấu đóng cũng là ba dấu nháy kép.

```java
String text = """
    Nội dung dòng thứ nhất.
    Nội dung dòng thứ hai.
    """;
```

Các quy tắc cú pháp cơ bản:

1. Dấu mở phải là ba dấu nháy kép liên tiếp.
2. Sau dấu mở phải có dấu kết thúc dòng (line terminator). Có thể có khoảng trắng hoặc tab giữa dấu mở và dấu xuống dòng.
3. Dấu đóng là ba dấu nháy kép liên tiếp.
4. Nội dung được viết giữa hai dấu phân cách và được tạo thành một giá trị `String`.
5. Dấu kết thúc dòng của nội dung được chuẩn hóa thành LF (`\n`) trong giá trị text block.

### 1.1. Dấu xuống dòng sau dấu mở là bắt buộc

Đây là text block hợp lệ:

```java
String greeting = """
    Hello Java
    """;
```

Đoạn sau **không phải** cú pháp text block hợp lệ trong Java 17:

```java
// Không hợp lệ: không có line terminator sau dấu mở.
// String greeting = """Hello Java""";
```

Nếu chỉ cần một chuỗi ngắn trên một dòng, dùng string literal thông thường:

```java
String greeting = "Hello Java";
```

### 1.2. Vị trí dấu đóng ảnh hưởng dấu xuống dòng cuối

Khi dấu đóng nằm trên một dòng riêng, dấu xuống dòng ngay trước nó là một phần nội dung:

```java
String withFinalNewline = """
    Java
    17
    """;
```

Giá trị tương đương với chuỗi có dấu xuống dòng sau `17`:

```text
Java\n17\n
```

Nếu đặt dấu đóng ngay sau ký tự cuối cùng của nội dung, không có dấu xuống dòng cuối:

```java
String withoutFinalNewline = """
    Java
    17""";
```

Giá trị tương đương:

```text
Java\n17
```

Đây là khác biệt có ý nghĩa khi tạo nội dung gửi qua HTTP, ghi file, so sánh chuỗi, tạo checksum hoặc xây dựng thông điệp giao thức. Đừng cho rằng mọi text block đều tự động kết thúc bằng newline; hãy nhìn vị trí dấu đóng.

## 2. Dấu nháy kép bên trong text block

Trong string literal thông thường, dấu nháy kép dùng để đóng chuỗi nên phải viết `\"` nếu muốn nó xuất hiện như dữ liệu:

```java
String regular = "Tên người dùng là \"Lan\".";
```

Trong text block, một hoặc hai dấu nháy kép có thể viết trực tiếp:

```java
String sentence = """
    Người dùng nói: "Xin chào".
    Thuộc tính có giá trị "" (chuỗi rỗng).
    """;
```

Kết quả giữ nguyên dấu nháy:

```text
Người dùng nói: "Xin chào".
Thuộc tính có giá trị "" (chuỗi rỗng).
```

Vì dấu nháy kép đơn lẻ không kết thúc text block, code dễ đọc hơn khi tạo JSON, HTML hoặc đoạn văn bản có nhiều chuỗi được đặt trong dấu nháy.

### 2.1. Ba dấu nháy kép liên tiếp là trường hợp đặc biệt

Dấu phân cách đóng của text block cũng là ba dấu nháy kép `"""`. Vì vậy, nếu nội dung cần chứa chính xác ba dấu nháy kép liên tiếp, phải **escape ít nhất một dấu nháy** để trình biên dịch không hiểu nhầm đó là dấu đóng.

Cách thường dùng là đặt dấu gạch chéo ngược trước dấu nháy đầu tiên:

```java
String delimiterText = """
    Dấu phân cách của text block gồm ba dấu nháy: \"""
    """;
```

Trong giá trị `delimiterText`, chuỗi `\"""` ở mã nguồn trở thành ba ký tự dấu nháy kép:

```text
Dấu phân cách của text block gồm ba dấu nháy: """
```

Ở đây, `\"` là escape sequence tạo ra một dấu nháy kép; hai dấu nháy tiếp theo là ký tự dấu nháy thông thường. Cả ba trở thành **nội dung của String**, không phải dấu kết thúc text block.

### 2.2. Không cần escape mọi dấu nháy

Đừng thêm `\` trước tất cả dấu nháy kép chỉ vì đã quen với string literal:

```java
String json = """
    {
      "name": "Lan",
      "active": true
    }
    """;
```

Trong ví dụ text block, các dấu nháy kép bao quanh key và value là nội dung trực tiếp. Chỉ cần xử lý những chuỗi ba dấu nháy có thể bị hiểu thành dấu đóng và các dấu gạch chéo ngược có ý nghĩa escape.

## 3. Dấu gạch chéo ngược và escape sequence

Text block không loại bỏ quy tắc escape của Java. Một dấu gạch chéo ngược `\` mở đầu một escape sequence; nếu muốn kết quả chứa chính ký tự gạch chéo ngược, thường phải viết **hai dấu gạch chéo ngược trong mã nguồn**: `\\`.

Một số escape sequence thường dùng:

| Viết trong mã nguồn | Ký tự trong giá trị String |
| --- | --- |
| `\n` | Xuống dòng LF. |
| `\r` | Carriage return. |
| `\t` | Tab. |
| `\b` | Backspace. |
| `\f` | Form feed. |
| `\"` | Dấu nháy kép. |
| `\'` | Dấu nháy đơn. |
| `\\` | Một dấu gạch chéo ngược. |
| `\s` | Một dấu cách (space), được hỗ trợ từ Java 15. |
| `\` ngay trước line terminator | Nối dòng mã nguồn mà không đưa newline đó vào kết quả. |

Các escape sequence này được xử lý khi tạo giá trị chuỗi. Do đó, đếm dấu gạch chéo trong **mã nguồn** và đếm dấu gạch chéo trong **kết quả String** là hai việc khác nhau.

### 3.1. Đường dẫn Windows

Đường dẫn Windows thường chứa dấu gạch chéo ngược. Trong Java, không thể viết một dấu gạch chéo ngược đơn lẻ trước các chữ như `t`, `n` hoặc `u` mà mong chúng luôn được giữ nguyên, vì một số tổ hợp có nghĩa escape đặc biệt.

```java
String path = """
    C:\\Users\\Public\\Documents\\notes.txt
    """;

System.out.println(path);
```

Giá trị in ra:

```text
C:\Users\Public\Documents\notes.txt
```

Mỗi cặp `\\` trong mã nguồn tạo ra một dấu `\` trong giá trị. Cách viết này cũng áp dụng cho string literal thông thường.

Nếu không muốn quan tâm đến quy tắc escape của đường dẫn, có thể dùng dấu gạch chéo xuôi (Java trên Windows thường chấp nhận đường dẫn dạng này) hoặc API `Path.of(...)` để ghép các thành phần đường dẫn theo nền tảng:

```java
import java.nio.file.Path;

Path notes = Path.of(
        "C:/", "Users", "Public", "Documents", "notes.txt"
);
```

Text block phục vụ biểu diễn chuỗi nhiều dòng; nó không thay thế API xử lý đường dẫn của hệ điều hành.

### 3.2. Biểu thức chính quy (regex)

Regex thường dùng `\d`, `\w`, `\s`, `\.`. Nhưng `\d` và `\w` không phải escape sequence hợp lệ của Java. Nếu viết thẳng chúng trong text block, compiler báo lỗi escape không hợp lệ.

Ví dụ đúng:

```java
String regex = """
    \\d{4}-\\d{2}-\\d{2}
    """;
```

Giá trị của `regex` là:

```text
\d{4}-\d{2}-\d{2}
```

Một ví dụ sử dụng:

```java
import java.util.regex.Pattern;

String dateRegex = """
    \\d{4}-\\d{2}-\\d{2}
    """;

boolean valid = Pattern.matches(dateRegex, "2026-11-15");
System.out.println(valid); // true
```

Lý do cần viết `\\d` trong mã nguồn là Java xử lý cặp `\\` thành một dấu gạch chéo ngược; regex engine mới nhận được `\d` để hiểu đó là nhóm chữ số.

### 3.3. JSON có dấu nháy và escape bên trong giá trị

JSON sử dụng dấu nháy kép để bao quanh key và string value. Text block giúp viết cấu trúc JSON tự nhiên, nhưng nếu **nội dung JSON cần chứa một dấu nháy được escape**, phải bảo đảm dấu gạch chéo ngược được giữ lại trong chuỗi Java:

```java
String json = """
    {
      "message": "He said: \\\"hello\\\"",
      "path": "C:\\\\temp"
    }
    """;
```

Giải thích:

- `\\\"` trong mã Java tạo ra hai ký tự: một dấu gạch chéo ngược và một dấu nháy kép; JSON cần cặp ký tự đó để biểu diễn dấu nháy nằm bên trong một string value.
- `\\\\` trong mã Java tạo ra hai dấu gạch chéo ngược trong nội dung JSON; JSON cần escape dấu gạch chéo ngược của chính nó.
- Dấu nháy bao quanh key và value không cần escape trong mã text block.

Đây là ví dụ về **hai tầng cú pháp**: Java xử lý escape trước, sau đó JSON parser mới đọc chuỗi kết quả. Khi làm việc với JSON thực tế, nên dùng thư viện JSON để serialize dữ liệu động; text block phù hợp với JSON mẫu cố định hoặc dữ liệu minh họa.

## 4. Escape sequence đặc biệt của text block: `\s`

Khi tạo nội dung nhiều dòng, Java loại bỏ khoảng trắng cuối dòng (trailing whitespace) để tránh các khoảng trắng vô tình trong file nguồn làm thay đổi kết quả. Điều này gây bất tiện nếu nội dung thực sự cần kết thúc bằng một hoặc nhiều dấu cách.

Java 15 bổ sung escape sequence `\s` để biểu diễn **một dấu cách có chủ ý**:

```java
String padded = """
    key\s
    """;
```

Kết quả có một dấu cách sau chữ `key` trước newline cuối:

```text
key ·\n
```

Trong minh họa trên, ký hiệu `·` chỉ một dấu cách; ký tự chấm không có trong String thực tế.

### 4.1. Vì sao không chỉ nhấn Space ở cuối dòng?

Ví dụ:

```java
String notPadded = """
    key
    """;
```

Nếu gõ thêm các dấu cách thông thường sau chữ `key` ở cuối dòng mã nguồn, chúng bị xử lý như trailing whitespace và không được giữ như nội dung có ý nghĩa. Để biểu diễn khoảng trắng cuối dòng một cách rõ ràng, dùng `\s`.

### 4.2. Phân biệt `\s` trong Java với `\s` trong regex

Hai ngữ cảnh khác nhau:

- Trong **mã nguồn text block**, `\s` là escape sequence Java tạo ra một dấu cách.
- Trong **regex**, `\s` là ký hiệu nhóm ký tự whitespace của regex engine.

Muốn kết quả String chứa ký tự `\s` để regex sử dụng, mã nguồn phải viết:

```java
String whitespaceRegex = """
    \\s+
    """;
```

Nếu viết `\s+` trực tiếp trong text block, Java sẽ tạo ra một dấu cách rồi đến dấu `+`; regex nhận được dấu cách literal, không phải token `\s`.

## 5. Nối dòng mà không tạo ký tự xuống dòng

Text block giữ các dấu xuống dòng trong nội dung. Nhưng đôi khi muốn xuống dòng trong **mã nguồn** để dễ đọc, trong khi kết quả vẫn là một dòng. Có thể đặt escape sequence nối dòng: một dấu gạch chéo ngược ngay trước line terminator.

```java
String oneLine = """
    Đây là một câu dài \
    được chia thành hai dòng trong source code.
    """;
```

Giá trị của `oneLine`:

```text
Đây là một câu dài được chia thành hai dòng trong source code.\n
```

Dấu gạch chéo ngược và line terminator sau nó không được đưa vào chuỗi. Khoảng trắng đầu dòng thứ hai được xử lý theo quy tắc incidental indentation trước khi tạo nội dung cuối.

**Lưu ý:** dấu gạch chéo ngược phải ở ngay trước dấu kết thúc dòng. Nếu đặt thêm ký tự hoặc khoảng trắng sau dấu gạch chéo, nó không còn là cú pháp nối dòng mong muốn. Hãy xem đúng vị trí ký tự trong source.

Nối dòng khác với:

```java
String twoLines = """
    Dòng thứ nhất
    Dòng thứ hai
    """;
```

Ở ví dụ thứ hai, newline giữa hai dòng vẫn có trong giá trị String.

## 6. Khoảng trắng đầu dòng và vị trí dấu đóng

Text block được thiết kế để nội dung có thể thụt lề theo cấu trúc mã nguồn mà không buộc giá trị String phải giữ nguyên tất cả khoảng trắng đó. Java loại bỏ **incidental white space** (khoảng trắng không chủ ý) theo quy tắc xác định độ thụt lề tối thiểu.

Khi tính incidental indentation, vị trí dấu đóng có vai trò quan trọng. Trình biên dịch xác định mức thụt lề tối thiểu từ các dòng nội dung không rỗng và dòng chứa dấu đóng nếu dòng đó chỉ có khoảng trắng trước delimiter; sau đó loại bỏ mức thụt lề tương ứng khỏi các dòng. Khoảng trắng cuối dòng cũng được loại bỏ. Dấu xuống dòng được chuẩn hóa trước khi xử lý escape.

### 6.1. Ví dụ thụt lề phổ biến

```java
String html = """
        <html>
            <body>
                <h1>Hello</h1>
            </body>
        </html>
        """;
```

Trong ví dụ trên, phần nội dung có mức thụt lề chung 8 dấu cách so với lề source; Java loại bỏ mức chung đó. Giá trị thu được:

```text
<html>
    <body>
        <h1>Hello</h1>
    </body>
</html>
```

Khoảng thụt lề tương đối bên trong HTML được giữ nguyên.

### 6.2. Dời dấu đóng có thể làm thay đổi kết quả

```java
String indented = """
        first
            second
        """;

String preserved = """
        first
            second
""";
```

Ở biến `indented`, dấu đóng được thụt lề 8 dấu cách nên mức tối thiểu có thể loại bỏ là 8. Ở biến `preserved`, dấu đóng ở cột đầu tiên nên mức thụt lề tối thiểu là 0; các dấu cách đầu dòng của nội dung được giữ lại.

Giá trị minh họa:

```text
indented:
first
    second

preserved:
        first
            second
```

Vì vậy, khi tạo nội dung có indentation mang ý nghĩa, chẳng hạn code mẫu hoặc YAML, **không nên tùy tiện di chuyển delimiter**. Định dạng source và vị trí dấu đóng có thể thay đổi dữ liệu đầu ra.

### 6.3. Blank line và trailing whitespace

Các dòng trống không nên được dùng để quyết định mức thụt lề như một dòng nội dung không rỗng. Khoảng trắng ở cuối mỗi dòng bị loại bỏ; muốn có dấu cách cuối dòng, biểu diễn bằng `\s`. Nếu nội dung có các dòng trống để phân đoạn, hãy đặt chúng trực quan và kiểm tra giá trị kết quả khi whitespace là một phần của định dạng.

Ví dụ:

```java
String poem = """
        First line

        Third line
        """;
```

Dòng trống giữa hai dòng văn bản vẫn là một dòng trống trong kết quả. Không cần chèn `\n` thủ công chỉ để tạo một dòng trống.

## 7. Thứ tự xử lý: indentation rồi mới escape

Để hiểu các trường hợp phức tạp, cần nhớ quy trình xử lý text block theo đặc tả:

1. **Nhận diện delimiter và nội dung.** Dấu mở, dấu đóng và các ký tự trong phần thân xác định text block.
2. **Chuẩn hóa line terminator.** Các dạng line ending của source được chuẩn hóa thành LF trong nội dung.
3. **Loại bỏ incidental white space.** Mức thụt lề chung và trailing whitespace được xử lý.
4. **Diễn giải escape sequence.** Ví dụ `\\`, `\n`, `\s` và line continuation được chuyển thành ký tự tương ứng.

Thứ tự này giải thích vì sao khoảng trắng cuối dòng thông thường bị bỏ nhưng `\s` vẫn tạo được dấu cách cuối: escape được xử lý **sau** bước loại bỏ trailing whitespace.

Ngoài ra, Unicode escape dạng backslash-u theo sau bởi bốn chữ số thập lục phân được xử lý ở giai đoạn dịch mã nguồn sớm hơn việc phân tích token và xử lý text block. Text block không biến chuỗi đó thành dữ liệu thô. Khi cần chứa đúng một chuỗi có dạng Unicode escape, hãy hiểu quy tắc Unicode escape của JLS và kiểm tra mã nguồn thực tế; đừng mặc định mọi backslash trong text block đều chỉ được xử lý ở bước escape của String.

## 8. Ví dụ thực tế: SQL nhiều dòng

Text block giúp câu truy vấn SQL gần với định dạng thường thấy trong công cụ quản trị cơ sở dữ liệu:

```java
String sql = """
        SELECT id, full_name, email
        FROM customer
        WHERE status = ?
          AND created_at >= ?
        ORDER BY created_at DESC
        """;
```

Có thể dùng cùng `PreparedStatement`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.sql.Timestamp;

class CustomerRepository {
    private static final String FIND_ACTIVE = """
            SELECT id, full_name, email
            FROM customer
            WHERE status = ?
              AND created_at >= ?
            ORDER BY created_at DESC
            """;

    static void findActive(Connection connection, Instant from)
            throws SQLException {
        try (PreparedStatement statement =
                     connection.prepareStatement(FIND_ACTIVE)) {
            statement.setString(1, "ACTIVE");
            statement.setTimestamp(2, Timestamp.from(from));

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    System.out.println(rows.getString("full_name"));
                }
            }
        }
    }
}
```

Text block chỉ làm câu SQL dễ đọc hơn. Nó **không tự escape dữ liệu, không chống SQL injection và không thay thế tham số hóa truy vấn**. Vẫn dùng dấu `?` cùng các phương thức `setString`, `setTimestamp` của JDBC.

## 9. Ví dụ thực tế: HTML có dấu nháy và nội dung nhiều dòng

```java
String html = """
        <!doctype html>
        <html lang="vi">
          <head>
            <meta charset="UTF-8">
            <title>"Java 17"</title>
          </head>
          <body>
            <p class="message">Xin chào!</p>
          </body>
        </html>
        """;
```

Dấu nháy kép trong thuộc tính HTML và tiêu đề không cần escape trong mã nguồn text block. Nội dung HTML được giữ theo dòng và có thể truyền cho API ghi file hoặc HTTP.

Nhưng text block không tự encode dữ liệu động để chống XSS:

```java
String userName = request.getParameter("name");

// Không an toàn nếu userName có thể chứa HTML/JavaScript tùy ý:
String page = """
        <p>Xin chào, %s!</p>
        """.formatted(userName);
```

`formatted` chỉ thay thế placeholder; nó không tự escape HTML. Khi chèn dữ liệu người dùng vào HTML, phải dùng thư viện/template engine có cơ chế encode đúng ngữ cảnh.

## 10. Text block có phải raw string hoặc template không?

Không. Một số hiểu nhầm dễ gặp:

| Hiểu nhầm | Thực tế trong Java 17 |
| --- | --- |
| Text block giữ nguyên mọi backslash. | Không; escape sequence Java vẫn được xử lý. |
| Dấu nháy kép luôn phải viết `\"`. | Không; một hoặc hai dấu nháy kép có thể viết trực tiếp. Chuỗi ba dấu nháy liên tiếp cần xử lý để không đóng block. |
| Có thể đặt delimiter mở và nội dung trên cùng dòng. | Không; delimiter mở phải theo sau bởi line terminator. |
| Dòng nguồn xuống hàng luôn được bỏ qua. | Không; newline thường là một phần của giá trị String. |
| Dời dấu đóng không ảnh hưởng dữ liệu. | Có thể ảnh hưởng indentation và dấu newline cuối. |
| Có thể nhúng biến bằng cú pháp template theo tên biến. | Không; Java 17 text block không có nội suy biến. Dùng nối chuỗi, `formatted` hoặc template engine phù hợp. |
| Text block tự bảo vệ SQL/HTML/JSON. | Không; cần API tham số hóa hoặc serializer/encoder đúng định dạng. |

### 10.1. Dùng `formatted` khi cần chèn giá trị đơn giản

```java
String template = """
        Hello, %s!
        Your score is %d.
        """;

String message = template.formatted("Lan", 95);
```

`String.formatted(...)` có từ Java 15 và dùng được trong Java 17. Nó xử lý placeholder theo quy tắc định dạng của `Formatter`, **không phải** cơ chế nội suy tổng quát hoặc encoder an toàn cho HTML, SQL, shell hay JSON.

## 11. So sánh string literal, nối chuỗi và text block

| Cách viết | Phù hợp khi | Điểm cần chú ý |
| --- | --- | --- |
| String literal `"..."` | Chuỗi ngắn, một dòng. | Phải escape dấu nháy kép và newline theo quy tắc Java. |
| Nối chuỗi bằng `+` | Ghép vài thành phần nhỏ hoặc biểu thức đơn giản. | Nhiều dòng nối thủ công dễ rối và khó căn chỉnh. |
| Text block `""" ... """` | Nội dung nhiều dòng, có cấu trúc, nhiều dấu nháy. | Phải hiểu indentation, newline, trailing whitespace và escape. |
| API chuyên biệt (Path, JDBC parameters, JSON serializer, HTML encoder) | Xử lý dữ liệu có ngữ nghĩa riêng. | Dùng API đúng mục đích; text block chỉ là cách biểu diễn String. |

Không nên chuyển mọi chuỗi sang text block. Chuỗi một dòng như mã trạng thái, key hoặc thông báo ngắn thường dễ đọc nhất khi dùng string literal thông thường.

## 12. Ví dụ tổng hợp: dấu nháy, backslash, triple quote và newline

Lưu chương trình sau vào file **`TextBlockDetails.java`**:

```java
public class TextBlockDetails {
    public static void main(String[] args) {
        String quotes = """
                A normal quote: "hello"
                Two quotes: ""
                Three quotes: \"""
                """;

        String windowsPath = """
                C:\\Users\\Public\\notes.txt
                """;

        String regex = """
                \\d{4}-\\d{2}-\\d{2}
                """;

        String padded = """
                key\s
                """;

        System.out.println("QUOTES:");
        System.out.print(quotes);

        System.out.println("PATH:");
        System.out.println(windowsPath);

        System.out.println("REGEX:");
        System.out.println(regex);

        System.out.println("PADDED:");
        System.out.println("[" + padded.replace(" ", "·") + "]");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TextBlockDetails.java
java TextBlockDetails
```

Chương trình cho thấy các quy tắc được áp dụng cùng lúc:

- `"hello"` và `""` được viết trực tiếp.
- `\"""` tạo ra nội dung ba dấu nháy.
- `\\` tạo ra một dấu gạch chéo ngược trong đường dẫn.
- `\\d` tạo ra token regex `\d`.
- `\s` tạo dấu cách cuối dòng có chủ ý.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Compiler báo lỗi gần `"""Hello...`. | Dấu mở không có line terminator sau nó. | Đặt nội dung ở dòng tiếp theo hoặc dùng string literal một dòng. |
| Text block kết thúc sớm ở chỗ có ba dấu nháy. | Chuỗi ba dấu nháy trong nội dung bị hiểu là delimiter đóng. | Escape ít nhất một dấu nháy, ví dụ `\"""` để tạo ba dấu nháy trong kết quả. |
| Compiler báo illegal escape cho `\d` hoặc `\w`. | Đây là escape của regex, không phải escape hợp lệ của Java. | Viết `\\d` hoặc `\\w` để String nhận một backslash. |
| Đường dẫn Windows mất dấu gạch chéo hoặc báo lỗi escape. | Backslash trong source đang mở đầu escape sequence. | Dùng `\\\\` trong source cho mỗi backslash cần có trong kết quả; hoặc dùng `Path.of(...)`. |
| Text block có indentation khác dự kiến. | Mức thụt lề phụ thuộc các dòng nội dung và vị trí dấu đóng. | Căn lại delimiter, xem xét incidental indentation và kiểm tra giá trị String. |
| Khoảng trắng cuối dòng biến mất. | Trailing whitespace bị loại bỏ. | Dùng `\s` cho dấu cách có chủ ý. |
| Kết quả có newline cuối không như mong đợi. | Vị trí delimiter đóng quyết định newline cuối có nằm trong nội dung hay không. | Đặt dấu đóng ở dòng riêng nếu cần newline cuối; đặt ngay sau nội dung nếu không cần. |
| Nghĩ text block không xử lý escape. | Nhầm text block với raw string. | Nhớ rằng Java vẫn diễn giải escape sequence sau bước xử lý indentation. |
| Dữ liệu HTML/SQL động bị lỗi bảo mật. | Dùng text block như một bộ escape dữ liệu. | Dùng prepared statement, serializer hoặc encoder đúng ngữ cảnh. |

## 14. Bài tập thực hành

### Bài 1 — Chuyển string nối thành text block

Chuyển đoạn sau thành text block mà giữ nguyên các dòng và dấu nháy trong nội dung:

```java
String config = "{\n"
        + "  \"app\": \"demo\",\n"
        + "  \"enabled\": true\n"
        + "}";
```

Sau đó giải thích vì sao dấu nháy bao quanh `app` không cần escape trong text block.

### Bài 2 — Viết đường dẫn Windows

Tạo text block chứa:

```text
C:\Program Files\Java\jdk-17
```

Viết mã nguồn sao cho giá trị String có đúng một backslash giữa các thành phần đường dẫn. Thử giải thích tại sao viết trực tiếp `\t` có thể tạo tab thay vì hai ký tự backslash và chữ `t`.

### Bài 3 — Tạo regex ngày tháng

Tạo text block cho regex:

```text
\d{4}-\d{2}-\d{2}
```

Dùng `Pattern.matches(...)` kiểm tra chuỗi `2026-11-15` và một chuỗi không hợp lệ. Trong source, cần viết bao nhiêu backslash cho mỗi token `\d`?

### Bài 4 — Chứa ba dấu nháy trong nội dung

Viết một text block có câu:

```text
The delimiter is """
```

Giải thích vì sao escape một dấu nháy là đủ để compiler không đóng text block ở vị trí đó.

### Bài 5 — Giữ dấu cách cuối dòng

Tạo text block chứa từ `key` theo sau bởi đúng một dấu cách và một newline. Dùng `\s` và giải thích vì sao một dấu Space thông thường ở cuối dòng source không phải cách đáng tin cậy để giữ trailing whitespace.

### Bài 6 — Điều khiển newline

Viết hai text block có cùng hai dòng mã nguồn:

- Một giá trị giữ newline giữa hai dòng.
- Một giá trị dùng line continuation để ghép nội dung thành một dòng.

In cả hai giá trị kèm dấu ngoặc vuông để quan sát newline cuối.

## 15. Tài liệu chính thức Java 17

- [JLS Java SE 17, §3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): cú pháp, delimiter, incidental indentation, escape processing và quy tắc nội dung text block.
- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): mục tiêu thiết kế, cú pháp và trạng thái chính thức của text block từ JDK 15.
- [Java 17 Language Guide — Text Blocks](https://docs.oracle.com/en/java/javase/17/language/text-blocks.html): hướng dẫn sử dụng text block trong Java 17.
- [JLS Java SE 17, §3.3 — Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.3): giải thích giai đoạn xử lý Unicode escape trong dịch mã nguồn.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): tra các phương thức chuỗi như `formatted`, `stripIndent` và các thao tác xử lý String.

Khi làm việc với text block Java 17, hãy tách ba lớp vấn đề: **delimiter quyết định phần nào là nội dung; indentation và vị trí dấu đóng quyết định khoảng trắng/newline; escape sequence quyết định các ký tự đặc biệt trong giá trị String**. Dấu nháy kép thường được viết trực tiếp, ba dấu nháy liên tiếp cần escape một dấu, còn backslash phải được nhân đôi khi muốn giữ nguyên trong kết quả. Hiểu đúng ba lớp này giúp tạo SQL, JSON, HTML, regex và văn bản nhiều dòng một cách rõ ràng, đồng thời tránh lỗi do tưởng text block là raw string.

