# Đẳng thức nội dung giữa text block và string literal (Java 15+)

## 1. Cùng một `String`, khác cách biểu diễn trong mã nguồn

Từ Java 15, **text block** (`""" ... """`) là một cách viết literal cho đối tượng `java.lang.String`, đặc biệt hữu ích với chuỗi nhiều dòng. **String literal** thông thường (`"..."`) cũng tạo giá trị kiểu `String`. Hai cách viết **bằng nhau về nội dung** khi các ký tự thu được sau khi Java xử lý cú pháp là giống hệt nhau, theo đúng thứ tự.

Ví dụ, hai biểu thức sau cho cùng nội dung, bao gồm dấu xuống dòng cuối chuỗi:

```java
String regular = "Hello\nJava\n";
String block = """
        Hello
        Java
        """;

System.out.println(regular.equals(block)); // true
```

Kết quả của cả hai là dãy ký tự `H e l l o \n J a v a \n`. Dấu xuống dòng và khoảng trắng là **một phần của nội dung**; cùng nhìn thấy chữ “Hello” và “Java” trên màn hình không đủ để kết luận hai chuỗi bằng nhau.

**Quy tắc chính:** Hãy dùng `a.equals(b)` để so sánh nội dung khi `a` chắc chắn khác `null`, hoặc `Objects.equals(a, b)` (cần `import java.util.Objects;`) khi có thể có `null`. Phép `==` kiểm tra hai biến có trỏ đến **cùng đối tượng** hay không; nó không phải phép so sánh nội dung tổng quát.

## 2. Ví dụ đầy đủ: `equals` và `==` cho kết quả gì?

Lưu mã dưới tên **`TextBlockContentEquality.java`**:

```java
public class TextBlockContentEquality {
    public static void main(String[] args) {
        String literal = "Xin chào!\nJava 15\n";
        String block = """
                Xin chào!
                Java 15
                """;

        String builtAtRuntime = new String(literal);
        String withoutLastNewline = """
                Xin chào!
                Java 15""";

        System.out.println(literal.equals(block));
        System.out.println(literal == block);
        System.out.println(builtAtRuntime.equals(block));
        System.out.println(builtAtRuntime == block);
        System.out.println(
                withoutLastNewline.equals("Xin chào!\nJava 15")
        );
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên (tính năng này đã chính thức từ Java 15, không cần cờ preview):

```bash
javac -encoding UTF-8 TextBlockContentEquality.java
java TextBlockContentEquality
```

Đầu ra chính xác:

```text
true
true
true
false
true
```

Giải thích từng dòng:

1. `literal.equals(block)` là `true` vì nội dung hai chuỗi hoàn toàn giống nhau.
2. `literal == block` cũng là `true` **trong trường hợp cụ thể này**: string literal và text block đều là các hằng chuỗi được Java **intern**, nên khi có cùng giá trị, chúng tham chiếu cùng đối tượng trong string pool.
3. `builtAtRuntime.equals(block)` vẫn là `true`: hàm `new String(literal)` tạo một đối tượng khác nhưng giữ nguyên dãy ký tự.
4. `builtAtRuntime == block` là `false` vì đây là hai đối tượng khác nhau. Điều đó chứng minh tại sao không nên dựa vào `==` để kiểm tra nội dung ở chương trình thực tế.
5. Text block có dấu đóng `"""` ngay sau `Java 15` **không** có dấu xuống dòng cuối, nên bằng với `"Xin chào!\nJava 15"`.

Kết luận về `==` cần được hiểu đúng: **hai literal hằng có nội dung giống nhau được intern**, nên `==` có thể cho kết quả `true`; nhưng khi một giá trị đến từ đầu vào, thao tác xử lý chuỗi, API hoặc một đối tượng mới, không thể dùng kết quả đó làm quy tắc so sánh. Hãy giữ `equals` làm lựa chọn mặc định.

## 3. Java tính nội dung text block như thế nào?

Không được so sánh trực tiếp ký tự hiển thị giữa hai dấu `"""` với ký tự ghi trong `"..."`. Khi xử lý text block, Java thực hiện theo thứ tự:

1. **Chuẩn hóa dấu kết thúc dòng:** dấu xuống dòng thực trong mã nguồn là CR, CRLF hay LF đều được đưa về **LF** (`\n`, U+000A) trong giá trị text block.
2. **Loại bỏ khoảng trắng thụt lề phụ (incidental indentation):** Java xác định lề chung từ các dòng không trống và, khi dấu đóng ở một dòng riêng, cả vị trí dấu đóng; lề chung này bị loại khỏi mỗi dòng, còn phần thụt lề tương đối có ý nghĩa vẫn được giữ. Khoảng trắng thừa cuối từng dòng cũng bị loại.
3. **Diễn giải escape sequence:** những chuỗi ký tự như `\n`, `\t`, `\s`, `\"`, `\\` hay ký tự `\` ngay trước một xuống dòng được chuyển thành giá trị tương ứng.

