# Gửi đồng bộ bằng HttpClient.send trong Java 11+

> **Chủ đề:** HTTP Client — gửi yêu cầu HTTP đồng bộ bằng phương thức `send`. API `java.net.http.HttpClient` trở thành API chuẩn của Java từ Java 11 và vẫn được hỗ trợ trên các JDK hiện đại. Bài học dùng những cách gọi ổn định, tương thích Java 11; các ví dụ khởi chạy được trên JDK 17+ mà không cần thư viện HTTP bên ngoài.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Tạo `HttpClient` và `HttpRequest`, gửi GET/POST bằng `HttpClient.send(...)` và nhận `HttpResponse<T>`.
2. Giải thích chính xác “**đồng bộ**” là gì: luồng gọi `send` chờ cho tới khi có kết quả hoặc lỗi, còn thời điểm body được tiêu thụ hết **phụ thuộc `BodyHandler`**.
3. Đọc mã trạng thái, header, body, URI và phiên bản HTTP của phản hồi; phân biệt HTTP `4xx/5xx` với lỗi mạng/timeout.
4. Chọn `BodyHandlers.ofString`, `ofByteArray`, `ofFile`, `ofInputStream` hoặc `discarding` theo nhu cầu, đặc biệt với dữ liệu lớn.
5. Thiết lập `connectTimeout` và timeout của mỗi `HttpRequest`; xử lý `IOException`, `HttpTimeoutException` và `InterruptedException` đúng cách.
6. Viết và chạy một chương trình kiểm thử cục bộ cho cả kết quả `200` và `404`.
7. Nhận diện những lỗi thiết kế thường gặp: mặc định không theo redirect, không bảo đảm mọi status là thành công, không vô hạn tích lũy body vào RAM, không tự động retry POST.

## 2. Gửi đồng bộ có nghĩa là gì?

`HttpClient` nằm trong module chuẩn `java.net.http`. Phương thức chính:

~~~java
<T> HttpResponse<T> send(
    HttpRequest request,
    HttpResponse.BodyHandler<T> responseBodyHandler
) throws IOException, InterruptedException;
~~~

Đây là **chữ ký API rút gọn**, không phải tệp Java có thể chạy độc lập. `T` là **kiểu dữ liệu body phản hồi** do `BodyHandler<T>` quyết định.

Luồng xử lý điển hình:

~~~text
Thread gọi
   |
   v
Tạo HttpClient (có thể tái sử dụng)
   |
   v
Tạo HttpRequest (URI, phương thức, headers, timeout, body...)
   |
   v
client.send(request, BodyHandler<T>)   <-- luồng gọi chờ ở đây
   |
   +--> kết nối / gửi request / nhận status + headers / xử lý body
   |
   +--> Thành công về I/O: trả HttpResponse<T>
   |                       statusCode() có thể là 200, 301, 404, 500...
   |
   +--> Lỗi I/O hoặc timeout: IOException và các lớp con
   |
   +--> Bị ngắt: InterruptedException
   v
Chương trình kiểm tra status, body, xử lý nghiệp vụ
~~~

**Điểm quan trọng:**

- **Đồng bộ** nghĩa là **luồng đang gọi `send` sẽ chặn (block)** tới lúc kết quả phản hồi được cung cấp hoặc có ngoại lệ. Nó không có nghĩa toàn bộ ứng dụng hay JVM “đứng yên”.
- HTTP client có thể dùng I/O và các tác vụ nội bộ bất đồng bộ, nhưng **API `send` vẫn chặn người gọi**.
- Với `BodyHandlers.ofString()` hoặc `ofByteArray()`, khi `send` trả về thì body đã được tiêu thụ và chuyển thành `String`/`byte[]`.
- Với `BodyHandlers.ofInputStream()`, `send` có thể trả về ngay sau khi đã nhận đủ status và headers; body còn đang đến, và người gọi phải **đọc/đóng `InputStream`**. Vì vậy không nói chung rằng “`send` luôn tải xong toàn bộ body trước khi trả về”.
- `send` khác `sendAsync`: `sendAsync` trả `CompletableFuture<HttpResponse<T>>` ngay để xử lý kết quả sau, còn `send` trả trực tiếp `HttpResponse<T>` hoặc ném ngoại lệ.
- Cần đặt timeout có chủ đích. Nếu chờ I/O trên một thread xử lý request của server, thread đó có thể bị chiếm trong thời gian chờ phản hồi ngoài.

## 3. Ba đối tượng cần hiểu: Client, Request và Response

### 3.1. HttpClient — cấu hình dùng chung và tái sử dụng

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

Đây là **đoạn minh họa** bên trong một method; cần import `java.net.http.HttpClient` và `java.time.Duration`.

