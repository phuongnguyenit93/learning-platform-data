# 15.9 Phân biệt TLS trên luồng với DTLS trên datagram

## 1. Học gì trong bài này?

**TLS (Transport Layer Security)** và **DTLS (Datagram Transport Layer Security)** đều dùng handshake và lớp record để bảo vệ trao đổi dữ liệu qua mạng không tin cậy. Chúng có chung những mục tiêu như bảo mật nội dung, xác thực bản tin và (khi cấu hình phù hợp) xác thực peer, nhưng **có giả định vận chuyển hoàn toàn khác nhau**:

- **TLS trên luồng:** thường chạy trên **TCP**, nhận một **byte stream tin cậy, đúng thứ tự**. TCP chịu trách nhiệm đưa byte đến đúng thứ tự hoặc báo kết nối đã hỏng; TLS bảo vệ nội dung byte stream đó.
- **DTLS trên datagram:** thường chạy trên **UDP**, không đòi mọi datagram đều phải đến hoặc đến theo thứ tự. DTLS bổ sung xử lý handshake bị mất/đảo, số thứ tự record và cơ chế chống replay để bảo vệ dữ liệu mà **vẫn giữ datagram semantics**.

Câu nói cần nhớ: **TLS/TCP bảo vệ một luồng byte có thứ tự; DTLS/UDP bảo vệ các datagram có thể mất, trùng, đến muộn hoặc đảo thứ tự.** DTLS **không biến UDP thành TCP**.

Bài này nằm trong chủ đề **Nền tảng TLS** và tập trung vào phân biệt transport/record semantics, xử lý handshake, chi phí mạng, cách chọn API Java 17+ và kiểm thử. Ví dụ runnable ở phần 8 là **demo TCP/UDP + khám phá JSSE TLS/DTLS**, không phải hai kết nối bảo mật đã hoàn thành TLS/DTLS handshake; sự khác nhau được nêu rõ để không gây ảo tưởng bảo mật.

### Mục tiêu sau bài

1. Phân biệt **TCP stream**, **UDP datagram**, **TLS record** và **DTLS record**.
2. Giải thích vì sao UDP không thể chỉ “nhét TLS vào” mà không thay đổi giao thức.
3. Biết DTLS xử lý **handshake retransmission, fragmentation, reordering, epoch/sequence và replay detection**.
4. Chọn đúng **`SSLSocket`/`SSLServerSocket` cho TLS/TCP** hoặc **`SSLContext("DTLS")` + `SSLEngine` + datagram I/O** trong Java.
5. Nhận biết DTLS không mặc nhiên bảo đảm **độ tin cậy, thứ tự và xử lý giao dịch đúng một lần**.
6. Đánh giá khi nào chọn TLS, DTLS hoặc QUIC/TLS 1.3 cho bài toán mạng.

## 2. Mô hình phân tầng: đừng trộn transport và security

```text
        TLS/TCP thông dụng                      DTLS/UDP thông dụng
  +-----------------------------+        +------------------------------+
  | Ứng dụng: HTTP, RPC, ...     |        | Ứng dụng: realtime, sensor...|
  +-----------------------------+        +------------------------------+
  | TLS: handshake + records     |        | DTLS: handshake + records    |
  | encrypt, integrity, identity |        | encrypt, integrity, identity |
  +-----------------------------+        +------------------------------+
  | TCP: stream byte tuần tự     |        | UDP: datagrams độc lập       |
  | tin cậy trong kết nối        |        | có thể mất/đảo/trùng         |
  +-----------------------------+        +------------------------------+
  | IP                           |        | IP                           |
  +-----------------------------+        +------------------------------+
```

**Ứng dụng** quyết định “một request là gì”; **transport** quyết định cách vận chuyển byte/gói tin; **TLS/DTLS** quyết định cách bắt tay, chọn khóa và bảo vệ dữ liệu. Không protocol nào tự suy ra người dùng có quyền thanh toán, ghi dữ liệu, hay dùng lại một request đã thực hiện hay không.

| Đơn vị | Có ý nghĩa gì? | Có giữ ranh giới ứng dụng không? |
| --- | --- | --- |
| TCP **byte stream** | Một chuỗi byte liên tục giữa hai endpoint | **Không**. Hai lần `write` có thể được đọc thành một hoặc nhiều lần `read` |
| TCP **segment** | Đơn vị truyền tải trên mạng của TCP | Không tương ứng với message ứng dụng |
| **TLS record** | Đơn vị framing/bảo vệ của TLS | Không nên dùng record boundary làm application message boundary |
| UDP **datagram** | Một gói tin có độ dài/địa chỉ nguồn đích riêng | Có ranh giới datagram, nhưng không có reliability hay order |
| **DTLS record** | Đơn vị bảo vệ của DTLS có metadata record/epoch | Được đóng gói vào datagram; không có bảo đảm delivery/in-order ở tầng ứng dụng |

**Lưu ý về UDP:** nếu một datagram lớn hơn bộ đệm `DatagramPacket`, nội dung có thể bị **truncation**; chương trình phải dùng `packet.getLength()` và kiểm tra giới hạn. Một UDP datagram không tự động đồng nghĩa một giao dịch nghiệp vụ, và DTLS record không tự động đồng nghĩa một request.

## 3. Bảng đối chiếu TLS stream và DTLS datagram

