# `Scanner` với `InputStream` và `Charset` (Java 10+)

## 1. Bài toán: đọc byte thành văn bản đúng mã hóa

`InputStream` cung cấp **các byte**, chưa phải ký tự Unicode. Khi đọc văn bản từ tệp, kết nối mạng, bộ nhớ hoặc đầu vào chuẩn, ứng dụng cần biết **charset** mà phía tạo dữ liệu đã dùng để mã hóa các ký tự thành byte.

Từ **Java 10**, lớp `java.util.Scanner` có constructor nhận trực tiếp `java.nio.charset.Charset`:

```java
Scanner scanner = new Scanner(inputStream, StandardCharsets.UTF_8);
```

Đây là đoạn mã minh họa trong một phương thức; `inputStream` là một `InputStream` đã được tạo và còn mở. Cần import `java.util.Scanner` và `java.nio.charset.StandardCharsets`.

Bằng cách truyền `StandardCharsets.UTF_8`, ta nói rõ cách giải mã byte. `Scanner` tiếp đó có thể **đọc từng dòng**, **tách token theo delimiter**, hoặc **chuyển token thành số**.

**Nguyên tắc quan trọng:** Charset kiểm soát **byte → ký tự**, trong khi delimiter, locale và những phương thức như `nextInt()` kiểm soát **ký tự → token/giá trị**. Các bước này khác nhau và cần được cấu hình đúng theo hợp đồng dữ liệu.

API này vẫn là Java hiện hành; không cần dùng tên charset dạng chuỗi khi đã có sẵn object `Charset`.

## 2. Constructor được bổ sung ở Java 10 và các dạng liên quan

Chữ ký được Java SE công bố:

```java
public Scanner(InputStream source, Charset charset)
```

Đây là **chữ ký constructor của JDK**, không phải phương thức tự viết. Nó được đánh dấu `Since: 10` trong Javadoc.

Các cách khởi tạo thường gặp:

| Cách tạo | Nguồn | Cách xác định charset |
| --- | --- | --- |
| `new Scanner(in)` | `InputStream` | Theo mặc định mà API/runtime sử dụng; không biểu đạt rõ giao thức của nguồn |
| `new Scanner(in, "UTF-8")` | `InputStream` | Theo **tên** charset dạng String |
| `new Scanner(in, StandardCharsets.UTF_8)` | `InputStream` | Theo **object Charset** cụ thể; constructor từ Java 10 |
| `new Scanner(path, StandardCharsets.UTF_8)` | `Path` | Mở tệp tại `Path` rồi giải mã bằng Charset; constructor cũng có từ Java 10 |
| `new Scanner(reader)` | `Readable` như `Reader` | Dữ liệu đã được giải mã thành ký tự ở tầng Reader |

Điểm mạnh của overload nhận `Charset`:

- Có thể dùng hằng số type-safe như `StandardCharsets.UTF_8`, `ISO_8859_1`, `UTF_16`.
- Không phải lặp lại tên mã hóa dưới dạng chuỗi và tránh lỗi viết sai tên khi đã biết charset từ trước.
- Nếu charset được chọn động ở một bước cấu hình, có thể truyền object `Charset` đã được xác nhận, tái sử dụng cùng cấu hình.
- Dùng trực tiếp với stream có sẵn: `Files.newInputStream(path)`, `ByteArrayInputStream` hay một InputStream nhận từ API.

Đừng nhầm với `new Scanner(String source)`: overload đó nhận **chính nội dung văn bản** để quét, **không phải tên đường dẫn tệp**. `new Scanner("data.txt")` sẽ quét các ký tự trong chuỗi `"data.txt"`.

## 3. Luồng xử lý: mã hóa và giải mã phải khớp nhau

Có thể hình dung quy trình:

```text
Text nguồn: "Tiếng Việt"
   |
   |  mã hóa, ví dụ UTF-8
   v
Chuỗi byte trong InputStream
   |
   |  Scanner(InputStream, Charset UTF-8)
   v
Ký tự Java (Unicode)
   |
   +--> nextLine()  : dòng văn bản
   +--> next()      : token
   +--> nextInt()   : số nguyên từ token, còn phụ thuộc locale/radix
```

Nếu byte được mã hóa theo UTF-8 nhưng lại giải mã bằng ISO-8859-1, các ký tự tiếng Việt có dấu **có thể sai**. Chọn `StandardCharsets.UTF_8` trong code không thể tự biến một nguồn ISO-8859-1 thành UTF-8; charset là **thỏa thuận với nơi tạo dữ liệu**.

Ví dụ tối thiểu với dữ liệu UTF-8 trong bộ nhớ:

```java
String message = "Xin chào Việt Nam";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);

try (Scanner scanner = new Scanner(
        new ByteArrayInputStream(bytes),
        StandardCharsets.UTF_8)) {
    String decoded = scanner.nextLine();
    System.out.println(message.equals(decoded)); // true
}
```