- `HttpClient.newBuilder()` cho phép cấu hình client trước khi tạo; `HttpClient.newHttpClient()` tạo client với các thiết lập mặc định.
- `connectTimeout` kiểm soát thời gian **thiết lập kết nối mới**. Khi có kết nối có thể tái sử dụng, cấu hình này có thể không tác động đến request đó.
- `followRedirects` quyết định có theo mã chuyển hướng HTTP hay không. **Mặc định là `NEVER`**; ở đây ghi rõ để người đọc thấy chính sách.
- `HttpClient` sau khi `build()` có cấu hình bất biến. Một client thường được **tái sử dụng cho nhiều request** để có lợi cho kết nối và tài nguyên, thay vì tạo client mới mỗi lần gửi.
- HTTP/2 có thể được ưu tiên tùy cấu hình/client, nhưng phiên bản giao thức thực tế chịu ảnh hưởng server và kết nối. Đọc `response.version()` nếu ứng dụng cần biết kết nối đã dùng HTTP/1.1 hay HTTP/2.

**Vòng đời phiên bản:** Java 11 không có bộ phương thức đóng/shutdown của `HttpClient` như các JDK mới; từ Java 21, API có thêm cơ chế đóng/tắt client. Mã tương thích Java 11 trong bài không gọi `client.close()`. Với body dạng stream, việc đóng/tiêu thụ stream vẫn bắt buộc dù client được tái sử dụng.

### 3.2. HttpRequest — một yêu cầu cụ thể

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "text/plain")
        .GET()
        .build();
~~~

Đây là **đoạn minh họa**, không cam kết `example.com` luôn trả nội dung nhất định và không cần gửi request thật để học cấu trúc.

- `uri(...)` chỉ định địa chỉ yêu cầu, thông thường dùng `http` hoặc `https`.
- `timeout(...)` là timeout cho **request**; khác với `connectTimeout` của client.
- `header(...)` thêm header theo nhu cầu; `setHeader(...)` thay giá trị hiện có của cùng tên header trong builder.
- `GET()` chọn phương thức GET, không có request body. Nếu không gọi phương thức cụ thể, một builder mới thường tạo GET.
- `build()` tạo một `HttpRequest` có thể gửi. Với GET thông thường, có thể tái dùng cùng request; với request body dạng stream, khả năng gửi lại còn phụ thuộc `BodyPublisher`.

### 3.3. HttpResponse<T> — kết quả HTTP

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
);

int code = response.statusCode();
String body = response.body();
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("(không có)");
URI actualUri = response.uri();
HttpClient.Version protocol = response.version();
~~~

Đây là **đoạn minh họa bên trong method khai báo `throws IOException, InterruptedException`**, với `client` và `request` đã được tạo.

Các thuộc tính cần dùng:

| Phương thức | Kết quả |
| --- | --- |
| `response.statusCode()` | HTTP status dạng `int` (ví dụ 200, 201, 301, 404, 500). |
| `response.headers()` | `HttpHeaders` chứa các response header đã nhận; `firstValue(name)` trả `Optional<String>`. |
| `response.body()` | `T` do `BodyHandler<T>` quyết định: `String`, `byte[]`, `Path`, `InputStream`, `Void`... |
| `response.uri()` | URI thực tế của phản hồi, có thể khác URI gốc nếu client theo redirect. |
| `response.version()` | Phiên bản HTTP thực sự sử dụng. |
| `response.request()` | `HttpRequest` tương ứng với phản hồi. |
| `response.previousResponse()` | Phản hồi trung gian trước đó nếu có (chẳng hạn do redirect/authentication), dưới dạng `Optional`. |

**Không đồng nhất “send không ném exception” với “nghiệp vụ thành công”.** Máy chủ trả `404` hoặc `500` vẫn là một phản hồi HTTP hợp lệ, nên `send` thường trả về `HttpResponse<T>`. Chính ứng dụng phải kiểm tra `statusCode()` và giải mã thông báo lỗi của API.

## 4. Chương trình Java 11+ hoàn chỉnh, tự kiểm tra không cần Internet

Ví dụ chạy một HTTP server **chỉ trên loopback** với cổng do hệ điều hành chọn, rồi dùng `HttpClient.send` để gửi hai GET đồng bộ. Nó chạy ngay cả khi không có kết nối Internet và không phụ thuộc status hay nội dung của dịch vụ bên ngoài.

> Phần server dùng `com.sun.net.httpserver.HttpServer` trong module JDK `jdk.httpserver` để làm **fixture kiểm thử**. Đây là API của JDK, không phải một phần của module `java.net.http`. Phần **client** dùng API Java SE 11 chuẩn. Với JDK đầy đủ, có thể chạy như bên dưới; nếu bản phân phối JDK đã rút gọn module này, cần cung cấp module `jdk.httpserver`.

