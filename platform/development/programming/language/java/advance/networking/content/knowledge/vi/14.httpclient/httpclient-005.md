# connectTimeout của HttpClient và timeout của từng HttpRequest trong Java 17

Trong mô-đun **HttpClient** của Java Advance — networking, hai cấu hình dễ bị nhầm nhất là **HttpClient.Builder.connectTimeout(Duration)** và **HttpRequest.Builder.timeout(Duration)**. Cả hai đều dùng một Duration dương, nhưng **kiểm soát hai phạm vi khác nhau**:

- **connectTimeout của client** đặt thời gian cho **việc thiết lập kết nối mới cần thiết để gửi request**. Nếu client **tái sử dụng một kết nối đang có**, giới hạn này **không có tác dụng** đối với request ấy.
- **timeout của từng HttpRequest** giới hạn thời gian chờ **response của request đó**. Khi quá hạn theo hợp đồng API, send ném **HttpTimeoutException**, còn sendAsync hoàn tất bất thường với exception tương ứng.

**Điểm quan trọng nhất:** một server có thể nhận connection rất nhanh nhưng xử lý nghiệp vụ nhiều giây. Khi đó connectTimeout dù đặt 100 ms hay 10 giây **không thay thế request timeout**. Ngược lại, việc request timeout quá ngắn có thể kết thúc một request trong khi connection đang được thiết lập hoặc trước khi server kịp phản hồi. Để kiểm soát **toàn bộ nghiệp vụ nhiều request/retry**, ứng dụng còn cần **overall deadline** và chính sách retry, cancellation, idempotency, observability.

Bài này dùng API Java 17 **java.net.http.HttpClient** và **HttpRequest** (từ Java 11), phân tích hành vi Java API, ví dụ chạy trên loopback không phụ thuộc Internet, phân biệt các exception, các lỗi vận hành và cách thiết kế timeout phù hợp production.

## 1. Tách các giai đoạn của một lời gọi HTTP

Khi gọi **HttpClient.send(request, bodyHandler)** hoặc **sendAsync(request, bodyHandler)**, phía client có thể phải đi qua nhiều giai đoạn:

~~~text
Application tạo HttpRequest
        |
        v
HttpClient tìm connection phù hợp trong pool
        |
        +-- Có connection có thể tái sử dụng --> dùng connection đó
        |
        +-- Cần connection mới ----------------> DNS / proxy / TCP / TLS*
                                                |
                                                | connectTimeout ở phạm vi
                                                | thiết lập connection mới
                                                v
                                      connection sử dụng được
        |
        v
Gửi request headers/body
        |
        v
Server nhận, xếp hàng, xử lý nghiệp vụ
        |
        v
Nhận HTTP response headers
        |
        v
BodyHandler / BodySubscriber xử lý response body
        |
        v
HttpResponse và kết quả send / sendAsync
~~~

Dấu sao ở **DNS / proxy / TCP / TLS** lưu ý rằng **những bước cụ thể được tính vào connection establishment không được mô tả chi tiết giống nhau trong mọi phiên bản/provider**. Javadoc Java 17 chỉ cam kết ý nghĩa “underlying connection needs to be established”; không coi connectTimeout là deadline chính xác riêng cho mọi bước DNS, TLS hay proxy. Việc đo thực tế cần theo JDK, môi trường mạng và phương thức truy cập.

**Request timeout có phạm vi lớn hơn chuyện mở kết nối:** nó nhằm giới hạn thời gian chờ response theo hợp đồng HttpRequest. Nhưng **không được mặc định đồng nhất với timeout cho toàn bộ việc người gọi tự xử lý mọi byte stream**, đặc biệt khi sử dụng BodyHandler trả về InputStream hay cơ chế streaming: thời điểm HttpResponse có sẵn và body được đọc hết phụ thuộc loại BodyHandler.

### Tình huống so sánh nhanh

| Tình huống | connectTimeout của HttpClient | HttpRequest.timeout |
|---|---|---|
| TCP connect tới remote không thể hoàn tất trong giới hạn | Có thể gây **HttpConnectTimeoutException** | Có thể cũng hết hạn; lỗi cuối phụ thuộc giai đoạn và thời hạn |
| Kết nối đã được thiết lập, server xử lý chậm | **Không giới hạn** thời gian xử lý server | Giới hạn việc chờ response của request |
| HTTP keep-alive reuse kết nối trước đó | **Không tác dụng** với request không cần connection mới | Vẫn áp dụng cho từng request có đặt |
| HTTP/2 gửi nhiều request trên một connection | Không tính lại một thời hạn connect cho mọi HTTP/2 stream | Mỗi HttpRequest có timeout riêng |
| Response trả về nhanh | Không chứng minh connectTimeout đã được dùng | Không có lỗi nếu response đến đúng hạn |
| Request không đặt timeout | Không tự áp timeout request | Không có giới hạn request do Builder này đặt |
| Client không đặt connectTimeout | Không có connect timeout tường minh từ builder | Request vẫn có thể có timeout |
| HTTP status 408 hoặc 504 | Đây là response từ server/gateway, không phải Java connectTimeout | Không tự trở thành HttpTimeoutException chỉ vì status là 408/504 |

**HTTP 408/504 là mã trạng thái trong một HttpResponse**, còn **HttpTimeoutException** là ngoại lệ từ client-side timeout policy. Một client nhận 504 vẫn có thể có HttpResponse bình thường với statusCode() == 504; không được coi mọi 504 đều do client.connectTimeout gây ra.

## 2. HttpClient.Builder.connectTimeout(Duration)

Javadoc Java SE 17 định nghĩa rõ **connectTimeout**: nếu cần thiết lập kết nối **mới** và việc thiết lập không hoàn thành trong khoảng thời gian đã cho, **HttpClient.send** ném **HttpConnectTimeoutException**; **sendAsync** hoàn tất bất thường với **HttpConnectTimeoutException**. Nếu không cần tạo kết nối mới, ví dụ tái sử dụng kết nối cũ, timeout này **không có hiệu lực** đối với request đó.

### Cấu hình trên HttpClient

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

Đây là đoạn API minh họa, giả sử đã import **java.net.http.HttpClient** và **java.time.Duration**. **HttpClient** là đối tượng được xây dựng từ builder; nên **tái sử dụng cùng HttpClient** cho nhiều requests, thay vì tạo mới mỗi lần, để tận dụng connection pooling và tránh khởi tạo tài nguyên không cần thiết.

**connectTimeout là cấu hình ở mức client**, không phải property từng HttpRequest. Nếu hai đích có chính sách connect khác nhau, có thể dùng các HttpClient được cấu hình phù hợp hoặc đưa chúng vào policy per-endpoint của tầng service; không có HttpRequest.Builder.connectTimeout(...) trong Java 17.

