# Định dạng chuỗi Java với %s, %c, %b, %d, %f và %e

## 1. Mục đích và các API sử dụng

Trong Java, `java.util.Formatter` cung cấp cú pháp để chèn giá trị vào một chuỗi theo mẫu (*format string*). Sáu **conversion specifier** thường gặp là `%s`, `%c`, `%b`, `%d`, `%f` và `%e`. Mỗi specifier quyết định cách chuyển một đối số sang văn bản; có thể bổ sung độ rộng, độ chính xác, dấu căn lề và quy tắc hiển thị.

Ba cách sử dụng phổ biến:

~~~java
import java.util.Locale;

String message = String.format(Locale.US, "Name: %s, age: %d", "Mai", 20);
System.out.printf(Locale.US, "Price: %.2f%n", 12.5);

String message2 = "Name: %s, age: %d".formatted("Mai", 20);
~~~

- `String.format(...)` **trả về một `String`**; không tự in.
- `System.out.printf(...)` **ghi vào luồng đầu ra**, tương tự `System.out.format(...)`; thường thêm `%n` khi muốn xuống dòng. `printf` trả về chính `PrintStream`.
- `"mẫu".formatted(...)` (từ Java 15) trả về một chuỗi đã định dạng và dùng locale mặc định; cú pháp các specifier vẫn theo `Formatter`.

Ở hai lời gọi đầu, `Locale.US` được truyền tường minh để ví dụ số có dấu chấm thập phân và dấu phẩy tách nhóm nhất quán. Nếu bỏ locale, kết quả định dạng số có thể phụ thuộc cấu hình vùng/ngôn ngữ của JVM.

Một format string có thể chứa văn bản thường xen kẽ nhiều specifier:

~~~java
String line = String.format(
        Locale.US,
        "%s | %c | %b | %d | %.2f | %.2e",
        "Java", 'J', true, 42, 12.5, 1250.0
);
// Java | J | true | 42 | 12.50 | 1.25e+03
~~~

Mỗi vị trí `%...` nhận một đối số tương ứng theo thứ tự, trừ khi sử dụng chỉ số đối số hoặc cú pháp tái sử dụng đối số.

## 2. Cấu trúc một chỉ thị định dạng

Dạng khái quát của `Formatter`:

~~~text
%[argument_index$][flags][width][.precision]conversion
~~~

Ý nghĩa các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| `%` | Bắt đầu chỉ thị | `%d` |
| `argument_index$` | Chọn đối số thứ mấy, tính từ **1** | `%2$s` |
| `flags` | Căn trái, thêm dấu, đệm 0, phân nhóm... tùy conversion | `%-8s`, `%+d`, `%,d` |
| `width` | **Độ rộng tối thiểu** của trường kết quả | `%8d` |
| `.precision` | Giới hạn độ dài chuỗi hoặc số chữ số sau dấu thập phân, tùy conversion | `%.3s`, `%.2f` |
| `conversion` | Kiểu chuyển đổi | `s`, `c`, `b`, `d`, `f`, `e` |

`width` không cắt bớt giá trị dài hơn độ rộng đã yêu cầu; thông thường nó thêm khoảng trắng ở bên trái, trừ khi có flag căn trái. `precision` mang nghĩa khác nhau theo từng conversion và **không được dùng với mọi kiểu**.

Ví dụ:

~~~java
System.out.println("|" + String.format(Locale.US, "%8s", "Hi") + "|");
// |      Hi|

System.out.println("|" + String.format(Locale.US, "%-8s", "Hi") + "|");
// |Hi      |

System.out.println(String.format(Locale.US, "%.3s", "Spring"));
// Spr

System.out.println("|" + String.format(Locale.US, "%8.2f", 12.5) + "|");
// |   12.50|
~~~

Các ví dụ sử dụng chữ Latin và ký tự ASCII để số khoảng trắng dễ kiểm chứng. Độ rộng của `Formatter` không nên được hiểu là số cột hiển thị chắc chắn trong terminal đối với mọi emoji, ký tự tổ hợp hoặc chữ Đông Á.

## 3. `%s`: biểu diễn đối tượng dưới dạng chuỗi

`%s` là conversion **general/string**. Nó chấp nhận nhiều kiểu đối số, bao gồm `String`, số, boolean và đối tượng thông thường:

