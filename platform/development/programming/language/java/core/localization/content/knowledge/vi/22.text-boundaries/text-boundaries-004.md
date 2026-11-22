# Cụm ký tự hiển thị, dấu kết hợp và chuỗi emoji trong Java

## 1. Vì sao một “ký tự” trên màn hình có thể gồm nhiều phần?

Trong giao diện nhiều ngôn ngữ, người dùng thường coi chữ `é`, biểu tượng `😀`, cờ `🇻🇳`, dấu tay `👍🏽` hoặc gia đình `👩‍👩‍👧‍👦` là những đơn vị có thể chọn hay xóa cùng nhau. Tuy nhiên, những biểu diễn này không nhất thiết gồm một code point Unicode, và cũng không nhất thiết chiếm một `char` Java.

Ví dụ, `e\u0301` là chữ `e` theo sau bởi **combining acute accent** `U+0301`. Nó gồm hai code point nhưng thường được người đọc nhận ra như một chữ có dấu. Cờ `🇻🇳` gồm hai **regional indicator** code points, và emoji gia đình có thể gồm bốn emoji cùng ba ký tự nối **zero-width joiner** (ZWJ).

Khi xử lý **ranh giới văn bản**, có ba câu hỏi tách biệt:

1. Có bao nhiêu **UTF-16 code unit**? Đây là điều `String.length()` trả về.
2. Có bao nhiêu **Unicode code point**? Đây là điều `codePointCount()` đo.
3. Có bao nhiêu **extended grapheme cluster**? Đây là đơn vị phân đoạn thường gần với “một ký tự mà người dùng cảm nhận”.

