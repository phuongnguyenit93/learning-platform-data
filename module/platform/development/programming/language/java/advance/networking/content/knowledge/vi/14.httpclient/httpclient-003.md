# Builder có thể thay đổi và đối tượng client, request sau khi build

## Mục tiêu bài học

Trong Java 17+, API `java.net.http` dùng **Builder pattern** để tạo `HttpClient` và `HttpRequest`. Một phân biệt rất quan trọng là **builder còn có thể thay đổi**, trong khi **đối tượng đã build được thiết kế bất biến về cấu hình**. Nếu không hiểu ranh giới này, chương trình dễ gửi nhầm URI, header, body hoặc cấu hình timeout/redirect, nhất là khi nhiều luồng cùng làm việc.

Sau bài này, bạn có thể:

- Phân biệt `HttpClient.Builder`, `HttpClient`, `HttpRequest.Builder` và `HttpRequest`.
- Giải thích chính xác mỗi lời gọi `build()` tạo **đối tượng mới theo trạng thái builder ở thời điểm đó**, không biến builder thành đối tượng đã khóa.
- Chứng minh việc **sửa builder sau khi build** không làm thay đổi cấu hình `HttpClient` hoặc method/URI/headers của `HttpRequest` đã tạo.
- Biết `HttpClient` nên được **tái sử dụng** để chia sẻ tài nguyên kết nối; `HttpRequest` đã build có thể tái sử dụng theo semantics API, nhưng phải xem xét body publisher và việc gửi lại request không idempotent.
- Sử dụng `header`, `setHeader`, `uri`, `timeout`, `GET`/`POST`, `HttpRequest.Builder.copy()` và `HttpRequest.newBuilder(existingRequest, filter)` đúng ý nghĩa.
- Phân biệt thuộc tính ở cấp **client** (connect timeout, HTTP version preference, redirect policy, proxy, TLS) với thuộc tính ở cấp **request** (URI, method, headers, body, request timeout).
- Chọn cách phối hợp thread an toàn: **không dùng chung một builder để sửa đồng thời**; dùng chung client/request đã build trong phạm vi phù hợp.
- Kiểm chứng bằng chương trình Java 17 chạy **HTTP server/client trên loopback**, không cần Internet.

**Phạm vi:** Java SE 17 `java.net.http.HttpClient`/`HttpRequest` và các builder tương ứng. Những khác biệt Java 21+ được nêu riêng khi ảnh hưởng đến vòng đời tài nguyên; không dùng API không tồn tại trên Java 17.

## 1. Mô hình: Builder là bản nháp, đối tượng build là cấu hình đã chốt

Sơ đồ tổng quan:

~~~text
HttpClient.newBuilder()
       │
       ▼
HttpClient.Builder  ──── cấu hình có thể sửa: version, redirect,
       │                  connectTimeout, proxy, TLS, executor...
       │ build()
       ▼
  HttpClient A       ← cấu hình đã build; dùng để gửi nhiều request
       ▲
       │
       └─── HttpClient.Builder vẫn có thể sửa tiếp rồi build()
                                         │
                                         ▼
                                    HttpClient B

HttpRequest.newBuilder(uri)
       │
       ▼
HttpRequest.Builder ──── cấu hình có thể sửa: method, URI,
       │                  header, request timeout, body...
       │ build()
       ▼
  HttpRequest X     ← method/URI/header/timeouts đã được tạo
       ▲
       │
       └─── builder tiếp tục thay đổi, build() lần nữa
                                         │
                                         ▼
                                    HttpRequest Y
~~~

**Tư duy chính:**

1. `newBuilder()` tạo **builder**, chưa phải client/request cuối cùng.
2. Các setter trên builder **thay đổi chính instance builder** và thường trả về `this` để gọi chuỗi.
3. `build()` trả về **một client/request mới** dựa trên trạng thái builder tại thời điểm gọi.
4. **Builder không tự bị vô hiệu hóa sau `build()`**: có thể tiếp tục gọi setter rồi `build()` lần nữa.
5. **Đối tượng cũ không bị “nâng cấp” theo builder**. Muốn đổi cấu hình client hoặc thông số request, tạo object khác.
6. “Immutable” ở đây chủ yếu nói về **cấu hình của đối tượng**. Nó không có nghĩa mọi đối tượng được tham chiếu qua cấu hình đều sâu-bất-biến, hoặc trạng thái mạng của client không bao giờ thay đổi.

Ví dụ ý tưởng:

~~~java
HttpClient.Builder builder = HttpClient.newBuilder();
HttpClient first = builder.build();

builder.followRedirects(HttpClient.Redirect.ALWAYS);
HttpClient second = builder.build();

// first không tự đổi policy chỉ vì builder vừa thay đổi.
~~~

Đây là snippet cần import `java.net.http.HttpClient`. `first` và `second` là hai đối tượng độc lập được tạo từ hai snapshot cấu hình khác nhau. Đừng nhầm `first = builder.build()` là “liên kết sống” với builder.

## 2. Bốn kiểu đối tượng và mức thay đổi

