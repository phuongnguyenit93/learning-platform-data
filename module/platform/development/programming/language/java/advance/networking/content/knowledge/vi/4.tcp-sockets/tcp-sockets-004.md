# Đặt thời hạn kết nối bằng `Socket.connect()` và thời hạn đọc bằng `SO_TIMEOUT`

## 1. Vì sao cần hai loại timeout riêng?

Khi dùng TCP bằng `java.net.Socket`, kết nối đến một máy chủ và chờ dữ liệu từ máy chủ là **hai thao tác khác nhau**. Một kết nối có thể được thiết lập nhanh nhưng server không bao giờ trả lời; ngược lại, server có thể phản hồi tốt sau khi kết nối nhưng đích mạng ban đầu không thể kết nối. Vì vậy Java cung cấp hai cơ chế chủ đạo:

- **Connect timeout:** truyền vào `Socket.connect(SocketAddress endpoint, int timeout)` để giới hạn khoảng chờ **thiết lập kết nối TCP**.
- **Read timeout:** cấu hình bằng `Socket.setSoTimeout(int timeout)`, tương ứng tùy chọn **`SO_TIMEOUT`**, để giới hạn một lần chờ đọc dữ liệu blocking từ `InputStream` của socket đã kết nối.

Cả hai sử dụng **mili giây (ms)**, nhưng không thay thế nhau và không tự tạo deadline cho toàn bộ request.

### 1.1. Hình dung theo dòng thời gian

~~~text
Client                                TCP server
  |                                        |
  |--- connect(endpoint, 2000) ---------->|   Pha A: thiết lập kết nối TCP
  |<--- kết nối được ----------------------|
  |                                        |
  |--- ghi request ----------------------->|
  |                                        |   Server đang xử lý...
  |--- read(), SO_TIMEOUT = 3000 -------->|   Pha B: chờ byte để đọc
  |<--- byte phản hồi ---------------------|   hoặc read ném SocketTimeoutException
  |                                        |
~~~

Giá trị `2_000` và `3_000` là thời hạn chờ theo từng thao tác tương ứng. Nếu kết nối thành công trong 10 ms, `connect` kết thúc ngay; không cố chờ đủ 2 giây. Nếu bên kia từ chối kết nối ngay lập tức, lỗi có thể xảy ra ngay trước khi hết connect timeout.

### 1.2. Bảng so sánh nhanh

| Tiêu chí | `connect(endpoint, timeout)` | `setSoTimeout(timeout)` |
| --- | --- | --- |
| Mục đích | Giới hạn thời gian chờ kết nối TCP | Cấu hình thời gian chờ **mỗi lần đọc blocking** |
| Thời điểm áp dụng | Khi gọi `connect` trên socket chưa kết nối | Sau khi cấu hình, áp dụng cho lần đọc blocking tiếp theo |
| Giá trị thời gian | `int` mili giây | `int` mili giây |
| `0` | Không đặt giới hạn thời gian kết nối bằng tham số này | Vô hiệu hóa read timeout; lần đọc có thể đợi vô thời hạn |
| Vượt thời hạn | Thường gặp `SocketTimeoutException` tại `connect` | `SocketTimeoutException` tại `read` |
| Khi thành công | Socket đã kết nối và có thể lấy input/output stream | `read` trả số byte / byte hợp lệ hoặc báo EOF theo API |
| Có áp dụng cho ghi? | Không | Không |
| Có giới hạn toàn bộ request? | Không | Không |

**Điểm then chốt:** `setSoTimeout(3_000)` không giới hạn thời gian kết nối, còn `connect(..., 2_000)` không giới hạn thời gian chờ phản hồi sau khi kết nối thành công.

## 2. Dùng đúng `Socket.connect(SocketAddress, int)`

### 2.1. Tạo socket chưa kết nối, sau đó connect có timeout

Ví dụ cấu hình điển hình trong Java 17+:

~~~java
import java.net.InetSocketAddress;
import java.net.Socket;

String host = "example.org";
int port = 8080;

try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(host, port), 2_000);
    socket.setSoTimeout(5_000);

    // Chỉ sau khi connect thành công mới trao đổi dữ liệu với peer.
    // Ví dụ: socket.getOutputStream().write(...);
    //         socket.getInputStream().read(...);
}
~~~

