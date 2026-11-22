# String.format, printf và Formatter trong Java

Trong Java, biểu diễn số trong bộ nhớ và **trình bày số thành văn bản** là hai vấn đề khác nhau. Cùng một giá trị `12345.678` có thể được hiển thị dưới dạng `12,345.68`, `12.345,68` hoặc `1.235e+04` tùy **mẫu định dạng, Locale và mục đích sử dụng**.

Ba API liên quan chặt chẽ nhưng không đồng nhất:

- **`String.format(...)`**: định dạng các đối số thành **một `String` mới**, không tự in ra console.
- **`System.out.printf(...)`** (hoặc `PrintStream.printf`): **định dạng và ghi ngay** vào luồng đầu ra; trả lại `PrintStream` để có thể gọi nối tiếp.
- **`java.util.Formatter`**: đối tượng định dạng có trạng thái, ghi vào một `Appendable` như `StringBuilder`, một luồng hoặc đích được hỗ trợ. Phù hợp khi muốn tái sử dụng bộ định dạng hoặc kiểm soát nơi nhận văn bản.

Cả ba dựa trên **cú pháp format string của `Formatter`**, như `%d`, `%.2f`, `%,.2f`, `%e`. Việc định dạng **không làm thay đổi giá trị số nguồn**, nhưng chuỗi kết quả có thể đã làm tròn hoặc thay ký hiệu dấu thập phân theo Locale.

## 1. Ba API khác nhau ở hành động nào?

### `String.format` tạo chuỗi

```java
import java.util.Locale;

double amount = 1234.567;
String text = String.format(Locale.US, "%,.2f", amount);
System.out.println(text); // 1,234.57
```

`text` chứa chuỗi `"1,234.57"`. Biến `amount` vẫn mang giá trị số cũ. `String.format` **không tự in**; việc in là câu lệnh `System.out.println` riêng.

Có hai overload quen thuộc:

```java
String a = String.format("%.2f", 1.5); // dùng Locale mặc định của môi trường
String b = String.format(Locale.US, "%.2f", 1.5); // dùng Locale.US
```

Nếu kết quả phải có dạng nhất quán trong log máy, xuất dữ liệu hoặc kiểm thử, **truyền Locale rõ ràng** thay vì dựa vào Locale mặc định thay đổi theo máy.

### `printf` định dạng và in ra luồng

```java
System.out.printf(Locale.US, "Total: %.2f%n", 1234.5);
```

Kết quả hiển thị:

```text
Total: 1234.50
```

`printf` không “tạo một String để bạn tự dùng” như `String.format`; nó ghi vào `System.out`. Trong `PrintStream`, `printf` trả lại chính luồng đó. Khi gọi nhiều lần, cần xác định xuống dòng bằng `%n`, `println` hoặc cấu trúc thông điệp thích hợp; `printf` không mặc định tự thêm newline.

### `Formatter` ghi vào một đích và có thể dùng nhiều lượt

```java
import java.util.Formatter;
import java.util.Locale;

StringBuilder buffer = new StringBuilder();
try (Formatter formatter = new Formatter(buffer, Locale.US)) {
    formatter.format("Price: %.2f", 12.5);
    formatter.format(" | Qty: %d", 3);
}
System.out.println(buffer); // Price: 12.50 | Qty: 3
```

`Formatter` thực hiện nhiều lệnh `format` trên cùng đích `StringBuilder`. Sau khi đóng formatter, `StringBuilder` còn chứa nội dung đã ghi và có thể đọc được. Nên đóng đối tượng do bạn tạo nếu nó sở hữu tài nguyên; với formatter ghi vào stream/file, cần chú ý cách đóng có thể ảnh hưởng đích. **Không chủ động đóng `System.out`** chỉ vì muốn ngừng định dạng.

## 2. Cấu trúc một format specifier

Mẫu tổng quát cho một conversion dùng đối số:

```text
%[argument_index$][flags][width][.precision]conversion
```

Các phần là tùy chọn, nhưng `%` mở đầu và **conversion** xác định cách biểu diễn. Ví dụ:

```text
%1$+08d
││ │ │ └─ d: số nguyên thập phân
││ │ └── 8: độ rộng tối thiểu
││ └──── + và 0: luôn in dấu; đệm zero
│└─────── 1$: dùng đối số thứ nhất
└──────── %: bắt đầu specifier
```

Trong `"%1$+08d"`, đối số thứ nhất là một số nguyên; với `42`, kết quả là `+0000042` (8 ký tự).

Các thành phần:

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| `argument_index$` | Chọn đối số bắt đầu từ 1 thay vì theo thứ tự mặc định | `%2$s` |
| `flags` | Quy định dấu, đệm, căn lề, grouping, dạng thay thế... | `+`, `0`, `-`, `,`, `(`, `#` |
| `width` | Độ rộng **tối thiểu**; không tự cắt chuỗi dài hơn | `%8d` |
| `.precision` | Ý nghĩa tùy conversion: số chữ số phần lẻ hoặc chữ số có nghĩa, giới hạn chuỗi... | `%.2f`, `%.4g` |
| `conversion` | Kiểu hiển thị mong muốn | `d`, `f`, `e`, `g`, `x`, `s` |

**Không phải mọi flag và precision đều hợp lệ với mọi conversion.** Ví dụ `%.2d` không phải cách hợp lệ để yêu cầu “hai chữ số phần lẻ của số nguyên” và có thể ném `IllegalFormatPrecisionException`.

## 3. Các conversion số nguyên thường dùng

| Conversion | Ý nghĩa | Ví dụ theo Locale.US |
| --- | --- | --- |
| `%d` | Số nguyên hệ 10 | `String.format("%d", 42)` → `"42"` |
| `%x` | Số nguyên hệ 16, chữ thường | `String.format("%x", 255)` → `"ff"` |
| `%X` | Số nguyên hệ 16, chữ hoa | `String.format("%X", 255)` → `"FF"` |
| `%o` | Số nguyên hệ 8 | `String.format("%o", 8)` → `"10"` |
| `%#x` | Dạng hệ 16 có tiền tố | `String.format("%#x", 255)` → `"0xff"` |
| `%,d` | Hệ 10 có grouping theo Locale | `String.format(Locale.US, "%,d", 1234567)` → `"1,234,567"` |
| `%+d` | Luôn in dấu `+` hoặc `-` | `42` → `"+42"` |
| `%(d` | Số âm trong ngoặc | `-42` → `"(42)"` |
| `%05d` | Độ rộng ít nhất 5, đệm số 0 | `-42` → `"-0042"` |

`%d` phù hợp cho các kiểu nguyên, bao gồm wrapper tương ứng và `BigInteger`. Không thể truyền một `double` vào `%d` rồi hy vọng formatter tự cắt phần thập phân:

```java
// String.format("%d", 3.5); // IllegalFormatConversionException
String correct = String.format(Locale.US, "%.0f", 3.5); // "4"
```

Đây là **làm tròn khi hiển thị dưới dạng số thực**, không phải cast `double` thành `int`. Với đối số âm hoặc số rất lớn, quy tắc định dạng và ép kiểu có thể khác nhau rõ rệt.

### Căn lề, width và zero-padding

```java
String right = String.format(Locale.US, "|%6d|", 42);
// "|    42|": căn phải trong ít nhất 6 ký tự

String left = String.format(Locale.US, "|%-6d|", 42);
// "|42    |": căn trái trong ít nhất 6 ký tự

String zeroFilled = String.format(Locale.US, "%+08d", 42);
// "+0000042": có dấu và đệm zero
```

`width` chỉ là **chiều rộng tối thiểu**, nên chuỗi đầu ra dài hơn width vẫn được in đầy đủ; formatter không tự cắt bớt phần số. Nếu format gây khó đọc hoặc dùng để truyền dữ liệu có độ dài cố định, phải kiểm tra độ dài sau định dạng riêng theo contract.

## 4. Các conversion cho số thực `float`/`double` và `BigDecimal`

