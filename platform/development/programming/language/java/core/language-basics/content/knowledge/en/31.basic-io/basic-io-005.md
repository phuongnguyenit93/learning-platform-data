# Đọc dữ liệu console bằng `Scanner` (Java 17+)

## 1. `Scanner` là gì và dùng khi nào?

`java.util.Scanner` là lớp tiện ích đọc đầu vào dưới dạng **token** hoặc **dòng**, có thể phân tích dữ liệu thành các kiểu như `int`, `long`, `double` và `boolean`. Trong bài nhập xuất console, ta thường gắn một `Scanner` với `System.in`:

```java
import java.util.Scanner;

Scanner scanner = new Scanner(System.in);
String name = scanner.nextLine();
int age = scanner.nextInt();
```

Đây là những câu lệnh minh họa cần đặt trong phương thức hay khối mã thích hợp. `System.in` là luồng đầu vào chuẩn; thường nhận ký tự từ bàn phím khi chương trình chạy trong terminal, nhưng cũng có thể lấy dữ liệu từ một file hoặc pipe. `Scanner` biến luồng này thành các giá trị có cấu trúc.

`Scanner` thích hợp với chương trình console nhỏ, bài tập và công cụ dòng lệnh đơn giản. Đối với khối lượng dữ liệu văn bản rất lớn, có thể xem xét `BufferedReader` để chủ động đọc từng dòng; `Scanner` thuận tiện hơn khi cần tách và parse token.

## 2. Các phương thức quan trọng

| Phương thức | Dữ liệu đọc | Đặc điểm |
| --- | --- | --- |
| `next()` | Token kế tiếp, trả `String` | Mặc định bỏ qua dấu phân cách khoảng trắng; chỉ lấy một token |
| `nextLine()` | Phần còn lại của dòng hiện tại, trả `String` | Có thể gồm khoảng trắng; bỏ dấu kết thúc dòng khỏi giá trị trả về |
| `nextInt()` / `nextLong()` | Token số nguyên | Parse theo radix/locale tương ứng; báo lỗi nếu token không hợp lệ hoặc ngoài miền giá trị |
| `nextDouble()` / `nextFloat()` | Token số thực | Quy tắc dấu thập phân và phân nhóm chịu ảnh hưởng của `Locale` |
| `nextBoolean()` | Token boolean | Nhận `true`/`false` theo cách so khớp không phân biệt hoa thường |
| `hasNext()` / `hasNextLine()` | `boolean` | Kiểm tra còn token/dòng hay không, hữu ích ở cuối input |
| `hasNextInt()` / `hasNextDouble()` | `boolean` | Kiểm tra token tiếp theo có parse được theo kiểu đó không |
| `useLocale(locale)` | Cấu hình Scanner | Quy định cú pháp số theo locale |
| `useDelimiter(regex)` | Cấu hình Scanner | Thay mẫu phân cách token mặc định bằng biểu thức chính quy |

**Token khác dòng:** với đầu vào `Nguyen Van An`, `next()` chỉ lấy `Nguyen`, còn `nextLine()` có thể lấy toàn bộ `Nguyen Van An` (nếu đang ở đầu dòng).

Mặc định, dấu phân cách token của `Scanner` là các ký tự khoảng trắng (space, tab, xuống dòng...). Những phương thức `nextInt()`, `nextDouble()`, `next()` đọc theo **token**; `nextLine()` đọc theo **ranh giới dòng**. Trộn hai cách đọc này cần cẩn thận.

## 3. Ví dụ đầy đủ: đọc tên, tuổi, điểm và ghi chú

Tạo file **`ScannerDemo.java`**:

```java
import java.util.Locale;
import java.util.Scanner;

public class ScannerDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            scanner.useLocale(Locale.US);

            System.out.println("Enter full name:");
            String name = scanner.nextLine();

            System.out.println("Enter age:");
            int age = scanner.nextInt();

            System.out.println("Enter score:");
            double score = scanner.nextDouble();

            scanner.nextLine(); // consume the remainder of the score line
            System.out.println("Enter note:");
            String note = scanner.nextLine();

            System.out.printf(Locale.US,
                    "Result: %s | age=%d | score=%.1f | note=%s%n",
                    name, age, score, note);
        }
    }
}
```

**Đầu vào** (gõ mỗi giá trị rồi nhấn Enter, hoặc tạo file `sample.txt` có chính xác bốn dòng này):

```text
Nguyen Van An
20
8.5
Likes Java
```

Biên dịch tại thư mục chứa `ScannerDemo.java` bằng **JDK 17+**:

```sh
javac -encoding UTF-8 --release 17 -d out ScannerDemo.java
java -cp out ScannerDemo
```

