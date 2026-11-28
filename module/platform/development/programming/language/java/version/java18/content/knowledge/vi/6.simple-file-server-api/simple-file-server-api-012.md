# Tách route kiểm tra trạng thái khỏi route phục vụ tài nguyên tĩnh trong ví dụ phát triển

> **Chương:** API SimpleFileServer  
> **Module học:** JAVA_VERSION_JAVA18 — SimpleFileServer được bổ sung từ Java 18; bài này kết hợp API đó với HttpServer và HttpContext vẫn dùng được trên JDK hiện đại.  
> **Mục tiêu:** Tạo một endpoint health riêng, giữ file handler ở context tĩnh, hiểu cách HttpServer chọn context và kiểm thử cả hai route trong một server phát triển cục bộ.

## 1. Vì sao nên tách health route khỏi static route?

Một file server thường phục vụ HTML, CSS, JavaScript, ảnh hoặc tài liệu mẫu. Nếu gắn file handler trực tiếp ở context gốc /, mọi request không khớp context cụ thể hơn đều có thể đi tới handler đó. Một endpoint kiểm tra trạng thái như /health/ nên có handler riêng để trả response ngắn, ổn định và không phụ thuộc vào việc một tệp có tồn tại trong thư mục tĩnh hay không.

Ví dụ, một server phát triển có thể có hai route:

| Route | Handler | Trách nhiệm |
| --- | --- | --- |
| /health/ | Health handler tự viết | Trả trạng thái của tiến trình HTTP demo. |
| / | SimpleFileServer.createFileHandler(root) | Phục vụ tệp và directory listing dưới thư mục root. |

Khi client gửi GET /health/, server chọn context /health/ vì nó cụ thể hơn /. Khi client gửi GET /hello.txt, context / chuyển request cho file handler và handler tìm hello.txt dưới thư mục gốc.

Tách hai trách nhiệm này giúp:

- Health probe không cần tạo một tệp health trong thư mục public.
- Nội dung health response không phụ thuộc vào file server.
- Có thể đặt chính sách method, headers và cache riêng cho health endpoint.
- Log/filter của từng context có thể được cấu hình độc lập.
- Các request sai đường dẫn vẫn được xử lý bởi static handler hoặc trả 404, thay vì vô tình nhận response health.

## 2. Hai tầng định tuyến: HttpContext trước, handler sau

HttpServer chọn HttpContext theo request URI path. Context có tiền tố khớp dài nhất được chọn. Sau khi context được xác định, filter chain và handler của context đó mới được chạy.

Với hai context:

~~~text
/health/  -> healthHandler
/         -> fileHandler
~~~

Luồng xử lý:

~~~text
HTTP request
     |
     v
HttpServer chọn HttpContext theo URI path
     |
     +---- /health/... ----> context /health/
     |                           |
     |                           v
     |                      healthHandler
     |
     +---- các path khác ---> context /
                                 |
                                 v
                              fileHandler
     |
     v
HTTP response
~~~

Trên JDK built-in hiện đại, path-prefix matching giữ ranh giới segment. Context /health/ khớp /health/ và các path con như /health/details, nhưng không khớp /healthcheck. Dấu / cuối làm ranh giới route rõ ràng và cũng tránh phụ thuộc vào khác biệt string-prefix của một số HttpServerProvider bên thứ ba.

Trong ví dụ này, /health/ là URL health chính thức. Request /health thiếu dấu / cuối sẽ đi vào context /; nếu thư mục tĩnh không có tài nguyên tương ứng, file handler trả 404. Nếu ứng dụng muốn hỗ trợ cả /health và /health/, hãy đăng ký và kiểm tra rõ cả hai đường dẫn hoặc chuẩn hóa URL bằng một handler riêng.

## 3. Health handler nên trả gì?

Một health handler cho ví dụ phát triển chỉ cần trả một response ngắn, không đọc file và không liệt kê thư mục. Ví dụ dưới đây:

- GET /health/ trả 200 OK cùng body OK.
- HEAD /health/ trả 200 OK nhưng không có body.
- Method khác trả 405 Method Not Allowed cùng header Allow: GET, HEAD.
- Header Cache-Control: no-store yêu cầu client/cache không lưu response health.
- Header Content-Type mô tả body là văn bản UTF-8.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

static HttpHandler healthHandler() {
    return exchange -> {
        String method = exchange.getRequestMethod();
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");

        if (method.equals("GET")) {
            sendText(exchange, 200, "OK\n");
            return;
        }

        if (method.equals("HEAD")) {
            // HEAD có cùng status nhưng không gửi response body.
            exchange.sendResponseHeaders(200, -1);
            exchange.close();
            return;
        }

        exchange.getResponseHeaders().set("Allow", "GET, HEAD");
        sendText(exchange, 405, "Method Not Allowed\n");
    };
}

