# Regex với thuộc tính Unicode và cụm grapheme trong Java 15

> **Mục tiêu:** Viết và hiểu biểu thức chính quy (*regular expression*) dùng **thuộc tính Unicode** và **cụm grapheme** trong Java; phân biệt UTF-16 code unit, Unicode code point và ký tự người dùng cảm nhận; sử dụng đúng `\p{...}`, `\P{...}`, `\X`, `\b{g}` và `Pattern.UNICODE_CHARACTER_CLASS`; xử lý dấu tiếng Việt ở dạng tổ hợp, emoji, ranh giới nhóm ký tự và Unicode normalization. Nội dung chỉ gồm cơ chế **còn áp dụng trong Java hiện đại**, minh họa bằng **Java 17+** chạy được, không dùng tính năng preview.

## 1. Bối cảnh Java 15: regex phải hiểu Unicode

Java đã hỗ trợ xử lý Unicode từ lâu, và `java.util.regex.Pattern` là API chính thức còn được sử dụng trong Java 15 cũng như các JDK hiện đại. `\X` và `\b{g}`, các biểu thức thuộc tính `\p{...}` và cờ Unicode đều **không cần preview**. Đây là năng lực xử lý văn bản đang được dùng thường xuyên, chứ không phải thay đổi chỉ có trong bản phát hành Java 15.

Tại sao regex kiểu ASCII như `[A-Za-z]+` dễ sai?

- Tên **`Hà`**, **`Đức`**, **`TiếngViệt`** chứa những chữ nằm ngoài `A-Z`/`a-z`.
- Một ký tự nhìn giống **é** có thể được lưu thành một code point `U+00E9` hoặc **`e` + dấu sắc kết hợp `U+0301`**.
- Emoji **🇻🇳** gồm hai Unicode code points (regional indicators) nhưng thường được hiển thị như **một cụm grapheme**.
- Emoji gia đình **👩‍👩‍👧‍👦** là một chuỗi nhiều code points nối bằng zero-width joiner; cắt ở giữa chuỗi có thể tạo biểu diễn không mong muốn.

**Định hướng:** Dùng regex để phân tích và khớp cấu trúc Unicode; dùng `Normalizer` để xử lý tính tương đương canonical; dùng `\X` khi cần tách/cắt theo ranh giới grapheme. Đừng gộp những nhiệm vụ này thành một giả định “một Java `char` = một ký tự con người nhìn thấy”.

## 2. Ba đơn vị đếm cần phân biệt

| Đơn vị | API tiêu biểu | Đang đếm gì? | Ví dụ |
| --- | --- | --- | --- |
| **UTF-16 code unit** | `String.length()`, chỉ số `substring`, `Matcher.start()/end()` | Đơn vị `char` 16 bit trong chuỗi Java | `"🇻🇳".length() == 4` |
| **Unicode code point** | `String.codePointCount(...)`, `String.codePoints()` | Một điểm mã Unicode; ký tự ngoài BMP thường chiếm hai code units | Cờ `🇻🇳` có 2 code points |
| **Extended grapheme cluster** | Regex `\X` | Cụm ký tự theo quy tắc phân đoạn Unicode, gần với “ký tự người dùng thấy” | Cờ `🇻🇳` thường là 1 cụm |

Ví dụ với dấu sắc kết hợp:

~~~java
String composed = "\u00E9";   // é: một code point
String decomposed = "e\u0301"; // e + combining acute accent

System.out.println(composed.length());   // 1
System.out.println(decomposed.length()); // 2
~~~

Hai chuỗi **có thể hiển thị giống nhau nhưng `String.equals()` trả `false`** vì dãy code points khác nhau. `\X` sẽ xem cả chuỗi tổ hợp `e\u0301` là một cụm grapheme. **Đếm code points cũng chưa đủ để đếm grapheme**: cờ, dấu kết hợp và emoji nối bằng ZWJ có thể chứa nhiều code points trong một cụm.

**Giới hạn khái niệm:** Một grapheme cluster là ranh giới **được Unicode xác định theo thuật toán**, không phải cam kết luôn bằng một ô hiển thị, một glyph, một byte hoặc một đơn vị độ rộng cột. Font, trình hiển thị, ngôn ngữ và phiên bản Unicode vẫn ảnh hưởng trải nghiệm người dùng.

## 3. Thuộc tính Unicode: `\p{...}` và `\P{...}`

`java.util.regex.Pattern` hỗ trợ các nhóm thuộc tính Unicode. Trong cú pháp regex, `\p{prop}` khớp một code point mang thuộc tính `prop`, còn `\P{prop}` khớp một code point **không** mang thuộc tính đó.

