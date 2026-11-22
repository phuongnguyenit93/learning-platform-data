# Giới hạn số kết nối, số yêu cầu và bộ nhớ đệm đang sử dụng

*Java Advance – networking · Nhóm: Độ tin cậy · Java 17+*

## 1. Vì sao ba giới hạn này cần được thiết kế cùng nhau?

Một ứng dụng networking không chỉ cần **xử lý được request** mà phải **tiếp tục hoạt động khi request tăng đột biến, phía bên kia chậm hoặc dữ liệu không đáng tin**. Các tài nguyên cốt lõi thường bị tiêu thụ là:

1. **Kết nối đang mở**: socket/TCP connection, file descriptor, TLS state, idle keep-alive connection và native network buffers.
2. **Yêu cầu đang xử lý hoặc chờ xử lý**: HTTP request, tác vụ trong thread pool, futures, queue entries, database queries và downstream calls.
3. **Bộ nhớ đệm (buffers) đang được giữ**: `byte[]`, `ByteBuffer` heap/direct, request/response body đã gom, socket send/receive buffers, buffer pools và application caches.

**Giới hạn một loại tài nguyên không tự giới hạn hai loại còn lại.** Một TCP connection HTTP/2 có thể chứa nhiều HTTP streams/requests đồng thời; một HTTP request tải file lớn có thể giữ nhiều MiB buffer; và một HTTP/1.1 keep-alive connection có thể tồn tại lâu **khi không có request nào đang xử lý**.

~~~text
                          Networking service
                                  |
    +-----------------------------+-------------------------------+
    |                             |                               |
    v                             v                               v
Connection budget            Request budget                 Memory budget
open TCP/TLS sockets         in-flight operations           retained buffer bytes
idle connections             request queues                 heap + direct memory
file descriptors             worker threads                 body size and caches
    |                             |                               |
    v                             v                               v
max connections              max active + queue             max bytes + pool sizes
idle timeout                 overload admission              per-request byte quota
backlog (pending only)       deadline + cancel              release in finally
    |                             |                               |
    +-----------------------------+-------------------------------+
                                  |
                     Bounded and observable load
~~~

Ba mục tiêu vận hành:

- **Ổn định:** tải vượt khả năng được từ chối/điều tiết có kiểm soát, thay vì hết heap, cạn socket hoặc tạo hàng đợi không giới hạn.
- **Công bằng:** một client/tenant/request lớn không chiếm hết tài nguyên của tất cả người dùng khác.
- **Dự đoán được:** có giới hạn, thời hạn chờ, metric và cách trả lỗi cụ thể; không biến overload thành “server cứ đứng im”.

Đây là kiến thức về **resource budgets và backpressure**. Không có một cấu hình Java duy nhất thay thế mọi giới hạn, đặc biệt khi phối hợp TCP, HTTP/1.1, HTTP/2, `HttpServer`, `HttpClient`, NIO và thread pools.

## 2. Phân biệt các đại lượng trước khi đặt hạn mức

| Đại lượng | Đơn vị | Tính gì? | Không tương đương |
|---|---|---|---|
| Open TCP connections | Kết nối/socket | TCP connections đang mở, gồm active và idle | Số request đang chạy |
| Accepted connections | Kết nối | Kết nối được application chấp nhận từ accept loop | Số request đã hoàn tất |
| Backlog | Pending connections | Yêu cầu kết nối đang chờ được accept trong kernel | Max active connections |
| Idle keep-alive connections | Kết nối | Kết nối không có request đang xử lý nhưng giữ để reuse | Request queue |
| In-flight HTTP requests | Request | Request đã được nhận/gửi nhưng chưa hoàn tất theo contract | TCP connection count |
| Queued requests/tasks | Phần tử | Tác vụ đã chấp nhận nhưng chưa được executor bắt đầu | Active worker threads |
| Request rate | Request/giây | Tốc độ đến trong một khoảng thời gian | Concurrency |
| Heap buffer usage | Byte | `byte[]`, heap `ByteBuffer` và các object còn được tham chiếu | Direct memory |
| Direct buffer usage | Byte | Buffer cấp bằng `ByteBuffer.allocateDirect` / native pooling | `Runtime.totalMemory()` |
| Cached response/data | Byte / entry | Dữ liệu giữ lại để tái sử dụng (cache thật) | I/O buffer đang hoạt động |

**Ba tình huống phản ví dụ:**

- Chỉ có **1 HTTP/2 connection**, nhưng **100 requests** có thể đang được multiplex trên connection đó. Giới hạn socket = 1 không đặt trần request = 1.
- Chỉ có **5 requests**, mỗi request gom response **50 MiB** thành `byte[]` → riêng payload đã có thể giữ **250 MiB**, chưa tính bản sao, JSON objects, TLS và native buffers.
- Có **500 keep-alive connections** nhưng **0 active requests**. Thread xử lý request có thể rảnh nhưng file descriptor và connection buffers vẫn bị giữ.

Vì thế mỗi tài nguyên cần **một chỉ số đo và một admission policy độc lập**.

## 3. Mô hình ngân sách: active, waiting và retained bytes

Một mô hình đơn giản cho server:

~~~text
Incoming connections (kernel listen backlog)
            |
            v
Connection accepted + socket lifetime
            |
            v
HTTP request parsed
            |
            v
Admission? active requests < limit
            |
       +----+----+
       |         |
      yes        no
       |         |
       v         v
bounded worker   503 / 429 / close theo policy
       |
       v
reserve request buffers / downstream slots
       |
       v
business processing + response streaming
       |
       v
close streams, release request slot, release memory reservation
~~~

Khi thiết kế limits, hãy hỏi cả **đỉnh** lẫn **thời gian giữ tài nguyên**. Ví dụ 100 in-flight requests có latency trung bình 20 ms là một tải rất khác với 100 requests mỗi request chờ downstream 30 giây.

### 3.1. Các bất biến cần giữ

~~~text
0 <= openConnections <= configuredConnectionBudget
0 <= activeRequests   <= configuredRequestBudget
0 <= queuedTasks      <= configuredQueueCapacity
0 <= reservedBytes    <= configuredBufferBudget
~~~

Đây là **mục tiêu của tầng policy/application**, không tự động đúng chỉ vì đặt `ServerSocket.bind(backlog)` hoặc `ThreadPoolExecutor.maximumPoolSize`. Một request có thể tiêu thụ nhiều loại buffer cùng lúc, còn socket có thể vẫn mở sau request.

Một phép kiểm soát hợp lý dùng:

- **Counted permit** (ví dụ `Semaphore`) cho active requests hoặc các connection được application quản lý.
- **Bounded `BlockingQueue`** cho tasks chờ.
- **Byte reservation** trước khi allocate/giữ buffer.
- **Deadlines/idle timeouts** để yêu cầu không giữ permit mãi.
- **Release trong `finally`** hoặc callback terminal (success, failure, cancel), kể cả exception.

## 4. Giới hạn số kết nối: đừng nhầm với backlog

### 4.1. ServerSocket.bind(backlog) chỉ là hàng đợi kết nối chờ accept

~~~java
// Trích đoạn: socket server TCP thuần, không phải toàn bộ server.
ServerSocket listener = new ServerSocket();
listener.bind(new InetSocketAddress("127.0.0.1", 8080), 64);
~~~

Tham số **`backlog = 64`** yêu cầu hệ điều hành dành hàng đợi cho **kết nối đang chờ được accept**. Javadoc Java 17 nói đây là requested maximum và **hành vi chính xác phụ thuộc implementation/OS**; OS có thể giới hạn hoặc bỏ qua giá trị.

**Backlog không phải:** giới hạn số socket đã được accept, giới hạn số HTTP requests, số threads, số file descriptors hoặc tổng RAM. Một server có thể accept hàng nghìn connections dù backlog chỉ 64 nếu nó liên tục rút khỏi queue.