Sau đó, kết quả là một `String` bình thường. String literal `"..."` cũng diễn giải escape sequence, nhưng **không có cơ chế tự động loại lề và khoảng trắng cuối dòng theo bố cục mã nguồn**. Vì vậy, khi chuyển từ `"..."` sang text block, bạn phải so sánh **giá trị sau xử lý**, không chỉ so sánh cách trình bày.

### 3.1. Dấu xuống dòng cuối chuỗi

```java
String withFinalNewline = """
        A
        B
        """;

String withoutFinalNewline = """
        A
        B""";

System.out.println(withFinalNewline.equals("A\nB\n")); // true
System.out.println(withoutFinalNewline.equals("A\nB")); // true
System.out.println(withFinalNewline.equals("A\nB"));  // false
```

Với dấu đóng `"""` trên dòng riêng ngay sau dòng `B`, xuống dòng sau `B` vẫn thuộc nội dung. Đặt dấu đóng cùng dòng với `B` sẽ không có xuống dòng cuối. Dòng trống sau dấu mở `"""` bắt buộc về **cú pháp** không tự tạo một dòng trống ở đầu giá trị.

Nếu cần xuống dòng cuối nhưng muốn trình bày khác, có thể giữ dấu đóng trên dòng riêng. Nếu cần không có xuống dòng cuối, đặt dấu đóng trên dòng nội dung cuối là cách dễ đọc.

### 3.2. Lề chung bị bỏ, lề tương đối còn lại

```java
String jsonBlock = """
        {
          "name": "Lan",
          "active": true
        }
        """;

String jsonLiteral = "{\n"
        + "  \"name\": \"Lan\",\n"
        + "  \"active\": true\n"
        + "}\n";

System.out.println(jsonBlock.equals(jsonLiteral)); // true
```

Các dòng của text block cùng thụt vào để dễ đọc trong chương trình. Lề chung biến mất khi biên dịch; hai dấu cách trước `"name"` và `"active"` là **lề tương đối**, nên tồn tại trong giá trị và cần xuất hiện tương ứng trong string literal.

Di chuyển dấu đóng `"""` sang trái hoặc phải có thể thay đổi lề chung và vì vậy thay đổi giá trị thu được. Đừng mặc định rằng việc căn lề mã nguồn là vô hại trong mọi trường hợp.

### 3.3. Khoảng trắng cuối dòng và escape `\s`

Text block thường loại bỏ các dấu cách nằm ở cuối dòng trong mã nguồn. Khi **cần giữ đúng một dấu cách cuối dòng**, dùng `\s` (escape cho ký tự khoảng trắng U+0020); vì escape được diễn giải sau bước xử lý lề nên dấu cách này được giữ:

```java
String withTrailingSpace = """
        A\s
        """;

System.out.println(withTrailingSpace.equals("A \n")); // true
System.out.println(withTrailingSpace.equals("A\n"));  // false
```