Tạo tệp **`SynchronousSendDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class SynchronousSendDemo {
    public static void main(String[] args) throws Exception {
        // Dựng server cục bộ: /ok -> 200, đường dẫn khác -> 404.
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/", exchange -> {
            boolean ok = "/ok".equals(exchange.getRequestURI().getPath());
            String message = ok ? "Xin chao Java 11" : "Not found";
            int code = ok ? 200 : 404;

            byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(code, bytes.length);

            try (var body = exchange.getResponseBody()) {
                body.write(bytes);
            }
        });

        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest okRequest = HttpRequest.newBuilder(
                    URI.create(base + "/ok"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> ok = client.send(
                    okRequest,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)
            );
            System.out.println("ok.status=" + ok.statusCode());
            System.out.println("ok.body=" + ok.body());

            HttpRequest missing = HttpRequest.newBuilder(
                    URI.create(base + "/missing"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> notFound = client.send(
                    missing,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)
            );
            System.out.println(
                    "missing.status=" + notFound.statusCode());
            System.out.println(
                    "missing.body=" + notFound.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 11 trở lên:

~~~bash
javac SynchronousSendDemo.java
java SynchronousSendDemo
~~~

**Stdout của hai phản hồi (đã kiểm tra trên JDK):**

~~~text
ok.status=200
ok.body=Xin chao Java 11
missing.status=404
missing.body=Not found
~~~

Để ép module server trong một cấu hình module-path đã tối giản, có thể sử dụng `--add-modules jdk.httpserver` khi khởi chạy, nếu module đã được cài trong runtime.

### Giải thích kết quả

1. Server lắng nghe trên `127.0.0.1` (loopback), cổng `0` yêu cầu hệ điều hành cấp cổng khả dụng. Chương trình không in cổng ngẫu nhiên, vì vậy stdout ổn định.
2. Client xây request `/ok`, chờ bằng `send`, nhận `200` và body `Xin chao Java 11`.
3. Client dùng lại **cùng một `HttpClient`** cho request `/missing`; server trả `404`, còn `send` vẫn **trả phản hồi bình thường**. Không có `IOException` chỉ vì status là 404.
4. `BodyHandlers.ofString(StandardCharsets.UTF_8)` chuyển byte của body thành `String` theo UTF-8; phần server gửi đúng cùng encoding. `ofString` tích lũy nội dung trong bộ nhớ, thích hợp vì body thử nghiệm rất nhỏ.
5. `server.stop(0)` thực hiện cleanup server trong `finally` kể cả khi lời gọi client gặp lỗi. Chương trình dùng `throws Exception` để ví dụ chính gọn; ứng dụng sản xuất nên bắt các nhóm lỗi theo chính sách rõ ràng (mục 8).
6. `HttpClient.Version.HTTP_1_1` được chọn chỉ để fixture server nhỏ dễ tương thích. Ứng dụng thật có thể để client lựa chọn HTTP/2 theo điều kiện server.

**Phần liên quan trực tiếp đến bài:** cấu trúc `client.send(request, BodyHandlers.ofString(...))`, `response.statusCode()`, `response.body()`, chính sách timeout và xử lý mã trạng thái. Server cục bộ chỉ tạo dữ liệu có thể dự đoán để luyện tập.

## 5. Gửi GET trong ứng dụng thật: quy trình từng bước

Với URL do chương trình tin cậy xác định, mã GET cơ bản có dạng:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/health"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

if (response.statusCode() >= 200 && response.statusCode() < 300) {
    System.out.println(response.body());
} else {
    System.err.println("HTTP error: " + response.statusCode());
}
~~~

**Mã minh họa**: `https://api.example.com/health` là địa chỉ mẫu, không khẳng định endpoint này hoạt động. Đặt đoạn mã trong một method có `throws IOException, InterruptedException` hoặc khối xử lý ngoại lệ; import các kiểu tương ứng. Không có stdout cố định cho endpoint thực tế.

Ý nghĩa theo thứ tự:

1. Xác định **client** (thường được lưu và tái sử dụng trong service).
2. Tạo **request** với URI và timeout.
3. Chọn **BodyHandler** theo loại dữ liệu và kích thước dự kiến.
4. Gọi **send**; thread hiện tại chờ.
5. Kiểm **status HTTP** trước khi coi phản hồi là dữ liệu nghiệp vụ hợp lệ.
6. Nếu response JSON, đưa body vào parser có giới hạn kích thước/độ sâu phù hợp; `send` **không tự chuyển JSON thành object Java**.

Nếu API quy định `204 No Content` là thành công, không bắt buộc đòi body có nội dung. Nếu API trả `301/302/307/308` mà client chưa bật follow redirects, hãy xử lý chính sách redirect ở tầng ứng dụng.

## 6. Gửi POST đồng bộ với BodyPublishers

