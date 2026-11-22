# `System.out.print()`, `println()` và `printf()` trong Java

## 1. Ba cách xuất dữ liệu ra màn hình console

Trong Java, `System.out` là một đối tượng `java.io.PrintStream` đại diện cho **luồng xuất chuẩn** (*standard output*, thường gọi là stdout). Ba nhóm phương thức quen thuộc nhất là:

- **`System.out.print(value)`**: in giá trị nhưng **không chủ động thêm ký tự xuống dòng**.
- **`System.out.println(value)`**: in giá trị rồi **kết thúc dòng**; `println()` không đối số chỉ in một dấu kết thúc dòng, thường dùng tạo dòng trống.
- **`System.out.printf(format, args...)`**: in một chuỗi **theo mẫu định dạng**, sử dụng những ký hiệu như `%s`, `%d`, `%.2f`. `printf()` **không tự thêm dấu kết thúc dòng** nếu chuỗi định dạng không yêu cầu.

Ví dụ đặt trong phương thức:

```java
System.out.print("Xin ");
System.out.print("chao");
System.out.println(" Java");
System.out.println("Dong moi");
System.out.println();
System.out.println("Sau mot dong trong");
```

Kết quả:

```text
Xin chao Java
Dong moi

Sau mot dong trong
```

Hai lần `print` đầu tiên viết tiếp trên **cùng dòng**. `println(" Java")` bổ sung nội dung và kết thúc dòng. `println()` không có đối số tạo một **dòng trống** trước nội dung tiếp theo.

**Đừng nhầm `print()` với `println()`:** `print("A")` không tự xuống dòng, còn `println("A")` có xuống dòng. Tương tự, `printf("A")` không tự thêm xuống dòng.

## 2. `print()`: in tiếp mà không tự xuống dòng

`print` hữu ích để ghép nội dung của một dòng từ nhiều phần nhỏ, chẳng hạn nhãn và giá trị.

```java
int count = 4;
System.out.print("So luong: ");
System.out.print(count);
System.out.println(" san pham");
```

Stdout:

```text
So luong: 4 san pham
```

Nếu chỉ gọi `print` mà không có ký tự xuống dòng trong giá trị truyền vào, lần in tiếp theo sẽ tiếp tục tại dòng hiện tại. Ví dụ `print("A\nB")` **có thể tạo xuống dòng** vì chính chuỗi chứa ký tự `\n`; việc không *tự động* thêm newline không có nghĩa giá trị được in không thể chứa newline.

`print` có các overload cho những kiểu như `boolean`, `char`, `char[]`, `int`, `long`, `float`, `double`, `String` và `Object`. Với giá trị nguyên thủy, Java chuyển thành dạng văn bản phù hợp. Với nhiều đối tượng, việc in sử dụng biểu diễn dạng chuỗi (`String.valueOf`/`toString()`). Cần nhớ `toString()` của đối tượng tự định nghĩa có thể không diễn tả các trường theo cách mình muốn.

Ví dụ:

```java
System.out.print(25);
System.out.print(" tuoi");
System.out.println();
```

Kết quả là một dòng `25 tuoi`.

## 3. `println()`: in và kết thúc dòng

`println` phù hợp với thông báo, ghi giá trị theo từng dòng và in kết quả sau mỗi bước.

```java
System.out.println("Java");
System.out.println(17);
System.out.println(true);
```

Stdout:

```text
Java
17
true
```

`println()` không đối số chỉ kết thúc dòng hiện tại. Khác với một dấu cách, ký tự kết thúc dòng ảnh hưởng cách terminal hiển thị dữ liệu.

### Nối chuỗi bằng toán tử `+`

Khi một toán hạng là `String`, toán tử `+` có thể dùng để nối chuỗi:

```java
int a = 2, b = 3;
System.out.println("Tong: " + (a + b)); // Tong: 5
System.out.println("Ket qua: " + a + b); // Ket qua: 23
System.out.println(a + b + " la tong"); // 5 la tong
```

**Vì sao khác nhau?** Trong `"Ket qua: " + a + b`, phép toán được đánh giá từ trái sang phải: sau khi nối chuỗi với `a`, phép `+ b` tiếp tục nối văn bản. Muốn tính toán trước khi nối, đặt phép tính trong ngoặc `(a + b)`.

