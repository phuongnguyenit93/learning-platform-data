# 16.9. Xử lý `BUFFER_UNDERFLOW`, `BUFFER_OVERFLOW`, đóng kết nối và tài nguyên bộ đệm

## Mục tiêu và bối cảnh

Trong **JSSE (Java Secure Socket Extension)**, `SSLEngine` cung cấp TLS/DTLS ở mức bộ đệm `ByteBuffer` thay vì tự sở hữu socket. Ứng dụng chịu trách nhiệm mang dữ liệu qua mạng, xử lý trạng thái bắt tay, cấp phát bộ đệm, điều phối non-blocking I/O và **đóng TLS đúng giao thức**. Đặc biệt, hai kết quả `SSLEngineResult.Status.BUFFER_UNDERFLOW` và `BUFFER_OVERFLOW` **không đơn giản là lỗi cần đóng kết nối**: chúng là tín hiệu điều phối dữ liệu và bộ nhớ.

Sau bài này, bạn có thể:

1. Phân biệt **network packet buffers** và **application plaintext buffers** cho cả hai hướng của `SSLEngine`.
2. Đọc bốn loại `Status` (`OK`, `BUFFER_UNDERFLOW`, `BUFFER_OVERFLOW`, `CLOSED`) cùng `HandshakeStatus`, `bytesConsumed` và `bytesProduced`.
3. Chữa `BUFFER_UNDERFLOW` bằng **giữ lại bytes chưa xử lý, đọc thêm dữ liệu**, chỉ tăng capacity khi cần đủ chứa TLS record; không làm mất mảnh packet.
4. Chữa `BUFFER_OVERFLOW` bằng **drain/flush hoặc tăng destination buffer** đúng cho `wrap` và `unwrap`; không lặp vô hạn với buffer không đổi.
5. Gửi và nhận `close_notify` bằng `closeOutbound`, `wrap`, `unwrap`, theo dõi `isInboundDone/isOutboundDone`; nhận biết EOF đột ngột khác đóng TLS hợp lệ.
6. Thiết kế giới hạn dung lượng, pooling, backpressure, cleanup, timeout và test lỗi cho một ứng dụng Java 17+ non-blocking.

Bài có **hai chương trình Java chạy độc lập**: một probe tạo `BUFFER_OVERFLOW`/`BUFFER_UNDERFLOW`, và một vòng lặp TLS 1.3 giữa hai `SSLEngine` trong RAM, có KeyStore/truststore thử nghiệm, truyền dữ liệu, trao đổi `close_notify` và kiểm tra trạng thái đóng. Ví dụ vòng lặp chỉ là **mô phỏng trong bộ nhớ**: khi triển khai `SocketChannel + Selector` thực tế cần bổ sung I/O scheduling, concurrency, timeouts, policy và quản lý tài nguyên như phần sau.

## 1. Vì sao `SSLEngine` cần bốn hướng bộ đệm?

Hãy hình dung một TLS connection:

```text
ỨNG DỤNG GỬI                                            ỨNG DỤNG NHẬN
plaintext ByteBuffer                                        plaintext
         |                                                       ^
         v                                                       |
     engine.wrap(src, networkOut)                    engine.unwrap(networkIn, dst)
         |                                                       ^
         v                                                       |
TLS record bytes (ciphertext/handshake)       TLS record bytes nhận từ mạng
         |                                                       ^
         +-------- SocketChannel / network ---------------------+
```

Mỗi bên thường tổ chức các buffer riêng:

| Bộ đệm logic | Chứa gì? | Chủ thể ghi | Bên tiêu thụ |
| --- | --- | --- | --- |
| `applicationOut` | Plaintext **chờ gửi** | Application | `engine.wrap(...)` |
| `networkOut` | TLS records **chờ ghi ra socket** | `engine.wrap(...)` | `SocketChannel.write(...)` |
| `networkIn` | TLS records **đã đọc từ socket** | `SocketChannel.read(...)` | `engine.unwrap(...)` |
| `applicationIn` | Plaintext **đã giải mã** | `engine.unwrap(...)` | Application |

Đây là **bốn vai trò**, không bắt buộc đúng bốn instance `ByteBuffer` trên đời. Một ứng dụng có thể có hàng đợi nhiều plaintext messages, nhiều network buffers hoặc memory pool. Điều bắt buộc là **không nhầm hướng, trạng thái `position/limit` và quyền sở hữu dữ liệu**.

Một TLS record có thể gồm handshake content, application content hoặc alert. Vì vậy **`wrap` không phải lúc nào cũng lấy plaintext để mã hóa**, và **`unwrap` không phải lúc nào cũng trả plaintext**. Trong handshake hoặc closure, `wrap(EMPTY, networkOut)` vẫn có thể sinh record điều khiển, và `unwrap` vẫn có thể tiêu thụ network bytes nhưng sinh **0 application bytes**.

`SSLEngine` không tự đọc/ghi socket; nếu bạn nhận được `BUFFER_UNDERFLOW` mà không bố trí đọc mạng, trạng thái sẽ không tự tiến triển. Nếu có `BUFFER_OVERFLOW` mà không giải phóng buffer đích, cứ gọi lại cùng tham số sẽ dẫn đến vòng lặp bận (busy spin).

## 2. `ByteBuffer` là state machine thứ hai

Để điều phối chính xác, luôn nhớ:

- `capacity()`: dung lượng vật lý đã cấp.
- `position()`: vị trí đọc/ghi hiện tại.
- `limit()`: ranh giới đọc/ghi.
- `remaining()`: số bytes có thể đọc/ghi theo mode hiện tại, bằng `limit - position`.
- `flip()`: chuyển từ **write mode → read mode**, đặt `limit=position` và `position=0`.
- `compact()`: sau khi đọc, dịch **các bytes còn chưa đọc** về đầu buffer, chuyển sang **write mode** để đọc thêm dữ liệu vào phần trống.
- `clear()`: chuyển sang write mode, **không xóa bytes vật lý** và **không giữ dữ liệu chưa đọc về mặt logic**.
- `slice()/duplicate()`: có thể chia sẻ backing memory; phải tách quyền sở hữu, tránh sửa cùng vùng dữ liệu khi `wrap/unwrap` đang dùng.

Ví dụ nhận hai mảnh của **cùng một TLS record**:

```text
networkIn đang WRITE MODE:
  [record bytes đầu...][chưa được nhận]  position=k

flip():
  [record bytes đầu...]  position=0, limit=k  READ MODE

engine.unwrap(networkIn, applicationIn) -> BUFFER_UNDERFLOW

compact():
  [bytes chưa đọc giữ lại][chỗ trống nhận tiếp]  WRITE MODE

socket.read(networkIn) -> nối thêm dữ liệu mới

flip() -> unwrap(...) lần nữa
```

**Không gọi `networkIn.clear()` sau `BUFFER_UNDERFLOW`**, vì nó có thể làm mất phần record chưa tiêu thụ. `compact()` giữ lại phần còn thiếu, là thao tác phù hợp trước khi đọc thêm. Nếu `unwrap` đã tiêu thụ một phần dữ liệu, `compact` chỉ giữ **phần còn lại**, không sao chép lại bytes đã được xử lý.

Ví dụ nhỏ để tự hình dung (`buffer` là write mode có `position=3`):

```java
buffer.flip();           // position=0, limit=3
// đọc 1 byte từ buffer ...
buffer.compact();        // giữ 2 byte chưa đọc, position=2, limit=capacity
// socket.read(buffer);  // điền thêm sau 2 byte đó
```

Đây là snippet minh họa, không phải chương trình độc lập; buffer/socket cần tạo và quản lý phù hợp.

## 3. Đọc `SSLEngineResult`: hai lớp trạng thái độc lập

`SSLEngine.wrap` và `SSLEngine.unwrap` trả `SSLEngineResult` với:

```java
result.getStatus();
result.getHandshakeStatus();
result.bytesConsumed();
result.bytesProduced();
```

**`getStatus()`** cho biết tình trạng thao tác I/O của engine. **`getHandshakeStatus()`** chỉ ra việc tiếp theo cần làm cho handshake TLS/DTLS. Hai trường đó **không thay thế** nhau: ví dụ `Status.OK` vẫn có thể đi kèm `HandshakeStatus.NEED_TASK` hoặc `NEED_WRAP`.

