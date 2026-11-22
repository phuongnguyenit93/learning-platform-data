# `Scanner` với `ReadableByteChannel` và `Charset` (Java 10+)

## 1. Mục tiêu và tình huống sử dụng

Khi đọc dữ liệu văn bản từ một **kênh byte** (`ReadableByteChannel`), chương trình Java cần chuyển byte thành ký tự theo một **bảng mã** (`Charset`) trước khi phân tách và diễn giải nội dung. Từ **Java 10**, `java.util.Scanner` cung cấp constructor nhận trực tiếp một `ReadableByteChannel` và **đối tượng `Charset`**:

~~~java
Scanner scanner = new Scanner(channel, StandardCharsets.UTF_8);
~~~

Trong đó:
- `channel` là một đối tượng triển khai `java.nio.channels.ReadableByteChannel`, có thể đọc byte từ tệp, luồng I/O được thích ứng thành channel hoặc một nguồn byte phù hợp khác.
- `StandardCharsets.UTF_8` là một `Charset` chuẩn, xác định **cách giải mã byte thành ký tự**.
- `Scanner` thực hiện các thao tác **tách token, đọc dòng và phân tích kiểu dữ liệu** như `next()`, `nextLine()`, `nextInt()`, `hasNextInt()`.

**Trọng tâm:** `Charset` quyết định cách hiểu **byte**; `Scanner` quyết định cách tách và phân tích **văn bản đã giải mã**. Đây là **hai tầng xử lý khác nhau**.

Bài học giúp bạn:
1. Dùng đúng constructor `Scanner(ReadableByteChannel, Charset)` và phân biệt với các overload cũ.
2. Đọc tiếng Việt có dấu bằng UTF-8 mà không phụ thuộc vào charset mặc định.
3. Hiểu `next()`, `nextLine()`, delimiter và locale hoạt động ra sao sau bước giải mã.
4. Quản lý vòng đời channel và scanner bằng `try-with-resources` đúng với quyền sở hữu tài nguyên.
5. Xử lý token sai định dạng, dữ liệu không đủ và lỗi I/O thông qua `Scanner.ioException()`.
6. Chọn `Scanner` khi cần phân tích dữ liệu văn bản, tránh nhầm nó với trình đọc dữ liệu nhị phân hoặc bộ phân tích CSV đầy đủ.

Ví dụ độc lập trong bài chạy với **JDK 17+**, không sử dụng tính năng preview. Các quy tắc `Scanner`, `Charset` và `ReadableByteChannel` nêu ở đây vẫn áp dụng trong Java hiện đại.

## 2. API và mốc phiên bản

Constructor được nhấn mạnh trong Java 10 có chữ ký:

~~~java
public Scanner(ReadableByteChannel source, Charset charset)
~~~

Đây là overload được đánh dấu **Since: 10** trong tài liệu Java API. Các overload liên quan:

| Constructor | Giải thích | Ghi chú |
| --- | --- | --- |
| `new Scanner(channel)` | Đọc byte từ channel bằng charset mặc định | Tránh phụ thuộc vào môi trường khi định dạng dữ liệu đã biết |
| `new Scanner(channel, "UTF-8")` | Đọc bằng charset chỉ định qua **tên chuỗi** | Đã có từ trước Java 10; sai tên charset có thể gây `IllegalArgumentException` |
| `new Scanner(channel, StandardCharsets.UTF_8)` | Đọc bằng **đối tượng `Charset`** | Overload được bổ sung trong **Java 10** |
| `new Scanner(inputStream, StandardCharsets.UTF_8)` | Đọc từ `InputStream` và charset cụ thể | Overload nhận `Charset` cũng có từ Java 10 |
| `new Scanner(path, StandardCharsets.UTF_8)` | Đọc tệp tại `Path` và charset cụ thể | Phù hợp khi đã có đường dẫn và không cần quản lý channel trực tiếp |
| `new Scanner(reader)` | Đọc ký tự đã được `Reader` cung cấp | Không chọn charset ở constructor này, vì nguồn đã ở tầng ký tự |
| `new Scanner(text)` | Phân tích chính **nội dung chuỗi** `text` | Không coi `text` là tên tệp |

Các loại import phổ biến:

~~~java
import java.nio.channels.ReadableByteChannel;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;
~~~

Trong code ứng dụng, `StandardCharsets.UTF_8` là cách viết rõ ràng hơn chuỗi tự gõ `"UTF-8"`, vì là hằng `Charset` được Java cung cấp. Dùng `Charset.forName(name)` khi bảng mã được cấu hình động, đồng thời xử lý cấu hình không hợp lệ theo hợp đồng ứng dụng.

**Đừng nhầm `Scanner(String)`:**

~~~java
Scanner scanner = new Scanner("data.txt");
~~~

Câu lệnh này chỉ quét **chuỗi ký tự `"data.txt"`**, không đọc nội dung tệp trên đĩa. Nếu có `Path path`, dùng constructor nhận `Path` hoặc mở channel từ `Files.newByteChannel(path)`.

## 3. Luồng xử lý: byte → ký tự → token

Hình dung pipeline:

~~~text
ReadableByteChannel
   │ đọc các byte
   ▼
Charset / bộ giải mã ký tự (ví dụ UTF-8)
   │ tạo chuỗi ký tự
   ▼
