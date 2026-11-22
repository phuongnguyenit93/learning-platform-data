# Unicode 15.0 trong Java 21 và giới hạn của xử lý theo char

Java 21 sử dụng dữ liệu ký tự Unicode 15.0 trong API `Character`. Tuy nhiên, `char` trong Java là một đơn vị mã UTF-16 16 bit, không phải lúc nào cũng là một ký tự Unicode hoàn chỉnh. Các ký tự ngoài Basic Multilingual Plane (BMP), chẳng hạn nhiều emoji và chữ viết bổ sung, được biểu diễn bằng **hai `char`** gọi là surrogate pair.

Vì vậy, các thao tác như `length()`, `charAt()` và vòng lặp tăng chỉ số từng đơn vị có thể không tương ứng với số lượng ký tự Unicode mà người dùng nhìn thấy. Khi cần xử lý theo code point, hãy dùng các API nhận `int` như `codePointAt`, `codePoints`, `codePointCount` và `offsetByCodePoints`. Nếu cần xử lý ký tự hiển thị, còn phải tính đến grapheme cluster, normalization và quy tắc locale.

## 1. Unicode 15.0 trong Java 21

Unicode là chuẩn gán mã và thuộc tính cho ký tự của nhiều hệ chữ viết, dấu kết hợp, ký hiệu, emoji và các ký tự điều khiển. Mỗi giá trị mã được gọi là **code point**, ký hiệu thường viết `U+XXXX`.

Java 21 dựa trên Unicode 15.0 cho các thuộc tính ký tự mà `Character` cung cấp, chẳng hạn phân loại chữ cái, chữ số, dấu kết hợp và chuyển đổi hoa/thường ở mức ký tự. Điều này có nghĩa một code point mới được bổ sung trong Unicode 15.0 có thể được nhận diện theo các thuộc tính tương ứng trong JDK 21.

Không nên hiểu Unicode 15.0 là “Java chỉ lưu được ký tự đến phiên bản 15”. `String` lưu các đơn vị mã UTF-16; dữ liệu ký tự và thuộc tính Unicode được dùng bởi các API là một vấn đề khác. Cũng cần phân biệt phiên bản Unicode với charset như UTF-8: Unicode xác định tập ký tự và thuộc tính, còn UTF-8/UTF-16 xác định cách mã hóa code point thành byte hoặc code unit.

Ví dụ kiểm tra một số thuộc tính:

```java
public class UnicodeVersionDemo {
    public static void main(String[] args) {
        int latinA = 'A';
        int rocket = 0x1F680;

        System.out.println(Character.isLetter(latinA));
        System.out.println(Character.isLetter(rocket));
        System.out.println(Character.isValidCodePoint(rocket));
        System.out.println(Character.toString(rocket));
    }
}
```

`Character` có overload nhận `int` để xử lý code point. Với ký tự supplementary, hãy ưu tiên overload `int`; overload chỉ nhận `char` không thể biểu diễn một code point nằm ngoài BMP.

## 2. Phân biệt char, code unit, code point và grapheme cluster

Các khái niệm này giải quyết những lớp khác nhau của văn bản:

- **`char` / UTF-16 code unit:** kiểu nguyên thủy 16 bit trong Java. Một `char` có thể biểu diễn một code point thuộc BMP không nằm trong vùng surrogate, hoặc một nửa của surrogate pair.
- **Code point:** một giá trị Unicode từ `U+0000` đến `U+10FFFF`, ngoại trừ vùng surrogate không phải scalar value hợp lệ để mã hóa văn bản Unicode.
- **Surrogate pair:** hai code unit UTF-16, một high surrogate và một low surrogate, cùng mã hóa một code point supplementary.
- **Grapheme cluster:** một chuỗi code point được xem là một đơn vị ký tự hiển thị theo quy tắc phân đoạn văn bản. Một cluster có thể gồm nhiều code point, ví dụ chữ cái và combining mark hoặc emoji ghép bằng ZWJ.

Ví dụ về số lượng khác nhau:

| Nội dung | Số code point | Số UTF-16 code unit (`String.length()`) | Ghi chú |
|---|---:|---:|---|
| `A` | 1 | 1 | Ký tự BMP |
| `🚀` | 1 | 2 | Code point supplementary |
| `e` + dấu sắc kết hợp (`e\u0301`) | 2 | 2 | Thường hiển thị như một grapheme cluster |
| Emoji gia đình có ZWJ | Nhiều | Nhiều | Có thể hiển thị như một grapheme cluster |

