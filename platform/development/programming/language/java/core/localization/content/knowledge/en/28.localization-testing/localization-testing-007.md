# Kiểm thử dấu kết hợp, emoji và biến đổi hoa–thường trong Java

Một hệ thống có thể xử lý đúng chuỗi `"Hello"` nhưng gặp lỗi với tiếng Việt có dấu, emoji, chữ `I` tiếng Thổ Nhĩ Kỳ hoặc chữ `ß` tiếng Đức. Những lỗi Unicode thường không phải do **Java không hỗ trợ Unicode** mà do ứng dụng chọn sai đơn vị đếm hoặc áp dụng sai quy tắc biến đổi: cắt theo từng `char`, cho rằng `String.length()` là số chữ nhìn thấy, hạ chữ thường theo locale mặc định, hoặc so hai chuỗi trông giống nhau bằng `equals` rồi mặc định chúng phải giống nhau ở mức mã hóa.

Bài Knowledge thuộc nhóm **Kiểm thử và lỗi** trong module **Java core - localization**, tập trung vào cách thiết kế kiểm thử **dấu kết hợp, emoji và biến đổi chữ hoa–thường** bằng **Java 17+**. Các ví dụ chạy độc lập với JDK, có những khẳng định kết quả ổn định; những chỗ phụ thuộc phiên bản Unicode/JDK, font hoặc locale được chỉ rõ thay vì coi mọi máy hiển thị và phân đoạn như nhau.

**Nguyên tắc:** phân biệt ít nhất năm tầng: byte UTF-8, đơn vị mã UTF-16 (`char`), Unicode code point, *extended grapheme cluster* (cụm ký tự mà người dùng thường nhìn như một đơn vị), và phép so sánh/biến đổi theo **ngữ nghĩa từng trường dữ liệu**. Phép thử đúng phải nói rõ đang kiểm tra tầng nào.

## 1. Một chữ hiển thị không nhất thiết là một char Java

Java `String` cung cấp API dựa trên **UTF-16 code units**. `String.length()` trả số đơn vị mã `char`, không phải số Unicode code point và càng không phải số “ký tự” theo cảm nhận người dùng.

| Văn bản minh họa | Cấu tạo Unicode | `String.length()` | Số code point | Ghi chú |
| --- | --- | ---: | ---: | --- |
| `A` | U+0041 | 1 | 1 | ASCII đơn giản |
| `é` dựng sẵn | U+00E9 | 1 | 1 | Precomposed |
| `e◌́` (e + dấu sắc kết hợp) | U+0065, U+0301 | 2 | 2 | Thường hiển thị gần như một chữ `é` |
| `😀` | U+1F600 | 2 | 1 | Emoji ngoài BMP, surrogate pair |
| `✈️` | U+2708, U+FE0F | 2 | 2 | Variation selector có thể chọn trình bày emoji |
| `👩‍💻` | U+1F469, U+200D, U+1F4BB | 5 | 3 | Emoji ZWJ sequence |
| `🇻🇳` | U+1F1FB, U+1F1F3 | 4 | 2 | Cặp regional indicators |

Độ dài **grapheme cluster** thường là 1 đối với từng chuỗi minh họa trong bảng, nhưng tiêu chuẩn phân đoạn Unicode và dữ liệu phiên bản của runtime mới là cơ sở xác định, không phải sự xuất hiện của một glyph trên màn hình. Font hoặc platform có thể hiển thị emoji ZWJ thành một hình ghép hoặc nhiều hình riêng, trong khi chuỗi code points không đổi.

**Không dùng `substring(i, i + 1)` để lấy một ký tự nhìn thấy**. Một nửa surrogate hoặc dấu kết hợp đơn lẻ có thể thành nội dung rời rạc, thậm chí không thể encode như Unicode scalar value hợp lệ.

## 2. Dấu dựng sẵn và dấu kết hợp: hai chuỗi trông giống nhau

Một chữ có dấu có thể được biểu diễn theo nhiều cách canonically equivalent:

- Dựng sẵn (*precomposed*): `"\u00E9"` gồm U+00E9.
- Phân rã (*decomposed*): `"e\u0301"` gồm U+0065 và dấu kết hợp U+0301.

Nhiều font trình bày hai biểu diễn gần giống nhau, nhưng:

```text
String.equals(...)             -> false
String.length()                -> 1 và 2
codePointCount(...)            -> 1 và 2
UTF-8 bytes                    -> C3 A9 và 65 CC 81
Normalizer.normalize(..., NFC) -> chuỗi bằng nhau
```

Điều này đặc biệt quan trọng với văn bản tiếng Việt, nơi các nguyên âm có thể đi cùng nhiều dấu hoặc thanh điệu. Không suy luận “người dùng nhìn giống nhau” là dữ liệu **byte-for-byte** giống nhau, và cũng không tự thay đổi mọi chuỗi nếu chúng là token, chữ ký hoặc dữ liệu yêu cầu bảo toàn byte.

### Canonical và compatibility normalization

`java.text.Normalizer` hỗ trợ:

| Form | Ý nghĩa |
| --- | --- |
| `NFC` | Canonical decomposition rồi composition |
| `NFD` | Canonical decomposition |
| `NFKC` | Compatibility decomposition rồi composition |
| `NFKD` | Compatibility decomposition |

`NFC`/`NFD` xử lý **canonical equivalence**; `NFKC`/`NFKD` còn có thể hợp nhất một số ký tự tương thích như chữ fullwidth hoặc ký hiệu được trình bày đặc biệt. Vì vậy, `NFKC` **có thể làm mất khác biệt có ý nghĩa** ở một số trường dữ liệu; không dùng nó như một phép “làm sạch” mặc định trên tên người, password và dữ liệu pháp lý.

### Ví dụ 1 — CanonicalNormalizationDemo.java

```java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CanonicalNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Raw equals: "
                + composed.equals(decomposed));
        System.out.println("Lengths: "
                + composed.length() + "/" + decomposed.length());
        System.out.println("UTF-8 bytes equal: "
                + Arrays.equals(
                        composed.getBytes(StandardCharsets.UTF_8),
                        decomposed.getBytes(StandardCharsets.UTF_8)));

        String a = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String b = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: " + a.equals(b));
        System.out.println("NFC idempotent: "
                + a.equals(Normalizer.normalize(
                        a, Normalizer.Form.NFC)));
        System.out.println("NFKC fullwidth A: "
                + Normalizer.normalize(
                        "\uFF21", Normalizer.Form.NFKC)
                        .equals("A"));
    }
}
```

```bash
javac -encoding UTF-8 CanonicalNormalizationDemo.java
java CanonicalNormalizationDemo
```

Stdout:

```text
Raw equals: false
Lengths: 1/2
UTF-8 bytes equal: false
NFC equals: true
NFC idempotent: true
NFKC fullwidth A: true
```

**Kiểm thử quan trọng:** Unicode normalization phải được áp dụng **theo hợp đồng trường dữ liệu**. Với text tìm kiếm, có thể tạo index canonical riêng; với một access token hoặc chữ ký trên byte, **không** tự normalize dữ liệu vì có thể phá giá trị cần xác thực.

