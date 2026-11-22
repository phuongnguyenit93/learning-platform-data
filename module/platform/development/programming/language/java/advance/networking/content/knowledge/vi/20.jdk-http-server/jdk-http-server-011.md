# SimpleFileServer và jwebserver: phục vụ file tĩnh để thử nghiệm với JDK

## 1. Tình huống thực tế: cần một HTTP server ngay, nhưng không cần framework

Khi học Java Networking, đôi khi ta chỉ muốn một địa chỉ HTTP để trình duyệt, `curl`, Java `HttpClient` hoặc một chương trình frontend truy cập các tài nguyên **tĩnh**:

- Thử `GET /index.html` để xem một trang HTML local.
- Phục vụ `/assets/data.json` chứa dữ liệu mẫu cho frontend hoặc bài test API client.
- Cho phép download `hello.txt`/ảnh từ máy phát triển mà không phải viết `HttpHandler` đọc file thủ công.
- Thử hành vi HTTP status `200`, `404`, `HEAD`, `Content-Type` hay sự khác nhau giữa GET và POST.
- Có một thư mục fixture để chạy kiểm thử tích hợp local mà không phụ thuộc Internet.

Từ **JDK 18** (JEP 408), JDK cung cấp hai cách thuận tiện:

1. **`jwebserver`**: một chương trình dòng lệnh tạo **Simple Web Server** cho thư mục static, chỉ cần chạy lệnh.
2. **`com.sun.net.httpserver.SimpleFileServer`**: API Java tạo server hoặc handler phục vụ file, có thể kết hợp `HttpServer` và các endpoint test riêng.

Cả hai chủ yếu dành cho **prototyping, development, debugging và giáo dục**. Chúng **không** phải web server production, **không hỗ trợ HTTPS hay HTTP/2** theo thiết kế Simple Web Server, và không cung cấp đầy đủ xác thực, phân quyền, quản trị tài nguyên, công cụ hardening của một server chuyên dụng. <https://openjdk.org/jeps/408>

**Mục tiêu của bài:** hiểu thời điểm dùng từng lựa chọn, triển khai server static trên loopback, kiểm thử HTTP response thực tế, biết giới hạn bảo mật/khả năng phục vụ, rồi tự dọn tài nguyên. Nội dung tập trung **SimpleFileServer và jwebserver** trong ngữ cảnh cha “HTTP server của JDK”; không viết một framework backend mới.

## 2. Yêu cầu phiên bản: đây là tính năng Java 18+, không phải Java 17

Thành phần này được giới thiệu trong **JDK 18**; JDK 17 có module `jdk.httpserver` và lớp `HttpServer`, nhưng **chưa có `SimpleFileServer` và tool `jwebserver`**.

| Thành phần | Có từ phiên bản | Ghi chú |
| --- | --- | --- |
| `com.sun.net.httpserver.HttpServer` | Có từ lâu trước JDK 18 | Có thể tự tạo handler GET/POST trong Java 17 |
| `com.sun.net.httpserver.SimpleFileServer` | **JDK 18** | Static file handler/server factory |
| `jwebserver` | **JDK 18** | CLI static server đi kèm JDK |
| `java -m jdk.httpserver` | Với Simple Web Server của JDK 18+ | Cách khởi động công cụ qua module |
| `java.net.http.HttpClient` | JDK 11+ | Dùng làm client kiểm tra ví dụ |

**Kiểm tra môi trường:**

```bash
java -version
javac -version
jwebserver -h
```

Nếu hệ điều hành báo `jwebserver: command not found` hoặc không có lệnh tương đương, hãy kiểm tra `PATH` có trỏ tới **thư mục `bin` của JDK 18+** hay chỉ trỏ tới JRE/JDK cũ. Trên Windows, chạy `where jwebserver`; trên Unix, `command -v jwebserver`. Cũng có thể dùng:

```bash
java -m jdk.httpserver -h
```

Lệnh này không tạo tài nguyên HTTP khi đi kèm `-h`, mà hiển thị hướng dẫn CLI. Nếu IDE biên dịch bằng `--release 17`, import `SimpleFileServer` sẽ không có trong public API target; dùng **`--release 18` hoặc mới hơn** và module `jdk.httpserver` khi biên dịch chương trình Java mẫu.

**Lưu ý về bài test:** mã ở mục 8 được **biên dịch bằng `javac --release 18` và chạy thực tế trên JDK 24**. Không tuyên bố rằng sample chạy trên Java 17. Dùng bản JDK có hỗ trợ tương ứng với API.

## 3. Khả năng của Simple Web Server: phục vụ static, không xử lý nghiệp vụ

Một **document root** (thư mục gốc để xuất bản) được chọn. Server ánh xạ path của HTTP request tới tài nguyên trong cây thư mục đó:

```text
Thư mục local đã chọn:
  static-demo/
    index.html
    hello.txt
    assets/
      logo.png
      data.json

HTTP server chạy ở http://127.0.0.1:8000/

GET /                  -> static-demo/index.html (nếu có)
GET /hello.txt         -> static-demo/hello.txt
GET /assets/data.json  -> static-demo/assets/data.json
GET /assets/           -> directory listing nếu không có index
GET /missing.txt       -> 404
HEAD /hello.txt        -> status/headers, không có response body
POST /hello.txt        -> không được hỗ trợ làm thao tác ghi file
```

Cách hoạt động được mô tả trong tài liệu JDK:

- **File tồn tại:** gửi nội dung file trong HTTP response.
- **Directory có index file:** phục vụ index file theo quy tắc của server, thông thường `index.html`.
- **Directory không có index file:** có thể trả **HTML directory listing** chứa tên file/thư mục con.
- **Hidden file và symbolic link:** bản triển khai Simple Web Server **không liệt kê hoặc phục vụ** những đối tượng này theo tài liệu. Cách nhận diện hidden file có thể khác nhau theo filesystem/hệ điều hành.
- **HTTP methods:** chỉ phục vụ **`GET` và `HEAD`**. Method khác có thể bị đáp `405 Method Not Allowed` hoặc `501 Not Implemented` tùy method/đường xử lý.
- **Content-Type:** server sử dụng bảng MIME sẵn có để đoán loại nội dung theo file type/extension; ví dụ `.html` là `text/html`, `.java` hoặc `.txt` thường là `text/plain`.
- **Giao thức:** Simple Web Server chỉ phục vụ HTTP/1.1 trên HTTP, **không phải HTTPS/HTTP2 application server**.

