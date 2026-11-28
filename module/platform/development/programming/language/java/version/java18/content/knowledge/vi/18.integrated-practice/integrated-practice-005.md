# Xác minh hostname, địa chỉ kết nối và nội dung HTTP theo từng bước để định vị lỗi liên thành phần

## 1. Mục tiêu: tìm đúng tầng đang lỗi thay vì đoán

Một request HTTP có thể thất bại ở nhiều tầng khác nhau: tên host không phân giải được, DNS trả về địa chỉ không đúng, ứng dụng kết nối sai cổng, server không lắng nghe ở địa chỉ đó, request HTTP nhận status lỗi, hoặc status `200 OK` nhưng body không đúng định dạng hoặc sai mã hóa UTF-8.

Ví dụ khi gọi:

~~~text
http://api.example.test:8080/health
~~~

ít nhất phải phân biệt ba câu hỏi:

1. **Hostname:** `api.example.test` có được phân giải thành địa chỉ mạng thích hợp không?
2. **Địa chỉ kết nối:** tiến trình có thể mở TCP tới một địa chỉ IP đã chọn và cổng `8080` không?
3. **Nội dung HTTP:** server trả status, header và byte của response đúng hợp đồng ứng dụng chưa?

Bài thuộc chương **Thực hành tổng hợp** của module `JAVA_VERSION_JAVA18`. Kiến thức còn áp dụng trên JDK hiện đại gồm `InetAddress`, `Socket`, `HttpClient`, UTF-8 tường minh (JEP 400) và công cụ HTTP đơn giản từ JDK 18 (JEP 408). Ta kết hợp chúng để xác định vị trí lỗi qua từng bằng chứng, không sử dụng giải pháp phụ thuộc cơ chế đã lỗi thời.

Sau bài này, bạn có thể:

- Tách đúng các trường `scheme`, `host`, `port` và `path` trong URI.
- Kiểm tra danh sách IP bằng `InetAddress.getAllByName` mà không mặc định chỉ có một địa chỉ.
- Kiểm tra TCP connection trực tiếp đến từng địa chỉ/cổng, phân biệt với kết nối HTTP thực tế.
- Thu status, content type, content length và **byte gốc** của HTTP response.
- Phát hiện body UTF-8 sai định dạng bằng `CharsetDecoder` với `CodingErrorAction.REPORT`.
- Phân biệt các lỗi DNS, TCP, TLS, HTTP status, content type, encoding và dữ liệu nghiệp vụ.
- Xây dựng một lab loopback có thể tái hiện, sau đó chuyển quy trình sang dịch vụ thật.

## 2. Đường đi của request và điểm quan sát

~~~mermaid
flowchart TD
    A[URI: scheme, host, port, path] --> B[Phân giải hostname thành IP candidates]
    B --> C[Kiểm tra TCP tới IP và port]
    C --> D{Scheme HTTPS?}
    D -- Có --> E[TLS handshake và kiểm tra certificate]
    D -- Không --> F[Gửi HTTP request]
    E --> F
    F --> G[Nhận HTTP status và response headers]
    G --> H[Nhận byte body]
    H --> I[Giải mã UTF-8 theo hợp đồng nội dung]
    I --> J[Kiểm tra JSON/schema/giá trị nghiệp vụ]
~~~

Bảng phân loại theo **bằng chứng đã có**:

| Tầng | Câu hỏi kiểm chứng | Ví dụ bằng chứng | Không chứng minh được điều gì? |
| --- | --- | --- | --- |
| URI | URL chứa host/cổng/path nào? | `uri.getHost()`, `uri.getPort()` | Không chứng minh host tồn tại. |
| Resolver | Tên host có thành IP không? | `InetAddress.getAllByName(host)` | Không chứng minh cổng đang mở. |
| TCP | Có mở kết nối đến IP:port không? | `Socket.connect(...)` | Không chứng minh server trả HTTP hợp lệ. |
| TLS (nếu HTTPS) | Server xác thực được theo hostname không? | Kết quả TLS handshake của HTTP client | Không chứng minh status/body đúng. |
| HTTP | Status và header là gì? | `HttpResponse.statusCode()`, `headers()` | `200` chưa đủ chứng minh dữ liệu đúng. |
| Encoding | Byte body có là UTF-8 hợp lệ? | Decoder nghiêm ngặt | Không chứng minh JSON/schema đúng. |
| Ứng dụng | Nội dung có đúng trường, kiểu, ý nghĩa? | Parser/schema check, assertions | Không thay thế kiểm tra các tầng bên dưới. |

Không bỏ qua một tầng chỉ vì tầng trước đã thành công. DNS đúng không bảo đảm TCP; TCP đúng không bảo đảm HTTP; HTTP `200` không bảo đảm byte UTF-8 hoặc nội dung nghiệp vụ đúng.

## 3. Phân biệt hostname, IP, địa chỉ bind và Host của HTTP

Trong URI `http://localhost:8080/health`:

- `localhost` là **host do client yêu cầu**.
- `8080` là **cổng đích**; với HTTP không ghi cổng thì mặc định `80`, HTTPS là `443`.
- `/health` là **đường dẫn tài nguyên** trên HTTP server.
- Resolver có thể trả về `127.0.0.1`, `::1` hoặc nhiều địa chỉ khác tùy cấu hình máy.
- Server chỉ nhận kết nối đến địa chỉ/cổng nó thực sự **bind/listen**.

Một ứng dụng có thể bind `127.0.0.1` nhưng client thử kết nối `::1`. Hai địa chỉ này đều là loopback nhưng thuộc hai address family khác nhau. Đừng giả định server bind IPv4 luôn nhận kết nối IPv6.

### Hostname và IP không hoàn toàn thay thế nhau

Khi client dùng hostname, thông tin hostname có thể còn được dùng ở các tầng khác:

- HTTP/1.1 dùng `Host` header để server chọn virtual host.
- HTTP/2 dùng cơ chế authority tương ứng.
- HTTPS còn dùng hostname trong quy trình kiểm tra chứng chỉ máy chủ; SNI có thể ảnh hưởng chứng chỉ được server trình bày.

Việc kết nối thành công đến một IP **không** chứng minh rằng yêu cầu dùng hostname mong muốn sẽ chọn đúng virtual host hoặc vượt qua kiểm tra chứng chỉ TLS.

### Cẩn thận với địa chỉ bind

- `127.0.0.1`: loopback IPv4, chỉ phục vụ kết nối cục bộ của máy.
- `::1`: loopback IPv6.
- `0.0.0.0`: địa chỉ **bind tất cả giao diện IPv4**, không phải hostname đích để client dùng như một URL dịch vụ.
- Địa chỉ IP cụ thể của card mạng: chỉ lắng nghe trên giao diện tương ứng tùy cấu hình.

Trong bài thực hành, server bind `127.0.0.1` để tránh vô tình mở một cổng HTTP ra mạng bên ngoài.

## 4. Kịch bản thực hành: một server, bốn kiểu phản hồi

Ta sẽ chạy một HTTP server cục bộ bằng `com.sun.net.httpserver.HttpServer` thuộc module `jdk.httpserver` và một client `java.net.http.HttpClient`. Tính năng server đơn giản nằm trong JDK và phù hợp cho thử nghiệm, không cần framework bên ngoài.

Lab cung cấp bốn endpoint:

| Endpoint | HTTP status | Body | Mục tiêu |
| --- | ---: | --- | --- |
| `/health` | `200` | JSON UTF-8 hợp lệ với tiếng Việt | Đường đi thành công. |
| `/not-found` | `404` | JSON UTF-8 hợp lệ | TCP và HTTP vẫn hoạt động dù không tìm thấy tài nguyên. |
| `/unready` | `503` | JSON UTF-8 hợp lệ | Server trả phản hồi nhưng ứng dụng chưa sẵn sàng. |
| `/bad-utf8` | `200` | Byte `E2 82` bị cắt cụt | HTTP thành công nhưng nội dung vi phạm UTF-8. |

Mục đích của endpoint cuối là chứng minh một lỗi liên thành phần: **status tốt nhưng body hỏng**. Nếu client chỉ xem status hoặc tự thay byte lỗi bằng ký tự `�`, nó có thể bỏ qua lỗi dữ liệu thực tế.

### Vì sao dùng cổng 0?

Trong `new InetSocketAddress(bindAddress, 0)`, cổng `0` yêu cầu hệ điều hành cấp một cổng khả dụng. Sau khi server được tạo, lấy cổng thực tế bằng `server.getAddress().getPort()`. Điều này làm lab dễ tái chạy mà không cố chiếm cổng `8080` vốn có thể đang được dùng.

Không hard-code cổng của bước HTTP client; hãy truyền cổng mà server thực sự lắng nghe.

## 5. Chương trình Java đầy đủ

Tạo một tệp `HttpPathLab.java`. Chương trình chạy trên JDK 18 hoặc mới hơn; nó chỉ truy cập loopback, không cần Internet.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.net.UnknownHostException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Locale;

public final class HttpPathLab {
    private static final String EXPECTED_BODY =
            "{\"ok\":true,\"message\":\"Xin chào\"}";

    private HttpPathLab() {
    }

    public static void main(String[] args) throws Exception {
        // Bind IPv4 loopback một cách tường minh.
        InetAddress bind = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(bind, 0), 0);

        server.createContext("/health", exchange ->
                respond(exchange, 200,
                        EXPECTED_BODY.getBytes(StandardCharsets.UTF_8)));

        server.createContext("/not-found", exchange ->
                respond(exchange, 404,
                        "{\"error\":\"not_found\"}"
                                .getBytes(StandardCharsets.UTF_8)));

        server.createContext("/unready", exchange ->
                respond(exchange, 503,
                        "{\"error\":\"not_ready\"}"
                                .getBytes(StandardCharsets.UTF_8)));

        server.createContext("/bad-utf8", exchange ->
                respond(exchange, 200,
                        new byte[] { (byte) 0xE2, (byte) 0x82 }));

