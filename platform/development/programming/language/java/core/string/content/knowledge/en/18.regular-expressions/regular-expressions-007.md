# CASE_INSENSITIVE, UNICODE_CASE và UNICODE_CHARACTER_CLASS trong Java Regex

## 1. Vì sao cần phân biệt ba cờ?

Trong Java, `java.util.regex.Pattern` biên dịch một biểu thức chính quy (regular expression), còn `Matcher` kiểm tra biểu thức đó trên chuỗi. Tham số `flags` của `Pattern.compile(regex, flags)` thay đổi cách engine hiểu phép so khớp. Ba cờ dễ bị nhầm lẫn:

- `Pattern.CASE_INSENSITIVE`: bật **so khớp không phân biệt hoa/thường**; mặc định phần xử lý hoa/thường này theo US-ASCII.
- `Pattern.UNICODE_CASE`: khi đã bật so khớp không phân biệt hoa/thường, dùng **quy tắc Unicode case folding** thay vì chỉ US-ASCII. Bản thân cờ này **không bật** chế độ bỏ qua hoa/thường.
- `Pattern.UNICODE_CHARACTER_CLASS`: cho các lớp ký tự định nghĩa sẵn và các lớp POSIX như `\d`, `\w`, `\s`, `\p{Alpha}`, `\p{Digit}` hoạt động theo định nghĩa Unicode. Cờ này **ngầm bật UNICODE_CASE**, nhưng **không ngầm bật CASE_INSENSITIVE**.

Vì thế, “không phân biệt hoa/thường” và “nhận diện lớp ký tự Unicode” là hai vấn đề độc lập. Một regex có thể hỗ trợ chữ số Unicode mà vẫn phân biệt `é` với `É`; hoặc có thể so khớp `é` với `É` nhưng `\d` vẫn chỉ nhận các chữ số ASCII.

| Cờ Java | Ký hiệu ngay trong regex | Điều thay đổi trực tiếp | Điều không tự làm |
| --- | --- | --- | --- |
| `CASE_INSENSITIVE` | `(?i)` | Bỏ qua khác biệt hoa/thường khi so khớp, mặc định dựa trên US-ASCII | Không tự mở rộng `\d`, `\w`, `\s` thành Unicode |
| `UNICODE_CASE` | `(?u)` | Dùng Unicode case folding **khi chế độ không phân biệt hoa/thường đã bật** | Không tự bật `CASE_INSENSITIVE`; không đổi các lớp ký tự thành Unicode |
| `UNICODE_CHARACTER_CLASS` | `(?U)` (chữ `U` viết hoa) | Áp dụng quy tắc Unicode cho các lớp ký tự định nghĩa sẵn/POSIX; đồng thời ngầm bật `UNICODE_CASE` | Không tự bật `CASE_INSENSITIVE`; không xóa dấu hay chuẩn hóa Unicode |

## 2. CASE_INSENSITIVE: không phân biệt hoa/thường kiểu mặc định

`Pattern.CASE_INSENSITIVE` làm cho `"java"` khớp `"JAVA"`. Nó cũng tác động đến ký tự chữ cái trong literal, tập ký tự và các nhóm regex thích hợp. Tuy nhiên, theo hợp đồng của `Pattern`, khi dùng riêng cờ này, so khớp không phân biệt hoa/thường mặc định giả định **US-ASCII**. Ví dụ với `é` và `É` sẽ thể hiện giới hạn:

```java
import java.util.regex.Pattern;

boolean ascii = Pattern.compile("java", Pattern.CASE_INSENSITIVE)
                       .matcher("JAVA").matches();

boolean accent = Pattern.compile("\u00E9", Pattern.CASE_INSENSITIVE)
                        .matcher("\u00C9").matches();

System.out.println(ascii);  // true
System.out.println(accent); // false
```

Hai đoạn trên là các câu lệnh minh họa (có thể chạy trong `jshell`), không phải một lớp Java độc lập. Phương thức `matches()` yêu cầu **toàn bộ đầu vào** khớp regex; `find()` tìm một đoạn con phù hợp. Khác biệt giữa hai phương thức này không liên quan đến cờ.

