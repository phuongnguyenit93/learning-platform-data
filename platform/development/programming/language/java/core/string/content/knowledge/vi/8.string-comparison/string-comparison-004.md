# `String.equalsIgnoreCase()` và giới hạn của so sánh không phụ thuộc `Locale`

## 1. Mục tiêu

`String.equalsIgnoreCase(String anotherString)` so sánh **nội dung hai chuỗi** mà bỏ qua một số khác biệt chữ hoa/chữ thường theo quy tắc Unicode được Java sử dụng, **không dựa vào ngôn ngữ/vùng địa lý (`Locale`) mặc định của JVM**.

Điều đó thuận tiện cho một số giá trị quy ước đơn giản, nhưng không có nghĩa đây là thuật toán so sánh văn bản chính xác cho mọi ngôn ngữ, mọi trường hợp Unicode, hay mọi quy tắc nghiệp vụ.

Sau bài này, bạn sẽ:
- Phân biệt `equals`, `equalsIgnoreCase` và so sánh có ý thức về `Locale`.
- Hiểu cách xử lý các trường hợp đặc biệt như chữ `I/i/İ/ı` trong tiếng Thổ Nhĩ Kỳ và chữ `ß` trong tiếng Đức.
- Biết vì sao `equalsIgnoreCase` không thay thế Unicode normalization hoặc full case folding.
- Chọn đúng kỹ thuật khi so sánh mã định danh, từ ngữ nhập bởi người dùng, và các dạng dữ liệu yêu cầu quy tắc cố định.

## 2. API và hợp đồng cơ bản

Cú pháp:

```java
boolean equal = first.equalsIgnoreCase(second);
```

Ví dụ:

```java
String left = "Java Core";

System.out.println(left.equals("java core"));           // false
System.out.println(left.equalsIgnoreCase("java core")); // true
System.out.println(left.equalsIgnoreCase("JAVA CORE")); // true
System.out.println(left.equalsIgnoreCase("Java"));      // false
```

`equals` chỉ trả về `true` khi hai chuỗi có cùng nội dung theo chuỗi giá trị UTF-16. `equalsIgnoreCase` bỏ qua sự khác biệt hoa/thường *theo quy tắc của phương thức*; nó **không bỏ qua** khoảng trắng, dấu câu, dấu tiếng Việt, khác biệt độ dài hoặc những khác biệt Unicode khác một cách tổng quát.

| Trường hợp | `equalsIgnoreCase` | Giải thích |
| --- | --- | --- |
| `"Java"` và `"jAVA"` | `true` | Các chữ cái khớp khi bỏ qua hoa/thường. |
| `"Java"` và `"Java "` | `false` | Chuỗi sau có thêm dấu cách. |
| `"cat"` và `"cats"` | `false` | Khác độ dài. |
| `"abc"` và `"abd"` | `false` | Khác ký tự, không chỉ khác hoa/thường. |
| `"a"` và `null` | `false` khi gọi `"a".equalsIgnoreCase(null)` | Đối số `null` được xử lý bằng kết quả `false`. |

**Độ dài là một ràng buộc quan trọng:** hai chuỗi chỉ có thể bằng nhau theo `equalsIgnoreCase` khi chúng có cùng số **UTF-16 code unit** (`length()`). API này không phải phép biến đổi tự động xóa dấu, chuẩn hóa ký tự, hoặc mở rộng một ký tự thành nhiều ký tự.

### Xử lý `null` đúng cách

```java
String input = null;

System.out.println("yes".equalsIgnoreCase(input)); // false

// input.equalsIgnoreCase("yes"); // NullPointerException.
```

Nên gọi trên hằng chuỗi không null nếu điều đó phù hợp bài toán. Nếu cả hai biến đều có thể null và bạn muốn `null` bằng `null` trong hợp đồng riêng, hãy viết rõ:

```java
static boolean sameIgnoringCase(String a, String b) {
    return a == null ? b == null : a.equalsIgnoreCase(b);
}
```

`Objects.equals(a, b)` không thay thế được phương thức này nếu yêu cầu **không phân biệt hoa/thường**: `Objects.equals` gọi `equals` và vẫn phân biệt hoa/thường.

## 3. “Không phụ thuộc locale” nghĩa là gì?

`Locale` biểu diễn ngữ cảnh về ngôn ngữ/vùng, ví dụ `Locale.forLanguageTag("tr")` cho tiếng Thổ Nhĩ Kỳ hoặc `Locale.forLanguageTag("en")` cho tiếng Anh. Cách chuyển hoa/thường trong ngôn ngữ tự nhiên **có thể phụ thuộc locale**.

