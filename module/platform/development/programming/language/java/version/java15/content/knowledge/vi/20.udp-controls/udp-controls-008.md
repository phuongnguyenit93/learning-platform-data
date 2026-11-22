# Timeout ứng dụng, số thứ tự và xác nhận khi giao thức UDP cần — Java 15+

## 1. Mục tiêu

UDP cung cấp cơ chế gửi và nhận **datagram độc lập**, nhưng không tự bảo đảm datagram tới đích, tới đúng thứ tự hay chỉ tới một lần. `DatagramSocket.send(...)` thành công **không phải** xác nhận của ứng dụng bên nhận. Một lần `DatagramSocket.receive(...)` hết thời gian chờ cũng **không có nghĩa** server chưa xử lý yêu cầu: gói request, gói ACK hoặc cả hai đều có thể bị mất/chậm.

Nếu nghiệp vụ yêu cầu biết kết quả trao đổi, một giao thức ứng dụng chạy trên UDP có thể cần tự định nghĩa:
- **Timeout cho một lần nhận**, **deadline của toàn tác vụ** và giới hạn số lần gửi.
- **Số thứ tự / request ID** để đối chiếu ACK với đúng request, nhận biết bản sao và loại phản hồi cũ.
- **ACK (acknowledgment)** với ngữ nghĩa được thỏa thuận: đã nhận, đã đưa vào hàng đợi, đã xử lý hay đã ghi bền vững?
- **Retry có giới hạn, backoff và congestion control**, không bắn lại liên tục khi mạng tắc.
- **Idempotency/deduplication** khi request có thể được nhận nhiều lần.

Đây là kiến thức vẫn áp dụng trong Java hiện hành. Bài dùng các API `java.net.DatagramSocket`, `DatagramPacket`, `SocketTimeoutException`, `System.nanoTime()` và `ByteBuffer` mà Java 15 hỗ trợ. Khi chỉ cần kết nối tin cậy phổ biến, nên ưu tiên giao thức đã thiết kế sẵn như TCP/TLS, HTTP hoặc QUIC thích hợp; **không phải mọi ứng dụng UDP đều cần ACK và retry tự chế**.

Sau bài, bạn sẽ giải thích được vì sao timeout là trạng thái **chưa biết kết quả**, xác định request ID đúng vai trò, kiểm tra ACK, tránh thao tác lặp và chạy một ví dụ Java 15 có **ACK đầu tiên bị bỏ có chủ đích** để thấy cơ chế gửi lại.

## 2. Hai mốc cần phân biệt: UDP đã gửi và ứng dụng đã xác nhận

Xét client gửi yêu cầu `SET:42` và muốn server cập nhật một trạng thái. Chuỗi trao đổi lý tưởng:

```text
Client                                   Server
  |                                        |
  | --- DATA(seq=42, body="SET:42") ---->  |
  |                                        |  Validate
  |                                        |  Apply operation once
  | <----------- ACK(seq=42) ------------  |
  |                                        |
Client reports result according to ACK contract
```

Nhưng các chuỗi sau cũng hoàn toàn có thể xảy ra:

| Tình huống | Client có thể quan sát | Server thực tế |
| --- | --- | --- |
| DATA mất trên đường | Chờ ACK đến timeout | Chưa nhận yêu cầu |
| DATA đến; ACK bị mất | Chờ ACK đến timeout | **Có thể đã xử lý thành công** |
| DATA đến; server xử lý chậm | Timeout trước ACK | Có thể đang xử lý |
| ACK đến trễ sau khi client gửi lại | Có thể nhận ACK của lần gửi đầu | Có thể đã xử lý một hoặc nhiều lần nếu không dedup |
| DATA bị lặp do retry | Server nhận cùng request nhiều lần | Cần tránh tạo tác động nghiệp vụ nhiều lần |
| ACK giả mạo hoặc cũ | Client có thể nhầm thành thành công | Chưa chắc server hợp lệ đã xác nhận |

Vì vậy, **timeout không đồng nghĩa thất bại**, cũng **không đồng nghĩa thành công**. Nó chỉ nói caller **chưa quan sát được phản hồi hợp lệ trong khoảng chờ**. Không tự động ghi trạng thái “thanh toán thất bại” hoặc “thanh toán thành công” chỉ dựa vào việc UDP timeout.

Một hệ thống cần kết quả chắc chắn phải dựa vào một hợp đồng nghiệp vụ rõ ràng, ví dụ tra cứu lại trạng thái giao dịch bằng request ID, ACK sau khi commit bền vững, hoặc cơ chế đối soát. Các lựa chọn đó vượt khỏi tính năng có sẵn của `DatagramPacket`.

## 3. Socket timeout không phải application deadline

### 3.1. `setSoTimeout` áp dụng cho một lời gọi receive đang chặn

Trong Java, có thể đặt timeout nhận:

```java
try (DatagramSocket socket = new DatagramSocket()) {
    socket.setSoTimeout(1000); // milliseconds, áp dụng cho receive().
    DatagramPacket packet = new DatagramPacket(new byte[1200], 1200);
    try {
        socket.receive(packet);
        // Chỉ xử lý sau khi đã kiểm tra packet hợp lệ.
    } catch (java.net.SocketTimeoutException timeout) {
        // Trong 1000 ms chờ này chưa nhận được datagram phù hợp.
    }
}
```

Đây là đoạn ví dụ trong phương thức có import `java.net.*` và khai báo/giải quyết ngoại lệ I/O. `receive()` trả khi có một datagram; `setSoTimeout(0)` nghĩa là **không giới hạn thời gian chờ theo option này**. Khi quá thời gian, `SocketTimeoutException` được ném, nhưng **socket vẫn hợp lệ** để tiếp tục nhận. Một timeout ở socket không hủy request đã gửi và không rollback tác vụ ở server.

**Không nhầm `setSoTimeout` với một deadline toàn nghiệp vụ.** Nếu ứng dụng luôn gọi `receive()` với timeout 1 giây trong vòng lặp vô hạn, mỗi lần nhận datagram sai, lỗi hoặc retry có thể lại bắt đầu một khoảng chờ mới. Tác vụ tổng thể vẫn có thể kéo dài vô hạn.

