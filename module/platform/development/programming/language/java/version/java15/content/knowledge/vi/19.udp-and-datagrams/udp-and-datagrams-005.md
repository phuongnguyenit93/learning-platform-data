# Giới hạn độ tin cậy, thứ tự và nguy cơ trùng gói trong UDP (Java 15+)

> **Chủ đề cha: UDP và datagram.** UDP (*User Datagram Protocol*) là giao thức truyền tải **best-effort theo từng datagram**, không phải một luồng byte đáng tin cậy. `DatagramSocket.send()` thành công **không có nghĩa** bên nhận đã đọc hoặc xử lý gói. UDP **không cam kết** gói đến nơi, đến đúng thứ tự, chỉ đến một lần, hoặc có phản hồi. Nếu ứng dụng cần các đặc tính đó, ứng dụng/giao thức ở tầng trên phải tự xây chúng, hoặc chọn giao thức có bảo đảm phù hợp.

Bài tập trung vào Java API hiện hành (`DatagramSocket`, `DatagramPacket` và các cơ chế tầng ứng dụng), theo tài liệu Java SE hiện đại và IETF RFC 8085. Ba ví dụ độc lập bên dưới dùng Java 17+, chạy trên **loopback** để minh họa rõ ranh giới; không dựa vào hiện tượng mất gói ngẫu nhiên của Internet.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Nêu chính xác giới hạn của UDP: **có thể mất, đến muộn, đến sai thứ tự, hoặc bị lặp**; không có tự động ACK/retransmission/order/dedup.
2. Phân biệt **mỗi lần gọi `send()`**, **một datagram được giao tới socket nhận**, và **một thao tác nghiệp vụ được thực thi**: đây không phải ba sự kiện tương đương.
3. Hiểu tại sao `DatagramSocket.receive()` nhận **một datagram mỗi lần**, không có TCP-style stream, nhưng payload vẫn có thể bị **cắt cụt** khi buffer không đủ.
4. Dùng sequence number, message/request ID, receive window và reorder buffer ở tầng ứng dụng để phát hiện gói trễ/trùng/sai thứ tự.
5. Giải thích ACK, timeout, retry, retry-backoff và tại sao **mất ACK cũng gây retransmission của yêu cầu đã được xử lý**.
6. Đặt idempotency/dedup ở đúng ranh giới nghiệp vụ, không tự khẳng định “exactly once” từ UDP + ACK.
7. Xử lý session/epoch, overflow/wrap của sequence number, giới hạn bộ nhớ, hết hạn cache, replay và kiểm tra danh tính nguồn.
8. Kiểm thử bằng tình huống được **chủ động tạo ra**, không mặc định loopback lúc nào cũng reorder hoặc drop.
9. Biết khi nào nên dùng **TCP/QUIC** thay vì viết một giao thức reliable-UDP mới.

## 2. UDP thực sự cung cấp những gì?

UDP mang **thông điệp riêng lẻ** qua IP. Mỗi datagram có header UDP chứa cổng nguồn, cổng đích, độ dài và checksum; phần payload là một chuỗi byte tùy ứng dụng. Hai lần `send()` thông thường tạo hai datagrams; đây không phải các lần ghi vào cùng một byte stream được TCP nối lại.

Theo chuẩn UDP và hướng dẫn triển khai RFC 8085:

| Thuộc tính | UDP cung cấp? | Hệ quả với ứng dụng |
| --- | --- | --- |
| Địa chỉ IP/cổng gửi–nhận của datagram | Có thông tin transport | Bên nhận biết endpoint báo cáo bởi socket; **không tự chứng thực danh tính** |
| Ranh giới thông điệp (datagram) | Có | Mỗi `receive()` đọc một datagram; không ghép bytes của datagrams như TCP |
| Bảo đảm giao đến nơi | **Không** | Có thể mất, bị loại ở router/firewall/socket buffer |
| Bảo đảm thứ tự gửi–nhận | **Không** | Gói `seq=3` có thể đến trước `seq=2` |
| Chống nhận trùng | **Không** | Có thể nhận nhiều bản sao một thông điệp |
| ACK tự động | **Không** | Muốn xác nhận phải xây ở tầng protocol |
| Tự retransmit khi mất | **Không** | Muốn retry phải thiết kế timeout, dedup, giới hạn retry |
| Flow/congestion control | **Không** | Ứng dụng phải giới hạn tốc độ, backoff và tránh gây nghẽn |
| Bảo vệ tính toàn vẹn cơ bản | Có checksum UDP theo IP/VM và điều kiện protocol | **Không** cung cấp authentication, encryption hay chống giả mạo |
| Connection handshake | **Không** | `DatagramSocket.connect()` không phải bắt tay thiết lập kết nối như TCP |
| Exactly-once business effect | **Không** | Phải thiết kế giao dịch/idempotency theo tầng nghiệp vụ |

**UDP không tự đặt lại thứ tự hoặc xóa trùng.** RFC 8085 mục 3.3 giải thích rằng gói có thể đến trễ đáng kể, reorder và duplicate; một ứng dụng cần thứ tự phải tự khôi phục thứ tự, cần reliable delivery phải xây cơ chế thích hợp.

### 2.1. Ba tầng thường bị nhầm

~~~text
Tầng 1: Sender gọi socket.send(datagram)
    -> Gửi qua API/OS (hoặc phát sinh lỗi gửi)
    -> KHÔNG có xác nhận receiver đã xử lý.

Tầng 2: Receiver gọi socket.receive(packet)
    -> Một datagram được lấy khỏi receive queue
    -> KHÔNG xác nhận parser, service hoặc database đã xử lý thành công.

Tầng 3: Business handler hoàn tất side effect
    -> Ví dụ: ghi database, cộng tiền, tạo đơn hàng.
    -> Nếu ACK bị thất lạc, sender có thể retry và tạo yêu cầu trùng.
~~~

Vì vậy:

- `send()` trở về bình thường **không tương đương** “đã giao thành công”.
- `receive()` không có nghĩa dữ liệu đáng tin hoặc đã được xử lý.
- “Đã gửi một lần” **không tương đương** “bên nhận đã thấy đúng một lần”.
- “Đã nhận ACK” chỉ có ý nghĩa theo **định nghĩa ACK trong protocol**: ACK khi socket nhận? Khi xử lý xong? Khi transaction đã commit? Cần nói rõ.

## 3. Mất gói, đảo thứ tự và nhận trùng đến từ đâu?

### 3.1. Mất gói (loss)

Một datagram có thể không đến được phía nhận vì:

- Queue tại sender/network interface hoặc router bị đầy.
- Congestion, chất lượng mạng radio, mất kết nối tạm thời.
- Firewall, NAT, ACL hoặc quy tắc mạng loại datagram.
- IP fragmentation/reassembly không thành công; **mất một fragment có thể làm mất cả datagram**.
- Receiver quá tải, kernel socket receive buffer đầy.
- Ứng dụng nhận quá chậm hoặc dùng buffer không phù hợp.