| Conversion | Ý nghĩa | Mẫu điển hình |
| --- | --- | --- |
| `%f` | Dạng dấu phẩy động thập phân thường | `%.2f` |
| `%e` hoặc `%E` | Ký hiệu khoa học với số mũ | `%.3e` |
| `%g` hoặc `%G` | Dạng tổng quát: dùng định dạng thường hoặc khoa học tùy giá trị/precision | `%.4g` |
| `%a` hoặc `%A` | Dạng số thực **hexadecimal floating point** | `%a` với `double` |
| `%,.2f` | Phân nhóm và hai chữ số thập phân theo Locale | `%,.2f` |
| `%(,.2f` | Phân nhóm; số âm trong ngoặc | `%(,.2f` |

Ví dụ cụ thể:

```java
String fixed = String.format(Locale.US, "%.2f", 12.345);
// "12.35"

String science = String.format(Locale.US, "%.3e", 12345.6);
// "1.235e+04"

String general = String.format(Locale.US, "%.4g", 12345.6);
// "1.235e+04"

String hexadecimal = String.format(Locale.US, "%a", 3.5);
// "0x1.cp1"
```

**Precision không có cùng ý nghĩa giữa `%f` và `%g`**:

- `%.2f` yêu cầu **2 chữ số sau dấu thập phân** của biểu diễn.
- `%.4g` yêu cầu **4 chữ số có nghĩa** trong biểu diễn tổng quát; formatter chọn dạng thường/khoa học phù hợp.
- `%.3e` yêu cầu **3 chữ số sau dấu thập phân của mantissa** trong dạng khoa học.

Các giá trị số thực đặc biệt như `Double.NaN` và `Double.POSITIVE_INFINITY` có thể được in dưới dạng `NaN` và `Infinity`, tùy hoa/thường theo conversion. `-0.0` cũng có thể giữ dấu khi in:

```java
System.out.println(String.format(Locale.US, "%.2f", -0.0));
// -0.00
```

`BigDecimal` dùng được với nhiều conversion thập phân (`%f`, `%e`, `%g`), nhưng `%a` dành cho biểu diễn hex của các kiểu dấu phẩy động nhị phân và **không hỗ trợ `BigDecimal` như một chuyển đổi tương đương**.

## 5. Rounding khi định dạng không đổi giá trị nguồn

`String.format` và `printf` có thể **làm tròn phần văn bản được hiển thị** khi precision yêu cầu ít chữ số hơn, nhưng không sửa giá trị lưu trong biến.

```java
double value = 12.3456;
String display = String.format(Locale.US, "%.2f", value);

System.out.println(display); // 12.35
System.out.println(value);   // 12.3456
```

Với số thập phân cần chính xác (ví dụ những khoản tiền đã chốt), có thể tạo `BigDecimal` từ chuỗi:

```java
java.math.BigDecimal exact = new java.math.BigDecimal("2.345");
String display = String.format(Locale.US, "%.2f", exact);
// "2.35"
```

Không nên tự suy ra rằng dùng `%.2f` cho mọi phép tính tiền là đủ: formatter **chỉ tạo văn bản**; việc xác định thời điểm chốt khoản tiền, scale, rounding mode và số liệu được ghi nhận là trách nhiệm của **nghiệp vụ**.

`Math.round`, `BigDecimal.setScale` và `String.format` không phải ba cách thay thế tùy ý cho một yêu cầu. Một bước định dạng có thể làm tròn chỉ **để in** mà không thay đổi giá trị tính toán tiếp theo. Nếu hợp đồng yêu cầu biến số đã được làm tròn chính thức, cần thao tác kiểu số thích hợp rồi lưu kết quả đã chốt.

### Chú ý sai số nhị phân

`double` không thể biểu diễn chính xác mọi số thập phân. `%.2f` có thể hiển thị một giá trị trông “đẹp”, nhưng đó không phải chứng cứ rằng số thập phân nguồn được biểu diễn và tính toán chính xác đến hai chữ số.

Không nên dùng định dạng rồi `Double.parseDouble(...)` chuỗi đã in để “sửa sai số” trong mọi tình huống: việc ấy có thể tạo thêm một phép làm tròn không được yêu cầu, và nếu chuỗi định dạng phụ thuộc Locale thì việc parse bằng `Double.parseDouble` còn có thể thất bại.