Sử dụng `(?i)` khi muốn khai báo cờ ngay trong regex, chẳng hạn `Pattern.compile("(?i)java")`. Trong mã Java, hai cách sau tương đương về ý nghĩa với regex này:

```java
Pattern.compile("java", Pattern.CASE_INSENSITIVE);
Pattern.compile("(?i)java");
```

## 3. UNICODE_CASE: làm Unicode case folding hoạt động cùng CASE_INSENSITIVE

Cờ `Pattern.UNICODE_CASE` điều chỉnh **cách** đối chiếu hoa/thường khi `CASE_INSENSITIVE` đang có hiệu lực. Nó không tự biến biểu thức thành case-insensitive. Với hai ký tự `é` (U+00E9) và `É` (U+00C9):

| Bộ cờ | `"é"` có khớp `"É"` không? | Vì sao? |
| --- | --- | --- |
| Không cờ | Không | So khớp có phân biệt hoa/thường |
| Chỉ `CASE_INSENSITIVE` | Không | Bỏ qua hoa/thường theo US-ASCII mặc định |
| Chỉ `UNICODE_CASE` | Không | Chưa bật bỏ qua hoa/thường |
| `CASE_INSENSITIVE \| UNICODE_CASE` | Có | Bật bỏ qua hoa/thường và dùng Unicode case folding |

Cách kết hợp đúng là dùng phép OR bitwise `|`:

```java
Pattern p = Pattern.compile(
    "\u00E9",
    Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
);
boolean found = p.matcher("\u00C9").matches(); // true
```

Hoặc đặt cả hai cờ trong biểu thức: `(?iu)é`. Chữ `i` bật không phân biệt hoa/thường; chữ `u` chọn cách xử lý Unicode. Dùng `(?u)` một mình không đạt yêu cầu này.

**Ranh giới cần nhớ:** Unicode case folding không đồng nghĩa với xóa dấu, chuyển tự hay chuẩn hóa văn bản. Ví dụ `é` và `e` là hai chữ khác nhau; chuỗi một ký tự `é` (dạng dựng sẵn) và chuỗi `e` + dấu sắc kết hợp (dạng phân rã) cũng không được tự động xem là tương đương chỉ vì bật `UNICODE_CASE`. Khi cần cùng một chuẩn biểu diễn, cân nhắc `java.text.Normalizer` với NFC/NFD theo yêu cầu; việc chuẩn hóa phải được thiết kế riêng.

Case folding trong regex cũng không thay thế phép biến đổi chữ hoa/thường phụ thuộc ngôn ngữ như `String.toLowerCase(Locale)`. Với các luật xử lý tên riêng, thứ tự từ điển hoặc ngôn ngữ cụ thể, cần kiểm thử dữ liệu thực tế thay vì giả định một phép so khớp có thể đáp ứng mọi quy tắc bản địa hóa.

## 4. UNICODE_CHARACTER_CLASS: mở rộng ý nghĩa của lớp ký tự

Không bật `UNICODE_CHARACTER_CLASS`, một số lớp ký tự định nghĩa sẵn thường được hiểu theo phạm vi US-ASCII:

| Regex | Mặc định (US-ASCII) | Khi bật `UNICODE_CHARACTER_CLASS` |
| --- | --- | --- |
| `\d` | Chữ số `0` đến `9` | Chữ số thập phân Unicode, tương ứng `\p{IsDigit}` |
| `\w` | `[a-zA-Z_0-9]` | Gồm chữ cái Unicode, dấu kết hợp, chữ số, dấu nối thuộc lớp connector và join control theo định nghĩa Java |
| `\s` | Các khoảng trắng ASCII tiêu chuẩn như space, tab, xuống dòng | Ký tự khoảng trắng theo Unicode `White_Space` |
| `\p{Alpha}` | Chữ cái ASCII | Ký tự có thuộc tính Unicode `Alphabetic` |
| `\p{Digit}` | Chữ số ASCII | Chữ số thập phân Unicode |
| `\p{ASCII}` | Vẫn chỉ ASCII | Vẫn chỉ ASCII; cờ không biến mọi lớp thành “mọi ký tự” |

