# Chia sẻ tài nguyên kết nối giữa nhiều yêu cầu với Java HTTP Client (Java 11+)

## Mục tiêu

Khi một ứng dụng liên tục gửi HTTP request đến API, điều quan trọng không chỉ là gọi `send()` hay `sendAsync()`, mà còn là **quản lý vòng đời `HttpClient` để có cơ hội tái sử dụng tài nguyên kết nối**. Tạo một `HttpClient` mới cho từng request thường làm tăng chi phí thiết lập kết nối, TLS và bộ nhớ, trong khi một client dùng chung có thể quản lý pool kết nối, executor và các cấu hình liên quan.

Từ Java 11, `java.net.http.HttpClient` là API chuẩn, hiện vẫn được hỗ trợ. Bài này tập trung trực tiếp vào cách **chia sẻ `HttpClient` giữa nhiều yêu cầu**, hiểu HTTP/1.1 và HTTP/2, dùng đồng bộ/không đồng bộ, giải phóng response body và chọn ranh giới chia sẻ an toàn.

Sau bài học, bạn sẽ biết:

- Phân biệt **một đối tượng `HttpClient`**, **một `HttpRequest`** và **một kết nối TCP/TLS thực tế**.
- Tái sử dụng một client bất biến cho nhiều request đồng bộ và bất đồng bộ.
- Hiểu **connection pooling** và **HTTP/2 multiplexing** là các khả năng, không phải lời hứa mọi request sẽ dùng cùng một socket.
- Tránh giữ response body streaming mở, tạo client mỗi lần hoặc chia sẻ trạng thái bảo mật sai phạm vi.
- Phân biệt cách quản lý vòng đời ở **Java 11** và API `close/shutdown` được bổ sung ở **Java 21+**.

## 1. Ba tầng dễ bị nhầm lẫn

### `HttpRequest` — mô tả **một** yêu cầu

`HttpRequest` chứa URL/URI, method, headers, timeout và request body publisher. Bạn có thể tạo request riêng cho mỗi lần gọi:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/items"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
```

Đây là **đoạn minh họa**; cần các import `java.net.URI`, `java.net.http.HttpRequest` và `java.time.Duration`. URI ví dụ không được gọi trong chương trình chạy ở phần sau.

Sau khi `build()`, request là đối tượng bất biến. **Request mới không có nghĩa phải tạo HTTP client mới**.

### `HttpClient` — cấu hình và tài nguyên dùng chung

`HttpClient` được tạo qua `HttpClient.newHttpClient()` hoặc `HttpClient.newBuilder().build()`. Khi đã xây dựng, đối tượng client **bất biến về cấu hình** và có thể dùng để gửi nhiều request:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

Nó có thể quản lý pool kết nối, thiết lập TLS, HTTP version preference, proxy, authenticator, cookie handler và executor theo cấu hình. Theo tài liệu JDK, **một client thường có pool kết nối riêng**, các pool giữa **các client khác nhau thường không được chia sẻ**. Không có API chuẩn để ép hai đối tượng `HttpClient` độc lập dùng chung một TCP connection.

### Connection — kết nối thực bên dưới

Một HTTP client có thể có **không, một hoặc nhiều** kết nối TCP/TLS tại những thời điểm khác nhau. Server, proxy, thời gian idle, protocol, lỗi mạng và số request đồng thời đều có thể khiến nó mở hoặc đóng kết nối.

**Không có quan hệ 1–1 cố định** giữa client và connection:

```text
Một HttpClient dùng chung
  ├── HttpRequest A ──┐
  ├── HttpRequest B ──┼── Pool / connection management
  ├── HttpRequest C ──┤      ├── TCP/TLS connection 1
  └── HttpRequest D ──┘      └── TCP/TLS connection 2 (nếu cần)
