# Phối hợp `formatted()`, `stripIndent()`, `indent()` và `transform()` trong Java

## 1. Mục tiêu và bức tranh tổng thể

Khi tạo báo cáo, mẫu email, log nhiều dòng hoặc văn bản sinh từ dữ liệu, ta thường cần bốn công việc khác nhau: **chuẩn hóa thụt lề**, **điền dữ liệu**, **thay đổi mức thụt lề để trình bày**, rồi **biến đổi kết quả theo nhu cầu ứng dụng**. Java cung cấp bốn phương thức của `java.lang.String` để ghép thành một luồng xử lý dễ đọc:

- `stripIndent()`: loại thụt lề phụ trợ và khoảng trắng cuối từng dòng; chuẩn hóa dấu xuống dòng.
- `formatted(Object... args)`: lấy chính chuỗi hiện tại làm khuôn định dạng, thay các placeholder dạng `%s`, `%d`, `%.2f`...
- `indent(int n)`: thêm hoặc bỏ thụt lề ở đầu *mỗi* dòng.
- `transform(Function<? super String, ? extends R> f)`: đưa chuỗi qua một hàm xử lý, có thể nhận kết quả thuộc kiểu bất kỳ.

Cả bốn đều là **API hiện hành**: `indent` và `transform` có từ Java 12; `formatted` và `stripIndent` có từ Java 15. Các ví dụ dùng Java 17 trở lên, tương thích với Java hiện đại. Mỗi phương thức tạo kết quả theo ngữ nghĩa riêng, không chỉnh sửa nội dung của đối tượng `String` ban đầu (vì `String` bất biến).

Một pipeline thường gặp:

~~~text
Chuỗi mẫu hoặc chuỗi đọc từ bên ngoài
       │
       ▼
stripIndent()     chuẩn hóa lề của mẫu (khi thực sự cần)
       │
       ▼
formatted(...)    điền các giá trị vào mẫu
       │
       ▼
indent(n)         đặt lề mới cho nơi hiển thị
       │
       ▼
transform(f)      tùy biến kết quả hoặc đổi sang kiểu khác
~~~

**Thứ tự không cố định cho mọi trường hợp.** Ví dụ có thể `formatted()` trực tiếp trên text block đã được trình biên dịch xử lý thụt lề, và có thể dùng `transform()` ở vị trí khác khi hàm biến đổi cần chạy trước.

## 2. Hiểu đúng từng phương thức

### 2.1. `formatted(Object... args)` — điền dữ liệu bằng cú pháp Formatter

~~~java
String message = """
        Name: %s
        Score: %d
        """.formatted("Lan", 95);
~~~

Kết quả là `"Name: Lan\nScore: 95\n"`. Cách gọi `template.formatted(args)` tương đương `String.format(template, args)`. Một số ký hiệu thường dùng:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `%s` | Biểu diễn đối tượng dạng chuỗi | `"%s".formatted("Java")` → `"Java"` |
| `%d` | Số nguyên thập phân | `"%d".formatted(15)` → `"15"` |
| `%.2f` | Số thực với hai chữ số phần thập phân | `"%.2f".formatted(1.5)` → tùy locale định dạng |
| `%%` | Ký tự `%` thực | `"Done: %d%%".formatted(80)` → `"Done: 80%"` |
| `%n` | Ký tự kết thúc dòng theo nền tảng | Khác `\n` cố định trong text block |

Hai điểm quan trọng:

1. `formatted()` dựa trên **`Formatter` và locale mặc định của loại `FORMAT`**. Với số, ngày, dấu phân cách cần kết quả cố định bất kể máy, dùng `String.format(Locale.ROOT, template, args)` thay cho `formatted()` vì `formatted()` không nhận tham số `Locale`.
2. Khuôn định dạng chứa `%` phải đúng cú pháp: muốn hiển thị phần trăm thật thì viết `%%`. Placeholder sai kiểu, thiếu đối số hoặc mẫu định dạng sai có thể gây `IllegalFormatException`. Các giá trị đối số không được tự động escape thành HTML, JSON, SQL hay shell command; cần công cụ phù hợp nếu dữ liệu đi vào các ngữ cảnh đó.

### 2.2. `stripIndent()` — bỏ lề chung và khoảng trắng cuối dòng

Với chuỗi thường (không nhất thiết là text block):

