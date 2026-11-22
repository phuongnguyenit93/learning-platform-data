# Text blocks: Dòng mới bắt buộc sau dấu mở `"""` trong Java

> **Ngữ cảnh:** Java 14 → **Text blocks** → **Dòng mới bắt buộc sau dấu mở**. Text blocks được thử nghiệm tại Java 13 (JEP 355), thử nghiệm lần hai ở Java 14 (JEP 368), và **chính thức từ Java 15** (JEP 378). Bài này chỉ sử dụng cú pháp chính thức vẫn áp dụng trong Java hiện đại. Ví dụ dùng JDK còn được cập nhật (chẳng hạn JDK 21/25), biên dịch với `--release 17`; không cài JDK 14 cũ và không bật `--enable-preview`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu chính xác quy tắc: **sau ba dấu nháy kép mở `"""` phải có ký tự kết thúc dòng**, có thể có một số ký tự khoảng trắng được cho phép ở giữa.
2. Giải thích vì sao `String s = """Hello""";` là **lỗi biên dịch**, dù chuỗi muốn lưu chỉ có một dòng.
3. Viết đúng text block nhiều dòng và text block lưu một chuỗi không có dấu xuống dòng.
4. Phân biệt **ký tự xuống dòng bắt buộc trong mã nguồn sau dấu mở** với **ký tự xuống dòng thực sự trong giá trị `String`**.
5. Hiểu vị trí dấu đóng `"""` ảnh hưởng thế nào đến **dấu xuống dòng ở cuối chuỗi**.
6. Biết cách xử lý dòng trống cố ý, thụt lề (*incidental indentation*), chuẩn hóa kết thúc dòng và escape `\` ở cuối dòng.
7. Dùng chương trình Java độc lập để kiểm chứng giá trị thực tế, thay vì đoán từ cách IDE hiển thị.

## 2. Quy tắc cú pháp chính thức

Một text block là một cách viết **giá trị `String`** bằng cặp dấu phân cách ba nháy kép:

~~~java
String message = """
    Hello
    Java
    """;
~~~

Phần mở không chỉ là `"""` đứng riêng lẻ theo nghĩa đầy đủ. Theo Java Language Specification, **opening delimiter** gồm:

1. **Ba ký tự nháy kép liên tiếp:** `"""`.
2. **Không hoặc một số ký tự khoảng trắng cho phép:** space (dấu cách ASCII), tab, form feed.
3. **Bắt buộc một line terminator:** LF (`\n`), CR (`\r`), hoặc cặp CRLF (`\r\n`) trong văn bản mã nguồn.

Biểu diễn ngữ pháp rút gọn, chỉ để đọc:

~~~text
""" [space/tab/form-feed]* <line-terminator>
    <text block content>
"""
~~~

Trong sơ đồ, dấu ngoặc vuông và dấu `*` diễn tả tùy chọn/lặp theo ngữ pháp, **không phải Java code**. Phần nội dung bắt đầu **sau line terminator của dấu mở**, không được viết ngay sau `"""` trên cùng dòng.

Cần phân biệt rõ hai câu:

- **Đúng:** ngay sau `"""` có thể có *một ít khoảng trắng hợp lệ* rồi mới tới dấu kết thúc dòng.
- **Sai:** bắt buộc ngay lập tức là ký tự `\n` và không được có bất kỳ khoảng trắng nào; đặc tả không quy định như vậy.

Về cách trình bày, **nên đặt dấu xuống dòng ngay sau `"""`**, không thêm khoảng trắng cuối dòng vì chúng không mang lợi ích đọc mã và dễ bị formatter xóa.

### Mã đúng

~~~java
String name = """
    Java
    """;
~~~

### Mã sai

~~~java
String name = """Java"""; // LỖI: nội dung bắt đầu ngay sau dấu mở
~~~

Đây là **mảnh minh họa cố ý không biên dịch**. Trình biên dịch báo lỗi do thiếu line terminator trong opening delimiter. Một text block Java **không thể có dấu mở, nội dung và dấu đóng tất cả trên cùng một dòng nguồn**.

## 3. Sau dấu mở phải xuống dòng để làm gì?

Quy tắc mở ở một dòng và nội dung bắt đầu sau đó giúp Java xử lý **thụt lề** của chuỗi nhiều dòng một cách nhất quán. Nó cũng phân biệt rõ text block với chuỗi truyền thống `"..."`.

Xét:

~~~java
String greeting = """
    Xin chào
    Java
    """;
~~~

Dấu xuống dòng nằm **ngay sau dấu mở** thuộc về cú pháp của opening delimiter. Dấu đó **không tự tạo ra một ký tự `\n` ở đầu giá trị `greeting`**.

Sau bước chuẩn hóa dòng và xử lý thụt lề, giá trị của `greeting` trong ví dụ tương đương:

~~~java
String greeting = "Xin chào\nJava\n";
~~~

Bởi vậy:

- Giá trị bắt đầu bằng `X`, **không** bắt đầu bằng `\n`.
- Có một `\n` giữa `Xin chào` và `Java`.
- Có một `\n` ở cuối vì **dòng chứa `Java` kết thúc bằng dấu xuống dòng trước dấu đóng đặt trên dòng riêng**.
- Những khoảng trắng đầu dòng dùng để thụt lề mã Java ở đây được xem là *incidental indentation* nên đã được loại bỏ khỏi giá trị.

**Điểm dễ nhầm:** “Bắt buộc xuống dòng sau dấu mở” là **quy tắc tạo token trong mã nguồn**; “giá trị `String` có xuống dòng ở đầu/cuối không?” là **vấn đề nội dung và vị trí dấu đóng**. Hai câu hỏi không thể coi là một.

## 4. Ví dụ độc lập: quan sát dòng mới bắt buộc nhưng không có `\n` ở đầu giá trị

Tạo tệp **`TextBlockOpeningDemo.java`**:

~~~java
public class TextBlockOpeningDemo {
    public static void main(String[] args) {
        String greeting = """
                Xin chào
                Java
                """;

        System.out.println(
                greeting.equals("Xin chào\nJava\n"));
        System.out.println(greeting.startsWith("\n"));
        System.out.println(greeting.replace("\n", "|"));
    }
}
~~~

Biên dịch và chạy bằng JDK hiện hành có hỗ trợ target 17:

~~~bash
javac --release 17 TextBlockOpeningDemo.java
java TextBlockOpeningDemo
~~~

**Stdout chính xác:**

~~~text
true
false
Xin chào|Java|
~~~

Giải thích:

1. `equals("Xin chào\nJava\n")` là `true` vì hai cách viết tạo cùng các ký tự.
2. `startsWith("\n")` là `false`: dấu xuống dòng sau dấu mở **không trở thành dấu xuống dòng đầu chuỗi**.
3. `replace("\n", "|")` biến những dấu xuống dòng **thật sự có trong giá trị** thành ký hiệu dễ quan sát `|`.

Ví dụ không phụ thuộc cách terminal trình bày dòng trống; các kiểm tra `equals` và `startsWith` làm rõ đúng nội dung `String`.

## 5. Không phải text block nào cũng lưu chuỗi nhiều dòng

Một text block **phải có dấu kết thúc dòng sau dấu mở trong mã nguồn**, nhưng **giá trị của nó** không nhất thiết phải chứa ký tự `\n`. Dấu đóng có thể đặt ngay sau ký tự cuối của nội dung, trên **dòng nội dung cuối**:

~~~java
String oneLine = """
    Java""";
~~~

Giá trị tương đương:

~~~java
String oneLine = "Java";
~~~

Đặt `"""` đóng ngay sau `Java` có nghĩa là **không có dấu xuống dòng ở cuối**. Mặc dù chuỗi chỉ có một dòng, dấu mở vẫn phải có line terminator trước khi nội dung bắt đầu.

Nếu mục đích là lưu một từ đơn giản như `"Java"`, hãy ưu tiên **string literal thông thường** để mã gọn hơn:

~~~java
String language = "Java";
~~~

Text block phát huy tác dụng lớn hơn khi lưu SQL nhiều dòng, HTML, JSON mẫu, đoạn mã hoặc nội dung có nhiều dấu nháy kép. **Không dùng text block chỉ để thay mọi `"..."` bất kể nhu cầu.**

## 6. Vị trí dấu đóng quyết định dấu `\n` cuối chuỗi

Cả hai dạng dưới đây đều có **line terminator bắt buộc sau dấu mở**. Điểm khác nhau nằm ở vị trí `"""` **đóng**.

### Dấu đóng trên dòng riêng: có `\n` cuối

~~~java
String withFinalNewline = """
    A
    B
    """;
~~~

Giá trị: `"A\nB\n"`.

### Dấu đóng ngay sau dòng cuối: không có `\n` cuối

~~~java
String withoutFinalNewline = """
    A
    B""";
~~~

Giá trị: `"A\nB"`.

Hai dạng đều hợp lệ. Việc chọn dạng nào tùy dữ liệu cần tạo. Ví dụ một file văn bản chuẩn thường có newline cuối, còn một giá trị dùng so sánh hoặc một đoạn JSON đơn dòng được ghép với nội dung khác có thể không cần dấu này.

### Ví dụ độc lập: so sánh giá trị thực

Tạo tệp **`TextBlockClosingDemo.java`**:

~~~java
public class TextBlockClosingDemo {
    public static void main(String[] args) {
        String withEnd = """
                A
                B
                """;

        String withoutEnd = """
                A
                B""";

        String singleLine = """
                Java""";

        System.out.println(withEnd.equals("A\nB\n"));
        System.out.println(withoutEnd.equals("A\nB"));
        System.out.println(singleLine.equals("Java"));
        System.out.println(withEnd.replace("\n", "|"));
        System.out.println(withoutEnd.replace("\n", "|"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TextBlockClosingDemo.java
java TextBlockClosingDemo
~~~

**Stdout chính xác:**

~~~text
true
true
true
A|B|
A|B
~~~

Một lỗi hay gặp là viết dấu đóng ở dòng riêng rồi ngạc nhiên khi chuỗi có `\n` cuối. Muốn kiểm tra, dùng `equals`, `endsWith("\n")`, hoặc hiển thị theo cách thay `\n` thành ký hiệu như ví dụ.

## 7. Muốn thật sự có dòng trống ở đầu chuỗi thì làm sao?

Để chuỗi bắt đầu bằng newline, hãy thêm **một dòng trống sau dòng mở**. Dòng mới bắt buộc của opening delimiter **không đủ** để tạo newline đầu chuỗi.

Ví dụ:

~~~java
String withLeadingBlank = """

    Dữ liệu
    """;
~~~

Trong nội dung mã này:

- Dòng 1: `String ... = """`, kết thúc bằng newline bắt buộc.
- Dòng 2: dòng trống **thuộc nội dung**.
- Dòng 3: `Dữ liệu`.
- Dòng 4: dấu đóng.

Giá trị tương đương `"\nDữ liệu\n"`. Như vậy **dòng trống thực** tạo ra `\n` đầu chuỗi, còn line terminator ngay sau dấu mở chỉ có tác dụng kết thúc opening delimiter.

### Ví dụ độc lập: dòng trống là nội dung

Tạo tệp **`LeadingBlankLineDemo.java`**:

~~~java
public class LeadingBlankLineDemo {
    public static void main(String[] args) {
        String noLeadingBlank = """
                Alpha
                """;

        String withLeadingBlank = """

                Alpha
                """;

        System.out.println(noLeadingBlank.startsWith("\n"));
        System.out.println(withLeadingBlank.startsWith("\n"));
        System.out.println(withLeadingBlank.equals("\nAlpha\n"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 LeadingBlankLineDemo.java
java LeadingBlankLineDemo
~~~

**Stdout chính xác:**

~~~text
false
true
true
~~~

Trong code review, phân biệt **dòng trống chủ ý trong nội dung** và **dòng trống do formatter/chỉnh sửa vô tình thêm vào**. Với chuỗi có yêu cầu định dạng chính xác, test nội dung thực để ngăn thay đổi ngoài ý muốn.

## 8. Thụt lề và xuống dòng: hai quy tắc liên quan nhưng khác nhau

Text block thường được đặt trong class/method và phải thụt lề để Java code dễ đọc. Trình biên dịch xử lý khoảng trắng dư dùng cho thụt lề theo **incidental indentation**, giúp giá trị chuỗi không mang tất cả khoảng trắng dùng để căn chỉnh mã nguồn.

Ví dụ:

~~~java
String html = """
        <main>
          <h1>Java</h1>
        </main>
        """;
~~~

Giá trị được tạo:

~~~text
<main>
  <h1>Java</h1>
</main>
~~~

và có một `\n` cuối cùng (khó nhìn thấy trong block output, nhưng có thể kiểm tra bằng `endsWith("\n")`). Phần khoảng trắng chung trước các dòng không được giữ nguyên thành nội dung; phần thụt vào thêm trước `<h1>` được giữ, vì nó mang ý nghĩa trong nội dung.

Các quy tắc cần phân biệt:

| Khía cạnh | Hành vi |
| --- | --- |
| Line terminator sau dấu mở `"""` | **Bắt buộc để cú pháp hợp lệ**, không tự thành `\n` đầu chuỗi. |
| Ký tự xuống dòng giữa các dòng nội dung | Trở thành `\n` trong giá trị sau chuẩn hóa. |
| Khoảng trắng đầu dòng phục vụ thụt lề mã | Có thể bị loại theo thuật toán incidental indentation. |
| Khoảng trắng cuối mỗi dòng nội dung | Thông thường bị coi là incidental và loại bỏ; có thể giữ theo chính sách bằng escape `\s`. |
| Vị trí dấu đóng `"""` | Quyết định có ký tự xuống dòng cuối và có thể ảnh hưởng mức incidental indentation. |

**Mức thụt lề không bị quyết định bởi dấu mở nằm ở cột nào.** Các dòng nội dung và vị trí dấu đóng tác động đến cách Java loại khoảng trắng không thiết yếu. Nếu muốn giữ chính xác khoảng trắng, hãy dùng test giá trị `String`; đừng chỉ nhìn căn lề trong IDE.

### Ví dụ độc lập: nguồn JSON đọc được

Tạo tệp **`TextBlockIndentationDemo.java`**:

~~~java
public class TextBlockIndentationDemo {
    public static void main(String[] args) {
        String json = """
                {
                  "topic": "Java",
                  "lessons": 3
                }
                """;

        String expected = "{\n"
                + "  \"topic\": \"Java\",\n"
                + "  \"lessons\": 3\n"
                + "}\n";

        System.out.println(json.equals(expected));
        System.out.println(json.endsWith("\n"));
        System.out.println(json.lines().count());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TextBlockIndentationDemo.java
java TextBlockIndentationDemo
~~~

**Stdout chính xác:**

~~~text
true
true
4
~~~

`String.lines()` đếm bốn dòng văn bản trong ví dụ; newline cuối không tạo một dòng thứ năm rỗng theo hợp đồng của phương thức này. Text block là **`String` thông thường**, không tự phân tích/công nhận JSON hợp lệ. Khi phải đưa dữ liệu không tin cậy vào JSON thật, nên dùng thư viện JSON thích hợp để mã hóa và validation, không nối raw input vào một mẫu văn bản.

## 9. Line terminator của mã nguồn và giá trị chuỗi

Trong mã nguồn Java, một dòng có thể kết thúc bằng:

- LF (phổ biến trên Linux/macOS và trong repository);
- CRLF (thường gặp trong một số file trên Windows);
- CR (ít gặp hơn nhưng vẫn được đặc tả).

**Mọi trường hợp đều có thể đáp ứng line terminator bắt buộc sau dấu mở.** Khi tạo giá trị text block, Java chuẩn hóa line terminator trong nội dung thành **LF `\n`**, kể cả mã nguồn có dòng CRLF.

Ví dụ, nếu file mã nguồn dùng CRLF, text block:

~~~java
String s = """
    A
    B
    """;
~~~

vẫn có giá trị `"A\nB\n"`. Nó **không tự tạo `"A\r\nB\r\n"`** chỉ vì file nguồn trên Windows.

Đây là lý do kết quả đọc/ghi text block nên được so sánh với `\n` khi chưa có yêu cầu khác. Khi cần tạo file có line ending cụ thể của một giao thức hoặc môi trường, hãy chủ động xử lý tại bước ghi/xuất file; đừng phụ thuộc vào line ending của mã nguồn Java.

### Ví dụ độc lập: kiểm tra LF trong giá trị

Tạo tệp **`TextBlockLineEndingDemo.java`**:

~~~java
public class TextBlockLineEndingDemo {
    public static void main(String[] args) {
        String text = """
                A
                B
                """;

        System.out.println(text.equals("A\nB\n"));
        System.out.println(text.indexOf('\r') == -1);
        System.out.println(text.indexOf('\n') >= 0);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 TextBlockLineEndingDemo.java
java TextBlockLineEndingDemo
~~~

**Stdout chính xác:**

~~~text
true
true
true
~~~

Nếu lấy mã nguồn này và đổi toàn bộ line ending giữa LF/CRLF, ý nghĩa `String` được tạo vẫn không đổi theo quy tắc text block.

## 10. Escape `\` ở cuối dòng: nối nội dung mà không tạo `\n`

Java text block hỗ trợ escape đặc biệt **backslash + line terminator**. Đặt `\` ngay cuối một dòng nội dung sẽ **ngăn dòng đó đưa ký tự xuống dòng vào giá trị**. Đây là cách kiểm soát nội dung, **không loại bỏ quy tắc xuống dòng bắt buộc sau dấu mở**.

Ví dụ:

~~~java
String joined = """
    Hello\
    World\
    """;
~~~

Giá trị tương đương `"HelloWorld"`: cả dấu xuống dòng sau `Hello` và sau `World` đều bị loại ở thời điểm xử lý escape.

Lưu ý:

- Dấu `\` phải trực tiếp đứng trước line terminator để là escape nối dòng này; thêm một dấu cách sau `\` sẽ làm thay đổi cú pháp/ý nghĩa.
- Không đặt `\` sau **dấu mở `"""`** để “bỏ” yêu cầu xuống dòng; opening delimiter **vẫn phải có** line terminator hợp lệ.
- Chỉ dùng nối dòng khi dữ liệu thực sự cần một dòng. Với câu SQL, JSON hoặc nội dung phân biệt khoảng trắng, nối dòng có thể vô tình dính các từ/ký hiệu vào nhau.

### Escape `\s` để giữ dấu cách cuối dòng

Text blocks có quy tắc loại khoảng trắng thừa cuối dòng. Nếu cần giữ một dấu cách cuối dòng theo đúng hợp đồng dữ liệu, có thể dùng `\s` (tương đương một dấu cách ASCII). Khác với newline sau dấu mở, `\s` là **escape trong nội dung**.

### Ví dụ độc lập: hai kiểu escape còn dùng hiện nay

Tạo tệp **`TextBlockEscapeDemo.java`**:

~~~java
public class TextBlockEscapeDemo {
    public static void main(String[] args) {
        String joined = """
                Hello\
                World\
                """;

        String trailingSpace = """
                X\s
                """;

        System.out.println(joined.equals("HelloWorld"));
        System.out.println(trailingSpace.equals("X \n"));
        System.out.println(trailingSpace.endsWith(" \n"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TextBlockEscapeDemo.java
java TextBlockEscapeDemo
~~~

**Stdout chính xác:**

~~~text
true
true
true
~~~

Trong chuỗi `trailingSpace`, `\s` được xử lý sau bước bỏ incidental whitespace nên giữ một dấu cách trước `\n`. Không dựa vào việc editor bảo tồn những dấu cách vô hình cuối dòng mã nguồn.

## 11. Text block khác chuỗi thường ở đâu?

| Thuộc tính | Chuỗi thường `"..."` | Text block `"""` |
| --- | --- | --- |
| Mở nội dung ngay sau dấu nháy mở | Có | **Không**: phải có line terminator sau dấu mở. |
| Nhiều dòng mã nguồn chưa escape | Không dùng line terminator trực tiếp trong literal thường | Cho phép các dòng nội dung thực. |
| Kiểu runtime | `String` | **`String`**, không phải loại dữ liệu mới. |
| Dấu nháy kép `"` trong nội dung | Thường escape `\"` | Dấu nháy kép đơn lẻ thường viết trực tiếp; chuỗi ba dấu liên tiếp cần escape để tránh kết thúc text block. |
| Dấu xuống dòng trong giá trị | Thường viết `\n` | Có thể đến từ các dòng nội dung, sau chuẩn hóa thành `\n`. |
| Thụt lề | Mỗi khoảng trắng viết trong literal là nội dung | Java có cơ chế loại incidental indentation. |
| Dấu xuống dòng cuối | Theo `\n` người viết thêm | Phụ thuộc vị trí dấu đóng hoặc escape nối dòng. |
| Trường hợp phù hợp | Chuỗi ngắn/một dòng, ít dấu nháy | HTML/JSON/SQL tĩnh/đoạn văn bản nhiều dòng. |

