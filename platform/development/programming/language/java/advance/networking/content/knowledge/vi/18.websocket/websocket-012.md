# Giới hạn kích thước thông điệp, nối lại và phục hồi trạng thái phiên WebSocket

## 1. Vấn đề: kết nối còn sống chưa chắc phiên ứng dụng còn đúng

WebSocket cung cấp kênh giao tiếp hai chiều, tồn tại lâu giữa client và server sau HTTP handshake. Tuy nhiên, **WebSocket không tự cung cấp** giới hạn message theo nhu cầu của ứng dụng, tự nối lại khi mất kết nối, hay tự phục hồi lịch sử sự kiện/phiên sau khi reconnect.

Ba nhu cầu liên quan nhưng **khác nhau**:

1. **Giới hạn kích thước thông điệp (message size limit):** không cho peer gửi text/binary quá lớn, quá nhiều fragment hoặc dữ liệu nén phình ra vượt ngân sách bộ nhớ/CPU. Quy định giới hạn theo **byte thực**, chứ không theo số ký tự Java.
2. **Nối lại (reconnect):** tạo **WebSocket connection mới** khi connection cũ bị mất, handshake mới, xác thực lại và kiểm soát retry/backoff. Không phải tự hồi sinh TCP connection cũ.
3. **Phục hồi trạng thái phiên (session recovery):** đồng bộ lại những gì client đã xử lý, sự kiện nào bị lỡ, quyền truy cập còn hiệu lực và những lệnh nào đã được server chấp nhận. Cần **protocol tầng ứng dụng** như sequence ID, replay cursor, snapshot, acknowledgment và idempotency.

Nếu một client chỉ viết `onError -> connect()` mà không quản lý data/sequence, nó có thể **bỏ lỡ thông báo**, **áp dụng một event hai lần** hoặc gửi lại thao tác có side effect sai. Nếu chỉ dùng `StringBuilder.append(fragment)` và không có giới hạn, peer có thể giữ ứng dụng bận và dùng RAM tùy ý, ngay cả khi mỗi frame riêng lẻ nhỏ.

Bài học dùng Java 17 `java.net.http.WebSocket` (client API) và một **server WebSocket loopback cực nhỏ dành cho kiểm thử**, không dùng thư viện ngoài. Tệp Java chạy được ở mục 11 cho thấy event bị chia fragment, mất TCP bất ngờ, reconnect, resume theo sequence, bỏ trùng và kiểm soát giới hạn UTF-8.

## 2. WebSocket frame khác application message

WebSocket RFC 6455 cho phép một **message** được chia thành nhiều **frames**:

```text
Một text message: "seq=1|Hello"

Frame 1: opcode=TEXT,          FIN=0, data="seq=1|He"
Frame 2: opcode=CONTINUATION,  FIN=1, data="llo"

Application receives a completed text message:
  "seq=1|Hello"
```

Một frame không mặc nhiên là một message. Với Java `WebSocket.Listener.onText(socket, data, last)`:

- `data` là **một phần text message đã được decoder cung cấp** dưới dạng `CharSequence`.
- `last==true` nghĩa là phần hiện tại kết thúc text message.
- **Không giả định một callback == một message**; phải gom nhiều phần hoặc dùng streaming parser.
- **Không giả định ranh giới callback khớp ranh giới frame trên wire**; implementation có thể chia/gom theo cách khác.
- Khi nhận binary, `WebSocket.Listener.onBinary(socket, ByteBuffer data, boolean last)` có cùng ý nghĩa "phần của binary message".
- Các control frames như Ping/Pong/Close có quy tắc riêng, không thể trộn như continuation frames. Control frame payload trong RFC 6455 dài **tối đa 125 byte** và không được phân mảnh.

**Rủi ro điển hình:** server gửi một message 100 MiB bằng 100.000 fragment 1 KiB. Nếu client chỉ giới hạn từng lần `data.length() <= 1024`, nó vẫn có thể tích lũy 100 MiB trong `StringBuilder`. Cần giới hạn **tổng message xuyên suốt mọi fragment**, không chỉ kích thước frame hay một callback.

Bảng phân biệt:

| Khái niệm | Điều cần giới hạn | Chỗ áp dụng |
| --- | --- | --- |
| Frame payload size | Bytes của mỗi WebSocket frame | Network/WebSocket codec |
| **Message size** | Tổng bytes của mọi fragment thuộc **một message** | Decoder + application listener |
| Encoded/compressed size | Bytes trên wire khi có compression extension | Codec/proxy |
| Decoded/decompressed size | Dữ liệu sau giải nén/UTF-8 decoding | Application; phòng decompression bomb |
| In-flight message count | Số message đang xử lý đồng thời | Queue/worker/backpressure |
| Outbound queued bytes | Tổng bytes response/request đang chờ gửi | Client và server send queue |
| Session backlog | Số event giữ để replay khi client offline | Session/event store |

**Không chọn giới hạn chỉ bằng số lượng message.** Một message 200 MiB có thể nguy hiểm ngay cả khi mỗi client chỉ có một message in-flight. Ngược lại, 100.000 message 100 byte cũng có thể làm nghẽn CPU/queue.

## 3. Giới hạn theo bytes, không phải `String.length()`

Trong Java, `String.length()` đếm **UTF-16 code units**, không phải số bytes UTF-8 trên network:

```java
String message = "é".repeat(70);
int charactersAsUtf16Units = message.length();               // 70
int utf8Bytes = message.getBytes(StandardCharsets.UTF_8).length; // 140
```

Với ngân sách `MAX_TEXT_BYTES=128`, một message gồm 70 chữ `é` **vượt giới hạn** mặc dù `message.length()==70`. Tương tự, một Unicode supplementary character như emoji chiếm hai UTF-16 code units nhưng thường bốn UTF-8 bytes. Đây là lý do **không dùng `String.length()` làm byte quota**.

Trong Java `onText`, dữ liệu đã chuyển từ WebSocket bytes sang `CharSequence`; một phần callback có thể kết thúc giữa hai UTF-16 surrogate code units. Đừng ép từng fragment thành UTF-8 bytes rồi cộng độc lập nếu decoder/fragment chia surrogate pair: bạn có thể đếm sai hoặc tạo replacement characters. Cách dễ hiểu cho **message nhỏ**:

1. Đặt một **ngưỡng bảo vệ sớm** theo tổng UTF-16 code units đã gom. Với text UTF-8 hợp lệ, mỗi code unit đóng góp ít nhất một byte trên wire; nếu số code units đã vượt `MAX_TEXT_BYTES` thì tổng UTF-8 bytes chắc chắn vượt.
2. Tích lũy tới `last==true` nhưng không cho `StringBuilder` tăng quá ngưỡng sớm.
3. **Sau khi hoàn thành** message, tính `completeText.getBytes(StandardCharsets.UTF_8).length` rồi so với byte quota thật.
4. Nếu dùng message lớn, cần một **streaming UTF-8 size validator có trạng thái giữa fragment** hoặc streaming decoder/parser giới hạn, thay vì luôn tạo một chuỗi khổng lồ. Không tạo `getBytes(...)` cho message đã quá lớn.

Mảnh code trong listener, **chưa phải class độc lập**:

```java
// fields per WebSocket connection:
private static final int MAX_TEXT_BYTES = 128;
private final StringBuilder partial = new StringBuilder();

// inside onText(WebSocket socket, CharSequence fragment, boolean last):
if (fragment.length() > MAX_TEXT_BYTES - partial.length()) {
    socket.sendClose(1008, "message too large");
    return CompletableFuture.completedFuture(null);
}
partial.append(fragment);
if (last) {
    String completed = partial.toString();
    partial.setLength(0);
    if (completed.getBytes(StandardCharsets.UTF_8).length
            > MAX_TEXT_BYTES) {
        socket.sendClose(1008, "message too large");
        return CompletableFuture.completedFuture(null);
    }
    // Parse/validate completed text message here.
}
socket.request(1);
return CompletableFuture.completedFuture(null);
```

**Vì sao dùng close code 1008 chứ không phải 1009 trong mảnh Java trên?** Theo RFC 6455, **1009** có nghĩa "message too big". Tuy nhiên **Java 17 `java.net.http.WebSocket.sendClose(...)` liệt kê 1009 trong các statusCode không được caller gửi** (cùng các code 1002/1003/1006/1007/1010/1012/1013/1015); API có thể hoàn tất `CompletableFuture` với `IllegalArgumentException`. Trong Java 17 API này, dùng **1008 (policy violation)** cho quyết định đóng do application size policy, hoặc `abort()` khi không thể đóng có trật tự. Một WebSocket server implementation khác có thể gửi **1009** đúng RFC; client Java vẫn có thể *nhận* close code đó. Không viết `socket.sendClose(1009, ...)` và tưởng Java 17 đã xử lý giới hạn.

**Điểm cần lưu ý về resource:** `sendClose(...)` chỉ khởi động close handshake phía output; nó **không bảo đảm input đã đóng ngay**. Nếu peer chậm hoặc không hoàn thành handshake, cần deadline và sau đó `abort()`/cleanup để chặn tiêu thụ tài nguyên. Trong code production phải xử lý future thất bại, ngừng xử lý các message tiếp theo và không kích hoạt reconnect vô hạn khi chính client đang từ chối peer quá giới hạn.

## 4. Giới hạn binary message chính xác theo `ByteBuffer.remaining()`

Với binary, WebSocket.Listener cung cấp `ByteBuffer` nên việc đếm byte trực tiếp hơn:

```java
// Mảnh code minh họa trong WebSocket.Listener.
private static final long MAX_BINARY_BYTES = 1024 * 1024;
private long accumulatedBytes = 0;
private final ByteArrayOutputStream binary =
        new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(WebSocket ws,
        ByteBuffer fragment, boolean last) {
    int n = fragment.remaining();
    if (n > MAX_BINARY_BYTES - accumulatedBytes) {
        ws.sendClose(1008, "binary message limit");
        return CompletableFuture.completedFuture(null);
    }

    // Nạp dữ liệu fragment vào bộ tích lũy có upper bound.
    byte[] bytes = new byte[n];
    fragment.get(bytes);
    binary.write(bytes, 0, n);
    accumulatedBytes += n;

    if (last) {
        byte[] complete = binary.toByteArray();
        // Parse/validate complete binary bytes. No untrusted deserialization.
        binary.reset();
        accumulatedBytes = 0;
    }
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
```

*Mảnh code có field trong listener, cần import `java.io.ByteArrayOutputStream`, `ByteBuffer`, `WebSocket`, `CompletionStage` và `CompletableFuture`; không là chương trình standalone.*

Quan trọng:

- Dùng `fragment.remaining()`, **không** dùng `capacity()` hoặc `limit()` đơn lẻ; chỉ khoảng `position...limit` đang chứa bytes của fragment.
- Dùng kiểm tra `n > MAX - accumulated` trước phép cộng để tránh overflow và vượt quota.
- Không giữ reference tới `ByteBuffer` của callback cho worker dùng mãi khi không biết lifecycle/ownership; copy bytes hoặc có hợp đồng ownership rõ ràng.
- Nếu protocol hỗ trợ file stream lớn, không nên `toByteArray()` toàn bộ; **stream vào file .part** có total-size limit và checksum, rồi commit khi message/end-of-file protocol hoàn thành.
- Một ứng dụng có thể chọn **binary streaming chunks là các message độc lập**. Khi đó phải bảo vệ cả giới hạn mỗi message và tổng kích thước/offset của **tệp logic**; không nhầm mỗi WebSocket message là toàn bộ tệp.
- Decoder cấp WebSocket và server cần ngăn malformed frame, invalid UTF-8, control frame sai, fragmentation abuse; listener của client không phải lớp kiểm soát duy nhất.

## 5. Quản lý nhu cầu nhận và chống overload trên Java WebSocket

Java 17 `WebSocket.Listener` dùng cơ chế **demand** thông qua `webSocket.request(n)`. Với `onOpen`, thường bắt đầu:

```java
@Override
public void onOpen(WebSocket socket) {
    socket.request(1);
}
```

Mỗi lần xử lý hoàn tất một callback mà vẫn muốn nhận thêm:

```java
socket.request(1);
```

Đây không phải "gửi request HTTP"; nó tăng số callback receive mà WebSocket client có thể chuyển cho listener. Điều này hỗ trợ **flow control ở tầng callback**:

- Không gọi `request(...)` vô hạn mà không có ngân sách.
- Với message nhỏ xử lý đồng bộ nhanh, listener có thể xử lý một phần rồi `request(1)`.
- Nếu đưa message sang worker/queue, chỉ gọi `request(1)` khi queue có chỗ hoặc công việc cần thiết đã hoàn tất; đặt upper bound cho message và work queue.
- Tránh chạy tác vụ database blocking hoặc xử lý CPU lâu trong callback của WebSocket client; dùng bounded executor, lưu ownership và điều khiển demand theo trạng thái.
- Demand không phải **hard cap trên mọi buffer network/JDK**. Client và server vẫn cần giới hạn frame/message, byte quota và tổng số connection.
- WebSocket send có API bất đồng bộ trả `CompletableFuture<WebSocket>`. **Future hoàn tất nghĩa bytes đã được gửi theo hợp đồng API, không đồng nghĩa peer đã commit nghiệp vụ**. Cần **ACK tầng ứng dụng** riêng.

Ví dụ **lỗi**:

```java
// PHẢN VÍ DỤ: peer chậm và producer nhanh có thể xếp nhiều send.
for (String event : hugeEventStream) {
    socket.sendText(event, true); // Không hề giới hạn outstanding queue.
}
```

Trong thực tế, việc gửi đồng thời frame/message không tuân trạng thái trước có thể dẫn tới exception hoặc xếp hàng tùy API/triển khai. Cách đúng là **serialize outbound** theo một queue bounded, chỉ enqueue khi có ngân sách, chain/completion phù hợp và xử lý failure. Với `sendBinary(ByteBuffer,...)`, không sửa buffer khi send future còn đang dùng nó.

**Nhiều giới hạn độc lập cần áp:** max bytes/message, max fragment count, max messages/s, max concurrent sessions, max queued send bytes, max in-flight jobs và timeout thao tác. Chỉ có một `MAX_MESSAGE_BYTES` không giải quyết tình huống 1.000 message nhỏ mỗi giây.

## 6. Connection lifecycle: nối lại là một kết nối mới

WebSocket không có nút `reconnect()` trong API Java 17. Khi socket mất, client **phải tạo handshake mới**:

```text
DISCONNECTED
     |
     v
CONNECTING (new HTTP Upgrade / TLS handshake)
     |
     v
AUTHENTICATING / NEGOTIATING APP VERSION
     |
     v
RESUMING (cursor, server validation, replay/snapshot)
     |
     v
LIVE (application events)
     |
     +---- network failure ----> RETRY_WAIT ----> CONNECTING
     |
     +---- auth revoked -------> STOP; ask for fresh credentials
     |
     +---- explicit logout ----> CLOSED; no reconnect
```

