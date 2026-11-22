# Chọn Charset rõ ràng cho dữ liệu trao đổi trong Java 17

## 1. Vì sao phải chỉ định Charset?

Khi chương trình ghi chuỗi ra tệp, gửi qua mạng hoặc đọc dữ liệu từ một hệ thống khác, dữ liệu đi qua ranh giới giữa **ký tự** và **byte**. Java biểu diễn nội dung văn bản trong `String` theo mô hình UTF-16, nhưng tệp và giao thức thường truyền một dãy byte. Một **charset** quy định cách ánh xạ giữa các ký tự và byte khi mã hóa (encode) hoặc giải mã (decode).

Nếu hai phía dùng charset khác nhau, cùng một dãy byte có thể được hiểu thành những ký tự khác nhau. Kết quả thường thấy là tiếng Việt bị lỗi dấu, ký tự thay bằng `�`, nội dung không thể parse hoặc dữ liệu bị thay đổi khi lưu rồi đọc lại.

Ví dụ, chuỗi `"Xin chào"` có thể được mã hóa thành UTF-8:

~~~java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text); // Xin chào
~~~

Điều quan trọng là cả hai phía của phép chuyển đổi dùng cùng charset đã được thỏa thuận. Với dữ liệu trao đổi, hãy chọn charset theo đặc tả giao thức hoặc định dạng tệp, rồi truyền rõ charset vào API Java. Không dựa vào cấu hình máy đang chạy để đoán cách đối tác sẽ đọc dữ liệu.

Sau bài học, người học cần:

1. Phân biệt ký tự, code point, `String`, byte và charset.
2. Giải thích vì sao phải thống nhất charset giữa bên ghi và bên đọc.
3. Dùng `StandardCharsets.UTF_8` và overload nhận `Charset` của các API tệp, reader/writer.
4. Nhận diện các API dùng charset mặc định của nền tảng và tránh chúng ở ranh giới dữ liệu trao đổi.
5. Chọn chính sách phù hợp khi byte đầu vào không hợp lệ hoặc không thể biểu diễn bằng charset đích.
6. Kiểm tra round-trip, BOM, newline và các trường hợp dữ liệu Unicode thực tế.

## 2. Ký tự, byte và Charset là ba khái niệm khác nhau

### 2.1. Java String không phải byte array

`String` là chuỗi ký tự theo mô hình UTF-16 của Java. Một `String` không đồng nghĩa với một tệp UTF-8 hoặc một mảng byte đã có encoding cố định.

~~~java
String message = "Việt Nam";
int length = message.length();
byte[] utf8 = message.getBytes(StandardCharsets.UTF_8);
~~~

- `message` là dữ liệu văn bản trong Java.
- `message.length()` đếm UTF-16 code units, không nhất thiết bằng số ký tự người dùng nhìn thấy.
- `utf8` là các byte được tạo bằng charset UTF-8.
- Một `String` có thể được mã hóa thành các byte khác nhau nếu chọn charset khác nhau.

Không nên gọi `String.length()` rồi suy ra số byte sẽ được ghi. Số byte phụ thuộc charset và nội dung.

### 2.2. Encoding và decoding

Hai chiều chuyển đổi:

~~~text
String (Java) --encode bằng Charset--> byte[]
byte[]         --decode bằng Charset--> String (Java)
~~~

Ví dụ:

~~~java
String original = "Tiếng Việt: ă, â, ê, ô, ơ, ư";

byte[] data = original.getBytes(StandardCharsets.UTF_8);
String restored = new String(data, StandardCharsets.UTF_8);

System.out.println(original.equals(restored)); // true
~~~

Nếu byte được mã hóa bằng UTF-8 thì phải giải mã bằng UTF-8. Việc dùng một charset khác có thể tạo ra chuỗi sai dù byte gốc không bị thay đổi.

### 2.3. Charset là một hợp đồng trao đổi