| `SSLEngineResult.Status` | Diễn giải | Hành động thường dùng |
| --- | --- | --- |
| `OK` | Thao tác không bị chặn bởi trạng thái lỗi/buffer | Xử lý bytes consumed/produced, mạng và `HandshakeStatus`; không giả định đã hoàn tất toàn bộ message |
| `BUFFER_UNDERFLOW` | `unwrap` thiếu TLS record bytes trong input network buffer | Giữ bytes chưa tiêu thụ, kiểm tra capacity rồi **đọc thêm từ peer** |
| `BUFFER_OVERFLOW` | Destination buffer quá nhỏ/không còn chỗ cho output | **`wrap`: networkOut**; **`unwrap`: applicationIn**. Flush/drain hoặc mở rộng đúng destination |
| `CLOSED` | Engine đã đóng phần liên quan hoặc thao tác kết thúc vì trạng thái đóng | Xử lý close_notify và half-close; phân biệt thành công và EOF bất thường |

Hai bộ đếm quan trọng:

- `bytesConsumed()` là số byte bị tiêu thụ trong **input buffers** của lời gọi đó.
- `bytesProduced()` là số byte được ghi vào **output buffers** của lời gọi đó.

**Không đồng nhất** số bytes plaintext với TLS network bytes; TLS thêm record headers, authentication tags và metadata. Một lần `unwrap` có thể **tiêu thụ TLS record** rồi produce 0 plaintext vì đó là message handshake/alert. Một lần `wrap` có thể produce record dù consume 0 application bytes.

Một cách đo progress đúng hơn là **có bytes consumed/produced, handshake state thay đổi, task hoàn thành hoặc socket chuyển dữ liệu**. Nếu không có tiến triển và đã thiếu input, hãy đợi I/O thay vì spin. Dù vậy, một số hành vi TLS/DTLS có thể chuyển internal state không phản ánh đơn giản bằng hai bộ đếm; cần triển khai theo contract của provider.

## 4. `BUFFER_UNDERFLOW`: thiếu dữ liệu nhận, không phải “packet sai”

Trong TCP, `SocketChannel.read` **không đảm bảo trả về một TLS record hoàn chỉnh**. Dữ liệu TLS có thể đến theo nhiều mảnh, hoặc nhiều record cùng trong một lần read. `SSLEngine.unwrap` cần đủ bytes để giải mã record cần xử lý; nếu không đủ, nó báo `BUFFER_UNDERFLOW`.

### Quy trình xử lý chuẩn

1. `networkIn` ban đầu là **write mode** chứa bytes đã đọc từ socket.
2. `networkIn.flip()` để engine đọc.
3. Gọi `SSLEngineResult r = engine.unwrap(networkIn, applicationIn)`.
4. Nếu `r.getStatus()==BUFFER_UNDERFLOW`, **đừng loại bỏ bytes còn lại**. Gọi `networkIn.compact()` để trở về write mode và giữ bytes chưa tiêu thụ.
5. Kiểm tra `networkIn.capacity()` có nhỏ hơn `engine.getSession().getPacketBufferSize()` không. Nếu nhỏ, tăng capacity **sau khi bảo toàn bytes**. Nếu capacity đã đủ, **không mở rộng vô điều kiện** chỉ vì underflow.
6. Đăng ký quan tâm `OP_READ`/đợi socket nhận thêm bytes; chỉ thử `unwrap` tiếp sau khi dữ liệu mới hoặc state TLS cho phép.
7. Nếu socket trả **-1 (EOF)**, xử lý như **đóng transport**, không đợi vĩnh viễn record không bao giờ đến và không chuyển unknown thành thành công.

Snippet xử lý một kết quả (`networkIn` được quản lý theo mô hình write mode ở ngoài lời gọi; `appIn` là write mode):

```java
networkIn.flip();
SSLEngineResult r = engine.unwrap(networkIn, appIn);
networkIn.compact(); // bảo toàn network bytes còn lại

if (r.getStatus() == SSLEngineResult.Status.BUFFER_UNDERFLOW) {
    int expected = engine.getSession().getPacketBufferSize();
    if (networkIn.capacity() < expected) {
        networkIn = growWriteModeBuffer(networkIn, expected);
    }
    // Chờ socket.read(networkIn) có thêm bytes, KHÔNG spin.
}
```

`growWriteModeBuffer(...)` là helper phải **copy bytes đang có trong write mode**, không phải lời gọi chuẩn JDK; ví dụ đầy đủ ở dưới có helper `grow(...)`. Vì `getPacketBufferSize()` có thể thay đổi theo session/handshake, đừng chỉ kiểm tra kích thước một lần lúc kết nối vừa tạo.

**Hai trường hợp rất dễ nhầm:**

- `BUFFER_UNDERFLOW` khi `networkIn.remaining()==0` ở read mode hoặc chỉ có header/fragment của record: **cần thêm bytes**.
- `BUFFER_OVERFLOW` trên `unwrap` vì `applicationIn` quá nhỏ: **không được giải bằng đọc thêm network bytes**. Cần xử lý output buffer.

**Đừng parse TLS record length để tự cấp phát tùy ý** dựa trên input chưa tin cậy. Hãy dùng `getPacketBufferSize` và giới hạn bộ nhớ cho mỗi kết nối, kiểm thử provider và đóng connection vi phạm chính sách.

## 5. `BUFFER_OVERFLOW`: thiếu chỗ cho output

### Trường hợp A — `wrap` overflow: `networkOut` quá nhỏ

`wrap(applicationOut, networkOut)` tạo TLS network bytes (record headers, ciphertext, tag, handshake/alert). Output không đủ chỗ khiến `BUFFER_OVERFLOW`. Không cố gắng ghi thêm ứng dụng vào `applicationOut` để giải quyết; nguồn không phải vấn đề.

Chọn một trong hai hướng:

1. Nếu `networkOut` đã chứa bytes từ các lần wrap trước, **flip và flush đến `SocketChannel`**. Nếu socket chỉ ghi một phần, giữ remainder ở read mode, đăng ký `OP_WRITE`, chờ socket writable rồi ghi nốt. Sau khi flush, `compact` trở lại write mode.
2. Nếu capacity thực sự nhỏ hơn packet cần sinh, tăng `networkOut` dựa trên `engine.getSession().getPacketBufferSize()` và upper bound của ứng dụng. **Bảo toàn bytes đã ghi nhưng chưa gửi**.

Snippet khái niệm:

```java
SSLEngineResult r = engine.wrap(applicationOut, networkOut);
if (r.getStatus() == SSLEngineResult.Status.BUFFER_OVERFLOW) {
    // Ưu tiên gửi TLS bytes đang có trong networkOut;
    // nếu vẫn thiếu: mở rộng destination phù hợp, không clear.
    int required = engine.getSession().getPacketBufferSize();
    networkOut = growWriteModeBuffer(networkOut, required);
    // Retry sau khi có chỗ thực sự.
}
```

Nếu output còn pending mà tăng buffer, helper phải giữ chính xác bytes chưa gửi, không gửi trùng/làm mất record. Trong mô hình event-loop, **đợi OP_WRITE khi socket không tiến triển**, không bận CPU bằng gọi `wrap` mãi.

### Trường hợp B — `unwrap` overflow: `applicationIn` quá nhỏ

`unwrap(networkIn, applicationIn)` giải mã TLS record ra plaintext. Khi plaintext không vừa destination, trả `BUFFER_OVERFLOW`. Khi đó:

1. Cho application **đọc/xử lý bytes đã có trong `applicationIn`**, sau đó `compact()/clear()` khi thực sự được phép.
2. Hoặc tăng `applicationIn` ít nhất theo `engine.getSession().getApplicationBufferSize()` và số bytes đang chứa.
3. Retry `unwrap` với đúng **network bytes chưa bị tiêu thụ**, không tự loại bỏ TLS bytes đang chờ.

Snippet:

```java
if (r.getStatus() == SSLEngineResult.Status.BUFFER_OVERFLOW) {
    int required = engine.getSession().getApplicationBufferSize();
    appIn = growWriteModeBuffer(appIn, required);
    // Sau đó gọi lại unwrap bằng network bytes chưa xử lý.
}
```

**Không bắt buộc cứ overflow là tăng bộ nhớ:** drain đến consumer có thể tốt hơn, đặc biệt khi ứng dụng giữ nhiều connection. Nếu consumer chậm, thực hiện **backpressure** và có giới hạn queue; không tăng buffer vô hạn để “xử lý hết”.

### Cách viết helper tăng buffer đúng mode

Giả định buffer hiện tại đang ở **write mode** và `position` là lượng bytes cần giữ:

```java
static ByteBuffer grow(ByteBuffer old, int minimum) {
    int capacity = Math.max(old.capacity() * 2, minimum);
    if (capacity > MAX_BUFFER_BYTES) {
        throw new IllegalStateException("Buffer cap exceeded");
    }
    ByteBuffer newer = ByteBuffer.allocate(capacity);
    old.flip();          // chuyển các bytes đã ghi sang read mode
    newer.put(old);      // copy đúng bytes đó
    return newer;        // write mode, position sau dữ liệu được giữ
}
```

