# Keep-alive TCP, tái sử dụng HTTP và heartbeat ứng dụng có mục đích khác nhau

**Chủ đề:** Java Advance - networking  
**Nhóm:** Độ tin cậy  
**Mục tiêu:** hiểu ba cơ chế thường bị gọi là “keep-alive” nhưng khác nhau về tầng mạng, mục tiêu, khả năng phát hiện lỗi và cách triển khai trong Java 17+.

Một kết nối TCP có thể còn phản hồi ACK trong khi Java service đã deadlock. Một connection đang trong pool của HTTP client có thể đã bị proxy đóng vì idle timeout. Một heartbeat **GET /ready** có thể trả **503** trong khi HTTP request vẫn đi và về hoàn chỉnh. Do đó:

- **TCP keep-alive** thăm dò tính kết nối ở tầng TCP khi socket idle, do OS quản lý; **không tạo HTTP requests**.
- **HTTP keep-alive/persistent connection** cho phép **tái sử dụng kết nối** cho nhiều request/response nhằm tiết kiệm TCP/TLS handshakes và tài nguyên.
- **Heartbeat ứng dụng** là thông điệp có **ngữ nghĩa health/readiness** và **deadline**, do application hoặc SDK quản lý, nhằm đánh giá một điều kiện hoạt động cụ thể.

**SO_KEEPALIVE=true ≠ HTTP connection được reuse ≠ service ready.** Ba cơ chế có thể cùng tồn tại nhưng không thay thế nhau. Bài có bảng so sánh, sơ đồ, API Java, một chương trình Java 17 độc lập đã chạy thật, mẫu scheduler, lỗi thực tế, quan sát vận hành và checklist.

## 1. Vị trí của từng cơ chế

~~~text
Application layer
    GET /ready -> 204/503
    App heartbeat message -> ACK / timeout
    Mục tiêu: kiểm tra app/service theo contract
              |
              v
HTTP layer
    HttpClient, connection pool, persistent HTTP/1.1
    HTTP/2 multiplexed streams, HTTP/3 QUIC connection reuse
    Mục tiêu: tiết kiệm kết nối/handshakes
              |
              v
Transport layer (nếu dùng TCP)
    Socket SO_KEEPALIVE, kernel idle probes
    Mục tiêu: phát hiện một số peer/path failures
~~~

| Câu hỏi | TCP keep-alive | HTTP connection reuse | Application heartbeat |
| --- | --- | --- | --- |
| Tầng nào? | TCP/OS | HTTP client + server/pool | Business/application protocol |
| Ai kích hoạt? | Kernel khi socket idle và bật option | HTTP implementation khi gửi request | Scheduler/SDK/app gọi health/ping |
| Gửi gì? | TCP probe, chờ TCP ACK | HTTP request thực trên connection có sẵn | Request /ready hoặc heartbeat+ACK |
| Mục đích | Kiểm tra một phần TCP reachability | Giảm chi phí mở connection | Kiểm tra responsiveness/readiness |
| Kiểm tra DB, queue, worker? | **Không** | **Không** | **Chỉ nếu endpoint kiểm tra** |
| Phát hiện lỗi trong SLA vài giây? | Không được bảo đảm, phụ thuộc OS timers | Chỉ khi send/read gặp lỗi | Theo interval, deadline, threshold |
| Bảo đảm dùng cùng socket? | Chỉ cấu hình một socket cụ thể | Không | Không |
| Dùng cho HTTP/3? | Không: HTTP/3 qua QUIC/UDP | Có QUIC reuse nhưng không phải TCP | Có thể có health request qua H3 |

Một heartbeat HTTP có thể được gửi trên connection HTTP persistent, và TCP connection bên dưới có thể bật SO_KEEPALIVE. Không có mâu thuẫn khi cả ba hoạt động, nhưng mỗi tầng cần metrics và error handling riêng.

## 2. TCP SO_KEEPALIVE: cơ chế của kernel

**TCP keep-alive** là tính năng tùy chọn của TCP stack. Khi bật trên một TCP socket, sau thời gian idle và các điều kiện hệ điều hành cho phép, kernel có thể gửi probe nhằm kiểm tra TCP peer/path còn phản hồi. **RFC 9293 mục 3.8.4** giải thích tính optional, default disabled, khoảng probe mặc định có thể rất dài; không được xem một lần probe không phản hồi là bằng chứng đủ rằng peer chết.

Trong Java 17:

~~~java
// Snippet: biến port đã được xác định.
try (Socket socket = new Socket()) {
    socket.setKeepAlive(true);
    socket.connect(new InetSocketAddress("127.0.0.1", port), 2000);
    System.out.println(socket.getKeepAlive()); // true
}
~~~

**Socket.getKeepAlive()==true chỉ xác nhận option đã bật**, không chứng minh đã phát probe, không đọc được HTTP status và không gọi Java server handler. Kết nối có thể vừa tạo xong, chưa đủ idle để kernel gửi bất kỳ keep-alive probe nào.