Không có cơ chế UDP mặc định tự phát lại datagram. Nếu sender cần biết kết quả, protocol phải tự đặt timeout/ACK/retry, hoặc dùng giao thức đáng tin ở tầng trên.

### 3.2. Sai thứ tự (reordering)

~~~text
Thứ tự gửi:
    [seq=1] ---> [seq=2] ---> [seq=3]

Một thứ tự nhận có thể xảy ra:
    [seq=2] ---> [seq=1] ---> [seq=3]
~~~

Các gói có thể đi qua route khác nhau hoặc bị delay không đều. UDP không chứa số thứ tự chuẩn ở header, nên ứng dụng muốn ordering phải **đưa sequence vào payload** và định nghĩa quy tắc delivery.

Với ứng dụng real-time, đôi khi gói đến muộn **không còn hữu ích**; có thể bỏ gói trễ thay vì chờ để sắp lại mọi thứ. Với dữ liệu có quan hệ thứ tự nghiêm ngặt, cần buffer/retransmit hoặc giao thức cung cấp ordered reliable stream.

### 3.3. Gói trùng (duplication)

Một datagram có thể bị duplicate trên đường truyền, hoặc cùng request được gửi nhiều lần vì **sender retry** sau timeout. Dù mạng không duplicate, chính **cơ chế tăng độ tin cậy do ứng dụng thêm vào** vẫn có thể làm receiver thấy request trùng:

~~~text
Client                 Server
  | ---- request 42 ---> |
  |                      | nhận, commit tác vụ 42
  | <-- ACK 42 -- X      | ACK bị mất / không được gửi
  | ... timeout ...      |
  | ---- request 42 ---> | request 42 xuất hiện lần hai
  |                      | nếu không dedup -> side effect thứ hai
  | <---- ACK 42 --------|
~~~

**Timeout không phân biệt được** “request chưa đến” với “request đã xử lý nhưng ACK không đến”. Đây là lý do phải kết hợp **retry + idempotency/dedup**, không chỉ retry.

### 3.4. Packet được gửi khác với business message

Một logical request có thể tương ứng nhiều datagrams, ví dụ message lớn do protocol tầng trên chia chunk. Ngược lại, một datagram cũng có thể mang một batch gồm nhiều logical events. **ID chống trùng phải được gắn ở đúng đơn vị cần idempotency**, không đơn giản lấy “số lần `send()`” làm business ID.

## 4. Những API Java hiện hành cần biết

| API | Vai trò | Điểm cần lưu ý |
| --- | --- | --- |
| `DatagramSocket` | Socket UDP gửi/nhận datagram | Không tự ACK, retry, order hoặc dedup |
| `DatagramPacket` | Chứa buffer và metadata của một datagram | `getData()` có thể lớn hơn payload thật; đọc `getOffset()` và `getLength()` |
| `DatagramSocket.send(packet)` | Gửi datagram qua socket | Trở về không chứng minh delivery |
| `DatagramSocket.receive(packet)` | Chờ nhận một datagram vào buffer | Nếu datagram dài hơn nhận được, có thể bị **truncate** |
| `DatagramSocket.setSoTimeout(ms)` | Hạn chế thời gian blocking của `receive()` | Hết hạn ném `SocketTimeoutException`, socket vẫn dùng được |
| `InetSocketAddress` | Địa chỉ IP + cổng | Không phải authenticated identity |
| `InetAddress.getLoopbackAddress()` | Endpoint local cho thử nghiệm | Giảm nhiễu mạng, **không mô phỏng loss/reorder thực tế** |
| `ByteBuffer` | Serialize/parse sequence number và trường nhị phân | Thống nhất endian/format trong protocol |
| `DatagramChannel` | NIO API cho datagram/network selector | Cũng không tự biến UDP thành reliable transport |

### 4.1. Một send có thể thất bại hoặc thành công mà remote không nhận

~~~java
// Đoạn minh họa; socket/target/payload đã được tạo.
socket.send(new DatagramPacket(payload, payload.length, target));
~~~

Thành công của lời gọi chứng minh một bước trong **local I/O path** đã hoàn thành, không chứng minh remote process còn chạy, nhận được datagram hoặc đã commit database. Lỗi mạng có thể được báo theo cách phụ thuộc OS/network, hoặc không báo về sender ở thời điểm gửi.

### 4.2. Timeout là sự kiện của socket nhận, không phải bằng chứng đã mất

~~~java
// Đoạn mã minh họa trong phương thức, chưa phải một chương trình.
socket.setSoTimeout(500);
try {
    socket.receive(packet);
} catch (java.net.SocketTimeoutException ex) {
    // Trong 500 ms không lấy được datagram đáp ứng điều kiện nhận.
    // Chưa biết remote request đã xử lý hay chưa!
}
~~~

`receive()` timeout **không đóng socket**. Nhưng không nên retry vô hạn với khoảng cách cực ngắn; retry không kiểm soát có thể tăng congestion và làm tỷ lệ mất gói tệ hơn.

### 4.3. `connect()` trên UDP không biến nó thành TCP

`DatagramSocket.connect(remote)` đặt default destination cho việc gửi và liên quan lọc datagrams nhận theo endpoint. Nó **không thiết lập TCP-style handshake**, không chứng thực remote tồn tại, không tạo stream reliable, không bảo đảm thứ tự hay chỉ nhận một lần.

Nếu ứng dụng cần xác thực sender, đừng dùng “đã connect UDP” như một bằng chứng danh tính. Dùng một protocol có authentication/integrity phù hợp (ví dụ DTLS hoặc QUIC khi yêu cầu tương ứng), và vẫn phân biệt authentication với authorization.

## 5. Ví dụ 1 — Nhận dữ liệu sai thứ tự và trùng: sắp thứ tự ở tầng ứng dụng

Ví dụ sẽ **chủ động gửi** các sequence theo thứ tự `2, 1, 2, 4, 3`. Mục đích là kiểm tra **logic receiver khi input có thứ tự này**, **không khẳng định loopback/UDP tự làm gói đảo thứ tự**. Để stdout có thể kiểm thử, chương trình gửi một datagram rồi nhận đúng một datagram, lặp lại.

Receiver quy ước:
- Muốn deliver từ sequence `1` trở lên theo thứ tự.
- Gói có sequence chưa đến lượt được đưa vào `TreeMap` chờ.
- Khi nhận được gói lấp gap, deliver liên tiếp những sequence đang có.
- Gói có sequence thấp hơn `next` hoặc đang có trong pending map là duplicate.

### 5.1. Mã đầy đủ — `UdpOrderDuplicateDemo.java`

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.TreeMap;
import java.util.StringJoiner;

public class UdpOrderDuplicateDemo {
    record Message(int sequence, String text) {}

