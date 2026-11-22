# `%%` và `%n` khi định dạng chuỗi trong Java

## Mục tiêu

Khi sử dụng `String.format(... )`, `String.formatted(... )` hoặc `System.out.printf(... )`, bạn cần biết cách in dấu phần trăm thật và xuống dòng đúng nền tảng:

- `%%` biểu diễn **một dấu `%` trong kết quả**.
- `%n` biểu diễn **một ký tự hoặc chuỗi ký tự kết thúc dòng theo hệ điều hành**.
- Cả hai đều là **conversion đặc biệt của `java.util.Formatter`** và **không tiêu thụ đối số** trong danh sách tham số định dạng.

Hai ký hiệu này chỉ được diễn giải khi chuỗi đóng vai trò **format string**. Chúng không phải cú pháp đặc biệt của mọi đối tượng `String`.

## 1. Vì sao có hai ký hiệu này?

Trong họ API dựa trên `Formatter`, dấu `%` thông thường mở đầu một chỉ thị định dạng: `%s` để chèn chuỗi, `%d` để chèn số nguyên, `%.2f` để định dạng số thực với hai chữ số thập phân. Vì dấu `%` đã có ý nghĩa điều khiển, muốn hiển thị nó theo nghĩa thông thường cần viết `%%`.

Tương tự, `%n` yêu cầu bộ định dạng thêm dấu kết thúc dòng thích hợp với môi trường thực thi, tiện cho việc tạo báo cáo nhiều dòng và in ra console.

| Mẫu trong format string | Ý nghĩa | Đối số cần cung cấp |
| --- | --- | --- |
| `%%` | Ghi ra một dấu `%` | Không |
| `%n` | Ghi ra dấu kết thúc dòng theo nền tảng | Không |
| `%d` | Chèn một số nguyên | Có |
| `%s` | Chèn biểu diễn chuỗi của một giá trị | Có |

Ví dụ: chuỗi mẫu `"Tiến độ: %d%%%n"` được đọc thành `%d` (giá trị số), `%%` (dấu phần trăm) và `%n` (kết thúc dòng). Ba dấu `%` liên tiếp trước chữ `n` ở đây là đúng cú pháp: hai dấu đầu thuộc `%%`, dấu thứ ba bắt đầu `%n`.

## 2. `%%` — in dấu phần trăm

Với `Formatter`, `%%` cho ra đúng một dấu `%`:

```java
String result = String.format("Đã xử lý 100%%");
System.out.println(result);
```

Kết quả:

```text
Đã xử lý 100%
```

Muốn ghép số phần trăm động, hãy đặt `%%` sau chỉ thị của số:

```java
int progress = 75;
System.out.printf("Tiến độ: %d%%%n", progress);
```

Kết quả là dòng `Tiến độ: 75%` rồi xuống dòng. `%d` lấy đối số `progress`, còn `%%` không lấy đối số nào. Nếu chỉ muốn chuỗi kết quả mà chưa in ra màn hình, dùng `String.format("Tiến độ: %d%%", progress)`.

**Phân biệt với chuỗi bình thường:** `System.out.print("50%%")` in nguyên hai dấu `%%`, vì `print` không phân tích format string. Trái lại, `System.out.printf("50%%")` in `50%`.

Đặc biệt, dấu `%` đơn lẻ trong format string thường gây lỗi định dạng vì `Formatter` đang chờ tên phép chuyển đổi tiếp theo. Cách viết `"100%"` vẫn hoàn toàn hợp lệ nếu chỉ đưa vào `print`/`println` như văn bản thuần.

## 3. `%n` — kết thúc dòng theo nền tảng

`%n` không in hai ký tự `%` và `n`. Trong một format string, nó tạo dấu kết thúc dòng giống giá trị do `System.lineSeparator()` cung cấp tại môi trường chạy. Thông thường, Unix/Linux/macOS dùng LF (`\n`); Windows dùng CRLF (`\r\n`).

```java
String report = String.format("Dòng thứ nhất%nDòng thứ hai");
System.out.print(report);
```

Kết quả hiển thị:

```text
Dòng thứ nhất
Dòng thứ hai
```

Có thể dùng nhiều `%n` liên tiếp khi **chủ ý** tạo dòng trống:

```java
System.out.printf("Mục A%n%nMục B%n");
```

Kết quả:

```text
Mục A

Mục B
```

**So sánh với `\n` và `println`:**

- `\n` là escape sequence của *Java string literal*: trình biên dịch Java biến nó thành ký tự xuống dòng LF. Nó được hiểu ngay cả khi không dùng `Formatter`.
- `%n` là chỉ thị của *format string*: chỉ được biến thành kết thúc dòng khi đi qua `Formatter`, thường là lựa chọn tốt cho định dạng văn bản theo nền tảng.
- `println(... )` tự thêm kết thúc dòng sau giá trị được in. Nếu giá trị đã kết thúc bằng `%n` qua `String.format` rồi lại gọi `println`, sẽ có thêm một dòng trống ngoài ý muốn.
- `System.out.print("%n")` in nguyên văn `%n`. Muốn nó xuống dòng, gọi `System.out.printf("%n")` hoặc dùng `println()`.

Không nên giả định kết quả `%n` luôn có đúng một ký tự: trên Windows dấu kết thúc dòng thường gồm hai ký tự `\r\n`. Điều này quan trọng nếu bạn so sánh chuỗi theo byte hoặc kiểm thử văn bản đa nền tảng.

