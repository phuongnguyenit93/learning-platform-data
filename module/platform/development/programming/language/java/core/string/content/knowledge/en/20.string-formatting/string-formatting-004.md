# Căn lề, đệm ký tự và phân nhóm chữ số khi định dạng chuỗi Java

## 1. Bài toán và công cụ

Khi tạo báo cáo dạng văn bản, bảng điều khiển (console), hóa đơn hay dòng log, ta thường muốn **căn các cột thẳng hàng**, **thêm ký tự đệm cho đủ chiều rộng** và **phân nhóm chữ số** để dễ đọc:

```text
Tên           Số lượng        Doanh thu
Java                 42         1,234,567
Spring                7            12,500
```

Java cung cấp cơ chế định dạng bằng **format string** trong `String.format(...)`, `System.out.printf(...)` và `java.util.Formatter`. Các API này dùng chung quy tắc định dạng, nhưng khác cách nhận kết quả:

- `String.format(Locale, format, args...)` **trả về một `String`**, thuận tiện để đưa vào biến, ghi file hoặc trả về từ phương thức.
- `System.out.printf(Locale, format, args...)` **ghi trực tiếp ra standard output**; nếu muốn xuống dòng, thêm `%n` vào chuỗi format.
- `Formatter` cho phép ghi nhiều lần vào một đối tượng đích; đa số ví dụ cơ bản dùng `String.format` hoặc `printf` là đủ.
- `"Hello %s".formatted(name)` (Java 15+) cũng sử dụng ngữ nghĩa Formatter, nhưng không có tham số `Locale` trực tiếp trong cách gọi này; khi cần kết quả nhất quán giữa môi trường, ưu tiên overload có `Locale` tường minh.

Ba yêu cầu dễ bị nhầm là:

1. **Căn lề (alignment)**: nội dung nằm bên trái hay bên phải vùng có độ rộng tối thiểu.
2. **Đệm (padding)**: thêm khoảng trắng hoặc số `0` để đủ vùng đó.
3. **Phân nhóm số (grouping)**: thêm ký hiệu phân tách giữa các nhóm chữ số, do `Locale` quyết định.

Căn lề và đệm xử lý cách trình bày; phân nhóm thay đổi cách hiển thị các chữ số. Chúng có thể kết hợp, nhưng phải dùng đúng cờ định dạng.

## 2. Cú pháp một định dạng trong Java

Một conversion có dạng tổng quát:

```text
%[argument_index$][flags][width][.precision]conversion
```

Dấu ngoặc vuông ở dòng trên chỉ thành phần **tùy chọn trong mô tả**, không phải ký tự nhập nguyên xi vào format string.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `%` | `%10s` | Bắt đầu một chỉ thị định dạng. |
| `argument_index$` | `%2$s` | Tùy chọn lấy đối số theo vị trí, đánh số từ `1`. |
| `flags` | `-`, `0`, `,`, `+`, `(` | Các hành vi như căn trái, đệm số không, phân nhóm, hiển thị dấu. |
| `width` | `10` trong `%10s` | **Chiều rộng tối thiểu** của trường xuất. |
| `.precision` | `.2` trong `%.2f` | Ý nghĩa phụ thuộc conversion: số chữ số sau dấu thập phân với `%f`, độ dài hiển thị tối đa cho `%s`. |
| `conversion` | `s`, `d`, `f` | Loại định dạng của đối số. |

Các conversion dùng nhiều trong bài:

| Conversion | Dùng cho | Ví dụ |
| --- | --- | --- |
| `%s` | Chuỗi/đối tượng hiển thị dạng chuỗi | `"%10s"` |
| `%d` | Số nguyên hệ thập phân | `"%08d"` |
| `%f` | Số thực dạng thập phân cố định | `"%,12.2f"` |
| `%%` | In ký tự phần trăm `%` | `"100%%"` |
| `%n` | Xuống dòng theo nền tảng đang chạy | `"Done%n"` |