Đoạn trên cần `java.io.ByteArrayInputStream`, `java.nio.charset.StandardCharsets` và `java.util.Scanner`. `getBytes(UTF_8)` ở bên ghi và `Scanner(..., UTF_8)` ở bên đọc **dùng cùng chuẩn**; vì vậy nội dung Unicode được khôi phục chính xác.

Không dùng `new String(bytes)` hoặc `text.getBytes()` không tham số trong các ví dụ cần đảm bảo tính di động, vì chúng không tự diễn đạt charset của giao thức dữ liệu. Trên các JDK hiện đại, mặc định có thể là UTF-8, nhưng vẫn nên chỉ rõ charset **ở ranh giới I/O** khi định dạng dữ liệu yêu cầu.

## 4. Dùng `StandardCharsets` thay vì tên String khi biết trước bộ mã

`StandardCharsets` có các hằng số charset chuẩn và luôn được hỗ trợ theo Java:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset utf8 = StandardCharsets.UTF_8;
Charset latin1 = StandardCharsets.ISO_8859_1;
Charset ascii = StandardCharsets.US_ASCII;
Charset utf16 = StandardCharsets.UTF_16;
```

Đây là các khai báo minh họa trong một phương thức. Các hằng số này tránh phải tra cứu tên tại runtime. Nếu cần charset khác do dữ liệu quyết định, có thể dùng:

```java
Charset selected = Charset.forName(configuredName);
Scanner scanner = new Scanner(inputStream, selected);
```

Đoạn này giả định `configuredName` là tên charset từ cấu hình và `inputStream` còn mở. `Charset.forName` có thể ném ngoại lệ khi tên không hợp lệ hoặc charset không được hỗ trợ; ứng dụng nên xử lý lỗi **cấu hình** tại ranh giới, không âm thầm đoán charset khác.

**Phân biệt những lỗi sau:**

- Tên charset không tồn tại: lỗi **chọn cấu hình**, có thể phát sinh tại `Charset.forName(...)` hoặc overload nhận tên `String`.
- Byte được giải mã bằng charset không đúng: dữ liệu có thể bị **mojibake** (ký tự hiển thị sai) mà không nhất thiết có ngoại lệ.
- Dữ liệu có byte không hợp lệ theo charset: tùy cơ chế decoder, ký tự có thể được thay thế hoặc cần xử lý lỗi theo chính sách nghiêm ngặt.

Nếu cần **phát hiện chính xác byte hỏng và từ chối file**, hãy thiết kế bước giải mã kiểm soát bằng `CharsetDecoder` với `CodingErrorAction.REPORT` ở tầng đọc phù hợp, thay vì mặc định `Scanner` là bộ xác thực encoding nghiêm ngặt.

## 5. Ví dụ đọc theo dòng: `hasNextLine()` và `nextLine()`

Với dữ liệu văn bản gồm nhiều dòng, `nextLine()` thường dễ hiểu nhất:

```java
String text = "Tên: An\nĐịa điểm: Hà Nội\n";
byte[] data = text.getBytes(StandardCharsets.UTF_8);

try (var scanner = new Scanner(
        new ByteArrayInputStream(data),
        StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        String line = scanner.nextLine();
        System.out.println(line);
    }
}
```

Cần import `java.util.Scanner`, `ByteArrayInputStream` và `StandardCharsets`. Hai dòng được in đúng với dấu tiếng Việt nếu môi trường **xuất** nội dung console cũng hỗ trợ các ký tự đó; encoding của **đầu ra console** là một vấn đề riêng với charset của InputStream nguồn.

Cần nhớ:

- `hasNextLine()` kiểm tra còn dòng đọc được hay không; nó có thể **chờ dữ liệu** nếu nguồn là stream đang mở và chưa nhận đủ dữ liệu.
- `nextLine()` đọc phần còn lại của dòng hiện tại và đi qua ký tự kết thúc dòng; giá trị trả về **không bao gồm** dấu kết thúc dòng.
- Nếu đọc khi không còn dòng, `nextLine()` có thể ném `NoSuchElementException`.
- Không phải mọi chuỗi nhiều từ đều nên đọc bằng `next()`: `next()` chỉ lấy token theo delimiter; mặc định delimiter nhận các ký tự khoảng trắng.

Với một tên chứa khoảng trắng như `"Nguyễn Văn An"`, `nextLine()` phù hợp để đọc **cả tên**. `next()` mặc định có thể tách tên ấy thành nhiều token.

## 6. Ví dụ đọc token và phân tích số

`Scanner` thường được dùng cho dữ liệu “một dòng có nhiều trường đơn giản”, chẳng hạn:

```text
coffee 3 12.50
```

Đọc như sau:

```java
byte[] data = "coffee 3 12.50".getBytes(StandardCharsets.UTF_8);

