# Đọc hết, đóng hoặc hủy HTTP response body dạng luồng để giải phóng tài nguyên trong Java

Khi gọi HTTP bằng `java.net.http.HttpClient`, developer thường tập trung vào status code và dữ liệu cần lấy. Nhưng với **response body dạng luồng**, việc nhận được đối tượng `HttpResponse` **không đồng nghĩa response đã được đọc hết**. Nếu ứng dụng chỉ xem headers/status rồi bỏ `InputStream`, `Stream<String>` hoặc reactive `Publisher` mà không tiêu thụ hay hủy đúng cách, HTTP exchange có thể tiếp tục giữ buffer, subscription, connection hoặc những tài nguyên khác. Khi lặp qua nhiều request, hệ quả có thể là giảm khả năng tái sử dụng kết nối, pending response kéo dài, chậm, memory tăng, tắc pool/stream hoặc request về sau timeout.

Trọng tâm của bài: **mỗi body dạng luồng phải có người sở hữu và một đường kết thúc rõ ràng**. Sau khi nhận response, hãy chọn **một trong ba cách**, tương ứng với API:

1. **Đọc đến hết (EOF / terminal signal)** khi còn muốn toàn bộ nội dung và kích thước/tốc độ hợp lý.
2. **Đóng body stream** khi không còn muốn đọc (`InputStream.close()` hoặc `Stream.close()`).
3. **Hủy subscription** với reactive publisher (`Flow.Subscription.cancel()`), hoặc hủy exchange async **trước khi future hoàn thành** theo contract.

Việc đọc hết thường giúp triển khai có cơ hội tái sử dụng HTTP connection; **đóng/hủy sớm** là cách giải phóng trách nhiệm xử lý response không còn cần thiết, nhưng có thể khiến connection không tái sử dụng được. **Không có quy tắc “luôn tải hết mọi body chỉ để tiết kiệm connection”**: với body vô hạn, rất lớn hoặc peer chậm, tiếp tục tải có thể tốn băng thông, CPU và thời gian nhiều hơn tạo connection mới.

Bài học sử dụng **Java 17+**, module `java.net.http` (có từ Java 11), kèm hai chương trình độc lập chạy trên loopback, không cần Internet: một chương trình kiểm tra đầy đủ `InputStream`/`ofLines` và một chương trình thực hành `Flow.Publisher` có completion/cancellation.

## 1. Vòng đời của HTTP response khác vòng đời của Java object

Một request có thể trải qua:

~~~text
Tạo HttpRequest
       |
HttpClient.send / sendAsync
       |
Nhận status + headers
       |
       +------ BodyHandlers.ofString()/ofByteArray()
       |            |
       |       body được gom đầy đủ trước khi response sẵn sàng
       |            |
       |          DONE
       |
       +------ BodyHandlers.ofInputStream()
       |            |
       |       HttpResponse<InputStream> đã trả về,
       |       nhưng response bytes còn có thể chưa đến hết
       |            |
       |       READ TO EOF  ---- hoặc ---- CLOSE EARLY
       |
       +------ BodyHandlers.ofLines()
       |            |
       |       Stream<String> vẫn đọc từng dòng từ HTTP body
       |            |
       |       CONSUME ALL ---- hoặc ---- Stream.close()
       |
       +------ BodyHandlers.ofPublisher()
                    |
               Flow.Publisher<List<ByteBuffer>>
                    |
                SUBSCRIBE EXACTLY ONCE
                    |
              request items -> onNext...
                    |
               onComplete/onError ---- hoặc ---- cancel
~~~

`HttpResponse<T>` có `body()` trả về kiểu `T` do `BodyHandler` chọn. Một số body là **giá trị đã hoàn thành** (`String`, `byte[]`, `Path` sau `ofFile`); những body khác là **cổng đọc dữ liệu tiếp theo** (`InputStream`, `Stream<String>`, `Flow.Publisher`). Đối tượng `HttpResponse` trong Java 17 **không có `close()`** và không phải `AutoCloseable`; hãy đóng/tiêu thụ **đúng đối tượng body**.

| BodyHandler | Kiểu `HttpResponse.body()` | Khi response sẵn sàng | Việc caller phải làm |
| --- | --- | --- | --- |
| `ofString()` | `String` | Sau khi body đã được đọc/giải mã | Xử lý dữ liệu; không có stream cần đóng, nhưng phải giới hạn kích thước đầu vào |
| `ofByteArray()` | `byte[]` | Sau khi body đã được đọc đầy đủ | Quản lý memory, không có body stream cần đóng |
| `discarding()` | `Void` | Sau khi body đã được tiêu thụ và bỏ | Dùng khi biết trước không cần body; **vẫn có chi phí tải/tiêu thụ** |
| `ofFile(path)` | `Path` | Sau khi body được ghi vào file | Quản lý file output/quota/file dở nếu lỗi |
| `ofInputStream()` | `InputStream` | **Sau headers**, trước khi body nhất thiết hoàn thành | **Read tới EOF hoặc close** |
| `ofLines()` | `Stream<String>` | **Sau headers**, body có thể còn đang truyền | **Consume hết dòng hoặc close stream** |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **Sau headers**, body có thể còn đang truyền | **Subscribe một lần, consume tới terminal hoặc cancel** |

**Status code không thay đổi nghĩa vụ cleanup.** Một response 404 hay 500 vẫn có thể mang response body đầy đủ; việc đọc `response.statusCode()` rồi `return` mà không đóng `body()` là lỗi ownership tương tự với response 200.

### 1.1. Hai loại hoàn thành khác nhau

Ví dụ:

~~~java
HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());
System.out.println(response.statusCode());
// DÒNG NÀY KHÔNG CHỨNG MINH body đã đọc tới EOF.
~~~

`HttpClient.send(...)` ở đây đã trả về headers/status và một stream có thể đọc được, **không nhất thiết đã nhận toàn bộ body**. Nếu sau đó quên xử lý stream, response exchange có thể còn resources. Ngược lại:

~~~java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
// response.body() lúc này là String đã được tạo.
~~~

Hai đoạn là **minh họa đặt trong phương thức Java**, giả định `client`/`request` có sẵn và có import `java.net.http.*`, xử lý `IOException`/`InterruptedException`. Với `ofString`, thư viện gom body trước khi hoàn tất response; vì vậy nên tránh với payload không có giới hạn. Với streaming, thư viện giao trách nhiệm tiêu thụ cho caller sớm hơn.

## 2. Chọn “đọc hết” hay “đóng/hủy” theo dữ liệu thực tế