| Giá trị | Điều bị tác động |
|---|---|
| `backlog` | Hàng đợi kết nối tới trước khi application accept |
| Active connection cap | Số connection đã mở/được quản lý |
| Socket read timeout | Thời gian đọc không tiến triển |
| Idle timeout | Thời gian cho phép connection không làm việc |
| Request concurrency cap | Số HTTP requests đang thực thi |
| Worker queue capacity | Số tasks đợi được executor nhận |

### 4.2. Giới hạn connection cho TCP server tự viết

Một accept loop có thể sử dụng `Semaphore` để hạn chế **số socket được xử lý cùng lúc**:

~~~java
// Trích đoạn ý tưởng; serverSocket, workerPool, processSocket đã được cấu hình.
// Không phải chương trình Java độc lập.
Semaphore connectionSlots = new Semaphore(100);

for (;;) {
    Socket socket = serverSocket.accept();
    if (!connectionSlots.tryAcquire()) {
        socket.close();                 // Policy: từ chối kết nối mới.
        continue;
    }
    try {
        workerPool.execute(() -> {
            try (Socket owned = socket) {
                processSocket(owned);  // Đọc/ghi với timeout + giới hạn bytes.
            } catch (IOException ex) {
                // Log đã lọc thông tin và cập nhật error metrics.
            } finally {
                connectionSlots.release();
            }
        });
    } catch (RejectedExecutionException rejected) {
        socket.close();
        connectionSlots.release();      // Không để mất permit nếu chưa chạy task.
    }
}
~~~

Đây là **mẫu cho blocking socket server**. Nếu giữ socket trong queue nhưng tính permit ngay khi accept, permit bao gồm cả connections đang chờ xử lý; nếu muốn giới hạn chính xác active vs accepted/queued, phải tách counters. Với asynchronous NIO, không cần một thread cho mỗi connection, nhưng vẫn cần connection budget và timeout.

**Lưu ý:** đóng TCP socket thô không trả HTTP 503 có cấu trúc. Nếu yêu cầu HTTP đã parse và server có khả năng trả response, phản hồi 503 ngắn thường tốt hơn. Một connection đã được accept nhưng không đủ worker có thể không có nơi để xử lý HTTP ngay; cần thêm admission ở ingress/reverse proxy hoặc handler.

### 4.3. OS file descriptors và cổng nguồn

Mỗi socket thường tiêu thụ file descriptor/handle. Một ứng dụng còn mở files, pipes, database connections, TLS sessions và DNS resources. Nếu mở quá nhiều socket sẽ có nguy cơ:

- `Too many open files` / `SocketException`.
- Cạn ephemeral source ports ở phía client, đặc biệt khi tạo kết nối mới liên tục hoặc TIME_WAIT nhiều.
- Bộ nhớ kernel socket buffers và native TLS buffers phình to.
- Nhiều idle connections giữ tài nguyên dù không có active requests.
- Các connections chậm/half-open giữ slot nhiều phút.

Bởi vậy max connections cần đi kèm **keep-alive/idle policy, socket timeout, graceful close và monitoring**. Tăng OS file descriptor limit chỉ xử lý một nút thắt, không thay thế giới hạn của ứng dụng.

## 5. Cấu hình connection cap trong JDK HttpServer

`com.sun.net.httpserver.HttpServer` của Java 17 cho phép chỉ định backlog khi tạo/bind và executor khi xử lý request:

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080),
        64  // TCP pending accept backlog, KHÔNG phải max open connections
);
server.setExecutor(workers);           // Phải đặt trước server.start().
server.start();
~~~

Đây là **trích đoạn**: `workers` cần được tạo; muốn giới hạn thread/queue, xem phần executor bên dưới.

Theo *Oracle Java 17 Java Networking* dành cho default JDK implementation, có các **JDK-specific system properties**:

| Java system property (JDK 17 implementation) | Mô tả theo tài liệu | Điều KHÔNG bảo đảm |
|---|---|---|
| `jdk.httpserver.maxConnections` | Số **open connections** tối đa; gồm active và idle; 0/âm là không áp giới hạn | Không phải in-flight request cap |
| `sun.net.httpserver.maxIdleConnections` | Trần **idle connections** được giữ | Không giới hạn active connections |
| `sun.net.httpserver.idleInterval` | Thời gian connection được giữ idle (giây) | Không phải overall request deadline |
| `sun.net.httpserver.maxReqHeaders` | Số request header fields tối đa | Không giới hạn response body |
| `sun.net.httpserver.maxReqHeaderSize` | Kích thước request headers tối đa | Không giới hạn số request |
| `sun.net.httpserver.maxReqTime` | Thời gian giới hạn cho giai đoạn nhận request theo JDK implementation | Không phải business processing deadline độc lập |
| `sun.net.httpserver.maxRspTime` | Thời gian giới hạn cho giai đoạn response theo JDK implementation | Không thay thế downstream timeout |
| `sun.net.httpserver.drainAmount` | Số byte request chưa đọc tối đa mà server thử discard để có thể reuse connection | Không phải max request body của ứng dụng |

Theo tài liệu JDK 17, `jdk.httpserver.maxConnections` mặc định là `-1` (không giới hạn được áp bởi property này). Các giá trị mặc định của những `sun.net.httpserver.*` là **chi tiết triển khai cụ thể phiên bản**; không thiết kế service với giả định tất cả Java vendors/versions sẽ hành xử giống nhau.

Ví dụ cấu hình ở JVM startup:

~~~bash
java -Djdk.httpserver.maxConnections=200 \
     -Dsun.net.httpserver.maxIdleConnections=50 \
     -Dsun.net.httpserver.idleInterval=30 \
     -jar your-server.jar
~~~

`your-server.jar` là artifact minh họa, không đi kèm bài. Trên Windows, có thể truyền các tham số `-D` tương tự trên **một dòng**. Kiểm tra JDK thực tế và thử tải trước khi áp dụng trong production: những properties này **không phải setters portable của lớp `HttpServer`**, và cách xử lý khi đạt cap phụ thuộc implementation.

**Không dùng `jdk.httpserver.maxConnections` như thay thế cho request concurrency cap.** HTTP keep-alive cho phép nhiều requests tuần tự trên cùng socket, và một request có thể giữ nhiều byte memory/worker resources.

## 6. Client-side: giới hạn open connection KHÁC giới hạn request

`java.net.http.HttpClient` (Java 11+, có trong Java 17) dùng chung client cho nhiều request và có connection reuse. `HttpClient.Builder` công khai những options như `version`, `connectTimeout`, `executor`, `proxy` và `followRedirects`, nhưng **không có public setter portable `maxConnections` hoặc `maxConcurrentRequests` trong Java 17 builder**.

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

**Câu quan trọng:** `.executor(myPool)` là cấu hình executor cho asynchronous/dependent tasks. **Không được coi kích thước của pool đó là trần chắc chắn đối với số TCP connections hay số requests đang được mạng xử lý**. Muốn giới hạn in-flight HTTP requests do chính ứng dụng phát, thêm admission permit ở tầng gọi API.

### 6.1. Các JDK-specific HTTP client properties hay bị hiểu nhầm

Oracle Java 17 *Java Networking* có:

| Property | Ý nghĩa chính xác theo tài liệu Java 17 | Cạm bẫy |
|---|---|---|
| `jdk.httpclient.connectionPoolSize` | Trần số connections trong **HTTP/1.1 keep-alive cache**; 0 nghĩa unbounded **cache** | **Không phải** max active connections hoặc global in-flight request cap |
| `jdk.httpclient.keepalive.timeout` | Giới hạn thời gian giữ idle HTTP/1.1 connection trong keep-alive cache | Không phải tổng thời gian một request |
| `jdk.httpclient.maxstreams` | Số **HTTP/2 streams tối đa mỗi connection** theo implementation (JDK 17 docs ghi 100) | Không phải trần global số requests across all connections |
| `jdk.httpclient.bufsize` | Kích thước một số internal allocated buffers (JDK 17 docs ghi mặc định 16 KiB) | Không phải tổng memory budget của mọi response |
| `jdk.httpclient.receiveBufferSize` | Socket receive buffer size theo JDK/OS | Không giới hạn application body accumulation |

