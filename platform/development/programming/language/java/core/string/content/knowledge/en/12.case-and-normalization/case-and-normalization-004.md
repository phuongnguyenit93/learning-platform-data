# Đổi hoa–thường có thể làm thay đổi độ dài chuỗi trong Java

Nhiều lập trình viên quen với ví dụ `"java".toUpperCase()` trả về `"JAVA"` và nghĩ rằng đổi hoa–thường chỉ thay từng ký tự bằng một ký tự khác ở cùng vị trí. **Điều đó không đúng cho Unicode.** Khi dùng `String.toUpperCase(Locale)` hoặc `String.toLowerCase(Locale)`, một ký tự Unicode có thể được ánh xạ thành **nhiều ký tự/code point**, hoặc kết quả phụ thuộc vào ngữ cảnh và ngôn ngữ. Vì vậy, `length()` và các chỉ số UTF-16 của chuỗi kết quả có thể khác chuỗi gốc.

Ví dụ nổi bật trên JDK 17 trở lên:

```java
String before = "Straße";
String after = before.toUpperCase(java.util.Locale.ROOT);

System.out.println(before);           // Straße
System.out.println(after);            // STRASSE
System.out.println(before.length());  // 6
System.out.println(after.length());   // 7
```

Chữ `ß` trong `Straße` có thể được ánh xạ thành hai chữ `SS` khi chuyển hoa. Do đó, nội dung **và cả độ dài** thay đổi. Đây là hành vi chuyển đổi Unicode có chủ đích, không phải lỗi bộ nhớ hay do `String` có thể sửa tại chỗ.

## 1. `String.length()` thật sự đếm gì?

Trong Java, `String.length()` trả về số **UTF-16 code unit** (`char`), không bảo đảm bằng số code point Unicode hay số ký tự mà con người nhận thấy trên màn hình.

Ba khái niệm cần tách:

| Đơn vị | Ý nghĩa | Liên hệ tới Java |
| --- | --- | --- |
| UTF-16 code unit | Một đơn vị 16 bit | `String.length()` và `charAt(index)` dùng đơn vị này |
| Unicode code point | Một mã điểm Unicode, có thể chiếm một hoặc hai UTF-16 code unit | `codePointCount(...)` và `codePoints()` |
| Grapheme cluster | Một cụm ký tự mà người đọc thường coi là một ký tự hiển thị | Có thể gồm nhiều code point, ví dụ chữ và dấu kết hợp; `length()` không đếm cụm này |

Một code point ngoài BMP như U+1F600 (😀) chiếm **hai** UTF-16 code unit. Ngược lại, dấu kết hợp U+0307 là một code point riêng, thường được hiển thị cùng một chữ cái đứng trước. Bởi vậy, thay đổi độ dài theo UTF-16 có thể đến từ việc chuyển một code point thành nhiều code point, hoặc từ cách biểu diễn ký tự mới.

Phép đổi hoa–thường của `String` hoạt động trên văn bản Unicode, không có hợp đồng bảo toàn độ dài tính theo bất kỳ đơn vị nào ở trên. Khi đánh giá kết quả, cần kiểm tra **giá trị kết quả**, không dự đoán kích thước chỉ từ dữ liệu nguồn.

## 2. Vì sao một chữ có thể chuyển thành nhiều chữ?

Unicode hỗ trợ cả **ánh xạ đơn giản (simple case mapping)** và **ánh xạ đầy đủ (full case mapping)**. Ở ánh xạ đơn giản, một code point thường được ánh xạ sang tối đa một code point tương ứng. Ánh xạ đầy đủ có thể tạo ra **dãy gồm nhiều code point**, và một số quy tắc còn dựa vào locale hoặc các ký tự xung quanh.

Các phương thức xử lý toàn chuỗi `String.toUpperCase(Locale)` và `String.toLowerCase(Locale)` có thể áp dụng ánh xạ đầy đủ. Vì vậy không nên hình dung kết quả luôn được tạo bằng cách duyệt từng `char` và thay một-một.