| Trường hợp | Quyết định chính | Vì sao |
| --- | --- | --- |
| Response nhỏ, hợp lệ, application thực sự cần mọi byte | Đọc tới `-1`/EOF | Đảm bảo đủ dữ liệu và tạo điều kiện cho connection reuse |
| Stream là JSON/file lớn nhưng cần xử lý đầy đủ | Đọc theo chunk/streaming parser với size cap | Tránh giữ toàn bộ body trong RAM |
| Chỉ cần 2 dòng đầu, hoặc tìm thấy thông tin đủ dùng | Đóng `InputStream` / `Stream` ngay sau phần cần | Không tải tiếp vô hạn chỉ để mong tái sử dụng connection |
| Status 404/500, cần error detail nhỏ | Đọc error body có cap rồi đến EOF nếu phù hợp | Có thể lấy thông tin chẩn đoán, tránh bỏ quên exchange |
| Status không thành công và body có thể rất lớn | Chỉ đọc phần lỗi cần thiết rồi close | Bảo vệ memory/bandwidth, chấp nhận mất reuse |
| Body không cần ngay từ đầu | `BodyHandlers.discarding()` hoặc policy hủy phù hợp | Đơn giản hóa cleanup, nhưng `discarding` vẫn nhận/bỏ dữ liệu |
| Reactive subscriber xử lý hết | Xin items, nhận `onComplete`/`onError` | Terminal signal hoàn tất protocol subscriber |
| Reactive subscriber không thể xử lý tiếp | `subscription.cancel()` | Thông báo ngừng tiêu thụ; không đợi `onComplete` |
| Async request còn pending và user rút yêu cầu | `future.cancel(true)` trên future do `sendAsync` trả về | Cố gắng hủy HTTP exchange, best-effort |
| Future streaming đã hoàn thành và đã trao `InputStream` | **Đóng body**, không chỉ gọi `future.cancel(true)` | Future đã hoàn thành không thay thế ownership của body |

Một response body có thể dài không xác định (`Transfer-Encoding: chunked` trong HTTP/1.1, streaming HTTP/2, server-sent events). **Không có giới hạn byte, thời hạn và nhu cầu nghiệp vụ** thì “đọc đến EOF” có thể chờ vô hạn hoặc chiếm network không cần thiết. Dùng timeout/deadline, max body bytes và chính sách cancel/close rõ ràng.

## 3. `BodyHandlers.ofInputStream()`: luôn xử lý qua `try-with-resources`

Java 17 Javadoc ghi rõ: để giải phóng resources của HTTP exchange, caller phải **đọc toàn bộ bytes đến EOF** hoặc **gọi `InputStream.close()`** nếu không thể/không muốn đọc hết. Đóng trước EOF có thể khiến underlying HTTP connection bị đóng và không được tái sử dụng.

Mẫu đúng cho body còn cần:

~~~java
HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = body.read(buffer)) != -1) {
        processBytes(buffer, 0, n);
    }
}
// Tới EOF; try-with-resources vẫn close nếu processBytes lỗi.
~~~

Đây là **đoạn minh họa, không chạy độc lập**: giả định đã import `java.io.*`, `java.net.http.*` và có `client`, `request`, `processBytes`. `processBytes` là hàm nghiệp vụ. Điều cần học là **close nằm trong lexical scope**, nên cả khi parser ném exception, vòng lặp bị break hoặc caller return, stream vẫn được đóng.

### 3.1. `read() == -1` mới là EOF

`InputStream.read(byte[])` trả:
- số byte dương khi có dữ liệu;
- `-1` khi đạt EOF;
- có thể block khi chưa có dữ liệu;
- ném `IOException` nếu lỗi I/O/connection.

`body.available() == 0` **không chứng minh EOF**; `available()` chỉ ước lượng số byte có thể đọc mà không block. Không viết:

~~~java
while (body.available() > 0) {
    body.read(buffer);
}
// SAI: có thể dừng sớm khi network chưa giao hết DATA.
~~~

Nếu cần kiểm tra hoàn tất, phải đọc tới `-1` hoặc đến terminal signal theo API. Đừng lấy `Content-Length` trong headers làm chứng cứ duy nhất đã nhận đủ dữ liệu: response có thể không có header đó, chuyển mã, bị cắt kết nối hoặc có framing/transfer semantics khác. Khi cần integrity, xác nhận theo protocol/size/checksum riêng.

### 3.2. Giới hạn byte trước khi xử lý

Để chống response body không đáng tin cậy hoặc quá lớn:

~~~java
long maxBytes = 10L * 1024 * 1024;
long total = 0;
byte[] buffer = new byte[8192];

try (InputStream body = response.body()) {
    int n;
    while ((n = body.read(buffer)) != -1) {
        if (n > maxBytes - total) {
            throw new IOException("Body exceeds 10 MiB limit");
        }
        total += n;
        processBytes(buffer, 0, n);
    }
}
~~~

Đây là **pseudocode nằm trong phương thức Java**, với response/processBytes giả định. Dùng `n > maxBytes - total` để tránh cộng tràn khi count có thể lớn. Khi vượt cap, ném exception, `try-with-resources` **close body sớm**. Không nên tiếp tục drain vài gigabyte chỉ để giữ connection reusable.

Với parser JSON/XML/ZIP, cap số **byte truyền**, số **byte giải nén**, số **object/nesting level** hoặc file size có thể cần đặt riêng. Giới hạn 10 MiB trên bytes nhận không tự chống decompression bomb hoặc CPU-exhausting parse.

### 3.3. Tránh `readAllBytes()` với nguồn không giới hạn

~~~java
byte[] all = response.body().readAllBytes(); // dễ vượt heap nếu body lớn
~~~

Đoạn trên vừa có nguy cơ tích dữ liệu quá lớn, vừa **không cho thấy close**. Nếu body nhỏ đã được xác thực giới hạn, vẫn cần try-with-resources. Với body có thể rất lớn, dùng chunked reads hoặc `BodyHandlers.ofFile(...)` với quota và file cleanup. `readNBytes(k)` chỉ đọc **tối đa k bytes**, không tự nhận toàn bộ response đã được hoàn thành.

## 4. `close()` sớm: chủ động bỏ body, không hứa reuse

Khi chỉ cần header/status hoặc vài byte đầu:

~~~java
HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] prefix = body.readNBytes(8);
    usePrefix(prefix);
}
// Nếu body còn lại: close đã được gọi; exchange không bị bỏ quên.
~~~

Đoạn này là **minh họa**, `usePrefix` là hàm do ứng dụng định nghĩa. `close()` không có nghĩa “server ngừng gửi ngay vào đúng thời điểm dòng Java đó chạy”; hủy có thể được thực hiện **bất đồng bộ/best-effort** tùy implementation và network state. Không được khẳng định underlying TCP connection chắc chắn còn sống hoặc chắc chắn đóng.

### 4.1. Tại sao close sớm có thể mất keep-alive?

HTTP connection có thể tái sử dụng khi thư viện đã giải quyết xong message trước và còn phù hợp với pooling policy. Với HTTP/1.1 keep-alive, nếu body chưa được đọc hết, phần bytes chưa tiêu thụ có thể còn nằm trên cùng TCP stream; implementation có thể **đóng connection** thay vì giữ nó cho request tiếp theo, tránh nhầm bytes. Với HTTP/2, connection chứa nhiều stream độc lập, nên hủy một stream có thể dẫn tới reset stream chứ không nhất thiết đóng toàn connection. Tuy nhiên **JDK 17 Javadoc chỉ cam kết khả năng**, không cam kết chính xác protocol-specific reuse sau mọi loại cancellation.

- **Consume EOF** giúp exchange kết thúc sạch và *có cơ hội* tái sử dụng connection.
- **Close sớm** giải phóng trách nhiệm đọc body nhưng *có thể* làm mất reuse.
- **Không close, không consume** là rủi ro resource retention, không phải chiến lược giữ keep-alive.

Đừng ép tải body cực lớn để tiết kiệm một TCP/TLS handshake; chọn theo chi phí thật và SLA.

### 4.2. `close` không có nghĩa giải phóng mọi tài nguyên của ứng dụng

Khi parser giữ tham chiếu tới `byte[]`, connection-level queue, file temp, worker task hoặc cache, đóng body stream **không tự cleanup** những tài nguyên application khác. Thiết kế luôn xác định owner riêng cho:
- input stream;
- output file/temporary file;
- decoder/parser;
- task/CompletableFuture;
- queued buffers;
- network request deadline.

