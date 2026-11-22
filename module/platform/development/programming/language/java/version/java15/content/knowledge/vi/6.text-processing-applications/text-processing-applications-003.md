# Regex nhiều dòng và các lớp escape cần xử lý trong Java 15+

## 1. Ba lớp cần hiểu trước khi viết regex bằng text block

Khi xử lý log, thông báo lỗi hoặc văn bản có nhiều dòng, Java 15+ cho phép đặt biểu thức chính quy (regular expression, **regex**) trong **text block** `""" ... """`. Cú pháp này giúp pattern dài dễ đọc, nhưng rất dễ nhầm giữa các lớp diễn giải:

1. **Lớp mã nguồn Java:** Trình biên dịch đọc text block, loại phần thụt lề chung, chuẩn hóa xuống dòng và xử lý escape Java như `\\`, `\n`, `\t`, `\s`. Kết quả là một `String`.
2. **Lớp cú pháp regex:** `java.util.regex.Pattern` đọc `String` đó và diễn giải các ký hiệu như `\d` (chữ số), `\s` (khoảng trắng), `\b` (ranh giới từ), `^` và `$` (neo), `.` hoặc `\R` (xuống dòng).
3. **Lớp chuỗi thay thế (nếu có):** `Matcher.replaceAll` / `String.replaceAll` còn diễn giải `$1`, `$2` hoặc `\` trong đối số *replacement*. Đây là cú pháp riêng, khác với regex *pattern*.

Ngoài ra, **văn bản đầu vào** là dữ liệu thực tế cần khớp, có thể chứa LF (`\n`), CRLF (`\r\n`) hoặc các ký tự Unicode. Những ký tự trong dữ liệu **không tự động** đi qua bước escape của mã nguồn Java lần nữa.

Text block và regex giải quyết **hai việc độc lập**: text block chỉ giúp **viết giá trị `String` trong source code**; cờ `Pattern.MULTILINE`, `Pattern.DOTALL`, `Pattern.COMMENTS` mới quyết định regex diễn giải nội dung đó ra sao.

Các API và cú pháp trong bài đều đang được Java hiện đại hỗ trợ. Text block là tính năng chính thức từ **Java 15**, không cần `--enable-preview`. Những ví dụ độc lập dùng Java 17+ để dễ biên dịch và chạy.

## 2. `MULTILINE`, `DOTALL` và `COMMENTS` khác nhau thế nào?

### 2.1. `MULTILINE`: thay đổi phạm vi của `^` và `$`

Mặc định, `^` và `$` chủ yếu neo ở đầu/cuối **toàn bộ đầu vào** (với quy tắc riêng cho dấu kết thúc dòng cuối). Khi bật `Pattern.MULTILINE` hay `(?m)`, chúng có thể khớp ở **đầu/cuối từng dòng**:

```java
import java.util.regex.Pattern;

String input = "OK\nERROR 503\nOK\n";

boolean withoutMultiline = Pattern.compile("^ERROR.*$")
        .matcher(input).find();
boolean withMultiline = Pattern.compile("(?m)^ERROR.*$")
        .matcher(input).find();

System.out.println(withoutMultiline); // false
System.out.println(withMultiline);    // true
```

`(?m)` không tự khiến dấu `.` khớp ký tự xuống dòng và cũng **không cắt chuỗi thành từng phần tử**; `Matcher.find()` quét cùng một đầu vào và tìm vị trí đáp ứng pattern.

- `^` với `MULTILINE`: đầu toàn bộ đầu vào hoặc vị trí đầu dòng sau một dấu kết thúc dòng.
- `$` với `MULTILINE`: cuối dòng, ngay trước dấu kết thúc dòng, hoặc cuối toàn bộ đầu vào.
- `\A` luôn chỉ **đầu toàn bộ đầu vào** và `\z` luôn chỉ **cuối tuyệt đối** của đầu vào, bất kể `MULTILINE`. Chúng phải được viết thành `\\A`, `\\z` trong Java source.
- `Matcher.find()` tìm **một phần phù hợp** ở bất kỳ vị trí thích hợp; `Matcher.matches()` đòi **toàn bộ vùng đầu vào** khớp pattern. Bật `MULTILINE` không biến `matches()` thành phép kiểm tra “có ít nhất một dòng phù hợp”.

Với log nhiều dòng, tổ hợp thường dùng là `(?m)^...$` đi cùng `matcher.find()` để lấy từng dòng đúng điều kiện.

### 2.2. `DOTALL`: cho phép `.` khớp dấu xuống dòng

Mặc định `.` không khớp dấu kết thúc dòng. Bật `Pattern.DOTALL` hoặc `(?s)` nếu muốn nó khớp cả ký tự xuống dòng:

```java
import java.util.regex.Pattern;