Thư mục được phục vụ có thể có subdirectories. **Directory listing không tự có authentication**; một tệp tên ngẫu nhiên trong directory listing **không được xem như file bí mật**. Chọn document root chỉ chứa fixture được phép xem.

## 4. Bắt đầu ngay với `jwebserver`

Giả sử bạn đã tạo **thư mục riêng chỉ chứa file test**:

```text
static-demo/
  index.html
  hello.txt
  assets/
    data.json
```

Nội dung file mẫu `index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>JDK Static Demo</title>
</head>
<body>
  <h1>Java Simple Web Server</h1>
  <a href="/hello.txt">Mở file text</a>
</body>
</html>
```

File `hello.txt` có thể chứa `Xin chào từ Java!`; file `assets/data.json` có thể chứa `{"ok":true}`. Không đặt private key, secrets, `.env`, cookie/session dumps hay cấu hình production vào thư mục test.

Từ một terminal, chạy:

```bash
jwebserver -b 127.0.0.1 -p 8000 -d ./static-demo -o info
```

Sau khi startup thành công, duyệt **`http://127.0.0.1:8000/`** hoặc gọi:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/hello.txt
curl -I http://127.0.0.1:8000/hello.txt
curl -i http://127.0.0.1:8000/not-found.txt
```

**Các kết quả quan sát nên kiểm tra, không hard-code response bytes:** GET file thường trả `200`, HEAD trả headers nhưng không body, path không tồn tại trả `404`; content bytes/MIME phụ thuộc file thật và JDK. Nếu port 8000 đã được dùng, đổi sang port chưa bị chiếm, ví dụ `-p 9000`. Nếu `-d ./static-demo` không được tìm thấy, kiểm tra **working directory của terminal** hoặc truyền đường dẫn tuyệt đối.

**Dừng server:** nhấn **Ctrl+C** trong terminal chạy `jwebserver`. Nó chạy ở foreground cho tới khi dừng; đừng để server lắng nghe ngoài ý muốn sau khi test.

Một cách khác tương đương về ý định:

```bash
java -m jdk.httpserver -b 127.0.0.1 -p 8000 -d ./static-demo -o info
```

Với bản JDK đã kiểm thử, CLI và module entry point đều nhận các tùy chọn bind, port, directory và output. Khởi động bằng module **không có nghĩa bạn phải tự viết Java class**.

## 5. Tất cả tùy chọn `jwebserver` cần biết

Cú pháp:

```text
jwebserver [-b bind-address] [-p port] [-d directory]
           [-o none|info|verbose] [-h] [-version]
```

| Flag | Giá trị | Mặc định và lưu ý |
| --- | --- | --- |
| `-b`, `--bind-address` | Địa chỉ mạng local | **Loopback** `127.0.0.1` hoặc `::1`; an toàn nhất cho thử nghiệm local |
| `-p`, `--port` | Port TCP | `8000`; port phải khả dụng |
| `-d`, `--directory` | Đường dẫn document root | Current working directory; không nên dùng nếu đang ở repo chứa secrets |
| `-o`, `--output` | `none`, `info`, `verbose` | `info` theo mặc định; `verbose` log thêm headers/path |
| `-h`, `--help` hoặc `-?` | Help | Hiển thị usage, không khởi động server |
| `-version`, `--version` | Version | Hiển thị version của tool |

Các kịch bản:

```bash
# Chỉ phục vụ một thư mục test trên loopback:
jwebserver -b 127.0.0.1 -p 8000 -d ./static-demo -o info

# Giảm log khi chạy bài kiểm thử:
jwebserver -b 127.0.0.1 -p 9000 -d ./static-demo -o none

# Quan sát thêm HTTP header và path trong môi trường KHÔNG có secret:
jwebserver -b 127.0.0.1 -p 8000 -d ./static-demo -o verbose

# Xem version:
jwebserver -version
```

**Không khuyên dùng:**

```bash
# PHẢN VÍ DỤ: server bắt đầu lắng nghe trên mọi interface.
jwebserver -b 0.0.0.0 -p 8000 -d .
```

Lệnh trên có thể cho các máy khác trong mạng truy cập file tĩnh. Khi current directory chứa repo source, credential, tài liệu chưa công bố hoặc file sinh ra trong CI, rủi ro lộ dữ liệu rất rõ ràng. `-b 0.0.0.0` **không** là phương án production networking; nếu thật sự cần chia sẻ fixture trên LAN, hãy có quyền/phê duyệt, chọn thư mục sạch và dùng biện pháp mạng riêng. Tốt hơn là dùng server có TLS/auth/firewall cho truy cập từ xa.

## 6. Tự kiểm tra GET, HEAD, POST bằng HTTP client

Một request GET bình thường:

```http
GET /hello.txt HTTP/1.1
Host: 127.0.0.1:8000

```

Nếu tài nguyên tồn tại, server trả status `200 OK` cùng bytes của file và metadata như `Content-Type`. Nếu resource là text UTF-8, ứng dụng client nên giải mã bằng charset đã biết từ hợp đồng fixture, không lấy `String.length()` làm kích thước bytes.

**HEAD** là request nhận response headers tương đương mà **không có response body**:

```http
HEAD /hello.txt HTTP/1.1
Host: 127.0.0.1:8000

```

Có thể thấy response status `200` và thông tin header, nhưng **client không được cố đọc một file body từ HEAD**. Một `Content-Length` trong response HEAD, nếu được gửi, có thể đại diện kích thước body của GET tương ứng, không phải số bytes body thực sự có trong HEAD.

**POST/PUT/DELETE không biến Simple Web Server thành writable file store**. Với SimpleFileServer, các method ngoài GET và HEAD không thực hiện thao tác upload/chỉnh sửa dữ liệu như một REST API. Trong phép thử mục 8, `POST /hello.txt` trả `405`. Tài liệu công cụ cho phép `405` hoặc `501` với request không hỗ trợ; không viết test khẳng định mọi method lạ bắt buộc trả đúng cùng một code.

| Request | Kỳ vọng hợp lý | Ý nghĩa |
| --- | --- | --- |
| `GET /hello.txt` | `200` nếu tồn tại | Đọc bytes static |
| `HEAD /hello.txt` | `200`, body rỗng | Kiểm tra metadata |
| `GET /missing.txt` | `404` | File không tồn tại |
| `GET /` | `200` + index nếu có | File index trang gốc |
| `GET /assets/` | `200` + listing nếu không có index | Directory listing dễ lộ tên fixture |
| `POST /hello.txt` | `405`/`501` theo cách xử lý | Không phải endpoint upload |
| `GET /private-key.pem` | Không được xuất hiện nếu không thuộc public root | **Bảo vệ bằng cách không đưa secret vào root** |

## 7. API `SimpleFileServer`: server, handler và output filter

Trong module `jdk.httpserver`, lớp `com.sun.net.httpserver.SimpleFileServer` cung cấp ba factory static:

### 7.1. `createFileServer(...)`

```java
HttpServer server = SimpleFileServer.createFileServer(
        new InetSocketAddress("127.0.0.1", 0),
        documentRoot.toAbsolutePath(),
        SimpleFileServer.OutputLevel.NONE);