Một ví dụ dễ sai là:

~~~bash
java -Djdk.httpclient.connectionPoolSize=8 -jar your-client.jar
~~~

Lệnh này **không bảo đảm rằng Java chỉ mở tối đa tám TCP connections đang hoạt động**. Nó mô tả số connection HTTP/1.1 được **giữ trong keep-alive cache** khi idle. Không đánh đồng cache connection count với active socket count.

**Quan trọng khi bảo trì:** đây là properties của default JDK implementation, không phải contract portable từ `HttpClient.Builder`; xác nhận JDK/runtime version và quan sát metrics. Không dựa vào tên property để suy ra semantics ngoài tài liệu.

### 6.2. HTTP/1.1 và HTTP/2 có quan hệ request–connection khác nhau

~~~text
HTTP/1.1 (đơn giản hóa):
  Connection A --> Request A đang xử lý
  Connection B --> Request B đang xử lý
  Connection C --> idle keep-alive

HTTP/2:
  Connection A --> Stream 1 / Request A
               --> Stream 3 / Request B
               --> Stream 5 / Request C
               --> ... multiplexed streams
~~~

HTTP/2 còn có settings/flow control và server-advertised `SETTINGS_MAX_CONCURRENT_STREAMS`. Cả HTTP/2 và Java implementation đều có trần stream/cửa sổ flow-control, nhưng **chúng không thay thế business request admission** của ứng dụng. Một request có thể có nhiều redirects/retries, hoặc giữ response streaming body chưa được tiêu thụ; cần xác định permit bao phủ giai đoạn nào.

## 7. Giới hạn in-flight requests bằng Semaphore

`java.util.concurrent.Semaphore` quản lý số permits; `tryAcquire()` trả `false` ngay khi hết slot, không tích tụ vô hạn các thread bị chặn. Đây là công cụ phổ biến cho **bulkhead / concurrency limit**.

~~~java
Semaphore requestSlots = new Semaphore(50, true);

if (!requestSlots.tryAcquire()) {
    // Server có thể trả 503 ngắn/Retry-After;
    // client có thể fail-fast hoặc queue vào hàng đợi hữu hạn.
    return;
}

try {
    processOneRequest();
} finally {
    requestSlots.release();
}
~~~

Đây là **trích đoạn**, không phải chương trình độc lập. Với server, chỉ acquire sau khi request được route vào handler và trước công việc tốn kém; với client, acquire **trước khi phát** `sendAsync` để tránh tạo hàng ngàn requests/futures khi đã quá tải.

### 7.1. Thế nào là “request đang xử lý”?

Bạn phải định nghĩa rõ thời điểm nhận/nhả permit:

- Server: từ lúc request được admitted tới lúc **business work và response body** hoàn tất/aborted.
- Client dùng `BodyHandlers.ofString()/ofByteArray()`: khi future response hoàn tất **thành công**, subscriber đã xử lý full body theo handler; vẫn có thể còn business processing downstream.
- Client dùng `BodyHandlers.ofInputStream()/ofLines()/ofPublisher()`: future `HttpResponse` có thể hoàn tất **sớm sau headers**, **chưa tới EOF/onComplete**. **Không nhả permit chỉ vì future trả `HttpResponse<InputStream>`** nếu mục tiêu là giới hạn request exchange tới khi body tiêu thụ hết.
- Với streaming phải nhả permit tại **EOF/close/onComplete/onError/cancel** theo ownership rõ ràng.
- Retry/redirect có thể tạo thêm HTTP exchanges; policy cần giới hạn cả tổng số in-flight tasks và từng attempt nếu mục tiêu là kiểm soát load.

**Lỗi nguy hiểm:** gọi `release()` hai lần từ hai callback (ví dụ timeout và success race) làm số permits vượt trần. Dùng một ownership token/atomic terminal state để bảo đảm chỉ release một lần. Ngược lại, quên release khi exception/cancel sẽ làm service dần ngừng nhận request dù không còn tải.

### 7.2. Fairness và tải thực tế

`Semaphore(max, true)` hỗ trợ fairness cho các thread đang đợi, nhưng fairness có overhead và **`tryAcquire()` không bảo đảm tính công bằng y hệt `acquire()`** theo tài liệu API. Cần cân nhắc starvation, priority, per-tenant fairness và throughput.

Trong server overload, `tryAcquire` hữu ích khi muốn **fail fast**. Nếu muốn chờ slot, dùng `tryAcquire(timeout, unit)` với **deadline rất rõ**; không dùng `acquire()` vô thời hạn cho hàng ngàn server threads vì sẽ chuyển overload thành thread starvation.

## 8. Giới hạn hàng đợi và worker threads

`Executor` điều phối tasks. Số threads tối đa và số tác vụ **đang đợi** cần được thiết lập **riêng**. Một code phổ biến:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);
~~~

Cố định số worker threads là **8**, nhưng queue nội bộ của `newFixedThreadPool` có thể **không giới hạn số tasks đang chờ** theo giới hạn do ứng dụng đặt. Dưới tải đột biến, queue dài có thể giữ request objects, CompletableFutures và body data trong memory.

Muốn queue hữu hạn, dùng `ThreadPoolExecutor` với `ArrayBlockingQueue`:

~~~java
ThreadPoolExecutor workers = new ThreadPoolExecutor(
        8, 8,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(32),
        new ThreadPoolExecutor.AbortPolicy());
~~~

Theo Javadoc, lúc cả workers và queue đều full, `AbortPolicy` ném `RejectedExecutionException` cho task mới.

| Thành phần | Ví dụ | Giới hạn cái gì? |
|---|---|---|
| `corePoolSize` | 8 | Số worker core |
| `maximumPoolSize` | 8 | Số worker tối đa |
| `ArrayBlockingQueue<>(32)` | 32 | Số tasks chờ trong queue |
| `AbortPolicy` | Reject | Hành vi khi executor không còn sức chứa |
| `Semaphore(16)` | 16 | Số requests **được admit** theo policy riêng |
| `HttpServer.create(address, 64)` | 64 | Backlog **pending TCP connections** |

**Không cộng 8 + 32 rồi tuyên bố “server bảo đảm xử lý tối đa 40 HTTP requests”**: executor có thể phục vụ các tasks nội bộ, mỗi task có thể bao nhiều bước, và server có thể accept connections trước khi task được xử lý. Đây là các tầng của hệ thống, phải đo đúng hiện thực.

### 8.1. RejectedExecutionException không bảo đảm HTTP 503

Nếu JDK `HttpServer` đưa một task vào executor đã full, executor có thể **reject ở tầng dispatch**, trước khi `HttpHandler.handle` được chạy. Khi ấy handler không có cơ hội tự viết status 503. Bởi vậy:

- Dùng **handler-level admission** (`Semaphore.tryAcquire`) khi muốn chủ động trả `503`.
- Dùng **bounded worker queue** để bảo vệ bộ nhớ của executor.
- Có thể cần **reverse proxy/ingress** hoặc HTTP server framework hỗ trợ overload handling nếu muốn kiểm soát cả thời điểm trước khi handler được gọi.
- Không giả định executor rejection được chuyển tự động thành `503 Service Unavailable` với header `Retry-After`.

### 8.2. Đặt executor trước khi khởi động server

Javadoc Java 17 `HttpServer.setExecutor` yêu cầu cấu hình trước `server.start()`. Nếu không set executor, default executor có thể dùng thread được tạo từ `start()` để xử lý requests, không thích hợp để suy ra concurrency/throughput production.

