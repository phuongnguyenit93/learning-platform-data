# `UNICODE_CHARACTER_CLASS` và lớp ký tự định sẵn trong Java Regex

Trong `java.util.regex`, những mẫu ngắn như `\w`, `\d` và `\s` rất tiện để nhận diện ký tự. Nhưng **mặc định chúng không bao phủ toàn bộ Unicode**. Khi xử lý tên tiếng Việt, số của hệ chữ viết khác hoặc khoảng trắng Unicode, cần hiểu chính xác `Pattern.UNICODE_CHARACTER_CLASS` thay đổi những gì. Đây là API vẫn được hỗ trợ trong Java hiện đại, bao gồm Java 17+.

## 1. Ý tưởng cốt lõi

- Một **lớp ký tự định sẵn** (predefined character class) như `\d` khớp **một ký tự** thuộc nhóm tương ứng. Thêm `+` thành `\d+` để khớp một hoặc nhiều ký tự; dùng `Matcher.matches()` để kiểm tra toàn bộ chuỗi, `Matcher.find()` để tìm một đoạn khớp.
- Nếu không bật `UNICODE_CHARACTER_CLASS` (viết tắt **UCC**), ba lớp phổ biến `\d`, `\s`, `\w` theo bộ ký tự cơ bản thiên về ASCII. Chuỗi đầu vào vẫn là Unicode; **không bật UCC không có nghĩa Java Regex không hỗ trợ Unicode**.
- Khi bật UCC, các lớp định sẵn liên quan và nhóm lớp POSIX chuyển sang cách phân loại ký tự theo thuộc tính Unicode. Đây là thay đổi về **điều kiện một ký tự có khớp hay không**, không phải chuyển đổi mã hóa hay chuẩn hóa văn bản.
- Có thể bật bằng tham số của `Pattern.compile(...)` hoặc cờ nội tuyến `(?U)`; chữ `U` viết hoa rất quan trọng.

## 2. Các lớp định sẵn thay đổi ra sao?

| Mẫu regex | Không bật UCC | Bật UCC |
| --- | --- | --- |
| `\d` | Chữ số ASCII `0`–`9` | Chữ số thập phân Unicode (`\p{IsDigit}`, thuộc nhóm `Nd`), ví dụ `3`, `١`, `३` |
| `\D` | Bất kỳ ký tự nào không thuộc `\d` mặc định | Phần bù của `\d` Unicode |
| `\w` | `[a-zA-Z_0-9]` | Ký tự mang thuộc tính Alphabetic, dấu kết hợp (`Mark`), chữ số thập phân, dấu nối thuộc `Connector_Punctuation` và `Join_Control` |
| `\W` | Phần bù của `\w` mặc định | Phần bù của `\w` Unicode |
| `\s` | Khoảng trắng ASCII quen thuộc: space, tab, LF, VT, FF, CR | Ký tự có thuộc tính Unicode `White_Space` (`\p{IsWhite_Space}`), bao gồm cả NBSP (`U+00A0`) |
| `\S` | Phần bù của `\s` mặc định | Phần bù của `\s` Unicode |

Ví dụ, `café` không khớp toàn bộ `\w+` mặc định vì ký tự `é` nằm ngoài `[a-zA-Z_0-9]`, nhưng khớp `(?U)\w+`. Tương tự, `١٢٣` (chữ số Arabic-Indic) khớp `(?U)\d+` nhưng không khớp `\d+` mặc định.

**Hai giới hạn thường bị bỏ qua:**

1. `\d` ở chế độ Unicode biểu diễn **chữ số thập phân**, không phải mọi ký tự thuộc nhóm số Unicode như phân số hay ký hiệu số La Mã. Nếu nghiệp vụ chỉ chấp nhận `0`–`9`, hãy dùng `[0-9]` rõ ràng.
2. `\w` ở chế độ Unicode **không đồng nghĩa “chỉ chữ cái”**: nó cũng có số, dấu gạch dưới, dấu kết hợp và các ký tự nối. Nó cũng không phải bộ tách từ ngôn ngữ tự nhiên hay bộ kiểm tra tên người.

