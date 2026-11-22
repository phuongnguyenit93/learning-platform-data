# Timeout nhận bằng SO_TIMEOUT trong UDP DatagramSocket (Java)

**`SO_TIMEOUT`** là tùy chọn cho phép giới hạn thời gian mà một lời gọi **`DatagramSocket.receive(DatagramPacket)`** phải chặn khi chưa nhận được datagram. Nếu quá thời hạn, Java ném **`SocketTimeoutException`**; **socket vẫn hợp lệ** và ứng dụng có thể thử nhận tiếp, hủy request hoặc đóng socket theo chính sách của mình.

Đây là kiến thức thuộc nhóm **UDP và datagram**, vẫn sử dụng trực tiếp trên **Java 15 và Java hiện đại** qua API `java.net.DatagramSocket`. Dù UDP nhẹ và thuận tiện cho các thông điệp độc lập, nó **không bảo đảm gói đến nơi, không bảo đảm thứ tự, không tự chống trùng lặp hoặc hỗ trợ request/response đáng tin cậy**. Timeout nhận chỉ giải quyết việc luồng không phải chờ vô hạn trong **một lần `receive`**, chứ không giải quyết mọi vấn đề tin cậy của giao thức.

## 1. Nhận UDP mặc định chờ như thế nào?

Chương trình đơn giản:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;

try (DatagramSocket socket = new DatagramSocket(0)) {
    byte[] data = new byte[1024];
    DatagramPacket packet = new DatagramPacket(data, data.length);

    socket.receive(packet); // Có thể chờ vô hạn khi không có datagram.
}
```

Đoạn mã trên là **mẫu độc lập về cú pháp**, nhưng không có bên gửi nên không nên chạy nó như một demo sẽ tự kết thúc. `new DatagramSocket(0)` yêu cầu hệ điều hành gán một cổng UDP local còn trống. Trước khi có datagram hoặc một sự kiện lỗi/đóng socket, `receive` chặn luồng.

Nếu receiver là một server đang phục vụ nhiều client, trạng thái chờ lâu có thể bình thường. Nhưng đối với client đợi phản hồi, polling, thao tác có deadline hoặc ứng dụng cần dừng có kiểm soát, việc chờ vô hạn thường không phù hợp.

Giải pháp trực tiếp là bật timeout **trước khi vào `receive`**:

```java
socket.setSoTimeout(800); // 800 mili giây cho mỗi lần receive.
socket.receive(packet);
```

Đây là **mã minh họa cần đặt trong ngữ cảnh đã có `socket` và `packet`**. Nếu sau khoảng chờ mà chưa nhận được datagram, `receive` ném `java.net.SocketTimeoutException`.

## 2. Ý nghĩa giá trị SO_TIMEOUT

| Giá trị truyền vào | Ý nghĩa | Kết quả |
| --- | --- | --- |
| `setSoTimeout(250)` | Chờ khoảng **250 ms** cho một lần blocking receive | Datagram tới thì return bình thường; quá hạn thì `SocketTimeoutException` |
| `setSoTimeout(1000)` | Chờ khoảng **1 giây** cho một lần receive | Cách xử lý tương tự |
| `setSoTimeout(0)` | **Tắt** timeout | Có thể chờ vô hạn; không phải non-blocking |
| `setSoTimeout(-1)` | Giá trị âm không hợp lệ | `IllegalArgumentException` ngay khi cấu hình |

`setSoTimeout` nhận **`int` tính bằng milliseconds**, không phải giây. Muốn 2 giây, dùng `2000`. Nếu muốn kiểm tra cấu hình hiện tại, gọi `socket.getSoTimeout()`; **giá trị 0 nghĩa là không giới hạn thời gian chờ**.

Các điểm phải phân biệt:

- **Per receive:** cấu hình tác động đến **mỗi lần** `DatagramSocket.receive(...)` chờ. Không phải tổng thời gian của 5 lượt retry.
- **Socket option:** giá trị gắn với **socket**, không gắn riêng với một `DatagramPacket`.
- **Thiết lập trước:** theo Javadoc, tùy chọn phải được bật **trước khi vào thao tác blocking** để có hiệu lực. Không trông chờ việc luồng khác thay timeout sẽ lập tức rút ngắn một lần receive đang chặn.
- **Độ chính xác thực tế:** thời điểm timeout có thể chịu ảnh hưởng của OS scheduler, thread scheduling và timer granularity; không phải cam kết dừng chính xác từng mili giây.
- **Sau timeout:** socket **không bị đóng**; `isClosed()` tiếp tục là `false` nếu không có thao tác đóng độc lập.

Ví dụ cấu hình nhỏ:

```java
import java.net.DatagramSocket;

