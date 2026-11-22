# Đóng socket để giải phóng tài nguyên trong UDP và datagram (Java 15+)

## 1. Vì sao phải đóng DatagramSocket?

Trong Java, `java.net.DatagramSocket` là điểm gửi/nhận các **UDP datagram** thông qua hệ điều hành. Khi tạo socket và bind vào một địa chỉ/cổng, chương trình dùng tài nguyên mạng do JVM và hệ điều hành quản lý: socket handle/file descriptor, địa chỉ/cổng cục bộ được cấp phát, bộ đệm gửi/nhận và trạng thái giao tiếp.

**Nếu socket không còn được dùng, cần đóng nó** để hệ điều hành thu hồi tài nguyên, giải phóng binding thích hợp và tránh để các luồng nhận dữ liệu tiếp tục chờ vô thời hạn.

API chuẩn là:

```java
socket.close();
```

`DatagramSocket` thực thi `java.io.Closeable` và `AutoCloseable`, nên trong code có phạm vi sở hữu socket rõ ràng, cách ưu tiên là **try-with-resources**:

```java
try (DatagramSocket socket = new DatagramSocket()) {
    // Gửi/nhận datagram ở đây.
} // close() được tự động gọi, kể cả khi code trong try ném exception.
```

Các API này có từ lâu, **vẫn chính thức và phù hợp Java hiện đại**. Bài học tập trung vào ngữ nghĩa được hỗ trợ trong Java 15 trở lên; ví dụ thực hành dùng Java 17+ và đã được chạy kiểm chứng trên JDK 24.

## 2. Hiểu đúng vòng đời một UDP socket

```text
new DatagramSocket(...) / DatagramSocket.bind(...)
                     |
                     v
        Socket đã mở, có thể gửi/nhận
                     |
         +-----------+------------+
         |                        |
         v                        v
  send(DatagramPacket)       receive(DatagramPacket)
         |                        |
         +-----------+------------+
                     |
            Dùng xong / tắt server /
            xảy ra lỗi cần kết thúc
                     |
                     v
                 close()
                     |
                     v
          isClosed() == true
         Không thể tái sử dụng để I/O
```

Việc **đóng socket** khác với việc “không còn packet nào đến”. Một UDP socket không giữ kết nối TCP có phiên bắt tay và teardown; `close()` kết thúc **endpoint UDP cục bộ**, không gửi một thông điệp bảo đảm bên kia đã nhận hay biết rằng ứng dụng đóng.

Các trạng thái và thao tác chính:

| API | Công dụng | Lưu ý |
| --- | --- | --- |
| `new DatagramSocket()` | Mở socket UDP, tự chọn cổng cục bộ | Cần `close()` khi xong |
| `new DatagramSocket(0, address)` | Bind socket tại địa chỉ chỉ định, tự cấp cổng khả dụng | `0` yêu cầu hệ điều hành chọn cổng |
| `bind(SocketAddress)` | Bind socket chưa bind | Không thay cho close |
| `send(DatagramPacket)` | Gửi một datagram | Socket đóng sẽ không gửi được |
| `receive(DatagramPacket)` | Nhận datagram; thường chặn để chờ | Đóng socket sẽ làm luồng đang chặn nhận `SocketException` |
| `setSoTimeout(ms)` | Giới hạn thời gian chờ một lần `receive` | Timeout **không đóng** socket |
| `close()` | Đóng socket và giải phóng tài nguyên liên quan | Không có giá trị trả về |
| `isClosed()` | Kiểm tra socket đã đóng | Dùng để kiểm tra trạng thái đóng |
| `isBound()` | Cho biết socket đã từng bind thành công | Có thể vẫn `true` **sau khi close** |
| `disconnect()` | Bỏ liên kết peer mặc định của UDP socket đã connect | **Không đóng**, không giải phóng binding |

## 3. Phân biệt `close()`, `disconnect()` và `setSoTimeout()`

### 3.1. `close()`: kết thúc socket

