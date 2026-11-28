# Unicode, code point và giới hạn của char

> **Bối cảnh:** Java 27, chương **Chuỗi và dữ liệu văn bản**. Bài học giải thích các tầng biểu diễn văn bản, cách làm việc với Unicode code point, giới hạn của `char` và các API đang được hỗ trợ. Những ví dụ sử dụng tính năng Java chính thức, không cần preview hay các kỹ thuật xử lý văn bản đã lỗi thời.

## 1. Mục tiêu và vấn đề thực tế

Một ứng dụng Java có thể xử lý tiếng Việt, chữ Hán, ký hiệu toán học, emoji, tên người dùng và dữ liệu đến từ tệp hoặc HTTP. Nếu giả định “một `char` là một ký tự” hoặc “`String.length()` là số chữ người dùng nhìn thấy”, chương trình có thể:

- Cắt đôi một emoji thành hai surrogate không ghép cặp.
- Giới hạn tên theo sai đơn vị và từ chối đầu vào hợp lệ.
- Đếm sai độ dài văn bản có dấu kết hợp hoặc emoji nhiều thành phần.
- So sánh hai chuỗi hiển thị giống nhau nhưng có biểu diễn Unicode khác nhau.
- Mã hóa sai hoặc thay thế dữ liệu âm thầm khi chuyển giữa `String` và `byte[]`.
- Dùng API nhận `char` để phân loại một code point nằm ngoài Basic Multilingual Plane.

Sau bài này, bạn cần trả lời được bốn câu hỏi: giá trị đang là **byte**, **UTF-16 code unit**, **Unicode code point** hay **grapheme cluster**; API đang đếm/chỉ số theo đơn vị nào; lúc nào cần `int` thay cho `char`; và tại đâu cần chuẩn hóa, phân đoạn hoặc kiểm tra dữ liệu.

## 2. Bốn tầng cần phân biệt

Unicode gán các **code point** cho ký tự, ký hiệu và các giá trị điều khiển. Cách mã hóa như UTF-8 hoặc UTF-16 biến dữ liệu đó thành các đơn vị lưu trữ. Chuỗi biểu diễn những gì người dùng nhìn thấy còn có thêm quy tắc ghép cụm.

| Khái niệm | Đơn vị | Ví dụ với 😀 (U+1F600) | API/thao tác Java |
| --- | --- | --- | --- |
| Byte | 8 bit | UTF-8 dùng bốn byte `F0 9F 98 80` | `getBytes(StandardCharsets.UTF_8)` |
| UTF-16 code unit | 16 bit | Hai code unit `D83D DE00` | `char`, `charAt`, `length` |
| Unicode code point | Số nguyên trong miền Unicode | Một giá trị `U+1F600` | `codePointAt`, `codePoints`, `Character` API nhận `int` |
| Grapheme cluster | Cụm văn bản theo ranh giới ký tự hiển thị | 😀 là một cụm | `BreakIterator.getCharacterInstance`, regex `\\X` |

Không được đồng nhất ba phép đếm **UTF-16 code units**, **code points** và **grapheme clusters**. Một code point không nhất thiết là một glyph trên màn hình; một glyph có thể biểu diễn bằng nhiều code point, và cách hiển thị còn phụ thuộc font, shaping engine và ngữ cảnh.

Đặc tả ngôn ngữ Java mô tả các chuỗi văn bản theo code unit UTF-16. Điều đó xác định hợp đồng của `String`/`char`, **không** bắt buộc máy ảo phải dùng một mảng `char[]` cụ thể làm cấu trúc lưu trữ nội bộ.

## 3. Unicode code point, BMP và supplementary plane

Unicode code point nằm trong khoảng từ `U+0000` tới `U+10FFFF`. Ký hiệu `U+XXXX` biểu diễn giá trị hệ thập lục phân của code point.

- **Basic Multilingual Plane (BMP)**: `U+0000` đến `U+FFFF`, còn gọi là plane 0.
- **Supplementary planes**: `U+10000` đến `U+10FFFF`, được dùng cho nhiều emoji, chữ viết cổ, ký hiệu và các hệ chữ khác.
- **Surrogate range**: `U+D800` đến `U+DFFF`, dành cho việc ghép đôi trong UTF-16; chúng **không phải Unicode scalar value độc lập**.

Ví dụ:

| Nội dung | Code point | BMP? | Số code unit UTF-16 |
| --- | --- | --- | --- |
| `A` | U+0041 | Có | 1 |
| `á` (dạng dựng sẵn) | U+00E1 | Có | 1 |
| `漢` | U+6F22 | Có | 1 |
| `😀` | U+1F600 | Không | 2 |
| `𝄞` (G clef) | U+1D11E | Không | 2 |

Một code point có thể **hợp lệ về miền số** nhưng **chưa được Unicode gán ký tự**. `Character.isValidCodePoint` chỉ kiểm tra khoảng `0..0x10FFFF`, không chứng minh rằng code point đã được định nghĩa hoặc là scalar value. `Character.isDefined` kiểm tra thuộc tính đã được gán theo dữ liệu Unicode của JDK.

