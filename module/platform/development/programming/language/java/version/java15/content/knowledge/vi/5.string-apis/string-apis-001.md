# String.formatted() và chuỗi định dạng làm đối tượng nhận

> **Mục tiêu:** Hiểu cách gọi `String.formatted(Object... args)` trên **chính chuỗi mẫu định dạng** trong Java; biết dùng dấu định dạng, text block, kiểm soát locale, xử lý lỗi và lựa chọn API phù hợp. `formatted` là API chính thức từ **Java 15**, tiếp tục có trong Java 17, 21, 25 và các JDK hiện đại. Nội dung này chỉ dựa trên tính năng đã chuẩn hóa và còn áp dụng hiện nay.

## 1. Khái niệm: format string là receiver

Trong Java, một **format string** (chuỗi định dạng) là chuỗi văn bản chứa các chỉ thị bắt đầu bằng `%` như `%s`, `%d` hoặc `%.2f`. Khi định dạng, Java dùng những chỉ thị này để chuyển đổi và chèn giá trị từ danh sách đối số vào chuỗi kết quả.

Trước hết, xem hai lối viết cho cùng một yêu cầu:

```java
String a = String.format("Xin chào %s!", "Mai");
String b = "Xin chào %s!".formatted("Mai");
```

Cả `a` và `b` đều có giá trị:

```text
Xin chào Mai!
```

Điểm khác biệt là **chuỗi mẫu xuất hiện ở đâu**:

- `String.format("Xin chào %s!", "Mai")`: `format` là **phương thức static**; chuỗi mẫu là tham số đầu tiên.
- `"Xin chào %s!".formatted("Mai")`: `formatted` là **phương thức instance**; chuỗi mẫu nằm **bên trái dấu chấm** và là đối tượng nhận (*receiver*) của lời gọi.
- `"Mai"` là đối số được chèn vào `%s` trong cả hai trường hợp.

Sơ đồ:

```text
String.format(mau, giaTri1, giaTri2)
              ^          ^
              mẫu        các đối số

mau.formatted(giaTri1, giaTri2)
^             ^
receiver      các đối số
```

`receiver` có thể là literal `"Tên: %s"`, biến `String template`, giá trị được trả về từ phương thức khác, hoặc một **text block** nhiều dòng. Kỹ thuật này thường giúp mã dễ đọc khi mẫu dài, nhất là với các thông báo hoặc tài liệu nhiều dòng.

## 2. Chữ ký API và quy tắc tương đương

API `java.lang.String` công bố:

```java
public String formatted(Object... args)
```

Đặc tả chính thức xác nhận phương thức này **tương đương về hành vi** với:

```java
String.format(this, args)
```

Trong biểu thức `template.formatted("Lan", 20)`, `this` về mặt ý nghĩa chính là `template`, không phải đối số đầu tiên `"Lan"`.

Các hệ quả quan trọng:

1. `formatted` dùng **cơ chế `java.util.Formatter`** giống `String.format`: cùng cú pháp dấu `%`, width, precision, index và họ lỗi định dạng.
2. `Object... args` là **varargs**: có thể truyền 0, 1 hoặc nhiều đối số, mỗi đối số được dùng theo format specifier tương ứng.
3. `String` trong Java **bất biến**. Gọi `template.formatted(...)` tạo **giá trị chuỗi kết quả**; nó **không thay thế nội dung của `template`**.
4. `formatted` chỉ có dạng instance nhận `Object... args`; không có overload chuẩn nhận `Locale` riêng. Nếu cần định dạng theo một locale được chỉ rõ, dùng `String.format(Locale, format, args...)`.
5. Java **không tự nội suy biến** theo cú pháp `${name}` hay `{name}` trong `formatted`. Phải dùng đúng các format specifier của `Formatter`.

Ví dụ về tính bất biến:

```java
String template = "Học viên: %s";
String output = template.formatted("Minh");

System.out.println(template);
System.out.println(output);
```

Kết quả:

```text
Học viên: %s
Học viên: Minh
```

Nếu gọi `template.formatted("Minh");` mà **không gán, in hoặc chuyển tiếp giá trị trả về**, kết quả định dạng được tạo ra nhưng không được sử dụng.

## 3. Cách các dấu `%` nhận đối số

Dạng tổng quát với các conversion thường gặp:

```text
%[argument_index$][flags][width][.precision]conversion
```

