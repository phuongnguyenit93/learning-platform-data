# Scanner: xác định charset ở nơi tiếp nhận byte và phân biệt lỗi mã hóa với lỗi token hoặc locale

## 1. Scanner làm gì và charset nằm ở đâu?

`java.util.Scanner` phân tích dữ liệu đầu vào thành token hoặc dòng. Nó có thể đọc từ file, `Path`, `InputStream`, `ReadableByteChannel`, `Readable`, hoặc một `String` đã có sẵn. Scanner hỗ trợ các thao tác như `next()`, `nextLine()`, `nextInt()`, `nextDouble()`, kiểm tra trước bằng `hasNext...()`, và thay đổi delimiter, locale hoặc radix.

Khi nguồn đầu vào là **byte** (ví dụ `InputStream`, file hoặc channel), chương trình phải giải mã byte thành ký tự trước khi Scanner có thể phân tích token. Vì vậy, cần chọn charset ở đúng constructor nhận byte hoặc ở `Reader` được truyền vào Scanner.

```text
File / socket / InputStream
          |
          | byte
          v
  Charset decoder
  (ví dụ UTF-8)
          |
          | char
          v
       Scanner
          |
          +--> delimiter / token
          +--> nextInt / nextDouble
          +--> locale / radix
          |
          v
   Logic ứng dụng
```

**Charset, delimiter và locale giải quyết ba vấn đề khác nhau:**

- Charset xác định cách diễn giải byte thành ký tự.
- Delimiter xác định cách tách chuỗi ký tự thành token.
- Locale xác định quy ước địa phương khi phân tích các giá trị như số thập phân, dấu nhóm hàng nghìn hoặc ngày tháng nếu ứng dụng tự xử lý.

Một token không phân tích được thành số chưa chắc là lỗi charset. Ngược lại, nếu byte bị giải mã sai, token có thể đã sai trước khi Scanner kiểm tra kiểu dữ liệu.

## 2. Chọn constructor có charset khi nguồn là byte

### 2.1. Các dạng constructor thường dùng

| Nguồn | Constructor | Charset |
| --- | --- | --- |
| `InputStream` | `new Scanner(input)` | Default charset của JVM |
| `InputStream` | `new Scanner(input, charset)` | Charset chỉ định |
| `File` | `new Scanner(file)` | Default charset của JVM |
| `File` | `new Scanner(file, charset)` | Charset chỉ định |
| `Path` | `new Scanner(path)` | Default charset của JVM |
| `Path` | `new Scanner(path, charset)` | Charset chỉ định |
| `ReadableByteChannel` | `new Scanner(channel)` | Default charset của JVM |
| `ReadableByteChannel` | `new Scanner(channel, charset)` | Charset chỉ định |
| `Readable` | `new Scanner(readable)` | Không chọn charset ở Scanner |
| `String` | `new Scanner(string)` | Không chọn charset ở Scanner |

Các overload nhận `Charset` được bổ sung từ Java 10 và vẫn dùng được trên JDK hiện đại. Ưu tiên truyền `StandardCharsets.UTF_8` hoặc charset thực tế của dữ liệu thay vì dựa vào default charset.

Ví dụ đọc file UTF-8:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;

Path path = Path.of("users.txt");

try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        String line = scanner.nextLine();
        process(line);
    }
    IOException sourceFailure = scanner.ioException();
    if (sourceFailure != null) {
        throw sourceFailure;
    }
} catch (IOException e) {
    // Lỗi mở file hoặc lỗi đọc được Scanner ghi nhận.
    reportReadFailure(e);
}
```

Scanner đọc và giải mã dữ liệu theo UTF-8 trước khi tách token hoặc dòng. Nếu file thực sự được tạo theo ISO-8859-1, hãy truyền `StandardCharsets.ISO_8859_1` thay vì UTF-8.

### 2.2. Khi nguồn đã là ký tự, charset đã được quyết định ở tầng trước

`Scanner(Readable)` và `Scanner(String)` không nhận charset vì dữ liệu đầu vào đã là ký tự Java. Ví dụ:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

var reader = new BufferedReader(
        new InputStreamReader(inputStream, StandardCharsets.UTF_8));

try (Scanner scanner = new Scanner(reader)) {
    while (scanner.hasNextLine()) {
        process(scanner.nextLine());
    }
}
```