Một giao thức hoặc định dạng tệp cần xác định:

- Charset nào được dùng (ví dụ UTF-8).
- Có cho phép BOM hay không và xử lý BOM như thế nào.
- Cách xử lý byte sequence không hợp lệ.
- Quy ước newline, dấu phân cách và các ký tự đặc biệt.
- Có yêu cầu chuẩn hóa Unicode hay không.

Không phải mọi dữ liệu đều phải dùng UTF-8, nhưng UTF-8 là lựa chọn phổ biến và phù hợp cho phần lớn dữ liệu văn bản trao đổi mới. Nếu một giao thức quy định charset khác, hãy tuân theo giao thức thay vì tự ý đổi.

## 3. UTF-8 và các Charset có sẵn trong Java

### 3.1. Dùng StandardCharsets

Java cung cấp các hằng charset chuẩn trong `java.nio.charset.StandardCharsets`:

| Hằng | Charset | Đặc điểm khái quát |
|---|---|---|
| `StandardCharsets.UTF_8` | UTF-8 | Mã hóa Unicode độ dài biến đổi từ 1 đến 4 byte cho một code point; lựa chọn phổ biến cho dữ liệu trao đổi |
| `StandardCharsets.UTF_16` | UTF-16 | Mã hóa Unicode bằng một hoặc hai UTF-16 code units; quy ước byte order có thể liên quan BOM |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian | UTF-16 với thứ tự byte big-endian |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian | UTF-16 với thứ tự byte little-endian |
| `StandardCharsets.ISO_8859_1` | ISO-8859-1 | Bộ ký tự một byte, không thể biểu diễn mọi ký tự Unicode |
| `StandardCharsets.US_ASCII` | US-ASCII | Bộ ký tự ASCII 7 bit; không biểu diễn được tiếng Việt |

Với ứng dụng Java 17, thường nên viết:

~~~java
import java.nio.charset.StandardCharsets;

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Hằng trong `StandardCharsets` giúp tránh lỗi gõ sai tên charset và làm rõ lựa chọn trong mã. Nếu cần charset khác theo tên, dùng `Charset.forName("...")` sau khi đã xác nhận charset đó được runtime hỗ trợ.

### 3.2. UTF-8 không đồng nghĩa với một ký tự bằng một byte

UTF-8 mã hóa code point theo số byte thay đổi:

| Ví dụ | Code point | Số byte UTF-8 |
|---|---|---:|
| `A` | U+0041 | 1 |
| `é` | U+00E9 | 2 |
| `ệ` | U+1EC7 | 3 |
| `😀` | U+1F600 | 4 |

Vì vậy, không được cắt một mảng UTF-8 tại vị trí bất kỳ rồi giả định phần còn lại vẫn là văn bản hợp lệ. Nếu chia dữ liệu theo byte, cần dùng ranh giới code point hoặc một giao thức phân khung phù hợp.

### 3.3. UTF-8 và ASCII

Các byte UTF-8 của ký tự ASCII giữ nguyên giá trị ASCII. Điều này giúp nhiều định dạng văn bản và giao thức có cấu trúc bằng các ký tự ASCII hoạt động thuận tiện với nội dung Unicode. Tuy nhiên, ký tự ngoài ASCII có thể cần nhiều byte.

Không dùng `US_ASCII` cho văn bản tiếng Việt. Những ký tự không biểu diễn được trong charset đích sẽ phải được báo lỗi hoặc thay thế tùy API và chính sách encoder.

## 4. Chọn Charset tường minh khi làm việc với tệp

### 4.1. `Files.writeString` và `Files.readString`

Các phương thức `Files.writeString` và `Files.readString` có từ Java 11. Overload không nhận charset dùng UTF-8 theo hợp đồng API; overload nhận `Charset` cho phép nêu rõ lựa chọn ngay tại nơi trao đổi dữ liệu.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("message.txt");
        String content = "Xin chào Java 17";

        Files.writeString(path, content, StandardCharsets.UTF_8);
        String loaded = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println(content.equals(loaded)); // true
    }
}
~~~