### 3.2. Deadline toàn tác vụ dùng `System.nanoTime()`

Một **application deadline** xác định hạn cuối cho **toàn bộ thao tác**, bao gồm nhiều lượt gửi, nhiều lượt chờ, xử lý ACK và thời gian backoff.

Mẫu tính thời gian phù hợp:

```java
long deadlineNanos =
        System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(4);

long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new IllegalStateException("Application deadline expired");
}
```

Sử dụng **chênh lệch thời gian đơn điệu (elapsed time)** từ `System.nanoTime()`, không dùng `System.currentTimeMillis()` để đo các khoảng chờ nội bộ vì đồng hồ tường có thể bị điều chỉnh. Giá trị tuyệt đối của `nanoTime()` không có nghĩa là timestamp trên lịch và không truyền giữa các máy để so sánh.

Khi dùng `receive` đang chặn, đặt timeout hiện tại không vượt **ngân sách thời gian còn lại**, và kiểm tra deadline một lần nữa sau khi xử lý dữ liệu. Vì socket option đo bằng millisecond, cần xử lý làm tròn hợp lý (ví dụ tối thiểu 1 ms) và không đợi vượt deadline quá lâu. Nếu thư viện hoặc tầng I/O hỗ trợ deadline trực tiếp, ưu tiên cách đó thay vì tự cấu hình lại một socket được chia sẻ bởi nhiều thread.

### 3.3. Phân biệt ba giới hạn

| Giới hạn | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| Per-receive timeout | Mỗi lần `receive` có thể chờ tối đa bao lâu | `socket.setSoTimeout(400)` |
| Per-attempt retry timer / RTO | Chờ phản hồi của một lần gửi trước khi xét retransmit | Bắt đầu bằng RTT estimate hoặc một mức có chính sách |
| Overall application deadline | Hạn cuối cho toàn bộ request gồm mọi lần retry | Tối đa 4 giây cho bài thử |
| Max attempts | Giới hạn số lần phát DATA | Tối đa 2 lần trong ví dụ |
| Retry/backoff policy | Phân phối thời điểm gửi lại, giảm tải khi tắc | RTO tăng dần, jitter, rate limit |

**400 ms trong chương trình ở mục 9 chỉ dùng để kiểm thử loopback** và cố ý mô phỏng một ACK bị mất. Nó **không phải timeout khuyến nghị** cho Internet. RFC 8085 khuyên ứng dụng UDP có retry phải tính đến RTT và congestion; nếu dùng timeout định sẵn do thiếu RTT estimate, mức ban đầu khoảng 1 giây là một khuyến nghị phổ biến của tài liệu đó, cùng exponential backoff và giới hạn tốc độ thích hợp.

## 4. Số thứ tự (sequence number) và request ID dùng làm gì?

Một ACK chỉ có nội dung `"OK"` là mơ hồ nếu client có nhiều yêu cầu đang chờ. Gói ACK nên chứa thông tin đủ để **liên hệ với yêu cầu chính xác**.

Ví dụ bản tin ở mức ứng dụng:

```text
Request:
  version = 1
  type = DATA
  session = <session-id>
  sequence = 42
  payload = SET:42

ACK:
  version = 1
  type = ACK
  session = <same-session-id>
  sequence = 42
  status = ACCEPTED / COMMITTED / FAILED (định nghĩa cụ thể)
```

**Phân biệt thứ tự và danh tính:**

- **Sequence number** biểu thị thứ tự logic của bản tin trong một phiên, hữu ích cho phát hiện bản sao, bỏ các ACK cũ, tái sắp thứ tự hoặc theo dõi outstanding requests.
- **Request ID** định danh một thao tác nghiệp vụ cụ thể. Retransmission của cùng thao tác phải **giữ nguyên ID** để server deduplicate.
- **Session ID / client identity** tách không gian sequence giữa các phiên và các client. Chỉ dùng con số `42` chung cho mọi client là không đủ.
- **ACK correlation** tối thiểu cần đối chiếu version/type, ID/sequence, phiên và endpoint hợp lệ; ứng dụng cần bảo mật còn phải xác thực cryptographic nguồn ACK.
- **Sequence wrap-around** có thể xảy ra khi counter hữu hạn, ví dụ 32-bit. Không dùng phép so sánh signed `a > b` một cách tùy tiện quanh điểm wrap; cần quy tắc modular ordering và epoch/session, hoặc dùng ID đủ rộng và vòng đời rõ ràng.

Trong bài thực hành chỉ gửi **một thao tác, một client và một server**, nên minh họa ngắn gọn bằng `long SEQUENCE=42`; đây **không phải định dạng protocol production** đầy đủ. Hệ thống đa client cần tối thiểu một khóa nhận dạng kiểu `(authenticatedClient, session, requestId)`, không chỉ sequence number.

### Retransmission phải dùng cùng ID

```text
Lần gửi 1: DATA(session=S, seq=42, payload=SET:42)
Timeout
Lần gửi 2: DATA(session=S, seq=42, payload=SET:42)  <-- CÙNG ID

Yêu cầu mới: DATA(session=S, seq=43, payload=SET:99) <-- ID MỚI
```

Nếu retry dùng sequence mới, server có thể nghĩ đó là **một nghiệp vụ mới** và thực hiện lại thao tác. Nếu payload thay đổi trong khi ID không đổi, server nên từ chối conflict hoặc áp dụng hợp đồng bất biến đã thiết kế, không âm thầm lấy request mới đè lên request cũ.

Không suy rằng việc có một sequence là đủ xác thực gói tin: kẻ tấn công có thể đoán/quan sát và tạo ACK giả nếu giao thức không có khóa xác thực hoặc kênh đã được bảo vệ.

## 5. ACK xác nhận điều gì?

Một “ACK” chỉ có giá trị khi hai bên hiểu **điều kiện tạo ACK**:

| Hợp đồng ACK | Server gửi ACK khi | Client được suy ra |
| --- | --- | --- |
| RECEIVED | Datagram được parser nhận vào bộ nhớ | Server nhận gói, **chưa chắc xử lý** |
| ACCEPTED / QUEUED | Request đã được chấp nhận vào hàng đợi | Tác vụ được tiếp nhận, có thể chưa hoàn tất |
| PROCESSED | Thao tác đã xử lý trong tiến trình | Server đã xử lý theo định nghĩa, nhưng có thể chưa lưu bền vững |
| COMMITTED | Kết quả và trạng thái dedup đã được ghi bền vững | Có cơ sở mạnh hơn để khẳng định thao tác đã được commit |
| FAILED / REJECTED | Đã từ chối sau validation/authorization | Cần mã lỗi và chính sách retry rõ ràng |

ACK gửi trước khi trạng thái được lưu bền có thể dẫn đến “client tin là thành công nhưng server crash mất dữ liệu”. ACK sau commit giúp cải thiện điều đó, nhưng vẫn cần định nghĩa duplicate handling và phục hồi.

**ACK có thể bị mất.** Khi client không nhận ACK, nó có thể gửi lại cùng request. Đó là lý do server cần kết hợp **ghi nhận ID → kết quả** với nghiệp vụ, lý tưởng là cùng một transaction nếu yêu cầu tránh tác động lặp.

**ACK không tự xác thực danh tính.** Kiểm tra source IP/port chỉ là kiểm tra endpoint dự kiến; nó không ngăn spoofing trên mọi network. Nếu ACK có thể kích hoạt hành vi nhạy cảm, cần MAC, AEAD, DTLS hoặc một giao thức có xác thực tương đương.

## 6. Luồng gửi có giới hạn: request, chờ, retransmit và dừng

Một state machine đơn giản khi giao thức thật sự cần ACK:

```text
START
  |
  v
Check overall deadline / max attempts
  |
  v
Send DATA with same (session, request-id)
  |
  v
Wait for ACK within attempt RTO and remaining deadline
  |
  +---- valid matching, authenticated ACK ----> DONE
  |
  +---- unrelated/old/malformed ACK ----------> discard; continue waiting
  |
  +---- timeout ------------------------------> backoff, reduce sending rate
  |                                               |
  |                                               +--> if budget remains, retry
  |
  +---- deadline/attempt limit exhausted ------> UNKNOWN RESULT
                                                  reconcile/query later
```

Khi thiết kế vòng lặp thực tế:
1. Có **overall deadline**, không cho request chạy mãi.
2. Có **max attempts**, giới hạn tổng số datagram request phát ra.
3. Có timeout dựa trên ước lượng RTT hoặc cấu hình hợp lý cho đường mạng.
4. Có retry backoff (thường exponential), jitter khi nhiều client, và congestion control theo RFC 8085.
5. Không gọi retry dồn dập vì nhận một datagram sai; ACK không khớp phải bị loại nhưng không làm reset budget.
6. Khi đã hết budget mà không có ACK hợp lệ, trả trạng thái **UNKNOWN / NOT CONFIRMED**, không tự ghi FAILED.
7. Nghiệp vụ nhạy cảm cần cơ chế **status reconciliation** dựa trên request ID, hoặc chờ thông báo kết quả từ server.

**Không nên tự triển khai toàn bộ reliable UDP chung chung chỉ bằng một vòng lặp**. Giao thức production cần chiến lược quản lý nhiều request, congestion, ACK loss, duplicate/replay, restart, security và đôi khi fragmentation; hãy cân nhắc QUIC hoặc transport đáng tin cậy sẵn có.

## 7. Server phải nhận biết duplicate và giới hạn hiệu ứng

Giả sử request tăng số dư 100 đơn vị. Nếu server xử lý lại cùng request sau ACK loss, số dư có thể tăng **hai lần**. Có hai chiến lược phổ biến:

### 7.1. Thao tác idempotent

Một lệnh dạng `SET balance=42` có thể idempotent nếu thực hiện lại cùng nội dung dẫn đến cùng kết quả, dưới các điều kiện khác không đổi. Ngược lại `INCREMENT balance BY 42` thường **không idempotent**.

Tuy nhiên **idempotent không tự giải quyết mọi vấn đề**: có thể có log, email, side effect, timestamp hoặc phiên bản trạng thái thay đổi khi chạy lại. Và các thao tác gán cũng có thể xảy ra ngoài thứ tự với những request khác nếu không kiểm soát version/order.

### 7.2. Deduplication theo request ID

Server giữ registry, ví dụ:

```text
Key:   (authenticated-client, session, request-id)
Value: payload-hash, state(IN_PROGRESS/COMMITTED/FAILED), result/ACK
```

Khi nhận request:
- **ID chưa thấy:** validate; thực thi nghiệp vụ; ghi result; gửi ACK theo hợp đồng.
- **ID đã COMMITTED, payload giống:** **không áp dụng lại**, trả ACK/result đã ghi trước đó.
- **ID đã IN_PROGRESS:** không thực hiện lại song song; đợi, ghi nhận trạng thái hoặc phản hồi tạm theo contract.
- **ID cũ nhưng payload khác:** từ chối conflict vì không thể coi đó là retry cùng tác vụ.
- **Request expired/ngoài cửa sổ replay:** áp dụng chính sách phiên và xử lý lỗi rõ ràng.

Trong hệ thống nhiều instance, cache chỉ nằm trong RAM một server **không bảo đảm dedup sau crash hoặc khi request bị route sang instance khác**. Nếu nghiệp vụ cần đảm bảo tác động xảy ra tối đa một lần qua restart/failover, phải có khóa dedup bền vững, transaction/unique constraint và xử lý side effects thích hợp. Không quảng cáo “exactly once” chỉ vì có sequence và ACK.

**Giữ registry có giới hạn:** TTL, dung lượng tối đa, per-client quota, số yêu cầu đang chờ và chính sách cleanup. Nếu ID cũ được tái sử dụng sau TTL, hệ thống cần quy tắc phiên/epoch để không nhận nhầm replay.

