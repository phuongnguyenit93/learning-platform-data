# Phân biệt text block với chuỗi thô không xử lý escape trong Java

## 1. Điểm mấu chốt: text block **không phải** raw string

Một **text block** trong Java là cách viết `String` nhiều dòng bằng dấu phân cách ba dấu nháy kép `"""`. Nó giúp các đoạn SQL, JSON, HTML hoặc thông điệp dễ đọc, nhưng **vẫn xử lý các escape sequence của Java**.

Ví dụ:

```java
String value = """
        First line
        Second line
        """;
```

Đây là đoạn khai báo trong một phương thức. Chuỗi thực tế chứa hai dòng và một ký tự xuống dòng ở cuối: `"First line\nSecond line\n"`.

So sánh khái niệm:

- **Text block của Java**: cú pháp nhiều dòng, xử lý lề chung (*incidental indentation*), chuẩn hóa dấu kết thúc dòng và giải mã escape sequence; kiểu kết quả là `java.lang.String`.
- **Raw string literal** theo nghĩa thông thường ở một số ngôn ngữ khác: nội dung được giữ gần như nguyên văn, dấu `\` không bị hiểu thành ký hiệu mở đầu escape của ngôn ngữ.
- **Java không có cú pháp raw string literal chuẩn để thay thế text block** trong phạm vi các phiên bản ổn định Java 17/21 đang dùng. Viết `"""..."""` **không** bật chế độ raw; dấu `\` trong đó vẫn mang ý nghĩa cú pháp Java.

**Ngữ cảnh Java 14:** Text blocks từng là preview trong Java 13/14 và trở thành tính năng chuẩn ở **Java 15** (JEP 378). Bài này chỉ dùng cú pháp đã ổn định, chạy trên JDK 17 trở lên, không cần `--enable-preview` hay cách viết preview cũ.

Cần nhớ một câu: **text block thay cách trình bày chuỗi nhiều dòng, không thay cơ chế escape của Java**.

## 2. Hai cách viết khác nhau có thể tạo cùng một `String`

Chuỗi Java thông thường dùng dấu `"..."`; text block dùng `"""` và yêu cầu xuống dòng sau delimiter mở. Cả hai đều tạo đối tượng `String`, và các escape vẫn được Java giải mã.

```java
String ordinary = "A\nB";
String block = """
        A
        B""";

System.out.println(ordinary.equals(block)); // true
```

Đoạn mã trong một phương thức. Cả hai chuỗi đều chứa `A`, một ký tự LF xuống dòng, rồi `B`; vì delimiter đóng của text block nằm ngay sau `B`, text block **không** có LF cuối chuỗi.

Text block cũng có thể dùng escape `\n` thay vì xuống dòng vật lý:

```java
String escaped = """
        A\nB""";

String physical = """
        A
        B""";

System.out.println(escaped.equals(physical)); // true
```

Điều này cho thấy nội dung `\n` trong text block **không bị giữ nguyên thành hai ký tự** backslash và chữ `n`: Java biến nó thành một ký tự xuống dòng, giống trong string literal thông thường.

## 3. Bảng các escape cần phân biệt

| Mã nguồn Java ở trong text block | Ý nghĩa khi tạo `String` | Khi cần giữ nguyên dấu `\` |
| --- | --- | --- |
| `\n` | Một ký tự LF (xuống dòng) | Viết `\\n` để được hai ký tự `\` và `n` |
| `\t` | Một ký tự tab | Viết `\\t` để được backslash và `t` |
| `\r` | Một ký tự carriage return | Viết `\\r` để được backslash và `r` |
| `\f` | Một ký tự form feed | Viết `\\f` nếu cần văn bản chứa `\f` |
| `\\` | Một ký tự backslash | Chính cách viết này dùng để giữ dấu `\` |
| `\"` | Một ký tự nháy kép | Dấu `"` riêng lẻ trong text block thường không cần escape |
| `\s` | Một dấu cách U+0020 | Dùng khi muốn giữ một space, đặc biệt ở cuối dòng |
| `\` ngay trước line terminator | Bỏ line terminator này (line continuation) | Nếu muốn giữ ký tự backslash thật, dùng `\\` và cân nhắc newline |
| Một escape không được Java hỗ trợ, ví dụ `\d` | **Lỗi biên dịch (illegal escape character)** | Viết `\\d` để tạo hai ký tự `\` và `d` |

Bảng mô tả **ký tự mã nguồn** trong text block; nếu copy phần ký tự ở cột đầu vào một `String` thường, ý nghĩa escape tương ứng vẫn là của Java.

Lưu ý: Escape của Java không giống escape của JSON, SQL, regex hoặc một ngôn ngữ khác. Nếu đưa một chuỗi vào nhiều tầng cú pháp, mỗi tầng có thể có quy tắc giải mã riêng. Ví dụ `\\d` ở **mã Java** tạo chuỗi gồm một backslash và chữ `d`, mà công cụ **regex** sẽ đọc như `\d` (mẫu chữ số).

### Nháy kép có còn cần escape không?

Text block giúp các dấu `"` thông thường trở nên dễ đọc:

```java
String json = """
        {"name": "Lan", "active": true}
        """;
```

Không cần `\"` cho mỗi dấu nháy kép trong JSON vì một hoặc hai dấu `"` không tự kết thúc text block. Nhưng nếu nội dung cần chứa **ba dấu nháy kép liên tiếp** có khả năng bị nhận thành delimiter đóng, phải escape thích hợp ít nhất một dấu nháy. Vì thế text block vẫn **không phải** một vùng văn bản “mọi ký tự đều nguyên xi”.

## 4. Ví dụ dễ sai nhất: đường dẫn Windows

Giả sử muốn lưu văn bản đường dẫn:

```text
C:\temp\file.txt
```

Trong mã Java, một dấu backslash đơn ở `\t` và `\f` được hiểu lần lượt là **tab** và **form feed**, chứ không phải ký tự phân cách thư mục. Ví dụ này **sai về ý nghĩa** dù `\t` và `\f` đều là escape hợp lệ:

```java
String wrongPath = """
        C:\temp\file.txt""";
```

Chuỗi thực tế không còn giống đường dẫn mong muốn: `\t` bị đổi thành tab, `\f` thành form feed. Một số đường dẫn chứa escape không được Java hỗ trợ (ví dụ `\U`) còn gây **lỗi biên dịch**.

Viết đúng bằng cách **nhân đôi dấu backslash ở mã nguồn**:

```java
String windowsPath = """
        C:\\temp\\file.txt""";

System.out.println(windowsPath.equals("C:\\temp\\file.txt")); // true
```

Ở đây hai literal Java được tạo ra giống nhau. Trong bộ nhớ, `windowsPath` chứa **mỗi vị trí phân cách chỉ một ký tự `\`**. Việc phải viết `\\` để có một backslash là bằng chứng rõ ràng rằng text block vẫn xử lý escape.

Đối với các đường dẫn thực sự trong ứng dụng, nên sử dụng `java.nio.file.Path` để biểu diễn và thao tác, thay vì tự ghép chuỗi phân cách theo hệ điều hành. Text block chỉ cải thiện cách viết giá trị nguồn cố định, không thay thế API đường dẫn.

## 5. Regular expression: hai tầng cú pháp Java và regex

Mẫu regex dùng `\d` để biểu diễn chữ số. Nhưng `\d` **không phải escape hợp lệ của Java**, nên không thể viết trực tiếp `\d` trong text block rồi hy vọng Java giữ nguyên. Ví dụ này **cố ý không biên dịch**:

```java
// String regex = """
//         \d{3}-\d{2}"""; // illegal escape character
```

Đúng: viết `\\d` trong mã nguồn Java để chuỗi tạo ra chứa `\d` mà regex engine hiểu:

```java
String regex = """
        \\d{3}-\\d{2}""";

