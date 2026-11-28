# Lập bản đồ ranh giới byte và ký tự trong tệp, tài nguyên classpath, tiến trình con và phản hồi HTTP

## 1. Mục tiêu và phạm vi

Trong module **JAVA_VERSION_JAVA18**, Java 18 đánh dấu một thay đổi quan trọng: theo [JEP 400](https://openjdk.org/jeps/400), **UTF-8 trở thành charset mặc định của các API Java thông dụng**. Thay đổi này giúp chương trình chạy nhất quán hơn giữa các hệ điều hành, nhưng không có nghĩa mọi byte mà ứng dụng nhận được đều là UTF-8.

Bài này thuộc chương **Kiểm chứng mã hóa**. Sau khi học, bạn có thể:

- Chỉ ra chính xác vị trí ứng dụng **mã hóa** (`String → byte[]`) và **giải mã** (`byte[] → String`) khi làm việc với tệp, tài nguyên classpath, tiến trình con và HTTP.
- Phân biệt charset mặc định của JVM với charset do **định dạng dữ liệu, giao thức hoặc chương trình bên ngoài** quy định.
- Dùng API có charset tường minh, đối chiếu byte thực tế, phát hiện chuỗi UTF-8 không hợp lệ và kiểm thử tính nhất quán qua các ranh giới.

> Nguyên tắc xuyên suốt: **Mỗi lần dữ liệu đi qua ranh giới giữa byte và ký tự, phải biết charset do bên nào quy định.** Khi đã có hợp đồng UTF-8, hãy ghi rõ `StandardCharsets.UTF_8` tại điểm chuyển đổi; đừng dựa vào cấu hình máy chạy.

## 2. Vẽ đúng bản đồ trước khi viết mã

`String` của Java biểu diễn văn bản bằng các đơn vị mã UTF-16. Byte từ đĩa, JAR, pipe hay mạng **chưa phải** là ký tự Java. Chuyển đổi hai chiều phải xảy ra tại vị trí xác định:

```text
                    ENCODE (bên phát)                         DECODE (bên nhận)
Java String ── getBytes(UTF_8) ──> byte[] ── tệp / JAR / pipe / HTTP ──> byte[]
     ^                                                                  │
     └──────────────────── new String(bytes, UTF_8) ─────────────────────┘
```

Sơ đồ trên chỉ đúng khi **hợp đồng dữ liệu là UTF-8**. Nếu đầu phát thực tế dùng charset khác, việc đầu nhận giải mã bằng UTF-8 sẽ sai, dù `Charset.defaultCharset()` trả về UTF-8.

| Ranh giới | Byte nằm ở đâu? | Ai xác định charset văn bản? | Điểm chuyển đổi nên thể hiện trong mã |
| --- | --- | --- | --- |
| Tệp | Nội dung trên hệ thống tệp | Định dạng tệp/hợp đồng với bên tạo tệp | `Files.readString(path, UTF_8)`, `Files.writeString(path, text, UTF_8)` |
| Tài nguyên classpath | Entry trong thư mục classpath hoặc JAR | Định dạng của tài nguyên, không phải class loader | `getResourceAsStream()` rồi `InputStreamReader(..., UTF_8)` |
| Tiến trình con | Pipe `stdin`, `stdout`, `stderr` | Chương trình con và cấu hình của nó | `getInputStream()`/`getErrorStream()` rồi giải mã theo hợp đồng |
| HTTP | Byte của phần thân yêu cầu/phản hồi | Chuẩn định dạng và metadata giao thức, thường là `Content-Type` | `BodyHandlers.ofByteArray()` + giải mã, hoặc `BodyHandlers.ofString(charset)` |

### Ba con số không được đánh đồng

```java
import java.nio.charset.StandardCharsets;

String s = "Việt 🚀";
System.out.println(s.length());                            // 7 đơn vị mã UTF-16
System.out.println(s.codePointCount(0, s.length()));       // 6 code point Unicode
System.out.println(s.getBytes(StandardCharsets.UTF_8).length); // 11 byte UTF-8
```

Ký tự `ệ` chiếm **ba byte UTF-8**, còn `🚀` chiếm **bốn byte UTF-8 nhưng hai đơn vị mã UTF-16**. Vì thế không dùng `String.length()` để tính `Content-Length` hay kiểm tra kích thước tệp.

### Java 18 thay đổi điều gì, và không thay đổi điều gì?

Từ Java 18, charset mặc định được chuẩn hóa thành UTF-8 cho các API chịu ảnh hưởng của JEP 400, chẳng hạn constructor `InputStreamReader(InputStream)` và `FileReader` không nhận charset. Dù vậy, **mã có charset tường minh vẫn rõ hợp đồng và kiểm chứng dễ hơn**.

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

System.out.println(Charset.defaultCharset()); // Thông thường: UTF-8 trên JDK 18+
System.out.println(StandardCharsets.UTF_8);  // Charset của hợp đồng dữ liệu
```

Đừng suy ra rằng thay đổi này tự động áp dụng cho mọi tình huống: nội dung file cũ có thể dùng charset khác; tên tệp và tham số tiến trình có quy tắc từ hệ điều hành; `System.out`/`System.err` và console có cơ chế mã hóa riêng; pipe của chương trình ngoài và HTTP tuân theo hợp đồng của phía phát. `-Dfile.encoding=COMPAT` tồn tại cho tương thích khi chạy ứng dụng cũ, **không phải cách thiết kế một định dạng dữ liệu mới**.

## 3. Ranh giới 1 — Đọc và ghi tệp

Với tệp văn bản do ứng dụng kiểm soát, hãy chọn UTF-8 và giữ lựa chọn đó ở **cả hai chiều**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("note.txt");
String original = "Việt 🚀";

Files.writeString(file, original, StandardCharsets.UTF_8);
String restored = Files.readString(file, StandardCharsets.UTF_8);
if (!original.equals(restored)) {
    throw new IllegalStateException("Nội dung sau khi đọc khác nội dung đã ghi");
}

byte[] actualBytes = Files.readAllBytes(file);
System.out.println(actualBytes.length); // 11 byte, không phải 7
```

`Files.readString(Path)` và `Files.writeString(Path, CharSequence)` đã có **ngữ nghĩa UTF-8 cố định** từ khi xuất hiện (Java 11); bản overload nhận `Charset` cho phép ghi rõ lựa chọn. Trái lại, các API sử dụng charset mặc định phụ thuộc phiên bản JDK và cấu hình tương thích. Khi làm việc với tệp **nhị phân**, giữ nguyên `byte[]` và dùng `Files.readAllBytes`/`Files.write`; không ép qua `String`.

Nếu dùng stream, đặt điểm giải mã ngay tại lớp chuyển đổi:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (var input = Files.newInputStream(Path.of("note.txt"));
     var reader = new BufferedReader(
             new InputStreamReader(input, StandardCharsets.UTF_8))) {
    System.out.println(reader.readLine());
}
```

**Kiểm chứng:** lưu cùng một chuỗi chứa tiếng Việt và ký tự ngoài BMP, đối chiếu `Files.readAllBytes(file)` với `original.getBytes(UTF_8)`. Nếu hai mảng byte khác nhau, cần kiểm tra việc thêm BOM, đổi dòng (`\n`/`\r\n`), chuyển đổi charset hoặc xử lý nội dung ở một lớp trung gian. So sánh chuỗi sau khi đọc là cần thiết nhưng chưa đủ để chứng minh byte đã được bảo toàn.

## 4. Ranh giới 2 — Tài nguyên classpath, kể cả trong JAR

`Class.getResourceAsStream` trả về **luồng byte**; class loader không tự chuyển các byte của tài nguyên thành Unicode. Cùng một lời gọi có thể đọc entry trong thư mục khi phát triển hoặc trong JAR khi triển khai.

Giả sử có tài nguyên UTF-8 `src/main/resources/messages/welcome.txt`, ví dụ sau dùng đường dẫn bắt đầu bằng `/` để tìm từ gốc classpath:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

try (InputStream in = Objects.requireNonNull(
        Example.class.getResourceAsStream("/messages/welcome.txt"),
        "Thiếu tài nguyên /messages/welcome.txt")) {
    byte[] raw = in.readAllBytes();
    String welcome = new String(raw, StandardCharsets.UTF_8);
    System.out.println(welcome);
}
```

Trong ví dụ, `Example` là class chứa đoạn mã; tài nguyên phải thực sự được đóng gói trên classpath khi chạy. **Không chuyển URL classpath thành `Path` rồi giả định đó luôn là tệp thông thường**: tài nguyên bên trong JAR có thể không có đường dẫn hệ thống tệp tương ứng. Dùng `getResourceAsStream` để mã hoạt động ở cả hai cách đóng gói.

Một trường hợp dễ nhầm là `.properties`:

| API | Quy tắc giải mã liên quan |
| --- | --- |
| `Properties.load(InputStream)` | Diễn giải byte theo ISO-8859-1, cho phép escape `\uXXXX`; **không** tự dùng charset mặc định UTF-8 của Java 18. |
| `Properties.load(Reader)` | Dùng ký tự do `Reader` đã giải mã; truyền `InputStreamReader(in, UTF_8)` nếu file `.properties` theo UTF-8. |
| `ResourceBundle` nạp `.properties` theo cơ chế tiêu chuẩn hiện đại | Mặc định thử UTF-8 và có cơ chế tương thích riêng đối với byte không hợp lệ; không đánh đồng với `Properties.load(InputStream)`. |

Ví dụ để giữ hợp đồng UTF-8 cho `Properties`:

```java
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.Properties;

Properties properties = new Properties();
try (var input = Objects.requireNonNull(
             Example.class.getResourceAsStream("/messages/app.properties"));
     var reader = new InputStreamReader(input, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
System.out.println(properties.getProperty("greeting"));
```

**Kiểm chứng:** đọc byte của tài nguyên đã đóng gói và so với byte nguồn lúc build; chạy cùng phép đọc cả khi dùng thư mục classpath lẫn khi dùng JAR. Nếu dữ liệu là ảnh, chứng chỉ, ZIP hoặc định dạng nhị phân, giữ luồng byte nguyên trạng; không dùng `Reader`.

## 5. Ranh giới 3 — `stdin`, `stdout`, `stderr` của tiến trình con

`ProcessBuilder` kết nối chương trình Java với tiến trình con bằng **các pipe byte**. Java 18 mặc định UTF-8 không buộc một executable bên ngoài phải phát UTF-8. Công cụ đó có thể dùng UTF-8, mã hóa theo locale, một giao thức nhị phân hoặc lựa chọn dòng lệnh riêng.

Ví dụ có hợp đồng rõ ràng giữa **hai chương trình Java**: `ChildPrinter` tự xuất byte UTF-8 thay vì dựa vào charset mặc định của `System.out`.

```java
// ChildPrinter.java
import java.nio.charset.StandardCharsets;

public class ChildPrinter {
    public static void main(String[] args) throws Exception {
        byte[] message = "Việt 🚀\n".getBytes(StandardCharsets.UTF_8);
        System.out.write(message);
        System.out.flush();
    }
}
```

Chương trình cha giải mã `stdout` bằng chính charset đã thống nhất:

```java
// ParentReader.java — biên dịch cùng ChildPrinter.java và chạy từ classpath chứa cả hai
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class ParentReader {
    public static void main(String[] args) throws Exception {
        String executable = System.getProperty("os.name").startsWith("Windows")
                ? "java.exe" : "java";
        String java = Path.of(System.getProperty("java.home"), "bin", executable).toString();

        Process child = new ProcessBuilder(
                java, "-cp", System.getProperty("java.class.path"), "ChildPrinter")
                .redirectError(ProcessBuilder.Redirect.INHERIT)
                .start();

        byte[] raw;
        try (InputStream stdout = child.getInputStream()) {
            raw = stdout.readAllBytes();
        }
        int exitCode = child.waitFor();
        if (exitCode != 0) throw new IllegalStateException("Child exit=" + exitCode);
        System.out.println(new String(raw, StandardCharsets.UTF_8));
    }
}
```

Ở đây cha đọc một pipe trong khi `stderr` được chuyển trực tiếp ra môi trường chạy. Với chương trình có **cả `stdout` và `stderr` được nối pipe**, cần tiêu thụ đồng thời hai luồng (hoặc cấu hình redirect phù hợp), vì pipe đầy có thể khiến tiến trình treo. `getOutputStream()` của `Process` là byte gửi **vào `stdin` của con**; muốn gửi văn bản thì mã hóa theo charset **đầu vào** mà con chấp nhận, không mặc định giống charset đầu ra.

Với công cụ bên ngoài, trước hết tìm hợp đồng thực sự (tùy chọn `--encoding`, tài liệu API, biến môi trường/locale, hoặc quy định giao thức). Cấu hình `-Dfile.encoding=UTF-8` ở **JVM cha** không thay đổi cách một executable khác mã hóa đầu ra. Nếu đầu ra là nhị phân hoặc pha trộn nhị phân với text, đọc dữ liệu theo định dạng byte của công cụ đó.

## 6. Ranh giới 4 — Phần thân phản hồi HTTP

HTTP chuyển phần thân dưới dạng byte. Charset văn bản phụ thuộc vào media type và quy ước của endpoint, thường được diễn đạt bằng `Content-Type`, chẳng hạn `text/plain; charset=utf-8`. Charset không được suy ra chỉ từ mặc định JVM của client.

Ví dụ handler trên máy chủ Java (API `com.sun.net.httpserver.HttpServer` thuộc module JDK `jdk.httpserver`):

```java
// Bên trong HttpHandler.handle(HttpExchange exchange)
import java.nio.charset.StandardCharsets;

byte[] payload = "Việt 🚀".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, payload.length); // Kích thước BYTE của body
try (var out = exchange.getResponseBody()) {
    out.write(payload);
}
```

Đoạn handler là phần thân phương thức minh họa; khi tạo server hoàn chỉnh, cần cấu hình địa chỉ, context và vòng đời máy chủ. Với `payload` ở trên, kích thước gửi đi là **11 byte**, không phải `"Việt 🚀".length()`.

Ở client, một cách dễ kiểm chứng là giữ byte thô trước khi giải mã:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("http://127.0.0.1:8080/message")).GET().build();

HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());
if (response.statusCode() != 200) {
    throw new IllegalStateException("HTTP " + response.statusCode());
}
byte[] body = response.body();
String text = new String(body, StandardCharsets.UTF_8); // Endpoint cam kết UTF-8
System.out.println(text);
```

Endpoint `/message` và cổng `8080` ở đây là giá trị ví dụ: client cần khớp với server thực tế. Khi đã biết chắc phản hồi là UTF-8, có thể thay bằng `HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)` để client tự giải mã. `BodyHandlers.ofString()` không truyền charset có quy tắc chọn charset từ `Content-Type` và dùng UTF-8 khi thiếu charset phù hợp; với hợp đồng biết trước, bản nhận `Charset` giúp tránh phụ thuộc metadata của peer.

Hai lưu ý khi kiểm chứng giao thức:

- Với JSON trao đổi trên mạng, quy ước hiện hành là **UTF-8** (xem [RFC 8259, mục 8.1](https://www.rfc-editor.org/rfc/rfc8259#section-8.1)); đặt `Content-Type: application/json` và phát byte UTF-8. Đừng để `String.getBytes()` không tham số quyết định định dạng của API.
- Nếu có nén `Content-Encoding: gzip`, phải giải nén nội dung trước khi giải mã thành ký tự; nếu phản hồi là ảnh hoặc file tải xuống, giữ dạng byte. `Content-Length` nếu được khai báo biểu diễn số **octet của body truyền qua HTTP**, không phải số ký tự Java.

## 7. Kiểm chứng byte bằng bộ giải mã nghiêm ngặt

`new String(bytes, UTF_8)` thuận tiện để hiển thị nhưng thường **thay thế** chuỗi byte UTF-8 lỗi bằng ký tự thay thế `�` (U+FFFD), làm mất chứng cứ rằng dữ liệu gốc không hợp lệ. Khi xác nhận ranh giới, dùng `CharsetDecoder` ở chế độ `REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes) throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

