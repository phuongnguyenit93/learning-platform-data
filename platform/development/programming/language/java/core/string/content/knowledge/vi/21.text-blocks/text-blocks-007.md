# `String.stripIndent()` và `String.indent(int)` — xử lý thụt lề trong Java Text Block

Khi viết JSON, HTML, SQL hoặc thông báo nhiều dòng bằng Java, **khoảng trắng đầu dòng** có thể phục vụ hai mục đích khác nhau: căn lề mã nguồn cho dễ đọc hoặc thể hiện cấu trúc thật của văn bản. Java cung cấp hai phương thức trên `String` giúp kiểm soát chúng:

- `stripIndent()`: bỏ phần **thụt lề chung không cần thiết** ở đầu các dòng, giữ lại sự chênh lệch thụt lề giữa chúng và bỏ khoảng trắng thừa cuối dòng.
- `indent(int n)`: thêm hoặc bớt **một số ký tự thụt lề đã chỉ định** cho *từng dòng*, đồng thời chuẩn hóa dấu kết thúc dòng.

Hai phương thức đặc biệt hữu ích khi làm việc với **text block** (`"""..."""`), nhưng cũng áp dụng cho mọi `String`, kể cả dữ liệu đọc từ file hoặc từ API.

## 1. Vì sao thụt lề trong text block cần được hiểu đúng?

Java 15 chính thức hỗ trợ text block: một cách viết chuỗi nhiều dòng bằng ba dấu ngoặc kép. Mã Java thường được thụt lề theo lớp, phương thức, khối điều kiện; nếu giữ nguyên mọi khoảng trắng trong source, chuỗi kết quả có thể bị lệch quá sâu.

Ví dụ:

```java
String html = """
        <ul>
          <li>Java</li>
          <li>String</li>
        </ul>
        """;
```

Với cách bố trí trên, giá trị thực của `html` tương đương:

```text
<ul>
  <li>Java</li>
  <li>String</li>
</ul>
```

Trong chuỗi thực tế còn có ký tự `\n` sau `</ul>`. Trình biên dịch **đã tự bỏ khoảng trắng thụt lề phụ thuộc vị trí mã nguồn** nhưng giữ lại hai dấu cách trước mỗi thẻ `<li>`. Cơ chế này gọi là bỏ *incidental indentation* (thụt lề phụ).

**Điểm mấu chốt:** trình biên dịch đã xử lý thụt lề của text block khi tạo giá trị `String`. Gọi `stripIndent()` lần nữa trên text block đó không có nghĩa là Java sẽ tiếp tục xóa một mức thụt lề tùy ý.

## 2. `stripIndent()` hoạt động như thế nào?

Chữ ký API:

```java
public String stripIndent()
```

`stripIndent()` được bổ sung ở **Java 15**. Thuật toán áp dụng cho chuỗi nhiều dòng:

1. Phân chia văn bản thành các dòng. `\n`, `\r`, `\r\n` là dấu kết thúc dòng hợp lệ.
2. Với **mọi dòng không rỗng theo `isBlank()`**, đếm số ký tự khoảng trắng ở đầu dòng. **Dòng cuối cũng được xét, ngay cả khi nó là dòng trống.**
3. Chọn số nhỏ nhất trong các mức thụt lề ấy (thường gọi là *minimum indentation*).
4. Bỏ đúng số ký tự khoảng trắng đầu dòng đó khỏi mỗi dòng **không trống**, đồng thời bỏ mọi khoảng trắng cuối dòng; các dòng chỉ có khoảng trắng trở thành chuỗi rỗng.
5. Ghép lại bằng ký tự xuống dòng `\n` (LF), giữ nguyên **số lượng dấu kết thúc dòng** của đầu vào.

Ví dụ, dùng dấu `·` để biểu diễn một dấu cách cho dễ quan sát:

```text
Trước stripIndent():
····root··
······child··

Sau stripIndent():
root
··child
```

Hai dòng ban đầu lần lượt có **4** và **6** dấu cách ở đầu. Mức thụt lề chung là **4** nên kết quả còn **0** và **2** dấu cách. Hai dấu cách cuối từng dòng bị bỏ.

