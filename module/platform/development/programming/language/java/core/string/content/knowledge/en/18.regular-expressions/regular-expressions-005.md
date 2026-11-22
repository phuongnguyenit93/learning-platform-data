# Hai lớp escape: literal Java và cú pháp regex

## 1. Vì sao phải hiểu hai lớp escape?

Trong Java, biểu thức chính quy thường được truyền cho `java.util.regex.Pattern`, `String.matches`, `String.split` hoặc `String.replaceAll` dưới dạng một `String`. Khi viết chuỗi này **ngay trong mã nguồn Java**, có hai bộ phân tích cú pháp xử lý lần lượt:

1. **Java string literal:** trình biên dịch xử lý cú pháp bên trong dấu `"..."`, bao gồm escape như `\\` (một dấu backslash), `\n` (xuống dòng), `\t` (tab), `\"` (dấu nháy).
2. **Regex:** regex engine của `Pattern` nhận chuỗi *đã được Java xử lý* rồi diễn giải `\d` (chữ số), `\s` (whitespace), `\.` (dấu chấm literal), `\b` (ranh giới từ), v.v.

Do đó, **backslash dùng trong regex thường phải viết gấp đôi trong Java string literal**.

```text
Java source           Giá trị String runtime        Regex engine hiểu
"\\d+"          ->     \d+                      ->   một hay nhiều chữ số
"\\."           ->     \.                       ->   dấu chấm literal
"\\\\"         ->     \\                       ->   một dấu \ literal
```

Hãy giải mã lớp Java trước, rồi mới giải mã lớp regex. Hai lớp cùng dùng dấu `\` nhưng có **ngữ pháp và mục đích khác nhau**.

## 2. Lớp thứ nhất: Java string literal

| Literal trong Java source | Giá trị chuỗi thực tế | Lưu ý |
| --- | --- | --- |
| `"abc"` | `abc` | Không có escape |
| `"\\."` | `\.` | Hai backslash trong source tạo một backslash |
| `"\\d+"` | `\d+` | Ba ký tự runtime: `\`, `d`, `+` |
| `"\\\\"` | `\\` (hai dấu backslash) | Bốn backslash trong source tạo hai backslash |
| `"\n"` | Một ký tự xuống dòng | Không phải hai ký tự `\` và `n` |
| `"\t"` | Một ký tự tab | Không phải hai ký tự `\` và `t` |
| `"\""` | Một dấu nháy kép `"` | Escape dành cho dấu nháy |

Java không công nhận các escape source `\d` và `\.`. Vì vậy `"\d+"` hay `"\."` gây lỗi biên dịch (*illegal escape character*) trước khi regex engine có cơ hội xử lý.

### Chú ý đặc biệt với `\s` trong Java 17+

Từ Java 15, `\s` **là escape hợp lệ trong Java string literal**, nghĩa là một dấu cách thường U+0020. Điều này dễ gây lỗi âm thầm:

- `"\\s+"` tạo regex `\s+`, khớp một hay nhiều whitespace theo quy tắc regex (như space, tab).
- `"\s+"` tạo regex ` +`, khớp một hay nhiều **dấu cách thường**, không khớp tab.

Trên Java 17+, cả hai dòng đều biên dịch, nhưng hành vi khác nhau. Không thể dùng kết quả biên dịch thành công để kết luận đã escape regex chính xác.

## 3. Lớp thứ hai: Regex engine của `Pattern`

Một số ánh xạ thông dụng:

| Ý định | Regex thực tế cần truyền vào `Pattern` | Viết trong Java string literal |
| --- | --- | --- |
| Một hay nhiều chữ số | `\d+` | `"\\d+"` |
| Một hay nhiều whitespace | `\s+` | `"\\s+"` |
| Dấu chấm literal | `\.` | `"\\."` |
| Dấu gạch đứng literal `|` | `\|` | `"\\|"` |
| Một dấu backslash literal `\` | `\\` | `"\\\\"` |
| Ranh giới từ | `\b` | `"\\b"` |
| Ký tự thuộc Unicode Letter | `\p{L}` | `"\\p{L}"` |

Dấu chấm `.` không được escape trong regex là **ký tự đại diện** (thông thường khớp một ký tự trừ ký tự kết thúc dòng, trừ khi bật `DOTALL`). Regex `\.` có nghĩa dấu chấm thật; Java literal cho nó là `"\\."`. Còn muốn regex nhận *một dấu backslash thật*, phải tạo regex `\\`, vì vậy Java source cần `"\\\\"`.

Đối với ranh giới từ, regex `\b` khớp **vị trí**, không tiêu thụ ký tự. Java literal `"\\b"` đưa hai ký tự `\` và `b` đến regex engine. Ngược lại `"\b"` là escape **backspace U+0008 của Java**, nên nghĩa khác hoàn toàn.

## 4. Ví dụ Java 17+ có thể chạy độc lập

Lưu đúng tên tệp `EscapeLayersDemo.java`:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

public class EscapeLayersDemo {
    public static void main(String[] args) {
        System.out.println("dot literal: " + "a.b".matches("a\\.b"));
        System.out.println("dot strict: " + "axb".matches("a\\.b"));
        System.out.println("dot wildcard: " + "axb".matches("a.b"));

        System.out.println("digit: " + "123".matches("\\d+"));
        System.out.println("digit overescape: " + "123".matches("\\\\d+"));

        System.out.println("backslash: " + "\\".matches("\\\\"));
        System.out.println("tab whitespace: " + "a\tb".matches("a\\sb"));
        System.out.println("tab mistaken Java escape: "
                + "a\tb".matches("a\s+b"));

        System.out.println("quoted dot: "
                + "a.b".matches("a" + Pattern.quote(".") + "b"));
        System.out.println("literal replacement: "
                + "a.b".replace(".", "-"));
        System.out.println("regex replacement: "
                + "a.b".replaceAll("\\.", "-"));
        System.out.println("split: "
                + Arrays.toString("one.two".split("\\.")));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 EscapeLayersDemo.java
java EscapeLayersDemo
```

Stdout chính xác:

```text
dot literal: true
dot strict: false
dot wildcard: true
digit: true
digit overescape: false
backslash: true
tab whitespace: true
tab mistaken Java escape: false
quoted dot: true
literal replacement: a-b
regex replacement: a-b
split: [one, two]
```

Các điểm cần đọc kỹ từ ví dụ:

- `"a\\.b"` qua lớp Java trở thành regex `a\.b`, chỉ khớp `a.b`. `"a.b"` qua regex giữ dấu `.` đại diện nên còn khớp `axb`.
- `"\\d+"` trở thành regex `\d+`, khớp `123`. Nhưng `"\\\\d+"` trở thành regex `\\d+`: regex hiểu `\\` là **backslash literal**, còn `d+` là một hoặc nhiều chữ `d`, vì vậy không khớp `123`. Đây là lỗi **escape thừa**.
- `"\\"` tạo dữ liệu đầu vào chỉ gồm một dấu backslash. `"\\\\"` tạo regex khớp đúng dấu đó.
- `"a\tb"` chứa tab. Regex `a\sb` khớp tab, nhưng Java source `"a\s+b"` tạo regex `a +b` nên không khớp tab.
- `Pattern.quote(".")` tạo mẫu tìm **dấu chấm literal**. `replace` không dùng regex, còn `replaceAll` dùng regex ở đối số đầu tiên.
- `split("\\.")` dùng regex tìm dấu chấm literal. `split(".")` sẽ hiểu `.` là ký tự đại diện, nên không có ý nghĩa tách theo dấu chấm thật.

`String.matches(regex)` yêu cầu **toàn bộ chuỗi** khớp. Nếu cần tìm một đoạn bất kỳ, dùng `Pattern.compile(regex).matcher(input).find()`. Ví dụ `"abc123".matches("\\d+")` cho `false`, nhưng `Pattern.compile("\\d+").matcher("abc123").find()` cho `true`.

## 5. Phân tích escape đúng cách: từ mã nguồn đến hành vi

Xét hai chuỗi sau trong thân một phương thức Java:

```java
String digits = "\\d+";
String extraSlash = "\\\\d+";

System.out.println(digits);      // \d+
System.out.println(extraSlash);  // \\d+
```

- `digits` có ba ký tự runtime: `\`, `d`, `+`. Regex hiểu là *một hay nhiều chữ số*.
- `extraSlash` có bốn ký tự runtime: `\`, `\`, `d`, `+`. Regex hiểu là *một backslash literal theo sau một hay nhiều chữ d*.

Các thông báo lỗi cũng xảy ra ở **những giai đoạn khác nhau**:

```java
// Không biên dịch được: \d không phải escape Java hợp lệ.
// String invalidJava = "\d+";

// Dòng sau biên dịch Java được nhưng ném PatternSyntaxException
// khi Pattern cố biên dịch regex gồm một backslash đơn lẻ.
// Pattern.compile("\\");
```

Nếu `String regex` đến từ input người dùng hoặc database *lúc chương trình chạy*, Java không tự áp lại các quy tắc string literal cho ký tự của giá trị đó. Khi `Pattern.compile(regex)` nhận chuỗi runtime có nội dung `\d+`, chỉ còn lớp xử lý regex. File cấu hình như JSON/YAML có thể có cú pháp escape riêng; cần xét định dạng nguồn thực tế, không mặc nhiên áp cú pháp Java source lên mọi chuỗi dữ liệu.

### Xuống dòng và chuỗi `\n`

Cần phân biệt **ký tự xuống dòng thực** với **hai ký tự backslash và chữ n**:

- Trong Java, `"\n"` là ký tự xuống dòng.
- `"\\n"` là hai ký tự `\` và `n`. Khi đưa nội dung `\n` này qua regex engine, `Pattern` diễn giải nó thành mẫu khớp ký tự xuống dòng.
- Nếu muốn khớp đúng hai ký tự `\` và `n` trong dữ liệu, cách an toàn là `Pattern.quote("\\n")`, vì nó tạo regex theo nghĩa literal của toàn bộ chuỗi.

Việc “nhìn thấy `\n`” trong một chuỗi được in ra chưa đủ để biết đó là xuống dòng hay chữ literal; phải xác định đang nhìn mã nguồn, giá trị runtime hay regex đã được phân tích.

## 6. Khi nào nên dùng `Pattern.quote`?

Khi đoạn cần tìm là **dữ liệu literal**, đặc biệt dấu phân cách lấy từ input/configuration, `Pattern.quote(value)` tạo regex khớp nguyên văn nội dung chuỗi. Không cần tự escape dấu chấm, dấu `|`, ngoặc hoặc dấu backslash.

```java
import java.util.Arrays;
import java.util.regex.Pattern;

String delimiter = ".";
String[] fields = "api.example.com".split(Pattern.quote(delimiter));
// fields = ["api", "example", "com"]