~~~java
HttpServer server = HttpServer.create(address, 64);
server.createContext("/work", handler);
server.setExecutor(workers); // Trước start
server.start();
~~~

Chọn kích thước pool theo workload: CPU-bound khác blocking I/O-bound. **Không tăng worker count vô hạn để “tăng throughput”**: tăng thread stacks, context switching, queues và downstream saturation; kết hợp timeouts, admission và resource budget.

## 9. Trả overload có cấu trúc: 503, 429 và Retry-After

Giới hạn tài nguyên không chỉ là `throw` hoặc đóng socket, mà còn là quyết định **client sẽ nhìn thấy gì**.

| Tình huống | Response thường phù hợp | Phải chú ý |
|---|---|---|
| Server/service tạm không đủ khả năng phục vụ | `503 Service Unavailable` | Có thể kèm `Retry-After` |
| Một người dùng/API key vượt rate quota riêng | `429 Too Many Requests` | Có thể kèm `Retry-After` |
| Request body vượt giới hạn | `413 Content Too Large` | Đừng đọc/giữ toàn body trước khi từ chối |
| Headers không hợp lệ/quá lớn | `400` hoặc từ chối ở protocol layer | Có thể bị chặn trước handler |
| Service không thể xử lý vì upstream down | `502/503/504` tùy semantics gateway | Không giấu mọi lỗi vào 200 |
| Server hard cap ở TCP accept/OS layer | Connection refused/reset/timeout | HTTP status có thể **không được phát** |

Mẫu trả 503 trong `HttpExchange`:

~~~java
byte[] response = "BUSY".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set("Retry-After", "1");
exchange.getResponseHeaders()
        .set("Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(503, response.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(response);
}
~~~

**`Retry-After: 1` là một gợi ý chờ 1 giây, không bảo đảm server đã đủ capacity khi hết 1 giây.** Client cần exponential backoff + jitter, total deadline, retry budget; chỉ retry khi request idempotent hoặc có idempotency key/policy đúng. Nếu mọi client retry cùng lúc, hệ thống có thể bị **retry storm**.

**Fail-fast có chủ đích thường tốt hơn** việc giữ request đến khi timeout hàng phút và tiêu thụ thêm buffer/threads. Nhưng nếu chặn quá mạnh có thể gây starvation: hãy đo error rate, queue wait, p95/p99 latency và điều chỉnh capacity theo SLO.

## 10. Giới hạn bộ nhớ đệm: byte quota, không chỉ số buffer

Một buffer có thể là:

- `byte[]` nằm trong **Java heap**.
- `ByteBuffer.allocate(n)` tạo heap buffer.
- `ByteBuffer.allocateDirect(n)` tạo direct buffer, thường có storage **ngoài heap được GC quản lý trực tiếp**; direct memory vẫn làm tăng footprint của process.
- `ByteBuffer.wrap(existingArray)` chỉ bọc một array hiện có; có thể **chia sẻ cùng backing storage**.
- `ByteBuffer.slice()/duplicate()` tạo views chia sẻ storage, nên **không được cộng toàn bộ capacity của mọi view như dữ liệu độc lập**.
- Socket kernel send/receive buffers, TLS implementation buffers, compressed/decompressed representations, cached bodies, decoder/parser objects.

Một quota đếm **số buffers** không đủ: 100 buffers × 1 KiB và 100 buffers × 8 MiB có mức tiêu thụ rất khác nhau. Nên đo **retained bytes theo loại**, cùng với buffer count, allocation rate và peak.

### 10.1. Bộ nhớ đệm (buffer) khác bộ nhớ cache

| Thuật ngữ | Mục đích | Giới hạn phù hợp |
|---|---|---|
| Network read/write buffer | Giữ bytes tạm thời trong khi truyền/parse | Concurrent buffers × size; quota bytes |
| Buffer pool | Tái sử dụng blocks để giảm allocation | Maximum retained bytes, idle count, eviction |
| HTTP response body collector | Gom body để xử lý | Per-response max bytes + concurrent total |
| HTTP cache | Giữ responses để phục vụ lại | Max entries/bytes + TTL/eviction |
| Kernel socket buffers | Hệ điều hành duy trì send/receive queues | OS/socket settings và số connections |
| Direct memory | Native/off-heap storage cho direct buffers | JDK-specific limit + BufferPoolMXBean metrics |

Bài này tập trung **buffers đang dùng**, không biến cache HTTP thành một thành phần bắt buộc. Nhưng nếu ứng dụng có response cache thực, phải **đặt riêng max cached bytes và eviction policy**. Một cache có giới hạn 1.000 entries nhưng mỗi entry 10 MiB vẫn có thể giữ gần 10 GiB.

### 10.2. Heap và direct không thể quy hết vào -Xmx

`-Xmx` đặt trần heap, **không phải tổng RSS của process**. Direct buffers, thread stacks, JVM metaspace, native libraries, socket buffers và overhead container đều có thể nằm ngoài giới hạn heap.

`ByteBuffer.allocateDirect` có thể có chi phí allocate/free cao hơn heap buffer; Javadoc khuyên ưu tiên cho buffers lớn/sống lâu và native I/O khi có **hiệu quả đo được**, không thay mọi `byte[]` bằng direct buffer.

JVM có `-XX:MaxDirectMemorySize` ở nhiều bản HotSpot, nhưng đây là option triển khai JVM, **không phải API portable giới hạn tổng memory của mọi thư viện, kernel socket và native allocations**. Kiểm tra JDK, container memory limit và memory metrics thay vì chỉ nhìn heap usage.

## 11. Reservation: đặt trước số byte rồi mới cấp phát

Nếu nhiều requests cùng tạo buffers lớn, chỉ kiểm tra kích thước **sau khi allocate** là quá muộn. Mẫu an toàn hơn:

~~~text
request cần 8 MiB
    |
    v
tryReserve(8 MiB)?
    |
    +-- false -> từ chối / chờ với deadline / stream sang disk
    |
    +-- true
           |
         allocate/borrow buffer
           |
         read/write/process
           |
         release buffer/reference
           |
         release(8 MiB) exactly once (finally)
~~~

Một counter quota có thể dùng `AtomicLong.compareAndSet`:

~~~java
// Trích đoạn class, bản hoàn chỉnh có trong demo ở phần dưới.
boolean tryReserve(int bytes) {
    if (bytes < 0) throw new IllegalArgumentException();
    for (;;) {
        long current = used.get();
        if (bytes > limit - current) return false;
        if (used.compareAndSet(current, current + bytes)) return true;
    }
}
~~~

Kiểm tra `bytes > limit - current` tránh cộng vượt giới hạn khi nhiều thread cùng lúc. **Reservation là lượng bộ nhớ theo logic ứng dụng đã hứa/đang quản lý**, không phải phép đo **heap đã được GC thu hồi**. Khi `release`, object có thể vẫn chưa bị GC; vì thế đo logical budget và actual process memory riêng.

### 11.1. Vì sao không đếm currentBuffers * standardBufferSize?

Các kích thước có thể thay đổi; view buffers chia sẻ underlying storage, pooled buffers có thể được trả vào pool nhưng vẫn giữ physical memory. Nếu một pool giữ 100 blocks × 64 KiB, ngay cả khi **0 active borrowers**, nó vẫn có thể giữ khoảng **6,25 MiB** block storage. Do đó cần hai counters:

- **Borrowed/reserved bytes:** blocks hiện thuộc về operations đang xử lý.
- **Retained pool bytes:** blocks chưa borrow nhưng pool vẫn giữ để reuse.

Nếu muốn quota theo **actual retained memory**, reserve khi pool **cấp block mới**, đừng release actual-memory counter chỉ vì trả block vào pool; release counter khi block thực sự bị eviction/freed. Nếu chỉ giới hạn **đồng thời sử dụng**, release ở lúc trả block là đúng, nhưng đó là một quota khác.

### 11.2. Tránh double-release và leaks