public class TimeoutConfigDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramSocket socket = new DatagramSocket(0)) {
            socket.setSoTimeout(500);
            System.out.println(socket.getSoTimeout()); // 500
            socket.setSoTimeout(0);
            System.out.println(socket.getSoTimeout()); // 0
        }
    }
}
```

Đoạn trên không gọi `receive`, nên không có khả năng bị chặn bởi một gói chưa đến. Đây là mẫu ngắn bổ trợ; chương trình có gửi/nhận thực tế ở mục 5.

## 3. Cấu trúc xử lý timeout đúng

Cách phổ biến là:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketTimeoutException;

try (DatagramSocket socket = new DatagramSocket(0)) {
    socket.setSoTimeout(500);

    byte[] buffer = new byte[2048];
    DatagramPacket incoming = new DatagramPacket(buffer, buffer.length);

    try {
        socket.receive(incoming);
        System.out.println("Received " + incoming.getLength() + " bytes");
    } catch (SocketTimeoutException ex) {
        System.out.println("No datagram arrived within the timeout");
    }
}
```

Đây là ví dụ đầy đủ nhưng **kết quả phụ thuộc datagram thực tế có đến hay không**, nên không đưa stdout cố định. Trên cổng được hệ điều hành cấp và không có bên gửi, nó thường in thông báo timeout.

Khi bắt timeout, ứng dụng nên quyết định dựa trên ngữ cảnh:

- **Client UDP:** có thể retry một cách hữu hạn, trả lỗi timeout hoặc đổi sang cơ chế đáng tin hơn; không retry vô hạn.
- **Server UDP:** có thể dùng mỗi timeout để kiểm tra tín hiệu dừng, cập nhật metrics, kiểm tra deadline của các request.
- **Ứng dụng realtime:** có thể bỏ qua message đã quá hạn, nhưng cần kiểm soát số lần chờ và trạng thái tổng.
- **Tác vụ quan trọng:** không coi một timeout là bằng chứng server chưa xử lý request; có thể request đã xử lý, còn response bị mất.

Sơ đồ:

```text
Bind DatagramSocket vào IP/port nhận
               |
               v
    setSoTimeout(timeoutMs > 0)
               |
               v
        receive(packet)
        /       |        \\
       /        |         \\
Datagram     Hết hạn     Lỗi socket/I/O
  tới        thời gian       |
   |           |             v
   v           v       SocketException /
return     SocketTimeout  IOException khác
bình thường Exception        |
   |           |             |
   v           v             v
Validate   Retry hữu hạn,  Chẩn đoán lỗi,
packet     bỏ qua hoặc     xem socket còn
           hủy request     usable không
```

`SocketTimeoutException` là một loại `IOException`, nhưng **không báo rằng socket đã chết**.

## 4. DatagramPacket: đúng buffer, đúng độ dài

Một lần nhận cần nơi chứa bytes:

```java
byte[] buffer = new byte[2048];
DatagramPacket packet = new DatagramPacket(buffer, buffer.length);

socket.receive(packet);
```

Đoạn trên là mã minh họa. Sau `receive` thành công, đối tượng `DatagramPacket` chứa:

- `packet.getData()`: mảng byte đang dùng làm buffer.
- `packet.getOffset()`: vị trí byte đầu dữ liệu trong buffer.
- `packet.getLength()`: **số byte** nhận được ở datagram hiện tại.
- `packet.getAddress()` và `packet.getPort()`: IP và port của phía gửi.

Khi decode UTF-8, **không chuyển toàn bộ buffer thành String**, vì phần chưa được ghi có thể chứa byte cũ hoặc byte 0:

```java
import java.nio.charset.StandardCharsets;

String receivedText = new String(
        packet.getData(),
        packet.getOffset(),
        packet.getLength(),
        StandardCharsets.UTF_8);
```

Đây là đoạn minh họa phụ thuộc `packet` đã nhận. Với text đến từ mạng và yêu cầu reject UTF-8 không hợp lệ, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` thay vì mặc định thay thế ký tự lỗi.

### Tái sử dụng packet có thể làm gói tiếp theo bị cắt

Sau khi packet nhận `"OK"`, `packet.getLength()` có thể bằng **2**. Nếu dùng lại cùng packet để nhận datagram dài hơn, **giá trị length hiện tại có thể giới hạn lượng byte được ghi vào lần sau**. Vì vậy:

```java
packet.setLength(buffer.length); // Khôi phục receive capacity.
socket.receive(packet);
```

Nếu packet có offset khác 0, `setLength(...)` phải tính sao cho offset + length không vượt kích thước mảng.

Nếu message đến dài hơn capacity của packet, **datagram bị cắt** (*truncated*). Không có cách mặc định gọi `receive` lần nữa để lấy “phần còn lại” như TCP stream. Một datagram là một thông điệp rời rạc. Muốn bảo đảm không vượt kích thước, giao thức phải có giới hạn payload và buffer đủ lớn hoặc cơ chế xác thực chiều dài ở tầng ứng dụng.

Dữ liệu nhận được có thể là **datagram từ bên không mong đợi**. Chỉ việc nhận được bytes trước hạn không chứng minh đó là phản hồi hợp lệ của request đang chờ.

## 5. Chương trình Java 17+ hoàn chỉnh: timeout rồi nhận tiếp trên cùng socket

Ví dụ dùng **UDP loopback** để tự kiểm chứng mà không cần server bên ngoài, không dùng cổng cố định và không phụ thuộc Internet.

- Một socket receiver bind vào loopback với port 0 (hệ điều hành tự chọn port).
- Một socket sender khác cũng bind loopback.
- Receiver đặt timeout 150 ms rồi gọi `receive` **trước khi gửi**; nhận được timeout.
- Sau đó receiver vẫn mở, và sender gửi datagram `"pong"`.
- Receiver nhận thành công, đồng thời kiểm tra port nguồn và length.
- Nhận tiếp datagram dài hơn bằng cách **reset packet length**.
- Cuối cùng demo kiểm tra timeout 0 và timeout âm.

Lưu toàn bộ thành **`DatagramTimeoutDemo.java`** (UTF-8):

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class DatagramTimeoutDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (DatagramSocket receiver =
                     new DatagramSocket(new InetSocketAddress(loopback, 0));
             DatagramSocket sender =
                     new DatagramSocket(new InetSocketAddress(loopback, 0))) {

            receiver.setSoTimeout(150);
            System.out.println("timeoutMs=" + receiver.getSoTimeout());

            byte[] buffer = new byte[128];
            DatagramPacket incoming = new DatagramPacket(buffer, buffer.length);

            try {
                receiver.receive(incoming);
                System.out.println("firstReceive=unexpected");
            } catch (SocketTimeoutException ex) {
                System.out.println("firstReceive=timeout");
            }

            System.out.println("socketStillOpen=" + !receiver.isClosed());

            // Tăng timeout để thử nhận datagram gửi qua loopback.
            receiver.setSoTimeout(4000);
            send(sender, loopback, receiver.getLocalPort(), "pong");
            receiver.receive(incoming);

            System.out.println("firstMessage=" + readText(incoming));
            System.out.println("firstLength=" + incoming.getLength());
            System.out.println("senderPortMatches=" +
                    (incoming.getPort() == sender.getLocalPort()));

            // Khôi phục capacity khi reuse DatagramPacket.
            incoming.setLength(buffer.length);
            send(sender, loopback, receiver.getLocalPort(), "second-datagram");
            receiver.receive(incoming);

            System.out.println("secondMessage=" + readText(incoming));
            System.out.println("secondLength=" + incoming.getLength());

            // 0 = tắt timeout; không gọi receive sau khi tắt.
            receiver.setSoTimeout(0);
            System.out.println("timeoutDisabled=" +
                    (receiver.getSoTimeout() == 0));

            try {
                receiver.setSoTimeout(-1);
                System.out.println("negativeRejected=false");
            } catch (IllegalArgumentException ex) {
                System.out.println("negativeRejected=true");
            }
        }
    }

    private static void send(DatagramSocket socket,
                             InetAddress address, int port, String text)
            throws Exception {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        socket.send(new DatagramPacket(bytes, bytes.length, address, port));
    }

    private static String readText(DatagramPacket packet) {
        return new String(packet.getData(), packet.getOffset(),
                packet.getLength(), StandardCharsets.UTF_8);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DatagramTimeoutDemo.java
java DatagramTimeoutDemo
```

