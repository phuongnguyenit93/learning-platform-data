# `OutputLevel.NONE`, `INFO` và `VERBOSE`: cân bằng quan sát với dữ liệu xuất hiện trong log

> **Chương:** API SimpleFileServer  
> **Module học:** `JAVA_VERSION_JAVA18` — `SimpleFileServer` được bổ sung từ Java 18 và vẫn có trong JDK hiện đại.  
> **Mục tiêu:** Chọn đúng mức ghi log, phân biệt log tích hợp của `createFileServer` với `createOutputFilter`, hiểu nội dung được ghi ở `INFO`/`VERBOSE`, và tránh để log làm lộ thông tin nhạy cảm.

## 1. Log của SimpleFileServer dùng để làm gì?

`SimpleFileServer` là file server HTTP tối giản, được thiết kế cho **testing, development và debugging**. Khi thử nghiệm, log giúp trả lời những câu hỏi như:

- Client nào vừa gửi request đến server?
- Client yêu cầu đường dẫn nào, dùng phương thức HTTP nào?
- Server trả về status code nào?
- Khi bật mức chi tiết, request/response headers và tệp thực tế nào được phục vụ?

Java 18 cung cấp enum `SimpleFileServer.OutputLevel` với ba giá trị:

```java
SimpleFileServer.OutputLevel.NONE
SimpleFileServer.OutputLevel.INFO
SimpleFileServer.OutputLevel.VERBOSE
```

Đây là **các mức chọn đầu ra**, không phải logger framework tổng quát như SLF4J hoặc JUL. `SimpleFileServer` không cung cấp sẵn cấu hình rolling file, retention, structured JSON, redaction theo tên header hoặc bộ lọc theo mức log tùy ý. Nếu ứng dụng cần các chức năng vận hành đó, cần tự xây dựng cơ chế logging phù hợp.

## 2. Ba mức `NONE`, `INFO`, `VERBOSE`

### 2.1. `OutputLevel.NONE`: không ghi log

`NONE` yêu cầu file server không in log trao đổi HTTP:

```java
HttpServer server = SimpleFileServer.createFileServer(
        address, root, SimpleFileServer.OutputLevel.NONE);
server.start();
```

Đây là lựa chọn phù hợp khi test không cần quan sát từng request hoặc muốn giữ terminal output gọn. Nó **không tắt HTTP server**, không chặn request và không làm thay đổi status/body của response. Server vẫn phục vụ nội dung như bình thường.

Với factory `createOutputFilter(...)`, có một điểm khác: `OutputLevel.NONE` **không hợp lệ**. Nếu không muốn ghi log, hãy **không gắn output filter**. Truyền `NONE` vào `createOutputFilter` sẽ ném `IllegalArgumentException`.

### 2.2. `OutputLevel.INFO`: thông tin request cơ bản

`INFO` ghi một dòng log theo định dạng dựa trên **Common Logfile Format (CLF)**. Dòng log có các trường:

```text
remotehost rfc931 authuser [date] "request" status bytes
```

Ví dụ minh họa trong Javadoc:

```text
127.0.0.1 - - [22/Jun/2000:13:55:36 -0700] "GET /example.txt HTTP/1.1" 200 -
```

Ý nghĩa:

| Trường | Ý nghĩa |
| --- | --- |
| `remotehost` | Địa chỉ client mà server quan sát được. |
| `rfc931` | Trường định danh theo CLF. |
| `authuser` | Tên người dùng đã xác thực theo định dạng CLF. |
| `[date]` | Thời điểm xử lý request. |
| `"request"` | Request line, gồm phương thức, request target và phiên bản HTTP. |
| `status` | Mã trạng thái HTTP server trả về. |
| `bytes` | Trường số byte của response theo CLF. |

**Lưu ý theo implementation note của Javadoc:** triển khai JDK hiện hành không thu thập các trường `rfc931`, `authuser` và `bytes`; chúng luôn được biểu diễn bằng dấu gạch ngang (`-`). Vì vậy không dùng trường `bytes` trong log này để đo dung lượng response hoặc tính traffic.

