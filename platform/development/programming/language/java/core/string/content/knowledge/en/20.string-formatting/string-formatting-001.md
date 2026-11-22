# String.format, String.formatted và Formatter trong Java

## 1. Vì sao cần định dạng chuỗi?

Khi tạo thông báo, báo cáo, log hay dòng dữ liệu trình bày cho người đọc, ta thường muốn ghép **văn bản cố định** với những giá trị có kiểu khác nhau: chuỗi, số nguyên, số thực, ngày giờ. Nối nhiều đoạn bằng toán tử `+` có thể khiến mã dài và khó căn chỉnh. Java cung cấp ba API cùng dựa trên **cú pháp format string**:

- `String.format(...)`: tạo một `String` mới từ mẫu định dạng và các đối số.
- `String.formatted(...)`: gọi mẫu định dạng như một phương thức trên chính `String`, từ Java 15.
- `java.util.Formatter`: đối tượng định dạng có trạng thái, có thể ghi nhiều lần vào một đích như `StringBuilder` hoặc `Appendable`.

Mục tiêu của bài: đọc đúng ký hiệu `%...`, kiểm soát độ rộng và số chữ số thập phân, chọn đúng `Locale`, phân biệt ba API, biết cách xử lý lỗi format và chọn công cụ phù hợp.

## 2. String.format: định dạng một lần thành chuỗi

Hai overload quan trọng:

```java
public static String format(String format, Object... args);

public static String format(Locale l, String format, Object... args);
```

Đối số đầu là **mẫu** chứa văn bản cố định và các *format specifier* (ký hiệu bắt đầu bằng `%`). Các đối số tiếp theo cung cấp giá trị thay vào những vị trí đó.

```java
import java.util.Locale;

String text = String.format(
        Locale.US,
        "Tên: %s | Tuổi: %d | Điểm: %.2f",
        "An", 20, 8.75
);
// "Tên: An | Tuổi: 20 | Điểm: 8.75"
```

Ở ví dụ này: `%s` biểu diễn chuỗi, `%d` biểu diễn số nguyên dạng thập phân, `%.2f` hiển thị số thực với **2 chữ số sau dấu thập phân**. `Locale.US` giúp cách in dấu thập phân ổn định, ngay cả khi máy chạy sử dụng locale khác.

Nếu không truyền `Locale`, `String.format(String, Object...)` sử dụng **default FORMAT locale** của JVM (`Locale.getDefault(Locale.Category.FORMAT)`). Vì vậy cùng một mẫu định dạng số có thể tạo dấu phân cách khác nhau trên hai máy. Khi kết quả cần nhất quán trong tài liệu, bài kiểm thử hoặc giao tiếp giữa hệ thống, hãy truyền locale tường minh.

`String.format` trả chuỗi mới, không thay đổi biến mẫu, đối số hay `String` nguồn.

## 3. String.formatted: viết gọn từ mẫu chuỗi

Từ Java 15, `String` có phương thức thể hiện trực tiếp quan hệ “mẫu này được định dạng bằng các giá trị sau”:

```java
public String formatted(Object... args);
```

Ví dụ:

```java
String title = "Chào %s, bạn có %d thông báo."
        .formatted("Linh", 3);

// "Chào Linh, bạn có 3 thông báo."
```

So sánh hai cách có cùng mục đích:

```java
String a = String.format("Mã: %s, số lượng: %d", "P01", 7);
String b = "Mã: %s, số lượng: %d".formatted("P01", 7);
```

Trong cùng môi trường locale, `a` và `b` có cùng nội dung. `formatted(...)` thuận tiện khi mẫu chuỗi đã có sẵn dưới dạng biểu thức `String`, ví dụ một text block nhiều dòng. Nó dùng các quy tắc định dạng của `Formatter`, tương tự `String.format`.

**Khác biệt cần nhớ:** `String.formatted(...)` **không có overload nhận `Locale`**. Khi cần định dạng số/ngày theo locale cụ thể, chọn `String.format(locale, mẫu, đốiSố...)` hoặc `Formatter` được cấu hình locale. Cả `format` lẫn `formatted` đều tạo kết quả `String` mới.

## 4. Cấu trúc format specifier: đủ để bắt đầu

