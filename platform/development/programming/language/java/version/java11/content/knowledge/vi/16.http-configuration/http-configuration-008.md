# Java 11 — HTTP/2 multiplexing và tài nguyên kết nối

**Chủ đề:** Java 11 → Cấu hình HTTP. Bài học giải thích cách **HTTP/2 multiplexing** cho nhiều request/response hoạt động đồng thời trên các **stream** của một kết nối, cách Java 11 `java.net.http.HttpClient` tận dụng kết nối, giới hạn tài nguyên và những vấn đề dễ gặp khi cấu hình client, concurrency, xử lý response body, timeout và retry. Kiến thức tuân theo các API chuẩn có trên Java 11 và các nguyên tắc HTTP/2 còn áp dụng theo RFC 9113; không sử dụng API incubator, HTTP/3 hay phương thức chỉ có trong các phiên bản JDK mới hơn.

**Sau bài học, bạn có thể:** phân biệt request, stream và TCP connection; hiểu vì sao multiplexing không đồng nghĩa vô hạn request hoặc một kết nối được bảo đảm; đọc phiên bản HTTP thực tế; tái sử dụng `HttpClient` đúng cách; giới hạn số request/body đang xử lý; tránh giữ kết nối do quên tiêu thụ/cancel body; đánh giá hiệu năng và kiểm thử H2 bằng fixture có hỗ trợ thật sự.

## 1. Ba khái niệm không được gộp: request, stream, connection

**HTTP request/response** là một lượt trao đổi ở tầng giao thức: method, URI, headers, status và body. Với HTTP/2, mỗi lượt trao đổi thường được ánh xạ lên một **stream** có ID và trạng thái riêng trong một **HTTP/2 connection**. Kết nối HTTP/2 chạy trên một transport connection, thông thường là **TCP** (qua TLS khi sử dụng HTTPS).

~~~text
Ứng dụng Java 11
  GET /catalog ───── stream 1 ─┐
  GET /prices  ───── stream 3 ─┼─ HTTP/2 connection ─ TCP/TLS ─ Server
  GET /reviews ───── stream 5 ─┘
                               ^
           HEADERS/DATA frames từ nhiều stream có thể xen kẽ
~~~

Sơ đồ minh họa một khả năng hợp lệ: ba request đồng thời qua một kết nối. Nó **không cam kết** JDK luôn chọn đúng ba ID này, không cam kết mọi request dùng cùng một TCP connection, và không cam kết server nhận ba request cùng lúc. Stream ID, framing, lịch truyền và số kết nối thực tế do protocol/implementation và hai đầu kết nối quản lý.

Trong HTTP/1.1, kết nối persistent có thể tái sử dụng cho nhiều request theo thời gian. Tuy nhiên, khả năng chạy nhiều response **đồng thời trên cùng một kết nối** bị hạn chế so với multiplexing của HTTP/2. HTTP/1.1 client thường dùng nhiều kết nối để đạt concurrency. **HTTP/1.1 không có nghĩa mỗi request mở một TCP connection mới.**

| Khái niệm | Ý nghĩa | Ai cần quản lý? |
| --- | --- | --- |
| Request | Một thao tác GET/POST/PUT... và response tương ứng. | App quyết định nghiệp vụ, body, timeout, retry/idempotency. |
| HTTP/2 stream | Kênh logic cho một lượt trao đổi bên trong H2 connection. | HTTP stack quản lý ID, lifecycle, flow control; app quản lý việc hoàn thành/cancel body. |
| HTTP/2 connection | Kết nối có thể chứa nhiều stream, SETTINGS và trạng thái chung. | HTTP stack/server/proxy; app quản lý client lifecycle, concurrency và tài nguyên. |
| TCP connection | Kết nối transport chứa byte của HTTP/2, có congestion/retransmission riêng. | OS/network/JDK; không tương đương số lượng request. |
| TLS session | Cơ chế bảo mật HTTPS và thương lượng giao thức qua ALPN. | TLS stack và cấu hình tin cậy; khác với HTTP protocol version. |

**Kết luận đầu tiên:** Giảm số connection nhờ multiplexing có thể tiết kiệm handshake/tài nguyên, nhưng các stream vẫn tiêu tốn memory, flow-control window, CPU, file descriptor, deadline và năng lực server.

## 2. Multiplexing hoạt động nhờ frame, không phải nhiều HTTP request “trộn text”

HTTP/2 truyền dữ liệu dưới dạng **binary frames**. Một stream có thể có HEADERS frame và các DATA frame, với stream ID cho phép nhận biết frame thuộc request/response nào. Hai bên có thể **xen kẽ frame của nhiều stream** trên cùng connection mà vẫn lắp ráp riêng từng nội dung.

~~~text
Thời gian →
Connection:  [HEADERS s1][HEADERS s3][DATA s1][DATA s3][DATA s1][DATA s3]
Stream s1:   [HEADERS]          [DATA]          [DATA]
Stream s3:               [HEADERS]       [DATA]          [DATA]
~~~

- Thứ tự frame liên quan **trong từng stream** có quy tắc riêng; ứng dụng vẫn nhận response tương ứng với request của nó.
- Stream có thể hoàn thành **không theo thứ tự request được gửi**. Chờ `CompletableFuture` của từng request, không giả định request đầu sẽ trả đầu.
- Stream không phải một thread Java. Một H2 connection có thể có nhiều stream trong khi Java HTTP client dùng các thread/executor phù hợp; **không có quan hệ một-một stream ↔ thread ↔ socket**.
- Một lần `InputStream.read`/`BodySubscriber.onNext` không nhất thiết là một DATA frame hoặc TCP packet. Ranh giới byte/network không được bảo đảm trở thành ranh giới record nghiệp vụ.
- HPACK nén **HTTP header fields**, không tự nén JSON/file body. Nếu body được nén, `Content-Encoding` và codec là vấn đề riêng.

HTTP/2 **không sửa head-of-line blocking ở tầng TCP**: khi mất một segment TCP, dữ liệu của nhiều stream trên cùng connection có thể phải chờ retransmission. Đây là lý do không thể kết luận “một H2 connection luôn nhanh hơn nhiều H1.1 connections” trong mọi mạng.

## 3. Stream concurrency có giới hạn và phải tôn trọng SETTINGS

Theo RFC 9113, peer có thể quảng bá `SETTINGS_MAX_CONCURRENT_STREAMS` để giới hạn số **stream đang active** mà đầu còn lại được mở. Stream ở trạng thái `open` hoặc `half-closed` thuộc phạm vi cần tính theo giới hạn; giá trị này không phải “số request tối đa của ứng dụng từ trước đến nay”.

Nếu server giới hạn 100 stream active:

- Điều đó **không có nghĩa** client Java chỉ được tạo 100 `CompletableFuture`.
- Khi ứng dụng gửi 1.000 request, client implementation phải tuân thủ giới hạn H2, có thể chờ, lập lịch, dùng đường kết nối được phép theo policy hoặc báo lỗi khi gặp giới hạn/tình huống cụ thể.
- Không có hợp đồng Java 11 công khai rằng mọi `HttpClient` chỉ mở đúng **một** connection trên mỗi origin, cũng không có builder chuẩn để ép số TCP connections = 1 cho mọi tình huống.
- Giới hạn stream H2 **không thay thế** giới hạn concurrency nghiệp vụ, thread, RAM và connection quota của service.

**Đừng hard-code “100 stream là mặc định của HTTP/2”**. Mọi giá trị giới hạn stream phải được xác minh từ hạ tầng thực tế, và có thể khác giữa server, gateway, proxy, kết nối và thời điểm.

### 3.1. Stream error so với connection error

- `RST_STREAM` báo đóng/hủy **một stream**. Các stream khác trên connection có thể vẫn tiếp tục.
- `GOAWAY` thông báo connection đang ngừng nhận stream mới theo điều kiện được quảng bá; những stream cũ có thể hoàn tất tùy trạng thái.
- `REFUSED_STREAM` có thể biểu thị request trên stream chưa được xử lý theo protocol, nhưng **quyết định retry ở ứng dụng vẫn cần thận trọng**.
- TCP reset, TLS failure hoặc lỗi connection có thể ảnh hưởng **nhiều stream** cùng lúc.
- Một `HttpResponse` có status `429`/`503` là HTTP response thật; nó khác với lỗi stream/transport xảy ra trước khi có response.

Java 11 `HttpClient` xử lý chi tiết H2 framing ở tầng dưới. Ở ứng dụng, bạn thường thấy `IOException`, `CompletionException` khi dùng async, request timeout hoặc kết quả status. Đừng dựa vào việc exception message của từng JDK provider luôn chứa đúng chuỗi `RST_STREAM` hay `GOAWAY`; hãy giữ cause và test tình huống nghiệp vụ.

## 4. Flow control: tài nguyên chia sẻ của stream và connection

HTTP/2 dùng cơ chế **flow-control window** cho **mỗi stream** và cho **cả connection**; bên nhận quảng bá khả năng nhận thêm byte bằng `WINDOW_UPDATE`. Flow control áp dụng lên **DATA frames**, không phải mọi frame điều khiển. Điều này cho phép receiver ngăn sender phát dữ liệu vượt khả năng xử lý ở tầng HTTP/2.

~~~text
Stream A: consumer nhanh -> cửa sổ nhận có thể được mở thêm
Stream B: consumer chậm -> cửa sổ/khả năng nhận bị giới hạn
                    |
Cùng HTTP/2 connection còn chịu cửa sổ chung,
TCP congestion và năng lực xử lý của server/proxy.
~~~

**Những hệ quả thiết kế:**

1. Một consumer chậm ở stream B có thể ảnh hưởng tài nguyên dùng chung. Multiplexing **giảm** một số kiểu blocking ở tầng HTTP nhưng không biến các stream thành hoàn toàn không liên quan.
2. Không có lời hứa chỉ cần `Thread.sleep(100)` trong callback Java sẽ khiến server lập tức ngừng gửi: JDK, TLS và OS vẫn có buffer; hãy đo dưới tải và điều kiện kiểm soát.
3. `BodySubscriber` hoặc `Flow.Publisher` tùy biến phải tuân thủ **backpressure** của Java `Flow` nếu được dùng; đăng ký không giới hạn `request(Long.MAX_VALUE)` rồi đưa vào queue vô hạn có thể làm tiêu tốn RAM.
4. Flow control không giải quyết tự động **CPU-bound processing**, database chậm, file disk full hoặc hàng nghìn request futures đã được tạo.
5. Proxy/gateway có các kết nối và flow-control state riêng ở từng hop. Client thấy H2 ở phía trước không chứng minh backend phía sau dùng H2.

Một download lớn không được tiêu thụ hoặc cancel có thể giữ stream, byte buffers và connection state lâu hơn dự kiến. **Đọc hết hoặc đóng/cancel body đúng lifecycle** là phần của quản lý tài nguyên H2, không chỉ là lựa chọn API nhận nội dung.

## 5. Java 11 HttpClient: một client dùng chung cho nhiều request

JDK 11 chuẩn hóa module `java.net.http` (JEP 321). `HttpClient` được tạo bằng builder, **immutable sau khi build** và có thể gửi **nhiều request**. Nó mang cấu hình và chia sẻ tài nguyên giữa các request. Khi cần gọi thường xuyên đến cùng service, **tái sử dụng client có cấu hình phù hợp** thay vì tạo client mới sau mỗi GET.

~~~java
HttpClient client = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();
~~~

Đây là **đoạn minh họa trong một method**, cần import `java.net.http.HttpClient` và `java.time.Duration`. Java 11 mặc định ưu tiên `HTTP_2` khi không chỉ định version; dòng `version(HTTP_2)` ở đây giúp ý định rõ ràng, **không bảo đảm request luôn thực sự chạy H2**.

### 5.1. Các tùy chọn thực sự có trên Java 11

| Cấu hình | Mục đích | Điều không nên suy diễn |
| --- | --- | --- |
| `version(HTTP_2)` | Ưu tiên HTTP/2 khi kết nối cho phép. | Không ép được server/proxy hỗ trợ H2; không ấn định một connection. |
| `version(HTTP_1_1)` | Yêu cầu ưu tiên H1.1 để tương thích/thử nghiệm. | Không đồng nghĩa mỗi request mở connection mới. |
| `connectTimeout(duration)` | Giới hạn tạo **connection mới**. | Không phải toàn bộ deadline của request/body streaming; không áp dụng như timeout mở connection khi connection đã được tái sử dụng. |
| `followRedirects(policy)` | Chọn chính sách tự theo chuyển hướng. | Không bảo đảm redirect luôn an toàn hoặc cùng origin/protocol. |
| `proxy(ProxySelector)` | Chọn proxy theo cấu hình. | Proxy có thể hạn chế khả năng H2; kết quả không giống direct connect. |
| `executor(executor)` | Cấp executor phục vụ tác vụ bất đồng bộ/phụ thuộc. | Không phải công tắc đặt số concurrent HTTP/2 streams = thread count. |
| `sslContext/sslParameters` | Cấu hình TLS cần thiết theo kiến trúc. | Không nên tự can thiệp danh sách ALPN để ép H2 hoặc tắt xác minh chứng chỉ. |
| `cookieHandler/authenticator` | Chính sách cookie/xác thực chung. | Dữ liệu xác thực/chia sẻ giữa origin phải được kiểm soát theo bảo mật. |