### Kiểm tra giá trị đã cấu hình

~~~java
Optional<Duration> configured = client.connectTimeout();
System.out.println(configured);
~~~

Đây là đoạn minh họa không độc lập, có import **java.util.Optional**. **HttpClient.connectTimeout() trả Optional<Duration>**. Nếu builder không đặt connectTimeout, **Optional.empty()** là hợp lệ. Đừng kết luận “empty nghĩa mọi network call sẽ thành công và đợi vô hạn”: OS, proxy, TLS và các tầng khác vẫn có thể báo lỗi hoặc tự kết thúc chờ vì lý do riêng.

### Giá trị không hợp lệ

**Duration.ZERO** hoặc một Duration âm không được chấp nhận ở **connectTimeout(Duration)**: Java ném **IllegalArgumentException**. Không dùng 0 để biểu thị “tắt giới hạn”; nếu muốn không đặt connect timeout ở builder, **đừng gọi** phương thức ấy. Nếu cấu hình lấy từ env/config, validate trước khi build client.

~~~java
HttpClient.newBuilder().connectTimeout(Duration.ofMillis(500));
// Hợp lệ: 500 ms.

HttpClient.newBuilder().connectTimeout(Duration.ZERO);
// IllegalArgumentException: phải là Duration dương.
~~~

Đây là hai lệnh minh họa API, không phải một chương trình hoàn chỉnh.

### Tại sao giữ HttpClient lâu dài là quan trọng?

Một HttpClient có thể tái sử dụng HTTP/1.1 keep-alive connections và HTTP/2 connections. Khi một request dùng kết nối cũ, **không có một lần TCP connect mới** để áp dụng connectTimeout. Vì vậy cấu hình “client connect timeout 1 giây” **không** bảo vệ bạn khỏi server giữ request 30 giây trên một connection đang khỏe.

Một kết nối đã reuse cũng có thể chết giữa chừng, bị idle timeout, reset hoặc đi qua load balancer; khi ấy request có thể thất bại hoặc client phải xây connection khác. **Không tự dự đoán** mọi request được reuse hay luôn mở mới — đó là quyết định runtime, protocol và trạng thái connection pool. Để kiểm soát thời gian response **trong cả hai trường hợp**, đặt **timeout trên request**.

## 3. HttpRequest.Builder.timeout(Duration)

Javadoc Java 17 mô tả **HttpRequest.Builder.timeout(Duration)** là timeout của **chính request**. Nếu response không được nhận trong khoảng thời gian đặt, **send(...)** ném **HttpTimeoutException**; **sendAsync(...)** hoàn tất bất thường với exception tương ứng.

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/orders/42"))
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();
~~~

Đây là đoạn API minh họa (không truy cập domain trong bài demo chạy). Dùng **java.net.http.HttpRequest**, **java.net.URI** và **java.time.Duration**.

**timeout này thuộc HttpRequest, không tự đổi connectTimeout của HttpClient.** Hai requests gửi bằng cùng một HttpClient có thể có timeout khác nhau:

~~~java
HttpRequest quick = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMillis(800)).GET().build();

HttpRequest report = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(15)).GET().build();
~~~

Hai dòng trên giả định **uri** là URI đã định nghĩa; là đoạn minh họa API chứ không phải file runnable. Bài toán có thể cần timeout ngắn cho tra cứu trạng thái, dài hơn cho sinh báo cáo, nhưng giá trị cụ thể **phải đo trên workload, SLO và người dùng thực tế**, không sao chép con số này làm cấu hình mặc định toàn hệ thống.

### Request timeout không đặt có nghĩa gì?

**HttpRequest.timeout()** trả **Optional<Duration>**. Nếu không gọi builder.timeout, Optional rỗng. Theo Javadoc, không đặt request timeout có hiệu ứng tương tự một Duration vô hạn cho việc chờ response, tức **không có giới hạn thời gian request ở cấp API này**. Tuy nhiên request vẫn có thể kết thúc bởi lỗi TCP, DNS, TLS, socket, server close, application cancellation, client connectTimeout nếu mở connection mới, hoặc lỗi khác.

**Duration.ZERO** và Duration âm đều gây **IllegalArgumentException**. Không có ý nghĩa “0 ms tức trả kết quả ngay” hay “0 nghĩa là không giới hạn”.

### “Response đã nhận” và việc đọc body

Đặc biệt quan trọng trong Java 17: **HttpClient.send** trả HttpResponse, nhưng tài liệu HttpClient nói **response body đã được đọc hết hay chưa phụ thuộc kiểu BodyHandler**.

- **BodyHandlers.ofString():** thường hoàn tất khi body đã được thu nhận để hình thành String. Đây là lựa chọn phù hợp cho ví dụ đơn giản về request timeout và server chậm trả response.
- **BodyHandlers.ofByteArray():** cũng thu body thành byte array và phải cân nhắc giới hạn kích thước để tránh tốn bộ nhớ.
- **BodyHandlers.ofInputStream():** có thể trả HttpResponse chứa **InputStream chưa được tiêu thụ hết**. Nếu code sau đó tự đọc stream chậm hoặc đứng chờ dữ liệu, đừng coi request timeout là một **hard end-to-end deadline đã bảo vệ toàn bộ vòng xử lý của chính bạn**.
- **BodyHandlers.ofLines(), publisher hoặc custom subscriber:** thời gian tiêu thụ body, backpressure và completion semantics phụ thuộc loại handler. Phải hiểu contract của handler và đóng/cancel tài nguyên đúng.

Đừng khẳng định một cách tuyệt đối rằng **HttpRequest.timeout(Duration)** trên Java 17 luôn bao gồm **tất cả bytes của mọi response body**. Đặc tả Java 17 đặt điều kiện **response không được nhận đúng hạn**; để bảo vệ việc streaming và downstream processing, hãy thêm deadline/budget riêng, giới hạn nội dung, cancellation và ownership phù hợp.

## 4. Hai timeout phối hợp như thế nào?

Một cách hình dung hữu ích là đặt **connectTimeout nhỏ hơn hoặc bằng một phần budget của request**, ví dụ connect 1 giây và request 4 giây. Đây chỉ là một **định hướng ngân sách**, không phải một công thức thời gian tuyệt đối:

~~~text
Request có budget chờ response 4 giây
     |
     +-- cần connection mới:
     |       connectTimeout client = 1 giây
     |       không connect kịp -> có thể HttpConnectTimeoutException
     |       connect xong      -> còn thời gian cho HTTP request/response
     |
     +-- connection reuse:
             bỏ qua connectTimeout
             request timeout vẫn kiểm soát response
~~~

Cần chú ý ba điều:

1. **Không cộng 1 + 4 thành mặc định 5 giây** một cách máy móc. Request timeout là cấu hình của request; connect là giai đoạn có thể diễn ra trong hành trình request. Thời gian thực tế và lỗi xuất hiện chịu ảnh hưởng của provider/phase.
2. Nếu request timeout ngắn hơn connectTimeout và connection không kịp mở, **không được giả định chắc chắn** sẽ luôn nhìn thấy **HttpConnectTimeoutException** hay luôn thấy **HttpTimeoutException** ở đúng một thời điểm; các chính sách cạnh tranh và lỗi mạng có thể khác nhau.
3. Trên connection reuse, client connectTimeout **không được áp dụng lại**. Bạn vẫn phải đặt giới hạn request để tránh response chậm vô hạn.

### Bảng cách dùng theo mục tiêu

| Mục tiêu của bạn | Cấu hình chính | Cần bổ sung |
|---|---|---|
| Không chờ thiết lập connection mới quá lâu | HttpClient.Builder.connectTimeout | DNS/proxy/TLS policy, request timeout |
| Không chờ một HTTP response quá lâu | HttpRequest.Builder.timeout | Cẩn trọng BodyHandler và xử lý response body |
| Chỉ chờ CompletableFuture trong thread hiện tại tối đa N giây | CompletableFuture.get(timeout) | Không coi như đã hủy HTTP operation |
| Giới hạn toàn bộ chuỗi nhiều HTTP requests | Overall deadline trong service | Chia budget còn lại cho từng request, retry/backoff |
| Giới hạn tải server | Server-side timeouts, queues, deadlines | Rate limiting, circuit breaker, backpressure |
| Giới hạn streaming response hoặc xử lý dữ liệu | Streaming deadline, giới hạn bytes, close/cancel | Không dựa riêng vào HttpRequest.timeout |

## 5. Ví dụ Java 17 chạy được: fast, slow, send và sendAsync

Để kiểm chứng **request timeout khác connect timeout**, ví dụ này khởi tạo một HTTP server nhỏ ngay trong JVM với **com.sun.net.httpserver.HttpServer** của module **jdk.httpserver**. Server bind **127.0.0.1 trên cổng động**, không phụ thuộc Internet, có hai endpoint:

- **/fast:** trả response body **FAST** ngay.
- **/slow:** chờ khoảng **1,2 giây** mới tạo response **SLOW**. Kết nối TCP tới chính server này có thể mở rất nhanh, nhưng response bị cố ý trì hoãn.

Client được cấu hình **connectTimeout = 2 giây**, còn request **/slow** được cấu hình **timeout = 150 ms**. Do server chủ động không gửi response cho /slow trong 1,2 giây, lời gọi đồng bộ và bất đồng bộ đều cho timeout theo policy request trong điều kiện lab thông thường. Demo in nhãn lỗi ổn định, không in port hay thời gian thực đo.