~~~java
System.out.println(String.format("Language: %s", "Java"));    // Language: Java
System.out.println(String.format("Count: %s", 42));           // Count: 42
System.out.println(String.format("Enabled: %s", true));       // Enabled: true
System.out.println(String.format("Value: %s", (Object) null)); // Value: null
~~~

Thông thường, Java dùng biểu diễn chuỗi của đối tượng (liên quan đến `toString()`). Với đối tượng triển khai `java.util.Formattable`, `Formatter` có thể sử dụng cơ chế định dạng chuyên biệt của interface đó. `%s` không có nghĩa là Java tự tạo JSON, CSV hoặc một định dạng trao đổi dữ liệu chuẩn.

Các tùy chọn quan trọng:

~~~java
String.format("%10s", "Java");  // "      Java": rộng ít nhất 10
String.format("%-10s", "Java"); // "Java      ": căn trái
String.format("%.2s", "Java"); // "Ja": tối đa 2 ký tự
String.format("%-6.3s", "Spring"); // "Spr   "
~~~

Khi cần định dạng cột tên người, mã sản phẩm hay nhãn văn bản, `%s` kết hợp với width/precision giúp trình bày rõ ràng. Nếu việc cắt chuỗi có thể làm mất thông tin hoặc cắt cụm ký tự Unicode, hãy xử lý quy tắc rút gọn ở tầng nghiệp vụ trước khi định dạng.

Chữ hoa `%S` áp dụng biến đổi sang chữ hoa cho kết quả theo locale (ví dụ `String.format(Locale.US, "%S", "java")` cho `JAVA`). Điều này khác với `%s` vốn không tự đổi chữ hoa.

## 4. `%c`: ký tự hoặc mã điểm Unicode

`%c` là conversion **character**, thường dùng với `char`/`Character`. Nó cũng chấp nhận `Byte`, `Short` hoặc `Integer` biểu diễn một mã điểm Unicode hợp lệ:

~~~java
System.out.println(String.format("%c", 'A')); // A
System.out.println(String.format("%c", 66));  // B (mã điểm U+0042)
System.out.println(String.format("|%3c|", 'Z')); // |  Z|
~~~

`%c` đòi hỏi đối số đúng loại; **`String` chỉ dài một ký tự vẫn không phải là `char`**:

~~~java
char letter = "Java".charAt(0);
String ok = String.format("%c", letter); // J

// String.format("%c", "J"); // Sai lúc chạy: IllegalFormatConversionException
~~~

`%c` với giá trị số nguyên nhận **mã điểm Unicode**, không có nghĩa là lấy chữ số đó để in. Mã điểm ngoài miền Unicode hợp lệ sẽ dẫn đến lỗi định dạng; ví dụ `String.format("%c", -1)` không hợp lệ. Với một mã điểm bổ sung hợp lệ (ngoài BMP), kết quả có thể chứa hai đơn vị mã UTF-16 nhưng vẫn biểu diễn một mã điểm.

Không dùng precision với `%c`; `%.2c` là format không hợp lệ. Có thể dùng width để căn cột. `%C` là biến thể in hoa phụ thuộc quy tắc locale.

## 5. `%b`: biểu diễn boolean theo quy tắc của Formatter

`%b` là conversion **boolean**, nhưng quy tắc của nó **khác** với việc ép mọi đối số thành `boolean` theo logic nghiệp vụ.

- Nếu đối số là `null`, kết quả là `false`.
- Nếu là `Boolean`, kết quả là `true` hoặc `false` theo giá trị thực.
- Nếu là **đối tượng khác và không null**, kết quả là `true`, kể cả số `0` hay chuỗi rỗng.

~~~java
System.out.println(String.format("%b", true));           // true
System.out.println(String.format("%b", false));          // false
System.out.println(String.format("%b", (Object) null));  // false
System.out.println(String.format("%b", 0));              // true
System.out.println(String.format("%b", ""));             // true
~~~

Vì vậy, `%b` **không kiểm tra “số khác 0” hay “chuỗi không rỗng”** và cũng không tự hiểu chuỗi `"false"` là giá trị boolean `false`. Để biểu diễn điều kiện nghiệp vụ, hãy tính biểu thức boolean trước:

~~~java
int quantity = 0;
System.out.println(String.format("Has stock: %b", quantity > 0));
// Has stock: false
~~~

`%B` viết hoa kết quả thành `TRUE` hoặc `FALSE`. Có thể dùng width/căn lề để trình bày; không nên dùng `%b` để thay việc kiểm tra dữ liệu đầu vào.