## 3. String.length, codePointCount và offsetByCodePoints

Một surrogate pair hợp lệ biểu diễn một code point ngoài Basic Multilingual Plane. Ví dụ chuỗi `"A😀B"`:

```text
Chữ thấy được:      A       😀       B
UTF-16 positions:   0  1  2  3  4
Code units:         A  high low B
Code-point index:   0     1     2
```

Offset `2` là vị trí giữa high surrogate và low surrogate của emoji, **không phải vị trí được chọn để cắt emoji**. Sau hai code points tính từ đầu, offset UTF-16 là **3**, không phải 2.

Các API:

- `length()`: số **UTF-16 code units**.
- `codePointCount(begin, end)`: số code points được Java tính trong dải UTF-16, kể cả việc surrogate không ghép cặp được tính riêng nếu đầu vào bất thường.
- `offsetByCodePoints(index, count)`: chuyển dịch theo code points, trả về **UTF-16 offset**.
- `codePoints()`: duyệt các giá trị code point từ chuỗi.
- `charAt(i)`: một UTF-16 code unit, có thể chỉ là **một nửa** surrogate pair.
- `substring(begin, end)`: cắt bằng **UTF-16 offsets** trong khoảng nửa mở `[begin,end)`.

### Ví dụ 2 — CodePointBoundaryDemo.java

```java
import java.nio.charset.StandardCharsets;

public class CodePointBoundaryDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 byte length: "
                + text.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("After 2 code points: "
                + text.offsetByCodePoints(0, 2));
        System.out.println("High surrogate: "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("Low surrogate: "
                + Character.isLowSurrogate(text.charAt(2)));
        System.out.println("Emoji slice length: "
                + text.substring(1, 3).length());
    }
}
```

```bash
javac -encoding UTF-8 CodePointBoundaryDemo.java
java CodePointBoundaryDemo
```

Stdout:

```text
UTF-16 length: 4
Code points: 3
UTF-8 byte length: 6
After 2 code points: 3
High surrogate: true
Low surrogate: true
Emoji slice length: 2
```

Kết quả `UTF-8 byte length: 6` gồm ASCII `A` (1 byte), emoji (4 byte), ASCII `B` (1 byte). Độ dài được tính theo encoding; **không thể dùng `String.length()` để đặt byte length cho HTTP**.

## 4. Grapheme cluster: đơn vị người dùng mong muốn chọn, xóa hay di chuyển

Hai Unicode code points có thể là một cụm chữ. Chuỗi `"e\u0301"` có code point `e` và combining acute accent, thường là một **extended grapheme cluster**. Emoji ZWJ hoặc cờ từ hai regional indicators cũng thường là một cluster.

Java có ít nhất hai công cụ liên quan:

- `BreakIterator.getCharacterInstance(locale)` để tìm ranh giới ký tự cho tác vụ text; hành vi và hỗ trợ emoji phức tạp còn phụ thuộc phiên bản Unicode/JDK/provider.
- `java.util.regex.Pattern` với `\\X` (Java 17 hỗ trợ) để match extended grapheme cluster theo quy tắc Unicode được runtime triển khai.

**Không đồng nhất “extended grapheme cluster” với mọi glyph được renderer vẽ**. Một số font sẽ gộp nhiều code points thành glyph, hoặc tách emoji thành nhiều hình tùy platform. Segmentation là một thuật toán về văn bản, còn rendering thuộc font/shaping/rendering engine.

### Ví dụ 3 — GraphemeBoundaryDemo.java

```java
import java.text.BreakIterator;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeBoundaryDemo {
    private static int countGraphemes(String text) {
        Matcher matcher = Pattern.compile("\\X").matcher(text);
        int count = 0;
        while (matcher.find()) {
            count++;
        }
        return count;
    }

    public static void main(String[] args) {
        String text = "e\u0301";

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("Regex clusters: "
                + countGraphemes(text));
        System.out.println("Boundary at 1: "
                + it.isBoundary(1));
        System.out.println("Following 0: " + it.following(0));
        System.out.println("Preceding 2: " + it.preceding(2));
    }
}
```

```bash
javac -encoding UTF-8 GraphemeBoundaryDemo.java
java GraphemeBoundaryDemo
```

Stdout với ví dụ dấu kết hợp cơ bản trên Java 17:

```text
UTF-16 length: 2
Code points: 2
Regex clusters: 1
Boundary at 1: false
Following 0: 2
Preceding 2: 0
```

Nếu ứng dụng cần xử lý toàn bộ emoji hiện đại, hãy xây **test corpus theo version Unicode**; không chỉ dùng một ví dụ `e + dấu` rồi suy ra runtime hỗ trợ đủ mọi sequence. Khi cần mức tương thích chặt chẽ giữa client và server khác runtime, xem xét thư viện segmentation có dữ liệu Unicode được khóa phiên bản.

## 5. Emoji thường là chuỗi nhiều code points

Một emoji có thể là:

- **Một code point ngoài BMP:** `😀` (U+1F600; UTF-16 dài 2).
- **Emoji + variation selector:** `✈️` = U+2708 + U+FE0F.
- **Emoji + skin tone modifier:** một số emoji có thêm modifier ở range U+1F3FB–U+1F3FF.
- **ZWJ sequence:** `👩‍💻` = WOMAN + ZERO WIDTH JOINER + PERSONAL COMPUTER.
- **Flag sequence:** `🇻🇳` = cặp regional indicator letters.
- **Keycap sequence:** có thể là digit, variation selector và combining enclosing keycap.

Không có quy tắc “một emoji = hai `char`”. Chỉ một số code point emoji đơn nằm ngoài BMP mới có hai UTF-16 units; emoji sequence có thể dài hơn nhiều.

