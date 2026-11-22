# Các cờ định dạng số và chuỗi

## 1. Cờ điều chỉnh cách biểu diễn, không đổi giá trị gốc

Một số nguyên `42` có thể được trình bày là `42`, `+42`, `00042` hoặc một ô căn lề có khoảng trắng. Giá trị số không thay đổi; chỉ cách biểu diễn thay đổi.

Trong cú pháp Formatter, cờ (flag) là những ký tự điều chỉnh một phép chuyển đổi:

```text
%[argument_index$][flags][width][.precision]conversion
```

Ví dụ:

```text
%+08.2f
 │││ │└─ f: dạng thập phân cố định
 │││ └── .2: hai chữ số sau dấu thập phân
 ││└──── 8: độ rộng tối thiểu của toàn kết quả
 │└───── 0: đệm số không
 └────── +: hiện dấu cho cả số không âm
```

Các cờ không hoạt động độc lập với loại chuyển đổi. Một cờ hợp lệ cho số thập phân có thể không hợp lệ cho chuỗi hoặc số hệ mười sáu.

Bài áp dụng cho Formatter và những API dùng cùng quy tắc như String.format và printf. Các cơ chế này vẫn phù hợp trong Java hiện đại; chương trình minh chứng chạy trên Java 17 trở lên.

## 2. Phân biệt cờ, độ rộng, độ chính xác và chuyển đổi

Trước khi học từng cờ, cần tránh gộp mọi thành phần sau dấu phần trăm thành một khái niệm.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Cờ | `-`, `+`, `0`, `,` | Điều chỉnh cách trình bày |
| Độ rộng | `8` trong `%8s` | Số ký tự tối thiểu của trường kết quả |
| Độ chính xác | `.2` trong `%.2f` | Có ý nghĩa riêng theo loại chuyển đổi |
| Chuyển đổi | `s`, `d`, `f`, `x` | Chọn cách diễn giải và biểu diễn đối số |
| Chỉ số đối số | `2$` trong `%2$s` | Chọn đối số cụ thể |

Chữ hoa trong `%S`, `%X` không phải một cờ viết hoa. Nó là biến thể chuyển đổi tương ứng, có quy tắc tạo kết quả chữ hoa.

Độ rộng không cắt ngắn nội dung. Nếu `%5d` nhận số có bảy chữ số, kết quả vẫn cần cả bảy chữ số. Với chuỗi thông thường, giới hạn độ chính xác như `%.3s` mới có thể giới hạn phần nội dung.

Đừng dùng độ rộng của Formatter như số ô hiển thị tuyệt đối trên mọi thiết bị đầu cuối. Ký tự Unicode, dấu kết hợp và độ rộng hiển thị của từng hệ chữ có thể làm cột nhìn không đều dù cách đệm đã đúng theo API. Các ví dụ căn lề dưới đây dùng ASCII để khoảng trắng có thể đối chiếu rõ.

## 3. Căn lề chuỗi với dấu trừ

Mặc định, khi có độ rộng lớn hơn kết quả, Formatter đệm khoảng trắng bên trái:

```java
String.format(Locale.ROOT, "|%8s|", "Java");
```

Kết quả có bốn dấu cách trước Java:

```text
|    Java|
```

Cờ `-` chuyển sang căn trái:

```java
String.format(Locale.ROOT, "|%-8s|", "Java");
```

Kết quả:

```text
|Java    |
```

Cờ này cần đi cùng độ rộng; `%-s` không nói được độ rộng để căn nên bị từ chối.

Có thể kết hợp giới hạn phần chuỗi rồi căn lề:

```java
String.format(Locale.ROOT, "|%-8.3s|", "Java");
```

Kết quả:

```text
|Jav     |
```

Phần chuỗi được giới hạn thành `Jav` trước, sau đó thêm năm khoảng trắng để đủ độ rộng tám. Độ chính xác `.3` không phải cờ; nó phối hợp với cờ căn trái.

Đối với String thông thường, không dùng `0`, `+`, dấu cách, `,` hoặc `(` như các cờ của `%s`. Nếu cần đệm ký tự riêng cho một mã văn bản, hãy thiết kế thao tác đó rõ ràng thay vì giả định `%08s` sẽ đệm số không.

## 4. Dấu của số: cộng, khoảng trắng và ngoặc

### Cờ cộng: hiện dấu dương

`%+d` với `42` tạo `+42`; với `-42` vẫn có dấu âm. Nó hữu ích khi cần thấy rõ chiều biến động, ví dụ mức tăng/giảm.

Khi thêm độ rộng:

```text
%+7d, giá trị 42 → |    +42|
```

Dấu cũng được tính vào toàn bộ trường rộng bảy ký tự.

### Cờ khoảng trắng: dành chỗ cho dấu âm

