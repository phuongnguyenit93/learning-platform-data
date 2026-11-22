# Khác biệt thứ tự, mất gói và trạng thái bắt tay DTLS (Java 9+)

## Mục tiêu

Bài học giải thích vì sao **Datagram Transport Layer Security (DTLS)** phải xử lý **gói đến sai thứ tự (reordering)**, **mất gói (loss)** và **gói trùng (duplication)**; cách DTLS duy trì trạng thái **bắt tay (handshake)** trước khi truyền dữ liệu ứng dụng; sự khác biệt giữa DTLS 1.2 và DTLS 1.3; và cách Java điều khiển `SSLEngine` khi DTLS chạy trên một tầng truyền datagram như UDP.

Phạm vi chuẩn đang có giá trị: **DTLS 1.2 — RFC 6347**, **DTLS 1.3 — RFC 9147** và giao diện **JSSE/SSLEngine** trên Java hiện đại. Không dùng các phiên bản DTLS đời cũ làm ví dụ triển khai. Một điểm rất quan trọng về khả năng tương thích: **RFC 9147 mô tả DTLS 1.3 nhưng việc một JDK có hỗ trợ DTLS 1.3 hay không phải kiểm tra theo provider**. Tài liệu Oracle SunJSSE cho JDK 24 liệt kê `DTLSv1.2`, chưa liệt kê `DTLSv1.3`; ví dụ runnable bên dưới chủ động dùng **DTLSv1.2** và chỉ mô tả DTLS 1.3 ở mức giao thức.

## 1. DTLS khác TLS ở đặc tính vận chuyển nào?

TLS thông thường được triển khai trên một luồng byte đáng tin cậy, có thứ tự (ví dụ TCP); DTLS bảo vệ các bản ghi (*records*) trên một phương tiện datagram, phổ biến là UDP. UDP không cam kết mỗi datagram đến đích, không cam kết thứ tự, có thể nhận trùng và có thể mất kết nối tạm thời.

| Tình huống | TLS trên TCP | DTLS trên UDP |
| --- | --- | --- |
| Một phân đoạn mạng bị mất | TCP xử lý truyền lại và cung cấp luồng byte có thứ tự cho TLS. | Bản ghi DTLS có thể không đến; **handshake** cần cơ chế truyền lại ở tầng DTLS/ứng dụng điều phối. |
| Hai đơn vị dữ liệu đến ngược thứ tự | TCP sắp xếp lại trước khi TLS tiêu thụ luồng. | DTLS có số thứ tự và thông tin handshake để xác định bản ghi/mảnh nào cần xử lý hoặc tạm giữ. |
| Nhận bản sao trùng | TCP không trình bày byte trùng ngoài luồng đã tái lập. | DTLS có cơ chế chống phát lại dựa trên epoch/sequence number; tùy phiên bản và chính sách. |
| Thông điệp lớn hơn MTU | TCP có cơ chế phân mảnh trên luồng. | DTLS handshake có thông tin phân mảnh/tái lắp riêng; ứng dụng phải tính kích thước datagram/PMTU. |
| Dữ liệu ứng dụng sau bắt tay | TCP bảo đảm chuyển byte theo thứ tự hoặc kết nối lỗi. | DTLS bảo vệ bí mật và tính toàn vẹn nhưng **không tự biến UDP thành kênh gửi tin đáng tin cậy, có thứ tự**. |

Vì vậy, khi một datagram bị mất, cần hỏi **mất datagram chứa handshake hay chứa dữ liệu ứng dụng?** Với handshake, thiếu thông điệp có thể ngăn thiết lập khóa; DTLS phải phát hiện và truyền lại. Với application data, DTLS có thể bỏ qua một datagram bị mất và tiếp tục giải mã datagram sau; ứng dụng chịu trách nhiệm nếu nghiệp vụ muốn phát lại, thứ tự, xác nhận hoặc phát hiện khoảng trống.

Dù DTLS kế thừa nhiều cơ chế mật mã của TLS, **không thể lấy nguyên vòng đọc/ghi socket TCP để dùng với UDP**. Khi đọc DTLS, cần quan tâm đến datagram, key epoch, record sequence và message sequence thay vì chỉ số byte trên stream.

## 2. Hai loại “thứ tự” không được nhầm

### 2.1. Thứ tự bản ghi (record sequence) và epoch

DTLS gắn thông tin thứ tự bản ghi với một **epoch** để biết trạng thái khóa đang được dùng. Về nguyên tắc:

- **Epoch** phân biệt các giai đoạn trạng thái mật mã, ví dụ trước và sau khi có khóa handshake/application. Một datagram dùng khóa của epoch cũ có thể đến muộn khi bên nhận đã chuyển sang epoch mới.
- **Record sequence number** phân biệt các bản ghi trong từng epoch, giúp xử lý gói trùng, gói quá cũ, và bảo vệ tính toàn vẹn/chống phát lại.
- Bên nhận có thể dùng cửa sổ chống replay. Những bản ghi nằm ngoài cửa sổ, lặp lại hoặc không xác thực có thể bị loại. Không diễn giải kết quả “bỏ” như việc tầng dưới phải tự phát lại.
- Cơ chế bố trí bit và mã hóa số thứ tự **khác giữa các phiên bản**. Tài liệu RFC 9147 quy định rõ epoch và sequence number cho DTLS 1.3; không bê cách giải mã header 1.2 áp cho 1.3.

