# Bảng mã tường minh khi chuyển byte sang văn bản

Dữ liệu trong file, socket hoặc HTTP body thường đến dưới dạng byte. Để biến byte thành ký tự Java, chương trình phải biết **charset (bảng mã)** dùng để mã hóa dữ liệu. Chiều ngược lại, khi ghi văn bản ra byte, chương trình cũng phải chọn charset để các bên đọc có thể giải mã đúng.

Java cung cấp `java.nio.charset.Charset`, `CharsetDecoder`, `CharsetEncoder` và các hằng chuẩn trong `StandardCharsets`. Hãy chỉ định charset theo hợp đồng của file hoặc giao thức. UTF-8 là lựa chọn phổ biến cho dữ liệu văn bản mới, nhưng không được tự ý giả định mọi nguồn dữ liệu đều dùng UTF-8.

## Mục tiêu

- Phân biệt byte, ký tự và charset.
- Chuyển đổi hai chiều bằng `String`, `InputStreamReader` và `OutputStreamWriter` với charset tường minh.
- Dùng `StandardCharsets` và các API `Files` để đọc/ghi văn bản.
- Hiểu rủi ro khi dựa vào charset mặc định của môi trường.
- Phát hiện dữ liệu byte không hợp lệ bằng `CharsetDecoder` và `CharsetEncoder`.
- Chọn cách đọc phù hợp với kích thước dữ liệu và xử lý lỗi chuyển đổi rõ ràng.

## 1. Byte không tự mang thông tin charset

Một `byte[]` chỉ là dãy giá trị byte. Nó không tự cho biết các byte đó biểu diễn văn bản theo UTF-8, UTF-16, ISO-8859-1 hay một charset khác.

Cùng một byte có thể biểu diễn ký tự khác nhau tùy charset. Nếu giải mã bằng charset sai, chương trình có thể tạo ra ký tự sai, ký tự thay thế `�` hoặc dữ liệu bị mất. Việc giải mã thành công mà không ném ngoại lệ cũng không chứng minh charset đã chọn là đúng.

Quy trình chuyển đổi:

~~~text
Văn bản Java (String)
        | encode bằng Charset
        v
      byte[]
        | decode bằng cùng charset
        v
Văn bản Java (String)
~~~

Charset là quy tắc ánh xạ giữa chuỗi ký tự và chuỗi byte. `CharsetEncoder` thực hiện chiều ký tự sang byte; `CharsetDecoder` thực hiện chiều byte sang ký tự.

### 1.1. UTF-8 và các charset chuẩn

`StandardCharsets` cung cấp các hằng chuẩn mà mọi implementation Java phải hỗ trợ:

| Hằng | Ý nghĩa |
| --- | --- |
| `StandardCharsets.UTF_8` | UTF-8; mã hóa Unicode theo độ dài biến đổi từ 1 đến 4 byte cho một code point |
| `StandardCharsets.UTF_16` | UTF-16 |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian |
| `StandardCharsets.US_ASCII` | ASCII |
| `StandardCharsets.ISO_8859_1` | ISO-8859-1 |

Ưu tiên các hằng này khi giao thức hoặc định dạng quy định một trong các charset chuẩn. Nếu tên charset đến từ cấu hình, có thể dùng `Charset.forName(name)`; tên không được hỗ trợ sẽ gây `UnsupportedCharsetException`.

Không chọn charset chỉ dựa vào locale của máy hoặc ngôn ngữ mà người dùng đang dùng. Charset là một phần của hợp đồng dữ liệu, cần thống nhất giữa bên ghi và bên đọc.

## 2. Chuyển byte sang String và String sang byte

`String` cung cấp các overload nhận charset để chuyển đổi tường minh:

- `new String(byte[], Charset)` giải mã byte thành văn bản.
- `String.getBytes(Charset)` mã hóa văn bản thành byte.

~~~java
String message = "Xin chào";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);

System.out.println(restored); // Xin chào
~~~

Phải dùng cùng charset ở hai chiều nếu muốn khôi phục đúng văn bản. Nếu bên gửi dùng UTF-8 nhưng bên nhận giải mã bằng một charset khác, kết quả có thể bị sai.

### 2.1. Tránh overload dựa vào charset mặc định