## 8. Định dạng datagram mẫu trong Java 15

Chương trình ở mục 9 dùng frame rất nhỏ:

| Vị trí byte | Trường | Kích thước | Ý nghĩa |
| ---: | --- | ---: | --- |
| 0 | `version` | 1 | Giá trị 1 |
| 1 | `type` | 1 | 1 = REQUEST, 2 = ACK |
| 2..9 | `sequence` | 8 | `long`, big-endian |
| 10.. | `payload` | 0..N | Request có bytes ASCII `"SET:42"`; ACK không có payload |

Với request:
- 10 bytes header + 6 bytes ASCII của `"SET:42"` = **16 bytes**.
- ACK chỉ có 10 bytes.
- Có sẵn `InetAddress` và port từ `DatagramPacket`: không cần mã hóa lại remote IP/port trong payload để gửi ACK.

Java `ByteBuffer` mặc định big-endian; ta dùng `putLong()` và `getLong()` ở cùng byte order. Với protocol nhiều ngôn ngữ, **byte order phải ghi rõ trong đặc tả**. Khi nhận, dùng `packet.getData()`, `getOffset()` và `getLength()`, không đọc toàn bộ backing buffer.

**Đây chỉ là demo**: không có session ID, client identity, authentication tag, anti-replay hay status code. Các triển khai thật phải định nghĩa đầy đủ trước khi dùng cho dữ liệu nhạy cảm.

## 9. Chương trình hoàn chỉnh: ACK đầu tiên bị bỏ, retry và dedup

Chương trình minh họa trên **loopback**, sử dụng hai `DatagramSocket` trong một tiến trình và một thread server. Server **cố ý không gửi ACK cho datagram đầu** mặc dù đã nhận request. Client đợi rồi timeout, gửi lại **cùng sequence**, server nhận duplicate và không áp dụng lần thứ hai; cuối cùng trả ACK.

Cách mô phỏng này giúp stdout có thể kiểm chứng mà **không phải cố làm mất gói mạng thật**, không cần công cụ mạng ngoài hoặc firewall. Số lần retry và khoảng 400 ms được chọn **chỉ cho bài kiểm thử cục bộ**, không phải cấu hình Internet.