**Bản ghi có sequence number lớn hơn không có nghĩa thông điệp handshake của nó được phép xử lý trước một thông điệp bắt buộc đứng trước.** Record ordering và handshake ordering là hai bài toán khác nhau.

### 2.2. Thứ tự thông điệp handshake (message_seq)

Handshake của DTLS còn có trường **`message_seq`** để nhận biết vị trí logic của thông điệp trong quá trình bắt tay. Chẳng hạn ở một flight giả định:

```text
Ý nghĩa logic: Handshake M0 -> Handshake M1 -> Handshake M2

UDP thực tế:      M2 -------->
                  M0 ------>
                  M1 ------------->

Bên nhận: có thể đệm M2, xử lý M0, sau đó M1 rồi mới xử lý M2.
```

DTLS 1.2 có các trường `message_seq`, `fragment_offset` và `fragment_length` trong cấu trúc handshake; chúng giúp xử lý bản ghi đến sai thứ tự và ghép lại thông điệp bị chia thành nhiều mảnh. DTLS 1.3 tiếp tục quy định message sequence và cơ chế phân mảnh handshake tương ứng. Mỗi **datagram** không nhất thiết chứa đúng một **thông điệp handshake**: một thông điệp lớn có thể bị phân mảnh; một datagram cũng có thể mang nhiều record.

Cần phân biệt ba việc:

1. **Reordering:** mảnh đã đến nhưng chưa thể tiêu thụ vì thông điệp trước còn thiếu; có thể đệm trong giới hạn.
2. **Loss:** mảnh chưa đến; đợi hoặc yêu cầu truyền lại thông qua cơ chế handshake.
3. **Duplication/replay:** nhận lại bản sao; xác định xem đã xử lý chưa, không ứng dụng lại tác dụng phụ của handshake.

Bản tin đến sai thứ tự **không đồng nghĩa là hỏng hay bị tấn công**; mạng UDP bình thường có thể gây ra. Ngược lại, việc chấp nhận mọi thứ tự mà không kiểm soát epoch, khóa, integrity và sequence number sẽ làm hỏng state machine.

## 3. “Flight” là gì và vì sao handshake cần truyền lại?

Một **flight** là nhóm thông điệp handshake mà một bên gửi trước khi chờ phản hồi/ACK tiếp theo. Ví dụ đơn giản:

```text
Client                           Server
  | ---- ClientHello ---------->  |
  |                                |
  | <------ [server flight] ------  |
  |                                |
  | ---- [client final flight] ->  |
  |                                |
  | <------- [ACK nếu cần] ------  |   (DTLS 1.3)
  v                                v
     Hai bên đi tới trạng thái sử dụng khóa ứng dụng
```

Đây là sơ đồ **khái niệm**, không mô tả đầy đủ mọi chứng chỉ, `CertificateVerify`, `Finished`, cookie, 0-RTT hoặc trạng thái cipher của từng phiên bản.

Nếu một datagram chứa mảnh của server flight bị mất:

```text
Client                           Server
  | ---- ClientHello ---------->  |
  | <--- ServerHello -----------  |
  | <--- fragment A -----------  |
  |       fragment B (LOST)  X  |
  | <--- fragment C -----------  |
  |                                |
  | [chưa có đủ thông điệp]         | [chờ phản hồi]
  |                                |
  | <-- gửi lại phần cần thiết --  | (tùy phiên bản/cơ chế)
```

**DTLS 1.2 (RFC 6347):** truyền lại dựa trên **flight và retransmission timer**. Khi hết giờ chờ mà không thấy tiến triển, phía gửi có thể gửi lại flight cần thiết. Bộ nhận có thể giữ các mảnh đến sớm đến khi ghép được đầy đủ. Điều chỉnh timeout/backoff và giới hạn số lượt là trách nhiệm quan trọng để tránh vòng lặp vô hạn.

**DTLS 1.3 (RFC 9147):** có thêm **ACK record** cho handshake. ACK mô tả các record handshake đã nhận và xử lý/đệm; bên gửi có thể xác định phần chưa được xác nhận để phát lại chính xác hơn. RFC 9147 cũng dùng flight/timer, không phải mọi datagram đều trở thành reliable như TCP. ACK này là **cơ chế của DTLS 1.3**, không được giả định rằng mọi `SSLEngine` DTLS 1.2 đều tạo hoặc cung cấp ACK loại đó cho ứng dụng.

Khi nhận một flight kế tiếp, bên gửi thường có thể xem flight trước đã được ngầm xác nhận theo quy tắc protocol; ở DTLS 1.3, flight cuối và một số bản tin sau bắt tay cần ACK theo RFC. Không nên làm các timer riêng “mỗi gói UDP phải ACK” ở tầng ứng dụng cho dữ liệu handshake: dùng cơ chế của thư viện DTLS.

## 4. Trạng thái bắt tay ở cấp giao thức và ở Java

Có **hai cách mô tả trạng thái** phục vụ mục đích khác nhau.