Việc truyền charset rõ ràng giúp người đọc mã thấy ngay định dạng byte của tệp. Dù overload không charset của hai phương thức này dùng UTF-8, việc ghi rõ charset vẫn có ích khi tài liệu hóa hợp đồng hoặc khi mã có nhiều loại dữ liệu.

### 4.2. `Files.newBufferedReader` và `Files.newBufferedWriter`

Với xử lý theo dòng hoặc dữ liệu lớn, có thể dùng reader/writer có buffer:

~~~java
Path path = Path.of("report.txt");

try (var writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Dòng thứ nhất");
    writer.newLine();
    writer.write("Dòng thứ hai");
}

try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

`try-with-resources` đảm bảo reader/writer được đóng khi kết thúc hoặc khi có lỗi. `newLine()` dùng line separator của hệ điều hành hiện tại; nếu giao thức yêu cầu newline cố định như LF hoặc CRLF, hãy ghi đúng ký tự theo đặc tả thay vì phụ thuộc vào `newLine()`.

### 4.3. `Files.readAllLines`

~~~java
List<String> lines = Files.readAllLines(
        Path.of("input.txt"),
        StandardCharsets.UTF_8);
~~~

Phương thức này đọc toàn bộ tệp thành danh sách dòng. Với tệp rất lớn, cân nhắc `Files.lines(path, charset)` để xử lý theo stream và đóng stream đúng cách:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

`Files.lines` trả về Stream gắn với tài nguyên tệp; phải đóng bằng try-with-resources. Việc chỉ gọi terminal operation không thay thế trách nhiệm đóng stream.

## 5. Chọn Charset khi làm việc với Reader và Writer

### 5.1. `InputStreamReader`

`InputStreamReader` là cầu nối từ byte stream sang character stream. Constructor nhận charset rõ ràng:

~~~java
try (var reader = new InputStreamReader(
        inputStream, StandardCharsets.UTF_8)) {
    // Đọc ký tự đã được giải mã theo UTF-8.
}
~~~

Nếu dùng constructor chỉ nhận `InputStream`, charset mặc định của nền tảng được sử dụng. Điều đó có thể làm cùng một byte sequence được giải mã khác nhau trên các môi trường.

### 5.2. `OutputStreamWriter`

`OutputStreamWriter` chuyển ký tự sang byte:

~~~java
try (var writer = new OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
}
~~~

Đóng writer hoặc flush khi phù hợp để đảm bảo dữ liệu đã được đẩy xuống byte stream. Trong ví dụ thực tế, quyền sở hữu và đóng stream cần được xác định rõ: nếu wrapper sở hữu stream thì đóng wrapper sẽ đóng stream bên dưới.

### 5.3. `FileReader` và `FileWriter`

Với API file dạng reader/writer, chọn constructor có charset:

~~~java
try (var reader = new FileReader(file, StandardCharsets.UTF_8);
     var writer = new FileWriter(outputFile, StandardCharsets.UTF_8)) {
    // Đọc/ghi ký tự theo UTF-8.
}
~~~

Các constructor nhận `Charset` có trong Java 17. Khi viết mã mới, API `Files.newBufferedReader` và `Files.newBufferedWriter` thường thuận tiện vì làm việc trực tiếp với `Path` và có overload charset rõ ràng.

## 6. Tránh charset mặc định của nền tảng tại ranh giới trao đổi

### 6.1. Những lời gọi dễ gây phụ thuộc môi trường

Các dạng sau không nêu charset:

~~~java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);

InputStreamReader reader = new InputStreamReader(inputStream);
OutputStreamWriter writer = new OutputStreamWriter(outputStream);
~~~

Chúng sử dụng charset mặc định của nền tảng hoặc cơ chế mặc định tương ứng. Trên các môi trường Java 17 khác nhau, mặc định có thể không giống nhau.

