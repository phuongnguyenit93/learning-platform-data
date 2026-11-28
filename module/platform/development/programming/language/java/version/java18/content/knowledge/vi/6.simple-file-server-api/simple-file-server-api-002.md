# Ba thành phần của `SimpleFileServer`: `HttpServer`, `HttpHandler` và `Filter`

> **Chương:** API SimpleFileServer  
> **Phạm vi:** `JAVA_VERSION_JAVA18`, tập trung vào chức năng được đưa vào Java 18 và vẫn có hiệu lực trên JDK hiện đại.  
> **Mục tiêu:** Hiểu sự phối hợp của ba thành phần, lựa chọn factory method phù hợp, ghép HTTP endpoint với file server và sử dụng logging filter đúng hợp đồng API.

## 1. Mô hình ba thành phần

`SimpleFileServer` thuộc package `com.sun.net.httpserver`, nằm trong module `jdk.httpserver`. Từ Java 18, lớp này cung cấp một file server HTTP tối giản để thử nghiệm, phát triển và gỡ lỗi. Theo Javadoc hiện hành, file server được cấu thành từ **ba thành phần**:

| Thành phần | Trách nhiệm | API nhà máy tương ứng |
| --- | --- | --- |
| **`HttpServer`** | Gắn với địa chỉ IP/cổng, nhận kết nối, chọn `HttpContext` và quản lý vòng đời server. | `SimpleFileServer.createFileServer(addr, root, level)` |
| **`HttpHandler`** | Nhận một `HttpExchange`, tra cứu tài nguyên trong thư mục gốc, trả về nội dung tệp hoặc danh sách thư mục. | `SimpleFileServer.createFileHandler(root)` |
| **`Filter` (tùy chọn)** | Ghi thông tin trao đổi HTTP sau khi handler xử lý; có thể kết hợp với những filter khác. | `SimpleFileServer.createOutputFilter(out, level)` |

`SimpleFileServer` là một **lớp `final` chứa các static factory method**. Nó **không** là một kiểu server riêng để `new SimpleFileServer()`; đối tượng nhận được vẫn là `HttpServer`, `HttpHandler` hoặc `Filter` trong HTTP Server API của JDK.

`HttpContext` đóng vai trò **liên kết** giữa ba thành phần: server chọn context theo request path; context chứa handler và danh sách filter. `HttpExchange` đại diện cho một yêu cầu và phản hồi HTTP cụ thể.

```text
Client gửi HTTP request
        │
        ▼
HttpServer (địa chỉ, cổng, vòng đời)
        │ chọn HttpContext phù hợp
        ▼
HttpContext (URI path + handler + filters)
        │
        ├── Filter trước handler (nếu được gắn)
        │
        ▼
HttpHandler.handle(HttpExchange)
        │ đọc request, gửi status / headers / body
        ▼
Filter sau handler (nếu được gắn)
        │
        ▼
HTTP response đến client
```

Ba thành phần **không phải ba server độc lập**. Việc tạo một `HttpHandler` hoặc `Filter` chỉ tạo đối tượng có thể tái sử dụng; muốn nhận yêu cầu HTTP, ứng dụng vẫn cần một `HttpServer` đang chạy và context gắn với handler.

## 2. Thành phần thứ nhất: `HttpServer` tạo bằng `createFileServer`

Chữ ký công khai:

```java
static HttpServer createFileServer(
    InetSocketAddress addr,
    Path rootDirectory,
    SimpleFileServer.OutputLevel outputLevel
)
```

Factory trả về một `HttpServer` đã được cấu hình để phục vụ nội dung từ `rootDirectory`. Nó tạo sẵn `HttpContext` tại path `/`, với file handler tương đương kết quả của `createFileHandler(rootDirectory)`. Server **chưa chạy**: phải gọi `start()` để bắt đầu nhận kết nối.

`addr` chỉ định địa chỉ IP và cổng lắng nghe. `rootDirectory` phải là **đường dẫn tuyệt đối**, trỏ đến thư mục **đã tồn tại và có quyền đọc**. `outputLevel` quyết định việc ghi log ra `System.out`.

### Ví dụ 1: phục vụ thư mục `public` với ít mã nhất

