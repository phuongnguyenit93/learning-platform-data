# Code unit, code point và cụm ký tự hiển thị trong Java

> **Chủ đề:** Unicode và văn bản — Java 15 trở lên. Một `String` không có một cách đếm “số ký tự” duy nhất. Cần xác định rõ đang đếm **UTF-16 code units**, **Unicode code points** hay **extended grapheme clusters** (cụm ký tự người dùng thường cảm nhận là một ký tự). Đây là kiến thức vẫn áp dụng trong Java hiện đại.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `char`/UTF-16 code unit, Unicode code point và grapheme cluster; hiểu vì sao ba số đếm khác nhau.
2. Đọc và duyệt code point bằng `codePointAt()`, `codePoints()`, `codePointCount()`, `offsetByCodePoints()` mà không cắt nhầm surrogate pair.
3. Dùng regex `\\X` để nhận biết extended grapheme clusters và `BreakIterator` với giới hạn phiên bản JDK phù hợp.
4. Cắt chuỗi theo ranh giới grapheme thay vì `substring()` với số lượng UTF-16 code units tùy ý.
5. Nhận ra ảnh hưởng của emoji ghép bằng ZWJ, cờ quốc gia, dấu tiếng Việt, CRLF, Unicode normalization và text block đến thao tác đếm chuỗi.
6. Chọn đơn vị đo phù hợp với giới hạn đầu vào, giới hạn byte và giao diện người dùng.

## 1. Bốn tầng khác nhau của một văn bản

Một văn bản đi từ bytes đến các ký hiệu hiển thị qua nhiều tầng:

~~~text
Bytes theo charset (ví dụ UTF-8)
            ↓ giải mã
Java String: dãy UTF-16 code units (char)
            ↓ ghép các surrogate pair hợp lệ
Unicode code points (số nguyên U+0000..U+10FFFF)
            ↓ Unicode text segmentation / UAX #29
Extended grapheme clusters
            ↓ font, shaping, layout, rendering
Glyphs / hình ảnh hiển thị trên màn hình
~~~

**Một tầng không thay thế tầng khác.**

- **Byte:** Dung lượng sau mã hóa. Một `String` có thể tốn số byte UTF-8 khác số code units UTF-16.
- **UTF-16 code unit:** Một đơn vị 16 bit. `String.length()` đếm các đơn vị này; `charAt()` lấy một đơn vị.
- **Unicode code point:** Giá trị định danh ký tự trong Unicode, biểu diễn bằng `int`. Có code point được mã hóa bằng một `char`, có code point cần cặp hai `char`.
- **Extended grapheme cluster (EGC):** Nhóm code points được Unicode quy định là một đơn vị để phân đoạn văn bản phục vụ các thao tác hướng tới người dùng như di chuyển con trỏ, chọn hoặc cắt ở ranh giới ký tự.
- **Glyph:** Hình dạng font dùng để vẽ. Một grapheme cluster có thể cần nhiều glyph; một glyph cũng có thể biểu diễn kết hợp nhiều ký tự. Số grapheme clusters **không phải** số ô màn hình hay chiều rộng pixel.

Các từ “ký tự” (*character*) và “độ dài” dễ mơ hồ. Khi thiết kế API hay kiểm tra dữ liệu, hãy ghi rõ “code units”, “code points”, “grapheme clusters” hoặc “UTF-8 bytes”.

### 1.1. Ví dụ trực quan

Giả sử tạo chuỗi theo thứ tự:

~~~text
A           U+0041   → 1 UTF-16 code unit
🙂          U+1F642  → 2 UTF-16 code units (surrogate pair)
e           U+0065   → 1 UTF-16 code unit
◌́          U+0301   → 1 UTF-16 code unit (dấu acute tổ hợp)
~~~

Tổng hợp thành `A🙂é`:

| Đơn vị | Kết quả | Lý do |
| --- | ---: | --- |
| UTF-16 code units | **5** | `1 + 2 + 1 + 1` |
| Unicode code points | **4** | `A`, emoji, `e`, dấu tổ hợp |
| Extended grapheme clusters | **3** | `A`, emoji, `e` kèm dấu |
| Byte UTF-8 | **8** | `1 + 4 + 1 + 2` |

