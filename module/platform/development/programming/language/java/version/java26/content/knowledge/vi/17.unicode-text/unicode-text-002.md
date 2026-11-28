# Code point, UTF-16 code unit và ký tự người dùng nhìn thấy

*Tình trạng được đối chiếu với Java 26 và Unicode 17.0 tại ngày 27/11/2026.*

Khi xử lý văn bản, từ “ký tự” có thể chỉ ba đơn vị khác nhau:

1. **UTF-16 code unit**: một đơn vị 16 bit mà Java biểu diễn bằng kiểu char.
2. **Unicode code point**: một giá trị mã Unicode, ví dụ U+1F600.
3. **Extended grapheme cluster (EGC)**: một cụm code point thường tương ứng với một ký tự mà người dùng cảm nhận khi đọc, chọn hoặc xóa văn bản.

Ba đơn vị này không luôn có số lượng bằng nhau. String.length() đếm UTF-16 code unit; String.codePointCount() đếm code point; còn số ký tự người dùng nhìn thấy cần phân đoạn theo grapheme cluster.

Java 26 dùng Unicode 17.0 cho dữ liệu ký tự, chuẩn hóa và phân đoạn văn bản. JDK 26 cũng hỗ trợ Extended Grapheme Clusters trong regex theo Unicode Standard Annex #29. Đây là năng lực của API chuẩn, không phải preview hay incubator.

## 1. Ba cấp độ biểu diễn văn bản

| Đơn vị | Ý nghĩa | API Java tiêu biểu | Dùng khi |
|---|---|---|---|
| UTF-16 code unit | Một giá trị char 16 bit | String.length(), charAt(), chars() | Index của String, thao tác mức UTF-16 |
| Unicode code point | Một giá trị mã Unicode | codePointAt(), codePoints(), codePointCount() | Phân loại, duyệt và xử lý từng code point |
| Extended grapheme cluster | Một cụm code point theo quy tắc phân đoạn Unicode | BreakIterator.getCharacterInstance(), regex \X | Đếm, chọn, di chuyển con trỏ hoặc xóa ký tự người dùng cảm nhận |

Ví dụ một chữ cái có dấu tiếng Việt có thể được lưu bằng một code point dựng sẵn hoặc bằng chữ cái gốc cộng các dấu kết hợp. Emoji ngoài Basic Multilingual Plane cần hai UTF-16 code unit. Emoji gia đình có thể gồm nhiều emoji và ký tự nối nhưng vẫn được phân đoạn thành một grapheme cluster.

Không nên dùng char như từ đồng nghĩa với “ký tự Unicode”. char là một code unit của UTF-16; nó không đủ để biểu diễn riêng một code point nằm ngoài Basic Multilingual Plane và cũng không đại diện đầy đủ cho một ký tự người dùng nhìn thấy.

## 2. UTF-16 code unit và surrogate pair

Java biểu diễn nội dung String theo UTF-16. Một code point trong Basic Multilingual Plane (BMP), từ U+0000 đến U+FFFF, thường dùng một code unit. Các code point bổ sung (supplementary code points), từ U+10000 đến U+10FFFF, được biểu diễn bằng hai code unit gọi là surrogate pair:

- High surrogate: U+D800 đến U+DBFF.
- Low surrogate: U+DC00 đến U+DFFF.

Ví dụ emoji 😀 có code point U+1F600. Trong UTF-16, nó cần một high surrogate và một low surrogate. Vì vậy, String.length() trả về 2 dù chỉ có một code point.

```java
String face = new String(Character.toChars(0x1F600));

System.out.println(face.length());                 // 2 code units
System.out.println(face.codePointCount(0, face.length())); // 1 code point
System.out.printf("U+%X%n", face.codePointAt(0));  // U+1F600
```

Character.toChars(int) chuyển một code point thành một hoặc hai char. Dùng phương thức này khi cần tạo String từ code point ngoài BMP. Không ép một code point lớn hơn U+FFFF sang char, vì việc ép kiểu sẽ làm mất thông tin.

### Vì sao charAt() có thể chỉ trả về một nửa ký tự?