Trong ví dụ này, `InputStreamReader` chịu trách nhiệm giải mã UTF-8; Scanner chỉ đọc ký tự từ `Reader`. Nếu đổi charset, phải đổi ở `InputStreamReader`, không có tác dụng khi cố tìm một constructor `Scanner(Reader, Charset)` vì constructor như vậy không tồn tại.

### 2.3. Tên charset dạng String và dạng Charset

Scanner cũng có các overload nhận tên charset dạng `String`, ví dụ `new Scanner(path, "UTF-8")`. Tuy nhiên, nếu đã biết charset, dạng `Charset` thường dễ kiểm tra và an toàn hơn:

```java
new Scanner(path, StandardCharsets.UTF_8);
```

Các hằng số trong `StandardCharsets` như `UTF_8`, `ISO_8859_1`, `US_ASCII` được chuẩn Java bảo đảm có sẵn. Constructor nhận tên charset có thể ném `IllegalArgumentException` nếu tên không được hỗ trợ hoặc không hợp lệ.

## 3. Java 18 và JEP 400: default charset không thay thế hợp đồng dữ liệu

JEP 400 đặt UTF-8 làm default charset thông thường của Java SE từ Java 18. Vì vậy, constructor Scanner không truyền charset thường sử dụng UTF-8 trong cấu hình mặc định của JDK 18+.

Tuy nhiên, cần tách hai trường hợp:

1. `new Scanner(inputStream)` dùng default charset của JVM. Kết quả có thể chịu ảnh hưởng của cấu hình tương thích mà JDK hỗ trợ, chẳng hạn `-Dfile.encoding=COMPAT`.
2. `new Scanner(inputStream, StandardCharsets.UTF_8)` luôn thể hiện rõ charset theo hợp đồng của dữ liệu, không phụ thuộc default charset.

Không nên coi Java 18 là lý do để bỏ tham số charset trong ứng dụng đọc file hoặc giao thức có encoding đã được quy định. Nếu bên gửi đã công bố UTF-8, hãy chỉ rõ UTF-8; nếu bên gửi công bố charset khác, dùng charset đó.

Có thể kiểm tra default charset tại runtime:

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
```

Thông tin này hữu ích để chẩn đoán môi trường. Nó không tự cho biết charset mà một file tùy ý hoặc một terminal bên ngoài đang sử dụng.

## 4. Đọc token và đọc dòng là hai cách phân tích khác nhau

Scanner mặc định tách token bằng các ký tự whitespace. Các phương thức thường dùng:

| Phương thức | Kết quả | Hành vi |
| --- | --- | --- |
| `next()` | `String` | Lấy token kế tiếp |
| `hasNext()` | `boolean` | Kiểm tra có token kế tiếp |
| `nextLine()` | `String` | Lấy phần còn lại của dòng hiện tại, bỏ line separator |
| `hasNextLine()` | `boolean` | Kiểm tra còn dòng hay không |
| `nextInt()` | `int` | Phân tích token kế tiếp thành số nguyên |
| `hasNextInt()` | `boolean` | Kiểm tra token kế tiếp có phân tích được thành số nguyên không |
| `nextDouble()` | `double` | Phân tích token kế tiếp thành số thực theo locale |
| `hasNextDouble()` | `boolean` | Kiểm tra token kế tiếp có phân tích được thành số thực không |

Ví dụ tách token:

```java
import java.util.Scanner;

try (Scanner scanner = new Scanner("red green blue")) {
    while (scanner.hasNext()) {
        System.out.println(scanner.next());
    }
}
```

Kết quả là ba token `red`, `green`, `blue`. Scanner không tự biết cấu trúc nghiệp vụ của dữ liệu; delimiter mặc định chỉ là whitespace.

### 4.1. Đổi delimiter

Có thể dùng biểu thức chính quy để xác định dấu phân cách:

```java
import java.util.Scanner;

String record = "alice,42,active";