- `argument_index$`: chọn vị trí đối số, đếm từ **1** (`%1$s`, `%2$s`).
- `flags`: thay đổi cách trình bày, như `-` căn trái hoặc `0` đệm số bằng số không khi hợp lệ.
- `width`: **độ rộng tối thiểu** của trường định dạng, ví dụ `%8s`.
- `.precision`: cách giới hạn độ dài hoặc độ chính xác tùy conversion, ví dụ `%.3s`, `%.2f`.
- `conversion`: loại hiển thị, như `s`, `d`, `f`, `c`, `b`.

| Ký hiệu | Mục đích | Ví dụ dùng làm receiver |
| --- | --- | --- |
| `%s` | Biểu diễn đối số dạng chuỗi | `"Chào %s".formatted("Lan")` |
| `%S` | Dạng chữ hoa theo quy tắc locale | `"%S".formatted("java")` |
| `%d` | Số nguyên hệ thập phân | `"%d".formatted(42)` |
| `%f` | Định dạng số thực | `"%.2f".formatted(3.5)` |
| `%c` | Ký tự tương thích | `"%c".formatted('A')` |
| `%b` | Chuyển đổi boolean theo quy tắc Formatter | `"%b".formatted(true)` |
| `%1$s`, `%2$s` | Chọn đối số theo vị trí | `"%2$s - %1$s".formatted("A", "B")` |
| `%<s` | Dùng lại đối số của format specifier trước | `"%s / %<s".formatted("Java")` |
| `%%` | In một dấu `%` thật; không dùng đối số | `"100%%".formatted()` |
| `%n` | Xuống dòng theo hệ điều hành; không dùng đối số | `"A%nB".formatted()` |

**Lưu ý loại dữ liệu:** `%d` cần đối số số nguyên phù hợp; `%f` cần kiểu số thực phù hợp. Truyền `"42"` (một `String`) cho `%d` **không** khiến Java tự động phân tích chuỗi thành số; có thể phát sinh `IllegalFormatConversionException`.

### Width, precision và căn lề

```java
String right = "[%8s]".formatted("Java");
String left = "[%-8s]".formatted("Java");
String shortText = "[%.3s]".formatted("Spring");
```

Kết quả:

```text
[    Java]
[Java    ]
[Spr]
```

- `%8s`: có 4 spaces trước `Java` để đạt độ rộng 8.
- `%-8s`: có 4 spaces sau `Java`.
- `%.3s`: giới hạn phần chuỗi được hiển thị thành ba ký tự đầu theo quy tắc `Formatter`.

`width` là độ rộng **tối thiểu**, không phải mệnh lệnh cắt bớt chuỗi dài hơn. Với Unicode phức tạp, số ký tự Java xử lý và số ô hiển thị của terminal có thể khác nhau; ví dụ minh họa dùng chữ Latin để dễ kiểm chứng.

### Đổi thứ tự và lặp lại đối số

```java
String reversed = "%2$s rồi %1$s".formatted("Một", "Hai");
String repeated = "%1$s / %<s".formatted("Java");
```

Kết quả:

```text
Hai rồi Một
Java / Java
```

Các index bắt đầu từ **1**, không phải 0. Cờ `<` dùng lại đối số mà format specifier trước đó đã sử dụng. Nếu cần một đối số chưa được cung cấp, Java ném `MissingFormatArgumentException`. Ngược lại, **đối số thừa** thường bị bỏ qua, nên việc chương trình chạy không chứng minh bạn đã sử dụng hết mọi đối số.

## 4. Ví dụ hoàn chỉnh: receiver và kết quả trả về

Tạo tệp **`FormattedReceiverDemo.java`** với nội dung sau. Ví dụ dùng dữ liệu chuỗi để stdout không phụ thuộc dấu thập phân của locale.

```java
public class FormattedReceiverDemo {
    public static void main(String[] args) {
        String template = "Xin chào %s, mã %s.";
        String result = template.formatted("Mai", "A-07");

        System.out.println(result);
        System.out.println(template);
        System.out.println(result.equals(
                String.format(template, "Mai", "A-07")));

        System.out.println("[%8s]".formatted("Java"));
        System.out.println("[%-8s]".formatted("Java"));
        System.out.println("[%.3s]".formatted("Spring"));

        System.out.println("%2$s / %1$s".formatted("đầu", "cuối"));
        System.out.println("Hoàn thành 100%%: %s".formatted("OK"));

        String notice = """
                Chào %s,
                Mã khóa học: %s
                """.formatted("Mai", "JV15");

        System.out.print(notice);
    }
}
```

