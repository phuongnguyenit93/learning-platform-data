# BodyHandlers.ofString và giải mã charset của HTTP Response trong Java 11

## Mục tiêu

Một HTTP response chứa **bytes**, còn một chương trình Java xử lý văn bản bằng **`String`** (UTF-16). Để chuyển bytes thành chữ tiếng Việt, JSON, HTML hoặc văn bản theo charset khác, HTTP Client phải **chọn đúng character encoding**. Nếu chọn sai, phản hồi vẫn có status 200 nhưng nội dung có thể thành chuỗi lỗi dấu (*mojibake*), chứa ký tự thay thế `U+FFFD` hoặc không khớp dữ liệu gốc.

Java 11 cung cấp hai factory method thuộc `java.net.http.HttpResponse.BodyHandlers`:

- **`BodyHandlers.ofString()`:** để handler chọn charset dựa trên **`Content-Type` của HTTP response**, mặc định UTF-8 khi không có charset được hỗ trợ.
- **`BodyHandlers.ofString(Charset charset)`:** dùng **charset do ứng dụng chỉ định** để giải mã, không phụ thuộc giá trị charset được khai báo trong response.

Sau bài học bạn sẽ có thể:

1. Chọn overload phù hợp với hợp đồng API/server và giải thích chính xác đường đi **bytes → charset → `String`**.
2. Phân biệt `Content-Type`/`charset` với `Accept`, `Content-Encoding`, kiểu Java `String` và charset nguồn của request.
3. Kiểm thử UTF-8 với tiếng Việt và ký tự bổ sung, ISO-8859-1, UTF-16LE, thiếu header, charset không được hỗ trợ và header khai sai.
4. Hiểu hành vi đối với body rỗng, BOM UTF-8, byte UTF-8 không hợp lệ và HTTP 404.
5. Dùng `BodyHandlers.ofByteArray()` cùng `CharsetDecoder` khi muốn **kiểm chứng bytes và từ chối dữ liệu lỗi**, thay vì chấp nhận ký tự thay thế.
6. Áp dụng cho cả `HttpClient.send` và `sendAsync`, tránh các API incubator/legacy không thuộc Java 11.

Nội dung dựa trên Javadoc Java SE 11 và các phiên bản JDK hiện hành; `BodyHandlers.ofString` là API công khai được hỗ trợ, không phải cơ chế đã lỗi thời.

## 1. HTTP response từ bytes đến Java String

### 1.1. Bytes, charset và String không đồng nhất

Một HTTP response có thể gồm:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Length: 5

Hello
~~~

Header `Content-Type` mô tả **kiểu media** (ở đây `text/plain`) và có thể bao gồm tham số `charset` cho phần body. HTTP Client nhận bytes của body; muốn nhận `String` đúng, phải giải mã bytes theo charset phù hợp.

Ví dụ từ các bytes thực tế:

| Nội dung mong muốn | Bytes | Charset đúng | Kết quả |
| --- | --- | --- | --- |
| `A` | `41` | UTF-8 hoặc ISO-8859-1 | `"A"` |
| `é` | `C3 A9` | UTF-8 | `"é"` |
| `é` | `E9` | ISO-8859-1 | `"é"` |
| `ắ` | `E1 BA AF` | UTF-8 | `"ắ"` |
| `🙂` (U+1F642) | `F0 9F 99 82` | UTF-8 | Một Unicode code point, hai UTF-16 code units |

Cùng một chữ **é** nhưng có cách mã hóa khác nhau. Nếu server gửi bytes `E9` theo ISO-8859-1 mà client đọc bằng UTF-8, byte đó không tạo một chuỗi UTF-8 hợp lệ đầy đủ. Ngược lại, nếu bytes UTF-8 của tiếng Việt bị đọc như ISO-8859-1, kết quả có thể là các chữ lạ dù mạng và HTTP đều hoạt động bình thường.

**Không dùng `String.length()` để suy ra số bytes đã truyền.** `String.length()` đo UTF-16 code units; kích thước UTF-8 được xác định bằng `string.getBytes(StandardCharsets.UTF_8).length`. Một code point supplementary cần hai `char` trong Java nhưng thường là bốn bytes UTF-8.

### 1.2. `BodyHandler<String>` và `BodySubscriber<String>`

`HttpResponse.BodyHandlers.ofString(...)` tạo **`HttpResponse.BodyHandler<String>`**. Handler được HTTP Client sử dụng khi các header của response đã có để lựa chọn một `BodySubscriber<String>`; subscriber tiêu thụ bytes và hoàn thành kết quả ở dạng `String`.

~~~java
// Đoạn minh họa trong method có sẵn client/request.
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

String body = response.body();
int status = response.statusCode();
~~~

Kiểu `T` của response phụ thuộc handler:

