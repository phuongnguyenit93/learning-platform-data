# Khác biệt chữ I trong tiếng Thổ Nhĩ Kỳ: Unicode, Locale và chuyển chữ hoa/thường trong Java

## 1. Một chữ I có thể làm ứng dụng đa ngôn ngữ sai như thế nào?

Người phát triển Java thường biết:

```java
"I".toLowerCase(Locale.ENGLISH) // "i"
"i".toUpperCase(Locale.ENGLISH) // "I"
```

Nhưng quy tắc trên **không đúng cho tất cả ngôn ngữ**. Tiếng Thổ Nhĩ Kỳ (`tr`/`tr-TR`) phân biệt hai cặp chữ:

- **I ↔ ı**: chữ I hoa **không chấm** (U+0049) ↔ chữ ı thường **không chấm** (U+0131).
- **İ ↔ i**: chữ İ hoa **có chấm** (U+0130) ↔ chữ i thường **có chấm** (U+0069).

Do đó, kết quả của `String.toLowerCase(locale)` và `String.toUpperCase(locale)` có thể thay đổi theo `Locale`. Lỗi này thường được gọi là **Turkish I problem** trong quá trình quốc tế hóa phần mềm.

Ví dụ thực tế: tên khóa kỹ thuật `"TITLE"` trong một chương trình Java được chuyển sang chữ thường. Nếu dùng `"TITLE".toLowerCase()` mà máy chủ đang có default locale tiếng Thổ Nhĩ Kỳ, kết quả là `"tıtle"`, chứa chữ **ı** U+0131, **khác** `"title"` chứa chữ **i** U+0069.

Một phép tra `map.get("title")` hoặc so sánh `equals` có thể thất bại dù nhìn qua font chữ khó nhận ra. Vấn đề không nằm ở Java “dịch sai”: ta đã sử dụng **quy tắc ngôn ngữ của người dùng cho một định danh kỹ thuật cần độc lập với ngôn ngữ**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Nhận diện bốn Unicode code points `I`, `i`, `İ`, `ı` và hai cặp chữ hoa/thường trong tiếng Thổ Nhĩ Kỳ.
2. Phân biệt `String.toLowerCase()` (dùng default locale), `String.toLowerCase(Locale)` và `Locale.ROOT`.
3. Xác định khi nào phải chuyển case **theo ngôn ngữ hiển thị** và khi nào phải xử lý **định danh máy** độc lập locale.
4. Hiểu giới hạn của `Character.toLowerCase`, `equalsIgnoreCase`, `Collator`, Unicode normalization và regex.
5. Viết test Java 17 tái hiện lỗi để ngăn sự cố ở production.

## 2. Bốn chữ, hai cặp: nhìn giống nhưng mã Unicode khác

| Chữ | Tên Unicode | Code point | Vai trò trong tiếng Thổ Nhĩ Kỳ |
| --- | --- | --- | --- |
| `I` | LATIN CAPITAL LETTER I | U+0049 | Chữ **hoa không chấm** |
| `ı` | LATIN SMALL LETTER DOTLESS I | U+0131 | Chữ **thường không chấm** |
| `İ` | LATIN CAPITAL LETTER I WITH DOT ABOVE | U+0130 | Chữ **hoa có chấm** |
| `i` | LATIN SMALL LETTER I | U+0069 | Chữ **thường có chấm** |

Đây là **bốn code points khác nhau**, không phải bốn cách vẽ của cùng một ký tự. Trong font kém hỗ trợ hoặc bảng điều khiển khó đọc, chữ `I` và `İ` có thể khác nhau ở một dấu chấm rất nhỏ; `i` và `ı` khác ở chỗ có/không có dấu chấm.

Sơ đồ hai cặp:

```text
Tiếng Thổ Nhĩ Kỳ:
    HOA         thường
     I    <-->     ı       (không chấm)
     İ    <-->     i       (có chấm)

Quy tắc tiếng Anh thường gặp:
     I    <-->     i

Không thể dùng cặp tiếng Anh thay thế cả hai cặp tiếng Thổ.
```

**Không nhầm với dấu tiếng Việt**: Unicode `İ` không đơn thuần là `I` ASCII được render cùng dấu chấm theo một font khác. Cả `İ` và `ı` đều có code point riêng.

### Thứ tự đúng cho case mapping tiếng Thổ

Với `Locale.forLanguageTag("tr-TR")`:

| Đầu vào | `toLowerCase(tr)` | `toUpperCase(tr)` |
| --- | --- | --- |
| `I` (U+0049) | `ı` (U+0131) | `I` (U+0049) |
| `ı` (U+0131) | `ı` (U+0131) | `I` (U+0049) |
| `İ` (U+0130) | `i` (U+0069) | `İ` (U+0130) |
| `i` (U+0069) | `i` (U+0069) | `İ` (U+0130) |