Một request có thể có nhiều terminal events: success, timeout, cancel, connection reset, handler exception. Nếu vừa `finally` vừa callback timeout cùng `release`, counter có thể âm hoặc permit tăng vượt max. Nếu exception xảy ra trước `release`, quota có thể “mất” mãi.

Dùng **ownership rõ ràng**, structured cleanup và trạng thái terminal exactly-once. Với stream/publisher, để permit sống đến lúc **body kết thúc/đóng**; không release ngay khi `HttpResponse<InputStream>` đã sẵn sau headers.

## 12. Áp giới hạn body và queue trước khi buffer phình to

### 12.1. Đếm bytes thực khi đọc request/response

`Content-Length` là metadata, không phải bảo đảm dữ liệu nhỏ và cũng có thể vắng mặt. Với chunked body hoặc dữ liệu nén, đếm bytes **thực đi qua pipeline**.

~~~java
// Trích đoạn: đọc stream có giới hạn, không tự gom body vô hạn.
long maxBytes = 1_000_000;
long count = 0;
byte[] block = new byte[8192];
for (int n; (n = input.read(block)) != -1;) {
    if (n > maxBytes - count) {
        throw new IOException("Body exceeds configured limit");
    }
    count += n;
    // Đưa đúng n byte sang parser/sink có backpressure.
}
~~~

Khi có `Content-Encoding: gzip`, phải phân biệt quota **bytes nén** và quota **bytes đã giải nén**: một payload nén nhỏ có thể bung ra rất lớn (decompression bomb). Tránh dùng `readAllBytes()` không giới hạn với HTTP body do bên ngoài điều khiển.

### 12.2. Queue item cũng giữ memory

Một queue chỉ có 1.000 entries vẫn có thể giữ nhiều GiB nếu mỗi entry kèm payload 5 MiB. Cần budget đồng thời theo:

- **Queue length**: số tasks.
- **Queued payload bytes**: lượng dữ liệu đang chờ.
- **Queue wait time**: request đã hết deadline thì bỏ trước khi bắt đầu work.
- **Per-tenant share**: một tenant không chiếm tất cả slots.

Không “giải quyết hết queue quá tải” bằng cách tăng queue length vô hạn. Điều đó chỉ kéo dài thời gian chờ và tăng memory pressure.

## 13. Ví dụ Java 17+ chạy được: request admission và buffer quota

Ví dụ hoàn chỉnh này minh họa **hai giới hạn độc lập** và tạo kết quả **deterministic** mà không cần `Thread.sleep`:

- Server `HttpServer` chạy trên `127.0.0.1`, có `ThreadPoolExecutor` **4 workers và queue 4 tasks**, backlog 8. Các con số chỉ là **cấu hình demo nhỏ**, không phải khuyến nghị production.
- Trong `HttpHandler`, `Semaphore(2)` chỉ chấp nhận **tối đa 2 request đang xử lý**. Hai request đầu được giữ bằng `CountDownLatch` để bảo đảm chúng vẫn đang active; request thứ ba nhận **`503 Service Unavailable` và `Retry-After: 1`**.
- Khi mở chốt, hai request đầu nhận `200 OK`. `finally` trả permits và giảm active counter.
- `BufferQuota` dùng `AtomicLong` đặt **16 byte logical reservation**. Sau khi reserve 12 byte, yêu cầu thêm 8 bị từ chối. Khi release 12 byte, reserve 8 được phép. Đây là *logical byte budget*, không phải phép đo RSS thực.
- Tất cả network connections đều loopback; không yêu cầu Internet hoặc thư viện bên ngoài JDK.