```java
String face = new String(Character.toChars(0x1F600));

char first = face.charAt(0);
char second = face.charAt(1);

System.out.println(Character.isHighSurrogate(first)); // true
System.out.println(Character.isLowSurrogate(second)); // true
```

charAt() trả về code unit tại index được chỉ định. Nếu index trỏ vào high surrogate, kết quả chỉ là nửa đầu của cặp. Điều này đúng với hợp đồng API vì index của String là index UTF-16, không phải index code point.

Các phương thức Character nhận char cũng không thể phân loại một supplementary code point hoàn chỉnh. Khi xử lý code point, hãy dùng overload nhận int, ví dụ Character.isLetter(int) hoặc Character.getType(int).

## 3. Duyệt code point đúng cách

String cung cấp các API để duyệt code point thay vì duyệt từng code unit:

- codePointAt(index) đọc code point bắt đầu tại UTF-16 index.
- codePointBefore(index) đọc code point ngay trước UTF-16 index.
- codePointCount(beginIndex, endIndex) đếm code point trong đoạn được xác định bằng UTF-16 index.
- offsetByCodePoints(index, offset) tìm UTF-16 index sau khi dịch một số code point.
- codePoints() tạo IntStream chứa các code point.

Ví dụ duyệt toàn bộ code point:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";

text.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp)
);
```

Kết quả là ba code point: A, U+1F600 và B. Nếu dùng text.chars(), stream nhận bốn giá trị code unit: A, high surrogate, low surrogate và B.

| API | Giá trị được duyệt |
|---|---|
| chars() | Mỗi UTF-16 code unit được chuyển thành int, surrogate được giữ nguyên |
| codePoints() | Ghép surrogate pair hợp lệ thành một code point; các code unit khác được đưa ra riêng |

Một lưu ý quan trọng: codePointAt() nhận **UTF-16 index**, không nhận code point index. Tương tự, codePointCount() nhận hai mốc UTF-16. offsetByCodePoints() nhận một UTF-16 index ban đầu và trả về UTF-16 index mới. Các API này giúp tránh cắt đôi surrogate pair khi cần dịch theo code point, nhưng chúng chưa giải quyết việc cắt giữa base character và combining mark.

### Tránh duyệt bằng char khi cần xử lý Unicode

Mẫu sau chỉ duyệt code unit:

```java
for (int i = 0; i < text.length(); i++) {
    char ch = text.charAt(i);
    // ch có thể là một nửa của surrogate pair
}
```

Nếu mục tiêu là phân loại hoặc xử lý từng code point, dùng:

```java
text.codePoints().forEach(cp -> {
    if (Character.isLetter(cp)) {
        // Xử lý một Unicode code point dạng chữ
    }
});
```

Cách này xử lý được supplementary code point. Tuy nhiên, nó vẫn xử lý từng code point riêng lẻ; một chữ cái kèm dấu kết hợp có thể có nhiều code point và sẽ đi qua lambda nhiều lần.

## 4. Code point không đồng nghĩa với ký tự người dùng nhìn thấy

Unicode cho phép một đơn vị chữ viết được biểu diễn bằng nhiều code point. Ví dụ chữ ấ có thể được biểu diễn bằng:

- Một code point dựng sẵn: U+1EA5.
- Ba code point: U+0061 LATIN SMALL LETTER A, U+0302 COMBINING CIRCUMFLEX ACCENT và U+0301 COMBINING ACUTE ACCENT.

Hai chuỗi có thể hiển thị giống nhau nhưng có số code unit và code point khác nhau:

```java
String composed = "\u1EA5";         // ấ: một code point
String decomposed = "a\u0302\u0301"; // a + circumflex + acute

System.out.println(composed.length());   // 1
System.out.println(decomposed.length()); // 3