| Handler phản hồi | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `HttpResponse<String>` | Giải mã text theo charset từ response/fallback. |
| `BodyHandlers.ofString(UTF_8)` | `HttpResponse<String>` | Giải mã text bằng UTF-8 được chỉ định. |
| `BodyHandlers.ofByteArray()` | `HttpResponse<byte[]>` | Giữ raw bytes, chưa giải mã thành text. |
| `BodyHandlers.ofInputStream()` | `HttpResponse<InputStream>` | Đọc body theo stream; caller chịu trách nhiệm tiêu thụ/đóng. |
| `BodyHandlers.ofFile(path)` | `HttpResponse<Path>` | Ghi bytes vào file thay vì giữ toàn bộ String trong heap. |

Với `ofString`, khi `HttpResponse<String>` được trả về từ `send` hoặc future hoàn tất thành công với `sendAsync`, toàn bộ response body đã được đọc và chuyển thành String. Không cần tự gọi `InputStream.read` cho handler này.

Các BodyHandler dựng sẵn **không tự từ chối một response chỉ vì status 404/500**: status phải do ứng dụng kiểm tra riêng.

## 2. Hai overload `ofString`: thứ tự ưu tiên charset

### 2.1. `BodyHandlers.ofString()` — theo response `Content-Type`

Chữ ký API:

~~~java
public static HttpResponse.BodyHandler<String> ofString()
~~~

Theo Javadoc Java 11: body được giải mã bằng charset khai báo trong **`Content-Type` của response**. Nếu **không có header này hoặc charset không được hỗ trợ**, handler dùng **`StandardCharsets.UTF_8`**.

Ví dụ nếu server gửi:

~~~http
Content-Type: text/plain; charset=ISO-8859-1
~~~

và body chứa byte `E9` thì:

~~~java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
// Nếu server gửi byte E9 và khai ISO-8859-1,
// body chứa đúng chữ "é".
~~~

Ngược lại, nếu server gửi:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

thì handler giải mã theo UTF-8. Nếu response không có `Content-Type`, test Java 11 sẽ dùng UTF-8 fallback; điều đó **không chứng minh server thật gửi UTF-8**. Nếu server thực sự gửi Latin-1 nhưng bỏ header, text vẫn có thể hỏng.

**Không tự suy ra `text/plain` luôn có charset mặc định giống mọi chuẩn HTTP hoặc quy ước riêng của một framework.** Đây là hợp đồng **cụ thể của Java `BodyHandlers.ofString()`**, không phải tuyên bố về mọi HTTP client.

### 2.2. `BodyHandlers.ofString(Charset)` — khóa một charset

Chữ ký API:

~~~java
public static HttpResponse.BodyHandler<String> ofString(
        Charset charset)
~~~

Ví dụ:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Với overload này, **charset được chỉ định được dùng để decode body**, kể cả khi response `Content-Type` ghi một charset khác.

Điều này hữu ích khi bạn có **hợp đồng đáng tin cậy** rằng endpoint luôn gửi UTF-8, nhưng server bỏ header hoặc khai không đúng. Tuy nhiên, nếu phía server thực sự dùng Latin-1, ép UTF-8 sẽ khiến nội dung bị lỗi.

Các charset chuẩn phổ biến trong Java 11:

- `StandardCharsets.UTF_8`: Unicode UTF-8, lựa chọn thường gặp cho JSON/text hiện đại.
- `StandardCharsets.ISO_8859_1`: ánh xạ single-byte Latin-1.
- `StandardCharsets.US_ASCII`: dữ liệu ASCII 7-bit.
- `StandardCharsets.UTF_16LE` / `UTF_16BE`: Unicode UTF-16 theo endian cụ thể.
- `StandardCharsets.UTF_16`: UTF-16 với cơ chế byte-order mark/fallback theo charset này.

Không tạo Charset bằng tên chuỗi không rõ nguồn nếu có sẵn hằng số trong `StandardCharsets`. Nếu cần hỗ trợ một giao thức bên ngoài quy định charset khác, kiểm tra `Charset.isSupported(...)` hoặc quản lý lỗi `UnsupportedCharsetException`, đồng thời kiểm thử với bytes thực.

### 2.3. Bảng quyết định nhanh

| Response body thực tế | Header `Content-Type` | Handler | Kết quả mong muốn |
| --- | --- | --- | --- |
| UTF-8 có tiếng Việt | `charset=UTF-8` | `ofString()` | Đúng |
| UTF-8 có tiếng Việt | Không có header | `ofString()` | Đúng nhờ fallback UTF-8 |
| UTF-8 có tiếng Việt | `charset=X-NOT-SUPPORTED` | `ofString()` | Đúng nhờ fallback UTF-8 |
| Latin-1 byte `E9` | `charset=ISO-8859-1` | `ofString()` | `é` |
| Latin-1 byte `E9` | `charset=ISO-8859-1` | `ofString(UTF_8)` | Sai/ví dụ xuất hiện `U+FFFD` |
| UTF-8 tiếng Việt | Server khai nhầm Latin-1 | `ofString()` | Mojibake do tin header |
| UTF-8 tiếng Việt | Server khai nhầm Latin-1 | `ofString(UTF_8)` | Đúng khi hợp đồng thực tế bảo đảm UTF-8 |
| UTF-16LE | `charset=UTF-16LE` | `ofString()` | Đúng |
| Bytes bất kỳ | Bất kỳ | `ofByteArray()` | Giữ nguyên bytes, tự giải mã theo quy tắc ứng dụng |

