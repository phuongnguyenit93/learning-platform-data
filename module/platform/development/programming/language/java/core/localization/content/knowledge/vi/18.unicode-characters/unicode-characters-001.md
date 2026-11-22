# Unicode, code point, UTF-16 code unit và ký tự người dùng nhìn thấy trong Java

## 1. Vì sao một “ký tự” không nhất thiết có độ dài 1?

Trong lập trình xử lý văn bản đa ngôn ngữ, chữ **ký tự** có thể được dùng cho nhiều khái niệm khác nhau. Giả sử màn hình hiển thị chữ **é**, emoji **😀**, cờ **🇻🇳** hoặc hình gia đình **👩‍👩‍👧‍👦**. Mỗi ví dụ có thể trông như một ký tự độc lập đối với người đọc, nhưng cách lưu trữ và số lượng phần tử Unicode bên trong hoàn toàn khác nhau.

Trong Java, `String.length()` trả **số UTF-16 code unit**, không phải số code point và càng không phải số ký tự người dùng nhìn thấy. Sử dụng `length()` như phép đếm chữ trong một ô nhập liệu, hoặc cắt chuỗi bằng `substring(0, 1)`, có thể tạo lỗi với emoji, dấu thanh kết hợp, cờ và những chuỗi viết theo hệ chữ phức tạp.

Bài học làm rõ ba tầng:

1. **Unicode code point**: một giá trị định danh trong không gian mã Unicode, ví dụ chữ `A` là `U+0041`, emoji 😀 là `U+1F600`.
2. **UTF-16 code unit**: đơn vị 16 bit dùng trong `char` và các chỉ số chuỗi Java; một code point bổ sung (*supplementary*) cần **hai** code unit liên tiếp.
3. **Grapheme cluster**, gần với “ký tự người dùng nhìn thấy” (*user-perceived character*): một cụm có thể chứa **nhiều code point**, chẳng hạn `e` + dấu sắc kết hợp hoặc một chuỗi emoji có ký tự nối.

**Thông điệp chính:** code unit, code point và grapheme cluster là ba đơn vị đếm khác nhau. Lựa chọn đơn vị phải dựa trên mục đích: thao tác với biểu diễn UTF-16, xử lý Unicode scalar, hay chỉnh sửa văn bản mà người dùng nhận thức thành một đơn vị.

## 2. Bức tranh tổng quan với ví dụ

Bảng sau dùng Java 17+ và `java.util.regex.Pattern` với biểu thức `\\X` để đếm **extended grapheme clusters**:

| Chuỗi minh họa | Diễn giải | UTF-16 code units (`length()`) | Code points | Grapheme clusters (`\\X`) |
| --- | --- | ---: | ---: | ---: |
| `A` | Chữ Latin cơ bản | 1 | 1 | 1 |
| `é` (U+00E9) | Chữ có dấu dạng dựng sẵn | 1 | 1 | 1 |
| `e\u0301` | `e` + combining acute accent | 2 | 2 | 1 |
| `😀` | Emoji ngoài BMP | 2 | 1 | 1 |
| `🇻🇳` | Hai regional indicators tạo hình cờ | 4 | 2 | 1 |
| `👍🏽` | Emoji + modifier màu da | 4 | 2 | 1 |
| `👩‍👩‍👧‍👦` | Bốn emoji + ba ZWJ | 11 | 7 | 1 |

Các con số không thể thay thế cho nhau. Ví dụ, với cờ `🇻🇳`:

- **4 code unit** vì hai regional indicator đều nằm ngoài BMP và mỗi cái dùng surrogate pair.
- **2 code point** vì lá cờ trong ví dụ được mã hóa bằng hai regional indicator.
- **1 extended grapheme cluster** theo quy tắc phân đoạn Unicode áp dụng cho cặp regional indicators.

Chuỗi gia đình `👩‍👩‍👧‍👦` gồm bốn code point emoji (mỗi cái hai UTF-16 code unit) và ba ký tự nối *zero-width joiner* `U+200D` (mỗi cái một code unit): tổng **11 code unit** và **7 code point** nhưng thường được hiển thị thành **một cụm emoji** trên hệ thống có hỗ trợ.

Một grapheme cluster **không bảo đảm** luôn chiếm đúng một ô ký tự monospace, đúng một glyph trong font, hoặc đúng một vị trí con trỏ trên mọi trình duyệt. Kết quả render còn phụ thuộc font, hệ điều hành, Unicode version, shaping engine và cách hỗ trợ emoji.

## 3. Unicode code point là gì?

Một code point là một giá trị số trong khoảng từ `U+0000` đến `U+10FFFF`. Người ta viết code point theo hệ thập lục phân với tiền tố `U+`.

