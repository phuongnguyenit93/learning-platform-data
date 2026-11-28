# `createFileServer()`: khởi tạo máy chủ và gọi `start()` tường minh

> **Chương:** API SimpleFileServer  
> **Module học:** `JAVA_VERSION_JAVA18` — các thay đổi từ Java 18 còn hữu ích trên JDK hiện đại.  
> **Phạm vi bài:** Tìm hiểu hợp đồng `SimpleFileServer.createFileServer(...)`, ý nghĩa của server **đã tạo nhưng chưa khởi động**, cách gọi `start()` đúng thứ tự và quản lý vòng đời của `HttpServer`. `SimpleFileServer` xuất hiện từ Java 18; những API nền tảng như `HttpServer.start()` đã có từ trước và vẫn được sử dụng trên JDK hiện đại.

## 1. Vì sao `createFileServer()` và `start()` là hai bước?

Trong lúc phát triển ứng dụng Java, ta có thể cần mở nhanh một thư mục chứa tài nguyên HTML, CSS hoặc tệp mẫu để thử nghiệm qua HTTP. Từ Java 18, `SimpleFileServer` cho phép tạo máy chủ phục vụ tệp trực tiếp bằng một factory method. Tuy nhiên, **việc tạo đối tượng server không đồng nghĩa với việc server đã xử lý request**.

```java
HttpServer server = SimpleFileServer.createFileServer(
        address, rootDirectory, OutputLevel.INFO); // Bước 1: tạo và cấu hình

server.start();                                     // Bước 2: bắt đầu phục vụ
```

Giữa hai lệnh này có một ranh giới vòng đời quan trọng:

- `createFileServer(...)` tạo và **bind** một `HttpServer` vào địa chỉ đã cho, đồng thời đăng ký sẵn `HttpContext` tại `/` với file handler. Cổng có thể đã được chiếm giữ cho server này, nhưng luồng xử lý HTTP **chưa khởi chạy**.
- `start()` bắt đầu server trong một luồng nền, tiếp nhận và điều phối các request đến handler đã cấu hình.
- Khoảng thời gian trước `start()` là lúc thích hợp để thực hiện những tùy chỉnh cần hoàn tất trước khi chạy, chẳng hạn gán `Executor` hoặc đăng ký context bổ sung.

**Điểm cần nhớ:** Javadoc của `SimpleFileServer.createFileServer` ghi rõ đối tượng trả về **chưa được start**. Nếu quên gọi `start()`, chương trình có thể tạo server thành công nhưng client vẫn không nhận được nội dung tệp.

## 2. Hợp đồng API hiện hành

Phương thức nằm trong package `com.sun.net.httpserver`, module `jdk.httpserver`:

```java
public static HttpServer createFileServer(
        InetSocketAddress addr,
        Path rootDirectory,
        SimpleFileServer.OutputLevel outputLevel)
```

| Tham số | Kiểu | Ý nghĩa và yêu cầu |
| --- | --- | --- |
| `addr` | `InetSocketAddress` | IP và cổng mà máy chủ HTTP bind vào; chỉ định loopback khi chỉ cần truy cập cục bộ. |
| `rootDirectory` | `Path` | Thư mục gốc được chia sẻ; phải là **đường dẫn tuyệt đối**, tồn tại, là thư mục và đọc được. |
| `outputLevel` | `SimpleFileServer.OutputLevel` | Chọn mức log gửi tới `System.out`: `NONE`, `INFO` hoặc `VERBOSE`. |
| **Kết quả** | `HttpServer` | Server đã cấu hình file handler ở context `/` nhưng **chưa chạy**. |

Khi request được xử lý sau `start()`, file handler ánh xạ URL đến tài nguyên nằm trong thư mục gốc và các thư mục con. Nó hỗ trợ `GET`/`HEAD`; phương thức HTTP khác nhận phản hồi `405 Method Not Allowed`. Nếu path trỏ tới một thư mục, handler có thể trả danh sách tệp dạng HTML.

### Các lỗi được định nghĩa trong Javadoc