try (Scanner scanner = new Scanner(record)) {
    scanner.useDelimiter(",");

    String name = scanner.next();
    int age = scanner.nextInt();
    String status = scanner.next();

    System.out.println(name + " / " + age + " / " + status);
}
```

`useDelimiter` nhận một regex, không phải chuỗi delimiter literal trong mọi trường hợp. Nếu delimiter có ký tự đặc biệt của regex như dấu chấm hoặc dấu gạch đứng, cần escape hoặc dùng `Pattern.quote`.

`nextLine()` có ngữ nghĩa riêng: nó trả phần còn lại của dòng, không tách theo delimiter token hiện tại. Điều này giải thích vì sao trộn `nextInt()` và `nextLine()` có thể khiến chương trình nhận một dòng rỗng ngoài dự kiến.

### 4.2. Tránh lỗi khi trộn nextInt và nextLine

Ví dụ:

```java
try (Scanner scanner = new Scanner("25\nNguyen Van A\n")) {
    int age = scanner.nextInt();
    String name = scanner.nextLine(); // Có thể chỉ nhận phần còn lại sau 25: ""
}
```

`nextInt()` chỉ tiêu thụ token `25`; ký tự newline còn lại vẫn ở trong input. Lệnh `nextLine()` tiếp theo lấy phần còn lại của dòng đó, thường là chuỗi rỗng.

Có thể bỏ phần còn lại của dòng trước khi đọc dòng tiếp theo:

```java
try (Scanner scanner = new Scanner("25\nNguyen Van A\n")) {
    int age = scanner.nextInt();
    scanner.nextLine(); // Bỏ phần còn lại của dòng chứa số.
    String name = scanner.nextLine();
}
```

Một cách khác là đọc tất cả theo dòng rồi phân tích từng trường; cách này thường dễ kiểm soát hơn với dữ liệu nhập theo record.

## 5. Phân biệt lỗi token với lỗi charset

### 5.1. InputMismatchException: token không đúng kiểu hoặc ngoài phạm vi

`nextInt()` ném `InputMismatchException` nếu token kế tiếp không khớp cú pháp số nguyên hoặc giá trị nằm ngoài phạm vi `int`. `InputMismatchException` là lớp con của `NoSuchElementException`, nhưng biểu thị trường hợp token có tồn tại mà không khớp kiểu yêu cầu.

```java
import java.util.InputMismatchException;
import java.util.Scanner;

try (Scanner scanner = new Scanner("abc 42")) {
    try {
        int value = scanner.nextInt();
    } catch (InputMismatchException e) {
        // Token "abc" không phải số nguyên hợp lệ.
        String invalidToken = scanner.next();
        System.out.println("Token không hợp lệ: " + invalidToken);
    }

    int nextValue = scanner.nextInt();
    System.out.println(nextValue); // 42
}
```

Khi `nextInt()` ném `InputMismatchException`, token gây lỗi **không bị tiêu thụ**. Nếu vòng lặp chỉ gọi lại `nextInt()` mà không bỏ qua hoặc xử lý token, chương trình có thể lặp vô hạn trên cùng một token.

Có thể kiểm tra trước:

```java
while (scanner.hasNext()) {
    if (scanner.hasNextInt()) {
        int value = scanner.nextInt();
        process(value);
    } else {
        String invalid = scanner.next();
        reportInvalidToken(invalid);
    }
}
```

`hasNextInt()` không tiêu thụ token; `next()` trong nhánh lỗi mới bỏ token đó để vòng lặp tiếp tục.

### 5.2. NoSuchElementException: không còn dữ liệu

`next()`, `nextInt()` hoặc phương thức `next...()` tương ứng có thể ném `NoSuchElementException` nếu không còn token phù hợp. Đây là trạng thái hết input, khác với việc token tồn tại nhưng sai định dạng.

Dùng `hasNext...()` khi cần kiểm tra trước khi đọc. Với nguồn tương tác như bàn phím hoặc socket, thao tác kiểm tra có thể chờ dữ liệu mới; không phải lúc nào nó cũng trả về ngay.

### 5.3. IllegalStateException: Scanner đã đóng

Sau khi gọi `close()`, các thao tác đọc tiếp theo trên Scanner ném `IllegalStateException`. Không tái sử dụng Scanner sau khi đóng.

### 5.4. IOException từ nguồn đầu vào

Scanner xử lý `IOException` từ `Readable` như kết thúc input. Lỗi I/O gần nhất có thể truy xuất bằng `scanner.ioException()`.

Điều này khác với `InputMismatchException`: một bên là lỗi đọc nguồn, bên kia là token đã đọc được nhưng không phân tích được thành kiểu yêu cầu.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;

try (Scanner scanner = new Scanner(
        Path.of("input.txt"), StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        process(scanner.nextLine());
    }

    IOException sourceFailure = scanner.ioException();
    if (sourceFailure != null) {
        throw sourceFailure;
    }
} catch (IOException e) {
    reportReadFailure(e);
}
```