server.start();
try {
    int actualPort = server.getAddress().getPort();
    // Run localhost client tests.
} finally {
    server.stop(0);
}
```

*Đây là mảnh mã trong method đã có `Path documentRoot` và các import; không phải class độc lập. Mục 8 có chương trình đầy đủ.*

Giải thích:

- `InetSocketAddress("127.0.0.1", 0)` ràng buộc loopback và yêu cầu OS chọn **port trống tự động**. Sau `start()`, đọc `server.getAddress().getPort()` để biết port thật.
- `documentRoot.toAbsolutePath()` quan trọng: API yêu cầu rootDirectory **absolute**, tồn tại, là directory và đọc được. Nếu không hợp lệ, nó có thể ném `IllegalArgumentException`.
- `OutputLevel.NONE` không in request logs, phù hợp khi muốn stdout test rõ. Có thể dùng `INFO` hoặc `VERBOSE` để debug.
- `server.start()` bắt đầu phục vụ; `server.stop(0)` dừng test trong finally. Với `HttpServer`, tham số của `stop(delay)` là số giây cho phép xử lý trao đổi hiện hữu, **không** là port hay timeout của client.
- Server tạo qua API này là **HTTP-only static server**; code không có SSLContext hay `HttpsServer`.

**Mẹo:** port `0` rất tiện cho integration test chạy song song, tránh hard-code 8000 dễ xung đột. Không giả định port được chọn giống nhau giữa các lần chạy.

### 7.2. `createFileHandler(Path)`

Khi bạn đã có `HttpServer` và cần kết hợp static handler với một endpoint nhỏ:

```java
// Fragment, root là Path tuyệt đối của thư mục static.
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 0);
server.createContext("/files/",
        SimpleFileServer.createFileHandler(root));

server.createContext("/health", exchange -> {
    try (exchange) {
        byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, body.length);
        exchange.getResponseBody().write(body);
    }
});

server.start();
```

*Mảnh code trên cần import `HttpServer`, `SimpleFileServer`, `InetSocketAddress` và `StandardCharsets`, đồng thời cần gọi `server.stop(0)` trong khối quản lý lifecycle ở ngoài.*

Ví dụ handler gắn `/files/`:

```text
GET /files/hi.txt -> file root/hi.txt
GET /health       -> response "OK" từ custom HttpHandler
GET /hi.txt       -> không match /files/ và /health, thường 404
```

Ba kết quả này đã được **kiểm thử riêng bằng Java** trong môi trường JDK tương thích.

**Lưu ý:** khả năng gắn một custom handler vào cùng server không biến `createFileHandler` thành framework có auth/TLS/rate-limits. Mỗi custom context phải tự xác định phương thức HTTP hợp lệ, status code, body, giới hạn request và bảo vệ dữ liệu. Nếu code chỉ để phục vụ static fixture, dùng `jwebserver` đơn giản hơn.

Ngoài ra, có thể dùng `HttpHandlers.handleOrElse(...)` để chọn giữa các handlers theo predicate. Chỉ nên dùng khi có yêu cầu rõ ràng; thêm PUT handler vào static server có thể vô tình mở chức năng ghi file nếu không thiết kế permission đầy đủ.

### 7.3. `createOutputFilter(...)`

```java
Filter logs = SimpleFileServer.createOutputFilter(
        System.out, SimpleFileServer.OutputLevel.VERBOSE);
HttpContext context = server.createContext("/files/",
        SimpleFileServer.createFileHandler(root));
