# Biểu thức chính quy và cụm ký tự grapheme

Khi xử lý văn bản Unicode, một vị trí mà Java nhìn thấy trong `String` không nhất thiết tương ứng với một ký tự mà người dùng nhìn thấy trên màn hình. Một emoji có thể gồm hai code point; một chữ có dấu có thể gồm chữ cái và dấu kết hợp; một emoji gia đình có thể gồm nhiều emoji nối bằng ký tự Zero Width Joiner. Vì vậy, regex kiểm tra nội dung và thuật toán cắt chuỗi phải phân biệt **UTF-16 code unit**, **Unicode code point** và **extended grapheme cluster**.

Java cung cấp hai công cụ trực tiếp để làm việc ở mức grapheme: `\X` trong `java.util.regex.Pattern` khớp một extended grapheme cluster, còn `\b{g}` khớp ranh giới giữa các cluster. `BreakIterator.getCharacterInstance()` cũng cung cấp ranh giới ký tự theo quy tắc Extended Grapheme Cluster của Unicode. Đây là API chuẩn, ổn định; không phải preview hoặc incubator trong JDK 26.

## 1. Ba mức đơn vị của văn bản Unicode

Java biểu diễn `String` bằng UTF-16. Cần phân biệt ba khái niệm:

| Đơn vị | Ý nghĩa | API Java thường dùng |
|---|---|---|
| UTF-16 code unit | Một giá trị `char` 16 bit trong chuỗi | `String.length()`, `charAt()`, `substring()` |
| Unicode code point | Một giá trị Unicode từ U+0000 đến U+10FFFF | `codePointAt()`, `codePoints()`, `codePointCount()` |
| Extended grapheme cluster | Một đơn vị văn bản gần với thứ người dùng cảm nhận là một ký tự | Regex `\X`, `BreakIterator.getCharacterInstance()` |

Với ký tự thuộc Basic Multilingual Plane (BMP), một code point thường chiếm một code unit. Ký tự bổ sung (*supplementary character*) nằm ngoài BMP cần một cặp surrogate gồm hai code unit. Một grapheme cluster có thể chứa một hoặc nhiều code point; mỗi code point lại có thể chiếm một hoặc hai code unit.

Ví dụ:

```java
String text = "A😀e\u0301";

System.out.println(text.length());
System.out.println(text.codePointCount(0, text.length()));
```

Chuỗi trên có 5 UTF-16 code unit: `A` chiếm 1, emoji `😀` chiếm 2, `e` chiếm 1 và dấu sắc kết hợp U+0301 chiếm 1. Nó có 4 code point, nhưng người dùng thường nhìn thấy 3 grapheme cluster: `A`, `😀` và `é`.

`charAt(index)` trả về một code unit, không bảo đảm là một Unicode code point hoàn chỉnh. Khi cần duyệt code point, dùng `codePoints()` hoặc `codePointAt()`; khi cần đếm hoặc cắt theo ký tự người dùng nhìn thấy, dùng grapheme segmentation.

## 2. Grapheme cluster là gì?

Unicode Standard Annex #29 định nghĩa các quy tắc ranh giới grapheme. Một extended grapheme cluster (EGC) là một chuỗi code point được xử lý như một đơn vị trong nhiều thao tác văn bản, chẳng hạn di chuyển con trỏ hoặc xóa một ký tự. Những ví dụ thường gặp:

- **Chữ và dấu kết hợp:** `e` + U+0301 COMBINING ACUTE ACCENT tạo thành một grapheme `é`.
- **Ký tự ngoài BMP:** emoji `😀` là một code point nhưng chiếm hai UTF-16 code unit.
- **Emoji có màu da:** `👍🏽` gồm emoji cơ sở và emoji modifier.
- **Emoji nối bằng ZWJ:** `👩‍💻` gồm nhiều code point được nối bằng U+200D ZERO WIDTH JOINER.
- **Cờ quốc gia:** `🇻🇳` gồm hai Regional Indicator code point nhưng được nhóm thành một grapheme.
- **Chữ Hangul:** một âm tiết có thể được biểu diễn bằng một code point hoặc chuỗi Jamo kết hợp.