| Trường hợp | Ngoại lệ |
| --- | --- |
| `rootDirectory` tương đối, không tồn tại, không phải thư mục hoặc không đọc được | `IllegalArgumentException` |
| Bất kỳ tham số nào là `null` | `NullPointerException` |
| Lỗi I/O khi tạo hoặc bind server (ví dụ cổng không khả dụng) | `UncheckedIOException` |

Vì factory có thể bind vào cổng ngay khi được gọi, **cổng đã bị chiếm có thể làm hỏng bước khởi tạo**, trước khi chương trình tới `start()`. Đừng diễn giải mọi lỗi kết nối là do thiếu `start()`; cần xem nguyên nhân phát sinh ở giai đoạn nào.

Đối với ứng dụng có `module-info.java`, khai báo:

```java
module demo.file.server {
    requires jdk.httpserver;
}
```

Hai package `com.sun.net.httpserver` và `com.sun.net.httpserver.spi` là những package công khai được module `jdk.httpserver` export. Chúng là API đặc thù của JDK, khác với các lớp nội bộ không được export. Trong một ứng dụng chạy trên classpath, các import tương ứng sử dụng bình thường nếu JDK/runtime image có `jdk.httpserver`.

## 3. Sơ đồ vòng đời và thời điểm cấu hình

```text
Chưa có server
      │
      ▼
SimpleFileServer.createFileServer(addr, root, level)
      │  • bind địa chỉ/cổng
      │  • gắn HttpContext("/") với file handler
      ▼
ĐÃ TẠO — CHƯA START
      │  • có thể đăng ký thêm context
      │  • có thể setExecutor(...) nếu cần
      ▼
server.start()                     ← phải gọi tường minh
      │
      ▼
ĐANG CHẠY
      │  • nhận và xử lý HTTP exchanges
      │  • có thể GET/HEAD tệp đã cho phép
      ▼
server.stop(delay)                 ← chủ động dừng
      │
      ▼
ĐÃ DỪNG — không thể start() lại cùng đối tượng
```

**Bind và start không giống nhau.** Bind gắn socket với một địa chỉ mạng; start bắt đầu luồng phục vụ các kết nối. Khi cấu hình trước `start()`, bạn có thể phát hiện lỗi thư mục/cổng sớm, đăng ký thêm handler cần thiết và chọn cơ chế thực thi request.

`HttpServer.setExecutor(Executor)` phải được gọi **trước** `start()`. Nếu gọi sau khi server đã chạy, phương thức ném `IllegalStateException`. Nếu không đặt executor, server dùng cơ chế thực thi mặc định của `HttpServer`; không nên giả định đây là một thread pool có kích thước tự động phù hợp cho tải lớn.

## 4. Ví dụ đầy đủ: tạo, start, truy cập và stop

Ví dụ sau tập trung vào đúng vòng đời của `createFileServer()`. Nó sử dụng loopback `127.0.0.1` để thử nghiệm trên máy hiện tại, kiểm tra thư mục gốc trước khi tạo server, gọi `start()` đúng chỗ, sau đó dừng bằng `stop(2)` khi người chạy nhấn Enter.

**Bước chuẩn bị:** trong thư mục nơi chạy Java, tạo thư mục `public` với một tệp `hello.txt`, chẳng hạn nội dung `Xin chào từ Java HTTP server!`. Cần thực hiện bước này trước vì `createFileServer()` không tạo hộ thư mục còn thiếu.

