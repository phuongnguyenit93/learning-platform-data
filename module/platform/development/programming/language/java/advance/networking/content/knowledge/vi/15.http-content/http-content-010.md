# Giới hạn dung lượng phản hồi HTTP và tránh gom nội dung không giới hạn vào heap trong Java

Trong mô-đun **Nội dung HTTP** của Java Advance — networking, một nguyên tắc bảo vệ bộ nhớ cần được thực hiện **trước khi chuyển response body thành String, byte[] hoặc object**: **mọi response đến từ hệ thống bên ngoài đều phải có giới hạn kích thước và vòng đời xử lý rõ ràng**. Một request có thể nhận status 200 và headers hợp lệ nhưng trả một body hàng gigabyte, một stream không kết thúc, một tài liệu nén nhỏ bung thành lượng dữ liệu khổng lồ, hoặc một JSON có số phần tử/độ sâu cực lớn. Nếu ứng dụng Java gom toàn bộ body vào heap không giới hạn, kết quả có thể là **OutOfMemoryError (OOM), dừng Garbage Collector kéo dài, giảm throughput hoặc mất khả năng phục vụ các request khác**.

Với Java 17 **java.net.http.HttpClient**, các cách đọc body phổ biến có rủi ro bộ nhớ khác nhau:

- **HttpResponse.BodyHandlers.ofString()**: chuyển toàn bộ body thành **String**; tiện cho payload nhỏ có mức trần đã xác minh, nhưng **không tự mang giới hạn kích thước ứng dụng**.
- **HttpResponse.BodyHandlers.ofByteArray()**: gom body thành **byte[]**; cũng **không tự mang giới hạn byte ứng dụng**.
- **BodyHandlers.ofInputStream()**: trao một **InputStream** để ứng dụng tiêu thụ dần, giúp không cần gom cả payload ngay, **nhưng không tự giới hạn byte hoặc thời gian đọc**; người gọi phải đếm, abort và close.
- **BodyHandlers.ofFile(...)**: ghi body xuống đĩa thay vì giữ trọn ở heap, nhưng **có thể làm đầy đĩa** nếu thiếu quota/limit.
- **BodyHandler/BodySubscriber tùy biến**: có thể giới hạn byte ngay trong quá trình subscriber nhận các mảnh **ByteBuffer**, dừng subscription khi vượt giới hạn và phối hợp backpressure.

**Quy tắc cốt lõi:** có thể xem **Content-Length như tín hiệu để từ chối sớm**, nhưng nó **không thay thế đếm số byte thực nhận**. Chỉ từ chối dựa trên Content-Length là chưa đủ khi response chunked, thiếu header, có lớp decompression hoặc source không đáng tin cậy. Cũng cần phân biệt **giới hạn body HTTP theo byte trên wire** với **giới hạn dữ liệu sau giải nén**, **số dòng, số phần tử, độ sâu JSON** và **memory budget của cả tiến trình**.

Bài học này đưa ra hai chương trình **Java 17 runnable trên loopback**, đã được biên dịch bằng **javac --release 17** và chạy thành công với JDK hỗ trợ module **jdk.httpserver**. Ví dụ dùng HTTP server nội bộ để so sánh Content-Length, chunked response, InputStream có trần và BodySubscriber có giới hạn. Sau đó là các vấn đề production: cấu hình timeout, decompression bomb, file download, concurrency, metrics, kiểm thử và các lỗi phổ biến.

## 1. Vì sao response body không giới hạn nguy hiểm?

Một ứng dụng điển hình gọi REST API như sau:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
String json = response.body();
~~~

Đây là **đoạn API minh họa**, giả sử **client** và **request** đã được khởi tạo. Mã nhìn đơn giản nhưng có hai giả định nguy hiểm: bên trả dữ liệu **không gửi quá nhiều byte**, và String/JSON thu được **không dùng quá nhiều heap**. Đối với dịch vụ có response nhỏ và được kiểm soát, cách viết này có thể đủ. Nhưng khi body đến từ Internet, bên thứ ba, user-upload, proxy hoặc service bị lỗi, ứng dụng cần một cơ chế kiểm tra kích thước **trong lúc nhận**.

**Ví dụ tải nhiều request đồng thời:** giả sử 200 request cùng trả body 10 MiB. Riêng dữ liệu payload đã có thể chiếm tới khoảng **2.000 MiB** nếu mọi request giữ toàn bộ body trong heap, chưa tính byte buffers của HTTP, String, JSON object graph, log, cache và các lớp trung gian. **Có 1 GiB heap không có nghĩa hệ thống có thể an toàn nhận 1 GiB body**.

### Ba tầng memory amplification thường bị bỏ sót

1. **Byte[] từ transport:** một body 8 MiB có thể được copy qua nhiều buffer/stages trước khi ứng dụng dùng nó.
2. **String từ charset decode:** payload UTF-8 chuyển sang String; biểu diễn nội bộ/copies tùy JVM, charset, thời gian giữ reference và parser.
3. **Object graph sau parse:** một chuỗi JSON nhỏ hơn nhiều so với lượng đối tượng Map, List, String, wrapper và metadata mà parser tạo ra; dữ liệu rất sâu/có nhiều entries còn gây CPU và stack exhaustion.

Do đó **limit theo byte là lớp đầu tiên, không phải lớp duy nhất**. Một policy production cần quyết định **maxEncodedBytes**, **maxDecodedBytes**, **maxItems**, **maxDepth**, **maxDuration**, **maxConcurrentResponses** và mục tiêu bộ nhớ toàn hệ thống.

## 2. Các BodyHandlers trong Java 17 và tính chất bộ nhớ

| BodyHandler | Dạng kết quả | Ưu điểm | Rủi ro nếu không thêm giới hạn |
|---|---|---|---|
| **ofString()** | String | Tốt cho text/JSON nhỏ, tiện dùng | Toàn bộ body được thu gom, decode, có thể OOM |
| **ofByteArray()** | byte[] | Giữ bytes nguyên vẹn | Gom toàn bộ body trong heap, không có trần ứng dụng |
| **ofInputStream()** | InputStream | Ứng dụng tự đọc tăng dần | Cần đếm byte, close, timeout; đọc xong rồi gom lại vẫn có thể OOM |
| **ofLines()** | Stream<String> | Tiêu thụ text theo dòng | Một dòng quá dài hoặc collect mọi dòng vẫn tốn heap; phải close stream |
| **ofFile(path)** | Path | Có thể tránh giữ cả body trong heap | Disk quota/path/cleanup; có thể tải vô hạn |
| **ofPublisher()** | Flow.Publisher<List<ByteBuffer>> | Reactive processing, backpressure | Subscriber vẫn có thể đệm không giới hạn hoặc request quá nhiều |
| **discarding()** | Void | Không cần giữ payload | Vẫn nhận/tiêu thụ body; không có chính sách byte cap tự thân |
| **BodySubscriber tùy biến** | Tùy thiết kế | Tính byte, giới hạn, cancel khi vượt | Dễ sai Flow contract/concurrency; cần QA |

**Lưu ý:** các phương thức **BodyHandlers.ofString/ofByteArray/ofFile/ofInputStream** mô tả **cách xử lý body**; không có tham số **maxBodyBytes** trên các factory này trong Java 17. Không được giả định bản thân HttpClient tự áp một mức dung lượng an toàn theo nhu cầu ứng dụng.

### Bẫy khi đọc code

~~~java
byte[] bytes = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray()).body();

if (bytes.length > MAX_BYTES) {
    throw new IOException("too large");
}
~~~

