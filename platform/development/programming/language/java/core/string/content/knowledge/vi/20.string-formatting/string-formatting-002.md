# Cú pháp chỉ số đối số, cờ, độ rộng, độ chính xác và kiểu chuyển trong Java

Khi dùng `String.format(...)`, `System.out.printf(...)` hoặc `Formatter`, ta mô tả hình thức của dữ liệu bằng **format string**. Một ký hiệu bắt đầu bằng `%` được gọi là *format specifier*: nó chọn đối số, quyết định cách căn lề/điền ký tự, giới hạn độ chính xác và chọn kiểu hiển thị. Hiểu đúng thứ tự các thành phần giúp tạo bảng, thông báo, số tiền, ngày tháng và báo cáo có kết quả nhất quán.

Bài học tập trung vào **cú pháp của một format specifier trong Java 17+**, đặc biệt là chỉ số đối số (`argument index`), cờ (`flags`), độ rộng (`width`), độ chính xác (`precision`), và kiểu chuyển (`conversion`). Các quy tắc này thuộc `java.util.Formatter`; `String.format` và `printf` sử dụng cùng hệ cú pháp.

## 1. Bắt đầu với một chuỗi định dạng

```java
String message = String.format("Hello %s, you have %d messages", "An", 3);
// "Hello An, you have 3 messages"
```

- `Hello `, dấu phẩy và ` you have ` là văn bản giữ nguyên.
- `%s` lấy đối số tương ứng và hiển thị dưới dạng chuỗi.
- `%d` lấy đối số số nguyên và hiển thị dạng thập phân.
- `String.format(...)` **trả về** một `String`; `System.out.printf(...)` **ghi** văn bản ra luồng đầu ra (và trả về `PrintStream`).

Ví dụ `String.format(Locale.US, "%,.2f", 12345.5)` trả về `"12,345.50"`. `Locale.US` được chỉ định chủ động để cố định dấu thập phân và dấu phân nhóm trong kết quả.

## 2. Công thức cú pháp đầy đủ

Với kiểu chuyển thông thường (chuỗi, ký tự, số nguyên và số thực), cú pháp là:

```text
%[argument_index$][flags][width][.precision]conversion
```

Dấu ngoặc vuông trong dòng **mô tả ngữ pháp** chỉ nghĩa là “thành phần tùy chọn”; **không gõ ngoặc vuông** vào format string thật. Những thành phần được viết theo đúng thứ tự sau:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `%` | Bắt đầu một format specifier. | `%s` |
| `argument_index$` | Chọn vị trí đối số, tính từ **1**; có dấu `$`. | `%2$s` |
| `flags` | Các cờ điều khiển căn lề, dấu âm/dương, điền `0`, nhóm số... | `%-10s`, `%+d` |
| `width` | **Độ rộng tối thiểu** của trường đầu ra. | `%10s` |
| `.precision` | Độ chính xác hoặc giới hạn chiều dài, tùy kiểu chuyển; có dấu chấm. | `%.2f`, `%.4s` |
| `conversion` | Chỉ kiểu chuyển và quy tắc biểu diễn. | `s`, `d`, `f`, `x` |

**Đọc biểu thức `%2$-12.4s` từ trái sang phải:**

1. `%`: bắt đầu chỉ thị.
2. `2$`: lấy **đối số thứ hai**.
3. `-`: căn trái.
4. `12`: trường rộng **ít nhất 12** ký tự.
5. `.4`: với `s`, chỉ lấy **tối đa 4** ký tự của nội dung chuỗi.
6. `s`: chuyển đối số thành chuỗi.

Ví dụ `String.format("%2$-12.4s", 99, "Notebook")` tạo văn bản `"Note        "`: bốn ký tự `Note` theo sau bởi tám dấu cách. Nếu bỏ `-`, các dấu cách sẽ nằm **bên trái**.

Lưu ý có **hai nhánh cú pháp đặc biệt**:

- Ngày/giờ: `%[argument_index$][flags][width]tX` hoặc `...TX`, trong đó `t`/`T` được theo sau bởi **ký tự chỉ thành phần thời gian**, ví dụ `%1$tF`, `%1$tY`; không có `.precision`.
- Ký hiệu không nhận đối số: `%%` (một dấu phần trăm thật) và `%n` (ký tự xuống dòng theo nền tảng). Các chỉ thị này không tiêu thụ đối số dữ liệu.

Không phải flag, width hay precision nào cũng hợp lệ với mọi conversion; Java sẽ ném ngoại lệ nếu tổ hợp sai thay vì lặng lẽ bỏ qua.

## 3. Argument index: chọn và dùng lại đối số

### 3.1. Không ghi chỉ số: lấy đối số theo thứ tự

```java
String value = String.format("%s has %d points", "Mai", 42);
// "Mai has 42 points"
```

Trong ví dụ này, `%s` dùng đối số thứ nhất, `%d` dùng đối số thứ hai.

### 3.2. Chỉ số tường minh: `1$`, `2$`...

```java
String value = String.format("%2$d points belong to %1$s", "Mai", 42);
// "42 points belong to Mai"
```

`%2$d` lấy phần tử thứ hai của danh sách đối số và hiển thị số nguyên; `%1$s` lấy phần tử thứ nhất và hiển thị chuỗi. Chỉ số **bắt đầu từ 1**, không từ 0. Có thể tham chiếu một đối số nhiều lần:

```java
String value = String.format("%1$s / %1$S", "java");
// "java / JAVA"
```

`%S` dùng cách chuyển thành chữ hoa (theo locale). Đây là cách dùng cùng đối số hai lần mà vẫn định dạng khác nhau.

### 3.3. Cờ `<`: dùng lại đối số của specifier trước

```java
String value = String.format("%s -> %<S", "java");
// "java -> JAVA"
```

Ở `%<S`, `<` **không phải dấu so sánh**: đó là cờ “dùng lại đối số của specifier ngay trước có đối số”, còn `S` là conversion. Nếu dùng `%<s` mà chưa có đối số trước để tham chiếu, sẽ phát sinh `MissingFormatArgumentException`.

**Quy tắc dễ nhầm:** chỉ số tường minh (`%2$s`) và chỉ số tuần tự mặc định (`%s`) có cách theo dõi riêng; xen kẽ cả hai trong một mẫu dễ gây khó đọc. Ưu tiên dùng toàn bộ chỉ số tường minh khi cần đổi thứ tự, hoặc toàn bộ dạng tuần tự nếu không cần đổi thứ tự. Cờ `<` hữu ích để trình bày **cùng một đối số** theo nhiều cách, nhất là ngày tháng.

## 4. Flags: thay đổi cách hiển thị

Các cờ có thể xuất hiện liên tiếp **sau chỉ số đối số và trước width**. Chúng có ý nghĩa khác nhau tùy conversion.

| Flag | Tác dụng điển hình | Ví dụ và ý nghĩa |
| --- | --- | --- |
| `-` | Căn trái trong trường có width; mặc định thường căn phải. | `%-8s` |
| `+` | Luôn hiển thị dấu số: `+` hoặc `-`. | `%+d`, `%+.2f` |
| ` ` (dấu cách) | Dành vị trí trống trước số dương; với số âm vẫn có dấu trừ. | `% d` |
| `0` | Điền số `0` vào bên trái phần số để đủ width. | `%08d` |
| `,` | Nhóm chữ số theo locale, với các phép chuyển số thích hợp. | `%,d`, `%,.2f` |
| `(` | Bao số âm bằng dấu ngoặc đơn thay cho dấu trừ ở các kiểu số phù hợp. | `%(d`, `%(,.2f` |
| `#` | Dạng biểu diễn thay thế khi conversion hỗ trợ. | `%#x` tạo tiền tố `0x` |
| `<` | Dùng lại đối số trước. | `%s %<S` |

Với `Locale.US`:

```java
String a = String.format(Locale.US, "%08d", -42);      // "-0000042"
String b = String.format(Locale.US, "%+d", 42);        // "+42"
String c = String.format(Locale.US, "%,d", 1234567);  // "1,234,567"
String d = String.format(Locale.US, "%(,.2f", -1234.5);
// "(1,234.50)"
String e = String.format(Locale.US, "%#x", 255);      // "0xff"
```

**Cẩn thận với tổ hợp cờ:** `-` (căn trái) và `0` (đệm số 0) không dùng chung trong các conversion số có áp dụng hai cờ này; `+` và cờ dấu cách cũng xung đột. Với `%s` thông thường, các cờ số như `0` hoặc `,` không phù hợp. Một số flag chỉ áp dụng cho vài conversion: chẳng hạn `,` có thể dùng với `d` và nhiều dạng số thực, nhưng không dùng như cờ phân nhóm cho `x`.

## 5. Width: độ rộng **tối thiểu**

Với `%8s` và nội dung `"AB"`, kết quả có sáu dấu cách rồi đến `AB`. Với `%-8s`, kết quả là `AB` rồi sáu dấu cách:

```java
String right = String.format("|%8s|", "AB");  // "|      AB|"
String left  = String.format("|%-8s|", "AB"); // "|AB      |"
```

Width không làm ngắn một giá trị vốn dài hơn trường:

```java
String value = String.format("|%3s|", "Hello");
// "|Hello|" (không cắt xuống 3 ký tự)
```

**Width là số ký tự của trường kết quả, gồm cả dấu cộng/trừ, tiền tố số và dấu phân cách đã định dạng khi áp dụng.** Khi đệm `0` cho số âm, các chữ số 0 được chèn **sau dấu trừ**: `%08d` với `-42` cho `-0000042`.

Không nhầm `-` đứng trước width là số âm. Trong `%-10s`, dấu `-` là **flag căn trái**, còn `10` vẫn là width dương. Một số flag đòi hỏi width, ví dụ `%-s` không có độ rộng nên không hợp lệ.

## 6. Precision: không giống nhau giữa chuỗi và số

Precision được viết `.N`, với `N` là số nguyên không âm. Nó được áp dụng tùy conversion:

| Conversion | Ý nghĩa của precision | Ví dụ |
| --- | --- | --- |
| `s` / `S` (văn bản thông thường) | Số ký tự **tối đa** được hiển thị trước khi áp dụng width. | `%.3s` với `"abcdef"` → `"abc"` |
| `f` | Số chữ số sau dấu thập phân. | `%.2f` với `12.5` → `"12.50"` |
| `e` / `E` | Số chữ số sau dấu thập phân trong dạng khoa học. | `%.2e` |
| `g` / `G` | Số **chữ số có nghĩa** của trị số sau khi làm tròn. | `%.3g` |
| `d`, `x`, `c`, `tF` | **Không hỗ trợ precision**. | `%.2d` không hợp lệ |

Ví dụ kết hợp width và precision:

```java
String a = String.format(Locale.US, "|%8.3s|", "abcdef");
// "|     abc|" — cắt còn 3 ký tự rồi căn phải trong 8 vị trí

String b = String.format(Locale.US, "|%-8.3s|", "abcdef");
// "|abc     |" — cắt còn 3 ký tự rồi căn trái

String c = String.format(Locale.US, "|%8.2f|", 12.5);
// "|   12.50|" — làm tròn/hiển thị 2 chữ số sau dấu thập phân,
// rồi đệm khoảng trắng đến width 8
```

Với số thực nhị phân (`double`/`float`), kết quả làm tròn ở những giá trị ranh giới có thể chịu ảnh hưởng của cách lưu trữ số thực. Nếu là giá trị tiền tệ cần độ chính xác thập phân chặt chẽ, xem xét `BigDecimal` và quy tắc làm tròn nghiệp vụ; `%.2f` chỉ là cách **hiển thị** chứ không thay đổi dữ liệu gốc.

## 7. Conversion: chọn kiểu dữ liệu đầu ra