### Ví dụ 4 — EmojiSequenceDemo.java

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class EmojiSequenceDemo {
    private static int clusters(String text) {
        Matcher m = Pattern.compile("\\X").matcher(text);
        int n = 0;
        while (m.find()) {
            n++;
        }
        return n;
    }

    public static void main(String[] args) {
        String grin = "\uD83D\uDE00";
        String airplane = "\u2708\uFE0F";
        String developer = "\uD83D\uDC69\u200D\uD83D\uDCBB";

        System.out.println("Grin units/codepoints: "
                + grin.length() + "/"
                + grin.codePointCount(0, grin.length()));
        System.out.println("Airplane units/codepoints: "
                + airplane.length() + "/"
                + airplane.codePointCount(0, airplane.length()));
        System.out.println("Developer units/codepoints: "
                + developer.length() + "/"
                + developer.codePointCount(0, developer.length()));
        System.out.println("Grin clusters: " + clusters(grin));
        System.out.println("Airplane clusters: "
                + clusters(airplane));
        // So sánh kết quả với Unicode version của runtime.
        System.out.println("Developer clusters: "
                + clusters(developer));
    }
}
```

```bash
javac -encoding UTF-8 EmojiSequenceDemo.java
java EmojiSequenceDemo
```

Đối với Java 17 có triển khai `\\X` hỗ trợ chuỗi ZWJ minh họa, kết quả thường là:

```text
Grin units/codepoints: 2/1
Airplane units/codepoints: 2/2
Developer units/codepoints: 5/3
Grin clusters: 1
Airplane clusters: 1
Developer clusters: 1
```

Phần **units/codepoints** không phụ thuộc renderer. `Developer clusters` được tính theo Unicode grapheme algorithm mà **JDK đang dùng**; khi kiểm thử nhiều JDK/Unicode versions phải xác nhận trên runtime mục tiêu thay vì dùng một snapshot cho mọi phiên bản trong tương lai. Một emoji có thể hiển thị thành các hình rời trên terminal cũ, nhưng điều đó không chứng minh chuỗi đã hỏng.

### Tại sao chỉ đếm code points vẫn chưa đủ?

`offsetByCodePoints` có thể tránh cắt surrogate pair, nhưng nó **vẫn có thể cắt giữa một ký tự cơ sở và dấu kết hợp**, hoặc giữa các code points của một emoji ZWJ sequence. Khi làm nút “xóa một ký tự”, thao tác selection/caret hoặc giới hạn số ký tự mà người dùng thấy, hãy xác định chính xác cần **grapheme segmentation** hay đếm code points.

## 6. Dấu kết hợp tiếng Việt: kiểm thử theo nhiều thứ tự và biểu diễn

Nhiều chữ tiếng Việt có thể gồm base letter, dấu phụ âm/chính và dấu thanh. Unicode có quy tắc **canonical combining class** giúp chuẩn hóa thứ tự một số dấu kết hợp. Nhưng không phải mọi phép hoán đổi code points đều tương đương; chỉ kết luận tương đương khi **Normalizer** hoặc dữ liệu Unicode xác nhận.

Bộ kiểm thử nên bao gồm:

1. Chữ precomposed và decomposed canonically equivalent.
2. Chuỗi nhiều combining marks với thứ tự thực tế khác nhau nếu canonically equivalent.
3. Dấu kết hợp xuất hiện ở đầu chuỗi (không có base): chính sách input UI cần rõ.
4. Các chữ có dấu ở đầu/cuối segment và sát emoji.
5. NFC/NFD round-trip theo canonical equivalence; tính idempotence.
6. Mã khóa/identifier không được thay đổi tùy tiện ngoài chính sách.
7. Kiểm tra UTF-8 round-trip cho chuỗi well-formed sau chuẩn hóa.
8. Không chỉ so hiển thị screenshot; kiểm tra code points và byte khi điều tra lỗi.

### Mẫu kiểm tra tính chất chuẩn hóa

Với mọi chuỗi Unicode hợp lệ `s` trong miền ứng dụng:

```text
NFC(NFC(s)) == NFC(s)
NFD(NFD(s)) == NFD(s)
NFC(s) canonically equivalent s
NFD(s) canonically equivalent s
```

Hai dòng đầu kiểm tra **idempotence**. Hai dòng sau không có nghĩa `NFC(s).equals(s)` luôn đúng; ngược lại, mục đích normalize là có thể thay đổi chuỗi biểu diễn nhưng giữ **canonical equivalence**. Lưu ý với chuỗi chứa surrogate đơn lẻ không hợp lệ, chính sách nhập và xử lý encoding phải được thử riêng.

## 7. Biến đổi hoa/thường có thể thay đổi độ dài chuỗi

Một sai lầm phổ biến là xem `toUpperCase`/`toLowerCase` như phép thay từng ký tự theo tỷ lệ 1:1. Trong Unicode, case mapping có thể **thay đổi số code points và số UTF-16 units**.

Ví dụ:

- `"Straße"` được `toUpperCase(Locale.ROOT)` chuyển thành `"STRASSE"`; `ß` được ánh xạ thành `SS` trong phép String uppercase.
- `"\u0130"` (LATIN CAPITAL LETTER I WITH DOT ABOVE) chuyển xuống lower-case bằng `Locale.ROOT` có thể thành `i` + dấu chấm kết hợp U+0307.
- Trong tiếng Thổ Nhĩ Kỳ, chữ `I` uppercase không dấu chấm chuyển thành `ı` lower-case (dotless i), khác chữ `i` ASCII.
- Một số chữ Hy Lạp có case mapping phụ thuộc vị trí trong từ; không viết logic ngôn ngữ học bằng `Character.toLowerCase(char)` thay cho `String.toLowerCase(Locale)`.

**`Character.toUpperCase(int codePoint)`** thường trả một code point và không biểu diễn được tất cả phép mở rộng thành nhiều ký tự; `String.toUpperCase(Locale)` mới hỗ trợ ánh xạ chuỗi theo ngữ cảnh. Dù vậy, `String.toLowerCase(Locale.ROOT)` **không phải phép Unicode full case folding hoàn chỉnh** cho mọi bài toán matching.

### Ví dụ 5 — CaseExpansionDemo.java

```java
import java.util.Locale;

public class CaseExpansionDemo {
    public static void main(String[] args) {
        String german = "Stra\u00DFe";
        String upper = german.toUpperCase(Locale.ROOT);
        String dottedI = "\u0130";
        String rootLower = dottedI.toLowerCase(Locale.ROOT);

        System.out.println("German upper: " + upper);
        System.out.println("German length: "
                + german.length() + " -> " + upper.length());
        System.out.println("Ignore case equals: "
                + german.equalsIgnoreCase("STRASSE"));
        System.out.println("Uppercase equals: "
                + upper.equals("STRASSE"));
        System.out.println("Dotted I ROOT lower length: "
                + rootLower.length());
        System.out.println("Dotted I ROOT has combining dot: "
                + rootLower.equals("i\u0307"));
    }
}
```

```bash
javac -encoding UTF-8 CaseExpansionDemo.java
java CaseExpansionDemo
```

Stdout với Java 17:

```text
German upper: STRASSE
German length: 6 -> 7
Ignore case equals: false
Uppercase equals: true
Dotted I ROOT lower length: 2
Dotted I ROOT has combining dot: true
```

**Điểm không được hiểu sai:** `"Straße".equalsIgnoreCase("STRASSE")` là `false`, nhưng so hai chuỗi sau uppercase ROOT trong trường hợp này là `true`. **Không kết luận** uppercase rồi equals là chiến lược full Unicode case folding chuẩn. Đây chỉ là phép thử phản ví dụ cho việc coi tất cả API case-insensitive là tương đương.

## 8. Locale mặc định làm test không ổn định: Turkish I

`String.toLowerCase()` không tham số dùng `Locale.getDefault()`. Vì thế cùng chuỗi `"TITLE"` có thể tạo khóa khác nếu chạy dưới default locale `en-US` và `tr-TR`.

Chính sách được khuyến nghị:

- Với **mã máy đọc ASCII** do ứng dụng định nghĩa, kiểm tra tập ký tự rồi chuyển case theo `Locale.ROOT` nếu hợp đồng yêu cầu.
- Với **văn bản hiển thị theo ngôn ngữ**, truyền `Locale` đúng của người dùng; không ép ROOT khi cần quy tắc chữ viết của tiếng Thổ Nhĩ Kỳ hoặc ngôn ngữ khác.
- Với **password, token, signature**, không tự đổi case ngoài hợp đồng xác thực.
- Với **username Unicode**, không coi ROOT lowercase là toàn bộ profile an toàn; cần xác định normalization, case folding, confusables, uniqueness và phiên bản Unicode.
- Không thay `Locale.setDefault` giữa các test chạy song song hoặc giữa các HTTP request.

### Ví dụ 6 — TurkishCaseDemo.java

```java
import java.util.Locale;

