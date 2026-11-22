# Surrogate pair và ký tự ngoài BMP trong Java

## 1. Vì sao một “ký tự” đôi khi chiếm hai `char`?

Khi làm localization, ứng dụng Java phải xử lý tiếng Việt, tiếng Nhật, tiếng Ả Rập, biểu tượng toán học, emoji và nhiều hệ chữ khác. Một lỗi phổ biến là cho rằng **mỗi ký tự Unicode luôn tương đương một `char` trong Java**. Điều này không đúng.

Java `String` dùng biểu diễn **UTF-16**. Với một Unicode code point thuộc vùng thường gọi là **BMP** (Basic Multilingual Plane), nó có thể được biểu diễn bằng **một UTF-16 code unit**. Nhưng nhiều code point nằm **ngoài BMP** cần **hai code unit**, gọi là **surrogate pair**.

Ví dụ:

- `A` là U+0041: một UTF-16 code unit.
- `中` là U+4E2D: một UTF-16 code unit.
- `😀` là U+1F600: **hai** UTF-16 code unit.
- `𐐷` là U+10437: **hai** UTF-16 code unit.

Vì thế:

```java
String text = "A\uD83D\uDE00\u4E2D"; // A😀中
System.out.println(text.length()); // 4
```

Có **ba Unicode code point** nhưng `String.length()` trả **4** vì trả số **UTF-16 code units**, không phải số ký tự nhìn thấy trên màn hình.

Bài này đi từ cấu trúc Unicode, cách UTF-16 dùng surrogate pair, API Java 17 để xử lý code point, rủi ro khi cắt/duyệt chuỗi, chuyển sang UTF-8, kiểm tra surrogate lỗi và sự khác biệt giữa code point với **grapheme cluster** (ký tự mà người dùng cảm nhận).

## 2. Từ vựng quan trọng: code point, code unit, BMP và grapheme

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Unicode code point** | Vị trí có giá trị số từ U+0000 đến U+10FFFF trong không gian mã Unicode | `U+1F600` |
| **Unicode scalar value** | Code point **không nằm** trong khoảng surrogate U+D800–U+DFFF | `U+0041`, `U+1F600` |
| **BMP** | Plane 0, từ U+0000 đến U+FFFF | `A`, `中`, `é` |
| **Supplementary planes** | Các plane 1–16, từ U+10000 đến U+10FFFF | `😀`, `𐐷` |
| **UTF-16 code unit** | Đơn vị 16-bit của biểu diễn UTF-16 | Java `char` |
| **Surrogate pair** | Cặp high surrogate + low surrogate cùng biểu diễn một supplementary code point | `\uD83D\uDE00` = U+1F600 |
| **Grapheme cluster** | Cụm code point thường được người dùng cảm nhận như một ký tự | `e` + dấu kết hợp `◌́`; emoji ghép |
| **UTF-8 code unit** | Một byte trong chuỗi mã UTF-8 | Emoji U+1F600 mã thành 4 byte |

**Phân biệt “code point” với “scalar value”:** Unicode có các vị trí surrogate U+D800–U+DFFF nhưng chúng không hợp lệ để dùng độc lập như ký tự văn bản. Vì thế **không phải mọi số trong khoảng code point đều là scalar value**. Phương thức `Character.isValidCodePoint(int)` chỉ kiểm tra miền giá trị U+0000–U+10FFFF, **không tự loại trừ surrogate code point**; muốn kiểm tra scalar value còn phải loại U+D800–U+DFFF.

Một điều nữa: ngay cả “một code point” cũng chưa chắc tương đương “một chữ” người dùng cảm nhận. Ví dụ `e\u0301` gồm chữ `e` và dấu sắc kết hợp U+0301, là **hai code point** nhưng thường hiển thị như một chữ `é`. Một emoji gia đình có thể gồm nhiều code point nối nhau bằng zero width joiner (ZWJ) nhưng hiển thị thành một biểu tượng.

Trong phần lớn xử lý chuỗi Unicode, ta cần trả lời rõ đang đếm **UTF-16 units**, **code points**, hay **grapheme clusters**.

## 3. BMP và ký tự ngoài BMP

Unicode chia không gian mã thành 17 plane (plane 0 đến 16), mỗi plane có tối đa 65.536 vị trí mã. BMP là plane 0, từ U+0000 đến U+FFFF. Các plane bổ sung nằm từ U+10000 đến U+10FFFF.

Ví dụ:

| Ký tự | Code point | Vùng | Số UTF-16 code units |
| --- | --- | --- | ---: |
| `A` | U+0041 | BMP | 1 |
| `Đ` | U+0110 | BMP | 1 |
| `中` | U+4E2D | BMP | 1 |
| `€` | U+20AC | BMP | 1 |
| `😀` | U+1F600 | Ngoài BMP | 2 |
| `🚀` | U+1F680 | Ngoài BMP | 2 |
| `𐐷` | U+10437 | Ngoài BMP | 2 |

**Không nhầm BMP với ASCII:** ASCII chỉ là tập nhỏ của BMP. Đa số chữ tiếng Việt có dấu trong dạng precomposed vẫn thuộc BMP, nhưng điều đó **không bảo đảm** một chữ tiếng Việt luôn là một code point: ký tự có thể tồn tại ở dạng decomposed như chữ cái cơ sở + dấu kết hợp.