Đóng stream không giải phóng `HttpClient` object theo một nghĩa phải gọi `HttpClient.close()` trên Java 17. **Java 17 `HttpClient` không cung cấp `close()` như một API chính thức**; quản lý ownership của từng streaming body mới là điểm chính.

## 5. Response lỗi HTTP vẫn có body cần xử lý

Một lỗi thiết kế thường thấy:

~~~java
HttpResponse<InputStream> r =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

if (r.statusCode() >= 400) {
    throw new IOException("HTTP error " + r.statusCode());
}
// SAI: thoát sớm mà không close r.body().
~~~

Phương thức `send` với `ofInputStream()` có thể đã trả response body stream dù status code `404`, `429` hoặc `500`. Nếu ném exception trước khi lấy/đóng body, exchange bị bỏ dở.

Mẫu đúng:

~~~java
HttpResponse<InputStream> r =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = r.body()) {
    int status = r.statusCode();
    if (status >= 400) {
        byte[] detail = body.readNBytes(4096);
        logSafeError(status, detail);
        // Sau đoạn này body có thể chưa EOF; try vẫn close.
        throw new IOException("HTTP " + status);
    }
    consumeSuccess(body);
}
~~~

Đây là **pseudocode ứng dụng**: `logSafeError` và `consumeSuccess` chưa định nghĩa, cần chính sách tránh log secret/PII. `readNBytes(4096)` giới hạn lượng **được lưu để log**, nhưng ứng dụng phải có deadline để tránh bị server chậm treo khi đọc. Nếu không cần error body, vẫn lấy body vào `try` rồi close ngay. Không có `HttpResponse.getErrorStream()` trong `java.net.http.HttpClient`; đây là API khác của `HttpURLConnection`.

Lưu ý: response `204 No Content`, `304 Not Modified`, hoặc response cho `HEAD` có semantics không có body theo HTTP. Với streaming BodyHandler, cách viết nhất quán vẫn là **sở hữu/đóng đối tượng body trả về** khi có; một EOF rỗng là hợp lệ. Đừng dựa vào status “chắc chắn rỗng” để bỏ qua cleanup generic.

## 6. `BodyHandlers.ofLines()`: `Stream<String>` cũng cần `close()`

`ofLines()` trả `HttpResponse<Stream<String>>`; từng dòng được giải mã khi đọc body. Đây là **stream tài nguyên**, không phải `List<String>` được tải hoàn tất từ đầu. Nó cần được **consume hết** hoặc **đóng** theo Javadoc `BodySubscribers.ofLines`.

Ví dụ:

~~~java
HttpResponse<Stream<String>> r =
        client.send(request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = r.body()) {
    lines.forEach(System.out::println); // đi hết nếu không lỗi
}
~~~

Đây là đoạn minh họa, import `java.util.stream.Stream`. Nếu stream lỗi khi decode/receive hoặc consumer ném exception, `try-with-resources` vẫn close. Không nên gọi operations song song trên cùng body stream nếu thư viện/stream nguồn không đảm bảo điều đó.

### 6.1. `limit(2)`, `findFirst()` không có nghĩa đã đọc hết

~~~java
try (Stream<String> lines = response.body()) {
    List<String> firstTwo = lines.limit(2).toList();
    handle(firstTwo);
}
~~~

Nếu server gửi 10.000 dòng, `limit(2)` là **short-circuit terminal operation**; chỉ lấy đủ hai dòng đầu và có thể để lại rất nhiều bytes. Dòng `try` gọi `lines.close()` khi kết thúc, dọn resource của streaming body. `findFirst()`, `anyMatch()`, `takeWhile()` cũng có thể dừng sớm. **Một terminal operation hoàn thành không tự chứng minh underlying HTTP body đã EOF**.

`Stream.close()` là hoạt động riêng: đọc hết stream là một sự kiện, đóng resource là sự kiện khác; bài này khuyến nghị dùng `try-with-resources` cho mọi đường xử lý để an toàn cả khi exception hoặc short-circuit.

### 6.2. Charset và line length

`BodyHandlers.ofLines()` lấy charset từ thông tin response headers theo Javadoc; nếu charset không có/không phù hợp, policy mặc định của handler áp dụng. **Đọc từng dòng không có nghĩa mỗi dòng có kích thước nhỏ**. Một dòng đơn lẻ rất dài không chứa delimiter vẫn có thể tiêu tốn memory lớn. Với dữ liệu không tin cậy, cân nhắc parser có giới hạn số ký tự/byte trên mỗi dòng, tổng số dòng và tổng body, hoặc custom `BodySubscriber`.

Không lấy `Stream<String>` được trả từ response rồi cache lại để xử lý “sau này” mà không có quy tắc lifetime; task có thể giữ network exchange qua nhiều phút. Chuyển ownership rõ ràng, đặt deadline và close trong chính task đảm nhiệm tiêu thụ.

## 7. `BodyHandlers.ofPublisher()`: subscribe một lần, terminal hoặc cancel

`ofPublisher()` tạo `HttpResponse<Flow.Publisher<List<ByteBuffer>>>`. Response này sẵn sàng **sau headers**, publisher cung cấp body theo cơ chế `Flow`. Từ Javadoc Java 17:

- Publisher của response **chỉ được `subscribe` một lần**.
- Caller phải **subscribe** và request dữ liệu cho đến `onComplete`/`onError` **hoặc** gọi `subscription.cancel()` khi dừng sớm.
- `onSubscribe(Flow.Subscription)` cung cấp subscription mà subscriber dùng để `request(n)` và `cancel()`.
- `onNext(List<ByteBuffer>)` nhận **một item chứa danh sách buffers**. `request(1)` xin một **item**, không phải 1 byte.
- Khi `cancel()`, có thể **không nhận `onComplete` hay `onError`**; cancel là best-effort và vẫn có thể có tín hiệu dữ liệu đã in flight theo contract `Flow`.

Ví dụ logic:

~~~java
publisher.subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
    private Flow.Subscription subscription;

    @Override public void onSubscribe(Flow.Subscription s) {
        this.subscription = s;
        s.request(1);
    }
    @Override public void onNext(List<ByteBuffer> buffers) {
        processBuffers(buffers); // phải xử lý/retain ownership đúng
        if (stillNeeded()) {
            subscription.request(1);
        } else {
            subscription.cancel();
        }
    }
    @Override public void onError(Throwable error) {
        reportError(error);
    }
    @Override public void onComplete() {
        reportCompleted();
    }
});
~~~

Đây là **pseudocode**, vì `publisher`, `processBuffers`, `stillNeeded`, `reportError` và `reportCompleted` là thành phần ứng dụng. Java syntax đúng cho anonymous subscriber khi có `publisher` kiểu phù hợp và `java.nio.ByteBuffer`, `java.util.List`, `java.util.concurrent.Flow` được import.

**Quan trọng:** nếu caller lấy publisher nhưng không `subscribe`, nó không thực hiện flow đủ để kết thúc body. Nếu subscribe mà không gọi `request(n)`, flow có thể dừng vĩnh viễn. Nếu ngừng xử lý mà không `cancel()`, exchange có thể giữ resources. Và **không hẹn đợi `onComplete` sau cancel** vì Flow contract không bảo đảm signal này xảy ra.

### 7.1. `onError` cũng là terminal

