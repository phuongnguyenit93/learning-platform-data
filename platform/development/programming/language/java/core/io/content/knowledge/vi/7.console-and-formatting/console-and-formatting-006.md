# print, println, printf và Formatter trong Java

Khi xuất dữ liệu ra console hoặc tạo văn bản có cấu trúc, Java cung cấp ba phương thức quen thuộc trên `PrintStream`: `print(...)`, `println(...)` và `printf(...)`. Cả ba thường được gọi qua `System.out`, nhưng **chúng không có cùng hành vi xuống dòng hay định dạng giá trị**. Phía dưới `printf` là cơ chế của `java.util.Formatter`, có khả năng căn lề, chèn số theo mẫu, chọn `Locale` và tạo chuỗi định dạng để gửi sang tệp hoặc nơi nhận khác.

Bài này giải thích cách chọn đúng phương thức, đọc cú pháp `%...`, kiểm soát định dạng giữa các máy và tránh các lỗi thường gặp trong Java 17+.

## 1. Đầu ra tiêu chuẩn và PrintStream

`System.out` là luồng đầu ra tiêu chuẩn (stdout), có kiểu `PrintStream`; `System.err` là luồng lỗi chuẩn (stderr), cũng là `PrintStream`. Với chương trình chạy trong terminal, cả hai thường hiển thị trên màn hình. Tuy nhiên khi chuyển hướng hoặc chạy trong IDE, chúng có thể được gửi tới những nơi khác nhau.

~~~java
System.out.print("Hello");
System.out.println(" World");
System.err.println("Something went wrong");
~~~

Đây là **mảnh mã minh họa**. Hai lời gọi đầu nối lại thành dòng `Hello World` trên stdout. Lời gọi cuối gửi thông báo sang stderr; thứ tự hiển thị tương đối giữa hai luồng không nhất thiết được bảo đảm bởi terminal hoặc công cụ gom log. Không tự gọi `close()` trên `System.out`/`System.err` trong chương trình thông thường, vì các phần còn lại của ứng dụng có thể vẫn cần dùng chúng.

`PrintStream` có các overload của `print`/`println` nhận kiểu nguyên thủy, `String`, `char[]` và `Object`. Đối với đối tượng, việc biểu diễn thường dựa vào `String.valueOf(...)` và `toString()`; do đó định dạng đẹp của đối tượng tùy cách `toString()` được triển khai. Riêng mảng số nguyên không tự in danh sách phần tử bằng `print(array)`; để hiển thị nội dung, dùng `Arrays.toString(array)`.

## 2. print, println và printf khác nhau thế nào?

| Phương thức | Hành vi chính | Có tự kết thúc dòng? | Có chuỗi định dạng `%...`? |
|---|---|---|---|
| `print(value)` | In biểu diễn của một giá trị | **Không** | Không |
| `println(value)` | In giá trị rồi in dấu kết thúc dòng | **Có** | Không |
| `println()` | Chỉ in dấu kết thúc dòng | **Có** | Không |
| `printf(format, args...)` | Thay các format specifier bằng giá trị đã định dạng | **Không**, trừ khi mẫu chứa ký tự xuống dòng hoặc `%n` | **Có** |
| `format(format, args...)` trên `PrintStream` | Cùng cơ chế định dạng như `printf` | Theo mẫu | Có |

`print` hữu ích để nối nhiều phần trên cùng dòng. `println` thích hợp cho thông báo theo dòng. `printf` thích hợp khi cần bản ghi có kích thước cột, số chữ số, độ chính xác hoặc biểu diễn khác nhau theo loại dữ liệu.

Ví dụ:

~~~java
System.out.print("A");
System.out.print("B");
System.out.println("C");
System.out.println("D");
~~~

Kết quả trên stdout:

~~~text
ABC
D
~~~

Hai lần `print` không tạo newline. Lần `println("C")` mới kết thúc dòng `ABC`; lần `println("D")` tạo dòng tiếp theo.