| Khía cạnh | TLS trên stream, thường TCP | DTLS trên datagram, thường UDP |
| --- | --- | --- |
| Yêu cầu transport | Reliable + ordered byte stream | Datagram không tin cậy, có thể out-of-order |
| Dữ liệu phía ứng dụng | Byte stream sau giải mã | Dữ liệu bảo vệ theo datagram/record |
| `write(A)`, `write(B)` | Nhận byte theo thứ tự `AB` nếu chuyển thành công; không giữ hai boundary | Có thể nhận `A,B`, `B,A`, chỉ `B`, lặp hoặc mất |
| Truyền lại gói mất | **TCP** retransmit | **DTLS handshake** có retransmission; application data **không tự retransmit** |
| Handshake | Dựa trên transport tin cậy, thứ tự | Có số thứ tự/fragment, buffering, timeout, retransmit |
| Record ordering | Dựa trên thứ tự stream và ngữ cảnh TLS record | Có record sequence/epoch để nhận ra record và reordering |
| Anti-replay | Chống sửa record/trộn thứ tự trong stream theo scheme | DTLS có cơ chế replay window phù hợp version/policy, nhưng không giải quyết business replay |
| MTU/packet size | TCP segmentation giúp che giấu chi tiết packet khỏi ứng dụng | Phải tính record overhead và path MTU, tránh IP fragmentation |
| Head-of-line | Mất một đoạn TCP có thể chặn byte sau trên cùng connection | Không bị TCP stream buộc giao đúng thứ tự; ứng dụng có thể tự giữ hàng đợi nếu cần |
| Định danh peer | Certificate/PSK + trust/hostname policy | Tương tự, nhưng phải kiểm soát UDP peer/session/DoS |
| Java JSSE | `SSLSocket`, `SSLServerSocket`, `SSLEngine` | `SSLContext.getInstance("DTLS")`, `SSLEngine`, tự quản lý UDP I/O |
| Độ trễ | Tùy congestion, packet loss, server, handshake, RTT | Tùy packet loss, MTU, NAT, retransmission handshake, logic ứng dụng; **không mặc nhiên nhanh hơn** |

**Bảo mật mật mã không đồng nghĩa độ tin cậy truyền tải.** DTLS có thể xác minh được một record nhưng **không ép được mạng phải gửi record đó tới nơi**. Việc thiết lập session thành công cũng không có nghĩa ứng dụng đã nhận mọi dữ liệu phía gửi đã phát.

## 4. TLS/TCP: một luồng byte, không phải hàng đợi thông điệp

Giả sử sender gọi:

```text
write("one")
write("two")
```

TCP cho bên nhận một chuỗi 6 byte:

```text
o n e t w o
```

Receiver có thể `read()` được `"o"`, `"net"`, `"wo"`; hoặc `"onetwo"`; hoặc bất kỳ cách chia hợp lệ khác. Việc sender `write` hai lần **không** buộc receiver `read` đúng hai lần. Điều này vẫn đúng khi thay socket thường bằng `SSLSocket` và dùng **TLS over TCP**.

### 4.1 Phải có framing ở tầng ứng dụng

Một giao thức ứng dụng trên TLS stream cần cách phân định message:

- **Length prefix:** trường độ dài (ví dụ 4 byte unsigned/giới hạn ứng dụng) rồi đúng số byte body.
- **Delimiter có escaping:** có quy tắc phân tách và escape đủ mạnh.
- **Framing chuẩn sẵn có:** HTTP/2, WebSocket, gRPC và các giao thức có cấu trúc riêng.

Đoạn dưới đây **không độc lập**: `tlsSocket` là `SSLSocket` đã được xác thực và handshake thành công, hai bên đồng thuận length-prefix:

```java
byte[] message = "ping".getBytes(java.nio.charset.StandardCharsets.UTF_8);
java.io.DataOutputStream output =
        new java.io.DataOutputStream(tlsSocket.getOutputStream());
output.writeInt(message.length);
output.write(message);
output.flush();

// Ở bên nhận, trên một SSLSocket khác đã xác thực:
java.io.DataInputStream input =
        new java.io.DataInputStream(peerSocket.getInputStream());
int length = input.readInt();
if (length < 0 || length > 65536) {
    throw new java.io.IOException("Invalid frame length");
}
byte[] received = new byte[length];
input.readFully(received);
```

Việc **kiểm tra upper bound trước khi cấp phát** là bắt buộc trong một hệ thống nhận dữ liệu từ peer chưa đáng tin hoàn toàn. Không viết code chỉ gọi `read()` một lần rồi mặc định đã đủ body.

### 4.2 TCP và TLS chịu trách nhiệm khác nhau

- TCP: vận chuyển **byte** đúng thứ tự, retransmission, congestion/flow control, phát hiện kết nối hỏng.
- TLS: handshake, lựa chọn các tham số mật mã, xác thực peer khi cấu hình đúng, bảo vệ ciphertext/integrity; không thay thế framing ứng dụng.
- JSSE `SSLSocket`: kết nối hai lớp đó và cung cấp input/output stream sau khi đã xử lý TLS.

**TLS record không phải TCP segment**, và **TLS record không phải application frame**. JSSE có thể đóng gói một message ứng dụng trong nhiều records hoặc gom dữ liệu theo nhu cầu implementation.

## 5. DTLS/UDP: bảo vệ datagram nhưng vẫn cho phép loss/reorder

UDP gửi từng datagram với source/destination address và độ dài; không đảm bảo giao đủ, chỉ một lần, theo thứ tự. DTLS thêm bảo vệ mật mã cho record trên mô hình này:

```text
Ứng dụng tạo A ------> DTLS record A -----> UDP datagram A -----+
                                                               |
Ứng dụng tạo B ------> DTLS record B -----> UDP datagram B --+ |
                                                            | |
                                                   Mạng: mất/trễ/đảo/trùng
                                                            | |
                                         DTLS kiểm tra record, epoch, seq, tag
                                                   |
                                         Trả dữ liệu hợp lệ cho ứng dụng
```

