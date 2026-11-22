# Cấu trúc chuỗi định dạng và chỉ định chuyển đổi

## 1. Chuỗi định dạng là một khuôn có quy tắc

Khi ghép tên sản phẩm, số lượng và giá, phép nối chuỗi chỉ chuyển giá trị thành văn bản. Nếu cần căn cột, thêm số 0 hoặc giới hạn số chữ số thập phân, ta cần một khuôn rõ ràng.

Trong họ API `Formatter`, phần văn bản thường được giữ nguyên; mỗi phần bắt đầu bằng `%` mô tả cách lấy và biểu diễn một đối số.

```java
System.out.printf(Locale.ROOT,
        "Item: %s, count: %d, price: %.2f%n",
        "Book", 3, 12.5);
```

Đoạn này đặt trong một phương thức và cần import `java.util.Locale`. Kết quả là:

```text
Item: Book, count: 3, price: 12.50
```

Ở đây:

- `%s` định dạng đối số thứ nhất thành chuỗi.
- `%d` định dạng đối số thứ hai theo số nguyên thập phân.
- `%.2f` định dạng đối số thứ ba theo số thực thập phân với hai chữ số sau dấu phân cách.
- `%n` tạo dấu xuống dòng của nền tảng, không lấy đối số.

Các API này được đưa vào từ Java 5 và vẫn phù hợp trên Java hiện đại. Ví dụ trong bài chạy với Java 17+; ngày tháng dùng `java.time` khi cần.

## 2. Cấu trúc tổng quát của một chỉ định định dạng

Với các nhóm chuyển đổi thông thường:

```text
%[argument_index$][flags][width][.precision]conversion
```

Dấu ngoặc vuông trong sơ đồ nghĩa là thành phần tùy chọn, không phải ký tự cần viết trong khuôn.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| % | Mở đầu chỉ định | %s |
| argument_index$ | Chọn đối số, đánh số từ 1 | %2$s |
| flags | Các cờ điều khiển biểu diễn | %-10s, %+d |
| width | Độ rộng tối thiểu | %8d |
| .precision | Độ chính xác, ý nghĩa tùy chuyển đổi | %.2f, %.3s |
| conversion | Nhóm biểu diễn và kiểu đối số phù hợp | s, d, f, x |

Ví dụ:

```text
%2$-10.3s
 | | |  |
 | | |  +-- s: chuyển đổi chuỗi
 | | +----- .3: tối đa 3 ký tự cho chuỗi thông thường
 | +------- - và 10: căn trái trong độ rộng tối thiểu 10
 +--------- 2$: lấy đối số thứ hai
```

Ký tự `$` đứng sau chỉ số đối số. Nó không liên quan ký hiệu tiền tệ. Chữ số không có `$` có thể thuộc width; vì vậy `%2s` và `%2$s` mang ý nghĩa khác nhau.

Không phải mọi cờ hoặc precision đều hợp lệ với mọi conversion. Cú pháp hợp lệ về thứ tự vẫn có thể sai về tổ hợp, chẳng hạn `%.2d` không hợp lệ cho số nguyên thập phân.

Quy tắc đầy đủ nằm trong [Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html).

## 3. Chọn đối số: tuần tự, tường minh và dùng lại

### Chọn tuần tự

Mỗi chỉ định lấy đối số kế tiếp trong chuỗi chọn tuần tự:

```java
String text = String.format(Locale.ROOT,
        "%s has %d books", "Lan", 3);
```

`text` bằng `"Lan has 3 books"`.

### Chọn bằng chỉ số từ 1

```java
String text = String.format(Locale.ROOT,
        "%2$s has code %1$d", 7, "Lan");
```

`text` bằng `"Lan has code 7"`. Chỉ số tính trong danh sách đối số được định dạng, không tính tham số Locale hay chuỗi khuôn.

Một đối số có thể được dùng nhiều lần:

```java
String text = String.format(Locale.ROOT,
        "%1$s / %1$s", "Lan");
```

Kết quả là `"Lan / Lan"`.

### Dùng lại đối số gần nhất bằng cờ <

```java
String text = String.format(Locale.ROOT,
        "%s -> %<S", "book");
```

Kết quả là `"book -> BOOK"`. `<` yêu cầu lấy lại đối số đã được chỉ định trước đó; nó không tự có đối số để dùng nếu xuất hiện ngay đầu như `%<s`.

### Tránh nhầm khi trộn các cách chọn

