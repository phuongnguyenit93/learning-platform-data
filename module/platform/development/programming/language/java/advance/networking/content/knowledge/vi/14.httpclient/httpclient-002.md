# Tạo HttpClient có thể dùng lại và chia sẻ tài nguyên kết nối (Java 17+)

`java.net.http.HttpClient` là HTTP client chuẩn của Java từ Java 11, hỗ trợ HTTP/1.1, HTTP/2 và hai kiểu gọi **đồng bộ** (`send`) hoặc **bất đồng bộ** (`sendAsync`). Để sử dụng hiệu quả, **hãy tạo `HttpClient` một lần cho một cấu hình/nhóm dịch vụ thích hợp, sau đó tái sử dụng instance đó qua nhiều request và nhiều thread**, thay vì tạo `HttpClient.newHttpClient()` trong mỗi lần gọi API.

Một `HttpClient` đã `build()` là **immutable** và được thiết kế cho nhiều request. Nó giữ thông tin cấu hình và chia sẻ tài nguyên nội bộ của quá trình trao đổi HTTP. Bản triển khai thường quản lý connection pool của riêng client để có thể tái sử dụng các kết nối khi thích hợp. Tuy nhiên **không được hứa rằng mọi request sẽ dùng đúng một TCP connection**: server, proxy, phiên bản HTTP, idle timeout, tình trạng kết nối và chính sách triển khai đều có thể ảnh hưởng.

Bài thuộc **HttpClient** trong **Java Advance - networking**, tập trung vào kiến trúc tái sử dụng, connection pooling, lựa chọn scope, thread safety, `send`/`sendAsync`, cấu hình, body lifecycle, quá tải, timeout, bảo mật và ví dụ chạy thật trên JDK 17+.

## 1. Ba cấp độ không được nhầm: client, HTTP request và TCP connection

```text
Application / service (nhiều lời gọi API)
       |
       +---- request A (HttpRequest immutable) -----+
       +---- request B (HttpRequest immutable) -----+----> SHARED HttpClient
       +---- request C (HttpRequest immutable) -----+         |
                                                         | preferred HTTP version
                                                         | proxy / SSLContext / cookies
                                                         | executor / authentication
                                                         v
                                              HTTP transport & connections
                                               /          |           \
                                           socket 1    socket 2     HTTP/2 streams
                                               \          |           /
                                               remote HTTP server / proxy
```

Phân biệt:

- **`HttpClient`:** thành phần dài hạn của ứng dụng. Nó chứa cấu hình của client và cung cấp khả năng chia sẻ tài nguyên giữa nhiều HTTP exchange.
- **`HttpRequest`:** một request được xây từ `HttpRequest.Builder`, gồm URI, method, headers, timeout, body publisher nếu cần. Đối tượng `HttpRequest` sau `build()` là immutable; tạo một request mới mỗi operation thường rõ ràng nhất khi dữ liệu thay đổi.
- **HTTP connection:** kết nối vật lý ở tầng transport hoặc phiên TCP/TLS mà implementation có thể mở, giữ idle, tái sử dụng hoặc đóng. **Ứng dụng không được quyền suy luận “một client = một socket”.**

Nhiều request dùng một client **không bắt buộc** chạy trên cùng kết nối. Với HTTP/1.1, nhiều request tuần tự có thể tái sử dụng persistent connection; khi song song hoặc bên kia đóng socket, client có thể phải mở nhiều connection. Với HTTP/2, nhiều request có thể cùng chia sẻ một kết nối bằng các stream độc lập nếu đã đàm phán HTTP/2 và điều kiện cho phép.

## 2. Vì sao không nên tạo client mới ở mọi request?

Anti-pattern thường thấy:

```java
// Ví dụ cấu trúc sai về quản lý tài nguyên:
// hàm được gọi lặp lại nhiều lần, mỗi lần lại tạo HttpClient mới.
static String fetch(URI uri) throws Exception {
    HttpClient client = HttpClient.newHttpClient();
    HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
    return client.send(request,
            HttpResponse.BodyHandlers.ofString()).body();
}
```

Đây chỉ là snippet minh họa, thiếu imports/class. Về mặt chức năng, nó có thể trả nội dung đúng, nhưng có những nhược điểm:

1. **Không tạo cơ hội chia sẻ transport cùng instance:** client mới thường có tập kết nối/tài nguyên nội bộ riêng. Mỗi lần tạo mới có thể tốn setup TCP, TLS và quản lý threads/buffers.
2. **Tăng chi phí tại tải cao:** nhiều client sống ngắn tạo nhiều objects và socket lifecycle, giảm hiệu quả keep-alive và session reuse.
3. **Cấu hình rải rác:** timeout, proxy, redirect policy, TLS trust, cookie/authentication dễ lệch nhau giữa các lần gọi.
4. **Khó quan sát:** không còn một “client policy” nhất quán, khó gắn metrics, retry/backpressure và resource quotas vào service.

**Không phải cứ tạo client mới thì chắc chắn mở thêm một TCP connection ngay lập tức**; việc kết nối còn phụ thuộc phương thức gọi và provider. Luận điểm đúng là: tạo client mới **làm mất cơ hội chia sẻ ở cấp instance**, trong khi reuse phù hợp với cách API được thiết kế.

## 3. Mẫu kiến trúc đề xuất: một shared instance theo scope phù hợp

Một phương án đơn giản:

```java
// Snippet minh họa, đặt bên trong lớp ứng dụng/service.
private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

String fetch(URI uri) throws Exception {
    HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
    return response.body();
}
```

Các imports và lớp bao ngoài bị lược bỏ nên đây **không phải chương trình độc lập**. Điểm chính là `HttpClient` được **khởi tạo khi service được tạo**, không tạo trong `fetch`. `HttpRequest` được tạo mới theo mỗi URI, timeout và header cụ thể.