Không phải mọi cờ đều dùng được với mọi conversion. Chẳng hạn `0` là cờ đệm số, **không phải** cờ đệm chuỗi `%s`; còn dấu phẩy phân nhóm `,` áp dụng với một số conversion số thích hợp chứ không áp dụng cho `%s`.

## 3. Căn phải và căn trái bằng chiều rộng tối thiểu

### 3.1. Căn phải mặc định

Với `%10s`, phần hiển thị chiếm **ít nhất 10 vị trí ký tự**. Nếu `"Java"` có bốn ký tự, Java thêm sáu khoảng trắng ở **bên trái**:

```java
String right = String.format("%10s", "Java");
// right = "      Java" (6 khoảng trắng rồi đến Java)
```

Đối với `%d`, căn phải cũng là mặc định:

```java
String rightNumber = String.format("%8d", 42);
// rightNumber = "      42"
```

### 3.2. Cờ `-` để căn trái

`%-10s` và `%-8d` thêm khoảng trắng ở **bên phải**:

```java
String left = String.format("%-10s", "Java");
// left = "Java      "

String leftNumber = String.format("%-8d", 42);
// leftNumber = "42      "
```

Khi in ví dụ ra console, nên đặt ký tự `|` bao quanh từng giá trị để thấy rõ khoảng trắng:

```java
System.out.printf("|%10s|%-10s|%n", "Java", "Java");
// |      Java|Java      |
```

**Cần nhớ:** `width` là chiều rộng **tối thiểu**, không phải chiều rộng tối đa. `%10s` sẽ **không cắt ngắn** chuỗi dài hơn 10 ký tự. Ví dụ `String.format("%10s", "VeryLongText")` vẫn trả về `"VeryLongText"`. Nếu cần giới hạn độ dài hiển thị của chuỗi, xem `precision` trong mục 7.

## 4. Đệm số `0`: số nguyên có độ dài cố định

Với số nguyên, cờ `0` bổ sung các số không ở **bên trái phần chữ số** để tổng chiều rộng đạt `width`:

```java
System.out.printf("|%08d|%n", 42);
// |00000042|
```

Phân biệt ba tình huống:

| Format | Giá trị | Kết quả trong `|...|` | Ghi chú |
| --- | ---: | --- | --- |
| `%8d` | `42` | `\|      42\|` | Mặc định đệm khoảng trắng bên trái. |
| `%-8d` | `42` | `\|42      \|` | Căn trái, đệm khoảng trắng bên phải. |
| `%08d` | `42` | `\|00000042\|` | Đệm số không ở bên trái số. |
| `%+08d` | `42` | `\|+0000042\|` | Dấu `+` xuất hiện trước các số `0`. |
| `%(08d` | `-42` | `\|(000042)\|` | Số âm trong ngoặc, các số `0` nằm trong ngoặc. |

Đặc điểm quan trọng: chiều rộng `8` **tính cả dấu cộng/trừ hoặc dấu ngoặc** do định dạng thêm vào. Vì thế `%+08d` của `42` là `+0000042`, có tổng cộng tám ký tự.

Cờ `0` cần một `width`; một format như `%0d` là không hợp lệ. Cờ `-` (căn trái) và `0` (đệm số không bên trái) không được kết hợp tùy tiện trong cùng chỉ thị, vì chúng xung đột về cách đệm.

Đối với mã định danh kiểu `000042`, cách đệm `%06d` có ích nếu giá trị là số nguyên. Nếu phải giữ nguyên **chuỗi định danh** như `"00A42"` hoặc số có độ dài/leading zeros vốn là dữ liệu, hãy lưu nó dưới dạng `String`; chuyển sang kiểu số có thể làm mất các số `0` gốc.

## 5. Phân nhóm chữ số bằng cờ dấu phẩy `,`