Lưu đúng tên file **`UdpAckRetryDemo.java`**:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class UdpAckRetryDemo {
    private static final byte VERSION = 1;
    private static final byte REQUEST = 1;
    private static final byte ACK = 2;
    private static final long SEQUENCE = 42L;
    private static final byte[] BODY =
            "SET:42".getBytes(StandardCharsets.US_ASCII);
    private static final int HEADER_SIZE = 10;

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        AtomicBoolean processed = new AtomicBoolean();
        AtomicInteger applied = new AtomicInteger();
        AtomicInteger duplicates = new AtomicInteger();
        AtomicReference<Throwable> serverError = new AtomicReference<>();

        try (DatagramSocket server = new DatagramSocket(0, loopback);
             DatagramSocket client = new DatagramSocket(0, loopback)) {
            server.setSoTimeout(5000);
            final int serverPort = server.getLocalPort();

            Thread receiver = new Thread(() -> {
                try {
                    for (int n = 0; n < 2; n++) {
                        DatagramPacket incoming = new DatagramPacket(
                                new byte[256], 256);
                        server.receive(incoming);
                        checkRequest(incoming);

                        if (processed.compareAndSet(false, true)) {
                            applied.incrementAndGet();
                        } else {
                            duplicates.incrementAndGet();
                        }

                        // Model one ACK loss. The request still reached server.
                        if (n == 0) {
                            continue;
                        }

                        byte[] ack = ByteBuffer.allocate(HEADER_SIZE)
                                .put(VERSION).put(ACK)
                                .putLong(SEQUENCE).array();
                        server.send(new DatagramPacket(ack, ack.length,
                                incoming.getAddress(), incoming.getPort()));
                    }
                } catch (Throwable e) {
                    serverError.set(e);
                }
            }, "udp-demo-server");
            receiver.start();

            byte[] request = ByteBuffer.allocate(HEADER_SIZE + BODY.length)
                    .put(VERSION).put(REQUEST)
                    .putLong(SEQUENCE).put(BODY).array();

            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(4);
            int timeouts = 0;
            boolean acknowledged = false;

            for (int attempt = 1; attempt <= 2 && !acknowledged; attempt++) {
                if (System.nanoTime() >= deadline) {
                    throw new IllegalStateException("application deadline expired");
                }
                client.send(new DatagramPacket(request, request.length,
                        loopback, serverPort));

                long remainingNanos = deadline - System.nanoTime();
                int waitMillis = (int) Math.min(400,
                        Math.max(1, TimeUnit.NANOSECONDS.toMillis(
                                Math.max(1, remainingNanos))));
                client.setSoTimeout(waitMillis);

                try {
                    DatagramPacket reply = new DatagramPacket(
                            new byte[HEADER_SIZE], HEADER_SIZE);
                    client.receive(reply);
                    acknowledged = isExpectedAck(reply, loopback, serverPort);
                    System.out.println("attempt " + attempt +
                            ": valid ACK=" + acknowledged);
                } catch (SocketTimeoutException expected) {
                    timeouts++;
                    System.out.println("attempt " + attempt + ": timeout");
                }
            }

            receiver.join(2500);
            if (receiver.isAlive()) {
                throw new IllegalStateException("server thread did not finish");
            }
            if (serverError.get() != null) {
                throw new IllegalStateException("server failed", serverError.get());
            }
            System.out.println("server applied count: " + applied.get());
            System.out.println("server duplicate count: " + duplicates.get());
            System.out.println("client receive timeouts: " + timeouts);
            System.out.println("acknowledged: " + acknowledged);
            if (!acknowledged) {
                throw new IllegalStateException("No valid ACK before deadline");
            }
        }
    }

    private static void checkRequest(DatagramPacket packet) {
        if (packet.getLength() != HEADER_SIZE + BODY.length) {
            throw new IllegalArgumentException("unexpected request size");
        }
        ByteBuffer b = ByteBuffer.wrap(packet.getData(),
                packet.getOffset(), packet.getLength());
        byte version = b.get();
        byte kind = b.get();
        long sequence = b.getLong();
        byte[] payload = new byte[b.remaining()];
        b.get(payload);
        if (version != VERSION || kind != REQUEST ||
                sequence != SEQUENCE || !Arrays.equals(payload, BODY)) {
            throw new IllegalArgumentException("invalid request");
        }
    }

    private static boolean isExpectedAck(DatagramPacket packet,
            InetAddress expectedAddress, int expectedPort) {
        if (!expectedAddress.equals(packet.getAddress()) ||
                packet.getPort() != expectedPort ||
                packet.getLength() != HEADER_SIZE) {
            return false;
        }
        ByteBuffer b = ByteBuffer.wrap(packet.getData(),
                packet.getOffset(), packet.getLength());
        return b.get() == VERSION && b.get() == ACK &&
                b.getLong() == SEQUENCE;
    }
}
```

### 9.1. Biên dịch và chạy

Dùng JDK hỗ trợ đích Java 15:

```bash
javac --release 15 UdpAckRetryDemo.java
java UdpAckRetryDemo
```

**Stdout chính xác đã kiểm tra** khi biên dịch bằng `javac --release 15` và thực thi trên JDK hiện đại trong môi trường loopback:

```text
attempt 1: timeout
attempt 2: valid ACK=true
server applied count: 1
server duplicate count: 1
client receive timeouts: 1
acknowledged: true
```

Chương trình có 6 dòng kết quả. Nếu một máy có loopback/network stack bị chặn, bị quá tải hoặc thời gian thực thi quá chậm, ví dụ có thể gặp lỗi mạng hoặc hết deadline; output trên là **kết quả kiểm chứng của môi trường thử**, không phải bảo đảm UDP luôn nhận đủ gói.

### 9.2. Giải thích từng bước

1. Server và client bind vào loopback bằng port `0` để OS chọn cổng cục bộ còn trống. Client biết `server.getLocalPort()` trước khi gửi.
2. Client tạo frame gồm version=1, type=REQUEST, sequence=42, body=`"SET:42"`; mỗi lần retry giữ **đúng cùng 16 bytes**.
3. Thread server nhận lần đầu, kiểm tra frame, chuyển `processed` từ `false` sang `true` và tăng `applied` lên 1. Nó **bỏ qua bước gửi ACK có chủ đích**, dù request đã xử lý.
4. Client không có ACK trong thời gian chờ 400 ms, nhận `SocketTimeoutException` và in `attempt 1: timeout`.
5. Client còn ngân sách thời gian và số lượt, nên gửi lại **cùng sequence=42**.
6. Server nhận lại, thấy `processed` đã true, tăng `duplicates` lên 1 nhưng **không tăng `applied`**; sau đó gửi ACK về `incoming.getAddress()` và `incoming.getPort()`.
7. Client nhận ACK, kiểm tra source IP, source port, độ dài 10 bytes, version, type và sequence=42. Vì tất cả phù hợp, `acknowledged=true` và dừng retry.
8. Thread server kết thúc; main đợi bằng `join`, kiểm tra lỗi server rồi in thống kê. `AtomicBoolean`/`AtomicInteger` giúp trạng thái dùng xuyên thread được quan sát đúng trong ví dụ.

### 9.3. Hạn chế cố ý của demo

- Server chỉ xử lý **đúng hai datagram** từ một client và có một `AtomicBoolean` cho một request. Đây không phải bản triển khai multi-client; production cần registry theo **(client/session/request ID)** với TTL và chính sách bền vững.
- Timeout 400 ms, tối đa hai lần, deadline 4 giây là cấu hình **kiểm thử loopback**. Không copy các con số này vào hệ thống Internet như một RTO hoặc congestion control chuẩn.
- `isExpectedAck(...)` kiểm tra source IP/port **chứ không xác thực mật mã**; attacker có thể giả mạo thông điệp trong những điều kiện mạng nhất định. Dùng protocol có bảo vệ khi cần.
- Ví dụ chỉ cần nhận một ACK trong mỗi lần thử. Với nhiều datagrams đang chờ hoặc ACK giả/không khớp, production phải **tiếp tục nhận cho đến hết attempt deadline**, loại ACK sai mà không tự tăng attempt hoặc gia hạn toàn bộ deadline. Mã demo khi nhận một ACK sai sẽ thử lượt kế tiếp; không dùng nó làm bộ điều phối ACK tổng quát.
- ACK trong demo chỉ phản ánh một cập nhật **trong bộ nhớ** (`applied`). Nó **không chứng minh durable commit**; mất tiến trình có thể mất trạng thái.
- Không có backoff/jitter hoặc RTT estimator vì mục tiêu ví dụ là thấy ACK loss và dedup rõ ràng. Muốn triển khai thật, phải bổ sung congestion control đúng với tải và network.

Điểm học được là **client timeout dù server đã xử lý**; một retry đúng ID cho phép server tránh lặp hiệu ứng. Đó là logic ứng dụng, không phải cơ chế tự động của UDP.

## 10. Retry đúng: RTO, exponential backoff, jitter, rate limit

Gửi lại khi timeout có vẻ hợp lý, nhưng chính **tắc nghẽn mạng** có thể gây mất datagram/ACK; càng gửi lại liên tục càng làm tình hình xấu hơn.

Hướng dẫn IETF **RFC 8085** nhấn mạnh ứng dụng dùng UDP phải có cơ chế congestion control và cân bằng với lưu lượng khác. Nếu không có RTT estimate đáng tin và sử dụng một RTO định sẵn cho các request ít lưu lượng, hướng dẫn này khuyến nghị **mức khởi đầu khoảng 1 giây** và tăng theo exponential backoff; một số protocol cụ thể có cơ chế riêng. Đây là **định hướng**, không phải con số tuyệt đối cho mọi mạng và mọi ứng dụng.

Ví dụ thiết kế:

```text
initialRto = value based on RTT estimate / protocol
rto(n) = min(maxRto, initialRto * 2^n)
scheduledWait = rto(n) with bounded jitter
remainingBudget = deadline - monotonicNow()
wait = min(scheduledWait, remainingBudget)