Một trường hợp dễ thấy là chữ **sharp s** (`ß`, U+00DF) của tiếng Đức:

```text
"Straße"                  : 6 UTF-16 code unit
"Straße".toUpperCase(ROOT): "STRASSE", 7 UTF-16 code unit
                                 ^^
                             ß -> SS
```

Lưu ý chữ hoa Unicode `ẞ` (U+1E9E) cũng tồn tại. Điều đó không làm thay đổi kết quả cụ thể của cách chuyển `"ß".toUpperCase(Locale.ROOT)` trong ví dụ trên: Java dùng phép ánh xạ chuỗi thành `"SS"`. Một ứng dụng có quy tắc ngôn ngữ riêng cần xác định yêu cầu trước khi áp dụng phép biến đổi này.

### Ví dụ 1: quan sát số lượng code unit trước và sau

Tạo tệp `UppercaseExpansionDemo.java`:

```java
import java.util.Locale;

public class UppercaseExpansionDemo {
    public static void main(String[] args) {
        String original = "Straße";
        String upper = original.toUpperCase(Locale.ROOT);

        System.out.println(original);
        System.out.println(upper);
        System.out.println(original.length());
        System.out.println(upper.length());
        System.out.println(original.codePointCount(0, original.length()));
        System.out.println(upper.codePointCount(0, upper.length()));
        System.out.println("ß".toUpperCase(Locale.ROOT));
    }
}
```

Biên dịch với UTF-8 và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 UppercaseExpansionDemo.java
java UppercaseExpansionDemo
```

Kết quả:

```text
Straße
STRASSE
6
7
6
7
SS
```

Trong ví dụ này, mỗi chữ của chuỗi gốc được biểu diễn bằng một UTF-16 code unit. Phép viết hoa thay `ß` bằng hai code point `S`, khiến cả số code unit và số code point tăng từ 6 lên 7. Kết quả `String` mới không sửa nội dung `original`.

## 3. Đổi sang chữ thường cũng có thể làm chuỗi dài hơn

Không chỉ `toUpperCase` mới có thể mở rộng độ dài. Chữ Latin hoa có dấu chấm phía trên `İ` (U+0130, *LATIN CAPITAL LETTER I WITH DOT ABOVE*) là ví dụ điển hình.

Trong ánh xạ không đặc thù ngôn ngữ của `Locale.ROOT`:

```text
U+0130 (İ) -> U+0069 (i) + U+0307 (COMBINING DOT ABOVE)
```

Chuỗi trước có **một** UTF-16 code unit; chuỗi kết quả có **hai** UTF-16 code unit. Trên màn hình, `i` cộng dấu kết hợp có thể trông gần giống một chữ thường có chấm, nhưng hai biểu diễn Unicode không nhất thiết có cùng số code point.

### Ví dụ 2: xác minh bằng code point thay vì chỉ nhìn chữ

Tạo tệp `LowercaseExpansionDemo.java`:

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class LowercaseExpansionDemo {
    static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        String original = "\u0130";
        String lower = original.toLowerCase(Locale.ROOT);

        System.out.println(original.length());
        System.out.println(lower.length());
        System.out.println(codePoints(original));
        System.out.println(codePoints(lower));
        System.out.println(original.equals(lower));
    }
}
```

```bash
javac -encoding UTF-8 LowercaseExpansionDemo.java
java LowercaseExpansionDemo
```

Kết quả:

```text
1
2
U+0130
U+0069, U+0307
false
```

Dùng `codePoints()` giúp quan sát chính xác dữ liệu, tránh nhầm lẫn do font hoặc cách trình bày dấu kết hợp. `String.equals` trả về `false` vì hai chuỗi có dãy code unit khác nhau; đương nhiên đổi hoa–thường không phải là thao tác giữ nguyên nội dung.

## 4. `Locale` có thể quyết định kết quả và độ dài