Trong tài liệu `java.lang.Character` của Java SE 27, dữ liệu ký tự dựa trên **Unicode 17.0**. Các thuộc tính như chữ cái, chữ số và loại ký tự có thể thay đổi khi JDK nâng phiên bản Unicode; không nên hard-code danh sách mã Unicode dựa trên một bản hướng dẫn cũ.

## 4. Kiểu primitive char là gì?

`char` trong Java là kiểu số nguyên **không dấu 16 bit**, có miền giá trị từ `0` đến `65_535` (hex: `0x0000` đến `0xFFFF`). Nó biểu diễn **một UTF-16 code unit**, không nhất thiết một code point hoàn chỉnh, càng không phải một grapheme cluster.

~~~java
char latin = 'A';
char vietnamese = 'á';
char ideograph = '漢';

System.out.println((int) latin);       // 65
System.out.println((int) vietnamese);  // 225
System.out.println((int) ideograph);   // 28450
~~~

Những ví dụ trên thuộc BMP nên mỗi giá trị khớp một code unit. Trái lại:

~~~java
String smile = "😀";
// char invalid = '😀'; // Không hợp lệ: một char literal không chứa supplementary code point
int smileCodePoint = 0x1F600;
~~~

Code point của 😀 vượt `0xFFFF` nên **không thể nằm trong một `char`**. Dùng `int` khi cần biểu diễn một code point bất kỳ:

~~~java
int cp = 0x1F600;
System.out.println(Character.isValidCodePoint(cp)); // true
System.out.println(Character.isSupplementaryCodePoint(cp)); // true
System.out.println(new String(Character.toChars(cp))); // 😀
~~~

### 4.1. Vì sao không dùng char cho mọi thao tác phân loại?

`Character` có những phương thức overload nhận `char` và `int`. Khi cần hỗ trợ supplementary characters, dùng phiên bản **nhận `int`**:

~~~java
int cp = 0x10400; // DESERET CAPITAL LETTER LONG I

System.out.println(Character.isLetter(cp)); // true
System.out.println(Character.charCount(cp)); // 2
~~~

Nếu chỉ truyền một nửa surrogate vào overload `Character.isLetter(char)`, kết quả không phản ánh thuộc tính của code point gốc.

### 4.2. char không phải byte, cũng không phải số chữ hiển thị

Trong Java, `char` có thể tham gia phép toán số học và được nâng kiểu lên `int`:

~~~java
char c = 'A';
int next = c + 1;
System.out.println(next); // 66
~~~

Phép tính này **không** có nghĩa là “ký tự kế tiếp theo bảng chữ cái” trong mọi ngôn ngữ. Chẳng hạn, thứ tự code point không đại diện cho thứ tự từ điển, và phép cộng 1 có thể tạo giá trị không được gán ký tự.

## 5. UTF-16 và surrogate pair

UTF-16 mã hóa code point BMP (trừ surrogate) bằng một code unit 16 bit; code point supplementary cần hai code unit:

1. **High surrogate** từ `U+D800` đến `U+DBFF`.
2. **Low surrogate** từ `U+DC00` đến `U+DFFF`.

Ví dụ 😀 (`U+1F600`) được mã hóa bằng high surrogate `U+D83D` và low surrogate `U+DE00`.

Có thể kiểm tra trực tiếp:

~~~java
String emoji = "😀";

System.out.println(emoji.length()); // 2: UTF-16 code units
System.out.printf("%04X%n", (int) emoji.charAt(0)); // D83D
System.out.printf("%04X%n", (int) emoji.charAt(1)); // DE00

System.out.println(Character.isHighSurrogate(emoji.charAt(0))); // true
System.out.println(Character.isLowSurrogate(emoji.charAt(1)));  // true
System.out.println(Character.isSurrogatePair(
        emoji.charAt(0), emoji.charAt(1))); // true

System.out.printf("U+%X%n",
        Character.toCodePoint(emoji.charAt(0), emoji.charAt(1))); // U+1F600
~~~

`Character.toCodePoint(high, low)` **không tự xác nhận** hai tham số là một surrogate pair đúng; nếu nhận dữ liệu không đáng tin cậy, hãy kiểm tra bằng `Character.isSurrogatePair` trước.

### 5.1. Chuyển giữa code point và UTF-16

Các API hữu ích:

| API | Tác dụng | Lưu ý |
| --- | --- | --- |
| `Character.toChars(int)` | Tạo mảng `char[]` biểu diễn code point | Mảng độ dài 1 hoặc 2; kiểm tra miền giá trị |
| `Character.toCodePoint(char, char)` | Ghép high + low surrogate thành code point | Không tự validate cặp |
| `Character.charCount(int)` | Trả 1 hoặc 2 code unit | Không tự validate đầu vào |
| `Character.isHighSurrogate(char)` | Kiểm tra high surrogate | Dùng khi kiểm tra chuỗi |
| `Character.isLowSurrogate(char)` | Kiểm tra low surrogate | Dùng khi kiểm tra chuỗi |
| `Character.isSupplementaryCodePoint(int)` | Có nằm ngoài BMP và trong miền hỗ trợ? | Trả `true` cho `U+10000..U+10FFFF` |
| `StringBuilder.appendCodePoint(int)` | Nối một code point vào builder | Không phải nối một `char` nguyên thủy |