```

Sơ đồ chỉ minh họa kiến trúc. Từng request có dùng lại kết nối nào là quyết định của implementation và điều kiện thực tế, không nên suy ra chỉ từ sơ đồ hoặc việc giữ cùng một biến `client`.

## 2. Quy tắc thiết kế: tạo client theo vòng đời ứng dụng/nhóm cấu hình

**Sai về mặt thiết kế tài nguyên** khi một request luôn kéo theo việc tạo một client mới:

```java
// Minh họa anti-pattern, không phải chương trình độc lập.
HttpResponse<String> fetch(URI uri) throws Exception {
    HttpClient client = HttpClient.newHttpClient();
    HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
    return client.send(request, HttpResponse.BodyHandlers.ofString());
}
```

Nếu hàm được gọi hàng nghìn lần, ứng dụng có thể tạo hàng nghìn client với các pool và tài nguyên riêng. Việc JVM thu hồi object không đồng nghĩa mọi kết nối được tái sử dụng giữa các client.

**Nên tạo client một lần cho mỗi nhóm cấu hình/chính sách phù hợp**, rồi gửi nhiều request qua client đó:

```java
// Minh họa cấu trúc service; cần import tương ứng.
final class ApiGateway {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    HttpResponse<String> get(URI uri)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString());
    }
}
```

Đoạn này **không phải tệp độc lập**; sử dụng `java.net.http.HttpClient`/`HttpRequest`/`HttpResponse`, `java.net.URI`, `java.time.Duration` và `java.io.IOException`. Một instance `ApiGateway` có thể là thành phần sống cùng một service. `HttpClient` và `HttpRequest` đã build đều bất biến, phù hợp dùng từ nhiều luồng theo hợp đồng API; **không dùng một `HttpRequest.Builder` có thể thay đổi chung giữa các thread**.

### Trường hợp nên dùng nhiều client

Chia sẻ không phải lúc nào cũng có nghĩa “chỉ duy nhất một client cho toàn bộ hệ thống”. Có thể cần client khác nhau khi:

- Các nhóm request dùng **proxy** hoặc cấu hình TLS/trust khác nhau.
- Các tenant phải được **cách ly cookie, chứng thực hoặc chính sách mạng**.
- Một nhóm cần executor, redirect policy hay cấu hình client khác nhóm còn lại.
- Vòng đời các thành phần không giống nhau, chẳng hạn một connector được dừng độc lập.

Chọn ranh giới theo **cấu hình và cách ly**, không tạo client mới chỉ vì URI hoặc header khác nhau. Đừng chia sẻ `CookieManager` hoặc credential-bearing `Authenticator` giữa các tenant không được phép nhìn thấy trạng thái của nhau.

## 3. Chạy thử hoàn chỉnh không cần Internet: một client, ba request

Chương trình dưới đây dựng máy chủ HTTP **loopback** trên `127.0.0.1` với cổng ngẫu nhiên (0). Nó gửi một request đồng bộ và hai request bất đồng bộ **qua đúng một biến `HttpClient client`**. Server do chương trình tự tạo, nên không phụ thuộc API bên ngoài, DNS công cộng hoặc secret.

**Tệp: `SharedHttpClientDemo.java`** — tương thích Java 11+

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class SharedHttpClientDemo {
    private static HttpRequest request(int port, String path) {
        URI uri = URI.create("http://127.0.0.1:" + port + "/" + path);
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            String path = exchange.getRequestURI().getPath().substring(1);
            byte[] body = ("reply:" + path)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();

        try {
            int port = server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            HttpResponse<String> one = client.send(
                    request(port, "one"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            CompletableFuture<HttpResponse<String>> two =
                    client.sendAsync(
                            request(port, "two"),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            CompletableFuture<HttpResponse<String>> three =
                    client.sendAsync(
                            request(port, "three"),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));

            CompletableFuture.allOf(two, three).join();

            System.out.println("sync=" + one.statusCode()
                    + " " + one.body());
            System.out.println("async2=" + two.join().statusCode()
                    + " " + two.join().body());
            System.out.println("async3=" + three.join().statusCode()
                    + " " + three.join().body());
        } finally {
            server.stop(0);
        }
    }
}
```

