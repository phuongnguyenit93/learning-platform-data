# 18.3 Đối chiếu thread đang ở native I/O với cấu hình timeout và tiến triển dữ liệu

> **Phạm vi:** chẩn đoán I/O và độ trễ trong ứng dụng Java 17+ (HotSpot/JDK), đặc biệt khi thread dump cho thấy thread ở đường đọc/ghi socket, file hoặc thư viện native. Mục tiêu không phải gán nhãn “treo” chỉ từ một stack trace, mà **đối chiếu cùng lúc ba nguồn bằng chứng**: (1) thread đang chờ thao tác nào, (2) timeout/deadline thực sự có hiệu lực ở tầng nào, và (3) dữ liệu có tiến triển theo thời gian hay không.

## 1. Ba câu hỏi bắt buộc trước khi kết luận

Một thread xuất hiện ở `SocketInputStream.read`, `SocketDispatcher.read0`, `NioSocketImpl.timedRead`, `FileDispatcherImpl.read0` hoặc đường JNI/native **không tự chứng minh deadlock**. Phương thức native có thể đang chờ OS trả dữ liệu, chờ đối tác mạng, chờ storage, hoặc lặp đọc có tiến triển bình thường.

Hãy lần lượt trả lời:

1. **Thread đang làm gì?** Lấy nhiều thread dump có timestamp, xác định Java thread ID, native thread ID (nếu có), stack frames và connection/dependency tương ứng. Phân biệt socket read, socket write, `connect`, file I/O, selector/poll, TLS handshake, gọi driver/native library và chờ lock.
2. **Timeout nào thực sự áp dụng?** Kiểm tra cấu hình **đang chạy**, scope và đơn vị: TCP connect timeout, socket read timeout, tổng deadline nghiệp vụ, HTTP request timeout, connection-pool acquire timeout, driver/JDBC timeout, v.v. “Đã đặt timeout” không đủ nếu nó chỉ bao một pha khác.
3. **Có tiến triển dữ liệu không?** So sánh counters/timestamps ở ít nhất hai thời điểm: bytes read/written thành công, số message/frame hoàn tất, lần cuối có byte, request/response state, throughput, JFR I/O events và metrics bên peer. Không có bytes mới khác với “request chưa hoàn tất”.

**Kết luận đáng tin** phải chỉ rõ cả ba, chẳng hạn:

> Thread `gateway-reader-7` đang trong socket read tới upstream A; read timeout thực tế là 0 (vô hạn), deadline nghiệp vụ chưa được áp dụng; trong 45 giây gần nhất bytesReceived không đổi từ 8 KiB. Upstream cũng không phát response chunk mới. Đây là **nghi vấn thiếu deadline/đối tác ngừng gửi**, chưa phải bằng chứng về Java monitor deadlock.

Ngược lại, nếu bytesReceived tăng liên tục và latency cao, việc thread thường xuyên hiện ở read có thể phản ánh **dòng dữ liệu chậm hoặc response dài**, không phải một read bị kẹt từ đầu đến cuối.

## 2. Hiểu đúng trạng thái thread và “native I/O”

### 2.1. `RUNNABLE` không có nghĩa luôn tiêu CPU

`java.lang.Thread.State` là trạng thái do JVM báo cáo, **không tương ứng một-một với trạng thái OS thread**:

| Java thread state | Ý nghĩa điển hình | Diễn giải khi chẩn đoán I/O |
| --- | --- | --- |
| `RUNNABLE` | Đang ở trạng thái có thể chạy theo JVM | Có thể đang thực thi Java/native code **hoặc chờ tài nguyên OS**; không kết luận CPU-bound chỉ vì `RUNNABLE`. |
| `BLOCKED` | Chờ vào Java monitor (`synchronized`) | Đây là chờ khóa monitor, **khác** socket read bị OS chặn. |
| `WAITING` | Chờ không thời hạn ở `wait`, `join`, `park`... | Có thể liên quan pool, condition, queue, completion; cần xem stack. |
| `TIMED_WAITING` | Chờ có thời hạn (`sleep`, `wait(timeout)`, `parkNanos`...) | Không đồng nghĩa socket I/O đã cấu hình đúng timeout. |
| `TERMINATED` | Thread kết thúc | Snapshot sau khi request xong không thể chứng minh trạng thái trước đó. |

Một Java thread có thể ở trạng thái `RUNNABLE` trong khi native code/OS syscall đang chờ dữ liệu. Trên các JDK khác nhau, stack có thể hiển thị `SocketDispatcher.read0(Native Method)`, `sun.nio.ch.NioSocketImpl.timedRead`, `java.net.Socket$SocketInputStream.read`, hoặc lớp wrapper khác. **Tên frame không phải hợp đồng ổn định qua JDK/OS**.

Ví dụ **minh họa hình dáng**, không phải output cố định:

```text
"upstream-reader-7" #47 ...
   java.lang.Thread.State: RUNNABLE
    at sun.nio.ch.SocketDispatcher.read0(Native Method)
    at sun.nio.ch.SocketDispatcher.read(...)
    at java.net.Socket$SocketInputStream.read(...)
    at com.example.UpstreamClient.fetch(...)
```

Những frame quan trọng cần xác định là **read hay write**, **ứng dụng gọi từ đâu**, **thread ID/tên**, **endpoint**, và **nó còn ở đó bao lâu qua nhiều snapshot**. Một dump duy nhất chỉ cho biết tình trạng tại thời điểm lấy mẫu; không cho biết bytes có dịch chuyển giữa các lần chạy của thread.

### 2.2. Java thread ID, native TID và OS state

Một thread dump HotSpot có thể chứa:

- Java thread name và Java thread ID.
- `nid=...` (native thread ID, thường được hiển thị dạng hex trên Linux); cách biểu diễn tùy công cụ/version.
- Stack trace, Java state, lock owners/monitors khi có.

Nếu so với Linux `top -H`, `ps -L`, `strace` hoặc `/proc`, phải **quy đổi/đối chiếu đúng TID**; đừng nhầm JVM PID, Java `Thread.threadId()` và OS thread ID là cùng một giá trị. OS có thể báo sleeping/polling trong khi Java dump báo `RUNNABLE`.

`ThreadInfo.isInNative()` của `ThreadMXBean` cho biết Java thread đang thực thi JNI native code theo định nghĩa riêng; nó **không** bao trùm mọi VM-support code hay machine code do JIT sinh. Không dùng một boolean này làm bằng chứng duy nhất rằng socket đang bị kẹt ở native I/O.