Đây là **đoạn code minh họa**, chưa có protocol request/response hoàn chỉnh và không phụ thuộc server phải trả dữ liệu. Các điểm cần nhớ:

1. `new Socket()` tạo socket chưa kết nối; bạn chủ động gọi `connect(endpoint, connectTimeoutMs)`.
2. `new InetSocketAddress(host, port)` đại diện địa chỉ IP/host và cổng đích; việc phân giải tên có thể xảy ra trước pha connect.
3. Tham số `2_000` là **2.000 ms = 2 giây**, dành cho lần `connect` đó. Dùng `0` nghĩa là chờ kết nối không giới hạn bởi timeout này; giá trị âm không hợp lệ.
4. Nếu kết nối thành công, mới thực hiện I/O. `try-with-resources` đóng socket cả khi thành công lẫn khi gặp ngoại lệ.
5. `socket.setSoTimeout(5_000)` là thiết lập **riêng** cho lần đọc sau đó. Không cần đặt trước `connect` để connect timeout có hiệu lực.

Cú pháp rút gọn `new Socket(host, port)` cũng có thể kết nối, nhưng không cho bạn truyền timeout vào chính lời gọi constructor đó. Khi cần kiểm soát connect timeout rõ ràng, hãy dùng `new Socket()` rồi `connect(endpoint, timeout)`.

### 2.2. Những gì connect timeout không bảo đảm

**Connect timeout là giới hạn cho thao tác kết nối tại `connect`**, không phải đồng hồ đếm tổng của mọi công việc liên quan đến một request:

- **DNS:** nếu dùng hostname, thao tác phân giải tên có thể xảy ra khi dựng `InetSocketAddress` (hoặc tại tầng khác) và nằm ngoài thời gian chờ `connect`; timeout này không mặc nhiên giới hạn toàn bộ DNS.
- **TLS:** thiết lập TCP thành công chưa có nghĩa TLS handshake hoàn tất. Khi dùng TLS/HTTPS, cần chính sách timeout phù hợp cho handshake và I/O của tầng đó.
- **Gửi request, xử lý nghiệp vụ và nhận response:** không được giới hạn bởi `connect` sau khi kết nối thành công.
- **Ứng dụng từ chối/không thể truy cập đích:** có thể ném lỗi sớm (ví dụ `ConnectException`) mà không chờ đến mốc timeout; đây không có nghĩa cấu hình timeout không hoạt động.
- **Tính chính xác theo mili giây:** thời hạn do hệ điều hành và cơ chế lập lịch thực thi, không phải bảo đảm thời gian thực cứng; không giả định phép đo sẽ chính xác tuyệt đối đến một ms.

**Kiểm tra kết nối thất bại:** `SocketTimeoutException` trong pha connect diễn đạt việc chờ kết nối quá lâu, còn `ConnectException` thường diễn đạt bị từ chối hoặc kết nối không thành công theo thông báo của hệ điều hành. Lỗi địa chỉ/tên miền, mạng không tới được hoặc chính sách firewall cũng có thể tạo các ngoại lệ I/O khác. Hãy giữ nguyên nguyên nhân để chẩn đoán.

### 2.3. Không nhầm “đã connect” với “đang sử dụng tốt”

`socket.isConnected()` cho biết socket **đã từng kết nối thành công**; giá trị có thể vẫn là `true` sau khi socket đóng. Đừng dùng riêng nó để suy ra peer đang hoạt động. Có thể kiểm tra thêm `isClosed()`, nhưng ngay cả hai cờ này cũng **không thể xác nhận** server còn xử lý được request; chỉ giao thức ứng dụng và phản hồi thực tế mới chứng minh điều đó.

## 3. Dùng đúng `Socket.setSoTimeout(int)` cho đọc blocking

### 3.1. Cơ chế SO_TIMEOUT

`setSoTimeout(3_000)` cấu hình thời gian chờ đọc ở socket, đo bằng mili giây. Khi một thao tác `InputStream.read()` trên socket **phải chờ vì chưa có byte**, quá thời gian quy định thì thao tác đó ném `java.net.SocketTimeoutException`. Theo API `Socket`, **socket vẫn có thể sử dụng được** sau một read timeout; ứng dụng quyết định đọc tiếp, retry ở mức giao thức, hoặc đóng.

Ví dụ:

~~~java
socket.setSoTimeout(3_000);
int value = socket.getInputStream().read();
if (value == -1) {
    // Peer kết thúc phía gửi (EOF).
} else {
    // Có đúng một byte; value trong khoảng 0..255.
}
~~~

Đoạn trên giả định `socket` đã kết nối và vẫn mở. Ba kết quả phải được phân biệt:

- **Có dữ liệu:** `read()` trả byte (hoặc số byte dương đối với overload đọc vào mảng). Nếu byte đã nằm trong bộ đệm, thao tác có thể trả về ngay.
- **EOF:** `read()` trả `-1` khi đầu kia đóng chiều gửi bình thường và luồng đã hết byte.
- **Timeout:** `SocketTimeoutException` nghĩa là thao tác đọc không lấy được dữ liệu trong thời hạn; **không đồng nghĩa EOF và không tự chứng minh server đã chết**.

`socket.getSoTimeout()` trả số mili giây đang cấu hình. Giá trị mặc định của tùy chọn này thường là `0` (chờ không giới hạn). `setSoTimeout(0)` tắt timeout đọc; số âm không hợp lệ.

### 3.2. SO_TIMEOUT áp dụng cho mỗi lần chờ đọc, không phải cả thông điệp

Giả sử protocol yêu cầu nhận 1.000 byte. Client đọc thành nhiều lượt, mỗi lượt có `SO_TIMEOUT = 1_000` ms. Nếu peer liên tục gửi một ít byte trước khi mỗi lần đọc hết hạn, **tổng thời gian để nhận đủ 1.000 byte có thể vượt rất xa 1 giây**. Đây là lý do SO_TIMEOUT không tự tạo deadline tổng cho một frame hoặc request.

~~~text
Đọc lần 1: chờ 800 ms -> nhận 10 byte
Đọc lần 2: chờ 900 ms -> nhận 10 byte
Đọc lần 3: chờ 950 ms -> nhận 10 byte
...
Mỗi lần đọc vẫn dưới 1.000 ms; tổng thời gian thì cộng dồn.
~~~

Khi cần giới hạn **toàn bộ message**, hãy dùng deadline riêng bằng `System.nanoTime()`, tính thời gian còn lại trước mỗi lần đọc, và cập nhật SO_TIMEOUT phù hợp. Đồng thời giới hạn kích thước frame, tiến độ nhận và số lượng kết nối. Nếu chỉ có `SO_TIMEOUT`, một peer gửi dữ liệu nhỏ giọt có thể giữ kết nối rất lâu.

### 3.3. Read timeout không phải write timeout

`SO_TIMEOUT` được dùng cho **đọc** blocking. Nó không trực tiếp giới hạn:

- `socket.connect(...)`: phải sử dụng tham số timeout của `connect`.
- `socket.getOutputStream().write(...)` hoặc `flush()`: khi peer nhận chậm hoặc TCP backpressure, thao tác ghi có thể bị chặn; `setSoTimeout` không tự cung cấp write timeout.
- Toàn bộ chu kỳ connect → request → response.
- Một lệnh `ServerSocket.accept()` đang chờ client kết nối.

Đối với `ServerSocket`, phương thức `listener.setSoTimeout(ms)` là một **tùy chọn khác, trên listening socket**, dùng để giới hạn thời gian chờ của `accept()`. Nó không tự đặt thời hạn đọc cho mỗi `Socket` được `accept()` trả về. Nếu cần, đặt `acceptedSocket.setSoTimeout(ms)` riêng.

Với NIO non-blocking `SocketChannel`, `Selector` hoặc asynchronous channels, bạn phải sử dụng cơ chế deadline/scheduling phù hợp với API đó. Không giả định mọi thao tác non-blocking sẽ hành xử giống `InputStream.read()` của `Socket`.

## 4. Chọn timeout theo điều kiện mạng và yêu cầu nghiệp vụ

Không có một cặp thời gian duy nhất đúng cho mọi ứng dụng. Các mốc 2 giây connect và 5 giây read trong ví dụ chỉ là **giá trị minh họa**. Cần cân nhắc:

- **Độ trễ mạng:** LAN thường khác mạng di động/quốc tế; TCP connect có thể thất bại nhanh ở mạng này nhưng phải chờ ở mạng khác.
- **SLA của chức năng:** thao tác người dùng tương tác cần deadline chặt hơn job nền dài hạn.
- **Thời gian xử lý bình thường của server:** nếu server hợp lệ đôi khi cần 4 giây để phản hồi, read timeout 500 ms sẽ tạo lỗi giả.
- **Kích thước dữ liệu:** đọc một byte khác nhận payload lớn; thời gian tổng phải phù hợp tốc độ/khối lượng và giới hạn tài nguyên.
- **Retry:** mỗi lần thử có thể có connect timeout và read timeout riêng; cả chuỗi retry vẫn cần deadline cuối cùng và giới hạn backoff/tần suất.

Ví dụ chính sách nội bộ của một thao tác có deadline 6 giây:

~~~text
Overall deadline = 6.000 ms (tính từ khi bắt đầu yêu cầu)
  DNS                -> được quản lý riêng nếu cần
  TCP connect        -> tối đa 1.500 ms
  Gửi request        -> theo tiến độ/giới hạn riêng
  Chờ các lần read   -> mỗi lần <= thời gian còn lại của deadline
  Retry nếu hợp lệ   -> chỉ khi còn ngân sách thời gian
~~~

Đây là mô hình **ngân sách thời gian**, không phải lời khuyên cộng hai timeout thành thời hạn tổng. Phải tính deadline trên đồng hồ đơn điệu `System.nanoTime()` để không phụ thuộc thao tác chỉnh giờ hệ thống. Connect timeout và read timeout có thể được điều chỉnh theo thời gian còn lại trước mỗi bước.

Nếu server có thể hoàn thành giao dịch trước khi phản hồi tới client, timeout đọc **không chứng minh giao dịch chưa diễn ra**. Với thao tác có side effect, retry chỉ an toàn khi có chính sách idempotency, request ID hoặc cơ chế đối soát.

## 5. Ví dụ Java 17+ chạy được: kết nối thành công, timeout một lần đọc, sau đó đọc lại

Ví dụ sau tạo **TCP server trên loopback**, không cần Internet, DNS hay server bên ngoài. Client dùng `connect(..., 2_000)` để thiết lập kết nối. Server chủ động **chưa gửi byte**; client đặt `SO_TIMEOUT = 200` ms và gặp `SocketTimeoutException` khi đọc lần đầu. Sau khi nhận tín hiệu rằng client đã timeout, server mới gửi byte `42`. Client đổi `SO_TIMEOUT = 2_000` ms rồi đọc tiếp trên **cùng socket** và nhận byte đó.

Dùng `CountDownLatch` để điều phối thứ tự, vì vậy ví dụ không phụ thuộc mẹo `Thread.sleep()` để cố tạo tình huống mạng chậm.

