# Body handler trả stream và yêu cầu tiêu thụ hoặc đóng response body

Trong Java 21, `HttpResponse.BodyHandlers.ofInputStream()` cho phép nhận response body dưới dạng `InputStream` để đọc dần, phù hợp với nội dung lớn hoặc khi ứng dụng muốn tự kiểm soát cách xử lý dữ liệu. `BodyHandlers.ofLines()` cũng trả về một `Stream<String>` được đọc theo dòng. Các body dạng stream có vòng đời riêng: ứng dụng phải tiêu thụ đến hết hoặc đóng stream khi không đọc tiếp.

Điểm quan trọng là response có thể được trả về khi stream đã sẵn sàng, trong khi dữ liệu body vẫn đang được truyền. Vì vậy, việc nhận được `HttpResponse` hoặc việc `CompletableFuture` hoàn tất không đồng nghĩa toàn bộ body đã được đọc. Nếu bỏ quên stream, ứng dụng có thể giữ tài nguyên và làm giảm khả năng tái sử dụng kết nối HTTP.

## 1. BodyHandler và thời điểm nhận response

`HttpClient.send()` và `sendAsync()` nhận một `BodyHandler<T>` để xác định cách chuyển response body thành kiểu `T`. Body handler được áp dụng sau khi client nhận response headers. Từ headers và handler, HttpClient tạo một `BodySubscriber<T>` để tiếp nhận body.

Một số body handler phổ biến trong Java 21:

| Body handler | Kiểu `HttpResponse.body()` | Cách xử lý |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | Đọc và chuyển toàn bộ body thành chuỗi trước khi response hoàn tất. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Đọc toàn bộ body vào bộ nhớ. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Trả stream để ứng dụng đọc body dần và tự đóng. |
| `BodyHandlers.ofLines()` | `Stream<String>` | Trả stream các dòng văn bản UTF-8; phải tiêu thụ hoặc đóng stream. |
| `BodyHandlers.ofFile(path)` | `Path` | Ghi body vào file và trả đường dẫn sau khi body được ghi xong. |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Cho ứng dụng xử lý dữ liệu theo mô hình reactive streams và backpressure. |

Với `ofInputStream()`, body subscriber có thể hoàn tất khi cung cấp được `InputStream`, không cần đợi toàn bộ nội dung được tải xuống. Do đó, `send()` có thể trả về `HttpResponse<InputStream>` trong khi lần đọc tiếp theo trên stream vẫn phải chờ mạng.

## 2. Đọc `InputStream` bằng try-with-resources

Luôn đặt response body vào try-with-resources để stream được đóng cả khi đọc thành công lẫn khi có exception:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class StreamBodyExample {
    public static void main(String[] args) throws IOException, InterruptedException {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/data"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream()
        );

        try (InputStream body = response.body()) {
            System.out.println("HTTP status: " + response.statusCode());

            byte[] buffer = new byte[8_192];
            int count;
            while ((count = body.read(buffer)) != -1) {
                processChunk(buffer, count);
            }
        }
    }

    private static void processChunk(byte[] buffer, int length) {
        // Xử lý length byte đầu tiên của buffer.
    }
}
```

`InputStream.read()` trả về `-1` khi đã đọc hết body. Vòng lặp xử lý từng chunk nên không cần giữ toàn bộ response trong bộ nhớ. Khối `try` đóng body khi đọc đến EOF, khi `processChunk()` ném exception hoặc khi phương thức kết thúc sớm.

Không trả `response.body()` ra khỏi một phương thức đã đóng stream trong `finally` hoặc try-with-resources. Nếu caller cần tự đọc body, quyền sở hữu stream phải được chuyển rõ ràng cho caller và caller phải chịu trách nhiệm đóng nó.

## 3. Đọc văn bản theo dòng với `BodyHandlers.ofLines()`

Nếu response là văn bản UTF-8 có cấu trúc theo dòng, `BodyHandlers.ofLines()` trả về `Stream<String>`. Stream được đọc lười; dữ liệu được lấy khi pipeline thực thi. Vì `Stream` triển khai `AutoCloseable`, hãy dùng try-with-resources:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.stream.Stream;

public class LinesBodyExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/logs"))
                .GET()
                .build();

        HttpResponse<Stream<String>> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofLines()
        );

        try (Stream<String> lines = response.body()) {
            lines.limit(100).forEach(System.out::println);
        }
    }
}
```

Ví dụ chỉ xử lý tối đa 100 dòng. Khi `limit(100)` kết thúc sớm, try-with-resources vẫn đóng stream và giải phóng việc tiêu thụ body còn lại. Nếu cần đọc toàn bộ nội dung, bỏ `limit()` và xử lý đến hết stream.