Chọn tuần tự có bộ đếm riêng với chọn chỉ số tường minh. Ví dụ:

```java
String text = String.format(Locale.ROOT,
        "%2$s | %s | %<s | %s", "A", "B");
```

Kết quả là:

```text
B | A | A | B
```

Lần `%2$s` lấy B nhưng không làm lần chọn tuần tự đầu tiên `%s` chuyển sang một đối số mới ngoài A. Cờ `<` sau đó dùng lại A.

Dù được phép, trộn nhiều kiểu chọn khiến khuôn khó đọc. Với khuôn dài hoặc cần đảo vị trí cho bản dịch, dùng chỉ số tường minh nhất quán thường dễ kiểm tra hơn.

Đối số dư có thể bị bỏ qua nếu khuôn không dùng tới. Đối số thiếu cho một chỉ định lại gây lỗi; không dựa vào số lượng tham số để đoán khuôn đã đúng.

## 4. Các nhóm chuyển đổi thường gặp

| Nhóm | Chuyển đổi tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Tổng quát | %s, %b, %h | Chuỗi, biểu diễn boolean, hash dạng hex |
| Ký tự | %c | Ký tự hoặc mã Unicode phù hợp |
| Số nguyên | %d, %o, %x | Thập phân, bát phân, thập lục phân |
| Số thực | %f, %e, %g, %a | Thập phân, khoa học, tổng quát, số thực hex |
| Ngày giờ | %t với hậu tố, như %tF | Thành phần hoặc tổ hợp ngày giờ |
| Ký tự đặc biệt | %%, %n | Dấu phần trăm và xuống dòng |

### %s: biểu diễn chuỗi

Với đối tượng thông thường, `%s` dùng biểu diễn chuỗi; giá trị null được in thành `null`. Đối tượng triển khai `Formattable` có thể tùy biến cách định dạng theo hợp đồng riêng.

`%s` không có nghĩa “chỉ chấp nhận đối số String”. Nó có thể nhận nhiều loại đối tượng, nhưng dùng `%s` cho mọi dữ liệu sẽ không tạo được quy tắc số học như thêm số 0, dấu hay số lẻ thập phân.

### %b: không phải phép kiểm tra số bằng 0

Với đối số Boolean, `%b` biểu diễn giá trị boolean. Với null, kết quả là false. Với đối tượng không null khác, kết quả là true.

Do đó, `String.format(Locale.ROOT, "%b", 0)` cho `"true"`: số nguyên 0 được đóng hộp thành một đối tượng không null. Không dùng `%b` để thay một điều kiện nghiệp vụ.

### %h: không phải mã hóa hoặc băm mật mã

`%h` biểu diễn giá trị hashCode theo dạng hex cho đối tượng thông thường, hoặc `null` với null. Không dùng nó làm định danh duy nhất, dấu kiểm tra toàn vẹn hoặc giá trị băm bảo mật.

### %c: ký tự

Có thể dùng `char`/Character hoặc một số kiểu số nguyên tương thích để biểu diễn ký tự/mã Unicode hợp lệ. Nó không lấy chữ số cuối của một số để in. Mã nằm ngoài miền hợp lệ có thể gây lỗi định dạng.

### Nhóm số nguyên

`%d` cần kiểu số nguyên được hỗ trợ, không tự chấp nhận một Double dù giá trị đang là 7.0. `%o` và `%x` dùng hệ cơ số tương ứng. Kiểu đối số ảnh hưởng cách biểu diễn số âm; đừng áp dụng ví dụ của int cho mọi kiểu như BigInteger mà không xem hợp đồng.

### Nhóm số thực

- `%f`: dạng thập phân, precision là số chữ số sau dấu phân cách.
- `%e`: dạng khoa học, precision là số chữ số sau dấu phân cách của phần định trị.
- `%g`: dạng tổng quát; precision liên quan số chữ số có nghĩa, không đơn giản là số chữ số sau dấu phẩy.
- `%a`: dạng số thực thập lục phân cho các kiểu phù hợp.

Không phải mọi kiểu số thực được mọi conversion hỗ trợ. Ví dụ không nên suy ra BigDecimal dùng được với `%a` chỉ vì nó dùng được với một số chuyển đổi thập phân.

## 5. Width và precision giải quyết hai việc khác nhau

### Width là độ rộng tối thiểu

```java
String text = String.format(Locale.ROOT, "[%5d]", 12);
```

`text` là `"[   12]"`: ba dấu cách rồi hai chữ số.

