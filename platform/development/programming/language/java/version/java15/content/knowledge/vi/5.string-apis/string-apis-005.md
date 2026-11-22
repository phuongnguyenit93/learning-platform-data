# IllegalFormatException và dữ liệu định dạng không hợp lệ trong Java

Các API `String.format(...)` và `String.formatted(...)` tạo một chuỗi theo **mẫu định dạng** (*format string*). Nếu mẫu có cú pháp không hợp lệ, tham chiếu đến đối số không tồn tại, hoặc dùng kiểu chuyển đổi không tương thích với đối số được cung cấp, Java có thể ném `java.util.IllegalFormatException`.

`String.formatted(Object... args)` được bổ sung từ **Java 15**; `String.format(...)` và `java.util.Formatter` đã có từ trước và vẫn hoạt động trong Java hiện đại. Các ngoại lệ định dạng là kiến thức cần thiết khi dùng API chuỗi hiện nay. Cần phân biệt rõ **lỗi định dạng** với **dữ liệu sai cú pháp hoặc sai quy tắc nghiệp vụ**: mỗi lỗi phát sinh ở một bước khác nhau và có cách xử lý riêng.

## 1. Cơ chế tạo chuỗi có định dạng

Ví dụ hợp lệ:

```java
import java.util.Locale;

String output = String.format(
        Locale.US, "Age: %d; Balance: %,.2f", 24, 12345.5);
// output = "Age: 24; Balance: 12,345.50"
```

`%d` là vị trí cho số nguyên, `%,.2f` là vị trí cho số thực với phân nhóm hàng nghìn và hai chữ số thập phân. Các ký hiệu bắt đầu bằng `%` được gọi là *format specifier*.

Với `String.formatted`, chính chuỗi nhận phương thức là mẫu:

```java
String message = "User: %s, age: %d".formatted("Lan", 24);
// message = "User: Lan, age: 24"
```

`String.formatted(args)` tương đương `String.format(this, args)`. Phiên bản này dùng ngữ cảnh `Locale` mặc định khi biểu diễn những giá trị nhạy với ngôn ngữ/khu vực. Nếu cần dấu phân tách số nhất quán, dùng overload `String.format(Locale, String, Object...)` như ví dụ đầu.

**Lỗi định dạng thường xuất hiện lúc chạy**, khi `Formatter` phân tích mẫu và ghép đối số. Một chương trình có thể biên dịch thành công nhưng vẫn lỗi khi nhận dữ liệu khác với loại mong đợi.

## 2. IllegalFormatException là loại ngoại lệ nào?

`java.util.IllegalFormatException` nằm trong nhánh `RuntimeException → IllegalArgumentException → IllegalFormatException`. Nó là **unchecked exception**: người gọi không bị bắt buộc phải khai báo `throws` hoặc dùng `catch`.

Đây là **lớp cơ sở của nhiều lớp ngoại lệ định dạng cụ thể**, ví dụ:

- `IllegalFormatConversionException`: kiểu đối số không tương thích với conversion.
- `MissingFormatArgumentException`: thiếu đối số được tham chiếu trong mẫu.
- `UnknownFormatConversionException`: ký hiệu chuyển đổi không được hỗ trợ.
- `IllegalFormatPrecisionException`: precision không hợp lệ hoặc không được conversion hỗ trợ.
- `MissingFormatWidthException`: dùng flag cần width nhưng lại thiếu width.
- `FormatFlagsConversionMismatchException`: một flag không phù hợp với conversion.
- `DuplicateFormatFlagsException`: flag bị lặp.

Có thể bắt lớp cha khi cần xử lý chung mọi lỗi định dạng:

```java
import java.util.IllegalFormatException;

try {
    String text = "%d".formatted("24");
    System.out.println(text);
} catch (IllegalFormatException e) {
    System.out.println(e.getClass().getSimpleName());
}
```

Kết quả:

```text
IllegalFormatConversionException
```

`"24"` là `String`, không phải số nguyên. Java không tự gọi `Integer.parseInt` chỉ vì mẫu yêu cầu `%d`. Nếu dùng `%s`, chuỗi `"24"` được hiển thị nguyên văn; nếu cần tính toán số thì phải chuyển đổi và xác thực trước.

## 3. Hiểu cấu trúc format specifier để xác định lỗi

Dạng tổng quát của ký hiệu định dạng thông dụng:

```text
%[argument_index$][flags][width][.precision]conversion
```

Các phần trong dấu ngoặc vuông là tùy chọn. Có thể chỉ rõ vị trí đối số, cờ trình bày, độ rộng, độ chính xác và kiểu chuyển đổi, nhưng **không phải conversion nào cũng chấp nhận mọi flag hay precision**.