Đây là khác biệt quan trọng khi lưu nội dung mà dấu cách có ý nghĩa, như một số mẫu kiểm thử, thông điệp giao thức hoặc văn bản cần so sánh chính xác từng ký tự. Không nên thêm các dấu cách vô hình ở cuối dòng text block rồi tin rằng chúng sẽ được giữ lại.

### 3.4. Ngắt dòng trong mã nguồn không nhất thiết tạo ký tự xuống dòng

Trong text block, dấu `\` đặt **ngay trước** xuống dòng thực của mã nguồn báo hiệu **line continuation**: dấu xuống dòng đó không xuất hiện trong chuỗi kết quả.

```java
String continuedLine = """
        A\
        B""";

System.out.println(continuedLine.equals("AB"));   // true
System.out.println(continuedLine.equals("A\nB")); // false
```

Không nhầm cú pháp này với `\n`: `\n` **thêm** ký tự xuống dòng LF; `\` ở cuối dòng text block **loại** xuống dòng tại vị trí đó. Khi cần nội dung giống string literal, cần tính đúng cả escape và vị trí dấu đóng.

### 3.5. CRLF, LF và Unicode

Text block chuẩn hóa **xuống dòng vật lý trong mã nguồn** thành `\n`. Vì thế:

```java
String block = """
        one
        two
        """;

System.out.println(block.equals("one\ntwo\n"));     // true
System.out.println(block.equals("one\r\ntwo\r\n")); // false
```

Nếu dữ liệu đến từ tệp hay hệ thống dùng CRLF (`\r\n`), hai chuỗi có thể nhìn như nhau trong trình soạn thảo nhưng `equals` vẫn là `false`. Khi yêu cầu nghiệp vụ cho phép, có thể chuẩn hóa **cả hai phía theo cùng một quy tắc** trước khi so sánh, chẳng hạn thay `\r\n` thành `\n`. Đừng chuẩn hóa tùy tiện nếu byte hoặc ký tự xuống dòng có ý nghĩa của riêng chúng.

Tương tự, `String.equals` kiểm tra chính xác dãy đơn vị UTF-16. Chữ hoa/chữ thường, dấu cách thường so với tab, và các cách biểu diễn Unicode khác nhau của ký tự có dấu không tự động được xem là bằng nhau. Text block không thêm cơ chế so sánh không phân biệt hoa thường hay chuẩn hóa Unicode.

## 4. Các trường hợp dễ nhầm khi so sánh

| Tình huống | Có bằng nhau về nội dung không? | Vì sao |
| --- | --- | --- |
| `"""` chứa `A` rồi xuống dòng và dấu đóng trên dòng riêng, so với `"A\n"` | **Có** | Cùng kết thúc bằng LF. |
| Text block trên so với `"A"` | **Không** | Text block có thêm LF cuối. |
| Text block `A` rồi dấu đóng ngay sau `A`, so với `"A"` | **Có** | Cả hai không có LF cuối. |
| Text block `A\s` rồi xuống dòng, so với `"A \n"` | **Có** | `\s` giữ dấu cách cuối dòng. |
| Text block hai dòng nguồn `A`, `B`, so với `"A\r\nB\n"` | **Không** | CRLF khác LF. |
| Hai giá trị `String` giống nội dung nhưng một bên là `new String(...)` | `equals`: **Có**; `==`: thường **Không** | Nội dung giống nhau, tham chiếu khác nhau; với `new String(...)` trong ví dụ trên, `==` chắc chắn `false`. |

**Phân biệt “nội dung bằng nhau” với “ý nghĩa tương đương”:** Hai JSON có khoảng trắng khác nhau có thể biểu diễn cùng dữ liệu khi được parser đọc, nhưng `String.equals` vẫn trả về `false`. Nếu bài toán muốn so sánh cấu trúc JSON, hãy parse rồi so sánh cấu trúc; nếu bài toán yêu cầu so sánh văn bản nguyên trạng, hãy dùng `equals`.

## 5. Cách đối chiếu chính xác khi đổi string literal sang text block

Khi refactor một chuỗi có `\n`, dấu nháy và phép nối `+` sang text block:

1. **Viết ra giá trị kỳ vọng** từ string literal gốc, đặc biệt là LF cuối, CRLF, tab, dấu cách đầu/cuối dòng và chuỗi escape.
2. **Viết text block** với dấu mở `"""` rồi xuống dòng; đặt dấu đóng ở vị trí kiểm soát được dấu LF cuối và lề chung.
3. **So sánh bằng `equals` trong kiểm thử**, không dùng `==` để chứng minh tính tương đương.
4. **Nếu khác nhau, kiểm tra ký tự vô hình** bằng `length()`, `charAt()`, phép thay dấu xuống dòng bằng ký hiệu hiển thị, hoặc kiểm tra từng vị trí. Hãy xem xét dấu xuống dòng cuối và thụt lề trước.
5. **Chỉ chuẩn hóa nếu yêu cầu bài toán cho phép.** Các hàm `strip()`, `trim()`, `stripTrailing()` hoặc biểu thức thay nhiều khoảng trắng bằng một khoảng trắng đều có thể xóa thông tin cần giữ; đừng gọi chúng chỉ để khiến `equals` trở thành `true`.

Một cách hiển thị dấu cách và xuống dòng khi debug:

```java
static String visible(String value) {
    return value
            .replace(" ", "·")
            .replace("\r", "\\r")
            .replace("\n", "\\n\n");
}
```

Ví dụ, `visible("A \n")` trả về văn bản có dấu cách thành `·` và LF thành hai ký tự `\n` rồi xuống dòng thực. Hàm này là **công cụ hiển thị khi kiểm tra**, không phải hàm chuẩn hóa dữ liệu để so sánh.

### Kiểm tra nhanh với biểu thức `equals`

```java
String expected = "first\n  second\n";
String actual = """
        first
          second
        """;

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Khác nội dung: expected=[" + expected + "], actual=[" + actual + "]"
    );
}
```

Điểm cần kiểm tra: `actual` phải chứa đúng **hai dấu cách** trước `second`, không có dấu cách trước `first`, và có `\n` cuối chuỗi.

## 6. Tự kiểm tra kiến thức

**Câu 1.** Giá trị của text block dưới đây có bằng `"red\nblue"` không?

```java
String colors = """
        red
        blue
        """;