Nếu dữ liệu dài hơn width, nó không bị cắt chỉ vì width nhỏ:

```java
String text = String.format(Locale.ROOT, "[%2d]", 12345);
```

Kết quả là `"[12345]"`.

Width không phải giới hạn bộ nhớ, giới hạn số chữ số hay bảo đảm số ô hiển thị trên mọi terminal. Văn bản Unicode, dấu kết hợp và phông chữ có thể khiến độ dài chuỗi khác cảm nhận thị giác.

### Precision tùy vào conversion

```java
String text = String.format(Locale.ROOT,
        "[%.3s] [%.2f]", "Notebook", 12.5);
```

Kết quả là `"[Not] [12.50]"`.

Với chuỗi thông thường, `.3` giới hạn phần văn bản được dùng; với `f`, `.2` tạo hai chữ số phần lẻ và thực hiện làm tròn định dạng khi cần. Đây là hai ý nghĩa khác nhau.

`%.2d` không phải cách buộc một số nguyên có hai chữ số. Nếu muốn thêm số 0 cho số nguyên, dùng cờ `0` và width, chẳng hạn `%02d`.

Định dạng số để hiển thị cũng không thay đổi giá trị gốc hoặc thay cho quy tắc tính toán tiền tệ. Việc thấy hai chữ số phần lẻ không làm một phép tính double trở nên chính xác theo số thập phân.

## 6. Các cờ thường gặp và giới hạn áp dụng