System.out.println("123-45".matches(regex)); // true
System.out.println("ABC-DE".matches(regex)); // false
```

Chúng ta đang đi qua hai tầng:

1. **Java source → String:** `\\d` trong mã nguồn Java tạo `\d` trong chuỗi.
2. **String → regex engine:** `\d` trong chuỗi regex được công cụ so khớp diễn giải là lớp ký tự số.

Text block **không bỏ qua tầng thứ nhất**. Khi regex phức tạp, có thể xem xét thư viện, xây dựng pattern theo từng thành phần hoặc ghi chú rõ cách escape, thay vì coi text block là raw string.

## 6. JSON chứa dấu backslash: cần để ý cả hai lần giải mã

JSON cũng có escape riêng. Ví dụ một **giá trị JSON** muốn biểu diễn đường dẫn `C:\temp\file.txt` phải chứa chuỗi JSON với các backslash đã được escape theo JSON:

```json
{"path":"C:\\temp\\file.txt","note":"a\nb"}
```

Trong ví dụ JSON này, chuỗi `path` có **hai ký tự backslash trong văn bản JSON** ở mỗi vị trí để decoder JSON tạo một dấu backslash thật trong giá trị. `note` chứa escape JSON `\n` để decoder chuyển thành ký tự xuống dòng khi parse.

Khi **viết văn bản JSON đó trong mã Java**, phải xử lý thêm một tầng escape của Java:

```java
String json = """
        {"path":"C:\\\\temp\\\\file.txt","note":"a\\nb"}""";