Không có một phép đếm duy nhất phù hợp cho mọi mục đích. Giới hạn độ dài cột trong database có thể tính theo byte hoặc code unit; giới hạn giao diện có thể tính theo grapheme cluster; thuật toán phân loại Unicode thường làm việc theo code point. Hãy xác định đơn vị cần đo trước khi chọn API.

## 3. Vì sao xử lý từng char có thể sai?

`String.length()` trả về số UTF-16 code unit, còn `charAt(index)` trả về một code unit. Với chuỗi có emoji, hai chỉ số liên tiếp có thể là hai nửa của cùng một code point.

```java
String text = "A🚀B";

System.out.println(text.length()); // 4 code units
System.out.println(text.charAt(1)); // high surrogate, không phải rocket hoàn chỉnh
System.out.println(text.charAt(2)); // low surrogate
```

Vòng lặp kiểu sau không xử lý đúng mọi code point:

```java
for (int i = 0; i < text.length(); i++) {
    char ch = text.charAt(i);
    System.out.println(Character.isLetter(ch));
}
```

Với `🚀`, vòng lặp nhìn thấy hai surrogate riêng. Các hàm nhận `char` không thể nhận biết đó là một code point supplementary. Nếu cần phân loại Unicode, duyệt theo code point:

```java
text.codePoints().forEach(codePoint -> {
    System.out.printf("U+%04X%n", codePoint);
    System.out.println(Character.isLetter(codePoint));
});
```

Kết quả code point của chuỗi `A🚀B` lần lượt là `U+0041`, `U+1F680` và `U+0042`.

## 4. Duyệt String theo code point

### Dùng codePoints()

`String.codePoints()` trả về `IntStream` chứa code point được giải mã từ UTF-16. Đây là lựa chọn gọn khi cần lọc, đếm hoặc biến đổi theo code point:

```java
String text = "A🚀B";

long count = text.codePoints().count();
System.out.println(count); // 3

text.codePoints()
        .filter(Character::isLetter)
        .map(Character::toUpperCase)
        .forEach(cp -> System.out.print(Character.toString(cp)));
```

`codePoints()` tạo stream theo thứ tự chuỗi. Một surrogate pair hợp lệ được đưa ra như một code point; surrogate đơn lẻ không ghép thành pair vẫn được đưa ra như giá trị code unit tương ứng. Nếu dữ liệu có thể chứa UTF-16 không hợp lệ, cần quyết định rõ cách kiểm tra hoặc từ chối.

### Dùng codePointAt() và offsetByCodePoints()

Khi cần duyệt bằng vòng lặp hoặc thao tác tại một vị trí cụ thể, dùng `codePointAt` và `Character.charCount` để tăng chỉ số đúng số code unit:

```java
String text = "A🚀B";

for (int index = 0; index < text.length();) {
    int codePoint = text.codePointAt(index);
    System.out.printf("U+%04X%n", codePoint);
    index += Character.charCount(codePoint);
}
```

`Character.charCount(codePoint)` trả về 1 với code point BMP và 2 với code point supplementary. Cách này giúp không tách surrogate pair hợp lệ.

Nếu cần tính vị trí code unit tương ứng với một số lượng code point tính từ đầu:

```java
String text = "A🚀B";

int indexAfterTwoCodePoints = text.offsetByCodePoints(0, 2);
System.out.println(indexAfterTwoCodePoints); // 3 UTF-16 code units
System.out.println(text.charAt(indexAfterTwoCodePoints)); // B
```

`offsetByCodePoints` trả về chỉ số UTF-16, không phải chỉ số code point. Điều này hữu ích khi một API khác yêu cầu index theo `String`, nhưng cần nhớ hai hệ chỉ số khác nhau.

## 5. Đếm code point và tạo chuỗi từ code point

`codePointCount(beginIndex, endIndex)` đếm số code point trong đoạn UTF-16 được chỉ định:

```java
String text = "A🚀B";

int codePoints = text.codePointCount(0, text.length());
System.out.println(codePoints); // 3
```

Để tạo chuỗi từ một code point, dùng `Character.toChars` hoặc `StringBuilder.appendCodePoint`:

```java
int rocket = 0x1F680;

String rocketText = new String(Character.toChars(rocket));
System.out.println(rocketText); // 🚀

StringBuilder builder = new StringBuilder();
builder.appendCodePoint('A');
builder.appendCodePoint(rocket);
builder.appendCodePoint('B');

System.out.println(builder); // A🚀B
```

Trước khi nhận một giá trị `int` không tin cậy làm code point, có thể kiểm tra bằng `Character.isValidCodePoint`. Lưu ý vùng surrogate `U+D800`–`U+DFFF` nằm trong khoảng số mà `isValidCodePoint` chấp nhận, nhưng không phải Unicode scalar value hợp lệ. Nếu cần bảo đảm scalar value, hãy từ chối các giá trị surrogate:

```java
static boolean isUnicodeScalarValue(int codePoint) {
    return Character.isValidCodePoint(codePoint)
            && (codePoint < Character.MIN_SURROGATE
                || codePoint > Character.MAX_SURROGATE);
}
```

## 6. Surrogate pair và UTF-16

UTF-16 dùng một code unit cho code point trong BMP ngoài vùng surrogate, và hai code unit cho code point supplementary. Hai vùng surrogate được chia như sau:

- High surrogate: `U+D800` đến `U+DBFF`.
- Low surrogate: `U+DC00` đến `U+DFFF`.

Một pair hợp lệ gồm high surrogate đứng trước low surrogate. Java cung cấp API để kiểm tra và kết hợp:

```java
char high = '\uD83D';
char low = '\uDE80';

System.out.println(Character.isHighSurrogate(high)); // true
System.out.println(Character.isLowSurrogate(low));   // true

int codePoint = Character.toCodePoint(high, low);
System.out.printf("U+%04X%n", codePoint); // U+1F680
```

Không tự ghép hai `char` bằng phép cộng hoặc tự tính surrogate nếu không có lý do đặc biệt. `Character.toCodePoint`, `Character.toChars`, `codePointAt` và `appendCodePoint` đã cung cấp các phép chuyển đổi chuẩn.

Một `String` Java có thể chứa surrogate không ghép cặp vì UTF-16 code unit có thể được tạo trực tiếp từ `char` hoặc đến từ nguồn dữ liệu không hợp lệ. Các API code point không tự động biến mọi chuỗi thành dữ liệu Unicode hợp lệ; nếu yêu cầu đầu vào phải là Unicode scalar values, cần xác thực surrogate pair trước khi lưu hoặc truyền đi.

## 7. Dùng Character API nhận int thay vì char

Nhiều phương thức `Character` có overload nhận `char` và overload nhận `int`. Khi xử lý toàn bộ Unicode, chọn overload `int`:

```java
String text = "A中🚀";

text.codePoints().forEach(cp -> {
    boolean letter = Character.isLetter(cp);
    boolean digit = Character.isDigit(cp);
    int type = Character.getType(cp);

    System.out.printf("U+%04X letter=%s digit=%s type=%d%n",
            cp, letter, digit, type);
});
```

Một số phương thức hữu ích:

| API | Mục đích |
|---|---|
| `Character.isLetter(int)` | Kiểm tra code point thuộc nhóm chữ cái |
| `Character.isDigit(int)` | Kiểm tra chữ số theo thuộc tính Unicode |
| `Character.isWhitespace(int)` | Kiểm tra ký tự được phân loại là whitespace theo định nghĩa Java |
| `Character.getType(int)` | Lấy general category của code point |
| `Character.toUpperCase(int)` / `toLowerCase(int)` | Chuyển đổi hoa/thường ở mức một code point |
| `Character.isValidCodePoint(int)` | Kiểm tra giá trị nằm trong khoảng code point Unicode |
| `Character.charCount(int)` | Số UTF-16 code unit cần để biểu diễn code point |

Không dùng `Character.isWhitespace` như một phép kiểm tra mọi ký tự trông giống khoảng trắng trong mọi ngôn ngữ. Unicode có nhiều separator và format character với ý nghĩa khác nhau; hãy chọn thuộc tính phù hợp với yêu cầu đầu vào.

## 8. Code point và ký tự hiển thị (grapheme cluster)

Ngay cả khi duyệt đúng code point, chương trình vẫn chưa chắc đang thao tác theo ký tự mà người dùng nhìn thấy. Một chữ có dấu kết hợp có thể gồm chữ cái cơ sở và combining mark. Một emoji có thể gồm nhiều code point nối với nhau bằng ZWJ hoặc có variation selector và modifier.

Ví dụ:

```java
String composed = "é";       // U+00E9
String decomposed = "e\u0301"; // U+0065 + U+0301

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.length());           // 1
System.out.println(decomposed.length());         // 2
System.out.println(composed.codePointCount(0, composed.length()));   // 1
System.out.println(decomposed.codePointCount(0, decomposed.length())); // 2
```

Hai chuỗi có thể hiển thị giống nhau nhưng có cách mã hóa khác nhau. Cả hai trường hợp thường được người dùng cảm nhận như một grapheme cluster.

Java cung cấp `BreakIterator.getCharacterInstance(...)` để tìm ranh giới ký tự theo locale:

```java
import java.text.BreakIterator;
import java.util.Locale;

String text = "e\u0301🚀";
BreakIterator iterator = BreakIterator.getCharacterInstance(Locale.ROOT);
iterator.setText(text);

int start = iterator.first();
for (int end = iterator.next(); end != BreakIterator.DONE;
     start = end, end = iterator.next()) {
    System.out.println(text.substring(start, end));
}
```

`BreakIterator` trả về các ranh giới theo dữ liệu và quy tắc phân đoạn của JDK. Nếu ứng dụng cần tuân thủ chính xác phiên bản mới nhất của Unicode Extended Grapheme Cluster (UAX #29), đặc biệt với chuỗi emoji phức tạp, hãy xác minh hành vi của JDK mục tiêu hoặc dùng thư viện Unicode chuyên dụng như ICU4J. Không giả định một code point tương đương một grapheme cluster.

## 9. Chuẩn hóa Unicode trước khi so sánh

Hai chuỗi có thể hiển thị giống nhau nhưng có dãy code point khác nhau. Unicode normalization cung cấp các dạng chuẩn hóa để biểu diễn những chuỗi tương đương theo quy tắc chuẩn hóa:

- **NFC:** canonical decomposition rồi canonical composition khi có thể; thường tạo dạng ghép.
- **NFD:** canonical decomposition; biểu diễn ký tự ghép thành ký tự cơ sở và dấu kết hợp khi áp dụng.
- **NFKC/NFKD:** ngoài canonical equivalence còn áp dụng compatibility mappings; có thể làm mất các khác biệt định dạng hoặc ý nghĩa cần giữ.

Ví dụ dùng `Normalizer`:

```java
import java.text.Normalizer;

String composed = "é";
String decomposed = "e\u0301";

String normalizedA = Normalizer.normalize(composed, Normalizer.Form.NFC);
String normalizedB = Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(normalizedA.equals(normalizedB)); // true
```

Nếu nghiệp vụ cần so sánh chuỗi theo canonical equivalence, chuẩn hóa cả hai về cùng một form trước khi so sánh. Không áp dụng NFKC/NFKD một cách tùy tiện cho nội dung hiển thị, mật khẩu hoặc định danh nếu chưa xác định rõ chính sách, vì compatibility normalization có thể gộp những ký tự vốn được phân biệt.

Normalization không phải phép chuyển mã hóa byte. Nó biến đổi chuỗi code point theo quy tắc Unicode; việc encode thành UTF-8 là bước riêng.

## 10. Chuyển đổi hoa/thường và locale

Chuyển đổi hoa/thường có thể phụ thuộc ngôn ngữ. Ví dụ chữ `I` có quy tắc khác nhau trong tiếng Thổ Nhĩ Kỳ và một số locale khác. Không dùng default locale của máy chủ để chuẩn hóa khóa giao thức hoặc identifier mà yêu cầu không phụ thuộc ngôn ngữ.

Với chuỗi dùng trong giao thức hoặc phép chuyển đổi trung lập locale, chỉ định `Locale.ROOT`:

```java
import java.util.Locale;

String headerName = "content-type";
String normalized = headerName.toUpperCase(Locale.ROOT);
System.out.println(normalized); // CONTENT-TYPE
```

Với nội dung hiển thị cho người dùng, truyền locale phù hợp với ngôn ngữ giao diện:

```java
String text = "istanbul";
String turkishUpper = text.toUpperCase(Locale.forLanguageTag("tr"));
System.out.println(turkishUpper);
```

`Character.toUpperCase(int)` chỉ chuyển đổi một code point và không thể biểu diễn các trường hợp chuyển đổi một-nhiều code point. `String.toUpperCase(Locale)` và `toLowerCase(Locale)` làm việc ở mức chuỗi và có thể thay đổi độ dài. Với so sánh không phân biệt hoa/thường theo ngôn ngữ, cần xác định rõ quy tắc locale và Unicode; `equalsIgnoreCase` không phải một triển khai đầy đủ của mọi quy tắc linguistic collation hoặc Unicode full case folding.

## 11. So sánh và sắp xếp chuỗi theo ngôn ngữ

`String.compareTo()` so sánh theo thứ tự từ điển của các đơn vị UTF-16, không phải quy tắc sắp xếp tự nhiên của mọi ngôn ngữ. Khi sắp xếp tên người hoặc văn bản hiển thị, dùng `Collator` với locale phù hợp:

```java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

List<String> names = new ArrayList<>(List.of("An", "Ánh", "Bình", "Chi"));
Collator collator = Collator.getInstance(Locale.forLanguageTag("vi"));
names.sort(collator);

System.out.println(names);
```

Kết quả sắp xếp phụ thuộc dữ liệu locale và phiên bản thư viện/JDK. Không dùng thứ tự `compareTo()` thay cho collation theo ngôn ngữ khi sản phẩm cần thứ tự từ điển phù hợp với người dùng.

## 12. Charset và dữ liệu đầu vào

`String` lưu nội dung theo UTF-16, nhưng dữ liệu từ file, mạng hoặc database thường đi qua byte stream. Khi chuyển byte thành text, hãy chỉ định charset rõ ràng:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = "Xin chào 🚀".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);

