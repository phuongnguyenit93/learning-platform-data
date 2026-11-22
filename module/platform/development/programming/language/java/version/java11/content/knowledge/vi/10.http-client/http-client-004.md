# Tính bất biến và tái sử dụng HttpClient (Java 11+)

**Chủ đề: HTTP Client.** Từ Java 11, `java.net.http.HttpClient` là API chuẩn để gửi HTTP request đồng bộ hoặc bất đồng bộ. Điểm quan trọng khi thiết kế ứng dụng lâu dài: **tạo và cấu hình client một lần cho nhóm tác vụ có cùng chính sách, sau đó tái sử dụng client để gửi nhiều request**. Một `HttpClient` đã được xây dựng là **bất biến về cấu hình** (*immutable*) nhưng vẫn quản lý kết nối, tác vụ và tài nguyên chạy nền.

Bài này giải thích bất biến nghĩa là gì, sự khác nhau giữa `HttpClient.Builder` và `HttpClient`, lợi ích và giới hạn của tái sử dụng kết nối, cách chia sẻ client giữa nhiều tác vụ, cấu hình theo từng request, vòng đời trong Java 11 so với Java 21+, cùng ví dụ có thể chạy với JDK 11 trở lên. Các kiến thức được trình bày ở đây vẫn áp dụng trong Java hiện đại.

## 1. Mô hình ba thành phần: client, request và response

Luồng cơ bản:

```text
HttpClient.Builder --build()--> HttpClient (cấu hình cố định)
                                     |
                    +----------------+----------------+
                    |                                 |
                HttpRequest A                     HttpRequest B
                    |                                 |
               client.send(...)                 client.sendAsync(...)
                    |                                 |
               HttpResponse A                  CompletableFuture
                                                      |
                                                 HttpResponse B
```

- **`HttpClient`:** sở hữu cấu hình liên quan đến nhiều request: chính sách redirect, proxy, SSL/TLS, `Authenticator`, `CookieHandler`, executor và phiên bản HTTP ưu tiên. Một client có thể gửi nhiều request.
- **`HttpRequest`:** mô tả *một yêu cầu* (URI, method, headers, body publisher, timeout và một số tùy chọn). Request đã `build()` cũng bất biến về cấu hình và có thể được gửi nhiều lần, với điều kiện body publisher và ý nghĩa nghiệp vụ cho phép.
- **`HttpResponse<T>`:** kết quả *của một lần gửi*: status, headers, body và metadata tương ứng. Mỗi lần gửi có response của riêng nó; đừng nhầm việc dùng lại client với việc dùng lại response.

Một ví dụ ngắn (đoạn minh họa trong phương thức có thể xử lý `IOException` và `InterruptedException`):

```java
HttpClient client = HttpClient.newHttpClient();

HttpRequest first = HttpRequest.newBuilder(
        URI.create("https://example.org/first")).GET().build();
HttpRequest second = HttpRequest.newBuilder(
        URI.create("https://example.org/second")).GET().build();

HttpResponse<String> a = client.send(
        first, HttpResponse.BodyHandlers.ofString());
HttpResponse<String> b = client.send(
        second, HttpResponse.BodyHandlers.ofString());
```

Cần import các lớp trong `java.net.http` và `java.net.URI`. Hai lệnh gọi `send` dùng **cùng một** `client`. Đoạn này chỉ minh họa cấu trúc API, không phải bài test cần truy cập Internet; các ví dụ chạy độc lập phía dưới dùng máy chủ HTTP nội bộ.

## 2. Bất biến sau build: phân biệt với Builder thay đổi được

Javadoc Java 11 nêu rõ: khi đã tạo bằng `build()`, `HttpClient` là *immutable* và có thể gửi nhiều request. Bất biến ở đây chủ yếu có nghĩa là **cấu hình được thiết lập lúc tạo không bị thay đổi bằng setter của client**.

`HttpClient.Builder` thì khác:

- `HttpClient.newBuilder()` trả về một builder có thể thay đổi.
- Các lời gọi như `connectTimeout(...)`, `followRedirects(...)`, `version(...)` chỉnh trạng thái builder và trả về chính builder.
- `build()` tạo một đối tượng `HttpClient` mới từ cấu hình hiện tại.
- Thay đổi builder **sau khi tạo client A** không đổi lại cấu hình đã chốt của A; gọi `build()` tiếp tạo client B mới.
- **Builder không thread-safe** theo hợp đồng API: không dùng chung một builder từ nhiều thread để gọi setter hay build nếu không đồng bộ bên ngoài.

### Ví dụ chạy độc lập: `ImmutableClientConfigDemo.java`

Ví dụ này không phát sinh kết nối mạng.

```java
import java.net.http.HttpClient;
import java.time.Duration;

public class ImmutableClientConfigDemo {
    public static void main(String[] args) {
        HttpClient.Builder builder = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1);

        HttpClient first = builder.build();

        builder.connectTimeout(Duration.ofSeconds(8))
                .followRedirects(HttpClient.Redirect.NORMAL);

        HttpClient second = builder.build();

        System.out.println("first timeout: "
                + first.connectTimeout().orElseThrow().toSeconds());
        System.out.println("second timeout: "
                + second.connectTimeout().orElseThrow().toSeconds());
        System.out.println("first redirects: " + first.followRedirects());
        System.out.println("second redirects: " + second.followRedirects());
        System.out.println("same object: " + (first == second));
    }
}
```

Biên dịch và chạy bằng JDK 11 hoặc mới hơn:

```bash
javac --release 11 -encoding UTF-8 ImmutableClientConfigDemo.java
java ImmutableClientConfigDemo
```

Stdout:

```text
first timeout: 3
second timeout: 8
first redirects: NEVER
second redirects: NORMAL
same object: false
```

`first` vẫn giữ timeout 3 giây và redirect policy `NEVER` dù builder được đổi sau đó. `second` là client khác, có timeout 8 giây và policy `NORMAL`. Việc cùng dùng một builder **không** làm hai client trở thành cùng một đối tượng hoặc dùng chung mọi tài nguyên nội bộ.

**Phân biệt bất biến cấu hình với bất biến trạng thái chạy:** client vẫn có thể mở/đóng kết nối, cập nhật pool nội bộ, gửi request mới và hoàn tất tác vụ bất đồng bộ. Các đối tượng được đưa vào cấu hình như `CookieHandler`, `Authenticator` hoặc `Executor` cũng có thể chứa trạng thái riêng. “Client immutable” không có nghĩa mọi đối tượng liên quan đều immutable.

## 3. Vì sao nên tái sử dụng HttpClient?

Một client cung cấp cấu hình dùng chung và khả năng chia sẻ tài nguyên cho các request mà nó gửi. Trong triển khai JDK, các client thường quản lý **pool kết nối của riêng mình**; việc tạo client mới cho mỗi request có thể làm mất cơ hội tái sử dụng kết nối.

**Lợi ích có thể có:**

1. **Giảm chi phí thiết lập lại kết nối**: với HTTP/1.1, một kết nối đủ điều kiện có thể được giữ lại để phục vụ request sau; kết nối HTTPS mới còn có thể tốn thêm quá trình bắt tay TLS.
2. **Hỗ trợ trao đổi song song hiệu quả hơn**: với HTTP/2 được thương lượng thành công, nhiều request/response có thể được ghép kênh trên kết nối phù hợp.
3. **Dùng chung chính sách**: các request cùng đích dịch vụ có thể chia sẻ proxy, SSL context, redirect policy, authenticator, cookie handler và executor được cấu hình nhất quán.
4. **Giảm việc tạo những đối tượng và tài nguyên chạy nền lặp lại**: đặc biệt khi dịch vụ gửi rất nhiều request.

Tuy nhiên, **tái sử dụng `HttpClient` không bảo đảm tái sử dụng cùng một TCP connection**. Server có thể đóng kết nối; mạng, timeout, proxy, TLS, nguồn đích, giới hạn pool, phiên bản giao thức hoặc trạng thái request đều có thể khiến client phải mở kết nối mới. Đây là cơ hội tối ưu mà triển khai có thể sử dụng, không phải cam kết “100% request dùng chung một socket”.