| Đối tượng | Cách tạo | Sau khi tạo có sửa được không? | Nên dùng vào việc gì? |
|---|---|---|---|
| `HttpClient.Builder` | `HttpClient.newBuilder()` | **Có**, thông qua setter | Chuẩn bị cấu hình dùng chung cho nhiều HTTP request |
| `HttpClient` | `clientBuilder.build()` hoặc `HttpClient.newHttpClient()` | **Không sửa cấu hình client qua builder cũ** | Gửi nhiều request đồng bộ/bất đồng bộ, chia sẻ tài nguyên |
| `HttpRequest.Builder` | `HttpRequest.newBuilder(uri)`, `newBuilder()`, hoặc sao chép từ request | **Có**, thông qua setter | Tạo một hoặc nhiều cấu hình request |
| `HttpRequest` | `requestBuilder.build()` | **Không có setter sửa request đã build** | Đưa vào `HttpClient.send` / `sendAsync` |

`HttpClient.newHttpClient()` là cách tạo nhanh client với thiết lập mặc định. Khi cần timeout, redirect, TLS context, proxy hoặc version preference thì dùng builder.

`HttpRequest.newBuilder(URI)` tạo request builder đã có URI. `HttpRequest.newBuilder()` cần đặt `uri(...)` trước `build()`; nếu không có URI, `build()` có thể ném `IllegalStateException`.

**Chú ý tên gọi:** `HttpClient.Builder` và `HttpRequest.Builder` là hai interface **khác nhau**. Dù đều có `build()`, client builder không có `uri(...)`/`GET()`, còn request builder không có `followRedirects(...)`/`connectTimeout(...)`.

## 3. Mutable builder: setter sửa trạng thái hiện tại

Ví dụ client builder:

~~~java
HttpClient.Builder cb = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .version(HttpClient.Version.HTTP_1_1);

HttpClient client1 = cb.build();

cb.connectTimeout(Duration.ofSeconds(5))
  .followRedirects(HttpClient.Redirect.ALWAYS)
  .version(HttpClient.Version.HTTP_2);

HttpClient client2 = cb.build();
~~~

Đây là snippet cần import `java.net.http.HttpClient` và `java.time.Duration`. Mỗi lời gọi cấu hình sửa `cb`; thứ tự trên tạo hai client với các giá trị khác nhau.

- `client1.connectTimeout().orElseThrow()` vẫn là 2 giây.
- `client1.followRedirects()` vẫn là `NEVER`.
- `client1.version()` vẫn là `HTTP_1_1`.
- `client2` nhận 5 giây, `ALWAYS` và preferred `HTTP_2`.

**Không nói `client2` chắc chắn giao tiếp bằng HTTP/2.** `HttpClient.version()` mô tả version ưu tiên/cấu hình; giao thức thực tế có thể phụ thuộc server, TLS/ALPN, proxy và khả năng negotiation. Kiểm tra `HttpResponse.version()` sau khi có response.

### Đối tượng nào nên thay đổi, đối tượng nào nên dùng lại?

- Muốn đổi timeout/redirect policy của **một client đã build**: tạo **client khác** từ builder.
- Muốn đổi URI/header của **một request đã build**: tạo **request khác** từ builder hoặc sao chép request.
- Muốn gửi request tới nhiều URL cùng chính sách HTTP/TLS: **tái sử dụng một HttpClient** và tạo nhiều `HttpRequest`.
- Không tạo `new HttpClient` cho **mỗi** request chỉ vì cần URI khác; cấu hình URI nằm ở request, không nằm ở client.

Tài liệu Java 17 ghi rõ `HttpClient` sau build là immutable và có thể dùng gửi nhiều request; client còn cung cấp **resource sharing** cho những lần gửi, như các tài nguyên HTTP/network mà triển khai có thể tái sử dụng. Không suy diễn rằng việc tái sử dụng **luôn** tạo đúng một TCP connection, vì connection pooling/negotiation và server policy là chi tiết thực thi.

## 4. `HttpRequest.Builder`: trạng thái của từng request

Một request có thể gồm URI, method, headers, body publisher, timeout và version preference:

~~~java
HttpRequest.Builder rb = HttpRequest.newBuilder(
        URI.create("https://api.example.org/items"))
    .timeout(Duration.ofSeconds(4))
    .header("Accept", "application/json")
    .GET();

HttpRequest request = rb.build();
~~~

Đây là snippet, cần import `java.net.URI`, `java.net.http.HttpRequest` và `java.time.Duration`. Request `request` đã build không tự đổi khi `rb` thay đổi.

Một số thao tác trên request builder:

| API | Thay đổi trạng thái builder | Điểm cần nhớ |
|---|---|---|
| `uri(URI)` | Thay URI đích | Dùng URI có scheme `http` hoặc `https` phù hợp |
| `GET()` | Đặt method thành GET | Mặc định đã là GET nếu chưa đặt method khác |
| `POST(BodyPublisher)` | Đặt POST và body publisher | Body là đối tượng phát dữ liệu, không phải String field tự động |
| `PUT(BodyPublisher)` | Đặt PUT và body publisher | Chọn đúng semantics API |
| `DELETE()` | Đặt DELETE | Không tự biến request đã build khác thành DELETE |
| `method("PATCH", publisher)` | Đặt method tùy chọn và publisher | Kiểm tra method server/API hỗ trợ |
| `header(name, value)` | **Thêm** một giá trị header | Có thể tạo nhiều giá trị cho cùng header |
| `setHeader(name, value)` | **Thay** các giá trị trước của header đó | Dùng khi muốn chắc chắn chỉ có giá trị mới |
| `headers(name1, value1, ...)` | Thêm nhiều cặp header | Số tham số phải chẵn và hợp lệ |
| `timeout(Duration)` | Đặt request timeout | Khác với client connect timeout |
| `version(HttpClient.Version)` | Đặt preferred version riêng của request | Response thực tế có thể dùng version khác |
| `expectContinue(boolean)` | Yêu cầu cơ chế `100 Continue` khi phù hợp | Không phải mọi server/proxy đều xử lý giống nhau |
| `build()` | Trả về `HttpRequest` mới | Builder vẫn tiếp tục dùng được |
| `copy()` | Trả builder mới có cùng trạng thái hiện tại | Chỉ có trên **HttpRequest.Builder** trong Java 17 |

