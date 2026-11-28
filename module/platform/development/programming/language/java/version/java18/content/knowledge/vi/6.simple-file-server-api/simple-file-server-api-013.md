# Quản lý request body, response body và đóng HttpExchange trong handler tự viết

> **Chương:** API SimpleFileServer  
> **Module học:** JAVA_VERSION_JAVA18 — SimpleFileServer được bổ sung từ Java 18; bài này dùng HttpExchange và HttpHandler để viết endpoint tùy biến, kết hợp với file handler trên JDK hiện đại.  
> **Mục tiêu:** Đọc và đóng request body, gửi và đóng response body, chọn đúng response length, kết thúc exchange an toàn và tránh lỗi kết nối do quản lý stream sai.

## 1. HttpExchange đại diện cho một lượt request/response

Khi HttpServer nhận một HTTP request và chuyển nó đến HttpHandler, handler nhận một đối tượng **HttpExchange**. Đối tượng này gói cả request từ client và response mà ứng dụng cần gửi lại.

Các API thường dùng:

| API | Vai trò |
| --- | --- |
| `getRequestMethod()` | Lấy HTTP method như `GET`, `POST`, `HEAD`. |
| `getRequestURI()` | Lấy URI của request. |
| `getRequestHeaders()` | Đọc headers request; tập headers này là immutable. |
| `getRequestBody()` | Lấy `InputStream` để đọc bytes của request body. |
| `getResponseHeaders()` | Lấy `Headers` mutable để chuẩn bị response headers. |
| `sendResponseHeaders(status, responseLength)` | Gửi status và response headers, đồng thời khai báo cách gửi body. |
| `getResponseBody()` | Lấy `OutputStream` để ghi response body. |
| `close()` | Đóng request input stream và response output stream để kết thúc exchange. |

HttpExchange triển khai `AutoCloseable`, vì vậy có thể quản lý bằng `try-with-resources`. Hợp đồng request/response body và cách đóng exchange đã có từ các JDK trước Java 18, vẫn còn áp dụng trên JDK hiện đại.

## 2. Vòng đời chuẩn của một exchange

Javadoc mô tả trình tự xử lý điển hình:

~~~text
1. Đọc request method và request headers
                 |
                 v
2. Đọc request body qua InputStream (nếu có)
                 |
                 v
3. Đóng request InputStream sau khi đọc
                 |
                 v
4. Thiết lập response headers
                 |
                 v
5. sendResponseHeaders(status, responseLength)
                 |
                 v
6. Lấy response OutputStream và ghi body
                 |
                 v
7. Đóng response OutputStream
                 |
                 v
8. Exchange kết thúc
~~~

Hai quy tắc cần nhớ:

- Phải gọi `sendResponseHeaders(...)` **trước** khi gọi `getResponseBody()`.
- Phải đóng response output stream để kết thúc exchange, kể cả khi response không gửi body. Có thể gọi `exchange.close()` để đóng cả hai stream.

Nếu không kết thúc exchange, hành vi không được xác định; thông thường tài nguyên có thể không được giải phóng hoặc tái sử dụng đúng cách. Nếu chỉ đóng request stream mà không gửi/đóng response, exchange vẫn chưa hoàn tất.

## 3. Đọc request body đúng cách

`getRequestBody()` trả về một `InputStream`. Gọi phương thức nhiều lần trên cùng exchange vẫn nhận cùng một stream, không phải một bản sao mới của request body.

Ví dụ đọc toàn bộ request body:

~~~java
byte[] requestBytes;
try (InputStream input = exchange.getRequestBody()) {
    requestBytes = input.readAllBytes();
}
~~~

`readAllBytes()` đọc đến EOF; đây là cách đơn giản cho request nhỏ trong ví dụ học tập. Khi đọc dữ liệu văn bản, phải giải mã bytes bằng charset mà giao thức ứng dụng quy định:

~~~java
String text = new String(requestBytes, StandardCharsets.UTF_8);
~~~

Không nên dùng `new String(requestBytes)` nếu cần kết quả nhất quán, vì overload đó dùng charset mặc định. Request body cũng có thể là dữ liệu nhị phân; khi đó giữ nguyên `byte[]` hoặc xử lý theo luồng, không ép thành String.

### 3.1. Đọc hết request body trước khi đóng

Javadoc khuyến nghị ứng dụng **đọc hết dữ liệu** từ request InputStream trước khi đóng. Nếu đóng stream khi vẫn còn bytes chưa đọc, implementation sẽ cố đọc và loại bỏ phần còn lại, nhưng chỉ đến một giới hạn số bytes phụ thuộc implementation.

Đóng request stream khi chưa đọc hết không phải lúc nào cũng là lỗi, nhưng có thể làm TCP connection bên dưới không dùng lại được cho exchange tiếp theo. Vì vậy:

- Nếu handler cần request body, hãy đọc đến EOF rồi đóng stream.
- Nếu handler từ chối request trước khi đọc hết body, hãy hiểu rằng connection có thể không được tái sử dụng.
- Không giả định request nào cũng có `Content-Length`; body có thể được truyền theo cơ chế streaming/chunked.
- Không dùng `readAllBytes()` cho payload không giới hạn trong hệ thống thật; cần giới hạn kích thước và/hoặc xử lý streaming.

### 3.2. Giới hạn kích thước body

Ví dụ nhỏ có thể dùng `readAllBytes()`, nhưng endpoint nhận dữ liệu từ client cần giới hạn dung lượng. Có thể kiểm tra `Content-Length` nếu header hiện diện, đồng thời áp dụng giới hạn khi đọc thực tế vì không phải request nào cũng cung cấp độ dài đó.

Ví dụ helper đọc tối đa một số bytes vào bộ nhớ:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

static byte[] readAtMost(InputStream input, int maxBytes)
        throws IOException {
    ByteArrayOutputStream buffer = new ByteArrayOutputStream();
    byte[] chunk = new byte[8192];
    int total = 0;
    int count;

    while ((count = input.read(chunk)) != -1) {
        if (count > maxBytes - total) {
            throw new IOException("Request body vượt giới hạn");
        }
        buffer.write(chunk, 0, count);
        total += count;
    }
    return buffer.toByteArray();
}
~~~

Helper này đọc đến EOF nếu body nằm trong giới hạn; nếu vượt giới hạn, nó dừng sớm và caller phải đóng stream/exchange. Việc đóng khi chưa đọc hết có thể khiến connection không được tái sử dụng. Trong ứng dụng thực tế, cần quyết định rõ chính sách cho payload quá lớn, timeout đọc và giới hạn ở proxy/server trước khi nhận dữ liệu.

## 4. Gửi response body và response length

Trình tự gửi response:

1. Chuẩn bị headers qua `getResponseHeaders()`.
2. Gọi `sendResponseHeaders(status, responseLength)`.
3. Gọi `getResponseBody()` và ghi đúng lượng bytes theo response length.
4. Đóng output stream.

Tham số `responseLength` có ý nghĩa đặc biệt:

| `responseLength` | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| Số dương | Độ dài body cố định, tính bằng **bytes**. | Phải ghi chính xác số bytes đã khai báo. |
| `0` | Dùng chunked transfer encoding; độ dài body không biết trước. | Ghi số bytes tùy ý, đóng output stream để kết thúc body. |
| `-1` | Không gửi response body. | Dùng cho response rỗng, ví dụ HEAD hoặc 204. |

Ví dụ gửi body có độ dài biết trước:

~~~java
byte[] body = "Xin chào".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, body.length);

try (OutputStream output = exchange.getResponseBody()) {
    output.write(body);
}
~~~