Tệp **HttpClientTimeoutDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HttpClientTimeoutDemo {
    private static void respond(HttpExchange exchange, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream body = exchange.getResponseBody()) {
            body.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(3);
        server.setExecutor(pool);

        server.createContext("/fast", exchange -> {
            try {
                respond(exchange, "FAST");
            } finally {
                exchange.close();
            }
        });
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(1200);
                respond(exchange, "SLOW");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            } catch (IOException ignored) {
                // Client có thể đã đóng exchange khi request timeout.
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            URI root = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest fast = HttpRequest.newBuilder(
                            root.resolve("/fast"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<String> ok = client.send(
                    fast, HttpResponse.BodyHandlers.ofString());

            HttpRequest slow = HttpRequest.newBuilder(
                            root.resolve("/slow"))
                    .timeout(Duration.ofMillis(150))
                    .GET().build();

            System.out.println("Connect timeout: "
                    + client.connectTimeout().orElseThrow().toMillis()
                    + " ms");
            System.out.println("Fast response: " + ok.body());

            try {
                client.send(slow, HttpResponse.BodyHandlers.ofString());
                System.out.println("Sync request: unexpectedly completed");
            } catch (HttpTimeoutException timeout) {
                System.out.println("Sync request: timed out");
            }

            try {
                client.sendAsync(slow,
                        HttpResponse.BodyHandlers.ofString()).join();
                System.out.println("Async request: unexpectedly completed");
            } catch (CompletionException error) {
                if (error.getCause() instanceof HttpTimeoutException) {
                    System.out.println("Async request: timed out");
                } else {
                    throw error;
                }
            }

            System.out.println("Per-request timeout: "
                    + slow.timeout().orElseThrow().toMillis() + " ms");
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpClientTimeoutDemo.java
java --add-modules jdk.httpserver HttpClientTimeoutDemo
~~~

Stdout **trong lần chạy thành công**:

~~~text
Connect timeout: 2000 ms
Fast response: FAST
Sync request: timed out
Async request: timed out
Per-request timeout: 150 ms
~~~

**Đã biên dịch với javac --release 17 và thực thi ví dụ trên JDK tương thích**, kết quả khớp năm dòng trên. Server dùng module jdk.httpserver có trong JDK đầy đủ; nếu runtime custom jlink không chứa module này, phải dùng một JDK/runtime có module phù hợp hoặc bật module khi đóng gói.

### Giải thích mỗi điểm quan trọng

**1. Server dùng loopback:** bind địa chỉ 127.0.0.1, port = 0 nên không chọn cổng cố định. URI được tạo từ **server.getAddress().getPort()** sau khi server.start(). Ví dụ không gọi dịch vụ ngoài và không phụ thuộc DNS Internet.

**2. Hai endpoint khác nhau:** /fast trả **FAST**; /slow cố ý chờ **1.200 ms** trước khi gửi response headers. Chỉ số slow không liên quan đến TCP connect timeout: server đã listen trên local port, nhưng response application đến muộn.

**3. No proxy:** **HttpClient.Builder.NO_PROXY** tránh chuyển request loopback qua proxy do máy có thể cấu hình. Nó chỉ phục vụ độ ổn định của lab; production có thể cần proxy đã được phê duyệt.

**4. Client dùng connectTimeout 2.000 ms:** timeout này chỉ có ý nghĩa khi HttpClient cần mở connection; không phải giới hạn cho server xử lý /slow. Vì các requests có thể được reuse hoặc không tùy runtime, ví dụ **không tuyên bố** đã đo đích xác connection reuse.

**5. /fast đặt timeout 5 giây:** chủ động cho request nhanh một budget dư dả để hạn chế fail giả do môi trường test chậm. **HttpResponse.BodyHandlers.ofString()** đọc body thành String, nên in **FAST** khi nhận đủ.

**6. /slow đặt timeout 150 ms:** response bị trì hoãn xa hơn 150 ms; lời gọi **send** ném một **HttpTimeoutException** (hoặc subclass nếu giai đoạn connect cũng timeout). Catch cha HttpTimeoutException là đủ cho thông báo demo.

**7. sendAsync không ném HTTP timeout trực tiếp ra thread gọi:** nó trả một **CompletableFuture**. Khi **join()** thất bại, exception được bọc trong **CompletionException**, và chương trình kiểm tra **getCause()** để phân biệt lỗi timeout đã mong đợi khỏi các lỗi khác. Không bắt mọi exception rồi in “timeout”.

**8. Finally dọn tài nguyên:** server.stop(0) dừng HTTP server; executor được **shutdownNow()**. Một handler đang sleep có thể bị interrupt; nếu client đã timeout và đóng exchange, handler có thể thấy IOException trong lúc gửi response và demo đã bắt để dọn đúng cách.

**9. Vì sao đầu ra không chứa Connection timeout exception?** Bởi endpoint loopback trong demo tiếp nhận kết nối nhanh; mục tiêu của bài thử là chứng minh **request timeout khi server trả response chậm**, chứ không mô phỏng một TCP SYN không có phản hồi.

**10. Giới hạn của output:** đây là stdout mong đợi khi server local được phép bind và scheduler không bị nghẽn bất thường. Một JVM/máy cực kỳ chậm có thể gặp lỗi bất thường; khi đó đọc exception, không coi chương trình là bằng chứng rằng mọi timeout có cùng lịch chính xác.

## 6. Ví dụ Java 17 thứ hai: giá trị mặc định, Duration không hợp lệ và quan hệ exception

Ví dụ tiếp theo **không gửi network request**; nó chỉ hỏi trạng thái cấu hình API và kiểm tra những lỗi phổ biến. Vì không phụ thuộc Internet hay timing, stdout ổn định.

Tệp **HttpTimeoutDefaultsDemo.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

public class HttpTimeoutDefaultsDemo {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.invalid/")).GET().build();

        System.out.println("Client timeout configured: "
                + client.connectTimeout().isPresent());
        System.out.println("Request timeout configured: "
                + request.timeout().isPresent());

        try {
            HttpClient.newBuilder().connectTimeout(Duration.ZERO);
        } catch (IllegalArgumentException expected) {
            System.out.println("Zero connect timeout: rejected");
        }

        try {
            HttpRequest.newBuilder(URI.create("https://example.invalid/"))
                    .timeout(Duration.ZERO);
        } catch (IllegalArgumentException expected) {
            System.out.println("Zero request timeout: rejected");
        }

        System.out.println("Connect timeout extends request timeout: "
                + (new HttpConnectTimeoutException("sample")
                   instanceof HttpTimeoutException));
    }
}
~~~

~~~bash
javac --release 17 HttpTimeoutDefaultsDemo.java
java HttpTimeoutDefaultsDemo
~~~

Stdout:

~~~text
Client timeout configured: false
Request timeout configured: false
Zero connect timeout: rejected
Zero request timeout: rejected
Connect timeout extends request timeout: true
~~~

**Đã biên dịch với javac --release 17 và chạy thành công.** URI example.invalid chỉ được dùng làm dữ liệu trong HttpRequest, **không có lời gọi send/sendAsync**, do đó chương trình không yêu cầu kết nối mạng hoặc DNS thành công.

Giải thích:

- **false** ở hai dòng đầu chỉ nghĩa builder chưa đặt timeout tương ứng. Không mặc định suy ra một giá trị bí mật như 30 giây hoặc 60 giây.
- **Duration.ZERO** bị từ chối vì cả hai setter đều yêu cầu Duration dương.
- **HttpConnectTimeoutException là subclass của HttpTimeoutException**; thứ bậc này quyết định thứ tự catch khi ứng dụng muốn phân biệt connect timeout với response timeout.
- Hai ví dụ giúp phân biệt **API contract ổn định** với **network timing không thể giả lập hoàn hảo bằng localhost**.

## 7. Thứ bậc exception: bắt đúng để không nuốt lỗi

Theo Java 17:

~~~text
Throwable
  |
  Exception
  |
  IOException
  |
  HttpTimeoutException
  |
  HttpConnectTimeoutException
~~~

**HttpConnectTimeoutException extends HttpTimeoutException**, vì vậy catch cha có thể xử lý cả connect timeout và response timeout. Nếu cần metric riêng, bắt lớp con trước:

~~~java
try {
    HttpResponse<String> result =
            client.send(request, HttpResponse.BodyHandlers.ofString());
    System.out.println(result.statusCode());
} catch (HttpConnectTimeoutException connectionTimedOut) {
    // Connection mới không được thiết lập đúng hạn.
} catch (HttpTimeoutException responseTimedOut) {
    // Request chờ response quá hạn.
} catch (IOException networkFailure) {
    // DNS/TLS/reset/EOF/lỗi mạng khác.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Tôn trọng chính sách cancellation/shutdown của ứng dụng.
}
~~~

**Đây là đoạn minh họa**, giả định client và request đã được tạo; cần import các class phù hợp. Nếu đảo thứ tự catch và bắt HttpTimeoutException trước, catch riêng HttpConnectTimeoutException phía sau sẽ là nhánh không thể tới được khi biên dịch.

### Không phải mọi IOException đều là timeout

Các lỗi có thể gặp:

- **ConnectException** khi connection bị từ chối, ví dụ không có listener ở cổng đích.
- **UnknownHostException** khi việc phân giải tên miền thất bại, phụ thuộc cách API/OS báo lỗi.
- **SSLHandshakeException** hoặc lỗi chứng chỉ khi TLS/hostname verification thất bại.
- **IOException** do reset, socket close, HTTP protocol hoặc proxy.
- **HttpTimeoutException** khi request-level timeout xảy ra.
- **HttpConnectTimeoutException** khi việc mở connection mới không hoàn tất đúng hạn.

**Không gán mọi lỗi connect là HttpConnectTimeoutException.** Kết nối bị từ chối nhanh thường ném lỗi kết nối khác, chứ không phải “đã đợi hết connectTimeout”. Ngược lại, timeout ở firewall hoặc tầng network có thể có biểu hiện khác tùy thời điểm.

### sendAsync, CompletionException và ExecutionException

Với **sendAsync**, HttpTimeoutException có thể là nguyên nhân khiến CompletableFuture hoàn tất bất thường:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

try {
    HttpResponse<String> result = future.join();
} catch (CompletionException failure) {
    Throwable cause = failure.getCause();
    // Kiểm tra cause instanceof HttpConnectTimeoutException
    // trước HttpTimeoutException nếu muốn phân loại chi tiết.
}
~~~

Đây là đoạn minh họa với các import đầy đủ ở ứng dụng gọi. Nếu dùng **future.get()** thay cho join, failure thường được bọc trong **ExecutionException**. Nếu dùng **get(timeout, unit)**, thêm khả năng **java.util.concurrent.TimeoutException của chính lời gọi get** — đó là một timeout *khác* với HttpTimeoutException của HTTP exchange.

## 8. Bốn “timeout” dễ nhầm trong mã bất đồng bộ

Một hệ thống có thể có đến bốn giới hạn nhìn rất giống nhau:

| Cấu hình hoặc thao tác | Giới hạn đối tượng nào? | Exception hoặc tín hiệu |
|---|---|---|
| **HttpClient.Builder.connectTimeout** | Mở connection mới | **HttpConnectTimeoutException** từ send hoặc exceptional completion |
| **HttpRequest.Builder.timeout** | Chờ response cho một HttpRequest | **HttpTimeoutException** từ send hoặc exceptional completion |
| **CompletableFuture.get(timeout, unit)** | Thời gian thread hiện tại đợi future | **TimeoutException** của java.util.concurrent |
| **CompletableFuture.orTimeout(timeout, unit)** | Thời gian để future được đánh dấu hoàn tất; hoàn tất bất thường nếu quá hạn | **TimeoutException** trong future chain |

**Cạm bẫy:** future.get(500, MILLISECONDS) hết hạn **không tự bảo đảm HTTP operation bên dưới đã ngừng**. Lời gọi chỉ chứng minh caller đã chờ đủ thời gian mà chưa có kết quả. Tương tự **orTimeout** có thể khiến future hoàn tất bất thường do scheduler, nhưng không được coi như cam kết HTTP request không còn tới server hoặc server chắc chắn đã dừng xử lý.

Nếu cần dừng/giải phóng, hãy thiết kế **cancellation**, giới hạn outstanding work và theo dõi đúng lifecycle; cancellation là một yêu cầu hủy, **không chứng minh mọi byte đã gửi đều bị thu hồi**. Với HttpClient của các phiên bản JDK khác nhau, hiệu ứng hủy tác vụ ở socket/HTTP exchange có thể khác; cần đối chiếu bản triển khai và kiểm thử.

### Ví dụ API minh họa

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

try {
    HttpResponse<String> response =
            future.get(600, TimeUnit.MILLISECONDS);
} catch (TimeoutException waitingTooLong) {
    future.cancel(true); // Yêu cầu hủy, KHÔNG chứng minh server chưa xử lý.
}
~~~

Đoạn minh họa chưa độc lập và còn phải xử lý InterruptedException/ExecutionException ở caller. Hãy nhớ **TimeUnit.MILLISECONDS** thuộc package **java.util.concurrent**, và **TimeoutException** trong đây thuộc **java.util.concurrent**, không phải java.net.http.HttpTimeoutException.

## 9. Connection reuse và HTTP/2 có thể làm kết quả thử nghiệm thay đổi

Một số bài viết nói: “đặt connectTimeout=1 giây, thử 10 HTTP calls, mỗi call đều có 1 giây để kết nối”. Đây là **cách hiểu sai**.

### HTTP/1.1 keep-alive

HttpClient có thể dùng connection vừa mở để gửi request kế tiếp cùng origin, tùy keep-alive và trạng thái server. Khi không có new connect, **connectTimeout không được áp dụng cho request kế tiếp**, nhưng request timeout vẫn áp dụng nếu đã cấu hình.

### HTTP/2 multiplexing

HTTP/2 có thể truyền nhiều streams trên cùng một connection. Một stream chậm do server xử lý không làm phát sinh một TCP connect độc lập chỉ vì stream đó bắt đầu. **connectTimeout không trở thành stream timeout**; timeout riêng của HttpRequest tiếp tục là ràng buộc hữu ích.

### Kết nối không phải lúc nào cũng reuse

Connection pool có thể không reuse vì idle timeout, server đóng, cấu hình proxy, yêu cầu transport, giới hạn pool, xử lý request hoặc lỗi. Một số request có thể làm connection mới dù cùng client. Vì vậy **không nên kiểm thử connectTimeout bằng cách chỉ nhìn request thứ nhất/thứ hai rồi tuyên bố kết quả cố định**. Quan sát connection events ở tầng phù hợp và đọc tài liệu provider.

### Cách đo thực tế

Ghi lại **connect attempts**, connection establishment latency, request duration, response header latency, active/idle connections nếu observability cho phép, HTTP version, proxy hop, status và exception class. Tránh suy từ một dấu hiệu duy nhất như “HTTP 200 tức connectTimeout không hoạt động”. Thử nghiệm cần biết **request nào thực sự mở connection mới**.

## 10. Overall deadline cho một nghiệp vụ nhiều HTTP requests

Giả sử một nghiệp vụ cần **tổng tối đa 5 giây**, bao gồm service discovery, hai HTTP requests và một lần retry. Nếu request A timeout 4 giây rồi retry A 4 giây, sau đó request B timeout 4 giây, toàn bộ nghiệp vụ có thể vượt rất xa 5 giây.

**Một HttpRequest.timeout chỉ bảo vệ chính request ấy**, không tự làm hạn chót cho cả chuỗi nghiệp vụ. Hãy quản lý một **deadline chung**:

~~~text
totalBudget = 5 seconds
startNanos = System.nanoTime()
deadlineNanos = startNanos + totalBudget

before each HTTP step:
    remaining = deadlineNanos - System.nanoTime()
    if remaining <= 0: stop, fail with "deadline exceeded"
    choose perRequestTimeout <= remaining
    build a request with timeout(perRequestTimeout)

after failure:
    classify error
    if retry allowed and remaining > backoff + safetyMargin:
        backoff with jitter
        retry within the same original deadline
    else:
        stop; report exact outcome/unknown outcome
~~~

Đây là thuật toán ở mức khái niệm, không phải Java độc lập. **System.nanoTime()** phù hợp đo khoảng thời gian trôi qua; không dùng **System.currentTimeMillis()** như đồng hồ monotonic vì wall-clock có thể bị điều chỉnh bởi NTP hoặc người quản trị.

### Chuyển thời gian còn lại sang Duration

Dùng Duration dương, không truyền Duration.ZERO vì Builder.timeout sẽ ném IllegalArgumentException. Nếu remaining rất nhỏ hoặc đã âm, **dừng trước khi tạo request**. Nếu kết hợp scheduler, cân nhắc thời gian dự phòng cho serialization, queueing và xử lý kết quả. Một timeout đặt trong request không bảo đảm hệ thống đáp ứng hard real-time ở đúng nanosecond.

### Khi connectTimeout lớn hơn overall deadline

Client có connectTimeout=10 giây nhưng toàn nghiệp vụ chỉ còn 500 ms. **Request timeout cần giới hạn ngắn hơn** và application deadline phải bảo vệ đường đi còn lại; không được tự tin rằng connectTimeout lớn sẽ được rút về 500 ms một cách hoàn hảo trong mọi provider. Với hệ thống nhiều loại workload, cân nhắc nhiều HttpClient được cấu hình hợp lý theo profile, nhưng tránh tạo client mới cho mọi request.

### Redirect, authentication, proxy và TLS

Một request có thể liên quan nhiều hops: proxy, TLS handshake, redirect (nếu followRedirects bật), authentication challenge hay connection mới sau redirect. Mỗi hop tạo thêm hành vi và tài nguyên; **không nên tự cộng nhiều connectTimeout rồi coi đó là tổng request deadline**, cũng không dựa vào một connectTimeout cho thời hạn end-to-end. Thiết kế với timeout của request và deadline của tác vụ nhiều bước.

**DNS và HTTPS không có nghĩa mọi thời gian nằm hoàn toàn trong một timeout cụ thể.** Chính xác giai đoạn nào được áp ràng buộc ở một provider/JDK version là chi tiết cần kiểm chứng. Riêng các lỗi **SSLHandshakeException** không thể xử lý bằng cách vô hiệu hóa kiểm tra hostname/trust để tránh timeout.

## 11. Retry khi gặp timeout: có thể server đã xử lý rồi

Một HTTP timeout **không chứng minh** server chưa nhận request hoặc chưa thực hiện side effect.

Ví dụ lệnh POST tạo đơn hàng:

~~~text
Client POST /orders (idempotency key = 7e1)
      |
      v
Server tạo order thành công
      |
      X Response 201 bị mất / tới sau deadline
      |
Client thấy HttpTimeoutException
      |
Nếu tự POST lại với ID nghiệp vụ mới:
    có thể tạo đơn hàng thứ hai!
~~~

**Chỉ retry một operation khi hiểu rõ an toàn nghiệp vụ và chính sách transport.**

- **GET** thường có semantics idempotent; retry có thể phù hợp nếu request không có side effect và tải cho phép.
- **PUT** thường được thiết kế idempotent theo phương thức HTTP, nhưng vẫn cần xem behavior thực tế của service.
- **POST** có thể tạo side effect; nếu muốn retry, sử dụng **idempotency key** do server hỗ trợ, lưu kết quả theo key và xử lý trùng một cách nhất quán.
- **HttpConnectTimeoutException** có thể xảy ra khi kết nối chưa được thiết lập đúng hạn, nhưng vẫn cần suy xét retry policy, network và proxy; không thiết kế logic nghiệp vụ dựa vào việc một exception subclass luôn chứng minh server không thấy bất kỳ byte nào trong mọi trường hợp.
- Retry nhiều lần liên tiếp không backoff có thể tăng overload. Dùng **bounded retries**, exponential backoff, jitter, rate limit, circuit breaker và overall deadline.

### Không reset toàn bộ deadline sau mỗi attempt

Giả sử còn 1 giây cho toàn giao dịch. Nếu backoff đã dùng 700 ms, attempt kế tiếp chỉ có khoảng 300 ms, không được mở một request timeout mới 5 giây rồi làm caller chờ thêm. Để làm đúng, tính remaining từ **một mốc khởi đầu duy nhất**, không khởi tạo lại deadline từ đầu sau mỗi retry.

### Dữ liệu cần log khi timeout

Log **request ID**, method/host/path đã mask phù hợp, **attempt number**, client connectTimeout, per-request timeout, deadline remaining, duration thực, HTTP version (nếu có response), exception class và root cause. Không log Authorization header, cookies, token, private data hoặc toàn bộ response body nhạy cảm. Khi có lỗi timeout, correlate với server trace để xác định server **đã nhận request / đã commit side effect / đã trả response** hay chưa.

## 12. Streaming response và các thao tác sau khi send hoàn tất

Với **BodyHandlers.ofInputStream()**, API có thể trao một **HttpResponse<InputStream>** khi body chưa được đọc hết. Nếu application đọc stream trong 30 phút, **HttpRequest.timeout không được hiểu như bảo đảm ngừng toàn bộ việc đọc stream đó sau 2 giây**. Người dùng cần:

1. **Đóng InputStream** sau khi đọc hoặc khi không còn cần, tránh giữ connection và tài nguyên.
2. **Giới hạn tối đa số bytes** nhận và xử lý; response quá lớn có thể làm bộ nhớ/đĩa đầy.
3. Có **deadline riêng cho bước tiêu thụ stream**, và cancellation/close theo API/transport phù hợp.
4. Với backpressure, không giữ request/response body subscribers vô hạn.
5. Phân biệt **thời điểm response headers đến** với **thời điểm payload nghiệp vụ đã hoàn tất và được validate**.
6. Khi callback/parser mất nhiều giây, timeout network không tự giới hạn CPU/business logic.

Tương tự, một HTTP 200 có response body chưa đủ, JSON không hợp lệ hoặc nội dung bị cắt vẫn có thể gây lỗi application **sau khi** transport đã nhận headers. Thời hạn nghiệp vụ phải bao gồm parse, validate, DB commit và các bước khác khi yêu cầu.

**Đừng đánh tráo khái niệm “response received” với “kết quả nghiệp vụ chắc chắn hợp lệ”.** Timeout của HttpRequest là một công cụ transport; deadline nghiệp vụ và tính đúng đắn dữ liệu do ứng dụng quyết định.

## 13. Kiểm thử đúng: cái gì deterministic, cái gì phụ thuộc mạng?

**Thử nghiệm request timeout** tương đối dễ tạo deterministic: server cục bộ chủ động trì hoãn response sau khi đã nhận request, ví dụ **/slow** trong HttpClientTimeoutDemo. Nó tránh phải dựa vào host bên ngoài và phân biệt được “kết nối TCP đã mở” với “response đến muộn”.

**Thử nghiệm connect timeout** khó tạo deterministic hơn: cần endpoint mới mà việc thiết lập connection **thực sự treo/chậm**, thay vì một cổng không có listener (thường trả connection refused rất nhanh) hoặc địa chỉ DNS không tồn tại (có thể trả UnknownHostException). Firewall, proxy, VPN, dual-stack IPv4/IPv6 và route OS quyết định kết quả.

Không được hứa rằng “gọi 192.0.2.1 luôn ném HttpConnectTimeoutException trong 1 giây”. Địa chỉ dành riêng cho tài liệu, chính sách mạng hoặc firewall có thể route/reject khác nhau, và kết quả không được bảo đảm. Nếu cần kiểm thử connect timeout trong hệ thống thật, dùng **network emulator được cấp phép**, firewall rules của lab hoặc fault injection có quan sát TCP, và ghi lại OS/JDK/proxy/version.

### Ma trận kiểm thử

| Test | Kỳ vọng nên kiểm tra | Không được suy diễn |
|---|---|---|
| Local /fast trả body ngay | HTTP 200, body FAST | Connect timeout đã được “tiêu thụ” bao nhiêu |
| Local /slow trả sau > request timeout | HttpTimeoutException của request | Server chưa xử lý request |
| Gọi sendAsync tới /slow | Future hoàn tất bất thường, cause là timeout | Exception nhất thiết ném trực tiếp khi gọi sendAsync |
| Cấu hình Duration.ZERO | IllegalArgumentException | 0 nghĩa wait forever |
| Tạo client không gọi connectTimeout | Optional.empty() | Không còn lỗi mạng/OS timeout |
| Tạo request không gọi timeout | Optional.empty() | Mọi request sẽ chờ vô hạn bất chấp lỗi khác |
| Kết nối bị từ chối nhanh | Thường là ConnectException hoặc IOException khác | Phải là HttpConnectTimeoutException |
| Proxy trả HTTP 504 | HttpResponse statusCode() == 504 nếu nhận response bình thường | Luôn ném client-side HttpTimeoutException |
| Reused connection, server xử lý chậm | Request timeout mới là giới hạn cần thiết | connectTimeout sẽ được áp lại mỗi request |
| Dùng Future.get(timeout) | TimeoutException chỉ giới hạn thread chờ | Underlying HTTP exchange đã chắc chắn bị hủy |
| Streaming InputStream | Body cần được consumer đóng/xử lý đúng | HttpRequest timeout là deadline cho toàn bộ stream processing |

### Đo thực tế và biểu đồ latency

Để chọn timeout phù hợp, thu thập ít nhất **p50/p95/p99** latency của request, tách **connection establishment** và **time to response** nếu tracing cho phép; quan sát **connect failures**, request timeout, exception causes, active requests, reused connection ratio, retry rate và saturation của server. Tránh chọn timeout thấp hơn p99 chỉ vì muốn UI nhanh nếu điều đó gây retry storm và làm hệ thống chậm hơn.

Cấu hình timeout của **downstream dependencies** còn cần hợp lý với **upstream deadline**. Nếu frontend hết hạn ở 3 giây mà backend đợi DB 30 giây, hệ thống có thể tiếp tục thực hiện công việc vô ích sau khi caller bỏ cuộc. Phối hợp propagated deadlines khi các thư viện/protocol hỗ trợ và quản lý cancellation rõ ràng.

## 14. Những lỗi thường gặp khi viết code

### Lỗi 1 — Chỉ đặt connectTimeout, không đặt request timeout

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(1))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
~~~

Đây là mã minh họa. **request.timeout() rỗng**: nếu server đã nhận connection nhưng xử lý rất lâu, connect timeout không giải quyết được. Hãy đặt request.timeout cho request cần giới hạn response.

### Lỗi 2 — Chỉ đặt request timeout, rồi cho rằng mọi DNS/TLS step được bảo đảm đúng thời gian tuyệt đối

Đây cũng là suy luận quá mức. HttpRequest.timeout là ràng buộc response theo API, nhưng **không thay thế riêng toàn bộ chính sách DNS, proxy, TLS handshake, streaming, application CPU/DB** và không biến HTTP thành hard real-time. Khi cần tổng SLA, dùng overall deadline và kiểm chứng provider.

### Lỗi 3 — Dùng Duration.ZERO như “no timeout”

Cả hai Builder setters đều yêu cầu Duration **dương**. Để không đặt giới hạn ở cấp cấu hình ấy, bỏ qua setter; nếu cần đợi 0, không gửi request mới mà xử lý điều kiện hết deadline trước.

### Lỗi 4 — Bắt HttpTimeoutException trước HttpConnectTimeoutException

Khi cần phân biệt hai loại, bắt **subclass trước**; nếu không cần phân loại, một catch HttpTimeoutException có thể bao cả hai.

### Lỗi 5 — Tạo HttpClient mới cho từng HTTP request

Làm vậy cản trở connection reuse và tăng overhead. HttpClient có thể dùng lại cho nhiều requests và là đối tượng bất biến sau build. Không dùng builder chung thay đổi đồng thời từ nhiều threads.

### Lỗi 6 — Coi timeout là câu trả lời nghiệp vụ “server chưa xử lý”

Một request timeout có thể đến **sau khi server đã commit** nhưng response chưa tới client. Với payment, order, email, job creation, retry phải có idempotency hoặc reconciliation.

### Lỗi 7 — Không xử lý lỗi trong CompletableFuture

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
      .thenAccept(response -> System.out.println(response.statusCode()));
~~~

Đây là ví dụ **thiếu error handling**, chưa phải code độc lập. Nếu request timeout, stage có thể hoàn tất bất thường và logic success không chạy; phải thêm **whenComplete/exceptionally/handle** phù hợp, logging và cleanup. Đừng để caller tưởng request đã xong chỉ vì sendAsync trả CompletableFuture ngay.

### Lỗi 8 — Dùng timeout quá ngắn trên request của chính mình

Thời gian dành cho request cần chứa network jitter, scheduling, TLS/connection setup, queueing và thời gian server xử lý trong phạm vi contract. Lấy một số “150 ms” từ bài lab để áp lên API Internet thường tạo lỗi giả và retry storm.

### Lỗi 9 — Nhầm HTTP status 408/504 với Java exceptions

Kiểm tra **response.statusCode()** khi đã có HttpResponse. Với lỗi network timeout không có response, xử lý exception. Metric 504 của gateway và HttpTimeoutException ở client đo hai sự kiện khác nhau.

### Lỗi 10 — Quên đóng stream và hủy tải thừa

Với **BodyHandlers.ofInputStream**, nếu không đọc/đóng, socket/stream có thể giữ tài nguyên. Đặt giới hạn bytes và lifecycle tiêu thụ body; timeout một Future không thay thế cleanup đúng.

## 15. Bài tập thực hành

### Bài tập A — Đổi một cấu hình, quan sát đúng hiện tượng

Trong **HttpClientTimeoutDemo**, đổi client.connectTimeout từ 2 giây thành 5 giây, giữ /slow timeout 150 ms. Dự đoán điều gì xảy ra với /slow và giải thích vì sao tăng connect timeout không giải quyết server trả response muộn.

### Bài tập B — Đổi timeout của từng request

Đặt /slow timeout = 2 giây trong khi server ngủ 1,2 giây. Với môi trường loopback khỏe, request có thể hoàn thành và trả **SLOW**. Đừng viết test yêu cầu thời gian chính xác từng millisecond; hãy assert status/body và dùng tolerance khi đo duration.

### Bài tập C — Đồng bộ và bất đồng bộ

Chạy cả **send** và **sendAsync** với /slow 150 ms. So sánh **catch HttpTimeoutException** ở send với **CompletionException.getCause()** ở join, và thử phiên bản **future.get()** để quan sát **ExecutionException**.

### Bài tập D — Mặc định và validate config

Chạy **HttpTimeoutDefaultsDemo**, sau đó thử Duration âm. Ghi lại Optional.empty và IllegalArgumentException; giải thích vì sao client không đặt connect timeout vẫn có thể gặp network exception.

### Bài tập E — Phân biệt connect failure với connect timeout

Tạo một HTTP URI trỏ đến một cổng local không có listener trong lab. Xác định exception thực tế; tại sao không thể từ một lần Connection refused mà kết luận HttpClient.connectTimeout đã hết hạn? Không giả định mọi OS có cùng lỗi.

### Bài tập F — Request timeout và HTTP 504

Sửa HTTP server local để trả **HTTP 504** ngay, body "Gateway Timeout". Client request timeout vẫn đủ dài. Assert nhận được HttpResponse có **statusCode() == 504**, không phải Java ném HttpTimeoutException. Phân biệt gateway timeout và client timeout.

### Bài tập G — Overall deadline cho ba requests

Giả sử một nghiệp vụ có tổng 3 giây nhưng gồm A, B, C. Dùng System.nanoTime tính remaining trước từng call, dựng HttpRequest.timeout với Duration dương không vượt budget, trừ thời gian backoff và dừng khi hết budget. Giải thích vì sao mỗi request timeout 3 giây sẽ không tạo deadline chung 3 giây.

### Bài tập H — Retry và idempotency

Thiết kế POST /orders có idempotency key và response cache ở server, giả lập server commit thành công nhưng response bị trì hoãn quá request timeout. Sau retry cùng key, chỉ một order được tạo. Nếu không có hỗ trợ key, trả trạng thái **unknown outcome** và reconciliation thay vì retry mù.

### Bài tập I — Streaming response

Thử BodyHandlers.ofInputStream với server gửi headers rồi stream dữ liệu rất chậm. Quan sát khi nào HttpResponse được trả và thời gian đọc InputStream so với request timeout. Đặt streaming deadline và bảo đảm close cả trong đường lỗi. Không dựa vào một phiên bản JDK để kết luận semantics của tất cả BodyHandlers.

### Bài tập J — Kết nối tái sử dụng

Gửi nhiều GET tới cùng origin với **một** HttpClient, ghi server-side connection identity/remote port và duration. Cân nhắc HTTP/1.1 vs HTTP/2 và server keep-alive. Giải thích vì sao không thể đếm số request rồi coi đó là số lần connect; phân tích connectTimeout trong các trường hợp mở mới và reuse.

## 16. Tự kiểm tra kiến thức

**1. connectTimeout áp dụng cho mọi request hay chỉ khi cần connection mới?** Theo Java 17 Javadoc, nó có hiệu lực khi cần thiết lập **connection mới**; connection reuse không chịu connectTimeout ấy.

**2. Server đã nhận TCP connection nhưng đợi database 20 giây; timeout nào quan trọng?** HttpRequest.Builder.timeout cho việc chờ response, cộng overall deadline khi cần.

**3. Hai HttpRequest dùng cùng HttpClient có thể có timeout khác nhau không?** Có. Mỗi request cấu hình một Duration riêng.

**4. HttpClient.connectTimeout() và HttpRequest.timeout() trả gì?** Optional<Duration>, rỗng nếu không có timeout tương ứng được cấu hình.

**5. Duration.ZERO có nghĩa không giới hạn?** Không. Cả hai setter ném IllegalArgumentException đối với Duration không dương.

**6. HttpConnectTimeoutException có thuộc HttpTimeoutException không?** Có, là subclass. Bắt subclass trước nếu phân loại.

**7. sendAsync quá hạn ném HttpTimeoutException ngay tại lời gọi?** Không nhất thiết; CompletableFuture hoàn tất bất thường, caller thấy cause qua get/join hoặc callback.

**8. future.get(2, SECONDS) quá hạn nghĩa request chắc chắn bị hủy?** Không. Chỉ caller dừng đợi, operation có thể tiếp tục trừ khi được xử lý cancellation theo policy.

**9. HTTP 504 có đồng nghĩa HttpTimeoutException không?** Không. 504 có thể là một HTTP response hợp lệ do gateway trả.

**10. Vì sao HttpRequest.timeout không thể được tuyên bố là timeout cho mọi thao tác đọc stream sau khi nhận HttpResponse?** Vì BodyHandler có thể trả đối tượng streaming trước khi body được tiêu thụ hết và trách nhiệm đọc/close/cancel nằm ở consumer.

**11. Chỉ cần connectTimeout 300 ms thì đủ bảo vệ API call dưới 300 ms?** Không. Server có thể xử lý lâu trên connection đã mở; request timeout và deadline mới giải quyết phần còn lại.

**12. Khi request POST timeout, có nên retry ngay với request ID mới?** Không được mặc định. Server có thể đã commit; cần idempotency key hoặc đối soát.

**13. Java HttpClient có tự retry mọi timeout không?** Không được giả định một chính sách retry nghiệp vụ chung. Hãy chủ động kiểm soát số lần, backoff, deadline và điều kiện an toàn; xét hành vi triển khai khi cần.

**14. Vì sao test connect timeout bằng cổng không có listener thường sai?** Vì OS có thể từ chối kết nối ngay, không phải đợi đủ thời gian connect timeout.

**15. DNS/TLS/redirect/proxy có luôn bị chặn chính xác bởi connectTimeout của Java 17 không?** Không nên khẳng định tuyệt đối như vậy; API mô tả phạm vi thiết lập connection mới, chi tiết các bước khác cần kiểm chứng trên provider/JDK và có overall deadline nếu cần.

## Tài liệu chính thức Java SE 17

- **HttpClient.Builder — connectTimeout:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- **HttpRequest.Builder — timeout:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- **HttpClient — send/sendAsync, kết quả response và BodyHandler:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **HttpResponse.BodyHandlers — ofString/ofInputStream và các kiểu xử lý body:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- **HttpTimeoutException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- **HttpConnectTimeoutException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html
- **Duration:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html

**Ghi nhớ:** **HttpClient.Builder.connectTimeout** giới hạn thời gian thiết lập **connection mới**, **không** giải quyết response chậm trên kết nối tái sử dụng. **HttpRequest.Builder.timeout** đặt giới hạn **chờ response riêng cho từng request** và dẫn tới **HttpTimeoutException** nếu quá hạn. Trong Java 17, **HttpConnectTimeoutException là subclass của HttpTimeoutException**; sendAsync báo lỗi qua CompletableFuture. Khi một nghiệp vụ gồm nhiều requests, streaming, retries hoặc side effects, cần thêm **overall deadline, cancellation/cleanup, backoff, idempotency và monitoring**; không suy rằng một timeout duy nhất bao hết mọi tầng mạng và xử lý ứng dụng.