Lưu tệp dưới tên `SharedHttpClientDemo.java`, rồi chạy bằng JDK 11 trở lên:

```bash
javac -encoding UTF-8 SharedHttpClientDemo.java
java SharedHttpClientDemo
```

Để kiểm tra tương thích API Java 11 trên JDK mới hơn có hỗ trợ target 11:

```bash
javac --release 11 -encoding UTF-8 SharedHttpClientDemo.java
java SharedHttpClientDemo
```

**Stdout chính xác đã được kiểm tra thực tế:**

```text
sync=200 reply:one
async2=200 reply:two
async3=200 reply:three
```

Ở đây `HttpServer` thuộc module JDK `jdk.httpserver` (API HTTP server nhỏ phục vụ minh họa), **không phải thư viện ngoài**. Trong môi trường module hạn chế, có thể cần bảo đảm module `jdk.httpserver` sẵn có khi biên dịch/chạy. Các lệnh ở trên đã được kiểm tra trên một bản JDK có module đó.

### Ví dụ chứng minh điều gì?

- **Chứng minh một instance `HttpClient`** có thể gửi nhiều yêu cầu, gồm `send` và `sendAsync`, với mỗi request riêng.
- **Chứng minh cùng client dùng được cho các yêu cầu bất đồng bộ đang chạy đồng thời**; hai `CompletableFuture` được tạo trước khi gọi `allOf(...).join()`.
- **Không tự chứng minh ba yêu cầu đã dùng đúng một TCP socket.** Tái sử dụng connection là khả năng của client/pool, không phải một hợp đồng cho từng request. Server hoặc client có thể mở kết nối khác nếu điều kiện yêu cầu.
- Việc chọn `HTTP_1_1` chỉ nhằm làm rõ demo với server nội bộ. Với một server phù hợp, client có thể hỗ trợ HTTP/2 theo cấu hình/thương lượng.
- Hai request async có thể hoàn thành theo thứ tự khác nhau; chương trình **in kết quả sau khi cả hai hoàn thành**, theo thứ tự `two`, rồi `three`, nên stdout ổn định.

### Vòng đời tài nguyên trong demo

`server.stop(0)` nằm trong `finally` để dừng server kể cả khi một request thất bại. Từ Java 11, `HttpClient` chưa có API `close()` công khai như Java 21+, vì vậy ví dụ không gọi `client.close()`. Các response ở đây dùng `BodyHandlers.ofString(...)`, nhận body đầy đủ chứ không để một stream đọc dở. Trong ứng dụng dài hạn, client thường sống cùng component/service để hưởng lợi từ việc dùng chung tài nguyên.

## 4. HTTP/1.1 keep-alive và HTTP/2 multiplexing khác nhau

### HTTP/1.1

Trong HTTP/1.1, một connection có thể được **giữ sống** để gửi các request tiếp theo, nếu server/proxy và client cho phép. Việc giữ connection có thể tránh một số chi phí thiết lập TCP/TLS cho lần gọi kế tiếp. Nhưng:

- Connection có thể hết thời gian idle, server gửi `Connection: close` hoặc xảy ra lỗi mạng.
- Nhiều request đồng thời có thể cần **nhiều connection** để tránh chờ tuần tự.
- Không có bảo đảm request thứ hai sẽ dùng cùng socket với request thứ nhất, ngay cả khi cả hai dùng cùng client.

Vì vậy tối ưu cần làm là **tái sử dụng client**, chứ không cố giữ một socket duy nhất cho mọi request.

### HTTP/2

HTTP/2 cho phép **nhiều stream HTTP được ghép kênh trên một connection** (*multiplexing*). Nếu client và server thực sự thương lượng HTTP/2, nhiều request có thể đang thực thi đồng thời qua một connection, giảm nhu cầu mở connection riêng cho từng request.