### In mảng và đối tượng

```java
int[] numbers = {4, 6};
System.out.println(java.util.Arrays.toString(numbers)); // [4, 6]
```

Với mảng, **đừng kỳ vọng** `System.out.println(numbers)` tự in mọi phần tử. Mảng không ghi đè `toString()` theo dạng danh sách phần tử; kết quả thường có dạng thông tin kiểu và mã định danh, không phải `[4, 6]`. Dùng `Arrays.toString` cho mảng một chiều hoặc `Arrays.deepToString` cho mảng lồng thích hợp.

## 4. `printf()`: in theo mẫu thay vì nối chuỗi thủ công

`printf(format, args...)` nhận chuỗi mẫu có các ký hiệu bắt đầu bằng `%` và những đối số tương ứng. Ví dụ `System.out.printf("Ten: %s; Tuoi: %d%n", "An", 18);` in `Ten: An; Tuoi: 18` rồi xuống dòng. Khác `println()`, `printf()` **không tự thêm** ký tự kết thúc dòng.

| Ký hiệu | Ý nghĩa trong ví dụ cơ bản |
| --- | --- |
| `%s` / `%d` | Văn bản / số nguyên thập phân |
| `%.2f` | Số thực với hai chữ số thập phân |
| `%04d` / `%-6s` | Đệm số bằng 0 đến độ rộng 4 / căn trái chuỗi trong vùng rộng 6 |
| `%%` / `%n` | Một dấu phần trăm / ký tự kết thúc dòng của nền tảng |

Định dạng số thực chịu ảnh hưởng của `Locale`. Các cờ, độ rộng, precision, chỉ số đối số và ngoại lệ của `Formatter` được thực hành chi tiết ở bài về định dạng `printf()`; ví dụ chạy độc lập ngay dưới đây minh họa sự khác biệt giữa ba phương thức in.

## 5. Chọn `Locale` để đầu ra có thể đối chiếu

`System.out.printf(Locale.US, "Gia: %.2f%n", 12.5);` in `Gia: 12.50` rồi kết thúc dòng. Nếu bỏ `Locale.US`, dấu thập phân của `%.2f` có thể theo locale mặc định và khác giữa các máy. Chọn locale phù hợp với người đọc hoặc định dạng trao đổi; `Locale.US` chỉ cố định ví dụ đang dùng dấu chấm.

`%n` yêu cầu dấu kết thúc dòng của nền tảng, còn escape `\n` trong Java string biểu diễn ký tự LF. Bài định dạng `printf()` giải thích thêm sự khác biệt này khi chạy đa hệ điều hành.

## 6. Ví dụ Java 17+ chạy độc lập và kết quả chính xác

Tạo tệp **`ConsoleOutputDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;

public class ConsoleOutputDemo {
    public static void main(String[] args) {
        System.out.print("Xin ");
        System.out.print("chao");
        System.out.println(" Java");
        System.out.println("Dong trong");
        System.out.println();

        System.out.println(2 + 3);
        System.out.println("Tong: " + (2 + 3));

        System.out.printf(Locale.US, "So luong: %d%n", 7);
        System.out.printf(Locale.US, "Gia: %.2f%n", 12.5);
        System.out.printf(Locale.US, "Bang: |%-6s|%04d|%n", "A", 9);
        System.out.printf(Locale.US, "Ty le: %.1f%%%n", 87.4);
        System.out.printf(Locale.US, "Hex: %x, ky tu: %c, dung: %b%n",
                          255, 'Z', true);

        String saved = String.format(Locale.US, "Ma=%03d", 5);
        System.out.println("Chuoi: " + saved);

        int[] values = {4, 6};
        System.out.println("Mang: " + Arrays.toString(values));
    }
}
```

Mở terminal tại thư mục chứa tệp, dùng **JDK 17 trở lên** trên Windows (PowerShell/CMD) hoặc Linux/macOS:

```bash
javac -encoding UTF-8 ConsoleOutputDemo.java
java ConsoleOutputDemo
```

Stdout chính xác (có **một dòng trống** sau `Dong trong`; lệnh `javac` thành công không in gì):

```text
Xin chao Java
Dong trong

5
Tong: 5
So luong: 7
Gia: 12.50
Bang: |A     |0009|
Ty le: 87.4%
Hex: ff, ky tu: Z, dung: true
Chuoi: Ma=005
Mang: [4, 6]
```

