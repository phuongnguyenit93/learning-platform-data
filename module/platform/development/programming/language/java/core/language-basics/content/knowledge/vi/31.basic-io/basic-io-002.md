# Định dạng số, chuỗi, xuống dòng và ký hiệu % trong `printf()` (Java 17+)

## 1. `printf()` dùng để làm gì?

Trong Java, `System.out.printf(...)` ghi văn bản đã định dạng ra luồng chuẩn `stdout`. Thay vì tự nối nhiều chuỗi, ta viết **format string** chứa các chỉ thị bắt đầu bằng `%`, rồi đưa các giá trị tương ứng vào.

```java
System.out.printf("Name: %s, age: %d%n", "An", 20);
```

Dòng in ra là `Name: An, age: 20` rồi xuống dòng. `%s` định dạng chuỗi hoặc đối tượng, `%d` định dạng số nguyên hệ thập phân, còn `%n` là dấu xuống dòng phụ thuộc nền tảng.

So sánh các phương thức:

| Phương thức | Vai trò | Tự thêm xuống dòng? |
| --- | --- | --- |
| `System.out.print(value)` | In giá trị trực tiếp | Không |
| `System.out.println(value)` | In giá trị rồi xuống dòng | Có |
| `System.out.printf(format, args...)` | In theo mẫu với các conversion/flags/width/precision | **Không**, trừ khi mẫu có `%n` hay ký tự xuống dòng |
| `String.format(format, args...)` | Tạo và **trả về** chuỗi đã định dạng để dùng tiếp | Không tự in ra console |

`printf()` trả về chính `PrintStream` để có thể gọi nối tiếp; trong bài nhập xuất cơ bản, thông thường chỉ cần quan tâm nội dung nó in ra.

## 2. Cấu trúc một chỉ thị định dạng

Dạng tổng quát phổ biến:

```text
%[argument_index$][flags][width][.precision]conversion
```

Các phần trong ngoặc vuông là tùy chọn; đây là mô tả cú pháp, không phải biểu thức Java để dán và chạy.

- `argument_index$`: lấy tham số ở vị trí cụ thể, đếm từ 1. Ví dụ `%2$s` chọn đối số thứ hai và định dạng bằng `%s`.
- `flags`: quy định căn lề, dấu, thêm số 0, phân nhóm chữ số... Một số cờ chỉ hợp lệ với những loại chuyển đổi nhất định.
- `width`: **độ rộng tối thiểu** của vùng hiển thị, tính bằng ký tự theo quy tắc Formatter. Nếu giá trị dài hơn, nó không tự bị cắt.
- `.precision`: ý nghĩa tùy loại: `%.2f` là hai chữ số sau dấu thập phân; `%.4s` giữ tối đa bốn ký tự trong chuỗi theo cách Formatter xử lý.
- `conversion`: ký hiệu loại giá trị cần in: `d`, `f`, `s`, `x`, `c`, v.v.

Ví dụ `%8.2f`: in số thực với hai chữ số thập phân, vùng rộng tối thiểu tám ký tự và căn phải theo mặc định. `%-8.2f`: cùng độ rộng nhưng căn trái. `%08.2f`: đệm bằng `0` ở phía trái (khi cờ `0` hợp lệ cho loại định dạng đó).

## 3. Các ký hiệu cơ bản cần nhớ

| Ký hiệu | Dùng với | Ví dụ giá trị | Kết quả |
| --- | --- | --- | --- |
| `%d` | Số nguyên thập phân (`byte`, `short`, `int`, `long`, `BigInteger` tương thích) | `42` | `42` |
| `%x` / `%X` | Số nguyên dạng hệ 16, chữ thường/chữ hoa | `26` | `1a` / `1A` |
| `%o` | Số nguyên dạng hệ 8 | `26` | `32` |
| `%f` | Số thực dạng thập phân (`float`, `double`, `BigDecimal`) | `12.5` | `12.500000` khi dùng `Locale.ROOT` |
| `%.2f` | Số thực, hai chữ số sau dấu thập phân | `12.5` | `12.50` |
| `%e` | Số thực dạng khoa học | `12.5` | `1.250000e+01` |
| `%s` | Chuỗi/đối tượng; dùng cách biểu diễn chuỗi thích hợp | `"Java"` | `Java` |
| `%S` | Chuỗi dạng chữ hoa theo locale thích hợp | `"java"` | `JAVA` |
| `%c` | Ký tự hoặc mã Unicode hợp lệ ở dạng số nguyên phù hợp | `'A'` | `A` |
| `%b` | Giá trị boolean hoặc các đối tượng khác | `true` | `true` |
| `%%` | Dấu phần trăm **nguyên văn** | Không cần tham số | `%` |
| `%n` | Dấu xuống dòng theo hệ điều hành | Không cần tham số | Xuống dòng |

