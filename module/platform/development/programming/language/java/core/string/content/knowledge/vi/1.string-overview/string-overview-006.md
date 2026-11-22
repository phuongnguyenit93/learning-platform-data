# Các nhóm thao tác với String trong Java: đọc, so sánh, tìm kiếm, biến đổi và chuyển mã

Trong Java, `String` là kiểu tham chiếu biểu diễn văn bản. Năm nhóm thao tác thường gặp gồm: **đọc/trích xuất**, **so sánh**, **tìm kiếm**, **biến đổi** và **chuyển đổi/mã hóa**. Mỗi nhóm giải quyết một mục đích khác nhau; chọn đúng API giúp code dễ hiểu và tránh lỗi với Unicode, biểu thức chính quy hoặc dữ liệu từ hệ thống ngoài.

## 1. Quy tắc nền tảng trước khi thao tác

1. **`String` bất biến (immutable):** `replace()`, `strip()`, `substring()`, `toUpperCase()` trả về kết quả nhưng không sửa chuỗi gốc. Phải gán `s = s.strip();` nếu muốn lưu giá trị sau biến đổi. Nếu không có thay đổi, một phương thức có thể trả về cùng đối tượng; không dựa vào danh tính tham chiếu để quyết định nội dung.
2. **Chỉ số bắt đầu từ 0, biên cuối không bao gồm:** `"Java".substring(1, 3)` là `"av"`. Giá trị chỉ số không hợp lệ gây `StringIndexOutOfBoundsException`.
3. **Đơn vị chỉ số của String là UTF-16 code unit:** `"🚀".length() == 2` dù emoji là một Unicode code point. `charAt()` có thể trả về nửa surrogate pair; `codePoints()` phù hợp hơn khi muốn duyệt code point. Một ký tự hiển thị cũng có thể gồm nhiều code point, ví dụ chữ cộng dấu kết hợp.
4. **`null` khác `""`:** `null` không có đối tượng; chuỗi rỗng có `length() == 0`. Gọi `length()` hoặc bất cứ instance method nào trên null gây `NullPointerException`.
5. **Văn bản khác byte:** `String` chứa văn bản, `byte[]` chứa dữ liệu byte. Chuyển qua lại cần chọn charset, thông thường `StandardCharsets.UTF_8`, ở cả hai đầu.

## 2. Đọc và trích xuất

| Nhu cầu | Phương thức | Ghi nhớ |
|---|---|---|
| Đo độ dài | `length()` | Số UTF-16 code unit |
| Chuỗi rỗng | `isEmpty()` | `true` chỉ khi độ dài bằng 0 |
| Rỗng hoặc toàn whitespace | `isBlank()` | Dùng quy tắc whitespace của `Character.isWhitespace` |
| Đọc một code unit | `charAt(index)` | Trả về `char` |
| Đọc một code point | `codePointAt(index)` | Trả về `int`, index vẫn tính theo UTF-16 |
| Đếm code point | `codePointCount(begin, end)` | Hai biên là chỉ số UTF-16 |
| Duyệt code point | `codePoints()` | Trả về `IntStream` |
| Lấy đoạn | `substring(begin, end)` | Lấy từ begin đến trước end |
| Lấy dạng `CharSequence` | `subSequence(begin, end)` | Dùng khi API nhận `CharSequence` |
| Sao chép các `char` | `toCharArray()`, `getChars(...)` | Vẫn theo code unit UTF-16 |
| Duyệt từng dòng | `lines()` | Trả về `Stream<String>` |

~~~java
String s = "Java 🚀";
System.out.println(s.length());                      // 7
System.out.println(s.charAt(0));                     // J
System.out.println(s.substring(0, 4));              // Java
System.out.println(s.codePointCount(0, s.length())); // 6
s.codePoints().forEach(cp -> System.out.print(Character.toString(cp)));
System.out.println();                                // Java 🚀
~~~

Muốn cắt theo **số code point**, dùng `offsetByCodePoints()` để tính vị trí UTF-16 rồi mới `substring()`:

~~~java
String s = "A🚀B";
int end = s.offsetByCodePoints(0, 2);
System.out.println(s.substring(0, end)); // A🚀
~~~

`s.substring(0, 2)` trong trường hợp này cắt giữa hai code unit của 🚀 và tạo chuỗi chứa surrogate lẻ. Nếu phải thao tác theo **grapheme cluster** (ký tự người dùng nhìn thấy), chỉ tính code point vẫn chưa đủ; cần bộ phân đoạn văn bản phù hợp.