Ngược lại, `equalsIgnoreCase`:
- Không nhận tham số `Locale`.
- Không âm thầm dựa vào `Locale.getDefault()` để quyết định hai chuỗi bằng nhau.
- Dùng các phép so sánh không phân biệt hoa/thường dựa trên thông tin Unicode và quy tắc trong Java.

Vì vậy, **ổn định theo `Locale` không đồng nghĩa đúng theo từng ngôn ngữ**. Cùng một phép so sánh có thể trả cùng kết quả bất kể locale mặc định, nhưng kết quả đó vẫn không khớp cách người nói một ngôn ngữ cụ thể phân biệt từ ngữ.

### Trường hợp tiếng Thổ Nhĩ Kỳ: bốn dạng `I`

Trong tiếng Thổ Nhĩ Kỳ có hai cặp hoa/thường riêng:
- `I` ↔ `ı` (chữ i **không chấm**).
- `İ` ↔ `i` (chữ i **có chấm**).

Tuy nhiên, `equalsIgnoreCase` của Java có thể coi các dạng này bằng nhau theo phép ánh xạ không phụ thuộc locale:

```java
System.out.println("I".equalsIgnoreCase("i"));      // true
System.out.println("I".equalsIgnoreCase("\u0131")); // true: ı
System.out.println("\u0130".equalsIgnoreCase("i")); // true: İ
```

Đây là ví dụ quan trọng cho thấy **so sánh không phụ thuộc locale có thể gom những chữ cái mà một ngôn ngữ xem là khác nhau**.

Trong khi đó, phép chuyển chữ thường có truyền `Locale` có thể cho kết quả khác:

```java
import java.util.Locale;

Locale turkish = Locale.forLanguageTag("tr");

System.out.println("I".toLowerCase(turkish).equals("i")); // false
System.out.println("I".toLowerCase(Locale.ROOT).equals("i")); // true
```

`Locale.ROOT` là locale trung lập về ngôn ngữ, thích hợp cho nhiều cách xử lý dữ liệu theo quy ước cố định. Nhưng dùng `Locale.ROOT` để chuyển chữ thường **không làm cho việc so sánh trở thành so sánh ngôn ngữ tự nhiên của tất cả locale**, và cũng không đồng nghĩa với full Unicode case folding.

## 4. Bài toán Unicode: một chữ có thể biến thành nhiều chữ

### 4.1. Chữ `ß` của tiếng Đức

`ß` (*sharp s*, U+00DF) có một số cách xử lý biến đổi chữ hoa/thường khác các chữ Latin cơ bản. Ví dụ:

```java
import java.util.Locale;

String a = "Stra\u00DFe"; // Straße
String b = "STRASSE";

System.out.println(a.equalsIgnoreCase(b));                // false
System.out.println(a.toUpperCase(Locale.ROOT).equals(b)); // true
```

Tại sao dòng thứ nhất `false`? `"Straße"` có **6** code unit UTF-16, còn `"STRASSE"` có **7**. `equalsIgnoreCase` yêu cầu độ dài phù hợp và **không thực hiện ánh xạ một ký tự thành hai chữ "SS" để làm bằng nhau**.

Dòng thứ hai `true` vì phép chuyển **toàn chuỗi** bằng `toUpperCase(Locale.ROOT)` có thể thực hiện ánh xạ **một thành nhiều** (ở đây `ß` → `SS`). Điều đó cho thấy kết quả của `equalsIgnoreCase` và của cách “chuyển cả hai chuỗi sang hoa/thường rồi so sánh” không nhất thiết giống nhau.

Không nên suy ra rằng `toUpperCase(Locale.ROOT)` là giải pháp tổng quát cho mọi chuỗi Unicode: biến đổi cả chuỗi có thể phụ thuộc ngữ cảnh, độ dài có thể thay đổi, và một hệ thống cần so sánh độc lập với ngôn ngữ thường cần một định nghĩa **case folding/normalization** cụ thể.

### 4.2. Greek sigma và các ánh xạ khác

`Σ` (sigma hoa), `σ` (sigma thường), `ς` (sigma cuối từ) là ví dụ các dạng chữ liên quan về hoa/thường:

```java
System.out.println("\u03A3".equalsIgnoreCase("\u03C3")); // true
System.out.println("\u03A3".equalsIgnoreCase("\u03C2")); // true
```

Cách coi các ký tự bằng nhau phục vụ phép so sánh Unicode không phụ thuộc ngôn ngữ; nó không tự biết vị trí từ hoặc quy tắc chính tả của từng ngôn ngữ.

Với chuỗi Unicode tổng quát, đừng định nghĩa thuật toán của `equalsIgnoreCase` đơn giản là “gọi `toLowerCase()` trên cả hai chuỗi”. Chúng là **các API khác nhau**, với các quy tắc và khả năng biến đổi độ dài khác nhau.

## 5. Unicode normalization: chữ nhìn giống nhau vẫn có thể khác

Unicode có thể biểu diễn cùng một dạng chữ bằng các chuỗi code point khác nhau. Ví dụ:
- `"\u00E9"` là ký tự `é` được mã hóa bởi **một** code point U+00E9.
- `"e\u0301"` là chữ `e` U+0065 theo sau bởi dấu sắc kết hợp U+0301, gồm **hai** code point.

Hai chuỗi có thể nhìn giống nhau nhưng dữ liệu thực khác nhau:

```java
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equalsIgnoreCase(decomposed)); // false
System.out.println(composed.length());                     // 1
System.out.println(decomposed.length());                   // 2
```

`equalsIgnoreCase` **không tự chuẩn hóa Unicode**. Nếu hợp đồng nghiệp vụ cho phép coi hai dạng *canonically equivalent* là cùng văn bản, chuẩn hóa trước khi so sánh:

```java
import java.text.Normalizer;

String leftNfc = Normalizer.normalize(composed, Normalizer.Form.NFC);
String rightNfc = Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(leftNfc.equalsIgnoreCase(rightNfc)); // true
```

`Normalizer.Form.NFC` giúp chuẩn hóa các biểu diễn tương đương về dạng dựng sẵn khi có thể. Nhưng **NFC chỉ giải quyết canonical equivalence**, không phải mọi sự tương đương về hoa/thường, ngôn ngữ, dấu câu hay ký tự nhìn tương tự nhau. Cần quyết định rõ chuẩn hóa đầu vào ở mức nào và có được phép biến đổi dữ liệu gốc không.

## 6. Chương trình Java 17+ chạy độc lập

Lưu thành file `EqualsIgnoreCaseDemo.java`:

```java
import java.text.Normalizer;
import java.util.Locale;

public class EqualsIgnoreCaseDemo {
    public static void main(String[] args) {
        System.out.println("basic = "
                + "Java".equalsIgnoreCase("jAVA"));
        System.out.println("space = "
                + "Java".equalsIgnoreCase("Java "));
        System.out.println("null argument = "
                + "Java".equalsIgnoreCase(null));

        // Hai cặp chữ I/i khác nhau trong tiếng Thổ Nhĩ Kỳ.
        System.out.println("I vs i = "
                + "I".equalsIgnoreCase("i"));
        System.out.println("I vs dotless = "
                + "I".equalsIgnoreCase("\u0131"));
        System.out.println("dotted vs i = "
                + "\u0130".equalsIgnoreCase("i"));

        Locale tr = Locale.forLanguageTag("tr");
        System.out.println("Turkish lowercase I is i = "
                + "I".toLowerCase(tr).equals("i"));
        System.out.println("ROOT lowercase I is i = "
                + "I".toLowerCase(Locale.ROOT).equals("i"));

        String german = "Stra\u00DFe";
        System.out.println("sharp-s ignore-case = "
                + german.equalsIgnoreCase("STRASSE"));
        System.out.println("sharp-s upper ROOT = "
                + german.toUpperCase(Locale.ROOT).equals("STRASSE"));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("before NFC = "
                + composed.equalsIgnoreCase(decomposed));
        System.out.println("after NFC = "
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                  .equalsIgnoreCase(
                      Normalizer.normalize(
                          decomposed, Normalizer.Form.NFC)));

        System.out.println("Greek sigma = "
                + "\u03A3".equalsIgnoreCase("\u03C2"));
    }
}
```

Biên dịch và chạy (Java 17 trở lên):

```bash
javac -encoding UTF-8 EqualsIgnoreCaseDemo.java
java EqualsIgnoreCaseDemo
```

Kết quả:

```text
basic = true
space = false
null argument = false
I vs i = true
I vs dotless = true
dotted vs i = true
Turkish lowercase I is i = false
ROOT lowercase I is i = true
sharp-s ignore-case = false
sharp-s upper ROOT = true
before NFC = false
after NFC = true
Greek sigma = true
```

**Diễn giải:** cùng một phương thức `equalsIgnoreCase` làm tốt việc bỏ qua khác biệt hoa/thường đơn giản (`Java`/`jAVA`), nhưng không tự biết quy tắc phân biệt hai chữ `I` trong tiếng Thổ Nhĩ Kỳ, không mở rộng `ß` thành `SS`, cũng không chuyển hai dạng biểu diễn `é` về cùng một chuẩn Unicode. Mỗi khác biệt đó cần được giải quyết theo **quy tắc dữ liệu/ngôn ngữ** cụ thể.

## 7. Khi nào chọn `equalsIgnoreCase`, `Locale.ROOT` hay `Collator`?

Không có một thuật toán “bỏ qua hoa/thường” phù hợp cho mọi dữ liệu. Trước tiên hãy xác định bạn muốn so sánh **mã giao thức**, **dữ liệu định danh ứng dụng**, hay **văn bản ngôn ngữ tự nhiên**.

| Nhu cầu | Cách tiếp cận | Lưu ý |
| --- | --- | --- |
| So sánh giá trị lựa chọn đơn giản như `"yes"`, `"YES"` | `"yes".equalsIgnoreCase(input)` | Đủ khi hợp đồng giá trị rõ ràng và tập ký tự được kiểm soát. |
| Chuẩn hóa mã ASCII theo quy ước cố định | Xác thực alphabet hợp lệ, rồi dùng phép so sánh phù hợp; có thể chuyển bằng `Locale.ROOT` nếu quy ước yêu cầu | Kiểm tra đúng cú pháp trước; không tự chấp nhận mọi chữ Unicode trông giống ASCII. |
| So sánh văn bản theo ngôn ngữ người dùng | `java.text.Collator` theo `Locale` phù hợp | Quy tắc so sánh, dấu và chữ hoa/thường khác nhau theo locale/cấu hình. |
| So sánh Unicode canonical-equivalent | Chuẩn hóa `Normalizer` rồi so sánh theo chính sách đã chọn | NFC **không** phải full case folding. |
| Định danh Unicode không phân biệt hoa/thường theo một tiêu chuẩn nghiệp vụ | Định nghĩa rõ chuẩn hóa, case folding, phiên bản Unicode và xử lý trường hợp đặc biệt | `equalsIgnoreCase` không mặc nhiên tương đương Unicode full case folding. |
| So sánh mật khẩu/token mật được cấp chính xác | Thực hiện theo hợp đồng bảo mật của hệ thống | Không mặc định bỏ qua hoa/thường; với dữ liệu bí mật còn có yêu cầu riêng về so sánh an toàn. |

### `Collator` cho ngôn ngữ tự nhiên

Khi bạn cần so sánh theo quy tắc tiếng Thổ Nhĩ Kỳ, tiếng Việt hoặc ngôn ngữ khác, hãy dùng API collation được cấu hình đúng:

```java
import java.text.Collator;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("tr");
Collator collator = Collator.getInstance(locale);

// Mức SECONDARY thường giữ phân biệt dấu
// và giảm phân biệt chữ hoa/thường, tùy bộ quy tắc collation.
collator.setStrength(Collator.SECONDARY);

boolean same = collator.compare("I", "\u0131") == 0;
```

Đây là đoạn minh họa đặt trong một phương thức Java. `Collator` có nhiều mức độ so sánh (`PRIMARY`, `SECONDARY`, `TERTIARY`, …); lựa chọn mức độ quyết định việc phân biệt dấu, hoa/thường và các biến thể khác theo locale/provider. Đừng đặt `Collator.PRIMARY` rồi mặc nhiên giả định mọi ngôn ngữ sẽ chỉ bỏ qua hoa/thường mà vẫn giữ mọi khác biệt khác.

`Collator` không nên dùng như một bộ định nghĩa chuẩn tắc cho các mã định danh mang tính giao thức. Quy tắc collation có thể chịu ảnh hưởng của locale, provider và dữ liệu ngôn ngữ trong runtime. Nếu cần tính ổn định xuyên các hệ thống/phiên bản, phải quy định, kiểm thử và quản lý phiên bản thuật toán so sánh.

### Dùng `Locale.ROOT` đúng bối cảnh