**Quan trọng:** trường hợp server **khai sai** charset là lỗi hợp đồng trao đổi dữ liệu. Đừng âm thầm «sửa» dựa trên một lần test rồi áp dụng toàn hệ thống; cần biết chính xác API, charset thực, ràng buộc và các trường hợp ngoại lệ.

## 3. `Content-Type`, `Content-Encoding` và các header khác

### 3.1. `Content-Type` không phải `Content-Encoding`

Một response có thể có:

~~~http
Content-Type: application/json; charset=UTF-8
Content-Encoding: gzip
~~~

- **`Content-Type`** cho biết **media type** và có thể chỉ ra **charset** của **văn bản sau khi đã giải mã content coding**.
- **`Content-Encoding`** mô tả một phép biến đổi representation như gzip, là vấn đề **nén/giải nén**, không phải bảng mã ký tự.
- **`Content-Length`** liên quan đến kích thước thông điệp theo framing, **không phải** số ký tự trong Java String.
- Header `Accept-Charset` (nếu ứng dụng dùng) diễn tả một số khả năng chấp nhận từ phía client, **không thay đổi bytes server đã gửi** và không buộc `ofString()` tự chọn charset khác với header response.

Không kỳ vọng thay `BodyHandlers.ofString(UTF_8)` là đủ để giải quyết payload bị nén mà client chưa được cấu hình/triển khai phần content coding phù hợp. Phân biệt **giải nén bytes** và **giải mã bytes thành text**.

### 3.2. `Content-Type` không tự làm JSON thành object

~~~java
HttpResponse<String> result =
        client.send(request, HttpResponse.BodyHandlers.ofString());
String jsonText = result.body();
~~~

Dù header là `application/json; charset=UTF-8`, `ofString` chỉ giải mã thành **String**, không parse JSON thành Map/record/domain object. JSON parsing là bước riêng, sử dụng parser phù hợp với hệ thống, kiểm tra schema và lỗi dữ liệu. Tương tự, `text/html` không tự được giải mã HTML entities; charset decoding và cú pháp nội dung là hai tầng khác nhau.

Nếu endpoint có thể trả HTML khi lỗi thay vì JSON khi thành công, phải kiểm tra **`statusCode()`** và **`Content-Type`** trước khi parse dữ liệu nghiệp vụ.

## 4. Ví dụ Java 11 chạy độc lập: server cục bộ và 10 nhóm kiểm thử

Chương trình sau không phụ thuộc API công khai ngoài Internet. Nó dùng:

- `java.net.http.HttpClient` của **Java 11** để gửi GET và nhận response.
- `com.sun.net.httpserver.HttpServer` của module JDK `jdk.httpserver` chỉ để **tạo server kiểm thử trên `127.0.0.1`**.
- Các charset được cung cấp bởi `StandardCharsets`.
- Các byte payload cố định để kiểm chứng trường hợp header đúng/sai, nội dung lỗi và quy tắc fallback.

