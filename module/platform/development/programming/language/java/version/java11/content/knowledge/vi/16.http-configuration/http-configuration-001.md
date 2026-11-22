# Redirect.NEVER, Redirect.NORMAL, Redirect.ALWAYS — cấu hình HTTP Client trong Java 11+

## 1. Vì sao cần cấu hình HTTP redirect?

Khi client truy cập một URL, máy chủ có thể trả **HTTP 3xx** và header `Location` yêu cầu truy cập địa chỉ khác. Ví dụ:

```http
HTTP/1.1 302 Found
Location: /new-address
Content-Length: 0
```

Client có thể **tự động gửi request tiếp** đến `/new-address`, hoặc **trả nguyên response 302** cho ứng dụng quyết định. Quyết định này không chỉ ảnh hưởng trải nghiệm mà còn ảnh hưởng tới **bảo mật**, **HTTP method**, **request body**, **số lần gửi request** và **địa chỉ cuối cùng** mà ứng dụng liên hệ.

Trong Java 11, gói tiêu chuẩn `java.net.http` cung cấp enum:

```java
java.net.http.HttpClient.Redirect
```

với ba hằng số **`NEVER`, `NORMAL`, `ALWAYS`**. Chúng được cấu hình tại `HttpClient.Builder.followRedirects(...)` trước khi tạo client. Đây là API chính thức từ **Java 11** và vẫn được sử dụng ở các JDK hiện đại.

Mục tiêu bài học: nắm rõ chính sách của ba lựa chọn, cách cấu hình, cách kiểm tra request/response cuối, tác động của chuyển hướng tới POST/body, ranh giới HTTPS → HTTP, những rủi ro khi theo Location không tin cậy và cách kiểm thử trên server nội bộ.

## 2. Ba chính sách redirect

| Chính sách | Khi nhận redirect hợp lệ | HTTP → HTTP | HTTP → HTTPS | HTTPS → HTTPS | HTTPS → HTTP |
| --- | --- | --- | --- | --- | --- |
| `Redirect.NEVER` | **Không tự theo** | Không | Không | Không | Không |
| `Redirect.NORMAL` | Theo chuyển hướng, **trừ HTTPS → HTTP** | Có | Có | Có | **Chặn** |
| `Redirect.ALWAYS` | Cho phép theo chuyển hướng, kể cả hạ cấp giao thức | Có | Có | Có | **Có thể theo** |

Bảng mô tả **chính sách cho những redirect được HTTP client hỗ trợ**, không hứa rằng mọi response thuộc nhóm 3xx hoặc mọi `Location` đều dẫn tới request mới. Thiếu `Location`, URI không hợp lệ, đích có scheme không hỗ trợ, redirect loop, giới hạn redirect, lỗi mạng hoặc vấn đề bảo mật khác vẫn có thể khiến client dừng hoặc báo lỗi.

### 2.1. `NEVER` — không tự chuyển hướng

- Nếu server trả `301`/`302`/`307`/`308`, ứng dụng có thể nhận trực tiếp response 3xx cùng header `Location`.
- **Không tự gửi request mới** đến nơi mà server chỉ ra.
- Hữu ích khi muốn tự xác thực đích, kiểm soát miền được phép truy cập, xử lý redirect bằng logic nghiệp vụ, hoặc tránh gửi lại body/credentials ngoài dự kiến.
- Nếu ứng dụng cần theo redirect, chính ứng dụng phải kiểm tra và quyết định bước tiếp theo.

Đây là **mặc định** của `HttpClient.newHttpClient()` và `HttpClient.newBuilder().build()` nếu không gọi `followRedirects`.

### 2.2. `NORMAL` — theo redirect nhưng không hạ cấp HTTPS xuống HTTP

- Theo redirect HTTP → HTTP, HTTP → HTTPS và HTTPS → HTTPS nếu chuyển hướng thuộc loại được hỗ trợ.
- **Không** tự động theo redirect từ URL `https://...` đến `http://...`.
- Lý do: chuyển từ TLS sang HTTP không mã hóa có thể làm mất tính bí mật và toàn vẹn của dữ liệu khi trao đổi tiếp.
- Phù hợp cho nhiều ứng dụng muốn theo redirect thông thường **mà vẫn chặn hạ cấp bảo mật**.