context.getFilters().add(logs);
```

*Đây là fragment trong ngữ cảnh server/context được khởi tạo, cần import `Filter`, `HttpContext`, `HttpServer` và `SimpleFileServer`.*

Filter dùng cho logging. **`createOutputFilter(..., OutputLevel.NONE)` không phải cách tạo no-op filter**: API quy định sẽ ném `IllegalArgumentException` với `NONE`. Nếu không cần log, **đừng gắn filter**. Mặt khác, `createFileServer(..., OutputLevel.NONE)` là một trường hợp được hỗ trợ để server không log.

Ở chế độ `VERBOSE`, log có thể bao gồm request/response headers và absolute path của file. Không bật verbose trong môi trường có token, cookie, private URL hoặc tài liệu nhạy cảm; log không phải nơi chứa secrets.

## 8. Ví dụ Java chạy được: kiểm tra toàn bộ static behavior qua loopback

Chương trình sau tạo một document root **tạm thời và riêng biệt**, đưa vào vài file fixture, chạy `SimpleFileServer` ở port 0, dùng `HttpClient` kiểm tra response; sau đó khởi chạy **chính lệnh `jwebserver` từ JDK** dưới dạng tiến trình con để test CLI.

Nó không sửa repository hiện hành, không mở network interface ngoài loopback và tự dọn thư mục test.

**Tên tệp: `SimpleFileServerDemo.java`**

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Comparator;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

public final class SimpleFileServerDemo {
    static final HttpClient HTTP = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    static HttpResponse<byte[]> request(URI uri, String method)
            throws IOException, InterruptedException {
        HttpRequest req = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .method(method, HttpRequest.BodyPublishers.noBody())
                .build();
        return HTTP.send(req, HttpResponse.BodyHandlers.ofByteArray());
    }

    static URI url(int port, String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    static int temporaryPort() throws IOException {
        try (ServerSocket socket = new ServerSocket(0, 10,
                InetAddress.getByName("127.0.0.1"))) {
            return socket.getLocalPort();
        }
    }

    static void probeApi(Path root) throws Exception {
        HttpServer server = SimpleFileServer.createFileServer(
                new InetSocketAddress("127.0.0.1", 0),
                root.toAbsolutePath(), OutputLevel.NONE);
        server.start();
        try {
            int port = server.getAddress().getPort();
            HttpResponse<byte[]> file = request(url(port, "/hello.txt"), "GET");
            String text = new String(file.body(), StandardCharsets.UTF_8);
            System.out.println("API GET: " + file.statusCode() + " " + text);
            System.out.println("API MIME: " + file.headers()
                    .firstValue("Content-Type").orElse("(none)"));

            HttpResponse<byte[]> head = request(url(port, "/hello.txt"), "HEAD");
            System.out.println("API HEAD: " + head.statusCode()
                    + " bodyBytes=" + head.body().length);

            HttpResponse<byte[]> rootIndex = request(url(port, "/"), "GET");
            System.out.println("API index: " + rootIndex.statusCode()
                    + " containsTitle=" + new String(rootIndex.body(),
                    StandardCharsets.UTF_8).contains("Test Page"));

            HttpResponse<byte[]> listing = request(url(port, "/assets/"), "GET");
            System.out.println("API listing: " + listing.statusCode()
                    + " hasJson=" + new String(listing.body(),
                    StandardCharsets.UTF_8).contains("data.json"));

            System.out.println("API missing: "
                    + request(url(port, "/not-found.txt"), "GET").statusCode());
            System.out.println("API POST: "
                    + request(url(port, "/hello.txt"), "POST").statusCode());
        } finally {
            server.stop(0);
        }
    }

    static void probeCli(Path root) throws Exception {
        int port = temporaryPort();
        String executable = System.getProperty("os.name")
                .toLowerCase().contains("win") ? "jwebserver.exe" : "jwebserver";
        Path binary = Path.of(System.getProperty("java.home"),
                "bin", executable);
        Process process = new ProcessBuilder(binary.toString(),
                "-b", "127.0.0.1", "-p", Integer.toString(port),
                "-d", root.toString(), "-o", "none")
                .redirectErrorStream(true).start();
        try {
            HttpResponse<byte[]> result = null;
            for (int i = 0; i < 50; i++) {
                try {
                    result = request(url(port, "/hello.txt"), "GET");
                    break;
                } catch (IOException notReady) {
                    Thread.sleep(60);
                }
            }
            if (result == null) {
                throw new IllegalStateException("CLI did not start");
            }
            System.out.println("CLI GET: " + result.statusCode() + " "
                    + new String(result.body(), StandardCharsets.UTF_8));
        } finally {
            process.destroy();
            if (!process.waitFor(2, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor(2, TimeUnit.SECONDS);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("static-fixture-");
        try {
            Files.writeString(root.resolve("index.html"),
                    "<h1>Test Page</h1>", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("hello.txt"),
                    "Xin chào!", StandardCharsets.UTF_8);
            Path assets = Files.createDirectory(root.resolve("assets"));
            Files.writeString(assets.resolve("data.json"), "{\"ok\":true}",
                    StandardCharsets.UTF_8);
            probeApi(root);
            probeCli(root);
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder())
                        .toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

**Biên dịch bằng JDK 18+** (JDK 24 đã được kiểm thử):

```bash
javac --release 18 --add-modules jdk.httpserver SimpleFileServerDemo.java
java --add-modules jdk.httpserver SimpleFileServerDemo
```

Lệnh `--release 18` nhằm nhắm đến surface API xuất hiện ở JDK 18. Nếu Java runtime dùng để chạy **cũ hơn 18**, chương trình vẫn không thể chạy dù biên dịch bằng JDK mới.

**Stdout đã xác minh thực tế:**

```text
API GET: 200 Xin chào!
API MIME: text/plain
API HEAD: 200 bodyBytes=0
API index: 200 containsTitle=true
API listing: 200 hasJson=true
API missing: 404
API POST: 405
CLI GET: 200 Xin chào!
```

### 8.1. Giải thích từng phép thử

**GET 200:** SimpleFileServer ánh xạ `/hello.txt` vào file fixture trong root. Java HttpClient nhận bytes, decoder UTF-8 được chọn rõ. Không cần viết handler riêng đọc FileInputStream.

**MIME text/plain:** bảng MIME của JDK trả `Content-Type: text/plain` cho file `.txt`. Bảng MIME có thể thay đổi theo version/triển khai; không nên dùng extension làm chứng cứ an toàn cho nội dung.

**HEAD 200 bodyBytes=0:** vẫn kiểm tra tài nguyên tồn tại, nhưng body rỗng theo semantics HEAD. Điều này **không chứng minh `Content-Length: 0`**; body 0 bytes và Content-Length header có thể diễn đạt hai khái niệm khác nhau.

**Index 200:** root có `index.html` nên GET `/` phục vụ trang index thay vì directory listing.

**Listing 200:** thư mục `assets` không có index nên server tạo listing có `data.json`. Khi dùng công cụ này, hành vi listing có thể tiết lộ tên file/thư mục; không đặt thông tin nhạy cảm trong root.

**404:** path không tồn tại không thành công; test nên kiểm tra cả negative path, tránh frontend nhầm response 404 HTML với JSON mong muốn.

**POST 405:** server static từ chối POST; không được biến nó thành upload server chỉ bằng cách gọi `POST` từ client.

**CLI 200:** tiến trình `jwebserver` riêng được khởi chạy với bind loopback, directory fixture và port test. HttpClient xác minh server CLI thật sự trả dữ liệu, rồi chương trình dừng tiến trình con.

### 8.2. Những giới hạn của demo

- Mã test sử dụng **JDK 24** ở runtime nhưng **compile target JDK 18**; đây không phải bài test mọi version 18–24, mọi OS hoặc mọi filesystem.
- Server chỉ phục vụ **HTTP plaintext trên loopback**. Không có TLS, auth, access control, rate limit, chống DDoS hoặc hỗ trợ API động.
- `temporaryPort()` lấy một port tạm rồi đóng socket trước khi CLI bind: có một **race nhỏ** nếu chương trình khác chiếm port ngay sau đó. Trong test đơn giản, vòng retry đọc giúp chờ startup nhưng không giải quyết xung đột port tuyệt đối.
- `probeCli` dùng ProcessBuilder để truy cập file `jwebserver[.exe]` trong `java.home/bin`, không thay đổi PATH toàn hệ thống. Nếu chạy trên một custom runtime image **không có tool** này, test CLI không khả dụng.
- `Process.destroy()` và `waitFor(...)` là cleanup của tiến trình con; trên hệ điều hành khác có thể cần điều chỉnh thời gian chờ.
- `Files.walk(root)` xóa file fixture **do chính chương trình mới tạo**. Không copy logic này để xóa một thư mục có dữ liệu thật.
- Mã không bật log nên kết quả stdout ổn định, không in absolute path/headers của mỗi request.
- Những assertions trong stdout chỉ xác minh **một đường đi thử nghiệm local**, không chứng minh production safety, tính năng được hỗ trợ ngoài phạm vi hoặc tải lớn.

## 9. Phân biệt `createFileServer` và `createFileHandler`

| Nhu cầu | Lựa chọn | Tại sao |
| --- | --- | --- |
| Chia sẻ vài file local để frontend thử | `jwebserver` | Không cần code Java |
| Kiểm thử HTTP client với fixture local được tự tạo | `SimpleFileServer.createFileServer(...)` | Có lifecycle start/stop và port 0 trong chương trình test |
| Có `HttpServer` sẵn, muốn thêm static path | `SimpleFileServer.createFileHandler(...)` | Chỉ gắn handler cho context đã chọn |
| Muốn in log theo từng request trong test | `OutputLevel.INFO/VERBOSE` hoặc output filter | Quan sát request/response |
| Muốn tạo JSON động theo request ID, POST/PUT | Custom `HttpHandler` / test server chuyên dụng | Static file server không xử lý nghiệp vụ |
| Muốn cung cấp download có auth/TLS ngoài Internet | Web server/reverse proxy chuyên dụng | Simple Web Server không đáp ứng các yêu cầu này |
| Dịch vụ production cần HTTP/2, TLS, metrics, rate limit | Server production phù hợp | JEP 408 không thiết kế mục tiêu đó |

`createFileServer` trả lại một đối tượng `HttpServer` có thể cấu hình thêm trong phạm vi API, nhưng **phần static handler** vẫn có những giới hạn của Simple Web Server. Khi cần custom route hoặc header, nên suy nghĩ rõ ràng về phạm vi: static fixtures có thể được phục vụ bởi handler, còn nghiệp vụ động do custom handler đảm nhiệm. **Tính mở rộng của API không biến jwebserver CLI thành backend framework**.

## 10. Thư mục root phải tách riêng khỏi source code và tài liệu nhạy cảm

Lỗi thường gặp: chạy `jwebserver` khi current directory là root của dự án:

```text
my-project/
  .git/
  .env
  config/
  src/
  target/
  secrets/
  README.md