    static byte[] encode(int sequence, String text) {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + body.length)
                .putInt(sequence).put(body).array();
    }

    static Message decode(DatagramPacket packet) {
        if (packet.getLength() < 4) {
            throw new IllegalArgumentException("Missing sequence");
        }
        int sequence = ByteBuffer.wrap(
                packet.getData(), packet.getOffset(), 4).getInt();
        String text = new String(packet.getData(),
                packet.getOffset() + 4, packet.getLength() - 4,
                StandardCharsets.UTF_8);
        return new Message(sequence, text);
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getLoopbackAddress();

        try (DatagramSocket receiver = new DatagramSocket(
                     new InetSocketAddress(local, 0));
             DatagramSocket sender = new DatagramSocket(
                     new InetSocketAddress(local, 0))) {

            receiver.setSoTimeout(2000);
            int[] sequence = {2, 1, 2, 4, 3};
            String[] text = {"two", "one", "two", "four", "three"};
            Map<Integer, String> pending = new TreeMap<>();
            int next = 1;

            for (int i = 0; i < sequence.length; i++) {
                byte[] bytes = encode(sequence[i], text[i]);
                sender.send(new DatagramPacket(
                        bytes, bytes.length, local,
                        receiver.getLocalPort()));

                // One send, then one receive: input order is controlled.
                DatagramPacket packet =
                        new DatagramPacket(new byte[128], 128);
                receiver.receive(packet);
                Message m = decode(packet);

                if (m.sequence() < next ||
                        pending.containsKey(m.sequence())) {
                    System.out.println("recv=" + m.sequence()
                            + " duplicate");
                    continue;
                }

                pending.put(m.sequence(), m.text());
                StringJoiner delivered = new StringJoiner(",");
                while (pending.containsKey(next)) {
                    pending.remove(next);
                    delivered.add(Integer.toString(next));
                    next++;
                }

                if (delivered.length() == 0) {
                    System.out.println("recv=" + m.sequence()
                            + " buffered");
                } else {
                    System.out.println("recv=" + m.sequence()
                            + " delivered=" + delivered);
                }
            }
            System.out.println("complete=" +
                    (next == 5 && pending.isEmpty()));
        }
    }
}
~~~

**Biên dịch và chạy từ thư mục chứa file:** 

~~~bash
javac --release 17 -encoding UTF-8 UdpOrderDuplicateDemo.java
java UdpOrderDuplicateDemo
~~~

**Stdout đã kiểm chứng trên JDK 24, loopback:**

~~~text
recv=2 buffered
recv=1 delivered=1,2
recv=2 duplicate
recv=4 buffered
recv=3 delivered=3,4
complete=true
~~~

### 5.2. Phân tích chi tiết

**`recv=2 buffered`:** Receiver muốn `next=1`, nhưng nhận `seq=2`. Nó **không deliver** gói `2` ngay; giữ trong map. Đây là chính sách của ứng dụng, không phải đặc tính UDP.

**`recv=1 delivered=1,2`:** Khi `1` đến, gap được lấp; receiver có thể deliver `1` rồi `2` theo thứ tự.

**`recv=2 duplicate`:** `2` đã được deliver, nên lần xuất hiện sau bị bỏ. Một ứng dụng làm “đặt hàng”, “chuyển tiền” hoặc “ghi event” có thể tránh lặp side effect nhờ ID/dedup tương ứng.

**`recv=4 buffered`:** `3` vẫn thiếu. Chờ vô hạn sẽ gây *head-of-line blocking do ứng dụng tự tạo*. Trong production phải có timeout, chính sách xử lý gap, giới hạn bộ đệm và yêu cầu retransmit nếu có.

**`recv=3 delivered=3,4`:** Gói `3` tới, chuỗi được giải phóng theo thứ tự. `complete=true` là tình trạng **đầu vào đã được chủ động cấp đủ `1..4` trong ví dụ**, không phải UDP mặc nhiên bảo đảm mọi gói sẽ đến.

### 5.3. Những giới hạn cố ý của demo

- Không có truyền dữ liệu qua Internet; loopback chỉ giúp học dễ chạy. Chương trình **cố ý chọn thứ tự gửi** không phải đo route thực tế.
- Chưa xác thực sender, chưa có session ID, sequence-wrap handling, TTL, receive-window/max-memory, rate limiting hoặc checksum application-level.
- `ByteBuffer` mặc định dùng big-endian. Nếu client/server ở nhiều ngôn ngữ, phải quy định rõ thứ tự byte của `sequence`.
- Chưa validate `sequence` âm, quá lớn hoặc payload không hợp lệ. Production nên reject hoặc quarantine input sai protocol trước khi cấp phát buffer.
- Việc chỉ so `seq < next` hợp lý trong một session đơn giản, nhưng không được dùng trực tiếp với bộ đếm int sẽ wrap sau nhiều gói.
- `Map<Integer,String>` chỉ nằm trong RAM, phù hợp ví dụ ordering; không phải dedup database bền vững cho business effect.

## 6. Thiết kế ordering: sequence, window, gap và late arrival

### 6.1. Các trường nên có trong protocol

Ví dụ một application-level datagram format:

~~~text
version             1 byte
messageType         1 byte
sessionId          16 bytes (hoặc ID có độ duy nhất tương đương)
sequenceNumber      8 bytes unsigned / counter do protocol quy định
requestId          16 bytes nếu một business action cần idempotency
payloadLength       4 bytes với bounds check
payload             bytes
authenticationTag   tùy cơ chế bảo mật (không tự tạo crypto)
~~~

Đây là **mô hình minh họa**, chưa phải một chuẩn wire format. Kích thước được chọn theo ứng dụng; nếu đổi thành production protocol, cần đặc tả endian, phiên bản, quyền truy cập và nguồn tạo ID.

`sessionId` giúp tách sequence của các phiên khác nhau. `sequenceNumber` giúp sắp thứ tự datagrams; `requestId` gắn với **business operation** để chống thực thi trùng. Một message chia thành nhiều datagrams còn cần `messageId` và chunk indexes riêng.

### 6.2. Không để reorder buffer vô hạn

Một receiver ngây thơ chỉ làm `pending.put(seq, payload)` và chờ đến khi nhận mọi seq nhỏ hơn có thể:
- Giữ bộ nhớ vô hạn khi một gap không bao giờ được lấp.
- Bị một sender độc hại gửi sequence rất lớn làm tăng tài nguyên.
- Bị kẹt không deliver dữ liệu còn hữu ích vì một gói lỗi thời.
- Bị duplicate của một gói bị từ chối lặp lại vô hạn.

Một design thực tế nên có:
1. **Window giới hạn:** Chỉ nhận `next ≤ seq < next+windowSize` sau khi xử lý an toàn overflow/wrap.
2. **TTL/gap timeout:** Sau khoảng phù hợp, chọn retransmit, skip hoặc fail session tùy nghiệp vụ.
3. **Giới hạn tổng bytes và số datagrams:** Không chỉ giới hạn số entry trong map.
4. **Tách session/epoch:** Tránh gói từ session cũ bị nhận nhầm ở session mới.
5. **Dedupe cả pending lẫn delivered:** Gói trùng trước hoặc sau khi deliver đều không gây lặp tác vụ.
6. **Cảnh báo vận hành:** Reorder rate, missing gaps, queue depth, age of oldest gap, rejects.
7. **Giới hạn tốc độ và xác thực nguồn:** Tránh sender không đáng tin chiếm bộ nhớ CPU.