public class TurkishCaseDemo {
    public static void main(String[] args) {
        Locale tr = Locale.forLanguageTag("tr-TR");
        String source = "TITLE";

        String root = source.toLowerCase(Locale.ROOT);
        String turkish = source.toLowerCase(tr);

        System.out.println("ROOT lower: " + root);
        System.out.println("Turkish equals title: "
                + turkish.equals("title"));
        System.out.println("Turkish has dotless i: "
                + turkish.contains("\u0131"));
        System.out.println("Different keys: "
                + !root.equals(turkish));

        System.out.println("Capital dotted I -> Turkish i: "
                + "\u0130".toLowerCase(tr).equals("i"));
    }
}
```

```bash
javac -encoding UTF-8 TurkishCaseDemo.java
java TurkishCaseDemo
```

Stdout:

```text
ROOT lower: title
Turkish equals title: false
Turkish has dotless i: true
Different keys: true
Capital dotted I -> Turkish i: true
```

Các kết quả này không phụ thuộc **default locale của máy chạy** vì chương trình truyền locale tường minh. Điều cần kiểm tra trong code ứng dụng không chỉ là việc có gọi `toLowerCase` hay không, mà là **dùng locale nào, với trường dữ liệu nào và mục đích gì**.

## 9. equals, equalsIgnoreCase, Normalizer và Collator kiểm tra điều gì?

| Công cụ | Câu hỏi được trả lời | Không nên dùng thay cho |
| --- | --- | --- |
| `String.equals` | Hai dãy UTF-16 có cùng giá trị không? | Canonical Unicode equivalence hoặc so theo ngôn ngữ |
| `equalsIgnoreCase` | Case-insensitive theo quy tắc của `String` | Locale-aware collation hoặc Unicode full case folding |
| `Normalizer.normalize(..., NFC)` | Cùng một dạng Unicode canonical để so/lưu theo policy? | Đổi hoa/thường |
| `toLowerCase(Locale.ROOT)` | Tạo lowercase độc lập locale mặc định | Full identifier/security profile |
| `Collator.getInstance(locale)` | So/sắp xếp văn bản theo quy tắc ngôn ngữ | Exact token, chữ ký, khóa định danh |
| `Pattern.compile("\\X")` | Tìm các grapheme clusters theo thuật toán runtime | Đếm byte/Unicode code point |
| `BreakIterator.getCharacterInstance` | Tìm biên text trong triển khai JDK | Parser từ ngữ chuyên biệt hoặc UI renderer |

**Tách bốn hợp đồng:**

1. **Display:** giữ cách viết người dùng nhập (ví dụ tên người), chỉ đổi case khi thiết kế UI cần.
2. **Search:** có thể case-insensitive/diacritic-insensitive theo locale và công cụ tìm kiếm; lưu bản gốc riêng.
3. **Identity:** canonical key theo quy tắc rõ ràng, test va chạm; không tùy tiện dùng collation của JDK thay quy tắc username.
4. **Exact bytes/token:** không normalization/case conversion nếu giao thức không cho phép.

Ví dụ cùng chữ `é` có thể được so canonically equivalent sau NFC nhưng vẫn khác byte đầu vào. Một password không nên bị “sửa” ngầm chỉ để pass phép so chuỗi.

## 10. Regex với Unicode: không nhầm \w, . và \X

Các regex pattern có semantics riêng:

- `.` thông thường khớp các code point Unicode theo quy tắc regex Java (ngoại lệ line terminators theo flags); **không bảo đảm khớp một grapheme cluster**. Dùng `\\X` khi thực sự cần segment dạng extended grapheme cluster.
- `\\w` và các character classes như `[A-Za-z]` không có cùng ý nghĩa. `[A-Za-z]` chỉ cho ASCII Latin; `\\w` mặc định có quy tắc riêng và có thể mở rộng khi bật `UNICODE_CHARACTER_CLASS`. Không dùng chúng như “mọi chữ viết của mọi ngôn ngữ” khi chưa định nghĩa.
- `\\p{L}` nhận Unicode **Letter** theo dữ liệu Unicode của runtime, nhưng dấu kết hợp thuộc các loại Mark; một tên có dấu ở dạng decomposed có thể cần xử lý thêm marks hoặc normalize trước theo policy.
- `Pattern.CASE_INSENSITIVE` không tương đương full locale-aware mapping; với `UNICODE_CASE` có thêm Unicode-aware case folding theo quy tắc regex, nhưng không thay thế chính sách identity.
- `Pattern.CANON_EQ` có hỗ trợ canonical equivalence và chi phí/semantics riêng; nếu cần canonicalization cho dữ liệu lớn hoặc khóa, cân nhắc normalize tường minh và kiểm thử performance.

### Chương trình 7 — RegexUnicodeDemo.java

```java
import java.util.regex.Pattern;

public class RegexUnicodeDemo {
    public static void main(String[] args) {
        String decomposed = "e\u0301";
        String emoji = "\uD83D\uDE00";

        System.out.println("ASCII-only letters match: "
                + Pattern.matches("[A-Za-z]+", decomposed));
        System.out.println("Unicode letter then mark: "
                + Pattern.matches("\\p{L}\\p{M}", decomposed));
        System.out.println("One grapheme cluster: "
                + Pattern.matches("\\X", decomposed));
        System.out.println("Emoji one grapheme: "
                + Pattern.matches("\\X", emoji));
    }
}
```

```bash
javac -encoding UTF-8 RegexUnicodeDemo.java
java RegexUnicodeDemo
```

Stdout:

```text
ASCII-only letters match: false
Unicode letter then mark: true
One grapheme cluster: true
Emoji one grapheme: true
```

Đây là kiểm thử **ý nghĩa regex**, không phải kiểm thử xem font có hiện emoji hay không. Nếu sản phẩm yêu cầu tên người có tất cả Unicode letter/marks hợp lệ, hãy định nghĩa rõ thêm chính sách spacing, punctuation, chuẩn hóa và bảo mật; regex hai token trên chỉ minh họa tính khác biệt giữa `Letter` và `Mark`.

## 11. UTF-8 round-trip và surrogate đơn lẻ không hợp lệ

Một chuỗi Java có thể chứa **surrogate đơn lẻ** (unpaired surrogate), dù giá trị đó không phải Unicode scalar value hợp lệ để encode thành UTF-8 chuẩn. Ví dụ `"\uD83D"` chỉ là high surrogate không có low surrogate.

Các API tiện lợi như `String.getBytes(StandardCharsets.UTF_8)` có thể thay dữ liệu malformed bằng ký tự/byte thay thế. Đối với dữ liệu cần bảo toàn chính xác, test không thể chỉ nhìn xem hàm có ném lỗi hay không.

Dùng `CharsetEncoder`/`CharsetDecoder` với `CodingErrorAction.REPORT` khi contract yêu cầu từ chối dữ liệu không hợp lệ. Byte malformed và ký tự unmappable là hai dạng lỗi khác nhau:

- **Malformed UTF-8 bytes:** ví dụ `C3 28`, không có continuation byte hợp lệ.
- **Malformed UTF-16 string:** ví dụ high surrogate đứng một mình.
- **Unmappable character:** ví dụ encode emoji sang ISO-8859-1.

### Chương trình 8 — StrictUnicodeEncodingDemo.java

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUnicodeEncodingDemo {
    public static void main(String[] args) {
        byte[] badUtf8 = {(byte) 0xC3, (byte) 0x28};
        String replacement = new String(
                badUtf8, StandardCharsets.UTF_8);

        System.out.println("Replacement present: "
                + replacement.contains("\uFFFD"));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(badUtf8));
            System.out.println("Unexpected decoded bytes");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict decode rejected");
        }

        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap("\uD83D"));
            System.out.println("Unexpected encoded surrogate");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict encode rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 StrictUnicodeEncodingDemo.java
java StrictUnicodeEncodingDemo
```