Tạo sẵn thư mục `out` bằng `mkdir out` trước khi biên dịch nếu nó chưa tồn tại. Trong lần chạy tương tác, terminal có thể hiển thị lại các ký tự người dùng vừa gõ; các ký tự được terminal echo **không thuộc stdout do Java in**.

Để kiểm tra output ổn định với `sample.txt`:

- **Linux/macOS hoặc Windows CMD:** `java -cp out ScannerDemo < sample.txt`
- **Windows PowerShell 5.1+:** `Get-Content -LiteralPath sample.txt | java -cp out ScannerDemo`

**Stdout chính xác của chương trình** với đầu vào đã nêu (không tính phần input được terminal tự echo):

```text
Enter full name:
Enter age:
Enter score:
Enter note:
Result: Nguyen Van An | age=20 | score=8.5 | note=Likes Java
```

Cần hiểu các bước sau:

1. `nextLine()` lấy toàn bộ tên có dấu cách.
2. `nextInt()` đọc token `20`; `nextDouble()` đọc token `8.5`.
3. `scanner.useLocale(Locale.US)` quy định dấu chấm `.` làm dấu thập phân. Locale mặc định của máy có thể khác, vì vậy `8.5` không phải lúc nào cũng được đọc như mong đợi nếu bỏ cấu hình.
4. `scanner.nextLine()` ngay sau `nextDouble()` chủ động đọc và bỏ phần còn lại của dòng điểm, để `nextLine()` kế tiếp nhận dòng ghi chú.
5. `System.out.printf(Locale.US, ...)` cố định cách định dạng dấu thập phân trong kết quả.

Mã ví dụ giả định tuổi và điểm **đúng định dạng**. Nếu đầu vào sai hoặc bị cắt ngắn, các lệnh `nextInt()`, `nextDouble()`, `nextLine()` có thể ném ngoại lệ; phần 6–7 hướng dẫn xử lý.

## 4. Chú ý khi chuyển từ đọc token sang đọc dòng

`nextInt()` và `nextDouble()` đọc một **token số**; `nextLine()` đọc **phần còn lại của dòng hiện tại**. Với input `21\nHello Java\n`, sau `nextInt()` lần `nextLine()` kế tiếp nhận `""` vì dòng số đã hết. Nếu còn văn bản sau số trên cùng dòng, `nextLine()` sẽ trả phần văn bản đó thay vì chuỗi rỗng.

Khi hợp đồng yêu cầu **số ở một dòng, ghi chú ở dòng kế tiếp**, có thể gọi một `nextLine()` để tiêu thụ phần dư rồi gọi lần nữa để lấy ghi chú. Khi muốn nhập từng trường một dòng và dễ kiểm tra lỗi, dùng `Integer.parseInt(scanner.nextLine().strip())` sau khi kiểm tra còn dòng là lựa chọn khác. Đừng tự bỏ phần dư nếu nó chứa dữ liệu cần giữ.

Ví dụ `ScannerDemo` phía trên áp dụng cách đầu; bài xử lý phần xuống dòng còn lại trình bày tình huống có/không có văn bản cùng dòng, EOF và các phương án xử lý bằng chương trình tái hiện độc lập.

## 5. Đọc token, dòng và dấu phân cách theo nhu cầu

Một token được xác định bởi **delimiter** hiện tại. Ví dụ đọc những từ phân cách bằng khoảng trắng:

```java
import java.util.Scanner;

public class TokenDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("red green\nblue")) {
            while (scanner.hasNext()) {
                System.out.println("token=" + scanner.next());
            }
        }
    }
}
```

```sh
javac -encoding UTF-8 --release 17 -d out TokenDemo.java
java -cp out TokenDemo
```

Output:

```text
token=red
token=green
token=blue
```

Nếu muốn tách theo dấu phẩy, có thể thay delimiter:

```java
scanner.useDelimiter(",");
```

Đây là statement minh họa cần đặt trong khối có biến `scanner` phù hợp. `useDelimiter` nhận **regex**, không phải chuỗi văn bản đơn thuần cho mọi ký hiệu. Ví dụ muốn tách cả dấu phẩy lẫn khoảng trắng, sử dụng `scanner.useDelimiter("[,\\s]+");` trong Java source; Java biến `\\` trong string literal thành `\`, để biểu thức chính quy nhận `\s` là lớp ký tự trắng.

Dùng `nextLine()` khi cần giữ khoảng trắng giữa các từ (họ tên, câu nhập từ người dùng), và dùng `next()`/`nextInt()` khi input thực sự được thiết kế như một chuỗi token.

## 6. Kiểm tra dữ liệu trước khi parse

Nếu `nextInt()` gặp `abc`, `Scanner` thường ném `InputMismatchException`. Nếu không còn token, `nextInt()` có thể ném `NoSuchElementException`. `hasNextInt()` giúp kiểm tra token tiếp theo trước khi đọc:

```java
if (scanner.hasNextInt()) {
    int value = scanner.nextInt();
    System.out.println("value=" + value);
} else {
    System.out.println("Not a valid int token");
}
```

Đoạn trên là minh họa phụ thuộc vào biến `scanner`. Khi `hasNextInt()` trả `false` do token sai, scanner **chưa tự loại token không hợp lệ**; nếu lặp mà không tiêu thụ hay bỏ token đó, vòng lặp có thể không tiến triển. Khi kiểm tra input theo dòng, nên đọc `nextLine()`, parse và phản hồi lại người dùng.

### Ví dụ đầy đủ: đọc dòng, xử lý sai số nguyên và EOF

Tạo **`ValidatedScannerDemo.java`**:

```java
import java.util.Scanner;