Độ dài phải là `body.length`, không phải `String.length()`. Với chuỗi có dấu tiếng Việt hoặc emoji, số ký tự Java và số bytes UTF-8 có thể khác nhau.

Nếu ghi nhiều bytes hơn độ dài cố định, thao tác ghi có thể ném `IOException`. Nếu ghi ít hơn, `close()` của output stream có thể ném `IOException`. Trong cả hai trường hợp exchange bị hủy và TCP connection bị đóng.

### 4.1. Body rỗng và chunked không giống nhau

Một lỗi phổ biến là truyền `body.length` mà không xử lý mảng rỗng:

~~~java
byte[] body = new byte[0];
exchange.sendResponseHeaders(200, body.length); // responseLength = 0
~~~

Giá trị `0` có nghĩa là **chunked**, không phải "không có body". Đây vẫn là response hợp lệ với body rỗng theo dạng chunked, nhưng nếu muốn khai báo rõ không gửi body, dùng `-1`:

~~~java
exchange.sendResponseHeaders(204, -1);
exchange.close();
~~~

Từ JDK 26, `HttpExchange` có hai hằng số diễn đạt rõ hai ý nghĩa này:

- `HttpExchange.RSPBODY_EMPTY`: không gửi response body.
- `HttpExchange.RSPBODY_CHUNKED`: response body dùng chunked transfer encoding.

Hai hằng số này được thêm từ JDK 26. Với mã nguồn cần chạy từ Java 18, tiếp tục dùng `-1` cho no-body và `0` cho chunked để giữ tương thích.

### 4.2. Streaming response với chunked encoding

Khi không biết trước tổng số bytes cần gửi, có thể dùng `responseLength = 0`:

~~~java
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, 0);

try (OutputStream output = exchange.getResponseBody()) {
    output.write("Phần 1\n".getBytes(StandardCharsets.UTF_8));
    output.flush();
    output.write("Phần 2\n".getBytes(StandardCharsets.UTF_8));
}
~~~

Đóng output stream sẽ kết thúc response chunked. Không đóng stream thì client có thể tiếp tục chờ phần còn lại của response.

## 5. Không tự đặt Content-Length sai

Javadoc khuyến nghị thiết lập response headers trước khi gửi, ngoại trừ `Content-Length`. Nếu ứng dụng chưa đặt `Content-Length`, `sendResponseHeaders(...)` sẽ thiết lập giá trị phù hợp với `responseLength`.

Vì vậy, với response body có độ dài cố định, cách thông thường là:

~~~java
byte[] body = createBody();
exchange.getResponseHeaders().set("Content-Type", "application/octet-stream");
exchange.sendResponseHeaders(200, body.length);
~~~

Không cần tự ghi:

~~~java
exchange.getResponseHeaders().set(
        "Content-Length", String.valueOf(body.length));
~~~

Nếu tự đặt Content-Length không khớp số bytes thực tế, client có thể chờ mãi, nhận response bị cắt hoặc connection bị đóng. Đặc biệt, không dùng số ký tự của String làm Content-Length cho nội dung UTF-8.

## 6. Đóng HttpExchange đúng cách

`HttpExchange.close()` thực hiện hai việc theo thứ tự:

1. Đóng request InputStream nếu chưa đóng.
2. Đóng response OutputStream nếu chưa đóng.

Đóng response OutputStream cũng đóng request InputStream nếu nó còn mở. Tuy vậy, nếu handler cần request body, hãy đọc hết body trước khi đóng response.

Có thể quản lý exchange bằng try-with-resources:

~~~java
static void handle(HttpExchange exchange) throws IOException {
    try (exchange) {
        // Đọc request, chuẩn bị headers, gửi response.
    }
}
~~~

Khi thoát khỏi block, dù return sớm hay có exception, `exchange.close()` vẫn được gọi. Cách này hữu ích với handler có nhiều nhánh như method không hỗ trợ, body không hợp lệ hoặc response không có nội dung.

### 6.1. Đóng stream riêng hay đóng exchange?