~~~java
int codePoint = 0x1F600;
String text = new String(Character.toChars(codePoint));

StringBuilder builder = new StringBuilder();
builder.append("Java ");
builder.appendCodePoint(codePoint);

System.out.println(text);               // 😀
System.out.println(builder.toString()); // Java 😀
~~~

**Lưu ý về miền giá trị:** `Character.isValidCodePoint(0xD800)` trả `true` vì giá trị này nằm trong miền số của code point, nhưng `U+D800` là surrogate, **không phải Unicode scalar value**. Nếu hệ thống đòi một scalar value hợp lệ:

~~~java
static boolean isUnicodeScalar(int cp) {
    return Character.isValidCodePoint(cp)
            && (cp < 0xD800 || cp > 0xDFFF);
}
~~~

## 6. String.length(), charAt() và codePointCount()

Với `String`, chỉ số trong các API truyền thống là **chỉ số UTF-16 code unit**. Xét chuỗi chứa chữ thường, emoji và dấu kết hợp:

~~~java
String text = "A😀e\u0301"; // A, mặt cười, e + COMBINING ACUTE ACCENT

System.out.println(text.length()); // 5 UTF-16 code units
System.out.println(text.codePointCount(0, text.length())); // 4 code points
~~~

Giải thích:

- `A` là một code unit và một code point.
- `😀` là **hai** code unit nhưng **một** code point.
- `e` và dấu sắc kết hợp `U+0301` là **hai** code unit và **hai** code point.
- Người đọc thường nhận thấy **ba cụm**: `A`, `😀` và `é`.

| Phép gọi | Kết quả | Đơn vị |
| --- | --- | --- |
| `text.length()` | 5 | UTF-16 code unit |
| `text.codePointCount(0, text.length())` | 4 | Code point |
| Phân đoạn grapheme bằng `BreakIterator` | 3 | Grapheme cluster |
| `text.getBytes(UTF_8).length` | 8 | Byte UTF-8 |

Giá trị UTF-8 bằng 8 byte vì `A` = 1 byte, `😀` = 4 byte, `e` = 1 byte và `U+0301` = 2 byte.

`String.length()` **không** trả số code point, byte hay grapheme cluster. Không thể dự đoán số byte UTF-8 bằng `length() * 2` hay một hệ số cố định.

### 6.1. charAt có thể trả một nửa emoji

~~~java
String text = "A😀Z";

System.out.printf("%04X%n", (int) text.charAt(1)); // D83D
System.out.println(text.codePointAt(1) == 0x1F600); // true
~~~

`charAt(1)` trả high surrogate. `codePointAt(1)` nhận diện hai code unit liên tiếp và trả một code point.

**Quan trọng:** tham số `index` của `codePointAt(index)` vẫn là **chỉ số UTF-16**, không phải “số thứ tự code point”. Gọi `codePointAt(2)` ở ví dụ trên sẽ bắt đầu tại low surrogate và trả giá trị của low surrogate riêng lẻ, không tự quay lại high surrogate đứng trước.

### 6.2. codePointCount không kiểm tra Unicode scalar hoàn chỉnh

`codePointCount(beginIndex, endIndex)` đếm cặp surrogate hợp lệ như một code point, nhưng **unpaired surrogate** cũng được tính là một code point riêng theo hợp đồng API. Do vậy, giá trị đếm không phải bằng chứng dữ liệu đầu vào là văn bản Unicode hợp lệ hoàn toàn.

## 7. Duyệt chuỗi an toàn theo code point

Khi cần phân loại chữ, chữ số hoặc biểu tượng theo Unicode, có hai cách thông dụng.

### 7.1. Vòng lặp với codePointAt và charCount

~~~java
String text = "A😀漢";

for (int offset = 0; offset < text.length();) {
    int cp = text.codePointAt(offset);
    System.out.printf("UTF-16 index=%d, code point=U+%X%n", offset, cp);
    offset += Character.charCount(cp);
}
~~~

Kết quả tương ứng:

~~~text
UTF-16 index=0, code point=U+41
UTF-16 index=1, code point=U+1F600
UTF-16 index=3, code point=U+6F22
~~~

`Character.charCount(cp)` trả 2 với supplementary code point để chỉ số nhảy qua toàn bộ surrogate pair. Đoạn mã duyệt theo code point, không duyệt theo từng `char`. Nếu có unpaired surrogate, vòng lặp vẫn có thể trả giá trị surrogate đó như một đơn vị; việc **xác nhận đầu vào** là trách nhiệm khác.

### 7.2. Stream codePoints()

~~~java
String text = "A😀漢";

text.codePoints()
        .forEach(cp -> System.out.printf("U+%X%n", cp));

long letters = text.codePoints()
        .filter(Character::isLetter)
        .count();
System.out.println(letters); // 2 (A, 漢)
~~~

`String.codePoints()` tạo `IntStream`. Nó xử lý surrogate pair thành một code point, nhưng các surrogate không ghép cặp vẫn đi qua stream dưới dạng số nguyên mang giá trị của code unit đó. Đừng giả định mọi phần tử trong stream đều là scalar value đã được Unicode gán.

Nếu chỉ cần ký tự ở vị trí hiện tại, `String.codePointBefore(index)` cũng hữu ích khi duyệt ngược; tham số của nó là chỉ số **sau** code point cần lấy, tính theo code unit.