Với Scanner trên file, kiểm tra `ioException()` sau khi tiêu thụ giúp phát hiện lỗi I/O bị Scanner giữ lại thay vì ném trực tiếp từ `next...()`.

## 6. Malformed bytes: Scanner có thể không báo như lỗi token

Charset được chọn ở constructor Scanner quyết định cách giải mã byte. Tuy nhiên, các constructor Scanner nhận `InputStream`, `File` hoặc `Path` cùng `Charset` không cung cấp tham số để cấu hình `CodingErrorAction` cho decoder.

Với các chuỗi byte không hợp lệ, decoder ở tầng `InputStreamReader` thông thường có thể thay thế bằng ký tự thay thế thay vì làm cho Scanner ném `InputMismatchException`. Kết quả là:

- Token có thể chứa ký tự `�` (replacement character).
- Token không khớp cú pháp mong đợi.
- Scanner có thể báo lỗi token, dù nguyên nhân ban đầu là byte không hợp lệ.
- Nếu dữ liệu sai nằm ở trường văn bản không được parse thành số, lỗi có thể không lộ rõ ngay.

Không nên coi `InputMismatchException` là bằng chứng chắc chắn rằng charset đúng. Nếu ứng dụng cần xác thực dữ liệu byte nghiêm ngặt, hãy cấu hình decoder ở tầng trước Scanner.

### 6.1. Decode nghiêm ngặt bằng CharsetDecoder

```java
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Scanner;

Path path = Path.of("incoming.txt");

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var scanner = new Scanner(
        new InputStreamReader(Files.newInputStream(path), decoder))) {

    while (scanner.hasNextLine()) {
        process(scanner.nextLine());
    }

    // Scanner giữ IOException từ Reader và coi nó như kết thúc input.
    IOException decodeOrReadFailure = scanner.ioException();
    if (decodeOrReadFailure != null) {
        throw decodeOrReadFailure;
    }
}
```

`CodingErrorAction.REPORT` yêu cầu decoder báo lỗi khi gặp chuỗi byte malformed hoặc không thể ánh xạ. `InputStreamReader` phát sinh ngoại lệ I/O khi đọc tới vùng byte lỗi. Scanner có thể ghi nhận lỗi này trong `ioException()` và ngừng đọc như thể đã hết input; vì vậy phải kiểm tra `ioException()` sau khi tiêu thụ stream.

Nếu chỉ dùng `new Scanner(path, StandardCharsets.UTF_8)`, Scanner có charset rõ ràng nhưng không cho ứng dụng chọn chế độ `REPORT` ở constructor. Hãy chọn pipeline decoder riêng khi yêu cầu nghiệp vụ bắt buộc từ chối byte lỗi.

## 7. Locale và radix: quy tắc diễn giải giá trị không phải charset

Charset quyết định byte thành ký tự. Sau đó, Scanner còn phải phân tích token số theo locale và radix.

### 7.1. Locale ảnh hưởng cách đọc số

`nextDouble()` và các phương thức phân tích số có xét locale. Nếu không gọi `useLocale`, Scanner lấy locale mặc định của nhóm `FORMAT` tại thời điểm tạo Scanner. Ví dụ dấu thập phân và dấu phân nhóm có thể khác giữa các locale:

```java
import java.util.Locale;
import java.util.Scanner;

try (Scanner scanner = new Scanner("3.14")) {
    scanner.useLocale(Locale.US);
    double value = scanner.nextDouble();
    System.out.println(value);
}
```

Nếu dữ liệu được quy định theo dấu thập phân dấu chấm, hãy chọn locale tường minh phù hợp, ví dụ `Locale.US` hoặc `Locale.ROOT` tùy định dạng. Không dựa vào locale mặc định của máy người dùng cho một file hoặc giao thức có định dạng cố định.

Locale không thay charset. Một file UTF-8 hợp lệ vẫn có thể chứa token số không khớp locale hiện tại.