Các trạng thái phục vụ hai câu hỏi:

1. **Connection đã sẵn sàng chưa?** HTTP/WebSocket handshake đã thành công, connection open.
2. **Application session có thể hoạt động bình thường chưa?** Auth pass, replay/snapshot pass, client biết nó có trạng thái đủ mới và không có gap.

Phương thức `onOpen` được gọi khi WebSocket connection mở, nhưng **không chứng minh application session đã hồi phục**. Nếu UI ngay lập tức hiển thị "đã đồng bộ", có thể bỏ lỡ dữ liệu từ lúc offline.

Khi connection mới mở:

- Xác thực lại bằng cơ chế được phép, kể cả token mới nếu token cũ đã hết hạn.
- Gửi version/negotiation của application protocol.
- Gửi thông tin **resume cursor** có phạm vi rõ (ví dụ `lastAppliedSequence`), kèm session/stream identity và token bảo vệ theo thiết kế.
- Đợi server trả `RESUME_OK` / replay hoặc `SNAPSHOT_REQUIRED` trước khi coi state synchronized.
- Sau khi đồng bộ, mới thực hiện những thao tác cần trạng thái mới.

**Tái kết nối TCP/WebSocket không giữ server memory session.** Server có thể đã restart, deploy sang node khác, mất in-memory subscription hoặc xóa replay log. Cơ chế "nối lại" muốn bền vững phải có **event store/shared session store** hoặc snapshot có thể tải lại.

## 7. Khi nào nối lại, khi nào dừng hẳn?

Không phải mọi lần đóng đều nên reconnect. Đánh giá các nhóm:

| Tình huống | Quyết định mẫu |
| --- | --- |
| Mất Wi-Fi/TCP reset/EOF không có Close frame | Retry có backoff và giới hạn |
| Server restart/chuyển node | Retry sau backoff, rồi resume |
| Server trả close `1001 Going Away` | Tùy contract, thường reconnect có delay |
| Server báo overload/retry-after theo app protocol | Respect server delay, backoff/jitter |
| Normal close `1000` khi user chủ động logout | **Không** reconnect |
| Auth invalid/forbidden trong handshake (401/403) | Dừng và yêu cầu token/đăng nhập đúng; không retry vô hạn |
| Policy violation `1008` do client gửi dữ liệu sai | Không retry lặp lại cùng payload |
| Message too large `1009` nhận từ server | Sửa payload/limit; không tạo vòng lặp gửi lại nguyên xi |
| App protocol version không tương thích | Dừng, báo client update hoặc negotiate phiên bản hỗ trợ |
| Cố tình offline hoặc ứng dụng shutdown | Hủy timers/jobs; không tự bật kết nối mới |
| Một request/command đã gửi nhưng chưa ACK | Trạng thái **unknown**; không mặc định resend như chưa xử lý |

**Mã close `1006` là mã quan sát cho mất kết nối bất thường, không phải mã hợp lệ để gửi trong Close frame.** Tương tự, lỗi transport có thể được báo bằng `onError` thay vì `onClose`; cần một đường xử lý chung và tránh lên lịch retry **hai lần**.

## 8. Backoff, jitter, ngân sách thử lại và generation ID

Retry liên tục không delay có thể khiến server đang quá tải bị hàng nghìn client reconnect cùng lúc (thundering herd). Một chiến lược production:

```text
baseDelay = 250 ms
maxDelay  = 30 s
attempt:  0, 1, 2, ...
cap = min(maxDelay, baseDelay * 2^attempt)
delay = random(0, cap)      // full jitter, ví dụ
```

Điểm cần có:

- **Exponential backoff + jitter** để giảm các đợt reconnect đồng bộ.
- **Trần attempt/thời lượng** hoặc chính sách retry theo trạng thái app; khi hết ngân sách, báo lỗi có thể can thiệp.
- **Reset backoff chỉ khi kết nối ổn định và resume thành công** đủ lâu, không chỉ `onOpen`.
- Tôn trọng server-provided retry interval nếu protocol định nghĩa và đã xác thực.
- Một bộ điều phối (scheduler) và một **connection attempt generation ID** để bỏ callback đến muộn từ socket cũ.
- Guard **retry scheduled once** per attempt bằng `AtomicBoolean`/state machine, vì `onError`/`onClose`/connect-future failure có thể cùng báo lỗi.
- Khi user logout, cancel pending retry, đóng socket và hủy công việc; không để timer "hồi sinh" phiên đã logout.

Mẫu mã minh họa trong chương trình chạy:

```java
void retry() {
    if (owner.finished.isDone()
            || !retryQueued.compareAndSet(false, true)) return;
    owner.timers.schedule(owner::connect, 100,
            TimeUnit.MILLISECONDS);
}
```

**Đây là timer cố định 100 ms phục vụ test localhost, không phải cấu hình production.** Hệ thống thật cần exponential backoff/jitter, idle timeout, auth state, throttling và network-awareness.

Nếu dùng thread pool timer, không được tạo một thread mới không giới hạn cho mỗi retry; dùng `ScheduledExecutorService` có vòng đời rõ ràng. Sau khi đóng ứng dụng, phải shutdown timer để không giữ JVM hoặc rò rỉ callback.

## 9. Thiết kế protocol để phục hồi message và state

WebSocket không có giao thức replay chung cho mọi app. Một schema nhỏ thường cần:

```text
Client -> Server:
  HELLO {appProtocolVersion, sessionId, resumeToken, lastAppliedSeq}

Server -> Client:
  RESUME_OK {streamId, epoch, replayFromSeq}
  EVENT {streamId, epoch, seq, eventId, payload}
  ... EVENT ...

Client -> Server:
  ACK {streamId, epoch, lastDurablyAppliedSeq}

Khi không còn lịch sử:
  RESYNC_REQUIRED {reason, minAvailableSeq, snapshotVersion}

Client:
  tải snapshot / yêu cầu full state từ kênh đáng tin
  áp snapshot nguyên tử
  bắt đầu replay event sau snapshotVersion
  chuyển trạng thái SYNCED rồi LIVE
```

Các trường cần phân biệt:

| Trường | Tác dụng |
| --- | --- |
| `sessionId` | Nhận diện phiên ứng dụng có quyền được nối lại; không suy từ TCP connection |
| `resumeToken` | Chứng minh quyền tiếp tục phiên; phải bảo vệ, hết hạn/rotate và scope |
| `streamId` | Phạm vi của sequence; tránh trộn hai stream của hai resource |
| `epoch/generation` | Phân biệt sequence sau restart/reset/topology change |
| `seq` | Số thứ tự tăng theo stream, dùng phát hiện duplicate/gap |
| `eventId` | Định danh sự kiện phục vụ idempotency/dedup dài hạn |
| `lastDurablyAppliedSeq` | Cursor đã thực sự được client **commit** (không chỉ đã nhìn thấy) |
| `snapshotVersion` | Mốc trạng thái đầy đủ làm nền để replay delta |
| `ACK` | Xác nhận ở **tầng ứng dụng**, không phải WebSocket transport send future |
| `retention window` | Khoảng lịch sử mà server có thể replay |

**Luồng bình thường:**

```text
Server stored events: #41, #42, #43, #44
Client lastAppliedSeq: 41
Connection lost while #42..#44 were produced
      |
      v
New WebSocket handshake + auth
      |
      v
Client HELLO(lastAppliedSeq=41)
      |
      v
Server replays #42, #43, #44 in order
      |
      v
Client validates, applies and durably commits each event
      |
      v
Client ACK 44
      |
      v
LIVE from #45 onward
```