String text = "BEGIN\nEND";
System.out.println(
        Pattern.compile("^BEGIN.*END$").matcher(text).matches()
); // false

System.out.println(
        Pattern.compile("(?s)^BEGIN.*END$").matcher(text).matches()
); // true
```

**Đừng nhầm:** `MULTILINE` thay đổi `^` và `$`; `DOTALL` thay đổi `.`. Có thể bật cả hai, nhưng chỉ khi bài toán cần.

Khi dùng `(?s).*` trên văn bản dài, `.*` là phép lặp **tham lam** và có thể nuốt nhiều khối cùng lúc. `.*?` (không tham lam) có thể hữu ích để tìm khối ngắn hơn, nhưng vẫn cần thiết kế điểm kết thúc rõ và kiểm thử các trường hợp có nhiều khối, chuỗi rỗng hoặc đầu vào rất dài.

### 2.3. `COMMENTS`: viết regex dài trên nhiều dòng cho dễ đọc

Bật `Pattern.COMMENTS` hoặc `(?x)` để Java regex **bỏ qua khoảng trắng không escape và phần chú thích từ `#` đến cuối dòng của biểu thức regex**. Nhờ vậy, có thể trình bày một biểu thức dài trên nhiều dòng text block, thêm chú thích từng phần.

```java
import java.util.regex.Pattern;

String regex = """
        (?x)
        \\d{2}  # Hai chu so dau
        -       # Dau gach noi
        \\d{2}  # Hai chu so cuoi
        """;

System.out.println(
        Pattern.compile(regex).matcher("12-34").matches()
); // true
```

Text block ở trên có nhiều xuống dòng và khoảng trắng trong **giá trị nguồn regex**, nhưng `(?x)` khiến regex engine bỏ qua chúng khi phân tích pattern. Nếu **không** bật `COMMENTS`, những xuống dòng trong text block là ký tự thật của regex và thường làm thay đổi điều kiện khớp.

Cần chú ý với `(?x)`:

- Muốn regex khớp **dấu cách thật**, dùng cú pháp regex có biểu diễn rõ ràng như `\x20` (viết `\\x20` trong Java source) hoặc một lớp ký tự thích hợp, thay vì dựa vào dấu cách nhìn thấy trong pattern.
- Muốn khớp dấu `#` theo nghĩa literal, phải escape phù hợp (ví dụ `\\#` trong Java source) hoặc dùng `Pattern.quote` cho dữ liệu literal.
- Khoảng trắng và chú thích trong **pattern** bị bỏ qua theo luật `COMMENTS`; dấu cách trong **văn bản đầu vào** không tự bị xóa.
- Java `Pattern.COMMENTS` cũng có thể được truyền qua tham số cờ của `Pattern.compile(regex, flags)`. Không cần vừa thêm `(?x)` vừa bật cùng cờ trừ khi bạn có lý do rõ ràng.

Các cờ inline có thể kết hợp: `(?mx)` nghĩa là **MULTILINE + COMMENTS**. `(?ms)` là **MULTILINE + DOTALL**; đừng bật `s` chỉ vì dữ liệu có nhiều dòng.

## 3. Ví dụ hoàn chỉnh: phân tích log nhiều dòng bằng text block

Bài toán: tìm các dòng log bắt đầu bằng `[ERROR]` hoặc `[WARN]`, theo sau là mã ba chữ số và một thông điệp. Bỏ qua dòng `INFO`, lấy rõ **mức độ**, **mã** và **nội dung**. Text block giúp diễn giải pattern theo từng dòng, `(?m)` cho phép dùng neo theo dòng, `(?x)` cho phép tách và chú thích pattern.