## 6. `Locale` ảnh hưởng trực tiếp định dạng số

`Locale` quy định nhiều đặc điểm biểu diễn văn bản, trong đó có dấu thập phân và dấu phân nhóm chữ số. So sánh:

```java
String us = String.format(Locale.US, "%,.2f", 12345.67);
String germany = String.format(Locale.GERMANY, "%,.2f", 12345.67);

// us:      "12,345.67"
// germany: "12.345,67"
```

Các chuỗi khác nhau dù **giá trị `double` như nhau**. `Locale` làm thay đổi **văn bản**, không thay đổi số học của biểu thức trước khi truyền cho formatter.

Vì thế:

- **Giao diện người dùng:** chọn Locale phù hợp với người dùng hoặc quy tắc sản phẩm.
- **Giao thức, CSV có schema, log máy và golden tests:** chọn Locale cố định, ví dụ `Locale.US` hoặc `Locale.ROOT` tùy contract.
- **Đọc lại chuỗi:** không mặc định `Double.parseDouble` sẽ hiểu dấu phẩy thập phân và phân nhóm. `Double.parseDouble("12.345,67")` không phải cách parse phù hợp.

Không nên tự thay dấu phẩy thành dấu chấm một cách máy móc: một chuỗi như `"1,234"` có thể mang nghĩa **một nghìn hai trăm ba mươi bốn** hoặc **một phẩy hai ba bốn**, tùy Locale và hợp đồng. Khi cần parse chuỗi do người dùng nhập, dùng parser được cấu hình Locale và kiểm tra **toàn bộ đầu vào**.

### Locale mặc định có thể thay đổi

`String.format("%.2f", value)` và `System.out.printf("%.2f", value)` sử dụng Locale phù hợp với môi trường hoặc cấu hình hiện hành; đầu ra có thể khác theo nơi chạy. Tránh dựa vào kết quả mặc định trong test snapshot hoặc định dạng dữ liệu liên hệ thống.

## 7. Argument index, tái sử dụng và thứ tự đối số

Thông thường conversion lấy đối số theo thứ tự:

```java
String text = String.format(Locale.US, "%s=%d", "count", 7);
// "count=7"
```

`%n$` cho phép chọn đối số thứ `n` (chỉ số bắt đầu từ **1**):

```java
String reversed = String.format(Locale.US, "%2$s=%1$04d", 7, "n");
// "n=0007"
```

Flag `<` **tái sử dụng đối số được dùng bởi format specifier trước đó**:

```java
String bothBases = String.format(Locale.US, "%1$d / %<x", 31);
// "31 / 1f"
```

Rất dễ nhầm giữa **đối số thứ hai** và **chỉ số bắt đầu từ 0**. `%2$s` là đối số thứ hai, không phải đối số ở vị trí 2 trong mảng Java.

Đừng dùng cú pháp chỉ số và flag `<` khi nó khiến mẫu trở nên khó kiểm toán. Với code quan trọng, tên biến rõ ràng và format đơn giản thường dễ bảo trì hơn so với một chuỗi ghép nhiều chỉ số thủ công.

## 8. `%s`, `%%`, `%n` và ký tự đặc biệt

Các conversion ngoài số vẫn rất cần thiết:

| Conversion | Công dụng | Ví dụ |
| --- | --- | --- |
| `%s` | Biểu diễn đối tượng thành chuỗi | `String.format("%s", "cat")` → `"cat"` |
| `%.3s` | Giới hạn chuỗi tối đa 3 ký tự | `"abcdef"` → `"abc"` |
| `%b` | Biểu diễn boolean-like | `true` → `"true"`; tham chiếu `null` → `"false"` |
| `%c` | Ký tự | `'A'` → `"A"` |
| `%%` | In dấu phần trăm literal | `"Discount: 10%%"` → `"Discount: 10%"` |
| `%n` | Ký tự xuống dòng theo nền tảng | Khác cách cố định viết `\n` trong chuỗi |

Ví dụ:

```java
String percent = String.format(Locale.US, "Discount: %d%%", 10);
// "Discount: 10%"

String row = String.format(Locale.US, "A%nB");
// có một xuống dòng phụ thuộc nền tảng giữa A và B
```

