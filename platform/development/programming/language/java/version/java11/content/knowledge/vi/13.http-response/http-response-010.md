# Phân biệt nhận header với đọc xong body trong Java 11 HTTP Response

**Chủ đề cha:** HTTP Response  
**Trọng tâm:** Hiểu chính xác thời điểm có thể đọc HTTP status/headers, thời điểm `HttpResponse<T>` xuất hiện, và khi nào response body đã thật sự được nhận/xử lý xong. Bài sử dụng API `java.net.http` từ Java 11, với các cơ chế vẫn hữu ích trên những bản Java hiện đại.

Một HTTP response gồm **status line**, **headers** và (nếu có) **body**. Server có thể gửi status/headers rất nhanh, rồi tiếp tục truyền body chậm, từng phần hoặc qua một kết nối kéo dài. Vì vậy, sự kiện **“đã nhận header”** và **“đã đọc/ghi/xử lý xong body”** là hai mốc **khác nhau**. Sự khác biệt càng quan trọng trong Java `HttpClient` vì **thời điểm hoàn tất `send` hoặc `CompletableFuture` phụ thuộc vào `BodyHandler` được chọn**.

Ví dụ, `BodyHandlers.ofString()` tích lũy body vào một chuỗi trước khi trả `HttpResponse<String>`. Nhưng `BodyHandlers.ofInputStream()` có thể trả `HttpResponse<InputStream>` sau khi headers đã được đọc, **ngay cả khi body còn đang truyền**. Nếu ứng dụng ghi log “download hoàn tất” ngay khi `sendAsync(...ofInputStream())` thành công thì rất dễ tạo ra thống kê sai, trả trạng thái thành công sớm hoặc bỏ quên việc đóng stream.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân biệt **header received**, **body handler invoked**, **HttpResponse available**, **body consumed/EOF** và **nghiệp vụ hoàn tất**.
2. Giải thích `HttpResponse.BodyHandler<T>`, `HttpResponse.ResponseInfo`, `BodySubscriber<T>` và vì sao kiểu `T` quyết định cách lấy body.
3. Xác định mốc hoàn tất cho `ofString`, `ofByteArray`, `ofFile`, `discarding` so với `ofInputStream`, `ofLines` và `ofPublisher`.
4. Dùng `send` hoặc `sendAsync` theo kiểu xử lý thích hợp, không đánh đồng future hoàn tất với việc đã đọc hết body ở các handler dạng streaming.
5. Tiêu thụ và đóng `InputStream`/`Stream<String>` đúng vòng đời; đăng ký `Flow.Subscriber`, kiểm soát demand và theo dõi `onComplete/onError` khi dùng `ofPublisher`.
6. Viết kiểm thử có tính quyết định: server gửi header và phần đầu body, **tạm ngừng có kiểm soát**, rồi gửi phần còn lại; kiểm tra mốc hoàn tất mà không phụ thuộc `Thread.sleep()`.
7. Xử lý lỗi HTTP status, lỗi body xảy ra sau header, giới hạn bộ nhớ, body dài/chunked và cleanup tài nguyên.

## 2. Ba mốc kỹ thuật và một mốc nghiệp vụ

Một response có thể đi theo thứ tự:

```text
Client gửi HTTP request
         |
         v
[1] Status + response headers được nhận
         |
         +--> BodyHandler.apply(ResponseInfo)
         |    quyết định BodySubscriber
         |
         v
[2] HttpResponse<T> được cung cấp cho phía gọi
         |    (thời điểm phụ thuộc loại BodySubscriber)
         |
         v
[3] Body thực sự đến hết / stream hết / subscriber onComplete
         |
         v
[4] Ứng dụng xác minh byte, parse dữ liệu, commit nghiệp vụ
```

**Điểm cần hiểu:** với một handler tích lũy `String`, thứ tự **[2] đến sau [3]**. Với một handler streaming, **[2] có thể đến trước [3]**. Trên một request không có body (`HEAD`, `204 No Content` hoặc body 0 byte đúng hợp đồng), các mốc có thể sát nhau; không suy ra quy tắc chung từ trường hợp đơn giản đó.

`BodyHandler<T>` được gọi khi có `ResponseInfo` chứa status, headers và HTTP version, **trước khi body bytes được chuyển vào subscriber**. Nó trả `BodySubscriber<T>` để nhận body. Sau đó `HttpResponse<T>` đại diện cho kết quả ở mức mà subscriber/handler đã hứa. `HttpResponse.body()` có thể là dữ liệu **đã hoàn thành** (chuỗi, mảng, đường dẫn) hoặc là **một phương tiện để tiếp tục nhận dữ liệu** (stream/publisher).

**Hai câu hỏi tách biệt:**

- **Header đã có chưa?** Có thể xem `statusCode()`, `headers()` hoặc sử dụng `ResponseInfo` trong `BodyHandler`.
- **Body đã xong chưa?** Phải xét `BodyHandler`/subscriber cụ thể và trạng thái đọc của body, không dựa riêng vào `statusCode()` hay việc future đã hoàn tất.

## 3. Bảng hành vi của các BodyHandlers trên Java 11

| Handler | Kiểu `T` trong `HttpResponse<T>` | Khi `HttpResponse` có thể được trả | Ai hoàn tất việc đọc body? |
|---|---|---|---|
| `BodyHandlers.ofString(charset)` | `String` | **Sau khi body được nhận và giải mã thành String** | BodySubscriber của client |
| `BodyHandlers.ofByteArray()` | `byte[]` | **Sau khi body được tích lũy hoàn toàn** | BodySubscriber của client |
| `BodyHandlers.ofFile(path)` | `Path` | **Sau khi body đã ghi hoàn toàn vào file** | BodySubscriber ghi file |
| `BodyHandlers.discarding()` | `Void` | Sau khi subscriber tiêu thụ và loại bỏ body | BodySubscriber của client |
| `BodyHandlers.replacing(value)` | Kiểu của `value` | Sau khi body được loại bỏ, rồi trả giá trị thay thế | BodySubscriber của client |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Sau khi headers được đọc; body có thể chưa xong** | Mã ứng dụng đọc/đóng stream |
| `BodyHandlers.ofLines()` | `Stream<String>` | **Có thể trước khi toàn bộ body đến** | Mã ứng dụng duyệt/đóng Stream |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **Sau khi headers được đọc; body có thể chưa xong** | `Flow.Subscriber` đăng ký và yêu cầu dữ liệu |