### 6.3. Sequence wrap-around

Một số thứ tự `int` Java có dấu sẽ wrap sau `Integer.MAX_VALUE`. Nếu ứng dụng truyền một counter unsigned trên wire:
- Không so đơn giản `seq < next` khi có thể wrap.
- Chọn độ dài counter và thời gian sống session phù hợp; có quy tắc modular arithmetic đã được xem xét.
- Chặn reuse/replay ID cũ trong cùng epoch.
- Nếu cần reset sequence, tạo `sessionId/epoch` mới theo protocol và có xác thực phù hợp.

Với những bài toán dài hạn, dùng `long`/unsigned encoding và session epoch có thể đơn giản hơn, nhưng **không có kiểu số nguyên nào thay thế policy về sequence reuse**.

### 6.4. Khi nào có thể bỏ gói trễ?

Trong streaming audio/video, telemetry theo thời gian thực hoặc state snapshots:
- Một trạng thái mới có thể thay thế trạng thái cũ.
- Gói đến quá muộn đôi khi nên bị drop để tránh tăng latency.
- Không nhất thiết phải đòi tất cả datagrams đi qua ordered queue.

Trong audit log/ledger/các bước nghiệp vụ phụ thuộc thứ tự:
- Bỏ gói có thể tạo lỗ hổng logic; cần phục hồi hoặc giao thức reliably ordered.
- TCP hay QUIC reliable stream thường là lựa chọn tự nhiên hơn tự viết một reliable UDP protocol.

Không có một chính sách ordering chung cho mọi ứng dụng; lựa chọn phải xuất phát từ semantics nghiệp vụ.

## 7. ACK, timeout và retransmission: vì sao tạo ra nguy cơ trùng

UDP không tạo ACK. Muốn sender biết request đã nhận/xử lý, protocol phải định nghĩa gói ACK riêng.

Một flow thường gặp:

~~~text
Request:
    sessionId + requestId + payload + auth
Receiver:
    validate request / replay policy / authorization
    dedup requestId
    execute business action nếu chưa từng xử lý
    store outcome nếu cần
    send ACK(requestId, status/outcome)
Sender:
    wait bounded duration for ACK matching expected peer/session/requestId
    if timeout: maybe retry with backoff, stop after limits
~~~

Cần phân biệt **ACK đã nhận datagram** với **ACK đã commit side effect**. Nếu ACK gửi quá sớm trước khi commit, sender có thể nghĩ request thành công dù server crash. Nếu ACK sau commit bị mất, sender sẽ retry một request đã commit. Vì vậy chính sách ACK và data durability phải đồng bộ với requirements.

### 7.1. Stop-and-wait chỉ là một phương án

Stop-and-wait gửi một request, chờ ACK rồi mới gửi tiếp. Nó dễ hiểu nhưng utilization kém khi RTT cao. Nếu dùng sliding window/multiple outstanding requests, phải quản lý:
- Thứ tự request và ACK, cumulative/selective ACK nếu protocol cần.
- Timeout theo RTT, retry count, exponential backoff + jitter.
- Giới hạn window, bytes-in-flight và congestion control.
- Dedupe giữa các lần gửi lại, giữa các client/instance/session.
- Khả năng ACK bị trùng, đến muộn hoặc bị giả mạo.
- Trường hợp sender crash/restart giữa các bước.

**Không có thuật toán retransmission nào tự bảo đảm exactly-once business effect** nếu không quản lý state ở tầng nghiệp vụ.

## 8. Ví dụ 2 — ACK không được gửi, client timeout và retry làm server nhận trùng

Ví dụ sau cố ý mô phỏng trường hợp ACK của lần gửi đầu **không được phát ra**. Đây là lỗi được **chủ động điều khiển** ở tầng ứng dụng, không khẳng định rằng đường truyền loopback thật sự đánh rơi ACK. Client thấy timeout, gửi lại đúng cùng request ID; server suppress duplicate và ACK lần sau.

### 8.1. Mã đầy đủ — `UdpAckRetryDemo.java`

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

public class UdpAckRetryDemo {
    record Request(String id, String action) {}

    static void send(DatagramSocket socket, InetSocketAddress target,
                     String message) throws Exception {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        socket.send(new DatagramPacket(bytes, bytes.length, target));
    }

    static DatagramPacket receive(DatagramSocket socket) throws Exception {
        DatagramPacket packet =
                new DatagramPacket(new byte[256], 256);
        socket.receive(packet);
        return packet;
    }

    static String text(DatagramPacket packet) {
        return new String(packet.getData(),
                packet.getOffset(), packet.getLength(),
                StandardCharsets.UTF_8);
    }