**Lưu ý kiểu:** `%d` không tự chuyển chuỗi `"42"` thành số, và `%f` không tự chấp nhận mọi kiểu số nguyên. Đặt đúng loại dữ liệu tương ứng. Nếu muốn in một `int` dưới dạng số thực hai chữ số thập phân, chuyển đổi có chủ đích, ví dụ `System.out.printf("%.2f%n", (double) 42);`.

Với `%b`, kiểu `Boolean` dùng giá trị `true/false`, tham số `null` cho `false`, và đối tượng không phải `Boolean` khác `null` có thể được in thành `true`. Vì thế `%b` **không** có nghĩa Java tự biến mọi dữ liệu thành phép kiểm tra đúng/sai theo ý nghiệp vụ.

## 4. Ví dụ chạy được: số, chuỗi và dấu %

Tạo **`PrintfDemo.java`**:

```java
import java.util.Locale;

public class PrintfDemo {
    public static void main(String[] args) {
        System.out.printf(Locale.ROOT,
                "so=%d, hex=%x, oct=%o%n", 26, 26, 26);
        System.out.printf(Locale.ROOT,
                "thap-phan=%.2f, khoa-hoc=%.2e%n", 12.5, 12.5);
        System.out.printf(Locale.ROOT,
                "can-phai=[%6d], can-trai=[%-6d]%n", 42, 42);
        System.out.printf(Locale.ROOT,
                "them-zero=[%05d], them-dau=[%+d]%n", 42, 42);
        System.out.printf(Locale.ROOT,
                "nhom=[%,d]%n", 1234567);
        System.out.printf(Locale.ROOT,
                "chuoi=[%s], rut-gon=[%.4s], viet-hoa=[%S]%n",
                "Java", "language", "java");
        System.out.printf(Locale.ROOT,
                "ti-le=%.1f%%%n", 12.5);
        System.out.printf(Locale.ROOT,
                "doi-cho: %2$s (%1$d)%n", 7, "items");
    }
}
```