`INFO` phù hợp cho việc quan sát request/status khi phát triển. Tuy vậy, request line có thể chứa query string; nếu ứng dụng đặt token, email, mã định danh hoặc dữ liệu cá nhân trong URL, thông tin đó có thể xuất hiện trong log ngay cả khi không bật `VERBOSE`.

### 2.3. `OutputLevel.VERBOSE`: thêm headers và đường dẫn tài nguyên

`VERBOSE` bao gồm thông tin của `INFO`, đồng thời ghi:

- Request headers.
- Response headers.
- Đường dẫn tuyệt đối của tài nguyên được phục vụ.

Ví dụ, khi client gửi:

```http
GET /report.csv HTTP/1.1
Host: 127.0.0.1:8080
Authorization: Bearer example-token
Cookie: session=example-session
```

Mức `VERBOSE` có thể làm các header như `Authorization` hoặc `Cookie` xuất hiện trong log. Ở chiều response, những header như `Set-Cookie` hoặc header tùy biến chứa token cũng có thể bị ghi. Đường dẫn tuyệt đối có thể tiết lộ cấu trúc thư mục của máy chạy server.

Do đó, **không bật `VERBOSE` một cách mặc định trên dữ liệu thật**. Chỉ bật khi cần chẩn đoán, trong thời gian ngắn và với dữ liệu thử nghiệm không nhạy cảm. Nếu phải ghi log chi tiết trong môi trường có thông tin riêng tư, cần cơ chế redaction có chủ đích; output filter có sẵn không cung cấp cấu hình che header.

### 2.4. Bảng so sánh

| Mức | Nội dung chính | Đích ghi của `createFileServer` | Có phù hợp khi không muốn log? |
| --- | --- | --- | --- |
| `NONE` | Không ghi log | Không in ra `System.out` | Có |
| `INFO` | CLF: remote host, ngày giờ, request line, status; một số trường luôn là `-` | `System.out` | Không |
| `VERBOSE` | INFO + request/response headers + đường dẫn tuyệt đối của tài nguyên | `System.out` | Không |

Mức càng chi tiết thì lượng dữ liệu được ghi càng lớn, và nguy cơ lộ thông tin càng cao. Không nên coi `VERBOSE` là “tốt hơn” trong mọi trường hợp.

## 3. Log tích hợp trong `createFileServer(...)`

Factory:

```java
HttpServer createFileServer(
        InetSocketAddress addr,
        Path rootDirectory,
        SimpleFileServer.OutputLevel outputLevel)
```

Khi dùng factory này, mức log được chọn trực tiếp trong tham số thứ ba. Nếu chọn `INFO` hoặc `VERBOSE`, thông tin được ghi vào **`System.out`**. Nếu chọn `NONE`, server không in log trao đổi HTTP.

Ví dụ:

```java
Path root = Path.of("public").toAbsolutePath().normalize();
InetSocketAddress address = new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 0);

HttpServer server = SimpleFileServer.createFileServer(
        address, root, SimpleFileServer.OutputLevel.INFO);

int port = server.getAddress().getPort();
server.start();
System.out.println("File server port: " + port);
```

Trong ví dụ, log request do file server ghi ra stdout. Lệnh `System.out.println` cuối cùng cũng ghi ra stdout, nhưng đó là thông báo do ứng dụng tự in, không phải một dòng log của `SimpleFileServer`.

Nếu muốn kiểm soát mức chi tiết, chỉ cần thay enum:

```java
SimpleFileServer.OutputLevel.NONE
SimpleFileServer.OutputLevel.INFO
SimpleFileServer.OutputLevel.VERBOSE
```

Không cần tạo thêm `Filter` nếu chỉ dùng log tích hợp của `createFileServer`. Tránh gắn một output filter giống chức năng vào cùng context nếu không muốn cùng một exchange bị ghi lặp.

## 4. Dùng `createOutputFilter(...)` để chọn đích ghi

Khi ứng dụng đã có `HttpServer` và muốn tự chọn nơi ghi log, dùng factory:

```java
Filter createOutputFilter(
        OutputStream out,
        SimpleFileServer.OutputLevel outputLevel)
```

Filter được tạo là **post-processing filter**: nó ghi thông tin về các exchange đã đi qua handler/chuỗi filter. Log được ghi vào `OutputStream` truyền vào, sử dụng **UTF-8**. Factory chấp nhận `INFO` và `VERBOSE`; truyền `NONE` sẽ ném `IllegalArgumentException`. Nếu không muốn log, không gắn filter.

### 4.1. Ghi log ra `System.out`

```java
Path root = Path.of("public").toAbsolutePath().normalize();
InetSocketAddress address = new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 0);

HttpServer server = HttpServer.create(address, 0);
HttpContext files = server.createContext(
        "/files", SimpleFileServer.createFileHandler(root));

Filter output = SimpleFileServer.createOutputFilter(
        System.out, SimpleFileServer.OutputLevel.INFO);
files.getFilters().add(output);

server.start();
```

Đây là cách dùng khi muốn tạo server thủ công, gắn file handler vào context riêng và chọn filter. Log chỉ áp dụng cho context `/files` vì filter được thêm vào `files.getFilters()`; nó không tự động áp dụng cho mọi context của server.

### 4.2. Ghi log vào file UTF-8

Ví dụ sau tạo log file riêng, dùng chế độ append và đặt nó **bên ngoài thư mục gốc đang được phục vụ**:

```java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileServerWithLogFile {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("public").toAbsolutePath().normalize();
        if (!Files.isDirectory(root) || !Files.isReadable(root)) {
            throw new IllegalArgumentException("Thư mục public không hợp lệ: " + root);
        }

        Path logPath = Path.of("logs", "simple-file-server.log")
                .toAbsolutePath().normalize();
        if (logPath.startsWith(root)) {
            throw new IllegalArgumentException(
                    "Log phải nằm ngoài thư mục được phục vụ: " + logPath);
        }
        Files.createDirectories(logPath.getParent());

        try (OutputStream logStream = Files.newOutputStream(
                logPath, StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
            try {
                HttpContext files = server.createContext(
                        "/files", SimpleFileServer.createFileHandler(root));
                Filter output = SimpleFileServer.createOutputFilter(
                        logStream, OutputLevel.INFO);
                files.getFilters().add(output);

                server.start();
                System.out.println(
                        "File server port: " + server.getAddress().getPort());
                System.in.read();
            } finally {
                server.stop(1);
            }
        }
    }
}
```

Biên dịch và chạy trên JDK 18 trở lên sau khi tạo thư mục `public`:

```bash
javac FileServerWithLogFile.java
java FileServerWithLogFile
```

`try-with-resources` đóng log stream sau khi khối xử lý kết thúc; `finally` dừng server trước. Không đóng `System.out` khi truyền stream này vào filter.

**Vì sao phải để log ngoài root?** File handler phục vụ các tệp dưới thư mục gốc. Nếu log file được đặt trong `public`, client có thể request chính đường dẫn log và đọc nội dung đã ghi. Việc ghi log ra đĩa không tự tạo vùng riêng tư; vị trí file và quyền hệ thống tệp rất quan trọng.

## 5. Chọn mức log theo mục tiêu

| Tình huống | Lựa chọn đề xuất | Lý do |
| --- | --- | --- |
| Test tự động chỉ cần kiểm tra status/body | `NONE` | Giữ output test gọn, tránh log không cần thiết. |
| Phát triển cục bộ, cần biết request và status | `INFO` | Đủ thông tin cơ bản để quan sát trao đổi HTTP. |
| Điều tra lỗi tạm thời cần xem headers hoặc tệp được phục vụ | `VERBOSE` | Cung cấp dữ liệu chi tiết hơn; cần kiểm soát nội dung và thời gian bật. |
| Muốn ghi log vào file/stream do ứng dụng quản lý | `createOutputFilter(out, INFO/VERBOSE)` | Chọn được `OutputStream` đích thay vì mặc định stdout. |
| Không muốn log ở context cụ thể | Không gắn output filter vào context đó | `createOutputFilter(..., NONE)` không hợp lệ. |
| Cần log JSON, che token, xoay vòng file, retention hoặc gửi log tập trung | Logger/filter riêng | Output filter có sẵn không cung cấp các tùy chỉnh này. |

