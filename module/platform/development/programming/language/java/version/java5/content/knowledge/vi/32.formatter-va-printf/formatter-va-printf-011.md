# Các nhóm IllegalFormatException

## 1. Lỗi định dạng xảy ra ở đâu?

Một lời gọi có thể biên dịch nhưng thất bại khi Formatter diễn giải khuôn:

```java
String text = String.format("%d", "12");
```

`"12"` là String, còn `%d` yêu cầu kiểu số nguyên được hỗ trợ. Formatter không tự parse chuỗi ấy thành int; lời gọi ném `IllegalFormatConversionException`.

Nhóm `IllegalFormatException` dùng cho khuôn có cú pháp không hợp lệ hoặc chỉ định không tương thích với đối số. Nó nằm trong nhánh:

```text
RuntimeException
    -> IllegalArgumentException
        -> IllegalFormatException
            -> các loại lỗi định dạng cụ thể
```

Đây là ngoại lệ không cần khai báo bắt buộc bằng throws. Điều đó không có nghĩa có thể bỏ qua nó: với khuôn cố định do chương trình quản lý, lỗi thường là một khiếm khuyết cần sửa.

Các API trong bài vẫn phù hợp trên Java hiện đại. Ví dụ chạy với Java 17+, chỉ dùng các lớp ngoại lệ công khai và cơ chế định dạng ổn định.

Nguồn phân cấp: [IllegalFormatException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IllegalFormatException.html).

## 2. Bản đồ các nhóm lỗi

| Nhóm nguyên nhân | Ngoại lệ công khai tiêu biểu | Cần kiểm tra |
| --- | --- | --- |
| Không nhận diện conversion | UnknownFormatConversionException | Ký tự sau %, conversion ngày giờ hoặc khuôn bị dang dở |
| Conversion không nhận kiểu đối số | IllegalFormatConversionException | %d, %f, %c… có khớp kiểu thật không |
| Không có đối số được yêu cầu | MissingFormatArgumentException | Số đối số, chỉ số tường minh, cờ dùng lại < |
| Cờ lặp | DuplicateFormatFlagsException | Có lặp - hoặc cờ khác không |
| Tổ hợp cờ không hợp lệ | IllegalFormatFlagsException | Các cờ có được kết hợp không |
| Cờ không hợp conversion | FormatFlagsConversionMismatchException | Cờ có ý nghĩa với conversion hiện tại không |
| Cờ không được nhận diện | UnknownFormatFlagsException | Chuỗi cờ có ký hiệu được hỗ trợ không |
| Thiếu width cần thiết | MissingFormatWidthException | Cờ hiện tại có yêu cầu width không |
| Width không hợp lệ | IllegalFormatWidthException | Conversion có cho width không; giá trị có được hỗ trợ không |
| Precision không hợp lệ | IllegalFormatPrecisionException | Conversion có cho precision không |
| Mã Unicode không hợp lệ | IllegalFormatCodePointException | Giá trị dùng cho %c có là code point hợp lệ không |

Bảng này là cách phân loại để chẩn đoán, không phải thứ tự ưu tiên kiểm tra của Formatter. Một khuôn có nhiều lỗi có thể chỉ báo một lỗi trước; sửa xong cần chạy lại.

Không coi danh sách tên lớp công khai là mọi chi tiết triển khai của từng JDK. Đặc biệt, lỗi về chỉ số đối số không hợp lệ có thể được báo dưới một lớp con cụ thể không dành để mã ứng dụng phụ thuộc trực tiếp. Bắt lớp cơ sở ở biên phù hợp rồi sửa khuôn theo hợp đồng sẽ bền vững hơn bắt tên lớp nội bộ.

## 3. Conversion không nhận diện khác với sai kiểu

### UnknownFormatConversionException

Ví dụ `%q` dùng một conversion không có trong Formatter:

```java
String.format("%q", 12);
```

Một dấu phần trăm lẻ ở cuối khuôn cũng không tạo thành chỉ định hợp lệ. Nếu muốn in ký tự phần trăm theo nghĩa đen trong khuôn, dùng `%%`.

Không phải mọi chữ hoa đều là conversion hợp lệ. Ví dụ `%N` không phải biến thể xuống dòng của `%n`.

Ngoại lệ có `getConversion()` để đọc phần conversion không được nhận diện.

