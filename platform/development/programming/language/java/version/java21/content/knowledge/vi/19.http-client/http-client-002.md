# Lựa chọn phạm vi sống của client và tái sử dụng connection

## 1. Vì sao cần tái sử dụng `HttpClient`?

`java.net.http.HttpClient` trong Java 21 được thiết kế để gửi nhiều HTTP request thông qua cùng một client. Sau khi được tạo, `HttpClient` là immutable (không thay đổi cấu hình) và có thể được dùng cho nhiều request. Mỗi instance thường tự quản lý pool connection của nó để tái sử dụng khi phù hợp; các pool thường không được chia sẻ giữa những instance `HttpClient` khác nhau.

Vì vậy, tạo một client mới cho mỗi request thường làm mất cơ hội tái sử dụng connection và lặp lại chi phí khởi tạo tài nguyên mạng. Với các request có cùng cấu hình và cùng phạm vi bảo mật, nên dùng một client sống đủ lâu để phục vụ nhiều request.

```java
private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .version(HttpClient.Version.HTTP_2)
        .build();

static HttpResponse<String> get(URI uri)
        throws IOException, InterruptedException {
    HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

    return HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
}
```

Trong ví dụ, nhiều lần gọi `get` dùng chung `HTTP_CLIENT`. Cấu hình client được giữ cố định, còn mỗi request có URI và timeout riêng. Cách tổ chức này cho phép client quản lý tài nguyên và connection qua nhiều lần gửi request.

Tái sử dụng client không có nghĩa ứng dụng được bảo đảm dùng lại đúng một TCP connection cho mọi request. Connection cụ thể còn phụ thuộc giao thức HTTP, server, proxy, TLS, trạng thái connection, thời gian idle và điều kiện mạng. API không cung cấp một connection handle để ứng dụng tự chọn hoặc bắt buộc dùng một socket cụ thể.

## 2. Phân biệt vòng đời client, request và response body

Ba phạm vi này có vòng đời khác nhau:

| Thành phần | Phạm vi sống điển hình | Trách nhiệm |
|---|---|---|
| `HttpClient` | Vòng đời ứng dụng hoặc thành phần tích hợp với một cấu hình mạng | Quản lý cấu hình client và tài nguyên mạng dùng chung |
| `HttpRequest` | Một lần gửi request hoặc một thao tác nghiệp vụ | Mô tả URI, method, header, body publisher và timeout |
| `HttpResponse`/response body | Từ khi nhận response đến khi body được đọc hoặc đóng theo loại body handler | Đọc dữ liệu, giải phóng stream/subscription nếu dùng body dạng streaming |

Không nên đóng client sau mỗi request nếu client được thiết kế để dùng chung lâu dài. Ngược lại, cũng không nên giữ stream response chưa đọc hoặc chưa đóng vô thời hạn chỉ vì client vẫn còn sống.

Với `BodyHandlers.ofString()` hoặc `BodyHandlers.ofByteArray()`, body được đọc vào bộ nhớ trước khi response hoàn tất theo kiểu body tương ứng. Với `BodyHandlers.ofInputStream()` hoặc `BodyHandlers.ofLines()`, ứng dụng nhận stream để tự đọc và phải đóng stream khi hoàn tất. Với publisher/subscriber streaming, phải tiêu thụ dữ liệu hoặc hủy subscription đúng cách.

## 3. `HttpClient` immutable và dùng chung giữa nhiều request

Client được cấu hình thông qua `HttpClient.Builder`, sau đó tạo bằng `build()`. Khi đã build, cấu hình của client không còn thay đổi. Đây là lý do phù hợp để chia sẻ một instance giữa nhiều thread/task, bao gồm các request đồng thời.

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .version(HttpClient.Version.HTTP_2)
        .build();