| Regex | Ý nghĩa | Ứng dụng thường gặp |
| --- | --- | --- |
| `\p{L}` | Unicode general category **Letter**: các loại chữ cái | Lọc các ký tự thuộc nhóm chữ |
| `\p{Lu}`, `\p{Ll}` | Chữ hoa, chữ thường theo general category | Phân tích dạng chữ hoa/thường |
| `\p{M}` | **Mark**: dấu kết hợp, dấu phụ trợ | Cho phép dấu ở dạng decomposed |
| `\p{Nd}` | Số thập phân thuộc nhiều hệ chữ | Nhận chữ số Unicode khi phù hợp nghiệp vụ |
| `\p{N}` | Nhóm **Number** rộng hơn `Nd` | Khi muốn nhận mọi kiểu số thuộc category |
| `\p{IsAlphabetic}` | Thuộc tính nhị phân Unicode **Alphabetic** | Khác với chỉ hỏi general category `L` |
| `\p{sc=Greek}` | Chữ có **script** là Greek | Xác định hệ chữ |
| `\p{InGreek}` | Code point nằm trong **Unicode block** Greek | Kiểm tra vị trí thuộc khối mã |
| `\P{L}` | Một code point không thuộc nhóm Letter | Tìm dấu câu/ký tự khác chữ (cũng có thể là dấu kết hợp) |

Trong **mã Java**, ký tự backslash của regex cần được escape lần nữa:

~~~java
java.util.regex.Pattern letters =
        java.util.regex.Pattern.compile("\\p{L}+");

System.out.println(letters.matcher("Hà").matches()); // true
~~~

Chuỗi Java `"\\p{L}+"` có giá trị runtime là regex `\p{L}+`. Viết thẳng `"\p{L}+"` trong string literal thông thường là **escape Java không hợp lệ**. Sự khác nhau giữa hai tầng escaping là nguyên nhân phổ biến của lỗi compile.

**Lưu ý quan trọng:** `\p{L}` khớp **một code point thuộc category Letter**. Nó không mặc nhiên gộp dấu kết hợp thành chữ, không đảm bảo tính hợp lệ của tên người và không tự ngăn các ký tự gây nhầm lẫn thị giác.

## 4. Letter và Mark: vì sao regex chữ có thể thất bại trên tiếng Việt tổ hợp?

Xét:

~~~java
String composed = "\u00E9";   // é
String decomposed = "e\u0301"; // e + combining acute accent

System.out.println(
        java.util.regex.Pattern.matches("\\p{L}+", composed));   // true
System.out.println(
        java.util.regex.Pattern.matches("\\p{L}+", decomposed)); // false
System.out.println(
        java.util.regex.Pattern.matches("\\p{L}\\p{M}*", decomposed)); // true
~~~

Ở dạng decomposed, `e` thuộc category `L`, còn dấu sắc `U+0301` thuộc category `M`. Vì thế mẫu `\p{L}+` **không khớp toàn bộ** chuỗi `e\u0301` khi dùng `matches()`.

Nếu dữ liệu nghiệp vụ cho phép các chữ kèm dấu kết hợp, một mẫu đơn giản hơn là:

~~~java
String oneOrMoreLettersWithMarks = "(?:\\p{L}\\p{M}*)+";
~~~

Nó mô tả một hoặc nhiều chữ Unicode, mỗi chữ có thể theo sau bởi số lượng dấu kết hợp bất kỳ. Đây là **một ví dụ về cấu trúc regex**, không phải bộ xác thực tên người cho mọi ngôn ngữ; một số hệ chữ cần quy tắc riêng về thứ tự dấu, dấu nối, joiner, phân đoạn âm tiết hoặc ký tự hợp lệ. Không mặc định rằng mọi dãy `\p{L}`/`\p{M}` đều là văn bản hợp lệ theo ngữ pháp ngôn ngữ.

**Tại sao vẫn cần `\X`?** Mẫu `\p{L}\p{M}*` chỉ xét chữ và dấu; còn một grapheme cluster có thể gồm **regional indicators, emoji modifier, ZWJ và thành phần khác**, không thể biểu diễn đầy đủ bằng mẫu “một chữ và vài dấu”.

## 5. Script khác với Block: hai câu hỏi khác nhau

Unicode tổ chức ký tự theo nhiều cách. Khi dùng `\p{...}`, phải biết rõ đang hỏi **thuộc tính script** hay **vị trí trong block**:

- **Script:** phân loại hệ chữ mà ký tự thuộc về, ví dụ Greek, Latin, Han. Viết `\p{sc=Greek}` hoặc `\p{IsGreek}`.
- **Block:** một **dải mã liên tiếp** được đặt tên trong Unicode, ví dụ Greek, Greek Extended. Viết `\p{InGreek}` hoặc `\p{InGreekExtended}`.
- **General category:** kiểu ký tự như `L`, `M`, `Nd`, `Lu`; câu hỏi độc lập với script hay block.
- **Binary property:** thuộc tính có/không như `IsAlphabetic`; không đồng nhất một cách máy móc với category `L`.