Grapheme cluster là đơn vị gần với ký tự mà người dùng cảm nhận, không phải cam kết một glyph duy nhất trong mọi font. Quy tắc EGC cũng không phải thuật toán phân đoạn từ, câu, ngữ pháp hay đo độ rộng hiển thị. Một cụm có thể chiếm một, hai hoặc nhiều cột hiển thị tùy nội dung và môi trường.

## 3. Regex `\X`: khớp một grapheme cluster

Trong Java regex, `\X` khớp một Unicode extended grapheme cluster. Vì regex được viết bên trong Java string literal, phải nhân đôi dấu gạch chéo ngược:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

Pattern GRAPHEME = Pattern.compile("\\X");

String text = "e\u0301👩‍💻🇻🇳👍🏽";
Matcher matcher = GRAPHEME.matcher(text);

while (matcher.find()) {
    System.out.println(matcher.group());
}
```

Matcher tìm lần lượt các cluster trong chuỗi. Với ví dụ trên, các kết quả là `é`, `👩‍💻`, `🇻🇳` và `👍🏽`. Mỗi kết quả có thể chứa nhiều code point và nhiều UTF-16 code unit.

Có thể gom các cluster thành list:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

private static final Pattern GRAPHEME = Pattern.compile("\\X");

static List<String> graphemes(String text) {
    Matcher matcher = GRAPHEME.matcher(text);
    List<String> result = new ArrayList<>();

    while (matcher.find()) {
        result.add(matcher.group());
    }

    return List.copyOf(result);
}
```

`Pattern` là immutable và có thể chia sẻ giữa nhiều thread. `Matcher` giữ trạng thái của một lần duyệt nên không chia sẻ cùng một matcher giữa các thread đồng thời; tạo matcher mới cho từng chuỗi hoặc từng thao tác.

### 3.1. Đếm grapheme cluster

Nếu cần đếm số ký tự mà người dùng nhìn thấy gần đúng theo EGC, đếm số lần `\X` khớp:

```java
static int graphemeCount(String text) {
    Matcher matcher = GRAPHEME.matcher(text);
    int count = 0;

    while (matcher.find()) {
        count++;
    }

    return count;
}
```

Không thay bằng `text.length()` hoặc `text.codePointCount(0, text.length())`. Hai cách đó đếm các đơn vị thấp hơn grapheme. Ví dụ `e\u0301` có hai code point nhưng là một grapheme; `👩‍💻` có ba code point nhưng là một grapheme.

### 3.2. Cắt chuỗi theo grapheme

Có thể dùng `Matcher.start()` và `Matcher.end()` để lấy offset rồi cắt bằng `substring()`:

```java
static List<String> splitByGrapheme(String text) {
    Matcher matcher = GRAPHEME.matcher(text);
    List<String> result = new ArrayList<>();

    while (matcher.find()) {
        result.add(text.substring(matcher.start(), matcher.end()));
    }

    return List.copyOf(result);
}
```

`Matcher.start()` và `end()` trả offset theo chỉ số của `CharSequence`, với `String` tức là UTF-16 code unit index. Vì vậy, các offset này dùng trực tiếp được với `substring()`. Không đổi chúng thành code point index trước khi cắt.

## 4. `\b{g}`: tìm ranh giới grapheme cluster

`\b{g}` là một boundary matcher có độ rộng bằng zero: nó khớp tại vị trí nằm giữa hai grapheme cluster hoặc ở đầu/cuối chuỗi. Nó không lấy nội dung của cluster; muốn lấy nội dung thì dùng `\X`.

```java
Pattern GRAPHEME_BOUNDARY = Pattern.compile("\\b{g}");
Matcher boundaries = GRAPHEME_BOUNDARY.matcher(text);

while (boundaries.find()) {
    System.out.println("Boundary at UTF-16 index " + boundaries.start());
}
```