Một khoảng trắng trong vị trí cờ làm số không âm có một dấu cách dẫn đầu thay cho dấu cộng:

```text
% d, giá trị 42  → | 42|
% d, giá trị -42 → |-42|
```

Nó hỗ trợ căn dãy số dương/âm mà không muốn hiện dấu cộng. Kết hợp với độ rộng có thể tạo nhiều dấu cách do cả phần dấu lẫn phần đệm trường:

```text
% 7d, giá trị 42 → |     42|
```

Không dùng đồng thời `+` và cờ khoảng trắng: hai cờ cùng yêu cầu cách thể hiện khác nhau cho số không âm, nên tổ hợp bị từ chối.

### Cờ ngoặc mở: biểu diễn số âm trong ngoặc

Với một chuyển đổi hỗ trợ cờ này, `(` yêu cầu số âm được biểu diễn trong cặp ngoặc thay cho dấu trừ.

```text
%(d, giá trị -42 → |(42)|
```

Chỉ cần viết ký tự ngoặc mở trong vùng cờ; Formatter tự tạo cả hai ngoặc ở kết quả. Không thêm ngoặc đóng vào vùng cờ.

Các cờ dấu phải phù hợp với kiểu số và chuyển đổi. Trong những ví dụ số nguyên cơ bản của bài, chúng dùng với `d`; không bê nguyên tổ hợp sang `x` hoặc `o` cho các kiểu nguyên thủy. BigInteger có một số quy tắc dấu khác, nên phải tra theo cả kiểu đối số thay vì chỉ tên chuyển đổi.

## 5. Cờ số không và vị trí của dấu, tiền tố

Cờ `0` đệm số không để đạt độ rộng tối thiểu:

```text
%07d, giá trị -42 → |-000042|
```

Các số không được đặt sau dấu âm, không phải trước dấu:

```text
Đúng: -000042
Không phải: 0000-42
```

Toàn bộ kết quả vẫn có bảy ký tự. Cờ `0` cần độ rộng; `%0d` không đủ thông tin và bị từ chối.

Không dùng đồng thời `-` và `0`. Một cờ muốn căn trái với khoảng trắng ở cuối, cờ kia muốn đệm số không ở đầu. Ví dụ `%-05d` ném `IllegalFormatFlagsException`.

Đệm số không phù hợp khi biểu diễn mã số hoặc trường số có độ rộng tối thiểu. Nếu số dài hơn độ rộng, nó không bị cắt bớt.

Với dạng có tiền tố hệ số, số không cũng được chèn theo quy tắc của dạng biểu diễn đó:

```text
%#08x, giá trị 42 → |0x00002a|
```

Tiền tố `0x` nằm trước phần đệm, không bị đẩy ra sau những số không.

## 6. Dấu phẩy: yêu cầu phân nhóm theo locale

Cờ `,` yêu cầu sử dụng phân nhóm cho những chuyển đổi hỗ trợ nó.

Ví dụ với Locale.ROOT:

```text
%,d, giá trị 1234567 → |1,234,567|
```

Ký tự dấu phẩy trong mẫu là ký hiệu yêu cầu phân nhóm; dấu phân cách thực tế phụ thuộc locale. Không được kết luận rằng nó luôn tạo dấu phẩy cho mọi người dùng.

Cờ phân nhóm có thể phối hợp với ngoặc và độ rộng:

```text
%(,12d, giá trị -1234567 → | (1,234,567)|
```

Có một khoảng trắng đầu trường vì phần `(1,234,567)` dài mười một ký tự, nhỏ hơn độ rộng mười hai.

Với một số thập phân:

```text
%(,12.2f, giá trị -1234.50 → |  (1,234.50)|
```

Ví dụ dùng BigDecimal và locale cố định. Cờ nhóm không quyết định đơn vị tiền hay quy tắc tính tiền. Phần `.2` là độ chính xác của dạng f, không phải “hai chữ số cho mọi kiểu số”.

`,` được hỗ trợ trong các dạng như `d`, `f`, `g`; không phải mọi dạng số. Chẳng hạn `%,x` không hợp lệ. Khi dùng chuyển đổi khác, kiểm tra bảng tương thích của Formatter thay vì thêm cờ theo trực giác.

## 7. Dấu thăng: dạng biểu diễn thay thế

Cờ `#` không có một ý nghĩa chung cho tất cả chuyển đổi. Ví dụ:

| Chuyển đổi | Tác dụng điển hình của # |
| --- | --- |
| `o` | Bổ sung tiền tố dạng bát phân |
| `x`, `X` | Bổ sung tiền tố `0x` hoặc `0X` |
| `f`, `e` | Giữ dấu thập phân ngay cả khi độ chính xác bằng không |
| `s` với đối tượng Formattable | Chuyển yêu cầu dạng thay thế cho mã tùy biến của đối tượng |