**`NORMAL` không đồng nghĩa “chỉ chuyển trong cùng domain”**. Chuyển từ `https://api.example.com` sang `https://another.example.net` vẫn không phải HTTPS → HTTP, vì vậy không nên dùng `NORMAL` như một cơ chế giới hạn origin.

### 2.3. `ALWAYS` — cho phép theo cả HTTPS → HTTP

- Cho phép redirect theo chính sách của HTTP client **ngay cả khi URL HTTPS dẫn đến URL HTTP**.
- Có thể làm thông tin yêu cầu, URL, một số metadata hoặc dữ liệu nghiệp vụ truyền qua kết nối không được TLS bảo vệ.
- **Không nên dùng chỉ vì muốn “redirect hoạt động tối đa”** nếu có thể truyền dữ liệu nhạy cảm.
- Có giá trị trong môi trường thử nghiệm hoặc hệ thống có yêu cầu cụ thể và đã đánh giá rõ ràng rủi ro.

Tên `ALWAYS` **không phải bảo đảm mọi status 3xx sẽ được theo bằng mọi giá**. Nó không biến một URI không hợp lệ thành URI hợp lệ và không vô hiệu hóa các giới hạn/chính sách khác của client.

## 3. Cấu hình chính sách đúng trong Java 11

Cấu hình tại `HttpClient.Builder`:

```java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

Đây là **mảnh code** dùng được trong phương thức Java 11 với các import được chỉ ra.

Nếu muốn chặn:

```java
HttpClient strict = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Nếu thật sự cần cho phép cả HTTPS → HTTP (và chấp nhận rủi ro):

```java
HttpClient permissive = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.ALWAYS)
        .build();
```

Kiểm tra chính sách thực tế của client:

```java
System.out.println(client.followRedirects());    // NORMAL
System.out.println(strict.followRedirects());    // NEVER
System.out.println(permissive.followRedirects()); // ALWAYS
System.out.println(HttpClient.newHttpClient().followRedirects()); // NEVER
```

**Phân biệt chỗ đặt cấu hình:** `followRedirects(...)` là phương thức của **`HttpClient.Builder`**, không phải `HttpRequest.Builder`. Một client được tạo xong là đối tượng cấu hình bất biến; chính sách redirect áp dụng cho các request gửi **qua client đó**. Nếu cần hai chính sách khác nhau, hãy tạo hai client phù hợp hoặc dùng `NEVER` rồi tự xử lý redirect theo yêu cầu.

Java 11 hỗ trợ cả `send(...)` đồng bộ lẫn `sendAsync(...)` bất đồng bộ. Redirect policy thuộc client, nên các request đi qua hai API này tuân theo chính sách tương ứng; nó **không phải lời hứa** rằng thời điểm callback hoặc hành vi hoàn thành async sẽ giống hệt mọi lần chạy.

## 4. Điều gì xảy ra khi nhận 3xx và Location?

### 4.1. URI tương đối và URI tuyệt đối

Server có thể trả:

```http
Location: /v2/items
```

hoặc:

```http
Location: https://example.com/v2/items
```

`Location` tương đối được giải quyết dựa trên request URI đang nhận redirect. Ví dụ truy cập `http://127.0.0.1:8080/v1/items` và nhận `Location: /v2/items` thì đích là `http://127.0.0.1:8080/v2/items`.

Nếu chính sách là `NEVER`, ứng dụng nhận status và header rồi có thể xử lý thủ công:

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

