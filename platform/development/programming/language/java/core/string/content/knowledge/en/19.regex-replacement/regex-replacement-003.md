# Ý nghĩa đặc biệt của dấu đô la (`$`) và gạch chéo ngược (`\`) khi thay thế bằng regex trong Java

## 1. Vì sao cần hiểu cú pháp chuỗi thay thế?

Hai phương thức sau có ý nghĩa khác nhau:

~~~java
input.replace("x", replacement);       // Tìm/thay thế chuỗi literal.
input.replaceAll("x", replacement);    // Tìm bằng regex, thay bằng cú pháp replacement.
~~~

Trong `String.replaceAll(regex, replacement)`, tham số `regex` là biểu thức chính quy. Tham số `replacement` không được chèn nguyên xi: `Matcher` **diễn giải** nó theo một cú pháp riêng. Hai ký tự quan trọng nhất là:

- **`$`** mở đầu tham chiếu đến **nhóm bắt** (capturing group), ví dụ `$1`, `$2`, `$0` và `${name}`.
- **`\`** là ký tự **escape trong replacement**: ký tự ngay sau nó được đưa vào kết quả theo nghĩa đen.

Do đó, văn bản cần chèn như `$100` hay `C:\data` có thể bị hiểu sai hoặc gây lỗi nếu truyền trực tiếp làm replacement. Cách khắc phục là escape đúng hoặc dùng `Matcher.quoteReplacement(...)`.

## 2. Phân biệt ba lớp escape

Trong một câu lệnh `replaceAll`, ta phải phân biệt **Java string literal**, **regex pattern** và **replacement**.

| Lớp | Viết trong Java hoặc ở runtime | Ý nghĩa |
| --- | --- | --- |
| Java string literal | `"\\d+"` | Tạo chuỗi runtime `\d+` |
| Regex pattern | `\d+` | Khớp một hoặc nhiều chữ số |
| Java string literal | `"$1"` | Tạo chuỗi runtime `$1` |
| Replacement | `$1` | Chèn giá trị nhóm bắt số 1 |
| Java string literal | `"\\$"` | Tạo chuỗi runtime `\$` |
| Replacement | `\$` | Chèn một ký tự `$` |
| Java string literal | `"\\\\"` | Tạo chuỗi runtime gồm **hai** dấu `\` |
| Replacement | `\\` | Chèn một ký tự `\` |

- **Lớp Java:** dấu `\` dùng để tạo các escape trong mã nguồn như `\n`, `\t`, `\\`. Một dấu gạch chéo ngược runtime phải được biểu diễn bằng `\\` trong Java string literal thông thường.
- **Lớp regex:** dấu `\` mang ý nghĩa trong mẫu tìm kiếm, ví dụ `\d` (chữ số), `\b` (word boundary), `\.` (dấu chấm thật). Đây là luật của **tham số thứ nhất**.
- **Lớp replacement:** dấu `\` escape ký tự tiếp theo, còn `$` mở đầu tham chiếu nhóm. Đây là luật của **tham số thứ hai**.

Ví dụ:

~~~java
String result = "a1b2".replaceAll("\\d", "\\$");
System.out.println(result);
~~~

Đầu tiên, Java biến literal `"\\d"` thành regex `\d` và `"\\$"` thành replacement runtime `\$`. Regex khớp mỗi chữ số, còn replacement parser chuyển `\$` thành dấu `$`. Kết quả: `a$b$`.

## 3. Dấu đô la `$` và tham chiếu nhóm bắt

### 3.1. `$1`, `$2` và `$0`

Trong regex, mỗi cặp ngoặc tròn bắt `(...)` tạo một nhóm. Các nhóm được đánh số từ `1` theo thứ tự dấu ngoặc mở; `(?:...)` là nhóm **không bắt** nên không tăng số. `$0` là toàn bộ phần khớp (tương tự `Matcher.group(0)`).

~~~java
String value = "Mã AB-123";
String result = value.replaceAll(
        "([A-Z]{2})-(\\d+)",
        "$2/$1"
);
System.out.println(result);
~~~

Kết quả:

~~~text
Mã 123/AB
~~~

Ở đây nhóm `1` là `AB`, nhóm `2` là `123`. Chuỗi thay thế `$2/$1` đảo vị trí hai nhóm; phần văn bản không khớp vẫn giữ nguyên.

~~~java
System.out.println("a1b2".replaceAll("\\d", "[$0]"));
~~~

Kết quả: `a[1]b[2]`. Vì mẫu `\d` không khai báo nhóm bắt phụ, dùng `$1` trong ví dụ này là sai, còn `$0` vẫn hợp lệ.

Nếu một nhóm tùy chọn có khai báo nhưng **không tham gia** một lần khớp, tham chiếu đến nhóm đó tạo chuỗi rỗng. Nếu **chỉ số nhóm không tồn tại**, phép thay thế sẽ báo lỗi lúc replacement được xử lý.

### 3.2. Nhóm bắt có tên và `${name}`

Java hỗ trợ khai báo nhóm bằng `(?<name>...)` trong regex và lấy giá trị bằng `${name}` trong replacement:

~~~java
String result = "cat:42".replaceAll(
        "(?<animal>[a-z]+):(?<count>\\d+)",
        "${count}/${animal}"
);
System.out.println(result);
~~~

Kết quả: `42/cat`.

`${animal}` là cú pháp **replacement**, không phải biến Java hay interpolation. Tên nhóm không khai báo sẽ gây lỗi.

### 3.3. `$` đứng một mình không phải dấu đô la literal

Những cách dùng sau là replacement không hợp lệ khi regex có phần khớp:

~~~java
"a1".replaceAll("\\d", "$");          // Thiếu chỉ số hoặc tên nhóm.
"a1".replaceAll("\\d", "${missing}"); // Không có nhóm tên missing.
~~~

Nếu muốn chèn chính ký tự `$`, hãy escape ở **replacement** hoặc dùng `Matcher.quoteReplacement`.

## 4. Gạch chéo ngược `\` trong replacement

### 4.1. Chèn một ký tự `$` theo nghĩa đen

Replacement runtime phải chứa `\$`, tức là dấu `\` rồi tới `$`. Để tạo chuỗi đó trong **Java source**, dùng `"\\$"`:

~~~java
System.out.println("a1b2".replaceAll("\\d", "\\$"));
~~~

Kết quả: `a$b$`.

Viết `"$"` sẽ bị hiểu là tham chiếu nhóm không hoàn chỉnh. Viết trực tiếp `"\$"` trong **Java source** cũng không hợp lệ vì Java không có escape `\$`. Cần hai dấu `\` trong string literal.

### 4.2. Chèn một ký tự gạch chéo ngược thật

Replacement runtime cần hai dấu `\` liền nhau, tức `\\`, để giải mã thành **một** dấu `\` trong output. Trong Java source phải viết tổng cộng **bốn dấu** `"\\\\"`:

~~~java
System.out.println("a1b2".replaceAll("\\d", "\\\\"));
~~~

Output gồm các ký tự `a`, `\`, `b`, `\`:

~~~text
a\b\
~~~

`System.out.println` in dấu gạch chéo ngược thật; nó không in thêm dấu để trình bày escape như cách một số debugger thể hiện Java string.

### 4.3. Khi `\` gây lỗi hoặc làm mất dữ liệu

Một replacement runtime kết thúc bằng **một** ký tự `\` chưa escape ký tự nào phía sau nên không hợp lệ khi được dùng để thay thế. Ký hiệu regex `\d` không còn có nghĩa “chữ số” trong replacement; tại đây, `\d` khiến parser chèn ký tự `d`. Tương tự, nếu bạn truyền đường dẫn Windows làm replacement mà không quote, dấu `\` trong đường dẫn có thể bị bỏ khi được hiểu là escape.

Vì thế, nếu chuỗi thay thế là **dữ liệu thông thường**, nên dùng `Matcher.quoteReplacement(...)` thay vì cố đoán cách thêm dấu gạch chéo ngược theo vị trí.

## 5. Chương trình Java 17+ đầy đủ và kết quả chạy

Lưu mã thành `RegexReplacementDemo.java`:

~~~java
import java.util.regex.Matcher;

public final class RegexReplacementDemo {
    public static void main(String[] args) {
        String code = "Mã AB-123";
        System.out.println(
                code.replaceAll("([A-Z]{2})-(\\d+)", "$2/$1"));

        String value = "a1b2";
        System.out.println(value.replaceAll("\\d", "[$0]"));
        System.out.println(value.replaceAll("\\d", "\\$"));
        System.out.println(value.replaceAll("\\d", "\\\\"));

        // Văn bản cần chèn có cả '$' và dấu '\'.
        String literal = "$5\\tmp";
        System.out.println(value.replaceAll(
                "\\d", Matcher.quoteReplacement(literal)));

        System.out.println("x$y".replace("$", "USD"));
        System.out.println("x$y".replaceAll("\\$", "USD"));
        System.out.println("x$y".replaceAll("$", "USD"));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 RegexReplacementDemo.java
java RegexReplacementDemo
~~~

`stdout`:

~~~text
Mã 123/AB
a[1]b[2]
a$b$
a\b\
a$5\tmpb$5\tmp
xUSDy
xUSDy
x$yUSD
~~~

Giải thích:

1. `$2/$1` lắp ghép nhóm bắt số `2` và `1` theo thứ tự mới.
2. `$0` là toàn bộ phần khớp.
3. `"\\$"` chèn dấu `$`; `"\\\\"` chèn dấu `\`.
4. `Matcher.quoteReplacement(literal)` giữ nguyên `$5\tmp`. Dòng output có hai ký tự `\` và `t`, **không phải tab**.
5. `String.replace("$", "USD")` thay **ký tự đô la literal**, vì `replace` không hiểu regex.
6. `replaceAll("\\$", "USD")` cũng thay dấu đô la literal, nhưng bằng **regex `\$`**.
7. `replaceAll("$", "USD")` có `$` trong **pattern**. Ở vị trí này `$` là anchor cuối input, nên nó **thêm** `USD` vào sau `x$y`.

## 6. Dữ liệu thay thế động nên được chèn nguyên văn

Với chuỗi do người dùng hoặc dịch vụ khác gửi đến, dùng **Matcher.quoteReplacement(value)** để bảo toàn **$** và dấu gạch chéo ngược. Phương thức này chỉ xử lý **replacement**; nếu chuỗi tìm kiếm cũng là dữ liệu literal, dùng **Pattern.quote(needle)** ở phía regex, hoặc **String.replace** khi không cần regex.

Đừng quote cả template **$2/$1** nếu chủ đích là lấy giá trị nhóm. Bài tiếp theo về quoteReplacement sẽ đi sâu vào dữ liệu động, appendReplacement và những tình huống chỉ quote một phía.

## 7. Lỗi phổ biến cần phân biệt

### Lỗi 1: nhầm `$` trong pattern và replacement

~~~java
System.out.println("a$b".replaceAll("$", "X"));    // a$bX
System.out.println("a$b".replaceAll("\\$", "X"));  // aXb
~~~

`$` trong **pattern** đánh dấu cuối input (hoặc cuối dòng tùy chế độ regex); `$` trong **replacement** mở đầu tham chiếu nhóm.

### Lỗi 2: nghĩ `$1` luôn là văn bản literal

~~~java
String text = "x12y";
System.out.println(text.replaceAll("(\\d+)", "[$1]")); // x[12]y
System.out.println(text.replaceAll(
        "(\\d+)", Matcher.quoteReplacement("[$1]")));  // x[$1]y
~~~

Dòng đầu chèn **nhóm bắt**; dòng sau chèn nguyên xi ký tự `[`, `$`, `1`, `]`.

### Lỗi 3: đếm nhầm số dấu `\`

~~~java
String replacement = "\\\\";
System.out.println(replacement.length());                // 2
System.out.println("x".replaceAll("x", replacement).length()); // 1
~~~

Bốn dấu trong **Java source**, hai dấu trong **runtime replacement**, một dấu trong **kết quả**.

### Lỗi 4: dùng regex khi chỉ muốn thay chuỗi

~~~java
String path = "C:\\temp\\data.txt";
System.out.println(path.replace("\\", "/"));
// C:/temp/data.txt
~~~

`String.replace(CharSequence, CharSequence)` thay mọi lần xuất hiện theo nghĩa đen, không diễn giải `$` và `\` theo ngữ pháp replacement của regex. Đây thường là lựa chọn đơn giản hơn khi không cần pattern hay nhóm bắt.

### Lỗi 5: quote sai tham số

~~~java
String text = "a.b";
System.out.println(text.replaceAll(".", "X")); // XXX

String correct = text.replaceAll(
        java.util.regex.Pattern.quote("."),
        java.util.regex.Matcher.quoteReplacement("$")
);
System.out.println(correct); // a$b
~~~

`Pattern.quote(".")` khiến pattern khớp dấu chấm thật thay vì regex “bất kỳ ký tự nào”. `Matcher.quoteReplacement("$")` đảm bảo ký tự đô la được chèn literal.

## 8. Lưu ý nâng cao

- Tham chiếu nhóm số có thể được đọc theo số nhóm **hợp lệ** của pattern: `$10` có thể là nhóm số 10 nếu tồn tại, hoặc nhóm 1 rồi đến ký tự `0` nếu chỉ nhóm 1 hợp lệ. Khi cần ghép chữ số vào sau giá trị nhóm, named group `${name}` làm ý định rõ hơn.
- Các API `Matcher.replaceAll`, `Matcher.replaceFirst`, `Matcher.appendReplacement` cũng dùng ngữ pháp replacement có ý nghĩa đối với `$` và `\`. `String.replaceFirst` chỉ thay lần khớp đầu tiên nhưng có quy tắc cú pháp replacement tương tự.
- Chuỗi replacement sai cú pháp có thể chỉ phát sinh lỗi khi pattern **có phần khớp**. Trường hợp không tìm thấy match không chứng minh replacement hợp lệ.
- Khi sử dụng overload nhận callback để sinh replacement từ từng `MatchResult`, đọc hợp đồng API về cách chuỗi trả về được diễn giải; không giả định rằng nội dung từ callback mặc định là literal.
- Không cần regex để “thay tất cả” chuỗi con cố định: `String.replace` cũng thay **mọi lần khớp literal**.

## 9. Tự kiểm tra

Hãy giải thích vì sao **dấu đô la trong pattern** có thể đánh dấu cuối chuỗi, nhưng **dấu đô la đứng một mình trong replacement** là cú pháp sai khi có match. Sau đó dự đoán kết quả nếu regex tìm chữ số và replacement được viết để xuất đúng một ký tự đô la.

Để debug, kiểm tra ba bước theo thứ tự: Java tạo chuỗi runtime nào, Pattern tìm những vị trí nào, và Matcher diễn giải replacement ra sao. Các ví dụ và kết quả tại mục 5 cho phép đối chiếu từng bước.