Tại thư mục chứa tệp, dùng **JDK 17+** (PowerShell, CMD hoặc bash). Tạo thư mục `out` nếu chưa có:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out PrintfDemo.java
java -cp out PrintfDemo
```

**Stdout chính xác** (các khoảng trắng trong dấu ngoặc vuông là thành phần có chủ đích của output):

```text
so=26, hex=1a, oct=32
thap-phan=12.50, khoa-hoc=1.25e+01
can-phai=[    42], can-trai=[42    ]
them-zero=[00042], them-dau=[+42]
nhom=[1,234,567]
chuoi=[Java], rut-gon=[lang], viet-hoa=[JAVA]
ti-le=12.5%
doi-cho: items (7)
```

Giải thích:

1. `%d`, `%x`, `%o` cùng nhận giá trị `26` nhưng thể hiện lần lượt theo hệ 10, 16, 8.
2. `%.2f` giữ hai chữ số sau dấu thập phân; `%.2e` dùng dạng khoa học với hai chữ số sau dấu thập phân của phần định trị.
3. `%6d` tạo vùng rộng ít nhất sáu ký tự cho `42`: bốn khoảng trắng ở **trước**. `%-6d` thêm bốn khoảng trắng ở **sau**.
4. `%05d` thêm số 0 để đạt độ rộng năm; `%+d` hiển thị `+` cho số dương. `%,d` bật phân nhóm hàng nghìn theo `Locale.ROOT`.
5. `%.4s` rút `language` thành `lang`; `%S` in `java` thành `JAVA`.
6. `%.1f%%%n` gồm **ba chỉ thị theo thứ tự**: `%.1f` tiêu thụ `12.5`, `%%` in một dấu `%`, `%n` xuống dòng. Chúng không phải một chỉ thị `%%%`.
7. `%2$s` lấy đối số thứ hai (`"items"`), `%1$d` lấy đối số thứ nhất (`7`). Đây là **chỉ số đối số từ 1**, khác chỉ số mảng Java từ 0.

Việc chỉ định `Locale.ROOT` giúp các ví dụ trên có dấu thập phân `.` và quy tắc phân nhóm nhất quán. Nếu không truyền locale, `printf()` sử dụng locale mặc định của môi trường Java, có thể hiển thị `,` làm dấu thập phân ở một số nơi.

## 5. `%n`, `\n`, `print()` và `println()`

Một điểm quan trọng: **`printf()` không tự xuống dòng** sau khi in. Hãy thêm `%n` vào format string khi muốn kết thúc dòng.

- `%n` là một **conversion của Formatter**, đại diện dấu kết thúc dòng theo nền tảng (`System.lineSeparator()` về mặt ý nghĩa sử dụng).
- `\n` là **ký tự escape trong Java string literal**, biểu thị ký tự LF. Trên Windows, dấu kết thúc dòng của nền tảng thường là CRLF, vì thế `%n` và `\n` không nhất thiết cho cùng các byte.
- `println()` tự thêm dấu kết thúc dòng theo `PrintStream`; `print()` thì không.
- Trong một format string, `%%` và `%n` đều **không tiêu thụ tham số**.

Tạo **`NewlineDemo.java`**:

```java
public class NewlineDemo {
    public static void main(String[] args) {
        System.out.print("A");
        System.out.println("B");
        System.out.printf("C%n");
        System.out.print("D\nE\n");
        System.out.printf("progress=100%%%n");
    }
}
```

Biên dịch và chạy:

```sh
javac -encoding UTF-8 --release 17 -d out NewlineDemo.java
java -cp out NewlineDemo
```

**Nội dung stdout theo từng dòng, chính xác** (ký tự kết thúc dòng có thể là LF hoặc CRLF tùy nền tảng):

```text
AB
C
D
E
progress=100%
```

`print("A")` chưa xuống dòng, nên `println("B")` ghép `B` ngay sau `A`. Với `System.out.printf("C%n")`, phải có `%n` thì `D` mới bắt đầu ở dòng mới. `"D\nE\n"` chứa hai ký tự LF do escape `\n`. `"progress=100%%%n"` gồm văn bản `100`, chỉ thị `%%` in một dấu `%`, rồi `%n` kết thúc dòng.

**Lỗi thường gặp:** viết `System.out.printf("100% done%n");` sẽ để một dấu `%` trần mở đầu chỉ thị định dạng không hợp lệ. Sửa thành `System.out.printf("100%% done%n");`, hoặc dùng `println("100% done")` nếu không cần Formatter.

## 6. Độ rộng, căn lề và độ chính xác

### Độ rộng tối thiểu

Với chuỗi `"Cat"`:

```java
System.out.printf("[%8s]%n", "Cat");
System.out.printf("[%-8s]%n", "Cat");
```

Output:

```text
[     Cat]
[Cat     ]
```

Trong `%8s`, `Cat` dài ba ký tự nên có năm dấu cách ở trước; `%-8s` có năm dấu cách ở sau. `width` không giới hạn độ dài tối đa: nếu chuỗi dài hơn tám ký tự, Formatter vẫn in toàn bộ (trừ khi dùng precision để giới hạn).

### Độ chính xác của số thực và chuỗi

```java
System.out.printf(java.util.Locale.ROOT, "[%8.2f]%n", 12.5);
System.out.printf(java.util.Locale.ROOT, "[%.3s]%n", "abcdef");
```

Output:

```text
[   12.50]
[abc]
```

`%8.2f` tạo `12.50` dài năm ký tự, nên được thêm ba dấu cách bên trái. `%.3s` giữ tối đa ba ký tự trong `abcdef`.

Với `%f`, precision kiểm soát số chữ số phần thập phân và có thể cần làm tròn. Nếu muốn biểu diễn **tiền tệ chính xác**, nên dùng `BigDecimal` với quy tắc làm tròn nghiệp vụ rõ ràng, không mặc định rằng `double` có thể biểu diễn chính xác mọi số thập phân.

### Các cờ định dạng thông dụng

| Cờ | Ví dụ | Kết quả với `Locale.ROOT` | Ghi chú |
| --- | --- | --- | --- |
| `-` | `%-6d`, số `42` | `42    ` | Căn trái trong vùng rộng sáu |
| `+` | `%+d`, số `42` | `+42` | Luôn thể hiện dấu số |
| `0` | `%05d`, số `42` | `00042` | Đệm bằng chữ số 0, không phải khoảng trắng |
| `,` | `%,d`, số `1234567` | `1,234,567` | Phân nhóm chữ số theo locale |
| `(` | `%(d`, số `-42` | `(42)` | Dùng ngoặc cho giá trị âm |
| `#` | `%#x`, số `26` | `0x1a` | Dạng thay thế, ý nghĩa tùy conversion |

Không thể dùng mọi cờ với mọi conversion. Ví dụ cờ `0` dùng được với nhiều định dạng số, nhưng không hợp lệ với `%s` thông thường.

## 7. `Locale` quyết định cách hiện số

Khi dùng `System.out.printf("%.2f%n", 1234.5)`, kết quả phụ thuộc locale mặc định. Để chỉ định rõ cách hiển thị:

```java
import java.util.Locale;

public class LocaleDemo {
    public static void main(String[] args) {
        System.out.printf(Locale.US, "US=[%,.2f]%n", 1234.5);
        System.out.printf(Locale.GERMANY, "DE=[%,.2f]%n", 1234.5);
    }
}
```

Biên dịch và chạy:

```sh
javac -encoding UTF-8 --release 17 -d out LocaleDemo.java
java -cp out LocaleDemo
```

Stdout:

```text
US=[1,234.50]
DE=[1.234,50]
```

Trong `Locale.US`, dấu phẩy dùng để phân nhóm, dấu chấm phân tách phần thập phân. Trong `Locale.GERMANY`, hai dấu này đổi vai trò. Khi format để **người dùng đọc**, chọn locale theo người dùng; khi cần output học tập hoặc máy xử lý có tính ổn định, chọn locale thích hợp một cách tường minh.

`Locale.ROOT` được dùng trong ví dụ chính để tránh phụ thuộc thiết lập hệ thống; nó không có nghĩa mọi quốc gia đều dùng cùng quy ước.

## 8. Dùng `String.format()` khi cần giữ kết quả

`System.out.printf(...)` in ngay ra stdout. Nếu cần lắp chuỗi trước, dùng `String.format(Locale, format, args...)`:

```java
import java.util.Locale;

public class FormatStringDemo {
    public static void main(String[] args) {
        String label = String.format(Locale.ROOT, "ID=%03d; value=%.1f%%", 7, 12.5);
        System.out.println(label);
    }
}
```

Biên dịch và chạy:

```sh
javac -encoding UTF-8 --release 17 -d out FormatStringDemo.java
java -cp out FormatStringDemo
```

Output:

```text
ID=007; value=12.5%
```

`%03d` in `7` với độ rộng ba và hai số 0 ở trước. `%.1f%%` in `12.5%` trong `Locale.ROOT`. Dấu `%` trong chuỗi format vẫn phải được escape thành `%%` dù ta dùng `String.format` thay vì `printf`.

## 9. Lỗi thường gặp và cách khắc phục

Các lỗi định dạng chủ yếu là **ngoại lệ khi chạy** thuộc nhóm `java.util.IllegalFormatException`, không nhất thiết bị `javac` phát hiện:

| Sai lầm | Hậu quả có thể gặp | Cách sửa |
| --- | --- | --- |
| `printf("%d", "42")` | `IllegalFormatConversionException` vì `String` không phù hợp `%d` | Parse thành số nguyên hoặc dùng `%s` |
| `printf("%f", 42)` | Kiểu `Integer` không phù hợp `%f` | Dùng `42.0`, `(double) 42` hoặc `%d` |
| `printf("%s %d", "An")` | `MissingFormatArgumentException` do thiếu đối số cho `%d` | Cung cấp đủ đối số |
| `printf("%.2d", 7)` | `IllegalFormatPrecisionException` | Với số nguyên, dùng width hoặc cờ `0`, như `%03d` |
| `printf("rate=10%")` | Dấu `%` đơn lẻ tạo format sai | `printf("rate=10%%")` |
| `printf("%05s", "A")` | Cờ `0` không phù hợp `%s` | Dùng `%5s` hoặc `%-5s` |
| Thiếu `%n` cuối định dạng | Các lần in nối cùng một dòng | Thêm `%n` hoặc dùng `println` |
| Output khác dấu thập phân mong đợi | Locale mặc định khác | Truyền `Locale.ROOT`, `Locale.US` hoặc locale đích |

Không phải mọi chuỗi bắt đầu bằng `%` đều cần đối số. `%%` in dấu `%` và `%n` xuống dòng **không chiếm vị trí đối số**. Nếu muốn hiển thị một định dạng giống `%d` nguyên văn, hãy viết `%%d` trong format string.

Ngoài ra:

- Thứ tự đối số quan trọng: `printf("%s: %d", name, age)` khác `printf("%s: %d", age, name)` và lời gọi sau có thể sai kiểu.
- `%d` in giá trị số nguyên theo quy tắc định dạng, không thêm đơn vị. Với tiền hoặc tỉ lệ phần trăm, hãy ghi đơn vị rõ ràng.
- `%f` mặc định sáu chữ số sau dấu thập phân. Đừng nhầm **precision** với **width**.
- `%s` là lựa chọn đơn giản khi cần thể hiện nhiều loại đối tượng, nhưng biểu diễn phụ thuộc `toString()` hoặc cách định dạng tương ứng; không tự coi nó là dạng có thể parse ngược cho mọi đối tượng.
- Độ rộng và precision không phải công cụ chuẩn hóa bảng Unicode khi có emoji, dấu kết hợp hoặc ký tự có độ rộng hiển thị khác một cột terminal. Với bảng căn cột, nên kiểm tra trên terminal thực tế.

## 10. Bài luyện tập có đáp án

**Bài 1.** In số `5` dưới dạng `005` rồi xuống dòng.

```java
System.out.printf("%03d%n", 5);
```

Kết quả: `005` trên một dòng.

**Bài 2.** In số `7.5` với hai chữ số sau dấu thập phân và một dấu phần trăm.

```java
System.out.printf(java.util.Locale.ROOT, "%.2f%%%n", 7.5);
```

Kết quả: `7.50%` rồi xuống dòng.

**Bài 3.** Căn trái chuỗi `"Hi"` trong vùng sáu ký tự, có ngoặc vuông để nhìn thấy dấu cách.

```java
System.out.printf("[%-6s]%n", "Hi");
```

Kết quả: `[Hi    ]`.

**Bài 4.** In lần lượt `"second"` và `"first"` khi đối số truyền vào theo thứ tự `"first", "second"`.

```java
System.out.printf("%2$s, %1$s%n", "first", "second");
```

Kết quả: `second, first`.

Các đoạn bài luyện tập có thể đặt trong `main` của một lớp Java, hoặc thực thi trong JShell; chúng là các statement riêng lẻ, không phải tệp Java độc lập.

**Ghi nhớ:** Với `printf()`, chọn đúng conversion cho kiểu dữ liệu, dùng `width`/ `precision` khi cần căn cột hoặc kiểm soát chữ số, dùng `%%` để in dấu phần trăm và `%n` để xuống dòng phù hợp hệ thống. Chỉ định `Locale` khi cần đầu ra ổn định.