Scanner
   │ nhận diện delimiter, dòng, số, mẫu regex
   ▼
String / int / double / các giá trị ứng dụng
~~~

**`Charset`** không quyết định dấu phẩy là delimiter hay số `3,5` có nghĩa là ba phẩy năm. Bước charset chỉ giải mã byte, chẳng hạn từ tệp UTF-8 thành `"Tiếng Việt"`.

**`Scanner`** xử lý văn bản sau giải mã:
- Mặc định, token được ngăn cách bằng **whitespace** theo quy tắc Java.
- `useDelimiter(regex)` thay quy tắc tách token bằng biểu thức chính quy.
- `useLocale(locale)` ảnh hưởng cách nhận diện **số và dữ liệu được địa phương hóa**.
- `useRadix(radix)` thay cơ số mặc định của phương thức đọc số nguyên.
- `nextLine()` đọc phần còn lại của dòng và không dùng delimiter token như `next()`.

Một tập byte giống nhau nhưng giải mã bằng **charset khác** có thể tạo ra chuỗi ký tự khác nhau. Dùng charset sai có thể dẫn đến chữ tiếng Việt bị lỗi (*mojibake*), regex không khớp hoặc parse thất bại.

## 4. Tạo `ReadableByteChannel` từ dữ liệu văn bản UTF-8

Một cách dễ kiểm thử mà không cần tệp trên đĩa là bắt đầu từ một chuỗi và tạo channel từ `InputStream`:

~~~java
String content = "Hà Nội\nĐà Nẵng\n";
byte[] bytes = content.getBytes(StandardCharsets.UTF_8);

ReadableByteChannel channel = Channels.newChannel(
        new ByteArrayInputStream(bytes));

try (Scanner scanner = new Scanner(channel, StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        System.out.println(scanner.nextLine());
    }
}
~~~

Đây là đoạn minh họa đặt trong một phương thức, cần thêm import `java.io.ByteArrayInputStream`, `java.nio.channels.Channels`, `ReadableByteChannel`, `StandardCharsets` và `Scanner`.

Đầu ra:

~~~text
Hà Nội
Đà Nẵng
~~~

Giải thích:
1. `getBytes(UTF_8)` **mã hóa** các ký tự thành byte UTF-8.
2. `ByteArrayInputStream` cung cấp các byte trong bộ nhớ.
3. `Channels.newChannel(inputStream)` tạo một `ReadableByteChannel`.
4. `new Scanner(channel, UTF_8)` **giải mã đúng bằng UTF-8**.
5. `hasNextLine()` kiểm tra còn dòng; `nextLine()` trả về văn bản của dòng, không bao gồm ký tự kết thúc dòng.
6. `try-with-resources` đóng scanner; scanner đóng nguồn có thể đóng theo hợp đồng của nó (xem mục 8).

**Điểm cần phân biệt:** các byte mà chương trình tự mã hóa bằng UTF-8 **phải được giải mã bằng UTF-8** để khôi phục đúng nội dung. Truyền `StandardCharsets.ISO_8859_1` thay cho `UTF_8` không phải “chọn cách hiển thị” mà là **đọc byte thành những ký tự khác**.

## 5. Tách token và đọc số với delimiter có chủ đích

Giả sử dữ liệu đơn giản:

~~~text
name,score
An,21
Bình,35
~~~

Đây là một định dạng **tách cột bằng dấu phẩy đơn giản**, không có giá trị rỗng, dấu phẩy nằm trong dữ liệu hay cặp dấu nháy. Chúng ta có thể đọc bằng `Scanner` với delimiter:

~~~java
scanner.useDelimiter("[,\\r\\n]+");
scanner.useLocale(Locale.ROOT);

String column1 = scanner.next(); // name
String column2 = scanner.next(); // score

while (scanner.hasNext()) {
    String name = scanner.next();
    int score = scanner.nextInt();

    System.out.println(name + ":" + score);
}
~~~

Đây là đoạn minh họa trong một phương thức đang có `Scanner scanner`, cần import `java.util.Locale`.

**Giải thích regex:** `"[,\\r\\n]+"` trong Java là biểu thức chính quy nhận một hoặc nhiều dấu phẩy hoặc ký tự xuống dòng `CR`/`LF` liên tiếp làm dấu phân tách.

**Tại sao gọi `useLocale(Locale.ROOT)`?** Để thiết lập môi trường phân tích số nhất quán cho ví dụ, thay vì dựa vào locale mặc định của máy. `Charset` không thay thế `Locale`; hai khái niệm độc lập.

**Không coi regex này là CSV parser đầy đủ.** Nó không xử lý:
- Trường có dấu phẩy trong cặp dấu nháy, như `"Nguyễn, An"`.
- Trường rỗng giữa hai dấu phẩy; dấu `+` có thể gộp nhiều delimiter và làm mất cột rỗng.
- Escape, xuống dòng bên trong quoted field hoặc cấu trúc CSV theo RFC 4180.

Với CSV thực tế, hãy dùng một CSV parser chuyên dụng hoặc parser được thiết kế đúng đặc tả. `Scanner` thuận tiện khi dữ liệu token đơn giản và định dạng đã được kiểm soát.

## 6. `next()`, `nextLine()` và lỗi “bị bỏ qua dòng”