`HttpClient.Version.HTTP_2` là **phiên bản ưu tiên/yêu cầu khi có thể**; không phải bảo đảm giao thức thực tế của mọi response. Hãy kiểm tra `HttpResponse.version()` nếu ứng dụng cần biết HTTP/1.1 hay HTTP/2 đã được dùng. Trong Java 11, client mặc định ưu tiên HTTP/2 nhưng có thể sử dụng HTTP/1.1 khi điều kiện không cho phép HTTP/2.

### Thói quen nên tránh

```java
// Không nên tạo một HttpClient mới cho từng request trong đường nóng:
HttpResponse<String> response = HttpClient.newHttpClient()
        .send(request, HttpResponse.BodyHandlers.ofString());
```

Đoạn minh họa không sai về cú pháp; điểm bất lợi nằm ở **vòng đời** khi được chạy lặp lại trong một ứng dụng. Với hàng nghìn lần gọi, tạo client liên tục thường kém phù hợp hơn việc dùng một client lâu dài cho cùng nhóm chính sách.

Một client dùng chung không có nghĩa toàn ứng dụng bắt buộc chỉ được có đúng một client. Tạo **nhiều client có chủ đích** khi cần tách biệt SSL context, proxy, authenticator, cookie/session policy hoặc nhóm tài nguyên riêng.

## 4. Gửi nhiều request bằng cùng một client: ví dụ không cần Internet

Ví dụ này khởi động HTTP server trên `127.0.0.1` với cổng do hệ điều hành chọn, gửi **hai request đồng bộ** và **hai request bất đồng bộ** bằng **cùng một `HttpClient`**. Kết quả có nội dung cố định để không phụ thuộc vào server bên ngoài.

JDK cung cấp HTTP server nhỏ phục vụ test trong module `jdk.httpserver`. Đây chỉ là fixture để trình diễn; phần client vẫn dùng API `java.net.http` của Java 11.

Tệp **`ClientReuseLocalDemo.java`**:

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
import java.util.concurrent.atomic.AtomicInteger;

