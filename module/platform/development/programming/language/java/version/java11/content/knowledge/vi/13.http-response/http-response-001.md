# `HttpResponse<T>` và kiểu phần thân trong Java 11+

## 1. Vì sao `HttpResponse<T>` có tham số kiểu `T`?

Khi gửi HTTP request, server trả về **status code**, **response headers** và có thể có **response body**. Status/header có cấu trúc chung nhưng body có thể là JSON, text tiếng Việt, tệp ảnh, dữ liệu nhị phân, nội dung cần đọc theo luồng hoặc hoàn toàn không cần giữ lại. Java 11 dùng kiểu tổng quát:

~~~java
public interface HttpResponse<T> {
    T body();
    // Cùng nhiều phương thức metadata khác.
}
~~~

Trong đó **`T` là kiểu Java của giá trị body sau khi được `BodyHandler<T>` xử lý**, *không phải* kiểu của HTTP status, kiểu media (MIME) hoặc kiểu object mà server tự động gửi tới.

Ví dụ cùng một URL có thể được nhận theo những cách khác nhau:

~~~java
HttpResponse<String> text = client.send(
        request, HttpResponse.BodyHandlers.ofString());

HttpResponse<byte[]> raw = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

HttpResponse<InputStream> streaming = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
~~~

Đây là **ba lời gọi độc lập minh họa cùng một ý**, không phải chương trình tự chạy; cần tạo `client` và `request`, import `HttpResponse`/`InputStream`, xử lý `IOException` và `InterruptedException`. Ba lời gọi trên gửi **ba request HTTP**, chứ không phải đọc lại một response bằng ba định dạng. Với streaming body, caller phải đóng stream sau khi sử dụng.

**Trọng tâm cần nhớ:**

- `HttpResponse<String>` có `response.body()` trả `String`.
- `HttpResponse<byte[]>` có `response.body()` trả `byte[]`, giữ byte gốc.
- `HttpResponse<Path>` có `response.body()` trả một `Path` trỏ tới tệp đã ghi.
- `HttpResponse<InputStream>` có `response.body()` trả `InputStream`, dữ liệu có thể vẫn đang tới.
- `HttpResponse<Stream<String>>` có `response.body()` trả stream các dòng.
- `HttpResponse<Void>` (với `BodyHandlers.discarding()`) không giữ nội dung body: `body()` là `null`.

`java.net.http.HttpResponse` là API chuẩn từ Java 11 và tiếp tục được duy trì. Cần phân biệt rõ phần API sẵn có ở Java 11 với những phương thức được bổ sung trên JDK mới nếu viết mã phải tương thích `--release 11`.

## 2. Vị trí của `HttpResponse<T>` trong quy trình giao tiếp

~~~text
HttpClient ── send/sendAsync ─────────────────────────────────┐
    |                                                        |
    v                                                        |
HttpRequest                                                  |
    URI + method + request headers + BodyPublisher            |
    |                                                        |
    v                                                        |
HTTP server trả status + response headers + response bytes   |
    |                                                        |
    v                                                        |
BodyHandler<T>.apply(ResponseInfo)                            |
    Chọn BodySubscriber<T> theo status/headers                 |
    |                                                        |
    v                                                        |
BodySubscriber<T> nhận byte, có thể lưu/giải mã/stream         |
    |                                                        |
    v                                                        |
HttpResponse<T>                                               |
    statusCode(), headers(), uri(), version(), request()      |
    body() có kiểu T tương ứng BodyHandler<T>                 |
    └────────────────────────────────────────────────────────┘
~~~

Các trách nhiệm không trùng nhau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `HttpClient` | Gửi/nhận HTTP, cấu hình kết nối, đồng bộ hoặc bất đồng bộ | `client.send(request, handler)` |
| `HttpRequest` | Mô tả yêu cầu gửi đến server | `GET /articles`, header `Accept` |
| `HttpRequest.BodyPublisher` | Cung cấp **request body** nếu có | `BodyPublishers.ofString(json)` |
| `HttpResponse.BodyHandler<T>` | Lựa chọn cách nhận **response body** sau khi biết status/headers | `BodyHandlers.ofString(UTF_8)` |
| `HttpResponse.BodySubscriber<T>` | Thực sự tiêu thụ các byte response và tạo giá trị kiểu `T` | Giải mã text, tích lũy byte, ghi file |
| `HttpResponse<T>` | Đối tượng kết quả gồm metadata và body kiểu `T` | `response.statusCode()`, `response.body()` |

**Phân biệt hai chiều:** `BodyPublisher` gửi dữ liệu từ client *đi ra*, còn `BodyHandler/BodySubscriber` xử lý dữ liệu từ server *đi vào*. `HttpResponse<T>` không tự chọn kiểu body dựa vào generic khi chạy; **`BodyHandler<T>` được truyền lúc gọi `send`/`sendAsync` mới là thứ quyết định** cách biểu diễn body.

## 3. Cơ chế generic: kiểu của `body()` được xác định tại điểm gọi

Chữ ký chính (tối giản):

~~~java
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
        throws IOException, InterruptedException;

<T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler);
~~~

Điều này giúp Java kiểm tra kiểu ngay khi biên dịch:

~~~java
HttpResponse<String> a = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
String bodyText = a.body();