`DatagramSocket.close()` đóng endpoint cục bộ. Theo tài liệu Java hiện hành:

- Luồng đang bị chặn trong `receive(DatagramPacket)` trên socket ấy sẽ nhận `SocketException`.
- Nếu socket được tạo từ một `DatagramChannel` và có channel liên kết, **đóng socket cũng đóng channel liên quan**.
- Sau khi đóng, nhiều phương thức của socket (như gửi/nhận hoặc thay đổi option) sẽ từ chối hoạt động, thường thông qua ngoại lệ.
- `isClosed()` trả `true` khi socket đã đóng.

Trong thực hành, gọi `close()` thêm lần nữa lên socket đã đóng không làm socket mở lại và không cần một thao tác “đóng sâu hơn”. Ví dụ bên dưới kiểm chứng việc gọi hai lần trên JDK hiện đại.

### 3.2. `disconnect()`: chỉ bỏ cấu hình peer mặc định

UDP vốn không thiết lập luồng kết nối như TCP, nhưng `DatagramSocket.connect(remoteAddress, port)` có thể đặt **peer mặc định** để `send` và `receive` bị giới hạn tới địa chỉ/cổng đó, đồng thời cho phép một số kiểu lỗi liên quan peer.

`disconnect()` **xóa liên kết peer** khi socket đã connect. Nó không tương đương `close()`; socket vẫn tồn tại, vẫn có thể bind và vẫn dùng cho I/O sau đó.

```java
// Ví dụ đặt bên trong một method đã có socket và InetAddress peer.
socket.connect(peer, 5353);
socket.disconnect();  // Không phải đóng socket.
socket.close();       // Thực sự kết thúc endpoint.
```

Đừng gọi `disconnect()` chỉ để “thu hồi cổng”. Cổng vẫn có thể thuộc binding của socket nếu socket còn mở.

### 3.3. `setSoTimeout(ms)`: kết thúc lần chờ, không kết thúc socket

`receive()` bình thường chặn tới khi có packet hoặc bị ảnh hưởng bởi đóng socket/lỗi. Có thể cấu hình:

```java
socket.setSoTimeout(1000); // 1 giây
```

Nếu hết thời gian mà chưa nhận được datagram, `receive()` ném `SocketTimeoutException` nhưng **socket vẫn hợp lệ và có thể tiếp tục được sử dụng**. `setSoTimeout(0)` nghĩa là không đặt giới hạn timeout theo cơ chế này.

Timeout không thay cho close: một socket đã hết thời gian chờ một lần nhận vẫn tiếp tục chiếm tài nguyên nếu chương trình không đóng sau khi thực sự hoàn tất việc sử dụng.

## 4. Nên ưu tiên try-with-resources khi sở hữu socket

Java có thể tự gọi `close()` ở cuối khối `try` vì `DatagramSocket implements Closeable`. Mẫu rõ ràng nhất cho tác vụ ngắn:

```java
import java.net.DatagramSocket;
import java.net.DatagramPacket;

// Đoạn minh họa cần đặt trong method có xử lý IOException.
try (DatagramSocket socket = new DatagramSocket()) {
    // send(...) hoặc receive(...).
} // Kể cả khi thao tác I/O lỗi, socket vẫn được đóng.
```

**Ưu điểm:**

- Đường đi thành công và đường đi có exception đều kết thúc bằng đóng tài nguyên.
- Không cần lặp `socket.close()` trên mọi nhánh `return`, `break` hoặc `catch`.
- Thể hiện rõ **ai sở hữu socket** và phạm vi socket được dùng.
- Hạn chế resource leak khi code có nhiều điều kiện hoặc exception.

`try-with-resources` đóng resource theo thứ tự **ngược** lại thứ tự khai báo nếu có nhiều resource. Với `DatagramSocket`, `close()` không yêu cầu bắt checked exception do chính `close`, nhưng thao tác `send`, `receive` hoặc tạo socket vẫn có thể ném các ngoại lệ I/O.