// Có thể gọi đồng thời từ nhiều thread.
CompletableFuture<HttpResponse<String>> first = client.sendAsync(
        HttpRequest.newBuilder(URI.create("https://api.example.com/a")).build(),
        HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<String>> second = client.sendAsync(
        HttpRequest.newBuilder(URI.create("https://api.example.com/b")).build(),
        HttpResponse.BodyHandlers.ofString());
```

Client là immutable; các request riêng biệt vẫn có thể chạy đồng thời. Không cần tạo một `HttpClient` riêng cho từng thread. Tạo client riêng chỉ nên xuất phát từ nhu cầu cấu hình hoặc cô lập trạng thái thực sự.

Lưu ý rằng `HttpClient.Builder` không thread-safe. Hãy cấu hình builder trong một luồng khởi tạo, gọi `build()`, rồi chia sẻ client đã tạo. Không dùng chung một builder để nhiều thread cùng thay đổi cấu hình và gọi `build()`.

## 4. Connection pool và giới hạn của bảo đảm tái sử dụng

Một instance `HttpClient` thường quản lý pool connection riêng và có thể tái sử dụng các connection đó khi thích hợp. Tạo nhiều client độc lập thường đồng nghĩa với nhiều nhóm tài nguyên/pool riêng, làm tăng chi phí kết nối và giảm khả năng tái sử dụng giữa các request.

Tuy nhiên, cần hiểu đúng mức bảo đảm:

- API bảo đảm client có thể được dùng cho nhiều request; API không bảo đảm mọi request sẽ dùng cùng một connection.
- Connection có thể bị đóng bởi server, proxy, peer timeout, lỗi mạng hoặc chính sách idle.
- Request đến các origin khác nhau không nhất thiết có thể dùng chung connection.
- Connection HTTP/2 có thể phục vụ nhiều stream đồng thời; HTTP/1.1 có mô hình trao đổi khác và khả năng reuse phụ thuộc trạng thái connection.
- `HttpClient` không cung cấp API công khai để xem hoặc trực tiếp quản lý từng connection trong pool.

Do đó, nên tái sử dụng client để cho implementation cơ hội quản lý pool hiệu quả, nhưng không xây logic nghiệp vụ phụ thuộc vào việc connection cụ thể luôn được giữ mở.

## 5. HTTP/1.1, HTTP/2 và multiplexing

`HttpClient.Builder.version(...)` chọn phiên bản giao thức được ưu tiên khi có thể. Trong Java 21, mặc định client ưu tiên HTTP/2. Nếu HTTP/2 không được hỗ trợ trong điều kiện kết nối cụ thể, client có thể sử dụng HTTP/1.1.

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpResponse<String> response = client.send(
        HttpRequest.newBuilder(URI.create("https://example.com/health")).build(),
        HttpResponse.BodyHandlers.ofString());

System.out.println(response.version()); // Phiên bản thực tế của response
```

`client.version()` biểu thị phiên bản được cấu hình/ưu tiên. `response.version()` cho biết phiên bản được dùng cho response cụ thể.

HTTP/2 hỗ trợ multiplexing: nhiều stream request/response có thể cùng hoạt động trên một connection. Vì thế, khi server và đường truyền hỗ trợ HTTP/2, tái sử dụng một client có thể giúp tận dụng connection và multiplexing hiệu quả. Với HTTP/1.1, connection persistent cũng có thể được tái sử dụng khi phù hợp, nhưng không có multiplexing nhiều request độc lập trên cùng connection theo cách HTTP/2 cung cấp.

Không nên giả định chỉ vì đã yêu cầu HTTP/2 thì mọi response chắc chắn dùng HTTP/2. Hãy kiểm tra `HttpResponse.version()` nếu ứng dụng cần quan sát giao thức thực tế.

## 6. Chọn phạm vi sống phù hợp

### 6.1. Client cấp ứng dụng hoặc service

Với một service gọi cùng nhóm endpoint và dùng chung cấu hình proxy, TLS, redirect, authentication và cookie policy, thường nên tạo một client khi service khởi tạo và dùng nó cho đến khi service dừng.

```java
final class CatalogApi implements AutoCloseable {
    private final HttpClient client;

    CatalogApi() {
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .version(HttpClient.Version.HTTP_2)
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    HttpResponse<String> find(String id)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("https://catalog.example.com/items/" + id))
                .timeout(Duration.ofSeconds(8))
                .GET()
                .build();

        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    @Override
    public void close() {
        client.close();
    }
}
```

Application container hoặc thành phần quản lý vòng đời gọi `close()` khi `CatalogApi` dừng. Method `find` không tạo hoặc đóng client mỗi lần được gọi.

### 6.2. Client theo tác vụ batch ngắn hạn

Nếu một tác vụ độc lập thực hiện một nhóm request rồi kết thúc, có thể đặt client trong try-with-resources:

```java
try (HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build()) {

    for (URI uri : uris) {
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        process(response);
    }
}
```

Client được tái sử dụng cho tất cả request trong batch và được đóng khi batch hoàn tất. Đây là phạm vi hợp lý khi tác vụ thực sự sở hữu client và không cần giữ client cho công việc khác.

### 6.3. Tránh tạo client trong từng request handler

Ví dụ không nên dùng cho endpoint được gọi thường xuyên:

```java
// Không nên: mỗi lần xử lý lại tạo một client mới.
HttpResponse<String> call(URI uri) throws IOException, InterruptedException {
    try (HttpClient client = HttpClient.newHttpClient()) {
        return client.send(
                HttpRequest.newBuilder(uri).build(),
                HttpResponse.BodyHandlers.ofString());
    }
}
```

Đóng client ngay sau mỗi lần gọi làm giảm cơ hội tái sử dụng connection cho request tiếp theo và tăng số lần khởi tạo tài nguyên. Hãy chuyển client thành field được quản lý theo vòng đời service hoặc application.

## 7. Khi nào nên tạo nhiều client?

Không phải toàn ứng dụng chỉ nên có đúng một client. Tạo nhiều client là hợp lý khi chúng cần cấu hình hoặc ranh giới trạng thái khác nhau.

| Khác biệt | Vì sao có thể cần client riêng |
|---|---|
| `SSLContext` hoặc trust/key material khác nhau | Cần trust store, client certificate hoặc chính sách TLS riêng |
| Proxy hoặc network route khác nhau | Request đi qua các proxy hoặc network interface khác nhau |
| `Authenticator` hoặc thông tin xác thực khác nhau | Cần tách danh tính gọi dịch vụ và phạm vi quyền |
| `CookieHandler`/cookie store khác nhau | Cần tách phiên và trạng thái cookie, ví dụ giữa tenant hoặc tài khoản |
| Chính sách redirect/protocol/timeout khác nhau | Các nhóm endpoint có yêu cầu giao thức hoặc chính sách vận hành khác nhau |
| Executor bất đồng bộ khác nhau | Cần tách tài nguyên và chính sách thực thi callback/task của client |

Ví dụ, không nên dùng chung một client có cookie store chứa session của nhiều người dùng nếu cookie có thể làm lẫn trạng thái xác thực. Trong trường hợp đó, hãy tách client hoặc cookie handler theo ranh giới phiên phù hợp.

Mỗi client bổ sung có thể có pool và tài nguyên riêng. Không tạo client riêng chỉ vì URL khác nhau nếu cấu hình, chính sách bảo mật và trạng thái có thể dùng chung. Ngược lại, không ép dùng chung một client khi điều đó làm trộn credential, cookie hoặc trust boundary.

## 8. Cấu hình client và cấu hình từng request

Một quyết định quan trọng là đặt thuộc tính ở cấp client hay request.

| Cấp client (`HttpClient.Builder`) | Cấp request (`HttpRequest.Builder`) |
|---|---|
| Preferred HTTP version | URI và HTTP method |
| Proxy selector | Request headers |
| `SSLContext` và `SSLParameters` | Request body publisher |
| `Authenticator` | Request timeout |
| `CookieHandler` | Các header riêng như `Accept`, `Content-Type` |
| Redirect policy | Thông tin riêng của lần gọi |
| Connect timeout |  |
| Executor cho async/dependent tasks |  |

Ví dụ, connect timeout được đặt ở client và chỉ có tác dụng khi cần thiết lập connection mới. Nếu connection được tái sử dụng, connect timeout không áp dụng cho request đó. Request timeout được đặt trên `HttpRequest` để giới hạn thời gian của request theo chính sách riêng.

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(7))
        .header("Accept", "application/json")
        .GET()
        .build();