HttpResponse<byte[]> b = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());
byte[] bodyBytes = b.body();
~~~

Các dòng trên **minh họa cú pháp**, cần biến `client`, `request` và imports phù hợp để chạy. Hai dạng không thay thế được cho nhau:

~~~java
// LỖI BIÊN DỊCH: BodyHandler<byte[]> không phải BodyHandler<String>.
// HttpResponse<String> wrong = client.send(
//         request, HttpResponse.BodyHandlers.ofByteArray());
~~~

Ký hiệu `<T>` hỗ trợ **type safety**, không có nghĩa server gửi class Java đã được serialize hay JDK tự parse JSON. Nếu body là JSON, `ofString` cho một chuỗi JSON; muốn thành `UserDto` phải có bước parse/validate bằng thư viện JSON hoặc logic riêng theo schema.

Java generic có **type erasure**. `HttpResponse<List<User>>` không thể tự khiến HTTP Client hiểu định dạng `List<User>` qua runtime generic type; phải thiết kế `BodyHandler`/`BodySubscriber` và bộ giải mã thật. Không dùng cast thiếu kiểm chứng để “biến” `HttpResponse<String>` thành `HttpResponse<User>`.

### Hai phần trong `HttpResponse<T>` độc lập nhau

Metadata như `statusCode()` và `headers()` **không đổi kiểu** khi `T` đổi. Ví dụ response có status 404 vẫn có thể là `HttpResponse<String>`, `HttpResponse<byte[]>` hoặc `HttpResponse<Void>` tùy handler. Tham số `T` chỉ phản ánh **giá trị của body()**.

Ngoài ra, `response.body()` có thể là `null` ở những handler được thiết kế bỏ body (như `discarding()`) hoặc trong các tình huống đặc biệt được API mô tả. **Không suy từ `HttpResponse<T>` sang bảo đảm `body()` luôn khác null** nếu handler của bạn không đưa ra hợp đồng đó.

## 4. Các `BodyHandlers` phổ biến trong Java 11

Dưới đây là những factory có sẵn từ Java 11 và vẫn dùng được ngày nay:

| `BodyHandler` | Kiểu của `HttpResponse<T>` | Giá trị `body()` và tình huống |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `HttpResponse<String>` | Giải mã text theo charset ở `Content-Type`; không có/không hỗ trợ thì dùng UTF-8 |
| `BodyHandlers.ofString(charset)` | `HttpResponse<String>` | Giải mã text theo charset được cung cấp rõ ràng |
| `BodyHandlers.ofByteArray()` | `HttpResponse<byte[]>` | Tích lũy toàn bộ bytes, không giải mã chữ |
| `BodyHandlers.ofFile(path)` | `HttpResponse<Path>` | Ghi toàn bộ body vào tệp, trả đường dẫn |
| `BodyHandlers.ofFile(path, options...)` | `HttpResponse<Path>` | Như trên, chọn rõ quy tắc tạo/ghi file |
| `BodyHandlers.ofInputStream()` | `HttpResponse<InputStream>` | Đọc body dạng luồng; **phải tiêu thụ hoặc đóng** |
| `BodyHandlers.ofLines()` | `HttpResponse<Stream<String>>` | Stream từng dòng text, **phải tiêu thụ hoặc đóng** |
| `BodyHandlers.discarding()` | `HttpResponse<Void>` | Nhận và bỏ nội dung body; `body() == null` |
| `BodyHandlers.replacing(value)` | `HttpResponse<U>` | Bỏ bytes của body, trả giá trị thay thế đã cung cấp |
| `BodyHandlers.ofPublisher()` | `HttpResponse<Flow.Publisher<List<ByteBuffer>>>` | Tiêu thụ qua Reactive Streams `Flow`, điều phối backpressure |
| `BodyHandlers.buffering(handler, n)` | `HttpResponse<T>` | Bọc handler khác với buffer chuyển tiếp, **không** tự thay kiểu body |

**Lựa chọn đúng kiểu không có nghĩa đã hoàn tất yêu cầu nghiệp vụ.** Phải kiểm tra status HTTP, giới hạn dung lượng và validate nội dung sau khi nhận. Các factory có sẵn **không tự phân nhánh 2xx/4xx**: `ofString` vẫn đọc body của response 404, `ofFile` vẫn có thể ghi nội dung response lỗi ra tệp nếu không có quy tắc kiểm tra status.

### `ofString()` và `ofString(Charset)`

~~~java
HttpResponse<String> byHeader = client.send(
        request, HttpResponse.BodyHandlers.ofString());

HttpResponse<String> explicitUtf8 = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Hai đoạn này là mã minh họa của **hai lần gửi độc lập**; không phải cách đọc hai lần cùng một response. Với `ofString()`, charset lấy từ response header `Content-Type`; khi không có charset được hỗ trợ thì mặc định UTF-8 theo hợp đồng API. Với `ofString(StandardCharsets.UTF_8)`, bạn **chủ động** chỉ định cách chuyển bytes thành ký tự.

Nếu server khai báo sai charset, text có thể bị lỗi ký tự (mojibake). Không dùng `new String(bytes)` với charset mặc định của môi trường khi hợp đồng của endpoint là UTF-8. Khi cần xác minh dữ liệu ở mức byte, dùng `ofByteArray()` và tự thực hiện giải mã có chính sách lỗi phù hợp.

