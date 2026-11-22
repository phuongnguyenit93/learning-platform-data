# Chỉ số đối số và tái sử dụng đối số

## 1. Tách thứ tự dữ liệu khỏi thứ tự hiển thị

Một chuỗi định dạng có thể cần:

- Hiển thị đối số thứ hai trước đối số thứ nhất.
- Dùng cùng một giá trị ở nhiều vị trí.
- In một số theo nhiều cách biểu diễn.
- Tách năm, tháng và ngày từ cùng một đối tượng ngày.

Nếu chỉ dùng `%s`, `%d` liên tiếp, mỗi chỉ thị thông thường nhận đối số kế tiếp. Ta phải lặp đối số trong danh sách hoặc thay đổi thứ tự truyền vào khi mẫu hiển thị thay đổi.

`Formatter` hỗ trợ ba cách chọn đối số:

1. **Thứ tự ngầm định:** `%s`, `%d` lấy lần lượt các đối số.
2. **Chỉ số tường minh:** `%2$s` chọn đối số thứ hai.
3. **Tái sử dụng tương đối:** `%<s` dùng lại đối số được chỉ thị dùng đối số gần nhất chọn trước đó.

Các quy tắc này áp dụng cho chuỗi định dạng kiểu `Formatter` trong `System.out.printf`, `String.format`, `Formatter.format` và các API tương ứng. Xem phần Argument Index của [Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html).

## 2. Chỉ số tường minh bắt đầu từ 1

Một chỉ thị thông thường có dạng tổng quát:

```text
%[argument_index$][flags][width][.precision]conversion
```

Phần `argument_index$` là một số nguyên dương theo sau bởi `$`:

| Chỉ thị | Đối số được chọn |
| --- | --- |
| `%1$s` | Đối số định dạng thứ nhất, hiển thị dạng chuỗi |
| `%2$d` | Đối số thứ hai, hiển thị dạng số nguyên thập phân |
| `%3$.2f` | Đối số thứ ba, hiển thị dạng số thực với hai chữ số sau dấu thập phân |

Chỉ số này **bắt đầu từ 1**, khác với chỉ số mảng Java bắt đầu từ 0. Nó đếm các giá trị đưa vào để định dạng, không đếm tham số `Locale` hoặc bản thân chuỗi mẫu.

Ví dụ minh họa:

```java
String result = String.format(
        Locale.ROOT,
        "%2$s / %1$s / %2$s",
        "A",
        "B");
```

Giá trị của `result`:

```text
B / A / B
```

`%2$s` xuất hiện hai lần nhưng đều chọn cùng đối số thứ hai. Số chỉ thị định dạng không phải số đối số bắt buộc khác nhau.

### Chỉ số không phải độ rộng

Hai chỉ thị nhìn gần giống nhau nhưng có nghĩa khác:

```text
%10s  → đối số ngầm định tiếp theo, độ rộng tối thiểu 10
%10$s → đối số thứ 10, không khai báo độ rộng
```

Dấu `$` làm ranh giới giữa số chỉ đối số và các thành phần còn lại.

Có thể kết hợp chỉ số với độ rộng và cờ:

```text
%1$04d
 │ │└─ chuyển đổi số nguyên thập phân
 │ └── cờ 0 và độ rộng 4
 └──── đối số thứ 1
```

Nếu đối số là 26, kết quả là `0026`. Độ rộng là tối thiểu, không có nghĩa cắt bớt một số dài hơn bốn ký tự.

## 3. Dấu < tái dùng đối số vừa được chọn

`<` là cờ tái sử dụng đối số. Ví dụ:

```java
String result = String.format(
        Locale.ROOT,
        "%1$d | %<04d | %<x",
        26);
```

Kết quả:

```text
26 | 0026 | 1a
```

Diễn giải từng bước:

1. `%1$d` chọn đối số thứ nhất là số 26.
2. `%<04d` dùng lại chính đối số đó, thêm số 0 đến độ rộng 4.
3. `%<x` vẫn dùng đối số đó, chuyển thành dạng hệ mười sáu.

Điều được tái sử dụng là **đối số gốc**, không phải chuỗi đã tạo ở lần định dạng trước.

Vì vậy `%<x` không lấy chuỗi `"0026"` để phân tích hay chuyển đổi. Nó định dạng lại giá trị số 26.

### Tái sử dụng không mang theo kiểu chuyển đổi