Lưu mã thành `StartFileServerDemo.java`:

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class StartFileServerDemo {
    public static void main(String[] args) throws IOException {
        // 1. Chuyển path tương đối thành path tuyệt đối.
        Path root = Path.of("public").toAbsolutePath().normalize();
        if (!Files.isDirectory(root) || !Files.isReadable(root)) {
            throw new IllegalArgumentException(
                    "Thư mục public không tồn tại hoặc không đọc được: " + root);
        }

        // 2. Chỉ lắng nghe trên máy cục bộ, cổng 8000.
        InetSocketAddress address = new InetSocketAddress("127.0.0.1", 8000);

        // 3. Tạo server: đã bind và gắn handler ở "/", CHƯA start.
        HttpServer server = SimpleFileServer.createFileServer(
                address, root, OutputLevel.INFO);
        System.out.println("Server đã khởi tạo ở: " + server.getAddress());

        // 4. Bắt đầu nhận và xử lý request HTTP.
        server.start();
        System.out.println("Đang phục vụ: http://127.0.0.1:8000/hello.txt");
        System.out.println("Nhấn Enter để dừng server...");

        try {
            System.in.read();
        } finally {
            // 5. Dừng nhận kết nối mới và chờ request đang xử lý tối đa 2 giây.
            server.stop(2);
            System.out.println("Server đã dừng.");
        }
    }
}
```

Đây là Java thuần, không cần Gradle/Maven hoặc thư viện HTTP server bên thứ ba. Biên dịch và chạy bằng **JDK 18 trở lên**:

```bash
javac StartFileServerDemo.java
java StartFileServerDemo
```

Giữ chương trình đang chạy. Mở terminal khác để thử HTTP request:

```bash
curl -i http://127.0.0.1:8000/hello.txt
curl -I http://127.0.0.1:8000/hello.txt
curl -i -X POST http://127.0.0.1:8000/hello.txt
curl -i http://127.0.0.1:8000/not-found.txt
```

Trên **Windows PowerShell 5.1**, nên dùng `curl.exe` thay vì `curl` để gọi đúng chương trình curl (vì `curl` có thể là alias của PowerShell). Chẳng hạn:

```powershell
curl.exe -i http://127.0.0.1:8000/hello.txt
curl.exe -I http://127.0.0.1:8000/hello.txt
```

| Yêu cầu | Kết quả mong đợi | Điều cần quan sát |
| --- | --- | --- |
| `GET /hello.txt` | `200 OK` nếu tệp tồn tại và đọc được | Có nội dung file trong response body. |
| `HEAD /hello.txt` | `200 OK` nếu tệp tồn tại và đọc được | Có response headers, **không gửi body**. |
| `POST /hello.txt` | `405 Method Not Allowed` | File handler không xử lý upload hoặc thay đổi tệp. |
| `GET /not-found.txt` | Thường `404 Not Found` | Tệp không tồn tại dưới thư mục gốc. |
| `GET /` | HTML liệt kê thư mục | File handler có khả năng trả directory listing. |

Sau khi thử các yêu cầu, quay lại terminal chạy Java và **nhấn Enter**. `System.in.read()` trả về, `finally` gọi `server.stop(2)`, rồi chương trình thoát. Ví dụ dựa vào stdin tương tác; nếu chạy trong môi trường đã đóng stdin, nó có thể dừng ngay. Với ứng dụng service chạy lâu dài, dùng cơ chế quản lý vòng đời phù hợp thay cho việc đợi Enter.

## 5. `OutputLevel` ảnh hưởng gì đến lúc server chạy?

Factory nhận một trong ba giá trị enum:

| Giá trị | Hành vi khi sử dụng với `createFileServer()` |
| --- | --- |
| `OutputLevel.NONE` | Không in log trao đổi HTTP tự động. |
| `OutputLevel.INFO` | In các thông tin cơ bản theo kiểu Common Logfile Format: client, thời điểm, request, status; một số trường không được thu thập. |
| `OutputLevel.VERBOSE` | Ngoài thông tin mức INFO còn in request/response headers và đường dẫn tuyệt đối của tài nguyên được phục vụ. |

Ví dụ chỉ thay đổi mức log, giữ nguyên vòng đời:

```java
HttpServer server = SimpleFileServer.createFileServer(
        address, root, OutputLevel.NONE);