Tương đương ở SocketChannel:

~~~java
// Snippet Java 17.
try (SocketChannel ch = SocketChannel.open()) {
    ch.setOption(StandardSocketOptions.SO_KEEPALIVE, true);
    ch.connect(new InetSocketAddress("127.0.0.1", port));
}
~~~

**StandardSocketOptions.SO_KEEPALIVE** là Boolean và hành vi probe **system-dependent**. Trên những nền tảng cho phép, **jdk.net.ExtendedSocketOptions.TCP_KEEPIDLE/TCP_KEEPINTERVAL/TCP_KEEPCOUNT** có thể thay đổi idle time, khoảng giữa các lần thử và giới hạn số probes. Chúng không phải API portable trên mọi socket/OS; phải kiểm tra supportedOptions() và xử lý unsupported behavior.

**Đừng lẫn với Socket.setSoTimeout()**: SO_TIMEOUT liên quan read() chờ dữ liệu; SO_KEEPALIVE là thăm dò kết nối TCP idle. Bật SO_KEEPALIVE **không thay request timeout** và không làm app handler trả lời nhanh hơn.

### Tại sao TCP peer có thể sống nhưng app chết?

~~~text
Client TCP                  Server kernel             Server app
    | --- keepalive probe ---> |                         |
    | <--------- ACK --------- |                         |
    |                          |     Worker deadlock      |
    | --- GET /ready --------> | -----> không xử lý ----> X
    |       chờ đến deadline...
~~~

TCP ACK có thể được kernel xử lý mà không cần application worker chạy. Server vẫn có thể mất DB, bị stop-the-world pause, thiếu threads, bị lỗi queue, không có quyền xử lý request. Vì vậy **TCP keep-alive chỉ là tín hiệu TCP-level**, không phải service readiness.

**Socket do bạn tạo khác sockets của HttpClient.** Java 17 **HttpClient.Builder** không có setter công khai tổng quát tên tcpKeepAlive(true) để đặt SO_KEEPALIVE trên mọi sockets do built-in HttpClient sở hữu. Đừng gọi **Socket.setKeepAlive(true)** trên một socket riêng rồi mặc định HTTP client cũng dùng cấu hình đó.

## 3. HTTP keep-alive: persistent connection/connection reuse

Theo **RFC 9112 mục 9.3**, **HTTP/1.1 mặc định cho phép persistent connections** nếu không có **Connection: close** và các điều kiện framing khác cho phép. Một TCP/TLS connection có thể phục vụ nhiều HTTP requests, tránh chi phí TCP handshake/TLS handshake cho mỗi request.

~~~text
Không reuse:
  TCP connect -> TLS -> GET /a -> response A -> close
  TCP connect -> TLS -> GET /b -> response B -> close

Có reuse:
  TCP connect -> TLS -> GET /a -> response A
                     -> GET /b -> response B
                     -> GET /c -> response C -> close later
~~~

**HTTP keep-alive không yêu cầu Socket.setKeepAlive(true).** Đó là hai cơ chế độc lập. HTTP/1.1 persistent connections **không bắt buộc** header **Connection: keep-alive**; đây là source nhầm lẫn từ compatibility/HTTP/1.0. **Connection: close** báo connection không tiếp tục persistent sau exchange theo quy tắc protocol.

Một connection persistent cần biết ranh giới message body; theo RFC, server muốn reuse phải nhận hết request body hoặc đóng, client muốn reuse phải đọc hết response body. Nếu một HTTP response stream vẫn mở chưa được consume, client có thể không tái dùng connection.

~~~java
// Java 17: body hoàn chỉnh.
HttpResponse<String> res = client.send(
        request, HttpResponse.BodyHandlers.ofString());

// Với streaming, caller chịu trách nhiệm read-to-EOF hoặc close.
HttpResponse<InputStream> streamed = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = streamed.body()) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = body.read(buffer)) != -1) {
        // Xử lý chunk với size/deadline limits.
    }
}
~~~

Đây là snippets cần imports và các biến client/request đã tạo. Không gọi readAllBytes() cho response GB hoặc stream vô hạn chỉ để giữ keep-alive; **đóng sớm** có thể mất reuse nhưng vẫn đúng nếu consumer không cần dữ liệu.

### HTTP/1.1, HTTP/2 và HTTP/3

| Protocol | Kết nối và reuse | TCP keep-alive |
| --- | --- | --- |
| HTTP/1.1 | Một TCP connection persistent cho nhiều HTTP exchanges | Có thể bật trên TCP socket nếu implementation cho phép |
| HTTP/2 | Multiplex nhiều HTTP streams trên cùng một TCP/TLS connection | TCP still exists; nhưng HTTP/2 PING là cơ chế khác |
| HTTP/3 | Multiplex streams trên QUIC connection chạy UDP | **Không** dùng TCP, SO_KEEPALIVE không áp dụng |

