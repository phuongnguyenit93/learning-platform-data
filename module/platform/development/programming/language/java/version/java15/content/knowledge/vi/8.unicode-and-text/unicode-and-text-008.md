# Giữ encoding tường minh tại ranh giới tệp và mạng trong Java

## 1. Vì sao encoding là hợp đồng của dữ liệu?

Trong Java, một `String` biểu diễn **văn bản**; tệp trên ổ đĩa, gói tin mạng và nội dung HTTP được lưu/truyền dưới dạng **byte**. Mỗi lần chuyển giữa hai thế giới phải có quy tắc mã hóa ký tự (`charset`):

~~~text
Java String  -- encode bằng charset -->  byte[] / tệp / mạng
Java String  <-- decode bằng charset --  byte[] / tệp / mạng
~~~

Ví dụ chữ tiếng Việt, emoji, tiếng Nhật có thể cần nhiều byte trong **UTF-8**. Nếu phía ghi dùng UTF-8 nhưng phía đọc giải mã theo ISO-8859-1 hay một code page khác, chuỗi có thể biến thành ký tự rác (*mojibake*) dù byte trên đĩa và mạng vẫn không hỏng.

Nguyên tắc: **chọn charset theo đặc tả dữ liệu, ghi rõ nó ngay tại ranh giới encode/decode và dùng thống nhất ở cả hai chiều**. Đối với giao thức/tệp mới do nhóm phát triển kiểm soát, UTF-8 thường là lựa chọn phù hợp:

~~~java
import java.nio.charset.StandardCharsets;

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

`StandardCharsets.UTF_8` là hằng số chuẩn có sẵn, không cần tra cứu tên charset hay bắt `UnsupportedEncodingException`. Nếu định dạng bên ngoài **quy định charset khác**, phải dùng đúng charset mà định dạng đó yêu cầu; không thể đổi sang UTF-8 tùy ý rồi kỳ vọng hệ thống nhận đọc chính xác.

### Điều này quan trọng với Java 15 và các bản Java hiện hành như thế nào?

- Với **Java 15–17**, nhiều API dùng charset mặc định của môi trường nếu không truyền `Charset`; kết quả có thể thay đổi theo hệ điều hành/cấu hình.
- Từ **Java 18**, JEP 400 chuẩn hóa UTF-8 làm charset mặc định cho nhiều Java SE API, mặc dù có các tùy chọn tương thích/cấu hình cần lưu ý. **Không nên dựa vào mặc định** khi trao đổi dữ liệu giữa hệ thống hoặc cần bảo đảm hợp đồng giao thức.
- Một số API, chẳng hạn `Files.readString(Path)` và `Files.writeString(Path, ...)`, **đã dùng UTF-8 theo đặc tả từ Java 11**. Viết overload có `StandardCharsets.UTF_8` không phải để sửa lỗi của những overload đó, mà để làm hợp đồng dữ liệu hiển thị rõ trong mã, nhất quán với các API khác.

Bài học sử dụng API vẫn áp dụng trong Java hiện đại, không yêu cầu cơ chế cũ hay flag thử nghiệm.

## 2. Không nhầm ký tự, UTF-16 và byte

`String.length()` đếm **đơn vị mã UTF-16** (`char`), không đếm byte UTF-8 và không nhất thiết đếm số Unicode code point. Đó là ba đại lượng khác nhau:

~~~java
String text = "Chào 🌍";

int units = text.length();                         // 7 đơn vị UTF-16
int points = text.codePointCount(0, text.length()); // 6 code point
int byteCount = text.getBytes(StandardCharsets.UTF_8).length; // 10 byte
~~~

Trong ví dụ, ký tự `à` chiếm 2 byte UTF-8; emoji `🌍` chiếm 4 byte UTF-8 và 2 đơn vị UTF-16. Sự chênh lệch này xuất hiện ngay cả khi biểu diễn trong Java hoàn toàn đúng.

**Hệ quả thực tế:**

- Khi giao thức quy định **độ dài tính bằng byte**, dùng `bytes.length` sau khi encode, không dùng `text.length()`.
- Với tệp, `Files.size(path)` trả độ dài theo byte của tệp; không tương đương số ký tự của `String`.
- Với HTTP, `Content-Length` mô tả số byte của nội dung thông điệp (theo quy tắc HTTP), không phải số đơn vị UTF-16. Thư viện HTTP thường tự tính phần này; không tự đặt header bằng `text.length()`.
- Nếu đang xử lý ký tự Unicode theo code point, dùng API như `codePointCount`/`codePoints()` thay vì giả định mỗi `char` là một ký tự hoàn chỉnh.