Mỗi chỉ thị vẫn cần một conversion hợp lệ và kiểu đối số tương thích.

```java
// Ví dụ lỗi: cùng một Integer không trở thành kiểu phù hợp cho %f.
String.format(Locale.ROOT, "%1$d / %<f", 26);
```

Việc `%1$d` dùng được không khiến `%<f` dùng được. Kiểu số nguyên được đóng gói thành `Integer` trong lời gọi này không phải kiểu được `%f` chấp nhận.

Khi đối số không tương thích với conversion, có thể nhận `IllegalFormatConversionException`; xem [hợp đồng ngoại lệ sai kiểu chuyển đổi](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IllegalFormatConversionException.html).

## 4. Ba cơ chế đánh số không cùng dùng một con trỏ

Chỉ thị không có chỉ số và không có `<` dùng bộ đếm ngầm định riêng: lần thứ nhất lấy đối số 1, lần thứ hai lấy đối số 2, v.v.

Các chỉ thị có chỉ số tường minh hoặc `<` không làm tăng bộ đếm ngầm định đó.

Xét:

```java
String result = String.format(
        Locale.ROOT,
        "%2$s | %s | %<s | %s | %1$s",
        "A",
        "B");
```

Kết quả:

```text
B | A | A | B | A
```

Bảng diễn giải:

| Chỉ thị | Cách chọn | Giá trị |
| --- | --- | --- |
| `%2$s` | Tường minh: đối số 2 | B |
| `%s` | Ngầm định lần 1: đối số 1 | A |
| `%<s` | Đối số được dùng gần nhất: đối số 1 | A |
| `%s` | Ngầm định lần 2: đối số 2 | B |
| `%1$s` | Tường minh: đối số 1 | A |

Một lỗi hay gặp là cho rằng sau `%2$s`, chỉ thị `%s` tiếp theo sẽ lấy đối số 3. Thực tế, nó là chỉ thị ngầm định đầu tiên nên vẫn lấy đối số 1.

Java cho phép trộn các cách chọn, nhưng mẫu dài sẽ khó theo dõi. Khi mẫu cần đảo thứ tự hoặc lặp lại nhiều vị trí xa nhau, dùng chỉ số tường minh nhất quán thường giúp việc bảo trì và kiểm tra dễ hơn. `<` hữu ích nhất khi các cách biểu diễn cùng giá trị nằm gần nhau.

## 5. Phần trăm và xuống dòng không tiêu thụ đối số

Hai conversion đặc biệt:

- `%%`: in ký tự `%`.
- `%n`: in dấu xuống dòng của nền tảng.

Chúng không lấy một đối số định dạng mới.

Ví dụ:

```java
System.out.printf(Locale.ROOT, "value: %s %% %<s%n", "X");
```

Dòng được in:

```text
value: X % X
```

`%%` không làm `%<s` quên đối số X vừa được dùng. Tương tự, thêm một `%n` không làm chỉ thị ngầm định tiếp theo tự bỏ qua một đối số.

Cần phân biệt `%%` với một dấu `%` đơn lẻ trong chuỗi mẫu. Dấu `%` bắt đầu chỉ thị định dạng, không phải lúc nào cũng được in nguyên văn.

## 6. Dùng một đối tượng ngày cho nhiều thành phần

Không cần truyền cùng ngày ba lần để in năm, tháng, ngày:

```java
LocalDate date = LocalDate.of(2026, 10, 29);
String text = String.format(
        Locale.ROOT,
        "%1$tY-%<tm-%<td",
        date);
```

Kết quả:

```text
2026-10-29
```

Ở đây:

- `%1$tY` chọn đối số 1, lấy năm.
- `%<tm` tái dùng đối số đó, lấy tháng.
- `%<td` tái dùng đối số đó, lấy ngày trong tháng.

Cũng có thể viết rõ chỉ số ở mọi vị trí:

```java
String text = String.format(
        Locale.ROOT,
        "%1$tY-%1$tm-%1$td",
        date);
```

Hai mẫu biểu đạt cùng việc chọn đối số, chỉ khác mức độ viết tường minh.

`LocalDate` có các trường cần cho năm/tháng/ngày. Không vì có cú pháp chọn đúng đối số mà mọi hậu tố ngày/giờ đều hợp lệ cho đối tượng đó; chẳng hạn đối tượng chỉ có ngày không tự có giờ hay múi giờ.