Các cách gọi như `new String(bytes)` và `text.getBytes()` dùng charset mặc định của JVM. Kết quả vì thế có thể phụ thuộc cấu hình hoặc môi trường chạy.

Java 9 vẫn có thể chạy với charset mặc định phụ thuộc môi trường. Từ Java 18, UTF-8 được chuẩn hóa làm charset mặc định trong chế độ mặc định của JDK. Sự thay đổi đó giúp tính nhất quán tốt hơn, nhưng không thay thế hợp đồng của dữ liệu bên ngoài: file cũ, giao thức mạng hoặc hệ thống khác vẫn có thể quy định một charset cụ thể.

Vì vậy, hãy chỉ định charset tường minh ở ranh giới I/O, kể cả khi charset đó trùng với charset mặc định trên máy hiện tại.

### 2.2. Độ dài String không phải độ dài byte

`String.length()` trả về số đơn vị mã UTF-16 (code unit), không phải số byte sau khi mã hóa. Một chuỗi có thể chiếm số byte khác nhau tùy charset.

~~~java
String text = "é";
System.out.println(text.length());
System.out.println(text.getBytes(StandardCharsets.UTF_8).length);
~~~

Với ví dụ trên, `String.length()` là `1`, còn UTF-8 cần `2` byte. Nếu cần biết dung lượng dữ liệu truyền hoặc ghi, hãy đo byte sau khi mã hóa bằng đúng charset.

## 3. Đọc và ghi văn bản bằng Reader/Writer

Trong Java I/O, `InputStream` và `OutputStream` làm việc với byte. `Reader` và `Writer` làm việc với ký tự. Các lớp cầu nối chuyển đổi giữa hai miền này.

### 3.1. InputStreamReader

`InputStreamReader` chuyển byte từ một `InputStream` thành ký tự. Dùng constructor nhận `Charset` để chỉ định cách giải mã:

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

`BufferedReader` bổ sung buffering và tiện ích `readLine()`. Khi reader được đóng, stream byte bên dưới cũng được đóng; do đó cần quản lý ownership của `inputStream` rõ ràng và tránh đóng cùng tài nguyên ở nhiều nơi không cần thiết.

### 3.2. OutputStreamWriter

`OutputStreamWriter` chuyển ký tự Java thành byte theo charset được chọn:

~~~java
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(outputStream, StandardCharsets.UTF_8))) {
    writer.write("Xin chào");
    writer.newLine();
}
~~~

Khi đóng writer, dữ liệu đệm được flush và stream byte bên dưới cũng được đóng. Nếu cần tiếp tục sử dụng `outputStream` sau khi ghi, phải thiết kế rõ ai sở hữu và đóng tài nguyên; việc đóng writer sẽ đóng stream bên dưới.

### 3.3. Đóng tài nguyên

Reader/Writer có thể giữ file descriptor, socket hoặc tài nguyên I/O khác. Dùng try-with-resources để đóng chúng ngay cả khi đọc/ghi phát sinh ngoại lệ. Charset được truyền vào constructor chỉ quyết định chuyển đổi byte/ký tự; nó không tự quản lý vòng đời stream.

## 4. Dùng charset tường minh với java.nio.file.Files

`Files` cung cấp các API tiện dụng cho văn bản:

| API | Công dụng |
| --- | --- |
| `Files.newBufferedReader(path, charset)` | Mở reader có buffer để đọc file văn bản |
| `Files.newBufferedWriter(path, charset, options...)` | Mở writer có buffer để ghi file văn bản |
| `Files.readAllLines(path, charset)` | Đọc tất cả dòng thành `List<String>` |
| `Files.write(path, lines, charset, options...)` | Ghi các dòng văn bản theo charset |
| `Files.readAllBytes(path)` | Đọc byte thô; cần giải mã riêng bằng charset |
| `Files.write(path, byte[])` | Ghi byte thô đã được mã hóa trước |

`Files.newBufferedReader(path, charset)` và `Files.newBufferedWriter(path, charset, ...)` giúp charset xuất hiện rõ ngay tại điểm mở file.

~~~java
Path path = Paths.get("message.txt");

try (BufferedWriter writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Dữ liệu tiếng Việt");
}

try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
~~~

Ví dụ dùng `Paths.get()` để tương thích Java 9. Các API như `Files.readString()` và `Files.writeString()` chỉ có từ Java 11, nên không dùng chúng trong ví dụ yêu cầu biên dịch bằng Java 9.

