# Tạo server, bind địa chỉ và đăng ký HttpContext

## 1. Mục tiêu bài học

Khi viết một HTTP endpoint nhỏ bằng Java, bạn không nhất thiết phải cài framework web. JDK cung cấp module `jdk.httpserver` với `com.sun.net.httpserver.HttpServer`, `HttpContext`, `HttpHandler` và `HttpExchange`. Chúng đủ để xây dựng một HTTP server đơn giản phục vụ bài thực hành, health check nội bộ, endpoint thử nghiệm hoặc công cụ phát triển.

Sau bài này bạn sẽ thực hiện được ba việc trọng tâm:

1. **Tạo HTTP server** bằng `HttpServer.create()` hoặc `HttpServer.create(InetSocketAddress, backlog)`, biết khác nhau giữa server **chưa bind** và server **đã bind**.
2. **Bind vào IP/port và bắt đầu lắng nghe** với `bind(...)` rồi `start()`; hiểu địa chỉ loopback, cổng `0`, socket backlog và thứ tự cấu hình executor.
3. **Đăng ký URL path bằng `HttpContext`**, liên kết nó với `HttpHandler`, hiểu **longest literal prefix matching** (tiền tố dài nhất, phân biệt hoa/thường) và cách gỡ context.

Hai chương trình Java 17+ ở phần 9 và 11 chạy trực tiếp qua `javac`/`java`, tự mở server tại `127.0.0.1` và dùng HTTP client của JDK để kiểm tra response. Bạn không phải cài Spring, Servlet container, framework bên thứ ba hay kết nối Internet.

**Giới hạn:** `com.sun.net.httpserver.HttpServer` là HTTP server gọn nhẹ của JDK. Nó **không đồng nghĩa** một web application server đầy đủ, không tự cung cấp routing theo annotation, validation, bảo mật nghiệp vụ, reverse proxy hoặc các khả năng triển khai chuyên dụng. Bài tập trung vào **vòng đời server và cơ chế context routing**, không biến nó thành hướng dẫn framework.

## 2. Các đối tượng và mối quan hệ

| API | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `HttpServer` | Quản lý socket lắng nghe, contexts, executor, lifecycle | Server có thể được tạo chưa bind hoặc bind ngay |
| `InetSocketAddress` | Địa chỉ IP/tên host và port để lắng nghe | Cổng `0` yêu cầu OS cấp port trống |
| `HttpContext` | Ánh xạ một **path prefix** đến `HttpHandler` | Phân giải theo tiền tố khớp dài nhất |
| `HttpHandler` | Hàm xử lý request được định tuyến đến context | Phương thức `handle(HttpExchange)` |
| `HttpExchange` | Một request và response tương ứng | Chứa method, URI, headers, body streams |
| `Headers` | Header request/response | Dùng `getResponseHeaders()` để thiết lập trước khi gửi |
| `Executor` | Điều phối nơi chạy các handler | Cấu hình bằng `setExecutor` trước `start` |
| `HttpClient` | Client của JDK để thử server | Thuộc module `java.net.http`, tách biệt với `HttpServer` |
| `HttpsServer` | Biến thể server hỗ trợ HTTPS | Cần `HttpsConfigurator` và cấu hình TLS hợp lệ |

Dòng chảy điển hình:

~~~text
             Java application
                    |
     HttpServer.create() hoặc create(addr, backlog)
                    |
              bind nếu cần
                    |
  createContext("/hello", HttpHandler)
  createContext("/api/", HttpHandler)
                    |
            setExecutor(...)
                    |
                 start()
                    |
 TCP accept -> HTTP parse -> chọn HttpContext -> HttpHandler.handle(exchange)
                                               |
                                đọc method/URI/headers/body
                                               |
                             set response headers + sendResponseHeaders
                                               |
                               ghi/đóng response body + exchange
                    |
               stop(delay)
~~~

`HttpContext` không phải socket listener độc lập. **Một `HttpServer` có thể có nhiều `HttpContext` nhưng tất cả dùng chung socket đã bind của server đó**. Đường dẫn `/hello` hay `/api/` không thay thế IP/port: chúng chỉ xác định handler được chọn **sau khi kết nối TCP và request HTTP tới server**.

## 3. Vòng đời chính xác: create → bind → contexts → executor → start → stop

Có **hai cách tạo phổ biến**:

**Cách A — tạo chưa bind, bind sau:**

~~~java
HttpServer server = HttpServer.create();
server.bind(new InetSocketAddress("127.0.0.1", 8080), 32);
server.createContext("/hello", exchange -> {
    // Xử lý một HTTP request.
});
server.start();
~~~

*Đoạn minh họa, handler đang để trống phần nội dung response; dùng chương trình đầy đủ ở phần 9 để chạy.*

`HttpServer.create()` trả server **chưa gắn vào IP/port nào**. Phải gọi `server.bind(InetSocketAddress,int)` trước khi sử dụng socket lắng nghe. Không gọi `bind` hai lần trên cùng server đã bind.

**Cách B — tạo và bind trong một lệnh:**

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 32);
server.createContext("/hello", handler);
server.start();
~~~

*Đoạn minh họa với `handler` cần được khai báo riêng.*

`HttpServer.create(addr,backlog)` bind vào `addr` ngay khi tạo, nhưng **chưa bắt đầu phục vụ request** cho đến khi gọi `start()`. Trong overload này, truyền `addr == null` tạo server chưa bind và bạn phải `bind(...)` sau; để rõ ý thường dùng `create()` khi thật sự muốn tách bước.