try (var scanner = new Scanner(
        new ByteArrayInputStream(data),
        StandardCharsets.UTF_8)) {
    scanner.useLocale(Locale.ROOT);

    String item = scanner.next();
    int count = scanner.nextInt();
    double price = scanner.nextDouble();

    System.out.printf(Locale.ROOT,
            "item=%s,count=%d,price=%.2f%n", item, count, price);
}
```

Đoạn cần import `java.util.Locale`, `Scanner`, `ByteArrayInputStream`, `StandardCharsets`.

Kết quả:

```text
item=coffee,count=3,price=12.50
```

`Scanner` mặc định dùng delimiter dựa trên **khoảng trắng** khi tách token. `next()` lấy token `coffee`; `nextInt()` đọc `3`; `nextDouble()` đọc `12.50`.

Vì sao phải `useLocale(Locale.ROOT)`? Cú pháp số được `Scanner` phân tích **phụ thuộc locale**. Ở một số locale, dấu phẩy là dấu thập phân và dấu chấm có thể mang vai trò khác. Với định dạng trao đổi dữ liệu đã quy định dấu thập phân là `.`, cấu hình `Locale.ROOT` giúp ví dụ có kết quả ổn định.

**Charset không thay thế Locale**. Charset diễn giải byte thành ký tự; Locale ảnh hưởng cách `nextDouble()`, `nextInt()` và các phương thức liên quan nhận biết biểu diễn số.

Ví dụ `double` chỉ để minh họa parser. Với số tiền cần tính toán chính xác, hãy cân nhắc `BigDecimal` hoặc cấu trúc số phù hợp nghiệp vụ thay vì mặc định dùng floating point nhị phân.

## 7. Delimiter là biểu thức chính quy

Muốn tách dữ liệu cách nhau bằng dấu phẩy đơn giản:

```java
byte[] data = "A, B, C".getBytes(StandardCharsets.UTF_8);

try (var scanner = new Scanner(
        new ByteArrayInputStream(data),
        StandardCharsets.UTF_8)) {
    scanner.useDelimiter("\\s*,\\s*");

    while (scanner.hasNext()) {
        System.out.println("token=" + scanner.next());
    }
}
```

Kết quả:

```text
token=A
token=B
token=C
```

Trong Java String, `"\\s*,\\s*"` là regex nhận dấu phẩy có hoặc không có khoảng trắng hai bên. `useDelimiter(...)` **không thay charset** và **không đổi byte nguồn**; nó chỉ điều chỉnh cách Scanner phân tách ký tự đã giải mã.

**Không dùng `useDelimiter(",")` như bộ phân tích CSV hoàn chỉnh** nếu dữ liệu có dấu phẩy bên trong dấu nháy, quote escaping, hoặc dòng nhiều trường phức tạp. Với CSV thực tế, nên dùng parser CSV hỗ trợ đầy đủ định dạng.

Mỗi lần gọi `useDelimiter` sẽ đặt delimiter mới cho scanner. Các thao tác như `findInLine` có quy tắc riêng; không phải mọi phương thức tìm kiếm của Scanner đều chịu ảnh hưởng bởi delimiter.

## 8. Bẫy khi dùng `nextInt()` rồi `nextLine()`

`nextInt()` tiêu thụ **token số**, nhưng thường không tiêu thụ phần kết thúc dòng. Vì vậy, ngay sau `nextInt()`, lời gọi `nextLine()` có thể trả về chuỗi rỗng/phần còn lại của **chính dòng đó**.

Ví dụ nguồn:

```text
42
Full Name
```

Cách đọc đúng khi số nằm trọn trên một dòng:

```java
byte[] data = "42\nFull Name\n"
        .getBytes(StandardCharsets.UTF_8);