### IllegalFormatConversionException

Ví dụ:

```java
String.format("%d", "12");
String.format("%f", 12);
```

Dòng đầu đưa String cho số nguyên; dòng sau đưa Integer cho nhóm số thực. Java có những chuyển đổi kiểu trong ngữ cảnh khác không có nghĩa Formatter sẽ tự thực hiện chúng.

Dữ liệu `12.0` có phần lẻ bằng 0 vẫn là Double khi được truyền như double. Nó không tự hợp lệ cho `%d`.

Ngoại lệ có:

- `getConversion()`: ký tự conversion.
- `getArgumentClass()`: lớp của đối số không tương thích.

Khi sửa lỗi, xác định lại ý định: cần đúng conversion cho kiểu hiện có, hay cần chuyển/parse dữ liệu trước đó bằng một bước có kiểm tra? Không đổi hết về `%s` chỉ để tránh ngoại lệ nếu định dạng số vẫn là yêu cầu.

## 4. Đối số thiếu và chỉ số chọn đối số

### MissingFormatArgumentException

Những tình huống điển hình:

```java
String.format("%s %s", "only one");
String.format("%2$s", "only one");
String.format("%<s", "no previous selection");
```

- Khuôn thứ nhất yêu cầu hai đối số nhưng chỉ có một.
- Khuôn thứ hai chọn đối số thứ hai, không phải “chuỗi có width 2”.
- Khuôn thứ ba muốn dùng lại đối số của một chỉ định trước đó nhưng chưa có chỉ định chọn đối số nào trước nó.

Ngoại lệ có `getFormatSpecifier()` để nhận chỉ định bị thiếu đối số.

Đối số được đánh số từ 1. Khuôn có chỉ số 0 không hợp lệ; đừng “sửa” bằng cách truyền thêm phần tử thứ 0 như khi dùng một mảng Java.

### Đối số dư không phải lỗi đối số thiếu

```java
String text = String.format("%s", "A", "B");
```

Kết quả là A; đối số B không được dùng. Vì vậy việc lời gọi không ném ngoại lệ chưa chứng minh mọi đối số được sử dụng đúng ý định.

`%%` và `%n` không lấy đối số. Đừng truyền các giá trị phụ cho chúng rồi vô tình làm lệch ý nghĩa danh sách đối số của những chỉ định còn lại.

## 5. Ba lỗi cờ thường bị nhầm

### DuplicateFormatFlagsException — lặp một cờ

```java
String.format("%--5s", "A");
```

Cờ `-` xuất hiện hai lần. Đây không phải cách “căn trái mạnh hơn”. Loại bỏ phần lặp theo ý định.

### IllegalFormatFlagsException — cờ hoặc tổ hợp không hợp lệ

```java
String.format("%+ d", 12);
```

Cờ `+` và dấu cách không được kết hợp theo cách này. Một cờ yêu cầu hiện dấu dương, cờ kia dành dấu cách cho giá trị không âm; hợp đồng không cho tùy ý ghép chúng.

Với conversion đặc biệt, việc đưa cờ không được phép cũng có thể thuộc nhóm này, chẳng hạn thêm cờ vào `%n`.

### FormatFlagsConversionMismatchException — cờ biết được nhưng sai conversion

```java
String.format("%+s", "A");
```

Cờ `+` được Formatter biết đến, nhưng không hợp với conversion chuỗi s trong trường hợp này. Nó khác lỗi “không biết cờ đó là gì”.

Ngoại lệ cung cấp cả `getFlags()` và `getConversion()`. Xem [FormatFlagsConversionMismatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/FormatFlagsConversionMismatchException.html).

### UnknownFormatFlagsException — cờ không nhận diện

[UnknownFormatFlagsException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UnknownFormatFlagsException.html) là lớp công khai cho trường hợp cờ không được nhận diện; có `getFlags()`.

Tuy nhiên, đừng tự chọn một ký hiệu lạ như `!`, đặt vào khuôn rồi khẳng định mọi JDK chắc chắn báo lớp này. Bộ phân tích khuôn có thể diễn giải ký hiệu ấy như phần conversion sai hoặc một chỉ định không hợp lệ ở vị trí khác.

Phân loại dựa vào ngoại lệ thực tế và hợp đồng API. Không cần tự dựng một ví dụ printf giả chỉ để mỗi tên lớp đều có một dòng output.