Hãy thay bằng:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);

InputStreamReader reader =
        new InputStreamReader(inputStream, StandardCharsets.UTF_8);
OutputStreamWriter writer =
        new OutputStreamWriter(outputStream, StandardCharsets.UTF_8);
~~~

### 6.2. Java 17 và thay đổi mặc định ở Java 18

Trong Java 17, `Charset.defaultCharset()` phản ánh charset mặc định của môi trường chạy; không nên giả định nó luôn là UTF-8. JEP 400 thay đổi mặc định của Java sang UTF-8 từ JDK 18, nhưng một ứng dụng đặt mục tiêu Java 17 vẫn cần coi platform default là cấu hình môi trường.

Có thể xem giá trị hiện tại để chẩn đoán:

~~~java
System.out.println(Charset.defaultCharset());
~~~

Đây là thông tin chẩn đoán, không phải cách xác định charset mà đối tác trao đổi đang dùng. Đừng viết giao thức kiểu “bên gửi dùng default charset của máy mình, bên nhận cũng dùng default charset của máy mình”.

### 6.3. Đừng sửa lỗi bằng cách đổi charset mặc định toàn JVM

Thiết lập toàn cục có thể ảnh hưởng những thư viện và API khác trong tiến trình. Cách bền vững hơn là chỉ định charset tại điểm đọc/ghi cần có hợp đồng cụ thể:

~~~java
Files.writeString(path, payload, StandardCharsets.UTF_8);
String payload = Files.readString(path, StandardCharsets.UTF_8);
~~~

Một chương trình có thể đồng thời làm việc với nhiều định dạng: dữ liệu trao đổi UTF-8, một tệp legacy theo charset đã được quy định, và nội dung nội bộ khác. Không nên ép mọi dữ liệu thành một encoding chỉ bằng cấu hình mặc định toàn cục.

## 7. Dữ liệu sai encoding và chính sách xử lý lỗi

Không phải mọi dãy byte đều là chuỗi UTF-8 hợp lệ. Một sequence có thể chứa byte tiếp nối không hợp lệ, thiếu byte ở cuối hoặc mã hóa một giá trị không được phép theo UTF-8.

### 7.1. Giải mã bằng `new String` có thể thay thế dữ liệu lỗi

Constructor:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

không cung cấp cơ chế báo lỗi chi tiết cho dữ liệu malformed; các sequence không hợp lệ được thay bằng ký tự thay thế theo hành vi của charset decoder dùng bên trong. Vì vậy, nếu ứng dụng cần **từ chối dữ liệu lỗi**, không nên chỉ dựa vào việc tạo `String` rồi kiểm tra kết quả bằng mắt.

### 7.2. Dùng CharsetDecoder với REPORT

Khi cần xử lý nghiêm ngặt, dùng `CharsetDecoder` và yêu cầu báo lỗi:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String decoded = decoder.decode(ByteBuffer.wrap(bytes)).toString();
~~~

Nếu dữ liệu có sequence malformed hoặc unmappable, thao tác decode ném `CharacterCodingException`. Đây là cách phù hợp khi dữ liệu đến từ đối tác, tệp import hoặc một giao thức mà lỗi encoding cần được phát hiện thay vì âm thầm thay thế.

Các chính sách của `CodingErrorAction`:

| Chính sách | Hành vi |
|---|---|
| `REPORT` | Báo lỗi bằng `CharacterCodingException` |
| `REPLACE` | Thay phần dữ liệu lỗi bằng replacement value |
| `IGNORE` | Bỏ qua phần dữ liệu lỗi |

`REPORT` thường phù hợp khi cần xác thực dữ liệu trao đổi. `REPLACE` hoặc `IGNORE` chỉ nên dùng khi đặc tả nghiệp vụ cho phép mất thông tin và hệ thống có chủ đích xử lý như vậy.