~~~java
String input = "    A  \n      B  ";
String normalized = input.stripIndent();
~~~

`normalized` là `"A\n  B"`: hai dòng cùng bỏ bốn dấu cách thụt đầu dòng; hai dấu cách dư ở cuối mỗi dòng bị xóa; hai dấu cách tương đối trước `B` được giữ. Phương thức cũng chuẩn hóa `CRLF`/`CR` thành `LF`.

Thuật toán chọn số ký tự thụt lề nhỏ nhất trên các dòng không rỗng, **đồng thời xét cả dòng cuối ngay cả khi dòng cuối là dòng rỗng**. Vì vậy một `\n` ở cuối có thể làm kết quả khác nhiều so với trực giác (xem mục 5). Mỗi ký tự whitespace ở đầu dòng được tính theo đơn vị ký tự: tab là một ký tự, không quy đổi thành nhiều dấu cách hiển thị.

`stripIndent()` khác `strip()`: `strip()` cắt whitespace ở hai *đầu của cả chuỗi*, còn `stripIndent()` xử lý từng dòng và cố gắng giữ thụt lề **tương đối giữa các dòng**.

### 2.3. `indent(int n)` — điều chỉnh lề chủ động

- `n > 0`: thêm đúng `n` dấu cách vào đầu **mỗi dòng**.
- `n < 0`: bỏ tối đa `|n|` ký tự whitespace ở đầu từng dòng; không đòi các dòng phải có cùng lượng thụt lề.
- `n == 0`: không đổi thụt lề, nhưng **vẫn chuẩn hóa dấu xuống dòng**.

Kết quả của `indent(n)` được tạo bằng cách lấy các dòng, xử lý từng dòng, rồi **thêm LF (`\n`) sau từng dòng**. Do đó đối với chuỗi không rỗng, `"Hello".indent(0)` tạo `"Hello\n"`. Đây không phải phép biến đổi vô hại đối với nội dung cần giữ nguyên byte/ký tự.

Ví dụ:

~~~java
String content = "A\n  B";
String padded = content.indent(2); // "  A\n    B\n"
String reduced = padded.indent(-2); // "A\n  B\n"
~~~

`reduced` khác `content` ở **LF cuối chuỗi**. Với tab, `"\tItem\n".indent(-1)` cho `"Item\n"` vì một ký tự tab được tính là một ký tự thụt lề.

### 2.4. `transform(Function... f)` — một chặng xử lý linh hoạt

~~~java
String text = "  Java 15  ";
String result = text.transform(String::strip); // "Java 15"
int length = text.transform(s -> s.strip().length()); // 7
~~~

Về ý nghĩa, `text.transform(f)` gọi `f.apply(text)`. `transform` không tự chuẩn hóa whitespace, không tự điền placeholder và **không bắt buộc trả về `String`**: kiểu trả về `R` do hàm quyết định, ví dụ `Integer`, `Long`, đối tượng dữ liệu hoặc một `String` khác. Nếu hàm ném exception, exception lan ra ngoài.

`transform` hữu ích khi muốn nối một bước xử lý không có sẵn dưới dạng phương thức `String` vào chuỗi gọi hàm. Không dùng nó chỉ để thay mọi lời gọi đơn giản vốn đã rõ nghĩa.

## 3. Ví dụ phối hợp đủ bốn API, từng bước

Giả sử nhận một **khuôn mẫu** có lề chung, có khoảng trắng dư ở cuối dòng và dùng CRLF (ví dụ dữ liệu đọc từ nơi khác). Ta muốn:

1. Chuẩn hóa lề của khuôn trước khi chèn dữ liệu.
2. Điền các giá trị.
3. Thụt toàn bộ báo cáo thêm hai dấu cách khi nhúng vào tài liệu cha.
4. Đổi nhãn hiển thị từ `State:` thành `Status:` bằng một hàm.

Đoạn dưới đây là phần quan trọng của chương trình hoàn chỉnh ở mục 6:

~~~java
String raw = "    Item: %s  \r\n      State: %s  ";

String cleaned = raw.stripIndent();
String filled = cleaned.formatted("Java 15", "ready");
String indented = filled.indent(2);
String result = indented.transform(s -> s.replace("State:", "Status:"));
~~~

