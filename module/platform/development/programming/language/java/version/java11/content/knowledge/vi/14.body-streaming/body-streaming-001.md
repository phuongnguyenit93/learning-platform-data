# `BodyHandlers.ofInputStream()` và trách nhiệm đóng luồng HTTP response trong Java 11+

## 1. Bài toán: đọc response theo luồng, không gom hết vào RAM

Từ **Java 11**, HTTP Client API trong `java.net.http` cho phép nhận phần **response body** bằng `InputStream`:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
```

Khác với `BodyHandlers.ofString()` hoặc `BodyHandlers.ofByteArray()`, cách này **không cần đợi tải hết response body** rồi mới đưa giá trị body cho caller. Khi `HttpClient.send(...)` trả về `HttpResponse<InputStream>`, HTTP response headers đã được nhận, nhưng các byte nội dung **có thể vẫn đang đến**. Phương thức `response.body()` trả về một luồng mà ứng dụng tự đọc từng phần.

Ví dụ, API trả về tệp 2 GB: nếu dùng `ofByteArray()` thì dữ liệu phải được tích lũy thành mảng byte lớn (hoặc có thể hết bộ nhớ); nếu dùng `ofInputStream()`, ứng dụng có thể xử lý từng khối 8 KB rồi chuyển ngay sang đích. Điều đó chỉ giúp hạn chế **bộ nhớ trung gian của client** nếu mã xử lý cũng thực sự đọc từng khối; nếu gọi `readAllBytes()` rồi giữ lại cả mảng, lợi ích streaming sẽ không còn.

**Trọng tâm quan trọng nhất:** ứng dụng nhận `InputStream` cũng nhận trách nhiệm **đọc cho đến EOF hoặc đóng luồng** khi không tiếp tục đọc. Bỏ mặc stream chưa tiêu thụ có thể giữ tài nguyên liên quan đến HTTP exchange và kết nối trong thời gian không mong muốn. Đây là quy tắc còn áp dụng trên các JDK hiện đại.

## 2. API và vòng đời response

| Thành phần | Kiểu/ý nghĩa | Điều nên nhớ |
| --- | --- | --- |
| `HttpResponse.BodyHandlers.ofInputStream()` | `BodyHandler<InputStream>` | Chọn cơ chế nhận response body theo luồng. |
| `HttpClient.send(request, handler)` | `HttpResponse<InputStream>` | Với handler này, thường trả về sau khi đã nhận headers mà chưa cần đọc hết body. |
| `response.statusCode()` | `int` | Mã HTTP, ví dụ 200, 404, 500; **không** tự thay thế việc xử lý/đóng body. |
| `response.headers()` | `HttpHeaders` | Metadata đã có khi response trả về; không có nghĩa body đã nhận hết. |
| `response.body()` | `InputStream` | Luồng cần được ứng dụng quản lý, đọc và đóng đúng cách. |
| `input.read(buffer)` | Số byte vừa đọc hoặc `-1` | `-1` biểu thị EOF; một lần đọc không nhất thiết trả đủ buffer. |
| `input.close()` | Đóng body stream | Giải phóng/cancel phần trao đổi chưa hoàn tất; có thể khiến kết nối không tái sử dụng được nếu đóng sớm. |

Điều kiện giải phóng tài nguyên mà tài liệu `BodySubscribers.ofInputStream()` nêu: **đọc hết body tới EOF** *hoặc* **gọi `InputStream.close()` nếu không thể hoặc không muốn đọc hết**. Trong thực tế, nên **luôn dùng `try-with-resources`** cho luồng nhận được, kể cả khi có kế hoạch đọc tới EOF, để bảo đảm nhánh exception cũng đóng tài nguyên.

Một chuỗi bước đúng:

1. Xây `HttpClient` và `HttpRequest`.
2. Gửi request bằng `BodyHandlers.ofInputStream()`.
3. Lấy `HttpResponse<InputStream>`; tại đây có thể kiểm tra HTTP status và headers.
4. **Ngay khi nhận body**, đưa `response.body()` vào `try-with-resources`.
5. Đọc/chuyển tiếp từng khối hoặc chủ động dừng sớm; khi rời khối `try`, stream được đóng kể cả khi đọc/parse bị lỗi.

`HttpResponse` không phải đối tượng cần bọc trong `try-with-resources` để đóng body. Đối tượng sở hữu cần được đóng ở đây chính là **`InputStream` từ `response.body()`**.

## 3. Mẫu chuẩn khi xử lý toàn bộ response body

Với một endpoint thực tế và dữ liệu có thể lớn, dùng buffer hữu hạn:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        process(buffer, 0, n); // Hàm do ứng dụng tự triển khai.
    }
}
```

