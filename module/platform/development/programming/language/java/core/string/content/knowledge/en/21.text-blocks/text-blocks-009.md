# Java Text Block không tự nội suy biến và không tự escape cho định dạng đích

## 1. Text block là chuỗi ký tự, không phải template tự chạy

Từ Java 15 (ổn định), **text block** là cú pháp để viết chuỗi nhiều dòng bằng ba dấu nháy kép (`"""`). Giá trị tạo ra vẫn là một đối tượng `String`. Text block giúp mã nguồn dễ đọc khi cần viết HTML, JSON, SQL, XML hoặc thông báo dài; **nó không tự nội suy biến, không tự chạy biểu thức, cũng không tự bảo vệ nội dung cho định dạng bên ngoài**.

Ví dụ:

```java
String name = "Lan";

String message = """
        Xin chào, {{name}}!
        """;

System.out.println(message.strip()); // Xin chào, {{name}}!
```

`{{name}}` chỉ là các ký tự có trong chuỗi. Java không lấy biến `name` để thay vào đó. Tương tự, các ký hiệu `%s`, `$name`, `#{name}` hay `{{expression}}` nằm trong text block **không có tác dụng đặc biệt với bản thân text block**. Chúng chỉ trở thành placeholder nếu lập trình viên chủ động dùng một API có quy ước xử lý chúng.

**Hai câu hỏi cần tách biệt:**

1. **Nội suy/chèn dữ liệu:** Làm sao đưa giá trị một biến vào chuỗi? Có thể dùng `String.formatted`, `String.format`, `String.replace`, hoặc trình dựng template phù hợp.
2. **Escape/encode theo định dạng đích:** Giá trị đó phải được biểu diễn ra sao để không phá cú pháp hoặc đổi ý nghĩa HTML, JSON, SQL, XML, URI…? Cần bộ mã hóa, serializer, tham số hóa hoặc parser đúng cho *ngữ cảnh đích*.

Giải được câu hỏi (1) **không đồng nghĩa** với giải được câu hỏi (2).

## 2. Text block được Java xử lý như thế nào?

Cú pháp thông thường:

```java
String lines = """
        Dòng thứ nhất
        Dòng thứ hai
        """;
```

Một text block hợp lệ yêu cầu có dòng mới sau dấu mở `"""`. Java thực hiện quy tắc xử lý text block khi biên dịch: chuẩn hóa ký tự kết thúc dòng, loại mức thụt lề chung không cần thiết (*incidental indentation*), rồi xử lý escape sequence của Java. Vì vậy, text block **không phải raw string** theo nghĩa “ký tự nào viết ra sẽ được giữ y nguyên”.

Những điều cần nhớ:

- Nếu dấu đóng `"""` nằm trên **dòng riêng** thì LF ngay trước dấu đóng thuộc nội dung. Nếu chỉ cần bỏ đúng một LF cuối, hãy điều chỉnh dấu đóng hoặc loại đúng ký tự đó sau khi kiểm tra `endsWith`; `stripTrailing()` có thể bỏ cả whitespace khác.
- Java vẫn xử lý các escape như LF, tab, một dấu backslash, dấu cách `\s` và dấu backslash nối dòng. Đây là escape của Java, chưa phải escape của định dạng HTML, JSON hay SQL.
- Text block dễ viết dấu `"` trong nội dung hơn chuỗi Java thông thường, nhưng chuỗi ba dấu nháy liên tiếp dùng làm delimiter cần escape thích hợp nếu muốn xuất hiện như dữ liệu.
- Text block trả về `String`; không có tính năng tự gọi biểu thức Java, lấy biến từ scope, làm template động, hay chuyển đổi định dạng.

Một chuỗi đường dẫn minh họa:

```java
String path = """
        C:\\temp\\notes.txt
        """;
```

Trong ví dụ, mỗi **hai dấu backslash liên tiếp** ở mã Java được giải mã thành **một backslash** trong chuỗi. Một backslash đơn trước chữ `t` có thể tạo tab, còn trước chữ `n` có thể tạo newline. Text block vẫn tuân theo quy tắc escape của Java.

## 3. Chèn giá trị bằng `formatted()` hoặc API tương tự

Một phương thức tiện dụng từ Java 15 là `String.formatted(Object... args)`. Nó thực hiện định dạng theo quy ước của `Formatter`, tương tự `String.format`. Cú pháp này vẫn là **lời gọi phương thức tường minh**, không phải khả năng tự nội suy của text block:

```java
String name = "Lan";
int score = 95;

String report = """
        Người học: %s
        Điểm: %d
        """.formatted(name, score);

System.out.print(report);
// Người học: Lan
// Điểm: 95
```

Ở đây `%s` và `%d` chỉ được xử lý **khi gọi** `formatted(name, score)`. Nếu bỏ lời gọi đó, text block vẫn chứa `%s` và `%d` nguyên văn. Nếu định dạng có dấu phần trăm nguyên văn, khi gọi `formatted` cần viết `%%` trong format string; ví dụ `"Tiến độ: 80%%".formatted()` trả `"Tiến độ: 80%"`. Định dạng sai hoặc thiếu tham số có thể phát sinh `IllegalFormatException` và các lớp con của nó.

Có thể dùng `replace("{{name}}", name)` cho dữ liệu đơn giản, vì `String.replace` thay chuỗi nguyên văn. Nhưng cách đó cũng **không tự escape** nội dung được chèn. Ngoài ra, một hệ thống template thực thụ có thể cần xử lý điều kiện, vòng lặp, tên biến hợp lệ và ngữ cảnh HTML; không nên biến `replace` thành bộ template tổng quát mà không có thiết kế rõ ràng.

## 4. Chương trình Java 17+ chạy độc lập

Tạo file `TextBlockContextDemo.java`:

```java
public class TextBlockContextDemo {
    // Chỉ dùng khi chèn vào text node HTML, không phải mọi ngữ cảnh HTML.
    private static String escapeHtmlText(String input) {
        return input.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;");
    }

    public static void main(String[] args) {
        String name = "Lan <Admin> & Co";

        // Không nội suy: placeholder vẫn nguyên vẹn.
        String literal = """
                Hello, {{name}}!
                """;
        System.out.println("Literal placeholder: " + literal.strip());

        // Có chèn dữ liệu nhưng chưa escape HTML.
        String htmlTemplate = """
                <p>Hi, %s!</p>
                """;
        System.out.println("HTML raw: "
                + htmlTemplate.formatted(name).strip());

        // Escape theo ngữ cảnh text node HTML trước khi chèn.
        System.out.println("HTML escaped: "
                + htmlTemplate.formatted(escapeHtmlText(name)).strip());

        // Chèn thẳng tên chứa dấu " sẽ phá cú pháp chuỗi JSON.
        String jsonTemplate = """
                {"name":"%s"}
                """;
        String jsonName = "Lan \"A\"";
        System.out.println("JSON raw: "
                + jsonTemplate.formatted(jsonName).strip());

        // Text block vẫn xử lý escape của Java.
        String path = """
                C:\\temp\\notes.txt
                """;
        System.out.println("Path: " + path.strip());

        // Với dấu đóng trên dòng riêng, text block có newline cuối.
        System.out.println("Trailing newline: "
                + literal.endsWith("\n"));

        System.out.println("Placeholder unchanged: "
                + literal.contains("{{name}}"));
    }
}
```

Biên dịch, chạy (Java 17 hoặc mới hơn):

```bash
javac TextBlockContextDemo.java
java TextBlockContextDemo
```

Đầu ra:

```text
Literal placeholder: Hello, {{name}}!
HTML raw: <p>Hi, Lan <Admin> & Co!</p>
HTML escaped: <p>Hi, Lan &lt;Admin&gt; &amp; Co!</p>
JSON raw: {"name":"Lan "A""}
Path: C:\temp\notes.txt
Trailing newline: true
Placeholder unchanged: true
```

Phần `HTML raw` cho thấy việc đưa `name` vào `%s` chỉ chèn dữ liệu. Nếu hiển thị như HTML, các ký tự `<` và `&` trong dữ liệu có thể bị diễn giải thành markup hoặc entity, thay vì được hiển thị theo nghĩa văn bản. Hàm `escapeHtmlText` chủ đích minh họa **ngữ cảnh text node**, nơi các ký tự `&`, `<`, `>` được mã hóa tương ứng. Nó không phải bộ mã hóa cho mọi ngữ cảnh HTML như thuộc tính, URL, JavaScript hoặc CSS.

Phần `JSON raw` tạo văn bản **JSON không hợp lệ** vì dấu nháy kép trong `jsonName` không được escape theo JSON. Không nên xem chuỗi vừa tạo là đối tượng JSON đã được serialize đúng.

## 5. Java escape khác escape của định dạng đích