Một mẫu thuận tiện cho dependency injection (minh họa):

```java
final class ProductApi {
    private final HttpClient http;

    ProductApi(HttpClient http) {
        this.http = http;
    }

    // Mọi phương thức gọi API của ProductApi dùng this.http.
}
```

Ứng dụng tạo client trong tầng composition root rồi truyền vào các service có **chung chính sách proxy/TLS/auth/cookie**, thay vì gọi `newHttpClient()` lặp lại bên trong domain method. Service có thể được test với HTTP server local hoặc adapter riêng, và cấu hình tập trung giúp kiểm soát timeout.

## 4. Bất biến không đồng nghĩa tất cả thành phần liên quan đều bất biến

Java 17 API xác nhận `HttpClient` **immutable sau khi `build()`**, có thể phục vụ nhiều requests. Nhưng:

- **`HttpClient.Builder` là mutable và không thread-safe.** Không chia sẻ cùng một builder rồi gọi `version`, `proxy`, `sslContext` từ các thread đồng thời. Cấu hình xong rồi `build()`, chia sẻ client.
- **`HttpRequest.Builder` cũng là builder mutable**, không nên được nhiều thread cùng chỉnh header/URI/body. Mỗi request tạo builder riêng.
- **`HttpRequest` đã build là immutable**, có thể dùng như một cấu hình request. Tuy nhiên khả năng **gửi lại phần body** còn phụ thuộc `BodyPublisher`; một input stream/file/producer stateful không nhất thiết có thể phát lại tùy ý. Với GET mới, tạo request mới thường rõ hơn.
- **`CookieHandler`, `Authenticator`, `Executor`, custom body publisher/subscriber** mà ứng dụng đưa vào client có thể mang mutable state riêng. Client immutable **không tự biến mọi collaborator thành thread-safe**.
- **`HttpResponse.BodyHandler`** và xử lý response của từng exchange phải tuân thủ giao diện và tính an toàn của chính handler; không dùng chung một `InputStream` nhận cho nhiều request.
- **Cấu hình bảo mật** có thể chứa reference tới provider/custom objects; “immutable client” không đồng nghĩa chính sách của một external credential store tự rotate khi đổi file trên disk.

**Quy tắc:** chia sẻ `HttpClient`, tạo request riêng; quản lý các thành phần mutable theo quyền sở hữu và luồng thực thi rõ ràng.

## 5. Tạo client một lần: các lựa chọn cấu hình cấp client

Ví dụ minh họa cấu hình cơ bản:

```java
HttpClient shared = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .version(HttpClient.Version.HTTP_2)
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Bốn lưu ý:

1. `connectTimeout` chỉ điều chỉnh thời gian **thiết lập kết nối mới**. Khi một connection sẵn có được reuse, giới hạn connect này không phải timeout của toàn bộ request.
2. `version(HTTP_2)` là **mức ưu tiên/đề nghị**, không hứa server/proxy đều hỗ trợ HTTP/2. Kiểm tra `response.version()` để biết request đó thực tế dùng version nào. Demo local dưới đây dùng `HTTP_1_1` để tương thích với `jdk.httpserver.HttpServer`.
3. `followRedirects` cần được thiết kế theo bảo mật và API contract. `Redirect.NEVER` không tự động đi theo redirect; `Redirect.NORMAL` cho phép theo một số redirect nhưng không thay thế việc xét miền đích, header bí mật và các chính sách.
4. `HttpClient.newHttpClient()` tương đương client xây bằng builder mặc định. Theo tài liệu Java 17, mặc định **ưu tiên HTTP/2**, redirect policy là `NEVER`. Nếu yêu cầu khác, cấu hình ngay lúc build.

Những cấu hình cấp client khác: `proxy(ProxySelector)`, `authenticator(Authenticator)`, `cookieHandler(CookieHandler)`, `sslContext(SSLContext)`, `sslParameters(SSLParameters)` và `executor(Executor)`. Để tránh lây lan session/credential, **không gộp các request khác tenant/principal vào một client chung** khi collaborator như cookie jar, authenticator hay trust policy có thể gây cross-tenant leakage.

## 6. Khi nào phải tạo nhiều HttpClient thay vì một singleton toàn JVM?

Mục tiêu không phải “cả ứng dụng chỉ có đúng một object `HttpClient`”. Scope nên do **chính sách chia sẻ tài nguyên và bảo mật** quyết định:

| Trường hợp | Scope thường hợp lý | Lý do |
| --- | --- | --- |
| Một service gọi cùng nhóm API với cùng proxy/TLS/trust và credential boundary | Một `HttpClient` cho service/integration | Chia sẻ cấu hình và tài nguyên |
| Nhiều worker/threads gọi cùng external API, cùng policy | Chia sẻ instance qua injection | Không cần tạo theo thread hay request |
| Một ứng dụng gọi các hệ thống yêu cầu truststore/proxy khác nhau | Nhiều `HttpClient` theo từng policy | Tránh trust quá rộng và cấu hình xung đột |
| Các tenant phải cách ly cookies/authorization state | Client hoặc collaborator partition theo tenant | Tránh session/credential leakage |
| Cần cô lập tải/giới hạn tài nguyên cho hai downstream rất khác nhau | Có thể tách client + quotas/bulkhead | Tách failure domain, đo lường và policy |
| One-off CLI hoặc thử nghiệm nhanh | Tạo một client cho vòng đời lệnh | Không cần hệ thống DI phức tạp |

Cùng client có thể gửi request đến nhiều origin, nhưng **điều đó không có nghĩa một TCP connection được sử dụng xuyên mọi hostname/port/trust context**. Khóa kết nối/pooling phụ thuộc implementation, origin, proxy, protocol, TLS, chính sách bảo mật và trạng thái mạng. Hãy dùng “một client chia sẻ theo policy”, không “một socket cho toàn hệ thống”.

## 7. HTTP/1.1 keep-alive và HTTP/2 multiplexing

### HTTP/1.1

Với persistent connection, server/client có thể tái sử dụng cùng TCP connection cho **những request nối tiếp** khi protocol cho phép. Nếu tải đồng thời cao, client có thể sử dụng **nhiều TCP connections** tới cùng origin. Không suy luận rằng mọi request chia đúng một socket; cũng không nên tự chỉnh header `Connection: keep-alive` để ép JDK internals. Java `HttpClient` quản lý connection lifecycle và một số header bị hạn chế theo implementation.

Ví dụ:

```text
HttpClient A --- request 1 ---> [TCP connection X] ---> api.example
             <--- response 1 ---
             --- request 2 ---> [có thể reuse X]
             <--- response 2 ---
             --- request 3 ---> [có thể X, cũng có thể Y nếu X đóng]