## 4. Ví dụ Java 17+ chạy hoàn chỉnh

Tạo tệp `FormatTokensDemo.java`:

```java
public class FormatTokensDemo {
    public static void main(String[] args) {
        int completed = 7;
        int total = 10;
        int percentage = completed * 100 / total;

        // %d nhận số; %% in dấu %; %n kết thúc dòng.
        System.out.printf(
                "Hoàn thành: %d/%d (%d%%)%n",
                completed, total, percentage
        );

        // String.format tạo chuỗi; println thêm xuống dòng cuối cùng.
        String report = String.format(
                "Giảm giá: 15%%%nĐơn hàng đã ghi nhận"
        );
        System.out.println(report);

        // print không diễn giải %% hoặc %n.
        System.out.print("print thông thường: 50%% và %n");
        System.out.println();
    }
}
```

Biên dịch và chạy:

```bash
javac FormatTokensDemo.java
java FormatTokensDemo
```

Kết quả hiển thị (các dòng như nhau trên mọi nền tảng; byte kết thúc dòng có thể khác):

```text
Hoàn thành: 7/10 (70%)
Giảm giá: 15%
Đơn hàng đã ghi nhận
print thông thường: 50%% và %n
```

Giải thích: biểu thức `completed * 100 / total` cho `70` bằng phép tính số nguyên; `%d` đưa số đó vào chuỗi. Cặp `%%` sau `%d` tạo dấu phần trăm, `%n` khép dòng. Trong `report`, `15%%%n` tương ứng `15%` rồi xuống dòng trước câu tiếp theo. `print` ở cuối chỉ xuất các ký tự theo đúng giá trị chuỗi truyền vào.

Khi đã có sẵn format string trong biến, bạn cũng có thể gọi `template.formatted(args)` (Java 15+); ký hiệu `%%` và `%n` vẫn có cùng ý nghĩa vì phương thức này dùng cơ chế định dạng kiểu `String.format`.

## 5. Quy tắc kết hợp và những nhầm lẫn thường gặp

| Mong muốn | Mẫu khi dùng `printf`/`String.format` | Kết quả |
| --- | --- | --- |
| In `100%` | `"100%%"` | `100%` |
| In `80%` từ số nguyên 80 | `"%d%%"` và đối số `80` | `80%` |
| In `80%` rồi kết thúc dòng | `"%d%%%n"` và đối số `80` | `80%` rồi xuống dòng |
| In hai dòng | `"A%nB"` | `A` và `B` trên hai dòng |
| In chữ `%n` theo nghĩa đen qua Formatter | `"%%n"` | `%n` |

Một số lỗi cần tránh:

1. **Thiếu dấu `%` thứ hai:** `System.out.printf("Hoàn thành 100%")` có format string không hợp lệ; phải dùng `"Hoàn thành 100%%"`. Khi chỉ in văn bản cố định, `System.out.println("Hoàn thành 100%")` cũng đúng.
2. **Nhầm với escape của Java:** `\%` không phải escape sequence hợp lệ trong Java string literal. Không dùng `"100\%"` để xử lý dấu phần trăm.
3. **Quên ngữ cảnh định dạng:** `"A%nB"` truyền trực tiếp vào `print` vẫn chứa ký tự `%n`. Chỉ truyền qua `printf`, `format` hoặc `formatted` mới diễn giải nó.
4. **Chèn xuống dòng hai lần:** `System.out.println(String.format("X%n"))` tạo một xuống dòng từ `%n` và một xuống dòng nữa từ `println`. Hãy chọn một trong hai khi chỉ muốn kết thúc một dòng.
5. **Gắn tùy chọn định dạng vào `%n`:** `%n` không nhận flags, width hay precision. Với `%%`, có thể chỉ định width và flag căn trái `-` (ví dụ `%5%` in dấu `%` trong ô rộng 5 ký tự), nhưng không dùng precision như định dạng số hoặc chuỗi.
6. **Cấp nhầm đối số:** `%%` và `%n` không lấy phần tử nào trong danh sách đối số; chỉ `%d`, `%s`… mới sử dụng đối số tương ứng. Ví dụ, `String.format("%s: 100%%%n", "Tải xuống")` chỉ cần một đối số là `"Tải xuống"`.

## 6. Tự kiểm tra

**Câu 1.** Đoạn mã sau hiển thị gì?

```java
System.out.printf("CPU: %d%%%n", 80);
```

Đáp án: in `CPU: 80%` rồi kết thúc dòng. `%d` nhận `80`; `%%` in dấu phần trăm; `%n` xuống dòng.

**Câu 2.** Vì sao hai lời gọi dưới đây cho kết quả khác nhau?

```java
System.out.print("X%nY");
System.out.printf("X%nY");
```

Đáp án: `print` hiển thị nguyên văn `X%nY`; `printf` diễn giải `%n` và hiển thị `X`, `Y` trên hai dòng. Do lời gọi `print` không tự xuống dòng, nếu chạy liên tiếp như trên thì ký tự `X` của `printf` nối ngay sau chữ `Y` đã được `print` in ra.

## Ghi nhớ

Trong **format string**, dùng `%%` để tạo dấu phần trăm hiển thị và `%n` để tạo dấu kết thúc dòng tương thích nền tảng. Chúng không chiếm đối số định dạng. Trong chuỗi được đưa thẳng tới `print`/`println`, hai ký hiệu giữ nguyên vì không có bước phân tích định dạng.