### 4.1. Trạng thái logic của DTLS 1.3 trong RFC 9147

RFC mô tả state machine retransmission với các trạng thái:

```text
PREPARING
   | chuẩn bị và lưu flight
   v
SENDING
   | gửi flight và đặt timer
   v
WAITING ---- timer hết hạn/ACK chưa đủ ----> SENDING
   |                                      ^
   | nhận flight/ACK thích hợp             |
   v                                      |
PREPARING (flight tiếp theo) -------------+
   |
   v
FINISHED
```

**Diễn giải thực tế:**

- `PREPARING`: tạo flight và cấu trúc cần thiết.
- `SENDING`: phát các thông điệp/fragment; nếu có ACK một phần, có thể bỏ các fragment đã được xác nhận.
- `WAITING`: nhận ACK hoặc flight kế tiếp; hết timer thì tái truyền; cũng cần giới hạn retry và tổng thời gian bắt tay.
- `FINISHED`: không còn phải đợi hoàn tất flight này. Đặc biệt, RFC 9147 có quy tắc đáp ứng retransmission của flight cuối để xử lý việc một bên kết thúc trước bên kia.

Các tên trạng thái trên **không phải tên enum của Java**. Đó là mô hình ở chuẩn giao thức để đọc dấu hiệu trên mạng và thiết kế vận hành.

### 4.2. Trạng thái API `SSLEngineResult.HandshakeStatus` trong JSSE

Java sử dụng `javax.net.ssl.SSLEngine`, API không trực tiếp đọc/ghi UDP. Bên gọi tự chuyển byte giữa engine và `DatagramSocket`/`DatagramChannel`, đồng thời chạy event loop theo các trạng thái:

| Giá trị | Ứng dụng nên làm |
| --- | --- |
| `NEED_WRAP` | Gọi `engine.wrap(...)` tạo DTLS packet, gửi các byte được tạo qua datagram transport. |
| `NEED_UNWRAP` | Chờ/nhận datagram từ peer, rồi gọi `engine.unwrap(...)` để engine xử lý. **Khi timer DTLS bắt tay hết hạn, có thể cần gọi `wrap(...)` ngay cả khi vẫn là `NEED_UNWRAP`** để provider phát lại flight trước. |
| `NEED_UNWRAP_AGAIN` | Gọi `unwrap(...)` tiếp để xử lý **dữ liệu đã đệm bên trong engine**; không chờ datagram mới cho thao tác này. |
| `NEED_TASK` | Lấy `engine.getDelegatedTask()` và thực thi các task theo API, rồi tiếp tục vòng xử lý trạng thái. |
| `FINISHED` | Được trả về trong kết quả `wrap/unwrap` khi handshake hoàn tất. Thường không phải trạng thái giữ lại dài hạn ở `getHandshakeStatus()`. |
| `NOT_HANDSHAKING` | Engine không đang bắt tay; kiểm tra kết quả, phiên đã thương lượng và điều kiện ứng dụng trước khi trao đổi dữ liệu. |

Song song với `HandshakeStatus`, từng lệnh `wrap/unwrap` trả `SSLEngineResult.Status`: `OK`, `BUFFER_OVERFLOW`, `BUFFER_UNDERFLOW`, `CLOSED`. Cần xử lý **cả hai**, không chỉ enum handshake.

- `BUFFER_OVERFLOW`: buffer đích quá nhỏ; tăng theo `SSLSession.getPacketBufferSize()`/`getApplicationBufferSize()` và giới hạn đã thiết kế, tránh vòng lặp vô hạn.
- `BUFFER_UNDERFLOW`: không đủ byte đầu vào cho một đơn vị cần giải mã. Với datagram, phải xác định liệu datagram đã bị cắt khi nhận hay thiếu thành phần hợp lệ; không coi UDP là một luồng TCP để tùy ý ghép dữ liệu từ các datagram không liên quan.
- `CLOSED`: xử lý đóng engine và kênh truyền theo quy trình, không tiếp tục bắt tay.

**Điểm rất dễ sai:** `NEED_UNWRAP_AGAIN` không có nghĩa là mất gói và không phải yêu cầu nhận UDP. Đây là tín hiệu engine còn dữ liệu handshake đã nội bộ đệm sau khi nhận gói đến lệch thứ tự. Nếu event loop cứ chờ socket, quá trình bắt tay có thể đứng im dù dữ liệu cần thiết đã ở trong bộ nhớ engine.

## 5. Ví dụ chạy được: tạo DTLS 1.2 ClientHello và kích hoạt tái truyền

Đây là **test thật trên JSSE** cho trạng thái bắt tay và đầu ra `wrap`, không mở cổng UDP hoặc đòi máy chủ ngoài. Chương trình tạo DTLS engine client, yêu cầu xuất ClientHello, giả lập việc **đã bỏ datagram đầu ra** (không gửi đến server) rồi gọi `wrap` lần nữa để mô phỏng timer báo rằng flight trước có thể bị mất.

**Giới hạn quan sát:** chương trình chỉ xác minh client tạo được handshake packet và retransmission packet; nó **không** chứng minh một phiên DTLS đầy đủ đã hoàn tất, **không** mô phỏng reordering từ server, và **không** thay thế integration test với hai peer.