### 4.1. Khi nào đọc toàn bộ byte?

`Files.readAllBytes(path)` phù hợp khi dữ liệu nhỏ và cần xử lý byte trực tiếp. Sau đó giải mã bằng charset đã biết:

~~~java
byte[] bytes = Files.readAllBytes(path);
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Với file lớn, không nên nạp toàn bộ file vào bộ nhớ chỉ để đọc văn bản. Hãy dùng `Files.newBufferedReader()` hoặc `InputStreamReader` để xử lý theo luồng.

### 4.2. Dữ liệu nhị phân không phải văn bản

Không chuyển ảnh, PDF nhị phân, file nén hoặc dữ liệu giao thức nhị phân thành `String` chỉ để lưu trữ hay truyền tiếp. Charset decoder có thể thay thế hoặc diễn giải byte thành ký tự mà không giữ nguyên dữ liệu gốc. Hãy giữ nguyên `byte[]`, `ByteBuffer`, `InputStream` hoặc `OutputStream` cho dữ liệu nhị phân.

## 5. Xử lý dữ liệu không hợp lệ

Không phải mọi chuỗi byte đều hợp lệ theo charset đã chọn. Ví dụ, một byte mở đầu UTF-8 có thể thiếu byte tiếp theo hoặc theo sau bởi byte không hợp lệ.

### 5.1. Hành vi của String constructor

`new String(bytes, charset)` là API tiện lợi. Khi chuỗi byte không hợp lệ hoặc không ánh xạ được, decoder dùng ký tự thay thế theo hợp đồng của API thay vì cung cấp cơ chế báo lỗi chi tiết cho caller.

Điều này hữu ích khi ứng dụng chấp nhận thay thế dữ liệu lỗi. Nhưng nếu dữ liệu cần được xác thực nghiêm ngặt, ví dụ file cấu hình, dữ liệu trao đổi hoặc nội dung có yêu cầu toàn vẹn, nên dùng `CharsetDecoder` và chọn chính sách lỗi rõ ràng.

### 5.2. CharsetDecoder và CodingErrorAction

`CharsetDecoder` cho phép cấu hình cách xử lý dữ liệu malformed hoặc unmappable:

| Chính sách | Hành vi |
| --- | --- |
| `CodingErrorAction.REPORT` | Báo lỗi bằng `CharacterCodingException` |
| `CodingErrorAction.REPLACE` | Thay phần dữ liệu lỗi bằng replacement string |
| `CodingErrorAction.IGNORE` | Bỏ qua phần dữ liệu lỗi |

Ví dụ yêu cầu UTF-8 hợp lệ:

~~~java
byte[] bytes = ...;
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

String text = decoder.decode(ByteBuffer.wrap(bytes)).toString();
~~~

`decode()` có thể ném `CharacterCodingException`. Caller cần quyết định báo lỗi, từ chối dữ liệu hay áp dụng chính sách phục hồi. Không nên âm thầm bỏ qua lỗi nếu dữ liệu sai có thể làm thay đổi ý nghĩa nghiệp vụ hoặc tạo rủi ro bảo mật.

### 5.3. CharsetEncoder khi ghi

Chiều mã hóa cũng có thể gặp ký tự không biểu diễn được trong charset đã chọn. Ví dụ, ASCII không thể biểu diễn `é`. `CharsetEncoder` cho phép báo lỗi thay vì thay thế âm thầm:

~~~java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

ByteBuffer encoded = encoder.encode(CharBuffer.wrap("café"));
~~~

Đoạn mã trên ném `CharacterCodingException` vì `é` không thuộc ASCII. Nếu dùng charset hỗ trợ toàn bộ nội dung như UTF-8, ký tự đó có thể được mã hóa.

### 5.4. Chọn chính sách theo dữ liệu

- Dùng `REPORT` khi dữ liệu lỗi phải bị từ chối hoặc cần điều tra.
- Dùng `REPLACE` khi nghiệp vụ chấp nhận ký tự thay thế và việc mất một phần thông tin là có chủ đích.
- Dùng `IGNORE` chỉ khi hợp đồng dữ liệu cho phép bỏ phần lỗi; đây là lựa chọn dễ làm mất thông tin nên cần cân nhắc kỹ.