## 6. Width thiếu khác với width không được phép

### MissingFormatWidthException

```java
String.format("%-s", "A");
```

Cờ căn trái `-` cần một width để biết vùng căn. Khuôn thiếu width nên lỗi. Nếu muốn căn trái trong 5 ký tự, sửa thành `%-5s`.

Tương tự, một số cờ đệm số yêu cầu width phù hợp. Cần xem cả chỉ định, không chỉ thêm một số ngẫu nhiên để hết lỗi.

Ngoại lệ có `getFormatSpecifier()`.

### IllegalFormatWidthException

```java
String.format("%3n");
```

Conversion n tạo dấu xuống dòng và không cho width. Thêm số 3 không tạo ba dòng; nó làm khuôn không hợp lệ. Muốn ba lần xuống dòng, viết `%n%n%n`.

Ngoại lệ có `getWidth()`.

Không phải mọi số viết cạnh dấu % đều là width. `%2$s` dùng chỉ số đối số 2, còn `%2s` dùng width tối thiểu 2. Đọc đúng cấu trúc trước khi chẩn đoán.

## 7. Precision không có cùng ý nghĩa với mọi kiểu

### IllegalFormatPrecisionException

```java
String.format("%.2d", 12);
```

Conversion d không cho precision. Khuôn này không có nghĩa “số nguyên ít nhất hai chữ số”. Nếu muốn đệm 0 tới width 2, dùng `%02d`.

Một số ví dụ hợp lệ để đối chiếu:

- `%.2f`: hai chữ số sau dấu phân cách của số thực.
- `%.2s`: giới hạn phần văn bản chuỗi thông thường được biểu diễn.
- `%.2g`: precision theo chữ số có nghĩa.
- `%.2d`: không hợp lệ.

Conversion `%n`, `%%` và một số nhóm khác không cho precision. Ngoại lệ có `getPrecision()`.

Nếu số width/precision quá lớn vượt miền được hỗ trợ, cũng không được xem nó là một chỉ định hợp lệ chỉ vì đã viết toàn chữ số. Hãy giới hạn tham số động theo nhu cầu thực tế.

## 8. Mã ký tự không hợp lệ

### IllegalFormatCodePointException

```java
String.format("%c", 0x110000);
```

Giá trị 0x110000 nằm ngoài miền code point Unicode được hỗ trợ cho conversion này, nên Formatter ném lỗi.

Đây là lỗi **giá trị** của đối số số nguyên được dùng như mã ký tự. Nó khác với việc đưa hẳn một kiểu không tương thích cho c.

Ngoại lệ có `getCodePoint()` để đọc mã đã gây lỗi. Sửa bằng cách kiểm tra giá trị theo nguồn dữ liệu và miền ký tự mong muốn, không phải ép mọi int về char để che vấn đề.

## 9. Chương trình phân loại các lỗi thường gặp

Lưu thành `FormatExceptionCatalogDemo.java`:

```java
import java.util.IllegalFormatException;
import java.util.Locale;

public class FormatExceptionCatalogDemo {
    private static void show(
            String label, String pattern, Object... values) {
        try {
            String result = String.format(Locale.ROOT, pattern, values);
            System.out.println(label + ": " + result);
        } catch (IllegalFormatException e) {
            System.out.println(label + ": "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("unknown conversion", "%q", 12);
        show("wrong argument type", "%d", "12");
        show("missing argument", "%2$s", "A");
        show("missing previous argument", "%<s", "A");
        show("duplicate flag", "%--5s", "A");
        show("invalid flag pair", "%+ d", 12);
        show("flag conversion mismatch", "%+s", "A");
        show("missing width", "%-s", "A");
        show("invalid width", "%3n");
        show("invalid precision", "%.2d", 12);
        show("invalid code point", "%c", 0x110000);
    }
}
```

Chạy:

```shell
javac FormatExceptionCatalogDemo.java
java FormatExceptionCatalogDemo
```

Stdout:

```text
unknown conversion: UnknownFormatConversionException
wrong argument type: IllegalFormatConversionException
missing argument: MissingFormatArgumentException
missing previous argument: MissingFormatArgumentException
duplicate flag: DuplicateFormatFlagsException
invalid flag pair: IllegalFormatFlagsException
flag conversion mismatch: FormatFlagsConversionMismatchException
missing width: MissingFormatWidthException
invalid width: IllegalFormatWidthException
invalid precision: IllegalFormatPrecisionException
invalid code point: IllegalFormatCodePointException
```