## 6. `%d`: số nguyên thập phân có dấu

`%d` nhận các kiểu số nguyên như `byte`, `short`, `int`, `long` và `BigInteger` (hoặc đối tượng bao tương ứng), rồi định dạng ở **hệ thập phân**.

~~~java
System.out.println(String.format(Locale.US, "%d", 42));       // 42
System.out.println(String.format(Locale.US, "%d", -42));      // -42
System.out.println(String.format(Locale.US, "%05d", 42));     // 00042
System.out.println(String.format(Locale.US, "%+d", 42));      // +42
System.out.println(String.format(Locale.US, "%,d", 1234567)); // 1,234,567
~~~

Các flag thường dùng:

- `0`: đệm số 0 vào khoảng trống bên trái sau dấu âm/dương để đủ width, ví dụ `%05d`.
- `+`: luôn hiển thị dấu dương hoặc âm, ví dụ `%+d`.
- `,`: phân nhóm chữ số theo locale, ví dụ `%,d`.
- `-`: căn trái trong trường đủ độ rộng, ví dụ `%-6d`.
- `(`: biểu diễn số âm bằng ngoặc, ví dụ `%(d` với `-42` thành `(42)`.

`%d` **không** làm tròn số thực: đưa `double` hoặc `float` cho `%d` gây `IllegalFormatConversionException`. Nếu muốn hiển thị một số thực không có phần thập phân, cần quyết định quy tắc làm tròn/chuyển kiểu trước, hoặc sử dụng `%.0f` với kiểu số thực nếu đúng yêu cầu hiển thị.

Đặc biệt, `%.3d` **không hợp lệ trong Java Formatter**: precision không được hỗ trợ cho `%d`. Muốn hiển thị `007` từ số nguyên `7`, dùng `%03d` (width + đệm 0).

## 7. `%f`: số thực ở dạng thập phân cố định

`%f` nhận `float`, `double` hoặc `BigDecimal` (và các đối tượng bao của hai kiểu nguyên thủy). Nó hiển thị số thực ở dạng thập phân thông thường, **không dùng ký hiệu số mũ**.

~~~java
System.out.println(String.format(Locale.US, "%f", 12.5));    // 12.500000
System.out.println(String.format(Locale.US, "%.2f", 12.5));  // 12.50
System.out.println(String.format(Locale.US, "%.0f", 12.5));  // 13
System.out.println(String.format(Locale.US, "%8.2f", 12.5)); // "   12.50"
System.out.println(String.format(Locale.US, "%,.2f", 1234.5)); // 1,234.50
~~~

Đối với `%f`:

- Không ghi precision: mặc định **6 chữ số sau dấu thập phân**.
- `%.2f`: hiển thị **2 chữ số sau dấu thập phân**; làm tròn để biểu diễn theo độ chính xác đó và thêm số 0 ở cuối nếu cần.
- `%.0f`: không in chữ số sau dấu thập phân, không có nghĩa làm thay đổi giá trị trong biến gốc.
- `%8.2f`: số 8 là độ rộng tối thiểu của cả trường, kể cả dấu âm hoặc dấu chấm; số 2 là số chữ số sau dấu thập phân.
- `%,.2f`: bổ sung ký tự phân nhóm, với ký tự cụ thể tùy locale.

Không dùng `%f` trực tiếp cho số nguyên `int`: `String.format("%f", 12)` bị lỗi loại đối số. Nếu mục đích là biểu diễn `12.00`, truyền `12.0`, ép sang `double` hoặc dùng `BigDecimal`.

**Về độ chính xác:** `double` lưu số theo nhị phân nên nhiều số thập phân (như `1.005`) không được biểu diễn chính xác tuyệt đối. `%.2f` quyết định cách **hiển thị**, không biến số nhị phân thành số thập phân chính xác và không thay thế quy tắc làm tròn tiền tệ. Với bài toán cần giá trị thập phân chính xác, cân nhắc `BigDecimal` tạo từ chuỗi và quy định rõ cách làm tròn trong tính toán; còn để hiển thị tiền theo vùng, `NumberFormat` có thể phù hợp hơn.

## 8. `%e`: số thực theo ký hiệu khoa học

`%e` nhận cùng nhóm đối số số thực với `%f`, nhưng dùng dạng **scientific notation**:

~~~text
mantissa e exponent
~~~

Ví dụ, `1250.0 = 1.25 × 10³`, nên:

~~~java
System.out.println(String.format(Locale.US, "%e", 1250.0));
// 1.250000e+03

System.out.println(String.format(Locale.US, "%.2e", 1250.0));
// 1.25e+03

System.out.println(String.format(Locale.US, "%.2e", 0.00125));
// 1.25e-03

System.out.println(String.format(Locale.US, "%.2E", 1250.0));
// 1.25E+03
~~~

Tương tự `%f`, precision mặc định của `%e` là **6 chữ số sau dấu thập phân trong phần hệ số (mantissa)**; `%.2e` cho hai chữ số sau dấu thập phân. `e`/`E` là ký hiệu số mũ, dấu `+`/`-` là dấu của số mũ, còn `03` có nghĩa số mũ là ba, được trình bày tối thiểu hai chữ số.

`%e` đặc biệt hữu ích khi dữ liệu rất lớn/nhỏ (thống kê, đo lường, tính toán khoa học); `%f` dễ đọc hơn khi giá trị nằm trong khoảng quen thuộc và người xem muốn một số chữ số thập phân cố định.

Ví dụ lựa chọn cách hiển thị cùng một số:

~~~java
double value = 0.0000125;
System.out.println(String.format(Locale.US, "%.8f", value));
// 0.00001250

System.out.println(String.format(Locale.US, "%.2e", value));
// 1.25e-05
~~~

Cả hai chỉ thay đổi biểu diễn văn bản của cùng `double`; không thay đổi biến `value`.

## 9. Bảng đối chiếu sáu conversion

| Conversion | Ý nghĩa | Đối số thường dùng | Ví dụ và kết quả với Locale.US |
|---|---|---|---|
| `%s` | Chuỗi/biểu diễn đối tượng | `String`, mọi đối tượng (kể cả null) | `"%s", "Java"` → `Java` |
| `%c` | Ký tự / mã điểm Unicode hợp lệ | `char`, `Character`, `byte`/`short`/`int` tương ứng | `"%c", 'A'` → `A` |
| `%b` | Boolean theo quy tắc Formatter | `boolean`, `Boolean`, bất kỳ đối tượng | `"%b", 0` → `true` |
| `%d` | Số nguyên thập phân | `byte`, `short`, `int`, `long`, `BigInteger` | `"%05d", 42` → `00042` |
| `%f` | Số thực dạng cố định | `float`, `double`, `BigDecimal` | `"%.2f", 12.5` → `12.50` |
| `%e` | Số thực dạng khoa học | `float`, `double`, `BigDecimal` | `"%.2e", 1250.0` → `1.25e+03` |

Các conversion viết hoa tương ứng `%S`, `%C`, `%B` và `%E` thay đổi cách trình bày chữ hoa; `%d` và `%f` không có dạng `%D` hoặc `%F` tương đương trong `Formatter`.

Lựa chọn theo bản chất dữ liệu: ký tự dùng `%c`; boolean dùng `%b`; số nguyên dùng `%d`; số thực cần hai chữ số thập phân dùng `%.2f`; số rất nhỏ/lớn có thể dùng `%.2e`; dữ liệu cần hiển thị dưới dạng văn bản chung dùng `%s`.

## 10. Thứ tự đối số, tái sử dụng và ký tự đặc biệt

### 10.1. Đổi thứ tự với `n$`

Theo mặc định, conversion nhận đối số theo thứ tự xuất hiện. Với `%1$s`, `%2$d`,... ta có thể chỉ định trực tiếp vị trí đối số (bắt đầu từ 1):

~~~java
String text = String.format(Locale.US,
        "%2$s has %1$d points", 95, "Lan");
System.out.println(text);
// Lan has 95 points
~~~

Đây là lựa chọn hữu ích khi bản dịch giữa các ngôn ngữ cần đảo trật tự thành phần câu. Cần đảm bảo chỉ số và kiểu conversion khớp đối số thật.

### 10.2. Tái sử dụng với `<`

Flag `<` dùng lại đối số của format specifier **trước đó**:

~~~java
System.out.println(String.format(Locale.US, "%d / %<d", 7));
// 7 / 7
~~~

Không dùng `%<d` ở vị trí đầu tiên khi chưa có đối số trước đó để tái sử dụng.

### 10.3. In dấu phần trăm và xuống dòng

`%%` biểu diễn **dấu `%` nguyên văn**; `%n` tạo dấu xuống dòng theo nền tảng. Cả hai **không sử dụng một đối số giá trị**:

~~~java
System.out.printf(Locale.US, "Completed: %d%%%n", 75);
// Completed: 75%
// (sau đó xuống dòng theo hệ điều hành)
~~~

`%n` phù hợp khi in ra console hoặc xây dựng văn bản phụ thuộc quy ước xuống dòng của nền tảng. Đối với chuỗi chuẩn giao thức yêu cầu rõ `\n`, nên sử dụng ký tự newline chuẩn mà giao thức yêu cầu, không mặc định thay bằng `%n`.

## 11. Locale và định dạng số

Cùng format `%,.2f` nhưng hai locale có thể cho hai cách viết khác nhau:

~~~java
double amount = 1234.5;

System.out.println(String.format(Locale.US, "%,.2f", amount));
// 1,234.50

System.out.println(String.format(Locale.GERMANY, "%,.2f", amount));
// 1.234,50
~~~

Locale ảnh hưởng đến dấu thập phân, phân nhóm và một số quy tắc ngôn ngữ. Đối với log, file trao đổi máy hoặc test có kỳ vọng chính xác, chọn locale tường minh phù hợp (chẳng hạn `Locale.US` hoặc `Locale.ROOT` theo quy ước định dạng mong muốn). Khi hiển thị cho người dùng, sử dụng locale phù hợp với họ.

Không tự ghép `String.format("%.2f", amount)` vào định dạng cần máy đọc nếu không kiểm soát locale: trong một locale, dấu phẩy có thể là dấu thập phân, làm người nhận hiểu sai dữ liệu. Đồng thời, `%s` và các conversion kể trên không tự mã hóa dấu nháy/escape cho CSV, JSON, SQL hay HTML.

## 12. Ví dụ hoàn chỉnh Java 17+

Tạo tệp **`FormatterConversionsDemo.java`**:

~~~java
import java.util.Locale;