| Cú pháp | Ý nghĩa | Đối số ví dụ |
| --- | --- | --- |
| `%s` | Biểu diễn dạng chuỗi của đối tượng | `"Lan"` |
| `%d` | Số nguyên thập phân | `42` |
| `%f` | Số thực | `3.5` |
| `%.2f` | Số thực với hai chữ số thập phân | `3.5` → `3.50` |
| `%04d` | Số nguyên, độ rộng ít nhất 4, thêm số 0 bên trái | `7` → `0007` |
| `%2$d` | Lấy đối số **thứ hai** để in dạng số nguyên | `String.format("%2$d", 7, 8)` → `8` |
| `%%` | Dấu phần trăm thật, không tiêu thụ đối số | `%%` → `%` |
| `%n` | Ký tự xuống dòng theo nền tảng, không tiêu thụ đối số | Dùng trong bản tin nhiều dòng |

Một vài giới hạn cần nhớ:

- `%d` không dùng cho `String` hoặc `double`; `%f` dùng cho kiểu số thực được hỗ trợ như `double`, `float`, `BigDecimal`.
- `%.2d` sai vì conversion `d` **không hỗ trợ precision**. Nếu muốn điền 0 phía trước số nguyên, dùng width và flag `0`, ví dụ `%02d`.
- `%0d` sai vì flag `0` cần một width; `%03d` là ví dụ đúng.
- Chỉ số đối số bắt đầu từ **1**. `%2$d` cần có ít nhất hai đối số, kể cả khi chỉ tham chiếu đối số thứ hai.
- `%%` dùng để in dấu `%` từ mẫu. Một dấu `%` trần trong mẫu có thể dẫn đến lỗi cú pháp.

## 4. Những ví dụ lỗi thường gặp và cách khắc phục

| Câu lệnh | Ngoại lệ | Cách sửa |
| --- | --- | --- |
| `String.format("%d", "12")` | `IllegalFormatConversionException` | Chuyển dữ liệu sang số nguyên hợp lệ hoặc dùng `%s` nếu chỉ hiển thị |
| `String.format("%d %s", 7)` | `MissingFormatArgumentException` | Thêm đối số thứ hai hoặc bỏ specifier thừa |
| `String.format("%2$d", 7)` | `MissingFormatArgumentException` | Dùng `%1$d` hoặc truyền ít nhất hai đối số |
| `String.format("%q", 7)` | `UnknownFormatConversionException` | Thay `q` bằng conversion hợp lệ |
| `String.format("%.2d", 7)` | `IllegalFormatPrecisionException` | Bỏ precision hoặc chuyển sang định dạng thích hợp |
| `String.format("%0d", 7)` | `MissingFormatWidthException` | Ví dụ sửa thành `%03d` |
| `String.format("%#d", 7)` | `FormatFlagsConversionMismatchException` | Bỏ flag `#` |
| `String.format("%--5d", 7)` | `DuplicateFormatFlagsException` | Không lặp flag `-` |

Ngoài những lớp trên, Java còn có `IllegalFormatFlagsException`, `IllegalFormatWidthException`, `IllegalFormatCodePointException` và `UnknownFormatFlagsException`. Khi khắc phục lỗi, hãy xem **tên lớp thực tế**, specifier bị lỗi và **kiểu đối số được truyền**. Không nên chỉ tìm cách sửa một đoạn thông báo `getMessage()` cố định vì nội dung thông báo không phải giao thức xử lý nghiệp vụ.

## 5. Chương trình Java 17+ chạy được và kết quả chính xác

Lưu đoạn mã sau thành file `FormatFailureDemo.java`:

```java
import java.util.IllegalFormatException;
import java.util.Locale;

public class FormatFailureDemo {
    private static void check(String label, String pattern, Object... args) {
        try {
            String value = String.format(Locale.US, pattern, args);
            System.out.println(label + ": OK: " + value);
        } catch (IllegalFormatException e) {
            System.out.println(label + ": " + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        check("type", "%d", "12");
        check("missing", "%d %s", 7);
        check("unknown", "%q", 7);
        check("precision", "%.2d", 7);
        check("width", "%0d", 7);
        check("index", "%2$d", 7);
        check("valid", "Price: %,.2f", 12345.5);

        String formatted = "User: %s, age: %d".formatted("Lan", 24);
        System.out.println("formatted=" + formatted);

        try {
            int parsed = Integer.parseInt("12x");
            System.out.println("parsed=" + parsed);
        } catch (NumberFormatException e) {
            System.out.println("parse: " + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 FormatFailureDemo.java
java FormatFailureDemo
```

Đầu ra (đã chọn `Locale.US` để định dạng số không phụ thuộc máy):

