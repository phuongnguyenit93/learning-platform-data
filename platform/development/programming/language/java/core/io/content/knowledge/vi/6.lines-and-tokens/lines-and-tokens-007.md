# Đọc số với `Scanner` theo locale và radix

## 1. Vấn đề: cùng một token, nhiều cách hiểu số

`java.util.Scanner` có thể đọc văn bản từ `String`, tệp, `InputStream` hoặc nguồn ký tự, tách thành các **token** rồi chuyển token thành `int`, `long`, `double`, `BigDecimal`, `BigInteger` và những kiểu khác. Khi đọc số, hai cấu hình quan trọng là:

- **Locale**: quy định cách hiểu dấu thập phân, dấu phân nhóm hàng nghìn, dấu cộng/trừ theo quy tắc địa phương và một số cách biểu diễn số khác.
- **Radix**: **cơ số** dùng để hiểu chữ số của **số nguyên**, từ 2 đến 36.

Một chuỗi như `1,234.50` thường được hiểu là một nghìn hai trăm ba mươi tư phẩy năm dưới `Locale.US`. Dưới `Locale.GERMANY`, cách viết tương ứng là `1.234,50`. Mặt khác, token `FF` không phải số nguyên hệ thập phân, nhưng có giá trị `255` khi đọc trong hệ 16.

**Ý tưởng cốt lõi:** `Scanner` không “tự đoán” ý định của dữ liệu. Chương trình phải thiết lập locale, radix và quy tắc phân tách token khớp với **định dạng đầu vào**. Một file được tạo theo quy ước của hệ thống khác không nhất thiết phù hợp với locale mặc định của máy đang chạy.

## 2. Scanner tách token trước, rồi mới phân tích số

Mặc định, `Scanner` dùng dấu trắng (whitespace) làm delimiter: dấu cách, tab, xuống dòng theo mẫu delimiter của Scanner. Ví dụ đầu vào:

```text
12 34
56
```

Ba token lần lượt là `12`, `34`, `56`. Các lời gọi `nextInt()` nhận từng token và phân tích chúng thành số nguyên.

Các API liên quan:

| API | Ý nghĩa |
| --- | --- |
| `hasNextInt()` | Kiểm tra token kế tiếp có thể đọc thành `int` theo radix hiện tại không, **không tiêu thụ token** |
| `nextInt()` | Tiêu thụ token kế tiếp và phân tích thành `int` với radix hiện tại |
| `hasNextInt(radix)` | Kiểm tra `int` theo cơ số truyền vào |
| `nextInt(radix)` | Tiêu thụ và đọc `int` theo cơ số truyền vào |
| `hasNextDouble()` / `nextDouble()` | Kiểm tra/đọc số thực theo locale hiện tại |
| `hasNextBigDecimal()` / `nextBigDecimal()` | Đọc số thập phân chính xác dạng `BigDecimal` |
| `useLocale(locale)` | Đặt locale mà Scanner áp dụng cho việc nhận diện số |
| `useRadix(radix)` | Đặt **radix mặc định** cho các thao tác số nguyên có hỗ trợ radix |
| `useDelimiter(pattern)` | Thay quy tắc tách token; không đổi locale hay radix |

`hasNextInt()` và `hasNextDouble()` kiểm tra **token đầy đủ** theo quy tắc số. Chúng không phải công cụ tìm một đoạn số bất kỳ trong giữa văn bản. Nếu token sai định dạng, `nextInt()` hoặc `nextDouble()` không tự sửa token. Hãy xác định delimiter trước khi phân tích số.

## 3. Locale: dấu thập phân và phân nhóm hàng nghìn

Thường gặp hai nhóm quy ước:

| Định dạng nhập | Locale tương ứng | Giá trị toán học |
| --- | --- | ---: |
| `1,234.50` | `Locale.US` | 1234.5 |
| `1.234,50` | `Locale.GERMANY` | 1234.5 |
| `12.75` | `Locale.US` | 12.75 |
| `12,75` | `Locale.GERMANY` | 12.75 |

Trong ví dụ trên:

- `Locale.US`: dấu phẩy `,` phân nhóm hàng nghìn; dấu chấm `.` là dấu thập phân.
- `Locale.GERMANY`: dấu chấm `.` phân nhóm; dấu phẩy `,` là dấu thập phân.

Đây là hai trường hợp cụ thể, không phải mọi locale đều dùng đúng hai quy tắc trên. Một locale có thể dùng khoảng trắng đặc biệt để phân nhóm, ký hiệu số khác hoặc quy tắc địa phương riêng.

Ví dụ tạo Scanner với locale tường minh:

```java
try (Scanner scanner = new Scanner("1.234,50 42")
        .useLocale(Locale.GERMANY)) {
    double amount = scanner.nextDouble();
    int count = scanner.nextInt();
}
```

Đây là **đoạn mã minh họa**, cần import `java.util.Scanner` và `java.util.Locale`; các biến `amount` và `count` chỉ tồn tại trong khối. Trong trường hợp này, `amount` bằng `1234.5` và `count` bằng `42`.

Không nên đổi mọi dấu phẩy thành dấu chấm trước khi parse: `"1.234,50"` có cả dấu nhóm và dấu thập phân, thay thế tùy tiện có thể tạo chuỗi không hợp lệ hoặc đổi ý nghĩa dữ liệu. Hãy chọn locale đúng rồi dùng parser tương ứng.

### Locale mặc định và khả năng tái lập

Nếu không gọi `useLocale`, Scanner khởi tạo với locale mặc định dùng cho định dạng của JVM (thông thường dựa trên `Locale.getDefault(Locale.Category.FORMAT)` ở thời điểm tạo). Giá trị này có thể khác giữa môi trường phát triển, máy chủ và máy người dùng.

Ví dụ file do một dịch vụ quốc tế xuất cố định `1,234.50`: chương trình nên chọn `Locale.US` (hoặc định dạng máy được đặc tả) ngay cả khi máy chạy đặt locale tiếng Đức. **Không lấy locale của máy làm đặc tả file**.

Cần phân biệt **locale của Scanner khi đọc**, **locale khi in với `printf`/`String.format`**, và **charset khi chuyển byte ↔ ký tự**:

- `Scanner.useLocale(Locale.GERMANY)` chọn cách hiểu `1.234,50`.
- `System.out.printf(Locale.US, "%.2f", value)` chọn cách **in** `1234.50`.
- `StandardCharsets.UTF_8` điều khiển cách chuyển chữ thành byte; **không xác định dấu thập phân**.

## 4. Radix: cơ số từ 2 đến 36 cho số nguyên

Radix là cơ số dùng diễn giải vị trí chữ số. Với `nextInt(radix)`:

| Token | Radix | Giá trị thập phân |
| --- | ---: | ---: |
| `1011` | 2 | 11 |
| `17` | 8 | 15 |
| `10` | 10 | 10 |
| `FF` | 16 | 255 |
| `Z` | 36 | 35 |

Ví dụ `1011` ở cơ số 2 tương đương `1×2³ + 0×2² + 1×2¹ + 1×2⁰ = 11`. Radix hợp lệ của các API Scanner đọc số nguyên là từ **`Character.MIN_RADIX` (2)** đến **`Character.MAX_RADIX` (36)**. Radix không hợp lệ, ví dụ 1 hoặc 37, gây `IllegalArgumentException` theo hợp đồng API.

Hai cách chọn radix:

```java
int a = scanner.nextInt(16); // radix 16 chỉ cho lần đọc này
scanner.useRadix(2);         // đặt radix mặc định
int b = scanner.nextInt();   // đọc token tiếp theo ở radix 2
```

Đây là **đoạn mã minh họa**, `scanner` phải được khởi tạo và có token phù hợp. Mặc định ban đầu, Scanner dùng radix **10**. `useRadix(16)` ảnh hưởng các lời gọi không truyền radix của những phương thức số nguyên tương ứng, ví dụ `nextInt()`, `hasNextInt()`, `nextLong()`. Lời gọi `nextInt(10)` vẫn yêu cầu radix 10 cho lần đó.