Khi viết JSON, HTML hoặc câu truy vấn trong text block, có thể có **hai tầng xử lý**:

1. **Tầng Java source:** Văn bản trong text block được Java biến thành `String`, có xử lý dấu xuống dòng, thụt lề và escape sequence Java.
2. **Tầng định dạng đích:** Nội dung `String` được đưa cho một bộ đọc khác (trình duyệt HTML, parser JSON, cơ sở dữ liệu, v.v.), nên phải tuân thủ cú pháp và quy tắc mã hóa của hệ thống nhận.

Một ví dụ với dấu `\\` trong JSON:

```java
String jsonLiteral = """
        {"path":"C:\\\\data\\\\file.txt"}
        """;
System.out.println(jsonLiteral.strip());
// {"path":"C:\\data\\file.txt"}
```

Trong ví dụ này, **bốn dấu backslash liên tiếp** ở Java source trở thành **hai dấu backslash** trong văn bản JSON. Hai dấu backslash của JSON biểu diễn một backslash trong giá trị đường dẫn sau khi JSON được parse. Đây chỉ là ví dụ với nội dung cố định; với dữ liệu động, nên dùng JSON serializer.

Với dữ liệu **động**, nên giao việc tạo JSON cho thư viện serializer: truyền giá trị Java như `String`, số, list hoặc object vào API của thư viện, để serializer phát sinh dấu nháy và escape đúng chuẩn. `String.formatted` không biết phần chèn vào nằm trong JSON string, JSON number hay bên ngoài một JSON value.

## 6. Escape theo đúng ngữ cảnh mà dữ liệu sẽ xuất hiện

| Định dạng đích | Rủi ro khi chèn thẳng dữ liệu vào text block | Cách làm đúng |
| --- | --- | --- |
| HTML **text node** | `<`, `&` có thể bị hiểu là markup/entity. | Escape văn bản theo HTML text context, hoặc API tạo text node an toàn. |
| Thuộc tính HTML | Dấu `"` hoặc `'` có thể đóng giá trị thuộc tính; URL attribute còn có chính sách scheme riêng. | Encoder theo ngữ cảnh thuộc tính và kiểm tra URL/scheme khi cần; ưu tiên API DOM/template có auto-escaping đúng ngữ cảnh. |
| JSON | `"`, `\\`, ký tự điều khiển và newline trong dữ liệu làm hỏng chuỗi JSON nếu chèn thẳng. | Serializer JSON hoặc API viết JSON có phân biệt value/object/array. |
| XML | Các ký tự đặc biệt và vị trí text/attribute khác nhau có quy tắc riêng. | API XML/serializer; tránh xây XML bằng nối chuỗi tùy tiện. |
| SQL | Dữ liệu chứa `'` hoặc cú pháp SQL có thể thay đổi câu truy vấn khi nối/chèn vào SQL text. | `PreparedStatement` với **tham số bind**, không dùng `formatted` để chèn giá trị SQL. |
| URI / URL | Khoảng trắng, `?`, `&`, `#` có vai trò phân tách các thành phần URI. | Dùng API xây URI và encode đúng từng thành phần (path, query parameter, v.v.). |
| Regular expression | `.`, `*`, `[`, `\\` là toán tử regex; replacement còn có `$`. | `Pattern.quote` cho mẫu tìm nguyên văn, `Matcher.quoteReplacement` cho replacement nguyên văn. |

Lưu ý một giá trị “đã escape HTML” **không vì thế mà an toàn trong JavaScript hoặc SQL**. Quy tắc escape thuộc về ngôn ngữ/ngữ cảnh **nhận**, không thuộc về cú pháp text block. Không mã hóa tùy tiện nhiều lượt hoặc áp cùng một encoder cho mọi nơi, vì điều đó có thể làm sai dữ liệu hoặc tạo lỗi double encoding.

### SQL: text block giúp đọc câu truy vấn, tham số bind giúp truyền dữ liệu

Đây là đoạn minh họa bên trong một phương thức đã có `Connection connection` và `String username` từ `java.sql`:

```java
String sql = """
        SELECT id, username
        FROM users
        WHERE username = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, username);
    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getLong("id"));
        }
    }
}
```