Ví dụ:

- `U+0041` — chữ Latin `A`.
- `U+0065` — chữ `e` thường.
- `U+0301` — dấu sắc kết hợp (*combining acute accent*).
- `U+00E9` — chữ `é` dựng sẵn.
- `U+1F600` — emoji mặt cười 😀.
- `U+200D` — *zero-width joiner* (ZWJ) dùng để liên kết một số emoji sequences và cách trình bày văn bản.

Không phải mọi code point đều là một chữ hoặc một biểu tượng hiển thị. Có code point điều khiển, kết hợp dấu, ký tự không in, mã chưa được gán hoặc những giá trị được dành riêng.

Trong không gian code point, miền từ `U+D800` đến `U+DFFF` được dành cho **surrogate code points**; chúng **không** phải Unicode scalar values có thể xuất hiện độc lập trong văn bản Unicode hợp lệ. Unicode scalar value là code point không thuộc miền surrogate.

Dù Unicode đặt tên nhiều ký tự bằng một code point, một grapheme cluster có thể gồm nhiều code point, và quá trình vẽ chữ có thể kết hợp hoặc chia tách glyph theo script và font. Không nên định nghĩa “một ký tự nhìn thấy” đơn giản là “một code point”.

## 4. UTF-16 và Java `char`: tại sao emoji chiếm hai phần tử?

UTF-16 mã hóa:

- Code point thuộc **Basic Multilingual Plane (BMP)** ngoài miền surrogate bằng **một** code unit 16 bit.
- Code point trong khoảng `U+10000` đến `U+10FFFF` bằng **hai** code unit: một **high surrogate** (`U+D800`–`U+DBFF`) và một **low surrogate** (`U+DC00`–`U+DFFF`).

Trong Java:

- `char` biểu diễn **một UTF-16 code unit**, tức giá trị 16 bit. Nó **không luôn biểu diễn một code point hoàn chỉnh**.
- `String.length()` đếm code unit.
- `String.charAt(index)` trả code unit ở chỉ số UTF-16.
- `String.substring(start, end)` dùng **chỉ số code unit**.
- `String.codePointAt(index)` đọc code point tại vị trí code unit, ghép surrogate pair hợp lệ khi có.
- `String.codePointCount(beginIndex, endIndex)` đếm code point trong đoạn chỉ số UTF-16.
- `String.offsetByCodePoints(index, codePointOffset)` di chuyển theo code point, trả về **chỉ số code unit**.

Chuỗi emoji 😀 có code point `U+1F600`, được UTF-16 mã hóa thành:

```text
U+1F600
  -> high surrogate U+D83D
  -> low  surrogate U+DE00
```

Do đó `"😀".length() == 2` dù đây là một code point.

**Không nhầm UTF-16 code unit với byte.** `char` có 16 bit; khi serialize thành UTF-8, số byte lại khác (emoji 😀 chiếm 4 byte UTF-8). `String.length()` không đo số byte của nội dung trên mạng hoặc tệp.

## 5. Chương trình Java 17+: duyệt code point đúng cách

Tạo file `CodePointWalkDemo.java`. Để chương trình không phụ thuộc vào việc gõ emoji trực tiếp trong source, ví dụ dùng Unicode escapes cho surrogate pair:

```java
public class CodePointWalkDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B"; // A + 😀 + B

        System.out.println("units=" + text.length()
                + " points="
                + text.codePointCount(0, text.length()));

        for (int index = 0; index < text.length();) {
            int cp = text.codePointAt(index);
            int width = Character.charCount(cp);

            System.out.printf("index=%d U+%X units=%d%n",
                    index, cp, width);
            index += width;
        }

        int end = text.offsetByCodePoints(0, 2);
        System.out.println("first2units="
                + text.substring(0, end).length());
    }
}
```

Lưu thành `CodePointWalkDemo.java`, biên dịch/chạy bằng Java 17+:

```bash
javac -encoding UTF-8 CodePointWalkDemo.java
java CodePointWalkDemo
```

Stdout đã kiểm tra:

```text
units=4 points=3
index=0 U+41 units=1
index=1 U+1F600 units=2
index=3 U+42 units=1
first2units=3
```

Đọc kết quả:

- Chuỗi `A😀B` có **4 UTF-16 code unit**, nhưng **3 code point**.
- Chỉ số code unit của `A` là `0`, của 😀 là `1`, của `B` là `3`.
- `Character.charCount(U+1F600)` bằng `2`, do đó vòng lặp nhảy từ chỉ số `1` đến `3`.
- Hai code point đầu tiên là `A` và 😀, nhưng đoạn `substring(0, end)` cần **3 code unit**.