        server.start();

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        try {
            int port = server.getAddress().getPort();
            String base = "http://127.0.0.1:" + port;

            // Khám phá hostname riêng; không giả định localhost chỉ có IPv4.
            System.out.println("Resolution of localhost:");
            try {
                for (InetAddress address :
                        InetAddress.getAllByName("localhost")) {
                    System.out.println("  " + address.getHostAddress());
                }
            } catch (UnknownHostException ex) {
                System.out.println("  localhost resolution failed; "
                        + "IP-literal tests still run: " + ex.getMessage());
            }

            diagnose(client, URI.create(base + "/health"),
                    200, true, EXPECTED_BODY);
            diagnose(client, URI.create(base + "/not-found"),
                    404, true, null);
            diagnose(client, URI.create(base + "/unready"),
                    503, true, null);
            diagnose(client, URI.create(base + "/bad-utf8"),
                    200, false, null);
        } finally {
            server.stop(0);
        }
    }

    private static void diagnose(
            HttpClient client,
            URI uri,
            int expectedStatus,
            boolean expectedValidUtf8,
            String expectedBody) throws Exception {

        System.out.println();
        System.out.println("=== " + uri + " ===");

        // Bước 1: kiểm tra URI; không tự tách URL bằng split(":").
        String scheme = uri.getScheme();
        String host = uri.getHost();
        int port = uri.getPort() != -1 ? uri.getPort()
                : "https".equalsIgnoreCase(scheme) ? 443 : 80;

        if (!"http".equalsIgnoreCase(scheme)
                && !"https".equalsIgnoreCase(scheme)) {
            throw new IllegalArgumentException("Unsupported scheme: " + scheme);
        }
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("Missing URI host: " + uri);
        }

        System.out.printf(
                "URI: scheme=%s, host=%s, port=%d, path=%s%n",
                scheme, host, port, uri.getRawPath());

        // Bước 2: xem các địa chỉ resolver trả về.
        InetAddress[] candidates = InetAddress.getAllByName(host);
        for (InetAddress address : candidates) {
            System.out.println("Address candidate: "
                    + address.getHostAddress());
        }

        // Bước 3: thử TCP trực tiếp trên từng IP.
        // Probe này độc lập với connection mà HttpClient sẽ chọn.
        boolean tcpReachable = false;
        for (InetAddress address : candidates) {
            try (Socket socket = new Socket()) {
                socket.connect(
                        new InetSocketAddress(address, port),
                        1500);
                System.out.println("TCP probe connected to "
                        + socket.getRemoteSocketAddress());
                tcpReachable = true;
            } catch (IOException ex) {
                System.out.println("TCP probe failed for "
                        + address.getHostAddress() + ":" + port
                        + " (" + ex.getClass().getSimpleName() + ")");
            }
        }
        if (!tcpReachable) {
            throw new IOException(
                    "No candidate accepted a direct TCP connection");
        }

        // Bước 4: gửi HTTP request; không tự động theo redirect.
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<byte[]> response = client.send(
                request, HttpResponse.BodyHandlers.ofByteArray());

        int status = response.statusCode();
        String contentType = response.headers()
                .firstValue("Content-Type").orElse("<missing>");
        byte[] bytes = response.body();

        System.out.println("HTTP version: " + response.version());
        System.out.println("HTTP status: " + status);
        System.out.println("Content-Type: " + contentType);
        System.out.println("Body bytes: " + bytes.length);
        System.out.println("Body prefix (hex): "
                + HexFormat.of().formatHex(
                        bytes, 0, Math.min(bytes.length, 24)));

        if (!contentType.toLowerCase(Locale.ROOT)
                .contains("charset=utf-8")) {
            System.out.println(
                    "WARNING: response does not explicitly declare UTF-8");
        }

        // Bước 5: giải mã nghiêm ngặt và giữ bằng chứng byte lỗi.
        boolean validUtf8;
        String decoded = null;

        try {
            decoded = decodeUtf8Strict(bytes);
            validUtf8 = true;
            System.out.println("Decoded UTF-8: " + decoded);
        } catch (CharacterCodingException ex) {
            validUtf8 = false;
            System.out.println("Invalid UTF-8: "
                    + ex.getClass().getSimpleName());
        }

        // Bước 6: kiểm tra hợp đồng của lab, không chỉ nhìn status.
        if (status != expectedStatus) {
            throw new AssertionError("Unexpected HTTP status: " + status);
        }
        if (validUtf8 != expectedValidUtf8) {
            throw new AssertionError("Unexpected UTF-8 validity");
        }
        if (expectedBody != null && !expectedBody.equals(decoded)) {
            throw new AssertionError("Unexpected application body");
        }

        System.out.println("Expected lab result verified");
    }

    private static String decodeUtf8Strict(byte[] bytes)
            throws CharacterCodingException {

        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.wrap(bytes);
        CharBuffer output = CharBuffer.allocate(Math.max(1, bytes.length));

        CoderResult result = decoder.decode(input, output, true);
        if (result.isError()) {
            System.out.printf(
                    "UTF-8 error at byte offset %d, length %d%n",
                    input.position(), result.length());
            result.throwException();
        }
        if (result.isOverflow()) {
            throw new AssertionError("Unexpected UTF-8 output overflow");
        }

        result = decoder.flush(output);
        if (result.isError()) {
            result.throwException();
        }
        if (result.isOverflow()) {
            throw new AssertionError("Unexpected decoder flush overflow");
        }

        output.flip();
        return output.toString();
    }

    private static void respond(
            HttpExchange exchange, int status, byte[] bytes)
            throws IOException {

        try {
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/json; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);

            try (OutputStream body = exchange.getResponseBody()) {
                body.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }
}
~~~

### Biên dịch và chạy

Từ thư mục chứa `HttpPathLab.java`:

~~~sh
javac --add-modules jdk.httpserver,java.net.http HttpPathLab.java
java --add-modules jdk.httpserver,java.net.http HttpPathLab
~~~

`jdk.httpserver` cung cấp `HttpServer`, còn `java.net.http` cung cấp `HttpClient`. Việc nêu rõ các module trong lệnh giúp người học thấy chính xác API thuộc module nào.

Server được tạo, chọn cổng, phục vụ các request thử nghiệm rồi dừng trong `finally`. Không cần sửa tệp hosts, cấu hình DNS công cộng hoặc mở quyền mạng ra ngoài máy.

### Ghi chú về mã mẫu

- Mỗi response gửi một body có số byte xác định; `sendResponseHeaders(status, bytes.length)` nhận **số byte**, không phải độ dài ký tự Java.
- Đoạn client thu `byte[]` trước khi giải mã, nên có thể phân biệt lỗi truyền dữ liệu hoặc encoding với nội dung đã biến đổi.
- Ví dụ dùng `String`, `CharBuffer` và `byte[]` trong bộ nhớ, chỉ thích hợp cho response có kích thước nhỏ/vừa. Với response lớn phải dùng streaming.
- Code kiểm tra nội dung chính xác của endpoint `/health` bằng so sánh chuỗi; trong ứng dụng thật cần kiểm tra cấu trúc JSON bằng parser và schema thích hợp.
- `HttpClient` có thể tái sử dụng connection; không khẳng định TCP probe là cùng connection mà HTTP client dùng.
- Kiểm tra `contains("charset=utf-8")` chỉ dành cho header cố định của lab. Trong ứng dụng thật cần phân tích tham số `Content-Type` đúng cú pháp (kể cả dấu nháy và khoảng trắng), rồi áp dụng quy tắc charset của media type.
- Nếu resolver của máy không phân giải được `localhost`, lab ghi cảnh báo nhưng vẫn tiếp tục dùng IP literal `127.0.0.1`. Nếu môi trường ép HTTP proxy, phải xác minh quy tắc bỏ qua proxy cho loopback trước khi xem lỗi request là lỗi server.