```

### HTTP/2

HTTP/2 có **multiplexing**: nhiều request/response được gán stream IDs, có thể đi song song trên cùng một connection; điều này giúp tiết kiệm một số overhead và tránh giới hạn của kiểu HTTP/1.1 không multiplex tương tự. Nhưng:

- Server/proxy phải hỗ trợ; với HTTPS thường dùng TLS/ALPN. Client chỉ *ưu tiên* HTTP/2 không bảo đảm version thực tế.
- Server có thể giới hạn số concurrent streams; client có thể mở hoặc dùng nhiều kết nối trong các tình huống thích hợp.
- Một kết nối TCP nền có thể tạo ra một số tương tác giữa streams khi packet loss; HTTP/2 không loại bỏ mọi vấn đề head-of-line của tầng transport.
- Không sử dụng `client.version()` như bằng chứng về version của response; đọc **`response.version()`**.

Ở cả hai giao thức, chuyện connection reuse bị ảnh hưởng bởi timeout idle, server `Connection: close`/GOAWAY, load balancer, proxy, TLS policy và hệ điều hành. **Tái sử dụng client làm tăng cơ hội reuse, không phải bảo đảm số lượng TCP connection.**

## 8. Ví dụ Java 17+ số 1: một client gửi ba request tuần tự

Tệp **`ReuseHttpClientDemo.java`** tạo HTTP server local trong cùng JVM nhờ module chuẩn của JDK `jdk.httpserver`, bind vào `127.0.0.1` và port được hệ điều hành cấp. Chương trình xây **một HttpClient** trước vòng lặp rồi dùng nó gửi ba GET request. Server trả lời lần lượt `hello-1`, `hello-2`, `hello-3`.

Không cần Internet, DNS public hay tài khoản API để chạy.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class ReuseHttpClientDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(2);
        AtomicInteger hits = new AtomicInteger();

        server.createContext("/hello", exchange -> {
            try {
                byte[] body = ("hello-" + hits.incrementAndGet())
                        .getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(serverWorkers);
        server.start();

        try {
            int port = server.getAddress().getPort();
            URI endpoint = URI.create(
                    "http://127.0.0.1:" + port + "/hello");

            // One immutable client configured once and reused.
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            List<String> responses = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                // A new immutable request per operation.
                HttpRequest request = HttpRequest.newBuilder(endpoint)
                        .timeout(Duration.ofSeconds(5))
                        .GET()
                        .build();
                HttpResponse<String> reply = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));
                if (reply.statusCode() != 200) {
                    throw new IOException("Unexpected status");
                }
                responses.add(reply.body());
            }

            System.out.println("Responses: " + responses);
            System.out.println("Server requests: " + hits.get());
            System.out.println("Client HTTP preference: "
                    + client.version());
        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 ReuseHttpClientDemo.java
java --add-modules jdk.httpserver ReuseHttpClientDemo
```

Stdout cho một lần chạy hoàn tất:

```text
Responses: [hello-1, hello-2, hello-3]
Server requests: 3
Client HTTP preference: HTTP_1_1
```

**Điểm cần rút ra từ code:**

1. `HttpClient client` chỉ được tạo **một lần**, nằm ngoài vòng `for`. Mỗi request lại dùng một `HttpRequest` mới, với cùng URI nhưng timeout riêng, để tách lifetime và thay đổi dữ liệu.
2. `HttpResponse.BodyHandlers.ofString(UTF_8)` tiêu thụ body vào `String`, nên ba request thực sự hoàn tất trao đổi nội dung. Không cố ý bỏ một streaming response chưa đọc.
3. `HttpServer` nhận 3 request trên loopback; `AtomicInteger` đếm request, không đo số socket. Output **không khẳng định một TCP connection duy nhất** đã được tái sử dụng.
4. `client.version()` là **HTTP version ưu tiên được cấu hình**, không phải kiểm chứng version của từng response. Để kiểm tra thực tế, có thể bổ sung logging `response.version()`.
5. `server.stop(0)` và `serverWorkers.shutdownNow()` dọn HTTP server thử nghiệm. Trong Java 17, **`HttpClient` không có `close()`/không implements `AutoCloseable`**: đừng bịa lời gọi `client.close()` hoặc đặt `HttpClient` vào try-with-resources trên JDK 17. API vòng đời khác có thể xuất hiện ở JDK mới hơn.
6. Test thành công chứng minh một client có thể gửi nhiều request và server xử lý đúng. Để xác nhận **TCP socket reuse**, cần đo/capture remote port hoặc connection metrics riêng và chấp nhận rằng mạng/implementation có thể thay đổi quyết định.