**HTTP/2 PING** và **QUIC PING** là control/protocol-level signals; chúng không chứng minh **business readiness**. **WebSocket Ping/Pong** cũng không tự xác nhận worker đã commit application message.

## 4. Java HttpClient và connection pool

**HttpClient** trong Java 17 có thể được xây một lần và tái sử dụng cho nhiều requests. HTTP client giữ configuration, connection resources, auth/proxy/redirect policies và có thể reuse connections theo implementation.

~~~java
// Snippet Java 17:
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .version(HttpClient.Version.HTTP_1_1)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/data"))
        .timeout(Duration.ofSeconds(3))
        .GET().build();

HttpResponse<String> a = client.send(
        request, HttpResponse.BodyHandlers.ofString());
HttpResponse<String> b = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Việc dùng cùng instance **tạo cơ hội reuse**, không bảo đảm a/b dùng **cùng socket**. Client/server/proxy có thể mở nhiều connections, xử lý concurrent requests, idle eviction, TLS issues hoặc server close.

**Trong Java 17, HttpClient chưa là AutoCloseable.** API đóng/shutdown trực tiếp được thêm từ Java 21; không viết try-with-resources cho HttpClient khi compile với **--release 17**. Tài nguyên của response streaming cần consumer đóng riêng.

### Pool idle timeout không phải TCP probe interval

Một số OpenJDK builds có property **jdk.httpclient.keepalive.timeout** quy định giữ **HTTP idle connection trong pool** bao lâu. Đây là **cache eviction policy**, không phải thời gian kernel gửi TCP probes. Default/semantics là implementation-/version-specific. Không chỉnh property này rồi kỳ vọng TCP keep-alive hoặc readiness được bật.

**HTTP headers Connection/Keep-Alive** cũng không phải knob để bật Socket.SO_KEEPALIVE. Trong java.net.http, một số headers liên quan connection management bị restricted. Nếu HTTP/2/HTTP/3 được dùng, semantics còn khác HTTP/1.1 hop-by-hop headers.

## 5. Heartbeat ứng dụng và health contract

Heartbeat ứng dụng chủ động hỏi remote service về một điều kiện cụ thể. Ví dụ:

- **GET /live** hỏi process/handler còn phản hồi theo định nghĩa liveness.
- **GET /ready** kiểm tra service có đủ điều kiện nhận traffic: workers, DB/queue/dependency theo contract.
- **WebSocket app heartbeat** gồm ID/nonce và ACK, không chỉ WebSocket control Pong.
- **gRPC health service** trả trạng thái service theo protocol.
- Một message hoặc request nhẹ trong business protocol có deadline riêng.

Ví dụ /ready:

~~~text
Client GET /ready   ---> Server ready=true
Client <--- 204 No Content

Server đổi ready=false

Client GET /ready   ---> Server (TCP/HTTP vẫn hoạt động)
Client <--- 503 Service Unavailable
~~~

**HTTP 503 ở đây là response hợp lệ do server gửi**. Nó cho biết application báo not ready, **không chứng minh TCP connection chết**. Tương tự, TCP peer/kernel có thể còn ACK nhưng /ready timeout vì app deadlock.

### Liveness khác readiness

| Kiểm tra | Có thể nói gì? | Không chứng minh |
| --- | --- | --- |
| TCP keepalive ACK | TCP peer/path phản hồi tại thời điểm probe | Worker/DB sẵn sàng |
| HTTP GET /live → 200 | Live endpoint trả đúng deadline | Mọi dependency ready |
| HTTP GET /ready → 204 | Endpoint nói ready theo contract của nó | Mọi request tương lai thành công |
| WebSocket Pong | WebSocket protocol peer trả control frame | Business event đã xử lý |
| App heartbeat ACK+nonce | Application nhận và đáp ứng đúng message | Job khác đã commit |
| Business receipt/ID | Operation có kết quả theo contract | Hệ thống sẽ không lỗi tiếp |

**Health endpoint chỉ tốt bằng logic thực hiện của nó.** Nếu /ready luôn trả 200 mà không kiểm tra queue/DB cần thiết, nó không đại diện đúng readiness. Nếu mỗi check chạy một truy vấn DB nặng và 10.000 clients cùng ping, endpoint có thể tự gây overload.

### Thành phần của một heartbeat

- **Interval**: tần suất phù hợp với SLA và traffic.
- **Per-attempt deadline**: connect/request/response timeout.
- **Success predicate**: status/body/ACK/nonce nào hợp lệ.
- **Failure threshold**: bao nhiêu lần lỗi liên tiếp chuyển degraded/unhealthy.
- **Recovery threshold**: bao nhiêu lần success để hồi phục, tránh flapping.
- **Non-overlap**: không chạy nhiều checks lên cùng target khi lượt trước chưa xong.
- **Jitter/backoff**: tránh nhiều clients đồng thời và retry storm.
- **Cancellation/shutdown**: dừng task, đóng tài nguyên/stream.
- **Observability**: latency, last success, error class, status code.
- **Security**: hạn chế lộ health details và tokens.