    static Request parse(String wire) {
        String[] fields = wire.split("\\|", -1);
        if (fields.length != 2 || fields[0].isBlank()) {
            throw new IllegalArgumentException("Invalid request");
        }
        return new Request(fields[0], fields[1]);
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getLoopbackAddress();
        try (DatagramSocket server = new DatagramSocket(
                    new InetSocketAddress(local, 0));
             DatagramSocket client = new DatagramSocket(
                    new InetSocketAddress(local, 0))) {

            server.setSoTimeout(2000);
            client.setSoTimeout(150);
            InetSocketAddress serverEndpoint =
                    new InetSocketAddress(local, server.getLocalPort());

            Set<String> processedIds = new HashSet<>();
            int effects = 0;

            send(client, serverEndpoint, "42|publish");
            DatagramPacket first = receive(server);
            Request one = parse(text(first));
            if (processedIds.add(one.id())) {
                effects++;
            }
            System.out.println("firstRequestApplied=" + (effects == 1));

            // Deliberate simulation: server omits first ACK.
            boolean timedOut = false;
            try {
                receive(client);
            } catch (SocketTimeoutException expected) {
                timedOut = true;
            }
            System.out.println("firstAckTimedOut=" + timedOut);

            send(client, serverEndpoint, "42|publish");
            DatagramPacket second = receive(server);
            Request two = parse(text(second));
            boolean duplicate = !processedIds.add(two.id());
            if (!duplicate) {
                effects++;
            }
            System.out.println("duplicateSuppressed=" + duplicate);

            send(server, new InetSocketAddress(
                    second.getAddress(), second.getPort()), "ACK:42");
            DatagramPacket ack = receive(client);
            boolean matched = "ACK:42".equals(text(ack))
                    && ack.getAddress().equals(local)
                    && ack.getPort() == server.getLocalPort();

            System.out.println("ackMatchedEndpointAndId=" + matched);
            System.out.println("businessEffectCount=" + effects);
        }
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac --release 17 -encoding UTF-8 UdpAckRetryDemo.java
java UdpAckRetryDemo
~~~

**Stdout đã kiểm chứng trên JDK 24 với loopback:**

~~~text
firstRequestApplied=true
firstAckTimedOut=true
duplicateSuppressed=true
ackMatchedEndpointAndId=true
businessEffectCount=1
~~~

### 8.2. Ý nghĩa từng dòng

- `firstRequestApplied=true`: Server đã nhận và thực thi logic giả lập ở lần đầu.
- `firstAckTimedOut=true`: Client chưa nhận ACK trong `150 ms` vì **server cố ý không gửi ACK**. Điều này không cho client biết request đã được xử lý.
- `duplicateSuppressed=true`: Client gửi lại request ID `42`, nhưng server nhìn thấy `processedIds` đã chứa `42`.
- `ackMatchedEndpointAndId=true`: ACK mà client đọc đúng endpoint IP/port và request ID theo format mô phỏng. **Điều này không phải xác thực mật mã**; IP/port và text có thể bị giả mạo trong threat model thực tế.
- `businessEffectCount=1`: Gói request đến server hai lần nhưng logic giả lập chỉ tăng side effect một lần.

**Cảnh báo quan trọng:** `HashSet` tồn tại trong RAM của một process và một thread, **không phải cơ chế exactly-once production**. Sau restart, cache mất; trên nhiều server nodes, chúng có thể có state khác nhau. Không thể dùng mỗi `HashSet.add(id)` để bảo vệ thao tác chuyển tiền/ghi đơn hàng thực sự.

### 8.3. Thiết kế idempotency bền vững

Một dịch vụ nghiệp vụ có thể cần:
1. Mỗi operation có **requestId** đủ duy nhất trong phạm vi principal/tenant/session phù hợp, và giữ cùng ID khi retry.
2. Xác thực sender/authorization **trước** khi sử dụng ID như quyền truy cập kết quả cũ.
3. Lưu record `(principal, requestId, payloadHash, state, result)` trong database.
4. Dùng **unique constraint hoặc compare-and-insert atomic** để chỉ một worker giành quyền thực hiện.
5. Đảm bảo side effect và trạng thái idempotency được commit nhất quán, tốt nhất cùng transaction nếu khả thi; nếu có external side effect, cần transactional outbox/saga/reconciliation phù hợp.
6. Nếu cùng requestId nhưng payload khác, từ chối thay vì trả kết quả của request cũ một cách tùy tiện.
7. Với request đã hoàn thành, trả lại **stored outcome** cho retry hợp lệ.
8. Có retention/TTL đủ dài theo khoảng retry/replay hợp lệ; sau khi hết TTL phải có chính sách xử lý request cũ.
9. Giới hạn bộ nhớ/disk và chống kẻ tấn công flood request IDs.
10. Chấp nhận rằng nếu ACK hoặc dữ liệu bị mất mãi, client có thể không bao giờ nhận được kết quả cuối; thiết kế API query status/reconciliation khi phù hợp.

### 8.4. Vì sao “at-most-once” và “at-least-once” không giống exactly-once?

| Mô hình | Đặc điểm | Nguy cơ |
| --- | --- | --- |
| **At-most-once attempt** | Gửi một lần, không retry | Có thể **không thực thi lần nào** nếu mất |
| **At-least-once attempt** | Retry cho đến điều kiện dừng / ACK | Có thể thực thi **nhiều lần** nếu không dedup |
| **At-most-once business effect** | Dedupe/transaction bảo vệ side effect | Vẫn có thể không có kết quả nếu request không bao giờ đến |
| **Exactly-once effect (theo phạm vi đã định nghĩa)** | Application transaction/idempotency bảo đảm chỉ có một side effect hợp lệ cho một operation ID | Không tự có nhờ UDP; phải định nghĩa phạm vi, durability, failures và reconciliation |

Một hệ thống có thể mô phỏng hành vi exactly-once **ở tầng business transaction** trong các giả định rõ ràng, nhưng không thể khẳng định transport UDP “giao đúng một lần” trên mạng không đáng tin.

## 9. Duplicate detection: chọn khóa và giữ state đúng

Chống trùng “chỉ bằng sequence number” có nhiều bẫy:

- **Sequence thuộc một session**; session mới có thể bắt đầu lại từ `1`. Phải phân biệt `sessionId + sequence`.
- **Request ID thuộc operation**; một operation có thể bao gồm nhiều datagrams/chunks.
- Sender có thể reset counter khi restart, dẫn đến collision nếu thiếu epoch.
- Các client khác nhau có thể dùng cùng số `42`; cần scope bằng principal/tenant đã xác thực.
- Nếu dùng timestamp làm ID duy nhất, clock skew và collision có thể gây nhận nhầm.
- Khi cache bị dọn hoặc server restart, request cũ có thể được gửi lại; yêu cầu durability theo nghiệp vụ quyết định TTL.
- Nếu attacker biết requestId và có thể tạo packet, dedup có thể bị dùng để chặn request hợp lệ; phải gắn ID với authenticated identity và payload.
- Retry từ client có thể đến qua endpoint khác do NAT rebinding; chỉ dùng IP:port làm identity hoặc dedup key là không an toàn.
- Không nên coi hai messages có payload bytes giống nhau là “trùng” nếu chúng là **hai business operations khác nhau**. Dùng explicit operation ID.
- Nếu có nhiều consumer, phải bảo đảm check-and-set **atomic across nodes** hoặc phân hoạch routing nhất quán.

**Quy tắc thực dụng:** Dùng một ID có nghĩa nghiệp vụ, có scope và vòng đời, được kiểm tra cùng nội dung đã xác thực; dùng database transaction khi cần bảo đảm effect, không chỉ cấu trúc dữ liệu trong RAM.

## 10. Một datagram, một `receive()`: vẫn có nguy cơ cắt cụt

UDP giữ **ranh giới datagram**, khác stream của TCP. Nhưng receiver phải cấp buffer đủ lớn. Nếu datagram dài hơn độ dài mà `DatagramPacket` cho phép nhận, **phần vượt quá có thể bị cắt bỏ**, không trở thành “phần tiếp theo” của một lần `receive()` sau.

### 10.1. Ví dụ 3 — Datagram dài hơn buffer

**Tệp `UdpDatagramBoundaryDemo.java` — độc lập Java 17+:**

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class UdpDatagramBoundaryDemo {
    static void send(DatagramSocket socket, InetAddress host,
                     int port, String message) throws Exception {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        socket.send(new DatagramPacket(
                bytes, bytes.length, host, port));
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getLoopbackAddress();

        try (DatagramSocket receiver = new DatagramSocket(
                    new InetSocketAddress(local, 0));
             DatagramSocket sender = new DatagramSocket(
                    new InetSocketAddress(local, 0))) {

            receiver.setSoTimeout(2000);
            byte[] buffer = new byte[8];
            DatagramPacket incoming =
                    new DatagramPacket(buffer, buffer.length);

            send(sender, local, receiver.getLocalPort(),
                    "ABCDEFGHIJKL");
            receiver.receive(incoming);
            System.out.println("firstLength=" +
                    incoming.getLength());
            System.out.println("firstData=" + new String(
                    incoming.getData(), incoming.getOffset(),
                    incoming.getLength(), StandardCharsets.UTF_8));

            // Reset capacity before reusing an incoming DatagramPacket.
            incoming.setLength(buffer.length);
            send(sender, local, receiver.getLocalPort(), "OK");
            receiver.receive(incoming);
            System.out.println("secondLength=" +
                    incoming.getLength());
            System.out.println("secondData=" + new String(
                    incoming.getData(), incoming.getOffset(),
                    incoming.getLength(), StandardCharsets.UTF_8));
        }
    }
}
~~~

**Chạy:**

~~~bash
javac --release 17 -encoding UTF-8 UdpDatagramBoundaryDemo.java
java UdpDatagramBoundaryDemo
~~~

**Stdout đã kiểm chứng trên JDK 24 loopback:**

~~~text
firstLength=8
firstData=ABCDEFGH
secondLength=2
secondData=OK
~~~

Giải thích:
- `"ABCDEFGHIJKL"` dài **12 bytes** UTF-8 ASCII, nhưng buffer chỉ dài **8 bytes**, nên receiver chỉ đọc `ABCDEFGH`.
- Phần `IJKL` **không xuất hiện ở lần receive sau**; datagram đầu đã được tiêu thụ và phần dư bị loại.
- Lần receive thứ hai trả `OK`, tức datagram thứ hai.
- `getLength()` mô tả số bytes đã nhận vào buffer, **không chỉ ra kích thước gốc khi truncation**.
- Khi tái sử dụng `DatagramPacket`, gọi `setLength(buffer.length)` để đặt lại độ dài nhận tối đa cho lần tiếp theo; hoặc tạo `DatagramPacket` mới mỗi lần như ví dụ 1/2.

**Nếu ứng dụng yêu cầu toàn bộ message không được cắt:** Định nghĩa max datagram payload của protocol, cấp đủ receive buffer, validate length/schema, và nếu cần nhận message lớn thì sử dụng **framing/fragmentation/reassembly ở tầng phù hợp hoặc giao thức khác**. Đừng assume một `new byte[1024]` luôn đủ cho mọi datagram.

## 11. Kích thước datagram, MTU và loss amplification

Mỗi UDP datagram được đưa vào IP. Kích thước thực tế có thể bị hạn chế bởi:
- UDP header (8 bytes).
- IPv4/IPv6 header và extension/option headers.
- Path MTU (kích thước packet phù hợp trên đường truyền).
- Các tunnel/VPN/encapsulation có overhead riêng.
- Cấu hình mạng, router và firewall.

Một datagram đủ nhỏ có thể đi trong một IP packet; datagram quá lớn có thể cần fragmentation hoặc bị drop nếu không thể gửi theo path MTU. Nếu một datagram bị chia thành nhiều IP fragments, **mất một fragment có thể làm mất toàn bộ datagram**, vì UDP chỉ chuyển dữ liệu hoàn chỉnh lên ứng dụng sau reassembly thành công.

### 11.1. Đừng chọn một “kích thước an toàn tuyệt đối” cho Internet

Ví dụ Ethernet MTU `1500` cho ra phép tính sơ bộ:
- IPv4 header tối thiểu 20 + UDP header 8 => payload ≈ `1472` bytes nếu không có IP options/tunnel.
- IPv6 header cơ bản 40 + UDP header 8 => payload ≈ `1452` bytes nếu không có extension headers/tunnel.

Đó **không** phải lời bảo đảm trên mọi đường truyền. Path có thể có MTU nhỏ hơn và overhead khác; cần cách chọn message size theo protocol, Path MTU Discovery/PLPMTUD khi thích hợp, và kiểm soát fallback. RFC 8085 khuyến nghị hạn chế phụ thuộc vào IP fragmentation.

### 11.2. Nếu tự chia một logical message thành nhiều datagrams

Ứng dụng phải làm thêm những việc trước đó UDP không có:
1. Chia message thành `messageId + partIndex + partCount + bytes`.
2. Kiểm tra length, index, count và tổng dung lượng, tránh overflow/tràn bộ nhớ.
3. Thu gom parts theo `(authenticated sender/session, messageId)`.
4. Có deadline/reassembly timeout và giới hạn số message đang chờ.
5. Xử lý part bị mất, đến sai thứ tự, trùng hoặc lẫn với session khác.
6. Quy định ACK hoặc selective retry nếu reliability thật sự cần.
7. Chỉ parse/commit payload đầy đủ đã được integrity/authentication check theo protocol.

Không nên tự viết một tầng fragmentation không có giới hạn rồi cho đối tượng mạng không tin cậy cấp phát số lượng parts tùy ý.

## 12. Retransmission phải đi cùng congestion control

Một thiết kế kiểu “mỗi 10 ms nếu chưa có ACK thì gửi lại mãi” có thể gây hại:
- Khi mạng congested, packet loss tăng.
- Sender hiểu loss là lý do retry nhanh hơn.
- Lưu lượng retry tăng khiến congestion tệ hơn, tạo vòng lặp tự khuếch đại.

RFC 8085 nhấn mạnh UDP **không có congestion control tích hợp**; ứng dụng Internet cần có chính sách kiểm soát tốc độ và tránh gây unfairness/congestion collapse.

Các thực hành hiện đại:
- Giới hạn **in-flight requests**, số retry và tổng thời gian.
- Dùng timeout dựa trên RTT/observed variance thay vì giá trị cực nhỏ cố định.
- Dùng **backoff có jitter**; tránh tất cả clients retry đồng thời.
- Dùng pacing/rate limiting/bandwidth budgeting.
- Giảm tải khi thấy loss/congestion, đừng bơm vô hạn.
- Với workload mạng công cộng, ưu tiên giao thức đã có congestion control thay vì sáng chế một giao thức hoàn toàn mới.
- Theo dõi `sent, received, timed out, retried, duplicates, RTT, reordered, dropped` cùng thời gian/endpoint để phát hiện vấn đề.

**Chú ý:** Retry không phải điều tất yếu. Trong telemetry hoặc cập nhật real-time, **bỏ mẫu cũ để nhận mẫu mới** có thể tốt hơn retry; điều đó phải là quyết định từ use case.

## 13. Bảo mật: UDP không chứng thực người gửi hoặc chống replay

`DatagramPacket.getAddress()` và `getPort()` trả endpoint được gắn với gói nhận, nhưng IP/port **không phải bằng chứng mật mã về danh tính**. Tùy mạng, attacker có thể giả mạo nguồn, thay đổi route, lợi dụng NAT rebinding, replay datagrams hoặc flood receiver.

Nếu hệ thống xử lý dữ liệu quan trọng:
- Dùng cơ chế **authentication + integrity** đã được thiết kế chuẩn (DTLS/QUIC hoặc cơ chế thích hợp do protocol quy định), không tự chế crypto.
- Gắn `sessionId`, `requestId`, nonce/sequence và các trường an ninh vào dữ liệu được xác thực.
- Xác định principal có quyền gửi, và action/resource được phép.
- Giới hạn request size, buffer, rate và số IDs đang chờ.
- Kiểm tra ID trùng **theo authenticated principal**, không chỉ IP:port.
- Chặn datagram malformed trước khi xử lý tốn tài nguyên.
- Không dùng một ACK text như `"ACK:42"` trong ví dụ để xác thực một tác vụ tài chính.
- Nếu sử dụng reflection/logging, tránh log token/secret/payload nhạy cảm của người dùng.
- Đặt độ dài và giới hạn cho các chuỗi deserialize để tránh memory exhaustion.

**UDP checksum không phải MAC hoặc chữ ký số.** Nó giúp phát hiện hỏng dữ liệu trong điều kiện protocol, không chứng minh sender đáng tin hay chống phát lại.

## 14. Kiểm thử loss, reorder và duplicate thế nào cho đáng tin?

Không nên viết unit test:
> “Gửi 10 UDP datagrams qua loopback, chắc chắn một gói sẽ mất hoặc đảo thứ tự.”

Loopback thường rất ổn định. Việc môi trường không tự tạo loss/reorder **không** chứng minh UDP bảo đảm thứ tự hay độ tin cậy.

### 14.1. Tách ba loại test

| Loại test | Cách kiểm | Mục tiêu |
| --- | --- | --- |
| **Pure unit test của reorder/dedupe logic** | Gọi trực tiếp state machine với input `2,1,2,4,3` | Test logic deterministic, không phụ thuộc OS/network |
| **Loopback integration test** | Dùng `DatagramSocket` thực, tạo thứ tự đầu vào và tình huống ACK omit có chủ đích | Kiểm serialization, receive, timeout, ACK và đóng socket |
| **Fault-injection/network emulation test** | Proxy/network emulator có loss/delay/duplicate/reorder có kiểm soát trong môi trường cô lập | Test recovery, retry/backoff, timers và congestion behavior |

Phép thử phải ghi rõ mình **tạo ra** lỗi ở layer nào. Một “ACK mất” do server cố ý không gửi khác việc network thật đánh rơi ACK; cả hai có thể dẫn tới cùng hành vi client timeout.

### 14.2. Ma trận negative tests nên có

| Input/sự kiện | Kết quả mong đợi |
| --- | --- |
| Gói `1,2,3` đến đủ | Deliver đúng thứ tự, không trùng |
| Gói `2,1,3` | Buffer `2`, deliver `1,2,3` |
| `1,1,2` | Bỏ duplicate `1`, side effect một lần |
| `3` đến, `1` và `2` không bao giờ đến | Không chờ vô hạn; áp dụng gap timeout/window policy |
| Request đã commit nhưng ACK không đến | Client có thể retry; receiver dedup và trả lại outcome |
| ACK cũ cho requestId khác | Sender không chấp nhận ACK cũ |
| Cùng requestId nhưng payload khác | Từ chối collision/mismatch theo protocol |
| Sender reset counter nhưng không reset session | Không được nhập nhầm gói cũ vào session mới |
| Sequence rất lớn hoặc âm | Reject ngoài receive window, không giữ memory vô hạn |
| Datagram dài hơn receive buffer | Truncated theo API; không coi payload rút gọn là thông điệp đủ |
| Duplicate đến sau TTL của cache | Có chính sách rõ để tránh side effect lặp lại trong cửa sổ nguy hiểm |
| Bên gửi không xác thực gửi ACK giả | Không được coi là xác nhận nghiệp vụ |
| Link nghẽn/retry nhiều | Retry giới hạn/backoff; không tạo flood hoặc tăng tải vô hạn |
| Socket `receive()` timeout | Service phân loại timeout; không giả định remote đã thất bại |

### 14.3. Test về exactly-once business effect

Đặt một database với unique key `(tenantId, requestId)`. Trong một test được cô lập:
- Cho hai/ba worker đồng thời nhận cùng request ID.
- Bảo đảm chỉ **một** transaction được phép commit side effect.
- Nếu worker crash sau commit nhưng trước ACK, retry phải nhận được stored outcome mà không chạy effect thêm lần nữa.
- Nếu requestId trùng với payload khác, reject và ghi cảnh báo, không silently reuse.
- Thử restart database/service theo policy và kiểm retention, không chỉ test trong RAM.

Một integration test loại này bảo vệ tính đúng của nghiệp vụ tốt hơn việc chỉ assert số UDP packets nhận.

## 15. Khi nào chọn UDP và khi nào không?

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Telemetry có thể mất một vài mẫu, mẫu mới thay mẫu cũ | UDP có thể phù hợp với validation/rate limit |
| Truyền media real-time có cơ chế riêng cho jitter, FEC, sequence và congestion | UDP qua protocol được thiết kế cho use case |
| Giao dịch cần reliable ordered byte stream đơn giản | TCP thường dễ hơn |
| Multiplexed streams đáng tin cậy, bảo mật và congestion control hiện đại | QUIC qua UDP, dùng implementation chuẩn |
| Bản tin UDP không đáng tin nhưng cần bảo mật transport | DTLS hoặc giao thức được tiêu chuẩn hóa tương ứng |
| Truyền thao tác tài chính cần idempotency/durable outcome | Dù dùng TCP/QUIC, vẫn phải có business idempotency và authorization |
| Application đòi datagrams không cần retransmit nhưng có session/security | Có thể dùng QUIC DATAGRAM nếu protocol/implementation hỗ trợ, song delivery vẫn không được bảo đảm |

Không có nghĩa “UDP luôn nhanh hơn TCP”. UDP có overhead nhỏ và không có connection setup, nhưng độ trễ hữu ích phụ thuộc loss, congestion, lượng retry, path MTU, bảo mật và workload. Xây lại ACK/retry/ordering từ đầu có thể vừa tốn công vừa khó đúng hơn sử dụng giao thức đáng tin đã được kiểm chứng.

## 16. Lỗi phổ biến

| Nhầm lẫn | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| `send()` không ném lỗi nên remote chắc chắn nhận | UDP không ACK delivery | Dùng protocol-level ACK nếu cần, hiểu giới hạn |
| `receive()` timeout nghĩa là request chưa xử lý | ACK có thể mất dù server đã commit | Retry với idempotency ID và durable state |
| UDP tự bảo đảm giữ đúng thứ tự | Không có sequence/order trong UDP header | Sequence và reorder policy ở tầng trên |
| UDP không bao giờ nhận duplicate | Có thể duplicate trên đường truyền hoặc do retry | Dedup requestId/sequence đúng phạm vi |
| Retry vô hạn mà không giới hạn tốc độ | Có thể gây congestion collapse | Backoff, jitter, rate limiting và retry budget |
| Dùng IP:port làm danh tính chắc chắn | NAT/rebinding/spoofing | Authentication và principal-bound ID |
| Xem `DatagramSocket.connect()` là TCP handshake | UDP vẫn connectionless về transport semantics | Không suy diễn reliability hay identity |
| Coi toàn bộ `getData()` là payload | Buffer có thể có bytes thừa | Đọc `getOffset()` và `getLength()` |
| Quên reset `DatagramPacket.setLength()` trước khi reuse | Receive capacity có thể giữ độ dài nhỏ | Tạo packet mới hoặc reset length |
| Cho rằng payload dài sẽ nhận ở nhiều lần `receive()` | Truncation không tạo TCP-style continuation | Cấp buffer đủ, có application-level fragmentation khi cần |
| Đặt reorder map không giới hạn | Gap mất gói làm memory tăng vô hạn | Window, TTL, max bytes và policy skip/retry |
| Chỉ dùng `int` sequence tăng mãi | Wrap làm so thứ tự sai | Chọn counter/session epoch và modular policy |
| Dedupe trong một `HashSet` rồi nói exactly-once | Crash/multi-node/state loss | Database unique key + transaction/outbox |
| Dedupe chỉ theo payload | Hai operation khác nhau có thể có payload giống nhau | Dùng requestId do protocol quy định |
| Chỉ tính số packet received để đo thành công | Packet count không phản ánh business commit | Theo dõi accepted/dedup/committed/outcome |
| Cho rằng UDP checksum xác thực sender | Checksum không phải MAC/signature | Dùng authentication/integrity phù hợp |
| Test loopback ít lỗi nên UDP reliable | Loopback không đại diện Internet | Fault injection, metrics và thực nghiệm có kiểm soát |

## 17. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** `DatagramSocket.send()` trả về không lỗi. Có được ghi đơn hàng là “đã nhận ở server” không?

**Đáp án:** Không. Chỉ biết local API send hoàn tất theo nghĩa của nó. UDP không bảo đảm delivery/processing. Cần cơ chế xác nhận có semantics rõ và lưu trạng thái nghiệp vụ.

**Câu 2.** Sender gửi `seq=1,2,3`, receiver quan sát `2,1,3`. UDP có vi phạm hợp đồng không?

**Đáp án:** Không. UDP không bảo đảm thứ tự. Nếu cần ordered processing, receiver phải buffer/sắp xếp hoặc dùng giao thức đáng tin có ordering.

**Câu 3.** Receiver nhận `seq=1` hai lần. Có nên chạy business side effect hai lần?

**Đáp án:** Không nếu đây là cùng logical operation. Dùng requestId/idempotency record có scope và policy phù hợp. Tuy nhiên hai messages có cùng payload chưa chắc cùng operation; không dedup tùy tiện theo nội dung.

**Câu 4.** Client gửi request chuyển tiền, server commit rồi ACK bị thất lạc. Client timeout. Retry có an toàn không?

**Đáp án:** Chỉ khi hệ thống có idempotency/durable state và key do authenticated principal ràng buộc. Retry đơn thuần có thể chuyển tiền lần hai.

**Câu 5.** Gọi `setSoTimeout(300)` rồi `receive()` ném `SocketTimeoutException`. Socket đã đóng chưa? Có chứng minh remote mất kết nối không?

**Đáp án:** Socket vẫn dùng được; timeout chỉ nói không lấy được datagram phù hợp trong thời gian chờ. Nó không chứng minh remote đã chết hoặc request chưa xử lý.

**Câu 6.** Gửi datagram 12 bytes vào receive `DatagramPacket` có buffer 8 bytes. Lần `receive()` sau có nhận bốn bytes còn lại không?

**Đáp án:** Không. Datagram đầu có thể bị truncate thành 8 bytes và phần vượt không trở thành một message tiếp theo. Phải có receive buffer đủ lớn hoặc application framing được định nghĩa rõ.

**Câu 7.** Vì sao buffer reorder cần window và timeout?

**Đáp án:** Nếu một sequence không bao giờ đến, các gói sau có thể chờ mãi và memory tăng không giới hạn. Window, TTL và gap policy giới hạn tài nguyên và độ trễ.

**Câu 8.** Dedupe bằng `Set<Integer> seenSequence` có đủ khi hai client đều dùng `seq=42` không?

**Đáp án:** Không. Sequence phải có scope theo session/sender đáng tin; business request ID còn cần principal/tenant và policy để tránh collision hoặc replay.

**Câu 9.** `connect()` trên `DatagramSocket` tạo reliable ordered stream như TCP không?

**Đáp án:** Không. Nó thiết lập default peer/lọc datagrams ở API, không bắt tay xác nhận remote hay cấp delivery/order/dedup guarantees.

**Câu 10.** Mỗi 5 ms gửi lại request chưa ACK mãi có thể gây gì?

**Đáp án:** Congestion tệ hơn, packet loss tăng, thậm chí gây unfairness hoặc congestion collapse. Cần retry budget, backoff, rate limit và congestion control.

**Câu 11.** Nếu một app streaming chỉ cần trạng thái mới nhất, có nhất thiết phải reorder mọi datagram và retry gói cũ?

**Đáp án:** Không. Có thể bỏ gói trễ/cũ theo semantics real-time. Quyết định ordering/reliability phụ thuộc yêu cầu ứng dụng, không phải hành vi mặc định của UDP.

**Câu 12.** Khi nào nên dùng TCP/QUIC thay vì tự xây ACK, sequence và retransmission?

**Đáp án:** Khi ứng dụng cần reliable ordered delivery/congestion control và không có lý do nghiệp vụ mạnh để dùng UDP thuần. TCP hoặc QUIC implementation chuẩn thường giảm nguy cơ thiết kế sai.

## 18. Ghi nhớ

- **UDP là best-effort:** không có bảo đảm **delivery**, **order**, **exactly once**, **ACK**, **retry** hoặc **congestion control**.
- **Gói trễ, trùng và lạc thứ tự là chuyện protocol phải chịu được.** Sender/receiver quyết định sequence, reorder window, dedupe và gap policy.
- **ACK bị mất cũng gây retry của request đã xử lý.** Timeout không cho biết phía server đã commit chưa.
- **Idempotency là ranh giới nghiệp vụ:** request ID có scope và lưu state bền vững/atomic khi cần; `HashSet` trong demo chỉ minh họa.
- **Datagram có boundary nhưng có thể truncate.** Luôn đọc `getLength()`/`getOffset()`, cấp buffer đủ và reset `setLength()` khi reuse.
- **Retry phải có backoff và congestion control.** Không tăng lưu lượng vô hạn khi mạng đang nghẽn.
- **UDP checksum và IP:port không phải authentication.** Với dữ liệu quan trọng, cần crypto/protocol tin cậy và authorization.
- **Kiểm thử chủ động:** dùng test input mất/gãy thứ tự/trùng được thiết kế trước; không suy từ một lần loopback ổn định rằng UDP reliable.
- **Nếu cần reliable ordered transport**, cân nhắc TCP/QUIC trước khi tự triển khai toàn bộ cơ chế.

## Tài liệu tham khảo hiện hành

- [Java SE 25 — `DatagramSocket` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html)
- [Java SE 25 — `DatagramPacket` Javadoc (getLength, receive buffer, truncation)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html)
- [Java SE 25 — `DatagramChannel` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [IETF RFC 8085 — UDP Usage Guidelines, nhất là `3.1` congestion và `3.3` reliability](https://www.rfc-editor.org/rfc/rfc8085.html)
- [IETF RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768.html)
- [IETF RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000.html)
- [IETF RFC 9147 — Datagram Transport Layer Security (DTLS) 1.3](https://www.rfc-editor.org/rfc/rfc9147.html)