**Không nhầm ký tự ngoài BMP với emoji:** emoji là ví dụ dễ thấy, nhưng nhiều chữ cổ, ký hiệu nhạc, ký hiệu toán học và chữ hiếm cũng thuộc supplementary planes. Đồng thời, một số ký tự tham gia emoji nằm ngay trong BMP; việc hiển thị emoji còn phụ thuộc variation selector và chuỗi ZWJ.

## 4. UTF-16 mã hóa supplementary code point bằng surrogate pair ra sao?

Một supplementary code point `U` trong khoảng U+10000–U+10FFFF được biểu diễn bằng hai code unit:

1. Trừ đi `0x10000` để có số `U'` trong khoảng `0x00000` đến `0xFFFFF` (20 bit).
2. Lấy 10 bit cao cộng `0xD800` để tạo **high surrogate** (U+D800–U+DBFF).
3. Lấy 10 bit thấp cộng `0xDC00` để tạo **low surrogate** (U+DC00–U+DFFF).

Công thức:

```text
U' = U - 0x10000

high = 0xD800 + (U' >> 10)
low  = 0xDC00 + (U' & 0x3FF)

U = 0x10000
    + ((high - 0xD800) << 10)
    + (low - 0xDC00)
```

Ví dụ với `😀` (U+1F600):

```text
U  = 0x1F600
U' = 0x0F600

high = 0xD800 + (0x0F600 >> 10) = 0xD83D
low  = 0xDC00 + (0x0F600 & 0x3FF) = 0xDE00

UTF-16 = D83D DE00
```

High surrogate **không** tự đại diện cho ký tự `😀`; low surrogate cũng vậy. Chỉ **cặp đúng thứ tự** mới là một supplementary code point. Một UTF-16 string có high surrogate không kèm low surrogate hoặc low surrogate đứng một mình là chuỗi **ill-formed UTF-16**, dù `String` của Java vẫn có thể chứa một `char` như vậy.

Điều kiện hợp lệ của cặp:

- Code unit đầu trong `0xD800..0xDBFF`.
- Code unit sau trong `0xDC00..0xDFFF`.
- Không đảo thứ tự và không tách chúng ra khi cắt chuỗi, lưu fragment hoặc truyền qua tầng mã hóa khác.

### Java `char` là gì?

`char` là giá trị 16-bit không dấu biểu diễn **một UTF-16 code unit**, không phải “một ký tự Unicode bất kỳ”:

```java
char letter = 'A';            // U+0041: một code unit
char high = '\uD83D';         // high surrogate của 😀
char low = '\uDE00';          // low surrogate của 😀
int emoji = 0x1F600;          // Unicode code point
```

Một supplementary code point không thể lưu đầy đủ trong **một** `char`. Khi cần biểu diễn code point, dùng `int` hoặc `String`.

## 5. Những API Java phải biết

| API | Đơn vị / kết quả | Điểm cần lưu ý |
| --- | --- | --- |
| `s.length()` | Số UTF-16 code units | Không phải số Unicode code points |
| `s.charAt(index)` | Một `char`/UTF-16 code unit | Có thể trả một nửa surrogate pair |
| `s.codePointAt(index)` | `int` code point bắt đầu ở UTF-16 index | Nếu trỏ đúng high surrogate của cặp hợp lệ, trả code point ngoài BMP |
| `s.codePointBefore(index)` | Code point ngay trước UTF-16 index | `index` là vị trí sau ký tự cần đọc |
| `s.codePointCount(begin, end)` | Đếm code points trong khoảng UTF-16 indexes | Không đếm grapheme clusters |
| `s.offsetByCodePoints(index, offset)` | Chuyển số bước code point thành UTF-16 index | Hữu ích để cắt theo code point |
| `s.codePoints()` | `IntStream` code points | Không phải luồng `char` |
| `s.chars()` | `IntStream` code units được mở rộng thành int | Với emoji có hai phần tử |
| `Character.charCount(cp)` | 1 hoặc 2 UTF-16 units cho code point | Giúp tăng index đúng |
| `Character.isHighSurrogate(c)` | Kiểm tra high surrogate | Không đủ xác minh cặp nếu thiếu ký tự kế tiếp |
| `Character.isLowSurrogate(c)` | Kiểm tra low surrogate | Cần xét vị trí đứng trước |
| `Character.isSurrogatePair(high, low)` | Kiểm tra cặp hai code units | Có thể kết hợp `toCodePoint` |
| `Character.toCodePoint(high, low)` | Ghép cặp thành `int` code point | Đảm bảo cặp hợp lệ trước khi gọi |
| `Character.toChars(cp)` | Chuyển code point thành 1–2 `char` | Không tự là bộ kiểm tra Unicode scalar |
| `StringBuilder.appendCodePoint(cp)` | Thêm biểu diễn UTF-16 của code point | Tiện hơn ép thành `char` |

**Lưu ý về indexes:** `String.indexOf(int codePoint)` có thể tìm cả supplementary code point, nhưng **index trả về vẫn là UTF-16 index**. `substring(begin, end)` cũng nhận UTF-16 indexes, không nhận số thứ tự code point.

### 5.1. `codePointAt` cần chỉ số đúng

Với chuỗi `"A😀中"`:

```text
UTF-16 index:       0        1        2        3
code unit:         0041     D83D     DE00     4E2D
                  ('A')    (high)   (low)    ('中')

Code points:       U+0041   U+1F600          U+4E2D
```