### 4.1. Không tự động đóng sau mỗi packet khi cần giữ socket lâu dài

Với một UDP server phục vụ nhiều packet trên **cùng cổng**, không nên tạo rồi đóng socket cho từng lần `receive` nếu mục tiêu là giữ một endpoint liên tục. Hãy bao **toàn bộ vòng đời server** trong một phạm vi quản lý socket, và đóng khi server thật sự dừng:

```java
try (DatagramSocket socket = new DatagramSocket(9000)) {
    boolean running = true;
    while (running) {
        // receive và xử lý từng datagram; xác định điều kiện thoát.
        // Trường hợp server khác cần dừng có thể gọi socket.close().
    }
}
```

Đoạn trên là **sơ đồ mã**, chưa phải server chạy độc lập; cần thêm `DatagramPacket`, logic xử lý, cơ chế hủy, giới hạn tài nguyên và xử lý lỗi. Vấn đề trọng tâm là **một resource scope cho một vòng đời socket**, không phải một socket cho mỗi datagram.

## 5. Chương trình Java 17+ đầy đủ: đóng tự động, timeout và dừng luồng nhận

Ví dụ sau chỉ sử dụng **loopback** trên máy đang chạy, không cần Internet hoặc UDP server bên ngoài. Nó mô phỏng ba trường hợp:

1. Gửi và nhận datagram rồi đóng cả hai socket tự động nhờ `try-with-resources`.
2. Chờ nhận với timeout, kiểm tra socket **vẫn mở sau timeout**, rồi tự đóng khi ra khỏi `try`.
3. Một luồng đang thực hiện đường nhận datagram; luồng chính đóng socket. Luồng nhận kết thúc với `SocketException`, được nhận diện như một phần của shutdown.

Tạo file **`DatagramSocketCloseDemo.java`**:

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;

