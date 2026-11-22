# Tránh coi text block hoặc `String.formatted()` là cơ chế chống chèn dữ liệu

> **Chủ đề:** Java 14 → *Escape và chuỗi* → **Tránh coi text block hoặc formatted là cơ chế chống chèn dữ liệu**. Text blocks từng được giới thiệu ở Java 13–14 dưới dạng preview, nhưng **đã ổn định từ Java 15 (JEP 378)**. Phương thức `String.formatted(Object...)` có từ Java 15. Bài học dùng Java 17+ và các quy tắc bảo mật vẫn áp dụng hiện nay, không yêu cầu preview.

## 1. Vấn đề: biểu diễn một chuỗi khác với bảo vệ nơi sử dụng chuỗi

~~~java
String username = "An";
String sql = """
        SELECT id
        FROM users
        WHERE username = '%s'
        """.formatted(username);
~~~

Đây là một đoạn Java hợp lệ (đặt trong phương thức), nhưng **không an toàn nếu `username` đến từ nguồn bên ngoài và chuỗi này được thực thi dưới dạng SQL**. Cú pháp dễ đọc không biến giá trị thành dữ liệu được cách ly với SQL.

Hãy phân biệt:

- **Text block (`"""`)** là cách viết `String` nhiều dòng. Java xử lý newline, indentation và escape sequences của **mã nguồn Java**, không tự phân tích SQL/HTML/JSON nằm trong chuỗi.
- **`String.formatted(args)`** định dạng đối số theo các dấu `%s`, `%d`... trong format string. Nó tạo ra một `String` mới, **không biết** kết quả sẽ dùng ở đâu và không tự thực hiện SQL binding, HTML output encoding, JSON serialization hay shell quoting.
- **Injection** có thể xảy ra khi dữ liệu không đáng tin cậy được đưa vào **vị trí có ý nghĩa cú pháp đối với bộ phân tích của ngữ cảnh đích** (SQL engine, browser, shell...), khiến dữ liệu bị hiểu là lệnh, toán tử, thẻ hoặc cấu trúc thay vì giá trị thông thường.

Ví dụ, `"<p>%s</p>".formatted(value)` chỉ ghép HTML source; nếu `value` chứa thẻ HTML và kết quả được parse như HTML, các thẻ đó có thể thay đổi DOM. Tương tự, dấu nháy đơn trong input SQL có thể kết thúc chuỗi literal SQL khi bạn nối trực tiếp.

**Rủi ro phụ thuộc vào điểm tiêu thụ (sink), không phụ thuộc vào toán tử tạo chuỗi (`+`, `StringBuilder`, text block hay `formatted`).**

### Sơ đồ tư duy

~~~text
INPUT chưa được tin cậy
       |
       +--> Kiểm tra hợp lệ: kiểu, độ dài, miền giá trị, quyền (cần thiết)
       |
       +--> KHI ĐƯA ĐẾN MỘT SINK:
              SQL:       PreparedStatement + bind parameter values
              HTML:      autoescape / context-specific output encoder
              JSON:      serializer đúng định dạng JSON
              OS shell:  executable và argument list tách biệt; hạn chế shell
              URL:       encode đúng thành phần và kiểm tra đích
              Logs:      structured logging và xử lý ký tự điều khiển
~~~

**Input validation không thay thế binding hoặc output encoding**; cả hai có nhiệm vụ khác nhau. Một tên người dùng hợp lệ vẫn có thể chứa dấu nháy hoặc ký tự Unicode đặc biệt.

## 2. Ba loại escape hoàn toàn khác nhau

| Công cụ/biến đổi | Tác dụng thực sự | Không bảo đảm |
| --- | --- | --- |
| Java `"\n"`, `"\\""`, `"\\"`, `\s` trong text block | Biểu diễn ký tự trong **`String` Java** sau bước biên dịch | Chống SQL injection, XSS, JSON injection |
| `"Hi %s".formatted(name)` | Thay `%s` bằng biểu diễn chuỗi của đối số | Escape đúng dấu nháy SQL/HTML/JSON/shell |
| `String.stripIndent()`, `translateEscapes()` | Xử lý thụt lề, escape Java ở mức chuỗi | Thực thi chính sách bảo mật của hệ thống đích |
| JDBC `PreparedStatement` + `setString` | Bind **giá trị** tách khỏi SQL structure | Tự kiểm tra quyền truy cập, mọi SQL identifier động |
| HTML text-node output encoding | Để dấu đặc biệt được hiển thị như **văn bản** ở HTML text context | An toàn trong JavaScript, CSS, URL hoặc event attributes |
| JSON serializer | Escape chuỗi theo **cú pháp JSON** và xuất value model | Xác thực mọi quy tắc nghiệp vụ, an toàn nếu đưa lại vào script tùy ý |