`MAX_BUFFER_BYTES` là chính sách bạn tự đặt; helper **không phải API có sẵn**. Nếu buffer đang ở **read mode** với bytes chưa gửi, phải dùng cách **giữ `remaining()` rồi chuyển mode** phù hợp, không áp helper write-mode này nguyên xi. Ví dụ vòng lặp thứ hai có helper đầy đủ đúng giả định.

## 6. Kích thước `SSLSession`: packet khác application

Khi khởi tạo:

```java
SSLSession session = engine.getSession();

ByteBuffer networkIn =
        ByteBuffer.allocate(session.getPacketBufferSize());
ByteBuffer networkOut =
        ByteBuffer.allocate(session.getPacketBufferSize());
ByteBuffer applicationIn =
        ByteBuffer.allocate(session.getApplicationBufferSize());
```

Các số trả về là gợi ý/giới hạn từ session/provider cho việc chứa dữ liệu TLS và plaintext. Không coi chúng là kích thước message business (HTTP payload) hoặc là lượng RAM cố định bất biến suốt đời connection.

| Loại | Getter | Tình huống sử dụng |
| --- | --- | --- |
| TLS network packet buffer | `getPacketBufferSize()` | Đảm bảo network input có thể giữ record hoàn chỉnh và network output có thể chứa record do wrap tạo |
| Decrypted application buffer | `getApplicationBufferSize()` | Đảm bảo destination `unwrap` đủ chứa dữ liệu plaintext record |
| Application output/source | Không có số tối thiểu cứng cho kích thước business input | `wrap` có thể tiêu thụ một phần; dựa vào `bytesConsumed`/`hasRemaining` để gửi tiếp |

**Dữ liệu TLS không phải lúc nào cũng nở đúng một tỉ lệ cố định.** Overhead thay đổi theo TLS version, cipher suite, handshake hay application record. Đừng đoán `plaintext + 32`, hoặc hard-code `16 * 1024` làm capacity duy nhất. Hãy hỏi session và xử lý `SSLEngineResult` thực tế.

**Giới hạn bảo vệ tài nguyên:** ngay cả khi helper gợi ý tăng, ứng dụng vẫn cần giới hạn RAM và số connection; nếu vượt quota thì fail/close theo policy thay vì cấp phát vô hạn. Ví dụ bài học dùng cap minh họa **1 MiB cho mỗi buffer** — đây không phải con số tối ưu cho mọi ứng dụng. Thực tế đo handshake/certificate chains/record sizes và bounded concurrency.

## 7. Handshake status vẫn phải được xử lý sau khi buffer OK

`SSLEngineResult.HandshakeStatus` gồm:

| Trạng thái | Hành động ứng dụng |
| --- | --- |
| `NEED_WRAP` | Gọi `wrap` để sinh handshake/TLS control records, gửi hết network output |
| `NEED_UNWRAP` | Chờ TLS bytes từ peer và gọi `unwrap` |
| `NEED_TASK` | Lấy `engine.getDelegatedTask()` cho đến khi hết task; hoàn thành đúng cách trước khi tiến hành bước tiếp theo |
| `FINISHED` | Handshake **vừa** hoàn tất; chỉ xuất hiện trên kết quả `wrap/unwrap`, **không** phải từ `engine.getHandshakeStatus()` |
| `NOT_HANDSHAKING` | Không còn handshake đang diễn ra tại thời điểm kiểm tra; vẫn có thể có application data/closure để xử lý |
| `NEED_UNWRAP_AGAIN` | Yêu cầu gọi `unwrap` thêm mà không nhất thiết đọc thêm network data; Java 17 document mô tả trạng thái này cho **DTLS** để xử lý handshake data đã được buffer nội bộ |

Khi `NEED_TASK`, một số task (kiểm tra chứng chỉ, khóa, trust manager) có thể **block** dù `SSLEngine` I/O API hướng non-blocking. Trong real selector server, chạy task trong **bounded executor**/worker thích hợp thay vì giữ event-loop. Cẩn thận đồng bộ per-engine: không có nhiều thread cùng tự ý `wrap/unwrap`/thay ByteBuffer của một connection.

Một flow tổng quát:

```text
engine.getHandshakeStatus()
      |
      +-- NEED_TASK ------> lấy / thực thi delegated tasks ----+
      |                                                       |
      +-- NEED_WRAP ------> wrap(empty hoặc app bytes) --------+--> ghi networkOut
      |                                                       |
      +-- NEED_UNWRAP ----> có network input? ---- no: OP_READ |
      |                             | yes                      |
      |                             v                          |
      |                           unwrap                       |
      |                             |                          |
      +-- NEED_UNWRAP_AGAIN -------> unwrap (DTLS) ------------+
      |
      +-- FINISHED/NOT_HANDSHAKING --> application IO / close
```

Sau **mỗi `wrap/unwrap`**, xem cả `getStatus()` lẫn `getHandshakeStatus()`. Dù `OK`, engine vẫn có thể cần `NEED_TASK` hoặc `NEED_WRAP`. Và `FINISHED` không có nghĩa connection đã đóng; chỉ là handshake TLS vừa hoàn thành.

## 8. Dừng gửi dữ liệu không đồng nghĩa đóng TLS hoàn chỉnh

TLS có **closure alert `close_notify`**. Trên `SSLEngine`, quản lý **hai chiều độc lập**:

- `closeOutbound()` thông báo ứng dụng sẽ **không gửi plaintext mới**. Engine cần phát ra bản tin đóng qua `wrap(EMPTY, networkOut)`; ứng dụng phải **gửi toàn bộ TLS bytes** đó đến peer.
- `isOutboundDone()` cho biết engine đã hoàn tất xử lý phía outbound; **không đảm bảo socket đã truyền hết bytes trong `networkOut` hoặc kernel send queue**.
- Khi nhận `close_notify` của peer, gọi `unwrap(networkIn, applicationIn)` để engine xử lý; kết quả có thể là `Status.CLOSED` và `isInboundDone()==true`.
- Mỗi bên cần phát `close_notify` theo quy tắc TLS/protocol và policy ứng dụng. Với giao thức client/server phổ biến, bên chủ động đóng gửi trước, bên còn lại nhận rồi gửi close_notify của mình.
- Khi **cả hai hướng engine done** và toàn bộ network output đã flush, transport có thể đóng; thực tế cần xử lý half-close, outstanding app data, timeout và I/O errors.

```text
Client                                Server
------                                ------
stop application writes
closeOutbound()
wrap(EMPTY, networkOut)
          -- TLS close_notify -->   unwrap(...)
                                       isInboundDone == true
                                   closeOutbound()
                    <-- close_notify -- wrap(EMPTY, networkOut)
unwrap(...)
isInboundDone == true
Both outboundDone/inboundDone when fully processed
Close channels after pending network bytes are flushed
```

**Không được** gọi `SocketChannel.close()` ngay sau `engine.closeOutbound()` khi `networkOut` chưa gửi: peer có thể thấy EOF mà không có close_notify, mất tín hiệu kết thúc TLS hợp lệ.

### EOF đột ngột, `closeInbound()` và truncation

Nếu `SocketChannel.read() == -1` mà **chưa** nhận được close_notify:

- Đây là tình huống **truncated TLS stream / peer transport closed unexpectedly** (hoặc policy/protocol không thực hiện đóng đúng).
- `engine.closeInbound()` thông báo không còn incoming TLS bytes. Theo Java Javadoc, nó **có thể ném `SSLException` khi peer chưa phát proper closure message** — **không được nuốt lỗi rồi coi kết nối đóng sạch**.
- Có thể vẫn cần `closeOutbound()` để giải phóng trạng thái của engine theo policy, nhưng không được báo rằng peer đã hoàn thành TLS closure.
- Đối với dữ liệu nhạy cảm, thiết kế application-level framing và xác nhận completeness (ví dụ content length/expected message count) để không dùng dữ liệu bị cắt như kết quả đầy đủ. `close_notify` không thay thế ý nghĩa “business transaction đã commit thành công”.

Snippet mang tính minh họa:

```java
if (endOfStream) {
    try {
        engine.closeInbound();
    } catch (SSLException truncated) {
        // Peer không đóng TLS đúng; ghi nhận và từ chối dùng dữ liệu chưa hoàn chỉnh.
        throw truncated;
    } finally {
        engine.closeOutbound(); // cho phép cleanup phía gửi theo state machine
    }
}
```