Mỗi mẫu tập trung vào một nguyên nhân để kết quả dễ đối chiếu. Với khuôn chứa nhiều lỗi, không dùng bảng này để dự đoán cứng lỗi nào phải xuất hiện đầu tiên.

## 10. Lấy thông tin có cấu trúc thay vì parse thông báo

Thông báo `getMessage()` hữu ích cho người đọc, nhưng không nên phân loại bằng cách cắt chuỗi tiếng Anh trong thông báo. Các lớp con cung cấp accessor phù hợp:

| Ngoại lệ | Thông tin công khai hữu ích |
| --- | --- |
| IllegalFormatConversionException | getConversion, getArgumentClass |
| FormatFlagsConversionMismatchException | getFlags, getConversion |
| DuplicateFormatFlagsException | getFlags |
| IllegalFormatFlagsException | getFlags |
| UnknownFormatFlagsException | getFlags |
| MissingFormatArgumentException | getFormatSpecifier |
| MissingFormatWidthException | getFormatSpecifier |
| IllegalFormatWidthException | getWidth |
| IllegalFormatPrecisionException | getPrecision |
| IllegalFormatCodePointException | getCodePoint |
| UnknownFormatConversionException | getConversion |

Lưu thành `FormatDiagnosticDemo.java`:

```java
import java.util.FormatFlagsConversionMismatchException;
import java.util.IllegalFormatConversionException;
import java.util.Locale;
import java.util.MissingFormatArgumentException;

public class FormatDiagnosticDemo {
    public static void main(String[] args) {
        try {
            String.format(Locale.ROOT, "%d", "twelve");
        } catch (IllegalFormatConversionException e) {
            System.out.println("conversion=" + e.getConversion()
                    + ", argument=" + e.getArgumentClass().getSimpleName());
        }

        try {
            String.format(Locale.ROOT, "%2$s", "A");
        } catch (MissingFormatArgumentException e) {
            System.out.println("missing=" + e.getFormatSpecifier());
        }

        try {
            String.format(Locale.ROOT, "%+s", "A");
        } catch (FormatFlagsConversionMismatchException e) {
            System.out.println("flags=" + e.getFlags()
                    + ", conversion=" + e.getConversion());
        }
    }
}
```

Chạy:

```shell
javac FormatDiagnosticDemo.java
java FormatDiagnosticDemo
```

Stdout:

```text
conversion=d, argument=String
missing=%2$s
flags=+, conversion=s
```

Trong log thực tế, có thể ghi định danh khuôn, chỉ định và kiểu đối số. Không cần mặc định ghi toàn bộ giá trị nghiệp vụ để biết rằng một String đã được truyền cho %d.

## 11. Những lỗi không thuộc nhóm này

| Hiện tượng | Nhóm cần phân biệt |
| --- | --- |
| Chuỗi format là null | Có thể là NullPointerException theo hợp đồng phương thức |
| Dùng Formatter đã đóng | FormatterClosedException, thuộc nhánh trạng thái |
| Đích I/O ghi thất bại | Theo hợp đồng của Formatter/stream; không phải lỗi khuôn |
| Đối tượng tự ném lỗi trong toString hoặc Formattable | Có thể là ngoại lệ của chính mã đối tượng |
| Dùng escape Java không hợp lệ trong mã nguồn | Lỗi biên dịch, chưa tới Formatter |
| Parse một chuỗi số thất bại trước định dạng | Có thể là NumberFormatException của bước parse |

Đừng bắt IllegalFormatException rồi giả định nó bao phủ mọi lỗi của một lời gọi định dạng.

Ngược lại, đối số null không tự là lỗi với mọi conversion. Ví dụ `String.format("%s", (Object) null)` cho chuỗi `null`. Phải phân biệt **khuôn null** với **một đối số null** và xem hợp đồng conversion cụ thể.

Formatter có cơ chế lưu IOException của đích trong những trường hợp được hợp đồng quy định và cho đọc qua `ioException()`; PrintStream cũng có hợp đồng báo lỗi I/O riêng. Không suy ra rằng không có IllegalFormatException thì dữ liệu chắc chắn đã được ghi thành công ra thiết bị.