Lưu tệp **`DtlsHandshakeStateDemo.java`**:

```java
import java.nio.ByteBuffer;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLEngineResult.HandshakeStatus;

public class DtlsHandshakeStateDemo {
    private static final ByteBuffer EMPTY = ByteBuffer.allocate(0);

    private static void check(boolean yes, String what) {
        if (!yes) throw new AssertionError(what);
    }

    private static SSLEngineResult outbound(SSLEngine engine, ByteBuffer network)
            throws Exception {
        network.clear();
        SSLEngineResult result = engine.wrap(EMPTY.duplicate(), network);
        check(result.getStatus() == SSLEngineResult.Status.OK, "wrap status");
        return result;
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("DTLSv1.2");
        context.init(null, null, null);

        SSLEngine client = context.createSSLEngine("example.invalid", 4433);
        client.setUseClientMode(true);
        client.setEnabledProtocols(new String[] {"DTLSv1.2"});
        client.beginHandshake();

        System.out.println("after begin: " + client.getHandshakeStatus());
        check(client.getHandshakeStatus() == HandshakeStatus.NEED_WRAP,
                "expected initial NEED_WRAP");

        ByteBuffer packet = ByteBuffer.allocate(
                client.getSession().getPacketBufferSize());

        SSLEngineResult hello = outbound(client, packet);
        System.out.println("after ClientHello wrap: " + hello.getHandshakeStatus()
                + ", packet produced=" + (hello.bytesProduced() > 0));
        check(hello.bytesProduced() > 0, "no ClientHello datagram");
        check(client.getHandshakeStatus() == HandshakeStatus.NEED_UNWRAP,
                "expected NEED_UNWRAP");

        // Transport intentionally drops the first outbound datagram.
        // This demonstrates loss; no server receives the packet.
        SSLEngineResult retry = outbound(client, packet);
        System.out.println("after timer-triggered wrap: " + retry.getHandshakeStatus()
                + ", packet produced=" + (retry.bytesProduced() > 0));
        check(retry.bytesProduced() > 0, "no retransmit datagram");

        System.out.println("PASS retransmission produces a DTLS packet");
    }
}
```

Chạy với **JDK có SunJSSE hỗ trợ DTLS 1.2**, ví dụ JDK 17 hoặc JDK 24:

```bash
javac -encoding UTF-8 --release 17 DtlsHandshakeStateDemo.java
java DtlsHandshakeStateDemo
```

Stdout quan sát với SunJSSE/JDK 24:

```text
after begin: NEED_WRAP
after ClientHello wrap: NEED_UNWRAP, packet produced=true
after timer-triggered wrap: NEED_UNWRAP, packet produced=true
PASS retransmission produces a DTLS packet
```

Ý nghĩa:

1. `beginHandshake()` đưa engine client vào trạng thái cần tạo handshake output.
2. `wrap(EMPTY, packet)` tạo DTLS bytes mà tầng UDP phải gửi đi. `packet.clear()` chuẩn bị buffer đích cho mỗi lượt; khi gửi thật cần `flip()` và chỉ gửi vùng chứa byte vừa tạo.
3. Vì không có gói đến từ server, client ở trạng thái `NEED_UNWRAP`. Đó là trạng thái chờ peer, **không phải bằng chứng đã lỗi**.
4. Trong vòng lặp production, khi timer hết hạn, tầng ứng dụng gọi `wrap` để yêu cầu provider phát lại các handshake packet cần thiết dù handshake status đang `NEED_UNWRAP`. Ví dụ dùng trực tiếp một lời gọi `wrap` để minh họa tín hiệu timeout; **nó không triển khai timer, backoff hay UDP thực**.
5. `bytesProduced() > 0` xác nhận có DTLS packet; không khẳng định nội dung byte hai lần giống hệt nhau hay server đã nhận được.

Một số provider có thể hỗ trợ phiên bản khác, dùng thứ tự trạng thái khác hoặc quy tắc retransmission riêng. Khi triển khai, đọc `context.getSupportedSSLParameters().getProtocols()` hoặc `engine.getSupportedProtocols()` và kiểm thử provider/JDK đang chạy thay vì bắt buộc stdout của ví dụ trên ở mọi môi trường. Không cấu hình `DTLSv1.3` trên provider chỉ có `DTLSv1.2`.

## 6. Event loop Java thực tế cần xử lý những gì?

Trên một server hay client dùng `DatagramChannel`, việc mở socket là của ứng dụng, còn JSSE xử lý mật mã. Luồng điều phối có thể hình dung như sau (**pseudocode**, các hàm `sendDatagram`/`receiveDatagram`/`growBuffer`/`scheduleTimeout` là trách nhiệm của ứng dụng và không phải API Java có sẵn):