System.out.println(composed.codePointCount(0, composed.length())); // 1
System.out.println(decomposed.codePointCount(0, decomposed.length())); // 3
```

Trong ngữ cảnh đọc và chỉnh sửa văn bản, cả hai thường được xem là một ký tự người dùng nhìn thấy. Unicode mô hình hóa đơn vị này bằng **grapheme cluster**. Extended Grapheme Cluster là quy tắc mặc định được khuyến nghị trong UAX #29 để xác định ranh giới các cụm như vậy.

Một số trường hợp phổ biến:

- Chữ cái cơ sở cộng combining mark: a + dấu mũ + dấu sắc.
- Emoji cộng skin-tone modifier.
- Cờ được tạo từ hai Regional Indicator code point.
- Chuỗi emoji có Zero Width Joiner (ZWJ), ví dụ emoji gia đình.

Grapheme cluster là một phép xấp xỉ có quy tắc cho “ký tự người dùng cảm nhận”, không phải bảo đảm rằng mọi cụm đều tương ứng chính xác với một glyph hay một đơn vị ngôn ngữ trong mọi ngữ cảnh. Một số ngôn ngữ hoặc tác vụ có thể cần quy tắc phân đoạn riêng.

## 5. Ví dụ emoji ZWJ: nhiều code point nhưng một grapheme cluster

Emoji gia đình có thể được biểu diễn bằng bốn emoji người, nối với nhau bằng ba U+200D ZERO WIDTH JOINER:

```java
String family = new StringBuilder()
        .appendCodePoint(0x1F468) // man
        .appendCodePoint(0x200D)  // ZWJ
        .appendCodePoint(0x1F469) // woman
        .appendCodePoint(0x200D)
        .appendCodePoint(0x1F467) // girl
        .appendCodePoint(0x200D)
        .appendCodePoint(0x1F466) // boy
        .toString();

System.out.println(family.length()); // 11 UTF-16 code units
System.out.println(family.codePointCount(0, family.length())); // 7 code points
```

Theo quy tắc Extended Grapheme Cluster của Unicode 17, chuỗi emoji này được phân đoạn thành một grapheme cluster. Điều đó cho thấy ba phép đếm khác nhau:

| Chuỗi | UTF-16 code units | Code points | Extended grapheme clusters |
|---|---:|---:|---:|
| A | 1 | 1 | 1 |
| 😀 | 2 | 1 | 1 |
| ấ dựng sẵn (U+1EA5) | 1 | 1 | 1 |
| a + dấu mũ + dấu sắc | 3 | 3 | 1 |
| Emoji gia đình dùng ZWJ ở ví dụ trên | 11 | 7 | 1 |

Nếu ứng dụng giới hạn số “ký tự” người dùng nhập, dùng số grapheme cluster phù hợp hơn String.length() hoặc codePointCount(). Nếu giới hạn dung lượng lưu trữ hoặc payload, cần đo số byte theo charset riêng; grapheme count không phải byte count.

## 6. Đếm và tách grapheme cluster bằng BreakIterator

Java 26 cung cấp BreakIterator.getCharacterInstance() để tìm ranh giới ký tự. Default implementation của Java 26 tuân theo Unicode Extended Grapheme Cluster breaks trong UAX #29.

Ví dụ tách chuỗi thành các grapheme cluster:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class GraphemeSegments {
    static List<String> splitGraphemes(String text) {
        BreakIterator iterator =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        iterator.setText(text);

        List<String> clusters = new ArrayList<>();
        int start = iterator.first();

        for (int end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {
            clusters.add(text.substring(start, end));
        }

        return List.copyOf(clusters);
    }

    static int countGraphemes(String text) {
        return splitGraphemes(text).size();
    }
}
```

Các index do BreakIterator trả về là offset trong chuỗi UTF-16. Vì ranh giới được xác định theo grapheme cluster, dùng chúng với substring(start, end) sẽ lấy nguyên cụm, không cắt giữa surrogate pair hoặc combining sequence theo quy tắc phân đoạn đang áp dụng.

Có thể dùng BreakIterator cho:

- Di chuyển con trỏ theo ký tự người dùng nhìn thấy.
- Xóa một grapheme cluster bằng phím Backspace.
- Chọn một cụm khi kéo chuột hoặc điều hướng bằng bàn phím.
- Đếm số ký tự hiển thị trong trường nhập liệu.
- Cắt văn bản theo giới hạn grapheme cluster.