`HttpClient.send` không chỉ cho GET. Request có thể dùng POST/PUT/PATCH (qua `method`) và body được cung cấp qua `HttpRequest.BodyPublisher`.

Ví dụ POST JSON đơn giản:

~~~java
String json = "{\"name\":\"An\",\"active\":true}";

HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://api.example.com/users"))
        .timeout(Duration.ofSeconds(10))
        .header("Content-Type", "application/json; charset=UTF-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();

HttpResponse<String> response = client.send(
        post,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
int status = response.statusCode();
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập: cần một `HttpClient client`, import, xử lý ngoại lệ và endpoint có thật. Không có stdout cố định.

- `BodyPublishers.ofString(String, Charset)` mã hóa chuỗi thành byte. Nếu dùng overload không truyền charset, **UTF-8** là mặc định từ Java 11.
- `Content-Type` mô tả kiểu dữ liệu request. Đừng cho rằng `BodyPublishers.ofString` tự đặt `Content-Type: application/json`; header do ứng dụng tạo khi cần.
- `Accept` diễn tả loại response mong muốn, không quyết định chắc chắn body server trả về.
- POST có thể thay đổi dữ liệu trên server. **Không tự động retry** request khi `send` bị timeout: server có thể đã nhận/xử lý request dù client chưa có phản hồi. Khi cần retry, dùng quy tắc idempotency, idempotency key hoặc xác nhận trạng thái phía server theo đặc tả API.
- Xác thực `Authorization`/token phải do ứng dụng quản lý an toàn; không ghi token hoặc nguyên request chứa bí mật vào log.
- Nếu request body lớn, có thể dùng `BodyPublishers.ofFile`/`ofInputStream` phù hợp thay cho việc tạo toàn bộ body trong một `String`.

## 7. Chọn đúng BodyHandler và hiểu điều gì đã hoàn thành

Đối số thứ hai của `send` là **`HttpResponse.BodyHandler<T>`**. Nó định nghĩa cách xử lý các byte response và loại `T`.

| Handler | Kiểu `T` trong `HttpResponse<T>` | Phù hợp khi nào? | Chú ý tài nguyên |
| --- | --- | --- | --- |
| `BodyHandlers.ofString()` hoặc `ofString(charset)` | `String` | Body văn bản nhỏ, JSON nhỏ, text | Có thể giữ cả body trong RAM; khi `send` trả về, `String` hoàn chỉnh |
| `BodyHandlers.ofByteArray()` | `byte[]` | Body nhị phân nhỏ cần xử lý trong RAM | Đừng dùng cho nội dung không tin cậy có kích thước vô hạn |
| `BodyHandlers.ofFile(path)` | `Path` | Lưu response vào tệp | Dọn tệp khi lỗi/không còn cần; kiểm path và quyền ghi |
| `BodyHandlers.ofInputStream()` | `InputStream` | Stream body lớn hoặc cần giới hạn byte khi đọc | **Phải đọc hết hoặc đóng** stream; `send` có thể trả trước khi body nhận xong |
| `BodyHandlers.discarding()` | `Void` | Chỉ cần status/headers, không cần body | Body được tiêu thụ rồi bỏ, tránh giữ nội dung |
| `BodyHandlers.ofLines()` | `Stream<String>` | Xử lý văn bản theo dòng | Cần đóng/tiêu thụ stream để giải phóng tài nguyên |

**Cẩn thận:** `ofString()` không truyền charset chọn charset từ `Content-Type` nếu hợp lệ; nếu thiếu hoặc không hỗ trợ thì dùng UTF-8. `ofString(StandardCharsets.UTF_8)` **ép UTF-8** cho body. Hãy chọn theo hợp đồng API bên kia, không suy đoán charset dựa trên tên file.

Các BodyHandler có sẵn **không tự phân biệt status thành công/thất bại** để bỏ body. Kể cả response `404`, `BodyHandlers.ofString` vẫn nhận body lỗi như một chuỗi. Có thể xây `BodyHandler` tùy chỉnh để lựa chọn cách xử lý dựa vào status và headers nếu hệ thống cần.

### BodyHandlers.ofInputStream và giới hạn bộ nhớ

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] prefix = body.readNBytes(1024);
    // Xử lý prefix; nếu chưa đọc hết, đóng stream sẽ kết thúc việc dùng body.
}
~~~

Đoạn mã **minh họa trong method**, cần import `InputStream` và các đối tượng `client`, `request`.