## 6. Đọc kết quả theo từng bước

Một lần chạy thành công có các nhóm thông tin sau; địa chỉ `localhost` và số cổng được hệ điều hành chọn sẽ khác nhau giữa các máy:

~~~text
Resolution of localhost:
  127.0.0.1
  ...

=== http://127.0.0.1:<port>/health ===
URI: scheme=http, host=127.0.0.1, port=<port>, path=/health
Address candidate: 127.0.0.1
TCP probe connected to /127.0.0.1:<port>
HTTP version: HTTP_1_1
HTTP status: 200
Content-Type: application/json; charset=utf-8
Body bytes: ...
Body prefix (hex): ...
Decoded UTF-8: {"ok":true,"message":"Xin chào"}
Expected lab result verified
~~~

Dòng `Resolution of localhost` có thể chứa `::1` trước hoặc sau `127.0.0.1`. Đây không phải lỗi. Trong lab, URL dùng IP literal `127.0.0.1` để tránh phụ thuộc việc `localhost` ưu tiên IPv4 hay IPv6.

Kết quả ba endpoint còn lại có ý nghĩa:

| Endpoint | Kết luận đúng |
| --- | --- |
| `/not-found` → `404` với UTF-8 hợp lệ | DNS/TCP/HTTP đã đi qua, nhưng tài nguyên được hỏi không có. |
| `/unready` → `503` với UTF-8 hợp lệ | Server có thể trả HTTP, nhưng tầng ứng dụng không sẵn sàng. |
| `/bad-utf8` → `200` và `MalformedInputException` | HTTP status không bảo đảm body hợp lệ; lỗi thuộc encoding/content. |

Chú ý `200` của `/bad-utf8` vẫn là status thành công của HTTP. Chương trình chủ động kết luận **không đạt hợp đồng nội dung** vì byte `E2 82` chưa hoàn chỉnh khi body đã kết thúc.

## 7. Kiểm tra hostname và danh sách địa chỉ thực tế

Với dịch vụ thật, bước đầu là phân tích URI và lấy danh sách địa chỉ hiện tại:

~~~java
URI uri = URI.create("https://service.example.com/health");

String host = uri.getHost();
int port = uri.getPort() == -1 ? 443 : uri.getPort();

InetAddress[] addresses = InetAddress.getAllByName(host);
for (InetAddress address : addresses) {
    System.out.println(address.getHostAddress());
}
~~~

Với hostname, `InetAddress.getAllByName` sử dụng resolver hiện hành của JVM. Kết quả có thể chịu ảnh hưởng bởi:

- Bản ghi IPv4/IPv6 và thứ tự được resolver trả về.
- Hosts file và cấu hình DNS của máy.
- Caching kết quả phân giải của `InetAddress`.
- Resolver provider tùy biến qua cơ chế `InetAddressResolverProvider` nếu ứng dụng có cấu hình này.
- Cấu hình hệ điều hành và hạ tầng mạng nơi chương trình đang chạy.

Không kết luận “DNS đúng” chỉ vì danh sách IP không rỗng. Cần so sánh với địa chỉ/hạ tầng dự kiến; một bản ghi DNS **hợp lệ về cú pháp** vẫn có thể chỉ tới server sai.

### Kết quả phân giải có thể được cache

`InetAddress` cache cả kết quả phân giải thành công lẫn thất bại. Các security property như `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` ảnh hưởng thời hạn cache tùy JVM/cấu hình.

Nếu bản ghi DNS vừa thay đổi nhưng process Java chưa nhìn thấy kết quả mới, kiểm tra cache và môi trường thực tế. Không suy ra rằng mỗi lần gọi `getAllByName` chắc chắn truy vấn DNS ra mạng.

### Hostname trong URI và reverse lookup là hai việc khác nhau

`InetAddress.getHostName()` hoặc `getCanonicalHostName()` không thay thế kiểm tra IP mục tiêu. Reverse lookup có thể không có kết quả hoặc trả tên khác với hostname gốc. Để xác minh request, ưu tiên ghi **hostname trong URI** và **IP candidates** mà resolver cung cấp; reverse DNS chỉ là thông tin bổ trợ.

## 8. TCP probe giúp thu hẹp lỗi, nhưng không thay thế HTTP

Mã kiểm tra kết nối TCP:

~~~java
InetAddress target = InetAddress.getByName("127.0.0.1");

try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(target, 8080), 1500);
    System.out.println(socket.getRemoteSocketAddress());
}
~~~

Thành công nghĩa là **kết nối TCP trực tiếp của probe** tới IP/cổng đó được thiết lập. Nó không chứng minh:

- HTTP server đọc và xử lý request đúng.
- HTTP server chọn virtual host phù hợp.
- TLS handshake/certificate đúng khi dùng HTTPS.
- `HttpClient` đã dùng đúng IP mà probe dùng.
- Nội dung response có đúng status, encoding hoặc schema.

### Vì sao TCP probe khác kết nối của HttpClient?

`HttpClient` có thể có:

- Proxy selector hoặc proxy được cấu hình.
- Cơ chế chọn IP, retry hoặc kết nối lại khác probe.
- Pool connection đang tồn tại từ request trước.
- TLS handshake, SNI và kiểm tra chứng chỉ cho HTTPS.
- Redirect nếu client cho phép đi theo redirect.