Cấu hình ưu tiên:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Đây là **đoạn minh họa**, không tự gửi request. `HTTP_2` thể hiện **phiên bản ưu tiên**, không ép mọi đích phải hỗ trợ HTTP/2. Client có thể chọn HTTP/1.1 khi thương lượng hoặc điều kiện mạng yêu cầu. Xem **phiên bản thực tế của response** qua `response.version()`; tuy nhiên thông tin protocol vẫn không chứng minh chính xác request đã dùng lại socket nào.

### Bảng so sánh

| Yếu tố | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Tái dùng kết nối | Có thể giữ keep-alive cho request kế tiếp | Có thể giữ kết nối và ghép nhiều stream |
| Đồng thời nhiều request | Client có thể dùng nhiều kết nối | Có thể multiplex qua một kết nối |
| Rủi ro áp dụng sai | Nhầm client với socket cố định | Nhầm “ưu tiên HTTP/2” với “mọi request chắc chắn dùng HTTP/2” |
| Quy tắc trong Java | Chia sẻ một `HttpClient` thích hợp | Cũng chia sẻ một `HttpClient` thích hợp |

Connection pooling và HTTP/2 multiplexing **có thể bổ trợ cho nhau**, nhưng không phải hai cách viết thay thế cho việc chọn vòng đời client.

## 5. Gửi đồng bộ và bất đồng bộ trên cùng client

### Đồng bộ: `send(...)`

```java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
```

Đây là câu lệnh minh họa với `client` và `request` đã tạo. `send` chặn luồng gọi đến khi response được xử lý theo `BodyHandler`, hoặc xảy ra exception. Dùng khi luồng đang chờ là chấp nhận được; không nên lạm dụng trong luồng UI/event loop cần phản hồi nhanh.

### Bất đồng bộ: `sendAsync(...)`

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());

future.thenAccept(response ->
        System.out.println(response.statusCode()));
```

Đây là đoạn minh họa, không phải chương trình độc lập. `sendAsync` trả ngay `CompletableFuture`; request và network I/O được xử lý bất đồng bộ. Client dùng chung có thể điều phối nhiều yêu cầu, song **số request phát đồng thời không tự động bị giới hạn chỉ vì bạn dùng pool connection**.

Nếu khởi tạo hàng chục nghìn future không giới hạn, ứng dụng vẫn có thể quá tải bộ nhớ, socket hoặc server. Cần áp dụng **giới hạn đồng thời** theo tải thực tế, backpressure hoặc một queue có số công việc tối đa; xử lý timeout, lỗi và cancellation ở ranh giới hợp lý.

**Lưu ý về lỗi:** `send` khai báo `IOException` và `InterruptedException`. Với async, lỗi được đưa vào future hoàn thành bất thường; khi gọi `join()`, lỗi thường được bọc trong `CompletionException`. Đừng chỉ xử lý HTTP status 200/500 mà bỏ qua lỗi kết nối, timeout, DNS, TLS và interruption.

## 6. Response body có thể quyết định khả năng giải phóng kết nối

Một client có pool không đảm bảo tái sử dụng tài nguyên hiệu quả nếu ứng dụng **không kết thúc việc tiêu thụ response**.

| BodyHandler | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | Đọc và giải mã response thành một `String` | Response nhỏ/vừa, cần text |
| `BodyHandlers.ofByteArray()` | Giữ toàn bộ bytes trong bộ nhớ | Nội dung nhỏ cần byte array |
| `BodyHandlers.discarding()` | Tiêu thụ và bỏ body | Chỉ quan tâm status/headers |
| `BodyHandlers.ofFile(path)` | Ghi body vào file | Nội dung lớn cần lưu xuống đĩa |
| `BodyHandlers.ofInputStream()` | Trả body kiểu `InputStream` để đọc dần | Streaming có kiểm soát |

Ví dụ khi chỉ cần biết status:

```java
HttpResponse<Void> result =
        client.send(request, HttpResponse.BodyHandlers.discarding());