`endOfStream` và `engine` là biến application đã định nghĩa; đoạn này **không** thay thế bước flush mạng, retry/backpressure/cleanup. Không gọi `closeInbound()` sớm chỉ để “ép” handshake/unwrap hoàn thành.

**TLS 1.3 lưu ý:** `close_notify` và chính sách half-close cần được phối hợp với application protocol. Bên nhận close_notify có thể vẫn có outbound data theo trạng thái và policy cụ thể, nhưng ứng dụng cần xác định rõ lúc nào ngừng gửi và không treo chờ. `SSLEngine` đã đóng **không tái sử dụng** cho connection mới.

## 9. Ví dụ Java đầu tiên: chủ động tạo OVERFLOW và UNDERFLOW

`EngineStatusProbe.java` chạy **không cần server thực, certificate hay socket**: tạo hai `SSLEngine` mới bằng default `SSLContext` để quan sát trạng thái. Client cần tạo TLS ClientHello nhưng buffer ghi ra mạng chỉ có **1 byte**, làm `wrap` trả `BUFFER_OVERFLOW`. Server mới bắt đầu handshake và chưa nhận byte nào, nên `unwrap` trả `BUFFER_UNDERFLOW`.

```java
import java.nio.ByteBuffer;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLSession;

public final class EngineStatusProbe {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();

        SSLEngine client = context.createSSLEngine("localhost", 443);
        client.setUseClientMode(true);
        client.beginHandshake();
        SSLSession session = client.getSession();

        SSLEngineResult overflow =
                client.wrap(ByteBuffer.allocate(0), ByteBuffer.allocate(1));

        SSLEngine server = context.createSSLEngine();
        server.setUseClientMode(false);
        server.beginHandshake();
        SSLEngineResult underflow =
                server.unwrap(ByteBuffer.allocate(0),
                        ByteBuffer.allocate(session.getApplicationBufferSize()));

        System.out.println("wrapStatus=" + overflow.getStatus());
        System.out.println("unwrapStatus=" + underflow.getStatus());
        System.out.println("wrapConsumed=" + overflow.bytesConsumed());
        System.out.println("unwrapProduced=" + underflow.bytesProduced());

        client.closeOutbound();
        server.closeOutbound();
    }
}
```

```bash
javac -encoding UTF-8 EngineStatusProbe.java
java EngineStatusProbe
```

**Stdout đã xác minh trên JDK thử nghiệm:**

```text
wrapStatus=BUFFER_OVERFLOW
unwrapStatus=BUFFER_UNDERFLOW
wrapConsumed=0
unwrapProduced=0
```

Giải thích:

- `wrapStatus=BUFFER_OVERFLOW` do **destination network output không đủ**, không có nghĩa certificate sai. Vì input là empty và đang handshake, engine chỉ đang cố tạo record điều khiển.
- `unwrapStatus=BUFFER_UNDERFLOW` do network input có **0 byte**, không có record nào để parse.
- `wrapConsumed=0` và `unwrapProduced=0` là hợp lý trong hai lời gọi này.
- Ví dụ **không hoàn tất handshake** và không mở socket. Hai lệnh `closeOutbound()` chỉ đánh dấu không gửi thêm; **không** được coi là trao đổi close_notify thành công.

Output chi tiết có thể khác nếu provider/JSSE version có hành vi đặc biệt; điều chính yếu là cách `Status` cung cấp hướng xử lý. Khi làm việc với provider thực tế, luôn xử lý `Status` thay vì giả định một lời gọi sẽ thành công.

## 10. Ví dụ Java thứ hai: hai `SSLEngine` TLS 1.3 chạy trong RAM

Ví dụ này thể hiện sự phối hợp đầy đủ:

- Một **server `SSLEngine`** với `PrivateKeyEntry` và self-signed certificate **lab** trong `server.p12`.
- Một **client `SSLEngine`** với `trust.p12` chỉ tin certificate lab được tạo. Ví dụ **không dùng `TrustManager` chấp nhận tất cả**.
- `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` để client kiểm tra `localhost` theo SAN. Việc tạo `SSLEngine("localhost",443)` **không tự đảm bảo** hostname được verify nếu không bật endpoint identification.
- Bắt tay **TLSv1.3**, trao đổi TLS records giữa hai ByteBuffer trong RAM, giải mã chuỗi `tls-data`.
- Client gửi `close_notify`, server nhận rồi gửi `close_notify`, client nhận; kiểm tra cả bốn trạng thái inbound/outbound hoàn tất.
- Xử lý `NEED_TASK`, `NEED_WRAP`, `NEED_UNWRAP`; giải quyết overflow bằng `grow` và underflow bằng đợi thêm bytes mà không làm mất dữ liệu.

**Ranh giới ví dụ:** helper `send` mô phỏng việc copy toàn bộ network output vào peer ngay trong RAM, **không** thay thế `SocketChannel.write` vốn có thể partial write. Task được chạy inline để test đơn luồng; production cần task executor, event-loop scheduling, fairness, cancellation và timeout. Cap **1 MiB** chỉ minh họa giới hạn bộ nhớ.

### 10.1. Tạo bộ certificate chỉ trong thư mục lab

Dùng một thư mục mới. Trên Bash, tạo biến password **chỉ dùng cho lab**:

```bash
mkdir jsse-engine-lab
cd jsse-engine-lab
read -r -s -p "Lab password: " LAB_PASS
echo
export LAB_PASS
```

Trên PowerShell, nếu dùng biến môi trường hãy **nhập password lab riêng**, không dùng credential production; ví dụ nhập tương tác qua cơ chế bảo mật phù hợp của môi trường. Cả `keytool -storepass:env` lẫn Java demo sẽ đọc biến `LAB_PASS`. Biến môi trường có thể bị đọc bởi process/diagnostic trong một số tình huống; **không coi `:env` là secret manager**.

Sau khi đã có `LAB_PASS` và ở trong thư mục lab, tạo server key pair/cert, xuất cert và đưa vào truststore lab:

```bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 1 -dname "CN=localhost" -ext "SAN=dns:localhost" -ext "EKU=serverAuth" -storetype PKCS12 -keystore server.p12 -storepass:env LAB_PASS -keypass:env LAB_PASS

keytool -exportcert -alias server -rfc -file server.pem -keystore server.p12 -storetype PKCS12 -storepass:env LAB_PASS

# Chỉ cho lab tự tạo: tin cert vừa được tạo và đã tự xác minh nguồn!
keytool -importcert -alias server -file server.pem -keystore trust.p12 -storetype PKCS12 -storepass:env LAB_PASS -noprompt
```

`-noprompt` ở đây **chỉ dùng với certificate do chính lab vừa tạo**; không dùng để âm thầm tin chứng chỉ của người lạ. Tệp `server.p12` **chứa private key**, cần bảo vệ/xóa sau lab; `server.pem` chứa certificate public. Certificate có SAN `localhost` để endpoint identification của client có thể thành công; không thực hiện public DNS/TLS call nào trong demo RAM.

### 10.2. Chương trình chạy đầy đủ: `EngineLoopbackDemo.java`