Ví dụ `decodeUtf8Strict(new byte[] {(byte) 0xC3, 0x28})` ném `MalformedInputException` vì `0xC3` không được theo sau bằng byte tiếp nối hợp lệ. Lỗi này chỉ chứng minh byte **không phải UTF-8 hợp lệ**, chưa đủ để kết luận charset gốc là gì.

Phép kiểm tra round-trip giúp phát hiện việc dữ liệu bị thay đổi ngoài ý muốn:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

byte[] raw = "Việt 🚀".getBytes(StandardCharsets.UTF_8);
String decoded = decodeUtf8Strict(raw);
byte[] encodedAgain = decoded.getBytes(StandardCharsets.UTF_8);
if (!Arrays.equals(raw, encodedAgain)) {
    throw new AssertionError("Ranh giới byte/ký tự đã thay đổi dữ liệu");
}
```

Phép round-trip đảm bảo byte UTF-8 hợp lệ được giải mã rồi mã hóa lại nhất quán; nó **không chứng minh** văn bản có đúng ý nghĩa hay charset gốc của một tệp không có hợp đồng. Chẳng hạn byte ASCII có thể hợp lệ dưới nhiều charset. Byte order mark (BOM), chuẩn hóa Unicode và quy ước xuống dòng là các quyết định độc lập: cần kiểm tra chúng riêng nếu định dạng dữ liệu yêu cầu.

## 8. Bảng kiểm tra nhanh cho bốn ranh giới

| Tình huống kiểm thử | Bằng chứng cần lấy | Điều kiện đạt |
| --- | --- | --- |
| Tệp chứa `Việt 🚀` | Byte thực tế từ `Files.readAllBytes` | Khớp `text.getBytes(UTF_8)`; dữ liệu đọc lại đúng |
| Tài nguyên được đóng vào JAR | Byte từ `getResourceAsStream` | Khớp tài nguyên UTF-8 nguồn; không phụ thuộc việc chạy trong JAR |
| Con in `stdout` và `stderr` | Byte của từng pipe, cấu hình charset của con | Cha giải mã đúng charset mà con thực sự phát; không có pipe bị bỏ quên gây treo |
| Server trả `text/plain` | `Content-Type`, byte body, kích thước body | Header khớp encoding thực, giải mã đúng; không dùng độ dài `String` làm độ dài byte |
| Dữ liệu UTF-8 hỏng | Kết quả từ `decodeUtf8Strict` | Báo lỗi ở biên nhận thay vì âm thầm thay bằng `�` |

### Bài thực hành tự kiểm chứng

1. Ghi `Việt 🚀` ra tệp bằng UTF-8; ghi lại `String.length()`, số code point và số byte. Đọc tệp bằng `Files.readString(path, UTF_8)` và so byte gốc.
2. Đưa cùng chuỗi vào `messages/welcome.txt`, chạy đọc tài nguyên từ thư mục classpath và từ JAR. Xác minh nội dung và số byte giống nhau.
3. Biên dịch `ChildPrinter` và `ParentReader`; đổi chương trình con để xuất một mảng byte UTF-8 không hợp lệ và quan sát khác biệt giữa `new String` với `decodeUtf8Strict` ở cha.
4. Tạo một HTTP endpoint trả UTF-8 với header đúng; dùng `ofByteArray()` xem byte thô, sau đó thử `ofString(UTF_8)`. Đối chiếu số byte gửi đi với `String.length()`; thử phát byte không khớp `charset` trong header và xác định lớp gây sai lệch.

**Tiêu chí hoàn thành:** với bất kỳ điểm đọc/ghi nào trong bốn ranh giới, bạn trả lời được ba câu hỏi: **byte đến từ đâu**, **ai cam kết charset**, và **dòng mã nào thực hiện encode/decode**. Đó là cách áp dụng thay đổi UTF-8 mặc định của Java 18 một cách kiểm chứng được trên JDK hiện đại.