```text
type: IllegalFormatConversionException
missing: MissingFormatArgumentException
unknown: UnknownFormatConversionException
precision: IllegalFormatPrecisionException
width: MissingFormatWidthException
index: MissingFormatArgumentException
valid: OK: Price: 12,345.50
formatted=User: Lan, age: 24
parse: NumberFormatException
```

Hàm `check` cố ý thử các mẫu lỗi rồi bắt lớp cha `IllegalFormatException`, vì vậy chương trình tiếp tục chạy để minh họa toàn bộ trường hợp. Trường hợp `parse` dùng một `catch` khác, bởi `NumberFormatException` xảy ra khi **phân tích dữ liệu đầu vào**, không phải khi xử lý mẫu định dạng. Các tên lớp ngoại lệ và kết quả trong ví dụ đã được đối chiếu với hành vi của JDK hiện đại.

## 6. Phân biệt format sai với dữ liệu sai

### Dữ liệu đầu vào là chữ, mẫu lại cần số

Thông tin từ biểu mẫu, tệp CSV hoặc API thường đến dưới dạng `String`, kể cả khi người dùng nhập chữ số.

Cách sai khi nghiệp vụ đòi tuổi là số nguyên:

```java
String ageText = "27";
String output = "Age: %d".formatted(ageText);
// IllegalFormatConversionException
```

Cách đúng là phân tích và xác thực dữ liệu **trước** khi định dạng:

```java
String ageText = "27";

try {
    int age = Integer.parseInt(ageText);
    if (age < 0 || age > 130) {
        throw new IllegalArgumentException("Tuổi ngoài phạm vi cho phép");
    }
    String output = "Age: %d".formatted(age);
    System.out.println(output); // Age: 27
} catch (NumberFormatException e) {
    System.out.println("Vui lòng nhập số nguyên hợp lệ");
}
```

Trong ví dụ này, phép `parseInt` xác nhận **cú pháp số nguyên**, câu lệnh `if` kiểm tra **quy tắc minh họa của ứng dụng** về khoảng tuổi, và `formatted` chỉ trình bày một giá trị đã được kiểm tra. Quy tắc 0–130 do ứng dụng đặt ra, không phải một giới hạn của Java.

Nếu chỉ muốn hiển thị nguyên văn chuỗi người dùng nhập, dùng `%s` là hợp lý:

```java
String ageText = "27x";
String output = "Input: %s".formatted(ageText);
// output = "Input: 27x"
```

Nhưng nếu cần thực sự tính toán hoặc lưu một tuổi hợp lệ, **đổi `%d` thành `%s` không thay thế được việc xác thực dữ liệu**.

### Lỗi parse không phải IllegalFormatException

`Integer.parseInt("27x")` ném `NumberFormatException`, còn `String.format("%d", "27x")` ném `IllegalFormatConversionException`. Hai thao tác thất bại ở hai thời điểm khác nhau:

```text
Chuỗi đầu vào
    |
    v
Phân tích / xác thực dữ liệu  ---> NumberFormatException hoặc lỗi nghiệp vụ
    |
    v
Giá trị đúng kiểu
    |
    v
Áp dụng mẫu định dạng       ---> IllegalFormatException và các lớp con
    |
    v
Chuỗi kết quả
```

Không nên dùng một `catch (IllegalArgumentException e)` quá rộng cho cả hai bước nếu ứng dụng cần trả thông báo lỗi chính xác; `IllegalFormatException` và `NumberFormatException` đều nằm dưới `IllegalArgumentException`.

## 7. Dùng mẫu định dạng và dữ liệu động một cách an toàn

**Mẫu định dạng** nên là mẫu được ứng dụng kiểm soát, còn **dữ liệu người dùng** là đối số được cung cấp cho mẫu.

```java
String userText = "Discount 20%";
String text = "%s".formatted(userText);
// text = "Discount 20%"
```

Nếu vô tình dùng `userText` làm **mẫu** trong `String.format(userText)`, ký tự `%` bên trong dữ liệu sẽ bị phân tích như một phần của cú pháp định dạng và có thể gây lỗi. Dùng mẫu cố định `%s` khi chỉ cần hiển thị dữ liệu thô.

Khi ứng dụng bắt buộc nhận mẫu từ cấu hình, nên kiểm tra và thử định dạng với kiểu/đủ số lượng đối số đại diện trước khi đưa vào sử dụng. Nếu mẫu không hợp lệ, ghi nhận nguyên nhân và báo lỗi cấu hình phù hợp thay vì âm thầm tạo nội dung sai.

**Đối số thừa chưa chắc gây lỗi**:

```java
String text = String.format("%s", "Lan", 24);
// text = "Lan"; đối số 24 không được dùng
```