Cờ `,` trong `Formatter` yêu cầu định dạng **phân nhóm chữ số theo Locale**. Với `Locale.US`, một số nguyên lớn thường được nhóm thành từng cụm ba chữ số, ngăn bằng dấu phẩy:

```java
import java.util.Locale;

String result = String.format(Locale.US, "%,d", 1_234_567);
System.out.println(result);
// 1,234,567
```

Dấu phẩy `,` **trong format string** là một **cờ cú pháp**, không nhất thiết là ký tự sẽ xuất hiện trong kết quả. Dấu phân nhóm thực tế tùy `Locale`.

### 5.1. Kết hợp phân nhóm và căn lề

`%,12d` vừa bật phân nhóm vừa yêu cầu vùng rộng tối thiểu 12 ký tự:

```java
String result = String.format(Locale.US, "|%,12d|", 1_234_567);
System.out.println(result);
// |   1,234,567|
```

`1,234,567` có 9 ký tự, nên có 3 khoảng trắng bên trái. Với `%-,12d`, khoảng trắng được đưa sang bên phải:

```java
String result = String.format(Locale.US, "|%-,12d|", 1_234_567);
System.out.println(result);
// |1,234,567   |
```

### 5.2. Kết hợp phân nhóm và đệm số không

Có thể dùng cả `0` lẫn `,`. Ví dụ:

```java
String result = String.format(Locale.US, "|%0,12d|", 1_234_567);
System.out.println(result);
// |0001,234,567|
```

Số `0` được thêm vào vị trí đệm để đủ chiều rộng; kết quả không giống việc thêm các số `0` vào giá trị số ban đầu rồi tự động phân nhóm lại. Vì yêu cầu đầu ra thường khác nhau, cần chọn rõ:

- **Trình bày số dễ đọc:** `%,d` hoặc `%,12d`.
- **Tạo trường số có độ rộng cố định:** `%08d`.
- **Vừa phân nhóm vừa đệm `0`:** `%0,12d` nếu thực sự muốn dạng hiển thị như trên.

Khi dữ liệu vượt quá chiều rộng tối thiểu, `Formatter` vẫn in **toàn bộ** giá trị; nó không tự cắt chữ số.

## 6. Phân nhóm phần nguyên và làm tròn phần thập phân

Với `%f`, `precision` là số chữ số **sau dấu thập phân** cần hiển thị. Kết hợp:

```java
String amount = String.format(
        Locale.US,
        "%,.2f",
        1234567.5
);
System.out.println(amount);
// 1,234,567.50
```

Có thể thêm chiều rộng:

```java
String amount = String.format(
        Locale.US,
        "|%,15.2f|",
        1234567.5
);
System.out.println(amount);
// |   1,234,567.50|
```

Giải thích `%,15.2f`:

1. `,` bật phân nhóm chữ số phần nguyên.
2. `15` yêu cầu tối thiểu 15 vị trí ký tự.
3. `.2` quy định hiển thị hai chữ số sau dấu thập phân.
4. `f` chọn dạng số thực thập phân cố định.

**Đừng nhầm `%.2f` với `%.2s`:** ở `%f`, precision nói về số chữ số sau dấu thập phân; ở `%s`, precision giới hạn độ dài chuỗi được hiển thị. Với `%d`, cú pháp `%.2d` không phải cách hợp lệ để đệm hai số không trong Java Formatter. Hãy dùng `%02d` khi muốn chiều rộng hai và đệm số không.

Khi định dạng giá trị tiền tệ, cần xác định cả loại số và yêu cầu làm tròn. `String.format` tạo **biểu diễn văn bản**, không biến `double` thành kiểu số thập phân chính xác để tính toán tiền. Đối với phép tính tiền cần độ chính xác thập phân, dùng kiểu và quy tắc làm tròn phù hợp (thường là `BigDecimal`), sau đó mới định dạng để hiển thị.

