# Phân biệt code unit, code point và cụm ký tự hiển thị

Trong Java, từ “ký tự” có thể chỉ ba cấp độ khác nhau: **đơn vị mã UTF-16**, **Unicode code point** và **cụm ký tự hiển thị (grapheme cluster)**. Với chữ `A`, cả ba số đếm đều bằng 1. Với emoji, chữ có dấu kết hợp hoặc cờ, chúng có thể khác nhau. Bài này xây dựng bản đồ khái niệm để chọn đúng đơn vị ngay từ đầu; các bài sau sẽ đi sâu vào chỉ số `String`, cặp surrogate, tiếng Việt và thao tác trên code point.

## 1. Ba tầng của cùng một văn bản

| Tầng | Chính xác là gì? | Công cụ tương ứng trong Java | Khi nào cần? |
| --- | --- | --- | --- |
| **UTF-16 code unit** | Một giá trị 16 bit trong dãy mã UTF-16 | `char`, `String.length()`, `charAt()`, chỉ số `substring()` | Giao tiếp với API chuỗi hoặc offset |
| **Unicode code point** | Một giá trị mã từ `U+0000` đến `U+10FFFF` | `int`, `codePointAt()`, `codePoints()`, `codePointCount()` | Phân loại, duyệt hoặc xử lý từng điểm mã |
| **Extended grapheme cluster** | Một hoặc nhiều code point được nhóm theo quy tắc phân đoạn Unicode | Regex `\\X` và `Matcher` | Cắt văn bản theo cụm mà người dùng thường cảm nhận như một ký tự |

Một `char` là **một code unit**, không bảo đảm biểu diễn trọn một code point. Một code point ngoài BMP cần **hai code unit** liên tiếp (surrogate pair). Một grapheme cluster có thể bao gồm **nhiều code point**, dù mỗi code point đã được đọc đúng. Ngược lại, số grapheme cũng không phải số glyph hoặc độ rộng hiển thị tính bằng pixel: font và hệ thống dựng chữ quyết định hình dạng cuối.

Dữ liệu Unicode có các code point dành riêng cho surrogate (`U+D800`–`U+DFFF`), nhưng từng giá trị đó không phải Unicode scalar value. Java vẫn có thể chứa surrogate đứng lẻ trong `String`; do đó phép đếm code point của Java không phải phép xác thực văn bản Unicode well-formed.

## 2. Nhìn qua một số trường hợp

| Dãy văn bản | UTF-16 units | Code points | Extended grapheme clusters | Nguyên nhân |
| --- | ---: | ---: | ---: | --- |
| `A` | 1 | 1 | 1 | Một mã BMP thông thường |
| `😊` (`U+1F60A`) | 2 | 1 | 1 | Một code point ngoài BMP có cặp surrogate |
| `é` (`U+00E9`) | 1 | 1 | 1 | Ký tự dựng sẵn |
| `e\u0301` | 2 | 2 | 1 | Chữ cơ sở và dấu kết hợp |
| `🇻🇳` | 4 | 2 | 1 | Hai regional indicator |
| `👩‍💻` | 5 | 3 | 1 | Hai emoji nối bằng `U+200D` (ZWJ) |

Bảng mô tả những **chuỗi mẫu cụ thể** theo quy tắc extended grapheme cluster; số liệu không phải công thức cho mọi emoji. Emoji mới hoặc quy tắc phân đoạn khác phiên bản có thể cần thử trên JDK thực tế.

Hai chuỗi `"\u00E9"` và `"e\u0301"` có thể trông như cùng chữ “é” nhưng khác dãy code unit. `String.equals()` không tự chuẩn hóa Unicode. Nếu nghiệp vụ cần so sánh theo tương đương chuẩn, cân nhắc `java.text.Normalizer`, ví dụ NFC, với chính sách nhất quán cho đầu vào. Chuẩn hóa không biến mọi grapheme cluster thành một code point.

## 3. Hợp đồng của API Java trước khi chọn cách đếm