Các mẫu `\h`/`\H` (khoảng trắng ngang và phần bù), `\v`/`\V` (khoảng trắng dọc và phần bù) có định nghĩa riêng và không cần UCC để trở thành các nhóm khoảng trắng chỉ ASCII. Dấu `.` có quy tắc riêng về dấu xuống dòng; muốn `.` khớp cả line terminator thì xét `Pattern.DOTALL`, không phải UCC.

## 3. Bật Unicode character classes trong Java

### Cách 1: Cờ khi biên dịch `Pattern`

```java
import java.util.regex.Pattern;

Pattern word = Pattern.compile("\\w+", Pattern.UNICODE_CHARACTER_CLASS);
boolean accepted = word.matcher("café").matches(); // true
```

### Cách 2: Cờ nội tuyến trong regex

```java
Pattern word = Pattern.compile("(?U)\\w+");
boolean accepted = word.matcher("café").matches(); // true
```

Có thể giới hạn cờ ở một nhóm bằng `(?U:...)` nếu cần phối hợp các đoạn regex với quy tắc khác nhau:

```java
Pattern mixed = Pattern.compile("[A-Z]+-(?U:\\w+)");
boolean accepted = mixed.matcher("ID-café").matches(); // true
```

**Cách viết escape:** Trong regex thực tế ta viết `\w`, `\d`, `\s`, `\p{L}`; trong *chuỗi Java* phải nhân đôi dấu gạch chéo ngược: `"\\w"`, `"\\d"`, `"\\s"`, `"\\p{L}"`. Viết `"\w"` trực tiếp vào Java string sẽ không biên dịch. Cờ `(?U)` là một phần của regex, vì vậy `"(?U)\\w+"` hợp lệ.

**Phân biệt `U` và `u`:** `(?U)` bật `UNICODE_CHARACTER_CLASS`; `(?u)` chỉ bật `UNICODE_CASE` (quy tắc gấp chữ hoa/thường theo Unicode) và **không tự biến `\w`, `\d`, `\s` thành lớp Unicode**.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu đoạn sau trong tệp `UnicodeClassDemo.java` dưới dạng UTF-8:

```java
import java.util.regex.Pattern;

public class UnicodeClassDemo {
    private static void compare(String label, String regex, String value) {
        boolean basic = Pattern.compile(regex).matcher(value).matches();
        boolean unicode = Pattern.compile(
                regex, Pattern.UNICODE_CHARACTER_CLASS
        ).matcher(value).matches();

        System.out.printf("%s: default=%s, UCC=%s%n",
                label, basic, unicode);
    }

    public static void main(String[] args) {
        compare("word", "\\w+", "café");
        compare("digits", "\\d+", "١٢٣");
        compare("space", "\\s", "\u00A0"); // NBSP: non-breaking space
        compare("alpha", "\\p{Alpha}+", "Đà");

        System.out.println("inline: " +
                Pattern.compile("(?U)\\w+").matcher("café").matches());

        System.out.println("fold: " +
                Pattern.compile(
                        "café",
                        Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CHARACTER_CLASS
                ).matcher("CAFÉ").matches());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 UnicodeClassDemo.java
java UnicodeClassDemo
```

Stdout:

```text
word: default=false, UCC=true
digits: default=false, UCC=true
space: default=false, UCC=true
alpha: default=false, UCC=true
inline: true
fold: true
```

Giải thích:

- `word`: `é` được nhận diện là ký tự từ khi bật UCC.
- `digits`: các chữ số Arabic-Indic thuộc tập số thập phân Unicode.
- `space`: NBSP là Unicode `White_Space` nhưng không thuộc `\s` mặc định.
- `alpha`: `\p{Alpha}` là một lớp POSIX chịu tác động của UCC, nên nhận `Đà`.
- `inline`: `(?U)` hoạt động tương đương việc truyền cờ khi biên dịch cho phạm vi regex tương ứng.
- `fold`: UCC **ngầm bật `UNICODE_CASE`**; khi kết hợp với `CASE_INSENSITIVE`, việc so khớp hoa/thường có nhận biết Unicode. Chỉ bật UCC mà không bật `CASE_INSENSITIVE` không khiến regex tự bỏ qua chữ hoa/thường.

Đoạn này dùng `matches()` nên đòi hỏi toàn bộ `value` khớp. Với văn bản dài, dùng `Matcher.find()` để lặp qua các đoạn khớp; đừng đổi hai phương thức cho nhau khi viết validator.

## 5. Lớp POSIX và thuộc tính Unicode tường minh

Ngoài `\w`, `\d`, `\s`, Java Regex hỗ trợ các lớp kiểu POSIX như:

| Mẫu | Ý nghĩa mặc định | Khi bật UCC |
| --- | --- | --- |
| `\p{Alpha}` | Chữ cái ASCII `[A-Za-z]` | Thuộc tính Unicode `Alphabetic` |
| `\p{Lower}` / `\p{Upper}` | Chữ thường/hoa ASCII | Thuộc tính Unicode `Lowercase` / `Uppercase` |
| `\p{Digit}` | Chữ số ASCII `[0-9]` | Chữ số thập phân Unicode |
| `\p{Alnum}` | Chữ cái hoặc chữ số ASCII | Chữ cái hoặc chữ số theo thuộc tính Unicode |
| `\p{Space}` | Nhóm khoảng trắng ASCII | Thuộc tính Unicode `White_Space` |
| `\p{ASCII}` | U+0000 đến U+007F | **Vẫn là ASCII**, không mở rộng |

Khi yêu cầu nghiệp vụ đã xác định rõ tập ký tự, có thể chọn **Unicode property tường minh** mà không cần bật UCC:

| Mẫu | Diễn giải |
| --- | --- |
| `\p{L}` | Ký tự thuộc general category `Letter` của Unicode |
| `\p{M}` | Dấu kết hợp (`Mark`), hữu ích với văn bản ở dạng decomposed |
| `\p{Nd}` | Chữ số thập phân Unicode |
| `\p{IsAlphabetic}` | Ký tự có thuộc tính nhị phân Unicode `Alphabetic` |
| `\p{IsWhite_Space}` | Ký tự có thuộc tính Unicode `White_Space` |
| `\p{sc=Latin}` hoặc `\p{IsLatin}` | Ký tự thuộc script Latin |
| `\P{L}` | Bất kỳ ký tự nào **không** thuộc nhóm Letter |

`\\p{L}` trong chuỗi Java tương ứng với regex `\p{L}`. Đừng nhầm **script** (hệ chữ viết, như Latin) với **block** (vùng mã Unicode, như `\p{InBasic_Latin}`), hoặc `\p{L}` với `\w`: chúng có tập ký tự khác nhau.

Ví dụ, nếu chỉ cần các chữ cái và dấu kết hợp, `[\p{L}\p{M}]+` thể hiện yêu cầu rõ hơn `(?U)\w+`, vì loại trừ số và dấu gạch dưới. Đó vẫn chỉ là một **điều kiện ký tự**; quy tắc tên người, số từ, khoảng trắng, dấu nối và giới hạn độ dài phải do nghiệp vụ quyết định.

## 6. Áp dụng vào xử lý văn bản thực tế

### 6.1. Tách theo khoảng trắng Unicode

Đoạn mã minh họa trong một phương thức:

```java
String text = "một\u00A0hai\tba";
String[] tokens = text.split("(?U)\\s+");
// tokens gồm "một", "hai", "ba"
```

Dùng `(?U)\s+` khi nguồn dữ liệu có NBSP hoặc khoảng trắng Unicode khác. Nếu hợp đồng dữ liệu chỉ có tab, CR, LF, space ASCII, `\s+` mặc định có thể là lựa chọn có chủ đích. `\s` với UCC không nhất thiết có tập ký tự trùng `Character.isWhitespace()` hoặc `String.strip()`; các API sử dụng định nghĩa khoảng trắng khác nhau.