### 2.3. Platform threads, virtual threads và asynchronous I/O

Trên JDK 21+, virtual threads có thể **unmount khỏi carrier** khi đợi blocking operations tương thích. Vì vậy một virtual thread chờ socket không nhất thiết “chiếm” một OS thread; thread dump truyền thống và OS thread count có thể không hiển thị toàn bộ mối quan hệ như với platform threads.

Với NIO/event-loop (`Selector.select`, `SocketChannel` non-blocking), một thread có thể chờ readiness cho **nhiều connections**. Không được kết luận chỉ từ stack `select()` rằng connection X chậm. Phải ghép thêm selector key/channel metrics, connection state và counters riêng từng request.

Một SDK/driver có thể gọi JNI, native TLS/crypto, database client hoặc I/O async bên dưới. Nếu stack chỉ dừng ở wrapper Java, điều tra có thể cần trace/log của thư viện, profiler native, TCP metrics hoặc driver configuration. **Không giả định mọi native I/O chịu `Socket#setSoTimeout`**.

## 3. Bản đồ timeout: các loại không thay thế cho nhau

Tên “timeout” gần giống nhau nhưng giới hạn các **giai đoạn khác nhau**. Luôn ghi cả **nguồn cấu hình**, **giá trị hiện hành**, **đơn vị**, **pha áp dụng** và **hành vi khi hết thời gian**.

| Timeout/deadline | Pha áp dụng | Java/API thường gặp | Không bảo đảm |
| --- | --- | --- | --- |
| **TCP connect timeout** | Thiết lập kết nối TCP | `Socket.connect(endpoint, timeoutMs)`; `HttpClient.Builder.connectTimeout` cho **kết nối mới** | Không giới hạn thời gian server trả response, đọc body, acquire connection pool hoặc công việc sau connect. |
| **Socket read timeout** | Một lần chờ đọc từ `Socket` input stream | `Socket.setSoTimeout(ms)` và `InputStream.read` | Không tự đặt trần **toàn bộ response** gồm nhiều lần read; không giới hạn connect hay write. |
| **Socket accept timeout** | Đợi connection mới trên server socket | `ServerSocket.setSoTimeout(ms)` | Không giới hạn việc đọc body từ client sau accept. |
| **HTTP request timeout** | Request/response theo định nghĩa thư viện | `HttpRequest.Builder.timeout(Duration)` | Không tự chứng minh mọi downstream processing/streaming user code đã được chặn bởi một deadline nghiệp vụ duy nhất. |
| **Pool acquire timeout** | Chờ lấy connection/client resource từ pool | HTTP/JDBC pool-specific options | Không giới hạn I/O sau khi mượn connection. |
| **TLS handshake timeout** | Giai đoạn thương lượng TLS | Phụ thuộc API/client/driver và cách nó sử dụng socket | TCP connect thành công không có nghĩa TLS đã hoàn thành. |
| **Query/driver socket timeout** | SQL command/driver network operations | `Statement.setQueryTimeout`, JDBC driver socket/network options | Một query timeout không tự bao quát pool wait, app queue và mọi native read. |
| **Overall operation deadline** | Từ đầu tới kết quả cuối của nghiệp vụ | Context/deadline ứng dụng, tracing/client policies, custom `System.nanoTime()` | Nếu chỉ kiểm tra deadline giữa các lần I/O, một call blocking không có timeout vẫn có thể quá hạn. |
| **File I/O deadline** | Đọc/ghi storage | FileChannel, async I/O, SDK-specific APIs | Java file read/write **không có** `Socket.setSoTimeout` tương đương dùng chung cho mọi filesystem. |

### 3.1. `Socket.connect` vs `Socket.setSoTimeout`

Với blocking `java.net.Socket`:

```java
Socket socket = new Socket();
socket.connect(new InetSocketAddress("example.invalid", 443), 1000);
socket.setSoTimeout(500);
```

Đây là **đoạn cấu hình minh họa**; không phải chương trình độc lập để kết nối tới host thật. `1000` ms là giới hạn cho **connect**, `500` ms là giới hạn cho **một lần blocking read** trên `InputStream` của socket. `setSoTimeout` phải thiết lập **trước** khi bắt đầu read mới có hiệu lực như mong muốn.

Theo API, `setSoTimeout(0)` nghĩa **vô hạn**; read hết thời gian dương sẽ ném `SocketTimeoutException`, nhưng **socket vẫn hợp lệ** về mặt API. Việc có nên đọc tiếp hay đóng/retry phụ thuộc giao thức và trạng thái request. Không kết luận timeout sẽ tự xóa mọi dữ liệu đã nhận, cũng không mặc định read retry là an toàn với mọi giao dịch.

**Quan trọng:** SO_TIMEOUT được áp dụng cho từng blocking read, **không phải tổng thời gian để lấy xong một message**. Nếu peer gửi 1 byte mỗi 400 ms và socket read timeout là 500 ms, nhiều lần `read()` có thể liên tục hoàn thành mà toàn response vẫn kéo dài vài phút. Cần **overall deadline** riêng để chống kiểu “trickle” này.

Một `SocketChannel` dùng non-blocking + Selector có mô hình chờ readiness riêng. Không gán `Socket.setSoTimeout` cho mọi biến thể NIO, async stream hoặc SDK; kiểm tra chính xác API mà code đang gọi.

### 3.2. HTTP client: cấu hình trông có nhưng không đúng pha

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(500))
        .build();

