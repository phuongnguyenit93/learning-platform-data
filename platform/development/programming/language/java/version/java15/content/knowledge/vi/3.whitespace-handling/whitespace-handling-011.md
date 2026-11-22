# Kiểm tra độ dài, code point và ký tự vô hình trong `String` (Java 15+)

> **Ngữ cảnh:** Chủ đề **Khoảng trắng** của module **Java 15**. Khi Java xử lý text block, dữ liệu copy/paste, form hoặc JSON, những ký tự không nhìn thấy và các dạng mã hóa Unicode có thể khiến phép so sánh, kiểm tra độ dài và cắt khoảng trắng cho kết quả bất ngờ. Các quy tắc dưới đây vẫn dùng được trong Java hiện đại.

## Mục tiêu

- Phân biệt **UTF-16 code unit**, **Unicode code point** và **grapheme cluster**.
- Dùng đúng `length()`, `codePointCount()`, `codePoints()`, `codePointAt()` và `offsetByCodePoints()`.
- Phát hiện tab, newline, dấu cách không ngắt dòng, ký tự không có độ rộng và dấu tổ hợp.
- Hiểu chính xác `isBlank()`, `strip()`, `Character.isWhitespace()` và `Character.isSpaceChar()`.
- Kiểm tra whitespace của text block Java 15 bằng giá trị `String` thực tế.
- Chọn cách chuẩn hóa hoặc làm sạch dữ liệu có chủ đích.

## 1. `String.length()` đếm cái gì?

`String.length()` trả về **số UTF-16 code units**; mỗi `char` Java là một đơn vị mã 16 bit. Đây không phải số Unicode code points, số byte UTF-8 hay số ký tự người dùng nhìn thấy.

- Các code points thuộc **Basic Multilingual Plane (BMP)** thường chiếm **1 UTF-16 code unit**.
- Các code points bổ sung (lớn hơn `U+FFFF`) chiếm **2 UTF-16 code units** (*surrogate pair*).
- Một ký tự được mắt người nhận ra có thể bao gồm nhiều code points, chẳng hạn một chữ cái với dấu tổ hợp hoặc một emoji ghép bằng zero-width joiner.

| Khái niệm | Cách tính hoặc tiêu chuẩn | Ví dụ `A🙂é` |
| --- | --- | --- |
| UTF-16 code units | `s.length()` | **5** |
| Unicode code points | `s.codePointCount(0, s.length())` | **4** |
| Grapheme clusters | Thuật toán Unicode text segmentation | Thường **3** cụm |

Trong ví dụ trên, chuỗi gồm `A` (`U+0041`), emoji `🙂` (`U+1F642`), `e` (`U+0065`) và dấu acute tổ hợp (`U+0301`). Emoji chiếm hai code units; `e` và dấu acute là hai code points nhưng thường hiển thị thành một cụm.

### 1.1. Những API cần phân biệt

- `s.charAt(index)` lấy **một UTF-16 code unit**. Nó có thể là một nửa surrogate pair.
- `s.codePointAt(index)` lấy code point bắt đầu tại **chỉ số UTF-16** `index`; ghép surrogate pair nếu hợp lệ.
- `s.codePointCount(beginIndex, endIndex)` đếm code points trong khoảng chỉ số **UTF-16**, với `endIndex` không bao gồm.
- `s.codePoints()` tạo `IntStream` duyệt lần lượt theo các code points; khác `s.chars()` vốn duyệt từng UTF-16 code unit.
- `s.offsetByCodePoints(index, n)` dịch từ vị trí UTF-16 `index` đi `n` code points và trả về chỉ số UTF-16 mới.

**Lưu ý về dữ liệu không hợp lệ:** `codePointCount()` coi surrogate đơn lẻ không ghép cặp như một giá trị riêng. Vì thế phép đếm code point **không phải** bộ kiểm tra tính hợp lệ của toàn bộ chuỗi Unicode.

### Ví dụ 1 — Đếm và truy cập code point

**Tệp `UnicodeLengthDemo.java`, chạy với Java 17+:**