**Radix không phải locale.** Cơ số giải thích chữ số của **số nguyên**; locale giải thích quy ước số theo địa phương. `nextDouble()` và `nextBigDecimal()` không có overload `nextDouble(radix)` hay `nextBigDecimal(radix)`; `useRadix(16)` không biến số thực thành “hexadecimal floating point parser”.

Khi nhận số nguyên dạng hex từ định dạng đã thỏa thuận, ghi nhận rõ là radix 16 và cung cấp các chữ số như `FF`, không giả định API `nextInt(16)` sẽ tự xử lý mọi cách viết có tiền tố `0x`, dấu `#` hoặc dấu phân tách do một ngôn ngữ lập trình cụ thể quy định.

## 5. Ví dụ Java 17+ đầy đủ: đọc theo locale và radix

Tạo file **`ScannerLocaleRadixDemo.java`**:

```java
import java.util.Locale;
import java.util.Scanner;

public class ScannerLocaleRadixDemo {
    public static void main(String[] args) {
        try (Scanner us = new Scanner("1,234.50 42")
                .useLocale(Locale.US)) {
            System.out.printf(Locale.ROOT, "US double=%.2f%n", us.nextDouble());
            System.out.println("US int=" + us.nextInt());
        }

        try (Scanner de = new Scanner("1.234,50 42")
                .useLocale(Locale.GERMANY)) {
            System.out.printf(Locale.ROOT, "DE double=%.2f%n", de.nextDouble());
            System.out.println("DE int=" + de.nextInt());
        }

        try (Scanner radix = new Scanner("FF 1011 17 10")
                .useLocale(Locale.US)) {
            System.out.println("hex FF=" + radix.nextInt(16));
            System.out.println("binary 1011=" + radix.nextInt(2));

            radix.useRadix(8);
            System.out.println("default octal 17=" + radix.nextInt());

            radix.useRadix(10);
            System.out.println("default decimal 10=" + radix.nextInt());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ScannerLocaleRadixDemo.java
java ScannerLocaleRadixDemo
```

Đầu ra:

```text
US double=1234.50
US int=42
DE double=1234.50
DE int=42
hex FF=255
binary 1011=11
default octal 17=15
default decimal 10=10
```

Tại sao kết quả đúng?

1. Hai Scanner đầu vào khác cách đặt dấu phân nhóm/thập phân, nhưng `useLocale` khiến cả hai đọc số toán học `1234.5`. `printf(Locale.ROOT, "%.2f")` cố định cách hiển thị dấu chấm trong đầu ra để kết quả dự đoán được trên nhiều máy.
2. `nextInt(16)` đọc `FF` thành `255`; `nextInt(2)` đọc `1011` thành `11`.
3. `useRadix(8)` đặt cơ số mặc định của scanner thứ ba; token `17` tương đương `1×8+7=15`.
4. `useRadix(10)` đặt lại cơ số; token `10` được đọc thành `10`.
5. Các Scanner đều dùng chuỗi trong bộ nhớ, không phụ thuộc tệp dữ liệu hoặc `System.in`; `try-with-resources` đóng đúng tài nguyên.

## 6. Kiểm tra token trước khi đọc và xử lý lỗi

Khi nội dung do người dùng nhập có thể sai, dùng `hasNextInt(radix)` hoặc `hasNextDouble()` trước lời gọi `next...`. Hai phương thức `hasNext...` **không tiêu thụ token**, nên cần tiến vị trí bằng `next...` khi thành công, hoặc `next()` để bỏ token sai và tránh vòng lặp vô hạn.

Tạo file **`ScannerValidationDemo.java`**:

```java
import java.util.Scanner;

public class ScannerValidationDemo {
    public static void main(String[] args) {
        try (Scanner input = new Scanner("FF G1 2147483648")) {
            if (input.hasNextInt(16)) {
                System.out.println("hex=" + input.nextInt(16));
            }

            if (!input.hasNextInt(16)) {
                System.out.println("invalid=" + input.next());
            }

            if (!input.hasNextInt()) {
                System.out.println("out of int=" + input.next());
            }
        }
    }
}
```

Biên dịch, chạy:

```bash
javac ScannerValidationDemo.java
java ScannerValidationDemo
```

Đầu ra:

```text
hex=255
invalid=G1
out of int=2147483648
```

- `FF` là token số nguyên hệ 16 hợp lệ.
- `G1` chứa `G`, không phải chữ số hợp lệ của hệ 16. `hasNextInt(16)` trả `false`; gọi `next()` để tiêu thụ token hỏng.
- `2147483648` vượt `Integer.MAX_VALUE` là `2147483647`. Dù chỉ có chữ số thập phân, nó **không phải `int` hợp lệ**. `hasNextInt()` trả `false`; nếu cần số này, cân nhắc `nextLong()` hoặc `nextBigInteger()` sau khi xác định quy tắc dữ liệu.

Khi gọi trực tiếp `nextInt()`, `nextDouble()` hoặc `nextBigDecimal()` mà token không khớp định dạng/số vượt phạm vi, `Scanner` có thể ném `InputMismatchException`. Nếu đầu vào đã hết mà vẫn gọi `next...`, có thể nhận `NoSuchElementException`; dùng scanner đã đóng gây `IllegalStateException`. Đừng trộn chúng thành một lỗi chung “EOF”; từng trường hợp cần thông báo hoặc chính sách xử lý riêng.

Mẫu vòng lặp xử lý token không tin cậy:

```java
while (scanner.hasNext()) {
    if (scanner.hasNextInt(16)) {
        int value = scanner.nextInt(16);
        // xử lý value
    } else {
        String invalidToken = scanner.next();
        // ghi nhận token sai / báo lỗi cho người dùng
    }
}
```

Đây là **đoạn mã minh họa**, `scanner` phải được khai báo và khởi tạo ở nơi gọi. `hasNext()` cho biết còn token theo delimiter, `hasNextInt(16)` kiểm tra parse không tiêu thụ token, `nextInt(16)`/`next()` làm tiến luồng đúng một token mỗi vòng.

## 7. Delimiter và dấu phẩy thập phân là hai chuyện khác nhau

Scanner mặc định phân tách token bằng dấu trắng. Token `1,5;2,75` **không tự động** trở thành hai số theo locale Đức; ký tự `;` chưa được cấu hình làm delimiter.

Nếu định dạng đầu vào dùng dấu chấm phẩy phân tách trường và dấu phẩy làm dấu thập phân, chỉ rõ **cả delimiter và locale**:

```java
import java.util.Locale;
import java.util.Scanner;

public class ScannerSemicolonDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("1,5;2,75")
                .useDelimiter(";")
                .useLocale(Locale.GERMANY)) {
            System.out.println(scanner.nextDouble());
            System.out.println(scanner.nextDouble());
        }
    }
}
```

Chạy:

```bash
javac ScannerSemicolonDemo.java
java ScannerSemicolonDemo
```

Đầu ra (Java `println(double)` in dạng số Java với dấu chấm):

```text
1.5
2.75
```

`useDelimiter(";")` quy định **ranh giới token**, còn `useLocale(Locale.GERMANY)` cho phép dấu phẩy trong mỗi token mang nghĩa dấu thập phân. Nếu delimiter lại là dấu phẩy, đầu vào `1,5;2,75` có thể bị cắt ở vị trí thuộc nội dung số, khiến parser thất bại hoặc hiểu sai.

Với tệp CSV, dấu phẩy có thể vừa là phần dữ liệu trong trường được quote vừa là delimiter. `Scanner.useDelimiter(",")` không phải CSV parser hoàn chỉnh: nó không hiểu escaping, trường chứa dấu phẩy trong dấu ngoặc kép hoặc xuống dòng bên trong trường. Với CSV thực sự nên dùng parser tuân chuẩn định dạng; với `Scanner`, chỉ dùng khi cú pháp đầu vào đủ đơn giản và đã được kiểm soát.

## 8. Khi cần số thập phân chính xác: `BigDecimal`

`nextDouble()` trả về `double` dạng IEEE 754, có thể không biểu diễn chính xác các giá trị thập phân như `0.1`. Điều đó phù hợp cho nhiều tính toán khoa học, nhưng không phải lựa chọn mặc định cho số tiền hay nghiệp vụ đòi hỏi chính xác thập phân.