Các quy tắc viết hoa/viết thường phụ thuộc ngôn ngữ. Tiếng Thổ Nhĩ Kỳ là ví dụ kinh điển với bốn ký tự liên quan:

- `I`: Latin hoa I không có chấm.
- `i`: Latin thường i có chấm.
- `İ`: Latin hoa I có chấm.
- `ı`: Latin thường i không có chấm.

Trong tiếng Thổ Nhĩ Kỳ, `I` thường đổi thành `ı`, còn `İ` đổi thành `i`. Với `Locale.ROOT`, quy tắc Unicode mặc định của `İ` có thể cho `i` + dấu kết hợp, nên độ dài khác so với cách đổi theo locale Thổ Nhĩ Kỳ.

### Ví dụ 3: cùng đầu vào, khác locale

Tạo tệp `LocaleCaseMappingDemo.java`:

```java
import java.util.Locale;

public class LocaleCaseMappingDemo {
    public static void main(String[] args) {
        Locale turkish = Locale.forLanguageTag("tr");
        String capitalDottedI = "\u0130";

        String rootLower = capitalDottedI.toLowerCase(Locale.ROOT);
        String trLower = capitalDottedI.toLowerCase(turkish);

        System.out.println(rootLower.length());
        System.out.println(trLower.length());
        System.out.println("I".toLowerCase(Locale.ROOT).equals("i"));
        System.out.println("I".toLowerCase(turkish).equals("\u0131"));
        System.out.println("title".toUpperCase(Locale.ROOT));
        System.out.println("title".toUpperCase(turkish)
                .codePoints()
                .mapToObj(cp -> String.format("%04X", cp))
                .toList());
    }
}
```

```bash
javac -encoding UTF-8 LocaleCaseMappingDemo.java
java LocaleCaseMappingDemo
```

Kết quả:

```text
2
1
true
true
TITLE
[0054, 0130, 0054, 004C, 0045]
```

`Locale.ROOT` là lựa chọn có chủ đích cho những quy tắc độc lập với ngôn ngữ người dùng (ví dụ một số mã khóa nội bộ được thiết kế như vậy). Khi xử lý **ngôn ngữ tự nhiên**, phải chọn locale phù hợp với dữ liệu. Không có một locale nào «đúng» cho mọi văn bản và mọi yêu cầu.

Hai overload không truyền locale là:

```java
text.toUpperCase()
text.toLowerCase()
```

Chúng sử dụng locale mặc định của môi trường theo hợp đồng `String`. Bởi vậy chương trình có thể cho kết quả khác nếu locale mặc định thay đổi. Nếu đầu ra cần lặp lại ổn định giữa máy chủ và môi trường CI, hãy **truyền `Locale` tường minh** thay vì phụ thuộc cấu hình của hệ thống.

## 5. Bối cảnh xung quanh ký tự cũng ảnh hưởng tới chuyển đổi

Ánh xạ Unicode không chỉ là bảng tra một ký tự đầu vào sang một ký tự đầu ra. Một số phép viết thường phải xem **ngữ cảnh trong từ**. Chẳng hạn chữ hoa Sigma của tiếng Hy Lạp (Σ, U+03A3) có thể chuyển sang sigma thường chuẩn (σ, U+03C3) hoặc sigma thường ở cuối từ (ς, U+03C2), tùy vị trí.

Ví dụ khái niệm:

```java
String word = "\u039F\u03A3"; // Hai chữ hoa Hy Lạp.
String lower = word.toLowerCase(java.util.Locale.ROOT);
```

Kết quả gồm các code point U+03BF (ο) và U+03C2 (ς); chữ sigma cuối nhận dạng phù hợp ngữ cảnh. Đây là **đoạn minh họa**, chưa có `main`. Dù ví dụ này không đổi độ dài, nó chứng minh rằng giải thuật chuyển chữ hoa/thường không thể luôn được thay thế bằng thao tác độc lập trên từng `char`.

