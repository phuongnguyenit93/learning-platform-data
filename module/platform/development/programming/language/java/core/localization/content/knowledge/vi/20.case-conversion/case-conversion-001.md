# String.toLowerCase và toUpperCase với Locale tường minh trong Java

## 1. Tại sao chuyển chữ hoa/chữ thường lại liên quan đến bản địa hóa?

Một đoạn code có vẻ vô hại:

```java
String key = "TITLE".toLowerCase();
```

Trong nhiều máy tính, `key` sẽ là `"title"`. Nhưng với **default locale tiếng Thổ Nhĩ Kỳ** (`tr-TR`), kết quả có thể là `"tıtle"`: chữ `ı` (`U+0131`, LATIN SMALL LETTER DOTLESS I) **không phải** `i` (`U+0069`). Nếu chuỗi dùng làm tên trường, mã trạng thái, key cấu hình hoặc đường dẫn đã được quy định theo ASCII, ứng dụng có thể không tìm thấy dữ liệu hoặc hành xử khác nhau khi chạy trên máy chủ khác.

Đối với giao diện người dùng, kết quả tiếng Thổ Nhĩ Kỳ lại **có thể chính là kết quả cần thiết**. Không có một cách đổi chữ hoa/thường phù hợp với mọi mục đích: phải xác định chuỗi đang được xử lý là **văn bản ngôn ngữ tự nhiên** hay **định danh máy**.

Java cung cấp bốn phương thức:

```java
String toLowerCase();
String toLowerCase(Locale locale);

String toUpperCase();
String toUpperCase(Locale locale);
```

Hai overload **không có tham số** dùng default locale của JVM. Hai overload **có tham số** dùng quy tắc biến đổi chữ theo locale được chỉ định. Bài học này làm rõ việc chọn `Locale`, các trường hợp Unicode đặc biệt, độ dài sau biến đổi, sai lầm khi so sánh không phân biệt hoa/thường và cách viết code Java 17+ dễ kiểm chứng.

## 2. Quy tắc cơ bản của hai phương thức

`String.toLowerCase(Locale)` biến đổi chữ trong chuỗi thành dạng thường theo quy tắc Unicode áp dụng cho locale. `String.toUpperCase(Locale)` làm điều tương tự sang dạng hoa.

```java
import java.util.Locale;

String source = "Java Localization";
String lower = source.toLowerCase(Locale.ENGLISH);
String upper = source.toUpperCase(Locale.ENGLISH);
```

Ở đây `lower` là `"java localization"` và `upper` là `"JAVA LOCALIZATION"`. Nhưng đó chỉ là trường hợp dễ; đối với văn bản quốc tế, quy tắc không phải luôn “đổi mỗi chữ thành đúng một chữ khác”.

| API | Locale sử dụng | Tình huống |
| --- | --- | --- |
| `s.toLowerCase()` | `Locale.getDefault()` tại thời điểm gọi | Khi ứng dụng thực sự muốn phụ thuộc default locale, nhưng dễ tạo lỗi ngầm |
| `s.toUpperCase()` | `Locale.getDefault()` tại thời điểm gọi | Tương tự |
| `s.toLowerCase(locale)` | Locale truyền vào | Chuyển chữ có chủ đích; dễ test, không lệ thuộc cấu hình máy |
| `s.toUpperCase(locale)` | Locale truyền vào | Chuyển chữ có chủ đích; dễ test, không lệ thuộc cấu hình máy |

Các phương thức trả về `String`, không chỉnh sửa chuỗi gốc vì `String` là immutable. Đừng giả định chuỗi kết quả luôn có cùng `length()` với chuỗi đầu vào hoặc luôn chỉ thay thế từng `char`: Unicode casing hỗ trợ ánh xạ **một code point thành nhiều code point** và **quy tắc phụ thuộc ngữ cảnh**.

### Locale không đồng nghĩa múi giờ hay encoding