**Bảng trạng thái:**

| Thời điểm | Có địa chỉ bind chưa? | Đã xử lý request chưa? | Việc hợp lệ |
| --- | --- | --- | --- |
| Sau `create()` | Chưa | Chưa | `bind`, cấu hình contexts/executor |
| Sau `create(addr,backlog)` | Rồi | Chưa | Đăng ký contexts, `setExecutor`, `start` |
| Sau `bind(addr,backlog)` | Rồi | Chưa | Lấy `getAddress`, đăng ký contexts, `start` |
| Sau `start()` | Rồi | Có | Nhận/gửi các `HttpExchange`, quản lý contexts |
| Sau `stop(delay)` | Không còn phục vụ | Không | Giải phóng tài nguyên; **không restart server cũ** |

Thông thường hãy **đăng ký handler, cấu hình filter/authenticator và executor trước khi `start()`**, để không xuất hiện cửa sổ thời gian request vào một context chưa sẵn sàng. `setExecutor(...)` phải gọi **trước** `start()`; gọi sau khi server đã start có thể ném `IllegalStateException`.

`stop(int delay)` dừng lắng nghe, không chấp nhận exchange mới và đợi các exchange hiện có hoàn thành **tối đa khoảng `delay` giây**, sau đó đóng các kết nối. Không thể `start()` lại server đã stop; hãy tạo server mới nếu cần bật lại.

## 4. Bind địa chỉ: loopback, port, backlog

Câu lệnh:

~~~java
server.bind(new InetSocketAddress("127.0.0.1", 0), 16);
int actualPort = server.getAddress().getPort();
~~~

Có ba thành phần ý nghĩa:

- **IP/hostname**: `127.0.0.1` là **IPv4 loopback**, chỉ phục vụ kết nối cùng máy (trong cấu hình mạng thông thường); phù hợp test hoặc dịch vụ chỉ dành cho local. `0.0.0.0` biểu diễn **mọi IPv4 interface**, có thể cho máy khác truy cập tùy firewall/network — không dùng vô ý.
- **Port**: `8080` là port cố định, người gọi cần biết đúng số này. `0` là **port tạm do hệ điều hành chọn** cho lần bind đó; gọi `getAddress().getPort()` **sau bind** để lấy port thực.
- **Backlog**: `16` là gợi ý **số kết nối TCP đang chờ được accept**, không phải số HTTP request được xử lý đồng thời, không phải giới hạn body size và không phải kích thước thread pool. Giá trị `<= 0` khiến implementation dùng mặc định của hệ thống.

Ví dụ chọn IP qua đối tượng:

~~~java
InetSocketAddress local =
        new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0);
HttpServer server = HttpServer.create(local, 0);
System.out.println(server.getAddress().getPort() > 0);
~~~

*Đoạn minh họa có imports và cần cleanup server; chương trình đầy đủ quản lý lifecycle ở phần 9–11.*

**Hai loại lỗi bind phổ biến:** port đang được tiến trình khác sử dụng, hoặc IP chỉ định không hiện diện/không thể bind trên host. JDK có thể ném `BindException` (kế thừa `IOException`). Với dịch vụ cố định, hãy cấu hình port và báo lỗi rõ ràng; không tự chọn port khác nếu client/reverse proxy vẫn trỏ về port cũ. Với test, port `0` giảm xung đột cổng.

Đối với IPv6, địa chỉ và cú pháp URL cần phù hợp, ví dụ `[::1]`; không mặc định tên `localhost` luôn trỏ tới cùng một họ IP. Demo sử dụng rõ `127.0.0.1` ở **cả server và client** để tránh sai khác IPv4/IPv6.

## 5. Đăng ký HttpContext: path prefix dẫn đến HttpHandler

Cách ngắn nhất:

~~~java
HttpContext context = server.createContext(
        "/hello", exchange -> {
            // Xử lý request cho path được chọn.
        });
~~~

`createContext(String path, HttpHandler handler)` tạo context và gắn handler trong một lần. `path` **phải bắt đầu bằng dấu `/`**. `handler` không được `null`, và tạo trùng một context path trên cùng server có thể ném `IllegalArgumentException`.

Một cách khác dùng khi cần khai báo context trước rồi gắn handler:

~~~java
HttpContext context = server.createContext("/api/");
context.setHandler(exchange -> {
    // Thiết lập handler lần đầu.
});
~~~

*Hai đoạn này là minh họa; chương trình runnable ở phần 9 dùng cả overload thường và lưu `HttpContext` để gỡ sau.*

`HttpContext.setHandler(...)` dùng để **thiết lập handler khi context chưa có handler**; không phải chức năng hot-swap handler tùy ý. Nếu handler đã gắn, gọi `setHandler` lại có thể ném `IllegalArgumentException`. Để thay đổi routing ở mức context, cần quản lý đăng ký/gỡ context có kiểm soát, hoặc để handler dùng cấu hình thread-safe nội bộ.

Một context có thể được cấu hình thêm:

- `context.getFilters()`: danh sách `Filter` để đặt xử lý trước/sau handler, ví dụ log, kiểm soát request, kiểm tra thông tin đầu vào.
- `context.setAuthenticator(...)`: gắn `Authenticator` khi có nhu cầu xác thực.
- `context.getPath()`: path prefix khi đăng ký.
- `context.getHandler()` và `context.getServer()`: truy cập handler/server liên quan.
- `context.getAttributes()`: map thuộc context để chia sẻ cấu hình với filter/handler, cần thiết kế đồng bộ hóa nếu nhiều thread cùng cập nhật.