**Một điều quan trọng về phiên bản:** API `HttpClient` trên **JDK 11 không có `close()`, `shutdown()` hay `shutdownNow()` như một hợp đồng lifecycle công khai**; đừng viết `try (HttpClient client = ...)` khi source nhắm Java 11. Một số JDK mới bổ sung phương thức/lifecycle khác, nhưng bài này phải biên dịch được cho Java 11.

Với JDK 11, ưu tiên **ít client sống lâu theo cấu hình hợp lý**, dùng phản hồi/stream đúng cách và quản lý lifecycle của **executor do ứng dụng cung cấp**. Không tự shutdown executor trong lúc request dùng chung vẫn chạy; cũng không ép người đọc dùng thuộc tính nội bộ `jdk.httpclient...` không phải public configuration contract.

### 5.2. Không lẫn HttpClient với HttpRequest.Builder

`HttpClient` sau build có thể dùng chung qua các thread theo contract HTTP client; **builder mutable** không phải object để nhiều thread cùng cấu hình. Tạo `HttpRequest` riêng cho từng request. Nếu hai endpoint cần trust store/proxy/cookie policy khác nhau, có thể dùng các client riêng theo đúng lý do isolation, không phải vì muốn có “một connection cho mỗi request”.

## 6. Preference và negotiated version: chỉ response mới chứng minh actual

~~~java
HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
    .GET()
    .build();

HttpResponse<Void> response = client.send(
    request, HttpResponse.BodyHandlers.discarding());

System.out.println("preferred=" + client.version());
System.out.println("override.present=" + request.version().isPresent());
System.out.println("actual=" + response.version());
~~~

Đây là **đoạn minh họa**, cần import `java.net.URI`, `java.net.http.*` và xử lý `IOException`/`InterruptedException`; URL public có thể yêu cầu mạng/proxy và output thực tế thay đổi.

- `client.version()` là **preference mặc định**, Java 11 thông thường là `HTTP_2`.
- `request.version()` trả `Optional<Version>`: nếu request **không đặt override** thì Optional empty và dùng preference của client khi gửi.
- `response.version()` mới phản ánh **HTTP version thực tế của response**: `HTTP_2` hoặc `HTTP_1_1` trong JDK 11.
- `response.statusCode()` là HTTP status và không chứng minh H2/H1.1.
- Nếu request lỗi DNS/TLS/timeout trước response, **không có `response.version()`** để ghi; dùng trạng thái `NO_RESPONSE`.

### 6.1. HTTPS, ALPN và fallback

Với HTTPS, HTTP/2 thường được thương lượng qua TLS **ALPN**: `h2` cho H2, `http/1.1` cho H1.1. Trong hệ thống dùng proxy, TLS termination hoặc load balancer, hop client→gateway có thể dùng H2 nhưng gateway→backend dùng H1.1.

Với `http://` cleartext không có TLS/ALPN, việc nâng cấp sang **h2c** phụ thuộc server, proxy và khả năng client. **Không** coi `version(HTTP_2)` trên URL `http://127.0.0.1` là bằng chứng đã dùng H2.

Vì thế, test demo local ở phần sau cố tình dùng HTTP/1.1 server: nó chứng minh cách **dùng chung HttpClient, giới hạn request đồng thời và đo fallback**, không tự nhận là benchmark H2. Để chứng minh multiplexing H2, cần **fixture HTTPS thực sự quảng bá `h2` qua ALPN** và có công cụ quan sát stream/connection từ server/proxy.

## 7. Quản lý concurrency ở tầng ứng dụng

H2 multiplexing không biến một API thành dịch vụ có vô hạn tài nguyên. Nếu ứng dụng làm:

~~~java
for (int i = 0; i < 100_000; i++) {
    futures.add(client.sendAsync(
        requestFor(i), HttpResponse.BodyHandlers.ofByteArray()));
}
~~~

Đây là **đoạn cố tình minh họa nguy cơ**, `futures` và `requestFor` được định nghĩa bởi ứng dụng. Việc tạo 100.000 future không có nghĩa 100.000 stream sẽ chạy đồng thời; nhưng nó vẫn tạo áp lực lên heap, hàng đợi, timer, HTTP client, server và response buffers. Nếu mỗi response là 1 MiB và dùng `ofByteArray()`, giữ nhiều phản hồi có thể làm memory tăng rất nhanh.

**Áp dụng giới hạn độc lập với protocol:**

- `maxRequestsInFlight`: số request đã gửi nhưng chưa kết thúc và chưa giải phóng tài nguyên.
- `maxBodyBytes` và `maxBytesInFlight`: byte đang đọc/đợi xử lý, đặc biệt khi dùng `ofByteArray` hay buffer trung gian.
- `maxQueuedOperations`: giới hạn số tác vụ chờ thay vì queue vô hạn.
- `requestTimeout` và end-to-end deadline bao gồm thời gian nhận body, parse, ghi sink.
- `perOriginLimit` nếu có nhiều host/service, tránh một origin chậm chiếm hết budget.
- `cancellation/cleanup` khi người dùng hủy hoặc circuit breaker từ chối.
- Phân biệt metric **logical requests**, **active H2 streams**, **TCP connections**, **pending futures** và **threads**.

Một cách dễ kiểm thử là **gửi theo từng lô nhỏ**; cách này đơn giản nhưng có khoảng trống giữa các lô và không tối ưu throughput tuyệt đối. Với production, dùng semaphore/bounded executor hoặc reactive pipeline quản lý permit, cấp permit **trước khi gửi** và nhả khi **toàn bộ body/lifecycle** đã xử lý xong.

### 7.1. Giới hạn bằng Semaphore — lưu ý vị trí nhả permit

Đoạn minh họa cho handler **tích lũy body hoàn chỉnh**:

~~~java
Semaphore slots = new Semaphore(16);

slots.acquire();
CompletableFuture<HttpResponse<byte[]>> future;
try {
    future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofByteArray());
} catch (RuntimeException ex) {
    slots.release();
    throw ex;
}
future.whenComplete((response, error) -> slots.release());
~~~

Đây là **đoạn minh họa**, cần import `java.util.concurrent.Semaphore`/`CompletableFuture` cùng HTTP API, và xử lý `InterruptedException` của `acquire()`. `ofByteArray()` hoàn thành sau khi body đã được tích lũy; permit được nhả khi future hoàn tất. Mã này vẫn có thể block thread gọi `acquire` và giữ toàn bộ bytes trong RAM cho đến khi caller giải phóng; chọn memory budget phù hợp.

