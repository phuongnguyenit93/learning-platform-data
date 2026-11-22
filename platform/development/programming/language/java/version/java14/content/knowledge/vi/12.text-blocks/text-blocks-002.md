# Các bổ sung Java 14 được giữ trong text block chính thức từ Java 15

## 1. Mục tiêu, bối cảnh và tính tương thích

**Text block** là một dạng literal của `java.lang.String`, viết bằng ba dấu nháy kép `"""` để nhúng văn bản nhiều dòng (JSON, HTML, SQL, mẫu thông báo...) một cách dễ đọc. Hai khả năng quan trọng được **bổ sung trong Java 14** (JEP 368, *second preview*) và **giữ nguyên khi text blocks chính thức từ Java 15** (JEP 378) là:

1. **`\s`:** biểu diễn một ký tự **SPACE U+0020**, đặc biệt hữu ích để giữ dấu cách cuối dòng mà thuật toán xử lý text blocks thường loại bỏ.
2. **`\` theo ngay sau bởi ký tự kết thúc dòng:** *line continuation*; loại bỏ dấu gạch chéo ngược và newline nguồn khỏi giá trị `String`, cho phép xuống dòng trong source mà không xuống dòng trong dữ liệu.

| Phiên bản Java | Trạng thái | Kiến thức còn phù hợp |
| --- | --- | --- |
| Java 13 — JEP 355 | Text blocks preview lần đầu | Nền tảng cú pháp và xử lý lề |
| Java 14 — JEP 368 | Preview lần hai | **Bổ sung `\s` và `\` + line terminator** |
| Java 15 — JEP 378 | **Chính thức** | Hai escape này được giữ lại trong ngôn ngữ |
| Java 17, 21 và các bản hiện đại | Tính năng ổn định | Sử dụng bình thường trong mã dự án |

Điểm cần phân biệt: **Java 14 là mốc bổ sung cú pháp, không phải mức Java cần chọn cho ví dụ hiện nay.** Dùng JDK 17+ và `javac --release 17` để thực hành; không bật `--enable-preview` cho text blocks chính thức. Bài không dựa vào bất kỳ hành vi legacy hoặc cú pháp preview chưa ổn định nào.

## 2. Nhắc lại quy tắc của text block

```java
String html = """
        <html>
          <body>Hello</body>
        </html>
        """;
```

- Mở bằng `"""` rồi **phải có ký tự kết thúc dòng** trước nội dung. Không được viết `String x = """abc""";` trên một dòng.
- Nội dung nhiều dòng nằm giữa dấu phân định mở và đóng; dấu nháy kép `"` thông thường trong JSON/HTML thường không cần escape.
- Dấu `"""` đóng có thể nằm trên dòng riêng hoặc sát ký tự cuối của nội dung; vị trí đó ảnh hưởng đến cách xác định lề và việc có newline cuối.
- Giá trị nhận được vẫn là `String` bình thường: có thể gọi `equals`, `formatted`, `lines`, v.v.
- Text block **không tự** nội suy tên biến, parse JSON hay tạo kết nối SQL. Nó chỉ là cú pháp biểu diễn chuỗi.

Ví dụ trên có giá trị tương đương:

```java
String html = "<html>\n"
        + "  <body>Hello</body>\n"
        + "</html>\n";
```

Ở đây hai dấu cách trong dòng `<body>` vẫn được giữ là **lề có chủ ý**, còn phần lề căn chỉnh source code chung đã được loại.

Ví dụ **cố ý sai cú pháp**:

```java
// Không biên dịch được: không có newline sau dấu mở.
String invalid = """hello""";
```

`javac` có thể báo `illegal text block open delimiter sequence, missing line terminator`. Nếu chỉ có một dòng ngắn, viết `"hello"` sẽ rõ hơn.

## 3. Bổ sung thứ nhất: `\s` giữ dấu cách có chủ ý

### 3.1. `\s` là một dấu cách

```java
String s = "A\sB";
System.out.println(s.equals("A B")); // true
```

Trong Java 15+ `\s` có nghĩa là **một SPACE**, mã Unicode U+0020, ở cả literal `"..."` truyền thống và text block. Nó **không** đại diện cho mọi loại khoảng trắng, không phải tab hoặc LF.

### 3.2. Vì sao phải dùng `\s` ở cuối một dòng?

Text blocks có cơ chế tự **loại trailing whitespace** (whitespace ở cuối mỗi dòng). Đây là thiết kế hữu ích vì các dấu cách cuối dòng thường không nhìn thấy và dễ bị editor/formatter tự xóa. Tuy nhiên, nếu giao thức hay một trường dữ liệu yêu cầu đúng số dấu cách, ta phải đánh dấu sự hiện diện của chúng.

```java
String padded = """
        red  \s
        green\s
        blue \s
        """;