Không dùng `IGNORE` để che lỗi encoding trong dữ liệu cần toàn vẹn. Hãy ghi log đủ ngữ cảnh nhưng tránh ghi nội dung nhạy cảm của dữ liệu.

## 6. Charset và dữ liệu bên ngoài

Charset phải đến từ hợp đồng của nguồn dữ liệu:

- File định dạng có quy định encoding: dùng đúng encoding trong đặc tả file hoặc metadata.
- Giao thức mạng: dùng charset mà giao thức hoặc header của payload quy định.
- Database hoặc message queue: thống nhất encoding giữa producer và consumer.
- Dữ liệu do ứng dụng tự tạo: chọn một charset rõ ràng, thường là UTF-8, và ghi nhận trong định dạng trao đổi.

Không thử nhiều charset cho đến khi thấy kết quả “có vẻ đọc được” rồi coi đó là bằng chứng. Một chuỗi byte có thể giải mã hợp lệ theo nhiều charset nhưng chỉ một charset mới đúng với nguồn dữ liệu.

### 6.1. BOM và chữ ký byte

Một số định dạng có thể dùng BOM (*byte order mark*) hoặc metadata để biểu thị encoding hoặc byte order. Cách xử lý BOM phụ thuộc định dạng và hợp đồng của file. `Charset` không thay thế bộ phân tích định dạng: nếu giao thức quy định BOM phải được kiểm tra hoặc loại bỏ, hãy xử lý nó theo đúng đặc tả.

### 6.2. Chuẩn hóa Unicode là vấn đề khác

Hai chuỗi có thể hiển thị giống nhau nhưng dùng chuỗi code point khác nhau, ví dụ ký tự có dấu được biểu diễn bằng một code point dựng sẵn hoặc một chữ cái kết hợp dấu. Charset chuyển đổi giữa ký tự và byte; nó không tự chuẩn hóa Unicode.

Nếu nghiệp vụ cần so sánh văn bản theo dạng chuẩn hóa, hãy dùng `java.text.Normalizer` với dạng chuẩn hóa được yêu cầu. Không nhầm chuẩn hóa Unicode với việc chọn charset.

## 7. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ này thực hiện ba việc: mã hóa và giải mã một chuỗi bằng UTF-8; ghi byte ra file rồi đọc bằng reader có charset tường minh; và từ chối một chuỗi byte không hợp lệ bằng decoder ở chế độ `REPORT`.

