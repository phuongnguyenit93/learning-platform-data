# Kiểm thử UDP với timeout, mất gói và bộ đệm nhỏ trong Java

## 1. Mục tiêu và phạm vi

UDP (*User Datagram Protocol*) trao đổi **datagram**: mỗi lần gửi tạo một thông điệp độc lập. UDP không tự đảm bảo gói đến nơi, không bắt buộc gói đến đúng thứ tự, không chống trùng lặp và không tự thử gửi lại. Vì thế, một chương trình Java có thể gọi `DatagramSocket.send(...)` thành công nhưng vẫn **không nhận được phản hồi**.

Bài này thuộc chủ đề **Kiểm thử** của module **Java 15** và tập trung vào ba tình huống thực tế:

1. **Timeout:** `receive(...)` chờ quá thời gian đã định mà không nhận được datagram.
2. **Mất gói hoặc mất phản hồi:** phía gửi hoặc nhận không thấy phản hồi trong một lần trao đổi; kiểm thử quy tắc retry, số lần thử và xử lý gói trùng.
3. **Bộ đệm nhỏ:** nơi nhận không chứa đủ một datagram hoặc hàng đợi nhận của hệ điều hành quá nhỏ khi lưu lượng lớn.

Ví dụ chính dùng API `java.net.DatagramSocket`, `DatagramPacket`, `SocketTimeoutException` và `StandardCharsets.UTF_8`. Những API này vẫn được hỗ trợ trong các Java hiện đại. Code chạy được với **JDK 17 trở lên** (và phần chức năng UDP liên quan cũng có trên Java 15), không dùng API đã bị loại bỏ.

**Điều cần phân biệt:** *timeout* chỉ là “chưa nhận được dữ liệu trước hạn”, **không chứng minh** gói đã mất. Gói có thể đang trễ, server chưa trả lời, phản hồi bị chặn, hoặc ứng dụng xử lý sai. Test phải kiểm tra hành vi quan sát được và đặt tên đúng cho tình huống mô phỏng.

## 2. UDP hoạt động ra sao trong lúc kiểm thử?

```text
Client                                Server
   | --- UDP request #42 -------------> |
   |                                    |  có thể nhận, bỏ qua,
   |                                    |  xử lý chậm hoặc trả lời
   | [chờ đến hết SO_TIMEOUT]           |
   | --- retry request #42 -----------> |
   | <------------ response #42 ------- |
   |                                    |
```

Khác với luồng byte TCP, UDP giữ ranh giới thông điệp: một `send(DatagramPacket)` gửi một datagram; một `receive(DatagramPacket)` nhận tối đa một datagram. Nếu vùng dữ liệu nhận quá ngắn, phần bị cắt **không chảy tiếp sang lần receive kế tiếp**.

| Tình huống | Quan sát thường gặp | Kết luận đúng |
|---|---|---|
| Không có datagram trước thời hạn | `SocketTimeoutException` tại `receive` | Hết thời gian chờ; chưa biết nguyên nhân |
| `send` trả về bình thường | Không nhất thiết có ACK | Hệ thống cục bộ chấp nhận thao tác gửi; không bảo đảm giao thành công |
| Server cố tình bỏ qua request | Client hết hạn chờ | Có thể tái hiện nhánh xử lý mất phản hồi một cách có kiểm soát |
| Datagram 8 byte, `DatagramPacket` nhận tối đa 4 byte | `getLength() == 4` và chỉ còn 4 byte đầu | Datagram đã bị cắt tại vùng nhận; các byte còn lại bị bỏ |
| `SO_RCVBUF` nhỏ khi có nhiều datagram dồn đến | Có thể thiếu datagram | Đây là vấn đề hàng đợi socket/OS, không giống cắt một datagram ở buffer Java |
| Gói đến muộn sau khi retry | Client có thể nhận phản hồi cũ | Cần mã yêu cầu, kiểm tra địa chỉ/port và khử trùng lặp |

Các nguyên tắc này vẫn đúng với `java.nio.channels.DatagramChannel`. Với kênh đó, nếu `ByteBuffer` nhận không đủ chỗ thì phần còn lại của datagram cũng bị loại bỏ. Trong chế độ non-blocking, `receive(ByteBuffer)` có thể trả về `null` nếu chưa có datagram; không nên nhầm tình huống đó với `SocketTimeoutException` của `DatagramSocket`.