Nếu viết `for (int i=0; i<text.length(); i++)` và coi `text.charAt(i)` như một ký tự Unicode độc lập, vòng lặp sẽ đi qua cả hai nửa surrogate của emoji. Nếu cần xử lý code point, hãy dùng cách duyệt ở trên hoặc `text.codePoints()`.

**Giới hạn:** duyệt theo code point vẫn có thể tách một grapheme cluster thành nhiều phần. Với chuỗi `e\u0301`, vòng lặp sẽ thấy `e` và `U+0301` là hai code point dù người đọc thường thấy một chữ `é`.

## 6. `charAt`, surrogate pair và cách cắt chuỗi dễ gây lỗi

Với `String smile = "\uD83D\uDE00";`:

```java
char first = smile.charAt(0);  // high surrogate: U+D83D
char second = smile.charAt(1); // low surrogate:  U+DE00
int whole = smile.codePointAt(0); // U+1F600
```

Đây là **đoạn minh họa trong một phương thức**, có biến `smile` cần khai báo như ở đầu đoạn. Có thể xác nhận:

```java
Character.isHighSurrogate(first); // true
Character.isLowSurrogate(second); // true
Character.toCodePoint(first, second); // 0x1F600
Character.charCount(whole); // 2
```

Các lời gọi trên minh họa API; các biểu thức không phải chương trình độc lập in stdout.

**Cắt sai:**

```java
String broken = smile.substring(0, 1);
```

`broken` chỉ chứa high surrogate, không phải emoji hoàn chỉnh. Chuỗi Java có thể chứa một code unit surrogate đứng đơn lẻ, nhưng đó là một **chuỗi UTF-16 không hợp lệ về mặt cặp surrogate cho văn bản Unicode thông thường**. Khi mã hóa sang UTF-8, thư viện có thể thay phần không hợp lệ bằng ký tự thay thế hoặc áp dụng chính sách lỗi; không nên dựa vào một biểu diễn hiển thị nhất định.

**Cắt theo code point:**

```java
int end = smile.offsetByCodePoints(0, 1);
String complete = smile.substring(0, end);
```

`end == 2`, giúp giữ nguyên code point 😀. Tuy nhiên, nếu chuỗi là `"e\u0301"`, cắt sau một code point vẫn bỏ rơi dấu sắc kết hợp. Khi thao tác theo “ký tự mà người dùng thấy”, cần phân đoạn **grapheme cluster**, không chỉ nhảy qua surrogate pair.

**Tạo chuỗi từ code point:** `Character.toChars(0x1F600)` trả hai `char` tương ứng surrogate pair. `StringBuilder.appendCodePoint(0x1F600)` là cách chèn code point đúng mà không tự ghép high/low surrogate. Luôn kiểm tra tính hợp lệ của dữ liệu ngoài nếu nó có thể chứa surrogate đứng đơn lẻ.

## 7. `String.codePoints()`: duyệt từng code point bằng Stream

Từ Java 9, `String.codePoints()` trả một `IntStream` duyệt code point. Đối với đoạn có surrogate pair hợp lệ, stream trả **một số `int`** cho cả cặp, không phải hai số của hai `char`.

Ví dụ:

```java
public class CodePointStreamDemo {
    public static void main(String[] args) {
        String s = "A\uD83D\uDE00B";

        s.codePoints()
                .forEach(cp ->
                        System.out.printf("U+%X%n", cp));
    }
}
```

Lưu thành `CodePointStreamDemo.java` rồi chạy:

```bash
javac -encoding UTF-8 CodePointStreamDemo.java
java CodePointStreamDemo
```

Stdout:

```text
U+41
U+1F600
U+42
```

So sánh với `s.chars()`: luồng `chars()` trả **từng UTF-16 code unit** dưới dạng số `int`; với emoji, stream đó chứa high surrogate và low surrogate riêng biệt. Tên `chars()` dễ gây nhầm, nhưng nó không tương đương `codePoints()`.

Một `int` code point cho phép biểu diễn giá trị ngoài BMP; đó là lý do các API Java Unicode thường trả `int` chứ không phải `char`.

## 8. Grapheme cluster: đơn vị gần với “ký tự người dùng nhìn thấy”