System.out.println(result.statusCode());
```

Đây là đoạn minh họa sử dụng biến `client`/`request` đã có. `discarding()` vẫn **tiêu thụ body**, chứ không phải đơn giản bỏ qua việc đọc dữ liệu mạng. Điều này khác việc dùng `ofInputStream()` rồi quên đóng stream.

### Với `ofInputStream()` phải đóng hoặc đọc đủ

```java
HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    body.transferTo(OutputStream.nullOutputStream());
}
```

Đây là đoạn minh họa cần các import `java.io.InputStream`, `java.io.OutputStream`, `java.net.http.HttpResponse` và xử lý `IOException`/`InterruptedException`. `transferTo` và `nullOutputStream` đều phù hợp Java 11.

Các streaming body handler có thể hoàn thành phần header trước khi ứng dụng thực sự đọc hết dữ liệu. **Hãy đọc hết, đóng hoặc hủy luồng/subscription khi thích hợp**. Nếu không, exchange có thể vẫn chưa hoàn tất, ảnh hưởng đến giải phóng connection và việc đóng client. Đọc hết body có thể giúp một kết nối tiếp tục đủ điều kiện để tái sử dụng; **đóng sớm không bảo đảm socket được giữ lại** — có thể khiến transport phải đóng kết nối đang dùng.

Với tải xuống lớn, ưu tiên `ofFile` hoặc xử lý theo luồng thay vì `ofString`/`ofByteArray` để tránh giữ toàn bộ payload trong heap. Với custom `BodySubscriber`, bảo đảm nó tiêu thụ, hoàn tất hoặc cancel theo giao thức `Flow`.

## 7. Các timeout: kết nối mới khác với toàn bộ request

Có hai cấu hình thường bị lẫn:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
```

Đây là đoạn minh họa, với `URI uri` và import phù hợp.

- `connectTimeout`: giới hạn thời gian **thiết lập kết nối mới**. Nếu một connection sẵn có được dùng lại thì không cần thiết lập kết nối TCP mới cho request đó, nên không hiểu đây là thời gian tối đa cho cả request.
- `HttpRequest.Builder.timeout`: thời gian chờ **response** của request theo hợp đồng API. Nó không có nghĩa bất kỳ bước xử lý streaming do người gọi tiếp tục thực hiện đều được đảm bảo hoàn tất trước hạn đó.
- Cả hai phải là giá trị hợp lệ; không dùng `Duration.ZERO` hoặc thời gian âm làm cách “tắt timeout” tùy tiện.
- Timeouts không thay thế giới hạn concurrency, retry policy hoặc deadline end-to-end cho workflow nhiều bước.

### Retry và tính an toàn của HTTP method

Một request lỗi không nhất thiết có nghĩa server chưa xử lý nó. Khi retry, đặc biệt với `POST`/cập nhật dữ liệu, phải xem xét **idempotency**, duplicate side effects, request body có thể phát lại được hay không, backoff và giới hạn số lần retry. Reuse client không tự đảm bảo retry an toàn hoặc tự biến một request lỗi thành thành công.

## 8. Tài nguyên client dùng chung gồm những gì?

Khi tạo `HttpClient` từ builder, nhiều thiết lập là **ở cấp client**:

- `version(...)`: phiên bản HTTP **ưu tiên**, thực tế có thể khác.
- `connectTimeout(...)`: timeout của thao tác connect mới.
- `followRedirects(...)`: chính sách theo redirect.
- `proxy(...)`: cách chọn proxy.
- `authenticator(...)`: authenticator có thể tham gia challenge/credential handling.
- `cookieHandler(...)`: cookie store/chính sách nếu được cung cấp.
- `sslContext(...)`, `sslParameters(...)`: cấu hình TLS trong những trường hợp cần thiết.
- `executor(...)`: executor sử dụng cho những công việc bất đồng bộ liên quan, khi được cấu hình.

Không cần bật tất cả; **mặc định an toàn, nhất quán và chỉ cấu hình thứ cần thiết** thường tốt hơn.

### Một client dùng chung không có nghĩa mọi dữ liệu xác thực phải dùng chung