```text
engine.beginHandshake()
start handshake deadline and retransmission scheduler

while handshake is not done:
    hs = engine.getHandshakeStatus()

    if hs == NEED_TASK:
        execute all engine.getDelegatedTask() tasks
        continue

    if hs == NEED_WRAP:
        result = engine.wrap(emptyApplicationInput, outboundPacket)
        process buffer status
        if bytes produced: sendDatagram(outboundPacket)
        continue

    if hs == NEED_UNWRAP_AGAIN:
        result = engine.unwrap(emptyNetworkInput, inboundApplicationBuffer)
        process buffer status
        continue                 # No new UDP receive here

    if hs == NEED_UNWRAP:
        if an inbound UDP datagram is available:
            result = engine.unwrap(datagram, inboundApplicationBuffer)
            process buffer status
        else if retransmission timer expired:
            result = engine.wrap(emptyApplicationInput, outboundPacket)
            process buffer status
            if bytes produced: sendDatagram(outboundPacket)
            schedule next bounded retry
        else:
            wait for network or timer
        continue

    if hs == NOT_HANDSHAKING:
        verify negotiated session, then hand off to application data
        break

if deadline/retry budget exceeded: close engine and fail handshake
```

Những điểm cần bổ sung cho một ứng dụng chạy thật:

- **Không blocking toàn bộ event loop** ở thao tác đọc socket nếu nó phải tự phát tín hiệu timer. Một vòng đợi có timeout hoặc event loop có scheduler giúp cơ chế tái truyền hoạt động.
- **Datagram phải giữ đúng ranh giới**: gửi chính xác `bytesProduced()` từ các `wrap`, cấp buffer đúng và đưa từng datagram nhận được vào `unwrap`. Không giả định một lần `unwrap` luôn tiêu thụ toàn bộ datagram, hoàn tất nguyên một handshake message hoặc sinh ngay application data.
- **Chạy `NEED_TASK`** trước khi chờ I/O tiếp theo. Task có thể liên quan kiểm tra chứng chỉ hoặc tác vụ mật mã; bỏ qua làm kẹt handshake.
- **Xử lý `NEED_UNWRAP_AGAIN`** kể cả khi không có network event, vì JSSE có thể đã đệm thông điệp đến sai thứ tự.
- **Tôn trọng `SSLEngineResult.Status`** và vị trí `ByteBuffer` (`clear/flip/compact` đúng hoàn cảnh). Sai buffer có thể tạo triệu chứng giống “mất gói” trong khi thực chất là lỗi ứng dụng.
- **Giới hạn thời gian và tài nguyên**: tổng thời gian handshake, số lần retransmit, kích thước bản tin đệm, số phiên chưa xác thực, độ dài hàng đợi và phần trăm CPU cho mỗi peer.
- **Kiểm tra danh tính peer**: cấu hình trust/key material và xác minh peer/endpoint phù hợp; bài demo chưa tạo kết nối nên không cung cấp một chính sách xác thực. Một handshake chạy đủ flight không tự đảm bảo bạn đã xác thực đúng server nếu trust/hostname bị bỏ qua.
- **Không sử dụng `SSLEngine` như một API tự gửi UDP**: `SSLContext` và `SSLEngine` không tự biết địa chỉ datagram thực hay quản lý socket. Hint hostname/port khi tạo engine không có nghĩa socket tự kết nối.

### Packet size, MTU và fragmentation

Để hạn chế phân mảnh IP, ứng dụng cần biết đường truyền thực tế/PMTU. JSSE có `SSLParameters.setMaximumPacketSize(int)` để cấu hình kích thước packet mong muốn trên các triển khai hỗ trợ; kiểm tra tài liệu của provider, giới hạn thực tế và overhead khi đóng gói. Đặt kích thước datagram quá lớn có thể làm tăng rủi ro mất toàn bộ datagram do IP fragmentation hoặc do đường đi không hỗ trợ.

Bản tin handshake như chứng chỉ có thể lớn hơn một datagram. DTLS handshake có cơ chế **fragment/reassembly** để tránh dựa vào IP fragmentation. Tuy nhiên, việc cấp phát buffer bên nhận vẫn phải được giới hạn nhằm chống cạn tài nguyên khi có lưu lượng không tin cậy.

## 7. Kịch bản chi tiết: cùng một thay đổi mạng, hai kết quả khác nhau

### 7.1. Datagram đến sai thứ tự

Giả định server phát hai mảnh handshake A rồi B, còn mạng giao B trước A:

```text
Server send:     A ----------> B --------->
Client receive:         B ----------> A
Client engine:         buffer B -> process A -> process B
                         |
                  có thể xuất hiện NEED_UNWRAP_AGAIN
```

Engine có thể đệm B để xử lý sau; không cần giả định kết nối hỏng hoặc gửi lại toàn bộ dữ liệu ngay. Phía tích hợp JSSE phải **đưa cả hai datagram vào engine**, tiếp tục vòng handshake và xử lý `NEED_UNWRAP_AGAIN`. Việc buffer/reorder nội bộ là trách nhiệm của triển khai DTLS, không phải tự sắp xếp byte và viết lại handshake parser trong ứng dụng.

**Test đúng:** tráo thứ tự **datagram hợp lệ sinh từ engine/server thật** và kiểm tra handshake cuối cùng hoàn tất, không vi phạm xác thực; không thể kiểm thử bằng cách tráo ngẫu nhiên byte trong một DTLS record đã được mã hóa.

### 7.2. Mất một mảnh handshake