### 7.2. Radix ảnh hưởng cách phân tích số nguyên

Radix là cơ số số học, thường là 10, 16 hoặc 8. Nó khác hoàn toàn với charset và locale:

```java
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

try (Scanner scanner = new Scanner("FF 100")) {
    scanner.useRadix(16);

    int first = scanner.nextInt();  // 255
    int second = scanner.nextInt(); // 256
}
```

Nếu chỉ một trường dùng radix khác, có thể truyền radix trực tiếp vào `nextInt(radix)` thay vì thay trạng thái Scanner cho toàn bộ lần đọc.

| Khái niệm | Ví dụ | Ảnh hưởng |
| --- | --- | --- |
| Charset | UTF-8, ISO-8859-1 | Byte thành ký tự |
| Delimiter | whitespace, dấu phẩy | Tách ký tự thành token |
| Locale | `Locale.US`, `Locale.GERMANY` | Cách diễn giải số có quy ước địa phương |
| Radix | 10, 16, 8 | Cơ số của số nguyên |

## 8. Đọc dữ liệu console và vòng đời System.in

Có thể tạo Scanner từ `System.in`:

```java
import java.util.Scanner;

Scanner scanner = new Scanner(System.in);
```

Nhưng constructor này sử dụng default charset của JVM. Với đầu vào terminal, encoding của console có thể có quy tắc riêng. Nếu ứng dụng biết rõ charset của dữ liệu stdin, hãy truyền charset đó:

```java
import java.nio.charset.StandardCharsets;

Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
```

Nếu chương trình tương tác trực tiếp với console, JDK hiện đại cung cấp `System.console()` khi có console tương ứng; `Console.charset()` cho biết charset của console. Cần kiểm tra `System.console()` có thể trả về `null` trong IDE, service, pipeline hoặc môi trường không gắn console.

Một điểm quan trọng về tài nguyên: `Scanner.close()` đóng nguồn bên dưới nếu nguồn đó có thể đóng. Vì vậy, đóng Scanner bọc `System.in` cũng đóng `System.in`. Không nên tạo một Scanner mới cho mỗi phương thức rồi đóng nó nếu các phần khác của ứng dụng còn cần đọc stdin. Với chương trình console nhỏ, có thể giữ một Scanner dùng chung trong suốt vòng đời chương trình và chỉ đóng khi thật sự kết thúc việc đọc.

Với file hoặc stream riêng do phương thức sở hữu, dùng try-with-resources để đóng Scanner và nguồn bên dưới đúng lúc.

## 9. Ví dụ hoàn chỉnh: đọc file CSV đơn giản theo hợp đồng UTF-8

Ví dụ minh họa một file UTF-8, mỗi dòng có ba trường phân tách bằng dấu phẩy. Đây là ví dụ parsing đơn giản, không thay thế parser CSV đầy đủ vì CSV thực tế còn có dấu nháy, dấu phẩy nằm trong trường và newline bên trong quoted field.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;

public class ScannerCsvDemo {
    public static void main(String[] args) {
        Path path = Path.of("users.csv");

        try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
            while (scanner.hasNextLine()) {
                String line = scanner.nextLine();

                try (Scanner fields = new Scanner(line)) {
                    fields.useDelimiter(",");
                    fields.useLocale(java.util.Locale.ROOT);

                    if (!fields.hasNext()) {
                        continue;
                    }

                    String name = fields.next();

                    if (!fields.hasNextInt()) {
                        System.err.println("Age không hợp lệ trong dòng: " + line);
                        continue;
                    }

                    int age = fields.nextInt();

                    if (!fields.hasNext()) {
                        System.err.println("Thiếu status trong dòng: " + line);
                        continue;
                    }

                    String status = fields.next();
                    System.out.printf("%s | %d | %s%n", name, age, status);
                }
            }

            IOException sourceFailure = scanner.ioException();
            if (sourceFailure != null) {
                throw new IOException("Lỗi khi đọc file CSV", sourceFailure);
            }
        } catch (IOException e) {
            System.err.println("Không thể xử lý file: " + e.getMessage());
        }
    }
}
```

Scanner ngoài đọc byte từ file bằng UTF-8 và tách dòng. Scanner bên trong nhận `String` đã decode, nên không cần charset. Delimiter dấu phẩy được áp dụng cho trường trong mỗi dòng. `hasNextInt()` kiểm tra tuổi trước khi gọi `nextInt()` để tránh lỗi token.

Nếu file CSV có quoted fields hoặc quy tắc escape chuẩn, nên dùng thư viện CSV chuyên dụng thay vì tự tách mỗi dòng bằng Scanner.

## 10. Kiểm thử theo từng loại lỗi

Một bộ kiểm thử hữu ích cần tách các lớp nguyên nhân:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| File UTF-8 có tiếng Việt | Giải mã đúng khi dùng `StandardCharsets.UTF_8` |
| File theo ISO-8859-1 | Phải truyền ISO-8859-1 |
| Token `"abc"` đọc bằng `nextInt()` | `InputMismatchException` |
| Hết token rồi gọi `next()` | `NoSuchElementException` |
| Scanner đã đóng rồi gọi `next()` | `IllegalStateException` |
| Số `"3,14"` với locale không phù hợp | Không parse theo quy tắc số mong đợi |
| Radix 16 với token `"FF"` | Giá trị 255 |
| Byte malformed khi dùng decoder `REPORT` | Reader báo lỗi; Scanner ghi nhận qua `ioException()` |

Ví dụ kiểm tra token sai và khôi phục:

```java
import java.util.InputMismatchException;
import java.util.Scanner;

