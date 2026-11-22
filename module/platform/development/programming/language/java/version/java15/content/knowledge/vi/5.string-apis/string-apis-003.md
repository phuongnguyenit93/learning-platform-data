# Độ rộng, độ chính xác và ký hiệu phần trăm trong Java String formatting

## 1. Bài học giải quyết vấn đề gì?

Trong Java, nhiều chuỗi có thể được tạo từ một **mẫu định dạng** (*format string*) với các vị trí thay thế dữ liệu: tên, số nguyên, số thập phân, tỷ lệ phần trăm, v.v. Ba thành phần rất hay bị nhầm là:

- **Độ rộng (*width*)**: số ký tự **tối thiểu** dành cho một giá trị sau khi định dạng, giúp căn cột hoặc thêm phần đệm.
- **Độ chính xác (*precision*)**: ý nghĩa thay đổi theo loại dữ liệu; với `%s` thường giới hạn số ký tự, với `%f` quy định số chữ số sau dấu thập phân.
- **Ký hiệu phần trăm**: `%%` trong format string để hiển thị một dấu `%` thật, không lấy thêm đối số.

Chủ đề thuộc API xử lý chuỗi vẫn được Java hỗ trợ đầy đủ. Java 15 bổ sung phương thức instance `String.formatted(Object... args)`; `String.format(...)`, `System.out.printf(...)` và `java.util.Formatter` cũng là API hiện hành, tiếp tục được dùng trên Java 17+ và các bản Java mới hơn.

## 2. Chọn API định dạng chuỗi

Ba cách dùng phổ biến:

```java
String a = "Hello, %s!".formatted("Java");
String b = String.format("Hello, %s!", "Java");
System.out.printf("Hello, %s!%n", "Java");
```

- `a` và `b` đều là `"Hello, Java!"`. `String.formatted(...)` có ý nghĩa tương đương `String.format(this, args)` và có từ **Java 15**.
- `System.out.printf(...)` định dạng rồi ghi ra luồng output, trong khi hai cách đầu trả về một `String`. `%n` ở đây tạo dấu xuống dòng theo nền tảng.
- `String.format(Locale.US, format, args...)` cho phép chọn `Locale` rõ ràng, rất hữu ích khi output số cần dấu chấm thập phân cố định. `String.formatted(...)` sử dụng locale định dạng mặc định của ứng dụng.

Ví dụ cùng một mẫu văn bản nhiều dòng:

```java
String template = """
        Name: %-10s
        Score: %6.2f%%
        """;

String report = String.format(java.util.Locale.US, template, "Mai", 87.5);
```

Text block làm mẫu nhiều dòng dễ đọc; chính các **format specifier** quyết định căn lề, số chữ số và dấu phần trăm trong chuỗi kết quả. Phương thức `formatted` cũng áp dụng trực tiếp cho text block khi không cần truyền `Locale` cụ thể.

## 3. Cú pháp của một format specifier

Dạng tổng quát cho các chuyển đổi phổ biến:

```text
%[argument_index$][flags][width][.precision]conversion
```

Dấu ngoặc vuông trong dòng trên **chỉ ký hiệu thành phần tùy chọn**, không phải ký tự phải gõ. Các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `%` | Bắt đầu định dạng | `%s` |
| `argument_index$` | Chọn đối số theo vị trí, bắt đầu từ 1 | `%2$s` |
| `flags` | Căn trái, thêm số 0, hiện dấu cộng... tùy conversion | `%-8s`, `%08.2f` |
| `width` | Độ rộng đầu ra tối thiểu | `%8s`, `%6d` |
| `.precision` | Độ chính xác, phụ thuộc conversion | `%.3s`, `%.2f` |
| `conversion` | Kiểu chuyển đổi | `s`, `d`, `f`, `g`, `%` |

Một số conversion cần biết để hiểu bài:

- `%s`: biểu diễn chuỗi/đối tượng; dùng width và precision.
- `%d`: số nguyên hệ thập phân; dùng width, **không hỗ trợ precision**.
- `%f`: số dấu phẩy động ở dạng thập phân; width và precision đều được hỗ trợ.
- `%e`: ký pháp khoa học; precision là số chữ số sau dấu thập phân.
- `%g`: cách biểu diễn số thực tổng quát; precision tính theo số chữ số có nghĩa.
- `%%`: chèn một ký hiệu `%` thật, không tiêu thụ đối số.
- `%n`: chèn dấu kết thúc dòng của nền tảng, không tiêu thụ đối số.