```java
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import javax.net.ssl.*;

public final class EngineLoopbackDemo {
    private static final ByteBuffer EMPTY = ByteBuffer.allocate(0);
    private static final int LIMIT = 1024 * 1024;

    private static final class Side {
        final SSLEngine engine;
        ByteBuffer networkIn;
        ByteBuffer networkOut;
        ByteBuffer applicationIn;
        Side peer;

        Side(SSLEngine engine) {
            this.engine = engine;
            SSLSession session = engine.getSession();
            networkIn = ByteBuffer.allocate(session.getPacketBufferSize());
            networkOut = ByteBuffer.allocate(session.getPacketBufferSize());
            applicationIn = ByteBuffer.allocate(
                    session.getApplicationBufferSize());
        }
    }

    // Đầu vào phải đang ở WRITE MODE, giữ những bytes hiện có.
    private static ByteBuffer grow(ByteBuffer writeMode, int wanted) {
        int capacity = Math.max(writeMode.capacity() * 2, wanted);
        if (capacity > LIMIT) {
            throw new IllegalStateException("Buffer cap exceeded");
        }
        ByteBuffer larger = ByteBuffer.allocate(capacity);
        writeMode.flip();
        larger.put(writeMode);
        return larger;
    }

    // Trong lab, copy nguyên TLS bytes sang buffer nhận của peer.
    private static boolean send(Side side) {
        if (side.networkOut.position() == 0) return false;
        side.networkOut.flip();
        int needed = side.peer.networkIn.position() +
                side.networkOut.remaining();
        if (side.peer.networkIn.remaining() <
                side.networkOut.remaining()) {
            side.peer.networkIn = grow(side.peer.networkIn, needed);
        }
        side.peer.networkIn.put(side.networkOut);
        side.networkOut.clear();
        return true;
    }

    private static boolean handshakeStep(Side s) throws Exception {
        SSLEngineResult.HandshakeStatus before =
                s.engine.getHandshakeStatus();
        switch (before) {
            case NEED_TASK -> {
                Runnable task;
                while ((task = s.engine.getDelegatedTask()) != null) {
                    task.run();
                }
                return true;
            }
            case NEED_WRAP -> {
                SSLEngineResult result =
                        s.engine.wrap(EMPTY.duplicate(), s.networkOut);
                if (result.getStatus() ==
                        SSLEngineResult.Status.BUFFER_OVERFLOW) {
                    s.networkOut = grow(s.networkOut,
                            s.engine.getSession().getPacketBufferSize());
                    return true;
                }
                if (result.getStatus() != SSLEngineResult.Status.OK) {
                    throw new SSLException(
                            "Unexpected handshake wrap: " + result);
                }
                boolean sent = send(s);
                return sent || result.getHandshakeStatus() != before;
            }
            case NEED_UNWRAP, NEED_UNWRAP_AGAIN -> {
                if (before ==
                        SSLEngineResult.HandshakeStatus.NEED_UNWRAP &&
                        s.networkIn.position() == 0) {
                    return false;
                }
                s.networkIn.flip();
                SSLEngineResult result =
                        s.engine.unwrap(s.networkIn, s.applicationIn);
                s.networkIn.compact();

                if (result.getStatus() ==
                        SSLEngineResult.Status.BUFFER_UNDERFLOW) {
                    if (s.networkIn.capacity() <
                            s.engine.getSession().getPacketBufferSize()) {
                        s.networkIn = grow(s.networkIn,
                                s.engine.getSession().getPacketBufferSize());
                        return true;
                    }
                    return false; // Đợi thêm TLS bytes của peer.
                }
                if (result.getStatus() ==
                        SSLEngineResult.Status.BUFFER_OVERFLOW) {
                    s.applicationIn = grow(s.applicationIn,
                            s.engine.getSession().getApplicationBufferSize());
                    return true;
                }
                if (result.getStatus() != SSLEngineResult.Status.OK) {
                    throw new SSLException(
                            "Unexpected handshake unwrap: " + result);
                }
                return result.bytesConsumed() > 0 ||
                        result.bytesProduced() > 0 ||
                        result.getHandshakeStatus() != before;
            }
            case NOT_HANDSHAKING, FINISHED -> {
                return false;
            }
        }
        return false;
    }

    private static void handshake(Side client, Side server)
            throws Exception {
        client.engine.beginHandshake();
        server.engine.beginHandshake();
        for (int i = 0; i < 500; i++) {
            boolean a = handshakeStep(client);
            boolean b = handshakeStep(server);
            boolean done =
                    client.engine.getHandshakeStatus() ==
                            SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING &&
                    server.engine.getHandshakeStatus() ==
                            SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING;
            if (done) return;
            if (!a && !b) {
                throw new SSLException("Handshake stalled");
            }
        }
        throw new SSLException("Handshake loop limit");
    }

    private static void deliverAndUnwrap(Side receiver)
            throws Exception {
        int attempts = 0;
        while (receiver.networkIn.position() > 0 && attempts++ < 100) {
            receiver.networkIn.flip();
            SSLEngineResult r = receiver.engine.unwrap(
                    receiver.networkIn, receiver.applicationIn);
            receiver.networkIn.compact();
            if (r.getStatus() ==
                    SSLEngineResult.Status.BUFFER_OVERFLOW) {
                receiver.applicationIn = grow(receiver.applicationIn,
                        receiver.engine.getSession().getApplicationBufferSize());
            } else if (r.getStatus() ==
                    SSLEngineResult.Status.BUFFER_UNDERFLOW) {
                if (receiver.networkIn.capacity() <
                        receiver.engine.getSession().getPacketBufferSize()) {
                    receiver.networkIn = grow(receiver.networkIn,
                            receiver.engine.getSession().getPacketBufferSize());
                }
                return;
            } else if (r.getStatus() ==
                    SSLEngineResult.Status.CLOSED) {
                return;
            } else if (r.getStatus() != SSLEngineResult.Status.OK) {
                throw new SSLException("Unexpected data unwrap: " + r);
            }
        }
    }

    private static void write(Side sender, Side receiver,
            byte[] plaintext) throws Exception {
        ByteBuffer input = ByteBuffer.wrap(plaintext);
        int attempts = 0;
        while (input.hasRemaining() && attempts++ < 100) {
            SSLEngineResult r =
                    sender.engine.wrap(input, sender.networkOut);
            if (r.getStatus() ==
                    SSLEngineResult.Status.BUFFER_OVERFLOW) {
                sender.networkOut = grow(sender.networkOut,
                        sender.engine.getSession().getPacketBufferSize());
                continue;
            }
            if (r.getStatus() != SSLEngineResult.Status.OK) {
                throw new SSLException("Unexpected data wrap: " + r);
            }
            send(sender);
            deliverAndUnwrap(receiver);
        }
        if (input.hasRemaining()) {
            throw new SSLException("Data loop limit");
        }
    }

    private static void close(Side sender, Side receiver)
            throws Exception {
        sender.engine.closeOutbound();
        for (int i = 0; !sender.engine.isOutboundDone() && i < 100; i++) {
            SSLEngineResult r = sender.engine.wrap(
                    EMPTY.duplicate(), sender.networkOut);
            if (r.getStatus() ==
                    SSLEngineResult.Status.BUFFER_OVERFLOW) {
                sender.networkOut = grow(sender.networkOut,
                        sender.engine.getSession().getPacketBufferSize());
                continue;
            }
            if (r.getStatus() != SSLEngineResult.Status.CLOSED &&
                    r.getStatus() != SSLEngineResult.Status.OK) {
                throw new SSLException("Close wrap failed: " + r);
            }
            send(sender);
        }
        if (!sender.engine.isOutboundDone()) {
            throw new SSLException("Close stalled");
        }
        deliverAndUnwrap(receiver);
    }

    private static SSLContext context(Path store, char[] pass,
            boolean useIdentity) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(store)) {
            ks.load(in, pass);
        }
        if (useIdentity) {
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(ks, pass);
            SSLContext ssl = SSLContext.getInstance("TLS");
            ssl.init(kmf.getKeyManagers(), null, null);
            return ssl;
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(ks);
        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), null);
        return ssl;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java EngineLoopbackDemo server.p12 trust.p12");
        }
        String fromEnv = System.getenv("LAB_PASS");
        if (fromEnv == null || fromEnv.length() < 6) {
            throw new IllegalArgumentException("LAB_PASS is required");
        }
        char[] pass = fromEnv.toCharArray();
        try {
            SSLEngine a = context(Path.of(args[1]), pass, false)
                    .createSSLEngine("localhost", 443);
            a.setUseClientMode(true);
            a.setEnabledProtocols(new String[]{"TLSv1.3"});
            SSLParameters cp = a.getSSLParameters();
            cp.setEndpointIdentificationAlgorithm("HTTPS");
            a.setSSLParameters(cp);

            SSLEngine b = context(Path.of(args[0]), pass, true)
                    .createSSLEngine();
            b.setUseClientMode(false);
            b.setEnabledProtocols(new String[]{"TLSv1.3"});

            Side client = new Side(a), server = new Side(b);
            client.peer = server;
            server.peer = client;

            handshake(client, server);
            byte[] msg = "tls-data".getBytes(StandardCharsets.UTF_8);
            write(client, server, msg);
            server.applicationIn.flip();
            byte[] received =
                    new byte[server.applicationIn.remaining()];
            server.applicationIn.get(received);

            close(client, server);
            close(server, client);

            System.out.println("handshakeProtocol=" +
                    a.getSession().getProtocol());
            System.out.println("messageRecovered=" +
                    Arrays.equals(msg, received));
            System.out.println("clientInboundDone=" + a.isInboundDone());
            System.out.println("serverInboundDone=" + b.isInboundDone());
            System.out.println("clientOutboundDone=" +
                    a.isOutboundDone());
            System.out.println("serverOutboundDone=" +
                    b.isOutboundDone());
        } finally {
            Arrays.fill(pass, '\0');
        }
    }
}
```

### 10.3. Biên dịch, chạy và kiểm tra output