## 12. Cách xử lý đúng trong mã ứng dụng

### Khuôn do chương trình quản lý

Kiểm tra các khuôn cố định với kiểu dữ liệu đại diện. Sửa conversion, vị trí đối số hoặc cờ tại nguồn. Không bắt rồi âm thầm trả chuỗi rỗng vì điều đó dễ biến một lỗi lập trình thành dữ liệu thiếu khó chẩn đoán.

Với khuôn được bản dịch đảo thứ tự, dùng chỉ số tường minh nhất quán và kiểm tra từng bản dịch. Một khuôn hợp lệ với một bộ đối số không tự hợp lệ với tất cả kiểu dữ liệu khác.

### Khuôn được cung cấp động

Nếu ứng dụng cho phép cấu hình khuôn, xác định tập conversion/cờ được hỗ trợ và giới hạn width/precision theo yêu cầu. Khi lỗi, trả kết quả xác thực rõ ràng thay vì để một lỗi cấu hình lặp vô hạn trong đường xử lý.

Một lần format thành công với giá trị mẫu không chứng minh mọi dữ liệu tương lai hợp lệ, nhất là khi nguồn có thể đổi kiểu hoặc mã ký tự.

### Dữ liệu không phải khuôn

Nếu chỉ muốn in một chuỗi dữ liệu có dấu %, dùng print hoặc đưa nó vào đối số:

```java
System.out.printf("%s%n", message);
```

`message` là dữ liệu được khai báo ở nơi sử dụng; không dùng nội dung đó làm khuôn chỉ vì API có tên printf.

### Không kỳ vọng tự hoàn tác output

Khi định dạng trực tiếp vào một đích, có thể đã có một phần output trước khi lỗi phụ thuộc đối số được phát hiện. Ngoại lệ không bảo đảm đích được khôi phục trạng thái ban đầu.

Nếu yêu cầu là chuẩn bị một thông điệp hoàn chỉnh trước khi ghi ra ngoài, có thể tạo String bằng String.format trước, rồi mới phát hành nó qua cơ chế ghi phù hợp. Bước này không làm mọi thao tác I/O trở thành giao dịch, nhưng tách lỗi chuẩn bị nội dung khỏi bước ghi.

## 13. Quy trình chẩn đoán ngắn

1. Giữ lại loại ngoại lệ và chỉ định gây lỗi.
2. Đọc khuôn theo cấu trúc: chỉ số đối số, cờ, width, precision, conversion.
3. Đối chiếu kiểu đối số thực tế, không chỉ giá trị nhìn thấy.
4. Kiểm tra số lượng/chỉ số đối số và cờ dùng lại <.
5. Sửa một nguyên nhân rồi chạy lại toàn bộ khuôn.
6. Kiểm tra cả output mong muốn, không chỉ việc hết ném lỗi.

[Hợp đồng Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html) là nơi đối chiếu tổ hợp hợp lệ. Các tên ngoại lệ giúp khoanh vùng nguyên nhân; chúng không thay cho việc hiểu ý định của khuôn.

## 14. Tự kiểm tra

**%+s là cờ lạ hay cờ không hợp conversion?**  
Cờ + được biết đến nhưng không hợp s trong tình huống ấy: FormatFlagsConversionMismatchException.

**%-s và %3n có cùng vấn đề không?**  
Không. Một bên thiếu width cần thiết; bên kia thêm width vào conversion không cho width.

**%.2d có nghĩa số nguyên hai chữ số không?**  
Không. Precision không áp dụng cho d; dùng width/cờ phù hợp hoặc kiểm tra miền số riêng.

**Bắt IllegalFormatException có bắt lỗi đích ghi hoặc Formatter đã đóng không?**  
Không bao phủ mọi lỗi ấy; chúng thuộc hợp đồng và phân cấp khác.

**Không ném lỗi có chứng minh dùng đúng mọi đối số không?**  
Không. Đối số dư có thể bị bỏ qua, hoặc khuôn hợp lệ nhưng trình bày sai ý định.

Cách sửa bền vững là làm khớp khuôn với kiểu dữ liệu và yêu cầu trình bày, rồi kiểm chứng output. Chỉ làm cho ngoại lệ biến mất chưa đủ chứng minh định dạng đã đúng.