Ví dụ `%8.2f` có nghĩa: bắt đầu một specifier, **ít nhất 8 ký tự đầu ra**, giữ **2 chữ số sau dấu thập phân**, áp dụng cho **số thực**.

## 4. Width: độ rộng tối thiểu, không phải độ dài tối đa

`width` quy định đầu ra phải có ít nhất bao nhiêu ký tự. Nếu giá trị đã dài hơn width, Java **không cắt bớt**.

```java
String a = "|%8s|".formatted("Java");       // "|    Java|"
String b = "|%8s|".formatted("JavaLanguage"); // "|JavaLanguage|"
```

Giá trị `Java` có 4 ký tự, nên `%8s` thêm 4 dấu cách **ở bên trái**. `JavaLanguage` dài hơn 8 nên được giữ nguyên toàn bộ; cột có thể rộng hơn dự kiến.

### 4.1. Căn phải và căn trái

```java
String right = "|%8s|".formatted("Java");  // "|    Java|"
String left  = "|%-8s|".formatted("Java"); // "|Java    |"
```

Không có cờ `-`: thông thường phần đệm được đặt ở **bên trái** (căn phải). Có cờ `-`: phần đệm ở **bên phải** (căn trái). Dấu `-` trong `%-8s` là **cờ căn trái**, không phải độ rộng âm.

### 4.2. Đệm bằng số 0 cho giá trị số

```java
String n = String.format(java.util.Locale.US, "|%08.2f|", 12.345);
// "|00012.35|"
```

Cờ `0` dùng cho những chuyển đổi số phù hợp, giúp thêm số 0 thay cho dấu cách ở phía trước theo quy tắc định dạng số. Độ rộng 8 bao gồm cả phần nguyên, dấu thập phân và 2 chữ số phần lẻ. Cần phân biệt `0` với `-`: không tự kết hợp các cờ không tương thích.

### 4.3. Width có giới hạn gì?

- Width phải là số nguyên dương nếu được chỉ định.
- Width là **tối thiểu**, không bảo đảm các cột luôn bằng nhau nếu dữ liệu dài hơn.
- Width được tính theo đầu ra của Formatter; nó không bảo đảm số ô hiển thị bằng nhau trên mọi terminal/font, đặc biệt với ký tự Unicode rộng hoặc dấu kết hợp.
- Với `%n` không được chỉ định width.

## 5. Precision: ý nghĩa tùy theo conversion

### 5.1. Với `%s`: tối đa bao nhiêu ký tự

```java
String a = "%.3s".formatted("Java 15");  // "Jav"
String b = "%8.3s".formatted("Java 15"); // "     Jav"
```

`%.3s` chỉ lấy nhiều nhất 3 ký tự cho phần biểu diễn chuỗi. `%8.3s` xử lý **precision trước** để có `"Jav"`, sau đó áp dụng width 8 nên thêm 5 dấu cách bên trái.

Vì vậy:

- `%8s` là độ rộng tối thiểu 8, **không cắt** chuỗi dài.
- `%.3s` giới hạn phần chuỗi xuất ra ở 3 ký tự.
- `%8.3s` vừa giới hạn 3 ký tự, vừa thêm đệm để đủ ít nhất 8 ký tự.

Precision bằng 0, ví dụ `%.0s`, có thể tạo phần chuỗi rỗng; width nếu có vẫn được áp dụng.

### 5.2. Với `%f`: chữ số sau dấu thập phân

```java
String a = String.format(java.util.Locale.US, "%.2f", 12.345);
// "12.35"

String b = String.format(java.util.Locale.US, "%8.2f", 12.345);
// "   12.35"

String c = String.format(java.util.Locale.US, "%.0f", 12.5);
// "13"
```

`%.2f` tạo 2 chữ số phần lẻ và làm tròn theo quy tắc Formatter. `%8.2f` cho kết quả `12.35` dài 5 ký tự rồi đệm thêm 3 dấu cách bên trái. `%.0f` không in chữ số thập phân.

Không nhầm **làm tròn để hiển thị** với việc thay đổi giá trị gốc của biến. Đặc biệt với phép tính tài chính cần độ chính xác thập phân, nên cân nhắc `BigDecimal` và chính sách làm tròn rõ ràng; format chỉ là bước trình bày kết quả.

### 5.3. Không phải conversion nào cũng hỗ trợ precision

```java
String ok = String.format("%5d", 7);  // "    7"
```

