# Phân biệt text block, định dạng và nội suy dữ liệu trong Java

> **Bối cảnh Java 15 và hiện nay:** Text block và `String.formatted()` được chuẩn hóa/bổ sung từ Java 15, vẫn có mặt trên các JDK hiện đại. Bài học chỉ dùng cú pháp và API ổn định, không dựa vào các string template preview đã bị rút lại.

## 1. Ba việc khác nhau khi tạo một chuỗi

| Khái niệm | Giải quyết việc gì? | Ví dụ trong Java | Điều nó không làm |
| --- | --- | --- | --- |
| **Text block** | Viết **văn bản nhiều dòng cố định** trong mã nguồn mà vẫn giữ cấu trúc dễ đọc | `String html = """ ... """;` | Không tự hiểu HTML/JSON/SQL và không tự thay biến |
| **Định dạng (formatting)** | Đưa các **giá trị đối số** vào chuỗi theo specifier và quy tắc kiểu/locale | `String.format("Hi %s", name)`, `"Hi %s".formatted(name)` | Không tự escape dữ liệu theo quy tắc HTML/JSON/SQL |
| **Nội suy dữ liệu (interpolation)** | Kết hợp văn bản mẫu với giá trị động hoặc biểu thức theo cú pháp/quy tắc template | Có thể thực hiện bằng `formatted`, `replace` hoặc template engine tùy yêu cầu | Java 15 không có cú pháp nội suy `${name}` tích hợp, ổn định |

**Điểm phân biệt quan trọng:** *text block* là **cú pháp tạo `String`**; *formatting* là **thao tác API trên `String`**; *nội suy* là **mục tiêu chèn dữ liệu động**, có thể được thực hiện theo nhiều cách. Ba khái niệm có thể kết hợp, nhưng không phải tên gọi thay thế cho nhau.

Trong Java, đoạn sau chỉ tạo văn bản tĩnh:

~~~java
String name = "Lan";
String greeting = """
        Hello, ${name}!""";
System.out.println(greeting);
~~~

Đây là đoạn minh họa **bên trong một phương thức**, với stdout:

~~~text
Hello, ${name}!
~~~

Java không tự lấy biến `name` để thay các ký tự `${name}`. Bất kể một template engine khác có quy ước như vậy hay không, Java text block **không tự động nội suy**.

## 2. Text block: cú pháp literal nhiều dòng, không phải template engine

Ví dụ:

~~~java
String template = """
        Hello, %s!
        Order count: %d
        Thank you.
        """;
~~~

Text block ở trên có các đặc tính:

1. Mở bằng ba dấu nháy kép `"""` và một line terminator bắt buộc ngay sau dấu mở.
2. Nội dung được compiler chuẩn hóa newline về LF, loại bỏ **incidental indentation**, rồi diễn giải escape của Java; giá trị tạo ra là một `String` thông thường.
3. Dấu đóng nằm trên dòng riêng nên giá trị có LF ở cuối.
4. `%s` và `%d` **vẫn là các ký tự thật** trong giá trị mẫu. Chúng chỉ là format specifiers khi mẫu được chuyển cho một `Formatter`.

Vì thế, ngay sau phép gán, nếu in `template` thì stdout vẫn chứa chữ `%s` và `%d`. Compiler không tự định dạng hay chèn biến.

Lợi ích của text block là thể hiện rõ nhiều dòng HTML, JSON, SQL, đoạn mã Java hoặc văn bản; nó không tự xác thực cú pháp dữ liệu nhúng và không tự biến chuỗi thành JSON object hay HTML DOM.

### Text block có thể chứa dấu nháy và escape

~~~java
String jsonSample = """
        {
          "enabled": true,
          "name": "Java 15"
        }
        """;
~~~

Dấu nháy kép đơn lẻ của JSON không cần escape khi ở trong text block. Tuy nhiên, `\n`, `\t`, `\\` vẫn là những escape Java có ý nghĩa; text block không phải **raw string**. Khi nội dung mang định dạng JSON, backslash và ký tự xuống dòng còn có ý nghĩa ở *tầng JSON*.