Vì thế, tránh viết vòng lặp tự động `Character.toLowerCase(text.charAt(i))` khi bạn cần **toàn bộ phép chuyển đổi Unicode của chuỗi**: cách xử lý từng code unit vừa bỏ lỡ ánh xạ nhiều code point, vừa không biết ngữ cảnh toàn chuỗi.

## 6. `Character.toUpperCase(char)` không tương đương `String.toUpperCase(Locale)`

`Character.toUpperCase(char)` nhận một `char` và trả về một `char`. Kiểu trả về này chỉ chứa được **một UTF-16 code unit**, nên không thể trả nguyên dãy hai chữ `"SS"` cho đầu vào `'ß'`. Các overload `Character.toUpperCase(int)` có thể làm việc với code point nhưng vẫn trả một giá trị `int` duy nhất, không biểu diễn được ánh xạ chuỗi dài tùy ý.

`String.toUpperCase(Locale)` có quyền tạo kết quả dài hơn để biểu diễn ánh xạ đầy đủ.

### Ví dụ 4: thay từng `char` có thể cho kết quả khác

Tạo tệp `CharacterVsStringDemo.java`:

```java
import java.util.Locale;

public class CharacterVsStringDemo {
    public static void main(String[] args) {
        char sharpS = '\u00DF';

        char charMapped = Character.toUpperCase(sharpS);
        String stringMapped = String.valueOf(sharpS).toUpperCase(Locale.ROOT);

        System.out.println(charMapped == sharpS);
        System.out.println(stringMapped);
        System.out.println(stringMapped.length());

        String text = "Straße";
        StringBuilder naive = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            naive.append(Character.toUpperCase(text.charAt(i)));
        }

        System.out.println(naive);
        System.out.println(text.toUpperCase(Locale.ROOT));
    }
}
```

```bash
javac -encoding UTF-8 CharacterVsStringDemo.java
java CharacterVsStringDemo
```

Kết quả:

```text
true
SS
2
STRAßE
STRASSE
```

Trong Java 17+, phép ánh xạ `Character.toUpperCase('ß')` không thể mở rộng thành hai ký tự và giữ nguyên code unit này, còn `String.toUpperCase(Locale.ROOT)` có thể mở rộng thành `SS`.

Khi yêu cầu chuyển đổi văn bản hoàn chỉnh, hãy dùng API của `String` với locale phù hợp. `Character` thích hợp cho những thuật toán cố ý thao tác trên một code point hoặc code unit, sau khi đã hiểu giới hạn của phép ánh xạ.

## 7. Thay đổi độ dài khiến chỉ số cũ không còn đáng tin

Trong Java, `substring`, `charAt`, `indexOf` và `lastIndexOf` đều sử dụng chỉ số UTF-16 trong **chuỗi đang được thao tác**. Nếu đổi hoa–thường tạo chuỗi dài hơn hoặc ngắn hơn, vị trí ký tự ở kết quả có thể dịch sang trái hoặc sang phải.

Xét:

```text
Trước : S t r a ß e
Index : 0 1 2 3 4 5

Sau   : S T R A S S E
Index : 0 1 2 3 4 5 6
```

Chữ `e` ở vị trí `5` trước khi viết hoa; sau khi `ß` thành `SS`, chữ `E` ở vị trí `6`. **Không nên lưu vị trí trong bản gốc rồi dùng nó để cắt hoặc truy cập bản đã đổi hoa–thường.**

### Ví dụ 5: lỗi dùng chỉ số trước chuyển đổi

Tạo tệp `CaseMappingIndexDemo.java`:

```java
import java.util.Locale;

public class CaseMappingIndexDemo {
    public static void main(String[] args) {
        String original = "Straße";
        int oldE = original.indexOf('e');

        String upper = original.toUpperCase(Locale.ROOT);

        System.out.println(oldE);
        System.out.println(upper.charAt(oldE));
        System.out.println(upper.indexOf('E'));
        System.out.println(upper.substring(upper.indexOf('E')));
    }
}
```