Unicode định nghĩa thuật toán phân đoạn thành *extended grapheme clusters* (UAX #29), phục vụ nhiều thao tác chỉnh sửa và điều hướng văn bản. Một grapheme cluster có thể bao gồm:

- Một chữ đơn lẻ như `A`.
- Một chữ cơ sở và nhiều dấu kết hợp: `e` + `U+0301`.
- Một emoji và modifier, ví dụ `👍🏽`.
- Một cặp regional indicators tạo cờ, ví dụ `🇻🇳`.
- Một chuỗi emoji với *zero-width joiner* `U+200D`, như emoji gia đình `👩‍👩‍👧‍👦`.

Các thành phần trên **không nhất thiết thành nhiều ký tự theo cảm nhận của người dùng**, dù code point count lớn hơn 1.

**Khác biệt then chốt:**

- **Code point** là đơn vị của mô hình mã Unicode.
- **Grapheme cluster** là đơn vị phân đoạn chuỗi gần với cách một người tương tác với ký tự trên giao diện.
- **Glyph** là hình dạng được font và bộ máy dựng chữ vẽ ra. Một cluster có thể được thể hiện bằng nhiều glyph hoặc những hình dạng khác nhau tùy hệ thống.
- **Số cột hiển thị trên terminal**, kích thước pixel và vị trí caret **không** thể suy trực tiếp từ số grapheme clusters.

Có thể dùng các thư viện theo UAX #29/CLDR hoặc regex `\\X` của Java để phân đoạn. Với những giao diện phức tạp, cần kiểm thử đúng bản Unicode/JDK, font, trình duyệt và các kiểu văn bản thực tế.

## 9. Java 17+: đếm code unit, code point và grapheme bằng `\\X`

Java `java.util.regex.Pattern` hỗ trợ `\\X` là một **Unicode extended grapheme cluster**. Mẫu `\\X` khớp một cụm khi regex duyệt qua chuỗi; trong Java source phải viết `"\\X"` (hai dấu gạch chéo ngược trong string literal) để regex engine nhận đúng ký hiệu.

Tạo file `UnicodeCountDemo.java`:

```java
import java.util.regex.Pattern;

public class UnicodeCountDemo {
    public static void main(String[] args) {
        String[] names = {
                "ASCII", "NFC", "NFD", "EMOJI",
                "FLAG", "SKIN", "FAMILY"
        };

        String[] values = {
                "A",
                "\u00E9",
                "e\u0301",
                "\uD83D\uDE00",
                "\uD83C\uDDFB\uD83C\uDDF3",
                "\uD83D\uDC4D\uD83C\uDFFD",
                "\uD83D\uDC69\u200D\uD83D\uDC69\u200D"
                        + "\uD83D\uDC67\u200D\uD83D\uDC66"
        };

        Pattern grapheme = Pattern.compile("\\X");

        for (int i = 0; i < values.length; i++) {
            String s = values[i];
            long clusters = grapheme.matcher(s)
                    .results().count();

            System.out.printf(
                    "%s | units=%d | points=%d | graphemes=%d%n",
                    names[i],
                    s.length(),
                    s.codePointCount(0, s.length()),
                    clusters
            );
        }
    }
}
```

Lưu `UnicodeCountDemo.java` với UTF-8 và chạy:

```bash
javac -encoding UTF-8 UnicodeCountDemo.java
java UnicodeCountDemo
```

Stdout đã được xác nhận bằng JVM:

```text
ASCII | units=1 | points=1 | graphemes=1
NFC | units=1 | points=1 | graphemes=1
NFD | units=2 | points=2 | graphemes=1
EMOJI | units=2 | points=1 | graphemes=1
FLAG | units=4 | points=2 | graphemes=1
SKIN | units=4 | points=2 | graphemes=1
FAMILY | units=11 | points=7 | graphemes=1
```

Tên `NFC`/`NFD` ở đây là nhãn cho ví dụ chữ é dựng sẵn và chữ e + dấu kết hợp, không phải bằng chứng rằng mọi chuỗi tự động được normalize.

`Matcher.results()` tồn tại trong Java 9+; code chạy trên Java 17. `Pattern` có thể được dùng lại, còn `Matcher` là đối tượng trạng thái tạo theo chuỗi. Trong ví dụ, `grapheme` được compile một lần và mỗi vòng lặp dùng một matcher mới.

**Giới hạn về Unicode version:** `\\X` dựa trên thuật toán Unicode mà runtime Java hỗ trợ. Quy tắc emoji/grapheme được cập nhật theo các bản Unicode, nên những emoji sequence mới có thể có hành vi phân đoạn khác giữa các JDK. Đừng khẳng định mọi môi trường đều luôn đếm mọi emoji mới thành một cluster.

## 10. Cắt chuỗi theo grapheme cluster thay vì cắt code point

Khi UI cần lấy “ký tự người dùng nhìn thấy đầu tiên”, `offsetByCodePoints(0,1)` chưa đủ cho `e\u0301` hoặc cờ emoji. Có thể lấy ranh giới cluster bằng matcher của `\\X`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class FirstGraphemeDemo {
    public static String firstCluster(String input) {
        Matcher matcher = Pattern.compile("\\X")
                .matcher(input);
        return matcher.find() ? matcher.group() : "";
    }

    public static void main(String[] args) {
        String accent = "e\u0301";
        String flag = "\uD83C\uDDFB\uD83C\uDDF3";

        String firstAccent = firstCluster(accent);
        String firstFlag = firstCluster(flag);

        System.out.println(
                "accent units=" + firstAccent.length());
        System.out.println(
                "accent points=" + firstAccent.codePointCount(
                        0, firstAccent.length()));
        System.out.println(
                "flag units=" + firstFlag.length());
        System.out.println(
                "flag points=" + firstFlag.codePointCount(
                        0, firstFlag.length()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FirstGraphemeDemo.java
java FirstGraphemeDemo
```

Stdout:

```text
accent units=2
accent points=2
flag units=4
flag points=2
```

Bằng cách lấy `matcher.group()`, chương trình không cắt rời dấu sắc khỏi chữ `e` hoặc cắt đôi cặp regional indicators của cờ trong các ví dụ này.

Nếu đang xây một trình soạn thảo, chức năng xóa grapheme, đặt caret hoặc giới hạn độ dài đầu vào, còn phải cân nhắc xử lý CRLF, ZWJ, biến thể emoji, script phức tạp và cấu hình Unicode thực tế. Regex phân đoạn là một bước cơ bản; UI editing còn phụ thuộc bộ máy layout của nền tảng.

## 11. Unicode normalization: giống nhau về hiển thị nhưng chưa chắc bằng nhau về String

Unicode cho phép một số văn bản có **nhiều cách biểu diễn chuẩn tắc**. Chữ `é` là ví dụ nổi bật:

```text
Dựng sẵn: U+00E9            (é)
Phân rã:  U+0065 + U+0301   (e + dấu sắc kết hợp)
```

Hai chuỗi này thường nhìn rất giống nhau, nhưng Java `String.equals` kiểm tra **dãy code unit**, nên chúng không bằng nhau trước khi chuẩn hóa.

API `java.text.Normalizer` hỗ trợ các form như `NFC`, `NFD`, `NFKC`, `NFKD`:

- **NFC** (*Canonical Composition*): chuẩn hóa và có xu hướng ghép những tổ hợp chuẩn tắc thành dạng dựng sẵn khi có thể.
- **NFD** (*Canonical Decomposition*): phân rã chuẩn tắc.
- **NFKC/NFKD** thêm các biến đổi tương thích và **có thể làm thay đổi phân biệt trình bày/ý nghĩa**, nên không áp dụng tùy tiện cho mọi loại dữ liệu như tên người hoặc nội dung ký tự tự do.

### Ví dụ runnable với Normalizer

```java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(
                "equals=" + composed.equals(decomposed));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println(
                "NFC equals=" + composed.equals(normalized));
        System.out.println("units: "
                + composed.length() + " vs "
                + decomposed.length());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

Stdout:

```text
equals=false
NFC equals=true
units: 1 vs 2
```

Normalization không phải transliteration, không phải dịch ngôn ngữ và không phải biện pháp an ninh đầy đủ đối với ký tự dễ nhầm (*confusables*). Khi cần tìm kiếm, so sánh, định danh hoặc xử lý bảo mật, hãy thiết kế chính sách chuẩn hóa/case folding/collation phù hợp với loại dữ liệu và hệ thống đích.

Đặc biệt, normalization **không** đồng nghĩa gom mọi grapheme cluster thành một code point. Cờ emoji và nhiều emoji ZWJ sequences vẫn gồm nhiều code point sau NFC.

## 12. Kích thước UTF-8 khác kích thước UTF-16

Một chuỗi Java được đánh chỉ số theo code unit UTF-16, nhưng khi lưu file hoặc truyền HTTP, encoding thường là **UTF-8**. Số byte hoàn toàn khác số `char`, code point hoặc cluster.

Ví dụ:

| Chuỗi | UTF-16 code units | Code points | Số byte UTF-8 |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| `é` dựng sẵn | 1 | 1 | 2 |
| `e\u0301` | 2 | 2 | 3 |
| `😀` | 2 | 1 | 4 |
| `🇻🇳` | 4 | 2 | 8 |

Có thể kiểm tra bằng Java:

```java
import java.nio.charset.StandardCharsets;

public class UnicodeBytesDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        String emoji = "\uD83D\uDE00";

        System.out.println(
                "NFC bytes=" + composed.getBytes(
                        StandardCharsets.UTF_8).length);
        System.out.println(
                "NFD bytes=" + decomposed.getBytes(
                        StandardCharsets.UTF_8).length);
        System.out.println(
                "EMOJI bytes=" + emoji.getBytes(
                        StandardCharsets.UTF_8).length);
    }
}
```

Lưu `UnicodeBytesDemo.java`, biên dịch/chạy:

```bash
javac -encoding UTF-8 UnicodeBytesDemo.java
java UnicodeBytesDemo
```

Stdout:

```text
NFC bytes=2
NFD bytes=3
EMOJI bytes=4
```

Lưu ý: UTF-8 không phải một byte cho mỗi code point. Với chữ Unicode ngoài ASCII, một code point có thể cần từ 2 đến 4 byte UTF-8; với ASCII cơ bản cần 1 byte. Byte count phụ thuộc **chuỗi code point và encoding**, không phụ thuộc riêng số grapheme.

Khi kiểm tra giới hạn payload HTTP, file hoặc cơ sở dữ liệu có giới hạn byte, hãy tính **byte theo charset thực tế**. Khi kiểm tra giới hạn số code unit của Java/Google Sheets, dùng phép đo mà hệ thống đích công bố. Không hoán đổi giữa ba phép đếm.

## 13. BreakIterator và thư viện phân đoạn văn bản

Java cung cấp `java.text.BreakIterator.getCharacterInstance(locale)` để tìm ranh giới ký tự phục vụ lặp/biên tập text. Ví dụ API:

```java
BreakIterator iterator =
        BreakIterator.getCharacterInstance(locale);
iterator.setText(text);

int start = iterator.first();
for (int end = iterator.next();
        end != BreakIterator.DONE;
        start = end, end = iterator.next()) {
    String segment = text.substring(start, end);
    // Xử lý segment ở ranh giới do BreakIterator trả về.
}
```

Đây là **mã minh họa nằm trong một phương thức**, giả định `locale` là `java.util.Locale` và `text` là `String`, có import `java.text.BreakIterator`. Nó không phải chương trình độc lập để chạy.

Cả `BreakIterator` lẫn regex `\\X` đều hướng đến các quy tắc phân đoạn văn bản, nhưng chi tiết có thể khác theo runtime/provider và bản Unicode, nhất là với một số emoji ZWJ sequences mới. Nếu sản phẩm xử lý chat, trình soạn thảo hay nhập liệu đa script ở quy mô lớn, cần kiểm thử hành vi thực tế của JDK đang dùng; có thể cân nhắc ICU4J hoặc bộ phân đoạn theo Unicode version do sản phẩm kiểm soát.

Không dùng `BreakIterator` để suy ra chiều rộng hiển thị. Cột terminal, glyph và thao tác caret là những vấn đề giao diện bổ sung.

## 14. Dữ liệu UTF-16 không hợp lệ và cách kiểm tra

Một `String` Java có thể chứa surrogate đứng đơn lẻ, ví dụ chỉ có `"\uD83D"`. Đây không phải chuỗi Unicode scalar values hợp lệ. Những API như `codePointAt` hoặc `codePoints()` vẫn có thể xử lý dãy UTF-16 như dữ liệu trong bộ nhớ và trả giá trị code unit surrogate khi không tạo thành cặp hợp lệ.

Do đó, **`codePointCount` không phải bộ kiểm tra tính hợp lệ của chuỗi Unicode**. Nó có thể đếm một surrogate không ghép cặp như một phần tử. Khi nhận dữ liệu từ nguồn có thể lỗi, hãy kiểm tra cặp surrogate hoặc sử dụng decoder với chính sách báo lỗi rõ ràng.

Ví dụ kiểm tra một code unit có bị bỏ lẻ hay không:

```java
public class SurrogateValidationDemo {
    public static boolean isWellFormedUtf16(String text) {
        for (int i = 0; i < text.length(); i++) {
            char unit = text.charAt(i);

            if (Character.isHighSurrogate(unit)) {
                if (i + 1 >= text.length()
                        || !Character.isLowSurrogate(
                                text.charAt(i + 1))) {
                    return false;
                }
                i++;
            } else if (Character.isLowSurrogate(unit)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        System.out.println(isWellFormedUtf16("A\uD83D\uDE00B"));
        System.out.println(isWellFormedUtf16("\uD83D"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SurrogateValidationDemo.java
java SurrogateValidationDemo
```

Stdout:

```text
true
false
```

Hàm này chỉ kiểm tra **cặp surrogate đúng về UTF-16**. Nó không xác nhận văn bản được chuẩn hóa, không lọc ký tự điều khiển, không xác nhận danh sách script được phép và không phát hiện mọi ký tự gây nhầm lẫn hình dạng. Các chính sách đó cần được thiết kế riêng.

## 15. Các thao tác dễ sai trong ứng dụng thực tế

### 15.1. Giới hạn “tối đa 20 ký tự” của ô nhập

Cần xác định “ký tự” ở đây là gì:

- Nếu giao thức giới hạn **UTF-8 bytes**, đếm `getBytes(StandardCharsets.UTF_8).length`.
- Nếu API/ràng buộc Java giới hạn **UTF-16 code units**, dùng `String.length()`.
- Nếu bài toán liên quan đến số **code points**, dùng `codePointCount(0, length())`.
- Nếu muốn hạn chế các đơn vị **người dùng có thể thao tác như một cụm**, dùng bộ phân đoạn grapheme phù hợp; `\\X` có thể là lựa chọn cho Java 17+.
- Nếu UI có ràng buộc chiều rộng thực, cần đo text layout/font; không dựa vào bất kỳ số lượng đơn vị nào ở trên.

Không tuyên bố “20 ký tự” nếu chưa định nghĩa rõ đơn vị tính. Một emoji gia đình là 11 UTF-16 code units nhưng có thể chỉ một grapheme cluster; UI nếu tính bằng `length()` sẽ tiêu tốn 11/20 hạn mức cho một biểu tượng.

### 15.2. Xóa một ký tự từ cuối chuỗi

`substring(0, s.length()-1)` xóa **một code unit**, có thể để lại surrogate lẻ hoặc dấu kết hợp. Xóa một code point bằng `offsetByCodePoints` tránh tách surrogate pair nhưng vẫn có thể tách cluster; chức năng Backspace của editor thường cần xử lý grapheme boundaries và quy tắc nền tảng.

### 15.3. Đảo ngược chuỗi

Đảo theo code unit thô có thể đổi thứ tự high/low surrogate. `StringBuilder.reverse()` có hỗ trợ giữ surrogate pairs hợp lệ, nhưng **không bảo đảm đảo đúng grapheme cluster**; chữ có dấu kết hợp hoặc chuỗi emoji ZWJ có thể bị đảo thành các cụm khác. Đảo văn bản tự nhiên còn phụ thuộc hướng viết, BiDi và ngữ nghĩa ngôn ngữ.

### 15.4. Chuẩn hóa và so sánh

Hai chuỗi render gần giống nhau chưa chắc `equals()` true. Dùng normalization khi bài toán yêu cầu canonical equivalence, nhưng không biến NFC/NFKC thành một hệ thống tự động xử lý toàn bộ vấn đề search, nhận diện người dùng hoặc chống tấn công Unicode confusables.

### 15.5. Cắt ở ranh giới byte

Tránh cắt byte UTF-8 giữa một sequence nhiều byte; nếu cần chia payload, phải giữ ranh giới code point khi decode. Nhưng giữ ranh giới code point vẫn chưa bảo đảm không chia một grapheme cluster.

## 16. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế | Phương án phù hợp |
| --- | --- | --- |
| `char` là một ký tự Unicode hoàn chỉnh | `char` là một UTF-16 code unit | Dùng `int` code point khi xử lý scalar |
| `String.length()` là số chữ nhìn thấy | Nó đếm UTF-16 code units | Chọn code points hoặc graphemes theo mục tiêu |
| `substring(0,1)` luôn lấy chữ đầu tiên | Có thể lấy một nửa surrogate pair | Dùng code point/grapheme boundary |
| Mỗi emoji bằng một code point | Cờ, modifiers và ZWJ sequences có thể nhiều code point | Hiểu extended grapheme clusters |
| `codePointCount` luôn đếm ký tự người dùng | Dấu kết hợp và ZWJ tạo nhiều code point/cluster | Dùng `\\X` hoặc segmentation API |
| UTF-8 byte và UTF-16 code unit giống nhau | Chúng là hai encoding với kích thước khác nhau | Đếm bytes khi đo payload, units khi đo UTF-16 |
| Hai chuỗi nhìn giống nhau thì `equals` true | NFC/NFD có thể khác dãy code units | Chuẩn hóa có chủ đích |
| Regex `\\X` đảm bảo một glyph/ô terminal | Cluster không tương đương layout width | Đo layout nếu mục tiêu là hiển thị |
| `codePointCount` phát hiện surrogate lỗi | Có thể vẫn đếm phần tử surrogate đứng riêng | Validate UTF-16/decoder nếu cần |
| Emoji hiển thị giống nhau trên mọi hệ thống | Phụ thuộc font, Unicode version, renderer | Kiểm thử trên nền tảng đích |
| Mọi ký tự hợp lệ phải nằm trong BMP | Code points bổ sung rất phổ biến | Hỗ trợ surrogate pairs đúng |
| `Normalizer` giải quyết mọi vấn đề Unicode security | Nó chỉ chuẩn hóa theo form được chọn | Áp dụng chính sách bảo mật/ngôn ngữ riêng |

## 17. Checklist kiểm thử

Với code xử lý chuỗi đa ngôn ngữ, nên kiểm tra ít nhất:

1. **ASCII**: `A`, `abc` — 1 code unit cho mỗi ký tự cơ bản.
2. **BMP có dấu dựng sẵn**: `é` (`U+00E9`) — 1 unit/1 point/1 cluster.
3. **Dấu kết hợp**: `e\u0301` — 2 units/2 points/1 cluster.
4. **Emoji bổ sung**: 😀 — 2 units/1 point/1 cluster.
5. **Cờ regional indicator**: 🇻🇳 — 4 units/2 points/1 cluster.
6. **Emoji modifier**: 👍🏽 — 4 units/2 points/1 cluster.
7. **ZWJ emoji**: 👩‍👩‍👧‍👦 — 11 units/7 points/1 cluster trên runtime được kiểm tra.
8. **Cắt code point**: `offsetByCodePoints` không cắt đôi surrogate pair.
9. **Cắt grapheme**: regex `\\X` không tách `e\u0301` trong ví dụ.
10. **Normalization**: NFC của `e\u0301` bằng `é`.
11. **Malformed UTF-16**: surrogate cao đứng đơn lẻ bị validation từ chối.
12. **UTF-8 size**: `é` dựng sẵn 2 bytes, phân rã 3 bytes, 😀 4 bytes.
13. **Version**: kiểm tra các emoji cluster mới trên đúng bản JDK/Unicode dữ liệu sẽ chạy.
14. **UI behavior**: caret, Backspace, chọn text và độ rộng chữ không bị suy trực tiếp từ `String.length()`.

### Bài tập thực hành

- Viết một hàm in từng code point của câu `"Chào 😀"` dưới dạng `U+XXXX`; so sánh số code unit với số code point.
- Viết hàm `firstCodePoint(String s)` dùng `offsetByCodePoints`, và `firstGrapheme(String s)` dùng `Pattern.compile("\\X")`. Thử với `"e\u0301"` và cờ emoji, giải thích vì sao kết quả khác.
- Viết validator cho giới hạn **10 grapheme clusters** và so sánh kết quả với validator giới hạn **10 UTF-16 code units** trên emoji gia đình.
- Chuẩn hóa danh sách chuỗi với `Normalizer.Form.NFC`, kiểm tra `equals` trước/sau. Giải thích vì sao dùng NFKC tùy tiện có thể làm thay đổi dạng tương thích.
- Thử tạo một chuỗi chỉ gồm high surrogate (`"\uD83D"`) và xác nhận `isWellFormedUtf16` trả false. Tìm lý do tại sao `codePointCount` không phải validator.
- Thử đếm byte UTF-8 và code unit của cùng chuỗi có tiếng Việt, emoji, dấu kết hợp. Quyết định loại giới hạn phù hợp cho UI và API.
- Dựng thử một nút Backspace chỉ xóa một code point, rồi đối chiếu với Backspace ở trình soạn thảo dùng grapheme clusters; đánh giá các trường hợp dấu kết hợp.

## 18. Kết luận

Để xử lý Unicode đúng trong Java, phải biết bạn đang làm việc ở **tầng nào**:

- `String.length()`, `charAt()`, `substring()`: **UTF-16 code units và chỉ số code unit**.
- `codePointAt()`, `codePointCount()`, `codePoints()`, `offsetByCodePoints()`: **Unicode code points**.
- `Pattern.compile("\\X")` hoặc bộ phân đoạn Unicode thích hợp: **extended grapheme clusters**, gần với đơn vị văn bản mà người dùng cảm nhận.
- `Normalizer`: giúp xử lý **canonical/compatibility normalization**, không phải phép đếm hay trình dựng glyph.
- `getBytes(StandardCharsets.UTF_8)`: **byte size khi mã hóa**, không phải số ký tự.

Mọi phép đếm/cắt/định dạng phải được gắn với đúng yêu cầu nghiệp vụ: **độ dài bộ nhớ/serialization, xử lý Unicode, hay thao tác trên văn bản nhìn thấy**. Không dùng một phép đếm duy nhất cho mọi tình huống và không coi “một code point = một ký tự người dùng nhìn thấy”.

## Tài liệu tham khảo

- [Oracle Java 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle Java 21 — Character](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html)
- [Oracle Java 21 — Pattern (Unicode grapheme `\\X`)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Oracle Java 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Oracle Java 21 — BreakIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html)
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