Probe `Socket` ở bài học tạo **kết nối trực tiếp** tới địa chỉ IP đã chọn. Nó là một quan sát bổ sung; không nên gọi `socket.getRemoteSocketAddress()` là “địa chỉ remote của request HttpClient” khi không có bằng chứng kết nối hai đối tượng cùng nhau.

Nếu cần địa chỉ peer thực sự của request, hãy dùng log phía server, logging mạng, trace của client/transport hoặc công cụ quan sát kết nối thích hợp. API `HttpResponse` chuẩn không cung cấp một thuộc tính đơn giản bảo đảm phản ánh socket peer cho mọi implementation.

## 9. Kiểm tra HTTP status, header và body như ba hợp đồng riêng

Sau khi `HttpClient.send(...)` thành công, ứng dụng có:

~~~java
int status = response.statusCode();
String contentType = response.headers()
        .firstValue("Content-Type").orElse("<missing>");
byte[] body = response.body();
~~~

Cần kiểm tra cả ba:

### 9.1. Status

- `200`: request được xử lý thành công theo semantics của endpoint, nhưng **không** chứng minh body đúng.
- `301`, `302`, `307`, `308`: redirect; xem `Location` và chính sách redirect của client.
- `400`: request không hợp lệ theo hợp đồng server.
- `401`: cần xác thực hợp lệ.
- `403`: server từ chối quyền truy cập.
- `404`: không có tài nguyên tương ứng ở URL này.
- `429`: giới hạn tần suất.
- `500`: server gặp lỗi khi xử lý.
- `502` hoặc `504`: gateway/proxy gặp lỗi với upstream.
- `503`: dịch vụ không sẵn sàng, quá tải hoặc đang bảo trì.

Không phải mọi `5xx` đều chứng minh DNS/client sai. Ngược lại, nhận được `404` nghĩa là có một HTTP server đã trả lời, nhưng vẫn có khả năng bạn đang gọi sai hostname/virtual host/path.

### 9.2. Header

Với JSON UTF-8, header thường gặp:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Content-Length: 33
~~~

Đây là **ví dụ dạng header** cho body `{\"ok\":true,\"message\":\"Xin chào\"}` với 33 byte UTF-8; đừng xem `Content-Length: 33` là số byte bắt buộc của mọi response. Hãy dùng kích thước byte thực tế để xác minh, vì ký tự nhiều byte khiến `String.length()` khác byte length.

Các điểm cần hỏi:

- `Content-Type` có đúng media type không?
- Nếu header khai báo `charset`, charset đó có khớp hợp đồng không?
- Có `Content-Encoding: gzip` hoặc cách nén khác không? Nếu có, phải giải nén theo semantics trước khi giải mã ký tự.
- Response có `Location` vì redirect không?
- Có header của proxy, cache hoặc gateway cho thấy request đi qua tầng trung gian không?
- Nếu `Content-Length` vắng mặt, body có thể được truyền bằng cơ chế khác như chunked transfer; **thiếu header này không tự động là lỗi**.

### 9.3. Body bytes

Khi cần kiểm chứng encoding, nhận byte trước:

~~~java
HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

byte[] bytes = response.body();
System.out.println(HexFormat.of().formatHex(
        bytes, 0, Math.min(bytes.length, 24)));
~~~

Ưu điểm:

- Có thể lưu phần đầu ở dạng hex khi cần chẩn đoán.
- Có thể kiểm tra byte bị cắt cụt hoặc sai UTF-8.
- Không vô tình biến lỗi byte thành `U+FFFD` khi đã giải mã thay thế.
- Có thể phân biệt lỗi transport/content-length với lỗi parser JSON.

`BodyHandlers.ofString()` thuận tiện cho trường hợp thông thường, nhưng không phải công cụ đầu tiên để kiểm chứng byte-level integrity. Với dữ liệu chẩn đoán, `ofByteArray()` và decoder có `REPORT` giúp bảo toàn bằng chứng.

## 10. Kiểm chứng UTF-8 không đồng nghĩa kiểm chứng JSON

Với response JSON, các tầng kiểm tra có thể tách như sau:

| Kiểm tra | Ví dụ | Lỗi phát hiện |
| --- | --- | --- |
| Byte length / body tồn tại | `response.body().length` | Body rỗng/truncated so với hợp đồng. |
| Decode UTF-8 strict | `CharsetDecoder.onMalformedInput(REPORT)` | Byte sequence không hợp lệ. |
| Parse JSON | Parser JSON phù hợp | Dấu ngoặc, dấu phẩy, chuỗi/number sai cú pháp. |
| Validate schema | Trường `ok` phải là boolean, `message` phải là string | JSON hợp lệ nhưng không đúng cấu trúc. |
| Validate nghiệp vụ | `ok=true` và thông báo kỳ vọng | Cấu trúc đúng nhưng nội dung sai. |

Trong lab, endpoint `/health` được kiểm tra bằng so sánh với chuỗi JSON kỳ vọng do chính server cung cấp. Với API thật, đừng so sánh chuỗi JSON thuần để suy ra tương đương ngữ nghĩa: thứ tự property, whitespace và escaping có thể khác dù JSON vẫn biểu diễn cùng dữ liệu.

Thư viện JSON chuyên dụng giúp parse/schema validation; Java SE không cung cấp sẵn một JSON parser tổng quát tương đương các thư viện chuyên dụng. Không cố biến `String.contains("ok")` thành một phép kiểm tra hợp đồng JSON đáng tin cậy.

### Mã hóa mặc định không quyết định mã hóa HTTP

JEP 400 làm UTF-8 trở thành default charset cho nhiều Java SE API kể từ JDK 18, nhưng **không** có nghĩa mọi HTTP endpoint trên Internet đều gửi UTF-8. Hợp đồng HTTP do server, media type và header quyết định.