### 7.3. Mã hóa bằng CharsetEncoder

Tương tự, nếu một chuỗi Java chứa ký tự không biểu diễn được trong charset đích, encoder có thể báo lỗi, thay thế hoặc bỏ qua tùy chính sách.

~~~java
var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

ByteBuffer encoded = encoder.encode(CharBuffer.wrap("Tiếng Việt"));
~~~

Đoạn mã trên ném lỗi vì US-ASCII không thể biểu diễn các ký tự tiếng Việt. Đây là kết quả tốt nếu giao thức thực sự chỉ chấp nhận ASCII: chương trình phát hiện vi phạm thay vì gửi một nội dung đã bị thay thế.

Nếu giao thức yêu cầu UTF-8, hãy chọn UTF-8 ngay từ đầu thay vì cố ép văn bản Unicode sang ASCII.

## 8. BOM và byte đầu tệp

BOM (*Byte Order Mark*) là dấu hiệu ở đầu byte stream, thường gặp trong một số tệp Unicode. Với UTF-8, chuỗi byte BOM là `EF BB BF`; nó không cần thiết để xác định byte order vì UTF-8 không có nhiều thứ tự byte như UTF-16.

Khi dùng `StandardCharsets.UTF_8`, không nên mặc định rằng BOM sẽ tự động bị bỏ. UTF-8 decoder tiêu chuẩn có thể giải mã ba byte BOM thành ký tự U+FEFF ở đầu `String`. Nếu định dạng tệp cho phép BOM và ứng dụng muốn loại bỏ nó, hãy xử lý rõ ràng tại ranh giới đọc:

~~~java
static String removeLeadingBom(String text) {
    if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
        return text.substring(1);
    }
    return text;
}
~~~

Không xóa U+FEFF ở mọi vị trí trong văn bản. Chỉ xử lý BOM đầu luồng theo đặc tả dữ liệu; ký tự U+FEFF xuất hiện ở vị trí khác có thể là nội dung thực tế hoặc dữ liệu cần phân tích riêng.

Với UTF-16, byte order và BOM có vai trò khác; nếu giao thức yêu cầu UTF-16BE hoặc UTF-16LE, chọn đúng charset cụ thể theo đặc tả.

## 9. Newline và định dạng văn bản cũng là một phần của hợp đồng

Chọn đúng charset chưa đảm bảo hai phía hiểu nội dung giống nhau nếu quy ước newline hoặc định dạng khác nhau.

Các ký tự thường gặp:

| Tên | Ký hiệu Java | Code point | Ý nghĩa |
|---|---|---|---|
| LF | `\n` | U+000A | Line feed |
| CR | `\r` | U+000D | Carriage return |
| CRLF | `\r\n` | U+000D U+000A | Cặp xuống dòng |

`BufferedReader.readLine()` loại bỏ line terminator khỏi chuỗi dòng trả về. `BufferedWriter.newLine()` ghi line separator của nền tảng. Nếu định dạng trao đổi yêu cầu LF hoặc CRLF cụ thể, hãy ghi và kiểm tra chính xác:

~~~java
String payload = "first\nsecond\n";
Files.writeString(path, payload, StandardCharsets.UTF_8);
~~~

Đoạn mã trên ghi LF trong nội dung `payload`. Không thay nó bằng `newLine()` nếu giao thức yêu cầu LF trên mọi hệ điều hành.

## 10. Ví dụ trao đổi dữ liệu hoàn chỉnh

Ví dụ sau mô phỏng ghi và đọc một tệp UTF-8, xác nhận nội dung bằng so sánh chuỗi và hiển thị byte:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class Main {
    public static void main(String[] args) throws IOException {
        Path file = Path.of("exchange.txt");
        String message = "Xin chào — tiếng Việt: ă, â, ê, ô, ơ, ư";

        // Bên gửi: chọn UTF-8 theo hợp đồng trao đổi.
        Files.writeString(file, message, StandardCharsets.UTF_8);

        // Bên nhận: dùng đúng charset đã thỏa thuận.
        String received = Files.readString(file, StandardCharsets.UTF_8);

        System.out.println(message.equals(received)); // true
        System.out.println(received);

        byte[] encoded = message.getBytes(StandardCharsets.UTF_8);
        System.out.println(HexFormat.of().formatHex(encoded));
    }
}
~~~