**Mẫu trên sai về giới hạn bộ nhớ**, dù có kiểm tra kích thước! Khi điều kiện if chạy, Java **đã tải toàn bộ body vào heap**. Đối với payload lớn, chương trình có thể OOM **trước khi kịp kiểm tra**. Nếu cần bảo đảm tối đa MAX_BYTES, phải **đếm và chặn trong lúc streaming**, không chỉ kiểm tra byte[].length sau khi hoàn tất.

Cũng đừng dùng **Content-Length <= MAX_BYTES rồi ofByteArray()** để tuyên bố có trần an toàn: header có thể thiếu (chunked transfer), hệ thống có thể có decompression, và một lớp xử lý khác có thể đưa vào dữ liệu lớn hơn giới hạn dự kiến. Nếu muốn strict limit, subscriber/reader phải kiểm soát byte thực tế.

## 3. Content-Length: kiểm tra nhanh nhưng không phải bảo đảm

**Content-Length** trong HTTP cho biết độ dài body theo framing của message trong những trường hợp có header này. Nó hữu ích để từ chối sớm, nhưng không phải mọi response đều chứa nó, và phần nào của stack kiểm soát framing phụ thuộc HTTP version/encoding.

### Trường hợp có Content-Length

~~~text
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 10485760

... body ...
~~~

Nếu ứng dụng chỉ chấp nhận tối đa **128 KiB**, header này báo trước response **10 MiB**, nên có thể đóng response stream **ngay sau khi đọc headers**, không cần chủ động copy 10 MiB vào heap.

Java 17 HttpHeaders hỗ trợ:

~~~java
OptionalLong announced = response.headers()
        .firstValueAsLong("Content-Length");

if (announced.isPresent()
        && announced.getAsLong() > MAX_BYTES) {
    throw new IOException("Response body too large");
}
~~~

Đây là snippet minh họa, với **response** là HttpResponse đã có headers và **MAX_BYTES** là limit đã cấu hình. **Không dùng header này để cấp phát byte[] theo độ dài do server cung cấp**. Kể cả khi declared length hợp lệ, phải áp **trần đối với byte thực nhận**.

### Trường hợp thiếu Content-Length hoặc truyền chunked

HTTP/1.1 có thể gửi **Transfer-Encoding: chunked**, HTTP/2 và các hình thức streaming cũng không buộc ứng dụng luôn có một Content-Length duy nhất. Không thấy Content-Length **không có nghĩa body rỗng**. Server có thể phát ra dữ liệu nhiều phút hoặc không có trần rõ ràng, nên kiểm tra trước bằng header có thể không phát hiện gì.

~~~text
HTTP/1.1 200 OK
Transfer-Encoding: chunked

chunk 1 -> 64 KiB
chunk 2 -> 64 KiB
chunk 3 -> 64 KiB
...
~~~

Phải tiếp tục **cộng dồn byte đã đọc** và **đóng/hủy** khi sắp vượt ngưỡng.

### Content-Length giả, nhiều giá trị, âm hoặc lỗi framing

- **Không tin header do peer không đáng tin cung cấp** như chứng cứ rằng payload chắc chắn nhỏ.
- HTTP parser có thể từ chối message sai framing hoặc bất nhất Content-Length/Transfer-Encoding; ứng dụng không nên tự phát triển parser HTTP mới để “chấp nhận cho qua”.
- Nếu nhận response hợp lệ về mặt framing nhưng có transform/decompression ở tầng trên, **số byte sau transform có thể lớn hơn header**.
- Kiểm tra cả **status code** trước khi parse body; response lỗi 4xx/5xx cũng có thể rất lớn và có thể trả HTML hoặc JSON không đáng tin.
- Nếu muốn từ chối sớm tại **BodyHandler.apply(ResponseInfo)**, có thể xem headers ngay thời điểm chọn subscriber và áp chính sách trước body; vẫn cần enforce byte thực tế trong subscriber để chống trường hợp thiếu/thay đổi ngữ nghĩa header.

**Phân biệt giới hạn HTTP status 413:** **413 Content Too Large** thường nói về **request body mà server từ chối nhận**, không phải là một exception Java chuẩn khi client từ chối tải response quá lớn. Trong HTTP client, ứng dụng thường phát sinh lỗi nội bộ có phân loại **BODY_TOO_LARGE**, ghi metric và quyết định cách ánh xạ lên API riêng.

## 4. Quy tắc đếm byte thực nhận không bị overflow

Một bộ đếm an toàn cần quản lý **maxBytes** (giá trị dương hợp lý) và **received** (ban đầu 0). Trước khi cộng một chunk có độ dài n:

~~~text
if n > maxBytes - received:
    reject and close
else:
    received += n
    append/process chunk
~~~

**Không kiểm tra received + n > maxBytes** một cách bất cẩn khi dùng kiểu số có thể overflow; biểu thức **n > maxBytes - received** tránh cộng vượt ngưỡng nếu invariant **0 <= received <= maxBytes** luôn đúng. Với dữ liệu rất nhỏ, int có thể đủ nhưng **long** thường rõ ràng hơn cho tổng bytes. Kiểm tra n không âm và tính hợp lệ của limit trước khi dùng trong code tổng quát.

**Một lỗi off-by-one điển hình:** khi **received == maxBytes** và nguồn trả thêm 1 byte, **phải từ chối**. Nhưng body có kích thước **đúng bằng maxBytes** phải được chấp nhận nếu policy của bạn là “at most”. Đây là trường hợp cần unit test riêng.

**Không phải cứ chia nhỏ read buffer là có memory cap**. Một ứng dụng có thể dùng byte[8192], đọc mãi rồi liên tục append vào ByteArrayOutputStream không có điều kiện; tổng số byte vẫn tăng vô hạn. Kích thước buffer **chỉ là kích thước mảnh I/O**, không phải tổng trần.

## 5. Java 17 runnable: giới hạn body qua BodyHandlers.ofInputStream

Ví dụ sau tạo HTTP server trên **127.0.0.1/cổng động** ngay trong JVM, không dùng dịch vụ ngoài. Server có bốn endpoint:

- **/small** trả body **hello** (5 byte), Content-Length đúng.
- **/declared** trả 256 byte và Content-Length 256.
- **/chunked** trả 256 byte nhưng **không công bố Content-Length**, dùng HTTP/1.1 chunked transfer.
- **/exact** trả **đúng 128 byte**, bằng giới hạn đã định.

Client đặt **MAX_BYTES = 128** cho mỗi response. Hàm **readBounded(...)** dùng BodyHandlers.ofInputStream(), từ chối sớm khi declared length vượt limit, **đếm từng mảnh thực đọc** để chặn trường hợp chunked, và **đóng InputStream kể cả khi ném exception**.