## 3. Đọc và ghi tệp văn bản với charset tường minh

### 3.1. Tệp nhỏ: `Files.writeString` và `Files.readString`

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("notes.txt");
String text = "Chào 🌍";

Files.writeString(path, text, StandardCharsets.UTF_8);
String loaded = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(text.equals(loaded)); // true
~~~

Các overload trên có từ Java 11 và vẫn còn phù hợp. `writeString` lưu text thành byte theo charset đã chỉ định; `readString` đọc byte và decode cùng charset. Nếu không truyền tùy chọn mở tệp khác, `writeString` tạo tệp nếu chưa tồn tại và ghi đè nội dung hiện có.

**Chú ý:** `Files.writeString/readString` thường hợp với tệp nhỏ/vừa, không phải lựa chọn tối ưu khi cần xử lý một tệp rất lớn bằng bộ nhớ giới hạn. `readString` tải nội dung tệp thành một `String` trong bộ nhớ.

### 3.2. Tệp lớn: `BufferedReader`/`BufferedWriter` có `Charset`

~~~java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng, không cần tải toàn bộ tệp vào bộ nhớ.
        System.out.println(line);
    }
}

try (var writer = Files.newBufferedWriter(
        Path.of("output.txt"), StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
    writer.newLine();
}
~~~

Đoạn trên là **mã minh họa độc lập theo ngữ cảnh**, giả định biến `path` đã được khai báo như ví dụ phía trước. `readLine()` **loại bỏ dấu kết thúc dòng** khỏi kết quả; `newLine()` ghi dấu kết thúc dòng theo hệ thống. Charset và quy ước xuống dòng là **hai vấn đề khác nhau**: nếu định dạng yêu cầu LF chính xác, hãy chủ động ghi `"\n"` thay vì mặc nhiên dùng `newLine()`.

Không nhầm mã hóa tệp với mã hóa **mã nguồn**. Khi `.java` chứa ký tự tiếng Việt, có thể biên dịch bằng `javac -encoding UTF-8 ...` để mô tả rõ cách trình biên dịch đọc tệp nguồn. Đây là một ranh giới encoding **khác** với thao tác `Files.writeString` tại runtime.

### 3.3. Khi tệp có encoding cũ hoặc khai báo khác

Nếu phải đọc một tệp được mô tả là ISO-8859-1 (hoặc charset khác), hãy dùng charset phù hợp:

~~~java
String text = Files.readString(path, StandardCharsets.ISO_8859_1);
~~~

Không cố sửa lỗi mã hóa bằng cách đọc sai rồi gọi `replace(...)` hàng loạt trên các ký tự hỏng. Quy trình đúng là **xác định charset của dữ liệu gốc, giải mã đúng, rồi chỉ mã hóa lại sang UTF-8 khi muốn chuyển đổi định dạng**. Việc đoán encoding từ byte không phải lúc nào cũng chính xác; nên dùng đặc tả, metadata hoặc thỏa thuận của nguồn cung cấp.

## 4. Stream và socket: chọn charset tại nơi chuyển byte/văn bản

Giao tiếp mạng và nhiều thư viện I/O cung cấp `InputStream`/`OutputStream` (luồng byte). Khi muốn gửi văn bản, đặt lớp encode/decode với charset rõ ràng:

~~~java
try (var writer = new java.io.OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
    writer.flush();
}

try (var reader = new java.io.InputStreamReader(
        inputStream, StandardCharsets.UTF_8)) {
    char[] buffer = new char[1024];
    int n = reader.read(buffer);
    // n là số đơn vị char đã đọc, KHÔNG phải số byte.
}
~~~

Đây là **mã minh họa**, trong đó `inputStream` và `outputStream` phải được cung cấp bởi ứng dụng. Khi đóng `InputStreamReader` hoặc `OutputStreamWriter`, luồng byte bên dưới cũng có thể bị đóng; quản lý vòng đời socket và việc đóng từng chiều theo giao thức, không tự đóng stream trước khi gửi xong toàn bộ thông điệp.

**Charset không thay thế giao thức đóng khung (framing).** TCP gửi *luồng byte*, không tự chia một thông điệp văn bản hoàn chỉnh theo lần gọi `read`. Hai bên còn phải thống nhất cách đánh dấu hết thông điệp: độ dài byte, dấu phân cách, cấu trúc protocol hoặc đóng đúng chiều kết nối. Nếu dùng dấu xuống dòng làm ranh giới, phải nói rõ dùng LF/CRLF, escaping và cách xử lý khi dấu đó xuất hiện trong dữ liệu.

Khi thao tác với `byte[]` trực tiếp, đặt charset ngay tại lệnh chuyển đổi:

~~~java
byte[] body = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(body, StandardCharsets.UTF_8);
~~~

Cùng quy tắc áp dụng cho hàng đợi thông điệp, đối tượng lưu trong blob storage, cache dạng byte, socket tự xây và giao thức nhị phân có trường văn bản.

## 5. HTTP: đồng bộ byte thật, `Content-Type` và bộ đọc phản hồi

### 5.1. Gửi body text bằng `java.net.http.HttpClient`

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.invalid/echo"))
    .header("Content-Type", "text/plain; charset=UTF-8")
    .POST(HttpRequest.BodyPublishers.ofString(
            text, StandardCharsets.UTF_8))
    .build();
~~~

Đây là **đoạn minh họa tạo request**, không tự gọi mạng và không phải chương trình đầy đủ; cần `import java.net.URI;`, `import java.net.http.HttpRequest;` và biến `text`. `example.invalid` là địa chỉ ví dụ, không phải endpoint hoạt động.

- `BodyPublishers.ofString(text, StandardCharsets.UTF_8)` chuyển chuỗi thành byte UTF-8 để gửi.
- Header `Content-Type: text/plain; charset=UTF-8` **thông báo** định dạng và charset của body cho hệ thống nhận.
- **Cả hai phải thống nhất**. Đặt header UTF-8 nhưng encode bằng charset khác, hoặc ngược lại, là lỗi giao tiếp.
- `BodyPublishers.ofString(text)` không truyền `Charset` cũng được đặc tả dùng UTF-8; overload có charset làm ý định tường minh.
- Không tự gán `Content-Length` bằng `String.length()`. `HttpClient` quản lý truyền tải body và độ dài byte; `BodyPublisher.contentLength()` cung cấp số byte dự kiến nếu biết.

### 5.2. Nhận phản hồi đúng charset

Khi **hợp đồng của API yêu cầu UTF-8**, có thể yêu cầu bộ đọc giải mã bằng UTF-8:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
String responseText = response.body();
~~~

Đây là **mã minh họa**, trong đó `client` là `HttpClient` đã tạo; ví dụ không thực hiện kết nối thật. Đừng tự động áp đặt UTF-8 nếu API bên ngoài công bố charset khác và định dạng cho phép charset đó.

`HttpResponse.BodyHandlers.ofString()` **không có tham số** dùng charset từ `Content-Type` của phản hồi nếu có và được hỗ trợ; nếu không có/không hỗ trợ, nó dùng UTF-8. Khi dùng overload `ofString(StandardCharsets.UTF_8)`, ta chủ động buộc giải mã UTF-8 theo hợp đồng của hệ thống. Nếu cần kiểm soát nghiêm ngặt byte đầu vào hoặc tự kiểm tra header, nhận `BodyHandlers.ofByteArray()` rồi validate/decode bằng `CharsetDecoder`.

**Phân biệt:**

- `Content-Type` và tham số `charset`: nói body thuộc loại nội dung nào và được mã hóa ký tự ra sao, nếu media type sử dụng tham số đó.
- `Content-Encoding` (chẳng hạn gzip): mô tả mã hóa nội dung ở tầng nén/biểu diễn, **khác với charset**. Dữ liệu phải được xử lý theo đúng thứ tự của protocol.
- Một số media type như JSON có quy tắc charset riêng; không gắn `charset` bừa bãi hoặc bỏ qua tiêu chuẩn của định dạng. Với JSON truyền giữa các hệ thống hiện đại, UTF-8 là lựa chọn chuẩn theo RFC 8259.

## 6. Phát hiện UTF-8 không hợp lệ thay vì vô tình thay ký tự

Không phải mọi dãy byte đều hợp lệ theo UTF-8. Một số cách chuyển byte thành `String` có thể thay byte lỗi bằng ký tự thay thế `U+FFFD` (ký tự `�`), giúp ứng dụng tiếp tục chạy nhưng có nguy cơ **mất thông tin mà không được báo lỗi**:

~~~java
byte[] malformed = {(byte) 0xC3, (byte) 0x28};
String replaced = new String(malformed, StandardCharsets.UTF_8);
boolean wasReplaced = replaced.contains("\uFFFD"); // true
~~~

Nếu văn bản là thông tin cần toàn vẹn (mã định danh, chữ ký, tệp cấu hình, giao dịch, dữ liệu cần lưu trữ chính xác), dùng bộ giải mã ở chế độ **REPORT**:

~~~java
String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(malformed))
        .toString();