Có thể tự kiểm tra:

```java
String text = "    root  \n      child  ";
String output = text.stripIndent();
System.out.println(output.equals("root\n  child")); // true
```

**Khác với `strip()`:** `strip()` chỉ loại khoảng trắng ở *hai đầu toàn bộ chuỗi*; `stripIndent()` xem xét thụt lề **theo từng dòng** và giữ cấu trúc tương đối bên trong.

### Ngoại lệ dễ nhầm: dấu xuống dòng cuối chuỗi

Hãy so sánh:

```java
String a = "    root\n      child";
String b = "    root\n      child\n";

System.out.println(a.stripIndent().equals("root\n  child")); // true
System.out.println(b.stripIndent().equals(b));             // true
```

Đối với `b`, sau dấu `\n` cuối có **một dòng rỗng cuối cùng**, có mức thụt lề bằng 0. Vì thuật toán **vẫn xét dòng cuối dù nó trống**, mức thụt chung là 0: hai dòng nội dung **không bị kéo về trái**. Đây không phải lỗi của Java; nó là hệ quả của quy tắc xác định minimum indentation.

Điều này rất quan trọng khi nhận chuỗi từ file hoặc khi so sánh với text block. Text block có dấu kết thúc dòng theo cấu trúc của chính literal, và trình biên dịch còn xét vị trí dấu `"""` đóng để xác định phần thụt lề phụ trước khi tạo `String`. Vì vậy **đừng suy luận rằng gọi `stripIndent()` trên một `String` đã kết thúc bằng LF luôn giống thao tác mà trình biên dịch đã thực hiện trên text block**.

## 3. `indent(int n)` thêm và bớt thụt lề

Chữ ký API:

```java
public String indent(int n)
```

`indent(int)` có từ **Java 12**. Giá trị `n` xác định cách điều chỉnh ở đầu **mỗi dòng**:

| Tham số | Hành vi |
| --- | --- |
| `n > 0` | Chèn đúng `n` dấu cách `U+0020` vào đầu mỗi dòng |
| `n = 0` | Không sửa thụt lề từng dòng, **nhưng vẫn chuẩn hóa dấu xuống dòng** |
| `n < 0` | Bỏ tối đa `abs(n)` ký tự khoảng trắng đầu mỗi dòng; dòng nào ít hơn thì bỏ hết phần khoảng trắng đầu dòng |

Các dấu cách bên phải nội dung **không bị tự động xóa** bởi `indent()`. Khi `n < 0`, mỗi dòng được xử lý riêng; nó không tính mức thụt lề chung nhỏ nhất như `stripIndent()`.

Giả sử `text = "    root  \n      child  "`:

| Lệnh | Kết quả (dấu `·` là một dấu cách, `\n` là ký tự LF) |
| --- | --- |
| `text.stripIndent()` | `root\n··child` |
| `text.indent(2)` | `······root··\n········child··\n` |
| `text.indent(-2)` | `··root··\n····child··\n` |
| `text.indent(0)` | `····root··\n······child··\n` |

**Chú ý dấu LF ở cuối:** `indent()` tách chuỗi thành các dòng theo quy tắc tương tự `lines()`, rồi **thêm `\n` vào sau mỗi dòng trong kết quả**. Vì thế, chuỗi đầu vào có nội dung nhưng không kết thúc bằng dấu xuống dòng sẽ **có `\n` ở cuối sau khi gọi `indent()`**, kể cả `indent(0)`. Với chuỗi rỗng `""`, kết quả vẫn là chuỗi rỗng.

Ví dụ:

```java
System.out.println("A".indent(0).equals("A\n")); // true
System.out.println("".indent(3).equals(""));      // true
```

### Số âm không có nghĩa là bỏ đúng từng ấy dấu cách