Các giai đoạn (dùng `·` để biểu diễn một dấu cách, `<CR>`/`<LF>` để nhìn thấy dấu xuống dòng):

| Giai đoạn | Nội dung quan trọng |
| --- | --- |
| `raw` | `····Item:·%s··<CR><LF>······State:·%s··` |
| `cleaned` | `Item:·%s<LF>··State:·%s` |
| `filled` | `Item:·Java·15<LF>··State:·ready` |
| `indented` | `··Item:·Java·15<LF>····State:·ready<LF>` |
| `result` | `··Item:·Java·15<LF>····Status:·ready<LF>` |

Dòng mẫu đầu thụt bốn space, dòng thứ hai sáu space: `stripIndent()` loại bốn space chung, vẫn giữ **hai** space trước `State`. Mẫu không có LF cuối để tránh trường hợp dòng cuối rỗng làm mức lề chung bằng 0. Sau `indent(2)`, cả hai dòng tăng thêm hai space và **có một LF cuối chuỗi**.

Cùng pipeline có thể viết ngắn gọn sau khi đã hiểu rõ tác động:

~~~java
String result = raw
        .stripIndent()
        .formatted("Java 15", "ready")
        .indent(2)
        .transform(s -> s.replace("State:", "Status:"));
~~~

Cách viết theo từng biến trung gian thuận tiện hơn khi cần debug, log độ dài, hoặc kiểm tra nội dung sau mỗi giai đoạn.

## 4. Thứ tự `formatted()` và `stripIndent()` làm thay đổi dữ liệu được chèn

Khi các đối số có nhiều dòng hoặc chứa lề chủ ý, nên xử lý lề **của mẫu trước**, rồi mới gọi `formatted()`. So sánh:

~~~java
String template = "    Note: %s\n    Done: yes";
String supplied = "alpha\n      beta";

String cleanBefore = template.stripIndent().formatted(supplied);
String cleanAfter = template.formatted(supplied).stripIndent();
~~~

Kết quả biểu diễn bằng `·`:

~~~text
cleanBefore=Note:·alpha<LF>······beta<LF>Done:·yes
cleanAfter=Note:·alpha<LF>··beta<LF>Done:·yes
~~~

**Vì sao khác nhau?**

- `cleanBefore`: `stripIndent()` chỉ thấy *hai dòng của mẫu*, loại bốn space chung; `formatted()` chèn nguyên văn `supplied`, nên sáu space trước `beta` được bảo toàn.
- `cleanAfter`: `formatted()` tạo ra một chuỗi mới có thêm dòng `beta`; `stripIndent()` tiếp tục xét **toàn bộ các dòng bao gồm dữ liệu vừa chèn**, rồi loại mức lề chung. Sáu space trước `beta` bị giảm còn hai.

Đây là khác biệt quan trọng trong trình tạo báo cáo, code snippet, YAML, văn bản ký hiệu căn lề hoặc dữ liệu do người dùng cung cấp. Nếu muốn giữ bố cục của giá trị chèn, **hãy chuẩn hóa khuôn trước khi chèn**; nếu muốn chuẩn hóa *cả kết quả* thì gọi sau, nhưng cần chấp nhận nó có thể thay đổi dữ liệu.

## 5. Hai trường hợp dễ gây lỗi về ký tự xuống dòng và khoảng trắng

### 5.1. `stripIndent()` với LF cuối chuỗi

~~~java
String withLF = "    A\n    B\n";
String withoutLF = "    A\n    B";

String a = withLF.stripIndent();       // "    A\n    B\n"
String b = withoutLF.stripIndent();    // "A\nB"
~~~

Hai kết quả trên là **khác nhau dù nội dung nhìn thấy tương tự**. Với `withLF`, sau dấu `\n` cuối có một dòng kết thúc rỗng, lề của dòng đó là 0 và được đưa vào phép tìm mức thụt lề nhỏ nhất; vì thế `stripIndent()` không thể trừ bốn space chung. Với `withoutLF`, dòng cuối chứa `B` và có thụt lề bốn space; phép loại lề chung hoạt động như mong đợi.