Không gọi `parallel()` chỉ để tăng tốc xử lý `ofLines()` nếu pipeline đang phụ thuộc vào một nguồn stream I/O tuần tự. Nếu cần xử lý song song từng record, hãy tách dữ liệu thành đơn vị công việc có kích thước giới hạn và đưa sang executor phù hợp sau khi đọc, đồng thời kiểm soát backpressure và bộ nhớ đệm.

## 4. Phải đóng body ngay cả khi status code là lỗi

Body handler vẫn được áp dụng cho response có status code như `404`, `429` hoặc `500`. HttpClient không tự đóng `InputStream` chỉ vì status không thuộc nhóm `2xx`. Nếu ứng dụng chỉ quan tâm status và không đọc error body, vẫn phải đóng stream:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;

public class DownloadWithStatusCheck {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/file"))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream()
        );

        try (InputStream body = response.body()) {
            if (response.statusCode() / 100 != 2) {
                throw new IOException("HTTP request failed: " + response.statusCode());
            }

            try (var output = Files.newOutputStream(Path.of("download.bin"))) {
                body.transferTo(output);
            }
        }
    }
}
```

Nếu cần thông tin lỗi từ server, hãy đọc một lượng dữ liệu giới hạn trước khi đóng stream. Không nên đọc error body không giới hạn vào bộ nhớ vì nội dung lỗi cũng có thể rất lớn.

```java
static byte[] readAtMost(InputStream input, int maxBytes) throws IOException {
    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must not be negative");
    }

    return input.readNBytes(maxBytes);
}
```

Sau khi lấy phần đầu của error body, đóng stream trong try-with-resources. Việc đóng stream khi chưa đọc hết báo cho body subscriber rằng ứng dụng không tiếp tục tiêu thụ nội dung. Khả năng tái sử dụng kết nối sau đó phụ thuộc giao thức, trạng thái response và implementation; không nên giả định mọi body bị đóng sớm đều có thể dùng lại cùng một connection.

## 5. Đóng stream khi chỉ cần một phần response

Một số trường hợp chỉ cần đọc phần đầu của response, chẳng hạn lấy vài dòng preview hoặc kiểm tra một header trong nội dung. Khi đó, có thể dừng sớm nhưng vẫn phải đóng stream:

```java
try (InputStream body = response.body()) {
    byte[] preview = body.readNBytes(1_024);
    inspectPreview(preview);
}
```

Không nên đọc một vài byte rồi bỏ tham chiếu đến stream. Nếu body chưa được tiêu thụ đến hết, việc không đóng có thể khiến subscriber và tài nguyên mạng còn hoạt động. Đóng sớm có thể làm hủy phần body còn lại; nếu cần connection reuse tối đa và response body nhỏ, tiêu thụ đến EOF thường là lựa chọn phù hợp hơn.

## 6. `sendAsync()` không có nghĩa body stream đã được đọc xong

Với `BodyHandlers.ofInputStream()`, future của `sendAsync()` có thể hoàn tất khi response và `InputStream` đã sẵn sàng, trong khi việc đọc body vẫn diễn ra sau đó:

```java
var responseFuture = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofInputStream()
);

