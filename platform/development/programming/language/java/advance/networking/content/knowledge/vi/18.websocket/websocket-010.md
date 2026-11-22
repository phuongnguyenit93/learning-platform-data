# Ping/pong, phát hiện kết nối im lặng và giới hạn của heartbeat trong WebSocket (Java 17+)

## 1. Vấn đề thực tế: socket còn “mở” nhưng phía kia đã biến mất

Ứng dụng WebSocket thường giữ kết nối lâu để nhận thông báo, chat, telemetry hoặc cập nhật thời gian thực. Nhưng một đối tượng `WebSocket` còn tồn tại trong Java, một cờ “connected” chưa đổi và việc **chưa thấy exception** không có nghĩa client thực sự có thể trao đổi với server ngay lúc đó.

Các tình huống thực tế:

- Laptop mất Wi-Fi, đổi mạng, ngủ rồi thức dậy; địa chỉ IP hoặc đường đi tới server đổi.
- NAT, proxy, firewall hoặc load balancer xóa state của kết nối sau thời gian không có traffic, **không gửi WebSocket Close frame**.
- TCP connection ở một phía vẫn chưa nhận `FIN`/`RST` vì đường truyền đã đứt âm thầm (*half-open connection*).
- Event loop/callback của ứng dụng bị nghẽn, garbage collection pause hoặc CPU bận nên không xử lý thông điệp kịp.
- Server process bị treo hoặc chết giữa chừng; TCP và WebSocket không nhất thiết báo lỗi tức thì.
- Server vẫn trả Pong ở tầng WebSocket nhưng business worker, database hoặc hàng đợi đã không còn sẵn sàng.

**Heartbeat** là một phép kiểm tra định kỳ nhằm tìm dấu hiệu kết nối còn đáp ứng. Trong WebSocket chuẩn RFC 6455, cách phổ biến là gửi **Ping control frame** rồi đợi **Pong control frame** mang payload tương ứng. Nếu không thấy Pong trong một khoảng thời gian phù hợp, client đánh dấu kết nối **nghi ngờ không phản hồi (suspect/unresponsive)**, có thể đóng và kết nối lại.

**Thông điệp cốt lõi:** *Pong cho biết một phía của WebSocket stack còn có thể nhận và phản hồi Ping gần đây; nó không chứng minh business service khỏe mạnh. Ngược lại, quá hạn Pong chỉ cung cấp bằng chứng theo chính sách timeout, không chứng minh tuyệt đối rằng peer đã chết.*

Bài này thuộc **Java Advance - networking → WebSocket**, tập trung vào **“Ping/pong, phát hiện kết nối im lặng và giới hạn của heartbeat”**. Các ví dụ sử dụng API `java.net.http.WebSocket` của Java 17, RFC 6455 và hai chương trình tự chạy được (một thử trên loopback WebSocket thật, một thử policy heartbeat với đồng hồ mô phỏng).

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Mô tả **WebSocket Ping (opcode 0x9)**, **Pong (opcode 0xA)**, payload tối đa **125 bytes**, cấm phân mảnh control frames và điều kiện phản hồi theo RFC 6455.
2. Phân biệt Ping→Pong **theo cặp**, **unsolicited Pong**, application-level heartbeat, TCP keepalive và idle timeout của proxy/load balancer.
3. Hiểu vì sao `WebSocket.sendPing(ByteBuffer)` trả `CompletableFuture<WebSocket>` cho **send operation**, không phải lời hứa đã nhận Pong.
4. Triển khai `WebSocket.Listener.onPong(...)`, quản lý `webSocket.request(n)` và đối chiếu **token/nonce** trong payload.
5. Hiểu Java 17 WebSocket client **tự gửi Pong khi nhận Ping**; thông thường không cần tự `sendPong(...)` trong `onPing`.
6. Thiết kế state machine `IDLE → PING_SENT → PONG_RECEIVED` hoặc `SUSPECT`, sử dụng thời gian đơn điệu `System.nanoTime()`, một Ping chưa được xác nhận tại một thời điểm.
7. Phân biệt **send timeout**, **Pong timeout**, **idle threshold**, **TCP connection failure** và **application readiness**.
8. Tránh đánh dấu sai kết nối chết khi có jitter, network congestion, JVM pause, scheduling delay hoặc listener không được cấp demand.
9. Tích hợp deadline, cancellation, `sendClose`/`abort`, retry backoff, jitter, observability và resource cleanup.
10. Giải thích giới hạn trình duyệt: JavaScript `WebSocket` của browser **không** cho ứng dụng trực tiếp gửi/nhận Ping/Pong control frame; phải dùng message-level heartbeat nếu cần xác nhận business code.
11. Chạy và đọc stdout chính xác của hai ví dụ Java 17+: **real frame handshake/ping/pong** và **policy deadline**.
12. Viết test xác nhận Pong đúng payload, Pong không khớp, Pong quá hạn, unsolicited Pong, server auto Pong và mạng half-open.

## 3. Mô hình luồng Ping/Pong và trường hợp im lặng

~~~text
CLIENT WEB SOCKET                                  SERVER WEB SOCKET
      |                                                   |
      |  PING payload=seq-71 (control opcode 0x9)          |
      |-------------------------------------------------->|
      |                                                   |
      |  PONG payload=seq-71 (control opcode 0xA)          |
      |<--------------------------------------------------|
      |       correlation matched: seq-71                 |
      |       ghi RTT, đánh dấu probe thành công          |
      |                                                   |
      | ... đợi theo heartbeat interval ...               |
      |                                                   |
      |  PING payload=seq-72                              |
      |-------------------------------------------------->X  network path bị mất
      |                                                   X
      |  Không nhận PONG seq-72 trước deadline            X
      |       ↓                                           |
      |  SUSPECT → cleanup/reconnect theo policy          |
      |                                                   |
~~~

Có **ba lớp thông tin** khác nhau:

| Lớp | Tín hiệu | Có thể kết luận | Không thể kết luận |
| --- | --- | --- | --- |
| TCP/transport | ACK, keepalive probe, FIN/RST, socket error | Đường truyền ở một thời điểm có một số dấu hiệu sống/chết | Business API khỏe mạnh |
| WebSocket protocol | Ping được phản hồi bằng Pong | WebSocket peer/stack và một đường đi hai chiều đã đáp ứng tại thời điểm probe | DB, queue, consumer business không bị kẹt |
| Ứng dụng | `{"type":"health","seq":...}` → `{"type":"health-ack",...}` | Logic nhận và xử lý loại message đó đã chạy | Mọi chức năng doanh nghiệp đã sẵn sàng |

Pong được gửi **tự động** bởi nhiều WebSocket stacks, kể cả client Java JDK; vì vậy việc app xử lý đơn hàng bị kẹt **không nhất thiết** làm WebSocket ngừng trả Pong. Ngược lại, application ack chậm vẫn có thể do một handler bận hoặc client background-throttling, chưa chắc TCP đã đứt.

## 4. RFC 6455 quy định gì về WebSocket Ping và Pong?

### 4.1. Control frame, opcode và giới hạn payload

Trong RFC 6455, các WebSocket control frames gồm:

| Control frame | Opcode | Công dụng |
| --- | --- | --- |
| Close | `0x8` | Bắt đầu/đáp lại quá trình đóng kết nối |
| Ping | `0x9` | Kiểm tra khả năng phản hồi/keepalive |
| Pong | `0xA` | Phản hồi Ping hoặc gửi chủ động |

Ràng buộc:

- **Payload tối đa 125 bytes** cho mọi control frame. Java `sendPing(ByteBuffer)` sẽ từ chối payload dài hơn bằng `IllegalArgumentException` qua kết quả future theo hợp đồng API.
- **Control frames không được phân mảnh**: bit FIN phải được đặt (frame là final), không chia control frame thành nhiều continuation frames.
- Control frames **có thể xen giữa các fragments của một data message** để tránh phải chờ transfer file cực dài rồi mới gửi Ping.
- Client-to-server frames cần **mask** theo RFC 6455; server-to-client frames không dùng masking theo quy tắc protocol. Đây là điều quan trọng khi tự viết TCP test fixture.
- Payload Ping/Pong là **bytes**, không phải một JSON business message, không có semantics format bắt buộc.
- WebSocket client và server đều **có thể gửi Ping** khi kết nối đã thiết lập và chưa đóng.
- Nếu nhận Ping khi chưa nhận Close, peer **phải gửi Pong** và nên làm sớm nhất có thể; **Pong trả lời phải chứa payload giống Ping được phản hồi**.
- Nếu có nhiều Ping đang chờ, RFC cho phép peer chỉ trả Pong cho Ping **mới nhất** trong một số điều kiện. Vì vậy heartbeat application nên giới hạn một probe đang chờ thay vì bắn hàng loạt.
- Một endpoint có thể gửi **Pong không kèm Ping trước đó** (*unsolicited Pong*). Không có nghĩa phía kia phải gửi thêm Pong để đáp lại Pong đó.