Một code point thuộc script Greek **không nhất thiết ở block Greek**. Ví dụ `U+1F00`, chữ Hy Lạp alpha có dấu psili, nằm trong block **Greek Extended**:

~~~java
String greekExtended = "\u1F00";

System.out.println(java.util.regex.Pattern.matches(
        "\\p{sc=Greek}", greekExtended));       // true
System.out.println(java.util.regex.Pattern.matches(
        "\\p{InGreek}", greekExtended));        // false
System.out.println(java.util.regex.Pattern.matches(
        "\\p{InGreekExtended}", greekExtended)); // true
~~~

**Chọn script khi câu hỏi liên quan đến hệ chữ**, chọn block khi cần kiểm tra phạm vi mã Unicode cụ thể. Block không phải danh sách đầy đủ những ký tự của một ngôn ngữ; một hệ chữ có thể nằm trong nhiều block, và việc một ký tự thuộc block nào đó không chứng minh đó là từ/ngữ hợp lệ.

Đối với đầu vào nhiều ngôn ngữ, đừng dùng một script cố định để xác thực tên hoặc nội dung nếu sản phẩm không thật sự yêu cầu giới hạn đó. Cũng cần hiểu regex một mình chưa giải quyết được văn bản *mixed-script* hoặc ký tự Unicode dễ gây nhầm lẫn thị giác.

## 6. `UNICODE_CHARACTER_CLASS`: ảnh hưởng tới `\w`, `\d`, `\s`

Nhiều lập trình viên kỳ vọng `\w` luôn có nghĩa “mọi chữ trên thế giới”. Trong Java, các lớp ký tự dựng sẵn này mặc định có phạm vi tương thích ASCII:

- `\w` mặc định tương ứng chữ/số ASCII và underscore.
- `\d` mặc định là `[0-9]`.
- `\s` mặc định là tập whitespace ASCII thông dụng như space, tab, newline.

Bật `Pattern.UNICODE_CHARACTER_CLASS` (cú pháp cờ nhúng `(?U)`) để chúng hoạt động theo phân loại Unicode:

~~~java
import java.util.regex.Pattern;

String name = "Hà_Nội";

boolean asciiWords = Pattern.compile("\\w+")
        .matcher(name).matches(); // false

boolean unicodeWords = Pattern.compile(
        "\\w+", Pattern.UNICODE_CHARACTER_CLASS)
        .matcher(name).matches(); // true

boolean unicodeSpace = Pattern.compile(
        "\\s+", Pattern.UNICODE_CHARACTER_CLASS)
        .matcher("\u00A0").matches(); // true: NO-BREAK SPACE
~~~

Ví dụ này minh họa **phạm vi nhận diện ký tự**, không phải một regex kiểm tra tên người hoàn chỉnh. Unicode `\w` có thể chấp nhận các nhóm ký tự khác chữ thường theo định nghĩa của cờ; cần thiết kế whitelist nghiệp vụ riêng nếu chỉ cho phép một số loại ký tự.

**Không nhầm cờ:**

- `UNICODE_CHARACTER_CLASS` hoặc `(?U)` mở rộng ý nghĩa của **predefined** và **POSIX character classes**, đồng thời hàm ý `UNICODE_CASE`.
- `UNICODE_CASE` hoặc `(?u)` liên quan đến **case folding theo Unicode**; **không tương đương** với việc bật `UNICODE_CHARACTER_CLASS`.
- `CASE_INSENSITIVE` hoặc `(?i)` yêu cầu so khớp không phân biệt hoa/thường. Khi muốn so khớp chữ hoa/thường Unicode, cân nhắc kết hợp `CASE_INSENSITIVE | UNICODE_CASE` và test với ngôn ngữ thực tế.

Cờ Unicode **không tự chuẩn hóa NFC/NFD**, không tự đếm grapheme và không tự thay thế chính sách xác thực input.

## 7. Cụm grapheme: `\X` khớp một extended grapheme cluster

Java `Pattern` hỗ trợ:

- **`\X`:** khớp **một Unicode extended grapheme cluster**, theo thuật toán phân đoạn grapheme của Unicode.
- **`\b{g}`:** khớp **ranh giới grapheme**; đây là **zero-width assertion**, không tiêu thụ ký tự.
- **`\b`:** ranh giới từ theo semantics regex, **không phải** ranh giới grapheme; không thay thế `\b{g}`.

Để đếm grapheme:

~~~java
import java.util.regex.Pattern;

Pattern grapheme = Pattern.compile("\\X");
String text = "e\u0301"; // e + dấu sắc kết hợp

long clusters = grapheme.matcher(text).results().count();
System.out.println(clusters); // 1
~~~

Vì `\X` khớp **cụm** thay vì từng code point riêng lẻ, có thể dùng để tìm các phần tử hợp lý khi cắt hiển thị:

~~~java
List<String> parts = grapheme.matcher("A" + "e\u0301" + "🇻🇳")
        .results()
        .map(java.util.regex.MatchResult::group)
        .toList();