`toLowerCase(Locale.ROOT)` hoặc `toUpperCase(Locale.ROOT)` hữu ích khi cần một phép biến đổi chữ **không phụ thuộc locale mặc định**, ví dụ xử lý một số khóa cấu hình theo quy ước đã chốt.

Tuy nhiên, hai điểm cần nhớ:

1. Chuyển hoa/thường toàn chuỗi có thể thay đổi **độ dài** hoặc phụ thuộc ngữ cảnh Unicode, nên không tương đương `equalsIgnoreCase`.
2. Một ánh xạ hoa/thường trung lập không phải bộ quy tắc so sánh người dùng cho mọi ngôn ngữ, và cũng không đảm bảo nhận diện mọi cặp mà Unicode full case folding xem là tương đương.

Đặc biệt, tránh `text.toLowerCase()` không truyền tham số khi thuật toán yêu cầu kết quả bất biến theo máy hoặc người dùng: overload không tham số sử dụng **locale mặc định**, nên kết quả có thể thay đổi theo môi trường chạy.

## 8. Lưu ý về Unicode code point và ký tự hiển thị

`String` trong Java sử dụng chỉ số dựa trên UTF-16 code unit, và `length()` trả về số code unit. Một ký tự ngoài BMP có thể chiếm hai `char`; một “ký tự người dùng nhìn thấy” (grapheme cluster) có thể chứa nhiều code point.

`equalsIgnoreCase` so sánh nội dung theo quy tắc case-insensitive được Java định nghĩa, nhưng không tự:
- Phân đoạn chuỗi thành grapheme cluster theo trải nghiệm người dùng.
- Bỏ dấu tiếng Việt hay dấu kết hợp.
- Đồng nhất ký tự nhìn tương tự nhau nhưng có code point khác nhau (ví dụ chữ Latin và chữ Cyrillic trông gần giống).
- Gộp mọi cặp chuỗi khác độ dài bằng phép case folding đầy đủ.
- Thực hiện Unicode normalization trước khi so sánh.

Vì vậy, với tìm kiếm, xác thực tên hiển thị hoặc phân nhóm văn bản quốc tế, cần xác định **đơn vị văn bản và quy tắc tương đương** trước khi viết code. Hai chuỗi nhìn giống nhau không chắc bằng nhau theo Java; hai chữ mà Java coi bằng nhau khi bỏ qua hoa/thường chưa chắc tương đương trong một ngôn ngữ.

## 9. Những lỗi thường gặp

**Lỗi 1 — Xem `equalsIgnoreCase` như so sánh theo locale người dùng.**

`"I".equalsIgnoreCase("i")` là `true` bất kể đang phục vụ giao diện tiếng Anh hay tiếng Thổ Nhĩ Kỳ. Nếu nghiệp vụ yêu cầu khác nhau theo ngôn ngữ, phải dùng cơ chế so sánh có ý thức về locale.

**Lỗi 2 — Gọi `toLowerCase()` không truyền `Locale` để chuẩn hóa mã máy.**

```java
String key = input.toLowerCase(); // Phụ thuộc default Locale.
```

Nếu dữ liệu có hợp đồng trung lập và đúng quy tắc chuyển chữ toàn chuỗi, hãy truyền `Locale.ROOT` tường minh, đồng thời xác nhận domain ký tự và hậu quả ánh xạ Unicode. Nếu mã chỉ được phép ASCII, xác thực ASCII trước.

**Lỗi 3 — Nghĩ `equalsIgnoreCase` sẽ xử lý `ß` bằng `SS`.**

`"Straße".equalsIgnoreCase("STRASSE")` cho kết quả `false` do độ dài khác nhau. Case conversion toàn chuỗi có thể có kết quả khác; không nên dùng thay thế mà không xác định semantics.

**Lỗi 4 — Bỏ qua Unicode normalization.**

`"\u00E9"` và `"e\u0301"` không bằng nhau theo `equalsIgnoreCase` vì biểu diễn khác nhau. Nếu muốn canonical equivalence, cần chuẩn hóa có chủ đích (ví dụ NFC) cho **cả hai** chuỗi.

**Lỗi 5 — Nhầm `null` với chuỗi rỗng hoặc bỏ kiểm tra receiver.**

`"x".equalsIgnoreCase(null)` trả `false`, nhưng `nullable.equalsIgnoreCase("x")` ném `NullPointerException` khi `nullable == null`. Hãy xác định chính sách null rõ ràng.