~~~

Đoạn sau phải đặt trong ngữ cảnh `try/catch (CharacterCodingException)` hoặc khai báo `throws`. Với dãy byte cố tình lỗi ở trên, `decode` sẽ **ném `CharacterCodingException`** (hoặc lớp con), để ứng dụng từ chối dữ liệu hay trả phản hồi lỗi rõ ràng. Các lớp `CharsetDecoder`, `CodingErrorAction` và `ByteBuffer` nằm trong `java.nio.charset` / `java.nio`.

Các API tiện ích không phải lúc nào cũng có cùng quy tắc xử lý dữ liệu hỏng: `Files.readString(path, charset)` báo `IOException` khi byte không thể decode theo charset; còn `new String(bytes, charset)` thường thay byte sai bằng `U+FFFD`. Chọn hành vi lỗi **có chủ đích**, không xem việc API trả về `String` là bằng chứng dữ liệu luôn hợp lệ.

Nếu văn bản có **BOM** hoặc metadata về encoding, xử lý theo đặc tả của định dạng. Không tự động giả định mọi tệp UTF-8 đều có BOM hay mọi decoder đều tự xóa BOM. BOM, charset và Unicode normalization là các khái niệm riêng.

## 7. Chương trình Java 15+/17+ hoàn chỉnh và kết quả chính xác