if (response.statusCode() == 302) {
    String location = response.headers()
            .firstValue("Location")
            .orElseThrow(() -> new IllegalStateException(
                    "302 without Location"));
    URI proposedTarget = response.uri().resolve(location);
    // Kiểm tra scheme, host, port, quyền truy cập và chính sách nghiệp vụ
    // TRƯỚC KHI tạo request tới proposedTarget.
}
```

Đây là **mảnh mã**, cần biến `client`, `request`, import `HttpResponse`/`URI`, và xử lý `IOException`/`InterruptedException`. Mã **chưa gửi** request mới: chỉ tính URI đề xuất. Chỉ làm `URI.resolve(...)` chưa đủ để bảo vệ trước URL độc hại.

### 4.2. Không phải mọi 3xx đều có thể theo giống nhau

Những status thường có ý nghĩa chuyển hướng đến tài nguyên khác là `301`, `302`, `303`, `307`, `308`. Còn `304 Not Modified` là phản hồi **cache validation**, không phải lời yêu cầu phát request mới tới một URI khác.

Nếu không theo tự động (do `NEVER` hoặc chính sách không cho phép), ứng dụng nhận response 3xx để quyết định. Đừng viết logic “`300 <= status < 400` thì tự động GET tới Location” cho mọi status: có thể sai ý nghĩa HTTP hoặc thiếu header `Location`.

### 4.3. Vì sao response cuối có thể khác request ban đầu?

Khi theo redirect, `HttpResponse` mà ứng dụng nhận được thường là response **cuối cùng** của chuỗi. Các API để kiểm tra:

- `response.statusCode()`: mã trạng thái response hiện tại.
- `response.uri()`: URI mà response hiện tại được nhận từ đó.
- `response.request()`: đối tượng request tương ứng với response hiện tại; **có thể là request đã được tạo sau chuyển hướng**, không còn chính là request ban đầu.
- `response.previousResponse()`: `Optional<HttpResponse<T>>` lưu response trung gian trước đó khi có redirect hoặc authentication. Có thể đi ngược nhiều bước qua chuỗi này.

Ví dụ test thực tế ở mục 6 cho:

```text
NORMAL = 200, path = /done, previous = 302
```

Điều đó có nghĩa response cuối là 200 ở `/done`, và trước đó đã có response 302. Trong `previousResponse()`, **`body()` trả `null`** theo Javadoc, không nên coi đây là bản lưu đầy đủ body của từng bước trung gian.

Nếu chọn `NEVER`, response 302 là response trực tiếp đầu tiên và `previousResponse().isPresent()` thường là `false`.

## 5. Redirect có thể thay đổi HTTP method và body

**Đừng mặc định redirect là gửi nguyên xi cùng một request sang URL mới.** Method và body có thể thay đổi tùy mã trạng thái.

| Status | Ý nghĩa chung | Lưu ý với POST/body |
| --- | --- | --- |
| `301 Moved Permanently` | Tài nguyên được chuyển vĩnh viễn | Với Java HTTP Client, `POST` sẽ được đổi thành `GET` khi tự theo 301 |
| `302 Found` | Chuyển hướng tạm thời | Với Java HTTP Client, `POST` cũng sẽ được đổi thành `GET` khi tự theo 302 |
| `303 See Other` | Hướng tới tài nguyên để truy xuất kết quả | Theo ngữ nghĩa HTTP, thường lấy đích bằng `GET` (hoặc HEAD nếu thích hợp) |
| `307 Temporary Redirect` | Chuyển hướng tạm mà **giữ method** | `POST`/body phải được giữ khi tự theo |
| `308 Permanent Redirect` | Chuyển hướng vĩnh viễn mà **giữ method** | `POST`/body phải được giữ khi tự theo |

Javadoc của `HttpClient.Redirect` trên Java 11 nêu rõ: **301/302 làm POST trở thành GET** khi redirect tự động. Đây là một điểm rất quan trọng nếu API có hành vi thay đổi trạng thái server.

Chương trình thực ở mục 6 chứng minh:

```text
POST 302 = GET:
POST 307 = POST:payload
```

Với 302, server đích nhận `GET` và không còn payload ban đầu. Với 307, server đích vẫn nhận `POST` cùng body `payload`.

### 5.1. BodyPublisher phải có khả năng phát lại

Nếu server trả 307/308 và client tự theo redirect, nó có thể cần gửi **cùng body thêm một lần** tới URL mới. Khi đó `HttpRequest.BodyPublisher` phải hỗ trợ subscription mới và phát lại cùng byte.

Những nguồn thường dễ tái phát khi dữ liệu được giữ ổn định:
- `BodyPublishers.ofString(text)`.
- `BodyPublishers.ofByteArray(bytes)`.
- File snapshot không bị thay đổi trong lúc gửi.

Với `BodyPublishers.ofInputStream(supplier)`, supplier phải **mở InputStream mới từ đầu** cho mỗi lần phát lại. Nếu trả về cùng stream đã tiêu thụ hoặc dùng nguồn dữ liệu live thay đổi, redirect có thể lỗi hoặc gửi nội dung không tương đương.

**Khả năng phát lại body** chỉ giải quyết bài toán kỹ thuật. Nó **không biến các thao tác POST có tác dụng phụ thành idempotent**. Client phải hiểu API nghiệp vụ, có thể cần server-side idempotency key hoặc từ chối tự động redirect sang origin khác.

### 5.2. Đừng xem 301/302 là cách giữ nguyên POST

Nếu đang tích hợp API tạo đơn hàng, thanh toán, ghi dữ liệu hoặc upload có body quan trọng, không phụ thuộc vào chuyển hướng 301/302 để giữ method/body. Server thường nên dùng 307/308 nếu muốn giữ nguyên yêu cầu. Phía client vẫn phải kiểm tra chính sách bảo mật, đích mới và khả năng replay.

## 6. Chương trình độc lập Java 11: kiểm thử NEVER, NORMAL, ALWAYS và POST

Ví dụ này dùng HTTP server **loopback** được cung cấp sẵn bởi mô-đun JDK `jdk.httpserver`. Nó **không gọi Internet** và không cần thư viện ngoài JDK. Đường dẫn:

- `/start` trả `302 Location: /done`.
- `/done` trả `200 DONE`.
- `/post302` trả 302 tới `/echo`.
- `/post307` trả 307 tới `/echo`.
- `/echo` phản hồi tên method và body nhận được.

Mã chỉ sử dụng HTTP nội bộ. Nó kiểm chứng **NEVER/NORMAL/ALWAYS trên HTTP → HTTP** và **method/body sau 302/307**. Nó **không** giả vờ kiểm chứng HTTPS → HTTP trên loopback không có TLS; khác biệt đó lấy từ hợp đồng Javadoc.

Tạo file **`RedirectPolicyDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