Với `10`, `%#o` tạo `012`. Đây là cách biểu diễn bát phân có tiền tố, không phải phép chuyển đổi biến dữ liệu gốc thành một loại số khác.

Với `12.0`, `%#.0f` giữ dấu thập phân nên tạo `12.` ở Locale.ROOT. Không có `#`, dạng `%.0f` tạo `12` cho giá trị đó.

Đối với String thông thường, `%#s` là lỗi. Nó không tự thêm dấu nháy hay tạo chuỗi “đẹp hơn”. Chỉ khi đối tượng thực hiện Formattable, cờ dạng thay thế mới có nghĩa theo phần cài đặt formatTo của đối tượng.

Không mặc định `#` hợp lệ với `d` hoặc `g`. Cùng là số nhưng mỗi chuyển đổi có tập cờ riêng. Bài không triển khai Formattable; điểm cần biết ở đây là tính tương thích phụ thuộc cả chuyển đổi lẫn kiểu đối số.

## 8. Cờ dùng lại đối số và chuyển đổi chữ hoa

Ký tự `<` trong vùng cờ cho phép dùng lại đối số đã được chỉ dẫn định dạng trước đó sử dụng:

```java
String.format(Locale.ROOT, "%d / %<x", 255);
```

Kết quả:

```text
255 / ff
```

Cùng một số được biểu diễn thập phân rồi hệ mười sáu. `<` chọn lại đối số, không có nghĩa căn trái; căn trái dùng `-`.

Nếu không có đối số trước để dùng lại, mẫu không hợp lệ cho mục đích đó. Đừng trộn việc chọn đối số với việc trang trí kết quả khi đọc một mẫu phức tạp.

`%S` là chuyển đổi chữ hoa tương ứng với `s`. Với `"Java"` và Locale.ROOT, kết quả là `JAVA`. Đây là thay đổi ký tự chuyển đổi, không phải cờ. Chữ hoa theo locale có thể có quy tắc ngôn ngữ riêng; kết quả không nên được dùng thay một giao thức chuẩn hóa định danh nếu giao thức đó có quy tắc khác.

## 9. Ví dụ chạy được: nhìn thấy khoảng trắng và lỗi tổ hợp

Chương trình bao quanh mỗi kết quả bằng hai vạch đứng để thấy vị trí đệm. Phần sau kiểm chứng các tổ hợp sai bằng tên lớp ngoại lệ.

Lưu thành `FormatFlagsDemo.java`:

```java
import java.math.BigDecimal;
import java.util.IllegalFormatException;
import java.util.Locale;

public class FormatFlagsDemo {
    private static void show(String label, String pattern, Object... values) {
        String result = String.format(Locale.ROOT, pattern, values);
        System.out.println(label + "=|" + result + "|");
    }

    private static void error(String pattern, Object value) {
        try {
            String.format(Locale.ROOT, pattern, value);
            throw new AssertionError("Expected a format error");
        } catch (IllegalFormatException e) {
            System.out.println(pattern + " -> "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("right", "%8s", "Java");
        show("left", "%-8s", "Java");
        show("short", "%-8.3s", "Java");
        show("positive", "%+7d", 42);
        show("space", "% 7d", 42);
        show("zero", "%07d", -42);
        show("group", "%,d", 1234567);
        show("negative", "%(,12d", -1234567);
        show("hex", "%#08x", 42);
        show("octal", "%#o", 10);
        show("decimal", "%# .0f", 12.0);
        show("money", "%(,12.2f", new BigDecimal("-1234.50"));
        show("reuse", "%d / %<x", 255);
        show("upper", "%S", "Java");

        error("%-s", "Java");
        error("%-05d", 12);
        error("%+ d", 12);
        error("%,x", 12);
        error("%#s", "Java");
        error("%.2d", 12);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 FormatFlagsDemo.java
java FormatFlagsDemo
```

Stdout theo các dòng:

```text
right=|    Java|
left=|Java    |
short=|Jav     |
positive=|    +42|
space=|     42|
zero=|-000042|
group=|1,234,567|
negative=| (1,234,567)|
hex=|0x00002a|
octal=|012|
decimal=| 12.|
money=|  (1,234.50)|
reuse=|255 / ff|
upper=|JAVA|
%-s -> MissingFormatWidthException
%-05d -> IllegalFormatFlagsException
%+ d -> IllegalFormatFlagsException
%,x -> FormatFlagsConversionMismatchException
%#s -> FormatFlagsConversionMismatchException
%.2d -> IllegalFormatPrecisionException
```

Dòng `decimal` dùng cả cờ khoảng trắng lẫn `#`, nên có dấu cách trước `12.`.