Đoạn này là **mã minh họa đặt trong phương thức** có sẵn `client`/`request`, có xử lý hoặc khai báo `IOException` và `InterruptedException`, import `InputStream`, `HttpResponse`. `process(buffer, 0, n)` chỉ là tên placeholder của thao tác xử lý ứng dụng, **không phải API JDK và không phải chương trình Java chạy độc lập**; chương trình đầy đủ ở mục sau sẽ dùng `ByteArrayOutputStream.write`.

Các điểm cần chính xác:

- Khi `read(buffer)` trả về `n > 0`, chỉ có vùng `buffer[0..n)` vừa được đọc. Không tự động xử lý cả 8192 byte vì khối cuối thường ngắn hơn.
- `read(...) == -1` mới là dấu EOF, không dùng `available() == 0` để quyết định đã hết body. `available()` chỉ ước lượng số byte có thể đọc mà không chặn, **không** là tổng độ dài còn lại.
- `InputStream.read` có thể **chặn** trong khi chờ thêm dữ liệu từ mạng; `ofInputStream()` không biến lời gọi `read` thành non-blocking.
- `Content-Length` (nếu có) là thông tin về kích thước body theo HTTP và có thể không hiện diện; không dùng một giá trị header thiếu/không đáng tin thay cho cơ chế đọc tới EOF hoặc đóng stream.
- Nếu đọc thất bại vì `IOException`, `try-with-resources` vẫn gọi `close()`. Nếu chính `close()` cũng thất bại, Java bảo toàn/suppressed exceptions theo quy tắc try-with-resources.

## 4. Ví dụ Java hoàn chỉnh, tự chạy bằng HTTP server loopback

Ví dụ này tạo **HTTP server cục bộ trong chính chương trình** bằng module JDK `jdk.httpserver`, để kết quả kiểm thử không cần Internet, tài khoản hoặc API bên ngoài. Server phản hồi cùng nội dung ASCII mỗi lần: `Hello streaming HTTP`.

Client thực hiện hai lần GET:

- **Lần 1:** đọc hết body bằng buffer 6 byte, tới `-1` (EOF), rồi đóng stream qua `try-with-resources`.
- **Lần 2:** chỉ đọc 5 byte đầu là `Hello`, rồi rời khối `try` để **đóng body sớm**. Điều này minh họa trách nhiệm đóng khi không đọc hết, không khẳng định kết nối nhất định bị đóng hay tái sử dụng.

Tạo tệp **`HttpInputStreamCloseDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class HttpInputStreamCloseDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/payload", exchange -> {
            byte[] payload = "Hello streaming HTTP"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, payload.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(payload);
            }
        });
        server.start();

        try {
            int port = server.getAddress().getPort();
            URI endpoint = URI.create(
                    "http://127.0.0.1:" + port + "/payload");

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .GET()
                    .build();

            HttpResponse<InputStream> full = client.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());

            try (InputStream input = full.body()) {
                ByteArrayOutputStream collected =
                        new ByteArrayOutputStream();
                byte[] buffer = new byte[6];
                int count;

                while ((count = input.read(buffer)) != -1) {
                    collected.write(buffer, 0, count);
                }
                System.out.println("fullStatus=" + full.statusCode());
                System.out.println("fullBody=" +
                        collected.toString(StandardCharsets.UTF_8));
            }

            HttpResponse<InputStream> partial = client.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());

            try (InputStream input = partial.body()) {
                byte[] firstFive = input.readNBytes(5);
                System.out.println("partialStatus=" +
                        partial.statusCode());
                System.out.println("firstFive=" +
                        new String(firstFive, StandardCharsets.UTF_8));
                // Không đọc các byte còn lại.
            } // Đóng stream ngay cả khi không đọc hết body.

            System.out.println("streamScopeClosed=true");
        } finally {
            server.stop(0);
        }
    }
}
```