```bash
javac -encoding UTF-8 CaseMappingIndexDemo.java
java CaseMappingIndexDemo
```

Kết quả:

```text
5
S
6
E
```

Chữ ở vị trí 5 sau chuyển đổi là chữ `S` thứ hai trong `SS`, không còn là chữ `E`. Nếu dùng chỉ số cũ để cắt chuỗi mới, kết quả sai dù chương trình không ném ngoại lệ.

**Cách an toàn hơn:** tính lại vị trí dựa trên **chuỗi sau biến đổi** hoặc xử lý/tách dữ liệu trước khi biến đổi nếu ranh giới thực sự thuộc chuỗi gốc. Nếu phải giữ ánh xạ vị trí hai phía (ví dụ tô sáng kết quả tìm kiếm trên văn bản đã chuẩn hóa), cần thiết kế cơ chế *offset mapping* tường minh. Không thể chỉ cộng trừ một số cố định trong trường hợp tổng quát.

## 8. `String` vẫn bất biến dù độ dài kết quả thay đổi

`String.toUpperCase(...)` và `String.toLowerCase(...)` không sửa nội dung `String` nguồn. Chúng trả về kết quả chuyển đổi. Khi biến đổi không làm thay đổi nội dung, implementation có thể trả về chính đối tượng ban đầu; đừng dựa vào identity của kết quả trong logic nghiệp vụ.

```java
String source = "Straße";
String alias = source;
String changed = source.toUpperCase(java.util.Locale.ROOT);

// source và alias vẫn có nội dung "Straße".
// changed có nội dung "STRASSE".
```

Đây là đoạn minh họa, không phải lớp có `main`. Tính bất biến giải thích vì sao có thể giữ cả hai phiên bản trước/sau; nó **không** bảo đảm rằng kết quả có cùng `length()`.

Khi cần biết độ dài để cấp phát vùng chứa, giới hạn trường dữ liệu, kiểm tra UI hoặc tính chỉ số, hãy **tính trên chuỗi kết quả thật**:

```java
String normalizedCase = source.toUpperCase(java.util.Locale.ROOT);
int finalLength = normalizedCase.length();
```

Không cấp phát sẵn mảng ký tự với độ dài nguồn rồi mặc định kết quả chuyển đổi vừa khít. Trong nhiều trường hợp văn bản quốc tế, giả định đó sai.

## 9. Không đồng nhất đổi hoa–thường với chuẩn hóa Unicode

Hai khái niệm thường xuất hiện cạnh nhau nhưng giải quyết những vấn đề khác nhau:

- **Case conversion:** viết hoa/viết thường theo Unicode và locale, có thể thay đổi số code point.
- **Unicode normalization:** đưa các dãy code point tương đương về một dạng chuẩn như NFC hoặc NFD (theo quy tắc tương đương chuẩn tắc), có thể thay đổi số code point và code unit.
- **Case-insensitive comparison / case folding:** chính sách so sánh hoặc đối chiếu chữ không phân biệt hoa thường, có quy tắc riêng, không đơn giản là bảo đảm một phép `toLowerCase` cho mọi ngôn ngữ.

Ví dụ `é` có thể được biểu diễn bằng một code point U+00E9, hoặc bằng `e` (U+0065) kết hợp dấu sắc U+0301. Chúng có thể trông giống nhau nhưng không bằng nhau theo `String.equals` trước khi chuẩn hóa:

### Ví dụ 6: chuẩn hóa là bước riêng

Tạo `UnicodeNormalizationDemo.java`:

```java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(composed.length());
        System.out.println(decomposed.length());
        System.out.println(composed.equals(decomposed));

        String fixed = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println(composed.equals(fixed));
        System.out.println(fixed.length());
    }
}
```