Nếu ứng dụng yêu cầu UTF-8, hãy ghi rõ yêu cầu trong giao thức và dùng `StandardCharsets.UTF_8`. Nếu server gửi header khai báo charset khác, đừng tự gắn nhãn “UTF-8 đúng” trước khi xem dữ liệu và hợp đồng; có thể đó là lỗi content negotiation hoặc cấu hình server.

## 11. Timeout, proxy, redirect và TLS: thêm các biến chẩn đoán

### Connect timeout khác request timeout

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example.com/health"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

- `connectTimeout` áp dụng cho **pha thiết lập kết nối mới**; nếu connection đã được tái sử dụng, timeout đó không có cùng tác dụng.
- `HttpRequest.timeout` đặt thời hạn hoàn tất request theo hợp đồng HTTP client.
- `HttpConnectTimeoutException` gợi ý không hoàn tất pha thiết lập kết nối trong giới hạn.
- `HttpTimeoutException` gợi ý request không hoàn tất đúng hạn, không tự chứng minh DNS sai.
- `ConnectException`, `UnknownHostException` hoặc các nguyên nhân lồng nhau cần được xem theo ngữ cảnh.

Đừng gộp mọi trường hợp “chờ lâu” thành DNS timeout. Phải ghi giai đoạn phát sinh và các exception/cause liên quan.

### Proxy có thể thay đổi đường đi

Nếu HTTP client dùng proxy, client có thể kết nối TCP tới **proxy**, không trực tiếp tới IP của hostname đích. Resolver của máy khách và resolver của proxy có thể khác nhau. Vì vậy, phép gọi `InetAddress.getAllByName(host)` tại client là bằng chứng về kết quả phân giải của **máy đó**, không bảo đảm proxy dùng cùng địa chỉ.

Khi so sánh kết quả với `curl` hoặc trình duyệt, ghi cả proxy settings, VPN, DNS và container namespace. Hai công cụ dùng hai đường đi mạng khác nhau có thể cho kết quả khác nhau mà không mâu thuẫn.

### HTTPS cần kiểm chứng riêng

Với HTTPS:

1. URI có hostname và cổng đích.
2. Client có thể phải phân giải tên và mở kết nối TCP.
3. TLS handshake diễn ra, bao gồm xác thực chứng chỉ theo hostname.
4. Sau đó mới có HTTP request/response ở tầng ứng dụng.

Nếu nhận `SSLHandshakeException`, đừng sửa bằng cách vô hiệu hóa hostname verification hoặc tin cậy mọi chứng chỉ. Hãy kiểm tra hostname trong URL, SAN của chứng chỉ, trust store, ngày hiệu lực, certificate chain và endpoint TLS thực sự được chọn.

Một phép TCP connect tới `443` thành công **không** phải bằng chứng rằng HTTPS đã thành công.

## 12. JDK 18 Simple Web Server: lựa chọn tối giản để xác minh file HTTP

JDK 18 giới thiệu công cụ `jwebserver` (JEP 408) để dựng HTTP static file server phục vụ thử nghiệm. Khi không cần endpoint động để trả `503` hay byte hỏng, có thể dùng nó để kiểm tra hostname, bind address, port và nội dung một tệp tĩnh.

Ví dụ trên terminal Linux/macOS:

~~~sh
mkdir -p webroot
printf 'Xin chào Java 18!\n' > webroot/hello.txt
jwebserver -b 127.0.0.1 -p 8000 -d webroot
~~~

Ở terminal khác:

~~~sh
curl -i http://127.0.0.1:8000/hello.txt
curl -v http://127.0.0.1:8000/missing.txt
~~~

Trên Windows PowerShell, có thể tạo thư mục/tệp bằng các lệnh tương ứng và dùng `curl.exe` để tránh nhầm với alias của một số phiên bản PowerShell.

Lưu ý:

- `jwebserver` chỉ phục vụ nội dung tĩnh theo khả năng của công cụ; không thay thế ứng dụng HTTP đầy đủ.
- Hỗ trợ GET/HEAD cho nhu cầu thử nghiệm; không dùng nó để suy ra semantics của API động.
- Công cụ mặc định bind loopback; chỉ đổi bind address khi thực sự cần và đã xem xét quyền truy cập mạng.
- Để tái hiện response 503 hoặc byte body không hợp lệ một cách có kiểm soát, dùng `HttpServer` như chương trình lab.

## 13. Quy trình chẩn đoán một lỗi thực tế

Giả sử ứng dụng báo:

~~~text
Cannot fetch health information from https://service.example.com/health
~~~

Thay vì thử thay URL hoặc sửa cấu hình ngẫu nhiên, đi theo thứ tự:

1. **Chụp trạng thái đầu vào:** hostname, scheme, cổng, path, môi trường chạy, JDK, thời điểm và cấu hình proxy. Không ghi token/password vào log.
2. **Kiểm tra URI:** có viết nhầm `http` thành `https`, thiếu cổng, sai path hoặc có redirect ngoài dự kiến không?
3. **Kiểm tra resolver:** `InetAddress.getAllByName(host)` trả IPv4/IPv6 nào? Các địa chỉ có thuộc hạ tầng mong đợi không?
4. **Kiểm tra TCP trực tiếp khi phù hợp:** thử từng IP/port và ghi địa chỉ thực sự probe kết nối được. Không đồng nhất với đường đi proxy.
5. **Kiểm tra TLS:** với HTTPS, ghi lỗi handshake/chứng chỉ chính xác, không bỏ qua xác thực.
6. **Kiểm tra HTTP:** gửi GET với timeout cụ thể, tạm thời không tự theo redirect, ghi status, `Content-Type` và `Location` nếu có.
7. **Kiểm tra body bytes:** số byte, prefix hex giới hạn và `Content-Encoding`. Không in toàn bộ body khi chứa thông tin riêng tư.
8. **Giải mã đúng charset:** với API quy định UTF-8, dùng strict decoder; nếu lỗi, báo byte offset và số byte lỗi.
9. **Kiểm tra dữ liệu:** parse JSON, validate schema/giá trị nghiệp vụ; không coi status `200` là đủ.
10. **Khoanh vùng component:** client resolver, mạng, proxy/LB, server, content encoder hoặc logic ứng dụng. Đưa ra bằng chứng cho giả thuyết trước khi thay cấu hình.
11. **Chạy lại sau sửa:** xác nhận cả status, body và điều kiện nghiệp vụ; đối chiếu với log server/correlation ID khi có.