**Trường hợp ACK bị mất:** server có thể gửi lại #44 dù client đã commit #44. Vì vậy client cần phát hiện `seq<=lastAppliedSeq` để **không áp dụng event hai lần**, sau đó ACK cursor hiện tại. Không được ngộ nhận một lần `sendText("ACK 44")` hoàn tất future là server đã nhận và lưu ACK đó.

**Trường hợp gap:** nếu client đang ở seq41 mà nhận seq44 trước 42/43, không tự bỏ qua đến 44. Phải buffer/reorder có giới hạn hoặc yêu cầu **resync/snapshot**, tùy contract. Nếu event #42 đã hết hạn khỏi replay log, server phải trả `RESYNC_REQUIRED`, không nói "resume thành công" rồi bỏ mất dữ liệu.

## 10. Exactly-once là yêu cầu tầng ứng dụng, không phải tính năng mặc định của WebSocket

Trong hệ thống phân tán, mất kết nối có thể xảy ra **sau khi server xử lý lệnh nhưng trước khi client thấy ACK**:

```text
Client: SEND transferFunds(requestId=X)
Server: commit transferFunds(X)
TCP breaks before ACK
Client cannot know whether X committed
```

Nối lại rồi gửi lại **lệnh chuyển tiền không có idempotency key** có thể gây xử lý hai lần. Cần:

1. Client sinh **request ID/idempotency key** ổn định cho một thao tác logic.
2. Server lưu trạng thái/response theo key trong phạm vi user/tenant và thời hạn phù hợp, cùng transaction/commit bảo đảm không làm hai lần.
3. Khi reconnect, client hỏi kết quả hoặc resend **cùng ID**, không tạo ID mới cho cùng tác vụ.
4. Client chỉ cập nhật cursor **sau khi application state được áp dụng bền vững**, để event replay không làm bỏ lỡ side effect.
5. Nếu nghiệp vụ cần thứ tự nghiêm ngặt, xử lý events tuần tự hoặc có reorder logic theo seq; nhiều worker xử lý song song có thể hoàn tất lệch thứ tự.

**At-least-once replay + idempotency/dedup** có thể tạo hiệu ứng nghiệp vụ đúng một lần trong phạm vi transaction được thiết kế; không phải WebSocket transport có guarantee exactly-once. Không hứa "mỗi event chỉ nhận đúng một lần" khi mạng mất và ACK có thể bị lạc.

Với UI không đòi durability, có thể chỉ giữ `lastAppliedSeq` trong RAM và coi mất trạng thái sau restart là cần snapshot mới. Với tài chính, đơn hàng hoặc workflow quan trọng, cursor/dedup và xử lý nghiệp vụ phải nằm trong durable store/transaction.

## 11. Ví dụ Java 17 đầy đủ: fragmentation, mất kết nối, resume, bỏ trùng

Ví dụ dưới đây dùng **JDK thuần**, gồm:

- Java `HttpClient.newWebSocketBuilder()` tạo WebSocket client (API Java 17).
- **Server loopback test tối giản** bằng `ServerSocket` chỉ để mô phỏng HTTP Upgrade WebSocket handshake và vài **small frames**. Nó không hỗ trợ đủ RFC 6455, không kiểm tra authentication hay extension, không dùng TLS; **không được dùng làm WebSocket server sản phẩm**.
- Server kết nối lần đầu: client gửi `RESUME 0`; server gửi event #1 trong **hai frames** (TEXT FIN=0 rồi CONTINUATION FIN=1), chờ `ACK 1` rồi đóng TCP đột ngột **không gửi Close frame**.
- Client nhận mất kết nối, schedule reconnect 100 ms để test, bắt đầu kết nối mới và gửi `RESUME 1`.
- Server lần hai cố tình gửi lại event #1 rồi event #2. Client bỏ qua duplicate #1, xử lý #2, ACK 2, sau đó server gửi Close 1000.
- Listener giới hạn `MAX_TEXT_BYTES=128` cho toàn text message, kiểm tra cả tổng UTF-16 code units và UTF-8 bytes. **Trong Java 17, khi tự đóng do vượt chính sách, dùng 1008 thay vì 1009** như đã giải thích ở mục 3.
- Cuối chương trình chạy phép thử `"é".repeat(70)` để nhắc rằng 70 code units vẫn là 140 UTF-8 bytes, vượt limit 128.