Một quy trình thực tế có thể là:

1. Dùng `NONE` cho test không cần quan sát.
2. Dùng `INFO` khi phát triển để biết request nào trả status bất thường.
3. Chỉ chuyển sang `VERBOSE` khi cần xem headers/đường dẫn, dùng dữ liệu thử nghiệm và tắt ngay sau khi tìm được nguyên nhân.
4. Nếu cần giữ log dài hạn hoặc có dữ liệu nhạy cảm, tự định nghĩa trường log và chính sách che dữ liệu thay vì ghi toàn bộ headers.

## 6. Dữ liệu nhạy cảm có thể lọt vào log như thế nào?

### 6.1. Dữ liệu trong URL

Mức `INFO` ghi request line, vì vậy request target có thể xuất hiện trong log:

```text
GET /download?token=example-secret HTTP/1.1
```

Không đặt mật khẩu, access token, session ID, email hoặc dữ liệu cá nhân trong query string nếu có thể tránh. URL thường xuất hiện ở nhiều nơi khác nhau như lịch sử trình duyệt, proxy, analytics và log server.

### 6.2. Dữ liệu trong headers

`VERBOSE` ghi request/response headers. Các header cần đặc biệt chú ý:

| Header | Nguy cơ khi ghi log |
| --- | --- |
| `Authorization` | Có thể chứa bearer token hoặc thông tin xác thực. |
| `Cookie` | Có thể chứa session identifier hoặc trạng thái đăng nhập. |
| `Set-Cookie` | Response có thể cấp session cookie hoặc thông tin xác thực phiên. |
| Header tùy biến như `X-Api-Key` | Có thể chứa API key hoặc credential riêng. |
| Header định danh nội bộ | Có thể tiết lộ ID người dùng, tenant hoặc thông tin hệ thống. |

Ngoài ra, đường dẫn tuyệt đối của tài nguyên có thể để lộ username hệ điều hành, tên ổ đĩa, cấu trúc thư mục hoặc tên dự án nội bộ.

### 6.3. Cách giảm rủi ro

- Không bật `VERBOSE` trên request chứa thông tin thật nếu chưa đánh giá dữ liệu sẽ ghi.
- Không đưa credential vào query string hoặc URL path.
- Chỉ ghi log vào nơi có quyền truy cập giới hạn; tránh thư mục được file server phục vụ.
- Nếu log được gửi tới CI artifact, log aggregation hoặc ticket hỗ trợ, xem đó là một bản sao dữ liệu cần kiểm soát quyền truy cập và thời gian lưu.
- Khi cần redaction, hãy dùng filter/logger riêng để chỉ ghi các trường đã chọn. `createOutputFilter` không có API cấu hình danh sách header được phép hoặc header phải che.
- Không xem log `INFO` là hoàn toàn không nhạy cảm: request line vẫn có thể chứa dữ liệu do ứng dụng đặt trong URL.

## 7. Phân biệt log của file server và log do ứng dụng tự tạo

`SimpleFileServer` chỉ ghi những trường do mức output của nó quy định. Nó không phải logger tổng quát cho toàn bộ ứng dụng:

- `createFileServer(..., INFO/VERBOSE)` ghi log của file server ra `System.out`.
- `createOutputFilter(out, level)` ghi log các exchange đi qua context gắn filter vào `OutputStream` chỉ định.
- `createFileHandler(root)` tự nó không thêm logging filter.
- Log của endpoint khác, exception trong nghiệp vụ, thời gian xử lý chi tiết, correlation ID hoặc dữ liệu audit cần được ứng dụng ghi riêng.

Không nên gắn cùng một output filter hai lần vào cùng context hoặc vừa bật log tích hợp vừa thêm filter tương đương nếu không muốn log trùng. Nếu server có nhiều context, mỗi context có danh sách filter riêng; muốn quan sát nhiều route cần gắn filter phù hợp vào từng context.

