# Hỗ trợ Unicode 17.0 trong Java 26

## Mục tiêu

Sau bài học này, bạn có thể:

- Xác định phiên bản Unicode mà Java 26 sử dụng và những phần dữ liệu được cập nhật.
- Nhận biết các ký tự và script mới của Unicode 17.0 bằng API `Character`.
- Phân biệt UTF-16 code unit, Unicode code point và extended grapheme cluster.
- Duyệt chuỗi có ký tự supplementary mà không tách đôi surrogate pair.
- Dùng `Normalizer` để xử lý các dạng biểu diễn tương đương theo Unicode.
- Hiểu vai trò của Unicode Bidirectional Algorithm trong `java.text.Bidi`.
- Dùng regex `\X` để làm việc với extended grapheme cluster.
- Kiểm thử và triển khai ứng dụng Unicode trên JDK 26 mà không nhầm hỗ trợ dữ liệu với khả năng hiển thị của font hoặc hệ thống bên ngoài.

## 1. Java 26 cập nhật lên Unicode 17.0

JDK 26 nâng dữ liệu Unicode mà Java sử dụng từ Unicode 16.0 lên Unicode 17.0. Đây là bản cập nhật dữ liệu và quy tắc xử lý văn bản trong các API nền tảng; không phải preview feature và không cần bật cờ JVM.

Unicode 17.0 bổ sung 4.803 ký tự, đưa tổng số ký tự đã được mã hóa lên 159.801. Trong số các bổ sung có:

- Bốn script mới: **Sidetic**, **Tolong Siki**, **Beria Erfe** và **Tai Yo**.
- Tám emoji mới.
- Các ký tự, biểu tượng và bổ sung cho những block đã tồn tại.

JDK 26 cập nhật những phần chính sau:

| API Java | Phần Unicode được hỗ trợ |
|---|---|
| `java.lang.Character` | Unicode Character Database (UCD), gồm tên, category, script và các thuộc tính ký tự |
| `java.text.Bidi` | Unicode Standard Annex #9 – Unicode Bidirectional Algorithm |
| `java.text.Normalizer` | Unicode Standard Annex #15 – Unicode Normalization Forms |
| `java.util.regex` | Unicode Standard Annex #29 – Extended Grapheme Clusters |

Các API này dùng dữ liệu Unicode 17.0 trong JDK 26. Điều đó giúp Java nhận diện và xử lý đúng các ký tự, thuộc tính và quy tắc phân đoạn mới theo phiên bản chuẩn này.

Đây là cập nhật của runtime JDK. Thư viện bên ngoài, database, hệ điều hành, trình duyệt hoặc dịch vụ khác không tự động chuyển sang Unicode 17.0 chỉ vì ứng dụng được chạy bằng Java 26.

## 2. Bốn script mới và cách nhận diện bằng Character

Unicode 17.0 bổ sung bốn script được JDK 26 đưa vào `Character.UnicodeScript`:

| Script | Enum constant |
|---|---|
| Sidetic | `Character.UnicodeScript.SIDETIC` |
| Tolong Siki | `Character.UnicodeScript.TOLONG_SIKI` |
| Beria Erfe | `Character.UnicodeScript.BERIA_ERFE` |
| Tai Yo | `Character.UnicodeScript.TAI_YO` |

Các enum constant này có từ Java 26. Ứng dụng có thể kiểm tra script của một code point bằng `Character.UnicodeScript.of(int)`.

Ví dụ với chữ cái Sidetic U+10940:

~~~java
int codePoint = 0x10940;

System.out.println(Character.isDefined(codePoint));       // true
System.out.println(Character.isLetter(codePoint));        // true
System.out.println(Character.getName(codePoint));         // SIDETIC LETTER N01
System.out.println(Character.UnicodeScript.of(codePoint)); // SIDETIC
~~~

Có thể tạo chuỗi Java chứa code point này bằng `Character.toChars()`:

~~~java
String sidetic = new String(Character.toChars(0x10940));
System.out.println(sidetic);
~~~