## 9. Tái sử dụng HttpClient qua nhiều thread có an toàn không?

**Có, với instance đã xây xong và dùng theo đúng API.** `HttpClient` là immutable, cung cấp phương thức gửi được thiết kế để thực hiện nhiều request. Một service có thể cho nhiều thread/task gửi request qua cùng client. Điều này **không có nghĩa toàn bộ chương trình tự động thread-safe**.

- **Safe:** chia sẻ tham chiếu `final HttpClient sharedClient` cho nhiều service; mỗi task tự tạo `HttpRequest.Builder` và `HttpRequest`, tự sở hữu phần body và future của nó.
- **Unsafe:** dùng chung một mutable `HttpRequest.Builder` và nhiều thread gọi `header`/`uri`/`build` đồng thời.
- **Unsafe:** dùng một `CookieStore` hoặc `Authenticator` tự viết không bảo đảm concurrency và tenant boundary; thread-safety của client không sửa được lỗi ở collaborator.
- **Unsafe:** nhiều task cùng đọc một response `InputStream`/cùng mutate một request body publisher stateful mà không có synchronization.
- **Cần cân nhắc:** chọn size thread pool và số lượng outstanding requests; thread-safe không đồng nghĩa vô hạn tài nguyên.

Nhờ vậy, thay vì tạo client “per thread”, thường thiết kế **một client per logical integration** và chia sẻ trong các thread xử lý. Resource isolation và credentials mới là lý do quan trọng để tạo thêm instance.

## 10. `send` đồng bộ và `sendAsync` bất đồng bộ

| Tiêu chí | `client.send(request, handler)` | `client.sendAsync(request, handler)` |
| --- | --- | --- |
| Cách gọi | Chặn thread gọi trong khi gửi/nhận theo kiểu đồng bộ | Trả về `CompletableFuture<HttpResponse<T>>` để theo dõi việc hoàn thành |
| Kết quả | `HttpResponse<T>` hoặc exceptions | Completion thành công/thất bại; `join` có thể bọc lỗi trong `CompletionException` |
| Phù hợp | Luồng xử lý đơn giản, giới hạn concurrency bởi số thread | Nhiều I/O concurrent với composition của futures |
| Dùng client | Vẫn chia sẻ một client | Vẫn chia sẻ chính client đó |
| Hạn mức | Thread-per-request có giới hạn của worker pool | Cần **giới hạn in-flight requests** bằng semaphore/batch/queue |
| Callback | Logic sau `send` chạy trên caller | Các `thenApply`/`thenCompose`/`handle` có chính sách executor; tránh chặn thread I/O |

`sendAsync` **không đồng nghĩa “tự giới hạn số request”**. Tạo 100.000 futures liên tiếp mà không kiểm soát outstanding requests có thể làm tăng memory, sockets, server load và queue. Các handler tự viết không nên làm công việc CPU/blocking lớn trong callback chạy trên execution context không được kiểm soát.

`CompletableFuture.allOf` rất hợp để chờ một batch nhỏ. Với workloads lớn, có thể dùng bounded scheduler, semaphore hoặc reactive backpressure. Giới hạn concurrency cần đi cùng **deadline, rate limit, retry budget và circuit breaker** theo SLA, chứ không chỉ là con số threads.

## 11. Ví dụ Java 17+ số 2: một client chung cho 12 async requests, giới hạn 4 in-flight