## 8. Lấy substring mà không cắt đôi surrogate pair

Thao tác `substring(begin, end)` nhận offset theo code unit. Điều này có thể gây hỏng chuỗi nếu cắt giữa hai code unit của một supplementary character:

~~~java
String text = "😀Z";

String broken = text.substring(0, 1); // Chỉ high surrogate
String correct = text.substring(0, text.offsetByCodePoints(0, 1));

System.out.println(Character.isHighSurrogate(broken.charAt(0))); // true
System.out.println(correct); // 😀
~~~

Dùng `offsetByCodePoints` khi yêu cầu là “lấy N code point đầu tiên”:

~~~java
static String firstCodePoints(String text, int limit) {
    java.util.Objects.requireNonNull(text, "text");

    if (limit < 0) {
        throw new IllegalArgumentException("limit must be non-negative");
    }
    int count = text.codePointCount(0, text.length());
    int end = text.offsetByCodePoints(0, Math.min(limit, count));

    return text.substring(0, end);
}
~~~

Phương thức trên tránh cắt đôi surrogate pair **hợp lệ**, nhưng **vẫn có thể** chia một grapheme cluster gồm nhiều code point, như `e` kèm dấu kết hợp hoặc emoji ghép bằng zero-width joiner. Nếu yêu cầu là “N ký tự hiển thị”, phải sử dụng thuật toán phân đoạn grapheme, không chỉ `codePointCount`.

### 8.1. Mapping giữa code point index và UTF-16 index

Giả sử có `"A😀Z"`:

| Code point index | Ký tự Unicode | UTF-16 start index | Độ dài code unit |
| ---: | --- | ---: | ---: |
| 0 | A | 0 | 1 |
| 1 | 😀 | 1 | 2 |
| 2 | Z | 3 | 1 |

Để tìm vị trí bắt đầu của code point số `n` (0-based), dùng `text.offsetByCodePoints(0, n)`, sau khi đã kiểm tra `n` nằm trong miền hợp lệ. Đừng trực tiếp đưa `n` vào `charAt` hoặc `substring`.

## 9. Grapheme cluster: ký tự người dùng nhìn thấy

Một **extended grapheme cluster** là một nhóm code point được phân đoạn theo Unicode Standard Annex #29, gần với đơn vị người dùng coi là một ký tự khi di chuyển con trỏ hoặc xóa một ký tự. Nó không phải một code point.

Các ví dụ:

- `e` + `U+0301` (dấu sắc kết hợp) là hai code point nhưng thường một grapheme cluster.
- Emoji có màu da có thể gồm base emoji và modifier.
- Quốc kỳ như 🇻🇳 thường dùng hai regional indicator code point nhưng là một grapheme cluster.
- Chuỗi emoji gia đình có thể chứa nhiều code point được nối bởi `U+200D` (zero-width joiner).

Ngay cả grapheme cluster cũng không bảo đảm đúng **một glyph** ở mọi font và nền tảng. Nó là quy tắc phân đoạn văn bản, không phải phép đo chiều rộng pixel.

### 9.1. Dùng BreakIterator cho ranh giới ký tự

Java 27 có `java.text.BreakIterator`. Tài liệu API ghi rõ cách phân đoạn character boundary mặc định tuân theo **Unicode Extended Grapheme Cluster**:

~~~java
import java.text.BreakIterator;
import java.util.Locale;

public class GraphemeDemo {
    public static void main(String[] args) {
        String text = "A😀e\u0301";
        BreakIterator boundary =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        boundary.setText(text);

        int clusters = 0;
        for (int start = boundary.first(),
                 end = boundary.next();
             end != BreakIterator.DONE;
             start = end, end = boundary.next()) {

            System.out.println(text.substring(start, end));
            clusters++;
        }

        System.out.println("Clusters: " + clusters); // 3
    }
}
~~~

Các ranh giới mà `BreakIterator` trả về vẫn là **UTF-16 offsets**, vì vậy có thể truyền chúng trực tiếp cho `String.substring`. Khi làm ứng dụng soạn thảo văn bản, kiểm thử thêm emoji phức tạp, ký hiệu kết hợp và các ngôn ngữ mục tiêu; hành vi phân đoạn có thể chịu ảnh hưởng của phiên bản dữ liệu Unicode.

### 9.2. Regex \X và ranh giới grapheme

Java regex hỗ trợ `\\X` để so khớp một extended grapheme cluster. Trong Java string literal, cần escape dấu backslash:

~~~java
import java.util.regex.Pattern;

String text = "A😀e\u0301";
long count = Pattern.compile("\\X")
        .matcher(text)
        .results()
        .count();

System.out.println(count); // 3
~~~

Đây là một giải pháp khi đã dùng regular expressions; để điều hướng văn bản theo ranh giới cụm, `BreakIterator` thường thể hiện ý định rõ hơn.

### 9.3. Cắt theo grapheme cluster