Nếu B mất:

```text
Server send:     A -----> B -X->
Client receive:  A
Client state:    đợi phần còn thiếu
Server state:    WAITING
Timer/ACK:       phát lại phần cần thiết theo phiên bản DTLS
```

**DTLS 1.2** thường dựa vào timer/flight retransmission; **DTLS 1.3** có thể ACK các record đã nhận để hỗ trợ gửi lại fragment chưa được ACK. Khi phía nhận có đủ dữ liệu, nó tiếp tục handshake. Một số packet duplicate có thể đến trong quá trình phát lại; không được coi chúng là handshake mới.

**Test đúng:** làm mất datagram mang một fragment ở network shim, ghi lại số lần retry/timeout, kiểm tra handshake thành công trong retry budget và cuối cùng không rò buffer/timer. Khi làm mất toàn bộ flight và không có peer phản hồi, test phải kết thúc bằng lỗi timeout có kiểm soát.

### 7.3. Mất datagram chứa application data sau handshake

```text
Application:   send(data #1) -> send(data #2) -> send(data #3)
UDP receive:       data #1           X           data #3
```

DTLS vẫn kiểm tra tính toàn vẹn của data #3 và có thể trao cho ứng dụng; nó **không phải TCP** nên không buộc phải đợi data #2 hay tự gửi lại data #2. Nếu nghiệp vụ cần đúng đủ và có thứ tự, ứng dụng/protocol phía trên phải có message ID, ACK, retry, deduplication hoặc chọn một transport khác với đặc tính phù hợp.

**Test đúng:** sau handshake, cố ý drop application datagram #2 và xác nhận ứng dụng không nhầm #3 thành #2. Không đánh giá DTLS “sai” chỉ vì application message #2 không được tự retransmit.

### 7.4. Nhận duplicate/replay hoặc record của epoch cũ

Kẻ tấn công/mạng có thể đưa lại một record từng gửi. DTLS cần kiểm tra authentication tag, epoch và replay window theo phiên bản/cấu hình. Ứng dụng không được nhân đôi tác dụng nghiệp vụ chỉ vì một datagram bị phát lại. Với record hợp lệ của epoch cũ đến trễ, RFC có chính sách xử lý/buffer/discard tùy trạng thái và phiên bản; không giả định “số thứ tự nhỏ” là trường hợp duy nhất gây mất thứ tự.

**Test đúng:** replay datagram hợp lệ sau khi đã được tiêu thụ; xác nhận không dẫn đến lặp trạng thái nghiệp vụ. Test ở tầng wire nếu cần, không gán ý nghĩa giao thức cho lỗi parse từ bytes tự chỉnh bừa.

## 8. DTLS 1.2 và 1.3: điểm khác cần giữ rõ ràng

| Khía cạnh | DTLS 1.2 — RFC 6347 | DTLS 1.3 — RFC 9147 |
| --- | --- | --- |
| Căn cứ bản mật mã | Gắn với họ TLS 1.2 và mô hình handshake của nó. | Gắn với TLS 1.3, thay đổi key schedule và nhiều thông điệp handshake. |
| Mất handshake | Flight retransmission dựa trên timeout và dấu hiệu phản hồi. | Giữ flight/timer **và** ACK record cho handshake, có thể tái truyền có chọn lọc. |
| Thứ tự/phân mảnh | Handshake có `message_seq`, `fragment_offset`, `fragment_length`. | Tiếp tục cơ chế đảm bảo thứ tự/reassembly với framing và record riêng của 1.3. |
| Epoch/record | Có epoch và record sequence để giải mã/chống replay. | Có epoch gắn với các giai đoạn khóa TLS 1.3; wire format/record protection khác DTLS 1.2. |
| Kiểm tra địa chỉ, chống khuếch đại | Có cơ chế cookie ở handshake DTLS 1.2. | Dùng cơ chế address validation tương ứng, trong đó `HelloRetryRequest` có thể mang cookie; áp dụng giới hạn chống amplification của chuẩn. |
| Java JSSE/SunJSSE (JDK 24 theo tài liệu Oracle) | `DTLSv1.2` được hỗ trợ và dùng trong ví dụ chạy được. | Không tự khẳng định `DTLSv1.3` được provider hiện tại hỗ trợ; phải chọn provider/implementation có quảng bá rõ khả năng ấy. |

Việc có RFC mới không chứng minh mọi thư viện Java đều đã triển khai nó. Luôn phân biệt **giao thức có chuẩn** với **provider hiện đang cài đặt trên runtime có hỗ trợ**.

DTLS 1.3 cũng có quy định liên quan đến 0-RTT, epoch và phản hồi gói đến sớm. Chỉ sử dụng 0-RTT nếu thư viện/giao thức ứng dụng hỗ trợ đúng và có chính sách chống replay; không tự xem dữ liệu đến sớm là tương đương dữ liệu sau handshake đã hoàn tất.

## 9. Ma trận kiểm thử mạng và state machine nên có