Lưu mã sau thành **SocketTimeoutDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketTimeoutDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            listener.setSoTimeout(3_000); // Chỉ áp dụng cho accept()

            CountDownLatch firstReadTimedOut = new CountDownLatch(1);
            ExecutorService workers = Executors.newSingleThreadExecutor();

            try {
                Future<?> serverTask = workers.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        // Chưa gửi byte nào: buộc client phải chờ ở read().
                        if (!firstReadTimedOut.await(3, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                    "Expected timeout was not observed");
                        }

                        peer.getOutputStream().write(42);
                        peer.getOutputStream().flush();
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "Server was interrupted", ex);
                    }
                });

                try (Socket client = new Socket()) {
                    // Đặt connect timeout cho giai đoạn TCP handshake.
                    client.connect(
                            new InetSocketAddress(
                                    loopback, listener.getLocalPort()),
                            2_000);
                    System.out.println("Connected");

                    // Chỉ đọc chờ tối đa 200 ms tại lần read này.
                    client.setSoTimeout(200);
                    try {
                        int value = client.getInputStream().read();
                        throw new AssertionError(
                                "Expected timeout, got " + value);
                    } catch (SocketTimeoutException expected) {
                        System.out.println("Read timed out");
                    } finally {
                        // Sau khi lần đọc đầu hoàn tất, cho server gửi byte.
                        firstReadTimedOut.countDown();
                    }

                    // Socket vẫn dùng được sau SocketTimeoutException.
                    client.setSoTimeout(2_000);
                    System.out.println(
                            "Received: " + client.getInputStream().read());
                }

                // Nếu server thread lỗi, Future.get() chuyển lỗi về main.
                serverTask.get(5, TimeUnit.SECONDS);
            } finally {
                firstReadTimedOut.countDown();
                workers.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 SocketTimeoutDemo.java
java SocketTimeoutDemo
~~~

Stdout khi chạy thành công:

~~~text
Connected
Read timed out
Received: 42
~~~

### 5.1. Giải thích dòng thời gian của ví dụ

1. `ServerSocket(0, 1, loopback)` tạo listening socket trên địa chỉ loopback và chọn một cổng còn trống. `listener.setSoTimeout(3_000)` chỉ bảo vệ thao tác `listener.accept()`.
2. Worker gọi `accept()` và chờ latch, nên **chưa gửi** byte nào cho client.
3. Client tạo `Socket` chưa kết nối, gọi `connect(endpoint, 2_000)`. Vì server lắng nghe trên loopback, kết nối thành công và in `Connected`.
4. Client đặt `SO_TIMEOUT=200` ms rồi gọi `InputStream.read()`. Chưa có byte và server chưa half-close/đóng chiều gửi, nên lần đọc này hết hạn và ném `SocketTimeoutException`; client in `Read timed out`.
5. `finally` của lần đọc đầu giải phóng latch; worker mới gửi byte 42. Client thay SO_TIMEOUT thành 2.000 ms và đọc lại trên socket còn sống; in `Received: 42`.
6. `Future.get(...)` kiểm tra worker hoàn tất; `try-with-resources` đóng client, peer và listener. `shutdownNow()` kết thúc executor phục vụ demo.

**Ý nghĩa của ví dụ:** timeout đọc không làm socket tự động đóng. Tuy nhiên, việc đọc lại an toàn trong ví dụ chỉ vì protocol cố tình gửi **đúng một byte** và lần đọc đầu không tiêu thụ một phần frame. Với protocol nhiều byte, timeout có thể xuất hiện sau khi đã nhận **một phần thông điệp**, vì vậy phải duy trì trạng thái framing hoặc đóng và tạo kết nối mới.

Trong môi trường quá tải, lịch trình thread hoặc timeout thử nghiệm có thể bị ảnh hưởng bởi tải máy. Chạy ở loopback và dùng latch giúp tạo đúng thứ tự sự kiện; các mốc mili giây minh họa không phải cam kết thời gian thực.

## 6. Xử lý timeout đúng theo pha và ngoại lệ

### 6.1. Bắt ngoại lệ gần thao tác tương ứng

Ví dụ phân biệt nơi connect lỗi và nơi read lỗi:

~~~java
// Minh họa nằm trong phương thức có thể ném IOException.
try (Socket socket = new Socket()) {
    try {
        socket.connect(remoteAddress, 2_000);
    } catch (SocketTimeoutException ex) {
        // Chờ thiết lập kết nối quá hạn.
        throw new IOException("TCP connect timed out", ex);
    }

    socket.setSoTimeout(3_000);
    try {
        int firstByte = socket.getInputStream().read();
        if (firstByte == -1) {
            throw new java.io.EOFException("Peer closed the stream");
        }
        // Phân tích dữ liệu theo giao thức đã thống nhất.
    } catch (SocketTimeoutException ex) {
        // Không có byte để hoàn tất read trong thời hạn.
        throw new IOException("TCP read timed out", ex);
    }
}
~~~

Đây **không phải chương trình độc lập**: `remoteAddress` là `SocketAddress` đã được ứng dụng tạo/kiểm tra. Trong chương trình thực tế, nếu bắt `IOException` bao trùm cả connect và read, hãy bổ sung ngữ cảnh về **pha đang thực hiện** để xử lý/log đúng thay vì mặc định mọi `SocketTimeoutException` là timeout đọc.

| Triệu chứng | Tín hiệu thường gặp | Ý nghĩa thực tiễn |
| --- | --- | --- |
| Connect chờ vượt mốc | `SocketTimeoutException` khi `connect` | Chưa thiết lập kết nối trong thời hạn |
| Đích từ chối ngay | `ConnectException` | Endpoint không nhận kết nối vào thời điểm đó; không nhất thiết hết timeout |
| Lỗi phân giải tên/địa chỉ | `UnknownHostException` hoặc lỗi kết nối khác tùy cách tạo endpoint | Cần kiểm tra tên, DNS, địa chỉ |
| Read không có dữ liệu trong thời hạn | `SocketTimeoutException` khi `read` | Lần đọc chờ quá lâu; chưa chắc peer đã chết |
| Peer kết thúc chiều gửi | `read() == -1` (hoặc `EOFException` ở API đọc đủ byte) | EOF, khác timeout |
| TCP reset/đóng bất thường | `SocketException`/`IOException` | Thường không nên tiếp tục dùng kết nối như bình thường |
| Thread cần hủy | `InterruptedException` khi chờ latch/future, v.v. | Phục hồi cờ interrupt, dọn tài nguyên theo hợp đồng |

Các loại lỗi có thể bị ảnh hưởng bởi hệ điều hành, API wrapper và trạng thái mạng; không nên kiểm thử bằng cách giả định mọi máy đều trả cùng một thông báo lỗi hoặc cùng thời gian chính xác.

### 6.2. Đọc nhiều byte: đừng bỏ mất trạng thái sau timeout

TCP là một **luồng byte**, không có ranh giới thông điệp gắn với các lần `read`. Xét protocol có **4 byte prefix độ dài + payload N byte**:

- Nếu đã đọc đủ 4 byte prefix và 300 byte payload trước khi read timeout, phần 300 byte đã tiêu thụ **không tự quay lại input stream**.
- Gọi lại `readFully(payload)` từ đầu trên cùng stream có thể làm lệch offset, nuốt byte của frame sau hoặc chờ nhầm số lượng còn lại.
- Cần cập nhật bộ đếm `received`/trạng thái parser qua từng lần đọc thành công, hoặc **bỏ kết nối** nếu protocol không hỗ trợ resume.
- Đặc biệt cẩn thận với phương thức tiện lợi như `DataInputStream.readFully()`: khi ném lỗi giữa chừng, ứng dụng không nhận lại số byte đã tiêu thụ qua giá trị trả về. Muốn hồi phục tinh tế, cần tự giữ tiến độ ở vòng lặp đọc.

Ví dụ một vòng đọc có **deadline tổng**, tách khỏi timeout của từng `read`:

~~~java
// Đoạn này là phương thức bổ sung, cần các import:
// java.io.*; java.net.*; java.util.concurrent.TimeUnit;
static void readExactlyBeforeDeadline(
        Socket socket, byte[] target, long timeoutMillis)
        throws IOException {

    if (timeoutMillis <= 0) {
        throw new IllegalArgumentException("timeoutMillis must be positive");
    }

    long deadline = System.nanoTime()
            + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
    int offset = 0;

    while (offset < target.length) {
        long remainingNanos = deadline - System.nanoTime();
        if (remainingNanos <= 0) {
            throw new SocketTimeoutException("Whole frame deadline exceeded");
        }

        long remainingMs = Math.max(
                1, TimeUnit.NANOSECONDS.toMillis(remainingNanos));
        socket.setSoTimeout(
                (int) Math.min(remainingMs, Integer.MAX_VALUE));

        int n = socket.getInputStream().read(
                target, offset, target.length - offset);
        if (n == -1) {
            throw new EOFException("Peer closed before full frame");
        }
        offset += n;
    }
}
~~~

Phương thức này minh họa **kỹ thuật bổ sung** khi cần một giới hạn cho *cả đoạn dữ liệu*: đặt deadline trên `System.nanoTime()`, trước mỗi `read` chỉ cho phép chờ tối đa thời gian còn lại, cộng dồn các byte đã đọc. Nó giả định `target.length` là độ dài đã được giao thức kiểm tra hợp lệ; cần áp dụng giới hạn kích thước trước khi cấp phát.

Lưu ý ba giới hạn: (1) timeout chỉ được làm tròn tới đơn vị mili giây, nên không phải deadline thời gian thực tuyệt đối; (2) hàm này **thay đổi SO_TIMEOUT trên socket** và không tự khôi phục giá trị cũ, vì vậy chủ sở hữu socket phải quyết định đặt lại khi dùng tiếp; (3) nếu phương thức ném lỗi, các byte đã điền vào `target` trước đó vẫn tồn tại, và caller cần quyết định đóng phiên hay lưu trạng thái tiến độ thích hợp. Ví dụ minh họa chỉ xử lý phần đọc, không thực hiện connect hay framing prefix.

## 7. Vì sao chỉ đặt timeout vẫn chưa đủ?

### 7.1. Không có timeout ghi bằng `setSoTimeout`

Khi mạng nghẽn hoặc peer đọc chậm, `OutputStream.write(...)` có thể bị chặn bởi TCP flow control. `SO_TIMEOUT` không áp dụng cho ghi. Trong hệ thống thực tế, bạn cần quản lý deadline toàn tác vụ, cơ chế hủy/đóng kết nối, giới hạn payload, tài nguyên và chọn API I/O phù hợp. Không mô tả `setSoTimeout(5_000)` như “sau 5 giây mọi I/O tự dừng”.

### 7.2. Kết nối nhiều lần và retry

Một client có thể làm nhiều lần connect để thử lại khi thất bại. Nhưng nếu có ba lần connect, mỗi lần tối đa 2 giây, rồi read 5 giây và backoff, **tổng thời gian có thể vượt xa 7 giây**. Retry cần được giới hạn cả số lần và ngân sách thời gian; không retry vô hạn chỉ vì lỗi là `SocketTimeoutException`.

Sau **read timeout**, đặc biệt với request làm thay đổi dữ liệu, server có thể đã xử lý xong nhưng phản hồi bị chậm/mất. Retry mù quáng có thể thực hiện nghiệp vụ hai lần. Nếu cần retry an toàn, thiết kế application-level acknowledgment, idempotency key hoặc phép kiểm tra trạng thái.

### 7.3. Tài nguyên và nhiều client đồng thời

Server dùng một thread cho mỗi socket có thể hết thread nếu nhiều client giữ kết nối mà không gửi dữ liệu. Dùng `setSoTimeout` giúp phát hiện các khoảng chờ đọc quá lâu, nhưng không thay thế việc giới hạn số socket, worker queue, kích thước message và **tổng thời gian tồn tại của phiên**. Với `ServerSocket.accept()`, đặt timeout nhận kết nối (nếu cần) **riêng** với timeout đọc của socket được chấp nhận:

~~~java
// Chỉ minh họa sự khác biệt giữa hai socket:
listener.setSoTimeout(1_000);             // Thời gian chờ accept()
Socket acceptedSocket = listener.accept();
acceptedSocket.setSoTimeout(3_000);       // Thời gian chờ read()
~~~

Đoạn này giả định `listener` đã được tạo/bind; các lời gọi có thể ném `IOException`. Nếu `accept()` timeout, listening socket thường vẫn còn dùng được để tiếp tục nhận kết nối. Với nhiều kết nối, hãy cấu hình timeout cho **từng** accepted socket và đóng đúng tài nguyên khi client rời đi.

## 8. Bài tập kiểm tra hiểu bản chất

### Tình huống A: connect thành công, read chờ mãi

~~~text
connect(endpoint, 1500) -> thành công sau 20 ms
setSoTimeout(0)
read()                 -> server không gửi dữ liệu, không đóng
~~~

**Đáp án:** connect đã thành công; `setSoTimeout(0)` không giới hạn thời gian chờ đọc. Nếu server không gửi, không EOF, không lỗi khác, `read()` có thể chờ vô thời hạn. Connect timeout 1.500 ms không có tác dụng ở pha này.

### Tình huống B: peer từ chối kết nối ngay

~~~text
connect(endpoint, 5000) -> ConnectException sau vài ms
~~~

**Đáp án:** việc có timeout 5 giây không có nghĩa kết nối buộc phải chờ đủ 5 giây. Lỗi bị từ chối có thể đến ngay lập tức.

### Tình huống C: một frame lớn được gửi nhỏ giọt

~~~text
SO_TIMEOUT = 1000 ms
Lần đọc 1:  700 ms -> có 1 byte
Lần đọc 2:  700 ms -> có 1 byte
... hàng ngàn lần đọc tương tự
~~~

**Đáp án:** nếu mỗi lần đọc đều có byte trước khi hết thời hạn, không có lần nào cần ném `SocketTimeoutException` chỉ vì tổng thời gian đã vượt 1 giây. Muốn chặn tình huống “slow trickle”, cần deadline tổng và quy tắc giới hạn tiến độ.

### Tình huống D: nhận được một phần dữ liệu rồi timeout

Server quy định trả frame 100 byte, client đã nhận 40 byte, rồi read timeout. **Đáp án:** 40 byte đã đọc vẫn là dữ liệu của frame hiện hành. Nếu quyết định tiếp tục, phải đọc **60 byte còn lại**, không đọc lại 100 byte từ đầu. Nếu parser không giữ được offset hoặc giao thức/ứng dụng không cho phép khôi phục, đóng socket và báo thất bại rõ ràng.

### Tình huống E: muốn timeout cho `accept()`

**Đáp án:** sử dụng `ServerSocket.setSoTimeout(ms)` trên **listening socket**. Nó không đặt timeout đọc cho các client socket đã được `accept()`; mỗi socket client phải được cấu hình độc lập.

## 9. Các lỗi thường gặp và cách sửa

| Lỗi | Tại sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `new Socket(host, port)` rồi kỳ vọng set connect timeout ở bước sau | Constructor đã thử kết nối trước khi bạn cấu hình | Dùng `new Socket()` rồi `connect(endpoint, timeout)` |
| Chỉ gọi `setSoTimeout` để xử lý cả connect và read | Nó chỉ giới hạn đọc blocking trên socket | Gọi `connect(..., timeout)` riêng; cấu hình `setSoTimeout` cho read |
| Nghĩ `SO_TIMEOUT=0` là “không chờ” | `0` nghĩa là chờ vô hạn nếu không có sự kiện khác | Đặt thời hạn dương phù hợp |
| Nghĩ read timeout nghĩa là server đã chết | Server có thể chỉ đang xử lý chậm | Xử lý theo chính sách ứng dụng, không đồng nhất với EOF |
| Lấy tổng connect timeout + read timeout làm deadline tổng | DNS, nhiều lần read/retry và write có thể vượt tổng đó | Dùng deadline chung, theo dõi thời gian còn lại |
| Sau timeout, đọc lại frame từ đầu | Có thể đã tiêu thụ byte trước đó | Giữ parser state và offset hoặc đóng socket |
| Nghĩ `setSoTimeout` cũng giới hạn `write` | Tùy chọn áp dụng cho đọc, không phải ghi | Quản lý deadline/hủy và chọn cơ chế I/O thích hợp |
| Trộn `ServerSocket` và `Socket` | `accept()` và `read()` là các thao tác khác nhau | Cấu hình timeout cho đúng đối tượng |
| Retry sau read timeout với lệnh ghi dữ liệu | Có thể server đã xử lý yêu cầu | Dùng idempotency và ngân sách retry |
| Nuốt `IOException` rồi giữ socket mãi | Trạng thái ứng dụng có thể không còn nhất quán | Log nguyên nhân, đóng/cứu phiên theo protocol rõ ràng |

## 10. Checklist trước khi triển khai socket timeout

- [ ] Mọi `Socket.connect(...)` cần timeout đều dùng overload có `timeout` dương theo **ms**?
- [ ] Socket chỉ gọi đọc sau khi kết nối thành công và đã thiết lập `SO_TIMEOUT` thích hợp?
- [ ] Có phân biệt `SocketTimeoutException` ở **connect** với ở **read**, `ConnectException` và EOF?
- [ ] Với kết nối chậm/không phản hồi, có deadline tổng ngoài timeout từng read?
- [ ] Với frame nhiều byte, có giới hạn chiều dài, lưu offset và xử lý partial read/timeout?
- [ ] Có hiểu `SO_TIMEOUT` không tự áp dụng cho write, TLS, DNS, accept hoặc toàn bộ request?
- [ ] Server đã đặt timeout `accept` riêng nếu cần, và socket được chấp nhận có read timeout riêng?
- [ ] Retry có giới hạn số lần, tổng thời gian và bảo đảm idempotency cho nghiệp vụ có side effect?
- [ ] Socket và executor được đóng/dừng ngay cả khi có lỗi; log có đủ pha, endpoint, thời hạn, nguyên nhân mà không lộ dữ liệu nhạy cảm?

**Kết luận:** `Socket.connect(endpoint, timeout)` bảo vệ **pha thiết lập TCP**; `Socket.setSoTimeout(timeout)` bảo vệ **thời gian chờ của một lần đọc blocking**. Hiểu rõ phạm vi của từng cơ chế, phân biệt timeout với EOF/lỗi kết nối và quản lý deadline ở tầng ứng dụng sẽ giúp chương trình Java tránh treo vô hạn, đọc thiếu frame và retry sai.