Có thể gửi request với headers khác nhau trên cùng một client vì `HttpRequest` là đối tượng riêng. Nhưng nếu dùng `CookieHandler`/`Authenticator` có trạng thái, việc chia sẻ client **cũng chia sẻ phạm vi cấu hình và trạng thái được gắn vào nó**. Với các tenant hoặc user không được phép chia sẻ session, hãy phân tách client/cookie store theo ranh giới cách ly, hoặc thiết kế tầng xác thực bảo đảm không rò cookie/token.

Ví dụ, `CookieManager` không tự động được gắn cho mọi client: chỉ khi ứng dụng cấu hình `cookieHandler(cookieManager)` thì client mới dùng cơ chế đó. Không mặc định “HTTP client dùng chung luôn tự chia sẻ cookie giữa mọi request”.

### Executor do ứng dụng tự cung cấp

Nếu cấp một `Executor`/`ExecutorService` riêng cho builder, **vòng đời executor là trách nhiệm của ứng dụng**. Đừng tắt executor khi các request async vẫn chạy; cũng đừng tạo executor riêng cho từng request chỉ để rồi không đóng.

Trong Java 11, nếu không truyền executor, implementation có thể dùng executor mặc định của nó. Không suy ra thread count hay chiến lược scheduling chính xác nếu không kiểm chứng với JDK/provider thực tế.

## 9. Quản lý vòng đời đúng phiên bản JDK

Đây là điểm quan trọng để tài liệu không áp đặt API mới lên dự án còn chạy Java 11.

### Java 11 đến Java 20: giữ client tái sử dụng, không gọi `client.close()`

`HttpClient` được đưa vào API chuẩn từ Java 11 và **chưa có** các phương thức `close()`/`shutdown()` của Java 21. Vì vậy, đoạn sau **không biên dịch khi target `--release 11`**:

```java
// Chỉ dùng Java 21+, không chạy/biên dịch với --release 11.
try (HttpClient client = HttpClient.newHttpClient()) {
    // Sử dụng client trong phạm vi này.
}
```

Trong Java 11, nguyên tắc thường dùng là giữ một `HttpClient` sống theo component hoặc service, hoàn tất/cancel các exchange và streaming response đúng cách, rồi để implementation/JVM quản lý tài nguyên khi client không còn được sử dụng. **Không tạo client mới mỗi request** để “tự đóng cho tiện”, và không cho rằng việc mất reference sẽ lập tức đóng mọi socket.

### Java 21 trở lên: `HttpClient` có API shutdown/close

Từ **Java 21**, `HttpClient` triển khai `AutoCloseable` và có `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(...)`, `isTerminated()`. Các API này vẫn có trong Java hiện đại.

- `close()` khởi động quá trình đóng có trật tự và **đợi các tác vụ đang chạy hoàn tất** theo hợp đồng, có thể kéo dài nếu response streaming bị bỏ dở.
- `shutdown()` yêu cầu ngừng nhận request mới nhưng **không chờ**; có thể phối hợp `awaitTermination(...)` khi cần.
- `shutdownNow()` cố gắng dừng nhanh, có thể làm gián đoạn yêu cầu đang chạy; không có bảo đảm mọi exchange biến mất tức thì.

**Quan trọng:** không gọi `close()` sau **mỗi** request trên một client được thiết kế để chia sẻ lâu dài — làm vậy sẽ phá vòng đời dùng chung. Hãy đóng tại thời điểm service/component kết thúc, khi chắc chắn không còn request mới cần sử dụng client đó. Đây không phải lý do để tránh reuse; nó là phần bổ sung cho quản lý vòng đời tốt hơn.

## 10. Giới hạn của connection reuse và cách đánh giá đúng

Ngay cả khi dùng client chung, các yếu tố sau có thể tạo connection mới:

- Server đóng connection sau mỗi response, đặt timeout keep-alive ngắn hoặc giới hạn số request/connection.
- Đích khác host/port/protocol, proxy khác hoặc không đủ điều kiện chia sẻ connection.
- Kết nối đang bận và implementation mở kết nối khác để phục vụ đồng thời.
- TLS, lỗi mạng, load balancer, DNS, redirect, proxy và thay đổi hạ tầng.
- Response body chưa kết thúc, connection bị hủy hoặc connection không còn đủ điều kiện dùng tiếp.

Không có lời bảo đảm “mọi request dùng cùng TCP socket”, “chỉ cần một client là không bao giờ handshake nữa” hay “HTTP/2 chắc chắn nhanh hơn HTTP/1.1 trong mọi môi trường”.

### Bạn có thể đo những gì?

- **Tỷ lệ thành công**, status code, lỗi network, timeout theo đích.
- **Latency** theo percentile và số lượng request đồng thời.
- **Số socket/connection thực tế** theo công cụ giám sát của hệ điều hành, server/proxy hoặc telemetry triển khai, thay vì suy luận từ object count.
- **HTTP version đã thương lượng** qua `response.version()`; không nhầm nó với số socket.
- **Bộ nhớ và số thread** nếu dùng async nhiều, body lớn hoặc executor tùy chỉnh.

So sánh trên tải đại diện trước/sau khi chuyển từ “new client per request” sang một client dùng chung. Chênh lệch đo được phụ thuộc server, mạng, TLS, concurrency và loại response; không bịa ra một tỷ lệ tăng tốc cố định.

## 11. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Tạo `HttpClient.newHttpClient()` cho từng request | Mỗi client thường có pool riêng, giảm cơ hội reuse | Giữ một client theo phạm vi component/cấu hình |
| Cho rằng một client = một TCP socket | Một client có thể tạo nhiều connection | Xem pool là cơ chế quản lý, không ép 1:1 |
| Bắt buộc HTTP/2 trên builder rồi tin mọi response là HTTP/2 | Server/proxy có thể đàm phán HTTP/1.1 | Kiểm tra `response.version()`, không cam kết trước |
| Đóng client dùng chung sau mỗi request trên Java 21+ | Request tiếp theo không thể dùng client đã shutdown | Đóng một lần tại cuối vòng đời component |
| Gọi `client.close()` trong mã target Java 11 | API không tồn tại ở Java 11 | Tách hướng dẫn theo JDK; reuse client và quản lý body/exchange đúng |
| Quên đọc/đóng stream từ `ofInputStream()` | Exchange có thể không hoàn tất và giữ tài nguyên | Dùng `try-with-resources`, đọc hết/đóng/hủy hợp lý |
| Thu gom response rất lớn vào `ofString()` | Bộ nhớ tăng theo toàn bộ body | Dùng `ofFile()` hoặc streaming |
| Phát quá nhiều `sendAsync()` không giới hạn | Future, socket, CPU và server có thể quá tải | Áp dụng concurrency limit, backpressure, timeout |
| Nhầm `connectTimeout` là timeout toàn bộ request | Request có thể chờ lâu sau khi connect xong | Đặt thêm request timeout và deadline nghiệp vụ |
| Dùng chung cookie/credential giữa tenant cách ly | Nguy cơ rò session/xác thực | Tách cookie store/client theo ranh giới bảo mật |
| Retry `POST` vô điều kiện khi timeout | Có thể tạo giao dịch trùng | Kiểm tra idempotency, retry policy và server contract |
| Xem stdout của demo là bằng chứng tái dùng cùng socket | Demo chỉ chứng minh cùng một object client | Đo kết nối thực ở tầng transport/server |
| Tạo custom executor rồi không quản lý vòng đời | Rò thread hoặc tắt sớm khi request còn chạy | Quản lý executor cùng vòng đời service |

## 12. Bài tập thực hành

**Bài 1 — Phân biệt request/client.** Sửa ví dụ chính để gửi 10 request với các path khác nhau, nhưng chỉ gọi `HttpClient.newBuilder().build()` **một lần**. Dự đoán object nào thay đổi mỗi request: `HttpRequest` mới, còn `HttpClient` dùng chung.