Với locale độc lập ngôn ngữ như `Locale.ROOT`, `I → i` và `i → I` theo quy tắc Unicode mặc định. Tuy nhiên, `İ` khi chuyển chữ thường theo `Locale.ROOT` thường thành **hai code points**: `i` (U+0069) rồi **COMBINING DOT ABOVE** (U+0307). Đây là ví dụ chứng minh rằng chuyển case Unicode không phải lúc nào cũng là phép ánh xạ **một code point → một code point**.

## 3. Phân biệt ba cách gọi trong Java

### 3.1. Không truyền Locale

```java
String lower = "TITLE".toLowerCase();
String upper = "title".toUpperCase();
```

Cả hai overload không đối số dùng **locale mặc định của JVM** (tương đương với `toLowerCase(Locale.getDefault())` và `toUpperCase(Locale.getDefault())`). Kết quả có thể phụ thuộc máy chủ, máy CI, container hoặc cấu hình hệ điều hành.

Đây là vấn đề khi chuỗi không phải văn bản người dùng mà là **tên biến, identifier, protocol key, constant, enum name, HTTP header name, database field name** hoặc một mã máy cần ổn định trên mọi máy.

### 3.2. Truyền locale của ngôn ngữ thật

```java
Locale turkish = Locale.forLanguageTag("tr-TR");

String label = "İSTANBUL";
String lower = label.toLowerCase(turkish);
```

Với tiếng Thổ Nhĩ Kỳ, `lower` trở thành `istanbul` như mong đợi về chữ chấm. Đây là cách hợp lý khi xử lý **văn bản tự nhiên của người dùng tiếng Thổ**, ví dụ nhãn hiển thị, tìm kiếm hoặc đối chiếu theo ngôn ngữ.

### 3.3. Dùng `Locale.ROOT` cho định danh độc lập locale

```java
String key = "TITLE".toLowerCase(Locale.ROOT);
```

`key` trở thành `title` và không bị thay bởi locale mặc định tiếng Thổ, tiếng Việt hay tiếng Anh của JVM.

**Nguyên tắc thiết kế:** định danh kỹ thuật phải tuân thủ một **hợp đồng chuẩn hóa bất biến**. Với protocol và token chỉ gồm ASCII, `Locale.ROOT` thường thích hợp để thực hiện case mapping độc lập locale. Đối với định danh Unicode không giới hạn, `Locale.ROOT` **chưa đủ** làm hệ thống “case-folding an toàn” hoàn chỉnh: cần quy định thêm Unicode normalization, case folding, phiên bản Unicode, danh sách ký tự được phép và quy tắc chống trùng/giả mạo.

## 4. Chương trình Java 17 hoàn chỉnh: quan sát hai cặp chữ

Tạo tệp `TurkishIDemo.java`:

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class TurkishIDemo {
    private static final Locale TR =
            Locale.forLanguageTag("tr-TR");

    private static String points(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String[] inputs = {
                "I", "i", "\u0130", "\u0131"
        };

        for (String input : inputs) {
            System.out.println(
                    points(input)
                    + " lowerTR=" + points(input.toLowerCase(TR))
                    + " upperTR=" + points(input.toUpperCase(TR)));
        }

        System.out.println("TITLE root=" +
                points("TITLE".toLowerCase(Locale.ROOT)));
        System.out.println("TITLE tr=" +
                points("TITLE".toLowerCase(TR)));
        System.out.println("title tr upper=" +
                points("title".toUpperCase(TR)));
    }
}
```

Lưu nguồn UTF-8, chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 TurkishIDemo.java
java TurkishIDemo
```

**Stdout xác định**, dùng mã U+ để tránh phụ thuộc font hay encoding terminal:

```text
U+0049 lowerTR=U+0131 upperTR=U+0049
U+0069 lowerTR=U+0069 upperTR=U+0130
U+0130 lowerTR=U+0069 upperTR=U+0130
U+0131 lowerTR=U+0131 upperTR=U+0049
TITLE root=U+0074 U+0069 U+0074 U+006C U+0065
TITLE tr=U+0074 U+0131 U+0074 U+006C U+0065
title tr upper=U+0054 U+0130 U+0054 U+004C U+0045
```

Giải thích:

- `I` (U+0049) chuyển thành `ı` (U+0131) khi dùng `TR`.
- `i` (U+0069) chuyển thành `İ` (U+0130) khi dùng `TR`.
- `"TITLE".toLowerCase(Locale.ROOT)` có code point thứ hai U+0069.
- `"TITLE".toLowerCase(TR)` có code point thứ hai U+0131.
- `"title".toUpperCase(TR)` có code point thứ hai U+0130 thay cho ASCII `I`.

Vì `String.equals` so sánh chuỗi code units, `"title".equals("tıtle")` là `false`. Đây là **hai chuỗi khác nhau**, dù giao diện font nhỏ có thể làm người đọc tưởng giống.

## 5. Lỗi production: định danh kỹ thuật bị đổi theo JVM default

Giả sử một ứng dụng dùng `Map` để tra thuộc tính tên `"title"`:

```java
Map<String, String> attributes = Map.of(
        "title", "Hướng dẫn Java");
String rawKey = "TITLE";
String normalized = rawKey.toLowerCase();
String title = attributes.get(normalized);
```