public class RedirectPolicyDemo {
    private static void redirect(com.sun.net.httpserver.HttpExchange e,
                                 int status, String location) throws IOException {
        e.getRequestBody().readAllBytes();
        e.getResponseHeaders().set("Location", location);
        e.sendResponseHeaders(status, -1);
        e.close();
    }

    private static void text(com.sun.net.httpserver.HttpExchange e,
                             String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        e.sendResponseHeaders(200, bytes.length);
        try (java.io.OutputStream out = e.getResponseBody()) {
            out.write(bytes);
        } finally {
            e.close();
        }
    }

    private static HttpClient create(HttpClient.Redirect redirect) {
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .followRedirects(redirect)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    private static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5)).GET().build();
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicInteger hits = new AtomicInteger();

        server.createContext("/start", e -> {
            hits.incrementAndGet();
            redirect(e, 302, "/done");
        });
        server.createContext("/done", e -> {
            hits.incrementAndGet();
            text(e, "DONE");
        });
        server.createContext("/post302", e -> redirect(e, 302, "/echo"));
        server.createContext("/post307", e -> redirect(e, 307, "/echo"));
        server.createContext("/echo", e -> {
            String incoming = new String(
                    e.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            text(e, e.getRequestMethod() + ":" + incoming);
        });
        server.start();

        try {
            URI root = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());

            HttpClient defaultClient = HttpClient.newHttpClient();
            check(defaultClient.followRedirects() == HttpClient.Redirect.NEVER,
                    "default redirect must be NEVER");
            System.out.println("default = " + defaultClient.followRedirects());

            HttpClient never = create(HttpClient.Redirect.NEVER);
            HttpResponse<String> rNever = never.send(
                    get(root.resolve("/start")),
                    HttpResponse.BodyHandlers.ofString());

            check(rNever.statusCode() == 302
                    && rNever.headers().firstValue("Location")
                            .orElse("").equals("/done")
                    && rNever.previousResponse().isEmpty(),
                    "never must return initial 302");
            System.out.println("NEVER = " + rNever.statusCode()
                    + ", previous = "
                    + rNever.previousResponse().isPresent());

            HttpClient normal = create(HttpClient.Redirect.NORMAL);
            HttpResponse<String> rNormal = normal.send(
                    get(root.resolve("/start")),
                    HttpResponse.BodyHandlers.ofString());

            check(rNormal.statusCode() == 200
                    && rNormal.uri().getPath().equals("/done")
                    && rNormal.body().equals("DONE")
                    && rNormal.previousResponse().isPresent()
                    && rNormal.previousResponse().get().statusCode() == 302,
                    "normal must follow 302");
            System.out.println("NORMAL = " + rNormal.statusCode()
                    + ", path = " + rNormal.uri().getPath()
                    + ", previous = "
                    + rNormal.previousResponse().get().statusCode());

            HttpClient always = create(HttpClient.Redirect.ALWAYS);
            HttpResponse<String> rAlways = always.send(
                    get(root.resolve("/start")),
                    HttpResponse.BodyHandlers.ofString());

            check(rAlways.statusCode() == 200
                    && rAlways.uri().getPath().equals("/done"),
                    "always must follow");
            System.out.println("ALWAYS = " + rAlways.statusCode()
                    + ", path = " + rAlways.uri().getPath());

            HttpRequest post302 = HttpRequest.newBuilder(
                    root.resolve("/post302"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofString("payload"))
                    .build();

            HttpResponse<String> r302 = normal.send(
                    post302, HttpResponse.BodyHandlers.ofString());
            check(r302.statusCode() == 200
                    && r302.body().equals("GET:"),
                    "POST with 302 expected GET without payload");
            System.out.println("POST 302 = " + r302.body());

            HttpRequest post307 = HttpRequest.newBuilder(
                    root.resolve("/post307"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofString("payload"))
                    .build();

            HttpResponse<String> r307 = normal.send(
                    post307, HttpResponse.BodyHandlers.ofString());
            check(r307.statusCode() == 200
                    && r307.body().equals("POST:payload"),
                    "POST with 307 expected POST and payload");
            System.out.println("POST 307 = " + r307.body());

            check(hits.get() == 5, "start/done requests must be 5");
            System.out.println("get requests = " + hits.get());
            System.out.println("ALL TESTS PASSED");
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file, với JDK 11 trở lên:

```bash
javac --release 11 --add-modules jdk.httpserver RedirectPolicyDemo.java
java --add-modules jdk.httpserver RedirectPolicyDemo
```

**Đầu ra đã kiểm chứng khi biên dịch `--release 11`:**

```text
default = NEVER
NEVER = 302, previous = false
NORMAL = 200, path = /done, previous = 302
ALWAYS = 200, path = /done
POST 302 = GET:
POST 307 = POST:payload
get requests = 5
ALL TESTS PASSED
```

Giải thích:

1. `HttpClient.newHttpClient()` có `followRedirects() == NEVER`.
2. `NEVER` giữ nguyên `302`, để caller có thể đọc `Location`; không tạo response trước đó.
3. `NORMAL` theo relative Location `/done`, nhận response `200 DONE` và `previousResponse()` chứa `302`.
4. `ALWAYS` cũng theo chuyển hướng HTTP → HTTP; khác biệt về HTTPS → HTTP không thể kiểm chứng bằng một HTTP server thuần không dùng TLS.
5. Với `302`, POST được đổi sang GET theo Javadoc và đầu đích nhận body rỗng.
6. Với `307`, POST được giữ nguyên và body `payload` đến đúng đích.
7. Bộ đếm `hits` đo số lượt ghé `/start` và `/done` cho ba chính sách: NEVER có một lượt, NORMAL và ALWAYS mỗi loại có hai lượt ⇒ tổng `5`. Đây là kiểm thử phản hồi thực, không chỉ so chuỗi cấu hình.

Mọi request tới `127.0.0.1` và server dùng port do hệ điều hành cấp. Nếu môi trường hạn chế mở cổng loopback thì chạy thử có thể bị từ chối bởi sandbox/firewall; không nên thay bằng một server thật có dữ liệu nhạy cảm chỉ để làm bài tập.

## 7. NORMAL, ALWAYS và rủi ro bảo mật

### 7.1. HTTPS → HTTP downgrade

Đây là khác biệt chính giữa `NORMAL` và `ALWAYS`:

```text
https://secure.example/path
    |
    | HTTP 302 Location: http://other.example/path
    v
Redirect.NORMAL  : không tự theo HTTP đích
Redirect.ALWAYS  : cho phép xem xét tự theo HTTP đích
Redirect.NEVER   : trả 302 để ứng dụng tự quyết định
```

Khi tự theo sang HTTP, dữ liệu qua chặng mới có thể bị quan sát/thay đổi trên mạng. Nếu request có token, URL chứa thông tin nhạy cảm, body chứa dữ liệu riêng tư hoặc dữ liệu xác thực, rủi ro càng đáng chú ý.

**Không được giả định** mọi header nhạy cảm chắc chắn sẽ được chuyển tiếp hay chắc chắn sẽ bị bỏ ở mọi redirect. Quy tắc giữ/bỏ các header như `Authorization`, `Cookie` hoặc header custom có thể phụ thuộc implementation, chính sách xác thực và redirect target. Ứng dụng cần đánh giá và kiểm soát **đích cuối**, không lấy `NORMAL` làm giải pháp duy nhất.

### 7.2. NORMAL không có nghĩa cùng origin

Origin về cơ bản được xác định bởi `scheme + host + port`. Một redirect từ `https://api.example.com` sang `https://another.example.net` vẫn là HTTPS → HTTPS nên **không bị `NORMAL` chặn chỉ vì đổi host**.

Khi URL ban đầu hoặc response từ server có thể bị bên ngoài kiểm soát, redirect đến đích nội bộ, địa chỉ metadata service, loopback hay vùng mạng riêng có thể tạo rủi ro **SSRF**. Cân nhắc `NEVER` và tự kiểm tra redirect với allowlist host/origin, xử lý DNS/IP và giới hạn số bước. Chỉ so chuỗi host một lần không đủ cho mọi hệ thống có rủi ro cao; phân giải DNS, proxy và địa chỉ thực tế cũng cần kiểm soát thích hợp.

### 7.3. Redirect loop, số hop, timeout và tài nguyên

Một server có thể trả vòng lặp:

```text
/a → /b → /a → /b ...
```

Không phụ thuộc vào một con số redirect tối đa cố định như một **hợp đồng ổn định** giữa mọi bản JDK. HTTP Client có cơ chế giới hạn/chống lặp theo triển khai, nhưng ứng dụng vẫn phải có deadline, log số bước và điều kiện dừng phù hợp.

`HttpClient.Builder.connectTimeout(Duration)` giới hạn thời gian **thiết lập kết nối mới**, không phải giới hạn toàn bộ chuỗi redirect. `HttpRequest.Builder.timeout(Duration)` áp dụng hạn mức request theo API, nhưng đừng dùng riêng nó làm chính sách ngân sách tổng cộng cho một nghiệp vụ gồm nhiều lần gửi thủ công, retry hay xử lý logic tùy biến. Cần quản lý deadline tổng ở tầng ứng dụng nếu quan trọng.

**Một redirect có thể khiến client gửi thêm request**, vì vậy số lượt request, lượng dữ liệu body, phương thức HTTP và đích mạng phải nằm trong mô hình bảo mật và kiểm soát tài nguyên.

## 8. Khi nào nên dùng từng chính sách?

| Nhu cầu | Gợi ý | Vì sao |
| --- | --- | --- |
| Tích hợp API cần kiểm soát chính xác đích, method, body, headers | `NEVER` | Caller xét và chấp thuận từng redirect |
| Truy vấn tài nguyên công khai có redirect thông thường, vẫn muốn tránh HTTPS → HTTP | `NORMAL` | Theo redirect tiện lợi nhưng ngăn downgrade |
| Môi trường test hoặc hệ thống có yêu cầu theo cả HTTPS → HTTP đã đánh giá rủi ro | `ALWAYS` | Cho phép cả downgrade, nhưng không phải mặc định an toàn |
| Gửi POST thanh toán, upload hoặc dữ liệu nhạy cảm | Thường ưu tiên `NEVER` hoặc policy rất chặt | Chặn redirect tự phát sang đích mới, giảm nguy cơ đổi method/đích |
| URL từ người dùng/ngoài hệ thống, có nguy cơ truy cập nội bộ | `NEVER` cộng kiểm soát origin và mạng | Chỉ chính sách redirect không đủ chống SSRF |

**Các gợi ý không phải quy tắc cứng:** nếu API đối tác có hợp đồng redirect 307/308 và vùng đích đáng tin, `NORMAL` có thể hợp lý. Quyết định phải dựa trên mục tiêu nghiệp vụ và ranh giới tin cậy.

## 9. Tự xử lý redirect với NEVER: checklist bắt buộc

Khi cần kiểm soát từng hop, đặt `NEVER`, nhận response 3xx và kiểm tra `Location` trước khi tạo request mới.

Nên kiểm tra ít nhất:

1. Status có thực sự thuộc tập redirect cần xử lý (ví dụ 301/302/303/307/308) không? `304` không phải redirect tới nơi khác.
2. `Location` có tồn tại và phân tích thành URI hợp lệ không? Nếu là relative URI thì giải theo URI hiện tại.
3. `scheme` có thuộc `http`/`https` theo chính sách ứng dụng không? Có cấm HTTPS → HTTP không?
4. Host/port/origin có trong allowlist không? Có chuyển sang loopback, mạng riêng hoặc vùng nội bộ không?
5. Số hop có vượt ngưỡng không? Có bị vòng lặp giữa các URI không?
6. HTTP method/body phải thay theo RFC và hợp đồng dịch vụ nào? Body có tái phát được không?
7. Header xác thực, cookie, token, thông tin riêng tư cần giữ hay bỏ? Không chuyển tiếp mù quáng.
8. Thời gian tổng, response body trung gian và tài nguyên mạng có được xử lý hợp lý không?
9. Có log an toàn trạng thái và URI đã được redacted không? Không đưa credential/query nhạy cảm vào log.

**Không áp dụng đơn giản `return client.send(HttpRequest.newBuilder(response.uri().resolve(location)).build(), ...)` cho Location đến từ bên ngoài mà không kiểm tra**. Đây là lỗi nguy hiểm vì có thể đổi origin hoặc phá vỡ ngữ nghĩa method/body.

`NEVER` cho bạn quyền quyết định, **không tự làm code thủ công an toàn**. Với sản phẩm cần chống SSRF mạnh, phải kết hợp chính sách mạng, kiểm soát DNS/proxy và kiểm tra địa chỉ kết nối thực tế, không chỉ kiểm tra chuỗi URL.

## 10. Các lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| Client trả 302 thay vì 200 cuối | Mặc định là `Redirect.NEVER` | Chọn `NORMAL` nếu muốn tự theo và phù hợp bảo mật |
| Gọi `request.followRedirects(...)` không biên dịch | Redirect policy ở `HttpClient.Builder`, không phải Request Builder | Dùng `HttpClient.newBuilder().followRedirects(...)` |
| Dùng NORMAL nhưng HTTPS → HTTP không được theo | `NORMAL` cố ý chặn downgrade | Giữ bảo mật; chỉ dùng `ALWAYS` khi đã chấp nhận rủi ro |
| Tưởng NORMAL chỉ theo cùng host | `NORMAL` chỉ chặn HTTPS → HTTP | Tự kiểm soát allowlist/origin nếu cần |
| POST sau 302 biến thành GET | JDK tự đổi POST → GET trên 301/302 | Dùng hợp đồng server phù hợp, thường là 307/308 nếu cần giữ method |
| POST 307 không gửi lại body thành công | BodyPublisher không phát lại được | Dùng nguồn replayable (String/byte[]/stream mới) |
| Test chỉ kiểm tra `statusCode`, không biết redirect qua đâu | Không đọc `uri` hay `previousResponse` | Kiểm tra response cuối và chuỗi trung gian |
| Nghĩ 3xx luôn có Location hợp lệ | Status 3xx có nhiều ý nghĩa; header có thể thiếu | Phân loại status và validate Location |
| Tin rằng ALWAYS bảo đảm theo mọi 3xx | Vẫn có định dạng URI/giới hạn/lỗi mạng | Xử lý các response không được theo và các exception |
| Theo URL ngoài rồi gửi token nhạy cảm | Tự động đổi host/transport có thể vượt ranh giới tin cậy | Hạn chế redirect, validate đích và xử lý header cẩn thận |
| Infinite redirect loop hoặc quá nhiều hops | Server cấu hình vòng lặp; ứng dụng thủ công quên giới hạn | Đặt giới hạn hop và deadline, phát hiện loop |
| Xem previousResponse body như response gốc đầy đủ | Javadoc trả `null` cho body của previous response | Chỉ dựa vào status/headers/URI của response trung gian |
| Nhầm HTTP/2 với redirect policy | Chọn version không quyết định NEVER/NORMAL/ALWAYS | Cấu hình hai thuộc tính riêng trên client |

## 11. Câu hỏi tự kiểm tra

**1.** Tạo `HttpClient.newHttpClient()` rồi gửi GET tới URL trả `302 Location: /next`. Nếu không chỉnh gì, client tự theo không?  
**Đáp án:** Không. Mặc định `Redirect.NEVER`, ứng dụng nhận response 302.

**2.** Client có `NORMAL`, server HTTPS trả `302 Location: http://example.com/x`. Client có tự theo không?  
**Đáp án:** Không, vì `NORMAL` chặn HTTPS → HTTP.

**3.** Client có `NORMAL`, server `https://a.example` trả `Location: https://b.example`. Có chắc bị chặn vì khác host không?  
**Đáp án:** Không. `NORMAL` không phải same-origin policy; ứng dụng phải kiểm soát đích riêng nếu cần.

**4.** Client có `ALWAYS`. Điều đó có bảo đảm mọi 3xx tự động theo không?  
**Đáp án:** Không. Chỉ cho phép redirect theo chính sách; status, Location, scheme và giới hạn khác vẫn quan trọng.

**5.** Khi POST nhận 302 rồi client tự theo, request đích thường dùng method gì trong Java 11?  
**Đáp án:** `GET`; Java HTTP Client đổi POST thành GET cho 301/302. Nếu muốn giữ method và body, server nên dùng 307/308 theo hợp đồng API.

**6.** Làm sao biết response cuối đi qua redirect 302?  
**Đáp án:** Xem `response.uri()`/`response.request()` và `response.previousResponse()`; lần trung gian có status 302, body của previous response thường là `null` theo Javadoc.

**7.** Vì sao `ofInputStream(() -> sharedStream)` có thể lỗi khi theo redirect 307?  
**Đáp án:** Redirect cần phát lại body; sharedStream đã tiêu thụ ở lượt đầu. Supplier phải tạo stream mới từ đầu với cùng byte.

**8.** Muốn chỉ theo URL cùng miền đã tin cậy, có nên chỉ dùng `NORMAL` không?  
**Đáp án:** Không. `NORMAL` chỉ chặn downgrade; dùng `NEVER` và kiểm tra Location/allowlist trước khi gửi mới, cùng các biện pháp mạng cần thiết.

## 12. Tổng kết

Java 11 có ba lựa chọn cấu hình tự động theo redirect tại `HttpClient.Builder.followRedirects(...)`:

- **`NEVER`:** **mặc định**, trả response 3xx để caller tự quyết định, không tự gửi tiếp.
- **`NORMAL`:** theo redirect được hỗ trợ, **ngoại trừ HTTPS → HTTP**, phù hợp nhiều luồng cần tiện lợi mà tránh downgrade.
- **`ALWAYS`:** cho phép cả HTTPS → HTTP, cần hiểu rõ nguy cơ bảo mật.

Khi theo redirect, kiểm tra thêm **status code, Location, HTTP method/body**, khả năng phát lại `BodyPublisher` và response thực sự qua `uri()`/`previousResponse()`. **Không có chính sách nào tự bảo đảm cùng origin, chống SSRF hay đảm bảo một POST có thể lặp an toàn.**

### Tài liệu chính thức

- [Java SE 11 — HttpClient.Redirect: NEVER, NORMAL, ALWAYS và chuyển POST 301/302 thành GET](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html)
- [Java SE 11 — HttpClient.Builder.followRedirects, mặc định NEVER](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 11 — HttpResponse.uri, request, previousResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [Java SE 11 — HttpRequest.BodyPublisher và khả năng phát lại](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [Java SE 25 — HttpClient.Redirect, API hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html)
- [RFC 9110 — HTTP Semantics, mục 15.4: Redirection 3xx](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4)