- `s.codePointAt(1)` trả `0x1F600` khi gặp high + low hợp lệ.
- `s.charAt(1)` chỉ trả `0xD83D`.
- `s.charAt(2)` chỉ trả `0xDE00`.
- `s.codePointAt(2)` bắt đầu ở **low surrogate**, nên sẽ thấy một mã surrogate đứng riêng, **không trả ngược U+1F600**. Đó là lý do luôn duyệt từ **ranh giới code point hợp lệ**, không tùy ý tăng index từng `char` rồi gọi `codePointAt`.

## 6. Ví dụ Java 17 độc lập: đếm UTF-16 và code point

Tạo tệp `SurrogatePairDemo.java`:

```java
import java.util.Locale;

public class SurrogatePairDemo {
    public static void main(String[] args) {
        // A + 😀 + 中. Escape giúp source không phụ thuộc font editor.
        String text = "A\uD83D\uDE00\u4E2D";

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" +
                text.codePointCount(0, text.length()));
        System.out.println("highAt1=" +
                Character.isHighSurrogate(text.charAt(1)));
        System.out.println("lowAt2=" +
                Character.isLowSurrogate(text.charAt(2)));

        System.out.printf(
                Locale.ROOT,
                "codePointAt1=U+%04X%n",
                text.codePointAt(1));
        System.out.printf(
                Locale.ROOT,
                "charAt2=U+%04X%n",
                (int) text.charAt(2));

        System.out.println("afterTwoCodePoints=" +
                text.offsetByCodePoints(0, 2));
        System.out.println("emojiUtf16Units=" +
                Character.toChars(0x1F600).length);
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac -encoding UTF-8 SurrogatePairDemo.java
java SurrogatePairDemo
```

Stdout chính xác:

```text
utf16Units=4
codePoints=3
highAt1=true
lowAt2=true
codePointAt1=U+1F600
charAt2=U+DE00
afterTwoCodePoints=3
emojiUtf16Units=2
```

Giải thích:

- `A` chiếm một unit, `😀` hai units, `中` một unit → tổng **4**.
- Có ba code points → `codePointCount` bằng **3**.
- Emoji bắt đầu tại UTF-16 index **1**, chiếm indexes **1 và 2**.
- Sau **hai code points** từ index 0 (A và 😀), vị trí tiếp theo là UTF-16 index **3**.
- `Character.toChars(0x1F600)` trả `char[]` độ dài 2; không thể nhét cả emoji vào một `char`.

Một lưu ý cho người học: trong mã Java, các chuỗi escape `\uD83D\uDE00` được Java dịch thành hai `char` ghép đôi. Chúng vẫn mô tả **một** Unicode code point hợp lệ khi được đọc đúng bằng API code-point-aware.

## 7. Duyệt chuỗi: tại sao vòng lặp `charAt(i++)` chưa đủ?

Cách đơn giản nhưng **sai ngữ nghĩa** nếu mục tiêu là từng code point:

```java
for (int i = 0; i < text.length(); i++) {
    char c = text.charAt(i);
    // Với emoji, vòng lặp thấy high và low surrogate riêng.
}
```

Đây là đoạn minh họa có biến `text` từ bên ngoài. Nó không tự là bug nếu nghiệp vụ thật sự muốn duyệt **UTF-16 units**, nhưng là bug khi muốn đếm “kí tự Unicode”, kiểm tra `Character.isLetter` trên ký tự ngoài BMP hoặc xử lý từng ký tự hiển thị.

### 7.1. Cách duyệt theo code point

```java
for (int i = 0; i < text.length(); ) {
    int cp = text.codePointAt(i);
    // Xử lý toàn bộ code point tại đây.
    i += Character.charCount(cp);
}
```

Chỉ số `i` vẫn là UTF-16 index. Khi `cp` ngoài BMP, `Character.charCount(cp)` bằng 2, nhảy qua cả cặp. Với BMP, tăng 1.

### 7.2. Java 17 runnable: duyệt và in code point