## 14. Bảng định vị lỗi liên thành phần

| Hiện tượng | Tầng nghi vấn | Bằng chứng cần lấy | Hành động tiếp theo |
| --- | --- | --- | --- |
| `uri.getHost() == null` | Cú pháp URI | URI/scheme/authority | Sửa URI hợp lệ trước khi chẩn đoán mạng. |
| `UnknownHostException` | Resolver/hostname | Tên host, cấu hình DNS/hosts, resolver context | Kiểm tra tên, bản ghi, cache và mạng nội bộ. |
| Có IP nhưng TCP `Connection refused` | TCP/port/service bind | IP:port cụ thể, process listen | Kiểm tra cổng, địa chỉ bind và service readiness. |
| TCP timeout | Route/firewall/filter/service | IP, port, timeout, path mạng | Kiểm tra đường đi mạng; không vội kết luận DNS. |
| TCP probe thành công, HTTP client thất bại | HTTP client/proxy/TLS/route khác | Proxy, TLS errors, request URI, HTTP logs | So sánh đường đi thực tế, không giả định hai kết nối giống nhau. |
| HTTPS báo `SSLHandshakeException` | TLS/trust/hostname | Certificate chain, SAN, trust store | Sửa chứng chỉ/cấu hình trust, không tắt validation. |
| HTTP `301/302/307/308` | Redirect | `Location` và chính sách follow | Kiểm tra endpoint cuối, scheme và host đích. |
| HTTP `401/403` | Authentication/authorization | Status, auth scope, policy | Kiểm tra quyền, không in bí mật vào log. |
| HTTP `404` | Route/virtual host/path | URL, `Host`/authority, server routing | Kiểm tra endpoint chính xác; TCP không phải vấn đề chính. |
| HTTP `502/504` | Gateway/upstream | Gateway trace, upstream address/status | Chẩn đoán kết nối gateway tới backend. |
| HTTP `503` | Service readiness/capacity | Server logs/health checks | Kiểm tra trạng thái ứng dụng, phụ thuộc downstream. |
| HTTP `200` nhưng byte UTF-8 sai | Content encoding/generation | Hex body, strict decoder byte offset | Sửa encoder hoặc quá trình cắt/gom dữ liệu. |
| HTTP `200`, UTF-8 đúng nhưng JSON sai | Serialization/content schema | JSON parser errors, schema | Sửa trả dữ liệu hoặc hợp đồng client/server. |
| Một số máy lỗi, số khác không | DNS cache/IPv4-IPv6/proxy/load balancer | IP candidates và route của từng máy | So sánh môi trường trước khi sửa ứng dụng. |

## 15. Kiểm chứng trên CI và môi trường triển khai

Một kiểm thử liên thành phần tốt không chỉ gọi một endpoint rồi assert `statusCode() == 200`. Nó cần kiểm tra các bất biến chính:

~~~text
[ ] URI có scheme/host/path/cổng đúng
[ ] Dịch vụ bind và client kết nối đúng address family
[ ] TCP hoạt động tới địa chỉ/cổng dự kiến
[ ] Status thuộc tập được hợp đồng cho phép
[ ] Header Content-Type/Content-Encoding hợp lệ
[ ] Byte response không bị cắt, sai framing hoặc sai encoding
[ ] Body giải mã thành công với charset quy định
[ ] Nội dung parse/schema/giá trị nghiệp vụ đúng
[ ] Lỗi 404/503/malformed bytes được phát hiện đúng tầng
[ ] Không rò rỉ token, cookie hoặc payload bí mật trong log chẩn đoán
~~~

Với lab `HttpPathLab`, bốn endpoint đã cho phép kiểm tra ba điều kiện rất khác nhau: HTTP success, HTTP application error và HTTP success nhưng encoding error.

Trong CI:

- Sử dụng địa chỉ loopback và cổng động để tránh xung đột giữa test jobs.
- Có timeout cho cả kết nối và request.
- Luôn dừng server và đóng tài nguyên khi test hoàn tất.
- Phân biệt test mạng cục bộ với test integration qua DNS/proxy/load balancer thật.
- Ghi phiên bản JDK đang chạy, vì resolver, network policy và HTTP implementation có thể bị cấu hình khác nhau.
- Không hard-code IP của dịch vụ production vào test đơn vị; hệ thống triển khai có thể thay đổi địa chỉ.

## 16. Bảo mật và giới hạn của công cụ chẩn đoán

Một công cụ tự động nhận URL do người dùng cung cấp có thể bị lạm dụng để gửi request tới mạng nội bộ (*server-side request forgery*, SSRF). Nếu triển khai bộ kiểm tra hostname/HTTP như một service, phải kiểm soát nguồn URL, hostname, IP được phép, redirect, proxy và chính sách egress.

Trong lab, ta cố định `127.0.0.1`, tạo một server thuộc chính tiến trình test và không gửi dữ liệu ra ngoài. Khi chuyển sang môi trường thật:

- Chỉ probe những endpoint bạn được phép kiểm tra.
- Không tự mở cổng lắng nghe `0.0.0.0` chỉ vì muốn thử nhanh.
- Không log `Authorization` header, cookie, query chứa token hoặc toàn bộ payload nhạy cảm.
- Chỉ in phần hex prefix đủ để chẩn đoán, kết hợp masking và retention policy phù hợp.
- Không tắt xác thực TLS để “làm cho request chạy được”.
- Không coi thành công khi kết nối TCP đến một cổng là sự xác nhận danh tính server.