Không nên giả định font đang dùng có glyph Sidetic. API có thể nhận diện code point dù font hoặc terminal không thể hiển thị đúng hình dạng ký tự.

### Duyệt theo code point

Các method của `Character` nhận `int` có thể xử lý supplementary code point. Ví dụ:

~~~java
String text = "A𐥀B";

text.codePoints().forEach(codePoint -> {
    System.out.printf(
        "U+%X: %s%n",
        codePoint,
        Character.getName(codePoint)
    );
});
~~~

Dùng `Character.UnicodeScript.of(codePoint)` khi cần kiểm tra script. Không nên lấy một `char` riêng lẻ từ chuỗi rồi giả định nó luôn tương ứng với một ký tự Unicode hoàn chỉnh.

## 3. Phân biệt code unit, code point và grapheme cluster

Một nguồn lỗi phổ biến khi xử lý Unicode là coi `char`, code point và ký tự người dùng nhìn thấy là một khái niệm.

Java lưu `String` bằng UTF-16. Vì vậy, `String.length()` trả số UTF-16 code unit, không phải số Unicode code point hoặc số ký tự người dùng cảm nhận.

Ba khái niệm cần phân biệt:

- **UTF-16 code unit:** một đơn vị 16 bit được Java biểu diễn bằng `char`.
- **Unicode code point:** một giá trị mã trong phạm vi U+0000 đến U+10FFFF.
- **Extended grapheme cluster:** một chuỗi code point được quy tắc Unicode xem như một đơn vị văn bản gần với ký tự người dùng cảm nhận.

Một code point trong Basic Multilingual Plane (BMP) thường chiếm một code unit. Code point ngoài BMP cần một cặp surrogate gồm high surrogate và low surrogate, tức hai code unit.

Ví dụ:

~~~java
String text = "A𐥀B";

System.out.println(text.length());                    // 4 UTF-16 code units
System.out.println(text.codePointCount(0, text.length())); // 3 code points
~~~

Chuỗi có ba code point: chữ A, chữ Sidetic và chữ B. Code point Sidetic nằm ngoài BMP nên được biểu diễn bằng hai UTF-16 code unit.

### Đếm grapheme cluster

Một ký tự hiển thị có thể gồm nhiều code point. Ví dụ chữ `é` có thể được biểu diễn theo hai cách:

- U+00E9: LATIN SMALL LETTER E WITH ACUTE.
- U+0065 theo sau bởi U+0301: LATIN SMALL LETTER E và COMBINING ACUTE ACCENT.

Hai code point trong cách thứ hai thường được hiển thị như một đơn vị văn bản. Emoji gia đình tạo bằng các emoji riêng lẻ nối với Zero Width Joiner (ZWJ) cũng có thể là một grapheme cluster gồm nhiều code point.

Vì thế:

| Phép đo | Đếm gì? | API |
|---|---|---|
| Độ dài UTF-16 | Code unit | `String.length()` |
| Số code point | Unicode code point | `String.codePointCount()` hoặc `String.codePoints()` |
| Số grapheme cluster | Extended grapheme cluster | Regex `\X` |

Không dùng `String.length()` để giới hạn số ký tự mà người dùng nhìn thấy, ví dụ độ dài tên hiển thị hoặc nội dung tin nhắn. Hãy xác định nghiệp vụ muốn giới hạn code unit, code point hay grapheme cluster.

## 4. Duyệt supplementary character an toàn

Không nên duyệt chuỗi Unicode bằng cách coi mỗi `charAt(i)` là một ký tự độc lập:

~~~java
for (int i = 0; i < text.length(); i++) {
    char ch = text.charAt(i);
    // ch có thể chỉ là một nửa surrogate pair.
}
~~~

Với supplementary code point, vòng lặp trên sẽ thấy high surrogate và low surrogate ở hai vị trí riêng. Nếu kiểm tra `Character.isLetter(char)`, kết quả có thể sai vì overload nhận `char` không xử lý supplementary character.

Dùng `codePoints()`:

~~~java
String text = "A𐥀B";

text.codePoints().forEach(cp -> {
    if (Character.isLetter(cp)) {
        System.out.println(Character.getName(cp));
    }
});
~~~