Không phải dấu acute tổ hợp là “rỗng”: nó là một code point thật, có thể được hiển thị cùng chữ `e`. Tương tự, emoji này là một code point, nhưng cần **hai** code units trong Java `String`.

## 2. UTF-16 code unit và surrogate pair

Java `String` mô tả chỉ số theo **UTF-16 code units**. Một `char` Java lưu một số nguyên 16 bit; không thể chứa trọn mọi code point Unicode. Với code point bổ sung (ngoài Basic Multilingual Plane), UTF-16 sử dụng:

- **High surrogate** trong khoảng `U+D800..U+DBFF`.
- **Low surrogate** trong khoảng `U+DC00..U+DFFF`.

Hai code units hợp lệ liền nhau biểu diễn một code point bổ sung. Ví dụ `U+1F642` được biểu diễn bằng `U+D83D` và `U+DE42`.

| Chỉ số UTF-16 | Code unit của `A🙂é` | Ý nghĩa |
| ---: | --- | --- |
| 0 | `U+0041` | `A` |
| 1 | `U+D83D` | High surrogate của emoji |
| 2 | `U+DE42` | Low surrogate của emoji |
| 3 | `U+0065` | `e` |
| 4 | `U+0301` | Dấu acute tổ hợp |

### 2.1. Những API thao tác với code points

| API Java | Trả về/nhận đầu vào | Lưu ý |
| --- | --- | --- |
| `s.length()` | Số UTF-16 code units | Không phải số code points |
| `s.charAt(i)` | Một `char` ở chỉ số UTF-16 `i` | Có thể chỉ là nửa surrogate pair |
| `s.codePointAt(i)` | `int` code point bắt đầu tại chỉ số UTF-16 `i` | Có thể ghép hai `char`; không truyền nhầm chỉ số code point |
| `s.codePointBefore(i)` | Code point kết thúc ngay trước vị trí UTF-16 `i` | `i` là vị trí sau phần muốn đọc |
| `s.codePointCount(begin, end)` | Số code points trong khoảng chỉ số UTF-16 | `end` là exclusive |
| `s.codePoints()` | `IntStream` theo code points | Phù hợp để duyệt Unicode |
| `s.chars()` | `IntStream` theo từng UTF-16 code unit | Không thay cho `codePoints()` |
| `s.offsetByCodePoints(i, n)` | Chỉ số UTF-16 sau khi di chuyển `n` code points | Phải đảm bảo chỉ số hợp lệ |
| `Character.toString(cp)` | `String` cho một code point hợp lệ | Hữu ích để tạo emoji từ mã Unicode |
| `StringBuilder.appendCodePoint(cp)` | Thêm code point vào builder | Không ép code point vào một `char` |

**Lưu ý quan trọng:** `String` có thể chứa **unpaired surrogate** (surrogate đơn lẻ). `codePointCount()` đếm mỗi surrogate lẻ như một giá trị riêng; `codePoints()` cũng có thể trả về giá trị surrogate lẻ. Những phương thức này **không đồng nghĩa xác thực văn bản Unicode well-formed**. Khi dữ liệu cần hợp lệ theo giao thức, phải quy định xử lý malformed Unicode và encoding.

### Ví dụ 1 — Đếm UTF-16 code units và code points

**Tệp `Utf16CodePointDemo.java`, chạy trên Java 17+:**