```

Dù tài liệu Simple Web Server nói hidden file và symbolic link không được phục vụ, vẫn **không coi đó là cơ chế bảo mật để có thể tùy tiện xuất bản root của repo**. Các file `README.md`, file config không hidden, file mới sinh ra hoặc tệp bất kỳ do script đặt có thể bị lộ. Một cơ chế server static test không phải sandbox chống mọi liên kết, race và thay đổi filesystem.

Nên tạo:

```text
project/
  src/                 # code thật: KHÔNG serve
  .env                 # secret: KHÔNG serve
  config/              # production config: KHÔNG serve
  test-fixtures-public/
    index.html
    assets/
      demo.json         # dữ liệu giả, không chứa thông tin cá nhân
```

Chỉ chạy:

```bash
jwebserver -b 127.0.0.1 -p 8000 -d ./test-fixtures-public
```

**Quy tắc path và permission:**

1. Root là directory do bạn chủ động xác định và có quyền đọc.
2. Root chứa **duy nhất** file được phép public trong phạm vi test.
3. Tránh sử dụng `.` nếu chưa chắc working directory; dùng `-d` tường minh.
4. Đừng chuyển `-b` sang all interfaces chỉ để giải quyết lỗi không truy cập từ một container/máy ảo mà không hiểu network topology.
5. Nếu root có dữ liệu người dùng/thành phần thứ ba được phép ghi, không lấy hidden-file/symlink behavior làm bảo đảm chống mọi rủi ro TOCTOU.
6. Không dùng static test server để truyền credential qua HTTP plaintext, kể cả cùng mạng LAN.
7. Đóng server ngay sau bài test; hạn chế quyền filesystem ở OS để server không đọc được secrets nằm ngoài fixture.
8. Nếu test phục vụ file HTML/JS, nhớ trình duyệt có thể chạy nội dung JavaScript trong origin localhost của server. Không mở file HTML không tin cậy và không đặt endpoint nhạy cảm dùng cùng origin.

**Lắng nghe loopback có nghĩa:** chỉ các tiến trình trên cùng host hoặc cùng không gian mạng phù hợp có thể kết nối; nó **không** là authentication. Một ứng dụng không tin cậy chạy trên cùng máy vẫn có thể gọi `http://127.0.0.1:8000/` nếu firewall/OS cho phép. Với container/VM, `localhost` nằm trong network namespace của từng môi trường, không tự là loopback của máy chủ vật lý.

## 11. Static MIME, encoding và kiểm tra dữ liệu nhận

Simple Web Server có bảng MIME cơ bản: `.html` thường `text/html`, `.txt` `text/plain`, `.json` có thể được xác định theo bảng MIME của JDK. Tuy nhiên, khi dùng nó để test client, hãy tách:

- **Bytes file**: nội dung thực sự đọc từ filesystem, không phải `String.length()`.
- **Content-Type**: loại media mà server đoán theo extension/bảng MIME, không chứng minh file parse được.
- **Charset**: đối với text, decoder phía client phải dùng encoding phù hợp; file JSON thông thường dùng UTF-8 theo RFC 8259.
- **Content-Length**: khi được gửi, đếm bytes theo semantics HTTP chứ không đếm UTF-16 code units.
- **HTTP status**: 200/404/405 nói trạng thái xử lý request, không bảo đảm semantic JSON/HTML.
- **Response version**: server đang dùng HTTP/1.1; đừng nhầm client `HttpClient.Version.HTTP_2` là server đã thương lượng HTTP/2.

**Ví dụ client đọc JSON fixture:**