Các kiểu `PreparedStatement` và `ResultSet` cần import từ `java.sql`. Đây là mã minh họa có phụ thuộc vào kết nối/cơ sở dữ liệu, **không phải chương trình chạy độc lập**. `?` là placeholder dành cho **giá trị SQL được bind**, không phải ký hiệu được text block tự nội suy. Dù `username` chứa dấu nháy hoặc ký tự SQL, `setString` truyền nó theo cơ chế tham số của JDBC. Với **tên bảng hoặc cột động**, placeholder giá trị không thay thế được identifier; phải dùng danh sách tên hợp lệ được cho phép rõ ràng, không nối identifier tùy ý từ đầu vào.

### JSON: ưu tiên serializer khi giá trị đến từ bên ngoài

Với:

```java
String name = "Lan \"A\"";
String json = """
        {"name":"%s"}
        """.formatted(name);
```

`json` chứa `{"name":"Lan "A""}` và không hợp lệ. Việc thay `"` bằng `\\"` trong riêng một ví dụ chưa giải quyết đầy đủ escape `\\`, ký tự điều khiển, xuống dòng và kiểu dữ liệu phức tạp. Dùng JSON serializer, đưa `name` như một **giá trị String**, và để thư viện tạo văn bản JSON hợp lệ thay vì tự nối/format chuỗi.

## 7. Các sai lầm thường gặp

**Tưởng `{{name}}` hoặc `%s` được thay ngay khi khai báo.** Text block không xử lý template. Chỉ có lời gọi `formatted`, `replace` hoặc template engine được thiết kế riêng mới chủ động thực hiện phép chèn.

**Tưởng `formatted` tự escape HTML/JSON.** `formatted` dùng quy tắc `Formatter`, không biết ngữ cảnh cú pháp đích; giá trị có `<`, `"`, `$`, dấu xuống dòng hoặc escape của định dạng có thể làm kết quả sai hoặc nguy hiểm.

**Tưởng text block là raw string.** Java vẫn xử lý escape Java, bỏ thụt lề chung và có thể giữ LF cuối. Hãy kiểm tra giá trị chuỗi thực tế trước khi gửi sang parser của định dạng đích.

**Lẫn lộn escape Java với escape JSON.** Mẫu dấu `\\` trong Java source phải đi qua tầng Java **trước** khi văn bản được parser JSON đọc. Nếu cố tự tạo JSON, rất dễ thiếu hoặc thừa escape; ưu tiên serializer JSON.

**Dùng text block như cơ chế chống SQL injection.** Text block chỉ giúp câu SQL nhiều dòng dễ đọc. Chèn `username` bằng `formatted(username)` bên trong SQL không có cơ chế tham số hóa; phải bind tham số qua `PreparedStatement`.

**Đặt dữ liệu vào sai ngữ cảnh HTML.** Mã hóa dành cho HTML text node không tự động hợp lệ cho thuộc tính HTML, URL, JS hay CSS. Chọn encoder hoặc template engine phù hợp với vị trí dữ liệu.

**Quên dấu phần trăm khi gọi `formatted`.** Chuỗi `"Đạt 90%"` ở text block là chuỗi bình thường, nhưng khi đưa cho `formatted()` dấu `%` được xem như bắt đầu một format specifier. Nếu muốn ký hiệu phần trăm nguyên văn trong chuỗi định dạng, dùng `%%`.

## 8. Bài tập kiểm tra

1. Cho `String user = "Mai"; String s = """` rồi nội dung `Hi, {{user}}!` và dấu đóng trên dòng riêng. `s` có tự trở thành `"Hi, Mai!"` không? Vì sao?
2. Viết một text block làm phần trình bày HTML `<p>Xin chào, %s</p>`. Nêu rõ thời điểm `formatted` chèn dữ liệu và bước nào phải thực hiện để bảo vệ **HTML text node**.
3. Với biến `name = "Lan \\"A\\""`, giải thích vì sao `{"name":"%s"}`.formatted(name) không tự sinh JSON hợp lệ.
4. Cho SQL có text block `WHERE email = ?`, giải thích vai trò của `PreparedStatement.setString` và vì sao không nên chuyển thành `WHERE email = '%s'` rồi `formatted(email)`.
5. Với đường dẫn chứa dấu `\\`, giải thích khác nhau giữa **escape trong Java source** và **escape của JSON runtime**.

**Ghi nhớ:** Text block là cú pháp viết `String` nhiều dòng dễ đọc. Việc chèn biến phải gọi API tường minh; việc escape hoặc tham số hóa phải dựa trên **định dạng và ngữ cảnh đích**. Hai trách nhiệm này không được nhầm lẫn.