Một heartbeat trả 204 chứng minh **endpoint đã trả 204 tại thời điểm đó**, không cam kết POST sau đó sẽ thành công.

## 6. Kịch bản lỗi: connection reuse nhưng service không ready

Một server có thể vẫn nhận HTTP requests trong khi worker/dependency chính không dùng được:

~~~text
T0: GET /resource -> 200, body đầy đủ, connection có thể reuse
T1: Application ready=true -> GET /health = 204
T2: DB queue backlog hoặc app chuyển ready=false
T3: GET /health = 503 (cùng HTTP protocol hoạt động)
T4: Load balancer/routing logic có thể ngừng gửi business traffic
~~~

**Không có mâu thuẫn:** connection reuse là khả năng tầng HTTP, readiness là kết quả từ health handler. Nếu chỉ theo dõi socket status hoặc số lần HTTP 200, bạn có thể không phát hiện service degraded.

## 7. Kịch bản lỗi: cached connection stale do LB/NAT

~~~text
Java HttpClient --- TCP A ---> proxy/LB --- TCP B ---> backend
      |                       |                      |
      | -- GET /data -------->|--------------------->|
      |<--- 200 --------------|<---------------------|
      |                       |                      |
      |       idle            |  middlebox closes   |
      |                       |                      |
      | -- next request ----->|   reconnect or fail |
~~~

**SO_KEEPALIVE** trên client TCP A không chứng minh trạng thái TCP B. Một số middleboxes có idle policies độc lập, có thể không reset timers theo TCP keepalive probes. HTTP heartbeat nếu thực sự đi qua proxy và tới handler backend có thể phản ánh một đường end-to-end hơn, nhưng không **bảo đảm** nó giữ đúng socket idle hoặc bao quát mọi dependency.

**Không suy từ một lần stale connection fail rằng server process chết**. Client có thể reconnect. Cũng không ép heartbeat tần suất cao chỉ để tránh handshake mới nếu chi phí lớn hơn lợi ích.

## 8. Ví dụ Java 17 độc lập: minh họa cả ba tầng

Tệp **KeepAliveLayersDemo.java** tạo một HTTP server trên loopback **127.0.0.1** với port do OS cấp. Nó chạy ba phép thử:

1. Một **raw Socket riêng** bật **SO_KEEPALIVE**, xác minh flag bằng **getKeepAlive()**. Nó không gửi HTTP và không áp dụng config lên HttpClient.
2. Một **HttpClient HTTP/1.1** gửi hai GET **/resource**; server trả header debug **X-Observed-Peer-Port** ghi client source port để quan sát khả năng reuse trong **lần chạy thử**.
3. Hai GET **/health**; lần đầu **ready=true** trả **204**, sau khi đổi **ready=false** trả **503**; server tăng **healthRequests**.

Mọi request đều đi vào fixture do chính chương trình khởi chạy, không cần Internet. Header debug chỉ dùng để minh họa, **không phải chuẩn HTTP connection ID**. Client source port giống nhau phù hợp với reuse trên loopback, nhưng không phải test assertion bắt buộc vì pool/proxy/NAT có thể thay đổi.