Ba API cùng sử dụng cú pháp của `Formatter`: `%[argument_index$][flags][width][.precision]conversion`. Dấu ngoặc vuông là ký hiệu mô tả thành phần tùy chọn, không phải ký tự gõ vào mẫu. Chỉ số đối số bắt đầu từ **1**; `conversion` quyết định loại giá trị, chẳng hạn `%s` (chuỗi), `%d` (số nguyên), `%f` (số thực), `%tF` (ngày). `%%` in dấu phần trăm và `%n` chèn kết thúc dòng theo nền tảng; hai ký hiệu này không tiêu thụ đối số.

```java
String line = String.format(Locale.US, "%s: %d mục, tổng %.2f", "Giỏ", 3, 12.5);
// "Giỏ: 3 mục, tổng 12.50"
```

Đây là lớp cú pháp chung giúp bạn hiểu cả ba API. Việc phân tích đầy đủ các tổ hợp chỉ số, flags và conversion là trọng tâm của các bài chuyên sâu tiếp theo trong chương.

## 5. Width, precision và flags: những khác biệt thiết yếu

`width` là **độ rộng tối thiểu** của trường xuất, không tự cắt văn bản. Dấu `-` căn trái; flag `0` đệm số 0 cho kiểu số phù hợp. `precision` phụ thuộc conversion: `%.2f` in hai chữ số thập phân, còn `%.3s` giới hạn chuỗi còn tối đa ba ký tự.

```java
String s = String.format(Locale.US, "|%-6s|%04d|%.2f|", "AB", 7, 2.5);
// "|AB    |0007|2.50|"
```

Không phải flag hay precision nào cũng tương thích với mọi conversion: ví dụ `%.2d` và `%05s` không hợp lệ. Định dạng chỉ thay đổi văn bản đầu ra, không làm tròn hoặc sửa biến dữ liệu gốc.

## 6. Chọn lại hoặc đổi thứ tự đối số

Thông thường `%s`, `%d` nhận đối số lần lượt từ trái sang phải. `%2$s` chọn đối số thứ hai, còn `%1$d` chọn đối số thứ nhất; flag `<` tái sử dụng đối số của specifier có đối số trước đó.

```java
String reordered = String.format("%2$s mua %1$d món", 3, "Lan");
// "Lan mua 3 món"
String reused = String.format("%s -> %<S", "java");
// "java -> JAVA"
```

Việc chỉ định đối số hữu ích khi câu thông báo đổi trật tự từ. Với bản địa hóa câu hoàn chỉnh theo ngôn ngữ, chương này còn giới thiệu `MessageFormat` và `ResourceBundle`.

## 7. Locale thuộc về kết quả, không thuộc về mẫu

`String.format(format, args)` và `String.formatted(args)` dùng locale mặc định cho định dạng (`Locale.Category.FORMAT`). `String.format(locale, format, args)` cho phép chọn rõ quy ước dấu thập phân, phân nhóm số hoặc chữ hoa; bản thân mẫu văn bản cố định không được dịch tự động.

```java
String us = String.format(Locale.US, "%,.2f", 12345.5);       // 12,345.50
String de = String.format(Locale.GERMANY, "%,.2f", 12345.5);  // 12.345,50
```

Chọn locale theo người đọc; khi cần dữ liệu cho máy, tuân thủ chuẩn serialization của giao thức. Không thay đổi `Locale.setDefault` theo từng request trong ứng dụng đa luồng.

## 8. Formatter: định dạng nhiều lần vào cùng đích

`Formatter` thuộc `java.util`, triển khai `Closeable` và `Flushable`. Nó có các lời gọi `format(...)` tương tự, nhưng ghi vào **đích đầu ra** được gắn với đối tượng. Đích có thể là `StringBuilder`, `Writer`, `OutputStream` hoặc các đối tượng hỗ trợ cách thức ghi tương thích, tùy constructor.

Ví dụ ghi tuần tự vào `StringBuilder`:

```java
import java.util.Formatter;
import java.util.Locale;

StringBuilder builder = new StringBuilder();

try (Formatter formatter = new Formatter(builder, Locale.US)) {
    formatter.format("Mã: %04d; ", 7);
    formatter.format("Giá: %,.2f", 1234.5);
}

System.out.println(builder);
// Mã: 0007; Giá: 1,234.50
```