public class FormatterConversionsDemo {
    public static void main(String[] args) {
        String name = "Linh";
        char grade = 'A';
        boolean active = true;
        long count = 1_234_567L;
        double price = 1234.5;
        double tiny = 0.00125;

        System.out.printf(Locale.US, "text: %s%n", name);
        System.out.printf(Locale.US, "char: %c%n", grade);
        System.out.printf(Locale.US, "bool: %b%n", active);
        System.out.printf(Locale.US, "decimal: %,d%n", count);
        System.out.printf(Locale.US, "fixed: %,.2f%n", price);
        System.out.printf(Locale.US, "scientific: %.2e%n", tiny);

        System.out.printf(Locale.US,
                "alignment: |%-8.3s|%05d|%n", "Spring", 42);
        System.out.printf(Locale.US,
                "reordered: %2$s=%1$d%n", 9, "id");

        String summary = String.format(
                Locale.US, "%s: %.2f", "Total", 12.5);
        System.out.println(summary);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FormatterConversionsDemo.java
java FormatterConversionsDemo
~~~

Đầu ra khi dùng `Locale.US`:

~~~text
text: Linh
char: A
bool: true
decimal: 1,234,567
fixed: 1,234.50
scientific: 1.25e-03
alignment: |Spr     |00042|
reordered: id=9
Total: 12.50
~~~

Đối chiếu kết quả:

1. `%s` chèn `Linh`, `%c` chèn `A`, `%b` chèn `true`.
2. `%,d` phân nhóm số nguyên: `1,234,567`.
3. `%,.2f` biểu diễn số thực hai chữ số thập phân và phân nhóm: `1,234.50`.
4. `%.2e` chuẩn hóa số nhỏ thành hệ số và số mũ: `1.25e-03`.
5. `%-8.3s` cắt `Spring` còn `Spr` rồi thêm 5 dấu cách ở phải để rộng 8; `%05d` đệm số 0 để số `42` có độ rộng 5.
6. `%2$s=%1$d` lấy đối số thứ hai `id` trước rồi lấy đối số thứ nhất `9`; `String.format` tạo `Total: 12.50` mà không in cho tới khi gọi `println`.

Các câu lệnh `System.out.printf` và `System.out.println` tạo xuống dòng như trong đầu ra. Không cần thư viện ngoài JDK.

## 13. Lỗi phổ biến và cách xử lý

### 13.1. Conversion không phù hợp kiểu đối số

Những lời gọi này **biên dịch được nhưng ném ngoại lệ khi chạy**:

~~~java
// String.format("%d", "42");  // IllegalFormatConversionException
// String.format("%f", 42);    // IllegalFormatConversionException
// String.format("%c", "A");   // IllegalFormatConversionException
~~~

Cách sửa là truyền đúng loại dữ liệu hoặc chủ động chuyển đổi sau khi kiểm tra đầu vào; ví dụ `Integer.parseInt("42")` nếu muốn hiển thị dưới dạng số nguyên thật sự. Không thay mọi conversion bằng `%s` chỉ để giấu lỗi nếu bài toán yêu cầu định dạng số.

### 13.2. Số lượng đối số không đủ

~~~java
// String.format("%s %d", "Java");
// MissingFormatArgumentException: chưa có đối số cho %d
~~~

Kiểm tra đủ đối số, thứ tự và các chỉ số `n$`. Lưu ý `%%` và `%n` không chiếm vị trí một đối số.

### 13.3. Nhầm width với precision

- `%8s`: độ rộng **ít nhất 8**, không cắt chuỗi.
- `%.3s`: chỉ lấy tối đa 3 ký tự trong kết quả `%s`.
- `%8.2f`: độ rộng ít nhất 8, với 2 chữ số thập phân.
- `%03d`: số nguyên có trường rộng 3 và được đệm số 0.
- `%.3d`: **sai** trong Java Formatter; `%d` không hỗ trợ precision.

### 13.4. Đặt flag hoặc precision không hợp lệ

Không phải flag nào cũng hợp lệ cho mọi conversion. Ví dụ, `%05s` không hợp lệ vì flag `0` dùng để đệm số, không dùng để đệm chuỗi kiểu `%s`. `%.2c` và `%.2d` không hợp lệ vì hai conversion này không chấp nhận precision. Java sẽ phát sinh các ngoại lệ thuộc họ `IllegalFormatException` (ví dụ `FormatFlagsConversionMismatchException` hoặc `IllegalFormatPrecisionException`), thay vì bỏ qua tùy chọn sai.

### 13.5. Cho rằng `%b` là phép chuyển đổi boolean theo nghiệp vụ

`String.format("%b", 0)` cho `true` vì `Integer` là một đối tượng không null. Để hiển thị ý nghĩa “số lượng có lớn hơn 0 không”, hãy định dạng biểu thức `quantity > 0`.

### 13.6. Cho rằng định dạng thay đổi dữ liệu gốc hoặc đủ để giải quyết bài toán tiền tệ

~~~java
double x = 12.5;
String display = String.format(Locale.US, "%.2f", x);
// display = "12.50", còn x vẫn bằng 12.5
~~~

`Formatter` tạo biểu diễn văn bản. Nó không làm thay đổi `x`, không tự kiểm tra đơn vị tiền và không xử lý các quy tắc làm tròn phức tạp của nghiệp vụ. Đừng dùng chuỗi đã định dạng như nguồn sự thật để tính toán tiếp.

### 13.7. Không kiểm soát locale

`String.format("%,.2f", value)` có thể cho dấu phân nhóm và dấu thập phân khác nhau ở các máy. Với output cần so sánh nguyên văn trong test hoặc truyền giữa hệ thống, chọn locale tường minh và quy ước encoding/format cụ thể.

## 14. Cách chọn conversion khi viết chương trình

Khi định dạng giá trị, hãy xác định loại dữ liệu thật và mục đích hiển thị trước:

- Dữ liệu văn bản/đối tượng: `%s`; dùng width, alignment, precision khi cần cột hoặc rút gọn.
- Một ký tự hoặc mã điểm Unicode: `%c`; không truyền `String` thay cho `char`.
- Điều kiện boolean đã được tính: `%b`.
- Số nguyên: `%d`; dùng `%05d` cho đệm 0 theo chiều rộng, `%,d` cho phân nhóm theo locale.
- Số thực ở dạng thông thường: `%f` hoặc `%.2f`; precision kiểm soát chữ số sau dấu thập phân.
- Số thực dạng khoa học: `%e` hoặc `%.2e`; phù hợp với giá trị rất lớn/nhỏ.

Cuối cùng, kiểm tra thứ tự đối số, loại dữ liệu, locale, ý nghĩa width/precision và các dấu `%%`, `%n`. Những kiểm tra này giúp chuỗi hiển thị nhất quán và tránh các lỗi `Formatter` chỉ xuất hiện khi chạy chương trình.
