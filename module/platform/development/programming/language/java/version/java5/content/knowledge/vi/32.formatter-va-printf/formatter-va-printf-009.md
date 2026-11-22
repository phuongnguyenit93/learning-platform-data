# Xuống dòng bằng %n và dấu phần trăm theo nghĩa đen

## 1. Hai chỉ định đặc biệt không lấy đối số

Trong `printf`, `String.format` hoặc `Formatter.format`, dấu `%` mở đầu một chỉ định định dạng. Nếu muốn tạo dấu xuống dòng hoặc in chính ký tự phần trăm, dùng:

| Chỉ định trong khuôn | Kết quả | Có lấy đối số không? |
| --- | --- | --- |
| %n | Dấu xuống dòng của nền tảng | Không |
| %% | Một ký tự % | Không |

Ví dụ:

```java
System.out.printf("Completed: %d%%%n", 80);
```

Đoạn này đặt trong một phương thức và in một dòng:

```text
Completed: 80%
```

Sau ký tự phần trăm có dấu xuống dòng. Khuôn được đọc thành các phần:

```text
"Completed: " + %d + %% + %n
                 |    |    |
                 80   %    xuống dòng
```

Đây là cách đọc theo từng chỉ định, không phải phép nối Java được viết trong chương trình.

Các quy tắc này được giới thiệu cùng Formatter từ Java 5 và vẫn phù hợp trên Java hiện đại. Ví dụ hoàn chỉnh trong bài chạy với Java 17+.

## 2. %n khác với hai ký tự xuống dòng viết trong mã Java

Có hai lớp diễn giải:

1. Trình biên dịch Java tạo giá trị String từ mã nguồn.
2. Formatter diễn giải các chỉ định có dấu phần trăm trong giá trị String đó.

| Mã nguồn chuỗi Java | Giá trị String trước Formatter | Khi dùng làm khuôn |
| --- | --- | --- |
| "%n" | Hai ký tự % và n | Formatter tạo xuống dòng theo nền tảng |
| "\n" | Một ký tự LF | Formatter giữ ký tự LF đã có |
| "\\n" | Dấu gạch chéo ngược và chữ n | In nguyên hai ký tự đó |
| "%%" | Hai ký tự phần trăm | Formatter tạo một ký tự phần trăm |

Ở bảng này, cột mã nguồn là các chuỗi Java thực sự: `"\n"` có escape xuống dòng của Java; `"\\n"` có escape cho dấu gạch chéo ngược.

Ví dụ:

```java
System.out.print("%n");
```

`print` không dùng ngôn ngữ khuôn của Formatter, nên in nguyên `%n`.

Trong khi đó:

```java
System.out.printf("%n");
```

lại tạo dấu xuống dòng.

Tương tự, `System.out.print("%%")` in hai dấu phần trăm; `System.out.printf("%%")` in một dấu. Ý nghĩa phụ thuộc vào API đang nhận chuỗi.

## 3. %n theo nền tảng, còn \n luôn là LF trong chuỗi Java

Theo hợp đồng Formatter, `%n` dùng dấu phân cách dòng do `System.lineSeparator()` cung cấp:

- Môi trường Windows thường dùng CRLF: ký tự CR rồi LF.
- Môi trường Unix/Linux thường dùng LF.
- `"\n"` trong Java luôn tạo ký tự LF, không tự mở rộng thành CRLF.

Vì vậy hai chuỗi trông giống nhau khi hiển thị trên console vẫn có thể khác về độ dài và byte khi lưu ra tệp.

```java
String platform = String.format("A%nB");
String explicitLF = "A\nB";
```

Trên môi trường dùng LF, hai giá trị có thể bằng nhau. Trên môi trường dùng CRLF, giá trị thứ nhất có thêm CR trước LF.

Khi output là văn bản thông thường cần theo quy ước hệ điều hành, `%n` thuận tiện trong một khuôn Formatter. Khi định dạng tệp hoặc giao thức quy định cụ thể LF hay CRLF, hãy dùng chính quy ước đó; không mặc định `%n` phù hợp với mọi chuẩn trao đổi dữ liệu.