- `Locale` ở đây điều khiển **quy tắc chuyển chữ**; nó không chuyển UTF-8 thành UTF-16 và không tự làm bản dịch.
- Chọn `Locale.forLanguageTag("tr-TR")` không đổi ngôn ngữ của tất cả chuỗi khác trong ứng dụng: chỉ tác động đến lời gọi sử dụng locale đó.
- `Locale.ROOT` là locale trung lập về ngôn ngữ/vùng để thực hiện các phép chuyển chữ không phụ thuộc default locale; nó **không** phải một bộ quy tắc so sánh/ngữ nghĩa Unicode hoàn chỉnh cho mọi ứng dụng.

## 3. Trường hợp kinh điển: I, İ, ı và i trong tiếng Thổ Nhĩ Kỳ

Tiếng Thổ Nhĩ Kỳ có hai cặp chữ hoa/thường khác nhau:

| Chữ hoa | Unicode | Chữ thường | Unicode | Cách hiểu |
| --- | --- | --- | --- | --- |
| `I` | `U+0049` | `ı` | `U+0131` | Chữ i **không chấm** |
| `İ` | `U+0130` | `i` | `U+0069` | Chữ i **có chấm** |

Trong quy tắc không đặc thù tiếng Thổ Nhĩ Kỳ, `I` thường thành `i` và `i` thành `I`. Nhưng ở `tr-TR`, `I` phải thành `ı`, `i` phải thành `İ`.

```java
Locale turkish = Locale.forLanguageTag("tr-TR");

String a = "TITLE".toLowerCase(Locale.ROOT);  // title
String b = "TITLE".toLowerCase(turkish);      // tıtle

String c = "title".toUpperCase(Locale.ROOT);  // TITLE
String d = "title".toUpperCase(turkish);      // TİTLE
```

Đây là **snippet** cần `import java.util.Locale;`. Sự khác biệt không nằm ở phông chữ: `i` và `ı` là **hai Unicode code point khác nhau**. Một key tên `"title"` sẽ không khớp `"tıtle"` khi dùng so sánh chính xác `String.equals`.

### Không chỉ tiếng Thổ Nhĩ Kỳ

Ngôn ngữ Azerbaijan có những quy tắc chữ `I`/`İ` tương tự. Tiếng Hy Lạp có sigma cuối từ và cách hạ chữ hoa dựa vào ngữ cảnh. Một số cách chuyển chữ ở tiếng Lithuania liên quan đến dấu kết hợp. Vì thế không nên xây quy tắc Unicode casing bằng cách tự cộng/trừ mã ASCII hoặc đi qua từng `char`.

**Kết luận:** dữ liệu hiển thị cho người dùng nên chuyển theo locale có ý nghĩa đối với **văn bản đó**. Định danh máy độc lập văn hóa nên dùng quy tắc được **hợp đồng kỹ thuật** quy định, thường là `Locale.ROOT` hoặc chỉ xử lý ASCII nếu protocol giới hạn ASCII.

## 4. Chương trình Java 17+ độc lập: so sánh Locale.ROOT và tr-TR