**Đầu ra đã biên dịch và chạy thử trên JDK 24, với UDP loopback hoạt động bình thường:**

```text
timeoutMs=150
firstReceive=timeout
socketStillOpen=true
firstMessage=pong
firstLength=4
senderPortMatches=true
secondMessage=second-datagram
secondLength=15
timeoutDisabled=true
negativeRejected=true
```

Chương trình không in thời gian đo thật hay số port ngẫu nhiên nên kết quả dễ kiểm tra. Nếu môi trường cô lập chặn UDP loopback, các lệnh `receive` sau khi gửi vẫn có thể timeout; khi ấy cần kiểm tra chính sách sandbox/firewall, không kết luận lỗi ở API `setSoTimeout`.

**Giải thích kết quả:**

| Dòng output | Ý nghĩa |
| --- | --- |
| `timeoutMs=150` | `getSoTimeout()` phản ánh cấu hình dương ban đầu |
| `firstReceive=timeout` | Lần nhận đầu chưa có datagram gửi đến nên hết hạn |
| `socketStillOpen=true` | Timeout **không tự đóng socket** |
| `firstMessage=pong` | Cùng receiver nhận được datagram sau timeout |
| `firstLength=4` | Độ dài payload `"pong"` là 4 byte |
| `senderPortMatches=true` | Port nguồn trong packet đúng port sender |
| `secondMessage=second-datagram` | Sau khi reset length, nhận được message dài hơn |
| `secondLength=15` | Message thứ hai dài 15 byte UTF-8 |
| `timeoutDisabled=true` | `setSoTimeout(0)` chuyển về chờ vô hạn |
| `negativeRejected=true` | Giá trị âm bị từ chối bằng `IllegalArgumentException` |

Demo cho thấy điểm quan trọng nhất của bài: **bắt `SocketTimeoutException` xong vẫn có thể dùng cùng một `DatagramSocket`**.

## 6. SO_TIMEOUT không phải deadline của cả request

Giả sử bạn gọi:

```java
socket.setSoTimeout(500);
for (int attempt = 0; attempt < 10; attempt++) {
    try {
        socket.receive(packet);
        break;
    } catch (SocketTimeoutException ex) {
        // Chờ tiếp một lượt...
    }
}
```

Đây là đoạn **minh họa phụ thuộc socket/packet đã khởi tạo**. Mỗi lần chờ có thể mất khoảng 500 ms, nên tổng thời gian chờ có thể tới **khoảng 5 giây hoặc hơn**, chưa tính xử lý và scheduling. **Không có “timeout toàn vòng lặp” tự động**.