Tệp `CodePointIterationDemo.java`:

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class CodePointIterationDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00\u4E2D";

        for (int i = 0; i < text.length(); ) {
            int cp = text.codePointAt(i);
            System.out.printf(
                    Locale.ROOT,
                    "utf16Index=%d codePoint=U+%04X%n", i, cp);
            i += Character.charCount(cp);
        }

        String values = text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(", "));

        System.out.println("stream=" + values);
        System.out.println("unitsStream=" + text.chars().count());
        System.out.println("pointsStream=" + text.codePoints().count());
    }
}
```

```bash
javac -encoding UTF-8 CodePointIterationDemo.java
java CodePointIterationDemo
```

Stdout:

```text
utf16Index=0 codePoint=U+0041
utf16Index=1 codePoint=U+1F600
utf16Index=3 codePoint=U+4E2D
stream=U+0041, U+1F600, U+4E2D
unitsStream=4
pointsStream=3
```

**`chars()` và `codePoints()` khác nhau:** `chars()` đưa từng UTF-16 code unit vào `IntStream`, còn `codePoints()` kết hợp các surrogate pair hợp lệ thành một phần tử `int`. Khi cần chạy các API `Character.isLetter(int)`, `Character.isDigit(int)` hoặc phân tích Unicode property, hãy ưu tiên code points thay vì ép một ký tự ngoài BMP xuống `char`.

**Điểm giới hạn:** `codePoints()` không tự biến một chuỗi UTF-16 **ill-formed** thành hợp lệ. Với unpaired surrogate, stream vẫn có thể chứa giá trị surrogate đó dưới dạng `int`; ứng dụng nhận dữ liệu không đáng tin cần xác thực riêng.

## 8. Cắt chuỗi: hai kiểu “an toàn” khác nhau

Khi gọi `substring(begin, end)`, Java hiểu `begin` và `end` là **UTF-16 indexes**. Nó không bảo đảm đầu và cuối cắt ở ranh giới code point hợp lệ. Ví dụ:

```text
"A😀B"
UTF-16: A | HIGH | LOW | B
index:  0     1     2    3  (end=4)
```

Lời gọi `text.substring(0, 2)` giữ lại `A` và **chỉ high surrogate**, làm chuỗi kết quả không còn UTF-16 well-formed. Dù Java không nhất thiết ném exception, chuỗi có thể bị thay ký tự, lỗi encoding hoặc hiển thị ký tự thay thế ở hệ thống khác.

### 8.1. Cắt đúng N code points

Nếu muốn lấy **N code points đầu tiên**, dùng `offsetByCodePoints`:

```java
int endUtf16 = text.offsetByCodePoints(0, n);
String prefix = text.substring(0, endUtf16);
```

Đoạn này thuộc một method có `text` và `n` hợp lệ. Phải kiểm tra `n` nằm trong khoảng từ 0 đến `codePointCount`; nếu vượt, `offsetByCodePoints` có thể ném `IndexOutOfBoundsException`.

### 8.2. Cắt theo ngân sách UTF-16 nhưng không chia surrogate pair

Một số storage hoặc giao thức giới hạn độ dài theo **UTF-16 units**, chẳng hạn 30.000 units/fragment. Khi buộc phải cắt theo dung lượng, phải kiểm tra ranh giới của hai unit tại điểm cắt. Nếu cuối fragment là **high surrogate** và đầu phần sau là **low surrogate**, giảm end đi một unit để chuyển **cả cặp** sang fragment kế tiếp.

Lưu ý: đây chỉ là an toàn **code point**, **chưa** bảo đảm an toàn **grapheme cluster** (emoji ZWJ hoặc dấu kết hợp).

### Ví dụ Java 17: so sánh cắt sai và cắt đúng

Tệp `SafeSliceDemo.java`:

```java
public class SafeSliceDemo {
    static String prefixByUtf16Budget(String text, int maxUnits) {
        if (maxUnits < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        int end = Math.min(text.length(), maxUnits);

        if (end > 0 && end < text.length()
                && Character.isHighSurrogate(text.charAt(end - 1))
                && Character.isLowSurrogate(text.charAt(end))) {
            end--; // Đẩy cả pair sang phần tiếp theo.
        }

        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        String broken = text.substring(0, 2);
        String safe = prefixByUtf16Budget(text, 2);
        String firstTwoPoints = text.substring(
                0, text.offsetByCodePoints(0, 2));

        System.out.println("brokenHighAtEnd=" +
                Character.isHighSurrogate(
                        broken.charAt(broken.length() - 1)));
        System.out.println("safeUnits=" + safe.length());
        System.out.println("safePoints=" +
                safe.codePointCount(0, safe.length()));
        System.out.println("twoPointsUnits=" +
                firstTwoPoints.length());
        System.out.println("twoPointsCount=" +
                firstTwoPoints.codePointCount(0, firstTwoPoints.length()));
    }
}
```

```bash
javac -encoding UTF-8 SafeSliceDemo.java
java SafeSliceDemo
```

Stdout:

```text
brokenHighAtEnd=true
safeUnits=1
safePoints=1
twoPointsUnits=3
twoPointsCount=2
```

- `broken` là `A` kèm **high surrogate đơn lẻ**; `substring` không tự báo lỗi.
- `safe` chỉ còn `A` vì ngân sách 2 UTF-16 units không đủ cho `A` (1) **và** `😀` (2).
- `firstTwoPoints` gồm `A😀` và chiếm **3** UTF-16 units, vì nó cắt theo số code points thay vì theo ngân sách 2 units.

Nếu viết một hàm chia fragment tổng quát theo `maxUnits`, còn phải xử lý trường hợp ngân sách quá nhỏ để chứa code point kế tiếp (ví dụ `maxUnits=1` nhưng phần tiếp theo bắt đầu bằng emoji). Không được lặp vô hạn khi điểm cắt được giảm về đúng vị trí đầu fragment; hãy báo lỗi hoặc thay policy ngân sách.

## 9. UTF-8, UTF-16 và việc đếm độ dài

UTF-8 và UTF-16 là **hai cách mã hóa cùng các Unicode scalar values**, nhưng dùng đơn vị khác nhau:

- UTF-8 biểu diễn mỗi scalar value bằng **1–4 byte**.
- UTF-16 biểu diễn mỗi scalar value bằng **1 hoặc 2 code units 16-bit**, tức thường tương ứng 2 hoặc 4 byte khi ghi dữ liệu UTF-16 thực.
- Java `String.length()` đếm **code units của chuỗi**, không phải bytes khi xuất UTF-8.
- `String.getBytes(StandardCharsets.UTF_8).length` đếm **bytes sau khi encode UTF-8**, thường khác `String.length()` và số code points.

Ví dụ `😀`:

| Thước đo | Giá trị |
| --- | --- |
| Unicode code point | `U+1F600` |
| UTF-16 code units trong Java String | 2 |
| UTF-16 high/low | `D83D DE00` |
| UTF-8 bytes | `F0 9F 98 80` |
| UTF-8 byte count | 4 |
| Grapheme cluster count của emoji đơn này | 1 |

### Ví dụ Java 17 độc lập: UTF-8 bytes của emoji

Tệp `Utf8VsUtf16Demo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class Utf8VsUtf16Demo {
    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        byte[] utf8 = emoji.getBytes(StandardCharsets.UTF_8);

        StringBuilder hex = new StringBuilder();
        for (byte b : utf8) {
            if (hex.length() > 0) {
                hex.append(' ');
            }
            hex.append(String.format(
                    Locale.ROOT, "%02X", Byte.toUnsignedInt(b)));
        }

        System.out.println("utf16Units=" + emoji.length());
        System.out.println("codePoints=" +
                emoji.codePointCount(0, emoji.length()));
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("utf8Hex=" + hex);
    }
}
```

```bash
javac -encoding UTF-8 Utf8VsUtf16Demo.java
java Utf8VsUtf16Demo
```

Stdout:

```text
utf16Units=2
codePoints=1
utf8Bytes=4
utf8Hex=F0 9F 98 80
```

Không dùng `String.length()` để ước lượng kích thước payload UTF-8. Ngược lại, nếu một hệ thống quy định giới hạn bằng UTF-16 units, không dùng độ dài UTF-8 bytes để quyết định điểm cắt.

Khi truyền JSON qua các nền tảng, cần ghi rõ giao thức đếm độ dài: JavaScript `String.length` thường đếm UTF-16 units tương tự Java, nhưng nhiều ngôn ngữ và thư viện khác có semantics về Unicode code point hoặc byte khác. **Hợp đồng dữ liệu phải nêu đơn vị đo**.

## 10. Unpaired surrogate: String vẫn chứa được nhưng văn bản không hợp lệ

Một `String` Java có thể chứa một high surrogate đơn lẻ:

```java
String invalid = "\uD83D";
```

`invalid.length()` vẫn bằng 1; Java không tự từ chối mọi chuỗi ill-formed tại lúc tạo object. Nhưng một surrogate đơn lẻ **không đại diện cho Unicode scalar value hợp lệ**, và việc chuyển ra UTF-8, JSON, XML, log hoặc một thư viện khác có thể dẫn đến lỗi hay ký tự thay thế.

**Không xem điều kiện `Character.isValidCodePoint(0xD83D)` là kiểm tra scalar hợp lệ**, vì nó chỉ xét miền code point, còn U+D83D chính là surrogate range. Nếu cần xác minh văn bản UTF-16 có cặp hợp lệ, phải xét thứ tự high/low:

```text
Nếu gặp high surrogate:
  Ký tự tiếp theo phải là low surrogate.
  Bỏ qua cả hai rồi tiếp tục.