`com.sun.net.httpserver.HttpServer` là API của **module `jdk.httpserver` đi kèm JDK**, dùng ở đây để minh họa HTTP loopback. Nó không phải một phần của `java.net.http` và không bắt buộc cho ứng dụng HTTP client thông thường. Sử dụng **JDK 17+ đầy đủ** (mã nguồn/HTTP API tương thích Java 11), chạy:

```bash
javac --add-modules jdk.httpserver HttpInputStreamCloseDemo.java
java --add-modules jdk.httpserver HttpInputStreamCloseDemo
```

**Stdout chính xác khi chạy trong môi trường cho phép kết nối loopback:**

```text
fullStatus=200
fullBody=Hello streaming HTTP
partialStatus=200
firstFive=Hello
streamScopeClosed=true
```

Phân tích:

1. Server lắng nghe trên `127.0.0.1` với port `0` để hệ điều hành cấp một cổng trống, sau đó client truy cập đúng cổng vừa cấp. Chương trình không in số port nên kết quả không phụ thuộc cổng được chọn.
2. Lần 1 dùng `while ((count = input.read(buffer)) != -1)` để gom đúng `count` byte mỗi lần. Nội dung sau cùng là `Hello streaming HTTP`.
3. Lần 2 cố ý dừng sau 5 byte. `InputStream.readNBytes(5)` (Java 9+) lấy tối đa 5 byte; với payload cố định của ví dụ, kết quả là `Hello`. Khối `try-with-resources` bảo đảm `close`, ngay cả khi không đọc tiếp.
4. `streamScopeClosed=true` là một dòng được chương trình in **sau khi thoát khối try**, không phải xác nhận rằng TCP socket đã đóng hay kết nối có được tái sử dụng. Hành vi tái sử dụng phụ thuộc HTTP client/server và thời điểm đóng sớm.
5. `finally { server.stop(0); }` dừng HTTP server minh họa. Server chỉ phục vụ trong quá trình chạy chương trình, không để lại dịch vụ ngoài.

Trong môi trường bị chặn mở cổng loopback, ví dụ có thể gặp lỗi socket và không tạo được stdout nêu trên; điều đó không thay đổi hợp đồng API Java. Với hệ thống thật, thay server minh họa bằng endpoint do ứng dụng quản lý và xử lý mạng, TLS, thời gian chờ, xác thực phù hợp.

## 5. Đọc đến EOF hay đóng sớm: hai hướng đúng nhưng tác động khác nhau

### 5.1. Đọc đến EOF

Đọc cho tới khi `read(...) == -1` cho HTTP client cơ hội nhận và xử lý hết body, hoàn tất quá trình trao đổi và có thể **tái sử dụng kết nối** cho các request tiếp theo khi điều kiện giao thức/triển khai phù hợp.

Đây là lựa chọn tự nhiên nếu ứng dụng cần toàn bộ dữ liệu: tải tệp, streaming parser, xử lý CSV lớn hoặc sao chép sang một `OutputStream`. Sau khi đạt EOF, vẫn nên kết thúc phạm vi `try-with-resources` để đảm bảo vòng đời stream nhất quán.

### 5.2. Đóng trước EOF

Nếu ứng dụng biết rõ không cần phần body còn lại (chẳng hạn chỉ kiểm tra vài byte đầu hoặc status không mong đợi), **không bắt buộc tải cả body cho xong** chỉ để có EOF. Hãy đóng stream ngay khi quyết định dừng đọc:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    byte[] preview = input.readNBytes(128);
    // Xử lý preview rồi dừng; các byte còn lại không cần dùng.
}
```

Đây là đoạn minh họa trong một phương thức có xử lý checked exceptions. `close()` trước EOF có thể khiến kết nối HTTP bên dưới **bị đóng hoặc không tái sử dụng được**. Đây là một **khả năng có điều kiện**, không phải quy tắc rằng mỗi lần đóng sớm đều chắc chắn đóng socket TCP. Ứng dụng cần cân đối lợi ích bỏ phần dữ liệu không cần với chi phí tạo lại kết nối.

### 5.3. Bỏ mặc stream là lựa chọn sai

Đoạn sau **cố ý sai về quản lý tài nguyên**:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

if (response.statusCode() != 200) {
    return; // Sai: body InputStream đã được cấp nhưng chưa đóng.
}
```