Các boundary hữu ích khi cần đánh dấu vị trí con trỏ, kiểm tra một offset có nằm giữa hai cluster hay không, hoặc xây dựng thao tác cắt văn bản. Vì matcher không tiêu thụ ký tự, `find()` tiếp tục tìm ranh giới kế tiếp theo cơ chế xử lý zero-length match của `Matcher`.

### 4.1. Phân biệt `\b` và `\b{g}`

Hai biểu thức có mục đích khác nhau:

| Regex | Ý nghĩa | Dùng cho |
|---|---|---|
| `\b` | Ranh giới từ, nơi word character tiếp giáp non-word character | Tìm token/từ theo định nghĩa word-character của regex |
| `\b{g}` | Ranh giới extended grapheme cluster | Di chuyển/cắt theo ký tự người dùng cảm nhận |
| `\X` | Khớp một extended grapheme cluster | Lấy từng cluster |

Không dùng `\b` để đếm ký tự hiển thị; không dùng `\b{g}` để phân đoạn từ. Nếu cần phân đoạn từ trong văn bản tự nhiên, hãy xem `BreakIterator.getWordInstance(locale)` hoặc một bộ phân đoạn ngôn ngữ phù hợp. `BreakIterator` mặc định được thiết kế cho văn bản tự nhiên, không phải tokenizer của ngôn ngữ lập trình.

## 5. Dùng BreakIterator để duyệt ký tự người dùng nhìn thấy

`java.text.BreakIterator.getCharacterInstance()` trả về iterator tìm ranh giới ký tự. Yêu cầu triển khai mặc định của Java SE 26 quy định phân tích character boundary tuân theo Unicode Extended Grapheme Cluster breaks trong UAX #29.

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

static List<String> splitWithBreakIterator(String text) {
    BreakIterator iterator = BreakIterator.getCharacterInstance(Locale.ROOT);
    iterator.setText(text);

    List<String> result = new ArrayList<>();
    int start = iterator.first();

    for (int end = iterator.next();
         end != BreakIterator.DONE;
         start = end, end = iterator.next()) {
        result.add(text.substring(start, end));
    }

    return List.copyOf(result);
}
```

`BreakIterator` trả boundary dưới dạng chỉ số ký tự của `CharacterIterator`. Với `String`, các offset đó tương ứng UTF-16 index và có thể dùng trực tiếp với `substring()`. Một iterator có trạng thái vị trí hiện tại; không dùng chung một instance cho nhiều thao tác đồng thời. Tạo iterator cho từng lần xử lý hoặc từng thread.

### 5.1. Chọn Pattern hay BreakIterator?

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Đã dùng regex và cần lấy từng cluster | `Pattern.compile("\\X")` |
| Cần kiểm tra ranh giới EGC bằng regex | `Pattern.compile("\\b{g}")` |
| Duyệt ranh giới ký tự bằng API văn bản | `BreakIterator.getCharacterInstance(locale)` |
| Duyệt từ trong văn bản tự nhiên | `BreakIterator.getWordInstance(locale)` |
| Duyệt code point, không cần nhóm grapheme | `String.codePoints()` |
| Tokenize cú pháp Java hoặc ngôn ngữ lập trình | Lexer/parser phù hợp, không dùng word BreakIterator |

`BreakIterator.getCharacterInstance()` và `\X` đều dựa trên EGC nhưng đi qua API khác nhau. Nếu cần cùng một quy tắc cho nhiều runtime hoặc dịch vụ, hãy kiểm thử các chuỗi Unicode quan trọng trên từng JDK và nhà cung cấp locale service đang triển khai.

## 6. Regex Unicode: chọn property thay vì giả định ASCII

Các shorthand regex `\d`, `\s`, `\w` có chế độ mặc định tương thích ASCII. Nếu xử lý văn bản đa ngôn ngữ, cần hiểu rõ phạm vi của chúng hoặc dùng Unicode property trực tiếp.

| Regex | Ý nghĩa |
|---|---|
| `\p{L}` | Mọi ký tự thuộc category Letter |
| `\p{M}` | Các combining mark: non-spacing, spacing-combining và enclosing mark |
| `\p{Nd}` | Decimal digit |
| `\p{IsAlphabetic}` | Ký tự có Unicode binary property Alphabetic |
| `\p{IsLatin}` | Ký tự thuộc Latin script |
| `\p{IsWhite_Space}` | Ký tự có Unicode property White_Space |

Ví dụ tìm các chuỗi chữ cái có thể chứa dấu kết hợp:

```java
Pattern lettersAndMarks = Pattern.compile("[\\p{L}\\p{M}]+");
Matcher matcher = lettersAndMarks.matcher("Tiếng Việt và e\u0301");