Tạo file **BodyStringCharsetDemo.java** với toàn bộ nội dung:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class BodyStringCharsetDemo {
    private static final String VIETNAMESE =
            "Ti\u1EBFng Vi\u1EC7t "
            + new String(Character.toChars(0x1F642));

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static void reply(HttpExchange exchange, int status,
                              String contentType, byte[] data)
            throws IOException {
        if (contentType != null) {
            exchange.getResponseHeaders().set("Content-Type", contentType);
        }
        if (data.length == 0) {
            exchange.sendResponseHeaders(status, -1);
            exchange.close();
            return;
        }
        exchange.sendResponseHeaders(status, data.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(data);
        }
    }

    private static HttpRequest request(URI root, String path) {
        return HttpRequest.newBuilder(root.resolve(path))
                .timeout(Duration.ofSeconds(5))
                .GET().build();
    }

    private static HttpResponse<String> text(HttpClient client, URI root,
                                             String path,
                                             HttpResponse.BodyHandler<String> handler)
            throws Exception {
        return client.send(request(root, path), handler);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        server.setExecutor(executor);

        server.createContext("/utf8", ex ->
                reply(ex, 200, "text/plain; charset=UTF-8",
                      VIETNAMESE.getBytes(StandardCharsets.UTF_8)));
        server.createContext("/latin1", ex ->
                reply(ex, 200, "text/plain; charset=ISO-8859-1",
                      "caf\u00E9".getBytes(StandardCharsets.ISO_8859_1)));
        server.createContext("/no-header", ex ->
                reply(ex, 200, null,
                      VIETNAMESE.getBytes(StandardCharsets.UTF_8)));
        server.createContext("/unsupported", ex ->
                reply(ex, 200, "text/plain; charset=X-NOT-SUPPORTED",
                      VIETNAMESE.getBytes(StandardCharsets.UTF_8)));
        server.createContext("/wrong", ex ->
                reply(ex, 200, "text/plain; charset=ISO-8859-1",
                      VIETNAMESE.getBytes(StandardCharsets.UTF_8)));
        server.createContext("/utf16le", ex ->
                reply(ex, 200, "text/plain; charset=UTF-16LE",
                      "\u1EAF".getBytes(StandardCharsets.UTF_16LE)));
        server.createContext("/empty", ex ->
                reply(ex, 200, "text/plain; charset=UTF-8",
                      new byte[0]));
        server.createContext("/malformed", ex ->
                reply(ex, 200, "text/plain; charset=UTF-8",
                      new byte[] {(byte) 0xC3, (byte) 0x28}));
        server.createContext("/bom", ex ->
                reply(ex, 200, "text/plain; charset=UTF-8",
                      new byte[] {(byte) 0xEF, (byte) 0xBB,
                                  (byte) 0xBF, 65}));
        server.createContext("/not-found", ex ->
                reply(ex, 404, "text/plain; charset=UTF-8",
                      "kh\u00F4ng c\u00F3".getBytes(StandardCharsets.UTF_8)));

        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpResponse<String> utf8 = text(client, root, "/utf8",
                    HttpResponse.BodyHandlers.ofString());
            check(utf8.statusCode() == 200
                    && VIETNAMESE.equals(utf8.body()),
                    "UTF-8 declared header");
            check(utf8.headers().firstValue("Content-Type").isPresent(),
                    "Content-Type header available");
            System.out.println("PASS UTF-8 declared charset");

            HttpResponse<String> latin = text(client, root, "/latin1",
                    HttpResponse.BodyHandlers.ofString());
            check("caf\u00E9".equals(latin.body()), "Latin-1 declared header");
            String forcedWrong = text(client, root, "/latin1",
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)).body();
            check(!"caf\u00E9".equals(forcedWrong)
                    && forcedWrong.indexOf('\uFFFD') >= 0,
                    "fixed UTF-8 must not follow Latin-1 header");
            System.out.println("PASS declared Latin-1 versus fixed UTF-8");

            check(VIETNAMESE.equals(text(client, root, "/no-header",
                    HttpResponse.BodyHandlers.ofString()).body()),
                    "missing header fallback UTF-8");
            check(VIETNAMESE.equals(text(client, root, "/unsupported",
                    HttpResponse.BodyHandlers.ofString()).body()),
                    "unsupported charset fallback UTF-8");
            System.out.println("PASS UTF-8 fallback");

            check(!VIETNAMESE.equals(text(client, root, "/wrong",
                    HttpResponse.BodyHandlers.ofString()).body()),
                    "wrong declared charset causes mojibake");
            check(VIETNAMESE.equals(text(client, root, "/wrong",
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)).body()),
                    "explicit UTF-8 overrides wrong header");
            byte[] rawWrong = client.send(request(root, "/wrong"),
                    HttpResponse.BodyHandlers.ofByteArray()).body();
            check(Arrays.equals(VIETNAMESE.getBytes(StandardCharsets.UTF_8),
                    rawWrong), "raw bytes remain unchanged");
            System.out.println("PASS wrong header and raw bytes");

            check("\u1EAF".equals(text(client, root, "/utf16le",
                    HttpResponse.BodyHandlers.ofString()).body()),
                    "UTF-16LE header charset");
            check(!"\u1EAF".equals(text(client, root, "/utf16le",
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)).body()),
                    "forced UTF-8 cannot decode UTF-16LE equivalent");
            System.out.println("PASS UTF-16LE charset");

            check("".equals(text(client, root, "/empty",
                    HttpResponse.BodyHandlers.ofString()).body()),
                    "zero byte response is empty String");
            System.out.println("PASS empty body");

            String decoded = text(client, root, "/malformed",
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)).body();
            check("\uFFFD(".equals(decoded),
                    "malformed UTF-8 should be replaced");
            byte[] rawMalformed = client.send(request(root, "/malformed"),
                    HttpResponse.BodyHandlers.ofByteArray()).body();
            boolean rejected = false;
            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(rawMalformed));
            } catch (CharacterCodingException expected) {
                rejected = true;
            }
            check(rejected, "strict decoder must reject malformed bytes");
            System.out.println("PASS replacement versus strict decoder");

            check("\uFEFFA".equals(text(client, root, "/bom",
                    HttpResponse.BodyHandlers.ofString()).body()),
                    "UTF-8 BOM is retained as U+FEFF");
            System.out.println("PASS UTF-8 BOM");

            HttpResponse<String> notFound = text(client, root, "/not-found",
                    HttpResponse.BodyHandlers.ofString());
            check(notFound.statusCode() == 404
                    && "kh\u00F4ng c\u00F3".equals(notFound.body()),
                    "HTTP status does not control ofString decoder");
            System.out.println("PASS 404 body decoding");

            String asyncText = client.sendAsync(request(root, "/utf8"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
                    .thenApply(HttpResponse::body).join();
            check(VIETNAMESE.equals(asyncText),
                    "sendAsync uses the same body handler contract");
            System.out.println("PASS sendAsync response decoding");

            System.out.println("ALL CHARSET RESPONSE TESTS PASSED");
        } finally {
            server.stop(0);
            executor.shutdownNow();
        }
    }
}
~~~