## 3. Formatting: `String.format` và `String.formatted`

Sau khi đã có chuỗi `template` ở mục 2, có thể đưa dữ liệu vào:

~~~java
String result = template.formatted("Lan", 7);
~~~

Giá trị nhận được là:

~~~text
Hello, Lan!
Order count: 7
Thank you.
~~~

Vẫn có LF sau `Thank you.` do text block gốc. Hai API sau có cùng kết quả khi dùng cùng format template và đối số:

~~~java
String a = String.format("Hello, %s!", "Lan");
String b = "Hello, %s!".formatted("Lan");
boolean same = a.equals(b); // true
~~~

`String.formatted(Object... args)` có từ **Java 15**; theo đặc tả, tương đương gọi `String.format(this, args)`. Khi viết nội dung dài, có thể gọi trên chính text block:

~~~java
String summary = """
        User: %s
        Items: %d
        """.formatted("Lan", 4);
~~~

Formatter xử lý specifier ở **runtime**, sau khi compiler đã xử lý text block. Nó không đọc lại mã nguồn `.java` để chạy thuật toán lề và escape một lần nữa.

### Các format specifier phổ biến

| Specifier trong mẫu | Ý nghĩa | Ví dụ kết quả |
| --- | --- | --- |
| `%s` | Biểu diễn đối số dạng chuỗi (`toString` theo hợp đồng định dạng) | `"Hi %s".formatted("An")` → `Hi An` |
| `%d` | Số nguyên phù hợp | `"id=%d".formatted(7)` → `id=7` |
| `%04d` | Bổ sung số 0 để đủ chiều rộng tối thiểu 4 cho ví dụ dương | `"id=%04d".formatted(7)` → `id=0007` |
| `%.2f` | Số thực với hai chữ số thập phân | `String.format(Locale.ROOT, "%.2f", 12.5)` → `12.50` |
| `%%` | Một dấu phần trăm **thật** | `"%d%%".formatted(80)` → `80%` |
| `%n` | Xuống dòng theo **nền tảng runtime** | Có thể khác LF của text block |
| `%1$s` | Tham chiếu đối số số 1 | `"%1$s/%1$s".formatted("A")` → `A/A` |

Để dùng `Locale.ROOT` cần import `java.util.Locale` hoặc viết đầy đủ `java.util.Locale.ROOT`.

Đừng nhầm `%s` với `${name}`: `%s` chỉ được formatter phân tích **khi gọi API**; còn `${name}` trong Java text block là văn bản literal, không có formatter Java mặc định nào tự biến tên đó thành biến `name`.

### Locale và kết quả nhất quán

`"%.2f".formatted(12.5)` dùng format locale mặc định của tiến trình Java. Tùy locale, chữ số thập phân có thể dùng dấu chấm hoặc dấu phẩy. Khi định dạng cho giao thức, snapshot hoặc bài test cần kết quả ổn định, nên ghi locale:

~~~java
String output = String.format(
        java.util.Locale.ROOT, "price=%.2f", 12.5);
~~~

`output` là `"price=12.50"`. `String.formatted` không có overload trực tiếp với `Locale`; chọn `String.format(Locale, format, args)` khi cần chính sách rõ ràng.

### Những lỗi formatter thường gặp

- `"%d".formatted("Lan")` không hợp kiểu cho số nguyên; formatter có thể ném `IllegalFormatConversionException`.
- `"%s %s".formatted("Lan")` thiếu đối số, có thể ném `MissingFormatArgumentException`.
- Nếu gọi formatter trên mẫu có dấu `%` bình thường, cần viết `%%` để biểu diễn dấu phần trăm thật. Ví dụ `"width: 50%"` là chuỗi bình thường khi **không** gọi formatter, nhưng có thể gây lỗi khi gọi `formatted()` vì formatter xem `%` là ký hiệu bắt đầu format.
- `%n` dùng line separator của hệ điều hành; newline có sẵn trong text block được chuẩn hóa thành LF. Không trộn hai cách nếu hợp đồng output cần chính xác từng ký tự.
- Những đối tượng tùy ý có thể có `toString()` không đúng biểu diễn của JSON, XML hoặc SQL. `%s` không thay thế serializer.