Đây là đoạn minh họa trong method. Nếu JVM default locale là tiếng Thổ Nhĩ Kỳ, `normalized` là `tıtle`, nên `Map.get` trả `null`. Khi chạy ở môi trường có default locale khác, nó lại có thể thành `title` và hoạt động.

### 5.1. Chương trình Java độc lập tái hiện lỗi

Tệp `TurkishMapBugDemo.java`:

```java
import java.util.Locale;
import java.util.Map;

public class TurkishMapBugDemo {
    public static void main(String[] args) {
        Locale original = Locale.getDefault();
        try {
            // Chỉ mô phỏng trong chương trình demo một luồng.
            Locale.setDefault(Locale.forLanguageTag("tr-TR"));

            Map<String, String> data = Map.of(
                    "title", "FOUND");

            String input = "TITLE";

            String unsafeKey = input.toLowerCase();
            String stableKey = input.toLowerCase(Locale.ROOT);

            System.out.println("unsafeFound=" +
                    (data.get(unsafeKey) != null));
            System.out.println("stableFound=" +
                    (data.get(stableKey) != null));
            System.out.println("unsafeEqualsTitle=" +
                    unsafeKey.equals("title"));
            System.out.println("stableEqualsTitle=" +
                    stableKey.equals("title"));
        } finally {
            Locale.setDefault(original);
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac -encoding UTF-8 TurkishMapBugDemo.java
java TurkishMapBugDemo
```

Stdout:

```text
unsafeFound=false
stableFound=true
unsafeEqualsTitle=false
stableEqualsTitle=true
```

**Vì sao phải khôi phục default locale?** `Locale.setDefault` sửa trạng thái **toàn JVM**. Demo dùng `try/finally` để trả về môi trường ban đầu, nhưng việc này **không biến thao tác thành thread-safe**. Tuyệt đối không đổi `Locale.setDefault(...)` theo từng request trong web server: nhiều người dùng đồng thời có thể thấy kết quả khác nhau và ảnh hưởng cả thư viện thứ ba.

Trong ứng dụng thực tế, sửa đúng bằng `toLowerCase(Locale.ROOT)` ở nơi định nghĩa key kỹ thuật, chứ không phải ép default locale của server thành English để giấu bug.

### 5.2. Các nơi dễ bị ảnh hưởng

- Chuẩn hóa key từ input/JSON config trước khi tra `Map`.
- Chuyển tên enum, mã trạng thái, parser token, tên trường trong protocol.
- Bắt cặp tên khóa khi import/export CSV, cấu hình hoặc metadata.
- Logic check đường dẫn/tên file theo chuỗi chữ thường; cần biết quy tắc của hệ điều hành và filesystem.
- So sánh chuỗi dùng làm định danh được lưu giữa nhiều máy JVM khác locale.
- Tạo tên cột, tham số hoặc lookup key bằng phép nối với một từ tiếng Anh chứa I/i.

**Đừng sửa bằng cách ép mọi văn bản người dùng dùng `Locale.ROOT`.** Với câu tiếng Thổ, đây lại là lỗi localization. Cách sửa là xác định **phạm vi**: machine identifier cần ổn định độc lập locale, còn natural-language text cần locale phù hợp.

## 6. Chuyển case theo locale và không theo locale: dùng khi nào?

| Bối cảnh | Hướng xử lý | Lý do |
| --- | --- | --- |
| Label UI tiếng Thổ Nhĩ Kỳ | `toUpperCase(trLocale)` / `toLowerCase(trLocale)` | Tôn trọng quy tắc I/İ/ı/i |
| Tìm kiếm văn bản tự nhiên tiếng Thổ | Locale-sensitive collation/matching theo yêu cầu | So sánh có ngữ nghĩa ngôn ngữ |
| Key nội bộ ASCII `TITLE` | `toLowerCase(Locale.ROOT)` hoặc chính sách key canonical | Ổn định qua môi trường |
| Mã enum, trạng thái, protocol token | Đúng đặc tả protocol; thường ASCII/ROOT | Locale người dùng không nên ảnh hưởng hợp đồng máy |
| Tên người và địa danh | Không tự thay đổi cách viết gốc khi lưu; chỉ biến đổi bản hiển thị khi cần | Case có thể mang ý nghĩa ngôn ngữ |
| Tên đăng nhập không phân biệt hoa/thường | Chính sách Unicode/case folding/normalization rõ ràng | `Locale.ROOT` một mình chưa đủ bảo đảm chống trùng |
| Password hoặc token bí mật | Không tự lower-case | Có thể làm thay đổi credential, phá tính phân biệt |
| HTML/XML/URL/schema identifier | Theo đúng spec của từng định dạng | Không áp locale của người dùng cho mã cú pháp |

**Ví dụ ranh giới:** Hiển thị tiêu đề tiếng Thổ `"İSTANBUL"` thành `"istanbul"` là chuyện ngôn ngữ. Chuyển key JSON `"TITLE"` thành `"title"` là chuyện contract kỹ thuật. Hai hành động nhìn giống nhau ở code nhưng phải **chọn locale khác nhau**.