server.start();
```

Chọn `NONE` khi không cần log từ file server, `INFO` để xem request khi thử nghiệm, và `VERBOSE` khi cần tìm nguyên nhân lỗi. Với `VERBOSE`, header hoặc đường dẫn tuyệt đối có thể chứa thông tin nhạy cảm; tránh ghi dữ liệu thật hoặc chia sẻ log rộng rãi.

`OutputLevel.NONE` **hợp lệ** với `createFileServer()`. Tuy nhiên, nó **không hợp lệ** với `SimpleFileServer.createOutputFilter(out, OutputLevel.NONE)`: factory filter sẽ ném `IllegalArgumentException`. Hai factory có hợp đồng khác nhau; khi không cần output filter, chỉ cần không thêm filter.

## 6. Những cấu hình có thể thêm trước khi `start()`

### 6.1. Thêm endpoint HTTP riêng

Đối tượng nhận được là `HttpServer` thật, nên bạn có thể thêm `HttpContext` trước khi start. Ví dụ, chèn khối mã này **sau `createFileServer(...)` nhưng trước `server.start()`**:

```java
server.createContext("/health", exchange -> {
    byte[] body = "OK".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    exchange.getResponseHeaders()
            .set("Content-Type", "text/plain; charset=utf-8");
    exchange.sendResponseHeaders(200, body.length);
    try (var output = exchange.getResponseBody()) {
        output.write(body);
    }
});
```

Khi server chạy, `GET /health` sẽ được xử lý bởi handler vừa thêm; context `/` vẫn phục vụ tệp cho những đường dẫn tương ứng. Đây là ví dụ tối giản về cách kết hợp file server với API HTTP server công khai. Để xây endpoint thực tế, handler nên kiểm tra HTTP method và phân quyền nếu cần.

### 6.2. Gắn một executor để xử lý song song

Với ứng dụng cần chủ động quản lý số luồng xử lý request, có thể cấu hình một `ExecutorService` **trước `start()`**. Trong đoạn này, `server` là đối tượng được tạo bởi `createFileServer(...)`:

```java
java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newFixedThreadPool(4);
server.setExecutor(pool); // Phải trước server.start().
server.start();

try {
    System.in.read();
} finally {
    server.stop(2);
    pool.shutdown();
}
```

Đây là **đoạn thay thế** phần `start()` và `stop()` trong ví dụ đầy đủ, không phải đoạn cần gọi thêm sau khi server đã start. `pool.shutdown()` dừng việc nhận task mới của executor do ứng dụng tự tạo; `server.stop(2)` giải phóng tài nguyên của HTTP server. Khi không cần tùy chỉnh, việc bỏ `setExecutor` là hợp lệ.

### 6.3. Cho hệ điều hành cấp cổng tự do

Trong bài thử nghiệm tự động, không nên giả định cổng `8000` luôn rảnh. `InetSocketAddress` với cổng `0` cho phép hệ điều hành chọn một cổng khả dụng khi bind:

```java
InetSocketAddress address = new InetSocketAddress("127.0.0.1", 0);
HttpServer server = SimpleFileServer.createFileServer(
        address, root, OutputLevel.NONE);