public class ClientReuseLocalDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger handled = new AtomicInteger();

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/ping", exchange -> {
            handled.incrementAndGet();
            byte[] body = "pong".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });

        server.start();
        try {
            URI uri = URI.create(
                    "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/ping");

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> first = client.send(
                    request, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            HttpResponse<String> second = client.send(
                    request, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            CompletableFuture<HttpResponse<String>> async1 =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            CompletableFuture<HttpResponse<String>> async2 =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));

            CompletableFuture.allOf(async1, async2).join();

            System.out.println("sync: "
                    + first.statusCode() + "/" + first.body()
                    + ", " + second.statusCode() + "/" + second.body());
            System.out.println("async: "
                    + async1.join().body() + ", " + async2.join().body());
            System.out.println("requests handled: " + handled.get());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy bằng JDK 11+ với module fixture được bật:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 ClientReuseLocalDemo.java
java --add-modules jdk.httpserver ClientReuseLocalDemo
```

Stdout khi local server nhận đủ bốn request:

```text
sync: 200/pong, 200/pong
async: pong, pong
requests handled: 4
```

Giải thích:

- Chỉ có **một lần tạo `HttpClient`**, nhưng có bốn lần gọi gửi request. Hai lệnh `send` chờ phản hồi; hai lệnh `sendAsync` trả về `CompletableFuture`.
- `CompletableFuture.allOf(...).join()` chờ cả hai tác vụ async hoàn tất trước khi in kết quả. Hai response async có nội dung bằng nhau nên thứ tự xử lý nội bộ không làm thay đổi stdout.
- Cùng một `HttpRequest` GET bất biến được gửi nhiều lần. Mỗi lần gửi trả về response riêng; máy chủ đếm được bốn request.
- Ví dụ dùng `HTTP_1_1` để phù hợp server test tối giản; không suy luận rằng một kết nối TCP duy nhất đã phục vụ cả bốn request. Để đo connection reuse thật, cần công cụ quan sát socket/connection của server hoặc tầng mạng.
- Nếu server local bị hệ điều hành hoặc sandbox chặn việc mở socket, lỗi môi trường đó không chứng minh API client bị sai.

## 5. Chia sẻ client khi nhiều luồng cùng gửi request

Một `HttpClient` đã build được thiết kế để phục vụ nhiều request, gồm các lệnh gọi đồng bộ và bất đồng bộ. Vì vậy một dịch vụ có thể giữ **một tham chiếu client dùng chung** và để nhiều lời gọi cùng gửi request, thay vì tạo client mới cho mỗi thread.

Cần phân biệt ba loại đối tượng:

| Đối tượng | Cách sử dụng phù hợp |
| --- | --- |
| `HttpClient.Builder` | Có thể thay đổi, **không thread-safe**; cấu hình lúc khởi tạo |
| `HttpClient` đã build | Cấu hình bất biến, có thể dùng chung để gửi nhiều request đồng thời |
| `HttpRequest.Builder` | Có thể thay đổi, **không thread-safe**; tạo builder riêng cho request cần khác cấu hình |
| `HttpRequest` đã build | Bất biến về cấu hình; có thể gửi lại khi body publisher và nghiệp vụ cho phép |
| `HttpResponse<T>` | Kết quả của một lần gửi, xử lý body/tài nguyên theo loại BodyHandler |

**Quan trọng:** Không chia sẻ một `HttpRequest.Builder` rồi để nhiều thread đồng thời thay URI, header hoặc body. Dùng một client chung nhưng tạo request builder **mới** trong từng lời gọi thường dễ suy luận nhất.

### Mẫu tổ chức theo dependency injection

Dưới đây là một lớp dịch vụ hoàn chỉnh có thể biên dịch trong JDK 11. Nó giả định một client được tạo và truyền vào từ nơi khởi tạo ứng dụng.

Tệp **`TextApi.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;

public final class TextApi {
    private final HttpClient client;

    public TextApi(HttpClient client) {
        this.client = Objects.requireNonNull(client);
    }

    public CompletableFuture<String> getText(URI uri) {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        return client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                .thenApply(response -> {
                    if (response.statusCode() != 200) {
                        throw new IllegalStateException(
                                "HTTP status: " + response.statusCode());
                    }
                    return response.body();
                });
    }
}
```

Biên dịch riêng (lớp không có `main` nên không chạy trực tiếp):

```bash
javac --release 11 -encoding UTF-8 TextApi.java
```

Ví dụ nơi khởi tạo ứng dụng có thể dùng:

```java
HttpClient shared = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

TextApi api = new TextApi(shared);
// Nhiều lời gọi api.getText(uri) dùng cùng shared.
```

Đây là **đoạn tích hợp**, không phải một chương trình có `main` hay stdout. Tham chiếu `client` được gán một lần và giữ trong field `final`; mỗi lần `getText` tạo request riêng với timeout của chính request.

Việc tái sử dụng client **không** tự bảo đảm service có logic đúng về retry, xác thực, idempotency, backpressure hay giới hạn số request đồng thời. Hãy xử lý các yêu cầu đó riêng trong tầng gọi.

## 6. Cấu hình nào gắn với client, cấu hình nào gắn với request?

| Phạm vi | Ví dụ cấu hình | Khi muốn đổi |
| --- | --- | --- |
| **Client** | `connectTimeout`, `followRedirects`, proxy, `SSLContext`, `Authenticator`, `CookieHandler`, executor, HTTP version ưu tiên | Xây client khác cho chính sách khác |
| **Request** | URI, HTTP method, headers, body publisher, timeout của request, version nếu chỉ định | Tạo `HttpRequest` khác; giữ client |
| **Response** | Status code, headers, body, HTTP version thực tế | Nhận kết quả mới từ mỗi lần gửi |

Hai timeout cần phân biệt:

- `HttpClient.Builder.connectTimeout(Duration)`: áp dụng **khi cần thiết lập kết nối mới**. Nếu có kết nối phù hợp để dùng lại, timeout thiết lập kết nối này không quyết định thời lượng xử lý request.
- `HttpRequest.Builder.timeout(Duration)`: timeout cho **request cụ thể**. Có thể đặt giá trị khác nhau cho hai request gửi bằng cùng một client.

### Ví dụ chạy độc lập: `ClientAndRequestTimeouts.java`

Ví dụ không gửi request ra mạng; chỉ in cấu hình đã build.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

public class ClientAndRequestTimeouts {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(4))
                .build();

        URI endpoint = URI.create("https://example.org/api");
        HttpRequest quick = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(2))
                .GET()
                .build();
        HttpRequest slower = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(20))
                .GET()
                .build();

        System.out.println("client connect: "
                + client.connectTimeout().orElseThrow().toSeconds());
        System.out.println("quick request: "
                + quick.timeout().orElseThrow().toSeconds());
        System.out.println("slower request: "
                + slower.timeout().orElseThrow().toSeconds());
    }
}
```

```bash
javac --release 11 -encoding UTF-8 ClientAndRequestTimeouts.java
java ClientAndRequestTimeouts
```

```text
client connect: 4
quick request: 2
slower request: 20
```

Hai request có timeout khác nhau trong khi cấu hình client được giữ nguyên. Địa chỉ `example.org` chỉ được dùng để xây URI; ví dụ này không thực hiện I/O mạng.

**Lưu ý về HTTP version:** chọn `client.version()` hoặc `HttpRequest.Builder.version(...)` chỉ biểu diễn phiên bản được ưu tiên/yêu cầu khi có thể; kiểm tra `response.version()` để biết phiên bản thực tế. Không coi preference HTTP/2 là lời hứa rằng mọi server đều dùng HTTP/2.

## 7. Client bất biến nhưng cookie, chứng thực và executor có trạng thái

“Bất biến” của `HttpClient` không có nghĩa mọi thứ đi cùng client đều là hằng số:

- `CookieHandler` có thể lưu, bổ sung hoặc xóa cookie theo các response và chính sách. Nếu dùng chung cookie handler, cần cân nhắc phạm vi người dùng/tenant hoặc phiên làm việc.
- `Authenticator` có thể gọi đến nguồn thông tin xác thực, cache hoặc trạng thái nội bộ. Không vô tình chia sẻ session/credential của người dùng này sang người dùng khác chỉ vì muốn tái sử dụng client.
- `Executor` tùy chỉnh là một đối tượng quản lý tác vụ và thread; nó có vòng đời và giới hạn công suất riêng.
- `SSLContext`, `ProxySelector` và các handler tùy chỉnh có chính sách cần được cân nhắc theo phạm vi chia sẻ.

**Nguyên tắc:** Tái sử dụng client trong một **ranh giới cấu hình và bảo mật phù hợp**. Một client dùng chung cho nhiều request cùng chính sách là hợp lý; nếu hai nhóm yêu cầu cần cookie/ủy quyền/TLS/proxy thực sự khác nhau, tạo các client riêng biệt có cấu hình rõ ràng.

Ví dụ một dịch vụ đa tenant nên xem lại cách gắn Authorization header, cookie và handler trước khi tạo singleton client. Có thể tiếp tục tái sử dụng client mà đặt header cho **từng HttpRequest** nếu chính sách bảo mật cho phép; không lưu token thay đổi theo người dùng vào các biến dùng chung không đồng bộ.

## 8. Gửi lại HttpRequest: bất biến không có nghĩa thao tác luôn lặp lại an toàn

Javadoc của `HttpRequest.Builder` nêu rằng đối tượng `HttpRequest` sau `build()` là immutable và **có thể được gửi nhiều lần**. Điều này hữu ích cho các GET có cùng URI và headers, như ví dụ server local.

Tuy vậy cần kiểm tra **body publisher** và **ngữ nghĩa nghiệp vụ**:

- GET không có body thường dễ dùng lại về mặt dữ liệu. Tuy nhiên server vẫn có thể thay đổi response giữa các lần gọi.
- Một POST thực hiện tạo đơn hàng hoặc chuyển tiền có thể gây **tác dụng phụ lặp lại** nếu gửi nhiều lần; bất biến của request không làm POST trở thành idempotent. Khi cần retry, dùng cơ chế idempotency được server hỗ trợ và chính sách rõ ràng.
- Nếu body được tạo từ nguồn dữ liệu chỉ đọc được một lần, cần bảo đảm publisher có thể cung cấp dữ liệu cho **mỗi lần gửi**. Không tự suy luận rằng mọi `BodyPublisher` tùy chỉnh đều có thể phát lại vô hạn.
- `BodyPublishers.ofInputStream(...)` dùng một `Supplier<InputStream>` để cung cấp stream; khi gửi lại, supplier cần có khả năng cung cấp nguồn mới nếu payload phải lặp lại.
- Header xác thực hay `X-Request-ID` thay đổi theo lượt gọi phải được đưa vào request **mới**, dù vẫn sử dụng client chung.

Ví dụ cách tổ chức tốt:

```java
// client đã được tạo và lưu bên ngoài vòng lặp
for (String id : ids) {
    HttpRequest request = HttpRequest.newBuilder(
            URI.create("https://example.org/items/" + id))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();
    client.sendAsync(request, HttpResponse.BodyHandlers.discarding());
}
```

Đây là **đoạn minh họa**, giả định `ids`, `client` đã được khai báo. Trong ứng dụng thực, cần **giữ và quản lý các CompletableFuture trả về**, xử lý lỗi và chờ hoặc giới hạn số tác vụ phù hợp; chỉ gọi rồi bỏ future có thể khiến lỗi không được quan sát. Địa chỉ trong ví dụ không dành cho chạy trực tiếp.

## 9. Quản lý vòng đời: Java 11 và Java 21 trở lên

Đây là khác biệt theo phiên bản cần biết để viết mã hiện đại đúng:

**Java 11 đến Java 20:**

- `HttpClient` **không triển khai `AutoCloseable`** và không có `close()`, `shutdown()` theo API hiện nay.
- Vì vậy `try (HttpClient client = ...)` và `client.close()` **không biên dịch khi dùng `--release 11`**.
- Thực hành thường phù hợp: giữ client cho vòng đời của thành phần/dịch vụ; quản lý kết quả request, body streaming và executor tùy chỉnh theo trách nhiệm của ứng dụng.

**Java 21 trở lên:**

- `HttpClient` triển khai `AutoCloseable`; có `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)` và `isTerminated()` (các API này được thêm từ Java 21).
- `close()` tiến hành đóng theo hướng orderly: không chấp nhận request mới và chờ các request trước đó hoàn tất theo hợp đồng.
- `shutdown()` khởi tạo quá trình ngừng nhận request mới nhưng không chờ; `awaitTermination(...)` có thể được dùng khi cần chờ có giới hạn.
- `shutdownNow()` là best effort, không phải cam kết dừng tức thì mọi hoạt động. Cần tránh ngắt các request mà ứng dụng vẫn cần kết quả.
- Trong cả hai thế hệ, response body dạng stream hoặc publisher cần được đọc hết/đóng/hủy đúng cách. Từ Java 21, nếu bỏ dở streaming body, việc `close()` theo hướng orderly có thể bị giữ lại lâu do request chưa hoàn tất.

Minh họa **chỉ dành cho Java 21+**:

```java
// Java 21+ (không biên dịch với --release 11)
try (HttpClient client = HttpClient.newHttpClient()) {
    // Gửi request và xử lý response/body tại đây.
} // close() khi kết thúc scope
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Với ứng dụng server đang phục vụ request, không nên tạo client trong try-with-resources của **mỗi lần xử lý request** nếu chủ đích là chia sẻ pool lâu dài. Đóng client khi thành phần sở hữu nó kết thúc vòng đời, sau khi xử lý các tác vụ cần hoàn tất.

**Tại sao vẫn gọi client là immutable ở Java 21+ dù có `close()`?** Bất biến nói về **cấu hình** client sau khi build; việc mở kết nối, gửi request, hoàn tất tác vụ hoặc chuyển sang trạng thái shutdown là **trạng thái vận hành/vòng đời**, không phải hành động sửa lại proxy, SSL context hay redirect policy.

## 10. Executor và tài nguyên của ứng dụng

Nếu không cung cấp executor, triển khai JDK tạo executor mặc định phục vụ các tác vụ bất đồng bộ của client. Tạo rất nhiều client lặp lại có thể kéo theo nhiều nhóm tài nguyên khó theo dõi.

Khi cần executor riêng:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
HttpClient client = HttpClient.newBuilder()
        .executor(executor)
        .build();
```

Đây là đoạn minh họa cần import `java.util.concurrent.ExecutorService` và `java.util.concurrent.Executors`. Ứng dụng phải quản lý executor do **chính mình tạo**, theo vòng đời và tải thực tế. Không gọi `executor.shutdown()` tùy tiện khi các request hoặc dependent tasks còn cần executor; điều đó có thể gây lỗi hoặc làm quá trình hoàn tất bị ảnh hưởng. Trên Java 21+, việc đóng client và tắt executor tùy chỉnh cần được phối hợp theo chính sách shutdown của hệ thống.

Không hiểu rằng bất kỳ lời gọi `sendAsync` nào cũng dùng duy nhất một thread hoặc rằng một client chỉ có một kết nối. Số thread, pool và lịch tác vụ là chi tiết có thể thay đổi theo triển khai và workload. Khi cần giới hạn tải, hãy kiểm soát mức song song ở tầng ứng dụng, đo bằng công cụ phù hợp và không suy diễn từ số lượng client.

## 11. Kiểm thử những gì khi tái sử dụng client?

Một bộ kiểm thử đáng tin cậy nên phân biệt **hành vi được API bảo đảm** và **hiệu năng/kết nối phụ thuộc môi trường**.

| Nhóm test | Điều cần xác minh | Điều không nên mặc định |
| --- | --- | --- |
| Bất biến cấu hình | Đổi builder sau build không đổi client đã tạo | Hai client từ cùng builder là cùng instance |
| Tái sử dụng logic | Một client gửi được nhiều request và nhận response riêng | Mọi request dùng chung đúng một socket |
| Đồng bộ/bất đồng bộ | `send` chờ response; `sendAsync` trả future và hoàn tất | Các request async luôn kết thúc theo thứ tự gửi |
| Request scope | URI, headers, timeout khác nhau không buộc tạo client mới | `connectTimeout` thay thế timeout của request |
| Builder đồng thời | Mỗi thread/lời gọi dùng request builder riêng | Dùng chung builder mutable là thread-safe |
| Body streaming | Consume/close body theo handler | Đọc một phần rồi bỏ vẫn giải phóng mọi tài nguyên |
| Vòng đời Java 21+ | Shutdown/close sau khi hoàn tất tác vụ, không gửi mới sau shutdown | `shutdownNow` bảo đảm hủy tức thì tất cả hoạt động |

### Bộ test cấu hình không cần mạng

Tệp **`ClientReuseAssertions.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

public class ClientReuseAssertions {
    private static int checks = 0;

    static void check(String label, boolean condition) {
        checks++;
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        HttpClient.Builder builder = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER);

        HttpClient first = builder.build();
        builder.connectTimeout(Duration.ofSeconds(7))
                .followRedirects(HttpClient.Redirect.ALWAYS);
        HttpClient second = builder.build();

        check("first timeout",
                first.connectTimeout().orElseThrow().equals(
                        Duration.ofSeconds(3)));
        check("second timeout",
                second.connectTimeout().orElseThrow().equals(
                        Duration.ofSeconds(7)));
        check("first redirects",
                first.followRedirects() == HttpClient.Redirect.NEVER);
        check("second redirects",
                second.followRedirects() == HttpClient.Redirect.ALWAYS);
        check("different clients", first != second);

        URI uri = URI.create("https://example.org/ping");
        HttpRequest a = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(2)).GET().build();
        HttpRequest b = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10)).GET().build();

        check("request A timeout",
                a.timeout().orElseThrow().equals(Duration.ofSeconds(2)));
        check("request B timeout",
                b.timeout().orElseThrow().equals(Duration.ofSeconds(10)));
        check("client unchanged",
                first.connectTimeout().orElseThrow().equals(
                        Duration.ofSeconds(3)));

        System.out.println("PASS: " + checks + " checks");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 ClientReuseAssertions.java
java ClientReuseAssertions
```

```text
PASS: 8 checks
```

Đếm kiểm tra: hai timeout client, hai redirect policy, hai client khác nhau, hai timeout request và một kiểm tra client không đổi — tổng **8**. Nếu một điều kiện sai, chương trình ném `AssertionError` với tên case. Vì không có `send`, bài test không truy cập `example.org`.

**Để kiểm chứng connection reuse thực sự**, dùng test tích hợp với server/proxy có logging connection ID hoặc công cụ phân tích mạng, đồng thời xét chính sách keep-alive, phiên bản HTTP, TLS và timeout của môi trường. Đừng đặt assertion rằng 100 request nhất định mở chính xác một socket; đây không phải bảo đảm của Javadoc.

## 12. Các lỗi thường gặp

1. **Tạo `HttpClient.newHttpClient()` trong mỗi lần gọi.** Hệ thống mất cơ hội chia sẻ tài nguyên/kết nối; ưu tiên client được giữ theo vòng đời dịch vụ.
2. **Cho nhiều thread sửa cùng `HttpClient.Builder` hoặc `HttpRequest.Builder`.** Builder có thể thay đổi và không thread-safe; chỉ chia sẻ đối tượng sau build khi hợp đồng cho phép.
3. **Nghĩ immutable nghĩa là không có connection pool, cookie hay task chạy nền.** Đây là bất biến **cấu hình**, không loại bỏ trạng thái vận hành.
4. **Đặt timeout toàn bộ request bằng `connectTimeout`.** Giá trị này chỉ có tác dụng khi cần thiết lập kết nối; dùng `HttpRequest.timeout` cho thời hạn cụ thể của request.
5. **Cho rằng `version(HTTP_2)` ép mọi server dùng HTTP/2.** Kiểm tra `HttpResponse.version()` thay vì chỉ nhìn preference của client.
6. **Dùng lại request chứa body chỉ phát được một lần hoặc thao tác POST có tác dụng phụ.** Xem lại publisher và ngữ nghĩa retry/idempotency.
7. **Dùng chung cookie/credential giữa các phạm vi bảo mật không phù hợp.** Thiết kế chính sách auth/session trước khi tái sử dụng client.
8. **Bỏ mặc `CompletableFuture` của `sendAsync`.** Cần quan sát lỗi, quản lý số tác vụ, completion và cancellation.
9. **Đóng client quá sớm ở Java 21+.** Client dùng chung nên sống đến khi thành phần sở hữu nó shutdown; hoàn tất hoặc hủy các request theo chính sách.
10. **Gọi `client.close()` trong mã phải chạy Java 11.** API close của `HttpClient` chỉ có từ Java 21; phân biệt phiên bản khi biên dịch.
11. **Không tiêu thụ/đóng streaming response bodies.** Điều đó có thể giữ kết nối, tài nguyên và cản trở graceful shutdown.

## 13. Câu hỏi củng cố

**A.** Hai lời gọi `client.send(...)` dùng cùng một đối tượng client có bắt buộc dùng cùng TCP connection không?

**B.** Thay đổi `HttpClient.Builder.followRedirects(...)` sau khi `build()` có cập nhật client đã tạo không?

**C.** Ứng dụng cần hai request có timeout 3 và 20 giây, có bắt buộc tạo hai client không?

**D.** Có nên dùng chung một `HttpRequest.Builder` từ nhiều thread không?

**E.** Mã `try (HttpClient client = HttpClient.newHttpClient())` dùng `--release 11` có biên dịch được không?

**F.** Cùng `HttpRequest` POST được gửi lần thứ hai có tự bảo đảm nghiệp vụ không bị xử lý lặp không?

**Đáp án:** A: Không; có cơ hội tái sử dụng kết nối nhưng không bảo đảm. B: Không; client đã build có cấu hình cố định. C: Không; dùng `HttpRequest.timeout(...)` khác nhau. D: Không, builder không thread-safe. E: Không; `AutoCloseable/close` của HttpClient xuất hiện từ Java 21. F: Không; phải xét idempotency và khả năng phát lại body.

## Tài liệu chính thức

- [Java SE 11 — HttpClient: immutable sau khi build; send và sendAsync](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 11 — HttpClient.Builder: cấu hình và tính không thread-safe của builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html).
- [Java SE 11 — HttpRequest.Builder: request bất biến sau build, có thể gửi nhiều lần](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
- [Java SE 11 — HttpRequest và BodyPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Java SE 21 — HttpClient.close, shutdown, AutoCloseable (thêm từ 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 26 — HttpClient: quản lý tài nguyên và connection sharing hiện đại](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html).