try (var scanner = new Scanner(
        new ByteArrayInputStream(data), StandardCharsets.UTF_8)) {
    int id = scanner.nextInt();
    scanner.nextLine(); // tiêu thụ phần còn lại của dòng chứa id
    String name = scanner.nextLine();
    System.out.println("id=" + id + ";name=" + name);
}
```

Kết quả:

```text
id=42;name=Full Name
```

**Không thêm `nextLine()` “bù” một cách máy móc** nếu cấu trúc dữ liệu không giống ví dụ. Chẳng hạn một dòng có cả id và tên ở phía sau, `nextLine()` ngay sau `nextInt()` có thể chứa chính phần tên đó; gọi bỏ qua sẽ làm mất dữ liệu.

Một chiến lược khác dễ kiểm soát là **đọc một dòng trước rồi parse** nội dung của dòng bằng `Integer.parseInt` hoặc một Scanner riêng. Quyết định theo định dạng đầu vào, không theo mẹo thuộc lòng.

## 9. Quản lý vòng đời: đóng Scanner cũng đóng nguồn

`Scanner` triển khai `Closeable`, vì vậy nên dùng **try-with-resources** khi ứng dụng sở hữu tài nguyên nguồn:

```java
try (Scanner scanner = new Scanner(
        Files.newInputStream(path),
        StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        String line = scanner.nextLine();
        // Xử lý line.
    }
}
```

Đây là đoạn minh họa trong một phương thức có khai báo hoặc xử lý `IOException` khi mở file; cần import `java.nio.file.Files`, `Path`, `java.util.Scanner`, `StandardCharsets`.

Theo Javadoc, khi `Scanner.close()` chạy, nó sẽ **đóng nguồn đọc nếu nguồn triển khai `Closeable`**. `InputStream` triển khai `Closeable`, nên việc đóng Scanner thường cũng đóng stream mà nó bao bọc.

Ưu điểm của try-with-resources:

- Đóng tài nguyên kể cả khi code trong khối ném exception.
- Đặt rõ phạm vi sở hữu và sử dụng Scanner.
- Không cần gọi `scanner.close()` thủ công trên mọi đường rẽ của hàm.

**Cảnh báo với `System.in`:** nếu tạo `Scanner` bao `System.in` rồi đóng Scanner, đầu vào chuẩn của tiến trình cũng bị đóng. Nếu `System.in` còn được các thành phần khác sử dụng, hãy thiết kế rõ **ai sở hữu và có quyền đóng** nguồn này. Không áp dụng try-with-resources trên stream mượn từ nơi khác mà không xem hợp đồng quyền sở hữu.

Ngoài ra, sau khi Scanner đã đóng, gọi các thao tác quét tiếp có thể ném `IllegalStateException`.

## 10. Ví dụ mở tệp UTF-8 bằng InputStream và kiểm tra lỗi I/O

Với đường dẫn `Path`, có thể chủ động mở `InputStream` rồi chuyển cho Scanner:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Scanner;

static List<String> readUtf8Lines(Path path) throws IOException {
    try (Scanner scanner = new Scanner(
            Files.newInputStream(path), StandardCharsets.UTF_8)) {

        var lines = new ArrayList<String>();
        while (scanner.hasNextLine()) {
            lines.add(scanner.nextLine());
        }

        IOException error = scanner.ioException();
        if (error != null) {
            throw error;
        }
        return List.copyOf(lines);
    }
}
```

Đây là **phương thức minh họa** cần đặt trong một lớp. Lệnh `Files.newInputStream(path)` có thể ném `IOException` khi mở file. Scanner xử lý việc giải mã nội dung tệp theo UTF-8.

**Điểm quan trọng:** nếu đối tượng `Readable` bên dưới ném `IOException` trong khi quét, Javadoc cho biết Scanner sẽ **coi như đã đến cuối nguồn**; có thể lấy ngoại lệ gần nhất qua `scanner.ioException()`. Nếu ứng dụng cần phân biệt **kết thúc file bình thường** và **đọc bị lỗi**, phải kiểm tra `ioException()` sau vòng lặp.

Phương thức trên tạo List kết quả không sửa được bằng `List.copyOf` khi đọc thành công. Vì `nextLine()` trả chuỗi không null, bước này hợp lệ về ràng buộc null. Không nên mặc định `ioException() == null` đồng nghĩa mọi nội dung đầu vào đúng **định dạng nghiệp vụ**: việc đó cần validator/parser riêng.

Cần chú ý: `Scanner` không phải giải pháp tối ưu mặc định cho **mọi** tệp văn bản. Khi chỉ đọc từng dòng và cần throughput cao, `Files.newBufferedReader(path, charset)` hoặc `BufferedReader` có thể đơn giản/hữu ích hơn. `Scanner` tỏ ra thuận tiện khi cần thêm **tách token, regex delimiter, parse số**.

## 11. `System.in`: charset của bàn phím/terminal có thể khác mặc định

`System.in` là một `InputStream`. Về mặt cú pháp, có thể tạo:

```java
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
```

Nhưng điều này **chỉ đúng về nội dung** nếu byte mà terminal hoặc quá trình cấp đầu vào gửi tới `System.in` thực sự được mã hóa theo UTF-8. Một số môi trường có cơ chế charset riêng cho standard input, có thể thể hiện qua `stdin.encoding` và khác charset mặc định của Java.

Hãy xác định charset từ **hợp đồng đầu vào thực tế**, không áp đặt UTF-8 chỉ vì chương trình hiện đại thường dùng UTF-8. Khi làm công cụ dòng lệnh, có thể cần tham khảo cấu hình console/stdin của môi trường thực thi.

Về quản lý tài nguyên: không đóng Scanner bao `System.in` nếu chương trình hoặc module khác vẫn cần đọc đầu vào chuẩn sau đó. Có thể quản lý một Scanner dùng chung ở điểm sở hữu vòng đời của ứng dụng. `Scanner` **không an toàn khi chia sẻ giữa nhiều luồng** nếu không có đồng bộ thích hợp, nên tránh để nhiều thành phần tự tạo Scanner cùng đọc cạnh tranh từ `System.in`.

## 12. Ngoại lệ cần phân biệt trong xử lý InputStream