Hai nhóm thao tác được dùng nhiều:

| Thao tác | Dựa trên | Kết quả |
| --- | --- | --- |
| `hasNext()` | Delimiter token hiện tại | Có token kế tiếp hay không |
| `next()` | Delimiter token hiện tại | Token tiếp theo dưới dạng `String` |
| `hasNextInt()` | Delimiter + locale + radix | Token kế tiếp có phân tích thành `int` được không |
| `nextInt()` | Delimiter + locale + radix | Đọc token thành `int`, có thể ném `InputMismatchException` |
| `hasNextLine()` | Ranh giới dòng | Có dòng kế tiếp hay không |
| `nextLine()` | Ranh giới dòng | Đọc phần còn lại của dòng hiện tại, bỏ ký tự kết thúc dòng |

Mã dễ gây bất ngờ:

~~~java
try (Scanner scanner = new Scanner("42\nHello")) {
    int number = scanner.nextInt();
    String restOfLine = scanner.nextLine();

    System.out.println(number);            // 42
    System.out.println(restOfLine.isEmpty()); // true
    System.out.println(scanner.nextLine()); // Hello
}
~~~

`nextInt()` đọc số nhưng **không tiêu thụ ký tự kết thúc dòng** theo cách mà `nextLine()` sẽ làm, nên `nextLine()` ngay sau đó đọc phần còn lại của dòng số (rỗng trong ví dụ).

**Cách viết an toàn khi dữ liệu theo từng dòng:**

~~~java
try (Scanner scanner = new Scanner("42\nHello")) {
    int number = Integer.parseInt(scanner.nextLine());
    String text = scanner.nextLine();
    System.out.println(number + ":" + text); // 42:Hello
}
~~~

Đây là ví dụ dùng `Scanner(String)` với văn bản đã là `String`, không cần `Charset`. Khi đọc từ channel, cùng quy tắc `nextInt`/`nextLine` vẫn áp dụng **sau khi byte đã được giải mã**.

**Lời khuyên:** Nếu yêu cầu xử lý từng dòng, thường dùng `hasNextLine()`/`nextLine()` rồi parse từng dòng một; tránh trộn token và line mà không chủ động quản lý ranh giới.

## 7. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **ScannerChannelCharsetDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.nio.channels.Channels;
import java.nio.channels.ReadableByteChannel;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Scanner;

public class ScannerChannelCharsetDemo {

    static ReadableByteChannel fromUtf8(String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        return Channels.newChannel(new ByteArrayInputStream(bytes));
    }

    static void readRows() {
        ReadableByteChannel channel = fromUtf8(
                "name,score\nAn,21\nBình,35\n");

        try (Scanner scanner = new Scanner(channel, StandardCharsets.UTF_8)) {
            scanner.useDelimiter("[,\\r\\n]+");
            scanner.useLocale(Locale.ROOT);

            String firstHeader = scanner.next();
            String secondHeader = scanner.next();
            System.out.println("header = "
                    + firstHeader + ":" + secondHeader);

            int sum = 0;
            while (scanner.hasNext()) {
                String name = scanner.next();

                if (!scanner.hasNextInt()) {
                    throw new IllegalArgumentException(
                            "Invalid score for " + name);
                }

                int score = scanner.nextInt();
                sum += score;
                System.out.println("row = " + name + ":" + score);
            }
            System.out.println("sum = " + sum);
            System.out.println("io error = "
                    + (scanner.ioException() != null));
        }

        // Scanner.close() đóng kênh đầu vào được thích ứng bên trong.
        System.out.println("channel open after close = " + channel.isOpen());
    }

    static void readLines() {
        try (Scanner scanner = new Scanner(
                fromUtf8("Hà Nội\nĐà Nẵng\n"),
                StandardCharsets.UTF_8)) {

            System.out.println("line 1 = " + scanner.nextLine());
            System.out.println("line 2 = " + scanner.nextLine());
            System.out.println("has another line = "
                    + scanner.hasNextLine());
        }
    }

    static void compareCharset() {
        // Byte gốc là UTF-8, nhưng đọc nhầm bằng ISO-8859-1.
        try (Scanner scanner = new Scanner(
                fromUtf8("Cà phê"),
                StandardCharsets.ISO_8859_1)) {

            String decoded = scanner.nextLine();
            System.out.println("wrong charset matches = "
                    + decoded.equals("Cà phê"));
        }
    }

    static void parseLocalizedNumber() {
        try (Scanner scanner = new Scanner(
                fromUtf8("3,5;7,25"),
                StandardCharsets.UTF_8)) {

            scanner.useDelimiter(";");
            scanner.useLocale(Locale.GERMANY);

            double first = scanner.nextDouble();
            double second = scanner.nextDouble();
            System.out.println("localized numbers = "
                    + first + ":" + second);
        }
    }

    static void invalidNumber() {
        try (Scanner scanner = new Scanner(
                fromUtf8("12 abc"),
                StandardCharsets.UTF_8)) {

            scanner.useLocale(Locale.ROOT);
            System.out.println("first int = " + scanner.nextInt());
            System.out.println("has next int = " + scanner.hasNextInt());
            System.out.println("remaining token = " + scanner.next());
        }
    }