Ví dụ `"١٢٣"` gồm ba chữ số Arabic-Indic: `\d+` mặc định không khớp toàn bộ, nhưng sẽ khớp khi bật `UNICODE_CHARACTER_CLASS`. Tương tự, `"café"` không khớp toàn bộ `\w+` mặc định, nhưng khớp khi bật cờ này.

```java
Pattern asciiDigits = Pattern.compile("\\d+");
Pattern unicodeDigits = Pattern.compile(
    "\\d+", Pattern.UNICODE_CHARACTER_CLASS
);

String digits = "\u0661\u0662\u0663"; // ١٢٣
System.out.println(asciiDigits.matcher(digits).matches());   // false
System.out.println(unicodeDigits.matcher(digits).matches()); // true
```

**Điểm phân biệt quan trọng:** `UNICODE_CASE` **không** làm `\d` hay `\w` mở rộng phạm vi; muốn đổi các lớp đó thì dùng `UNICODE_CHARACTER_CLASS`. Ngược lại, `UNICODE_CHARACTER_CLASS` có ngầm bật `UNICODE_CASE` nhưng vẫn cần `CASE_INSENSITIVE` nếu muốn bỏ qua hoa/thường:

- `Pattern.compile("é", Pattern.UNICODE_CHARACTER_CLASS)` vẫn không khớp `"É"` với `matches()`.
- `Pattern.compile("é", Pattern.UNICODE_CHARACTER_CLASS | Pattern.CASE_INSENSITIVE)` sẽ khớp `"É"`.
- `Pattern.compile("(?U)\\w+")` nhận dạng `\w` theo Unicode, còn `Pattern.compile("(?iU)é")` vừa dùng Unicode character classes vừa bỏ qua hoa/thường.

Các lớp như `\p{L}` (ký tự thuộc nhóm Letter của Unicode) và `\p{Nd}` (Decimal_Number) **đã là các thuộc tính Unicode được gọi tường minh**, kể cả khi chưa bật `UNICODE_CHARACTER_CLASS`. Vì vậy `\p{L}+` là một lựa chọn rõ nghĩa khi chỉ cần chữ cái Unicode, không nhất thiết phải bật `(?U)` cho toàn regex.

Lưu ý rằng khái niệm “word” trong `\w` khi bật Unicode **rộng hơn chữ cái đơn thuần**. Nó có thể nhận các dấu kết hợp và một số ký tự điều khiển nối chữ. Nếu kiểm tra tên người, mã tài khoản hay định danh, đừng mặc nhiên coi `(?U)\w+` là bộ quy tắc nghiệp vụ hoàn chỉnh.

## 5. Ví dụ Java 17+ có thể biên dịch và chạy

Lưu chương trình UTF-8 vào `RegexUnicodeFlagsDemo.java`. Các chuỗi `\u00E9`, `\u00C9` và `\u0661`–`\u0663` là cách viết Unicode escape trong mã nguồn Java để ví dụ tái hiện được mà không phụ thuộc bàn phím:

```java
import java.util.regex.Pattern;

public class RegexUnicodeFlagsDemo {
    private static void check(String name, String regex, String input, int flags) {
        boolean ok = Pattern.compile(regex, flags).matcher(input).matches();
        System.out.println(name + " = " + ok);
    }

    public static void main(String[] args) {
        check("ASCII letters", "java", "JAVA", Pattern.CASE_INSENSITIVE);
        check("Accent, i only", "\u00E9", "\u00C9", Pattern.CASE_INSENSITIVE);
        check("Accent, u only", "\u00E9", "\u00C9", Pattern.UNICODE_CASE);
        check("Accent, iu", "\u00E9", "\u00C9",
                Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

        check("Arabic digits, default", "\\d+", "\u0661\u0662\u0663", 0);
        check("Arabic digits, U", "\\d+", "\u0661\u0662\u0663",
                Pattern.UNICODE_CHARACTER_CLASS);

        check("Unicode word, default", "\\w+", "caf\u00E9", 0);
        check("Unicode word, U", "\\w+", "caf\u00E9",
                Pattern.UNICODE_CHARACTER_CLASS);

        check("Accent, U only", "\u00E9", "\u00C9",
                Pattern.UNICODE_CHARACTER_CLASS);
        check("Accent, iU", "\u00E9", "\u00C9",
                Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CHARACTER_CLASS);

        check("Explicit letter class", "\\p{L}+", "caf\u00E9", 0);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 RegexUnicodeFlagsDemo.java
java RegexUnicodeFlagsDemo
```