```

Mỗi dòng có **6 ký tự trước `\n`**:

| Source content | Nội dung dòng trong giá trị String | Số ký tự |
| --- | --- | --- |
| `red  \s` | `red` và 3 dấu cách | 6 |
| `green\s` | `green` và 1 dấu cách | 6 |
| `blue \s` | `blue` và 2 dấu cách | 6 |

Kiểm chứng:

```java
System.out.println(
        java.util.Arrays.toString(
                padded.lines().mapToInt(String::length).toArray()
        )
); // [6, 6, 6]
```

**Cơ chế:** bước loại trailing whitespace diễn ra **trước** bước dịch escape. Khi đang loại dấu cách cuối dòng, `\s` còn là các ký tự trong source, chưa phải một dấu cách thật, nên nó đóng vai trò “hàng rào” và **giữ lại** những dấu cách đứng ngay trước. Đến bước dịch escape, `\s` mới trở thành thêm một dấu cách.

Nếu viết `red   ` bằng ba dấu cách cuối dòng mà không dùng escape, compiler có thể loại chúng; không nên tin rằng khoảng trắng phía sau chữ trong mã nguồn sẽ được giữ như mong muốn.

### 3.3. `\s` trong Java string khác `\s` trong regular expression

Đây là một bẫy dễ nhầm:

```java
java.util.regex.Pattern onlySpace =
        java.util.regex.Pattern.compile("\s+");

java.util.regex.Pattern anyWhitespace =
        java.util.regex.Pattern.compile("\\s+");
```

`"\s+"` đã được Java compiler dịch thành chuỗi gồm **dấu cách + dấu `+`**, vì vậy regex chỉ tìm space. Ngược lại, `"\\s+"` cung cấp cho regex engine hai ký tự `\` và `s` cùng `+`, nên biểu thức chính quy có nghĩa là **một hoặc nhiều whitespace theo quy tắc regex**.

Khi tạo một regex bằng text block cũng vậy: backslash vẫn phải được xử lý theo quy tắc Java String; text block không phải *raw string*.

## 4. Bổ sung thứ hai: `\` + xuống dòng là line continuation

Đặt dấu `\` **ngay trước line terminator trong nguồn** để loại bỏ chính newline ấy khỏi chuỗi cuối:

```java
String joined = """
        left \
        right\
        """;
```

Giá trị chính xác là `"left right"`, **không chứa `\n` cuối**. Có thể kiểm thử:

```java
System.out.println(joined.equals("left right")); // true
System.out.println(joined.contains("\n"));       // false
```

Hai dấu `\` có hai tác dụng:
- Dấu sau `left ` **nối** từ `left` và `right` thành cùng một dòng String.
- Dấu sau `right` loại bỏ newline ngay trước delimiter đóng, nên không còn `\n` cuối.

**Dấu cách trước `\` có ý nghĩa.** Ở dòng `left \`, dấu cách sau chữ `left` được giữ lại để hai từ không dính liền. Nếu viết:

```java
String glued = """
        hello\
        world\
        """;
```

thì giá trị là `"helloworld"`. Muốn `"hello world"`, phải chủ động thêm space trước dấu `\` đầu tiên.

### 4.1. Dùng để hard-wrap dòng mã nguồn dài

```java
String message = """
        Yêu cầu của bạn đang được xử lý và \
        sẽ được phản hồi sau khi hoàn tất.\
        """;