```

Diễn giải bằng từng tầng:

| Điều muốn biểu diễn | Văn bản JSON sau khi tạo `String` | Mã Java trong text block |
| --- | --- | --- |
| Backslash trong giá trị path | `\\` | `\\\\` |
| Xuống dòng trong giá trị note | `\n` | `\\n` |
| Dấu nháy kép delimiting JSON | `"` | `"` (không cần escape riêng) |

Đọc từ **phải sang trái**: Java xử lý mã nguồn trước; JSON parser xử lý văn bản JSON sau. Nếu bỏ một tầng escape, JSON có thể sai hoặc mang giá trị khác mong đợi.

**Khuyến nghị thực tế:** Nếu nội dung JSON là **tĩnh và đã kiểm tra**, text block tiện để đặt fixture/mẫu. Nếu JSON có **giá trị động từ người dùng**, hãy dùng một thư viện JSON serializer (như Jackson trong dự án đã cấu hình) để serializer lo việc encode ký tự JSON; không tự nối chuỗi hoặc gọi `formatted(...)` rồi tin rằng text block sẽ tự làm JSON escaping.

## 7. Ngoài escape: text block còn xử lý indentation và line terminator

Một raw string literal lý tưởng thường gợi ý “giữ nguyên văn bản đã gõ”. Text block của Java lại có hai biến đổi quan trọng **ngoài escape sequence**:

### 7.1. Incidental indentation

```java
String example = """
        outer
          inner
        """;
```

Nội dung tương đương:

```java
String same = "outer\n  inner\n";
```

Java loại bỏ phần lề chung để mã nguồn có thể thụt lề đẹp theo lớp/phương thức. **Hai dấu cách có chủ ý** trước `inner` được giữ lại. Vị trí delimiter đóng và các dòng trắng cũng ảnh hưởng cách tính lề chung; nếu cần giữ khoảng trắng chính xác, hãy test chuỗi.

### 7.2. Chuẩn hóa line ending

Text block chuẩn hóa các loại line terminator trong nội dung nguồn thành **LF** (`\n`). Vì vậy nội dung Java thu được không nhất thiết giữ nguyên CRLF của file nguồn. Đừng coi việc xuống dòng trong text block là một cơ chế “raw bytes”.

Nếu cần line separator phụ thuộc hệ thống khi tạo văn bản gửi đi, có thể xây dựng rõ ràng tại bước xuất (ví dụ dùng `System.lineSeparator()` trong một pipeline thích hợp), nhưng không nên tự đổi mọi LF thành CRLF nếu định dạng đích đã quy định LF.

### 7.3. Dòng cuối

```java
String withNewline = """
        hello
        """;

String withoutNewline = """
        hello""";

System.out.println(withNewline.endsWith("\n")); // true
System.out.println(withoutNewline.endsWith("\n")); // false
```

Khi delimiter đóng nằm **trên dòng riêng** ngay sau dòng nội dung, chuỗi thường có LF cuối. Khi delimiter đóng nằm **ngay sau văn bản**, không có LF cuối do chỗ đóng đó. Cần kiểm tra khi tạo thông điệp, SQL, HTML hoặc test snapshot.

## 8. Hai escape chỉ có ý nghĩa đặc biệt khi trình bày nhiều dòng

### 8.1. `\s` giữ dấu cách cuối dòng

Java loại bỏ khoảng trắng cuối dòng không có chủ đích trong quá trình xử lý text block. Escape `\s` được diễn giải **sau bước loại khoảng trắng**, nên có thể dùng để giữ một dấu cách ở cuối một dòng:

```java
String text = """
        X\s
        """;

System.out.println(text.equals("X \n")); // true
```

`\s` tạo một ký tự space U+0020 ngay trước `\n`. Nó hữu ích khi whitespace cuối dòng có ý nghĩa trong định dạng đích, nhưng thường nên tránh phụ thuộc vào khoảng trắng cuối dòng nếu không cần thiết vì khó nhìn khi review code.

### 8.2. Backslash cuối dòng nối hai dòng vật lý

Java hỗ trợ **line continuation** trong text block: một dấu backslash ở cuối dòng nội dung có thể làm dấu xuống dòng đó bị loại khỏi kết quả:

```java
String joined = """
        hello\
        world
        """;