Bài này tập trung vào câu hỏi thứ ba: **cụm ký tự hiển thị, dấu kết hợp, emoji modifiers và emoji sequences**. Ta sẽ dùng `java.util.regex.Pattern` với biểu thức `\\X` trong Java 17+, hiểu Unicode Text Segmentation (UAX #29), kiểm tra các ranh giới, cắt chuỗi an toàn và phân biệt phân đoạn với việc vẽ glyph thực tế.

**Nguyên tắc:** để giới hạn số “ký tự” người dùng nhập, xóa một phần văn bản hoặc đặt con trỏ một cách tự nhiên, đừng mặc nhiên dùng `String.length()`, `charAt()` hoặc `codePoints()` làm đơn vị giao diện.

## 2. Ba tầng biểu diễn và một bảng ví dụ

Unicode phân biệt **code point** (một giá trị `U+...`) với **code unit** (đơn vị mã hóa) và **grapheme cluster** (một cụm code point theo quy tắc phân đoạn).

| Nội dung | UTF-16 code units | Code points | Grapheme clusters |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| `é` dạng dựng sẵn `U+00E9` | 1 | 1 | 1 |
| `e\u0301`: chữ + dấu kết hợp | 2 | 2 | 1 |
| `😀` | 2 | 1 | 1 |
| `👍🏽`: emoji + skin tone modifier | 4 | 2 | 1 |
| `🇻🇳`: cặp regional indicators | 4 | 2 | 1 |
| `👩‍👩‍👧‍👦`: chuỗi emoji ZWJ | 11 | 7 | 1 |
| `❤️`: heart + variation selector | 2 | 2 | 1 |
| `1️⃣`: keycap emoji sequence | 3 | 3 | 1 |

Bảng minh họa kết quả từ thuật toán grapheme mà Java regex `\\X` hỗ trợ trong JVM được kiểm thử. Kết quả phân đoạn với một số **emoji sequence mới** có thể thay đổi giữa các phiên bản Unicode/JDK; kết quả hiển thị còn phụ thuộc font và nền tảng.

Ví dụ đối với `👩‍👩‍👧‍👦`:

- Bốn emoji người nằm ngoài Basic Multilingual Plane (BMP), mỗi emoji dùng hai UTF-16 code unit → tổng 8.
- Ba ký tự `U+200D` (ZWJ) nằm trong BMP, mỗi cái một code unit → tổng thêm 3.
- Tổng cộng **11 code unit**, **7 code point**, nhưng thường được phân đoạn thành **một extended grapheme cluster**.

Một cluster có thể chứa nhiều code point; một code point không nhất thiết tương đương một glyph; và một glyph không nhất thiết chiếm một cột màn hình. Đó là những khái niệm có mục đích riêng.

## 3. Extended grapheme cluster là gì?

Unicode Standard Annex #29 (UAX #29) mô tả quy tắc phân đoạn văn bản, trong đó có các **extended grapheme clusters**. Khái niệm này mô phỏng nhiều trường hợp mà người dùng muốn thao tác trên **một đơn vị văn bản**, dù đơn vị đó là một chuỗi code point.

Ví dụ:

~~~text
e + ◌́             -> một cụm: é
👍 + 🏽             -> một cụm: 👍🏽
🇻 + 🇳             -> một cụm: 🇻🇳
👩 + ZWJ + 👩 + ZWJ + 👧 + ZWJ + 👦 -> một cụm
~~~

Các quy tắc chuẩn không đơn giản là “ghép mọi dấu với ký tự đứng trước”. Chúng xét nhiều thuộc tính Unicode và ngữ cảnh: **Extend** (các dấu nối tiếp), **SpacingMark**, **Prepend**, **Regional_Indicator**, **Extended_Pictographic** và các điều kiện với ZWJ, Hangul hoặc một số hệ chữ phức tạp.

**Extended grapheme cluster** là thuật ngữ phân đoạn. Nó không có nghĩa tất cả trình duyệt sẽ vẽ một cụm thành một glyph hoàn chỉnh. Nếu font/hệ điều hành chưa hỗ trợ một chuỗi emoji, người dùng có thể thấy nhiều hình rời, trong khi thuật toán phân đoạn vẫn xem cả chuỗi là một cluster.

Khi xác định đơn vị mà UI gọi là “ký tự”, cần chỉ rõ đó là **grapheme cluster theo thuật toán/Unicode version nào** hoặc là một quy tắc sản phẩm riêng; đừng ghi “mỗi ký tự là một char” trong hợp đồng dữ liệu.

## 4. Dấu kết hợp: chữ có dấu không nhất thiết là một code point

Unicode có thể biểu diễn chữ cái có dấu theo các cách tương đương chuẩn tắc. Với `é`:

~~~text
U+00E9                 é (dựng sẵn)
U+0065 U+0301          e + combining acute accent
~~~

Hai chuỗi thường có cùng hình thức hiển thị, nhưng về nội dung Java:

| Phép đo | `"\u00E9"` | `"e\u0301"` |
| --- | ---: | ---: |
| `String.length()` | 1 | 2 |
| `codePointCount()` | 1 | 2 |
| Số cluster theo `\\X` | 1 | 1 |

Dấu `U+0301` là **combining mark**: nó có thể được bố trí trên chữ cơ sở thay vì hiện một hình riêng. Tiếng Việt thường có những cấu trúc kết hợp chữ cơ sở, dấu phụ và dấu thanh. Vì vậy một phép kiểm tra độ dài dựa vào code point vẫn có thể đếm thừa so với trực giác người dùng.

Không xóa hoặc cắt riêng dấu kết hợp nếu thao tác được mô tả là “xóa một ký tự”. Ví dụ, cắt `"e\u0301"` ở ranh giới giữa `e` và `U+0301` có thể để lại dấu sắc lơ lửng hoặc một biểu diễn khác.

**Normalization không thay thế phân đoạn:** `Normalizer.normalize(text, NFC)` có thể ghép một số chữ với dấu thành một code point dựng sẵn, nhưng không thể ghép **mọi** grapheme cluster (như cờ hoặc emoji ZWJ) thành một code point. Muốn thao tác theo cluster, vẫn phải dùng thuật toán phân đoạn.

## 5. Emoji modifiers: một biểu tượng có thể gồm hai code point

Emoji `👍🏽` minh họa **skin tone modifier**:

~~~text
U+1F44D  THUMBS UP SIGN
U+1F3FD  EMOJI MODIFIER FITZPATRICK TYPE-4
~~~

Hai code point đều nằm ngoài BMP, nên tạo ra **4 UTF-16 code unit**. Một phần mềm render hỗ trợ thường hiển thị tổ hợp này như một biểu tượng duy nhất; thuật toán grapheme cluster cũng xem tổ hợp thành một cụm trong ví dụ trên.

Nếu thao tác xóa dựa vào một code point, nó có thể chỉ bỏ modifier hoặc chỉ bỏ ký tự cơ sở, làm thay đổi biểu tượng một cách người dùng không mong muốn. Dùng ranh giới grapheme khi mục tiêu là xóa biểu tượng như một đơn vị.

Modifier không phải dấu tiếng Việt hay ký tự nối ZWJ: nó là một loại code point khác có quy tắc kết hợp emoji cụ thể. Trong xử lý dữ liệu, các yếu tố này cần được giữ đúng thứ tự, nhất là khi sao chép, cắt và dán.

## 6. Cờ emoji: hai regional indicators tạo một cụm

Cờ `🇻🇳` là chuỗi:

~~~text
U+1F1FB  REGIONAL INDICATOR SYMBOL LETTER V
U+1F1F3  REGIONAL INDICATOR SYMBOL LETTER N
~~~

Mỗi code point cần hai UTF-16 code unit. Vì vậy `🇻🇳` gồm **4 code unit**, **2 code point** và thường **1 extended grapheme cluster**.

Quy tắc phân đoạn Regional Indicator không phải là “mọi regional indicators đứng liền đều thành một cụm”. Các ký tự RI được **ghép cặp theo ngữ cảnh**, vì vậy một chuỗi dài có thể phân thành nhiều cụm. Không chia một đoạn RI ở vị trí code point tùy ý rồi giả định việc ghép cluster vẫn giữ nguyên qua ranh giới đó.

Cũng không coi một cụm RI bất kỳ chắc chắn render thành lá cờ của một quốc gia được công nhận; sự hỗ trợ biểu tượng và ngữ nghĩa mã vùng còn phụ thuộc chuẩn emoji và nền tảng.

## 7. Chuỗi emoji với ZWJ: một cụm có thể có nhiều emoji

`U+200D`, **zero-width joiner** (ZWJ), có thể nối một số chuỗi pictographic thành biểu tượng tổng hợp. Ví dụ `👩‍👩‍👧‍👦` gồm:

~~~text
WOMAN + ZWJ + WOMAN + ZWJ + GIRL + ZWJ + BOY
~~~

Bốn emoji và ba ZWJ = **7 code point**, còn UTF-16 là **11 code unit**. Trong runtime được kiểm chứng, biểu thức `\\X` nhận toàn bộ thành một cluster.

Không phải **mọi** dãy `emoji + ZWJ + emoji` đều là emoji sequence được chuẩn hóa để render thành một glyph duy nhất. Grapheme segmentation và danh sách emoji sequences có liên quan nhưng **không đồng nhất**. Font/rendering engine có thể thiếu glyph kết hợp; thao tác phân đoạn vẫn cần xem xét ranh giới cluster dựa trên quy tắc Unicode của runtime.

Tương tự, variation selector `U+FE0F` có thể tác động cách trình bày emoji, chẳng hạn `❤️` gồm `U+2764` và `U+FE0F`; keycap `1️⃣` gồm `1`, `U+FE0F`, `U+20E3`. Chúng lần lượt có **2 và 3 code point** nhưng một grapheme cluster trong ví dụ. Không cắt bỏ variation selector/combining keycap giữa chừng nếu mục tiêu là giữ nguyên biểu tượng.

## 8. Java String đếm UTF-16 code unit, không đếm cụm

Đối với `String`:

- `length()` trả về số UTF-16 code unit.
- `charAt(index)` lấy **một** code unit tại vị trí UTF-16.
- `substring(begin, end)` cắt theo chỉ số code unit.
- `codePointAt(index)` đọc code point tại chỉ số UTF-16.
- `codePointCount(begin, end)` đếm code point trong đoạn.
- `offsetByCodePoints(index, n)` di chuyển theo code point và trả về chỉ số UTF-16.

Dùng `codePointAt` tốt hơn `charAt` khi cần duyệt Unicode scalar values; nó tránh tách một supplementary code point thành hai surrogate code unit. Nhưng **code point boundary chưa chắc là grapheme boundary**, ví dụ giữa `e` và dấu kết hợp, giữa hai regional indicators hoặc giữa emoji và modifier.

Nếu giao diện cần cắt theo “đơn vị người dùng thấy”, hãy dùng **grapheme segmentation** thay vì chỉ dùng `offsetByCodePoints`.

## 9. Java 17+: dùng regex `\\X` để đếm extended grapheme clusters

Từ Java 9, `java.util.regex.Pattern` hỗ trợ `\\X` để khớp một **Unicode extended grapheme cluster**. Trong một Java string literal, phải viết `"\\X"` (hai dấu backslash trong mã nguồn Java) để regex nhận một dấu backslash và `X`.

Chương trình `GraphemeCountDemo.java`:

~~~java
import java.util.regex.Pattern;

public class GraphemeCountDemo {
    public static void main(String[] args) {
        String[] names = {
            "ASCII", "ACCENT", "EMOJI", "SKIN",
            "FLAG", "FAMILY", "HEART", "KEYCAP"
        };

        String[] values = {
            "A",
            "e\u0301",
            "\uD83D\uDE00",
            "\uD83D\uDC4D\uD83C\uDFFD",
            "\uD83C\uDDFB\uD83C\uDDF3",
            "\uD83D\uDC69\u200D\uD83D\uDC69\u200D"
                + "\uD83D\uDC67\u200D\uD83D\uDC66",
            "\u2764\uFE0F",
            "1\uFE0F\u20E3"
        };

        Pattern grapheme = Pattern.compile("\\X");

        for (int i = 0; i < values.length; i++) {
            String text = values[i];
            long clusters = grapheme.matcher(text)
                .results().count();

            System.out.printf(
                "%s: units=%d points=%d clusters=%d%n",
                names[i],
                text.length(),
                text.codePointCount(0, text.length()),
                clusters);
        }
    }
}
~~~

Lưu với encoding UTF-8 dưới tên `GraphemeCountDemo.java`; chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 GraphemeCountDemo.java
java GraphemeCountDemo
~~~

Stdout theo dữ liệu Unicode của JVM đã kiểm chứng:

~~~text
ASCII: units=1 points=1 clusters=1
ACCENT: units=2 points=2 clusters=1
EMOJI: units=2 points=1 clusters=1
SKIN: units=4 points=2 clusters=1
FLAG: units=4 points=2 clusters=1
FAMILY: units=11 points=7 clusters=1
HEART: units=2 points=2 clusters=1
KEYCAP: units=3 points=3 clusters=1
~~~

Ở đây `Matcher.results()` là API có trong Java 9+, vì vậy dùng được với Java 17. `Pattern` compile một lần; mỗi `matcher(text)` là matcher mới cho dữ liệu cần phân đoạn.

**Không nhầm lẫn:** `\\X` là regex dựa trên thuật toán phân đoạn, không đo chiều rộng pixel hoặc số glyph. Nó cũng không phải bước normalize; chuỗi `e\u0301` vẫn có 2 code point, dù regex nhận thành 1 cluster.

## 10. Xác định ranh giới thực tế: chỉ số trả về vẫn là UTF-16

Một matcher `\\X` có thể trả về `start()` và `end()` của từng cluster. Hai giá trị này **vẫn là chỉ số UTF-16 code unit** trong `String`, không phải chỉ số code point hoặc số cluster.

Ví dụ `GraphemeBoundaryDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeBoundaryDemo {
    public static void main(String[] args) {
        String text = "A" + "e\u0301"
            + "\uD83C\uDDFB\uD83C\uDDF3";

        Pattern pattern = Pattern.compile("\\X");
        Matcher matcher = pattern.matcher(text);

        System.out.println("all=" + text.length()
            + "/" + text.codePointCount(0, text.length())
            + "/" + pattern.matcher(text).results().count());

        while (matcher.find()) {
            String cluster = matcher.group();
            System.out.println(matcher.start() + ".."
                + matcher.end() + " => "
                + cluster.length() + "/"
                + cluster.codePointCount(0, cluster.length()));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GraphemeBoundaryDemo.java
java GraphemeBoundaryDemo
~~~

Stdout:

~~~text
all=7/5/3
0..1 => 1/1
1..3 => 2/2
3..7 => 4/2
~~~

Giải thích:

- `A` ở đoạn UTF-16 `[0, 1)`: 1 code unit/1 code point.
- `e\u0301` ở đoạn `[1, 3)`: 2 code unit/2 code point nhưng 1 cluster.
- `🇻🇳` ở đoạn `[3, 7)`: 4 code unit/2 code point nhưng 1 cluster.

Các ranh giới là **half-open intervals**: start được tính, end không được tính. Nếu dùng `substring(matcher.start(), matcher.end())`, ta lấy trọn cluster theo ranh giới đã nhận; không tự thêm hoặc bớt đơn vị.

## 11. Cắt văn bản theo số cụm thay vì số code unit

Chức năng rút gọn text thường dùng kiểu `text.substring(0, limit)`. Nếu `limit` được giải thích là **số ký tự người dùng nhìn thấy**, cách đó có thể sai: cắt đôi surrogate pair, để lại dấu kết hợp hoặc chia một chuỗi emoji.

Ta có thể duyệt `Matcher` để tìm **ranh giới kết thúc của cluster thứ N** rồi cắt một lần.

Chương trình `GraphemePrefixDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemePrefixDemo {
    private static final Pattern GRAPHEME =
        Pattern.compile("\\X");

    static String firstClusters(String text, int limit) {
        if (text == null || limit < 0) {
            throw new IllegalArgumentException("invalid input");
        }

        Matcher matcher = GRAPHEME.matcher(text);
        int end = 0;
        int count = 0;

        while (count < limit && matcher.find()) {
            end = matcher.end();
            count++;
        }
        return text.substring(0, end);
    }

    static void describe(String label, String value) {
        System.out.println(label + "=" + value.length() + "/"
            + value.codePointCount(0, value.length())
            + "/" + GRAPHEME.matcher(value).results().count());
    }

    public static void main(String[] args) {
        String text = "A" + "e\u0301"
            + "\uD83C\uDDFB\uD83C\uDDF3";

        describe("original", text);
        describe("first2", firstClusters(text, 2));
        describe("first3", firstClusters(text, 3));
        describe("first0", firstClusters(text, 0));
    }
}
~~~

Lưu `GraphemePrefixDemo.java` rồi chạy:

~~~bash
javac -encoding UTF-8 GraphemePrefixDemo.java
java GraphemePrefixDemo
~~~

Stdout:

~~~text
original=7/5/3
first2=3/3/2
first3=7/5/3
first0=0/0/0
~~~

Hàm lấy tối đa `limit` cluster, giữ nguyên những code point bên trong. Nếu `limit` lớn hơn số cluster hiện có, kết quả là toàn chuỗi. Nếu `limit == 0`, kết quả rỗng. Đầu vào `null` hoặc giới hạn âm bị từ chối rõ ràng.

Cách này phù hợp để lấy prefix theo grapheme trong các bài toán nhất định; việc rút gọn UI thực tế còn cần cân nhắc dấu `…`, chiều rộng hiển thị và quy tắc sản phẩm. Nếu giới hạn bằng **bytes truyền mạng**, **code units** hoặc **code points**, hãy dùng phép đo đúng với yêu cầu đó, thay vì luôn dùng grapheme.

## 12. Backspace, caret và khả năng chọn văn bản

Giả sử chuỗi chỉ chứa `"e\u0301"`. Một thao tác `substring(0, text.length() - 1)` sẽ bỏ dấu sắc và để lại `e`; tức đã xóa **một code unit**, không phải một grapheme. Với cờ emoji `🇻🇳`, xóa một code unit có thể để lại surrogate không ghép cặp.

Xóa theo **code point** bằng `offsetByCodePoints` tránh cắt đôi surrogate pair, nhưng vẫn có thể tách `e\u0301` thành `e` và dấu sắc, hoặc cắt đôi cặp regional indicators. Muốn Backspace theo cụm, cần xác định **ranh giới cluster ngay trước vị trí con trỏ**, rồi xóa toàn bộ đoạn UTF-16 tương ứng.

Đối với caret và selection, còn nhiều vấn đề giao diện:

- Người dùng có thể đặt caret giữa các vị trí cho phép bởi engine soạn thảo chứ không đơn thuần ở mọi code unit.
- Một cluster không đảm bảo tương ứng đúng một glyph hay một ô monospace.
- Các hệ chữ như tiếng Ả Rập, Indic và văn bản bidirectional có quy tắc layout, thứ tự đọc và điều hướng phức tạp.
- Hệ điều hành/trình duyệt có thể hỗ trợ hành vi chỉnh sửa khác thuật toán Java server-side.

Vì vậy **grapheme cluster là một lớp nền tảng** cho editing, không phải công thức hoàn chỉnh cho caret hoặc rendering.

## 13. Normalization thay đổi số code point nhưng không giải quyết mọi cluster

`java.text.Normalizer` hỗ trợ NFC, NFD, NFKC và NFKD. Đối với chữ `é`, NFC có thể biến `e\u0301` thành `U+00E9`; số code point/UTF-16 code unit giảm từ 2 xuống 1. Cả hai dạng vẫn là **1 grapheme cluster**.

Ví dụ độc lập `GraphemeNormalizationDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class GraphemeNormalizationDemo {
    static String metrics(String s) {
        long clusters = Pattern.compile("\\X")
            .matcher(s).results().count();
        return s.length() + "/"
            + s.codePointCount(0, s.length()) + "/"
            + clusters;
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("equals="
            + composed.equals(decomposed));
        System.out.println("before=" + metrics(decomposed));

        String nfc = Normalizer.normalize(
            decomposed, Normalizer.Form.NFC);

        System.out.println("after=" + metrics(nfc));
        System.out.println("nfcEqual=" + composed.equals(nfc));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GraphemeNormalizationDemo.java
java GraphemeNormalizationDemo
~~~

Stdout:

~~~text
equals=false
before=2/2/1
after=1/1/1
nfcEqual=true
~~~

Đây là sự khác biệt giữa **cấu trúc dữ liệu** và **cách người dùng cảm nhận**. Đừng normalize chỉ để “biến mọi ký tự hiển thị thành một code point”: điều đó không thể đạt được với nhiều emoji sequences.

Nếu cần bảo toàn chính xác dữ liệu nguồn (ví dụ tài liệu có chữ và dấu nhập theo dạng decomposed), hãy giữ bản gốc trước khi normalize. Một giá trị đã NFC thường không tiết lộ được cách biểu diễn code point ban đầu dù giữ tương đương chuẩn tắc.

## 14. BreakIterator và sự khác biệt giữa các bộ phân đoạn

Ngoài regex, Java cung cấp `java.text.BreakIterator.getCharacterInstance(locale)` để tìm ranh giới ký tự. Đây là API khác với `Pattern.compile("\\X")`, và kết quả phụ thuộc các quy tắc/bộ dữ liệu mà implementation cụ thể sử dụng.

Đoạn mã sau là **minh họa bên trong một phương thức** có biến `String text`, `Locale locale` và import `java.text.BreakIterator`:

~~~java
BreakIterator iterator =
    BreakIterator.getCharacterInstance(locale);
iterator.setText(text);

for (int start = iterator.first(),
         end = iterator.next();
     end != BreakIterator.DONE;
     start = end, end = iterator.next()) {

    String segment = text.substring(start, end);
    // Xử lý segment theo ranh giới trả về.
}
~~~

Không mặc định `BreakIterator` trên mọi JDK/locale sẽ xử lý **mọi emoji ZWJ sequence mới** giống `\\X`; cần kiểm thử với Unicode data version và runtime mục tiêu. Tùy yêu cầu, có thể dùng ICU4J hoặc một thư viện cập nhật theo phiên bản Unicode được quản lý.

Dù dùng cách nào, chỉ số `start/end` trên `String` vẫn là **chỉ số UTF-16**. Đừng trộn chúng với vị trí code point hoặc số cluster khi cắt chuỗi.

## 15. Phiên bản Unicode và emoji mới

Quy tắc UAX #29 thay đổi theo chuẩn Unicode; danh sách emoji sequences và khả năng rendering cũng thay đổi theo Unicode/emoji version. Một JVM cũ có thể biết cách phân đoạn nhiều emoji phổ biến, nhưng không nhất thiết hiểu các thuộc tính của emoji mới nhất.

Hệ quả thực tế:

1. Bộ kiểm thử nên chứa những chuỗi emoji mà sản phẩm thực sự hỗ trợ.
2. Cần pin hoặc ghi rõ phiên bản JDK/ICU/Unicode data khi hành vi phân đoạn là một phần của hợp đồng.
3. Không chỉ test `😀` đơn lẻ; phải có dấu kết hợp, cờ RI, modifiers, ZWJ và variation selectors.
4. Không coi một biểu tượng render thành các hình rời là bằng chứng regex đã phân đoạn sai; đó có thể là khác biệt font/renderer.
5. Nếu phụ thuộc vào giới hạn số grapheme trong dữ liệu lưu trữ, khi nâng Unicode version có thể cần kiểm tra lại dữ liệu và các trường hợp gần ngưỡng.

Bất kỳ code nào giả định mỗi emoji có độ dài `2` UTF-16 units sẽ sai với chuỗi tổ hợp; bất kỳ code nào giả định mỗi glyph là một grapheme cũng không đáng tin trên các hệ chữ phức tạp.

## 16. Cụm ký tự và giới hạn độ dài ô nhập liệu

Một yêu cầu sản phẩm như “Tên hiển thị tối đa 20 ký tự” còn thiếu **đơn vị đo**. Có thể là:

| Yêu cầu thực sự | Cách đo trong Java |
| --- | --- |
| Tối đa 20 UTF-16 code units | `text.length()` |
| Tối đa 20 Unicode code points | `text.codePointCount(0, text.length())` |
| Tối đa 20 extended grapheme clusters | `Pattern.compile("\\X").matcher(text).results().count()` |
| Tối đa 20 bytes UTF-8 | `text.getBytes(StandardCharsets.UTF_8).length` |
| Tối đa một chiều rộng pixel | API layout/font, không phải các phép đếm trên |

Các đơn vị không tương đương. Một emoji gia đình có thể tiêu tốn **11 code unit** nhưng chỉ **1 grapheme cluster**. Nếu sản phẩm hứa giới hạn “20 ký tự người dùng nhìn thấy” mà server kiểm tra `length() <= 20`, trải nghiệm có thể thiếu công bằng hoặc khó hiểu.

Ngược lại, nếu cơ sở dữ liệu/giao thức giới hạn bytes, thì dù UI chỉ đếm một cluster, hệ thống vẫn phải kiểm tra **byte count** trước khi lưu hoặc truyền. Vì thế cần cả validation kỹ thuật và chính sách UX, không cố thay thế một bằng một.

**Lưu ý:** `\\X` không tự xác thực chuỗi Unicode có đúng UTF-16 surrogate pairs hay không. Nếu đầu vào có thể chứa surrogate lẻ hoặc dữ liệu decode lỗi, cần validation/decoder policy riêng.

## 17. Không phải mọi đơn vị hiển thị đều có cùng độ rộng

Điều quan trọng về localization: **“một grapheme cluster” không có nghĩa “một ô terminal” hay “một glyph”.** Ví dụ:

- Chữ Latin `A` thường chiếm một cột trong terminal monospace.
- Nhiều chữ CJK có thể chiếm hai cột.
- Emoji có thể được render bằng glyph màu hoặc fallback nhiều ký tự.
- Một grapheme cluster có thể có nhiều thành phần được shaping engine vẽ thành nhiều glyph.
- Một ligature của font có thể vẽ từ nhiều ký tự thành một glyph mà grapheme segmentation vẫn giữ các cluster riêng.
- Văn bản có dấu và những hệ chữ tổ hợp cần xử lý vị trí dấu, BiDi hoặc quy tắc dòng.

Do đó nếu làm căn cột terminal, tab alignment, layout hộp văn bản hoặc cắt theo pixel, cần thư viện đo **độ rộng hiển thị** phù hợp. Không dùng `Matcher.results().count()` như kích thước pixel hay số cột.

Trong xử lý chuỗi máy–máy, ngược lại, có thể cần lưu UTF-8 bytes hoặc Unicode scalar values mà không quan tâm cách font vẽ. Chọn đúng phép đo theo nhiệm vụ.

## 18. Ranh giới có thể phụ thuộc dữ liệu ở hai phía

Grapheme segmentation không phải luôn tính được bằng cách phân đoạn từng mảnh rồi cộng số cluster của chúng.

Ví dụ:

- Một dấu kết hợp ở đầu mảnh thứ hai có thể gắn vào chữ cơ sở cuối mảnh thứ nhất sau khi nối.
- Hai regional indicators ở hai mảnh có thể tạo cờ khi ghép.
- Một chuỗi emoji có ZWJ ở ranh giới có thể hợp thành cluster khi các phần được nối lại.

Do đó `countGraphemes(part1 + part2)` **không nhất thiết bằng** `countGraphemes(part1) + countGraphemes(part2)`. Nếu phải chia dữ liệu thành chunk để truyền/lưu, nên tách ở ranh giới phù hợp hoặc phân đoạn lại sau khi ghép toàn chuỗi. Không dựa vào tổng số lượng cluster từng chunk khi cần kết quả chính xác của chuỗi cuối cùng.

Khi dữ liệu văn bản được nhận theo luồng (*streaming*), một bộ phân đoạn đúng có thể cần giữ một phần ngữ cảnh ở ranh giới chunk để quyết định break. Chỉ cắt dựa vào code unit hoặc code point có thể làm hỏng đơn vị mà người dùng cảm nhận.

## 19. Những ngộ nhận phổ biến

| Ngộ nhận | Thực tế | Cách xử lý |
| --- | --- | --- |
| `String.length()` đếm ký tự màn hình | Nó đếm UTF-16 code units | Dùng grapheme segmentation nếu cần |
| Một code point bằng một chữ nhìn thấy | Dấu kết hợp, RI và emoji sequences có thể gồm nhiều code point | Phân biệt các tầng |
| `offsetByCodePoints` luôn cắt đúng glyph | Nó chỉ di chuyển theo code point | Dùng cluster boundaries cho UI |
| Cứ gặp combining mark là một cluster mới | Dấu có thể thuộc cùng cụm với chữ cơ sở | Theo UAX #29 |
| Một cờ là một code point | Cờ RI ví dụ gồm hai code point | Nhìn đúng chuỗi mã hóa |
| Emoji ZWJ luôn là một glyph trên mọi thiết bị | Rendering phụ thuộc font/nền tảng | Test rendering riêng |
| Một emoji luôn có 2 code units | Emoji sequences có thể dài hơn nhiều | Đếm đúng mục tiêu |
| `\\X` đếm cột terminal | Cluster khác display width | Dùng layout/width API |
| NFC biến mọi cluster thành một code point | Không làm được với phần lớn emoji sequences | Không nhầm normalization với segmentation |
| `BreakIterator` và regex luôn giống nhau | Implementation/data version có thể khác | Test trên runtime mục tiêu |
| Có thể cộng cluster count của từng fragment | Ranh giới có thể thay đổi khi nối | Phân đoạn lại chuỗi kết hợp |
| Chỉ cần kiểm tra emoji đơn lẻ | Lỗi thường nằm ở modifiers, flags, ZWJ | Test tổ hợp |
| `\\X` xác nhận Unicode hợp lệ | Regex phân đoạn không thay validator | Validate nguồn riêng |

## 20. Checklist kiểm thử

Một bộ test nên bao phủ:

1. **Chữ cơ bản:** `A` → 1 unit, 1 point, 1 cluster.
2. **Dấu kết hợp:** `e\u0301` → 2 units, 2 points, 1 cluster.
3. **Dựng sẵn:** `é` → 1 unit, 1 point, 1 cluster.
4. **Emoji đơn:** `😀` → 2 units, 1 point, 1 cluster.
5. **Emoji modifier:** `👍🏽` → 4 units, 2 points, 1 cluster.
6. **Cờ RI:** `🇻🇳` → 4 units, 2 points, 1 cluster.
7. **ZWJ family:** `👩‍👩‍👧‍👦` → 11 units, 7 points, 1 cluster trên runtime thử nghiệm.
8. **Emoji variation selector:** `❤️` → 2 units, 2 points, 1 cluster.
9. **Keycap:** `1️⃣` → 3 units, 3 points, 1 cluster.
10. **Ranh giới:** `Matcher.start()/end()` không cắt surrogate pair hoặc tách dấu trong các ví dụ.
11. **Giới hạn:** lấy 0, 1, 2, N cluster; đầu vào rỗng; giới hạn âm được từ chối.
12. **Normalization:** `e\u0301` và `é` cùng NFC nhưng raw code point count khác nhau.
13. **Fragment boundary:** dấu kết hợp, RI hoặc ZWJ tại chỗ ghép không làm sai logic.
14. **Unicode version:** thử chuỗi emoji mới trên JDK và nền tảng đích.
15. **UI vs server:** cách đếm server phù hợp yêu cầu giao diện, đồng thời kiểm tra byte limit riêng.

### Bài tập

1. Dùng `GraphemeCountDemo` thêm `"\r\n"` và kiểm tra cách thuật toán coi cặp CRLF khi phân đoạn. Giải thích tại sao ranh giới văn bản không chỉ là những ký tự in ra.
2. Thêm hai cặp regional indicators liên tiếp vào một chuỗi, in `Matcher.start()/end()` và xem chúng được ghép thành các cluster như thế nào.
3. Viết hàm `lastCluster(String s)` lấy cụm cuối bằng `Pattern.compile("\\X")` và thử với `e\u0301`, `👍🏽` và emoji gia đình.
4. So sánh `firstClusters(s, 1)` với `s.substring(0, 1)` khi `s` bắt đầu bằng emoji ngoài BMP hoặc dấu kết hợp; phân tích lỗi có thể xảy ra.
5. Xây validator cho “tối đa 10 cụm ký tự hiển thị” và một validator riêng cho “tối đa 100 bytes UTF-8”. Viết test khi hai kết quả cho phép/từ chối khác nhau.
6. So sánh `BreakIterator.getCharacterInstance(locale)` với regex `\\X` trên chính bản JDK đang dùng; ghi lại các khác biệt thay vì mặc định hai API tương đương hoàn toàn.
7. Thử thay `e\u0301` bằng chuỗi tiếng Việt có chữ + nhiều dấu kết hợp, rồi kiểm tra số unit, point và cluster trước/sau NFC.
8. Tạo một chuỗi có ZWJ nối các emoji và mô tả vì sao việc render có thể khác giữa thiết bị dù chuỗi Unicode giống nhau.

## 21. Tổng kết

**Grapheme cluster** là đơn vị phân đoạn văn bản quan trọng khi xây giao diện có thao tác theo “ký tự người dùng nhìn thấy”. Nó có thể chứa **một hoặc nhiều Unicode code point**; mỗi code point lại dùng **một hoặc hai UTF-16 code unit** trong Java. Dấu kết hợp, regional indicator flags, emoji skin tone modifiers, variation selectors và ZWJ sequences khiến sự khác biệt này xuất hiện thường xuyên.

Trong Java 17+, dùng `Pattern.compile("\\X")` để tìm ranh giới extended grapheme cluster theo dữ liệu Unicode của runtime; `Matcher.start()` và `end()` trả chỉ số UTF-16 dùng trực tiếp với `substring`. Dùng `codePointCount()` khi thực sự cần số code point, `String.length()` khi cần số code unit, và đếm byte nếu giao thức đặt giới hạn bytes.

Cuối cùng, **phân đoạn không phải rendering**: grapheme cluster không đảm bảo bằng một glyph, một ô terminal hoặc một độ rộng pixel. Kiểm thử các chuỗi đa ngôn ngữ và emoji trên đúng JDK, font và nền tảng của sản phẩm, và chỉ áp dụng thuật toán phân đoạn khi phù hợp với yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
- [Unicode Technical Standard #51 — Unicode Emoji](https://www.unicode.org/reports/tr51/)
- [Oracle Java 21 — Pattern, biểu thức `\\X`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Oracle Java 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle Java 21 — BreakIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html)
- [Oracle Java 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