Chuẩn bị thư mục `public` trong working directory của chương trình và đặt `hello.txt` chứa một dòng văn bản vào đó. Lưu mã sau thành `QuickFileServer.java`:

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class QuickFileServer {
    public static void main(String[] args) {
        Path root = Path.of("public").toAbsolutePath().normalize();
        if (!Files.isDirectory(root) || !Files.isReadable(root)) {
            throw new IllegalArgumentException("Thư mục public chưa sẵn sàng: " + root);
        }

        InetSocketAddress address =
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 8000);

        HttpServer server = SimpleFileServer.createFileServer(
                address, root, OutputLevel.INFO);

        server.start(); // Bắt buộc: factory chỉ tạo server.
        System.out.println("Đang phục vụ tệp tại http://localhost:8000/");
    }
}
```

Biên dịch/chạy bằng JDK 18 trở lên:

```bash
javac QuickFileServer.java
java QuickFileServer
```

Trong terminal khác, gửi request:

```bash
curl -i http://localhost:8000/hello.txt
curl -I http://localhost:8000/hello.txt
curl -i -X POST http://localhost:8000/hello.txt
```

`GET` lấy nội dung; `HEAD` lấy metadata phản hồi mà không tải phần body; `POST` nhận mã **405 Method Not Allowed** vì file handler chỉ hỗ trợ `GET` và `HEAD`. Server vẫn chạy sau khi `main` kết thúc; dùng `Ctrl+C` để dừng tiến trình thử nghiệm.

Mỗi `HttpServer` cần quản lý vòng đời bằng `start()` và `stop(int delay)`. Có thể tạo thêm context hoặc gán `Executor` trước khi gọi `start()`. Server đã `stop` không được khởi động lại; muốn chạy tiếp thì tạo server mới.

> **Chú ý về cổng:** Ví dụ sử dụng cổng `8000` để dễ thử nghiệm. Nếu bị chiếm, đổi sang cổng khác. `InetAddress.getLoopbackAddress()` giữ phạm vi truy cập trong máy cục bộ; khi cố tình bind ra mọi giao diện mạng, cần hiểu rằng người khác có thể truy cập các tệp được phục vụ.

## 3. Thành phần thứ hai: `HttpHandler` tạo bằng `createFileHandler`

Chữ ký công khai:

```java
static HttpHandler createFileHandler(Path rootDirectory)
```

Factory này chỉ trả về **handler**, không tự mở cổng, không tự tạo server hoặc context. Điều này hữu ích khi ứng dụng đã có `HttpServer` và cần ghép file server với các endpoint khác, ví dụ `/health`.

Hợp đồng quan trọng của file handler:

| Yêu cầu | Hành vi |
| --- | --- |
| `GET /hello.txt`, tệp tồn tại | Trả nội dung tệp và `Content-Type` được suy đoán từ cơ chế MIME của hệ thống. |
| `HEAD /hello.txt` | Trả metadata của phản hồi tương ứng, không gửi body. |
| `GET /`, path tương ứng với thư mục | Trả **danh sách thư mục định dạng HTML**; không nên giả định có cơ chế tự chọn `index.html` kiểu web framework. |
| `GET /missing.txt`, tài nguyên không tồn tại | Trả phản hồi lỗi tương ứng, thông thường `404 Not Found`. |
| `POST`, `PUT`, `DELETE` hoặc phương thức khác `GET`/`HEAD` | Trả `405 Method Not Allowed`. |

Path `rootDirectory` cũng phải tuyệt đối, tồn tại, là thư mục và đọc được. Truyền path tương đối hoặc path không đáp ứng yêu cầu sẽ gây `IllegalArgumentException`; truyền `null` gây `NullPointerException`. Tránh xây dựng đường dẫn phục vụ tệp bằng cách nối chuỗi URI chưa kiểm soát: hãy dùng handler có sẵn, đồng thời chỉ định đúng thư mục được phép công khai.

### `HttpHandler` là điểm mở rộng

`HttpHandler` là functional interface có phương thức `handle(HttpExchange)`. Trong một server, context `/health` có thể dùng một handler tĩnh, trong khi context `/` dùng file handler.

Quy tắc chọn context của `HttpServer` là **tiền tố path khớp dài nhất**, so khớp phân biệt chữ hoa/chữ thường. Vì thế, một request đến `/health` được định tuyến vào context `/health` thay vì `/`; nhưng path `/healthcheck` cũng bắt đầu bằng `/health`, nên nếu cần so khớp chính xác, handler phải tự kiểm tra URI path.

Java 18 cũng cung cấp `HttpHandlers.of(status, headers, body)` để tạo phản hồi tĩnh và `HttpHandlers.handleOrElse(predicate, first, fallback)` để chọn handler theo điều kiện. Các API này có thể phối hợp với `createFileHandler` mà không cần thay đổi chính file handler.

## 4. Thành phần thứ ba: `Filter` tạo bằng `createOutputFilter`

Chữ ký công khai:

```java
static Filter createOutputFilter(
    OutputStream out,
    SimpleFileServer.OutputLevel outputLevel
)
```

Factory trả về **filter hậu xử lý** ghi thông tin về các `HttpExchange` đã được xử lý, sử dụng **UTF-8** để ghi vào `out`. Filter chỉ hoạt động khi được gắn vào một `HttpContext` qua `context.getFilters().add(filter)` (hoặc truyền khi tạo server/context bằng API hỗ trợ filter).

Các mức log thuộc enum `SimpleFileServer.OutputLevel`:

| Giá trị | Khi truyền vào `createFileServer` | Khi truyền vào `createOutputFilter` |
| --- | --- | --- |
| `NONE` | Server không tạo log tự động. | **Không hợp lệ:** ném `IllegalArgumentException`. Nếu không muốn log, đừng gắn filter. |
| `INFO` | Ghi thông tin cơ bản về trao đổi HTTP ra `System.out`. | Ghi thông tin trao đổi HTTP ra `OutputStream` chỉ định. |
| `VERBOSE` | Ghi log chi tiết hơn ra `System.out`. | Ghi log chi tiết hơn, có thể bao gồm header và đường dẫn tài nguyên tuyệt đối. |

Khác biệt cần nhớ: `createFileServer(..., OutputLevel.INFO)` **đã tích hợp cơ chế log**; khi bạn tự tạo `HttpServer` và dùng `createFileHandler`, hãy gắn `createOutputFilter` nếu cần log. Gắn thêm logging filter trùng chức năng vào server đã có log có thể làm thông tin bị ghi lặp.

`Filter` là API rộng hơn việc ghi log. Những factory được hỗ trợ trên JDK hiện đại gồm:

- `Filter.beforeHandler(description, operation)`: chạy một thao tác **trước** các filter tiếp theo hoặc handler; ví dụ thêm response header.
- `Filter.afterHandler(description, operation)`: chạy thao tác **sau** khi handler hoặc chuỗi kế tiếp hoàn tất; phù hợp quan sát status, không nên gửi response mới ở thời điểm này.
- `Filter.adaptRequest(description, operator)`: điều chỉnh góc nhìn `Request` trước khi xử lý tiếp, chẳng hạn bổ sung request header cho chuỗi handler phía sau.

Filter gắn theo **context**, không mặc nhiên áp dụng cho mọi route của cùng server. Thứ tự trong danh sách filter ảnh hưởng đến thứ tự thực thi: những thao tác `beforeHandler` chạy theo thứ tự được gắn khi chuỗi đi vào; những thao tác `afterHandler` chạy theo chiều ngược lại khi chuỗi quay về.

## 5. Ví dụ 2: ghép đủ `HttpServer`, `HttpHandler` và `Filter`

Ví dụ sau tạo server bằng `HttpServer.create`, gắn file handler vào `/`, thêm một response header trước khi phục vụ tệp, gắn logging filter sau khi phục vụ, và tạo endpoint `/health`. Không chạy ví dụ này đồng thời với `QuickFileServer` nếu cả hai dùng cổng `8000`.

Lưu dưới tên `ComposedFileServer.java`:

```java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpHandlers;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class ComposedFileServer {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("public").toAbsolutePath().normalize();
        if (!Files.isDirectory(root) || !Files.isReadable(root)) {
            throw new IllegalArgumentException("Thư mục public chưa sẵn sàng: " + root);
        }

        InetSocketAddress address =
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 8000);
        HttpServer server = HttpServer.create(address, 0);

        // HttpHandler: chịu trách nhiệm đọc và phục vụ tệp.
        HttpHandler fileHandler = SimpleFileServer.createFileHandler(root);
        HttpContext fileContext = server.createContext("/", fileHandler);

        // Filter trước handler: áp dụng header cho response phục vụ tệp.
        fileContext.getFilters().add(
                Filter.beforeHandler("Add nosniff header",
                        exchange -> exchange.getResponseHeaders()
                                .set("X-Content-Type-Options", "nosniff")));

        // Filter sau handler: ghi log exchange ra stdout.
        fileContext.getFilters().add(
                SimpleFileServer.createOutputFilter(System.out, OutputLevel.INFO));

        // Một context riêng: handler trả phản hồi tĩnh cho health check.
        HttpHandler healthHandler = HttpHandlers.handleOrElse(
                request -> request.getRequestMethod().equals("GET"),
                HttpHandlers.of(200,
                        Headers.of("Content-Type", "text/plain; charset=utf-8"),
                        "OK"),
                HttpHandlers.of(405, Headers.of("Allow", "GET"), ""));
        server.createContext("/health", healthHandler);

        server.start();
        System.out.println("Server đang chạy tại http://localhost:8000/");
    }
}
```

Chạy bằng JDK 18 trở lên:

```bash
javac ComposedFileServer.java
java ComposedFileServer
```

Thử các yêu cầu sau trong terminal khác:

```bash
curl -i http://localhost:8000/hello.txt
curl -I http://localhost:8000/hello.txt
curl -i -X POST http://localhost:8000/hello.txt
curl -i http://localhost:8000/health
curl -i -X POST http://localhost:8000/health
```

| Request | Context được chọn | Kết quả cần quan sát |
| --- | --- | --- |
| `GET /hello.txt` | `/` | Nhận nội dung tệp, `X-Content-Type-Options: nosniff`, có log ở stdout. |
| `HEAD /hello.txt` | `/` | Có header phản hồi, không có body. |
| `POST /hello.txt` | `/` | File handler trả `405`; logging filter của context `/` ghi trao đổi. |
| `GET /health` | `/health` | Trả `200` và `OK`, không đi qua hai filter của `/`. |
| `POST /health` | `/health` | Trả `405` với `Allow: GET`; vẫn không đi qua các filter của `/`. |

Ở đây, `server.createContext("/health", healthHandler)` tạo context riêng. `/health` khớp cụ thể hơn `/`; danh sách filter của `fileContext` không áp dụng lên context `/health`. Đó là lý do vì sao log filter chỉ ghi những request được xử lý bởi file handler, không ghi toàn bộ traffic của server.

**Lưu ý về đường dẫn:** vì `/health` là một *tiền tố*, request đến `/healthcheck` cũng có thể được định tuyến vào context `/health`. Ví dụ ưu tiên minh họa cách ghép thành phần; hệ thống cần route chính xác phải kiểm tra `exchange.getRequestURI().getPath()` trong handler.

## 6. Phân tích một lượt request

Với `GET /hello.txt` trong `ComposedFileServer`:

1. `HttpServer` nhận request đến cổng `8000` và chọn context `/`.
2. `Filter.beforeHandler` đặt `X-Content-Type-Options: nosniff` trong response header, **trước khi header được gửi**.
3. Logging filter chuyển tiếp request đến `fileHandler`.
4. `fileHandler` lấy nội dung `public/hello.txt`, gửi HTTP status, header và body.
5. Khi handler trả về, logging filter ghi thông tin exchange ra `System.out`.
6. Client nhận phản hồi; vòng đời server tiếp tục cho những request khác.

Trong ví dụ này, filter ghi log là một **post-processing filter**. Nó không tạo response và không thay thế `HttpHandler`. Nếu tự triển khai một `Filter` bằng `doFilter(exchange, chain)`, ứng dụng phải gọi `chain.doFilter(exchange)` để chuyển tiếp. Nếu cố ý dừng chuỗi và không gọi tiếp, chính filter phải gửi một phản hồi hợp lệ cho client.

Một phân biệt thực tế:

- **Lỗi trong handler** có thể khiến response không được gửi đầy đủ; không nên phụ thuộc vào logging filter để tự xử lý mọi ngoại lệ.
- **Header response** nên đặt trước khi handler gửi status/header. `Filter.afterHandler` dùng tốt cho quan sát, nhưng thường đã quá muộn để sửa phản hồi.
- **Log có dữ liệu nhạy cảm:** mức `VERBOSE` có thể ghi headers và đường dẫn tuyệt đối. Chỉ bật khi phục vụ dữ liệu thử nghiệm và kiểm soát nơi lưu log.

## 7. Lựa chọn factory theo yêu cầu thực tế

| Nhu cầu | Chọn API | Lý do |
| --- | --- | --- |
| Phục vụ nhanh một thư mục tệp trong máy phát triển | `createFileServer(addr, root, INFO)` | Nhận ngay server đã cấu hình context `/` và logging. |
| Đã có server với các route riêng và muốn thêm phục vụ tệp | `createFileHandler(root)` | Có thể gắn handler vào một `HttpContext` trên server hiện có. |
| Muốn log request của một route nhất định | `createOutputFilter(out, INFO)` | Chỉ cần gắn filter vào context tương ứng. |
| Không cần log | `createFileServer(..., NONE)` hoặc không gắn output filter | `createOutputFilter(..., NONE)` không hợp lệ. |
| Muốn thêm header, đo phản hồi hoặc điều chỉnh request | `Filter.beforeHandler`, `afterHandler`, `adaptRequest` | Có thể dùng filter tùy biến bên cạnh file handler hoặc handler khác. |
| Muốn xử lý `POST`/`PUT` hợp lệ | Viết `HttpHandler` riêng hoặc ghép qua `HttpHandlers.handleOrElse` | File handler có sẵn chỉ phục vụ `GET` và `HEAD`. |

Khi dùng **named module**, ứng dụng khai báo:

```java
module example.files {
    requires jdk.httpserver;
}
```

Hai package `com.sun.net.httpserver` và `com.sun.net.httpserver.spi` được `jdk.httpserver` export công khai. Chúng là API đặc thù của JDK, không phải API HTTP của Java SE độc lập với mọi bản triển khai JDK. Trong ứng dụng Java thông thường dùng classpath, có thể biên dịch và sử dụng trực tiếp khi runtime có module `jdk.httpserver`.

## 8. Những sai lầm phổ biến

1. **Quên `server.start()`:** factory chỉ tạo và cấu hình server, chưa bắt đầu phục vụ request.
2. **Truyền `Path.of("public")` trực tiếp:** đây thường là path tương đối; cần `toAbsolutePath()` và bảo đảm thư mục tồn tại, đọc được.
3. **Tưởng `HttpHandler` tự lắng nghe cổng:** handler chỉ thực thi khi được gắn vào context của server đang chạy.
4. **Tưởng filter áp dụng cho toàn bộ server:** filter được gắn vào danh sách của một context cụ thể.
5. **Dùng `OutputLevel.NONE` để tạo output filter:** factory filter ném `IllegalArgumentException`; hãy bỏ filter.
6. **Tưởng file handler nhận mọi HTTP method:** chỉ có `GET` và `HEAD`; các phương thức khác trả `405`.
7. **Cố ghi response mới trong post-processing filter:** tại thời điểm đó response đã có thể được gửi; chỉ nên quan sát.
8. **Đưa file server vào production như web server hoàn chỉnh:** `SimpleFileServer` được thiết kế cho test, development và debug, không cung cấp sẵn bộ tính năng bảo vệ, xác thực, giám sát và vận hành của hệ thống production.

Đặc biệt, không trỏ `rootDirectory` tới thư mục chứa source code nội bộ, khóa riêng, token hoặc tệp nhạy cảm. Handler có thể trả danh sách thư mục dạng HTML, vì vậy chỉ chia sẻ đúng thư mục dành cho nội dung thử nghiệm. Để thử nội bộ, ưu tiên bind vào địa chỉ loopback.

## 9. Bài tập tự kiểm tra

1. Mô tả chính xác nhiệm vụ của `HttpServer`, `HttpHandler`, `Filter` và vai trò trung gian của `HttpContext`.
2. `createFileServer(..., OutputLevel.INFO)` trả về kiểu gì? Nó có tự khởi động không? Context mặc định là path nào?
3. Vì sao dùng `createFileHandler(root)` tiện hơn `createFileServer(...)` khi cần thêm endpoint `/health`?
4. `OutputLevel.NONE` có ý nghĩa gì ở mỗi factory? Vì sao có thể dùng ở một factory nhưng không thể dùng ở factory kia?
5. Khi `GET /hello.txt` được xử lý trong ví dụ, filter thêm header chạy trước hay sau file handler? Logging filter ghi log khi nào?
6. Vì sao `GET /health` không đi qua filter gắn ở context `/`? Nếu muốn log cả hai context, cần làm gì?
7. Nếu `POST /hello.txt` trả `405`, thành phần nào quyết định status này?
8. Vì sao không nên bật `VERBOSE` hoặc bind mọi giao diện mạng trên thư mục có dữ liệu nhạy cảm?

**Thực hành mở rộng:** thay `OutputLevel.INFO` trong `ComposedFileServer` thành `VERBOSE`, quan sát khác biệt log của `GET` và `HEAD`. Tiếp đó thêm một `Filter.beforeHandler` vào context `/health` để thấy rõ tính độc lập của chuỗi filter mỗi context. Chỉ dùng dữ liệu giả lập khi thử logging chi tiết.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): ba thành phần, factory method, hợp đồng file handler và log filter.
- [Oracle JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): vòng đời server, `HttpContext` và quy tắc chọn context.
- [Oracle JDK 27 — `HttpContext`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): quan hệ context-handler-filter, danh sách filter.
- [Oracle JDK 27 — `Filter`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html): `doFilter`, `beforeHandler`, `afterHandler`, `adaptRequest`.
- [Oracle JDK 27 — `HttpHandlers`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandlers.html): phản hồi tĩnh và handler có điều kiện.
- [Oracle JDK 27 — module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): phạm vi module và các package được export.