**Bài 2 — Đồng thời.** Thêm 5 lời gọi `sendAsync()` và dùng `CompletableFuture.allOf(...)` để đợi. Xác nhận không phụ thuộc thứ tự hoàn thành để ghép kết quả. Thử sử dụng giới hạn đồng thời nhỏ trước khi tăng tải.

**Bài 3 — Kiểm tra HTTP version.** In `response.version()` khi dùng server `HttpServer` trong ví dụ. Vì demo đặt `HTTP_1_1`, kết quả phản ánh HTTP/1.1. Sau đó thử trên một HTTPS endpoint do bạn kiểm soát có hỗ trợ HTTP/2 và phân biệt **ưu tiên phiên bản** với **phiên bản thực tế**. Không suy luận socket reuse chỉ từ phiên bản.

**Bài 4 — Response streaming.** Viết request dùng `BodyHandlers.ofInputStream()`, đọc bằng `try-with-resources` và so sánh với `BodyHandlers.discarding()` khi chỉ cần status. Giải thích vì sao body phải được xử lý đến trạng thái hoàn tất/hủy.

**Bài 5 — Phiên bản JDK.** Giải thích vì sao `try (HttpClient client = HttpClient.newHttpClient()) {...}` không biên dịch với `--release 11`, nhưng hợp lệ khi biên dịch bằng JDK 21+. Hãy giữ code chạy được trên JDK tối thiểu của dự án.

**Bài 6 — Thiết kế nhiều tenant.** Một service gọi API cho hai khách hàng có cookie khác nhau. Bạn chọn một hay hai client? Có thể dùng chung client nếu thiết kế không có trạng thái chứng thực rò rỉ, nhưng khi cookie manager/authenticator là trạng thái chia sẻ thì cần ranh giới cách ly rõ ràng; cân nhắc client riêng hoặc cơ chế độc lập tương đương.

### Checklist trước khi đưa vào production

1. Client được tạo theo vòng đời **service/configuration**, không phải mỗi request?
2. Kết nối có thể được tái dùng nhưng code **không phụ thuộc** vào việc mọi request cùng socket?
3. Chọn `connectTimeout` và timeout của request theo yêu cầu?
4. Response body được đọc xong, ghi file, tiêu thụ/bỏ qua hoặc đóng/cancel phù hợp?
5. Có giới hạn số request đồng thời, retry/backoff và xử lý lỗi async?
6. Cookie, credential, proxy, TLS và executor có phạm vi chia sẻ an toàn?
7. Có kế hoạch đóng client theo **phiên bản JDK thực tế** và đóng executor riêng nếu cấp từ ngoài?
8. Có telemetry về latency, failure rate, connection/HTTP version để đánh giá thay vì khẳng định reuse mơ hồ?

## Tài liệu chính thức

- [Oracle Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): client bất biến, chia sẻ tài nguyên qua nhiều request và các API `send`/`sendAsync`.
- [Oracle Java SE 25 — HttpClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): connection pools theo client, streaming body, callback, đóng client và các API hiện đại.
- [Oracle Java SE 25 — HttpRequest](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.html): request bất biến, cấu hình timeout và headers.
- [Oracle Java SE 25 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): cách tiêu thụ response theo `ofString`, `ofFile`, `ofInputStream` và `discarding`.
- [Oracle Java SE 21 — HttpClient.close](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html#close()): vòng đời client theo `AutoCloseable` từ Java 21.
- [OpenJDK JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321): đưa HTTP Client vào tiêu chuẩn Java 11.

**Thông điệp quan trọng:** **dùng lại một `HttpClient` cho nhiều HTTP request cùng phạm vi cấu hình/bảo mật** để implementation có cơ hội quản lý và tái sử dụng kết nối. Nhưng việc từng request có dùng cùng socket hay không là đặc điểm transport/runtime, không phải điều ứng dụng được phép giả định.