## 7. Câu chuyện của chữ İ: một code point có thể thành hai

Đây là vấn đề tinh vi ngay cả khi không dùng locale tiếng Thổ.

`İ` là U+0130, Latin capital letter I with dot above. Theo quy tắc Unicode default case conversion, khi chuyển chữ thường độc lập locale, nó có thể tạo chuỗi:

```text
U+0130 LATIN CAPITAL LETTER I WITH DOT ABOVE
            |
            | lower-case default (Locale.ROOT)
            v
U+0069 LATIN SMALL LETTER I
U+0307 COMBINING DOT ABOVE
```

Trong tiếng Thổ, kết quả lại là một code point `i` U+0069, vì dấu chấm đã là thành phần đặc biệt của cặp `İ ↔ i`. Do đó, chuyển case có thể làm **thay đổi số Unicode code points** và độ dài `String`.

### Ví dụ Java 17 kiểm tra độ dài và code point

Tệp `DottedIExpansionDemo.java`:

```java
import java.util.Locale;

public class DottedIExpansionDemo {
    public static void main(String[] args) {
        String capitalDottedI = "\u0130";

        String root =
                capitalDottedI.toLowerCase(Locale.ROOT);
        String turkish =
                capitalDottedI.toLowerCase(
                        Locale.forLanguageTag("tr-TR"));

        System.out.println("originalUnits=" +
                capitalDottedI.length());
        System.out.println("rootUnits=" + root.length());
        System.out.println("turkishUnits=" +
                turkish.length());

        System.out.println("rootCodePoints=" +
                root.codePointCount(0, root.length()));
        System.out.println("turkishCodePoints=" +
                turkish.codePointCount(0, turkish.length()));

        System.out.println("rootIsPlainI=" +
                root.equals("i"));
        System.out.println("turkishIsPlainI=" +
                turkish.equals("i"));
    }
}
```

```bash
javac -encoding UTF-8 DottedIExpansionDemo.java
java DottedIExpansionDemo
```

Stdout theo quy tắc Unicode/Java 17:

```text
originalUnits=1
rootUnits=2
turkishUnits=1
rootCodePoints=2
turkishCodePoints=1
rootIsPlainI=false
turkishIsPlainI=true
```

Kết quả `rootIsPlainI=false` không phải vì Java thất bại; nó đang giữ thông tin dấu chấm trong dạng combining mark theo default case mapping.

**Hệ quả:** Không giả định `s.toLowerCase(locale).length() == s.length()`. Không dùng UTF-16 index ban đầu để trỏ thẳng vào chuỗi sau khi case conversion. Khi phân tích Unicode, phân biệt code units, code points và grapheme clusters.

## 8. `Character.toLowerCase` khác `String.toLowerCase(Locale)`

Java có các phương thức trên `Character`:

```java
int lowercaseCodePoint = Character.toLowerCase(0x0049);
int uppercaseCodePoint = Character.toUpperCase(0x0069);
```

Các API `Character.toLowerCase(int)` và `toUpperCase(int)` xử lý **simple Unicode case mapping** cho code point đơn, **không nhận tham số `Locale`**. Chúng không thực hiện đủ mọi phép biến đổi chuỗi phụ thuộc ngữ cảnh/ngôn ngữ, và không thể tự biểu diễn ánh xạ từ một code point thành **hai** code points.

Trong khi đó, `String.toLowerCase(Locale)` / `String.toUpperCase(Locale)` có thể:

- Dùng quy tắc đặc biệt theo locale như `tr-TR` và `az`.
- Phụ thuộc ngữ cảnh trong chuỗi đối với một số ngôn ngữ.
- Mở rộng một ký tự thành nhiều ký tự (ví dụ quy tắc uppercase/lowercase Unicode nhất định).

**Không** dùng vòng lặp `Character.toLowerCase(s.charAt(i))` để “tối ưu” một `String.toLowerCase(trLocale)`. Nó vừa không truyền locale, vừa có thể xử lý sai code points ngoài BMP khi duyệt từng `char`. Sử dụng API chuỗi với locale hoặc thư viện Unicode đúng yêu cầu.

### Ví dụ không nên viết

```java
StringBuilder lower = new StringBuilder();
for (int i = 0; i < text.length(); i++) {
    lower.append(Character.toLowerCase(text.charAt(i)));
}
```

Đây là đoạn minh họa trong method với biến `text`. Nó không tuân quy tắc Turkish I và không xử lý đầy đủ các ánh xạ nhiều-code-point. Khi cần lower-case text người dùng, hãy gọi `text.toLowerCase(selectedLocale)`.

## 9. `equalsIgnoreCase` có thật sự “hiểu tiếng Thổ” không?

`String.equalsIgnoreCase` **không nhận `Locale`**. Theo đặc tả Java, nó sử dụng phép so sánh không phân biệt case dựa trên `Character`/Unicode cho từng code point, **không tuân riêng hệ thống cặp chữ của tiếng Thổ**.