`Scanner.nextBigDecimal()` đọc token số thực thỏa locale dưới dạng `java.math.BigDecimal`, hỗ trợ tính toán thập phân chính xác theo quy tắc của `BigDecimal`.

Tạo file **`ScannerBigDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Scanner;

public class ScannerBigDecimalDemo {
    public static void main(String[] args) {
        try (Scanner input = new Scanner("1.234,50;2,75")
                .useDelimiter(";")
                .useLocale(Locale.GERMANY)) {
            BigDecimal first = input.nextBigDecimal();
            BigDecimal second = input.nextBigDecimal();
            BigDecimal total = first.add(second);

            System.out.println("first=" + first.toPlainString());
            System.out.println("second=" + second.toPlainString());
            System.out.println("sum=" + total.toPlainString());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ScannerBigDecimalDemo.java
java ScannerBigDecimalDemo
```

Kết quả:

```text
first=1234.50
second=2.75
sum=1237.25
```

`Scanner` nhận diện dấu nhóm `.` và dấu thập phân `,` theo `Locale.GERMANY`. `BigDecimal.toPlainString()` hiển thị số ở dạng chữ số thập phân với dấu chấm, không tự tái dùng định dạng locale gốc. Nếu cần xuất ra theo quy ước địa phương, định dạng **đầu ra** bằng API định dạng thích hợp (ví dụ `NumberFormat`) và chỉ định locale rõ ràng.

Radix không áp dụng cho `nextBigDecimal()`; cơ số không quyết định dấu thập phân hoặc số chữ số sau phần thập phân.

## 9. Tương tác giữa `nextInt()` và `nextLine()`

`nextInt()` đọc **token số**, thường dừng trước ký tự xuống dòng; `nextLine()` lấy **phần còn lại của dòng hiện tại**, loại bỏ ký tự kết thúc dòng. Vì vậy sau một `nextInt()`, `nextLine()` có thể trả về chuỗi rỗng.

Ví dụ:

```java
import java.util.Scanner;

public class ScannerLineDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("42\nXin chào\n")) {
            int number = scanner.nextInt();
            String rest = scanner.nextLine();
            String nextLine = scanner.nextLine();

            System.out.println("number=" + number);
            System.out.println("rest empty=" + rest.isEmpty());
            System.out.println("next=" + nextLine);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ScannerLineDemo.java
java ScannerLineDemo
```

Đầu ra:

```text
number=42
rest empty=true
next=Xin chào
```

Đây là hệ quả của việc trộn đọc **token** với đọc **dòng**, không phải lỗi locale hay radix. Nếu mỗi dòng đại diện cho một bản ghi, một cách khác là lấy cả dòng bằng `nextLine()` rồi dùng Scanner riêng cho chuỗi dòng đó với delimiter, locale và radix được chỉ định tường minh. Tránh bỏ `nextLine()` một cách máy móc nếu phần còn lại của dòng có dữ liệu cần giữ.

## 10. Đọc số từ tệp và vấn đề charset

Nếu nguồn là tệp byte, **charset** giải quyết chuyển byte thành văn bản, còn **locale/radix** giải quyết chuyển token văn bản thành số. Chúng độc lập:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Scanner;

public class ScanNumbersFile {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("numbers.txt");