~~~text
Frame từ Java client đến server:
FIN=1 | opcode=0x9 (Ping) | MASK=1 | length <=125 | masking key | payload bytes

Frame phản hồi từ server:
FIN=1 | opcode=0xA (Pong) | MASK=0 | length <=125 | same payload bytes
~~~

**Tránh nhầm lẫn:** `PING` viết trong một text message bình thường không có cùng opcode với WebSocket **Ping control frame**. Một server nhận WebSocket text `"PING"` có thể chỉ coi đó là chat text, không tự bắt buộc trả Pong theo RFC.

### 4.2. Gửi thành công không có nghĩa peer đã trả lời

Giả sử:

~~~java
webSocket.sendPing(ByteBuffer.wrap(new byte[]{1, 2, 3}))
         .get(5, TimeUnit.SECONDS);
~~~

Đây là **mảnh code** với `webSocket` là WebSocket đã kết nối, imports `ByteBuffer` và `TimeUnit`. Khi future thành công, JDK cho biết **send operation đã hoàn tất**. Nó **không có nghĩa** server đã nhận, xử lý Ping hoặc gửi Pong. Trên TCP, việc bytes được enqueue/chuyển qua transport cũng không chứng minh business layer đã xử lý.

Muốn xác nhận Pong, cần **Listener.onPong(...)**, đối chiếu payload của Pong với Ping đang chờ, và có deadline độc lập.

### 4.3. Pong không được đòi phản hồi tiếp

Một sơ đồ sai dễ tạo ping-pong storm:

~~~text
Client Ping → Server Pong → Client Pong → Server Pong → ...  (SAI)
~~~

Phản hồi đúng:

~~~text
Client Ping(payload=x) → Server Pong(payload=x) → KẾT THÚC probe.
~~~

Unsolicited Pong là hợp lệ, nhưng **không được đòi Pong đáp ứng Pong**. Nếu application chọn gửi Pong tự phát làm tín hiệu một chiều, bên nhận có thể quan sát traffic/ước lượng liveness nhưng đó không thay thế phép đo cặp Ping→Pong của người gửi.

## 5. Java 17 API: sendPing, onPing, onPong, request(n)

Java 17 cung cấp client WebSocket trong module `java.net.http` (có từ Java 11):

~~~java
HttpClient client = HttpClient.newHttpClient();
WebSocket webSocket = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(URI.create("wss://example.com/events"), listener)
        .get(10, TimeUnit.SECONDS);
~~~

Đây là **mảnh code**: `listener` phải được định nghĩa trước, URI minh họa không được kiểm thử, method khai báo `throws Exception` hoặc xử lý timeout/exception. `connectTimeout` của builder áp cho việc **thiết lập WebSocket**, không tự cài **heartbeat định kỳ sau khi đã kết nối**.

### 5.1. Bảng API trọng yếu

| API | Tác dụng | Cạm bẫy cần tránh |
| --- | --- | --- |
| `WebSocket.sendPing(ByteBuffer)` | Gửi Ping frame, trả future cho send operation | Future thành công **không phải** Pong ack |
| `WebSocket.sendPong(ByteBuffer)` | Gửi Pong frame chủ động | JDK đã tự reply Ping; không gửi thủ công lặp vô ích |
| `WebSocket.Listener.onPing(WebSocket, ByteBuffer)` | Callback nhận Ping | Java implementation tự gửi reciprocal Pong |
| `WebSocket.Listener.onPong(WebSocket, ByteBuffer)` | Callback nhận Pong | Phải copy/read payload trong thời gian sở hữu buffer |
| `WebSocket.Listener.onOpen(WebSocket)` | Callback sau handshake | Gọi `webSocket.request(n)` để cấp quyền receive callback |
| `WebSocket.request(long n)` | Tăng demand count của các receive callbacks | Nếu không request thêm, app có thể **không nhận onPong** dù mạng vẫn tốt |
| `WebSocket.Listener.onClose(...)` | Thấy WebSocket Close frame | Dừng heartbeat, đóng input/output theo lifecycle |
| `WebSocket.Listener.onError(...)` | Được thông báo lỗi receive/callback | Tắt probe, dọn resources; không đợi Pong vô hạn |
| `WebSocket.sendClose(1000, reason)` | Khởi tạo close handshake có trật tự | Future báo send hoàn thành, không có nghĩa peer/business đã graceful stop |
| `WebSocket.abort()` | Đóng input/output ngay, hủy kết nối đột ngột | Chỉ nên dùng khi timeout/cần force, không thay graceful close bình thường |
| `WebSocket.isInputClosed()/isOutputClosed()` | Quan sát hai chiều input/output | Hai chiều có thể đóng độc lập; cờ hiện tại không thay active probe |

**Quy tắc buffer:** byte trong `ByteBuffer` truyền cho `sendPing` phải nằm từ `position` tới `limit` và không được truy cập/sửa trước khi CompletableFuture send hoàn tất. Khi xử lý `onPong`, copy bytes trước khi hoàn tất `CompletionStage` của callback; JDK có thể thu hồi buffer sau đó.

### 5.2. JDK tự phản hồi Ping

Theo Java 17 `WebSocket`, implementation tự phản hồi Ping bằng Pong và tự xử lý Close protocol reply. Vì vậy một `Listener` bình thường **không cần viết `sendPong(...)` trong `onPing(...)`**.