~~~

Đoạn `parts` là **code minh họa trong một phương thức** (cần import `java.util.List` nếu dùng như trên); nó tạo ba phần: `"A"`, `"e\u0301"`, `"🇻🇳"`. Phần tiếp theo cung cấp chương trình đầy đủ với imports và stdout đã kiểm chứng.

Ranh giới `\b{g}` dùng cho việc xác định **vị trí có thể ngắt cụm** mà không lấy nội dung cụm. Với `"e\u0301"`, có ranh giới ở vị trí UTF-16 `0` và `2`; không có ranh giới giữa `e` và combining mark.

**Giới hạn:** `\X` mô hình hóa **extended grapheme cluster**; nó không xác định độ rộng ký tự trên terminal, số glyph font vẽ, số ô trong bảng hay ranh giới từ theo ngôn ngữ. Đừng dùng `\X` thay thế các API dành riêng cho line breaking, collation, word segmentation hoặc chuẩn hóa.

## 8. Ví dụ hoàn chỉnh: Unicode properties, grapheme và normalization

Tạo tệp **UnicodeRegexDemo.java**, mã nguồn UTF-8. Chương trình dùng các tính năng đã ổn định trên **Java 17+**:

~~~java
import java.text.Normalizer;
import java.util.List;
import java.util.regex.MatchResult;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeRegexDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static long clusters(String text) {
        return GRAPHEME.matcher(text).results().count();
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        String flag = "\uD83C\uDDFB\uD83C\uDDF3"; // Vietnam flag
        String family = "👩‍👩‍👧‍👦";

        System.out.println("sameText=" + composed.equals(decomposed));
        System.out.println("sameNFC=" + composed.equals(
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)));
        System.out.println("decomposedUtf16=" + decomposed.length());
        System.out.println("decomposedCodePoints="
                + decomposed.codePointCount(0, decomposed.length()));
        System.out.println("decomposedClusters=" + clusters(decomposed));
        System.out.println("flagUtf16=" + flag.length());
        System.out.println("flagCodePoints="
                + flag.codePointCount(0, flag.length()));
        System.out.println("flagClusters=" + clusters(flag));
        System.out.println("familyCodePoints="
                + family.codePointCount(0, family.length()));
        System.out.println("familyClusters=" + clusters(family));

        Pattern letters = Pattern.compile("\\p{L}+");
        Pattern letterAndMarks = Pattern.compile("\\p{L}\\p{M}*");
        System.out.println("letterDecomposed="
                + letters.matcher(decomposed).matches());
        System.out.println("letterMarksDecomposed="
                + letterAndMarks.matcher(decomposed).matches());

        String greekExtended = "\u1F00"; // alpha with psili
        System.out.println("greekScript="
                + Pattern.matches("\\p{sc=Greek}", greekExtended));
        System.out.println("greekBlock="
                + Pattern.matches("\\p{InGreek}", greekExtended));
        System.out.println("greekExtendedBlock="
                + Pattern.matches("\\p{InGreekExtended}", greekExtended));

        String name = "Hà_Nội";
        System.out.println("wordDefault="
                + Pattern.compile("\\w+").matcher(name).matches());
        System.out.println("wordUnicode="
                + Pattern.compile("\\w+", Pattern.UNICODE_CHARACTER_CLASS)
                        .matcher(name).matches());
        System.out.println("alphaUnicode="
                + Pattern.matches("\\p{IsAlphabetic}+", "TiếngViệt"));

        List<String> parts = GRAPHEME.matcher("A" + decomposed + flag)
                .results().map(MatchResult::group).toList();
        System.out.println("segments=" + parts.size());
        System.out.println("segmentsText=" + String.join("|", parts));
        System.out.println("graphemeBoundaries="
                + Pattern.compile("\\b{g}")
                        .matcher(decomposed).results().count());

        System.out.println("unicodeSpace="
                + Pattern.compile("\\s+", Pattern.UNICODE_CHARACTER_CLASS)
                        .matcher("\u00A0").matches());
        System.out.println("defaultSpace="
                + Pattern.compile("\\s+").matcher("\u00A0").matches());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 UnicodeRegexDemo.java
java UnicodeRegexDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
sameText=false
sameNFC=true
decomposedUtf16=2
decomposedCodePoints=2
decomposedClusters=1
flagUtf16=4
flagCodePoints=2
flagClusters=1
familyCodePoints=7
familyClusters=1
letterDecomposed=false
letterMarksDecomposed=true
greekScript=true
greekBlock=false
greekExtendedBlock=true
wordDefault=false
wordUnicode=true
alphaUnicode=true
segments=3
segmentsText=A|é|🇻🇳
graphemeBoundaries=2
unicodeSpace=true
defaultSpace=false
~~~

**Giải thích kết quả then chốt:**

