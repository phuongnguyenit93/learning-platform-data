# Kiểm thử mất gói, trùng gói, sai peer và dữ liệu rỗng — Điều khiển UDP (Java 15+)

## 1. Mục tiêu

Một ứng dụng dùng **UDP (User Datagram Protocol)** cần xử lý cả các tình huống truyền tải không lý tưởng. Trong Java, `DatagramSocket` gửi/nhận từng `DatagramPacket`, nhưng bản thân UDP **không đảm bảo gói được giao đến nơi, không đảm bảo đúng thứ tự, không tự loại các bản sao trùng và không xác thực danh tính người gửi**.

Trong nhóm chủ đề **Điều khiển UDP**, bốn loại kiểm thử thiết yếu là:

1. **Mất gói (packet loss):** thông điệp không đến receiver trong thời gian dự kiến.
2. **Trùng gói (duplicate):** một thông điệp hoặc một message ID xuất hiện nhiều lần.
3. **Sai peer (wrong source endpoint):** datagram đến từ IP hoặc cổng nguồn không đúng chính sách.
4. **Dữ liệu rỗng (zero-length payload):** receiver nhận một datagram **có tồn tại** nhưng payload dài 0 byte.

Bài học xây dựng một **fault-injection test** chạy thật trên UDP loopback. Nó chủ động tạo cả bốn trường hợp, thay vì hy vọng mạng nội bộ tình cờ làm mất hoặc nhân đôi packet. Phần ứng dụng phải phân biệt các kết quả một cách chính xác, không tạo side effect sai, không treo test vô hạn và không nhầm UDP rỗng với EOF.

**Phạm vi Java:** ví dụ biên dịch với `javac --release 17` và chạy được trên JDK 17+. Các API `java.net.DatagramSocket`, `java.net.DatagramPacket`, `SocketTimeoutException` và `try-with-resources` vẫn là API chuẩn trong Java hiện đại, phù hợp để học trên module Java 15. Bài không dựa vào API legacy.

## 2. Bảng phân biệt bốn lỗi

| Trường hợp | Cách tạo tình huống | Dấu hiệu cần quan sát | Quyết định ứng dụng |
| --- | --- | --- | --- |
| Mất gói | Relay nhận `id=1` rồi **không chuyển tiếp** | Receiver không nhận packet trong timeout, phát sinh `SocketTimeoutException` | Chờ/retry/hết hạn theo giao thức; không giả định packet đã được xử lý |
| Trùng gói | Relay chuyển tiếp `id=2` **hai lần** | Hai `receive` trả packet cùng ID | Chỉ xử lý message ID lần đầu; lần sau báo `DUPLICATE` |
| Sai peer | Một socket khác cổng nguồn gửi tới receiver | `packet.getPort()` khác cổng relay được cho phép | Từ chối hoặc bỏ packet trước khi xử lý payload |
| Dữ liệu rỗng | Relay gửi `new byte[0]` | `receive` trả về, `packet.getLength() == 0` | Phân loại `EMPTY`; giao thức quyết định có hợp lệ hay không |

**Giới hạn của mô hình:** “Drop” trong bài là hành động **cố ý tại relay thử nghiệm**, không phải bằng chứng hệ điều hành hoặc Internet đã làm rơi packet. “Wrong peer” được tạo bằng **cổng nguồn khác trên loopback**, không phải kỹ thuật giả mạo IP. Các giới hạn này làm cho demo kiểm chứng được, đồng thời tránh tuyên bố sai về bảo đảm UDP.

## 3. Cách DatagramSocket và DatagramPacket hoạt động

### 3.1. Gửi một gói

Đoạn mã minh họa đặt trong một method có import, `sender`, `host`, `port` và xử lý `IOException` phù hợp:

```java
byte[] payload = "id=2".getBytes(StandardCharsets.UTF_8);
DatagramPacket outbound = new DatagramPacket(
        payload, payload.length, host, port);
sender.send(outbound);
```

`send` gửi datagram qua socket. Lời gọi `send` **không tự chứng minh** packet đã đến receiver, đã được ứng dụng xử lý hoặc đã được lưu vào database. Nếu cần xác nhận ở tầng ứng dụng, hãy thiết kế **ACK/response**, message ID, timeout và retry theo giao thức.

### 3.2. Nhận packet đúng cách

```java
byte[] buffer = new byte[128];
DatagramPacket inbound = new DatagramPacket(buffer, buffer.length);
receiver.receive(inbound);

InetAddress address = inbound.getAddress();
int sourcePort = inbound.getPort();
int bytesReceived = inbound.getLength();
String message = new String(inbound.getData(),
        inbound.getOffset(), inbound.getLength(), StandardCharsets.UTF_8);
```