HttpRequest request = HttpRequest.newBuilder(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();
```

Đây là đoạn mã minh họa (cần các `import java.net.URI;`, `java.net.http.*;`, `java.time.Duration;` và method/class bao quanh). `connectTimeout` của `HttpClient` chỉ được dùng khi phải **tạo kết nối mới**; trên reused connection nó không tác động. `HttpRequest.timeout` giới hạn việc chờ response theo contract `HttpRequest`/HTTP client và có thể tạo `HttpTimeoutException`.

Không suy từ `connectTimeout=500ms` rằng request sẽ hoàn tất sau 500 ms. Cũng không mặc định HTTP client timeout đã bao hết công việc bất đồng bộ **sau khi** response được giao cho consumer, logic parse/transform, hoặc retry ở tầng ứng dụng. Với client và body handler cụ thể, xác minh lifecycle thực tế.

Nếu request có retry 3 lần, mỗi lần có timeout 2 giây, **tổng thời gian** còn có backoff/pool wait/serialization và có thể vượt nhiều lần 2 giây. Phải có deadline ở tầng operation (ví dụ budget 3 giây) và truyền phần thời gian còn lại xuống từng attempt.

### 3.3. Write timeout và các giới hạn khác

`Socket.setSoTimeout` là **read timeout**, không phải cách giới hạn một blocking `OutputStream.write`. Ghi lớn vào TCP socket khi peer ngừng đọc có thể bị backpressure/đầy send buffer; muốn giới hạn **toàn bộ thao tác gửi**, hãy dùng API/client có deadline/cancellation được hỗ trợ hoặc thiết kế nonblocking channel/selector với policy rõ.

Ngay cả khi `write()` trả về thành công, dữ liệu có thể mới chỉ được chuyển vào bộ đệm phía local/kernel, **không** có nghĩa peer đã nhận, parse hoặc xử lý xong. Số `bytesWritten` trong JFR/ứng dụng vì vậy khác với business acknowledgment.

Với DB/network driver, TLS, DNS, pool acquire hay native libraries: kiểm tra timeout của từng subsystem và log cấu hình cuối cùng được áp dụng. Không áp một giá trị cấu hình ở tầng này rồi suy nó đã tự truyền tới tầng khác.

## 4. “Tiến triển dữ liệu” cần đo thế nào?

### 4.1. Không chỉ nhìn thread sống hay connection ESTABLISHED

Một TCP connection ở trạng thái `ESTABLISHED` có thể không nhận byte mới trong thời gian dài; một thread `RUNNABLE` có thể đang chờ read, và một server có thể liên tục gửi các chunk nhỏ nhưng chưa hoàn tất response. Cần ít nhất bốn chỉ dấu độc lập:

1. **`bytesReceived`**: cộng bytes **thực sự trả về thành công** qua read, không cộng bytes được *yêu cầu* trong buffer.
2. **`lastByteReceivedAt`**: mốc monotonic (`System.nanoTime()`) khi có `n > 0`; xem `now - lastByteReceivedAt` để phát hiện idle.
3. **`framesCompleted`/`recordsCompleted`**: số message hoặc response hoàn tất sau parse đúng giao thức; 1 MiB đã nhận **không** chứng minh một response hợp lệ đã hoàn tất.
4. **`operationStartedAt`, `deadline`, `stage`, `outcome`**: tổng elapsed, deadline còn lại và giai đoạn hiện hành (connect, handshake, read headers, read body, decode, persist, ...).

Với `InputStream.read(byte[])`: giá trị **dương** nghĩa nhận được chừng ấy byte; `-1` nghĩa end-of-stream (EOF). Nếu gọi read với độ dài buffer bằng 0, API có thể trả 0 và **không có tiến triển**. Không cộng `0` hoặc `-1` vào bytesReceived. Với nonblocking `SocketChannel.read`, `0` còn có thể nghĩa hiện chưa có byte ở lần thăm dò này.

Khi gọi `read()` timeout, những **lần đọc trước** có thể đã nhận dữ liệu hợp lệ; timeout không phủ nhận tiến triển cũ. Nếu muốn hỗ trợ recovery/retry, application phải giữ state parser, offsets, correlation ID và tính idempotency của thao tác tiếp theo.

### 4.2. Tính được gì từ hai snapshot?

Ví dụ minh họa (cùng operation, cùng socket, đo bằng monotonic clock):

| Thời điểm | `bytesReceived` | `framesCompleted` | `lastByteAge` | Stack gần nhất |
| --- | ---: | ---: | ---: | --- |
| 10:00:00 | 8192 | 0 | 2 s | `SocketInputStream.read` |
| 10:00:10 | 8192 | 0 | 12 s | `SocketInputStream.read` |
| 10:00:20 | 8192 | 0 | 22 s | `SocketInputStream.read` |

**Nhận định:** cùng request không có bytes mới trong 20 giây; thread liên tục được lấy mẫu ở đường đọc; cần kiểm tra read timeout, end-to-end deadline, peer state và network. **Chưa thể** xác định bên nào gây ra việc đứng yên nếu chưa có dữ liệu phía peer.

Ví dụ khác:

| Thời điểm | `bytesReceived` | `framesCompleted` | `lastByteAge` | Stack gần nhất |
| --- | ---: | ---: | ---: | --- |
| 10:00:00 | 8192 | 0 | 0.2 s | `SocketInputStream.read` |
| 10:00:10 | 17408 | 0 | 0.4 s | `SocketInputStream.read` |
| 10:00:20 | 26624 | 0 | 0.1 s | `SocketInputStream.read` |

**Nhận định:** có tiến triển byte (~0,9 KiB/s), nhưng vẫn chưa hoàn thành frame/response; nghi vấn throughput thấp, payload quá lớn, backpressure, framing/protocol hoặc peer gửi nhỏ giọt. Tăng read timeout không giải quyết nguyên nhân latency; deadline tổng và throughput/idle thresholds có thể hữu ích.

**Phân biệt `bytesRead` và bytes thực dùng:** TLS/compression/protocol buffers có thể làm số byte ở tầng socket khác số byte ứng dụng đã giải mã. Metrics phải ghi rõ đo ở tầng nào; không cộng nhầm các tầng khiến double counting.

### 4.3. Những con số nên có trong telemetry

Một mẫu event/log **minh họa**, không chứa payload:

```json
{
  "operation": "fetch-inventory",
  "correlationCode": "opaque-7F3B",
  "stage": "READ_BODY",
  "elapsedMs": 1480,
  "remainingDeadlineMs": 520,
  "configuredReadTimeoutMs": 500,
  "bytesReceived": 8192,
  "expectedBytes": 32768,
  "lastByteAgeMs": 970,
  "framesCompleted": 0,
  "outcome": "PENDING"
}
```

Đừng log URL đầy đủ, query, auth headers, request/response body hoặc PII chỉ để debug. `expectedBytes` chỉ đáng tin khi protocol có framing/length rõ và không bị nén/streaming theo semantics khác; nếu không biết, lưu `unknown` thay vì đoán.

**Kiểm soát cardinality:** operation/stage/outcome có tập giá trị hữu hạn; correlationCode chỉ dùng trong trace/log/JFR có retention và quyền truy cập phù hợp, **không** làm label cho time-series metrics. Không phát mỗi byte một log hoặc event; ghi progress theo interval, số bytes threshold, request completion, timeout/error.

## 5. Thu bằng chứng: thread dump + timeout + JFR + OS

### 5.1. Chụp nhiều thread dump có timestamp

Khi tiến trình còn sống và có quyền attach:

```bash
jcmd -l
jcmd <PID> Thread.print -l > threads-t0.txt
sleep 5
jcmd <PID> Thread.print -l > threads-t1.txt
sleep 5
jcmd <PID> Thread.print -l > threads-t2.txt
```

Thay `<PID>` bằng PID thật của JVM. Các file thread dump cần gắn timestamp từ hệ thống thu thập; đặt tên `t0`/`t1` **không** tự bảo đảm chúng cách đúng 5 giây nếu hệ thống đang quá tải.

Phân tích theo **Java thread ID/native ID**, không chỉ theo tên: thread pool có thể đổi worker hoặc request giữa các lần chụp. Nhìn stack thuộc app (`service`, `client`, `driver`) để biết **ai gọi read**, địa chỉ peer từ cấu hình/metrics/traces. Những frame như `Unsafe.park`, `LockSupport.park`, `Selector.select`, `SocketDispatcher.read0` mang ngữ nghĩa khác nhau, không nên gộp là “native I/O stuck”.

Ở JVM không attach được vì quyền/namespace, có thể dùng công cụ do hệ thống cho phép (`jstack`/signal support/diagnostic endpoint/observability của runtime). Không tự mở quyền admin hay ptrace trên production nếu chưa được phép; hoạt động dump cũng có chi phí và có thể chứa dữ liệu nhạy cảm.

### 5.2. JFR: xem **I/O đã hoàn thành và ghi nhận được**

JFR của JDK có các loại event hữu ích:

- `jdk.SocketRead`: thời lượng, remote host/address/port, `timeout` (theo schema JVM), `bytesRead`, `endOfStream`.
- `jdk.SocketWrite`: thời lượng, remote endpoint và `bytesWritten`.
- `jdk.FileRead`: thời lượng, path, `bytesRead`, `endOfFile`.
- `jdk.FileWrite`: thời lượng, path, `bytesWritten`.

**Kiểm tra schema thật của JDK đang chạy**:

```bash
jfr metadata --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite
```

`jdk.SocketRead.timeout` là giá trị timeout được instrument/ghi trong event, **không** có nghĩa bằng duration thực của lần đọc. `bytesRead` là số byte của **event read đó**, không phải tổng bytesReceived của request. `endOfStream=true` khác với `bytesRead=0`.

Một event SocketRead thường xuất hiện khi đường đọc được JDK **ghi nhận sau một lời gọi hoàn tất** và đạt threshold. **Không được suy “không có SocketRead event ⇒ không có read”**: recording có thể tắt event, filter threshold, mất event, dùng một implementation không được instrument, hoặc lời gọi ném exception/timeout không tạo event như bạn mong đợi. Trong kiểm tra thực tế trên JDK 24, một blocking read ném `SocketTimeoutException` không tạo `jdk.SocketRead` event; ngược lại một read thành công 251 ms đã được ghi nhận khi bật event rõ ràng.

### 5.3. Cấu hình recording có chủ đích

Có thể dùng `jfr configure` tạo file settings riêng (giữ những setting mặc định khác):

```bash
jfr configure --output io.jfc \
  'jdk.SocketRead#enabled=true' \
  'jdk.SocketRead#threshold=5ms' \
  'jdk.SocketWrite#enabled=true' \
  'jdk.SocketWrite#threshold=5ms' \
  'jdk.FileRead#enabled=true' \
  'jdk.FileRead#threshold=5ms' \
  'jdk.FileWrite#enabled=true' \
  'jdk.FileWrite#threshold=5ms'
```

Lệnh này tạo `io.jfc` **chứ không bắt đầu recording**. Threshold 5 ms là ví dụ khi muốn xem I/O chậm; nó chủ động bỏ các operation nhanh. Hạ threshold xuống `0` chỉ trong lab hoặc một cửa sổ điều tra có kiểm soát nếu cần mọi I/O call được instrument; event volume và overhead sẽ tăng.

Bắt recording lúc JVM start:

```bash
java -XX:StartFlightRecording=name=io,settings=io.jfc,disk=true,filename=io.jfr,dumponexit=true \
  -jar app.jar
```

`app.jar` là tên ứng dụng **minh họa**. Với JVM đang chạy và được quyền attach:

```bash
jcmd <PID> JFR.start name=io settings=io.jfc duration=2m filename=io-snapshot.jfr
jcmd <PID> JFR.check name=io verbose=true
```

Đọc bản ghi bằng:

```bash
jfr summary io-snapshot.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite io-snapshot.jfr
```

Nếu đang ghi theo cách khác, dùng đúng đường file `.jfr` thực tế. `jfr summary` cho số lượng event theo loại; `jfr print` chi tiết giúp nhóm theo host, port, thread, duration/bytes. Có thể mở JFR bằng JDK Mission Control (JMC) để đối chiếu timeline.

**Cảnh báo:** Nếu threshold=20 ms, một read nhanh trả 16 KiB có thể không được ghi, còn một read 300 ms nhận 0 byte có thể cũng không xuất hiện nếu đường error không emit event. Vì vậy **không lấy tổng `bytesRead` của JFR làm tổng traffic chính xác**, càng không xem event thiếu là bằng chứng thiếu I/O. Kết hợp application byte counters và network/driver metrics.

### 5.4. Bằng chứng OS và phía đối tác

Trên Linux, ví dụ:

```bash
ps -L -p <PID> -o pid,tid,stat,wchan:32,comm
ss -tinp
lsof -nP -p <PID>
```

`ps -L` giúp đối chiếu OS TID và wait channel khi có thông tin; `ss` cung cấp trạng thái socket/queue/TCP info; `lsof` cho biết file descriptors/sockets mở. Những lệnh này có phạm vi và yêu cầu quyền riêng; đừng diễn giải `ESTABLISHED` là ứng dụng đang nhận dữ liệu hay `Recv-Q=0` là peer “chết”.

Khi cần cấp syscall/network trace (`strace`, eBPF, packet capture), hãy xin quyền vận hành phù hợp; chúng có overhead và có thể chứa payload hoặc địa chỉ nhạy cảm. Trên Windows/macOS chọn công cụ hệ điều hành tương ứng. Khi điều tra 2 đầu kết nối, đồng bộ thời gian/clock drift; phân biệt thời điểm OS capture, application log và JFR event.

## 6. Lab Java 17+: read timeout xảy ra dù đã nhận được một phần dữ liệu

Lab chạy hoàn toàn trên loopback; **không cần server ngoài**. Một thread server gửi `"HE"`, giữ lại `"LLO"` cho tới khi client gặp read timeout, sau đó gửi phần còn lại. Nó minh họa ba điều:

1. Read timeout của **một lần đọc** không xóa những bytes đã nhận ở lần trước.
2. `SO_TIMEOUT` không phải deadline tổng; socket vẫn còn dùng được sau timeout.
3. Muốn kết luận có hay không có progress phải đo bytes theo **nhiều lần đọc** và xem protocol đã hoàn tất hay chưa.

### 6.1. Tạo file `NativeIoProgressLab.java`

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class NativeIoProgressLab {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        CountDownLatch allowTail = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            Future<?> peer = pool.submit(() -> {
                try (Socket socket = listener.accept()) {
                    OutputStream out = socket.getOutputStream();
                    out.write("HE".getBytes(StandardCharsets.US_ASCII));
                    out.flush();
                    allowTail.await();
                    out.write("LLO".getBytes(StandardCharsets.US_ASCII));
                    out.flush();
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(loopback, listener.getLocalPort()), 1000);
                client.setSoTimeout(2000);
                InputStream in = client.getInputStream();

                byte[] first = in.readNBytes(2);
                if (first.length != 2) throw new IllegalStateException("missing first part");
                int bytesReceived = first.length;
                System.out.println("received=" + new String(first, StandardCharsets.US_ASCII)
                    + " bytes=" + bytesReceived);

                client.setSoTimeout(args.length > 0 && args[0].equals("observe") ? 10000 : 150);
                try {
                    int b = in.read();
                    throw new IllegalStateException("expected timeout, read=" + b);
                } catch (SocketTimeoutException expected) {
                    System.out.println("read-timeout bytes=" + bytesReceived);
                }

                allowTail.countDown();
                client.setSoTimeout(2000);
                byte[] tail = in.readNBytes(3);
                if (tail.length != 3) throw new IllegalStateException("missing tail");
                bytesReceived += tail.length;
                System.out.println("received=" +
                    new String(first, StandardCharsets.US_ASCII) +
                    new String(tail, StandardCharsets.US_ASCII) +
                    " bytes=" + bytesReceived);
            } finally {
                allowTail.countDown();
            }
            peer.get(5, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Giải thích chi tiết:**

- `ServerSocket` bind loopback với port 0: OS chọn port còn trống; không phải mở service ra network bên ngoài.
- Thread `pool` làm peer. Nó ghi **chính xác 2 bytes** `"HE"`, sau đó chờ `allowTail` trước khi ghi `"LLO"`. Vì vậy client không thể nhận phần sau trước lúc phát tín hiệu.
- `readNBytes(2)` ở lần đầu yêu cầu đủ 2 bytes để minh họa prefix; đây là sự đơn giản hóa cho lab. Trong production, đọc stream theo vòng lặp và kiểm tra từng `read` cùng deadline để không làm mất khả năng quan sát progress.
- Client đặt `SO_TIMEOUT=150` ms cho lần read kế tiếp. Server cố ý không phát bytes mới nên xảy ra `SocketTimeoutException`.
- Sau timeout, biến `bytesReceived` vẫn là 2; server được phép gửi tiếp và client tăng nó thành 5. **Đó là tiến triển quan sát được**, khác tình trạng chưa nhận byte nào.
- Với tùy chọn `observe`, timeout của lần đọc thứ hai tăng lên 10 giây để có thời gian lấy thread dump **trong lúc client đang ở read**. Đây không phải cấu hình nên dùng trong production.
- `peer.get` xác nhận server không ném lỗi trong lab, và `finally` bảo đảm không giữ server đợi latch vô hạn.

### 6.2. Biên dịch, chạy và đọc stdout

```bash
javac NativeIoProgressLab.java
java NativeIoProgressLab
```

**Stdout chính xác của chương trình** (đã biên dịch/chạy trên OpenJDK 24):

```text
received=HE bytes=2
read-timeout bytes=2
received=HELLO bytes=5
```

Lưu ý: `Thread.sleep` không được dùng để “canh” phía server trong demo; `CountDownLatch` bảo đảm server chờ cho đến khi client đã ghi nhận timeout. Thời gian thực tế có thể dao động theo OS scheduling nhưng thứ tự và nội dung các dòng trên ổn định nếu chương trình chạy thành công.

Thử quan sát dump:

```bash
java NativeIoProgressLab observe
```

Trong terminal thứ hai **khi 10 giây read đang chờ**:

```bash
jcmd -l
jcmd <PID> Thread.print -l
```

Tìm thread `"main"` và các stack frame ở đường `InputStream.read`/socket hoặc NIO tùy JDK. Snapshot có thể chụp sau khi read kết thúc nếu thao tác quá chậm; có thể tăng cửa sổ chẩn đoán của lab có chủ đích. **Java state có thể là `RUNNABLE` dù thread đang chờ OS I/O**. Không lấy một lần dump trễ làm kết luận nguyên nhân.

### 6.3. Tạo recording JFR và kiểm tra event thực

Dùng settings riêng nếu muốn thấy các I/O calls ngắn trong lab:

```bash
jfr configure --output io.jfc \
  'jdk.SocketRead#enabled=true' \
  'jdk.SocketRead#threshold=0' \
  'jdk.SocketWrite#enabled=true' \
  'jdk.SocketWrite#threshold=0'
```

```bash
java -XX:StartFlightRecording=name=lab,settings=io.jfc,filename=io.jfr,dumponexit=true \
  NativeIoProgressLab
jfr summary io.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite io.jfr
```

`jfr configure` và các flags trên là lệnh thực của JDK. Khi chạy trên Windows PowerShell, thay phần xuống dòng Bash (`\`) bằng chạy một dòng đầy đủ hoặc dùng ký tự tiếp dòng PowerShell tương ứng; không chép nguyên lệnh Bash nhiều dòng sang PowerShell.

**Cách đọc kết quả:** Các event I/O trả bytes cho biết các phép read/write được instrument; chúng có `duration`, `timeout`, `bytesRead` hoặc `bytesWritten` và endpoint theo schema. **Số event không cố định giữa các JVM/JDK**; đừng khẳng định mỗi lời gọi `read` ném exception đều tạo một `SocketRead`. Một phép thử trên OpenJDK 24 với read timeout thực tế tạo **0** event SocketRead cho nhánh exception, dù Java code đã bắt timeout thành công.

Đây là lý do cần **bảng progress của ứng dụng** bên cạnh JFR: ghi `bytesReceived`/`lastByteAt` trong code (với sampling hợp lý), rồi so theo thời gian với event JFR, thread dumps và socket stats.

## 7. Thiết kế overall deadline để không bị “drip feed”

Một hệ thống production nên phân biệt:

- **Connect budget**: tối đa bao lâu để tạo connection.
- **Read idle timeout**: tối đa bao lâu cho một lần blocking read chờ byte mới.
- **Overall deadline**: từ lúc bắt đầu operation tới hạn phải trả kết quả/hủy.
- **Progress/throughput expectation**: sau mỗi khoảng thời gian, cần bytes/frame có nghĩa hoặc đủ throughput tối thiểu, tùy giao thức.

Đo elapsed bằng đồng hồ monotonic như `System.nanoTime()`, không dùng wall clock từ `System.currentTimeMillis()` làm deadline vì NTP/clock adjustment có thể làm đồng hồ nhảy.

### 7.1. Mã minh họa: một deadline bao nhiều lần read

Đây là một **phương thức Java minh họa**, không phải file chạy độc lập. Nó cần `import java.io.*;`, `import java.net.*;`, `import java.util.concurrent.TimeUnit;` và được đặt trong class có sẵn:

```java
static byte[] readExactlyBeforeDeadline(
        Socket socket, int expectedBytes, long maxMillis) throws IOException {
    if (expectedBytes < 0 || maxMillis <= 0) {
        throw new IllegalArgumentException("invalid limit");
    }

    byte[] result = new byte[expectedBytes];
    int received = 0;
    long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(maxMillis);
    InputStream in = socket.getInputStream();

    while (received < expectedBytes) {
        long remainingNanos = deadline - System.nanoTime();
        if (remainingNanos <= 0) {
            throw new SocketTimeoutException("overall deadline exceeded");
        }

        long remainingMs = TimeUnit.NANOSECONDS.toMillis(remainingNanos);
        int timeoutMs = (int) Math.max(1L, Math.min(500L, remainingMs));
        socket.setSoTimeout(timeoutMs);

        int n = in.read(result, received, expectedBytes - received);
        if (n == -1) {
            throw new EOFException("unexpected EOF after " + received + " bytes");
        }
        if (n > 0) {
            received += n;
            // Ghi metric lastProgressAt/bytesReceived ở đây, không log body.
        }
    }
    return result;
}
```

**Điều này giải quyết gì?** Sau mỗi lần `read` thành công, tính lại **thời gian còn lại**; không cấp một timeout cố định mới mãi mãi. `setSoTimeout` được đặt theo min(per-read cap, remaining deadline), nên peer gửi nhỏ giọt khó kéo dài operation vô hạn. Thời gian của các phase **trước/sau** method vẫn cần tính vào deadline của business operation nếu mục tiêu là end-to-end.

**Các giới hạn của phương thức:**

- `expectedBytes` chỉ được truyền khi giao thức có message length đã **xác thực**, không nhận giá trị tuỳ ý lớn từ client để cấp phát mảng gây OOM; production nên thêm max message size và streaming parser.
- `maxMillis` phải có range hợp lý; tránh overflow của phép cộng nanos khi dùng deadline rất lớn.
- Rounding về milliseconds và OS scheduling có thể làm timeout lệch một ít; đây không phải hard real-time deadline.
- Nếu một API native/driver **không** dùng cơ chế timeout này, setting `Socket` không giúp; cần đúng API phù hợp.
- Nếu request không thể retry an toàn, catching timeout chỉ để đánh dấu outcome/cleanup; không tự gửi lại giao dịch có side effect chưa xác định.
- `readExactlyBeforeDeadline` là mẫu single connection/synchronous; concurrent clients cần pool/async integration, cancellation và resource lifecycle riêng.

### 7.2. Budget phải xuyên suốt request

Ví dụ illustrative (không phải giá trị tối ưu):

| Giai đoạn | Budget độc lập | Chỉ dấu cần đo |
| --- | ---: | --- |
| Pool acquire | 100 ms | pool wait, queue depth, timeout counter |
| TCP connect | 300 ms | connect duration, failure rate, reused/new |
| TLS handshake | 300 ms | handshake duration, timeout/errors |
| Read | Mỗi blocking read tối đa 500 ms | bytesReceived, lastByteAge, bytes/sec |
| **Toàn operation** | **2 s** | startedAt, deadlineRemaining, final outcome |

Không đơn giản cộng các con số này để suy latency tối đa: cùng một operation có thể dùng nhiều reads, retries, redirects và queueing. **Overall deadline 2 giây cần được truyền xuống từng phase**; mỗi phase nhận phần budget còn lại, có thể phải rút ngắn hoặc abort sớm. Nếu server hoặc gateway upstream có timeout 1 giây thì client 10 giây có thể chỉ giữ thread chờ một request vốn đã thất bại ở tầng kia.

Cũng đừng dùng `Future.get(2, SECONDS)` rồi coi đó là “đã hủy I/O”. `get` hết thời gian chỉ làm **caller ngừng chờ**; task/IO phía sau có thể vẫn chạy. Phải xét contract của API, cách hủy/cắt connection và giải phóng tài nguyên.

## 8. Đối chiếu thực địa: ma trận tình huống

| Thread evidence | Timeout evidence | Progress evidence | Hướng điều tra hợp lý |
| --- | --- | --- | --- |
| Nhiều dump ở `SocketInputStream.read`/native read; CPU thấp | `SO_TIMEOUT=0`, không có overall deadline | Bytes không tăng 30 s | Thiếu read timeout/deadline hoặc peer không phát; xem upstream/socket stats, đặt bounded deadline. |
| Dump liên tục ở read | Mỗi read 500 ms nhưng no overall deadline | Bytes tăng vài byte mỗi 400 ms | “Drip-feed”: mỗi read không hết giờ nhưng cả response quá lâu; thêm deadline tổng/min throughput policy. |
| Socket read lặp, request chậm | Read timeout hợp lý | Bytes tăng nhanh, frame chưa hoàn tất | Response lớn, framing/content-length/chunked parse, downstream decode hoặc server streaming; không gán deadlock. |
| Stack ở `SocketDispatcher.write`/write path | Chỉ có read timeout | Bytes gửi không tăng hoặc send-Q lớn | Kiểm tra backpressure, peer không đọc, write timeout/cancellation của client/channel. |
| Stack ở `Selector.select` | Có per-request timeout ở app | Một số channels có bytes, một số không | Event loop chờ nhiều connections; cần per-channel metrics, không quy mọi latency cho selector thread. |
| Worker chờ pool/queue, không tới read | Chỉ thiết lập connect/read timeout | Progress bytes = 0 vì chưa có socket | Pool saturation hoặc upstream concurrency/bulkhead; timeout network không bao queue wait. |
| Thread ở TLS/handshake | Connect timeout ngắn | TCP connected nhưng không có app bytes | Kiểm tra handshake deadline, certificates, peer TLS, protocol negotiation; không coi connect thành công là xong. |
| Thread ở file/native driver read | Network `SO_TIMEOUT` đã đặt | I/O counters/offset file không đổi | Không liên quan socket timeout; kiểm tra storage, filesystem, JNI/driver-specific timeout. |
| App timeout được trả nhưng thread vẫn ở native call | Caller `Future.get` timed out | Thread/FD còn sống, không có progress | Caller timeout chưa đảm bảo cancellation; kiểm tra close/cancel semantics và leaked tasks. |
| `RUNNABLE` nhiều trong dump nhưng CPU process thấp | Timeout có vẻ đủ | Bytes tăng đều | Hoạt động I/O bình thường hoặc throughput chậm; tránh kết luận CPU runaway chỉ từ RUNNABLE. |

### Case A — Endpoint ngừng trả dữ liệu

**Bằng chứng:** thread dump t0/t1/t2 cùng stack `read`, bytesReceived không đổi, `lastByteAge` tăng, TCP vẫn ESTABLISHED, JFR không có completed read mới. Timeout setting = 0 hoặc lớn hơn budget upstream.

**Hướng xử lý:** lấy trạng thái peer, connection mapping, server logs, proxy/gateway timeouts; đặt read timeout phù hợp và **overall deadline**. Sau khi timeout, cần cleanup/reuse connection theo protocol/SDK; không retry request có side effect nếu chưa biết kết quả server.

**Điều không được kết luận:** “JFR không thấy SocketRead, chắc chắn không có I/O” — read đang chờ hoặc exception path có thể không phát event.

### Case B — Đọc đều nhưng request không hoàn tất

**Bằng chứng:** app counters tăng, JFR có nhiều SocketRead nhỏ, thread dump ngẫu nhiên bắt đúng read, tổng latency vượt SLO. `framesCompleted=0`, `expectedBytes` lớn hoặc chưa xác định.

**Hướng xử lý:** kiểm tra framing, chunked encoding, server-side serialization, dữ liệu thực được parse, compression ratio và network throughput; chọn streaming và bounds phù hợp. Read timeout đơn lẻ không giới hạn tổng duration nếu luôn có bytes đến kịp lúc.

### Case C — Timeout cấu hình ở HTTP client nhưng app vẫn chờ pool

**Bằng chứng:** thread stack ở acquire queue/lock, không có socket read; client đặt `connectTimeout` 500 ms, nhưng cả request có thể chờ connection pool nhiều giây. Số connections đang dùng đạt maximum.

**Hướng xử lý:** kiểm tra pool acquire timeout, queued tasks, busy connections, total deadline; đo `poolWaitMs`. Không sửa bằng tăng `SO_TIMEOUT` vì bước I/O chưa bắt đầu.

### Case D — Bị chặn ở write, peer không đọc

**Bằng chứng:** thread ở socket write, send-Q tăng hoặc bytesWritten đứng yên, read timeout 300 ms đã được bật. `SocketWrite` JFR có thể hiển thị write chậm sau khi nó hoàn tất.

**Hướng xử lý:** đánh giá backpressure, protocol flow control, server receive rate và outbound write deadline. `setSoTimeout` không áp dụng cho write. Ghi thành công local không chứng minh peer đã xử lý dữ liệu.

### Case E — File I/O hoặc native library

**Bằng chứng:** thread dump ở `FileDispatcherImpl.read0`/JNI/native call, file offset không tăng, storage latency tăng; network timeouts vẫn đúng nhưng không liên quan.

**Hướng xử lý:** dùng `jdk.FileRead/FileWrite` events, filesystem metrics, disk queue/latency, mount/NFS state hoặc library docs; kiểm tra cancel/interrupt semantics riêng. `Thread.State.RUNNABLE` không đủ kết luận file I/O bị deadlock.

### Case F — Virtual thread hoặc event loop

**Bằng chứng:** nhiều virtual threads chờ socket, OS thread count tương đối thấp; hoặc selector thread phục vụ nhiều channels. Một snapshot OS không lộ đầy đủ call path của từng request.

**Hướng xử lý:** bổ sung thread dumps hỗ trợ virtual threads/JFR events tương ứng, per-request correlation, deadline và bytes progress; đừng nhân số OS threads với số requests để suy số “thread bị nghẽn”.

## 9. Thứ tự hành động khi incident đang diễn ra

1. **Khoanh vùng request/operation:** correlation ID an toàn, endpoint/dependency, timeout hiện hành, tổng latency, thời gian bắt đầu. Xác nhận cùng PID/JDK/host/container.
2. **Chụp ít nhất 2–3 snapshot** (ví dụ cách 5 giây): thread dumps có timestamps, count active requests, bytes progress, lastByteAge, pool stats, OS sockets/TCP queues, logs.
3. **Ánh xạ thread → thao tác → endpoint:** Java stack và application frames, Java thread ID/native TID, connection/FD và correlation ID. Với async/virtual threads, thread name chưa đủ.
4. **Lập bảng timeout thực tế:** connect, pool acquire, TLS, read, write, request/overall deadline, retry. Kiểm tra `0`/unset và đơn vị; ghi rõ từng pha.
5. **Đối chiếu JFR:** bật/có event types `SocketRead`, `SocketWrite`, `FileRead`, `FileWrite`; xem threshold và `duration`, `timeout`, `bytesRead`, `bytesWritten`. Không thay application counters bằng JFR.
6. **Phân loại:** không progress, slow progress, progress hoàn tất nhưng business chưa xong, waiting pool/selector, file/native stall, hoặc CPU/lock issue thực sự.
7. **Chọn mitigation có kiểm soát:** timeouts/deadline ở đúng tầng, bounded concurrency, cancel/close đúng semantics, backpressure, cải thiện peer, retries an toàn; tránh tăng timeout hàng loạt mà không biết nguyên nhân.
8. **Kiểm chứng sau sửa:** cùng tải và thời gian; đo success/error rate, timeout rate, latency p95/p99, bytes/s, in-flight requests, JFR I/O duration, pool wait và thread snapshots. Không tuyên bố fix chỉ vì log lỗi biến mất.

**Mẫu kết luận có thể dùng trong báo cáo kỹ thuật:**

```text
Time window: 10:00:00–10:00:30 UTC
JVM: pid ..., JDK ..., service ...
Operation: fetch-inventory, correlation: opaque-...
Thread: javaId ..., nativeTID ..., stack: SocketInputStream.read(...)
Configured: connect=300 ms, read=0 ms, request-deadline=unset
Progress: bytesReceived=8192 at both t0 and t1; framesCompleted=0
Peer evidence: upstream no response-body bytes since 09:59:58
Interpretation: likely stalled peer read, unbounded by current read timeout
Mitigation: read idle timeout 500 ms + operation deadline 2 s
Verification: compare p99, timeout/error, throughput and partial-read behavior
```

Đây là **mẫu minh họa**, không phải những số liệu lấy từ một hệ thống thật. Báo cáo cuối cùng cần ghi độ tin cậy của từng kết luận, ví dụ “nghi vấn” khi chưa có log của peer.

## 10. Sai lầm thường gặp

1. **“RUNNABLE nghĩa CPU 100%.”** Sai: Java state khác OS scheduling; native I/O có thể chờ kernel.
2. **“Thread trong `SocketDispatcher.read0` chắc chắn deadlock.”** Sai: phải phân biệt blocked I/O với Java monitor deadlock và kiểm tra nhiều snapshots/progress.
3. **“Có connect timeout thì request có tổng timeout.”** Sai: connect chỉ bao giai đoạn kết nối, và connection pool/reuse thay đổi tính áp dụng.
4. **“Đã đặt `SO_TIMEOUT=500`, toàn response tối đa 500 ms.”** Sai: đó là timeout **mỗi blocking read**, response nhiều reads vẫn kéo dài.
5. **“`SO_TIMEOUT` cũng giới hạn `write()`.”** Sai: read timeout và write/backpressure khác nhau.
6. **“`read()` trả về số bytes yêu cầu.”** Sai: stream có thể trả ít hơn; đếm giá trị thực trả về `n>0`.
7. **“Một byte mới nghĩa request đang khỏe.”** Sai: peer có thể gửi nhỏ giọt, framing chưa hoàn tất và overall SLA đã quá.
8. **“BytesWritten báo thành công là server đã xử lý.”** Sai: có thể chỉ là bytes gửi vào local network stack, cần business acknowledgement.
9. **“JFR không có SocketRead event thì không có read.”** Sai: threshold, disabled settings, exception, incomplete call hoặc instrumentation path có thể khiến không có event.
10. **“SocketRead.timeout trong JFR là duration thực.”** Sai: event có `timeout` config và `duration` riêng.
11. **“Một thread dump chứng minh request đứng 30 giây.”** Sai: một snapshot không có chiều thời gian; cần thêm timestamps/counters.
12. **“Future.get timeout đã hủy được native I/O.”** Sai: `get` hết giờ không bảo đảm task đã dừng; cần API cancellation/resource close phù hợp.
13. **“Có TCP ESTABLISHED là có data progress.”** Sai: socket có thể sống nhưng không có payload mới.
14. **“Tăng timeout giải quyết mọi I/O latency.”** Sai: có thể chỉ làm tăng số in-flight requests và che vấn đề ở peer, pool hoặc retry.
15. **“Đếm bytes ở TLS/socket/body decoder có thể cộng lại.”** Sai: những tầng đó có thể đếm cùng dữ liệu theo biểu diễn khác.
16. **“Virtual thread chờ socket luôn chiếm một OS thread.”** Sai: blocking I/O tương thích thường cho phép unmount; cần công cụ quan sát hợp với JDK đang dùng.

## 11. Checklist ngắn trước khi kết luận

- [ ] Biết **PID, JDK/OS, Java thread ID, native TID**, stack ứng dụng và endpoint thực.
- [ ] Có **nhiều snapshot** theo thời gian, không chỉ một thread dump.
- [ ] Xác định **read/write/connect/file/selector/pool/handshake**, không gộp tất cả thành “native I/O”.
- [ ] Xác minh **giá trị timeout tại runtime**, phạm vi và đơn vị (0, unset, library defaults).
- [ ] Có **overall deadline** nếu operation phải đáp ứng SLA; không chỉ timeout từng read.
- [ ] Đo **bytesReceived/bytesWritten và frame/message completion** cùng thời điểm; chú ý `lastByteAge`.
- [ ] Đọc đúng `SocketRead.duration` vs `SocketRead.timeout`; biết JFR threshold và missing-event limitations.
- [ ] Kiểm tra phía peer, OS sockets/queues, pool và driver nếu hiện tượng vượt phạm vi Java stack.
- [ ] Gắn correlation ID và stage an toàn; tránh log body/token/PII.
- [ ] Sau sửa, kiểm chứng timeout/error rate, p95/p99, throughput và số connection/thread còn sống.

**Kết luận:** Thread đứng trên frame native I/O là **điểm bắt đầu điều tra**, không phải lời giải. Phải nối stack và trạng thái thread với **timeout thực sự có hiệu lực** cùng **tiến triển byte/message qua thời gian**. Chỉ khi ba dữ kiện này phù hợp, bạn mới phân biệt được kết nối đang chờ hợp lệ, peer gửi dữ liệu nhỏ giọt, cấu hình timeout thiếu, queue/pool bottleneck và tình trạng I/O thực sự đình trệ.

## Tài liệu tham khảo

- [Oracle Java 21 — `Thread.State`: RUNNABLE và sự khác biệt với OS state](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html)
- [Oracle Java 21 — `Socket`: `connect`, `setSoTimeout`, read semantics](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [Oracle Java 21 — `InputStream`: read, readNBytes và EOF](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html)
- [Oracle Java 21 — `HttpClient.Builder.connectTimeout`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Oracle Java 21 — `HttpRequest.Builder.timeout`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Oracle Java 21 — `SocketChannel` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Oracle Java 21 — `ThreadInfo` và thread dumps](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [Oracle Java 21 — `jcmd`: Thread.print và JFR commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java 21 — `jfr`: metadata, summary, print, configure](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle Java 21 — `jdk.jfr`: event settings, threshold và stack trace](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle — Troubleshoot Performance Issues Using JFR: Socket/File Read/Write](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