`indent(-4)` bỏ **tối đa bốn ký tự khoảng trắng đầu mỗi dòng**. Dòng chỉ có hai dấu cách đầu dòng sẽ bị bỏ hai; dòng có sáu dấu cách sẽ còn hai. Nếu một dòng vốn không có thụt lề, dòng đó giữ nguyên.

Ký tự tab `\t` được tính là **một ký tự khoảng trắng** trong phép đếm này; Java không tự đổi tab thành 4 hoặc 8 dấu cách hiển thị. Kết quả có thể gây ngạc nhiên khi đầu vào trộn tab với space.

## 4. Ví dụ Java 17+ chạy độc lập, thấy rõ từng dấu cách

Để phân biệt dấu cách và LF, dùng hàm `show` đổi dấu cách thành `_` và chuyển dấu xuống dòng thật thành chữ `\n`.

Tạo file `IndentAndStripIndentDemo.java`:

```java
public class IndentAndStripIndentDemo {

    private static String show(String value) {
        return value.replace(" ", "_")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String raw = "    root  \n      child  ";

        System.out.println("raw          = " + show(raw));
        System.out.println("stripIndent  = " + show(raw.stripIndent()));
        System.out.println("indent(2)    = " + show(raw.indent(2)));
        System.out.println("indent(-2)   = " + show(raw.indent(-2)));
        System.out.println("indent(0)    = " + show(raw.indent(0)));

        String block = """
                root
                  child
                """;

        System.out.println("textBlock    = " + show(block));
        System.out.println("block.indent = " + show(block.indent(2)));

        String withFinalLf = "    root\n      child\n";
        System.out.println("endLF.strip  = "
                + show(withFinalLf.stripIndent()));

        String windowsLines = "  one\r\n    two\r";
        System.out.println("CRLF.indent  = "
                + show(windowsLines.indent(0)));
    }
}
```

Biên dịch và chạy:

```bash
javac IndentAndStripIndentDemo.java
java IndentAndStripIndentDemo
```

Kết quả stdout (dấu `_` là **một** dấu cách thật trong chuỗi đầu vào):

```text
raw          = ____root__\n______child__
stripIndent  = root\n__child
indent(2)    = ______root__\n________child__\n
indent(-2)   = __root__\n____child__\n
indent(0)    = ____root__\n______child__\n
textBlock    = root\n__child\n
block.indent = __root\n____child\n
endLF.strip  = ____root\n______child\n
CRLF.indent  = __one\n____two\n
```

Quan sát ba điều:

1. `stripIndent()` bỏ phần thụt chung và khoảng trắng cuối mỗi dòng khi đầu vào **không có LF cuối**.
2. `indent(2)` và `indent(-2)` giữ nguyên các dấu cách cuối nội dung; mọi dòng trong kết quả có LF kết thúc.
3. Text block đã được trình biên dịch bỏ thụt lề phụ; gọi `block.indent(2)` thêm hai dấu cách mới cho từng dòng.

## 5. Kết hợp text block với `indent()` khi tạo nội dung lồng nhau

Một ứng dụng phổ biến là tạo đoạn HTML, thông báo hoặc cấu trúc cấu hình ở độ sâu khác nhau:

```java
String item = """
        <li>Java</li>
        <li>Regex</li>
        """;

String html = "<ul>\n"
        + item.indent(2)
        + "</ul>\n";

System.out.print(html);
```

Kết quả:

```html
<ul>
  <li>Java</li>
  <li>Regex</li>
</ul>
```

Phân tích: text block `item` sau biên dịch là `"<li>Java</li>\n<li>Regex</li>\n"`, nên `indent(2)` đặt hai dấu cách trước mỗi thẻ. Cách này tiện khi tạo một khối văn bản rồi lồng vào một khối khác.

**Không nên xem `indent()` là trình định dạng HTML, JSON hay YAML.** Nó chỉ thay đổi dấu cách đầu dòng và dấu kết thúc dòng, không kiểm tra cú pháp của cấu trúc bên trong. Với JSON có giá trị cần escape, hãy dùng serializer; với HTML từ dữ liệu không tin cậy, cần escape dữ liệu trước khi chèn.