Nếu gặp low surrogate mà không có high ngay trước:
  Chuỗi không well-formed.
Các char BMP khác:
  Chấp nhận.
```

### Ví dụ Java 17: báo lỗi khi encode surrogate đơn lẻ

Tệp `MalformedUtf16Demo.java`:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class MalformedUtf16Demo {
    static boolean isWellFormedUtf16(String s) {
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);

            if (Character.isHighSurrogate(ch)) {
                if (i + 1 >= s.length()
                        || !Character.isLowSurrogate(s.charAt(i + 1))) {
                    return false;
                }
                i++; // Hai units là một code point.
            } else if (Character.isLowSurrogate(ch)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        String valid = "\uD83D\uDE00";
        String loneHigh = "\uD83D";

        System.out.println("validPair=" +
                isWellFormedUtf16(valid));
        System.out.println("loneHighWellFormed=" +
                isWellFormedUtf16(loneHigh));

        boolean rejected = false;
        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(loneHigh));
        } catch (CharacterCodingException ex) {
            rejected = true;
        }

        System.out.println("encoderRejected=" + rejected);
    }
}
```

```bash
javac -encoding UTF-8 MalformedUtf16Demo.java
java MalformedUtf16Demo
```

Stdout:

```text
validPair=true
loneHighWellFormed=false
encoderRejected=true
```

Ở đây `CharsetEncoder` được cấu hình `CodingErrorAction.REPORT` nên thông báo lỗi khi gặp surrogate đơn lẻ. Một số API encode tiện dụng có thể dùng ký tự **replacement** thay vì ném exception; muốn kiểm soát mất dữ liệu thì phải chọn chiến lược encode rõ ràng và xác thực trước khi gửi.

Không thay toàn bộ surrogate đơn lẻ bằng `?` một cách âm thầm trong hệ thống yêu cầu toàn vẹn dữ liệu; hãy thiết kế policy từ chối, chuẩn hóa hoặc sửa input tại boundary đáng tin.

## 11. Code point KHÔNG đồng nghĩa grapheme cluster

Đây là khác biệt rất quan trọng với localization.

### 11.1. Chữ cái có dấu kết hợp

Hai chuỗi có thể hiển thị giống nhau:

```text
precomposed: "é"      U+00E9
decomposed:  "e◌́"     U+0065 U+0301
```

Ở dạng decomposed, đây là **hai code points**, hai UTF-16 units, nhưng thường được người dùng đọc thành **một chữ**. Nếu giới hạn nhập liệu 10 “ký tự nhìn thấy”, `codePointCount` chưa đủ để tính đúng số grapheme clusters.

Trong tiếng Việt, một tiếng có dấu có thể dùng code point dựng sẵn hoặc chuỗi dấu kết hợp. Các hệ thống tìm kiếm, validation và so sánh không nên giả định mọi văn bản đã được Unicode-normalized.