Để thiết kế một UDP request/response cần giới hạn thời gian, nên có cả:

1. **Timeout từng lần nhận:** dùng `setSoTimeout(perAttemptMs)`, ví dụ 300 ms.
2. **Deadline tổng:** tính bằng thời gian đã trôi qua, ví dụ 2 giây kể từ khi phát request.
3. **Số lần thử tối đa:** ví dụ 3–5 lần thay vì lặp vô hạn.
4. **Quy tắc retry hợp lệ:** không gửi lại vô điều kiện các lệnh gây tác dụng phụ.
5. **Correlation ID:** chỉ chấp nhận datagram liên quan đúng request, không lấy “bất kỳ gói nào đến” làm câu trả lời.

Dùng **`System.nanoTime()`** để đo thời gian đã trôi qua vì nó phù hợp với elapsed time, khác với `System.currentTimeMillis()` có thể thay đổi khi đồng hồ hệ thống bị điều chỉnh.

Mẫu phác thảo **không độc lập** (giả định đã có `DatagramSocket socket` và logic validate phản hồi):

```java
long deadline = System.nanoTime()
        + java.util.concurrent.TimeUnit.SECONDS.toNanos(2);

for (int attempt = 1; attempt <= 5; attempt++) {
    long remainingNs = deadline - System.nanoTime();
    if (remainingNs <= 0) {
        break;
    }

    // Tránh làm tròn xuống 0 ms vì 0 lại nghĩa là vô hạn.
    long remainingMs = Math.max(1,
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(remainingNs));
    socket.setSoTimeout((int) Math.min(300L, remainingMs));

    DatagramPacket packet = new DatagramPacket(new byte[2048], 2048);
    try {
        socket.receive(packet);
        // Kiểm tra source, requestId, format và nội dung.
        // Chỉ kết thúc khi đúng phản hồi của request đang chờ.
        break;
    } catch (SocketTimeoutException ex) {
        // Chỉ tiếp tục khi còn deadline và retry vẫn được phép.
    }
}
```

**Giới hạn của phác thảo:** chưa cài đặt gửi request, chống trùng, xác thực và kiểm tra response thực tế. Một datagram không hợp lệ **không được** làm kết thúc request; trong production, cần lặp tiếp đến khi có một phản hồi hợp lệ hoặc hết deadline. Nếu socket được dùng chung, hãy quản lý việc thay `SO_TIMEOUT` và khôi phục cấu hình cho thao tác sau. Timeouts không phải hard real-time guarantee; khi còn dưới 1 ms thì `Math.max(1, ...)` có thể cho một lượt chờ hơi vượt deadline vì API chỉ nhận đơn vị mili giây.

### Vì sao cần một deadline tổng?

Một request có thể hết thời gian do **nhiều thao tác khác nhau**, không chỉ receive: gửi, retry, delay giữa các lần thử, đọc/parse, xử lý ở client và nghẽn thread pool. `SO_TIMEOUT` **không kiểm soát** các bước ấy. Deadline giúp ứng dụng quyết định khi nào trả kết quả timeout cho nghiệp vụ và ngừng chờ.

## 7. Hết timeout có cần gửi lại datagram không?

Không nhất thiết. **UDP là giao thức không bảo đảm giao hàng**:

- Datagram được gửi có thể bị mất trên mạng.
- Gói tới đích nhưng **response** bị mất.
- Gói có thể tới muộn, lặp lại hoặc sai thứ tự.
- Sender và receiver có thể đang hoạt động bình thường nhưng mạng/tường lửa/chính sách port chặn lưu lượng.
- Sender có thể gửi xong trước khi receiver bắt đầu chờ, nhưng datagram chưa chắc được giữ đủ lâu trong queue.
- Gói nhận tiếp sau một lần timeout có thể là **phản hồi cho request cũ**, không phải request mới.