Do đó, không được dùng kết quả:

```java
boolean same = a.equalsIgnoreCase(b);
```

như phép khẳng định hai từ tiếng Thổ giống nhau theo quy tắc ngôn ngữ. Tương tự, `String.CASE_INSENSITIVE_ORDER` và `compareToIgnoreCase` không phải thuật toán collation theo từng locale.

Chú ý hai loại câu hỏi có ý nghĩa khác nhau:

1. **Có phải cùng key của máy sau khi chuẩn hóa theo hợp đồng không?** Dùng một canonicalization được định nghĩa rõ, ví dụ ASCII-only key + `Locale.ROOT`.
2. **Có phải cùng từ khi người dùng tiếng Thổ tìm kiếm bất chấp chữ hoa/thường không?** Cần so khớp có xét **locale**, có thể dùng `Collator` hoặc công cụ tìm kiếm Unicode được cấu hình Turkish collation.

Một hệ thống xử lý tên người, danh sách hoặc từ điển tiếng Thổ phải cân nhắc phân biệt **I/ı** và **İ/i**; không gom tất cả vào một nhóm chỉ vì trông giống chữ I.

## 10. `Collator`: so sánh chuỗi theo ngôn ngữ

`java.text.Collator` dùng các quy tắc so sánh văn bản theo locale. Nó không thay thế hoàn toàn engine tìm kiếm, nhưng phù hợp để sắp xếp và so sánh từ ngữ khi yêu cầu văn hóa địa phương.

Khởi tạo cho tiếng Thổ:

```java
Collator collator = Collator.getInstance(
        Locale.forLanguageTag("tr-TR"));
collator.setStrength(Collator.PRIMARY);
```

`PRIMARY` có thể bỏ qua những khác biệt ở cấp độ phụ như case trong ngữ cảnh quy tắc collation của locale. Với tiếng Thổ, chữ I không chấm và chữ i có chấm thuộc **hai cặp chữ cái riêng**, vì thế việc dùng `Collator` có ngữ nghĩa khác với ép tất cả ký tự thành lowercase theo `Locale.ROOT`.

### Ví dụ Java 17 độc lập

Tệp `TurkishCollationDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class TurkishCollationDemo {
    public static void main(String[] args) {
        Locale turkish = Locale.forLanguageTag("tr-TR");
        Collator collator = Collator.getInstance(turkish);
        collator.setStrength(Collator.PRIMARY);

        System.out.println("I-dotlessI=" +
                (collator.compare("I", "\u0131") == 0));
        System.out.println("dottedI-i=" +
                (collator.compare("\u0130", "i") == 0));
        System.out.println("I-i=" +
                (collator.compare("I", "i") == 0));
        System.out.println("i-dotlessI=" +
                (collator.compare("i", "\u0131") == 0));
    }
}
```

```bash
javac -encoding UTF-8 TurkishCollationDemo.java
java TurkishCollationDemo
```

Với bộ quy tắc collation tiếng Thổ phổ biến của JDK 17 (provider hỗ trợ tiếng Thổ), **kỳ vọng về quan hệ** là:

```text
I-dotlessI=true
dottedI-i=true
I-i=false
i-dotlessI=false
```

Kết quả của `Collator` phụ thuộc provider và dữ liệu locale; nếu ứng dụng hỗ trợ nhiều JDK/CLDR/provider, cần **kiểm thử trực tiếp trên runtime triển khai**. Bảng kỳ vọng này thể hiện nguyên tắc hai cặp chữ, không phải một lời hứa về mọi cấu hình Java có provider tùy chỉnh.

**Không chia sẻ một `Collator` mutable rồi thay strength/locale đồng thời giữa request**. Có thể tạo riêng, clone khi thích hợp hoặc có chiến lược cache an toàn; dùng `CollationKey` khi cần tối ưu so sánh nhiều chuỗi.

### So sánh không đồng nghĩa tìm kiếm

`Collator` xử lý so sánh/sắp xếp theo locale. Tìm kiếm toàn văn có thể cần thêm tokenizer, bộ phân tích ngôn ngữ, Unicode normalization, thiết kế prefix matching và khả năng đồng nhất với collation ở database. Đừng suy `Collator.PRIMARY` là bộ tìm kiếm tiếng Thổ hoàn chỉnh cho mọi miền dữ liệu.

## 11. Unicode normalization: dấu chấm còn có dạng tổ hợp

Một số văn bản Unicode có biểu diễn **composed** và **decomposed**. Với chữ İ U+0130, dạng phân rã canonical là:

```text
composed:   U+0130            (İ)
decomposed: U+0049 U+0307     (I + COMBINING DOT ABOVE)
```

Hai chuỗi này có thể trông giống nhau nhưng `String.equals` sẽ khác khi chưa normalize. `java.text.Normalizer` cho phép áp dụng NFC/NFD.

Ví dụ:

```java
String composed = "\u0130";
String decomposed = "I\u0307";
boolean before = composed.equals(decomposed); // false

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
boolean after = composed.equals(normalized);   // true
```

Đây là đoạn mã minh họa trong method, cần import `java.text.Normalizer`.

**Normalization và case conversion là hai việc khác nhau:**

- **Normalization** xử lý những dạng biểu diễn Unicode tương đương/có quan hệ tương thích theo quy tắc được chọn.
- **Case conversion** áp dụng quy tắc chữ hoa/thường, có thể phụ thuộc locale.
- **Collation** quyết định quan hệ sắp xếp/so sánh ngôn ngữ, không nhất thiết tạo một chuỗi canonical duy nhất.
- **Case folding** là cơ chế Unicode phục vụ so khớp caseless; các quy tắc full folding khác với thao tác lowercase đơn giản và không đồng nghĩa Turkish-specific casing.

Trong một hệ thống tìm kiếm, **thứ tự normalize/case-convert có thể ảnh hưởng kết quả** với các dấu kết hợp. Hãy xây dựng và kiểm thử một pipeline cố định cho từng loại dữ liệu. Không tự xóa U+0307 chỉ để “sửa lỗi Turkish I” vì có thể thay đổi nghĩa của ký tự trong ngôn ngữ khác.

### 11.1. Code point và grapheme cluster

`"i\u0307"` chứa hai Unicode code points nhưng thường hiển thị như một chữ i có dấu chấm. `String.length()` trả số UTF-16 code units; `String.codePointCount` trả số code points; cả hai chưa chắc phản ánh số ký tự người dùng cảm nhận.

Khi làm nổi bật kết quả tìm kiếm hoặc dùng chỉ số bắt đầu/kết thúc của một chuỗi sau chuyển case, phải nhớ **độ dài có thể thay đổi** do mapping `İ → i + combining dot`. Không dùng chỉ số đã tính trên chuỗi trước biến đổi để cắt chuỗi sau biến đổi.

## 12. Regex không tự biết locale người dùng

Java có các flag như:

- `Pattern.CASE_INSENSITIVE`: bật matching không phân biệt case (mặc định chủ yếu áp dụng ASCII trong regex Java).
- `Pattern.UNICODE_CASE`: kết hợp với `CASE_INSENSITIVE` cho phép Unicode-aware case-insensitive matching.
- `Pattern.UNICODE_CHARACTER_CLASS`: thay đổi ý nghĩa một số predefined character classes theo Unicode.

Các flag này **không nhận `Locale`**, vì thế không phải cách chỉ định quy tắc `tr-TR` cho mọi chữ I/i. Với pattern tìm kiếm tiếng Thổ, phải kiểm thử các cặp `I/ı` và `İ/i`, đồng thời cân nhắc thư viện/engine thực hiện case-insensitive matching có hỗ trợ locale.

Một lỗi khác là chạy `regex.matcher(text.toLowerCase(Locale.ROOT))` rồi kết luận có thể dùng các UTF-16 offsets từ text gốc: lowercase có thể làm đổi độ dài, đặc biệt với `İ`. Khi làm highlight, cần thiết kế mapping offsets hoặc tránh biến đổi text đầu vào theo cách phá vị trí.

Regex không thay thế collation, tokenization hay normalization policy.

## 13. Cách thiết kế production: phân tách văn bản và identifier

### 13.1. Tầng domain: giữ dữ liệu gốc

- Tên người, địa danh, nội dung người dùng: lưu đúng chữ gốc theo contract, không tự uppercase/lowercase khi ghi.
- Nếu cần search index, tạo trường canonical **riêng** với version của thuật toán; không ghi đè bản gốc.
- Nếu cần kiểm tra uniqueness, thống nhất quy tắc giữa Java application và database collation, tránh một phía coi `I` và `i` bằng nhau trong khi phía kia coi khác nhau.

### 13.2. Tầng UI: truyền `Locale` tường minh

```java
Locale displayLocale = Locale.forLanguageTag("tr-TR");
String shown = source.toUpperCase(displayLocale);
```

Locale có thể lấy từ sở thích người dùng, profile hoặc negotiation có supported locales và fallback. Đừng lấy một default JVM toàn cầu cho mọi người dùng trong web server nhiều locale.

### 13.3. Tầng protocol: hợp đồng máy độc lập locale

Với key kỹ thuật chỉ gồm ASCII:

```java
String canonicalKey(String input) {
    return input.toLowerCase(Locale.ROOT);
}
```

Đoạn này minh họa trong một class/method. Nó không tự validate ASCII hoặc chống spoofing; cần kiểm tra bộ ký tự được phép nếu protocol đòi hỏi giới hạn. Nếu dùng identifier nhạy cảm bảo mật, cần thêm validation, normalization và chính sách uniqueness rõ ràng; không dùng riêng `toLowerCase(Locale.ROOT)` như bảo đảm an toàn.

**Không “sửa” bằng cách set default locale của cả JVM thành `Locale.US`**. Đó chỉ là cách che việc gọi API thiếu locale, có thể làm bản dịch tiếng Thổ hoặc formatter ngày/số của người dùng hoạt động sai.