Khi network deliver hai datagrams theo thứ tự `B` rồi `A`, DTLS có thể xử lý dữ liệu hợp lệ mà không bắt buộc xếp lại thành một **TCP-like stream**. Khi `A` mất, DTLS **không tự phát lại application record A**. Cần tránh hiểu nhầm rằng “datagram được bảo vệ mật mã” đồng nghĩa “datagram chắc chắn được giao”.

### 5.1 Vì sao không đơn giản dùng TLS records qua UDP?

RFC 6347 và RFC 9147 chỉ ra các khác biệt nền tảng:

1. **TLS records trên reliable stream** dựa vào thứ tự; khi mất hoặc reorder datagrams, các thông số thứ tự implicit có thể không còn đồng bộ. **DTLS** mang record number/epoch cần thiết để nhận dạng record và giải mã tương ứng.
2. **TLS handshake** có trình tự logic nhất định và giả định vận chuyển hỗ trợ thứ tự; **DTLS handshake** phải có message sequence, bộ đệm và cách tái sắp xếp.
3. Handshake messages như certificate chain có thể lớn hơn một datagram: **DTLS hỗ trợ phân mảnh và ghép lại handshake**.
4. Với UDP, attacker có thể giả địa chỉ nguồn và làm server phát nhiều byte đến nạn nhân: **DTLS có return-routability/cookie mechanisms** để giảm chi phí/anti-amplification trước khi tin kết nối.

DTLS còn phải xử lý **key epoch** khi đổi trạng thái khóa, bản tin handshake trễ và anti-replay record. Các chi tiết record layout **khác nhau giữa DTLS 1.2 và DTLS 1.3**, nên không tự suy rằng các trường bit trên wire giống nhau.

### 5.2 Sequence number và epoch

```text
Khái niệm:
   (epoch 1, record 100): protected(A)
   (epoch 1, record 101): protected(B)

Receiver có thể thấy record 101 trước record 100.
DTLS xác định record bằng metadata, không lấy vị trí gói đến làm thứ tự duy nhất.
```

**Epoch** phân biệt các thế hệ key/state khác nhau. **Sequence number/record number** giúp nhận diện record để xử lý reordering, kiểm tra integrity và chống replay theo scheme. Không dùng record sequence number như `transactionId` của thanh toán hoặc `messageId` của ứng dụng; hai lớp có threat model khác nhau.

### 5.3 Anti-replay là hạn chế record lặp, không phải exactly-once

Một implementation DTLS có thể dùng **sliding replay window**: nhận diện record đã thấy hoặc quá cũ, và loại bỏ. Tùy version/policy, replay detection có thể tùy chọn, giới hạn window khác nhau và việc gói đến trễ có thể khiến record hợp lệ bị bỏ.

Nếu client tạo một **record mới** chứa cùng payload `"transfer=42"`, record ấy có sequence mới và có thể vượt qua anti-replay DTLS; đây vẫn là một yêu cầu nghiệp vụ trùng. Do đó cấp ứng dụng cần **idempotency key**, sequence nghiệp vụ, expiry, nonces, state và policy chống replay riêng khi hành động có side effects.

### 5.4 DTLS handshake retransmission khác data retransmission

Trong DTLS, **handshake phải hoàn tất** để hai bên thống nhất khóa và xác thực. Nếu một flight handshake mất, protocol có **timeout và retransmission**. Bên ứng dụng JSSE phải quản lý timer của `SSLEngine`, sau đó kích hoạt việc tạo lại các handshake packets theo contract.

Ngược lại, với **application datagrams đã handshake xong**, DTLS không tự bảo đảm ACK/retransmission/ordering. Ứng dụng thời gian thực có thể chủ động bỏ dữ liệu cũ; hệ thống cần bảo đảm delivery phải tự bổ sung reliability hoặc dùng transport tin cậy.

**Chỉ trong lớp handshake** DTLS cần reliability để hoàn tất đàm phán. Đừng kết luận “UDP + DTLS luôn có TCP-like retransmission”.

### 5.5 Fragmentation: handshake có quy tắc riêng

DTLS có fragmentation/reassembly đối với **handshake messages** lớn hơn kích thước packet. Một DTLS record được đóng gói vừa một datagram theo mục tiêu của protocol; nhưng UDP datagram lớn vẫn có thể gây **IP fragmentation** ở lớp dưới nếu vượt PMTU. Không coi việc DTLS xử lý handshake fragments là chức năng chia/gộp **toàn bộ file ứng dụng** hoặc một thông điệp business rất lớn.

Đối với payload lớn cần đúng thứ tự/đủ byte, dùng TLS/TCP hoặc giao thức đáng tin cậy được thiết kế rõ; nếu buộc UDP thì phải có segmentation, reassembly, per-message identification, max size, timeout, resend/ACK và chống cạn kiệt bộ nhớ.

## 6. TLS/DTLS security: giống về mục tiêu nhưng khác thuộc tính vận chuyển

Các cặp protocol thường gặp:

| Protocol | RFC | Kiểu transport |
| --- | --- | --- |
| TLS 1.2 | RFC 5246 | Reliable byte stream |
| TLS 1.3 | RFC 8446 | Reliable byte stream |
| DTLS 1.2 | RFC 6347 | Datagrams |
| DTLS 1.3 | RFC 9147 | Datagrams |

DTLS 1.3 dựa trên TLS 1.3, nhưng RFC 9147 đặc biệt lưu ý sự khác biệt về **order protection / non-replayability** vì datagram semantics. Đừng nói rằng DTLS bảo đảm mọi gói tới đúng thứ tự chỉ vì nó cung cấp confidentiality và integrity.

### 6.1 Java version khác giao thức version

Java 17 có **standard names** cho `SSLContext`: `TLS`, `TLSv1.2`, `TLSv1.3`, `DTLS`, `DTLSv1.0`, `DTLSv1.2`. Việc tên được chuẩn hóa **không bảo đảm** mọi Java runtime/provider triển khai mọi phiên bản. Java 17 có thể có DTLS 1.2 nhưng **không tự suy ra có DTLS 1.3** chỉ vì RFC DTLS 1.3 đã được công bố.