`Formatter` có thể bỏ qua đối số không được tham chiếu. Ngược lại, specifier tham chiếu đến đối số không tồn tại gây `MissingFormatArgumentException`. Vì vậy, kiểm tra số lượng và **thứ tự** các đối số khi chỉnh sửa mẫu là cần thiết, kể cả khi chương trình không báo lỗi.

**Locale không đồng nghĩa với định dạng sai**:

```java
String total = String.format(Locale.US, "%,.2f", 12345.5);
// total = "12,345.50"
```

Số thập phân có thể được hiển thị bằng ký hiệu khác khi locale thay đổi; đó có thể là biểu diễn hợp lệ, không phải `IllegalFormatException`. Chỉ định locale khi dữ liệu đầu ra phải nhất quán theo một quy ước cụ thể.

## 8. Khi nào nên bắt IllegalFormatException?

| Bối cảnh | Hướng xử lý |
| --- | --- |
| Mẫu định dạng cố định trong code | Sửa ngay lỗi mẫu, kiểu và số lượng đối số; thêm kiểm thử cho nhánh liên quan |
| Mẫu lấy từ cấu hình được phép thay đổi | Xác thực cấu hình khi nhận và báo lỗi cấu hình rõ ràng nếu mẫu sai |
| Dữ liệu đầu vào từ người dùng hoặc API | Parse, xác thực kiểu và quy tắc nghiệp vụ trước khi định dạng |
| Cần duy trì một luồng xử lý khi format lỗi | Bắt `IllegalFormatException` ở ranh giới phù hợp, ghi lại bối cảnh chẩn đoán cần thiết và xử lý lỗi có chủ đích |

Ví dụ bắt lỗi định dạng tại ranh giới:

```java
import java.util.IllegalFormatException;

try {
    String message = String.format("Items: %d", "unknown");
    System.out.println(message);
} catch (IllegalFormatException e) {
    System.out.println("Format failed: " + e.getClass().getSimpleName());
}
```

Kết quả:

```text
Format failed: IllegalFormatConversionException
```

**Không dùng `catch` để che một mẫu sai cố định trong chương trình.** Ngoại lệ cho biết cần sửa mẫu hoặc giá trị truyền vào. Nếu nghiệp vụ buộc phải xử lý mẫu cấu hình ngoài mã nguồn, có thể bắt ngoại lệ rồi trả lỗi/đường xử lý dự phòng đã kiểm chứng.

## 9. Những nhầm lẫn phổ biến

| Nhầm lẫn | Thực tế |
| --- | --- |
| `"42"` dùng được với `%d` vì nội dung là số | Kiểu Java vẫn là `String`; cần parse hoặc dùng `%s` để hiển thị |
| `%.2d` dùng để tạo số nguyên hai chữ số | `d` không hỗ trợ precision; dùng width như `%02d` khi cần thêm 0 |
| `%f` chấp nhận mọi đối tượng kiểu `Number` | Mỗi conversion có tập kiểu được hỗ trợ riêng |
| Sai dữ liệu luôn dẫn tới `IllegalFormatException` | Parse số có thể ném `NumberFormatException`; quy tắc nghiệp vụ do ứng dụng tự kiểm tra |
| Truyền nhiều đối số hơn mẫu luôn gây lỗi | Đối số thừa không được sử dụng có thể bị bỏ qua |
| Mẫu định dạng chính là dữ liệu người dùng | Dấu `%` trong mẫu được phân tích như cú pháp, nên dữ liệu nên truyền ở vị trí đối số |
| Cùng một mẫu luôn hiển thị số giống hệt trên mọi máy | Locale mặc định có thể ảnh hưởng dấu phân tách và cách trình bày |
| Biên dịch thành công nghĩa là mọi phép format đều an toàn | Mẫu và đối số có thể chỉ được phát hiện không tương thích khi chương trình chạy |

## 10. Tự kiểm tra

Hãy đoán các biểu thức sau trả về chuỗi nào hoặc ném ngoại lệ nào (đây là các biểu thức minh họa; để biên dịch trong lớp cần đặt vào phương thức và import `java.util.Locale`):

```java
String a = "%d".formatted(12);
String b = "%d".formatted("12");
String c = "%2$s".formatted("A");
String d = "Completed: %d%%".formatted(50);
String e = String.format(Locale.US, "%.2f", 3.5);
```

**Đáp án:** `a` trả `"12"`; `b` ném `IllegalFormatConversionException`; `c` ném `MissingFormatArgumentException` vì không có đối số thứ hai; `d` trả `"Completed: 50%"`; `e` trả `"3.50"`.

**Tài liệu chính thức còn áp dụng:**
- [Java SE 26 API — IllegalFormatException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IllegalFormatException.html).
- [Java SE 26 API — Formatter (cú pháp, loại chuyển đổi và lỗi)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Formatter.html).
- [Java SE 26 API — String.format và String.formatted](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html).