### 13.4. Tầng dữ liệu: database và search engine

Hệ thống có thể cùng lúc xử lý:

- Java `String.equalsIgnoreCase` theo quy tắc locale-neutral đơn giản;
- Database collation `tr-TR` theo ngữ nghĩa tiếng Thổ;
- Search engine dùng Unicode case folding;
- Frontend JavaScript `toLocaleLowerCase("tr-TR")`.

Các thành phần này **không nhất thiết cho cùng kết quả**. Cần chọn contract cho từng loại dữ liệu, đặc biệt định danh đăng nhập, email, tên hiển thị và khóa đối chiếu. Không giả định cùng chữ I chắc chắn map giống nhau ở mọi tầng.

Với dữ liệu người dùng, cách case-insensitive của tên thường phải theo locale cụ thể và xem cả normalized forms; với ID kỹ thuật, cần canonicalization và bộ ký tự nghiêm ngặt.

## 14. Test tái hiện để phòng hồi quy

### 14.1. Ma trận giá trị cần có

| Input | Locale | Hành vi kỳ vọng |
| --- | --- | --- |
| `"I"` | `tr-TR` lowercase | `"ı"` (U+0131) |
| `"i"` | `tr-TR` uppercase | `"İ"` (U+0130) |
| `"İ"` | `tr-TR` lowercase | `"i"` (U+0069) |
| `"ı"` | `tr-TR` uppercase | `"I"` (U+0049) |
| `"TITLE"` | `Locale.ROOT` lowercase | `"title"` |
| `"TITLE"` | `tr-TR` lowercase | `"tıtle"` |
| `"İ"` | `Locale.ROOT` lowercase | `"i\u0307"` (2 code points) |
| `"İ"` | `tr-TR` lowercase | `"i"` (1 code point) |
| `"I"` và `"i"` | `equalsIgnoreCase` | Không kết luận đây là phép so sánh tiếng Thổ |
| `"I"` và `"ı"` | `Collator tr-TR` | Cần xác minh theo collation locale/provider |

### 14.2. Java 17 runnable: assertions độc lập locale mặc định

Tệp `TurkishIAssertions.java`:

```java
import java.util.Locale;

public class TurkishIAssertions {
    private static final Locale TR =
            Locale.forLanguageTag("tr-TR");

    private static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    public static void main(String[] args) {
        check("I".toLowerCase(TR).equals("\u0131"),
                "I-to-dotless-i");
        check("i".toUpperCase(TR).equals("\u0130"),
                "i-to-dotted-I");
        check("\u0130".toLowerCase(TR).equals("i"),
                "dotted-I-to-i");
        check("\u0131".toUpperCase(TR).equals("I"),
                "dotless-i-to-I");

        check("TITLE".toLowerCase(Locale.ROOT).equals("title"),
                "machine-key");
        check("\u0130".toLowerCase(Locale.ROOT)
                        .equals("i\u0307"),
                "unicode-expansion");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 TurkishIAssertions.java
java TurkishIAssertions
```

Stdout:

```text
PASS I-to-dotless-i
PASS i-to-dotted-I
PASS dotted-I-to-i
PASS dotless-i-to-I
PASS machine-key
PASS unicode-expansion
```

Nếu một assertion không đạt, đó là tín hiệu cần xem lại runtime, nguồn mã, quy tắc được kỳ vọng hoặc API được dùng. Khi chạy test đa môi trường, ghi rõ JDK 17+ và bộ locale/provider; đừng chỉ test trên developer machine có default tiếng Anh.

### 14.3. Thử default locale của JVM một cách cô lập

Nên test một chương trình riêng (không chạy song song với test phụ thuộc default JVM) để chứng minh `"TITLE".toLowerCase()` nhạy với default locale. Không thay `Locale.setDefault` trong một server request hoặc một tập unit test chạy parallel không được cô lập.

Với web app, test cả đường đi: HTTP header/profile locale → locale resolver → display case mapping. Đồng thời test các key/mã máy vẫn được canonicalize `Locale.ROOT` dù người dùng chọn tiếng Thổ.

### 14.4. Khi có nhiều văn bản Unicode khác nhau

Kiểm tra các dạng:

- `İ` (U+0130) so với `I + U+0307` (decomposed);
- `i + U+0307` sau default case mapping;
- `ı` (U+0131) so với `i` (U+0069);
- các từ chứa nhiều chữ I/i ở đầu, giữa và cuối;
- ký tự supplementary và dấu kết hợp nếu pipeline làm việc trên mọi Unicode;
- text hiển thị dưới font/terminal không hỗ trợ đầy đủ.

Các bài test so sánh kết quả theo code point (ví dụ in `U+0131`) thường tin cậy hơn việc chỉ nhìn chữ trên terminal.

## 15. Câu hỏi thường gặp

**Câu 1.** Vì sao `"TITLE".toLowerCase()` đôi khi không thành `"title"`?

