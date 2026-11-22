# Formatter nhận Charset cùng Locale trong Java 10: định dạng văn bản và mã hóa đầu ra

*Ngữ cảnh: Java 10 — Charset trong I/O. Bài học tập trung vào những constructor `java.util.Formatter` nhận đồng thời `Charset` và `Locale`, vẫn được hỗ trợ trong Java 17+ và các JDK hiện đại. Các ví dụ chạy được trên Java 17 trở lên.*

## 1. Khái niệm cốt lõi

Khi viết dữ liệu ra tệp hoặc `OutputStream`, có **hai quyết định khác nhau**:

1. **Định dạng nội dung theo vùng/ngôn ngữ — `Locale`:** số `1234.5` sẽ hiển thị là `1,234.50` theo `Locale.US` hay `1.234,50` theo `Locale.GERMANY`? Dấu phân cách hàng nghìn, dấu thập phân, một số dạng chữ số, tên tháng/ngày và chuyển đổi chữ hoa trong một số format specifier phụ thuộc locale.
2. **Mã hóa chuỗi đã định dạng thành byte — `Charset`:** ký tự `é` được ghi thành những byte nào? `UTF-8`, `UTF-16LE` và các bộ mã khác cho biểu diễn byte khác nhau.

Java 10 bổ sung **ba constructor `Formatter`** giúp chỉ định trực tiếp cả hai quyết định:

~~~java
new Formatter(String fileName, Charset charset, Locale locale)
new Formatter(File file, Charset charset, Locale locale)
new Formatter(OutputStream stream, Charset charset, Locale locale)
~~~

Ví dụ ngắn (đặt trong một phương thức có xử lý tài nguyên):

~~~java
try (var formatter = new Formatter(
        outputStream,
        StandardCharsets.UTF_8,
        Locale.GERMANY)) {
    formatter.format("Betrag: %,.2f", 1234.5);
}
~~~

Kết quả văn bản có nội dung `Betrag: 1.234,50` rồi được mã hóa theo **UTF-8** để ghi vào `outputStream`. Dấu `.` và `,` được chọn theo `Locale.GERMANY`; các byte được chọn theo `StandardCharsets.UTF_8`. Đây là hai tầng chức năng độc lập.

**Ghi nhớ:** `Locale` **không phải** charset, và `Charset` **không phải** locale. Đổi `Locale` có thể đổi **ký tự được sinh ra**; đổi `Charset` có thể đổi **byte biểu diễn cùng chuỗi ký tự**.

## 2. `Formatter` là gì, và điều mới của Java 10 là gì?

`java.util.Formatter` là công cụ định dạng có cú pháp tương tự `printf` trong Java. Nó hỗ trợ các format specifier như:

- `%s`: biểu diễn một giá trị dạng chuỗi.
- `%d`: số nguyên dạng thập phân.
- `%f`: số dấu phẩy động dạng thập phân.
- `%,.2f`: số có dấu phân nhóm theo locale và hai chữ số thập phân.
- `%1$s`, `%2$,.2f`: tham chiếu đối số theo chỉ số.
- `%n`: dấu xuống dòng phụ thuộc nền tảng; không phải một chuỗi cố định `\n` trên mọi hệ điều hành.

Ví dụ nội dung định dạng:

~~~java
formatter.format("%s | total=%,.2f | qty=%d",
                 "Café", 1234.5, 7);
~~~

Điều **mới từ Java 10** không phải bản thân `Formatter`: lớp này đã tồn tại từ trước. Phần bổ sung là các constructor chấp nhận tham số **`java.nio.charset.Charset`** trực tiếp cùng với **`Locale`** khi chọn đích là tên tệp, `File` hoặc `OutputStream`.

Trước đó đã có các constructor dùng **tên charset dạng `String`** (ví dụ `"UTF-8"`). Những constructor đó vẫn tồn tại, nhưng cách truyền `StandardCharsets.UTF_8` cho compiler kiểm tra kiểu và tránh chuỗi charset bị gõ sai:

~~~java
// Tương thích với cách dùng cũ; csn là tên charset dạng String:
new Formatter(outputStream, "UTF-8", Locale.US);

// Dạng Java 10+, rõ ràng dùng một Charset object:
new Formatter(outputStream, StandardCharsets.UTF_8, Locale.US);
~~~

Ví dụ là biểu thức constructor minh họa; trong thực tế, hãy đóng `Formatter` đúng phạm vi sở hữu tài nguyên thay vì tạo rồi bỏ tham chiếu.

## 3. Ba overload nhận đồng thời `Charset` và `Locale`

| Constructor | Đích nhận dữ liệu | Điểm cần lưu ý |
| --- | --- | --- |
| `Formatter(String fileName, Charset charset, Locale locale)` | Tệp theo đường dẫn dạng `String` | Có thể tạo mới; **tệp đang tồn tại bị truncate** khi mở thành công; constructor khai báo `throws IOException` |
| `Formatter(File file, Charset charset, Locale locale)` | Một đối tượng `java.io.File` | Tương tự; có thể tạo/tái mở tệp và ghi đè nội dung cũ; khai báo `throws IOException` |
| `Formatter(OutputStream os, Charset charset, Locale locale)` | Luồng byte đã có | Chuyển ký tự thành byte bằng charset được truyền; không khai báo checked IOException ở constructor |
| `Formatter(Appendable a, Locale locale)` | Đối tượng nhận **ký tự** (ví dụ `StringBuilder` hoặc `Writer`) | **Không có tham số Charset** ở constructor này; mã hóa chỉ có ý nghĩa nếu `Appendable` được nối tới byte |
| `Formatter(Locale locale)` | Bộ đệm ký tự nội bộ | Chỉ định locale; không viết byte vào tệp/stream |

**Không có constructor `Formatter(Writer, Charset, Locale)`** để chỉ định charset một lần nữa cho `Writer`. Một `Writer` đã là đích nhận ký tự; nếu nó là `OutputStreamWriter` thì charset đã được chọn khi xây dựng writer. Với `StringBuilder` hay `StringWriter`, kết quả còn là ký tự trong bộ nhớ, chưa có bước chuyển byte.

Tài liệu Java hiện hành đánh dấu các overload `(String,Charset,Locale)`, `(File,Charset,Locale)` và `(OutputStream,Charset,Locale)` bằng `Since: 10`.

### 3.1. Truyền `Locale` như thế nào?

~~~java
Locale.US
Locale.GERMANY
Locale.FRANCE
Locale.forLanguageTag("vi-VN")
~~~

Ví dụ `Locale.forLanguageTag("vi-VN")` tạo locale theo BCP 47 cho tiếng Việt tại Việt Nam. Khi dùng locale tùy biến, kết quả cụ thể của một số phép định dạng phụ thuộc các quy tắc/dữ liệu locale được hỗ trợ trên runtime. Đối với đầu ra cần bit-for-bit cố định giữa các môi trường, đừng tự dựa vào locale default hoặc bảng định dạng có thể thay đổi giữa các bản dữ liệu locale.