static void sendText(
        HttpExchange exchange, int status, String text) throws IOException {
    byte[] body = text.getBytes(StandardCharsets.UTF_8);
    exchange.sendResponseHeaders(status, body.length);
    try (OutputStream output = exchange.getResponseBody()) {
        output.write(body);
    }
}
~~~

HttpExchange là đối tượng của một request/response cụ thể. Handler đọc method qua getRequestMethod(), thiết lập response headers, gửi status/độ dài body bằng sendResponseHeaders(...), rồi ghi response body. Với HEAD, ví dụ truyền -1 để không gửi body.

Không nên trả quá nhiều thông tin nội bộ trong health response. Một response OK ngắn thường đủ cho ví dụ phát triển; không in stack trace, đường dẫn ổ đĩa, biến môi trường hoặc thông tin xác thực ra endpoint công khai.

## 4. Gắn health context và file context vào cùng HttpServer

Đoạn cấu hình cốt lõi:

~~~java
Path root = Path.of("public").toAbsolutePath().normalize();
HttpServer server = HttpServer.create(address, 0);

server.createContext(
        "/health/", healthHandler());
server.createContext(
        "/", SimpleFileServer.createFileHandler(root));

server.start();
~~~

Trong đó:

- root là thư mục hệ thống tệp được file handler phục vụ.
- healthHandler() trả một HttpHandler do ứng dụng viết.
- Context /health/ được chọn cho health route.
- Context / làm route tĩnh mặc định.
- start() mới bắt đầu nhận và xử lý request.

Factory createFileHandler(root) chỉ tạo handler. Ứng dụng vẫn phải tự tạo HttpServer, đăng ký context, chọn địa chỉ/cổng và quản lý vòng đời server.

Trong ứng dụng dùng named module, khai báo:

~~~java
module demo.simplefileserver {
    requires jdk.httpserver;
}
~~~

## 5. Ví dụ hoàn chỉnh: kiểm thử health route và static route

Ví dụ này tự tạo thư mục tạm và file hello.txt, bind server vào loopback với cổng 0, gửi request bằng HttpClient, kiểm tra status/body rồi dừng server và xóa dữ liệu tạm. Không cần tạo file thủ công hoặc giữ terminal chờ Enter.

Lưu thành SeparatedHealthAndStaticRoutes.java:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;

import java.io.IOException;
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

public class SeparatedHealthAndStaticRoutes {
    private static HttpHandler healthHandler() {
        return exchange -> {
            String method = exchange.getRequestMethod();
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.getResponseHeaders().set("Cache-Control", "no-store");

            if (method.equals("GET")) {
                sendText(exchange, 200, "OK\n");
                return;
            }

            if (method.equals("HEAD")) {
                exchange.sendResponseHeaders(200, -1);
                exchange.close();
                return;
            }

            exchange.getResponseHeaders().set("Allow", "GET, HEAD");
            sendText(exchange, 405, "Method Not Allowed\n");
        };
    }