Tệp **BoundedStreamDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.OptionalLong;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class BoundedStreamDemo {
    private static byte[] repeat(int count) {
        byte[] value = new byte[count];
        Arrays.fill(value, (byte) 'X');
        return value;
    }

    private static void reply(HttpExchange exchange, byte[] bytes,
                              boolean chunked) throws IOException {
        exchange.sendResponseHeaders(200, chunked ? 0 : bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static byte[] readBounded(HttpClient client, URI uri, long maxBytes)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET().build();

        HttpResponse<InputStream> response = client.send(
                request, HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException("Unexpected HTTP status");
            }

            OptionalLong declared = response.headers()
                    .firstValueAsLong("Content-Length");
            if (declared.isPresent() && declared.getAsLong() > maxBytes) {
                throw new IOException("Declared body exceeds limit");
            }

            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] chunk = new byte[64];
            long total = 0;
            int read;

            while ((read = body.read(chunk)) != -1) {
                if (read > maxBytes - total) {
                    throw new IOException("Actual body exceeds limit");
                }
                output.write(chunk, 0, read);
                total += read;
            }
            return output.toByteArray();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        server.setExecutor(workers);

        server.createContext("/small", exchange -> {
            try {
                reply(exchange, "hello".getBytes(StandardCharsets.UTF_8),
                        false);
            } catch (IOException ignored) {
                // Client may abort an oversized response.
            } finally {
                exchange.close();
            }
        });
        server.createContext("/declared", exchange -> {
            try {
                reply(exchange, repeat(256), false);
            } catch (IOException ignored) {
                // A closed client stream can stop delivery.
            } finally {
                exchange.close();
            }
        });
        server.createContext("/chunked", exchange -> {
            try {
                reply(exchange, repeat(256), true);
            } catch (IOException ignored) {
                // A closed client stream can stop delivery.
            } finally {
                exchange.close();
            }
        });
        server.createContext("/exact", exchange -> {
            try {
                reply(exchange, repeat(128), false);
            } catch (IOException ignored) {
                // A closed client stream can stop delivery.
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            byte[] small = readBounded(client, root.resolve("/small"), 128);
            System.out.println("Small: "
                    + new String(small, StandardCharsets.UTF_8));

            try {
                readBounded(client, root.resolve("/declared"), 128);
                System.out.println("Declared oversized: unexpected success");
            } catch (IOException expected) {
                System.out.println("Declared oversized: rejected");
            }

            try {
                readBounded(client, root.resolve("/chunked"), 128);
                System.out.println("Chunked oversized: unexpected success");
            } catch (IOException expected) {
                System.out.println("Chunked oversized: rejected");
            }

            byte[] exact = readBounded(client, root.resolve("/exact"), 128);
            System.out.println("Exactly at limit: " + exact.length + " bytes");
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

**Biên dịch và chạy** bằng JDK 17 hoặc mới hơn (cần module **jdk.httpserver**):

~~~bash
javac --release 17 --add-modules jdk.httpserver BoundedStreamDemo.java
java --add-modules jdk.httpserver BoundedStreamDemo
~~~

Stdout khi chạy thành công:

~~~text
Small: hello
Declared oversized: rejected
Chunked oversized: rejected
Exactly at limit: 128 bytes
~~~

Hai đường từ chối **đều cần thiết**: **/declared** có thể bị từ chối trước khi đọc body nhờ Content-Length; **/chunked** không có Content-Length để dựa vào nên **vượt giới hạn được phát hiện khi đọc byte thực tế**. **/exact** cho thấy phép so sánh chấp nhận giá trị bằng trần.

### Phân tích mã nguồn và những điều nó bảo đảm

1. **Server loopback/port động:** không có phụ thuộc Internet, proxy hoặc cổng cố định. **HttpServer.sendResponseHeaders(200, 0)** sử dụng chunked transfer cho response có body trong lab.
2. **BodyHandlers.ofInputStream():** HttpClient trả HttpResponse có InputStream; application chủ động nhận và xử lý từng mảnh. **HttpRequest.timeout(3s)** là timeout request, không nên tuyên bố sẽ giới hạn cứng toàn bộ thời gian đọc InputStream sau khi HttpResponse đã được trả.
3. **Early reject:** **HttpHeaders.firstValueAsLong("Content-Length")** được dùng như gợi ý; không tạo byte[] có kích thước do server đề xuất.
4. **Actual-byte cap:** mỗi chunk chỉ được append nếu **read <= maxBytes - total**, do đó **ByteArrayOutputStream không bao giờ chứa quá maxBytes byte dữ liệu hữu ích** trong lần gọi này.
5. **Try-with-resources:** cả đường thành công và lỗi đều đóng **response.body()**. Khi từ chối giữa chừng, kết nối có thể không được reuse; đó là trade-off hợp lý để bảo vệ ứng dụng.
6. **Kiểm tra status:** code từ chối mọi status khác 200 thay vì cố parse lỗi HTML/JSON không đúng schema. Production có thể áp limit riêng cho error body.
7. **Giới hạn của demo:** tối đa 128 byte đủ nhỏ để bài học dễ quan sát. Nếu đặt cap 100 MiB cho hàng trăm request đồng thời, cách gom lại vào ByteArrayOutputStream vẫn có thể tốn hàng chục GiB. Dùng **stream-to-file, incremental parser** hoặc bounded concurrency cho payload lớn.
8. **Ngoại lệ được catch trong main:** các test oversized catch IOException do chính hàm đọc ném. Trong hệ thống thật **không bắt toàn bộ IOException rồi luôn báo BODY_TOO_LARGE**; cần phân biệt IOException do network, timeout, stream bị đóng với lỗi limit bằng exception riêng.

**Đã biên dịch bằng javac --release 17 và chạy thành công**, stdout khớp bốn dòng trong một JDK có module jdk.httpserver. Kết quả này minh họa policy byte cap, **không phải stress-test** với request vô hạn.

## 6. Cách thiết kế một exception riêng cho body quá lớn

Trong sản phẩm thật, dùng một kiểu lỗi ứng dụng để không nhầm “body vượt trần” với “socket reset”:

~~~java
public final class BodyTooLargeException extends IOException {
    public BodyTooLargeException(String message) {
        super(message);
    }
}
~~~

Đây là đoạn khai báo lớp, **không phải chương trình độc lập** (cần import java.io.IOException và tên file khớp public class nếu dùng riêng).

Khi phát hiện header hoặc actual byte vượt trần, ném **BodyTooLargeException**; khi **InputStream.read()** tự ném IOException vì network, giữ nguyên/bao nguyên nhân. Ở tầng service, phân loại metric/circuit breaker/retry theo loại lỗi. **Không nên retry một response oversized bằng cùng cap rồi liên tục tải lại**, vì server rất có thể vẫn trả response oversized và chỉ làm tăng tải.

**Lưu ý về ký tự:** một giới hạn **maxBytes** khác giới hạn **maxCharacters**. UTF-8 có thể dùng nhiều byte cho một ký tự Unicode, hoặc có chuỗi kiểm soát và combining characters. Nếu ứng dụng cần giới hạn số ký tự hoặc độ dài hiển thị, sau byte cap cần kiểm tra riêng trên text đã decode, không thay thế byte cap bằng String.length().

## 7. Java 17 runnable: BodySubscriber tùy biến giới hạn byte trong sendAsync

Với **HttpClient.sendAsync(...)**, application thường muốn subscriber **kiểm tra và chặn ngay lúc nhận các ByteBuffer**, tránh chờ body hoàn chỉnh. Trong Java 17 có interface **HttpResponse.BodySubscriber<T>**, là một **Flow.Subscriber<List<ByteBuffer>>** đồng thời cung cấp **CompletionStage<T> getBody()**.

Subscriber cần quản lý bốn sự kiện:

- **onSubscribe(subscription):** lưu subscription và gọi **request(1)** để yêu cầu một tín hiệu **onNext** (đơn vị request ở đây là **danh sách ByteBuffer**, không phải “1 byte”).
- **onNext(List<ByteBuffer>):** kiểm tra **remaining()** của từng buffer trước khi copy. Nếu sắp vượt cap thì **completeExceptionally(...)** rồi **subscription.cancel()**; nếu hợp lệ thì copy và gọi request(1) tiếp.
- **onError(Throwable):** hoàn tất CompletableFuture bất thường.
- **onComplete():** sau khi publisher báo hết body, trả byte[] đã được **giới hạn**. Với ví dụ payload nhỏ, dùng ByteArrayOutputStream; với payload lớn có trần cao, thay cách lưu bằng incremental processing/file.

Tệp **CappedSubscriberDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;

public class CappedSubscriberDemo {
    private static final class CappedSubscriber
            implements HttpResponse.BodySubscriber<byte[]> {
        private final long limit;
        private final CompletableFuture<byte[]> result =
                new CompletableFuture<>();
        private final ByteArrayOutputStream output =
                new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        private long received;

        CappedSubscriber(long limit) {
            this.limit = limit;
        }

        @Override
        public CompletionStage<byte[]> getBody() {
            return result;
        }

        @Override
        public void onSubscribe(Flow.Subscription next) {
            if (subscription != null) {
                next.cancel();
                return;
            }
            subscription = next;
            next.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> data) {
            if (result.isDone()) {
                return;
            }
            try {
                for (ByteBuffer buffer : data) {
                    int count = buffer.remaining();
                    if (count > limit - received) {
                        result.completeExceptionally(
                                new IOException("Body exceeds byte cap"));
                        subscription.cancel();
                        return;
                    }
                    byte[] piece = new byte[count];
                    buffer.get(piece);
                    output.write(piece, 0, piece.length);
                    received += count;
                }
                subscription.request(1);
            } catch (RuntimeException error) {
                result.completeExceptionally(error);
                subscription.cancel();
            }
        }

        @Override
        public void onError(Throwable error) {
            result.completeExceptionally(error);
        }

        @Override
        public void onComplete() {
            result.complete(output.toByteArray());
        }
    }

    private static void reply(HttpExchange exchange, int size)
            throws IOException {
        byte[] body = new byte[size];
        Arrays.fill(body, (byte) 'Z');
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        server.setExecutor(pool);
        server.createContext("/small", e -> {
            try { reply(e, 5); }
            catch (IOException ignored) { }
            finally { e.close(); }
        });
        server.createContext("/large", e -> {
            try { reply(e, 256); }
            catch (IOException ignored) { }
            finally { e.close(); }
        });
        server.start();

        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY).build();

            HttpResponse.BodyHandler<byte[]> capped =
                    info -> new CappedSubscriber(128);
            HttpRequest small = HttpRequest.newBuilder(
                            root.resolve("/small"))
                    .timeout(Duration.ofSeconds(3)).GET().build();
            HttpResponse<byte[]> ok = client.sendAsync(small, capped).join();
            System.out.println("Small body: " + ok.body().length + " bytes");

            HttpRequest large = HttpRequest.newBuilder(
                            root.resolve("/large"))
                    .timeout(Duration.ofSeconds(3)).GET().build();
            try {
                client.sendAsync(large, capped).join();
                System.out.println("Large body: unexpected success");
            } catch (CompletionException expected) {
                System.out.println("Large body: rejected");
            }
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Lệnh chạy trên JDK 17+:

~~~bash
javac --release 17 --add-modules jdk.httpserver CappedSubscriberDemo.java
java --add-modules jdk.httpserver CappedSubscriberDemo
~~~

Stdout khi chạy thành công:

~~~text
Small body: 5 bytes
Large body: rejected
~~~

**Đã biên dịch với javac --release 17 và chạy thành công.** Khi body 5 byte, subscriber nhận đủ và trả byte[] 5 byte; khi body 256 byte, **số byte phải copy vượt 128**, subscriber completeExceptionally và cancel subscription, làm **sendAsync.join()** hoàn tất với **CompletionException** trong ví dụ.

### Phân tích giới hạn và trách nhiệm của custom subscriber

- **BodyHandler** nhận **ResponseInfo** ở thời điểm có response headers. Ở demo, handler chỉ tạo một subscriber mới cho mỗi response: **info -> new CappedSubscriber(128)**. Production có thể kiểm tra status/Content-Length tại đây để reject sớm hơn.
- **Mỗi response có subscriber/state riêng**, tránh chia sẻ ByteArrayOutputStream/received giữa các requests. Điều này làm cap được áp trên từng response.
- **onNext** dùng **List<ByteBuffer>**; kích thước của list hoặc từng ByteBuffer không bị bảo đảm luôn nhỏ. Demo kiểm tra **remaining() trước khi cấp phát byte[]** để không copy một buffer lớn vượt cap.
- **request(1)** là một tín hiệu demand theo Flow API, **không phải giới hạn 1 byte, 1 network packet hay 1 MiB**. Dù gọi request(1), vẫn phải kiểm tra toàn bộ byte của list được gửi trong onNext.
- **subscription.cancel()** nói với publisher không cần dữ liệu tiếp, nhưng **không cam kết mọi byte ở kernel hoặc network đã được thu hồi**. Một phần dữ liệu có thể đã đến trước khi cancellation được xử lý.
- **CompletionStage<byte[]> getBody()** cho HttpClient biết lúc body hoàn tất/đã lỗi. Nếu vượt cap, completable future lỗi; **không được trả byte[] bị cắt mà âm thầm coi đó là full valid response**.
- **onError** và **onComplete** phải giải quyết kết quả đúng một lần; CompletableFuture có ngữ nghĩa idempotent cho các lần complete tiếp theo. Production nên log nguyên nhân và cleanup theo chính sách.
- **Phạm vi code:** demo dùng ByteArrayOutputStream cho cap 128 byte và chỉ hai request. Một subscriber cho production cần định nghĩa limit dương, xử lý stream cancellation, concurrency, exception types, downstream parse, status/error bodies, timeout và quota tổng. Không dùng đoạn ví dụ như bằng chứng nó là một HTTP client SDK production đã được harden.

**Khác với ví dụ InputStream:** custom subscriber áp trần **ở quá trình subscriber nhận chunks** và có thể dùng trong sendAsync mà không phải block thread caller bằng InputStream.read. Nhưng **callback processing nặng** có thể làm nghẽn executor của HttpClient; giữ xử lý onNext ngắn, giới hạn memory và không blocking trong callback. Khi cần CPU-bound parse, chuyển công việc sang bounded executor và bảo toàn backpressure.

## 8. Không bị nhầm giữa limit của một response và limit của toàn hệ thống

Một body cap 5 MiB chỉ giới hạn **một** response. Nếu app có 1.000 calls đồng thời, upper bound payload đang được giữ về lý thuyết có thể lên tới khoảng **5 GiB**, chưa kể overhead. Vì vậy resource budget production cần ba lớp:

1. **Per-response cap:** ví dụ một JSON endpoint chỉ được trả tối đa 256 KiB, endpoint export 10 MiB, v.v. Các con số phải dựa trên schema/service contract, không copy từ ví dụ.
2. **Concurrent operation budget:** giới hạn số response đang active, tổng byte đang buffered và queue depth, dùng semaphore/bounded executor/admission control.
3. **Global process memory budget:** so cap và concurrency với heap size, String/JSON object overhead, caches, thread stacks, direct memory, HTTP library buffers và mức độ an toàn GC.

### Bất đẳng thức ngân sách đơn giản

~~~text
MAX_ACTIVE_RESPONSES * MAX_HEAP_BODY_BYTES_PER_RESPONSE
    + parser/object/copy overhead
    + existing application heap usage
    <= safe heap budget
~~~

Đây là **mô hình ngân sách**, không phải công thức dự đoán chính xác JVM heap. Khi data không cần giữ trong RAM, dùng streaming processor hoặc ghi file được quản lý để giảm phần giữ body.

**ByteArrayOutputStream có internal buffer:** ngay cả khi chỉ write tối đa MAX_BYTES, cấu trúc có thể mở rộng capacity và khi gọi **toByteArray()** còn tạo bản copy. Do đó với cap lớn vẫn phải tính **amplification do cấp phát/copy**, không coi giới hạn byte dữ liệu là giới hạn memory chính xác từng byte. Để giảm heap, nên parse dần hoặc stream xuống đĩa/đích được kiểm soát.

### Không giữ reference lâu

Một response body đã được parse thành đối tượng lớn có thể còn bị giữ qua cache, CompletableFuture, log, queue, metrics labels hoặc closure; GC không thu hồi khi vẫn còn reference sống. Design response lifecycle cần rõ: đọc, validate, xử lý, đóng stream, giải phóng buffer, không tích lũy toàn bộ object graph trong một List toàn cục.

## 9. Compression: giới hạn bytes trước và sau giải nén

Đối với **Content-Encoding: gzip/br/deflate** hoặc ZIP archive bên trong response, **payload được truyền qua mạng có thể nhỏ hơn rất nhiều so với dữ liệu giải nén**. Một file nén vài kilobyte có thể giải phóng thành hàng trăm megabyte hoặc nhiều gigabyte trong trường hợp cố ý khai thác (*decompression bomb/zip bomb*).

**Không đặt duy nhất một giới hạn lên Content-Length của gzip rồi bỏ kiểm tra sau giải nén.** Ví dụ:

~~~text
HTTP Content-Length (compressed bytes):       75 KiB
maxWireBytes:                                 1 MiB   => qua bước 1
Decompressed UTF-8/body:                      90 MiB
maxDecodedBytes:                              4 MiB   => PHẢI chặn ở bước 2
~~~

Các con số trên chỉ minh họa nguy cơ compression ratio lớn, không phải kết quả của một file cụ thể.

### Thiết kế hai bộ đếm

~~~text
network response body
    |
    v
count compressed/raw entity bytes <= maxWireBytes
    |
    v
decompressor (nếu Content-Encoding hợp lệ và được cho phép)
    |
    v
count decompressed bytes <= maxDecodedBytes
    |
    v
parse JSON/XML/CSV... với maxDepth/maxItems/maxTextLength
    |
    v
application object / xử lý dần
~~~

**Java 17 HttpClient không nên được giả định tự giải nén mọi Content-Encoding và áp trần decoded size theo nhu cầu của bạn.** Khi ứng dụng dùng GZIPInputStream, thư viện HTTP, proxy hoặc JSON deserializer có auto decompression, phải hiểu byte counter nằm **trước** hay **sau** transform. Nếu dùng thư viện tự decompress, kiểm tra cơ chế limit được cung cấp và kiểm thử với payload nén có tỷ lệ cao.

Đối với ZIP archive có nhiều entries, cần giới hạn **tổng uncompressed bytes**, **số entry**, **tỉ lệ compression**, **độ sâu thư mục**, **tên file/path traversal** và **thời gian xử lý**; không chỉ kiểm tra kích thước của file ZIP nhận về.

### Gzip/InputStream minh họa

~~~java
try (InputStream compressed = response.body();
     GZIPInputStream decoded = new GZIPInputStream(compressed)) {
    // Đếm bytes đọc từ decoded: đây là uncompressed bytes.
    // Đọc tới maxDecodedBytes; abort ngay khi vượt trần.
}
~~~

Đây là **snippet API**, chưa phải chương trình độc lập (cần java.util.zip.GZIPInputStream và response đúng Content-Encoding). Một bộ đếm maxWireBytes phải bọc InputStream **trước** GZIPInputStream nếu muốn giới hạn cả compressed bytes; một bộ đếm maxDecodedBytes đặt khi đọc từ GZIPInputStream. Không tin tên encoding do peer cung cấp mà không kiểm tra tính hợp lệ và policy.

**Bẫy Content-Length:** header của HTTP response đã nén thường biểu thị số byte entity đã nén (nếu có), **không phải số byte của JSON/XML sau giải nén**. Kiểm tra nó rồi đọc toàn bộ decompressed body vào String vẫn có thể OOM.

## 10. Dùng BodyHandlers.ofFile và streaming-to-disk đúng cách

**BodyHandlers.ofFile(path)** ghi response body vào file, nên không cần giữ toàn bộ body trong một byte[]/String. Đây là lựa chọn tốt cho download lớn có policy, nhưng **không hề miễn phí**:

- Nếu thiếu disk quota, remote có thể làm đầy ổ đĩa hoặc inode.
- Nếu path được ghép từ tên file do người dùng gửi mà không validate, có nguy cơ **path traversal, overwrite hoặc ghi vào vị trí nhạy cảm**.
- Nếu download bị lỗi giữa chừng, có thể có **file chưa hoàn chỉnh** cần dọn.
- Nếu file cần lưu bền, phải kiểm tra Content-Type, checksum/signature, expected size/format và quarantine/scan theo loại dữ liệu.
- Nếu nhiều download song song, cần **global disk budget**, queue và retention cleanup.

**Cách triển khai chặt chẽ** khi cần một kích thước tối đa: chọn temp path an toàn do server cấp, mở output với mode phù hợp (tránh overwrite), stream body qua một buffer nhỏ và **đếm byte trước khi ghi mỗi chunk**; nếu vượt limit, đóng input/output, xóa temp file theo policy và ghi metric. Chỉ đổi tên temp file sang tên đích bằng thao tác atomic khi đã đọc đủ, checksum đúng và validation thành công.

### BodyHandlers.ofFile không có tham số maxBytes

~~~java
HttpResponse<Path> response = client.send(
        request, HttpResponse.BodyHandlers.ofFile(targetPath));
~~~

Đây chỉ là snippet minh họa, **không phải mẫu bounded download hoàn chỉnh**. Khi nó hoàn tất, file có thể đã được ghi lớn hơn mức mong muốn nếu chỉ kiểm tra Files.size(path) sau đó. Muốn cap **trong lúc nhận**, dùng InputStream với bounded copy, custom subscriber ghi file theo quota, hoặc thư viện downloader hỗ trợ hard limit và cleanup.

### File temp và an toàn path

- Tạo thư mục được quản lý, không cho người gọi tự chọn đường dẫn tuyệt đối tùy ý.
- Dùng tên temp random và quyền file tối thiểu; hạn chế symlink/path traversal nếu upload/download có ảnh hưởng bảo mật.
- Chỉ **move/commit** file khi kiểm tra kích thước, checksum, loại nội dung và trạng thái response đã thành công.
- Nếu request hủy/timeout/quá limit, đảm bảo finally đóng stream và dọn temp file.
- Với cloud object storage, cân nhắc multipart/streamed upload và quota; không cần gom toàn bộ response trước khi đẩy lên storage.

## 11. Streaming JSON/XML/CSV không có nghĩa parser tự an toàn

Một cách khác để tránh String/byte[] quá lớn là sử dụng **streaming parser**: đọc token hoặc record dần và xử lý với bộ nhớ giới hạn. Nhưng phải giới hạn dữ liệu **trong khi parse**, không chỉ tin parser sẽ tự bảo vệ.

### JSON

- Giới hạn **raw bytes** và **decoded bytes** trước parser.
- Giới hạn **nesting depth**, **number of fields**, **array length**, **string length**, **numeric precision** nếu thư viện có hỗ trợ.
- Không tạo một Map/List chứa toàn bộ response nếu chỉ cần thống kê hay lọc vài trường.
- Với JSON array rất lớn, cần protocol cho phép **pagination, NDJSON hoặc streaming items**; một array monolithic thường khó giữ O(1) memory nếu ứng dụng cần reorder toàn bộ.
- Cẩn thận Unicode surrogate, không cắt byte UTF-8 tùy tiện rồi decode thành các đoạn String độc lập khi có ký tự đa byte cắt qua buffer.

### XML

- Giới hạn bytes, element depth và entity expansion; tắt/giới hạn **external entities** khi không cần, phòng XXE/entity-expansion attacks.
- Dùng SAX/StAX streaming nếu phù hợp; DOM parser xây toàn bộ tree trên heap nên không tự phù hợp XML cực lớn.

### CSV/NDJSON/log lines

- Giới hạn **bytes mỗi dòng**, **số dòng**, **tổng bytes** và **số trường**.
- Dùng **BufferedReader.readLine()** mà không trần độ dài dòng vẫn có thể tạo một String cực lớn trước khi có cơ hội kiểm tra. Nếu nguồn không tin cậy, cần reader/parser có **line-length cap** được enforce trong lúc đọc.
- Nếu mỗi record có thể tới vài MB, streaming parser vẫn cần limit riêng cho record.

**Không đồng nhất “chỉ giữ một record” với “heap luôn nhỏ”**: nếu một record có kích thước không giới hạn, bản thân nó vẫn đủ làm đầy heap.

## 12. Timeout, cancellation và response-size limit là các trục khác nhau

**Giới hạn byte không ngăn server nhỏ giọt 1 byte mỗi phút.** Một body dưới 1 MiB vẫn có thể mất nhiều giờ để hoàn tất. Tương tự, timeout 2 giây không bảo đảm request dùng ít bộ nhớ nếu server truyền 200 MiB trong 1 giây.

Cần ít nhất:

1. **Max bytes:** body cap trước decode và/hoặc sau decompress.
2. **Per-request response timeout:** HttpRequest.Builder.timeout(Duration) giới hạn thời gian chờ response theo contract Java 17.
3. **Overall operation deadline:** tổng thời gian đọc stream, parse, validate, downstream write và retry.
4. **Idle/read progress timeout:** policy dừng khi không có byte/record hợp lệ trong khoảng thời gian quy định (nếu protocol cần).
5. **Cancellation/close:** khi vượt trần hoặc deadline, giải phóng response body/subscription/connection và các tài nguyên backend.

### BodyHandlers.ofInputStream có điểm cần nhớ

HttpClient có thể trả HttpResponse<InputStream> **trước khi toàn bộ body được tiêu thụ hết**; nếu ứng dụng sau đó đọc body trong thời gian dài, không được mặc định HttpRequest.timeout vẫn bao hết thao tác tiêu thụ InputStream đó. Muốn giới hạn đọc dài, cần một deadline ngoài, cancellation và phương án gián đoạn I/O/close theo lifecycle.

**Future.get(timeout)** hoặc **CompletableFuture.orTimeout** chỉ là giới hạn chờ/hoàn tất future, **không bảo đảm đã thu hồi bytes gửi qua network hay server ngừng xử lý**. Nếu timeout, cleanup phải được tổ chức chủ động, đặc biệt khi có InputStream hoặc file đang ghi.

### Không retry vô hạn sau body oversized

Nếu server trả payload 50 MiB nhưng app chỉ cho phép 1 MiB, retry cùng request ngay sẽ tiếp tục tải payload 50 MiB và gây thêm chi phí. Phân loại **BODY_TOO_LARGE** như lỗi policy/non-retryable trừ khi có lý do cụ thể (ví dụ request sửa thành paginated range và giới hạn khác). Với lỗi network/timeout, retry cần **bounded attempts**, backoff, jitter, overall deadline và idempotency nếu operation có side effect.

## 13. HTTP caching, redirect và error response cần chung một policy

### Redirect

Một HttpClient có thể cấu hình followRedirects. Nếu request A trả 302 tới location B, B có thể trả body lớn không đáng tin. Limit phải áp cho **response cuối và các response được ứng dụng xử lý**, không chỉ tin Content-Length từ host ban đầu. Cần bảo vệ **SSRF/redirect-to-internal-address** trong hệ thống cho phép user nhập URL.

### Error bodies

Một response 500/502/429 có thể chứa HTML lỗi rất dài hoặc nội dung debug. Nếu ứng dụng gọi **ofString()** để log toàn bộ error body, attacker vẫn có thể lợi dụng để tiêu tốn heap/log storage. Đặt cap cho **error body** riêng, thường nhỏ hơn success body; log một preview đã giới hạn và mask secrets.

### Cache

Một cache lưu String/byte[] của mọi HTTP response có thể giữ dữ liệu lâu sau khi request hoàn tất. Cần **max entry bytes**, **max aggregate bytes**, TTL, admission/eviction policy và bounded key/cardinality. Response có size đúng cap per-item nhưng cache tổng không giới hạn vẫn có thể OOM.

### Content-Type

**Content-Type: application/json** không chứng minh payload là JSON hợp lệ hoặc nhỏ. Header có thể giả, charset sai, schema không phù hợp. Dùng parser validation, giới hạn dữ liệu và reject khi sai; không dựa vào Content-Type để nới byte cap một cách tùy tiện.

## 14. Memory-safe design theo loại endpoint

Không phải endpoint nào cũng nên có cùng giới hạn:

| Loại response | Chiến lược đề xuất | Cần ràng buộc thêm |
|---|---|---|
| Config JSON nhỏ | Bounded InputStream/custom subscriber rồi parse | Max bytes, max depth, schema, deadline |
| Paginated API list | Giới hạn từng page, giữ một page tại thời điểm xử lý | Max page count, tổng item count, rate limit |
| Large CSV/NDJSON | Incremental decoder/parser, xử lý từng record | Max line length, bytes, records, time |
| PDF/image download | Bounded streaming to temp file | Disk quota, MIME sniffing, checksum, virus scan nếu cần |
| Gzip JSON | Byte cap cả trước và sau decompress | Compression ratio, parser depth, CPU budget |
| Unknown third-party endpoint | Reject theo allowlist, strict size/time quota | Proxy, redirect, SSRF, auth, egress policy |
| Error response để log | Bounded preview và metadata | Không log secrets/body không giới hạn |

**Không có một maxBytes “đúng cho mọi dự án”.** Một API trả 10 KiB JSON có thể chọn cap vài trăm KiB; một báo cáo 200 MiB cần thiết kế streaming/disk khác. Chọn theo contract endpoint, expected p99 size, loại nội dung, concurrency và tài nguyên có thật.

### Pagination là tối ưu quan trọng

Nếu API hỗ trợ **limit/pageSize/cursor**, nên yêu cầu từng page nhỏ thay vì tải một JSON array khổng lồ. Tuy nhiên **server-side pageSize không thay thế client-side byte cap**, vì một record hoặc server lỗi vẫn có thể trả payload quá lớn. Pagination và byte cap là hai lớp bảo vệ bổ sung.

### Range requests không phải bảo đảm cắt chính xác

Có thể dùng **Range** HTTP để đề nghị lấy một phần dữ liệu, nhưng server **có thể không hỗ trợ hoặc bỏ qua Range** và trả 200 với toàn bộ tài nguyên. Client phải kiểm tra **206 Partial Content**, **Content-Range**, expected offset và vẫn áp byte cap thực tế. Không dựa vào Range header như một memory limiter duy nhất.

## 15. Backpressure và Flow.Subscriber: request(1) không có nghĩa một byte

Trong Java Flow API, **Subscription.request(n)** biểu thị nhu cầu nhận **n onNext signals**, chứ không phải n bytes. Khi BodySubscriber nhận **List<ByteBuffer>**, một tín hiệu onNext có thể chứa nhiều buffers và nhiều byte. Vì vậy:

~~~text
request(1)
    -> onNext([ByteBuffer 4 KiB, ByteBuffer 8 KiB, ...])
    -> count all remaining bytes
    -> reject if total > cap
    -> otherwise process and request(1) again
~~~

**Subscriber phải enforce byte limit bên trong onNext**, bất kể n được request bao nhiêu. Nếu subscriber **request(Long.MAX_VALUE)** để nhận vô hạn rồi enqueue mọi chunk vào một queue không giới hạn, nó có thể dễ dàng OOM dù producer có Flow API.

### Một số quy tắc thực hành

- Không gọi **onNext** từ code application theo ý mình; publisher chịu trách nhiệm gọi theo Flow contract.
- Không chia sẻ ByteBuffer của publisher cho xử lý async ở nơi khác mà không có ownership/copy/lifecycle rõ ràng.
- Hoàn tất **getBody() stage** khi body đủ hoặc thất bại, không để future pending mãi khi reject.
- Khi vượt cap, **cancel subscription** và hoàn tất lỗi; đừng trả body bị cắt rồi xem như JSON hợp lệ.
- Chỉ yêu cầu thêm tín hiệu khi hệ thống còn dung lượng xử lý; nếu downstream queue đầy, tạm dừng request thay vì đệm vô hạn.
- Nếu callback cần parse/IO blocking nặng, dùng bounded executor và không khóa thread dispatch của HttpClient.
- Có cơ chế close/cancel/cleanup nếu application bỏ future hoặc hết overall deadline.

Các yêu cầu này là nguyên tắc concurrency/backpressure; ví dụ CappedSubscriberDemo chỉ mô phỏng cap byte, không tuyên bố đã giải quyết mọi production edge case của Flow.

## 16. Kiểm thử giới hạn phản hồi: ma trận bắt buộc

| Test | Response đầu vào | Hành vi an toàn mong đợi |
|---|---|---|
| Dưới ngưỡng | 5 byte, cap 128 | Được xử lý bình thường |
| Bằng ngưỡng | Đúng 128 byte, cap 128 | Chấp nhận, không lỗi off-by-one |
| Vượt ngưỡng 1 byte | 129 byte, cap 128 | Từ chối trước khi append byte thứ 129 |
| Content-Length lớn | Declared 256, cap 128 | Có thể reject ngay sau headers |
| Chunked không có Content-Length | Chunked 256, cap 128 | Reject khi byte thực vượt cap |
| Header báo nhỏ, decoder phình to | Gzip nhỏ, decoded lớn | Chặn bằng maxDecodedBytes |
| Body có một line cực dài | NDJSON/CSV không newline | Giới hạn line length trước khi tạo String quá lớn |
| Streaming vô hạn nhỏ giọt | Tổng byte chưa vượt cap | Dừng bằng deadline/idle timeout |
| Nhiều concurrent responses | N request mỗi body gần cap | Bảo vệ tổng heap budget, queue/concurrency |
| Error response oversized | HTTP 500 với HTML khổng lồ | Không log/read unbounded error body |
| Redirect tới host khác | 302 tới response lớn | Áp cùng policy/allowlist/SSRF protection |
| Client timeout/cancel giữa stream | Future/stream đang pending | Close/cancel và dọn buffer/temp file |
| File download quá lớn | Body lớn hơn disk quota | Dừng ghi, xóa temp file, không commit |
| Parser sâu/quá nhiều items | JSON nhỏ vừa nhưng nested cực sâu | Giới hạn độ sâu/độ phức tạp parser |

**Kiểm thử server local có thể dự đoán byte count**, nhưng không nên assert network timing chính xác từng ms. Khi thêm concurrency và backpressure, đo cả **peak heap/GC pressure** và **request completion time** dưới tải được cấp phép. Đừng gửi payload cực lớn vào dịch vụ public chỉ để thử giới hạn.

### Metrics vận hành

Ghi lại **response_bytes_received**, **Content-Length declared**, **body_limit_bytes**, **BODY_TOO_LARGE rejections**, **decoded_bytes**, **compression_ratio**, **active_response_streams**, **buffered_bytes_global**, **stream_duration**, **timeouts**, **cancellation_count**, **file_cleanup_failures**, **GC pause/p95/p99 latency**.

Có thể dùng **per-endpoint/body-policy labels** nhưng phải giới hạn cardinality: không đưa URL đầy đủ có user ID/token hoặc request body vào tên metric. Log đủ correlation ID và nguyên nhân lỗi; mask secrets và tránh log toàn bộ response lớn.

## 17. Trường hợp response từ API bạn kiểm soát

Nếu bạn quản lý cả client lẫn server, **giải pháp tốt nhất thường bắt đầu từ protocol design**:

- Thiết kế **pagination** hoặc streaming thay vì JSON array vô hạn.
- Đặt **maxResults/pageSize**, số byte/record và deadline trên server; trả lỗi có cấu trúc khi request đòi dữ liệu quá lớn.
- Hỗ trợ **Content-Length chính xác** khi kích thước đã biết, nhưng client vẫn phải kiểm tra actual bytes.
- Nén response khi phù hợp, đồng thời chặn decompressed size tại phía nhận.
- Giới hạn **records/bytes/time** trong serialization để server không tự OOM khi tạo response.
- Gửi status lỗi nhỏ, không đính kèm stack traces hoặc dữ liệu nhạy cảm khổng lồ.
- Dùng backpressure khi tải qua HTTP/2 hoặc reactive pipelines; không chỉ chuyển nơi tích tụ dữ liệu từ client sang queue của server.
- Thiết lập SLO về response size/latency và kiểm thử hợp đồng hai phía.

**Một API tự tuyên bố Content-Length <= 64 KiB không đủ để bỏ trần phía client**. Network, proxy, code version mới hoặc server bug vẫn có thể vi phạm contract.

## 18. Các lỗi lập trình thường gặp và cách sửa

### Lỗi 1 — Gom toàn bộ rồi mới kiểm tra

Sai: dùng **ofByteArray()/ofString()** cho nguồn không đáng tin, sau đó kiểm tra length. Sửa: giới hạn trong subscriber hoặc bounded InputStream **trước khi tạo byte[]/String**.

### Lỗi 2 — Tin tuyệt đối Content-Length

Sai: chỉ reject nếu firstValueAsLong > cap rồi đọc phần còn lại vô hạn. Sửa: **đếm byte đọc thực**, hỗ trợ thiếu header/chunked.

### Lỗi 3 — Nhầm chunk size với total size

Sai: chọn buffer 4 KiB rồi append mãi vào ByteArrayOutputStream. Sửa: tổng byte counter và policy reject tại ngưỡng.

### Lỗi 4 — Bỏ qua lượng dữ liệu sau giải nén

Sai: gzip 100 KiB dưới cap, giải nén thành 500 MiB rồi parse JSON. Sửa: **hai trần encoded/decoded** và giới hạn parser.

### Lỗi 5 — Không close InputStream khi exception

Sai: throw vì vượt cap nhưng bỏ quên stream. Sửa: **try-with-resources**, close/cancel và cleanup.

### Lỗi 6 — Stream xuống file không giới hạn

Sai: cho rằng BodyHandlers.ofFile là giải pháp đủ an toàn. Sửa: enforce disk/body quota **trong lúc ghi**, temp file, cleanup và commit an toàn.

### Lỗi 7 — Cắt body rồi coi là JSON đầy đủ

Sai: lấy first N bytes và return success nếu JSON parser không báo ngay lỗi. Sửa: **reject oversized** trừ khi giao thức cho phép **truncation** có đánh dấu và checksum/partial semantics rõ ràng.

### Lỗi 8 — Không áp limit cho error response

Sai: HTTP 500 trả HTML hàng chục MiB và code log nguyên body. Sửa: limited error preview, mask và policy ngắn.

### Lỗi 9 — Chỉ giới hạn một request, quên concurrency

Sai: mỗi response tối đa 10 MiB, 1.000 requests song song. Sửa: semaphore, max aggregate buffered bytes, load shedding, bounded queues.

### Lỗi 10 — Chỉ đặt timeout, không giới hạn bytes

Sai: HttpRequest.timeout(2s) rồi assume body không thể OOM. Sửa: time budget **và** byte budget là hai giới hạn độc lập.

### Lỗi 11 — Flow.Subscription.request(1) được coi là 1 byte

Sai: giữ onNext mà không đếm List<ByteBuffer> bytes. Sửa: đếm buffer.remaining() trước mỗi copy, cancel on limit.

### Lỗi 12 — Không giới hạn số phần tử và parser depth

Sai: body nhỏ dưới cap nhưng JSON parser tạo object graph không giới hạn theo nhu cầu ứng dụng. Sửa: schema/record/depth/token limits, streaming parse và quota CPU.

## 19. Bài tập thực hành

### Bài tập A — Biên đúng một byte

Sửa **BoundedStreamDemo** để server trả **127, 128 và 129 byte** theo ba endpoint. Kiểm tra 127/128 được chấp nhận, 129 bị từ chối. Giải thích vì sao điều kiện đúng là **read > maxBytes - total**, không phải **read >= maxBytes - total**.

### Bài tập B — Bỏ kiểm tra Content-Length

Tạm thời bỏ phần precheck header khỏi readBounded nhưng giữ actual-byte cap. Chạy lại endpoint **/declared**; lý do nào khiến response vẫn bị từ chối? Vì actual-byte cap vẫn còn. Giải thích lợi ích **performance/bandwidth** của precheck khi header đáng tin để từ chối sớm.

### Bài tập C — Chunked stream

Dùng **/chunked**, thêm số chunk/size log trong server và đo bao nhiêu byte đến consumer trước khi abort. Không hardcode số lần InputStream.read vì ranh giới read có thể khác từng lần run.

### Bài tập D — Không dùng ByteArrayOutputStream

Sửa hàm readBounded để đọc từng chunk và **tính SHA-256 digest** mà không giữ toàn bộ payload. Vẫn đặt cap 128 và in checksum hex của body nhỏ. So sánh peak heap với cách thu toàn bộ body.

### Bài tập E — Custom BodySubscriber

Chạy **CappedSubscriberDemo**, thay 128 bằng 5. Xác nhận response 5 byte thành công, response 256 byte bị reject. Giải thích **request(1)** đếm **onNext signal**, không đếm byte.

### Bài tập F — Disk quota

Tạo bounded downloader tới một temp path do bạn kiểm soát, dùng byte[8192] và tổng byte counter trước khi ghi. Khi vượt cap, abort, đóng stream, xóa temp file. Kiểm tra không còn file chưa hoàn chỉnh sau lỗi.

### Bài tập G — Gzip decompression bomb

Tạo một sample gzip nhỏ chứa dữ liệu lặp lại trong môi trường local, cho maxWireBytes đủ chứa nhưng maxDecodedBytes thấp. Bảo đảm decoder bị dừng khi uncompressed bytes vượt trần. Không dùng dữ liệu cực lớn hoặc chạy ngoài môi trường được phép.

### Bài tập H — Concurrency budget

Giả sử heap hữu ích còn 256 MiB, mỗi response cần tối đa 2 MiB raw bytes và parser có thể dùng nhiều lần số đó. Đề xuất số concurrent requests tối đa có dự phòng, rồi áp semaphore/bounded queue. Dùng load test nhỏ để quan sát GC và peak heap, không đánh giá bằng công thức lý thuyết đơn độc.

### Bài tập I — Error body

Cho server trả HTTP 500 với 1 MiB HTML, client chỉ log **tối đa 1 KiB đã kiểm tra** và không parse như JSON. Phân biệt “error preview bị rút gọn” với “body HTTP hợp lệ được xử lý đầy đủ”; không bỏ bảo vệ vì status không phải 200.

### Bài tập J — Streaming parser

Cho server trả NDJSON gồm nhiều record nhỏ và một record cực dài. Dùng streaming decoder để đếm record, maxTotalBytes và maxRecordBytes, từ chối record dài trước khi tạo String cực lớn.

## 20. Câu hỏi tự kiểm tra

**1. Vì sao ofString() nguy hiểm với nguồn không đáng tin?** Vì nó có thể gom toàn bộ body thành String không có byte cap nghiệp vụ.

**2. ofByteArray() + if (length > cap) đã an toàn heap chưa?** Chưa; việc cấp phát byte[] lớn xảy ra **trước** khi kiểm tra.

**3. Content-Length có đủ để làm giới hạn?** Không; có thể thiếu/chunked hoặc không bao quát phần giải nén. Phải đếm actual bytes.

**4. Đọc InputStream bằng buffer 4 KiB có nghĩa tổng bộ nhớ 4 KiB?** Không nếu tiếp tục append vào ByteArrayOutputStream/List; cần trần tổng.

**5. Điều kiện đúng khi đã nhận total byte và đọc thêm n byte?** **n > cap - total** để reject trước khi copy, với invariant 0 <= total <= cap.

**6. Response đúng bằng cap có hợp lệ?** Có, theo chính sách “tối đa cap byte”; chỉ reject khi **vượt** cap.

**7. Vì sao body nén cần hai giới hạn?** Compressed size nhỏ không bảo đảm decompressed size nhỏ; cần maxEncodedBytes và maxDecodedBytes.

**8. ofFile() có bảo vệ đĩa khỏi payload vô hạn không?** Không; phải dùng disk quota, byte cap trong lúc ghi và cleanup.

**9. request(1) trong Flow có nghĩa tải đúng một byte không?** Không; nó yêu cầu một onNext signal, có thể mang List<ByteBuffer> lớn.

**10. BodySubscriber khi quá cap nên trả bản cắt hay báo lỗi?** Nên báo lỗi/cancel, không coi dữ liệu bị cắt là response hoàn chỉnh.

**11. HttpRequest.timeout có thay byte cap được không?** Không. Tốc độ network cao có thể chuyển rất nhiều byte trước timeout.

**12. Một response cap 1 MiB với 10.000 requests song song đã đủ bảo vệ heap?** Chưa; cần max concurrency/aggregate buffered bytes.

**13. Vì sao JSON sau khi nhận phải có giới hạn depth/items?** Vì object graph và CPU parser có thể vượt xa raw byte size.

**14. Tại sao cần close response.body() khi vượt ngưỡng?** Để giải phóng stream/connection resources và không tiếp tục nhận dữ liệu không cần.

**15. HTTP 413 có phải exception client download oversized chuẩn của Java không?** Không; 413 là mã trạng thái HTTP thường dành cho request content quá lớn.

**16. Nếu BodyHandler trả InputStream, khi HttpResponse xuất hiện đã chắc body được đọc xong?** Không; application còn trách nhiệm đọc/đóng và đặt deadline riêng cho tiêu thụ stream.

## Tài liệu chính thức Java 17 và HTTP

- **Java SE 17 — HttpResponse.BodyHandlers:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- **Java SE 17 — HttpResponse.BodySubscribers:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html
- **Java SE 17 — HttpResponse.BodySubscriber:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html
- **Java SE 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java SE 17 — HttpHeaders:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html
- **Java SE 17 — Flow.Subscription:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- **Java SE 17 — InputStream:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- **RFC 9110 — HTTP Semantics:** https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9112 — HTTP/1.1 Message Framing:** https://www.rfc-editor.org/rfc/rfc9112

**Ghi nhớ:** **Đừng gom response HTTP không giới hạn vào heap** bằng ofString/ofByteArray rồi mới kiểm tra. Dùng **Content-Length để từ chối sớm**, nhưng **luôn đếm byte thực nhận**; khi cần stream lớn thì xử lý tăng dần hoặc ghi xuống file có quota, không thu toàn bộ vào String/List/ByteArrayOutputStream vô hạn. Với compressed data cần kiểm tra **cả encoded và decoded bytes**. Kết hợp **body byte cap, parser limits, total concurrency/memory budget, deadline, backpressure, cancellation và cleanup** để bảo vệ hệ thống trước payload quá lớn, server lỗi và dữ liệu cố ý gây quá tải.