Hai cách sau đều có thể dùng:

~~~java
try (OutputStream output = exchange.getResponseBody()) {
    output.write(body);
}
~~~

Hoặc:

~~~java
exchange.sendResponseHeaders(200, body.length);
try (exchange) {
    exchange.getResponseBody().write(body);
}
~~~

Trong ví dụ thứ hai, exchange tự đóng output stream. Không gọi `getResponseBody()` trước `sendResponseHeaders(...)`.

Một handler có thể đóng request InputStream và response OutputStream riêng, rồi để `exchange.close()` làm lớp bảo vệ cuối. Việc đóng stream nhiều lần thông thường không làm thay đổi kết quả, nhưng nên giữ lifecycle đơn giản và rõ ràng.

## 7. HEAD, 204 và các response không có body

Một số response không gửi body:

- `HEAD`: trả headers tương ứng với GET nhưng không gửi body.
- `204 No Content`: không có response body.
- `304 Not Modified`: không có response body.

Ví dụ handler trả HEAD:

~~~java
if (exchange.getRequestMethod().equals("HEAD")) {
    exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
    exchange.sendResponseHeaders(200, -1);
    exchange.close();
    return;
}
~~~

Ví dụ trả 204:

~~~java
exchange.sendResponseHeaders(204, -1);
exchange.close();
~~~

Ngay cả khi không có body, exchange vẫn cần kết thúc. Gọi `exchange.close()` sau khi gửi headers để đóng response output stream và request input stream.

Đừng gọi `sendResponseHeaders()` hai lần cho cùng một exchange. Nếu headers đã được gửi, lần gọi tiếp theo có thể ném `IOException`. Hãy quyết định status/body trước khi gửi response headers.

## 8. Ví dụ hoàn chỉnh: echo request body và kết hợp file handler

Ví dụ sau tạo hai context:

- `/echo/`: handler tùy biến nhận POST body và trả lại đúng bytes đã nhận.
- `/`: `SimpleFileServer.createFileHandler(root)` phục vụ tệp tĩnh.

Handler echo đọc request body, đóng input stream, gửi response length đúng bằng số bytes, ghi response body và đóng exchange. Server bind vào loopback với cổng `0` để tránh xung đột cổng trong kiểm thử.