```java
// Fragment: client và uri đã được khởi tạo.
HttpResponse<String> response = client.send(
        HttpRequest.newBuilder(uri).GET().build(),
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

if (response.statusCode() != 200) {
    throw new IOException("Fixture unavailable");
}
String jsonText = response.body();
// Parse/validate JSON with a JSON library appropriate to the test.
```

Đoạn này không phải class standalone; cần import `HttpClient`/`HttpRequest`/`HttpResponse`, `IOException`, `StandardCharsets`. **Không dùng regex/cắt chuỗi để parse JSON phức tạp** chỉ vì file được server static phục vụ. Ngoài ra, nếu test response cần header đặc biệt (CORS, cache, auth, content-encoding), đừng giả định jwebserver tự sinh chính xác mọi header; sử dụng custom handler hoặc mock server có khả năng cấu hình response.

## 12. Cache, CORS, Range, compression: đừng giả định có đầy đủ

Một HTTP server static chuyên dụng có thể hỗ trợ mạnh các tính năng như conditional requests, compression, configurable cache headers, byte-range requests hoặc security headers. **Không tự suy rằng Simple Web Server cung cấp đầy đủ những khả năng đó** chỉ vì nó phục vụ file thành công.

Những phép thử nên tách biệt:

| Tính năng | Nếu bài test phụ thuộc vào đó | Hướng xử lý |
| --- | --- | --- |
| `ETag`, `If-None-Match`, `If-Modified-Since` | Cần kiểm tra caching đúng spec | Quan sát actual headers/status hoặc dùng mock HTTP handler |
| `Cache-Control` | Muốn browser không cache fixture cũ | Sử dụng handler/proxy phù hợp, không giả định cache policy của static server |
| `Access-Control-Allow-Origin` | Frontend khác origin gọi fetch | Cần CORS response headers từ server kiểm soát; static server có thể không đáp ứng |
| `Range` / `206 Partial Content` | Kiểm thử resume download | Dùng server có Range implementation được xác nhận |
| `Content-Encoding: gzip` | Kiểm thử giải nén và length | Tạo response encoded đúng trong custom handler |
| `Authorization` và access control | Dữ liệu có quyền truy cập | Dùng server thực có authentication, không dùng public fixture server |
| HTTP/2/TLS ALPN | Kiểm thử performance/security protocol | Dùng server HTTP/2/HTTPS khác; Simple Web Server là HTTP/1.1 cleartext |
| Dynamic JSON theo body POST | Mock API có logic | Custom HttpHandler, WireMock hoặc test framework |

Nếu frontend báo lỗi CORS, việc chạy `jwebserver` thành công trên port 8000 **không** có nghĩa server đã tự thêm CORS headers cho site khác origin. Đừng nhầm **CORS** là cơ chế server-side authentication: đây là chính sách kiểm soát script trình duyệt; clients không phải browser vẫn có thể gửi HTTP request tới loopback nếu họ có khả năng kết nối.

Nếu cần một header/thao tác cụ thể, **test bằng HTTP client và quan sát response** thay vì ghi chú tài liệu giả định.

## 13. Logging: chọn mức đủ để quan sát, tránh lộ dữ liệu

Cấu hình command line:

```bash
jwebserver -b 127.0.0.1 -p 8000 -d ./static-demo -o info
```

Phân biệt:

- **`none`:** không in request log. Hữu ích cho test CI có stdout cần ổn định.
- **`info`:** ghi request log cơ bản, đủ thấy URL/method/status.
- **`verbose`:** log bổ sung request/response headers và absolute path tài nguyên, giúp debug nhưng dễ có thông tin nhạy cảm.

Nếu chạy `jwebserver -o verbose` trong repo không được kiểm soát, bạn không những có nguy cơ serve file nhạy cảm mà còn để path, query hoặc headers xuất hiện trong console/log pipeline. Trong ứng dụng có Authorization/Cookie headers, **không log nguyên văn**. Chỉ bật verbose khi cần, trên fixture giả, rồi tắt.

API `createFileServer(..., OutputLevel.INFO)` hỗ trợ mức log tương tự. Nếu đã tạo context riêng và muốn filter log, dùng `createOutputFilter(out, OutputLevel.INFO/VERBOSE)`; không tạo filter với `OutputLevel.NONE`.

## 14. Bài toán testing: static fixtures không phải mock API động

Sử dụng document root:

```text
fixtures/
  index.html
  api/
    users.json
    products.json
  assets/
    style.css
```

Khi test một frontend:

```text
GET /api/users.json
  -> nội dung file fixtures/api/users.json

GET /api/products.json
  -> nội dung file fixtures/api/products.json

GET /api/orders
  -> không có file, không tự tạo dữ liệu động
```

Đây là **static stub**: hữu ích khi nội dung response đã biết trước và client chỉ cần đọc. Nếu test cần `POST /orders` nhận body, validate input, sinh ID hay trả status 201/409 theo điều kiện, **SimpleFileServer không phải lựa chọn phù hợp**. Tạo custom `HttpHandler` hoặc dùng mock server chuyên dụng.

**Khi dùng fixtures cho integration tests:**

1. Mỗi test hoặc test suite tạo **thư mục root riêng** để tránh ghi lẫn.
2. Dùng port 0 trong API để tránh collision của port cố định.
3. Ghi file bằng charset xác định, ví dụ `StandardCharsets.UTF_8`, để byte count không phụ thuộc môi trường.
4. Cho client tự dựng URI theo port server vừa cấp; không hard-code 8000 nếu có thể chạy song song.
5. Kiểm tra cả success (200) và lỗi dự kiến (404, unsupported method), không chỉ nhìn body.
6. Dùng `try/finally` để `stop(0)` server và dọn file fixture do test tạo.
7. Nếu cần test CLI `jwebserver`, chạy trong child process được quản lý chặt, kết thúc trong finally, không sinh nhiều process tồn tại mãi.
8. Khi muốn test auth/CORS/cache/Range, tạo mock handler **đúng behavior cần kiểm thử**, không "hy vọng" static server mặc định sẽ làm giống production.
9. Không dùng secret thật trong fixture, kể cả server chỉ bind loopback.
10. Bảo đảm code test không xóa nhầm directory của người dùng: chỉ delete thư mục được tạo và sở hữu bởi chính test.

## 15. Sự khác nhau giữa static server và `HttpServer` custom

Trước JDK 18, một bài Java 17 thường tạo HTTP server kiểu:

```java
// Fragment minh họa Java 17: chưa có tự động serve directory.
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8000), 0);

server.createContext("/hello", exchange -> {
    try (exchange) {
        byte[] bytes = "Hello".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
});
server.start();
```

*Cần import `HttpServer`, `InetSocketAddress` và `StandardCharsets`, cùng cleanup `server.stop(0)`. Đây là fragment, không có main/class tự chạy.*

Với `SimpleFileServer` từ JDK 18, nếu chỉ muốn phục vụ file `hello.txt`, bạn **không cần tự giải URI path**, tự kiểm tra path traversal/symlink theo cách handler thủ công, mở FileInputStream, xác định MIME và tạo directory listing. Dùng factory có sẵn giảm boilerplate đáng kể.

Nhưng không được suy rằng custom handler thủ công "an toàn hơn" hoặc SimpleFileServer đã là security sandbox. Cả hai cần chọn network bind, directory, dữ liệu, auth và chính sách triển khai phù hợp với môi trường.

### Có cần Maven/Gradle dependency không?

**Không.** `jdk.httpserver` là JDK module được phân phối trong các JDK thông dụng. Với CLI `jwebserver`, không cần viết build file. Với Java source dùng `SimpleFileServer`, cần JDK 18+ và compiler/runtime có module này; dùng `--add-modules jdk.httpserver` trong lệnh compile/run mẫu để nêu rõ dependency.

Nếu chạy trong custom runtime image do `jlink` tạo ra, module hoặc CLI tool có thể không có tùy cách đóng gói. Không giả định một **JRE tối giản** sẽ chứa `jwebserver`.

## 16. Xử lý các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `jwebserver: command not found` | JDK cũ hoặc PATH sai | Dùng JDK 18+, kiểm tra `PATH/JAVA_HOME` |
| `cannot find symbol SimpleFileServer` | Build target Java 17 hoặc thiếu module | Biên dịch JDK 18+, `--release 18 --add-modules jdk.httpserver` |
| `UnsupportedClassVersionError` | Compile bằng Java mới, chạy bằng runtime cũ | Đồng bộ phiên bản compile/runtime |
| `Address already in use` | Port 8000 đã được server khác sử dụng | Chọn port khác hoặc dùng port 0 trong API |
| Dùng `-d ./static-demo` mà server trả 404 | Working directory khác kỳ vọng hoặc file không ở root | Kiểm tra path tuyệt đối, cấu trúc fixture và URI |
| `403`/lỗi quyền truy cập file | Filesystem không cho phép đọc một tài nguyên | Sửa quyền fixture, không chạy admin vô hạn |
| GET `/` trả listing thay vì HTML | Không có index file phù hợp | Đặt `index.html` vào root |
| GET `/assets/` lộ tên file | Directory listing là behavior mặc định khi thiếu index | Dùng root sạch, chỉ chứa file test |
| HEAD không có body | Đây là HTTP semantics đúng | Không đọc file bytes từ HEAD |
| POST không tạo file | Static server chỉ hỗ trợ GET/HEAD | Custom handler/service khác cho write |
| Frontend báo CORS | Không có header phù hợp với origin frontend | Cấu hình mock server có CORS response headers |
| Browser cache file cũ | Cache behavior không khớp test | Kiểm tra HTTP headers, tắt cache ở dev tools hoặc dùng endpoint phù hợp |
| `https://localhost:8000` thất bại | Simple Web Server là HTTP plaintext | Dùng `http://` cho fixture local; muốn HTTPS dùng server khác |
| Muốn HTTP/2 mà client nhận HTTP/1.1 | Simple Web Server không hỗ trợ HTTP/2 | Chọn server HTTP/2 khác cho test ALPN |
| Không truy cập được từ điện thoại | Server bind loopback của máy dev | Đừng đổi 0.0.0.0 khi chưa hiểu chia sẻ mạng và dữ liệu |
| Test treo vì server còn chạy | Quên `stop(0)` hoặc Ctrl+C | Quản lý lifecycle trong finally |
| Log verbose lộ path/header | Log quá chi tiết | Giảm về info/none và dùng fixture giả |
| File hidden/symlink xử lý khác kỳ vọng | Filesystem/OS/implementation khác nhau | Kiểm tra thực tế, không dùng server làm sandbox |
| `createOutputFilter(..., NONE)` báo lỗi | Factory này không chấp nhận NONE | Không tạo filter khi không cần log |

**Chẩn đoán có hệ thống:** kiểm tra JDK version → command help → bind address/port → document root → file tồn tại/quyền đọc → request method/path → HTTP status/content-type → dừng server. Không chuyển sang cổng mạng công khai hoặc chạy bằng quyền quản trị chỉ để "cho hết lỗi" trước khi biết nguyên nhân.

## 17. Kiểm thử hiệu năng và an toàn: đừng suy từ local thành production

Static server tối giản có thể phù hợp vài request từ localhost, nhưng không nên sử dụng để kết luận về:

- HTTP/2 multiplexing, TLS handshake, HTTP/3/QUIC.
- Hệ thống caching/CDN/edge proxy, HTTP compression, conditional GET phức tạp.
- Load balancing hoặc horizontal scaling.
- Authentication, authorization, bảo vệ dữ liệu cá nhân và audit.
- Rate limiting, quota, body/header limits và chống slow-client/DDoS.
- Khả năng chịu nhiều kết nối và traffic lớn so với server sản phẩm.
- Logging/observability và graceful shutdown của production.
- Security headers, content sniffing, clickjacking protection và CSP của site thật.

**JEP 408 chọn sự tối giản có chủ đích.** Càng nhiều yêu cầu production, càng nên dùng framework/container/reverse proxy chuyên dụng. Dùng một công cụ học tập đúng phạm vi sẽ giúp bài test dễ lặp lại hơn thay vì mang rủi ro không cần thiết.

## 18. Ma trận test đề xuất