| Test | Cách dựng lỗi | Quan sát/tiêu chí chấp nhận |
| --- | --- | --- |
| Baseline sạch | Hai peer trao đổi DTLS bình thường | Hoàn tất handshake, xác thực peer, hai bên thống nhất protocol/cipher phù hợp. |
| ClientHello bị mất | Drop datagram đầu tiên từ client | Client vẫn `NEED_UNWRAP` trước timeout; tầng app kích hoạt retransmission; handshake thành công nếu retry còn đủ. |
| Server flight mất toàn bộ | Drop mọi datagram flight đầu từ server | Retransmission xảy ra theo phiên bản; không treo vĩnh viễn; nếu peer thật sự mất, timeout có kiểm soát. |
| Một fragment bị mất | Drop một datagram trong handshake message nhiều mảnh | Không xử lý message thiếu; reassembly sau khi nhận lại; không lộ dữ liệu chưa xác thực. |
| Đảo thứ tự | Giữ datagram A rồi giao B trước A | Engine xử lý đúng, có thể dùng buffering/`NEED_UNWRAP_AGAIN`; handshake hoàn tất khi đủ dữ liệu. |
| Duplicate | Giao cùng record hai lần | Không phát sinh hai phiên hoặc áp dụng tác dụng phụ hai lần. |
| Replay/epoch cũ | Phát lại record sau khi đổi trạng thái khóa | Record được xác thực/loại bỏ đúng quy tắc; không hồi quy trạng thái handshake. |
| Buffer nhỏ | Cấp buffer nhỏ hơn yêu cầu | Xử lý `BUFFER_OVERFLOW`/`BUFFER_UNDERFLOW` với giới hạn; không mất byte âm thầm. |
| Chứng chỉ/khóa không hợp lệ | Dùng peer không được tin cậy hoặc sai danh tính | Handshake thất bại; không báo thành công chỉ vì đã gửi đủ flight. |
| MTU nhỏ | Giới hạn datagram và gửi handshake lớn | Fragmentation/reassembly hợp lệ; không dựa vào IP fragmentation thiếu kiểm soát. |
| Dữ liệu ứng dụng bị mất | Drop một protected application datagram | DTLS không tự khôi phục như TCP; logic ứng dụng xử lý gap theo hợp đồng. |
| Không có peer | Không trả lời mọi datagram | Retry hạn chế, timeout, giải phóng session/buffer/timer. |
| Nhiều peer | Các peer có IP/port và khóa trạng thái khác nhau | Không dùng nhầm `SSLEngine`/session/timer giữa những kết nối độc lập. |

Test độ tin cậy phải có **network shim** có thể drop, delay, reorder, duplicate datagram **được tạo hợp lệ bởi hai engine**; việc sửa ngẫu nhiên ciphertext chỉ kiểm tra integrity failure. Với DTLS 1.3, chạy ma trận tương tự trên implementation DTLS 1.3 thật để xác minh ACK/flight semantics riêng, thay vì suy luận từ output của SunJSSE DTLS 1.2.

**Đo lường nên ghi lại:** số flight và số datagram đã gửi, số lần timer kích hoạt, packet được retransmit, thời gian hoàn tất handshake, lý do thất bại, số bản ghi bỏ qua do replay/buffer/epoch, và lượng RAM cho các handshake chưa kết thúc. Các biến này giúp phân biệt lỗi kết nối thật với lỗi vòng lặp JSSE.

## 10. Lưu ý bảo mật khi UDP không đáng tin

- **Chống DoS/amplification:** server chưa xác minh được địa chỉ khách có thể bị lợi dụng trả nhiều byte về địa chỉ giả mạo. Áp dụng address validation/cookie, giới hạn gửi khi chưa xác minh peer và rate limit theo chuẩn/giao thức.
- **Xác minh peer:** handshake “FINISHED” không tự động chứng minh đối tác thuộc danh tính nghiệp vụ mà bạn mong đợi nếu trust manager hoặc endpoint identification bị cấu hình sai. Tránh các trust manager chấp nhận mọi chứng chỉ trong mã sản phẩm.
- **Anti-replay không phải deduplication nghiệp vụ:** record bị phát lại ở tầng DTLS khác với người dùng hợp lệ gửi hai request tương đương. Nghiệp vụ tài chính/cập nhật trạng thái vẫn cần request ID/idempotency khi phù hợp.
- **Dữ liệu sớm và trạng thái epoch:** không giao application data cho handler khi chưa hoàn thành các điều kiện bảo mật của phiên, kể cả khi một số record đến trước vì mạng đảo thứ tự. 0-RTT có hợp đồng replay riêng.
- **Giới hạn bộ nhớ và timeout:** không đệm vô hạn packet đến sai thứ tự, mảnh handshake hoặc session chờ chứng chỉ. Điều chỉnh kích thước datagram, retry/backoff và giới hạn số phiên đồng thời.
- **Không dùng lại nonce/sequence sai cách:** giao phần quản lý record number/epoch và khóa cho DTLS implementation; không tự làm crypto transport dựa trên byte dump của `SSLEngine`.
- **Không đoán phiên bản:** kiểm tra thuật toán được phép, provider, JDK và cipher suite phù hợp. DTLS 1.3 dùng những yêu cầu, trạng thái và cơ chế khác, không chỉ đổi chuỗi `DTLSv1.2` thành `DTLSv1.3`.