### Cách biên dịch và chạy

Tại thư mục chứa `BodyStringCharsetDemo.java`, dùng JDK 11 hoặc một JDK mới hỗ trợ target 11:

~~~bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 BodyStringCharsetDemo.java
java --add-modules jdk.httpserver -cp . BodyStringCharsetDemo
~~~

`jdk.httpserver` chỉ dùng để **mô phỏng server trong test**. Ứng dụng thật chỉ dùng HTTP Client thuộc module `java.net.http` không cần thêm module server này. Chương trình kiểm thử trên HTTP/1.1 loopback, cổng động (0), tránh phụ thuộc Internet. `HttpClient` được tái sử dụng; `ExecutorService` của server được tắt trong `finally`.

**Đầu ra khi toàn bộ assertion thành công:**

~~~text
PASS UTF-8 declared charset
PASS declared Latin-1 versus fixed UTF-8
PASS UTF-8 fallback
PASS wrong header and raw bytes
PASS UTF-16LE charset
PASS empty body
PASS replacement versus strict decoder
PASS UTF-8 BOM
PASS 404 body decoding
PASS sendAsync response decoding
ALL CHARSET RESPONSE TESTS PASSED
~~~

Các phép kiểm thử dùng `check(...)` ném `AssertionError` khi sai, không phụ thuộc cờ `-ea` của Java. `--release 11` bảo đảm cú pháp/API phù hợp Java 11 trong bước biên dịch; với sản phẩm phải chạy Java 11 thật, CI vẫn cần chạy thêm trên **runtime Java 11** chứ không chỉ biên dịch bằng JDK mới.

### Các case khó mà chương trình chứng minh

**GET UTF-8:** endpoint `/utf8` gửi chuỗi tiếng Việt có dấu và ký tự `U+1F642` ngoài BMP; `ofString()` đọc đúng vì header chỉ định UTF-8.

**Latin-1:** endpoint `/latin1` trả byte `E9`, header `ISO-8859-1`. `ofString()` đọc đúng `café`, còn `ofString(UTF_8)` không thể giải mã byte `E9` đơn lẻ thành `é` và có ký tự thay thế.

**Fallback:** endpoint `/no-header` không đặt `Content-Type`, còn `/unsupported` khai tên charset không tồn tại. Cả hai chứa UTF-8 thật nên `ofString()` đọc đúng nhờ fallback UTF-8.

**Header sai:** endpoint `/wrong` gửi bytes UTF-8 thật nhưng khai Latin-1. `ofString()` không thể tự biết ý định của server, vì thế đọc ra chuỗi khác. Overload cố định `ofString(UTF_8)` đọc đúng; `ofByteArray()` chứng minh raw bytes vốn không đổi.

**UTF-16LE:** endpoint `/utf16le` gửi bytes của chữ `ắ` theo UTF-16LE và khai đúng charset. `ofString()` đọc đúng; cưỡng ép UTF-8 là sai.

**Body rỗng:** response không có byte body tương ứng với `String` rỗng `""`; điều này không đồng nghĩa HTTP request đã thất bại.

**Malformed UTF-8:** endpoint `/malformed` gửi bytes `C3 28` — là một dãy sai chuẩn UTF-8. `ofString(UTF_8)` của Java trong ví dụ biến dữ liệu lỗi thành `"\uFFFD("`; decoder có `CodingErrorAction.REPORT` phát hiện và báo lỗi.

**BOM:** endpoint `/bom` gửi `EF BB BF 41`, chuỗi thu được là `"\uFEFFA"`. `U+FEFF` là ký tự dữ liệu đầu chuỗi trong test này; không nên mặc định mọi phép giải mã UTF-8 đều tự xóa BOM.

**404:** endpoint `/not-found` trả HTTP 404 nhưng vẫn có body văn bản có dấu. Handler vẫn giải mã body; `statusCode()` được kiểm riêng.

**sendAsync:** `BodyHandlers.ofString(UTF_8)` dùng tương tự khi gửi bất đồng bộ; kiểu trả về là `CompletableFuture<HttpResponse<String>>`. Chương trình dùng `join()` để chờ kết quả ở cuối test, không phải lời khuyên chặn event loop của ứng dụng.

## 5. Khi bytes không hợp lệ: replacement khác strict validation

### 5.1. Vì sao ký tự thay thế có thể xuất hiện?

Khi một decoder được cấu hình theo chế độ **REPLACE**, dãy byte không thể giải mã sẽ được thay bằng ký tự như `U+FFFD`. Điều này tạo một `String` để hiển thị nhưng **không bảo toàn bytes ban đầu**.

Với dữ liệu ngắn:

~~~text
bytes:      C3 28
UTF-8:      C3 cần byte continuation, nhưng 28 là '('
replacement: U+FFFD + '('
Java String: "\uFFFD("
~~~

Không nên dùng phép thử **«không có exception»** làm bằng chứng response body đúng charset. Khi có replacement, bản gốc có thể đã bị mất thông tin. Với API nhận văn bản chỉ để hiển thị, replacement đôi khi được chấp nhận theo chính sách; với chữ ký số, định danh, mã định tuyến, dữ liệu cấu hình hoặc nội dung phải khớp chính xác, **không nên chấp nhận im lặng**.