### 6.2. Tìm token Unicode

```java
Pattern tokens = Pattern.compile("(?U)\\w+");
var matcher = tokens.matcher("Tên: café, mã: ١٢٣");
while (matcher.find()) {
    System.out.println(matcher.group());
}
```

Đây là ví dụ dùng `find()` để lấy các đoạn khớp. `\w+` không nhận khoảng trắng hay dấu câu làm phần của token, nhưng vẫn có thể nhận số, `_` và dấu kết hợp. Không dùng kết quả này làm thuật toán phân đoạn từ tiếng Việt hoàn chỉnh. Nếu cần một tập ký tự cụ thể, dùng các Unicode property và quy tắc ranh giới được thiết kế cho yêu cầu đó.

### 6.3. Validator: chọn đúng hợp đồng đầu vào

```java
Pattern asciiCode = Pattern.compile("[A-Za-z][A-Za-z0-9_]*");
Pattern asciiDigits = Pattern.compile("[0-9]+");
Pattern unicodeLettersAndMarks = Pattern.compile("[\\p{L}\\p{M}]+");
```

- Mã hệ thống bắt buộc ASCII: dùng tập ASCII tường minh, không phụ thuộc việc nơi gọi đã bật UCC.
- Số nhập chỉ cho phép `0`–`9`: dùng `[0-9]+`, kể cả khi các regex khác xử lý Unicode.
- Văn bản cần chữ cái đa ngôn ngữ: dùng `\p{L}` và cân nhắc `\p{M}` nếu có dấu kết hợp. Không suy diễn rằng “Unicode-aware” đồng nghĩa mọi chuỗi đều an toàn hoặc hợp lệ cho tên tài khoản.

## 7. Những điểm UCC không giải quyết

**Chuẩn hóa Unicode.** Cùng một chữ nhìn giống nhau có thể có nhiều biểu diễn: `é` dạng NFC (U+00E9) và `e` + dấu sắc kết hợp (U+0065 U+0301). Một regex chứa ký tự `é` literal không mặc nhiên coi hai chuỗi là tương đương chỉ vì bật UCC. Khi cần so khớp theo một dạng chuẩn, chuẩn hóa dữ liệu nhất quán trước khi kiểm tra:

```java
import java.text.Normalizer;
import java.util.regex.Pattern;

// Các lệnh sau minh họa trong thân một phương thức:
String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
boolean hasOnlyLettersAndMarks = Pattern.compile("[\\p{L}\\p{M}]+")
        .matcher(normalized).matches();
```

**Chữ hoa/thường.** `UNICODE_CHARACTER_CLASS` ngầm kích hoạt `UNICODE_CASE`, nhưng so khớp không phân biệt hoa/thường còn cần `CASE_INSENSITIVE`. `UNICODE_CASE` không tự chuẩn hóa chuỗi và không tương đương quy tắc biến đổi chữ hoa/thường đặc thù của từng ngôn ngữ/locale.

**Ranh giới ký tự và từ.** `\b` là **word boundary** có độ rộng bằng 0; nó không phải tập ký tự giống `\w`. Với từ nhiều dấu kết hợp, emoji hoặc nhiều hệ chữ viết, cần kiểm thử ranh giới trên JDK đang triển khai. Việc `\w+` khớp một chuỗi không chứng minh chuỗi đó là một từ ngữ nghĩa. Nếu bài toán cần xử lý grapheme cluster, Java Regex còn có `\X` và `\b{g}`, nhưng đó là khái niệm khác với UCC.