**`%n` không dùng đối số.** Với nội dung văn bản nhiều dòng có yêu cầu byte-for-byte cố định qua mọi hệ điều hành, chọn quy ước xuống dòng rõ ràng thay vì mặc định `%n`.

Khi đưa dữ liệu có thể chứa ký tự xuống dòng hoặc định dạng không tin cậy vào log, cũng cần cân nhắc escape và policy logging để tránh log injection; formatter không tự làm sạch toàn bộ dữ liệu.

## 9. Lỗi format string chỉ xuất hiện lúc chạy

Java kiểm tra cú pháp kiểu của lời gọi `String.format`, nhưng không chứng minh tại thời điểm compile rằng chuỗi format và các đối số **luôn tương thích**.

Một số exception của `java.util.IllegalFormatException`:

| Sai sót | Ví dụ | Exception điển hình |
| --- | --- | --- |
| Conversion sai với kiểu đối số | `String.format("%d", 1.25)` | `IllegalFormatConversionException` |
| Thiếu đối số | `String.format("%d %d", 1)` | `MissingFormatArgumentException` |
| Precision không hợp lệ | `String.format("%.2d", 7)` | `IllegalFormatPrecisionException` |
| Conversion không được hỗ trợ | `String.format("%q", 7)` | `UnknownFormatConversionException` |
| Flag không hợp lệ cho conversion | `String.format("%#s", "a")` trong trường hợp đối số không phải `Formattable` | `FormatFlagsConversionMismatchException` |

Các ví dụ trên là những trường hợp **cố tình gây lỗi** để giải thích. Không chạy chúng ngoài cơ chế kiểm thử/bắt lỗi.

```java
try {
    String.format(Locale.US, "%d", 1.25);
} catch (java.util.IllegalFormatException ex) {
    System.out.println("invalid conversion");
}
```

Khi xây dựng API, có thể tránh tạo format string từ dữ liệu không đáng tin cậy. Tách rõ mẫu format do chương trình định nghĩa và **nội dung** người dùng cung cấp:

```java
String userText = "%n%n";
String safeAsArgument = String.format(Locale.US, "Input: %s", userText);
// "Input: %n%n" — userText là dữ liệu %s, không trở thành format string
```

Điều này không thay thế escaping theo ngữ cảnh đầu ra (HTML/SQL/log). Nó chỉ giảm rủi ro khi dữ liệu đầu vào bị diễn giải thành chuỗi format.

### Chú ý `null` và đối số có kiểu khác

`String.format("%s", (Object) null)` có thể hiển thị `"null"`, nhưng `String.format("%d", (Object) null)` hiển thị `"null"` theo quy tắc Formatter của Java cho null, không phải bằng chứng có một số nguyên 0. Nếu nghiệp vụ cấm thiếu dữ liệu, kiểm tra đầu vào trước khi định dạng.

**Không** dùng `%f` để tự động chuyển mọi `Integer` sang số thực. Với `String.format("%.2f", 7)`, đối số là `Integer`, và formatter có thể ném `IllegalFormatConversionException`. Muốn định dạng số thực, truyền `7.0`, `Double.valueOf(7)` hoặc `BigDecimal` phù hợp.

## 10. Thiết kế đầu ra ổn định và rõ nghĩa

Có thể phân loại theo mục tiêu:

| Mục tiêu | Gợi ý |
| --- | --- |
| Chuỗi ngắn để hiển thị | `String.format(locale, pattern, args)` |
| In trực tiếp console | `System.out.printf(locale, pattern, args)` |
| Nhiều lần append vào một bộ đệm | `Formatter` với `StringBuilder` |
| Phần trăm và căn cột | `%%`, `width`, flag `-` |
| Báo cáo số có ngăn cách nhóm | `%,d`, `%,.2f` theo Locale |
| Trao đổi dữ liệu máy-máy | Cố định Locale/cú pháp; tốt hơn dùng serializer đúng schema thay vì format tùy ý |
| Giá trị tiền thập phân chính xác | Tính toán bằng kiểu/phương pháp phù hợp (thường `BigDecimal`), format chỉ tại bước hiển thị |

