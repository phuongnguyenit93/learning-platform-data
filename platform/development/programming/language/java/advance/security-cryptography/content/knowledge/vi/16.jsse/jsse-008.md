# 16.8 SSLEngine với wrap, unwrap, delegated task và quản lý trạng thái handshake

`javax.net.ssl.SSLEngine` là tầng xử lý TLS/DTLS **không gắn với một socket cụ thể** của Java Secure Socket Extension (JSSE). Nó nhận/giao dữ liệu qua các `ByteBuffer` do ứng dụng quản lý; ứng dụng tự chuyển ciphertext trên TCP/transport, lên lịch đọc/ghi, chạy các tác vụ handshake được ủy quyền và bảo đảm thứ tự. API này phù hợp với server NIO, event loop, Netty-style transport, một số mô hình asynchronous I/O và chương trình muốn tách **TLS engine** khỏi **network transport**.

Trọng tâm của bài là **quản lý trạng thái thực**: `wrap()`, `unwrap()`, `getDelegatedTask()`, `SSLEngineResult.Status` và `SSLEngineResult.HandshakeStatus`. Một vòng lặp đúng phải xử lý được record đến từng phần, bộ đệm đầy, tác vụ có thể block, kết quả tiêu thụ/sinh byte bằng 0 và việc đóng TLS bằng `close_notify`. Chỉ gọi `wrap` rồi `unwrap` một lần là **không đủ** để tạo thành một kết nối TLS đáng tin cậy.

Bài dùng **Java 17+**, trình bày một demo TLS 1.3 client/server thật bằng hai `SSLEngine` nối với nhau bằng hàng đợi byte trong bộ nhớ, không cần mở cổng mạng. Demo này giúp quan sát đúng handshake, chứng thư và mã hóa, nhưng **cố ý không phải bản triển khai NIO production**: bộ đệm lớn, transport không phân mảnh và delegated tasks chạy đồng bộ để dễ kiểm tra. Phần sau giải thích chính xác những việc phải bổ sung khi chuyển sang `SocketChannel`/`Selector`.

## 1. `SSLEngine` nằm ở đâu trong JSSE?

Sơ đồ từ góc nhìn **một** endpoint:

~~~text
                 ỨNG DỤNG                          NETWORK / TRANSPORT
                  (plaintext)                         (TLS records)
                      |                                     ^
                      v                                     |
              outboundApp ByteBuffer                       |
                      |                                     |
                      v                                     |
             SSLEngine.wrap(appSrc, netDst) ----------------+
                      ^
                      |
   local TLS state: handshake, certificate, session,
   key schedule, traffic keys, record encryption/decryption
                      |
                      v
             SSLEngine.unwrap(netSrc, appDst) <------------+
                      |                                     ^
                      v                                     |
              inboundApp ByteBuffer                 inboundNet ByteBuffer
                  (plaintext)                         (TLS records)
~~~

**`wrap(srcApp, dstNet)`** lấy plaintext application bytes (khi ở giai đoạn được phép), biến thành dữ liệu TLS đã bảo vệ hoặc sinh handshake/alert records, rồi đưa vào `dstNet`. Ứng dụng phải **tự gửi bytes đó** qua transport.

**`unwrap(srcNet, dstApp)`** lấy bytes TLS từ transport, giải mã/xử lý handshake và (khi phù hợp) đưa application plaintext vào `dstApp`. Ứng dụng phải **tự cung cấp đủ bytes theo đúng thứ tự**.

Các cuộc gọi này **không tự đọc/ghi TCP** và không tự làm cho một `SocketChannel` “sẵn sàng” theo logic NIO của ứng dụng. `SSLEngine` là stateful TLS processor, còn I/O multiplexing và framing/buffer ownership là trách nhiệm của caller.

### `SSLSocket` so với `SSLEngine`

| Tiêu chí | `SSLSocket` | `SSLEngine` |
| --- | --- | --- |
| Transport | Tích hợp socket và TLS streams. | **Transport độc lập**; caller mang bytes đi/đến. |
| Lập trình | `InputStream`/`OutputStream`, tương đối đơn giản. | `ByteBuffer` + state machine + scheduler. |
| Handshake | `startHandshake()` điều phối việc trao đổi. | `beginHandshake()` chỉ khởi động; caller phải chạy `wrap/unwrap/task` tới khi xong. |
| Backpressure/partial I/O | Thư viện quản lý nhiều chi tiết của stream. | Caller quản lý `SocketChannel` đọc/ghi một phần và các hàng đợi. |
| Use case | Ứng dụng đồng bộ, ví dụ đơn giản, API socket trực tiếp. | Event loop/NIO, engine transport riêng, async protocols. |
| Mức khó | Thấp hơn. | **Cao hơn đáng kể**, dễ sai state/buffer/close. |

**Nguyên tắc:** Nếu chỉ muốn gọi HTTPS, ưu tiên `java.net.http.HttpClient` hay framework HTTP có cấu hình TLS phù hợp. Đừng tự viết `SSLEngine` driver khi thư viện mạng đáng tin đã giải quyết các vấn đề này.

## 2. Bốn vùng byte của một endpoint

Một ứng dụng dùng `SSLEngine` thường có bốn vùng logic; thư viện có thể biểu diễn chúng bằng nhiều buffer/queue khác nhau:

| Vùng | Byte chứa gì? | Ai ghi / ai đọc? |
| --- | --- | --- |
| **Outbound application** (`appOut`) | Plaintext app cần gửi. | App ghi; `wrap` tiêu thụ. |
| **Outbound network** (`netOut`) | TLS handshake/alert/encrypted record cần gửi. | `wrap` ghi; transport đọc/`SocketChannel.write` gửi. |
| **Inbound network** (`netIn`) | Bytes TLS nhận từ peer, có thể mới là **một phần record**. | Transport ghi; `unwrap` tiêu thụ. |
| **Inbound application** (`appIn`) | Plaintext mà `unwrap` đã giải mã và xác thực. | `unwrap` ghi; app đọc. |

**Quan trọng:** `wrap`/`unwrap` có thể tiêu thụ/sinh byte nhưng **không nhất thiết đồng thời**:

- `wrap(emptyApp, netOut)` có thể sinh handshake record dù không có application byte nào.
- `unwrap(netIn, appIn)` có thể tiêu thụ nhiều handshake bytes nhưng sinh **0 application byte**.
- Một `unwrap` gặp thiếu bytes có thể không tiêu thụ gì: caller phải chờ mạng thêm bytes, không được gọi lại mãi trên cùng phần dữ liệu.
- Một `wrap` sau handshake có thể sinh TLS post-handshake messages hoặc `close_notify`; không giả định nó luôn chỉ tạo application ciphertext.

### Buffer không phải “message boundary” của TCP

TCP là **byte stream**, không cam kết một lần `SocketChannel.read` mang đủ một TLS record hoặc chỉ có một record. Dữ liệu có thể được chia thành nhiều lần read hoặc nhiều TLS records cùng đến trong một read. `SSLEngine` giải mã TLS framing, nhưng ứng dụng vẫn phải **giữ nguyên phần chưa tiêu thụ** trong `netIn`.

Không dùng `read()` trả số byte bằng 0 như một tín hiệu “hết record”. Trong NIO, 0 thường có nghĩa **chưa có dữ liệu mới lúc này**. EOF của `SocketChannel.read` được biểu diễn bằng `-1`; cách xử lý EOF TLS phải khác 0 và khác `BUFFER_UNDERFLOW`.

## 3. Tạo engine, cấu hình client/server và bảo đảm danh tính

### 3.1. `SSLContext` phải có key/trust managers đúng chính sách

- **Server** dùng `KeyManagerFactory`/key provider để chọn chứng thư và private key phù hợp; có thể yêu cầu client cert nếu mTLS.
- **Client** dùng `TrustManagerFactory`/PKIX truststore đã được phê duyệt để xác minh server certificate.
- Ở raw `SSLEngine` client, nên đặt **peer host/port** khi tạo engine, rồi bật `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` nếu ứng dụng đang xác thực hostname HTTPS.
- `SSLContext.getInstance("TLS")` là provider TLS engine, không tự có nghĩa dùng giao thức SSL cũ. Có thể hạn chế `TLSv1.3` trong lab, còn production tuân theo security policy/peer compatibility.

API cơ bản:

~~~java
// Mảnh API minh họa: sslContext phải đã được init đúng key/trust policy.
SSLEngine client = sslContext.createSSLEngine("api.example.test", 443);
client.setUseClientMode(true);

SSLParameters p = client.getSSLParameters();
p.setProtocols(new String[] {"TLSv1.3"});
p.setEndpointIdentificationAlgorithm("HTTPS");
client.setSSLParameters(p);

// Khi cấu hình xong mới beginHandshake/wrap/unwrap.
client.beginHandshake();
~~~

Đoạn trên **không phải tệp độc lập**, vì `sslContext` được cung cấp từ cấu hình tin cậy của ứng dụng. `SSLContext` không tạo truststore tự động từ một certificate lạ trong mạng, và `setEndpointIdentificationAlgorithm("HTTPS")` **không thay thế** việc chọn nguồn CA/truststore đúng.

**Không sử dụng “trust-all”** hoặc bỏ endpoint identification để sửa nhanh lỗi certificate. Bước đó có thể cho phép MITM ngay cả khi `wrap/unwrap` và AES-GCM hoạt động hoàn hảo.

### 3.2. Client/server mode phải đặt trước handshake