    private static void sendText(
            HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, body.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(body);
        }
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
        Path root = Files.createTempDirectory("static-root-")
                .toAbsolutePath().normalize();
        Files.writeString(
                root.resolve("hello.txt"),
                "Hello from static files\n",
                StandardCharsets.UTF_8);

        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0),
                0);

        server.createContext("/health/", healthHandler());
        server.createContext(
                "/", SimpleFileServer.createFileHandler(root));

        try {
            server.start();

            InetSocketAddress bound = server.getAddress();
            URI healthUri = uri(
                    bound.getAddress(), bound.getPort(), "/health/");
            URI staticUri = uri(
                    bound.getAddress(), bound.getPort(), "/hello.txt");
            URI nearMatchUri = uri(
                    bound.getAddress(), bound.getPort(), "/healthcheck");

            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<String> health = client.send(
                    HttpRequest.newBuilder(healthUri).GET().build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            HttpResponse<String> staticFile = client.send(
                    HttpRequest.newBuilder(staticUri).GET().build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            HttpResponse<String> nearMatch = client.send(
                    HttpRequest.newBuilder(nearMatchUri).GET().build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            HttpResponse<String> unsupported = client.send(
                    HttpRequest.newBuilder(healthUri)
                            .POST(HttpRequest.BodyPublishers.noBody())
                            .build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            if (health.statusCode() != 200
                    || !health.body().equals("OK\n")) {
                throw new AssertionError("Health response không hợp lệ");
            }
            if (staticFile.statusCode() != 200
                    || !staticFile.body().equals("Hello from static files\n")) {
                throw new AssertionError("Static response không hợp lệ");
            }
            if (nearMatch.statusCode() != 404) {
                throw new AssertionError(
                        "/healthcheck phải được chuyển sang static handler");
            }
            if (unsupported.statusCode() != 405
                    || !unsupported.headers().firstValue("Allow")
                            .orElse("").equals("GET, HEAD")) {
                throw new AssertionError("Health method policy không hợp lệ");
            }

            System.out.println("Health: " + health.statusCode()
                    + " " + health.body().trim());
            System.out.println("Static: " + staticFile.statusCode()
                    + " " + staticFile.body().trim());
            System.out.println("Near match /healthcheck: "
                    + nearMatch.statusCode());
            System.out.println("POST health: " + unsupported.statusCode()
                    + ", Allow=" + unsupported.headers()
                            .firstValue("Allow").orElse(""));
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

Biên dịch và chạy trên JDK 18 trở lên:

~~~bash
javac SeparatedHealthAndStaticRoutes.java
java SeparatedHealthAndStaticRoutes
~~~

Kết quả mong đợi:

~~~text
Health: 200 OK
Static: 200 Hello from static files
Near match /healthcheck: 404
POST health: 405, Allow=GET, HEAD
~~~

Cổng được hệ điều hành cấp nên thay đổi giữa các lần chạy. URL được dựng từ địa chỉ thực tế; nếu loopback là IPv6, host được đặt trong dấu ngoặc vuông.

## 6. Vì sao /healthcheck không phải health route?

Context health được đăng ký là /health/, có dấu / cuối. Với path-prefix matching của JDK built-in, route này khớp các path bắt đầu bằng segment /health/, chẳng hạn:

| Request path | Context được chọn | Kết quả trong ví dụ |
| --- | --- | --- |
| /health/ | /health/ | Health handler trả 200. |
| /health/details | /health/ | Health handler trả 200 nếu handler không kiểm tra path con. |
| /healthcheck | / | File handler tìm root/healthcheck, không có file nên 404. |
| /hello.txt | / | File handler trả nội dung tệp. |
| /health | / | File handler tìm root/health, không có file nên 404. |

Nếu chỉ muốn endpoint chính xác /health/, có thể bổ sung kiểm tra exchange.getRequestURI().getPath() trong health handler và trả 404 cho path con. Trong ví dụ hiện tại, mọi path con dưới /health/ đều được coi là health route; đó là lựa chọn đơn giản cho một endpoint phát triển.

Tránh đăng ký context /health khi muốn ranh giới route nghiêm ngặt mà không kiểm tra provider: JDK built-in hiện đại dùng path-prefix matching theo segment, nhưng API Note cho phép HttpServerProvider khác có cách so khớp khác khi context path không kết thúc bằng /. Dùng /health/ là cách thể hiện ý định rõ ràng và portable hơn.

## 7. Health check khác với kiểm tra tài nguyên tĩnh

Health handler và file handler trả lời hai câu hỏi khác nhau:

- Health handler trả lời: tiến trình HTTP demo có thể nhận request và tạo response hay không?
- File handler trả lời: tài nguyên được yêu cầu có tồn tại và đọc được dưới root directory hay không?

Do đó:

- /health/ trả 200 không chứng minh mọi file đều tồn tại hoặc đọc được.
- /hello.txt trả 404 không nhất thiết có nghĩa HTTP server đã chết; có thể chỉ là file bị thiếu.
- Health route không nên dùng để liệt kê nội dung thư mục hoặc tiết lộ cấu trúc filesystem.
- File route không nên được dùng làm tín hiệu health vì một file cụ thể có thể bị xóa hoặc đổi tên.

Trong ví dụ phát triển, health response chỉ chứng minh handler có thể trả response. Một hệ thống thực tế có thể phân biệt **liveness** (tiến trình còn sống) và **readiness** (đã sẵn sàng nhận traffic). Kiểm tra readiness có thể cần xác minh các phụ thuộc mà ứng dụng thật sự cần; tránh biến endpoint liveness thành một chuỗi kiểm tra dependency dài khiến một sự cố bên ngoài làm tiến trình bị khởi động lại không cần thiết.

## 8. Filter, logging và chính sách riêng theo context

Vì health và static là hai HttpContext khác nhau, có thể gắn filter riêng:

~~~java
HttpContext health = server.createContext(
        "/health/", healthHandler());
HttpContext files = server.createContext(
        "/", SimpleFileServer.createFileHandler(root));

health.getFilters().add(/* filter dành cho health */);
files.getFilters().add(/* filter dành cho static files */);
~~~

Ví dụ:

- Health route có thể chỉ ghi method, status và thời gian xử lý.
- Static route có thể dùng SimpleFileServer.createOutputFilter(...) để ghi request log.
- Không cần ghi headers nhạy cảm của health probe nếu không có nhu cầu chẩn đoán.
- Filter thêm vào một context không tự động áp dụng cho context còn lại.

Nếu bật OutputLevel.VERBOSE trên static context, hãy nhớ request/response headers và đường dẫn tuyệt đối có thể xuất hiện trong log. Chỉ dùng dữ liệu thử nghiệm và không lưu log trong thư mục root đang được phục vụ.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| /health/ trả nội dung directory listing | Health context chưa được đăng ký hoặc path không khớp. | Kiểm tra server.createContext("/health/", healthHandler()) và URL có dấu / cuối. |
| /healthcheck bị xử lý như health | Dùng context path thiếu ranh giới segment hoặc provider có quy tắc string-prefix. | Dùng /health/ và kiểm thử trên JDK/provider đích. |
| /hello.txt trả 404 | File không nằm trong root hoặc root không phải thư mục mong muốn. | Kiểm tra root.resolve("hello.txt") và working directory. |
| Health route trả 405 | Handler chỉ cho phép method được định nghĩa, ví dụ GET/HEAD. | Gửi method được cho phép hoặc cập nhật policy có chủ đích. |
| Health trả 200 nhưng static file lỗi | Hai handler kiểm tra hai điều kiện khác nhau. | Kiểm tra riêng quyền đọc, root directory và file cần phục vụ. |
| Static route vô tình phục vụ tệp riêng | Chọn root quá rộng. | Dùng một thư mục public riêng chỉ chứa nội dung được phép chia sẻ. |
| Không thấy log health route | Filter chỉ gắn vào static context. | Gắn filter riêng vào health context nếu thực sự cần log. |
| URL test không kết nối được | Chưa gọi server.start(), dùng sai cổng hoặc sai họ IP. | Đọc server.getAddress() sau bind, dựng URL đúng IPv4/IPv6 và gọi start. |

## 10. Nguyên tắc sử dụng trong môi trường phát triển

1. **Đăng ký health context cụ thể trước khi start:** cấu hình đầy đủ cả health và static route trước server.start().
2. **Giữ health response ngắn:** trả status và nội dung tối thiểu, không đưa thông tin nội bộ vào body.
3. **Dùng path có dấu / cuối:** /health/ tạo ranh giới segment rõ ràng.
4. **Giữ static root nhỏ và có chủ đích:** không phục vụ home directory, source code, secret hoặc dữ liệu người dùng.
5. **Bind loopback khi chỉ thử trên máy hiện tại:** dùng InetAddress.getLoopbackAddress() và cổng 0 để tránh mở server ra mạng ngoài ý muốn.
6. **Kiểm thử từng route:** health GET/HEAD, method không hỗ trợ, static file tồn tại, static file không tồn tại và path gần giống /healthcheck.
7. **Phân biệt demo health với production readiness:** ví dụ này minh họa routing và handler, không thay thế thiết kế health monitoring của ứng dụng triển khai thực tế.

## 11. Câu hỏi tự kiểm tra

1. Vì sao nên tách /health/ khỏi context phục vụ file?
2. Khi có context /health/ và /, request /health/ được chuyển đến context nào? Vì sao?
3. Vì sao /healthcheck không được coi là /health/ trên JDK built-in path-prefix matching?
4. SimpleFileServer.createFileHandler(root) trả về kiểu gì và nó đảm nhiệm phần nào?
5. Vì sao health handler có thể trả 200 trong khi static file handler trả 404?
6. Trong ví dụ, vì sao health handler chỉ cho phép GET/HEAD?
7. Filter gắn vào health context có tự chạy cho static context không?
8. Vì sao nên bind loopback và dùng cổng 0 trong ví dụ phát triển?
9. Health endpoint tối giản có chứng minh mọi dependency của ứng dụng đều sẵn sàng không?
10. Vì sao không nên dùng thư mục chứa source code hoặc secret làm static root?

**Bài thực hành:** chạy SeparatedHealthAndStaticRoutes, quan sát bốn kết quả được in ra. Thêm một file healthcheck vào root rồi chạy lại để thấy /healthcheck thuộc static route, không thuộc health route. Sau đó đổi context health thành /health và thử /healthcheck trên JDK built-in; so sánh với /health/ và ghi lại vì sao dấu / cuối giúp route rõ ràng hơn. Khôi phục /health/ sau khi thử.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — SimpleFileServer](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): createFileHandler, phục vụ tệp, directory listing và method được hỗ trợ.
- [Oracle JDK 27 — HttpServer](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo context, chọn context theo URI path, start() và stop(delay).
- [Oracle JDK 27 — HttpContext](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): handler, filter và path của context.
- [Oracle JDK 27 — HttpExchange](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request method, response headers, sendResponseHeaders và response body.
- [Oracle JDK 27 — HttpClient](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html): gửi request để kiểm thử health và static route.
- [Oracle JDK 18 — SimpleFileServer](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): API file server được giới thiệu từ Java 18.
