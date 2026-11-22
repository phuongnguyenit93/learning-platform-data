# Phân biệt định dạng chuỗi với nội suy biến tự động trong Java

## Mục tiêu

Khi thấy một chuỗi nhiều dòng như `"""..."""`, nhiều người học Java dễ liên tưởng đến chuỗi template của JavaScript hoặc Python: viết tên biến vào chuỗi là giá trị sẽ tự được chèn vào. **Java text block không hoạt động như vậy.** Text block chỉ là một cách viết **giá trị `String`**, không tự tìm, đánh giá hoặc thay thế biến trong nội dung.

Nếu muốn kết hợp văn bản cố định với dữ liệu đang có ở runtime, Java cung cấp các cách **tường minh** như phép nối chuỗi `+`, `String.format(...)`, `String.formatted(...)`, `StringBuilder` và `MessageFormat`. Mỗi cách có cú pháp, mục đích và quy tắc xử lý khác nhau.

Sau bài này, bạn sẽ:

- Phân biệt **string literal/text block** với **định dạng chuỗi (formatting)** và **nội suy biến tự động (automatic interpolation)**.
- Giải thích vì sao `${name}`, `{name}` hay `%s` nằm trong một text block **không tự thay thành giá trị biến**.
- Dùng `String.formatted(...)` trên text block và `String.format(Locale, ...)` một cách chính xác.
- Hiểu các format specifiers phổ biến (`%s`, `%d`, `%.2f`, `%%`, `%n`), thứ tự đối số, locale và lỗi khi kiểu tham số không phù hợp.
- Chọn `+`, `StringBuilder`, `Formatter`/`formatted` hoặc `MessageFormat` đúng nhu cầu; không nhầm formatting với escape cho JSON/HTML/SQL.
- Nhận diện cú pháp String Templates từng ở giai đoạn preview nhưng **không phải cú pháp Java chuẩn đang sử dụng**.
- Biên dịch/chạy ví dụ Java 17 và dự đoán chính xác đầu ra.