1. `composed.equals(decomposed) == false`: cùng hình thức nhìn thấy không đồng nghĩa cùng dãy UTF-16/code points. Sau khi chuẩn hóa decomposed về NFC, hai giá trị bằng nhau.
2. `decomposedUtf16=2` và `decomposedCodePoints=2`, nhưng `decomposedClusters=1`: dấu sắc kết hợp được nhóm chung với chữ `e`.
3. Cờ `🇻🇳` có 4 UTF-16 code units, 2 code points, 1 grapheme cluster. Chuỗi emoji gia đình có 7 code points nhưng chỉ 1 cụm trong môi trường JDK đã kiểm thử.
4. `\p{L}+` không khớp toàn bộ dạng decomposed vì dấu sắc thuộc `M`; mẫu `\p{L}\p{M}*` thì có.
5. `\p{sc=Greek}` nhận U+1F00, nhưng `\p{InGreek}` không vì ký tự thuộc block Greek Extended.
6. `\w+` mặc định không nhận toàn bộ `Hà_Nội`; bật `UNICODE_CHARACTER_CLASS` thì nhận. `\s` mở rộng nhận NO-BREAK SPACE U+00A0.
7. `\X` tách `A`, `e + dấu sắc` và `🇻🇳` thành 3 cụm. `\b{g}` tìm được hai ranh giới của một cụm `e + dấu sắc` (đầu và cuối).

**Kiểm tra giao diện:** Chuỗi `segmentsText` chứa `e` và **combining acute accent** thật; nếu font hoặc nền tảng hiển thị khác đi, vẫn nên dùng mã Unicode/`equals` trong test để xác nhận nội dung.

## 9. Cắt chuỗi an toàn theo số grapheme: tránh cắt vào giữa dấu hoặc emoji

Một lỗi thực tế là giới hạn nội dung nhập hoặc tạo preview bằng:

~~~java
String preview = input.substring(0, maxCharacters);
~~~

`substring` dùng **chỉ số UTF-16 code units**. Lệnh này có thể cắt giữa **surrogate pair**, giữa chữ và combining mark, hoặc giữa các thành phần của một cụm emoji. Ngay cả khi dùng `codePoints()` để cắt theo code point, vẫn có thể chia một grapheme cluster thành nhiều phần.