## 7. Locale quyết định dấu phân nhóm và dấu thập phân

Sử dụng cùng format `%,12.2f` và cùng số `1234567.5`:

```java
System.out.printf(Locale.US, "|%,12.2f|%n", 1234567.5);
System.out.printf(Locale.GERMANY, "|%,12.2f|%n", 1234567.5);
```

Kết quả:

```text
|1,234,567.50|
|1.234.567,50|
```

Với `Locale.US`, dấu phẩy phân nhóm và dấu chấm ngăn phần thập phân. Với `Locale.GERMANY`, hai vai trò được đảo lại. Do đó, **không thể dựa vào ký tự `,` trong format để khẳng định kết quả luôn chứa dấu phẩy**.

Khi không truyền `Locale`, nhiều API định dạng dùng locale mặc định của môi trường chạy. Điều này có thể khiến cùng mã hiển thị khác nhau trên máy lập trình viên, máy CI và máy người dùng. Khi cần output ổn định (ví dụ snapshot test hoặc dữ liệu xuất có quy ước rõ), truyền `Locale` cụ thể:

```java
String stable = String.format(Locale.US, "%,.2f", 1234.5);
// "1,234.50"
```

Ngược lại, với giao diện dành cho người dùng cuối, lựa chọn `Locale` theo ngôn ngữ và khu vực của người dùng, thay vì cố định `Locale.US` cho mọi người.

Với các nhu cầu nâng cao như quy tắc tiền tệ, số chữ số nhóm khác nhau hay mẫu dấu âm riêng, có thể dùng `NumberFormat` hoặc `DecimalFormat`. Bài này tập trung vào cơ chế căn lề, đệm và phân nhóm bằng formatter string.

## 8. Ví dụ Java 17 chạy độc lập

Lưu toàn bộ nội dung dưới đây trong tệp `StringFormatLayoutDemo.java`:

```java
import java.util.Locale;

public class StringFormatLayoutDemo {
    public static void main(String[] args) {
        Locale us = Locale.US;

        System.out.printf(us, "string right: |%10s|%n", "Java");
        System.out.printf(us, "string left : |%-10s|%n", "Java");
        System.out.printf(us, "number right: |%8d|%n", 42);
        System.out.printf(us, "number left : |%-8d|%n", 42);
        System.out.printf(us, "zero padded : |%08d|%n", 42);
        System.out.printf(us, "sign + zeros: |%+08d|%n", 42);
        System.out.printf(us, "negative    : |%(08d|%n", -42);
        System.out.printf(us, "group       : |%,d|%n", 1234567);
        System.out.printf(us, "group width : |%,12d|%n", 1234567);
        System.out.printf(us, "group zeros : |%0,12d|%n", 1234567);
        System.out.printf(us, "decimal US  : |%,12.2f|%n", 1234567.5);
        System.out.printf(Locale.GERMANY,
                "decimal DE  : |%,12.2f|%n", 1234567.5);
        System.out.printf(us, "precision   : |%-12.5s|%n", "Formatting");
        System.out.printf(us, "long string : |%10s|%n", "VeryLongText");
        System.out.printf(us, "progress    : %d%%%n", 75);
    }
}
```

Biên dịch và chạy:

```bash
javac StringFormatLayoutDemo.java
java StringFormatLayoutDemo
```

Đầu ra chính xác (giữ nguyên khoảng trắng giữa `|`):

```text
string right: |      Java|
string left : |Java      |
number right: |      42|
number left : |42      |
zero padded : |00000042|
sign + zeros: |+0000042|
negative    : |(000042)|
group       : |1,234,567|
group width : |   1,234,567|
group zeros : |0001,234,567|
decimal US  : |1,234,567.50|
decimal DE  : |1.234.567,50|
precision   : |Forma       |
long string : |VeryLongText|
progress    : 75%
```

Ý nghĩa các dòng cần để ý:

- `string right`, `string left` so sánh hai phía nhận khoảng trắng.
- `zero padded`, `sign + zeros` và `negative` cho thấy cách dấu và dấu ngoặc tham gia tính chiều rộng.
- `group width` và `group zeros` minh họa rõ rằng **phân nhóm** và **đệm** là hai thao tác khác nhau.
- `decimal US` và `decimal DE` có cùng format nhưng khác `Locale`.
- `precision` dùng `%-12.5s`: chuỗi `"Formatting"` được hiển thị thành `"Forma"` (5 ký tự), rồi đệm khoảng trắng bên phải đến 12 ký tự.
- `long string` chứng minh `width` không cắt nội dung dài.
- `%%` in một dấu phần trăm thực, còn `%n` dùng để xuống dòng.

## 9. Ví dụ áp dụng: định dạng bảng console

Khi dựng bảng văn bản, đặt từng cột vào vùng có width cố định và chọn kiểu căn thích hợp:

```java
import java.util.Locale;

public class SalesTable {
    public static void main(String[] args) {
        System.out.printf(Locale.US,
                "| %-12s | %8s | %12s |%n",
                "Sản phẩm", "Số lượng", "Doanh thu");
        System.out.printf(Locale.US,
                "| %-12s | %,8d | %,12d |%n",
                "Java", 42, 1_234_567);
        System.out.printf(Locale.US,
                "| %-12s | %,8d | %,12d |%n",
                "Spring", 7, 12_500);
    }
}
```

Đây là một chương trình độc lập khác, lưu tên tệp `SalesTable.java` rồi chạy `javac SalesTable.java` và `java SalesTable`. Kết quả có cùng quy tắc căn lề: cột sản phẩm căn trái, cột số lượng/doanh thu căn phải và phân nhóm. Nếu tên sản phẩm hoặc số lớn vượt width, bảng có thể lệch vì Java không tự cắt nội dung.

Đối với output có tiếng Việt, emoji hoặc ký tự Đông Á, các ô có số ký tự tương đương chưa chắc có **độ rộng hình ảnh trên terminal** tương đương. Formatter kiểm soát số ký tự trong trường định dạng, không phải hệ thống bố trí cột theo độ rộng hiển thị của mọi font/terminal. Nếu cần bảng thật sự thẳng hàng với mọi kiểu Unicode, dùng thư viện dựng bảng hoặc giao diện có xử lý độ rộng ký tự.

## 10. Lỗi phổ biến

### 10.1. Dùng cờ không phù hợp với conversion

Các định dạng sau không phải cách viết đúng cho mục đích thường gặp:

- `%010s`: cờ `0` không dùng để đệm chuỗi. Đối với `%s`, mặc định chỉ có đệm khoảng trắng theo `width`.
- `%,s`: dấu `,` là cờ grouping cho conversion số phù hợp, không thể yêu cầu formatter phân nhóm một chuỗi tùy ý.
- `%.2d`: với số nguyên, hãy dùng `%02d` nếu cần đệm `0` đến width 2.
- `%0d`: có cờ `0` nhưng không có width.
- `%-08d`: trộn căn trái `-` với đệm số không `0`.

Những format sai có thể gây một ngoại lệ thuộc họ `IllegalFormatException` khi chạy, ví dụ `FormatFlagsConversionMismatchException`, `MissingFormatWidthException` hoặc `IllegalFormatPrecisionException`. Nếu format string được ghép động, cần kiểm tra trước hoặc xử lý lỗi phù hợp.

### 10.2. Nhầm chiều rộng với số chữ số

Với `%08d` và số `-42`, dấu trừ cũng chiếm chỗ trong tổng chiều rộng; kết quả sẽ có 8 ký tự, không phải 8 chữ số rồi thêm dấu trừ. Tương tự, dấu phẩy phân nhóm và dấu chấm thập phân **đều chiếm vị trí** trong vùng width.