Tạo tệp **`LocaleCaseDemo.java`** với nội dung sau:

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class LocaleCaseDemo {
    private static String points(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        Locale turkish = Locale.forLanguageTag("tr-TR");

        System.out.println("TITLE ROOT: "
                + points("TITLE".toLowerCase(Locale.ROOT)));
        System.out.println("TITLE TR: "
                + points("TITLE".toLowerCase(turkish)));

        System.out.println("title ROOT upper: "
                + points("title".toUpperCase(Locale.ROOT)));
        System.out.println("title TR upper: "
                + points("title".toUpperCase(turkish)));

        System.out.println("TITLE TR equals title: "
                + "title".equals("TITLE".toLowerCase(turkish)));

        String dottedUpperI = "\u0130";
        System.out.println("Dotted I ROOT lowercase: "
                + points(dottedUpperI.toLowerCase(Locale.ROOT)));
        System.out.println("Dotted I TR lowercase: "
                + points(dottedUpperI.toLowerCase(turkish)));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 LocaleCaseDemo.java
java LocaleCaseDemo
```

**Stdout:**

```text
TITLE ROOT: U+0074 U+0069 U+0074 U+006C U+0065
TITLE TR: U+0074 U+0131 U+0074 U+006C U+0065
title ROOT upper: U+0054 U+0049 U+0054 U+004C U+0045
title TR upper: U+0054 U+0130 U+0054 U+004C U+0045
TITLE TR equals title: false
Dotted I ROOT lowercase: U+0069 U+0307
Dotted I TR lowercase: U+0069
```

Chương trình cố tình in code point bằng ký hiệu `U+XXXX` để tránh phụ thuộc terminal có hiển thị chữ `ı`, `İ` và dấu kết hợp đúng hay không. Các dòng đã chỉ ra:

1. `"TITLE"` có chữ `I` `U+0049` ở vị trí thứ hai.
2. `Locale.ROOT` biến nó thành `i` `U+0069`, còn `tr-TR` thành `ı` `U+0131`.
3. `"title"` chuyển sang hoa với `tr-TR` cho `İ` `U+0130`.
4. `"İ".toLowerCase(Locale.ROOT)` tạo **hai code point** (`i + COMBINING DOT ABOVE`), trong khi với `tr-TR` tạo một `i`. Ngay cả **số ký tự UTF-16** cũng có thể thay đổi sau chuyển chữ.

Không so sánh hai đầu ra bằng mắt hoặc dựa vào font để phán đoán xem chúng có cùng giá trị Unicode hay không.

## 5. String.toUpperCase có thể làm chuỗi dài hơn: ß → SS

Ví dụ tiếng Đức thường gặp là `ß` (LATIN SMALL LETTER SHARP S). Theo quy tắc chuyển chữ hoa mà `String.toUpperCase(Locale)` áp dụng, một chữ `ß` có thể mở rộng thành **`SS`**:

```java
String original = "straße";
String upper = original.toUpperCase(Locale.GERMAN);

System.out.println(upper);            // STRASSE
System.out.println(original.length()); // 6
System.out.println(upper.length());    // 7
```

Vì `ß` là một code point còn `SS` là **hai**, không được giả định:

```text
input.length() == input.toUpperCase(locale).length()
```

Cũng đừng thay `String.toUpperCase(Locale)` bằng cách lặp qua từng `char` rồi gọi `Character.toUpperCase(char)`. Phương thức đơn ký tự không thể trực tiếp tạo hai ký tự để biểu diễn ánh xạ một-nhiều, và có thể bỏ qua các điều kiện theo ngữ cảnh.

### Lưu ý về “chuyển hoa rồi chuyển thường để hoàn nguyên”

Nếu `"straße".toUpperCase(Locale.GERMAN)` thành `"STRASSE"`, chuyển ngược:

```java
"STRASSE".toLowerCase(Locale.GERMAN)
```

sẽ cho `"strasse"`, **không phải `"straße"`**. Chuyển hoa/thường là thao tác xử lý văn bản, **không phải mã hóa hai chiều có thể đảo ngược**. Không dùng kết quả chuyển chữ để thay thế giá trị định danh gốc khi cần giữ chính xác cách viết ban đầu.

## 6. Case mapping phụ thuộc ngữ cảnh: sigma trong tiếng Hy Lạp

Tiếng Hy Lạp có hai dạng chữ sigma thường:

- `σ` (`U+03C3`) khi không ở cuối từ.
- `ς` (`U+03C2`) khi ở cuối từ theo ngữ cảnh.

Khi chuyển `"ΟΣ"` (chữ omicron hoa + sigma hoa) sang thường, kết quả là `"ος"`, với code point cuối `U+03C2`:

```java
String greek = "\u039F\u03A3";
String lower = greek.toLowerCase(Locale.ROOT);

System.out.println(
        lower.codePoints()
             .mapToObj(cp -> String.format(
                     Locale.ROOT, "U+%04X", cp))
             .toList());
// [U+03BF, U+03C2]
```

Đây là **snippet** cần `import java.util.Locale;`. Một phép chuyển từng code point đơn lẻ sẽ không nhất thiết giữ được ngữ cảnh của toàn chuỗi. Vì vậy, dùng API `String.toLowerCase(Locale)` cho cả đoạn văn bản thay vì tự xử lý từng `char` hoặc chỉ từng code point bằng một ánh xạ giản lược.

Cách viết chữ hoa/thường trong các ngôn ngữ có thể còn phụ thuộc dấu Unicode, ranh giới từ và phiên bản dữ liệu Unicode mà JDK hỗ trợ. Nếu có yêu cầu ngôn ngữ chuyên sâu (ví dụ trường hợp title case hoặc case folding chuẩn), hãy dùng API phù hợp chứ không thay tất cả bằng `toUpperCase`.

## 7. Ví dụ Java 17+ độc lập: độ dài và sigma

Tạo tệp **`CaseExpansionDemo.java`**:

```java
import java.util.Locale;

public class CaseExpansionDemo {
    public static void main(String[] args) {
        String german = "stra\u00DFe";
        String upper = german.toUpperCase(Locale.GERMAN);

        System.out.println("German upper: " + upper);
        System.out.println("German lengths: "
                + german.length() + " -> " + upper.length());
        System.out.println("Round trip: "
                + german.equals(upper.toLowerCase(Locale.GERMAN)));

        String greek = "\u039F\u03A3";
        String greekLower = greek.toLowerCase(Locale.ROOT);
        System.out.println("Greek lower code points: "
                + greekLower.codePoints()
                    .mapToObj(cp -> String.format(
                            Locale.ROOT, "U+%04X", cp))
                    .toList());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CaseExpansionDemo.java
java CaseExpansionDemo
```

Kết quả:

```text
German upper: STRASSE
German lengths: 6 -> 7
Round trip: false
Greek lower code points: [U+03BF, U+03C2]
```

Bài học không phải “mọi locale đều mở rộng `ß` bằng nhau trong mọi công cụ” mà là: **String casing có thể thay đổi độ dài và phải xem là phép biến đổi Unicode theo hợp đồng Java**, không thể giả định thay thế một-đối-một. Các kết quả trên phản ánh mapping của `String` trên JDK hiện đại.

## 8. Locale.ROOT, Locale.ENGLISH và default locale khác nhau thế nào?

Ba cách dùng thường gặp:

```java
String a = input.toLowerCase(Locale.ROOT);
String b = input.toLowerCase(Locale.ENGLISH);
String c = input.toLowerCase();
```

Đây là snippet, với `input` đã được định nghĩa.

- **`Locale.ROOT`**: locale ngôn ngữ/vùng trung lập, thích hợp cho **những phép chuyển chuỗi được định nghĩa là không phụ thuộc ngôn ngữ người dùng**. Đây là khuyến nghị rõ ràng trong tài liệu `String.toLowerCase()` khi xử lý định danh của ngôn ngữ lập trình, protocol key, HTML tag, v.v. Tuy nhiên, hợp đồng giao thức vẫn là thẩm quyền cuối cùng: nếu protocol chỉ quy định ASCII, có thể cần chỉ chấp nhận ASCII và dùng thuật toán ASCII cụ thể.
- **`Locale.ENGLISH`**: mang ngôn ngữ tiếng Anh, phù hợp khi văn bản thực sự là tiếng Anh. Nó không tương đương về **ý nghĩa** với `Locale.ROOT`, dù nhiều chữ ASCII thường cho cùng kết quả.
- **Không truyền locale**: `toLowerCase()` và `toUpperCase()` dùng **`Locale.getDefault()`**. Điều này dễ tạo lỗi ở server triển khai đa vùng hoặc khi JVM default locale thay đổi.

### Cách chọn theo mục đích

| Dữ liệu | Locale/cách làm thường phù hợp | Ví dụ |
| --- | --- | --- |
| Nhãn giao diện tiếng Thổ Nhĩ Kỳ | `Locale.forLanguageTag("tr-TR")` | Đổi chữ hoa/thường trong câu tiếng Thổ Nhĩ Kỳ |
| Văn bản tiếng Anh | `Locale.ENGLISH` hoặc locale tiếng Anh vùng phù hợp | Nút hoặc heading tiếng Anh |
| Key kỹ thuật không phụ thuộc user locale | `Locale.ROOT`, theo hợp đồng của key | `"CONTENT-TYPE"`, định danh nội bộ |
| Văn bản người dùng đa ngôn ngữ | Locale gắn với văn bản, không dựa tùy tiện vào locale máy | Tìm kiếm/định dạng UI |
| Dữ liệu cần so khớp không phân biệt hoa/thường theo ngôn ngữ | Bộ so sánh có quy tắc locale như `Collator`, nếu phù hợp | Danh sách tên, tìm kiếm địa phương |
| Username, ID, token, mã bảo mật | Quy tắc chuẩn hóa/so sánh **được đặc tả riêng**; không tự suy diễn | Hệ thống xác thực |

**Không dùng `Locale.setDefault(...)` theo từng request.** Default locale là trạng thái có ảnh hưởng rộng trong JVM; thay đổi trong server đa luồng có thể khiến kết quả của request khác thay đổi ngoài ý muốn. Hãy truyền locale riêng trong mọi lời gọi cần bản địa hóa.

## 9. Đừng nhầm chuyển chữ với so sánh không phân biệt hoa/thường

### 9.1. equalsIgnoreCase không nhận Locale

`String.equalsIgnoreCase(String)` không có tham số `Locale`. Nó so sánh các ký tự theo quy tắc bỏ qua khác biệt chữ hoa/thường của Java, **không tạo một bản so sánh theo mọi quy tắc ngôn ngữ**. Tài liệu Java nêu rằng cách này có thể không cho kết quả phù hợp với một số locale; `Collator` hỗ trợ so sánh phụ thuộc locale.

```java
boolean equal = "Hello".equalsIgnoreCase("HELLO");
```

Đối với các từ ASCII thông thường, `equal` là `true`. Nhưng không nên suy ra `equalsIgnoreCase` có thể thay `Collator` hoặc Unicode full case folding trong mọi ngôn ngữ.

Đặc biệt, không có bảo đảm:

```text
a.equalsIgnoreCase(b)
==
a.toLowerCase(locale).equals(b.toLowerCase(locale))
```

Hai bên có thể khác nhau vì một bên không nhận locale, một bên nhận locale và còn có các ánh xạ Unicode một-nhiều. Nếu nghiệp vụ dựa trên việc so sánh, hãy định nghĩa **hợp đồng so sánh** riêng thay vì coi bất kỳ một phép chuyển chữ nào là giải pháp tổng quát.

### 9.2. Collator phục vụ thứ tự và so sánh theo ngôn ngữ

`java.text.Collator` cho phép so sánh chuỗi theo quy tắc locale:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("tr-TR"));
collator.setStrength(Collator.SECONDARY);
int result = collator.compare("text1", "text2");
```

Đây là **snippet** minh họa việc cấu hình. `Collator.SECONDARY` thường phân biệt dấu khác nhau nhưng không phân biệt chữ hoa/thường ở các quy tắc collation thông dụng; kết quả chi tiết tùy locale/provider. Không nên xem `Collator` là giải pháp cho **so sánh byte chính xác** hoặc xác thực token bảo mật. Với tìm kiếm văn bản đa ngôn ngữ lớn, cân nhắc công cụ tìm kiếm/collation hỗ trợ Unicode và các yêu cầu sản phẩm.

### 9.3. Locale.ROOT không phải Unicode full case folding

Unicode **case folding** là khái niệm dùng để tạo dạng so sánh không phân biệt hoa/thường theo quy tắc riêng. `String.toLowerCase(Locale.ROOT)` là một phép đổi sang chữ thường, không được đặc tả là **đầy đủ Unicode case folding**, nhất là khi có mở rộng nhiều code point, cấu trúc kết hợp và quy tắc bảo mật/ID.

Nếu yêu cầu so khớp đặc thù như tên người dùng Unicode không phân biệt hoa/thường, cần xác định rõ: normalization form (NFC/NFKC tùy quy chuẩn), Unicode case-folding, chính sách ký tự, phiên bản Unicode, kiểm tra ký tự dễ nhầm lẫn, và tính ổn định giữa các phiên bản. Các API chuẩn `String` không tự cung cấp toàn bộ những chính sách này.

## 10. toLowerCase/toUpperCase không giải quyết normalization

Hai chuỗi có thể trông giống nhau mà chứa dãy code point khác nhau:

```java
String composed = "\u00E9";   // é: một code point
String decomposed = "e\u0301"; // e + combining acute accent
```

`equals` thường trả `false` vì chuỗi UTF-16 khác nhau. Chuyển cả hai sang chữ thường không nhất thiết khiến chúng giống nhau. Nếu ứng dụng cần so sánh theo **canonical equivalence**, có thể chuẩn hóa với `java.text.Normalizer`:

```java
import java.text.Normalizer;
import java.util.Locale;

String a = Normalizer.normalize(
        composed.toLowerCase(Locale.ROOT), Normalizer.Form.NFC);
String b = Normalizer.normalize(
        decomposed.toLowerCase(Locale.ROOT), Normalizer.Form.NFC);
boolean equivalent = a.equals(b); // true với hai chuỗi minh họa
```

Đây là snippet cần hai biến `composed` và `decomposed` đã khai báo. Không có một thứ tự chuẩn hóa/chuyển chữ duy nhất phù hợp với mọi giao thức: cần theo yêu cầu miền ứng dụng. Normalization không tự xử lý tất cả khác biệt về viết hoa, cách sắp xếp theo ngôn ngữ, confusable Unicode hoặc ký tự tương đương theo nghĩa người dùng.

Đặc biệt với chuỗi có `İ`, `toLowerCase(Locale.ROOT)` có thể sinh thêm dấu `COMBINING DOT ABOVE`, khiến số lượng code point tăng. Do vậy, sau khi chuyển chữ có thể cần **kiểm tra lại độ dài, normalization và validation** nếu có ràng buộc dữ liệu.

## 11. Ứng dụng thực tế: key cấu hình và nội dung giao diện

### 11.1. Key kỹ thuật ổn định

Giả sử hệ thống cho phép người dùng nhập tên trường theo chuẩn ASCII, và muốn coi chữ hoa/chữ thường như nhau:

```java
import java.util.Locale;
import java.util.regex.Pattern;

static String normalizeAsciiKey(String key) {
    if (!Pattern.matches("[A-Za-z0-9_.-]+", key)) {
        throw new IllegalArgumentException("Invalid ASCII key");
    }
    return key.toLowerCase(Locale.ROOT);
}
```

Đây là **snippet của một phương thức trong lớp**. Nó tách hai bước:

1. **Validation:** key chỉ chứa ký tự được phép theo hợp đồng `[A-Za-z0-9_.-]+`.
2. **Canonicalization:** chuyển chữ cái ASCII bằng `Locale.ROOT`, không phụ thuộc locale người dùng/máy.

Cách này phù hợp khi **đặc tả của chính hệ thống thật sự giới hạn ASCII**. Nếu protocol cho phép Unicode, bước validation phải dùng một chính sách khác; không tự dùng regex ASCII cho tên người, nhãn hiển thị hoặc nội dung tiếng Việt.

### 11.2. Hiển thị tên/tiêu đề theo ngôn ngữ

```java
Locale displayLocale = Locale.forLanguageTag("tr-TR");
String heading = "istanbul";
String upperHeading = heading.toUpperCase(displayLocale);
```

Trong `tr-TR`, chữ `i` đầu có thể biến thành `İ`. Đây là điều đúng khi văn bản có ngữ cảnh ngôn ngữ Turkish. Tuy nhiên, `toUpperCase` chỉ chuyển chữ hoa, **không dịch** `heading` sang ngôn ngữ khác và **không làm title case**. Chuyển chữ cái đầu mỗi từ theo ngữ pháp/typography cũng không đơn giản là `toUpperCase` toàn bộ chuỗi.

### 11.3. Dữ liệu gốc và dữ liệu hiển thị

Không nên ghi đè giá trị gốc bằng phiên bản `toLowerCase` chỉ để hiển thị hoặc tìm kiếm, trừ khi nghiệp vụ đã định nghĩa đó là dạng canonical được lưu. Một chiến lược phổ biến là giữ giá trị gốc, đồng thời tạo một key chuẩn hóa **riêng** cho chỉ mục tìm kiếm theo hợp đồng. Điều này tránh mất thông tin như `ß → SS` và giúp tái thiết lập cách hiển thị của người dùng.

## 12. Kiểm thử bắt buộc cho hệ thống quốc tế hóa

Ít nhất nên kiểm thử các nhóm sau:

| Tình huống | Giá trị kiểm tra | Điều cần xác minh |
| --- | --- | --- |
| Locale tường minh | `Locale.ROOT`, `tr-TR` | Kết quả ổn định dù default locale của JVM khác |
| Chữ I | `TITLE`, `title`, `I`, `İ`, `ı` | Ánh xạ có chấm/không chấm đúng |
| Unicode một-nhiều | `straße` | `toUpperCase` có thể tăng độ dài |
| Ký tự theo ngữ cảnh | `ΟΣ` | Sigma cuối từ được xử lý theo chuỗi |
| Độ dài | Trước/sau casing | Không giả định chiều dài giữ nguyên |
| Kết hợp dấu | `é` và `e + U+0301` | Phân biệt casing với normalization |
| Key kỹ thuật | `TITLE` trong mọi locale | Canonicalization theo hợp đồng, không dùng default |
| Văn bản người dùng | Tiếng Việt, Turkish, Greek, German | Chọn locale đúng ngôn ngữ và review trực quan |
| So sánh | `equalsIgnoreCase`/`Collator` | Không nhầm phép chuyển chữ với collation |
| Dữ liệu bảo mật | Username/token/ID | Quy tắc mapping, normalization, validation rõ ràng |
| Chạy nhiều phiên bản JDK | Bộ ký tự Unicode đa dạng | Ghi nhận khác biệt theo phiên bản dữ liệu Unicode nếu có |

### Tại sao không chỉ kiểm thử tiếng Anh?

Một test với `"HELLO"` và `"hello"` thường đi qua cả các đường `Locale.ROOT`, `Locale.ENGLISH` và `tr-TR` mà không phát hiện sự khác biệt ở chữ `I`. Ngược lại `"TITLE"` hoặc `"IDENTIFIER"` làm lộ sai lầm ngay ở bước hạ chữ. Test thêm case nhiều-code-point như `İ` và `ß` sẽ phát hiện giả định không hợp lệ rằng kết quả luôn dài bằng đầu vào.

### Vì sao không dùng Locale.setDefault trong test đa luồng?

`Locale.setDefault(...)` thay đổi trạng thái toàn JVM và dễ gây nhiễu các test chạy đồng thời. Khi kiểm thử hành vi sản phẩm, truyền `Locale` tường minh cho mỗi hàm. Nếu bắt buộc kiểm tra overload không tham số, cô lập test, khôi phục default trong `finally` và tránh chạy đồng thời với các test khác dựa vào default locale.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `"TITLE".toLowerCase()` tạo key khác trên máy Turkish | Overload không tham số dùng default locale | Với key độc lập ngôn ngữ, dùng `Locale.ROOT` |
| `"title".toUpperCase()` có chữ `İ` | Turkish casing | Truyền đúng locale theo mục đích |
| Dùng `Locale.ENGLISH` cho mọi văn bản | Cho rằng tiếng Anh là quy tắc mặc định toàn cầu | Với văn bản tiếng khác, dùng locale của văn bản; với key kỹ thuật, `ROOT` |
| Dùng vòng `charAt(i)` rồi `Character.toUpperCase(...)` | Không xử lý 1:N và ngữ cảnh đầy đủ | Chuyển cả `String` bằng API có Locale |
| Dự đoán output giữ nguyên chiều dài | `ß` có thể thành `SS`, `İ` thành `i + dấu` | Không định vị theo index cũ nếu chuỗi đã đổi |
| Dùng `equalsIgnoreCase` thay Collator | Không phải so sánh theo locale | Chọn API đúng với hợp đồng tìm kiếm/sắp xếp |
| Dùng lowercase làm Unicode full case folding | Casing khác case folding | Thiết kế quy tắc Unicode profile rõ ràng |
| Tin rằng hai chuỗi nhìn giống nhau thì equals | Unicode normalization khác nhau | Dùng Normalizer nếu hợp đồng yêu cầu |
| Lưu bản uppercase/lowercase rồi bỏ bản gốc | Mất khả năng khôi phục cách viết | Giữ chuỗi nguồn và key xử lý riêng |
| Dùng `Locale.setDefault` theo từng request | Thay trạng thái dùng chung của JVM | Truyền locale vào mọi thao tác |
| Biến đổi username/token mà không có đặc tả | Có thể gây collision hoặc bypass logic | Xác định whitelist, normalization và so sánh an toàn |
| Dùng casing để dịch nội dung | Chỉ biến đổi hoa/thường, không dịch | Dùng ResourceBundle/i18n để bản địa hóa thông điệp |

## 14. Câu hỏi ôn tập

**Câu 1.** `"TITLE".toLowerCase(Locale.ROOT)` khác `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))` thế nào?

**Đáp án:** Với `ROOT`, chữ `I` thành `i` (`U+0069`). Với Turkish, `I` thành `ı` (`U+0131`). Các chuỗi `"title"` và `"tıtle"` khác nhau khi so sánh chính xác.

**Câu 2.** Có nên dùng `String.toLowerCase()` không tham số để chuẩn hóa key protocol?

**Đáp án:** Không, vì nó phụ thuộc default locale của JVM. Dùng `Locale.ROOT` hoặc thuật toán canonicalization được protocol quy định, kèm validation.

**Câu 3.** Vì sao `"straße".toUpperCase(Locale.GERMAN)` có thể dài hơn chuỗi ban đầu?

**Đáp án:** `ß` mở rộng thành `SS`; đó là ánh xạ Unicode một-nhiều. Độ dài từ 6 thành 7.

**Câu 4.** `"STRASSE".toLowerCase(Locale.GERMAN)` có trả lại `"straße"` không?

**Đáp án:** Không. Kết quả là `"strasse"`; chuyển hoa/thường không bảo đảm hoàn nguyên.

**Câu 5.** `equalsIgnoreCase` có tham số `Locale` không? Nó có thay `Collator` trong mọi trường hợp không?

**Đáp án:** Không có tham số locale, và không phải công cụ collation đầy đủ theo ngôn ngữ. Dùng bộ so sánh phù hợp yêu cầu.

**Câu 6.** `"İ".toLowerCase(Locale.ROOT)` có nhất thiết dài một code point không?

**Đáp án:** Không. Kết quả gồm `i` `U+0069` và dấu chấm kết hợp `U+0307`, hai code point. Trong `tr-TR`, nó thành một `i`.

**Câu 7.** Chuỗi có chữ tiếng Việt cùng hình thức hiển thị nhưng dùng code point dấu kết hợp khác nhau thì chỉ lowercase đã đủ để equals không?

**Đáp án:** Chưa chắc. Có thể cần normalization theo một form được thỏa thuận, ví dụ NFC; casing không mặc nhiên chuẩn hóa toàn bộ Unicode.

## 15. Ghi nhớ

- `String.toLowerCase(Locale)` và `toUpperCase(Locale)` có thể dùng quy tắc **ngôn ngữ/vùng**; hãy truyền locale tường minh khi mục đích đã rõ.
- Overload **không có `Locale`** dựa vào `Locale.getDefault()` và dễ làm định danh kỹ thuật phụ thuộc máy chủ.
- `Locale.ROOT` là lựa chọn thường phù hợp cho phép chuyển chữ **không phụ thuộc locale**, nhưng không thay hợp đồng xử lý/so sánh Unicode chuyên biệt của từng hệ thống.
- Các mapping Unicode có thể là **một-nhiều** và **phụ thuộc ngữ cảnh**: Turkish `I/İ`, German `ß`, Greek sigma là ví dụ quan trọng.
- Chuyển hoa/thường **không bảo đảm giữ độ dài**, **không hoàn nguyên**, **không thay thế normalization** và **không đồng nghĩa collation/case folding**.
- Chọn đúng `Locale` cho văn bản người dùng; kiểm thử ít nhất các tình huống Turkish, Greek và German trước khi đưa sản phẩm đa ngôn ngữ vào thực tế.

**Tài liệu chính thức:**

- [Java SE 21 — String, toLowerCase/toUpperCase](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Java SE 21 — Collator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Collator.html)
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Standard — Default Case Algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/)
