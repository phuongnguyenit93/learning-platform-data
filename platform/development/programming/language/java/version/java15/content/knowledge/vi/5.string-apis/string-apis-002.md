# Placeholder, chỉ số tham số và kiểu đối số trong API chuỗi Java 15+

## 1. Bài toán: chèn giá trị vào khuôn mẫu chuỗi

Khi cần tạo lời nhắn, dòng báo cáo hoặc thông tin hiển thị có nhiều giá trị thay đổi, Java cho phép đặt **placeholder** (ký hiệu giữ chỗ) trong một chuỗi định dạng (*format string*) rồi truyền các đối số tương ứng. Từ **Java 15**, phương thức instance `String.formatted(Object... args)` đã trở thành API chính thức; nó vẫn được hỗ trợ trong Java hiện đại.

~~~java
String name = "Lan";
int quantity = 7;

String message = "Hello %s, quantity=%d".formatted(name, quantity);
// message là "Hello Lan, quantity=7"
~~~

Ở đây `%s` và `%d` là **format specifier**. `name` và `quantity` là **đối số định dạng**. Trình định dạng thay từng specifier bằng cách biểu diễn của đối số theo quy tắc tương ứng.

Hai cách gọi cơ bản:

~~~java
String a = "User=%s, count=%d".formatted("Lan", 7); // Java 15+
String b = String.format("User=%s, count=%d", "Lan", 7);
~~~

`a` và `b` đều là `"User=Lan, count=7"`. Theo tài liệu API, `pattern.formatted(args)` tương đương `String.format(pattern, args)`. Cả hai dùng quy tắc định dạng của `java.util.Formatter`, trả về **một `String` mới**, không sửa chuỗi mẫu. Các đối số nguyên thủy như `int` được tự đóng hộp (*autobox*) khi truyền qua `Object...`.

## 2. Cấu trúc một placeholder

Dạng chung của phần lớn format specifier:

~~~text
%[argument_index$][flags][width][.precision]conversion
~~~

Các dấu ngoặc vuông trong dòng mô tả trên biểu thị **thành phần tùy chọn**, không phải ký tự cần gõ vào chuỗi Java.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `%` | Bắt đầu format specifier | `%s` |
| `argument_index$` | Chọn đối số theo vị trí, **đánh số từ 1** | `%2$s` chọn đối số thứ hai |
| `flags` | Điều khiển cách hiển thị: căn trái, thêm dấu, đệm số 0, v.v. | `%-8s`, `%05d` |
| `width` | Độ rộng tối thiểu của kết quả | `%8s` |
| `.precision` | Độ chính xác; ý nghĩa thay đổi theo conversion | `%.2f`, `%.3s` |
| `conversion` | Xác định kiểu định dạng | `s`, `d`, `f`, `tF` |

Ví dụ, `%2$-10.3s` có nghĩa: chọn **đối số thứ hai**; biểu diễn dạng chuỗi (`s`); tối đa ba ký tự (`.3`); chèn khoảng trắng để đạt tối thiểu mười ký tự (`10`); căn trái (`-`).

~~~java
String result = String.format("|%2$-10.3s|", "ignored", "Long");
// result là "|Lon       |"
~~~

Không phải mọi cờ, độ rộng hoặc độ chính xác đều hợp lệ với mọi conversion. Chẳng hạn `%.2f` có nghĩa làm tròn cách biểu diễn số thực đến hai chữ số sau dấu thập phân, nhưng `%.2d` **không hợp lệ** vì `d` không hỗ trợ precision.

## 3. Các conversion và kiểu đối số

Chọn conversion theo **kiểu giá trị thực sự được truyền**, chứ không chỉ theo hình thức chữ số nhìn thấy.

| Placeholder | Kiểu đối số phù hợp / ý nghĩa | Ví dụ và kết quả |
| --- | --- | --- |
| `%s` / `%S` | Đối tượng bất kỳ: biểu diễn chuỗi; `S` chuyển thành chữ hoa theo locale | `"%s".formatted("Lan")` → `Lan` |
| `%b` / `%B` | Boolean; nếu đối số không phải `Boolean` thì `null` → `false`, đối tượng khác `null` → `true` | `"%b".formatted(false)` → `false` |
| `%d` | Số nguyên thập phân: `byte`, `short`, `int`, `long`, `BigInteger` (và wrapper tương ứng) | `"%d".formatted(42)` → `42` |
| `%x` / `%X` | Số nguyên ở hệ thập lục phân (các kiểu số nguyên được hỗ trợ) | `"%x".formatted(255)` → `ff` |
| `%o` | Số nguyên ở hệ bát phân | `"%o".formatted(8)` → `10` |
| `%f` | Số dấu phẩy động ở dạng thập phân: `float`, `double`, `BigDecimal` | `String.format(Locale.ROOT, "%.2f", 12.5)` → `12.50` |
| `%e` / `%g` | Số dấu phẩy động dạng khoa học / dạng tổng quát | `String.format(Locale.ROOT, "%.1e", 12.5)` → `1.3e+01` |
| `%c` / `%C` | Ký tự `char` hoặc giá trị mã điểm Unicode nguyên hợp lệ | `"%c".formatted('A')` → `A` |
| `%tF` | Ngày theo dạng năm-tháng-ngày; đối số ngày giờ phải hỗ trợ các trường cần thiết, ví dụ `LocalDate` | `String.format(Locale.ROOT, "%tF", LocalDate.of(2026, 11, 8))` → `2026-11-08` |
| `%%` | Dấu phần trăm `%` thật trong kết quả; **không dùng đối số** | `"rate=50%%".formatted()` → `rate=50%` |
| `%n` | Dấu xuống dòng theo nền tảng; **không dùng đối số** | `"A%nB".formatted()` có hai dòng |