Nhưng ví dụ dưới đây **ném `IllegalFormatPrecisionException`** khi chạy:

```java
// Sai: %d không hỗ trợ .precision
String wrong = String.format("%.2d", 7);
```

Tương tự, `%.2%` là không hợp lệ vì conversion percent không chấp nhận precision. Precision không dùng cho nhóm ký tự, số nguyên, ngày/giờ, percent hoặc line separator trong Formatter. Với những conversion này, hãy đọc đúng quy tắc riêng thay vì giả định precision luôn giống `%f`.

## 6. Ký hiệu phần trăm: `%%` và `%` có width

### 6.1. Vì sao phải viết hai dấu phần trăm?

Dấu `%` bắt đầu một chỉ thị định dạng; muốn đưa một `%` **nguyên văn** vào output, dùng `%%`:

```java
String a = "Progress: 80%%".formatted();  // "Progress: 80%"
String b = "Done: %s%%".formatted("90"); // "Done: 90%"
```

`%%` không đòi hỏi giá trị đối số. Nếu chỉ dùng dấu `%` đơn độc tại cuối format string, Java sẽ báo lỗi định dạng vì thiếu conversion hợp lệ.

### 6.2. Có thể dùng width cho dấu phần trăm

```java
String a = "|%6%|".formatted();  // "|     %|"
String b = "|%-6%|".formatted(); // "|%     |"
```

`%6%` là một dấu `%` cộng 5 dấu cách bên trái. `%-6%` căn trái nên 5 dấu cách nằm bên phải. Cờ `-` và width hợp lệ với conversion percent; precision không hợp lệ.

### 6.3. Hiển thị tỷ lệ: Formatter không tự nhân 100

```java
double ratio = 0.875;

String shown = String.format(
        java.util.Locale.US,
        "%.1f%%",
        ratio * 100
);
// "87.5%"
```

`%.1f` quyết định làm tròn số được truyền vào và `%%` chỉ chèn dấu `%` thật. **Formatter không tự hiểu `0.875` là 87,5%.** Phép nhân 100 được viết rõ trong code, nên dễ kiểm tra.

Khi đọc `"%6.2f%%"`, hãy tách thành hai specifier liên tiếp: `%6.2f` cho số và `%%` cho ký hiệu phần trăm.

## 7. Ví dụ hoàn chỉnh: Java 17+ và stdout kiểm chứng

Tạo file `WidthPrecisionPercentDemo.java`:

```java
import java.util.Locale;

public class WidthPrecisionPercentDemo {
    public static void main(String[] args) {
        String labels =
                "|%8s|%-8s|%8.3s|".formatted("Java", "Java", "Java 15");

        String amounts =
                String.format(Locale.US, "|%8.2f|%08.2f|", 12.345, 12.345);

        String percent =
                String.format(Locale.US, "|%6%|%-6%|%.1f%%|", 87.5);

        String template = """
                Course: %-8s
                Score: %6.2f%%
                """;
        String report = String.format(Locale.US, template, "Java", 87.5);

        // Chỉ để nhìn rõ dấu cách: thay space bằng dấu "_".
        System.out.println(labels.replace(' ', '_'));
        System.out.println(amounts.replace(' ', '_'));
        System.out.println(percent.replace(' ', '_'));
        System.out.print(report.replace(' ', '_'));
    }
}
```

Chạy:

```bash
javac WidthPrecisionPercentDemo.java
java WidthPrecisionPercentDemo
```

**Stdout chính xác** (dấu `_` là dấu cách đã được thay để quan sát):

```text
|____Java|Java____|_____Jav|
|___12.35|00012.35|
|_____%|%_____|87.5%|
Course:_Java____
Score:__87.50%
```

Từng phần thể hiện:

1. `%8s` đệm trái, `%-8s` đệm phải, `%8.3s` cắt về `Jav` rồi đệm đủ width 8.
2. `%8.2f` cho `12.35` rồi đệm bằng space; `%08.2f` đệm bằng số 0.
3. `%6%` / `%-6%` căn dấu `%` trong vùng rộng 6; `%.1f%%` in `87.5%`.
4. Text block kết hợp `%-8s` và `%6.2f%%`. Giá trị report có newline ở cuối do dấu đóng text block nằm trên dòng riêng; `System.out.print` không tự thêm newline khác.

Mẫu số dùng `Locale.US` để output có dấu thập phân `.` nhất quán trên máy có locale khác nhau. Phần string-only dùng `String.formatted` nhằm minh họa API có từ Java 15.