```

**Đáp án:** Không. `colors` bằng `"red\nblue\n"` vì có dấu LF cuối.

**Câu 2.** Có thể chứng minh hai chuỗi mang cùng nội dung bằng `a == b` không?

**Đáp án:** Không. Hai literal hằng bằng nhau có thể cùng tham chiếu đến chuỗi đã intern, nhưng đối tượng `String` được tạo lúc chạy vẫn có thể khác tham chiếu. So sánh nội dung bằng `equals`.

**Câu 3.** Text block có tự biến tab và dấu cách thành tương đương nhau khi so sánh không?

**Đáp án:** Không. Thao tác loại bỏ lề chung chỉ xử lý cách viết text block khi tạo giá trị; khi đã tạo, `String.equals` vẫn so sánh chính xác các ký tự.

## Ghi nhớ

- **Text block và string literal đều tạo `String`**; không có quy tắc `equals` riêng cho text block.
- **Tương đương về nội dung = dãy ký tự sau xử lý giống hệt nhau.** Cẩn thận với LF cuối, lề tương đối, khoảng trắng cuối dòng, `\s`, line continuation và CRLF.
- **`==` có thể là `true` với hai literal cùng được intern**, nhưng **`equals` mới là cách so sánh nội dung đáng tin cậy**.
- Khi chuyển mã, hãy kiểm thử giá trị thực; không suy ra nội dung chỉ từ cách text block trông trên màn hình.

### Tài liệu chuẩn còn hiệu lực

- [Oracle Java Text Blocks (Java 25)](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html) — cú pháp, xử lý lề, LF cuối, escape và cơ chế intern.
- [Java Language Specification, `3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6) — định nghĩa giá trị text block.
- [Java Language Specification, `15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.29) — hằng chuỗi và interning.