Nếu `locale` là `null` trong các constructor tương ứng, hợp đồng `Formatter` cho phép **không áp dụng localization** thay vì mặc định mọi trường hợp phải ném `NullPointerException`. Ngược lại, `Charset` đối với ba overload Java 10 **không được null**; các đích file/stream liên quan cũng không được null.

### 3.2. `Locale` không dịch nội dung

~~~java
try (var f = new Formatter(outputStream,
                           StandardCharsets.UTF_8,
                           Locale.GERMANY)) {
    f.format("Total: %,.2f", 1234.5);
}
~~~

Locale có thể tạo `Total: 1.234,50`, nhưng nó **không dịch** chữ `Total` thành tiếng Đức. Chuỗi văn bản thường như nhãn, tiêu đề hoặc mô tả phải được bản địa hóa riêng bằng resource bundle hoặc dữ liệu bản dịch phù hợp.

Vì vậy, **i18n** thường gồm nhiều việc: dịch nhãn, quy tắc hiển thị số/ngày, múi giờ, tiền tệ, thứ tự câu, và mã hóa. Constructor này chỉ giải quyết phần **định dạng theo locale và charset tại đầu ra**.

## 4. Chuỗi xử lý bên trong — từ giá trị thành byte

Một mô hình tư duy hữu ích:

~~~text
Giá trị Java:
    amount = 1234.5, label = "Café"
           |
           v
Formatter.format(...) + Locale.US
           |
           v
Ký tự: "Café | amount=1,234.50"
           |
           v
Encoder sử dụng Charset UTF-8
           |
           v
Byte được ghi vào OutputStream
~~~

Đổi sang `Locale.GERMANY` với cùng `Charset.UTF_8` (thực tế hằng là `StandardCharsets.UTF_8`):

~~~text
Giá trị Java:
    amount = 1234.5, label = "Café"
           |
           v
Formatter.format(...) + Locale.GERMANY
           |
           v
Ký tự: "Café | amount=1.234,50"
           |
           v
Encoder sử dụng Charset UTF-8
           |
           v
Byte được ghi vào OutputStream
~~~

Ký tự của số khác nhau **trước** khi encode. Nếu giữ `Locale.US` nhưng thay `UTF-8` bằng `UTF-16LE`, văn bản sau khi **giải mã đúng charset** vẫn có thể là `Café | amount=1,234.50`, song **byte khác nhau**.

Tư duy đúng là **giá trị → ký tự được format → byte được encode**. Không đảo hai công đoạn, không trông đợi charset quyết định dấu thập phân hoặc locale quyết định byte UTF-8.

## 5. Ví dụ: cùng UTF-8, hai locale

### 5.1. Đầu ra theo US

~~~java
var bytes = new ByteArrayOutputStream();
try (var formatter = new Formatter(
        bytes, StandardCharsets.UTF_8, Locale.US)) {
    formatter.format("Café | amount=%,.2f | count=%d", 1234.5, 7);
}

var text = new String(bytes.toByteArray(), StandardCharsets.UTF_8);
// text là "Café | amount=1,234.50 | count=7"
~~~

### 5.2. Đầu ra theo Đức

~~~java
var bytes = new ByteArrayOutputStream();
try (var formatter = new Formatter(
        bytes, StandardCharsets.UTF_8, Locale.GERMANY)) {
    formatter.format("Café | amount=%,.2f | count=%d", 1234.5, 7);
}

var text = new String(bytes.toByteArray(), StandardCharsets.UTF_8);
// text là "Café | amount=1.234,50 | count=7"
~~~

Hai đoạn trên đều là code đặt trong một phương thức, cần import `ByteArrayOutputStream`, `Formatter`, `StandardCharsets` và `Locale`. Trong ví dụ, `ByteArrayOutputStream` chỉ là một output stream trong bộ nhớ. Nếu thay bằng file stream, nên quản lý việc đóng theo quyền sở hữu tài nguyên.

Những thành phần không đổi:

- `Charset` đều là `UTF-8`.
- `label` chứa `é` trong cả hai kết quả.
- `amount` vẫn là cùng một giá trị số Java `1234.5`.
- `count` vẫn là `7`.

Những thành phần thay đổi:

- Dấu phân tách hàng nghìn và phần thập phân: `1,234.50` so với `1.234,50`.
- Dãy byte tại các vị trí tương ứng với dấu câu của số thay đổi vì **ký tự đầu ra** thay đổi, không phải vì charset thay đổi.

**Không dùng `String.equals` giữa hai chuỗi để đánh giá các giá trị số khác nhau:** hai chuỗi hiển thị khác nhau có thể mô tả cùng một số. Nếu cần trao đổi dữ liệu máy-máy, thường nên dùng định dạng có quy ước cố định như JSON number hoặc một protocol được đặc tả rõ, không dùng số được format theo locale tùy ý.

## 6. Ví dụ: cùng locale, hai charset

Giữ nguyên `Locale.US`, thay cách mã hóa đầu ra:

~~~java
byte[] utf8 = formatBytes(StandardCharsets.UTF_8, Locale.US);
byte[] utf16le = formatBytes(StandardCharsets.UTF_16LE, Locale.US);
~~~

Giả định `formatBytes` là hàm được định nghĩa trong chương trình đầy đủ ở mục 9.

Khi giải mã đúng charset:

~~~java
var fromUtf8 = new String(utf8, StandardCharsets.UTF_8);
var fromUtf16le = new String(utf16le, StandardCharsets.UTF_16LE);

System.out.println(fromUtf8.equals(fromUtf16le)); // true
~~~

Dù cả hai chuỗi văn bản giống nhau, mảng byte không giống nhau. Trong ví dụ hoàn chỉnh:

- UTF-8: **33 byte**.
- UTF-16LE: **64 byte**.

Không suy ra `UTF-16LE` luôn có số byte gấp đôi `UTF-8`. Số byte phụ thuộc nội dung và encoding: ký tự ASCII thường dùng 1 byte trong UTF-8 nhưng 2 byte trong UTF-16LE, trong khi các ký tự khác có tỷ lệ khác. Bài kiểm thử chứa `é` và các dấu câu, nên tổng dung lượng byte mang tính cụ thể của chuỗi được format.

**Đặc điểm định dạng:** `UTF-16LE` là UTF-16 theo little-endian. Không tự giả định mọi đầu ra UTF-16 đều có BOM; quy tắc BOM phụ thuộc charset cụ thể (`UTF-16` khác `UTF-16LE`) và hợp đồng định dạng file. Khi so sánh hai byte stream, phải dùng chính xác charset đã sử dụng để giải mã.

## 7. `Locale` cấu hình lúc tạo và `format(Locale, ...)` lúc gọi