Nếu muốn kiểm soát sâu hơn, có thể tự viết `Filter` dùng `beforeHandler`, `afterHandler` hoặc triển khai `doFilter`. Khi đó hãy ghi đúng những dữ liệu cần thiết, tránh log body hoặc credential, và bảo đảm xử lý đồng thời/đóng stream phù hợp với lifecycle của server.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `createOutputFilter(System.out, NONE)` ném `IllegalArgumentException` | `NONE` không hợp lệ cho output filter. | Không gắn filter nếu không cần log. |
| Chọn `INFO` nhưng không thấy request/response headers | Headers chỉ xuất hiện ở `VERBOSE`. | Chỉ bật `VERBOSE` tạm thời khi dữ liệu an toàn. |
| Chọn `VERBOSE` nhưng log chứa token/cookie | Filter ghi toàn bộ request/response headers. | Tắt verbose; dùng filter riêng có redaction nếu cần. |
| Không thấy log của một endpoint | Filter chỉ được gắn vào context khác. | Gắn filter vào context xử lý endpoint đó. |
| Log file rỗng dù filter đã tạo | Server chưa start, request không đi qua context hoặc stream chưa được flush/đóng đúng lifecycle. | Kiểm tra start, route, filter và đóng stream sau stop. |
| Client tải được file log | Log nằm dưới `rootDirectory` đang phục vụ. | Chuyển log ra thư mục ngoài root và giới hạn quyền đọc. |
| Thấy dấu gạch ngang ở trường `bytes` | JDK implementation không thu thập trường này trong CLF output. | Không dùng trường đó để thống kê dung lượng; tự đo bằng cơ chế khác nếu cần. |

## 9. Bài tập và câu hỏi tự kiểm tra

**Bài thực hành:** chạy file server ba lần với `NONE`, `INFO`, `VERBOSE`; gửi lần lượt `GET /hello.txt` và `HEAD /hello.txt`. So sánh output. Sau đó dùng `createOutputFilter` với một file log bên ngoài `rootDirectory`, xác nhận nội dung được ghi UTF-8 và client không thể request file log qua file server.

1. `OutputLevel.NONE` có làm file server ngừng phục vụ request không?
2. Vì sao `NONE` hợp lệ với `createFileServer` nhưng không hợp lệ với `createOutputFilter`?
3. `INFO` dựa trên định dạng log nào? Những trường nào JDK implementation hiện hành luôn ghi là `-`?
4. `VERBOSE` bổ sung những thông tin gì so với `INFO`?
5. Vì sao `INFO` vẫn có thể làm lộ token nếu ứng dụng đặt token trong query string?
6. Những header nào thường chứa dữ liệu nhạy cảm và có thể xuất hiện ở `VERBOSE`?
7. `createFileServer(..., INFO)` ghi log ra đâu? `createOutputFilter(out, INFO)` ghi log ra đâu và dùng encoding nào?
8. Vì sao output filter không tự động áp dụng cho mọi context của server?
9. Vì sao log file cần được đặt ngoài `rootDirectory`?
10. Khi cần redaction, JSON log hoặc retention, vì sao nên viết filter/logger riêng?

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `SimpleFileServer.OutputLevel`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.OutputLevel.html): ý nghĩa `NONE`, `INFO`, `VERBOSE`; Common Logfile Format; trường không được thu thập; headers và absolute path ở verbose.
- [Oracle JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): `createFileServer`, `createOutputFilter`, stdout, UTF-8, post-processing và ngoại lệ khi dùng `NONE`.
- [Oracle JDK 27 — `Filter`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html): vị trí filter trong chuỗi xử lý HTTP.
- [Oracle JDK 27 — `HttpContext`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): danh sách filter được gắn theo context.
- [Oracle JDK 18 — `SimpleFileServer.OutputLevel`](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.OutputLevel.html): đối chiếu enum và các mức log từ phiên bản giới thiệu.