Stdout:

```text
Replacement present: true
Strict decode rejected
Strict encode rejected
```

**Không kiểm tra “chuỗi có U+FFFD hay không” như phép xác định nguồn byte malformed tổng quát:** ký tự `�` có thể xuất hiện hợp lệ trong input. Muốn biết decoder có gặp byte lỗi hay không, dùng chính sách `REPORT` và bắt `CharacterCodingException`.

## 12. Một bộ regression test có assertion, không chỉ in thử

Để test thực sự tự phát hiện lỗi, nên dùng JUnit hoặc một helper ném `AssertionError`. `assert` trong Java **mặc định có thể tắt** nếu không bật `-ea`, do đó ví dụ dưới đây dùng `check` chạy bất kể JVM flags.

### Chương trình 9 — UnicodeRegressionTest.java

```java
import java.text.BreakIterator;
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnicodeRegressionTest {
    private static int checked = 0;

    private static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
        checked++;
    }

    public static void main(String[] args) {
        String pre = "\u00E9";
        String de = "e\u0301";
        String emoji = "\uD83D\uDE00";
        String whole = "A" + emoji + "B";

        check(!pre.equals(de), "raw representations");
        check(Normalizer.normalize(pre, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(
                        de, Normalizer.Form.NFC)), "canonical NFC");
        check(Normalizer.normalize(de, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(
                        Normalizer.normalize(
                                de, Normalizer.Form.NFC),
                        Normalizer.Form.NFC)), "NFC idempotent");

        check(whole.length() == 4, "UTF-16 units");
        check(whole.codePointCount(0, whole.length()) == 3,
                "code points");
        check(whole.offsetByCodePoints(0, 2) == 3,
                "code point offset");

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(de);
        check(!it.isBoundary(1), "combining mark boundary");
        check(Pattern.matches("\\X", de),
                "single grapheme cluster");
        check("\u00DF".toUpperCase(Locale.ROOT)
                .equals("SS"), "case expansion");
        check("I".toLowerCase(Locale.ROOT)
                .equals("i"), "locale-neutral ASCII");
        check("I".toLowerCase(
                Locale.forLanguageTag("tr-TR"))
                .equals("\u0131"), "Turkish case");

        System.out.println("Passed checks: " + checked);
    }
}
```

```bash
javac -encoding UTF-8 UnicodeRegressionTest.java
java UnicodeRegressionTest
```

Stdout khi tất cả assertion thành công:

```text
Passed checks: 11
```

Chương trình này kiểm tra **11 điều kiện** và tự dừng khi điều kiện không thỏa. Các phép thử được chọn cho Java 17 với những trường hợp Unicode cơ bản, tránh phụ thuộc vị trí cursor trên màn hình. Với ứng dụng sản xuất, mở rộng thành JUnit parameterized tests cho nhiều script/locale và đặt bộ test cạnh phiên bản dữ liệu Unicode được hỗ trợ.

## 13. Property-based testing: tạo dữ liệu Unicode hợp lệ có seed cố định

Test với một vài chuỗi cố định rất hữu ích để bảo vệ các lỗi đã biết, nhưng không đủ để phủ các tổ hợp base letter, marks, emoji, ZWJ và case mapping. Property-based testing có thể sinh nhiều chuỗi rồi kiểm tra những bất biến hợp lệ.

**Bất biến nên kiểm tra:**

- `NFC(NFC(s)) == NFC(s)`.
- `NFD(NFD(s)) == NFD(s)`.
- `NFC(s)` và `NFD(s)` có canonical equivalence phù hợp.
- Với chuỗi well-formed, UTF-8 encode/decode bằng cùng charset bảo toàn `String.equals`.
- Một chuỗi được tách bằng grapheme segments phải **ghép lại đúng chuỗi gốc**; tránh mất code units.
- Mọi offset từ các segments phải nằm trong `0..length`; các đoạn không được chồng lên nhau.
- Sau một phép đổi case, không được giả định `length` và tập code points không đổi; test phải **cho phép expansion**.

**Không phải bất biến:**

- `s.toUpperCase(locale).toLowerCase(locale).equals(s)`: có thể sai do phép case mapping nhiều-một.
- `s.equalsIgnoreCase(t)` luôn bằng `NFC(s).equalsIgnoreCase(NFC(t))`: các quy tắc equivalence khác nhau, cần kiểm tra theo contract.
- “Có bao nhiêu code points thì có bấy nhiêu graphemes”: sai khi có marks/ZWJ.
- “Mọi emoji đều là một code point”: sai với nhiều emoji sequences.
- “NFKC không làm thay đổi ý nghĩa dữ liệu”: sai trong một số miền nghiệp vụ.

### Chương trình 10 — SeededUnicodePropertiesDemo.java

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Random;

public class SeededUnicodePropertiesDemo {
    private static void check(boolean okay) {
        if (!okay) {
            throw new AssertionError("Unicode property failed");
        }
    }