| Conversion | Loại giá trị thường dùng | Ví dụ/ý nghĩa |
| --- | --- | --- |
| `s` / `S` | Đối tượng bất kỳ, lấy biểu diễn chuỗi; `S` chuyển thành chữ hoa. | `%s`, `%S` |
| `b` / `B` | Boolean; `null` thành `false`, đối tượng khác `Boolean` nếu không null thành `true`. | `%b` |
| `h` / `H` | Dạng thập lục phân của hash code (không phải địa chỉ bộ nhớ). | `%h` |
| `c` / `C` | Ký tự Unicode hợp lệ (ví dụ `char`; hoặc code point trong `int`). | `%c` |
| `d` | Số nguyên thập phân. | `%d` |
| `o` | Số nguyên bát phân. | `%o` |
| `x` / `X` | Số nguyên thập lục phân, dùng chữ thường/chữ hoa. | `%x` |
| `f` | Số thực dạng thập phân cố định. | `%.2f` |
| `e` / `E` | Số thực dạng khoa học. | `%e` |
| `g` / `G` | Số thực dạng tổng quát theo số chữ số có nghĩa. | `%g` |
| `a` / `A` | Biểu diễn số thực thập lục phân (phù hợp `float`/`double`). | `%a` |
| `tX` / `TX` | Ngày giờ, **X là ký tự thành phần ngày/giờ**, ví dụ `F`, `Y`, `m`, `d`, `H`. | `%tF`, `%1$tY` |
| `%` trong `%%` | Dấu phần trăm thật; không nhận đối số. | `100%%` → `100%` |
| `n` trong `%n` | Xuống dòng theo hệ điều hành; không nhận đối số. | `Line 1%nLine 2` |

**Tương thích kiểu dữ liệu:** `%d` không nhận một `String` có nội dung `"42"` thay cho số nguyên; `%f` dành cho số thực như `double`, `float` và `BigDecimal`; `%c` không nhận một `String` nhiều ký tự thay cho một ký tự. Các phép chuyển không tương thích thường gây `IllegalFormatConversionException`.

Một số định dạng ngày thường dùng (với `LocalDate` hoặc giá trị thời gian tương thích `TemporalAccessor`):

- `%tF`: ngày ISO dạng `yyyy-MM-dd`.
- `%tY`: năm bốn chữ số; `%tm`: tháng hai chữ số; `%td`: ngày trong tháng hai chữ số.
- `%tH`: giờ (00–23); `%tM`: phút, **chỉ dùng với giá trị có trường giờ/phút**, chẳng hạn `LocalDateTime`.

Vì `tF` gồm **hai ký tự conversion** `t` và `F`, không được đọc `F` là một flag hay width. Để tái sử dụng cùng ngày:

```java
LocalDate date = LocalDate.of(2026, 10, 23);
String value = String.format(Locale.US,
        "%1$td/%1$tm/%1$tY", date);
// "23/10/2026"
```

Đây là đoạn minh họa, cần import `java.time.LocalDate` và `java.util.Locale`.

## 8. Ví dụ Java 17+ chạy độc lập

Lưu tệp tên `FormatSyntaxDemo.java` với mã:

```java
import java.time.LocalDate;
import java.util.Locale;

public class FormatSyntaxDemo {
    public static void main(String[] args) {
        String product = "Notebook";
        int quantity = 7;
        double price = 12.5;

        // Chỉ số đối số 1-based và đổi thứ tự.
        System.out.println(String.format(Locale.US,
                "Name: %1$s; qty: %2$d", product, quantity));
        System.out.println(String.format(Locale.US,
                "Reordered: %2$d / %1$s", product, quantity));

        // Căn trái, cắt chuỗi, căn phải, định dạng số thực.
        System.out.println(String.format(Locale.US,
                "|%1$-12.4s|", product));
        System.out.println(String.format(Locale.US,
                "|%1$10.2f|", price));

        // Kết hợp các cờ + và 0 với width, precision, conversion f.
        System.out.println(String.format(Locale.US,
                "%1$+010.2f", price));

        System.out.println(String.format(Locale.US,
                "%,d", 1234567));
        System.out.println(String.format(Locale.US,
                "%#x", 255));

        // < lặp lại đối số của specifier trước; S viết chữ hoa.
        System.out.println(String.format(Locale.US,
                "%1$s -> %<S", "java"));

        System.out.println(String.format(Locale.US,
                "%b", (Object) null));

        // Date/time conversion tF; không có precision.
        System.out.println(String.format(Locale.US,
                "%tF", LocalDate.of(2026, 10, 23)));

        // %% là phần trăm thực; %n là xuống dòng theo hệ thống.
        System.out.print(String.format(Locale.US,
                "100%% done%n"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FormatSyntaxDemo.java
java FormatSyntaxDemo
```