```

Không dùng connect timeout như timeout tổng cho mọi request. Hai loại timeout bảo vệ các giai đoạn khác nhau.

## 9. Quản lý vòng đời `HttpClient` trong Java 21

Từ Java 21, `HttpClient` triển khai `AutoCloseable` và cung cấp các method quản lý vòng đời: `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)`, `isTerminated()` và `close()`.

| Method | Ý nghĩa |
|---|---|
| `shutdown()` | Bắt đầu orderly shutdown: không nhận request mới, nhưng request đã gửi được phép hoàn tất; method không chờ hoàn tất |
| `awaitTermination(duration)` | Chờ tối đa thời gian chỉ định sau khi shutdown; trả `true` nếu đã kết thúc, `false` nếu hết thời gian |
| `isTerminated()` | Kiểm tra mọi hoạt động đã kết thúc sau shutdown hay chưa |
| `close()` | Bắt đầu orderly shutdown và chờ các hoạt động đã gửi hoàn tất; client không nhận request mới |
| `shutdownNow()` | Cố gắng bắt đầu shutdown ngay; không có bảo đảm mọi hoạt động đang chạy sẽ dừng thành công |

Với client thuộc quyền sở hữu của một thành phần, có thể gọi `close()` khi thành phần dừng. Với client dùng chung ở cấp ứng dụng, hãy đóng nó trong lifecycle hook khi ứng dụng dừng, sau khi ngừng nhận công việc mới và xử lý các request đang chạy theo chính sách shutdown.

Không gọi `close()` trên client dùng chung sau từng request. `close()` là thao tác kết thúc vòng đời client, không phải thao tác kết thúc một request.

### 9.1. Orderly shutdown và chờ hoàn tất

Nếu cần tách thời điểm ngừng nhận request mới khỏi thời điểm chờ hoàn tất, có thể gọi `shutdown()` rồi `awaitTermination`:

```java
client.shutdown();