Lớp `Formatter` còn hỗ trợ overload:

~~~java
formatter.format(Locale locale, String format, Object... args)
~~~

Nhờ vậy, cùng một Formatter có thể định dạng một lần theo locale khác **mà không làm thay đổi locale đã lưu trong instance**.

~~~java
var sb = new StringBuilder();
try (var formatter = new Formatter(sb, Locale.US)) {
    formatter.format(Locale.GERMANY, "%,.2f", 1234.5);

    System.out.println(sb); // 1.234,50
    System.out.println(formatter.locale().equals(Locale.US)); // true
}
~~~

Ở đây `StringBuilder` là **ký tự trong bộ nhớ**, nên constructor `Formatter(sb, Locale.US)` không cần charset. Locale cho một lần gọi `format` thay thế locale mặc định của Formatter **trong lần format đó**, còn `formatter.locale()` vẫn trả `Locale.US` như khi khởi tạo.

Nếu Formatter đã được tạo với `OutputStream` và `Charset.UTF_8` (đúng tên Java là `StandardCharsets.UTF_8`), lời gọi `formatter.format(Locale.FRANCE, ...)` có thể thay locale định dạng cho lần đó; **charset ghi byte vẫn là charset đã chọn khi tạo Formatter**. Không có tham số Charset trong `format(Locale,...)`.

### Một điểm cần phân biệt

- `Formatter.locale()`: locale được thiết lập khi tạo đối tượng.
- `Formatter.format(Locale,...)`: locale áp dụng cho lần format cụ thể.
- `Charset`: được chọn khi tạo đầu ra byte, không được thay bằng `format(Locale,...)`.
- `String.format(Locale, ...)`: tạo một `String` đã format, **không trực tiếp ghi byte**. Nếu cần ghi ra file, bước encoding xảy ra sau đó.

Ví dụ cách tách hai tầng khi chỉ cần chuỗi:

~~~java
String line = String.format(Locale.GERMANY, "Total: %,.2f", 1234.5);
Files.writeString(path, line, StandardCharsets.UTF_8);
~~~

Đoạn này minh họa trong method có `path` và xử lý I/O phù hợp. Nó định dạng thành `String` trước, sau đó mã hóa khi gọi `Files.writeString`. Về thiết kế, đôi khi tách như vậy dễ test hơn việc để Formatter trực tiếp sở hữu output stream.

## 8. Khi nào nên dùng `Formatter`, khi nào dùng `String.format` hoặc `NumberFormat`?

### 8.1. `Formatter` cho nội dung nhiều thành phần

Khi tạo log được format thành dòng, báo cáo hoặc file text:

~~~java
try (var f = new Formatter(out, StandardCharsets.UTF_8, Locale.US)) {
    f.format("Customer=%s; amount=%,.2f%n", customerId, amount);
}
~~~

Khi dùng `Formatter(OutputStream,Charset,Locale)`, bạn chủ động chỉ định encoding của byte ghi và locale số.

### 8.2. `String.format` khi cần kết quả dạng chuỗi

~~~java
String formatted = String.format(
        Locale.GERMANY, "Total: %,.2f", 1234.5);
~~~

Đây là một `String`. Bạn có thể kiểm thử hoặc biến đổi chuỗi trước khi gửi nó ra nơi khác. Không có charset trong lệnh này; charset chỉ xuất hiện khi có hoạt động mã hóa ra byte.

### 8.3. `NumberFormat`/`DecimalFormat` khi cần chính sách số chuyên biệt

Nếu cần format số theo luật hiển thị phức tạp, tiền tệ, phân nhóm, số chữ số và các quy tắc rounding có chủ đích, `java.text.NumberFormat` và `DecimalFormat` có thể phù hợp hơn. Ví dụ:

~~~java
var numberFormatter = NumberFormat.getNumberInstance(Locale.GERMANY);
String result = numberFormatter.format(1234.5);
~~~

Đây là đoạn mã minh họa với import `NumberFormat` và `Locale`. Nó không tạo byte; encoding sẽ được chọn ở bước ghi file/response.

**Với tiền tệ và số tiền**, không tự cho rằng `%,.2f` giải quyết mọi bài toán độ chính xác và đơn vị tiền. `double` có giới hạn số dấu phẩy động nhị phân; các phép tính tiền thường cần `BigDecimal`, quy tắc làm tròn và cách hiển thị/currency code phù hợp. `Locale` quyết định cách trình bày, **không thay thế loại dữ liệu số chính xác**.

## 9. Chương trình Java 17+ hoàn chỉnh, có stdout đã kiểm thử

Chương trình này kiểm tra **cả ba constructor có `Charset` và `Locale` từ Java 10** (OutputStream, File, String fileName), sự khác biệt locale và charset, và khả năng override locale cho một lần gọi.

Nó dùng chuỗi chứa `é` để kiểm tra UTF-8 nhưng chỉ in số và boolean ASCII, tránh phụ thuộc khả năng hiển thị Unicode của terminal. Nó tạo file tạm an toàn bằng `Files.createTempFile` và xóa file trong `finally`; không sửa bất kỳ file cố định nào của người dùng.

~~~java
// File: FormatterCharsetLocaleDemo.java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Formatter;
import java.util.Locale;