- `String.length()` trả **số code unit UTF-16**; các vị trí `charAt(index)` và `substring(begin, end)` cũng tính theo UTF-16.
- `codePointCount(0, s.length())` đếm các code point mà API Java nhận diện khi duyệt dãy UTF-16; surrogate lẻ vẫn được đếm như đơn vị riêng.
- `s.codePoints()` cho luồng `int` theo code point, ghép surrogate pair hợp lệ; `s.chars()` cho luồng các code unit.
- `Pattern.compile("\\X")` khớp từng extended grapheme cluster trong regex Java; `Matcher.start()` và `Matcher.end()` trả lại **offset UTF-16**, có thể dùng làm biên `substring`.
- `s.getBytes(StandardCharsets.UTF_8).length` là số **byte sau khi mã hóa**, không phải bất kỳ một trong ba phép đếm ở trên.

Phân biệt “độ dài” và “vị trí”: `codePointAt(2)` có đối số là **offset UTF-16**, không có nghĩa “code point thứ ba”. Nếu cần chuyển thứ tự code point thành offset UTF-16, dùng `offsetByCodePoints`. Nếu cần cắt theo ký tự hiển thị, ranh giới code point chưa đủ: phải phân đoạn grapheme.

## 4. Chương trình đối chiếu ba đơn vị

Lưu thành `UnicodeLevelsOverview.java` (JDK 17+):

~~~java
import java.util.regex.Pattern;

public class UnicodeLevelsOverview {
    private static final Pattern CLUSTERS = Pattern.compile("\\X");

    private static void show(String label, String text) {
        int units = text.length();
        int points = text.codePointCount(0, units);
        long clusters = CLUSTERS.matcher(text).results().count();
        System.out.printf("%s: units=%d, points=%d, clusters=%d%n",
                label, units, points, clusters);
    }

    public static void main(String[] args) {
        show("A", "A");
        show("smile", "\uD83D\uDE0A");
        show("composed", "\u00E9");
        show("decomposed", "e\u0301");
        show("flag", "\uD83C\uDDFB\uD83C\uDDF3");
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnicodeLevelsOverview.java
java UnicodeLevelsOverview
~~~

Kết quả mong đợi với quy tắc phân đoạn hỗ trợ các chuỗi mẫu:

~~~text
A: units=1, points=1, clusters=1
smile: units=2, points=1, clusters=1
composed: units=1, points=1, clusters=1
decomposed: units=2, points=2, clusters=1
flag: units=4, points=2, clusters=1
~~~

Ở `smile`, khác biệt xảy ra **giữa code unit và code point**. Ở `decomposed`, hai code point được nhóm thành **một grapheme cluster**. Ở `flag`, cả hai cơ chế cùng xuất hiện: hai code point ngoài BMP thành bốn UTF-16 units, nhưng quy tắc phân đoạn nhóm thành một cụm.

## 5. Chọn đơn vị từ yêu cầu, không từ hình dáng chữ

Nếu API yêu cầu offset để gọi `substring`, dùng **UTF-16 offset**. Nếu bài toán cần kiểm tra từng giá trị Unicode, dùng **code point** với lưu ý về surrogate lẻ. Nếu giới hạn trường nhập “tối đa 20 ký tự người dùng cảm nhận”, dùng **grapheme clusters**, kèm quy tắc Unicode/version nhất quán ở client và server. Nếu lưu payload giới hạn 255 byte, phải **mã hóa đúng charset rồi đếm byte**. Độ rộng ô trên màn hình vẫn cần công cụ đo chữ của UI.

Một ứng dụng có thể áp dụng đồng thời số grapheme tối đa và kích thước byte tối đa. Dùng `length()` cho cả hai sẽ sai đối với nhiều văn bản đa ngôn ngữ.

### Tự kiểm tra

Với `String s = "A\uD83D\uDE0Ae\u0301";`, hãy dự đoán ba số đếm. Đáp án: **5 UTF-16 units**, **4 code points**, **3 grapheme clusters** (A, 😊, e + dấu sắc). `s.substring(1, 2)` chỉ lấy high surrogate của emoji và cắt hỏng cặp. `s.substring(1, 3)` lấy nguyên emoji, nhưng một lát cắt theo code point vẫn có thể chia đôi chữ với dấu kết hợp. Việc chọn ranh giới luôn phụ thuộc đơn vị mà yêu cầu thật sự nói đến.

Các bài kế tiếp lần lượt làm rõ chỉ số UTF-16, BMP và surrogate pair, normalization tiếng Việt, dữ liệu lỗi, API `Character`, charset tệp và chính sách thao tác theo ký tự hiển thị.