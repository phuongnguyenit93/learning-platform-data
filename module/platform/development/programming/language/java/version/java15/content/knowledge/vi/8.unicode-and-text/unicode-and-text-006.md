# Độ dài hiển thị khác String.length() trong Java

Trong Java, `String.length()` **không trả về số ký tự mà người đọc nhìn thấy trên màn hình**. Nó trả về **số đơn vị mã UTF-16 (*UTF-16 code units*)** của chuỗi. Với nhiều ký tự ASCII thông thường, mỗi ký tự chiếm một đơn vị mã nên hai con số thường trùng nhau. Nhưng với emoji, dấu kết hợp, chữ ghép và cách hiển thị phụ thuộc font, hai cách đo có thể khác xa nhau.

Đây là kiến thức vẫn áp dụng cho **Java 15 và các phiên bản Java hiện đại**, bất kể chương trình sử dụng string literal, text block, `String.format(...)` hay `String.formatted(...)`. Muốn đếm hoặc cắt văn bản chính xác, trước tiên phải xác định **“độ dài” có nghĩa gì đối với yêu cầu của ứng dụng**.

## 1. Có ít nhất bốn khái niệm độ dài khác nhau

| Khái niệm | Đo thứ gì? | Cách tiếp cận trong Java |
| --- | --- | --- |
| **UTF-16 code units** | Số đơn vị 16 bit của biểu diễn logic `String` | `text.length()` |
| **Unicode code points** | Số giá trị mã Unicode trong chuỗi | `text.codePointCount(0, text.length())` hoặc `text.codePoints().count()` |
| **Grapheme clusters** | Các cụm ký tự người dùng thường nhận thức như một ký tự | Regex Unicode `\\X`, hoặc thư viện/thuật toán phân đoạn Unicode phù hợp |
| **Độ rộng hiển thị** | Số pixel trên giao diện đồ họa hoặc số cột trong terminal | Đo bằng hệ thống render và font/terminal tương ứng; **không suy ra trực tiếp từ `length()`** |

Ba hàng đầu là những kiểu **đếm đơn vị**. Hàng cuối là một phép đo **trình bày**, phụ thuộc môi trường. Ngay cả khi số grapheme cluster bằng 1, ký tự đó vẫn có thể chiếm 1, 2 hoặc một số lượng pixel/cột khác nhau.

Cần phân biệt thêm **độ dài byte khi mã hóa**: `text.getBytes(StandardCharsets.UTF_8).length` đếm byte UTF-8, khác với mọi khái niệm trên. Không dùng số byte để suy luận số chữ hiển thị.

## 2. Vì sao String.length() dùng UTF-16?

API `java.lang.String.length()` trả về số *code unit*. Trong UTF-16:

- Một code point thuộc **Basic Multilingual Plane (BMP)** thường được biểu diễn bằng **một** đơn vị UTF-16. Ví dụ `A`, `é` (dạng dựng sẵn) hoặc chữ Hán `界` đều có `length() == 1`.
- Một code point **bổ sung** (ngoài BMP), như emoji `😀`, dùng **hai** đơn vị UTF-16 gọi là một *surrogate pair*. Vì thế `"😀".length() == 2` dù mắt thường thấy một emoji.
- Một chữ có dấu có thể được tạo từ **nhiều code point**: `e` + ký tự dấu sắc kết hợp `U+0301` thường hiển thị thành một chữ `é`, nhưng chuỗi `"e\u0301"` có **hai** code unit và **hai** code point.
- Một emoji tổ hợp có thể chứa nhiều code point và các ký tự nối như **zero-width joiner (ZWJ)** `U+200D`, nhưng người dùng nhìn thấy một hình biểu tượng duy nhất.

**Lưu ý kỹ thuật:** Java có thể tối ưu cách *lưu trữ vật lý* một số chuỗi trong bộ nhớ, nhưng hợp đồng của `String.length()`, `charAt(...)` và chỉ số `substring(...)` vẫn dựa trên các vị trí code unit UTF-16. Không nhầm số code unit với số byte bộ nhớ thực tế.

### Một bảng ví dụ