Hoặc duyệt thủ công bằng `Character.codePointAt()` và tăng index theo số code unit của code point:

~~~java
for (int index = 0; index < text.length();) {
    int codePoint = text.codePointAt(index);

    process(codePoint);

    index += Character.charCount(codePoint);
}
~~~

`process(int)` là logic ứng dụng. `Character.charCount(codePoint)` trả về 1 hoặc 2 tùy code point có cần surrogate pair hay không.

Khi xử lý dữ liệu có thể chứa surrogate không ghép cặp, cần xác định chính sách đầu vào rõ ràng. Việc duyệt theo code point không tự biến chuỗi UTF-16 lỗi thành văn bản hợp lệ.

## 5. Nhận diện Unicode 17 bằng Character

`Character` cung cấp nhiều phép kiểm tra dựa trên UCD:

- `Character.isDefined(int)`: code point có được gán trong dữ liệu Unicode của JDK hay không.
- `Character.getName(int)`: tên Unicode của code point.
- `Character.getType(int)`: general category như letter, mark, number hoặc punctuation.
- `Character.isLetter(int)`, `isDigit(int)`, `isWhitespace(int)`: kiểm tra thuộc tính ký tự.
- `Character.UnicodeScript.of(int)`: script của code point.
- `Character.isEmoji(int)`, `isEmojiPresentation(int)` và các method emoji khác: kiểm tra thuộc tính emoji.

Ví dụ, trước Unicode 17.0, một code point mới có thể bị một runtime cũ xem là unassigned. Trên JDK 26, các code point đã được Unicode 17.0 gán sẽ được nhận diện theo dữ liệu mới.

~~~java
int sideticLetter = 0x10940;

if (Character.isDefined(sideticLetter)) {
    System.out.println(Character.getName(sideticLetter));
    System.out.println(Character.getType(sideticLetter));
    System.out.println(Character.UnicodeScript.of(sideticLetter));
}
~~~

Kết quả của các method này phụ thuộc phiên bản Unicode mà runtime hỗ trợ. Nếu cùng một ứng dụng chạy trên nhiều JDK, kết quả kiểm tra một code point mới có thể khác nhau giữa các runtime.

### Không dùng char overload cho mọi Unicode

Các method chỉ nhận `char` không thể xử lý supplementary character. Khi xử lý dữ liệu người dùng, ưu tiên overload nhận `int` hoặc API làm việc theo code point.

Ví dụ:

~~~java
int codePoint = 0x10940;

boolean letter = Character.isLetter(codePoint);
boolean defined = Character.isDefined(codePoint);
~~~

Các overload này giữ đúng ngữ nghĩa khi code point nằm ngoài BMP.

## 6. Chuẩn hóa Unicode với Normalizer

Cùng một văn bản có thể có nhiều chuỗi code point tương đương về mặt Unicode. Điều này ảnh hưởng đến so sánh, tìm kiếm, khóa dữ liệu và kiểm tra trùng lặp.

`java.text.Normalizer` hỗ trợ bốn dạng chuẩn hóa được định nghĩa trong UAX #15:

| Form | Ý nghĩa |
|---|---|
| NFC | Canonical Decomposition followed by Canonical Composition |
| NFD | Canonical Decomposition |
| NFKC | Compatibility Decomposition followed by Canonical Composition |
| NFKD | Compatibility Decomposition |

Ví dụ hai cách biểu diễn chữ `é`:

~~~java
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false

String normalizedComposed =
    Normalizer.normalize(composed, Normalizer.Form.NFC);

String normalizedDecomposed =
    Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(normalizedComposed.equals(normalizedDecomposed)); // true
~~~

NFC thường phù hợp khi cần thống nhất biểu diễn canonical trước khi so sánh hoặc lưu trữ, nếu đó là quy tắc của hệ thống.

NFKC/NFKD còn áp dụng compatibility decomposition. Chúng có thể làm mất một số khác biệt về cách trình bày hoặc ý nghĩa tương thích. Không áp dụng NFKC cho mọi loại dữ liệu mà không đánh giá tác động, đặc biệt với nội dung cần bảo toàn chính xác, mật khẩu, mã định danh hoặc dữ liệu đã ký.