## 3. So sánh: nội dung, chữ hoa và thứ tự

- `a.equals(b)`: so nội dung chính xác theo code unit và có phân biệt hoa/thường.
- `a.equalsIgnoreCase(b)`: so không phân biệt chữ hoa/thường theo quy tắc Unicode của Java, không thay thế đối chiếu ngôn ngữ tự nhiên đầy đủ.
- `a.compareTo(b)`: so thứ tự từ điển theo UTF-16, trả **âm / 0 / dương**; không mặc định chỉ có `-1, 0, 1`. `compareToIgnoreCase(b)` bỏ qua hoa/thường.
- `a.contentEquals(charSequence)`: so nội dung với một `CharSequence` như `StringBuilder`.
- `a.regionMatches(...)`: so hai vùng con, có biến thể bỏ qua hoa/thường.
- `Objects.equals(a, b)`: so an toàn khi tham chiếu có thể null.

~~~java
import java.util.Objects;

String a = new String("Java");
String b = "Java";
System.out.println(a == b);                                // false
System.out.println(a.equals(b));                           // true
System.out.println("Java".equalsIgnoreCase("JAVA"));       // true
System.out.println("Java".compareTo("Kotlin"));            // -1
System.out.println(Objects.equals(null, null));           // true
System.out.println("Java".contentEquals(
        new StringBuilder("Java")));                      // true
~~~

**Lỗi phổ biến:** `==` so danh tính tham chiếu, **không** so nội dung. String pool có thể làm hai literal trỏ cùng đối tượng, khiến ví dụ `"abc" == "abc"` có kết quả true nhưng không bảo đảm cho chuỗi tạo lúc chạy. Dùng `"expected".equals(candidate)` hoặc `Objects.equals(...)` khi có khả năng null.

Khi cần **sắp xếp tên hiển thị theo một ngôn ngữ** như tiếng Việt, dùng `java.text.Collator` với locale phù hợp thay vì dựa vào `compareTo()`:

~~~java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(Locale.forLanguageTag("vi-VN"));
int result = collator.compare("An", "Ánh");
// result âm, bằng 0 hoặc dương theo quy tắc collation của locale.
~~~

Kết quả collation phụ thuộc dữ liệu locale, cấu hình mức phân biệt dấu/hoa thường (`strength`) và môi trường; không suy ra thứ tự theo ngôn ngữ từ giá trị Unicode code point.

## 4. Tìm kiếm chuỗi con và biểu thức chính quy

| Phương thức | Kết quả | Khi dùng |
|---|---|---|
| `contains(part)` | `boolean` | Có chuỗi con literal hay không |
| `startsWith(prefix)`, `endsWith(suffix)` | `boolean` | Kiểm tra tiền tố/hậu tố |
| `indexOf(part)` | Chỉ số xuất hiện đầu hoặc `-1` | Tìm vị trí (UTF-16) |
| `indexOf(part, fromIndex)` | Chỉ số hoặc `-1` | Tìm tiếp từ một vị trí |
| `lastIndexOf(part)` | Chỉ số xuất hiện cuối hoặc `-1` | Tìm từ cuối |
| `matches(regex)` | `boolean` | **Cả chuỗi** khớp regex |
| `Pattern` + `Matcher.find()` | `boolean`/nhóm/vị trí | Một **đoạn con** khớp regex |

~~~java
String text = "Java 17, Java 21";
System.out.println(text.contains("Java"));            // true
System.out.println(text.indexOf("Java"));             // 0
System.out.println(text.indexOf("Java", 1));          // 9
System.out.println(text.lastIndexOf("Java"));         // 9
System.out.println(text.startsWith("Java 17"));       // true
System.out.println("ABC123".matches("[A-Z]+\\d+"));   // true
System.out.println("x123y".matches("\\d+"));          // false
~~~

`matches()` yêu cầu regex khớp **toàn bộ** chuỗi. Để tìm nhiều đoạn con, dùng `find()`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

Matcher m = Pattern.compile("\\d+").matcher("A12 B345");
while (m.find()) {
    System.out.println(m.group() + " tại " + m.start());
}
// 12 tại 1
// 345 tại 5
~~~

Trong Java source, regex `\d+` cần ghi bằng chuỗi `"\\d+"` vì backslash phải được escape ở tầng Java string. Dấu `.` trong regex khớp một ký tự theo quy tắc regex, không phải dấu chấm literal. Nếu người dùng nhập văn bản cần tìm, dùng `Pattern.quote(userText)` để tạo mẫu regex literal. Nếu chỉ tìm literal, `contains()`/`indexOf()` thường gọn và rõ hơn regex.