### Những lỗi triển khai thường gặp

1. **Đợi vô hạn ở `NEED_UNWRAP`:** ứng dụng chờ socket mãi mà không có timer; peer chờ retransmission nhưng không bao giờ được gửi.
2. **Bỏ qua `NEED_UNWRAP_AGAIN`:** engine có handshake fragment đệm nhưng ứng dụng chỉ chạy tiếp khi có UDP mới.
3. **Gọi `wrap` chỉ ở `NEED_WRAP`:** bỏ lỡ yêu cầu retransmit lúc `NEED_UNWRAP` sau timeout trong JSSE DTLS.
4. **Coi `FINISHED` là trạng thái luôn hiện trong `getHandshakeStatus()`:** enum `FINISHED` thường chỉ xuất hiện ở kết quả của thao tác hoàn tất; sau đó có thể là `NOT_HANDSHAKING`.
5. **Không xét `SSLEngineResult.Status`:** `BUFFER_OVERFLOW`/`BUFFER_UNDERFLOW` bị hiểu nhầm là mất gói ở mạng.
6. **Dùng `Socket` stream giả lập UDP:** vứt bỏ ranh giới datagram, dẫn tới kết luận test sai về reorder và loss.
7. **Áp ACK của RFC 9147 cho mọi DTLS:** DTLS 1.2 và DTLS 1.3 có cơ chế retransmission không trùng nhau.
8. **Đồng nhất “handshake tin cậy” với “application data tin cậy”:** sau khi bắt tay thành công, DTLS vẫn không tự bảo đảm mọi application datagram đều đến đúng thứ tự.

## 11. Câu hỏi tự kiểm tra

1. Nếu datagram B của một handshake message đến trước A, làm sao phân biệt “sai thứ tự” với “mất gói”? Khi nào cần đệm, khi nào cần chờ, khi nào timer dẫn tới retransmission?
2. Tại sao `record sequence number` và `message_seq` phục vụ hai mục đích khác nhau? Epoch giúp giải quyết điều gì khi gói thuộc trạng thái khóa cũ đến muộn?
3. Khi `SSLEngine` trả `NEED_UNWRAP_AGAIN`, vì sao vòng lặp không nên đợi datagram mới? Dữ liệu cần xử lý đang ở đâu?
4. Khi status đang `NEED_UNWRAP` và không có peer response, ai quyết định timeout và gọi phương thức nào để provider có cơ hội retransmit?
5. DTLS 1.3 dùng ACK record trong handshake. Đó có phải ACK cho mọi application datagram không? Hãy phân biệt ACK handshake và reliability nghiệp vụ.
6. Một `SSLEngine` DTLS 1.2 chạy trên Java 17 có thể tự động hiểu ACK/epoch theo DTLS 1.3 chỉ vì RFC 9147 đã được chuẩn hóa không? Bạn sẽ xác minh khả năng đó ở đâu?
7. Nếu handshake hoàn tất nhưng identity peer chưa được kiểm tra đúng, kết nối có thực sự đáng tin cậy cho nghiệp vụ không?

## Ghi nhớ

- DTLS bảo vệ datagram trên một tầng truyền không bảo đảm delivery/order; **handshake cần được tái truyền đúng cơ chế**, còn application data loss/order thường do lớp ứng dụng quyết định.
- **Record sequence/epoch** phục vụ trạng thái bảo vệ record và anti-replay; **message sequence/fragment offset** giúp tái lắp handshake đến sai thứ tự.
- **DTLS 1.2** dùng flight/timer; **DTLS 1.3** có ACK record cho handshake và chính sách retransmission chi tiết hơn.
- Java `SSLEngine` **không tự vận chuyển UDP**: ứng dụng cung cấp socket, timer, buffer, task execution và event loop.
- Trong JSSE, `NEED_UNWRAP_AGAIN` cần được xử lý ngay; khi timeout dù đang `NEED_UNWRAP`, gọi `wrap` có thể tạo gói retransmit.
- Kiểm thử đúng phải **drop/reorder/duplicate các datagram DTLS hợp lệ** và quan sát cả trạng thái giao thức lẫn trạng thái API.

### Tài liệu chuẩn đang áp dụng

- [IETF RFC 9147 — The Datagram Transport Layer Security (DTLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc9147.html), đặc biệt các phần về record number/epoch, handshake flights, ACK, timer và retransmission.
- [IETF RFC 6347 — Datagram Transport Layer Security Version 1.2](https://www.rfc-editor.org/rfc/rfc6347.html), đặc biệt handshake sequence, fragmentation, retransmission và replay detection — vẫn cần cho triển khai DTLS 1.2.
- [Oracle Java SE 24 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/24/security/java-secure-socket-extension-jsse-reference-guide.html), phần **SSLEngine for DTLS**, **Handling Retransmissions** và **NEED_UNWRAP_AGAIN**.
- [Oracle Java SE 24 — JDK Providers](https://docs.oracle.com/en/java/javase/24/security/oracle-providers.html), danh sách phiên bản DTLS do SunJSSE hỗ trợ.
- [Oracle Java SE 21 — SSLEngine API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html) và [SSLEngineResult.HandshakeStatus](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html).