~~~java
public class UnicodeLengthDemo {
    public static void main(String[] args) {
        // A + U+1F642 (emoji) + e + U+0301 (combining acute).
        String text = "A" + Character.toString(0x1F642) + "e\u0301";

        System.out.println("length=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
        System.out.printf("charAt(1)=U+%04X%n", (int) text.charAt(1));
        System.out.printf("codePointAt(1)=U+%04X%n", text.codePointAt(1));
        System.out.println("nextIndex="
                + text.offsetByCodePoints(1, 1));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 UnicodeLengthDemo.java
java UnicodeLengthDemo
~~~

**Kết quả chính xác:**

~~~text
length=5
codePoints=4
charAt(1)=U+D83D
codePointAt(1)=U+1F642
nextIndex=3
~~~

`charAt(1)` trả về high surrogate `U+D83D` chứ không phải cả emoji. `codePointAt(1)` trả về `U+1F642`. Đi một code point từ vị trí UTF-16 `1` dẫn tới vị trí `3` vì emoji chiếm hai code units.

**Cẩn thận:** Tham số `n` trong `codePointAt(n)` là chỉ số UTF-16, **không phải** vị trí code point thứ `n`. Để truy cập code point thứ `n`, hãy dùng `offsetByCodePoints(0, n)` trước (và kiểm tra giới hạn).

## 2. “Khoảng trắng” khác “ký tự vô hình”

Một ký tự có thể không nhìn thấy, nhìn giống space thông thường, ảnh hưởng bố cục hoặc ảnh hưởng cách ghép ký tự. Không phải tất cả đều thuộc cùng một nhóm Unicode.

| Unicode | Tên | Ý nghĩa | `isWhitespace` | `isSpaceChar` |
| --- | --- | --- | --- | --- |
| `U+0020` | SPACE | Space thông thường | `true` | `true` |
| `U+0009` | TAB | Tab ngang | `true` | `false` |
| `U+000A` | LF | Xuống dòng | `true` | `false` |
| `U+000D` | CR | Ký tự về đầu dòng | `true` | `false` |
| `U+00A0` | NO-BREAK SPACE | Space không ngắt dòng | `false` | `true` |
| `U+202F` | NARROW NO-BREAK SPACE | Space hẹp không ngắt dòng | `false` | `true` |
| `U+2003` | EM SPACE | Space Unicode | `true` | `true` |
| `U+200B` | ZERO WIDTH SPACE | Vị trí ngắt từ có độ rộng bằng 0 | `false` | `false` |
| `U+200D` | ZERO WIDTH JOINER | Hỗ trợ ghép ký tự/emoji | `false` | `false` |
| `U+0301` | COMBINING ACUTE ACCENT | Dấu tổ hợp trên ký tự trước | `false` | `false` |

Các API có hợp đồng khác nhau:

- `Character.isWhitespace(int)` dùng định nghĩa **Java whitespace**, bao gồm tab, CR, LF và nhiều Unicode spaces, nhưng **loại trừ** một số non-breaking spaces như `U+00A0`, `U+2007` và `U+202F`.
- `Character.isSpaceChar(int)` kiểm tra các nhóm Unicode `SPACE_SEPARATOR`, `LINE_SEPARATOR`, `PARAGRAPH_SEPARATOR`. Nó có thể nhận ra NBSP mà không nhận tab.
- `Character.isISOControl(int)` nhận diện nhiều ký tự điều khiển, nhưng không bao trùm những format characters Unicode như `U+200B`.
- `Character.getType(cp) == Character.FORMAT` nhận diện một số format characters như `U+200B`, `U+200D`, nhưng **không có nghĩa các ký tự đó phải bị xóa**.

### Ví dụ 2 — Quan sát chính xác hai nhóm whitespace

**Tệp `WhitespaceCategoryDemo.java`:**

~~~java
public class WhitespaceCategoryDemo {
    public static void main(String[] args) {
        int[] samples = {0x0020, 0x0009, 0x00A0,
                         0x2003, 0x200B, 0x200D};

        for (int cp : samples) {
            System.out.printf("U+%04X whitespace=%s spaceChar=%s%n",
                cp,
                Character.isWhitespace(cp),
                Character.isSpaceChar(cp));
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 WhitespaceCategoryDemo.java
java WhitespaceCategoryDemo
~~~

**Kết quả chính xác:**

~~~text
U+0020 whitespace=true spaceChar=true
U+0009 whitespace=true spaceChar=false
U+00A0 whitespace=false spaceChar=true
U+2003 whitespace=true spaceChar=true
U+200B whitespace=false spaceChar=false
U+200D whitespace=false spaceChar=false
~~~

Khi validation hoặc làm sạch văn bản, phải chọn nhóm ký tự được phép **theo yêu cầu**, không dùng hai API trên thay thế nhau.

## 3. Phát hiện ký tự vô hình bằng mã Unicode

`System.out.println(s)` không bảo đảm cho thấy NBSP, tab, trailing space, ZWSP hoặc newline cuối. Khi hai chuỗi trông giống nhau nhưng `equals()` là `false`, hãy in **mã U+XXXX của từng code point**.

### Ví dụ 3 — Audit chuỗi có NBSP, ZWSP, TAB và LF

**Tệp `InvisibleCharacterAudit.java`:**

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public class InvisibleCharacterAudit {
    public static void main(String[] args) {
        // A, NBSP, B, ZWSP, C, TAB, D, LF.
        String input = "A\u00A0B\u200BC\tD\n";

        String unicode = input.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));

        System.out.println("length=" + input.length());
        System.out.println("codePoints="
                + input.codePointCount(0, input.length()));
        System.out.println(unicode);
        System.out.println("hasNBSP=" + input.contains("\u00A0"));
        System.out.println("hasZWSP=" + input.contains("\u200B"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InvisibleCharacterAudit.java
java InvisibleCharacterAudit
~~~

**Kết quả chính xác:**

~~~text
length=8
codePoints=8
U+0041 U+00A0 U+0042 U+200B U+0043 U+0009 U+0044 U+000A
hasNBSP=true
hasZWSP=true
~~~

Ở đây mọi code point thuộc BMP nên hai số đếm đều bằng **8**, dù chuỗi chứa nhiều ký tự khó nhìn thấy. Nếu có code point bổ sung như emoji, số UTF-16 code units có thể lớn hơn số code points.

**Quy trình xử lý lỗi dữ liệu:**

1. Giữ giá trị đầu vào gốc trước khi cắt hoặc chuẩn hóa.
2. In `length()`, `codePointCount()` và danh sách `U+XXXX`.
3. Xác định code point gây khác biệt và nó có ý nghĩa gì trong loại dữ liệu đang xử lý.
4. Chỉ chuyển đổi/xóa khi đặc tả dữ liệu cho phép.
5. Kiểm thử lại cả dữ liệu thông thường và dữ liệu có whitespace/Unicode đặc biệt.

Với dữ liệu nhạy cảm, có thể log loại và số lượng code points bất thường thay vì ghi toàn bộ nội dung người dùng.

## 4. `isEmpty()`, `isBlank()` và `strip()` khác nhau thế nào?

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `"".isEmpty()` | `true` | Độ dài bằng 0 |
| `" ".isEmpty()` | `false` | Có một `U+0020` |
| `" ".isBlank()` | `true` | Chỉ có Java whitespace |
| `"\t\n".isBlank()` | `true` | TAB và LF là Java whitespace |
| `"\u00A0".isBlank()` | `false` | NBSP không là Java whitespace |
| `"\u200B".isBlank()` | `false` | ZWSP không là Java whitespace |

- `isEmpty()` chỉ kiểm tra `length() == 0`.
- `isBlank()` trả về `true` nếu rỗng hoặc toàn bộ code points là `Character.isWhitespace`.
- `strip()` bỏ Java whitespace ở **đầu và cuối**, không bỏ giữa chuỗi.
- `stripLeading()` và `stripTrailing()` chỉ xử lý một phía.
- `strip()` **không** loại NBSP `U+00A0` hoặc ZWSP `U+200B` theo mặc định.

### Ví dụ 4 — Một trường hợp `strip()` không xử lý được

**Tệp `WhitespaceCleaningDemo.java`:**

~~~java
public class WhitespaceCleaningDemo {
    public static void main(String[] args) {
        String normal = " \tJava\n";
        String emSpace = "\u2003Java\u2003";
        String noBreak = "\u00A0Java\u00A0";

        System.out.println(normal.strip().equals("Java"));
        System.out.println(emSpace.strip().equals("Java"));
        System.out.println(noBreak.strip().equals("Java"));

        // Chỉ chuyển NBSP nếu hợp đồng dữ liệu cho phép.
        String converted = noBreak.replace('\u00A0', ' ').strip();
        System.out.println(converted.equals("Java"));

        System.out.println("\t\n".isBlank());
        System.out.println("\u00A0".isBlank());
        System.out.println("\u200B".isBlank());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 WhitespaceCleaningDemo.java
java WhitespaceCleaningDemo
~~~

**Kết quả chính xác:**

~~~text
true
true
false
true
true
false
false
~~~

Chuyển `U+00A0` sang `U+0020` bằng `replace()` làm mất tính **không ngắt dòng**. Chỉ thực hiện khi mong muốn này được quy định rõ, ví dụ một trường dữ liệu định danh đơn giản. Đừng xóa mọi ký tự có độ rộng bằng 0 trong nội dung ngôn ngữ tự nhiên vì `U+200D` có thể tham gia ghép emoji/chữ viết.

### 4.1. Cần phân biệt `\s` của Java và regex `\\s`

- Trong literal hoặc text block Java, escape `\s` có nghĩa **một space `U+0020`**.
- Literal `"\\s"` tạo ra regex `\s` khi dùng với `java.util.regex.Pattern`.
- Regex `\s` ở chế độ mặc định không đại diện đầy đủ cho mọi Unicode whitespace. `Pattern.UNICODE_CHARACTER_CLASS` mở rộng lớp ký tự theo Unicode nhưng cũng không đồng nhất hoàn toàn với `Character.isWhitespace`.

Vì vậy, đừng giả định một lệnh regex `replaceAll("\\s", "")` sẽ loại tất cả NBSP, ZWSP và mọi ký tự định dạng. Hãy kiểm tra loại code point thực tế rồi chọn chính sách xử lý.

## 5. Text block Java 15: thụt lề, khoảng trắng cuối dòng và LF

Text block tạo ra `String` bình thường. Giá trị của nó được xử lý bằng cách chuẩn hóa line terminators trong nguồn thành LF (`U+000A`), loại bỏ incidental indentation/trailing whitespace, sau đó diễn giải escape sequences.

- Dấu xuống dòng ngay sau dấu mở `"""` thuộc cú pháp, không tạo thêm LF ở đầu giá trị.
- Khi dấu đóng `"""` nằm **trên dòng riêng**, giá trị thường có **LF cuối**.
- Khi dấu đóng nằm ngay cuối dòng nội dung, giá trị có thể **không có LF cuối**.
- Space cuối dòng thường bị loại như khoảng trắng phụ; escape `\s` giúp giữ một space thực sự.

### Ví dụ 5 — Kiểm tra giá trị và độ dài text block

**Tệp `TextBlockWhitespaceDemo.java`:**

~~~java
public class TextBlockWhitespaceDemo {
    public static void main(String[] args) {
        String block = """
            A\s
            B
            """;

        System.out.println(block.equals("A \nB\n"));
        System.out.println("length=" + block.length());
        System.out.println(block.endsWith("\n"));
        System.out.println(block.equals("A\nB\n"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TextBlockWhitespaceDemo.java
java TextBlockWhitespaceDemo
~~~

**Kết quả chính xác:**

~~~text
true
length=5
true
false
~~~

Giá trị thực tế là `"A \nB\n"`: ký tự `A`, space, LF, `B`, LF — tổng cộng **5 UTF-16 code units**. Nếu bỏ `\s`, space cuối dòng không được bảo toàn như trên.

Để bỏ LF cuối, có thể đặt dấu đóng ngay sau nội dung cuối. Đoạn sau chỉ là **mã minh họa đặt trong một phương thức Java**:

~~~java
String noTrailingLf = """
    A
    B""";
System.out.println(noTrailingLf.equals("A\nB")); // true
~~~

Khi text block được dùng làm SQL, JSON hoặc thông báo nhiều dòng, hãy so sánh chính xác với chuỗi kỳ vọng bằng `equals()` và in mã `U+XXXX` khi cần. Nhìn indentation trong editor không đủ để xác nhận giá trị.

## 6. Dấu tổ hợp và Unicode normalization

Một số chuỗi giống nhau về hình ảnh nhưng khác nội dung:

- `"\u00E9"`: ký tự `é` dựng sẵn, một code point `U+00E9`.
- `"e\u0301"`: `e` (`U+0065`) + combining acute accent (`U+0301`), hai code points.

`String.equals()` **không tự chuẩn hóa Unicode**. Nếu nghiệp vụ cần xem hai dạng này tương đương, có thể dùng `java.text.Normalizer` với dạng NFC (nếu dữ liệu cho phép).

### Ví dụ 6 — So sánh sau khi chuẩn hóa NFC

**Tệp `UnicodeNormalizationDemo.java`:**

~~~java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String decomposed = "e\u0301";
        String composed = "\u00E9";

        System.out.println(decomposed.length());
        System.out.println(composed.length());
        System.out.println(decomposed.equals(composed));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println(normalized.equals(composed));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

**Kết quả chính xác:**

~~~text
2
1
false
true
~~~

**Không chuẩn hóa vô điều kiện:** Định danh kỹ thuật, dữ liệu cần bảo toàn byte, chữ ký hoặc văn bản chuyên biệt có thể yêu cầu lưu chuỗi nguyên bản. NFC cũng không giải quyết việc đếm grapheme clusters; muốn giới hạn số “ký tự người dùng nhìn thấy” cần quy tắc Unicode grapheme segmentation thích hợp.

## 7. Dùng công cụ nào cho đúng nhu cầu?

| Nhu cầu | Công cụ phù hợp | Giới hạn |
| --- | --- | --- |
| Chuỗi thật sự rỗng | `isEmpty()` | NBSP/ZWSP vẫn làm chuỗi không rỗng |
| Chuỗi chỉ chứa Java whitespace | `isBlank()` | Không xem NBSP/ZWSP là blank |
| Bỏ Java whitespace ở hai đầu | `strip()` | Không tự xóa NBSP/ZWSP |
| Số UTF-16 code units | `length()` | Emoji bổ sung thường chiếm 2 |
| Số code points | `codePointCount(0, length())` | Không đo grapheme clusters |
| Duyệt code points | `codePoints()` | Không đồng nghĩa duyệt ký tự hiển thị |
| Lấy code point tại vị trí UTF-16 | `codePointAt(index)` | Chú ý surrogate pair |
| Phân loại Java whitespace | `Character.isWhitespace(cp)` | Không phải mọi ký tự vô hình |
| Phân loại Unicode space characters | `Character.isSpaceChar(cp)` | TAB/LF không thuộc nhóm này |
| Tìm format characters | `Character.getType(cp)` | Không được tự động xóa mọi FORMAT |
| So sánh sau chuẩn hóa Unicode | `Normalizer.normalize(..., Form.NFC)` | Chỉ theo đặc tả nghiệp vụ |
| Đo độ dài UTF-8 theo byte | `s.getBytes(StandardCharsets.UTF_8).length` | Khác `length()` và số code points |
| Đếm cụm ký tự hiển thị | Unicode grapheme segmentation | Cần đặc tả và phiên bản phù hợp |

## 8. Lỗi phổ biến và bài tập

**Lỗi cần tránh:** Dùng `charAt(i)` để xử lý mọi ký tự Unicode; nhầm `length()` với số emoji hoặc ký tự hiển thị; cho rằng `strip()` xóa mọi space; dùng `isBlank()` phát hiện tất cả ký tự vô hình; xóa tùy tiện `U+200B` và `U+200D`; so sánh Unicode dựng sẵn và dạng tổ hợp bằng `equals()` mà không xác định chính sách normalization; quên LF cuối hoặc trailing space trong text block.

**Câu 1.** `String emoji = Character.toString(0x1F642);` có `length()` và `codePointCount(0, length())` bằng bao nhiêu?

Đáp án: **2** và **1**, do surrogate pair.

**Câu 2.** `"\u00A0".isBlank()` và `"\t".isBlank()` trả về gì?

Đáp án: `false` và `true`; NBSP không là Java whitespace, còn TAB thì có.

**Câu 3.** `"\u200B".length() == 0` đúng không?

Đáp án: Sai; ZWSP không có bề rộng hiển thị nhưng vẫn chiếm **1 code point và 1 UTF-16 code unit**.

**Câu 4.** Một text block khác chuỗi thông thường chỉ vì LF cuối có thể làm gì để kiểm tra?

Đáp án: So sánh bằng `equals()` với giá trị kỳ vọng, kiểm tra `endsWith("\n")` và in mã code points.

**Câu 5.** Có nên xóa toàn bộ `U+200D` trong dữ liệu người dùng?

Đáp án: Không; nó có thể tham gia ghép ký tự/emoji và mang ý nghĩa hiển thị.

## Ghi nhớ

`length()` đếm **UTF-16 code units**; `codePointCount()` đếm **Unicode code points**; cả hai không bảo đảm bằng số **grapheme clusters**. `isBlank()`, `strip()`, `isWhitespace()` và `isSpaceChar()` có những định nghĩa khác nhau. Khi gặp lỗi liên quan đến khoảng trắng hoặc ký tự vô hình, hãy **in từng mã `U+XXXX`** trước, sau đó mới quyết định có chuẩn hóa hoặc xóa hay không.

## Tài liệu chính thức

- [Java SE – String API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html)
- [Java SE – Character API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html)
- [Oracle – Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html)
- [Java SE – Normalizer API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Standard Annex #29 – Text Segmentation](https://www.unicode.org/reports/tr29/)