| Chuỗi | `String.length()` | Code points | Grapheme clusters (theo Unicode) |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| `é` dạng dựng sẵn (U+00E9) | 1 | 1 | 1 |
| `e` + dấu sắc kết hợp (U+0301) | 2 | 2 | 1 |
| `😀` | 2 | 1 | 1 |
| `🇻🇳` (hai *regional indicators*) | 4 | 2 | 1 |
| `👨‍👩‍👧‍👦` (chuỗi emoji có ZWJ) | 11 | 7 | 1 |
| `界` | 1 | 1 | 1 |

Ví dụ emoji gia đình có bốn emoji thành phần (mỗi thành phần dùng hai code unit) và ba ký tự ZWJ (mỗi ký tự một code unit): `4 × 2 + 3 = 11`. Bảy code point ấy tạo thành một **extended grapheme cluster** theo quy tắc Unicode được áp dụng cho chuỗi đó.

Các con số ở cột cuối là **số cụm văn tự**, không phải độ rộng pixel hay terminal columns. Tùy font, thiết bị và khả năng hỗ trợ emoji ZWJ, hình hiển thị có thể khác nhau.

## 3. Đếm code point bằng API chuẩn

Khi cần xử lý từng mã Unicode, dùng `codePointCount` thay vì `length`:

```java
String emoji = "😀";

System.out.println(emoji.length());                           // 2
System.out.println(emoji.codePointCount(0, emoji.length()));   // 1
System.out.println(emoji.codePoints().count());                // 1
```

`codePointCount(int beginIndex, int endIndex)` nhận **vị trí code unit UTF-16**, trong đó `endIndex` là vị trí sau phần tử cuối. Với toàn bộ chuỗi, dùng `0` và `text.length()`.

Có thể duyệt code point mà không tách nhầm surrogate pair:

```java
String emoji = "😀";
emoji.codePoints().forEach(cp ->
        System.out.printf("U+%X%n", cp));
// U+1F600
```

Để biến một code point thành một chuỗi, dùng `Character.toChars(codePoint)` khi thích hợp. Để di chuyển qua `n` code point, dùng `String.offsetByCodePoints(...)`, nhưng nhớ rằng **ranh giới code point chưa chắc là ranh giới grapheme cluster**: nó vẫn có thể tách chữ ra khỏi dấu kết hợp hoặc tách một emoji ZWJ.

Lưu ý `codePointCount` tính cả một surrogate không ghép cặp như một code point theo hợp đồng API. Nếu dữ liệu có khả năng bị hỏng hoặc chứa surrogate lẻ, cần kiểm tra tính hợp lệ Unicode riêng; phép đếm không phải bộ xác thực encoding.

## 4. Grapheme cluster: đơn vị gần với “một ký tự nhìn thấy”

**Extended grapheme cluster** là khái niệm phân đoạn văn bản do Unicode Standard Annex #29 định nghĩa. Nó thường gần với thao tác mà người dùng mong đợi khi di chuyển con trỏ, xóa một ký tự hoặc chọn một biểu tượng.

Một grapheme cluster có thể gồm:

- Một chữ ASCII đơn như `A`.
- Một ký tự có dấu đã dựng sẵn như `é`.
- Một chữ cơ sở và một hoặc nhiều dấu kết hợp như `e\u0301`.
- Một emoji ngoài BMP như `😀`.
- Một cặp ký hiệu vùng tạo cờ, như `🇻🇳`.
- Một chuỗi emoji nối bằng ZWJ, như `👨‍👩‍👧‍👦`.

Java cung cấp **regex `\\X`**, khớp một Unicode extended grapheme cluster. Trong **chuỗi Java chứa regex**, phải viết **`"\\\\X"`** (hai ký tự gạch chéo ngược trong mã nguồn Java) để `Pattern` nhận biểu thức `\\X`.

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

Pattern clusters = Pattern.compile("\\X");
Matcher matcher = clusters.matcher("e\u0301");