Ba câu hỏi cần tách:

- **Supported protocols?** `SSLEngine.getSupportedProtocols()` — provider có implementation/đường hỗ trợ?
- **Enabled protocols?** `SSLEngine.getEnabledProtocols()` — phiên bản nào được cho phép trên engine?
- **Negotiated protocol?** `engine.getSession().getProtocol()` **sau khi handshake thành công** mới phản ánh phiên được chọn.

**Không tự fallback** sang TLSv1.0/DTLSv1.0 hay vô hiệu hóa thuật toán khi bắt tay không tương thích. Cần kiểm tra policy bảo mật và lựa chọn một phiên bản được phê duyệt.

### 6.2 QUIC không phải DTLS

**HTTP/3 dùng QUIC trên UDP**, nhưng **không dùng DTLS**. RFC 9001 định nghĩa QUIC sử dụng **TLS 1.3 handshake/key schedule** để thiết lập bảo mật, còn QUIC tự xử lý packet protection, reliable streams và congestion control. QUIC không vận chuyển TLS application records theo cách TLS/TCP và cũng không đơn giản dùng `SSLContext.getInstance("DTLS")`.

Do đó:

- HTTPS HTTP/1.1/2 trên TCP: **TLS/TCP**.
- UDP application cần bảo vệ datagrams: **DTLS/UDP** có thể thích hợp.
- HTTP/3: **QUIC + TLS 1.3 integration** qua QUIC stack.

## 7. Java JSSE: `SSLSocket` khác `SSLEngine`

Java Secure Socket Extension (**JSSE**) có hai phong cách triển khai:

| Java API | Sử dụng phù hợp |
| --- | --- |
| `SSLSocket` / `SSLServerSocket` | TLS trên kết nối **stream**, thực hiện I/O qua socket TCP tương ứng |
| `SSLEngine` | TLS/DTLS crypto và handshake **tách biệt khỏi I/O**, ứng dụng tự chuyển ciphertext |
| `SSLContext.getInstance("TLS")` | Tạo TLS context theo provider |
| `SSLContext.getInstance("DTLS")` | Tạo DTLS context theo provider hỗ trợ |
| `DatagramSocket` / `DatagramChannel` | Gửi/nhận **UDP datagrams**; tự nó không cung cấp mã hóa/xác thực |
| `SSLParameters.setMaximumPacketSize(...)` | Hỗ trợ cấu hình kích thước network packet/record mong muốn, quan trọng với DTLS |
| `SSLEngineResult` | Status, handshake status và số byte đã tiêu thụ/sinh ra khi `wrap/unwrap` |

### 7.1 TLS stream: API ngắn gọn hơn

Đoạn sau là **mảnh code**, chỉ có thể chạy nếu `hostname` được cung cấp và server phù hợp:

```java
// Trong phương thức có throws IOException, trên Java 17+:
javax.net.ssl.SSLSocketFactory factory =
        (javax.net.ssl.SSLSocketFactory)
        javax.net.ssl.SSLSocketFactory.getDefault();
try (javax.net.ssl.SSLSocket socket =
        (javax.net.ssl.SSLSocket) factory.createSocket(hostname, 443)) {
    javax.net.ssl.SSLParameters p = socket.getSSLParameters();
    p.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(p);
    socket.startHandshake();
    // Phía ứng dụng đọc/ghi từ InputStream/OutputStream qua framing riêng.
}
```

Phải xác minh server certificate qua trust manager và endpoint identity, chọn version/cipher suites theo chính sách, cấu hình SNI/ALPN khi cần. **Không tạo trust manager tin mọi chứng thư** để cho demo chạy bằng mọi giá.

### 7.2 DTLS: `SSLContext("DTLS")` + `SSLEngine` + UDP transport

```text
Ứng dụng gửi plaintext
       |
  SSLEngine.wrap()   -- tạo DTLS protected record(s)
       |
DatagramSocket.send() -- gửi UDP datagram
       |
       mạng
       |
DatagramSocket.receive() -- nhận đúng datagram bytes
       |
  SSLEngine.unwrap() -- kiểm tra và giải mã record
       |
Ứng dụng xử lý plaintext hợp lệ
```

Khởi tạo context/engine là **chưa đủ** cho bảo mật. Với handshake thực cần **key managers / trust managers / SecureRandom** thích hợp, identity/peer selection, UDP read/write loop, state machine, retransmission timer và packet-size policy.

```java
// Mảnh minh họa: chỉ tạo engine, CHƯA handshake, CHƯA bảo vệ dữ liệu.
javax.net.ssl.SSLContext dtls = javax.net.ssl.SSLContext.getInstance("DTLS");
dtls.init(keyManagers, trustManagers, secureRandom);
javax.net.ssl.SSLEngine engine = dtls.createSSLEngine(peerHost, peerPort);
engine.setUseClientMode(true);
javax.net.ssl.SSLParameters p = engine.getSSLParameters();
p.setMaximumPacketSize(1200);
engine.setSSLParameters(p);
engine.beginHandshake();
// Cần một loop xử lý SSLEngineResult + DatagramSocket đúng chuẩn.
```

Đây là **fragment tích hợp**, không phải chương trình độc lập: `keyManagers`, `trustManagers`, `secureRandom`, `peerHost` và `peerPort` là dữ liệu/cấu hình của hệ thống, `engine.beginHandshake()` không tự giao tiếp với peer. Client không thể tự giải mã UDP datagrams nếu chưa hoàn thành handshake.

## 8. Ví dụ Java 17 chạy được: stream, datagrams và khả năng JSSE