Không có hàm `escape(String)` chung dùng được cho mọi ngôn ngữ. Chuỗi đã encode cho HTML text có thể sai khi dùng làm giá trị database hoặc URL. Giữ dữ liệu **ở dạng dữ liệu** càng lâu càng tốt và xử lý đúng ngữ cảnh **ngay tại sink**.

## 3. SQL injection: không đưa dữ liệu vào text block SQL bằng `formatted`

### 3.1. Mẫu ghép chuỗi không an toàn

~~~java
String username = requestUserName; // lấy từ request, chỉ minh họa
String sql = """
        SELECT id
        FROM users
        WHERE username = '%s'
        """.formatted(username);

// Không chuyển SQL này cho Statement.executeQuery(sql).
~~~

Nếu input bằng:

~~~text
' OR '1'='1
~~~

thì kết quả là:

~~~sql
SELECT id
FROM users
WHERE username = '' OR '1'='1'
~~~

Ở đây `OR` và các dấu nháy từ dữ liệu đã trở thành **cú pháp câu SQL**. Tùy database, quyền và câu truy vấn, điều kiện lọc có thể bị thay đổi. Bài chỉ **in chuỗi**, không thực thi câu truy vấn nguy hiểm.

Đổi sang `"WHERE username = '" + username + "'"` hoặc `StringBuilder.append(username)` **không khắc phục lỗi**. Cách kết hợp Java String khác nhau nhưng điểm mất ranh giới dữ liệu vẫn vậy.

### 3.2. Cách đúng: text block chứa **`?`**, dữ liệu đi qua JDBC

~~~java
static boolean usernameExists(
        java.sql.Connection connection,
        String username) throws java.sql.SQLException {

    String sql = """
            SELECT 1
            FROM users
            WHERE username = ?
            """;

    try (java.sql.PreparedStatement ps =
                 connection.prepareStatement(sql)) {
        ps.setString(1, username);

        try (java.sql.ResultSet rs = ps.executeQuery()) {
            return rs.next();
        }
    }
}
~~~

Đây là **phương thức** đặt trong một lớp Java, dùng được trên JDK 17+ khi dự án có JDBC driver/`Connection` và bảng `users` phù hợp. Không thể chạy nó với database thực mà không cung cấp `Connection`.

Cơ chế an toàn nằm ở việc **tách SQL structure khỏi SQL value**:

1. `?` là parameter marker ở vị trí dữ liệu của câu SQL.
2. `ps.setString(1, username)` bind giá trị vào parameter đầu tiên. Dấu nháy và toán tử có trong `username` được xử lý như **dữ liệu**, không phải phần mở rộng câu SQL.
3. `executeQuery()` mới thực thi truy vấn theo cấu trúc đã chỉ định.
4. `try-with-resources` đóng tài nguyên đúng vòng đời.

Đừng viết `WHERE username = '?'`: dấu `?` nằm trong cặp nháy là nội dung literal trong SQL, không phải marker cần bind. Đừng viết `WHERE username = '%s'` rồi gọi `setString` sau đó: `setString` chỉ bind các marker thực có.

**PreparedStatement không xóa bỏ nhu cầu phân quyền:** cần bảo đảm chỉ truy xuất dữ liệu mà caller được phép xem; nếu ứng dụng đa tenant vẫn phải có điều kiện tenant và authorization.

### 3.3. Trường hợp SQL structure thực sự phải thay đổi

Không thể dùng một parameter marker để thay tùy ý **tên cột, tên bảng hoặc từ khóa SQL** như `ASC`/`DESC`. Khi người dùng chọn một chế độ sắp xếp, map lựa chọn đó sang token cố định do lập trình viên quy định:

~~~java
static String safeSortColumn(String userOption) {
    return switch (userOption) {
        case "name" -> "display_name";
        case "newest" -> "created_at";
        default -> throw new IllegalArgumentException(
                "Unsupported sort option");
    };
}
~~~

Đây là phương thức Java 17+ độc lập; nó không ghép trực tiếp input chưa tin cậy. Khi tạo SQL từ các tên cột cố định được allowlist, phần giá trị tìm kiếm vẫn phải được bind.

Lưu ý quan trọng khác: `LIKE ?` ngăn người dùng thêm **cú pháp SQL**, nhưng các ký tự `%` và `_` có thể vẫn là **wildcard** trong giá trị LIKE; nếu yêu cầu tìm kiếm ký tự chính xác, cần xử lý wildcard theo dialect. Khi dùng danh sách `IN` dài thay đổi, tạo số marker phù hợp hoặc dùng công cụ hỗ trợ bind danh sách, **không nối trực tiếp các phần tử vào SQL**. Tránh tự chế “escape dấu `'` bằng `replace`” để thay thế prepared statements: cú pháp và chế độ escape thay đổi theo database.

## 4. XSS/HTML injection: `.formatted()` không encode HTML

### 4.1. Ví dụ dễ gây hiểu lầm

~~~java
String userText = "<script>alert('x')</script>";
String html = "<p>%s</p>".formatted(userText);
~~~

Kết quả:

~~~html
<p><script>alert('x')</script></p>
~~~

Nếu chuỗi được đưa vào browser như **HTML source**, browser có thể parse thẻ `script` thay vì coi toàn bộ input là chữ. Việc HTML được khai báo bằng text block hay literal `"<p>..."` không khác nhau về điểm yếu này.

Một bản ghi đã lưu trong database **không tự trở thành trusted data**: nội dung do người dùng nhập từ trước vẫn có thể gây *stored XSS* khi hiển thị về sau.

### 4.2. Biện pháp tùy theo ngữ cảnh đích

| Ngữ cảnh đầu ra | Cách bảo vệ phù hợp |
| --- | --- |
| **Text giữa các thẻ HTML thường**, ví dụ `<p>...` | Template engine **autoescape** mặc định, HTML text encoder, hoặc tạo DOM text node |
| Giá trị một **HTML attribute** được quote | HTML **attribute** encoding, thuộc tính cố định; quy tắc bổ sung nếu attribute là URL |
| JavaScript string bên trong `<script>` | Tránh nối động; nếu bắt buộc, sử dụng encoder được thiết kế cho **JavaScript-in-HTML context** |
| Event handler attribute như `onclick` | Tránh đặt dữ liệu vào mã executable; dùng handler do ứng dụng kiểm soát |
| URL trong `href`/`src` | Validate scheme/host đích, encoding thích hợp cho URL và attribute |
| CSS hoặc raw HTML người dùng nhập | Không dùng HTML text encoder chung; CSS context handling hoặc HTML sanitizer có chính sách rõ |
| JavaScript DOM manipulation | Dùng `element.textContent = data` cho dữ liệu văn bản, tránh `innerHTML` khi chưa bảo vệ |

**Một bộ HTML escaping duy nhất không đủ cho tất cả các context.** Ví dụ encoder dành cho text node không có hợp đồng tự bảo vệ dữ liệu trong `onclick` hay một JavaScript literal.

### 4.3. Ví dụ học tập giới hạn ở HTML text node

Hàm dưới đây minh họa cách ký tự đặc biệt không còn được hiểu thành thẻ trong **văn bản nằm giữa `<p>` và `</p>`**:

~~~java
static String escapeHtmlText(String value) {
    return value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;");
}
~~~

Hàm này **chỉ nhằm minh họa**, không phải HTML sanitizer hay một bộ encoder đầy đủ cho mọi vị trí. Nó chưa giải quyết thuộc tính, URL, JS, CSS hay raw HTML. Trong ứng dụng thực tế, dùng **autoescaping của framework** hoặc thư viện như **OWASP Java Encoder** với hàm phù hợp đúng context; nếu cần chấp nhận HTML do người dùng viết, hãy dùng **HTML sanitizer** đáng tin cậy thay vì HTML text encoding.