Giả sử client gửi lệnh “trừ 100.000 VND” và timeout khi đợi phản hồi. Server **có thể đã thực hiện lệnh** nhưng phản hồi bị mất. Nếu client tự động gửi lại không có định danh request, khoản tiền có thể bị trừ hai lần.

Một giao thức UDP cần độ tin cậy ở tầng ứng dụng nên cân nhắc:

- **`requestId` duy nhất** trong payload và response.
- **Idempotency key / deduplication** ở server cho những thao tác có side effects.
- **Số lần retry hữu hạn**, per-attempt timeout và end-to-end deadline.
- **Backoff + jitter** để tránh nhiều client cùng retry gây quá tải.
- **Version/sequence** để xử lý gói đến sai thứ tự hoặc gói cũ.
- **Authentication/integrity** nếu cần chống giả mạo; source IP/port tự nó không đủ cho một ranh giới bảo mật nghiêm ngặt.
- **Payload size limit** để không cấp phát quá nhiều bộ nhớ hoặc chấp nhận datagram đã bị cắt.

Nếu yêu cầu giao hàng đúng thứ tự, quản lý stream và xác nhận tích hợp, đôi khi **TCP hoặc một giao thức có cơ chế tin cậy rõ ràng** sẽ phù hợp hơn tự xây lại toàn bộ trên UDP.

## 8. SO_TIMEOUT tác động lên API nào?

| API / hoạt động | `SO_TIMEOUT` của DatagramSocket |
| --- | --- |
| `DatagramSocket.receive(DatagramPacket)` | **Có**: giới hạn một lần chờ nhận |
| `DatagramSocket.send(DatagramPacket)` | **Không**: không phải send timeout |
| Xử lý dữ liệu, parse JSON, decode UTF-8 | **Không** |
| `Thread.sleep(...)` | **Không** |
| Tất cả request của một vòng retry | **Không**: phải có deadline riêng |
| `DatagramChannel.receive(ByteBuffer)` | **Không dùng trực tiếp** tùy chọn này để điều khiển NIO channel |
| `Socket.getInputStream().read()` của TCP | Có `Socket.setSoTimeout(...)` riêng |
| `ServerSocket.accept()` | Có `ServerSocket.setSoTimeout(...)` riêng |

Với Java NIO, `DatagramChannel` có thể là **non-blocking**, trong trường hợp đó `receive(ByteBuffer)` có thể trả `null` nếu chưa có datagram. Có thể kết hợp `Selector` và chờ readiness có timeout nếu ứng dụng cần event loop cho nhiều socket.

**Không trộn hai mô hình:** `DatagramSocket.setSoTimeout(...)` là API cho blocking receive trên `DatagramSocket`; `Selector.select(timeout)` là cơ chế chờ sự kiện của channel trong NIO. Nếu `DatagramSocket` liên kết với một `DatagramChannel` đang ở non-blocking mode, các lời gọi kiểu socket có thể ném `IllegalBlockingModeException` theo Javadoc.

Trong Java hiện đại, `DatagramSocket` vẫn là API chuẩn đang được hỗ trợ; không có lý do phải chuyển sang API cũ/nội bộ chỉ để có timeout nhận.

## 9. Phân biệt các ngoại lệ nhận UDP

| Tình huống | Ngoại lệ | Giải thích |
| --- | --- | --- |
| Quá hạn một lần nhận | `SocketTimeoutException` | Socket vẫn dùng được; ứng dụng quyết định retry/cancel |
| Giá trị `timeout` âm | `IllegalArgumentException` khi set | Lỗi cấu hình |
| Socket đã đóng hoặc bị đóng từ thread khác | `SocketException` | Khác timeout; không retry trên socket đã đóng |
| Lỗi socket/I/O khác | `SocketException` hoặc `IOException` | Xem thông tin lỗi và trạng thái socket |
| Socket UDP đã `connect(...)` đến đích không truy cập được | Có thể `PortUnreachableException` | Không được bảo đảm sẽ luôn phát hiện hoặc ném |
| DatagramChannel non-blocking mode được dùng qua socket wrapper | `IllegalBlockingModeException` | Cần đồng bộ mô hình blocking/NIO |
| Datagram tới bình thường | Không có ngoại lệ | Packet chứa địa chỉ/port nguồn, bytes và length |