Trong phản hồi không thành công ở tầng network, `onError` là signal kết thúc; không gọi `request` nữa. Phân biệt:
- HTTP status code `500` là **response HTTP bình thường về mặt transport** và có thể có body, không tự động là `onError`.
- `onError` của subscriber là lỗi trong stream/transport/subscriber processing.
- `onComplete` nghĩa publisher kết thúc gửi items theo contract, không có nghĩa business operation ứng dụng thành công.

Đừng để một exception ném không kiểm soát từ `onNext` làm subscriber rơi vào trạng thái không cleanup; design handler bắt và chuyển sang cancel/report theo policy.

### 7.2. Cần ownership của `List<ByteBuffer>`

`BodySubscriber` nhận danh sách `ByteBuffer` có thứ tự biểu diễn response body. Khi giữ reference để xử lý async, cần quy định ai sở hữu buffer, ai được thay đổi `position/limit`, có copy khi chuyển cho worker hay không, memory cap và làm thế nào gửi request backpressure lên upstream. Đừng gom mọi `List<ByteBuffer>` vào một `ArrayList` không giới hạn khi downstream chậm. Chỉ `request(1)` sau khi xử lý xong item hiện tại hoặc enqueue được trong bounded queue; đừng `request(Long.MAX_VALUE)` mù quáng.

## 8. Async `sendAsync` cancellation khác close body sau khi future hoàn thành

Java 17 Javadoc của `HttpClient.sendAsync`: default implementation trả `CompletableFuture` có hỗ trợ cancellation. Nếu `future` **chưa hoàn thành**, `future.cancel(true)` cố hủy HTTP exchange để giải phóng tài nguyên **sớm nhất có thể**, nhưng **không bảo đảm chính xác lúc nào** cancellation có hiệu lực.

- Với HTTP/1.1, hủy có thể làm underlying connection đóng đột ngột.
- Với HTTP/2, hủy có thể gây reset stream thay vì đóng toàn connection.
- Request có thể đã được gửi và server đã xử lý trước khi cancellation đến. **Cancel không đảo ngược side effects của POST/PUT**.

Ví dụ:

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

if (userCancelledBeforeResponse) {
    future.cancel(true);
}
~~~

Đoạn này là **minh họa**: `userCancelledBeforeResponse` là trạng thái ứng dụng chưa định nghĩa. Sau khi future **đã hoàn thành** với `HttpResponse<InputStream>`, caller/continuation là chủ sở hữu `response.body()`. Hủy future đã hoàn thành **không thay thế việc close body stream**. Đối với response streaming, future có thể hoàn thành khi mới đọc headers, nên điều này đặc biệt quan trọng.

### 8.1. Pattern async an toàn: continuation sở hữu stream

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

CompletableFuture<Long> processed = future.thenApplyAsync(response -> {
    try (InputStream body = response.body()) {
        long total = 0;
        byte[] chunk = new byte[8192];
        int n;
        while ((n = body.read(chunk)) != -1) {
            total += n;
            processChunk(chunk, n);
        }
        return total;
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
}, dedicatedBodyExecutor);
~~~

Đây là **pseudocode có các phụ thuộc**: `client`, `request`, `processChunk` và `dedicatedBodyExecutor` do ứng dụng cung cấp. Đọc network body có thể **block**, nên không dồn hàng trăm response-consuming continuations lên một executor quá nhỏ hoặc event-loop/selector thread. Dùng bounded executor/work queue và backpressure, timeout/deadline, bảo vệ task được hủy khi vẫn sở hữu stream.

Một điểm nâng cao: nếu `thenApplyAsync` không được thực thi vì bị cancel/race/executor từ chối sau khi response đã sẵn sàng, ứng dụng cần cơ chế **handoff ownership và cleanup** cho body đã trả về. Trong code production, đặt giới hạn queue trước khi chấp nhận workload, hoặc dùng callback/response manager bảo đảm **mọi response được nhận đều có một owner closing body**. Không chỉ “gắn callback là chắc chắn không leak”.

### 8.2. `HttpClient.send` bị interrupt và resource release

Với synchronous `send`, nếu thread bị interrupt, default implementation cố hủy exchange rồi ném `InterruptedException`. Java 17 Javadoc cảnh báo HTTP exchange có thể đã được gửi; release có thể là async. Ở tầng application:

~~~java
try {
    // send + consume trong try-with-resources như ở trên
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // propagate/abort theo policy, không nuốt interrupt.
}
~~~

Đây là **minh họa** với nội dung `try` do caller điền. Một cancel/interrupt không đảm bảo server chưa xử lý request; cần idempotency token/correlation nếu retry nghiệp vụ có side effects.

## 9. Lựa chọn BodyHandler ngay từ đầu để giảm gánh cleanup

Chọn handler phù hợp với nhu cầu thực, tránh nhận streaming body nếu không có consumer rõ:

| Nhu cầu | BodyHandler hợp lý | Ghi chú |
| --- | --- | --- |
| Chỉ cần status + headers, response body hữu hạn có thể bỏ | `BodyHandlers.discarding()` | Tiêu thụ rồi loại bỏ, không tích vào heap; **vẫn nhận bytes** |
| File tải về | `BodyHandlers.ofFile(path)` | Tải và ghi file trước khi hoàn thành response; quản lý quota/path/file chưa hoàn tất |
| Payload nhỏ với hạn mức rõ | `ofByteArray()` hoặc `ofString()` | Có rủi ro memory nếu server gửi quá nhiều |
| Stream bytes để parse/chuyển tiếp | `ofInputStream()` | Caller read EOF hoặc close |
| Dòng log/NDJSON line-oriented | `ofLines()` | Consume hết hoặc close, thêm line-size limit |
| Reactive pipeline cần demand | `ofPublisher()` | Subscribe đúng một lần; terminal hoặc cancel |
| Cần chọn handler theo status/headers | Custom `BodyHandler<ResponseType>` | Có thể chọn `BodySubscribers.discarding()` cho một số status |

### 9.1. `discarding()` không giống hủy request

~~~java
HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());
System.out.println(response.statusCode());
~~~

Đoạn này là **minh họa**. Với default handler `discarding`, response được trả khi body đã được tiêu thụ và bỏ. Nếu server stream nhiều giờ, `discarding` cũng có thể mất nhiều giờ. Do đó:
- Nếu biết trước response nhỏ nhưng không cần body: `discarding` hợp lý.
- Nếu body có thể vô hạn/cực lớn và không cần nội dung: nên có **cancel/close policy**, không cố “discard everything”.
- Nếu chỉ cần biết status và quyết định sau khi headers đến: `BodyHandler` có thể chọn subscriber theo `ResponseInfo`; chú ý việc chọn discarding vẫn tiêu thụ body.

### 9.2. `ofFile` và file chưa hoàn thành

`BodyHandlers.ofFile(path)` hoàn thành response sau khi body đã được ghi vào file; khi ứng dụng dùng `HttpResponse<Path>`, nó không còn một `InputStream` chưa đọc cần close. Nhưng file có thể chứa nội dung partial nếu quá trình tải thất bại trước lúc hoàn tất, và có thể tiêu thụ disk/quota. Với tải quan trọng:
1. Tạo đường dẫn tạm an toàn (không lấy path tùy ý từ nguồn không tin cậy).
2. Giới hạn kích thước tải, timeout, permission và disk quota.
3. Xác minh status, length/checksum/signature khi phù hợp.
4. Chỉ publish/rename file khi tải đã hoàn tất và được xác thực.
5. Xóa file tạm trên lỗi/cancel.