Lưu tệp tên **`RegexMultilineTextBlockDemo.java`**:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexMultilineTextBlockDemo {
    public static void main(String[] args) {
        String regex = """
                (?mx)
                ^\\h*\\[(?<level>ERROR|WARN)\\]\\h+  # Loai su kien
                (?<code>\\d{3}):\\h*                   # Ma ba chu so
                (?<message>[^\\r\\n]+)$                # Noi dung den het dong
                """;

        String log = """
                INFO 200: Started
                [ERROR] 503: Database unavailable
                [WARN] 429: Retry later
                """;

        Matcher matcher = Pattern.compile(regex).matcher(log);
        while (matcher.find()) {
            System.out.println(
                    matcher.group("level") + "|" +
                    matcher.group("code") + "|" +
                    matcher.group("message")
            );
        }

        System.out.println("default=" +
                Pattern.compile("^ERROR.*$")
                        .matcher("OK\nERROR 1\nOK").find());
        System.out.println("multi=" +
                Pattern.compile("(?m)^ERROR.*$")
                        .matcher("OK\nERROR 1\nOK").find());
        System.out.println("dotall0=" +
                Pattern.compile("^start.*end$")
                        .matcher("start\nend").matches());
        System.out.println("dotall1=" +
                Pattern.compile("(?s)^start.*end$")
                        .matcher("start\nend").matches());

        // Java \s la mot dau cach; regex \\s moi la nhom whitespace.
        String wrong = """
                A\s+B""";
        String right = """
                A\\s+B""";

        System.out.println("wrong=" +
                Pattern.compile(wrong).matcher("A\tB").matches());
        System.out.println("right=" +
                Pattern.compile(right).matcher("A\tB").matches());

        System.out.println("linebreak=" +
                Pattern.compile("A\\RB\\RC")
                        .matcher("A\r\nB\nC").matches());

        System.out.println("wholeAnchor=" +
                Pattern.compile("\\AERROR")
                        .matcher("ok\nERROR").find());

        String replacement = "$1\\backup";
        System.out.println("literalReplacement=" +
                Pattern.compile("(?m)^PATH=.*$")
                        .matcher("PATH=old\n")
                        .replaceAll(Matcher.quoteReplacement(replacement))
                        .equals("$1\\backup\n"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 RegexMultilineTextBlockDemo.java
java RegexMultilineTextBlockDemo
```

Đầu ra:

```text
ERROR|503|Database unavailable
WARN|429|Retry later
default=false
multi=true
dotall0=false
dotall1=true
wrong=false
right=true
linebreak=true
wholeAnchor=false
literalReplacement=true
```

Tại sao pattern chính hoạt động?

1. `(?mx)` bật cả neo theo từng dòng và chế độ bỏ qua khoảng trắng/chú thích của regex.
2. `^\\h*` trong **mã nguồn Java** tạo regex `^\h*`: bắt đầu một dòng, cho phép không hoặc nhiều ký tự khoảng trắng **ngang** như space/tab.
3. `\\[` và `\\]` tạo regex `\[`, `\]` để khớp **dấu ngoặc vuông thật**. Nếu không escape, `[ ... ]` trong regex mang nghĩa lớp ký tự.
4. `(?<level>ERROR|WARN)` là nhóm bắt **có tên**; `matcher.group("level")` lấy giá trị trong dòng phù hợp.
5. `\\h+` tạo regex `\h+` để khớp ít nhất một khoảng trắng ngang; `(?<code>\\d{3})` lấy đúng ba chữ số ASCII hay Unicode theo các cờ regex đang dùng.
6. `(?<message>[^\\r\\n]+)$` lấy một hoặc nhiều ký tự **không phải CR/LF** đến cuối dòng. Dấu `$` làm điểm kết thúc dòng nhờ `(?m)`. Mẫu này không tự loại dấu cách cuối thông điệp; nếu cần loại, hãy quy định rõ nghiệp vụ.
7. `matcher.find()` lần lượt tìm các dòng phù hợp trong toàn bộ `log`; vòng lặp dừng khi không tìm thấy kết quả mới.

Đây là ví dụ biểu diễn **văn bản log**, không phải bộ parser hoàn chỉnh cho mọi định dạng log. Nếu thông điệp thực tế có nhiều dòng, mẫu phải được thiết kế riêng để xác định ranh giới một bản ghi; chỉ thêm `(?s)` vào mẫu trên không giải quyết đúng mọi trường hợp.

## 4. Đếm escape đúng: Java source → String runtime → regex engine

Trong **Java string literal** và **Java text block**, một dấu `\` trong giá trị thường phải viết `\\` ở source. Regex engine sau đó lại xem chính dấu `\` trong giá trị ấy là một lệnh regex.

| Mục đích regex | Viết trong Java source (kể cả text block) | `String` mà `Pattern` nhận | Ý nghĩa |
| --- | --- | --- | --- |
| Một hay nhiều chữ số | `\\d+` | `\d+` | Lớp chữ số với `+`. |
| Một hay nhiều khoảng trắng | `\\s+` | `\s+` | Regex whitespace class. |
| Neo ranh giới từ | `\\bJava\\b` | `\bJava\b` | Ranh giới từ hai phía. |
| Một dấu xuống dòng thuộc loại bất kỳ được `\R` hỗ trợ | `\\R` | `\R` | Một chuỗi linebreak, gồm CRLF. |
| Ký tự dấu chấm thật | `\\.` | `\.` | Dấu chấm literal, không phải wildcard `.`. |
| Một backslash thật trong dữ liệu | `\\\\` | `\\` | Regex escape cho một `\` thật. |
| Đầu vào tuyệt đối | `\\A` | `\A` | Neo đầu toàn bộ input. |
| Cuối input tuyệt đối | `\\z` | `\z` | Neo cuối toàn bộ input. |

**Hai lỗi đặc biệt đáng nhớ trong Java 15+:**

- Viết `\s` **một dấu backslash** trong source là **escape Java hợp lệ** biểu diễn **một dấu cách U+0020**. Pattern nhận được dấu cách, **không nhận được regex `\s`**. Muốn regex whitespace phải viết `\\s`.
- Viết `\b` trong source là escape Java tạo ký tự **backspace**, **không phải regex word boundary**. Muốn ranh giới từ phải viết `\\b`.

Các ký hiệu regex khác như `\d` hoặc `\R` nếu gõ một backslash trong source thường gây lỗi biên dịch `illegal escape character`, vì chúng không phải escape Java hợp lệ. Vì vậy **quy tắc nhất quán là: khi muốn regex engine nhìn thấy một dấu `\`, hãy viết `\\` trong Java source**.

### 4.1. Minh họa bẫy `\s`

Ví dụ đã có trong chương trình trên:

```java
String wrong = """
        A\s+B""";   // String runtime: "A +B"

String right = """
        A\\s+B""";  // String runtime: "A\\s+B"

System.out.println(
        Pattern.compile(wrong).matcher("A\tB").matches()
); // false

System.out.println(
        Pattern.compile(right).matcher("A\tB").matches()
); // true
```

Ở `wrong`, `+` của regex lặp dấu **space literal**, không thể khớp tab trong `"A\tB"`. Ở `right`, regex thực sự là `A\s+B`, nên lớp whitespace khớp tab.

Nếu dùng `(?x)`, dấu cách không escape trong **pattern** còn có thể bị bỏ qua; điều đó làm lỗi `\s` một backslash càng khó quan sát. Hãy so sánh các giá trị thực với `System.out.println`, `length()` hay phép duyệt ký tự khi nghi ngờ ký tự ẩn.

### 4.2. Bẫy `\b` và biểu thức khớp từ

```java
String good = """
        \\bJava\\b""";

String bad = """
        \bJava\b""";

System.out.println(
        Pattern.compile(good).matcher("Java 15").find()
); // true

System.out.println(
        Pattern.compile(bad).matcher("Java 15").find()
); // false
```

Trong `good`, regex engine thấy ranh giới từ `\b`. Trong `bad`, Java đã thay `\b` bằng ký tự backspace trước khi regex được biên dịch. `\b` trong Java source và `\b` trong regex là **hai bộ luật khác nhau ở hai giai đoạn khác nhau**.

### 4.3. Backslash thật và ký tự regex đặc biệt

Ví dụ, dữ liệu chứa `C:\logs` có backslash thật. Một regex để khớp backslash phải dùng `\\` ở tầng regex; vì vậy trong mã nguồn Java cần `\\\\`:

```java
import java.util.regex.Pattern;

String actualText = "C:\\logs";
String regexForBackslash = """
        \\\\""";

System.out.println(
        Pattern.compile(regexForBackslash).matcher(actualText).find()
); // true
```

Nếu mục tiêu chỉ là tìm một đoạn **văn bản cố định**, không cần tự escape từng metacharacter. Dùng `Pattern.quote`:

```java
String needle = "[ERROR] C:\\logs";
Pattern literalSearch = Pattern.compile(Pattern.quote(needle));

System.out.println(
        literalSearch.matcher("[ERROR] C:\\logs").find()
); // true
```

`Pattern.quote` nhận **giá trị runtime đã có**, không nhận cú pháp Java source. Hàm này trích dẫn toàn bộ chuỗi làm regex literal, hữu ích khi người dùng nhập các ký tự `.`, `*`, `[`, `\` mà bạn muốn tìm đúng nguyên văn.

## 5. Các xuống dòng xuất hiện ở hai chỗ khác nhau

### 5.1. Xuống dòng trong **pattern text block**

Khi viết:

```java
String patternText = """
        ^a
        b$""";
```

Giá trị regex chứa một **LF thực** giữa `^a` và `b$`. Pattern này có thể khớp `"a\nb"`, không phải `"ab"`:

```java
System.out.println(
        Pattern.compile(patternText).matcher("a\nb").matches()
); // true
```

Nếu mục tiêu chỉ là trình bày *cùng một regex* trên nhiều dòng, hãy dùng `(?x)` / `Pattern.COMMENTS`, hoặc tự xây chuỗi không mang LF giữa các đoạn theo cách rõ ràng. `(?m)` **không** tự bỏ các xuống dòng bên trong văn bản pattern.

Lưu ý cách đóng text block:

```java
String trailingLf = """
        \\d+
        """;

String noTrailingLf = """
        \\d+""";

System.out.println(trailingLf.endsWith("\n"));   // true
System.out.println(noTrailingLf.endsWith("\n")); // false
```

Dấu đóng `"""` ở dòng riêng thường giữ **LF cuối** trong `String`; đặt dấu đóng ngay sau ký tự cuối để không tạo LF cuối. LF đó có thể làm một regex đơn giản không dùng `(?x)` khác đi. Trong `COMMENTS` mode, LF được xử lý theo luật whitespace/comment của pattern.

### 5.2. Xuống dòng trong **dữ liệu cần khớp**

Text block chuẩn hóa dấu kết thúc dòng **trong chính mã nguồn** về LF; dữ liệu ngoài thực tế có thể chứa CRLF, LF, CR hoặc những dấu kết thúc dòng Unicode khác. Nếu muốn khớp **một chuỗi kết thúc dòng** linh hoạt, regex Java có `\R`:

```java
import java.util.regex.Pattern;

String mixed = "A\r\nB\nC";
boolean same = Pattern.compile("A\\RB\\RC")
        .matcher(mixed).matches();

System.out.println(same); // true
```

`\R` có thể nhận CRLF như **một chuỗi linebreak** và nhiều loại dấu kết thúc dòng khác. Khi viết trong Java source, phải dùng `\\R`.

Nếu regex muốn lấy **nội dung một dòng** mà không ăn sang CR/LF, có thể dùng `[^\\r\\n]+` trong Java source. Biểu thức này chặn rõ CR và LF; nếu đầu vào cần hỗ trợ **mọi** dấu kết thúc dòng Unicode, hãy thiết kế và kiểm thử bộ phân tách phù hợp, không tự suy ra rằng `[^\r\n]` bao phủ hết mọi trường hợp.

Với chuỗi đọc từ tệp hoặc socket, **không** tùy tiện thay CRLF bằng LF nếu định dạng giao thức yêu cầu giữ chính xác ký tự gốc.

### 5.3. `\A` / `\z` khi cần kiểm tra toàn bộ nội dung

Nếu cần chắc chắn pattern khớp **từ đầu đến cuối toàn bộ dữ liệu**, dùng `Matcher.matches()` và thiết kế pattern phù hợp, hoặc neo `\A` và `\z`:

```java
String input = "OK\nERROR";
System.out.println(
        Pattern.compile("(?m)^ERROR").matcher(input).find()
); // true

System.out.println(
        Pattern.compile("\\AERROR").matcher(input).find()
); // false
```

`(?m)^ERROR` tìm thấy `ERROR` ở đầu **dòng thứ hai**; `\AERROR` yêu cầu `ERROR` ở đầu **toàn bộ đầu vào**. Chú ý `$` có quy tắc cho vị trí **trước dấu kết thúc dòng cuối**; khi đòi kết thúc tuyệt đối, `\z` rõ ràng hơn.

## 6. Thay thế nhiều dòng: còn một lớp escape cho replacement

Khi dùng `replaceAll`, Java regex engine đọc hai thông số theo **hai cú pháp khác nhau**:

- Tham số `regex`: quy tắc tìm kiếm như `^`, `\d`, `(?m)`, nhóm bắt `(...)`.
- Tham số `replacement`: `$1`, `$2` tham chiếu nhóm bắt (có thể dùng cú pháp tham chiếu nhóm tên nếu cần), dấu `\` dùng để escape ký tự ở tầng **replacement**. Nó không phải regex pattern thứ hai.

Ví dụ, đổi tên khóa trên từng dòng bằng nhóm bắt:

```java
import java.util.regex.Pattern;

String input = "user=Lan\nuser=Minh\n";
String updated = Pattern.compile("(?m)^user=(.+)$")
        .matcher(input)
        .replaceAll("name=$1");

System.out.print(updated);
```

Đầu ra:

```text
name=Lan
name=Minh
```

Nếu muốn replacement là **văn bản literal** chứa `$` và `\`, hãy dùng `Matcher.quoteReplacement` để tránh các ký tự đó bị hiểu thành tham chiếu nhóm hay escape:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String replacement = "$1\\backup"; // Runtime: $1\backup
String result = Pattern.compile("(?m)^PATH=.*$")
        .matcher("PATH=old\n")
        .replaceAll(Matcher.quoteReplacement(replacement));

System.out.println(result.equals("$1\\backup\n")); // true
```

Nếu bỏ `quoteReplacement`, `$1` trong replacement có thể được hiểu là yêu cầu lấy **nhóm bắt thứ nhất** (và gây lỗi nếu không có nhóm); backslash cũng được hiểu theo luật replacement. **Không tự escape bằng những lần `replace` chồng chéo** khi `Matcher.quoteReplacement` đã giải quyết đúng ý định chèn literal.

Tương tự, khi biến một chuỗi runtime thành regex chỉ để tìm **nguyên văn**, dùng `Pattern.quote`. Hai hàm này phục vụ **hai tham số và hai lớp phân tích khác nhau**:

| Dữ liệu muốn giữ literal | Dùng hàm | Chỗ áp dụng |
| --- | --- | --- |
| Văn bản cố định có ký tự đặc biệt, dùng làm mẫu tìm kiếm | `Pattern.quote(text)` | Regex `pattern`. |
| Văn bản có ký tự `$` hoặc `\`, dùng làm chuỗi thay thế | `Matcher.quoteReplacement(text)` | Regex `replacement`. |

## 7. Cách viết và kiểm thử regex nhiều dòng trong dự án thật

1. **Xác định đơn vị khớp:** một dòng, một khối nhiều dòng hay toàn bộ đầu vào. Nếu cần từng dòng, dùng `(?m)^...$` với `find()` hoặc tách dòng có chủ đích; nếu cần khối, thiết kế ranh giới khối rồi cân nhắc `DOTALL`.
2. **Viết giá trị regex trước:** trên giấy, hãy xác định regex engine phải nhận gì, chẳng hạn `^\d{3}\s+\w+$`. Sau đó mới thêm escape Java: `^\\d{3}\\s+\\w+$`.
3. **Chọn cách trình bày source:** pattern ngắn có thể dùng `"..."`; pattern nhiều dòng kèm chú thích dùng text block với `(?x)`. Không coi text block là raw string.
4. **Quản lý xuống dòng:** phân biệt xuống dòng thuộc source text block, xuống dòng nằm trong regex runtime, và xuống dòng thật trong dữ liệu. Kiểm tra đặc biệt LF cuối do vị trí đóng `"""`.
5. **Dùng đúng API:** `Pattern.compile` một lần khi tái sử dụng; mỗi lần so khớp lấy `Matcher` tương ứng. Dùng `find()` để tìm đoạn phù hợp, `matches()` để kiểm tra toàn vùng.
6. **Thử ít nhất các trường hợp biên:** không có dòng phù hợp, có nhiều dòng phù hợp, dòng đầu/cuối, CRLF, tab, khoảng trắng thừa, thông điệp rỗng, dấu `#`/`\` trong dữ liệu, và đoạn đầu vào rất dài.
7. **Cảnh giác regex tốn tài nguyên:** lặp lồng nhau mơ hồ như `(a+)+` hoặc `.*` quá rộng có thể gây backtracking tốn kém trên dữ liệu lớn hay không tin cậy. Giới hạn phạm vi, dùng lớp ký tự và ranh giới rõ, đo hiệu năng nếu xử lý log lớn.
8. **Tách dữ liệu khỏi regex động:** nếu người dùng nhập từ khóa cần tìm nguyên văn, truyền qua `Pattern.quote` thay vì ghép thẳng vào regex; nếu họ nhập replacement literal, truyền qua `Matcher.quoteReplacement`.

Các bài kiểm thử nên so sánh **giá trị đầu ra thực tế** với chuỗi kỳ vọng, ví dụ:

```java
String expected = """
        ERROR|503|Database unavailable
        WARN|429|Retry later
        """;

String actual = /* chuỗi tích lũy từ matcher.find() */ "";

System.out.println(expected.equals(actual)); // Chỉ true nếu kết quả khớp
```

Đây là **mã minh họa cách so sánh**: thay giá trị `actual` bằng kết quả thật cần kiểm thử. Khi viết unit test, dùng JUnit `assertEquals(expected, actual)` sẽ báo lệch nội dung rõ hơn. Không xem chuỗi `actual` minh họa rỗng là kết quả đã kiểm thử.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Regex source có `\d`, `\R` và Java báo `illegal escape character` | Đang dùng cú pháp regex trực tiếp như escape Java. | Viết `\\d`, `\\R` trong source. |
| `\s` trong text block chỉ khớp dấu cách, không khớp tab | `\s` đã được Java biến thành U+0020 trước khi tạo Pattern. | Viết `\\s` để regex nhận `\s`. |
| `\bword\b` không bắt được ranh giới từ | Java source `\b` là backspace. | Viết `\\bword\\b`. |
| Dùng `(?m)` nhưng `.` vẫn không đi qua xuống dòng | `MULTILINE` không phải `DOTALL`. | Dùng `(?s)` nếu **thật sự** cần dấu `.` khớp newline. |
| Chia pattern trên nhiều dòng text block và bỗng không khớp | Các LF trong text block trở thành ký tự regex. | Dùng `(?x)` / `Pattern.COMMENTS` hoặc chủ động tạo pattern một dòng. |
| Đặt dấu đóng text block ở dòng riêng, pattern nhận thêm LF cuối | Vị trí dấu đóng quyết định LF cuối giá trị. | Đặt dấu đóng trên dòng cuối nội dung khi cần không có LF cuối. |
| Pattern có `(?m)^...$` nhưng `matches()` vẫn `false` | `matches()` đòi khớp toàn đầu vào. | Dùng `find()` để tìm từng dòng; `matches()` cho kiểm tra cả đầu vào. |
| Dùng `(?x)` rồi không khớp dấu cách hoặc `#` literal | `COMMENTS` bỏ qua whitespace và đọc `#` thành comment. | Escape/biểu diễn ký tự rõ ràng, hoặc dùng `Pattern.quote`. |
| Chỉ khớp LF mà không khớp log CRLF | Giả định sai về dấu kết thúc dòng trong dữ liệu thực. | Dùng `\\R` khi cần linebreak linh hoạt và kiểm thử CRLF. |
| `replaceAll` báo lỗi nhóm tham chiếu hoặc mất backslash | `$` và `\` có ý nghĩa riêng ở chuỗi replacement. | Dùng `Matcher.quoteReplacement` khi thay literal. |

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Đoạn `(?m)^ERROR.*$` có thể bắt dòng `ERROR 42` nằm giữa chuỗi nhiều dòng không, và vì sao?

**Đáp án:** Có, khi dùng `find()`. `(?m)` cho `^`, `$` hoạt động tại đầu/cuối từng dòng; nó không yêu cầu khớp toàn bộ đầu vào.

**Câu 2.** Muốn dấu `.` khớp newline, bật `MULTILINE` là đủ?

**Đáp án:** Không. Phải cân nhắc `DOTALL` / `(?s)`. `MULTILINE` chỉ thay đổi neo `^`/`$`.

**Câu 3.** Trong Java 15 text block, `A\s+B` và `A\\s+B` có cùng giá trị runtime không?

**Đáp án:** Không. Mẫu thứ nhất tạo regex tương đương `A +B`, dấu `+` lặp khoảng trắng thường; mẫu thứ hai tạo regex `A\s+B` với lớp whitespace.

**Câu 4.** Regex source đặt nhiều dòng rồi có thêm `(?x)` có phải luôn giữ nguyên ý nghĩa khoảng trắng mong muốn không?

**Đáp án:** Không. `COMMENTS` bỏ qua khoảng trắng không escape trong pattern và dùng `#` cho comment. Cần escape/biểu diễn rõ ký tự thực sự muốn khớp.

**Câu 5.** Khi người dùng nhập literal `$1\backup` để thay toàn bộ nội dung một dòng bằng chuỗi đó, có nên đưa trực tiếp vào `replaceAll` không?

**Đáp án:** Không. Hãy dùng `Matcher.quoteReplacement(userText)` để giữ nguyên dấu `$` và backslash.

## Ghi nhớ

- **Text block là cú pháp viết `String`, không phải regex raw string.** Các escape Java vẫn được xử lý trước `Pattern`.
- **`(?m)` cho neo theo dòng; `(?s)` cho dấu chấm đi qua xuống dòng; `(?x)` cho regex nhiều dòng có khoảng trắng/chú thích.** Các cờ phục vụ những mục đích độc lập.
- **Regex `\d`, `\s`, `\b`, `\R` phải đi qua lớp escape Java**: trong source thường viết `\\d`, `\\s`, `\\b`, `\\R`.
- **Xuống dòng nằm trong pattern và xuống dòng nằm trong dữ liệu là hai vấn đề khác nhau.** Kiểm tra LF cuối text block, CRLF trong dữ liệu và cách dùng `find()`/`matches()`.
- Với dữ liệu literal, `Pattern.quote` bảo vệ **pattern**; `Matcher.quoteReplacement` bảo vệ **replacement**.
- Viết ví dụ đơn giản, chạy và đối chiếu output thật, rồi mới tăng độ phức tạp của regex.

### Tài liệu chính thức còn hiệu lực

- [Oracle Java — Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): cú pháp, xuống dòng, lề, xử lý escape của text block.
- [Java SE — Pattern](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html): `MULTILINE`, `DOTALL`, `COMMENTS`, các lớp ký tự, `\R`, neo, `Pattern.quote`.
- [Java SE — Matcher](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Matcher.html): `find`, `matches`, các nhóm bắt, `replaceAll`, `quoteReplacement`.
- [Java Language Specification — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): cách hình thành giá trị text block từ mã nguồn Java.