Không dùng BreakIterator.getWordInstance() để đếm ký tự. Word iterator và character iterator phân tích hai loại ranh giới khác nhau. Cũng không dùng character iterator cho tokenizer mã nguồn; tài liệu API định hướng các iterator mặc định cho văn bản ngôn ngữ tự nhiên.

## 7. Dùng regex \X và ranh giới \b{g}

Java regex hỗ trợ hai cấu trúc dành cho Extended Grapheme Cluster:

- \X: khớp một extended grapheme cluster.
- \b{g}: khớp tại một ranh giới extended grapheme cluster.

Trong Java string literal, phải viết hai dấu gạch chéo ngược để truyền \X cho regex engine:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexGraphemes {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    static List<String> split(String text) {
        List<String> result = new ArrayList<>();
        Matcher matcher = GRAPHEME.matcher(text);

        while (matcher.find()) {
            result.add(matcher.group());
        }

        return List.copyOf(result);
    }
}
```

Có thể dùng \X khi muốn tận dụng API regex trong pipeline xử lý chuỗi. BreakIterator thường dễ đọc hơn khi ứng dụng cần thao tác trực tiếp với vị trí ranh giới và offset. Cả hai cách đều dựa trên Extended Grapheme Cluster; hãy kiểm tra phiên bản Unicode của runtime nếu kết quả phân đoạn cần nhất quán giữa nhiều JDK.

Không nhầm \b với \b{g}. \b là ranh giới từ theo định nghĩa word character của regex; \b{g} là ranh giới grapheme cluster. Chúng phục vụ mục đích khác nhau.

## 8. Chọn API theo đơn vị cần xử lý

| Yêu cầu | API nên dùng | Lý do |
|---|---|---|
| Lấy code unit tại một vị trí UTF-16 | charAt(index) | Trả về một char |
| Đọc code point tại UTF-16 offset | codePointAt(index) | Ghép surrogate pair hợp lệ |
| Duyệt code point | codePoints() | Tránh xử lý hai nửa surrogate riêng |
| Đếm code point | codePointCount(begin, end) | Đếm code point trong vùng UTF-16 |
| Dịch index theo code point | offsetByCodePoints(index, offset) | Không cắt đôi surrogate pair |
| Đếm/tách ký tự người dùng nhìn thấy | BreakIterator.getCharacterInstance() hoặc regex \X | Dựa trên Extended Grapheme Cluster |
| Đo payload UTF-8 | getBytes(StandardCharsets.UTF_8).length | Đếm byte sau encoding |

Ví dụ chọn hai code point đầu tiên trong một chuỗi hỗn hợp:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";

int end = text.offsetByCodePoints(0, 2);
String firstTwoCodePoints = text.substring(0, end);
```

end là UTF-16 offset sau A và emoji. Cách này không cắt giữa surrogate pair. Nhưng nếu hai code point đầu tiên là a và combining circumflex, substring vẫn có thể kết thúc giữa một grapheme cluster. Khi cần cắt theo ký tự người dùng nhìn thấy, dùng ranh giới từ BreakIterator hoặc \X.

## 9. Chuẩn hóa Unicode là vấn đề khác với phân đoạn grapheme

Hai chuỗi có thể nhìn giống nhau nhưng có chuỗi code point khác nhau. Ví dụ chữ ấ dựng sẵn và dạng a cộng hai combining mark thường có quan hệ tương đương canonical.

String.equals() so sánh chuỗi code unit chính xác; nó không tự chuẩn hóa Unicode. Nếu nghiệp vụ cần so sánh các dạng canonical tương đương, có thể chuẩn hóa cả hai về cùng một dạng bằng Normalizer:

```java
import java.text.Normalizer;

String composed = "\u1EA5";
String decomposed = "a\u0302\u0301";

System.out.println(composed.equals(decomposed)); // false

String normalizedA =
        Normalizer.normalize(composed, Normalizer.Form.NFC);
String normalizedB =
        Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(normalizedA.equals(normalizedB)); // true
```

Các dạng phổ biến:

- NFC: canonical decomposition rồi canonical composition; thường hữu ích để lưu văn bản ở dạng chuẩn hóa gọn.
- NFD: canonical decomposition.
- NFKC và NFKD: có thêm compatibility decomposition/composition; có thể làm mất khác biệt có ý nghĩa trong một số văn bản.

Chuẩn hóa không phải phân đoạn grapheme. Nó có thể thay đổi chuỗi code point nhưng không phải công cụ đếm ký tự người dùng nhìn thấy. Không chuẩn hóa dữ liệu nhị phân, token, chữ ký, mật khẩu hoặc định danh opaque một cách tùy tiện; chỉ áp dụng khi hợp đồng dữ liệu và chính sách bảo mật cho phép.

Java 26 nâng dữ liệu Normalizer theo Unicode 17.0 và UAX #15. Khi cần tương thích chính xác giữa các hệ thống, hãy thống nhất normalization form và phiên bản Unicode hoặc kiểm thử trên runtime mục tiêu.

## 10. UTF-8 byte count không phải character count

String là chuỗi UTF-16 ở cấp API. Khi truyền qua mạng hoặc ghi file, văn bản thường được encode thành byte bằng UTF-8. Một Unicode scalar value có thể chiếm từ một đến bốn byte UTF-8; một grapheme cluster có thể chứa nhiều scalar value và vì thế có thể chiếm nhiều byte hơn. Surrogate đơn lẻ không phải scalar value hợp lệ để mã hóa UTF-8.

```java
import java.nio.charset.StandardCharsets;

String text = "A" + new String(Character.toChars(0x1F600));

int utf16Units = text.length();
int codePoints = text.codePointCount(0, text.length());
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;

System.out.println(utf16Units);
System.out.println(codePoints);
System.out.println(utf8Bytes);
```

Dùng charset tường minh như StandardCharsets.UTF_8 khi encode/decode dữ liệu trao đổi. Không dùng số grapheme cluster để kiểm tra giới hạn byte của HTTP payload hoặc database column. Nếu form cần giới hạn cả trải nghiệm người dùng và dung lượng lưu trữ, áp dụng hai kiểm tra độc lập: số grapheme cluster và số byte sau encoding.

## 11. Unicode 17.0 trong Java 26 và tính tương thích

JDK 26 nâng Unicode support lên **Unicode 17.0**:

- Character sử dụng Unicode Character Database 17.0, bổ sung 4.803 ký tự và bốn script mới.
- Normalizer hỗ trợ Unicode Standard Annex #15 phiên bản tương ứng.
- Bidi hỗ trợ cập nhật theo Unicode Standard Annex #9.
- java.util.regex hỗ trợ Extended Grapheme Clusters theo UAX #29.

Điều này ảnh hưởng đến việc nhận diện ký tự mới, phân loại chữ/số, tên ký tự, chuẩn hóa và ranh giới grapheme. Một code point mới có thể được nhận diện khác nhau giữa JDK 25 và JDK 26 vì hai release dùng phiên bản Unicode khác nhau.

Khi triển khai trên nhiều runtime:

1. Ghi rõ JDK release và phiên bản Unicode được runtime hỗ trợ.
2. Dùng cùng phiên bản JDK trong test và production nếu logic phụ thuộc thuộc tính Unicode mới.
3. Kiểm thử ký tự thuộc script mới, combining mark, emoji modifier, regional indicator và ZWJ sequence.
4. Nếu client và server dùng phiên bản Unicode khác nhau, không giả định chúng luôn đếm hoặc phân đoạn mọi chuỗi mới giống nhau.
5. Cân nhắc cập nhật JDK khi cần hỗ trợ các ký tự được bổ sung sau Unicode 17.0.

Unicode tiếp tục được cập nhật độc lập với Java release. Vì vậy, “một code point hợp lệ” và “runtime đã biết thuộc tính của code point đó” là hai vấn đề cần phân biệt. Không nên hard-code danh sách ký tự hoặc giả định dữ liệu Unicode của mọi JDK giống nhau.

## 12. Kiểm thử các trường hợp dễ sai