    public static void main(String[] args) {
        String[] atoms = {
                "a", "e", "\u0301", "\u00E9",
                "\uD83D\uDE00", "\u0130",
                "\u00DF", "\u200D", "\uFE0F"
        };
        Random random = new Random(271);
        int trials = 200;

        for (int i = 0; i < trials; i++) {
            StringBuilder input = new StringBuilder();
            int count = 1 + random.nextInt(8);
            for (int j = 0; j < count; j++) {
                input.append(atoms[random.nextInt(atoms.length)]);
            }
            String text = input.toString();

            String nfc = Normalizer.normalize(
                    text, Normalizer.Form.NFC);
            check(nfc.equals(Normalizer.normalize(
                    nfc, Normalizer.Form.NFC)));

            String nfd = Normalizer.normalize(
                    text, Normalizer.Form.NFD);
            check(nfd.equals(Normalizer.normalize(
                    nfd, Normalizer.Form.NFD)));

            byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
            check(text.equals(
                    new String(utf8, StandardCharsets.UTF_8)));
        }

        System.out.println("Passed trials: " + trials);
    }
}
```

```bash
javac -encoding UTF-8 SeededUnicodePropertiesDemo.java
java SeededUnicodePropertiesDemo
```

Stdout:

```text
Passed trials: 200
```

**Vì sao atoms được chọn vậy?** Mỗi atom là một chuỗi Unicode **well-formed**: emoji ở dạng surrogate pair hợp lệ, còn combining mark/ZWJ/variation selector dù đứng riêng cũng có code points hợp lệ. Chúng có thể tạo text khó hiển thị nhưng **không tạo surrogate lẻ**, nên UTF-8 round-trip là một property hợp lệ cho corpus này.

**Không nhầm random text với ngôn ngữ tự nhiên:** sinh ngẫu nhiên không thay thế test câu tiếng Việt, tên người, emoji sequences thông dụng hoặc test dữ liệu rìa từ báo lỗi production. Seed được cố định để có thể tái hiện trường hợp lỗi.

## 14. Kiểm thử cách cắt chuỗi không làm rơi dấu hoặc tách emoji

Đối với một text editor, chọn/xóa ký tự thường cần dựa trên **grapheme boundaries**, không phải số UTF-16 units. Với `Pattern.compile("\\X")`, có thể lấy từng match như một đoạn, nối lại phải bằng chuỗi ban đầu.

### Ví dụ 11 — GraphemeRoundTripDemo.java

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeRoundTripDemo {
    public static void main(String[] args) {
        String original = "A" + "e\u0301"
                + "\uD83D\uDE00" + "B";
        Matcher matcher = Pattern.compile("\\X").matcher(original);
        StringBuilder rebuilt = new StringBuilder();
        int segments = 0;

        while (matcher.find()) {
            rebuilt.append(matcher.group());
            segments++;
        }

        System.out.println("UTF-16 units: " + original.length());
        System.out.println("Code points: "
                + original.codePointCount(0, original.length()));
        System.out.println("Segments: " + segments);
        System.out.println("Round trip exact: "
                + original.contentEquals(rebuilt));
    }
}
```

```bash
javac -encoding UTF-8 GraphemeRoundTripDemo.java
java GraphemeRoundTripDemo
```

Stdout với thuật toán grapheme Java 17 cho chuỗi đơn giản:

```text
UTF-16 units: 6
Code points: 5
Segments: 4
Round trip exact: true
```

Đếm: `A` (1 unit), `e + dấu` (2 units), emoji (2 units), `B` (1 unit) → **6 UTF-16 units**; số code points **1 + 2 + 1 + 1 = 5**, nhưng có **4 grapheme clusters**.

Đối với emoji sequence ZWJ dài hơn, một số phiên bản JDK hoặc thuật toán segmentation có thể khác nhau: **kiểm thử với runtime thực tế, không lấy đúng số cụm của một máy làm hợp đồng chung vô thời hạn**.

## 15. So sánh theo locale: phân biệt tìm kiếm với định danh

Với nội dung ngôn ngữ tự nhiên, một chức năng tìm kiếm có thể muốn bỏ qua case hoặc dấu. `java.text.Collator` hỗ trợ so sánh theo `Locale`, có các mức nhạy:

- `PRIMARY` thường chỉ so khác biệt cơ bản; có thể bỏ qua case/accents tùy quy tắc locale.
- `SECONDARY` thường phân biệt dấu nhưng bỏ qua case trong nhiều locale.
- `TERTIARY` có thể phân biệt kiểu chữ và biến thể khác.
- `IDENTICAL` mức phân biệt sâu hơn, có liên quan canonical decomposition.

Đây là **nguyên tắc thường gặp**, không phải lời hứa mọi chữ có dấu đều bằng chữ không dấu trong mọi ngôn ngữ và provider. Tạo `Collator` riêng theo locale người dùng khi dùng cho sort/search, đồng thời kiểm tra kết quả trên các JDK/provider được hỗ trợ.

**Không dùng Collator làm bộ so sánh access token, chữ ký số hoặc uniqueness tự động của username**. Chúng cần chính sách định danh hoặc exact matching riêng, ổn định giữa các môi trường. Nếu ứng dụng dùng database collation, nó có thể khác Java `Collator` về Unicode/CLDR version; cần integration test thay vì suy diễn.

### Hợp đồng ví dụ cho bốn field

| Field | Chính sách có thể chấp nhận | Test phải có |
| --- | --- | --- |
| `displayName` | Giữ nguyên cách viết; có thể tạo NFC index nếu cần search | Precomposed/decomposed, casing đặc biệt |
| `username` ASCII case-insensitive | Validate ASCII, lower ROOT, unique key | `Lan`/`LAN` collision; Turkish locale |
| `password` | Không tự trim/normalize/change case ngoài hợp đồng xác thực | Khác nhau chỉ bởi case hoặc dấu |
| `accessToken` | So theo chuẩn token, thường case-sensitive | `aB` khác `ab` |
| `searchQuery` | Locale-sensitive search/collation theo nhu cầu | Accent, case, mark, Unicode versions |
| `filePath` | Theo chính sách filesystem thực tế | Không lower-case toàn bộ path |
| `apiFieldName` | Exact theo schema JSON | `userId` khác `userid` khi schema yêu cầu |
| `localizationKey` | Exact key trong ResourceBundle | Không tự hạ case khi lookup |

Chữ có dấu và emoji không phải dữ liệu “xấu” cần xóa cho mọi field. Ngược lại, dữ liệu có nguy cơ trộn script hoặc confusables trong **identifier** phải được xử lý bởi profile và luật bảo mật riêng, không chỉ bằng `Normalizer` hoặc `toLowerCase`.

## 16. Phép thử collision sau khi chuẩn hóa và đổi case

Hai input khác nhau có thể trở thành cùng khóa sau normalization/case conversion. Nếu database đã chứa cả hai trước khi đổi policy, migration không thể gộp mà không giải quyết chủ sở hữu.

Ví dụ:

```text
Raw 1: Lan_01
Raw 2: LAN_01
ASCII lowercase ROOT -> lan_01 cho cả hai
```

Tương tự, hai biểu diễn canonically equivalent như `"\u00E9"` và `"e\u0301"` sẽ có cùng NFC key. Đó có thể là hành vi mong muốn của search hoặc username, nhưng không thể coi đó là một quy tắc chung cho email/token/file name.

### Chương trình 12 — CanonicalCollisionDemo.java

```java
import java.text.Normalizer;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public class CanonicalCollisionDemo {
    private static String key(String text) {
        return Normalizer.normalize(
                text, Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String[] inputs = {
                "Lan_01", "LAN_01",
                "\u00E9", "e\u0301"
        };
        Map<String, String> first = new LinkedHashMap<>();

        int collisions = 0;
        for (String value : inputs) {
            String canonical = key(value);
            String earlier = first.putIfAbsent(
                    canonical, value);
            if (earlier != null) {
                collisions++;
            }
        }

        System.out.println("Inputs: " + inputs.length);
        System.out.println("Unique keys: " + first.size());
        System.out.println("Collisions: " + collisions);
    }
}
```