Biên dịch và chạy trên JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 Main.java
java Main
~~~

Tùy nội dung và encoding của terminal, phần hiển thị tiếng Việt có thể phụ thuộc cấu hình console. Tuy nhiên, phép so sánh trong chương trình kiểm tra nội dung `String` sau khi đọc bằng UTF-8; chuỗi hex cho biết byte đã được mã hóa.

Để mô phỏng sai charset, có thể cố ý giải mã byte UTF-8 bằng US-ASCII hoặc một charset không phù hợp, rồi so sánh với chuỗi gốc. Với ký tự không biểu diễn được, kết quả có thể chứa replacement character hoặc phát sinh lỗi nếu dùng decoder strict.

## 11. Ví dụ với byte stream và Reader/Writer

Khi giao tiếp qua socket, HTTP body hoặc API chỉ cung cấp InputStream/OutputStream, cần tạo cầu nối ký tự với charset rõ ràng:

~~~java
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

try (var writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_8)) {
    writer.write("status=ready\n");
    writer.flush();
}

try (var reader = new InputStreamReader(inputStream, StandardCharsets.UTF_8)) {
    char[] buffer = new char[1024];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        // Xử lý đúng count ký tự đã đọc.
    }
}
~~~

Trong ứng dụng thực tế, không nhất thiết phải đóng stream gốc tại đây nếu nó được quản lý bởi một lớp bên ngoài. Hãy tuân thủ quyền sở hữu tài nguyên của API. Điểm chính là **charset được chọn ở lớp chuyển byte thành ký tự và ngược lại**, không được suy đoán từ terminal hoặc máy chủ.

## 12. Charset trong giao thức và định dạng trao đổi

### 12.1. HTTP

Với HTTP, charset có thể được quy định bởi định dạng nội dung và header. Khi gửi/nhận text, cần theo hợp đồng của media type và API client/server. Không tự ý giả định mọi body đều UTF-8 nếu giao thức hoặc header quy định khác; cũng không dùng charset của máy chạy làm thay thế cho metadata giao thức.

Nếu ứng dụng tự tạo body UTF-8:

~~~java
byte[] body = json.getBytes(StandardCharsets.UTF_8);
~~~

thì phần khai báo content type phải nhất quán với byte body, ví dụ media type JSON theo quy ước của hệ thống. Khi nhận, đọc byte body theo charset mà định dạng quy định.

### 12.2. JSON, CSV và XML

- **JSON:** hệ sinh thái hiện đại sử dụng UTF-8 phổ biến; hãy tuân thủ đặc tả và API parser/serializer đang dùng. Text block hoặc String không tự biến thành JSON hợp lệ.
- **CSV:** phải thống nhất charset, dấu phân cách, quy tắc quote, newline và header. Cùng UTF-8 nhưng hai file CSV vẫn có thể khác cấu trúc.
- **XML:** khai báo encoding trong XML declaration phải khớp byte thực tế. Parser XML phù hợp nên được giao nhiệm vụ đọc declaration và byte stream theo quy tắc XML, thay vì tự decode sai trước rồi truyền String đã hỏng.

Không chỉ định charset theo thói quen nếu dữ liệu đầu vào đã có đặc tả riêng. Charset là một phần của hợp đồng dữ liệu, cùng với cú pháp và framing.

## 13. Kiểm tra và xác thực dữ liệu trao đổi

### 13.1. Round-trip không đủ để chứng minh giao thức đúng

Nếu cùng một chương trình encode và decode bằng cùng charset, round-trip có thể thành công:

~~~java
String original = "Café";
String decoded = new String(
        original.getBytes(StandardCharsets.UTF_8),
        StandardCharsets.UTF_8);
~~~

Điều này chứng minh cặp API tương thích với dữ liệu thử. Nó không chứng minh đối tác cũng dùng UTF-8, cũng không xác nhận quy tắc BOM, newline hoặc normalization.

### 13.2. Kiểm tra bằng byte thực tế

~~~java
byte[] bytes = "Aé".getBytes(StandardCharsets.UTF_8);
System.out.println(HexFormat.of().formatHex(bytes)); // 41c3a9
~~~

`A` có byte UTF-8 `41`; `é` (U+00E9) có byte UTF-8 `C3 A9`. Dùng byte dump giúp xác định dữ liệu đang được encode ra sao mà không phụ thuộc font hiển thị.

### 13.3. Kiểm tra lỗi decode

Với dữ liệu ngoài hệ thống, hãy quyết định rõ:

1. Dữ liệu malformed có bị từ chối không?
2. Có cho phép thay thế bằng U+FFFD không?
3. Có ghi log vị trí hoặc nguồn gây lỗi không?
4. Có giới hạn kích thước đầu vào để tránh đọc dữ liệu quá lớn không?
5. Charset có được lấy từ cấu hình đáng tin cậy hay từ metadata giao thức không?

Với dữ liệu nghiệp vụ quan trọng, thường nên dùng decoder strict để phát hiện lỗi sớm. Không âm thầm bỏ ký tự hoặc thay thế nội dung nếu điều đó có thể làm thay đổi mã định danh, chữ ký, số tiền hoặc dữ liệu kiểm soát.

## 14. Những lỗi thường gặp

### 14.1. Dùng `getBytes()` không tham số để gửi dữ liệu

~~~java
byte[] bytes = message.getBytes(); // Phụ thuộc charset mặc định.
~~~

Sửa:

~~~java
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
~~~

### 14.2. Ghi UTF-8 nhưng đọc bằng charset khác

Nếu ghi bằng UTF-8 và đọc bằng charset khác, nội dung có thể sai. Hãy giữ một hợp đồng charset xuyên suốt:

~~~java
Files.writeString(path, text, StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
~~~

### 14.3. Nghĩ Java 17 luôn dùng UTF-8 mặc định

Java 17 chưa có mặc định UTF-8 phổ quát như thay đổi được chuẩn hóa từ Java 18. Đừng dựa vào platform default khi trao đổi dữ liệu.

### 14.4. Dùng ASCII cho văn bản tiếng Việt

ASCII không thể biểu diễn dấu tiếng Việt. Dùng charset phù hợp như UTF-8 nếu định dạng cho phép.

### 14.5. Không phân biệt byte và ký tự

Một code point UTF-8 có thể chiếm nhiều byte; không cắt byte array theo chỉ số ký tự. Hãy xử lý văn bản sau decode hoặc dùng framing theo byte được định nghĩa rõ.

### 14.6. Bỏ qua malformed input

Nếu dữ liệu sai, thay thế hoặc bỏ qua có thể làm thay đổi nội dung mà hệ thống không nhận ra. Chọn `CodingErrorAction` phù hợp với hợp đồng và yêu cầu toàn vẹn.

### 14.7. Xử lý BOM ở mọi vị trí

Chỉ xử lý BOM đầu luồng theo định dạng. Không xóa mọi ký tự U+FEFF khỏi nội dung một cách vô điều kiện.

### 14.8. Cho rằng chọn UTF-8 đã giải quyết mọi khác biệt văn bản

UTF-8 thống nhất cách mã hóa byte, nhưng không tự thống nhất newline, Unicode normalization, dấu phân cách, quote, BOM hoặc cấu trúc dữ liệu. Những quy tắc đó vẫn cần được mô tả riêng.

## 15. Bài tập thực hành

### Bài 1 — Ghi và đọc UTF-8

Viết chương trình ghi chuỗi `"Lập trình Java 17 — tiếng Việt"` ra file bằng UTF-8 rồi đọc lại bằng UTF-8. Kiểm tra `original.equals(restored)`.

Gợi ý:

~~~java
Files.writeString(path, original, StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
~~~

### Bài 2 — Quan sát byte

Mã hóa `"Aé"` bằng UTF-8, in hex bằng `HexFormat.of().formatHex(bytes)`. Giải thích vì sao kết quả là `41c3a9`.

### Bài 3 — Phát hiện charset mặc định

In `Charset.defaultCharset()` trên môi trường Java 17 đang dùng. Giải thích tại sao kết quả đó không được dùng làm hợp đồng cho tệp hoặc giao thức trao đổi với máy khác.

### Bài 4 — Strict decoder

Tạo một byte array UTF-8 không hợp lệ (ví dụ một byte tiếp nối đứng riêng), giải mã bằng `CharsetDecoder` với `CodingErrorAction.REPORT` và xử lý `CharacterCodingException`. So sánh với constructor `new String(bytes, UTF_8)`.

### Bài 5 — BOM

Tạo chuỗi byte bắt đầu bằng `EF BB BF` rồi theo sau là nội dung UTF-8. Giải mã, kiểm tra ký tự đầu tiên có phải U+FEFF không, và chỉ loại bỏ ký tự đó nếu định dạng tệp quy định BOM ở đầu.

### Bài 6 — Newline theo giao thức

Ghi nội dung có LF tường minh bằng `Files.writeString`. Đọc lại và kiểm tra `endsWith("\\n")`. Giải thích vì sao `BufferedWriter.newLine()` có thể tạo line separator khác trên nền tảng khác.

## 16. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Giải thích vai trò của charset trong chuyển đổi `String` ↔ byte[].
2. Dùng `StandardCharsets.UTF_8` ở cả bên ghi và bên đọc dữ liệu trao đổi.
3. Dùng overload có charset của `Files`, `InputStreamReader`, `OutputStreamWriter` hoặc reader/writer tương ứng.
4. Nhận ra API nào đang phụ thuộc charset mặc định và giải thích vì sao không nên dùng nó tại ranh giới giao thức.
5. Phân biệt hành vi mặc định Java 17 với thay đổi UTF-8 default từ Java 18.
6. Xử lý malformed/unmappable input bằng `CharsetDecoder`/`CharsetEncoder` và `CodingErrorAction` phù hợp.
7. Giải thích BOM, newline và giới hạn giữa byte, code unit, code point.
8. Kiểm tra round-trip và byte thực tế; không chỉ dựa vào console hoặc việc hai phía trong cùng một chương trình cùng dùng một charset.
9. Chọn charset theo đặc tả tệp/giao thức và giữ nhất quán giữa các hệ thống.

## 17. Tài liệu chính thức

- [Java SE 17 API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn có sẵn.
- [Java SE 17 API — `Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): charset, tên chuẩn, charset mặc định và factory.
- [Java SE 17 API — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [`CharsetEncoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): giải mã/mã hóa và chính sách lỗi.
- [Java SE 17 API — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): đọc/ghi String, reader, writer và stream với charset.
- [Java SE 17 API — `InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) và [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html): cầu nối byte stream và character stream.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ JDK 18; hữu ích để hiểu vì sao Java 17 cần thận trọng với platform default.

**Ghi nhớ:** dữ liệu trao đổi là byte theo một hợp đồng cụ thể. Hãy chọn charset từ đặc tả, ghi rõ nó tại nơi encode/decode, xác thực dữ liệu lỗi và kiểm tra byte thực tế. UTF-8 là lựa chọn phổ biến, nhưng tính đúng đắn đến từ việc hai phía tuân theo cùng một hợp đồng, không phải từ giả định về máy đang chạy.