Phân tích:

1. Hai `print()` đầu nối tiếp trên cùng dòng; `println(" Java")` kết thúc dòng ấy.
2. `println()` không đối số tạo dòng trắng.
3. `println(2 + 3)` in kết quả phép cộng số học là `5`.
4. `printf` xuất đúng kiểu và độ rộng của `%d`, `%.2f`, `%-6s`, `%04d`, `%.1f`, `%x`, `%c`, `%b`; `%%` là dấu phần trăm.
5. `String.format` **trả về `String`**, không tự in; sau đó `println` mới ghi chuỗi ấy ra console.
6. `Arrays.toString` biến nội dung mảng thành chuỗi dễ đọc.

## 7. Khi `printf()` báo lỗi hoặc dính dòng

Các định dạng sai có thể **biên dịch được nhưng ném ngoại lệ lúc chạy**: `printf("%d", "7")` dùng `String` thay cho số nguyên và gây `IllegalFormatConversionException`; `printf("%d %s", 3)` thiếu một đối số và gây `MissingFormatArgumentException`.

`%f` không tự chuyển `String` thành số thực; khi cần, hãy parse và validate dữ liệu trước. `printf("Ti le: %d%%%n", 80);` in `Ti le: 80%` rồi xuống dòng: `%%` in phần trăm, `%n` kết thúc dòng. Đừng viết một dấu `%` trần trong mẫu, và đừng trông chờ `printf()` tự xuống dòng. Bài định dạng chuyên sâu có bảng đầy đủ các lỗi về conversion, flag và precision.

## 8. Khi nào nên chọn phương thức nào?

| Nhu cầu | Phương thức phù hợp |
| --- | --- |
| In một thông báo đơn giản và xuống dòng | `println("Da xong")` |
| In nhiều phần của cùng một dòng | `print(...)`, rồi `println(...)` khi muốn kết thúc |
| In nhiều giá trị cần độ rộng, số chữ số thập phân, padding | `printf(...)` |
| Tạo chuỗi được định dạng để lưu hoặc trả về, **không in ngay** | `String.format(...)` |
| Xuất lỗi/chẩn đoán riêng luồng stdout | `System.err.println(...)` nếu phù hợp |

`System.out` là **standard output**; `System.err` là **standard error**, thường dùng cho thông báo lỗi. Terminal có thể hiển thị cả hai trên cùng màn hình, nhưng chúng là hai luồng riêng và có thể được chuyển hướng riêng.

Ví dụ:

```bash
java ConsoleOutputDemo > output.txt
```

Lệnh này chuyển hướng stdout vào tệp `output.txt` theo cú pháp shell thường gặp. Cách mã hóa tệp từ việc chuyển hướng có thể khác theo môi trường shell; khi ứng dụng cần định dạng/ký tự đầu ra chuẩn xác trong tệp, nên dùng API ghi file với charset rõ ràng thay vì phụ thuộc ngầm vào cấu hình terminal.

## 9. Kiểm tra nhanh trước khi chạy

- Nếu các phần bị dính nhau: xem có dùng nhầm `print` thay vì `println` hoặc quên `%n` trong `printf` không.
- Nếu kết quả toán học bị nối thành chuỗi: thêm ngoặc quanh phép tính trước khi dùng `+` với `String`.
- Nếu hiển thị số thập phân không như mong muốn: kiểm tra `%.nf`, kiểu đối số và `Locale`.
- Nếu định dạng ném ngoại lệ: so khớp từng ký hiệu `%d`, `%f`, `%s` với số lượng và kiểu đối số thực tế.
- Nếu mảng in ra dạng khó đọc: dùng `Arrays.toString` hoặc `Arrays.deepToString` khi phù hợp.
- Nếu thấy thông báo lỗi cùng chỗ với kết quả: nhớ phân biệt `System.err` và `System.out`; các luồng có thể được hiển thị cùng một terminal.

**Ghi nhớ:** `print` in tiếp, `println` in rồi xuống dòng, còn `printf` in theo mẫu và chỉ xuống dòng khi mẫu có ký tự kết thúc dòng. Chọn đúng phương thức giúp kết quả console dễ đọc và có thể kiểm tra chính xác.