Trong bảng, `Locale` nằm ở `java.util.Locale` và `LocalDate` ở `java.time.LocalDate`; ví dụ độc lập cần import tương ứng.

**Ba điểm dễ nhầm về kiểu:**

- `%s` có thể nhận số và gọi cách biểu diễn chuỗi của số, nhưng không vì thế mà thực hiện các quy tắc số của `%d` hay `%f`.
- `%d` **không tự chuyển** một `String` chứa `"7"` thành số nguyên; `"%d".formatted("7")` ném `IllegalFormatConversionException`. Hãy truyền `7` hoặc phân tích chuỗi bằng `Integer.parseInt` khi đầu vào thực sự là văn bản số hợp lệ.
- `%f` **không chấp nhận `Integer`** chỉ vì số nguyên có thể biểu diễn như số thực; hãy truyền `7.0` nếu cần dạng số thực. Với số tiền cần độ chính xác thập phân, cân nhắc `BigDecimal` và quy tắc làm tròn phù hợp.

`%b` cũng không phải phép kiểm tra “giá trị có đúng hay không” cho mọi đối tượng: với một đối tượng non-null không phải `Boolean`, kết quả là `true`, kể cả khi đó là chuỗi `"false"`.

## 4. Chỉ số đối số: tuần tự, chỉ định và dùng lại

### 4.1. Tuần tự (ordinary indexing)

Khi không khai báo chỉ số, từng specifier tiêu thụ đối số theo thứ tự xuất hiện:

~~~java
String text = "%s has %d items".formatted("Lan", 3);
// "Lan has 3 items"
~~~

Ở ví dụ này, `%s` dùng đối số thứ nhất, `%d` dùng đối số thứ hai. Nếu có nhiều đối số hơn số lần cần dùng, các đối số dư bị bỏ qua.

### 4.2. Chỉ định (explicit indexing): `1$`, `2$`, …

Đặt `n$` ngay sau `%` để chọn đối số theo **chỉ số bắt đầu từ 1**:

~~~java
String text = "%2$s - %1$s - %2$s".formatted("one", "two");
// "two - one - two"
~~~

- `%2$s` chọn `"two"`.
- `%1$s` chọn `"one"`.
- `%2$s` dùng lại đối số thứ hai mà **không cần truyền nó thêm lần nữa**.

Có thể dùng cùng một đối số với nhiều kiểu biểu diễn khác nhau nếu các kiểu conversion đều tương thích:

~~~java
String text = "%1$d (hex=%1$x)".formatted(255);
// "255 (hex=ff)"
~~~

### 4.3. Chỉ định tương đối: `<` dùng lại đối số trước đó

Cờ `<` (ví dụ `%<s`, `%<.1f`) dùng lại **đối số mà format specifier có dùng đối số trước đó đã tham chiếu**:

~~~java
String text = "%s/%s/%<s".formatted("A", "B");
// "A/B/B"
~~~

`%<s` là một specifier mới nhưng dùng lại `"B"`. Nếu `<` xuất hiện mà chưa có đối số trước đó để tái sử dụng, Java ném `MissingFormatArgumentException`.

Độ chính xác và conversion vẫn được áp dụng theo specifier mới:

~~~java
String text = String.format(Locale.ROOT,
        "price=%1$.2f; again=%<.1f", 12.5);
// "price=12.50; again=12.5"
~~~

### 4.4. Cẩn thận khi trộn ba chế độ chỉ số

**Chỉ số tuần tự được đếm riêng** với chỉ số chỉ định và tương đối; chúng không đơn giản “tiếp tục từ đối số vừa dùng”. Xét:

~~~java
String text = "%2$s|%s|%<s|%s".formatted("A", "B", "C");
// "B|A|A|B"
~~~

Giải thích theo thứ tự:

1. `%2$s` → đối số số 2: `B`.
2. `%s` → specifier **tuần tự đầu tiên**: đối số số 1: `A`.
3. `%<s` → dùng lại đối số của specifier trước: `A`.
4. `%s` → specifier **tuần tự thứ hai**: đối số số 2: `B`.

Đối số `C` không được dùng. Trong khuôn mẫu phức tạp, ưu tiên dùng chỉ số rõ ràng nhất quán để người đọc không phải tính lại thứ tự.

**`%%` và `%n` không nhận và không tiêu thụ đối số.** Một ký tự `%` thông thường trong khuôn mẫu phải viết thành `%%`; nếu ghi một `%` đơn lẻ, Java có thể coi đây là cú pháp định dạng lỗi.

## 5. Cờ, độ rộng, độ chính xác và locale

Các tùy chọn được áp dụng **sau khi chọn đúng đối số**:

~~~java
String left = String.format("|%-8s|", "Lan");   // "|Lan     |"
String zeros = String.format("%05d", 7);       // "00007"
String decimal = String.format(Locale.ROOT, "%.2f", 12.5); // "12.50"
~~~

- `width` là **độ rộng tối thiểu**, không phải giới hạn trên. Dùng `-` để căn trái; mặc định thường căn phải khi đặt width.
- Precision của `%s` có thể giới hạn số ký tự hiển thị, ví dụ `%.3s` với `"Long"` cho `"Lon"`. Precision của `%f` kiểm soát số chữ số sau dấu thập phân. Với `%d`, precision không được hỗ trợ.
- Dấu `0` dùng để đệm số 0 cho kiểu số phù hợp; dấu `,` yêu cầu nhóm chữ số theo locale; không áp dụng tùy tiện cho kiểu chuỗi.
- `String.formatted(...)` dùng **locale định dạng mặc định** của môi trường, giống `String.format(pattern, args)`. Điều này có thể thay đổi dấu thập phân, phân nhóm hàng nghìn hoặc tên ngày.
- Khi cần kết quả số ổn định giữa các máy, hãy dùng `String.format(Locale.ROOT, pattern, args)` hoặc locale được chỉ định bởi yêu cầu nghiệp vụ. **`String.formatted` không có overload nhận `Locale`**.
- `%n` tạo dấu xuống dòng theo hệ điều hành. Khi giao thức yêu cầu cụ thể LF (`\n`), hãy dùng dấu LF một cách chủ đích thay vì giả định `%n` luôn là LF.

## 6. Ví dụ hoàn chỉnh: Java 17+ và kết quả thực tế