## 3. API cần nắm để tạo test có kiểm soát

### 3.1. Tạo socket và chọn cổng thử nghiệm

```java
InetAddress loopback = InetAddress.getLoopbackAddress();

try (DatagramSocket socket = new DatagramSocket(0, loopback)) {
    System.out.println(socket.getLocalPort());
}
```

Đây là **đoạn minh họa**, cần import `java.net.*` hoặc import từng lớp để biên dịch. Truyền cổng `0` giúp hệ điều hành tự chọn **cổng còn trống**, tránh hard-code một cổng dễ xung đột trong CI. Bind vào **loopback** giúp bài test không phụ thuộc server ngoài Internet. Kết quả cổng thay đổi mỗi lượt nên không assert một số cố định.

### 3.2. Giới hạn thời gian `receive`

```java
socket.setSoTimeout(200); // 200 ms, phải gọi trước receive()
socket.receive(packet);   // ném SocketTimeoutException nếu hết hạn
```

- Tham số của `setSoTimeout` tính bằng **mili giây**.
- Giá trị dương giới hạn thời gian một lần **`receive` chặn**; `0` nghĩa là chờ không giới hạn.
- Khi quá hạn, `receive` phát sinh `SocketTimeoutException` nhưng **socket vẫn mở** và có thể nhận tiếp.
- Đây không phải “thời gian tối đa để UDP gửi thành công”, cũng không phải cam kết phản hồi sẽ đến trước thời hạn.
- Không nên assert “đúng 200 ms” trong test: lịch CPU, scheduler và tải máy khiến thời gian thực biến thiên.

Nếu test chờ trên socket mở mà **không** cài timeout, tiến trình CI có thể treo mãi. Mỗi ví dụ blocking receive đều nên có thời hạn hợp lý.

### 3.3. Gửi và nhận có đúng kích thước

```java
byte[] data = "PING".getBytes(StandardCharsets.UTF_8);
DatagramPacket outgoing =
        new DatagramPacket(data, data.length, targetAddress, targetPort);
socket.send(outgoing);

DatagramPacket incoming = new DatagramPacket(new byte[1024], 1024);
socket.receive(incoming);

String payload = new String(
        incoming.getData(),
        incoming.getOffset(),
        incoming.getLength(),
        StandardCharsets.UTF_8);
```

Đoạn trên **không phải chương trình độc lập**: `socket`, `targetAddress` và `targetPort` phải được khai báo; ví dụ đầy đủ nằm ở mục 5.

Quan trọng: dùng **`getLength()`** để chỉ giải mã những byte thực sự nhận được. Không giải mã cả mảng `getData()` nếu nó có vùng thừa, vì dữ liệu đệm có thể chứa byte cũ hoặc byte zero.

Nếu dùng lại một `DatagramPacket` sau lần nhận ngắn, hãy nhớ cập nhật giới hạn nhận bằng `setLength(buffer.length)` trước lần nhận mới; cách đơn giản hơn cho test là **tạo `DatagramPacket` mới** mỗi lần. Nếu quên reset độ dài, lần nhận tiếp theo có thể bị giới hạn bởi độ dài nhỏ từ lần trước.

## 4. Thiết kế bộ ba test: tách timeout, mất phản hồi và truncation

Để tránh phụ thuộc mạng bên ngoài, ví dụ dùng **hai socket trên loopback**, phân bổ cổng tự động và không tạo thread:

1. **Timeout không phản hồi:** socket chờ trên cổng riêng; không có gói nào được gửi tới, nên bắt được `SocketTimeoutException`.
2. **Mất phản hồi có chủ đích:** client gửi `REQ:42`. Server **thực sự nhận** request đầu tiên nhưng cố tình **không gửi phản hồi**. Client hết hạn, gửi lại một lần; server nhận yêu cầu thứ hai và gửi `ACK:42`. Đây là *fault injection ở tầng ứng dụng* để kiểm tra retry, **không phải chứng minh kernel hay mạng đã làm mất gói**.
3. **Bộ đệm packet quá ngắn:** bên gửi gửi `ABCDEFGH` (8 byte ASCII), bên nhận đưa vào `DatagramPacket` có buffer 4 byte. Test chỉ nhận `ABCD` và kiểm tra phần `EFGH` không tự xuất hiện trong lần `receive` tiếp theo.