Chương trình **`TlsDtlsTransportDemo.java`** cho phép quan sát: (1) TLS và DTLS context được provider hỗ trợ, (2) DTLS packet-size parameter, (3) hai TCP writes được đọc như một stream, (4) hai UDP datagrams được nhận thành hai gói riêng trên **loopback local**.

**Giới hạn bắt buộc:** TCP và UDP ở đây là **plain sockets, chưa được mã hóa**. Việc khởi tạo `SSLContext`/`SSLEngine` chỉ nhằm khám phá API; **không có TLS/DTLS handshake**, không có certificate verification và không có ciphertext trên network. Để thật sự bảo vệ payload phải dùng `SSLSocket` hoặc `SSLEngine.wrap/unwrap` sau handshake hoàn tất.

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public final class TlsDtlsTransportDemo {
    private static boolean supports(SSLEngine engine, String protocol) {
        return Arrays.asList(engine.getSupportedProtocols()).contains(protocol);
    }

    public static void main(String[] args) throws Exception {
        SSLContext tls = SSLContext.getInstance("TLS");
        SSLContext dtls = SSLContext.getInstance("DTLS");
        tls.init(null, null, null);
        dtls.init(null, null, null);

        SSLEngine tlsEngine = tls.createSSLEngine();
        SSLEngine dtlsEngine = dtls.createSSLEngine();
        tlsEngine.setUseClientMode(true);
        dtlsEngine.setUseClientMode(true);

        System.out.println("TLSv1.2 supported: " +
                supports(tlsEngine, "TLSv1.2"));
        System.out.println("DTLSv1.2 supported: " +
                supports(dtlsEngine, "DTLSv1.2"));

        SSLParameters parameters = dtlsEngine.getSSLParameters();
        parameters.setMaximumPacketSize(1200);
        dtlsEngine.setSSLParameters(parameters);
        System.out.println("DTLS max packet bytes: " +
                dtlsEngine.getSSLParameters().getMaximumPacketSize());

        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket listener = new ServerSocket(0, 1, loopback);
             Socket client = new Socket(loopback, listener.getLocalPort());
             Socket peer = listener.accept()) {
            client.getOutputStream().write("one".getBytes(StandardCharsets.UTF_8));
            client.getOutputStream().write("two".getBytes(StandardCharsets.UTF_8));
            client.getOutputStream().flush();
            byte[] six = peer.getInputStream().readNBytes(6);
            System.out.println("TCP stream bytes: " +
                    new String(six, StandardCharsets.UTF_8));
        }

        try (DatagramSocket receiver =
                     new DatagramSocket(new InetSocketAddress(loopback, 0));
             DatagramSocket sender = new DatagramSocket()) {
            receiver.setSoTimeout(3000);
            byte[] first = "one".getBytes(StandardCharsets.UTF_8);
            byte[] second = "two".getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(first, first.length,
                    loopback, receiver.getLocalPort()));
            sender.send(new DatagramPacket(second, second.length,
                    loopback, receiver.getLocalPort()));

            String[] messages = new String[2];
            for (int i = 0; i < messages.length; i++) {
                byte[] buffer = new byte[64];
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                receiver.receive(packet);
                messages[i] = new String(packet.getData(), packet.getOffset(),
                        packet.getLength(), StandardCharsets.UTF_8);
            }
            System.out.println("UDP datagrams received: " + messages.length);
            System.out.println("UDP payloads (this local run): " +
                    String.join(" | ", messages));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TlsDtlsTransportDemo.java
java TlsDtlsTransportDemo
```

**Stdout đã quan sát trong môi trường kiểm thử JDK có provider DTLS 1.2 và network loopback:**

```text
TLSv1.2 supported: true
DTLSv1.2 supported: true
DTLS max packet bytes: 1200
TCP stream bytes: onetwo
UDP datagrams received: 2
UDP payloads (this local run): one | two
```

**Phân tích:**

1. `TLSv1.2 supported` và `DTLSv1.2 supported`: là kết quả **capability của provider**. Nếu runtime không có DTLS, `SSLContext.getInstance("DTLS")` có thể ném `NoSuchAlgorithmException`, hoặc supported protocols khác.
2. `DTLS max packet bytes: 1200`: xác nhận `SSLParameters` nhận cấu hình. Nó **không** chứng minh mọi IP path đều có MTU 1200 byte hay rằng handshake đã hoàn tất.
3. TCP gửi `"one"` rồi `"two"`, `readNBytes(6)` trả `"onetwo"`, minh họa stream không có message boundary của lệnh `write`.
4. UDP hai lần `send` tạo hai datagrams riêng; hai lần `receive` lấy hai datagram. Loopback trong lần chạy giữ thứ tự `"one"`, `"two"`, nhưng UDP **không bảo đảm** điều này trên mọi mạng.
5. `setSoTimeout(3000)` chỉ chống treo vô hạn khi một UDP datagram không đến; trên mạng có packet loss, chương trình có thể ném `SocketTimeoutException`. Đó là kết quả **hợp lệ của transport không đáng tin**, không phải lỗi trong định nghĩa DTLS.

Chương trình dùng **localhost/loopback** nên không cần server ngoài hoặc certificate fixture. Cũng vì vậy nó **không kiểm tra bảo mật của TLS/DTLS**, chỉ kiểm tra những khác biệt vận chuyển và khả năng tạo engine. Không mang mẫu raw UDP ấy vào ứng dụng cần encryption mà không triển khai `SSLEngine` đầy đủ.

## 9. Cách xử lý DTLS `SSLEngine` đúng chuẩn

DTLS engine tách phần **mật mã/handshake** khỏi phần **UDP I/O**. Một ứng dụng DTLS thực cần:

1. `SSLContext.getInstance("DTLS")`, `init` với credentials/trust đáng tin và entropy.
2. `createSSLEngine(peerHost, peerPort)`, `setUseClientMode(true/false)`.
3. Cấu hình protocols, cipher suites, packet size, peer identity và client auth policy nếu cần.
4. `beginHandshake()`.
5. Xử lý `SSLEngineResult.HandshakeStatus`: **`NEED_TASK`**, **`NEED_WRAP`**, **`NEED_UNWRAP`**, **`NEED_UNWRAP_AGAIN`**, `NOT_HANDSHAKING` và `FINISHED`.
6. Đưa `wrap` output vào **UDP datagram(s)**; đưa bytes của **datagram nhận thực tế** vào `unwrap`.
7. Khi handshake đang `NEED_UNWRAP` và mạng timeout, application timer có thể phải **gọi `wrap` để kích hoạt retransmission handshake flight**, theo hướng dẫn DTLS JSSE.
8. Xử lý `BUFFER_OVERFLOW`, `BUFFER_UNDERFLOW`, `CLOSED`, `SSLException`, delegated tasks, peer validation, close alerts và giới hạn tài nguyên.
9. Chỉ đưa app data vào kênh bảo mật khi handshake/policy thành công.

Bảng `HandshakeStatus`:

| Trạng thái | Hành động |
| --- | --- |
| `NEED_WRAP` | Gọi `wrap`, gửi network output đúng định dạng |
| `NEED_UNWRAP` | Chờ UDP data, có timeout; có thể trigger retransmit ở DTLS handshake |
| `NEED_UNWRAP_AGAIN` | Gọi `unwrap` lần nữa trên dữ liệu **đã được engine buffer**, không đợi datagram mới |
| `NEED_TASK` | Chạy các delegated tasks từ `getDelegatedTask` |
| `FINISHED` | Hoàn thành handshake được báo qua kết quả thao tác |
| `NOT_HANDSHAKING` | Engine hiện không trong handshake |

Bảng `SSLEngineResult.Status`:

| `Status` | Ý nghĩa |
| --- | --- |
| `OK` | Thao tác thành công theo trạng thái |
| `BUFFER_UNDERFLOW` | Input chưa đủ bytes xử lý |
| `BUFFER_OVERFLOW` | Buffer output không đủ chỗ |
| `CLOSED` | Engine/direction đóng |

Không viết vòng lặp gọi `unwrap()` liên tục khi chưa có input mới và không phải `NEED_UNWRAP_AGAIN`, tránh **busy spin**. Không nối tùy tiện datagrams khác nhau thành một TCP stream rồi đưa vào một lần unwrap. JSSE hướng dẫn DTLS `SSLEngine.wrap()` tạo **tối đa một DTLS record trong một lần gọi** để tiện chuyển thành UDP packet phù hợp.

Đây là sơ đồ **giả mã**, không phải chương trình JSSE chạy độc lập:

```text
context = DTLS context initialized with appropriate key/trust managers
engine  = context.createSSLEngine(peer identity)
engine.setUseClientMode(client or server)
configure maximum packet size, ciphers/protocols, authentication policy
engine.beginHandshake()

while handshake not complete:
  NEED_TASK          => run delegated tasks
  NEED_WRAP          => wrap(empty app buffer) => send ciphertext datagram
  NEED_UNWRAP        => UDP receive with timeout => unwrap(received datagram)
                        timeout => retransmit handshake flight via engine as documented
  NEED_UNWRAP_AGAIN  => unwrap engine-buffered data (no network receive)
  errors/buffer state=> react safely; close/fail handshake if invalid

after authenticated handshake:
  outgoing application data => wrap => send datagrams
  received UDP datagram     => unwrap => process authenticated app data
  application handles replay of commands, packet ordering/loss if required
```

**Tại sao chỉ là pseudocode?** Một server DTLS an toàn còn cần key/certificate/PSK provisioning, peer/source-address association, cookie/anti-amplification protection, bounds, retransmission policy, receive queues, duplicate/reordered packets, concurrency và graceful close. Không nên rút gọn chúng thành code 10 dòng rồi tuyên bố đó là DTLS server production.

## 10. Packet size, path MTU và tránh IP fragmentation

Với TCP, tầng transport quản lý segmentation. Với UDP, một datagram quá lớn có thể bị **IP fragmentation**, không qua được đường mạng hoặc mất toàn bộ datagram vì chỉ một fragment bị mất. DTLS encryption overhead cũng làm tăng kích thước so với plaintext.

Trong Java, dùng:

```java
// Mảnh code trong phương thức có engine DTLS đã tạo:
javax.net.ssl.SSLParameters p = engine.getSSLParameters();
p.setMaximumPacketSize(1200);
engine.setSSLParameters(p);
```

`setMaximumPacketSize` nêu **kích thước packet/record tối đa mong muốn**; trong triển khai thực phải tính **IP + UDP headers, tunnel/VPN overhead, DTLS record header/tag**, PMTU và version/cipher suite. Con số **1200** trong bài chỉ là cấu hình minh họa, không phải quy định mọi mạng hay bảo đảm không bị fragmentation. Theo JSSE guidance, đừng đặt quá thấp (chẳng hạn dưới 256 byte) vì handshake messages nhỏ có thể cũng cần fragment.

**Handshake fragmentation** do DTLS hỗ trợ khác với **application fragmentation/reassembly**: nếu gửi một message ứng dụng vài megabyte, bạn cần một protocol chuyên biệt hoặc reliable transport; không thể chỉ trông chờ DTLS tự chia/gộp và retransmit hết payload.

## 11. NAT, identity và DoS cần được nghĩ đến

- **NAT rebinding/source tuple:** UDP source IP:port có thể đổi, nhưng cryptographic association phải vẫn kiểm soát đúng. **Không** giả định mọi JSSE provider hỗ trợ DTLS Connection ID (CID) hay migration.
- **Spoofing/amplification:** UDP cho phép tấn công giả source; ứng dụng/server phải giới hạn handshake allocation, rate, bytes gửi trước khi xác minh peer và session state; cookie/return-routability không thay thế quản lý DoS.
- **Trust anchors/hostname/PSK identity:** DTLS có cùng nhu cầu xác thực peer giống TLS. Không dùng trust-all certificate manager hay bỏ qua endpoint identity.
- **Datagram replay:** DTLS record anti-replay không thay thế idempotency và anti-replay ở nghiệp vụ.
- **Record errors:** dữ liệu không qua AEAD/MAC/tag verification phải bị từ chối; không dùng plaintext tạm/partial từ input chưa xác thực.
- **Fallback:** nếu `SSLContext("DTLS")` hoặc cipher suite không được runtime hỗ trợ, phải cấu hình một provider/giao thức được phê duyệt thay vì âm thầm gửi UDP plaintext.
- **0-RTT/early data:** với giao thức/version có hỗ trợ, cần threat model replay riêng; không dùng cho thao tác nhạy cảm không idempotent nếu không có bảo vệ phù hợp.

## 12. Chọn TLS, DTLS hay QUIC trong tình huống thực tế

| Trường hợp | Thường chọn | Giải thích |
| --- | --- | --- |
| HTTPS/REST trên TCP | TLS/TCP | Hạ tầng chuẩn, byte stream, certificate/hostname trust |
| gRPC/HTTP/2 | TLS/TCP | HTTP/2 tự framing trên stream |
| Truyền file đúng/đủ và theo thứ tự | TLS/TCP hoặc reliable transport phù hợp | Tránh tự phát minh reliability trên UDP |
| Trò chơi truyền state vị trí liên tục | DTLS/UDP có thể thích hợp | Gói cũ có thể bỏ qua, application tự quản lý sequence |
| Telemetry UDP, báo cáo realtime | DTLS/UDP có thể thích hợp | Giữ datagrams, bảo vệ integrity/confidentiality |
| Real-time voice/video | SRTP và cơ chế thiết lập khóa phù hợp (ví dụ DTLS-SRTP) | **Không** đồng nghĩa mọi gói media đi qua DTLS |
| HTTP/3 | QUIC/UDP + TLS 1.3 integration | QUIC không phải DTLS, có transport/packet protection riêng |
| Mạng bị firewall chặn UDP | TLS/TCP hoặc fallback protocol đúng chuẩn | DTLS không tự vượt mọi chính sách mạng |
| Giao dịch quan trọng cần exactly-once | Kênh bảo mật + idempotency/replay state ở application | Không protocol TLS/DTLS nào thay kiểm soát nghiệp vụ |

DTLS có thể giảm head-of-line blocking ở lớp vận chuyển cho một số ứng dụng, nhưng **không phải bảo đảm latency thấp nhất**. Với packet loss cao, handshake retransmission, thiếu PMTU, NAT/firewall hoặc logic ứng dụng phức tạp, hệ thống có thể chậm hoặc kém ổn định hơn một TCP/TLS stack tốt.

## 13. Lỗi phổ biến và khắc phục

| Hiện tượng/nhận định | Lý do | Cách xử lý |
| --- | --- | --- |
| "`DatagramSocket` nghĩa là DTLS" | UDP socket thuần không mã hóa | Kết hợp `SSLEngine` và handshake |
| "`SSLContext("DTLS")` đủ tạo secure channel" | Context/engine mới tạo chưa có authenticated peer | Init managers, handshake, wrap/unwrap datagrams |
| "`SSLSocket` chạy trực tiếp trên UDP" | Socket API đó dùng stream | Dùng `SSLEngine` cho DTLS |
| "UDP luôn giữ thứ tự trên loopback nên production cũng vậy" | Local observation không phải network guarantee | Kiểm thử loss/reorder/duplicate |
| "DTLS retransmit application data" | Protocol chỉ có cơ chế retransmission handshake | App tự resend/ACK hoặc reliable transport |
| "DTLS replay window đủ chống giao dịch trùng" | Record hợp lệ mới vẫn có thể chứa cùng message | Application idempotency |
| `NoSuchAlgorithmException` với DTLS | Runtime/provider không triển khai DTLS | Chọn provider được phê duyệt, không fallback sang plaintext |
| DTLS packet lỗi kích thước | PMTU, buffer, IP fragmentation | Set `MaximumPacketSize`, chọn MTU budget và max input |
| `NEED_UNWRAP_AGAIN` bị kẹt | Đợi mạng dù bytes nằm trong engine | Gọi `unwrap` lại không cần UDP receive |
| Handshake treo ở `NEED_UNWRAP` | Mất handshake flight hoặc chưa có timer | Quản lý timeout/backoff, trigger retransmission theo JSSE |
| `BUFFER_UNDERFLOW`/`BUFFER_OVERFLOW` | Input/buffer sai kích thước hoặc trạng thái | Cấp đúng packet data, điều chỉnh buffers, kiểm tra `SSLEngineResult` |
| `SSLHandshakeException` | Cert/key/trust/version/suite/peer error | Chẩn đoán cấu hình, không tắt verification |
| TCP `read()` cho ít hơn message | Stream không có message boundary | Length prefix + `readFully` và giới hạn |
| HTTP/3 bị gọi là DTLS | QUIC dùng TLS 1.3 handshake nhưng không DTLS record | Chọn QUIC implementation |
| JDK có TLSv1.3 nên tưởng có DTLSv1.3 | Khác protocol/version support | Đọc provider supported/enabled/negotiated |

## 14. Checklist thiết kế

- [ ] Xác định nhu cầu **reliable in-order byte stream** hay **best-effort datagrams**.
- [ ] Phân biệt rõ TLS/DTLS với TCP/UDP và application message framing.
- [ ] TLS stream có length-prefix/delimiter/framing hợp lệ; không suy `write` = `read`.
- [ ] DTLS có packet boundary, MTU budget, giới hạn input/buffer, timeout policy.
- [ ] Chọn Java API đúng: `SSLSocket` cho TLS stream, `SSLEngine` + datagrams cho DTLS.
- [ ] Cấu hình `SSLContext`, trust/keys, endpoint identity, versions/ciphers đúng policy.
- [ ] DTLS engine loop xử lý `NEED_WRAP`, `NEED_UNWRAP`, `NEED_UNWRAP_AGAIN`, `NEED_TASK`, buffer statuses và close.
- [ ] Có **handshake retransmission** nhưng không kỳ vọng application retransmission tự động.
- [ ] Anti-replay record không thay idempotency/transaction dedupe.
- [ ] Có tests về mất gói, reorder, duplicate, malformed datagrams, MTU reduction, NAT rebinding.
- [ ] Có DoS limits: packet/session/rate/memory/time và chống spoofing/amplification.
- [ ] Không mặc định RFC DTLS 1.3 đồng nghĩa mọi Java provider đã có DTLS 1.3.
- [ ] Không dùng `DatagramSocket` plain demo để truyền thông tin nhạy cảm.

## 15. Bài tập và câu hỏi tự đánh giá

**1.** Tại sao hai lần `SocketOutputStream.write("A")`, `write("B")` không bắt buộc tạo hai lần `read()` ở peer?  
Vì TCP/TLS là byte stream không có message boundary ứng dụng; receiver đọc được chuỗi byte theo cách hệ thống phân chia.

**2.** DTLS có tự biến datagrams bị mất thành stream đầy đủ như TCP không?  
**Không.** DTLS handshake có retransmission; application data có thể bị mất mà không có retransmission tự động.

**3.** Nếu UDP datagram `B` đến trước `A`, điều gì giúp DTLS nhận ra record không theo thứ tự?  
Record sequence/epoch và trạng thái crypto; việc dữ liệu ứng dụng nên chờ hay bỏ là quyết định protocol/app.

**4.** `setMaximumPacketSize(1200)` có chắc 1200 byte ứng dụng sẽ không bị IP fragmentation không?  
Không. Còn overhead IP/UDP/DTLS/tag/tunnel và PMTU; đây là giới hạn network record được cấu hình.

**5.** Tại sao `SSLContext.getInstance("DTLS")` và `DatagramSocket` chưa đủ để bảo mật?  
Chưa có key/trust managers, peer validation, handshake, DTLS wrap/unwrap và I/O pipeline.

**6.** `NEED_UNWRAP_AGAIN` nghĩa là nên gọi `DatagramSocket.receive()` ngay không?  
Không. Nó báo engine còn buffered handshake data; cần gọi `unwrap` tiếp không đợi gói mới.

**7.** DTLS record anti-replay có chống lặp một giao dịch chuyển tiền có chữ ký hợp lệ không?  
Không. Một record mới có thể chứa lại cùng command; cần idempotency key hoặc application replay state.

**8.** HTTP/3 có dùng DTLS không?  
Không. HTTP/3 dùng QUIC, QUIC tích hợp TLS 1.3 handshake nhưng dùng packet protection/stream/reliability riêng.

**9.** Tại sao một DTLS server phải cân nhắc cookie và rate limit?  
UDP cho phép giả source, tấn công spoofing/amplification hoặc làm cạn trạng thái server.

**10.** Có nên chọn DTLS chỉ vì “nhanh hơn TLS” không?  
Không. Chọn dựa vào datagram semantics, loss tolerance, latency trade-offs, MTU, firewall/NAT, tính sẵn có của implementation và chi phí vận hành.

## 16. Tài liệu tham khảo chuẩn

- [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): phần `SSLEngine`, DTLS handshake, `NEED_UNWRAP_AGAIN`, retransmission, maximum packet size.
- [Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên `SSLContext`/protocol cho TLS và DTLS.
- [Java SE 17 — `SSLContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): tạo TLS/DTLS context.
- [Java SE 17 — `SSLEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): `wrap`, `unwrap`, handshake và đóng engine.
- [Java SE 17 — `SSLEngineResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.html): operation status và handshake status.
- [Java SE 17 — `SSLParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): packet-size và endpoint-identification configuration.
- [Java SE 17 — `DatagramSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html): UDP I/O.
- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246), [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446).
- [RFC 6347 — DTLS 1.2](https://www.rfc-editor.org/rfc/rfc6347): record/epoch/sequence, handshake retransmission và replay.
- [RFC 9147 — DTLS 1.3](https://www.rfc-editor.org/rfc/rfc9147): thiết kế datagram, loss/reorder, handshake/record layer, replay considerations.
- [RFC 9001 — QUIC uses TLS](https://www.rfc-editor.org/rfc/rfc9001): QUIC dùng TLS 1.3 handshake nhưng không dùng DTLS record.
- [OpenJDK JEP 219 — Datagram Transport Layer Security](https://openjdk.org/jeps/219): tích hợp DTLS trong JSSE.

**Tổng kết:** **TLS/TCP** bảo vệ **byte stream tin cậy, theo thứ tự**; **DTLS/UDP** bảo vệ **datagrams có thể mất hoặc đảo thứ tự**, bổ sung handshake retransmission và record sequence/epoch nhưng **không cam kết application data reliability, order hay exactly-once**. Trong Java, chọn `SSLSocket` hoặc `SSLEngine` theo mô hình I/O thực và không nhầm hỗ trợ provider với một kết nối bảo mật đã handshake.