Ngay cả khi server trả `404` hoặc `500`, `BodyHandlers.ofInputStream()` vẫn tạo luồng body. Đóng stream trong một nhánh “thành công” không bảo vệ được các nhánh lỗi. Sửa bằng cách **đưa `try-with-resources` bao quanh tất cả nhánh kiểm tra/xử lý body**:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    if (response.statusCode() != 200) {
        // Quyết định không xử lý body lỗi.
        return; // Trước khi return, try-with-resources sẽ close input.
    }

    // Đọc/parse response body cho trường hợp thành công.
}
```

Đây cũng là đoạn minh họa, không phải chương trình độc lập; biến `client`/`request` và phương thức chứa đoạn này cần có ngữ cảnh phù hợp. Không bỏ qua status code: HTTP status 4xx/5xx **không mặc nhiên ném `IOException`** chỉ vì là lỗi ứng dụng.

## 6. So sánh với các BodyHandler khác

| Handler | `HttpResponse<T>.body()` | Thời điểm body sẵn sàng / cách sử dụng |
| --- | --- | --- |
| `BodyHandlers.ofInputStream()` | `InputStream` | Trả response sau headers; **caller phải đọc hoặc close luồng**. Phù hợp xử lý theo khối. |
| `BodyHandlers.ofString(StandardCharsets.UTF_8)` | `String` | Chờ đọc và giải mã toàn bộ body trước khi hoàn tất response; phù hợp nội dung nhỏ. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Tích lũy toàn bộ body vào mảng; tránh với dữ liệu không tin cậy có thể rất lớn. |
| `BodyHandlers.ofFile(path)` | `Path` | Ghi body vào tệp; phù hợp tải tệp trực tiếp khi đã kiểm tra path/quyền ghi/dung lượng. |
| `BodyHandlers.discarding()` | `Void` | Nhận rồi bỏ nội dung body; phù hợp nếu không cần đọc dữ liệu. |
| `BodyHandlers.ofLines()` | `Stream<String>` | Xử lý từng dòng và **cần đóng `Stream`** nếu không tiêu thụ hết. |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Mô hình reactive; phải subscribe và hoàn tất/cancel đúng cách, không thay thế yêu cầu quản lý tài nguyên. |

`ofInputStream()` là API **cho response body**. Không nhầm với `HttpRequest.BodyPublishers.ofInputStream(...)` ở chiều **request body**: API request dùng supplier để lấy luồng dữ liệu **gửi đi**, còn API của bài này cung cấp luồng dữ liệu **nhận về**.

`BodyHandlers.discarding()` là lựa chọn gọn nếu ứng dụng biết từ đầu rằng không cần body. Nó **tiêu thụ rồi bỏ dữ liệu**, khác với quyết định đọc vài byte sau đó đóng sớm. Việc chọn cách nào phụ thuộc kích thước response và mục tiêu sử dụng kết nối.

## 7. Những vấn đề thực tế của streaming

### 7.1. Bản thân `read()` có thể blocking

`send(...)` với `ofInputStream()` có thể trả về sau headers nhưng `input.read(...)` vẫn chờ dữ liệu đến sau. Không gọi thao tác đọc lâu trên thread UI hoặc event loop đang xử lý nhiều kết nối. Với `sendAsync(...)`, tương lai của response có thể hoàn tất sau headers; **sở hữu và đóng `InputStream` vẫn do ứng dụng chịu trách nhiệm**:

```java
client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream())
        .thenAcceptAsync(response -> {
            try (InputStream input = response.body()) {
                // Đọc, xử lý hoặc hủy sớm theo yêu cầu.
                input.transferTo(OutputStream.nullOutputStream());
            } catch (IOException ex) {
                throw new java.io.UncheckedIOException(ex);
            }
        }, workerExecutor);