Đây là hành vi của **các handler chuẩn**. Khi tự viết `BodyHandler`/`BodySubscriber`, thời điểm tương lai `getBody()` hoàn thành phụ thuộc implementation. Không tự suy từ kiểu `T` mà chưa đọc hợp đồng của subscriber.

**Không được nhầm** `HttpResponse<Path>` của `ofFile` với đường dẫn tồn tại **một phần** khi đang tải. Với `ofFile` chuẩn, khi response được trả thành công, body đã được ghi đầy đủ vào file. Nếu kết nối lỗi giữa chừng, có thể còn file chưa hoàn chỉnh trên đĩa; ứng dụng cần chính sách xóa/đánh dấu thất bại. Việc `Path` xuất hiện là trạng thái hoàn thành **tác vụ download theo handler**, không tự chứng minh nội dung hợp lệ về checksum/nghiệp vụ.

### 3.1 Vì sao `send` không có nghĩa “đã đọc xong tất cả”?

Hai cách gọi đều dùng `BodyHandler`:

```java
HttpResponse<InputStream> sync = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
```

```java
CompletableFuture<HttpResponse<InputStream>> async = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofInputStream());
```

Đây là hai **trích đoạn**, cần import và biến `client`, `request`. Với `ofInputStream`, ngay cả lệnh `send` đồng bộ cũng có thể trả về **sau khi header đã có nhưng trước khi body hoàn tất**. `sendAsync` có thể hoàn tất future ở mốc tương tự. Sự khác biệt **đồng bộ/bất đồng bộ** liên quan cách chờ kết quả response ở phía gọi; sự khác biệt **đã đọc xong body/chưa đọc xong** liên quan đến `BodySubscriber`.

Khi dùng `ofString`, cả `send` và `sendAsync` trả `HttpResponse<String>` sau khi đã có chuỗi body hoàn chỉnh (nếu không có lỗi). Khi dùng `ofPublisher`, `sendAsync` có thể hoàn tất sau headers, còn subscriber vẫn cần được đăng ký và nhận `onComplete` sau đó.

## 4. Header đến trước không chứng minh body đang hợp lệ

Các HTTP status như `200`, `201` hay `206` nằm trong phần **header**. Một server có thể gửi `200 OK` rồi đứt kết nối trong khi chuyển body. Khi sử dụng handler streaming, ứng dụng đã có `response.statusCode() == 200` nhưng `InputStream.read()` vẫn có thể ném `IOException` hoặc `Flow.Subscriber.onError` vẫn có thể được gọi.

Ví dụ anti-pattern:

```java
client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream())
        .thenAccept(response ->
                markDownloadCompleted(response.statusCode()));
```

Đây là **trích đoạn lỗi về ý nghĩa**, vì chỉ xem status sau khi stream body có thể chưa được tiêu thụ. Nó còn bỏ trách nhiệm đóng `response.body()`. Đánh dấu hoàn tất phải dựa trên kết quả **đọc hết stream, xác minh và lưu thành công** theo hợp đồng.