```bash
javac -encoding UTF-8 CanonicalCollisionDemo.java
java CanonicalCollisionDemo
```

Stdout:

```text
Inputs: 4
Unique keys: 2
Collisions: 2
```

**Đây chỉ là ví dụ về collision**, không phải canonicalizer được khuyến nghị cho mọi trường Unicode. `NFC + lowercase(ROOT)` không phải Unicode full case folding hay Unicode security profile; một sản phẩm hỗ trợ username Unicode cần định nghĩa và kiểm tra thêm Unicode version, confusables, ký tự được phép và database collation. Với mật khẩu hoặc token, key transformation như trên thường không được phép.

## 17. Ma trận QA nên đưa vào bộ test

| Nhóm | Dữ liệu mẫu | Kiểm tra |
| --- | --- | --- |
| Canonical forms | `é` / `e + U+0301` | Raw khác, NFC bằng, UTF-8 bytes có thể khác |
| Dấu tiếng Việt | Chữ có dấu thanh, dấu phụ | NFC/NFD, caret/selection đúng cluster |
| Combining mark đầu chuỗi | U+0301 trước chữ | Không crash; policy nhập rõ |
| Surrogate pair | `A😀B` | length 4, codepoints 3, không cắt tại offset 2 |
| Variation selector | `✈️` | 2 codepoints; test grapheme trên runtime |
| ZWJ sequence | `👩‍💻` | 5 UTF-16 units, 3 codepoints |
| Regional indicators | `🇻🇳` | Nhiều codepoints/UTF-16 units |
| Emoji modifier | Emoji + skin tone | Không đếm mỗi codepoint là một ký tự |
| Regex `\\X` | `e\u0301` | Một extended grapheme cluster |
| Case expansion | `ß` → `SS` khi uppercase ROOT | Độ dài thay đổi |
| Dotted I | `İ` ROOT lower | `i` + combining dot |
| Turkish I | `TITLE` ROOT và tr-TR | Hai lowercase keys khác nhau |
| Exact vs ignore-case | `Straße`/`STRASSE` | Không giả định equalsIgnoreCase = full fold |
| Charset | UTF-8 encode/decode | Round trip trên well-formed text |
| Malformed data | UTF-8 `C3 28`, high surrogate đơn | Strict codec từ chối |
| Identifier collision | `Lan_01`/`LAN_01` | Phát hiện unique-key conflict |
| Grapheme segmentation | Ghép mọi `\\X` match | Exact string round-trip |
| Locale-driven search | `en`, `vi`, `tr` | Locale được truyền tường minh |
| Unicode version | Emoji ZWJ mới | Khóa runtime/provider hoặc kiểm tra expected data |
| UI renderer | Font/platform khác nhau | Không coi hình vẽ là chuẩn bytes hay codepoints |
| Database | Java string vs DB collation | Integration test uniqueness |
| File/API boundary | UTF-8/normalization contracts | Không tự thay bytes/ngữ nghĩa |

Mỗi test phải cho biết nó đang đảm bảo **đúng byte, đúng codepoint, đúng grapheme, đúng layout hay đúng nghiệp vụ**. Trộn các tầng này làm xuất hiện test sai hoặc bỏ sót bug.

## 18. Test đa phiên bản JDK và Unicode

JDK phân phối dữ liệu Unicode/locale theo các phiên bản cụ thể. Khi nâng cấp JDK, những khía cạnh cần test lại gồm:

- `Character` classifications theo dữ liệu Unicode mới.
- Segmentation của `BreakIterator`, `Pattern("\\X")` và handling emoji mới.
- Locale-sensitive case mapping và collation.
- `Normalizer` và biểu diễn canonical trong các trường hợp chuẩn Unicode.
- Font/rendering nếu giao diện desktop hoặc bản preview text phụ thuộc platform.

Không phải tất cả hành vi đều thay đổi mỗi lần nâng cấp, và Unicode có chính sách ổn định cho nhiều khía cạnh normalization. Tuy nhiên, **đừng giả định snapshot phân đoạn của mọi emoji mới vĩnh viễn giống nhau**. Phát hiện regression bằng corpus đã gắn kỳ vọng theo runtime hoặc chuẩn mà ứng dụng tuyên bố hỗ trợ.

**Gợi ý cấu trúc test corpus:**

```text
case-id, source-escaped, expected-codepoints, expected-graphemes, unicode-version
combining-e, e\u0301, 2, 1, target-runtime
grinning-face, \uD83D\uDE00, 1, 1, target-runtime
woman-technologist, \uD83D\uDC69\u200D\uD83D\uDCBB, 3, 1, target-runtime
```

Đây là **dữ liệu minh họa corpus**, không phải CSV chuẩn máy đọc vì phần `source-escaped` chứa backslash escapes cần parser riêng. Trong repo thực, dùng JSON/test fixtures với định dạng escaping được xác định, không tự dùng `split(",")` nếu giá trị có thể chứa dấu phẩy.

Đặc biệt, nếu app có nhiều runtime (Java backend, JS frontend, native mobile), có thể dùng Unicode segmentation engines **khác phiên bản**. UI/editor cần thống nhất chính sách giới hạn độ dài và selection, hoặc thông báo rõ việc kiểm tra lại ở backend.

## 19. Sai lầm phổ biến cần tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `String.length()` là số glyph | Emoji bị đếm thành 2 hoặc nhiều hơn | Chọn codepoints/graphemes theo requirement |
| Dùng `substring(i,i+1)` cho emoji | Cắt surrogate pair | Dựa vào biên hợp lệ |
| Coi `offsetByCodePoints` đủ cho caret | Có thể tách dấu/ZWJ | Grapheme segmentation |
| Dùng `equals` để kiểm tra canonical Unicode | NFD/NFC bị xem khác | Normalize theo policy |
| Normalize token/password tự động | Thay đổi giá trị cần xác thực | Tôn trọng giao thức |
| NFKC mọi nội dung | Có thể hợp nhất ký tự mang nghĩa riêng | Chỉ dùng khi profile cho phép |
| Dùng `toLowerCase()` mặc định cho ID | Lỗi Turkish I, khác môi trường | Validate + locale tường minh |
| Giả định uppercase không đổi length | Không đủ dung lượng, collision | Kiểm tra sau mapping |
| Cho rằng `equalsIgnoreCase` là full fold | So sai ở phép mở rộng `ß` | Chọn casefold/profile phù hợp |
| Đếm mọi dấu kết hợp là ký tự riêng | Trải nghiệm caret/xóa sai | Theo grapheme |
| Hard-code emoji segmentation một JDK cho mọi máy | Sai sau thay Unicode/runtime | Test đúng version |
| So screenshot/font để xác định codepoints | Glyph render khác nhau | Kiểm tra codepoint/UTF-8 thực |
| Decode malformed UTF-8 có replacement mà coi thành công | Mất dữ liệu nguồn | Decoder REPORT |
| Chỉ chạy test ASCII/English | Bỏ sót đa ngôn ngữ | Corpus tiếng Việt, Turkish, emoji |
| Dùng regex `[A-Za-z]` cho mọi tên người | Từ chối Unicode hợp lệ | Policy ngôn ngữ cụ thể |
| Tin `\\w` đồng nhất Unicode Letter | Phạm vi regex khác theo flags | Định nghĩa các loại Unicode |
| Dùng Collator cho token/ID | Matching phụ thuộc locale | Exact/identifier policy |
| Quên database collation | Uniqueness Java và DB khác | Integration testing |
| Dùng `Locale.setDefault` trong test concurrent | Test khác bị nhiễu | Truyền Locale per operation |
| Fuzz tạo surrogate đơn lẻ rồi kỳ vọng UTF-8 exact | Sai điều kiện property | Sinh scalar hợp lệ hoặc test malformed riêng |