### Chuẩn hóa không phải chuyển mã

`Normalizer` không chuyển UTF-8 thành UTF-16 hoặc ngược lại. Nó biến đổi chuỗi code point về một dạng chuẩn hóa Unicode. Việc mã hóa byte vẫn được thực hiện bằng charset như UTF-8 thông qua API I/O.

Chuẩn hóa cũng không thay thế case folding, collation, quy tắc tìm kiếm theo ngôn ngữ hoặc kiểm tra confusable. Những việc này có semantics riêng và cần chính sách rõ ràng.

## 7. Unicode Bidirectional Algorithm với Bidi

Một đoạn văn có thể trộn chữ viết từ trái sang phải (LTR) và phải sang trái (RTL). Ví dụ văn bản tiếng Ả Rập hoặc Hebrew có thể chứa số và tên sản phẩm Latin.

UAX #9 định nghĩa Unicode Bidirectional Algorithm để xác định thứ tự hiển thị của các đoạn văn bản hai chiều. Trong Java, `java.text.Bidi` cung cấp thông tin về các run và embedding level của văn bản.

Ví dụ:

~~~java
import java.text.Bidi;

String text = "Invoice رقم 123";

Bidi bidi = new Bidi(
    text,
    Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT
);

System.out.println("Mixed: " + bidi.isMixed());
System.out.println("Run count: " + bidi.getRunCount());

for (int run = 0; run < bidi.getRunCount(); run++) {
    int start = bidi.getRunStart(run);
    int limit = bidi.getRunLimit(run);
    byte level = (byte) bidi.getRunLevel(run);

    System.out.printf(
        "Run %d: [%d, %d), level=%d, text=%s%n",
        run,
        start,
        limit,
        level,
        text.substring(start, limit)
    );
}
~~~

Embedding level chẵn biểu thị hướng trái sang phải; level lẻ biểu thị hướng phải sang trái. Các run cho biết vùng văn bản có cùng mức hướng trong quá trình xử lý bidi.

JDK 26 cập nhật dữ liệu và quy tắc Bidi theo Unicode 17.0/UAX #9. Điều này giúp xử lý ký tự và thuộc tính hướng mới theo phiên bản chuẩn.

`Bidi` cung cấp thông tin thuật toán và thứ tự run; nó không phải bộ dựng glyph hoàn chỉnh. Font shaping, bố cục dòng, căn chỉnh và hiển thị cuối cùng vẫn thuộc trách nhiệm của toolkit giao diện hoặc renderer.

### Lưu ý bảo mật với văn bản hai chiều

Các ký tự điều khiển hướng có thể làm thứ tự hiển thị khác thứ tự lưu trữ. Điều này có thể bị lợi dụng để làm người đọc hiểu sai tên file, mã nguồn, log hoặc định danh.

Không nên xóa tất cả ký tự định dạng một cách mù quáng. Hãy xác định quy tắc cho từng ngữ cảnh:

- Hiển thị dữ liệu không tin cậy theo cách có thể nhận biết ký tự điều khiển.
- Bảo vệ log và giao diện quản trị khỏi văn bản làm đảo thứ tự hiển thị.
- Kiểm tra identifier theo chính sách sản phẩm, không dựa riêng vào hướng hiển thị.
- Không coi `Bidi` là bộ phát hiện phishing hoặc bộ lọc bảo mật.

## 8. Phân đoạn grapheme cluster bằng regex `\X`

Java regex hỗ trợ extended grapheme cluster matcher `\X` và grapheme boundary matcher `\b{g}`. Trong JDK 26, quy tắc phân đoạn được cập nhật theo UAX #29 của Unicode 17.0.

Ví dụ đếm grapheme cluster:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

static int graphemeCount(String text) {
    Matcher matcher = Pattern.compile("\\X").matcher(text);
    int count = 0;

    while (matcher.find()) {
        count++;
    }

    return count;
}
~~~

Có thể kiểm tra một chuỗi có dấu kết hợp:

~~~java
String decomposed = "e\u0301";

System.out.println(decomposed.length()); // 2 UTF-16 code units
System.out.println(
    decomposed.codePointCount(0, decomposed.length())
); // 2 code points
System.out.println(graphemeCount(decomposed)); // 1 grapheme cluster
~~~

Một emoji gia đình được ghép bằng ZWJ cũng có thể gồm nhiều code point nhưng được phân đoạn thành một extended grapheme cluster:

~~~java
String family =
    "\uD83D\uDC68\u200D" +
    "\uD83D\uDC69\u200D" +
    "\uD83D\uDC67\u200D" +
    "\uD83D\uDC66";

System.out.println(family.length()); // 11 UTF-16 code units
System.out.println(
    family.codePointCount(0, family.length())
); // 7 code points
System.out.println(graphemeCount(family)); // 1 grapheme cluster
~~~

Đây là lý do một giới hạn “10 ký tự” cần được định nghĩa chính xác. Nếu UI giới hạn 10 grapheme cluster nhưng backend dùng `String.length()`, hai tầng có thể đưa ra kết quả khác nhau.

### Dùng grapheme boundary

`\b{g}` khớp ranh giới grapheme cluster. Nó có thể hữu ích khi cần tìm ranh giới để cắt chuỗi mà không tách một cluster thành nhiều phần.

Tuy nhiên, khi cắt chuỗi, cần kiểm tra index mà matcher trả về và bảo đảm không chia cluster. Không dùng `substring(0, n)` với `n` được tính bằng số code point hoặc grapheme cluster nếu index cần truyền cho substring là UTF-16 offset.

## 9. Regex Unicode và các thuộc tính ký tự

Java regex hỗ trợ Unicode script, block, general category và binary property. Ví dụ:

~~~java
Pattern letters = Pattern.compile("\\p{L}+");
Pattern emoji = Pattern.compile("\\p{IsEmoji}");
Pattern sidetic = Pattern.compile("\\p{IsSidetic}+");
~~~

Với JDK 26, các thuộc tính được hỗ trợ dựa trên dữ liệu Unicode 17.0. Vì vậy, ký tự thuộc script mới có thể được nhận diện qua các thuộc tính script tương ứng.

Cần chú ý `\w`:

- Mặc định, `\w` dùng tập ký tự ASCII tương thích truyền thống.
- Muốn dùng định nghĩa Unicode cho predefined character classes, bật `Pattern.UNICODE_CHARACTER_CLASS` hoặc inline flag `(?U)`.

~~~java
Pattern unicodeWord = Pattern.compile(
    "\\w+",
    Pattern.UNICODE_CHARACTER_CLASS
);
~~~

Đừng nhầm `\w` với mọi khái niệm “chữ cái” trong Unicode. Tùy nghiệp vụ, có thể cần `\p{L}`, `\p{IsAlphabetic}`, thuộc tính script hoặc quy tắc identifier riêng.

Với tên người dùng hoặc định danh, regex chỉ là một phần của validation. Cần xác định rõ ký tự cho phép, script được chấp nhận, normalization, dấu kết hợp, độ dài và chính sách chống spoofing.

## 10. Những gì Unicode 17.0 không tự giải quyết

Cập nhật Unicode database trong JDK không có nghĩa mọi hệ thống hiển thị và lưu trữ đều hỗ trợ đầy đủ các ký tự mới.

| Thành phần | Điều cần kiểm tra |
|---|---|
| Font | Có glyph cho code point mới hay không |
| Terminal/console | Font và terminal có hiển thị supplementary character đúng không |
| Database | Character set, collation và Unicode version của database |
| Trình duyệt/client | Font, renderer và Unicode data phía client |
| Message broker/API | Charset và giới hạn byte/code unit |
| Search engine | Normalization, tokenization, collation và index |
| Validation | Quy tắc code point, grapheme cluster và script |
| Logging/monitoring | Khả năng lưu, hiển thị và lọc văn bản hai chiều |

