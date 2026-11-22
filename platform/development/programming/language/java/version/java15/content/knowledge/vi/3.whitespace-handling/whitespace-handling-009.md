# Thứ tự chuẩn hóa dòng, loại thụt lề và xử lý escape trong Java text block

## 1. Quy tắc cốt lõi: ba bước theo đúng thứ tự

Từ **Java 15**, text block (`""" ... """`) là cú pháp chính thức để tạo một giá trị `String`. Nội dung giữa hai dấu phân định **không được đưa nguyên xi** vào `String`: trình biên dịch xử lý theo thứ tự cố định:

1. **Chuẩn hóa ký tự kết thúc dòng (line terminator normalization):** `CRLF` (`\r\n`) và `CR` (`\r`) có trong *mã nguồn* trở thành `LF` (`\n`); `LF` giữ nguyên.
2. **Loại khoảng trắng phụ trợ (incidental white space stripping):** bỏ mức thụt lề dùng để căn chỉnh text block trong mã Java, giữ mức thụt lề tương đối có ý nghĩa; bỏ khoảng trắng ở cuối mỗi dòng.
3. **Diễn giải escape sequence (escape translation):** sau hai bước trên mới chuyển các chuỗi escape như `\t`, `\n`, `\r`, `\s` hoặc `\` ngay trước dấu xuống dòng thành ký tự/hiệu ứng tương ứng.

Sơ đồ:

~~~text
Nội dung trong mã nguồn Java
    ↓ (1) CRLF/CR → LF
Nội dung có dấu xuống dòng đã thống nhất
    ↓ (2) bỏ thụt lề phụ trợ và khoảng trắng cuối dòng
Nội dung đã chỉnh khoảng trắng
    ↓ (3) diễn giải escape
Giá trị String cuối cùng
~~~

Đây là **ngữ nghĩa của text block tại thời điểm biên dịch**; không cần gọi `stripIndent()` hoặc `translateEscapes()` thủ công trên `String` đã tạo. Đặc tả mô tả bước 2 và 3 có hiệu ứng *như thể* dùng `String.stripIndent()` và `String.translateEscapes()`. Thứ tự này vẫn được áp dụng trong Java hiện đại; không phải cơ chế thử nghiệm hoặc cũ.

## 2. Bước 1 — Chuẩn hóa dấu kết thúc dòng trong mã nguồn

Một tệp `.java` có thể dùng LF (thường gặp trên Linux/macOS), CRLF (thường gặp trên Windows) hoặc CR. Bên trong text block, trình biên dịch chuyển:

| Dấu kết thúc dòng thực sự trong mã nguồn | Giá trị sau bước 1 |
| --- | --- |
| LF (`\n`) | Một LF (`\n`) |
| CRLF (`\r\n`) | Một LF (`\n`) |
| CR (`\r`) | Một LF (`\n`) |

Ví dụ:

~~~java
String lines = """
        A
        B
        """;
~~~

Dù lưu tệp nguồn bằng LF hay CRLF, kết quả vẫn tương đương với `"A\nB\n"`. Dòng xuống ngay sau bộ dấu mở `"""` là phần bắt buộc của cú pháp và **không tạo một `\n` ở đầu chuỗi**. Dấu xuống sau `B`, trước dòng chứa dấu đóng, tạo `\n` cuối chuỗi.

**Giới hạn của bước 1:** bước này chuẩn hóa *ký tự xuống dòng có sẵn trong mã nguồn*, không phải mọi ký tự xuống dòng có thể xuất hiện sau này. Ví dụ `\r` viết bằng hai ký tự `\` và `r` lúc này vẫn chưa được diễn giải; đến bước 3 nó mới trở thành ký tự CR thực sự. Vì vậy, `\r` viết bằng escape **có thể còn tồn tại** trong kết quả cuối cùng.

## 3. Bước 2 — Loại thụt lề phụ trợ và khoảng trắng cuối dòng

### 3.1. Phân biệt thụt lề của mã nguồn và thụt lề của dữ liệu

~~~java
String layout = """
        <root>
          <item>OK</item>
        </root>
        """;
~~~

Giả sử các dòng `<root>`, `</root>` và dấu đóng cùng thụt vào tám khoảng trắng; `<item>` thụt thêm hai khoảng trắng. Java loại bỏ tám khoảng trắng chung, nhưng giữ hai khoảng trắng có ý nghĩa trước `<item>`. Giá trị tương đương là:

~~~java
String expected = "<root>\n  <item>OK</item>\n</root>\n";
~~~

Các dòng không trống và vị trí của dấu đóng (khi nằm trên dòng riêng) quyết định mức thụt lề phụ trợ. Sau khi loại mức chung, **khoảng cách tương đối giữa các dòng vẫn được giữ**.

Nếu cố ý đặt dấu đóng về bên trái so với các dòng nội dung, một phần khoảng trắng đầu dòng có thể được giữ lại trong kết quả. Ngược lại, khi dấu đóng ở ngay cuối dòng nội dung cuối, không có dòng riêng chứa dấu đóng để góp phần xác định lề. Vì vậy, **di chuyển dấu đóng có thể ảnh hưởng cả `\n` cuối và số khoảng trắng đầu dòng**.

### 3.2. Khoảng trắng cuối dòng bị bỏ trước khi xử lý escape

Khoảng trắng ở cuối dòng mã nguồn thường khó nhận biết và dễ bị trình soạn thảo tự động cắt. Do đó, text block bỏ những khoảng trắng này ở bước 2. Nếu muốn có khoảng trắng cuối dòng **trong giá trị chuỗi**, hãy dùng `\s` (một dấu cách) hoặc `\040` (một dấu cách dạng octal) để tạo khoảng trắng sau bước cắt.

~~~java
String trailing = """
        red  \s
        blue\s
        """;
~~~

Sau bước 2, hai dấu cách trước `\s` ở dòng `red` vẫn còn vì chúng nằm **trước ký tự escape**, không nằm tận cuối dòng; `\s` chưa chuyển thành dấu cách. Đến bước 3, mỗi `\s` tạo thêm một khoảng trắng. Kết quả:

- Dòng `red` có **ba** dấu cách cuối: hai dấu cách viết trực tiếp và một dấu cách từ `\s`.
- Dòng `blue` có **một** dấu cách cuối từ `\s`.
- Mỗi dòng vẫn kết thúc bằng `\n`.

Khi dùng cả tab và space để thụt lề, ký tự tab là một ký tự thụt lề nhưng độ rộng hiển thị có thể khác tùy trình soạn thảo. Hãy dùng nhất quán một kiểu thụt lề để tránh kết quả khó đoán. Có thể bật cảnh báo liên quan text block bằng `javac -Xlint:text-blocks`.

## 4. Bước 3 — Diễn giải escape sau cùng

Chỉ **sau** chuẩn hóa dòng và xử lý thụt lề, Java mới diễn giải escape. Những escape hợp lệ có liên quan gồm `\b`, `\f`, `\n`, `\t`, `\r`, `\s`, `\"`, `\'`, `\\`, escape octal như `\040`, và **dấu `\` ngay trước dấu kết thúc dòng**.

| Escape viết trong nội dung text block | Hiệu ứng sau bước 3 |
| --- | --- |
| `\n` | Thêm ký tự LF; có thể thêm xuống dòng ngay trong một dòng của mã nguồn |
| `\r` | Thêm ký tự CR; không bị bước 1 đổi thành LF vì được tạo sau bước 1 |
| `\t` | Thêm ký tự tab; không tham gia tính thụt lề ở bước 2 |
| `\s` | Thêm một dấu cách; giúp giữ dấu cách cuối dòng |
| `\040` | Thêm một dấu cách (octal 040) |
| `\\` | Thêm một dấu gạch chéo ngược `\` |
| `\` ngay trước ký tự kết thúc dòng | **Bỏ** dấu xuống dòng đó, nối nội dung hai dòng |

Ví dụ nối dòng:

~~~java
String joined = """
        Java\
        15
        """;
~~~

Kết quả là `"Java15\n"`: dấu `\` gắn với ký tự xuống dòng ngay sau `Java` khiến ký tự LF tại đó không xuất hiện trong `String`; dấu xuống sau `15` vẫn còn. Đây là **escape nối dòng**, không phải phép nối chuỗi tại runtime.

Ví dụ escape tạo CR sau chuẩn hóa:

~~~java
String explicitCR = """
        A\rB
        """;
~~~

Kết quả là `"A\rB\n"`. Ký tự `\r` ở giữa `A` và `B` tồn tại vì được tạo tại bước 3; chỉ các dấu xuống dòng gốc của tệp nguồn mới được chuẩn hóa tại bước 1.

Ví dụ escape tạo tab ở đầu nội dung:

~~~java
String escapedTab = """
        \tlabel
        """;
~~~

Giá trị là `"\tlabel\n"`: phần khoảng trắng thụt lề của mã Java bị cắt ở bước 2, sau đó `\t` mới trở thành ký tự tab thật. Không được tính tab đó vào mức thụt lề cần loại.

Lưu ý: escape dạng `\u0020` **không phải cách thay thế tương đương `\s` tại bước 3**. Java xử lý *Unicode escape* từ rất sớm, trước khi nhận diện token text block; ký tự được tạo có thể tiếp tục bị loại bởi bước thụt lề. Khi cần một dấu cách được tạo sau cùng, dùng `\s` hoặc `\040`.

## 5. Theo dõi một ví dụ qua đủ ba bước

Xét:

~~~java
String sample = """
        first
          second\s
        """;
~~~

Ở đây hai dòng nội dung có mức thụt lề khác nhau; dòng `second` thụt nhiều hơn `first` hai dấu cách, và ở cuối dòng có chuỗi ký tự escape `\s`.

1. **Chuẩn hóa dòng:** các dấu xuống dòng trở thành LF; trên tệp dùng LF sẵn thì không thấy thay đổi.
2. **Loại thụt lề:** bỏ mức thụt chung; lúc này nội dung có dạng `first\n  second\s\n` (hai dấu cách trước `second` còn lại, `\s` vẫn chưa diễn giải).
3. **Xử lý escape:** `\s` trở thành một dấu cách. Giá trị cuối cùng là `"first\n  second \n"`, có **một dấu cách sau `second` và trước LF**.

Từ ví dụ này có thể suy ra điều quan trọng: nếu đổi thứ tự để diễn giải `\s` *trước* khi bỏ khoảng trắng cuối dòng, dấu cách mới sinh ra có thể bị xóa. Java quy định **escape luôn xử lý sau cùng**, nên dấu cách đó được giữ.

## 6. Chương trình hoàn chỉnh để kiểm chứng bằng Java

Lưu thành **`TextBlockProcessingOrderDemo.java`**, biên dịch với Java 17 trở lên (cơ chế đã chính thức có từ Java 15). Hàm `visible` thay các ký tự khó nhìn bằng dấu hiệu dễ quan sát: `·` cho space, `<LF>`, `<CR>`, `<TAB>` cho ký tự điều khiển.

~~~java
public class TextBlockProcessingOrderDemo {
    public static void main(String[] args) {
        String layout = """
                <root>
                  <item>OK</item>
                </root>
                """;

        String trailing = """
                red  \s
                blue\s
                """;

        String joined = """
                Java\
                15
                """;

        String escapedTab = """
                \tlabel
                """;

        String explicitCR = """
                A\rB
                """;

        String withFinalLF = """
                end
                """;

        String withoutFinalLF = """
                end""";

        System.out.println("layout=" + visible(layout));
        System.out.println("trailing=" + visible(trailing));
        System.out.println("joined=" + visible(joined));
        System.out.println("escapedTab=" + visible(escapedTab));
        System.out.println("explicitCR=" + visible(explicitCR));
        System.out.println("withFinalLF=" + visible(withFinalLF));
        System.out.println("withoutFinalLF=" + visible(withoutFinalLF));
    }

    private static String visible(String s) {
        return s.replace(" ", "·")
                .replace("\t", "<TAB>")
                .replace("\r", "<CR>")
                .replace("\n", "<LF>");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TextBlockProcessingOrderDemo.java
java TextBlockProcessingOrderDemo
~~~

Kết quả chính xác:

~~~text
layout=<root><LF>··<item>OK</item><LF></root><LF>
trailing=red···<LF>blue·<LF>
joined=Java15<LF>
escapedTab=<TAB>label<LF>
explicitCR=A<CR>B<LF>
withFinalLF=end<LF>
withoutFinalLF=end
~~~

Các kết quả trên xác nhận được bằng JDK 24. Nếu biên dịch nguồn có dấu CRLF thay cho LF, giá trị các text block vẫn sử dụng LF trong `String` (trừ những CR được tạo chủ động bằng escape `\r`).

## 7. Các lỗi cần tránh khi làm việc với khoảng trắng

- **Cho rằng xuống dòng ở mã nguồn sẽ luôn giữ nguyên theo hệ điều hành:** text block chuẩn hóa xuống LF. Chỉ chuyển sang `System.lineSeparator()` nếu quy trình ghi dữ liệu thực sự cần dấu kết thúc dòng của hệ điều hành.
- **Nghĩ dấu cách sau cùng viết trực tiếp sẽ được giữ:** bước loại khoảng trắng chạy trước escape. Nếu số dấu cách cuối dòng là dữ liệu quan trọng, dùng `\s`/`\040` và kiểm tra cụ thể.
- **Gọi `stripIndent()` hoặc `translateEscapes()` thêm một lần theo thói quen:** text block đã được trình biên dịch xử lý. Gọi thêm sẽ biến đổi kết quả lần nữa khi dữ liệu phù hợp, khác với ý định ban đầu.
- **Hiểu `\` nối dòng như ký tự `\n`:** ngược lại, nó *loại bỏ* xuống dòng; còn `\n` tạo ra LF ở bước escape.
- **Quên vị trí dấu đóng:** dấu đóng đặt trên dòng riêng thường giữ `\n` cuối, trong khi dấu đóng ngay sau nội dung cuối không có `\n` đó; dấu đóng còn có thể ảnh hưởng mức thụt lề.
- **Trộn tab và space ở đầu các dòng:** lề nhìn bằng mắt có thể khác số ký tự mà thuật toán dùng để xác định khoảng trắng phụ trợ.
- **Nhầm xử lý Unicode escape với escape của text block:** `\u0020` được xử lý trước khi text block đi qua ba bước; nếu mục tiêu là dấu cách cuối dòng, dùng `\s`.

**Tự kiểm tra:** Cho text block sau:

~~~java
String check = """
        left\s
        right\
        now
        """;
~~~

Giá trị là `"left \nrightnow\n"`: `\s` giữ một space sau `left`, còn dấu `\` cuối dòng `right` loại bỏ LF nên `right` nối liền `now`.

## Tài liệu chính thức

- Oracle, *Text Blocks*, Java SE 25: https://docs.oracle.com/en/java/javase/25/language/text-blocks.html
- Java Language Specification, `3.10.6 *Text Blocks*: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6
- OpenJDK, *JEP 378: Text Blocks*: https://openjdk.org/jeps/378