Đầu ra chính xác của chương trình:

```text
Name: Notebook; qty: 7
Reordered: 7 / Notebook
|Note        |
|     12.50|
+000012.50
1,234,567
0xff
java -> JAVA
false
2026-10-23
100% done
```

Những điểm cần quan sát: `%1$-12.4s` chọn đối số một, cắt `Notebook` còn `Note` rồi điền tám khoảng trắng bên phải để có width 12; `%1$10.2f` hiển thị `12.50` và thêm năm khoảng trắng bên trái; `%1$+010.2f` hiển thị dấu `+`, điền số 0 sau dấu và đạt tổng độ rộng 10. Các dấu cách bên trong cặp `|...|` ở stdout là một phần của kết quả, không phải lỗi trình bày.

## 9. Locale, các API liên quan và việc thoát ký tự

### 9.1. Locale quyết định một phần định dạng

```java
double value = 12345.5;
String us = String.format(Locale.US, "%,.2f", value);
// "12,345.50"
String de = String.format(Locale.GERMANY, "%,.2f", value);
// "12.345,50"
```

Khi không truyền `Locale`, định dạng dùng locale mặc định phục vụ việc format của môi trường chạy. Kết quả có thể khác nhau giữa máy phát triển và máy triển khai. Nếu đầu ra là dữ liệu giao tiếp giữa các hệ thống hoặc bài kiểm tra cần stdout xác định, truyền locale tường minh như `Locale.US`. Với giao diện người dùng, chọn locale theo ngôn ngữ/khu vực thích hợp.

### 9.2. `String.format`, `formatted`, `printf` và `Formatter`

- `String.format(Locale.US, "%d", 7)` tạo chuỗi `"7"`.
- `"%d".formatted(7)` cũng tạo chuỗi `"7"` (API có từ Java 15, dùng được ở Java 17+).
- `System.out.printf("%d%n", 7)` ghi trực tiếp ra màn hình.
- `Formatter` cho phép định dạng vào một `Appendable`, chẳng hạn `StringBuilder`, khi cần kiểm soát nơi nhận kết quả.

Cú pháp các specifier về cơ bản chung giữa các API trên; khác biệt chính là phương thức trả về giá trị chuỗi hay ghi ra đích.

### 9.3. Phân biệt dấu phần trăm trong format và dữ liệu

Trong chính **format string**, muốn in dấu phần trăm thật phải viết `%%`. Nhưng khi dữ liệu `"50%"` được truyền như đối số cho `%s`, **không phải nhân đôi** dấu phần trăm bên trong dữ liệu:

```java
String result = String.format("Progress: %s", "50%");
// "Progress: 50%"

String another = String.format("Progress: 50%%");
// "Progress: 50%"
```

Không lấy văn bản do người dùng cung cấp trực tiếp làm **format string** khi mục đích chỉ là hiển thị nguyên văn, vì ký hiệu `%` trong đó có thể bị phân tích như format specifier. Hãy dùng mẫu cố định như `"%s"` và truyền văn bản đó thành đối số.

## 10. Lỗi phổ biến và cách chẩn đoán