**Lỗi 6 — Dùng kết quả comparison làm khóa lâu dài mà không chuẩn hóa quy ước.**

Nếu hệ thống cho phép người dùng đặt username, mã tham chiếu, hay nhãn phân nhóm Unicode, cần quyết định một **quan hệ tương đương chuẩn** và cách lưu khóa để tránh va chạm hoặc phân biệt không nhất quán qua database, API, giao diện và phiên bản runtime. `equalsIgnoreCase` tự nó không định nghĩa quy tắc nhận diện Unicode đầy đủ cho mọi hệ thống.

## 10. Bài tập tự kiểm tra

### Bài 1

```java
System.out.println("ABC".equalsIgnoreCase("abc"));
System.out.println("abc".equalsIgnoreCase("abc "));
```

**Đáp án:** `true` rồi `false`. Lời gọi thứ hai không bằng nhau vì có thêm khoảng trắng, không chỉ khác chữ hoa/thường.

### Bài 2

```java
System.out.println("I".equalsIgnoreCase("\u0131"));
System.out.println("I".toLowerCase(
        java.util.Locale.forLanguageTag("tr")).equals("i"));
```

**Đáp án:** `true` rồi `false`. Phương thức thứ nhất dùng quy tắc không phụ thuộc locale; phép chuyển chữ thường thứ hai dùng quy tắc của locale Thổ Nhĩ Kỳ.

### Bài 3

```java
System.out.println("Stra\u00DFe".equalsIgnoreCase("STRASSE"));
System.out.println("Stra\u00DFe".toUpperCase(
        java.util.Locale.ROOT).equals("STRASSE"));
```

**Đáp án:** `false` rồi `true`. Sự khác biệt minh họa rằng `equalsIgnoreCase` không tương đương với chuyển hoa toàn chuỗi rồi gọi `equals`.

### Bài 4

```java
String a = "\u00E9";
String b = "e\u0301";
System.out.println(a.equalsIgnoreCase(b));
```

**Đáp án:** `false`. Khác biểu diễn Unicode, muốn nhận canonical-equivalent thì chuẩn hóa theo quy tắc đã thống nhất trước khi so sánh.

### Bài 5

Một ứng dụng quốc tế muốn kiểm tra tên hiển thị theo ngôn ngữ người dùng; ứng dụng khác muốn kiểm tra tùy chọn ASCII `"ON"`/`"OFF"`. Cả hai có nên mặc định dùng cùng `equalsIgnoreCase` không?

**Đáp án:** Không. Với tùy chọn ASCII có domain và quy tắc rõ, `equalsIgnoreCase` phù hợp. Với tên hiển thị theo ngôn ngữ, cần xác định locale và mức độ collation, chuẩn hóa Unicode khi hợp đồng yêu cầu, rồi chọn API tương ứng.

## 11. Ghi nhớ

- `equalsIgnoreCase` bỏ qua hoa/thường theo quy tắc Java **không phụ thuộc `Locale`**; nó không gọi phép so sánh ngôn ngữ tự nhiên theo mặc định.
- Các chuỗi khác độ dài không bằng nhau; `ß` so với `SS` là ví dụ giới hạn của phương thức.
- `I/i/İ/ı` cho thấy phép so sánh không phụ thuộc locale có thể không phù hợp quy tắc tiếng Thổ Nhĩ Kỳ.
- Unicode normalization và case-insensitive comparison là **hai bước khác nhau**; `equalsIgnoreCase` không làm normalization.
- Chọn `Collator` cho nhu cầu so sánh theo ngôn ngữ, `Locale.ROOT` cho phép chuyển hoa/thường trung lập **khi hợp đồng dữ liệu phù hợp**, và cơ chế full case folding chuyên biệt nếu ứng dụng cần chuẩn tương đương Unicode chặt chẽ.
- Luôn xác định miền dữ liệu, chính sách null, khoảng trắng, dấu, ngôn ngữ, cách chuẩn hóa và tính ổn định giữa các hệ thống trước khi quyết định hai chuỗi “bằng nhau”.

## Tài liệu tham khảo

- [Java SE 17 — `String.equalsIgnoreCase(String)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#equalsIgnoreCase(java.lang.String))
- [Java SE 17 — `String.toLowerCase(Locale)` và `toUpperCase(Locale)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Collator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Java SE 17 — `Normalizer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Standard — `Default Case Folding` (Chapter 3)](https://www.unicode.org/versions/latest/core-spec/chapter-3/)