### 5.2. Nếu cần từ chối bytes lỗi, giữ raw bytes và dùng decoder strict

Đoạn code độc lập về mặt thuật toán (đặt trong method có import phù hợp và `byte[] rawBytes` đã có):

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String strictText = decoder.decode(
        ByteBuffer.wrap(rawBytes)).toString();
// Có thể ném CharacterCodingException khi dữ liệu không hợp lệ.
~~~

Đây là đoạn **minh họa**, không phải chương trình độc lập. Các lớp `CharsetDecoder`, `CodingErrorAction` và `CharacterCodingException` vẫn được hỗ trợ; cách này cho phép chọn policy rõ ràng thay vì trông chờ handler báo lỗi.

Lấy raw bytes:

~~~java
HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());
byte[] rawBytes = response.body();
~~~

Sau đó dùng decoder strict theo charset **được hợp đồng bên ngoài quy định**. Nếu response khai charset khác, phải xác minh chứ không tự dùng UTF-8 trong mọi tình huống. Với tệp rất lớn, không cần tải toàn bộ body vào RAM chỉ để decode; dùng luồng hoặc xử lý từng buffer và quản lý trạng thái decoder.

**Khác biệt quan trọng:** ví dụ chuẩn của `ofString` có thể thay byte lỗi; `Files.readString(path, UTF_8)` lại có hợp đồng ném `IOException` cho byte malformed/unmappable. Không suy luận mọi API «bytes thành String» có cùng chính sách lỗi giải mã.

## 6. Cách xử lý server khai sai Content-Type

Khi hệ thống thực tế trả văn bản lỗi dấu, quy trình điều tra an toàn là:

1. **Ghi nhận `Content-Type` response** (bao gồm tham số charset) và status code, nhưng tránh log body có dữ liệu nhạy cảm.
2. **Lấy raw bytes** bằng `BodyHandlers.ofByteArray()` trong môi trường kiểm thử hoặc chẩn đoán được cho phép.
3. **So với byte mẫu theo giao thức**: ví dụ `"ắ".getBytes(UTF_8)` khác bytes theo UTF-16LE/charset khác.
4. **Kiểm chính xác bên phát** đang serialize/encode thế nào; đừng chỉ sửa phép hiển thị của client.
5. **Chọn policy:** tin header `ofString()` khi server chuẩn; cố định `ofString(UTF_8)` khi giao thức bảo đảm UTF-8; hoặc xử lý tùy theo `Content-Type`/validation khi hệ thống thực sự hỗ trợ nhiều charset.
6. **Viết regression test** cho ít nhất một chuỗi ASCII, tiếng Việt có dấu, ký tự ngoài BMP và một byte lỗi/trường hợp header sai.

Đừng «fix» mojibake bằng một chuỗi `new String(old.getBytes(...), ...)` áp dụng chung không có hợp đồng; khi dữ liệu đã bị thay thế bằng `U+FFFD`, nhiều thông tin gốc có thể đã mất và không thể phục hồi tin cậy.

### 6.1. Có nên tự xây `BodyHandler` theo header?

Nếu cần quy tắc phức tạp (ví dụ từ chối charset không hỗ trợ thay vì UTF-8 fallback), có thể tự tạo `HttpResponse.BodyHandler<T>` và chọn `BodySubscriber` theo `ResponseInfo.headers()` hoặc nhận bytes rồi validate riêng.

Với phần lớn ứng dụng có một charset được quy định rõ, **`BodyHandlers.ofString(StandardCharsets.UTF_8)` đơn giản và dễ kiểm thử hơn**. Chỉ viết custom handler khi thật sự có yêu cầu vượt hợp đồng dựng sẵn, vì tự parse header/charset và xử lý lỗi sẽ mang thêm trách nhiệm bảo mật và tương thích.

## 7. Bộ kiểm thử hồi quy nên có

| Test | Fixture | Mong đợi |
| --- | --- | --- |
| Declared UTF-8 | Response có `charset=UTF-8`, tiếng Việt và emoji | `ofString()` == chuỗi chuẩn |
| Declared Latin-1 | `charset=ISO-8859-1`, byte `E9` | `ofString()` == `"é"` |
| Fixed charset | Latin-1 header, handler `ofString(UTF_8)` | Không «tuân» header, có thể replacement |
| No header | Không có `Content-Type`, bytes UTF-8 | `ofString()` fallback UTF-8 |
| Unsupported charset | `charset=X-NOT-SUPPORTED`, bytes UTF-8 | Fallback UTF-8 |
| Incorrect header | UTF-8 bytes, header ISO-8859-1 | `ofString()` sai, fixed UTF-8 đúng theo hợp đồng |
| UTF-16LE | `charset=UTF-16LE` và bytes UTF-16LE | `ofString()` == chữ gốc |
| Empty response | 0 byte | `body().equals("")` |
| Malformed UTF-8 | `C3 28` | Replacement khi đọc text; strict decoder ném lỗi |
| UTF-8 BOM | `EF BB BF 41` | Body chứa `U+FEFF` + `A` |
| HTTP 404 | status 404 và text UTF-8 | Body vẫn được giải mã, kiểm status riêng |
| sendAsync | Cùng URL, handler `ofString(UTF_8)` | Future có `HttpResponse<String>` đúng |