String[] keepEmptyEnd = "a.b.".split(Pattern.quote(delimiter), -1);
// keepEmptyEnd = ["a", "b", ""]
```

Đây là **đoạn mã minh họa đặt trong một phương thức**, không phải class chạy độc lập. Mẫu `Pattern.quote` có thể quote cả một chuỗi nhiều ký tự, và cũng xử lý được dấu backslash.

Ngược lại, **không quote một regex mà bạn muốn nó hoạt động như regex**. Ví dụ `Pattern.quote("\\d+")` sẽ tìm đúng ba ký tự `\`, `d`, `+` trong input, không còn mang nghĩa một hay nhiều chữ số. Để khớp chữ số, dùng `Pattern.compile("\\d+")`.

Các ký tự có ý nghĩa đặc biệt trong regex gồm `.`, `^`, `$`, `*`, `+`, `?`, `(`, `)`, `[`, `]`, `{`, `}`, `|` và `\`. Khi chúng là *dữ liệu*, chọn `Pattern.quote` hoặc escape regex theo đúng ngữ cảnh; khi chúng là *toán tử regex*, giữ ngữ nghĩa mong muốn.

## 7. Phân biệt các API và “lớp escape” thứ ba

| API | Ý nghĩa của tham số liên quan |
| --- | --- |
| `Pattern.compile(regex)` | Biên dịch regex |
| `String.matches(regex)` | Regex, yêu cầu toàn chuỗi khớp |
| `String.split(regex)` | Regex làm dấu phân cách |
| `String.replaceAll(regex, replacement)` | Tham số đầu là regex; replacement có cú pháp riêng |
| `String.replace(target, replacement)` | Thay chuỗi literal; không diễn giải regex |

Đặc biệt, với `replaceAll`, **replacement** có thêm quy tắc riêng: `$1` có thể tham chiếu nhóm bắt và `\` là ký tự escape trong replacement. Nếu replacement đến từ dữ liệu literal có thể chứa `$` hoặc `\`, dùng `Matcher.quoteReplacement(replacement)`. Hai hàm không hoán đổi vai trò:

- `Pattern.quote(literal)` xử lý **mẫu tìm kiếm** theo nghĩa literal.
- `Matcher.quoteReplacement(literal)` xử lý **chuỗi thay thế** theo nghĩa literal.

Đây là lý do không thể áp dụng mẹo “chỉ cần nhân đôi mọi backslash” một cách máy móc: trước hết phải biết chuỗi đang được phân tích bởi ngữ pháp Java source, ngữ pháp regex hay ngữ pháp replacement.

## 8. Lỗi phổ biến và cách kiểm tra

1. **`"\d+"` hoặc `"\."` không biên dịch:** Java không có những escape đó. Cần `"\\d+"` hoặc `"\\."`.
2. **`"\s+"` biên dịch được nhưng bỏ sót tab:** Java đã biến `\s` thành space. Để dùng regex whitespace, cần `"\\s+"`.
3. **`"."` khớp quá rộng:** regex hiểu `.` là ký tự đại diện. Nếu muốn dấu chấm, dùng `"\\."`, `"[.]"` hoặc `Pattern.quote(".")`.
4. **`"\\"` được đưa trực tiếp vào regex để tìm dấu backslash:** Java tạo một dấu `\` đơn, khiến regex không hợp lệ. Dùng `"\\\\"` hoặc `Pattern.quote("\\")`.
5. **`"\\\\d+"` bị escape thừa:** regex không còn là chữ số. Xác định giá trị `String` trung gian trước khi sửa.
6. **`"\b"` bị dùng cho word boundary:** Java tạo ký tự backspace. Dùng `"\\b"`.
7. **`Pattern.quote("\\d+")` mất tác dụng regex:** chỉ quote khi mẫu thực sự là dữ liệu literal.
8. **Thay thế chuỗi chứa `$` hay `\` bằng `replaceAll`:** với replacement nguyên văn, dùng `Matcher.quoteReplacement`.
9. **Nhầm `matches` và `find`:** `matches` khớp toàn bộ input, `find` tìm đoạn phù hợp.

### Quy trình tự kiểm tra

**Bước 1.** Viết rõ bạn muốn khớp một ký tự literal hay cú pháp regex (ví dụ dấu chấm thật hay ký tự bất kỳ).

**Bước 2.** Tính chính xác giá trị `String` sau bước Java literal: có bao nhiêu ký tự `\`, tab hoặc xuống dòng thực?

**Bước 3.** Phân tích giá trị đó theo `Pattern`; nếu dùng `replaceAll`, phân tích replacement theo ngữ pháp replacement riêng.

**Bước 4.** Kiểm thử cả dữ liệu phải khớp và dữ liệu gần giống nhưng **không được khớp**, chẳng hạn `a.b` so với `axb`. Kiểm tra đúng API `matches`, `find`, `split` hoặc `replaceAll` theo mục đích.

**Ghi nhớ:** với regex viết trong Java source, phải đi qua **hai lớp**: Java giải mã literal thành `String`; regex engine giải mã `String` thành quy tắc khớp. `Pattern.quote` hữu ích khi mục tiêu là tìm chuỗi literal, còn `"\\d+"`, `"\\."`, `"\\s+"` minh họa cách escape khi muốn dùng cú pháp regex thật.