Java 26 không tự nâng cấp database collation hoặc Unicode data trong thư viện bên ngoài. Một ứng dụng có thể nhận diện ký tự mới nhưng database vẫn xem nó như unassigned hoặc xử lý tìm kiếm khác.

Tương tự, API `Character` nhận diện code point không đảm bảo font có thể vẽ glyph. Người dùng có thể thấy ô vuông, ký hiệu thay thế hoặc hình dạng không mong muốn dù dữ liệu vẫn được lưu đúng.

## 11. Thiết kế validation và lưu trữ văn bản Unicode

Khi xây dựng API nhận văn bản, nên định nghĩa rõ các tầng xử lý:

1. **Charset decoding:** giải mã byte thành String bằng charset đã xác định, thường là UTF-8.
2. **Input validation:** kiểm tra chuỗi có cấu trúc UTF-16 hợp lệ và không chứa dữ liệu bị cấm theo hợp đồng.
3. **Normalization:** chọn NFC/NFKC hoặc không chuẩn hóa theo quy tắc nghiệp vụ.
4. **Character validation:** kiểm tra code point, category, script và các thuộc tính cần thiết.
5. **Length policy:** giới hạn theo byte, UTF-16 code unit, code point hoặc grapheme cluster.
6. **Storage/search:** xác nhận database và search engine xử lý cùng chính sách.
7. **Display/logging:** xử lý bidi control và ký tự không hiển thị phù hợp ngữ cảnh.

Không áp dụng cùng một quy tắc cho mọi trường dữ liệu. Ví dụ:

- Mật khẩu thường cần giữ nguyên chuỗi người dùng nhập theo chính sách xác thực; không tự ý normalize nếu giao thức không quy định.
- Tên hiển thị có thể dùng grapheme cluster để giới hạn chiều dài UI.
- Identifier có thể cần NFC, giới hạn script và chính sách confusable.
- Nội dung văn bản tự do cần bảo toàn dữ liệu và xử lý đúng encoding.
- Log có thể cần escape control characters để người vận hành đọc đúng thứ tự.

## 12. Kiểm thử Unicode 17.0 trên JDK 26

Nên có bộ test gồm các nhóm:

| Nhóm dữ liệu | Mục tiêu kiểm thử |
|---|---|
| BMP | Ký tự cơ bản và dấu kết hợp |
| Supplementary | Surrogate pair, code point ngoài BMP |
| Script mới | Sidetic, Tolong Siki, Beria Erfe, Tai Yo |
| Emoji | Emoji mới và chuỗi emoji có modifier/ZWJ |
| Bidi | Văn bản trộn LTR/RTL, số và dấu điều khiển |
| Normalization | NFC/NFD và compatibility forms |
| Grapheme | Combining mark, emoji sequence và cluster boundary |
| Invalid input | Surrogate không ghép cặp hoặc byte sequence sai |

Ví dụ kiểm tra script mới:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class Unicode17Test {
    @Test
    void recognizesSideticLetter() {
        int cp = 0x10940;

        assertTrue(Character.isDefined(cp));
        assertTrue(Character.isLetter(cp));
        assertEquals(
            Character.UnicodeScript.SIDETIC,
            Character.UnicodeScript.of(cp)
        );
    }

    @Test
    void recognizesScriptNamesAddedInJava26() {
        assertEquals(
            Character.UnicodeScript.TOLONG_SIKI,
            Character.UnicodeScript.forName("Tolong Siki")
        );

        assertEquals(
            Character.UnicodeScript.BERIA_ERFE,
            Character.UnicodeScript.forName("Beria Erfe")
        );

        assertEquals(
            Character.UnicodeScript.TAI_YO,
            Character.UnicodeScript.forName("Tai Yo")
        );
    }
}
~~~

Ví dụ kiểm tra grapheme cluster:

~~~java
@Test
void countsCombiningSequenceAsOneCluster() {
    String text = "e\u0301";

    assertEquals(2, text.codePointCount(0, text.length()));
    assertEquals(1, graphemeCount(text));
}
~~~

Trong CI, chạy test bằng đúng JDK 26. Nếu hỗ trợ nhiều JDK, ghi nhận rằng kết quả `Character.isDefined`, script, category và regex property có thể khác khi runtime dùng Unicode version cũ hơn.