public class DatagramSocketCloseDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        DatagramSocket receiver = new DatagramSocket(0, loopback);
        try (receiver; DatagramSocket sender = new DatagramSocket(0, loopback)) {
            receiver.setSoTimeout(2_000);

            byte[] message = "hello UDP".getBytes(StandardCharsets.UTF_8);
            DatagramPacket outbound = new DatagramPacket(
                    message, message.length, loopback, receiver.getLocalPort());
            sender.send(outbound);

            byte[] buffer = new byte[64];
            DatagramPacket inbound = new DatagramPacket(buffer, buffer.length);
            receiver.receive(inbound);
            String text = new String(inbound.getData(),
                    inbound.getOffset(), inbound.getLength(), StandardCharsets.UTF_8);
            System.out.println("received=" + text);
            System.out.println("insideTryClosed=" + receiver.isClosed());
        }
        System.out.println("afterTryClosed=" + receiver.isClosed());
        receiver.close();
        System.out.println("afterSecondClose=" + receiver.isClosed());
        System.out.println("boundFlagAfterClose=" + receiver.isBound());

        DatagramSocket timed = new DatagramSocket(0, loopback);
        try (timed) {
            timed.setSoTimeout(100);
            try {
                timed.receive(new DatagramPacket(new byte[8], 8));
                System.out.println("timeout=unexpectedPacket");
            } catch (SocketTimeoutException expected) {
                System.out.println("timeout=SocketTimeoutException");
            }
            System.out.println("afterTimeoutStillOpen=" + !timed.isClosed());
        }
        System.out.println("afterTimeoutTryClosed=" + timed.isClosed());

        DatagramSocket blocked = new DatagramSocket(0, loopback);
        CountDownLatch receiveStarted = new CountDownLatch(1);
        Thread reader = new Thread(() -> {
            receiveStarted.countDown();
            try {
                blocked.receive(new DatagramPacket(new byte[32], 32));
                System.out.println("blockedReceive=unexpectedPacket");
            } catch (SocketException expected) {
                System.out.println("blockedReceive=SocketException");
            } catch (IOException other) {
                System.out.println("blockedReceive=IOException");
            }
        }, "udp-reader");
        reader.setDaemon(true);
        reader.start();
        receiveStarted.await();
        blocked.close();
        reader.join(2_000);
        if (reader.isAlive()) {
            throw new IllegalStateException("receiver did not stop after close");
        }
        System.out.println("explicitClose=" + blocked.isClosed());

        try {
            byte[] bytes = "x".getBytes(StandardCharsets.UTF_8);
            blocked.send(new DatagramPacket(bytes, bytes.length, loopback, 9));
            System.out.println("sendAfterClose=unexpectedSuccess");
        } catch (SocketException expected) {
            System.out.println("sendAfterClose=SocketException");
        }
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac --release 17 DatagramSocketCloseDemo.java
java DatagramSocketCloseDemo
```

**Stdout chính xác trong lần chạy kiểm chứng trên JDK 24:**

```text
received=hello UDP
insideTryClosed=false
afterTryClosed=true
afterSecondClose=true
boundFlagAfterClose=true
timeout=SocketTimeoutException
afterTimeoutStillOpen=true
afterTimeoutTryClosed=true
blockedReceive=SocketException
explicitClose=true
sendAfterClose=SocketException
```

**Điều kiện thực thi:** chương trình cần quyền tạo/bind socket UDP loopback, cổng tự động còn khả dụng và bộ lập lịch luồng hoạt động bình thường. Môi trường sandbox hạn chế network socket có thể ngăn chương trình chạy; trong môi trường Java phát triển thông thường kết quả được kiểm chứng như trên.

### 5.1. Vì sao output cho thấy socket được đóng tự động?

- `insideTryClosed=false`: trong khối `try`, `receiver` vẫn mở nên nhận được datagram `"hello UDP"`.
- `afterTryClosed=true`: rời khối `try-with-resources` sẽ gọi `close()` cho `sender` và `receiver`.
- `afterSecondClose=true`: gọi `receiver.close()` thêm lần nữa không mở lại socket và không làm trạng thái thay đổi.

Mẫu `try (receiver; DatagramSocket sender = ...)` là cú pháp hợp lệ từ Java 9 trở lên: `receiver` là **biến local effectively final** và được khai báo trước `try`. Cú pháp này tương thích Java 15 và Java 17+.

### 5.2. Vì sao `isBound()` vẫn true sau close?

`boundFlagAfterClose=true` dễ gây hiểu nhầm. Theo hợp đồng `DatagramSocket.isBound()`, nếu socket đã từng bind thành công, `isBound()` **vẫn có thể trả `true` sau khi socket đã đóng**. Nó diễn tả **trạng thái lịch sử của binding**, không phải bằng chứng endpoint vẫn hoạt động.

Khi cần biết socket đã kết thúc chưa, dùng `isClosed()`. Không viết:

```java
if (socket.isBound()) {
    // Sai nếu suy ra socket chắc chắn vẫn có thể send/receive.
}
```

Phép kiểm tra `isBound()` không thay thế được `!socket.isClosed()`, và ngay cả `isClosed()` cũng chỉ là **kiểm tra tại một thời điểm**, không đảm bảo một thao tác I/O sẽ thành công nếu thread khác có thể đóng socket ngay sau đó.

### 5.3. Vì sao timeout khác shutdown?

- `timeout=SocketTimeoutException` thể hiện một lần `receive` hết thời gian chờ do `setSoTimeout(100)`.
- `afterTimeoutStillOpen=true` chứng minh timeout **không tự đóng socket**.
- `afterTimeoutTryClosed=true` chứng minh cuối phạm vi `try-with-resources` mới thực hiện đóng socket.

Không bắt `SocketTimeoutException` rồi tự động coi đó là “socket hỏng” trong mọi trường hợp. Nó có thể là một tín hiệu hợp lệ để lặp lại, thực hiện công việc định kỳ hoặc kiểm tra điều kiện dừng. Ngược lại, khi **không còn nhu cầu dùng socket**, vẫn phải đóng nó.

### 5.4. Vì sao luồng nhận ném SocketException khi close?

Đoạn này sử dụng `CountDownLatch` để luồng chính biết luồng nhận đã bắt đầu đường xử lý. Tín hiệu `countDown()` diễn ra **ngay trước** `receive()`; vì thế có thể `close()` xảy ra ngay trước khi luồng nhận thật sự chặn hoặc trong lúc nó đang chặn. Trong cả hai trường hợp, socket đã đóng thì thao tác nhận không thành công, và ví dụ kiểm chứng kết thúc bằng `SocketException`.

`reader.join(2_000)` chờ luồng nhận kết thúc tối đa 2 giây; nếu nó không kết thúc, chương trình ném lỗi kiểm thử thay vì báo thành công giả. Luồng được đặt daemon chỉ để tránh giữ tiến trình vô hạn trong tình huống môi trường bất thường; **daemon không thay cho cơ chế đóng socket và join**.

Đừng nhận diện một `SocketException` chỉ bằng **chuỗi thông điệp lỗi** như `"Socket closed"`: thông điệp có thể khác nhau giữa JDK, hệ điều hành hoặc socket implementation. Hãy xem loại ngoại lệ và trạng thái shutdown do ứng dụng kiểm soát.

### 5.5. Gửi trên socket đã đóng

`sendAfterClose=SocketException` nhắc rằng **không được tái sử dụng DatagramSocket sau close**. Muốn tiếp tục gửi/nhận trong một vòng đời mới, hãy tạo một socket mới, bind và cấu hình lại theo yêu cầu ứng dụng. Không thể “mở lại” cùng đối tượng `DatagramSocket` bằng `bind` sau khi nó đã đóng.

## 6. Đóng socket khi có exception: tránh rò rỉ tài nguyên

Một đường xử lý UDP có thể thất bại ở nhiều điểm: không bind được cổng, không gửi được datagram, socket nhận `SocketTimeoutException`, lỗi I/O hoặc code xử lý payload ném ngoại lệ. Nếu socket đã được tạo, code cần bảo đảm `close()` xảy ra khi tác vụ thật sự kết thúc.

**Mẫu ưu tiên:**

```java
try (DatagramSocket socket = new DatagramSocket()) {
    socket.setSoTimeout(1000);
    // send hoặc receive; nếu đoạn này ném IOException,
    // try-with-resources vẫn đóng socket khi rời khối try.
}
```

Đây là đoạn minh họa cần có import và xử lý exception trong phương thức chứa nó.

**Mẫu cần tránh:**

```java
DatagramSocket socket = new DatagramSocket();
// ...
socket.send(packet); // Nếu ném exception, dòng close dưới có thể bị bỏ qua.
socket.close();
```

Mẫu thứ hai chỉ an toàn nếu mọi đường đi đều có logic cleanup phù hợp. Nếu không thể dùng `try-with-resources`, dùng `try/finally`:

```java
DatagramSocket socket = new DatagramSocket();
try {
    // send/receive
} finally {
    socket.close();
}
```

Sự khác biệt giữa `try-with-resources` và `finally` chủ yếu là khả năng quản lý ownership và viết code gọn, dễ kiểm tra khi có nhiều tài nguyên. Với socket được **truyền vào từ bên ngoài**, không nên tự ý đóng nếu phương thức không sở hữu vòng đời đó: cần xác định rõ ai là chủ sở hữu và ai có trách nhiệm đóng.

## 7. Dừng UDP receiver đang chạy trong thread khác

Một server UDP thường có luồng lặp:

```java
while (running) {
    socket.receive(packet);
    handle(packet);
}
```

Nếu thread đang bị chặn tại `receive()`, chỉ đổi `running=false` **không chắc làm luồng thoát ngay**, vì nó chưa có cơ hội kiểm tra biến cờ. Đây là lý do `close()` là một cơ chế shutdown quan trọng.

Mẫu cấu trúc tham khảo:

```java
private final DatagramSocket socket;
// volatile bảo đảm thread nhận nhìn thấy thay đổi từ thread shutdown.
private volatile boolean running = true;