Khi tạo DOM bằng JavaScript, API `textContent` có thể đưa dữ liệu trực tiếp vào text node mà **không cần tự chuyển thành HTML entity trước**. Nếu sau đó lại lấy dữ liệu và chèn vào `innerHTML`, cần xét lại rủi ro tại sink mới.

## 5. Chương trình Java 17+ hoàn chỉnh: quan sát ranh giới

Chương trình này **không kết nối database và không hiển thị HTML trong browser**; nó chỉ in chuỗi để minh họa sự khác biệt. Nhờ đó, người học không cần triển khai server hoặc driver JDBC.

**File: `StringBoundaryDemo.java`**

~~~java
public class StringBoundaryDemo {

    // Chỉ minh họa HTML text-node encoding.
    static String escapeHtmlText(String value) {
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;");
    }

    // Thấy rõ cả ký tự xuống dòng trong chuỗi.
    static String visible(String value) {
        return value.replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String username = "' OR '1'='1";

        // KHÔNG AN TOÀN nếu thực thi chuỗi này như SQL.
        String unsafeSql = """
                SELECT id
                FROM users
                WHERE username = '%s'
                """.formatted(username);

        // Đây mới là SQL template; cần bind value bằng JDBC.
        String parameterSql = """
                SELECT id
                FROM users
                WHERE username = ?
                """;

        String suppliedMarkup = "<script>alert('x')</script>";

        // Không được render trực tiếp chuỗi này như HTML.
        String unsafeHtml =
                "<p>%s</p>".formatted(suppliedMarkup);

        // Chỉ minh họa HTML text context, KHÔNG dùng cho mọi context.
        String encodedTextHtml =
                "<p>%s</p>".formatted(escapeHtmlText(suppliedMarkup));

        System.out.println("unsafeSQL=" + visible(unsafeSql));
        System.out.println("safeSQL=" + visible(parameterSql));
        System.out.println("boundValue=" + username);
        System.out.println("unsafeHTML=" + unsafeHtml);
        System.out.println("encodedTextHTML=" + encodedTextHtml);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StringBoundaryDemo.java
java StringBoundaryDemo
~~~

**Stdout:**

~~~text
unsafeSQL=SELECT id\nFROM users\nWHERE username = '' OR '1'='1'\n
safeSQL=SELECT id\nFROM users\nWHERE username = ?\n
boundValue=' OR '1'='1
unsafeHTML=<p><script>alert('x')</script></p>
encodedTextHTML=<p>&lt;script&gt;alert('x')&lt;/script&gt;</p>
~~~

**Giải thích:**

1. `visible` biến ký tự xuống dòng thành hai ký tự `\n` để minh họa rõ kết quả trên một dòng console.
2. `unsafeSQL` đã thay `%s` bằng chuỗi chứa SQL operator, cho thấy việc nội suy có thể làm thay đổi cấu trúc.
3. `safeSQL` mới **chỉ là chuỗi SQL có parameter marker `?`**, chưa bind dữ liệu hay chạy truy vấn. Muốn thật sự an toàn ở truy vấn, cần `connection.prepareStatement(parameterSql)` và `ps.setString(1, username)`.
4. `unsafeHTML` chứa một thẻ có thể được browser phân tích nếu xuất dưới dạng HTML.
5. `encodedTextHTML` chỉ biểu diễn cách mã hóa ký tự cho **HTML text node**; đây là demo có giới hạn, không phải một hàm dùng chung cho tất cả đầu ra HTML.

Một chuỗi riêng lẻ có thể được **in ra console tương đối vô hại**, nhưng lại nguy hiểm khi cùng chuỗi ấy được đưa vào SQL statement hoặc HTML parser. Đó là lý do phải theo dõi **data flow tới sink**, chứ không đánh giá an toàn chỉ theo biểu thức tạo chuỗi.

## 6. JSON: `formatted` không phải serializer

Ví dụ:

~~~java
String json = """
        {"displayName": "%s"}
        """.formatted(untrustedName);
~~~

Đây là **đoạn minh họa** có biến `untrustedName` đã tồn tại; không phải chương trình Java độc lập. Với input chứa dấu nháy kép, dấu backslash, xuống dòng hoặc control characters, chuỗi kết quả có thể **không phải JSON hợp lệ** hoặc có cấu trúc ngoài mong muốn.

**Cách đúng:** tạo một object/value model và dùng JSON serializer được bảo trì, đã chốt phiên bản và cấu hình, thay vì tự ghép phần giá trị vào JSON source. Với HTTP JSON, gửi header `Content-Type: application/json` phù hợp và vẫn validate schema, kiểu, kích thước, quyền truy cập.

**Không được nhầm “đúng JSON” với “an toàn khi chèn nguyên vào JavaScript bên trong HTML”.** Đó là hai sink khác nhau. Nếu server muốn truyền dữ liệu cho browser, ưu tiên endpoint JSON được parse bằng JSON parser hoặc cách nhúng dữ liệu được framework bảo vệ đúng ngữ cảnh.

Lưu ý nếu dữ liệu đã bị HTML encoded trước khi serialize JSON, kết quả có thể sai về nội dung do **double encoding**. Giữ nguyên dữ liệu logic và mã hóa chỉ khi đến ngữ cảnh đầu ra thực.

## 7. Shell, URL và log cũng có điểm yếu tương tự

### 7.1. Shell command

~~~java
// Ví dụ lỗi; KHÔNG thực thi với dữ liệu chưa tin cậy.
String command = "grep '%s' logfile.txt".formatted(userPattern);
new ProcessBuilder("sh", "-c", command).start();
~~~

Khi dùng `sh -c` hoặc một shell tương tự, chuỗi sẽ tiếp tục được **shell parser** phân tích. Text block, `formatted` hoặc nối chuỗi không tạo được ranh giới giữa input và các toán tử shell.

Khi có thể, truyền **từng đối số tách biệt** mà không gọi shell:

~~~java
// Ví dụ minh họa, chỉ chạy khi môi trường có grep
// và ứng dụng đã kiểm soát executable, options, file path.
ProcessBuilder builder =
        new ProcessBuilder("grep", "--", userPattern, "logfile.txt");
Process process = builder.start();
int exitCode = process.waitFor();
~~~

Hai đoạn trên là **minh họa**, không phải mã bắt buộc chạy trong bài. Lệnh `grep` và option `--` phụ thuộc executable/nền tảng. Bỏ shell parser tránh **shell injection** theo cách này, nhưng không tự ngăn **option injection** của công cụ, path traversal hoặc việc cho phép người dùng chọn tùy ý chương trình được thực thi. Nên kiểm soát executable và các đối số theo hợp đồng của chương trình cụ thể.

### 7.2. URL

~~~java
String url = "https://example.test/search?q=%s"
        .formatted(searchTerm);
~~~

Ký tự `&`, `#` và các ký tự đặc biệt có ý nghĩa trong URL. Với API dùng query parameter kiểu `application/x-www-form-urlencoded`, `URLEncoder.encode(searchTerm, StandardCharsets.UTF_8)` là một công cụ **cho giá trị query parameter**, không phải giải pháp encode toàn bộ URL, path segment hoặc mọi loại URL.

Ngoài encode đúng thành phần, khi URL đích do người dùng cung cấp, vẫn cần kiểm tra scheme, host, port và chính sách truy cập mạng để tránh các rủi ro như SSRF/open redirect. Việc tạo URL bằng `formatted` không tự đặt các hạn chế này.

### 7.3. Log

~~~java
String message = "User=%s".formatted(userName);
~~~

Nếu `userName` chứa newline hoặc control characters, một hệ thống log lưu text thuần có thể bị **log forging** hoặc rối cấu trúc. Ưu tiên structured logging, giới hạn dữ liệu và xử lý control chars theo quy tắc log; không log mật khẩu, token hoặc dữ liệu nhạy cảm. Placeholder của logging framework **không phải SQL parameter binding**.

Một tinh tế của `formatted`: với `"%s".formatted(untrusted)`, dấu `%` **nằm trong đối số** không bị xử lý đệ quy như format string. Nhưng nếu chính **format string** được cung cấp từ bên ngoài, các conversion/flags bất thường có thể ném `IllegalFormatException` hoặc tạo đầu ra không mong đợi. Nên giữ format string do ứng dụng kiểm soát. Đây là lỗi định dạng, **khác** với vấn đề SQL/XSS.

## 8. Thiết kế ứng dụng: bảo vệ theo sink và quyền truy cập

Bản chất của một biện pháp phòng ngừa hiệu quả:

- **SQL values:** luôn bind. Dùng text block để lưu **SQL template cố định** là một lựa chọn tốt.
- **SQL identifiers/keywords:** lấy từ allowlist cố định, không từ chuỗi user tùy ý.
- **HTML:** autoescaping và encoding **đúng context**; hạn chế hoặc sanitize raw HTML.
- **JSON:** serializer chuẩn, không thay `%s` thủ công vào JSON source.
- **Shell:** tránh `sh -c`; dùng API argument list; validate option/executable.
- **URL:** encode đúng thành phần; validate destination khi phù hợp.
- **Logs:** structured logging và giới hạn ký tự/nội dung.
- **Mọi tầng:** xác thực, authorization, kiểm tra tenant, kích thước dữ liệu, rate limiting và các bất biến nghiệp vụ vẫn cần tách biệt.

Không thể “sanitize một lần rồi dùng ở tất cả nơi”. Một chuỗi `O'Reilly & Sons <VIP>` cần được truyền **nguyên vẹn** đến JDBC parameter, nhưng cần **HTML text encoding** khi hiển thị giữa thẻ `p`, cần **JSON serializer** khi đưa vào response JSON, và cần **query value encoding** khi đưa vào URL. Đó là bốn cách tiêu thụ khác nhau.

Tránh blacklist các chữ như `SELECT`, `OR` hoặc các dấu `'`, `"`: nó vừa chặn dữ liệu hợp lệ vừa không bao phủ mọi cách biểu diễn tấn công. Validate theo **quy tắc miền nghiệp vụ**, còn injection prevention theo **ngữ cảnh diễn giải cú pháp**.

## 9. Bảng lỗi phổ biến

| Hiểu sai | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| “`"""` khiến SQL an toàn hơn.” | Văn bản SQL vẫn có thể chứa input nối trực tiếp | Dùng text block với `?` rồi `PreparedStatement.setXxx` |
| “`.formatted()` escape các dấu nháy.” | `%s` chỉ định dạng thành văn bản | Parameter binding / context output encoding |
| “Đổi từ `+` sang `StringBuilder` là sửa injection.” | Chỉ thay API tạo String, không đổi sink | Sửa điểm thực thi/trình bày dữ liệu |
| “Thay `'` bằng `''` cho mọi database là đủ.” | Dialect/encoding/cấu trúc khác nhau | Dùng prepared statements |
| “PreparedStatement thay được tên cột trong `ORDER BY`.” | Parameter markers không dành cho SQL identifiers | Map allowlist sang identifier cố định |
| “`LIKE ?` nghĩa là so khớp literal.” | `%` và `_` có thể có ý nghĩa wildcard | Dùng escape wildcard hợp dialect khi cần |
| “HTML text escape đủ cho `onclick` hoặc `href`.” | Event handlers và URL có cú pháp riêng | Tránh đưa input vào executable context, validate URL |
| “Java text block là JSON serializer.” | JSON không được escape cho input tùy ý | Dùng JSON serialization library |
| “`ProcessBuilder("sh", "-c", ...)` tách dữ liệu khỏi shell.” | Shell vẫn parse chuỗi | Không đi qua shell, chia executable/arguments |
| “Dữ liệu đọc từ DB chắc chắn an toàn khi đưa vào HTML.” | Có thể tạo stored XSS | Bảo vệ tại điểm render |
| “Đã bind query thì không cần phân quyền.” | Injection và authorization là hai bài toán | Kiểm tra quyền và phạm vi dữ liệu |
| “Giá trị có ký tự `%` sẽ được `formatted` định dạng lại.” | Đối số `%s` không phải format string mới | Phân biệt format string và đối số |

## 10. Checklist kiểm tra một đoạn code dùng text block/formatted

- [ ] Mình có biết chính xác **giá trị đầu vào đến từ đâu** và **chuỗi sẽ đi vào sink nào** không?
- [ ] Không ngầm coi dữ liệu đã an toàn vì cách viết chuỗi đẹp hoặc có escape Java.
- [ ] Trong SQL, dữ liệu nằm ở **bind parameters**, không phải được nối vào câu SQL.
- [ ] `?` thực sự được chuẩn bị và bind trước `executeQuery()`/`executeUpdate()`.
- [ ] SQL identifier/keyword động được chọn từ allowlist do code sở hữu.
- [ ] Trong HTML, có encoder **đúng vị trí**, autoescape hoặc API tạo text node.
- [ ] Nếu có raw HTML, đã dùng sanitizer và policy đáng tin cậy.
- [ ] JSON được tạo bằng serializer; không chèn trực tiếp các chuỗi chưa escape.
- [ ] OS command không sử dụng shell parser với input chưa tin cậy; executable/option/path được kiểm soát.
- [ ] URL được encode đúng thành phần và kiểm soát đích khi cần.
- [ ] Log không chứa secrets hoặc control chars gây làm giả dòng.
- [ ] Có test với input chứa `'`, `"`, `&`, `<`, `%`, newline, whitespace và Unicode.
- [ ] Mã không làm mất các kiểm tra **authorization, tenant và invariant nghiệp vụ**.

## 11. Bài tập tự luyện

1. Với input `' OR '1'='1`, giải thích vì sao câu `WHERE username = '%s'` sau `formatted` không còn giữ ý nghĩa ban đầu. Đổi sang `WHERE username = ?` và viết `ps.setString(1, value)`.
2. Sửa một JDBC method đang dùng text block và nối string thành method dùng `PreparedStatement`, `try-with-resources` và `ResultSet`.
3. Viết một allowlist sắp xếp cho hai cột `created_at` và `display_name`; đầu vào khác phải bị từ chối.
4. So sánh HTML output khi render `<b>hello</b>` như **text node** và như **raw HTML source**; giải thích vì sao không dùng một encoder cho `onclick`.
5. Viết mã dùng serializer của dự án để tạo JSON có giá trị chứa `"`, `\` và newline. So sánh với cách ghép `"%s"` trực tiếp.
6. Giải thích giới hạn của `ProcessBuilder` truyền argument list: vì sao vẫn cần kiểm tra executable, option và path?
7. Nếu người dùng nhập `O'Reilly`, tại sao cấm dấu nháy không phải chiến lược chung để bảo vệ truy vấn SQL?
8. Phân biệt `String.format("%s", value)`, `"%s".formatted(value)` và việc cho người dùng **tự cung cấp format string**.
9. Review một đoạn code ghép `.formatted(request.getParameter("id"))` vào SQL text block. Viết đề xuất thay đổi cụ thể, giữ text block nhưng dùng `?` và bind value.
10. Thiết kế test cho ba sink: SQL (không thay đổi structure), HTML text (không biến input thành tag), JSON (serializer tạo JSON parse được).

## 12. Tài liệu đối chiếu

- [Oracle – Programmer's Guide to Text Blocks, JDK 25](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): text block là cách biểu diễn String, với xử lý indentation/escape theo Java.
- [Oracle – String.formatted, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)): format string và các đối số, không có tác dụng tự động chống injection.
- [Oracle – Formatter, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): ý nghĩa conversion, flags và format exceptions.
- [Oracle – PreparedStatement, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html): bind values bằng `setString`/`setXxx`.
- [OWASP – SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet/): parameterized queries, allowlisting cấu trúc SQL và giới hạn của escaping thủ công.
- [OWASP – Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet/): HTML/attribute/JavaScript/URL contexts, autoescape và output encoding.

**Ghi nhớ:** Text block và `String.formatted()` giải quyết **cách tạo String trong Java**, không giải quyết **cách xử lý dữ liệu chưa tin cậy tại hệ thống đích**. SQL cần **parameter binding**; HTML cần **encoding đúng ngữ cảnh hoặc safe rendering**; JSON cần **serializer**; shell cần **tách các đối số và kiểm soát executable**. An toàn đến từ kiến trúc dữ liệu, điểm tiêu thụ và kiểm tra quyền, chứ không từ dấu `"""` hay `%s`.