**Tên tệp: `WebSocketResumeDemo.java`**

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public final class WebSocketResumeDemo {
    static final int MAX_TEXT_BYTES = 128;

    static final class Client {
        final HttpClient http = HttpClient.newHttpClient();
        final ScheduledExecutorService timers =
                Executors.newSingleThreadScheduledExecutor();
        final URI uri;
        final AtomicLong lastApplied = new AtomicLong(0);
        final AtomicInteger attempts = new AtomicInteger(0);
        final CompletableFuture<Void> finished = new CompletableFuture<>();

        Client(URI uri) {
            this.uri = uri;
        }

        void connect() {
            if (finished.isDone()) return;
            int attempt = attempts.incrementAndGet();
            if (attempt > 4) {
                finished.completeExceptionally(
                        new IOException("Reconnect budget exhausted"));
                return;
            }
            WsListener listener = new WsListener(this);
            http.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(uri, listener)
                    .whenComplete((ws, error) -> {
                        if (error != null) listener.retry();
                    });
        }

        void stop() {
            timers.shutdownNow();
        }
    }

    static final class WsListener implements WebSocket.Listener {
        final Client owner;
        final StringBuilder pending = new StringBuilder();
        final AtomicBoolean retryQueued = new AtomicBoolean(false);

        WsListener(Client owner) {
            this.owner = owner;
        }

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
            String resume = "RESUME " + owner.lastApplied.get();
            System.out.println("client " + resume);
            socket.sendText(resume, true).whenComplete((ok, ex) -> {
                if (ex != null) retry();
            });
        }

        @Override
        public CompletionStage<?> onText(WebSocket socket,
                CharSequence fragment, boolean last) {
            if (fragment.length() > MAX_TEXT_BYTES - pending.length()) {
                // JDK 17 WebSocket.sendClose does not allow status 1009.
                socket.sendClose(1008, "message too large");
                owner.finished.completeExceptionally(
                        new IOException("Text exceeds safe character cap"));
                return CompletableFuture.completedFuture(null);
            }
            pending.append(fragment);
            if (last) {
                String message = pending.toString();
                pending.setLength(0);
                if (message.getBytes(StandardCharsets.UTF_8).length
                        > MAX_TEXT_BYTES) {
                    socket.sendClose(1008, "message too large");
                    owner.finished.completeExceptionally(
                            new IOException("Text exceeds UTF-8 byte cap"));
                    return CompletableFuture.completedFuture(null);
                }
                try {
                    int separator = message.indexOf('|');
                    if (!message.startsWith("seq=") || separator <= 4) {
                        throw new IOException("Bad application message");
                    }
                    long seq = Long.parseLong(
                            message.substring(4, separator));
                    String text = message.substring(separator + 1);
                    long lastApplied = owner.lastApplied.get();
                    if (seq <= lastApplied) {
                        System.out.println("duplicate seq=" + seq
                                + " ignored");
                    } else if (seq == lastApplied + 1) {
                        // Demo commits in memory. Production commits durably
                        // before advancing the cursor and sending ACK.
                        owner.lastApplied.set(seq);
                        System.out.println("applied seq=" + seq
                                + " text=" + text);
                    } else {
                        throw new IOException("Gap: snapshot required");
                    }
                    long acknowledged = owner.lastApplied.get();
                    socket.sendText("ACK " + acknowledged, true)
                            .whenComplete((ok, ex) -> {
                                if (ex != null) retry();
                            });
                } catch (Exception error) {
                    owner.finished.completeExceptionally(error);
                    socket.sendClose(1008, "invalid event");
                    return CompletableFuture.completedFuture(null);
                }
            }
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        void retry() {
            if (owner.finished.isDone()
                    || !retryQueued.compareAndSet(false, true)) return;
            System.out.println("connection lost: reconnecting");
            owner.timers.schedule(owner::connect, 100,
                    TimeUnit.MILLISECONDS);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket socket,
                int code, String reason) {
            if (code == 1000 && owner.lastApplied.get() == 2) {
                System.out.println("normal close after seq=2");
                owner.finished.complete(null);
            } else {
                retry();
            }
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            retry();
        }
    }

    static int read(InputStream in) throws IOException {
        int value = in.read();
        if (value < 0) throw new EOFException("Unexpected EOF");
        return value;
    }

    static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        int a = -1, b = -1, c = -1, d;
        while (result.size() < 8192) {
            d = read(in);
            result.write(d);
            if (a == '\r' && b == '\n'
                    && c == '\r' && d == '\n') {
                return result.toString(StandardCharsets.US_ASCII);
            }
            a = b; b = c; c = d;
        }
        throw new IOException("Too many header bytes");
    }

    static void handshake(InputStream in, OutputStream out)
            throws Exception {
        String request = readHeaders(in);
        String key = null;
        for (String line : request.split("\r\n")) {
            if (line.regionMatches(true, 0,
                    "Sec-WebSocket-Key:", 0, 18)) {
                key = line.substring(18).trim();
            }
        }
        if (key == null) throw new IOException("No WebSocket key");
        byte[] raw = MessageDigest.getInstance("SHA-1").digest(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                        .getBytes(StandardCharsets.US_ASCII));
        String accept = Base64.getEncoder().encodeToString(raw);
        out.write(("HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n")
                .getBytes(StandardCharsets.US_ASCII));
        out.flush();
    }

    static void writeFrame(OutputStream out, int opcode,
            boolean fin, byte[] payload) throws IOException {
        if (payload.length >= 126)
            throw new IllegalArgumentException("Demo frame too large");
        out.write((fin ? 0x80 : 0) | opcode);
        out.write(payload.length); // Server frames are never masked.
        out.write(payload);
        out.flush();
    }

    static void writeText(OutputStream out, String text)
            throws IOException {
        writeFrame(out, 1, true, text.getBytes(StandardCharsets.UTF_8));
    }

    static String readClientText(InputStream in) throws IOException {
        int first = read(in);
        int second = read(in);
        int opcode = first & 0x0f;
        int n = second & 0x7f;
        boolean masked = (second & 0x80) != 0;
        if (opcode != 1 || !masked || n >= 126) {
            throw new IOException("Unexpected demo client frame");
        }
        byte[] mask = in.readNBytes(4);
        byte[] payload = in.readNBytes(n);
        if (mask.length != 4 || payload.length != n)
            throw new EOFException();
        for (int i = 0; i < n; i++)
            payload[i] = (byte) (payload[i] ^ mask[i % 4]);
        return new String(payload, StandardCharsets.UTF_8);
    }

    static void runServer(ServerSocket server) throws Exception {
        for (int session = 1; session <= 2; session++) {
            try (Socket peer = server.accept()) {
                peer.setSoTimeout(5000);
                InputStream in = peer.getInputStream();
                OutputStream out = peer.getOutputStream();
                handshake(in, out);
                String resume = readClientText(in);
                if (!resume.equals("RESUME " + (session - 1)))
                    throw new IOException("Bad cursor: " + resume);
                if (session == 1) {
                    writeFrame(out, 1, false, "seq=1|He".getBytes(
                            StandardCharsets.UTF_8));
                    writeFrame(out, 0, true, "llo".getBytes(
                            StandardCharsets.UTF_8));
                    if (!"ACK 1".equals(readClientText(in)))
                        throw new IOException("Missing ACK 1");
                    // Drop underlying TCP without a WebSocket CLOSE frame.
                } else {
                    writeText(out, "seq=1|Hello"); // At-least-once duplicate.
                    writeText(out, "seq=2|World");
                    String ack;
                    do {
                        ack = readClientText(in);
                    } while ("ACK 1".equals(ack));
                    if (!"ACK 2".equals(ack))
                        throw new IOException("Missing ACK 2");
                    writeFrame(out, 8, true, new byte[]{3, (byte) 232});
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0));
            server.setSoTimeout(5000);
            AtomicReference<Throwable> serverError = new AtomicReference<>();
            Thread serverThread = new Thread(() -> {
                try {
                    runServer(server);
                } catch (Throwable error) {
                    serverError.set(error);
                }
            }, "loopback-ws-server");
            serverThread.start();

            URI uri = URI.create("ws://127.0.0.1:"
                    + server.getLocalPort() + "/events");
            Client client = new Client(uri);
            try {
                client.connect();
                client.finished.get(10, TimeUnit.SECONDS);
            } finally {
                client.stop();
            }
            serverThread.join(5000);
            if (serverThread.isAlive())
                throw new IllegalStateException("Server thread stuck");
            if (serverError.get() != null)
                throw new IllegalStateException(
                        "Server failed", serverError.get());
            int utf8Size = "é".repeat(70).getBytes(
                    StandardCharsets.UTF_8).length;
            System.out.println("UTF-8 size test: " + utf8Size
                    + " bytes > limit " + MAX_TEXT_BYTES
                    + ": " + (utf8Size > MAX_TEXT_BYTES));
        }
    }
}
```

**Chạy bằng JDK 17:**

```bash
javac --release 17 WebSocketResumeDemo.java
java WebSocketResumeDemo
```

**Stdout thực tế (một lần chạy đã kiểm thử trên Java 17):**

```text
client RESUME 0
applied seq=1 text=Hello
connection lost: reconnecting
client RESUME 1
duplicate seq=1 ignored
applied seq=2 text=World
normal close after seq=2
UTF-8 size test: 140 bytes > limit 128: true
```

### 11.1. Giải thích output và giới hạn kiểm thử

- `client RESUME 0`: chưa áp dụng event nào, client yêu cầu tiếp tục từ cursor 0.
- `applied seq=1 text=Hello`: server gửi **hai frames**, client gom callback đến `last==true` và xử lý một message trọn vẹn.
- `connection lost: reconnecting`: server đóng TCP bất ngờ mà **không** phát WebSocket Close frame. Client đi qua `onError` và schedule một retry.
- `client RESUME 1`: kết nối WebSocket hoàn toàn mới, gửi cursor đã xử lý.
- `duplicate seq=1 ignored`: server mô phỏng at-least-once delivery; client không áp lại event trùng.
- `applied seq=2 text=World`: phần còn thiếu được xử lý liên tục đúng sequence.
- `normal close after seq=2`: server gửi close 1000 để kết thúc bài test; client coi đó là kết thúc thành công của nhiệm vụ, không retry.
- `UTF-8 size test: 140 bytes > limit 128: true`: 70 ký tự `é` chiếm 140 UTF-8 bytes. Dòng này kiểm tra **quy tắc byte limit**, không phải một WebSocket quá tải được server gửi trong test.

**Phạm vi chủ đích:** server dùng `ServerSocket` chỉ hỗ trợ hai handshake, các frame nhỏ, masked client text đơn giản và vài opcode cụ thể. Nó **không phải WebSocket server tuân chuẩn đầy đủ**: không xử lý đầy đủ fragmentation client, extended payload lengths, TLS, Ping/Pong, origin validation, authentication, compression, HTTP header security hay scale. Với sản phẩm, sử dụng framework/server WebSocket đã được kiểm thử, đặt max frame/message limit ở codec và business layer. Client demo dùng cursor **in-memory**, timer 100 ms và không có token; đây **không phải durable session recovery** hay retry policy production.

**Về giới hạn 1008:** bài test chỉ phát các message nhỏ hợp lệ và kiểm tra byte count của chuỗi `é` sau khi kết thúc; nó **không kích hoạt nhánh WebSocket.sendClose(1008,...) bằng một message lớn**. Nhánh này dựa trên contract của API Java 17 và cần được kiểm thử riêng trong integration test của sản phẩm. Không tuyên bố dòng stdout test đó chứng minh hành vi close frame 1008 trên wire.

## 12. Bổ sung protocol production: HELLO, ACK, snapshot và cutover

Demo dùng payload text đơn giản:

```text
Client: RESUME 1
Server: seq=1|Hello
Server: seq=2|World
Client: ACK 1
Client: ACK 2
```

Một hệ thống thực tế nên có schema rõ ràng hơn:

```json
{"type":"HELLO","protocol":2,"streamId":"orders-42","epoch":"e17",
 "lastAppliedSeq":1042,"resumeToken":"<opaque-secret-not-logged>"}