| Tình huống | Hành vi có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Truyền `null` làm `source` hoặc `charset` | `NullPointerException` | Kiểm tra các tham số cần thiết ngay tại ranh giới |
| Không có token tiếp theo và gọi `next()` | `NoSuchElementException` | Dùng `hasNext()` khi format cho phép hết dữ liệu |
| Không có dòng và gọi `nextLine()` | `NoSuchElementException` | Dùng `hasNextLine()` |
| Token không hợp lệ cho `nextInt()`/`nextDouble()` | `InputMismatchException` | Xác thực `hasNextInt()`/`hasNextDouble()` hoặc xử lý lỗi parse |
| Gọi phương thức quét sau khi đóng | `IllegalStateException` | Không dùng lại Scanner đã đóng |
| Lỗi `IOException` ở nguồn đọc bên dưới | Scanner có thể coi là kết thúc dữ liệu; lưu lỗi để truy xuất qua `ioException()` | Kiểm tra `scanner.ioException()` |
| Mã hóa nguồn không khớp charset dùng để đọc | Dữ liệu giải mã sai, không nhất thiết có ngoại lệ | Quy định charset đầu vào; kiểm tra dữ liệu tại boundary |
| Bỏ qua locale của dữ liệu số | `nextDouble()`/`nextInt()` có thể không nhận số đúng | Chọn `useLocale` theo định dạng nguồn |
| Đóng Scanner trên `System.in` trong khi nơi khác còn dùng | Đóng luôn standard input | Quy định quyền sở hữu stream rõ ràng |

**Không nhầm ba tầng lỗi:** (1) mở/đọc byte, (2) giải mã charset, (3) parse token/định dạng. Chúng có nguyên nhân và cơ chế xử lý khác nhau.

## 13. Chương trình đầy đủ chạy với Java 17+ và kiểm tra được output

Tạo tệp `ScannerCharsetDemo.java`. Để kết quả minh họa ổn định ngay cả trên terminal có bảng mã đầu ra khác nhau, chương trình kiểm tra nội dung Unicode bằng **so sánh Boolean**, thay vì bắt buộc console phải in ký tự tiếng Việt có dấu. Các chuỗi chứa `\u` escape hợp lệ của Java để bảo đảm mã nguồn minh họa không phụ thuộc encoding của tệp nguồn.

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Scanner;

public class ScannerCharsetDemo {

    static Scanner utf8Scanner(String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        return new Scanner(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8);
    }