**Không sao chép nguyên logic release này sang `BodyHandlers.ofInputStream()`.** Với `ofInputStream()`, HTTP future có thể hoàn thành **ngay khi body stream có sẵn**, trong khi ứng dụng vẫn đang đọc. Nhả permit khi future hoàn thành lúc đó có thể cho nhiều body đang mở hơn giới hạn mong muốn; hãy nhả **sau khi đọc/đóng InputStream**. Tương tự với `ofPublisher()`, nhả khi subscriber đạt terminal event hoặc cancel, không chỉ khi response object được tạo.

Nếu có callback xử lý chậm, tách executor và tài nguyên phù hợp; đừng làm một callback hoàn thành future block các tác vụ I/O của HTTP client vô hạn.

## 8. Vòng đời response body ảnh hưởng trực tiếp tài nguyên kết nối

### 8.1. Các BodyHandler có mức giữ tài nguyên khác nhau

| Handler Java 11 | Khi nào nên dùng | Rủi ro/vòng đời |
| --- | --- | --- |
| `BodyHandlers.discarding()` | Chỉ cần status/headers, không cần lưu body. | JDK tiêu thụ và bỏ body; vẫn phải đợi future hoàn tất khi dùng async. |
| `BodyHandlers.ofString(UTF_8)` | Text/JSON nhỏ đã giới hạn. | Giữ toàn bộ body thành String; không phù hợp file cực lớn. |
| `BodyHandlers.ofByteArray()` | Binary nhỏ, cần bytes. | Toàn bộ bytes được giữ trong RAM; concurrency × body size nguy hiểm. |
| `BodyHandlers.ofFile(path)` | Tải file về disk. | Kiểm tra path/quyền/size/partial file và cleanup khi lỗi. |
| `BodyHandlers.ofInputStream()` | Consumer xử lý theo từng chunk. | `HttpResponse` có thể đến trước khi body xong; **phải đọc/đóng stream**. |
| `BodyHandlers.ofPublisher()` | Reactive consumer kiểm soát demand. | **Chỉ subscribe một lần**; đọc tới terminal signal hoặc `cancel`. |

Ví dụ đúng khi nhận file lớn thành luồng:

~~~java
HttpResponse<InputStream> response = client.send(
    request, HttpResponse.BodyHandlers.ofInputStream());

if (response.statusCode() != 200) {
    try (InputStream ignored = response.body()) {
        // Có thể quyết định bỏ/đóng body ở nhánh lỗi.
    }
    throw new IOException("Unexpected HTTP status");
}

try (InputStream in = response.body()) {
    byte[] buf = new byte[8192];
    int n;
    long total = 0;
    while ((n = in.read(buf)) != -1) {
        if (n > MAX_BYTES - total) {
            throw new IOException("Response exceeds limit");
        }
        total += n;
        sink.write(buf, 0, n);
    }
}
~~~

Đây là **đoạn minh họa**, cần import `InputStream`, `IOException`; `sink` và `MAX_BYTES` do ứng dụng định nghĩa. Nếu status/header không đạt, **đóng stream thay vì để lửng**. Khi body lớn hoặc chưa đáng tin, dùng file tạm rồi verify trước khi publish. Nếu consumer không đọc và không đóng, request/connection có thể tiếp tục giữ tài nguyên và ảnh hưởng stream khác.

### 8.2. Flow subscriber nhận List<ByteBuffer>

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
    client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> publisher = response.body();
publisher.subscribe(subscriber);
~~~

Đây là **đoạn minh họa**, cần import `java.util.concurrent.Flow`, `java.util.List`, `java.nio.ByteBuffer`. `subscriber` phải tuân thủ `Flow.Subscriber<List<ByteBuffer>>` và sắp xếp kết thúc/cancel đúng cách.

Một `request(1)` của `Flow.Subscription` là yêu cầu **một phần tử `List<ByteBuffer>`**, không phải một byte, không phải một HTTP/2 frame. Mỗi `ByteBuffer` có `remaining()` là byte chưa được consumer đọc. Nếu downstream chậm, đừng copy mọi buffer vào hàng đợi vô hạn; xử lý từng lô và phát demand có kiểm soát.

Khi người dùng cancel download, `InputStream.close()` hoặc subscription `cancel()` có thể ngăn việc nhận tiếp và giải phóng một phần tài nguyên, nhưng **không chứng minh server đã ngừng gửi mọi byte ngay lúc đó**: đã có buffering của TLS/kernel/JDK. Không dựa vào số byte server viết được như một invariant portable cho cancellation.

### 8.3. Không bỏ qua lỗi cuối body chỉ vì đã nhận HTTP 200

Đối với `ofInputStream()`, response `statusCode()==200` có thể được trả trước khi body truyền hết; trong khi `read` tiếp tục, connection có thể bị cắt hoặc stream reset. Chỉ báo `COMPLETED` khi toàn bộ body được tiêu thụ/kiểm chứng theo hợp đồng, và chỉ rename file tạm sau khi size/hash/schema đạt. Điều này bảo vệ chống file hỏng/partial data khi lỗi H2 hoặc mạng.

## 9. Timeout, executor và kết nối được tái sử dụng

~~~java
HttpClient client = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .connectTimeout(Duration.ofSeconds(5))
    .build();

HttpRequest req = HttpRequest.newBuilder(uri)
    .timeout(Duration.ofSeconds(20))
    .GET().build();
~~~

Đây là đoạn minh họa; `uri` là URI hợp lệ đã được kiểm soát. `connectTimeout` được áp dụng **khi cần tạo kết nối mới**; nếu kết nối tái sử dụng đã tồn tại, timeout này không áp dụng cho việc tạo connection không diễn ra. `req.timeout` là timeout của request theo API; với response body trả stream sớm, cần thiết kế **end-to-end deadline** bổ sung cho việc consumer đọc/parse/ghi.

Nếu dùng `ExecutorService` tùy chỉnh qua `builder.executor(executor)`:

- Executor phục vụ tác vụ async/dependent theo contract; **không** phải một API công khai để đặt số H2 streams tối đa.
- Không dùng executor một thread cho các callback có thể chờ đợi nhau dẫn tới deadlock; tránh blocking I/O nặng trong callbacks không kiểm soát.
- Application quản lý shutdown của executor **sau khi các request và body consumers sử dụng nó đã hoàn thành**. Shut down sớm có thể làm future fail hoặc không được thực thi.
- Không tạo client + executor mới trong mỗi request: ngoài overhead kết nối, còn có nguy cơ thread leak.
- Giới hạn workload bằng chính sách tường minh (semaphore, queue bounded, deadline), không suy từ kích thước thread pool.