Các trường quan trọng:

- `getData()`: mảng buffer, **không phải mảng chỉ gồm payload hợp lệ**.
- `getOffset()`: vị trí byte đầu tiên hợp lệ.
- `getLength()`: độ dài payload thực nhận.
- `getAddress()`: IP nguồn của datagram nhận.
- `getPort()`: **cổng nguồn** của datagram nhận, không phải cổng receiver.
- `receiver.getLocalPort()`: cổng cục bộ mà receiver đang bind.

Nếu buffer có 128 byte mà packet chỉ dài 4 byte, `new String(inbound.getData())` sẽ không phản ánh chính xác thông điệp. Luôn giải mã trong **phạm vi offset/length**, và xác định encoding ở giao thức (ví dụ UTF-8).

### 3.3. Nhận không có dữ liệu và timeout

```java
receiver.setSoTimeout(500);
try {
    receiver.receive(inbound);
} catch (SocketTimeoutException ex) {
    // Không có datagram được nhận trong cửa sổ chờ 500 ms.
}
```

`setSoTimeout` đặt **giới hạn chờ `receive`**, không thay đổi đặc tính tin cậy của UDP. Timeout dương khiến `receive` ném `SocketTimeoutException` nếu chưa có packet trước deadline; **socket vẫn hợp lệ** để dùng sau đó. Giá trị timeout bằng 0 là chờ vô hạn theo cơ chế này.

**Timeout không phải bằng chứng tuyệt đối về packet loss trên mạng:** nó còn có thể do gửi sai cổng, phía gửi chưa gửi, delay, lọc sai peer hoặc sự cố test runner. Trong demo, relay cung cấp chứng cứ riêng rằng packet đã tới relay rồi bị bỏ có chủ đích.

## 4. Thiết kế fault-injection test trên loopback

Test dùng bốn socket được mở với `new DatagramSocket(0, InetAddress.getLoopbackAddress())`: `0` cho hệ điều hành chọn một cổng local khả dụng.

```text
  client                 relay                 receiver
    |                      |                       |
    |---- id=1 ----------> |                       |
    |                      X DROP                  | --TIMEOUT
    |                      |                       |
    |---- id=2 ----------> |                       |
    |                      |----- id=2 ----------> | --ACCEPTED
    |                      |----- id=2 ----------> | --DUPLICATE
    |                      |                       |
wrongPeer ----------------------- id=3 ----------> | --WRONG_PEER
    |                      |                       |
    |                      |----- 0 bytes -------> | --EMPTY
```

- **client:** đưa message ID vào relay.
- **relay:** nhận gói từ client, có thể cố ý bỏ qua hoặc gửi nhiều lần; chính relay là nguồn mà receiver mong đợi.
- **receiver:** không `connect`, tự kiểm tra IP/cổng nguồn và message ID.
- **wrongPeer:** một socket khác có cổng nguồn riêng, gửi thẳng vào receiver để kiểm tra bộ lọc peer.

Bản test này **không** tạo lỗi “tự nhiên” của IP network. Nó điều khiển luồng packet ở tầng ứng dụng để có kết quả lặp lại được. Test mạng thực tế (latency, congestion, NAT, firewall...) cần môi trường riêng và các mức impairment phù hợp.

## 5. Chương trình Java 17+ đầy đủ, chạy độc lập

Tạo file **`UdpFaultInjectionDemo.java`**:

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