~~~java
static String firstGraphemes(String text, int limit) {
    java.util.Objects.requireNonNull(text, "text");
    if (limit < 0) {
        throw new IllegalArgumentException("limit must be non-negative");
    }

    var boundary = java.text.BreakIterator
            .getCharacterInstance(java.util.Locale.ROOT);
    boundary.setText(text);
    int end = boundary.first();

    for (int i = 0; i < limit; i++) {
        int next = boundary.next();
        if (next == java.text.BreakIterator.DONE) {
            break;
        }
        end = next;
    }
    return text.substring(0, end);
}
~~~

Với `limit = 0`, kết quả là chuỗi rỗng; nếu yêu cầu lớn hơn số cụm thực tế, kết quả là cả chuỗi. Hãy chọn đơn vị giới hạn ngay trong hợp đồng API: code units, code points, grapheme clusters, hoặc số byte mã hóa.

## 10. Surrogate không ghép cặp và đầu vào lỗi

`String` trong Java có thể chứa một high hoặc low surrogate đơn lẻ. Đây là một chuỗi code unit hợp lệ về mặt kiểu `String`, nhưng không phải một chuỗi **Unicode scalar value** hoàn chỉnh.

~~~java
String malformed = "\uD83D"; // Chỉ high surrogate, thiếu low surrogate

System.out.println(malformed.length()); // 1
System.out.println(malformed.codePointCount(0, 1)); // 1
System.out.println(Character.isHighSurrogate(malformed.charAt(0))); // true
~~~

Các API code-point như `codePointAt` không nhất thiết báo lỗi khi gặp surrogate đứng một mình. Nếu dữ liệu cần được ghi thành UTF-8 chuẩn, trao đổi qua JSON, lưu trữ hoặc kiểm tra bảo mật, nên có quy định rõ cách xử lý đầu vào malformed: **từ chối**, **thay thế** có kiểm soát, hoặc **ghi nhận lỗi**; tránh âm thầm sửa mà không thông báo khi tính toàn vẹn quan trọng.

### 10.1. Kiểm tra toàn bộ surrogate pair

~~~java
static boolean hasUnpairedSurrogate(String text) {
    java.util.Objects.requireNonNull(text, "text");

    for (int i = 0; i < text.length(); i++) {
        char unit = text.charAt(i);

        if (Character.isHighSurrogate(unit)) {
            if (i + 1 == text.length()
                    || !Character.isLowSurrogate(text.charAt(i + 1))) {
                return true;
            }
            i++; // Bỏ qua low surrogate của cặp hợp lệ
        } else if (Character.isLowSurrogate(unit)) {
            return true;
        }
    }
    return false;
}
~~~

Trả `true` nếu tìm thấy surrogate không ghép cặp. Kiểm tra này chỉ xác nhận chuỗi UTF-16 **đúng cấu trúc surrogate**; nó không kiểm tra văn bản có ký tự cấm theo nghiệp vụ, code point chưa được gán hoặc dữ liệu gây nhầm lẫn thị giác.

## 11. Unicode normalization: hai chuỗi nhìn giống nhau có thể khác nhau

Unicode có thể biểu diễn cùng một văn bản bằng những dãy code point khác nhau. Ví dụ chữ `é` có thể được biểu diễn dạng dựng sẵn `U+00E9` hoặc dạng `e` + `U+0301`.

~~~java
String composed = "\u00E9";   // U+00E9
String decomposed = "e\u0301"; // U+0065 U+0301

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.length()); // 1
System.out.println(decomposed.length()); // 2
~~~

`String.equals` so sánh nội dung chuỗi code unit; nó **không** tự chuẩn hóa Unicode.