System.out.println(joined.equals("helloworld\n")); // true
```

Chuỗi có `helloworld` trên cùng một dòng và LF cuối của dòng `world`. Dấu `\` ở cuối dòng **không trở thành backslash thật** trong kết quả. Điều này khác hoàn toàn với cách tưởng tượng của một raw string.

Dùng line continuation khi cần format source đẹp nhưng không muốn ký tự newline trong kết quả; nếu nội dung cần giữ đúng hai dòng, **không đặt backslash nối dòng**.

## 9. Chương trình Java 17+ độc lập: kiểm tra từng khác biệt

Lưu toàn bộ mã vào **`Main.java`**. Chương trình tự in chuỗi ở dạng dễ quan sát: hàm `visible` hiển thị các ký tự xuống dòng, tab và backslash bằng escape text để tránh nhầm giữa ký tự thật với ký hiệu trong cửa sổ terminal.

```java
public class Main {
    static String visible(String value) {
        return value.replace("\\", "\\\\")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
                .replace("\r", "\\r");
    }

    public static void main(String[] args) {
        String escapedNewline = """
                left\nright""";
        String physicalNewline = """
                left
                right""";

        String tabCharacter = """
                A\tB""";
        String literalBackslashT = """
                A\\tB""";

        String path = """
                C:\\temp\\file.txt""";

        String regex = """
                \\d{3}-\\d{2}""";

        String json = """
                {"path":"C:\\\\temp\\\\file.txt","note":"a\\nb"}""";

        String oneSpace = """
                X\s
                """;

        String joined = """
                hello\
                world
                """;

        System.out.println("LINES_EQUAL=" + escapedNewline.equals(physicalNewline));
        System.out.println("TAB_CHARACTER=" + visible(tabCharacter));
        System.out.println("BACKSLASH_T=" + visible(literalBackslashT));
        System.out.println("PATH=" + visible(path));
        System.out.println("REGEX_MATCH=" + "123-45".matches(regex));
        System.out.println("JSON=" + visible(json));
        System.out.println("TRAILING_SPACE=" + oneSpace.equals("X \n"));
        System.out.println("JOINED=" + visible(joined));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Stdout chính xác:**

```text
LINES_EQUAL=true
TAB_CHARACTER=A\tB
BACKSLASH_T=A\\tB
PATH=C:\\temp\\file.txt
REGEX_MATCH=true
JSON={"path":"C:\\\\temp\\\\file.txt","note":"a\\nb"}
TRAILING_SPACE=true
JOINED=helloworld\n
```

**Chú ý cách đọc stdout:** `visible(...)` cố ý biến **một backslash trong chuỗi gốc thành hai backslash khi in**. Vì thế dòng `PATH=C:\\temp\\file.txt` *không* có nghĩa chuỗi `path` chứa hai backslash ở mỗi vị trí; đó chỉ là cách in để nhìn rõ dấu `\` thực tế. Tương tự, ở `TAB_CHARACTER=A\tB`, ký hiệu `\t` là hai ký tự **do `visible` tạo để mô tả một tab thật**; còn `BACKSLASH_T=A\\tB` hiển thị chuỗi gốc đã chứa backslash và `t`.

Kết quả `JSON=...` cũng là biểu diễn đã qua `visible`; không phải byte-for-byte nội dung JSON ban đầu. Để thực sự xác thực JSON, hãy đưa biến `json` (chưa qua `visible`) vào JSON parser.

Các trường hợp đã được kiểm chứng:

1. `LINES_EQUAL=true`: newline viết bằng `\n` và newline vật lý tương đương trong trường hợp này.
2. `TAB_CHARACTER` khác `BACKSLASH_T`: dấu `\` ảnh hưởng đến nội dung khi được/không được escape.
3. `PATH` giữ được dấu phân cách thư mục vì source dùng `\\`.
4. `REGEX_MATCH=true`: Java tạo chuỗi regex với `\d` để engine nhận mẫu chữ số.
5. `JSON`: văn bản có các tầng backslash đúng cho đường dẫn và escape xuống dòng của JSON.
6. `TRAILING_SPACE=true`: escape `\s` cho ra dấu cách ở cuối dòng.
7. `JOINED=helloworld\n`: dấu backslash cuối dòng đã loại newline vật lý ở giữa `hello` và `world`.

## 10. Những ngộ nhận và lỗi dễ mắc

| Ngộ nhận / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| “Ba dấu nháy kép là raw string” | Text block vẫn xử lý escape, indentation và line ending | Xem nó là `String` nhiều dòng, test ký tự thực |
| “`\t` trong text block là backslash + chữ t” | `\t` trở thành tab | Viết `\\t` nếu cần hai ký tự |
| “`\d` regex viết trực tiếp được trong text block” | Java không nhận `\d` là escape hợp lệ | Viết `\\d` trong mã nguồn |
| “Đường dẫn Windows chỉ cần một `\`” | Có thể tạo tab/form feed hoặc lỗi escape | Viết `\\`, ưu tiên `Path` khi thao tác đường dẫn |
| “JSON nằm trong text block không cần escape” | Java và JSON đều xử lý escape ở tầng riêng | Dùng đủ tầng escape hoặc serializer |
| “Text block giữ nguyên CRLF từ file nguồn” | Line terminator được chuẩn hóa | Kiểm tra LF trong kết quả |
| “Khoảng trắng thụt lề nào cũng được giữ” | Java bỏ incidental indentation và xử lý trailing spaces | Test `equals`; dùng `\s` khi cần |
| “Backslash cuối dòng chỉ là ký tự hiển thị” | Nó có thể nối dòng, loại newline trong kết quả | Đừng đặt `\` cuối dòng ngoài chủ đích |
| “Dùng text block thì SQL/HTML an toàn” | Không có bind SQL hay escaping HTML tự động | JDBC parameters, contextual HTML escaping |
| “`formatted` biến text block thành raw template” | `formatted` chỉ thay format specifier sau khi Java đã tạo String | Đảm bảo format và escape dữ liệu đúng ngữ cảnh |

### Cẩn trọng với các tầng định dạng khác

- **SQL:** text block không bind tham số và không ngăn SQL injection. Dùng `PreparedStatement` cho dữ liệu động.
- **HTML:** text block không escape XSS. Dùng template engine/escaping theo ngữ cảnh và chính sách bảo mật phù hợp.
- **Regex:** backslash có thể có ý nghĩa với cả Java và regex engine.
- **JSON:** dữ liệu động cần JSON serializer; nối chuỗi thủ công dễ tạo escape không đúng.
- **Java Unicode escapes:** xử lý `\uXXXX` của Java diễn ra rất sớm trong quy trình xử lý mã nguồn; đây là chủ đề riêng, nên tránh suy luận rằng text block giữ nguyên mọi chuỗi bắt đầu bằng `\u`. Khi cần giữ nội dung có ký hiệu Unicode escape như văn bản, kiểm tra chính xác chuỗi sau biên dịch.

## 11. Khi nào nên dùng text block?

**Nên dùng** khi nội dung có nhiều dòng và phần lớn là văn bản do chương trình kiểm soát: truy vấn SQL, JSON tĩnh, HTML tĩnh, template email hoặc nội dung thông báo. Nó giảm nối chuỗi `+` và cho bố cục nguồn dễ kiểm tra.

**Cần thêm công cụ hoặc một chiến lược khác** khi mục tiêu là:

- Giữ nguyên chính xác một lượng lớn dấu backslash/escape mà không muốn nhân đôi: cân nhắc tài nguyên văn bản riêng ở `resources` và đọc với charset xác định, hoặc tạo chuỗi bằng API/hàm chuyên dụng. Tệp ngoài không bị Java compiler giải mã escape như literal trong mã Java, nhưng bản thân quy trình đọc file vẫn cần quản lý encoding/newline.
- Sinh JSON/HTML/SQL với dữ liệu động: dùng serializer, contextual escaping, hoặc parameter binding tương ứng.
- Kiểm soát byte chính xác để ký/chữ ký số/giao thức: xác định rõ charset và line ending, kiểm thử byte đầu ra; text block chỉ đại diện cho `String`, không phải chuỗi byte nguyên gốc.

**Ghi nhớ:** Text block của Java là cách viết `String` nhiều dòng, **không phải raw string**. `\n`, `\t`, `\\`, `\s` và backslash nối dòng vẫn có ý nghĩa; thêm nữa, text block còn chuẩn hóa xuống dòng và lề. Với đường dẫn, regex và JSON, hãy đếm đúng các **tầng escape** và dùng công cụ chuyên dụng khi dữ liệu động hoặc bảo mật quan trọng.

### Tài liệu chính thức

- [JEP 378 — Text Blocks (Java 15)](https://openjdk.org/jeps/378).
- [Java Language Specification — Text Blocks (`3.10.6)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.6).
- [Java Language Specification — Escape Sequences (`3.10.7)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.7).
- [Java SE API — String.translateEscapes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#translateEscapes()).