### 11.2. Emoji ghép và variation selectors

Ví dụ emoji một người với màu da, cờ quốc gia và emoji gia đình có thể gồm nhiều code points:

- Một ký hiệu kết hợp **emoji modifier** (tông da) có thể tạo một grapheme cluster.
- Cờ gồm hai **regional indicator** code points tạo hình lá cờ trong nhiều môi trường.
- Emoji gia đình có thể dùng **ZWJ** U+200D nối nhiều người thành một cụm.
- Một ký tự có thể kèm **variation selector** U+FE0F để yêu cầu trình bày kiểu emoji.

Một thuật toán chỉ “không cắt giữa surrogate pair” có thể vẫn cắt giữa một người và modifier, hai regional indicators của cờ hoặc giữa các thành phần ZWJ của gia đình. Kết quả UTF-16 **vẫn well-formed** nhưng **hiển thị sai hoặc khác dự định**.

### 11.3. Java hỗ trợ xử lý grapheme

Java 17 regex `java.util.regex.Pattern` hỗ trợ `\X` cho **Unicode extended grapheme cluster**. Ví dụ:

Tệp `GraphemeDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeDemo {
    public static void main(String[] args) {
        String text = "e\u0301";

        int count = 0;
        Matcher matcher = Pattern.compile("\\X").matcher(text);
        while (matcher.find()) {
            count++;
        }

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" +
                text.codePointCount(0, text.length()));
        System.out.println("graphemes=" + count);
    }
}
```

```bash
javac -encoding UTF-8 GraphemeDemo.java
java GraphemeDemo
```

Stdout:

```text
utf16Units=2
codePoints=2
graphemes=1
```

Kết quả `graphemes=1` là điều cần để ý: `e` và dấu kết hợp là một cụm. `BreakIterator.getCharacterInstance(locale)` là một API khác cho ranh giới ký tự theo locale, nhưng chi tiết segmentation và mức hỗ trợ emoji mới có thể khác giữa các phiên bản/dữ liệu Unicode. Với các yêu cầu UI nghiêm ngặt, kiểm thử trên phiên bản Java thật và dữ liệu Unicode thực của sản phẩm.

**Grapheme cluster vẫn chưa chắc bằng “một ký tự người dùng hiểu”:** những ngôn ngữ viết chữ phức tạp, trải nghiệm con trỏ, font shaping và thứ tự văn bản có nhiều quy tắc hơn. Khi thao tác caret, backspace hoặc cắt tin nhắn, dùng thư viện/phân đoạn tương thích yêu cầu giao diện và kiểm thử với người dùng bản địa.

## 12. Unicode normalization không phải surrogate processing

`java.text.Normalizer` hỗ trợ các dạng chuẩn hóa Unicode như `NFC`, `NFD`, `NFKC` và `NFKD`. Normalization nhằm xử lý các biểu diễn tương đương/compatibility của **chuỗi code points**, **không** phải thay vì xử lý surrogate pair.

Ví dụ:

```java
String combined = "\u00E9"; // é dựng sẵn
String split = "e\u0301";    // e + dấu sắc kết hợp

boolean equalBefore = combined.equals(split); // false
String normalized = java.text.Normalizer.normalize(
        split, java.text.Normalizer.Form.NFC);
boolean equalAfter = combined.equals(normalized); // true
```

Đây là đoạn minh họa trong method. Hai chuỗi có thể có hình thức giống nhau, nhưng `String.equals` so sánh code units, không thực hiện canonical equivalence tự động. Chuẩn hóa `NFC` thường hữu ích cho so khớp văn bản, nhưng phải dựa vào contract (với mật khẩu, chữ ký, mã định danh, normalization có thể phải theo quy tắc đặc biệt).

Không dùng `Normalizer` để “sửa” một unpaired surrogate và cũng không lầm normalization với chuyển charset. Mỗi vấn đề có phạm vi khác nhau.

## 13. Xử lý index, tìm kiếm và thao tác chuỗi an toàn

### `String.indexOf(int codePoint)`

Có thể gọi:

```java
int emojiIndex = text.indexOf(0x1F600);
```

Nó tìm code point `😀` nhưng trả **UTF-16 index**. Với `"A😀中"`, kết quả là 1. Nếu dùng `text.indexOf('\uD83D')`, bạn đang tìm **high surrogate code unit** chứ không phải code point emoji; điều đó có thể match một phần cặp hoặc một surrogate lỗi.

### `String.substring`

Chỉ số đầu/cuối là UTF-16 indexes. Luôn cắt ở **ranh giới code point** nếu chuỗi yêu cầu well-formed UTF-16, hoặc ở **ranh giới grapheme** nếu thao tác dành cho người dùng.

### `StringBuilder.reverse()`

`StringBuilder.reverse()` của Java có logic xử lý **các surrogate pair hợp lệ** để không đơn giản đảo hai nửa emoji như đảo từng char mù quáng. Tuy vậy, nó **không bảo đảm** giữ nguyên ý nghĩa của **grapheme cluster**, dấu kết hợp, emoji ZWJ hoặc thứ tự văn bản trong ngôn ngữ tự nhiên. Đừng coi reverse code units là phép “đảo các chữ nhìn thấy” chính xác.

### `String.toUpperCase(Locale)` / `toLowerCase(Locale)`

Một phép case mapping có thể **thay đổi độ dài chuỗi** (một số ký tự thành nhiều code points) và chịu quy tắc locale. Sau khi đổi case, không được dùng lại UTF-16 indexes hoặc code-point offsets cũ mà không kiểm tra.