{"type":"RESUME_OK","streamId":"orders-42","epoch":"e17",
 "replayFromSeq":1043}

{"type":"EVENT","streamId":"orders-42","epoch":"e17","seq":1043,
 "eventId":"evt-...","payload":{"orderId":"42","status":"SHIPPED"}}

{"type":"ACK","streamId":"orders-42","epoch":"e17","seq":1043}
```

*JSON này là ví dụ payload protocol tùy chỉnh, không phải định dạng WebSocket bắt buộc.* Các giá trị token/ID dạng minh họa, không dùng secret thực tế.

**Snapshot + delta cần cutover nhất quán**. Ví dụ có snapshot ở sequence #500. Server phải bảo đảm:

1. Snapshot phản ánh trạng thái đến một mốc nhất quán #500.
2. Replay event #501 trở đi được giữ từ một log còn tồn tại.
3. Không có "khoảng trống" giữa lúc lấy snapshot và lúc bắt đầu subscription live.
4. Client không được apply event #501 trước khi snapshot #500 đã được commit.
5. Khi replay kết thúc và stream live tiếp tục, event mới phải được nối sau cursor, có cơ chế bảo vệ thứ tự và retention.

Nếu event log chỉ giữ đến #600 nhưng client ở #200, server phải báo snapshot required thay vì âm thầm gửi #601 và đánh dấu synced. Trường hợp permission thay đổi, server phải xác thực lại quyền đọc stream trước replay, không coi resume token là vé vô thời hạn.

## 13. Kết nối nhiều node: state ở đâu sau khi reconnect?

Giả sử client nối tới load balancer:

```text
Client
   |
   v
Load Balancer
   |------ Node A: connection cũ, client đã nhận tới #17
   |
   +------ Node B: connection mới sau reconnect
                    |
                    +--> Shared event log / database
                    +--> Shared session or resume metadata
                    +--> Snapshot store
```

Nếu Node B chỉ lưu trong RAM những event bắt đầu từ lúc nó chạy, nó không thể replay event #18, #19 từ Node A. Cần một trong các chiến lược:

- **Shared durable event log** theo stream/user (có offset/sequence), Node nào cũng đọc và replay được.
- **Snapshot + replay** với log retention và version rõ ràng.
- **Session affinity** có thể giảm số lần đổi node, nhưng **không phải bảo đảm recovery** khi node hỏng, deploy lại hoặc autoscaling.
- **Pub/sub có replay** hoặc database change log với thứ tự và retention được quản lý; không nhầm ephemeral pub/sub với durable event store.

Bảo vệ replay bằng authorization trên mỗi stream/tenant: nếu server chỉ nhìn `lastSeq=7` mà cho bất kỳ client nào đọc lịch sử stream, đó là lỗ hổng lộ dữ liệu. Token và auth phải kiểm tra quyền truy cập cụ thể, có expire/revocation.

## 14. Mất kết nối trong lúc gửi lệnh: cần outbox và trạng thái UNKNOWN

Không chỉ server→client event mới cần recovery. Client→server command cũng có vùng bất định:

```text
Client: sendText("CREATE_ORDER idempotencyKey=X")
Network: bytes tới server
Server: commit order X
Network: disconnect before response ACK
Client: sendText future may complete or fail, but result unknown
```

Thiết kế phù hợp:

1. Ghi command vào **durable outbox** của client khi nghiệp vụ yêu cầu.
2. Gắn `commandId`/`idempotencyKey` duy nhất cho tác vụ logic.
3. Khi reconnect, hỏi trạng thái command hoặc gửi lại **cùng key**, không tự tạo một command mới.
4. Server lưu kết quả idempotency đủ lâu để chống duplicate retry; transaction phải thống nhất với business side effect.
5. Sau khi nhận **application ACK** tin cậy, client cập nhật trạng thái outbox.
6. Đừng coi `CompletableFuture<WebSocket>` của `sendText` là business ACK.

Nếu app chỉ gửi tín hiệu "typing..." hay telemetry có thể bỏ qua, không nhất thiết xây durable outbox; có thể gửi lại trạng thái mới nhất. Chọn theo **semantics của từng loại message** thay vì ép một protocol nặng cho mọi nội dung.

## 15. Authentication, wss:// và thông tin phiên

Khi dùng WebSocket production:

- Ưu tiên **`wss://`** để có TLS encryption và server certificate/hostname verification; demo `ws://127.0.0.1` chỉ dùng loopback.
- HTTP handshake và application protocol phải kiểm tra auth hợp lệ. Resume token phải ngẫu nhiên đủ mạnh, có scope, expiration, rotation và revoke; không tự tin vào một số seq do client gửi.
- Tránh nhét bearer/resume token bí mật vào URL query string vì URL dễ bị ghi vào proxy/server/access log. Dùng phương thức truyền token phù hợp với server/client và chính sách bảo mật; Java WebSocket.Builder có API cấu hình HTTP request headers, nhưng phải xử lý các hạn chế header và redirect.
- Browser WebSocket thường mang cookies theo chính sách browser; server phải kiểm tra **Origin** và chống cross-site WebSocket hijacking khi dùng cookie auth. Java client không phải browser nên CORS/SameSite không phải firewall thay backend authorization.
- Kiểm tra và giới hạn message **trước** khi parse JSON/XML hay deserialize, vì content-type/payload do peer cung cấp không đáng tin.
- Nếu WebSocket nằm sau proxy/load balancer, kiểm tra idle timeout, WebSocket upgrade forwarding, maximum frame/message size, session affinity và các chế độ TLS termination.
- Khi một phiên bị logout hoặc token revoke, đóng các connection tương ứng và **không retry tự động** bằng token đã mất quyền. Clear/outbox/replay cursor theo chính sách dữ liệu.
- Giảm lượng thông tin trả trong close reason; không để token, stack trace hoặc payload nhạy cảm xuất hiện trong protocol/log.

**Giới hạn không là toàn bộ bảo mật.** Một message hợp lệ 5 KB vẫn có thể là JSON cực sâu, payload độc hại, lệnh trái quyền hoặc SQL injection. Phải validate schema, authorization và rate limits.

## 16. Heartbeat, half-open connection và deadline