    public static void main(String[] args) {
        readRows();
        readLines();
        compareCharset();
        parseLocalizedNumber();
        invalidNumber();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

~~~bash
javac ScannerChannelCharsetDemo.java
java ScannerChannelCharsetDemo
~~~

**Đầu ra chuẩn:**

~~~text
header = name:score
row = An:21
row = Bình:35
sum = 56
io error = false
channel open after close = false
line 1 = Hà Nội
line 2 = Đà Nẵng
has another line = false
wrong charset matches = false
localized numbers = 3.5:7.25
first int = 12
has next int = false
remaining token = abc
~~~

### Vì sao chương trình cho ra các kết quả trên?

1. **`fromUtf8`:** mã hóa chuỗi bằng `StandardCharsets.UTF_8`, tạo `ByteArrayInputStream` rồi bọc thành `ReadableByteChannel`. Từ đây Scanner thật sự đọc **byte**, không phải trực tiếp quét một `String`.
2. **`readRows`:** scanner giải mã byte UTF-8, tách token bởi dấu phẩy và xuống dòng. Header là `name`, `score`; hai bản ghi cho số điểm `21` và `35`, tổng `56`.
3. **`ioException()`:** không có lỗi I/O trong ví dụ trong bộ nhớ, nên trả `null` và dòng `io error = false`.
4. **`channel.isOpen()`:** khi `Scanner` được đóng bởi `try-with-resources`, nguồn channel được đóng thông qua readable do Scanner tạo để giải mã byte; kết quả là `false`.
5. **`readLines`:** `nextLine()` trả hai dòng tiếng Việt đầy đủ; sau dòng cuối, `hasNextLine()` trả `false`.
6. **`compareCharset`:** byte được mã hóa bằng UTF-8 nhưng giải mã theo ISO-8859-1, nên văn bản không còn bằng chuỗi gốc; chương trình in `false` thay vì phụ thuộc vào các ký tự lỗi hiển thị trên console.
7. **`parseLocalizedNumber`:** charset vẫn là UTF-8; **locale `Locale.GERMANY`** mới quyết định dấu phẩy trong `3,5` và `7,25` là dấu thập phân. Các `double` được nối chuỗi qua Java `Double.toString`, nên hiển thị `3.5:7.25`.
8. **`invalidNumber`:** sau `12`, token `abc` không phải số nguyên; `hasNextInt()` trả `false` mà **không tiêu thụ token**, nên `next()` vẫn đọc được `abc`.

**Không dùng thứ tự ngẫu nhiên, ngày giờ hay cấu hình locale mặc định** trong các kiểm tra quan trọng; stdout được xây từ nguồn byte và locale cụ thể nên có thể kiểm chứng.

## 8. Quyền sở hữu channel và việc đóng Scanner

`Scanner` triển khai `Closeable`. Theo hợp đồng Java API, khi `Scanner.close()` được gọi, Scanner sẽ đóng nguồn đọc bên dưới **nếu nguồn readable ấy triển khai `Closeable`**.

Với constructor nhận `ReadableByteChannel` và `Charset`, Scanner tạo một tầng đọc/giải mã byte từ channel. Khi scanner quản lý nguồn đó được đóng, channel nền cũng sẽ được đóng.

Vì vậy, trường hợp phổ biến:

~~~java
ReadableByteChannel channel = Channels.newChannel(inputStream);

try (Scanner scanner = new Scanner(channel, StandardCharsets.UTF_8)) {
    while (scanner.hasNext()) {
        System.out.println(scanner.next());
    }
}
// Scanner đã đóng channel được nó quản lý.
~~~

Đây là đoạn minh họa cần có `inputStream` kiểu `InputStream` và các import thích hợp. Cần xác định **ai sở hữu inputStream**: `Channels.newChannel(inputStream)` là wrapper có thể truyền việc `close` xuống luồng nền. Nếu `inputStream` là tài nguyên mà caller cần giữ lại, đừng vô tình đóng nó bằng cách đóng scanner.

### Mẫu khi hàm tự mở channel: scanner là resource owner

~~~java
static void readFile(Path path) throws IOException {
    try (Scanner scanner = new Scanner(
            Files.newByteChannel(path),
            StandardCharsets.UTF_8)) {

        while (scanner.hasNextLine()) {
            System.out.println(scanner.nextLine());
        }

        IOException scanError = scanner.ioException();
        if (scanError != null) {
            throw scanError;
        }
    }
}
~~~

Đây là đoạn **minh họa cần nằm trong lớp**; import `java.nio.file.Path`, `Files`, `java.io.IOException`, `Scanner`, `StandardCharsets`. `Files.newByteChannel(path)` mặc định mở để đọc; hàm tự mở nguồn, nên `try-with-resources` làm quyền sở hữu rõ ràng.

**Tại sao không cần đưa channel vào `try` riêng ở ví dụ trên?** Channel được tạo rồi truyền ngay vào scanner, và scanner quản lý việc đóng nguồn đọc. Cách này tránh hai owner cùng cố đóng một channel. Nếu quá trình **xây dựng Scanner thất bại** sau khi channel đã mở, bạn phải cân nhắc cleanup theo thiết kế, nhưng với code thông thường và đối số cố định khác `null`, đây là pattern đơn giản.

### Nếu caller truyền channel vào helper

Ví dụ API:

~~~java
static void parseBorrowedChannel(ReadableByteChannel channel) {
    try (Scanner scanner = new Scanner(
            channel, StandardCharsets.UTF_8)) {

        // parse dữ liệu
    }
}
~~~

Đoạn này **không phù hợp nếu helper chỉ mượn channel và caller muốn tiếp tục sử dụng channel**, vì `scanner.close()` sẽ đóng nguồn bên dưới. Điều này khác với nhiều helper xử lý ký tự mượn `Reader` mà không đóng.

Khi cần chia sẻ channel:
- Tốt nhất chọn **một owner rõ ràng** và tài liệu API giải thích hàm nào sẽ đóng channel.
- Nếu helper phải giữ channel của caller còn mở, tránh tự ý tạo và đóng Scanner bao bọc trực tiếp channel đó. Hãy chọn cách thiết kế không đóng nguồn được mượn, ví dụ một wrapper được xác định rõ hợp đồng *non-closing*, hoặc để caller sở hữu vòng đời scanner sau khi xử lý.
- Không xem việc “bỏ qua `scanner.close()` để khỏi đóng channel” là giải pháp mặc định, vì có thể làm vòng đời tài nguyên thiếu rõ ràng.

### Tránh đóng các stream chuẩn của ứng dụng

Đặc biệt cẩn thận khi bọc `System.in` thành channel:

~~~java
var channel = Channels.newChannel(System.in);
// try (Scanner scanner = new Scanner(channel, StandardCharsets.UTF_8)) {
//     ...
// }
// Khi scanner đóng, System.in có thể bị đóng theo channel wrapper.
~~~

Việc đóng `System.in` có thể khiến phần khác của ứng dụng không đọc tiếp được. Đối với standard streams hoặc nguồn được quản lý bởi framework, **hợp đồng ownership quan trọng hơn sự tiện lợi của `try-with-resources`**.

## 9. Lỗi I/O và `Scanner.ioException()`

`ReadableByteChannel.read(ByteBuffer)` có thể ném `IOException` khi I/O thất bại. Tuy nhiên, `Scanner` **không nhất thiết ném trực tiếp IOException cho caller ở các thao tác quét**.

Theo tài liệu `Scanner`, nếu nguồn `Readable` bên dưới ném `IOException`, Scanner **xem như đã tới cuối đầu vào**, và giữ ngoại lệ đọc gần nhất để caller truy vấn bằng:

~~~java
IOException error = scanner.ioException();
~~~

Nếu không có IOException được ghi nhận, `ioException()` trả `null`.

Điều này quan trọng vì một vòng lặp có thể kết thúc như thể đã đọc hết dữ liệu:

~~~java
try (Scanner scanner = new Scanner(
        Files.newByteChannel(path), StandardCharsets.UTF_8)) {

    while (scanner.hasNextLine()) {
        process(scanner.nextLine());
    }

    IOException error = scanner.ioException();
    if (error != null) {
        throw error; // Không coi kết quả dở dang là thành công.
    }
}
~~~

Đây là đoạn minh họa: `path` là `Path`, `process(String)` là hàm xử lý của ứng dụng; phương thức chứa đoạn code cần khai báo `throws IOException` hoặc bắt ngoại lệ.

**Lưu ý về báo lỗi khi đóng:** `try-with-resources` cũng có thể ném ngoại lệ trong giai đoạn đóng tài nguyên nếu resource tương ứng có lỗi. Đừng giả định một lần `hasNextLine() == false` tự chứng minh đã đọc thành công toàn bộ tệp.

### Lỗi parse không phải lỗi I/O

Các ngoại lệ khác nhau và cần xử lý khác nhau:

| Tình huống | Hành vi thường gặp | Cách xử lý |
| --- | --- | --- |
| Token `"abc"` nhưng gọi `nextInt()` | `InputMismatchException` | Kiểm tra bằng `hasNextInt()`, báo lỗi dữ liệu, hoặc chuyển sang parse từng dòng |
| Gọi `next()` khi không còn token | `NoSuchElementException` | Dùng `hasNext()` hoặc xác thực số lượng token |
| Gọi phương thức quét sau `scanner.close()` | `IllegalStateException` | Quản lý vòng đời rõ, không tái dùng scanner đã đóng |
| Channel đọc bị lỗi I/O | Scanner có thể coi như EOF, lưu lỗi cho `ioException()` | Kiểm tra `ioException()` sau khi quét |
| Truyền `null` cho nguồn hoặc charset | `NullPointerException` | Bảo đảm đối số khác `null` |
| Dùng charset sai nhưng vẫn giải mã được | Có thể nhận chuỗi ký tự sai mà không có ngoại lệ | Gắn charset với hợp đồng dữ liệu; kiểm tra dữ liệu hợp lệ |

**Phân biệt:** `InputMismatchException` nói rằng token không phù hợp kiểu được yêu cầu; `IOException` nói rằng thao tác I/O nguồn/đích gặp lỗi. Hai lỗi này cần được giải quyết ở những tầng khác nhau.

## 10. Charset và locale là hai quyết định độc lập

**Charset:** biến byte thành ký tự.

~~~java
new Scanner(channel, StandardCharsets.UTF_8);
~~~

**Locale:** ảnh hưởng cách Scanner diễn giải các giá trị như số.

~~~java
scanner.useLocale(Locale.GERMANY);
double price = scanner.nextDouble();
~~~

Ví dụ chuỗi `"3,5"` với `Locale.GERMANY` có thể được đọc thành `3.5` kiểu `double`, ngay cả khi byte của chuỗi đó được giải mã bằng UTF-8. Nếu dùng locale khác, cách parse token có thể khác.

Vì vậy:
- **Dữ liệu tệp dùng UTF-8** không có nghĩa số thập phân luôn dùng dấu chấm.
- **Locale `Locale.GERMANY`** không có nghĩa tệp phải được mã hóa theo một charset riêng của Đức.
- Để chương trình tái lập giữa các máy, nêu rõ **cả charset và locale** khi định dạng dữ liệu yêu cầu.

Với số tiền hoặc dữ liệu cần độ chính xác thập phân, cân nhắc `BigDecimal` và quy tắc định dạng đã xác định thay vì dùng `double` để lưu các phép tính tài chính. Đây là lựa chọn mô hình dữ liệu, độc lập với constructor `Scanner`.

## 11. Khi đọc tệp thật: `Files.newByteChannel` hay constructor `Scanner(Path, Charset)`?

### Khi cần kênh byte

~~~java
Path path = Path.of("data.txt");

try (Scanner scanner = new Scanner(
        Files.newByteChannel(path),
        StandardCharsets.UTF_8)) {

    while (scanner.hasNextLine()) {
        System.out.println(scanner.nextLine());
    }
}
~~~

Đây là đoạn minh họa cần import `Path`, `Files`, `Scanner`, `StandardCharsets`, và xử lý `IOException` khi mở tệp.

**Ưu điểm:** đầu vào là `ReadableByteChannel`; code có thể tích hợp với lớp I/O đang cung cấp channel và dùng constructor `Charset` rõ ràng.

### Khi chỉ có đường dẫn tệp và cần scan text

~~~java
Path path = Path.of("data.txt");

try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        System.out.println(scanner.nextLine());
    }
}
~~~