~~~java
SSLEngine server = serverSslContext.createSSLEngine();
server.setUseClientMode(false);
~~~

Một engine chưa được đặt client/server mode có thể ném `IllegalStateException` khi gọi `wrap/unwrap`. Sau khi bắt đầu handshake, không thay mode tùy tiện. Nên tạo **mỗi kết nối một engine**, không dùng chung cùng một `SSLEngine` cho nhiều client.

`createSSLEngine(host, port)` cung cấp peer host/port phục vụ session/certificate/endpoint identification, **không mở TCP socket**. Transport vẫn do `SocketChannel` hoặc ứng dụng quản lý.

## 4. Hai loại status phải đọc đồng thời

Kết quả của `wrap`/`unwrap` là `SSLEngineResult`, cung cấp **hai loại trạng thái độc lập**:

~~~java
SSLEngineResult result = engine.wrap(appBytes, netBytes);
SSLEngineResult.Status status = result.getStatus();
SSLEngineResult.HandshakeStatus hs = result.getHandshakeStatus();

int inputBytes = result.bytesConsumed();
int outputBytes = result.bytesProduced();
~~~

Đoạn trên minh họa API; `engine` và hai ByteBuffer cần được thiết lập trong hệ thống chạy thật.

- **Operation status (`getStatus()`):** thao tác vừa gọi đã xử lý buffer thành công, đóng engine hay cần thêm dung lượng/dữ liệu?
- **Handshake status (`getHandshakeStatus()`):** engine muốn ứng dụng thực hiện bước **TLS state machine** nào tiếp theo?
- **`bytesConsumed()` và `bytesProduced()`:** số byte đã tiêu thụ từ source / tạo ở destination; là cơ sở cập nhật queue/backpressure và phát hiện tiến triển.

Ví dụ `Status.OK` **không đồng nghĩa handshake đã hoàn tất**. `OK + NEED_UNWRAP` có thể nghĩa là đã xử lý record hiện tại nhưng phải nhận thêm record từ peer. `OK + NEED_TASK` nghĩa là có công việc crypto/trust được giao cho ứng dụng thực thi.

### 4.1. `SSLEngineResult.Status`

| `Status` | Ý nghĩa | Việc phải làm |
| --- | --- | --- |
| `OK` | Thao tác hoàn tất không có lỗi buffer/close cho lần gọi đó. | Đọc handshake status, consumed/produced và tiếp tục đúng hướng. |
| `BUFFER_UNDERFLOW` | Dữ liệu nguồn chưa đủ cho thao tác (thường gặp ở `unwrap` với TLS record chưa đủ). | Giữ phần net bytes chưa xử lý, lấy thêm từ mạng; kiểm tra/grow `netIn` nếu record lớn hơn buffer. **Không spin** trên cùng bytes. |
| `BUFFER_OVERFLOW` | Destination không đủ chỗ giữ output. | Với `wrap`: flush/grow `netOut`; với `unwrap`: drain/grow `appIn`. Retry đúng khi còn chỗ. |
| `CLOSED` | Phần tương ứng đã đóng hoặc không xử lý tiếp vì engine đóng. | **Vẫn chuyển các bytes đã được tạo**, xử lý `close_notify`, close state và transport thích hợp. |

**Không được gộp `BUFFER_UNDERFLOW` và `BUFFER_OVERFLOW` thành một lỗi TLS**: chúng thường là tín hiệu **điều phối buffer**, không phải certificate/chữ ký sai. Ngược lại, `SSLException` có thể là lỗi bảo mật/protocol thật sự và phải xử lý fail-closed.

### 4.2. `SSLEngineResult.HandshakeStatus`

| `HandshakeStatus` | Ý nghĩa | Hành động tiếp |
| --- | --- | --- |
| `NEED_WRAP` | Engine cần phát TLS bytes (handshake/alert/post-handshake). | Gọi `wrap`, giữ/gửi toàn bộ ciphertext sinh ra. |
| `NEED_UNWRAP` | Engine cần TLS bytes từ peer. | Dùng `unwrap` trên bytes đã nhận; nếu chưa đủ thì chờ read. |
| `NEED_UNWRAP_AGAIN` | Engine còn dữ liệu đã nhận nội bộ cần xử lý tiếp. | Gọi `unwrap` **ngay**, có thể không cần thêm bytes mạng. |
| `NEED_TASK` | Engine chờ các `Runnable` delegated tasks. | Lấy tất cả tasks qua `getDelegatedTask()`, chạy/chờ hoàn tất theo threading policy, rồi resume engine. |
| `FINISHED` | **Lần gọi `wrap/unwrap` vừa hoàn tất handshake.** | Thường quan sát ở **result** vừa trả về; ghi nhận sự kiện hoàn tất và chuyển đúng sang application/transport handling. |
| `NOT_HANDSHAKING` | Hiện không có handshake đang diễn ra. | Có thể xử lý application data; vẫn cần flush queue, post-handshake messages và close protocol khi phát sinh. |

**Bẫy đặc biệt:** `FINISHED` mang tính **sự kiện trên `SSLEngineResult`**, không phải trạng thái bền vững. `engine.getHandshakeStatus()` thường chuyển sang `NOT_HANDSHAKING` sau khi hoàn tất. Đừng thiết kế vòng lặp chỉ thoát khi `engine.getHandshakeStatus() == FINISHED`: nó có thể không bao giờ đúng.

**`NEED_UNWRAP_AGAIN` không giống `BUFFER_UNDERFLOW`**. Trường hợp đầu: engine còn handshake data đã đưa vào nội bộ và **có thể cần gọi unwrap ngay cả khi netIn không có byte mới**. Trường hợp sau: dữ liệu input chưa đủ, cần thêm bytes mạng hoặc buffer phù hợp.

### 4.3. Không tự suy đoán tiến triển từ `bytesProduced() == 0`

Ví dụ:
- `unwrap` có thể tiêu thụ handshake bytes nhưng sinh 0 plaintext bytes.
- `getDelegatedTask()` có thể thay đổi state dù không có bytes đi qua.
- `wrap` có thể trả `Status.OK` và `HandshakeStatus.NEED_UNWRAP`, không phải “không làm gì”.
- Đầu ra TLS chỉ có ý nghĩa khi kết hợp status, handshake status, buffer positions và queue state.

Khi chẩn đoán deadlock, log **hai trạng thái + consumed/produced + buffer positions/capacities**, không log raw handshake secrets hoặc payload nhạy cảm.

## 5. Mô hình state machine điều khiển handshake

`beginHandshake()` **không đồng nghĩa handshake đã hoàn thành**. Nó chỉ bắt đầu tiến trình; ứng dụng cần lặp luân phiên gửi/nhận cho đến khi cả peer và TLS state đạt điều kiện.

Sơ đồ logic cấp driver:

~~~text
engine.beginHandshake()
          |
          v
  engine.getHandshakeStatus()
          |
          +-- NEED_TASK ----------> getDelegatedTask().run()
          |                         (hoặc offload & chờ completion)
          |                                  |
          |                                  v
          |                              Kiểm tra lại state
          |
          +-- NEED_WRAP ----------> wrap(app buffer hoặc EMPTY, netOut)
          |                         kiểm tra status, flush/cấp buffer
          |                         chuyển TLS bytes đi theo đúng thứ tự
          |                                  |
          |                                  v
          |                              Kiểm tra lại state
          |
          +-- NEED_UNWRAP --------> nhận thêm net bytes nếu cần
          |                         unwrap(netIn, appIn)
          |                         kiểm tra status, giữ phần chưa dùng
          |                                  |
          |                                  v
          |                              Kiểm tra lại state
          |
          +-- NEED_UNWRAP_AGAIN --> unwrap(...) dù có thể không có bytes mới
          |                                  |
          |                                  v
          |                              Kiểm tra lại state
          |
          +-- FINISHED (result) ---> ghi nhận handshake hoàn tất
          |
          +-- NOT_HANDSHAKING ----> data phase / post-handshake / close
~~~

**Đây là sơ đồ điều phối, không phải code production độc lập.** Một event loop thật còn cần xử lý `Status.CLOSED`, `BUFFER_OVERFLOW`, `BUFFER_UNDERFLOW`, EOF, cancel/timeout, close_notify, tasks chạy chậm, pending ciphertext và trạng thái network channel.

### 5.1. Driver pseudocode có phân biệt result status

~~~text
onTick(connection):
  if taskFuture đang chạy:
    return, đợi completion; không gọi wrap/unwrap như thể task đã xong

  while còn tiến triển hợp lệ trong ngân sách CPU:
    hs = engine.getHandshakeStatus()

    if hs == NEED_TASK:
      tasks = lấy tất cả engine.getDelegatedTask()
      chạy tasks theo policy và chờ hoàn tất
      nếu offload: return, hẹn resume khi future complete
      continue

    if hs == NEED_WRAP:
      result = engine.wrap(pendingApplicationOrEmpty, netOutWriteMode)
      inspect result.Status và result.HandshakeStatus
      nếu BUFFER_OVERFLOW: flush/grow netOut; retry khi có chỗ
      nếu CLOSED: flush bytes/close_notify, cập nhật outbound state
      nếu OK: enqueue ciphertext; đăng ký OP_WRITE nếu chưa flush hết
      continue hoặc yield tùy backpressure

    if hs == NEED_UNWRAP or hs == NEED_UNWRAP_AGAIN:
      netIn.flip()       # WRITE -> READ
      result = engine.unwrap(netIn, appInWriteMode)
      netIn.compact()    # giữ ciphertext chưa tiêu thụ; về WRITE
      nếu BUFFER_UNDERFLOW:
        nếu buffer quá nhỏ: grow đến packet size hợp lý
        đợi OP_READ / bytes mới; KHÔNG busy-spin
      nếu BUFFER_OVERFLOW:
        deliver/grow appIn; retry sau khi có chỗ
      nếu CLOSED: ghi nhận close_notify/trạng thái inbound
      nếu OK: xử lý app bytes và handshake status; continue

    if hs == NOT_HANDSHAKING:
      flush mọi ciphertext pending
      chỉ nhận/gửi application data khi handshake chính sách đã xác minh
      xử lý post-handshake/close/queued application I/O
      return

    FINISHED chỉ là event từ SSLEngineResult, không điều kiện duy nhất