**Tạo file `ResourceBudgetDemo.java`:**

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
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class ResourceBudgetDemo {
    static final Semaphore REQUEST_SLOTS = new Semaphore(2, true);
    static final CountDownLatch STARTED = new CountDownLatch(2);
    static final CountDownLatch RELEASE = new CountDownLatch(1);
    static final CountDownLatch FINISHED = new CountDownLatch(2);
    static final AtomicInteger ACTIVE = new AtomicInteger();
    static final AtomicInteger MAX_ACTIVE = new AtomicInteger();

    static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        if (status == 503) {
            exchange.getResponseHeaders().set("Retry-After", "1");
        }
        exchange.sendResponseHeaders(status, payload.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(payload);
        }
    }

    static void handle(HttpExchange exchange) throws IOException {
        try {
            if (!REQUEST_SLOTS.tryAcquire()) {
                reply(exchange, 503, "BUSY");
                return;
            }
            int now = ACTIVE.incrementAndGet();
            MAX_ACTIVE.accumulateAndGet(now, Math::max);
            STARTED.countDown();
            try {
                if (!RELEASE.await(5, TimeUnit.SECONDS)) {
                    reply(exchange, 503, "DEADLINE");
                    return;
                }
                reply(exchange, 200, "OK");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                ACTIVE.decrementAndGet();
                REQUEST_SLOTS.release();
                FINISHED.countDown();
            }
        } finally {
            exchange.close();
        }
    }

    static class BufferQuota {
        final long limit;
        final AtomicLong used = new AtomicLong();

        BufferQuota(long limit) {
            if (limit < 0) throw new IllegalArgumentException();
            this.limit = limit;
        }
        boolean tryReserve(int bytes) {
            if (bytes < 0) throw new IllegalArgumentException();
            for (;;) {
                long current = used.get();
                if (bytes > limit - current) return false;
                if (used.compareAndSet(current, current + bytes)) return true;
            }
        }
        void release(int bytes) {
            long now = used.addAndGet(-bytes);
            if (now < 0) throw new IllegalStateException("Double release");
        }
    }

    static void await(CountDownLatch latch) throws Exception {
        if (!latch.await(5, TimeUnit.SECONDS)) throw new IOException("Deadline exceeded");
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor workers = new ThreadPoolExecutor(
                4, 4, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4),
                new ThreadPoolExecutor.AbortPolicy());
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 8);
        server.createContext("/work", ResourceBudgetDemo::handle);
        server.setExecutor(workers);
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/work");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();
            HttpRequest req = HttpRequest.newBuilder(uri).GET()
                    .timeout(Duration.ofSeconds(5)).build();

            CompletableFuture<HttpResponse<String>> first = client.sendAsync(
                    req, HttpResponse.BodyHandlers.ofString());
            CompletableFuture<HttpResponse<String>> second = client.sendAsync(
                    req, HttpResponse.BodyHandlers.ofString());

            await(STARTED);
            HttpResponse<String> overloaded = client.send(
                    req, HttpResponse.BodyHandlers.ofString());
            System.out.println("overloadStatus=" + overloaded.statusCode());
            System.out.println("retryAfter=" +
                    overloaded.headers().firstValue("Retry-After").orElse("missing"));

            RELEASE.countDown();
            System.out.println("acceptedStatuses=" +
                    first.get(5, TimeUnit.SECONDS).statusCode() + "," +
                    second.get(5, TimeUnit.SECONDS).statusCode());
            await(FINISHED);
            System.out.println("maxInFlight=" + MAX_ACTIVE.get());
            System.out.println("requestSlotsRestored=" +
                    REQUEST_SLOTS.availablePermits());

            BufferQuota memory = new BufferQuota(16);
            boolean firstReserve = memory.tryReserve(12);
            System.out.println("reserve12=" + firstReserve);
            if (firstReserve) {
                byte[] bytes = new byte[12];
                try {
                    System.out.println("reserve8WhileUsed=" +
                            memory.tryReserve(8));
                    bytes[0] = 7;
                } finally {
                    memory.release(bytes.length);
                }
            }
            boolean secondReserve = memory.tryReserve(8);
            System.out.println("reserve8AfterRelease=" + secondReserve);
            if (secondReserve) {
                byte[] bytes = new byte[8];
                try {
                    bytes[0] = 9;
                } finally {
                    memory.release(bytes.length);
                }
            }
            System.out.println("reservedBytesEnd=" + memory.used.get());
        } finally {
            RELEASE.countDown();
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17+**; `jdk.httpserver` là module chính thức trong JDK:

~~~bash
javac --release 17 --add-modules jdk.httpserver ResourceBudgetDemo.java
java --add-modules jdk.httpserver ResourceBudgetDemo
~~~

**Stdout đã kiểm chứng khi biên dịch `--release 17` và chạy trên OpenJDK 24:**

~~~text
overloadStatus=503
retryAfter=1
acceptedStatuses=200,200
maxInFlight=2
requestSlotsRestored=2
reserve12=true
reserve8WhileUsed=false
reserve8AfterRelease=true
reservedBytesEnd=0
~~~

### 13.1. Giải thích từng dòng output

| Kết quả | Điều được kiểm chứng |
|---|---|
| `overloadStatus=503` | Hai request đã có slot; request thứ ba không acquire được và bị reject có kiểm soát |
| `retryAfter=1` | Response overload có header hướng dẫn client trì hoãn retry |
| `acceptedStatuses=200,200` | Hai request đã được admitted hoàn tất thành công sau khi mở CountDownLatch |
| `maxInFlight=2` | Handler đã ghi nhận tối đa hai admitted requests đang active |
| `requestSlotsRestored=2` | Hai permits được release đúng sau khi handlers hoàn tất |
| `reserve12=true` | Reservation 12 byte còn nằm trong quota 16 byte |
| `reserve8WhileUsed=false` | 12 + 8 vượt quota 16 byte nên request mới bị từ chối |
| `reserve8AfterRelease=true` | Sau khi trả 12 byte, có đủ ngân sách để reserve 8 |
| `reservedBytesEnd=0` | Logical reservations trở lại 0 khi hai allocations kết thúc |

### 13.2. Vì sao dùng CountDownLatch thay Thread.sleep?

Nếu chỉ gửi ba request nhanh rồi đo concurrency, kết quả có thể khác theo scheduler và tốc độ máy: request đầu đôi khi đã hoàn tất trước khi request thứ ba đến. `CountDownLatch STARTED` đảm bảo **hai handlers đã acquire permits và đang đợi**; `RELEASE` ngăn chúng kết thúc trong lúc request thứ ba được xét. Nhờ vậy `503` và max active 2 không dựa vào phỏng đoán thời gian.

Thời hạn 5 giây chỉ là **test deadline để tránh treo** trong môi trường chạy không bình thường. Trên host rất chậm có thể cần điều chỉnh deadline; không dùng timeout 5 giây này làm một SLA production cố định.

### 13.3. Những giới hạn cố ý của demo

- **Không chứng minh max TCP connections.** Demo giới hạn **request đang xử lý**, không đếm sockets đang mở. Backlog 8 không phải active connection cap.
- `ThreadPoolExecutor` có bounded queue nhưng nếu task bị reject **trước handler**, JDK server không bảo đảm một HTTP 503; 503 của demo xuất phát từ **handler-level Semaphore**.
- Demo dùng **HTTP/1.1 loopback**, không kiểm thử HTTP/2 multiplexing, TLS, sockets từ Internet hoặc load balancer.
- `BufferQuota(16)` là mô phỏng logical reservation; nó không đo heap/GC/RSS và không tính backing storage của các object ngoài demo.
- Đầu ra `200`/`503` là status từ local handler. Khi server mất khả năng accept vì OS/socket overload, client có thể gặp connection error trước khi nhận được status.
- `workers.shutdownNow()` chỉ để cleanup test; production cần shutdown/drain chính sách đang xử lý, không dừng đột ngột các requests hợp lệ.

## 14. Client-side Semaphore: tránh tự tạo hàng ngàn futures

Ở phía HTTP client, đặt request admission **trước sendAsync**. Ví dụ:

~~~java
// Trích đoạn ý tưởng; client, request và requestSlots đã được tạo.
if (!requestSlots.tryAcquire()) {
    // Fail-fast hoặc đặt vào queue có giới hạn riêng.
    return;
}

try {
    CompletableFuture<HttpResponse<byte[]>> future = client.sendAsync(
            request, HttpResponse.BodyHandlers.ofByteArray());
    future.whenComplete((response, error) -> {
        requestSlots.release();
        // Ghi metrics; phân biệt HTTP 4xx/5xx với transport exception.
    });
} catch (RuntimeException setupFailure) {
    requestSlots.release(); // sendAsync không trả future: phải rollback.
    throw setupFailure;
}
~~~

Đây **chỉ là trích đoạn**. Trong implementation thật, phải bảo đảm ownership và exactly-once release khi callback đã được đăng ký (tránh double-release nếu có exception sau khi callback được thiết lập), xử lý cancel/timeouts, và tính cả downstream business work nếu permit được định nghĩa đến khi business hoàn tất.

Đặc biệt nếu dùng `BodyHandlers.ofInputStream()` thì future có thể hoàn tất **ngay sau headers**. Trong tình huống ấy callback `whenComplete` nhả slot **quá sớm** khi body chưa đọc hết. Cần gắn permit với vòng đời của stream, như một wrapper `InputStream` đóng/EOF giải phóng permit exactly once, hoặc giữ permit trong worker xử lý stream từ đầu đến cuối.

## 15. Đặt hạn mức bộ nhớ theo worst-case hợp lý

### 15.1. Ước tính từ kích thước và concurrency

Giả sử một service có:

- 100 requests có thể active.
- Mỗi request giữ tối đa 256 KiB **application buffer riêng**.
- Không có bản sao bổ sung trong ví dụ tính nháp này.

Ngân sách buffer riêng vào thời điểm đỉnh:

~~~text
100 requests x 256 KiB = 25,600 KiB ≈ 25 MiB
~~~

Đây **chỉ là ước tính phần buffer được tính**, không phải toàn bộ memory của service. Phải cộng TLS buffers, kernel socket buffers, request body, response body, decoder/JSON tree, queue elements, thread stacks, idle buffers, caches và JVM overhead. Nếu ứng dụng parse JSON thành object graph, memory có thể lớn hơn raw body nhiều lần.

### 15.2. Budget đa tầng

Một cấu hình minh họa:

| Budget | Ví dụ | Vì sao không quá lớn? |
|---|---|---|
| Open connections | 200 | Hạn chế sockets/file descriptors và idle memory |
| Active requests | 64 | Tránh quá tải CPU/downstream |
| Waiting requests | 128 | Chặn queue memory và queue latency |
| Body per request | 1 MiB | Tránh một request gây OOM |
| Total active buffer reservations | 32 MiB | Tránh cộng dồn nhiều body lớn |
| Retained idle buffer pool | 8 MiB | Tránh pool giữ native memory mãi |
| Request deadline | 5 giây | Giải phóng slots khi upstream kẹt |
| Idle connection timeout | Theo traffic profile | Thu hồi socket không dùng |

Các con số trên **không phải khuyến nghị mặc định**; cần đo workload, payload distributions, concurrent users, OS limits và SLO. Một service xử lý file 1 GiB theo streaming có thể cần per-body bytes *transferred* lớn nhưng per-request *in-memory buffer* nhỏ. Cần phân biệt quota body data tổng và quota bytes giữ trong RAM.

## 16. Monitoring: phải nhìn được cả ba loại tài nguyên

### 16.1. Đo connections

- Open connections **active + idle**.
- Connections đang accept/chờ backlog nếu OS hỗ trợ.
- TCP connection failures, resets, timeouts, TLS handshake failures.
- File descriptors/handles đang sử dụng so với OS limit.
- Connections theo origin/host/tenant, HTTP protocol version, keep-alive reuse rate.
- Socket states như ESTABLISHED/TIME_WAIT khi điều tra cạn ephemeral ports.

### 16.2. Đo requests

- In-flight requests và peak, histogram thời gian giữ permit.
- Queue length, queue wait duration, rejected tasks.
- 2xx/4xx/5xx riêng, đặc biệt `429`/`503`.
- RPS, success/error rate, p50/p95/p99 latency và downstream calls đang mở.
- Timeouts, cancels, retries, retry amplification; phân biệt HTTP status lỗi và network exception.
- Per-tenant/per-route in-flight quota để tránh một nhóm chiếm hết slots.

### 16.3. Đo memory/buffers

- Java heap used, committed, GC pauses, allocation rate.
- Native/direct buffer count, capacity và memory used.
- Buffer pool retained bytes vs borrowed/in-use bytes.
- In-memory request/response body bytes và queue payload bytes.
- Container RSS/working set, OOM-kill metrics; phân biệt heap/direct/OS memory.
- Leaked buffers hoặc ByteBuffer views còn giữ backing storage lớn.

Java 17 cung cấp `BufferPoolMXBean`:

~~~java
// Trích đoạn; cần import ManagementFactory và BufferPoolMXBean.
for (BufferPoolMXBean p : ManagementFactory.getPlatformMXBeans(
        BufferPoolMXBean.class)) {
    System.out.println(p.getName() + " count=" + p.getCount()
            + " capacity=" + p.getTotalCapacity()
            + " used=" + p.getMemoryUsed());
}
~~~

Theo Javadoc, đây là **ước tính** cho các buffer pools như `direct` hoặc `mapped`; `getMemoryUsed()` có thể là `-1` nếu không có ước tính. **Không cộng các số này và coi đó là mọi byte network memory**, vì kernel, JVM nội bộ và application arrays có cơ chế khác. Hãy dùng các metric này cùng heap/native metrics và application-owned quotas.

## 17. Bảo vệ hệ thống trước slow clients và slow upstream

Một client có thể mở connection rồi gửi bytes cực chậm (**slow request/Slowloris**), hoặc đọc response chậm. Một upstream có thể treo khiến request slot không được trả.

Các biện pháp cần phối hợp:

- **Connect timeout**: giới hạn giai đoạn kết nối.
- **Header/body read timeout**: giới hạn thời gian không có tiến độ.
- **Overall deadline**: giới hạn tổng thời gian một logical operation.
- **Maximum request body size**: giới hạn bytes đọc thực, kể cả chunked.
- **Minimum throughput/idle policy** khi phù hợp; tránh một byte mỗi vài giây giữ connection vô hạn.
- **Cancellation**: đóng stream/socket hoặc hủy subscription theo API.
- **Semaphore slots + queue budget**: tránh slow operations khiến mọi request chờ không giới hạn.
- **Circuit breaker/bulkhead theo downstream**: một API phụ thuộc chậm không chiếm toàn bộ ứng dụng.

**Không nhầm read timeout với overall deadline**: một server có thể liên tục gửi ít dữ liệu trước mỗi read timeout, khiến toàn bộ download kéo dài vô hạn. Cần tổng thời hạn riêng khi policy yêu cầu.

### 17.1. Thứ tự acquire tránh deadlock và overreservation

Nếu mỗi operation cần connection permit, request permit và byte quota, hãy định nghĩa **một thứ tự acquire nhất quán** và rollback khi tầng sau thất bại:

~~~text
admit request slot
    |
check/obtain connection capacity
    |
reserve buffer bytes
    |
perform I/O
    |
release memory -> connection lifecycle -> request slot
~~~

Ví dụ chỉ để giải thích: connection pool có thể tái sử dụng socket nên connection slot không nhất thiết thuộc một request, và release connection phải tuân vòng đời socket thật. **Không buộc mọi service dùng thứ tự cứng này**; mục tiêu là tránh giữ resource A vô hạn trong khi chờ B, tránh deadlock và đảm bảo rollback trên mọi failure path.

## 18. Load testing để kiểm tra giới hạn thật

Chỉ nhìn cấu hình không đủ. Hãy thử ít nhất các kịch bản:

| Test | Kỳ vọng |
|---|---|
| Requests ít hơn admission cap | Thành công bình thường, không reject |
| Requests đúng cap | Active counter không vượt giới hạn |
| Requests cao hơn cap | Reject/queue có kiểm soát, không OOM |
| Queue full | Task mới không tạo hàng đợi vô hạn; overload feedback quan sát được |
| Slow requests/body | Slots được release khi timeout/cancel/EOF đúng contract |
| Keep-alive idle lâu | Idle sockets được thu hồi theo policy |
| HTTP/2 nhiều streams trên một connection | Request count được giới hạn độc lập khỏi socket count |
| Body lớn hơn per-request quota | Bị chặn trước khi giữ quá nhiều memory |
| Nhiều buffers đồng thời | Tổng reservation không vượt budget |
| Buffer view/pool retention | Không đếm thiếu actual retained memory hoặc release logical quota sai |
| Client disconnect giữa response | Server không leak permit/buffer |
| Lỗi khi vừa allocate hoặc enqueue | Rollback đúng, không double release |
| 503 burst + client retries | Không tạo retry storm, hệ thống phục hồi theo backoff |
| Nhiều tenants/host routes | Không có tenant đơn lẻ chiếm toàn bộ slots |

Cần đo **throughput, p99 latency, rejection rate, queue latency, connection count, heap/direct memory và GC** trong cùng lượt thử. Nếu tăng queue làm p99 tăng mạnh mà throughput không tăng, đó là dấu hiệu **queue chỉ đang lưu overload**, không giải quyết bottleneck.

### 18.1. Không dùng một benchmark làm cấu hình cố định cho mọi workload

Dữ liệu cần biết trước khi đặt limits:

1. Average/p95/p99 request duration ở tải thực.
2. Phân phối kích thước request/response bodies.
3. Tỉ lệ streaming vs buffering.
4. Tỷ lệ keep-alive, HTTP/1.1 vs HTTP/2, số origins.
5. CPU core quota, memory limit, file descriptors và ephemeral port limits.
6. Downstream concurrency / database pool / remote service quotas.
7. SLO latency và mục tiêu overload error rate.

Thử bắt đầu với **budget thận trọng, queue hữu hạn, metric đầy đủ**, sau đó tăng dựa trên throughput và headroom. Không chỉ nhìn CPU thấp rồi tăng số request: service có thể đang chờ database/network hoặc đã hết direct memory.

## 19. Lỗi phổ biến

| Ngộ nhận / lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Backlog 100 nghĩa max 100 active sockets | Server vẫn có thể mở nhiều socket sau accept | Tách pending accept queue và active cap |
| Connection cap = request cap | HTTP/2 multiplex nhiều streams | Đếm in-flight requests riêng |
| `HttpClient.Builder.executor` là max HTTP connections | Network I/O không bị ràng buộc 1–1 với worker | Dùng application admission và observability |
| `jdk.httpclient.connectionPoolSize=8` nghĩa tối đa 8 active sockets | Property giới hạn **HTTP/1.1 idle keep-alive cache** | Không coi là total live socket limit |
| Tăng backlog sẽ tăng request throughput | Backlog chỉ lưu pending connections | Chữa bottleneck worker/downstream |
| `Executors.newFixedThreadPool(8)` đã bounded hoàn toàn | Queue chờ có thể không có cap | Dùng bounded queue + rejection |
| Chỉ hạn chế queue count, không hạn chế payload bytes | Queue giữ nhiều GiB | Byte quota cho queued bodies |
| `Semaphore.acquire()` vô thời hạn trong handlers | Tích tụ threads đang chờ | Fail fast hoặc timed acquire |
| Quên release khi exception | Permit leak, service ngừng nhận request | `finally`/terminal callback exactly once |
| Release hai lần trong cancel/success race | Active requests vượt trần | Ownership/atomic terminal state |
| Trả HTTP 200 dù overload | Client và monitoring tưởng success | 429/503 theo semantics |
| Assume mọi executor rejection thành 503 | Handler có thể chưa được gọi | Admission ở HTTP handler hoặc ingress |
| Chỉ đặt `-Xmx` là đã có tổng memory cap | Direct/native/kernel memory ngoài heap | Đo RSS/direct/heap riêng |
| `ByteBuffer.slice()` tạo block mới độc lập | Chia sẻ backing memory, retention/double count | Track owner của allocation gốc |
| Buffer pool được trả là memory đã freed | Pool vẫn giữ memory để reuse | Tách borrowed vs retained counters |
| Dùng `readAllBytes()` cho body untrusted | OOM/GC pressure | Per-body max + streaming |
| Dùng Content-Length làm quota duy nhất | Thiếu/giả mạo/chunked/nén | Đếm bytes đã đọc, giải nén có limit |
| Nhả client permit khi `HttpResponse<InputStream>` xuất hiện | Body vẫn chưa được tiêu thụ | Giữ đến EOF/close/onComplete |
| Retry mọi 503 ngay lập tức | Retry storm | Deadline, exponential backoff + jitter |
| Đóng socket mà nghĩ client luôn nhận 503 | TCP reject có thể không tạo HTTP response | Hiểu tầng reject trước/sau HTTP parse |
| Dựa vào số `maxstreams` để giới hạn global requests | Đó là per-connection HTTP/2 policy | Global concurrency admission riêng |

## 20. Checklist cho production

**Connections:** Có phân biệt active, idle và pending backlog? Open sockets ≤ budget? Có idle timeout và graceful cleanup? File descriptor/headroom có đủ? HTTP/2 streams được đo riêng? Client-side keep-alive cache có được cấu hình theo đúng semantics thay vì coi như connection concurrency cap?

**Requests:** Có active concurrency cap độc lập? Queue hữu hạn? Có 503/429 logic và retry/backoff policy? Có per-tenant fairness? Có deadlines/cancellation? Có release permits exactly once sau khi body xử lý xong, kể cả lỗi? Worker pool configuration có phản ánh CPU/downstream và không dùng queue unbounded?

**Buffers:** Có per-request body quota, global memory reservation và pool retention budget? Có phân biệt heap/direct/kernel, logical in-use vs physically retained? Có kiểm soát size sau decompression, ByteBuffer views và readAllBytes không giới hạn? Có metrics heap, direct BufferPoolMXBean, process RSS?

**Verification:** Đã load test overload, slow clients, HTTP/2 multiplexing, chunked bodies, retry storms, cancel/timeout, double-release và queue full? Khi ngắt giữa body, server/client có giải phóng socket/permit/buffer không? Metrics được gắn nhãn route/tenant/origin hợp lý mà không lộ PII?

## 21. Câu hỏi tự kiểm tra

**1. `ServerSocket.bind(address, 64)` có giới hạn 64 active connections?** Không. 64 là requested pending connection backlog và còn phụ thuộc OS.

**2. Một HTTP/2 connection có thể chứa nhiều requests?** Có, nhiều HTTP streams multiplex trên cùng TCP/TLS connection.

**3. `jdk.httpserver.maxConnections` của JDK 17 giới hạn gì?** Số open connections gồm active và idle; không phải request concurrency cap.

**4. `jdk.httpclient.connectionPoolSize` giới hạn bao nhiêu active TCP connections?** Không định nghĩa trần active connections; đó là giới hạn HTTP/1.1 **keep-alive cache** trong JDK implementation.

**5. `HttpClient.Builder.executor(pool)` có tự đặt max in-flight HTTP requests?** Không. Đó là executor cho các tasks bất đồng bộ/dependent theo API.

**6. `Executors.newFixedThreadPool(8)` có bounded queue chờ?** Không nên giả định queue bounded. Dùng `ThreadPoolExecutor` và `ArrayBlockingQueue` khi cần cap hữu hạn.

**7. Khi server hết request permits nên làm gì?** Trả 503 có policy/Retry-After nếu handler có thể trả; hoặc điều tiết/từ chối sớm theo tầng mạng, không đợi vô hạn.

**8. 429 khác 503 ở đâu?** 429 thường là quota/rate limit của client; 503 là service tạm không đáp ứng.

**9. Vì sao phải nhả `Semaphore` trong finally?** Để exception/timeout không làm mất permit mãi.

**10. Vì sao không release hai lần từ timeout và success callbacks?** Có thể làm permits vượt trần; cần ownership terminal exactly once.

**11. `ByteBuffer.allocateDirect` có chắc nằm trong -Xmx?** Không. Direct memory thường ở ngoài heap và cần theo dõi riêng.

**12. Hai `ByteBuffer.slice()` có thể chia sẻ storage?** Có. Không đếm chúng như hai allocations độc lập khi tính physical memory.

**13. Memory reservation `release` có đồng nghĩa GC đã thu hồi bytes?** Không. Đó là budget logic; GC và pool retention có lifecycle khác.

**14. Vì sao Content-Length không đủ để chống body quá lớn?** Có thể vắng/sai và nén làm khác kích thước xử lý; phải đếm bytes thực.

**15. Client dùng `ofInputStream()`, response future done thì request permit có nên release ngay?** Không nếu permit bảo vệ toàn bộ tiêu thụ body. Chờ EOF/close/error.

**16. Vì sao demo bảo đảm nhận 503 cho request thứ ba?** Hai CountDownLatch giữ hai request đã acquire permits, nên request thứ ba không thể lấy slot.

**17. Demo có đặt max TCP connections không?** Không. Nó đặt max request processing và logical buffer quota, với backlog riêng.

**18. Tại sao queue lớn có thể làm latency xấu hơn?** Requests phải chờ lâu, giữ payload/objects và có thể hết deadline trước khi được xử lý.

**19. `BufferPoolMXBean.getMemoryUsed()` có đo toàn bộ RSS?** Không. Chỉ là ước tính memory của một buffer pool; có thể trả -1.

**20. Một service có ít active requests nhưng nhiều idle sockets vẫn có nguy cơ gì?** File descriptor và kernel/native memory bị giữ, làm cạn connection capacity.

## 22. Tài liệu tham khảo chính thức

- [Java SE 17 – ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): `bind(backlog)` là requested pending connection queue, không phải active cap.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `create/bind` backlog, `setExecutor` trước `start`, server lifecycle.
- [Java SE 17 – HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response body, headers và close.
- [Java SE 17 – Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): bảng **JDK-specific HTTP client/server system properties**, trong đó có `jdk.httpserver.maxConnections`, `jdk.httpclient.connectionPoolSize`, `jdk.httpclient.maxstreams` và các memory/buffer-related knobs.
- [Java SE 17 – HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): public builder options, `executor`, `connectTimeout`, protocol version.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client reuse, `sendAsync`, response BodyHandlers.
- [Java SE 17 – Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): concurrency permits, `tryAcquire` và `release`.
- [Java SE 17 – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded thread pools, queues và rejection.
- [Java SE 17 – ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): hàng đợi có capacity cố định.
- [Java SE 17 – ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): heap/direct buffers, `slice/duplicate`, backing storage và native I/O.
- [Java SE 17 – BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): đo estimates của direct/mapped buffers.
- [Java SE 17 – ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy platform MXBeans.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `429`, `503`, `Retry-After` và retry semantics.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): streams, multiplexing và concurrency settings.

**Kết luận:** Độ tin cậy không được tạo ra bằng một con số “max connections” duy nhất. **Backlog** chỉ là queue chờ TCP accept; **connection cap** bảo vệ sockets/file descriptors; **request cap + bounded queue** bảo vệ worker/downstream; **byte reservations + pool budgets** bảo vệ heap/direct memory. Với Java 17, hãy phân biệt JDK-specific cache properties với public APIs, giới hạn request bằng admission rõ ràng, giữ permit đến lúc xử lý body hoàn tất, trả overload có kiểm soát và đo tài nguyên thực khi load test.