- Body streaming **không có nghĩa** `send` đã nhận toàn bộ body. Đọc `body` có thể tiếp tục chặn khi dữ liệu đến.
- `readNBytes(1024)` chỉ đọc **tối đa** 1.024 byte, không bảo đảm đã nhận hết response. Nếu cần từ chối payload vượt giới hạn 1.024 byte, phải kiểm byte tiếp theo (`limit + 1`) hoặc đếm dữ liệu khi stream; tránh lặng lẽ coi prefix là toàn body.
- `try-with-resources` đóng stream dù xảy ra exception. Việc đóng sớm có thể ảnh hưởng khả năng tái sử dụng kết nối; đó vẫn là cách đúng khi không muốn nhận phần còn lại.
- Với dữ liệu rất lớn, dùng streaming và bộ đếm byte, giới hạn tổng dữ liệu, timeout thích hợp và nơi lưu trữ có giới hạn. Đọc tất cả bằng `ofString()`/`ofByteArray()` có thể làm tăng heap.

### Lưu body vào file

~~~java
Path destination = Path.of("download.bin");
HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(destination));
~~~

Đây là **đoạn minh họa**. Body được handler ghi ra file trước khi `send` trả phản hồi hoàn tất, nhưng **không** có nghĩa file chắc chắn hợp lệ về nghiệp vụ: cần kiểm status, độ dài, định dạng, hash/chữ ký nếu liên quan và chính sách xóa file khi lỗi. Có thể ghi file của phản hồi lỗi `404` vào đích nếu không kiểm/điều khiển handler.

## 8. Timeout và ngoại lệ: phân biệt rõ nguyên nhân

Mã đồng bộ cần đường xử lý lỗi rõ ràng vì lời gọi có thể chờ mạng.

### 8.1. Hai timeout chính

| Thiết lập | Vị trí | Ý nghĩa |
| --- | --- | --- |
| `connectTimeout(Duration)` | `HttpClient.newBuilder()` | Giới hạn thiết lập **kết nối mới**; có thể ném `HttpConnectTimeoutException` khi hết hạn |
| `timeout(Duration)` | `HttpRequest.newBuilder()` | Giới hạn thời gian để nhận phản hồi theo hợp đồng request; khi hết hạn có thể ném `HttpTimeoutException` |

Cả hai yêu cầu `Duration` **dương**. `connectTimeout` không có tác dụng với kết nối đang được tái sử dụng; nó không thay cho request timeout. Nếu không cấu hình request timeout, ứng dụng không nên giả định có deadline hữu hạn cho yêu cầu.

Với `BodyHandler` dạng stream, thời gian đọc body tiếp theo còn phụ thuộc chế độ streaming và socket/tầng vận hành; không nên dùng hai timeout trên để khẳng định có bảo đảm cứng cho toàn bộ thời gian xử lý đến byte cuối trên mọi JDK/provider.

### 8.2. Xử lý IOException và InterruptedException

Một method có thể mô tả rõ ngoại lệ:

~~~java
static String fetchText(
        HttpClient client, URI url)
        throws IOException, InterruptedException {

    HttpRequest request = HttpRequest.newBuilder(url)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

    if (response.statusCode() < 200
            || response.statusCode() >= 300) {
        throw new IOException(
                "Unexpected HTTP status: " + response.statusCode());
    }
    return response.body();
}
~~~

**Đoạn mã là một method**, cần đặt trong một class và import `HttpClient`, `URI`, `HttpRequest`, `HttpResponse`, `IOException`, `Duration`, `StandardCharsets`. Ngoại lệ HTTP status do **ứng dụng chủ động tạo** sau khi kiểm tra `statusCode()`; bản thân `send` không coi mọi `4xx/5xx` là lỗi I/O.

Khi tầng gọi cần bắt và xử lý:

~~~java
try {
    String body = fetchText(client, url);
    System.out.println(body);
} catch (java.net.http.HttpTimeoutException ex) {
    System.err.println("HTTP request timed out");
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    System.err.println("HTTP request was interrupted");
} catch (IOException ex) {
    System.err.println("HTTP I/O or status error: " + ex.getMessage());
}
~~~

Đây là **đoạn trong một method**, với `client` và `url` có sẵn. Thứ tự catch hợp lệ vì `HttpTimeoutException` là lớp con của `IOException`.

- `IOException`: có thể là DNS/connection/TLS/đọc-ghi hoặc lỗi I/O khác; có thể chứa `HttpTimeoutException` và `HttpConnectTimeoutException`. Nên giữ nguyên nguyên nhân/stack trace ở tầng logging thích hợp, tránh lộ dữ liệu nhạy cảm.
- `InterruptedException`: thread bị ngắt khi chờ. Nếu **bắt** ngoại lệ và không truyền tiếp, thường gọi `Thread.currentThread().interrupt()` để khôi phục cờ ngắt cho tầng quản lý tác vụ. Sau đó nên dừng công việc hoặc tuân theo chính sách hủy.
- Nếu `send` bị ngắt, client có thể **cố gắng hủy** HTTP exchange, nhưng việc hủy không bảo đảm xảy ra ngay. Server có thể đã bắt đầu xử lý request. Vì vậy không biến timeout/ngắt thành tín hiệu “server chắc chắn chưa nhận”.
- `IllegalArgumentException` do URI/header/request không hợp lệ là lỗi tham số/logic; không nên gộp mù vào retry network.
- `send` không trả `null` đơn thuần để báo lỗi mạng. Lỗi được thể hiện qua ngoại lệ, còn kết quả HTTP bình thường qua `HttpResponse`.