**Phạm vi phiên bản hiện hành:** Text blocks là tính năng **chính thức từ Java 15** ([JEP 378](https://openjdk.org/jeps/378)); `String.formatted(Object...)` cũng có từ Java 15. Bài học sử dụng cú pháp **Java 17 trở lên**, không dùng flag preview hoặc API đã lỗi thời. Phần lưu ý về String Templates chỉ giúp tránh nhầm với một thử nghiệm đã bị rút lại.

## 1. Ba khái niệm khác nhau

### 1.1. String literal và text block: khai báo văn bản

~~~java
String simple = "Hello, world!";

String multiline = """
    Hello, world!
    Welcome to Java.
    """;
~~~

Đây là **mã minh họa** với hai biến `String`. Text block cho phép ghi văn bản nhiều dòng bằng bộ dấu `"""`, tự xử lý incidental indentation và line terminators theo quy tắc của ngôn ngữ.

Text block **không** có cơ chế tự đánh giá các expression viết bên trong dấu `"""`. Đối với compiler, nhiều ký hiệu trông như placeholder chỉ là **ký tự bình thường**.

~~~java
String name = "Linh";

String text = """
    Hello, ${name}!
    """;
~~~

Giá trị của `text` là `"Hello, ${name}!\n"`, **không phải** `"Hello, Linh!\n"`. Cặp ký tự `${` và `}` không có ý nghĩa nội suy trong Java String hoặc text block chuẩn.

### 1.2. Formatting: áp dụng một mẫu với các đối số do lập trình viên truyền

~~~java
String name = "Linh";
int count = 3;

String text = """
    Hello, %s!
    Count: %d
    """.formatted(name, count);
~~~

Đây là **mã minh họa bên trong phương thức**, dùng Java 17+.

Quy trình diễn ra theo hai bước có thể phân biệt:

1. Text block tạo một `String` chứa hai format specifiers `%s` và `%d` (cùng các dấu xuống dòng).
2. Lời gọi `.formatted(name, count)` **thực sự thực hiện** định dạng ở runtime và tạo `String` mới: `"Hello, Linh!\nCount: 3\n"`.

Không gọi `formatted(...)` hoặc `format(...)` thì `%s` và `%d` chỉ là văn bản bình thường.

### 1.3. Automatic interpolation: giá trị expression nằm trực tiếp trong cú pháp literal

Ở một số ngôn ngữ, literal có cú pháp cho phép tham chiếu biến/expression ngay trong chuỗi và biểu thức được đánh giá tự động. **Java text block chuẩn không làm việc này.**

Vì vậy, khi nói “nội suy biến” trong một bài thực hành Java, cần xác định đó là:

- Một **lệnh format tường minh**, ví dụ `template.formatted(name)`; hay
- Một **thư viện template** chuyên dụng với bộ giải placeholder và quy tắc riêng; hay
- Một tính năng ngôn ngữ được chuẩn hóa (không nên tự mặc định có chỉ vì thấy mẫu cú pháp của bản preview).

Đừng dùng ba cách gọi này thay cho nhau. `String.formatted` là **formatting được gọi bằng phương thức**, không phải compiler tự tìm các biến có tên giống placeholder.

## 2. Điều gì xảy ra với ký hiệu trông như placeholder?

Giả sử trong phương thức có:

~~~java
String user = "Linh";

String s1 = """
    Hello, ${user}!
    """;

String s2 = """
    Hello, {user}!
    """;

String s3 = """
    Hello, %s!
    """;
~~~

Ba biểu thức trên đều là **literal text blocks**. Các ký tự `${user}`, `{user}` và `%s` vẫn nằm trong giá trị chuỗi. Không có lệnh nào đang gọi `formatted` hay template engine; tên biến `user` bên ngoài không bị đọc.

Chỉ khi thực hiện bước định dạng, ví dụ:

~~~java
String s4 = """
    Hello, %s!
    """.formatted(user);
~~~

thì `s4` mới mang giá trị `"Hello, Linh!\n"`.

**Điểm dễ nhầm:** `%s` có ý nghĩa **khi được `Formatter` phân tích trong một lệnh định dạng**. Compiler Java không nhìn một `%s` trong literal rồi tự quyết định giá trị nào phải đi vào đó. `${user}` cũng không phải syntax của `String.formatted(...)`.

## 3. `String.formatted(...)` với text block

`String.formatted(Object... args)` là phương thức instance của `java.lang.String`, được thêm ở Java 15. Theo tài liệu JDK, lời gọi:

~~~java
String output = template.formatted(arg1, arg2);
~~~

tương đương về cách format với:

~~~java
String output = String.format(template, arg1, arg2);
~~~

Đây là **hai đoạn minh họa**, giả sử `template`, `arg1` và `arg2` đã khai báo.

### 3.1. Cú pháp phổ biến

~~~java
String name = "Linh";
int lessons = 3;

String message = """
    Student: %s
    Completed lessons: %d
    """.formatted(name, lessons);
~~~

Kết quả:

~~~text
Student: Linh
Completed lessons: 3
~~~

Chuỗi thực tế có thêm một ký tự `\n` ở cuối vì closing delimiter `"""` nằm trên dòng riêng.

**Hai dấu `%` đầu vào theo thứ tự xuất hiện** quyết định cách các tham số được chọn: `%s` lấy `name`, `%d` lấy `lessons`. Nếu đổi thứ tự truyền đối số mà không chỉnh specifiers, có thể tạo nội dung sai hoặc ném exception khi kiểu không tương thích.

### 3.2. Đặt gọi phương thức ngay sau closing delimiter

~~~java
String title = "Guide";

String header = """
    <h1>%s</h1>
    """.formatted(title);
~~~

Dấu `"""` kết thúc literal. Phần `.formatted(title)` là **lời gọi trên String do literal tạo ra**, không phải một phần nội dung text block.

Text block vẫn xử lý newline/indentation trước. `formatted(...)` nhận **chuỗi sau khi xử lý** làm format string rồi điền các đối số. Vì vậy, nếu bạn cần loại newline cuối, có thể đặt closing delimiter cuối dòng nội dung hoặc xử lý chuỗi có chủ đích; bản thân `formatted(...)` **không tự xóa** LF cuối.

### 3.3. Formatting không thay đổi text block ban đầu

`String` trong Java là **immutable**. Phương thức `formatted(...)` trả về **chuỗi mới**, không thay đổi giá trị của biến chứa template.

~~~java
String template = "Hello, %s";
String one = template.formatted("Linh");
String two = template.formatted("An");
~~~

Ở đây:

- `template` vẫn là `"Hello, %s"`.
- `one` là `"Hello, Linh"`.
- `two` là `"Hello, An"`.

Điều này cho phép giữ một mẫu cố định để dùng cho nhiều giá trị, miễn là mẫu ấy đáng tin cậy và đúng loại conversion.

## 4. Format specifiers và kiểu dữ liệu

`String.formatted(...)` và `String.format(...)` dùng cú pháp `java.util.Formatter`.

| Ký hiệu trong format string | Ý nghĩa chính | Ví dụ trong lời gọi |
|---|---|---|
| `%s` | Biểu diễn đối tượng dưới dạng chuỗi (thường dùng `toString`) | `"Hi %s".formatted("Linh")` → `"Hi Linh"` |
| `%d` | Số nguyên dạng thập phân; yêu cầu kiểu đối số tương thích | `"Count=%d".formatted(3)` → `"Count=3"` |
| `%f` | Số dấu phẩy động dạng decimal theo quy tắc Formatter | `String.format(Locale.US, "%.2f", 12.5)` → `"12.50"` |
| `%.2f` | Số thực hiển thị hai chữ số sau dấu thập phân; có làm tròn khi định dạng | `"%.2f".formatted(2.345)` (phụ thuộc locale về dấu thập phân) |
| `%2$s` | Tham số **thứ hai** theo chỉ số 1-based, dạng chuỗi | `"%2$s - %1$s".formatted("A", "B")` → `"B - A"` |
| `%%` | Một dấu phần trăm literal trong kết quả | `"100%%".formatted()` → `"100%"` |
| `%n` | Ký tự xuống dòng **theo nền tảng** khi format | `"A%nB".formatted()` |
| `%t...` | Các conversion ngày/giờ của Formatter | Cần đối số và suffix tương ứng, phải đọc Javadoc trước khi dùng |

**Ba điều cần phân biệt:**

1. `%s` **không phải tên biến**. Nó là một conversion type, thường nhận đối số theo vị trí.
2. `%d` không tự ép mọi chuỗi thành số nguyên. Truyền một `String` như `"3"` vào `%d` sẽ ném `IllegalFormatConversionException`; hãy parse/validate đúng kiểu trước.
3. `%%` và `%n` là những escape đặc biệt của **Formatter**, không phải chuỗi Java escape `\n` trong source.

### 4.1. Vì sao dấu `%` có thể gây lỗi?

~~~java
String line = "Progress: 100%% (%s)".formatted("done");
~~~

Đoạn trên tạo ra `"Progress: 100% (done)"`. Nếu muốn dấu `%` làm nội dung literal **trong một format string**, bạn thường phải dùng `%%`.

Ngược lại:

~~~java
String raw = "Progress: 100%";
~~~

chỉ là một string literal bình thường, **không cần viết `%%`**, vì chưa có bước định dạng. Đừng sửa toàn bộ phần trăm thành `%%` khi chỉ muốn lưu văn bản cố định.

### 4.2. Nhiều lần dùng một tham số

~~~java
String result = String.format(
        Locale.US,
        "Product %1$s / ID: %1$s / count: %2$d",
        "BOOK", 3);
~~~

Kết quả `"Product BOOK / ID: BOOK / count: 3"`. Chỉ số `1$`/`2$` giúp **dùng lại hoặc đổi thứ tự** tham số mà không cần truyền trùng. Nếu mẫu dành cho bản địa hóa ở nhiều ngôn ngữ, chỉ số đối số cũng hữu ích vì thứ tự từ trong từng ngôn ngữ có thể khác.

## 5. `String.format(...)` và quy tắc locale

`String.format(String format, Object... args)` dùng locale mặc định cho **hạng mục FORMAT** của môi trường chạy. Điều này làm kết quả của conversion số và ngày/giờ có thể khác theo cấu hình máy.

Ví dụ nếu muốn định dạng số **cố định** với dấu chấm thập phân:

~~~java
import java.util.Locale;

// Đoạn minh họa trong phương thức.
double price = 12.5;
String text = String.format(Locale.US, "Price: %.2f", price);
~~~

Giá trị của `text` là `"Price: 12.50"`. Đặt `Locale.US` **tường minh** giúp kết quả demo/API contract có dấu `.`, không phụ thuộc locale mặc định.

**Phân biệt hai lệnh:**

~~~java
String a = "Price: %.2f".formatted(price);  // locale mặc định
String b = String.format(Locale.US, "Price: %.2f", price); // locale tường minh
~~~

Đây là **mã minh họa**, giả sử `price` đã có kiểu số tương thích. `String.formatted` không có overload nhận `Locale` làm tham số riêng như `String.format(Locale, ...)`. Muốn ràng buộc locale, ưu tiên `String.format(Locale, template, args)`.

**Lưu ý về số tiền:** `%.2f` chỉ là cách trình bày số tại đầu ra. Không dùng `double` và `String.format` để thay cho mô hình số tiền chính xác trong nghiệp vụ; với tiền tệ, có thể cần `BigDecimal`, quy tắc làm tròn, đơn vị tiền và locale phù hợp. Việc “đẹp hai chữ số” không tự đảm bảo toán học trước đó chính xác.

## 6. Nối chuỗi `+` là một thao tác tường minh khác

Đối với vài giá trị đơn giản, phép nối chuỗi giúp mã trực quan:

~~~java
String user = "Linh";
String greeting = "Hello, " + user + "!";
~~~

Kết quả `"Hello, Linh!"`. Java đánh giá `user` như một biểu thức **nằm ngoài string literal**, rồi chuyển nó sang dạng chuỗi cho phép nối. Đây vẫn **không** phải nội suy bên trong literal.

Cần đọc dấu phân cách rõ:

~~~java
// Tên biến xuất hiện trong biểu thức Java bên ngoài dấu nháy:
String correct = "Hello, " + user + "!";

// Các ký tự tên biến nằm bên trong chuỗi, không có phép nối:
String literal = "Hello, ${user}!";
~~~

**Khi nào dùng `+`?** Tốt cho vài phần văn bản đơn giản và dễ đọc. Không nhất thiết thay mọi biểu thức nối chuỗi bằng `formatted` nếu nó làm mẫu rối hơn.

**Khi nào dùng `StringBuilder`?** Nếu phải xây chuỗi qua **vòng lặp/lần thêm từng phần** và cần giảm việc tạo nhiều đối tượng trung gian, có thể dùng:

~~~java
StringBuilder result = new StringBuilder();
result.append("Hello, ");
result.append(user);
result.append('!');
String greeting = result.toString();
~~~

Đây là **mã minh họa** với `user` đã khai báo. Tuy nhiên, trình biên dịch/JVM hiện đại có thể tối ưu phép nối `+`; **đừng thay `+` bằng `StringBuilder` trong mọi nơi** chỉ vì giả định nhanh hơn. Dùng lựa chọn dễ đọc trước, đo hiệu năng khi cần.

## 7. `MessageFormat` khác `String.format`

`java.text.MessageFormat` dùng **mẫu chứa placeholder theo chỉ số trong ngoặc nhọn**, ví dụ `{0}` và `{1}`, thay vì `%s` và `%d`.

~~~java
import java.text.MessageFormat;
import java.util.Locale;

// Đoạn minh họa trong phương thức.
MessageFormat format = new MessageFormat(
        "{0} has {1,number,integer} items", Locale.US);
String message = format.format(new Object[]{"Linh", 3});
~~~

Kết quả: `"Linh has 3 items"`.

Một số điểm khác biệt:

- `{0}`, `{1}` là **vị trí đối số của MessageFormat**, không phải tên biến Java.
- `{1,number,integer}` yêu cầu định dạng số theo locale và pattern của `MessageFormat`.
- `MessageFormat` thích hợp khi mẫu thông điệp bản địa hóa có các tham số và thứ tự từ thay đổi.
- Dấu nháy đơn `'` trong pattern của `MessageFormat` có **quy tắc trích dẫn riêng**. Không được copy một chuỗi chứa apostrophe từ người dùng vào pattern rồi giả định tất cả ký tự được giữ nguyên.
- `MessageFormat` khác `String.format` và không đọc `%s`/`%d` theo quy tắc `Formatter`.

**Quan trọng:** Java không tự phát hiện rằng trong text block có `{0}` để chạy `MessageFormat`. Bạn vẫn phải **gọi** `new MessageFormat(pattern, locale).format(args)` hoặc API tương ứng.

## 8. Ví dụ Java 17 chạy đầy đủ

Tạo tệp **`TextBlockFormattingDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public final class TextBlockFormattingDemo {
    static String show(String s) {
        return s.replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String user = "Linh";
        int count = 3;
        double price = 12.5;

        String textBlock = """
                Hello, ${user}!
                Count: %d
                """;
        System.out.println("literal=" + show(textBlock));

        String formatted = """
                Hello, %s!
                Count: %d
                """.formatted(user, count);
        System.out.println("formatted=" + show(formatted));

        String explicit = String.format(
                Locale.US, "Item=%s; price=%.2f", "BOOK", price);
        System.out.println("format=" + explicit);

        String joined = "Hello, " + user + "!";
        System.out.println("joined=" + joined);

        String percent = "Progress 100%% for %s".formatted(user);
        System.out.println("percent=" + percent);

        String reordered = String.format(Locale.US,
                "%2$s: %1$d", count, "items");
        System.out.println("reordered=" + reordered);

        MessageFormat mf = new MessageFormat(
                "{0} has {1,number,integer} items", Locale.US);
        System.out.println("message="
                + mf.format(new Object[]{user, count}));

        try {
            String incorrect = "%d".formatted(user);
            System.out.println(incorrect);
        } catch (java.util.IllegalFormatConversionException ex) {
            System.out.println("badType=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

**Biên dịch và chạy bằng JDK 17 trở lên**:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockFormattingDemo.java
java TextBlockFormattingDemo
~~~

**Đầu ra chính xác đã kiểm chứng:**

~~~text
literal=Hello, ${user}!\nCount: %d\n
formatted=Hello, Linh!\nCount: 3\n
format=Item=BOOK; price=12.50
joined=Hello, Linh!
percent=Progress 100% for Linh
reordered=items: 3
message=Linh has 3 items
badType=IllegalFormatConversionException
~~~

**Giải thích theo từng dòng:**

1. `literal` giữ nguyên `${user}` và `%d`, không đánh giá `user` hoặc `count`.
2. `formatted` thay `%s` bằng `Linh` và `%d` bằng `3` vì lời gọi `.formatted(user, count)` là một bước runtime tường minh.
3. `format` dùng `Locale.US`, nên `%.2f` cho `12.50`.
4. `joined` dùng toán tử `+` và tên biến ở **ngoài** literal.
5. `percent` dùng `%%` để xuất dấu `%` bình thường.
6. `reordered` dùng `%2$s` để lấy đối số thứ hai và `%1$d` để lấy đối số thứ nhất.
7. `message` sử dụng `MessageFormat` với `{0}` và `{1,number,integer}`.
8. `badType` xác nhận `%d` không chấp nhận một `String` bất kỳ thay vì số nguyên tương thích; định dạng sai ném `IllegalFormatConversionException`.

Trong chương trình, `show(...)` chuyển **ký tự LF thực** thành hai ký tự nhìn thấy `\` và `n`. Do đó `\n` trên hai dòng đầu của output là cách biểu diễn dấu xuống dòng **bên trong giá trị `String`**, không có nghĩa code in các biến qua một cơ chế nội suy.

## 9. `String Templates` preview không phải cú pháp được phép mặc định dùng hiện nay

Từng có một đề xuất ngôn ngữ **String Templates** (JEP 430, JEP 459), được thử nghiệm dưới dạng **preview** trong Java 21 và Java 22. Sau khi được đánh giá, tính năng này **bị rút lại**, **không xuất hiện trong JDK 23** và chưa được chuẩn hóa thành cơ chế nội suy của text block ở các bản Java sản xuất hiện đại được đề cập trong bài.

Vì vậy:

- **Không** hướng dẫn người học sử dụng cú pháp preview String Templates như một cú pháp Java 17, Java 21 LTS, Java 25 hay Java hiện đại mặc định.
- **Không** thêm `--enable-preview` chỉ để có cú pháp nội suy tự động từ các bản thử nghiệm cũ.
- Nếu thấy một ví dụ trên mạng với bộ xử lý `STR` hoặc cú pháp đặt expression trong string template, hãy kiểm tra **chính xác JDK, JEP và trạng thái tính năng** của ví dụ trước khi áp dụng.
- Đối với Java 17+ và mã ứng dụng hiện hành, có thể dùng những API **chuẩn, ổn định** như `String.formatted`, `String.format`, `+` hoặc một template engine được dự án chủ động lựa chọn.

Nguồn xác nhận: [Oracle — Significant Changes in JDK 23](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-23.html) và [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html). Việc ghi nhận lịch sử ở đây nhằm **tránh nhầm lẫn**, không phải khuyến nghị dùng chức năng đã bị rút.

## 10. Formatting không thay thế escape/encode theo định dạng đầu ra

Đây là ranh giới quan trọng khi dùng text block làm JSON, HTML hoặc SQL.

### 10.1. JSON: `%s` không tự escape dấu nháy kép

~~~java
// Đoạn minh họa: giả sử user chứa dữ liệu đầu vào bên ngoài.
String json = """
    {"name":"%s"}
    """.formatted(user);
~~~

Nếu `user` chứa `"`, ký tự `\` hoặc newline, thay thế `%s` có thể tạo **JSON sai cú pháp hoặc sai dữ liệu**. `String.formatted` không hứa sẽ escape theo ngữ pháp JSON.

**Nên dùng một thư viện JSON serializer** (ví dụ Jackson/Gson trong những project đã chọn nó) để serialize đối tượng/map. Formatting chỉ thích hợp khi bạn kiểm soát nội dung và đã bảo đảm encoding cho đúng ngữ cảnh.

### 10.2. HTML: `%s` không tự HTML-escape

~~~java
// Đoạn minh họa, không dùng trực tiếp cho dữ liệu người dùng.
String html = "<p>%s</p>".formatted(user);
~~~

Nếu `user` chứa chuỗi HTML hoặc script do người dùng nhập, việc chèn thẳng không có **contextual output encoding** có thể dẫn tới XSS. Hãy dùng template engine/HTML escaping có ngữ cảnh phù hợp; không xem `String.format` như một lớp bảo mật.

### 10.3. SQL: thay thế chuỗi không phải parameter binding

~~~java
// KHÔNG NÊN dùng với dữ liệu người dùng:
String sql = "SELECT * FROM users WHERE name = '%s'"
        .formatted(user);
~~~

Đoạn trên làm dữ liệu tham gia trực tiếp vào văn bản SQL. Nó **không** tạo prepared statement và có nguy cơ SQL injection.

Dùng parameterized query:

~~~java
// Đoạn minh họa trong phương thức có Connection connection.
String sql = "SELECT * FROM users WHERE name = ?";
try (java.sql.PreparedStatement ps =
             connection.prepareStatement(sql)) {
    ps.setString(1, user);
    try (java.sql.ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả; code ứng dụng thật xử lý rs tại đây.
    }
}
~~~

**Lưu ý:** `connection` và `user` là các biến giả định đã tồn tại. Đây không phải chương trình độc lập trong bài. Với SQL động cần thay đổi **định danh** bảng/cột, bind parameter không thay cho identifier; phải kiểm soát tập cho phép bằng danh sách xác thực, không chèn dữ liệu tùy ý.

### 10.4. Không lấy một chuỗi format không tin cậy làm template

~~~java
// Không phù hợp: rawPattern được người dùng quyết định.
String output = String.format(rawPattern, user);
~~~

Nếu dữ liệu điều khiển template có `%`/specifier sai, định dạng có thể ném `IllegalFormatException` hoặc cho ra văn bản không mong muốn. Tách **mẫu do ứng dụng kiểm soát** và **đối số dữ liệu**. Nếu muốn cho người dùng soạn mẫu, cần công cụ template có chính sách escape, giới hạn tính năng và kiểm tra lỗi rõ ràng.

**Phân biệt:** dấu `%` bên trong **giá trị đối số** truyền qua `%s` không bị coi là một format specifier mới. Vấn đề xuất hiện khi dữ liệu không tin cậy được dùng làm **chính format string** hoặc khi kết quả chèn vào môi trường cần escaping riêng.

## 11. Những lỗi phổ biến

| Hiểu nhầm | Hậu quả | Cách đúng |
|---|---|---|
| “Text block sẽ tự thay `${name}`” | Kết quả chứa nguyên placeholder | Dùng `%s` và gọi `.formatted(name)`, hoặc template engine rõ ràng |
| “Viết `%s` vào text block là đã format” | Kết quả vẫn có `%s` | Gọi `formatted(...)` hay `String.format(...)` |
| “`String.formatted` là cú pháp nội suy của compiler” | Hiểu nhầm thời điểm xử lý và lỗi runtime | Xem đó là lời gọi phương thức Java bình thường |
| “`String.formatted` và `String.format(Locale, ...)` luôn như nhau về locale” | Output số/ngày phụ thuộc máy | Dùng overload `Locale` tường minh khi cần kết quả cố định |
| “`%d` sẽ tự parse `"3"` thành 3” | `IllegalFormatConversionException` | Parse và validate thành số trước khi format |
| “`%n` và `\n` luôn giống nhau” | `%n` dựa trên platform, LF là ký tự xác định | Chọn newline theo hợp đồng; test khi nhạy cảm |
| “Dùng `String.formatted` là JSON/HTML/SQL sẽ an toàn” | Payload sai hoặc injection/XSS | Dùng serializer, escaping có ngữ cảnh, prepared statements |
| “Cứ thấy `{0}` thì Java tự biết định dạng” | Pattern giữ nguyên nếu không gọi formatter phù hợp | Dùng `MessageFormat` tường minh |
| “Cứ thấy `100%` là lỗi” | Literal bình thường hợp lệ, lỗi chỉ khi đi qua Formatter | Nếu là format string, viết `100%%` |
| “String Templates preview là tính năng đã chuẩn hóa” | Code không chạy trên JDK hiện đại được giao | Dùng API chuẩn, không dùng tính năng bị rút lại |
| “Text block tự xóa newline cuối sau format” | Snapshot/format output có LF không mong muốn | Kiểm tra closing delimiter và giá trị chuỗi, không đổ lỗi cho `formatted` |
| “Nên dùng `StringBuilder` cho mọi phép nối chuỗi” | Mã dài hơn và dễ mất rõ ràng mà chưa chắc nhanh hơn | Dùng `+` khi đơn giản, builder cho luồng xây lặp lại khi hợp lý |

## 12. Quy trình chọn cách tạo chuỗi động

1. **Văn bản hoàn toàn cố định?** Dùng literal `"..."` hoặc text block `"""..."""` nếu nhiều dòng.
2. **Chỉ một hoặc hai biến, thông điệp ngắn?** Dùng `+` khi rõ ràng.
3. **Mẫu có vị trí cần điền, muốn điều chỉnh padding/số/locale?** Dùng `String.format(Locale, ...)` hoặc `String.formatted(...)` nếu locale mặc định phù hợp.
4. **Mẫu thông điệp bản địa hóa với thứ tự tham số khác nhau?** Xem xét `MessageFormat` hoặc hệ thống i18n của ứng dụng; kiểm tra quoting và locale.
5. **Xây chuỗi theo vòng lặp, nhiều lần append?** Cân nhắc `StringBuilder`; ưu tiên đo hiệu năng ở điểm nóng.
6. **Đầu ra là JSON, HTML, SQL hoặc định dạng có escaping/phân quyền riêng?** Dùng công cụ tạo output chuyên biệt. Formatting không thay thế encode hay bind dữ liệu.
7. **Mẫu đến từ dữ liệu bên ngoài?** Kiểm tra nguồn tin cậy và loại template phù hợp; không tùy tiện đưa nó vào `String.format`.
8. **Kiểm thử trước khi triển khai:** phân biệt literal `${name}`, string sau format, newline cuối, locale, kiểu conversion và escaping.

## 13. Bài tự kiểm tra

**Câu 1.** Có biến `String name = "An";`. Đoạn dưới in gì?

~~~java
System.out.println("""
    Hi ${name}
    """);
~~~

**Đáp án:** In `Hi ${name}` và một xuống dòng do text block (ngoài newline do `println`). Không tự thay tên biến thành `An`.

**Câu 2.** Hai biểu thức sau có đồng nghĩa không?

~~~java
String x = "Hello, %s";
String y = "Hello, %s".formatted("An");
~~~

**Đáp án:** Không. `x` là chuỗi chứa nguyên `%s`; `y` là `"Hello, An"`.

**Câu 3.** Điều gì xảy ra với `"%d".formatted("3")`?

**Đáp án:** Ném `IllegalFormatConversionException` vì `%d` không chấp nhận `String` như một đối số số nguyên. Muốn in số nguyên, parse thành `int`/`Integer` rồi truyền số đúng kiểu, hoặc dùng `%s` nếu chỉ muốn biểu diễn văn bản.

**Câu 4.** Muốn kết quả `"Price: 12.50"` giống nhau trên các máy với locale khác nhau thì nên dùng gì?

**Đáp án:** `String.format(Locale.US, "Price: %.2f", 12.5)` hoặc locale xác định theo hợp đồng. `formatted(...)` dùng locale mặc định theo quy tắc Formatter.

**Câu 5.** Vì sao `String.format("{0} has {1} items", name, count)` không phải cách sử dụng đúng pattern `MessageFormat`?

**Đáp án:** Vì `String.format` hiểu format specifiers dạng `%s`/`%d`, không thay `{0}` theo quy tắc `MessageFormat`. Cần gọi API `MessageFormat` tương ứng.

**Câu 6.** Có thể dùng `"SELECT ... name='%s'".formatted(userInput)` để thay prepared statement không?

**Đáp án:** Không. Thay chuỗi không thực hiện SQL parameter binding và có thể dẫn tới SQL injection. Dùng `PreparedStatement` và bind tham số.

**Câu 7.** Nếu một bài blog yêu cầu bật `--enable-preview` để dùng String Templates của Java 21, bạn nên đưa nó thẳng vào bài thực hành Java 17/Java hiện đại không?

**Đáp án:** Không. Đó là cú pháp thử nghiệm đã bị rút lại, không phải tính năng Java chuẩn. Sử dụng API đã chuẩn hóa hoặc thư viện phù hợp với JDK mục tiêu.

## Tài liệu đối chiếu

- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text blocks được chuẩn hóa từ Java 15 và **không trực tiếp hỗ trợ string interpolation**.
- [Oracle Java 17 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): cách tạo text block, newline, indent và `formatted(...)`.
- [Java Language Specification SE 17 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): cú pháp và giá trị của text block.
- [Java SE 17 API — `String.formatted` / `String.format`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): signature, locale, exceptions và mốc thêm `formatted` từ Java 15.
- [Java SE 17 API — `java.util.Formatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html): format specifiers, conversion, argument indexing và lỗi.
- [Java SE 17 API — `java.text.MessageFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): placeholder dạng `{0}`, locale và quy tắc quoting.
- [Oracle — Significant Changes in JDK 23](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-23.html): String Templates đã bị rút sau các bản preview 21/22.
- [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): trạng thái ngôn ngữ qua từng bản phát hành.

**Ghi nhớ:** `"""..."""` **chỉ tạo một `String`**; dấu `${name}` không tự động nội suy biến, và `%s` cũng chỉ là văn bản cho đến khi bạn gọi **`formatted(...)` hoặc `String.format(...)`**. Hãy chọn API định dạng có chủ đích, kiểm soát locale/kiểu đối số và sử dụng serializer/parameter binding khi tạo dữ liệu có ngữ pháp hoặc yêu cầu bảo mật riêng.