Một formatter có thể làm tròn **chuỗi được in** nhưng không biến số đo chưa chính xác thành dữ liệu chính xác. Nếu ứng dụng cần lưu giá trị đã chốt theo hợp đồng, chốt bằng thuật toán số và chế độ làm tròn phù hợp, sau đó mới dùng formatter để trình bày.

Không tạo formatter mới nhiều lần trong vòng lặp nóng chỉ vì tiện cú pháp nếu hiệu năng quan trọng; đo lường và cân nhắc `StringBuilder` hay cách ghép chuỗi thích hợp. Dù vậy, ưu tiên đầu tiên vẫn là **đúng định dạng, đúng Locale và rõ hợp đồng**.

## 11. Chương trình Java 17+ chạy độc lập

Tạo file **`NumberFormattingDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Formatter;
import java.util.IllegalFormatException;
import java.util.Locale;

public class NumberFormattingDemo {
    public static void main(String[] args) {
        double amount = 12345.678;
        String text = String.format(Locale.US, "%,.2f", amount);
        System.out.println("formatted=" + text);
        System.out.println("original=" + amount);

        System.out.println("integer=" +
                String.format(Locale.US, "%d", 42));
        System.out.println("hex=" +
                String.format(Locale.US, "%#x", 255));
        System.out.println("octal=" +
                String.format(Locale.US, "%o", 8));
        System.out.println("signed=" +
                String.format(Locale.US, "%+08d", 42));
        System.out.println("negativePadded=" +
                String.format(Locale.US, "%05d", -42));
        System.out.println("leftAligned=" +
                String.format(Locale.US, "|%-6d|", 42));
        System.out.println("groupInteger=" +
                String.format(Locale.US, "%,d", 1234567));

        System.out.println("scientific=" +
                String.format(Locale.US, "%.3e", 12345.6));
        System.out.println("general=" +
                String.format(Locale.US, "%.4g", 12345.6));
        System.out.println("hexFloat=" +
                String.format(Locale.US, "%a", 3.5));
        System.out.println("negativeParen=" +
                String.format(Locale.US, "%(,.2f", -1234.5));
        System.out.println("negativeZero=" +
                String.format(Locale.US, "%.2f", -0.0));
        System.out.println("specialNaN=" +
                String.format(Locale.US, "%f", Double.NaN));
        System.out.println("specialInfinity=" +
                String.format(Locale.US, "%f", Double.POSITIVE_INFINITY));

        System.out.println("bigDecimal=" +
                String.format(Locale.US, "%.2f",
                        new BigDecimal("2.345")));
        System.out.println("germany=" +
                String.format(Locale.GERMANY, "%,.2f", 12345.67));
        System.out.println("positional=" +
                String.format(Locale.US, "%2$s=%1$04d", 7, "n"));
        System.out.println("reused=" +
                String.format(Locale.US, "%1$d / %<x", 31));
        System.out.println("percent=" +
                String.format(Locale.US, "Discount: %d%%", 10));

        StringBuilder buffer = new StringBuilder();
        try (Formatter formatter = new Formatter(buffer, Locale.US)) {
            formatter.format("item=%s", "pen");
            formatter.format(" qty=%d price=%.2f",
                    3, new BigDecimal("1.25"));
        }
        System.out.println("formatter=" + buffer);

        try {
            String.format(Locale.US, "%d", 1.25);
            System.out.println("invalidFormat=missed");
        } catch (IllegalFormatException ex) {
            System.out.println("invalidFormat=detected");
        }

        System.out.printf(Locale.US, "printfValue=%.2f%n", 2.5);
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac NumberFormattingDemo.java
java NumberFormattingDemo
```

Output với `Locale` được chỉ định và đúng các đối số trên:

```text
formatted=12,345.68
original=12345.678
integer=42
hex=0xff
octal=10
signed=+0000042
negativePadded=-0042
leftAligned=|42    |
groupInteger=1,234,567
scientific=1.235e+04
general=1.235e+04
hexFloat=0x1.cp1
negativeParen=(1,234.50)
negativeZero=-0.00
specialNaN=NaN
specialInfinity=Infinity
bigDecimal=2.35
germany=12.345,67
positional=n=0007
reused=31 / 1f
percent=Discount: 10%
formatter=item=pen qty=3 price=1.25
invalidFormat=detected
printfValue=2.50
```

Để chương trình in thêm một dòng qua `printf`, nó dùng `%n` (xuống dòng của hệ điều hành). Phần văn bản nhìn thấy giống nhau trên các nền tảng phổ biến; **byte của ký tự xuống dòng** có thể khác theo môi trường.

## 12. Lỗi phổ biến và checklist

| Nhận định | Thực tế |
| --- | --- |
| “`String.format` tự in kết quả.” | Sai: nó trả `String`; `printf` ghi vào stream. |
| “`printf` luôn tự xuống dòng.” | Sai: mẫu phải có `%n` hoặc phải in newline riêng. |
| “`%.2f` giúp biến `double` chứa chính xác hai chữ số decimal.” | Sai: định dạng chỉ tạo văn bản; giá trị nguồn không đổi. |
| “`%,.2f` luôn dùng dấu phẩy làm grouping và dấu chấm thập phân.” | Sai: Locale ảnh hưởng cách hiển thị. |
| “`%.4g` có bốn chữ số sau dấu thập phân.” | Sai: `g` dùng precision chữ số có nghĩa. |
| “`%8d` sẽ cắt mọi số dài hơn 8 ký tự.” | Sai: width là **tối thiểu**. |
| “`%d` tự chuyển một `double` thành `int`.” | Sai: có thể ném `IllegalFormatConversionException`. |
| “`%n` giống mọi nơi với ký tự `\n`.” | Sai: `%n` dùng newline nền tảng. |
| “`%2$s` tham chiếu đối số index 2 theo Java zero-based.” | Sai: index bắt đầu từ 1. |
| “`Formatter` chỉ là tên khác của `String.format`.” | Không: nó là đối tượng định dạng với đích và vòng đời sử dụng riêng. |
| “Format string sai sẽ luôn bị compiler bắt.” | Không: nhiều lỗi chỉ ném `IllegalFormatException` lúc chạy. |
| “In `NaN` hoặc `Infinity` nghĩa là parser đầu vào đã sai.” | Không: đây là những giá trị `float`/`double` hợp lệ về biểu diễn; xử lý theo policy. |

Trước khi format số, hãy tự kiểm tra:

1. **Mục tiêu là trả chuỗi, in ra luồng hay ghi bộ đệm?** Chọn `String.format`, `printf` hoặc `Formatter`.
2. **Đối số thực tế thuộc kiểu nào?** Chọn `%d` cho nguyên, `%f`/`%e`/`%g` cho số thực phù hợp, đừng đoán formatter tự ép mọi kiểu.
3. **Độ chính xác có nghĩa gì?** `%.2f` là hai chữ số sau dấu thập phân; `%.4g` là bốn chữ số có nghĩa.
4. **Đầu ra phụ thuộc Locale không?** Cố định Locale trong test, log máy hoặc trao đổi dữ liệu.
5. **Format có thể lỗi lúc chạy không?** Kiểm tra specifier, flag, số đối số và chuyển đổi; test các mẫu quan trọng.
6. **Định dạng có đang bị lẫn với nghiệp vụ làm tròn không?** Không dùng chuỗi đã format thay giá trị tính toán nếu hợp đồng không yêu cầu.
7. **Dữ liệu đặc biệt và âm zero được xử lý thế nào?** Cân nhắc `NaN`, `Infinity`, `-0.0` và giao thức bên ngoài trước khi xuất.

**Ghi nhớ:** `String.format` **trả chuỗi**, `printf` **in ra stream**, còn `Formatter` **định dạng vào một đích cụ thể**. Chúng chia sẻ ngữ pháp `%...` nhưng bạn vẫn phải chọn đúng **conversion, precision, width, flags và Locale**; đồng thời tách việc **trình bày số** khỏi việc **tính toán và làm tròn theo nghiệp vụ**.