    public static void main(String[] args) {
        // "Tiếng Việt: cà phê" biểu diễn bằng Unicode escape
        String expected = "Ti\u1EBFng Vi\u1EC7t: c\u00E0 ph\u00EA";
        byte[] bytes = (expected + "\n").getBytes(StandardCharsets.UTF_8);

        try (var scanner = new Scanner(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8)) {

            System.out.println("utf8RoundTrip="
                    + scanner.nextLine().equals(expected));
            System.out.println("ioExceptionIsNull="
                    + (scanner.ioException() == null));
        }

        // Cùng byte UTF-8 nhưng cố tình giải mã theo ISO-8859-1
        try (var scanner = new Scanner(
                new ByteArrayInputStream(bytes),
                StandardCharsets.ISO_8859_1)) {

            System.out.println("wrongCharsetMatches="
                    + scanner.nextLine().equals(expected));
        }

        // Đọc các token và số dưới locale xác định
        try (var scanner = utf8Scanner("coffee 3 12.50")) {
            scanner.useLocale(Locale.ROOT);

            String item = scanner.next();
            int count = scanner.nextInt();
            double price = scanner.nextDouble();

            System.out.printf(Locale.ROOT,
                    "item=%s,count=%d,price=%.2f%n",
                    item, count, price);
        }

        // Dữ liệu ISO-8859-1 cần được đọc đúng bằng ISO-8859-1
        byte[] latin1 = "Caf\u00E9".getBytes(
                StandardCharsets.ISO_8859_1);

        try (var scanner = new Scanner(
                new ByteArrayInputStream(latin1),
                StandardCharsets.ISO_8859_1)) {

            System.out.println("latin1RoundTrip="
                    + scanner.nextLine().equals("Caf\u00E9"));
        }

        // Delimiter tùy chỉnh cho các giá trị đơn giản
        try (var scanner = utf8Scanner("A, B, C")) {
            scanner.useDelimiter("\\s*,\\s*");

            while (scanner.hasNext()) {
                System.out.println("token=" + scanner.next());
            }
        }

        // Trộn nextInt() và nextLine(): phải tiêu thụ cuối dòng
        try (var scanner = utf8Scanner("42\nFull Name\n")) {
            int id = scanner.nextInt();
            scanner.nextLine();

            String name = scanner.nextLine();
            System.out.println("id=" + id + ";name=" + name);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ScannerCharsetDemo.java
java ScannerCharsetDemo
```

Output:

```text
utf8RoundTrip=true
ioExceptionIsNull=true
wrongCharsetMatches=false
item=coffee,count=3,price=12.50
latin1RoundTrip=true
token=A
token=B
token=C
id=42;name=Full Name
```

**Đối chiếu từng kết quả:**

1. `utf8RoundTrip=true`: byte được mã hóa UTF-8 và Scanner giải mã UTF-8 nên chuỗi Unicode khớp.
2. `ioExceptionIsNull=true`: trong ví dụ đọc `ByteArrayInputStream` bình thường, không có lỗi I/O được báo qua Scanner.
3. `wrongCharsetMatches=false`: cố tình giải mã byte UTF-8 bằng ISO-8859-1 cho ra nội dung khác, minh họa tác hại của charset không khớp.
4. `item=coffee,count=3,price=12.50`: delimiter mặc định và `Locale.ROOT` phân tích token/số thành công.
5. `latin1RoundTrip=true`: cùng một charset ISO-8859-1 ở cả phía mã hóa/giải mã khôi phục đúng ký tự có dấu.
6. Ba dòng `token=A`, `token=B`, `token=C`: delimiter dấu phẩy hoạt động đúng với dữ liệu đơn giản.
7. `id=42;name=Full Name`: tiêu thụ phần cuối dòng sau `nextInt()` để đọc đúng dòng tên tiếp theo.

Chương trình không cần file đầu vào, môi trường mạng hoặc thư viện ngoài. `ByteArrayInputStream` giúp kiểm tra riêng phần **charset và parse** một cách xác định.

## 14. Cách viết unit test cho charset và Scanner

Khi kiểm tra code nhận `InputStream` từ bên ngoài, nên tạo byte bằng **charset xác định** ngay trong test:

```java
static String readFirstLine(
        byte[] bytes, java.nio.charset.Charset charset) {

    try (var scanner = new Scanner(
            new ByteArrayInputStream(bytes), charset)) {
        return scanner.nextLine();
    }
}
```

Đây là phương thức minh họa cần đặt trong lớp và cần import `java.util.Scanner` cùng `java.io.ByteArrayInputStream`.

Test tích cực:

```java
String expected = "Ti\u1EBFng Vi\u1EC7t";
byte[] utf8 = expected.getBytes(StandardCharsets.UTF_8);

if (!expected.equals(readFirstLine(utf8, StandardCharsets.UTF_8))) {
    throw new AssertionError("UTF-8 round trip failed");
}
```

Test âm tính cho charset sai:

```java
if (expected.equals(
        readFirstLine(utf8, StandardCharsets.ISO_8859_1))) {
    throw new AssertionError("Wrong charset unexpectedly matched");
}
```

Các phép kiểm tra trên chứng minh kết quả khác nhau đối với **chuỗi mẫu cụ thể**, không có nghĩa mọi chuỗi ASCII sẽ khác nhau giữa UTF-8 và ISO-8859-1: **ASCII thuần** có thể giống hệt nhau trong cả hai bộ mã. Muốn phát hiện lỗi cấu hình, dùng đầu vào chứa những ký tự phân biệt charset như chuỗi tiếng Việt có dấu trong ví dụ.

Ngoài ra, nên test:

- Empty stream: `hasNextLine()` có thể trả `false`; gọi trực tiếp `nextLine()` sẽ không có dòng.
- Nhiều dòng và dòng rỗng; xác minh `nextLine()` giữ đúng nội dung dòng.
- Token số hợp lệ và không hợp lệ; xác minh `hasNextInt()` hoặc `InputMismatchException`.
- Input chứa delimiter tùy chỉnh; xác minh số token đúng, không coi format đơn giản như CSV hoàn chỉnh.
- Stream bị lỗi I/O; nếu ứng dụng cần phân biệt EOF và lỗi đọc, xác minh logic `ioException()`.
- Quyền sở hữu stream: code phải đóng tài nguyên mà mình sở hữu, không đóng nguồn dùng chung khi hợp đồng không cho phép.

## 15. Lưu ý về hiệu năng và an toàn luồng

`Scanner` cung cấp parser tiện lợi dựa trên regular expression, locale và token. Chi phí này thường phù hợp với công cụ dòng lệnh, input có cấu trúc đơn giản, tệp nhỏ và các bài kiểm thử. Nhưng nếu chỉ cần đọc hàng triệu dòng văn bản mà không parse token theo quy tắc Scanner, `BufferedReader`/`Files.newBufferedReader` hoặc những API đọc theo dòng có thể là lựa chọn dễ tối ưu hơn tùy workload.

**Scanner không an toàn cho nhiều luồng cùng thao tác mà không có đồng bộ bên ngoài.** Đừng để hai luồng gọi `next()`/`nextLine()` trên cùng một Scanner và kỳ vọng mỗi luồng tự nhận một phần dữ liệu có trật tự.

Với nguồn từ network, `hasNext()` hoặc `hasNextLine()` có thể chờ dữ liệu và không nên được coi là thao tác kiểm tra không chặn. Hãy thiết kế timeout và ranh giới tài nguyên ở tầng stream/network phù hợp, chứ `Scanner(InputStream, Charset)` không tự cấp timeout cho I/O.

## 16. Những lỗi thường gặp

| Hiểu nhầm hoặc cách viết | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| `new Scanner(in)` khi định dạng file yêu cầu UTF-8 | Phụ thuộc charset mặc định/môi trường | Chỉ định `StandardCharsets.UTF_8` nếu dữ liệu thực sự là UTF-8 |
| `new Scanner(in, "utf8-typo")` | Tên charset sai hoặc không được hỗ trợ | Dùng `StandardCharsets.UTF_8` hoặc `Charset.forName` kèm validation |
| Mã hóa UTF-8 nhưng đọc ISO-8859-1 | Chuỗi Unicode giải mã khác dữ liệu gốc | Đảm bảo charset ở hai đầu khớp với chuẩn nguồn |
| Dùng `next()` để đọc tên nhiều từ | Mất phần văn bản sau whitespace | Dùng `nextLine()` khi cần cả dòng |
| Gọi `nextLine()` ngay sau `nextInt()` rồi hiểu kết quả rỗng là lỗi encoding | Vẫn còn phần cuối dòng sau token số | Thiết kế ranh giới token/dòng, tiêu thụ cuối dòng đúng lúc |
| Đọc `nextDouble()` mà không cấu hình locale theo định dạng | Parsing số không ổn định giữa môi trường | `useLocale(Locale.ROOT)` hoặc locale hợp đồng |
| Gọi `nextInt()` khi token không phải số | `InputMismatchException` | Kiểm tra `hasNextInt()` hoặc xử lý exception |
| Tưởng `Scanner.close()` chỉ đóng wrapper | Có thể đóng luôn InputStream | Quản lý quyền sở hữu và try-with-resources đúng cách |
| Đóng Scanner trên `System.in` rồi muốn tiếp tục đọc | Standard input đã bị đóng | Không đóng nguồn dùng chung khi nó còn được cần |
| Tưởng `hasNextLine()` không bao giờ block | InputStream mạng/interactive có thể chờ dữ liệu | Có chính sách timeout tại tầng nguồn |
| Tưởng `Scanner` luôn ném ngay `IOException` từ nguồn | Scanner có thể xử lý như EOF | Xem `ioException()` khi cần báo lỗi đọc |
| Dùng delimiter dấu phẩy cho CSV có dấu quote và escape | Tách sai trường | Dùng CSV parser thích hợp |
| Dùng Scanner từ nhiều luồng | Không thread-safe | Phân quyền một consumer hoặc đồng bộ phù hợp |
| Gặp Unicode sai rồi chỉ đổi locale | Locale không sửa lỗi decode byte | Kiểm tra charset của byte nguồn, không phải locale |
| Mặc định mọi byte hỏng đều ném ngoại lệ | Decoder có thể thay thế dữ liệu không hợp lệ | Dùng `CharsetDecoder` với chính sách báo lỗi nếu cần strict validation |

## 17. Bài tập tự kiểm tra

### Câu 1: Constructor nào thể hiện rõ mã hóa?

```java
Scanner a = new Scanner(input);
Scanner b = new Scanner(input, StandardCharsets.UTF_8);
```

**Đáp án:** `b` chỉ rõ charset UTF-8 bằng đối tượng `Charset`, dùng overload có từ Java 10. `a` không mô tả rõ encoding của nguồn. Trong thực tế, không nên dùng **hai Scanner đọc cạnh tranh từ cùng một InputStream** như hai lệnh này cùng lúc; đoạn trên chỉ minh họa chữ ký.

### Câu 2: Vì sao một chuỗi ASCII không phát hiện được charset sai?

```java
byte[] bytes = "ABC".getBytes(StandardCharsets.UTF_8);
```

Nếu dùng ISO-8859-1 để đọc, có nhất thiết khác `"ABC"` không?

**Đáp án:** Không. Các byte biểu diễn `"ABC"` giống nhau ở các charset được nêu, nên test chỉ dùng ASCII có thể **không phát hiện** việc chọn sai charset. Hãy đưa ký tự không thuộc ASCII vào test, ví dụ tiếng Việt có dấu.

### Câu 3: `nextInt` rồi `nextLine`

Nguồn:

```text
5
Nguyen Van A
```

Sau `int n = scanner.nextInt();`, gọi `scanner.nextLine()` một lần trả gì?

**Đáp án:** Nó đọc phần còn lại của **dòng chứa số `5`**, trong ví dụ là chuỗi rỗng. Phải đọc tiếp dòng tên nếu format xác nhận rằng số và tên nằm trên hai dòng tách biệt.

### Câu 4: Ai đóng stream?

```java
try (var scanner = new Scanner(
        Files.newInputStream(path), StandardCharsets.UTF_8)) {
    // ...
}
```

**Đáp án:** `Scanner` được đóng tự động khi ra khỏi try. Nó cũng đóng nguồn InputStream của mình vì nguồn triển khai `Closeable`. Với stream mượn như `System.in`, phải cân nhắc quyền sở hữu thay vì tùy tiện áp dụng mẫu này.

### Câu 5: Phân biệt lỗi đọc và hết tệp

Một Scanner đang đọc một InputStream, rồi `hasNextLine()` trả false. Có thể kết luận file kết thúc bình thường không?

**Đáp án:** Chưa chắc. Javadoc nói khi nguồn đọc ném `IOException`, Scanner có thể coi đó là kết thúc đầu vào; hãy xem `scanner.ioException()` nếu ứng dụng cần biết đã có lỗi đọc hay chưa.

### Câu 6: Hai tầng cấu hình

Dữ liệu đầu vào là UTF-8 và số thực dùng dấu phẩy, ví dụ `"3,14"`. Đổi charset sang ISO-8859-1 có giải quyết được việc `nextDouble()` không đọc đúng số không?

**Đáp án:** Không. Charset giải mã byte; **locale hoặc quy tắc parsing số** giải quyết dấu thập phân. Giữ UTF-8 cho đầu vào UTF-8, đồng thời chọn locale phù hợp với định dạng số hoặc parse bằng một quy tắc định dạng riêng.

## 18. Checklist áp dụng ở ranh giới I/O

1. Xác nhận **ai tạo dữ liệu** và charset của byte đầu vào.
2. Dùng `new Scanner(inputStream, charset)` từ Java 10 để ghi rõ hợp đồng giải mã.
3. Ưu tiên `StandardCharsets.UTF_8` khi định dạng thực sự là UTF-8; không chọn vì thói quen nếu nguồn dùng charset khác.
4. Quy định dữ liệu cần đọc theo **dòng** hay **token**; đừng nhầm `nextLine()` với `next()`.
5. Nếu đọc số, xác định **locale** và **radix** đúng với định dạng nguồn.
6. Nếu có delimiter tùy chỉnh, nhớ đó là **regex**, không tự giải quyết các quy tắc trích dẫn phức tạp.
7. Kiểm tra điều kiện còn dữ liệu bằng `hasNext...()` nếu nguồn có thể kết thúc sớm; xử lý `InputMismatchException` khi dữ liệu sai.
8. Đặt chính sách sở hữu stream: đóng Scanner khi bạn sở hữu nguồn; không đóng `System.in` khi module khác còn sử dụng.
9. Kiểm tra `ioException()` khi cần phân biệt EOF bình thường với lỗi `IOException`.
10. Test bằng byte chứa **Unicode không phải ASCII**, locale cần thiết và input lỗi, không chỉ một chuỗi ASCII dễ qua.
11. Với yêu cầu phát hiện byte hỏng nghiêm ngặt, dùng decoder có chính sách lỗi rõ ràng.
12. Không chia sẻ Scanner cho nhiều luồng mà thiếu đồng bộ, và chú ý tác vụ đọc có thể block.

## Kết luận

`Scanner(InputStream, Charset)`, có từ **Java 10**, giúp thể hiện rõ **hợp đồng mã hóa** khi biến một luồng byte thành văn bản để quét. Sử dụng `Charset`/`StandardCharsets` giúp mã dễ đọc và tránh phụ thuộc charset mặc định khi định dạng nguồn đã xác định.

Để đọc đúng và an toàn còn cần phân biệt **charset** với **locale/delimiter**, chọn `nextLine` hay `next` phù hợp, quản lý quyền sở hữu InputStream, kiểm tra `ioException` khi cần, và kiểm thử Unicode thật bằng byte có encoding cụ thể. Đây đều là những kiến thức đang áp dụng trong Java hiện đại, không phụ thuộc tính năng cũ hoặc legacy.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `Scanner`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html): constructor `Scanner(InputStream, Charset)` được đánh dấu `Since: 10`, ngữ nghĩa token/line, locale, delimiter, đóng nguồn và `ioException`.
- [Java SE 26 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): các hằng số mã hóa chuẩn như `UTF_8` và `ISO_8859_1`.
- [Java SE 26 — `Charset`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/Charset.html): mô hình ánh xạ byte–ký tự và cách tra cứu charset.
- [Java SE 26 — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html): điều khiển chính sách xử lý byte không hợp lệ.
- [Java SE 26 — `InputStreamReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStreamReader.html): giải mã InputStream thành Reader khi cần thao tác ở tầng ký tự.
- [Java SE 26 — `Files.newInputStream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newInputStream(java.nio.file.Path,java.nio.file.OpenOption...)): mở dữ liệu byte từ Path.
- [Oracle Java SE 26 — Internationalization Guide](https://docs.oracle.com/en/java/javase/26/intl/internationalization-guide.pdf): charset mặc định và khác biệt của mã hóa stdin/stdout/stderr.