Lưu tệp với tên **`ExplicitEncodingDemo.java`** và encoding **UTF-8**. Chương trình:

1. Tạo văn bản chứa tiếng Việt và emoji; so sánh `String.length()` với số byte.
2. Encode/decode bằng UTF-8 và thử decode sai bằng ISO-8859-1.
3. Ghi/đọc một tệp tạm, xóa tệp trong `finally`.
4. Mô phỏng hai phía truyền/nhận byte bằng stream **trong bộ nhớ** (không mở socket, không gọi Internet).
5. Tạo một HTTP request object để xác minh header và số byte body (**không gửi request**).
6. Thử UTF-8 lỗi với decoder nghiêm ngặt.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.StringWriter;
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExplicitEncodingDemo {
    public static void main(String[] args) throws Exception {
        String text = "Chào 🌍";
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        boolean bytesOK = text.equals(new String(bytes, StandardCharsets.UTF_8));

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));
        System.out.println("utf8Bytes=" + bytes.length);
        System.out.println("bytesRoundTrip=" + bytesOK);
        System.out.println("wrongCharsetMatches=" +
                text.equals(new String(bytes, StandardCharsets.ISO_8859_1)));

        Path file = Files.createTempFile("utf8-example-", ".txt");
        boolean fileOK;
        try {
            Files.writeString(file, text, StandardCharsets.UTF_8);
            fileOK = text.equals(Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("fileSizeBytes=" + Files.size(file));
            System.out.println("fileRoundTrip=" + fileOK);
        } finally {
            Files.deleteIfExists(file);
        }

        ByteArrayOutputStream networkBuffer = new ByteArrayOutputStream();
        try (OutputStreamWriter writer = new OutputStreamWriter(
                networkBuffer, StandardCharsets.UTF_8)) {
            writer.write(text);
        }
        byte[] wireBytes = networkBuffer.toByteArray();
        StringWriter received = new StringWriter();
        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(wireBytes), StandardCharsets.UTF_8)) {
            reader.transferTo(received);
        }
        boolean networkOK = text.equals(received.toString());
        System.out.println("wireBytes=" + wireBytes.length);
        System.out.println("networkRoundTrip=" + networkOK);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("https://example.invalid/echo"))
                .header("Content-Type", "text/plain; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        text, StandardCharsets.UTF_8))
                .build();
        String mediaType = request.headers()
                .firstValue("Content-Type").orElse("");
        long httpLength = request.bodyPublisher()
                .orElseThrow().contentLength();
        System.out.println("httpContentType=" + mediaType);
        System.out.println("httpBodyBytes=" + httpLength);

        byte[] malformed = {(byte) 0xC3, (byte) 0x28};
        boolean rejected = false;
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformed));
            System.out.println("invalidUtf8=unexpected");
        } catch (CharacterCodingException expected) {
            rejected = true;
            System.out.println("invalidUtf8=rejected");
        }
        boolean replacementUsed = new String(malformed, StandardCharsets.UTF_8)
                .contains("\uFFFD");
        System.out.println("replacementUsed=" + replacementUsed);

        System.out.println("checks=" + (
                text.length() == 7
                && text.codePointCount(0, text.length()) == 6
                && bytes.length == 10
                && bytesOK && fileOK && networkOK
                && wireBytes.length == bytes.length
                && mediaType.equals("text/plain; charset=UTF-8")
                && httpLength == bytes.length
                && rejected && replacementUsed));
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 ExplicitEncodingDemo.java
java ExplicitEncodingDemo
~~~