Yêu cầu **JDK 17 trở lên** (ví dụ JDK 21 hoặc 25). Mở terminal trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 FormattedReceiverDemo.java
java FormattedReceiverDemo
```

**Stdout chính xác**:

```text
Xin chào Mai, mã A-07.
Xin chào %s, mã %s.
true
[    Java]
[Java    ]
[Spr]
cuối / đầu
Hoàn thành 100%: OK
Chào Mai,
Mã khóa học: JV15
```

Ba điểm cần thấy:

1. `result` được điền dữ liệu, còn `template` vẫn là `"Xin chào %s, mã %s."`.
2. `result.equals(String.format(template, ...))` bằng `true`: hai lối viết tương đương về kết quả.
3. `""".formatted("Mai", "JV15")` cho thấy **text block là receiver**. Các dấu `%s` trong nội dung text block được thay sau khi Java đã xử lý cú pháp text block.

Dùng `System.out.print(notice)` vì text block trên đã mang newline cuối theo cách đặt dấu đóng. Nếu thêm `println(notice)` sẽ có thêm một newline khác sau đó.

## 5. `formatted` hoạt động với text block như thế nào?

**Text block** là cú pháp `String` nhiều dòng được chuẩn hóa từ Java 15. Nó hữu ích cho các mẫu dài như thông báo, đoạn văn bản hay dữ liệu mẫu trong bài tập:

```java
String email = """
        Xin chào %s,

        Chào mừng bạn đến với khóa học %s.
        Mã xác nhận: %s
        """.formatted("Lan", "Java", "JV-001");
```

Trong mã trên:

- **Toàn bộ text block** là chuỗi mẫu, kết thúc ở `"""`.
- `.formatted(...)` thực thi trên chính `String` đó, nên không cần chuyển text block thành đối số cho `String.format`.
- Các dấu xuống dòng và khoảng trắng của text block được xử lý theo quy tắc ngôn ngữ Java **trước** khi `formatted` thay thế các format specifier.
- Phương thức `formatted` **không tự xóa thụt lề, không tự bỏ newline cuối, không tự escape dữ liệu cho định dạng khác**.

Nếu cần in thông báo:

```java
System.out.print(email);
```

Đây là **đoạn mã minh họa** để đặt trong một phương thức Java, không phải một chương trình độc lập có class và `main`. Chương 4 đã có chương trình chạy được đầy đủ.

### Tái sử dụng một mẫu nhiều lần

```java
String pattern = "Người học: %s | Môn: %s";
String first = pattern.formatted("Lan", "Java");
String second = pattern.formatted("Minh", "SQL");
```

`pattern` không đổi qua các lần gọi. Khi phải tạo nhiều chuỗi có cùng cấu trúc, mẫu giúp tránh viết lặp văn bản cố định. Nếu mẫu cần được dùng xuyên nhiều phương thức, có thể đặt trong một hằng `private static final String` theo thiết kế lớp.

## 6. Locale: điều mà receiver `formatted` không quyết định được

Theo API, `String.formatted(args)` có hành vi tương đương `String.format(this, args)`. Dạng `String.format(String, Object...)` sử dụng **locale định dạng mặc định** của JVM (`Locale.Category.FORMAT`). Điều này có thể ảnh hưởng đến:

- Dấu phân cách hàng nghìn, dấu thập phân và cách viết chữ số của một số conversion số.
- Cách hiển thị chữ hoa khi conversion và locale có quy tắc đặc thù.
- Một số conversion ngày/giờ và cách trình bày tên tháng/ngày.

Ví dụ:

```java
String pattern = "Tổng: %,.2f";
String result = pattern.formatted(12345.5);
```

`result` có thể là `"Tổng: 12,345.50"` trên môi trường dùng quy ước US, nhưng sẽ có dấu phân cách khác ở những locale khác. **Không viết test cố định chuỗi `12,345.50` cho `formatted` nếu không kiểm soát locale.**

`String.formatted` không có overload `formatted(Locale.US, amount)`: một `Locale` truyền như vậy chỉ là **đối số định dạng đầu tiên**, không phải tùy chọn locale. Muốn chỉ định locale rõ ràng, dùng:

```java
String fixed = String.format(
        java.util.Locale.US, "Tổng: %,.2f", 12345.5);