## 8. `%%` khác `%n` thế nào?

Hai conversion này không lấy đối số:

| Specifier | Output | Width | Precision |
| --- | --- | --- | --- |
| `%%` | Một dấu `%` | Có; ví dụ `%5%`, `%-5%` | Không |
| `%n` | Dấu xuống dòng theo `System.lineSeparator()` | Không | Không |

```java
System.out.printf("50%% complete%n");
// In: 50% complete, sau đó xuống dòng theo hệ điều hành
```

`%n` khác escape `\n` trong Java string literal: `\n` luôn là ký tự LF; `%n` sử dụng line separator của nền tảng. Nếu kết quả dành cho file hoặc giao thức yêu cầu LF cố định, nên nêu rõ `\n` thay vì phụ thuộc `%n`.

## 9. Các lỗi thường gặp khi ghép format string

| Viết như sau | Vấn đề | Cách đúng |
| --- | --- | --- |
| `"Rate: %.1f%"` | Dấu `%` cuối không tạo conversion hợp lệ | `"Rate: %.1f%%"` |
| `"%.2d"` | `%d` không hỗ trợ precision | `"%2d"` cho width; `"%02d"` nếu muốn đệm 0 |
| `"%.2%"` | Percent không hỗ trợ precision | `"%%"` hoặc `"%5%"` |
| `"%5s"` với chuỗi dài hơn 5 | Tưởng Java sẽ cắt chuỗi | Dùng `"%.5s"` nếu muốn giới hạn |
| `"%8.2f"` với đầu vào `String` | `%f` cần kiểu số thực tương thích | Truyền `double`, `float`, `BigDecimal`... |
| `String.format("%.1f", x)` trong kiểm thử dùng nhiều locale | Dấu thập phân có thể thành dấu phẩy | Chỉ định `Locale.US` khi cần output ổn định |

Một số ngoại lệ của `java.util.Formatter` cần biết là `IllegalFormatConversionException` (sai kiểu tham số), `MissingFormatArgumentException` (thiếu tham số) và `IllegalFormatPrecisionException` (precision không hợp lệ). Chúng là lỗi định dạng lúc chạy, dù source Java đã biên dịch thành công.

**Đừng dùng trực tiếp văn bản tùy ý chứa `%` làm format string.** Nếu chuỗi là nội dung người dùng, truyền nó như giá trị của `%s`, hoặc đưa ra output không qua Formatter:

```java
String comment = "100% done";
String safe = "Comment: %s".formatted(comment);
// "Comment: 100% done"
```

Truyền `comment` làm **đối số** giữ dấu phần trăm nguyên vẹn; dấu `%` chỉ có ý nghĩa đặc biệt khi nằm trong format string.

## 10. Ghi nhớ cách áp dụng

- Width là **độ rộng tối thiểu**; `%-8s` căn trái, `%8s` căn phải.
- Precision tùy conversion: `%.3s` giới hạn ký tự chuỗi; `%.2f` là 2 chữ số sau dấu thập phân; `%.3g` liên quan chữ số có nghĩa.
- `%8.3s`: precision xử lý phần giá trị, width thêm đệm cho kết quả.
- `%%` để hiển thị một dấu `%`; có thể dùng width như `%6%`, nhưng không được dùng precision với percent.
- `%.1f%%` chỉ hiển thị số và dấu `%`; muốn chuyển tỷ lệ 0–1 thành phần trăm phải nhân 100 trước.
- Chọn `String.formatted` cho cú pháp gọn từ Java 15; dùng `String.format(Locale, ...)` khi cần quy định cách hiển thị số cố định; dùng `printf` khi muốn ghi ra luồng.
- Khi kiểm thử text được căn cột, hãy kiểm tra chính xác dấu cách hoặc thay chúng bằng ký tự nhìn thấy như `_` trong phần minh họa.

## Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — `java.util.Formatter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Formatter.html): cú pháp, width, precision, percent, cờ, exception.
- [Oracle Java SE 26 — `java.lang.String`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): `String.format`, `String.formatted` và hợp đồng API.
- [Oracle Java SE 15 — `String.formatted` (Since: 15)](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html): xác nhận thời điểm bổ sung phương thức.

Các API và quy tắc được trình bày ở đây vẫn được hỗ trợ trên Java hiện đại; bài học không dựa vào chức năng preview đã hết hạn hoặc API legacy.