### `header` và `setHeader` khác nhau

Ví dụ:

~~~java
HttpRequest.Builder b = HttpRequest.newBuilder(
    URI.create("https://example.org"))
    .header("X-Tag", "one")
    .header("X-Tag", "two");

HttpRequest r1 = b.build();             // X-Tag có 2 giá trị.

b.setHeader("X-Tag", "final");
HttpRequest r2 = b.build();             // X-Tag chỉ còn "final".
~~~

Đây là snippet cần import `java.net.URI` và `java.net.http.HttpRequest`. `r1.headers().allValues("X-Tag")` có hai giá trị; `r2` có một. Mặc dù tên header HTTP không phân biệt hoa/thường, vẫn nên dùng `HttpHeaders.firstValue`/`allValues` thay vì tự so tên hoặc parse dòng header.

Không phải header nào cũng được đặt bằng `HttpRequest.Builder.header`: JDK HTTP client có thể từ chối một số tên hoặc giá trị **restricted** (ví dụ `Content-Length` do body publisher quyết định), hoặc điều khiển chúng qua API riêng. Khi gặp `IllegalArgumentException`, không nên lách kiểm tra bằng cách tự ghép chuỗi raw HTTP.

### `GET()`, `POST()` và body publisher

`HttpRequest.Builder.GET()` dùng cho GET thông thường và là mặc định khi chưa chọn method. `POST(publisher)` thiết lập body publisher; một số method có `noBody()` khi không cần body.