Dùng `Locale.ROOT` trong ví dụ giúp cách định dạng không phụ thuộc locale mặc định của máy chạy. Việc chọn đối số và việc chọn locale là hai quyết định khác nhau.

## 7. Ví dụ đầy đủ và các lỗi có thể quan sát

Tệp `FormatArgumentIndexDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.time.LocalDate;
import java.util.Formatter;
import java.util.Locale;
import java.util.MissingFormatArgumentException;

public class FormatArgumentIndexDemo {
    public static void main(String[] args) {
        System.out.printf(Locale.ROOT,
                "explicit: %2$s | %1$s | %2$s%n", "A", "B");
        System.out.printf(Locale.ROOT,
                "relative: %1$d | %<04d | %<x%n", 26);
        System.out.printf(Locale.ROOT,
                "mixed: %2$s | %s | %<s | %s | %1$s%n", "A", "B");
        System.out.printf(Locale.ROOT,
                "date: %1$tY-%<tm-%<td%n", LocalDate.of(2026, 10, 29));
        System.out.printf(Locale.ROOT,
                "value: %s %% %<s%n", "X");

        System.out.println("extra: " + String.format(Locale.ROOT, "%s", "A", "B"));

        try {
            System.out.printf(Locale.ROOT, "%2$s", "A");
        } catch (MissingFormatArgumentException expected) {
            System.out.println("missing: " + expected.getFormatSpecifier());
        }

        try (Formatter formatter = new Formatter(Locale.ROOT)) {
            formatter.format("%s", "A");
            try {
                formatter.format("%<s");
            } catch (MissingFormatArgumentException expected) {
                System.out.println("new-call: " + expected.getFormatSpecifier());
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac FormatArgumentIndexDemo.java
java FormatArgumentIndexDemo
```

Kết quả hiển thị theo các dòng:

```text
explicit: B | A | B
relative: 26 | 0026 | 1a
mixed: B | A | A | B | A
date: 2026-10-29
value: X % X
extra: A
missing: %2$s
new-call: %<s
```

`%n` dùng dấu xuống dòng của nền tảng, nên byte kết thúc dòng có thể khác giữa Windows và hệ điều hành khác; nội dung từng dòng ở trên không thay đổi.

Dòng `extra: A` cho thấy đối số B thừa không được dùng để tạo chuỗi đó. Dòng `missing` cho biết mẫu tham chiếu đối số 2 trong khi chỉ có một đối số.

Phần `new-call` kiểm chứng giới hạn của `<`: dù cùng đối tượng `Formatter` vừa định dạng A ở lần gọi trước, lần gọi mới bắt đầu bằng `%<s` vẫn thiếu đối số để tái sử dụng.

## 8. Tái sử dụng chỉ có hiệu lực trong cùng một lần gọi định dạng

Đoạn sau không phải cách dùng lại đối số của lời gọi trước:

```java
// Ví dụ lỗi.
try (Formatter formatter = new Formatter(Locale.ROOT)) {
    formatter.format("%s", "A");
    formatter.format("%<s");
}
```

Lần `format` thứ hai có một danh sách đối số riêng, và không có chỉ thị dùng đối số trước đó trong chính chuỗi mẫu đang xử lý. Vì vậy nó ném `MissingFormatArgumentException`.

Không nhầm việc một `Formatter` có thể tiếp tục ghi vào cùng đích với việc các lần gọi chia sẻ vị trí đối số. Muốn in lại A, truyền lại A ở lần gọi mới hoặc đặt các chỉ thị cần tái dùng vào cùng một lời gọi.

Tương tự, hai lần `printf()` liên tiếp không chia sẻ “đối số trước đó” cho `<`.

## 9. Thiếu đối số, thừa đối số và thiếu kiểu đúng là ba chuyện khác nhau

### Thiếu đối số được tham chiếu

```java
// Ví dụ lỗi: không có đối số thứ hai.
String.format(Locale.ROOT, "%2$s", "A");
```

`MissingFormatArgumentException` cũng có thể xảy ra khi dùng `<` mà chưa có đối số trước để dùng lại. Xem [MissingFormatArgumentException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/MissingFormatArgumentException.html).

Cần đếm **chỉ số được tham chiếu**, không chỉ đếm số ký hiệu `%`:

```text
"%1$s %1$s %1$s" → chỉ cần đối số thứ 1
"%3$s"          → cần có đối số thứ 3
"%% %n"         → không cần đối số định dạng
```

### Thừa đối số