int count = 0;
while (matcher.find()) {
    count++;
}
System.out.println(count); // 1
```

**Đừng nhầm grapheme cluster count với chiều rộng hiển thị.** Chữ Hán `界` thường chiếm hai cột trong nhiều terminal dùng monospace, dù chỉ có một grapheme cluster. Một tab có thể đưa con trỏ đến điểm dừng tab tiếp theo, nên độ rộng của nó tùy vị trí xuất hiện trên dòng.

### Ghi chú về BreakIterator ở các phiên bản Java

`java.text.BreakIterator.getCharacterInstance(...)` là API tìm ranh giới trong văn bản. Từ **JDK 20**, implementation mặc định cho ranh giới ký tự đã được nâng cấp để tuân theo **Unicode Extended Grapheme Cluster breaks**. Khi chạy trên **JDK 17**, không nên mặc định rằng kết quả `BreakIterator` với mọi chuỗi emoji ZWJ/cờ sẽ giống các JDK mới. Vì vậy, để có một ví dụ **Java 17+** cụ thể về grapheme cluster trong bài này, ta dùng regex `\\X`; khi cần độ chính xác đặc biệt cho emoji mới, luôn xét phiên bản dữ liệu Unicode và thư viện dùng thực tế.

API `BreakIterator` vẫn hữu ích cho các loại phân đoạn như word, line hoặc sentence; hãy chọn loại iterator và môi trường phù hợp yêu cầu.

## 5. Độ rộng hiển thị thực tế còn phụ thuộc trình kết xuất

Ngay cả một phép đếm grapheme cluster chính xác cũng **không đo được chiều rộng trên màn hình**. Các yếu tố ảnh hưởng gồm:

1. **Font và cỡ chữ:** `W` và `i` mỗi chữ có `length() == 1`, nhưng có độ rộng pixel khác nhau trong font tỷ lệ.
2. **Ký tự East Asian Width:** nhiều ký tự CJK chiếm khoảng **hai cột** trong terminal monospace, dù vẫn là một code point và một grapheme cluster.
3. **Emoji và biến thể trình bày:** có emoji được render bằng glyph màu, có sequence dùng ZWJ; chiều rộng và font fallback có thể khác nhau.
4. **Dấu kết hợp:** một dấu đi với chữ cơ sở thường không thêm một ô hiển thị; nhưng `length()` vẫn đếm code unit của dấu đó.
5. **Tab, xuống dòng và ký tự điều khiển:** tab dựa vào điểm dừng tab; xuống dòng tách hàng chứ không tạo độ rộng ngang; escape ANSI trong terminal có thể chiếm nhiều code unit mà không hiện thành chữ.
6. **Chữ ghép và quy tắc shaping:** một chuỗi code point có thể tạo ligature hoặc tổ hợp glyph; độ rộng còn do script, font và hệ thống dựng chữ quyết định.

Do đó, **không thể tính độ rộng terminal một cách đáng tin cậy bằng công thức `length()`, `codePointCount(...)` hoặc chỉ bằng số `\\X`**. Đối với cột terminal, dùng thư viện đo **display columns** phù hợp terminal, Unicode width rules và cách xử lý ANSI; đối với GUI, dùng phép đo của engine render.

Ví dụ với Java Swing, đoạn mã minh họa (cần một component và font thực tế, nên không có stdout cố định):

```java
import java.awt.FontMetrics;
import javax.swing.JComponent;