Cũng là đoạn minh họa với JDK 17+. Nếu ứng dụng chỉ cần đọc một tệp text từ `Path`, constructor **`Scanner(Path, Charset)`** có thể đơn giản hơn, không cần mở channel thủ công.

### Khi chỉ cần đọc dòng, không cần tách token hoặc parse số

~~~java
try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

Nếu chỉ cần xử lý tuần tự từng dòng, `BufferedReader` thường là một lựa chọn đơn giản. Không nhất thiết dùng `Scanner` cho mọi bài toán đọc text; Scanner hữu ích khi cần **tokenization và chuyển token thành kiểu dữ liệu** theo locale/pattern.

### Khi dữ liệu là nhị phân

`Scanner` không phù hợp để đọc trực tiếp những byte không phải text (ảnh, tệp nén, giao thức nhị phân). Dùng `ByteBuffer`, `ReadableByteChannel.read()`, `DataInputStream` hoặc thư viện parser đúng định dạng. Charset chỉ có ý nghĩa khi byte thực sự biểu diễn **văn bản đã mã hóa**.

## 12. Lưu ý về charset mặc định và dữ liệu sai mã hóa

### 12.1. Tránh phụ thuộc vào mặc định khi định dạng đã biết

~~~java
new Scanner(channel); // Charset mặc định của môi trường JDK/runtime
~~~