Kết quả chuẩn:

```text
ASCII letters = true
Accent, i only = false
Accent, u only = false
Accent, iu = true
Arabic digits, default = false
Arabic digits, U = true
Unicode word, default = false
Unicode word, U = true
Accent, U only = false
Accent, iU = true
Explicit letter class = true
```

Đọc kết quả theo hai nhóm: bốn dòng đầu cho thấy **bật `i` và `u` cùng nhau** mới so khớp chữ hoa/thường Unicode; các dòng chữ số/word cho thấy **`U`** thay đổi lớp ký tự. Dòng `Accent, U only` xác nhận `U` không tự bật `i`; dòng `Accent, iU` cho thấy `U` đã ngầm có `u`. Dòng cuối cho thấy có thể gọi lớp thuộc tính Unicode tường minh mà không bật `U`.

## 6. Chọn cách cấu hình cờ và phạm vi áp dụng

Có ba cách phổ biến:

**Dùng cờ khi biên dịch `Pattern`:** phù hợp khi tạo pattern tái sử dụng nhiều lần và muốn cấu hình tách khỏi regex.

```java
Pattern search = Pattern.compile(
    "cafe",
    Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
);
boolean result = search.matcher("CAFE").matches(); // true
```

**Dùng inline flag ở đầu regex:** phù hợp với API chỉ nhận biểu thức chuỗi, ví dụ `String.matches(String regex)`:

```java
boolean a = "\u00C9".matches("(?iu)\u00E9");  // true
boolean b = "caf\u00E9".matches("(?U)\\w+"); // true
```

**Giới hạn cờ cho một nhóm:** Java hỗ trợ cú pháp `(?flags:...)`. Ví dụ `(?i:[a-z]+)` chỉ bật chế độ không phân biệt hoa/thường bên trong nhóm; `(?iu:é)` bật cả `i` và `u` cho nhóm đó. Khi cần một phần quy tắc giữ phân biệt hoa/thường, scoped flags giúp diễn đạt phạm vi chính xác. Có thể tắt cờ inline phù hợp bằng dạng `(?-i:...)`.

Chữ trong embedded flag phân biệt hoa/thường: `u` viết thường chỉ chế độ Unicode-aware case folding; `U` viết hoa bật Unicode character classes. Đừng đọc `(?u)` và `(?U)` là cùng một tùy chọn.