**`Content-Type: application/json` không khiến `ofString()` parse JSON.** Kết quả vẫn là `String` chứa JSON text; cần parse và kiểm tra schema bằng công cụ phù hợp.

### `ofByteArray()` và phân biệt text/binary

~~~java
HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

byte[] bytes = response.body();
int firstUnsigned = bytes.length > 0 ? Byte.toUnsignedInt(bytes[0]) : -1;
~~~

Đây là mã minh họa trong ngữ cảnh đã có client/request. `byte[]` trong Java lưu byte signed (`-128..127`); `Byte.toUnsignedInt` chuyển một byte về giá trị `0..255` khi cần biểu diễn. Không lấy `new String(bytes, UTF_8)` đối với ảnh, ZIP hoặc dữ liệu nhị phân tùy ý — có thể thay đổi ý nghĩa hoặc mất dữ liệu khi decode không hợp lệ.

`ofString` và `ofByteArray` **tích lũy toàn bộ body** trước khi giá trị cuối cùng sẵn sàng theo handler. Dùng với response có kích thước đáng tin cậy/được giới hạn; không tự coi chúng an toàn cho tải về nhiều GB hoặc response từ nguồn không đáng tin.

## 5. `ofFile()`: nhận response trực tiếp thành `Path`

Khi tải nội dung lớn, thường muốn ghi vào tệp thay vì giữ toàn bộ ở RAM:

~~~java
Path destination = Path.of("downloads", "report.bin");

HttpResponse<Path> saved = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(
                destination,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE));

Path savedPath = saved.body();
~~~

Đoạn này là **mã minh họa**, cần tạo thư mục `downloads` trước, khai báo client/request, import `Path`/`StandardOpenOption`, xử lý I/O. `CREATE_NEW` từ chối mở nếu tệp đã tồn tại, hữu ích khi không được ghi đè; các open option phải phù hợp với chính sách hệ thống.

Điểm quan trọng:

- `HttpResponse<Path>.body()` **là đường dẫn tệp**, không phải byte array hay nội dung file đã được parse.
- Với `ofFile`, khi `HttpResponse` được trả về thành công, body đã được ghi hoàn tất vào tệp theo hợp đồng của handler.
- `ofFile(path)` có tùy chọn mở tệp mặc định của API; nếu cần bảo đảm không ghi lên dữ liệu cũ, **chọn option tường minh** như `CREATE_NEW, WRITE` và xử lý tệp tồn tại.
- Handler có thể ghi **body của 404/500** vào tệp. Kiểm tra status trước khi sử dụng file như một tài liệu hợp lệ; với tải xuống phải bảo toàn dữ liệu, cân nhắc tải vào tệp tạm, validate status/content/checksum rồi đổi tên an toàn.
- Khi quá trình tải thất bại, tệp có thể đã được tạo và chỉ chứa một phần dữ liệu. Ứng dụng phải có chiến lược cleanup.
- Không đặt `Path` đích từ input thiếu tin cậy mà không kiểm tra; tránh path traversal, quyền ghi và overwriting. Đừng dựa vào tên tệp do server khai báo mà bỏ qua validation.

**`ofFile` không giống `ofInputStream`:** trường hợp đầu chuyển toàn bộ body vào tệp trước khi trả kết quả; trường hợp sau có thể trả về khi body còn đang truyền.

## 6. `ofInputStream()` và `ofLines()`: streaming response body

### `ofInputStream()` cho dữ liệu byte chạy theo luồng

~~~java
HttpResponse<InputStream> streamed = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream in = streamed.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        // Xử lý đúng n byte; lưu ý giới hạn kích thước và backpressure.
    }
}
~~~

Đây là **đoạn minh họa** trong method đã có `client` và `request`, import `InputStream`, xử lý checked exceptions. Theo hợp đồng, `HttpResponse<InputStream>` có thể trở về sau khi nhận headers **trước khi toàn bộ body đến**. Vì vậy `send(...)` trả xong **không chứng minh response body đã đọc xong**.

**Quy tắc tài nguyên:** đọc stream đến EOF hoặc đóng nó nếu không muốn đọc tiếp. Dừng sau khi đọc một phần mà không đóng có thể giữ kết nối/resources. Đóng trước EOF có thể làm HTTP client không thể tái sử dụng kết nối đó.

Nếu dùng `sendAsync(..., ofInputStream())`, future cũng có thể hoàn tất khi đã có stream chứ không phải khi toàn bộ bytes được tiêu thụ. Ứng dụng chịu trách nhiệm cho giai đoạn đọc body tiếp theo, kể cả timeout và giới hạn kích thước ngoài handler.

### `ofLines()` cho dữ liệu text theo dòng

~~~java
HttpResponse<Stream<String>> linesResponse = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = linesResponse.body()) {
    lines.forEach(System.out::println);
}
~~~

Đoạn mã minh họa: `Stream` cần import `java.util.stream.Stream`; mỗi phần tử tương ứng một dòng được giải mã theo charset của response. `ofLines()` trong Java 11 cũng có thể trả về trước khi body nhận xong.