| Cờ | Ví dụ | Ý nghĩa khi hợp lệ |
| --- | --- | --- |
| - | %-10s | Căn trái trong width |
| 0 | %04d | Đệm số 0 theo quy tắc số |
| + | %+d | Hiện dấu cho số dương và âm |
| dấu cách | % d | Dành dấu cách cho số dương |
| , | %,d | Phân nhóm chữ số theo locale |
| ( | %(d | Biểu diễn số âm bằng ngoặc khi được hỗ trợ |
| # | %#x | Dạng thay thế, như tiền tố cơ số |
| < | %<s | Dùng lại đối số gần nhất |

Ví dụ `%04d` là cờ 0 và width 4; nó khác `%.4d` vốn không hợp lệ.

Cờ cần được kiểm tra với conversion. Chẳng hạn cờ số `+` không tự có nghĩa với chuỗi `s`; cờ căn trái `-` mà thiếu width cũng gây lỗi.

Một số cờ không được dùng cùng nhau. Không ghép tùy ý mọi ký hiệu trong bảng rồi kỳ vọng Formatter bỏ qua cờ không phù hợp. Java kiểm tra các tổ hợp và báo lỗi khi không hợp lệ.

Các conversion có dạng chữ hoa như `S`, `X`, `E` tạo dạng chữ hoa tương ứng theo hợp đồng. Không phải chỉ cần viết hoa bất kỳ ký tự conversion nào cũng hợp lệ.

## 7. Ngày giờ dùng tiền tố t/T và một hậu tố

Cấu trúc ngày giờ có thêm hậu tố:

```text
%[argument_index$][flags][width]t[suffix]
```

Ví dụ `%1$tF`:

- `1$`: chọn đối số thứ nhất.
- `t`: nhóm chuyển đổi ngày giờ.
- `F`: dạng ngày ISO gồm năm-tháng-ngày theo quy tắc Formatter.

Với kiểu hiện đại:

```java
LocalDate date = LocalDate.of(2026, 10, 29);
String text = String.format(Locale.ROOT,
        "%1$tF / %1$tY", date);
```

Cần import `java.time.LocalDate`. Kết quả là `"2026-10-29 / 2026"`.

Một TemporalAccessor chỉ dùng được với những thành phần mà nó cung cấp. LocalDate không có giờ, nên không dùng nó cho một chuyển đổi cần giờ rồi kỳ vọng tự được gán 00:00.

Đừng nhầm `%tF` với mẫu của `DateTimeFormatter` hoặc `SimpleDateFormat`. Chúng là các ngôn ngữ khuôn khác nhau; ký hiệu giống nhau không làm chúng thay thế cho nhau.

## 8. %% và %n không lấy đối số

```java
System.out.printf(Locale.ROOT,
        "Progress: %d%%%n", 80);
```

Kết quả là một dòng `Progress: 80%` rồi xuống dòng.

Ba ký tự `%%%` ở phần cuối dễ gây nhầm: `%d` là chỉ định lấy 80, `%%` in một dấu phần trăm, và `%n` tạo xuống dòng. Nhìn theo từng chỉ định sẽ rõ hơn là đếm dấu phần trăm rời rạc.

`%n` không tự có trong mọi printf. Nếu không thêm nó hoặc ký tự xuống dòng khác, lời gọi printf không bắt buộc đưa con trỏ sang dòng mới.

Xuống dòng của `%n` có thể là CRLF trên Windows hoặc LF trên môi trường khác. Những khối stdout trong bài biểu diễn các dòng, không mặc định byte xuống dòng giống nhau trên mọi hệ điều hành.

## 9. Chương trình tổng hợp có output kiểm chứng được

Lưu thành `FormatStructureDemo.java`:

```java
import java.time.LocalDate;
import java.util.Formatter;
import java.util.Locale;

public class FormatStructureDemo {
    public static void main(String[] args) {
        System.out.printf(Locale.ROOT,
                "[%2$-10.3s] id=%1$04d%n", 7, "Notebook");

        System.out.printf(Locale.ROOT,
                "%2$s | %s | %<s | %s%n", "A", "B");

        System.out.printf(Locale.ROOT,
                "dec=%d oct=%o hex=%#x%n", 26, 26, 26);

        System.out.printf(Locale.ROOT,
                "fixed=%.2f scientific=%.2e general=%.3g%n",
                12.5, 12.5, 12345.0);

        System.out.printf(Locale.ROOT,
                "hexFloat=%a char=%c%n", 1.5, 'A');

        System.out.printf(Locale.ROOT,
                "null=%s booleanZero=%b%n", (Object) null, 0);

        LocalDate date = LocalDate.of(2026, 10, 29);
        System.out.printf(Locale.ROOT,
                "date=%1$tF year=%1$tY%n", date);

        String progress = String.format(Locale.ROOT,
                "Progress: %d%%", 80);
        System.out.println(progress);

        StringBuilder target = new StringBuilder();
        try (Formatter formatter = new Formatter(target, Locale.ROOT)) {
            formatter.format("signed=%+d padded=%04d", 12, 7);
        }
        System.out.println(target);
    }
}
```

Chạy:

```shell
javac FormatStructureDemo.java
java FormatStructureDemo
```

Stdout:

```text
[Not       ] id=0007
B | A | A | B
dec=26 oct=32 hex=0x1a
fixed=12.50 scientific=1.25e+01 general=1.23e+04
hexFloat=0x1.8p0 char=A
null=null booleanZero=true
date=2026-10-29 year=2026
Progress: 80%
signed=+12 padded=0007
```

Dòng đầu có bảy dấu cách sau Not. Dấu ngoặc vuông giúp nhìn rõ vùng đệm. Locale.ROOT làm kết quả số trong thí nghiệm độc lập với locale mặc định của máy.

## 10. Cùng ngôn ngữ khuôn, khác nơi nhận kết quả

| API | Đích đến | Lưu ý |
| --- | --- | --- |
| System.out.printf | PrintStream hiện hành | Ghi ra luồng; không tự thêm xuống dòng |
| System.out.format | PrintStream hiện hành | Cùng kiểu định dạng với printf |
| String.format | Chuỗi mới | Không tự in ra console |
| new Formatter(target).format | Đích Appendable phù hợp | Quản lý vòng đời Formatter và đích |
| formatString.formatted(args) | Chuỗi mới | API bổ sung ở Java sau Java 5, dùng locale mặc định |

[PrintStream.printf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html#printf(java.lang.String,java.lang.Object...)) phục vụ việc in có định dạng. [String.format](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#format(java.util.Locale,java.lang.String,java.lang.Object...)) tạo chuỗi để bên gọi dùng tiếp.

Khi output cần tái lập, truyền locale tường minh vào overload hỗ trợ locale. Không giả định dấu phân cách thập phân, phân nhóm hay tên tháng giống nhau trên mọi máy.

Trong ví dụ, Formatter ghi vào StringBuilder riêng nên có thể đóng bằng try-with-resources. Nếu tạo Formatter bao một luồng khác, việc đóng nó có thể ảnh hưởng đích đóng được; cần hiểu quyền sở hữu đích, đặc biệt khi dùng System.out.

Không chia sẻ tùy ý một Formatter giữa nhiều luồng. Cần tuân thủ quy tắc đồng bộ của đối tượng đang sử dụng, thay vì suy ra rằng mọi API định dạng đều có cùng bảo đảm đồng thời.

## 11. Lỗi định dạng là lỗi lúc chạy

Chuỗi khuôn là String, còn danh sách đối số thường là varargs Object. Trình biên dịch Java không luôn chứng minh kiểu của từng đối số khớp từng chỉ định.

Lưu thành `FormatErrorDemo.java`:

```java
import java.util.IllegalFormatException;
import java.util.Locale;

public class FormatErrorDemo {
    private static void show(String label, String pattern, Object... args) {
        try {
            String result = String.format(Locale.ROOT, pattern, args);
            System.out.println(label + ": " + result);
        } catch (IllegalFormatException e) {
            System.out.println(label + ": "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("wrong type", "%d", 7.0);
        show("missing argument", "%s %s", "only one");
        show("unknown conversion", "%q", 7);
        show("missing width", "%-s", "book");
        show("invalid precision", "%.2d", 7);
        show("incompatible flag", "%+s", "book");
    }
}
```

Chạy:

```shell
javac FormatErrorDemo.java
java FormatErrorDemo
```

Stdout:

```text
wrong type: IllegalFormatConversionException
missing argument: MissingFormatArgumentException
unknown conversion: UnknownFormatConversionException
missing width: MissingFormatWidthException
invalid precision: IllegalFormatPrecisionException
incompatible flag: FormatFlagsConversionMismatchException
```

Trong ứng dụng, không nên bắt mọi lỗi này rồi âm thầm trả chuỗi rỗng. Với khuôn do chương trình quản lý, chúng thường là lỗi cần sửa và kiểm tra bằng dữ liệu đại diện.

Nếu một API ghi ra đích đã in một phần trước khi phát hiện lỗi sau đó, không coi ngoại lệ là một cơ chế hoàn tác toàn bộ output. Khi cần chuẩn bị văn bản trọn vẹn trước khi phát hành, có thể tạo String trước rồi ghi theo giao thức phù hợp.

## 12. Những nhầm lẫn thường gặp

- Dùng `{}` kiểu placeholder của thư viện log trong printf: nó chỉ là văn bản thường ở ngôn ngữ khuôn này.
- Dùng `%d` cho String chứa chữ số: Formatter không tự parse chuỗi thành số nguyên.
- Dùng width để cắt nội dung dài: width chỉ là tối thiểu.
- Dùng precision của số thực cho số nguyên: `%.2d` không hợp lệ.
- Viết `%` đơn lẻ để in phần trăm: cần `%%`.
- Nghĩ `%b` của 0 là false: 0 là đối tượng không null khi đóng hộp.
- Thay đổi thứ tự đối số nhưng quên sửa chỉ số trong khuôn.
- Dùng cùng ký hiệu ngày giờ giữa Formatter và DateTimeFormatter mà không chuyển đúng ngôn ngữ khuôn.

Khuôn nên do chương trình quản lý khi định dạng dữ liệu từ bên ngoài. Ví dụ, để in nguyên văn một chuỗi người dùng có dấu phần trăm, dùng `System.out.printf("%s%n", text)` thay vì coi `text` là khuôn. Mục đích là giữ dữ liệu ở vị trí đối số và không để ký tự trong dữ liệu bị diễn giải như chỉ định định dạng.

## 13. Tự kiểm tra

1. `%2$04d` lấy đối số thứ mấy và dùng width bao nhiêu?  
   Đối số thứ hai, width tối thiểu 4, đệm 0 theo quy tắc số.

2. `%5s` có cắt chuỗi dài 10 ký tự xuống 5 không?  
   Không. Width là tối thiểu.

3. `%.3s` và `%.3f` có cùng ý nghĩa không?  
   Không. Một bên giới hạn văn bản chuỗi thông thường, bên kia đặt số chữ số phần lẻ.

4. `%%` và `%n` có làm bộ đếm chọn đối số tuần tự tăng không?  
   Không. Chúng không lấy đối số.

5. Vì sao cần kiểm tra kiểu dù mã biên dịch được?  
   Vì hợp đồng conversion và đối số thường được xác minh khi Formatter diễn giải khuôn lúc chạy.

Đọc một chỉ định theo đúng thứ tự: chọn đối số nào, áp cờ gì, cần độ rộng/độ chính xác nào, rồi dùng conversion nào. Đó là cách hiểu khuôn có thể kiểm tra được, thay vì ghi nhớ từng chuỗi ký hiệu rời rạc.