### 10.3. Dùng dấu phân nhóm như một định dạng dữ liệu máy

`1,234,567` và `1.234.567` phù hợp để **người đọc** theo từng locale, nhưng không phải định dạng số trung lập để truyền giữa các hệ thống. Nếu cần dữ liệu số để máy xử lý, lưu giá trị bằng kiểu số/định dạng trao đổi được quy định rõ, sau đó chỉ phân nhóm trong lớp trình bày.

### 10.4. Nhầm ngôn ngữ hiển thị với căn lề

`Locale` thay đổi cách dùng dấu phân nhóm và dấu thập phân, nhưng không tự chọn nên căn trái hay căn phải. Những điều này thuộc hai nhóm tham số khác nhau: **flags/width** quy định căn và đệm, **Locale** quy định cách hiển thị số.

### 10.5. Đưa chuỗi do người dùng nhập làm format string

Nếu người dùng nhập ký tự `%`, hãy truyền dữ liệu đó làm **đối số**, không coi nó là format:

```java
String userText = "Sale 50%";
String safe = String.format("%s", userText);
```

Nếu dùng `String.format(userText)`, các dấu `%` trong dữ liệu có thể bị hiểu thành ký hiệu điều khiển định dạng và gây lỗi hoặc kết quả không mong muốn. Quy tắc chung: format string do ứng dụng kiểm soát; dữ liệu từ bên ngoài đi vào danh sách đối số.

## 11. Bài tập tự kiểm tra

Hãy dự đoán nội dung chính xác giữa hai ký tự `|`:

| Biểu thức (với `Locale.US` nếu có số) | Kết quả |
| --- | --- |
| `String.format("\|%6s\|", "Hi")` | `\|    Hi\|` |
| `String.format("\|%-6s\|", "Hi")` | `\|Hi    \|` |
| `String.format("\|%05d\|", 7)` | `\|00007\|` |
| `String.format("\|%+05d\|", 7)` | `\|+0007\|` |
| `String.format(Locale.US, "\|%,d\|", 123456)` | `\|123,456\|` |
| `String.format(Locale.US, "\|%,10d\|", 123456)` | `\|   123,456\|` |
| `String.format(Locale.US, "\|%,10.2f\|", 1234.5)` | `\|  1,234.50\|` |

Các dấu `\|` chỉ dùng để biểu diễn ranh giới trong bảng Markdown. Khi viết **mã Java thực tế**, dùng ký tự `|` trực tiếp trong chuỗi Java như `"|%6s|"`; dấu `\` trước `|` ở bảng chỉ để Markdown không tách nhầm cột.

Thử sửa `width` từ 10 thành 4, thay số `123456` thành `123456789`, rồi chạy lại. Quan sát vì sao kết quả có thể vượt width mà không mất chữ số. Tiếp theo, thử đổi `Locale.US` thành `Locale.GERMANY` và kiểm tra dấu phân nhóm đã thay đổi ra sao.

## 12. Ghi nhớ

- `%10s`, `%8d`: **căn phải** trong trường có chiều rộng tối thiểu; mặc định đệm khoảng trắng bên trái.
- `%-10s`, `%-8d`: **căn trái**; đệm khoảng trắng bên phải.
- `%08d`: **đệm số không**, thường dùng cho giá trị số có biểu diễn độ rộng cố định.
- `%,d`: **phân nhóm chữ số**; ký tự phân nhóm thực tế do `Locale` quyết định.
- `%,12d`, `%0,12d`, `%,15.2f`: có thể kết hợp grouping với width, đệm hoặc precision nếu conversion hỗ trợ.
- `width` là **độ rộng tối thiểu, không cắt nội dung**; `precision` có ý nghĩa khác nhau giữa `%s` và `%f`.
- Truyền `Locale` tường minh khi đầu ra cần ổn định. Dùng `%n` để xuống dòng và `%%` để in dấu phần trăm literal.