### 9.1. HTTP client không phải connection pooling API công khai

Java 11 `HttpClient` quản lý tài nguyên kết nối ở mức implementation. Public API không cho bạn liệt kê, đóng từng TCP socket, lấy stream ID hay thiết lập trực tiếp `SETTINGS_MAX_CONCURRENT_STREAMS`. Những con số pool/connection có thể khác theo runtime, TLS, proxy, server và cách gửi.

Khi cần mục tiêu **“ít kết nối hơn”**, hãy tái sử dụng `HttpClient`, dùng HTTPS H2 khi tương thích, nhận body/đóng đúng cách, giới hạn concurrency và **đo connection count ở network/server/observability**. Đừng dùng API private, Reflection hoặc JDK-internal knobs chưa được cam kết để xây hợp đồng sản phẩm.

## 10. Demo Java 11 chạy offline: concurrency có giới hạn, xác minh fallback

Chương trình này dùng server HTTP/1.1 **cục bộ** tại loopback, một `HttpClient` ưu tiên HTTP/2 và gửi 6 GET theo ba lô, **tối đa 2 request in-flight mỗi lô**. Đầu ra được đọc theo đúng thứ tự index sau khi cả lô hoàn thành, không phụ thuộc request nào trên mạng trả trước.

**Mục tiêu có thể kiểm chứng:** một client tái sử dụng cho nhiều request; cách giới hạn số `sendAsync` đang hoạt động; `response.version()` thực tế là HTTP/1.1 khi server chỉ hỗ trợ H1.1; concurrency không đòi một thread Java cho mỗi logical stream.

**Không dùng demo này để tuyên bố đã test HTTP/2 multiplexing:** `com.sun.net.httpserver.HttpServer` trong JDK 11 là server HTTP/1.1. Phần kiểm H2 thật nằm sau demo.