### Chỉnh thụt lề bằng vị trí dấu `"""` đóng

Trong text block, lượng thụt lề phụ bị bỏ thường phụ thuộc vào dòng có ít dấu cách nhất **và** vị trí dấu `"""` đóng:

```java
String a = """
        first
          second
        """;

String b = """
            first
              second
        """;
```

Ở `a`, kết quả là `"first\n  second\n"`. Ở `b`, dấu đóng nằm ít thụt hơn phần nội dung: kết quả giữ bốn dấu cách trước `first` và sáu trước `second`. Điều này cho phép chủ động giữ một mức thụt lề, nhưng nên ưu tiên bố cục text block dễ đọc; khi cần tăng/giảm thụt lề **theo dữ liệu runtime**, `indent(n)` rõ ràng hơn.

## 6. Khoảng trắng cuối dòng, dòng trống và dấu xuống dòng

### Khoảng trắng cuối dòng

`stripIndent()` xóa khoảng trắng ở **cuối từng dòng**, kể cả khi đó là khoảng trắng có chủ ý. `indent()` không tự xóa phần đó. Nếu định dạng đầu ra cần giữ khoảng trắng cuối dòng (một số giao thức hoặc biểu diễn), hãy chọn API cẩn thận.

Trong text block, trình biên dịch cũng coi khoảng trắng cuối dòng viết trực tiếp là phụ và thường loại bỏ. Java có escape `\s` để biểu diễn **một dấu cách có chủ ý**:

```java
String withSpace = """
        value\s
        """;

System.out.println(withSpace.equals("value \n")); // true
```

Escape `\s` được xử lý sau bước bỏ khoảng trắng phụ nên có thể giữ dấu cách cuối dòng. Nếu gọi thêm `stripIndent()` lên `withSpace`, dấu cách cuối dòng đó có thể bị loại: phương thức runtime không biết nó có nguồn gốc từ escape.

### Dòng trống

`stripIndent()` thay một dòng chỉ chứa khoảng trắng bằng dòng rỗng, nhưng giữ số dấu xuống dòng. `indent(n)` xử lý mỗi dòng theo giá trị `n`: ví dụ khi `n > 0`, nó vẫn thêm dấu cách vào đầu một dòng rỗng. Hãy dùng `show` hoặc `String.equals` để kiểm tra chính xác thay vì chỉ nhìn văn bản hiển thị.

### Chuẩn hóa CRLF và CR

Cả hai phương thức tạo kết quả dùng LF `\n` làm ký tự xuống dòng, kể cả khi đầu vào chứa CRLF `\r\n` hoặc CR `\r`. Ví dụ:

```java
String source = "  A\r\n    B\r";
String output = source.indent(0);
System.out.println(output.equals("  A\n    B\n")); // true
```

Điều này hữu ích khi xử lý văn bản đến từ nhiều hệ điều hành; tuy nhiên nếu cần giữ **nguyên byte** hoặc kiểu kết thúc dòng ban đầu của file, không được coi hai phương thức là thao tác bảo toàn dữ liệu.

## 7. Chọn phương thức theo yêu cầu

| Tình huống | Chọn |
| --- | --- |
| Văn bản nhiều dòng đến từ hệ thống khác, tất cả các dòng bị thụt sâu chung | `stripIndent()`, nhưng kiểm tra trường hợp dòng cuối trống |
| Đã có text block, muốn lồng toàn bộ nội dung sâu thêm bốn cột dấu cách | `indent(4)` |
| Muốn bỏ tối đa hai ký tự khoảng trắng đầu **mỗi dòng** | `indent(-2)` |
| Muốn giữ nguyên độ thụt lề, chỉ chuẩn hóa LF và thêm LF cuối cho mỗi dòng | `indent(0)` |
| Muốn xóa khoảng trắng ở hai đầu **toàn chuỗi**, không phân tích từng dòng | `strip()` |
| Muốn bảo toàn nguyên trạng từng dấu cách và CRLF ban đầu | Không gọi các phương thức chuẩn hóa thụt lề này |