Ví dụ đầy đủ thứ hai — tệp **GraphemePrefixDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemePrefixDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    static String firstClusters(String value, int limit) {
        if (limit < 0) {
            throw new IllegalArgumentException("limit must be nonnegative");
        }
        Matcher m = GRAPHEME.matcher(value);
        int end = 0;
        for (int i = 0; i < limit && m.find(); i++) {
            end = m.end();
        }
        return value.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A" + "e\u0301" + "🇻🇳";
        String two = firstClusters(text, 2);
        System.out.println("prefix=" + two);
        System.out.println("prefixLength=" + two.length());
        System.out.println("prefixCodePoints="
                + two.codePointCount(0, two.length()));
        System.out.println("zero=" + firstClusters(text, 0).isEmpty());
        System.out.println("all=" + firstClusters(text, 20).equals(text));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GraphemePrefixDemo.java
java GraphemePrefixDemo
~~~

Kết quả:

~~~text
prefix=Aé
prefixLength=3
prefixCodePoints=3
zero=true
all=true
~~~

**Cơ chế:** `Matcher.find()` tìm lần lượt từng `\X`. `Matcher.end()` trả **chỉ số UTF-16 ngay sau cụm**. Chỉ số này an toàn để sử dụng với `String.substring(0, end)` vì ranh giới đã được tìm theo grapheme. Nếu `limit=0`, kết quả rỗng; nếu `limit` lớn hơn số cụm có trong chuỗi, kết quả là toàn bộ chuỗi.

**Tối ưu:** Nếu chỉ cần tiền tố có `n` cụm, vòng lặp `Matcher.find()` như trên không phải tạo `List` chứa mọi cụm. Nếu cần *mọi* cụm để xử lý tiếp, `matcher.results().map(MatchResult::group).toList()` tiện lợi nhưng cấp phát danh sách theo số match; cân nhắc đặc điểm tải thực tế.

**Hợp đồng rõ ràng:** `limit` ở đây là **số extended grapheme clusters**, không phải giới hạn byte, code points, độ rộng hiển thị, ô giao diện hay số ký tự được cơ sở dữ liệu tính theo quy tắc riêng. Đừng gọi nó là “giới hạn 10 ký tự” nếu sản phẩm chưa định nghĩa từ “ký tự”.

## 10. Normalization không đồng nghĩa grapheme segmentation

Java hiện đại có `java.text.Normalizer` để chuẩn hóa Unicode:

~~~java
import java.text.Normalizer;

String composed = "\u00E9";
String decomposed = "e\u0301";

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(composed.equals(normalized)); // true
~~~

- **NFC:** chuẩn hóa canonical rồi tổ hợp khi có thể; hữu ích khi hệ thống muốn lưu/so sánh văn bản ở một dạng Unicode nhất quán.
- **NFD:** phân rã canonical; hữu ích khi cần phân tích dấu kết hợp theo quy trình xác định.
- **NFKC/NFKD:** chuẩn hóa có thêm tương đương tương thích, có thể biến đổi những khác biệt có ý nghĩa theo nghiệp vụ; không áp dụng hàng loạt khi chưa có chính sách dữ liệu.

**Hai công việc độc lập:**

- `Normalizer.normalize` giải quyết việc **nhiều dãy code points có thể tương đương canonical**.
- Regex `\X` giải quyết việc **tìm ranh giới extended grapheme clusters**.

Vì vậy `"é"` và `"e\u0301"` có thể cùng là **một grapheme cluster**, nhưng **chưa chắc bằng nhau theo `equals`**. Ngược lại, chuẩn hóa NFC không biến một chuỗi nhiều emoji thành một code point duy nhất. Với tìm kiếm Unicode, thường cần định nghĩa cả **cách normalize dữ liệu** và **cách phân đoạn/so khớp**.

Java `Pattern` còn có cờ `CANON_EQ` hỗ trợ canonical equivalence trong regex, nhưng có chi phí đáng kể và có thể tăng rủi ro dùng bộ nhớ; khi bài toán chỉ cần đối chiếu hai chuỗi theo một dạng canonical thống nhất, chuẩn hóa dữ liệu **có chủ đích** bằng `Normalizer` thường dễ kiểm soát và kiểm thử hơn.

**Tránh nhầm:** NFC không đồng nghĩa “loại dấu”, “đổi chữ hoa thành chữ thường”, “chống giả mạo Unicode” hay “chuẩn hóa mọi thứ trông giống nhau”.

## 11. `matches()`, `find()` và vị trí match trên Unicode

Một `Pattern` giống nhau có thể cho kết quả rất khác tùy cách sử dụng:

~~~java
Pattern letters = Pattern.compile("\\p{L}+");
String input = "Code: Hà Nội";

boolean entire = letters.matcher(input).matches(); // false
boolean contains = letters.matcher(input).find();   // true
~~~

- **`matches()`** yêu cầu regex khớp **toàn bộ vùng input**.
- **`find()`** tìm **một vùng con khớp**.
- **`Matcher.results()`** trả stream các match liên tiếp.
- **`Matcher.start()`/`end()`** trả **chỉ số UTF-16 code units**, không phải chỉ số grapheme.

Khi cần xác thực dữ liệu, `matches()` hoặc neo `^...$` theo ngữ nghĩa phù hợp có thể giúp tránh việc chấp nhận chuỗi chỉ vì **một đoạn nhỏ hợp lệ**. Tuy nhiên, anchor và chế độ dòng cũng có quy tắc riêng: nên chọn `matches()` khi yêu cầu chính xác là “toàn bộ input hợp lệ”.

Khi hiển thị vị trí lỗi trong giao diện, đừng mặc nhiên xem `start()/end()` là “vị trí ký tự thứ n theo mắt người”. Vị trí Java dựa trên UTF-16; chuyển đổi sang grapheme index nếu UI đòi đếm theo cụm người dùng nhìn thấy.

**Hiệu năng:** `Pattern.compile(...)` tạo mẫu regex có thể tái sử dụng; với regex cố định gọi nhiều lần, khai báo `private static final Pattern ...` giúp tránh biên dịch lặp. `Pattern.matches(regex, input)` là API ngắn gọn cho trường hợp ít dùng, nhưng không tối ưu bằng tái sử dụng mẫu khi chạy trong vòng lặp lớn.

## 12. Ứng dụng thực tế: xác thực, tìm kiếm và trải nghiệm nhập văn bản

### 12.1. Tên người và dữ liệu đa ngôn ngữ

Mẫu `[A-Za-z]+` bỏ sót chữ có dấu và nhiều hệ chữ. `\p{L}`, `\p{M}` và thuộc tính Script giúp bao quát Unicode. Nhưng **không có một regex ngắn nào xác thực đúng tên người cho mọi quốc gia**. Tên có thể chứa dấu cách, dấu nối, dấu nháy, chữ kết hợp và quy tắc ngôn ngữ cụ thể.

Với form nhập tên, nên xác định chính sách thực tế (giới hạn độ dài, ký tự điều khiển bị cấm, chấp nhận script nào, có cần trim hay NFC không) thay vì cấm mọi ký tự ngoài Latin ASCII.

### 12.2. Tìm kiếm có dấu và không dấu

Chuẩn hóa NFC trước khi lưu hoặc so sánh giúp giảm khác biệt giữa dạng composed/decomposed. **Tìm kiếm không phân biệt dấu** là yêu cầu khác: phải có quy tắc rõ việc phân rã, xử lý combining marks và những chữ **không** thể được biến đổi bằng cách xóa dấu đơn giản. Tránh áp dụng quy trình “xóa mọi `\p{M}`” một cách máy móc trên toàn bộ ngôn ngữ, vì có thể xóa những dấu mang nghĩa thiết yếu.

Khi yêu cầu phân loại theo ngôn ngữ, so sánh/lọc/sắp xếp theo locale, cân nhắc API ngôn ngữ như `Collator` hoặc bộ tìm kiếm có thiết kế Unicode thay vì chỉ dựa vào regex.

### 12.3. Cắt preview, SMS, ô nhập liệu và emoji

Nếu giao diện hứa “tối đa 20 ký tự người dùng nhìn thấy”, hãy cân nhắc đếm theo extended grapheme clusters bằng `\X` và xử lý UI tương thích. Nhưng giới hạn bytes của API, giới hạn UTF-16/code points của database hay kích thước payload vẫn cần kiểm tra riêng. Một grapheme cluster có thể gồm nhiều code points và rất nhiều bytes UTF-8.

### 12.4. Chuỗi bị trộn script và ký tự dễ gây nhầm lẫn

Regex `\p{L}+` có thể chấp nhận trộn chữ Latin, Cyrillic và Greek trong cùng một identifier. Đây là thuộc tính Unicode hợp lệ nhưng có thể không phù hợp với tên người dùng, miền hoặc mã định danh nhạy cảm. Với dữ liệu có rủi ro giả mạo bằng chữ đồng hình, cần thêm chính sách phát hiện *confusable/mixed-script* theo tiêu chuẩn Unicode Security; **regex thuộc tính đơn lẻ không đủ để bảo đảm an toàn**.

## 13. Những lỗi dễ mắc

1. **Viết `"\p{L}"` trong Java source.** Sai vì backslash phải escape ở tầng Java string. Đúng là `"\\p{L}"`.
2. **Dùng `[A-Za-z]` để nhận mọi chữ cái.** Sai với chữ có dấu, Greek, Cyrillic, Han và các hệ chữ khác.
3. **Cho rằng `\p{L}+` luôn nhận chữ có dấu ở dạng decomposed.** Dấu kết hợp có thể thuộc `\p{M}` và khiến `matches()` thất bại.
4. **Nhầm `Script` và `Block`.** U+1F00 là Greek script nhưng thuộc Greek Extended block.
5. **Dùng `\w` mặc định rồi tưởng đã hỗ trợ mọi Unicode.** Java mặc định giữ phạm vi ASCII cho `\w`; dùng `UNICODE_CHARACTER_CLASS` khi đúng yêu cầu.
6. **Dùng `(?u)` thay `(?U)` mà không hiểu khác biệt.** `(?u)` liên quan case folding, còn `(?U)` bật Unicode character classes.
7. **Dùng `String.length()` hoặc `codePoints().count()` để đếm số grapheme.** Chúng đếm đơn vị khác; dấu kết hợp, cờ và emoji ZWJ là phản ví dụ rõ ràng.
8. **Cắt `substring` ở một chỉ số bất kỳ rồi kỳ vọng không vỡ emoji.** Chỉ số là UTF-16 code units; phải xác định ranh giới phù hợp trước.
9. **Nhầm `\b` với `\b{g}`.** Một cái là ranh giới từ, một cái là ranh giới grapheme.
10. **Tin rằng `\X` kiểm tra một “ký tự hợp lệ” cho mọi nghiệp vụ.** Nó phân đoạn; nó không thực hiện xác thực domain, lọc ký tự điều khiển hoặc chống spoofing.
11. **Dùng `Normalizer.NFKC` cho mọi văn bản mà không có chính sách.** Chuẩn hóa tương thích có thể thay đổi phân biệt mang nghĩa đối với người dùng.
12. **Quên phiên bản Unicode/JDK khi test.** Những thuộc tính và quy tắc phân đoạn Unicode có thể thay đổi theo bản Unicode JDK hỗ trợ; nên chạy regression tests khi nâng JDK.
13. **Dùng `find()` khi muốn toàn bộ input phải hợp lệ.** `find()` có thể chỉ khớp một đoạn nhỏ; `matches()` kiểm tra toàn bộ.
14. **Đồng nhất độ rộng giao diện với số cụm `\X`.** Grapheme clusters không cho biết kích thước pixel, ô terminal hoặc số glyph hiển thị.

## 14. Checklist chọn công cụ

| Câu hỏi thực tế | Công cụ nên xem xét | Điều vẫn phải xác minh |
| --- | --- | --- |
| “Code point này là chữ Unicode?” | `\p{L}` hoặc `Character.isLetter` | Có cần cho phép dấu kết hợp `\p{M}` không? |
| “Nó thuộc hệ chữ Greek?” | `\p{sc=Greek}` | Có giới hạn nghiệp vụ về mixed script không? |
| “Nó nằm trong block Unicode nào?” | `\p{InGreek}` / `\p{InGreekExtended}` | Block có phải đại diện đủ cho script cần kiểm tra không? |
| “`\w`/`\d`/`\s` nhận Unicode?” | `Pattern.UNICODE_CHARACTER_CLASS` | Có những ký tự Unicode ngoài mong đợi không? |
| “Tôi muốn một cụm ký tự để cắt preview.” | `\X`; lấy `Matcher.end()` | UI/db/API giới hạn theo đơn vị nào? |
| “Tôi cần vị trí ranh giới cụm.” | `\b{g}` | Chỉ số nhận được là UTF-16 hay grapheme index? |
| “Hai chuỗi nhìn giống nhau có nên bằng nhau?” | `Normalizer.normalize(..., NFC)` theo chính sách | Canonical equivalence có phù hợp dữ liệu không? |
| “Regex phải khớp cả input.” | `Matcher.matches()` | Ký tự hợp lệ và độ dài domain đã được định nghĩa chưa? |

## 15. Bài tự luyện và tiêu chí đạt

**Bài 1 — Ba cách đếm.** Tính `length()`, `codePointCount()` và số match `\X` cho `"e\u0301"` và `"🇻🇳"`. **Đạt** khi giải thích kết quả lần lượt `2/2/1` và `4/2/1`; nêu được UTF-16, code point và grapheme khác nhau thế nào.

**Bài 2 — Chữ và dấu.** Dùng `\p{L}+` và `\p{L}\p{M}*` để kiểm tra chuỗi `"e\u0301"` bằng `matches()`. **Đạt** khi nêu `false` và `true`, rồi mô tả vì sao `M` cần thiết trong dạng decomposed.

**Bài 3 — Script/Block.** Thử U+1F00 với `\p{sc=Greek}`, `\p{InGreek}` và `\p{InGreekExtended}`. **Đạt** khi cho `true/false/true` và giải thích hai loại thuộc tính.

**Bài 4 — Bật Unicode mode.** Khớp `"Hà_Nội"` bằng `\w+` trước/sau khi bật `UNICODE_CHARACTER_CLASS`; sau đó thử U+00A0 với `\s+`. **Đạt** khi hiểu kết quả `false/true` và `false/true` theo cờ, đồng thời biết Unicode mode không có nghĩa dữ liệu hợp lệ theo domain.

**Bài 5 — Preview theo grapheme.** Cài đặt `firstClusters(String, int)` dựa trên `Pattern.compile("\\X")`, kiểm tra chuỗi `"A" + "e\u0301" + "🇻🇳"`. **Đạt** khi lấy hai cụm đầu tạo `"Ae\u0301"`, độ dài UTF-16 là 3, không cắt giữa dấu sắc hoặc cặp surrogate.

**Bài 6 — Normalization.** So sánh `"\u00E9"` và `"e\u0301"` bằng `equals()`, rồi chuẩn hóa dạng thứ hai về NFC. **Đạt** khi được `false` rồi `true`, và biết NFC không tự giải quyết case folding hay chữ đồng hình.

**Bài 7 — Matching và bảo trì.** Viết test phân biệt `find()` và `matches()` trên `"Code: Hà Nội"`; kiểm chứng các case Unicode khi nâng JDK. **Đạt** khi tránh coi một match con là bằng chứng toàn bộ đầu vào hợp lệ, ghi rõ mong đợi theo từng trường hợp.

## 16. Tài liệu chính thức

- [Oracle Java SE 25 — Pattern](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html): cú pháp `\p`, `\P`, script/block/category, `\X`, `\b{g}`, `UNICODE_CHARACTER_CLASS`, các cờ và `CANON_EQ`.
- [Oracle Java SE 25 — Matcher](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Matcher.html): `find()`, `matches()`, `results()`, chỉ số `start()/end()`.
- [Oracle Java SE 25 — Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html): NFC, NFD, NFKC, NFKD và tương đương Unicode.
- [Oracle Java SE 25 — String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `length()`, `codePointCount()`, `substring()`, Unicode trong Java.
- [Unicode UAX #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): cơ sở quy tắc extended grapheme cluster.
- [Unicode UAX #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): chuẩn hóa Unicode và ý nghĩa canonical/compatibility.
- [Unicode UTS #39 — Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/): bối cảnh về confusable và mixed-script khi xử lý định danh.

**Ghi nhớ:** `\p{...}` giúp hỏi **thuộc tính của code point**, còn `\X` giúp tìm **ranh giới của cụm grapheme**. `String.length()` và `Matcher.start()/end()` vẫn dùng **UTF-16 code units**. Khi ứng dụng cần xử lý văn bản Unicode đúng đắn, hãy lựa chọn rõ đơn vị đếm, ranh giới match, chính sách normalization và kiểm thử dữ liệu đa ngôn ngữ trên JDK thực tế.