~~~java
public class Utf16CodePointDemo {
    public static void main(String[] args) {
        String s = "A" + Character.toString(0x1F642) + "e\u0301";

        System.out.println("units=" + s.length());
        System.out.println("points=" + s.codePointCount(0, s.length()));
        System.out.printf("charAt(1)=U+%04X%n", (int) s.charAt(1));
        System.out.printf("codePointAt(1)=U+%04X%n", s.codePointAt(1));
        System.out.println("afterEmoji=" + s.offsetByCodePoints(1, 1));
        System.out.println("charsStream=" + s.chars().count());
        System.out.println("codePointsStream=" + s.codePoints().count());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 Utf16CodePointDemo.java
java Utf16CodePointDemo
~~~

**Kết quả chính xác:**

~~~text
units=5
points=4
charAt(1)=U+D83D
codePointAt(1)=U+1F642
afterEmoji=3
charsStream=5
codePointsStream=4
~~~

`charAt(1)` chỉ đọc high surrogate `U+D83D`; `codePointAt(1)` đọc đúng emoji `U+1F642`. `offsetByCodePoints(1, 1)` trả về chỉ số UTF-16 `3`, ngay sau hai code units của emoji.

**Bẫy chỉ số:** `codePointAt(2)` không có nghĩa là “code point thứ hai” mà là “code point bắt đầu tại UTF-16 index 2”. Trong ví dụ, index 2 trỏ vào low surrogate. Muốn lấy code point thứ `n` từ đầu, dùng `offsetByCodePoints(0, n)` để chuyển sang chỉ số UTF-16 phù hợp.

## 3. Extended grapheme cluster: gần với “ký tự hiển thị” hơn code point

Unicode Standard Annex #29 (UAX #29) đưa ra **extended grapheme cluster boundaries**. Đây là mô hình phân đoạn văn bản phù hợp cho phần lớn thao tác với ký tự người dùng nhận biết.

Những trường hợp nhiều code points nhưng **một grapheme cluster**:

1. **Dấu tổ hợp:** `"e\u0301"` chứa `U+0065` + `U+0301` nhưng thường thành một cụm.
2. **Emoji với skin tone modifier:** Một ký hiệu cơ sở + modifier có thể là một cụm.
3. **Emoji nối bằng Zero Width Joiner (`U+200D`):** Ví dụ một emoji gia đình có bốn người nối bằng ba ZWJ; là nhiều code points nhưng thường một cụm.
4. **Cờ quốc gia:** Một lá cờ có thể gồm hai *regional indicator code points* nhưng là một grapheme cluster.
5. **CRLF:** Hai code points CR (`U+000D`) + LF (`U+000A`) tạo một grapheme cluster theo quy tắc ranh giới, dù đây là ký tự điều khiển, **không phải một glyph nhìn thấy**.

Điều cuối nhắc rằng grapheme cluster **gần với đơn vị chỉnh sửa ký tự**, nhưng không phải “số ký tự nhìn thấy bằng mắt” trong mọi trường hợp. Một cluster có thể gồm control characters; độ rộng hiển thị phụ thuộc font, thiết bị, shaping engine và ngữ cảnh.

### 3.1. Đếm grapheme clusters bằng regex `\\X`

Java `java.util.regex.Pattern` hỗ trợ `\X` (một **Unicode extended grapheme cluster**) và `\b{g}` (ranh giới grapheme). Hỗ trợ này có mặt từ Java 9, vẫn dùng trong Java hiện đại; vì thế ứng dụng Java 17+ có thể dùng ngay `Pattern.compile("\\X")`.

**Vì sao dấu gạch chéo ngược xuất hiện hai lần?** `"\\X"` là **Java String literal** gồm backslash + `X`, sau đó regex engine hiểu `\X`. Viết `"\X"` không phải escape Java hợp lệ.

### Ví dụ 2 — Emoji gia đình và cờ quốc gia

**Tệp `GraphemeRegexDemo.java`, chạy trên Java 17+:**

~~~java
import java.util.regex.Pattern;

public class GraphemeRegexDemo {
    private static final Pattern CLUSTER = Pattern.compile("\\X");

    public static void main(String[] args) {
        int[] familyPoints = {
            0x1F468, 0x200D, 0x1F469, 0x200D,
            0x1F467, 0x200D, 0x1F466
        };
        String family = new String(
            familyPoints, 0, familyPoints.length
        );
        String flag = new String(
            new int[] {0x1F1FA, 0x1F1F8}, 0, 2
        );

        System.out.println("family.units=" + family.length());
        System.out.println("family.points="
                + family.codePointCount(0, family.length()));
        System.out.println("family.clusters="
                + CLUSTER.matcher(family).results().count());

        System.out.println("flag.units=" + flag.length());
        System.out.println("flag.points="
                + flag.codePointCount(0, flag.length()));
        System.out.println("flag.clusters="
                + CLUSTER.matcher(flag).results().count());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GraphemeRegexDemo.java
java GraphemeRegexDemo
~~~

**Kết quả chính xác trên JDK hiện đại (kiểm chứng với Java 24):**

~~~text
family.units=11
family.points=7
family.clusters=1
flag.units=4
flag.points=2
flag.clusters=1
~~~

Gia đình gồm bốn code points emoji, mỗi mã chiếm hai UTF-16 code units, cộng với ba `U+200D` (mỗi mã một code unit): `4 × 2 + 3 = 11` code units, **7 code points**, **1 grapheme cluster**. Cờ gồm hai regional indicator code points, chiếm **4 code units**, nhưng là một grapheme cluster.

**Quy tắc Unicode thay đổi theo phiên bản:** Bộ quy tắc và dữ liệu Unicode mà JDK dùng có thể được cập nhật. Các chuỗi Unicode mới hoặc hiếm có thể có ranh giới khác nhau giữa các phiên bản runtime. Khi app client/server phải có kết quả chính xác giống nhau, hãy chuẩn hóa thư viện/Unicode version và kiểm thử các ký tự quan trọng với phiên bản đã chọn.

## 4. `BreakIterator` và ranh giới phiên bản JDK

`java.text.BreakIterator.getCharacterInstance(Locale.ROOT)` được thiết kế để tìm **ranh giới ký tự**; các chỉ số ranh giới trả về là vị trí theo **UTF-16 code units** để dùng được với `String.substring(start, end)`.

**Phân biệt theo phiên bản:**
- Kể từ **JDK 20**, *default character BreakIterator* tuân theo **Unicode Extended Grapheme Cluster boundaries** theo UAX #29. Ví dụ chuỗi cờ và emoji gia đình được xử lý như từng cluster.
- Trên **JDK 17 và các JDK trước 20**, không nên dựa vào default `BreakIterator` để phân đoạn **mọi** emoji ZWJ/flag theo EGC mới. Nó có thể chia thành nhiều đoạn hơn vì thuật toán lịch sử khác nhau.
- Để đếm EGC trên **Java 17+**, regex `\X` là lựa chọn tiện dụng; để dùng `BreakIterator` với hợp đồng EGC mặc định, chọn **JDK 20+**.

### Ví dụ 3 — Duyệt ranh giới bằng `BreakIterator` (JDK 20+)

**Tệp `GraphemeBreakIteratorDemo.java`:**

~~~java
import java.text.BreakIterator;
import java.util.Locale;

public class GraphemeBreakIteratorDemo {
    public static void main(String[] args) {
        int[] familyPoints = {
            0x1F468, 0x200D, 0x1F469, 0x200D,
            0x1F467, 0x200D, 0x1F466
        };
        String family = new String(
            familyPoints, 0, familyPoints.length
        );

        BreakIterator it =
            BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(family);

        int count = 0;
        for (int start = it.first(), end = it.next();
             end != BreakIterator.DONE;
             start = end, end = it.next()) {
            count++;
            System.out.printf(
                "cluster%d UTF16=[%d,%d)%n", count, start, end
            );
        }
        System.out.println("clusters=" + count);
    }
}
~~~

Chạy với **JDK 20 hoặc mới hơn**:

~~~bash
javac -encoding UTF-8 GraphemeBreakIteratorDemo.java
java GraphemeBreakIteratorDemo
~~~

**Kết quả trên JDK 20+ có thuật toán EGC và bộ quy tắc Unicode nhận dạng mẫu này:**

~~~text
cluster1 UTF16=[0,11)
clusters=1
~~~

Các ranh giới `0` và `11` là **chỉ số UTF-16**, không phải “code point index”. `BreakIterator` hữu ích khi xây giao diện chỉnh sửa, duyệt đoạn, chọn ký tự; nhưng nếu đang xử lý tên token của ngôn ngữ lập trình hoặc cú pháp dữ liệu, hãy dùng parser/tokenizer chuyên biệt.

## 5. Cắt chuỗi an toàn: code unit, code point hay grapheme?

`substring(beginIndex, endIndex)` nhận **chỉ số UTF-16**. Nếu cắt tại một chỉ số bất kỳ, ứng dụng có thể:

1. Cắt giữa high/low surrogate, tạo chuỗi chứa surrogate đơn lẻ.
2. Không cắt surrogate nhưng lại chia đôi **grapheme cluster**, ví dụ giữa `e` và dấu acute, hoặc giữa các emoji nối bằng ZWJ.

Vì vậy “lấy `n` ký tự đầu” phải chỉ rõ:
- **`n` UTF-16 units** nếu đó là giới hạn theo `String.length()` (nhưng có thể gây cắt không hợp lệ).
- **`n` code points** nếu hệ thống định nghĩa độ dài theo code points; dùng `offsetByCodePoints()` rồi `substring()`.
- **`n` grapheme clusters** nếu là thao tác hướng tới người dùng; chỉ cắt tại ranh giới EGC.

### 5.1. Cắt theo code points (không đảm bảo grapheme)

Đoạn dưới đây chỉ là **mã trong một phương thức Java**:

~~~java
String s = "A" + Character.toString(0x1F642) + "e\u0301";
int count = Math.min(2, s.codePointCount(0, s.length()));
int utf16End = s.offsetByCodePoints(0, count);
String prefix = s.substring(0, utf16End);

System.out.println(prefix.equals(
    "A" + Character.toString(0x1F642))); // true
~~~

Cách này giữ nguyên surrogate pair của emoji, nhưng vẫn có thể chia rời `e` và dấu tổ hợp nếu cắt đúng giữa hai code points đó. Trong thao tác giao diện, chọn ranh giới grapheme.

### Ví dụ 4 — Lấy hai grapheme clusters đầu tiên bằng regex `\X`

**Tệp `SafeGraphemePrefixDemo.java`, chạy trên Java 17+:**

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SafeGraphemePrefixDemo {
    private static final Pattern CLUSTER = Pattern.compile("\\X");

    public static String prefix(String text, int maxClusters) {
        if (maxClusters < 0) {
            throw new IllegalArgumentException("maxClusters < 0");
        }

        Matcher matcher = CLUSTER.matcher(text);
        int end = 0;
        int count = 0;

        while (count < maxClusters && matcher.find()) {
            end = matcher.end(); // Chỉ số UTF-16 hợp lệ sau cluster
            count++;
        }
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        int[] points = {
            0x1F468, 0x200D, 0x1F469, 0x200D,
            0x1F467, 0x200D, 0x1F466
        };
        String family = new String(points, 0, points.length);
        String text = "A" + family + "B";

        String firstTwo = prefix(text, 2);

        System.out.println(firstTwo.equals("A" + family));
        System.out.println("prefixUnits=" + firstTwo.length());
        System.out.println("prefixPoints="
                + firstTwo.codePointCount(0, firstTwo.length()));
        System.out.println("prefixClusters="
                + CLUSTER.matcher(firstTwo).results().count());
        System.out.println(prefix(text, 0).isEmpty());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SafeGraphemePrefixDemo.java
java SafeGraphemePrefixDemo
~~~

**Kết quả chính xác với JDK hiện đại:**

~~~text
true
prefixUnits=12
prefixPoints=8
prefixClusters=2
true
~~~

Hai clusters đầu là `A` và emoji gia đình, nên `String` kết quả dài **12 UTF-16 units** (1 + 11) và **8 code points** (1 + 7). Cách cắt sử dụng `matcher.end()`, là chỉ số UTF-16 **ngay sau cluster**, tránh cắt giữa surrogate pair hoặc bên trong chuỗi emoji ghép.

Hàm trả về cả chuỗi nếu `maxClusters` lớn hơn số clusters thực tế; trả chuỗi rỗng nếu `maxClusters == 0`; báo lỗi nếu số yêu cầu âm. Khi input có thể `null`, hãy xử lý rõ ràng theo hợp đồng phương thức trước khi gọi.

## 6. Unicode normalization không phải phân đoạn grapheme

Một ký tự có dấu có thể được mã hóa theo nhiều cách nhưng trông giống nhau:

- `"\u00E9"`: `é` được dựng sẵn (một code point).
- `"e\u0301"`: `e` + dấu acute tổ hợp (hai code points).

Hai chuỗi khác nhau với `String.equals()` dù nhìn gần như giống nhau. Chúng có số code units và code points khác nhau nhưng **cùng có một grapheme cluster** theo phân đoạn EGC.

### Ví dụ 5 — So sánh và chuẩn hóa NFC

**Tệp `NormalizationGraphemeDemo.java`:**

~~~java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class NormalizationGraphemeDemo {
    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";
        Pattern cluster = Pattern.compile("\\X");

        System.out.println(precomposed.equals(decomposed));
        System.out.println("pre.units=" + precomposed.length());
        System.out.println("decomp.units=" + decomposed.length());
        System.out.println("pre.clusters="
                + cluster.matcher(precomposed).results().count());
        System.out.println("decomp.clusters="
                + cluster.matcher(decomposed).results().count());

        String normalized =
            Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println(normalized.equals(precomposed));
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac -encoding UTF-8 NormalizationGraphemeDemo.java
java NormalizationGraphemeDemo
~~~

**Kết quả:**

~~~text
false
pre.units=1
decomp.units=2
pre.clusters=1
decomp.clusters=1
true
~~~

`Normalizer.Form.NFC` là chuẩn hóa Unicode theo dạng *canonical composition*. Nó **không** có nghĩa xóa dấu, xóa whitespace hay biến mọi chuỗi trông giống nhau thành cùng nội dung. Chỉ chuẩn hóa nếu hợp đồng dữ liệu cho phép, đặc biệt với dữ liệu chữ ký, dữ liệu cần đối chiếu byte hoặc định danh có yêu cầu bảo toàn nguyên trạng.

Nếu cần so sánh hay sắp xếp theo **quy tắc ngôn ngữ** (chẳng hạn thứ tự từ tiếng Việt), đó là bài toán collation khác với việc `equals()` và normalization; không lấy `codePointCount()` hoặc EGC làm bộ so sánh ngôn ngữ.

## 7. CRLF và text block cũng ảnh hưởng các cách đếm

Grapheme clusters không chỉ gồm ký tự nhìn thấy. Quy tắc EGC xử lý `\r\n` như **một cluster** dù có **hai code points**, còn các LF riêng lẻ vẫn là cluster riêng. Điều này quan trọng khi chuyển đổi newline giữa hệ điều hành hoặc xử lý văn bản nhiều dòng.

### Ví dụ 6 — CRLF so với text block

**Tệp `LineEndingCountDemo.java`, chạy trên Java 17+:**

~~~java
import java.util.regex.Pattern;

public class LineEndingCountDemo {
    public static void main(String[] args) {
        Pattern cluster = Pattern.compile("\\X");

        String crlf = "A\r\nB";
        System.out.printf("CRLF: units=%d points=%d clusters=%d%n",
                crlf.length(),
                crlf.codePointCount(0, crlf.length()),
                cluster.matcher(crlf).results().count());

        String block = """
            A
            B
            """;
        System.out.printf("BLOCK: equal=%s units=%d clusters=%d%n",
                block.equals("A\nB\n"),
                block.length(),
                cluster.matcher(block).results().count());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LineEndingCountDemo.java
java LineEndingCountDemo
~~~

**Kết quả chính xác:**

~~~text
CRLF: units=4 points=4 clusters=3
BLOCK: equal=true units=4 clusters=4
~~~

Với `"A\r\nB"`, cả CR và LF là code point riêng, nhưng cặp CRLF hình thành một EGC. Với text block, dấu đóng `"""` ở dòng riêng khiến nội dung là `"A\nB\n"`: hai chữ cái và hai LF, tổng **4 code units**, **4 code points**, **4 clusters**.

**Lưu ý:** Trình biên dịch Java chuẩn hóa line terminators trong nguồn text block thành LF, loại bỏ indentation phụ rồi diễn giải escape. Không suy đoán độ dài từ hình thức thụt lề của mã nguồn; hãy kiểm thử **giá trị `String` sau biên dịch**.

## 8. Chọn đơn vị đo cho từng yêu cầu thực tế

| Yêu cầu | Đơn vị thích hợp | Công cụ trong Java | Cảnh báo |
| --- | --- | --- | --- |
| API quy định số UTF-16 units | Code units | `length()` | Có thể chia surrogate pair nếu cắt tùy ý |
| Giao thức giới hạn byte UTF-8 | Bytes sau mã hóa | `s.getBytes(StandardCharsets.UTF_8).length` | Không thay bằng `length()` |
| Xử lý code point theo thuộc tính Unicode | Code points | `codePoints()`, `Character` API | Chú ý unpaired surrogates |
| Cắt tên hiển thị sau N “ký tự người dùng” | EGC | `Pattern.compile("\\X")` hoặc `BreakIterator` JDK 20+ | Quy tắc Unicode có thể thay đổi theo runtime |
| Đếm số ký tự thực tế vẽ ra | Bài toán layout/font | Công cụ đo chữ của UI | Số EGC không bằng số glyph/cell/pixel |
| So sánh hai chuỗi cùng nội dung canonical | Chuẩn hóa rồi so sánh | `Normalizer.normalize(..., NFC)`, `equals()` | Không tự chuẩn hóa khi cần bảo toàn |
| Phân tích ngôn ngữ, tách từ | Token/word boundaries | Word BreakIterator, NLP tokenizer | Khác EGC; tùy ngôn ngữ |
| Phân tích cú pháp code/JSON/XML | Grammar tokens | Parser chuyên dụng | Không dùng grapheme segmentation để parse syntax |

### Những ràng buộc thực tế cần quyết định

**1. Giới hạn 20 “ký tự” của username có nghĩa gì?** Nếu giao diện cho phép emoji và dấu tổ hợp, định nghĩa theo EGC thường gần trải nghiệm người dùng hơn số UTF-16 units. Nhưng vẫn cần giới hạn **byte hoặc code point** riêng để kiểm soát kích thước tài nguyên; một EGC có thể chứa nhiều code points.

**2. Nhập tiếng Việt có dấu tổ hợp:** Chuỗi hiển thị giống nhau có thể khác code point sequences. Nếu hệ thống chọn NFC để ổn định lưu trữ hoặc tìm kiếm, cần áp dụng tại ranh giới dữ liệu đã quy định và kiểm thử dữ liệu cũ.

**3. Ứng dụng có nhiều runtime:** Một trình duyệt, Android, iOS và các JVM khác nhau có thể đi theo phiên bản Unicode khác nhau. Nếu đặc tả yêu cầu chính xác cùng số grapheme trên mọi hệ thống, phải chủ động chọn cùng thuật toán/Unicode data version và kiểm tra bằng test case.

**4. Độ dài chuỗi không đồng nghĩa an toàn hiển thị:** Ký tự không có độ rộng, dấu điều khiển định hướng, ZWJ hoặc ký tự tổ hợp có thể làm biểu diễn khác điều người dùng tưởng. Phát hiện và xử lý chúng theo yêu cầu sản phẩm, không xóa tất cả chỉ vì chúng “vô hình”.

**5. Hiệu năng:** `length()` là thông tin sẵn có của chuỗi; duyệt code points hoặc phân đoạn EGC cần quét nội dung. Khi xử lý nhiều chuỗi, biên dịch `Pattern.compile("\\X")` một lần rồi tạo `Matcher` mới cho từng chuỗi. `Matcher` có trạng thái, không nên chia sẻ một đối tượng matcher để dùng đồng thời giữa các luồng.

## 9. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Nghĩ `length()` là “số ký tự nhìn thấy” | Emoji có thể bị tính hai | Xác định EGC nếu đó là ý nghĩa cần đo |
| Ép `codePointAt(i)` thành `char` | Mất phần của code point ngoài BMP | Giữ `int`, dùng `appendCodePoint`/`Character.toString` |
| Dùng `charAt` cho mọi ký tự Unicode | Tách surrogate pair | Duyệt `codePoints()` |
| Dùng `offsetByCodePoints` rồi tin đã tránh chia mọi chữ | Có thể chia giữa `e` và dấu tổ hợp | Cắt theo EGC |
| `substring(0, n)` với n là số code points | `substring` nhận UTF-16 indices | Chuyển chỉ số, hoặc dùng ranh giới EGC |
| Cho rằng một lá cờ emoji là một code point | Cờ thường gồm hai regional indicators | Dùng `\X` để nhận cluster |
| Dùng `BreakIterator` trên JDK 17 như UAX #29 EGC mới | Có thể tách ZWJ/flags | `\X` hoặc JDK 20+ |
| Cho rằng EGC là số glyph hoặc độ rộng terminal | Rendering phụ thuộc font/layout | Dùng hệ thống đo chữ phù hợp |
| Nhầm `"\\X"` và `"\X"` trong Java | Escape Java sai | Dùng `Pattern.compile("\\X")` |
| Coi `equals()` là so sánh Unicode canonical equivalence | `"e\u0301"` có thể khác `"\u00E9"` | Chuẩn hóa theo chính sách trước khi so sánh |
| Đếm CRLF thành hai EGC | Sai quy tắc UAX #29 | Phân đoạn theo EGC |
| Bỏ qua LF cuối của text block | Lệch kết quả đếm/cắt | Đọc giá trị sau biên dịch và kiểm thử |

## 10. Bài tập có đáp án

**Bài 1.** Một `String` chỉ chứa emoji `U+1F642` có `length()`, `codePointCount(0, length())` và số EGC bằng bao nhiêu?

**Đáp án:** `2` UTF-16 units, `1` code point, `1` grapheme cluster.

**Bài 2.** `"e\u0301"` có hai code points. Có nên cắt với `substring(0, 1)` để lấy “một ký tự hiển thị” không?

**Đáp án:** Không. Kết quả chỉ là `e`, mất dấu acute. Hãy cắt theo ranh giới EGC.

**Bài 3.** Tại sao `codePointCount()` không phù hợp làm giới hạn “10 ký tự nhìn thấy” trong mọi trường hợp?

**Đáp án:** Một EGC có thể có nhiều code points: dấu tổ hợp, emoji ZWJ và cờ. Đếm code points có thể từ chối dữ liệu trông chỉ gồm vài ký tự.

**Bài 4.** Với `"A\r\nB"`, số code points là `4`. Vì sao số EGC là `3`?

**Đáp án:** Unicode coi CR + LF liền nhau là một cluster theo quy tắc ranh giới (GB3). Hai chữ `A`, `B` tạo hai clusters còn lại.

**Bài 5.** Khi hỗ trợ Java 17 và cần duyệt đầy đủ emoji gia đình theo EGC, nên dùng `BreakIterator.getCharacterInstance()` mặc định không?

**Đáp án:** Không nên giả định nó có hành vi EGC hiện đại. Sử dụng `Pattern.compile("\\X")` hoặc một bộ phân đoạn chuyên dụng có phiên bản Unicode rõ ràng; nếu chọn default `BreakIterator` với bảo đảm EGC, sử dụng JDK 20+.

**Bài 6.** Vì sao `"é"` dựng sẵn và `"e\u0301"` có thể là cùng một grapheme nhưng `equals()` trả về `false`?

**Đáp án:** Grapheme segmentation xác định ranh giới cụm ký tự; `equals()` so sánh đơn vị mã của chuỗi. Hai biểu diễn code point khác nhau. Chỉ chuẩn hóa NFC khi đặc tả dữ liệu cho phép so sánh canonical equivalent.

## Ghi nhớ

- **UTF-16 code unit (`char`):** Đơn vị mà `String.length()` và các chỉ số `substring()` dùng.
- **Unicode code point (`int`):** Mã Unicode của một ký tự, có thể cần **hai** code units trong UTF-16.
- **Extended grapheme cluster:** Cụm code points theo UAX #29, gần với đơn vị tương tác của người dùng nhưng **không đồng nghĩa glyph hay pixel width**.
- **Java 17+:** Dùng `Pattern.compile("\\X")` để duyệt EGC; `codePoints()` để duyệt code points.
- **JDK 20+:** Default `BreakIterator.getCharacterInstance()` tuân theo EGC; nhớ rằng chỉ số biên trả về vẫn là **UTF-16**.
- **Không cắt chuỗi theo một `n` mơ hồ:** Xác định đơn vị rồi chọn API phù hợp. Đừng cắt giữa surrogate pair hoặc trong grapheme cluster.

## Tài liệu tham khảo hiện hành

- [Java SE 26 — `String` API: length, codePointAt, codePointCount, codePoints, offsetByCodePoints](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html)
- [Java SE 25 — `Pattern` API: `\X` và `\b{g}`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 24 — `BreakIterator` API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/text/BreakIterator.html)
- [Oracle — JDK 20 Release Notes: Grapheme Support in BreakIterator, JDK-8291660](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html)
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
- [Java SE 25 — `Normalizer` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html)