## 17. Bài tập thực hành

### Bài tập 1: Đọc đúng hostname và cổng

Với các URI:

~~~text
http://localhost:8000/index.html
https://service.example.com/health
http://127.0.0.1:9000/api/status
~~~

Xác định `scheme`, `host`, `port` thực tế và `path`. Với URI không có cổng tường minh, sử dụng mặc định HTTP/HTTPS đúng. Dùng `URI`, không tự dùng `String.split(":")` vì IPv6 và phần scheme có dấu hai chấm.

### Bài tập 2: Phân biệt localhost và IP loopback

Chạy `InetAddress.getAllByName("localhost")`, ghi IPv4/IPv6 được trả về. Giữ server bind `127.0.0.1` rồi thử đổi request sang hostname `localhost`. Nếu có sai khác giữa IPv4 và IPv6, giải thích tác động của address family và địa chỉ bind.

### Bài tập 3: Sai cổng

Khởi chạy lab, ghi cổng động được cấp, thử một request tới cổng khác mà bạn biết không có service. Ghi exception chính xác. Không khẳng định một cổng tùy ý luôn đóng: hệ thống có thể đang có một process khác lắng nghe.

### Bài tập 4: Status khác encoding

Chạy cả bốn endpoint và lập bảng ba cột: HTTP status, byte body hợp lệ UTF-8 hay không, nội dung nghiệp vụ đúng hay không. Giải thích vì sao `/bad-utf8` trả `200` mà vẫn là lỗi dữ liệu.

### Bài tập 5: Header sai nhưng byte hợp lệ

Sửa endpoint `/health` để trả `text/plain` dù body vẫn là JSON UTF-8. Tạo check về `Content-Type` trong client. Kết luận HTTP có thể thành công nhưng vi phạm hợp đồng media type.

### Bài tập 6: Giả lập JSON không hợp lệ

Trả body UTF-8 hợp lệ như `{"ok": tru}`. Giữ status `200` và `Content-Type: application/json`. Dùng một JSON parser của dự án để phát hiện lỗi cú pháp. Phân biệt rõ lỗi UTF-8 với lỗi JSON parsing.

### Bài tập 7: Thử jwebserver

Tạo tệp `hello.txt` chứa tiếng Việt trong thư mục tĩnh và chạy `jwebserver` trên loopback. Dùng `curl -i` để kiểm tra status, header và body, sau đó thử path không tồn tại. So sánh khả năng của static file server với lab `HttpServer` trả các trạng thái động.

### Bài tập 8: Chẩn đoán HTTPS

Trong môi trường test được cấp quyền, gọi một HTTPS endpoint có chứng chỉ hợp lệ và một endpoint lỗi certificate do nhóm tự kiểm soát. Ghi nguyên nhân TLS handshake; không vô hiệu hóa hostname/certificate verification. Giải thích vì sao TCP thành công không có nghĩa HTTPS thành công.

### Bài tập 9: Viết báo cáo sự cố

Tạo báo cáo ngắn gồm: URI, thời điểm, môi trường JVM, hostname, IP candidates, TCP probe result, HTTP status, Content-Type, body length, UTF-8 validity và kết luận tầng lỗi. Phân biệt điều đã **đo được** với giả thuyết cần kiểm chứng thêm.

## 18. Ghi nhớ

- **Bắt đầu từ URI:** hostname, địa chỉ IP, cổng và path là các thành phần khác nhau.
- **DNS thành công không bảo đảm TCP thành công.** `InetAddress.getAllByName` cho danh sách IP candidates, không cho kết quả kết nối.
- **TCP thành công không bảo đảm HTTP thành công.** Địa chỉ bind, proxy, virtual host, TLS và routing vẫn có thể khác.
- **TCP probe không phải peer chắc chắn của `HttpClient`.** Hai thao tác có thể dùng đường đi mạng khác nhau.
- **Status HTTP không bảo đảm nội dung đúng.** `200` vẫn có thể trả byte UTF-8 sai, JSON không hợp lệ hoặc giá trị nghiệp vụ sai.
- **Giữ byte gốc khi cần chẩn đoán mã hóa.** Dùng `BodyHandlers.ofByteArray()` và `CharsetDecoder` với `REPORT`.
- **UTF-8 mặc định từ JDK 18 không thay thế hợp đồng HTTP.** Charset của payload phải được xác định rõ theo API/media type.
- **JDK 18 có `jwebserver` để test file tĩnh.** Với endpoint động và các lỗi có chủ đích, `HttpServer` phù hợp hơn.
- **Đo theo tầng và ghi bằng chứng.** Chỉ kết luận component gây lỗi sau khi đã phân biệt được resolver, TCP, TLS, HTTP và content/application.

## Tài liệu chính thống

- [Oracle Java SE 27 — InetAddress: Host Name Resolution, getAllByName và caching](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html).
- [Oracle Java SE 27 — Socket.connect và InetSocketAddress](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/Socket.html).
- [Oracle Java SE 27 — HttpClient và thời hạn kết nối](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Oracle Java SE 27 — HttpResponse.BodyHandlers.ofByteArray](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [Oracle Java SE 27 — HttpRequest và timeout](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Oracle Java SE 27 — HttpServer API (module jdk.httpserver)](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html).
- [Oracle Java SE 27 — CharsetDecoder và CodingErrorAction.REPORT](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [OpenJDK — JEP 408: Simple Web Server](https://openjdk.org/jeps/408).
- [Oracle Java SE 18 — jwebserver Command](https://docs.oracle.com/en/java/javase/18/docs/specs/man/jwebserver.html).