Chương trình cũng biên dịch thành công với `--release 15`, vì các API này đã có từ Java 15 trở về trước. Kết quả thực tế kiểm chứng bằng JDK 24:

~~~text
utf16Units=7
codePoints=6
utf8Bytes=10
bytesRoundTrip=true
wrongCharsetMatches=false
fileSizeBytes=10
fileRoundTrip=true
wireBytes=10
networkRoundTrip=true
httpContentType=text/plain; charset=UTF-8
httpBodyBytes=10
invalidUtf8=rejected
replacementUsed=true
checks=true
~~~

Điểm cần nhớ từ kết quả: `utf16Units=7` khác `utf8Bytes=10`; tệp và HTTP body có **10 byte**. Encoding thống nhất cho kết quả round-trip đúng; decode sai charset cho kết quả không bằng văn bản gốc; decoder strict phát hiện UTF-8 không hợp lệ.

## 8. Checklist cho dự án thực tế

| Điểm giao tiếp | Quy tắc nên áp dụng | Lỗi cần tránh |
| --- | --- | --- |
| Ghi tệp text | `Files.writeString(path, text, UTF_8)` hoặc writer có charset | Dựa vào charset mặc định của API có thể khác theo runtime |
| Đọc tệp text | `Files.readString(path, UTF_8)` / `newBufferedReader(path, UTF_8)` | Dùng sai charset, không xử lý byte lỗi |
| Chuyển text sang byte | `text.getBytes(UTF_8)` | `getBytes()` không khai báo charset ở ranh giới giao tiếp |
| Chuyển byte sang text | `new String(bytes, UTF_8)` hoặc decoder `REPORT` | Mặc nhiên tin byte luôn hợp lệ |
| Stream/socket văn bản | `InputStreamReader` / `OutputStreamWriter` với `UTF_8` | Chỉ định charset một chiều, bỏ qua framing |
| HTTP request text | `BodyPublishers.ofString(text, UTF_8)` và `Content-Type` phù hợp | Header nói UTF-8 nhưng byte gửi lại encode khác |
| HTTP response text | Xác định charset từ hợp đồng/header, chọn `BodyHandlers` phù hợp | Decode cố định trái với hợp đồng; bỏ qua xử lý dữ liệu sai |
| Kích thước body | Đếm `bytes.length`, không dùng `String.length()` | Sai độ dài đối với chữ có dấu và emoji |
| Biên dịch `.java` | Dùng `javac -encoding UTF-8` khi cần minh bạch encoding nguồn | Nhầm charset của mã nguồn với charset dữ liệu runtime |

Các tình huống đặc biệt: không thể thay UTF-8 vào một giao thức yêu cầu UTF-16/ISO-8859-1; không encode file nhị phân như thể đó là text; không giải quyết dữ liệu Unicode bị chuẩn hóa khác nhau (`NFC/NFD`) chỉ bằng việc thống nhất UTF-8. **Charset mô tả cách ký tự thành byte, không tự chuẩn hóa các ký tự Unicode.**

### Ba lỗi cần nhớ nhất

1. **Bỏ tham số charset rồi chạy ở các máy khác nhau:** Java mới có nhiều mặc định UTF-8, nhưng hợp đồng trao đổi dữ liệu nên độc lập runtime.
2. **Đếm ký tự thay vì byte:** kích thước tệp, độ dài frame và dữ liệu truyền tải mạng là byte; Unicode và UTF-16 không đảm bảo tương đương.
3. **Chỉ ghi rõ UTF-8 phía gửi:** bên nhận cũng phải dùng cùng chuẩn, và hệ thống cần phát hiện dữ liệu không hợp lệ nếu nghiệp vụ yêu cầu chính xác.

## Tài liệu chính thức

- Java SE 25 API: `StandardCharsets` — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html
- Java SE 25 API: `Files`, các overload `readString`/`writeString` — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html
- Java SE 25 API: `HttpRequest.BodyPublishers` / `HttpResponse.BodyHandlers` — https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- OpenJDK, JEP 400 *UTF-8 by Default* (Java 18): https://openjdk.org/jeps/400
- IETF RFC 9110, HTTP `Content-Type` và `charset`: https://www.rfc-editor.org/rfc/rfc9110#section-8.3
- IETF RFC 8259, JSON và mã hóa ký tự: https://www.rfc-editor.org/rfc/rfc8259#section-8.1