~~~

**Điểm cần thêm ở production:** `NEED_WRAP` vẫn có thể xuất hiện sau application handshake do KeyUpdate, NewSessionTicket hoặc đóng kết nối. Ngược lại, `NOT_HANDSHAKING` không tự bảo đảm mọi ciphertext đã thực sự đến peer. Để ra quyết định “đã hoàn thành” phải dựa cả engine state và transport queues.

### 5.2. Tránh vòng lặp tốn CPU

Không viết:

~~~java
while (engine.getHandshakeStatus()
        == SSLEngineResult.HandshakeStatus.NEED_UNWRAP) {
    engine.unwrap(netIn, appIn); // SAI nếu netIn không có bytes mới.
}
~~~

Khi `unwrap` trả `BUFFER_UNDERFLOW`, dữ liệu chưa đủ; gọi lại với cùng buffer nguyên trạng có thể tạo **busy loop** 100% CPU. Với `SocketChannel` non-blocking, phải **đợi kênh read-ready**, rồi nhận thêm bytes và thử lại.

Một scheduler hợp lý cần phân biệt:
- **Tiến triển nội bộ**: tasks đã hoàn tất, engine state chuyển, bytesConsumed/Produced.
- **Tiến triển transport**: có bytes nhận mới hoặc buffer đã được gửi/drain, có dung lượng trở lại.
- **Không tiến triển**: yield chờ sự kiện mới, không bận-spin trên `BUFFER_UNDERFLOW`.

## 6. ByteBuffer: `flip`, `compact` và dữ liệu chưa đọc

`ByteBuffer` có `capacity`, `position`, `limit`. Phương thức `put` thường ghi khi buffer ở **WRITE mode**; `get`/`unwrap` cần buffer nguồn ở **READ mode** sau khi gọi `flip()`.

### 6.1. Mô hình đúng cho `netIn`

~~~text
ByteBuffer netIn = allocate(...);  // WRITE mode
SocketChannel.read(netIn);         // ghi ciphertext mới
netIn.flip();                      // READ mode
engine.unwrap(netIn, appIn);       // tiêu thụ <= remaining()
netIn.compact();                   // giữ phần ciphertext chưa dùng
// netIn trở lại WRITE mode, có chỗ append khi read tiếp
~~~

`compact()` là **khác** `clear()`:
- `clear()` chuẩn bị ghi từ đầu và **coi bytes cũ đã bỏ**, nguy hiểm nếu còn TLS bytes chưa tiêu thụ.
- `compact()` dồn phần **còn remaining()** về đầu rồi chuyển sang WRITE mode; không mất phần record dở dang.

### 6.2. Java 17+: ví dụ nhỏ xác nhận `flip`/`compact`