Tệp **`SharedHttpClientAsyncDemo.java`** tạo một HTTP server local, sau đó **một shared HttpClient** gửi 12 GET requests. Nó chia thành ba batch, mỗi batch tối đa **4 future đang outstanding**. Mỗi request mang `id` riêng; server trả `id-0` tới `id-11`. Phía client lưu response theo thứ tự **futures được tạo** để output xác định dù network hoàn tất khác thứ tự.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedHttpClientAsyncDemo {
    private static final int TOTAL = 12;
    private static final int BATCH = 4;

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(4);
        AtomicInteger hits = new AtomicInteger();

        server.createContext("/item", exchange -> {
            try {
                String query = exchange.getRequestURI().getRawQuery();
                if (query == null || !query.matches("id=[0-9]+")) {
                    exchange.sendResponseHeaders(400, -1);
                    return;
                }
                int id = Integer.parseInt(query.substring(3));
                hits.incrementAndGet();
                byte[] body = ("id-" + id)
                        .getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(serverWorkers);
        server.start();

        try {
            int port = server.getAddress().getPort();
            HttpClient sharedClient = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            List<String> bodies = new ArrayList<>();
            boolean allOk = true;

            // At most four outstanding exchanges in each batch.
            for (int start = 0; start < TOTAL; start += BATCH) {
                List<CompletableFuture<HttpResponse<String>>> pending =
                        new ArrayList<>();
                for (int i = start; i < Math.min(TOTAL, start + BATCH);
                     i++) {
                    URI target = URI.create("http://127.0.0.1:"
                            + port + "/item?id=" + i);
                    HttpRequest request = HttpRequest.newBuilder(target)
                            .timeout(Duration.ofSeconds(5))
                            .GET()
                            .build();
                    pending.add(sharedClient.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8)));
                }

                CompletableFuture.allOf(
                        pending.toArray(new CompletableFuture<?>[0]))
                        .join();

                // Reading futures in submission order makes output stable.
                for (CompletableFuture<HttpResponse<String>> future
                        : pending) {
                    HttpResponse<String> reply = future.join();
                    allOk &= reply.statusCode() == 200;
                    bodies.add(reply.body());
                }
            }

            boolean ordered = true;
            for (int i = 0; i < TOTAL; i++) {
                ordered &= ("id-" + i).equals(bodies.get(i));
            }
            System.out.println("Responses: " + bodies.size());
            System.out.println("Max submitted per batch: " + BATCH);
            System.out.println("All HTTP 200: " + allOk);
            System.out.println("Bodies match request order: " + ordered);
            System.out.println("Server handled: " + hits.get());
        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 SharedHttpClientAsyncDemo.java
java --add-modules jdk.httpserver SharedHttpClientAsyncDemo
```

Stdout khi hoàn tất:

```text
Responses: 12
Max submitted per batch: 4
All HTTP 200: true
Bodies match request order: true
Server handled: 12
```

Giải thích:

1. `sharedClient` được xây **một lần** trước khi gửi 12 request. Mọi lời gọi `sendAsync` sử dụng đúng instance đó, mở cơ hội cho implementation quản lý kết nối.
2. Mỗi request có URI, `HttpRequest` và future riêng, không chia sẻ builder mutable. Server phản hồi `id-i` theo query, nên có thể kiểm tra response có khớp từng request hay không.
3. `CompletableFuture.allOf(...).join()` đảm bảo batch trước hoàn tất (hoặc báo lỗi) rồi mới gửi batch sau, do đó có **không quá 4 request đang outstanding từ chương trình** trong kịch bản này.
4. `pending` được duyệt theo thứ tự gửi, nên `bodies` giữ thứ tự ID, **không chứng minh mạng trả về theo thứ tự**. Hoàn tất asynchronous có thể đảo thứ tự; code tách ordering của output khỏi completion order.
5. Server có pool xử lý 4 threads, nhưng số threads **không đồng nhất số TCP connections**. Client có thể dùng nhiều socket HTTP/1.1 khi gửi đồng thời.
6. `BodyHandlers.ofString` đã tiêu thụ response body trước khi future hoàn thành theo handler này, giảm rủi ro giữ connections bận vì response chưa được đọc.
7. Nếu một future lỗi hoặc timeout, `allOf().join()` có thể ném `CompletionException`; production nên map exception, cancel phần cần cancel và áp dụng policy retry theo từng request.

Batch là một hình thức **giới hạn đơn giản**, nhưng có độ trễ giữa batch. Với traffic liên tục, bounded semaphore/queue có thể giữ tối đa N in-flight mà không đợi toàn bộ batch kết thúc. Dù dùng mô hình nào, invariant quan trọng là **số request đang gửi/đang xử lý không thể tăng vô hạn**.

## 12. Response body quyết định kết nối có thể được trả về pool khi nào

Đây là điểm thường bị bỏ qua khi tối ưu “reuse HttpClient”: **reuse client không giúp nhiều nếu exchange cũ giữ body hoặc resource chưa giải phóng**.

Một số `BodyHandlers`:

| Handler | Thời điểm có nội dung/điều kiện | Hệ quả resource |
| --- | --- | --- |
| `BodyHandlers.ofString(...)` | Thu toàn bộ body rồi tạo `String` | Thích hợp body nhỏ/vừa, nhưng body lớn có thể tốn heap |
| `BodyHandlers.ofByteArray()` | Thu toàn bộ body thành `byte[]` | Tiện cho payload giới hạn, không dùng vô tội vạ cho body vô hạn |
| `BodyHandlers.discarding()` | Nhận và bỏ body theo cơ chế handler | Có ích khi chỉ cần status/headers; không giữ stream cho caller |
| `BodyHandlers.ofFile(path)` | Ghi body vào file | Thích hợp nội dung lớn có kiểm soát; xử lý lỗi disk/permission |
| `BodyHandlers.ofInputStream()` | Trả `InputStream` sau khi headers đã sẵn sàng | **Caller phải đọc hết đến EOF hoặc close** để giải phóng exchange |
| `BodyHandlers.ofLines()` | Trả stream các dòng | **Đọc hết hoặc close** stream để hoàn tất giải phóng resource |

Với streaming handler, `HttpResponse<InputStream> response = client.send(..., BodyHandlers.ofInputStream())` **không có nghĩa response body đã được đọc hết**. Dùng try-with-resources cho **body stream**:

```java
// Snippet minh họa: client và request đã tồn tại.
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    // Đọc với kích thước tối đa, giới hạn thời gian và xử lý lỗi.
    // Hoặc đọc hết nếu protocol và dung lượng cho phép.
}
```

Nếu caller đóng stream **trước khi đọc hết**, implementation có thể phải **đóng underlying HTTP connection**, làm nó **không thể reuse**. Đọc hết đến EOF tạo điều kiện giải phóng tài nguyên đúng cách nhưng không bảo đảm socket sẽ được reuse, vì còn nhiều điều kiện khác. Không cố tải response 2 GB bằng `ofString` chỉ để giữ keep-alive.

## 13. Thiết lập timeout ở đúng lớp, tránh “client dùng chung thì đợi mãi”

Hai loại timeout dễ nhầm:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3)) // khi cần new connection
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))        // deadline exchange này
        .GET()
        .build();
```

Đây là snippet minh họa, không độc lập. Theo Java 17 API:

- **`HttpClient.Builder.connectTimeout`** áp dụng khi **cần thiết lập kết nối mới**; nếu request tái sử dụng connection sẵn có, giới hạn này **không được dùng để timeout phần xử lý request trên connection đó**.
- **`HttpRequest.Builder.timeout`** áp dụng cho việc nhận HTTP response của request theo hợp đồng API; khi hết có thể ném `HttpTimeoutException` hoặc future hoàn tất lỗi. Thiết kế deadline nghiệp vụ còn cần xét body streaming sau khi headers có mặt.
- **`send`** là lời gọi đồng bộ có thể ném `IOException`, `InterruptedException`. Nếu interrupt, giữ interrupt status/cleanup hợp lý và không tự động đoán rằng server **chưa** nhận request.
- **`sendAsync`** có future. `future.cancel(true)` là nỗ lực hủy exchange; theo API **không bảo đảm** hủy ngay trước khi server xử lý. Trong HTTP/1.1 nó có thể đóng connection; HTTP/2 có thể reset stream hoặc ảnh hưởng connection.
- `CompletableFuture.orTimeout` chỉ áp deadline lên completion của future theo cơ chế tương ứng; không biến một remote write đã thực hiện thành “chưa xảy ra” và không tự bảo đảm mọi resource/side effect bị thu hồi.

Đừng cấu hình timeout bằng một giá trị cho tất cả integration mà không xét latency, SLA, endpoint, request size và retry policy. Shared client có **connect timeout chung**, trong khi mỗi request có thể cần **request timeout riêng**.

## 14. Retry và idempotency: chia sẻ connection không thay thế logic nghiệp vụ

Nếu request lỗi do socket đóng khi reuse, reset, timeout hoặc HTTP 503:

- Với **GET idempotent**, có thể thử lại theo policy và retry budget khi thích hợp; vẫn cân nhắc load/backoff, rate limit, cache consistency và lỗi thực tế.
- Với **POST tạo đơn hàng/thanh toán**, không tự động retry chỉ vì không thấy response: server có thể đã xử lý giao dịch rồi response bị mất. Cần idempotency key và chính sách server hỗ trợ, hoặc xác minh trạng thái trước khi retry.
- **Không giả định `HttpClient` luôn retry mọi request hoặc hoàn toàn không retry**; implementation có thể có hành vi riêng cho lỗi kết nối trong những điều kiện nhất định. Xây quy tắc ứng dụng đúng semantics, không dựa vào retry ngầm không kiểm soát.
- **`BodyPublisher` phải phát lại được** nếu định gửi lại body. `BodyPublishers.ofInputStream` với supplier/stream mang trạng thái cần được xem xét kỹ; đừng reuse một stream đã đọc hết.
- Retry có thể yêu cầu **request mới** với header/token/date mới. Không giữ mutable builder với token cũ hoặc vô tình lặp lại authorization khác tenant.

Điểm an toàn: “client được reuse” là chuyện **transport**, còn “request có thể retry” là chuyện **HTTP method, idempotency, body publisher và business contract**.

## 15. Chia sẻ cấu hình: cookie jar, authenticator, token và TLS trust

Một `HttpClient` có thể chứa `CookieHandler`, `Authenticator`, `ProxySelector` và `SSLContext`. Việc share những thành phần này có ý nghĩa lớn:

- **Cookies/session:** nếu một shared `CookieHandler` lưu cookies chung, request từ các tài khoản/tenant khác nhau có thể bị lẫn session nếu không partition đúng. Không chia sẻ cross-user jar chỉ để tiết kiệm socket.
- **Authentication:** `Authenticator` có thể được gọi khi HTTP/proxy yêu cầu; custom implementation và secret state phải thread-safe. Một Bearer token riêng per request thường được đưa bằng `HttpRequest.Builder.header("Authorization", ...)`, không nhét token mutable chung vào client.
- **TLS trust/client certificate:** `sslContext` mang trust policy và local key material. Khác truststore, mTLS identity hoặc security boundary có thể cần **client riêng theo policy**, không chia sẻ một context tin quá rộng.
- **Proxy:** proxy configuration có thể thay đổi route và điều kiện reuse. Không khẳng định hai request đi qua hai proxy khác nhau sẽ tái sử dụng cùng TCP socket.
- **Default settings:** Java 17 ghi nhận một số system-wide defaults được lấy **khi xây client**; đổi `ProxySelector.setDefault(...)` hay `SSLContext.setDefault(...)` sau đó **không tự cập nhật client đã build**. Muốn đổi policy, tạo cấu hình/client mới theo quá trình rotation.

Tập trung vào “share tài nguyên” không đồng nghĩa “share credentials”. **Scope bảo mật luôn được ưu tiên** hơn số lượng instance tối thiểu.

## 16. Executor và lifecycle ở JDK 17: đừng áp nhầm tài liệu phiên bản mới

`HttpClient.Builder.executor(Executor)` cho phép chọn executor cho các asynchronous/dependent tasks của client theo API/provider; nếu không cung cấp, implementation có thể dùng executor mặc định không hiển thị trực tiếp qua `client.executor()`.

**Khi tự cung cấp executor:**

1. Thường cấp nó tại tầng service/application có ownership rõ; **không** tạo thread pool riêng bên trong mỗi request.
2. Không cho tasks nặng/blocking vô hạn chiếm hết executor khiến HTTP callbacks/handler không thể tiến triển.
3. Không `shutdownNow()` executor khi vẫn còn request/future cần chạy, kẻo cắt mất tiến trình xử lý.
4. Khi application shutdown, ngừng nhận request mới, chờ các outstanding exchanges theo deadline, đóng streaming bodies, sau đó giải phóng executor do application sở hữu.
5. Không suy luận size của custom executor là toàn bộ số connections hay toàn bộ số threads nội bộ của implementation; các cơ chế network I/O và protocol có thể có tài nguyên riêng.

**Ràng buộc phiên bản quan trọng:** `java.net.http.HttpClient` trong **Java 17** không triển khai `AutoCloseable` và **không có `close()` công khai**. Đoạn sau **không biên dịch được trên Java 17**:

```java
// SAI TRÊN JAVA 17 — HttpClient không phải AutoCloseable.
try (HttpClient client = HttpClient.newHttpClient()) {
    // ...
}
```

Tài liệu từ các JDK mới hơn có thể mô tả `HttpClient.close()/shutdown()`, nhưng **không áp API đó ngược vào bài Java 17**. Với Java 17, tạo client dùng lâu dài, hoàn tất các requests, đọc/đóng body streams và cleanup các resources tự quản lý. Nếu cần chính sách xả connection pool, hãy xem hạn chế/provider và kiến trúc ứng dụng; không giả vờ có một `client.close()` portable trên JDK 17.

## 17. Backpressure, giới hạn tài nguyên và rate limiting

Một shared client **không phải** bộ điều khiển traffic tự động. Ví dụ 500 threads cùng gọi `client.send` tới một downstream nhỏ, dù dùng chung instance vẫn có thể gây:

- Quá nhiều outstanding exchanges, connections hoặc HTTP/2 streams.
- Timeout hàng loạt, socket/buffer pressure và tăng memory.
- Nghẽn thread pool server và downstream, tạo hiệu ứng thác nước.
- Rate limit 429/503, retry storm và latency kéo dài.

Mỗi integration cần budget **concurrent requests**, **request per second**, **response size**, **timeout** và **retry**. Ví dụ minh họa:

```text
Shared HttpClient for Billing API
    |
    +-- queue bounded: nhận tối đa 100 request chờ
    +-- in-flight limit: 20 requests đang gửi
    +-- per-request timeout: theo SLA billing
    +-- retry budget: chỉ method/operation đủ điều kiện
    +-- circuit breaker / bulkhead: khi downstream lỗi
    +-- per-tenant authentication: không lẫn credentials
```

Đây là **con số chính sách giả định**, không phải mặc định Java hay khuyến nghị áp dụng máy móc.

Ví dụ `SharedHttpClientAsyncDemo` chọn cách dễ kiểm chứng: **4 outstanding requests theo batch**. Production có thể dùng bounded queue hoặc semaphore để lấp đầy slots linh hoạt hơn. Nếu queue hết chỗ, cần từ chối/đợi với deadline cụ thể; không kéo dài vô hạn chỉ vì client thread-safe.

## 18. Kết nối reuse quan sát bằng gì, và không nên suy từ đâu?

Trong hệ thống thật, quan sát một số chỉ số:

| Chỉ số | Cho biết | Không cho biết một mình |
| --- | --- | --- |
| `response.version()` | HTTP version thực tế của response | Không phải số TCP sockets đang mở |
| `client.version()` | Version được ưu tiên khi tạo client | Không bảo đảm server dùng version đó |
| Server access log với remote IP:port | Cùng remote TCP source port trong giai đoạn quan sát có thể gợi ý reuse trên cùng path | Proxy/NAT có thể đổi/che port; không chứng nhận mọi request luôn reuse |
| New TCP connects / TLS handshakes | Chi phí mở kết nối mới, session setup | Không đo logic application message hoàn tất |
| Connection counts/idle pools (metrics provider) | Mức độ tận dụng transport theo implementation | Không là API portable của `HttpClient` trên mọi JDK |
| p95/p99 latency + throughput | Hiệu năng nhìn từ workload | Không tách được mọi nguyên nhân nếu thiếu network trace |
| In-flight requests/queued bytes | Áp lực concurrency và backpressure | Không trực tiếp là socket count |

Một benchmark đúng nên so sánh **một shared client** với **client-per-request** trên cùng server/path, request count và warmup; đo connections/handshakes/latency/resources bằng công cụ phù hợp. Không kết luận chỉ từ một phép thử loopback rằng Internet sẽ luôn reuse hoặc nhanh hơn đúng một tỷ lệ cố định.

Ngược lại, đo thấy nhiều TCP connections **không nhất thiết là lỗi**: HTTP/1.1 requests đồng thời, server đóng idle connections hoặc load balancer thay route đều có thể khiến tạo connection mới hoàn toàn bình thường.

## 19. Tránh các lỗi phổ biến

1. **Tạo `HttpClient.newHttpClient()` mỗi request.** Giảm cơ hội dùng chung cấu hình và connection resources; tạo theo service.
2. **Dùng một global client cho mọi tenant bất chấp cookies/trust/credentials.** Tối ưu sai chỗ, có nguy cơ rò session. Chia scope theo security boundary.
3. **Nói “một HttpClient = một TCP socket”.** Không chính xác; connection management là việc của implementation và protocol.
4. **Dùng `client.version()` để khẳng định request chạy HTTP/2.** Chỉ là preference; kiểm tra `response.version()`.
5. **Tạo shared `HttpClient.Builder` rồi cho nhiều threads thay đổi.** Builder không thread-safe; chỉ share client sau build.
6. **Chia sẻ mutable `HttpRequest.Builder` giữa tasks.** Headers/URI dễ bị race; tạo builder riêng cho mỗi request.
7. **Dùng cùng một `InputStream` body publisher cho retry.** Stream có thể đã bị consume; xem tính repeatable.
8. **Không đọc/đóng `BodyHandlers.ofInputStream()` body.** Resource không giải phóng đúng; connection khó reuse.
9. **Đọc body vô hạn bằng `ofString()`.** Giữ nhiều byte trong heap; dùng stream có giới hạn để bảo vệ.
10. **Chỉ đặt `connectTimeout` và nghĩ đã có timeout toàn request.** Request timeout/deadline là lớp khác.
11. **Dùng `sendAsync` rồi tạo vô hạn futures.** Tăng in-flight/queue không có trần; có bounded concurrency.
12. **Gọi callback blocking nặng trên executor của client.** Có thể làm chậm toàn bộ exchange; tách compute executor.
13. **Retry mọi POST sau timeout mà không có idempotency key.** Có thể lặp side effect đã được server thực hiện.
14. **Dùng `client.close()` trong Java 17.** Không có API ấy; kiểm tra phiên bản tài liệu thật.
15. **Shutdown custom executor khi async calls đang chạy.** Có thể làm futures thất bại/stall; drain trước.
16. **Đổi SSLContext mặc định rồi nghĩ client đã xây sẽ tự đổi.** Java 17 capture một số defaults khi client được dựng.
17. **Ép `Connection: keep-alive` bằng tay để “bật pool”.** Không phải cách điều khiển pooling chuẩn của API; có thể bị hạn chế.
18. **Tự suy pool size từ số worker threads.** Threads, futures, connections và HTTP/2 streams là các loại tài nguyên khác nhau.
19. **Dùng client chung nhưng server gửi `Connection: close` rồi đổ lỗi cho JDK.** Không phải mọi response cho phép reuse.
20. **Không test server đóng idle socket/retry sau load balancer rotation.** Connection có thể mất giữa các requests; ứng dụng phải xử lý IOException/timeout phù hợp.

## 20. Câu hỏi tự kiểm tra

**Câu 1:** Có 40 thread gọi cùng một `HttpClient.send(...)`, có bắt buộc phải tạo 40 client không? **Không.** Một instance được xây xong có thể phục vụ nhiều requests. Phải bảo đảm state bên ngoài (builder, cookies, body handlers) an toàn và giới hạn tải.

**Câu 2:** Sau khi gửi 100 GET qua một `HttpClient`, có chắc chỉ mở một TCP connection không? **Không.** Đây là quyền quyết định của transport/provider và phụ thuộc HTTP version, server, proxy, load.

**Câu 3:** `connectTimeout(3s)` có giới hạn toàn bộ thời gian response về trong 3 giây không? **Không.** Nó áp dụng cho việc thiết lập connection mới; đặt request timeout riêng.

**Câu 4:** Muốn dùng `HttpClient` trong try-with-resources trên Java 17 được không? **Không.** Bản Java 17 không implements `AutoCloseable`.

**Câu 5:** `response.version() == HTTP_1_1` trong một request có nghĩa mọi request khác không thể HTTP/2? **Không.** Version thực tế phụ thuộc từng exchange và điều kiện đàm phán.

**Câu 6:** Dùng `BodyHandlers.ofInputStream()`, có được bỏ mặc stream không đọc/close rồi trông chờ pool reuse? **Không.** Phải đọc hết/close để giải phóng exchange; close sớm có thể khiến socket không reuse.

**Câu 7:** Ba mươi dịch vụ nội bộ có credential và cookie jar khác nhau có nên dùng một client singleton chung? **Không tự động.** Phải phân vùng theo policy và tenant; có thể tạo nhiều client hợp lý.

**Câu 8:** `sendAsync` trả về `CompletableFuture` nên không cần giới hạn outstanding requests? **Sai.** Futures và network resources vẫn tiêu tốn bộ nhớ/capacity, cần backpressure.

**Câu 9:** Có thể dùng `HttpRequest` immutable nhiều lần cho một POST với body input stream one-shot không? **Không được mặc định**; cần bảo đảm body publisher có thể tạo lại dữ liệu đúng khi resend, đặc biệt với retry.

**Câu 10:** Một lời gọi bị timeout, có chắc server chưa xử lý request không? **Không.** Cancellation có thể đến muộn; phương thức có side effect cần idempotency policy.

## 21. Checklist thiết kế reusable HttpClient và kết luận

Trước khi production, nên kiểm tra:

1. **Client được tạo ở tầng nào?** Tạo một instance đủ dài hạn cho mỗi service/integration/policy, tránh dựng mới mỗi operation.
2. **HttpClient.Builder có được dùng tuần tự rồi build một lần không?** Không dùng builder mutable đồng thời.
3. **Đã tách request state khỏi shared client chưa?** URI, headers, token, timeout, body publisher nằm trong request/call-specific state.
4. **Chia sẻ có đúng security boundary chưa?** Proxy, TLS trust, mTLS identity, cookie handler, authenticator, tenant isolation cần phù hợp.
5. **Có hiểu connection reuse là tối ưu có điều kiện?** Không giả định luôn cùng một TCP socket hoặc HTTP/2; kiểm tra response.version và metrics.
6. **Có consume/close response bodies đúng cách?** Đặc biệt `ofInputStream`/`ofLines` và body không giới hạn.
7. **Có timeout ở cả mức connect và request không?** Không để thread/future chờ vô hạn khi downstream lỗi.
8. **Có backpressure/bounded in-flight không?** Client reusable không tự giới hạn flood.
9. **Có retry theo HTTP semantics/idempotency không?** Tránh duplicate operation khi timeout.
10. **Có chính sách cho lifecycle/owned executor ở Java 17 không?** Không dùng API shutdown không tồn tại trên JDK 17; giải phóng resources do app sở hữu.
11. **Có quan sát real network reuse và latency không?** Metrics thực tế mới giúp quyết định scope và tuning.
12. **Có thử tải đa thread, server đóng idle connection, TLS renegotiation/rotation, proxy, malformed/oversized body và shutdown không?** Không chỉ test một GET đơn lẻ.

**Kết luận:** `HttpClient` đã `build` là **immutable, reuse được qua nhiều request và nhiều thread**. Tạo và chia sẻ instance theo **cùng một chính sách mạng/bảo mật**, dùng `HttpRequest` riêng theo từng operation, tiêu thụ/đóng response body đúng cách, đặt deadline và giới hạn in-flight. Việc này tạo điều kiện để implementation tận dụng connection pooling/HTTP/2 multiplexing, nhưng **không hứa một client luôn tương ứng đúng một socket**. Trong Java 17 không có `HttpClient.close()`, nên quản lý vòng đời ở service và những executor/body streams mà ứng dụng tự sở hữu.

### Tài liệu chính thức

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 17 — HttpRequest và HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html) và [BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java SE 17 — BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).