```

Kết quả xác định: `Tổng: 12,345.50`.

### Chương trình độc lập để kiểm chứng

Tạo tệp **`LocaleFormatDemo.java`**:

```java
import java.util.Locale;

public class LocaleFormatDemo {
    public static void main(String[] args) {
        String pattern = "Tổng: %,.2f";
        double amount = 12345.5;

        String us = String.format(Locale.US, pattern, amount);
        System.out.println(us);

        String local = pattern.formatted(amount);
        System.out.println(local.equals(String.format(pattern, amount)));

        System.out.println(String.format(Locale.US, "Mã: %04d", 12));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LocaleFormatDemo.java
java LocaleFormatDemo
```

**Stdout xác định**:

```text
Tổng: 12,345.50
true
Mã: 0012
```

Dòng thứ hai so sánh hai cách định dạng **cùng locale mặc định**, nên giá trị boolean là `true` dù cách hiển thị chữ số của một máy có thể khác máy khác. Với dữ liệu trao đổi giữa hệ thống, báo cáo cần định dạng cố định và automated test, hãy **chỉ rõ `Locale` tại lời gọi**. Không nên thay đổi locale mặc định cho **toàn bộ JVM** chỉ vì một thao tác định dạng đơn lẻ.

## 7. Phân biệt API tương tự

| API | Vai trò | Trả về | Khi nào nên chọn |
| --- | --- | --- | --- |
| `"Tên: %s".formatted(name)` | Chuỗi mẫu là **receiver** | `String` | Mẫu có sẵn, nhất là text block, và muốn cú pháp gọn |
| `String.format("Tên: %s", name)` | Mẫu là tham số của phương thức static | `String` | Quen với cách gọi static hoặc mã đang theo quy ước này |
| `String.format(Locale.US, "%.2f", number)` | Chỉ định locale rõ | `String` | Định dạng số/ngày cần kết quả theo locale cố định |
| `System.out.printf("Tên: %s%n", name)` | Ghi dữ liệu định dạng ra console | `PrintStream` | In trực tiếp, không cần giữ một chuỗi kết quả |
| `"Tên: " + name` | Nối chuỗi | `String` | Ghép ít giá trị đơn giản, không cần định dạng width/precision |

**Không đánh đồng** `.formatted` với hệ thống template có cú pháp `{name}` hoặc nội suy tự động. Java `Formatter` dùng format specifier với dấu `%`, và các đối số được truyền tường minh. Cũng không cần dùng string template dạng preview từ các hướng dẫn cũ để giải bài toán này.

Nếu phải ghép rất nhiều phần trong vòng lặp, `StringBuilder` có thể rõ hơn hoặc tiết kiệm cấp phát trong hoàn cảnh phù hợp. Không tự kết luận một API nhanh hơn API khác nếu chưa đo đạc trường hợp thực tế.

## 8. Lỗi định dạng thường gặp và cách xử lý

### Thiếu đối số hoặc sai kiểu

Hai ví dụ **cố ý sai**:

```java
"%s - %s".formatted("chỉ có một"); // thiếu đối số cho %s thứ hai
"Số: %d".formatted("mười");        // %d không nhận String
```

Các trường hợp này tạo ngoại lệ thuộc họ `java.util.IllegalFormatException`:

- `MissingFormatArgumentException`: thiếu đối số được tham chiếu.
- `IllegalFormatConversionException`: conversion không phù hợp với loại đối số.
- Còn có lỗi về cú pháp, cờ, width, precision hoặc conversion không tồn tại.

Ví dụ đầy đủ kiểm tra ngoại lệ, lưu thành **`FormatErrorDemo.java`**:

```java
import java.util.IllegalFormatException;

public class FormatErrorDemo {
    public static void main(String[] args) {
        try {
            System.out.println("%s - %s".formatted("một"));
        } catch (IllegalFormatException e) {
            System.out.println(e.getClass().getSimpleName());
        }

        try {
            System.out.println("Số: %d".formatted("mười"));
        } catch (IllegalFormatException e) {
            System.out.println(e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FormatErrorDemo.java
java FormatErrorDemo
```

Stdout:

```text
MissingFormatArgumentException
IllegalFormatConversionException
```

**Trong mã thực tế:** sửa mẫu và kiểu giá trị cho đúng; chỉ `catch` ngoại lệ khi cần xử lý lỗi cấu hình hoặc đầu vào một cách có chủ đích. Một mẫu định dạng sai thường là lỗi lập trình cần được phát hiện và sửa.

### Dấu phần trăm `%` theo nghĩa đen

Một dấu `%` đơn lẻ trong **mẫu định dạng** mở đầu chỉ thị đặc biệt. Vì vậy:

```java
String invalid = "Hoàn tất 100%".formatted(); // lỗi định dạng
String valid = "Hoàn tất 100%%".formatted();  // "Hoàn tất 100%"
```

`%%` tạo một dấu phần trăm thật, **không tiêu thụ đối số**. Đừng nhầm với chuỗi dữ liệu `"An%"` truyền cho `%s`: dấu `%` bên trong **giá trị đối số** không được diễn giải như format specifier lần nữa.

### `%n` khác `\n`

- `%n` trong mẫu là dấu xuống dòng phù hợp hệ điều hành, thường là `System.lineSeparator()`; không ăn đối số.
- `\n` trong Java string literal là line feed `U+000A`, dù chạy trên Windows.
- Text block là một trường hợp riêng: cú pháp Java chuẩn hóa line terminator trong nội dung text block về `\n` theo quy tắc text block.

Nếu hệ thống nhận dữ liệu yêu cầu chuẩn newline cụ thể, phải dùng đúng chuẩn đó; nếu in văn bản phù hợp môi trường, `%n` là lựa chọn tự nhiên.

### Sai khi dùng đầu vào người dùng làm chuỗi mẫu

```java
String username = "An%";
String greeting = "Xin chào %s".formatted(username);
```

Cách này an toàn về **cú pháp định dạng**, vì `username` là dữ liệu được chèn dưới `%s`: dấu `%` bên trong giá trị không bị xử lý như mã định dạng.

Ngược lại, không đặt một chuỗi tùy ý do người dùng nhập ở vị trí **receiver**, rồi gọi `.formatted(...)` trên nó nếu dữ liệu đó chỉ là văn bản: ký tự `%` có thể bị hiểu thành format specifier không hợp lệ, và các giá trị width/precision do người ngoài cung cấp cũng có thể gây kết quả ngoài dự kiến.

**Giới hạn an toàn cần nhớ:** `String.formatted` **không phải** bộ escape hoặc bộ mã hóa HTML/JSON/SQL. Đối với SQL, phải dùng truy vấn tham số hóa (`PreparedStatement`) thay cho việc nối chuỗi hoặc chèn `%s` vào câu SQL. Với HTML/JSON, dùng encoder/serializer phù hợp.

### Bảng lỗi thường thấy

| Hiện tượng | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| Gọi `formatted` nhưng mẫu vẫn là `%s` | `String` bất biến, bỏ qua giá trị trả về | Lưu hoặc sử dụng kết quả của lời gọi |
| Sai giá trị đầu ra | Đối số truyền nhầm thứ tự | Kiểm tra thứ tự hoặc dùng `%1$s`, `%2$s` |
| Lỗi `IllegalFormatConversionException` | Dùng `%d`, `%f` với loại dữ liệu không phù hợp | Chuyển đổi dữ liệu đúng kiểu trước khi định dạng |
| Lỗi `MissingFormatArgumentException` | Mẫu tham chiếu nhiều đối số hơn đã truyền | Bổ sung đối số hoặc sửa chỉ thị |
| Mẫu có `%` theo nghĩa đen gây lỗi | Thiếu escape phần trăm | Dùng `%%` trong mẫu |
| Số hiển thị dấu phẩy/dấu chấm khác máy | Locale FORMAT mặc định khác | Chỉ định `Locale` bằng `String.format(Locale,...)` |
| Dư newline khi in text block | Text block đã có newline cuối, lại dùng `println` | Xem nội dung text block và dùng `print` khi phù hợp |
| Nghĩ `formatted` dùng cú pháp `{x}` | Nhầm hệ thống định dạng | Dùng đúng dấu định dạng kiểu `printf` của `Formatter` |

## 9. Cách áp dụng trong ứng dụng

### Chuỗi thông báo dùng lại nhiều lần

```java
String notification = "Học viên %s đã hoàn thành %s";
String first = notification.formatted("Lan", "Java");
String second = notification.formatted("Minh", "SQL");
```

Chuỗi `notification` là **mẫu được định nghĩa một lần**, còn `first` và `second` là hai kết quả độc lập. Đây là chỗ cách gọi instance có lợi: mẫu được giữ ở vị trí dễ đọc, các đối số nằm ngay sau `.formatted`.

### Báo cáo văn bản nhiều dòng

```java
String report = """
        Học viên: %s
        Chủ đề: %s
        Kết quả: %s
        """.formatted("Mai", "Java", "Đạt");
```

Text block cho thấy ngay bố cục báo cáo, còn `.formatted` điền giá trị. Nếu muốn không có newline cuối hoặc thụt lề khác, phải sửa cách viết text block; `.formatted` không tự điều chỉnh chúng.

### Định dạng số trong một hợp đồng dữ liệu

```java
String amount = String.format(
        java.util.Locale.US, "%.2f", 1234.5);
```

Giá trị là `1234.50`, không phụ thuộc locale FORMAT của máy. Khi yêu cầu đầu ra ổn định, cách viết static với locale rõ ràng phù hợp hơn instance `.formatted`.

Ba đoạn trên là **snippet** cần đặt trong một phương thức hoặc khối Java hợp lệ. Chúng minh họa cách sử dụng API, còn chương 4, 6 và 8 là các chương trình độc lập có tên file/class, lệnh biên dịch và stdout.

## 10. Bài tập tự kiểm tra và lời giải

**Bài 1.** Tạo chuỗi `Mã: JV-01; học viên: Bình`, trong đó chuỗi mẫu là receiver.

```java
String value = "Mã: %s; học viên: %s".formatted("JV-01", "Bình");
```

**Bài 2.** Hãy giải thích kết quả:

```java
String pattern = "Xin chào %s";
String result = pattern.formatted("An");
```

`pattern` có giá trị `Xin chào %s`; `result` có giá trị `Xin chào An`. `formatted` trả về giá trị định dạng và **không thay đổi receiver**.

**Bài 3.** `"%2$s | %1$s".formatted("trái", "phải")` cho kết quả nào?

```text
phải | trái
```

**Bài 4.** Phải dùng API nào khi cần `1,234.50` theo quy ước US dù chương trình chạy trên máy dùng locale khác?

```java
String fixed = String.format(java.util.Locale.US, "%,.2f", 1234.5);
```

Không trông chờ `"%,.2f".formatted(1234.5)` giữ nguyên dấu phân cách trên mọi môi trường.

**Bài 5.** Tại sao `"100%".formatted()` không hợp lệ và phải sửa thế nào?

Dấu `%` là ký tự mở đầu format specifier, nhưng không có conversion ở cuối mẫu. Viết `"100%%".formatted()`.

**Bài 6.** Tại sao không thể dùng `"SELECT ... '%s'".formatted(userInput)` để bảo vệ một câu SQL?

Vì `formatted` chỉ thay chữ vào mẫu, **không tham số hóa SQL** và không đảm bảo escape đúng ngữ cảnh. Hãy dùng `PreparedStatement` cùng binding kiểu dữ liệu.

### Checklist

- [ ] Tôi biết chuỗi đứng trước `.formatted` là **đối tượng nhận** và là **format string**.
- [ ] Tôi nắm được quan hệ tương đương với `String.format(this, args)`.
- [ ] Tôi dùng đúng `%s`, `%d`, `%.2f`, width, index, `%%`, `%n`.
- [ ] Tôi hiểu `String` bất biến và biết dùng kết quả trả về.
- [ ] Tôi biết dùng `.formatted` ngay sau text block.
- [ ] Tôi biết chỉ định locale bằng `String.format(Locale,...)` khi cần định dạng cố định.
- [ ] Tôi biết nhận diện lỗi thiếu/sai loại đối số, tránh mẫu định dạng không đáng tin.
- [ ] Tôi không nhầm formatting với escaping hoặc SQL parameterization.

## Tài liệu chính thức (còn áp dụng)

1. [Oracle JDK 25 — API `String`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `formatted(Object...)`, `format(...)`, quy tắc `String` bất biến.
2. [Oracle JDK 25 — `java.util.Formatter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): cú pháp `%`, conversion, width, precision, locale và các ngoại lệ.
3. [Oracle JDK 25 — Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): text block, thụt lề và newline.
4. [Oracle — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/): cách tra cứu API theo phiên bản JDK đang sử dụng.

**Ghi nhớ:** `"Xin chào %s".formatted("Mai")` có nghĩa “hãy định dạng **chính chuỗi này** bằng các đối số đi kèm”. Đó là API instance ổn định, ngắn gọn, đặc biệt dễ đọc với text block. Nếu kết quả cần locale cố định, chọn `String.format(Locale, template, args...)`.