while (matcher.find()) {
    System.out.println(matcher.group());
}
```

`\p{L}` nhận chữ cái; `\p{M}` nhận dấu kết hợp. Chỉ dùng `\p{L}` có thể bỏ sót dấu khi văn bản đang ở dạng decomposed. Pattern trên chỉ tìm các chuỗi chữ liên tiếp; nó không phải bộ kiểm tra tên người, từ tiếng Việt hay username hoàn chỉnh. Quy tắc cho dấu cách, dấu gạch nối, dấu nháy và các ký tự khác phải do nghiệp vụ xác định.

### 6.1. Bật Unicode cho shorthand classes

Có thể bật Unicode character classes bằng flag `Pattern.UNICODE_CHARACTER_CLASS` hoặc inline flag `(?U)`:

```java
Pattern unicodeWords = Pattern.compile("(?U)\\w+");
Pattern unicodeDigits = Pattern.compile("\\d+", Pattern.UNICODE_CHARACTER_CLASS);
```

Trong chế độ Unicode, `\d`, `\s`, `\w` và các POSIX predefined classes sử dụng định nghĩa Unicode thay cho tập ASCII hẹp. Theo API Java SE 26, Unicode `\w` gồm alphabetic, combining marks, digits, connector punctuation và join controls. Flag này cũng ngầm bật `UNICODE_CASE`.

Nếu cần so khớp không phân biệt hoa thường theo Unicode, kết hợp `CASE_INSENSITIVE` với `UNICODE_CASE`, hoặc dùng inline flags `(?iu)`:

```java
Pattern unicodeIgnoreCase = Pattern.compile(
        "java",
        Pattern.UNICODE_CASE | Pattern.CASE_INSENSITIVE);
```

Nếu muốn đặt flag ngay trong regex, có thể dùng `Pattern.compile("(?iu)java")`; không cần bật cả hai cách cùng lúc.

Không giả định `\w` tương đương quy tắc identifier của Java hoặc quy tắc username của sản phẩm. Ví dụ, identifier Java có các điều kiện riêng; nếu kiểm tra identifier Java, dùng `Character.isJavaIdentifierStart(int)` và `Character.isJavaIdentifierPart(int)` hoặc parser/compiler thay vì tự suy ra từ `\w`.

## 7. Unicode normalization và so khớp chữ có dấu

Một ký tự hiển thị có thể có nhiều cách mã hóa Unicode tương đương về mặt canonical. Ví dụ chữ `é` có thể được biểu diễn bằng:

- NFC: U+00E9 LATIN SMALL LETTER E WITH ACUTE.
- NFD: U+0065 LATIN SMALL LETTER E theo sau U+0301 COMBINING ACUTE ACCENT.

Hai chuỗi này nhìn giống nhau nhưng `String.equals()` trả `false` vì dãy code unit khác nhau. `\X` vẫn nhận chúng là một grapheme cluster riêng lẻ, nhưng **không tự biến chúng thành cùng một chuỗi** để so sánh.

### 7.1. Chuẩn hóa trước khi tìm kiếm

`java.text.Normalizer` hỗ trợ NFC, NFD, NFKC và NFKD. Với dữ liệu văn bản thông thường, NFC thường là lựa chọn phù hợp để chuẩn hóa về dạng compose:

```java
import java.text.Normalizer;