Sau khi tạo `server.p12`/`trust.p12` và set biến `LAB_PASS` đúng như phần trên:

```bash
javac -encoding UTF-8 EngineLoopbackDemo.java
java EngineLoopbackDemo server.p12 trust.p12
```

**Stdout mong đợi trên JDK 17+ có TLS 1.3/KeyStore provider tương thích:**

```text
handshakeProtocol=TLSv1.3
messageRecovered=true
clientInboundDone=true
serverInboundDone=true
clientOutboundDone=true
serverOutboundDone=true
```

Vì private/public key và TLS session được sinh ngẫu nhiên, **không** dựa vào việc TLS record bytes giống nhau qua các lần chạy. Đầu ra trên là trạng thái logic, không hiển thị secrets.

**Đọc code theo trình tự:**

1. `context(...,true)` tải KeyStore chứa private key của server qua `KeyManagerFactory`; `context(...,false)` tải truststore chứa certificate lab qua `TrustManagerFactory`. Client kiểm tra chứng chỉ server bằng truststore, không dùng trust-all; `HTTPS endpoint identification` kiểm tra tên `localhost`.
2. `Side` cấp `networkIn`/`networkOut` theo `getPacketBufferSize()` và `applicationIn` theo `getApplicationBufferSize()`. Chúng bắt đầu ở **write mode**, giúp `send` và `unwrap` xử lý nhất quán.
3. `handshakeStep` chạy `NEED_TASK`, `NEED_WRAP` và `NEED_UNWRAP`. Với `BUFFER_OVERFLOW`, mở rộng **đích** thích hợp; với `BUFFER_UNDERFLOW`, `compact` giữ bytes và chờ peer có thêm network data. Branch `NEED_UNWRAP_AGAIN` để biết trạng thái API, vốn chủ yếu dùng với DTLS.
4. `send` mô phỏng `write/network transport` bằng copy TLS bytes từ `networkOut` sang `networkIn` của peer. Trong lab, peer có thể nhận hết bytes ngay. **Socket thật có partial writes/reads**, nên không được đem `send` thay nguyên hàm I/O mạng.
5. `write` đưa `tls-data` qua `client.wrap`; server gọi `unwrap` để khôi phục plaintext. Mọi bước cần kiểm tra `Status` và không trả về plaintext chưa được bảo vệ/xác minh theo TLS.
6. `close(client,server)` gọi `closeOutbound`, sinh close_notify qua `wrap(EMPTY)` và đưa sang server `unwrap`. Sau đó server làm tương tự về client.
7. `isInboundDone/isOutboundDone` kiểm tra trạng thái engine sau khi **đã nhận/gửi close_notify trong mô phỏng**. Trên socket thật còn phải đảm bảo kernel đã gửi hết bytes trước khi đóng transport.
8. `grow` đặt giới hạn một buffer để ngăn bộ nhớ nở vô hạn; production cần buffer pools, per-connection budget và chiến lược xử lý nếu vượt giới hạn.
9. `LAB_PASS` được đọc từ environment chỉ để thao tác lab, không xuất raw private key. `Arrays.fill(pass, '\0')` giảm thời gian giữ bản char[]; biến environment/String khác vẫn cần quản trị bằng secret manager/ACL theo policy.

**Quan trọng:** chương trình là fixture chứng minh luồng cơ bản **cho một message nhỏ** trên TLS 1.3 trong RAM, không phải implementation NIO server sẵn sàng production. Nó không triển khai socket fairness, partial writes, nhiều request concurrent, memory pressure, cancellation, application framing, shutdown timeout, TLS renegotiation/DTLS retransmission hoặc mọi trường hợp provider-specific handshake. Các phần tiếp theo chỉ rõ những việc cần bổ sung.

Khi học xong, xóa riêng các tệp chứa **private key lab** và biến environment trong phiên shell, ví dụ `unset LAB_PASS` trên Bash. Không copy chứng chỉ tự ký lab vào truststore hệ thống/production. Nếu muốn kiểm thử TLS 1.2, cần thay protocol ở cả hai engine, thử lại đầy đủ chứ không giả định behavior close/handshake y hệt.

## 11. Từ mô phỏng RAM sang `SocketChannel + Selector`

Trong một Java NIO server thực tế, network buffers cần quản lý **các thao tác bất đồng bộ và partial I/O**.

### Luồng đọc

```text
OP_READ fired
    |
    v
readBytes = channel.read(networkIn in WRITE mode)
    |
    +-- >0 --> networkIn.flip()
    |          engine.unwrap(networkIn, applicationIn)
    |          networkIn.compact()
    |                |
    |                +-- OK: xử lý result, handshake và plaintext
    |                +-- UNDERFLOW: giữ remainder, đợi OP_READ hoặc tăng capacity cần thiết
    |                +-- OVERFLOW: drain/grow applicationIn, retry
    |                +-- CLOSED: xử lý inbound close_notify, lên lịch outbound close
    |
    +-- =0 --> chờ sự kiện kế tiếp, KHÔNG spin
    |
    +-- -1 --> peer transport EOF; kiểm tra close_notify / closeInbound
```

**Đọc đủ trước khi unwrap** không có nghĩa đợi `networkIn` đầy; một buffer có thể chứa một record hoàn chỉnh khi mới dùng vài trăm bytes. Thử `unwrap` với bytes đang có rồi quyết định dựa trên status. Khi có nhiều TLS records trong `networkIn`, tiếp tục xử lý đến khi dưới ngưỡng, thiếu input, output đầy hoặc fairness budget hết.

### Luồng ghi

```text
Có app bytes hoặc engine NEED_WRAP/CLOSING
    |
    v
engine.wrap(applicationOut, networkOut in WRITE mode)
    |
    +-- BUFFER_OVERFLOW --> flush networkOut hoặc grow networkOut
    +-- OK/CLOSED -------> networkOut.flip()
                           channel.write(networkOut)
                                |
                                +-- partial write --> giữ remainder,
                                |                    chờ OP_WRITE
                                |
                                +-- all sent -------> networkOut.compact()
                                |                    (hoặc clear khi hết bytes)
                                |
                                +-- exception ------> close/error policy
```

Nếu `channel.write(...)` ghi 0 bytes, **đừng** gọi lại trong vòng lặp bận. Đăng ký `OP_WRITE`, tiếp tục khi socket có khả năng nhận; trong nhiều selector implementation, để `OP_WRITE` luôn bật gây wakeup liên tục, nên tắt khi không có output pending.

**Bảo vệ dữ liệu khi write một phần:**

```java
networkOut.flip();
channel.write(networkOut);
networkOut.compact(); // giữ bytes chưa được channel tiêu thụ
```

Đây là snippet ngắn dùng khi `networkOut` ban đầu ở **write mode**. Nếu channel ghi hết, `compact()` trở lại write mode position=0; nếu ghi một phần, `compact()` giữ TLS bytes còn lại để lần `OP_WRITE` sau. Không gọi `clear()` sau partial write.

### Khi vừa có pending output vừa có handshake NEED_UNWRAP

Có thể phải **gửi xong bytes đã sinh** trước khi peer phản hồi handshake, nhưng vẫn cần đọc các bytes inbound đến và chạy tasks. Hãy thiết kế state machine mà mỗi connection có bounded work per event, queue/app-IO riêng, và logic phân bổ `OP_READ/OP_WRITE` theo trạng thái. Đừng giữ lock toàn hệ thống trong khi chạy trust manager hoặc network I/O.

## 12. Đóng kết nối theo trạng thái và bảo đảm cleanup

Một thiết kế production nên có các phase rõ ràng, không dùng `boolean closed` chung cho mọi nghĩa:

| Phase | Công việc cần hoàn thành |
| --- | --- |
| `OPEN` | Cho phép app writes, wrap/unwrap bình thường |
| `DRAIN_APP` | Ngừng nhận thêm app messages mới, đưa các messages đã chấp nhận vào TLS records theo policy |
| `SEND_CLOSE_NOTIFY` | `closeOutbound`, tiếp tục `wrap(EMPTY)` khi cần, flush toàn bộ TLS outbound bytes |
| `WAIT_PEER_CLOSE` | Chờ `unwrap` xử lý close_notify của peer, có deadline; không đợi vô hạn |
| `TRANSPORT_CLOSE` | Khi đạt policy hoặc đã xác định error, ngừng selector interest, hủy task/queue, đóng socket |
| `RELEASE` | Trả pooled buffers, giải phóng connection state, metrics, không tái dùng engine đã đóng |

Không nhất thiết mọi ứng dụng phải đợi vô hạn “đối phương close_notify trước”: đặt **shutdown timeout**. Nếu timeout và transport phải đóng, ghi nhận rằng connection **không đóng TLS hoàn chỉnh**, không biến forced close thành success về mặt bảo mật.