**Tệp:** `ExplicitCharsetDemo.java`

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExplicitCharsetDemo {
    public static void main(String[] args) throws IOException {
        String message = "Xin chào – Java";
        byte[] encoded = message.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(encoded, StandardCharsets.UTF_8);
        System.out.println("round-trip: " + decoded);

        Path file = Files.createTempFile("explicit-charset-", ".txt");
        try {
            Files.write(file, encoded);
            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("file: " + reader.readLine());
            }

            byte[] malformedUtf8 = {(byte) 0xC3, (byte) 0x28};
            try {
                StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformedUtf8));
                throw new AssertionError("Invalid UTF-8 was accepted");
            } catch (CharacterCodingException expected) {
                System.out.println("malformed UTF-8 rejected");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~text
javac --release 9 ExplicitCharsetDemo.java
java ExplicitCharsetDemo
~~~

Output:

~~~text
round-trip: Xin chào – Java
file: Xin chào – Java
malformed UTF-8 rejected
~~~

File tạm được xóa trong `finally`. Reader được đóng bằng try-with-resources. Cùng một charset UTF-8 được dùng khi mã hóa và giải mã, vì vậy văn bản được khôi phục đúng.

## 8. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `new String(bytes)` hoặc `getBytes()` | Dựa vào charset mặc định của JVM | Truyền charset tường minh |
| Giải mã UTF-8 bằng charset khác | Bên ghi và bên đọc không dùng cùng hợp đồng encoding | Xác định charset từ định dạng hoặc giao thức |
| Nghĩ `String.length()` là số byte | `length()` đếm UTF-16 code unit | Đếm byte sau khi encode bằng charset thực tế |
| Dùng `new String()` để xác thực dữ liệu lỗi | API tiện lợi có thể thay thế dữ liệu malformed | Dùng `CharsetDecoder` với `REPORT` |
| Ghi ký tự ngoài phạm vi charset | Charset đích không biểu diễn được ký tự | Dùng charset phù hợp hoặc `CharsetEncoder` với chính sách lỗi rõ ràng |
| Đọc file lớn bằng `readAllBytes()` | Nạp toàn bộ dữ liệu vào bộ nhớ | Dùng reader có buffer và xử lý theo luồng |
| Chuyển dữ liệu nhị phân thành String | Charset decoding làm thay đổi cách diễn giải byte | Giữ dữ liệu nhị phân ở dạng byte/stream |
| Nghĩ charset tự loại BOM hoặc chuẩn hóa Unicode | Encoding và xử lý định dạng/normalization là các bước khác nhau | Làm theo hợp đồng định dạng và dùng `Normalizer` khi cần |
| Đóng InputStream riêng trong khi Reader vẫn đang dùng | Reader quản lý stream byte bên dưới | Xác định một nơi sở hữu và đóng tài nguyên |

## 9. Quy tắc thực hành

1. Xác định charset từ hợp đồng file hoặc giao thức trước khi giải mã byte.
2. Chỉ định charset tường minh ở mọi ranh giới chuyển đổi byte/văn bản.
3. Ưu tiên `StandardCharsets.UTF_8` khi định dạng quy định UTF-8; không giả định mọi nguồn đều dùng UTF-8.
4. Dùng `InputStreamReader`/`OutputStreamWriter` với charset rõ ràng cho stream I/O.
5. Dùng `Files.newBufferedReader(path, charset)` và `Files.newBufferedWriter(path, charset)` cho file văn bản.
6. Dùng reader/writer có buffer cho dữ liệu lớn; tránh nạp toàn bộ file vào bộ nhớ khi không cần.
7. Dùng `CharsetDecoder` hoặc `CharsetEncoder` với `REPORT` khi dữ liệu phải hợp lệ nghiêm ngặt.
8. Chỉ dùng `REPLACE` hoặc `IGNORE` khi nghiệp vụ chấp nhận việc thay thế hoặc mất dữ liệu.
9. Giữ dữ liệu nhị phân ở dạng byte; không chuyển nó thành String để lưu trữ hoặc truyền tiếp.
10. Phân biệt encoding, BOM và Unicode normalization; xử lý từng phần theo đặc tả tương ứng.
11. Quản lý Reader/Writer và stream bên dưới bằng try-with-resources, với ownership rõ ràng.

## 10. Tự kiểm tra

- Vì sao `byte[]` không đủ để khôi phục văn bản? Vì byte không tự chứa thông tin charset; cần biết quy tắc mã hóa của nguồn.
- `StandardCharsets.UTF_8` dùng để làm gì? Chỉ định UTF-8 tường minh khi mã hóa hoặc giải mã.
- `new String(bytes)` có dùng charset tường minh không? Không, nó dùng charset mặc định của JVM.
- Vì sao nên truyền charset dù JDK hiện đại mặc định UTF-8? Vì file hoặc giao thức bên ngoài có thể quy định charset khác, và hợp đồng dữ liệu cần rõ ràng.
- `InputStreamReader` làm nhiệm vụ gì? Chuyển byte từ InputStream thành ký tự theo charset.
- `OutputStreamWriter` làm nhiệm vụ gì? Chuyển ký tự thành byte theo charset.
- Khi nào dùng `CharsetDecoder` với `REPORT`? Khi cần phát hiện và từ chối byte malformed hoặc unmappable.
- `new String(bytes, charset)` có phải lựa chọn xác thực encoding nghiêm ngặt không? Không; dùng decoder với `REPORT` khi cần báo lỗi.
- Vì sao `String.length()` không cho biết số byte UTF-8? Vì nó đếm UTF-16 code unit; số byte phụ thuộc charset và nội dung.
- Có nên chuyển ảnh hoặc file nén thành String không? Không; giữ dữ liệu nhị phân ở dạng byte hoặc stream.

Điểm cốt lõi: **charset là một phần của hợp đồng dữ liệu**. Chọn đúng charset ở cả chiều đọc và ghi, dùng decoder/encoder có chính sách lỗi phù hợp, và quản lý stream rõ ràng để tránh sai văn bản hoặc mất dữ liệu.