Dù các JDK mới chuẩn hóa nhiều trường hợp mặc định theo UTF-8, **hợp đồng dữ liệu có charset cụ thể vẫn nên ghi rõ charset**. Điều này quan trọng khi:
- Hệ thống đọc dữ liệu qua nhiều môi trường.
- Đầu vào xuất phát từ nhà cung cấp có quy định charset.
- Dữ liệu chứa tiếng Việt hoặc ký tự ngoài ASCII.
- Cần kiểm thử kết quả không phụ thuộc cấu hình hệ thống.

Cách khuyến nghị:

~~~java
new Scanner(channel, StandardCharsets.UTF_8);
~~~

### 12.2. Chọn charset sai là lỗi logic, không chỉ lỗi hiển thị

Giả sử byte nguồn được mã hóa UTF-8 nhưng Scanner được tạo với `ISO_8859_1`. Các byte vẫn có thể được giải mã theo charset đó, nhưng kết quả ký tự không còn đúng. Tokenization hoặc matching có thể hành xử sai mà không ném ngoại lệ.

Không nên kỳ vọng `Scanner.ioException()` sẽ phát hiện **mọi trường hợp chọn charset sai**. Nó lưu lỗi I/O từ nguồn đọc, không phải bộ kiểm chứng độc lập rằng nội dung đã giải mã đúng ý nghĩa nghiệp vụ.

Nếu ứng dụng yêu cầu phát hiện byte sai mã hóa một cách nghiêm ngặt, hãy thiết kế một bước decode/validation rõ ràng bằng `CharsetDecoder` và `CodingErrorAction.REPORT` hoặc pipeline phù hợp với định dạng thực tế, sau đó mới parse text. Hành vi mặc định của `Scanner` không thay thế một chính sách kiểm định encoding.

### 12.3. Dữ liệu có BOM và định dạng đặc thù