var bodyReadFuture = responseFuture.thenAccept(response -> {
    try (InputStream body = response.body()) {
        body.transferTo(destination);
    } catch (IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
});
```

Đây là mảnh code giả sử `client`, `request` và `destination` đã được khai báo. `responseFuture` đại diện cho giai đoạn nhận response và stream; `bodyReadFuture` đại diện cho callback đọc body và hoàn tất bất thường nếu đọc thất bại. Có thể gọi `bodyReadFuture.join()` khi cần chờ giai đoạn đọc. Tuy nhiên, `transferTo()` là thao tác blocking; không nên mặc định chạy việc đọc stream dài trên thread hoàn tất future hoặc một executor dùng chung dành cho callback ngắn. Có thể chuyển phần đọc blocking sang executor chuyên dụng; trong Java 21, virtual-thread-per-task executor là một lựa chọn khi workload phù hợp.

Ví dụ hoàn chỉnh dưới đây chờ cả giai đoạn nhận response lẫn giai đoạn đọc/ghi body. Nó cũng đóng response body nếu status không thành công:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Executors;

public class AsyncStreamDownload {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/file"))
                .GET()
                .build();
        Path target = Path.of("download.bin");

        try (var bodyExecutor = Executors.newVirtualThreadPerTaskExecutor()) {
            var responseFuture = client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofInputStream()
            );

            var downloadFuture = responseFuture.thenAcceptAsync(response -> {
                try (InputStream body = response.body()) {
                    if (response.statusCode() / 100 != 2) {
                        throw new IOException("HTTP status: " + response.statusCode());
                    }

                    try (OutputStream output = Files.newOutputStream(target)) {
                        body.transferTo(output);
                    }
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            }, bodyExecutor);

            // Chờ callback đọc và ghi body hoàn tất, không chỉ chờ headers.
            downloadFuture.join();
        }
    }
}
```

`downloadFuture` chỉ hoàn tất sau khi callback đã đọc/đóng body. Nếu callback thất bại, `join()` ném `CompletionException` với nguyên nhân tương ứng. `ExecutorService.close()` trong Java 21 thực hiện shutdown và chờ các tác vụ đã được gửi hoàn tất; ở đây `downloadFuture.join()` còn bảo đảm lỗi của giai đoạn tải được quan sát trước khi rời khỏi khối. Trong ứng dụng thực tế, cần quyết định cách xử lý lỗi và cancellation ở cả giai đoạn nhận headers lẫn giai đoạn đọc body.

## 7. Request timeout không thay thế timeout đọc stream

`HttpRequest.Builder.timeout(Duration)` đặt giới hạn thời gian chờ response theo hợp đồng của HttpClient. Với body handler thu thập toàn bộ body như `ofString()` hoặc `ofByteArray()`, body được xử lý trong quá trình hoàn tất response. Nhưng với `ofInputStream()` và `ofLines()`, body handler có thể hoàn tất khi stream đã được cung cấp, trước khi ứng dụng đọc hết nội dung.

Do đó, không nên xem request timeout là timeout cho mọi lần `read()` tiếp theo trên `InputStream`. Sau khi nhận stream, một lần đọc có thể tiếp tục chờ dữ liệu. `HttpClient` không cung cấp API `setSoTimeout()` trực tiếp cho response `InputStream` như `Socket`.

Nếu cần deadline tổng cho giai đoạn đọc body, ứng dụng phải quản lý riêng thời gian và chính sách hủy. Một cách tiếp cận là thực hiện việc đọc trên task có thể theo dõi, khi deadline hết thì đóng stream để kết thúc tiêu thụ và xử lý task thất bại. Cần thiết kế cẩn thận để thao tác đóng có thể được gọi an toàn từ luồng điều phối và không để task đọc tiếp tục giữ tài nguyên.

Với xử lý streaming bất đồng bộ thực sự, có thể cân nhắc `BodyHandlers.ofPublisher()` và triển khai `Flow.Subscriber` có quản lý demand, cancellation và deadline. Cách này không tạo một `InputStream` blocking cho ứng dụng; subscriber chịu trách nhiệm tiêu thụ hoặc hủy subscription theo Flow API.

## 8. Chọn body handler phù hợp với kích thước và cách sử dụng

Không phải mọi response đều cần stream. Hãy chọn handler theo kích thước dữ liệu và cách ứng dụng sử dụng body:

| Nhu cầu | Lựa chọn | Lưu ý |
| --- | --- | --- |
| JSON hoặc văn bản nhỏ, có giới hạn kích thước rõ | `BodyHandlers.ofString()` | Body được giữ trong bộ nhớ dưới dạng `String`; chọn charset/giải mã phù hợp với giao thức. |
| Nội dung nhị phân nhỏ | `BodyHandlers.ofByteArray()` | Toàn bộ body được giữ trong `byte[]`; tránh với file lớn. |
| File lớn cần ghi xuống đĩa | `BodyHandlers.ofFile(path)` | HttpClient ghi body vào file; response chỉ hoàn tất khi việc ghi body hoàn thành. |
| Dữ liệu cần đọc/xử lý từng chunk | `BodyHandlers.ofInputStream()` | Ứng dụng phải đọc hoặc đóng `InputStream`. |
| Văn bản xử lý theo từng dòng | `BodyHandlers.ofLines()` | Stream là lazy và phải được đóng. |
| Pipeline reactive, cần backpressure/cancel | `BodyHandlers.ofPublisher()` | Phải subscribe và quản lý Flow subscription đúng hợp đồng. |

Nếu body có thể rất lớn, tránh `ofString()` và `ofByteArray()` vì chúng cần bộ nhớ tỷ lệ với kích thước nội dung. Nếu chỉ muốn tải file, `ofFile()` thường đơn giản hơn tự đọc `InputStream` rồi ghi từng chunk.

## 9. Connection reuse và tác động của việc không đóng body

HttpClient quản lý và có thể tái sử dụng các kết nối. Khi ứng dụng nhận body stream, việc tiêu thụ hoặc đóng body là một phần của vòng đời response. Nếu stream bị bỏ quên:

- Body subscriber có thể vẫn giữ tài nguyên cần thiết để nhận dữ liệu.
- Kết nối hoặc stream HTTP có thể chưa ở trạng thái có thể tái sử dụng.
- Số response đang mở tăng lên có thể làm cạn tài nguyên và gây nghẽn các request khác.
- Ứng dụng có thể giữ buffer và tham chiếu đến response lâu hơn cần thiết.

Đọc đến EOF thường cho client biết body đã được tiêu thụ đầy đủ. Đóng trước EOF cho phép hủy việc tiêu thụ còn lại; cách xử lý kết nối phụ thuộc HTTP/1.1 hay HTTP/2 và implementation. Không dựa vào garbage collection để đóng response body, vì thời điểm thu gom không xác định.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `send()` xong nhưng body vẫn chưa tải xong | `ofInputStream()` có thể trả stream ngay khi stream sẵn sàng. | Đọc stream đến EOF hoặc đóng stream. |
| `sendAsync()` future hoàn tất nhưng file chưa được ghi xong | Future chỉ đại diện giai đoạn response handler hoàn tất; callback đọc stream có thể vẫn chạy. | Chờ future đại diện cho callback đọc/ghi body. |
| Không nhận được connection reuse như kỳ vọng | Body stream chưa được tiêu thụ hoặc đóng. | Dùng try-with-resources cho body và xử lý đến EOF khi phù hợp. |
| Response status là 500 nên bỏ qua body | Error response vẫn có body stream cần quản lý. | Đọc error body có giới hạn hoặc đóng ngay. |
| Đọc vài byte rồi bỏ stream | Stream chưa được đóng và phần body còn lại chưa được hủy rõ ràng. | Đóng stream ngay khi không cần đọc tiếp. |
| Dùng `ofString()` cho file lớn | Toàn bộ body phải được giữ trong bộ nhớ. | Dùng `ofFile()` hoặc `ofInputStream()` để xử lý theo luồng. |
| Dùng `request.timeout()` làm read timeout cho stream | Body stream có thể được trả trước khi ứng dụng đọc hết; timeout request không phải timeout cho từng lần `InputStream.read()`. | Quản lý deadline đọc riêng hoặc dùng publisher/subscriber có cancellation. |
| Đọc stream blocking trong callback executor dùng chung | Một callback có thể chiếm thread lâu khi mạng chậm. | Chuyển việc đọc sang executor chuyên dụng hoặc virtual thread phù hợp. |
| Quên đóng `Stream<String>` từ `ofLines()` | Java Stream giữ tài nguyên body và cần được đóng. | Dùng try-with-resources quanh stream. |

## 11. Quy trình thực hành

1. Chọn body handler theo kích thước và cách tiêu thụ response.
2. Nếu dùng `ofInputStream()` hoặc `ofLines()`, xác định rõ nơi sở hữu và đóng body.
3. Đọc đến EOF nếu cần hoàn tất response; nếu dừng sớm, đóng stream ngay.
4. Quản lý body ngay cả khi status code là lỗi hoặc khi xử lý response phát sinh exception.
5. Với `sendAsync()`, phân biệt thời điểm future nhận stream và thời điểm việc đọc body hoàn tất.
6. Không dùng request timeout như timeout cho từng lần đọc sau khi stream đã được trả về.
7. Nếu cần deadline đọc, thiết kế task cancellation hoặc reactive subscriber có backpressure và cancellation rõ ràng.
8. Không dựa vào garbage collection để giải phóng response body hoặc connection.

## 12. Tài liệu tham khảo chính thức

- [Java SE 21 API — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofInputStream`, `ofLines`, `ofFile`, `ofPublisher` và các body handler chuẩn.
- [Java SE 21 API — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): các subscriber dựng body từ publisher, gồm input stream và publisher.
- [Java SE 21 API — `HttpResponse`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.html): response headers, status code và body.
- [Java SE 21 API — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout và cấu hình request.
- [Java SE 21 API — `HttpClient`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, quản lý response và HTTP client.
- [Java SE 21 API — `InputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): đọc, chuyển tiếp và đóng stream.
- [Java SE 21 API — `Flow`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): publisher/subscriber, demand và cancellation trong reactive streams.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads được chuẩn hóa trong Java 21, có thể dùng cho tác vụ blocking phù hợp.