static int textWidthPixels(JComponent component, String text) {
    FontMetrics metrics = component.getFontMetrics(component.getFont());
    return metrics.stringWidth(text);
}
```

Phương thức nhận `JComponent` đang có trong giao diện, đo chiều rộng gần với pixel của font ấy. Với văn bản phức tạp và yêu cầu layout chính xác, dùng engine bố cục thích hợp như `java.awt.font.TextLayout`, thay vì ép mọi glyph thành một độ rộng cố định. Trên web, trình duyệt có API đo layout thực tế riêng; phép đo phía server có thể không giống font phía client.

## 6. Chương trình Java 17+ hoàn chỉnh, có thể chạy

Chương trình sau kiểm tra **ba số đếm ổn định về ý nghĩa**: UTF-16 code units, Unicode code points và số extended grapheme clusters theo regex `\\X`. Nó **không tuyên bố** in được độ rộng pixel hoặc số cột terminal.

Lưu thành file `UnicodeLengthDemo.java` theo UTF-8:

```java
import java.text.Normalizer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeLengthDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static int graphemeCount(String text) {
        Matcher matcher = GRAPHEME.matcher(text);
        int count = 0;
        while (matcher.find()) {
            count++;
        }
        return count;
    }

    private static String firstGraphemes(String text, int limit) {
        if (limit < 0) {
            throw new IllegalArgumentException("limit must be nonnegative");
        }
        Matcher matcher = GRAPHEME.matcher(text);
        int end = 0;
        for (int i = 0; i < limit && matcher.find(); i++) {
            end = matcher.end();
        }
        return text.substring(0, end);
    }

    private static void describe(String label, String text) {
        System.out.printf("%s: units=%d, points=%d, graphemes=%d%n",
                label,
                text.length(),
                text.codePointCount(0, text.length()),
                graphemeCount(text));
    }

    public static void main(String[] args) {
        String ascii = "A";
        String composed = "\u00E9";       // é (một code point)
        String decomposed = "e\u0301";    // e + dấu sắc kết hợp
        String emoji = "\uD83D\uDE00";    // 😀
        String flag = "\uD83C\uDDFB\uD83C\uDDF3"; // 🇻🇳
        String family = "\uD83D\uDC68\u200D\uD83D\uDC69"
                + "\u200D\uD83D\uDC67\u200D\uD83D\uDC66"; // 👨‍👩‍👧‍👦

        describe("ASCII", ascii);
        describe("NFC", composed);
        describe("NFD", decomposed);
        describe("emoji", emoji);
        describe("flag", flag);
        describe("family", family);

        boolean sameAfterNfc = Normalizer
                .normalize(decomposed, Normalizer.Form.NFC)
                .equals(composed);
        System.out.println("NFC_equal=" + sameAfterNfc);

        System.out.println(
                "emoji_half_surrogate=" + Character.isHighSurrogate(emoji.charAt(0)));

        String oneVisibleCluster = firstGraphemes(decomposed + "X", 1);
        System.out.println("first_cluster_units=" + oneVisibleCluster.length());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 UnicodeLengthDemo.java
java UnicodeLengthDemo
```

Đầu ra dự kiến trên JDK hiện đại với các chuỗi mẫu đã nêu:

```text
ASCII: units=1, points=1, graphemes=1
NFC: units=1, points=1, graphemes=1
NFD: units=2, points=2, graphemes=1
emoji: units=2, points=1, graphemes=1
flag: units=4, points=2, graphemes=1
family: units=11, points=7, graphemes=1
NFC_equal=true
emoji_half_surrogate=true
first_cluster_units=2
```

Các số đếm của ví dụ được kiểm tra trên JDK 24; `\\X` được hỗ trợ từ những JDK trước Java 17. Sự thay đổi dữ liệu Unicode/thuật toán giữa các JDK có thể ảnh hưởng những sequence mới ngoài các ví dụ này. Chuỗi `family` có 11 code unit nhưng regex coi toàn bộ sequence là một grapheme cluster. Trong khi đó, `first_cluster_units=2` chứng tỏ cắt theo **một grapheme cluster** đã giữ cả chữ `e` và dấu kết hợp, thay vì giữ đúng một code unit.

Dùng `firstGraphemes` để cắt theo ranh giới người dùng thường nhận biết; đây vẫn là **giới hạn số cụm**, không phải giới hạn số pixel/cột terminal.

## 7. Vì sao substring và charAt dễ gây lỗi khi xử lý Unicode?

Các chỉ số của `String.charAt(int)`, `substring(int, int)`, `indexOf(...)` và nhiều API thao tác `String` được diễn giải theo **vị trí UTF-16 code unit**.

Ví dụ sau là thao tác **không nên dùng để cắt một ký tự hiển thị**:

```java
String emoji = "😀";
String broken = emoji.substring(0, 1);
```

Kết quả `broken` chỉ chứa một **high surrogate** không ghép cặp, không còn là emoji hoàn chỉnh. Tương tự, `"e\u0301".substring(0, 1)` chỉ giữ chữ `e` và loại mất dấu sắc. Hai ví dụ thể hiện hai loại đứt đoạn khác nhau:

- **Cắt đôi surrogate pair**: thậm chí không giữ được một code point hoàn chỉnh.
- **Cắt giữa grapheme cluster**: giữ code point hợp lệ nhưng không giữ trọn ký tự người dùng mong đợi.

Nếu cần di chuyển qua **code point**, có thể dùng `offsetByCodePoints`:

```java
String emoji = "😀X";
int boundary = emoji.offsetByCodePoints(0, 1);
String firstCodePoint = emoji.substring(0, boundary);
// firstCodePoint = "😀"; boundary = 2
```

Nhưng với `"e\u0301"`, lấy một code point vẫn chỉ cho chữ `e`. Để giới hạn theo **grapheme cluster**, dùng `\\X` hoặc bộ phân đoạn Unicode đúng mục tiêu; ví dụ `firstGraphemes(...)` trong chương trình hoàn chỉnh.

Không nên cắt chuỗi bằng `substring(0, max)` khi `max` được diễn giải là **số ký tự hiển thị**. Nếu hệ thống giới hạn byte UTF-8, việc cắt còn cần xử lý encoding và ranh giới Unicode tương ứng.

## 8. Hai chuỗi nhìn giống nhau vẫn có thể có độ dài khác nhau

Một chữ có dấu tiếng Việt hoặc châu Âu có thể có nhiều biểu diễn Unicode:

- Dạng dựng sẵn (*composed*): `é`, code point `U+00E9`.
- Dạng tách rời (*decomposed*): `e` (`U+0065`) + dấu sắc kết hợp (`U+0301`).

Chúng thường hiển thị giống nhau nhưng có `length()` khác nhau: **1 so với 2**. `String.equals(...)` so sánh nội dung code unit, nên hai chuỗi chưa chuẩn hóa **không bằng nhau**.

Khi nghiệp vụ yêu cầu so sánh hai biểu diễn Unicode tương đương về mặt chuẩn tắc, có thể chuẩn hóa:

```java
import java.text.Normalizer;

String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.equals(
        Normalizer.normalize(decomposed, Normalizer.Form.NFC))); // true