```

Đây là **đoạn minh họa không độc lập**: `client`, `request` và `workerExecutor` là các đối tượng do ứng dụng tạo; cần import `InputStream`, `OutputStream`, `HttpResponse` và `IOException`. `workerExecutor` nên là executor dành cho công việc có thể chặn. Việc gọi `transferTo(OutputStream.nullOutputStream())` ở ví dụ này cố ý **tiêu thụ toàn bộ body rồi bỏ đi**; nếu mục đích ngay từ đầu chỉ là bỏ body, `BodyHandlers.discarding()` thường đơn giản hơn.

Lưu ý: tác vụ bất đồng bộ cũng cần cơ chế theo dõi lỗi và kết thúc vòng đời. Không chỉ tạo future rồi bỏ mặc nó mà không bảo đảm nhánh xử lý input chạy.

### 7.2. Không hiểu nhầm `Content-Length` và `available()`

- `response.headers().firstValueAsLong("Content-Length")` có thể không có giá trị; cách framing HTTP/2 hoặc chunked transfer của HTTP/1.1 cũng làm việc dự đoán kích thước bằng một header trở nên không chắc chắn.
- `input.available() == 0` **không có nghĩa EOF**. Luồng có thể chỉ chưa có byte sẵn để đọc ngay.
- `input.read(buffer)` có thể trả ít hơn `buffer.length` mà vẫn chưa tới EOF; tiếp tục vòng lặp khi cần.
- `readAllBytes()` và `readNBytes(Integer.MAX_VALUE)` có thể tích lũy dữ liệu quá lớn. Với response không đáng tin, dùng buffer cố định và giới hạn số byte cho phép xử lý.

### 7.3. Giới hạn kích thước và tải tệp an toàn

Nếu dữ liệu từ server không đáng tin, cần kiểm soát **số byte đã đọc thực tế**, không chỉ tin vào `Content-Length`. Ví dụ pattern minh họa:

```java
long maxBytes = 10L * 1024 * 1024; // 10 MiB.
long total = 0;
byte[] chunk = new byte[8192];
int n;