if remainingBudget <= 0 or attempts >= maxAttempts:
    return UNKNOWN_RESULT
```

Cần kết hợp **jitter** khi nhiều client có thể retry cùng lúc, để giảm synchronized retry storms. Không nhân `long` không kiểm tra khiến overflow khi tính `2^n`; dùng phép tăng có cap. Không gửi nhiều lần ngay lập tức nếu vừa nhận một packet không hợp lệ. Rate limit riêng theo client/destination là cần thiết khi có nhiều outstanding requests.

**Đo RTT cẩn thận:** ACK cho một retransmission gây ambiguity về nó xác nhận lần gửi nào. Không suy RTT đơn giản từ thời điểm request đầu đến ACK sau retry; muốn RTO chuẩn phải theo quy tắc protocol/estimator phù hợp.

Một số workload (telemetry thời gian thực, voice, game) **cố ý không gửi lại dữ liệu cũ** vì giá trị dữ liệu đã hết hạn. Với workload này, timeout có thể chỉ dẫn đến bỏ qua sample và chuyển sang update tiếp theo; **ACK không phải yêu cầu bắt buộc** cho mọi datagram.

## 11. Kiểm tra ACK đúng request và đúng dữ liệu

Một ACK được nhận qua `DatagramPacket` có thể là:
- Datagrams của một request cũ, đến muộn.
- ACK có sequence không khớp.
- Gói không phải ACK (DATA, ERROR hoặc bản tin khác).
- Packet bị cắt do receive buffer quá nhỏ.
- Packet từ một endpoint khác.
- Packet giả mạo có đủ fields nhìn bề ngoài hợp lệ.

Bài demo kiểm tra bằng:

```java
boolean sourceMatches =
        expectedAddress.equals(reply.getAddress())
        && reply.getPort() == expectedPort;