**Trả lời:** overload không có locale dùng JVM default locale. Trong tiếng Thổ Nhĩ Kỳ, `I` thường hóa thành `ı` không chấm, tạo `tıtle`.

**Câu 2.** Nếu cần lowercase tên biến, protocol key hoặc mã định danh máy, nên làm gì?

**Trả lời:** Dùng contract độc lập locale; thường `toLowerCase(Locale.ROOT)` với identifier ASCII, cộng validation theo giao thức. Không dùng locale của người xem.

**Câu 3.** Nếu tên người dùng là tiếng Thổ, có nên luôn dùng `Locale.ROOT`?

**Trả lời:** Không. Với thao tác hiển thị/chuyển chữ hoa-thường theo ngôn ngữ, dùng locale phù hợp như `tr-TR`. Với đăng nhập/uniqueness, cần định nghĩa quy tắc canonicalization riêng, nhất quán qua mọi hệ thống.

**Câu 4.** `Character.toLowerCase('I')` có hiểu chữ ı tiếng Thổ không?

**Trả lời:** Không có tham số locale nên không thể áp đúng mọi case mapping đặc biệt cho ngôn ngữ. Dùng `String.toLowerCase(trLocale)` khi cần chuyển cả chuỗi theo tiếng Thổ.

**Câu 5.** `equalsIgnoreCase` có thay được `Collator` không?

**Trả lời:** Không. `equalsIgnoreCase` không nhận locale, còn `Collator` dựa vào các quy tắc so sánh cho ngôn ngữ. Chúng có mục tiêu khác nhau.

**Câu 6.** Vì sao chữ `İ` có thể thành hai code points khi lowercase mặc định?

**Trả lời:** Unicode default mapping giữ `i` cộng dấu chấm kết hợp `U+0307`. Trong quy tắc tiếng Thổ, `İ` chuyển thành một `i`.

**Câu 7.** Có nên dùng `Normalizer.NFC` rồi coi đã giải quyết xong Turkish I?

**Trả lời:** Không. Normalization xử lý biểu diễn Unicode, không chọn quy tắc chữ hoa/thường đúng ngôn ngữ. Vẫn cần quyết định locale và case comparison/collation.

**Câu 8.** Vì sao không dùng `Locale.setDefault(tr)` cho từng HTTP request?

**Trả lời:** Default locale là trạng thái JVM dùng chung. Request khác có thể bị ảnh hưởng; hãy truyền `Locale` tường minh vào xử lý văn bản.

**Câu 9.** Regex với `CASE_INSENSITIVE | UNICODE_CASE` có đảm bảo so khớp tiếng Thổ không?

**Trả lời:** Không. Các flag này không có tham số locale; cần test rõ cặp I/ı và İ/i hoặc dùng cơ chế so khớp theo locale phù hợp.

**Câu 10.** Có thể dùng `String.toLowerCase(Locale.ROOT)` làm bảo đảm an toàn cho mọi username Unicode không?

**Trả lời:** Không. Đây không phải Unicode full case folding/normalization/security profile toàn diện; phải thiết kế thêm quy tắc cho phép ký tự, trùng lặp và chống spoofing.

## 16. Ghi nhớ

- Tiếng Thổ Nhĩ Kỳ có **hai cặp chữ**: **I ↔ ı** và **İ ↔ i**. Không coi mọi chữ giống hình I/i là một cặp duy nhất.
- `String.toLowerCase()` và `toUpperCase()` không đối số dùng **default locale của JVM**, có thể làm key kỹ thuật sai trong môi trường `tr-TR`.
- Với **văn bản tự nhiên tiếng Thổ**, dùng `toLowerCase(trLocale)` hoặc `toUpperCase(trLocale)` khi nghiệp vụ thực sự cần chuyển case.
- Với **identifier độc lập ngôn ngữ**, thiết kế canonicalization ổn định (thường `Locale.ROOT` cho ASCII), kèm validation; không dùng user locale.
- `String` hỗ trợ ánh xạ phụ thuộc locale và có thể đổi độ dài; `Character` chỉ có simple per-code-point mapping, không đủ cho mọi trường hợp.
- `equalsIgnoreCase`/regex Unicode flag không tự thay thế **locale-aware collation**; sử dụng `Collator` hoặc cơ chế tìm kiếm được cấu hình phù hợp khi xử lý từ ngữ tiếng Thổ.
- `Normalizer`, case conversion, case folding và collation là những thao tác khác nhau. Hãy định nghĩa rõ pipeline và test bằng Unicode code points.
- Không đổi default locale toàn JVM cho từng request. **Truyền locale tường minh**, kiểm thử cả English/ROOT và Turkish trong Java 17.

### Tài liệu tham khảo Java 17 và Unicode

- [Oracle Java 17 — String: toLowerCase, toUpperCase, equalsIgnoreCase](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Oracle Java 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Oracle Java 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Oracle Java 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Oracle Java 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Standard — Special Casing](https://www.unicode.org/Public/UCD/latest/ucd/SpecialCasing.txt)