try {
    boolean terminated = client.awaitTermination(Duration.ofSeconds(20));
    if (!terminated) {
        // Ghi nhận rằng client chưa hoàn tất trong thời hạn chờ.
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
}
```

`shutdown()` không chờ request cũ hoàn tất. `awaitTermination` mới thực hiện việc chờ có giới hạn. `close()` là lựa chọn gọn hơn khi muốn orderly shutdown và chờ đến khi client kết thúc.

`shutdownNow()` chỉ nên dùng khi chính sách dừng khẩn cấp yêu cầu. API không bảo đảm các hoạt động đang chạy sẽ kết thúc hoặc mọi bên chờ sẽ được thông báo. Cần xử lý timeout và interruption ở tầng ứng dụng thay vì giả định shutdownNow luôn dừng ngay mọi I/O.

### 9.2. Đóng response body dạng streaming trước khi đóng client

JDK built-in `HttpClient` cần các request đã gửi hoàn tất để orderly shutdown kết thúc. Nếu ứng dụng nhận stream nhưng không đọc hết, không đóng hoặc không hủy stream/subscription, request có thể vẫn được xem là chưa hoàn tất và làm shutdown bị kẹt.

Ví dụ với `InputStream`:

```java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    body.transferTo(destination);
}
```

Với `BodyHandlers.ofLines()`, hãy đóng stream:

```java
HttpResponse<Stream<String>> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.forEach(this::processLine);
}
```

Với body publisher hoặc custom subscriber, phải yêu cầu dữ liệu đến khi hoàn tất hoặc hủy subscription khi không cần đọc tiếp. Quản lý body đúng cách vừa giải phóng tài nguyên vừa giúp client kết thúc orderly shutdown.

## 10. Executor tùy chỉnh và vòng đời riêng

Có thể truyền executor vào `HttpClient.Builder.executor(...)` để thực thi asynchronous và dependent tasks của client:

```java
ExecutorService callbackExecutor = Executors.newVirtualThreadPerTaskExecutor();

HttpClient client = HttpClient.newBuilder()
        .executor(callbackExecutor)
        .build();