Trong CI, nên kiểm **exact String** và raw byte fixtures khi có yêu cầu bảo toàn dữ liệu. Test theo mã `U+XXXX` tránh phụ thuộc font và trạng thái copy/paste. Dùng server loopback có cổng động thay vì thực hiện request ra một dịch vụ công khai dễ thay đổi.

## 8. Lưu ý vận hành và lỗi phổ biến

### 8.1. Đừng chặn event loop khi chọn `sendAsync`

~~~java
CompletableFuture<String> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
              .thenApply(response -> {
                  if (response.statusCode() >= 400) {
                      throw new IllegalStateException(
                              "HTTP " + response.statusCode());
                  }
                  return response.body();
              });
~~~

Đoạn minh họa này giữ chuỗi xử lý bất đồng bộ; chỉ gọi `future.join()` tại nơi ứng dụng thực sự cần đợi, như cuối một test hoặc command-line task. Nếu xử lý body mất nhiều CPU hoặc blocking, dùng executor thích hợp và không giả định callback luôn chạy trên một thread cố định.

### 8.2. `ofString` không phù hợp với mọi response

- **Binary:** ảnh, zip, PDF, protobuf... dùng `ofByteArray`, stream hoặc file; đừng giải mã tùy ý thành String.
- **Văn bản khổng lồ:** `ofString` lưu toàn body vào bộ nhớ trước khi hoàn tất. Với dữ liệu lớn, cân nhắc `ofInputStream`, `ofLines` hoặc custom streaming subscriber, đồng thời quản lý việc tiêu thụ và đóng tài nguyên.
- **Tài liệu JSON:** `ofString` giải mã body thành text nhưng **không parse JSON** và không xác minh cấu trúc.
- **Body theo chunk:** `ofString` sẽ ghép dữ liệu thành một String; ứng dụng không cần tự ghép từng TCP packet, nhưng không được suy ra `Content-Length` luôn có sẵn.
- **HTTP status lỗi:** `BodyHandlers` dựng sẵn chấp nhận body bất kể status; đừng đưa body 404 vào parser success mà không kiểm.
- **Server không đáng tin:** một header charset sai hoặc charset hiếm có thể khiến text khác với mong đợi. Đặt giới hạn kích thước body và validate nội dung theo yêu cầu ứng dụng.

### 8.3. Những sai lầm cần tránh

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `ofString()` **luôn** UTF-8. | Có thể dùng charset từ `Content-Type`. | Đọc Javadoc, kiểm header và fixture Latin-1. |
| Nghĩ `ofString(UTF_8)` vẫn tuân `charset=ISO-8859-1`. | Overload này sử dụng charset truyền vào. | Chọn overload phù hợp hợp đồng API. |
| Hiểu fallback UTF-8 là server chắc chắn gửi UTF-8. | Fallback chỉ là quyết định giải mã của Java. | Kiểm raw bytes/giao thức phía server. |
| Dùng `new String(bytes)` dựa vào charset mặc định máy. | Dễ lệch môi trường/runtime. | Chỉ định `StandardCharsets.UTF_8` hoặc charset hợp đồng. |
| Dùng `String.length()` làm số bytes HTTP. | UTF-16 khác UTF-8. | Dùng bytes và encoding xác định. |
| Bắt mọi chuỗi có `U+FFFD` rồi khẳng định chắc chắn lỗi mạng. | Ký tự thay thế có thể đến từ decoder hoặc nằm sẵn trong nội dung hợp lệ. | So raw bytes, validate theo policy. |
| Giải mã response nhị phân bằng `ofString`. | Có thể làm mất thông tin nhị phân. | Dùng `ofByteArray`/stream/file. |
| Dùng `trim()` hoặc `strip()` trước khi test exact String. | Che lỗi mất khoảng trắng/newline. | So sánh chính xác body gốc. |
| Không kiểm HTTP 4xx/5xx. | `ofString` vẫn trả text của lỗi. | Kiểm `statusCode()` độc lập. |
| Giả định `ofString` tự giải nén và parse JSON. | Charset decoding không phải decompression/parsing. | Tách riêng tầng content coding và parser. |
| Dùng `HttpClient.close()` khi compile `--release 11`. | `close()` được bổ sung sau Java 11. | Tuân API baseline, quản lý executor/stream mình tạo. |
| Chỉ kiểm ASCII trong bài test. | Không phát hiện lỗi dấu và supplementary. | Fixture tiếng Việt, Latin-1, UTF-16LE và emoji. |

## 9. Câu hỏi tự đánh giá

**Câu 1.** Response có `Content-Type: text/plain; charset=ISO-8859-1` và body là byte `E9`. `BodyHandlers.ofString()` trả gì?