Với connection đột ngột bị reset, I/O exception hoặc EOF thiếu close_notify, cần đánh dấu **truncation/unclean close**. Nếu ứng dụng chỉ xử lý message đã đầy đủ và có framing/authentication riêng, có thể có chính sách riêng cho việc giữ các message đã commit; điều đó **khác** với tuyên bố TLS connection hoàn tất cleanly.

**Không để pool tái sử dụng `SSLEngine` đã đóng**, đặc biệt khi key/session state thay đổi. `SSLSession` có thể được cache/resumed trong JSSE theo cơ chế TLS khác, nhưng đây **không** phải tái sử dụng chính object `SSLEngine` cho nhiều peer.

### `closeInbound()` có phải luôn được gọi?

Không. Khi peer gửi close_notify được `unwrap` xử lý, `isInboundDone()` trở thành true theo engine; gọi `closeInbound` **để giả vờ đã nhận close_notify** là sai. Chỉ khi transport kết thúc mà engine chưa nhận closure, dùng `closeInbound` để báo inbound không còn dữ liệu, và **xử lý `SSLException` nếu có**. Đừng “dập lỗi” từ closure alert bằng `try/catch(Exception ignored)`.

### Tài nguyên bộ đệm sau khi close

- Java heap `ByteBuffer.allocate` không cần `free()`; không giữ reference để GC thu hồi khi không còn owner.
- Direct buffers `ByteBuffer.allocateDirect` nằm ngoài heap managed memory, việc giải phóng thực tế do JVM/cleaner và provider quản lý; tránh gọi API nội bộ/`sun.misc.Unsafe` để ép unmap/free không kiểm soát.
- Nếu dùng **buffer pool**, **trả buffer chính xác một lần** sau khi không còn `wrap/unwrap`/socket write/task sử dụng nó. Không đưa buffer vào pool khi `networkOut` vẫn còn bytes chưa gửi hoặc `networkIn` còn mảnh TLS record.
- Plaintext `applicationIn/applicationOut` có thể chứa nội dung nhạy cảm. `clear()` và `compact()` chỉ đổi metadata, **không xóa dữ liệu cũ**; khi cần zeroization, chủ động overwrite nội dung có kiểm soát trước khi tái sử dụng, nhận thức giới hạn JVM copies/GC.
- Tránh giữ `ByteBuffer.slice()`/`duplicate()` sau khi owner đã trả backing buffer vào pool; có thể tạo data race hoặc lộ plaintext giữa kết nối.

## 13. Capacity planning, pooling và backpressure

Một connection có thể chiếm nhiều buffer với capacity vài chục KiB hoặc cao hơn. Khi có hàng nghìn connection, việc cấp phát dự phòng quá lớn gây áp lực heap/direct memory/GC. Ngược lại buffer quá nhỏ dẫn đến overflow/underflow lặp lại, copy và allocation.

### Quy tắc thiết kế

1. **Lấy size theo `SSLSession`**, nhưng đừng coi session getter là một allocation bắt buộc cho tất cả buffer cùng lúc. Có thể cấp phát lazy, pool theo size classes, tùy tải.
2. Đặt **trần bytes per connection**, trần global direct memory/heap, số handshake đồng thời và số delegated tasks. Không vì một peer gửi dữ liệu sai mà tăng buffer vô hạn.
3. Không cộng dồn app messages chưa tiêu thụ: nếu application consumer chậm, **dừng đọc/giảm OP_READ** trong phạm vi hợp lý, có backpressure vào nguồn và giới hạn queue.
4. **Pool** network buffers theo kiểu direct nếu đo thực tế có lợi cho socket I/O; heap buffers có thể rẻ hơn cho logic business/plaintext. Không mặc định direct luôn nhanh nhất.
5. Đặt buffer ownership rõ ràng, không chia sẻ writable buffer giữa hai `SSLEngine` cùng lúc, kể cả khi muốn tiết kiệm memory.
6. Chỉ tăng buffer khi có bằng chứng cần thiết: `BUFFER_UNDERFLOW` với packet capacity quá nhỏ, `BUFFER_OVERFLOW` với output capacity thiếu hoặc consumer chưa drain.
7. Khi memory quota bị chạm, ưu tiên fail/close có metric và giảm tải thay vì OOM toàn JVM.
8. Hạn chế số retries của từng operation trong một event để tránh peer gây CPU starvation; nếu không còn progress, đợi I/O/task tương ứng.

Bảng công thức sơ bộ:

```text
memoryPerConnection ~= networkInCapacity
                     + networkOutCapacity
                     + applicationInCapacity
                     + queuedAppOutBytes
                     + bufferPoolOverhead
                     + TLS/session/key material overhead

total ~= sum(active connection memory)
         + global caches + executor queues + JVM overhead
```

Đây là **ước lượng để lập budget**, không phải phép đo chính xác JVM native memory. TLS provider còn dùng object/session caches/temporary buffers; nên đo peak/RSS/direct buffer pool, GC allocation, write queue và handshake concurrency.

### Metrics hữu ích

| Metric | Ý nghĩa |
| --- | --- |
| `sslengine_wrap_status_total{status="BUFFER_OVERFLOW"}` | Output network buffer bị thiếu |
| `sslengine_unwrap_status_total{status="BUFFER_UNDERFLOW"}` | Input TLS record bị phân mảnh hoặc capacity không đủ |
| `sslengine_unwrap_status_total{status="BUFFER_OVERFLOW"}` | Plaintext buffer đầy hoặc consumer chậm |
| `sslengine_handshake_duration`, `task_queue_delay` | Theo dõi latency/độ nghẽn TLS handshake và delegated tasks |
| `tls_pending_network_out_bytes` | Áp lực pending socket writes |
| `tls_pending_app_in_bytes` | Áp lực application consumer/backpressure |
| `tls_unclean_eof_total` | Kết nối bị cắt thiếu close_notify |
| `tls_clean_close_total` | Đã xử lý close_notify đầy đủ |
| `tls_buffer_grows_total`, `tls_buffer_cap_exceeded_total` | Churn/capacity pressure và malicious/oversized records |
| `tls_active_connections`, `pool_bytes_in_use` | Resource budget và pool leak |

Gắn metrics theo provider/TLS version và high-level service, tránh cardinality quá lớn do connection ID/remote IP cho mọi sample. Đừng log plaintext TLS hoặc private keys để debug; với `-Djavax.net.debug=ssl,handshake` chỉ bật trên hệ thống test có giới hạn và hiểu dữ liệu xuất ra.

## 14. Ma trận kiểm thử cần thiết

| Kịch bản | Cách tạo | Kết quả đúng |
| --- | --- | --- |
| `wrap` output quá nhỏ | `EngineStatusProbe` `ByteBuffer.allocate(1)` | `BUFFER_OVERFLOW`; không mất app data |
| `unwrap` input rỗng | Server engine mới, network buffer rỗng | `BUFFER_UNDERFLOW`; đợi network |
| TLS record chia thành 2–3 mảnh | Socket/test transport chỉ chuyển từng phần | Lưu bytes chưa xử lý qua `compact` và ghép đúng |
| Hai TLS records trong một lần read | Peer gửi nhiều record trước một `read` | Xử lý lần lượt đến underflow/no progress, không bỏ data |
| Plaintext buffer đầy | `unwrap` với destination thiếu | `BUFFER_OVERFLOW`; drain/grow app buffer, retry |
| Socket partial write | Channel chỉ tiêu thụ phần của `networkOut` | Giữ remainder, chờ `OP_WRITE`; không gửi trùng |
| `SocketChannel.read()==0` | Non-blocking I/O chưa có data | Không spin |
| `SocketChannel.read()==-1` khi chưa close_notify | Ngắt transport đột ngột | Truncation/unclean EOF; `closeInbound` theo policy và xử lý exception |
| Client close_notify rồi server phản hồi | `EngineLoopbackDemo` | Cả hai `isInboundDone`/`isOutboundDone` true |
| Mất close_notify ở một chiều | Bỏ bản tin close_notify trong test transport | Không báo clean close |
| Handshake `NEED_TASK` chậm | Trust manager tác vụ mô phỏng delay | Không block selector toàn hệ thống; bounded executor |
| Peer gửi liên tục, consumer chậm | Giới hạn application processing | Backpressure không bùng RAM |
| Vượt memory cap | Cấu hình buffer cap nhỏ có chủ ý | Fail có kiểm soát, không endless grow |
| Hết hạn/cert không đáng tin | Dùng keystore khác/hostname mismatch trong lab | Handshake thất bại, không tắt trust check để workaround |
| TLS 1.2/1.3 và provider khác nhau | Test trên JDK/provider mục tiêu | Xác minh state machine tương thích, không dựa vào một trace cụ thể |