## 13. Tương thích JDK và trạng thái tính năng

Unicode 17.0 support trong Java 26 là cập nhật dữ liệu của Java SE, không phải preview hay incubator.

| Thành phần | Java 25 | Java 26 |
|---|---|---|
| Unicode data trong `Character` | Unicode 16.0 | Unicode 17.0 |
| `Character.UnicodeScript` mới | Chưa có bốn script mới | Có bốn enum constant mới |
| `Normalizer` | Dữ liệu Unicode trước đó | UAX #15 cập nhật theo Unicode 17.0 |
| `Bidi` | Dữ liệu Unicode trước đó | UAX #9 cập nhật theo Unicode 17.0 |
| Regex grapheme | Unicode data trước đó | UAX #29 cập nhật theo Unicode 17.0 |

Không cần `--enable-preview`, `--add-modules` hoặc cờ JVM đặc biệt. Các API thuộc module `java.base`.

Nếu code tham chiếu trực tiếp enum constant mới như `Character.UnicodeScript.SIDETIC`, ứng dụng cần runtime có API tương ứng. Chạy binary đó trên JDK cũ hơn 26 có thể thất bại khi liên kết. Nếu cần hỗ trợ nhiều JDK, có thể dùng adapter theo runtime hoặc tránh tham chiếu trực tiếp enum mới trong phần code phải chạy trên runtime cũ.

## 14. Checklist triển khai

- [ ] Xác định JDK runtime và Unicode version mà ứng dụng đang sử dụng.
- [ ] Dùng overload nhận `int` hoặc `codePoints()` khi xử lý supplementary character.
- [ ] Không coi `String.length()` là số ký tự người dùng nhìn thấy.
- [ ] Xác định rõ giới hạn theo byte, UTF-16 code unit, code point hay grapheme cluster.
- [ ] Chọn normalization form theo nghiệp vụ, không normalize mọi dữ liệu một cách máy móc.
- [ ] Dùng `Bidi` cho xử lý hướng văn bản và vẫn kiểm soát bidi spoofing ở tầng hiển thị.
- [ ] Dùng `\X` nếu cần đếm extended grapheme cluster.
- [ ] Kiểm tra Unicode property regex và cờ `UNICODE_CHARACTER_CLASS`.
- [ ] Kiểm thử bốn script mới và emoji mới trên JDK 26.
- [ ] Xác nhận font, database, search engine và client hỗ trợ dữ liệu cần dùng.
- [ ] Kiểm tra khác biệt kết quả khi chạy trên JDK cũ hơn.
- [ ] Không nhầm cập nhật Unicode data với thay đổi charset mặc định hoặc thay đổi UTF-16.

## Kết luận

Java 26 cập nhật dữ liệu Unicode lên phiên bản 17.0, bổ sung 4.803 ký tự và bốn script Sidetic, Tolong Siki, Beria Erfe, Tai Yo. Các API `Character`, `Bidi`, `Normalizer` và regex được cập nhật theo UCD và các phụ lục UAX #9, #15, #29. Khi xử lý văn bản, cần phân biệt UTF-16 code unit, code point và extended grapheme cluster; dùng API nhận `int` cho supplementary character và regex `\X` khi cần phân đoạn grapheme. Unicode 17.0 support là API nền tảng ổn định trong JDK 26, nhưng font, database, client và thư viện ngoài JDK vẫn cần được kiểm tra riêng.

## Tài liệu tham khảo

- [Oracle JDK 26 Release Notes – Support for Unicode 17.0](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [Java SE 26 API – Character](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html)
- [Java SE 26 API – Character.UnicodeScript](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.UnicodeScript.html)
- [Java SE 26 API – Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 26 API – Bidi](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Bidi.html)
- [Java SE 26 API – Pattern](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode 17.0.0 – Unicode Consortium](https://www.unicode.org/versions/Unicode17.0.0/)
- [Unicode 17.0 Release Announcement](https://blog.unicode.org/2025/09/unicode-170-release-announcement.html)