## 4. Nội suy: khái niệm chèn giá trị động và các cách làm thực tế

Trong nhiều công nghệ, ký pháp `${name}` có thể biểu thị “tìm biến tên `name` rồi chèn vào văn bản”. Nhưng **bản thân Java 15 không hỗ trợ cú pháp này trong literal**.

Trong Java hiện đại, ví dụ sau sử dụng ba cơ chế có thật:

~~~java
String name = "Lan";

String byPlus = "Hello, " + name + "!";
String byFormatter = "Hello, %s!".formatted(name);
String byReplace = "Hello, ${name}!"
        .replace("${name}", name);
~~~

Cả ba có thể tạo `Hello, Lan!`, nhưng tính chất khác nhau:

- Toán tử `+` là cú pháp Java để nối chuỗi; phù hợp với các biểu thức đơn giản.
- `formatted` nhận **đối số theo vị trí**, hiểu `%s`, `%d`, `%.2f` và những quy tắc của `Formatter`.
- `replace` thực hiện **thay văn bản literal**, không hiểu template hay biểu thức Java; tên `${name}` vẫn chỉ là chuỗi để tìm.
- Template engine chuyên dụng có thể hỗ trợ biến theo tên, vòng lặp, điều kiện, chính sách escape theo ngữ cảnh và tổ chức mẫu tách khỏi code.

Một tính năng được nhắc trong tài liệu cũ là **String Templates** với cú pháp preview kiểu `STR."..."`. Nó từng được thử nghiệm ở Java 21 và Java 22 rồi **bị rút lại**; không nên dựa vào cú pháp preview này để dạy/lập trình tính năng Java ổn định. `String.formatted`, `String.format` và text block vẫn là những lựa chọn chính thức, còn phù hợp.

## 5. Kết hợp text block và formatter trong HTML

Ví dụ sử dụng giá trị **tĩnh, tin cậy**:

~~~java
String html = """
        <section>
          <h2>%s</h2>
          <p>%s</p>
        </section>
        """.formatted("Java 15", "Text blocks");
~~~

Kết quả:

~~~html
<section>
  <h2>Java 15</h2>
  <p>Text blocks</p>
</section>
~~~

Ta có thể phân lớp rõ ràng:

- **Text block:** tạo ba cặp thẻ theo dạng nhiều dòng, giữ mức thụt lề tương đối 2 dấu cách.
- **Formatter:** thay hai specifier `%s` bằng hai giá trị.
- **HTML renderer:** nếu chuỗi được gửi vào trình duyệt, trình duyệt mới phân tích thẻ và văn bản HTML.

Formatter chỉ chèn dữ liệu, **không mã hóa HTML theo ngữ cảnh**. Ví dụ này không phải cách an toàn để hiển thị `userInput` tùy ý; hãy dùng template engine có auto-escaping hoặc hàm escape theo đúng ngữ cảnh HTML text/attribute/URL.

### Giá trị động có nhiều dòng không được text block tự canh lề lại

~~~java
String value = "A\nB";
String text = """
        Item: %s""".formatted(value);
~~~

Giá trị lúc chạy:

~~~text
Item: A
B
~~~

Dòng `B` đứng ở cột đầu vì nó là một phần của **đối số được chèn tại runtime**. Compiler đã loại lề phụ của mẫu text block từ trước; formatter **không tự dịch** dòng mới trong đối số để thẳng với ký tự `A`. Nếu cần căn lề trong nội dung động, ứng dụng phải xử lý riêng trước khi chèn hoặc dùng công cụ template phù hợp.

## 6. JSON động: cần serializer, không chỉ thế chỗ `%s`