```bash
javac UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

Kết quả:

```text
1
2
false
true
1
```

Ví dụ này nói về **biểu diễn Unicode**, không phải một tình huống chuyển hoa–thường. Nó cho thấy độ dài có thể thay đổi ở các bước xử lý văn bản khác nhau. Không dùng `Normalizer` để thay cho `toUpperCase` hoặc `toLowerCase`: mỗi thao tác có hợp đồng và mục đích riêng. Khi nghiệp vụ cần vừa chuẩn hóa vừa so sánh không phân biệt hoa thường, phải xác định rõ thứ tự và chuẩn so sánh được chấp nhận.

## 10. Đổi hoa–thường có thể làm hỏng giả định so sánh

`equalsIgnoreCase` hữu ích khi muốn so sánh hai `String` mà không phân biệt hoa/thường theo hợp đồng riêng của Java. Tuy nhiên nó **không tương đương** với mọi phép ánh xạ Unicode nhiều ký tự hoặc so sánh ngôn ngữ tự nhiên theo locale.

Ví dụ:

```java
String a = "straße";
String b = "STRASSE";

System.out.println(a.toUpperCase(java.util.Locale.ROOT));
System.out.println(a.equalsIgnoreCase(b));
```

Đoạn minh họa cho kết quả:

```text
STRASSE
false
```

Hai chuỗi có thể trở thành cùng chữ hoa theo phép biến đổi cụ thể, nhưng `equalsIgnoreCase` không được thiết kế để coi mọi mở rộng một-thành-nhiều là bằng nhau; nó cũng yêu cầu độ dài phù hợp. Dùng `equalsIgnoreCase` là quyết định theo **hợp đồng so sánh của API**, không phải một cách tổng quát để triển khai Unicode full case folding hoặc collation theo ngôn ngữ.

Nếu xử lý tìm kiếm tiếng người dùng, sắp xếp theo ngôn ngữ, tên riêng hoặc văn bản Unicode quốc tế, hãy làm rõ các yếu tố: locale, phân biệt dấu, phân biệt hoa thường, normalization, phép ánh xạ mở rộng và chính sách khớp. Có thể cần `Collator`, thư viện Unicode chuyên dụng hoặc quy tắc domain cụ thể, tùy bài toán. Không tự động coi mọi chuỗi đã `toLowerCase(Locale.ROOT)` là khóa tìm kiếm chuẩn cho mọi miền nghiệp vụ.

Đặc biệt với mã định danh nhạy cảm hoặc chính sách an toàn, một quy tắc canonicalization bất cẩn có thể làm hai giá trị riêng biệt bị coi là một, hoặc làm cùng một giá trị được nhận diện khác nhau giữa môi trường. Cần định nghĩa quy tắc một cách thống nhất ở tất cả nơi nhập, lưu và so sánh dữ liệu.

## 11. Những lỗi thường gặp

**Lỗi 1 — mặc định `upper.length() == original.length()`.** Không đúng với Unicode. `"Straße".toUpperCase(Locale.ROOT)` tăng từ 6 lên 7 UTF-16 code unit.

**Lỗi 2 — nghĩ chỉ viết hoa mới mở rộng.** `"\u0130".toLowerCase(Locale.ROOT)` biến một code point thành hai code point `i` và dấu chấm kết hợp.

**Lỗi 3 — dùng `Character.toUpperCase(char)` để thay `String.toUpperCase(Locale)`.** Hàm trả `char` đơn không thể biểu diễn ánh xạ một thành nhiều ký tự, và vòng lặp từng `char` bỏ qua bối cảnh của cả chuỗi.

**Lỗi 4 — bỏ qua locale.** Kết quả với `I`/`İ`/`ı`/`i` trong tiếng Thổ Nhĩ Kỳ khác cách xử lý chung. Truyền locale có chủ đích; không để cấu hình máy ngầm quyết định một quy tắc nghiệp vụ ổn định.

**Lỗi 5 — tin vào chỉ số cũ sau biến đổi.** Một chữ có thể mở rộng thành nhiều đơn vị, khiến các vị trí phía sau dịch chuyển. Tính lại chỉ số hoặc giữ bản đồ offset.

**Lỗi 6 — nghĩ UTF-16 length là số chữ nhìn thấy.** Một emoji ngoài BMP dùng hai code unit; chữ kết hợp dấu có thể gồm nhiều code point. Chỉ số `String` không phải chỉ số grapheme cluster.

**Lỗi 7 — cho rằng chuẩn hóa NFC chính là đổi chữ.** Normalization và case conversion là các phép xử lý riêng. Đừng thay thế lẫn nhau chỉ vì cả hai có thể thay đổi độ dài.

**Lỗi 8 — cho rằng `equalsIgnoreCase` hỗ trợ mọi quy tắc Unicode.** API này không thực hiện mọi phép mở rộng một-thành-nhiều và không phải so sánh ngôn ngữ theo locale.

**Lỗi 9 — giả định chuyển hoa–thường có thể đảo ngược.** Khi `ß` thành `SS`, chuỗi kết quả không mang thông tin để xác định chắc chắn có bao nhiêu ký tự gốc hay dạng chữ gốc. Ánh xạ không nhất thiết một-một hoặc thuận nghịch.

**Lỗi 10 — quên rằng `String` bất biến.** Đổi hoa–thường tạo giá trị kết quả, không sửa văn bản mà các tham chiếu khác đang giữ.

## 12. Câu hỏi tự kiểm tra

### Câu 1: độ dài sau chuyển chữ hoa

Cho:

```java
String word = "Straße";
String upper = word.toUpperCase(java.util.Locale.ROOT);