Tạo tệp **`FormatArgumentsDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.IllegalFormatException;
import java.util.Locale;

public class FormatArgumentsDemo {
    public static void main(String[] args) {
        String name = "Lan";
        int quantity = 7;
        double unitPrice = 12.5;

        System.out.println("Hello %s, quantity=%d".formatted(name, quantity));
        System.out.println("%2$s - %1$s - %2$s".formatted("one", "two"));
        System.out.println("%s/%s/%<s".formatted("A", "B"));
        System.out.println("%2$s|%s|%<s|%s".formatted("A", "B", "C"));
        System.out.println(String.format(Locale.ROOT, "price=%1$.2f; again=%<.1f", unitPrice));
        System.out.println(String.format(Locale.ROOT, "|%1$-8s|%2$05d|", name, quantity));
        System.out.println("percent=%%, ok=%b, hex=%x".formatted(true, 255));
        System.out.println("null=%s".formatted((Object) null));
        System.out.println(String.format(Locale.ROOT, "date=%tF", LocalDate.of(2026, 11, 8)));

        String report = """
                Customer: %1$s
                Quantity: %2$d
                """.formatted(name, quantity);
        System.out.println(report.replace("\n", "\\n"));

        checkError("wrongType", "%d", "7");
        checkError("missingIndex", "%2$s", "only");
        checkError("badRelativeIndex", "%<s", "A");
        checkError("badPrecision", "%.2d", 7);
    }

    private static void checkError(String label, String pattern, Object arg) {
        try {
            System.out.println(pattern.formatted(arg));
        } catch (IllegalFormatException ex) {
            System.out.println(label + ": " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 FormatArgumentsDemo.java
java FormatArgumentsDemo
~~~

**Kết quả stdout chính xác** (đã kiểm tra khi biên dịch ở mức Java 17):

~~~text
Hello Lan, quantity=7
two - one - two
A/B/B
B|A|A|B
price=12.50; again=12.5
|Lan     |00007|
percent=%, ok=true, hex=ff
null=null
date=2026-11-08
Customer: Lan\nQuantity: 7\n
wrongType: IllegalFormatConversionException
missingIndex: MissingFormatArgumentException
badRelativeIndex: MissingFormatArgumentException
badPrecision: IllegalFormatPrecisionException
~~~

Dòng `Customer: Lan\nQuantity: 7\n` hiển thị hai ký tự `\` và `n` thay cho từng ký tự xuống dòng thật vì chương trình gọi `replace` trước khi in. Text block chỉ là cách viết **chuỗi mẫu**; các placeholder vẫn được xử lý bởi `formatted` sau đó.

## 7. Các lỗi thường gặp và cách xử lý

Các lỗi cú pháp/kiểu định dạng được biểu diễn bằng các ngoại lệ thuộc họ `java.util.IllegalFormatException`.

| Hiện tượng | Ngoại lệ điển hình | Nguyên nhân và cách sửa |
| --- | --- | --- |
| `"%d".formatted("7")` | `IllegalFormatConversionException` | Đối số là `String`, không phải số nguyên. Truyền `7` hoặc chuyển đổi hợp lệ sang `int` trước. |
| `"%2$s".formatted("only")` | `MissingFormatArgumentException` | Truy cập đối số thứ hai nhưng chỉ truyền một đối số. Truyền đủ hoặc đổi `%2$s` thành `%1$s`. |
| `"%<s".formatted("A")` | `MissingFormatArgumentException` | Dùng `<` khi chưa có đối số trước đó để tham chiếu. Dùng `%s` cho lần đầu. |
| `"%.2d".formatted(7)` | `IllegalFormatPrecisionException` | `%d` không hỗ trợ precision. Dùng `%d` hoặc chọn conversion phù hợp. |
| `"%q".formatted("A")` | `UnknownFormatConversionException` | `q` không phải conversion được hỗ trợ. Chọn conversion được tài liệu `Formatter` định nghĩa. |
| Muốn hiển thị `50%` nhưng viết `"50%"` làm format string | Có thể báo lỗi định dạng | Viết `"50%%"` nếu mẫu phải đi qua `formatted`. |
| Số thập phân khác nhau giữa các máy | Không nhất thiết là lỗi | Locale định dạng mặc định khác nhau; chỉ định `Locale` bằng `String.format` khi cần đầu ra ổn định. |
| Dùng `%n` rồi so sánh từng byte trên nhiều hệ điều hành | Dấu kết thúc dòng có thể khác nhau | Chuẩn hóa dấu dòng hoặc định nghĩa LF/CRLF theo giao thức. |

Không nên chỉ kiểm tra kiểu bằng mắt: `"123"` khác `123`, `7` khác `7.0`, và `new BigDecimal("7.0")` là một đối tượng thập phân với những conversion được hỗ trợ riêng. Cũng không nên lạm dụng `%s` để né lỗi kiểu nếu yêu cầu thực sự là định dạng số.

## 8. Chọn đúng API và hiểu giới hạn của placeholder

- **`String.formatted(args)`:** tiện khi chính chuỗi hiện tại đã là khuôn mẫu, đặc biệt với text block. Có từ Java 15, không cần dùng chế độ preview.
- **`String.format(Locale, pattern, args)`:** phù hợp khi cần kiểm soát locale, ví dụ xuất số hoặc ngày với quy ước cố định.
- **`System.out.printf(pattern, args)`:** cùng họ cú pháp specifier, nhưng **in ra luồng đầu ra** thay vì trả về chuỗi để tiếp tục xử lý.
- **`java.text.MessageFormat`:** dùng cú pháp khác như `{0}`, `{1}` với chỉ số **bắt đầu từ 0**. Đừng trộn `{0}` với `%1$s` của `Formatter`.
- **Giới hạn bảo mật:** Placeholder `%s` chỉ thay thế thành văn bản; nó **không tự escape SQL, JSON, HTML hoặc URL**. Với SQL, dùng `PreparedStatement` và tham số ràng buộc; với các định dạng dữ liệu khác, dùng API encoder/serializer phù hợp.

**Checklist thực hành:** nhìn vào `%` → xác định chỉ số đối số (tuần tự, `n$`, hay `<`) → kiểm tra conversion có khớp kiểu đối số → kiểm tra flags/width/precision → kiểm tra locale và ký tự `%`/xuống dòng. Làm đúng thứ tự này giúp chẩn đoán phần lớn lỗi formatting mà không phải đoán kết quả.

## 9. Tài liệu chuẩn còn hiệu lực

- [Java SE 27 — `String.formatted(Object... args)` và `String.format`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html)
- [Java SE 26 — `java.util.Formatter`: format specifier, argument index, conversion, flags](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Formatter.html)

Bài học tập trung vào **API định dạng chuỗi hiện hành**, kể cả phương thức `String.formatted` được bổ sung từ Java 15; không sử dụng cú pháp thử nghiệm hay API đã ngừng được hỗ trợ.