TCP/WebSocket connection có thể trông "mở" trong JVM nhưng peer hoặc proxy đã mất đường truyền (half-open). Cần heartbeat/deadline để phát hiện:

- WebSocket có **Ping/Pong control frames**; Java `WebSocket.sendPing(ByteBuffer)` gửi Ping, `WebSocket.Listener.onPong(...)` nhận Pong. Trong JDK WebSocket implementation, khi nhận Ping có thể gửi Pong tương ứng tự động theo API, nhưng chính sách heartbeat/timeout vẫn do ứng dụng quyết định.
- Ping/Pong payload tối đa **125 byte** theo WebSocket protocol.
- Ứng dụng có thể dùng **application heartbeat message** khi cần đo tình trạng backend/business session, khác với TCP/WebSocket transport còn sống.
- Đo thời điểm Pong hoặc application reply gần nhất và có deadline, thay vì chờ TCP timeout rất lâu.
- Không dùng heartbeat để thay replay/resume. Connection đang sống không chứng minh không bỏ sót event do bug hoặc queue overflow.

Trên Java, cần chú ý `sendPing` trả future **gửi ping** chứ không phải future chứng minh **đã nhận Pong**. Nếu cần kiểm tra liveness, đánh dấu nonce/sequence trong Ping payload rồi xử lý matching Pong ở listener. Quản lý ping rate để không tự tạo flood và xử lý proxy/server idle timeout hợp lý.

## 17. Giới hạn có nén, binary/file và payload phức tạp

Ứng dụng có thể bật WebSocket compression extension như permessage-deflate. Khi có nén:

```text
Uncompressed logical event  = 15 MiB
Compressed WebSocket bytes  = 100 KiB
Frame size limit            = 2 MiB
Application message limit   = 1 MiB
```

Dù wire payload nhỏ hơn frame cap, **decoded message 15 MiB vẫn vượt application cap 1 MiB**. Cần giới hạn **decompressed data**, CPU và tỉ lệ expansion. Đừng chỉ nhìn Content-Length HTTP handshake; sau khi WebSocket được nâng cấp, WebSocket messages không được framing bằng HTTP Content-Length nữa.

Với file transfer over WebSocket:

- Chia thành **application chunks** có offset, file ID, total expected size và digest (nếu tin cậy).
- Giới hạn mỗi chunk/message và tổng file; dùng streaming output vào file tạm, không tích toàn bộ vào RAM.
- Phân biệt transport continuation frames với **application chunks**: continuation frames thuộc cùng WebSocket message, còn application chunks có thể là nhiều WebSocket messages.
- Xác minh offset, sequence, checksum, quyền truy cập, quota, deadline và cấm path traversal khi lưu file.
- Khi reconnect, chỉ tiếp tục từ offset đã commit; nếu server gửi lại chunk cũ phải dedup/verify. Không append dữ liệu mới bừa vào file khác version.
- Cần reset parser/partial message khi connection chết: một WebSocket message dở dang **không** tự được tiếp tục bằng continuation frame từ connection mới.

Đặc biệt, **mất kết nối giữa một fragmented message** nghĩa là message đó không hoàn tất; bỏ partial builder của connection cũ. Server phải replay **từ ranh giới application event/message có ID ổn định**, không cố nối raw frame mới vào fragment cũ.

## 18. Observability: đo được failure và data loss

Các chỉ số vận hành quan trọng:

| Metric | Vì sao cần |
| --- | --- |
| `websocket_active_connections` | Phát hiện số kết nối cao/connection leak |
| `ws_handshake_failures_by_reason` | Auth/TLS/upgrade/proxy problems |
| `reconnect_attempts` / `reconnect_delay_ms` | Reconnection storm, exponential backoff |
| `last_applied_seq` / `last_acked_seq` | Theo dõi tiến trình session |
| `replay_events_total` / `duplicates_ignored_total` | Chất lượng at-least-once recovery |
| `gap_detected_total` / `resync_required_total` | Phát hiện mất log hoặc không nhất quán |
| `message_bytes_in/out`, `oversize_rejections_total` | Điều chỉnh size cap và chống abuse |
| `fragment_count_per_message` | Phát hiện fragmentation abuse |
| `pending_outbound_bytes` / `worker_queue_depth` | Backpressure, RAM pressure |
| `ping_rtt_ms` / `last_pong_age_ms` | Phát hiện half-open và network latency |
| `application_ack_latency_ms` | Từ event/command đến xử lý bền vững |
| `session_recovery_duration_ms` | Thời gian từ handshake tới SYNCED |

Log có structure với `connectionGeneration`, `streamId`, `epoch`, event IDs và close/error classification; **không ghi resumeToken, Cookie/Authorization headers, payload cá nhân**. Đo tỉ lệ thành công reconnect riêng với tỉ lệ thành công **resume session**. Nếu reconnect liên tục nhưng session không đồng bộ, dashboard "connection up" là tín hiệu quá lạc quan.

Cần test **thời gian clock drift** giữa node nếu protocol dùng expiresAt; sequence/cursor không nên dựa vào đồng hồ client làm nguồn thứ tự duy nhất.

## 19. Ma trận test bắt buộc khi phát hành

| Test | Đầu vào/tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Message ngắn | 10 byte ASCII | Accept, parse đúng |
| Text UTF-8 nhiều byte | 70 × `é` = 140 UTF-8 byte, limit 128 | Reject theo byte quota |
| Fragmented text | Một message qua 2+ frames/callbacks | Chỉ parse khi last=true; đúng content |
| Fragmentation flood | Hàng nghìn fragment bé trong một message | Reject/timeout khi vượt ngân sách |
| Binary limit | Tổng `remaining()` vượt MAX | Không tích thêm, đóng/abort theo policy |
| Invalid UTF-8 | Malformed WebSocket text | WebSocket implementation từ chối theo protocol |
| Compression bomb | Tiny compressed input, huge decoded payload | Reject decoded-size quota |
| Server TCP reset | Mất kết nối không Close frame | Retry có backoff và reconnect một lần mỗi lỗi |
| Authentication error | Handshake 401/403, expired credential | Dừng hoặc refresh có policy; không vòng lặp vô hạn |
| Logout | User chủ động đóng | Không tự reconnect |
| Duplicate event | Replay #5 dù đã commit #5 | Không áp hai lần, ACK cursor |
| Missing event | Nhận #8 khi chờ #6 | Detect gap, snapshot/replay, không "bỏ qua" |
| Replay retention expired | Server chỉ còn #100, client ở #20 | RESYNC_REQUIRED, snapshot mới |
| ACK lost | Server gửi lại event đã commit | Dedup, idempotent state |
| Crash during processing | Đã đọc event nhưng chưa commit | Cursor không advance, replay xử lý lại an toàn |
| Side-effect command | Request ID X committed, ACK bị mất | Replay result/idempotency, không tạo side effect X lần hai |
| Session switching | Kết nối mới qua node khác | Shared event log/state, scope đúng |
| Proxy idle timeout | Lâu không có traffic | Ping/Pong/deadline, reconnect |
| Slow reader | Client không request callbacks đủ | Bounded queue và server backpressure |
| Slow writer | Send futures/backlog lớn | Bounded outbound queue, failure policy |
| Rapid retry | Hàng nghìn client reconnect đồng thời | Jitter/backoff, rate limit |
| Stale callback | Old WebSocket hoàn tất sau new generation | Generation guard, không ghi đè cursor mới |
| Resume token stolen | Token dùng từ user khác | Auth/scope reject, revoke token |