## 20. Lộ trình debug khi gặp lỗi Unicode

Khi một người dùng báo “chữ có dấu bị mất” hoặc “emoji bị xóa nửa”, đừng bắt đầu bằng thay thế ký tự bằng regex. Hãy ghi nhận theo thứ tự:

1. **Input gốc:** nó đến từ keyboard, clipboard, file UTF-8 hay API? Có cần giữ bytes ban đầu không?
2. **Code points:** log dưới dạng `U+XXXX` trong môi trường an toàn, tránh log PII hoặc token thô.
3. **Normalization:** raw khác hay giống ở NFC/NFD? Có ai ép NFKC hoặc bỏ marks không?
4. **UTF-16 offsets:** có thao tác `substring`/`charAt`/giới hạn độ dài làm cắt surrogate pair không?
5. **Grapheme segmentation:** caret/selection có dùng `BreakIterator` hoặc `\\X` đúng với phiên bản Unicode mong muốn không?
6. **Case mapping:** có dùng default locale hoặc case conversion làm tăng/giảm chiều dài không?
7. **Encoding:** UTF-8 bytes có hợp lệ? Có bị decode nhầm charset hoặc thay `U+FFFD` không?
8. **Database/API:** field collation, normalization, length và encoding có giống policy Java không?
9. **Rendering:** font và terminal có hỗ trợ glyph emoji/combining marks đúng không? Lỗi hiển thị có thể khác lỗi dữ liệu.
10. **Reproduction:** lưu test case escaped và runtime/Unicode version; sử dụng seed cố định cho fuzz.

Trước khi khắc phục, xác định rõ lỗi nằm ở **byte**, **chuỗi Unicode**, **grapheme boundaries**, **case equivalence** hay **display renderer**. Việc sửa nhầm tầng có thể che bug nhưng tạo bug mới.

## 21. Bài tập ứng dụng

**Bài 1 — So raw và NFC.** Dùng `"\u00E9"` và `"e\u0301"`. Tính UTF-16 length, code point count, UTF-8 hex, raw equality và NFC equality. Giải thích lý do kết quả nhìn thấy có thể giống nhau nhưng raw equality khác.

**Bài 2 — Emoji phức hợp.** Xây test cho `😀`, `✈️`, `👩‍💻` và `🇻🇳`. Đếm UTF-16 units/codepoints/graphemes; không cắt giữa surrogate pair và ZWJ sequence. Thử trên hai phiên bản JDK được dự án hỗ trợ.

**Bài 3 — Cắt/xóa một chữ.** Dùng `Pattern.compile("\\X")` để duyệt grapheme trong `"A" + "e\u0301" + "😀" + "B"`. Ghép lại phải bằng chuỗi gốc. Tạo hàm xóa grapheme cuối thay vì chỉ `substring(0,length-1)`.

**Bài 4 — Turkish I.** So `"TITLE".toLowerCase(Locale.ROOT)` và `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))`. Thiết kế canonical username chỉ ASCII rồi test khi default locale JVM là Turkish mà không gọi `Locale.setDefault` ở giữa các test.

**Bài 5 — Case expansion.** So `"Straße".equalsIgnoreCase("STRASSE")` với uppercase ROOT. Vì sao không dùng kết quả một ví dụ để coi uppercase là Unicode full case folding? Thử `"\u0130"` dưới ROOT và Turkish locale.

**Bài 6 — Strict Unicode input.** Cho byte `C3 28` và `String` chứa high surrogate đơn lẻ. So convenience codec với strict decoder/encoder. Viết policy reject hoặc repair có thông báo rõ cho import/API.

**Bài 7 — Property-based testing.** Mở rộng `SeededUnicodePropertiesDemo` bằng thêm các Unicode scalar value ngoài BMP, nhiều combining marks và regional indicators. Giữ seed cố định; kiểm thử NFC/NFD idempotence, UTF-8 round-trip và grapheme reconstruction.

**Bài 8 — Identity collision.** Cho username `Lan_01`, `LAN_01`, `é`, `e\u0301`. Tạo canonical keys theo một policy đã công bố, phát hiện trùng trước khi tạo unique index, không tự gộp tài khoản.

## 22. Tài liệu chính thức

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): UTF-16 `length`, `codePointCount`, `offsetByCodePoints`, `toUpperCase`/`toLowerCase`, `equalsIgnoreCase`.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD.
- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): text boundaries theo locale.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): `\\X`, Unicode classes, Unicode case, canonical equivalence.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): codepoints, surrogate pairs và các thao tác Unicode.
- [Java SE 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): malformed input và error actions.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): strict UTF-8 decoding.
- [Unicode Standard Annex #29](https://www.unicode.org/reports/tr29/): extended grapheme cluster segmentation.
- [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/): normalization forms.
- [Unicode Default Case Algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/#G33992): case mappings và case folding.
- [Unicode Technical Standard #39](https://www.unicode.org/reports/tr39/): confusable identifiers và Unicode security profiles.

## 23. Ghi nhớ

**Một ký tự người dùng nhìn thấy có thể gồm nhiều UTF-16 units và nhiều code points.** Vì vậy cần test riêng `String.length()`, `codePointCount`, grapheme boundaries và UTF-8 bytes. Các chữ có dấu ở dạng NFC/NFD có thể canonically equivalent dù `String.equals` trả false; emoji ZWJ, variation selectors và flags không phải luôn một code point.

**Biến đổi hoa/thường không bảo toàn độ dài và có thể phụ thuộc Locale.** `ß` thành `SS` khi upper-case, `İ` có thể biến thành `i + combining dot` và chữ `I` trong tiếng Thổ Nhĩ Kỳ có lower-case khác ROOT. Không dùng default locale vô tình cho khóa máy đọc, không xem `equalsIgnoreCase` là full Unicode case folding, và không áp normalization/case conversion cho mật khẩu hoặc token ngoài hợp đồng.

**Bộ test tốt phải tự fail khi sai, dùng dữ liệu Unicode đa dạng, seed cố định, codec strict cho malformed input và khóa phiên bản JDK/Unicode khi cần.** Chọn chính sách cho từng field, giữ nguyên bản gốc khi cần, phát hiện collision, và phân biệt lỗi văn bản với lỗi font/rendering.