Lưu ý **`SocketTimeoutException` kế thừa `InterruptedIOException`**, nhưng không có nghĩa timeout nhất thiết do `Thread.interrupt()` gây ra. Khi socket đang bị chặn trong `receive`, thao tác `socket.close()` làm luồng chờ nhận ném `SocketException`. Java hiện đại còn có những quy tắc riêng về interrupt trên socket gắn `DatagramChannel` hoặc virtual thread; hãy dựa trên Javadoc của phiên bản đang dùng.

Mẫu bắt ngoại lệ theo thứ tự cụ thể → rộng:

```java
try {
    socket.receive(packet);
    // Đã có datagram; còn phải kiểm tra nguồn và dữ liệu.
} catch (java.net.SocketTimeoutException e) {
    // Hết thời gian chờ; không tự đóng socket.
} catch (java.net.SocketException e) {
    // Có thể socket/network error hoặc socket đã đóng.
} catch (java.io.IOException e) {
    // Lỗi I/O còn lại.
}
```

Mẫu này **cần có socket và packet được tạo trước**. Không bắt `IOException` trước `SocketTimeoutException`, vì đó là subclass và nhánh catch sau sẽ không bao giờ được tới.

## 10. Checklist khi thiết kế UDP receiver có timeout

- [ ] Bind socket vào **đúng local address và port**. Dùng port 0 cho client/demo khi cần ephemeral port.
- [ ] Đặt **`setSoTimeout(positiveMillis)` trước `receive`**.
- [ ] Hiểu `0` là vô hạn và giá trị âm là lỗi.
- [ ] Có `try/catch SocketTimeoutException` để trả về trạng thái timeout hoặc retry hữu hạn.
- [ ] Đặt giới hạn **deadline toàn request** nếu có yêu cầu latency.
- [ ] Không retry thao tác nghiệp vụ có side effects mà thiếu idempotency/deduplication.
- [ ] Kiểm tra correlation ID, source và format trước khi nhận một datagram làm phản hồi hợp lệ.
- [ ] Dùng `packet.getOffset()`/`getLength()`, không đọc toàn bộ buffer.
- [ ] Reset `packet.setLength(buffer.length)` trước khi reuse packet; hoặc tạo packet mới.
- [ ] Giới hạn kích thước datagram và xử lý dữ liệu truncated/invalid.
- [ ] Đóng socket bằng `close()` hoặc `try-with-resources` khi kết thúc vòng đời.
- [ ] Đừng chia sẻ một socket cùng lúc cho nhiều luồng receive/đổi timeout mà không quản lý ownership rõ ràng.
- [ ] Phân biệt timeout với socket closed, I/O failure và invalid datagram.
- [ ] Có test thực trên loopback và môi trường triển khai, bởi firewall/sandbox/network policy có thể ảnh hưởng.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `setSoTimeout(0)` là chờ 0 ms | **0 = vô hạn**, không phải non-blocking |
| Giá trị âm có nghĩa vô hạn | `setSoTimeout(-1)` ném `IllegalArgumentException` |
| Timeout tự đóng DatagramSocket | `SocketTimeoutException` **không** đóng socket |
| Timeout là tổng thời gian của mọi lượt retry | Chỉ giới hạn **một lần receive** |
| SO_TIMEOUT ảnh hưởng cả `send` | Không; không phải send timeout |
| UDP không có phản hồi nghĩa là server chưa xử lý | Có thể request đã xử lý và response bị mất |
| Có packet là đã đúng response | Cần correlation ID và kiểm tra nguồn/nội dung |
| Reuse `DatagramPacket` không cần reset length | Message dài hơn có thể bị cắt |
| Decode toàn bộ `packet.getData()` | Cần dùng **offset + length** |
| Datagram dài bị cắt có thể nhận tiếp phần còn lại | Không giống TCP stream |
| `SocketTimeoutException` đồng nghĩa thread bị interrupt | Timeout I/O không đòi hỏi `Thread.interrupt` |
| NIO `DatagramChannel.receive` tự tuân thủ DatagramSocket SO_TIMEOUT | Đây là API khác, cần NIO/Selector phù hợp |