Đừng để context không có handler sẵn sàng phục vụ request. Chuẩn bị handler và filters **trước `start()`** sẽ dễ kiểm soát hơn. Không nên lấy context path như một cơ chế **phân quyền**: request vẫn phải được xác thực và kiểm tra authorization bởi handler/filter tương ứng.

## 6. Quy tắc định tuyến: tiền tố dài nhất, so khớp literal và case-sensitive

`HttpServer` chọn `HttpContext` dựa trên **longest matching literal prefix** của đường dẫn URI request. Không có regex, không có `@GetMapping`, không có wildcard như `/users/{id}` và **không tự phân đoạn path như một REST router**.

Ví dụ đăng ký:

~~~text
/
 /app/
 /app/admin/
 /legacy
~~~

*Dòng có khoảng trắng chỉ để dễ quan sát phân cấp; chuỗi context thực tế không có khoảng trắng đầu dòng.*

Các request sẽ được chọn như sau:

| URI path nhận được | Context được chọn | Vì sao |
| --- | --- | --- |
| `/app/report` | `/app/` | Prefix `/app/` dài hơn `/` |
| `/app/admin/users` | `/app/admin/` | Đây là tiền tố khớp dài nhất |
| `/app/ADMIN/users` | `/app/` | `admin` khác `ADMIN`; phân biệt hoa/thường |
| `/application` | `/` | Không bắt đầu bằng `/app/` |
| `/legacyExtra` | `/legacy` | `/legacy` là **tiền tố ký tự**, không tự kiểm tra ranh giới segment |
| `/foo` | `/` | Context `/` bắt mọi path còn lại |
| `/app/admin/users` sau khi gỡ `/app/admin/` | `/app/` | Context dài nhất còn lại thắng |

**Bẫy đáng nhớ:** context `/api` **có thể bắt cả `/apiculture`**, vì chỉ kiểm tra ký tự tiền tố; context `/api/` tránh va chạm này nhưng **không bắt path chính xác `/api`**. Nếu muốn xử lý cả hai, hãy đăng ký rõ cả `/api` và `/api/` hoặc kiểm tra path chính xác trong handler phù hợp.

**Một dấu `/` cuối có ý nghĩa.** `/admin/` thường là lựa chọn an toàn hơn `/admin` nếu bạn muốn giữ ranh giới nhánh con. Dù vậy handler **vẫn phải kiểm tra method, cấu trúc đường dẫn, tham số và quyền**. Chọn context thành công không tự bảo đảm request được phép.

**Không khớp context:** nếu không có `/` root và không có context nào khớp, JDK `HttpServer` gửi **404** tự động. Nếu bạn có root context `/`, gần như mọi URI path sẽ khớp root; lúc đó bạn phải chủ động trả 404 từ handler khi path không được hỗ trợ.

## 7. Percent-encoding, method và query không thay thế routing

API path matching của JDK so khớp **literal, phân biệt chữ hoa/thường, không tự chuyển đổi encoding** trong bước chọn context. Đừng lẫn:

- `exchange.getRequestURI().getRawPath()`: chuỗi raw path, còn các ký tự percent-encoded.
- `exchange.getRequestURI().getPath()`: path được URI decode theo quy tắc của `java.net.URI`.
- `exchange.getRequestURI().getRawQuery()`: query nguyên dạng; **query không phải context path prefix**.
- `exchange.getRequestMethod()`: HTTP method, **không tự được phân biệt khi chọn context**.

Ví dụ `/users?id=42` và `/users?id=99` có cùng path để chọn context `/users`. Handler cần tự đọc query và xác thực giá trị. Thực hiện path normalization/decoding có kiểm soát ở tầng ứng dụng, đặc biệt trước khi chuyển path thành tên file hoặc quyền truy cập; không dựa vào context matching để chống path traversal.

Đối với REST API, nếu chỉ muốn GET đúng `/hello`, code handler cần kiểm tra:

~~~java
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    respond(exchange, 405, "method not allowed");
} else if (!"/hello".equals(exchange.getRequestURI().getPath())) {
    respond(exchange, 404, "not found");
} else {
    respond(exchange, 200, "hello from JDK");
}
~~~

*Đây là đoạn trích **từ chương trình đầy đủ** ở phần 9; yêu cầu có `respond` và biến `exchange` đã khai báo.*

Lý do cần kiểm tra thêm `"/hello".equals(...)`: context `/hello` có thể khớp cả `/helloExtra`. `HttpServer` chỉ chọn handler; **handler mới biết endpoint cụ thể yêu cầu gì**.

## 8. HttpExchange: vòng đời request và response

`HttpHandler.handle(HttpExchange exchange)` được gọi khi một request khớp context. Trong handler, quy trình chuẩn gồm:

1. Đọc `exchange.getRequestMethod()`, `getRequestURI()` và `getRequestHeaders()`; xác thực/giới hạn đầu vào.
2. Nếu request có body, tiêu thụ đúng và **đóng `exchange.getRequestBody()`**. Tránh `readAllBytes()` vô điều kiện cho body không giới hạn.
3. Thiết lập `exchange.getResponseHeaders()`, như `Content-Type` và `Allow`.
4. Gọi **`exchange.sendResponseHeaders(statusCode, responseLength)` trước khi lấy response body output**.
5. Ghi đúng số byte theo responseLength, đóng output stream; **đảm bảo `exchange.close()`** trong `finally`/try-with-resources để giải phóng exchange.

**`responseLength` dễ sai nhất:**