### 8.3. Status và lỗi I/O là hai tầng khác nhau

| Kết quả | Thông thường `send` làm gì? | Ứng dụng cần xử lý |
| --- | --- | --- |
| `200 OK` / `201 Created` | Trả `HttpResponse<T>` | Phân tích body và nghiệp vụ thành công |
| `204 No Content` | Trả `HttpResponse<T>` | Không giả định có body |
| `301/302/307/308` | Có thể trả redirect; nếu bật follow redirects thì có thể theo | Kiểm chính sách redirect và URI cuối |
| `400/401/403/404/409/429` | Trả `HttpResponse<T>` khi HTTP exchange thành công | Phân loại lỗi client/auth/rate limit và body lỗi |
| `500/502/503/504` | Trả `HttpResponse<T>` khi server gửi phản hồi | Chính sách retry có kiểm soát, tránh làm trùng side effect |
| DNS/TCP/TLS thất bại | Ném `IOException` hoặc lớp con | Xử lý lỗi kết nối, retry khi phù hợp |
| Quá timeout | Ném `HttpTimeoutException`/lớp con | Deadline/retry theo nghiệp vụ |
| Thread bị ngắt | Ném `InterruptedException` | Truyền tiếp hoặc khôi phục interrupt rồi dừng tác vụ |

**Đừng tự động coi một mã `429`/`503` là cho phép retry ngay**. Nếu API có header `Retry-After`, xem xét chính sách/backoff và ngân sách retry; đặc biệt cẩn trọng khi request thay đổi dữ liệu.

## 9. send đồng bộ hay sendAsync: chọn theo nhu cầu

Cùng một request và handler:

~~~java
// Synchronous: thread hiện tại chờ kết quả.
HttpResponse<String> sync = client.send(
        request, HttpResponse.BodyHandlers.ofString());

// Asynchronous: nhận CompletableFuture, kết quả đến sau.
CompletableFuture<HttpResponse<String>> async = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Đây là **đoạn minh họa**, cần import `CompletableFuture` và xử lý ngoại lệ của nhánh synchronous.

| Tiêu chí | `send` | `sendAsync` |
| --- | --- | --- |
| Kết quả ngay sau lời gọi | `HttpResponse<T>` hoặc ngoại lệ sau khi chờ | `CompletableFuture<HttpResponse<T>>` |
| Thread gọi | Có thể bị chặn tới khi phản hồi sẵn sàng | Trả nhanh để gắn callback/chuỗi xử lý |
| Quản lý lỗi | `try/catch` với `IOException` và `InterruptedException` | Future hoàn thành thất bại, xử lý `exceptionally`/`handle`/... |
| Mã cho một thao tác tuần tự | Thường dễ đọc | Nhiều bước hơn |
| Nhiều yêu cầu đồng thời | Cần tổ chức thread/concurrency riêng | Dễ phối hợp future với pipeline bất đồng bộ |

**Đồng bộ không đồng nghĩa nhanh hơn hay chậm hơn về mạng.** Khác biệt chính là cách caller chờ và tổ chức công việc. Với tác vụ CLI/worker tuần tự có deadline rõ ràng, `send` thường phù hợp. Với nhiều yêu cầu HTTP đồng thời hoặc ứng dụng muốn tránh chiếm thread khi chờ I/O, `sendAsync` là lựa chọn đáng cân nhắc.

## 10. Những lưu ý thiết kế vẫn đúng trên JDK hiện đại

### 10.1. Không tạo client mới cho mỗi request nếu không cần

~~~java
// Không nên tạo một HttpClient mới trong mỗi vòng lặp nghiệp vụ
// nếu các request dùng chung cấu hình và cần tái sử dụng kết nối.
for (URI uri : trustedUris) {
    HttpClient oneOff = HttpClient.newHttpClient();
    // oneOff.send(...);
}
~~~

Đoạn trên chỉ minh họa cấu trúc, không chạy độc lập. Tốt hơn là tạo **một client có vòng đời phù hợp**, dùng lại cho các request cùng cấu hình. Nếu các request khác chính sách TLS/proxy/auth, nên tách client theo chính sách tương ứng.

### 10.2. Chặn rủi ro từ URL đầu vào

Nếu ứng dụng cho người dùng nhập URI, không gửi thẳng đến mọi host không kiểm tra. Trong dịch vụ server-side, URI trỏ vào mạng nội bộ, metadata endpoint hoặc địa chỉ chuyển hướng không mong muốn có thể tạo **SSRF**. Cần xác thực scheme/host/port, áp dụng chính sách outbound network và kiểm tra redirect nếu ứng dụng cho phép theo.