Java cung cấp `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

String left = "\u00E9";
String right = "e\u0301";

String leftNfc = Normalizer.normalize(left, Normalizer.Form.NFC);
String rightNfc = Normalizer.normalize(right, Normalizer.Form.NFC);

System.out.println(leftNfc.equals(rightNfc)); // true
~~~

Bốn dạng chuẩn hóa có mục đích khác nhau:

| Dạng | Ý nghĩa | Khi cân nhắc |
| --- | --- | --- |
| `NFC` | Canonical decomposition rồi composition | Lưu và trao đổi văn bản có biểu diễn nhất quán |
| `NFD` | Canonical decomposition | Phân tích chuỗi base và combining marks |
| `NFKC` | Compatibility decomposition rồi composition | Chỉ khi đặc tả nghiệp vụ cho phép gộp các dạng tương thích |
| `NFKD` | Compatibility decomposition | Xử lý cần phân tích tương thích; cẩn trọng mất khác biệt biểu diễn |

Đừng áp dụng `NFKC`/`NFKD` tùy tiện lên định danh, mật khẩu, mã số, văn bản pháp lý hoặc dữ liệu cần giữ nguyên vì chúng có thể gộp những ký tự có ý nghĩa phân biệt. Chuẩn hóa không tự giải quyết mọi trường hợp khác biệt chữ hoa/thường, phân loại chữ, collation hoặc Unicode confusables.

### 11.1. Unicode normalization không phải so sánh theo ngôn ngữ

`equalsIgnoreCase` không phải một giải pháp hoàn chỉnh cho mọi quy tắc Unicode case folding. Một số biến đổi chữ có thể liên quan nhiều code point và phụ thuộc ngôn ngữ. Khi sắp xếp hoặc so khớp tên người dùng theo ngôn ngữ tự nhiên, cân nhắc `Collator` theo locale:

~~~java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
int order = collator.compare("Anh", "Ánh");
~~~

Mức độ phân biệt dấu và chữ hoa/thường phải do ứng dụng quyết định. Không dùng so sánh ngôn ngữ tự nhiên làm cơ chế xác thực định danh hoặc bảo mật nếu giao thức yêu cầu so sánh byte/chuỗi chính xác.

## 12. UTF-8, UTF-16 và chuyển đổi byte

**Unicode** là hệ mã điểm ký tự; **UTF-8** và **UTF-16** là cách mã hóa dữ liệu đó. Trong Java:

- `char` và các chỉ số `String` quan sát theo UTF-16 code units.
- `byte[]` là dữ liệu byte; nó không tự mang thông tin charset.
- `StandardCharsets.UTF_8` biểu diễn charset dùng rộng rãi khi lưu file, giao tiếp HTTP và trao đổi dữ liệu.

UTF-8 dùng từ 1 đến 4 byte cho một Unicode scalar value. UTF-16 dùng 1 hoặc 2 code unit, mỗi code unit 16 bit trong dạng encoding. Chúng biểu diễn cùng nội dung Unicode nhưng khác chuỗi byte vật lý.

~~~java
import java.nio.charset.StandardCharsets;

String text = "A😀";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

System.out.println(text.length()); // 3 UTF-16 code units
System.out.println(text.codePointCount(0, text.length())); // 2
System.out.println(utf8.length); // 5 UTF-8 bytes

String decoded = new String(utf8, StandardCharsets.UTF_8);
System.out.println(decoded.equals(text)); // true
~~~

Độ dài byte có thể còn thay đổi theo charset, byte order mark hoặc định dạng đóng gói. Khi API quy định giới hạn 255 **byte**, tuyệt đối không kiểm tra bằng `String.length()` hoặc `codePointCount`.

### 12.1. Ghi và đọc tệp với charset rõ ràng

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("notes.txt");

Files.writeString(path, "Xin chào 😀", StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
~~~

UTF-8 là charset mặc định chuẩn của các API thông dụng từ JDK 18 theo JEP 400, nhưng **chỉ định charset tường minh** vẫn là lựa chọn tốt khi xử lý giao thức, tệp trao đổi và dữ liệu có hợp đồng encoding cụ thể. Nó tránh giả định ngầm ở biên hệ thống và giúp code rõ ý định.

### 12.2. Phát hiện byte UTF-8 lỗi thay vì âm thầm thay thế

Khi đọc byte từ nguồn không tin cậy, chọn chính sách lỗi rõ ràng. Nếu cần **từ chối** dữ liệu UTF-8 malformed:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

byte[] input = {(byte) 0xC3, (byte) 0x28};

try {
    String decoded = StandardCharsets.UTF_8
            .newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(input))
            .toString();

    System.out.println(decoded);
} catch (CharacterCodingException ex) {
    System.out.println("Invalid UTF-8 input");
}
~~~

Ba chính sách thường gặp trong `CodingErrorAction` là `REPORT`, `REPLACE` và `IGNORE`. Với dữ liệu cần giữ nguyên, `REPORT` là lựa chọn an toàn hơn vì không làm mất lỗi gốc. Nếu muốn thay thế ký tự lỗi, cần ghi rõ hành vi đó trong hợp đồng API. Cần phân biệt **lỗi mã hóa byte** với **unpaired surrogate đã tồn tại trong một String**.

## 13. Unicode escape trong mã nguồn Java

Java hỗ trợ Unicode escapes ở mức **phân tích mã nguồn**, ví dụ `\\u0041` tương ứng `A`. Đây không phải một API runtime để mã hóa Unicode.

~~~java
char latinA = '\u0041';
String smile = "\uD83D\uDE00"; // Hai UTF-16 code units -> 😀
~~~

Mỗi escape dạng `\\uXXXX` chỉ biểu diễn một **code unit 16 bit**. Supplementary character cần hai code units hoặc có thể được viết trực tiếp trong string literal khi tệp nguồn và compiler dùng encoding phù hợp.

**Bẫy quan trọng:** Unicode escapes được Java xử lý rất sớm, **trước cả bước nhận diện comment và string literal**. Nếu trong mã nguồn chứa chuỗi ký tự backslash-u-0-0-0-a như một Unicode escape đủ điều kiện, compiler sẽ biến nó thành xuống dòng thật, có thể phá vỡ cú pháp ngay cả khi nó trông như nằm trong comment hay chuỗi. Để tạo newline bên trong Java string literal, dùng escape thông thường `\\n`:

~~~java
String newline = "\n";
System.out.println("Dòng 1" + newline + "Dòng 2");
~~~

Đừng xem việc hiển thị đúng chữ trong IDE là đủ: khi dùng literal Unicode trực tiếp trong `.java`, hãy bảo đảm encoding source được nhận nhất quán (ví dụ cấu hình build hoặc `javac -encoding UTF-8`).

## 14. Những API Unicode hữu ích của Java 27

| Nhu cầu | API | Cần nhớ |
| --- | --- | --- |
| Đọc code unit tại vị trí | `String.charAt(int)` | Có thể chỉ là nửa surrogate pair |
| Đọc code point tại offset UTF-16 | `String.codePointAt(int)` | Chỉ số đầu vào vẫn là UTF-16 offset |
| Đọc code point trước offset | `String.codePointBefore(int)` | Offset là vị trí sau ký tự |
| Đếm code point trong đoạn | `String.codePointCount(int, int)` | Không phải đếm grapheme |
| Chuyển N code point thành offset UTF-16 | `String.offsetByCodePoints(int, int)` | Kiểm tra miền chỉ số |
| Duyệt code point | `String.codePoints()` | Trả `IntStream` |
| Đọc thuộc tính code point | `Character.isLetter(int)`, `isDigit(int)`, `getType(int)` | Ưu tiên overload `int` cho toàn Unicode |
| Đổi code point thành UTF-16 | `Character.toChars(int)` | Không suy ra số grapheme |
| Dò ranh giới grapheme | `BreakIterator.getCharacterInstance`, regex `\\X` | Trả/so khớp cụm hiển thị |
| Chuẩn hóa Unicode | `Normalizer.normalize` | Cần chọn đúng NFC/NFD/NFKC/NFKD |
| Ghi/đọc UTF-8 | `StandardCharsets.UTF_8`, `Files.readString`/`writeString` | Byte length khác char length |
| Lỗi giải mã byte | `CharsetDecoder`, `CodingErrorAction` | Chọn chính sách lỗi có chủ đích |

### 14.1. isDefined và isLetter không giống nhau

~~~java
int cp = 'A';

System.out.println(Character.isValidCodePoint(cp)); // true
System.out.println(Character.isDefined(cp));        // true
System.out.println(Character.isLetter(cp));         // true
System.out.println(Character.isDigit(cp));          // false
~~~

`isValidCodePoint` xác nhận code point nằm trong miền số; `isDefined` tra dữ liệu Unicode của JDK; `isLetter`/`isDigit` xét loại ký tự. Không API nào trong số đó một mình xác định “đây có phải ký tự tên người hợp lệ” cho mọi ngôn ngữ. Hãy tạo bộ quy tắc validation theo nghiệp vụ.

## 15. Ví dụ ứng dụng: giới hạn tên người dùng đúng đơn vị

Giả sử hệ thống yêu cầu một tên có tối đa **20 grapheme clusters**, không chứa surrogate lỗi và được lưu ở NFC. Quy trình hợp lý:

1. Kiểm tra `null` và cấu trúc surrogate.
2. Chuẩn hóa thành NFC nếu hợp đồng lưu trữ cho phép.
3. Phân đoạn grapheme và kiểm tra số cụm.
4. Áp dụng quy tắc riêng cho ký tự được phép, độ dài byte storage và validation khác.

~~~java
import java.text.BreakIterator;
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

public final class DisplayNames {
    private DisplayNames() {}

    public static String prepare(String raw) {
        Objects.requireNonNull(raw, "raw");
        if (hasUnpairedSurrogate(raw)) {
            throw new IllegalArgumentException("Malformed UTF-16");
        }

        String normalized =
                Normalizer.normalize(raw, Normalizer.Form.NFC);

        BreakIterator boundary =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        boundary.setText(normalized);

        int clusters = 0;
        for (int end = boundary.first();
             (end = boundary.next()) != BreakIterator.DONE;) {
            clusters++;
            if (clusters > 20) {
                throw new IllegalArgumentException(
                        "Display name exceeds 20 graphemes");
            }
        }

        if (normalized.isBlank()) {
            throw new IllegalArgumentException("Blank display name");
        }
        return normalized;
    }

    private static boolean hasUnpairedSurrogate(String text) {
        for (int i = 0; i < text.length(); i++) {
            char unit = text.charAt(i);
            if (Character.isHighSurrogate(unit)) {
                if (i + 1 >= text.length()
                        || !Character.isLowSurrogate(text.charAt(i + 1))) {
                    return true;
                }
                i++;
            } else if (Character.isLowSurrogate(unit)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Ví dụ trên minh họa **một** hợp đồng cụ thể. Nếu hệ thống có quy tắc cấm ký tự điều khiển, bắt buộc loại bỏ ký tự vô hình, giới hạn byte UTF-8 hoặc yêu cầu không cho phép emoji, phải bổ sung bước kiểm tra riêng. Đếm grapheme không tương đương validation bảo mật. Ngược lại, chỉ giới hạn 20 UTF-16 code units có thể bất công với người dùng có emoji hoặc chữ viết cần nhiều code units.

## 16. Lỗi thường gặp và cách sửa

| Sai lầm | Tác động | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `String.length()` để đếm “ký tự” người dùng | Sai với emoji và combining marks | Chọn `codePointCount` hoặc grapheme segmentation đúng nhu cầu |
| Dùng `charAt` để lấy emoji | Có thể lấy một surrogate đơn lẻ | `codePointAt` và xử lý offset UTF-16 |
| Tăng index `i++` khi duyệt code point | Chạm vào low surrogate | `i += Character.charCount(cp)` |
| Gọi `codePointAt(n)` với n là code point index | Lấy sai vị trí | Chuyển qua `offsetByCodePoints` |
| Cắt chuỗi bằng `substring(0, n)` với n là code point count | Cắt đôi surrogate pair | Dùng `offsetByCodePoints` |
| Giới hạn code point và cho rằng giữ nguyên ký tự hiển thị | Cắt dấu kết hợp, emoji ghép | Dùng `BreakIterator` hoặc regex `\\X` |
| Xem `char` là bất kỳ code point nào | Không chứa được code point > U+FFFF | Dùng `int` và API `Character` nhận `int` |
| Xem `isValidCodePoint` là kiểm tra scalar | Surrogate nằm trong miền hợp lệ nhưng không là scalar | Loại trừ `U+D800..U+DFFF` |
| Mặc định `codePoints()` lọc surrogate không ghép cặp | Có thể xử lý dữ liệu UTF-16 malformed mà không biết | Validate surrogate pair trước |
| So sánh bằng `equals` mà không xét normalization | Hai chuỗi nhìn giống nhau vẫn khác | Chuẩn hóa NFC theo hợp đồng |
| Dùng `NFKC` cho mọi dữ liệu | Có thể mất khác biệt quan trọng | Chỉ dùng khi nghiệp vụ chấp nhận compatibility mapping |
| Đo dung lượng UTF-8 bằng `length()` | Giới hạn byte bị tính sai | `getBytes(UTF_8).length` hoặc encoder phù hợp |
| Giải mã byte không chỉ định charset/chính sách lỗi | Mojibake hoặc thay thế dữ liệu không phát hiện | `StandardCharsets.UTF_8` và `CharsetDecoder` khi cần strict |
| Tin rằng Unicode escape được xử lý sau comment/string literal | Mã nguồn có thể hỏng trước tokenization | Nắm rõ JLS §3.3; dùng `\\n` cho newline runtime |

## 17. Checklist khi thiết kế API văn bản

- [ ] Tên trường và tài liệu ghi rõ độ dài theo **byte**, **UTF-16 code unit**, **code point** hay **grapheme cluster**.
- [ ] Không dùng `char` để đại diện mọi ký tự Unicode.
- [ ] Dùng API `Character` nhận `int` nếu cần hỗ trợ supplementary code points.
- [ ] Đã kiểm tra cách xử lý surrogate pair và unpaired surrogate.
- [ ] Không cắt chuỗi giữa hai code unit của một surrogate pair.
- [ ] Nếu hiển thị/di chuyển con trỏ, đã xem xét ranh giới grapheme.
- [ ] Nếu so sánh văn bản, đã quyết định có cần NFC/NFD và quy tắc locale hay không.
- [ ] Không mặc định một glyph hiển thị bằng một code point.
- [ ] Khi mã hóa/giải mã, đã chỉ định charset và chính sách lỗi phù hợp.
- [ ] Giới hạn số byte lưu trữ được kiểm tra bằng encoding thực tế.
- [ ] Validation không chỉ dựa vào `isLetter`, `isDefined` hay grapheme count.
- [ ] Test có ASCII, tiếng Việt dựng sẵn/tổ hợp dấu, CJK, emoji supplementary, emoji ghép và surrogate lỗi.
- [ ] Khi nâng JDK, đã xét phiên bản Unicode trong `Character` và các thuật toán text boundary.
- [ ] Không đưa các giả định về cấu trúc lưu trữ nội bộ của `String` thành hợp đồng API.

## 18. Tài liệu chính thức

- [JLS Java SE 27 §3.1 — Unicode](https://docs.oracle.com/javase/specs/jls/se27/html/jls-3.html#jls-3.1) — code point, UTF-16 code unit và supplementary characters.
- [JLS Java SE 27 §3.3 — Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se27/html/jls-3.html#jls-3.3) — Unicode escapes được xử lý trước bước tokenization.
- [JLS Java SE 27 §3.10.4 — Character Literals](https://docs.oracle.com/javase/specs/jls/se27/html/jls-3.html#jls-3.10.4) — giới hạn của `char` literal.
- [Java SE 27 API — Character](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html) — mã code point, surrogate, thuộc tính Unicode và phiên bản Unicode hỗ trợ.
- [Java SE 27 API — String](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html) — `length`, `charAt`, `codePointAt`, `codePoints`, `offsetByCodePoints`.
- [Java SE 27 API — BreakIterator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/BreakIterator.html) — ranh giới văn bản và extended grapheme clusters.
- [Java SE 27 API — Pattern](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/Pattern.html) — regex `\\X`, Unicode grapheme matcher.
- [Java SE 27 API — Normalizer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Normalizer.html) — NFC, NFD, NFKC và NFKD.
- [Java SE 27 API — StandardCharsets](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html) — UTF-8/UTF-16 và các charset chuẩn.
- [Java SE 27 API — CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html) — xử lý input malformed khi decode.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400) — charset mặc định chuẩn hóa từ JDK 18; không thay thế hợp đồng encoding tường minh.

**Kết luận:** `char` là một code unit UTF-16, `int` mới đủ để mang code point bất kỳ, và một ký tự người dùng nhìn thấy có thể chứa nhiều code point. Khi thiết kế thao tác văn bản trên Java 27, luôn chọn đúng đơn vị, đúng API và đúng chính sách xác thực/chuẩn hóa thay vì dựa vào `String.length()` cho mọi tình huống.