```

Executor do ứng dụng cung cấp có vòng đời cần được quản lý rõ ràng. `HttpClient` nhận một `Executor` để sử dụng; không nên giả định việc đóng client cũng tự động đóng executor mà ứng dụng đã truyền vào. Nếu executor là `ExecutorService`, chủ sở hữu của nó phải quyết định thời điểm shutdown/close.

Ví dụ quản lý cả hai tài nguyên:

```java
try (ExecutorService callbackExecutor = Executors.newVirtualThreadPerTaskExecutor()) {
    try (HttpClient client = HttpClient.newBuilder()
            .executor(callbackExecutor)
            .build()) {

        CompletableFuture<HttpResponse<String>> response = client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());

        System.out.println(response.join().statusCode());
    }
}
```

Trong ví dụ, client được đóng trước, sau đó executor được đóng. Với executor dùng chung cho nhiều thành phần, chỉ thành phần sở hữu mới được phép đóng executor; không để một client hoặc service đóng nhầm tài nguyên dùng chung.

Lưu ý: executor của client liên quan đến asynchronous/dependent tasks theo hợp đồng builder. Nó không đồng nghĩa mọi hoạt động socket hoặc mọi thao tác nội bộ của implementation đều chạy trực tiếp trên executor do ứng dụng cung cấp.

## 11. Các lỗi thường gặp khi chọn scope và tái sử dụng

| Cách làm | Hệ quả | Cách thiết kế phù hợp |
|---|---|---|
| Tạo `HttpClient` cho từng request | Khó tái sử dụng connection pool, tăng chi phí tạo tài nguyên | Dùng client dài hạn cho nhóm request cùng cấu hình |
| Đóng client sau mỗi request | Các request sau không thể dùng client/pool cũ | Đóng khi service hoặc batch sở hữu client kết thúc |
| Dùng một client cho nhiều ranh giới xác thực/cookie | Có thể trộn trạng thái session hoặc credential | Tách client/cookie handler theo ranh giới bảo mật |
| Giữ response stream không đóng | Connection/request có thể không được giải phóng; shutdown có thể bị kẹt | Đọc hết, đóng stream hoặc cancel subscription |
| Cho rằng `client.version()` là giao thức chắc chắn của mọi response | Server/proxy có thể khiến giao thức thực tế khác | Kiểm tra `response.version()` |
| Nhầm connect timeout với request timeout | Không kiểm soát đúng thời gian chờ response | Đặt connect timeout ở client và request timeout ở request |
| Đóng executor do ứng dụng truyền vào từ một component không sở hữu nó | Các thành phần khác mất khả năng thực thi task | Quản lý executor theo ownership riêng |
| Dùng `shutdownNow()` như bảo đảm hủy mọi I/O | Hoạt động đang chạy có thể không dừng như kỳ vọng | Thiết kế timeout, cancellation và shutdown có phối hợp |

## 12. Checklist lựa chọn phạm vi sống

Trước khi quyết định tạo hoặc đóng client, hãy xác định:

1. Nhóm request có cùng proxy, TLS, authentication, cookie và redirect policy không?
2. Client có thể được tạo ở cấp application hoặc service để phục vụ nhiều request không?
3. Thành phần nào sở hữu client và chịu trách nhiệm đóng nó?
4. Có response body dạng stream/publisher nào cần được đóng hoặc cancel không?
5. Request có cần HTTP/2 không, và đã kiểm tra protocol thực tế qua response chưa?
6. Connect timeout và request timeout đã được đặt ở đúng cấp chưa?
7. Có executor tùy chỉnh không, và ai sở hữu vòng đời executor đó?
8. Có ranh giới tenant/session/credential nào yêu cầu client riêng không?
9. Shutdown có ngừng nhận request mới, chờ request cũ và xử lý timeout/interruption đúng cách không?

## 13. Tài liệu tham khảo chính thức

- [Java SE 21 API — `HttpClient`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): tính immutable, quản lý pool connection, gửi nhiều request, HTTP version và lifecycle API Java 21.
- [Java SE 21 API — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): cấu hình client, connect timeout, executor, proxy, TLS và version.
- [Java SE 21 API — `HttpRequest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout và cấu trúc request.
- [Java SE 21 API — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): cách xử lý response body dạng string, byte array, input stream, lines và publisher.
- [Java SE 21 API — `HttpResponse`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.html): status, headers, body và phiên bản HTTP thực tế.

Hãy tạo `HttpClient` theo phạm vi cấu hình và bảo mật cần dùng chung, giữ client đủ lâu để phục vụ nhiều request, rồi đóng khi chủ sở hữu kết thúc vòng đời. Tái sử dụng client cho phép implementation tận dụng connection pool, nhưng không bảo đảm một socket cụ thể luôn được dùng lại. Với Java 21, cần quản lý thêm lifecycle `close`/`shutdown` và đóng response stream đúng cách để các request hoàn tất và tài nguyên được giải phóng.