**Đáp án:** `"é"`, vì handler sử dụng charset của `Content-Type`.

**Câu 2.** Với response đó, nếu dùng `BodyHandlers.ofString(StandardCharsets.UTF_8)` thì sao?

**Đáp án:** Handler giải mã bằng UTF-8 bất kể header; byte `E9` đơn lẻ không phải UTF-8 hợp lệ, trong ví dụ test được chuyển thành ký tự thay thế `U+FFFD`.

**Câu 3.** Response không có header `Content-Type`, nhưng bytes là UTF-8. `ofString()` chọn charset gì?

**Đáp án:** UTF-8 fallback theo Javadoc Java 11.

**Câu 4.** Nếu header khai charset không được hỗ trợ, `ofString()` luôn ném exception trước khi đọc body không?

**Đáp án:** Không. Theo hợp đồng dựng sẵn, charset không hỗ trợ dẫn đến **fallback UTF-8**. Điều đó không bảo đảm bytes server thật tương thích UTF-8.

**Câu 5.** Response chứa bytes UTF-8 của tiếng Việt, nhưng header khai sai Latin-1. Phương án nào an toàn?

**Đáp án:** Xác minh hợp đồng/bytes của server, sửa header ở phía phát khi có thể. Chỉ cố định `ofString(UTF_8)` nếu endpoint thực sự cam kết gửi UTF-8; không đoán dựa vào một ví dụ ngắn.

**Câu 6.** `ofString()` có trả về bản gốc `byte[]` không?

**Đáp án:** Không, nó trả `String` đã được giải mã. Muốn kiểm bytes nguyên trạng, dùng `BodyHandlers.ofByteArray()`.

**Câu 7.** Khi body chứa bytes UTF-8 không hợp lệ, làm sao yêu cầu chương trình **báo lỗi** thay vì dùng `U+FFFD`?

**Đáp án:** Nhận raw bytes bằng `ofByteArray()` và sử dụng `CharsetDecoder` đặt `CodingErrorAction.REPORT` cho `onMalformedInput`/`onUnmappableCharacter`.

**Câu 8.** `ofString()` có tự xử lý JSON hoặc coi HTTP 404 là exception nghiệp vụ không?

**Đáp án:** Không. Nó giải mã bytes thành text; parsing JSON và xử lý `statusCode()` là trách nhiệm tầng ứng dụng.

**Câu 9.** Tại sao `"🙂"` và UTF-8 bytes của nó có độ dài khác nhau?

**Đáp án:** Ký tự U+1F642 dùng **2 UTF-16 code units** trong Java String nhưng **4 bytes UTF-8**. Không dùng `String.length()` làm kích thước payload.

**Câu 10.** Khi dùng `sendAsync(..., BodyHandlers.ofString(...))`, kiểu kết quả là gì?

**Đáp án:** `CompletableFuture<HttpResponse<String>>`. Charset decoding của handler không đổi so với `send`; chỉ khác cách chờ/ghép xử lý phản hồi.

## Checklist áp dụng

- [ ] Biết phản hồi HTTP truyền **bytes** và Java nhận **String** thông qua charset decoding.
- [ ] Phân biệt `ofString()` theo header với `ofString(Charset)` cố định.
- [ ] Biết fallback **UTF-8** khi thiếu header hoặc charset không được hỗ trợ.
- [ ] Kiểm tra raw bytes khi gặp mojibake, không áp dụng chuyển mã tùy tiện.
- [ ] Phân biệt `Content-Type`, `Content-Encoding` và các thao tác parse dữ liệu.
- [ ] Kiểm thử UTF-8 tiếng Việt, Latin-1, UTF-16LE, malformed bytes, BOM, body rỗng, 404 và `sendAsync`.
- [ ] Nếu cần từ chối bytes không hợp lệ, sử dụng `ofByteArray` + `CharsetDecoder` với `CodingErrorAction.REPORT`.
- [ ] Không dùng `ofString` cho binary/tệp quá lớn nếu nghiệp vụ yêu cầu streaming.
- [ ] Chạy thành công `BodyStringCharsetDemo.java` bằng `javac --release 11 --add-modules jdk.httpserver`; stdout khớp ví dụ.
- [ ] Biết rằng `ofString` không tự giải quyết mọi lỗi HTTP, JSON parsing hay charset từ server sai.

## Nguồn tham khảo chính thức

1. [Java SE 11 — `HttpResponse.BodyHandlers`: `ofString()`, `ofString(Charset)`, `ofByteArray()`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
2. [Java SE 11 — `HttpResponse.BodySubscribers`: giải mã body thành String](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
3. [Java SE 11 — `HttpClient`: `send` và `sendAsync`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
4. [Java SE 11 — `HttpHeaders`: truy xuất response headers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpHeaders.html)
5. [Java SE 11 — `CharsetDecoder`: `REPORT`, `REPLACE` và malformed input](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
6. [Java SE 11 — `StandardCharsets`: UTF-8, ISO-8859-1, UTF-16LE](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html)
7. [Java SE 26 — `HttpResponse.BodyHandlers`: đối chiếu API hiện vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