Phần kiểm chứng lỗi dùng một lỗi chính cho từng mẫu để kết quả dễ hiểu. Nếu một mẫu cùng chứa nhiều lỗi khác nhau, không nên xây logic ứng dụng dựa vào việc một lỗi cụ thể phải được phát hiện trước tất cả lỗi còn lại.

## 10. Cách đọc và sửa mẫu bị lỗi

Đừng thêm hoặc xóa ký tự ngẫu nhiên cho đến khi mẫu “chạy được”. Hãy phân tích theo thứ tự:

1. Chuyển đổi là gì, ví dụ s, d hay f?
2. Đối số thực tế có kiểu nào?
3. Từng cờ có hợp lệ cho chuyển đổi và kiểu đó không?
4. Cờ cần độ rộng đã có độ rộng chưa?
5. Các cờ có xung đột không?
6. Độ chính xác có được phép và mang nghĩa gì?
7. Locale có phù hợp kết quả mong muốn không?

Các trường hợp trong chương trình cho thấy những loại lỗi khác nhau:

- `%-s`: thiếu độ rộng cần cho căn trái.
- `%-05d`: hai cờ xung đột.
- `%+ d`: xung đột cách hiện dấu số không âm.
- `%,x`: cờ không hợp với chuyển đổi.
- `%#s` với String: dạng thay thế không được hỗ trợ cho đối số này.
- `%.2d`: độ chính xác không hợp lệ cho dạng số nguyên d.

Java không bắt buộc phát hiện những lỗi này lúc biên dịch vì mẫu và đối số có thể được tạo động. Cần kiểm thử bằng dữ liệu dương, âm, bằng không, dài hơn độ rộng và locale đại diện.

Khi viết kiểm thử khoảng trắng, dùng chuỗi kỳ vọng chính xác hoặc biểu diễn có dấu bao như ví dụ. Đừng gọi trim trước khi so sánh nếu mục tiêu là kiểm tra căn lề; trim sẽ che chính lỗi cần phát hiện.

## 11. Một vài giới hạn khi áp dụng

Cờ chỉ định cách hiển thị. Chúng không tự kiểm tra miền nghiệp vụ, không ngăn tràn số trong phép tính trước đó và không làm một số tiền đúng về mặt kế toán.

Độ chính xác f làm tròn cách biểu diễn; nếu cần quy tắc làm tròn nghiệp vụ cụ thể, thực hiện quy tắc trên dữ liệu bằng công cụ thích hợp trước khi hiển thị. Không suy luận rằng thay mẫu sẽ sửa dữ liệu tính sai.

Đối với các giá trị đặc biệt như NaN, vô cực hoặc null, một số cờ có cách xử lý riêng. Các ví dụ trong bài dùng giá trị hữu hạn, khác null để tập trung vào tương tác cờ. Nếu miền dữ liệu có các giá trị đặc biệt, bổ sung ca kiểm thử theo hợp đồng của chuyển đổi.

Mẫu cũng không phải cơ chế thoát dữ liệu cho HTML, JSON hoặc SQL. Cờ `#` không làm chuỗi an toàn để chèn vào các ngữ cảnh đó.

Tránh nhận một mẫu tùy ý từ đầu vào không tin cậy nếu ứng dụng chỉ muốn hiển thị dữ liệu. Dùng mẫu do chương trình kiểm soát và truyền dữ liệu ở vị trí đối số. Độ rộng quá lớn do đầu vào điều khiển còn có thể tạo kết quả rất lớn, nên các cấu hình mẫu động cần giới hạn hợp lý.

## 12. Tự kiểm tra

1. Trong `%-10.4s`, ký tự nào là cờ và số nào là độ rộng?
2. `%5d` có cắt số bảy chữ số xuống năm chữ số không?
3. Vì sao `%-08d` không phải cách tạo số căn trái rồi đệm số không?
4. `,` trong mẫu có luôn tạo dấu phẩy ở kết quả không?
5. `%#s` có hoạt động với String thông thường không?
6. `<` có phải cờ căn trái không?

Đáp án:

1. `-` là cờ; `10` là độ rộng; `.4` là độ chính xác.
2. Không; độ rộng là tối thiểu.
3. Cờ căn trái và cờ đệm số không xung đột.
4. Không; ký hiệu thực tế phụ thuộc locale.
5. Không; dạng này cần đối tượng hỗ trợ Formattable.
6. Không; nó dùng lại đối số trước đó.

Một mẫu dễ kiểm chứng là mẫu mà người đọc tách được chuyển đổi, cờ, độ rộng và độ chính xác, rồi giải thích được tác dụng của từng phần đối với kiểu dữ liệu thực tế.

## Tài liệu đối chiếu

- [Formatter — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): cú pháp, bảng cờ và quy tắc từng chuyển đổi.
- [Formattable — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formattable.html): việc tùy biến s và cờ dạng thay thế.