| Giá trị truyền cho `sendResponseHeaders` | Nghĩa của JDK HTTP server |
| --- | --- |
| **`> 0`** | Body có **độ dài byte cố định**; phải viết **chính xác** số byte ấy |
| **`== 0`** | Dùng chunked transfer encoding để gửi body không biết sẵn độ dài (HTTP/1.1) |
| **`-1`** | **Không gửi response body**; phù hợp trường hợp cần response rỗng |
 
Vì vậy, khi gửi văn bản, **không dùng `String.length()` làm Content-Length**. Với UTF-8, chuỗi tiếng Việt có thể chiếm nhiều byte hơn số ký tự Java. Làm đúng:

~~~java
byte[] body = "Xin chào".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, body.length);
try (OutputStream output = exchange.getResponseBody()) {
    output.write(body);
}
exchange.close();
~~~

*Đoạn minh họa; production nên đặt `close()` trong `finally`. Nếu body rỗng và muốn không gửi body, dùng `-1` thay vì nhầm `0` là zero-length fixed body.*

Với `204 No Content` hoặc `HEAD`, phải chú ý **không gửi body không được phép** theo semantics HTTP; dùng response length/handler phù hợp và đóng stream đúng cách. Khi `getResponseBody()` được mở, cần đóng để hoàn tất exchange. Đọc/gửi thiếu hoặc dư số byte đã khai báo có thể ném `IOException` và làm connection bị đóng.

## 9. Ví dụ Java 17+ hoàn chỉnh: create(), bind(), đăng ký context và trả HTTP

Ví dụ đầu kiểm chứng **từ server chưa bind** đến server phục vụ HTTP, thêm ba context, dùng executor riêng và gỡ context đang chạy. Client trong cùng JVM gửi request thật qua TCP loopback.

Tạo file `HttpServerBindDemo.java` đúng toàn bộ nội dung:

~~~java
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HttpServerBindDemo {
    static void respond(HttpExchange exchange, int status, String body)
            throws IOException {
        try {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    static HttpResponse<String> get(HttpClient client, String base, String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(base + path)).GET().build();
        return client.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(); // Not bound yet.
        ExecutorService workers = Executors.newFixedThreadPool(2);
        try {
            server.bind(new InetSocketAddress("127.0.0.1", 0), 16);
            server.createContext("/hello", exchange -> {
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set("Allow", "GET");
                    respond(exchange, 405, "method not allowed");
                } else if (!"/hello".equals(exchange.getRequestURI().getPath())) {
                    respond(exchange, 404, "not found");
                } else {
                    respond(exchange, 200, "hello from JDK");
                }
            });
            server.createContext("/api/", exchange -> respond(exchange, 200,
                    "api path=" + exchange.getRequestURI().getPath()));
            HttpContext items = server.createContext("/api/items/",
                    exchange -> respond(exchange, 200,
                            "items path=" + exchange.getRequestURI().getPath()));
            server.setExecutor(workers); // Must happen before start().
            server.start();

            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();
            for (String path : new String[]{
                    "/hello", "/api/users", "/api/items/7", "/missing"}) {
                HttpResponse<String> response = get(client, base, path);
                System.out.println("GET " + path + ": " + response.statusCode()
                        + (response.statusCode() == 200
                        ? " " + response.body() : ""));
            }

            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(base + "/hello"))
                    .POST(HttpRequest.BodyPublishers.noBody()).build();
            HttpResponse<String> rejected = client.send(
                    post, HttpResponse.BodyHandlers.ofString());
            System.out.println("POST /hello: " + rejected.statusCode()
                    + " Allow=" + rejected.headers().firstValue("Allow")
                    .orElse("(missing)"));

            server.removeContext(items);
            HttpResponse<String> fallback = get(client, base, "/api/items/7");
            System.out.println("GET /api/items/7 after remove: "
                    + fallback.statusCode() + " " + fallback.body());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac HttpServerBindDemo.java
java HttpServerBindDemo
~~~

Kết quả chuẩn của chương trình khi loopback hoạt động:

~~~text
GET /hello: 200 hello from JDK
GET /api/users: 200 api path=/api/users
GET /api/items/7: 200 items path=/api/items/7
GET /missing: 404
POST /hello: 405 Allow=GET
GET /api/items/7 after remove: 200 api path=/api/items/7
~~~

### Vì sao chương trình có đúng các dòng này?

- `HttpServer.create()` ban đầu **chưa bind**. `server.bind(new InetSocketAddress("127.0.0.1",0),16)` mới gắn socket vào IPv4 loopback và cổng do hệ điều hành chọn. `server.getAddress().getPort()` được đọc **sau bind/start** để client biết địa chỉ thực.
- `createContext("/hello", handler)` gắn một handler cho prefix `/hello`. Bên trong handler **chủ động** so method GET và path chính xác; do đó POST bị từ chối với status **405** và header `Allow: GET`.
- `createContext("/api/", handler)` nhận `/api/users`. `createContext("/api/items/", handler)` dài hơn nên nhận `/api/items/7`.
- Không có context `/`, nên `/missing` **không khớp handler nào** và JDK server trả **404**. Client chỉ in status cho trường hợp này, không dựa vào nội dung body 404 do implementation tạo.
- `setExecutor(workers)` được gọi **trước `start()`**. Server dùng một executor có giới hạn hai worker threads cho demo; việc quản thread không lẫn với số backlog 16.
- `server.removeContext(items)` gỡ context cụ thể `/api/items/`. GET `/api/items/7` sau đó **khớp `/api/`** và trả body có tiền tố `api path=`. Đây là **fallback của thuật toán longest matching prefix**, không phải response được cache.
- `server.stop(0)` đóng server và `workers.shutdownNow()` xử lý executor trong `finally`, tránh process thử nghiệm còn chạy vì thread pool.

**Không suy luận từ output rằng mọi request đã được xử lý tuần tự.** Client trong demo gửi từng request để output ổn định; server có thể xử lý nhiều kết nối đồng thời nhờ executor. Nếu muốn đo concurrency, cần test nhiều client concurrent và có metric rõ.

## 10. Chọn giữa create(), create(addr,backlog) và bind()

| Tình huống | Cách dùng | Lý do |
| --- | --- | --- |
| Cấu hình server qua nhiều bước rồi mới biết địa chỉ | `HttpServer.create()` → `bind(...)` | Tách khởi tạo và bind |
| Địa chỉ đã xác định ngay | `HttpServer.create(address, backlog)` | Bind ngay, code gọn |
| Test tự động trên máy có nhiều test song song | `port = 0` và đọc `getAddress().getPort()` | Không chiếm cứng cổng |
| Dịch vụ nội bộ chỉ cho phép cùng máy | `127.0.0.1` | Giảm bề mặt mạng so với mọi interface |
| Dịch vụ cần nghe trên interface bên ngoài | Bind IP/interface được kiểm soát + firewall/auth | Không mặc định an toàn |
| Nhiều endpoint cùng port | Nhiều `createContext(...)` trên một `HttpServer` | Không cần mỗi path một socket |
| Cần TLS | `HttpsServer` + `HttpsConfigurator` | `HttpServer` thông thường không tự HTTPS |

**Không gọi `bind(...)` lần hai trên server đã bind.** Nếu bind thất bại, kiểm tra thông báo `BindException` và chính sách cấu hình. Không biến sự cố port bận thành chuyển sang cổng ngẫu nhiên trong production mà không cập nhật service discovery/proxy/client.

Một `HttpServer` đã `stop(...)` **không thể được khởi động lại**, dù executor còn sống. Tạo `HttpServer` mới cho vòng đời mới.

## 11. Ví dụ Java 17+ hoàn chỉnh: tiền tố dài nhất, phân biệt chữ hoa và gỡ context

Ví dụ thứ hai dùng **`HttpServer.create(address,backlog)` để bind ngay**, đăng ký bốn context `/`, `/app/`, `/app/admin/` và `/legacy`, rồi in tên **context thực sự được chọn** với `exchange.getHttpContext().getPath()`.

Tạo file `HttpContextRoutingDemo.java`:

~~~java
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class HttpContextRoutingDemo {
    static void route(HttpExchange exchange) throws IOException {
        try {
            String chosen = exchange.getHttpContext().getPath();
            String body = "context=" + chosen;
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    static void probe(HttpClient client, String base, String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create(base + path))
                .GET().build();
        HttpResponse<String> response = client.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        System.out.println(path + " -> " + response.body());
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        try {
            server.createContext("/", HttpContextRoutingDemo::route);
            server.createContext("/app/", HttpContextRoutingDemo::route);
            HttpContext admin = server.createContext(
                    "/app/admin/", HttpContextRoutingDemo::route);
            server.createContext("/legacy", HttpContextRoutingDemo::route);
            server.start();

            HttpClient client = HttpClient.newHttpClient();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            for (String path : new String[]{
                    "/app/report", "/app/admin/users",
                    "/app/ADMIN/users", "/application", "/legacyExtra"}) {
                probe(client, base, path);
            }

            server.removeContext(admin);
            probe(client, base, "/app/admin/users");
        } finally {
            server.stop(0);
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac HttpContextRoutingDemo.java
java HttpContextRoutingDemo
~~~

Stdout:

~~~text
/app/report -> context=/app/
/app/admin/users -> context=/app/admin/
/app/ADMIN/users -> context=/app/
/application -> context=/
/legacyExtra -> context=/legacy
/app/admin/users -> context=/app/
~~~

**Quan sát:**

- Request `/app/admin/users` ban đầu chọn context dài nhất `/app/admin/`.
- `/app/ADMIN/users` không khớp `/app/admin/` vì đường dẫn **case-sensitive**, nên fallback `/app/`.
- `/application` không có tiền tố `/app/` (vì khác sau `/app`), do đó được root `/` xử lý.
- `/legacyExtra` **vẫn khớp `/legacy`** do so tiền tố ký tự đơn thuần. Đây là lý do context đại diện một nhánh thường nên kết thúc bằng `/`, kết hợp kiểm tra path trong handler.
- Sau `server.removeContext(admin)`, request `/app/admin/users` không còn context chuyên biệt, vì vậy trở về `/app/`.

Trong ví dụ này vì có `createContext("/")` nên route không được đăng ký riêng **vẫn match root**. Không thể trông chờ automatic 404 khi đã đặt một catch-all root handler trả 200 cho mọi request.

## 12. HttpContext nào được chọn nếu có context chồng lấn?

Giả sử bạn thêm các context sau vào cùng một server:

~~~java
server.createContext("/", rootHandler);
server.createContext("/api/", apiHandler);
server.createContext("/api/orders/", ordersHandler);
~~~

*Đoạn minh họa, các biến `server` và handler phải tồn tại.*

Thuật toán:

1. HTTP server nhận request URI path.
2. So khớp **literal prefix** với các `HttpContext.getPath()` đã đăng ký.
3. Nếu có nhiều prefix, chọn **prefix dài nhất**.
4. Giao `HttpExchange` cho `HttpHandler` của context thắng cuộc.
5. Nếu không có prefix khớp, HTTP server trả 404. Nếu có root `/`, root sẽ match các path còn lại.

Đừng nhầm chuỗi path `"/api/orders/"` với template `"/api/orders/{id}"`. JDK không tự tách tham số `id`. Handler cần tự parse `getRequestURI()`, kiểm tra segment hợp lệ và authorization.

Thêm context trùng đường dẫn `"/api/"` lần thứ hai không tạo “override” tự nhiên; API có thể ném `IllegalArgumentException`. Nếu muốn thay handler, cần thiết kế lifecycle phù hợp, hoặc để một handler delegate theo trạng thái nội bộ đã được đồng bộ hóa.

Lưu ý path có percent encoding: raw path và decoded path của `URI` có thể khác nhau. Cơ chế context match không đảm nhiệm normalize hoặc decode cho chính sách bảo mật của ứng dụng. Khi đọc file từ URL path, tuyệt đối không nối trực tiếp path người dùng vào filesystem mà không normalize, kiểm tra đường dẫn nằm trong root được phép và bảo vệ quyền truy cập.

## 13. Executor, thread pool và backlog không phải một đại lượng

Ba thứ dễ bị trộn:

- **Socket backlog** là hàng đợi **TCP connections đang chờ accept** ở OS/server. Nó không trực tiếp đặt số request HTTP tối đa chạy cùng lúc.
- **`Executor`** cung cấp cách **chạy các exchange handlers**. `server.setExecutor(Executors.newFixedThreadPool(4))` cung cấp pool 4 threads, nhưng với tasks I/O bị chặn vẫn có khả năng nghẽn; pool này không tự bảo vệ mọi dạng quá tải.
- **Số request đồng thời** phụ thuộc clients, connection keep-alive, thời gian handler xử lý, executor và tài nguyên máy. Không suy ra số này chỉ từ backlog hoặc số context.

Ví dụ trước `start()`:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(4);
server.setExecutor(pool);
server.start();

// Trong shutdown của ứng dụng:
server.stop(5);
pool.shutdown();
~~~

*Đoạn minh họa, `server` đã bind và contexts đã được gắn; hệ thống thực cần xử lý deadline/forced shutdown của executor.*

Nếu không gọi `setExecutor`, HttpServer dùng executor mặc định do implementation cung cấp; `getExecutor()` có thể trả `null` khi bạn không tự đặt executor. Không nên giả định default phù hợp ứng dụng chịu tải cao.

**Quan trọng:** `stop(delay)` dừng server, nhưng nếu bạn cung cấp `ExecutorService` riêng, hãy **quản lý lifecycle của pool đó**. `stop` không tự biến một thread pool bên ngoài thành đã shutdown.

## 14. Bảo mật khi bind và mở endpoint

`HttpServer` rất thuận tiện cho demo, nhưng bind sai địa chỉ có thể mở dịch vụ ra mạng ngoài:

1. **Local test:** bind `127.0.0.1` và dùng client cùng máy. Không sử dụng `0.0.0.0` chỉ để “test cho chắc”.
2. **Dịch vụ cần truy cập từ xa:** chọn interface được phép, firewall/security group, HTTPS, authentication và authorization tương ứng.
3. **HTTP không tự mã hóa:** `HttpServer` với `http://` truyền payload plaintext trên mạng. `HttpsServer` yêu cầu cấu hình TLS thông qua `HttpsConfigurator` và certificate/trust phù hợp. Không tắt xác thực chỉ để kết nối được.
4. **Context path không phải cơ chế ACL:** `/admin/` không tự được bảo vệ vì tên path chứa chữ admin. Handler/filter phải xác thực quyền.
5. **Bảo vệ đầu vào:** method, query, headers, path, request body và content size đều có thể do client kiểm soát; phải giới hạn kích thước/thời gian, validate/normalize và không tin các trường này.
6. **Giới hạn thông tin lỗi:** không trả stack trace, secret, private file path hoặc dữ liệu nhạy cảm về server trong response 500.
7. **Không log token/credentials:** chỉ ghi requestId, route, method, status, latency và context có kiểm soát.
8. **Bảo vệ khỏi quá tải:** giới hạn worker pool, số request active, request body size, thời gian chờ và quota tại ứng dụng/proxy.

Khi triển khai trên container, `127.0.0.1` là loopback **bên trong network namespace của container**, không nhất thiết truy cập được từ host hoặc container khác. Ngược lại, bind mọi interface cùng port publishing có thể mở dịch vụ ngoài dự kiến. Luôn kiểm tra môi trường network thực tế.

## 15. Lỗi và ngoại lệ cần nhận biết

| Điều kiện | Dấu hiệu thường gặp | Cách xử lý |
| --- | --- | --- |
| Port đang được sử dụng | `BindException`/`IOException` tại `create(addr,...)` hoặc `bind` | Kiểm tra port và process, không tự overwrite |
| Bind vào IP không có trên máy | `BindException` hoặc I/O failure | Chọn đúng interface/IP |
| `bind(...)` trên server đã bind | `BindException` | Chỉ bind một lần |
| `start()` khi chưa bind | `IllegalStateException` | Bind trước rồi start |
| `setExecutor(...)` sau `start()` | `IllegalStateException` | Cấu hình trước start |
| `createContext("api", handler)` không có dấu `/` đầu | `IllegalArgumentException` | Dùng `"/api"` hoặc `"/api/"` |
| Tạo context trùng path | `IllegalArgumentException` | Đăng ký duy nhất, quản lifecycle |
| `createContext(path,null)` hoặc `setHandler(null)` | `NullPointerException` | Handler không được null |
| Gọi `setHandler` trên context đã có handler | `IllegalArgumentException` | Gắn handler một lần hoặc thiết kế delegate |
| URI path không khớp context nào | HTTP 404 | Đăng ký path phù hợp hoặc trả 404 theo route |
| Handler chỉ hỗ trợ GET nhưng nhận POST | Phải tự xử lý 405/Allow | Đừng cho rằng HttpServer tự phân loại method |
| Gọi `getResponseBody()` trước `sendResponseHeaders` | Vi phạm lifecycle, lỗi I/O | Gửi headers trước |
| Khai báo fixed length khác bytes thực gửi | `IOException`/đóng connection | Tính byte UTF-8 chính xác |
| Đọc body vô hạn | Hết RAM hoặc bị tấn công từ client | Áp limits và streaming |
| Quên đóng exchange/output | Tài nguyên bị giữ, HTTP client chờ | try/finally và đóng streams |
| `stop(...)` rồi `start()` lại | Server không được tái sử dụng | Tạo một HttpServer mới |

Trên ứng dụng production, không chỉ bắt mọi `IOException` rồi trả “200 OK”. Phân biệt lỗi **bind khi khởi động**, lỗi **network I/O trong handler** và **HTTP response do method/path không hợp lệ**. Nếu handler đã gọi `sendResponseHeaders`, không thể tùy tiện gửi response status mới lần hai trên cùng exchange; cần cleanup và logging thay vì cố ghi thêm một lỗi 500 khác.

## 16. Kiểm thử đúng routing và response

Hai chương trình dùng `java.net.http.HttpClient` gửi request thật tới địa chỉ đã bind. Điều đó kiểm chứng đồng thời:

- Socket đã bind đúng và có port hoạt động.
- `start()` đã bắt đầu nhận request.
- Context matching chọn đúng handler.
- Handler thiết lập response headers, status và body.
- Không có handler tương ứng thì JDK trả 404 (khi không có root context).
- Method GET/POST có thể được phân loại riêng bởi handler.
- `removeContext(...)` thay đổi routing tương ứng.
- `stop(...)` và cleanup không để lại server demo chạy mãi.

Nếu muốn kiểm tra thủ công khi server được chạy như một chương trình dài hạn, có thể dùng:

~~~bash
curl -i http://127.0.0.1:8080/hello
curl -i http://127.0.0.1:8080/api/users
curl -i -X POST http://127.0.0.1:8080/hello
~~~

*Lệnh curl là minh họa cho server **thực sự bind cổng 8080 và đang chạy**. Hai chương trình trong bài dùng **port 0** và tự dừng sau test, vì vậy không thể mặc định các lệnh trên sẽ kết nối được tới demo. Với chương trình ở phần 9–11, xem stdout là kết quả kiểm thử xác định.*

Đối với CI, dùng port `0` rồi lấy port thực từ `getAddress()` để các test song song giảm đụng cổng; assert HTTP status/body và luôn cleanup trong `finally`. Test cả đường dẫn gần giống `/legacyExtra`, path khác hoa/thường và endpoint không có để phát hiện sai lầm về prefix matching.

## 17. Những nhầm lẫn phổ biến

| Nhầm lẫn | Hậu quả | Cách nhớ |
| --- | --- | --- |
| “`HttpServer.create()` đã mở port” | Chưa bind, client không kết nối được | Gọi `bind` |
| “`create(addr,backlog)` bắt đầu nhận ngay” | Chưa start | Gọi `start()` sau khi cấu hình |
| “Port `0` nghĩa là port không hợp lệ” | Hiểu sai test bind | OS cấp port trống; đọc `getAddress().getPort()` |
| “Backlog 20 nghĩa là tối đa 20 HTTP handlers” | Sai tầng mạng | Backlog là pending TCP connects |
| “`/foo` chỉ match chính xác `/foo`” | Có thể match `/foobar` | Dùng `/foo/` và validate route |
| “Context path không phân biệt hoa/thường” | Route sai | So khớp literal, case-sensitive |
| “`/api/` cũng match `/api`” | Path prefix khác | Đăng ký/canonicalize cụ thể |
| “`/users/{id}` là template routing của JDK” | Không tự extract id | Handler tự parse/validate path |
| “`createContext` chỉ được gọi một lần/server” | Không hiểu nhiều endpoints | Một server có nhiều contexts |
| “Có root context, unmatched route vẫn tự 404” | Root bắt mọi path | Root handler phải tự quyết định 404 |
| “Đăng ký context bảo vệ endpoint” | Endpoint admin có thể bị truy cập trái phép | Auth/authorization riêng |
| “`setHandler` thay thế handler đã có tùy ý” | `IllegalArgumentException` | Gắn lần đầu hoặc dùng delegate |
| “String.length() chính là Content-Length UTF-8” | Response body bị cắt/IO failure | Dùng `byte[].length` |
| “`sendResponseHeaders(200,0)` là no body” | 0 nghĩa là chunked | Dùng -1 khi không có body |
| “`server.stop(0)` là có thể restart” | Không tái sử dụng server đã stop | Tạo instance mới |
| “`stop` tự shutdown executor ngoài” | Thread pool có thể còn sống | Shutdown pool riêng |
| “Bind `0.0.0.0` luôn chỉ phục vụ local” | Có thể mở service ra mạng | Chọn interface và firewall |
| “HTTP server này tự dùng TLS” | `http://` là plaintext | Dùng `HttpsServer` + TLS |

## 18. Tự kiểm tra

**Câu 1.** `HttpServer.create()` khác `HttpServer.create(new InetSocketAddress("127.0.0.1",8080),16)` ở điểm nào?

*Đáp án:* `create()` tạo instance **chưa bind**, sau đó phải `bind(addr,backlog)`. Overload có địa chỉ **bind ngay**, nhưng cả hai đều cần `start()` để phục vụ request.

**Câu 2.** Khi bind port 0, làm sao client test biết port thực?

*Đáp án:* Gọi `server.getAddress().getPort()` **sau khi bind**, dùng port đó để tạo URI của client. Không hard-code port 0 vào URL của client.

**Câu 3.** Có `/`, `/app/`, `/app/admin/`, request `/app/admin/users` chọn context nào?

*Đáp án:* `/app/admin/` vì nó là **tiền tố literal khớp dài nhất**.

**Câu 4.** Vì sao `/legacyExtra` lại match context `/legacy`?

*Đáp án:* HttpServer kiểm tra **tiền tố ký tự**, không bắt buộc ranh giới path segment. Khi muốn nhánh con hãy dùng `/legacy/` và validate route.

**Câu 5.** Có một context `/` catch-all thì request `/unknown` tự nhận 404 không?

*Đáp án:* Không chắc. Nó match root; status phụ thuộc handler của root. Không có context nào khớp mới tự 404.

**Câu 6.** Khi gửi body UTF-8 `Xin chào`, có nên dùng `String.length()` cho responseLength không?

*Đáp án:* Không. `sendResponseHeaders(status, responseLength)` dùng **số byte**; mã hóa UTF-8 thành `byte[]` rồi lấy `bytes.length`.

**Câu 7.** `stop(5)` có cho phép `start()` lại cùng instance không?

*Đáp án:* Không. `delay=5` là khoảng đợi tối đa khoảng 5 giây cho các exchange đang xử lý trước khi đóng; server dừng rồi không restart được.

**Câu 8.** Một context `/admin/` có tự yêu cầu đăng nhập không?

*Đáp án:* Không. Context chỉ chọn handler theo path; cần `Authenticator`, filters hoặc kiểm tra bảo mật phù hợp ở ứng dụng.

## 19. Bài tập thực hành

1. Tự viết server `HttpServer.create()`, `bind(127.0.0.1:0, 8)`, `createContext("/ping",...)`, `start()` và dùng `HttpClient` gọi để nhận `200 pong`. Đóng exchange và dừng server trong finally.
2. Chuyển sang `HttpServer.create(new InetSocketAddress("127.0.0.1",0),8)`, bỏ `bind(...)`; xác minh chương trình vẫn chạy khi server đã bind ngay.
3. Trong `HttpServerBindDemo`, thêm `/helloExtra` để thử chuyện `"/hello"` có thể được chọn bởi prefix nhưng handler đã kiểm tra path exact và trả 404.
4. Trong `HttpContextRoutingDemo`, đổi `/legacy` thành `/legacy/`; thử `/legacyExtra` và `/legacy/item` để quan sát khác biệt, nhớ rằng context root có thể bắt request không khớp.
5. Thêm hai context `/api/` và `/api/orders/`, dùng `exchange.getHttpContext().getPath()` để kiểm tra tiền tố dài nhất; thử URL với chữ hoa khác.
6. Đăng ký context bằng `createContext("/new/")` rồi `setHandler(...)` đúng một lần. Thử gắn thêm handler để quan sát lỗi và giải thích tại sao đây không phải API hot-swap.
7. Thử gửi POST vào handler chỉ nhận GET, kiểm tra status `405` và header `Allow: GET`; phân biệt với 404 khi path không tồn tại.
8. Thay response ASCII bằng text UTF-8 có dấu, tính `bytes.length` và kiểm tra body nhận không bị cắt.
9. Viết kiểm thử server trả response rỗng theo semantics của `sendResponseHeaders(...,-1)`, so sánh với chế độ chunked khi truyền `0`.
10. Cấu hình pool có giới hạn trước `start()`, gửi nhiều request concurrent và đo thời gian; xác định vai trò executor khác backlog.
11. Bắt `BindException` khi cố chạy hai server cùng port cố định; không chuyển sang port ngẫu nhiên âm thầm ở môi trường cần port xác định.
12. Thiết kế một endpoint health check local an toàn: bind loopback, method GET, response có giới hạn, không trả secret; giải thích những thay đổi cần thiết nếu phải phục vụ từ mạng khác.
13. Tạo context có `Filter` hoặc `Authenticator` cho `/admin/`, kiểm tra unauthorized response và logging; không xem tên path là đủ để bảo vệ.
14. Lập checklist startup/shutdown: bind interface, port, contexts, handler, filters, executor, start, metrics, stop(delay), executor shutdown. Kiểm tra không thể restart cùng instance.

## Tài liệu tham khảo chuẩn

- [`HttpServer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `create`, `bind`, `createContext`, `setExecutor`, `start`, `stop`, longest literal prefix.
- [`HttpContext` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): `setHandler`, `getPath`, filters, authenticator, attributes.
- [`HttpHandler` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): `handle(HttpExchange)`.
- [`HttpExchange` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response lifecycle, headers, body streams và `sendResponseHeaders`.
- [`HttpsServer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): server HTTPS.
- [`HttpClient` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client dùng để kiểm thử server.
