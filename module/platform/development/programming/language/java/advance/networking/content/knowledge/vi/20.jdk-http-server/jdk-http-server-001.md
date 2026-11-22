# Module jdk.httpserver và khả năng của HttpServer, HttpsServer (Java 17+)

Java SE 17 có module **`jdk.httpserver`**, cung cấp API HTTP server nhúng, nhỏ gọn và nằm ngay trong JDK. Module xuất package `com.sun.net.httpserver` với hai lớp trọng tâm: **`HttpServer`** để nhận HTTP/1.1 trên TCP và **`HttpsServer`** để nhận HTTP/1.1 qua TLS (HTTPS). Cùng với `HttpHandler`, `HttpExchange` và `HttpContext`, bạn có thể đăng ký endpoint, đọc request, tạo status/headers/body và điều phối worker threads mà không cài thêm web framework.

Mục tiêu của bài:

1. Hiểu module `jdk.httpserver`, phân biệt nó với **`java.net.http`** (HTTP client).
2. Biết tạo/bind/start/stop `HttpServer`, đăng ký `HttpContext` và hiểu **longest literal prefix matching** thay vì tự động routing REST.
3. Nắm vòng đời của một `HttpExchange`, đặc biệt là stream và quy tắc `sendResponseHeaders(status, length)` với **length >0, =0, <0**.
4. Xây server xử lý GET/POST, trả 405/404 đúng và tránh đọc body không giới hạn.
5. Biết dùng executor, filters và authorization riêng; hiểu backlog **không phải** concurrency limit.
6. Hiểu `HttpsServer` cần `HttpsConfigurator` gắn `SSLContext` có server identity key, chứng chỉ, và cách client tin cậy server.
7. Xác định giới hạn công nghệ: đây là HTTP server nhúng **đơn giản**, không thay thế mặc định một HTTP/2/WebSocket server, servlet container hoặc framework đầy đủ.
8. Chạy và phân tích **hai chương trình Java 17+ độc lập đã kiểm thử**: một HTTP và một HTTPS loopback.

## 1. Vị trí của jdk.httpserver trong hệ module Java

| Module/package | Cung cấp | Dùng khi |
| --- | --- | --- |
| `jdk.httpserver` | Server API `HttpServer`, `HttpsServer`, `HttpExchange`, `Filter` | Tự tiếp nhận HTTP/HTTPS request trên máy đang chạy Java |
| `java.net.http` | `HttpClient`, `HttpRequest`, `HttpResponse`, WebSocket client | Gửi HTTP request tới server khác |
| `java.base/java.net` | `Socket`, `ServerSocket`, `URI`, `InetSocketAddress` | Networking cấp thấp |
| `java.base/javax.net.ssl` | `SSLContext`, `KeyManagerFactory`, `TrustManagerFactory` | TLS/certificate/trust |
| `java.base/java.security` | `KeyStore`, `SecureRandom` | Lưu khóa, chứng chỉ và tạo entropy bảo mật |

`jdk.httpserver` là **JDK-specific module** từ Java 9; nó công bố hai package `com.sun.net.httpserver` và `com.sun.net.httpserver.spi`. Dù tên package bắt đầu bằng `com.sun`, API này được JDK document chính thức; không được nhầm với các package `sun.*` nội bộ không có cam kết tương thích. Vì là module JDK-specific, các **custom runtimes tạo bằng jlink** có thể không chứa nó; phải kiểm tra trước khi triển khai.

~~~bash
java --version
java --describe-module jdk.httpserver
~~~

Nếu runtime thông báo không tìm thấy module, kiểm tra cấu hình Java/JDK và module-resolution; không giả định package đã biến mất khỏi mọi Java 17. Ứng dụng **named module** dùng file `module-info.java` như sau:

~~~java
// Fragment module-info.java cho một ứng dụng named module.
module example.embedded.server {
    requires jdk.httpserver;
    requires java.net.http; // Chỉ cần nếu app cũng dùng HttpClient.
}
~~~

Các ví dụ trong bài là **classpath applications**: lưu đúng `JdkHttpServerDemo.java` và `JdkHttpsServerDemo.java`, rồi chạy với `javac --release 17` và `java` của một JDK đầy đủ. Nếu dùng module-path/Java runtime cắt gọn, bảo đảm `jdk.httpserver` được resolve.

**Giới hạn phiên bản quan trọng:** `SimpleFileServer` và command `jwebserver` được bổ sung ở Java 18, không phải thành phần để giả định có sẵn trên Java 17. Bài dùng các API `HttpServer/HttpsServer` thực sự tồn tại ở Java 17; không yêu cầu lệnh `java -m jdk.httpserver` của Java 18+.

## 2. Thành phần của HTTP server nhúng

~~~text
HTTP client
  GET /health HTTP/1.1
          |
          v
     TCP listener
     HttpServer.start()
          |
          v
Chọn HttpContext theo path prefix dài nhất
          |
          v
Executor thực thi HttpHandler.handle(HttpExchange)
          |
          +-- getRequestMethod()
          +-- getRequestURI()
          +-- getRequestHeaders()
          +-- getRequestBody()  -> InputStream
          |
          +-- getResponseHeaders()
          +-- sendResponseHeaders(status, bodyLength)
          +-- getResponseBody() -> OutputStream
          |
          v
Đóng InputStream/OutputStream, hoàn tất exchange
          |
          v
HTTP status + response headers + body
~~~

| Class/interface | Vai trò |
| --- | --- |
| `HttpServer` | Bind địa chỉ IP và port, lắng nghe TCP, chọn handler, điều phối request |
| `HttpHandler` | Functional interface có `handle(HttpExchange) throws IOException` |
| `HttpContext` | Một ánh xạ từ root path tới handler, có filters/authenticator riêng |
| `HttpExchange` | Một request và response tương ứng, chứa method, URI, headers, body streams |
| `Headers` | Header map không phân biệt hoa/thường cho tên header |
| `Filter` / `Filter.Chain` | Middleware tiền/hậu xử lý một exchange |
| `Executor` | Thực hiện handler tasks, ảnh hưởng khả năng xử lý đồng thời |
| `HttpsServer` | Subclass của HttpServer, dùng SSLContext/TLS |
| `HttpsExchange` | Subclass của HttpExchange, thêm `getSSLSession()` |
| `HttpsConfigurator` | Cung cấp cấu hình TLS khi nhận HTTPS connections |