## 5. Biến đổi nội dung

### 5.1. Ghép, nối và lặp

`+` hoặc `concat()` nối chuỗi. `String.join(delimiter, elements...)` ghép các phần có dấu phân tách. `repeat(n)` lặp `n` lần (n âm gây `IllegalArgumentException`). Với nhiều phép nối trong vòng lặp lớn, `StringBuilder.append()` giảm việc tạo chuỗi trung gian; `StringBuilder` thay đổi được, nên không chia sẻ để nhiều luồng cùng sửa nếu không đồng bộ.

~~~java
System.out.println("Java".concat(" 17"));                // Java 17
System.out.println(String.join(" | ", "đọc", "tìm", "đổi")); // đọc | tìm | đổi
System.out.println("ha".repeat(3));                     // hahaha

StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) builder.append(", ");
    builder.append(i);
}
System.out.println(builder); // 1, 2, 3
~~~

### 5.2. Thay thế literal khác regex

- `replace(char, char)` và `replace(CharSequence, CharSequence)`: thay các giá trị **literal**.
- `replaceAll(regex, replacement)`: thay tất cả phần khớp **regex**. Replacement có cú pháp tham chiếu nhóm như `$1`.
- `replaceFirst(regex, replacement)`: thay phần khớp đầu tiên.

~~~java
System.out.println("a.b".replace(".", "-"));           // a-b
System.out.println("a.b".replaceAll(".", "-"));        // ---
System.out.println("a12b34".replaceAll("\\d+", "#"));  // a#b#
System.out.println("1 2 3".replaceFirst("\\d", "X"));  // X 2 3
~~~

Khi replacement đến từ người dùng, dùng `Matcher.quoteReplacement(replacement)` để tránh `$` hoặc backslash bị diễn giải như cú pháp. Với dữ liệu literal, chọn `replace(old, new)` để giảm lỗi.

### 5.3. Khoảng trắng, chữ hoa/thường và Unicode

`strip()`, `stripLeading()`, `stripTrailing()` bỏ whitespace theo `Character.isWhitespace`; `trim()` chỉ bỏ các code unit ở đầu/cuối có giá trị từ U+0000 tới U+0020, vì vậy có trường hợp khác `strip()`.

`toUpperCase(locale)` và `toLowerCase(locale)` dùng quy tắc locale. Khi biểu diễn key máy không phụ thuộc ngôn ngữ mà đặc tả cho phép case folding đơn giản, sử dụng `Locale.ROOT` tường minh. Với văn bản hiển thị, dùng locale thích hợp. Việc đổi hoa/thường có thể đổi số code point hoặc độ dài chuỗi.

`java.text.Normalizer` dùng để chuẩn hóa biểu diễn Unicode. Hai chuỗi nhìn giống nhau có thể khác về code point, ví dụ ký tự `é` dựng sẵn và `e` cộng dấu sắc kết hợp:

~~~java
import java.text.Normalizer;
import java.util.Locale;

String raw = "  Java  ";
System.out.println("[" + raw.trim() + "]");              // [Java]
System.out.println("[" + raw.strip() + "]");             // [Java]
System.out.println("java".toUpperCase(Locale.ROOT));     // JAVA

String composed = "\u00E9";
String decomposed = "e\u0301";
System.out.println(composed.equals(decomposed));          // false
System.out.println(composed.equals(
        Normalizer.normalize(decomposed, Normalizer.Form.NFC))); // true
~~~

NFC chuẩn hóa các biểu diễn tương đương theo Unicode, nhưng không đồng nhất mọi từ trông giống nhau. Với văn bản nhiều dòng, Java còn có `indent()`, `stripIndent()`, `translateEscapes()`; cần đọc quy tắc dấu xuống dòng/escape trước khi áp dụng.

## 6. Chuyển đổi kiểu dữ liệu, charset và các dạng mã hóa

### 6.1. Giá trị Java ↔ String

`String.valueOf(42)` tạo `"42"`; `String.valueOf(true)` tạo `"true"`; `String.valueOf((Object)null)` tạo **chuỗi ký tự** `"null"`, khác tham chiếu null.

`Integer.parseInt()`, `Long.parseLong()`, `Double.parseDouble()` chuyển chuỗi thành số và có thể ném `NumberFormatException`. `Boolean.parseBoolean()` trả true khi bằng `"true"` không phân biệt hoa/thường, những giá trị còn lại trả false.