Test nên kết hợp **unit parser**, **integration test với WebSocket server chuẩn**, network fault injection (disconnect/reset/delay/duplicate/reorder), và load test có đo RAM/CPU/queue. Không chỉ test path bình thường.

## 20. Các sai lầm hay gặp

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Chỉ giới hạn frame, không giới hạn message | Fragmentation có thể cộng thành payload rất lớn | Cộng dồn toàn message |
| Dùng `String.length()` làm số byte | UTF-8 text vượt quota | Đếm UTF-8 bytes đúng, giữ bounded buffer |
| Ghép text rồi `getBytes()` không limit trước | Out-of-memory trước khi phát hiện quá lớn | Early char cap + final byte cap |
| Mỗi `onText` callback coi là một message | Mất/parse sai fragmented message | Tích tới `last==true` |
| Giữ partial message qua reconnect | Ghép dữ liệu của hai connection khác nhau | Bỏ partial khi mất socket, replay message |
| Gọi Java17 `sendClose(1009)` | API đánh dấu 1009 illegal | Dùng 1008 policy close/abort, phân biệt RFC 1009 |
| Chỉ dựa vào `request(1)` để chặn mọi bộ đệm | Bỏ qua queue/network/codec limits | Bounded processing + server max size |
| Reconnect ngay trong vòng lặp chặt | Reconnect storm | Backoff, jitter, retry budget |
| `onError` và `onClose` cùng schedule connect | Nhiều socket sống song song ngoài ý muốn | Guard scheduled-once/generation |
| Xem `onOpen` như trạng thái dữ liệu đã đồng bộ | Mất sự kiện trong gap offline | HELLO/RESUME/SNAPSHOT và SYNCED riêng |
| Lưu cursor khi mới nhận byte, chưa commit | Crash làm mất event thật | Advance cursor sau durable apply |
| Gửi lại non-idempotent command với ID mới | Side effect bị tạo hai lần | Stable idempotency key + server result store |
| Không có replay retention hoặc snapshot | Offline lâu không phục hồi được | RESYNC_REQUIRED + snapshot hợp lệ |
| Coi send future là business ACK | Mất khả năng xác định commit | Application-level ACK |
| Retry auth failed vô hạn | Quá tải và giữ session lỗi | Refresh/token policy, stop on terminal error |
| Nhét token nhạy cảm vào URL query | Rò log/proxy/browser history | Trusted header/auth channel, không log secret |
| Dùng `ws://` cho phiên thực ngoài loopback | Dữ liệu/session có thể bị nghe lén | `wss://`, TLS validation |
| Không giới hạn content sau giải nén | Decompression bomb | Limit decoded bytes/time |
| Dùng chỉ một sequence cho nhiều stream reset tùy ý | Dedup sai khi epoch thay đổi | streamId + epoch + seq |
| Tự làm WebSocket server raw cho production | Sai RFC/security/extended frames | Server framework có max limits và auth |

## 21. Bài tập tự kiểm tra

**Bài 1.** Một text message WebSocket dài 2 MiB được gửi thành 2.048 fragments 1 KiB. Chỉ kiểm tra từng `onText(...).data.length() <= 1024` có đủ không? Cần cộng giới hạn theo phạm vi nào?

**Bài 2.** `String message = "é".repeat(70)` và giới hạn 128 byte. `message.length()` là bao nhiêu? UTF-8 bytes là bao nhiêu? Nên reject không?

**Bài 3.** Server gửi một text message qua TEXT frame FIN=0 và CONTINUATION FIN=1. Client listener nên parse lúc nào, và `last` trong `onText` thể hiện điều gì?

**Bài 4.** Một Java 17 client muốn đóng khi nhận message quá lớn và gọi `sendClose(1009, "...")`. Tại sao sai dù RFC 6455 định nghĩa 1009? Cần dùng close policy nào với API này?

**Bài 5.** Client đã apply event #41 rồi mất mạng; server sinh #42, #43. Reconnect `onOpen` xong có được hiển thị "đồng bộ hoàn toàn" ngay chưa? Client cần trao đổi gì?

**Bài 6.** Sau reconnect, server gửi #41 lần nữa rồi #42. Client phải làm gì với #41? Nếu nhận #44 khi mới áp #41 thì sao?

**Bài 7.** Client gửi command chuyển tiền X; server commit nhưng ACK mất. Có nên gửi lại cùng thao tác với request ID mới? Làm sao tránh side effect hai lần?

**Bài 8.** Vì sao chỉ giữ `lastAppliedSeq` trong RAM không đủ cho ứng dụng phải đảm bảo không mất giao dịch khi JVM crash? Khi nào cập nhật cursor?

**Bài 9.** Khi kết nối chuyển từ Node A sang Node B, muốn replay event theo stream thì server cần có tài nguyên chia sẻ nào?

**Bài 10.** `WebSocket.sendText(...).join()` trả thành công. Có thể suy rằng server đã lưu giao dịch ứng dụng không? Cần loại ACK nào?

**Bài 11.** Server dùng compression, 100 KiB compressed bytes nở thành 15 MiB text. Giới hạn wire frame 2 MiB có đủ bảo vệ client đang giới hạn logical payload 1 MiB không?

**Bài 12.** Một WebSocket connection bị đóng bởi user logout, nhưng scheduler vẫn còn timer reconnect. Phải xử lý lifecycle thế nào?

### Đáp án gợi ý

1. Không. Giới hạn **tổng bytes toàn message**, cộng qua mọi fragment và cũng có byte/time budget.
2. 70 UTF-16 units, 140 UTF-8 bytes; phải reject khi max 128.
3. Parse khi message hoàn chỉnh, `last==true`; callback không bảo đảm trùng frame boundary.
4. JDK17 WebSocket.sendClose không cho caller gửi 1009; dùng code **1008** cho policy violation hoặc abort theo yêu cầu, có deadline close.
5. Chưa. HELLO/RESUME(lastAppliedSeq=41), server replay #42.., xác nhận synced rồi mới cập nhật UI.
6. #41 trùng phải ignore/dedup và ACK cursor; #44 tạo gap, phải yêu cầu replay #42/#43 hoặc snapshot, không advance bừa.
7. Không sinh ID mới. Dùng stable idempotencyKey, server lưu/tra kết quả theo key và transaction.
8. Vì crash mất cursor hoặc business commit không nhất quán. Lưu cursor/dedup cùng commit nghiệp vụ trước khi ACK.
9. Shared durable event log/DB, snapshot, replay retention, session/auth state; load-balancer affinity đơn thuần không đủ.
10. Không; send future chứng minh hành vi gửi theo WebSocket API, không phải server business commit. Cần application ACK.
11. Không. Phải giới hạn **decoded bytes** và compression ratio/CPU, không chỉ compressed frame size.
12. Đánh dấu terminal/closed, cancel timers/jobs, không để callback cũ reconnect; phân biệt user logout với transient failure.

## 22. Tài liệu tham khảo chính thức

- [Java SE 17 — WebSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html): `request(n)`, `sendText`, `sendBinary`, `sendPing`, `sendClose`/`abort`; đặc biệt danh sách close codes bị cấm trong Java API.
- [Java SE 17 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onText`, `onBinary`, `last`, `onClose`, `onError` và demand handling.
- [Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync`, `connectTimeout`, subprotocol và handshake headers.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): tạo WebSocket builder và xử lý HTTP client.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 byte counting.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `remaining()` và buffer ownership.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html): framing, fragmentation, masking, control frames, status codes 1000/1006/1008/1009.
- [RFC 7692 — Compression Extensions for WebSocket](https://www.rfc-editor.org/rfc/rfc7692.html): permessage-deflate và giới hạn decoded message.