public class FormatterCharsetLocaleDemo {
    static byte[] formatBytes(java.nio.charset.Charset charset, Locale locale) {
        var bytes = new ByteArrayOutputStream();
        try (var formatter = new Formatter(bytes, charset, locale)) {
            formatter.format("Caf\u00e9 | amount=%,.2f | count=%d", 1234.5, 7);
            if (formatter.ioException() != null) {
                throw new IllegalStateException(
                        "I/O formatting failed", formatter.ioException());
            }
        }
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        var usBytes = formatBytes(StandardCharsets.UTF_8, Locale.US);
        var deBytes = formatBytes(StandardCharsets.UTF_8, Locale.GERMANY);
        var usText = new String(usBytes, StandardCharsets.UTF_8);
        var deText = new String(deBytes, StandardCharsets.UTF_8);

        System.out.println("US amount = "
                + usText.split("amount=")[1].split(" \\|")[0]);
        System.out.println("DE amount = "
                + deText.split("amount=")[1].split(" \\|")[0]);
        System.out.println("US UTF-8 round-trip = "
                + usText.startsWith("Caf\u00e9 | amount="));
        System.out.println("DE UTF-8 round-trip = "
                + deText.startsWith("Caf\u00e9 | amount="));

        var utf16 = formatBytes(StandardCharsets.UTF_16LE, Locale.US);
        var restored = new String(utf16, StandardCharsets.UTF_16LE);
        System.out.println("Same locale, decoded UTF-16LE text = "
                + usText.equals(restored));
        System.out.println("US UTF-8 bytes = " + usBytes.length);
        System.out.println("US UTF-16LE bytes = " + utf16.length);

        var sb = new StringBuilder();
        try (var formatter = new Formatter(sb, Locale.US)) {
            formatter.format(Locale.GERMANY, "%,.2f", 1234.5);
            System.out.println("Per-call DE = " + sb);
            System.out.println("Stored locale US = "
                    + formatter.locale().equals(Locale.US));
        }

        Path file = Files.createTempFile("formatter-locale-", ".txt");
        try {
            try (var formatter = new Formatter(
                    file.toFile(), StandardCharsets.UTF_8, Locale.GERMANY)) {
                formatter.format("Preis %,.2f", 1234.5);
            }
            System.out.println("File constructor = "
                    + Files.readString(file, StandardCharsets.UTF_8)
                            .equals("Preis 1.234,50"));

            try (var formatter = new Formatter(
                    file.toString(), StandardCharsets.UTF_8, Locale.US)) {
                formatter.format("Price %,.2f", 1234.5);
            }
            System.out.println("Filename constructor = "
                    + Files.readString(file, StandardCharsets.UTF_8)
                            .equals("Price 1,234.50"));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Lưu vào `FormatterCharsetLocaleDemo.java`, biên dịch/chạy:

~~~bash
javac --release 17 FormatterCharsetLocaleDemo.java
java FormatterCharsetLocaleDemo
~~~

**Stdout chính xác**:

~~~text
US amount = 1,234.50
DE amount = 1.234,50
US UTF-8 round-trip = true
DE UTF-8 round-trip = true
Same locale, decoded UTF-16LE text = true
US UTF-8 bytes = 33
US UTF-16LE bytes = 64
Per-call DE = 1.234,50
Stored locale US = true
File constructor = true
Filename constructor = true
~~~

### 9.1. Phân tích kết quả

1. `US amount` là `1,234.50`; `DE amount` là `1.234,50`. Chỉ locale khác nhau vì cả hai dùng `UTF-8`.
2. Các phép `startsWith("Café ...")` chứng minh chuỗi có dấu đi qua encoding/decoding UTF-8 đúng trong trường hợp văn bản hợp lệ.
3. `UTF-16LE` tạo 64 byte so với 33 byte UTF-8 cho **cùng chuỗi đã format theo US**. Sau khi giải mã đúng, nội dung Java `String` giống nhau.
4. `Formatter.format(Locale.GERMANY,...)` cho một lần gọi định dạng kiểu Đức, trong khi `formatter.locale()` vẫn là `Locale.US`.
5. `new Formatter(file.toFile(), StandardCharsets.UTF_8, Locale.GERMANY)` ghi tệp bằng constructor có `File`.
6. `new Formatter(file.toString(), StandardCharsets.UTF_8, Locale.US)` dùng constructor có `String fileName`. File cũ được **truncate khi mở lại** rồi được ghi nội dung mới, nên kết quả kiểm tra file thứ hai vẫn đúng.
7. `try-with-resources` đóng Formatter sau từng lần ghi; đọc file bằng `Files.readString(..., UTF_8)` sau đóng bảo đảm các byte còn trong đệm đã được gửi tới tệp theo trách nhiệm close của writer.
8. `Files.deleteIfExists(file)` trong `finally` dọn file tạm ngay cả khi bước format hoặc đọc thất bại.

**Lưu ý:** Hàm `formatBytes` kiểm tra `ioException()` sau khi gọi `format()`, trước khi ra khỏi khối try-with-resources. Đây là ví dụ về kiểm tra lỗi ghi tại thời điểm format; với đích thực tế có thể phát sinh lỗi khi `flush`/`close`, cần thiết kế kiểm tra/truyền lỗi theo hợp đồng của đích I/O, không coi đoạn kiểm tra đơn lẻ là bảo đảm giao dịch.

## 10. Xử lý tệp: rủi ro ghi đè, truncate và đường dẫn

Hai overload nhận `String fileName`/`File` có thể mở tệp đích để ghi; **nếu tệp đã tồn tại thì bị truncate về kích thước 0 khi mở thành công**.

~~~java
Path path = Path.of("report.txt");
try (var formatter = new Formatter(
        path.toFile(),
        StandardCharsets.UTF_8,
        Locale.US)) {
    formatter.format("Total: %,.2f", 1234.5);
}
~~~

Đây là đoạn minh họa trong một phương thức khai báo `throws IOException` hoặc xử lý exception; import `Path`, `Formatter`, `StandardCharsets` và `Locale`. Không dùng với tệp có dữ liệu cần bảo toàn khi chưa quyết định overwrite.

### 10.1. Nếu cần append

`Formatter(File,Charset,Locale)` **không phải một constructor append**. Muốn nối thêm vào cuối file, bạn có thể chủ động mở một `OutputStream` với mode append rồi truyền stream ấy vào constructor:

~~~java
Path target = Path.of("report.txt");
try (var out = Files.newOutputStream(
            target,
            StandardOpenOption.CREATE,
            StandardOpenOption.APPEND);
     var formatter = new Formatter(
            out, StandardCharsets.UTF_8, Locale.US)) {
    formatter.format("Amount: %,.2f%n", 1234.5);
}
~~~

Đoạn này cần import `Files`, `Path`, `StandardOpenOption` và các lớp trên; nó phù hợp khi định dạng tệp text cho phép append. Cần cân nhắc **đường kết thúc dòng và encoding** để không trộn các định dạng khác nhau trong cùng một tệp.

Với nhiều writers cùng append file, không tự suy ra rằng gọi `Formatter.format` trên hai stream độc lập sẽ tạo các dòng atomic. Khi cần log/report theo thứ tự, hãy dùng cơ chế đồng bộ hoặc hệ thống logging/batching phù hợp.

### 10.2. Ghi tệp có tính toàn vẹn

Nếu tệp báo cáo quan trọng và không được phép để lại nội dung dở dang, có thể:

1. Tạo file tạm trong vị trí phù hợp.
2. Ghi hoàn chỉnh và đóng/flush.
3. Kiểm tra `ioException()` và các lỗi được hệ thống báo ở bước tạo/đóng.
4. Chuyển/đổi tên tệp tạm thành tệp đích sau khi hoàn tất, theo các lựa chọn của filesystem.

Không khẳng định mọi filesystem đều hỗ trợ đổi tên atomic hoặc việc `close` bảo đảm dữ liệu đã bền vững trên ổ đĩa. Các yêu cầu về atomicity/durability cần được thiết kế và kiểm chứng theo hệ thống lưu trữ cụ thể.

## 11. Quản lý `OutputStream` và vòng đời `Formatter`

`Formatter` implements `Closeable`/`Flushable` nên dùng được với try-with-resources:

~~~java
try (var formatter = new Formatter(
        out, StandardCharsets.UTF_8, Locale.US)) {
    formatter.format("Score = %,.2f", 1234.5);
}
~~~

Khi gọi `formatter.close()`, formatter đóng đích nhận dữ liệu `Closeable` mà nó sở hữu/được gắn, từ đó có thể đóng cả underlying `OutputStream`. Nếu `out` là stream do framework quản lý và cần tiếp tục sử dụng, việc đóng Formatter có thể đóng stream **sớm ngoài ý muốn**.

Do đó:

- Xác định **ai sở hữu** stream và ai có trách nhiệm đóng.
- Nếu method tạo/mở `OutputStream`, thường method hoặc scope đó chịu trách nhiệm đóng.
- Nếu method chỉ được truyền stream còn phải dùng ở nơi khác, cần cẩn thận khi tạo/đóng wrapper sở hữu nó.
- `Formatter.flush()` yêu cầu đẩy nội dung đệm tới đích nếu có thể; không đồng nghĩa byte chắc chắn đã được ghi bền vững xuống ổ đĩa.
- Sau khi `close()`, gọi `format` hoặc một số method trên Formatter có thể ném `FormatterClosedException`. Không tái sử dụng Formatter đã đóng.

Nếu muốn định dạng ra `StringBuilder` rồi gửi xuống một stream khác có vòng đời riêng, có thể dùng `new Formatter(builder, locale)`, sau đó encode/ghi `String` ở bước rõ ràng. Đánh đổi là cần bộ nhớ cho chuỗi/buffer trung gian.

## 12. Lỗi I/O và `Formatter.ioException()`

Đây là bẫy khá đặc trưng của `Formatter`: theo tài liệu API, **I/O exception phát sinh khi Formatter ghi dữ liệu không nhất thiết được ném trực tiếp cho caller của `format`**. Thông tin lỗi có thể được giữ và truy xuất bằng:

~~~java
IOException lastError = formatter.ioException();
~~~

Trả `null` nếu chưa ghi nhận lỗi I/O; nếu có lỗi, trả ngoại lệ được ghi nhận gần nhất theo hợp đồng. Vì vậy, với output stream/tệp quan trọng, sau khi format và flush thích hợp, cần kiểm tra kết quả thay vì giả định “không thấy exception nghĩa là ghi thành công”.

Ví dụ:

~~~java
try (var formatter = new Formatter(out, StandardCharsets.UTF_8, Locale.US)) {
    formatter.format("Order %s: %,.2f%n", orderId, total);
    formatter.flush();

    var error = formatter.ioException();
    if (error != null) {
        throw new IllegalStateException("Failed to write formatted output", error);
    }
}
~~~

Đây là đoạn code minh họa trong method có `out`, `orderId` và `total` thích hợp. Nếu có ngoại lệ khi **mở tệp** bằng constructor file mới từ Java 10, constructor có thể ném `IOException` trực tiếp. Cần tách lỗi mở tệp với lỗi xảy ra **trong quá trình ghi**.

**Không nhầm lỗi định dạng với lỗi I/O:**

- `IllegalFormatException` và các subtype (ví dụ `IllegalFormatConversionException`, `MissingFormatArgumentException`) là lỗi cú pháp/kiểu dữ liệu của format string; chúng là lỗi runtime format, không có nghĩa chỉ cần gọi `ioException()` sẽ phát hiện hết.
- `IOException` liên quan đến đích I/O. Formatter có chính sách báo lỗi riêng cho việc format ghi dữ liệu.
- `FormatterClosedException` xảy ra nếu dùng Formatter đã đóng.
- Nếu charset không biểu diễn được một ký tự, chính sách của encoder quyết định thay thế hay báo lỗi; không coi mọi trường hợp mất ký tự là một `IllegalFormatException`.

Kiểm tra thất bại và format data đã kiểm chứng là những trách nhiệm khác nhau.

## 13. `Charset`: chọn tường minh và tránh hiểu nhầm encoding mặc định

Với file text hoặc protocol đã quy định encoding:

~~~java
StandardCharsets.UTF_8
StandardCharsets.UTF_16LE
StandardCharsets.ISO_8859_1
StandardCharsets.US_ASCII
~~~

Các hằng này biểu thị `Charset` chuẩn. Không cần truyền tên chuỗi `"utf8"`/`"UTF_8"` vào constructor mới; dùng `StandardCharsets.UTF_8` giúp tránh lỗi gõ tên.

### 13.1. Nếu chỉ ghi ký tự ASCII, khác biệt charset có thể chưa lộ ra

Chuỗi `"Total=100"` được UTF-8 mã hóa thành các byte ASCII quen thuộc. Nếu chỉ test với dữ liệu ASCII, khó phát hiện lỗi chọn charset. Hãy kiểm thử thêm một giá trị có dấu như `"Café"` hoặc tiếng Việt, CJK, emoji khi định dạng yêu cầu hỗ trợ.

### 13.2. Nếu charset không biểu diễn được ký tự

Ví dụ `US_ASCII` không biểu diễn trực tiếp `é`. Nếu writer dùng encoder với chiến lược thay thế, kết quả có thể bị mất ký tự mà không phát sinh lỗi bạn mong đợi. Đối với đầu ra đòi bảo toàn ký tự:

- Ưu tiên UTF-8 khi định dạng cho phép.
- Nếu bắt buộc dùng charset hạn chế, kiểm tra trước chuỗi sẽ encode được hoặc cấu hình encoder để **REPORT** lỗi.
- Không phụ thuộc vào việc gọi `Formatter` chỉ với `Charset` là đủ bảo đảm không mất mát nội dung ở tất cả encoding.

Khi cần chính sách encode rất cụ thể, có thể tự tạo `CharsetEncoder` cấu hình `CodingErrorAction.REPORT` rồi nối vào `OutputStreamWriter` thích hợp và đưa writer đó cho `Formatter(Appendable,Locale)`. Lúc này charset/encoder do **writer** kiểm soát, không phải một tham số Charset khác của Formatter.

### 13.3. Default charset và default locale

Nếu dùng constructor bỏ charset/locale:

~~~java
new Formatter(outputStream);
~~~

kết quả phụ thuộc các giá trị mặc định được áp dụng theo JDK và môi trường. Từ Java 18, JEP 400 đặt UTF-8 làm default charset trong đa số tình huống thông thường; tuy vậy, hệ thống có thể có cấu hình khác. Default FORMAT locale có thể thay đổi theo cấu hình máy/JVM.

**Dữ liệu trao đổi, lưu trữ dài hạn hoặc output cần tái lập nên truyền tường minh cả `Charset` và `Locale`.** Như vậy, các môi trường CI, máy phát triển và server không tự chọn kiểu dấu thập phân/encoding khác nhau do default.

## 14. `Locale`: định dạng theo người đọc, không phải quy tắc lưu trữ số

Một số quyết định phải làm rõ:

| Yêu cầu | Lựa chọn |
| --- | --- |
| Báo cáo nội bộ dùng quy ước số kiểu US | `Locale.US` |
| Nội dung cho người dùng Đức | `Locale.GERMANY` khi phù hợp với sản phẩm |
| Nội dung tiếng Việt | Locale theo `vi-VN` và quy tắc hiển thị thực tế của sản phẩm |
| File text cần được parser máy đọc với dấu chấm thập phân | Chọn format mang quy ước cố định, không tùy ý dùng locale người dùng |
| Muốn số có chính xác tiền tệ | Dùng kiểu số/chính sách làm tròn thích hợp, thường `BigDecimal`; locale chỉ để trình bày |
| Muốn hiển thị thời gian theo múi giờ cụ thể | Phải quyết định zone riêng; `Locale` không tự thay timezone của một timestamp |

Một lỗi phổ biến là dùng Formatter theo `Locale.getDefault()` để tạo một CSV/config file mà chương trình khác luôn kỳ vọng dấu thập phân `.`. Khi chạy trên máy có locale dùng dấu `,`, file có thể không parse được.

Nếu cần CSV, còn phải thiết kế **quoting**, dấu phân cách trường, xuống dòng và escaping. `Formatter` có thể tạo chuỗi, nhưng **không phải thư viện CSV hoàn chỉnh**. Không dùng `%,.2f` trong một trường CSV phân tách bằng dấu phẩy mà không có chiến lược quote phù hợp.

Tương tự, nếu gửi JSON, hãy dùng serializer JSON đúng chuẩn và để nó tuân thủ format số của JSON. Không dùng một chuỗi số hiển thị theo locale làm JSON number.

## 15. Format string, kiểu dữ liệu và tính hợp lệ của đầu ra

### 15.1. Chọn đúng conversion

~~~java
formatter.format("%s | %d | %,.2f", "A", 7, 1234.5);
~~~

`%d` cần một kiểu số nguyên phù hợp; `%f` hỗ trợ các kiểu số thích hợp như `double`/`BigDecimal`. Nếu chuyển một `String` thành `%d`, Formatter không tự parse thành số và có thể ném `IllegalFormatConversionException`.

Không tạo format string tùy ý từ input không tin cậy rồi tự đưa các đối số nhạy cảm vào. Format string điều khiển **cách** diễn giải và sắp xếp đối số; hãy kiểm soát mẫu format và giới hạn dữ liệu trước khi ghi.

### 15.2. Số chữ số sau dấu thập phân

~~~java
formatter.format(Locale.US, "%.2f", 1.2345); // Biểu diễn làm tròn tới hai chữ số
~~~

`%.2f` yêu cầu định dạng có hai chữ số sau dấu thập phân. Đây là **định dạng hiển thị**, không làm thay đổi giá trị số nguyên thủy trong biến. Khi yêu cầu nghiệp vụ cần tính tiền chính xác, cần kiểm soát kiểu dữ liệu, rounding và đơn vị tiền độc lập với format.

### 15.3. Dấu xuống dòng `%n`

~~~java
formatter.format("Line one%nLine two%n");
~~~

`%n` dùng dấu phân cách dòng được định nghĩa theo nền tảng. Nếu giao thức yêu cầu cụ thể `\n` hoặc `\r\n`, hãy tạo đúng sequence đó trong format string hoặc xử lý đầu ra theo protocol. Đừng suy luận “locale Đức → xuống dòng kiểu Đức”; line separator không được quyết định trực tiếp chỉ bằng `Locale`.

### 15.4. Format cho một lần gọi có thể khác locale của Formatter

~~~java
var f = new Formatter(new StringBuilder(), Locale.US);
f.format(Locale.GERMANY, "%,.2f", 1234.5);
// Lời gọi này dùng cách format số kiểu Đức.
// f.locale() vẫn là Locale.US.
f.close();
~~~

Điều này hữu ích khi formatter có locale mặc định cho một báo cáo, nhưng một phần nội dung được chủ đích biểu diễn theo locale khác. Tuy nhiên, thay locale ở một lần gọi có thể khiến một file chứa các dòng số không đồng nhất; hãy giới hạn cách làm này khi format file yêu cầu quy ước cố định.

## 16. So sánh với `PrintWriter`, `PrintStream` và `Files.writeString`

Không phải mọi tình huống đều cần gọi constructor Formatter trực tiếp:

| Nhu cầu | Một lựa chọn phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Muốn format nhiều giá trị rồi ghi bytes với locale + charset cụ thể | `new Formatter(OutputStream, Charset, Locale)` | Ba tham số tách rõ trách nhiệm |
| Muốn kết quả là `String` có số theo locale | `String.format(Locale,...)` | Chưa encode byte |
| Muốn ghi sẵn một chuỗi UTF-8 ra file | `Files.writeString(path, text, UTF_8)` | Không cần Formatter nếu đã format xong |
| Muốn ghi các dòng text bằng writer đang được sở hữu | `BufferedWriter`/`PrintWriter` với encoding được chọn trước | Trách nhiệm close/flush thuộc owner |
| Muốn ghi dữ liệu binary không phải văn bản | `OutputStream`/`Files.copy` | Không đưa byte bất kỳ qua Formatter/Writer |

### `PrintStream` và charset

`new Formatter(PrintStream)` có thể định dạng ra một `PrintStream` đã tồn tại, nhưng mã hóa **do chính PrintStream quyết định**, không có constructor `Formatter(PrintStream, Charset, Locale)` để ghi đè charset của stream đó. Nếu cần rõ hai lựa chọn trong một constructor, dùng `Formatter(OutputStream,Charset,Locale)` hoặc thiết kế `PrintStream` có encoding được xác định từ lúc tạo.

### `Formatter(Appendable,Locale)` với `Writer`

`Writer` nhận ký tự. Nếu đó là `OutputStreamWriter`, charset được chọn tại constructor `OutputStreamWriter`:

~~~java
var writer = new OutputStreamWriter(out, StandardCharsets.UTF_8);
var formatter = new Formatter(writer, Locale.GERMANY);
~~~

Đây là mã minh họa trong method có `out`. Đừng cố thêm một charset vào constructor `Formatter(writer, charset, locale)`: overload ấy **không tồn tại**.

## 17. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`Charset` và `Locale` là cùng một loại cài đặt.” | Charset quyết định encoding, Locale quyết định một số quy tắc định dạng. |
| “`Formatter` chỉ có từ Java 10.” | Lớp có từ trước; ba constructor `Charset + Locale` được bổ sung trong Java 10. |
| “`new Formatter(file, UTF_8, Locale.GERMANY)` làm số dùng dấu thập phân kiểu US vì UTF-8.” | Sai; cách format số phụ thuộc Locale.GERMANY. |
| “Thay `UTF-8` bằng `UTF-16LE` sẽ đổi dấu chấm thành dấu phẩy.” | Sai; thay charset đổi byte, không tự chọn dấu câu. |
| “`Locale.GERMANY` sẽ dịch chữ ‘Total’ trong format string.” | Sai; locale không dịch literal text. |
| “`Formatter(Writer, Charset, Locale)` là overload Java 10.” | Sai; ba overload mới nhận String filename, File hoặc OutputStream. |
| “`format(Locale,...)` đổi luôn charset của Formatter.” | Sai; nó chỉ override locale cho lần gọi. |
| “`format(Locale,...)` sửa `formatter.locale()`.” | Sai; thuộc tính locale lúc tạo không đổi. |
| “`Formatter(File,Charset,Locale)` sẽ append khi file tồn tại.” | Sai; file bị truncate khi mở thành công. |
| “Không thấy IOException từ `format` nghĩa là output chắc chắn thành công.” | Cần kiểm tra `ioException()` và cơ chế ghi/flush/close. |
| “Đóng Formatter không ảnh hưởng underlying OutputStream.” | Có thể đóng đích/underlying stream; phải kiểm soát ownership. |
| “`String.format` đã xác định charset byte.” | Nó tạo chuỗi, charset chỉ xuất hiện lúc encode/ghi byte. |
| “`%,.2f` là format luôn phù hợp để lưu dữ liệu JSON/CSV.” | Đây là format hiển thị theo locale, không phải một serializer định dạng dữ liệu chuẩn. |
| “Chỉ đổi Locale là đủ để chọn timezone.” | Locale không thay thế chọn múi giờ/offset. |
| “Default Charset luôn như nhau ở mọi JDK và deployment.” | Nên chỉ rõ charset cho giao thức và file; default có bối cảnh riêng. |
| “Dùng UTF-8 bảo đảm mọi ký tự trong charset nguồn đều được giải mã đúng.” | Reader phải dùng **đúng charset của byte đầu vào**; chọn UTF-8 tùy tiện có thể đọc sai. |
| “Formatter đảm bảo thread-safe.” | Javadoc nói thread-safety không được bảo đảm; dùng mỗi formatter trong scope được kiểm soát. |

## 18. Tình huống ứng dụng

### 18.1. Xuất báo cáo số cho người đọc ở các thị trường

Bạn có cùng dữ liệu doanh số, nhưng xuất các file báo cáo văn bản riêng cho nhóm US và nhóm Đức:

~~~java
try (var us = new Formatter(usOutput, StandardCharsets.UTF_8, Locale.US)) {
    us.format("Revenue: %,.2f%n", revenue);
}

try (var de = new Formatter(deOutput, StandardCharsets.UTF_8, Locale.GERMANY)) {
    de.format("Revenue: %,.2f%n", revenue);
}
~~~

`revenue`, `usOutput` và `deOutput` được cung cấp bởi method/lớp chứa đoạn này. Dữ liệu số giống nhau; phần ký tự hiển thị khác nhau, nhưng cả hai file dùng UTF-8. Nếu báo cáo có nhãn bằng ngôn ngữ địa phương, cần dùng bản dịch riêng cho label.

### 18.2. Tạo file văn bản legacy có charset được đặc tả

Một hệ thống có thể yêu cầu tệp text trong một charset cụ thể. Nếu charset đó được hỗ trợ và thực sự phù hợp với tập ký tự cần ghi, chỉ định nó tường minh:

~~~java
try (var f = new Formatter(
        output, StandardCharsets.ISO_8859_1, Locale.US)) {
    f.format("Amount: %,.2f", 1234.5);
}
~~~

Đây là ví dụ kỹ thuật về constructor, **không phải lời khuyên chọn Latin-1 cho một dự án mới**. Đối với đầu ra hiện đại không có ràng buộc khác, UTF-8 thường là lựa chọn tương tác thuận tiện. Khi nhận một charset bị hạn chế, xác minh khả năng biểu diễn các ký tự dự kiến và error policy của encoder.

### 18.3. Tạo tệp tiêu thụ bởi máy

Nếu một batch job cần file có số dùng dấu `.` thập phân và không có grouping, hãy chọn format và locale được đặc tả, ví dụ:

~~~java
try (var f = new Formatter(output, StandardCharsets.UTF_8, Locale.US)) {
    f.format("%.2f%n", 1234.5);
}
~~~

Nhưng khi format là CSV/JSON/XML chính thức, dùng serializer theo specification có thể đáng tin cậy hơn. Một file dùng làm API không nên bị thay đổi quy ước số chỉ vì default locale của server.

### 18.4. Khi caller muốn giữ stream mở

Nếu caller phải tiếp tục sử dụng `OutputStream`, không tùy tiện đóng một `Formatter` được tạo trên stream đó. Có thể thiết kế hàm format ra `StringBuilder` với `Locale`, sau đó caller ghi chuỗi bằng charset và quản lý close theo contract riêng. Đây là lựa chọn cấu trúc, không phải cách thay đổi một overload đang thiếu.

## 19. Bài tập tự kiểm tra kèm đáp án

### Bài 1 — Phân biệt hai tham số

~~~java
new Formatter(output, StandardCharsets.UTF_8, Locale.GERMANY);
~~~

**Hỏi:** Tham số nào quyết định `1.234,50`, tham số nào quyết định byte của ký tự `é`?

**Đáp án:** `Locale.GERMANY` quyết định dấu phân nhóm và dấu thập phân khi format số phù hợp; `StandardCharsets.UTF_8` quyết định cách mã hóa `é` thành byte.

### Bài 2 — Overload thực sự có từ Java 10

**Hỏi:** Ba kiểu đích có overload nhận `Charset` và `Locale` cùng lúc là gì?

**Đáp án:** `String fileName`, `File file` và `OutputStream os`. Không có overload tương ứng nhận `Writer` cùng `Charset` và `Locale`.

### Bài 3 — Locale khác, charset giống

Hai Formatter dùng UTF-8, một dùng `Locale.US` và một dùng `Locale.GERMANY`. Cả hai gọi `format("%,.2f", 1234.5)`.

**Đáp án:** Giá trị hiển thị lần lượt là `1,234.50` và `1.234,50`. Charset giống nhau không buộc văn bản giống nhau.

### Bài 4 — Locale giống, charset khác

Hai Formatter đều `Locale.US`, format cùng chuỗi có `Café`. Một ghi UTF-8, một ghi UTF-16LE.

**Đáp án:** Byte stream khác nhau; giải mã đúng charset sẽ cho chuỗi nội dung như nhau. Với chương trình mẫu, số byte lần lượt là 33 và 64.

### Bài 5 — Locale override theo lần gọi

~~~java
var builder = new StringBuilder();
var f = new Formatter(builder, Locale.US);
f.format(Locale.GERMANY, "%,.2f", 1234.5);
~~~

**Hỏi:** `f.locale()` trả gì?

**Đáp án:** Vẫn là `Locale.US`. Chỉ lần format cụ thể dùng `Locale.GERMANY`. Code này cần đóng formatter theo scope phù hợp.

### Bài 6 — File tồn tại

Một tệp đã chứa dòng `OLD`. Code gọi `new Formatter(file, UTF_8, Locale.US)` và format dòng `NEW` rồi đóng.

**Đáp án:** Constructor mở tệp để ghi và **truncate** nội dung cũ theo hợp đồng; không tự append sau `OLD`. `UTF_8` ở đây cần là `StandardCharsets.UTF_8` (hoặc biến Charset tương ứng).

### Bài 7 — Trách nhiệm đóng

Một framework truyền vào `OutputStream` response còn cần dùng tiếp. Code tạo Formatter trên stream này và đóng Formatter.

**Đáp án:** Cần xem lại ownership; đóng Formatter có thể đóng cả underlying stream. Không áp dụng try-with-resources một cách máy móc nếu caller/framework phải tiếp tục sử dụng stream.

### Bài 8 — Lỗi I/O không ném ngay

`formatter.format(...)` không ném exception, nhưng dữ liệu không xuất hiện ở đích.

**Đáp án:** Kiểm tra `formatter.ioException()`, flush/close, đích ghi và quy tắc sở hữu stream. Không chỉ dựa vào việc `format` đã return.

### Bài 9 — Mã hóa không thể biểu diễn

Bạn cần xuất chữ `é` nhưng charset đầu ra là US-ASCII.

**Đáp án:** US-ASCII không biểu diễn `é` trực tiếp; cần đổi sang UTF-8 khi cho phép hoặc chọn encoder với chính sách báo lỗi/thay thế có chủ đích. Locale không làm charset này biểu diễn được ký tự mới.

### Bài 10 — `String.format` có ghi byte không?

~~~java
var text = String.format(Locale.GERMANY, "%,.2f", 1234.5);
~~~

**Đáp án:** Chưa. Kết quả là `String`; để ghi ra byte, gọi `getBytes(charset)` hoặc API I/O nhận `Charset` rõ ràng.

### Bài 11 — `%n` có phải thuộc charset?

**Đáp án:** `%n` đại diện dấu xuống dòng của nền tảng ở mức ký tự. Sau đó charset mã hóa các ký tự ấy thành byte. Locale không tự chọn `\r\n` hay `\n` cho giao thức.

### Bài 12 — Format cho máy hay người đọc?

Một endpoint xuất dữ liệu số mà parser luôn kỳ vọng dấu thập phân `.`. Có nên dùng `Locale.getDefault()` không?

**Đáp án:** Không nếu giao thức yêu cầu dấu chấm. Chọn format số được đặc tả, ví dụ locale và pattern cố định, hoặc dùng serializer chính thức cho format đó. Locale người dùng phù hợp với **hiển thị**, không tự động phù hợp với **protocol**.

## 20. Checklist khi review một lời gọi `Formatter(...,Charset,Locale)`

- [ ] Đích thực sự là `File`/`String fileName`/`OutputStream` hay chỉ `Appendable`?
- [ ] Nếu muốn overload Java 10+, có đúng kiểu `Charset`, không nhầm với `String` csn hay `Writer` không?
- [ ] Charset đã được xác định theo format/protocol chưa? Có chỉ rõ `StandardCharsets.UTF_8` khi phù hợp không?
- [ ] Locale đã được xác định theo người đọc hoặc quy tắc file chưa? Có vô tình dùng default locale không?
- [ ] Có tách **định dạng số** khỏi **mã hóa byte** trong lập luận/test chưa?
- [ ] Có kiểm thử ký tự không phải ASCII, ví dụ tiếng Việt, `é` hay emoji không?
- [ ] Có kiểm thử `Locale.US` và `Locale.GERMANY` khi format có dấu phân nhóm/decimal không?
- [ ] Có thể có output không biểu diễn được bằng charset đích không? Chính sách lỗi/thay thế là gì?
- [ ] Format string có được kiểm soát và conversion phù hợp kiểu tham số không?
- [ ] Nếu là file, có biết constructor sẽ truncate file cũ không? Nếu cần append đã mở stream bằng chế độ append riêng chưa?
- [ ] Ai sở hữu stream và ai đóng? Đóng Formatter có làm đóng một stream còn cần dùng không?
- [ ] Có kiểm tra `ioException()` và các lỗi mở/flush/close theo mức độ quan trọng của dữ liệu không?
- [ ] Nếu file yêu cầu toàn vẹn, đã có chính sách xử lý file ghi dở chưa?
- [ ] Nếu dùng `format(Locale,...)`, có hiểu nó không đổi charset hoặc `Formatter.locale()` không?
- [ ] Nếu dùng `%n`, có đúng quy tắc line ending của giao thức không?
- [ ] Nếu đầu ra là CSV/JSON, có dùng serializer phù hợp thay vì chỉ ghép format string không?
- [ ] Nếu định dạng tiền tệ, có kiểm soát độ chính xác và rounding của dữ liệu đầu vào không?
- [ ] Có tránh dùng chung một Formatter cho nhiều luồng mà không có cơ chế quản lý đúng không?

## 21. Tài liệu chính thức vẫn đang áp dụng

- [Java SE API — `java.util.Formatter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): constructor nhận `String`/`File`/`OutputStream` cùng `Charset`/`Locale` có dấu `Since: 10`, quy tắc format, `format(Locale,...)`, `locale()`, `ioException()`, `flush`/`close`.
- [Java SE 10 API — `Formatter`](https://docs.oracle.com/javase/10/docs/api/java/util/Formatter.html): đối chiếu ba overload `Charset`/`Locale` đã tồn tại từ Java 10.
- [Java SE API — `java.nio.charset.Charset`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html): ánh xạ ký tự Unicode và byte cùng charset encoder/decoder.
- [Java SE API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): các hằng charset thường dùng.
- [Java SE API — `java.util.Locale`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): ngôn ngữ/vùng và lựa chọn format locale.
- [Java SE API — `String.format`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): tạo chuỗi đã định dạng; bản thân không ghi byte.
- [Java SE API — `NumberFormat`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/NumberFormat.html): các định dạng số theo locale và tùy chỉnh.
- [Java SE API — `Files.writeString` và `Files.readString`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): đọc/ghi chuỗi với charset xác định.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): bối cảnh default charset Java 18+, không thay thế việc khai báo charset của định dạng file/protocol.

**Kết luận:** Khi tạo `Formatter` để ghi **byte**, `Charset` quyết định **cách mã hóa văn bản** còn `Locale` quyết định **cách trình bày một số dữ liệu**. Ba overload được thêm từ Java 10 cho `String fileName`, `File` và `OutputStream` vẫn được hỗ trợ. Dùng charset và locale tường minh khi cần kết quả dự đoán được; kiểm soát việc truncate file, vòng đời stream, lỗi I/O và quy ước dữ liệu của consumer.