System.out.println(text);
```

JDK 18 trở lên dùng UTF-8 làm default charset trong phần lớn môi trường chuẩn theo JEP 400, nhưng vẫn nên chỉ định charset ở ranh giới file/network để hợp đồng dữ liệu rõ ràng và không phụ thuộc cấu hình môi trường.

Nếu cần từ chối dữ liệu UTF-8 malformed thay vì thay bằng ký tự thay thế, dùng decoder với `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes) throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

Đối với dữ liệu không tin cậy, chọn chính sách rõ ràng: thay thế dữ liệu lỗi, từ chối, hoặc ghi nhận để xử lý. Đừng giả định mọi `String` đều được tạo từ một byte sequence UTF-8 hợp lệ; mã Java có thể tạo chuỗi chứa surrogate đơn lẻ.

## 13. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `length()` lớn hơn số ký tự hiển thị | `length()` đếm UTF-16 code unit | Dùng `codePointCount` nếu cần đếm code point; dùng grapheme segmentation nếu cần ký tự hiển thị |
| `charAt()` trả về ký tự lạ khi đọc emoji | Chỉ lấy một nửa surrogate pair | Dùng `codePointAt` hoặc `codePoints()` |
| `Character.isLetter(char)` không nhận diện ký tự supplementary | Overload `char` không thể chứa code point đó | Dùng `Character.isLetter(int)` trên code point |
| Hai chuỗi nhìn giống nhau nhưng `equals()` trả false | Hai chuỗi có thể dùng canonical representations khác nhau | Chuẩn hóa về NFC/NFD theo chính sách dữ liệu trước khi so sánh |
| Chuyển hoa/thường khác nhau giữa máy chủ | Dùng default locale không cố định | Chỉ định `Locale.ROOT` hoặc locale nghiệp vụ |
| Sắp xếp tên không đúng thứ tự ngôn ngữ | `String.compareTo()` không phải linguistic collation | Dùng `Collator` với locale phù hợp |
| Tách sai emoji hoặc chữ có dấu | Đang tách theo `char` hoặc code point trong khi cần grapheme cluster | Dùng character boundary iterator hoặc thư viện Unicode chuyên dụng |
| Byte đọc vào thành ký tự thay thế | Charset không đúng hoặc dữ liệu malformed | Chỉ định UTF-8/charset đúng và chọn chính sách decoder rõ ràng |

## 14. Checklist xử lý Unicode trong Java 21

- Nhớ dữ liệu thuộc tính `Character` trong Java 21 dựa trên Unicode 15.0.
- Không đồng nhất `char`, UTF-16 code unit, code point và grapheme cluster.
- Dùng `codePoints()` hoặc `codePointAt()` khi xử lý toàn bộ Unicode.
- Dùng overload `Character` nhận `int` cho các thao tác theo code point.
- Dùng `offsetByCodePoints()` khi cần chuyển số lượng code point thành chỉ số UTF-16.
- Kiểm tra surrogate pair nếu đầu vào cần là Unicode scalar values hợp lệ.
- Dùng `BreakIterator` hoặc thư viện Unicode phù hợp khi cần phân đoạn ký tự hiển thị.
- Chuẩn hóa NFC/NFD khi nghiệp vụ cần canonical equivalence; thận trọng với NFKC/NFKD.
- Chỉ định locale cho chuyển đổi hoa/thường và collation.
- Chỉ định charset rõ ràng khi đọc/ghi byte; dùng decoder strict khi cần từ chối dữ liệu lỗi.
- Đo độ dài theo đúng đơn vị nghiệp vụ: byte, UTF-16 code unit, code point hay grapheme cluster.

Java 21 hỗ trợ Unicode 15.0 trong các thuộc tính ký tự, nhưng `char` vẫn chỉ là một UTF-16 code unit. Để xử lý văn bản quốc tế chính xác, hãy chọn đúng tầng biểu diễn: code unit cho thao tác UTF-16, code point cho thuộc tính Unicode, grapheme cluster cho đơn vị hiển thị, và normalization/locale cho so sánh hoặc trình bày theo ngôn ngữ.