~~~java
HttpRequest post = HttpRequest.newBuilder(
    URI.create("https://api.example.org/items"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(
        "{\"name\":\"Java\"}", StandardCharsets.UTF_8))
    .build();
~~~

Snippet trên cần import `java.net.URI`, `java.net.http.HttpRequest`, `java.nio.charset.StandardCharsets`. API nhận `BodyPublisher` để gửi các byte; `String.length()` không được dùng để điền thủ công `Content-Length`.

**Chỉ đổi method trên builder không đảm bảo nghiệp vụ an toàn.** Một request `POST` gửi lại có thể tạo thêm tài nguyên. Dù `HttpRequest` immutable và được phép gửi nhiều lần, việc **retry** phụ thuộc idempotency, authentication, semantics API và khả năng phát lại body.

## 5. Ví dụ chạy thật: sửa hai builder nhưng các đối tượng cũ không đổi

Chương trình Java 17 sau sử dụng `com.sun.net.httpserver.HttpServer` trên `127.0.0.1` cùng `java.net.http.HttpClient`. Không gọi Internet, không cần credential. Chương trình tạo hai client từ **một client builder đã thay đổi**, rồi tạo ba request qua **một request builder** và một bản `copy()`. Sau đó gửi ba request tới HTTP server cục bộ để đối chiếu giá trị trên wire.

Lưu file đầy đủ **`BuilderSnapshotDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class BuilderSnapshotDemo {
    private static void handle(HttpExchange ex) throws IOException {
        String stage = ex.getRequestHeaders().getFirst("X-Stage");
        String data = ex.getRequestMethod() + " "
            + ex.getRequestURI().getRawPath()
            + " | stage=" + stage;
        byte[] bytes = data.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type",
                                    "text/plain; charset=utf-8");
        ex.sendResponseHeaders(200, bytes.length);
        try (var body = ex.getResponseBody()) {
            body.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpClient.Builder clientBuilder = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .version(HttpClient.Version.HTTP_1_1);

        HttpClient firstClient = clientBuilder.build();

        clientBuilder.connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.ALWAYS)
            .version(HttpClient.Version.HTTP_2);
        HttpClient secondClient = clientBuilder.build();

        System.out.println("client1: "
            + firstClient.connectTimeout().orElseThrow().toSeconds()
            + "s, " + firstClient.followRedirects()
            + ", " + firstClient.version());
        System.out.println("client2: "
            + secondClient.connectTimeout().orElseThrow().toSeconds()
            + "s, " + secondClient.followRedirects()
            + ", " + secondClient.version());

        HttpServer server = HttpServer.create(
            new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/", BuilderSnapshotDemo::handle);
        server.start();
        try {
            URI base = URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort());
            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder(
                    base.resolve("/first"))
                .setHeader("X-Stage", "alpha")
                .header("X-Tag", "one")
                .GET();

            HttpRequest firstRequest = requestBuilder.build();

            requestBuilder.uri(base.resolve("/second"))
                .setHeader("X-Stage", "beta")
                .header("X-Tag", "two");
            HttpRequest secondRequest = requestBuilder.build();

            HttpRequest.Builder fork = requestBuilder.copy();
            HttpRequest copiedRequest = fork
                .uri(base.resolve("/copy"))
                .setHeader("X-Stage", "gamma")
                .build();

            System.out.println("request1: "
                + firstRequest.uri().getRawPath()
                + " | " + firstRequest.headers()
                    .firstValue("X-Stage").orElse("")
                + " | tags=" + firstRequest.headers()
                    .allValues("X-Tag").size());
            System.out.println("request2: "
                + secondRequest.uri().getRawPath()
                + " | " + secondRequest.headers()
                    .firstValue("X-Stage").orElse("")
                + " | tags=" + secondRequest.headers()
                    .allValues("X-Tag").size());
            System.out.println("request3: "
                + copiedRequest.uri().getRawPath()
                + " | " + copiedRequest.headers()
                    .firstValue("X-Stage").orElse("")
                + " | tags=" + copiedRequest.headers()
                    .allValues("X-Tag").size());

            System.out.println("response1: "
                + firstClient.send(firstRequest,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8)).body());
            System.out.println("response2: "
                + firstClient.send(secondRequest,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8)).body());
            System.out.println("response3: "
                + firstClient.send(copiedRequest,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8)).body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Cách biên dịch và chạy

Yêu cầu **JDK 17+** có các module chuẩn `java.net.http` và `jdk.httpserver`:

~~~bash
javac -encoding UTF-8 BuilderSnapshotDemo.java
java BuilderSnapshotDemo
~~~

Stdout đã kiểm tra thực tế:

~~~text
client1: 2s, NEVER, HTTP_1_1
client2: 5s, ALWAYS, HTTP_2
request1: /first | alpha | tags=1
request2: /second | beta | tags=2
request3: /copy | gamma | tags=2
response1: GET /first | stage=alpha
response2: GET /second | stage=beta
response3: GET /copy | stage=gamma
~~~

Các dòng này chỉ hiển thị những giá trị quyết định của demo; port thật do OS chọn bằng cổng `0` nhưng **không xuất hiện trong stdout**. Ba request đều gửi bằng `firstClient` để giữ cùng cấu hình client. `secondClient` được tạo nhằm quan sát snapshot khác; không gửi HTTP/2 lên server demo vốn là HTTP/1.1.

### Giải thích output từng bước

1. `client1` được build khi connect timeout = 2s, redirects = `NEVER`, preferred version = `HTTP_1_1`.
2. Sau đó sửa **cùng client builder** sang 5s, `ALWAYS` và `HTTP_2` rồi build `client2`.
3. `client1` vẫn in các giá trị ban đầu. Nếu client cũ “tự chạy theo builder”, kết quả sẽ sai — nhưng điều đó không xảy ra.
4. `firstRequest` được build với `/first`, `X-Stage: alpha` và một `X-Tag`.
5. Sửa **request builder** sang `/second`, thay `X-Stage` thành `beta` và **thêm** `X-Tag: two`; `secondRequest` nhận hai giá trị X-Tag, còn `firstRequest` vẫn chỉ có một.
6. `requestBuilder.copy()` tạo builder mới từ trạng thái `/second`, rồi nhánh `fork` đặt `/copy` và `gamma`. `copiedRequest` mang trạng thái nhánh mới, không làm thay đổi `secondRequest` đã build.
7. HTTP server nhận đúng các đường dẫn và `X-Stage` như từng request đã build; không có thay đổi ngầm theo builder về sau.
8. Việc `firstClient.send(...)` được gọi nhiều lần trên cùng một client minh họa **reuse client**. Không dùng `clientBuilder.build()` lại cho mỗi request.

**Lưu ý:** `HttpClient.version()` trong stdout là phiên bản **ưu tiên**; không có một request HTTP/2 nào được gửi bởi `secondClient` nên không thể dùng output đó để kết luận server hỗ trợ HTTP/2.

## 6. Snapshot và ranh giới “bất biến” chính xác đến đâu?

Câu **“HttpClient và HttpRequest immutable”** là đúng theo tài liệu Java 17 ở mức **cấu hình công khai sau build**. Tuy nhiên cần tách ba lớp trạng thái:

1. **Builder state**: thay đổi được; mỗi setter sửa cấu hình của builder.
2. **Built configuration**: URI, method, headers, request timeout, preferred version hoặc client connect timeout/redirect policy **không bị sửa bằng cách thay đổi builder cũ**.
3. **Trạng thái bên ngoài/đang chạy**: socket, connection pool, cookie store, authenticator, proxy selector, custom body publisher, file hay mutable application objects có thể thay đổi theo thời gian. `build()` **không phải phép deep-copy toàn bộ thế giới**.

Một ví dụ trực quan:

~~~java
HttpRequest request = HttpRequest.newBuilder(
    URI.create("https://example.org/items"))
    .setHeader("X-Trace", "v1")
    .GET()
    .build();

// Không có request.setHeader("X-Trace", "v2").
// Tạo HttpRequest khác khi muốn đổi header.
~~~

Đây là snippet cần import `java.net.URI` và `java.net.http.HttpRequest`. Việc thiếu public setter trên `HttpRequest` thể hiện cấu hình đã đóng băng.

**Nhưng client vẫn hoạt động:** một `HttpClient` có thể tạo/kết thúc kết nối TCP, duy trì trạng thái hỗ trợ HTTP/2, trao đổi cookies qua `CookieHandler` đã cấu hình, chạy tác vụ asynchronous và nhận nhiều response. Đó không phải là “mutation builder”, cũng không mâu thuẫn với bất biến cấu hình.

**Đối tượng phụ thuộc có thể có state:** nếu cung cấp `CookieHandler`, `Authenticator`, `ProxySelector`, `Executor` hoặc custom `BodyPublisher`, chúng có thể mang trạng thái riêng. Không suy luận rằng mọi byte phát ra hoặc mọi cookie đều giữ nguyên vĩnh viễn sau `build()`. Cấu hình tham chiếu tới các thành phần bên ngoài và cách chúng hoạt động là một lớp trách nhiệm khác.

Một ví dụ về giới hạn của snapshot là request body tạo từ file hoặc supplier stream. `HttpRequest` giữ một `BodyPublisher`, nhưng nội dung được publish có thể phụ thuộc nguồn dữ liệu tại lúc gửi. Việc sửa file sau khi `build()` không được dùng làm một bảo đảm “request sẽ luôn gửi bytes y hệt”, vì còn phụ thuộc từng loại publisher và thời điểm đọc dữ liệu.

## 7. Hai cách tạo request mới từ mẫu có sẵn

### Cách A: `HttpRequest.Builder.copy()`

Tài liệu Java 17 cho biết `copy()` trả một builder **mới** có trạng thái tương đương builder hiện tại; sau đó mỗi builder có thể được sửa độc lập.

~~~java
HttpRequest.Builder template = HttpRequest.newBuilder(
    URI.create("https://api.example.org/v1"))
    .setHeader("Accept", "application/json")
    .timeout(Duration.ofSeconds(3));

HttpRequest.Builder branchA = template.copy()
    .uri(URI.create("https://api.example.org/v1/a"));
HttpRequest.Builder branchB = template.copy()
    .uri(URI.create("https://api.example.org/v1/b"));

HttpRequest a = branchA.build();
HttpRequest b = branchB.build();
~~~

Đây là snippet cần import `java.net.URI`, `java.time.Duration` và `java.net.http.HttpRequest`. `copy()` tránh sửa một builder chia sẻ giữa hai luồng công việc, nhưng **không được hiểu là clone sâu mọi đối tượng tham chiếu**, đặc biệt với `BodyPublisher` có trạng thái ngoài.

### Cách B: `HttpRequest.newBuilder(request, headerFilter)`

Từ **một request đã build**, Java 17 cho phép tạo builder dựa trên request đó và **lọc header** khi sao chép:

~~~java
HttpRequest next = HttpRequest.newBuilder(
        previous,
        (name, value) -> !name.equalsIgnoreCase("Authorization"))
    .uri(URI.create("https://api.example.org/other"))
    .build();
~~~

Snippet này giả định `previous` là `HttpRequest` đã build và import `java.net.URI`, `java.net.http.HttpRequest`. Bộ lọc nhận tên/giá trị của **từng cặp header**. Ví dụ trên bỏ `Authorization` khi tạo một request khác, tránh vô tình tái sử dụng bearer token ở sai resource.

**Đừng suy diễn rằng filter này tẩy sạch mọi credential:** cookie có thể được quản lý bởi `CookieHandler` của client, authentication có thể đến từ `Authenticator`, URL có thể chứa thông tin nhạy cảm và header khác cũng cần xem xét. Trong chuyển hướng từ host này sang host khác, nên thiết kế client/credential scope và redirect policy thay vì chỉ tin một bộ lọc header.

### Nên dùng cách nào?

| Tình huống | Cách hợp lý |
|---|---|
| Có cấu hình request mẫu chưa build, cần nhiều biến thể | `template.copy()` mỗi biến thể |
| Có request đã build, cần sửa URI/header/timeout | `HttpRequest.newBuilder(existing, filter)` rồi build mới |
| Tạo một request đơn giản hoàn toàn mới | `HttpRequest.newBuilder(uri)` trực tiếp |
| Nhiều thread tạo requests độc lập | Mỗi thread giữ một builder riêng hoặc bản copy phù hợp |
| Cần giữ cấu hình client chung | Reuse **một `HttpClient`**, không lặp xây client cho từng request |

## 8. Thread safety: builder không giống client

Theo Java SE 17, các setter trên **`HttpClient.Builder` và `HttpRequest.Builder` không được thiết kế thread-safe**. Không chia sẻ một instance builder để nhiều thread cùng gọi `uri`, `setHeader`, `POST` và `build` khi không có đồng bộ phù hợp.

Ví dụ sai dễ gây “trộn request”:

~~~java
// Một shared HttpRequest.Builder được cả thread A và B sử dụng.
sharedBuilder.uri(uriA).setHeader("X-User", "alice");
sharedBuilder.uri(uriB).setHeader("X-User", "bob");
// Thread A gọi build() ở thời điểm không xác định.
HttpRequest requestA = sharedBuilder.build();
~~~

Đây là mã minh họa race, không phải chương trình độc lập. Có thể `requestA` nhận URI/header của B hoặc một trạng thái không mong muốn. Chỉ dùng `synchronized` nếu thực sự cần share builder, nhưng cấu trúc tốt hơn thường là **mỗi request sở hữu builder riêng**.

Ví dụ đúng:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .build();

// Trong các tác vụ/threads khác nhau:
HttpRequest req = HttpRequest.newBuilder(targetUri)
    .setHeader("Accept", "application/json")
    .GET()
    .build();

HttpResponse<String> res = client.send(
    req, HttpResponse.BodyHandlers.ofString());
~~~

Đây là snippet cần import `java.net.http.*`, `java.time.Duration`, và giả định `targetUri` hợp lệ, `res` được xử lý sau đó. Các threads có thể dùng chung `client` đã build để gửi request, còn mỗi request có builder riêng. Nếu application dùng custom `CookieHandler`/`BodyPublisher`/`Executor`, các thành phần ấy cũng cần thread-safety phù hợp với cách sử dụng đồng thời.

**HttpRequest sau build cũng có thể được gửi nhiều lần**, nhưng đừng đồng nhất “có thể gửi” với “luôn có ý nghĩa gửi lại”. `GET` read-only thông thường phù hợp hơn `POST` tạo giao dịch; publisher kiểu input stream/file/custom có thể không phát lại bytes như mong muốn. Với các request có tác động, thiết kế idempotency/retry policy riêng.

## 9. Timeout, version, redirect: đặt đúng tầng

| Chính sách | Cấp cấu hình | Ý nghĩa |
|---|---|---|
| `connectTimeout(Duration)` | `HttpClient.Builder` | Thời hạn tạo **kết nối mới**, không phải timeout mọi request và không áp lên kết nối đã reuse |
| `followRedirects(Redirect)` | `HttpClient.Builder` | Có tự theo HTTP redirects không, theo policy `NEVER`/`NORMAL`/`ALWAYS` |
| `version(Version)` | Client hoặc Request builder | Preferred HTTP version, không cam kết server/response dùng đúng |
| `proxy(ProxySelector)` | `HttpClient.Builder` | Chính sách proxy của client |
| `sslContext(SSLContext)` | `HttpClient.Builder` | TLS trust/key context cho các kết nối HTTPS |
| `executor(Executor)` | `HttpClient.Builder` | Executor cho công việc async/phụ thuộc trong triển khai |
| `timeout(Duration)` | `HttpRequest.Builder` | Timeout cho từng request nếu response không về trong thời hạn |
| `uri(URI)` | `HttpRequest.Builder` | Endpoint đích của một request |
| `header/setHeader` | `HttpRequest.Builder` | Metadata riêng của request |
| `POST(BodyPublisher)` | `HttpRequest.Builder` | Method + body publisher riêng của request |

**Client connect timeout và request timeout khác nhau.** Nếu server kết nối nhanh nhưng xử lý request rất lâu, `connectTimeout` có thể không giúp. Dùng request timeout phù hợp để giới hạn chờ response, và quản lý hủy/trạng thái khi dùng `sendAsync`.

Đặt request version khác client:

~~~java
HttpRequest req = HttpRequest.newBuilder(target)
    .version(HttpClient.Version.HTTP_1_1)
    .GET()
    .build();

// Sau send, kiểm tra response.version(), không đoán từ req.
~~~

Snippet cần import `java.net.http.HttpRequest`, `java.net.http.HttpClient` và giả định `target` là URI hợp lệ.

**Redirect là chính sách bảo mật:** `Redirect.ALWAYS` có semantics khác `NORMAL`/`NEVER`. Theo Java 17, `NORMAL` không tự động follow redirect từ HTTPS sang HTTP, còn `ALWAYS` cho phép theo redirect bất kể protocol. Khi xử lý token/cookie hoặc URL do người dùng cung cấp, cần cân nhắc kỹ rủi ro downgrade, đổi host và SSRF; không chọn `ALWAYS` chỉ vì muốn “cho request nào cũng thành công”.

## 10. BodyPublisher: request immutable nhưng dữ liệu phát đi có thể có vòng đời riêng

`HttpRequest` đã build lưu thông tin về `BodyPublisher`, không nhất thiết là bản sao bất biến của **mọi byte** sẽ gửi.

Một số publisher thông dụng:
- `HttpRequest.BodyPublishers.noBody()`: không có nội dung body.
- `ofString(text, UTF_8)`: chuẩn bị phát nội dung chuỗi.
- `ofByteArray(byte[])`: phát bytes từ mảng qua publisher API; xem hợp đồng sao chép/khả năng lặp của loại publisher cụ thể.
- `ofFile(path)`: dữ liệu liên quan file được đọc khi phát, có khả năng file thay đổi hoặc bị xóa theo thời gian.
- `ofInputStream(supplier)`: tạo dữ liệu từ một `Supplier<InputStream>`; nguồn phải được thiết kế để có thể cung cấp stream mới khi cần gửi lại.

**Lưu ý replay:** một custom `BodyPublisher` đọc trực tiếp từ một stream đã tiêu thụ có thể không phát lại cùng bytes nếu gửi request hai lần hoặc client retry. API cho phép reuse `HttpRequest` không có nghĩa mọi publisher, file hay hệ thống bên ngoài đều được “đóng băng” và tái lập hoàn hảo.

Ví dụ một cách tạo body phù hợp khi muốn gửi đi từ dữ liệu nội bộ rõ ràng:

~~~java
byte[] payload = "{\"name\":\"Java\"}"
    .getBytes(StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder(target)
    .setHeader("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
    .build();
~~~

Đây là snippet, cần import `java.net.http.HttpRequest`, `java.nio.charset.StandardCharsets`; `target` phải là URI. Khi logic cần **repeatable** bytes, chuẩn bị nội dung bất biến theo ứng dụng và chọn publisher phù hợp. Không gửi `POST` trùng lặp vô ý khi có nguy cơ tạo đơn hàng/thanh toán hai lần.

### Immutable không phải deep freeze toàn bộ dependencies

Nếu bạn cấp một `CookieManager` vào client builder:
- Cấu hình **client gắn CookieHandler** đã được chọn khi build.
- **Kho cookie** có thể được cập nhật bởi response HTTP hoặc bởi code khác, và ảnh hưởng các request tương lai.
- Điều này không phải builder đã sửa client; nó là biến đổi trạng thái **của CookieHandler** được tham chiếu.

Tương tự, một `Authenticator` có state hoặc custom proxy selector có thể quyết định hành vi runtime; cần quản lý phạm vi chia sẻ, concurrency và bảo mật.

## 11. Vòng đời client trong Java 17

`HttpClient` có thể được dùng gửi nhiều request, và dùng một client lâu dài thường hợp lý hơn tạo hàng loạt client mới. Mục tiêu là tránh chi phí và phân mảnh tài nguyên HTTP/network khi mỗi thao tác dựng client mới không cần thiết.

**Cần chú ý phiên bản JDK:** trong **Java 17**, API `HttpClient` chưa cung cấp `close()`/`AutoCloseable` như những phiên bản JDK mới hơn. Vì vậy không viết:

~~~java
// Không biên dịch đúng với HttpClient API Java 17:
try (HttpClient client = HttpClient.newHttpClient()) {
    // ...
}
~~~

Đây là **ví dụ lỗi phiên bản có chủ đích**, không phải code runnable trong Java 17. Khi học tài liệu Java 21+ có các phương thức lifecycle mới, phải kiểm tra đúng phiên bản API target thay vì chép vào source JDK 17.

Trong một ứng dụng dài hạn, quản lý **số lượng HttpClient**, thread pools custom, connection-level settings, timeout và shutdown của toàn bộ ứng dụng. Nếu tự cấp `Executor` cho client, vòng đời executor ấy do ứng dụng kiểm soát. Không vứt tham chiếu client trong vòng lặp như một chiến lược “đóng socket” không có trong API Java 17.

### Client configuration ≠ request state ≠ response state

Một client cấu hình timeout/redirect/version, nhưng `send`/`sendAsync` trả về **response** chứa:
- `statusCode()` và `headers()` của response,
- `body()` theo `BodyHandler` đã chọn,
- `version()` — phiên bản thực dùng cho response,
- `uri()` — URI cuối cùng tương ứng response (có thể khác URI ban đầu sau redirect).

Các thuộc tính này là **kết quả runtime**, không bị “cố định” chỉ vì client configuration immutable. Body có thể là `String`, `byte[]`, `InputStream`, file path hoặc kiểu subscriber do handler định nghĩa; mỗi lựa chọn có cách quản lý tài nguyên khác nhau.

## 12. Những lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| “Gọi `build()` xong builder bị khóa.” | Builder vẫn mutable, có thể build tiếp | Phân biệt builder với object đã build |
| “Sửa builder sẽ tự đổi client cũ.” | `HttpClient` có cấu hình bất biến sau build | Build client mới nếu đổi policy |
| “Sửa builder sẽ tự đổi request cũ.” | `HttpRequest` immutable | Build request mới hoặc clone bằng builder |
| “`HttpClient.Builder` và `HttpRequest.Builder` như nhau.” | Setter/client policy khác với request URI/body | Đặt cấu hình đúng tầng |
| “`header` thay thế header trước đó.” | `header` **thêm** giá trị | Dùng `setHeader` khi muốn thay |
| “`copy()` trả HttpRequest bất biến.” | `copy()` trả **builder mới** | Gọi `copy().build()` |
| “`HttpClient.Builder.copy()` có trên Java 17.” | API này không được công bố trên client builder JDK 17 | Tạo client builder mới/áp cấu hình rõ |
| “Chia sẻ một request builder cho các thread không đồng bộ.” | Builder setter không thread-safe | Mỗi thread/request dùng builder riêng |
| “Client immutable nghĩa CookieHandler không đổi.” | Phụ thuộc runtime có state riêng | Quản lý mutable dependency |
| “Request immutable nghĩa body phát đi luôn giống nhau.” | Publisher/file/stream có vòng đời riêng | Xét repeatability, chỉ retry an toàn |
| “Tạo một HttpClient cho từng request là bắt buộc.” | Client có thể gửi nhiều request và chia sẻ tài nguyên | Reuse client theo trust/config |
| “`connectTimeout` áp lên mọi lần send.” | Chỉ liên quan tạo kết nối mới | Thêm request timeout phù hợp |
| “`version(HTTP_2)` buộc server dùng HTTP/2.” | Đây là preferred version | Đọc `HttpResponse.version()` |
| “`Redirect.ALWAYS` luôn an toàn.” | Có thể theo redirect ngoài ý muốn, kể cả downgrade | Chọn policy và kiểm tra trust boundary |
| “`HttpClient` trong Java 17 chắc chắn AutoCloseable.” | API lifecycle khác Java 21+ | Đọc đúng JDK docs và quản lý số client |
| “Gửi lại cùng POST request object chắc chắn không trùng giao dịch.” | Immutability không tự tạo idempotency | Dùng idempotency key + contract server |

## 13. Checklist thiết kế thực tế

Trước khi đưa `HttpClient` vào một service Java, hỏi:

1. **Phạm vi client:** có dùng chung proxy, TLS trust, redirect, cookie policy và connection timeout không? Nếu giống nhau, xây và **reuse** một client.
2. **Phạm vi request:** mỗi request có URI, method, header, payload và timeout riêng không? Dùng `HttpRequest.newBuilder` hoặc `copy` mỗi lần.
3. **Concurrency:** có thread nào gọi setter trên cùng builder cùng lúc không? Nếu có, thiết kế lại để không chia sẻ mutable builder; đảm bảo mutable dependencies thread-safe.
4. **Timeout:** có connect timeout và per-request timeout phù hợp không? Khi gửi async có kế hoạch cancel/exception handling không?
5. **Body publisher:** dữ liệu có đủ kích thước/định dạng, có stream nào chỉ đọc một lần, có cần phát lại khi retry/redirect không?
6. **HTTP semantics:** POST/PUT/PATCH/DELETE có idempotent theo contract không; có cần key chống gửi trùng?
7. **Identity/security:** HTTPS có truststore/hostname validation đúng? Redirect policy có vô tình đổi host, gửi credential sai nơi hoặc downgrade không?
8. **Observability:** đo status/latency/version thực tế; log có che `Authorization`, cookie, query chứa secret?
9. **Lifecycle:** có tạo thừa client hay executor? Phiên bản JDK runtime có các API lifecycle nào?
10. **Test:** xây hai client từ một builder sửa đổi; xây nhiều request từ một builder/copy; assert dữ liệu cũ bất biến; test response trên loopback.

## 14. Bài tập tự kiểm tra

1. Một `HttpClient.Builder` cấu hình connect timeout 2 giây rồi build `c1`; sau đó sửa thành 5 giây và build `c2`. Giá trị `c1.connectTimeout()` là bao nhiêu? Vì sao?
2. `requestBuilder.header("X-Tag", "a").header("X-Tag", "b")` rồi build. Header đó có mấy giá trị? Muốn chỉ còn `"c"` phải dùng API nào?
3. Sau khi `HttpRequest request = rb.build()`, `rb.uri(newUri)` có làm đổi `request.uri()` không?
4. `requestBuilder.copy()` trả về `HttpRequest` hay `HttpRequest.Builder`? Nếu sửa copy, builder gốc có bị thay đổi không?
5. Nêu trường hợp dùng `HttpRequest.newBuilder(previous, filter)` thay vì một builder mới hoàn toàn.
6. Vì sao không nên dùng chung một `HttpRequest.Builder` để nhiều thread thay URI/header rồi build đồng thời?
7. `HttpClient` immutable nhưng ứng dụng dùng `CookieHandler` lưu cookie session. Cookie được cập nhật có mâu thuẫn với client immutable không?
8. Một `HttpRequest` chứa `BodyPublisher` đọc file, file thay đổi trước lần gửi sau. “Request immutable” có đủ để bảo đảm bytes phát đi không đổi không?
9. Tại sao `HttpClient.version() == HTTP_2` không chứng minh response đã dùng HTTP/2?
10. `connectTimeout` đã đặt 2 giây; server nhận TCP nhưng xử lý 1 phút. Timeout nào có ý nghĩa hơn ở cấp request?
11. Một `POST` đã build được `send` hai lần. Điều đó có tự bảo đảm backend chỉ tạo một tài nguyên không?
12. Vì sao không nên đặt `followRedirects(ALWAYS)` một cách vô điều kiện với client có credential hoặc đích do người dùng cung cấp?
13. Với Java 17, cú pháp `try (HttpClient c = HttpClient.newHttpClient())` có đúng API version không?
14. Viết một đoạn tạo request mẫu với header `Accept` và timeout 3 giây, sau đó tạo hai biến thể URI khác nhau mà không sửa cùng builder đồng thời.
15. Trong ví dụ chạy thật, vì sao `request1` vẫn có một `X-Tag` dù request builder sau đó được thêm `X-Tag: two`?

**Đáp án ngắn:** (1) 2 giây, snapshot sau build; (2) hai, dùng `setHeader("X-Tag","c")`; (3) không; (4) builder mới, có thể thay đổi độc lập; (5) muốn giữ một phần request đã build và lọc/sửa header; (6) data race; (7) không, cookie store là dependency có trạng thái; (8) không; (9) chỉ preferred config, xem `HttpResponse.version()`; (10) `HttpRequest.Builder.timeout`; (11) không, idempotency riêng; (12) rủi ro redirect/downgrade và phạm vi credential; (13) không với Java 17; (14) dùng `copy()`/new builder mỗi nhánh; (15) request đã build không đổi theo builder.

## 15. Tổng kết

- **Builder mutable:** setter thay đổi chính builder; `build()` tạo object mới và **không khóa** builder để sử dụng tiếp.
- **HttpClient immutable về cấu hình:** build một lần cho một chính sách chung và **reuse** cho nhiều request; muốn đổi timeout/redirect/proxy/TLS hãy tạo client mới.
- **HttpRequest immutable về metadata:** URI/method/header/timeouts đã build không đổi; muốn biến thể dùng builder mới, `copy()` hoặc `newBuilder(existing, filter)`.
- **Thread safety:** builder không thread-safe; tách builder theo request/thread thay vì cùng sửa; client đã build có thể chia sẻ để gửi request đồng thời trong phạm vi đúng.
- **Không thần thánh hóa immutability:** connection pool, CookieHandler, custom BodyPublisher và dữ liệu file/stream có vòng đời riêng; retry còn phụ thuộc HTTP semantics.
- **Kiểm tra version và timeout đúng tầng:** client `connectTimeout` khác request `timeout`; client/request version là preference, response `version()` mới phản ánh giao thức thực.
- **Java 17 tương thích:** API cơ bản của `java.net.http` có từ Java 11; không sao chép máy móc lifecycle API mới hơn vào source Java 17.

### Tài liệu tham khảo

- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Oracle Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Oracle Java SE 17 — HttpRequest.Builder, copy, header/setHeader](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Oracle Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Oracle Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [Oracle Java SE 17 — HttpServer for local tests](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