        try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)
                .useLocale(Locale.GERMANY)
                .useRadix(10)) {
            while (scanner.hasNext()) {
                if (scanner.hasNextDouble()) {
                    System.out.println(scanner.nextDouble());
                } else {
                    System.err.println("Token không phải số: " + scanner.next());
                }
            }
        }
    }
}
```

Chương trình này **đầy đủ về mã Java 17+**, nhưng yêu cầu có tệp `numbers.txt` tồn tại trong thư mục làm việc; do nội dung tệp có thể khác nhau, không công bố stdout cố định. `new Scanner(path, StandardCharsets.UTF_8)` chỉ rõ charset của file; `useLocale(Locale.GERMANY)` chỉ rõ cách hiểu dấu thập phân/nhóm; `useRadix(10)` chỉ có ý nghĩa cho những lần đọc số **nguyên** hỗ trợ radix và không đổi cách `nextDouble()` hoạt động.

Khi mở `Scanner` trên `System.in` và đóng Scanner, luồng chuẩn nhập bên dưới cũng bị đóng; điều này có thể gây lỗi cho những phần khác của ứng dụng cần đọc console tiếp. Hãy xác định rõ nơi sở hữu tài nguyên. Với Scanner tự tạo từ `String`, `try-with-resources` là cách dùng đơn giản và an toàn.

`Scanner` có khả năng phân tích token mạnh, nhưng việc dùng biểu thức chính quy và phân tích từng token khiến nó thường không phải lựa chọn nhanh nhất cho dữ liệu cực lớn. Với ứng dụng cần throughput cao, có thể đọc theo dòng hoặc byte rồi parse bằng API chuyên dụng và benchmark, trong khi vẫn giữ locale/định dạng nhất quán.

## 11. Locale, radix, delimiter và định dạng đầu ra: đối chiếu nhanh

| Yêu cầu | Cấu hình/API cần quan tâm | Không nên nhầm với |
| --- | --- | --- |
| Nhận `1.234,50` thành `1234.5` | `useLocale(Locale.GERMANY)`, `nextDouble()` | `useRadix(10)` |
| Nhận `FF` thành `255` | `nextInt(16)` hoặc `useRadix(16)` | `useLocale(Locale.US)` |
| Tách `1,5;2,75` thành hai token | `useDelimiter(";")` | Charset UTF-8 |
| Giữ chính xác số tiền | `nextBigDecimal()` với locale đúng | `nextDouble()` rồi cộng trực tiếp |
| Đọc bytes tệp UTF-8 | `new Scanner(path, StandardCharsets.UTF_8)` | Locale của số |
| In số theo quy ước cố định | `printf(Locale.ROOT, ...)` hoặc `String.format(locale, ...)` | Locale của Scanner |
| Phát hiện token không hợp lệ | `hasNextInt(radix)`, `hasNextDouble()` | `hasNext()` chỉ kiểm tra có token |

Một vài lỗi thường gặp:

- Để Scanner dùng locale hệ thống khiến dữ liệu cùng định dạng chạy đúng trên máy này nhưng sai trên máy khác.
- Tưởng `"1,5"` luôn là `1.5`: dưới locale không dùng dấu phẩy thập phân, token có thể bị từ chối hoặc được hiểu theo quy tắc khác.
- Đặt `useRadix(16)` rồi gọi `nextDouble()` và chờ kết quả “số thực hệ 16”.
- Gọi `hasNextInt()` liên tục mà không tiêu thụ token sai khi trả `false`: vòng lặp có thể đứng mãi ở một chỗ.
- Dùng `nextInt()` cho số vượt phạm vi `int`, rồi nghĩ rằng token chứa chữ cái; kiểm tra cả radix lẫn giới hạn giá trị.
- Đọc từng token rồi gọi `nextLine()` mà không xét phần còn lại của dòng.
- Dùng delimiter dấu phẩy cho văn bản trong đó dấu phẩy thuộc chính số thập phân.
- Sử dụng `Double.parseDouble(...)` để thay thế Scanner locale-aware: `Double.parseDouble` chấp nhận cú pháp số Java không dựa trên locale, nên `"1,5"` không trở thành `1.5` chỉ vì locale máy là tiếng Đức.

**Bài tự luyện:** Cho văn bản `"1.234,50;FF;1011"`. Hãy chọn delimiter `;`, dùng `Locale.GERMANY` để đọc token đầu bằng `nextBigDecimal()`, tiếp đó `nextInt(16)` và `nextInt(2)`. Các giá trị mong đợi lần lượt là **`1234.50`, `255`, `11`**. Giải thích vì sao đổi locale mà không đặt delimiter là chưa đủ.

**Ghi nhớ:** Khi dùng `Scanner` đọc số, cần định nghĩa **ba tầng khác nhau**: delimiter chia token, locale diễn giải dấu và cách viết số, radix diễn giải chữ số của số nguyên. Chọn cả ba theo hợp đồng dữ liệu, xác thực token trước khi tiêu thụ và chỉ định charset riêng nếu nguồn là byte.