Đây là **ba test tích hợp cục bộ** trên UDP thật. Để thử nghẽn hàng đợi hoặc tỉ lệ mất gói thực tế, cần một môi trường mạng kiểm thử riêng với công cụ fault injection có kiểm soát.

## 5. Chương trình Java hoàn chỉnh và kết quả thực thi

Tạo tệp **`UdpFaultTests.java`** đúng tên public class như sau.

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class UdpFaultTests {
    private static final InetAddress LOOPBACK = InetAddress.getLoopbackAddress();

    public static void main(String[] args) throws IOException {
        timeoutWithoutReply();
        deliberatelyIgnoreFirstRequest();
        truncateSmallPacket();
        System.out.println("PASS 3 tests");
    }

    private static void timeoutWithoutReply() throws IOException {
        try (DatagramSocket receiver = new DatagramSocket(0, LOOPBACK)) {
            receiver.setSoTimeout(200);
            expectTimeout(receiver);
            check(!receiver.isClosed(), "Timeout should not close the socket");
        }
        System.out.println("PASS timeout");
    }

    private static void deliberatelyIgnoreFirstRequest() throws IOException {
        try (DatagramSocket server = new DatagramSocket(0, LOOPBACK);
             DatagramSocket client = new DatagramSocket(0, LOOPBACK)) {
            server.setSoTimeout(2_000);
            client.setSoTimeout(200);
            byte[] request = "REQ:42".getBytes(StandardCharsets.UTF_8);
            DatagramPacket outgoing = new DatagramPacket(
                    request, request.length, LOOPBACK, server.getLocalPort());

            client.send(outgoing);
            DatagramPacket first = new DatagramPacket(new byte[64], 64);
            server.receive(first);
            check("REQ:42".equals(text(first)), "First request differs");
            // Simulate an application that discards the request: no reply.
            expectTimeout(client);

            client.send(outgoing); // One bounded retry for this example.
            DatagramPacket second = new DatagramPacket(new byte[64], 64);
            server.receive(second);
            check("REQ:42".equals(text(second)), "Retry differs");

            byte[] response = "ACK:42".getBytes(StandardCharsets.UTF_8);
            server.send(new DatagramPacket(
                    response, response.length,
                    second.getAddress(), second.getPort()));
            DatagramPacket reply = new DatagramPacket(new byte[64], 64);
            client.receive(reply);
            check("ACK:42".equals(text(reply)), "Wrong reply");
        }
        System.out.println("PASS simulated loss and retry");
    }

    private static void truncateSmallPacket() throws IOException {
        try (DatagramSocket receiver = new DatagramSocket(0, LOOPBACK);
             DatagramSocket sender = new DatagramSocket(0, LOOPBACK)) {
            receiver.setSoTimeout(2_000);
            byte[] sent = "ABCDEFGH".getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(
                    sent, sent.length, LOOPBACK, receiver.getLocalPort()));

            DatagramPacket small = new DatagramPacket(new byte[4], 4);
            receiver.receive(small);
            check(small.getLength() == 4, "Expected four received bytes");
            check("ABCD".equals(text(small)), "Unexpected prefix");

            // The remaining EFGH bytes are discarded, not queued as a second datagram.
            receiver.setSoTimeout(200);
            expectTimeout(receiver);
        }
        System.out.println("PASS small receive packet");
    }

    private static void expectTimeout(DatagramSocket receiver) throws IOException {
        try {
            receiver.receive(new DatagramPacket(new byte[64], 64));
            throw new AssertionError("Expected SocketTimeoutException");
        } catch (SocketTimeoutException expected) {
            // Expected: no datagram arrived within SO_TIMEOUT.
        }
    }

    private static String text(DatagramPacket packet) {
        return new String(packet.getData(), packet.getOffset(),
                packet.getLength(), StandardCharsets.UTF_8);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 -encoding UTF-8 UdpFaultTests.java
java UdpFaultTests
```

**Stdout khi cả ba bài test đạt:**

```text
PASS timeout
PASS simulated loss and retry
PASS small receive packet
PASS 3 tests
```

Mã này đã được biên dịch và chạy kiểm tra với JDK 21, đặt `--release 17`; stdout nhận được đúng bốn dòng trên. Các test kiểm tra sự kiện và dữ liệu, **không kiểm tra chính xác số mili giây đã trôi qua**. Trong CI bị giới hạn tài nguyên, có thể nâng các timeout cho nhận gói hợp lệ và chạy thử trên môi trường loopback cô lập để giảm nhiễu; không nên thay `SocketTimeoutException` bằng những lần `Thread.sleep(...)` tùy ý.

### Giải thích vì sao từng assertion có ý nghĩa

- `expectTimeout` bắt **đúng `SocketTimeoutException`**, không bắt mọi `IOException`. Vì vậy, lỗi đóng socket hoặc lỗi I/O bất thường không bị coi là “timeout hợp lệ”.
- Test đầu kiểm tra `!receiver.isClosed()` vì timeout **không tự đóng** socket.
- Test thứ hai dùng cùng request ID `42` ở lần gửi lại, giúp hiểu vì sao giao thức ứng dụng cần so khớp phản hồi với yêu cầu.
- Test thứ ba kiểm tra **cả độ dài và byte nhận được**. Có bốn byte không chứng minh toàn bộ gói ban đầu dài bốn byte, nên thực tế cần biết chiều dài thông điệp theo protocol hoặc một framing phù hợp.
- Các socket đóng tự động bằng `try-with-resources`, giúp tránh chiếm cổng sau test, kể cả khi assertion thất bại.

## 6. Timeout: test đúng nhánh xử lý lỗi

Một thiết kế test timeout tốt cần xác định:

- **Điều kiện kích hoạt:** không có datagram hợp lệ gửi vào socket trong thời gian chờ.
- **Hành vi cần assert:** ném `SocketTimeoutException` ở `receive` hoặc ứng dụng chuyển sang trạng thái retry/hết hạn theo quy tắc.
- **Trạng thái sau lỗi:** socket có thể tiếp tục được dùng nếu ứng dụng còn cần.
- **Giới hạn chờ:** giá trị dương, đủ lớn cho CI nhưng không kéo dài vô ích.
- **Điều không thể kết luận:** timeout **không chỉ ra** gói request đã mất, response đã mất hay server xử lý chậm.

Ví dụ quy trình client cần thiết kế riêng cho production:

```text
gửi request(id)
  -> chờ response trong một khoảng timeout
  -> nhận đúng id: hoàn tất
  -> timeout: nếu số lần thử còn đủ, gửi lại theo backoff
  -> hết số lần thử: trả lỗi có thể xử lý, ghi metric và log id
```

Không retry vô hạn và không dùng một timeout ngắn cực đoan cho mọi môi trường. Sau timeout, một response muộn **vẫn có thể đến**; phải xác minh mã yêu cầu và nguồn gửi, tránh gán nhầm response cũ cho request mới. Nếu ứng dụng gửi tác vụ có tác dụng phụ (thanh toán, ghi dữ liệu), retry phải có **idempotency key** hoặc cơ chế khử trùng lặp ở server.

Nếu dùng `DatagramChannel` non-blocking, nhận `null` từ `receive` có nghĩa là **hiện chưa có datagram**, không phải timeout; muốn chờ theo thời hạn thường cần `Selector`/deadline hoặc cơ chế lập lịch phù hợp.

## 7. Mất gói: kiểm thử trạng thái, không dựa vào may rủi

UDP không có ACK/retransmission mặc định. Trong chương trình trên, server nhận lần đầu rồi bỏ qua giúp kiểm tra **phản ứng của client khi không có ACK**. Đó là cách mô phỏng ổn định hơn việc trông chờ hệ điều hành làm mất một datagram trên loopback.

### 7.1. Những hướng lỗi nên được tiêm có chủ đích

| Fault injection | Kịch bản phải quan sát | Hành vi cần assert |
|---|---|---|
| Bỏ request trước khi xử lý | Server không thấy request; client timeout | Retry có giới hạn; không treo |
| Server nhận request nhưng không trả response | Tương đương nhánh “không nhận ACK” của client | Client timeout và retry |
| Server xử lý thành công nhưng response bị bỏ | Client gửi lại một request đã xử lý | Server không thực hiện tác vụ có tác dụng phụ lần thứ hai |
| Trì hoãn response quá timeout | Response cũ đến sau retry | Client kiểm tra request ID, bỏ phản hồi quá hạn |
| Trả hai response cùng ID | Phản hồi trùng lặp | Client xử lý đúng một lần |
| Đảo thứ tự response hoặc message | Gói số thứ tự cao đến trước | Ứng dụng xử lý thứ tự nếu giao thức đòi hỏi |
| Gửi message với ID không khớp | Datagram đến từ request khác | Không đánh dấu request hiện tại hoàn tất |
| Đóng socket khi đang chờ | `receive` thất bại | Test kiểm tra nhánh đóng/hủy tài nguyên |

Để kiểm thử có thể lặp lại, có thể tạo một lớp bọc transport hỗ trợ các hành động **drop / delay / duplicate / reorder**, hoặc sử dụng trình giả lập mạng trong môi trường integration test riêng. Đừng khẳng định tỉ lệ mất gói thực tế bằng vài lần gửi trên loopback: localhost thường truyền gói rất tốt và OS xử lý hàng đợi theo điều kiện riêng.

### 7.2. Retry không thể suy ra “gửi đúng một lần”

Client có thể timeout sau khi server **đã** xử lý request nhưng phản hồi bị mất. Gửi lại cùng request có thể làm server xử lý tác vụ lần thứ hai nếu không có cơ chế kiểm soát. Một giao thức ứng dụng đáng tin cậy hơn thường cần:

1. **Request ID** để ghép response và xử lý late/duplicate response.
2. **Giới hạn retry** và chính sách backoff (thêm jitter khi có nhiều client).
3. **Idempotency/deduplication** cho thao tác có tác dụng phụ.
4. **Kiểm tra nguồn nhận** (IP, port, và xác thực theo yêu cầu bảo mật) trước khi chấp nhận response.
5. **Telemetry**: tỉ lệ timeout, số lần retry, thời gian phản hồi và tỷ lệ retry thành công.

Không nên coi `send(...)` trả về bình thường là cam kết server đã nhận, và cũng không nên coi mọi lần timeout là “packet loss”. Đây là điểm cốt lõi cần test ở cấp giao thức.

## 8. Hai loại bộ đệm nhỏ phải tách rõ

Cùng gọi là “buffer nhỏ”, nhưng Java có ít nhất **hai tầng** rất khác nhau.

### 8.1. Bộ đệm trong `DatagramPacket` — cắt một datagram

```java
byte[] buffer = new byte[4];
DatagramPacket received = new DatagramPacket(buffer, buffer.length);
receiver.receive(received);
```

Nếu bên gửi gửi **8 byte** và datagram tới nơi, `received` chỉ có tối đa **4 byte**. Bốn byte dư của datagram đó **bị bỏ**, không thể “gọi `receive` thêm” để lấy phần còn lại. Test mục 5 kiểm tra đúng hành vi này bằng dữ liệu ASCII dài 8 byte.

**Không nhầm số ký tự với số byte**: UTF-8 mã hóa một số ký tự tiếng Việt thành nhiều byte. Nếu bài test quan tâm kích thước datagram, lấy `payload.getBytes(StandardCharsets.UTF_8).length`, không lấy `payload.length()`.

Nếu chỉ thấy `received.getLength() == buffer.length`, **chưa thể kết luận** đã bị cắt, vì datagram có thể đúng bằng giới hạn đó. Giao thức nên định nghĩa payload có độ dài rõ ràng, có header length hoặc cơ chế kiểm tra tính toàn vẹn, và từ chối datagram không đầy đủ. Với dữ liệu chưa tin cậy, phải giới hạn cả kích thước khai báo để tránh cấp phát bộ nhớ vô hạn.

### 8.2. Bộ đệm nhận của socket/OS — hàng đợi các datagram

`DatagramSocket.setReceiveBufferSize(int)` điều chỉnh gợi ý cho `SO_RCVBUF`, tức bộ đệm của **hệ điều hành** cho các datagram đang chờ ứng dụng đọc. `setSendBufferSize(int)` tương ứng với `SO_SNDBUF` bên gửi. Đây là các **gợi ý**: giá trị thực tế có thể bị điều chỉnh hoặc giới hạn bởi OS.

```java
try (DatagramSocket socket = new DatagramSocket()) {
    socket.setReceiveBufferSize(1024);  // Yêu cầu 1 KiB; OS có thể điều chỉnh.
    int actual = socket.getReceiveBufferSize();
    System.out.println("SO_RCVBUF thực tế = " + actual + " byte");
}
```

Đoạn code này độc lập khi import `java.net.DatagramSocket`; **stdout không có một giá trị số cố định** vì phụ thuộc nền tảng. Không viết test dạng `assertEquals(1024, socket.getReceiveBufferSize())`. Bạn có thể xác nhận `actual > 0` và đo tác động trên môi trường đã biết, nhưng không dùng một giá trị buffer để bảo đảm gói sẽ mất.

Khi nhiều datagram đến nhanh hơn ứng dụng nhận, hàng đợi socket có thể đầy và dẫn tới **mất nguyên datagram**. Nó khác với việc **cắt nội dung của một datagram** khi `DatagramPacket`/`ByteBuffer` quá nhỏ. Tùy implementation, kích thước `SO_RCVBUF` cũng có thể ảnh hưởng kích thước datagram tối đa có thể nhận; hành vi với packet lớn hơn `SO_RCVBUF` **không đồng nhất giữa các OS**.

| Thuộc tính | `DatagramPacket` data buffer | `SO_RCVBUF` |
|---|---|---|
| Nằm ở đâu | Mảng byte của ứng dụng Java | Bộ đệm nhận của hệ điều hành/socket |
| Mục đích chính | Nhận payload của **một datagram** | Giữ các datagram chờ ứng dụng đọc |
| Khi quá nhỏ | Một datagram bị cắt phần dư | Có thể bị drop datagram nếu hàng đợi quá tải |
| Cách điều chỉnh | Tăng độ dài mảng/`DatagramPacket` và framing | `setReceiveBufferSize` / `getReceiveBufferSize` |
| Test dễ dự đoán | Gửi 8 byte, nhận với buffer 4 byte | Phải đo trên OS và tải xác định; không assert số gói drop cứng |

Không tự xem `SO_RCVBUF` là “giới hạn kích thước message ở Java” hoặc là cách chắc chắn tạo lỗi truncation. Với `DatagramChannel`, `ByteBuffer.remaining()` xác định số byte tối đa có thể nhận trong một lần đọc; phần dư của datagram cũng bị bỏ.

### 8.3. Kích thước datagram và MTU

Datagram lớn dễ gặp giới hạn kích thước UDP/IP, phân mảnh IP và tăng rủi ro mất toàn bộ thông điệp nếu một mảnh không đến. Dùng kích thước payload phù hợp với **path MTU** và giao thức triển khai; đừng giả định một số byte cố định phù hợp với mọi mạng. Trong test nên có dữ liệu kích thước nhỏ, đúng giới hạn và vượt giới hạn ứng dụng đã định; khi nhận dữ liệu lớn, xác thực độ dài thực nhận thay vì âm thầm xem dữ liệu bị cắt là thành công.

## 9. Ma trận test đề xuất cho dịch vụ UDP

| Nhóm | Setup | Assertion quan trọng |
|---|---|---|
| Gửi/nhận hợp lệ | Sender và receiver trên loopback, cổng tự chọn | Nội dung, byte length, địa chỉ và port |
| Timeout | Không có datagram gửi đến | `SocketTimeoutException`; ứng dụng không treo |
| Timeout rồi nhận lại | Không ACK lần đầu, ACK lần retry | Giới hạn retry; nhận đúng ACK/ID |
| Timeout cuối cùng | Không ACK ở mọi lần thử | Trả trạng thái thất bại đúng, dừng retry |
| Phản hồi muộn | ACK cũ đến sau request mới | Không gán nhầm cho request mới |
| Trùng lặp | Gửi hai request/response cùng ID | Dedup, idempotency theo thiết kế |
| Tráo thứ tự | Sắp thứ tự datagram có chủ đích | Kiểm tra seq/order nếu protocol yêu cầu |
| Packet buffer nhỏ | Payload 8 byte, buffer 4 byte | Chỉ nhận 4 byte, phần dư không xuất hiện lần sau |
| Buffer đúng kích thước | Payload đúng bằng buffer | Nhận đầy đủ; không báo truncation giả |
| Buffer lớn hơn payload | Payload ngắn, buffer dư | Chỉ parse tới `getLength()`, bỏ byte thừa |
| Packet tái sử dụng | Một datagram ngắn rồi một datagram dài | `setLength`/tạo packet mới, không làm cắt gói thứ hai |
| Receive queue stress | Burst datagram cao + consumer chậm | Metric drop/loss; kết quả phụ thuộc OS và tải |
| Dữ liệu không hợp lệ | Sai length, header, ID, encoding | Từ chối thông điệp; không crash/không dùng dữ liệu hỏng |
| Hủy xử lý | Đóng socket đang chờ hoặc hủy task | Có đường thoát rõ ràng, giải phóng tài nguyên |

Trong **unit test**, ưu tiên giả lập thời gian, fault injection và transport để kiểm soát chính xác drop/delay. Trong **integration test**, dùng UDP thật trên loopback để xác nhận Java socket API, timeout, ranh giới datagram và decode. Trong **kiểm thử chịu tải hoặc mạng xấu**, thực hiện trên môi trường riêng đã chuẩn hóa OS, kernel, socket buffer, traffic profile và công cụ làm suy giảm mạng; không đặt giả định về số packet bị drop trên tất cả máy CI.

## 10. Những lỗi thường gặp khi test UDP

### 10.1. Bắt mọi lỗi I/O như timeout

`SocketTimeoutException` chỉ thể hiện hết hạn chờ nhận. `SocketException` có thể phản ánh socket bị đóng hay lỗi cấp hệ thống; một số lỗi mạng khác thuộc `IOException`. Bắt `IOException` rồi coi tất cả là “mất gói” sẽ che lỗi triển khai thật. Test nên xác nhận **đúng exception** hoặc trạng thái domain mà ứng dụng quy định.

### 10.2. Dùng port cố định, sleep để “đảm bảo” thứ tự

Port cố định có thể trùng khi CI chạy song song. `Thread.sleep(100)` không chứng minh peer đã bind hay xử lý xong. Dùng cổng `0`, bind trước khi gửi, timeout có giới hạn và **đồng bộ bằng sự kiện/ACK** khi cần nhiều thread. Ví dụ mục 5 chạy tuần tự để loại bỏ race không cần thiết.

### 10.3. Cho rằng mỗi lần `receive` trả về “một phần” của stream

UDP là datagram-based. Khi mảng nhận quá nhỏ, phần đuôi của datagram bị bỏ; `receive` tiếp theo không thể nối tiếp cùng datagram. Kiểm tra `getLength` và cấu trúc message **trước** khi parse. Nếu cần truyền payload lớn, thiết kế giao thức phân mảnh/tái lắp ở tầng ứng dụng hoặc cân nhắc giao thức phù hợp hơn.

### 10.4. Kết luận không có packet loss vì test loopback PASS

Loopback chủ yếu xác minh logic socket và ứng dụng. Test trong mạng thực còn cần quan sát jitter, mất gói, trùng lặp, reorder, packet fragmentation, firewall/NAT và congestion. Dữ liệu mạng xấu nên được **mô phỏng chủ động** hoặc đo trong môi trường riêng, không tạo test “may rủi”.

### 10.5. Tin rằng `setReceiveBufferSize(128)` sẽ tạo ra drop hay cắt mọi gói lớn

`SO_RCVBUF` là hint phụ thuộc OS, thường không giữ đúng kích thước yêu cầu và không tương đương `new byte[128]` trong `DatagramPacket`. Test mong đợi kiểu “gửi 129 byte thì chắc chắn mất” là không đáng tin. Muốn test **truncation có thể lặp lại**, sử dụng `DatagramPacket` hoặc `ByteBuffer` thật sự nhỏ; muốn test **queue overflow**, dùng load test có quan sát và điều kiện máy được ghi nhận.

### 10.6. Chỉ kiểm tra payload rồi bỏ qua nguồn và ID

Ứng dụng có thể nhận response từ một yêu cầu trước đó hoặc sender khác. Với request/response UDP, xác minh ID, peer address/port và thông tin xác thực theo yêu cầu hệ thống. Khi timeout và retry, xử lý ACK trùng/muộn để không đánh dấu nhầm thành công.

## 11. Bài tập tự kiểm tra

**Bài 1.** `setSoTimeout(300)` và `receive` phát sinh `SocketTimeoutException`. Kết luận nào hợp lệ?

**Đáp án:** Không có datagram tới đúng socket trong khoảng chờ đó; socket vẫn dùng được nếu chưa bị đóng. Không thể khẳng định request đã mất hay server đã nhận.

**Bài 2.** Server nhận request `REQ:9`, xử lý xong nhưng ACK bị mất. Client retry `REQ:9`. Vì sao phải có request ID?

**Đáp án:** Server có thể phân biệt request đã xử lý và tránh thực hiện tác vụ có tác dụng phụ hai lần; client dùng ID để chỉ nhận ACK phù hợp với request hiện tại.

**Bài 3.** Client gửi 10 byte, receiver tạo `DatagramPacket(new byte[6], 6)` và nhận thành công. Có thể gọi `receive` lần thứ hai để lấy bốn byte còn lại không?

**Đáp án:** Không. Datagram đầu đã bị cắt và bốn byte dư bị loại bỏ, không còn thành một datagram khác.

**Bài 4.** Test `setReceiveBufferSize(512)` nhưng `getReceiveBufferSize()` trả về 2304. Test có chứng minh Java sai không?

**Đáp án:** Không. `SO_RCVBUF` là hint, OS có thể điều chỉnh giá trị. Không assert đúng 512; dùng giá trị thực để quan sát, và khi đo loss hãy ghi rõ OS và điều kiện tải.

**Bài 5.** Test trên loopback không thấy mất gói sau 1.000 lần gửi. Có thể xóa mã retry không?

**Đáp án:** Không. UDP không bảo đảm delivery. Test loopback không bao quát mọi tuyến mạng và server; vẫn cần chiến lược timeout/retry/dedup theo yêu cầu ứng dụng.

**Bài 6.** Trên socket có buffer nhận 1024 byte, chương trình nhận bằng `new DatagramPacket(new byte[4], 4)`. Gửi datagram 8 byte sẽ ra sao?

**Đáp án:** Nếu datagram tới nơi, API nhận chỉ lấy tối đa bốn byte trong `DatagramPacket`. `SO_RCVBUF` 1024 byte không làm mảng Java tự tăng dung lượng.

## 12. Checklist vận dụng vào dự án

1. Xác định **protocol contract**: số byte tối đa, request ID, response ID, thứ tự, retry policy, idempotency, bảo mật.
2. Đặt **timeout dương** cho blocking `receive`; mọi đường lỗi phải có điểm dừng.
3. Xác nhận đúng **địa chỉ/port** và chọn cổng động trong test cục bộ.
4. Tách **receive packet capacity** với **SO_RCVBUF**; đo giá trị buffer socket thực tế khi phân tích throughput.
5. Kiểm tra **`getLength()` và byte offset** trước khi decode; không giả định data array chỉ chứa thông điệp.
6. Test riêng **timeout, deliberate drop, delayed ACK, duplicate, reorder và packet truncation**.
7. Chạy smoke test trên runtime và môi trường mạng triển khai; giám sát timeout, retry, loss và latency.
8. Giữ test lặp lại được: cố định dữ liệu, chủ động tiêm lỗi, không phụ thuộc kết quả may rủi trên Internet.

## 13. Ghi nhớ

- **`DatagramSocket.setSoTimeout`** giới hạn thời gian chờ tại `receive`; hết hạn tạo `SocketTimeoutException`, không tự đóng socket.
- **UDP không đảm bảo giao, thứ tự hoặc chống trùng**; request ID, retry có giới hạn và idempotency là trách nhiệm của giao thức ứng dụng khi cần độ tin cậy.
- **`DatagramPacket` nhỏ** có thể làm **truncated payload** của một datagram; phần bị cắt không thể nhận lại ở lần `receive` sau.
- **`SO_RCVBUF` nhỏ** liên quan đến khả năng xếp hàng datagram của OS, là hint không có kích thước/kết quả drop giống nhau trên mọi hệ điều hành.
- **Kiểm thử mất gói hiệu quả** là tiêm lỗi có chủ đích, assert trạng thái có thể quan sát và dùng môi trường mạng kiểm soát được.

### Tài liệu chính thức (API vẫn áp dụng hiện nay)

- [Java SE 25 — `DatagramSocket`: `send`, `receive`, `setSoTimeout`, `SO_RCVBUF`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html)
- [Java SE 25 — `DatagramPacket`: buffer, offset, length](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html)
- [Java SE 25 — `SocketTimeoutException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/SocketTimeoutException.html)
- [Java SE 25 — `DatagramChannel`: nhận UDP qua `ByteBuffer` và non-blocking](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [Java SE 25 — `StandardSocketOptions`: `SO_RCVBUF` / `SO_SNDBUF`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardSocketOptions.html)