```java
String text = String.format(Locale.ROOT, "%s", "A", "B");
```

Kết quả là A; B không được tham chiếu. `String.format` không mặc định báo lỗi chỉ vì danh sách có thêm đối số không dùng. Xem [String.format](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#format(java.util.Locale,java.lang.String,java.lang.Object...)).

Điều đó có thể che một lỗi sau khi sửa mẫu: chuỗi vẫn tạo được, nhưng một thông tin dự kiến đã biến mất. Nên kiểm tra kết quả mong đợi, không chỉ kiểm tra “không ném ngoại lệ”.

### Đối số tồn tại nhưng sai kiểu

```java
// Ví dụ lỗi: đối số thứ nhất là chuỗi, không phải kiểu phù hợp cho %d.
String.format(Locale.ROOT, "%1$d", "26");
```

Chỉ số đúng không làm chuỗi `"26"` tự được phân tích thành số. Việc chọn đối số và kiểm tra kiểu cho conversion là hai bước khác nhau về ý nghĩa.

## 10. Tái sử dụng đối số không chạy lại biểu thức truyền vào

Xét mã minh họa:

```java
String text = String.format(
        Locale.ROOT,
        "%1$s / %1$s",
        loadDisplayName());
```

Theo cách đánh giá lời gọi phương thức của Java, `loadDisplayName()` được gọi để tạo đối số trước khi formatter xử lý mẫu. Việc tham chiếu `%1$s` hai lần không tự gọi lại biểu thức đó.

Tuy nhiên, cùng một đối tượng được chọn nhiều lần vẫn được định dạng ở từng chỉ thị. Nếu một đối tượng tự cung cấp hành vi định dạng hoặc `toString()` phụ thuộc trạng thái, không nên suy ra mọi lần biểu diễn bắt buộc giống nhau chỉ vì cùng đối số.

Với dữ liệu cần kết quả ổn định, tạo giá trị hiển thị ổn định trước khi định dạng. Không dùng mẫu lặp để dựa vào tác dụng phụ của các lần chuyển thành chuỗi.

## 11. Cách viết mẫu dễ bảo trì

Khi mẫu ngắn và mỗi giá trị xuất hiện một lần, thứ tự ngầm định thường đủ rõ:

```java
String text = String.format(Locale.ROOT, "%s: %d", name, count);
```

Khi nội dung hiển thị cần đổi vị trí theo ngôn ngữ hoặc cần một đối số lặp lại ở nhiều vị trí, dùng chỉ số tường minh:

```java
// Mã minh họa: cùng danh sách (name, count), hai cách sắp xếp.
String first = String.format(Locale.ROOT, "%1$s has %2$d items", name, count);
String second = String.format(Locale.ROOT, "%2$d items belong to %1$s", name, count);
```

Khi cùng giá trị được biểu diễn liên tiếp, `<` giúp giảm lặp chỉ số:

```java
String text = String.format(Locale.ROOT, "%1$d (hex: %<x)", number);
```

Đừng chuyển sang chỉ số ngầm định ở giữa một mẫu dài nếu người đọc phải dò một bộ đếm riêng để hiểu. Mỗi lần sửa mẫu, đối chiếu cả **đối số được chọn** và **conversion của vị trí đó**.

## 12. Tự kiểm tra

Với mỗi chỉ thị:

1. Nó có tiêu thụ đối số không, hay là `%%`/`%n`?
2. Nếu có `n$`, n trỏ đến đối số nào?
3. Nếu có `<`, chỉ thị dùng đối số gần nhất trước đó đã chọn đối số nào?
4. Nếu là ngầm định, đây là lần ngầm định thứ mấy?
5. Kiểu của đối số có hợp conversion không?
6. Có đối số nào vô tình bị bỏ khỏi nội dung sau khi đổi mẫu không?

Bài tập với hai đối số `"A", "B"`:

- `"%2$s %1$s %2$s"` tạo `B A B`.
- `"%2$s %s %s"` tạo `B A B`, vì hai `%s` ngầm định lần lượt chọn A và B.
- `"%1$s %<s %2$s %<s"` tạo `A A B B`.
- `"%<s"` không có đối số trước đó trong cùng lần định dạng để tái dùng, nên báo thiếu đối số.

Điều cần nhớ là **chỉ số chọn dữ liệu; cờ, độ rộng, độ chính xác và conversion quyết định cách biểu diễn dữ liệu đã chọn**.