Một `HttpServer` **không** tự serialize/parse JSON, không tự kiểm tra token, không tự gắn endpoint với GET/POST theo tên phương thức và không tự cung cấp dependency injection, servlet API, OpenAPI hoặc hệ thống session. Những việc đó thuộc application code hoặc framework được xây trên nó.

## 3. Tạo server, bind địa chỉ và chọn executor

~~~java
// Fragment Java 17+: server chỉ lắng nghe trên loopback.
InetAddress loopback = InetAddress.getByAddress(
        new byte[] {127, 0, 0, 1});

HttpServer server = HttpServer.create(
        new InetSocketAddress(loopback, 0), 32);

server.createContext("/health", exchange -> {
    // Đọc request, gửi response và kết thúc exchange.
});

server.start();
~~~

Ý nghĩa:

- `127.0.0.1` là loopback IPv4; máy khác không truy cập được qua địa chỉ này.
- Port **0** cho hệ điều hành cấp một cổng còn trống. Lấy số thực sau bind bằng `server.getAddress().getPort()`.
- Backlog **32** là số lượng kết nối TCP chờ được accept theo cấu hình và giới hạn của OS; nó **không phải** số worker threads hoặc maximum concurrent requests. Nếu backlog ≤0, JDK dùng giá trị mặc định của hệ thống.
- Có thể dùng `HttpServer.create()` rồi `server.bind(address,backlog)` khi cần tách bước khởi tạo và bind.
- `server.start()` bắt đầu nhận kết nối trên luồng nền.

Không mở server trên mọi interface (ví dụ bind `0.0.0.0`) chỉ để kiểm thử. Khi cần remote access, hãy thiết kế firewall/authentication/TLS/quotas và policy riêng.

### Executor mặc định

Javadoc Java 17 cho biết nếu không cấu hình executor, server dùng implementation mặc định chạy handler tasks trên **thread được tạo bởi `start()`**. Handler blocking lâu có thể làm các request khác phải đợi.

~~~java
// Fragment Java 17+: thiết lập TRƯỚC khi gọi start().
ExecutorService workers = Executors.newFixedThreadPool(4);
server.setExecutor(workers);
server.start();
~~~

Không gọi `setExecutor` sau `start()`: API có thể ném `IllegalStateException`. Nhớ rằng `Executors.newFixedThreadPool(4)` chỉ cố định tối đa 4 threads, nhưng **queue mặc định không giới hạn**, không phải bảo vệ memory tối ưu cho public server. Production cần bounded queue, overload policy, request limits, deadlines và metrics. Gắn executor trước start; khi stop server, ứng dụng vẫn phải shutdown executor **do chính mình tạo**.

## 4. Đăng ký path bằng createContext: tiền tố dài nhất

`HttpServer.createContext(String path,HttpHandler handler)` dùng root path làm **tiền tố so khớp nguyên văn (literal prefix)** và chọn context có **tiền tố dài nhất** trong những context khớp. So sánh **phân biệt hoa/thường**, không tự encode/decode ký tự theo nghĩa một router REST.

~~~java
// Fragment: handler instances đã được cung cấp.
server.createContext("/", rootHandler);
server.createContext("/api/", apiHandler);
server.createContext("/api/users/", usersHandler);
~~~

| Request path | Context phù hợp |
| --- | --- |
| `/api/users/17` | `/api/users/` |
| `/api/orders/7` | `/api/` |
| `/hello` | `/` |
| `/API/users/17` | Không khớp `/api/` do khác case, nếu có `/` thì fallback về đó |
| `/api` | Không khớp `/api/` (thiếu slash cuối); nếu có `/` thì fallback |

**Cảnh báo:** Nếu tạo context `"/foo"` không có slash cuối, **`"/foobar"` cũng khớp**, bởi đây là prefix match chứ không phải path-segment match. Javadoc khuyến nghị context path thường kết thúc bằng `/`. Đối với endpoint cụ thể như `"/health"`, handler nên kiểm tra `exchange.getRequestURI().getPath().equals("/health")` nếu muốn exact path.

Nếu không có context nào khớp, built-in server tự trả **404 Not Found**. Nhưng nếu context khớp mà method GET/POST không được handler cho phép, server **không tự** tạo 405: handler phải kiểm tra `exchange.getRequestMethod()` và trả **405 Method Not Allowed** cùng `Allow` phù hợp.

Không dùng literal `"/users/{id}"` như thể JDK sẽ tự phân tích `id`; việc trích xuất path/query variables cần code riêng, parser riêng hoặc framework cấp trên.

## 5. Vòng đời HttpExchange và stream ownership

Một HTTP request/response được gói vào `HttpExchange`. Javadoc chỉ rõ vòng đời điển hình:

1. Đọc `getRequestMethod()` để quyết định method có được phép.
2. Dùng `getRequestHeaders()` nếu cần kiểm tra Content-Type, Authorization, Accept, length, v.v.
3. Đọc `getRequestBody()` là `InputStream` và đóng nó đúng lúc; body có thể rỗng.
4. Thiết lập headers qua `getResponseHeaders()` **trước khi gửi**.
5. Gọi `sendResponseHeaders(status,responseLength)` trước khi ghi response body.
6. Ghi bytes tới `getResponseBody()` và **đóng OutputStream** để hoàn tất exchange.

Một handler đơn giản:

~~~java
// Fragment Java 17+, exchange được truyền vào handle(...).
try (exchange) {
    String method = exchange.getRequestMethod();
    URI uri = exchange.getRequestURI();
    Headers requestHeaders = exchange.getRequestHeaders();

    try (InputStream requestBody = exchange.getRequestBody()) {
        // Đọc có giới hạn, validate và xử lý dữ liệu.
    }

    byte[] bytes = "OK".getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=UTF-8");
    exchange.sendResponseHeaders(200, bytes.length);
    try (OutputStream responseBody = exchange.getResponseBody()) {
        responseBody.write(bytes);
    }
}
~~~

Đây là **fragment**, cần import/class và không tự chạy độc lập. `HttpExchange` implements `AutoCloseable`, nên `try(exchange)` hợp lệ trên Java 17. Tuy nhiên, chỉ gọi `close()` mà chưa gửi headers/body không phải cách xây một response hợp lệ. Nếu handler ném exception sau khi đã gửi response headers, thường **không thể an toàn thay đổi status thành 500** nữa; cần ghi lỗi nội bộ và đóng/hủy exchange theo policy.

### Request Headers và Response Headers

`getRequestHeaders()` là map request headers đọc từ phía client. `getResponseHeaders()` là map có thể ghi trước khi gửi status/headers; tên header không phân biệt hoa/thường. Có thể thêm:

~~~java
exchange.getResponseHeaders().set(
        "Content-Type", "application/json; charset=UTF-8");
exchange.getResponseHeaders().set("Cache-Control", "no-store");
~~~

Đặt `Content-Type` đúng với **body trả về**, không phải request body. Không tự gửi thông tin nhạy cảm, header injection hoặc thông điệp lỗi chứa stack trace. Nếu ứng dụng nhận nhiều giá trị cho cùng một header, hãy xử lý đúng semantics của field đó, không giả định mọi header đều đơn trị.

### ResponseLength: trường hợp >0, =0 và -1

`sendResponseHeaders(int status,long responseLength)` là một API dễ dùng sai:

| responseLength | Hành vi theo JDK 17 | Ví dụ |
| --- | --- | --- |
| **> 0** | Body có chiều dài **cố định, chính xác n byte**; phải ghi đủ byte | `sendResponseHeaders(200, payload.length)` |
| **= 0** | Dùng **chunked transfer encoding** (HTTP/1.1), dữ liệu gửi theo chunks cho tới khi đóng OutputStream | Body streaming chưa biết trước độ dài |
| **<= -1** | Không gửi response body | 204 No Content, hoặc response không có body phù hợp |

**Không nhầm `sendResponseHeaders(200,0)` với Content-Length: 0.** Giá trị 0 ở API này chọn chunked encoding, không phải biểu diễn “body rỗng”. Với các status/method không cho phép body như 204/HEAD, phải theo semantics HTTP và chỉ định length hợp lệ (thường -1 cho no body).

Với length > 0, **ghi thiếu byte có thể gây IOException khi OutputStream.close()**, ghi thừa cũng có thể lỗi, và TCP connection bị hủy. Mọi length là **số byte**, không phải số ký tự trong Java String:

~~~java
// Fragment: UTF-8 có ký tự đa byte, không dùng message.length().
String message = "Xin chào";
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, payload.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(payload);
}
~~~

`OutputStream.close()` làm kết thúc exchange và cũng đóng input stream nếu chưa đóng. Tuy nhiên đọc hết request input khi hợp lý vẫn được khuyến nghị vì **đóng input quá sớm có thể làm TCP connection không tái sử dụng được**. Không đọc vô hạn body độc hại chỉ để “cứu reuse”: giới hạn, trả 413/hủy theo policy là ưu tiên.

### Đọc body có giới hạn

Một HTTP server chạy trên Internet **không nên** dùng `input.readAllBytes()` vô giới hạn. Mẫu đếm byte:

~~~java
// Fragment trong handler, tối đa 4 KiB request body.
final int maxBytes = 4096;
ByteArrayOutputStream body = new ByteArrayOutputStream();
try (InputStream input = exchange.getRequestBody()) {
    byte[] buffer = new byte[512];
    int n;
    while ((n = input.read(buffer)) != -1) {
        if (n > maxBytes - body.size()) {
            // Gửi 413 theo chính sách; không tiếp tục lưu dữ liệu.
            break;
        }
        body.write(buffer, 0, n);
    }
}
~~~

Fragment chưa tự trả 413; ví dụ đầy đủ ngay dưới sẽ thực hiện. Đếm bytes tránh rủi ro `String.length()` khác UTF-8 bytes. Với server public, cần thêm timeout đọc, hạn chế concurrent connections và giới hạn tổng tài nguyên; ngay cả payload nhỏ nhưng client gửi cực chậm có thể làm handler chiếm thread lâu.

## 6. Chương trình HTTP hoàn chỉnh chạy trên Java 17+

Tệp **`JdkHttpServerDemo.java`** kiểm tra:

- GET `/health` → **200 OK**.
- POST `/echo` body nhỏ → **200 ECHO:hello**.
- GET `/echo` (đúng context nhưng sai method) → **405 Method Not Allowed**.
- GET `/missing` (không khớp context) → **404**.
- Server chỉ bind loopback IPv4 và port 0, dùng executor 4 threads, có try/finally dọn tài nguyên.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class JdkHttpServerDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final int MAX_BYTES = 4096;

    private static void send(
            HttpExchange ex, int status, String message)
            throws IOException {
        byte[] content = message.getBytes(UTF8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(status, content.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(content);
        }
    }

    private static void health(HttpExchange ex)
            throws IOException {
        try (ex) {
            if (!"GET".equals(ex.getRequestMethod())) {
                ex.getResponseHeaders().set("Allow", "GET");
                send(ex, 405, "Method Not Allowed");
                return;
            }
            try (InputStream in = ex.getRequestBody()) {
                in.transferTo(OutputStream.nullOutputStream());
            }
            send(ex, 200, "OK");
        }
    }

    private static void echo(HttpExchange ex)
            throws IOException {
        try (ex) {
            if (!"POST".equals(ex.getRequestMethod())) {
                ex.getResponseHeaders().set("Allow", "POST");
                send(ex, 405, "Method Not Allowed");
                return;
            }
            ByteArrayOutputStream content =
                    new ByteArrayOutputStream();
            try (InputStream in = ex.getRequestBody()) {
                byte[] temp = new byte[512];
                int n;
                while ((n = in.read(temp)) != -1) {
                    if (n > MAX_BYTES - content.size()) {
                        send(ex, 413, "Payload Too Large");
                        return;
                    }
                    content.write(temp, 0, n);
                }
            }
            send(ex, 200, "ECHO:" + content.toString(UTF8));
        }
    }

    private static void check(
            HttpClient client, HttpRequest request)
            throws Exception {
        HttpResponse<String> result = client.send(
                request, HttpResponse.BodyHandlers.ofString(UTF8));
        String display = request.method() + " "
                + request.uri().getPath()
                + " -> " + result.statusCode();
        if (!"/missing".equals(request.uri().getPath())) {
            display += " " + result.body();
        }
        System.out.println(display);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 32);
        ExecutorService workers =
                Executors.newFixedThreadPool(4);

        server.createContext("/health", JdkHttpServerDemo::health);
        server.createContext("/echo", JdkHttpServerDemo::echo);
        server.setExecutor(workers);
        server.start();

        try {
            String root = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            check(client, HttpRequest.newBuilder(
                    URI.create(root + "/health"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build());

            check(client, HttpRequest.newBuilder(
                    URI.create(root + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type",
                            "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "hello", UTF8))
                    .build());

            check(client, HttpRequest.newBuilder(
                    URI.create(root + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build());

            check(client, HttpRequest.newBuilder(
                    URI.create(root + "/missing"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build());
        } finally {
            server.stop(1);
            workers.shutdown();
            if (!workers.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        }
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac --release 17 JdkHttpServerDemo.java
java JdkHttpServerDemo
~~~

**Stdout đã kiểm chứng trên JDK 24 sau khi biên dịch với `--release 17`:**

~~~text
GET /health -> 200 OK
POST /echo -> 200 ECHO:hello
GET /echo -> 405 Method Not Allowed
GET /missing -> 404
~~~

**Đọc kết quả:** `GET /health` được handler GET xử lý; `POST /echo` đọc body và trả lại; `GET /echo` vẫn vào đúng context nhưng handler chủ động trả 405, còn `/missing` được built-in server trả 404. Chương trình chỉ in status của 404 vì body HTML mặc định có thể khác giữa providers/phiên bản.

Đây là **lab loopback**, không phải public REST service. Nó chưa kiểm tra Content-Type, exact path, authentication hay tốc độ gửi request. `health()` chủ động drain input vào null stream, phù hợp bài thử GET không body nhưng không nên dùng vô điều kiện cho client không đáng tin vì có thể phải đọc body rất lớn/cực chậm. `echo()` có max 4096 bytes nhưng không có deadline đọc riêng; khi vượt limit và trả 413 trước khi body hết, connection có thể không được reuse. Những điều đó là giới hạn được chủ động thừa nhận, không phải mẫu production hoàn chỉnh.

## 7. HttpsServer mở rộng HttpServer như thế nào?

`HttpsServer extends HttpServer`. Vì vậy phần lớn API **context, handler, filter, executor, bind/start/stop** giống nhau. Khác biệt nằm ở **TLS**:

~~~text
HttpServer:
  HTTP bytes (plaintext) -> HttpExchange -> handler -> response

HttpsServer:
  TLS handshake (server identity + crypto)
          |
          v
  HTTP bytes inside encrypted TLS connection
          |
          v
  HttpsExchange -> handler -> response over TLS
~~~

`HttpsServer` yêu cầu gắn một `HttpsConfigurator` chứa `SSLContext` đã được khởi tạo. `SSLContext` của **server** phải có **key material** (private key + certificate chain) dùng xác thực server. Chỉ gọi `HttpsServer.create()`, `start()` và hy vọng có TLS tự động là chưa đủ. Dùng `SSLContext.getDefault()` cũng không bảo đảm có certificate/private key phù hợp cho vai trò server.

| Thành phần HTTPS | Cần có? | Vì sao |
| --- | --- | --- |
| `HttpsServer` | Có | Listener HTTP qua TLS |
| `HttpsConfigurator` | Có | Cung cấp SSLContext/TLS settings |
| Server `KeyStore` (PKCS12) | Thông thường có | Chứa server private key và chứng chỉ |
| `KeyManagerFactory` | Có nếu sử dụng KeyStore | Nạp và cung cấp khóa server cho TLS |
| `SSLContext` đã init | Có | Engine TLS thực hiện handshake, mã hóa |
| Client `TrustManagerFactory` / truststore | Theo cách client xác thực server | Kiểm tra chain/tin cậy |
| Certificate hostname/SAN | Có đối với verification | Ngăn nhầm tên máy chủ |
| `HttpsExchange.getSSLSession()` | Có thể dùng | Quan sát trạng thái TLS trên exchange |
| Application authorization | Vẫn phải tự làm | TLS không tự cấp quyền đọc/ghi dữ liệu |

### Tạo SSLContext phía server

~~~java
// Fragment Java 17+, keys là KeyStore PKCS12 đã load.
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(keys, password);

SSLContext serverTls = SSLContext.getInstance("TLS");
serverTls.init(
        kmf.getKeyManagers(),
        null, // Demo không yêu cầu client certificate.
        new SecureRandom());
~~~

Đây là **fragment**: chưa định nghĩa keys/password/handler, xem code hoàn chỉnh mục 9. `SSLContext` ở đây nạp server key/cert; client truststore là thứ **riêng biệt**. **HTTPS thành công không tự có user authentication**. Nếu muốn mTLS, phía server cần trust managers phù hợp để xác minh client certificate và cấu hình `SSLParameters.setNeedClientAuth(true)`; phía client cũng phải có identity riêng. Dù dùng mTLS, ứng dụng vẫn cần authorization theo endpoint và tài nguyên.

### HttpsConfigurator có thể tùy chỉnh tham số

~~~java
// Fragment Java 17+, serverTls là SSLContext đã init.
https.setHttpsConfigurator(new HttpsConfigurator(serverTls) {
    @Override
    public void configure(HttpsParameters params) {
        SSLParameters sslparams =
                getSSLContext().getDefaultSSLParameters();
        // Tùy policy có thể chọn protocols/cipher suites/client auth.
        // Đừng bật needClientAuth khi chưa cấu hình mTLS.
        params.setSSLParameters(sslparams);
    }
});
~~~

Không ép một cipher suite/TLS version tùy ý chỉ để bỏ qua lỗi handshake; nên áp chính sách TLS theo yêu cầu bảo mật, Java provider và khả năng client. API `HttpsExchange.getSSLSession()` cung cấp thông tin về TLS session ở exchange; không thay thế chứng cứ đã xác thực người dùng hoặc được phân quyền nghiệp vụ.

## 8. Tạo chứng chỉ cho HTTPS loopback bằng keytool

Để kiểm thử HTTPS đúng cách, cần server keystore chứa **private key** và một **truststore phía client** chỉ chứa **chứng chỉ công khai đã được chọn tin cậy**.

~~~text
server.p12
  - private key server    (BÍ MẬT)
  - certificate (SAN localhost và 127.0.0.1)

server.cer
  - certificate public   (không chứa private key)

trust.p12
  - trusted certificate  (client dùng để verify server)
~~~

**Không** trao server.p12 (private key) cho client. Ở production cần CA/chain được quản lý, rotation, kiểm soát truy cập secrets và chính sách TLS. Chứng chỉ tự ký 1 ngày của lab là **chứng chỉ thử nghiệm**, không dùng cho public services.

Lệnh `keytool` sau chạy trong **thư mục lab tạm**:

~~~bash
# Ba lệnh minh họa trên Bash; password changeit CHỈ dùng lab.
keytool -genkeypair -alias loopback -keyalg RSA -keysize 2048 \
  -validity 1 -storetype PKCS12 -keystore server.p12 \
  -storepass changeit -keypass changeit -dname "CN=localhost" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1" -noprompt

keytool -exportcert -alias loopback -keystore server.p12 \
  -storepass changeit -file server.cer

keytool -importcert -alias loopback -file server.cer \
  -keystore trust.p12 -storetype PKCS12 \
  -storepass changeit -noprompt
~~~

Trên Windows PowerShell, nên gõ mỗi lệnh keytool **trên một dòng** hoặc dùng ký hiệu nối dòng của PowerShell; dấu `\` cuối dòng ở ví dụ Bash **không** phải cú pháp nối dòng của PowerShell.

**Vì sao có SAN?** Chương trình client sẽ kết nối tới `https://127.0.0.1:port/secure`, nên chứng chỉ phải có `IP:127.0.0.1` trong Subject Alternative Name. Không dựa vào `CN=localhost` để thay thế mọi kiểm tra hostname/IP hiện đại.

Thiết lập environment variables. Ví dụ Bash:

~~~bash
export HTTP_LAB_SERVER_P12="$PWD/server.p12"
export HTTP_LAB_TRUST_P12="$PWD/trust.p12"
export HTTP_LAB_P12_PASSWORD="changeit"
~~~

Ví dụ Windows PowerShell:

~~~powershell
$env:HTTP_LAB_SERVER_P12 = (Resolve-Path .\server.p12).Path
$env:HTTP_LAB_TRUST_P12 = (Resolve-Path .\trust.p12).Path
$env:HTTP_LAB_P12_PASSWORD = "changeit"
~~~

Đây là password cố ý đơn giản **chỉ để học**; không đưa password production vào source, shell history hoặc repo. Sau khi chạy lab, xóa các tệp keystore/cert thử nghiệm khỏi thư mục lab và không commit private key. Trong ứng dụng thật, dùng secret manager/hạ tầng quản lý khóa thay vì mã hard-code hoặc biến môi trường chung không kiểm soát.

### Không bao giờ dùng TrustManager accept-all để chữa lỗi TLS

Nếu client báo `SSLHandshakeException`, `PKIX path building failed` hoặc SAN mismatch, cách khắc phục là kiểm tra truststore, chain, expiry và URI host/IP, không gắn TrustManager tin mọi certificate hay tắt endpoint identification. Chỉ khi client xác minh đúng identity của server, HTTPS mới cung cấp bảo vệ xác thực server kỳ vọng.

## 9. Chương trình HTTPS hoàn chỉnh chạy được trên Java 17+

Lưu mã sau dưới tên **`JdkHttpsServerDemo.java`**. Chạy sau khi đã có `server.p12`, `trust.p12` và ba environment variables ở mục 8. Chương trình chỉ dùng các API hiện diện trên Java 17.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsExchange;
import com.sun.net.httpserver.HttpsServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class JdkHttpsServerDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;

    private static KeyStore load(
            String envName, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(
                Path.of(System.getenv(envName)))) {
            store.load(in, password);
        }
        return store;
    }

    private static SSLContext serverContext(
            KeyStore keys, char[] password) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, password);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(
                kmf.getKeyManagers(),
                null, // Không yêu cầu client certificate trong lab.
                new SecureRandom());
        return ssl;
    }

    private static SSLContext clientContext(
            KeyStore trusted) throws Exception {
        TrustManagerFactory tmf =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), new SecureRandom());
        return ssl;
    }

    private static void handle(
            HttpExchange exchange) throws IOException {
        try (exchange) {
            try (InputStream input = exchange.getRequestBody()) {
                input.transferTo(OutputStream.nullOutputStream());
            }
            boolean secure = exchange instanceof HttpsExchange
                    && ((HttpsExchange) exchange)
                            .getSSLSession() != null;

            byte[] bytes =
                    (secure ? "TLS-OK" : "TLS-MISSING")
                            .getBytes(UTF8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password =
                System.getenv("HTTP_LAB_P12_PASSWORD").toCharArray();

        KeyStore serverKeys =
                load("HTTP_LAB_SERVER_P12", password);
        KeyStore clientTrust =
                load("HTTP_LAB_TRUST_P12", password);

        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpsServer server = HttpsServer.create(
                new InetSocketAddress(loopback, 0), 16);
        ExecutorService workers =
                Executors.newFixedThreadPool(2);

        server.setHttpsConfigurator(
                new HttpsConfigurator(
                        serverContext(serverKeys, password)));
        server.createContext(
                "/secure", JdkHttpsServerDemo::handle);
        server.setExecutor(workers);
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .sslContext(clientContext(clientTrust))
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            URI uri = URI.create(
                    "https://127.0.0.1:"
                            + server.getAddress().getPort()
                            + "/secure");
            HttpRequest request =
                    HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response =
                    client.send(
                            request,
                            HttpResponse.BodyHandlers.ofString(UTF8));
            System.out.println(
                    "httpsStatus=" + response.statusCode());
            System.out.println(
                    "httpsBody=" + response.body());
        } finally {
            server.stop(1);
            workers.shutdown();
            if (!workers.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Biên dịch/chạy sau khi tạo certificates:

~~~bash
javac --release 17 JdkHttpsServerDemo.java
java JdkHttpsServerDemo
~~~

**Stdout quan sát khi biên dịch `--release 17` và chạy trên JDK 24:**

~~~text
httpsStatus=200
httpsBody=TLS-OK
~~~

Ý nghĩa:

1. Server dùng `KeyManagerFactory` lấy private key/chứng chỉ từ server.p12, tạo SSLContext và HttpsConfigurator **trước** khi start.
2. Client dùng `TrustManagerFactory` đọc **trust.p12 có certificate công khai** làm trust anchor; certificate có SAN IP phù hợp với URL. Không có đoạn mã disable certificate verification.
3. Handler thực hiện trong `HttpsExchange` và nhìn thấy `SSLSession`; chuỗi `TLS-OK` do chính handler tạo, không phải tính năng tự động của JDK.
4. Server vẫn đăng ký context/handler và quản lý executor/stop giống `HttpServer`.
5. Demo không kiểm tra authorization và không lưu dữ liệu: HTTPS hoàn tất **không đồng nghĩa API production đã bảo mật đủ**.

Nếu môi trường không có keytool, file chưa được tạo, mật khẩu sai, certificate hết hạn, TLS provider không phù hợp hoặc localhost bị chặn, bạn có thể gặp exception; không coi đây là kết quả stdout cố định trên mọi môi trường. Không gọi client với `https://localhost` nếu cert/URL không khớp SAN thích hợp. Không sửa bằng cách tắt hostname verification.

## 10. Filter, HttpContext và xử lý chung quanh handler

`HttpContext` có thể có `Filter`, `Authenticator` và các attributes phục vụ xử lý request. `Filter` chạy **trước/sau handler** thông qua `Filter.Chain`, thường dùng cho correlation ID, logging, kiểm tra chính sách hoặc observability.

Java 17 có factory:

~~~java
// Fragment, ctx là HttpContext đã được tạo.
ctx.getFilters().add(
        Filter.beforeHandler(
                "attach demo request ID",
                exchange -> {
                    exchange.setAttribute("requestId", "demo-1");
                    exchange.getResponseHeaders().set(
                            "X-Request-ID", "demo-1");
                }));
~~~

Ví dụ chỉ minh họa cách đăng ký filter, không chạy độc lập; cần import `com.sun.net.httpserver.Filter` và tạo ctx. Với production, request ID **phải sinh riêng cho mỗi request** và không lộ secret. Filter custom có thể override `doFilter(HttpExchange,Filter.Chain)`, gọi `chain.doFilter(exchange)` khi tiếp tục chain; nếu từ chối request, filter cần tự gửi response hợp lệ. Đừng vừa gửi response trong filter vừa tiếp tục để handler gửi status lần hai.

`BasicAuthenticator`/`DigestAuthenticator` hỗ trợ một số cơ chế HTTP authentication, nhưng **không thay thế authorization**. Basic credentials được mã hóa Base64 **không phải mã hóa bảo mật**: nếu dùng Basic, phải có TLS đúng và kiểm tra role/quyền đối với từng resource. Không giả định framework tự thêm CORS, CSRF protection hoặc OAuth/JWT verification.

## 11. Threading, backlog, giới hạn tải và graceful stop

Phân biệt:

- **Backlog:** hàng chờ TCP connection đang đợi accept, phụ thuộc OS.
- **Executor threads:** xử lý `HttpHandler.handle()`, có thể bị chiếm lâu do request body chậm hoặc DB call.
- **Task queue:** trong fixed thread pool mặc định thường không bounded, có thể tăng RAM khi quá tải.
- **Open connections/exchanges:** cần giới hạn riêng, không được đảm bảo chỉ bằng backlog.
- **Timeout:** giới hạn kết nối, đọc body, downstream processing và ứng dụng; nếu không có, slow clients gây cạn workers.

Một service thật nên giới hạn request size, read throughput, concurrent exchanges, response size, queue depth, rate theo user/IP và đặt deadlines cho dependencies. Đo active handler count, queue length, latency percentiles, HTTP status và TLS handshake failure class. Không log raw credentials hoặc body nhạy cảm.

### stop(delay) có nghĩa gì?

Javadoc `HttpServer.stop(int delay)` nói server đóng listening socket, ngừng nhận exchange mới, và đợi **cho đến khi các handler exchanges hiện tại hoàn tất hoặc đã qua khoảng delay giây (điều kiện nào tới trước)**. Sau đó kết nối TCP còn mở bị đóng, thread nền của server kết thúc; **object đã stop không thể restart**.

~~~java
// Fragment Java 17+, server và workers do ứng dụng sở hữu.
server.stop(5); // Đợi tối đa khoảng 5 giây cho exchanges đang xử lý.
workers.shutdown();
if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
    workers.shutdownNow();
}
~~~

- `stop(0)` dừng ngay mà không chờ handlers hoàn tất.
- `stop(5)` có thể chờ tối đa khoảng 5 giây nhưng **không bảo đảm mọi request thành công**, vì handlers có thể bị cắt khi hết hạn.
- `stop(-1)` không hợp lệ.
- Sau khi stop, **không thể gọi start lại** trên cùng instance; cần tạo server mới.
- `workers.shutdown()` là trách nhiệm quản lý executor riêng; `server.stop()` không tự động đóng mọi tài nguyên nghiệp vụ.

Khi shutdown một server có POST đang cập nhật DB, việc socket bị đóng không đồng nghĩa transaction bị rollback. Cần idempotency keys, transaction policy, error reporting và kiểm tra trạng thái request riêng.

## 12. Chú ý an toàn và giới hạn công nghệ

### HTTP plaintext so với HTTPS

`HttpServer` chỉ có HTTP không mã hóa: không dùng gửi Bearer token, password hay dữ liệu riêng tư qua mạng không tin cậy. `HttpsServer` bổ sung TLS, nhưng server certificate không đồng nghĩa user đã có quyền. Với API public, vẫn cần authn/authz, secret rotation, quotas, origin policy, request parsing và logging an toàn.

### Đây không phải full-featured HTTP framework

Module JDK17 này hỗ trợ **HTTP/1.1 server ở mức căn bản**, không có cam kết là HTTP/2 server, HTTP/3 server, WebSocket server chuyên dụng hay servlet container. Một `HttpClient` dùng HTTP/2 tới hệ thống khác không làm `HttpServer` hỗ trợ HTTP/2. Khi cần request routing phức tạp, JSON body mapping, middleware, HTTP/2, WebSocket server, metrics/traces, certificate rotation/mTLS production hoặc throughput lớn, hãy cân nhắc framework/servlet container/reverse proxy được thiết kế cho yêu cầu đó.

### Chạy trên localhost không thay thế kiểm tra quyền

Loopback giúp giảm phạm vi truy cập cho lab, nhưng process khác trên cùng máy vẫn có thể gửi request. Endpoint admin nội bộ phải có chính sách rõ ngay cả khi chỉ bind loopback, đặc biệt nếu hoạt động từ browser/desktop app hoặc dữ liệu nhạy cảm. Không phát log request headers/secret mà không lọc.

### CORS không phải authentication

Server JDK không tự áp CORS cho mọi browser API. Nếu ứng dụng web từ origin khác gọi endpoint, cần cấu hình response CORS headers, preflight OPTIONS và chính sách credentials chính xác. CORS browser chỉ là cơ chế bảo vệ trình duyệt; HTTP client Java không bị browser CORS chặn, và attacker vẫn có thể gọi endpoint trực tiếp nếu thiếu authentication.

### Input validation và parser

- Kiểm tra exact path để tránh prefix route ngoài ý muốn.
- Decode URI/path/query đúng, tránh traversal khi mapping tới filesystem.
- Kiểm tra method và content type, validate schema/trường bắt buộc.
- Đếm **bytes** không phải chỉ characters; áp max-size/deadline.
- Giới hạn số header/độ dài header phù hợp runtime/edge proxy.
- Không cho client điều khiển trực tiếp địa chỉ HTTP outbound của server nếu chưa kiểm soát SSRF.
- Không trả raw exception/stack trace vào response.
- Đóng streams và exchange trên mọi error path.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân chính | Cách xử lý |
| --- | --- | --- |
| `com.sun.net.httpserver` không tìm thấy | Thiếu module ở custom runtime/module resolution | `java --describe-module jdk.httpserver`, requires/add-modules |
| Không chạy được `jwebserver` trên Java 17 | Nhầm tính năng Java18+ | Dùng HttpServer API hoặc nâng JDK |
| `BindException: Address already in use` | Cổng đang bận | Dùng port 0 khi test, xác nhận bind |
| Remote không thể kết nối | Server chỉ bind loopback | Đúng cho test; production cần network/security plan |
| Request nhận 404 | Không có context khớp literal prefix | Kiểm tra path, chữ hoa/thường, slash |
| Request `/foobar` vào context `/foo` | Context match tiền tố | Dùng path `/foo/` hoặc check exact |
| GET tới route POST nhưng không 405 | Handler chưa check method | So sánh request method, trả 405 + Allow |
| Server chậm khi handler blocking | Executor mặc định hoặc thiếu threads/deadline | Executor đúng, giới hạn queue và I/O timeouts |
| `setExecutor` ném IllegalStateException | Gọi sau start | Set trước server.start() |
| Response client bị treo | Quên send headers/close output | `sendResponseHeaders` trước body; luôn close |
| IOException khi đóng output | Ghi thiếu/thừa số byte đã khai báo | Dùng UTF-8 payload.length, không String.length |
| `sendResponseHeaders(200,0)` tạo chunked | 0 là chunked, không phải no body | Dùng -1 nếu thật sự không body |
| HTTP/1.1 connection không reuse | Đóng request body khi chưa đọc hết | Drain có giới hạn hoặc chấp nhận connection close |
| 413 nhưng client gửi tiếp | Client đã buffer data/có in-flight bytes | Đóng/hạn chế connection theo policy |
| Server memory tăng | Body/readAllBytes/queue không bounded | Max bytes, bounded queues, slow-client protection |
| HTTPS handshake failed | Chưa có HttpsConfigurator hoặc key/cert | SSLContext với key manager, set config trước start |
| `PKIX path building failed` | Client không tin server cert | Truststore đúng/CA chain |
| `No subject alternative names present` | SAN không khớp URL/IP | Tạo SAN đúng, không tắt hostname verification |
| HTTPS nhưng chưa có user auth | TLS chỉ bảo vệ kết nối/server identity | Thêm authentication/authorization |
| Thoát ứng dụng nhưng pool thread sống | Chưa shutdown executor do app sở hữu | stop server, shutdown executor |
| `stop()` rồi `start()` không chạy | HttpServer không tái sử dụng sau stop | Tạo instance mới |

### Checklist debug

~~~text
1. JDK: java --version; java --describe-module jdk.httpserver
2. Bind: địa chỉ loopback/public, port, firewall, backlog
3. Context: path prefix dài nhất, hoa/thường, slash cuối
4. Handler: request method, URI, Content-Type, body limit
5. Response: headers trước body, đúng byte length, close streams
6. Executor: set trước start, active/queued tasks, blocking I/O
7. TLS: server keystore, SSLContext, HttpsConfigurator, SAN/trust
8. Shutdown: stop(delay), executor shutdown, pending handlers
~~~

Khi cần kiểm tra TLS, trước tiên xem certificate chain, SAN, expired date và trust roots; **không tắt SSL certificate verification** để làm lỗi biến mất. Khi cần kiểm tra routing, log route template và method chứ không log token/payload nhạy cảm.

## 14. Bài tập tự kiểm tra

**Câu 1.** `jdk.httpserver` có giống `java.net.http` không?  
**Đáp án:** Không. Module đầu tiên là API HTTP/HTTPS **server** nhúng của JDK, module thứ hai có HTTP/WebSocket **client**.

**Câu 2.** Các lớp cốt lõi để nhận HTTP trong JDK17?  
**Đáp án:** `HttpServer`, `HttpHandler`, `HttpExchange` và `HttpContext` từ `com.sun.net.httpserver`.

**Câu 3.** Vì sao context `"/foo"` có thể xử lý `"/foobar"`?  
**Đáp án:** Vì path matching là **longest literal prefix**, không phải exact segment routing.

**Câu 4.** Đặt backlog=32 có nghĩa chạy 32 handlers song song?  
**Đáp án:** Không. Backlog là hàng chờ TCP accept; concurrency do executor, workload và OS quyết định.

**Câu 5.** Nếu không gọi setExecutor, handler chạy ở đâu?  
**Đáp án:** Default implementation dùng thread được tạo khi `start()`, có thể thành bottleneck nếu handler blocking.

**Câu 6.** Có thể gọi setExecutor sau start không?  
**Đáp án:** Không đúng lifecycle; API có thể ném IllegalStateException. Gọi trước start.

**Câu 7.** Ai phải trả 405 khi GET vào context chỉ hỗ trợ POST?  
**Đáp án:** Chính handler/filter của ứng dụng, thường kèm `Allow: POST`. Context chỉ dựa vào path.

**Câu 8.** Gửi string UTF-8 bằng `sendResponseHeaders(status, message.length())` có an toàn không?  
**Đáp án:** Không. Length là số **bytes**, dùng `message.getBytes(UTF_8).length`.

**Câu 9.** `sendResponseHeaders(200,0)` có nghĩa không body?  
**Đáp án:** Không. Giá trị 0 chọn chunked transfer; no body dùng -1 khi hợp lệ.

**Câu 10.** Vì sao cần close getResponseBody()?  
**Đáp án:** Để hoàn tất exchange và giải phóng tài nguyên; thiếu close có thể khiến client/connection bị giữ.

**Câu 11.** HttpsServer cần gì ngoài create/start?  
**Đáp án:** HttpsConfigurator chứa SSLContext khởi tạo với **server identity key/certificate** phù hợp.

**Câu 12.** Client truststore có cần server private key không?  
**Đáp án:** Không. Chỉ cần CA/certificate công khai tin cậy; private key ở server.

**Câu 13.** SAN IP=127.0.0.1 quan trọng vì sao?  
**Đáp án:** Demo client gọi URL với IP 127.0.0.1, và TLS client xác minh identity từ certificate SAN.

**Câu 14.** HTTPS tự làm authorization theo user chưa?  
**Đáp án:** Chưa. TLS mã hóa/xác thực server, ứng dụng vẫn cần authentication và authorization.

**Câu 15.** Vì sao `Executors.newFixedThreadPool(4)` chưa đủ ngăn OOM?  
**Đáp án:** Queue mặc định có thể không bounded; request bodies/response buffers cũng cần giới hạn.

**Câu 16.** `server.stop(5)` có bảo đảm các POST đang chạy đều commit xong?  
**Đáp án:** Không. Nó chỉ đợi tối đa khoảng 5 giây; server có thể cắt connection khi hết thời hạn.

**Câu 17.** Sau khi stop có thể start lại cùng HttpServer không?  
**Đáp án:** Không. Tạo instance mới.

**Câu 18.** `jwebserver` có phải API Java17 không?  
**Đáp án:** Không. Tool này cùng SimpleFileServer được thêm từ Java18.

**Câu 19.** Khi nào nên chọn framework thay vì HttpServer?  
**Đáp án:** Khi cần routing/JSON/security/observability/HTTP2/WebSocket server, tải lớn và lifecycle production phức tạp.

**Câu 20.** Vì sao không nên sử dụng TrustManager tin mọi chứng chỉ?  
**Đáp án:** Vì mất xác thực danh tính server, dễ bị MITM; phải sửa certificate/truststore/SAN đúng.

## 15. Tài liệu chính thức

- Oracle Java SE 17 — module `jdk.httpserver` và exported packages: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html
- Oracle Java SE 17 — package `com.sun.net.httpserver` và phạm vi HTTP/HTTPS: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html
- Oracle Java SE 17 — `HttpServer`: create/bind/start/stop, context prefix, executor: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java SE 17 — `HttpHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html
- Oracle Java SE 17 — `HttpContext`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html
- Oracle Java SE 17 — `HttpExchange`: request/response lifecycle, length, close: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java SE 17 — `Filter`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html
- Oracle Java SE 17 — `Headers`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html
- Oracle Java SE 17 — `HttpsServer`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html
- Oracle Java SE 17 — `HttpsConfigurator`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html
- Oracle Java SE 17 — `HttpsExchange`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsExchange.html
- Oracle Java SE 17 — `SSLContext` và TLS: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html
- Oracle Java SE 17 — `HttpClient` dùng kiểm thử: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 18 — `SimpleFileServer/jwebserver` từ 18: https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/module-summary.html