boolean lengthMatches = reply.getLength() == HEADER_SIZE;
// Sau khi kiểm tra length, decode version, type và sequence.
```

Đây là đoạn **bên trong một phương thức có các biến đã được khởi tạo**, không phải chương trình độc lập. Việc đọc chỉ từ `reply.getOffset()` đến `reply.getOffset()+reply.getLength()` là bắt buộc; `getData()` trả cả backing buffer, có thể chứa bytes không thuộc datagram.

**Định dạng/validation cần rõ ràng:**
- Có magic hoặc version, type, chiều dài và giới hạn payload.
- Sequence/ID có đúng số bytes, byte order và phạm vi chưa bị wrap không?
- Độ dài frame có khớp exact length của datagram không? Không “giải mã được 10 bytes đầu” rồi bỏ qua bytes thừa không được đặc tả.
- ACK có đúng session/client/request ID đang chờ không, có nằm trong lifetime của request không?
- Server status có đúng hợp đồng hay ACK chỉ nói “received”?
- Có MAC/AEAD/tag hoặc kết nối được bảo vệ nếu dữ liệu/ACK cần xác thực không?
- Có chống replay và xử lý ACK lặp không?

**Đừng coi `getAddress()`/`getPort()` là một chứng thực cryptographic.** UDP có thể bị spoof trong một số môi trường; connected `DatagramSocket` cũng không biến nguồn packet thành danh tính đã được xác thực.

## 12. Số thứ tự, reorder, wrap-around và request song song

### Reorder và duplicate

UDP không bảo đảm thứ tự: `seq=102` có thể đến trước `seq=101`. Server cần xác định:
- Có yêu cầu **xử lý theo thứ tự** không? Nếu có, cần buffer nhỏ có giới hạn hoặc cơ chế sequencing.
- Hay yêu cầu **độc lập**, mỗi request được xử lý theo ID mà không cần tổng thứ tự?
- Nếu nhận duplicate, có trả ACK cùng kết quả hay bỏ qua? Nếu client cần ACK để dừng retry, **trả lại ACK cho duplicate hợp lệ** thường rất quan trọng.
- Nếu một ACK cũ đến sau khi request đã timeout/cancel, cần loại nó hoặc chuyển sang reconciliation theo state còn hợp lệ.

### Wrap-around của số thứ tự

Một sequence 32-bit sẽ quay vòng sau đủ số lần tăng. Ngay cả `long` 64-bit cũng có miền hữu hạn; khi dữ liệu cũ vẫn còn tồn tại trên mạng/cache, trùng ID với phiên mới là nguy hiểm.

Không dùng:
```java
// Không đúng tổng quát khi sequence có thể wrap và có nhiều phiên:
boolean newer = incomingSequence > lastSequence;
```

Muốn so sánh thứ tự modulo cần một **cửa sổ hợp lệ** và quy tắc rõ ràng; hoặc dùng request ID đủ rộng, phân tách namespace theo session/epoch và giới hạn lifetime để tránh alias. Với hệ thống nhiều client, **không** dùng một global `int` counter không persist làm danh tính duy nhất qua restart.

### Request song song và ACK multiplexing

Nếu client gửi đồng thời nhiều request trên một socket, không thể có nhiều thread tùy tiện gọi `receive` rồi giả định mỗi thread nhận ACK dành cho nó. Các thread có thể lấy datagrams của nhau. Cách an toàn thường dùng:
- Một receiver/demultiplexer đọc socket, validate packet.
- Dựa trên session/request ID để chuyển ACK đến đúng pending request/future.
- Giới hạn số outstanding requests, bộ nhớ và deadline.
- Khi retry/cancel hoàn tất, cập nhật state atomically; ACK đến muộn không được đánh dấu nhầm một request mới.

Tầng demultiplex và quản lý lifecycle không có sẵn chỉ nhờ `DatagramPacket`; đó là phần của protocol implementation.

## 13. Bảo mật, replay, spoofing và amplification

Sequence và ACK **không tự mang lại bảo mật**.

- **ACK spoofing:** attacker có thể phát ACK giả nếu ID dễ đoán và không có xác thực. Client phải tin cậy peer key/session, không chỉ trùng địa chỉ nguồn.
- **Replay:** attacker gửi lại một DATA/ACK hợp lệ đã quan sát; nếu server không có replay window/dedup, nghiệp vụ có thể chạy lại. Nonce/sequence phải được ràng buộc cryptographically với phiên.
- **Reflection/amplification:** UDP server trả một phản hồi lớn cho địa chỉ nguồn giả mạo có thể bị lợi dụng. Trước xác thực, cần hạn chế kích thước/khối lượng phản hồi và cân nhắc các quy tắc anti-amplification của protocol.
- **Resource exhaustion:** kẻ tấn công gửi vô số request IDs, khiến dedup registry hoặc pending ACK map tăng vô hạn. Áp dụng quota, TTL, max entries, kích thước packet tối đa và rate limit.
- **Authorization:** nhận packet và có signature/MAC hợp lệ cũng chưa đủ để thực thi mọi lệnh; kiểm tra quyền theo danh tính và trạng thái nghiệp vụ.
- **Transport bảo mật:** cân nhắc DTLS, QUIC, hoặc giao thức đã được đánh giá thay vì tự phát minh cơ chế mã hóa và MAC cho UDP.
- **Error handling:** không log private keys, tokens, toàn bộ payload nhạy cảm; tách lỗi validate, timeout, network và business status trong telemetry an toàn.

Một protocol có thể cần xác thực ACK **và** DATA, thêm session nonce/epoch và giữ anti-replay window. Chỉ tăng độ dài sequence từ 32 lên 64 bit **không thay thế** xác thực.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “`send()` không báo lỗi nghĩa là server đã nhận” | Chỉ chứng minh thao tác gửi được hệ thống chấp nhận, không bảo đảm delivery |
| “`SocketTimeoutException` nghĩa là server chưa xử lý” | ACK có thể bị mất sau khi server xử lý thành công |
| “Mỗi lần retry tạo sequence mới” | Retry **cùng nghiệp vụ** phải giữ request ID để server nhận duplicate |
| “Thêm sequence là tự động giao hàng đúng thứ tự” | Cần logic buffering, policy về missing/reorder và cửa sổ |
| “Có ACK nghĩa là durable commit” | Phải biết **ACK contract**, ACK RECEIVED không phải COMMITTED |
| “Gửi lại sẽ đúng một lần” | Retry có thể khiến xử lý nhiều lần nếu thiếu dedup/idempotency |
| “Server dedup trong RAM là exactly-once” | Crash/failover có thể làm mất trạng thái; cần thiết kế giao dịch bền vững |
| “Timeout socket 1 giây nghĩa là toàn request 1 giây” | Mỗi receive riêng có timeout; cần deadline cho toàn request |
| “Cứ retry nhanh nhất có thể khi mất ACK” | Có thể làm congestion nặng hơn; cần RTO/backoff/jitter/cap |
| “ACK có đúng source IP/port là đáng tin” | Source IP/port không phải xác thực cryptographic |
| “Khi toàn tác vụ hết deadline thì request chắc chắn thất bại” | Kết quả **chưa xác nhận**; cần reconcile |
| “Sequence long không bao giờ trùng” | Cần session namespace/lifetime; long vẫn có miền hữu hạn |
| “UDP client chỉ nên có một request” | Có thể nhiều request, nhưng cần ACK demultiplexer và quản lý state |
| “Mọi datagram đều phải có ACK” | Tùy protocol; dữ liệu thời gian thực có thể bỏ cũ thay vì retry |

## 15. Kiểm thử tình huống lỗi và điều kiện biên

Bên cạnh happy path, nên có các ca:

1. **Server không gửi ACK lần đầu nhưng request đến:** client timeout; retry cùng ID; server chỉ áp dụng một lần; ACK lặp được trả.
2. **DATA mất trước khi đến server:** client timeout; lần retry sau có thể là lần đầu server thấy ID; tác vụ áp dụng một lần.
3. **ACK đến trễ:** client vẫn liên hệ ACK với request cũ, không chấp nhận cho request mới có ID khác.
4. **ACK sai version/type/sequence:** bị từ chối; không chấm dứt deadline và không reset retry counter.
5. **ACK từ source endpoint khác:** không được coi là hợp lệ chỉ vì payload giống.
6. **Đổi payload nhưng giữ request ID:** server từ chối conflict, không thực hiện thao tác mới dưới ID cũ.
7. **Hai client dùng cùng sequence:** dedup dựa vào client/session ID, không chỉ sequence.
8. **Reorder:** gửi seq N+1 trước seq N; hệ thống phải xử lý theo policy rõ ràng (reorder buffer hay độc lập).
9. **Duplicate sau restart/failover:** kiểm tra trạng thái dedup bền vững nếu nghiệp vụ đòi hỏi.
10. **TTL hết hạn:** xác định điều gì xảy ra khi ID cũ quay lại; không nhận replay ngoài cửa sổ.
11. **Deadline vs per-receive timeout:** ACK không khớp liên tục không được gia hạn toàn request vô hạn.
12. **Retry overload:** mô phỏng nhiều client cùng timeout để kiểm tra exponential backoff, jitter và rate limit.
13. **Malformed/truncated packet:** dữ liệu quá ngắn, sai length/byte order/version → reject trước nghiệp vụ.
14. **Nonce/MAC sai khi có bảo mật:** từ chối dữ liệu và không cập nhật dedup/ACK như thể đã xác thực.
15. **Thao tác không idempotent:** duplicate không được gây side effect hai lần; đo metrics applied/duplicates riêng.
16. **Cancellation:** nếu client đã hủy request, ACK đến trễ không được tự khôi phục trạng thái thành công mà không theo chính sách.

Ví dụ mục 9 kiểm thử cụ thể ca **ACK đầu bị bỏ + retransmission + dedup**. Những ca còn lại cần thêm test harness/fault injection hoặc mô phỏng ở lớp protocol; **không tuyên bố chúng đã được chạy chỉ vì demo loopback thành công**.

## 16. Luyện tập có đáp án

**Câu 1.** Client gửi yêu cầu chuyển tiền; `receive()` ném `SocketTimeoutException`. Có thể khẳng định chưa chuyển tiền không?

**Đáp án:** **Không**. Server có thể đã commit nhưng ACK mất hoặc chậm. Trả trạng thái **chưa xác nhận**, tra cứu theo request ID và dùng idempotency/dedup ở server.

**Câu 2.** Retransmit cùng thao tác thì nên thay sequence từ 42 sang 43 không?

**Đáp án:** **Không** nếu sequence là ID của thao tác. Retry giữ cùng ID; request mới sử dụng ID mới, còn session và namespace phải được quy định.

**Câu 3.** Vì sao `setSoTimeout(500)` không bảo đảm cả tác vụ dài tối đa 500 ms?

**Đáp án:** Nó giới hạn **một lần `receive` đang chặn**. Nhiều lần receive/retry có thể vượt 500 ms; cần overall deadline riêng bằng `System.nanoTime()` hoặc cơ chế thời hạn của thư viện.

**Câu 4.** Server đã áp dụng lệnh nhưng ACK bị mất. Khi request lặp đến, server nên làm gì?

**Đáp án:** Kiểm tra ID và payload; nếu đó là duplicate hợp lệ thì **không áp dụng lại**, trả ACK hoặc kết quả đã lưu theo contract. Nghiệp vụ quan trọng cần lưu bền vững kết quả/dedup atomically.

**Câu 5.** `ACK(seq=42)` đến từ địa chỉ khác nhưng có byte format hợp lệ. Có nên nhận không?

**Đáp án:** **Không** theo chính sách endpoint đã biết; đồng thời IP/port trùng cũng **chưa đủ** nếu cần xác thực cryptographic. Dùng protocol bảo mật để chống ACK giả và replay.

**Câu 6.** Có thể chọn timeout 50 ms và retry vô hạn cho mọi client Internet không?

**Đáp án:** **Không**. Có thể tạo retry storm và congestion collapse. Cần RTT estimate hoặc timer phù hợp, max attempts/deadline, exponential backoff, jitter và congestion control theo RFC 8085 hoặc giao thức đã được chuẩn hóa.

**Câu 7.** ACK sau khi đưa request vào RAM queue có phải cam kết durable không?

**Đáp án:** **Không**. ACK có thể chỉ là ACCEPTED; nếu server crash trước khi lưu/ xử lý, tác vụ có thể mất. ACK contract phải nói rõ giai đoạn đã xác nhận.

**Câu 8.** Hai request có sequence `42` từ hai client khác nhau có phải duplicate không?

**Đáp án:** **Không thể kết luận chỉ từ sequence**. Cần client/session identity tin cậy và request ID để phân biệt.

**Câu 9.** Server trả lời trùng ACK cho một retry, client có phải áp dụng kết quả hai lần không?

**Đáp án:** **Không**. Client phải map ACK vào pending request và chỉ hoàn tất một lần; xử lý ACK trùng/đến trễ theo state machine.

**Câu 10.** Nếu ứng dụng phát telemetry mỗi 100 ms, có bắt buộc retry cho đủ từng sample không?

**Đáp án:** **Không**. Dữ liệu có thể hết hạn nhanh; retransmission của sample cũ có thể gây tắc và không còn giá trị. Tùy protocol lựa chọn “latest only” hoặc một transport khác.

**Tiêu chí hoàn thành:** bạn tự chỉ ra được ba lớp **per-receive timeout, application deadline, ACK semantics**; biết chọn request ID và retry giữ nguyên ID; lý giải dedup/idempotency, xử lý ACK sai/cũ, và không tuyên bố “exactly once” chỉ từ UDP.

## 17. Nguồn chuẩn còn áp dụng

- [Java SE 15 – DatagramSocket](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/DatagramSocket.html): `send`, `receive`, `setSoTimeout`, `SocketTimeoutException` và tính chất socket UDP.
- [Java SE 25 – DatagramSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html): hợp đồng hiện hành, timeout không làm đóng socket và hạn chế của `PortUnreachableException`.
- [Java SE 25 – DatagramPacket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html): `getData`, `getOffset`, `getLength`, `getAddress`, `getPort` và remote endpoint.
- [Java SE 25 – System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()): đo elapsed time bằng nguồn thời gian phân giải cao, không dùng như wall-clock timestamp.
- [IETF RFC 768 – User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): UDP là giao thức datagram đơn giản, không có bảo đảm reliability.
- [IETF RFC 8085 – UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): cơ chế reliability khi cần, retransmission, RTT/RTO, exponential backoff, congestion control và duplicate handling; văn bản hiện hành thay RFC 5405.
- [IETF RFC 8899 – Datagram Packetization Layer Path MTU Discovery](https://www.rfc-editor.org/rfc/rfc8899): tránh fragmentation và cân nhắc kích thước gói khi xây protocol UDP.
- [IETF RFC 9000 – QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000): ví dụ giao thức hiện đại đã chuẩn hóa reliability, streams, congestion control và bảo mật trên UDP.
- [IETF RFC 9002 – QUIC Loss Detection and Congestion Control](https://www.rfc-editor.org/rfc/rfc9002): tài liệu chuyên sâu về RTT, timeout, loss recovery và congestion control trong QUIC; không tự sao chép một phần thuật toán mà bỏ toàn bộ context giao thức.

**Ghi nhớ:** UDP không có ACK ở mức `DatagramSocket`. Khi nghiệp vụ cần, **timeout + sequence/request ID + ACK + dedup + retry có kiểm soát** là một thiết kế tầng ứng dụng. **Timeout chỉ có nghĩa chưa biết kết quả**, retry giữ **cùng ID**, còn ACK chỉ có nghĩa đã được **hợp đồng ACK** xác nhận. Với tác vụ nhạy cảm, cần xác thực peer, chống replay, lưu bền trạng thái dedup và cơ chế đối soát, hoặc chọn một protocol sẵn có phù hợp.