`format(...)` trên `Formatter` trả chính `Formatter` nên có thể gọi nối tiếp. Trong ví dụ, cả hai lời gọi ghi vào cùng `builder`; `StringBuilder` vẫn đọc được sau khi đóng `Formatter`. Dùng `try-with-resources` để đóng `Formatter` khi không dùng nữa, nhất là khi đích là tài nguyên I/O cần quản lý.

Cần lưu ý **đóng `Formatter` có thể đóng luôn đích đầu ra** nếu đích cũng là `Closeable`. Không tự tạo một `Formatter` rồi đóng nó trên `System.out` khi bạn vẫn cần tiếp tục ghi ra console. Có thể dùng `System.out.printf(...)` hoặc `System.out.format(...)` để ghi trực tiếp vào luồng chuẩn trong trường hợp đơn giản.

`Formatter` cũng có `locale()` để biết locale liên kết và `ioException()` để kiểm tra lỗi `IOException` mà formatter ghi nhận khi thao tác với đích đầu ra. Khi ghi tệp hoặc luồng, đừng chỉ kiểm tra chuỗi kết quả mà bỏ qua trạng thái I/O. Một đối tượng `Formatter` dùng chung cũng không nên được giả định là an toàn khi nhiều luồng cùng gọi; hãy tự kiểm soát truy cập đồng thời nếu cần.

## 9. Chương trình Java 17+ chạy độc lập

Tạo tệp tên `FormattingDemo.java` với toàn bộ nội dung:

```java
import java.time.LocalDate;
import java.util.Formatter;
import java.util.Locale;

public class FormattingDemo {
    public static void main(String[] args) {
        Locale us = Locale.US;

        String product = String.format(
                us, "Sản phẩm: %s | SL: %d | Giá: %,.2f",
                "Bút", 3, 1234.5);
        System.out.println(product);

        String greeting = "Xin chào %s (%d tuổi)"
                .formatted("Mai", 21);
        System.out.println(greeting);

        System.out.println(
                String.format(us, "|%8s|%-8s|", "cat", "dog"));

        System.out.println(
                String.format(us,
                        "%2$s mua %1$d món; %2$s đã thanh toán.",
                        3, "Lan"));

        System.out.println(
                String.format(us,
                        "Ngày: %tF", LocalDate.of(2026, 10, 23)));

        System.out.println(
                String.format(us, "US: %,.2f", 12345.5));
        System.out.println(
                String.format(Locale.GERMANY,
                        "DE: %,.2f", 12345.5));

        StringBuilder builder = new StringBuilder();
        try (Formatter formatter = new Formatter(builder, us)) {
            formatter.format("A=%04d; ", 7);
            formatter.format("B=%.1f", 2.5);
        }
        System.out.println(builder);
    }
}
```

Biên dịch và chạy (đảm bảo tệp nguồn được lưu dưới UTF-8):

```bash
javac -encoding UTF-8 FormattingDemo.java
java FormattingDemo
```

Kết quả stdout chính xác:

```text
Sản phẩm: Bút | SL: 3 | Giá: 1,234.50
Xin chào Mai (21 tuổi)
|     cat|dog     |
Lan mua 3 món; Lan đã thanh toán.
Ngày: 2026-10-23
US: 12,345.50
DE: 12.345,50
A=0007; B=2.5
```

Các dòng minh họa lần lượt `String.format`, `String.formatted`, căn lề, chỉ số đối số, định dạng ngày, locale và cách dùng lại `Formatter`. Ví dụ chọn ngày xác định và `Locale` tường minh ở các chuyển đổi cần locale để kết quả dễ kiểm tra.

## 10. Ngày giờ trong Formatter

`%tF` định dạng ngày theo `yyyy-MM-dd`; `%tT` định dạng giờ theo `HH:mm:ss`, nếu đối số thực sự cung cấp các trường thời gian cần thiết. Ví dụ, `String.format(Locale.US, "%tF", LocalDate.of(2026, 10, 23))` cho `2026-10-23` (cần import `LocalDate`). `LocalDate` không có giờ để dùng với `%tT`. Các yêu cầu parse, múi giờ hoặc pattern ngày giờ phong phú nên dùng `DateTimeFormatter`.

## 11. Lỗi đầu vào và ngoại lệ định dạng