~~~java
import java.util.Locale;

int count = Integer.parseInt("42");
String number = String.valueOf(count);
String code = String.format(Locale.ROOT, "ITEM-%04d", count);
System.out.println(number); // 42
System.out.println(code);   // ITEM-0042
~~~

`String.format(Locale, format, args)` cho phép xác định locale rõ ràng, rất hữu ích khi văn bản gửi qua hệ thống phải ổn định. `"ITEM-%04d".formatted(42)` là cú pháp gọn nhưng dùng locale mặc định. `Integer.parseInt("12.5")` không hợp lệ. `Double.parseDouble` dùng dấu thập phân theo cú pháp Java, không tự hiểu định dạng dấu phẩy của địa phương; với dữ liệu định dạng theo locale, cân nhắc `NumberFormat` và xác thực toàn bộ đầu vào.

### 6.2. Văn bản ↔ byte: charset

Encoding ánh xạ Unicode thành byte; decoding chuyển byte lại thành văn bản. Hai chiều phải thống nhất charset. Thông thường chọn `StandardCharsets.UTF_8` để tránh phụ thuộc charset mặc định của JVM/hệ điều hành.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String message = "Xin chào 🚀";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
System.out.println(bytes.length);                       // 14
System.out.println(message.equals(restored));          // true
System.out.println(HexFormat.of().formatHex(
        "A".getBytes(StandardCharsets.UTF_8)));         // 41
~~~

Độ dài byte khác độ dài `String`: `à` là 2 byte trong UTF-8, 🚀 là 4 byte UTF-8 nhưng 2 code unit UTF-16. Giải mã byte UTF-8 bằng charset không phù hợp có thể gây lỗi hiển thị. Một số API chuyển đổi tiện dụng thay dữ liệu sai bằng ký tự thay thế; để **từ chối** đầu vào mã hóa không hợp lệ, tạo `CharsetDecoder`/`CharsetEncoder` với `CodingErrorAction.REPORT` và xử lý `CharacterCodingException`.

### 6.3. Base64, hex và URL encoding có mục đích khác charset

| Bài toán | API | Ý nghĩa |
|---|---|---|
| Unicode ↔ byte | `getBytes(UTF_8)`, `new String(bytes, UTF_8)` | Charset encoding/decoding |
| Byte ↔ Base64 | `Base64.getEncoder()/getDecoder()` | Biểu diễn byte bằng ký tự ASCII |
| Byte ↔ hex | `HexFormat` (Java 17+) | Biểu diễn một byte bằng hai chữ số hexadecimal |
| Giá trị form/query parameter | `URLEncoder.encode(text, UTF_8)` / `URLDecoder.decode(...)` | Quy tắc `application/x-www-form-urlencoded`; dấu cách thành `+` |
| Unicode code point ↔ text | `codePointAt()`, `Character.toString(int)` | Thao tác Unicode, không phải charset byte |

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] data = "Java".getBytes(StandardCharsets.UTF_8);
String encoded = Base64.getEncoder().encodeToString(data);
String decoded = new String(Base64.getDecoder().decode(encoded),
                            StandardCharsets.UTF_8);
System.out.println(encoded); // SmF2YQ==
System.out.println(decoded); // Java
~~~

Base64, hex và URL encoding **không bảo mật dữ liệu** vì chúng có thể đảo ngược. `URLEncoder` mã hóa theo quy tắc form, không phải công cụ mã hóa nguyên URL hay mọi path segment một cách tùy ý.

## 7. Ví dụ tổng hợp: file chạy độc lập trên Java 17+