Đó là **lifecycle của file output**, không được giải quyết bằng `response.close()`.

## 10. Ví dụ Java 17+ hoàn chỉnh 1: đọc EOF, error body, đóng lines và close sớm

Chương trình dưới đây chạy **hoàn toàn trên loopback** bằng `com.sun.net.httpserver.HttpServer` thuộc module JDK `jdk.httpserver`. Nó tạo bốn endpoint:
- `/small`: nội dung nhỏ, client đọc tới EOF theo chunks.
- `/missing`: status 404 và error body, client vẫn consume/close.
- `/lines`: ba dòng, client chỉ cần hai dòng đầu và đóng `Stream<String>`.
- `/large`: body lớn hơn, client chỉ đọc 8 bytes và đóng sớm.

Không cần Internet, DNS hoặc server ngoài. **Ví dụ không cố khẳng định underlying HTTP TCP socket được reuse sau khi close sớm**; thông tin đó phụ thuộc implementation.

Tạo **`HttpBodyInputStreamDemo.java`**:

~~~java
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.stream.*;

public final class HttpBodyInputStreamDemo {
    private static void reply(HttpExchange exchange, int status,
                              byte[] bytes) throws IOException {
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static HttpRequest get(URI base, String path) {
        return HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(5)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);

        server.createContext("/small", e ->
                reply(e, 200,
                        "alpha\nbeta\n".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/missing", e ->
                reply(e, 404,
                        "not-found".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/lines", e ->
                reply(e, 200,
                        "one\ntwo\nthree\n".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/large", e -> {
            e.sendResponseHeaders(200, 0);
            try (OutputStream out = e.getResponseBody()) {
                byte[] block = new byte[8192];
                Arrays.fill(block, (byte) 'X');
                for (int i = 0; i < 64; i++) out.write(block);
            } catch (IOException expectedWhenClientStopsEarly) {
                // Đóng client sớm có thể hủy write phía server.
            }
        });

        server.start();
        try {
            URI base = new URI("http", null,
                    loopback.getHostAddress(),
                    server.getAddress().getPort(),
                    "/", null, null);

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5)).build();

            HttpResponse<InputStream> full = client.send(
                    get(base, "/small"),
                    HttpResponse.BodyHandlers.ofInputStream());

            ByteArrayOutputStream collected =
                    new ByteArrayOutputStream();
            long count = 0;
            try (InputStream body = full.body()) {
                byte[] buf = new byte[4];
                int n;
                while ((n = body.read(buf)) != -1) {
                    count += n;
                    collected.write(buf, 0, n);
                }
            }
            System.out.println(
                    "full status: " + full.statusCode());
            System.out.println("full bytes: " + count);
            System.out.println("full text: " +
                    collected.toString(StandardCharsets.UTF_8)
                            .replace("\n", "|"));

            HttpResponse<InputStream> error = client.send(
                    get(base, "/missing"),
                    HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = error.body()) {
                System.out.println(
                        "error status: " + error.statusCode());
                System.out.println("error text: " +
                        new String(body.readAllBytes(),
                                StandardCharsets.UTF_8));
            }

            HttpResponse<Stream<String>> lines = client.send(
                    get(base, "/lines"),
                    HttpResponse.BodyHandlers.ofLines());
            try (Stream<String> bodyLines = lines.body()) {
                System.out.println(
                        "first lines: " +
                        bodyLines.limit(2).toList());
            }

            HttpResponse<InputStream> large = client.send(
                    get(base, "/large"),
                    HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = large.body()) {
                System.out.println(
                        "early bytes: " +
                        body.readNBytes(8).length);
            }
            System.out.println("early body closed: true");
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 HttpBodyInputStreamDemo.java
java HttpBodyInputStreamDemo
~~~

Khi loopback HTTP server của JDK hoạt động, **stdout chính xác đã được kiểm tra**:

~~~text
full status: 200
full bytes: 11
full text: alpha|beta|
error status: 404
error text: not-found
first lines: [one, two]
early bytes: 8
early body closed: true
~~~

Các điểm cần giải thích:

1. `/small` trả đúng 11 byte UTF-8: `"alpha\nbeta\n"`. Mảng read buffer chỉ 4 byte, nhưng loop chạy đến EOF và `collected.write(buf,0,n)` giữ đủ dữ liệu/đúng thứ tự.
2. `ByteArrayOutputStream` chỉ dùng **trong demo với payload nhỏ đã biết**, không phải lời khuyên gom toàn bộ body không giới hạn trong production.
3. HTTP 404 không tự ném `IOException` khi transport bình thường; body vẫn chứa `"not-found"` và được đọc trong `try`.
4. `body.readAllBytes()` ở nhánh error là an toàn **trong bài test vì server tạo đúng 9 bytes**; với endpoint ngoài cần dùng limit/chunked reads.
5. `ofLines` trả về response khi body có thể chưa hoàn thành; `limit(2)` không chứng minh ba dòng đã đọc hết. `try` bảo đảm `Stream.close()`.
6. `/large` được tạo với chunked response; caller chỉ đọc 8 bytes rồi close body. Server có thể thấy IOException khi client dừng, được bắt để ví dụ không nhiễu stdout.
7. `early body closed: true` mô tả **code đã thoát khối try-with-resources**; **không** đo khả năng reuse connection và không khẳng định tất cả network buffers đã được giải phóng ngay trong một nano-giây.
8. Port bind là 0 để OS chọn port trống; host lấy từ `InetAddress.getLoopbackAddress()` (có thể là IPv4 hoặc IPv6). Không có hard-coded external endpoint.

Nếu chạy trong sandbox không cho bind loopback, ví dụ có thể ném network exception thay vì stdout trên. `jdk.httpserver` nằm trong JDK tiêu chuẩn thông dụng; một custom runtime image loại module này sẽ không chạy class. Trong ứng dụng thực, thêm giới hạn body size, request deadline, log chính xác exception, không swallow I/O errors của server nếu đó là dữ liệu nghiệp vụ quan trọng. Ở đây chỉ cố tình bỏ qua lỗi server write do client **chủ động close sớm**.

## 11. Ví dụ Java 17+ hoàn chỉnh 2: Reactive publisher, terminal và cancel

Ví dụ thứ hai minh họa **hai nhánh lifecycle của `BodyHandlers.ofPublisher()`**:
- `/all`: subscriber xin mỗi lần 1 item, tiêu thụ đủ 8.192 bytes và nhận `onComplete`.
- `/early`: subscriber xin 1 item rồi gọi `subscription.cancel()` ngay khi nhận item đầu; **không đợi `onComplete`**.

Chương trình giữ state riêng cho mỗi subscriber, dùng `CountDownLatch` để bảo đảm test có timeout. **Một `Flow.Publisher` trả từ một response chỉ subscribe một lần**; ta tạo hai HTTP responses riêng cho hai test.

Tạo file **`HttpPublisherLifecycleDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class HttpPublisherLifecycleDemo {
    private static final class Receiver
            implements Flow.Subscriber<List<ByteBuffer>> {
        private final boolean stopEarly;
        private final CountDownLatch done = new CountDownLatch(1);
        private final AtomicLong count = new AtomicLong();
        private volatile Flow.Subscription subscription;
        private volatile boolean complete;
        private volatile boolean cancelRequested;
        private volatile Throwable error;

        Receiver(boolean stopEarly) {
            this.stopEarly = stopEarly;
        }

        @Override public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }

        @Override public void onNext(List<ByteBuffer> buffers) {
            for (ByteBuffer b : buffers) {
                count.addAndGet(b.remaining());
            }
            if (stopEarly) {
                cancelRequested = true;
                subscription.cancel();
                done.countDown(); // cancel không hứa onComplete
            } else {
                subscription.request(1);
            }
        }

        @Override public void onError(Throwable t) {
            error = t;
            done.countDown();
        }

        @Override public void onComplete() {
            complete = true;
            done.countDown();
        }

        void await() throws Exception {
            if (!done.await(5, TimeUnit.SECONDS)) {
                Flow.Subscription s = subscription;
                if (s != null) s.cancel();
                throw new IOException("Timed out waiting for body");
            }
            if (error != null) {
                throw new IOException("Body failed", error);
            }
        }
    }

    private static void serve(
            com.sun.net.httpserver.HttpExchange e,
            int chunks) throws IOException {
        e.sendResponseHeaders(200, chunks * 8192);
        try (OutputStream out = e.getResponseBody()) {
            byte[] block = new byte[8192];
            Arrays.fill(block, (byte) 'X');
            for (int i = 0; i < chunks; i++) {
                out.write(block);
            }
        } catch (IOException expectedIfCancelled) {
            // Client có thể ngừng đọc trước khi server gửi hết.
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress host = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(host, 0), 0);
        server.createContext("/all", e -> serve(e, 1));
        server.createContext("/early", e -> serve(e, 64));
        server.start();

        try {
            URI base = new URI("http", null,
                    host.getHostAddress(),
                    server.getAddress().getPort(),
                    "/", null, null);
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();

            Receiver full = new Receiver(false);
            HttpResponse<Flow.Publisher<List<ByteBuffer>>>
                    completeResponse =
                    client.send(
                        HttpRequest.newBuilder(base.resolve("/all"))
                                .GET().build(),
                        HttpResponse.BodyHandlers.ofPublisher());

            completeResponse.body().subscribe(full);
            full.await();
            System.out.println("full bytes: " + full.count.get());
            System.out.println("full completed: " + full.complete);

            Receiver early = new Receiver(true);
            HttpResponse<Flow.Publisher<List<ByteBuffer>>>
                    earlyResponse =
                    client.send(
                        HttpRequest.newBuilder(base.resolve("/early"))
                                .GET().build(),
                        HttpResponse.BodyHandlers.ofPublisher());

            earlyResponse.body().subscribe(early);
            early.await();
            System.out.println(
                    "early received bytes: " +
                    (early.count.get() > 0));
            System.out.println(
                    "early cancel requested: " +
                    early.cancelRequested);
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 HttpPublisherLifecycleDemo.java
java HttpPublisherLifecycleDemo
~~~

Khi loopback hoạt động, **stdout đã kiểm tra**:

~~~text
full bytes: 8192
full completed: true
early received bytes: true
early cancel requested: true
~~~

**Không diễn giải quá mức:**
- `full completed: true` xác nhận onComplete trong lần đọc đầy đủ; không phải proof HTTP business operation thành công — vẫn cần status/validation.
- `early cancel requested: true` xác nhận đã gọi `subscription.cancel()`; **không** hứa terminal signal hay xác nhận TCP socket đã đóng đúng thời điểm ấy.
- `early received bytes: true` chỉ bảo đảm item đầu có dữ liệu trong bài test; kích thước của một `List<ByteBuffer>` tùy implementation nên chương trình không assert con số byte chính xác của nhánh early.
- `request(1)` yêu cầu một **onNext item**, không phải một byte và cũng không tương đương HTTP/2 `WINDOW_UPDATE(+1)`.
- Trong ví dụ, `Receiver.await()` countDown ngay tại branch cancel, **chủ động không đợi `onComplete`** vì cancel không buộc publisher phát terminal signal.
- `AtomicLong` và `volatile` dùng để chia sẻ state giữa HTTP client callback thread và main test thread; `CountDownLatch` cung cấp cơ chế hoàn tất. Trong production vẫn cần bounded downstream queue và cancellation khi error/timeout.
- `server.stop(0)` đóng test server trong `finally`; không chạy request ngoài Internet.

## 12. Nên “drain để tái sử dụng” trong trường hợp nào?

Có người viết:

~~~java
try (InputStream body = response.body()) {
    body.transferTo(OutputStream.nullOutputStream());
}
~~~

Đây là **đoạn minh họa**: nó đọc đến EOF và bỏ dữ liệu. Mục đích thường là giúp connection có thể được tái sử dụng. Nhưng nó **vẫn tải toàn bộ response**. Với body 1 GiB hoặc server stream liên tục, đoạn này có thể tiêu tốn hàng phút/giờ, băng thông, pin/CPU và có thể không bao giờ EOF.

Quy tắc quyết định thực tế:

- Nếu body **đã gần hết**, có kích thước nhỏ biết trước và có deadline, drain có thể hợp lý.
- Nếu body **lớn, không xác định hoặc đang bị chậm/treo**, **close/cancel** thường an toàn hơn để bảo vệ tài nguyên, dù mất cơ hội tái sử dụng connection.
- Không dựa hoàn toàn vào `Content-Length` để quyết định: server có thể thiếu header, dùng compression hoặc báo length không đáng tin. Luôn có **bytes actually received** và **max remaining drain time** trong policy.
- Nếu response thực sự không cần ngay từ đầu nhưng server gửi hữu hạn nhỏ, chọn `BodyHandlers.discarding()` để thư viện tự tiêu thụ/loại bỏ; đừng tạo stream rồi quên nó.

`InputStream.transferTo(...)` thuộc Java 9+, `OutputStream.nullOutputStream()` Java 11+, nên cú pháp hợp lệ với Java 17. Nhưng “đúng cú pháp” không làm nó phù hợp với mọi workload.

## 13. HTTP/1.1 và HTTP/2: resource reuse khác nhưng cleanup giống

Một request-response exchange có body chưa xong có thể giữ những tài nguyên:
- parser state, chunked framing hoặc HTTP/2 stream state;
- TCP/TLS connection và buffer;
- flow-control demand, publisher/subscriber hoặc InputStream queue;
- worker/selector tasks;
- pooled connection slot hoặc HTTP/2 stream capacity.

**Với HTTP/1.1**, response body nằm trong TCP byte stream. Nếu app ngừng đọc sớm, connection có thể không được reuse vì phải biết chính xác ranh giới response trước khi dùng lại. **Với HTTP/2**, DATA của nhiều streams có stream IDs riêng, có thể hủy một stream bằng reset; connection có thể phục vụ các stream khác. Cả hai đều có tình huống implementation chọn đóng connection vì lỗi/cancel, và Java 17 Javadoc **không cam kết** mọi lần close/cancel chỉ ảnh hưởng một stream.

Sự khác nhau về protocol **không làm thay đổi ownership rule**: `InputStream` phải read EOF hoặc close, `Stream<String>` phải exhaust hoặc close, publisher phải terminal hoặc cancel. Không giữ body chưa hoàn tất chỉ vì “HTTP/2 có multiplex nên chắc sẽ không ảnh hưởng người khác”.

### 13.1. Đóng body không đồng nghĩa với `HttpClient.close()`

Trong Java 17, `HttpClient` là object cấu hình và chia sẻ resources qua nhiều requests; API của phiên bản này không cung cấp một phương thức `close()` chuẩn để thay thế cleanup từng response. Không suy từ tài liệu JDK mới hơn rồi gọi sai method khi dùng `javac --release 17`.

Sau này nếu dùng phiên bản JDK có lifecycle APIs khác, vẫn cần đọc contract đúng phiên bản; resource của individual body cần được xử lý theo body handler. Đừng đặt quy tắc “đợi GC dọn” trong bất kỳ phiên bản nào.

## 14. Sự khác biệt với `HttpURLConnection` cũ

Ở các dự án còn dùng `java.net.HttpURLConnection`, response body thường được đọc từ `getInputStream()` (thành công) hoặc `getErrorStream()` (có thể có với HTTP error). Đây là API khác với `java.net.http.HttpClient`.

Mẫu **minh họa**, không chạy độc lập:

~~~java
HttpURLConnection con = (HttpURLConnection) url.openConnection();
con.setConnectTimeout(5000);
con.setReadTimeout(5000);

try {
    int status = con.getResponseCode();
    InputStream source =
            status >= 400 ? con.getErrorStream() : con.getInputStream();

    if (source != null) {
        try (InputStream body = source) {
            consumeWithLimit(body);
        }
    }
} finally {
    con.disconnect();
}
~~~

Ở đây `url` và `consumeWithLimit` là thành phần caller cung cấp. `getErrorStream()` **có thể trả `null`** dù status là lỗi. Javadoc `HttpURLConnection` nói một instance thường dùng một request, nhưng underlying persistent HTTP connection có thể được chia sẻ ngầm giữa instances. Gọi `InputStream.close()` có thể giải phóng resources thuộc instance; `disconnect()` có thể đóng underlying socket khi idle và không đảm bảo phá mọi shared persistent connection.

Không dùng `con.disconnect()` để giải thích `HttpClient` mới — hai API khác nhau. Phần chính của bài này sử dụng `java.net.http.HttpClient` vì các body handlers phân biệt rõ stream/subscriber ownership.

## 15. Backpressure, timeouts và giới hạn tài nguyên

Một phản hồi streaming không phải chỉ có “đọc hay không đọc”. Với nhiều concurrent requests, cần giới hạn:

- **Maximum response size**: bytes thực tế và bytes sau giải mã/nén khi phù hợp.
- **Per-chunk size**: vùng đệm tạm được cấp trong vòng lặp.
- **Per-request deadline**: thời gian cho headers và tổng thời gian xử lý body, có chính sách stop/close khi quá hạn.
- **Idle read deadline**: nếu peer không gửi byte tiếp trong thời gian cho phép, dừng request thay vì block vô hạn.
- **Concurrent responses/streams**: semaphore/bounded task queue, không tạo vô hạn `sendAsync`.
- **Downstream capacity**: nếu parser/file/DB quá chậm, phải pause demand hoặc đóng body; không enqueue vô hạn.
- **Disk quota**: với `ofFile` và download streams, tránh ghi tới hết ổ đĩa.

Một `HttpRequest.Builder.timeout(...)` có ý nghĩa theo contract của `HttpClient`/request, nhưng **không nên xem nó là một deadline ứng dụng bao trùm mọi hoạt động `InputStream.read` tùy ý sau khi streaming response đã được trả về**. Thêm giám sát tiến độ, deadline riêng và cách close/cancel nếu body không còn đủ giá trị để tiếp tục.

### 15.1. Không block lạm dụng trong HTTP client executor

Javadoc `BodySubscribers.mapping(...)` cảnh báo mapper chạy trên executor của client. Nếu mapper **đọc blocking InputStream toàn bộ** ngay trong callback, có thể chiếm worker thread lâu và làm executor starvation. Tương tự, tự viết subscriber mà `onNext` chặn trên I/O hoặc DB trong thời gian dài có thể làm hỏng throughput.

Lựa chọn:
- Tiêu thụ blocking `InputStream` ở bounded dedicated executor.
- Dùng `BodyHandler.ofFile`/streaming parser nếu phù hợp.
- Với reactive pipeline, `request(1)` hoặc demand hữu hạn và bounded queues; khi hết khả năng xử lý, `cancel()`.
- Khi chuyển ownership sang worker task, xác nhận task được accepted và có guarantee cleanup ngay cả khi executor shutdown/reject.

### 15.2. Cancel không giải quyết correctness nghiệp vụ

HTTP GET thường có thể retry theo policy, nhưng POST/PUT có side effects có thể đã được server thực hiện trước khi client hủy. Nếu request hủy giữa chừng:
- Không khẳng định “server chắc chắn chưa xử lý”.
- Dùng idempotency key/transaction semantics/correlation ID nếu có retry.
- Ghi cancellation riêng với HTTP error response; status 500 có body không giống network cancel.
- Không báo “download complete” nếu body đã close/cancel trước EOF.

## 16. Các lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Đọc status rồi return, bỏ `InputStream` | Response body còn đang chờ; resource retention | `try (InputStream in = response.body()) { ... }` |
| Dùng `available()==0` làm EOF | Không chứng minh peer đã gửi hết | Đọc tới `read()==-1` hoặc close |
| Gọi `readNBytes(100)` rồi nghĩ response đã xong | Chỉ đọc tối đa 100 byte | Close nếu không cần phần dư |
| `lines.limit(2).toList()` rồi bỏ `Stream` | Short circuit, body có thể còn chưa đọc hết | `try (Stream<String> lines = r.body())` |
| `publisher` được trả về nhưng không subscribe | Chưa tiêu thụ, exchange có thể giữ resources | Subscribe đúng một lần, request to terminal hoặc cancel |
| Subscribe publisher hai lần | `ofPublisher` chỉ cho phép một subscriber | Tách response/stream nếu cần fan-out; không tái-subscribe |
| Gọi `subscription.request(0)` | Không hợp lệ; Flow quy định `onError` | Request số items dương |
| Gọi cancel rồi chờ vô hạn `onComplete` | Terminal signal sau cancel không được bảo đảm | Cleanup theo nhánh cancel riêng |
| `sendAsync` future đã completed rồi `cancel(true)` và bỏ body | Future cancellation không thay stream close | Lấy `response.body()` và close/cancel |
| Gặp HTTP 404/500, chỉ ném exception | Error response vẫn có body | Consume bounded error detail hoặc close |
| Dùng `discarding()` cho body vô hạn để “cancel” | Discarding vẫn nhận body | Cancel/close phù hợp khi không muốn tiếp tục |
| `readAllBytes()` với body untrusted | Có thể tích response khổng lồ | Chunked processing + max bytes |
| Luôn drain huge body để giữ keep-alive | Có thể tốn băng thông/treo | Drain có cap, hoặc close sớm |
| Dùng `HttpResponse.close()` | Java 17 `HttpResponse` không có method này | Đóng đúng streaming body |
| Dùng `HttpClient.close()` trong Java 17 | Không phải API chuẩn trong JDK 17 | Quản lý per-response resources |
| Coi close là chắc chắn TCP socket đóng ngay | Cancel có thể bất đồng bộ, semantics khác HTTP/1.1 và HTTP/2 | Ghi ý định close, không bịa socket state |
| Đưa body `InputStream` vào task không bao giờ chạy | Mất owner, resource retention | Bounded executor + guaranteed cleanup |
| Gắn exception logging chứa toàn bộ error body | Có thể lộ secrets/PII, làm memory tăng | Limit và sanitize logs |

## 17. Bài tập tự kiểm tra

**Câu 1.** `HttpResponse<InputStream>` trả về sau `send()` có chắc body đã EOF?  
**Đáp án:** Không. `ofInputStream` trả response sau headers; caller phải đọc body tiếp hoặc close.

**Câu 2.** Caller chỉ đọc 10 byte đầu của response 100 KiB rồi return. Điều gì còn thiếu?  
**Đáp án:** Phải đóng `InputStream` khi không cần 100 KiB còn lại; try-with-resources bảo đảm cleanup.

**Câu 3.** `body.available()==0` có chứng minh stream đã kết thúc?  
**Đáp án:** Không. Có thể tạm thời chưa có bytes sẵn mà network vẫn sẽ giao thêm.

**Câu 4.** Với `BodyHandlers.ofLines()`, gọi `limit(1).findFirst()` có phải đã consume response?  
**Đáp án:** Không nhất thiết. Đây là short-circuit; cần `Stream.close()` nếu chưa exhaust.

**Câu 5.** Reactive publisher vừa nhận được từ `BodyHandlers.ofPublisher()`, caller không `subscribe`. Có hợp lệ để bỏ qua?  
**Đáp án:** Không nếu muốn đảm bảo resources được giải phóng; phải subscribe và consume tới terminal hoặc cancel.

**Câu 6.** `Flow.Subscription.request(1)` có yêu cầu đúng 1 byte?  
**Đáp án:** Không. Nó yêu cầu thêm 1 item (một `onNext`), item là `List<ByteBuffer>` có lượng bytes không cố định.

**Câu 7.** Sau `subscription.cancel()` có nên `latch.await` chờ `onComplete` mãi mãi?  
**Đáp án:** Không. Hủy không buộc nhận terminal signal; cleanup riêng theo cancel.

**Câu 8.** Gọi `future.cancel(true)` sau khi `sendAsync(...ofInputStream())` future đã trả response, đủ cleanup chưa?  
**Đáp án:** Chưa. Phải đóng/tiêu thụ body đã được chuyển quyền sở hữu.

**Câu 9.** 404 Not Found có `HttpResponse.body()==null` mặc định không?  
**Đáp án:** Không. Với `ofInputStream`, 404 có thể chứa error body stream; status không tự khiến `HttpClient` ném HTTP exception.

**Câu 10.** `BodyHandlers.discarding()` có ngừng network download ngay sau headers không?  
**Đáp án:** Không. Nó tiêu thụ và bỏ body, vẫn có chi phí truyền.

**Câu 11.** Có nên luôn drain 1 GiB còn lại để tận dụng connection?  
**Đáp án:** Không. Cần cân nhắc băng thông/thời gian/memory/deadline; close/cancel có thể hợp lý hơn.

**Câu 12.** Đóng body HTTP/2 có bảo đảm chỉ reset đúng stream và không ảnh hưởng connection?  
**Đáp án:** Không có bảo đảm tuyệt đối từ API Java 17. Protocol/implementation có thể xử lý khác nhau; premature close có thể ảnh hưởng reuse.

**Câu 13.** Dùng `ofFile` để tải body, có còn `InputStream` của response cần close?  
**Đáp án:** Không. Response chứa `Path` sau khi body đã được ghi; nhưng cần quản lý file temp/quota và cleanup lỗi.

**Câu 14.** Khi `processBytes` ném exception trong vòng đọc, pattern nào bảo đảm cleanup?  
**Đáp án:** `try-with-resources` bao quanh `response.body()`; JVM gọi close ở mọi nhánh thoát.

**Câu 15.** Một consumer đọc chậm trong executor nhỏ và application tạo hàng nghìn responses streaming. Chỉ gọi close khi cuối task có đủ không?  
**Đáp án:** Chưa đủ. Cần bounded task/connection concurrency, backpressure, deadlines và ownership khi task bị reject/cancel.

## 18. Checklist triển khai trước khi production

1. **Biết kiểu body trước khi gọi `send`/`sendAsync`.** Response streaming có lifetime kéo dài sau headers.
2. **Gán ownership cho body ngay khi response được trả về.** Không để `HttpResponse<InputStream>` bị bỏ rơi.
3. **`InputStream`:** đọc tới `-1` hoặc close; đặt `try-with-resources` quanh toàn bộ xử lý.
4. **`Stream<String>`:** exhaust hoặc close; nhớ short-circuit terminal operations không tương đương EOF.
5. **`Flow.Publisher`:** subscribe đúng một lần; request đến `onComplete/onError` hoặc cancel; không đợi terminal sau cancel.
6. **Async:** cancel pending future khi không cần request; khi future đã hoàn thành, cleanup **body riêng**.
7. **Error status:** đọc có limit hoặc close body ở cả 2xx và non-2xx.
8. **Không đọc vô hạn chỉ để reuse.** Chọn bounded drain hoặc early close theo response size/time budget.
9. **Không tin `available()`, `Content-Length` hay status là kết thúc body**; đo bytes thực, EOF và protocol semantics.
10. **Giới hạn memory, body size, concurrency, thread/executor queue, timeouts và downstream backpressure.**
11. **Phân biệt HTTP/1.1 với HTTP/2** khi nói về reuse/reset; không dự đoán chắc chắn kết quả low-level socket.
12. **Giải phóng file/temp/parser/task** riêng, không trông chờ body close tự dọn mọi thứ khác.
13. **Theo dõi metrics:** open streaming bodies, bytes read, early closes, cancels, body duration, connection reuse, timeouts và pending futures.
14. **Kiểm thử các đường thoát:** status 200/404/500, empty body, short-circuit lines, timeout, IOException giữa chừng, subscriber cancel, executor rejection, concurrent requests.
15. **Bảo vệ log:** error body tối đa N bytes, sanitize PII/secrets, không vô tình log payload lớn.

## Tài liệu chính thức Java 17

- [Java SE 17 — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): API Notes về `ofInputStream()` (read EOF hoặc close), `ofLines(...)` (exhaust hoặc Stream.close) và `ofPublisher()` (subscribe once, terminal hoặc cancel).
- [Java SE 17 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofInputStream`, `ofLines`, `ofPublisher`, `discarding`, `ofFile` và phản hồi sau headers.
- [Java SE 17 — `HttpResponse`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): body type, status/headers và thời điểm response có sẵn.
- [Java SE 17 — `HttpClient`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`/`sendAsync`, cancellation/interrupt, HTTP/1.1 vs HTTP/2 behavior.
- [Java SE 17 — `HttpResponse.BodySubscriber`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): `Flow.Subscriber<List<ByteBuffer>>`, streaming result hoàn thành trước toàn bộ body.
- [Java SE 17 — `Flow.Subscription`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(n)` và `cancel()`, best-effort cancellation.
- [Java SE 17 — `InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read`, EOF, `available`, `readNBytes`, `close`.
- [Java SE 17 — `HttpURLConnection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): khác biệt legacy API, `getErrorStream` và `disconnect`.
- [Java SE 17 — `Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): lazy/short-circuit operations và stream resource closure.

**Nguyên tắc nhớ lâu:** **nhận headers chưa chắc đã đọc body; body streaming không có GC làm “chủ sở hữu” thay bạn**. Nếu còn cần dữ liệu, **đọc đến EOF**; nếu không cần, **close** (`InputStream`/`Stream`) hoặc **cancel** (`Flow.Subscription`). Đặt quyền sở hữu và cleanup ở mọi nhánh thành công, lỗi, timeout và hủy để không bỏ dở HTTP exchange.