static String canonicalSearchKey(String text) {
    return Normalizer.normalize(text, Normalizer.Form.NFC);
}

String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(canonicalSearchKey(composed)
        .equals(canonicalSearchKey(decomposed))); // true
```

Nếu dữ liệu được lưu, tìm kiếm hoặc so sánh ở nhiều tầng, nên thống nhất chuẩn hóa tại ranh giới nhập dữ liệu và cùng quy tắc ở phía truy vấn. Không chỉ chuẩn hóa một phía rồi mong kết quả luôn tương đương.

NFKC/NFKD thực hiện compatibility decomposition, có thể làm nhiều ký tự tương thích trở thành cùng dạng. Chỉ dùng khi nghiệp vụ muốn coi các dạng tương thích là tương đương; không thay NFC bằng NFKC một cách mặc định vì có thể thay đổi ý nghĩa hoặc định dạng văn bản.

### 7.2. CANON_EQ của Pattern

`Pattern.CANON_EQ` cho phép regex so khớp các chuỗi có canonical decomposition tương đương:

```java
Pattern canonical = Pattern.compile("\u00E9", Pattern.CANON_EQ);
boolean matches = canonical.matcher("e\u0301").matches();
```

Flag này không có inline flag. Tài liệu JDK cảnh báo `CANON_EQ` có thể gây chi phí hiệu năng và rủi ro memory exhaustion ở mức vừa phải nếu input chứa quá nhiều combining mark. Với ứng dụng tìm kiếm hoặc so sánh dữ liệu nhập từ người dùng, chuẩn hóa hai phía bằng `Normalizer` thường giúp kiểm soát chính sách rõ ràng hơn. Chỉ bật `CANON_EQ` khi thực sự cần regex tự xử lý canonical equivalence và đã kiểm tra giới hạn dữ liệu.

## 8. Regex trong Java source: hai tầng escape

Regex được viết dưới dạng `String` nên phải xử lý cả cú pháp Java và cú pháp regex:

| Regex mong muốn | Java string literal |
|---|---|
| `\X` | `"\\X"` |
| `\b{g}` | `"\\b{g}"` |
| `\p{L}` | `"\\p{L}"` |
| `\d+` | `"\\d+"` |
| `\s+` | `"\\s+"` |

Khi đọc regex từ file cấu hình hoặc database, chuỗi đầu vào đã là regex text, không cần nhân đôi dấu `\` như trong Java source. Luôn kiểm tra nơi pattern được định nghĩa để tránh escape hai lần hoặc thiếu một lần.

Nếu chuỗi tìm kiếm đến từ người dùng và phải được coi là văn bản literal, dùng `Pattern.quote()` thay vì nối thẳng vào regex:

```java
String userText = "price (special) + tax";
Pattern literal = Pattern.compile(Pattern.quote(userText));
boolean found = literal.matcher(document).find();
```

Nếu dữ liệu thay thế chứa `$` hoặc `\`, dùng `Matcher.quoteReplacement()` khi truyền vào `replaceAll()` hoặc `appendReplacement()`:

```java
String safeReplacement = Matcher.quoteReplacement(userReplacement);
String result = literal.matcher(document).replaceAll(safeReplacement);
```

Điều này tránh để dữ liệu literal bị diễn giải như metacharacter hoặc back-reference của regex.

## 9. Regex Unicode cho tìm kiếm và kiểm tra văn bản

Một ví dụ tổng hợp: tìm các từ có chữ và dấu kết hợp, sau đó đếm số grapheme trong từng từ. Quy tắc này chỉ là minh họa cho một tập chữ liên tiếp; không thay thế bộ phân đoạn từ theo ngôn ngữ:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

private static final Pattern LETTER_RUN =
        Pattern.compile("[\\p{L}\\p{M}]+");
private static final Pattern GRAPHEME = Pattern.compile("\\X");

static void inspectWords(String text) {
    Matcher words = LETTER_RUN.matcher(text);

    while (words.find()) {
        String word = words.group();
        Matcher clusters = GRAPHEME.matcher(word);
        int count = 0;

        while (clusters.find()) {
            count++;
        }

        System.out.printf("%s: %d graphemes%n", word, count);
    }
}
```