Một số tệp UTF-8 có dấu BOM ở đầu. Nếu chương trình cần hỗ trợ cả tệp có và không có BOM, hãy xác định quy tắc xử lý BOM tại ranh giới nhập dữ liệu, thay vì giả định mọi token đầu tiên đều hoàn toàn giống nhau trên mọi biến thể đầu vào.

Tương tự, `Scanner` không tự hiểu cấu trúc JSON, XML hoặc CSV có quoted fields. Charset giúp giải mã ký tự; **parser định dạng** mới chịu trách nhiệm cú pháp nghiệp vụ.

## 13. Hiệu năng, đồng thời và môi trường thực tế

- **Scanner dùng regex và parse kiểu dữ liệu:** tiện cho lượng dữ liệu vừa phải hoặc input tương tác, nhưng không phải luôn là lựa chọn nhanh nhất cho file rất lớn. Khi throughput quan trọng, benchmark trên dữ liệu thực và cân nhắc `BufferedReader` hoặc parser chuyên biệt.
- **`ReadableByteChannel` có thể block:** thao tác `hasNext()`, `next()`, `hasNextLine()` có thể chờ thêm byte. Không đặt giả định rằng kiểm tra `hasNext` luôn là thao tác tức thì.
- **Scanner không an toàn khi truy cập đồng thời từ nhiều thread** nếu không có cơ chế đồng bộ bên ngoài. Một scanner gắn với một channel thường nên có một owner và một luồng xử lý rõ ràng.
- **Channel có thể bị đóng từ nơi khác:** nếu nhiều thành phần giữ tham chiếu channel, việc một thành phần đóng scanner có thể làm thành phần kia gặp lỗi. Tránh dùng chung channel mà không có hợp đồng vòng đời.
- **Dữ liệu thiếu hoặc hỏng:** xác thực từng token theo schema; không coi kết quả parse thành công vài dòng là bằng chứng toàn bộ input hợp lệ.
- **Kích thước token không giới hạn hợp lý:** đầu vào không tin cậy có thể chứa token/dòng rất dài, khiến quét và xử lý tiêu tốn bộ nhớ hoặc CPU. Cân nhắc giới hạn kích thước input và phương án streaming parser phù hợp.
- **Không tự động chuyển mọi thứ về String:** nếu dữ liệu là nhị phân hoặc đã được giải mã theo hợp đồng khác, dùng API đúng tầng để tránh lỗi.

## 14. Những sai lầm và cách sửa

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| `new Scanner(channel)` khi tệp quy định UTF-8 | Phụ thuộc charset mặc định | `new Scanner(channel, StandardCharsets.UTF_8)` |
| `new Scanner("file.txt")` để đọc tệp | Chuỗi bị coi là **nội dung text**, không phải path | `new Scanner(path, UTF_8)` hoặc `new Scanner(Files.newByteChannel(path), UTF_8)` |
| Dùng `Charset` để giải quyết dấu phẩy thập phân | Charset chỉ giải mã ký tự | `scanner.useLocale(...)` cho cách parse số |
| Dùng `next()` để giữ cả dòng có dấu cách | `next()` chỉ trả token | Dùng `nextLine()` khi muốn cả dòng |
| Gọi `nextLine()` ngay sau `nextInt()` mà không xét phần còn lại | Có thể nhận chuỗi rỗng | Quản lý ranh giới dòng hoặc parse từng dòng |
| Dùng delimiter `[,\\r\\n]+` như CSV parser hoàn chỉnh | Mất cột rỗng, không hiểu quoted fields | Dùng CSV parser đúng chuẩn |
| Dùng `nextInt()` mà không xác thực input | Có thể ném `InputMismatchException` | `hasNextInt()`, parse từng dòng hoặc xử lý ngoại lệ |
| Coi `hasNextLine()==false` luôn là EOF sạch | Scanner có thể lưu lỗi đọc rồi coi như hết input | Kiểm tra `scanner.ioException()` |
| Đóng Scanner trên channel do caller cần giữ mở | Scanner đóng nguồn đọc mà nó sở hữu | Quy định ownership; tránh đóng nguồn mượn |
| Đóng cả scanner và channel riêng rẽ mà không có lý do | Dễ gây hiểu nhầm owner, đóng lặp | Chọn một owner rõ ràng, thường là scanner trong `try-with-resources` |
| Đọc UTF-8 bằng ISO-8859-1 rồi nghĩ dữ liệu chỉ “hiển thị khác” | Byte được giải mã thành nội dung khác | Chọn charset đúng hợp đồng nguồn |
| Dùng Scanner cho binary file | Token parser không phù hợp dữ liệu byte tùy ý | Dùng ByteBuffer/channel hoặc parser nhị phân |

## 15. Tự kiểm tra kiến thức

**Câu 1.** Constructor nào kết hợp trực tiếp `ReadableByteChannel` và **đối tượng `Charset`** từ Java 10?

**Đáp án:** `new Scanner(channel, StandardCharsets.UTF_8)`, với `channel` kiểu `ReadableByteChannel`.

**Câu 2.** `new Scanner(channel, "UTF-8")` và `new Scanner(channel, StandardCharsets.UTF_8)` khác nhau ở đâu?