Mặc định `followRedirects` là `NEVER`; nếu bật redirect, hãy cân nhắc chuyển host, scheme, credentials và mức tin cậy của đích cuối. Dùng HTTPS với xác thực chứng chỉ phù hợp cho dữ liệu nhạy cảm; không vô hiệu hóa TLS validation chỉ để “cho code chạy”.

### 10.3. Giới hạn dữ liệu response

`BodyHandlers.ofString` và `ofByteArray` thuận tiện nhưng có thể dồn body không đáng tin vào RAM. Nếu response có thể rất lớn, hãy dùng streaming hoặc file, giới hạn byte, thời gian, số request đồng thời, và tránh parser chiếm quá nhiều bộ nhớ. `Content-Length` là dữ liệu header hữu ích để từ chối sớm, **không thay thế** đếm số byte thực nhận.

### 10.4. Không coi callback trong handler là nơi gọi blocking I/O tùy ý

`BodyHandler` được gọi lúc có status/header, trước khi subscriber xử lý body. Nếu tự xây handler/subscriber, cần hiểu cơ chế demand, completion, cancellation của `Flow`; không trộn nghiệp vụ chặn dài vào callback I/O của client nếu chưa nắm rõ scheduler và khả năng bế tắc.

Với phần lớn bài toán GET/POST thông thường, các `BodyHandlers` có sẵn là đủ, không cần tự xây reactive subscriber.

### 10.5. Request body có thể không gửi lại được

Một `BodyPublisher` đọc từ một `InputStream` được cung cấp theo `Supplier`. Nếu thiết kế retry, cần chắc rằng request body có thể **tạo lại** an toàn và server có ngữ nghĩa idempotency phù hợp. Không mặc định mọi publisher hay request POST đều gửi lại được nhiều lần.

## 11. Các lỗi phổ biến và cách sửa

| Nhầm lẫn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “`send` trả về nghĩa là status 2xx.” | Coi 404/500 là thành công | Kiểm `response.statusCode()` theo hợp đồng API đích |
| “`send` luôn tải xong toàn body.” | Với `ofInputStream`, chưa xử lý/đóng stream | Phân biệt handler tích lũy và streaming; đóng/tiêu thụ stream |
| “Không đặt timeout thì request sẽ luôn tự kết thúc sớm.” | Thread chờ lâu/không có deadline chủ động | Đặt timeout request, connect timeout và chính sách hủy |
| “`connectTimeout` là tổng timeout của request.” | Bỏ qua thời gian server xử lý/trả dữ liệu | Đặt `HttpRequest.timeout` riêng |
| “`404` làm `send` ném `IOException`.” | Xử lý sai nhánh HTTP error | Đọc `HttpResponse` rồi kiểm status |
| “`ofString` luôn dùng charset mặc định máy.” | Giải mã sai văn bản | `ofString()` xét Content-Type rồi fallback UTF-8; hoặc truyền charset tường minh |
| “Gửi JSON bằng `ofString` tự sinh Content-Type.” | Server không nhận đúng format | Đặt `Content-Type: application/json` tường minh |
| “Mặc định client theo mọi redirect.” | Không xử lý 3xx đúng | Mặc định `Redirect.NEVER`; cấu hình rõ nếu cần |
| “Bị timeout/ngắt nghĩa là server chưa xử lý.” | Retry có thể nhân đôi giao dịch | Dùng idempotency và chính sách xác nhận |
| “Client nào cũng phải `close()` trên Java 11.” | Mã không biên dịch trên Java 11 | Xem vòng đời theo phiên bản, không gọi API chỉ có ở JDK mới |
| “Tạo client mới mỗi lần gọi là miễn phí.” | Khó tái sử dụng kết nối, tăng tài nguyên | Tái sử dụng client theo cấu hình |
| “`ofString` phù hợp mọi file tải về.” | Có thể chiếm rất nhiều RAM | Dùng `ofInputStream` hoặc `ofFile`, đặt giới hạn |
| “`send` đồng bộ nên ứng dụng không cần xử lý concurrency.” | Nhiều request vẫn có thể chiếm nhiều thread | Quản lý thread, deadline và số công việc đồng thời |
| “Đọc body lỗi không cần xử lý.” | Mất thông điệp phục vụ debug/UX | Parse body lỗi theo status và hợp đồng endpoint, tránh in bí mật |

## 12. Checklist khi viết hàm gọi HTTP đồng bộ