Trong test tích hợp, **đừng tạo kết quả mong muốn bằng cách bắt mọi exception rồi trả success**. Đặc biệt lỗi certificate, TLS record integrity, close_notify/truncation và buffer cap phải là lỗi phân biệt được.

## 15. Lỗi thường gặp và hướng sửa

| Sai lầm | Vì sao sai | Sửa thế nào |
| --- | --- | --- |
| Xem `BUFFER_UNDERFLOW` là TLS corrupt | Thiếu bytes chưa có nghĩa record sai | Giữ remainder, chờ thêm bytes, kiểm tra capacity |
| `clear()` network input sau underflow | Xóa logic bytes của record còn thiếu | `compact()` rồi đọc tiếp |
| Gọi `unwrap` lặp vô hạn khi không có thêm bytes | Busy loop, CPU tăng | Đợi `OP_READ` hoặc event/task có progress |
| Cứ underflow là nhân đôi buffer | Tăng RAM vô hạn, che lỗi stall | So `getPacketBufferSize()` và giới hạn capacity |
| Thấy overflow ở `unwrap` rồi đọc thêm socket | Sai buffer: output app bị đầy | Drain/grow `applicationIn` |
| Thấy overflow ở `wrap` rồi tăng application buffer | Sai buffer: output network bị đầy | Flush/grow `networkOut` |
| `clear()` networkOut sau partial socket write | Mất TLS bytes, phá record stream | `flip → write → compact` |
| Bỏ qua `bytesConsumed()` | Có thể mất plaintext hoặc đếm sai | Dựa vào ByteBuffer positions và result counters |
| `OK` được xem là handshake xong | `NEED_TASK/NEED_WRAP` có thể còn | Xử lý cả `HandshakeStatus` |
| Chạy delegated task nặng trên selector | Block hàng trăm connections | Bounded executor và per-engine ownership |
| `closeOutbound()` rồi đóng socket ngay | close_notify chưa được gửi | `wrap(EMPTY)`, flush TLS bytes trước |
| `isOutboundDone()==true` nghĩa socket queue rỗng | Engine không quản lý kernel/socket pending bytes | Theo dõi networkOut và socket write completion |
| Nuốt `SSLException` từ `closeInbound` | Che connection bị truncated | Đánh dấu unclean EOF và kiểm tra app framing |
| Tái sử dụng `SSLEngine` đã đóng | Engine state không được reset cho connection mới | Tạo engine mới |
| Tưởng `ByteBuffer.clear()` xóa plaintext khỏi RAM | Chỉ reset metadata position/limit | Zeroization riêng theo policy và lifecycle |
| Trả buffer vào pool khi còn slice/duplicate đang dùng | Có thể rò dữ liệu / race | Buffer ownership, refcount/lifecycle rõ |
| Alloc per handshake không giới hạn | Tấn công tạo nhiều handshake gây OOM/GC | Connection quota, memory cap, bounded tasks |
| Chỉ test happy path | Lỗi xuất hiện dưới fragmentation/partial write | Thử underflow/overflow/truncation/slow consumer |
| Bật trust-all để demo chạy | Mất TLS identity verification | Truststore lab đúng và endpoint identification |
| Copy nguyên demo RAM vào production | Không có selector/backpressure/timeout/protocol integration | Xây event loop và tests theo môi trường thật |

## 16. Bài tập thực hành

1. **Nhận diện buffer:** với `wrap` và `unwrap`, chỉ ra buffer nguồn/đích và chứng minh vì sao cùng `BUFFER_OVERFLOW` nhưng phải tăng buffer khác nhau.
2. **Đọc trạng thái:** `Status.OK`, `HandshakeStatus.NEED_WRAP`, `bytesConsumed=0`, `bytesProduced=125`. Vì sao đây có thể là handshake record chứ không phải app ciphertext?
3. **Underflow có fragmentation:** peer gửi TLS record theo ba mảnh. Mô tả `position/limit` trước `unwrap`, sau `compact` và khi nhận mảnh thứ ba. Điều gì mất nếu gọi `clear` thay `compact`?
4. **Overflow khi socket chậm:** `networkOut` có pending record và `channel.write` chỉ ghi 20%. Thiết kế `OP_WRITE` và `compact` để gửi nốt, không tạo record trùng.
5. **Plaintext buffer đầy:** `unwrap` trả `BUFFER_OVERFLOW` trong khi `networkIn` có đủ bytes. Đề xuất hai phương án sửa: drain consumer hoặc grow buffer, nêu ưu/nhược dưới tải cao.
6. **Thực nghiệm Java:** chạy `EngineStatusProbe` và giải thích vì sao `wrapConsumed=0` không ngăn client sinh handshake data khi buffer đủ.
7. **TLS loopback:** chạy `EngineLoopbackDemo` trên TLSv1.3, giải thích vì sao output có `messageRecovered=true` và bốn trạng thái Done đều true.
8. **Tắt hostname check:** trong một bản copy lab, bỏ `setEndpointIdentificationAlgorithm("HTTPS")` rồi nghĩ lại tác động: vì sao client có thể chấp nhận cert trusted nhưng tên máy không đúng? Tránh đưa thay đổi này vào production.
9. **Close bất thường:** mô phỏng chỉ gửi TCP FIN không có close_notify. Vì sao gọi `closeInbound` có thể ném exception? Nên xử lý dữ liệu đã nhận thế nào?
10. **Memory budget:** giả sử 30.000 connections, mỗi connection có hai packet buffers và một app buffer. Xây bảng capacity thực đo và hạn mức tổng RAM, tính tác động của việc tự động gấp đôi mọi buffer.
11. **TLS states:** phân biệt `NEED_UNWRAP` và `NEED_UNWRAP_AGAIN`. Khi nào cần đọc socket, khi nào không? Trạng thái nào liên quan chủ yếu DTLS?
12. **Delegated task:** mô phỏng trust manager chậm 200ms và giải thích vì sao không chạy trực tiếp trên selector có nhiều kết nối.
13. **Result counters:** lý giải khi `unwrap` tiêu thụ 200 TLS bytes nhưng sinh 0 plaintext. Có nghĩa bị mất dữ liệu không?
14. **Production checklist:** viết pseudo-code cho `Selector` bảo đảm flush trước close, không spin khi I/O trả 0, chặn memory cap, ghi metric underflow/overflow theo thao tác và không dùng plaintext trước TLS record integrity checks.
15. **Peer reset:** trong test, ngắt transport ngay sau khi application gửi nửa message. Phân biệt TLS stream truncation và “business message hoàn chỉnh”, đề xuất framing/transaction boundary.
16. **Buffer pooling:** vì sao `ByteBuffer.allocateDirect()` không có nghĩa nên cấp vô hạn? Mô tả quy trình trả pool khi app có `slice()` và socket còn pending writes.

**Tiêu chí hoàn thành:** giải thích đúng `BUFFER_UNDERFLOW` (chờ data) và `BUFFER_OVERFLOW` (thiếu output space); bảo toàn `ByteBuffer` qua `flip/compact`; xử lý handshake và close_notify bằng `SSLEngineResult`, phân biệt clean shutdown/truncation; và vận hành bộ đệm có trần tài nguyên/selector/backpressure hợp lý.

## Tài liệu tham khảo

- [Java SE 17 `SSLEngine` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): `wrap`, `unwrap`, buffer overflow/underflow, closure, `closeInbound/closeOutbound`.
- [Java SE 17 `SSLEngineResult` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.html): `getStatus`, `getHandshakeStatus`, `bytesConsumed/bytesProduced`.
- [Java SE 17 `SSLEngineResult.Status`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.Status.html): `OK`, `BUFFER_OVERFLOW`, `BUFFER_UNDERFLOW`, `CLOSED`.
- [Java SE 17 `SSLEngineResult.HandshakeStatus`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html): `NEED_TASK`, `NEED_WRAP`, `NEED_UNWRAP`, `NEED_UNWRAP_AGAIN`, `FINISHED`.
- [Java SE 17 `SSLSession`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): `getPacketBufferSize` và `getApplicationBufferSize`.
- [Java SE 17 `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `compact`, `clear`.
- [Java SE 17 `SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking reads/writes và end-of-stream.
- [Oracle Java Security Developer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): JSSE, SSLEngine examples, TLS initialization và session configuration.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): alerts, record layer và `close_notify`.