void runLoop() {
    while (running) {
        try {
            DatagramPacket packet = new DatagramPacket(new byte[2048], 2048);
            socket.receive(packet);
            // Kiểm tra running và xử lý packet theo chính sách.
        } catch (SocketException ex) {
            if (!running && socket.isClosed()) {
                break; // Shutdown do ứng dụng chủ động yêu cầu.
            }
            // Lỗi socket ngoài dự kiến: log an toàn, dừng hoặc báo cho supervisor.
            break;
        } catch (IOException ex) {
            // Theo policy: ghi nhận lỗi và quyết định tiếp tục/dừng.
            break;
        }
    }
}

void stop() {
    running = false;
    socket.close(); // Đánh thức đường receive khi socket đang bị chặn.
}
```

**Đây là các thành viên minh họa bên trong một lớp server, không phải chương trình độc lập**. Trong ứng dụng production, cần có cơ chế chờ thread kết thúc, quản lý executor/lifecycle, đồng bộ hóa với shutdown và xử lý lỗi khởi động phù hợp.

Phải phân biệt:

- `SocketException` xuất hiện **sau khi ứng dụng chủ động close** trong quá trình shutdown: có thể là kết quả dự kiến.
- `SocketException` xảy ra **khi ứng dụng vẫn phải phục vụ**: không được mặc nhiên coi là shutdown sạch; cần log và xử lý theo chính sách, có thể khởi động lại một socket mới.
- Các lỗi I/O khác: không nên nuốt ngoại lệ để chạy tiếp khi socket đã hỏng hoặc cổng không còn hợp lệ.

**Lưu ý:** Việc `close()` đánh thức `receive()` được chính tài liệu `DatagramSocket` quy định. Việc `Thread.interrupt()` đánh thức nhận UDP tùy hoàn cảnh: nó có quy tắc riêng khi socket liên kết `DatagramChannel` hoặc khi virtual thread đang dùng implementation mặc định trong các JDK hiện đại. Không mặc định rằng chỉ `interrupt()` sẽ thay `close()` trong mọi triển khai.

## 8. DatagramSocket và DatagramChannel: khi đóng liên quan nhau

Java NIO cung cấp `java.nio.channels.DatagramChannel`. Một `DatagramSocket` có thể được liên kết với `DatagramChannel` khi socket được lấy từ channel qua `DatagramChannel.socket()`.

Theo Java API:

- Nếu `DatagramSocket` **có channel liên kết**, gọi `DatagramSocket.close()` cũng đóng channel ấy.
- Không phải mọi `DatagramSocket` đều có associated channel. `getChannel()` có thể trả `null`.
- `DatagramChannel` là resource cần được quản lý vòng đời riêng trong ứng dụng dùng NIO; nếu chương trình sở hữu channel thì nên dùng `try-with-resources` trên **channel** tương ứng.
- Selector, asynchronous-close và interrupt có cơ chế riêng trong NIO; không suy luận toàn bộ hành vi đó chỉ từ ví dụ `DatagramSocket` truyền thống.

Ví dụ khái niệm:

```java
import java.nio.channels.DatagramChannel;