Tệp **`ByteBufferModesDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;

public class ByteBufferModesDemo {
    public static void main(String[] args) {
        ByteBuffer inbound = ByteBuffer.allocate(8);

        inbound.put(new byte[] {1, 2, 3, 4});
        inbound.flip();                  // WRITE -> READ

        byte[] first = new byte[2];
        inbound.get(first);             // đã tiêu thụ 1, 2

        inbound.compact();              // giữ 3, 4; sang WRITE
        inbound.put(new byte[] {5, 6}); // append khi có thêm bytes
        inbound.flip();                 // sang READ

        byte[] rest = new byte[inbound.remaining()];
        inbound.get(rest);

        System.out.println("Consumed: " + Arrays.toString(first));
        System.out.println("Retained and appended: "
                + Arrays.toString(rest));
    }
}
~~~

~~~bash
javac ByteBufferModesDemo.java
java ByteBufferModesDemo
~~~

Stdout đã kiểm chứng:

~~~text
Consumed: [1, 2]
Retained and appended: [3, 4, 5, 6]
~~~

**Không nhầm ví dụ buffer đơn giản này với parser TLS.** TLS record cần đủ header/payload và state của engine; `ByteBuffer` chỉ đảm bảo bạn **không làm mất bytes còn dư** giữa các lần I/O.

### 6.3. Cách ghi `netOut` và partial writes

Khi `wrap` ghi ciphertext vào `netOut`, nó thường đang ở WRITE mode. Trước khi gửi:

~~~text
netOut.flip()                  // chuyển sang READ
SocketChannel.write(netOut)    // có thể chỉ gửi một phần
if netOut.hasRemaining():
    giữ nguyên bytes chưa gửi; hẹn OP_WRITE
else:
    netOut.clear()             // hoặc compact rồi nối record mới
~~~

Nếu output chưa gửi hết, **không được clear/overwrite** buffer và không được phát thêm record chồng lên phần chưa gửi mà làm đảo thứ tự. TLS record layer yêu cầu thứ tự byte chuẩn; một engine có thể có nhiều outbound records chờ transport.

Trong demo in-memory ở phần 10, hai hàng đợi luôn còn đủ chỗ, nên `peerInbound.put(encrypted)` mô phỏng việc chuyển **toàn bộ** record. Đây là cách cố ý loại bỏ partial writes để bài tập tập trung state machine. NIO thật phải xây chính sách enqueue + OP_WRITE + backpressure.

## 7. Phản ứng chính xác với `BUFFER_UNDERFLOW` và `BUFFER_OVERFLOW`

### 7.1. `BUFFER_UNDERFLOW` khi `unwrap`

Giả sử record TLS dài 1200 bytes nhưng TCP mới đưa đến 80 bytes. Không thể giải mã record đầy đủ:

~~~text
netIn chứa 80 bytes -> flip -> unwrap
Result.Status = BUFFER_UNDERFLOW
    |
    +-- Không bỏ 80 bytes
    +-- compact giữ 80 bytes
    +-- chờ read thêm bytes
    +-- lần sau append bytes vào netIn
    +-- flip -> unwrap lại
~~~

Nếu `netIn.capacity()` nhỏ hơn `SSLSession.getPacketBufferSize()` hoặc nhỏ hơn kích thước record mà engine cần, buffer có thể **không bao giờ đủ**: cần grow theo chính sách, nhưng cũng giới hạn kích thước/tài nguyên để chống DoS. `getPacketBufferSize()` là kích thước buffer đề xuất **có thể thay đổi trong quá trình session/handshake**.

**Không xử lý `BUFFER_UNDERFLOW` như TLS tampering ngay lập tức.** Nó thường có nghĩa dữ liệu đang đến từng phần. Tuy nhiên, nếu transport báo EOF khi một record còn dở dang, phải xử lý kết nối bị cắt đúng cách thay vì chờ vô hạn.

### 7.2. `BUFFER_OVERFLOW` khi `wrap`

Engine muốn tạo một TLS record nhưng `netOut` không đủ chỗ. Hướng xử lý:
1. Nếu có ciphertext chờ gửi, thử **drain netOut** qua transport.
2. Nếu dung lượng vẫn nhỏ hơn record, **grow** buffer phù hợp với `getPacketBufferSize()`.
3. Gọi lại `wrap` sau khi có đủ dung lượng.
4. Không bỏ plaintext khỏi `appOut` nếu nó **chưa được bytesConsumed**.

### 7.3. `BUFFER_OVERFLOW` khi `unwrap`

Engine muốn đưa application plaintext vào `appIn` nhưng `appIn` đầy. Hướng xử lý:
1. Nếu có dữ liệu plaintext đã được xác thực trong `appIn`, chuyển nó tới application consumer khi consumer còn capacity.
2. Nếu không thể drain, áp dụng **backpressure** lên network reads; không cứ tiếp tục đọc vô hạn.
3. Nếu buffer không đủ cho record/application packet theo `getApplicationBufferSize()`, grow hợp lý.
4. Retry `unwrap` khi có chỗ, giữ nguyên input chưa consumed.

### 7.4. Bảng tổng hợp tránh nhầm

| Trường hợp | Thiếu gì? | Hành động đúng |
| --- | --- | --- |
| `unwrap` -> `BUFFER_UNDERFLOW` | Input **network** TLS bytes chưa đủ. | Giữ netIn + nhận thêm, có thể grow netIn. |
| `unwrap` -> `BUFFER_OVERFLOW` | Destination **application** buffer không đủ. | Drain/grow appIn. |
| `wrap` -> `BUFFER_OVERFLOW` | Destination **network** buffer không đủ. | Flush/grow netOut. |
| `wrap` -> `Status.OK` + `bytesConsumed=0` | Có thể chỉ sinh handshake record. | Đọc handshake status + bytesProduced. |
| `unwrap` -> `Status.OK` + `bytesProduced=0` | Có thể chỉ xử lý handshake/alert. | Không giả định có app message. |
| `NEED_UNWRAP_AGAIN` | Còn xử lý nội bộ của handshake data. | Gọi `unwrap` tiếp, không cần chờ read mới nếu engine nói vậy. |

## 8. Delegated task: tại sao `SSLEngine` có thể vẫn làm event loop đứng?

Tài liệu JDK nói các phương thức `SSLEngine` được thiết kế **không thực hiện blocking transport I/O**, nhưng một số công việc handshake có thể đòi hỏi thời gian dài, ví dụ:

- Kiểm tra certificate chain/PKIX hoặc liên hệ dịch vụ kiểm tra chứng thư.
- Lấy private key từ token/HSM, thực hiện chữ ký hoặc thao tác provider có độ trễ.
- Tính toán mật mã, tra cứu trust/key manager, hoặc hành vi provider có thể chặn.

Engine có thể trả `HandshakeStatus.NEED_TASK`; caller phải lấy các `Runnable` qua `getDelegatedTask()` và cho chúng chạy.

### 8.1. Cách đồng bộ để học

~~~java
// Mảnh xử lý minh họa, phù hợp DEMO không có yêu cầu event-loop latency.
Runnable delegated;
while ((delegated = engine.getDelegatedTask()) != null) {
    delegated.run();
}
// Sau khi tất cả delegated tasks chạy xong:
// đọc engine.getHandshakeStatus() và resume wrap/unwrap.
~~~

**Đây không phải best practice cho một event-loop có hàng nghìn kết nối.** `Runnable.run()` có thể block: nếu chạy trên thread xử lý tất cả kênh, một certificate validation chậm làm ngưng mọi kết nối.

### 8.2. Production: offload có kiểm soát và resume đúng trạng thái

Pseudo-architecture:

~~~text
Event loop:
  engine reports NEED_TASK
      |
      v
  collect delegated tasks
      |
      v
  offload to bounded crypto/handshake executor
      |                     |
      |                     +-> kiểm soát concurrency, timeout, backpressure
      |
  mark connection WAITING_FOR_TASK
  do not spin or overlap wrap/unwrap as if tasks done
      |
  future completion / scheduled event
      |
      v
  check task error, verify engine/session state
  re-register needed interestOps
  resume handshake from engine.getHandshakeStatus()
~~~

Khi xử lý thực tế:
- Task phải chạy **đủ và hoàn tất** trước khi engine có thể tiến triển qua giai đoạn cần task đó. Không chỉ submit vào executor rồi gọi `wrap/unwrap` ngay.
- Dùng **bounded executor**; tránh `new Thread(task).start()` không giới hạn cho mỗi client trong server chịu tải.
- Không block event loop bằng `future.get()`; dùng callback/queue để gửi completion về **owner event-loop thread**.
- Phải xét điều kiện timeout, connection cancellation, task failure và race với close. Khi connection đã bị đóng hoặc bị thay generation, completion cũ không được làm sống lại engine.
- Với một số provider, exceptions của task có thể được truyền hoặc gây lỗi ở bước `wrap/unwrap` tiếp theo; log theo nguyên nhân nhưng không in private key/handshake secrets.
- Nên **serialize quyền điều phối state cho mỗi connection** (một event-loop owner) để tránh nhiều callback/tác vụ đồng thời sửa queue/engine vô trật tự.

### 8.3. Đừng nhầm `NEED_TASK` với `NEED_UNWRAP`

`NEED_TASK` nghĩa engine cần **kết quả công việc địa phương**; đọc thêm từ socket không tự chạy delegated task. `NEED_UNWRAP` nghĩa engine cần **dữ liệu TLS từ peer** hoặc có dữ liệu đã chờ; chạy một task không thay thế việc đọc network.

Kết hợp xử lý cả hai mới tránh deadlock như “client chờ ServerHello trong khi server chưa chạy key/cert validation task”.

## 9. Ranh giới giữa handshake phase và application phase

Đối với handshake ban đầu:

1. Tạo `SSLEngine`, gắn mode/trust/parameters.
2. Gọi `beginHandshake()` hoặc để lần `wrap/unwrap` đầu tiên tự khởi tạo.
3. Lặp `NEED_WRAP/NEED_UNWRAP/NEED_TASK/NEED_UNWRAP_AGAIN` cho tới khi handshake hoàn tất theo trạng thái engine/result.
4. Ghi nhận event `FINISHED` nếu ứng dụng cần, đồng thời kiểm tra `SSLSession` protocol/cipher và quyết định trust/identity theo JSSE policy.
5. Khi đã có TLS session hợp lệ, xử lý application bytes bằng `wrap`/`unwrap`.

**Lưu ý TLS 1.3:** Sau khi handshake ban đầu kết thúc, **NewSessionTicket**, **KeyUpdate** hoặc các post-handshake events vẫn có thể tạo nhu cầu `wrap/unwrap` và task tương ứng. Đừng viết logic “đã FINISHED một lần thì từ đó trở đi chỉ wrap plaintext, không xem handshake status nữa”.

`NOT_HANDSHAKING` là trạng thái engine tại một thời điểm; để coi **application đã được gửi ra mạng**, cần xác minh `netOut` đã flush hết; để coi **request đã nhận đầy đủ**, cần framing của giao thức ứng dụng (HTTP, custom length prefix, v.v.), không chỉ dựa trên một lần `unwrap`.

## 10. Demo runnable Java 17+: TLS 1.3 giữa hai `SSLEngine` qua bộ nhớ

### 10.1. Mục đích, giới hạn và môi trường

Ví dụ dùng hai `SSLEngine`: **client** và **server**, mỗi engine có cấu hình `SSLContext` riêng. Giữa chúng là hai `ByteBuffer` mô phỏng **các hàng đợi ciphertext inbound network**. Với mỗi trạng thái:
- `NEED_TASK`: chạy đủ delegated tasks **đồng bộ** trong demo.
- `NEED_WRAP`: gọi `wrap(EMPTY, output)`, copy output sang inbound queue của peer.
- `NEED_UNWRAP` / `NEED_UNWRAP_AGAIN`: `flip`, `unwrap`, `compact` và cập nhật state.
- `NOT_HANDSHAKING` ở cả hai đầu: demo coi handshake ban đầu hoàn tất.
- Sau đó client `wrap` thông điệp `hello`, server `unwrap` để nhận plaintext.
- Cuối cùng client gọi `closeOutbound()` và chuyển TLS `close_notify` tới server, chứng minh inbound close được nhận.

**Không mở network socket** trong ví dụ. Đây vẫn là một **TLS 1.3 handshake/mã hóa thật được JSSE thực hiện** bằng certificate test và crypto provider, chứ không phải mô phỏng giả mọi phép toán. Nhưng nó không kiểm tra các tình huống TCP partial-read/write, application backpressure, buffer growth, task cancellation, full duplex shutdown và tải nhiều client — những phần được phân tích riêng.

Chương trình yêu cầu:
- JDK 17+ với TLS 1.3 và `TLS_AES_128_GCM_SHA256`.
- Keystore PKCS#12 có private key + certificate server dùng cho hostname `localhost`.
- Truststore PKCS#12 của client đã tin certificate demo.
- `TLS_DEMO_PASS` chứa mật khẩu **test-only**.

### 10.2. Tạo hai keystore test

Chạy trong một **thư mục thử nghiệm mới**, không commit các file. Mật khẩu `changeit` chỉ để học, **không dùng cho production**.

~~~bash
# Tạo private key + self-signed certificate cho localhost (lab).
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 2 \
  -storetype PKCS12 -keystore server.p12 \
  -storepass changeit -keypass changeit -noprompt

# Xuất certificate công khai để client dùng làm trust anchor test.
keytool -exportcert -rfc -alias localhost -keystore server.p12 \
  -storepass changeit -file server.crt

# Import chứng thư test vào truststore RIÊNG của lab.
keytool -importcert -alias localhost -file server.crt \
  -keystore trust.p12 -storetype PKCS12 \
  -storepass changeit -noprompt
~~~

Dấu `\` cuối dòng ở ví dụ là nối dòng của **Bash**. Trên Windows PowerShell/CMD, chạy từng lệnh trên **một dòng hoàn chỉnh** và bỏ dấu `\`. Cần dùng cùng tên file trong lệnh Java bên dưới.

**Chú ý:** import certificate tự ký do mình vừa tạo vào truststore test là **một quyết định tin cậy có chủ đích** cho lab. Không tự tin một certificate từ đầu vào không xác thực rồi import vào truststore production để “vượt lỗi PKIX”. Certificate và private key `server.p12` cần bảo vệ; xóa test artifacts sau khi thực hành.

### 10.3. Mã đầy đủ: `InMemoryEngineDemo.java`

~~~java
import java.io.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.net.ssl.*;

public class InMemoryEngineDemo {
    private static final ByteBuffer EMPTY = ByteBuffer.allocate(0);

    static SSLContext serverContext(
            String file, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = new FileInputStream(file)) {
            store.load(in, password);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(store, password);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(kmf.getKeyManagers(), null, new SecureRandom());
        return ctx;
    }

    static SSLContext clientContext(
            String file, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = new FileInputStream(file)) {
            store.load(in, password);
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(store);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, tmf.getTrustManagers(), new SecureRandom());
        return ctx;
    }

    static boolean drive(
            SSLEngine engine, ByteBuffer inbound,
            ByteBuffer peerInbound) throws Exception {
        SSLEngineResult.HandshakeStatus hs =
                engine.getHandshakeStatus();
        switch (hs) {
            case NEED_TASK -> {
                Runnable task;
                int count = 0;
                while ((task = engine.getDelegatedTask()) != null) {
                    task.run();
                    count++;
                }
                if (count == 0) {
                    throw new IllegalStateException(
                            "NEED_TASK without task");
                }
                return true;
            }
            case NEED_WRAP -> {
                ByteBuffer output = ByteBuffer.allocate(
                        engine.getSession().getPacketBufferSize() * 2);
                SSLEngineResult result = engine.wrap(EMPTY, output);
                if (result.getStatus() != SSLEngineResult.Status.OK) {
                    throw new IllegalStateException("wrap: " + result);
                }
                output.flip();
                if (peerInbound.remaining() < output.remaining()) {
                    throw new IllegalStateException(
                            "Demo transport queue full");
                }
                peerInbound.put(output);
                return result.bytesProduced() > 0
                        || result.getHandshakeStatus() != hs;
            }
            case NEED_UNWRAP, NEED_UNWRAP_AGAIN -> {
                inbound.flip();
                SSLEngineResult result;
                try {
                    ByteBuffer app = ByteBuffer.allocate(
                            engine.getSession()
                                    .getApplicationBufferSize() * 2);
                    result = engine.unwrap(inbound, app);
                } finally {
                    inbound.compact();
                }

                if (result.getStatus()
                        == SSLEngineResult.Status.BUFFER_UNDERFLOW) {
                    return false;
                }
                if (result.getStatus() != SSLEngineResult.Status.OK) {
                    throw new IllegalStateException(
                            "unwrap: " + result);
                }
                return result.bytesConsumed() > 0
                        || result.bytesProduced() > 0
                        || result.getHandshakeStatus() != hs;
            }
            case NOT_HANDSHAKING, FINISHED -> {
                return false;
            }
            default -> throw new IllegalStateException(
                    "Unexpected handshake status");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java InMemoryEngineDemo server.p12 trust.p12");
            return;
        }

        String passText = System.getenv("TLS_DEMO_PASS");
        if (passText == null) {
            throw new IllegalStateException("TLS_DEMO_PASS missing");
        }
        char[] pass = passText.toCharArray();
        try {
            SSLEngine client = clientContext(args[1], pass)
                    .createSSLEngine("localhost", 443);
            client.setUseClientMode(true);

            SSLEngine server = serverContext(args[0], pass)
                    .createSSLEngine();
            server.setUseClientMode(false);

            SSLParameters cp = client.getSSLParameters();
            cp.setProtocols(new String[]{"TLSv1.3"});
            cp.setCipherSuites(
                    new String[]{"TLS_AES_128_GCM_SHA256"});
            cp.setEndpointIdentificationAlgorithm("HTTPS");
            client.setSSLParameters(cp);

            SSLParameters sp = server.getSSLParameters();
            sp.setProtocols(new String[]{"TLSv1.3"});
            sp.setCipherSuites(
                    new String[]{"TLS_AES_128_GCM_SHA256"});
            server.setSSLParameters(sp);

            // Hai inbound network buffers ở WRITE mode.
            ByteBuffer toServer = ByteBuffer.allocate(1024 * 1024);
            ByteBuffer toClient = ByteBuffer.allocate(1024 * 1024);

            client.beginHandshake();
            server.beginHandshake();

            boolean complete = false;
            for (int n = 0; n < 1000; n++) {
                boolean progress =
                        drive(client, toClient, toServer);
                progress |= drive(server, toServer, toClient);

                if (client.getHandshakeStatus()
                        == SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING
                        && server.getHandshakeStatus()
                        == SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING) {
                    complete = true;
                    break;
                }
                if (!progress) {
                    throw new IllegalStateException(
                            "Handshake stalled");
                }
            }
            if (!complete) {
                throw new IllegalStateException(
                        "Handshake loop limit");
            }

            System.out.println(
                    "Handshake complete: " + complete);
            System.out.println("Protocol: "
                    + client.getSession().getProtocol());
            System.out.println("Cipher suite: "
                    + client.getSession().getCipherSuite());
            System.out.println("Peer certificate present: "
                    + (client.getSession()
                            .getPeerCertificates().length > 0));

            // Client application plaintext -> TLS ciphertext.
            ByteBuffer clear = ByteBuffer.wrap(
                    "hello".getBytes(StandardCharsets.US_ASCII));
            ByteBuffer encrypted = ByteBuffer.allocate(
                    client.getSession().getPacketBufferSize() * 2);
            SSLEngineResult wr = client.wrap(clear, encrypted);
            if (wr.getStatus() != SSLEngineResult.Status.OK
                    || clear.hasRemaining()) {
                throw new IllegalStateException(
                        "Application wrap: " + wr);
            }
            encrypted.flip();

            // Server TLS ciphertext -> authenticated plaintext.
            ByteBuffer received = ByteBuffer.allocate(
                    server.getSession().getApplicationBufferSize() * 2);
            SSLEngineResult ur = server.unwrap(encrypted, received);
            if (ur.getStatus() != SSLEngineResult.Status.OK) {
                throw new IllegalStateException(
                        "Application unwrap: " + ur);
            }
            received.flip();
            System.out.println("Application message: "
                    + StandardCharsets.US_ASCII.decode(received));

            // Chỉ minh họa client close_notify -> server.
            client.closeOutbound();
            ByteBuffer closeRecord = ByteBuffer.allocate(
                    client.getSession().getPacketBufferSize() * 2);
            SSLEngineResult cr = client.wrap(EMPTY, closeRecord);
            if (cr.getStatus() != SSLEngineResult.Status.CLOSED) {
                throw new IllegalStateException(
                        "Close wrap: " + cr);
            }
            closeRecord.flip();
            SSLEngineResult peerClose = server.unwrap(
                    closeRecord,
                    ByteBuffer.allocate(
                            server.getSession()
                                    .getApplicationBufferSize() * 2));

            System.out.println("Peer received close_notify: "
                    + (peerClose.getStatus()
                            == SSLEngineResult.Status.CLOSED
                            && server.isInboundDone()));
        } finally {
            Arrays.fill(pass, '\0');
        }
    }
}
~~~

### 10.4. Biên dịch và chạy

Bash (từ thư mục chứa file Java và hai keystore):

~~~bash
export TLS_DEMO_PASS=changeit
javac InMemoryEngineDemo.java
java InMemoryEngineDemo server.p12 trust.p12
unset TLS_DEMO_PASS
~~~

Windows PowerShell:

~~~powershell
$env:TLS_DEMO_PASS = "changeit"
javac InMemoryEngineDemo.java
java InMemoryEngineDemo server.p12 trust.p12
Remove-Item Env:TLS_DEMO_PASS
~~~

Đầu ra kiểm chứng trên JDK hỗ trợ TLS 1.3, keystore test đúng hướng dẫn:

~~~text
Handshake complete: true
Protocol: TLSv1.3
Cipher suite: TLS_AES_128_GCM_SHA256
Peer certificate present: true
Application message: hello
Peer received close_notify: true
~~~

**Đây là stdout xác minh trên bộ môi trường demo.** Nếu JVM không hỗ trợ TLS 1.3/AEAD suite, truststore không chứa đúng certificate, SAN không khớp `localhost` hoặc keytool thất bại, handshake có thể ném exception — không hạ mức bảo mật để cố xuất dòng `true`.

### 10.5. Giải thích điểm khó trong code

1. **Client/server identity:** Server tạo `SSLContext` với `KeyManagerFactory` từ `server.p12`; client tạo `SSLContext` với `TrustManagerFactory` từ `trust.p12`. Client bật `HTTPS` endpoint identification với peer host `localhost`.
2. **Buffers là mô phỏng network queues:** `toServer` là ciphertext inbound phía server; `toClient` là ciphertext inbound phía client. Mỗi hàng đợi được để ở **WRITE mode** giữa các lượt.
3. **`NEED_WRAP`:** `engine.wrap(EMPTY, output)` sinh record handshake dù không có application plaintext, rồi `peerInbound.put(output)` chuyển bytes sang phía còn lại.
4. **`NEED_UNWRAP`:** `inbound.flip()`, `engine.unwrap(inbound, app)`, `inbound.compact()`; bytes chưa tiêu thụ vẫn ở queue sau khi quay về WRITE mode.
5. **`NEED_UNWRAP_AGAIN`:** dùng cùng nhánh gọi `unwrap`, kể cả khi engine xử lý buffered internal handshake bytes.
6. **`NEED_TASK`:** lấy và chạy tasks cho đến khi `getDelegatedTask()` trả `null`. **Demo chạy đồng bộ**; production phải cân nhắc offload và không block event loop.
7. **Handshake complete:** khi **cả hai** engine không còn đang handshake sau những lần drive hợp lệ, demo chuyển sang application phase. Trong network thật phải còn xét queue ciphertext và trạng thái peer/network.
8. **Client `wrap` / server `unwrap`:** Client wrap `"hello"`; server nhận plaintext qua unwrap. Đây là record mã hóa thật. Plaintext không được truyền trực tiếp qua mô phỏng `toServer`.
9. **`close_notify`:** `client.closeOutbound()` khiến `wrap(EMPTY, ...)` tạo alert đóng; server `unwrap` thấy `Status.CLOSED` và `isInboundDone()`. Demo **chỉ kiểm chứng một chiều close_notify**; ứng dụng thực còn cần phản hồi đóng đúng protocol và flush mọi ciphertext trước khi đóng transport.
10. **Bảo vệ secret:** `Arrays.fill(pass, '\0')` chỉ làm sạch **mảng tạm** do demo tạo; `passText` từ environment là `String` immutable và không thể đảm bảo xóa mọi bản sao trong JVM. Không dùng `changeit` cho secret thực.

### 10.6. Chính xác demo chưa hỗ trợ gì?

Demo chạy trên bộ đệm trong RAM đủ lớn nên:
- Nó **ném `IllegalStateException`** nếu queue mô phỏng đầy hoặc xảy ra overflow, thay vì retry/resize như transport production.
- Nó không phân mảnh TLS ciphertext thành nhiều lần `SocketChannel.read`; vì vậy chưa thử kỹ `BUFFER_UNDERFLOW` trên network thực.
- Nó không triển khai `Selector`/`OP_READ`/`OP_WRITE`, timeout tổng thể, scheduling fairness hay handling của hàng nghìn connections.
- Nó chỉ nhận **một application record đơn giản**. Real application có framing/streaming, nhiều records, partial writes, EOF và backpressure.
- Nó chỉ thể hiện **client close_notify tới server**, chưa hoàn thành toàn bộ quy trình đóng cả hai chiều của cặp engine.
- Nó không triển khai mTLS, resumption policy, early-data/0-RTT hay monitor post-handshake.
- Nó dùng truststore test tự ký. Không lấy mô hình này làm thay thế PKIX/truststore production.

Vì thế **không copy nguyên demo đưa vào nonblocking server production**. Hãy dùng phần status/buffer/transport ở các mục tiếp theo để hiểu thứ gì framework như Netty đã xử lý.

## 11. Mapping sang `SocketChannel` và `Selector`

Trong NIO non-blocking, mỗi kết nối thường có:
- Một `SocketChannel` ở nonblocking mode, `SelectionKey` và event-loop owner.
- Một `SSLEngine` cấu hình client hoặc server.
- `netIn` chứa ciphertext bytes nhận được **chưa unwrap**.
- `netOut`/queue chứa ciphertext bytes **chưa flush hết**.
- `appIn`/`appOut` hoặc application streams/framing.
- Trạng thái: handshake in progress, tasks pending, closing/closed, timer, buffer limits.

### 11.1. Quy tắc đăng ký interest ops

| Tình trạng | Nên quan tâm sự kiện gì? | Vì sao |
| --- | --- | --- |
| `NEED_UNWRAP` nhưng `netIn` chưa đủ | `OP_READ` | Chờ bytes TLS mới, không spin. |
| `NEED_WRAP`, có chỗ netOut | Có thể chạy `wrap` ngay trên event loop | Sinh ciphertext/handshake record nội bộ. |
| `netOut` còn bytes chưa gửi | `OP_WRITE` | Channel chỉ writable khi event loop được thông báo; flush dần. |
| `NEED_TASK` và tasks offloaded | Tạm chờ completion, quản lý interest ops theo policy | Không block loop hoặc đồng thời gọi engine trước khi tasks hoàn tất. |
| `appIn` đầy, application tiêu thụ chậm | Hạn chế thêm `OP_READ`, giữ backpressure | Tránh RAM tăng vô hạn. |
| Outbound queue quá lớn | Dừng/giảm việc nhận thêm appOut | Không tạo ciphertext nhanh hơn mạng gửi được. |
| TLS closing/close_notify pending | Tiếp tục `OP_WRITE` đến khi gửi hết close record | Đóng TCP quá sớm sẽ cắt TLS alert. |

**Bẫy CPU:** Nếu luôn bật `OP_WRITE` khi không có dữ liệu để gửi, vì socket thường writable, Selector có thể trả về liên tục và tiêu thụ CPU. Chỉ bật `OP_WRITE` khi **thực sự có pending bytes**.

### 11.2. Khi channel đọc được

Mô hình:

~~~text
n = channel.read(netIn)    # netIn WRITE mode
if n > 0:
    netIn.flip()
    loop:
       result = engine.unwrap(netIn, appIn)
       handle result Status + HandshakeStatus
       if UNDERFLOW -> break, cần thêm network bytes
       if OVERFLOW -> drain/grow appIn, có thể retry
       if NEED_TASK -> offload tasks, tạm dừng
       if no progress -> break để tránh busy-loop
    netIn.compact()        # giữ bytes chưa consume

if n == 0:
    không có bytes mới: yield, đừng coi là EOF

if n == -1:
    network EOF: kiểm tra TLS close_notify đã nhận chưa
    xử lý closeInbound()/truncation theo protocol & policy
~~~

Đây là **pseudocode thuật toán**, không có mọi chi tiết concurrency/exception của production. Khi `NEED_UNWRAP_AGAIN`, driver có thể vẫn cần gọi unwrap khi không có network byte mới.

### 11.3. Khi channel ghi được

Mô hình:

~~~text
while netOut/queue còn ciphertext:
    count = channel.write(readModeBuffer)
    if count == 0:
        giữ nguyên pending bytes, hẹn OP_WRITE
        break
    if readModeBuffer còn remaining:
        giữ lại, hẹn OP_WRITE
        break
    else:
        release/recycle sent buffer

khi queue rỗng:
    bỏ OP_WRITE interest
    nếu engine NEED_WRAP: gọi wrap để tạo record tiếp
    nếu application appOut pending và đã handshake: wrap thêm khi có capacity
~~~

**Không đảo record order.** Nếu `wrap` sinh ciphertext A rồi ciphertext B, chúng phải được gửi trong đúng thứ tự, kể cả khi A bị partial write. Không dùng một buffer đang được network thread đọc để gọi `wrap` ghi đồng thời.

### 11.4. Backpressure hai chiều

- **Inbound:** Application không tiêu thụ plaintext đủ nhanh -> `appIn` đầy -> `unwrap BUFFER_OVERFLOW` -> tạm giảm đọc TCP, nhưng cần cân nhắc TLS control/close để tránh deadlock. Thiết kế queue bounded và scheduler có chính sách.
- **Outbound:** Peer hoặc network chậm -> `netOut` đầy -> `wrap BUFFER_OVERFLOW` -> dừng tạo records mới, flush dần qua `OP_WRITE`. Không cứ gọi `wrap` và cấp buffer không giới hạn.
- **Handshake:** Dù chưa có application data, TLS vẫn cần gửi/nhận messages. Đừng chặn mọi `NEED_WRAP/NEED_UNWRAP` chỉ vì app queue rỗng.

## 12. Tính toán buffer size và quản lý cấp phát

`SSLSession` cung cấp hai chỉ số then chốt:

~~~java
int packetSize = engine.getSession().getPacketBufferSize();
int appSize = engine.getSession().getApplicationBufferSize();
~~~

- `getPacketBufferSize()`: dung lượng gợi ý cho TLS/DTLS packet được sinh/tiêu thụ qua engine.
- `getApplicationBufferSize()`: dung lượng gợi ý cho application plaintext của một record.
- Kích thước có thể **thay đổi theo handshake/session**; đừng hard-code `16_384` bytes rồi giả định luôn đủ cả TLS framing và tag.
- Không cố cấp buffer một record rồi tiếp tục ghi ciphertext vô hạn. Mỗi connection cần memory cap, queue cap và quy tắc nới/gom buffer.

### 12.1. Mẫu grow buffer minh họa

~~~java
// Mảnh minh họa: source đang ở WRITE mode, sẽ giữ mọi byte đã ghi.
static ByteBuffer growWriteBuffer(ByteBuffer old, int requiredCapacity) {
    if (requiredCapacity <= old.capacity()) {
        return old;
    }
    ByteBuffer replacement = ByteBuffer.allocate(requiredCapacity);
    old.flip();
    replacement.put(old);
    return replacement; // WRITE mode, bytes cũ được bảo toàn.
}
~~~

Đây không phải phương thức tự hoàn thiện cho production:
- Cần **giới hạn dung lượng** tránh untrusted peer khiến memory tăng vô hạn.
- Nếu dùng direct buffers, xử lý resource/pooling và copy overhead.
- Với output đang ở READ mode có pending bytes, phải copy phần `remaining()` chứ không áp dụng máy móc logic `flip()` thêm lần nữa.
- Kích thước phù hợp phụ thuộc trạng thái engine và queue, không chỉ một hằng số cố định.

### 12.2. `ByteBuffer` có thể heap hoặc direct

`ByteBuffer.allocate(...)` tạo heap buffer, `ByteBuffer.allocateDirect(...)` tạo direct buffer có thể phù hợp một số kênh I/O. Lựa chọn phụ thuộc hiệu năng, GC, allocation, provider và giới hạn tài nguyên; **không phải tính chất mật mã**. `SSLEngine` không cần lấy raw heap array của mọi buffer, nên tránh giả định `buffer.array()` luôn hoạt động với direct/read-only buffers.

**Không dùng chung source/destination với cùng vùng nhớ** cho `wrap/unwrap`. Hợp đồng API yêu cầu input/output không alias theo cách nguy hiểm; nếu có overlap, dữ liệu có thể hỏng hoặc hành vi provider bị từ chối.

## 13. Delegated tasks và event-loop threading: thiết kế đúng cho tải cao

Một số quy tắc thực hành:

1. **Mỗi connection có owner điều phối state.** Cho một event loop quyết định khi nào gọi `wrap`, `unwrap`, giao buffer và close. Đừng cho hai callback bất kỳ cùng gọi `wrap` trên cùng engine đồng thời.
2. **`wrap` và `unwrap` có thể đồng thời ở mức API** nếu người dùng tự bảo đảm ordering/synchronization và trạng thái; nhưng hai lần `wrap` cạnh nhau hoặc hai lần `unwrap` cạnh nhau trên cùng engine có nguy cơ sai thứ tự. Thiết kế đơn giản là serialize mọi engine operations theo connection.
3. **Deferred tasks không phải network I/O.** Dùng pool riêng hoặc cơ chế tính toán phù hợp; không tạo vô hạn worker threads.
4. **Task completion phải đánh thức đúng connection.** Đưa một sự kiện trở lại event loop, kiểm tra connection còn sống, xử lý exception, tiếp tục trạng thái engine.
5. **Không giữ lock lâu khi task có thể block.** Thiết kế race với close, timeout, cancellation và provider state; tránh deadlock event loop vs task worker.
6. **Kiểm tra active timer.** Một peer có thể gửi vài bytes rồi không bao giờ hoàn tất handshake. Đặt handshake timeout, max queued bytes, max cert chain size theo framework/policy.
7. **Dùng error handling fail-closed.** Bất cứ `SSLHandshakeException`, `SSLProtocolException`, certificate trust failure hoặc buffer logic violation chưa xử lý đều phải từ chối kết nối, không fallback plaintext.
8. **Không leak TLS secrets trong diagnostics.** Có thể log negotiated protocol, cipher suite, connection ID, generic failure stage; không log raw keys, pre-master/traffic secrets, session ticket secrets hay plaintext application data nhạy cảm.

Tài liệu Java SE 17 mô tả delegated task có thể kéo dài/thậm chí block do trust manager, key manager hoặc crypto provider. Nên **lên lịch, await completion và khôi phục engine state** — không chỉ chạy tất cả `Runnable` “cho xong” trên Selector thread.

## 14. Đóng TLS đúng: `closeOutbound`, `closeInbound` và `close_notify`

TLS có **protocol-level closure** riêng, không đồng nghĩa đóng TCP tức thời. Khi ứng dụng muốn ngừng gửi:

~~~text
Application decides to close
    |
engine.closeOutbound()
    |
wrap(EMPTY, netOut) -> TLS close_notify record
    |
flush toàn bộ netOut qua transport
    |
peer unwrap(record) -> Status.CLOSED / isInboundDone()
    |
peer có thể gửi close_notify chiều ngược lại
    |
chỉ sau quy trình đóng/bảo vệ dữ liệu mới đóng underlying channel
~~~

Chi tiết:
- `closeOutbound()` báo cho engine không tạo thêm application outbound data. Nó **chưa tự gửi** byte nào; cần gọi `wrap` cho tới khi outbound TLS closure records đã được tạo và gửi.
- `isOutboundDone()` cho biết phía outbound của engine đã hoàn tất; **không chứng minh** ciphertext của record cuối đã được gửi hết bằng TCP.
- `isInboundDone()` sau `unwrap` nhận `close_notify` cho biết peer đã đóng chiều gửi TLS đúng protocol. Nếu `SocketChannel` EOF trước `close_notify`, phải xử lý khả năng **truncation** theo security policy; `closeInbound()` có thể ném `SSLException` để báo đóng không đầy đủ.
- `SSLEngine` đã đóng **không tái sử dụng** cho kết nối mới; cần tạo engine khác.
- TLS 1.3 có semantics half-close/alerts riêng; đừng cưỡng ép mô hình “một bên đóng thì cả hai TCP lập tức cắt” nếu còn dữ liệu/chế độ protocol cần trao đổi.

**Demo `InMemoryEngineDemo` chỉ minh họa một chiều close_notify**, không thực hiện đóng hai chiều đầy đủ. Trong ứng dụng thật cần quản lý outbound/inbound status độc lập, flush và thời hạn đóng để tránh treo vô hạn khi peer không phản hồi.

### 14.1. `Status.CLOSED` vẫn có thể có bytes phải gửi

Khi `wrap` trả `Status.CLOSED`, nó có thể đã sinh một TLS alert/close record vào `netOut`. **Đừng bỏ buffer và đóng TCP ngay**: phải flush record nếu transport còn hoạt động và chính sách cho phép. Khi `unwrap` trả `CLOSED`, kiểm tra inbound done và protocol control state trước khi giải phóng connection.

### 14.2. EOF với `BUFFER_UNDERFLOW` không phải đóng đẹp

Một peer có thể bị mất mạng khi một TLS record chưa đủ bytes, khiến `unwrap` tiếp tục trả `BUFFER_UNDERFLOW`, rồi transport `read` trả `-1`. Nếu bỏ qua và gọi app callback như “kết thúc bình thường”, ứng dụng có thể chấp nhận dữ liệu chưa đủ hoặc bị cắt. Cần phân biệt **truncation** với **đóng TLS có `close_notify`** và xử lý theo quy tắc giao thức ứng dụng.

## 15. Những lỗi triển khai phổ biến

| Sai lầm | Tác động | Cách đúng |
| --- | --- | --- |
| Chỉ gọi `beginHandshake()` rồi gửi application data | Handshake chưa được điều phối. | Chạy state machine `wrap/unwrap/NEED_TASK` đến khi hoàn tất. |
| Gọi `wrap`/`unwrap` nhưng bỏ `SSLEngineResult` | Không biết buffer overflow/underflow, handshake status, bytes consumed. | Luôn xử lý cả status và byte counts. |
| Chỉ xét `getStatus() == OK` | `OK` không đồng nghĩa handshake completed. | Đọc `getHandshakeStatus`/engine state. |
| Đợi `engine.getHandshakeStatus()==FINISHED` | `FINISHED` thường chỉ xuất hiện trên result vừa trả về. | Xử lý `result.getHandshakeStatus()==FINISHED` và `NOT_HANDSHAKING` đúng ngữ cảnh. |
| Không hỗ trợ `NEED_UNWRAP_AGAIN` | Handshake có thể treo với provider/TLS state phù hợp. | Cho phép unwrap tiếp không cần read bytes mới. |
| Gọi `unwrap` mãi trên partial input | Busy loop khi `BUFFER_UNDERFLOW`. | Giữ bytes và chờ `OP_READ`. |
| Sau `unwrap` dùng `netIn.clear()` | Bỏ bytes TLS record chưa xử lý. | `flip` trước unwrap, `compact` sau unwrap. |
| Sau `wrap` gọi `netOut.clear()` khi TCP chỉ gửi một phần | Mất ciphertext hoặc đảo record order. | Giữ remaining bytes, flush qua `OP_WRITE`. |
| Xử lý `BUFFER_OVERFLOW` bằng cách bỏ plaintext | Có thể mất application data và làm lệch record stream. | Drain/grow destination, retry; dựa trên bytesConsumed. |
| Thực thi delegated tasks trên Selector thread | Task crypto/trust chậm chặn mọi connection. | Offload có giới hạn, callback completion về event loop. |
| Submit task rồi gọi tiếp `wrap/unwrap` ngay | Engine chưa có kết quả task, có thể bế tắc/race. | Đợi tasks hoàn tất và resume đúng state. |
| Dùng một `SSLEngine` cho nhiều connection | Session/state/ciphers/queues bị trộn, không an toàn. | Một engine cho một TLS connection. |
| Không cấu hình `setUseClientMode` | Engine có thể ném `IllegalStateException`. | Đặt mode trước handshake. |
| Tắt hostname verification để “fix PKIX” | Có thể chấp nhận server sai identity. | Truststore và endpoint identity đúng. |
| Nhầm `SSLEngine` với `SSLSocket` tự thực hiện I/O | Không có bytes nào được gửi ra socket. | Tự chuyển ciphertext vào/ra `SocketChannel`. |
| Mặc định TCP read một lần có đủ record | TCP là stream, có partial/multiple records. | Giữ netIn và xử lý kết quả unwrap. |
| Luôn bật `OP_WRITE` | Busy loop khi writable nhưng không có gì để gửi. | Chỉ đăng ký OP_WRITE khi pending ciphertext. |
| Đóng TCP ngay sau `closeOutbound()` | `close_notify` chưa được tạo/gửi, có thể gây truncation. | `wrap` TLS close records, flush rồi đóng đúng quy trình. |
| Debug raw application/traffic secret | Có thể lộ dữ liệu/khóa và metadata nhạy cảm. | Log trạng thái/metadata tối thiểu, bảo vệ debug logs. |

## 16. Chẩn đoán lỗi và kiểm thử state machine

### 16.1. Exception không thay thế status

| Tín hiệu | Loại | Giải thích |
| --- | --- | --- |
| `BUFFER_UNDERFLOW` / `BUFFER_OVERFLOW` | `SSLEngineResult.Status` | Điều kiện buffer, **thường không phải security exception**. |
| `NEED_TASK` / `NEED_WRAP` / `NEED_UNWRAP` | `HandshakeStatus` | Engine yêu cầu bước điều phối tiếp theo. |
| `SSLHandshakeException` | Exception | Handshake thất bại (có thể do chain/trust, hostname, protocol/ciphers, key material). |
| `SSLProtocolException` | Exception | Lỗi protocol TLS/DTLS; cần fail-closed và chẩn đoán context. |
| `SSLException` | Exception nền tảng | Engine không thể xử lý dữ liệu/kết nối theo TLS; có thể bao gồm close/truncation. |
| `IllegalStateException` | Exception Java hoặc app-defined | Ví dụ chưa set client/server mode; demo cũng dùng nó khi queue quá nhỏ/stalled. |
| `SocketChannel.read() == -1` | Transport EOF | Mạng đã đóng; **không phải `close_notify`**. |

Không bắt toàn bộ `Exception` rồi cố gọi `wrap` thêm vô hạn hoặc chuyển sang plaintext. Nếu certificate validation fail, hãy kiểm tra truststore/PKIX/SAN và thuật toán, không tạo trust-all manager.

### 16.2. Bộ test tối thiểu cho driver NIO

| Test | Cách dựng | Kỳ vọng |
| --- | --- | --- |
| Handshake TLS 1.3 bình thường | Client/server trust hợp lệ | Completed, session protocol/cipher đúng, data hai chiều hoạt động. |
| Certificate không được tin | Dùng truststore khác/không có issuer | Handshake fail; không cấp plaintext application data. |
| Hostname sai | Certificate chỉ có SAN `localhost`, engine tạo với host khác | Client endpoint identification fail. |
| Ngắt record thành 2–3 TCP reads | Gửi phần header/record rồi phần còn lại | `BUFFER_UNDERFLOW`, giữ bytes, sau đó unwrap OK. |
| Một read chứa nhiều TLS records | Nối các ciphertext records | Driver unwrap lặp và giữ position, không mất record. |
| `netOut` nhỏ | Destination không đủ packet | `BUFFER_OVERFLOW`, flush/grow rồi retry. |
| `appIn` nhỏ | Destination không đủ plaintext | `BUFFER_OVERFLOW`, drain/grow appIn. |
| Delegated task chậm | Trust manager/provider giả lập delay có kiểm soát | Event loop khác vẫn chạy, task completion resume đúng connection. |
| `NEED_UNWRAP_AGAIN` | Provider/state trả status đó | Driver gọi unwrap tiếp, không đợi read mới một cách sai. |
| TCP partial write | Channel.write chỉ gửi vài bytes | Ciphertext còn lại được giữ đúng thứ tự, OP_WRITE flush dần. |
| Event loop không có pending netOut | Socket writable | OP_WRITE không spin. |
| Đóng TLS đúng | Hai phía trao close_notify | Cả inbound/outbound done theo policy, transport chỉ đóng sau flush. |
| Abrupt TCP EOF | Đóng không gửi close_notify | Phân biệt truncation/closeInbound error với đóng hợp lệ. |
| Concurrent close + delegated task | Đóng khi task đang chạy | Completion không làm hồi sinh connection hoặc leak buffer. |
| Handshake không có tiến triển | Peer gửi nửa record rồi im | Timeout và giới hạn memory; không bận-spin vô hạn. |
| Post-handshake TLS 1.3 | NewSessionTicket/KeyUpdate | Driver tiếp tục xử lý control messages dù đã hoàn tất handshake. |

Không nên kiểm tra test bằng chuỗi exception message cố định của một provider; dùng **loại trạng thái, vị trí lỗi, dữ liệu nhận và điều kiện fail-closed**. Provider khác nhau có thể có nhiều delegated tasks, số vòng wrap/unwrap, kích thước output hoặc sequence status khác nhau — đừng hard-code rằng handshake luôn cần đúng N lần.

### 16.3. Log trạng thái có kiểm soát

Ví dụ field logging:
- Connection/correlation ID, role client/server, JSSE provider hoặc JDK build trong phạm vi policy.
- `SSLEngineResult.Status`, `HandshakeStatus`, `bytesConsumed`, `bytesProduced`.
- `netIn.position/limit/capacity`, `netOut.remaining`, number of pending tasks/bytes.
- Protocol và cipher suite **sau** handshake.
- `SSLException` class, giai đoạn (handshake, read, write, close), exception category đã chuẩn hóa.

Không log private key, TLS traffic secrets, session tickets, client credential, raw record bytes hoặc decrypted plaintext nhạy cảm; dùng debug flags JSSE trong lab có kiểm soát, không bật bừa bãi trên production.

## 17. Tự kiểm tra kiến thức

**Câu 1.** `SSLEngine.wrap(app, net)` trả `OK` và `bytesConsumed=0` nhưng `bytesProduced>0`. Có phải API bị lỗi không?

**Đáp án:** Không. Khi handshake hoặc đóng TLS, engine có thể sinh TLS record mà không tiêu thụ application plaintext nào.

**Câu 2.** `unwrap` trả `BUFFER_UNDERFLOW` sau khi mới nhận 12 bytes. Nên gọi unwrap tiếp 10.000 lần để chắc sẽ xong không?

**Đáp án:** Không. Giữ bytes chưa xử lý bằng `compact`, chờ thêm dữ liệu từ mạng hoặc grow netIn nếu quá nhỏ, rồi retry; tránh busy loop.

**Câu 3.** `unwrap` trả `BUFFER_OVERFLOW`; nên tăng `netIn` hay `appIn`?

**Đáp án:** **`appIn`** hoặc drain output plaintext đã xác thực, vì **destination** của `unwrap` không đủ chỗ. `BUFFER_UNDERFLOW` mới chủ yếu liên quan input netIn thiếu.

**Câu 4.** `wrap` trả `BUFFER_OVERFLOW` thì thao tác thích hợp là gì?

**Đáp án:** Flush/grow outbound network buffer `netOut`, rồi retry khi đủ chỗ. Không bỏ plaintext chưa `bytesConsumed`.

**Câu 5.** Tại sao `FINISHED` không phải điều kiện duy nhất để thoát vòng lặp qua `engine.getHandshakeStatus()`?

**Đáp án:** `FINISHED` chủ yếu là sự kiện của `SSLEngineResult` khi wrap/unwrap vừa kết thúc handshake; engine thường đã chuyển về `NOT_HANDSHAKING`.

**Câu 6.** `NEED_UNWRAP_AGAIN` và `BUFFER_UNDERFLOW` có cùng hành động không?

**Đáp án:** Không. `NEED_UNWRAP_AGAIN` yêu cầu unwrap tiếp với dữ liệu TLS nội bộ đã nhận, có thể không cần bytes mạng mới; `BUFFER_UNDERFLOW` là thiếu dữ liệu input cần chờ nhận thêm.

**Câu 7.** `NEED_TASK` xuất hiện; có thể submit tasks vào executor rồi tiếp tục wrap ngay trước khi future complete không?

**Đáp án:** Không. Engine cần **kết quả đã hoàn tất** của task; phải chờ, được đánh thức và resume state theo connection owner.

**Câu 8.** `SocketChannel.write(netOut)` trả số byte nhỏ hơn `netOut.remaining()` trước khi gọi. Có được clear netOut không?

**Đáp án:** Không. Phải giữ bytes chưa gửi, tiếp tục `OP_WRITE`; clear sớm làm mất ciphertext và phá thứ tự TLS record.

**Câu 9.** Một TLS client dùng `createSSLEngine("bank.example", 443)` nhưng không bật `setEndpointIdentificationAlgorithm("HTTPS")`. Có thể suy ra hostname luôn được kiểm tra không?

**Đáp án:** Không. Khi dùng raw engine cần cấu hình endpoint identification phù hợp; host/port gợi ý peer context không tự tương đương mọi kiểm tra hostname.

**Câu 10.** Khi client gọi `closeOutbound()`, có thể đóng TCP socket ngay không?

**Đáp án:** Không. Cần tiếp tục gọi `wrap` tạo `close_notify`, flush toàn bộ ciphertext, xử lý inbound close policy rồi mới đóng transport.

**Câu 11.** Sau handshake TLS 1.3, `SSLEngine` còn có thể trả `NEED_WRAP` không?

**Đáp án:** Có. Post-handshake messages như NewSessionTicket/KeyUpdate và close_notify có thể yêu cầu thêm wrap/unwrap. Driver phải tiếp tục theo state thay vì coi TLS đã “bất biến”.

**Câu 12.** Vì sao demo in-memory không được đưa thẳng vào một NIO server production?

**Đáp án:** Demo giả định queue đủ lớn và bytes được chuyển nguyên vẹn, tasks chạy đồng bộ, chưa xử lý full duplex close, buffer growth, partial I/O, backpressure, Selector scheduling và các race/timeout. Tất cả là nghĩa vụ thiết kế của transport driver thực tế.

## 18. Tài liệu tham khảo

- [Java SE 17 — SSLEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): hợp đồng `wrap/unwrap`, transport-independent processing, buffer semantics, delegated tasks, close và concurrency.
- [Java SE 17 — SSLEngineResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.html): `Status`, `HandshakeStatus`, `bytesConsumed()` và `bytesProduced()`.
- [Java SE 17 — SSLEngineResult.HandshakeStatus](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html): `NEED_WRAP`, `NEED_UNWRAP`, `NEED_UNWRAP_AGAIN`, `NEED_TASK`, `FINISHED` và `NOT_HANDSHAKING`.
- [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): hướng dẫn `SSLEngine`, buffer overflow/underflow, delegated task, nonblocking I/O và TLS handshake.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): tạo `SSLEngine` từ key/trust managers.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): protocol/cipher suites và endpoint identification.
- [Java SE 17 — SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): `getPacketBufferSize()`, `getApplicationBufferSize()`, metadata phiên.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `compact`, `position`, `limit` và `remaining`.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html) và [SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): event loop `OP_READ`/`OP_WRITE`.
- [Oracle JDK 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): PKCS#12 keystore và chứng thư thử nghiệm.