### Mã nguồn: KeepAliveLayersDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class KeepAliveLayersDemo {
    static final AtomicBoolean ready = new AtomicBoolean(true);
    static final AtomicInteger healthRequests = new AtomicInteger();

    static void resource(HttpExchange exchange) throws IOException {
        try (exchange) {
            byte[] body = "DATA".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "X-Observed-Peer-Port",
                    Integer.toString(exchange.getRemoteAddress().getPort()));
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        }
    }

    static void health(HttpExchange exchange) throws IOException {
        try (exchange) {
            healthRequests.incrementAndGet();
            if (ready.get()) {
                exchange.sendResponseHeaders(204, -1);
            } else {
                byte[] body = "NOT_READY".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(503, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            }
        }
    }

    static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET().build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/resource", KeepAliveLayersDemo::resource);
        server.createContext("/health", KeepAliveLayersDemo::health);
        server.start();
        try {
            InetSocketAddress address = new InetSocketAddress(
                    "127.0.0.1", server.getAddress().getPort());
            try (Socket raw = new Socket()) {
                raw.setKeepAlive(true);
                raw.connect(address, 2000);
                System.out.println("tcpSO_KEEPALIVE=" + raw.getKeepAlive());
            }

            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            HttpResponse<String> a = client.send(
                    get(base.resolve("resource")),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            HttpResponse<String> b = client.send(
                    get(base.resolve("resource")),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            String firstPeerPort = a.headers()
                    .firstValue("X-Observed-Peer-Port").orElseThrow();
            String secondPeerPort = b.headers()
                    .firstValue("X-Observed-Peer-Port").orElseThrow();
            System.out.println("httpStatuses="
                    + a.statusCode() + "," + b.statusCode());
            System.out.println("httpBodies=" + a.body() + "," + b.body());
            System.out.println("observedSameConnection="
                    + firstPeerPort.equals(secondPeerPort));

            HttpResponse<Void> ok = client.send(
                    get(base.resolve("health")),
                    HttpResponse.BodyHandlers.discarding());
            ready.set(false);
            HttpResponse<Void> notReady = client.send(
                    get(base.resolve("health")),
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("healthStatuses="
                    + ok.statusCode() + "," + notReady.statusCode());
            System.out.println("healthRequests=" + healthRequests.get());
            System.out.println("businessReadyAfterChange=" + ready.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Chạy và kiểm chứng

Yêu cầu JDK 17+, có module **jdk.httpserver**. Tạo file với đúng tên:

~~~bash
javac --release 17 -encoding UTF-8 KeepAliveLayersDemo.java
java KeepAliveLayersDemo
~~~

**Stdout đã biên dịch với --release 17 và chạy thực tế trên JDK 24.0.2:**

~~~text
tcpSO_KEEPALIVE=true
httpStatuses=200,200
httpBodies=DATA,DATA
observedSameConnection=true
healthStatuses=204,503
healthRequests=2
businessReadyAfterChange=false
~~~

**Phân tích từng dòng:**

- **tcpSO_KEEPALIVE=true** chỉ xác nhận bật option trên **raw Socket riêng**. Không khẳng định kernel đã gửi probe vì thời gian idle trong demo rất ngắn.
- **httpStatuses=200,200** và **httpBodies=DATA,DATA** cho thấy hai HTTP requests được gửi, nhận đủ response body với cùng HttpClient.
- **observedSameConnection=true** là quan sát của JDK 24 loopback test: server thấy cùng client source port ở hai GET. Dòng này **có thể là false trên môi trường khác mà không vi phạm API**.
- **healthStatuses=204,503** chứng minh HTTP service có thể phản hồi nhưng business readiness thay đổi từ true sang false.
- **healthRequests=2** là số HTTP endpoint invocations, không liên quan TCP probes.
- **businessReadyAfterChange=false** là state do test fixture định nghĩa, không đại diện dependency production.

Demo không kiểm thử thực sự TCP probes trên dây, TLS, HTTP/2 multiplexing, QUIC, proxy hay load balancer. Muốn quan sát SO_KEEPALIVE probes, cần thời gian idle/timers phù hợp và packet capture hoặc OS counters. **Không** sửa test để in “TCP alive” chỉ vì getKeepAlive()==true.

## 9. Application heartbeat scheduler Java 17

Trong thực tế, health check thường được chạy theo nhịp. Mẫu sau **không phải chương trình độc lập**: giả định đã có **client**, **healthUri**, **scheduler**, **consecutiveFailures** và những hàm ghi metrics do app định nghĩa.

~~~java
HttpRequest healthRequest = HttpRequest.newBuilder(healthUri)
        .timeout(Duration.ofSeconds(3))
        .GET().build();

ScheduledFuture<?> task = scheduler.scheduleWithFixedDelay(() -> {
    try {
        HttpResponse<Void> response = client.send(
                healthRequest, HttpResponse.BodyHandlers.discarding());
        if (response.statusCode() == 204) {
            consecutiveFailures.set(0);
            recordReady();
        } else {
            int fails = consecutiveFailures.incrementAndGet();
            recordNotReady(response.statusCode(), fails);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // Ứng dụng phải xử lý shutdown/cancel tương ứng.
    } catch (IOException e) {
        int fails = consecutiveFailures.incrementAndGet();
        recordTransportFailure(e, fails);
    }
}, 0, 10, TimeUnit.SECONDS);
~~~

**ScheduledExecutorService.scheduleWithFixedDelay** được dùng vì task không tự overlap khi lượt trước đang chạy; lượt sau chạy sau khi lượt trước kết thúc và delay thêm. **Không** để task block vô hạn: request phải có deadline và cleanup.

**Lifecycle:** ứng dụng phải **task.cancel(...)**, **scheduler.shutdown()** khi dừng; không để scheduler thread giữ JVM/tài nguyên vô thời hạn. Có thể bổ sung một ngưỡng **consecutive failures** (ví dụ ba lượt) trước khi chuyển unhealthy và một ngưỡng recovery khác để tránh flapping.

**Business health contract** ở đây chỉ chấp nhận 204; đó là quy ước của ví dụ. Với service khác, 200 + JSON healthy flag hoặc message ACK+nonce có thể đúng. Không gộp HTTP status 503/401/429 thành IOException: chúng có response và nguyên nhân/sửa chữa khác nhau.

### Bảng lập lịch

| Yếu tố | Quyết định cần có |
| --- | --- |
| Interval | Tần suất cần biết trạng thái trước request thật |
| Deadline | HTTP request timeout + app reply deadline |
| Threshold | Mấy lần fail thì degraded/unhealthy |
| Recovery | Mấy lần success để healthy lại |
| Jitter | Giảm synchronized health traffic |
| Concurrency | Không gửi chồng checks cho cùng target |
| Safety | Health request nên safe/idempotent |
| Cleanup | Cancel/shutdown scheduler, release bodies |
| Metrics | Last success, latency, failure reason |
| Security | Không rò token, cookies, dependency internals |

**Ví dụ tải:** 20.000 clients gửi một heartbeat mỗi 5 giây tạo **4.000 checks/giây trung bình**; nếu đồng bộ nhịp có thể cao hơn rất nhiều trong từng giây. Đừng mặc định heartbeat càng dày càng tốt. Dùng jitter, aggregation hoặc central health checks tùy topology.

## 10. Timeouts và phát hiện sự cố

| Cấu hình | Điều nó giới hạn/quan sát | Không phải |
| --- | --- | --- |
| SO_KEEPALIVE idle timer | Khi OS có thể thăm dò TCP socket idle | Request timeout |
| TCP probe interval/count | Cách OS xác định TCP path không phản hồi | App health deadline |
| HTTP pool idle timeout | Bao lâu giữ connection trong pool | Peer/application liveness |
| HttpClient.connectTimeout | Thời gian thiết lập connection mới | Tổng lifetime mọi requests |
| HttpRequest.timeout | Giới hạn request theo contract Java | Body idle timeout của stream đã giao |
| Heartbeat interval | Tần suất hỏi readiness | Timeout mỗi request |
| Heartbeat request deadline | Đợi response đúng contract | Bảo đảm health trong tương lai |
| Business transaction timeout | Giới hạn operation nghiệp vụ | Bảo đảm server rollback |

Một request **ofInputStream()** có thể trả HttpResponse khi body còn mở, nên ứng dụng streaming cần thêm body idle deadline/close/cancel. **TCP keep-alive không thay thế** những deadline này. Một **HTTP 503** là response được nhận; một **connect timeout** có thể không có HttpResponse nào.

Nếu một POST tạo side effect đã được server commit nhưng response mất, retry vô điều kiện có thể trùng giao dịch. **SO_KEEPALIVE, HTTP reuse và heartbeat đều không tự xác định business outcome**. Cần idempotency key, server deduplication hoặc status inquiry theo API contract.

## 11. Middleboxes và nhiều hops

~~~text
Java client --- TCP A ---> proxy/LB --- TCP B ---> backend
      |                     |                    |
      |---- HTTP request -->|---- HTTP request -->|
      |<--- HTTP response --|<--- HTTP response --|
      |                     |                    |
      | idle / probe        | closes TCP B       |
      |                     |                    |
      |---- next request -->| reconnect/fail     |
~~~

**SO_KEEPALIVE** trên TCP A chỉ thăm dò connection của **client↔proxy**. Nó không chứng minh TCP B tới backend, càng không chứng minh backend DB khỏe. Heartbeat HTTP nếu được forward qua proxy và được backend handler xử lý có thể kiểm tra end-to-end theo contract. HTTP client pool của proxy cũng có idle policy khác, nên một client-side connection được reuse chưa chắc backend-side connection được reuse.

**NAT/LB có thể có idle timeout riêng** và có thể không tính TCP probes như traffic reset timer. Việc gửi /health có thể làm connection bớt idle nếu thực sự đi trên connection đó, nhưng không có guarantee giữ mọi network flow. Đừng tắt timeouts hoặc gửi heartbeat liên tục chỉ vì kết nối idle có thể bị đóng bình thường.

## 12. Phân loại thất bại theo đúng tầng

| Hiện tượng | Tín hiệu đúng |
| --- | --- |
| Socket.getKeepAlive()==true | Option TCP đã bật |
| TCP probe được ACK | TCP peer/path phản hồi trong tình huống đó |
| Hai HTTP GET có cùng peer port trong fixture | Quan sát có thể đã reuse connection |
| HTTP GET /health → 204 | Service báo ready theo contract |
| HTTP GET /health → 503 | Service báo not ready nhưng HTTP vẫn trả response |
| GET /health → 401/403 | Auth/permission failure, không mặc định server chết |
| GET /health → 429 | Rate limit/overload, cần giảm checks/backoff |
| TLS certificate error | Identity/trust failure, không có HTTP status tương ứng |
| DNS/connect failure | Transport/network error |
| Timeout | Không có response kịp deadline; chưa biết server đã xử lý gì |
| WebSocket Pong | Control-plane peer phản hồi, không phải business ACK |
| HTTP/2 PING ACK | HTTP/2 protocol peer phản hồi, không phải readiness |
| QUIC PING response | QUIC path còn phản hồi, không phải TCP keepalive |

**Không gán transport IOException thành HTTP 503/500 giả**. Log các trường **httpStatus**, **transportError**, **serviceReady**, **actualHttpVersion** riêng. Đừng coi một lần thất bại là hệ thống chết vĩnh viễn: cân nhắc retries có hạn, consecutive failures và recovery policy.

## 13. Monitoring và observability

Một dashboard tốt tách ba nhóm:

**Transport metrics:** TCP connect attempts/failures, resets, retransmissions, OS socket configuration khi đo được, proxy/LB closes, TLS failures.

**HTTP connection metrics:** connection setup latency, new/reused connections khi instrumentation cho phép, idle pool size/lifetime, response protocol version qua **HttpResponse.version()**, streaming bodies còn mở/cancelled, request throughput.

**App heartbeat metrics:** health attempts/success/failure, response status và semantic result, response latency, last successful check, consecutive failures, time in DEGRADED/UNHEALTHY và dependency checker scope.

Ví dụ:

~~~text
transport.tcp_keepalive_option=true
http.connection_reused_observed=true
http.version=HTTP_1_1
heartbeat.endpoint=/health
heartbeat.http_status=503
heartbeat.ready=false
heartbeat.latency_ms=(giá trị đo thực)
~~~

Các field này **không mâu thuẫn**. Một connection có thể được reuse trong khi service readiness là false. Không log raw body/secret headers từ health requests; tránh tạo high-cardinality metrics theo URL chứa personal data.

## 14. Các sai lầm thường gặp

| Nhầm lẫn | Hậu quả | Cách sửa |
| --- | --- | --- |
| SO_KEEPALIVE=true nghĩa app sống | Deadlock không được phát hiện | App heartbeat/ready check riêng |
| TCP keepalive và HTTP keep-alive là một | Cấu hình sai tầng | Kernel probes khác connection pool |
| Bật TCP keepalive tự gửi GET /health | Không có application traffic | Scheduler hoặc SDK phải gửi |
| HTTP/1.1 luôn cần Connection: keep-alive | Header thừa/bị hạn chế | HTTP/1.1 persistent mặc định |
| Cùng HttpClient thì luôn cùng socket | Assertion brittle | Không có reuse guarantee |
| Connection trong pool chắc chắn còn mở | Stale socket do LB | Xử lý reconnect/failure |
| HTTP 503 nghĩa TCP chết | Chẩn đoán sai | 503 là HTTP response |
| /ready trả 200 nghĩa DB khỏe | False positive | Health contract kiểm tra đúng dependency |
| WebSocket Pong nghĩa event đã commit | Lỗi business state | App-level ack |
| HTTP/3 dùng TCP keepalive | Sai transport | QUIC/UDP riêng |
| Bật SO_KEEPALIVE đủ phát hiện trong vài giây | SLA sai | OS timers thường dài |
| Heartbeat càng thường xuyên càng tốt | Health traffic storm | Interval, jitter, caps |
| Heartbeat tự giữ socket khỏi mọi LB timeout | Vẫn có stale path | Đo topology và idle policies |
| Forget close InputStream response | Leak và reuse giảm | Drain hoặc close streaming body |
| Timeout POST thì retry luôn | Duplicate side effects | Idempotency key |
| Xem TCP ACK là business transaction success | Sai tầng | Business receipt/status inquiry |

## 15. Kiểm thử kỹ thuật

| Scenario | Cách mô phỏng | Điều cần đánh giá |
| --- | --- | --- |
| SO_KEEPALIVE enabled | Socket.setKeepAlive(true), getKeepAlive | Flag true, không claim probe |
| HTTP reuse | Hai GET cùng client, server ghi peer port | Reuse có thể được quan sát |
| Server đóng idle connection | HTTP test server close giữa requests | Reconnect hoặc failure tùy client |
| App not ready nhưng HTTP hoạt động | /health 204 rồi 503 | Phân loại HTTP vs readiness |
| App worker treo | Chặn handler, giữ TCP kernel active | TCP keepalive không thay deadline |
| Proxy tách TCP A/B | Tạo middlebox/ingress test | Không suy một hop chứng minh hop khác |
| Streaming body mở | BodyHandlers.ofInputStream chưa consume | Kiểm tra cleanup/timeout |
| HTTP 401/403 heartbeat | Token invalid | Authentication error không phải app dead |
| HTTP 429 heartbeat | Rate limiter | Backoff, không retry storm |
| Network timeout | Server không phản hồi | Error type/threshold hợp lý |
| TCP keepalive probes | OS timers + packet capture | Phân biệt option true và probe thật |
| HTTP/3 service | QUIC endpoint | TCP options không ảnh hưởng QUIC |
| POST commit + lost reply | Fixture side-effect rồi drop response | Idempotency/no duplicates |

**Đừng biến observedSameConnection=true trong demo thành test cứng trên mọi máy.** Cùng client source port chỉ là phép quan sát đơn giản khi không có proxy; OS/HTTP client có thể quản lý connections khác nhau hợp lệ.

## 16. Bài tập

1. Phân biệt TCP keepalive, HTTP connection reuse và heartbeat application theo tầng, thông điệp, trigger và mục tiêu.
2. Giải thích tại sao kernel ACK TCP probe khi Java workers đang deadlock.
3. Vì sao HTTP/1.1 persistent mặc định không cần Connection: keep-alive?
4. Tạo một HttpClient dùng cho hai GET. Có thể chứng minh cả hai cùng socket chỉ bằng client identity không?
5. Nếu proxy đã đóng connection idle, request tiếp có thể gặp những trường hợp nào?
6. Vì sao caller phải drain/close ofInputStream body nếu muốn giải phóng resources?
7. Socket.setKeepAlive(true) trên raw Socket có cấu hình sockets của HttpClient không?
8. So sánh HTTP/2 PING, WebSocket Pong và application ACK.
9. Vì sao HTTP/3/QUIC không áp dụng TCP SO_KEEPALIVE?
10. Một /ready trả 503 trong khi GET /resource vẫn 200. Bạn đánh dấu trạng thái nào là unhealthy?
11. Thiết kế heartbeat interval, timeout, threshold, jitter để phát hiện sự cố mà không tạo health traffic storm.
12. Chạy KeepAliveLayersDemo trên Java 17+ và giải thích từng dòng; quan sát nào không được Java API bảo đảm?
13. Chuyển health predicate từ HTTP 204 thành HTTP 200 + JSON ready flag; cần xác thực body thế nào?
14. Nếu 20.000 clients ping 5 giây/lần thì trung bình bao nhiêu heartbeat requests per second? Xử lý spike như thế nào?
15. Đề xuất một health check hợp lý khi service cần DB/queue nhưng không muốn làm truy vấn nặng.
16. Một POST đã commit nhưng response bị mất: TCP keepalive hay heartbeat xác định được business outcome không? Thiết kế idempotency.
17. Với SSE kết nối còn mở nhưng không có events, theo dõi liveness ở tầng nào?
18. Thiết kế metrics tách transportError, httpStatus, actualVersion, heartbeatReady, lastSuccess.

## 17. Checklist trước khi triển khai

- [ ] Biết mình đang cần TCP peer probing, HTTP reuse hay readiness?
- [ ] Không dùng SO_KEEPALIVE để thay request/heartbeat timeout?
- [ ] Bật SO_KEEPALIVE đúng Socket khi thật sự cần và hiểu platform timers?
- [ ] Không giả định HttpClient tự dùng SO_KEEPALIVE của Socket khác?
- [ ] Hiểu HTTP/1.1 persistent mặc định, Connection: close và body framing?
- [ ] Tái sử dụng HttpClient nhưng không assume luôn một TCP socket?
- [ ] Đọc/đóng streaming response bodies đúng contract?
- [ ] Phân biệt HTTP/2, HTTP/3 reuse và TCP keepalive?
- [ ] Health endpoint có success predicate và kiểm tra đúng dependencies?
- [ ] Có interval, deadline, fail/recovery thresholds, jitter và non-overlap?
- [ ] Có cleanup task/scheduler khi shutdown?
- [ ] Biết proxy/LB/NAT có idle policy và TCP hops khác nhau?
- [ ] Phân loại HTTP 503/401/429 khác DNS/TCP/TLS IOException?
- [ ] Có idempotency/retry policy cho requests tạo side effects?
- [ ] Có đo TCP, HTTP pooling và application readiness tách biệt?
- [ ] Đã test app not ready trong khi TCP/HTTP còn hoạt động?

**Kết luận:** **TCP keep-alive** thăm dò idle TCP path ở kernel. **HTTP keep-alive** là **khả năng tái sử dụng kết nối** để gửi nhiều requests hiệu quả. **Heartbeat ứng dụng** chủ động hỏi một điều kiện **readiness/liveness** qua protocol có **timeout và policy**. Ba cơ chế có thể dùng cùng nhau nhưng không có quan hệ tương đương: **TCP ACK tốt** không bảo đảm **HTTP handler chạy**, **HTTP reuse tốt** không bảo đảm **business service ready**, và **heartbeat ready ở thời điểm hiện tại** không hứa mọi request tương lai đều thành công.

### Tài liệu chính thức

- [Java SE 17: Socket.setKeepAlive](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java SE 17: StandardSocketOptions.SO_KEEPALIVE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html)
- [Java SE 17: ExtendedSocketOptions TCP_KEEPIDLE/TCP_KEEPINTERVAL/TCP_KEEPCOUNT](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html)
- [Java SE 17: HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17: HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java SE 17: HttpServer (test fixture)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [RFC 9293 — TCP Keep-Alives, section 3.8.4](https://www.rfc-editor.org/rfc/rfc9293)
- [RFC 9112 — HTTP/1.1 Persistence, section 9.3](https://www.rfc-editor.org/rfc/rfc9112)
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114)
- [RFC 6455 — WebSocket](https://www.rfc-editor.org/rfc/rfc6455)