## 12. Bài tập và đáp án

**Câu 1.** Socket gọi `setSoTimeout(0)`, sau đó `receive(packet)` khi không có datagram. Nó có return ngay không?

**Câu 2.** Socket gọi `setSoTimeout(200)`, bị timeout ở lần đầu. Ứng dụng có được dùng **cùng socket** để nhận tiếp không?

**Câu 3.** Vì sao `setSoTimeout(1000)` không bảo đảm tổng thời gian một request có 5 lần retry chỉ là 1 giây?

**Câu 4.** Sau khi nhận `"ok"`, `packet.getLength() == 2`. Muốn nhận một message 100 byte bằng packet cũ, cần chú ý gì?

**Câu 5.** Một hệ thống UDP nhận timeout khi đợi phản hồi của lệnh chuyển tiền. Có nên gửi lặp lại ngay mà không kiểm tra ID và trạng thái server?

**Câu 6.** Vì sao `new String(packet.getData(), UTF_8)` có thể làm bẩn kết quả?

**Câu 7.** Nếu server UDP muốn ngừng thread đang bị chặn ở `receive`, gọi `close()` có tác dụng gì?

**Câu 8.** Có thể dùng `DatagramSocket.setSoTimeout(...)` để trực tiếp giới hạn `DatagramChannel.receive(ByteBuffer)` trong non-blocking NIO không?

**Đáp án:**

1. Không. `0` có nghĩa vô hạn; `receive` có thể chờ đến khi có gói hoặc lỗi/đóng socket.
2. Được. `SocketTimeoutException` không đóng socket.
3. Mỗi lượt `receive` có timeout riêng. Năm lượt có thể chờ tổng cộng gần 5 giây hoặc hơn; cần deadline toàn yêu cầu.
4. Gọi `packet.setLength(buffer.length)` với buffer đủ lớn, hoặc tạo `DatagramPacket` mới. Không reset có thể khiến gói mới bị cắt.
5. Không nên. Server có thể đã chuyển tiền nhưng phản hồi bị mất. Cần request ID, idempotency và quy tắc retry hữu hạn.
6. Nó decode cả byte buffer, gồm bytes không thuộc datagram hiện tại. Dùng `getOffset()` và `getLength()`.
7. `close()` đóng socket và đánh thức lời gọi receive đang bị chặn, thường bằng `SocketException`; không thể tiếp tục dùng socket đã đóng.
8. Không. Với NIO non-blocking, cần dùng mô hình `DatagramChannel`/`Selector` hoặc cơ chế tương ứng.

## Tài liệu tham khảo còn áp dụng

- [Oracle Java SE 25 — DatagramSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html): `setSoTimeout`, `getSoTimeout`, `receive`, `close` và các ngoại lệ.
- [Oracle Java SE 25 — DatagramPacket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html): receive buffer, `setLength`, `getLength`, `getOffset`.
- [Oracle Java SE 25 — SocketTimeoutException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/SocketTimeoutException.html): timeout khi blocking socket operation.
- [Oracle Java SE 25 — DatagramChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): datagram networking theo NIO.
- [Oracle Java SE 25 — Selector](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html): multiplexing và timed readiness.
- [Oracle Java SE 25 — System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed time và deadline.
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): mô hình datagram của UDP.