Một mẫu JSON tĩnh có thể viết bằng text block:

~~~java
String example = """
        {
          "name": "Lan",
          "enabled": true
        }
        """;
~~~

Nhưng đoạn sau **không phải** cách serialize dữ liệu tùy ý:

~~~java
// Ví dụ cảnh báo; không dùng trực tiếp với đầu vào bất kỳ.
String json = """
        {"name":"%s"}""".formatted(name);
~~~

Nếu `name` chứa dấu nháy kép, backslash, newline hoặc ký tự điều khiển, chuỗi JSON được tạo có thể sai cú pháp hoặc không đúng giá trị. Formatter không thực hiện JSON quoting/escaping.

Cách tiếp cận bền vững là dùng **JSON serializer** đang được dự án duy trì để biến object thành JSON; text block chủ yếu thích hợp cho mẫu/tài liệu JSON *cố định*. Điều này cũng áp dụng cho XML và các cấu trúc dữ liệu khác: cú pháp Java của mẫu không tự đảm bảo đầu ra hợp lệ theo ngôn ngữ đích.

### Escape trong Java và escape trong JSON là hai tầng khác nhau

Nếu muốn văn bản JSON có phần giá trị `"A\nB"`, tức là JSON chứa **hai ký tự `\` và `n`** để biểu diễn newline bên trong JSON string:

~~~java
String jsonText = """
        {"message":"A\\nB"}""";
~~~

Sau khi Java xử lý `\\` thành một backslash thật, JSON parser có thể diễn giải `\n` trong **dữ liệu JSON**. Viết `\n` đơn lẻ trong Java text block sẽ tạo LF thật ngay trong cặp nháy của JSON string và có thể làm JSON không hợp lệ. Dùng serializer là cách thích hợp cho dữ liệu động.

## 7. SQL: text block để viết truy vấn, `PreparedStatement` để bind dữ liệu

Text block giúp câu SQL dễ đọc:

~~~java
String sql = """
        SELECT id, display_name
        FROM users
        WHERE email = ?
        """;
~~~

Dấu `?` là **placeholder của JDBC**, không phải `%s` của `Formatter`. Trong đoạn mã dưới, giả sử `connection` là một `java.sql.Connection` đang mở và `email` là dữ liệu đầu vào:

~~~java
// Mảnh mã trong phương thức đã khai báo connection và email.
try (java.sql.PreparedStatement ps =
        connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (java.sql.ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
~~~

Đối số được truyền qua API và driver để bind **giá trị**; việc này giúp tránh SQL injection do ghép chuỗi SQL trực tiếp. Không thay bằng:

~~~java
// Sai hướng tiếp cận với email không tin cậy:
String unsafeSql = """
        SELECT id FROM users WHERE email = '%s'
        """.formatted(email);
~~~

`formatted` chèn văn bản vào SQL, **không bind tham số và không escape an toàn theo ngữ cảnh SQL**. Nếu tên bảng/cột phải thay đổi động, cần thiết kế/kiểm soát định danh riêng; placeholder giá trị `?` không dùng cho tên bảng/cột.

## 8. Các API chuỗi khác vẫn hữu dụng

| API hoặc cách tiếp cận | Điểm mạnh | Lưu ý |
| --- | --- | --- |
| `StringBuilder.append(...)` | Ghép nhiều phần trong vòng lặp hoặc khi cấu trúc chuỗi thay đổi dần | Cần tự quản lý delimiter/newline/escaping |
| `String.replace(...)` | Thay một đoạn văn bản literal cụ thể | Không giải thích biểu thức Java hay an toàn theo ngữ cảnh |
| `String.format(...)` | Định dạng đối số; có overload với `Locale` | Cẩn thận specifier, locale và dấu `%` |
| `String.formatted(...)` | Viết gọn khi mẫu đã là `String` hoặc text block | Dùng format locale mặc định |
| `java.text.MessageFormat` | Mẫu thông điệp có vị trí `{0}`, `{1}`, hữu ích khi quốc tế hóa UI | Cú pháp khác `Formatter`; có quy tắc escape dấu nháy đơn riêng |
| Template engine có auto-escaping | Mẫu HTML/ email phức tạp với dữ liệu động | Cần chọn thư viện được duy trì và escape đúng ngữ cảnh |
| JSON serializer | Tạo JSON hợp lệ từ object và dữ liệu động | Không thể thay bằng `%s` một cách an toàn |
| JDBC `PreparedStatement` | Truy vấn SQL với giá trị động, bind theo kiểu | Dành cho SQL, không phải công cụ format văn bản tổng quát |

Ví dụ `MessageFormat`:

~~~java
String msg = java.text.MessageFormat.format(
        "Hello {0}, items: {1}", "Lan", 3);
~~~

Kết quả là `Hello Lan, items: 3`. `MessageFormat` không sử dụng specifier `%s`, `%d`. Việc chọn API phải theo yêu cầu **định dạng số/ngày, ngôn ngữ hiển thị, số lượng mẫu, và ranh giới dữ liệu tin cậy**.

## 9. Chương trình Java độc lập, chạy được trên Java 17+

Lưu đúng file **`TextBlockFormattingDemo.java`**:

~~~java
import java.util.Locale;

public class TextBlockFormattingDemo {
    public static void main(String[] args) {
        String template = """
                Hello, %s!
                Total: %.2f
                """;

        String message = String.format(
                Locale.ROOT, template, "Lan", 12.5);
        System.out.print(message);

        String name = "Lan";
        String literal = """
                Hi, ${name}""";
        System.out.println("Literal marker: " + literal);

        String progress = """
                Progress: %d%%
                """.formatted(80);
        System.out.print(progress);

        String twoLines = """
                First
                Second""";
        System.out.println("Line count: " + twoLines.lines().count());

        String byPlus = "Hello, " + name + "!";
        String byFormat = "Hello, %s!".formatted(name);
        System.out.println("Equal result: " + byPlus.equals(byFormat));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac TextBlockFormattingDemo.java
java TextBlockFormattingDemo
~~~

**Stdout chính xác:**

~~~text
Hello, Lan!
Total: 12.50
Literal marker: Hi, ${name}
Progress: 80%
Line count: 2
Equal result: true
~~~

Giải thích theo thứ tự:

1. `template` là text block chứa placeholder `%s` và `%.2f`; `String.format(Locale.ROOT, ...)` tạo kết quả với dấu thập phân `.` ổn định.
2. `${name}` là các ký tự nguyên vẹn; không được Java tự đổi thành `Lan`.
3. `%d%%` được formatter biến thành `80%`.
4. `twoLines` là một `String` chứa 2 dòng; `lines().count()` trả về `2`.
5. Phép nối `+` và `formatted` có thể tạo cùng văn bản với ví dụ đơn giản, nhưng cơ chế định dạng khác nhau.

Có thể kiểm tra tương thích Java 15 từ JDK mới nếu trình biên dịch hỗ trợ target này:

~~~bash
javac --release 15 TextBlockFormattingDemo.java
~~~

Chương trình chỉ dùng những tính năng và API đã ổn định trong Java 15 hoặc từ trước. Không cần `--enable-preview`.

## 10. Các lỗi thường gặp và cách nhận diện

| Hiện tượng | Phân loại lỗi | Cách khắc phục |
| --- | --- | --- |
| Dòng trong mẫu có lề hoặc LF thừa | Text block: vị trí dấu đóng, incidental indentation | Kiểm tra giá trị chuỗi gốc, newline cuối |
| Kết quả vẫn có `%s` | Chưa gọi formatting | Gọi `template.formatted(args)` / `String.format` |
| Kết quả vẫn có `${name}` | Nhầm là Java có interpolation | Chọn API format, replace hoặc template engine |
| `IllegalFormatConversionException` | Formatter nhận đối số không hợp kiểu | Đối chiếu `%d`, `%f`, `%s` với từng argument |
| Dấu `%` trong CSS/văn bản làm formatter lỗi | Ký hiệu `%` bị hiểu là format | Khi format, đổi phần trăm literal thành `%%` |
| Số thập phân đổi dấu `.` thành `,` | Locale mặc định khác | Chỉ rõ `Locale` cho format cố định |
| Giá trị nhiều dòng chèn vào mẫu bị lệch lề | Formatter không tự căn lề chuỗi động | Chủ động định dạng dữ liệu nhiều dòng |
| JSON sinh ra sai khi tên có nháy kép/newline | Formatter không serialize JSON | Dùng JSON serializer |
| HTML chèn dữ liệu không tin cậy | Chưa escape theo ngữ cảnh HTML | Dùng template engine/escaping đúng ngữ cảnh |
| Dữ liệu người dùng nối trực tiếp vào SQL | SQL injection | Bind giá trị bằng `PreparedStatement` |

## 11. Bài tập tự đánh giá

**Bài 1.** Với đoạn sau, stdout là `%s` hay `Mai`?

~~~java
String name = "Mai";
String t = """
        Hi %s!""";
System.out.println(t);
~~~

**Đáp án:** `Hi %s!`. Text block tạo chuỗi mẫu; chưa có bước formatting. `t.formatted(name)` mới tạo `Hi Mai!`.

**Bài 2.** Viết cách tạo `Score: 8.50` ổn định khi runtime dùng locale khác nhau.

**Đáp án:**

~~~java
String result = String.format(
        java.util.Locale.ROOT, "Score: %.2f", 8.5);
~~~

`result` chính xác bằng `"Score: 8.50"`.

**Bài 3.** Tại sao `"Hello, ${name}"` trong text block không tự lấy biến `name`?

**Đáp án:** Java không quy định cú pháp nội suy `${...}` bên trong literal chuẩn; đó chỉ là ký tự bình thường. Có thể chọn phương thức `formatted` với `%s`, `replace` hoặc thư viện template phù hợp.

**Bài 4.** Với JSON động chứa tên `Alice "A"` hoặc một newline, có nên dùng `"{\"name\":\"%s\"}".formatted(name)`?

**Đáp án:** Không nên. Dùng JSON serializer để escape và quote theo quy tắc JSON, tránh lỗi cú pháp và sai dữ liệu.

**Bài 5.** Tại sao nên giữ SQL text block và giá trị của người dùng tách riêng?

**Đáp án:** Text block giữ cấu trúc SQL rõ ràng; `PreparedStatement` bind giá trị qua JDBC, tránh để ký tự trong dữ liệu bị hiểu thành cú pháp SQL.

**Bài 6.** `String.format(Locale.ROOT, "%.2f", value)` khác gì `"%.2f".formatted(value)`?

**Đáp án:** Cả hai dùng `Formatter` nhưng lệnh đầu chỉ rõ `Locale.ROOT`, lệnh sau dùng format locale mặc định của runtime. Trong báo cáo cần output không phụ thuộc môi trường, hãy chỉ định locale.

## 12. Tài liệu chính thức còn áp dụng

- **JEP 378 — Text Blocks (Java 15):** https://openjdk.org/jeps/378
- **Java SE 15 — `String` API (`formatted`, `format`, `lines`):** https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html
- **Java SE — `Formatter` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html
- **Java SE — `MessageFormat` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html
- **Oracle — Java Language Changes by Release (tình trạng rút lại String Templates preview):** https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html

**Ghi nhớ:** text block **định nghĩa văn bản mẫu nhiều dòng**; `String.format`/`formatted` **định dạng các đối số vào mẫu**; nội suy là **một mục đích xử lý dữ liệu**, cần thực hiện rõ ràng bằng API/engine phù hợp. Khi đưa dữ liệu động sang HTML, JSON hoặc SQL, tính đúng đắn và an toàn phụ thuộc **escaping, serialization hoặc binding theo định dạng đích**, chứ không tự sinh ra từ text block.