System.out.println(word.length());
System.out.println(upper.length());
System.out.println(upper);
```

Kết quả:

```text
6
7
STRASSE
```

Giải thích vì sao: chữ `ß` trong chuỗi gốc ánh xạ thành hai chữ `S` liên tiếp khi viết hoa.

### Câu 2: chữ İ có độ dài ra sao?

Cho:

```java
String s = "\u0130";
String lowerRoot = s.toLowerCase(java.util.Locale.ROOT);
String lowerTr = s.toLowerCase(java.util.Locale.forLanguageTag("tr"));

System.out.println(lowerRoot.length());
System.out.println(lowerTr.length());
```

Kết quả:

```text
2
1
```

`Locale.ROOT` tạo `i` + combining dot, còn quy tắc tiếng Thổ Nhĩ Kỳ tạo `i` đơn.

### Câu 3: có dùng lại chỉ số cũ được không?

Nếu `original = "Straße"` và `upper = original.toUpperCase(Locale.ROOT)`, chỉ số của `e` gốc là 5. Vị trí của `E` trong kết quả là **6**. Vì vậy, `upper.charAt(5)` trả `'S'`, không phải `'E'`.

### Câu 4: xử lý chuỗi nhiều ngôn ngữ

Một ứng dụng lưu văn bản ở nhiều locale và cần tìm đoạn khớp trên bản đã chuyển hoa–thường. Nên làm gì?

**Hướng giải:** chọn quy tắc locale/canonicalization phù hợp, biến đổi dữ liệu theo hợp đồng nhất quán, tính chỉ số trên **bản đã biến đổi**, và nếu phải tô sáng trên bản gốc thì cần ánh xạ offset tường minh. Không dùng chỉ số hoặc độ dài cũ để suy ra vị trí mới.

## Kết luận

**Đổi hoa–thường trong Java là phép biến đổi Unicode, không đơn giản là thay từng `char` bằng một `char` khác.** `String.toUpperCase(Locale)` và `String.toLowerCase(Locale)` có thể mở rộng một ký tự thành nhiều code point; kết quả còn có thể phụ thuộc vào locale và ngữ cảnh. Vì thế, hãy tính `length()` và các chỉ số trên chính chuỗi kết quả, chọn locale tường minh, phân biệt case conversion với Unicode normalization và không giả định phép chuyển đổi là một-một hoặc đảo ngược được.