~~~java
@Override
public CompletionStage<?> onPing(
        WebSocket ws, ByteBuffer payload) {
    // Java WebSocket implementation tự gửi Pong đúng protocol.
    // Nếu override callback, vẫn phải cấp demand khi muốn nhận event tiếp.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là **mảnh method**, cần đặt trong class implement `WebSocket.Listener` và imports `WebSocket`, `ByteBuffer`, `CompletionStage`, `CompletableFuture`. Nếu không cần logic khi thấy Ping, có thể **không override `onPing`**; default listener implementation cũng gọi `request(1)`.

**Điểm tinh tế:** “Pong tự động” không chứng minh handler nghiệp vụ của server hoặc client khỏe. Khi WebSocket stack vẫn có năng lực phản hồi protocol-level Ping, nó có thể trả Pong dù task xử lý business message đang treo.

### 5.3. Demand/backpressure trong Listener

Một `WebSocket` mới xây có demand count ban đầu bằng **0**. JDK chỉ gọi receive callbacks khi ứng dụng đã gọi `request(n)`; mỗi callback receive tiêu thụ một đơn vị demand. Vì vậy:

~~~java
@Override
public void onOpen(WebSocket ws) {
    ws.request(1);
}

@Override
public CompletionStage<?> onPong(
        WebSocket ws, ByteBuffer payload) {
    byte[] bytes = new byte[payload.remaining()];
    payload.get(bytes);
    // Xử lý bytes tại đây; không giữ lại ByteBuffer ngoài callback.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là **mảnh code**, thuộc một `Listener`; cần các imports tương ứng. Khi override `onOpen` mà quên `request(1)`, bạn có thể không bao giờ thấy `onPong` và đánh dấu timeout **giả**. Khi override `onPong` mà không cấp demand cho event tiếp, Pong sau đó cũng có thể không được dispatch.

Các default methods `onText/onBinary/onPing/onPong` của Java 17 thực hiện `request(1)` nếu bạn không override. Nếu override bất kỳ callback nào, hãy quản lý demand có chủ ý; đừng gọi `request(Long.MAX_VALUE)` như lối tránh backpressure trong hệ thống có thể nhận message lớn/vô hạn.

**Không giả định callback luôn chạy trên một thread cố định:** JDK bảo đảm tuần tự hóa listener callbacks của một WebSocket, nhưng scheduler/timer của bạn chạy ở thread khác. Chia sẻ biến `pendingPing`, `lastPongNanos` hoặc `status` phải thread-safe (atomic, lock hoặc đồng bộ event loop).

### 5.4. Lỗi sendPing và giới hạn đồng thời

Theo Java 17 `WebSocket.sendPing`:

- Payload từ `ByteBuffer` không được vượt **125 bytes**.
- Một Ping/Pong send đang pending có thể khiến send tiếp thất bại qua `IllegalStateException` trong future.
- IOException có thể xảy ra nếu I/O lỗi hoặc output đã đóng.
- `sendPing` không tự cung cấp **Pong timeout**; Java application phải định nghĩa deadline/scheduler.
- `sendPong` hiếm khi cần để trả lời Ping vì implementation tự làm điều đó.

**Đừng gửi một Ping mới khi chưa xử lý Ping trước** chỉ để “chắc ăn”. Nếu peer gửi Pong cho Ping mới nhất, bản ghi Ping cũ có thể mãi không match; bạn tự tạo false alarm và thêm traffic khi mạng đã tắc.

## 6. Khi nào được xem là “kết nối im lặng”?

Một kết nối có thể “im lặng” theo các nghĩa khác nhau:

| Trạng thái | Điều quan sát được | Heartbeat giúp gì? |
| --- | --- | --- |
| Không có chat/event mới | Không có application messages | Ping/Pong xác nhận WebSocket stack vẫn đáp ứng |
| Proxy cắt idle connection âm thầm | Không có Close/FIN/RST ở client | Ping/Pong có thể phát hiện mất đường đi sau timeout |
| NAT mapping hết hạn | Gói gửi đi không còn quay về như cũ | Probe có thể làm lộ việc network path bị mất |
| JVM pause hoặc listener thiếu demand | Pong có thể đến nhưng chưa được callback xử lý | Có nguy cơ **false positive** |
| Server chỉ phản hồi control frames | Ping vẫn được Pong, business API treo | **Không phát hiện business readiness** |
| Server bị overload nặng | Pong chậm, callback thiếu CPU | Timeout có thể đánh dấu suspect, không biết nguyên nhân |
| Thiết bị đổi Wi-Fi sang 4G | Kết nối TCP cũ có thể không dùng được | Probe giúp biết phải reconnect |
| Browser tab bị suspend | Timer JS giãn lâu hoặc không chạy | App heartbeat kém chính xác khi background |
| Mạng chậm hoặc packet loss nhất thời | Pong đến sau deadline | Timeout là policy, không phải chứng cứ peer chết tuyệt đối |
| Một chiều network vẫn đi, chiều về mất | Ping có thể rời client, Pong không quay lại | Probe hai chiều nhận diện mất responsiveness |
| Proxy/LB idle timeout rất ngắn | WS có thể bị đóng trước probe kế | Cần cấu hình heartbeat phù hợp với hạ tầng |

**Phát hiện connection “silent” luôn là bài toán cân bằng** giữa thời gian phát hiện, chi phí probe, nguy cơ false positive và timeout của hạ tầng.

## 7. Chọn interval và deadline đúng cách

Các khái niệm:

- **Heartbeat interval** `I`: khoảng cách mục tiêu giữa các lần bắt đầu probe (khi không có probe đang chờ).
- **Pong timeout** `T`: tối đa cho phép từ khi probe đủ điều kiện được gửi tới lúc nhận Pong tương ứng.
- **Miss threshold** `M`: số lần thất bại liên tiếp trước khi force-close (nếu policy chọn cách này).
- **Idle threshold**: chỉ ping sau khi không có network/app traffic một thời gian hay ping đều bất kể traffic.
- **Jitter**: lệch pha nhỏ trong lịch gửi để nhiều client không đồng loạt flood server.
- **RTT estimate**: `PongReceivedAt - PingSentAt`, xấp xỉ round-trip cả event processing và scheduling; không chỉ network RTT.

Ví dụ minh họa *không phải khuyến nghị phổ quát*: `I=20 giây`, `T=8 giây`, có thể cần nhiều miss liên tiếp. Trên đường mạng di động hoặc thiết bị ngủ nền, T=8 giây có thể quá thấp; trên server latency thấp, ngưỡng có thể khác. Chọn số bằng dữ liệu đo thật: p95/p99 Pong RTT, GC pauses, network jitter, proxy/LB idle settings và yêu cầu thời gian phát hiện.

### 7.1. Dùng đồng hồ đơn điệu

**Không** tính deadline bằng `System.currentTimeMillis()` rồi giả định đồng hồ hệ điều hành không bao giờ nhảy. NTP chỉnh giờ hoặc người dùng đổi giờ có thể làm mốc chênh lệch sai.

Trong production:

~~~java
long startedAt = System.nanoTime();
long timeoutNanos = TimeUnit.SECONDS.toNanos(8);

if (System.nanoTime() - startedAt >= timeoutNanos) {
    // Hết hạn theo chính sách, mark SUSPECT.
}
~~~

Đây là **mảnh code**; `TimeUnit` từ `java.util.concurrent`. Dùng hiệu giữa hai mốc `nanoTime()` (đồng hồ đơn điệu) và loại bỏ phép so với epoch time. Đừng gọi `System.nanoTime()` là thời gian UTC hoặc dùng để ghi timestamps log như `Instant.now()`.

### 7.2. Mỗi lúc một outstanding Ping

~~~text
IDLE
  |
  | interval elapsed
  v
PING_PENDING(seq=47, sentAt)
  |        |
  |        +-- onPong(seq=46)  → IGNORE (stale/unsolicited)
  |        |
  |        +-- onPong(seq=47)  → ACKED → IDLE
  |        |
  |        +-- timeout        → SUSPECT → policy reconnect/abort
  |
  +-- Cấm tự tạo seq=48 khi seq=47 vẫn pending
~~~

Điều này giúp tránh hai lỗi:

1. Một Pong cũ/unsolicited làm bạn lầm tưởng Ping mới đã được xác nhận.
2. Nhiều Ping chồng nhau làm khó đối chiếu và có thể bị peer **chỉ trả Ping mới nhất** theo RFC.

Payload có thể chỉ là `seq` hoặc nonce ngắn; **không** đặt JWT, token bí mật hay dữ liệu nhạy cảm vào Ping payload. Đây là control frame, không phải kênh business metadata an toàn riêng. Tốt nhất giữ payload vài byte và đối chiếu đúng bytes, không chỉ “có một Pong bất kỳ”.

### 7.3. Gửi thất bại khác với không nhận Pong

Heartbeat scheduler nên phân biệt:

~~~text
sendPing()              → API khởi tạo send
future SEND_SUCCESS     → frame đã gửi theo hợp đồng JDK
onPong(matching payload)→ peer đã đáp ứng probe
Pong deadline expired   → chưa quan sát matching Pong đúng hạn
sendPing SEND_FAILURE   → lỗi local send / output closed / I/O
~~~

Nếu send thất bại ngay, đừng bắt đầu đếm “Pong response bị mất” như thể Ping đã rời client. Nếu send queue bị tắc trước khi frame thật sự được gửi, policy phải phân biệt **send deadline/backpressure** với Pong deadline; đo RTT từ thời điểm phù hợp (khi send hoàn tất hoặc một mốc đã ghi và được định nghĩa rõ), tránh gán mọi chậm trễ cho server.

## 8. Ví dụ chạy được 1 — WebSocket thật: Ping, Pong tự động và probe quá hạn

### 8.1. Bài thử kiểm chứng điều gì?

Chương trình tự dựng một **WebSocket test server tối giản trên TCP loopback** với handshake RFC 6455 để chúng ta không cần framework, Internet hoặc server bên ngoài. Client là **`java.net.http.WebSocket` thực sự** của Java 17.

Luồng test:

1. Local `ServerSocket` nhận request HTTP Upgrade, lấy `Sec-WebSocket-Key`, tính `Sec-WebSocket-Accept` theo RFC 6455, trả `101 Switching Protocols`.
2. Java WebSocket client gửi **Ping `seq-1`**; server giải mask frame và trả **Pong `seq-1`**.
3. Listener `onPong` đối chiếu payload và hoàn tất `CompletableFuture` của probe đầu tiên.
4. Server gửi **Ping `srv-1`** cho client. JDK tự gửi reciprocal Pong; test server ghi nhận, **không** cần client tự gọi `sendPong`.
5. Client gửi **Ping `seq-2`**; server cố ý **không phản hồi** để mô phỏng silent/unresponsive WebSocket peer.
6. Client chờ tối đa 600 ms cho **Pong seq-2**; hết hạn, in cờ true và `abort()` để kết thúc demo.
7. Server trả thông tin số Ping và đã nhận auto Pong từ client.

**Lưu ý:** proxy/firewall/TCP behavior ngoài đời phức tạp hơn test cố ý không trả Pong. Demo nhằm chứng minh **matching + deadline**, không phải chứng minh một lần timeout đủ để kết luận connection chết chắc.

### 8.2. Tệp `WebSocketPingPongHeartbeatDemo.java`

~~~java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class WebSocketPingPongHeartbeatDemo {
    record Frame(int opcode, byte[] body) {}

    static String readHttpHeaders(InputStream stream) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        int state = 0;
        while (result.size() < 8192) {
            int b = stream.read();
            if (b < 0) throw new EOFException("Handshake incomplete");
            result.write(b);
            state = switch(state) {
                case 0 -> b == '\r' ? 1 : 0;
                case 1 -> b == '\n' ? 2 : b == '\r' ? 1 : 0;
                case 2 -> b == '\r' ? 3 : 0;
                default -> b == '\n' ? 4 : b == '\r' ? 1 : 0;
            };
            if (state == 4) return result.toString(StandardCharsets.US_ASCII);
        }
        throw new IOException("Handshake header too long");
    }

    static Frame readFrame(InputStream in) throws IOException {
        int first = in.read();
        if (first < 0) return null;
        int second = in.read();
        if (second < 0) throw new EOFException("No frame length");
        boolean masked = (second & 0x80) != 0;
        int length = second & 0x7f;
        if ((first & 0x80) == 0 || length > 125 || !masked) {
            throw new IOException("Demo expects short, masked FIN client frame");
        }
        byte[] mask = in.readNBytes(4);
        byte[] data = in.readNBytes(length);
        if (mask.length != 4 || data.length != length) throw new EOFException();
        for (int i=0;i<data.length;i++) data[i] ^= mask[i%4];
        return new Frame(first & 0x0f, data);
    }

    static void sendControl(OutputStream out, int opcode, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.US_ASCII);
        if (data.length > 125) throw new IllegalArgumentException();
        out.write(0x80 | opcode);
        out.write(data.length);
        out.write(data);
        out.flush();
    }

    static String serve(ServerSocket server) throws Exception {
        try (Socket peer = server.accept()) {
            peer.setSoTimeout(5000);
            InputStream in=peer.getInputStream();
            OutputStream out=peer.getOutputStream();
            String headers = readHttpHeaders(in);
            String key=null;
            for (String line:headers.split("\r\n")) {
                if (line.regionMatches(true,0,"Sec-WebSocket-Key:",0,18)) {
                    key=line.substring(18).trim();
                }
            }
            if (key == null) throw new IOException("No websocket key");
            byte[] digest=MessageDigest.getInstance("SHA-1").digest(
                (key+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                   .getBytes(StandardCharsets.US_ASCII));
            String accept=Base64.getEncoder().encodeToString(digest);
            out.write(("HTTP/1.1 101 Switching Protocols\r\n"+
                       "Upgrade: websocket\r\n"+
                       "Connection: Upgrade\r\n"+
                       "Sec-WebSocket-Accept: "+accept+"\r\n\r\n")
                    .getBytes(StandardCharsets.US_ASCII));
            out.flush();
            int count=0;
            boolean clientEchoedPing=false;
            while(true) {
                Frame frame;
                try {frame=readFrame(in);}catch(SocketException e){break;}
                if(frame==null) break;
                String payload=new String(frame.body(),StandardCharsets.US_ASCII);
                if(frame.opcode()==9) {
                    count++;
                    if(count==1) {
                        sendControl(out,10,payload);
                        sendControl(out,9,"srv-1");
                    }
                    // Deliberately ignore the second Ping.
                } else if(frame.opcode()==10) {
                    if(payload.equals("srv-1")) clientEchoedPing=true;
                } else if(frame.opcode()==8) {
                    break;
                }
            }
            return "clientPingCount="+count+
                   " autoPongReceived="+clientEchoedPing;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker=Executors.newSingleThreadExecutor();
        try(ServerSocket server=new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);
            Future<String> serverResult=worker.submit(() -> serve(server));

            CompletableFuture<String> pong1=new CompletableFuture<>();
            CompletableFuture<String> pong2=new CompletableFuture<>();
            WebSocket.Listener listener = new WebSocket.Listener() {
                @Override public void onOpen(WebSocket ws) {
                    ws.request(1);
                }
                @Override public CompletionStage<?> onPong(
                        WebSocket ws, ByteBuffer payload) {
                    byte[] data=new byte[payload.remaining()];
                    payload.get(data);
                    String token=new String(data,StandardCharsets.US_ASCII);
                    if(token.equals("seq-1"))pong1.complete(token);
                    if(token.equals("seq-2"))pong2.complete(token);
                    ws.request(1);
                    return CompletableFuture.completedFuture(null);
                }
                @Override public void onError(WebSocket ws, Throwable error) {
                    pong1.completeExceptionally(error);
                    pong2.completeExceptionally(error);
                }
            };
            WebSocket ws=HttpClient.newHttpClient().newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(URI.create("ws://127.0.0.1:"+
                            server.getLocalPort()+"/health"),listener)
                    .get(5,TimeUnit.SECONDS);
            try {
                ws.sendPing(ByteBuffer.wrap(
                        "seq-1".getBytes(StandardCharsets.US_ASCII)))
                    .get(5,TimeUnit.SECONDS);
                System.out.println("Matched first pong: "+
                        pong1.get(5,TimeUnit.SECONDS));

                ws.sendPing(ByteBuffer.wrap(
                        "seq-2".getBytes(StandardCharsets.US_ASCII)))
                    .get(5,TimeUnit.SECONDS);
                boolean expired;
                try {
                    pong2.get(600,TimeUnit.MILLISECONDS);
                    expired=false;
                } catch(TimeoutException expected) {
                    expired=true;
                }
                System.out.println("Second pong deadline exceeded: "+expired);
                if(expired)ws.abort();
            } finally {
                ws.abort();
            }
            System.out.println("Server: "+serverResult.get(5,TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Lệnh biên dịch với target Java 17, chạy JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 WebSocketPingPongHeartbeatDemo.java
java WebSocketPingPongHeartbeatDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK 24 với `javac --release 17`:**

~~~text
Matched first pong: seq-1
Second pong deadline exceeded: true
Server: clientPingCount=2 autoPongReceived=true
~~~

### 8.3. Bóc tách kết quả

- `Matched first pong: seq-1` chứng minh `onPong` **đã nhận đúng payload của probe đang chờ**, chứ không chỉ bất kỳ Pong.
- `Second pong deadline exceeded: true` chứng minh **không quan sát thấy matching Pong seq-2 trong 600 ms** của bài thử. Nó **không phải bằng chứng tuyệt đối** peer đã chết; trong demo server sống nhưng cố tình không trả.
- `clientPingCount=2` chứng minh server nhận đủ **hai Ping control frames** từ Java client.
- `autoPongReceived=true` chứng minh server gửi Ping `srv-1` rồi nhận reciprocal Pong của JDK client, dù listener **không override `onPing` hoặc tự `sendPong`**.
- Client frames dùng mask, server frames không dùng mask; handshake `Sec-WebSocket-Accept` là yêu cầu protocol, **không phải cryptographic authentication của server**.
- Code dùng `sendPing().get` **cho send completion**, và `pong1.get/pong2.get` **cho matching Pong**. Hai futures này mang ý nghĩa khác nhau.
- `ws.abort()` là **cleanup bắt buộc** cho phép bài test kết thúc ngay dù server cố ý im lặng; production có thể dùng close handshake trước khi force abort tùy policy.

### 8.4. Giới hạn của test fixture

Máy chủ WebSocket tự viết ở trên **không** phải WebSocket server production:

- Chỉ nhận **một** TCP client, chỉ parse short masked FIN control frames, không xử lý data frame dài, fragmentation, compression, nhiều sessions, authorization, validation đầy đủ, TLS, quotas hoặc đóng chuẩn trong mọi trường hợp.
- Chỉ cho `ws://127.0.0.1`; không mở public proxy hoặc listener Internet, không dùng fixture này trong hệ thống thật.
- Dùng `SHA-1` để tính `Sec-WebSocket-Accept` **theo handshake RFC**, không phải để hash password hay xác thực server; security của WSS cần TLS/hostname validation riêng.
- Timeout 600 ms là để test chạy nhanh trên loopback; **không** nên lấy làm giá trị mặc định Internet/mạng di động.
- Trong production, thời gian phản hồi có thể chậm bất thường khi tải cao, GC stop-the-world, scheduler bị starvation hoặc thiết bị ngủ nền.

Nếu cần WebSocket server đầy đủ, hãy dùng thư viện/server được duy trì và có chính sách security, rate limit, authentication, timeout và capacity.

## 9. Ví dụ chạy được 2 — State machine heartbeat với mốc thời gian mô phỏng

Ví dụ đầu cho biết **wire behavior**; ví dụ này tập trung vào **policy**. Chúng ta mô phỏng mili-giây bằng biến `nowMillis` tự đưa vào, không gọi sleep hay phụ thuộc thời gian thực. Điều này tạo unit test ổn định cho các quyết định:

- t=0: được phép gửi `seq-1`.
- Nhận Pong `seq-old` không khớp: **không** coi là thành công.
- Nhận Pong `seq-1` tại t=35: thành công, RTT đo được 35 ms.
- t=70: chưa đủ interval 100 ms nên **IDLE**.
- t=120: gửi `seq-2`.
- t=140: vẫn chờ.
- t=171: vượt Pong timeout 50 ms từ t=120 nên **SUSPECT**.

### 9.1. Tệp `HeartbeatDecisionDemo.java`

~~~java
public class HeartbeatDecisionDemo {
    enum Action { SEND_PING, IDLE, WAIT_FOR_PONG, SUSPECT }

    static final class Policy {
        private final long intervalMillis;
        private final long pongTimeoutMillis;
        private long lastSentMillis;
        private long sentAtMillis;
        private int nextSequence;
        private String pending;
        private long lastRttMillis = -1;

        Policy(long intervalMillis, long pongTimeoutMillis) {
            if (intervalMillis <= 0 || pongTimeoutMillis <= 0)
                throw new IllegalArgumentException();
            this.intervalMillis = intervalMillis;
            this.pongTimeoutMillis = pongTimeoutMillis;
            this.lastSentMillis = -intervalMillis;
        }

        Action check(long nowMillis) {
            if (pending != null) {
                return nowMillis - sentAtMillis >= pongTimeoutMillis
                        ? Action.SUSPECT : Action.WAIT_FOR_PONG;
            }
            if (nowMillis - lastSentMillis < intervalMillis)
                return Action.IDLE;
            pending = "seq-" + ++nextSequence;
            sentAtMillis = nowMillis;
            lastSentMillis = nowMillis;
            return Action.SEND_PING;
        }

        String pendingToken() {
            return pending;
        }

        boolean onPong(String token, long nowMillis) {
            if (pending == null || !pending.equals(token))
                return false;
            lastRttMillis = Math.max(0, nowMillis - sentAtMillis);
            pending = null;
            return true;
        }

        long lastRttMillis() {
            return lastRttMillis;
        }
    }

    public static void main(String[] args) {
        Policy heartbeat = new Policy(100, 50);
        System.out.println("t=0: " + heartbeat.check(0) +
                " " + heartbeat.pendingToken());
        System.out.println("Wrong pong accepted: " +
                heartbeat.onPong("seq-old", 15));
        System.out.println("Matching pong accepted: " +
                heartbeat.onPong("seq-1", 35));
        System.out.println("Measured RTT millis: " +
                heartbeat.lastRttMillis());
        System.out.println("t=70: " + heartbeat.check(70));
        System.out.println("t=120: " + heartbeat.check(120) +
                " " + heartbeat.pendingToken());
        System.out.println("t=140: " + heartbeat.check(140));
        System.out.println("t=171: " + heartbeat.check(171));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 HeartbeatDecisionDemo.java
java HeartbeatDecisionDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
t=0: SEND_PING seq-1
Wrong pong accepted: false
Matching pong accepted: true
Measured RTT millis: 35
t=70: IDLE
t=120: SEND_PING seq-2
t=140: WAIT_FOR_PONG
t=171: SUSPECT
~~~

### 9.2. Vì sao state machine hữu ích?

**Không phụ thuộc scheduler timing** giúp test những trường hợp mà sleep-based test thường bỏ sót. Với state machine, có thể chứng minh:

- **Tối đa một pending token** vì `check` không tạo token mới nếu `pending != null`.
- **Matching bắt buộc**: Pong cho `seq-old` không hoàn tất `seq-1`.
- **RTT** chỉ được cập nhật khi Pong hợp lệ.
- **Timeout** được tính từ mốc đã lưu, không do tổng thời gian từ khi client tạo WebSocket.
- **SUSPECT là quyết định policy**, không được đổi thành `DEAD_CONFIRMED` nếu chưa có bằng chứng terminal mạnh hơn.

**Giới hạn demo policy:** `nowMillis` là đồng hồ mô phỏng, object `Policy` chưa thread-safe. Khi tích hợp với Java WebSocket thật, dùng `System.nanoTime()`, bảo vệ state qua lock/atomic hoặc event loop, xử lý send future lỗi, close/abort, reconnect, reset trạng thái khi tạo socket mới, và không so token cũ với phiên mới.

Đặc biệt, `check(now) == SEND_PING` trong demo **chỉ là lệnh yêu cầu gửi**; trong production phải ghi nhận trạng thái thành công/thất bại của `sendPing`. Nếu mạng bị nghẽn và tương lai send không hoàn tất, cần send timeout, không được đếm nhầm đó là peer đã nhận Ping.

## 10. Từ ví dụ tới thiết kế heartbeat scheduler trong sản phẩm

Một thiết kế production nên có **lifecycle owner** cho từng WebSocket connection, thay vì scheduler bất kỳ nắm tham chiếu tới một socket đã bị thay thế sau reconnect.

### 10.1. Mô hình state machine

~~~text
CREATED
  | WebSocket handshake xong
  v
ACTIVE
  | interval / idle timer
  v
PING_SENDING
  | future send failed ----> FAILED → cleanup/reconnect
  | future send success
  v
WAITING_PONG(token, deadline)
  |             |
  | onPong match| deadline exceeded / receive error
  v             v
ACTIVE       SUSPECT
                |
                +--> record metric, cancel old socket
                +--> close handshake/abort per policy
                +--> schedule reconnect with backoff+jitter
                v
             RECONNECTING
                |
                v
           new WebSocket session (new token epoch)
~~~

**Không được dùng chung pending token giữa hai WebSocket sessions.** Nếu vừa reconnect và một callback cũ tới muộn, nó không được đánh dấu session mới healthy. Gắn **generation/session ID** vào heartbeat policy để kiểm tra callback thuộc socket nào.

### 10.2. Scheduler: fixed delay và không chồng probe

Java có `ScheduledExecutorService`:

~~~java
ScheduledExecutorService timer =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> task = timer.scheduleWithFixedDelay(
        () -> {
            // 1. Nếu session không ACTIVE, bỏ qua.
            // 2. Nếu pending Ping, kiểm tra deadline/mark suspect.
            // 3. Nếu chưa tới interval, không gửi.
            // 4. Nếu được gửi, tạo nonce và dispatch sendPing.
            // 5. Xử lý send future failure/success riêng.
        },
        0, 1, TimeUnit.SECONDS);
~~~

Đây là **mảnh code kiến trúc**, không phải ứng dụng standalone. Imports `java.util.concurrent.*`; phần logic heartbeat do ứng dụng cung cấp. Tick mỗi giây **không** có nghĩa gửi Ping mỗi giây: chỉ gửi khi state và interval cho phép. Cần `task.cancel(...)` khi socket đóng và shutdown timer khi không còn owner, tránh executor leak. Với hàng nghìn client, không nên tạo một thread pool riêng cho mỗi connection; dùng scheduler chia sẻ có giới hạn và state per-session.

**Cạm bẫy `scheduleAtFixedRate`:** nếu một tick bị chậm lâu, các lần tick có thể chạy sát nhau (dù không đồng thời trên single-thread scheduler), tạo burst hoặc false timeout. `scheduleWithFixedDelay` cộng với state/deadline thường dễ điều khiển hơn, nhưng ứng dụng vẫn phải kiểm tra mốc monotonic thay vì tin tick xảy ra đúng giờ.

### 10.3. Event listener: cập nhật state, không block callback

~~~java
@Override
public CompletionStage<?> onPong(WebSocket ws, ByteBuffer data) {
    byte[] bytes = new byte[data.remaining()];
    data.get(bytes);
    // Gọi heartbeatPolicy nhận nonce, session/generation và now=System.nanoTime().
    // Nếu khớp pending Ping, ghi RTT, clear pending.
    // Không gọi DB hoặc CompletableFuture.get() chờ network tại đây.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là **mảnh code** trong Listener. Dùng parser payload tối giản, có giới hạn; tránh phân bổ byte array lớn (protocol đã giới hạn control frame <=125). Không log raw token bí mật. Nếu scheduler thread và listener thread cùng cập nhật state, phải đồng bộ đúng.

### 10.4. Close bình thường và force abort

Trường hợp ứng dụng chủ động ngừng:

~~~java
socket.sendClose(WebSocket.NORMAL_CLOSURE, "shutdown")
      .orTimeout(3, TimeUnit.SECONDS)
      .whenComplete((ignored, error) -> {
          if (error != null) socket.abort();
      });
~~~

Đây là **mảnh code** (biến `socket` là WebSocket), dùng `CompletableFuture.orTimeout` và `TimeUnit`, có thể cần dọn input/await peer closure tùy API/lifecycle. `sendClose` chỉ khởi tạo quá trình đóng chiều gửi; muốn graceful shutdown đầy đủ phải xử lý `onClose` và đóng hết resources.

Khi **Pong timeout** và kết nối được xem là không thể sử dụng theo policy, `socket.abort()` đóng input/output tức thời. `abort` **không** thực hiện WebSocket close handshake, nên dùng có chủ đích. Đừng vô tình tạo hàng chục lần `abort()` và reconnect đồng thời từ nhiều callbacks: cần atomic terminal transition và single owner.

## 11. Heartbeat không phải gì? Giới hạn không thể bỏ qua

### 11.1. Pong không chứng minh application/business healthy

Nếu một WebSocket server vẫn tự xử lý protocol Ping nhưng thread nghiệp vụ bị treo do deadlock, cache/database lỗi hoặc queue backlog, client vẫn có thể nhận Pong đều đặn.

~~~text
Network alive     : true
WebSocket Pong    : true
Message consumer  : stuck
Database ready    : false
User operation    : failing

=> Protocol heartbeat PASS nhưng business readiness FAIL
~~~

Nếu bạn cần xác nhận **business consumer thực sự xử lý được thông điệp**, thiết kế **application-level request/ack** với correlation ID, timeout và domain-specific signal (ví dụ “worker accepted job”), song **không** coi một ack đơn giản là đảm bảo transaction đã commit.

### 11.2. Missing Pong không chứng minh peer đã chết

Pong có thể trễ vì:

- RTT tăng cao, congestion, packet loss hoặc retransmission của TCP.
- JVM stop-the-world GC pause hoặc CPU starvation.
- WebSocket receive listener bị kẹt hoặc không gọi `request(1)`, khiến `onPong` không được dispatch kịp.
- OS process bị suspend hoặc laptop/browser tab background.
- Server đang quá tải, ưu tiên công việc khác hoặc control frame nằm sau blocked I/O.
- Clock/timer scheduler bị delay; deadline bị đo từ thời điểm không đúng.
- Proxy/LB có flow control và buffering, hoặc tunnel bất thường.
- Peer nhận nhiều Ping, chỉ trả một Pong cho Ping được xử lý gần nhất (được RFC cho phép trong điều kiện nhất định).

Vì vậy timeout nên ghi **SUSPECT/UNRESPONSIVE**. Hành động application có thể vẫn là đóng và reconnect (vì cần đáp ứng SLA), nhưng log phải nói **“không có matching Pong trước hạn”** thay vì **“đã chứng minh server chết”**.

### 11.3. Keepalive không đảm bảo tunnel không bị đóng

Traffic Ping/Pong có thể giúp ngăn một số idle timeout của NAT/proxy/LB, nhưng:

- Không phải proxy nào cũng tính control frames như activity theo đúng cách bạn nghĩ.
- Có thể có **absolute connection lifetime** bất kể traffic.
- Server có thể cố ý đặt max session duration, auth refresh hoặc rolling restart.
- Network migration có thể làm TCP connection cũ không thể phục hồi dù Ping đều trước đó.
- Idle timeout do **application layer** có thể dựa trên business messages và **bỏ qua protocol-level Ping**.

Cần kiểm tra chính sách connection idle/absolute timeout của **mỗi hop**, không chỉ cài interval nhỏ nhất có thể.

### 11.4. TCP keepalive khác WebSocket Ping

| Đặc điểm | TCP keepalive | WebSocket Ping/Pong | Application heartbeat |
| --- | --- | --- | --- |
| Lớp | OS/transport | WebSocket protocol | Business protocol/application |
| Ai cấu hình | OS/socket options/platform | WebSocket endpoint/application/library | Chính ứng dụng |
| Phản hồi | TCP ACK/keepalive handling | Pong control frame | App-defined ack |
| Có kiểm chứng WebSocket stack? | Không nhất thiết | Có trong giới hạn protocol | Có thể đến business consumer |
| Payload correlation ID | Thường không ở app | Có, tối đa 125 bytes | Do app định nghĩa |
| Phát hiện app worker bị treo | Không đảm bảo | Không đảm bảo | Có thể nếu ack xử lý đúng nơi |
| Browser JS trực tiếp điều khiển | Không | **Không** qua browser WebSocket API chuẩn | Có bằng text/binary messages |
| Tác động lên proxy idle | Tùy hop | Có thể, tùy proxy | Có thể, tùy proxy |
| Chính sách timeout | OS-specific, thường không tối ưu SLA | Do app định nghĩa | Do app định nghĩa |

Không thay WebSocket Ping bằng `Socket.setKeepAlive(true)` một cách mù quáng: Java `java.net.http.WebSocket` không cho API trực tiếp lấy socket để bật TCP keepalive trên mọi runtime, và OS defaults có thể rất lâu. Khi cần heartbeat chính xác ở cấp ứng dụng, dùng Ping/Pong WebSocket hoặc protocol riêng theo môi trường.

## 12. Đặc biệt: WebSocket trong trình duyệt không có sendPing()

Java application có API `WebSocket.sendPing(...)`, nhưng browser WebSocket JavaScript API thông thường chỉ cho gửi text/binary qua `socket.send(...)`, theo dõi `onmessage`, `onopen`, `onclose`, `onerror` và `readyState`. Nó **không expose control-frame Ping/Pong** cho JavaScript.

Vì vậy:

- Server có thể gửi native Ping control frame; browser network stack thường phản hồi Pong tự động.
- JavaScript browser code **không trực tiếp gọi native Ping hoặc nhận native Pong callback** để đo RTT.
- Nếu muốn client-side heartbeat với browser, định nghĩa **application-level message** như text JSON:

~~~json
{"type":"heartbeat","seq":"42","sentAt":123456789}
~~~

Server trả:

~~~json
{"type":"heartbeat-ack","seq":"42"}
~~~

Đây là **JSON minh họa**, không phải native control frame. Server phải **chủ động implement handler và ack** theo protocol của ứng dụng; không có RFC buộc server WebSocket tự trả heartbeat-ack cho JSON đó. Payload `sentAt` ở đây chỉ là dữ liệu demo, không phải clock synchronization. Với browser, khi tab suspended/throttled, timer app có thể trễ nhiều; không nên kết luận server chết từ một tick trễ rồi reconnect ồ ạt.

Tùy kiến trúc, có thể dùng **server-initiated Ping** để giữ WebSocket network alive và **client-initiated application-level heartbeat** để đo business processing. Khi hai loại cùng hoạt động, tính riêng traffic và deadlines để tránh probe storms.

## 13. Thiết kế retry và reconnect sau heartbeat timeout

Một heartbeat tốt mà reconnect tệ có thể làm dịch vụ mất ổn định hơn:

~~~text
100.000 clients đang connected
    |
   proxy mất mạng ngắn
    |
100.000 clients cùng timeout 5 giây
    |
100.000 clients reconnect cùng một lúc
    |
server CPU/TLS handshake spike -> outage kéo dài
~~~

**Biện pháp:**

1. Khi heartbeat timeout, chuyển session sang **SUSPECT** theo atomic state; chỉ một flow được quyền đóng/reconnect.
2. Hủy pending operations và timer của socket cũ, tách generation ID để callback cũ không làm “healthy” socket mới.
3. Dùng **exponential backoff với jitter** khi reconnect, ví dụ base delay tăng có giới hạn; không sleep trong network callback.
4. Kiểm soát tối đa số concurrent reconnects và TLS handshakes.
5. Xác thực lại session/token nếu cần; không bỏ authorization chỉ vì đã reconnect cùng user.
6. Có **resumption/replay** cho application messages cần delivery semantics. WebSocket transport không tự đảm bảo event đã được business subscriber xử lý nếu socket đứt.
7. Không tự gửi lại payment/order commands khi không biết server đã commit chưa; dùng request ID, idempotency key và kiểm tra trạng thái.
8. Theo dõi số heartbeat misses, RTT distribution, reconnect attempts, close codes, timeout phases và network/device class.
9. Phân biệt client đóng bình thường khi user logout với timeout không mong muốn.
10. Không tái sử dụng `WebSocket` cũ đã `abort`; tạo một WebSocket session mới và state mới.

**Lưu ý delivery:** Ping/Pong là phép kiểm tra kết nối, **không** là ACK business message. Nhận Pong sau khi gửi chat event không xác nhận người dùng đã thấy event, server đã lưu dữ liệu hay consumer đã xử lý transaction.

## 14. Phát hiện false positives và tránh giám sát sai

### 14.1. Các sự kiện nên log/metric

| Metric/event | Đo cái gì | Tác dụng |
| --- | --- | --- |
| `ws_heartbeat_ping_sent_total` | Số Ping send thành công | Hiểu probe traffic, số clients |
| `ws_heartbeat_send_fail_total` | Ping send future thất bại | Phân biệt lỗi local/output |
| `ws_heartbeat_pong_matched_total` | Pong payload khớp pending | Liveness observed |
| `ws_heartbeat_pong_unmatched_total` | Pong trễ/unsolicited/không khớp | Debug correlation, duplicates |
| `ws_heartbeat_timeout_total` | Deadline thiếu matching Pong | Tỷ lệ suspect, cần phân tích |
| `ws_heartbeat_rtt_ms` | Duration từ mốc gửi tới matching Pong | Baseline p95/p99 và biến động |
| `ws_connection_reconnect_total` | Số reconnect attempts | Có reconnect storms không |
| `ws_connection_close_code` | Close code theo RFC | Tách close hợp lệ và failure |
| `ws_listener_processing_lag_ms` | Thời gian callbacks bị chậm khi đo được | Nhận diện starvation/GC |
| `ws_business_ack_timeout_total` | Application ack quá hạn | Độc lập với protocol Ping |

**Không gắn raw authentication token, user ID nhạy cảm hoặc Pong payload chứa secret vào metric labels** vì high cardinality và bảo mật. Có thể dùng aggregate theo app instance, region, route, connection type và version.

### 14.2. Chẩn đoán theo tầng

~~~text
Không thấy application messages
    |
    +-- Có matching Pong?
    |      |
    |      +-- Có  → WebSocket stack còn đáp ứng,
    |      |          kiểm tra business queue/consumer/authorization
    |      |
    |      +-- Không → kiểm tra network path, listener demand,
    |                 scheduler timing, timeout, GC, proxy/LB
    |
    +-- TCP FIN/RST / onClose / onError?
    |      |
    |      +-- Có  → xác định close reason/codes và reconnect policy
    |      |
    |      +-- Không → half-open/network blackhole có thể xảy ra
    |
    +-- App-level ack có đến?
           |
           +-- Không nhưng Pong có → nghi app consumer bất thường
           +-- Có → một phần business path đã xử lý message
~~~

**Đừng dùng một giá trị `isInputClosed() == false` làm health check hoàn chỉnh.** Nó là trạng thái local, không phải phép thử tích cực qua mạng.

## 15. Kiểm thử heartbeat: không chỉ happy path

| Test | Cách dựng | Kỳ vọng |
| --- | --- | --- |
| Ping→Pong bình thường | Server gửi Pong echo payload | Matching probe thành công |
| Pong sai payload | Server gửi Pong `old` thay vì `seq-current` | Bỏ qua; pending giữ nguyên |
| Pong unsolicited | Server gửi Pong khi không có outstanding Ping | Không coi là ack cho probe tương lai |
| Server cố ý im lặng | Không gửi Pong sau Ping | Timeout → SUSPECT |
| Delayed Pong sau deadline | Pong đến muộn | Policy đánh dấu quá hạn; tránh làm sống lại session đã đóng |
| Chỉ trả Pong cho Ping mới nhất | Có nhiều outstanding probes | Thấy nguy cơ, thiết kế một pending |
| Client auto Pong | Server gửi native Ping | Java 17 client tự gửi Pong echo |
| Listener không request thêm | Override `onPong` bỏ `request(1)` | Callback sau bị chặn; đo false timeout |
| Client sendPing trong khi pending | Gửi liên tiếp không đợi future | Có thể lỗi `IllegalStateException` |
| Payload 126 bytes | `sendPing(ByteBuffer)` quá 125 | Send operation bị từ chối |
| Text frame `"PING"` | Server nhận text, không có Ping opcode | Không tự có Pong control frame |
| Server app worker bị treo | Protocol server vẫn auto Pong | Heartbeat protocol PASS nhưng business FAIL |
| GC pause/timer delay | Chặn scheduler có kiểm soát ở test | Timeout có thể false positive |
| Proxy idle timeout | Test môi trường staging với LB | Chọn interval theo actual idle policy |
| Absolute session timeout | LB đóng sau max life dù traffic đều | Heartbeat không ngăn đóng |
| Network blackhole | Chặn chiều về trong staging | Missing Pong, không có Close ngay |
| Browser background | Throttle/suspend tab ở test | App timer không đáng tin như đồng hồ chính xác |
| Reconnect race | Pong callback cũ tới sau new session | Không xác nhận session mới |
| Mass reconnect | Nhiều clients cùng mất mạng | Jitter/backoff tránh thundering herd |
| Graceful shutdown | Gửi close code 1000 và xử lý onClose | Dừng timer/đóng resources |
| Force abort | Không nhận Pong trong deadline và policy abort | Old socket không còn được sử dụng |

### 15.1. Test nên dùng đồng bộ rõ ràng

Không viết unit test chỉ theo kiểu `Thread.sleep(100)` rồi mong callback chắc đã được gọi. Sử dụng `CompletableFuture` hoặc `CountDownLatch` với timeout cho integration tests; dùng **clock giả lập** cho state machine deadlines.

Ví dụ 1 dùng `CompletableFuture<String> pong1/pong2` để chờ đúng payload và timeout. Ví dụ 2 dùng `nowMillis` để có kết quả deterministic, không phụ thuộc OS scheduler. Hai loại test bổ sung nhau: **wire correctness** và **policy correctness**.

### 15.2. Lưu ý khi kiểm thử trên Internet

Không gửi Ping quá thường xuyên tới server không thuộc quyền kiểm soát. Dùng server local hoặc staging và điều chỉnh tần suất theo hợp đồng dịch vụ. Các test intentionally bad frames, oversized payload hoặc đường truyền bị cố tình gián đoạn chỉ nên chạy trong môi trường được phép, để tránh DOS hoặc spam logs.

## 16. Những lỗi lập trình thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng `sendPing().get()` là Pong ack | Future chỉ đại diện send operation | Dùng `onPong`, nonce matching và deadline |
| Gửi Ping mới mỗi tick dù Ping cũ pending | Khó correlation, có thể bị chỉ trả Pong mới nhất | Tối đa một outstanding probe |
| Coi mọi Pong là phản hồi Ping hiện tại | Có unsolicited/stale Pong | So sánh payload token/session |
| Dùng payload >125 bytes | Vi phạm RFC control frame | Giữ payload ngắn, không fragment |
| Dùng text `"PING"` rồi mong native Pong | Text frame không phải control Ping | Dùng `sendPing` hoặc app ack protocol riêng |
| Tự `sendPong` trong `onPing` của JDK | JDK đã tự reciprocal Pong | Thường chỉ observe và request demand |
| Override `onOpen` mà không `request(1)` | Không nhận callback | Cấp demand rõ |
| Override `onPong` mà không `request(1)` | Có thể không nhận Pong tiếp | Cấp lại demand đúng thời điểm |
| Lưu giữ ByteBuffer của callback sau completion | Buffer có thể được JDK reclaim | Copy nội dung ngay |
| Sửa ByteBuffer send trước khi future complete | Race/corrupt payload | Chờ send future rồi mới reuse |
| Coi Pong là business readiness | Pong do stack tự trả | App-level ack/health với business validation |
| Coi timeout là bằng chứng server chết | Mạng/scheduler có thể chậm | Mark SUSPECT, cấu hình policy phù hợp |
| Dùng `currentTimeMillis` làm đồng hồ deadline | System clock có thể nhảy | Dùng `nanoTime` / monotonic |
| Dùng một timeout rất thấp trên mobile | False positives do suspend/radio/GC | Đo RTT distribution và jitter |
| Gửi heartbeat qua browser JS Ping API | Browser không expose native Ping/Pong | Dùng text/binary app heartbeat |
| Chỉ dựa vào TCP keepalive | OS timing/layer khác | Dùng WS/app heartbeat khi cần |
| Dùng `sendClose` trong mọi network blackhole và đợi vô hạn | Graceful close cũng có thể treo | Bounded close, force abort đúng policy |
| Không dừng scheduler sau socket close | Memory/thread/task leak | Cancel timer, release executor owner |
| Reconnect ngay lập tức không jitter | Thundering herd | Exponential backoff+jitter |
| Không reset token sau reconnect | Callback cũ đánh dấu session mới khỏe | Session/generation ID |
| Retry business write sau heartbeat timeout | Có thể trùng giao dịch | Idempotency key/operation tracking |
| Log Ping payload có secrets | Rò dữ liệu qua logs | Non-secret short nonce, redaction |
| Coi không có onError là khỏe | Half-open không phát sinh lỗi ngay | Active probe + timeout |
| Coi Ping luôn ngăn LB idle timeout | LB có thể có absolute timeout/policy riêng | Kiểm tra hạ tầng từng hop |

## 17. Bài tập và lời giải

### Bài 1 — CompletableFuture của Ping

Client gọi `webSocket.sendPing(buffer).get()` thành công. Có chắc remote đã gửi Pong và application xử lý request gần nhất không?

**Đáp án:** Không. Future xác nhận **send operation**, không phải nhận Pong. Cần `onPong` nhận payload khớp. Và cả Pong đúng cũng không xác nhận business application đã xử lý request khác.

### Bài 2 — Protocol frame hay text?

Ứng dụng gửi WebSocket text message `"PING"` và không nhận Pong control frame. Có phải server vi phạm RFC 6455?

**Đáp án:** Không. `"PING"` là **text data frame**, không phải WebSocket Ping control frame. RFC chỉ yêu cầu phản hồi Pong cho **Ping frame opcode 0x9** khi thỏa điều kiện, không bắt buộc xử lý chữ “PING” trong message.

### Bài 3 — Oversized Ping

Một programmer tạo `ByteBuffer.allocate(200)`, position=0, limit=200 rồi truyền cho `sendPing`. Điều gì sai?

**Đáp án:** 200 bytes vượt giới hạn **125 bytes** của control frame; Java API từ chối theo contract. Dùng payload ngắn, không cố fragment control frame.

### Bài 4 — Pong cũ đến muộn

Pending token hiện là `seq-8`, listener nhận Pong `seq-7`. Có nên đánh dấu session healthy và xóa pending?

**Đáp án:** Không. Pong cũ/unsolicited không chứng minh `seq-8` đã được peer nhận. Giữ pending, chờ matching Pong tới hạn hoặc mark suspect.

### Bài 5 — Không có callback onPong

Server log đã gửi Pong, nhưng client `onPong` không được gọi sau một lần thành công. Ngoài mạng, nên kiểm tra gì?

**Đáp án:** `Listener.onOpen` và `Listener.onPong` có gọi `webSocket.request(1)` để cấp tiếp demand không? Callback nhận bị flow control hạn chế; không được kết luận ngay rằng Pong chưa tới máy.

### Bài 6 — Server vẫn trả Pong nhưng người dùng không nhận message

WebSocket protocol heartbeat luôn PASS, nhưng event consumer không xử lý thông báo. Vì sao?

**Đáp án:** WebSocket stack có thể **tự gửi Pong** tách khỏi business handler. Cần app-level ack/readiness, metrics của queue/worker, không dùng Pong làm bằng chứng “business healthy”.

### Bài 7 — Timeout và trạng thái

Client không nhận matching Pong trong 8 giây; điều đó chứng minh server process chết không?

**Đáp án:** Không. Đó là **timeout theo chính sách**, có thể do network jitter, GC pause, listener demand, overload hoặc peer chết. Đánh dấu SUSPECT; app có thể chủ động reconnect để phục vụ SLA, nhưng log phải chính xác.

### Bài 8 — Pong tự phát

Server gửi unsolicited Pong. Client có bắt buộc gửi Pong đáp lại không?

**Đáp án:** Không. Pong không yêu cầu phản hồi; không tự tạo vòng Pong→Pong. Nếu muốn client phản hồi theo business protocol, phải thiết kế riêng, không dựa trên RFC control Pong.

### Bài 9 — Browser WebSocket

Trình duyệt JavaScript có thể gọi `socket.sendPing(...)` và đọc `onpong` trực tiếp không?

**Đáp án:** Không trong browser WebSocket API chuẩn. Browser xử lý protocol Ping/Pong ở network stack. Với client-side app liveness, gửi **application message** có seq và đợi ack do server định nghĩa.

### Bài 10 — RTT và clock

Vì sao dùng `System.nanoTime()` thay `System.currentTimeMillis()` để đo Pong RTT?

**Đáp án:** `nanoTime` thích hợp đo **thời lượng đơn điệu**; `currentTimeMillis` biểu thị wall clock có thể nhảy do NTP/chỉnh giờ. Không dùng `nanoTime` để hiển thị timestamp UTC.

### Bài 11 — Chọn heartbeat interval

Một reverse proxy đóng connection sau 60 giây idle, client gửi Ping mỗi 5 phút. Có thể ngăn idle timeout không?

**Đáp án:** Thường không. Ping đến quá muộn. Cần hiểu idle policy của proxy/server và đặt interval phù hợp, nhưng vẫn không bảo đảm ngăn **absolute max lifetime** hoặc các chính sách không tính control frame.

### Bài 12 — Reconnect storm

10.000 clients đều timeout đồng loạt và retry ngay sau 0 ms. Nguy cơ gì và sửa thế nào?

**Đáp án:** TLS/connect storm làm server bị quá tải. Dùng exponential backoff, jitter, cap concurrent attempts và chỉ một lifecycle owner per session.

### Bài 13 — TCP keepalive

`Socket.setKeepAlive(true)` có chứng minh WebSocket application responder đang khỏe không?

**Đáp án:** Không. TCP keepalive chỉ kiểm tra một phần transport reachability theo OS policy. Nếu cần WebSocket protocol responsiveness, dùng Ping/Pong. Nếu cần business readiness, dùng app-level ack/health.

### Bài 14 — Case từ demo

Ở ví dụ đầu, server trả Pong `seq-1` nhưng cố ý bỏ qua Ping `seq-2`. Tại sao stdout vẫn có `clientPingCount=2` nhưng timeout là true?

**Đáp án:** Vì server **đã nhận** cả hai Ping nhưng chỉ **phản hồi Ping đầu**. Điều đó chứng minh không nên coi “Ping đã gửi/đã đến remote” là “Pong đã nhận”; timeout là một phép đo riêng.

### Bài 15 — State machine

Một session vừa nhận `seq-1` ở t=35 ms, t=120 gửi `seq-2`, t=171 chưa nhận Pong, timeout 50 ms. Trạng thái nên là gì?

**Đáp án:** **SUSPECT** vì 51 ms từ t=120 vượt hạn 50 ms. Không gọi là `DEAD_CONFIRMED`; chính sách ứng dụng quyết định đóng/reconnect.

## 18. Checklist code review production

- [ ] Tôi phân biệt protocol Ping/Pong, TCP keepalive và application heartbeat.
- [ ] Tôi dùng WebSocket `sendPing(ByteBuffer)`, không nhầm text `"PING"` với control frame.
- [ ] Ping payload <=125 bytes, không phân mảnh; không chứa credentials/secrets.
- [ ] Tôi biết Java 17 client tự gửi reciprocal Pong cho incoming Ping.
- [ ] Tôi không tự gửi duplicate Pong không cần thiết trong `onPing`.
- [ ] Tôi biết send future chỉ là send completion, **không** phải Pong ack.
- [ ] Tôi triển khai `onPong` và so nonce/seq với pending probe đúng session.
- [ ] Tôi xử lý unsolicited/stale Pong mà không hoàn tất probe sai.
- [ ] Tôi gọi `request(1)` ở `onOpen` và các overridden receive handlers khi cần.
- [ ] Tôi không giữ `ByteBuffer` của callback sau khi callback CompletionStage kết thúc.
- [ ] Tôi chỉ cho một outstanding heartbeat Ping ở một thời điểm.
- [ ] Tôi tách send timeout, Pong timeout, callback lag và connection error.
- [ ] Tôi dùng đồng hồ đơn điệu `System.nanoTime()` cho interval/deadline.
- [ ] Tôi chọn heartbeat interval/timeout dựa trên RTT, network/device, proxy/LB policy và SLA.
- [ ] Tôi không coi một missed Pong là bằng chứng tuyệt đối peer chết.
- [ ] Tôi không coi một matching Pong là bằng chứng business API khỏe mạnh.
- [ ] Tôi dùng application ack riêng nếu cần kiểm tra consumer/database/transaction.
- [ ] Tôi hiểu browser JS không điều khiển native WebSocket control Ping/Pong.
- [ ] Tôi cancel scheduled tasks, dừng timer và cleanup khi onClose/onError.
- [ ] Tôi dùng bounded graceful close hoặc `abort` tùy tình huống; tránh treo vô hạn.
- [ ] Tôi giới hạn reconnect attempts và dùng exponential backoff+jitter.
- [ ] Tôi ngăn callback phiên cũ cập nhật heartbeat phiên mới bằng generation/session ID.
- [ ] Tôi không tự retry business write sau disconnect thiếu idempotency safeguards.
- [ ] Metrics không log secrets hay raw Ping payload.
- [ ] Tôi có unit test clock giả lập và integration test Ping/Pong trên loopback.
- [ ] Tôi test delayed/unmatched/unsolicited Pong, receive demand, proxy idle và reconnect race.

## 19. Tài liệu chuẩn và Java API

- [RFC 6455 `5.5 — Control Frames](https://www.rfc-editor.org/rfc/rfc6455#section-5.5): opcodes 8/9/A, payload tối đa 125 bytes, không fragment control frames, masking theo chiều.
- [RFC 6455 `5.5.2 — Ping](https://www.rfc-editor.org/rfc/rfc6455#section-5.5.2): khi nào có thể gửi Ping và yêu cầu gửi Pong để phản hồi.
- [RFC 6455 `5.5.3 — Pong](https://www.rfc-editor.org/rfc/rfc6455#section-5.5.3): payload echo, unsolicited Pong và giới hạn trả lời nhiều Pings.
- [RFC 6455 `5.3 — Client-to-Server Masking](https://www.rfc-editor.org/rfc/rfc6455#section-5.3): client frames phải masked, quy tắc XOR.
- [RFC 6455 `7 — Closing Handshake](https://www.rfc-editor.org/rfc/rfc6455#section-7): Close frame và connection closure.
- [Java SE 17 — WebSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html): `sendPing`/`sendPong`/`sendClose`/`abort`/`request`, pending send, tự động xử lý Ping/Close.
- [Java SE 17 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onPing`, `onPong`, `onError`, `request(n)` và buffer lifetime.
- [Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync` và `connectTimeout` cho handshake.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): tạo WebSocket client qua `newWebSocketBuilder`.
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): định kỳ trigger check theo trạng thái.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đồng hồ đo elapsed time.
- [MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket): JavaScript browser API không expose native Ping/Pong cho application code.

**Tóm kết:** WebSocket **Ping/Pong** giúp kiểm tra **peer protocol responsiveness và đường đi hai chiều**. Trong Java 17, gọi `sendPing(ByteBuffer)`, nhận và đối chiếu Pong qua `Listener.onPong`, duy trì `request(n)`, dùng một token pending và deadline monotonic; **đừng nhầm send future với Pong ack**. Tuy nhiên, **Pong thành công không chứng minh business service healthy**, và **Pong quá hạn không chứng minh tuyệt đối peer chết**. Dùng heartbeat như **tín hiệu phục vụ quyết định quản lý connection**, kết hợp application-level health, giới hạn tải, proxy/LB policy, reconnect backoff và quy tắc cleanup.