Lưu thành `ExchangeBodyDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;

public class ExchangeBodyDemo {
    private static void sendBytes(
            HttpExchange exchange,
            int status,
            String contentType,
            byte[] body) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", contentType);

        if (body.length == 0) {
            // -1: không gửi body; try-with-resources sẽ đóng exchange.
            exchange.sendResponseHeaders(status, -1);
            return;
        }

        // responseLength là số bytes, không phải số ký tự.
        exchange.sendResponseHeaders(status, body.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(body);
        }
    }

    private static HttpHandler echoHandler() {
        return exchange -> {
            try (exchange) {
                if (!exchange.getRequestMethod().equals("POST")) {
                    exchange.getResponseHeaders().set("Allow", "POST");
                    sendBytes(
                            exchange,
                            405,
                            "text/plain; charset=utf-8",
                            "Method Not Allowed".getBytes(StandardCharsets.UTF_8));
                    return;
                }

                byte[] requestBody;
                try (InputStream input = exchange.getRequestBody()) {
                    // Chỉ dùng readAllBytes cho body nhỏ trong ví dụ học tập.
                    requestBody = input.readAllBytes();
                }

                sendBytes(
                        exchange,
                        200,
                        "text/plain; charset=utf-8",
                        requestBody);
            }
        };
    }

    private static URI uri(
            InetAddress address, int port, String path) {
        String host = address.getHostAddress();
        if (address instanceof Inet6Address) {
            host = "[" + host + "]";
        }
        return URI.create("http://" + host + ":" + port + path);
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("exchange-static-root-")
                .toAbsolutePath().normalize();
        Files.writeString(
                root.resolve("hello.txt"),
                "Static file response",
                StandardCharsets.UTF_8);

        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0),
                0);
        server.createContext("/echo/", echoHandler());
        server.createContext(
                "/", SimpleFileServer.createFileHandler(root));

        try {
            server.start();

            InetSocketAddress bound = server.getAddress();
            URI echoUri = uri(
                    bound.getAddress(), bound.getPort(), "/echo/");
            URI fileUri = uri(
                    bound.getAddress(), bound.getPort(), "/hello.txt");

            HttpClient client = HttpClient.newHttpClient();
            String message = "Xin chào từ Java 18+";

            HttpResponse<byte[]> echo = client.send(
                    HttpRequest.newBuilder(echoUri)
                            .header("Content-Type", "text/plain; charset=utf-8")
                            .POST(HttpRequest.BodyPublishers.ofString(
                                    message, StandardCharsets.UTF_8))
                            .build(),
                    HttpResponse.BodyHandlers.ofByteArray());

            HttpResponse<String> file = client.send(
                    HttpRequest.newBuilder(fileUri).GET().build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            String echoedText = new String(
                    echo.body(), StandardCharsets.UTF_8);

            if (echo.statusCode() != 200 || !echoedText.equals(message)) {
                throw new AssertionError("Echo response không khớp request body");
            }
            if (file.statusCode() != 200
                    || !file.body().equals("Static file response")) {
                throw new AssertionError("Static response không hợp lệ");
            }

            System.out.println("Echo status: " + echo.statusCode());
            System.out.println("Echo body: " + echoedText);
            System.out.println("Static status: " + file.statusCode());
            System.out.println("Static body: " + file.body());
        } finally {
            server.stop(1);
            try (var paths = Files.walk(root)) {
                for (Path path : paths
                        .sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~bash
javac ExchangeBodyDemo.java
java ExchangeBodyDemo
~~~

Kết quả mong đợi:

~~~text
Echo status: 200
Echo body: Xin chào từ Java 18+
Static status: 200
Static body: Static file response
~~~

Ví dụ cho thấy `HttpExchange` quản lý hai luồng độc lập: request InputStream để đọc dữ liệu client gửi lên và response OutputStream để ghi dữ liệu trả về. File handler ở context `/` vẫn hoạt động bình thường bên cạnh endpoint echo.

## 9. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client chờ response mãi | Handler không gửi response headers hoặc không đóng response output stream. | Gọi `sendResponseHeaders()` và đóng output stream hoặc exchange. |
| `getResponseBody()` gây lỗi | Gọi trước `sendResponseHeaders()`. | Gửi status/headers trước rồi mới lấy output stream. |
| `sendResponseHeaders()` ném IOException | Đã gửi headers trước đó hoặc lỗi I/O. | Chỉ gửi response một lần; quyết định status trước khi gửi. |
| Connection bị đóng khi ghi body | Ghi nhiều bytes hơn response length cố định. | Dùng đúng `body.length` hoặc chunked khi không biết trước độ dài. |
| `close()` của output stream ném IOException | Ghi ít bytes hơn response length đã khai báo. | Bảo đảm ghi đủ số bytes đã cam kết. |
| Client nhận body rỗng ngoài dự kiến | Dùng `-1` khi muốn có body hoặc không ghi vào output stream. | Dùng độ dài cố định dương hoặc `0` cho chunked. |
| Body rỗng nhưng response chunked | Truyền `0` với mảng bytes rỗng. | Dùng `-1` nếu muốn no-body. |
| Request tiếp theo không dùng lại TCP connection | Handler đóng request stream khi chưa đọc hết body. | Đọc hết request body trước khi đóng nếu cần giữ khả năng tái sử dụng connection. |
| Bộ nhớ tăng khi nhận POST lớn | Dùng `readAllBytes()` với payload không giới hạn. | Giới hạn kích thước, streaming và timeout. |
| Tiếng Việt bị lỗi | Giải mã bytes bằng charset không đúng. | Dùng `StandardCharsets.UTF_8` theo hợp đồng request/response. |
| Response 204 hoặc HEAD có body | Handler vẫn ghi body sau khi gửi no-body headers. | Dùng response length `-1` và không ghi body. |

## 10. Quy tắc thực hành

1. **Đọc request body trước khi đóng:** nếu cần nội dung, tiêu thụ stream đến EOF rồi đóng.
2. **Đặt response headers trước khi gửi:** không thay đổi headers sau `sendResponseHeaders()`.
3. **Tính response length bằng bytes:** với String, mã hóa trước rồi dùng `byte[].length`.
4. **Chọn response length đúng:** số dương cho fixed length, `0` cho chunked, `-1` cho no-body trên mã tương thích Java 18.
5. **Đóng response body:** ngay cả response không body cũng phải kết thúc output stream/exchange.
6. **Dùng try-with-resources:** bảo đảm stream và exchange được đóng khi return hoặc exception.
7. **Không gửi response hai lần:** một exchange chỉ có một lần gửi response headers.
8. **Giới hạn request body:** tránh đọc toàn bộ dữ liệu không tin cậy vào bộ nhớ.
9. **Không giả định Content-Length luôn có mặt:** xử lý request body theo stream.
10. **Tách biệt handler với file server:** handler tự viết chịu trách nhiệm đóng exchange; `SimpleFileServer.createFileHandler()` quản lý việc phục vụ tệp của nó.

## 11. Câu hỏi tự kiểm tra

1. `HttpExchange` đại diện cho những phần nào của một HTTP request/response?
2. Vì sao phải gọi `sendResponseHeaders()` trước `getResponseBody()`?
3. `getRequestBody()` trả về loại stream nào? Vì sao nên đọc hết trước khi đóng?
4. Nếu đóng request body khi chưa đọc hết, điều gì có thể xảy ra với TCP connection?
5. `responseLength` dương, `0` và `-1` có ý nghĩa gì?
6. Vì sao dùng `String.length()` làm response length có thể sai với UTF-8?
7. Khi nào dùng chunked transfer encoding?
8. Vì sao mảng byte rỗng không nên truyền `length == 0` nếu muốn no-body?
9. `HttpExchange.close()` đóng những stream nào?
10. Vì sao cần giới hạn request body trong endpoint nhận dữ liệu từ client?
11. Những hằng số `RSPBODY_EMPTY` và `RSPBODY_CHUNKED` xuất hiện từ JDK nào?
12. Vì sao không nên gọi `sendResponseHeaders()` hai lần trên cùng exchange?

**Bài thực hành:** chạy `ExchangeBodyDemo`, thay body thành chuỗi tiếng Việt và emoji, xác minh bytes được echo chính xác sau khi giải mã UTF-8. Tiếp theo gửi body rỗng, kiểm tra no-body bằng `-1`; thử chunked với response length `0`; cuối cùng sửa cố ý response length nhỏ hơn/lớn hơn body để quan sát lỗi I/O và việc exchange bị hủy. Khôi phục độ dài chính xác sau khi thử.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — HttpExchange](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): vòng đời exchange, request/response body, sendResponseHeaders, close, response length và các hằng số mới từ JDK 26.
- [Oracle JDK 18 — HttpExchange](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): hợp đồng request body, response body, thứ tự gửi headers và kết thúc exchange tương thích Java 18.
- [Oracle JDK 27 — HttpHandler](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): hợp đồng handler nhận HttpExchange.
- [Oracle JDK 27 — HttpServer](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): đăng ký context, start và stop server.
- [Oracle JDK 27 — InputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/InputStream.html): đọc bytes, readAllBytes, transferTo và đóng input stream.
- [Oracle JDK 27 — OutputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/OutputStream.html): ghi bytes, flush và close output stream.