Các dòng được tách theo quy tắc của `BufferedReader.readLine()`. **Ký tự xuống dòng không được giữ nguyên** trong từng `String`, nên không dùng `ofLines` nếu nghiệp vụ cần tái lập đúng byte gốc hoặc kiểu line ending. Với file text lớn, streaming từng dòng có thể tiết kiệm bộ nhớ hơn `ofString`.

Lưu ý `Stream<String>` chỉ **tiêu thụ một lần** theo quy tắc stream của Java. Đừng vừa gọi `count()` rồi cố gọi `forEach()` trên chính stream đã tiêu thụ. `try-with-resources` là lựa chọn thích hợp để đóng stream dù xử lý thành công hay lỗi.

### `ofPublisher()` dành cho backpressure nâng cao

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> reactive = client.send(
        request, HttpResponse.BodyHandlers.ofPublisher());
~~~

Đoạn minh họa trên cần import `java.util.concurrent.Flow`, `java.util.List` và `java.nio.ByteBuffer`; không phải chương trình độc lập.

`Flow.Publisher<List<ByteBuffer>>` cho phép xử lý body bằng mô hình subscriber với `request(n)`/`cancel()`, phù hợp khi cần kiểm soát nhu cầu tiêu thụ byte. Publisher của handler này **chỉ chấp nhận một subscriber thực sự**; mọi subscriber bổ sung nhận lỗi theo hợp đồng. Nếu ứng dụng không subscribe/không hủy đúng cách, vòng đời exchange có thể bị giữ lại. Không dùng publisher chỉ vì muốn “async” nếu `ofInputStream` hoặc `ofFile` đáp ứng tốt nhu cầu đơn giản hơn.

## 7. `Void` và response không cần body

Có những request chỉ cần biết HTTP status hoặc headers, ví dụ ping nghiệp vụ, endpoint cập nhật chỉ trả kết quả trạng thái, hoặc response 204 No Content.

~~~java
HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding());

System.out.println(response.statusCode());
System.out.println(response.body() == null); // true
~~~

Mẫu này **đọc và bỏ dữ liệu response** theo handler, không có `String` rỗng để sử dụng. Giá trị `null` ở `body()` là hành vi có chủ đích của `BodyHandlers.discarding()`.

Cần phân biệt:

- **Không có body ở tầng HTTP** (chẳng hạn response 204) là một sự kiện của giao thức.
- **Không giữ body theo `BodyHandler<Void>`** là lựa chọn của client, có thể xảy ra ngay cả khi server thực sự gửi body.
- `HttpResponse<String>` với handler text có thể nhận chuỗi rỗng cho response không có byte dữ liệu. `""` và `null` có ý nghĩa Java khác nhau.
- Với `BodyHandlers.replacing(value)`, dữ liệu body được bỏ đi nhưng `body()` trả chính giá trị `value` đã cung cấp. Không nhầm response đó với dữ liệu server đã gửi.

`HttpResponse<Void>` vẫn cung cấp `statusCode()`, `headers()`, `request()`, `uri()` và `version()`. Vì vậy chọn `Void` không khiến việc kiểm tra lỗi HTTP biến mất.

## 8. Ví dụ Java 11 hoàn chỉnh với nhiều kiểu body

Ví dụ dùng `com.sun.net.httpserver.HttpServer` (module **`jdk.httpserver`**) mở server HTTP nội bộ trên loopback để không cần Internet hoặc tài khoản API. Server có endpoint trả text tiếng Việt, bytes nhị phân, HTTP 404 và response 204. Cùng một `HttpClient` được dùng nhiều lần với các `BodyHandler` khác nhau.

Tạo tệp **HttpResponseBodyTypesDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
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
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.Arrays;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class HttpResponseBodyTypesDemo {
    private static final byte[] BINARY = {0, 1, 2, (byte) 255};

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/text", exchange -> respond(
                exchange, 200,
                "Xin chào\nDòng 2\n".getBytes(StandardCharsets.UTF_8),
                "text/plain; charset=UTF-8"));
        server.createContext("/binary", exchange -> respond(
                exchange, 200, BINARY, "application/octet-stream"));
        server.createContext("/missing", exchange -> respond(
                exchange, 404,
                "Not found".getBytes(StandardCharsets.UTF_8),
                "text/plain; charset=UTF-8"));
        server.createContext("/empty", exchange ->
                respond(exchange, 204, new byte[0], "text/plain"));
        server.start();

        Path folder = Files.createTempDirectory("http-body-types-");
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            HttpResponse<String> text = client.send(
                    request(base, "text"),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("textStatus=" + text.statusCode());
            System.out.println("textHeader=" +
                    text.headers().firstValue("X-Trace").orElse("missing"));
            System.out.println("textLines=" +
                    text.body().lines().collect(Collectors.joining("|")));

            HttpResponse<byte[]> bytes = client.send(
                    request(base, "binary"),
                    HttpResponse.BodyHandlers.ofByteArray());
            System.out.println("binaryLength=" + bytes.body().length);
            System.out.println("lastByteUnsigned=" +
                    Byte.toUnsignedInt(bytes.body()[3]));

            Path destination = folder.resolve("download.bin");
            HttpResponse<Path> file = client.send(
                    request(base, "binary"),
                    HttpResponse.BodyHandlers.ofFile(
                            destination,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE));
            System.out.println("filePathMatches=" +
                    file.body().equals(destination));
            System.out.println("fileBytesMatch=" +
                    Arrays.equals(Files.readAllBytes(file.body()), BINARY));

            HttpResponse<InputStream> streamed = client.send(
                    request(base, "text"),
                    HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream in = streamed.body()) {
                System.out.println("streamTextMatch=" +
                        new String(in.readAllBytes(), StandardCharsets.UTF_8)
                                .equals("Xin chào\nDòng 2\n"));
            }

            HttpResponse<Stream<String>> lines = client.send(
                    request(base, "text"),
                    HttpResponse.BodyHandlers.ofLines());
            try (Stream<String> bodyLines = lines.body()) {
                System.out.println("lineCount=" + bodyLines.count());
            }

            HttpResponse<String> missing = client.send(
                    request(base, "missing"),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("missingStatus=" + missing.statusCode());
            System.out.println("missingBody=" + missing.body());

            HttpResponse<Void> empty = client.send(
                    request(base, "empty"),
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("discardBodyIsNull=" + (empty.body() == null));
        } finally {
            server.stop(0);
            Files.deleteIfExists(folder.resolve("download.bin"));
            Files.deleteIfExists(folder);
        }
    }

    private static HttpRequest request(URI base, String resource) {
        return HttpRequest.newBuilder(base.resolve(resource))
                .timeout(Duration.ofSeconds(5)).GET().build();
    }

    private static void respond(HttpExchange exchange, int status,
                                byte[] content, String contentType)
            throws IOException {
        try {
            exchange.getResponseHeaders().set("Content-Type", contentType);
            exchange.getResponseHeaders().set("X-Trace", "demo");
            if (status == 204) {
                exchange.sendResponseHeaders(status, -1);
            } else {
                exchange.sendResponseHeaders(status, content.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(content);
                }
            }
        } finally {
            exchange.close();
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 11 trở lên có `jdk.httpserver`**. Nếu dùng JDK mới, `--release 11` buộc trình biên dịch kiểm tra tương thích API/cú pháp Java 11:

~~~bash
javac --release 11 --add-modules jdk.httpserver HttpResponseBodyTypesDemo.java
java --add-modules jdk.httpserver HttpResponseBodyTypesDemo
~~~

**Stdout chính xác đã kiểm chứng** (JDK 24, Java 11 source/API compatibility):

~~~text
textStatus=200
textHeader=demo
textLines=Xin chào|Dòng 2
binaryLength=4
lastByteUnsigned=255
filePathMatches=true
fileBytesMatch=true
streamTextMatch=true
lineCount=2
missingStatus=404
missingBody=Not found
discardBodyIsNull=true
~~~

### Diễn giải các kết quả

1. `textStatus=200` và `textHeader=demo` đến từ metadata `HttpResponse<String>`, không phải text body. `headers().firstValue(...)` trả một `Optional<String>` vì một header có thể không có.
2. `textLines=Xin chào|Dòng 2` dùng `String.lines()` trên body đã nhận; hai dòng được nối để kiểm tra. Ký tự newline không được giữ trong từng phần tử.
3. `binaryLength=4` xác nhận body được nhận thành `byte[]` gồm bốn byte. Byte cuối là `(byte) 255`, biểu diễn dưới dạng signed `-1` trong Java; `Byte.toUnsignedInt` in ra `255`.
4. `filePathMatches=true`: `BodyHandlers.ofFile` trả `Path` đã cấu hình. `fileBytesMatch=true`: các byte file trùng `BINARY`. `CREATE_NEW` bảo vệ chống ghi lên tên file sẵn có.
5. `streamTextMatch=true`: response body kiểu `InputStream` được đọc hết và tự đóng bằng `try-with-resources`. Không đồng nhất `HttpResponse<InputStream>` với dữ liệu đã có đầy đủ lúc `send` trả về.
6. `lineCount=2`: `Stream<String>` từ `ofLines` được tiêu thụ một lần và đóng; đây là stream ký tự theo dòng, không phải mảng chứa toàn bộ dòng ngay từ đầu.
7. `missingStatus=404` **không ném `IOException`** chỉ vì server gửi lỗi HTTP; `missingBody=Not found` thể hiện `BodyHandlers.ofString` vẫn nhận body lỗi.
8. `discardBodyIsNull=true`: `BodyHandlers.discarding` trả `Void`/`null` đúng hợp đồng; server sử dụng 204 để minh họa một HTTP response không có body.

Ví dụ tự dọn tệp vừa ghi và thư mục tạm, đóng stream bằng `try-with-resources`, đồng thời dừng server HTTP nội bộ. Server dùng loopback, không gọi dịch vụ ngoài; môi trường bị cấm bind socket hoặc thiếu module `jdk.httpserver` cần được cấu hình phù hợp mới chạy được.

**Giới hạn của ví dụ:** đây là demo nhỏ dùng body có dung lượng rất thấp; phần `readAllBytes` chỉ hợp lý vì nội dung ngắn. Trong production, có thể cần đọc từng block/line, hạn chế số byte và kiểm soát deadline toàn bộ quá trình download.

## 9. Những metadata của `HttpResponse<T>` không phụ thuộc `T`

| Phương thức | Kết quả | Cần lưu ý |
| --- | --- | --- |
| `statusCode()` | `int`, ví dụ 200, 201, 204, 404, 500 | Không tự ném exception cho status 4xx/5xx |
| `headers()` | `HttpHeaders` | Tra cứu case-insensitive, giá trị header có thể vắng mặt hoặc có nhiều giá trị |
| `body()` | `T` theo `BodyHandler<T>` | Có thể chưa tiêu thụ hết bytes với streaming body |
| `request()` | `HttpRequest` liên quan đến response | Cung cấp thông tin request gắn với kết quả |
| `uri()` | `URI` của response | Có thể khác URI ban đầu sau redirect |
| `version()` | `HttpClient.Version` thực tế | Có thể khác phiên bản ưu tiên đã yêu cầu |
| `previousResponse()` | `Optional<HttpResponse<T>>` | Có thể liên quan các bước redirect; không dùng previous response để đọc lại mọi body |
| `sslSession()` | `Optional<SSLSession>` | Chỉ có khi ngữ cảnh TLS tương ứng hỗ trợ |

Ví dụ:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

int status = response.statusCode();
String contentType =
        response.headers().firstValue("Content-Type").orElse("unknown");
String body = response.body();
~~~

Đây là **mã minh họa**, chưa tự tạo client/request. Kiểm tra status và header nên diễn ra **trước khi tin rằng body có thể parse theo định dạng mong đợi**. Không dùng `response.body().toString()` cho `byte[]` để kiểm tra nội dung; mặc định Java chỉ cho tên lớp và mã băm, không in ra các byte.

### HTTP 4xx/5xx vẫn là response bình thường ở tầng protocol

Một HTTP server có thể trả `404 Not Found` cùng body text hoặc JSON giải thích lỗi. Khi dùng `BodyHandlers.ofString`, Java có thể tạo:

~~~java
HttpResponse<String> error = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

if (error.statusCode() >= 400) {
    // Ghi nhận HTTP error theo hợp đồng API và xử lý error.body().
}
~~~

Mã trên là **đoạn minh họa**. `IOException`, `HttpTimeoutException` hoặc `InterruptedException` chỉ xuất hiện theo hợp đồng I/O/deadline; **không tự sinh chỉ vì status == 404**.

Với response error có dữ liệu bí mật, đừng log nguyên body không kiểm soát. Để giảm rủi ro memory exhaustion, cần giới hạn dữ liệu response kể cả khi server báo lỗi và gửi một body khổng lồ.

## 10. `BodyHandler<T>` có thể chọn subscriber theo status/headers

Các factory `BodyHandlers.ofString()`/`ofFile()`/`ofByteArray()` **không tự đánh giá status**. Khi muốn thay đổi cách nhận body dựa trên response metadata *trước khi body bắt đầu truyền*, có thể cung cấp `BodyHandler<T>` tùy biến:

~~~java
HttpResponse.BodyHandler<String> handler = responseInfo -> {
    if (responseInfo.statusCode() >= 200
            && responseInfo.statusCode() < 300) {
        return HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
    }
    return HttpResponse.BodySubscribers.replacing("body ignored for error");
};
~~~

Đoạn mã là **minh họa độc lập về cách tạo một handler**; muốn gửi request thật vẫn cần client/request. Trong Java 11, `BodyHandler<T>` là functional interface nhận `ResponseInfo` (status/headers/version) và trả `BodySubscriber<T>`. Cả hai nhánh ở đây tạo `BodySubscriber<String>`, nên handler có kiểu `BodyHandler<String>`.

- Nhánh 2xx giải mã text bằng UTF-8.
- Nhánh khác bỏ bytes của response và trả chuỗi thay thế do ứng dụng cung cấp.
- **Chuỗi thay thế không phải body từ server**: nó chỉ là giá trị logic phía client.
- `BodyHandler` phù hợp để quyết định cách nhận body; nếu cần kiểm tra schema, MIME, giới hạn byte, bảo mật và báo lỗi HTTP, phải thiết kế đầy đủ hơn thay vì chỉ dựa vào status 2xx.

Khi không cần tối ưu đường đi nhận body theo status, thường đơn giản hơn là dùng `ofString` để nhận một response có kích thước giới hạn, sau đó kiểm tra `response.statusCode()` và parse nội dung theo schema.

### Tùy chỉnh thành đối tượng Java khác

Đối với API JSON trả về đối tượng, cách thông thường là:

~~~text
BodyHandler<String> nhận JSON bytes -> String
      |
      v
Kiểm tra status và Content-Type
      |
      v
JSON parser/validator tạo DTO, ví dụ UserDto
      |
      v
Ứng dụng tiếp tục xử lý đối tượng
~~~

Không gán `HttpResponse<UserDto>` khi handler trả `String`. Nếu muốn body trả thẳng `UserDto`, cần tự xây `BodySubscriber<UserDto>` hoặc dùng `BodySubscribers.mapping(...)` với một hàm parse hợp lệ; đó là **logic chuyển đổi do ứng dụng viết**, không phải hành vi mặc định của JDK. Không đưa mã JSON parser giả định khi chưa chọn thư viện/schema cụ thể.

## 11. Đồng bộ, bất đồng bộ và thời điểm body hoàn tất

Cùng một handler có thể dùng với `send` hoặc `sendAsync`:

~~~java
HttpResponse<byte[]> sync = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

CompletableFuture<HttpResponse<byte[]>> async = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofByteArray());
~~~

Hai đoạn minh họa yêu cầu đã có `client`/`request` và imports. Kết quả đồng bộ `HttpResponse<byte[]>` và kết quả bất đồng bộ `CompletableFuture<HttpResponse<byte[]>>` có **cùng logic body type**. `sendAsync` chỉ thay đổi cách nhận kết quả:

- `send(...)` có thể block thread và ném `IOException`/`InterruptedException`.
- `sendAsync(...)` trả một future; lỗi I/O/timeout thường khiến future hoàn tất exceptionally; `join()` có thể ném `CompletionException`.
- Với handler tích lũy toàn bộ (`ofString`, `ofByteArray`) hoặc ghi file (`ofFile`), `HttpResponse` xuất hiện khi body đã được nhận/xử lý theo handler.
- Với handler streaming (`ofInputStream`, `ofLines`, `ofPublisher`), `HttpResponse` có thể xuất hiện **trước** khi tất cả dữ liệu được nhận; caller phải tiếp tục tiêu thụ và/hoặc đóng/cancel.

**Đừng nghĩ `sendAsync` đồng nghĩa body luôn streaming.** `sendAsync(..., ofString())` vẫn đưa body về `String`; còn `send(..., ofInputStream())` là lời gọi đồng bộ *trả về một stream* có thể phải đọc tiếp.

### Timeout không tự giới hạn mọi lần đọc body streaming về sau

`HttpRequest.Builder.timeout(Duration)` có vai trò giới hạn việc nhận response theo hợp đồng của HTTP client, nhưng handler streaming có thể trả `HttpResponse` khi mới nhận headers. Vì vậy đừng sử dụng request timeout như một cam kết rằng bất kỳ `InputStream.read()` nào sau đó cũng tự có deadline và tốc độ tối thiểu.

Khi nhận payload lớn, cần chính sách riêng cho giới hạn byte, tốc độ/idle timeout, hủy tác vụ, đóng stream và deadline tổng của nghiệp vụ. Tương tự, `CompletableFuture.orTimeout(...)` chỉ quản lý trạng thái future theo hợp đồng của `CompletableFuture`, **không tự hoàn tác tác động server hoặc thay thế việc đóng resource**.

## 12. Lựa chọn body type theo nhu cầu thực tế

| Nhu cầu | Chọn handler | Lý do |
| --- | --- | --- |
| API trả text nhỏ/vừa có charset rõ | `ofString(UTF_8)` | Dùng ngay dưới dạng String |
| API trả JSON nhỏ/vừa | `ofString(UTF_8)` rồi parse JSON | Parser nằm ở logic ứng dụng |
| Tải ảnh nhỏ hoặc chữ ký/checksum cần bytes nguyên | `ofByteArray()` | Không chuyển byte thành ký tự |
| Tải tệp mà không cần giữ toàn bộ RAM | `ofFile(path, options)` | Ghi xuống file, trả Path |
| Xử lý download từng khối byte | `ofInputStream()` | Ứng dụng điều khiển đọc/đóng |
| Xử lý log/text dài từng dòng | `ofLines()` | Lấy Stream<String> theo dòng; cần đóng |
| Chỉ quan tâm status/headers | `discarding()` | Không giữ body |
| Reactive pipeline cần backpressure | `ofPublisher()` | Nhận Publisher, quản lý subscription |
| Cần quyết định handler từ status/headers | `BodyHandler<T>` tùy biến | Chọn BodySubscriber phù hợp |
| Cần DTO Java từ JSON | String/bytes + validator/parser riêng hoặc custom subscriber | JDK không parse JSON tự động |

**Lưu ý khi xử lý dữ liệu không tin cậy:** Giới hạn kích thước và kiểm soát kiểu nội dung trước khi đưa bytes vào parser hoặc RAM. Một số JDK mới có thêm API giới hạn body, nhưng khi viết mã chuẩn **Java 11** cần dùng các cơ chế giới hạn tương thích Java 11 hoặc chính sách streaming riêng; không đưa API mới vào mã biên dịch `--release 11`.

## 13. Những lỗi phổ biến và cách sửa

| Ngộ nhận/lỗi | Điều thực sự xảy ra | Cách xử lý |
| --- | --- | --- |
| “`HttpResponse<String>` là response JSON đã parse.” | Body là text String | Parse JSON, validate schema độc lập |
| “Gọi `client.send` mà không cần handler.” | API yêu cầu `BodyHandler<T>` | Chọn handler phù hợp |
| “`BodyPublisher` trả `HttpResponse<T>`.” | Publisher thuộc chiều **request** | Dùng BodyHandler cho chiều response |
| “Chọn generic `T` là Java tự chuyển bytes sang T.” | Handler mới quyết định chuyển đổi | Chọn/viết BodyHandler đúng kiểu |
| “`byte[]` cast được sang `String`.” | Hai kiểu khác nhau | Decode với charset đúng, khi thực sự là text |
| “`ofString` an toàn cho mọi dữ liệu nhị phân.” | Decode sai có thể làm mất byte gốc | Dùng `ofByteArray`/`ofFile`/stream |
| “`ofString`/`ofByteArray` vô hại khi response cực lớn.” | Có nguy cơ chiếm RAM lớn | Giới hạn body, streaming/file |
| “`ofFile` trả nội dung file trực tiếp.” | `body()` là `Path` | Dùng `Files` nếu cần đọc dữ liệu |
| “`ofFile` sẽ không bao giờ ghi đè file cũ.” | Phụ thuộc OpenOption | Dùng `CREATE_NEW` nếu phải chống ghi đè |
| “`ofFile` chỉ tải nếu status 200.” | Handler mặc định không xét status | Kiểm tra status, dùng handler/flow an toàn |
| “`ofInputStream` là body đã nhận đủ trước khi `send` trả về.” | Body có thể vẫn đang đến | Tiếp tục đọc và đóng đúng hợp đồng |
| “`Stream<String>` sau `ofLines` sử dụng lặp nhiều lần.” | Java Stream chỉ tiêu thụ một lần | Xử lý một lượt, đóng resource |
| “`ofLines` giữ nguyên byte xuống dòng.” | Trả dòng text không giữ line terminator | Dùng bytes/stream nếu cần bảo toàn |
| “`BodyHandlers.discarding` trả chuỗi rỗng.” | `HttpResponse<Void>.body() == null` | Không gọi method trên body null |
| “HTTP 404/500 tự ném `IOException`.” | Đây vẫn là HTTP response có status | Kiểm tra `statusCode()` |
| “Cùng handler, `sendAsync` luôn đọc nhanh hơn `send`.” | Khác cách chờ/kết hợp kết quả | Chọn theo kiến trúc, đo latency thực |
| “Thấy `HttpResponse` là tải xong toàn bộ streaming body.” | Có thể mới nhận xong headers | Đóng/tiêu thụ stream và quản lý deadline |
| “`Content-Type` luôn chính xác.” | Server có thể khai báo sai hoặc không có | Xác minh/validate khi an toàn quan trọng |
| “Không cần đóng response body streaming.” | Có thể giữ HTTP connection/resources | Dùng try-with-resources, đóng/cancel |
| “`HttpResponse<Void>` không cần kiểm tra status.” | `Void` chỉ bỏ body | Vẫn kiểm tra metadata và lỗi HTTP |

## 14. Checklist trước khi đưa vào ứng dụng

1. **Mục tiêu của body là gì?** Text, JSON, binary, file download, streaming byte, streaming line hay không cần body?
2. **`HttpResponse<T>` có khớp `BodyHandler<T>` thực sự đã truyền không?** Đừng dựa vào cast/type erasure.
3. **Có dùng charset đúng?** Với UTF-8 xác định rõ `StandardCharsets.UTF_8` nếu endpoint quy định.
4. **Đã kiểm tra status HTTP chưa?** Không cho rằng 4xx/5xx là Java exception.
5. **Body có kích thước giới hạn không?** Tránh nhận toàn bộ bằng `String`/`byte[]` nếu không biết trước dung lượng.
6. **Nếu ghi file, chính sách tên file/quyền ghi/overwrite/checksum/cleanup đã rõ chưa?**
7. **Nếu nhận stream, đã đọc EOF hoặc đóng/cancel chưa?** Không để kết nối giữ mở.
8. **Nếu dùng `ofLines`, có chấp nhận việc mất kiểu ký tự xuống dòng gốc không?**
9. **Nếu dùng `Void`, có hiểu body() là null và không còn nội dung server để đọc không?**
10. **Nếu parser tạo DTO, có validation schema/content type và xử lý error body phù hợp không?**
11. **Nếu bất đồng bộ, đã quan sát future thất bại và xử lý deadline/cancel đúng cách chưa?**
12. **Nếu dùng Java 11, đã kiểm tra API toàn bộ ví dụ thực sự tồn tại ở Java 11 chưa?**

**Kết luận:** `HttpResponse<T>` lưu cùng cấu trúc metadata cho mọi response, nhưng **kiểu body phụ thuộc `BodyHandler<T>`**. Chọn `String` khi cần text, `byte[]` cho binary nhỏ, `Path` cho file, `InputStream`/`Stream<String>` cho luồng dữ liệu và `Void` khi chỉ cần status/headers. Sau khi chọn đúng kiểu, vẫn phải kiểm soát status code, dung lượng, charset và vòng đời tài nguyên.

## Tài liệu tham khảo chính thức, còn áp dụng

- [Oracle Java SE 11 — `HttpResponse<T>`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `body()`, `statusCode()`, `headers()` và generic type.
- [Oracle Java SE 11 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): các handler có sẵn từ Java 11.
- [Oracle Java SE 11 — `HttpResponse.BodyHandler<T>`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): chọn `BodySubscriber` từ `ResponseInfo`.
- [Oracle Java SE 11 — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): xử lý bytes thành String/byte[]/Path/stream.
- [Oracle Java SE 25 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): hợp đồng body handlers đang được hỗ trợ.
- [Oracle Java SE 25 — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): trách nhiệm đóng streaming body và giới hạn subscriber.
- [Oracle Java SE 11 — module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/module-summary.html): server HTTP tối giản cho bài kiểm thử Java 11.

Các API được trình bày đều nằm trong Java 11 hoặc tiếp tục được hỗ trợ hiện nay. Không sử dụng HTTP Client incubator, kỹ thuật legacy hay giả định rằng kiểu generic `T` tự động parse dữ liệu từ mạng.