int actualPort = server.getAddress().getPort(); // Đọc cổng đã được cấp.
server.start();
System.out.println("http://127.0.0.1:" + actualPort + "/hello.txt");
```

Nên lấy cổng thực tế qua `server.getAddress().getPort()` **sau khi factory đã bind**; đừng tự ghép URL với cổng `0`. Cũng cần chủ động dừng server khi hoàn thành bài test.

## 7. Những sai sót thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
| --- | --- | --- |
| Chương trình in “đã tạo server” nhưng không phục vụ request | Quên `server.start()` | Đặt `start()` sau tất cả bước cấu hình và trước khi gửi thử request. |
| `IllegalArgumentException` khi tạo server | Path tương đối, thư mục không tồn tại/không có quyền đọc | In `root.toAbsolutePath()`; kiểm tra `Files.isDirectory`, `Files.isReadable`. |
| `UncheckedIOException` khi tạo server | Lỗi I/O/bind, có thể do cổng đã được sử dụng | Xem nguyên nhân gốc của ngoại lệ; thử cổng trống hoặc cổng `0`. |
| `NullPointerException` tại factory | Một trong ba đối số `null` | Kiểm tra `addr`, `rootDirectory` và `outputLevel`. |
| `IllegalStateException` khi gán executor | `server.setExecutor` gọi sau `start()` | Chuyển lệnh `setExecutor` lên trước `start()`. |
| Server chạy nhưng `GET` trả `404` | URL không trỏ tới tệp có trong thư mục gốc | Kiểm tra tệp và working directory lúc khởi chạy. |
| `POST` trả `405` | Hợp đồng file handler chỉ hỗ trợ `GET` và `HEAD` | Viết `HttpHandler` riêng nếu có nghiệp vụ cần phương thức khác. |
| Không thể khởi động lại sau `stop(delay)` | Một `HttpServer` đã dừng không thể tái sử dụng | Tạo `HttpServer` mới nếu cần phục vụ tiếp. |

Đừng nhầm `start()` với cơ chế sẵn sàng của một ứng dụng production: API chỉ đảm nhận vòng đời HTTP server tối giản. Nếu ứng dụng cần kiểm soát trạng thái phức tạp, bạn phải chủ động xây kiểm tra health/readiness và cơ chế shutdown.

## 8. Ranh giới sử dụng và tính an toàn

- **Dùng đúng mục đích:** Javadoc xác định `SimpleFileServer` dành cho **testing, development và debugging**. Nó không tự cung cấp kiến trúc quản lý xác thực, phân quyền, HTTPS hay các tính năng vận hành chuyên sâu cho production.
- **Giới hạn phạm vi truy cập:** bind `127.0.0.1` nếu chỉ thử nội bộ. Không đổi sang `0.0.0.0` nếu chưa xác định ai có thể truy cập dịch vụ qua mạng.
- **Chỉ chia sẻ thư mục chủ động lựa chọn:** file handler có thể cho xem danh sách thư mục; không trỏ `rootDirectory` đến thư mục chứa mật khẩu, khóa API, mã nguồn riêng hoặc dữ liệu khách hàng.
- **Không dùng như API ghi file:** file handler chỉ đọc tệp qua `GET`/`HEAD`. Muốn xử lý `POST`, `PUT`, `DELETE` cần handler riêng có kiểm tra dữ liệu và quyền truy cập phù hợp.
- **Quản lý vòng đời:** gọi `start()` một lần, chuẩn bị cách dừng tiến trình và `stop(delay)` ở luồng shutdown; tránh để server chạy ngoài ý muốn.

Khi chỉ muốn phục vụ thư mục mà không viết Java, công cụ `jwebserver` đi kèm JDK hiện đại là một lựa chọn khác. Tuy nhiên, khi viết Java để cấu hình `HttpServer`, **phải gọi `start()` trên đối tượng đã tạo**.

## 9. Câu hỏi tự kiểm tra và bài tập

1. `createFileServer()` trả về kiểu gì? Nó đã bind địa chỉ/cổng và đã đăng ký context nào?
2. Vì sao một đoạn mã chỉ gọi `createFileServer(...)` vẫn chưa phục vụ được HTTP request?
3. Khi cần `setExecutor`, phải gọi trước hay sau `start()`? Điều gì xảy ra nếu gọi sai thời điểm?
4. Vì sao `rootDirectory = Path.of("public")` có thể gây lỗi, còn `Path.of("public").toAbsolutePath().normalize()` thường phù hợp hơn?
5. Khi `GET /hello.txt` thành công nhưng `POST /hello.txt` nhận `405`, đó có phải lỗi của `start()` không?
6. Sự khác nhau giữa `OutputLevel.NONE`, `INFO` và `VERBOSE` là gì? Mức nào có thể in headers?
7. `server.stop(2)` hoạt động thế nào và có cho phép gọi lại `start()` trên cùng đối tượng không?
8. Nếu cấu hình địa chỉ với cổng `0`, làm thế nào lấy đúng URL để dùng `curl`?

**Bài thực hành:** chạy `StartFileServerDemo`, thử `GET`/`HEAD`/`POST`, quan sát log `INFO` và dừng bằng Enter. Sau đó lần lượt thử đổi `INFO` sang `NONE`, đổi cổng `8000` sang `0` (nhớ in cổng thực tế), và thêm endpoint `/health` trước `start()`. Ghi lại thay đổi quan sát được ở từng lần chạy.

## Tài liệu chính thức

- [Oracle JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): hợp đồng `createFileServer()`, trạng thái chưa start, các ngoại lệ và file handler.
- [Oracle JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `start()`, `stop(delay)`, `setExecutor`, `getAddress()` và `createContext()`.
- [Oracle JDK 27 — `SimpleFileServer.OutputLevel`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.OutputLevel.html): mức độ logging và thông tin được ghi.
- [Oracle JDK 27 — module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): module và các package HTTP Server API được export.
- [Oracle JDK 18 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): đối chiếu API được giới thiệu từ Java 18.