Khi thụt lề có ý nghĩa cấu trúc (như YAML), **không tự động kéo lề bằng `stripIndent()` nếu chưa kiểm tra đầu vào**; đặc biệt, hãy kiểm tra dòng cuối, dòng trống và khoảng trắng có chủ ý. Nếu cần độ thụt chung ổn định, có thể xây dựng quy tắc riêng dựa trên định dạng đó.

## 8. Lỗi thường gặp

1. **Gọi `stripIndent()` hai lần với kỳ vọng mỗi lần giảm một cấp thụt lề.** Sau lần đầu, mức thụt chung có thể bằng 0; gọi tiếp không phải cách xóa thêm một cấp.
2. **Không xét LF cuối chuỗi.** Dòng trống cuối có mức thụt 0 và có thể khiến `stripIndent()` không kéo các dòng trước về trái.
3. **Nhầm `indent(-n)` với `stripIndent()`.** Phép số âm cắt đến `n` ký tự ở từng dòng; nó có thể làm mất thụt lề tương đối nếu các dòng có ít khoảng trắng.
4. **Tưởng `indent(0)` không thay đổi dữ liệu.** Nó vẫn chuẩn hóa CRLF/CR thành LF và có thể thêm LF cuối.
5. **Tin rằng `indent(n)` xóa khoảng trắng cuối dòng.** Chỉ `stripIndent()` thực hiện loại bỏ khoảng trắng cuối dòng; `indent()` giữ chúng.
6. **Trộn tab và dấu cách rồi đo mức thụt lề bằng mắt.** Một ký tự tab được tính là một ký tự chứ không phải số cột hiển thị; cách căn lề có thể khác nhau tùy trình soạn thảo.
7. **Thêm `stripIndent()` vào text block đã có cấu trúc đúng.** Trình biên dịch đã bỏ thụt lề phụ. Hãy kiểm tra `String` thực tế trước khi sửa thêm.
8. **Bỏ qua tính bất biến của `String`.** Cả hai phương thức trả về một chuỗi mới; hãy gán hoặc sử dụng kết quả: `text = text.indent(2);` nếu muốn giữ thay đổi.

## 9. Tự kiểm tra kiến thức

**Câu 1.** `"   one\n     two".stripIndent()` trả về gì?

Đáp án: `"one\n  two"`. Mức thụt chung nhỏ nhất là ba dấu cách.

**Câu 2.** `"A".indent(0).equals("A")` là `true` hay `false`?

Đáp án: `false`. Kết quả là `"A\n"`, vì `indent()` thêm LF ở cuối dòng.

**Câu 3.** `"  A\n B".indent(-3)` tạo chuỗi gì?

Đáp án: `"A\nB\n"`. Mỗi dòng mất tối đa ba ký tự khoảng trắng đầu dòng, rồi có LF cuối.

**Câu 4.** Vì sao `"  A\n  B\n".stripIndent()` vẫn giữ hai dấu cách đầu mỗi dòng?

Đáp án: dòng cuối sau ký tự LF là dòng rỗng có mức thụt bằng 0, làm minimum indentation bằng 0.

**Câu 5.** Text block đã chứa `"A\n  B\n"`. Muốn thêm bốn dấu cách trước mỗi dòng mà vẫn giữ hai dấu cách tương đối trước `B`, dùng gì?

Đáp án: `text.indent(4)`, kết quả `"    A\n      B\n"`.

**Ghi nhớ:** `stripIndent()` tìm và loại *thụt lề chung* (đồng thời loại khoảng trắng cuối dòng); `indent(n)` cộng/trừ *lượng thụt xác định ở từng dòng* và luôn chuẩn hóa kết thúc dòng. Text block tự xử lý thụt lề phụ tại thời điểm biên dịch, nên cần phân biệt **chuỗi trong mã nguồn** với **giá trị `String` ở runtime**.

## Tài liệu chính thức

- [`String.indent(int)` và `String.stripIndent()`, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Text Blocks — Oracle Java Language Guide](https://docs.oracle.com/en/java/javase/21/language/text-blocks.html)