`stripIndent()` **bảo toàn việc chuỗi ban đầu có hay không có LF cuối**, đồng thời chuẩn hóa kiểu dấu xuống dòng. Nếu chủ động cần LF cuối sau khi loại lề, có thể tổ chức mẫu **không chứa LF cuối**, gọi `stripIndent()`, rồi dùng `indent(0)` để thêm LF trong trường hợp chuỗi không rỗng. Không tự ý gọi `stripTrailing()` như một cách sửa chung, vì nó có thể loại nhiều whitespace có ý nghĩa.

### 5.2. Text block đã được trình biên dịch xử lý trước khi gọi API

~~~java
String textBlock = """
        Root: %s
          Child: %s
        """;

String formattedBlock = textBlock.formatted("A", "B");
~~~

`formattedBlock` bằng `"Root: A\n  Child: B\n"`. Trình biên dịch **đã loại thụt lề phụ trợ** của `textBlock`, vì vậy thường **không cần gọi `stripIndent()` thêm lần nữa**. Tuy nhiên, `stripIndent()` vẫn có thể biến đổi khoảng trắng dữ liệu nếu được gọi.

Ví dụ, `\s` trong text block cố ý thêm một dấu cách **sau** giai đoạn loại khoảng trắng của trình biên dịch:

~~~java
String preserved = """
        data\s
        """;
// preserved.equals("data \n") == true
// preserved.stripIndent().equals("data\n") == true
~~~

Ở đây `stripIndent()` gọi tại runtime cắt bỏ dấu cách cuối dòng đã được `\s` tạo ra. Vì vậy, với text block đã viết đúng lề và có whitespace có nghĩa, **không thêm `stripIndent()` chỉ theo thói quen**.

## 6. Chương trình Java 17+ chạy được và kết quả chính xác

Lưu thành **`StringPipelineDemo.java`**:

~~~java
public class StringPipelineDemo {
    public static void main(String[] args) {
        String raw = "    Item: %s  \r\n      State: %s  ";
        String cleaned = raw.stripIndent();
        String filled = cleaned.formatted("Java 15", "ready");
        String indented = filled.indent(2);
        String result = indented.transform(s -> s.replace("State:", "Status:"));

        System.out.println("raw=" + visible(raw));
        System.out.println("cleaned=" + visible(cleaned));
        System.out.println("filled=" + visible(filled));
        System.out.println("indented=" + visible(indented));
        System.out.println("result=" + visible(result));
        System.out.println("lineCount=" + result.transform(s -> s.lines().count()));

        String template = "    Note: %s\n    Done: yes";
        String supplied = "alpha\n      beta";
        String cleanBefore = template.stripIndent().formatted(supplied);
        String cleanAfter = template.formatted(supplied).stripIndent();
        System.out.println("cleanBefore=" + visible(cleanBefore));
        System.out.println("cleanAfter=" + visible(cleanAfter));

        System.out.println("indentZero=" + visible("Hello".indent(0)));
        System.out.println("indentMinusOne=" + visible("\tItem\n".indent(-1)));
        String textBlock = """
                Root: %s
                  Child: %s
                """;
        System.out.println("textBlock=" + visible(textBlock.formatted("A", "B")));

        String withLF = "    A\n    B\n";
        String withoutLF = "    A\n    B";
        System.out.println("stripWithLF=" + visible(withLF.stripIndent()));
        System.out.println("stripWithoutLF=" + visible(withoutLF.stripIndent()));
        System.out.println("checks=" + (
                cleaned.equals("Item: %s\n  State: %s")
                && filled.equals("Item: Java 15\n  State: ready")
                && result.equals("  Item: Java 15\n    Status: ready\n")
                && cleanBefore.equals("Note: alpha\n      beta\nDone: yes")
                && cleanAfter.equals("Note: alpha\n  beta\nDone: yes")
                && "Hello".indent(0).equals("Hello\n")
                && "\tItem\n".indent(-1).equals("Item\n")
                && textBlock.formatted("A", "B").equals("Root: A\n  Child: B\n")
                && withLF.stripIndent().equals("    A\n    B\n")
                && withoutLF.stripIndent().equals("A\nB")));
    }