public class UdpFaultInjectionDemo {
    static void send(DatagramSocket source, DatagramSocket dest,
                     InetAddress host, String message) throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        sendBytes(source, dest, host, bytes);
    }

    static void sendBytes(DatagramSocket source, DatagramSocket dest,
                          InetAddress host, byte[] bytes) throws IOException {
        source.send(new DatagramPacket(
                bytes, bytes.length, host, dest.getLocalPort()));
    }

    static DatagramPacket receive(DatagramSocket socket) throws IOException {
        byte[] buffer = new byte[128];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
        socket.receive(packet);
        return packet;
    }

    static String content(DatagramPacket packet) {
        return new String(packet.getData(), packet.getOffset(),
                packet.getLength(), StandardCharsets.UTF_8);
    }

    static String classify(DatagramPacket packet, InetAddress trustedAddress,
                           int trustedPort, Set<String> seenIds) {
        if (!packet.getAddress().equals(trustedAddress)
                || packet.getPort() != trustedPort) {
            return "WRONG_PEER";
        }
        if (packet.getLength() == 0) {
            return "EMPTY";
        }
        String value = content(packet);
        if (!value.startsWith("id=")) {
            return "MALFORMED";
        }
        return seenIds.add(value) ? "ACCEPTED" : "DUPLICATE";
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (DatagramSocket client = new DatagramSocket(0, loopback);
             DatagramSocket relay = new DatagramSocket(0, loopback);
             DatagramSocket receiver = new DatagramSocket(0, loopback);
             DatagramSocket wrongPeer = new DatagramSocket(0, loopback)) {

            relay.setSoTimeout(2_000);
            receiver.setSoTimeout(500);
            Set<String> seen = new HashSet<>();

            send(client, relay, loopback, "id=1");
            DatagramPacket dropped = receive(relay);
            if (!"id=1".equals(content(dropped))) {
                throw new IllegalStateException("Unexpected relay input");
            }
            System.out.println("relayDrop=id=1");
            try {
                receive(receiver); // Relay intentionally did not forward id=1.
                throw new AssertionError("Unexpected packet");
            } catch (SocketTimeoutException expected) {
                System.out.println("lossDetected=TIMEOUT");
            }

            send(client, relay, loopback, "id=2");
            DatagramPacket incoming = receive(relay);
            byte[] forwarded = content(incoming).getBytes(StandardCharsets.UTF_8);
            sendBytes(relay, receiver, loopback, forwarded);
            sendBytes(relay, receiver, loopback, forwarded); // Inject duplicate.
            System.out.println("duplicateFirst=" + classify(
                    receive(receiver), loopback, relay.getLocalPort(), seen));
            System.out.println("duplicateSecond=" + classify(
                    receive(receiver), loopback, relay.getLocalPort(), seen));

            send(wrongPeer, receiver, loopback, "id=3");
            System.out.println("wrongPeer=" + classify(
                    receive(receiver), loopback, relay.getLocalPort(), seen));

            sendBytes(relay, receiver, loopback, new byte[0]);
            DatagramPacket emptyPacket = receive(receiver);
            System.out.println("emptyLength=" + emptyPacket.getLength());
            System.out.println("emptyVerdict=" + classify(
                    emptyPacket, loopback, relay.getLocalPort(), seen));
            System.out.println("acceptedUnique=" + seen.size());
        }
    }
}
```

Lệnh chạy với **JDK 17 trở lên**:

```bash
javac --release 17 UdpFaultInjectionDemo.java
java UdpFaultInjectionDemo
```

**Stdout chính xác** đã kiểm chứng với `javac --release 17` và JDK 24:

```text
relayDrop=id=1
lossDetected=TIMEOUT
duplicateFirst=ACCEPTED
duplicateSecond=DUPLICATE
wrongPeer=WRONG_PEER
emptyLength=0
emptyVerdict=EMPTY
acceptedUnique=1
```

Test sử dụng địa chỉ loopback và cổng ephemeral, không cần UDP server bên ngoài. Cần môi trường cho phép mở socket UDP local. Mỗi socket được đóng tự động bởi `try-with-resources` kể cả khi code throw exception. Thời gian chờ 500/2.000 ms là **cấu hình test**, không phải giới hạn chung của Java.

### 5.1. Vì sao loss được báo TIMEOUT?

Relay thực sự đã nhận packet `id=1`, kiểm tra nội dung rồi cố tình không chuyển tiếp. Khi receiver chờ 500 ms mà không thấy datagram, `SocketTimeoutException` xuất hiện và được chuyển thành `lossDetected=TIMEOUT`.

Như vậy ta biết chắc **test đã inject drop ở relay**. Nếu chỉ nhìn thấy `SocketTimeoutException` mà không có sự kiện inject, không thể khẳng định gói bị mạng thật đánh rơi hay xác định vị trí xảy ra lỗi.

### 5.2. Vì sao một packet được ACCEPTED, bản sao bị DUPLICATE?

Relay chuyển tiếp cùng payload `id=2` hai lần. Receiver lưu ID đã được xử lý trong `Set<String>`:

```java
return seenIds.add(value) ? "ACCEPTED" : "DUPLICATE";
```

`Set.add` trả `true` khi ID chưa tồn tại và `false` khi đã tồn tại. Hai lần nhận cùng `id=2` vì thế có kết quả khác nhau; `acceptedUnique=1`.

`HashSet` ở đây chỉ minh họa **định danh và phân loại trùng gói**. Nó không phải bộ chống replay production: còn cần scope ID theo peer đã xác thực, TTL, giới hạn bộ nhớ, xử lý đồng thời, lưu bền vững nếu thao tác quan trọng và tính nguyên tử giữa ghi nhận ID với side effect.

### 5.3. Vì sao wrongPeer bị từ chối?

`wrongPeer` và `relay` có cùng địa chỉ loopback nhưng khác **source port**. Hàm `classify` kiểm tra:

```java
if (!packet.getAddress().equals(trustedAddress)
        || packet.getPort() != trustedPort) {
    return "WRONG_PEER";
}
```

Datagram `id=3` từ socket khác không khớp cổng relay nên bị phân loại `WRONG_PEER` và không tăng tập hợp message ID được chấp nhận.

Đây là bài test **đúng IP, sai port**, không phải IP spoofing. Địa chỉ/cổng nguồn chỉ giúp thực hiện chính sách lọc endpoint; **không tự chứng minh danh tính bằng mật mã**.

### 5.4. Vì sao datagram 0 byte khác timeout?

Relay gửi `new byte[0]`. Lần gọi `receive` của receiver **trở về bình thường** với `getLength() == 0`, vì vậy in `emptyLength=0`, `emptyVerdict=EMPTY`.

Điều này khác hẳn nhánh mất gói: khi không có packet đến, `receive` phải chờ rồi ném `SocketTimeoutException`; khi có **gói rỗng**, nó vẫn là một sự kiện nhận datagram. UDP không có EOF giống `InputStream.read()` trên một byte stream. Ứng dụng phải quy định riêng có cho phép gói rỗng, coi nó là heartbeat, hoặc từ chối vì thiếu header/payload.

## 6. Kiểm thử loss có kiểm soát thay vì phụ thuộc may rủi

### 6.1. Cần tạo lỗi chủ động

Một phép test chỉ gửi UDP trên loopback rồi đợi "thỉnh thoảng mất gói" thường không kiểm tra đúng đường lỗi. Thay vào đó:

- **Relay/proxy:** nhận packet rồi bỏ, giữ lại, đảo thứ tự, làm trễ hoặc nhân đôi theo kịch bản có xác định.
- **Fake transport trong unit test:** tách logic protocol khỏi socket; fake có thể trả `TIMEOUT`, `DUPLICATE` hoặc message theo lịch giả lập.
- **Network impairment ở tầng OS/test environment:** gây loss, jitter, delay, reorder trong một mạng thử nghiệm có quyền cấu hình; dùng cho integration/performance test.
- **Clock/scheduler điều khiển được:** khi kiểm thử state machine với retry/deadline, tránh phụ thuộc quá mức vào `Thread.sleep`.

Mỗi bài test cần biết **đã inject lỗi gì** và **receiver/ứng dụng phản ứng ra sao**. Một timeout bất ngờ trong ca thành công phải làm test thất bại; không nên "chữa" test flakiness bằng cách ngầm bỏ qua lỗi.

### 6.2. Timeout không đồng nghĩa chắc chắn packet đã mất

Timeout có thể do không gửi, gửi nhầm địa chỉ/cổng, gói đến muộn, bộ lọc peer loại packet, thread khác đã lấy packet hoặc hệ thống bị quá tải. Do đó, `SocketTimeoutException` chỉ cho biết **không nhận được datagram trong thời gian chờ**.

Nếu giao thức có retry, cần test riêng chính sách **deadline tổng, số lần retry, backoff và cancellation**. Không gửi lại vô hạn với tốc độ cao: ứng dụng UDP cũng phải tôn trọng congestion control và rủi ro amplification.

### 6.3. Mất ACK cũng cần test

Một trường hợp khó hơn là **server đã xử lý message nhưng ACK bị rơi**. Client có thể gửi lại cùng message, trong khi thao tác ban đầu đã thành công. Vì vậy, test loss không chỉ kiểm tra packet từ client đến server, mà còn phải kiểm tra **ACK/response bị mất** và việc retry có tạo side effect trùng hay không.

Ví dụ request "đặt chỗ" có `requestId=42` phải được xử lý **một lần theo hợp đồng nghiệp vụ**, dù server nhận nhiều datagram do client không thấy ACK. Khi test này, hãy assert cả trạng thái giao dịch, không chỉ số packet nhận.

## 7. Kiểm thử duplicate và tính idempotent

### 7.1. Không dùng raw payload làm định danh mãi mãi

Ví dụ dùng nguyên chuỗi `"id=2"` cho dễ nhìn. Trong ứng dụng thực tế, một ID nên có phạm vi rõ như `(authenticatedPeerId, requestId)`, tránh hai peer khác nhau vô tình dùng cùng số.

Bộ chống trùng cần:

1. Parse cấu trúc message một cách chặt chẽ, không chỉ `startsWith("id=")`.
2. Xác định ID có độ dài, định dạng và scope hợp lệ.
3. Kiểm tra ID đã xử lý trong **cửa sổ thời gian hoặc replay window**.
4. Bảo đảm việc kiểm tra + ghi nhận + thực hiện side effect **nguyên tử khi cần**.
5. Quy định phản ứng với duplicate: bỏ qua, trả ACK/kết quả cũ hay từ chối theo hợp đồng.
6. Phát hiện **cùng ID nhưng payload khác** là trường hợp xung đột, không mặc định là retry hợp lệ.

Với hệ thống cần lưu trạng thái qua restart, `HashSet` trong RAM không đủ. Có thể cần storage giao dịch hoặc idempotency registry có TTL/cơ chế dọn dữ liệu, tùy mức độ quan trọng.

### 7.2. Kiểm thử vượt ra ngoài hai gói giống nhau

| Test | Dữ kiện | Mong đợi |
| --- | --- | --- |
| Duplicate đúng ID và đúng payload | Gửi `id=42` hai lần | Side effect tối đa một lần |
| Duplicate sau timeout | Server xử lý trước, client retry vì không nhận ACK | Không lặp thao tác |
| Cùng ID khác payload | `id=42;amount=10`, rồi `id=42;amount=99` | Phát hiện conflict/chính sách từ chối |
| Hai peer khác nhau dùng cùng ID | Cùng `requestId`, peer/auth identity khác nhau | Scope phù hợp, không nhầm lẫn |
| Duplicate sau TTL | Gửi ID cũ khi replay window hết hạn | Hành vi được định nghĩa rõ trong protocol |
| Hai thread nhận cùng ID | Cạnh tranh xử lý đồng thời | Không vượt qua check-then-act để lặp side effect |

UDP không tự cung cấp "exactly once". Cách hệ thống xử lý duplicate phụ thuộc đặc tả và cách gắn ID, transaction, storage với nghiệp vụ.

## 8. Kiểm thử sai peer: source endpoint và bảo mật

### 8.1. `getAddress()` và `getPort()` thực sự nói gì?

Sau khi nhận datagram:

```java
InetAddress sourceAddress = packet.getAddress();
int sourcePort = packet.getPort();
```

Hai giá trị biểu diễn **endpoint nguồn** mà datagram cung cấp qua UDP/IP. Đừng nhầm source port (`packet.getPort()`) với local port của receiver (`receiver.getLocalPort()`).

Nếu giao thức chỉ chấp nhận gói từ một endpoint, nên test ít nhất bốn trường hợp: đúng IP + đúng port; đúng IP + sai port; sai IP + đúng port; và peer thay đổi địa chỉ/cổng do NAT rebinding theo chính sách được cho phép hoặc không.

Không bắt buộc mọi ứng dụng phải cố định cổng nguồn: một số giao thức cho phép peer migration hoặc NAT traversal. Khi đó cần **session/authentication policy** rõ thay vì chỉ kiểm tra một hằng port.

### 8.2. DatagramSocket.connect có giúp lọc peer?

Có. `DatagramSocket.connect(remoteAddress, remotePort)` gắn endpoint peer mặc định để chỉ gửi/nhận với endpoint đó; một socket UDP được "connected" có thể loại packet từ nguồn khác trước khi `receive` trả về.

Tuy nhiên:

- Đây không phải **kết nối TCP** có handshake và bảo đảm giao hàng.
- Đây **không phải xác thực mật mã** người gửi.
- Packet đã nằm trong receive buffer trước khi `connect` có thể chịu quy tắc discard riêng.
- Khi muốn kiểm thử bộ lọc ở tầng ứng dụng, có thể dùng socket **không connect** rồi kiểm tra IP/port trên `DatagramPacket` như demo.

Không coi việc `connect` thành công là bằng chứng peer thực sự đang online. `send` cũng không cung cấp ACK UDP.

### 8.3. Chống spoofing cần nhiều hơn địa chỉ/port

Trong mạng có khả năng giả mạo, kiểm tra `InetAddress` và port **không đủ để chứng thực danh tính**. Nếu giao thức có dữ liệu nhạy cảm, cần cơ chế xác thực và chống replay phù hợp, chẳng hạn giao thức bảo vệ UDP như DTLS hoặc thiết kế đã được thẩm định.

Đừng lấy public key/token từ một datagram tùy ý rồi mặc định tin tưởng. Đối với một hệ thống có nhiều khách hàng, danh tính peer cần được ràng buộc với session/khóa và quyền đã được kiểm tra.

## 9. Dữ liệu rỗng, buffer cắt gói và tái sử dụng packet

### 9.1. Phân biệt zero-length, timeout và close

| Trạng thái | Hành vi điển hình trong Java | Ý nghĩa |
| --- | --- | --- |
| UDP packet 0 byte | `receive` trả về; `getLength() == 0` | Một datagram đã đến |
| Không có packet trong thời gian chờ | `SocketTimeoutException` | Chưa nhận packet trong deadline |
| Socket đóng khi luồng đang `receive` | `SocketException` | Endpoint đã đóng hoặc đang shutdown |

Không dùng `getLength()==0` để suy ra socket đóng. Không tự đóng server khi nhận một gói heartbeat rỗng nếu giao thức cho phép gói đó.

### 9.2. `getData().length` không phải số byte nhận được

Nếu buffer 128 byte nhưng packet chỉ 4 byte, `getData().length == 128` còn `getLength() == 4`. Khi parse, dùng đúng `getOffset()` và `getLength()`, tránh kéo các byte `0` hoặc dữ liệu cũ vào payload.

### 9.3. Buffer quá nhỏ và truncation

`receive` dùng dung lượng được cung cấp trong `DatagramPacket`. Nếu datagram dài hơn receive length, nội dung có thể bị **cắt**. Phần bị cắt **không tự được giao ở lần receive tiếp theo** như một mảnh stream.

```java
DatagramPacket packet = new DatagramPacket(new byte[8], 8);
receiver.receive(packet); // Packet dài hơn 8 byte có thể bị cắt.
```

Đây là code minh họa trong method có xử lý `IOException`. Một giao thức nghiêm túc nên xác định giới hạn kích thước, có cách phát hiện packet thiếu hoặc checksum/authentication nếu thích hợp, và không chấp nhận message bị cắt thành một lệnh hợp lệ.

### 9.4. Reset length khi tái sử dụng cùng DatagramPacket

Sau một lần `receive(packet)`, trường length đổi thành độ dài đã nhận. Nếu tái dùng **chính cùng đối tượng** ở lần sau, cần đặt lại length theo dung lượng buffer trước khi receive tiếp:

```java
DatagramPacket packet = new DatagramPacket(new byte[128], 128);
for (int i = 0; i < 2; i++) {
    packet.setLength(packet.getData().length);
    receiver.receive(packet);
    // Chỉ xử lý vùng getOffset()..getOffset()+getLength().
}
```

Một gói **0 byte** đặc biệt dễ phơi bày lỗi này: nếu dùng lại packet sau khi `getLength()==0` mà không reset, lần sau có thể chỉ dùng receive length 0 và cho kết quả sai. Vì lý do đó ví dụ chính **tạo mới DatagramPacket cho mỗi lần nhận**, đơn giản và tránh lỗi buffer cũ.

## 10. Ma trận test đầy đủ nên có

| Case | Cách inject hoặc tạo dữ kiện | Assertion chính |
| --- | --- | --- |
| UDP-01: hợp lệ | Peer chuẩn gửi message hợp lệ | Được chấp nhận đúng một lần |
| UDP-02: loss | Relay nhận rồi không forward | Không xử lý message; có timeout/deadline |
| UDP-03: mất ACK | Server xử lý nhưng response bị drop | Client retry; server không lặp side effect |
| UDP-04: duplicate | Relay forward một ID hai lần | Lần 2 đánh dấu duplicate |
| UDP-05: duplicate khác payload | Cùng ID nhưng amount/resource thay đổi | Từ chối conflict hoặc theo policy |
| UDP-06: sai source port | Socket khác trên cùng IP gửi packet | Bộ lọc peer phát hiện |
| UDP-07: sai source IP | Nguồn khác trong test network | Từ chối nếu policy không cho phép |
| UDP-08: socket connect | Receiver đã connect tới peer cụ thể | Gói khác peer không được giao tới ứng dụng |
| UDP-09: zero payload | Gửi `new byte[0]` | `getLength()==0`, không nhầm timeout |
| UDP-10: malformed packet | Thiếu ID/header hoặc sai encoding | Không thực hiện side effect |
| UDP-11: truncated payload | Packet dài hơn buffer | Không chấp nhận im lặng như dữ liệu hợp lệ |
| UDP-12: reuse buffer | Gói trước ngắn/rỗng, gói sau dài | Reset length, đọc đầy đủ đúng giới hạn |
| UDP-13: reorder | Relay giữ gói 1, chuyển gói 2 trước | Ordering policy xử lý đúng |
| UDP-14: delay | Relay trì hoãn gần deadline | Retry/timeout đúng, không flaky |
| UDP-15: shutdown | Close socket khi receive đang chờ | Thread nhận thoát, tài nguyên được đóng |

Bài tập chính bao phủ trực tiếp **UDP-02, UDP-04, UDP-06, UDP-09**. Các trường hợp còn lại là checklist phát triển test suite thực tế, không phải kết quả mà chương trình demo đã tự kiểm thử.

### 10.1. Phân tầng kiểm thử

- **Unit test:** tách logic parse/classify/dedup khỏi socket, dùng dữ liệu kiểm soát và fake clock; kiểm tra không lặp side effect.
- **Integration test:** dùng `DatagramSocket` thực trên loopback, relay inject drop/duplicate/wrong port/empty như bài này.
- **Network/system test:** dùng môi trường riêng với loss, latency, jitter, reorder và congestion có kiểm soát, kiểm tra performance và vận hành trên OS/network thực.

Tất cả các test phải có timeout hữu hạn, tự đóng socket trong `try-with-resources` hoặc `finally`, và **fail khi thiếu điều kiện mong đợi**. Đừng chỉ in log mà không có assertion trong test automation production.

## 11. Gợi ý thiết kế protocol và xử lý retry

### 11.1. ACK và deadline

Nếu ứng dụng cần xác nhận xử lý, một giao thức đơn giản có thể gửi `requestId`, chờ `ACK(requestId)`, rồi retry sau timeout. Nhưng:

- ACK có thể bị mất hoặc trễ.
- Retry có thể tạo duplicate nếu server đã xử lý lần gửi đầu.
- Cần deadline tổng, backoff và giới hạn số lần thử.
- Server cần cơ chế idempotency/dedup, nhất là với lệnh không thể lặp an toàn.
- Payload/ACK phải được xác thực nếu nguồn mạng không đáng tin.

**Không** lập trình `while (true) { send(); }` khi thiếu ACK. Điều đó có thể gây congestion và DoS vào peer hoặc mạng.

### 11.2. Message ID không thay cho xác thực

Dùng `id=123` giúp phân biệt bản sao nhưng một peer không tin cậy cũng có thể gửi ID ấy. Nếu có yêu cầu an toàn, nên ràng buộc ID với danh tính đã xác thực, ngăn replay trong cửa sổ quy định và giới hạn bộ nhớ.

### 11.3. Tránh nhầm idempotency và "exactly once"

Chống trùng chỉ bằng RAM `Set` có thể giới hạn xử lý trùng khi server còn sống. Nếu server restart, quên Set hoặc chạy nhiều instance, ID cũ có thể được xử lý lần nữa. Nếu bài toán thực sự cần hiệu quả "một lần" cho thay đổi dữ liệu quan trọng, cần thiết kế transaction, kho trạng thái idempotency hoặc cơ chế đồng thuận/định danh theo yêu cầu nghiệp vụ.

## 12. Quan sát, logging và bảo mật

Khi kiểm thử và vận hành UDP, nên tách hai loại chỉ số:

- **Faults đã inject:** relay intentionally dropped `id=1`, forwarded `id=2` hai lần, gói wrong-peer được tạo, packet 0 byte được gửi.
- **Hành vi quan sát được:** timeout, accepted ID, duplicate count, wrong-peer rejection và empty-payload handling.

Nếu chỉ có counter timeout, không thể suy ra chính xác tỷ lệ packet bị mạng rơi. Nếu chỉ có `send` counter, không thể suy ra số packet đã được bên kia xử lý.

Logging an toàn nên có correlation/message ID đã kiểm soát, peer endpoint, kích thước payload, trạng thái xử lý và timestamp. Tránh log nguyên payload có token/dữ liệu cá nhân hoặc byte khóa nhạy cảm.

**Một lưu ý bảo mật:** UDP thường bị lợi dụng để giả mạo nguồn hoặc amplification khi server gửi phản hồi lớn tới địa chỉ chưa được xác thực. Hệ thống có public UDP listener cần rate limit, giới hạn kích thước, xác thực peer phù hợp và tránh trả quá nhiều dữ liệu cho packet nhỏ không đáng tin.

**Chuẩn vận hành:** RFC 8085 cung cấp hướng dẫn hiện hành về sử dụng UDP có trách nhiệm trên Internet, đặc biệt congestion control, reliability ở tầng ứng dụng và rủi ro mạng. Bài demo chỉ chạy loopback, không phải phép kiểm thử congestion trên mạng sản xuất.

## 13. Lỗi thường gặp

1. **Trông chờ loopback tự làm mất gói:** kết quả gần như không lặp lại được; hãy inject drop có chủ đích.
2. **Thấy `send` thành công thì kết luận receiver đã xử lý:** UDP không có bảo đảm đó.
3. **Thấy timeout thì kết luận chính xác gói bị Internet đánh rơi:** timeout chỉ là dấu hiệu không nhận được packet trong deadline.
4. **Cho phép xử lý duplicate như request mới:** có nguy cơ thực hiện thao tác nhạy cảm hai lần.
5. **Dùng Set không giới hạn làm dedup vĩnh viễn:** rò rỉ bộ nhớ và không giải quyết reboot/đa instance.
6. **Chỉ kiểm tra IP, bỏ qua source port dù protocol yêu cầu:** nhận sai peer.
7. **Coi source endpoint là chứng thực mật mã:** không đủ trong môi trường có spoofing.
8. **Cho rằng `DatagramSocket.connect` tạo phiên tin cậy như TCP:** UDP connect chỉ gắn/lọc peer.
9. **Coi packet length 0 là EOF/socket closed:** zero-length UDP datagram vẫn là packet thật.
10. **Giải mã cả `getData()` thay vì phần `getOffset()/getLength()`:** kéo dữ liệu đệm thừa vào payload.
11. **Không reset `DatagramPacket.setLength()` khi tái sử dụng:** gói tiếp theo có thể bị cắt theo length cũ.
12. **Gửi lại vô hạn khi timeout:** tạo duplicate và tăng congestion.
13. **Nhầm test relay drop với đo loss tự nhiên của network:** cần phân biệt fault injection và network impairment.
14. **Viết test không có timeout:** có thể treo CI vô hạn khi không nhận gói.
15. **Bỏ qua peer mismatch hoặc malformed packet rồi vẫn xử lý nghiệp vụ:** làm mất ranh giới kiểm tra input.

## 14. Checklist trước khi hoàn thành một bộ test UDP

- [ ] Có test riêng cho **mất gói, trùng gói, sai peer, gói rỗng**?
- [ ] Loss/duplicate được tạo một cách có kiểm soát, có bằng chứng đã inject?
- [ ] Sử dụng timeout hữu hạn và không coi timeout là chứng cứ duy nhất về nguyên nhân?
- [ ] Kiểm tra đúng source IP và source port khi giao thức yêu cầu?
- [ ] Có biện pháp xác thực peer ngoài việc so địa chỉ/port nếu dữ liệu cần bảo vệ?
- [ ] Message ID và dedup có giới hạn thời gian/bộ nhớ, xử lý concurrency phù hợp?
- [ ] Không có side effect trùng khi client retry hoặc ACK bị mất?
- [ ] Datagram rỗng được phân loại khác timeout/đóng socket?
- [ ] Tất cả parser sử dụng đúng `getOffset()`, `getLength()` và xử lý buffer truncation?
- [ ] Nếu tái sử dụng DatagramPacket, đã reset receive length trước mỗi lần nhận?
- [ ] Test có kiểm tra cả request lỗi, packet đảo thứ tự, chậm và source không hợp lệ?
- [ ] Socket được đóng đúng lifecycle sau test?
- [ ] Test được kiểm chứng trên JDK/OS/network phù hợp với môi trường triển khai?

**Kết luận:** UDP không tự lo reliability hay peer identity. Một bài test tốt phải **inject lỗi có kiểm soát** rồi xác nhận hành vi ứng dụng. Demo Java 17+ minh họa relay drop một gói, forward một gói hai lần, packet từ cổng nguồn khác và datagram 0 byte. Receiver phân biệt `TIMEOUT`, `DUPLICATE`, `WRONG_PEER`, `EMPTY` và chỉ đánh dấu `ACCEPTED` cho message ID hợp lệ chưa xử lý.

## Tài liệu chính thức và tiêu chuẩn còn hiệu lực

- [Oracle Java SE 27 — DatagramSocket](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/DatagramSocket.html): `send()`, `receive()`, `setSoTimeout()`, `connect()`, `close()`, hành vi nhận datagram và timeout.
- [Oracle Java SE 27 — DatagramPacket](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/DatagramPacket.html): `getData()`, `getOffset()`, `getLength()`, `setLength()`, `getAddress()`, `getPort()`.
- [Oracle Java SE 27 — SocketTimeoutException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/SocketTimeoutException.html): ngoại lệ khi thao tác chờ nhận vượt thời gian.
- [Oracle Java SE 27 — InetAddress](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html): địa chỉ loopback thông qua `getLoopbackAddress()`.
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): UDP header, cổng nguồn/đích, length và payload.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): reliability/congestion/control ở tầng ứng dụng và hướng dẫn sử dụng UDP hiện hành.

Bài học chỉ dùng kiến thức còn áp dụng trong Java hiện đại; không đưa vào phương thức legacy đã lỗi thời hoặc giả định UDP bảo đảm giao hàng, thứ tự hay xác thực nguồn.