Lưu file **`BoundedHttpClientDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class BoundedHttpClientDemo {
    private BoundedHttpClientDemo() {
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        ExecutorService serverWorkers =
            Executors.newFixedThreadPool(3);

        server.setExecutor(serverWorkers);
        server.createContext("/item/", exchange -> {
            try {
                String path = exchange.getRequestURI().getPath();
                String id = path.substring("/item/".length());
                byte[] body = ("ok-" + id).getBytes(
                    StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

            String base = "http://127.0.0.1:" +
                server.getAddress().getPort() + "/item/";
            System.out.println("client.preferred=" + client.version());
            System.out.println("batch.max.inflight=2");

            for (int begin = 0; begin < 6; begin += 2) {
                List<CompletableFuture<HttpResponse<String>>> batch =
                    new ArrayList<>();

                for (int i = begin; i < begin + 2; i++) {
                    HttpRequest request = HttpRequest.newBuilder(
                            URI.create(base + i))
                        .timeout(Duration.ofSeconds(5))
                        .GET()
                        .build();

                    batch.add(client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)));
                }

                CompletableFuture.allOf(
                    batch.toArray(new CompletableFuture[0])).join();

                for (int index = 0; index < batch.size(); index++) {
                    int id = begin + index;
                    HttpResponse<String> r = batch.get(index).join();
                    if (r.statusCode() != 200
                            || r.version() != HttpClient.Version.HTTP_1_1
                            || !("ok-" + id).equals(r.body())) {
                        throw new AssertionError("Unexpected response");
                    }

                    System.out.println(
                        id + " " + r.version() + " " +
                        r.statusCode() + " " + r.body());
                }
            }
        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy với JDK 11, file source lưu UTF-8. Module `jdk.httpserver` được dùng **chỉ cho test fixture**:

~~~bash
javac -encoding UTF-8 --add-modules jdk.httpserver BoundedHttpClientDemo.java
java --add-modules jdk.httpserver BoundedHttpClientDemo
~~~

**Stdout dự kiến chính xác nếu loopback hoạt động và các assertion đều đạt:**

~~~text
client.preferred=HTTP_2
batch.max.inflight=2
0 HTTP_1_1 200 ok-0
1 HTTP_1_1 200 ok-1
2 HTTP_1_1 200 ok-2
3 HTTP_1_1 200 ok-3
4 HTTP_1_1 200 ok-4
5 HTTP_1_1 200 ok-5
~~~

**Từng bước:**

1. `HttpServer` mở cổng động trên `127.0.0.1`. Mỗi path `/item/i` trả nội dung `ok-i`. Không dùng Internet/cert; test yêu cầu quyền socket loopback.
2. Server có executor 3 thread để xử lý request, nhưng **không có phép suy luận một thread = một H2 stream**. Ở đây server chỉ HTTP/1.1.
3. Client xây **một lần**, đặt preferred version `HTTP_2`, rồi dùng cho 6 GET.
4. Mỗi lô thêm đúng **hai** future `sendAsync` trước khi chờ `allOf(...)`. Lô sau chỉ bắt đầu khi lô trước hoàn tất; do vậy tối đa hai request đã gửi và chưa hoàn tất tại mỗi thời điểm trong demo.
5. `ofString` tích lũy body nhỏ trước khi future hoàn tất; vì vậy lô hoàn thành cũng đồng nghĩa body của hai response đã được đọc.
6. Vòng in chạy theo index chứ không theo thứ tự future hoàn tất, nên stdout **cố định** ngay cả khi hai request chạy đồng thời.
7. Kết quả `HTTP_1_1` không mâu thuẫn `client.preferred=HTTP_2`; endpoint local không hỗ trợ H2. Kiểm tra `response.version()` mới cho biết actual.
8. `server.stop(0)` và `shutdownNow()` dọn **server fixture executor**; không hề gọi `HttpClient.close()` (không có trong API JDK 11).
9. Đây là **batching**, không phải một connection pool policy sản phẩm. Trong production, semaphore/queue bounded giữ pipeline luôn có tác vụ sẵn mà không cần đợi từng cặp cố định.
10. Nếu bind loopback bị từ chối, timeout hoặc runtime gặp I/O error, chương trình có thể ném exception trước khi in đủ stdout; không xem đây là một kết quả HTTP/2 khác.

## 11. Đo HTTP/2 thật: dùng HTTPS server có hỗ trợ ALPN h2

Để kiểm chứng một môi trường H2, cần endpoint HTTPS **có hỗ trợ `h2` qua ALPN**, không phải demo HTTP/1.1 ở trên. Tạo một probe với CLI nhập URL đích được vận hành cho phép. Không gán stdout actual version cố định: CDN, TLS termination, proxy, origin và thời điểm có thể đổi kết quả.

Lưu file **`H2VersionProbe.java`**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class H2VersionProbe {
    private H2VersionProbe() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                "Usage: java H2VersionProbe https://host/path");
            return;
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("HTTPS required");
        }

        HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(15))
            .GET().build();

        HttpResponse<Void> response = client.send(
            request, HttpResponse.BodyHandlers.discarding());

        System.out.println("preferred=" + client.version());
        System.out.println("actual=" + response.version());
        System.out.println("status=" + response.statusCode());
        System.out.println("uri=" + response.uri());
    }
}
~~~

Lệnh:

~~~bash
javac --release 11 H2VersionProbe.java
java H2VersionProbe https://example.com/
~~~

**Dòng đầu có thể dự đoán khi request thành công:**

~~~text
preferred=HTTP_2
~~~

Các dòng `actual`/`status`/`uri` phụ thuộc endpoint và đường mạng. Với H2 fixture được cấu hình xác minh rõ ràng, **điều kiện test mong muốn** là `response.version() == HttpClient.Version.HTTP_2`. Nếu nhận HTTP_1_1, kiểm tra ALPN, proxy, certificate, h2 enable và request override. Không cố “bật H2” bằng header `Upgrade` thủ công hoặc tắt kiểm tra chứng chỉ TLS.

**Probe không chứng minh số connection hoặc số concurrent streams**; để chứng minh multiplexing, kết hợp **nhiều GET đồng thời tới cùng H2 origin** với access log/frame trace ở chính server/gateway, xác định stream IDs và connection IDs. Không suy số connection từ số futures.

**Bảo mật:** Đây là công cụ CLI cho URL được phép truy cập. Không biến nó thành endpoint HTTP công khai nhận URL tùy ý nếu chưa có allowlist scheme/host/IP, chặn loopback/private/cloud metadata, quản lý DNS rebinding và redirect. URL ngoài không đáng tin có thể tạo SSRF.

## 12. Kiểm thử H2 multiplexing thực sự

Khi hạ tầng cần xác nhận “các request đã dùng multiplexing”, nên có **H2 test fixture** được kiểm soát:

1. HTTPS server với TLS/ALPN `h2`, chứng chỉ test hợp lệ và một điểm vào ổn định.
2. Một origin duy nhất, một `HttpClient` được tái sử dụng, nhiều `sendAsync` đồng thời.
3. Tại client, assert `response.version()==HTTP_2` cho từng response nhận được và kiểm nội dung/status.
4. Tại server/proxy, ghi **connection ID** và **stream ID** (hoặc trace H2 tương đương). Xác nhận ít nhất hai stream active **cùng lúc** trên cùng connection nếu đây là mục tiêu test cụ thể.
5. Kiểm tra SETTINGS limits của fixture và giới hạn concurrency trong ứng dụng; không ép một giá trị không được server hỗ trợ.
6. Cho một response chậm và một response nhanh: xác minh response nhanh vẫn có thể tiến triển; không assert hoàn tất trong đúng X ms dưới scheduler bất định.
7. Kiểm thử stream cancel/reset, server GOAWAY và failure connection ở các kịch bản riêng. Tách lỗi stream đơn lẻ với lỗi ảnh hưởng nhiều stream.
8. Đo CPU/heap/FD/network và timeout dưới load vừa đủ, không chỉ so sánh thời gian của một GET.

Một fixture HTTP/1.1 như `jdk.httpserver.HttpServer` **không** thể xác nhận multiplexing H2. Một CDN công khai cũng không phải fixture kiểm stream ID đáng tin cho CI: cấu hình có thể thay đổi mà bạn không kiểm soát.

### 12.1. Unit tests ổn định không cần mạng

Các tính chất builder/preference có thể kiểm trực tiếp trên Java 11:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class Http2ConfigurationTest {
    @Test
    void clientPrefersHttp2() {
        HttpClient client = HttpClient.newHttpClient();
        assertEquals(HttpClient.Version.HTTP_2, client.version());
    }

    @Test
    void requestUsesClientPreferenceUnlessOverridden() {
        HttpRequest inherited = HttpRequest.newBuilder(
            URI.create("https://example.com/")).GET().build();
        assertFalse(inherited.version().isPresent());

        HttpRequest pinned = HttpRequest.newBuilder(
            URI.create("https://example.com/"))
            .version(HttpClient.Version.HTTP_1_1)
            .GET().build();
        assertEquals(HttpClient.Version.HTTP_1_1,
            pinned.version().orElseThrow());
    }
}
~~~

Đây là **class JUnit Jupiter 5.x** dùng được khi project đã có dependency/test runner tương thích JDK 11; JUnit không nằm trong Java SE. Nó không gửi request và **không** chứng minh negotiated HTTP version hoặc multiplexing. Test negotiated version cần server thật như phần trên.

## 13. Retry khi stream/connection lỗi: có thể phát lại không đồng nghĩa an toàn

Multiplexing tạo ra những trường hợp lỗi mà nhiều request đang chạy cùng lúc:

| Tình huống | Kết quả có thể thấy | Cách xử lý |
| --- | --- | --- |
| Một stream bị RST_STREAM | Request đó thất bại; stream khác có thể vẫn hoạt động. | Ghi nguyên nhân, xem request có thể retry theo hợp đồng không. |
| Connection bị reset/GOAWAY | Một hoặc nhiều request có thể không có response hoàn chỉnh. | Kiểm trạng thái đã gửi/được xử lý; không tự đoán “mọi POST đều chưa chạy”. |
| Server giảm MAX_CONCURRENT_STREAMS | Request mới có thể chờ/được điều phối theo implementation. | Giới hạn load, đo timeout/queue, tuân thủ peer settings. |
| TLS handshake fail | Không có HTTP response. | Kiểm certificate, trust, SNI/ALPN/proxy; không tắt TLS verification. |
| Timeout giữa body | Status có thể đã nhận nhưng body incomplete. | Cancel/cleanup, không publish file partial, retry theo idempotency. |
| 429 hoặc 503 | HTTP response thật đã đến. | Kiểm `Retry-After`, backoff và business policy. |
| 200 nhưng checksum sai | HTTP exchange có thể hoàn thành nhưng dữ liệu không hợp lệ. | Từ chối publish, báo lỗi toàn vẹn. |

**Đặc biệt với POST/PUT:** Nếu client không nhận được response do connection error, server vẫn **có thể đã thực hiện side effect**. Không mặc định retry tự động hoặc gửi lại mọi request khi thấy lỗi H2. Dùng idempotency key, transaction ID, status reconciliation hoặc giao thức nghiệp vụ phù hợp. `HttpRequest.BodyPublisher` cũng cần có khả năng **tái phát dữ liệu** nếu HTTP client gửi lại theo policy; một InputStream một lần có thể không replay được.

**Không đồng nhất `REFUSED_STREAM` với mọi `IOException`**; protocol cho phép một số logic retry an toàn trong những điều kiện cụ thể, nhưng không phải exception chung nào cũng xác nhận server chưa xử lý request.

## 14. Connection reuse và cách đo thay vì đoán

Một số phương pháp đo đáng tin, khi có quyền quan sát môi trường:

- **Client-side:** `client.version()` cho preference, `request.version()` cho request override, `response.version()` cho actual. Ghi status, latency, bytes, timeout/error, số futures còn chờ.
- **Server/gateway:** access logs có connection ID, H2 stream ID, TLS ALPN, số stream active và SETTINGS; xác định chính xác hop.
- **OS/network:** TCP connection counts, socket states, bandwidth, retransmission/loss, TLS handshake counts và proxy statistics.
- **Application:** bounded queue depth, số request in-flight, body readers đang mở, executor saturation, heap/RSS/GC và disk/file handles.

**Không suy “số futures == số active streams”**, cũng không suy “`response.version() == HTTP_2` nghĩa là chỉ dùng một TCP connection”. Hệ thống có thể tạo connection mới để thay thế connection cũ, phục vụ origin khác hoặc do chính sách/tình huống mạng. Nếu gateway terminates TLS, phiên bản HTTP backend có thể hoàn toàn khác phiên bản ở client→gateway.

Lưu ý telemetry an toàn: URI có thể chứa query/token/PII; không lấy raw URL làm nhãn metrics cardinality cao, không ghi raw body hoặc Authorization header. Dùng route template/host danh mục cho phép, mã lỗi và correlation ID.

## 15. Benchmark HTTP/1.1 và HTTP/2 đúng cách

### 15.1. Những phép đo có ý nghĩa

| Metric | Vì sao quan trọng |
| --- | --- |
| p50 / p95 / p99 latency | Tail latency có thể tăng khi server/connection bị bão hòa. |
| Throughput (requests/s, bytes/s) | H2 multiplexing có thể cải thiện utilization dưới nhiều GET đồng thời. |
| Active connections và H2 streams | Kiểm lợi ích connection reuse/giới hạn server. |
| Error/timeout/cancel rate | Không đánh đổi throughput lấy thất bại tăng cao. |
| CPU/heap/GC/FD/thread count | Đánh giá chi phí tài nguyên ở client/server. |
| TLS handshakes/connection churn | Tạo HttpClient quá nhiều có thể làm mất lợi ích reuse. |
| Queue depth, backpressure và flow-control stalls | Tìm bottleneck khi consumer/server chậm. |

### 15.2. So sánh công bằng

- Dùng **cùng endpoint**, payload, schema, authentication, cache state và hạ tầng mạng.
- Kiểm actual HTTP version bằng `response.version()`, không chỉ preference.
- Warm-up kết nối/JIT và đo nhiều lần; công bố cấu hình JDK, server, proxy và môi trường.
- So nhiều mức concurrency (1, 2, 10, 50...), file nhỏ và file lớn, consumer nhanh/chậm.
- Giữ retry, redirect, keep-alive, TLS, compression và workload đồng nhất.
- Phân biệt hiệu năng mạng với thời gian xử lý API/DB; một endpoint chậm vì database không tự nhanh lên khi bật H2.
- Đặt budget load, tránh benchmark trở thành DoS đối với production. Dùng load-test environment được cấp phép.

**Kết luận đúng:** HTTP/2 thường cải thiện hiệu quả khi có nhiều exchange tới cùng origin trên connection phù hợp, nhưng vẫn chịu **TCP head-of-line blocking**, flow-control, server limits và contention. Không hứa H2 luôn nhanh hơn H1.1; hãy đo trong workload của chính ứng dụng.

## 16. Các lỗi thường gặp và cách sửa

| Hiểu sai / code sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| `client.version()==HTTP_2` → kết luận đang multiplex | Chỉ biết preference; có thể fallback H1.1. | Đọc `response.version()` và dùng server-side H2 trace. |
| Tạo `HttpClient` mới cho mỗi request | Mất khả năng chia sẻ tài nguyên/kết nối, tăng overhead. | Tái sử dụng client theo policy phù hợp. |
| Gọi `HttpClient.close()` trong Java 11 | Không có API này ở target JDK 11. | Quản lý body/executor, dùng API public của phiên bản đích. |
| 10.000 `sendAsync` thì có 10.000 stream | Sai: H2 stream limit và client scheduling tồn tại. | Giới hạn concurrency app, đo stream/queue thực tế. |
| Cho rằng H2 luôn một connection | Connection có thể thay mới/thêm theo tình huống. | Quan sát connection IDs và hạ tầng. |
| Hiểu flow control nghĩa là không cần byte budget | Buffer ứng dụng/OS vẫn dùng RAM. | Hạn chế bytes, queue và consumer concurrency. |
| Dùng `ofByteArray` cho nhiều file lớn đồng thời | Tích lũy nhiều body vào heap. | Dùng stream/file và giới hạn bytes/concurrency. |
| Nhả semaphore permit khi `ofInputStream` future hoàn tất | Body có thể vẫn đang mở và chiếm stream. | Nhả sau khi consume/close body. |
| Không đọc/đóng InputStream | Có thể giữ connection/stream tài nguyên. | `try-with-resources`, hoặc cancel khi dừng. |
| Dùng `Thread.sleep` làm chứng cứ H2 backpressure | Buffers và scheduler làm kết quả khó kết luận. | Đo producer/window/queue với fixture kiểm soát. |
| Gọi `request(1)` và tưởng nhận một byte | Flow element là List<ByteBuffer>. | Đọc `remaining()` của mỗi ByteBuffer, quản lý demand. |
| Ghi `Content-Length` bằng kích thước array trống | Không phản ánh byte thực nhận và protocol framing. | Đếm `n` của mỗi `read`, kiểm file size/hash. |
| Dựa vào một `sendAsync` thành công để chứng minh H2 | Không có concurrency hoặc stream overlap. | Gửi nhiều request đồng thời trên H2 fixture và quan sát ID. |
| Tự ép ALPN bằng HTTP header | Sai tầng; H2 qua HTTPS dùng TLS ALPN. | Dùng HttpClient/TLS stack và server h2 đúng chuẩn. |
| Tắt TLS verification để thử multiplex | Nguy cơ MITM, che lỗi cấu hình. | Sửa certificate/trust và kiểm ALPN an toàn. |
| Retry POST vì stream/connection lỗi | Có thể lặp giao dịch. | Idempotency/reconciliation và retry có điều kiện. |
| Tự chỉnh private JVM pool knobs làm hợp đồng | Không ổn định giữa JDK/update. | Public API + đo behavior + app-level limits. |
| Nhầm HPACK với body gzip | Body không tự được nén. | Cấu hình/giải nén Content-Encoding riêng. |

## 17. Bài tập thực hành

**Bài 1 — mô hình:** Vẽ 6 GET đồng thời tới cùng HTTPS origin. Giải thích sự khác nhau giữa 6 requests, 6 HTTP/2 streams và số TCP connections thực tế. Tại sao không được kết luận “6 requests = 6 sockets”?

**Bài 2 — đo fallback:** Chạy `BoundedHttpClientDemo.java`. Giải thích tại sao `client.preferred=HTTP_2` nhưng sáu dòng actual là `HTTP_1_1`. Chỉ ra vì sao demo không chứng minh H2 multiplexing.

**Bài 3 — giới hạn concurrency:** Đổi batch size từ 2 thành 3, kiểm logic lô cuối. Viết Semaphore-based design để giữ tối đa 3 request in-flight liên tục; bảo đảm permit được nhả khi body đã tiêu thụ xong.

**Bài 4 — stream limit:** Giả sử fixture H2 có `SETTINGS_MAX_CONCURRENT_STREAMS=10`. Ứng dụng tạo 100 futures đồng thời. Nêu ít nhất ba tài nguyên có thể vẫn bị chiếm và cách kiểm trường hợp queue/timeout mà không giả định server tự tạo thêm connection.

**Bài 5 — Flow:** Tạo consumer dùng `BodyHandlers.ofPublisher()` và `Flow.Subscription.request(1)` sau khi xử lý batch. Giải thích tại sao một `List<ByteBuffer>` có thể chứa nhiều byte, và tại sao không được giữ dữ liệu không giới hạn trong queue.

**Bài 6 — body lifecycle:** Với `ofInputStream()`, vì sao future có thể hoàn thành trước khi file tải xong? Viết `try-with-resources`, thêm byte budget và dọn file tạm khi stream lỗi.

**Bài 7 — HTTP/2 test:** Dùng H2 test fixture có TLS/ALPN, ghi connection ID và stream ID. Làm sao chứng minh hai stream overlap trên cùng connection mà không cần giả định một lần `read` là một frame?

**Bài 8 — sự cố:** Server gửi GOAWAY khi nhiều request đang chạy. Liệt kê thông tin cần log để biết request nào hoàn thành, request nào chưa có response và khi nào được retry; vì sao POST phải được xử lý cẩn thận?

**Bài 9 — hiệu năng:** So sánh H1.1/H2 ở concurrency=1 và concurrency=30 với response 1 KiB và 1 MiB. Chọn ít nhất bốn metric cần thu; giải thích vì sao network loss có thể làm H2 không tốt hơn H1.1.

**Bài 10 — proxy:** Vẽ Java client → API gateway → backend; hop đầu H2, hop sau H1.1. Nêu chính xác `response.version()` quan sát gì và cần log ở hop nào để khẳng định backend đang dùng H1.1.

**Bài 11 — executor:** Dùng executor tùy chỉnh cho client rồi shutdown khi còn request. Những rủi ro gì? Đề xuất lifecycle phù hợp cho executor và shared client trên Java 11.

**Bài 12 — kiểm thử lỗi:** Giả lập server reset một stream chứ không reset connection. Phân biệt cách quan sát lỗi đó với trường hợp toàn bộ TCP/TLS connection bị đứt và ảnh hưởng nhiều stream.

## 18. Checklist trước khi dùng HTTP/2 trong production

1. **Hợp đồng protocol:** service/proxy có hỗ trợ H2 qua HTTPS ALPN không? Actual version được xác minh bằng `response.version()` chưa?
2. **Tái sử dụng:** Có tái sử dụng `HttpClient` cho cùng policy proxy/TLS/auth/cookie, tránh tạo per-request không?
3. **Concurrency:** Có max in-flight/queue/budget cho từng origin và toàn ứng dụng không?
4. **Body:** Mọi response streaming được đọc hết hoặc đóng/cancel? Body lớn có được stream thay vì gom RAM?
5. **Flow control:** Có hiểu H2 connection window, stream window, server concurrent stream limit và việc buffer nội bộ vẫn tồn tại không?
6. **Executor:** Nếu tự cấp executor, ai sở hữu và đóng nó; callback có block lâu hoặc tạo deadlock không?
7. **Timeout:** Connect timeout, request timeout và deadline toàn bộ pipeline đã được phân biệt chưa?
8. **Retry:** Có phân loại status HTTP, stream error, connection error, timeout và idempotency của request không?
9. **Proxy:** Đã xác định rõ protocol ở mỗi hop, không suy từ H2 front-end sang H2 backend chưa?
10. **Kiểm thử:** Test HTTP/1.1 local, H2/ALPN fixture và trường hợp cancel/reset được đặt ở đúng mức chưa?
11. **Quan sát:** Có actual protocol, connection/stream counts ở server, p95/p99, queue depth và memory/FD mà không lộ dữ liệu nhạy cảm không?
12. **Phiên bản Java:** Có bảo đảm source nhắm Java 11, không gọi `HttpClient.close()` hay API HTTP/3 chỉ có ở runtime khác không?

## 19. Tài liệu chính thức và kết luận

- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client dùng chung, immutable sau build, `send`/`sendAsync`, `version`.
- [Java SE 11 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `version`, proxy, connect timeout, executor, redirect và cấu hình TLS.
- [Java SE 11 — HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `response.version()` là phiên bản thực tế; lifecycle response body.
- [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString`, `ofInputStream`, `ofPublisher`, `ofFile`.
- [Java SE 11 — Flow](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.html): backpressure và `Flow.Subscription`.
- [JEP 321 — HTTP Client API](https://openjdk.org/jeps/321): Java 11 chuẩn hóa HTTP Client.
- [RFC 9113 — HTTP/2 (2022)](https://www.rfc-editor.org/rfc/rfc9113.html): bản RFC hiện hành cho HTTP/2, multiplexing, streams, SETTINGS, flow control, GOAWAY và connection management; thay thế RFC 7540.

**Ghi nhớ:** HTTP/2 **cho phép nhiều stream trên một kết nối**, chứ không hứa số connection cố định hoặc tài nguyên vô hạn. Trong Java 11, tái sử dụng một `HttpClient` theo policy, xác minh `response.version()`, giữ **concurrency/body budget**, tiêu thụ hoặc đóng stream đúng cách và kiểm thử bằng H2 fixture thật. **Multiplexing là khả năng của protocol; giới hạn tài nguyên và tính đúng của request vẫn là trách nhiệm của ứng dụng.**