while ((n = input.read(chunk)) != -1) {
    total += n;
    if (total > maxBytes) {
        throw new IOException("Response body too large");
    }
    // Chỉ xử lý n byte của chunk.
}
```

Đoạn này nằm bên trong một `try (InputStream input = response.body())` và cần import `IOException`. Nếu vượt giới hạn, ngoại lệ đi ra khỏi `try` sẽ làm input được đóng, tránh tiếp tục tải body không mong muốn. Trên dịch vụ thực, cân nhắc timeout, tốc độ nhận dữ liệu, hủy tác vụ, lỗi TLS và số kết nối đồng thời.

### 7.4. Stream dữ liệu không tự giải mã thành text

`InputStream` cung cấp **byte**, không biết dữ liệu là JSON/UTF-8/ZIP. Nếu cần text, dùng charset rõ ràng và bộ giải mã xử lý được dữ liệu trải trên nhiều chunk; **không được mặc định mỗi `read` trả đúng một đoạn ký tự nguyên vẹn**. Với một response nhỏ đã được đọc đủ, có thể tạo `new String(bytes, StandardCharsets.UTF_8)`. Với luồng văn bản lớn, cân nhắc `InputStreamReader` kèm charset phù hợp hoặc parser streaming.

Nếu dùng `BufferedReader` hoặc `InputStreamReader` bọc bên ngoài `response.body()`, cho wrapper vào `try-with-resources` sẽ đóng luồng bên dưới khi wrapper đóng; đừng tạo wrapper rồi bỏ qua vòng đời của nó.

### 7.5. Phân biệt đóng body, đóng client và hủy future

- **Đóng response body**: `InputStream.close()` bảo đảm kết thúc vòng đời xử lý response đã cấp cho caller.
- **Đóng/cấu hình client**: là mối quan tâm riêng; không thay thế việc quản lý từng response body. Trên Java 11, `HttpClient` **không phải** đối tượng `AutoCloseable` để bọc vào `try-with-resources`; thiết kế phần mềm có thể tái sử dụng client.
- **Hủy xử lý bất đồng bộ**: hủy future không nên được coi là cách thay thế duy nhất cho `close()` của body stream đã lấy được. Nếu ứng dụng đã giữ stream, đóng nó khi dừng xử lý.

## 8. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả / cách xử lý |
| --- | --- |
| Lấy `response.body()` rồi không đọc hoặc đóng | HTTP exchange có thể giữ tài nguyên; dùng `try-with-resources`. |
| Thấy `send()` đã trả về rồi tưởng body đã tải hết | Với `ofInputStream()`, response có thể sẵn sàng **ngay sau headers**; việc đọc body tiếp tục khi caller gọi `read`. |
| Thoát sớm khi status 404 mà quên đóng | Đặt `try (InputStream input = response.body())` trước nhánh kiểm tra status. |
| Nghĩ `close()` sớm luôn cho phép keep-alive | Đóng trước EOF **có thể** đóng kết nối bên dưới, ngăn tái sử dụng. |
| Đọc `buffer.length` byte mỗi vòng bất kể `read` trả về bao nhiêu | Dẫn đến ghi thêm byte cũ/sai dữ liệu; chỉ xử lý `n` byte vừa nhận. |
| Dùng `available()==0` như EOF | Sai; chỉ `read()==-1` là EOF. |
| Dùng `readAllBytes()` cho dữ liệu vài GB | Có thể hết RAM; xử lý từng khối, đặt giới hạn dữ liệu. |
| Dùng `ofInputStream()` nhưng quên dùng stream trong `sendAsync` | Future có thể hoàn tất mà body chưa được tiêu thụ; cần có consumer và vòng đời rõ ràng. |
| Đọc text UTF-8 riêng từng chunk bằng `new String(chunk, UTF_8)` | Có thể cắt đôi ký tự đa byte; dùng decoder/reader streaming. |
| Tưởng `InputStream.close()` đóng luôn `HttpClient` | Nó đóng luồng body của trao đổi này; không phải hành động “đóng client”. |
| Thấy HTTP 500 và mặc định `send` ném exception | Server có thể trả `HttpResponse` bình thường; phải kiểm tra `statusCode()` và vẫn đóng body. |

## 9. Tự kiểm tra

**Câu 1:** Với `BodyHandlers.ofInputStream()`, khi `client.send(...)` trả về, response body đã nhận đủ chưa?

**Đáp án:** Chưa chắc. Headers đã đọc xong, còn body có thể đang được truyền, ứng dụng đọc qua `InputStream`.

**Câu 2:** Nếu chỉ muốn đọc 1 KB đầu của response 100 MB, nên làm gì sau khi lấy đủ 1 KB?

**Đáp án:** Đóng `InputStream` bằng `try-with-resources` ngay khi ngừng đọc. Có thể mất khả năng tái sử dụng kết nối; không được để stream mở mà bỏ mặc.

**Câu 3:** Có thể dùng `input.available() == 0` để xác định đã đến EOF chưa?

**Đáp án:** Không. EOF là khi `read(...)` trả `-1`; `available()==0` chỉ có thể biểu thị chưa có byte sẵn ngay lúc đó.

**Câu 4:** Vì sao `try-with-resources` cần thiết nếu vòng lặp đã đọc tới EOF?

**Đáp án:** Để bảo đảm stream được đóng cả ở những đường đi có exception, return sớm hoặc thay đổi logic về sau.

**Câu 5:** Nếu server trả `404`, client có trách nhiệm đóng stream không?

**Đáp án:** Có. HTTP status không xóa trách nhiệm đọc tới EOF hoặc đóng body; nên tạo phạm vi `try` rồi quyết định xử lý status bên trong.

**Câu 6:** `BodyHandlers.ofInputStream()` và `BodyPublishers.ofInputStream(...)` khác nhau ở đâu?

**Đáp án:** `BodyHandlers` xử lý **response body nhận về**; `BodyPublishers` cung cấp **request body gửi đi**. Hai hướng dữ liệu và trách nhiệm sở hữu stream không giống nhau.

**Ghi nhớ:** `BodyHandlers.ofInputStream()` cho phép **nhận response và xử lý body theo luồng** ngay sau headers, rất phù hợp dữ liệu lớn. Nhưng ứng dụng **phải đọc tới EOF hoặc đóng `InputStream`**, và nên dùng `try-with-resources` để an toàn trên mọi nhánh. **Đóng sớm có thể mất khả năng tái sử dụng kết nối**; không đọc cũng không đóng là lỗi quản lý tài nguyên.

**Tài liệu chính thức:** [Oracle Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html); [Oracle Java SE 11 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html); [Oracle Java SE 25 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html); [JDK 11 — module jdk.httpserver](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/module-summary.html).