Lưu đoạn dưới đây ở file UTF-8 `StringOperationsDemo.java`. Các đoạn code trước đó minh họa riêng từng API và có thể cần đặt trong class/phương thức nếu chạy độc lập.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class StringOperationsDemo {
    public static void main(String[] args) {
        String data = "  Java Java 🚀  ";

        // Đọc
        System.out.println("len=" + data.length());
        System.out.println("strip=[" + data.strip() + "]");
        System.out.println("charAt2=" + data.charAt(2));
        System.out.println("substring=" + data.substring(2, 6));
        System.out.println("codePointsEmoji=" +
                "🚀".codePointCount(0, "🚀".length()));

        // So sánh
        System.out.println("equals=" + "Java".equals(new String("Java")));
        System.out.println("compareTo=" + "Java".compareTo("Kotlin"));

        // Tìm kiếm
        System.out.println("indexOf=" + data.indexOf("Java"));
        System.out.println("lastIndexOf=" + data.lastIndexOf("Java"));
        System.out.println("contains=" + data.contains("Java"));

        // Biến đổi
        System.out.println("replace=" + data.strip().replace("Java", "Core"));
        System.out.println("replaceAll=" + "a12b34".replaceAll("\\d+", "#"));
        System.out.println("upper=" + "java".toUpperCase(Locale.ROOT));
        Matcher m = Pattern.compile("\\d+").matcher("A12 B345");
        while (m.find()) {
            System.out.println("match=" + m.group() + "@" + m.start());
        }

        // Chuyển mã
        byte[] utf8 = "Xin chào 🚀".getBytes(StandardCharsets.UTF_8);
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("decode=" + new String(utf8, StandardCharsets.UTF_8));
        String nfc = Normalizer.normalize("e\u0301", Normalizer.Form.NFC);
        System.out.println("nfcEqual=" + nfc.equals("\u00E9"));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StringOperationsDemo.java
java StringOperationsDemo
~~~

Kết quả tiêu chuẩn:

~~~text
len=16
strip=[Java Java 🚀]
charAt2=J
substring=Java
codePointsEmoji=1
equals=true
compareTo=-1
indexOf=2
lastIndexOf=7
contains=true
replace=Core Core 🚀
replaceAll=a#b#
upper=JAVA
match=12@1
match=345@5
utf8Bytes=14
decode=Xin chào 🚀
nfcEqual=true
~~~

`javac -encoding UTF-8` xác định encoding **mã nguồn**, còn `StandardCharsets.UTF_8` xác định encoding **dữ liệu chương trình**. Hai mục đích riêng biệt.

## 8. Bảng chọn API và lỗi thường gặp

| Khi cần… | Chọn… | Tránh… |
|---|---|---|
| Kiểm tra rỗng/trắng | `isEmpty()`, `isBlank()` | Bỏ qua `null` |
| So văn bản chính xác | `equals()` | Dùng `==` vì string pool |
| So có thể null | `Objects.equals()` | Gọi instance method trên null |
| Sắp xếp hiển thị tiếng Việt | `Collator` và locale | Mong `compareTo()` sắp theo ngôn ngữ |
| Tìm literal | `contains()`, `indexOf()` | Regex không cần thiết |
| Tìm đoạn theo mẫu | `Pattern` + `Matcher.find()` | Nhầm `matches()` tìm đoạn |
| Thay thế literal | `replace()` | Nhầm `replaceAll()` xử lý `.` như dấu chấm |
| Bỏ khoảng trắng đầu/cuối | `strip()` | Nghĩ `trim()` luôn tương đương |
| Ghép trong vòng lặp | `StringBuilder` | Nối `+` liên tục tạo nhiều chuỗi |
| Cắt theo code point | `offsetByCodePoints()` | Cắt đôi surrogate pair |
| So Unicode tương đương chuẩn | `Normalizer` NFC khi cần | Chỉ nhìn hình dạng để kết luận `equals` |
| Đổi hoa/thường key máy | `Locale.ROOT` khi phù hợp đặc tả | Phụ thuộc locale mặc định |
| String ↔ byte | UTF-8 được chỉ định rõ | Nhầm `length()` với số byte |
| Biểu diễn byte bằng chữ ASCII | Base64/hex | Coi đó là kỹ thuật bảo mật |

### Checklist ứng dụng

1. Xác định nhu cầu: đọc, so nội dung, so thứ tự theo locale, tìm literal, regex, biến đổi hay encoding.
2. Xác định đơn vị đang thao tác: UTF-16 code unit, code point, grapheme cluster hoặc byte. Các đơn vị này khác nhau.
3. Xử lý null, trường hợp chuỗi rỗng/whitespace, chỉ số sai, parse số lỗi và input regex đặc biệt.
4. Ưu tiên API trực tiếp và rõ nghĩa: `equals()` cho nội dung, `replace()` cho literal, `Matcher.find()` cho đoạn khớp regex, UTF-8 tường minh khi truyền byte.
5. Thử các dữ liệu biên: tiếng Việt có dấu, emoji, ký tự kết hợp, nhiều dòng, chữ hoa/thường, charset sai và dữ liệu byte không hợp lệ.

Khi hiểu rõ năm nhóm, bạn sẽ chọn được cách xử lý văn bản có ý nghĩa rõ ràng, chính xác trước những trường hợp Unicode khó và dễ bảo trì khi chương trình lớn lên.