Một phương án cơ bản:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    if (response.statusCode() != 200) {
        // Có thể đọc body lỗi có giới hạn nếu cần,
        // rồi ném lỗi hoặc trả trạng thái nghiệp vụ.
        throw new IOException("HTTP " + response.statusCode());
    }
    byte[] bytes = body.readAllBytes();
    // Xác thực bytes và hoàn tất nghiệp vụ trước khi báo thành công.
}
```

Đoạn này là **trích đoạn trong một phương thức**; cần import `InputStream`, `HttpResponse`, `IOException` và có `client`/`request`. `readAllBytes()` chỉ thích hợp khi biết response nhỏ: với body lớn, stream vào file/buffer theo từng phần và đặt giới hạn byte. Thao tác `try-with-resources` bảo đảm close cả khi status khác 200 hoặc đọc lỗi.

Cần phân biệt **lỗi ở tầng giao thức HTTP** (ví dụ 404, 500 nhận được thành `HttpResponse`) với **lỗi vận chuyển body** (đọc stream ném `IOException`, future hoặc subscriber thất bại). Các handler chuẩn thường vẫn đọc body cho HTTP status 4xx/5xx; chúng không tự ném exception chỉ vì status không phải 2xx.

## 5. Chương trình Java 11: header có trước, body đến hai đợt

Chương trình đầu tiên làm rõ ba hành vi bằng một HTTP server local trên `127.0.0.1`. Mỗi endpoint thông báo body có **hai byte** (`A` và `B`), gửi header và byte đầu `A`, rồi **đợi một latch**. Main thread chỉ cho server gửi byte `B` sau khi đã kiểm tra trạng thái. Không dùng `Thread.sleep()`, nên test không phụ thuộc thời gian máy chạy nhanh hay chậm.

Chương trình so sánh:

- `ofString`: future **chưa xong** khi body còn thiếu `B`; sau khi gửi `B` thì response body là `"AB"`.
- `ofInputStream`: future **đã xong** dù server **chưa gửi `B`**. Mã ứng dụng đọc `A`, cho phép server gửi tiếp, rồi đọc `B` đến EOF.
- `BodyHandler` tùy biến: hàm handler được gọi khi biết HTTP status trước khi body hoàn thành; subscriber `ofString` của handler vẫn đợi đủ body.

Dùng module `jdk.httpserver` để tạo server test; ứng dụng HTTP client bình thường dùng module `java.net.http`.

Lưu file **`ResponsePhasesDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ResponsePhasesDemo {
    static final class StagedHandler implements HttpHandler {
        final CountDownLatch firstSent = new CountDownLatch(1);
        final CountDownLatch allowLast = new CountDownLatch(1);
        final CountDownLatch lastSent = new CountDownLatch(1);

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, 2);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write('A');
                output.flush();
                firstSent.countDown();
                try {
                    if (!allowLast.await(5, TimeUnit.SECONDS)) {
                        throw new IOException("Server release timeout");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IOException(ex);
                }
                output.write('B');
                output.flush();
                lastSent.countDown();
            }
        }
    }

    static void await(CountDownLatch latch) throws Exception {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout awaiting latch");
        }
    }

    static HttpRequest request(HttpServer server, String path) {
        return HttpRequest.newBuilder(URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort() + path))
                .GET().build();
    }

    public static void main(String[] args) throws Exception {
        StagedHandler asString = new StagedHandler();
        StagedHandler asStream = new StagedHandler();
        StagedHandler withHandler = new StagedHandler();

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/string", asString);
        server.createContext("/stream", asStream);
        server.createContext("/handler", withHandler);

        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1).build();

            CompletableFuture<HttpResponse<String>> stringFuture =
                    client.sendAsync(request(server, "/string"),
                            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            await(asString.firstSent);
            System.out.println("string-future-done-before-last="
                    + stringFuture.isDone());
            asString.allowLast.countDown();
            HttpResponse<String> full = stringFuture.get(5, TimeUnit.SECONDS);
            System.out.println("string-status=" + full.statusCode());
            System.out.println("string-body=" + full.body());

            CompletableFuture<HttpResponse<InputStream>> streamFuture =
                    client.sendAsync(request(server, "/stream"),
                            HttpResponse.BodyHandlers.ofInputStream());
            HttpResponse<InputStream> streaming =
                    streamFuture.get(5, TimeUnit.SECONDS);
            await(asStream.firstSent);
            System.out.println("stream-future-done-before-last="
                    + streamFuture.isDone());
            System.out.println("stream-last-already-sent="
                    + (asStream.lastSent.getCount() == 0));
            System.out.println("stream-status=" + streaming.statusCode());
            try (InputStream input = streaming.body()) {
                System.out.println("stream-first-byte=" + input.read());
                asStream.allowLast.countDown();
                System.out.println("stream-rest="
                        + new String(input.readAllBytes(), StandardCharsets.UTF_8));
            }

            CountDownLatch handlerCalled = new CountDownLatch(1);
            HttpResponse.BodyHandler<String> bodyHandler = info -> {
                System.out.println("body-handler-status=" + info.statusCode());
                handlerCalled.countDown();
                return HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
            };
            CompletableFuture<HttpResponse<String>> customFuture =
                    client.sendAsync(request(server, "/handler"), bodyHandler);
            await(handlerCalled);
            await(withHandler.firstSent);
            System.out.println("custom-future-done-before-last="
                    + customFuture.isDone());
            withHandler.allowLast.countDown();
            HttpResponse<String> custom = customFuture.get(5, TimeUnit.SECONDS);
            System.out.println("custom-body=" + custom.body());
        } finally {
            asString.allowLast.countDown();
            asStream.allowLast.countDown();
            withHandler.allowLast.countDown();
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy bằng Java 11 hoặc JDK mới hơn có hỗ trợ target Java 11:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 ResponsePhasesDemo.java
java --add-modules jdk.httpserver ResponsePhasesDemo
```

**Kết quả stdout chính xác đã được kiểm tra:**

```text
string-future-done-before-last=false
string-status=200
string-body=AB
stream-future-done-before-last=true
stream-last-already-sent=false
stream-status=200
stream-first-byte=65
stream-rest=B
body-handler-status=200
custom-future-done-before-last=false
custom-body=AB
```

**Đọc kết quả đúng thứ tự:**

1. `string-future-done-before-last=false`: vì server chỉ phát một trong hai byte đã công bố, subscriber của `ofString` vẫn chưa tạo xong chuỗi.
2. Sau khi latch cho gửi `B`, `ofString` hoàn tất với status `200` và body `"AB"`. Đó là mốc mà string đã được đọc/giải mã đầy đủ.
3. `stream-future-done-before-last=true` đồng thời `stream-last-already-sent=false`: đã có `HttpResponse<InputStream>`, nhưng ít nhất một byte **chưa từng được server gửi**. Đây là chứng cứ độc lập với buffering của client.
4. `stream-first-byte=65` vì ASCII `'A'` có mã byte 65; sau khi phát tín hiệu cho gửi nốt, `readAllBytes()` nhận chữ `B`.
5. `body-handler-status=200` xuất hiện trước `custom-future-done-before-last=false`: callback `BodyHandler.apply(ResponseInfo)` biết status, còn `BodySubscribers.ofString` chưa hoàn thành body.
6. `finally` đảm bảo giải phóng các latch và dừng server. `InputStream` được đóng qua `try-with-resources`, nên demo không để response body stream mở sau khi dùng.

Test dùng HTTP/1.1 loopback để có kết quả kiểm soát được. Trong hệ thống thật, số packet và thời điểm TCP chia đợt **không đảm bảo** giống hai lần `write`; điều được xác minh ở đây là **thứ tự mốc** qua các latch và tính đúng của API. Nếu test timeout, đó là lỗi thực thi/test cần điều tra, không phải một kết quả khác được kỳ vọng.

## 6. BodyHandler có được gọi khi mới có headers?

Có. `HttpResponse.BodyHandler<T>` là một functional interface:

```java
HttpResponse.BodyHandler<String> handler = responseInfo -> {
    int code = responseInfo.statusCode();
    String server = responseInfo.headers()
            .firstValue("Server")
            .orElse("unknown");

    // Chọn cách nhận body dựa trên status / headers:
    return HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
};
```

Đây là **trích đoạn minh họa**, cần import `HttpResponse` và `StandardCharsets`. Biến `server` chỉ ví dụ đọc header; server có thể không gửi header này. BodyHandler phải trả `BodySubscriber<String>` ngay, không đợi dữ liệu body trong chính callback.

Một ứng dụng có thể chọn subscriber khác theo status/header (ví dụ lưu body thành file cho `200` nhưng thu error body có giới hạn cho `4xx`). Điều đó cần nhất quán kiểu `T` của `BodyHandler<T>` và hợp đồng API. Nếu tạo một handler tùy biến, tránh logic blocking hoặc gọi HTTP nested trong callback, vì nó nằm trên đường đi xử lý response và có thể ảnh hưởng tiến độ I/O.

**Giới hạn của status trong handler:** biết status `200` vẫn chưa chứng minh body cuối cùng sẽ đến đầy đủ hoặc JSON parse đúng. Đừng tạo một record “đã tải đủ file” ngay trong `apply(ResponseInfo)`. Hãy ghi “đã nhận headers” ở mốc này, rồi chỉ ghi “đã tải xong” sau khi subscriber và validation hoàn tất.

## 7. BodyHandlers.ofFile: chỉ trả Path sau khi ghi hết body

Với `BodyHandlers.ofFile(path)`, `HttpResponse<Path>` chỉ được cung cấp thành công sau khi body đã được ghi đầy đủ vào file. Nó phù hợp khi response lớn và bạn muốn lưu vào file mà không nạp toàn bộ thành `String` hoặc `byte[]`. Tuy nhiên **tệp đã tồn tại trên đĩa trong khi tải** có thể chưa hoàn chỉnh; một watcher ngoài ứng dụng có thể nhìn thấy file sớm hơn lúc future hoàn tất. Khi body lỗi, cần xử lý file dở dang theo chính sách.

### Ví dụ 2 — future tải file chỉ xong sau byte cuối

Server local gửi body `"READY"` với `Content-Length: 5`; ban đầu chỉ gửi hai byte `"RE"` rồi đợi latch. Client dùng `BodyHandlers.ofFile` ghi đến tệp tạm rỗng. Future chưa được đánh dấu hoàn tất cho đến khi server được cho phép gửi nốt `"ADY"`.

Lưu thành **`FileBodyCompletionDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class FileBodyCompletionDemo {
    static final class DelayedBody implements HttpHandler {
        final CountDownLatch firstSent = new CountDownLatch(1);
        final CountDownLatch releaseLast = new CountDownLatch(1);

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            exchange.sendResponseHeaders(200, 5);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write("RE".getBytes(StandardCharsets.UTF_8));
                out.flush();
                firstSent.countDown();
                try {
                    if (!releaseLast.await(5, TimeUnit.SECONDS)) {
                        throw new IOException("Timeout awaiting body release");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IOException(ex);
                }
                out.write("ADY".getBytes(StandardCharsets.UTF_8));
            }
        }
    }

    public static void main(String[] args) throws Exception {
        DelayedBody body = new DelayedBody();
        Path path = Files.createTempFile("http-body-", ".txt");
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/file", body);
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/file");
            HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
            CompletableFuture<HttpResponse<Path>> future =
                    HttpClient.newHttpClient().sendAsync(request,
                            HttpResponse.BodyHandlers.ofFile(path));
            if (!body.firstSent.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Header/first bytes timeout");
            }
            System.out.println("file-future-done-before-tail="
                    + future.isDone());
            body.releaseLast.countDown();
            HttpResponse<Path> response = future.get(5, TimeUnit.SECONDS);
            System.out.println("file-status=" + response.statusCode());
            System.out.println("file-body="
                    + Files.readString(response.body(), StandardCharsets.UTF_8));
        } finally {
            body.releaseLast.countDown();
            server.stop(0);
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 FileBodyCompletionDemo.java
java --add-modules jdk.httpserver FileBodyCompletionDemo
```

```text
file-future-done-before-tail=false
file-status=200
file-body=READY
```

**Ý nghĩa:** ở lúc `firstSent` được mở, header đã gửi và server mới gửi 2/5 byte. Future chưa xong. Sau khi server ghi hết `ADY` và body subscriber ghi đủ file, future mới có `HttpResponse<Path>`. Mã ứng dụng sau đó đọc tệp và xác minh nội dung. Tệp tạm được xóa trong `finally`.

Trong dịch vụ thực, không luôn ghi trực tiếp vào tên file đích cuối. Nếu kết quả phải nguyên vẹn, có thể tải vào file tạm trong thư mục đúng quyền, kiểm tra kích thước/hash/định dạng, rồi đổi tên/di chuyển nguyên tử **khi hệ thống file hỗ trợ**. Chọn chính sách xóa file khi status lỗi hoặc request dở; `ofFile` mặc định không cam kết rollback file khi body transfer thất bại.

## 8. BodyHandlers.ofPublisher: response sẵn sàng trước `onComplete`

`BodyHandlers.ofPublisher()` trả `HttpResponse<Flow.Publisher<List<ByteBuffer>>>`. Tại thời điểm `HttpResponse` được cung cấp, headers đã được đọc nhưng body có thể chưa xong. Publisher cần **một** subscriber đăng ký, sau đó subscription phải yêu cầu dữ liệu bằng `request(n)`. Tín hiệu `onNext(...)` mang các lô `ByteBuffer` và `onComplete()` đánh dấu stream thành công kết thúc; `onError(Throwable)` báo thất bại khi nhận body.

Nếu code chỉ kiểm tra:

```java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());
System.out.println(response.statusCode()); // có thể in trước khi body xong
```

Đây là **trích đoạn trong phương thức**: cần import `HttpResponse`, `Flow`, `ByteBuffer`, `List` và khai báo `client`/`request`. Nó chưa đăng ký subscriber nên **chưa xử lý body**. Đừng để một publisher không được subscribe vô thời hạn, vì request có thể giữ tài nguyên và khiến quá trình nhận body không tiến triển.

### Ví dụ 3 — subscriber tự xác nhận hoàn tất

Demo dùng server gửi `A` rồi tạm dừng trước `B`. `HttpResponse` được trả trước, subscriber nhận byte đầu và **chưa** nhận `onComplete`. Chỉ sau khi cho server gửi `B` thì subscriber hoàn tất và có thể xác minh body là `AB`.

Lưu thành **`PublisherCompletionDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class PublisherCompletionDemo {
    static final class DelayedBody implements HttpHandler {
        final CountDownLatch firstSent = new CountDownLatch(1);
        final CountDownLatch releaseLast = new CountDownLatch(1);
        final CountDownLatch lastSent = new CountDownLatch(1);

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            exchange.sendResponseHeaders(200, 2);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write('A');
                out.flush();
                firstSent.countDown();
                try {
                    if (!releaseLast.await(5, TimeUnit.SECONDS)) {
                        throw new IOException("Timeout awaiting release");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IOException(ex);
                }
                out.write('B');
                out.flush();
                lastSent.countDown();
            }
        }
    }

    static final class CollectingSubscriber
            implements Flow.Subscriber<List<ByteBuffer>> {
        final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        final CountDownLatch firstData = new CountDownLatch(1);
        final CountDownLatch completed = new CountDownLatch(1);
        final AtomicReference<Throwable> failure = new AtomicReference<>();

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            subscription.request(Long.MAX_VALUE);
        }

        @Override
        public void onNext(List<ByteBuffer> batch) {
            for (ByteBuffer buffer : batch) {
                while (buffer.hasRemaining()) {
                    bytes.write(buffer.get());
                }
            }
            firstData.countDown();
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            completed.countDown();
        }

        @Override
        public void onComplete() {
            completed.countDown();
        }
    }

    static void await(CountDownLatch latch) throws Exception {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out");
        }
    }

    public static void main(String[] args) throws Exception {
        DelayedBody body = new DelayedBody();
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/publisher", body);
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/publisher");
            HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
            HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
                    HttpClient.newHttpClient().sendAsync(
                            request, HttpResponse.BodyHandlers.ofPublisher())
                            .get(5, TimeUnit.SECONDS);
            await(body.firstSent);
            System.out.println("publisher-status=" + response.statusCode());
            System.out.println("publisher-last-sent="
                    + (body.lastSent.getCount() == 0));
            CollectingSubscriber sink = new CollectingSubscriber();
            response.body().subscribe(sink);
            await(sink.firstData);
            System.out.println("publisher-first-byte=" + sink.bytes.toByteArray()[0]);
            System.out.println("publisher-completed-before-tail="
                    + (sink.completed.getCount() == 0));
            body.releaseLast.countDown();
            await(sink.completed);
            if (sink.failure.get() != null) {
                throw new IOException("Subscriber failed", sink.failure.get());
            }
            System.out.println("publisher-complete=true");
            System.out.println("publisher-body="
                    + new String(sink.bytes.toByteArray(), StandardCharsets.UTF_8));
        } finally {
            body.releaseLast.countDown();
            server.stop(0);
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 PublisherCompletionDemo.java
java --add-modules jdk.httpserver PublisherCompletionDemo
```

```text
publisher-status=200
publisher-last-sent=false
publisher-first-byte=65
publisher-completed-before-tail=false
publisher-complete=true
publisher-body=AB
```

**Giải thích:** `publisher-status=200` xuất hiện trong khi `publisher-last-sent=false`: nhận được status và đối tượng publisher không có nghĩa nhận hết dữ liệu. `firstData` latch chứng minh subscriber đã nhận byte đầu, còn `completed` vẫn chưa được đếm. Sau khi mở `releaseLast`, server gửi `B` và subscriber được gọi `onComplete`; chỉ lúc ấy demo ghi `publisher-complete=true`.

Ví dụ yêu cầu `Long.MAX_VALUE` từ subscription để giữ mã ngắn gọn và cho phép đọc hết payload **rất nhỏ**. Trong ứng dụng thật phải thiết kế demand/backpressure, giới hạn số byte, xử lý lỗi và tránh giữ toàn bộ body lớn bằng `ByteArrayOutputStream`. Các `ByteBuffer` nhận qua `onNext` nên được xử lý/copy theo hợp đồng ngay trong callback; không giữ reference mutable để dùng muộn khi chưa nắm rõ vòng đời dữ liệu.

**Quy tắc quan trọng:** publisher từ `ofPublisher` được đăng ký **chỉ một lần**. Không dùng hai subscriber để “đọc lại body”; nếu cần hai hướng xử lý, tạo một pipeline phân phối có kiểm soát hoặc tải body vào một nơi lưu trữ rồi sử dụng lại sau khi đã hoàn tất.

## 9. ofInputStream, ofLines: tự quyết định lúc nào kết thúc đọc

### 9.1 Với `ofInputStream()`

`HttpResponse<InputStream>` cung cấp stream đã sẵn sàng **sau headers**, trong khi body vẫn có thể đến theo thời gian. Mã ứng dụng phải:

- Đọc đủ theo giao thức đến EOF (`read() == -1`) hoặc đến khi đã lấy phần cần thiết rồi **đóng stream**.
- Dùng `try-with-resources`. Không coi `response.body()` là `String` đã hoàn tất.
- Áp dụng giới hạn kích thước/độ dài được phép cho response, nhất là với server bên ngoài. `readAllBytes()` giữ toàn bộ dữ liệu trong RAM, chỉ phù hợp body đã biết nhỏ.
- Xử lý `IOException` hoặc việc block trong khi đọc. Một `sendAsync` hoàn tất thành công không bảo đảm không có lỗi đọc sau đó.
- Nếu chỉ cần header và muốn ngừng đọc body, **đóng stream một cách chủ đích**; việc này có thể ảnh hưởng khả năng tái sử dụng kết nối. Không tự ý bỏ mặc stream đã trả về.

Mẫu giới hạn số byte được đọc bằng vòng lặp, khi `response` là `HttpResponse<InputStream>`:

```java
long limitBytes = 10_000_000L;
long total = 0;
byte[] buffer = new byte[8192];

try (InputStream body = response.body()) {
    int count;
    while ((count = body.read(buffer)) != -1) {
        total = Math.addExact(total, count);
        if (total > limitBytes) {
            throw new IOException("Response body exceeds configured limit");
        }
        // Xử lý CHỈ buffer[0..count-1] ở đây.
    }
}
```

Đây là **trích đoạn**; code thực tế cần `InputStream`, `IOException` và sink/logic xử lý byte. Để giảm cấp phát/bộ nhớ với tải lớn, dùng `Files.newOutputStream` hoặc `BodyHandlers.ofFile` và chính sách tệp. Để chống body lớn ngoài ý muốn, còn có thể kiểm tra `Content-Length` nếu có, nhưng **phải giới hạn theo số byte thực tế đang nhận** nữa.

### 9.2 Với `ofLines()`

`BodyHandlers.ofLines()` trả `HttpResponse<Stream<String>>`; response có thể được cấp trước khi body nhận hết. Các dòng được giải mã và đưa ra khi duyệt stream. Phương thức terminal như `forEach` hoặc `count` có thể tiếp tục chờ dữ liệu cho tới khi body kết thúc. Stream cần được đóng theo vòng đời:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.forEach(System.out::println);
}
```

Đây là **trích đoạn** với import `HttpResponse` và `java.util.stream.Stream`, cùng `client`/`request` có sẵn; lỗi từ tiêu thụ stream cần được xử lý theo ngữ cảnh. Đừng dùng `response.statusCode()` hoặc sự tồn tại của `Stream<String>` để khẳng định đã duyệt xong các dòng.

Nếu endpoint là luồng sự kiện dài hạn (ví dụ text streaming liên tục), “đọc hết body” có thể không xảy ra cho tới khi server đóng stream. Hợp đồng ứng dụng có thể cần “nhận được sự kiện X” như mốc thành công cục bộ, trong khi kết nối vẫn tồn tại; đó là điều kiện nghiệp vụ **riêng** với việc toàn bộ body đạt EOF.

## 10. HTTP status, Content-Length và EOF nói những điều khác nhau

| Tín hiệu | Điều nó cho biết | Không cho biết |
|---|---|---|
| Status `200` | Server báo request thành công ở tầng HTTP | Body đã đủ byte, nội dung đúng schema, tải file hoàn tất |
| `Content-Length: 5000` | Server tuyên bố số byte payload trong body theo framing áp dụng | Đã thực sự nhận đủ 5000 byte |
| Không có `Content-Length` | Độ dài có thể không biết trước, dùng framing khác | Không có body hoặc body đã xong |
| HTTP/1.1 chunked | Body truyền thành các chunk có framing | Một chunk đã đọc nghĩa là toàn body hoàn tất |
| `InputStream.read() == -1` | Stream đã tới EOF | Nội dung có hợp lệ với nghiệp vụ không |
| `Flow.Subscriber.onComplete()` | Publisher đã kết thúc thành công | Dữ liệu đã parse/ghi DB thành công chưa |
| `Flow.Subscriber.onError(e)` | Lỗi nhận/chuyển body | Có thể xử lý body như thành công |
| `HttpResponse<String>` thành công với `ofString` | Chuỗi body đã được tạo đầy đủ | JSON/schema/checksum nghiệp vụ đã hợp lệ |
| `HttpResponse<Path>` thành công với `ofFile` | Body đã được ghi đầy đủ vào file | File đã được kiểm tra nội dung/virus/hash hoặc commit cuối |

**HTTP status là thông tin từ header**, không phải xác nhận body đã toàn vẹn. `Content-Length` cũng chỉ là giá trị được công bố; nếu server gửi thiếu byte, client có thể báo lỗi hoặc việc đọc không hoàn tất theo framing. Khi thực hiện download quan trọng, so sánh byte count/hash/ETag hoặc metadata do API cung cấp **theo đúng ngữ nghĩa của từng giao thức**, đồng thời xác minh tính toàn vẹn ở mức ứng dụng.

Body có thể rỗng hợp lệ (ví dụ status `204` không có payload), nên không có yêu cầu “bất kỳ request thành công nào cũng phải có body dài hơn 0”. Hãy kiểm tra HTTP method/status và contract cụ thể trước khi giả định body có nội dung.

## 11. Lỗi và hủy công việc ở các mốc khác nhau

### 11.1 Lỗi trước header

DNS, kết nối, TLS handshake, request timeout hay lỗi gửi request có thể làm `send` ném `IOException`/`InterruptedException` hoặc `sendAsync` hoàn thành ngoại lệ **trước khi có `HttpResponse`**. Khi đó status/header chưa có để đọc.

### 11.2 Lỗi sau header, khi đang đọc body

Với streaming handler, client có thể đã đưa ra `HttpResponse` status 200, nhưng `InputStream.read` còn có thể ném `IOException` hoặc `Flow.Publisher` phát `onError`. Một cơ chế giám sát đúng nên có các trạng thái riêng như `HEADERS_RECEIVED`, `BODY_IN_PROGRESS`, `BODY_COMPLETE` và `BODY_FAILED`.

Khi dùng `ofString`/`ofFile`, lỗi body trong quá trình tích lũy/ghi thường khiến `send` hoặc `sendAsync` thất bại thay vì cung cấp giá trị `String`/`Path` hoàn chỉnh. Tuy nhiên nếu đang ghi file, dữ liệu dở dang **có thể còn lại trên đĩa**; phải cleanup theo chính sách.

### 11.3 Hủy future không đồng nghĩa mọi bên đã ngừng ngay

Với `CompletableFuture` và HTTP I/O, việc hủy/interrupt ở phía client cần được hiểu theo tài liệu phiên bản JDK đang chạy. Đừng hứa rằng `future.cancel(true)` đảm bảo server không còn xử lý request hoặc những byte đã gửi được thu hồi. Hãy quản lý timeout, close tài nguyên còn mở và logic bù trừ/idempotency theo nghiệp vụ.

Khi body là `InputStream` hoặc `Stream<String>`, trách nhiệm **đóng body sau khi không dùng nữa** vẫn rất quan trọng, kể cả ở nhánh lỗi hoặc khi chỉ cần xem headers. Không để resource rò rỉ vì tưởng future đã xong tức connection đã giải phóng.

## 12. Đặt mốc log/metrics và trạng thái nghiệp vụ

Các tên mốc nên nói đúng sự kiện:

| Tên trạng thái minh họa | Trigger | Dùng để đo |
|---|---|---|
| `HEADERS_RECEIVED` | `BodyHandler.apply(ResponseInfo)` hoặc response streaming bắt đầu có status/header | Thời điểm status + header sẵn sàng |
| `BODY_STREAM_OPEN` | `HttpResponse<InputStream>` đã được cấp | Body có thể bắt đầu được tiêu thụ |
| `BODY_BYTES_RECEIVED` | `onNext` hoặc lệnh `read` thu byte | Tiến độ số byte |
| `BODY_COMPLETE` | EOF hợp lệ, subscriber `onComplete`, hoặc future của handler tích lũy thành công | Hoàn tất body theo loại handler |
| `BODY_FAILED` | Lỗi đọc, subscriber `onError` hoặc future thất bại | Lỗi body |
| `VALIDATED` | Kiểm tra schema, hash, size, parse thành công | Tính đúng nội dung |
| `COMMITTED` | File được chuyển vào vị trí chính thức hoặc tác vụ DB hoàn tất | Thành công nghiệp vụ thực sự |

Nếu cần đo “time to first byte” hay “time to headers”, phải chọn đúng tín hiệu đo. **Thời điểm future của `ofString` hoàn tất không phải thời điểm nhận byte đầu tiên hoặc header đầu tiên**; đó thường là mốc nhận và chuyển đổi body xong. Với streaming `ofInputStream`, thời điểm future hoàn tất gần mốc headers sẵn sàng, nhưng chưa đo đủ thời gian tiêu thụ response.

Nếu sản phẩm hiển thị progress download, số byte `read` hoặc các lô `onNext` phản ánh tiến độ phù hợp hơn chỉ báo “HttpResponse có mặt”. Với mã status HTTP 4xx/5xx, chỉ được đánh dấu **thành công nghiệp vụ** nếu API quy định như vậy; đa số trường hợp phải phân loại lỗi dù body đã đọc xong.

## 13. Ma trận kiểm thử cần có

| Ca | Cách thiết lập | Kết quả cần assert |
|---|---|---|
| `ofString`, body hai đợt | Server gửi A rồi giữ B bằng latch | Future chưa xong trước B; cuối cùng body AB |
| `ofInputStream`, body hai đợt | Server gửi headers và A, giữ B | Future có response sớm; stream nhận A rồi B |
| `BodyHandler` tự viết | Handler đọc `ResponseInfo.statusCode()` | Handler được gọi trước khi body đủ |
| `ofFile`, body hai đợt | Server gửi RE, giữ ADY | Future chưa hoàn tất; file cuối chứa READY |
| `ofPublisher`, body hai đợt | Subscriber nhận A, server chưa gửi B | Response có; `onComplete` chưa có; sau B thì hoàn tất |
| `ofLines` | Server gửi một dòng rồi tiếp tục | Duyệt stream có thể chờ dòng tiếp theo/EOF |
| Status 404 với body | Server trả 404 và thông báo lỗi | Handler chuẩn vẫn nhận body; app phân loại 404 |
| Body 0 byte | Server gửi 204 hoặc 200 body rỗng hợp lệ | Không giả định thiếu body là lỗi |
| Body lỗi sau headers | Server cắt truyền thiếu độ dài công bố | Không ghi “download success” chỉ vì status 200 |
| Không có Content-Length | Server dùng chunked/streaming | Logic dựa trên EOF/subscriber completion thay vì header length |
| Client dừng sớm | Đọc một phần rồi close InputStream | Không để resource mở; xử lý kết quả chưa đủ |
| Body vượt giới hạn | Server gửi hơn max bytes | Dừng xử lý theo chính sách và đóng/cleanup |
| Download file lỗi | Server ngắt giữa chừng | Xóa hoặc đánh dấu file tạm chưa hoàn chỉnh |
| Flow subscriber không request | Publisher đã được trả | Không có giả định body sẽ tự tiêu thụ xong |
| Flow subscriber báo lỗi | `onError` đến sau headers | Chuyển trạng thái BODY_FAILED, không báo thành công |

Trong test, dùng `CountDownLatch` hoặc server có tín hiệu điều phối để biết chính xác lúc server đã gửi đoạn đầu, sau đó cố ý giữ đoạn cuối. **Không** dùng `Thread.sleep(100)` rồi kết luận future “chắc chắn đã nhận header”: đó là bài test phụ thuộc scheduler và mạng, dễ flaky.

Ba chương trình trong bài dùng HTTP local và giới hạn chờ 5 giây để thất bại rõ khi có lỗi; chúng không đo throughput hoặc SLA của mạng ngoài.

## 14. Những hiểu nhầm dễ gây lỗi

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| `sendAsync(...ofInputStream())` future thành công = download xong | Body còn đang được stream | Đọc đến EOF/đóng stream, xác minh nội dung |
| `send(...ofInputStream())` đồng bộ = body chắc chắn đủ | `send` có thể trả khi header đã có | Xét BodyHandler, không chỉ send/sendAsync |
| `statusCode() == 200` = body toàn vẹn | Header đến trước body, lỗi còn có thể xảy ra | Đọc đủ và kiểm tra kết quả |
| `Content-Length` tồn tại = client đã nhận đủ | Chỉ là thông tin framing do server công bố | Dựa vào body completion, đếm/hash khi cần |
| `BodyHandlers.ofPublisher()` trả publisher = đã xử lý dữ liệu | Cần subscribe, request và chờ onComplete | Quản lý Flow.Subscriber đúng hợp đồng |
| Không subscribe vào publisher nhưng kết thúc request | Có thể giữ resource/không tiến triển | Subscribe đúng một lần hoặc chọn handler khác |
| Bỏ qua `InputStream.close()` | Có thể rò tài nguyên/kết nối | Dùng try-with-resources |
| Dùng `readAllBytes` với tệp rất lớn | Nạp toàn bộ RAM | Dùng streaming có quota hoặc ofFile |
| Nghĩ `BodyHandler.apply` có thể thấy body hoàn chỉnh | Callback chạy ở giai đoạn header | Handler chọn BodySubscriber; subscriber đọc body |
| Ghi “xong” khi future được cấp với `ofLines` | Stream<String> chưa chắc tiêu thụ xong | Terminal operation và close |
| Xem HTTP 404 như lỗi được ném tự động | Handler chuẩn vẫn có response | Kiểm tra status và body lỗi |
| Đặt trạng thái commit ở `onComplete` mà chưa parse/ghi xong | Hoàn tất nhận bytes không phải hoàn tất nghiệp vụ | Xác minh schema, hash, commit độc lập |
| Dùng retry sau khi body lỗi mà không xét idempotency | Server có thể đã xử lý request | Phân loại retry và chống trùng theo API |
| Không dọn file dở dang khi ofFile lỗi | File chưa hoàn chỉnh có thể còn trên disk | Dùng file tạm và cleanup/atomic move |

## 15. Bài tập tự luyện có đáp án

**1.** Lời gọi `sendAsync(request, BodyHandlers.ofString())` đã hoàn tất thành công. Có thể kết luận gì?  
**Đáp án:** BodySubscriber đã tạo xong `String` của response, do đó body cho handler này đã được nhận/giải mã đầy đủ. Không tự suy rằng JSON hợp lệ hoặc status là 2xx.

**2.** `sendAsync(request, BodyHandlers.ofInputStream())` trả `HttpResponse<InputStream>` có status 200. Có thể báo tệp download thành công chưa?  
**Đáp án:** chưa. Body còn có thể đang truyền; phải đọc/ghi và xác minh tới mốc hoàn thành, xử lý IOException và đóng stream.

**3.** BodyHandler tùy biến đọc status trước khi body tới, có vi phạm giao thức Java 11 không?  
**Đáp án:** không. `apply(ResponseInfo)` được gọi khi status/headers đã có, trước khi body bytes được đọc vào subscriber.

**4.** Vì sao `ofPublisher` trả `HttpResponse` rồi vẫn chưa nhận `onComplete`?  
**Đáp án:** response có thể được cung cấp sau headers; publisher cần subscriber và demand, và chỉ báo kết thúc body ở `onComplete` hoặc lỗi ở `onError`.

**5.** Server công bố `Content-Length: 10000`. Client đã nhận headers và đọc 100 byte. Download hoàn tất chưa?  
**Đáp án:** chưa. Độ dài công bố không bảo đảm dữ liệu đã đến; cần đọc đủ theo framing, xác minh nếu hệ thống yêu cầu.

**6.** Tại sao `BodyHandlers.ofFile(path)` có thể là lựa chọn tốt hơn `ofByteArray()` cho phản hồi lớn?  
**Đáp án:** handler ghi body thành file thay vì giữ toàn bộ mảng byte trong RAM. Future chỉ hoàn tất sau khi ghi xong; vẫn phải quản lý file tạm và tính toàn vẹn.

**7.** Sau khi gọi `response.body()` với `ofLines`, bạn đã có đủ mọi dòng chưa?  
**Đáp án:** chưa chắc. Cần duyệt `Stream<String>` đến hết theo hợp đồng và đóng stream.

**8.** Client đã nhận header `200`, sau đó kết nối đứt khi stream mới đọc nửa body. Đây là lỗi ở mốc nào?  
**Đáp án:** body failed **sau headers**. `HttpResponse` có thể đã tồn tại, nhưng nghiệp vụ phải báo thất bại/partial và dọn tài nguyên.

**9.** Có cần chờ `onComplete` rồi mới viết từng chunk dữ liệu của publisher vào file không?  
**Đáp án:** không. Xử lý từng chunk theo demand để tránh giữ toàn bộ body trong RAM; chỉ **xác nhận file hoàn tất** sau `onComplete` và bước kiểm tra/đóng/commit thích hợp.

## 16. Tài liệu chính thức

- [Java SE 11 — HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): `apply(ResponseInfo)` được gọi ở mốc status/header, trước body.
- [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): thời điểm trả response của `ofString`, `ofFile`, `ofInputStream`, `ofLines` và `ofPublisher`.
- [Java SE 11 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): hợp đồng subscriber và nội dung `getBody()`.
- [Java SE 11 — HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `body()` có thể là dữ liệu đã nhận hoặc một object dùng để đọc tiếp.
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, lỗi và vòng đời request.
- [Java SE 11 — Flow](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.html): `Publisher`, `Subscriber`, `Subscription.request`, `onComplete/onError`.
- [Java SE 11 — HttpServer](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server loopback dùng trong chương trình kiểm thử.

**Nguyên tắc áp dụng:** Khi đánh giá một HTTP response, trước tiên hỏi **BodyHandler nào đang sử dụng?**. Với handler tích lũy, response hoàn tất thường nghĩa là body đã được tạo đầy đủ. Với handler streaming, response có thể xuất hiện ngay sau headers; phải theo dõi **đọc hết body, lỗi, cleanup và validation** trước khi đánh dấu hoàn tất công việc.