```

`Normalizer.Form.NFC` là một dạng chuẩn hóa Unicode còn được sử dụng. **Không chuẩn hóa bừa mọi dữ liệu**: so sánh tên, định danh, mật khẩu, chữ ký số, tên file và dữ liệu cần bảo toàn byte có chính sách riêng. Normalization giải quyết tính tương đương văn bản theo quy tắc Unicode, **không đo độ rộng hiển thị**, không thay thế locale-aware collation và không tự biến văn bản thành một giá trị có cùng số byte.

## 9. Chọn phép đo theo nhu cầu sản phẩm

| Mục tiêu | Chọn cơ chế | Cảnh báo |
| --- | --- | --- |
| Làm việc với chỉ số `String`, tạo `char[]`, giới hạn code unit | `length()` | Có thể cắt giữa surrogate pair hoặc grapheme cluster |
| Đếm mã Unicode để xử lý ký tự ở mức code point | `codePointCount(...)`, `codePoints()` | Nhiều code point có thể tạo một cụm nhìn thấy |
| Cho phép người dùng xóa/di chuyển theo “ký tự” | Phân đoạn Unicode grapheme clusters | Không đo độ rộng; phiên bản Unicode ảnh hưởng sequence mới |
| Giới hạn số ký tự trong một trường văn bản dành cho người dùng | Định nghĩa cụ thể giới hạn theo **grapheme cluster**, code point, byte hay yêu cầu hệ thống | Kiểm tra cùng quy tắc ở client và server |
| Cắt nhãn giao diện mà không làm hỏng emoji/dấu | Cắt theo grapheme boundary; sau đó đo theo renderer | Giới hạn số grapheme không bảo đảm vừa chiều rộng |
| Căn cột trong terminal | Dùng phép đo *terminal display width* phù hợp và xử lý tab/ANSI/emoji | CJK/emoji có thể chiếm 2 cột hoặc tùy terminal |
| Đo độ rộng text cho Swing/AWT | `FontMetrics` hoặc hệ thống layout như `TextLayout` | Chiều rộng tính bằng pixel, phụ thuộc font và bối cảnh |
| Giới hạn dung lượng UTF-8 hoặc API tính theo byte | `getBytes(StandardCharsets.UTF_8).length` | Byte khác code unit, code point, grapheme và pixel |

Với yêu cầu hiển thị, hãy đo ở **đúng lớp giao diện** và font mà người dùng thấy; số đếm từ backend thường không đủ. Với yêu cầu lưu trữ, hãy xem cơ sở dữ liệu hoặc giao thức giới hạn thứ gì. Không dùng từ “ký tự” trong đặc tả mà không nêu đơn vị đo.

## 10. Những lỗi phổ biến

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| `String.length()` là số chữ người đọc nhìn thấy | Nó đếm **UTF-16 code units** |
| `"😀".length()` phải bằng 1 | Emoji này dùng **surrogate pair**, nên bằng 2 |
| `codePointCount` luôn bằng số ký tự người dùng thấy | Một grapheme cluster có thể có nhiều code point |
| Một grapheme cluster luôn rộng một cột | CJK, emoji, font tỷ lệ và môi trường render làm độ rộng thay đổi |
| `substring(0, n)` luôn cắt an toàn sau n “ký tự” | `n` tính bằng code unit và có thể chia đôi surrogate hoặc mất dấu kết hợp |
| Chuẩn hóa NFC khiến chuỗi luôn có cùng độ rộng hiển thị | Normalization không thay thế layout/rendering |
| Dùng `BreakIterator` trên mọi bản Java cho cùng ranh giới emoji ZWJ | JDK 20 đã cải thiện implementation; cần kiểm tra phiên bản chạy và phiên bản Unicode |
| Dùng `length()` để căn cột terminal | Cần chiều rộng hiển thị theo terminal, không phải số code unit |
| Code point và byte UTF-8 là một | UTF-8 là mã hóa byte, thường dùng số byte khác biệt |

## 11. Tự kiểm tra

Xét bốn giá trị dưới đây (đoạn mã minh họa, có thể đặt trong một phương thức):

```java
String a = "A";
String b = "\uD83D\uDE00";       // 😀
String c = "e\u0301";            // e + combining acute
String d = "\uD83C\uDDFB\uD83C\uDDF3"; // 🇻🇳
```

**Câu hỏi:**

1. Giá trị `length()` và `codePointCount(0, length())` của từng chuỗi là bao nhiêu?
2. Chuỗi nào có hơn một code point nhưng vẫn tạo một extended grapheme cluster?
3. Có thể lấy `b.substring(0, 1)` để hiển thị nguyên vẹn emoji không?
4. Nếu người dùng muốn căn một bảng bằng độ rộng cột terminal, `codePointCount(...)` đã đủ chưa?

**Đáp án:** (1) `a` có 1/1; `b` có 2/1; `c` có 2/2; `d` có 4/2 (trước/sau dấu `/` lần lượt là code units/code points). (2) `c` và `d`. (3) Không; phép cắt sẽ để lại một high surrogate lẻ. (4) Chưa; cần đo chiều rộng hiển thị theo terminal, kể cả độ rộng của emoji, CJK, tab và các quy tắc rendering.

## Tài liệu còn áp dụng

- [Oracle Java SE 26 API — String](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): `length()`, `codePointCount(...)`, `offsetByCodePoints(...)`, `codePoints()`.
- [Oracle Java SE 26 API — Pattern](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html): Unicode extended grapheme matcher `\\X`.
- [Oracle Java SE 26 API — BreakIterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/BreakIterator.html): phân đoạn ranh giới ký tự/ngôn ngữ.
- [Oracle JDK 20 Release Notes — Grapheme Support in BreakIterator](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html): hành vi mới so với các JDK trước.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): định nghĩa extended grapheme clusters.