**Điểm rất dễ nhầm:** `System.out.printf("Done")` không tự xuống dòng. Nếu muốn xuống dòng, dùng `System.out.printf("Done%n")` hoặc gọi `println()` sau đó.

## 3. Ví dụ hoàn chỉnh: ba phương thức trong cùng chương trình

Tạo file **`ConsoleOutputDemo.java`**:

~~~java
import java.util.Locale;

public class ConsoleOutputDemo {
    public static void main(String[] args) {
        System.out.print("Java");
        System.out.print(" ");
        System.out.println("IO");
        System.out.println();

        System.out.printf(Locale.US, "ID=%04d; price=%.2f%n", 7, 12.5);
        System.out.printf(Locale.US, "[%-6s][%05d]%n", "OK", 42);
        System.out.printf(Locale.US,
                "%2$s/%1$s/%%%n", "right", "left");
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 ConsoleOutputDemo.java
java ConsoleOutputDemo
~~~

Stdout (có **một dòng trống** sau `Java IO`):

~~~text
Java IO

ID=0007; price=12.50
[OK    ][00042]
left/right/%
~~~

Giải thích:

1. Hai lần `print` và một lần `println` cùng tạo `Java IO`; sau đó `println()` tạo dòng trống.
2. `%04d` in số nguyên `7` trong độ rộng tối thiểu 4 với các số `0` điền bên trái, cho `0007`.
3. `%.2f` in số thực với hai chữ số sau dấu thập phân, cho `12.50` khi dùng `Locale.US`.
4. `%-6s` căn trái chuỗi `OK` trong vùng rộng ít nhất sáu ký tự: `OK` cộng bốn dấu cách. `%05d` cho `00042`.
5. `%2$s` lấy tham số thứ hai (`left`); `%1$s` lấy tham số thứ nhất (`right`). `%%` là ký tự `%` thực, `%n` kết thúc dòng.
6. `Locale.US` được chỉ rõ để kết quả số và ký hiệu định dạng không phụ thuộc locale mặc định của máy chạy.

Các dòng văn bản giống nhau trên các nền tảng, nhưng chuỗi byte của dấu xuống dòng cuối các dòng có thể khác tùy hệ điều hành vì `println` và `%n` dùng line separator tương ứng của nền tảng.

## 4. Cấu trúc format specifier của Formatter

Mẫu tổng quát cho một phép chuyển đổi có đối số:

~~~text
%[argument_index$][flags][width][.precision]conversion
~~~

| Phần | Vai trò | Ví dụ |
|---|---|---|
| `%` | Bắt đầu một specifier | `%d` |
| `argument_index$` | Lấy đối số ở vị trí 1, 2, 3, ... (đếm từ 1) | `%2$s` |
| `flags` | Điều chỉnh căn lề, dấu, số 0, phân nhóm chữ số... | `%-10s`, `%+d` |
| `width` | **Độ rộng tối thiểu**, không tự cắt chuỗi nếu vượt quá | `%8d` |
| `.precision` | Độ chính xác hoặc độ dài tối đa, tùy kiểu chuyển đổi | `%.2f`, `%.3s` |
| `conversion` | Loại biểu diễn mong muốn | `s`, `d`, `f` |

Phần trong dấu `[...]` là tùy chọn. Không phải mọi tổ hợp cờ, độ rộng và precision đều hợp lệ với mọi conversion; chọn sai có thể phát sinh ngoại lệ định dạng.

Một số specifier đặc biệt không tiêu thụ đối số:

- `%%` xuất ký tự phần trăm `%`.
- `%n` xuất **dấu kết thúc dòng phù hợp nền tảng**.
- Ký tự `\n` viết trong chuỗi Java sẽ đưa đúng ký tự LF; nó không mang ý nghĩa *platform line separator* như `%n`.

### Các conversion thông dụng

| Specifier | Loại đối số phù hợp | Ví dụ giá trị / kết quả |
|---|---|---|
| `%s` | Hầu hết đối tượng, dạng chuỗi | `"Java"` → `Java` |
| `%S` | Dạng chữ hoa của `%s` theo locale áp dụng | `"java"` → `JAVA` |
| `%d` | Kiểu số nguyên: `byte`, `short`, `int`, `long`, `BigInteger` | `42` → `42` |
| `%x`, `%X` | Số nguyên hệ 16, chữ thường/chữ hoa | `255` → `ff` / `FF` |
| `%o` | Số nguyên hệ 8 | `8` → `10` |
| `%f` | `float`, `double`, `BigDecimal` | `1.5` → `1.500000` khi không chỉ precision |
| `%e`, `%E` | Số thực dạng khoa học | `12.0` → biểu diễn có số mũ |
| `%b` | Giá trị boolean theo quy tắc Formatter | `true` → `true` |
| `%c` | Ký tự, hoặc một code point hợp lệ từ giá trị nguyên phù hợp | `'A'` → `A` |
| `%tF` | Đối số ngày/giờ hỗ trợ conversion: ngày `yyyy-MM-dd` | `LocalDate.of(2024, 2, 29)` → `2024-02-29` |
| `%n` | Không nhận đối số | Dấu kết thúc dòng |
| `%%` | Không nhận đối số | `%` |

Một số chi tiết cần nhớ:

- `%d` **không** dành cho số thực `double`; nếu muốn biểu diễn số thập phân, dùng `%f` hoặc chuyển kiểu có chủ đích.
- `%f` mặc định sáu chữ số sau dấu thập phân (ví dụ `1.500000`), không phải hiển thị nguyên trạng bằng `Double.toString`.
- `%b` của `Formatter` **khác cách ép chuỗi sang boolean**: nếu đối số là `null` thì kết quả `false`; nếu là `Boolean` thì theo giá trị đó; đối tượng khác `null` và khác `Boolean` sẽ cho `true`. Đừng dùng `%b` để diễn giải dữ liệu text `"false"`.
- `%s` với `null` thường cho chữ `null`; nó không tương đương chuỗi rỗng. Với đối tượng tùy biến, kết quả phụ thuộc `toString()` hoặc `Formattable` nếu có hỗ trợ.
- `%tF` dùng cú pháp ngày-giờ: ký tự `t` theo sau là `F`; các biến thể khác có `%tY` (năm), `%tm` (tháng), `%td` (ngày), `%tT` (giờ/phút/giây). Loại đối số phải hỗ trợ trường thời gian được yêu cầu.
- Số nguyên Java kiểu `char`/`Character` không được dùng trực tiếp với `%d`; nếu cần mã số ký tự, chuyển sang kiểu `int` rõ ràng.

## 5. Độ rộng, căn lề, số 0 và precision

### 5.1. Width là tối thiểu

~~~java
System.out.printf(Locale.US, "[%5s]%n", "A");
System.out.printf(Locale.US, "[%-5s]%n", "A");
~~~

Đây là mảnh mã minh họa cần import `java.util.Locale` và đặt trong một phương thức. Kết quả:

~~~text
[    A]
[A    ]
~~~

- `%5s`: tổng độ rộng ít nhất 5, mặc định thêm 4 dấu cách ở **bên trái**.
- `%-5s`: cờ `-` căn **trái**, thêm 4 dấu cách ở bên phải.
- Nếu giá trị dài hơn width, Formatter không mặc nhiên cắt dữ liệu. Width không phải kích thước tối đa.

### 5.2. Precision phụ thuộc loại chuyển đổi

~~~java
System.out.printf(Locale.US, "[%.3s]%n", "Formatter");
System.out.printf(Locale.US, "[%.2f]%n", 3.14159);
~~~

Kết quả:

~~~text
[For]
[3.14]
~~~

- `%.3s` giới hạn phần biểu diễn chuỗi tối đa ba ký tự được định dạng, cho `For`.
- `%.2f` quy định hai chữ số sau dấu phân cách thập phân, có làm tròn khi cần.
- **Không dùng `%.2d`** theo thói quen từ các ngôn ngữ khác: precision không áp dụng cho phép chuyển số nguyên `%d` trong `java.util.Formatter`; có thể gặp `IllegalFormatPrecisionException`. Để thêm số 0 bên trái, dùng ví dụ `%04d`.

### 5.3. Cờ định dạng số thường gặp

| Specifier | Giá trị | Kết quả với `Locale.US` | Ý nghĩa |
|---|---:|---|---|
| `%+d` | `42` | `+42` | Luôn hiển thị dấu |
| `%06d` | `42` | `000042` | Điền số 0 đủ độ rộng 6 |
| `%,d` | `1234567` | `1,234,567` | Phân nhóm chữ số |
| `%(d` | `-42` | `(42)` | Số âm đặt trong ngoặc |
| `%8.2f` | `3.5` | `    3.50` | Độ rộng 8, hai chữ số thập phân |
| `%-8.2f` | `3.5` | `3.50    ` | Căn trái trong 8 vị trí |

Các khoảng trắng ở hai hàng cuối là thành phần của output. Không dùng cờ `0` cho chuỗi `%s` và đừng kết hợp hai cờ trái nghĩa `-` với `0`: những tổ hợp không phù hợp có thể ném `FormatFlagsConversionMismatchException` hoặc `IllegalFormatFlagsException`.

## 6. Thứ tự đối số và tái sử dụng đối số

Mặc định, các specifier có đối số tiêu thụ chúng theo thứ tự:

~~~java
String text = String.format("%s:%d", "port", 8080);
~~~

`text` chứa `port:8080`. Đây là mảnh mã minh họa.

Muốn đổi thứ tự mà không đổi danh sách đối số, dùng chỉ số bắt đầu từ **1**, gắn `$`:

~~~java
String text = String.format("%2$s / %1$s / %2$s", "B", "A");
~~~

`text` chứa `A / B / A`. Đối số được nhắc lại nhiều lần mà không phải truyền trùng.

Cờ `<` còn cho phép dùng lại đối số của specifier trước đó:

~~~java
String result = String.format(Locale.US, "%1$.2f / %<.1f", 2.5);
~~~

`result` là `2.50 / 2.5`. Khi dùng `<` trước khi có đối số trước đó, Formatter báo lỗi thiếu đối số. Trong mã có nhiều trường định dạng, chỉ số tường minh thường dễ kiểm tra hơn vì việc trộn chỉ số tường minh và ngầm định có những quy tắc khó đoán.

## 7. Locale ảnh hưởng đến kết quả định dạng

`Locale` quyết định các quy tắc bản địa hóa trong Formatter, chẳng hạn dấu thập phân, phân nhóm hàng nghìn và tên tháng. Mặc định, các lời gọi `printf(...)` không chỉ `Locale` lấy **default locale cho nhóm FORMAT**, nên kết quả có thể khác giữa hai máy.

Chương trình **`LocaleFormattingDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.Locale;

public class LocaleFormattingDemo {
    public static void main(String[] args) {
        double amount = 12345.6;

        System.out.println("US: "
                + String.format(Locale.US, "%,.2f", amount));
        System.out.println("DE: "
                + String.format(Locale.GERMANY, "%,.2f", amount));

        LocalDate date = LocalDate.of(2024, 2, 29);
        System.out.printf(Locale.US, "Date: %1$tF%n", date);

        String message = "Item=%s; quantity=%d".formatted("Pen", 3);
        System.out.println(message);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleFormattingDemo.java
java LocaleFormattingDemo
~~~

Kết quả:

~~~text
US: 12,345.60
DE: 12.345,60
Date: 2024-02-29
Item=Pen; quantity=3
~~~

Mức độ làm tròn của `%.2f` là hành vi định dạng biểu diễn, **không đổi giá trị gốc của biến `double`**. Khi nghiệp vụ cần quy tắc tiền tệ chính xác, phải chọn kiểu số (ví dụ `BigDecimal`), độ chính xác và cách làm tròn phù hợp riêng; Formatter chủ yếu trình bày kết quả.

- Dùng `Locale.US` hoặc một locale cụ thể để có kết quả dễ dự đoán khi định dạng báo cáo hoặc kiểm thử.
- Dùng locale theo người dùng cho nội dung hiển thị thân thiện với vùng miền.
- Không xem dấu thập phân do Formatter in ra là định dạng trao đổi máy-máy mặc định. CSV, JSON, SQL hoặc giao thức dữ liệu có quy tắc riêng; hãy tuân theo chuẩn của từng định dạng.
- `String.formatted(args...)` (Java 15+) là cách ngắn để áp dụng cú pháp Formatter lên chuỗi mẫu; nó sử dụng locale mặc định khi cần bản địa hóa. Muốn chỉ định locale, dùng `String.format(Locale, ...)`.

## 8. java.util.Formatter: định dạng không nhất thiết in ra console

`java.util.Formatter` là bộ máy định dạng. `PrintStream.printf` và `PrintStream.format` là các cách tiện lợi để ghi kết quả định dạng vào PrintStream; `String.format` tạo **String mới**; còn một đối tượng `Formatter` có thể ghi trực tiếp vào một đích `Appendable`, ví dụ `StringBuilder` hoặc `Writer`.

Ví dụ độc lập **`FormatterBuilderDemo.java`**:

~~~java
import java.util.Formatter;
import java.util.Locale;

public class FormatterBuilderDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder();

        try (Formatter formatter = new Formatter(builder, Locale.US)) {
            formatter.format("%2$s | %1$04d%n", 3, "ID");
            formatter.format("ratio=%.2f%n", 2.5);
        }

        System.out.print(builder.toString());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FormatterBuilderDemo.java
java FormatterBuilderDemo
~~~

Stdout:

~~~text
ID | 0003
ratio=2.50
~~~

Vòng đời ví dụ:

1. `StringBuilder` là nơi nhận ký tự, chưa có byte I/O hoặc console.
2. `new Formatter(builder, Locale.US)` tạo formatter ghi vào builder với locale chỉ định.
3. Hai lần `format` thêm dữ liệu vào cùng builder, **không xóa nội dung trước đó**.
4. `Formatter` hỗ trợ `AutoCloseable` nên dùng được trong `try-with-resources`. Ở đây `StringBuilder` không phải nguồn I/O cần đóng, và kết quả vẫn truy cập được sau khi đóng Formatter.
5. Lời gọi `System.out.print(...)` cuối chỉ làm nhiệm vụ xuất chuỗi đã tạo; có thể thay bằng ghi sang file hoặc sử dụng trong ứng dụng mà không in console.

Đối với Formatter ghi vào một đích thuộc loại `Closeable`, thao tác `Formatter.close()` sẽ đóng cả đích đó. Không nên mở `Formatter` sở hữu `System.out` rồi vô tình đóng nó giữa chương trình. Một đối tượng Formatter đã đóng không còn cho phép định dạng tiếp; dùng lại sẽ gặp `FormatterClosedException`.

### Formatter có thể ghi ra Writer

~~~java
// Mảnh mã minh họa: writer là Writer do ứng dụng sở hữu.
try (Formatter formatter = new Formatter(writer, Locale.US)) {
    formatter.format("%s,%.2f%n", "Book", 12.5);
}
~~~

Dùng cách này khi muốn tập trung chuẩn bị nội dung định dạng ở một nơi, có thể kết hợp với `BufferedWriter` hoặc `Files.newBufferedWriter(...)` với charset tường minh. Khi formatter đóng, writer phía dưới cũng được đóng nếu nó hỗ trợ `Closeable`.

## 9. printf, Formatter và phương thức tạo chuỗi

| API | Đích kết quả | Giá trị trả về | Đặc điểm |
|---|---|---|---|
| `System.out.printf(...)` | Stdout qua PrintStream | Chính `PrintStream` | Ghi trực tiếp, không tự thêm newline |
| `System.out.format(...)` | Stdout qua PrintStream | Chính `PrintStream` | Cơ chế tương đương printf |
| `String.format(...)` | Bộ nhớ | `String` mới | Phù hợp tạo thông báo rồi gửi sang nơi khác |
| `"pattern".formatted(...)` | Bộ nhớ | `String` mới | Cách viết ngắn từ Java 15 |
| `formatter.format(...)` | Đích `Appendable` của Formatter | Chính `Formatter` | Cho phép tiếp tục thêm nhiều đoạn với cùng formatter |

`printf` có overload `printf(Locale locale, String format, Object... args)`. Nếu không truyền locale, định dạng số và ngày tháng được thực hiện theo locale FORMAT mặc định. `String.format` cũng có overload tương ứng.

`print` và `println` **không phân tích chuỗi đầu vào thành format specifier**: `System.out.println("100%")` chỉ in đúng `100%`. Ngược lại, với `printf("100%")`, dấu phần trăm đứng một mình có thể gây lỗi cú pháp định dạng; phải viết `printf("100%%")` hoặc dùng `print/println` cho chuỗi không cần định dạng.

## 10. Lỗi định dạng và cách phát hiện

Khác với `print` đơn thuần, Formatter kiểm tra sự tương thích giữa mẫu và đối số **khi chương trình chạy**. Sai mã conversion, thiếu đối số hoặc cờ không hợp lệ thường gây một ngoại lệ thuộc họ `IllegalFormatException`, tức lỗi runtime.

| Lỗi | Ví dụ | Kết quả thường gặp |
|---|---|---|
| Kiểu đối số không phù hợp | `String.format("%d", "12")` | `IllegalFormatConversionException` |
| Thiếu đối số | `String.format("%s %d", "A")` | `MissingFormatArgumentException` |
| Precision không hỗ trợ | `String.format("%.2d", 4)` | `IllegalFormatPrecisionException` |
| Dùng cờ không phù hợp với conversion | `String.format("%05s", "A")` | `FormatFlagsConversionMismatchException` |
| Mẫu có conversion không được hỗ trợ | `String.format("%q", 1)` | `UnknownFormatConversionException` |

Ví dụ độc lập **`FormattingErrorsDemo.java`**:

~~~java
import java.util.IllegalFormatConversionException;
import java.util.MissingFormatArgumentException;

public class FormattingErrorsDemo {
    public static void main(String[] args) {
        try {
            String.format("%d", "42");
        } catch (IllegalFormatConversionException ex) {
            System.out.println("Wrong type");
        }

        try {
            String.format("%s %d", "A");
        } catch (MissingFormatArgumentException ex) {
            System.out.println("Missing argument");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FormattingErrorsDemo.java
java FormattingErrorsDemo
~~~

Stdout:

~~~text
Wrong type
Missing argument
~~~

Hãy xem lỗi định dạng là lỗi trong chương trình hoặc dữ liệu đầu vào cần được kiểm soát. Không nên dùng `catch (Exception)` rồi bỏ qua để che giấu mẫu sai. Nếu có phần văn bản do người dùng nhập, hãy truyền nó **như đối số của `%s`** (chẳng hạn `printf("%s%n", userText)`) thay vì dùng toàn bộ văn bản đó làm format string; một dấu `%` trong chuỗi người dùng sẽ không bị hiểu nhầm là lệnh định dạng.

### Lỗi I/O khác lỗi cú pháp format

`PrintStream` theo hợp đồng không ném `IOException` từ các thao tác in thông thường; sự cố I/O bên dưới thường được ghi nhận qua cờ lỗi, có thể kiểm tra bằng `checkError()`. Nhưng **ngoại lệ định dạng** như `IllegalFormatException` vẫn có thể ném khi mẫu/đối số sai. Đừng nhầm hai loại lỗi này.

Tương tự, `Formatter` ghi vào một đích `Appendable` có thể ghi nhận lỗi `IOException` từ đích và cung cấp thông tin qua `ioException()`. Khi ghi dữ liệu quan trọng ra file, ngoài việc định dạng chính xác còn phải quyết định cách phản ứng nếu việc ghi thực sự thất bại. Đặc biệt, việc không thấy ngoại lệ từ `PrintStream.print(...)` không đủ chứng minh dữ liệu đã được lưu bền vững xuống thiết bị lưu trữ.

## 11. Charset, newline và luồng đầu ra

Một chuỗi `String` trong JVM khác với byte do `System.out` gửi ra terminal/file. Charset dùng bởi `PrintStream` và môi trường terminal có thể ảnh hưởng đến việc dấu tiếng Việt hiển thị đúng; từ JDK 18, default charset UTF-8 không đồng nghĩa mọi thiết lập của `System.out`/`System.err` và terminal đều nhất thiết dùng cùng encoding.

Nếu cần tạo file văn bản có định dạng ổn định, có thể ghi một chuỗi được tạo bởi Formatter bằng charset rõ ràng:

~~~java
// Mảnh mã minh họa: path là Path hợp lệ và đã chọn cách xử lý ghi đè.
String line = String.format(Locale.US, "%s,%.2f%n", "Tea", 3.5);
Files.writeString(path, line, StandardCharsets.UTF_8);
~~~

Đoạn này cần import `Locale`, `Files` và `StandardCharsets`; `Files.writeString` dùng UTF-8 được chỉ định. Nó chỉ minh họa encoding, **không** là chương trình chạy độc lập. Khi cần tệp CSV thật, còn phải xử lý dấu phẩy trong dữ liệu, nháy kép, xuống dòng trong trường và các quy tắc CSV; chỉ nối `%s,%.2f` chưa đủ để làm bộ ghi CSV hoàn chỉnh.

Về xuống dòng:

- `println(...)` viết dấu kết thúc dòng theo nền tảng.
- `printf("...%n")` thêm line separator theo nền tảng.
- `printf("...\n")` viết ký tự LF `U+000A` trong chuỗi format.
- `print(...)` và `printf(...)` không tự thêm newline khi không được yêu cầu.

`PrintStream` có thể được cấu hình tự `flush` trong các tình huống xác định, nhưng flush phụ thuộc cách tạo PrintStream và không phải bảo đảm lưu bền vững trên đĩa. Với ứng dụng cần log có độ tin cậy cao hoặc lưu dữ liệu giao dịch, nên dùng công cụ và chiến lược ghi phù hợp thay vì chỉ phụ thuộc `System.out.printf`.

## 12. Cách chọn công cụ trong thực tế

**Thông báo đơn giản theo dòng:** dùng `println(...)`. Nó dễ đọc, tự xuống dòng, ít rủi ro hơn dùng `printf` mà không cần specifier.

**Nối phần nội dung trên cùng dòng:** dùng `print(...)`. Nhưng đối với UI terminal phức tạp, hãy cân nhắc công cụ hỗ trợ terminal thay vì phụ thuộc cách luồng ký tự được đệm và hiển thị.

**Bảng, số với dấu phân cách/độ chính xác:** dùng `printf(locale, pattern, args...)`; kiểm soát width, precision, cờ và locale.

**Tạo văn bản để dùng nhiều nơi:** dùng `String.format(...)` hoặc `String.formatted(...)`; tránh ghi trực tiếp ra console giữa tầng xử lý nghiệp vụ.

**Ghi nhiều đoạn vào cùng buffer hoặc Writer:** dùng `Formatter` với đích `Appendable`. Xác định rõ trách nhiệm đóng tài nguyên và kiểm tra lỗi I/O khi ghi ra đích ngoài.

**Số tiền hay dữ liệu cần tính toán chính xác:** Formatter là tầng trình bày; thiết kế kiểu dữ liệu, quy tắc làm tròn và cách lưu/trao đổi là các quyết định khác.

## 13. Các lỗi dễ mắc

1. **Cho rằng `printf` tự xuống dòng:** không đúng. Thêm `%n` khi cần kết thúc dòng.
2. **Nhầm `%n` với `\n`:** `%n` là line separator nền tảng, còn `\n` là LF. Kiểm thử byte đầu ra và định dạng file cần biết khác biệt này.
3. **Dùng `%d` cho `double`, `%.2d` cho số nguyên hoặc `%05s` cho chuỗi:** mỗi conversion chấp nhận kiểu và cờ khác nhau; tổ hợp sai gây runtime exception.
4. **Cho rằng width là độ dài tối đa:** nó chỉ là tối thiểu; muốn giới hạn chuỗi, xem precision của `%s` nếu phù hợp, hoặc kiểm tra dữ liệu trước khi in.
5. **Quên Locale:** `%,.2f` có thể in dấu phân nhóm và thập phân khác nhau giữa các máy. Chọn locale theo yêu cầu.
6. **Dùng `%b` để đọc giá trị boolean từ một chuỗi:** đối số `"false"` vẫn là đối tượng khác null và sẽ được Formatter biểu diễn thành `true` với `%b`.
7. **Dùng dữ liệu người dùng làm format string:** dấu `%` có thể kích hoạt specifier; nên truyền dữ liệu như đối số của mẫu cố định.
8. **In mảng bằng `print(intArray)` rồi chờ danh sách giá trị:** kiểu mảng không có `toString()` thân thiện. Dùng `Arrays.toString(...)` hoặc formatter cho từng phần tử.
9. **Dùng `printf` để tính toán/round số rồi tái sử dụng chuỗi như kết quả số học:** Formatter chỉ xây dựng biểu diễn, không thay thế quy tắc tính toán.
10. **Đóng `System.out` hoặc bọc `System.out` trong một Formatter rồi đóng ngoài ý muốn:** có thể khiến phần còn lại của chương trình không in được.
11. **Cho rằng mọi lỗi khi in đều ném `IOException`:** `PrintStream` thường ghi nhận qua `checkError()`; lỗi format runtime vẫn có thể ném bình thường.
12. **Nghĩ stdout và stderr nhất thiết hiển thị theo thứ tự gọi:** khi được trộn/chuyển hướng riêng, thứ tự quan sát được có thể khác, nên không dựa vào đó để bảo đảm thứ tự sự kiện.

## 14. Ghi nhớ

- `print(value)` **không xuống dòng**; `println(value)` **xuống dòng**; `printf(format, args...)` **định dạng theo mẫu** và chỉ xuống dòng khi yêu cầu.
- `Formatter` hỗ trợ `%s`, `%d`, `%f`, `%tF`, `%%`, `%n` cùng flags/width/precision/chỉ số đối số. Đúng loại đối số là yêu cầu bắt buộc.
- Chỉ rõ `Locale` để kết quả số và ngày/giờ ổn định; dùng `%n` khi cần line separator của nền tảng.
- `String.format`, `String.formatted` và `Formatter` cho phép tạo dữ liệu có định dạng mà không buộc phải in console.
- Cần phân biệt lỗi cú pháp/kiểu định dạng với lỗi I/O thực tế; nếu ghi ra file hoặc hệ thống khác, chọn charset và cơ chế quản lý tài nguyên phù hợp.

### Tài liệu chính thức

- [Java SE — PrintStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html)
- [Java SE — Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html)
- [Java SE — String.format và formatted](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