Nguồn hợp đồng: [Formatter — line separator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html), [System.lineSeparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#lineSeparator()).

### Không đồng nhất xuống dòng với flush

Tạo một dấu xuống dòng và đẩy dữ liệu đệm ra đích là hai hành vi khác nhau. Việc tự flush còn phụ thuộc loại stream và cấu hình của nó.

Không dùng `%n` như lời bảo đảm chung rằng mọi lớp đệm hay thiết bị bên dưới đã nhận dữ liệu ngay. Khi cần flush theo hợp đồng I/O, hãy quản lý riêng việc ấy. [PrintStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html#printf(java.lang.String,java.lang.Object...)) mô tả riêng khả năng định dạng và hành vi của stream.

## 4. printf không tự thêm xuống dòng

```java
System.out.printf("A");
System.out.printf("B");
```

Kết quả là `AB` trên cùng dòng. Tên printf có chữ “print” không có nghĩa nó hoạt động như println.

Để in từng dòng:

```java
System.out.printf("A%n");
System.out.printf("B%n");
```

Kết quả:

```text
A
B
```

Nếu khuôn đã có `%n`, đừng vô tình thêm một lần xuống dòng bên ngoài nữa:

```java
System.out.println(String.format("A%n"));
```

Chuỗi đã kết thúc bằng dấu xuống dòng; println lại thêm dấu xuống dòng nữa, thường tạo một dòng trống sau A. Nếu chỉ cần in khuôn có `%n`, dùng printf trực tiếp hoặc print chuỗi đã định dạng.

Ngược lại, `String.format("A%n")` chỉ tạo String. Nó chưa ghi gì ra console.

## 5. In phần trăm: %% không tính toán tỷ lệ

```java
System.out.printf("Progress: %d%%%n", 80);
```

in 80%. `%%` chỉ tạo ký tự phần trăm; nó không nhân 100, không chia 100 và không chuyển một phân số thành tỷ lệ phần trăm.

Nếu giá trị đang là tỷ lệ 0.8 mà muốn hiển thị 80.0%:

```java
double ratio = 0.8;
System.out.printf(Locale.ROOT,
        "Ratio: %.1f%%%n", ratio * 100);
```

Cần import `java.util.Locale`. Kết quả:

```text
Ratio: 80.0%
```

Phép nhân là quyết định của dữ liệu/nghiệp vụ, không phải tác dụng của `%%`. Không nhân thêm nếu giá trị đầu vào đã là 80.

### Dấu phần trăm trong đối số không cần nhân đôi

```java
String message = "Progress: 80%";
System.out.printf("%s%n", message);
```

Kết quả vẫn là:

```text
Progress: 80%
```

Formatter diễn giải chuỗi khuôn `"%s%n"`; nó không diễn giải lại nội dung message như một khuôn thứ hai.

Do đó, nếu dữ liệu người dùng có `%n` hoặc `%s`, đặt dữ liệu ấy vào đối số `%s` sẽ in nguyên văn theo conversion chuỗi. Không cần thay mọi dấu phần trăm trong dữ liệu thành hai dấu khi dữ liệu không được dùng làm khuôn.

Ví dụ `System.out.printf("%s%n", "literal %n")` in một dòng `literal %n`, rồi mới xuống dòng từ chỉ định ở khuôn ngoài.

## 6. Hai chỉ định không làm dịch vị trí đối số

```java
System.out.printf("%s %% %s%n", "A", "B");
```

Kết quả:

```text
A % B
```

`%s` đầu lấy A; `%%` không lấy gì; `%s` tiếp theo lấy B; `%n` không lấy gì. Không cần truyền thêm đối số “cho dấu phần trăm” hay “cho xuống dòng”.

Để in nguyên hai ký tự `%n` trong một khuôn, dùng:

```java
System.out.printf("literal: %%n%n");
```

Kết quả:

```text
literal: %n
```

Formatter đọc `%%` thành một dấu phần trăm, chữ n sau đó là văn bản thường; cuối cùng `%n` riêng tạo xuống dòng.

Nếu muốn in hai dấu phần trăm, khuôn cần hai lần `%%`, tức `"%%%%"`.

## 7. Width và cờ của %% khác với %n

`%%` cho phép width và cờ căn trái `-` theo hợp đồng:

```java
String text = String.format("[%5%][%-5%]");
```

Kết quả là:

```text
[    %][%    ]
```

Mỗi vùng rộng tối thiểu 5 ký tự gồm một dấu phần trăm và bốn dấu cách. Đây là width cho ký tự được tạo ra, không phải chọn đối số thứ năm.

Precision không áp dụng cho conversion phần trăm. Các cờ khác không được tùy ý gắn vào nó; chẳng hạn `%0%` không phải cách đệm 0 cho dấu phần trăm.

Với `%n`, flags, width và precision đều không áp dụng. Không viết `%5n` để mong tạo năm lần xuống dòng hoặc đệm dòng tới width 5.

Muốn hai lần xuống dòng, viết `%n%n`. Muốn dòng trống gồm một số dấu cách vì một lý do trình bày cụ thể, hãy biểu diễn rõ phần văn bản đó, không thêm width vào n.

## 8. Chương trình ví dụ đầy đủ

Lưu thành `PercentAndNewlineDemo.java`:

```java
import java.util.Locale;

public class PercentAndNewlineDemo {
    public static void main(String[] args) {
        System.out.printf(Locale.ROOT,
                "Progress: %d%%%n", 80);

        System.out.printf(Locale.ROOT,
                "Ratio: %.1f%%%n", 0.8 * 100);

        System.out.printf("literal: %%n%n");
        System.out.printf("args: %s %% %s%n", "A", "B");

        String padded = String.format("[%5%][%-5%]");
        System.out.println(padded);

        String fromUser = "Already 80% / literal %n";
        System.out.printf("%s%n", fromUser);

        String formatted = String.format("A%nB");
        String expected = "A" + System.lineSeparator() + "B";
        System.out.println("Platform separator matched: "
                + formatted.equals(expected));

        System.out.printf("Two percent signs: %%%% last%n");
    }
}
```

Chạy:

```shell
javac PercentAndNewlineDemo.java
java PercentAndNewlineDemo
```

Stdout theo các dòng:

```text
Progress: 80%
Ratio: 80.0%
literal: %n
args: A % B
[    %][%    ]
Already 80% / literal %n
Platform separator matched: true
Two percent signs: %% last
```

Các dòng hiển thị giống nhau trên nền tảng thông thường, nhưng byte xuống dòng thực tế đi theo `%n` hoặc println của nền tảng. Chương trình kiểm chứng bằng so sánh với System.lineSeparator thay vì khẳng định mọi máy đều xuất một byte LF.

## 9. Lỗi viết khuôn và lỗi escape Java

### Dấu phần trăm lẻ

```java
System.out.printf("Completed: 80%");
```

Khuôn kết thúc ở dấu phần trăm chưa tạo thành chỉ định hợp lệ, nên lỗi định dạng xảy ra. Đừng trông chờ Formatter tự hiểu nó là văn bản thường.

Đặc biệt, cách viết sai có thể vô tình tạo một conversion hợp lệ nhưng khác ý định. Tách văn bản và các chỉ định, rồi dùng `%%` cho mọi dấu phần trăm nghĩa đen **trong khuôn**.

### Gạch chéo ngược không phải escape cho Formatter

Trong mã nguồn Java, `"\%"` không phải escape chuỗi hợp lệ nên không biên dịch. Viết `"\\%"` tạo dấu gạch chéo ngược rồi dấu phần trăm, nhưng Formatter vẫn thấy dấu phần trăm; gạch chéo ngược không làm nó thành ký tự thường.

Muốn tạo chính ký tự phần trăm từ khuôn thì dùng `%%`. Muốn hiển thị dữ liệu đã có sẵn thì dùng print hoặc đặt dữ liệu vào đối số phù hợp.

### Dùng %N thay cho %n

Không phải mọi conversion đều có dạng chữ hoa. `%N` không phải biến thể hợp lệ để tạo xuống dòng. Cần dùng n viết thường.

### Chương trình kiểm chứng lỗi lúc chạy

Lưu thành `SpecialConversionErrorDemo.java`:

```java
import java.util.IllegalFormatException;

public class SpecialConversionErrorDemo {
    private static void show(String label, String pattern) {
        try {
            String result = String.format(pattern);
            System.out.println(label + ": " + result);
        } catch (IllegalFormatException e) {
            System.out.println(label + ": "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.println("Format token length: " + "%n".length());
        System.out.println("Java LF length: " + "\n".length());
        System.out.println("Literal backslash-n length: "
                + "\\n".length());

        show("lone percent", "%");
        show("newline width", "%3n");
        show("newline flag", "%-n");
        show("newline precision", "%.1n");
        show("percent zero flag", "%0%");
        show("uppercase newline", "%N");
    }
}
```

Chạy:

```shell
javac SpecialConversionErrorDemo.java
java SpecialConversionErrorDemo
```

Stdout:

```text
Format token length: 2
Java LF length: 1
Literal backslash-n length: 2
lone percent: UnknownFormatConversionException
newline width: IllegalFormatWidthException
newline flag: IllegalFormatFlagsException
newline precision: IllegalFormatPrecisionException
percent zero flag: IllegalFormatFlagsException
uppercase newline: UnknownFormatConversionException
```

Lỗi escape Java không được đưa vào chương trình chạy, vì chúng phải bị phát hiện từ bước biên dịch; chương trình trên chỉ kiểm chứng các lỗi khuôn Formatter lúc chạy.

## 10. Kiểm tra output khi newline không nhìn thấy

Khi unit test so chuỗi, đừng chỉ nhìn việc terminal có xuống dòng hay không. Có thể kiểm tra trực tiếp:

```java
String actual = String.format("A%nB");
String expected = "A" + System.lineSeparator() + "B";
boolean matches = actual.equals(expected);
```

Nếu hợp đồng yêu cầu LF cố định, expected phải chứa LF cố định và mã tạo output cũng phải làm theo hợp đồng ấy. Không thay expected theo nền tảng chỉ để che một sai lệch của định dạng giao thức.

Với output có width, dùng dấu phân cách nhìn thấy được như `[` và `]` để quan sát dấu cách. Với byte xuống dòng, có thể ghi nhận mã ký tự hoặc byte trong công cụ kiểm thử khi cần; phân biệt tiếp mã hóa ký tự với lựa chọn newline.

Không gọi format lần nữa trên một chuỗi đã được định dạng chỉ để in ra. Một dấu phần trăm mới tạo ra có thể lại bị diễn giải ở lần thứ hai. Chuẩn bị khuôn một lần, đưa dữ liệu vào đối số, rồi ghi kết quả theo đúng API.

## 11. Tự kiểm tra

**%n lấy một đối số String để xuống dòng không?**  
Không. Nó tự tạo dấu xuống dòng nền tảng.

**Vì sao 80% nằm trong đối số %s không cần viết thành 80%%?**  
Vì nội dung đối số không được diễn giải lại như khuôn.

**printf có tự xuống dòng cuối lời gọi không?**  
Không. Cần chỉ định hoặc ký tự xuống dòng rõ ràng nếu muốn.

**%5n có nghĩa năm lần xuống dòng không?**  
Không. Width không áp dụng cho n và làm khuôn lỗi.

**%% có nhân tỷ lệ 0.8 thành 80 không?**  
Không. Nó chỉ in ký tự phần trăm; chuyển đổi tỷ lệ thuộc xử lý dữ liệu.

Điểm cần nhớ: `%n` và `%%` là cú pháp của Formatter, còn escape như `\n` và `\\` thuộc cú pháp chuỗi Java. Hiểu hai lớp ấy giúp chọn đúng ký tự output và tránh diễn giải dữ liệu như khuôn.