try (Scanner scanner = new Scanner("not-a-number 12")) {
    try {
        scanner.nextInt();
    } catch (InputMismatchException e) {
        String rejected = scanner.next();
        System.out.println("Rejected: " + rejected);
    }

    int valid = scanner.nextInt();
    System.out.println(valid); // 12
}
```

Khi kiểm thử charset, xác minh nội dung Unicode hoặc byte đầu vào theo encoding đã quy định. Khi kiểm thử locale, tạo token số có dấu thập phân/nhóm cụ thể và gọi `useLocale` tường minh. Khi kiểm thử lỗi token, giữ nguyên charset hợp lệ để không trộn hai nguyên nhân.

## 11. Những nhận định dễ nhầm

- **“Java 18 dùng UTF-8 mặc định nên `new Scanner(input)` luôn là lựa chọn tốt.”** Không nhất thiết. API vẫn phụ thuộc default charset; truyền charset theo hợp đồng dữ liệu rõ ràng hơn.
- **“Scanner(String) cần charset.”** Sai. Chuỗi đã là ký tự Java; charset chỉ cần ở bước chuyển byte thành ký tự.
- **“Locale quyết định cách giải mã byte.”** Sai. Locale chỉ tác động việc phân tích giá trị có quy ước địa phương sau khi đã có ký tự.
- **“InputMismatchException nghĩa là file bị sai charset.”** Không. Nó chỉ cho biết token hiện tại không khớp kiểu hoặc phạm vi; nguyên nhân có thể là dữ liệu sai, locale hoặc radix.
- **“hasNextInt() tiêu thụ token.”** Sai. Phương thức kiểm tra trước, token vẫn còn cho `nextInt()` hoặc `next()`.
- **“Scanner tự đóng khi gọi count hoặc hết dữ liệu.”** Scanner không phải Stream; phải đóng Scanner theo quyền sở hữu nguồn.
- **“Scanner luôn ném IOException khi nguồn đọc lỗi.”** Sai. Scanner giữ lỗi gần nhất trong `ioException()` và có thể coi lỗi đó như kết thúc input.
- **“Truyền Charset cho Scanner đồng nghĩa có thể yêu cầu decoder REPORT.”** Sai. Nếu cần kiểm soát hành vi malformed/unmappable, cấu hình `CharsetDecoder` ở Reader bên dưới.
- **“nextLine() giống next() nhưng lấy token dài hơn.”** Sai. `nextLine()` lấy phần còn lại của dòng, độc lập với delimiter token.

## 12. Tài liệu tham khảo chính thức

- [Scanner — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html): constructor nhận `Charset`, token, locale, radix, `ioException()` và vòng đời.
- [CharsetDecoder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html): `CodingErrorAction.REPORT` và xử lý byte malformed/unmappable.
- [InputStreamReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStreamReader.html): giải mã byte theo charset hoặc decoder.
- [Locale — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): locale và các quy tắc định dạng.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18 và các điểm tương thích.