**Phiên bản Unicode và hiệu năng.** Các tập Unicode phụ thuộc dữ liệu Unicode mà JDK hỗ trợ; test những ký tự quan trọng trên đúng phiên bản JDK triển khai. UCC có thể làm regex tốn chi phí hơn trong một số trường hợp; nên biên dịch `Pattern` một lần nếu tái sử dụng thường xuyên. `Pattern` có thể dùng chung giữa các luồng, còn `Matcher` lưu trạng thái và không nên dùng chung đồng thời.

**An toàn đầu vào.** UCC mở rộng tập ký tự được chấp nhận, không tự phát hiện ký tự dễ gây nhầm lẫn về hình dạng, không tự bảo vệ trước Unicode spoofing, không tự áp dụng giới hạn độ dài hay chuẩn nghiệp vụ. Với định danh, URL, mã đơn hàng hoặc token máy đọc, hãy viết allowlist theo đúng hợp đồng dữ liệu; với văn bản người dùng, xác định thêm chiến lược chuẩn hóa và kiểm tra.

## 8. Các lỗi phổ biến và cách tránh

1. **Nghĩ `\w` luôn nhận tiếng Việt:** mặc định `[a-zA-Z_0-9]`; bật UCC hoặc mô tả tập Unicode mong muốn bằng `\p{...}`.
2. **Nghĩ `(?u)` và `(?U)` giống nhau:** chữ thường `u` là Unicode case folding; chữ hoa `U` là Unicode character classes.
3. **Dùng `\d` cho mã số ASCII rồi vô tình bật UCC:** nhiều chữ số từ hệ chữ viết khác sẽ được chấp nhận. Dùng `[0-9]` nếu chỉ cần ASCII.
4. **Dùng `(?U)\w+` để kiểm tra tên thuần chữ:** mẫu cũng cho phép chữ số và dấu nối; có thể cần `[\p{L}\p{M}]+` cùng quy tắc nghiệp vụ.
5. **Quên escape trong Java string:** regex `\p{L}` phải viết `"\\p{L}"`; nếu đọc regex từ tệp/cấu hình thì số lớp escape khác với literal trong mã Java.
6. **Đồng nhất Unicode classes với chuẩn hóa/locale:** UCC không biến NFD thành NFC và không thực hiện đối chiếu ngôn ngữ tự nhiên.
7. **Nhầm `matches()` với `find()`:** một cái khớp cả đầu vào, cái kia tìm đoạn con.
8. **Giả định mọi lớp đều thay đổi bởi UCC:** `\p{ASCII}` vẫn chỉ ASCII; `[a-z]`, `[0-9]` vẫn là dải ký tự viết tường minh.

## 9. Checklist lựa chọn regex

- Cần khớp các khoảng trắng/số/ký tự từ trên nhiều hệ chữ viết? Cân nhắc `Pattern.UNICODE_CHARACTER_CLASS` hoặc `(?U)`.
- Cần tập ký tự chính xác, ví dụ chỉ `A`–`Z` hoặc `0`–`9`? Ghi dải ASCII trực tiếp.
- Cần “chữ cái” thay vì “word character”? Dùng Unicode category/property phù hợp, cân nhắc dấu kết hợp.
- Cần so khớp không phân biệt hoa/thường? Thêm `CASE_INSENSITIVE`; UCC mang theo `UNICODE_CASE`.
- Cần đối chiếu các cách biểu diễn Unicode tương đương? Chuẩn hóa (thường là NFC) nhất quán.
- Có dữ liệu ngoài ASCII trong test? Kiểm thử NBSP, dấu tiếng Việt dạng dựng sẵn/dạng kết hợp, chữ số khác hệ viết và ký tự bổ sung theo JDK mục tiêu.

## Tài liệu chính thức

- [Java SE 26 — `java.util.regex.Pattern`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html): predefined classes, POSIX classes, Unicode support và `UNICODE_CHARACTER_CLASS`.
- [Java SE 17 — `java.util.regex.Pattern`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): đối chiếu API được hỗ trợ trên Java 17.
- [Java SE 26 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): chuẩn hóa NFC/NFD khi cần xử lý chuỗi Unicode tương đương.