Một bộ kiểm thử văn bản nên có tối thiểu các trường hợp sau:

- ASCII: một code unit, một code point, một grapheme cluster.
- Supplementary code point: một code point nhưng hai UTF-16 code unit.
- Chữ có dấu dựng sẵn và dạng decomposed.
- Emoji có skin-tone modifier.
- Cờ tạo từ hai Regional Indicator.
- Emoji ZWJ sequence.
- Chuỗi có combining mark liên tiếp.
- UTF-16 chứa unpaired surrogate nếu dữ liệu đầu vào không đáng tin cậy.
- Chuỗi rỗng và chuỗi chỉ có combining mark.

Không chỉ kiểm thử số lượng. Hãy kiểm tra ranh giới khi cắt chuỗi, di chuyển con trỏ, xóa lùi và giới hạn độ dài trường nhập liệu. Với văn bản người dùng, một lỗi cắt giữa surrogate pair hoặc combining sequence có thể làm hỏng hiển thị dù code vẫn chạy mà không ném exception.

Java String có thể chứa unpaired surrogate. codePoints() ghép các surrogate pair hợp lệ; một surrogate không ghép cặp được đưa ra như một giá trị riêng. Nếu hệ thống yêu cầu văn bản Unicode well-formed, cần kiểm tra UTF-16 trước khi encode hoặc lưu trữ. Đừng cho rằng gọi codePoints() tự động xác thực chuỗi.

Có thể kiểm tra cặp surrogate bằng cách duyệt code unit:

```java
static boolean isWellFormedUtf16(String text) {
    for (int i = 0; i < text.length(); i++) {
        char ch = text.charAt(i);

        if (Character.isHighSurrogate(ch)) {
            if (i + 1 >= text.length()
                    || !Character.isLowSurrogate(text.charAt(i + 1))) {
                return false;
            }
            i++; // Bỏ qua low surrogate đã ghép cặp.
        } else if (Character.isLowSurrogate(ch)) {
            return false; // Low surrogate không có high surrogate đứng trước.
        }
    }
    return true;
}
```

Nếu cần encoder báo lỗi thay vì tự thay thế dữ liệu không hợp lệ, dùng `CharsetEncoder` với `CodingErrorAction.REPORT`. Chính sách xử lý unpaired surrogate phải được xác định trước khi ghi dữ liệu ra hệ thống khác.

## 13. Checklist chọn đúng đơn vị

- [ ] Cần thao tác mức lưu trữ/index UTF-16? Dùng char và String.length() với hiểu biết rằng đây là code unit.
- [ ] Cần xử lý mọi code point, gồm supplementary characters? Dùng int, codePoints() và overload Character nhận int.
- [ ] Cần đếm ký tự người dùng nhìn thấy? Dùng Extended Grapheme Cluster qua BreakIterator hoặc regex \X.
- [ ] Cần dịch vị trí mà không cắt surrogate pair? Dùng offsetByCodePoints().
- [ ] Cần cắt nguyên một grapheme cluster? Dùng boundary offset của BreakIterator hoặc kết quả \X.
- [ ] Cần so sánh văn bản canonical-equivalent? Xác định normalization form và dùng Normalizer phù hợp.
- [ ] Cần giới hạn payload? Đếm byte sau khi encode bằng charset đã thống nhất.
- [ ] Cần xử lý ký tự Unicode mới? Kiểm tra phiên bản Unicode mà JDK mục tiêu hỗ trợ.
- [ ] Cần dữ liệu Unicode nhất quán giữa client và server? Khóa runtime/version hoặc dùng một thư viện Unicode có version rõ ràng.

## Tài liệu tham chiếu

1. [Oracle Java SE 26 API – Character](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html)
2. [Oracle Java SE 26 API – String](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html)
3. [Oracle Java SE 26 API – BreakIterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/BreakIterator.html)
4. [Oracle Java SE 26 API – Pattern](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html)
5. [Oracle Java SE 26 API – Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html)
6. [JDK 26 Release Notes – Support for Unicode 17.0](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
7. [Unicode Standard Annex #29 – Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
8. [Unicode Standard Annex #15 – Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)