### So sánh và độ dài

- `String.equals` / `compareTo` không tự áp canonical normalization hay collation theo ngôn ngữ.
- `String.length()` là độ dài UTF-16; `codePointCount` là số code points; regex `\X` liên quan grapheme clusters.
- Trong tìm kiếm/sắp xếp ngôn ngữ tự nhiên, cân nhắc `java.text.Collator` hoặc ICU theo chính sách, thay vì so sánh thứ tự code units.
- Giới hạn byte payload, độ dài DB và “số ký tự người dùng nhập” phải là **ba yêu cầu được diễn đạt riêng**.

## 14. Thiết kế API, lưu trữ và kiểm thử

### 14.1. Ghi rõ đơn vị đo giới hạn

Một hợp đồng thiếu rõ ràng:

```text
username maxLength = 20
```

Người phát triển có thể hiểu 20 bytes, 20 UTF-16 units, 20 code points hoặc 20 grapheme clusters. Nên ghi rõ:

```text
username maximum: 20 Unicode grapheme clusters
storage limit: measured separately in UTF-8 bytes
normalization: NFC before comparison
reject ill-formed UTF-16 input
```

Đây là ví dụ policy; từng sản phẩm có thể chọn giới hạn khác. Không nên tự động áp mọi giới hạn trên vào tên người hay mật khẩu; chính sách bảo mật và trải nghiệm người dùng cần quyết định riêng.

Nếu lưu trong DB có `VARCHAR(n)`, không mặc định tất cả DB/encoding đếm cùng một đơn vị. Một số DB và collation có semantics khác nhau; cần kiểm tra documentation thật của database và connector.

### 14.2. Dữ liệu ra ngoài JVM

Khi xuất JSON, UTF-8, XML hoặc truyền qua HTTP, cần nhất quán về charset và validation:

1. Xác thực chuỗi well-formed nếu dữ liệu không đáng tin hoặc có nguy cơ chứa surrogate đơn lẻ.
2. Chỉ format/encode ở boundary bằng charset được công bố, thường UTF-8 cho JSON/HTTP.
3. Không lưu hai nửa surrogate trong hai field hoặc hai fragment không liên hệ nếu downstream cần chuỗi Unicode well-formed.
4. Nếu buộc phải chia fragment theo UTF-16 capacity, tránh ranh giới nằm **giữa high/low surrogate** và bảo toàn thứ tự khi ghép.
5. Không dùng byte length như code-point length. Khi truncate UI, xét cả grapheme clusters và vấn đề hiển thị.
6. Khi nguồn có Unicode normalization khác nhau, kiểm tra canonical equivalence theo policy thay vì chỉ nhìn hình thức.

### 14.3. Tình huống thực tế: giới hạn fragment 30.000 UTF-16 units

Giả sử có `String content` dài và giới hạn mỗi fragment là `maxUnits=30000`. Thuật toán split an toàn tối thiểu:

```text
start = 0
while start < content.length():
    end = min(start + maxUnits, content.length())
    if end < content.length()
       and content[end-1] is HIGH surrogate
       and content[end] is LOW surrogate:
        end = end - 1
    if end <= start:
        fail: one complete code point cannot fit
    save content.substring(start, end)
    start = end
```

Điều kiện ở đây bảo toàn surrogate pair. Sau đó, ghép fragments bằng **không thêm separator** để tái lập đúng chuỗi gốc. Nếu còn yêu cầu không tách grapheme cluster, cần thuật toán phân đoạn nâng cao và có thể phải chọn điểm cắt sớm hơn.

**Một chú ý quan trọng:** thuật toán không tự biến nội dung ill-formed thành well-formed. Nếu chuỗi gốc đã có unpaired surrogate, việc bảo toàn ranh giới của các cặp hợp lệ **không đủ**; phải validate dữ liệu gốc trước.

### 14.4. Bộ test tối thiểu

| Trường hợp | Kỳ vọng |
| --- | --- |
| `"A"` | UTF-16 units = 1, code points = 1 |
| `"中"` | Units = 1, code points = 1 |
| `"😀"` | Units = 2, code points = 1 |
| `"A😀中"` | Units = 4, code points = 3 |
| `"e\u0301"` | Units = 2, code points = 2, graphemes = 1 |
| `"A😀B"` truncate tại 2 UTF-16 units | Không giữ nửa surrogate; prefix an toàn `"A"` |
| High surrogate đơn lẻ | Validation/encoder REPORT từ chối |
| Low surrogate đơn lẻ | Validation từ chối |
| High + high + low | Phần high đầu tiên là lỗi; không ghép sai |
| High + low hợp lệ | `codePointAt` và `toCodePoint` trả đúng code point |
| Emoji ZWJ và emoji modifier | Không dùng `codePointCount` như grapheme count |
| Cắt/ghép fragment | Nối chính xác UTF-16 units, không làm mất/thêm ký tự |
| NFC/NFD | So sánh theo normalization policy |
| Chuyển ra UTF-8 | Byte count và round-trip đúng với UTF-16 well-formed |

### 14.5. Bài tập độc lập về surrogate và code point

**Bài 1.** Với `s = "X😀Y"`, `s.length()` và `s.codePointCount(0, s.length())` bằng bao nhiêu?

**Đáp án:** 4 UTF-16 units, 3 code points (X = 1, emoji = 2, Y = 1).

**Bài 2.** Vì sao `s.charAt(1)` không phải `😀`?