**Quan trọng:** text block không tự bảo vệ SQL injection, HTML injection hay JSON escaping. Dù biểu diễn nguồn rõ ràng hơn, dữ liệu do người dùng cung cấp vẫn cần được xử lý bằng prepared statement, encoder hoặc serializer thích hợp. Ở bài này, ví dụ chỉ dùng dữ liệu tĩnh nhằm làm rõ **cú pháp và nội dung chuỗi**.

## 12. Lỗi biên dịch và lỗi nội dung thường gặp

| Viết hoặc hành vi | Kết quả | Cách sửa |
| --- | --- | --- |
| `String s = """hello""";` | **Lỗi biên dịch**: thiếu line terminator sau dấu mở. | Đặt newline ngay sau `"""` rồi mới viết `hello`, hoặc dùng `"hello"`. |
| `String s = """hello` rồi xuống dòng | **Lỗi**: ký tự `h` xuất hiện trước line terminator của dấu mở. | Dời `hello` xuống dòng sau. |
| Đặt dấu đóng trên dòng riêng nhưng mong không có `\n` cuối | Giá trị có thêm newline cuối | Đặt dấu đóng cùng dòng với ký tự nội dung cuối, hoặc dùng escape nối dòng khi phù hợp. |
| Thấy newline sau `"""` rồi đoán chuỗi bắt đầu bằng `\n` | **Sai về nội dung** | Nhớ dòng đó thuộc opening delimiter; thêm **dòng trống nội dung** nếu cần `\n` đầu. |
| Tưởng text block phải có nhiều ký tự `\n` trong giá trị | **Sai** | Có thể lưu `"Java"` với text block mở rồi xuống dòng và đóng ngay sau `Java`. |
| Đổi CRLF/LF của file và kỳ vọng `String` đổi theo | **Sai** | Text block chuẩn hóa line terminators trong nội dung thành LF. |
| Căn lề trong IDE rồi đoán đúng khoảng trắng trong giá trị | Có thể sai do incidental indentation | Kiểm tra bằng `equals`, `length`, `replace`, test. |
| Trộn tab và space khi căn lề text block | Khó thấy khác biệt; giá trị dễ sai | Chọn một kiểu indent nhất quán, kiểm thử nội dung. |
| Muốn giữ dấu cách cuối dòng nhưng chỉ gõ space | Có thể bị loại là incidental trailing space | Dùng `\s` khi thật sự cần. |
| Dùng `\` nối dòng khi nội dung cần newline | Các đoạn có thể bị dính nhau | Chỉ nối khi hợp đồng yêu cầu; đối chiếu giá trị sau khi biên dịch. |
| Giữ dấu `"""` bên trong nội dung mà không escape phù hợp | Có thể đóng text block sớm | Escape một dấu nháy trong chuỗi ba nháy liên tục theo hướng dẫn text blocks. |
| Bật `--enable-preview` để dùng text blocks trên JDK mới | Không cần và có thể gây sai quy trình build | Text blocks chính thức từ Java 15; chọn mức đích hiện hành, ví dụ `--release 17`. |

### Hai ví dụ sai để nhận diện ngay

**Sai 1 — toàn bộ literal trên một dòng:**

~~~java
String x = """abc""";
~~~

**Sai 2 — nội dung bắt đầu trên dòng dấu mở:**

~~~java
String x = """abc
    def
    """;
~~~

Hai khối mã này **cố ý không biên dịch**, không được trộn vào file chạy. Cùng một lỗi gốc: **không có line terminator ngay sau dấu mở (sau phần khoảng trắng tùy chọn)**.

**Đúng, dù chuỗi chỉ là một từ:**

~~~java
String x = """
    abc""";
~~~

Giá trị là `"abc"`; mở ở dòng trước, đóng cùng dòng nội dung.

## 13. Quy trình kiểm tra khi IDE báo lỗi ở dấu mở `"""`

1. **Xem đúng phiên bản đích:** text blocks chính thức từ Java 15; target Java 17/21/25 đều sử dụng được. Dùng `javac --version` và `javac --help` để xem compiler, kiểm tra cấu hình `--release`/language level trong IDE.
2. **Kiểm tra ba dấu nháy mở:** có đúng ba ký tự `"` liên tiếp, không phải dấu nháy kiểu typography hay thiếu dấu?
3. **Kiểm tra phần ngay sau dấu mở:** chỉ cho phép space/tab/form feed rồi **line terminator**. Có text, comment hoặc ký tự không hợp lệ trên cùng dòng sau `"""` sẽ khiến dấu mở sai.
4. **Kiểm tra nội dung ở dòng kế:** nội dung thực phải bắt đầu sau line terminator; đừng viết ký tự đầu tiên liền sau dấu mở.
5. **Kiểm tra dấu đóng:** cần đúng `"""` và cân nhắc đặt trên dòng riêng hoặc cuối dòng nội dung theo mục đích có/không có newline cuối.
6. **Đối chiếu giá trị:** so `equals` với chuỗi literal có `\n`, hoặc in chuỗi sau `replace("\n", "|")` để quan sát vị trí newline.
7. **Xem indent và escape:** nếu cú pháp đã đúng mà kết quả sai, kiểm tra incidental spaces, tab/space, `\s` và escape nối dòng `\`.
8. **Tránh cách chữa lỗi không liên quan:** không cài Java 14, không bật preview, không chỉnh ngẫu nhiên mã nguồn cho đến khi hiểu lỗi dấu mở.

Một test nội dung tốt nên kiểm tra **dữ liệu mà ứng dụng cần**, không chỉ rằng mã đã biên dịch thành công.

## 14. Bài tập tự luyện

### Bài 1 — Sửa dòng mở không hợp lệ

Đầu vào lỗi:

~~~java
String title = """Learning Java""";
~~~

Hãy viết lại thành một text block hợp lệ, có giá trị chính xác `"Learning Java"` **không kèm `\n`**. Gợi ý: dấu mở trên dòng trước, sau đó `Learning Java"""`.

**Đáp án tham khảo:**

~~~java
String title = """
    Learning Java""";
~~~

### Bài 2 — Có bao nhiêu `\n`?

Cho:

~~~java
String s = """
    red
    green
    blue
    """;
~~~

Giá trị tương đương `"red\ngreen\nblue\n"`, chứa **3** ký tự `\n`. Vì sao không phải 4? **Vì line terminator ngay sau dấu mở không nằm trong nội dung**.

### Bài 3 — Bỏ newline cuối

Sửa khối ở bài 2 để tạo chính xác `"red\ngreen\nblue"`. Đặt dấu đóng cùng dòng `blue"""`, hoặc dùng cách nối dòng phù hợp. Kiểm tra `endsWith("\n")` trả `false`.

### Bài 4 — Dòng trống đầu có chủ đích

Viết text block có giá trị đúng `"\nHeader\n"`. Hãy thêm một **dòng trống thật** giữa dòng dấu mở và dòng `Header`. Kiểm tra `startsWith("\n")` là `true`.

### Bài 5 — Chuỗi trên Windows

Một file `.java` được lưu với line ending CRLF. Tạo text block gồm hai dòng `A`, `B` với dấu đóng ở dòng riêng. Dự đoán giá trị: **`"A\nB\n"`**, không phải `"A\r\nB\r\n"`. Giải thích bước chuẩn hóa line terminators.

### Bài 6 — Dấu cách cuối dòng

Tạo text block mà giá trị kết thúc bằng `"X \n"` (có **một dấu cách** sau `X` trước newline). Dùng `X\s` trong nội dung rồi kiểm chứng `equals("X \n")`.

### Bài 7 — Biên dịch và đối chiếu output

Chạy từng chương trình độc lập:

~~~bash
javac --release 17 TextBlockOpeningDemo.java
java TextBlockOpeningDemo

javac --release 17 TextBlockClosingDemo.java
java TextBlockClosingDemo

javac --release 17 LeadingBlankLineDemo.java
java LeadingBlankLineDemo

javac --release 17 TextBlockIndentationDemo.java
java TextBlockIndentationDemo

javac --release 17 TextBlockLineEndingDemo.java
java TextBlockLineEndingDemo

javac --release 17 TextBlockEscapeDemo.java
java TextBlockEscapeDemo
~~~

Các tên tệp phải trùng với tên `public class` tương ứng. Chỉ đưa **ví dụ hợp lệ** vào file biên dịch; các ví dụ được đánh dấu “Sai” dùng để nhận biết lỗi.

**Tiêu chí hoàn thành:** bạn có thể nhìn một text block và trả lời chính xác (a) opening delimiter đã có line terminator chưa; (b) giá trị có newline ở đầu không; (c) có newline ở cuối không; (d) indent/escape có làm đổi nội dung không; (e) vì sao văn bản source dùng CRLF vẫn tạo `\n`.

## 15. Tài liệu chính thức còn áp dụng

1. [Java Language Specification 26 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.10.6): ngữ pháp chính thức của opening delimiter, line terminator, nội dung và xử lý khoảng trắng.
2. [Oracle — Text Blocks (Java SE 26)](https://docs.oracle.com/en/java/javase/26/language/text-blocks.html): ví dụ lỗi khi không có dòng mới sau dấu mở, hướng dẫn dấu đóng, indent, trailing newline.
3. [Oracle — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): giải thích thực tế về newline đầu/cuối, indentation, line terminator normalization và escape `\`/`\s`.
4. [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text blocks được chính thức hóa ở Java 15.
5. [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): đối chiếu Java 13 preview, Java 14 second preview và Java 15 final.

**Ghi nhớ:** Cú pháp text block **luôn yêu cầu line terminator sau ba dấu nháy kép mở**; các ký tự nội dung bắt đầu sau terminator đó. **Dấu xuống dòng bắt buộc này không phải ký tự `\n` đầu chuỗi.** Newline trong giá trị được quyết định bởi các dòng nội dung, dòng trống chủ ý, vị trí dấu đóng và escape. Đây là quy tắc Java chính thức từ Java 15 và vẫn hữu ích trên JDK hiện đại.