Compiler thường không kiểm tra việc khớp giữa conversion và đối số. Ví dụ `%d` với chuỗi `"42"` gây `IllegalFormatConversionException`, thiếu đối số gây `MissingFormatArgumentException`, flag/precision sai có thể gây các lớp khác của `IllegalFormatException`. Đối số `(Object) null` với `%s` hiển thị `"null"`, còn `%b` với chuỗi `"false"` lại cho `"true"` vì đó là đối tượng không null.

Với văn bản từ người dùng chứa `%`, hãy đưa văn bản đó vào đối số `%s` thay vì coi nó là format string. Chọn `%%` khi muốn in dấu phần trăm ngay trong mẫu; dùng `%n` cho kết thúc dòng theo nền tảng, hoặc `\n` khi giao thức yêu cầu LF cố định. Khi đóng `Formatter` gắn với đích I/O, nhớ kiểm tra và quản lý vòng đời của đích như ở mục 8.

## 12. Chọn API phù hợp

| Nhu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Một câu thông báo, chủ động chỉ định locale | `String.format(Locale, ...)` | Mẫu, đối số và locale rõ ràng trong một lệnh |
| Một mẫu `String` ngắn, dùng locale mặc định | `template.formatted(args)` | Đọc thuận khi mẫu là receiver |
| Xây dựng dần nhiều đoạn định dạng | `Formatter` + `StringBuilder` | Có thể gọi `format` nhiều lần vào cùng đích |
| In trực tiếp ra stdout | `System.out.printf(...)` hoặc `format(...)` | Không cần tạo chuỗi trung gian nếu chỉ cần in |
| Ngày giờ phức tạp | `DateTimeFormatter` | Kiểm soát pattern, locale và các kiểu thời gian |
| Số theo quy tắc tiền tệ/hiển thị chuyên biệt | `NumberFormat` hoặc `DecimalFormat` phù hợp | Có quy tắc biểu diễn số và tiền tệ chuyên dụng |

Các công cụ không loại trừ nhau. Ví dụ một chương trình có thể dùng `DateTimeFormatter` tạo phần ngày theo quy tắc riêng, sau đó đưa chuỗi đó vào `String.format` cùng những trường khác.

## 13. Bài tập tự luyện: chọn đúng API

**Bài 1.** Cần tạo một chuỗi báo cáo với dấu phân cách số ổn định ở Mỹ. Chọn `String.format(Locale.US, "Tổng: %,.2f", 1234.5)` để nhận `"Tổng: 1,234.50"`.

**Bài 2.** Mẫu đã nằm trong biến `String template = "Xin chào %s"`, chỉ cần locale mặc định. Dùng `template.formatted("Mai")`, kết quả `"Xin chào Mai"`. Nếu cần locale cụ thể, chuyển sang `String.format(locale, template, "Mai")`.

**Bài 3.** Cần ghi nhiều lần vào một `StringBuilder` mà không tạo nhiều chuỗi trung gian: tạo `Formatter(builder, locale)` và gọi `format(...)` liên tiếp. Sau đó đóng formatter; nếu đích là `Closeable`, việc đóng formatter có thể đóng luôn đích, nên quản lý tài nguyên có chủ đích.

## 14. Ghi nhớ

1. `String.format` là phương thức **tĩnh**, phù hợp cho một lần định dạng và có overload nhận `Locale`.
2. `String.formatted` là phương thức **instance** từ Java 15, ngắn gọn khi mẫu định dạng đã là `String`; không có overload `Locale`.
3. `Formatter` là đối tượng có thể **ghi nhiều lần vào cùng một đích** và cần chú ý vòng đời tài nguyên, đặc biệt khi đích là luồng I/O.
4. Format specifier có thứ tự `%[index$][flags][width][.precision]conversion`; **width** và **precision** có ý nghĩa khác nhau.
5. Chọn đúng conversion cho **kiểu dữ liệu thật**; sai kiểu/thiếu đối số/flag không hợp lệ có thể gây ngoại lệ runtime.
6. Với kết quả cần nhất quán, chỉ định `Locale` tường minh. Định dạng để trình bày không thay thế thao tác parse, tính toán chính xác hoặc serialization.

Tài liệu tham khảo chính thức: [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html), [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html).