Ở đây regex thứ nhất chọn chuỗi chữ và mark; regex thứ hai đếm EGC bên trong mỗi chuỗi. Hai bước giải quyết hai bài toán khác nhau: phân loại code point theo property và phân đoạn thành cluster.

## 10. Kiểm thử grapheme với combining mark và emoji

Không nên chỉ kiểm tra văn bản ASCII. Bộ test cần có các dạng Unicode có thể gồm nhiều code point hoặc nhiều code unit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class GraphemeTest {
    @Test
    void countsExtendedGraphemeClusters() {
        String text = "e\u0301👩‍💻🇻🇳👍🏽";

        assertEquals(4, graphemes(text).size());
    }

    @Test
    void keepsCombiningSequenceTogether() {
        String text = "e\u0301";

        assertEquals(List.of(text), graphemes(text));
    }

    @Test
    void keepsEmojiZwjSequenceTogether() {
        String text = "👩‍💻";

        assertEquals(List.of(text), graphemes(text));
    }

    @Test
    void keepsRegionalIndicatorPairTogether() {
        String text = "🇻🇳";

        assertEquals(List.of(text), graphemes(text));
    }
}
```

`graphemes()` là hàm được định nghĩa ở phần dùng `Pattern.compile("\\X")`. Các test trên kiểm tra combining mark, ZWJ sequence, cặp Regional Indicator và số cluster tổng thể. Bổ sung test cho emoji modifier, Hangul Jamo, chuỗi có nhiều combining mark, chuỗi rỗng và ký tự bổ sung theo tập dữ liệu thực tế của sản phẩm.

Nếu cần kiểm tra tương thích giữa `Pattern` và `BreakIterator`, chạy cùng một tập test qua cả hai implementation. Nếu có custom `BreakIteratorProvider`, hãy kiểm tra provider thực tế đang được chọn.

## 11. Giới hạn và lưu ý bảo mật của regex

`java.util.regex.Pattern` dùng engine NFA có backtracking. Một pattern có nhiều cách phân chia input giống nhau, đặc biệt với nested quantifier, alternation mơ hồ hoặc back-reference, có thể tốn thời gian rất lớn khi input gần khớp nhưng cuối cùng thất bại. Đây là nhóm lỗi Regular Expression Denial of Service (ReDoS). Một số JDK có tối ưu để giảm chi phí của một số pattern cổ điển, nhưng đó không phải cam kết thời gian chạy có giới hạn cho mọi regex.

Ví dụ pattern nguy hiểm:

```java
Pattern risky = Pattern.compile("^(a+)+$");
```

Pattern này minh họa cấu trúc lặp lồng nhau có nhiều cách phân chia input trong các engine backtracking; mức độ ảnh hưởng thực tế phụ thuộc pattern, JDK và các tối ưu của runtime. Không dùng nested repetition hoặc back-reference phức tạp cho dữ liệu không tin cậy nếu chưa phân tích độ phức tạp và kiểm thử input thất bại có chủ đích.

Các nguyên tắc thực tế:

- Giới hạn độ dài input trước khi đưa vào regex.
- Tránh nested quantifier và các nhánh có thể tiêu thụ cùng một đoạn input theo nhiều cách.
- Dùng character class hoặc cấu trúc pattern đơn giản, xác định rõ phần nào được lặp.
- Không nối regex do người dùng nhập trực tiếp vào pattern nội bộ; dùng `Pattern.quote()` nếu mục tiêu là literal.
- Compile pattern một lần và tái sử dụng; tạo `Matcher` mới cho từng input.
- Kiểm thử cả input hợp lệ lẫn input dài gần khớp nhưng thất bại.
- Nếu cho phép người dùng cung cấp regex tùy ý, cân nhắc engine có giới hạn độ phức tạp hoặc sandbox riêng; `java.util.regex` không cung cấp tham số timeout trực tiếp cho một lần match. Không dựa vào `Thread.interrupt()` như một timeout bảo đảm cho phép match đang chạy.

`CANON_EQ` có cảnh báo memory exhaustion riêng khi input chứa quá nhiều combining marks. Nếu dữ liệu không tin cậy, giới hạn độ dài và số lượng combining mark, hoặc chuẩn hóa đầu vào trước khi match theo chính sách ứng dụng.

## 12. Unicode version và tương thích trên JDK 26

Java SE 26 dựa trên Unicode Standard 17.0 cho thông tin ký tự trong `Character`. Các Unicode categories, scripts và binary properties mà `Pattern` hỗ trợ dựa trên phiên bản Unicode của `Character`. Vì thế, ký tự mới được thêm vào Unicode có thể được phân loại khác giữa JDK 24, JDK 26 và các release sau.

`\X`, `\b{g}` và `BreakIterator.getCharacterInstance()` là các API hiện hành; không phải tính năng preview của Java 26. Grapheme cluster matching trong `Pattern` đã có từ JDK 9, vì vậy không nên mô tả nó như một tính năng mới chỉ xuất hiện ở JDK 26. Điểm cần kiểm tra trên JDK 26 là dữ liệu Unicode 17.0 và hành vi segmentation theo phiên bản Unicode được runtime hỗ trợ.

Khi nâng JDK, cập nhật test với các code point mới, emoji sequence mới và các chuỗi combining mark trong dữ liệu thực tế. Không giả định ranh giới grapheme sẽ bất biến giữa mọi phiên bản Unicode: UAX #29 có thể bổ sung quy tắc khi Unicode phát triển.

## 13. Checklist chọn đúng API

- [ ] Cần đếm đơn vị UTF-16? Dùng `String.length()`.
- [ ] Cần duyệt code point? Dùng `String.codePoints()` hoặc `codePointAt()`.
- [ ] Cần đếm/cắt ký tự người dùng nhìn thấy? Dùng `\X` hoặc `BreakIterator.getCharacterInstance()`.
- [ ] Cần kiểm tra ranh giới grapheme? Dùng `\b{g}`, không dùng `\b`.
- [ ] Cần phân đoạn từ tự nhiên? Dùng `BreakIterator.getWordInstance(locale)` hoặc tokenizer theo ngôn ngữ.
- [ ] Cần nhận chữ và dấu kết hợp? Xem `\p{L}` và `\p{M}`.
- [ ] Cần Unicode semantics cho `\d`, `\s`, `\w`? Bật `UNICODE_CHARACTER_CLASS` hoặc `(?U)`.
- [ ] Cần so sánh chuỗi canonical-equivalent? Chuẩn hóa bằng `Normalizer` trước khi so sánh; chỉ dùng `CANON_EQ` khi đã đánh giá chi phí.
- [ ] Cần tìm chuỗi người dùng nhập theo nghĩa literal? Dùng `Pattern.quote()`.
- [ ] Regex xử lý input không tin cậy? Giới hạn input và tránh cấu trúc có nguy cơ ReDoS.
- [ ] Đang nâng JDK? Kiểm tra lại Unicode version và test grapheme trên runtime mục tiêu.

## Tài liệu tham khảo

- [Java SE 26 API: Pattern](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 26 API: Matcher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Matcher.html)
- [Java SE 26 API: BreakIterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/BreakIterator.html)
- [Java SE 26 API: Character – Unicode 17.0](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html)
- [Java SE 26 API: Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Standard Annex #29: Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
- [Unicode Standard Annex #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
- [OWASP: Regular Expression Denial of Service (ReDoS)](https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS)