**Đáp án:** Cách đầu truyền **tên charset** dưới dạng `String`, đã có trước Java 10. Cách sau truyền trực tiếp **`Charset` object**, overload được bổ sung từ Java 10. Cả hai có thể dùng UTF-8 khi được cấu hình hợp lệ.

**Câu 3.** Nếu các byte đầu vào được mã hóa bằng UTF-8, vì sao Scanner cũng phải giải mã bằng UTF-8?

**Đáp án:** Charset xác định ánh xạ byte → ký tự. Dùng charset khác có thể tạo text sai, đặc biệt với chữ có dấu và ký tự ngoài ASCII.

**Câu 4.** Charset có quyết định `"3,5"` được parse thành `double` không?

**Đáp án:** Không trực tiếp. Charset tạo ra chuỗi ký tự `3,5`; **`Locale`** và quy tắc parse số của Scanner mới quyết định token có được diễn giải thành số thực hay không.

**Câu 5.** Vì sao `scanner.nextInt(); scanner.nextLine();` đôi khi trả về dòng rỗng?

**Đáp án:** `nextInt` tiêu thụ token số, nhưng có thể để lại dấu xuống dòng của dòng hiện tại; `nextLine` đọc phần còn lại trước dấu xuống dòng ấy.

**Câu 6.** Khi Scanner được tạo từ một channel rồi đưa vào `try-with-resources`, ai đóng channel?

**Đáp án:** `Scanner.close()` đóng nguồn đọc `Closeable` của nó; với constructor nhận channel/charset, việc đóng được truyền tới channel nền. Vì vậy cần bảo đảm Scanner được phép sở hữu channel theo hợp đồng.

**Câu 7.** Nếu `hasNextLine()` trả `false`, làm sao kiểm tra xem có lỗi I/O trong quá trình đọc?

**Đáp án:** Gọi `scanner.ioException()`. Nếu khác `null`, đó là `IOException` gần nhất được Scanner lưu từ nguồn đọc.

**Câu 8.** Có nên dùng regex `[,\\r\\n]+` để parse một CSV chứa `"Nguyễn, An"` trong dấu nháy không?

**Đáp án:** Không. Regex đơn giản không hiểu dấu nháy và quy tắc escape của CSV. Dùng parser CSV phù hợp.

**Câu 9.** `Scanner(String)` có tự mở file theo tên đường dẫn trong chuỗi không?

**Đáp án:** Không. Nó quét **nội dung chuỗi**. Muốn đọc file, dùng `Path` hoặc channel mở từ file.

**Câu 10.** Khi nào nên dùng `BufferedReader` thay cho `Scanner`?

**Đáp án:** Khi chủ yếu cần đọc từng dòng hoặc yêu cầu hiệu năng/kiểm soát I/O khác, không cần chức năng tách token và parse số theo locale của Scanner.

**Câu 11.** `Scanner.ioException()==null` có chứng minh dữ liệu được giải mã đúng charset hoặc đúng định dạng nghiệp vụ không?

**Đáp án:** Không. Nó chỉ cho biết Scanner không lưu IOException từ nguồn readable; việc giải mã sai charset vẫn có thể tạo text khác mà không có lỗi I/O.

**Câu 12.** Vì sao không nên tự động đóng một Scanner tạo từ channel đang dùng chung?

**Đáp án:** Việc đóng Scanner có thể đóng luôn channel nền, ảnh hưởng code khác. Tài nguyên phải có ownership rõ ràng; helper chỉ mượn không nên tự ý chấm dứt vòng đời channel của caller.

## 16. Ghi nhớ cuối bài

1. **`Scanner(ReadableByteChannel, Charset)` có từ Java 10**, giúp chỉ định charset khi quét văn bản từ channel byte.
2. **Charset giải mã byte; Scanner tách token, đọc dòng và phân tích giá trị.** `Locale` dùng cho cách hiểu dữ liệu địa phương hóa như số, không thay vai trò Charset.
3. **Chỉ định `StandardCharsets.UTF_8` rõ ràng** khi nguồn có hợp đồng UTF-8, nhất là với tiếng Việt.
4. **`Scanner.close()` đóng nguồn Closeable bên dưới**; với channel được Scanner quản lý, việc đóng lan xuống channel. Xác định ownership trước khi dùng `try-with-resources`.
5. **Đọc hết token không luôn đồng nghĩa đã xử lý I/O thành công.** Sau khi quét, kiểm tra `scanner.ioException()` nếu cần phân biệt EOF với lỗi đọc.
6. **`nextLine()` khác `next()`**, và `nextInt()` có thể để lại ký tự kết thúc dòng; thiết kế vòng lặp theo cấu trúc dữ liệu thật.
7. **Delimiter regex không phải full parser**, đặc biệt với CSV/JSON và dữ liệu không tin cậy.
8. Scanner phù hợp khi cần **tokenization và parse text**; dùng `BufferedReader` hoặc kênh byte trực tiếp khi yêu cầu khác.

**Tài liệu tham khảo chính thức còn áp dụng:**
- [Java SE 17 — `Scanner`, constructors và `ioException()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html).
- [Java SE 10 — `Scanner(ReadableByteChannel, Charset)`](https://docs.oracle.com/javase/10/docs/api/java/util/Scanner.html).
- [Java SE 17 — `ReadableByteChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html).
- [Java SE 17 — `Channels.newChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Channels.html).
- [Java SE 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