    static String visible(String value) {
        return value.replace(" ", "·").replace("\t", "<TAB>")
                .replace("\r", "<CR>").replace("\n", "<LF>");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 StringPipelineDemo.java
java StringPipelineDemo
~~~

Đầu ra đã kiểm chứng trên JDK 24 với chế độ biên dịch `--release 17`:

~~~text
raw=····Item:·%s··<CR><LF>······State:·%s··
cleaned=Item:·%s<LF>··State:·%s
filled=Item:·Java·15<LF>··State:·ready
indented=··Item:·Java·15<LF>····State:·ready<LF>
result=··Item:·Java·15<LF>····Status:·ready<LF>
lineCount=2
cleanBefore=Note:·alpha<LF>······beta<LF>Done:·yes
cleanAfter=Note:·alpha<LF>··beta<LF>Done:·yes
indentZero=Hello<LF>
indentMinusOne=Item<LF>
textBlock=Root:·A<LF>··Child:·B<LF>
stripWithLF=····A<LF>····B<LF>
stripWithoutLF=A<LF>B
checks=true
~~~

Các dòng ở trên dùng `<LF>` và `<CR>` làm **ký hiệu hiển thị**, còn dữ liệu `String` trong chương trình chứa ký tự điều khiển thực sự. `checks=true` đối chiếu trực tiếp từng kết quả với chuỗi mong đợi, tránh hiểu sai do whitespace vô hình.

## 7. Chọn thứ tự và kiểm tra đúng trong ứng dụng

| Nhu cầu | Cách kết hợp nên cân nhắc | Lý do |
| --- | --- | --- |
| Mẫu văn bản thường có lề thừa | `template.stripIndent().formatted(values)` | Chuẩn hóa riêng khuôn, bảo toàn lề của dữ liệu chèn |
| Mẫu text block đã căn lề đúng | `template.formatted(values)` | Trình biên dịch đã xử lý thụt lề phụ trợ |
| Nhúng kết quả vào một cấp cấu trúc khác | `result.indent(2)` hoặc `indent(n)` phù hợp | Thêm lề mới vào từng dòng; chú ý LF cuối |
| Cần hàm hậu xử lý tùy biến | `result.transform(f)` | Giữ chuỗi gọi rõ nghĩa, có thể nhận kiểu kết quả khác |
| Cần đếm dòng sau xử lý | `result.transform(s -> s.lines().count())` | Kết quả là `long`, không phải `String` |
| Định dạng số cần nhất quán giữa các máy | `String.format(Locale.ROOT, template, args)` | `formatted` phụ thuộc locale mặc định |

**Các lỗi thường gặp:**

1. Dùng `stripIndent()` sau khi chèn chuỗi nhiều dòng mà không kiểm tra lại bố cục dữ liệu chèn.
2. Cho rằng `stripIndent()` chắc chắn bỏ phần lề chung dù chuỗi có một LF cuối (dòng cuối rỗng có thể làm `min = 0`).
3. Nhầm `indent(0)` là thao tác trả lại y nguyên chuỗi; thực tế nó chuẩn hóa dấu kết thúc dòng và thêm LF cho từng dòng không rỗng.
4. Cho rằng `indent(-n)` là phép đảo tuyệt đối của `indent(n)`; LF cuối, tab và lượng thụt lề gốc có thể khiến kết quả khác.
5. Lạm dụng `stripIndent()` trên text block vốn đã được xử lý ở thời điểm biên dịch; điều này có thể xóa dấu cách cố ý giữ bằng `\s`.
6. Quên `formatted()` dùng quy tắc của `Formatter`: `%%` cho phần trăm, `%n` theo nền tảng, kiểu placeholder phải khớp đối số và có thể phụ thuộc locale.
7. Tưởng `transform()` luôn trả về `String`; thực tế hàm có thể trả số, record hoặc kiểu khác và exception do hàm ném sẽ được truyền tiếp.

**Câu hỏi tự kiểm tra:** Với `String template = "    X: %s\n    Y: end";` và dữ liệu `"a\n      b"`, hai cách `template.stripIndent().formatted(data)` và `template.formatted(data).stripIndent()` có tạo cùng số dấu cách trước `b` không? **Không**: thứ tự thứ nhất giữ sáu dấu cách từ dữ liệu, thứ tự thứ hai còn hai dấu cách sau khi loại mức lề chung.

## Tài liệu chính thức đang áp dụng

- Oracle Java SE API, `String` (`formatted`, `stripIndent`, `indent`, `transform`): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html
- Oracle Java Language Specification, Text Blocks: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6
- OpenJDK, JEP 378 (text blocks được chuẩn hóa trong Java 15): https://openjdk.org/jeps/378