```

Giá trị String vẫn là **một dòng**: `"Yêu cầu của bạn đang được xử lý và sẽ được phản hồi sau khi hoàn tất."`. Có thể căn dòng trong source cho dễ đọc mà không vô tình thêm newline vào nội dung thông báo.

### 4.2. Phân biệt `\n`, xuống dòng thật và line continuation

| Trong source text block | Kết quả trong String | Khi nào dùng |
| --- | --- | --- |
| Xuống dòng thường | Có `\n` sau bước chuẩn hóa line terminators | JSON, HTML, log nhiều dòng |
| `\n` (escape) | Thêm một LF thật ở bước dịch escape | Muốn chủ động chèn newline |
| `\` ngay trước xuống dòng thật | **Loại bỏ** newline tại vị trí ấy | Dòng dài trong source nhưng một dòng trong String |
| `\\` (escape) | Cho ra một ký tự backslash `\` | Đường dẫn, regex hoặc nội dung cần dấu backslash |

**Không đặt dấu cách sau `\`** khi muốn line continuation: cú pháp cần dấu `\` liền kề line terminator. Dấu `\` đứng trước một dấu cách thông thường không có nghĩa “nối dòng”.

**Giới hạn khác nhau:** `\s` dùng được trong chuỗi truyền thống `"..."` lẫn text blocks. Nhưng chuỗi truyền thống không cho một line terminator thật nằm giữa hai dấu nháy kép, nên `\` + xuống dòng nguồn **chỉ áp dụng thực tế trong text blocks**.

## 5. Dòng cuối và vị trí delimiter đóng

Đoạn:

```java
String withFinalLine = """
        a
        b
        """;
```

có giá trị `"a\nb\n"` — có newline cuối. Trong khi:

```java
String noFinalLine = """
        a
        b\
        """;
```

có giá trị `"a\nb"` — **không** có newline cuối.

Một cách khác cũng loại bỏ newline cuối là đặt delimiter đóng ngay sau nội dung dòng cuối:

```java
String alsoNoFinalLine = """
        a
        b""";
```

Tuy nhiên, vị trí delimiter đóng cũng có thể thay đổi cách tính **incidental indentation** (thụt lề chung). Dùng `\` cuối dòng giúp để delimiter đóng riêng, dễ nhìn và điều khiển newline rõ ràng. Khi định dạng có yêu cầu chính xác từng ký tự, hãy kiểm thử bằng `equals` hoặc in biểu diễn trực quan như ở chương trình hoàn chỉnh.

## 6. Ba bước xử lý giải thích hai bổ sung

Theo Java Language Specification, compiler xử lý nội dung text block theo thứ tự:

1. **Chuẩn hóa line terminators:** các CRLF/CR trong source trở thành LF (`\n`). Cùng một text block có kết quả nhất quán giữa các hệ điều hành.
2. **Loại incidental whitespace:** xóa lề chung và trailing whitespace; việc xác định lề chịu ảnh hưởng của nội dung và delimiter đóng.
3. **Dịch escape sequences:** xử lý `\s`, `\` + newline, `\n`, `\t`, `\\`, các escape khác.

```text
Text block trong source
        |
        v
Normalize CR / CRLF -> LF
        |
        v
Remove incidental indentation / trailing whitespace
        |
        v
Translate escapes: \s -> SPACE; \<line terminator> -> nothing
        |
        v
java.lang.String
```

**Thứ tự 2 trước 3 là chìa khóa:** dấu `\s` chưa phải space thật ở lúc dọn trailing whitespace, và `\` + newline chỉ được loại khi dịch escape. Không nên tưởng việc gõ ký tự trong source sẽ luôn được giữ nguyên từng dấu cách.

**Góc kỹ thuật về Unicode escape:** trong mã nguồn Java, các dạng `\u0020` được xử lý rất sớm trong quá trình đọc source, trước khi compiler phân tích text block. Bởi vậy `\u0020` không phải giải pháp đáng tin để giữ trailing spaces theo cách `\s` làm được. Các lựa chọn rõ nghĩa hơn là `\s` hoặc `\040` khi cần biểu diễn dấu cách bằng escape.

## 7. Ví dụ Java 17+ độc lập, có kết quả kiểm chứng

Lưu đúng tên file **`TextBlockFinalDemo.java`**:

```java
import java.util.Arrays;

public class TextBlockFinalDemo {
    static String show(String s) {
        return s.replace(" ", "·").replace("\n", "|");
    }