public class ValidatedScannerDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            System.out.println("Enter an integer from 0 to 100:");

            if (!scanner.hasNextLine()) {
                System.out.println("Error: no input");
                return;
            }

            String text = scanner.nextLine().trim();
            try {
                int number = Integer.parseInt(text);
                if (number < 0 || number > 100) {
                    System.out.println("Error: out of range");
                } else {
                    System.out.println("Accepted: " + number);
                }
            } catch (NumberFormatException ex) {
                System.out.println("Error: not an integer");
            }
        }
    }
}
```

Biên dịch:

```sh
javac -encoding UTF-8 --release 17 -d out ValidatedScannerDemo.java
```

Chạy:

```sh
java -cp out ValidatedScannerDemo
```

Với mỗi lần chạy, người dùng cung cấp **một dòng duy nhất**. Đầu ra tương ứng:

| Input | Stdout từ chương trình |
| --- | --- |
| `42` | `Enter an integer from 0 to 100:` rồi `Accepted: 42` |
| `abc` | Dòng nhắc nhập rồi `Error: not an integer` |
| `150` | Dòng nhắc nhập rồi `Error: out of range` |
| EOF ngay lập tức | Dòng nhắc nhập rồi `Error: no input` |

Với input `42`, **stdout chính xác** là:

```text
Enter an integer from 0 to 100:
Accepted: 42
```

Ví dụ đọc toàn bộ dòng nên xử lý được giá trị có khoảng trắng ở hai đầu thông qua `trim()`, không gặp lỗi newline sau `nextInt()`. Phép parse `Integer.parseInt` ở đây là API của `Integer`, nên lỗi định dạng là `NumberFormatException`, khác với `InputMismatchException` của `Scanner.nextInt()`.

**Khác biệt giữa kiểm tra và xử lý:** `hasNextLine()` giúp tránh gọi `nextLine()` khi đã EOF, nhưng nó không xác minh định dạng số. Ngược lại, `hasNextInt()` xác minh token số nguyên theo `Scanner` nhưng không thay thế kiểm tra miền giá trị nghiệp vụ, ví dụ 0 đến 100.

## 7. Các ngoại lệ và vấn đề cần biết

| Tình huống | Hậu quả có thể gặp | Cách phòng tránh |
| --- | --- | --- |
| `nextInt()` đọc `abc` hoặc số ngoài miền `int` | `InputMismatchException` | `hasNextInt()`, thông báo cho người dùng, bỏ token sai hoặc đọc cả dòng để parse |
| `nextLine()` hoặc `next()` lúc không còn dòng/token | `NoSuchElementException` | Dùng `hasNextLine()` hoặc `hasNext()` phù hợp trước khi đọc |
| Dùng scanner sau `scanner.close()` | `IllegalStateException` | Không tiếp tục sử dụng đối tượng đã đóng |
| Quên dòng còn dư sau `nextInt()` | `nextLine()` trả chuỗi rỗng hoặc phần dư của dòng cũ | Dùng `nextLine()` để bỏ phần dư khi phù hợp, hoặc chỉ đọc cả dòng rồi parse |
| `nextDouble()` không chấp nhận `8.5` như mong đợi | Locale số đang dùng khác | Đặt `useLocale(Locale.US)` nếu yêu cầu dấu thập phân là `.` |
| Gõ số ngoài khoảng nghiệp vụ | Có thể parse thành công nhưng dữ liệu vẫn sai | Kiểm tra miền giá trị sau khi parse |
| Dùng nhiều `Scanner(System.in)` cùng lúc | Đọc trước/buffer làm các scanner cạnh tranh và gây lỗi khó hiểu | Duy trì một scanner dùng chung cho input console |

Ngoài những lỗi trên, `Scanner` có thể phải chờ khi chương trình đang yêu cầu dữ liệu mà đầu vào chưa cung cấp token/dòng hoàn chỉnh. Với bài console tương tác, hãy nhìn dòng nhắc nhập và xác nhận mình đã nhấn Enter hoặc đã kết thúc input.

## 8. `Locale` và mã hóa của nguồn nhập

`scanner.useLocale(Locale.US)` giúp `nextDouble()` đọc dạng như `8.5` với dấu chấm thập phân. Locale khác có thể dùng dấu phẩy, vì vậy ví dụ cần đầu ra xác định nên chỉ rõ locale. `Scanner.nextLine()` trả chuỗi chưa parse; dùng `Double.parseDouble` với chuỗi dấu chấm là một hợp đồng khác với `Scanner.nextDouble()` theo locale.

Với nguồn byte cần giải mã UTF-8, có thể khởi tạo `new Scanner(System.in, StandardCharsets.UTF_8)` (sau khi import tương ứng). `javac -encoding UTF-8` chỉ điều khiển việc đọc **mã nguồn**, không cấu hình mặc định cho dữ liệu của `System.in`. Bài Locale và sở hữu nguồn nhập phân tích chi tiết từng trường hợp.

## 9. Quyền sở hữu và việc đóng `Scanner`

`Scanner` triển khai `AutoCloseable`; khi đóng, nó cũng đóng nguồn bọc bên dưới nếu nguồn là `Closeable`. Vì vậy `try (Scanner s = new Scanner(System.in)) { ... }` phù hợp với chương trình nhỏ đã kết thúc mọi thao tác đọc khi rời khối. Nhưng `System.in` có thể được chia sẻ, nên không đóng scanner mượn nguồn này giữa chừng nếu phần khác còn cần đọc.

Nguồn do chính mã mở (như file) cần được đóng đúng lúc; scanner từ `String` không làm ảnh hưởng `System.in`. Hãy có một nơi chịu trách nhiệm vòng đời input và tránh tạo nhiều scanner tranh nhau đọc luồng console chung. Bài cuối chương có ví dụ riêng về đóng nguồn và cấu hình locale.

## 10. Thói quen tốt khi viết chương trình console

1. **Xác định input được tổ chức theo token hay theo dòng.** Họ tên/câu mô tả nên dùng `nextLine()`; danh sách số phân cách bởi khoảng trắng có thể phù hợp với `nextInt()`/`nextDouble()`.
2. **Giữ nhất quán cách đọc.** Dùng đọc theo dòng rồi parse khi muốn validation và thông báo lỗi rõ ràng; khi trộn token với dòng, chú ý phần còn lại của dòng.
3. **Kiểm tra EOF trước khi đọc** bằng các `hasNext...()` phù hợp nếu nguồn input có thể hết sớm.
4. **Kiểm tra kiểu và miền giá trị độc lập.** `42` có thể là `int` hợp lệ nhưng không phải tuổi hợp lệ theo hợp đồng ứng dụng.
5. **Đặt `Locale` rõ ràng** cho số thực và thống nhất quy tắc định dạng input/output.
6. **Không dùng nhiều scanner trên cùng `System.in`** nếu không thật sự cần; truyền một scanner qua các phương thức.
7. **Không hiển thị hoặc log dữ liệu bí mật** như mật khẩu nhập từ terminal. `Scanner(System.in)` không tắt tính năng echo của terminal nên không phù hợp để yêu cầu nhập mật khẩu mà cần che ký tự; xem `System.console().readPassword()` trong môi trường có console phù hợp.

## 11. Tự kiểm tra

**1. Với input `Tran Van Binh`, `next()` và `nextLine()` khác nhau thế nào?** `next()` đọc token `Tran`; `nextLine()` đọc phần còn lại của dòng hiện tại, tùy vị trí đọc. Nếu đang ở đầu dòng, nó lấy `Tran Van Binh`.

**2. Vì sao `nextLine()` ngay sau `nextInt()` thường trả chuỗi rỗng?** Vì `nextInt()` chỉ tiêu thụ token số, để lại dấu xuống dòng; `nextLine()` đọc phần còn lại của dòng đó.

**3. Đọc `abc` bằng `nextInt()` có trả về 0 không?** Không. Thường nó ném `InputMismatchException`. Dùng kiểm tra định dạng và xử lý lỗi.

**4. `hasNextInt()` trả `false` có tự bỏ token sai không?** Không. Nếu muốn tiếp tục, cần đọc/bỏ token không hợp lệ để tiến tới input kế tiếp.

**5. `nextDouble()` có luôn hiểu `8.5` như số thực không?** Không; phụ thuộc `Locale`. Có thể dùng `scanner.useLocale(Locale.US)`.

**6. Đóng `Scanner(System.in)` giữa chương trình có vô hại không?** Không. Nó có thể đóng luôn `System.in` khiến các bước nhập sau không hoạt động.

**Ghi nhớ:** `Scanner` giúp đọc và parse dữ liệu console rất tiện, nhưng bạn phải lựa chọn ranh giới **token hay dòng**, quản lý **locale**, xử lý **dữ liệu không hợp lệ/EOF** và điều khiển vòng đời `System.in` có chủ đích.