**Đáp án:** `charAt` chỉ trả một UTF-16 code unit. Ở index 1 là high surrogate của emoji, phải kết hợp low surrogate ở index 2.

**Bài 3.** Cho high `0xD83D` và low `0xDE00`. Code point là gì?

**Đáp án:** U+1F600. Có thể dùng `Character.toCodePoint((char)0xD83D, (char)0xDE00)` sau khi xác thực cặp.

**Bài 4.** `substring(0, 2)` trên `"A😀B"` tạo vấn đề gì?

**Đáp án:** End 2 nằm giữa pair; kết quả còn high surrogate mà thiếu low surrogate, làm chuỗi không well-formed UTF-16.

**Bài 5.** `"e\u0301"` có `codePointCount=2`. Người dùng nhất thiết nhìn thấy hai chữ không?

**Đáp án:** Không. Đây là một grapheme cluster thường hiển thị như chữ é; code points khác grapheme clusters.

**Bài 6.** Emoji `😀` có hai UTF-16 units và bốn UTF-8 bytes. Nếu API giới hạn 10 ký tự, dùng `String.length()` có luôn đúng không?

**Đáp án:** Chỉ đúng nếu contract thực sự định nghĩa “ký tự” là UTF-16 units. Nếu giới hạn code points, grapheme clusters hoặc bytes, phải dùng phép đo tương ứng.

**Bài 7.** Khi nào `Character.isValidCodePoint(cp)` chưa đủ để khẳng định `cp` là Unicode scalar value?

**Đáp án:** Khi `cp` nằm trong U+D800–U+DFFF. Đây là surrogate code point (trong miền Unicode code points), nhưng không được dùng độc lập làm scalar value.

**Bài 8.** Một emoji gia đình có 7 code points nhưng thường hiển thị thành một biểu tượng. Cắt sau 3 code points có thể xảy ra điều gì?

**Đáp án:** Có thể tách chuỗi ZWJ và làm emoji bị phân rã/hỏng nghĩa dù không chia surrogate pair. Với thao tác UI, cần phân đoạn grapheme.

## 15. Các lỗi và ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Java `char` luôn là một Unicode character.” | `char` là một UTF-16 code unit; ký tự ngoài BMP cần hai units |
| “`String.length()` trả số emoji/chữ.” | Trả số UTF-16 units |
| “Emoji luôn chiếm hai `char`.” | Một supplementary code point chiếm hai units, nhưng emoji ghép có thể có nhiều code points |
| “`codePointCount` bằng số ký tự nhìn thấy.” | Không, grapheme cluster có thể gồm nhiều code points |
| “`substring` không cho cắt giữa surrogate pair.” | Nó nhận UTF-16 indexes nên có thể cắt sai |
| “`codePointAt(i)` tự tìm high surrogate dù i đang là low.” | Không; cần trỏ vào ranh giới bắt đầu code point |
| “`chars()` giống `codePoints()`.” | `chars()` duyệt code units; `codePoints()` duyệt code points |
| “`UTF-8 byte length` bằng Java `String.length()`.” | Hai thước đo khác nhau |
| “`Character.isValidCodePoint` loại mọi surrogate.” | Không; phải kiểm tra scalar riêng |
| “Một surrogate đứng riêng sẽ luôn ném lỗi ngay trong String.” | Java có thể lưu nó, lỗi thường xuất hiện khi encode hoặc validate |
| “Không chia pair là đủ để truncate emoji UI.” | Chưa đủ nếu emoji ghép bằng modifier/ZWJ |
| “Normalizer sửa được mọi UTF-16 lỗi.” | Normalization và UTF-16 well-formed validation là hai việc khác |
| “`StringBuilder.reverse()` luôn đảo đúng các chữ hiển thị.” | Nó có xử lý surrogate pair, nhưng không bảo đảm đảo theo grapheme cluster |
| “Mọi DB đều đếm VARCHAR theo Java char.” | Độ dài phụ thuộc database, charset và contract |

## 16. Ghi nhớ

- **Unicode code point ngoài BMP (U+10000–U+10FFFF) cần surrogate pair trong UTF-16.**
- **High surrogate** thuộc U+D800–U+DBFF, **low surrogate** thuộc U+DC00–U+DFFF. Một cặp hợp lệ kết hợp thành một supplementary code point.
- Java `char` là **UTF-16 code unit**. `String.length()` và `substring` dùng đơn vị/index UTF-16, không phải code point.
- Khi xử lý từng code point, dùng `codePointAt` + `Character.charCount`, `offsetByCodePoints` hoặc `String.codePoints()`.
- **Không cắt giữa high và low surrogate** khi chia chuỗi. Nếu giới hạn hiển thị theo “chữ người dùng thấy”, còn phải xem xét **grapheme clusters**.
- **UTF-8 byte count, UTF-16 unit count, code-point count và grapheme count là bốn thước đo khác nhau.**
- Java `String` có thể chứa unpaired surrogate; nếu cần văn bản hợp lệ, validate và chọn chiến lược encoder rõ ràng.
- Tách biệt encoding, normalization, collation và grapheme segmentation; chúng giải quyết những vấn đề khác nhau của localization.

### Tài liệu Java 17 chính thức

- [Character — Unicode code points and surrogate handling](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [String — length, charAt, codePointAt, codePoints, substring](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Pattern — Unicode grapheme clusters (`\X`)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [StandardCharsets — UTF-8](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Normalizer — Unicode normalization forms](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