try (DatagramChannel channel = DatagramChannel.open()) {
    DatagramSocket socket = channel.socket();
    // Socket được liên kết với channel.
    // Đóng channel khi ra khỏi try sẽ giải phóng resource.
}
```

Đây là đoạn minh họa, cần import `DatagramSocket` và có method phù hợp. Nếu code chủ yếu dùng `DatagramSocket`, không cần tự chuyển sang NIO chỉ để có `close()`: `DatagramSocket` đã hỗ trợ `Closeable` và `try-with-resources`.

## 9. Đóng socket có bảo đảm cổng khả dụng ngay cho server khác không?

Gọi `close()` giải phóng socket handle và binding cục bộ liên quan theo quy tắc hệ điều hành. Tuy nhiên, **không nên xây dựng logic dựa trên lời hứa rằng một tiến trình khác luôn bind được chính cổng đó tức thì** trong mọi môi trường: khả năng bind phụ thuộc socket options như `SO_REUSEADDR`, các socket khác cùng máy, chính sách mạng và hệ điều hành.

Với UDP, không áp dụng máy móc trạng thái `TIME_WAIT` của kết nối TCP để giải thích mọi lỗi bind; UDP không có phiên kết nối TCP với teardown `FIN`. Nếu một socket mới báo `BindException`/ `SocketException`, hãy kiểm tra cổng có đang được một endpoint khác giữ, địa chỉ bind có phù hợp và chính sách OS/socket options.

**Không dùng việc gọi `close()` rồi bind lại cùng cổng như phương pháp kiểm tra duy nhất rằng không leak**. Kiểm tra `isClosed()`, luồng receive đã dừng, việc quản lý ownership và thống kê tài nguyên của hệ điều hành phù hợp hơn.

## 10. Những lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `java.net.SocketException` sau khi đóng rồi `send`/`receive` | Dùng lại socket đã đóng | Tạo socket mới nếu cần một vòng đời mới; không reuse đối tượng cũ |
| `SocketException` trong luồng đang receive khi shutdown | Thread khác gọi `close()` | Nếu shutdown được yêu cầu, kết thúc vòng lặp có kiểm soát |
| `SocketException` khi server vẫn phải chạy | Lỗi socket hoặc I/O bất thường | Log, báo lỗi, cân nhắc tạo lại socket theo policy |
| `SocketTimeoutException` trong `receive` | Quá thời gian `setSoTimeout` | Socket vẫn mở; tiếp tục hoặc dừng tùy nhiệm vụ |
| `BindException` khi mở socket | Cổng/địa chỉ không khả dụng hoặc xung đột binding | Kiểm tra cổng, bind address và process khác |
| `isBound() == true` nhưng I/O không được | `isBound` vẫn giữ trạng thái sau close | Dùng `isClosed()`; không suy ra khả năng I/O từ `isBound` |
| Thread không dừng khi chỉ đặt `running=false` | Nó vẫn bị chặn trong `receive` | Đóng socket từ luồng điều khiển và chờ thread kết thúc |
| Server không nhận packet tiếp theo sau timeout | Code đã đóng socket hoặc dừng sai quy trình | Tách timeout khỏi shutdown; kiểm tra policy xử lý |
| Resource leak khi xảy ra exception | `close()` chỉ được gọi ở nhánh thành công | Dùng `try-with-resources` hoặc `finally` |
| Socket đóng ngay khi method trả về | Chủ sở hữu đóng trong khi caller còn dùng | Thiết kế rõ ràng lifetime và quyền sở hữu resource |

**Không bắt mọi `IOException` rồi tiếp tục vòng lặp vô hạn mà không kiểm tra socket đã đóng.** Điều này dễ biến shutdown thành vòng lặp tiêu tốn CPU hoặc che giấu sự cố mạng.

## 11. Bảo mật, độ tin cậy và vận hành

Đóng socket đúng cách không biến UDP thành giao thức tin cậy: **UDP datagram có thể bị mất, trùng, đảo thứ tự hoặc vượt kích thước bộ đệm nhận**. `close()` không tự xác nhận delivery, không tự bảo vệ nội dung packet và không cung cấp xác thực đầu gửi.

Khi thiết kế ứng dụng thực tế:

- **Quản lý ownership:** một thành phần chịu trách nhiệm đóng socket; tránh nhiều module tự ý close cùng endpoint trong khi module khác đang dùng.
- **Không giữ socket vô hạn ngoài ý muốn:** tạo socket ở startup/task scope và đóng ở shutdown/finally.
- **Giới hạn thời gian hoặc cơ chế cancel:** dùng `setSoTimeout` cho các lần nhận cần timeout; dùng `close()` khi chủ động kết thúc lifetime.
- **Dừng nhận trước khi thoát ứng dụng:** thông báo cho luồng nhận, đóng socket, đợi thread/executor hoàn tất theo timeout của ứng dụng.
- **Không rò rỉ nội dung nhạy cảm:** hạn chế in payload mạng hoặc exception message chứa dữ liệu người dùng.
- **Giới hạn kích thước datagram:** buffer quá nhỏ có thể gây cắt nội dung trong `DatagramPacket`; kiểm tra `getLength()` sau nhận và định dạng protocol.
- **Kiểm tra source và quyền:** UDP không đảm bảo sender identity; cần xác thực/giao thức bảo vệ riêng nếu thông điệp đáng tin là yêu cầu.
- **Đừng giữ giả định về port reuse:** kiểm tra bind errors và xử lý cấu hình/OS thay vì tự ý đổi cổng mà không thông báo.

Đối với ứng dụng có thời gian hoạt động dài, nên kiểm thử nhiều chu kỳ startup/shutdown, exception xảy ra giữa lúc đang gửi/nhận và việc đóng socket từ thread khác. Việc không còn thread chờ `receive` và trạng thái `isClosed()==true` là các tín hiệu cần có trong QA vòng đời resource.

## 12. Checklist kiểm thử đóng DatagramSocket

- [ ] Socket được tạo/bind ở đâu? Thành phần nào **sở hữu** lifetime của nó?
- [ ] Có `try-with-resources` hoặc `finally` để đóng khi code kết thúc hoặc ném exception không?
- [ ] Có kiểm tra `isClosed()` thay vì chỉ dựa vào `isBound()` không?
- [ ] Nếu receive trong thread khác, `close()` có làm thread ấy thoát và được `join`/shutdown đúng không?
- [ ] `SocketException` khi shutdown được phân biệt với lỗi socket bất ngờ chưa?
- [ ] `SocketTimeoutException` được xử lý như timeout, **không tự cho rằng socket đã close**?
- [ ] Nếu dùng `DatagramChannel`, ownership của channel/socket đã rõ và không double-manage sai vòng đời?
- [ ] Có test gửi/nhận loopback, shutdown khi đang chờ và I/O sau close không?
- [ ] Nếu cần bind lại cổng, đã xử lý `BindException` và chính sách reuse đúng chưa?
- [ ] Có biện pháp an ninh/phục hồi riêng cho UDP mà không phụ thuộc vào `close()` không?

**Kết luận:** `DatagramSocket.close()` là cách chính thức để kết thúc UDP socket và giải phóng tài nguyên. Dùng `try-with-resources` khi có phạm vi sở hữu rõ ràng; dùng `close()` có kiểm soát để dừng thread đang bị chặn trong `receive()`. `setSoTimeout()` chỉ giới hạn một lần chờ, `disconnect()` chỉ xóa peer association, còn `isBound()` không chứng minh socket đang mở. **Không dùng lại socket đã đóng.**

## 13. Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 25 — DatagramSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html): `close()`, `isClosed()`, `isBound()`, `receive()`, `setSoTimeout()`, `getChannel()` và ngữ nghĩa close làm `receive` ném `SocketException`.
- [Oracle Java SE 25 — DatagramPacket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html): địa chỉ/port, buffer, `getLength()` và kích thước dữ liệu nhận.
- [Oracle Java SE 25 — SocketTimeoutException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/SocketTimeoutException.html): timeout của thao tác nhận mà không làm socket vô hiệu.
- [Oracle Java SE 25 — DatagramChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): channel có thể cung cấp `DatagramSocket` liên kết và có lifecycle riêng.
- [Oracle Java SE 25 — AutoCloseable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng hỗ trợ đóng resource tự động.
- [Oracle Java Tutorials / Java Language Specification — try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): cú pháp quản lý `AutoCloseable` và xử lý cleanup khi gặp ngoại lệ.

Bài học chỉ dùng API Java mạng và resource-management còn được hỗ trợ trong Java hiện đại; không sử dụng cấu hình networking lỗi thời hoặc cơ chế legacy.