**Quy tắc về dấu gạch chéo trong Java:** chuỗi Java `"\\d+"` biểu diễn regex `\d+` (vì Java cần escape ký tự `\`). Do đó `"(?U)\\d+"` biểu diễn regex `(?U)\d+`. Viết `"\d+"` trực tiếp trong Java string là sai cú pháp escape của Java. Nếu regex lấy từ cấu hình hoặc chuỗi đã được tạo sẵn, số lần escape phụ thuộc lớp biểu diễn chứ không thay đổi ý nghĩa của `\d`.

## 7. Những lựa chọn thực tế và lỗi dễ gặp

| Yêu cầu | Lựa chọn tiêu biểu | Lý do |
| --- | --- | --- |
| Mã chỉ gồm chữ Latin ASCII và số ASCII, không phân biệt hoa/thường | `Pattern.compile("[a-z0-9_-]+", Pattern.CASE_INSENSITIVE)` | Giữ tập ký tự đầu vào hẹp, rõ ràng |
| So khớp chữ có dấu mà không phân biệt hoa/thường | `CASE_INSENSITIVE \| UNICODE_CASE` hoặc `(?iu)` | Cần cả việc bật case-insensitive lẫn Unicode folding |
| Nhận chữ số thập phân từ các hệ chữ viết Unicode bằng `\d` | `(?U)\d+` | Mở rộng lớp `\d` theo Unicode |
| Cho phép chữ cái Unicode nhưng kiểm soát rõ tập ký tự | `\p{L}+` hoặc một tập `\p{L}`, `\p{M}`, `\p{Nd}` được thiết kế riêng | Không phụ thuộc việc `\w` có chấp nhận thêm dấu nối và ký tự đặc biệt |
| Chỉ nhận ký tự số từ `0` đến `9` | `[0-9]+` | Ràng buộc ASCII rõ ràng ngay cả khi pattern có `(?U)` |

Các lỗi cần tránh:

1. **Nghĩ `UNICODE_CASE` tự bỏ qua hoa/thường.** Cần kết hợp `CASE_INSENSITIVE`.
2. **Nghĩ `CASE_INSENSITIVE` tự khiến `\w` nhận tất cả chữ Unicode.** Cờ thay đổi so khớp hoa/thường, không phải lớp ký tự.
3. **Nghĩ `(?U)` tự làm mọi so khớp case-insensitive.** `U` ngầm có `u` nhưng không có `i`.
4. **Dùng `\d` mà quên yêu cầu nghiệp vụ.** `(?U)\d` nhận chữ số Unicode; `[0-9]` mới nói rõ “chỉ số ASCII”. Điều này quan trọng khi chuỗi phải tương thích với giao thức, định dạng hay hệ thống chỉ nhận ASCII.
5. **Dùng `(?U)\w+` như bộ lọc tên/username tuyệt đối.** Hãy định nghĩa rõ tập ký tự, độ dài, chuẩn hóa và các quy tắc riêng cho dữ liệu đầu vào.
6. **Nhầm hoa/thường Unicode với bỏ dấu hoặc so sánh ngôn ngữ.** `"é"` và `"e"` vẫn khác nhau; normalization và collation là những chủ đề độc lập.
7. **Quên phân biệt `matches()` và `find()`, hoặc quên Java string escaping.** Một pattern đúng vẫn có thể cho kết quả khác kỳ vọng nếu kiểm tra toàn chuỗi thay vì đoạn con hoặc escape sai.

Hiệu năng: tài liệu JDK lưu ý `CASE_INSENSITIVE` có thể thêm ít chi phí, còn `UNICODE_CASE` và `UNICODE_CHARACTER_CLASS` có thể tăng chi phí xử lý. Chọn cờ theo yêu cầu thực tế, tái sử dụng `Pattern` đã biên dịch khi dùng lặp lại, và đo đạc bằng dữ liệu thực nếu hiệu năng quan trọng. Kết quả cụ thể còn phụ thuộc phiên bản JDK và phiên bản dữ liệu Unicode mà JDK hỗ trợ.

## 8. Tự kiểm tra

**Câu 1.** Vì sao `Pattern.compile("\\d+")` không khớp toàn bộ chuỗi `"١٢٣"` nhưng `Pattern.compile("(?U)\\d+")` lại khớp?

**Giải thích:** `\d` mặc định là chữ số ASCII; `(?U)` chuyển lớp này sang phạm vi chữ số thập phân Unicode. Hai mẫu đều dùng `matches()` để kiểm tra toàn chuỗi.

**Câu 2.** Nếu đã bật `UNICODE_CHARACTER_CLASS`, liệu `"é"` có tự khớp `"É"` hay không?

**Giải thích:** Không. Cờ `U` ngầm bật `UNICODE_CASE` để định nghĩa quy tắc folding nhưng không bật `CASE_INSENSITIVE`. Muốn bỏ qua hoa/thường, thêm `CASE_INSENSITIVE` hoặc dùng `(?iU)`.

**Câu 3.** Khi chỉ muốn nhận số ASCII, nên viết `\\d+` với `(?U)` hay `[0-9]+`?

**Giải thích:** `[0-9]+` nêu rõ tập ký tự ASCII cần chấp nhận, ổn định về phạm vi khi pattern được dùng chung với các cờ Unicode khác.

**Tài liệu tham khảo:** [Java SE 17 — `java.util.regex.Pattern`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), đặc biệt phần “Predefined Character classes”, “Unicode Support” và mô tả ba hằng `CASE_INSENSITIVE`, `UNICODE_CASE`, `UNICODE_CHARACTER_CLASS`.