| Mẫu sai hoặc tình huống | Hậu quả thường gặp | Cách xử lý |
| --- | --- | --- |
| `String.format("%d", "42")` | `IllegalFormatConversionException`: chuỗi không phải số nguyên. | Parse sang số nếu phù hợp, hoặc dùng `%s` để hiển thị chuỗi. |
| `String.format("%.2d", 42)` | `IllegalFormatPrecisionException`: số nguyên `d` không hỗ trợ precision. | Dùng width/flag số như `%04d` nếu cần điền 0. |
| `String.format("%-s", "A")` | `MissingFormatWidthException`: `-` đòi hỏi width. | Dùng `%-8s` chẳng hạn. |
| `String.format("%2$s", "A")` | `MissingFormatArgumentException`: không có đối số thứ hai. | Kiểm tra vị trí theo chỉ số bắt đầu từ 1. |
| `String.format("%<s", "A")` | `MissingFormatArgumentException`: chưa có đối số trước để dùng lại. | Đặt một specifier có đối số trước `%<s`. |
| `String.format("%q", "A")` | `UnknownFormatConversionException`: `q` không phải conversion hợp lệ. | Chọn conversion trong bảng hỗ trợ. |
| Trộn `%s` và `%2$s` tùy tiện | Kết quả có thể khác thứ tự dự đoán. | Chọn một cách đánh chỉ số rõ ràng, kiểm tra thứ tự đối số. |
| Cho rằng `%8.3s` có nghĩa “lấy 8 ký tự, đệm 3” | Đọc sai width/precision. | Với `s`: lấy tối đa 3 ký tự, rồi đệm đến width tối thiểu 8. |
| Cho rằng `%n` là chữ `n` hoặc luôn bằng `\n` | Nhầm về ký tự xuống dòng phụ thuộc nền tảng. | Dùng `%n` cho đầu ra định dạng theo hệ thống; `\n` khi thật sự yêu cầu LF. |

Trong thực tế, các ngoại lệ trên thuộc họ `IllegalFormatException` và thường chỉ xuất hiện khi format string được phân tích lúc chạy. Tránh xây format string động nếu có thể; nếu phải làm vậy, kiểm tra đầu vào và thử các đường chạy đại diện.

## 11. Quy trình đọc bất kỳ specifier nào

Gặp một biểu thức như `%3$-14.5S`, hãy trả lời lần lượt:

1. **Đối số nào?** `3$` lấy đối số thứ ba.
2. **Có flags gì?** `-` yêu cầu căn trái.
3. **Width bao nhiêu?** `14` là mức rộng tối thiểu.
4. **Precision là gì với conversion này?** `.5` với `S` là tối đa năm ký tự.
5. **Conversion gì?** `S` chuyển chuỗi sang chữ hoa theo locale.

Khi gặp `%1$+010.2f`, câu trả lời sẽ là: đối số thứ nhất, luôn ghi dấu, điền 0, rộng tối thiểu 10 ký tự, hai chữ số sau dấu thập phân, kiểu số thực `f`. Khi gặp `%1$tF`, đọc thành: đối số thứ nhất, kiểu ngày giờ `t` với hậu tố `F`, **không có precision**.

## 12. Tự luyện tập

Cho đối số `"abcdef"`, giá trị `7` và số thực `12.5`, dự đoán:

```java
String a = String.format("|%1$8.3s|", "abcdef");
String b = String.format(Locale.US, "%1$04d", 7);
String c = String.format(Locale.US, "%1$+.1f", 12.5);
String d = String.format("%2$s-%1$s", "first", "second");
```

Đáp án: `a` là `"|     abc|"` (năm dấu cách trước `abc`), `b` là `"0007"`, `c` là `"+12.5"`, còn `d` là `"second-first"`.

**Điểm cần nhớ:** đọc specifier theo thứ tự **chỉ số → flags → width → precision → conversion**, đồng thời kiểm tra xem conversion có hỗ trợ những thành phần đã yêu cầu hay không. Với ngày giờ, xử lý thêm ký tự theo sau `t`/`T`; với `%%` và `%n`, không lấy đối số.

Tài liệu tham khảo chính thức: [`java.util.Formatter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html).