    public static void main(String[] args) {
        String ordinary = """
                alpha
                  beta
                """;

        String joined = """
                left \
                right\
                """;

        String padded = """
                red  \s
                green\s
                blue \s
                """;

        String noFinalLine = """
                a
                b\
                """;
        String withFinalLine = """
                a
                b
                """;

        String inline = "A\sB";

        String json = """
                {
                  "name": "%s",
                  "active": true
                }
                """.formatted("Lan");

        String escapedSequence = "\\n".translateEscapes();
        String rawString = "    one\n      two".stripIndent();

        System.out.println("ordinary=" + show(ordinary));
        System.out.println("joined=" + show(joined));
        System.out.println("padded=" + show(padded));
        System.out.println("paddedLengths=" +
                Arrays.toString(padded.lines().mapToInt(String::length).toArray()));
        System.out.println("noFinalLine=" + show(noFinalLine));
        System.out.println("withFinalLine=" + show(withFinalLine));
        System.out.println("inline=" + show(inline));
        System.out.println("json=" + show(json));
        System.out.println("translateEscapes=" + show(escapedSequence));
        System.out.println("stripIndent=" + show(rawString));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 TextBlockFinalDemo.java
java TextBlockFinalDemo
```

Kết quả chuẩn đã kiểm tra bằng compiler/runtime:

```text
ordinary=alpha|··beta|
joined=left·right
padded=red···|green·|blue··|
paddedLengths=[6, 6, 6]
noFinalLine=a|b
withFinalLine=a|b|
inline=A·B
json={|··"name":·"Lan",|··"active":·true|}
translateEscapes=|
stripIndent=one|··two
```

**Quy ước hiển thị trong method `show`:** `·` là ký hiệu biểu diễn dấu cách, còn `|` là ký hiệu biểu diễn ký tự LF. Các ký hiệu đó **không tự xuất hiện** trong String gốc.

Giải thích:

1. `ordinary`: thụt lề chung bị loại, còn hai dấu cách của dòng `beta` và `\n` cuối.
2. `joined`: line continuation nối hai dòng, giữ một dấu cách giữa các từ, không giữ newline cuối.
3. `padded`: escape `\s` bảo toàn số dấu cách cuối dòng theo chủ ý.
4. `paddedLengths`: ba dòng đều dài đúng 6 ký tự trước `\n`.
5. `noFinalLine` so với `withFinalLine`: chỉ khác ký tự `\n` cuối.
6. `inline`: `\s` hợp lệ trong string literal truyền thống.
7. `json`: dấu nháy kép JSON có thể viết trực tiếp; `formatted("Lan")` thay `%s` bằng giá trị được cung cấp.
8. `translateEscapes`: `"\\n"` có giá trị hai ký tự backslash và `n`; method dịch thành một LF thực.
9. `stripIndent`: chuỗi ban đầu có lề 4 dấu cách, còn 2 dấu cách phụ của dòng sau được giữ.

### Các String API liên quan còn được hỗ trợ

| API | Có từ | Công dụng |
| --- | --- | --- |
| `String.formatted(Object...)` | Java 15 | Định dạng dựa trên `String.format(this, ...)` |
| `String.stripIndent()` | Java 15 | Loại phần thụt lề ngẫu nhiên trong chuỗi nhiều dòng, chuẩn hóa line endings |
| `String.translateEscapes()` | Java 15 | Dịch escape sequences ở giá trị String runtime; không dịch source Unicode escapes |
| `String.lines()` | Java 11 | Lấy stream các dòng để kiểm tra/kết hợp |

**Lưu ý với `stripIndent()`:** phép tính incidental indentation còn phụ thuộc cấu trúc dòng cuối. `"    one\n      two".stripIndent()` cho `"one\n  two"`; một chuỗi khác có LF cuối và dòng rỗng có thể giữ lề khác. Hãy kiểm thử dữ liệu thực tế nếu khoảng trắng là phần của hợp đồng.

## 8. Ứng dụng hiện nay và giới hạn an toàn

### JSON nhiều dòng

```java
String json = """
        {
          "id": 12,
          "status": "READY"
        }
        """;
```

Text block giúp đọc source dễ hơn, nhưng **không** tự escape dữ liệu bên ngoài. Nếu phải thêm giá trị do người dùng nhập, hãy sử dụng JSON serializer/encoder phù hợp thay vì ghép chuỗi tùy ý bằng `formatted`.

### SQL nhiều dòng

```java
String sql = """
        SELECT id, title
        FROM books
        WHERE category = ?
        ORDER BY title
        """;
```

`sql` là một String bình thường. Hãy dùng `PreparedStatement` và bind tham số `?` qua JDBC; **không** đưa input người dùng trực tiếp vào SQL bằng `formatted` rồi kỳ vọng text block chống SQL injection.

### Nội dung cần trailing spaces

```java
String table = """
        ID  \s
        123 \s
        """;
```

Escape `\s` giúp giữ dấu cách ở phần cuối. Nếu bài toán cần định dạng theo chiều rộng phức tạp, `String.format` hoặc `formatted` thường rõ ràng hơn việc canh thủ công bằng whitespace.

### Câu thông báo dài một dòng

```java
String status = """
        Hồ sơ đã được nhận và đang \
        chờ xử lý theo quy trình.\
        """;
```

Dòng source được chia cho dễ đọc; **giá trị String chỉ có một dòng**. Cần để dấu cách trước `\` nhằm tách từ khi nối.

### Không có nội suy biến tự động

```java
String name = "Lan";
String message = """
        Hello $name
        """;
```

Text block **không** thay `$name` bằng biến `name`. Nếu muốn định dạng:

```java
String message = """
        Hello %s
        """.formatted(name);
```

`formatted` hữu ích cho chuỗi thông thường nhưng không thay thế escaping JSON, HTML hoặc prepared statements cho SQL.

## 9. Lỗi thường gặp

### 9.1. Quên xuống dòng sau opening delimiter

```java
// CỐ Ý SAI:
String invalid = """hello""";
```

Sửa thành `String valid = "hello";` nếu là chuỗi một dòng; hoặc chuyển nội dung xuống dòng kế tiếp sau `"""`.

### 9.2. Tưởng text block giữ nguyên toàn bộ lề/trailing spaces

```java
String text = """
        alpha
          beta
        """;
```

Giá trị là `"alpha\n  beta\n"`, không phải giá trị chứa toàn bộ 8 dấu cách căn lề trong source. Dùng `\s` khi cần dấu cách **cuối dòng**, và điều chỉnh vị trí delimiter đóng/`indent` khi cần kiểm soát **đầu dòng**.

### 9.3. Tưởng `\s` có nghĩa regex whitespace

```java
// Regex chỉ khớp space, KHÔNG phải mọi whitespace:
java.util.regex.Pattern p1 = java.util.regex.Pattern.compile("\s+");

// Regex nhận escape \s của regex engine:
java.util.regex.Pattern p2 = java.util.regex.Pattern.compile("\\s+");
```

Đây là lỗi logic, không nhất thiết là lỗi biên dịch. `\s` trong Java source được dịch trước khi regex engine nhận chuỗi.

### 9.4. Dùng `\n` khi mục đích là không có newline

```java
String a = """
        hello\n
        world
        """;
```

`\n` **thêm** một LF, không xóa ký tự xuống dòng. Dùng `\` + xuống dòng thật để nối source:

```java
String b = """
        hello \
        world\
        """;
```

`b.equals("hello world")` là `true`.

### 9.5. Quên dấu cách khi nối

```java
String s = """
        hello\
        world\
        """;
```

Giá trị là `"helloworld"`, không phải `"hello world"`. Sửa thành `hello \` ở dòng thứ nhất để bảo toàn dấu cách tách từ.

### 9.6. Có dấu cách ngay sau backslash cuối dòng

Escape line continuation cần `\` **ngay trước** line terminator; chèn whitespace sau `\` sẽ phá ý định nối dòng và có thể gây lỗi escape. Khi cần độ chính xác, bật hiển thị whitespace trong editor, và viết unit test trên `equals`/`length`.

### 9.7. Quên newline cuối trong dữ liệu

```java
String a = """
        ready
        """;
String b = """
        ready\
        """;
```

`a.equals("ready\n")` và `b.equals("ready")` đều đúng. Snapshot test hoặc dữ liệu mạng có thể sai chỉ vì newline cuối này.

### 9.8. Nghĩ text block là raw string hoặc một JSON template an toàn

Text block vẫn hiểu escape của Java, chẳng hạn `\n`, `\t`, `\s`, `\\`. Muốn giữ dấu backslash thật trong chuỗi, cần viết `\\` trong source Java hoặc dùng công cụ chuyên dụng để sinh nội dung. Text block không tự escape tên, dấu nháy kép trong dữ liệu đầu vào, không tự validate JSON, và không tự chặn SQL injection.

## 10. Bài tập và đáp án

**Câu 1:** Java 14 đã bổ sung điều gì cho text blocks và chúng còn hợp lệ trong Java 17+ không?

**Đáp án:** Hai escape `\s` và `\` + line terminator; cả hai được giữ khi text blocks chính thức từ Java 15.

**Câu 2:** `"A\sB"` có bao nhiêu dấu cách giữa A và B?

**Đáp án:** Một SPACE U+0020. `\s` dùng được trong string literal truyền thống lẫn text block.

**Câu 3:** Giá trị của đoạn sau có LF cuối không?

```java
String s = """
        x
        y\
        """;
```

**Đáp án:** Không. `s.equals("x\ny")` là `true`.

**Câu 4:** Vì sao `red  \s` giữ ba dấu cách sau `red`?

**Đáp án:** Hai dấu cách đứng trước `\s` được giữ ở giai đoạn loại trailing whitespace, rồi `\s` chuyển thành dấu cách thứ ba ở giai đoạn dịch escape.

**Câu 5:** Muốn regex tìm tab và newline, chọn `Pattern.compile("\s+")` hay `Pattern.compile("\\s+")`?

**Đáp án:** `Pattern.compile("\\s+")` vì regex engine cần nhận `\s`, còn Java source `"\s"` sẽ thành một dấu cách.

**Câu 6:** Vì sao `String message = """...""";` không tự thay `$name` thành giá trị Java variable?

**Đáp án:** Text block là chuỗi String literal, không có tính năng interpolation. `String.formatted` có thể định dạng theo placeholder, nhưng không tự đảm bảo escaping cho dữ liệu có cấu trúc.

**Câu 7:** Có nên dùng text block để ghép input người dùng thẳng vào câu SQL?

**Đáp án:** Không. Text block chỉ giúp đọc SQL trong source; dùng `PreparedStatement` và binding tham số.

## 11. Checklist dự án

- [ ] Chỉ dùng text blocks ở nơi nó thực sự cải thiện độ đọc cho văn bản nhiều dòng.
- [ ] Xác định Java đích là **15+**; Java 17+ không cần preview flags.
- [ ] Muốn giữ dấu cách cuối dòng: dùng `\s`.
- [ ] Muốn nối dòng mã nguồn thành một dòng dữ liệu: đặt `\` ngay trước newline thật.
- [ ] Có dấu cách trước `\` nếu cần hai từ không dính nhau.
- [ ] Kiểm tra việc có/không có newline cuối khi delimiter đóng ở dòng riêng.
- [ ] Nhớ thứ tự: normalize CR/CRLF → strip incidental whitespace → translate escapes.
- [ ] Không nhầm Java `\s` với regex `\\s` hoặc Java `\n` với line continuation.
- [ ] Dùng `formatted` khi phù hợp, nhưng không xem nó là JSON encoding hay SQL parameterization.
- [ ] Khi yêu cầu chính xác từng space/newline, dùng unit test so sánh chuỗi và/hoặc hiển thị ký tự ẩn.

## Tài liệu chính thức còn áp dụng

1. [Oracle — Java Language Changes (mục Java 14/JEP 368)](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html): text blocks second preview và hai escape bổ sung.
2. [Oracle — Significant Changes in JDK 15](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-15.html): text blocks đã chính thức từ Java 15, không cần preview.
3. [Oracle Java 17 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): cách dùng `\s`, nối dòng, thụt lề, newline cuối và những `String` API liên quan.
4. [Java Language Specification, Java SE 25 — `3.10.6/`3.10.7](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): quy tắc 3 bước của text blocks và escape sequences.
5. [Oracle — Java SE 17 `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `formatted`, `stripIndent`, `translateEscapes`.