| Trường hợp | Setup | Kiểm tra |
| --- | --- | --- |
| Static text | `hello.txt` UTF-8 | GET 200, body bytes đúng |
| Static HTML | `index.html` | GET / trả nội dung index |
| Directory listing | Thư mục con không có index | GET /sub/ trả listing, không vô tình lộ file riêng |
| Unknown resource | Không có file | 404 |
| HEAD | File tồn tại | 200, body rỗng |
| POST | Thử POST file | 405 hoặc 501, không ghi file |
| MIME | `.txt`/`.html` | Content-Type tương ứng với bảng MIME |
| Nested file | `assets/data.json` | Path ánh xạ đúng trong root |
| Port collision | Hai server cùng 8000 | Server thứ hai fail; API port 0 là giải pháp test |
| Directory invalid | Root không tồn tại/không đọc được | API từ chối/CLI báo lỗi, không phục vụ dir khác ngoài ý muốn |
| Hidden/symlink | Tài nguyên đặc biệt của OS | Kiểm tra không phục vụ ngoài root; không coi là security boundary |
| Unsupported protocol | HTTPS/HTTP2 | Không được giả định server hỗ trợ |
| Loopback | `-b 127.0.0.1` | Chỉ cần kết nối local để học/test |
| Verbose log | `-o verbose` | Không có secret trong URL/header/fixture |
| Cleanup | API stop/CLI Ctrl+C | Process, port và file fixture được dọn |
| Multiple tests | Port 0 + root riêng | Không giao thoa state, chạy độc lập |

Nếu cần test bằng CI, ưu tiên **API và port 0** hơn CLI hard-code port 8000, vì tránh xung đột và dễ gọi `server.stop(0)`. Lệnh jwebserver lại lý tưởng cho thao tác thủ công nhanh và giới thiệu HTTP static.

## 19. Bài tập thực hành

**Bài 1 — Version.** Tại sao người dùng JDK 17 biên dịch `SimpleFileServer.createFileServer(...)` lại lỗi? Phải dùng phiên bản nào và module gì?

**Bài 2 — jwebserver.** Có thư mục `demo-public` chỉ gồm `index.html` và `hello.txt`. Viết lệnh phục vụ ở `127.0.0.1:9000`, mức log `info`, không mở mọi interface.

**Bài 3 — HTTP methods.** Server static nhận `POST /hello.txt`. Có được tự hiểu request này là ghi đè file không? Kết quả HTTP nào là khả dĩ?

**Bài 4 — Directory listing.** Tại sao GET `/assets/` có thể trả HTML chứa tên file? Điều này liên quan thế nào tới nguy cơ xuất bản thông tin?

**Bài 5 — MIME.** Nếu một file đặt tên `report.json` nhưng chứa HTML không hợp lệ, `Content-Type` tự đoán theo extension có chứng minh payload là JSON không?

**Bài 6 — Loopback.** `jwebserver -b 0.0.0.0 -d .` có thể làm gì khác với `-b 127.0.0.1 -d ./static-demo`? Vì sao không nên dùng cách đầu trong repo?

**Bài 7 — API.** Khi dùng `new InetSocketAddress("127.0.0.1", 0)`, cách nào lấy port server thực sau khởi động? Tại sao hữu ích cho tests?

**Bài 8 — Output filter.** `createFileServer(..., OutputLevel.NONE)` và `createOutputFilter(..., OutputLevel.NONE)` có kết quả giống nhau không?

**Bài 9 — Composition.** Đã có HttpServer có route `/health`, muốn thêm static files ở `/files/`. Dùng factory nào và gắn vào đâu?

**Bài 10 — Production.** Một nhóm muốn dùng jwebserver làm public download server có tài khoản, HTTPS và rate-limits. Có phù hợp không? Nên đổi sang kiến trúc nào?

**Bài 11 — Testing.** Java HttpClient ưu tiên HTTP/2, gửi GET tới jwebserver và response.version() là HTTP_1_1. Đây có phải bug không?

**Bài 12 — Cleanup.** Vì sao không nên viết integration test tạo file trong directory thật của người dùng rồi dùng `Files.walk(...).forEach(delete)` trong finally?

### Gợi ý đáp án

1. JEP 408 xuất hiện ở JDK 18, Java 17 chưa có SimpleFileServer; dùng JDK 18+, module `jdk.httpserver`.
2. `jwebserver -b 127.0.0.1 -p 9000 -d ./demo-public -o info`.
3. Không. Chỉ GET/HEAD được phục vụ; method khác nhận 405/501 tùy ngữ cảnh.
4. Khi directory không có index, server có thể tạo directory listing. Phải phục vụ directory root sạch, không chứa tài liệu chưa công bố.
5. Không. MIME type tự đoán không thay nội dung file thực tế/validation.
6. 0.0.0.0 cho phép lắng nghe mọi interface, `.` có thể chứa tài liệu nhạy cảm. Loopback + thư mục public fixture giảm đáng kể phạm vi.
7. `server.getAddress().getPort()`; port 0 do OS chọn giúp tránh conflict và test song song.
8. Không. `createFileServer` chấp nhận NONE để không log, còn `createOutputFilter` với NONE ném IllegalArgumentException.
9. Dùng `SimpleFileServer.createFileHandler(root)` rồi `server.createContext("/files/", handler)`.
10. Không. Dùng server/reverse proxy production có HTTPS/auth/authorization/rate limits và audit.
11. Không. jwebserver phục vụ HTTP/1.1, client preference không buộc server phải HTTP/2.
12. Vì có thể xóa dữ liệu thật ngoài ý muốn; dùng directory tạm riêng do test tạo, kiểm tra ownership rồi cleanup.

## 20. Tài liệu tham khảo chính thức

- [JEP 408 — Simple Web Server (JDK 18)](https://openjdk.org/jeps/408): mục tiêu, phạm vi và giới hạn của công cụ.
- [Java SE 24 — SimpleFileServer](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): ba factory `createFileServer`, `createFileHandler`, `createOutputFilter` và yêu cầu root absolute.
- [Java SE 24 — SimpleFileServer.OutputLevel](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.OutputLevel.html): NONE/INFO/VERBOSE.
- [JDK jwebserver command guide](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jwebserver.html): options, default loopback/port, phương thức GET/HEAD và giới hạn.
- [dev.java — jwebserver tutorial](https://dev.java/learn/jvm/tool/jwebserver/): lệnh và tình huống sử dụng.
- [Inside Java — Java 18's Simple Web Server](https://inside.java/2022/04/08/simple-web-server/): giải thích sự khác nhau CLI và API.
- [Java SE 24 — HttpServer](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): lifecycle, context mapping, start/stop, port 0.
- [Java SE 24 — HttpClient](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpClient.html): thực hiện HTTP requests trong ví dụ.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): GET, HEAD, status codes, Content-Type và ngữ nghĩa response.