- [ ] `HttpClient` được tạo với cấu hình TLS/proxy/redirect/timeout phù hợp và có thể tái sử dụng.
- [ ] URI được xác thực theo nguồn dữ liệu và giới hạn host/scheme nếu đầu vào không đáng tin.
- [ ] `HttpRequest` có phương thức đúng (GET/POST/...), header hợp lệ và `timeout(Duration)`.
- [ ] `BodyHandler<T>` phù hợp loại nội dung, charset và giới hạn bộ nhớ.
- [ ] Sau `send`, code **phân loại HTTP status** trước khi coi body là dữ liệu thành công.
- [ ] Phân biệt `IOException`, timeout và `InterruptedException`; giữ/khôi phục interrupt nếu bắt mà không truyền lên.
- [ ] Với body dạng stream, đọc hết hoặc đóng; không để kết nối/tài nguyên treo.
- [ ] Có timeout, giới hạn response và concurrency cho endpoint không đáng tin.
- [ ] Retry POST/PUT chỉ theo hợp đồng API và idempotency phù hợp.
- [ ] Test cover HTTP 2xx, 4xx/5xx, timeout, body rỗng, charset và phản hồi lớn.
- [ ] Mã mục tiêu Java 11 không vô tình dùng API bổ sung chỉ xuất hiện ở các JDK mới hơn.

## 13. Tự kiểm tra kiến thức

**Câu 1.** `send(request, BodyHandlers.ofString())` nhận response `404`. Nó có buộc ném ngoại lệ chỉ vì `404` không?

**Không.** 404 là HTTP status; khi quá trình gửi/nhận không gặp lỗi I/O, `send` trả `HttpResponse<String>`. Ứng dụng tự kiểm `statusCode()`.

**Câu 2.** Trong lúc dùng `BodyHandlers.ofInputStream()`, vì sao sau khi `send` trả về vẫn có thể chặn khi gọi `response.body().read(...)`?

**Vì** `send` có thể trả khi đã nhận status và headers, còn body streaming đang đến. Lần `read` phải chờ byte của body; cần đọc/đóng stream hợp lý.

**Câu 3.** `connectTimeout(3s)` và `request.timeout(10s)` có phải một cơ chế duy nhất không?

**Không.** Connect timeout áp dụng việc tạo kết nối mới, còn request timeout áp dụng yêu cầu theo hợp đồng của request. Cả hai có mục đích khác nhau.

**Câu 4.** Vì sao sau `InterruptedException` nên cân nhắc `Thread.currentThread().interrupt()` nếu đã bắt mà không ném tiếp?

**Vì** bắt `InterruptedException` thường xóa trạng thái ngắt của thread. Khôi phục cờ giúp tầng quản lý cao hơn nhận biết tác vụ cần dừng.

**Câu 5.** `send` timeout khi gửi POST tạo đơn hàng. Có nên gửi lại ngay không?

**Không tự động.** Server có thể đã tạo đơn hàng. Cần idempotency key, kiểm trạng thái hoặc quy tắc retry do API cung cấp.

**Câu 6.** Muốn xử lý response 100 MiB mà không giữ toàn bộ trong `String`, chọn handler nào?

**Có thể chọn** `ofInputStream` để đọc từng phần hoặc `ofFile` để ghi ra file. Vẫn cần giới hạn kích thước, thời gian và cleanup.

**Câu 7.** Vì sao `BodyHandlers.ofString(StandardCharsets.UTF_8)` thường dễ dự đoán hơn `ofString()` với endpoint cố định UTF-8?

**Vì** nó chỉ định charset rõ ràng; `ofString()` còn có thể chọn charset theo header `Content-Type` của server.

## Tài liệu tham khảo chính thức — Java 11 và JDK hiện đại

- [`HttpClient` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, client configuration và ngoại lệ.
- [`HttpRequest.Builder` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `GET`, `POST`, headers, URI, timeout.
- [`HttpRequest.BodyPublishers` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): `ofString`, `ofFile`, `ofInputStream` và charset.
- [`HttpResponse` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): status, headers, body, URI và HTTP version.
- [`HttpResponse.BodyHandlers` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString`, `ofByteArray`, `ofInputStream`, `ofFile` và `discarding`.
- [`HttpTimeoutException` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): ngoại lệ timeout thuộc nhóm `IOException`.
- [`HttpClient` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): kiểm tra hợp đồng `send` vẫn còn và API vòng đời ở JDK hiện đại.
- [`HttpServer` — JDK 11](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server loopback dùng riêng trong fixture thử nghiệm.

**Ghi nhớ:** `HttpClient.send` chặn thread gọi và trả `HttpResponse<T>` khi nhận phản hồi theo `BodyHandler<T>`. Status HTTP là dữ liệu phải kiểm tra; timeout và lỗi I/O có nhánh xử lý riêng; body streaming vẫn cần tiêu thụ hoặc đóng. Đặt timeout, tái sử dụng client và chọn handler phù hợp giúp ứng dụng Java 11+ đúng và bền vững trên JDK hiện đại.