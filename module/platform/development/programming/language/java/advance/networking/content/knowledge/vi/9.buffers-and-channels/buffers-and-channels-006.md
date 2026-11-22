# SocketChannel, ServerSocketChannel và chế độ blocking mặc định (Java 17+)

Trong Java NIO, `ServerSocketChannel` đại diện cho đầu lắng nghe kết nối TCP, còn `SocketChannel` đại diện cho một kết nối TCP đã hoặc đang được thiết lập. Dù tên gọi có chữ *NIO*, **cả hai channel mới tạo đều ở chế độ blocking theo mặc định**. NIO không đồng nghĩa “mọi lệnh I/O đều bất đồng bộ” và cũng không có nghĩa phải dùng `Selector` ngay từ đầu.

Kiến thức nền thuộc nhóm **Buffer và channel**: channel đọc/ghi qua `ByteBuffer`, không phải trực tiếp qua `byte[]` như nhiều ví dụ `Socket.getInputStream()` cổ điển. Bài này giúp bạn nắm vòng đời channel, ngữ nghĩa blocking của `open/connect/bind/accept/read/write`, quy tắc `ByteBuffer`, cách chạy một TCP server đơn giản bằng NIO blocking, và thời điểm chuyển sang non-blocking + `Selector`.

## 1. Bức tranh tổng thể: hai loại channel, hai vai trò

```text
Client JVM                                  Server JVM
-----------------                           ------------------
SocketChannel.open(...)                     ServerSocketChannel.open()
connect(serverAddress)                      bind(listenAddress)
       |                                          |
       | ------------ TCP connect --------------> |
       |                                          | accept()
       |                                          v
       |                                    SocketChannel peer
       |                                          |
write(ByteBuffer) -----------------------> read(ByteBuffer)
read(ByteBuffer)  <----------------------- write(ByteBuffer)
       |                                          |
  close() / half-close                    close() / half-close
```

- **`ServerSocketChannel`**: đối tượng lắng nghe trên địa chỉ/port; không trực tiếp `read/write` dữ liệu ứng dụng của các client. Mỗi kết nối được chấp nhận tạo một **`SocketChannel` riêng**.
- **`SocketChannel`**: channel song công của một TCP connection; đọc/ghi byte theo `ByteBuffer`. Một đầu client có thể tạo bằng `SocketChannel.open(address)` hoặc `open()` rồi `connect(address)`.
- **`ByteBuffer`**: lưu vùng byte có `position`, `limit`, `capacity`, dùng để chuyển byte giữa channel và ứng dụng.
- **`SelectableChannel`**: lớp nền cho hai loại channel; có thể `configureBlocking(false)` để đăng ký vào `Selector` khi muốn xử lý readiness của nhiều socket.

Một server blocking điển hình dùng **một thread accept** và giao mỗi client cho một thread/task phù hợp. Không được lẫn logic *lắng nghe kết nối* với logic *đọc request của kết nối đã accept*.

## 2. Blocking mặc định: chính xác là mặc định của đối tượng nào?

Ngay sau khi tạo bằng các factory API thông thường:

| Đối tượng / thao tác | Trạng thái / hành vi cơ bản |
| --- | --- |
| `ServerSocketChannel.open()` | Channel **open, chưa bind**, mặc định **blocking=true** |
| `server.bind(localAddress)` | Gắn địa chỉ/port; **không** biến channel thành non-blocking |
| `server.accept()` khi blocking=true | Chờ một kết nối đến, hoặc lỗi/đóng/interrupt; trả một `SocketChannel` |
| `SocketChannel.open()` | Channel **open, chưa kết nối**, mặc định **blocking=true** |
| `SocketChannel.open(remote)` | Tạo channel và kết nối tới remote theo chế độ blocking mặc định; nếu thành công, trả channel connected |
| `channel.connect(remote)` khi blocking=true | Chờ kết nối hoàn thành hoặc phát sinh lỗi |
| `server.accept()` khi server non-blocking | Nếu chưa có kết nối chờ, trả `null` ngay |
| `SocketChannel` được `accept()` trả về | **Luôn ở blocking mode lúc vừa được trả**, kể cả khi listening channel non-blocking |

**Điểm hay nhầm nhất:** `ServerSocketChannel.configureBlocking(false)` chỉ thay đổi **chế độ của listening channel đó**. Nó **không tự động** biến các `SocketChannel` accept được thành non-blocking. Muốn đăng ký accepted socket vào `Selector`, phải chủ động gọi `accepted.configureBlocking(false)`.

Có thể kiểm tra trạng thái bằng `isBlocking()`, nhưng kết quả ấy chỉ phản ánh cấu hình mode của channel, **không chứng minh peer còn sống**, không xác nhận request đã đủ byte và không bảo đảm một lời gọi read sẽ lấp đầy buffer.

## 3. Tạo và bind ServerSocketChannel đúng vòng đời

Với internet TCP socket, một trình tự tối giản:

```java
// Đoạn minh họa trong method có throws IOException.
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress("127.0.0.1", 8080));
    while (true) {
        SocketChannel client = server.accept(); // blocking mặc định
        // Chuyển client cho handler sở hữu và đóng nó khi hoàn tất.
    }
}
```

Đoạn này **chỉ minh họa vòng đời**, chưa có handler đóng `client` và chưa có chiến lược dừng: không nên triển khai nguyên xi như production. Các điều cần ghi nhớ:

1. `open()` tạo channel **chưa bind**. Gọi `accept()` trước `bind(...)` với internet socket có thể ném `NotYetBoundException`, không phải âm thầm mở cổng ngẫu nhiên.
2. `bind(new InetSocketAddress(address, 0))` dùng **port 0** để hệ điều hành cấp cổng rảnh, rất phù hợp cho thử nghiệm. Dùng `getLocalAddress()` để đọc port sau khi bind.
3. `bind(...)` có thể thất bại (port bận, địa chỉ không tồn tại, quyền truy cập, hạn chế OS). Không bỏ qua `IOException`.
4. `accept()` khi blocking sẽ đợi cho đến khi có kết nối chờ hoặc xảy ra sự kiện hủy/lỗi; **không** phải hàm “poll rồi trả null” như khi non-blocking.
5. Với server public cần xác định bind vào wildcard/interface nào và cơ chế TLS/authentication/network firewall. Bind vào loopback để thử nghiệm, không tự mở ra Internet trong ví dụ học tập.
6. Mỗi accepted connection cần owner chịu trách nhiệm đóng `SocketChannel` khi hoàn tất. Đóng riêng accepted channel **không** tự đóng listening channel.
7. Hàng đợi kết nối chờ (**backlog**) và giới hạn hệ điều hành không phải số lượng client có thể xử lý vô hạn. Thiết kế giới hạn số handler và hành vi quá tải.

Một `ServerSocketChannel` có thể được nhiều thread gọi `accept()`, nhưng Java API đồng bộ hóa các accept đồng thời ở mức channel. Việc nhiều thread cùng gọi accept không thay thế thiết kế vòng đời/điều phối.

## 4. Kết nối client bằng SocketChannel: blocking connect

Hai cách thường gặp:

```java
// Cách A: tạo rồi connect
try (SocketChannel channel = SocketChannel.open()) {
    boolean connected =
            channel.connect(new InetSocketAddress("127.0.0.1", 8080));
    // Ở blocking mode, connect thành công -> connected == true.
}

// Cách B: factory tạo và kết nối trực tiếp
try (SocketChannel channel = SocketChannel.open(
        new InetSocketAddress("127.0.0.1", 8080))) {
    // Đã kết nối nếu constructor/factory trả về bình thường.
}
```

Cả hai đoạn là **minh họa API**, chỉ chạy nếu có server thực sự lắng nghe trên cổng 8080. Trong chế độ blocking, `connect(remote)` chờ hoàn thành kết nối hoặc báo lỗi; khi thành công, thường trả `true`. Trong non-blocking, nó có thể trả `false` nghĩa là quá trình kết nối **đang diễn ra**, và cần xử lý `finishConnect()` khi socket sẵn sàng, thường sau sự kiện `OP_CONNECT` của `Selector`.

`isConnected()` phản ánh trạng thái kết nối đã thiết lập của channel; không phải phép health check cho mọi thao tác tương lai. Kết nối có thể bị đóng hoặc lỗi ngay sau lần kiểm tra. Không gọi `read/write` trước khi kết nối hoàn chỉnh: các API có thể ném `NotYetConnectedException`.

**Timeout:** blocking `connect` có thể chờ lâu tùy mạng/OS. Java NIO `SocketChannel.connect` không nhận tham số timeout giống `Socket.connect(endpoint, timeout)`. Khi cần deadline kết nối nghiêm ngặt, phải thiết kế cách quản lý timeout riêng phù hợp (chẳng hạn non-blocking connect + Selector + deadline hoặc sử dụng API/protocol khác). Không suy luận rằng cấu hình socket read timeout sẽ tự trở thành connect timeout của channel.

## 5. Blocking mode tác động thế nào đến accept/read/write?

| API | Blocking mode (`true`) | Non-blocking mode (`false`) |
| --- | --- | --- |
| `ServerSocketChannel.accept()` | Đợi kết nối; trả channel khi có | Có thể trả `null` ngay nếu chưa có pending connection |
| `SocketChannel.connect(addr)` | Chờ thành công/lỗi | Có thể trả `false`; hoàn tất qua `finishConnect()` |
| `SocketChannel.read(dst)` | Với `dst.remaining()>0`, đợi **ít nhất 1 byte**, EOF hoặc lỗi; không cam kết lấp đầy buffer | Có thể trả `0` khi chưa có byte sẵn |
| `SocketChannel.write(src)` | Thông thường đợi ghi hết số byte được yêu cầu vào đường gửi của channel hoặc lỗi; có thể block khi send buffer đầy | Có thể ghi một phần hoặc `0` khi không còn chỗ ngay lúc đó |
| `Selector.register(...)` | **Không được** đăng ký channel khi còn blocking | Là mode cần thiết để đăng ký một selectable channel với selector |

Trong blocking mode, **`read` trả về ít hơn `dst.remaining()` là hợp lệ**. Ví dụ buffer còn chỗ 4096 byte nhưng peer chỉ mới gửi 10 byte: `read` có thể trả 10. Không nhất thiết chờ cho đủ 4096.

Ở blocking `SocketChannel.write(src)`, hợp đồng channel thông thường cố ghi hết `src.remaining()` trước khi trả. Tuy vậy vòng `while (src.hasRemaining())` vẫn là cách trình bày an toàn để luôn theo dõi `ByteBuffer.position()`, tránh phụ thuộc giả định nếu thiết kế đổi sang non-blocking hoặc gathering writes. **Ghi xong không có nghĩa ứng dụng ở peer đã xử lý xong.**

Nếu không thể read do peer đã đóng chiều gửi có trật tự và hết dữ liệu, `read` trả **`-1`** (EOF). Nếu buffer trống (`remaining()==0`), `read` có thể trả `0` mà không cần kết nối có dữ liệu.

## 6. ByteBuffer: position, limit, capacity và chuyển đổi giữa đọc/ghi

Một `ByteBuffer` có ba con số thiết yếu:

- **`capacity`**: dung lượng cố định của buffer.
- **`limit`**: biên trên (exclusive) của dữ liệu/bộ nhớ đang được truy cập trong mode hiện tại.
- **`position`**: vị trí byte kế tiếp để đặt vào hoặc lấy ra.

Luôn có `0 <= position <= limit <= capacity`. Ví dụ `ByteBuffer.allocate(8)`:

```text
Mới cấp phát:     position=0, limit=8, capacity=8
put 3 byte:       position=3, limit=8, capacity=8
flip():          position=0, limit=3, capacity=8   (đọc 3 byte)
get 2 byte:       position=2, limit=3, capacity=8
compact():       position=1, limit=8, capacity=8   (giữ 1 byte còn lại)
flip():          position=0, limit=1, capacity=8   (đọc byte còn lại)
```

Trong **nhận TCP**, channel ghi byte từ socket vào buffer (`channel.read(buffer)`). Sau đó ứng dụng chuyển buffer từ **write mode → read mode** bằng `flip()`, tiêu thụ byte hợp lệ, rồi `clear()` nếu đã xử lý hết hoặc `compact()` nếu vẫn còn byte chưa tiêu thụ.

Trong **gửi TCP**, ứng dụng viết byte vào buffer (hoặc dùng `ByteBuffer.wrap(payload)`/`StandardCharsets.UTF_8.encode(text)`), `flip()` nếu vừa `put(...)`, rồi `channel.write(buffer)` để channel tiêu thụ byte từ `position` đến `limit`.

| Method | Làm gì? | Không làm gì? |
| --- | --- | --- |
| `flip()` | `limit = position; position = 0`, chuẩn bị **đọc bytes vừa ghi vào** | Không sao chép dữ liệu |
| `clear()` | `position = 0; limit = capacity`, chuẩn bị **ghi đè** buffer | **Không** xóa sạch byte cũ về 0 |
| `compact()` | Giữ byte chưa tiêu thụ, dồn về đầu rồi chuẩn bị nhận thêm | Không giữ phần byte đã tiêu thụ |
| `rewind()` | `position = 0`, đọc lại trong `limit` hiện tại | Không đổi limit |
| `remaining()` | `limit - position` | Không phải số byte TCP còn ở mạng |
| `hasRemaining()` | Cho biết còn byte trong vùng buffer đã định nghĩa | Không phải “socket vẫn còn mở” |

Một lỗi rất thường gặp là `read(buffer)` xong **quên `flip()`**, rồi parse vùng từ `position` đến `limit`. Khi ấy parser có thể bỏ qua byte vừa nhận hoặc đọc rác dữ liệu cũ.

## 7. Đọc nhiều lượt: TCP là byte stream, không phải ranh giới message

Giả sử client gọi `write` hai lần với hai chuỗi `ABC` và `DEF`. Server có thể nhận `AB`, `CDE`, `F` trong ba lượt `read` hoặc một lượt `ABCDEF`. TCP chỉ giữ **thứ tự byte**, không giữ ranh giới các lời gọi `write`.

Một vòng lặp nhận byte đến EOF (đoạn minh họa **không phải chương trình độc lập**, giả định `channel` đã connected):

```java
ByteBuffer buffer = ByteBuffer.allocate(1024);
while (true) {
    int n = channel.read(buffer); // Có thể block.
    if (n == -1) break;           // Peer đóng chiều gửi.
    buffer.flip();
    while (buffer.hasRemaining()) {
        byte oneByte = buffer.get();
        // Xử lý byte hiện có; chưa chắc đủ một message.
    }
    buffer.clear();
}
```

Đoạn trên phù hợp khi ứng dụng cố ý **đọc tới EOF** và dữ liệu nhận không vượt ngân sách. Nhưng với giao thức giữ socket mở để gửi nhiều request/response, **EOF không phải ranh giới từng message**; đọc đến EOF có thể gây deadlock khi hai phía đều giữ kết nối mở để chờ nhau.

**Không giải mã UTF-8 từng `ByteBuffer` read độc lập** khi ký tự có nhiều byte có thể bị cắt giữa lượt nhận. Hoặc ghép đúng byte của từng frame rồi decode, hoặc dùng decoder có trạng thái xuyên các chunk. Đừng coi `available()` trên stream/socket wrapper là số byte của message sắp đến.

## 8. Ví dụ hoàn chỉnh 1 — BlockingChannelEcho: accept, read, write, half-close

Tệp **`BlockingChannelEcho.java`** tạo listener trên IPv4 loopback `127.0.0.1` với port tự cấp, mở một `SocketChannel` client, accept thành server-side `SocketChannel` và trao đổi một request/response.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class BlockingChannelEcho {
    private static void writeAll(SocketChannel channel, String message)
            throws IOException {
        ByteBuffer src = StandardCharsets.UTF_8.encode(message);
        while (src.hasRemaining()) {
            channel.write(src);
        }
    }

    private static String readToEof(SocketChannel channel)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        ByteBuffer buffer = ByteBuffer.allocate(3);
        while (true) {
            int n = channel.read(buffer);
            if (n == -1) {
                break;
            }
            buffer.flip();
            while (buffer.hasRemaining()) {
                bytes.write(buffer.get() & 0xFF);
            }
            buffer.clear();
        }
        return new String(bytes.toByteArray(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(local, 0));
            int port = ((InetSocketAddress) listener.getLocalAddress())
                    .getPort();

            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(local, port));
                 SocketChannel accepted = listener.accept()) {

                System.out.println("Listener blocking: "
                        + listener.isBlocking());
                System.out.println("Client blocking: "
                        + client.isBlocking());
                System.out.println("Accepted blocking: "
                        + accepted.isBlocking());

                writeAll(client, "HELLO NIO");
                client.shutdownOutput();

                String request = readToEof(accepted);
                writeAll(accepted, "ACK " + request);
                accepted.shutdownOutput();

                String response = readToEof(client);
                System.out.println("Server saw: " + request);
                System.out.println("Client saw: " + response);
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```sh
javac -encoding UTF-8 BlockingChannelEcho.java
java BlockingChannelEcho
```

Stdout xác định trên lần chạy thành công:

```text
Listener blocking: true
Client blocking: true
Accepted blocking: true
Server saw: HELLO NIO
Client saw: ACK HELLO NIO
```

Các điểm cần đọc trong mã:

1. `ServerSocketChannel.open()` mặc định blocking, nhưng **chưa bind**; `bind(new InetSocketAddress(local, 0))` mới tạo endpoint lắng nghe.
2. `SocketChannel.open(remote)` kết nối trong blocking mode. `listener.accept()` trả channel connected riêng cho phía server, cũng mặc định blocking.
3. `StandardCharsets.UTF_8.encode(message)` đã tạo `ByteBuffer` ở trạng thái sẵn sàng đọc byte để ghi vào channel, nên **không gọi `flip()` lần nữa** trên buffer ấy.
4. Hàm `readToEof` dùng buffer nhỏ **3 byte** cố ý để quan sát read nhiều lượt; nó chỉ ghép byte, không giải mã từng chunk. Sau khi ghép đủ byte của một chiều, mới tạo `String`.
5. `client.shutdownOutput()` báo client không gửi thêm request. Server đọc tới EOF, nhưng **vẫn có thể ghi response theo chiều ngược** vì kết nối TCP full-duplex.
6. `accepted.shutdownOutput()` báo kết thúc response. Client cũng đọc tới EOF, rồi kiểm tra chuỗi hoàn chỉnh.

Chương trình dùng **một thread** vì thứ tự write/half-close/read được sắp xếp để không chờ vòng tròn. Với ứng dụng tương tác nhiều message, phải chuyển sang framing, không dựa vào `shutdownOutput` sau mỗi message. Loopback thành công không chứng minh server production xử lý quá tải, đóng sai thứ tự hoặc mất kết nối ở WAN.

## 9. Framing với SocketChannel: readFully ở tầng ứng dụng

Để gửi nhiều thông điệp trên cùng TCP connection, thiết kế **length-prefix**. Ví dụ mỗi message dùng một header 4 byte big-endian mô tả số byte UTF-8 tiếp theo:

```text
+----------------------------+------------------------+
| 4-byte int N (big-endian)  | N byte UTF-8 payload    |
+----------------------------+------------------------+

sender: putInt(N) -> flip() -> writeFully(header)
        wrap(payload) -> writeFully(body)

receiver: readFully(4-byte header) -> flip() -> getInt()
          validate N -> readFully(N-byte body) -> flip() -> decode once
```

**Vòng `readFully`** là công cụ của **giao thức ứng dụng**, không phải API tự có của `SocketChannel`:

```java
// Đoạn minh họa: ch và dst đã tồn tại, blocking mode.
while (dst.hasRemaining()) {
    int n = ch.read(dst);
    if (n == -1) {
        throw new EOFException("Frame ended early");
    }
}
```

Trên blocking `SocketChannel` khi `dst.remaining() > 0`, `read` sẽ chờ byte/EOF/lỗi; vòng lặp vì thế hoàn tất khi nhận đủ số byte được khai báo hoặc fail khi EOF sớm. **Không bê y nguyên vòng này sang non-blocking mode**: `read` có thể trả `0`, khiến vòng lặp spin CPU không tiến triển. Trong non-blocking, phải giữ partial state và đợi `OP_READ` mới (hoặc readiness phù hợp).

Nếu peer khai báo `N` cực lớn hoặc âm, từ chối **trước khi cấp phát** body buffer; giới hạn theo protocol, tenant và bộ nhớ thực. Nếu frame chưa đủ mà peer đóng kết nối, ném `EOFException` và không đưa dữ liệu dở dang vào logic nghiệp vụ.

## 10. Ví dụ hoàn chỉnh 2 — FramedBlockingNio: hai frame trên một connection

Tệp **`FramedBlockingNio.java`** dùng `ByteBuffer` để ghi/đọc header `int32` big-endian, giới hạn mỗi payload **4.096 byte**, gửi hai frame UTF-8 và nhận một frame phản hồi trên **cùng** socket TCP. Bên nhận dùng `CharsetDecoder` ở chế độ `REPORT` để không âm thầm thay thế byte UTF-8 sai.

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class FramedBlockingNio {
    private static final int MAX_PAYLOAD = 4096;

    private static void writeFully(SocketChannel channel, ByteBuffer data)
            throws IOException {
        while (data.hasRemaining()) {
            channel.write(data);
        }
    }

    private static void readFully(SocketChannel channel, ByteBuffer target)
            throws IOException {
        while (target.hasRemaining()) {
            if (channel.read(target) == -1) {
                throw new EOFException("Incomplete frame");
            }
        }
    }

    private static void sendFrame(SocketChannel channel, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_PAYLOAD) {
            throw new IOException("Frame too large");
        }
        ByteBuffer header = ByteBuffer.allocate(4)
                .order(ByteOrder.BIG_ENDIAN);
        header.putInt(payload.length);
        header.flip();
        writeFully(channel, header);
        writeFully(channel, ByteBuffer.wrap(payload));
    }

    private static String receiveFrame(SocketChannel channel)
            throws IOException {
        ByteBuffer header = ByteBuffer.allocate(4)
                .order(ByteOrder.BIG_ENDIAN);
        readFully(channel, header);
        header.flip();

        int length = header.getInt();
        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("Invalid length: " + length);
        }

        ByteBuffer body = ByteBuffer.allocate(length);
        readFully(channel, body);
        body.flip();
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(body).toString();
    }

    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        String first = "Xin chào";
        String second = "NIO \uD83D\uDE00";

        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(local, 0));
            int port = ((InetSocketAddress) listener.getLocalAddress())
                    .getPort();

            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(local, port));
                 SocketChannel accepted = listener.accept()) {

                sendFrame(client, first);
                sendFrame(client, second);

                String one = receiveFrame(accepted);
                String two = receiveFrame(accepted);
                sendFrame(accepted, "OK 2");

                String reply = receiveFrame(client);
                System.out.println("Frames received: 2");
                System.out.println("First matches: "
                        + first.equals(one));
                System.out.println("Second matches: "
                        + second.equals(two));
                System.out.println("First UTF-8 bytes: "
                        + first.getBytes(StandardCharsets.UTF_8).length);
                System.out.println("Reply: " + reply);
            }
        }
    }
}
```

Chạy:

```sh
javac -encoding UTF-8 FramedBlockingNio.java
java FramedBlockingNio
```

Stdout xác định:

```text
Frames received: 2
First matches: true
Second matches: true
First UTF-8 bytes: 9
Reply: OK 2
```

Giải thích:

- `"Xin chào"` có **9 byte UTF-8**; độ dài frame phải là `payload.length`, không phải `String.length()`. Chuỗi thứ hai có emoji ngoài BMP nhằm kiểm tra xử lý Unicode qua byte stream.
- `ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN)` ghi và đọc int nhất quán; `putInt` tăng `position` nên sender gọi `flip` trước khi write.
- `readFully(header)` không đoán rằng một lần đọc nhận đủ 4 byte. `readFully(body)` không đoán lần đọc sẽ trùng với một lần gửi frame. `body.flip()` chuẩn bị cho decoder tiêu thụ đúng N byte.
- `while (data.hasRemaining()) channel.write(data)` theo dõi phần buffer còn chưa được ghi; hữu ích khi mở rộng code, nhưng khi chuyển sang non-blocking **cần xử lý `0` qua readiness**, không được spin.
- Hai frame được ghép đúng nhờ **header length**, không phụ thuộc EOF. Sau khi server đọc hai frame, nó gửi frame phản hồi `OK 2`; client đọc đúng một frame phản hồi mà không cần chờ server đóng kết nối.
- `newDecoder().onMalformedInput(REPORT)` báo lỗi khi byte UTF-8 không hợp lệ; `String.getBytes(UTF_8)` thường thay surrogate không hợp lệ ở nguồn, nên nếu dữ liệu đầu vào Java có thể malformed thì còn cần kiểm tra/strict-encode ở chiều gửi.

Đây là demo **synchronous blocking với khối lượng nhỏ**, không đại diện thiết kế event loop. Để bảo vệ production, thêm deadline end-to-end, giới hạn queue, xác thực peer, policy xử lý message malformed và đóng kết nối khi giao thức sai.

## 11. Chuyển sang non-blocking: configureBlocking(false) không phải lời gọi “read nhanh hơn”

`SelectableChannel.configureBlocking(false)` đổi cách các operation chờ:

```java
// Minh họa, không phải class độc lập.
server.configureBlocking(false);
SocketChannel incoming = server.accept();
if (incoming == null) {
    // Chưa có kết nối đang chờ: đây là kết quả bình thường.
}

// Sau khi accept thành công:
incoming.configureBlocking(false); // Đổi riêng accepted channel.
```

Ở mode non-blocking:

- `accept()` có thể trả `null`; đó không phải EOF hay lỗi.
- `connect()` có thể chưa hoàn thành; khi `false`, theo dõi trạng thái và gọi `finishConnect()` đúng lúc.
- `read(ByteBuffer)` có thể trả `0` nếu chưa có byte ngay; phải giữ `ByteBuffer` và parser state để tiếp tục ở sự kiện sau.
- `write(ByteBuffer)` có thể ghi **một phần** hoặc `0`; phải giữ lại phần chưa ghi để retry khi writable. **`OP_WRITE` thường luôn “ready” khi socket còn chỗ**, nên chỉ quan tâm OP_WRITE khi thực sự có pending outbound data để tránh vòng lặp nóng.
- Một accepted `SocketChannel` **vẫn blocking=true** ngay khi `accept()` trả về, dù listening channel non-blocking; phải đổi mode của accepted channel nếu muốn register với selector.

**Không** dùng vòng `while (channel.read(buffer) == 0) { }` hay `while (channel.write(buffer) == 0) { }` liên tục trong non-blocking code: nó chỉ đốt CPU. Dùng readiness notifications/`Selector` và quản lý backpressure.

## 12. Ví dụ hoàn chỉnh 3 — BlockingModeSwitch: mode và accept(null)

Tệp **`BlockingModeSwitch.java`** cho thấy cùng một `ServerSocketChannel` có thể chuyển qua non-blocking khi không đăng ký selector, nhận `null` lúc chưa có client, rồi chuyển lại blocking. Client được mở **sau** lần `accept` non-blocking để trạng thái “chưa có pending client” là xác định.

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

public class BlockingModeSwitch {
    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(local, 0));
            int port = ((InetSocketAddress) listener.getLocalAddress())
                    .getPort();

            System.out.println("Default blocking: "
                    + listener.isBlocking());
            listener.configureBlocking(false);
            System.out.println("Nonblocking now: "
                    + !listener.isBlocking());

            // No client has been created: accept returns null immediately.
            SocketChannel absent = listener.accept();
            System.out.println("No pending client: " + (absent == null));

            listener.configureBlocking(true);
            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(local, port));
                 SocketChannel accepted = listener.accept()) {
                System.out.println("Blocking restored: "
                        + listener.isBlocking());
                System.out.println("Accepted blocking: "
                        + accepted.isBlocking());
                System.out.println("Client connected: "
                        + client.isConnected());
            }
        }
    }
}
```

Chạy:

```sh
javac -encoding UTF-8 BlockingModeSwitch.java
java BlockingModeSwitch
```

Stdout:

```text
Default blocking: true
Nonblocking now: true
No pending client: true
Blocking restored: true
Accepted blocking: true
Client connected: true
```

Trong chương trình, `listener.configureBlocking(true)` an toàn vì nó **không hề đăng ký với `Selector`**. Nếu channel đang có registration/key hợp lệ trong selector, cố bật lại blocking mode sẽ gây `IllegalBlockingModeException`; cần hủy key và đợi registration không còn hiệu lực theo đúng quy trình trước khi thay mode.

Ví dụ chỉ demo mode change. Nó **không** xây dựng vòng event loop; một server thật không liên tục thay blocking↔non-blocking để “thử xem có dữ liệu chưa”, mà chọn hẳn mô hình concurrency thích hợp.

## 13. Một giới thiệu ngắn về Selector, đúng mức cần để hiểu blocking

`Selector` giúp **một thread theo dõi readiness** của nhiều selectable channel đã ở non-blocking mode. Các operation thường gắn với `SelectionKey`:

| Channel | Ops hỗ trợ thường dùng | Khi nào quan tâm |
| --- | --- | --- |
| `ServerSocketChannel` | `OP_ACCEPT` | Có khả năng chấp nhận một kết nối mới |
| `SocketChannel` chưa hoàn tất connect | `OP_CONNECT` | Có thể hoàn tất `finishConnect()` |
| `SocketChannel` đã connected | `OP_READ` | Có khả năng đọc; còn có thể gặp EOF |
| `SocketChannel` có pending outbound bytes | `OP_WRITE` | Có khả năng ghi thêm, nhưng không hứa ghi hết buffer |

Trình tự cơ bản:

```text
server.configureBlocking(false)
server.register(selector, OP_ACCEPT)
                 |
              select()
                 |
               ready
                 |
           server.accept()
                 |
       accepted.configureBlocking(false)
       accepted.register(selector, OP_READ)
                 |
         read into per-connection ByteBuffer
         parse complete frames; retain incomplete bytes
                 |
       queue response; when necessary enable OP_WRITE
                 |
          write until no progress
```

`Selector.select()` có thể chặn **selector thread** để chờ sự kiện; đó **không biến operations trên channel trở lại blocking mode**. Readiness không hứa một request TCP đã đầy đủ. Ngay cả khi nhận event OP_READ, code phải xử lý số byte thực nhận, `-1` và frame còn dang dở.

Mở rộng từ blocking server sang selector là thay đổi **kiến trúc state machine và ownership**, không chỉ thêm `configureBlocking(false)` vào từng socket. Đừng cố đăng ký `SocketChannel` mới accept mà quên đổi mode của nó.

## 14. Lỗi, timeout, interrupt và close của blocking channel

### Blocking I/O có thể chờ lâu

- `server.accept()` có thể chờ đến khi có client.
- `SocketChannel.read(buffer)` có thể chờ byte/EOF; nếu peer giữ socket mở mà không gửi, ứng dụng có thể chờ rất lâu.
- `SocketChannel.write(buffer)` có thể chờ khi peer đọc chậm và kernel send buffer đầy.
- `SocketChannel.connect(endpoint)` có thể chờ kết nối; deadline phụ thuộc OS nếu bạn không thiết kế timeout riêng.

Một chương trình blocking server cần chính sách **timeout/deadline ở tầng giao thức**, giới hạn tài nguyên và đường đóng an toàn. Đừng mặc định `Socket.setSoTimeout` áp dụng cho mọi lời gọi `SocketChannel.read`: tùy API, option này gắn với thao tác đọc của socket stream, không phải “timeout chung của mọi channel method”. Với channel cần deadline chặt, cân nhắc non-blocking selector + deadline hoặc cơ chế điều phối/cancellation có quản lý.

### Cách hủy một thread đang block

Đối với các channel chuẩn implement `InterruptibleChannel`:

- Thread đang block trong `accept/read/write` có thể bị thread khác **interrupt**: channel bị đóng và thường ném `ClosedByInterruptException`; interrupt status được đặt. **Không dùng lại channel bị đóng**.
- Thread khác **đóng channel** trong lúc I/O đang block có thể dẫn tới `AsynchronousCloseException`; caller phải xử lý đóng phiên.
- Peer đóng chiều gửi có trật tự khiến `read` cuối cùng trả `-1` **sau khi những byte trước đó đã được giao tới ứng dụng**. Kết nối reset/lỗi có thể ném `IOException` thay vì EOF.
- `SocketChannel.shutdownOutput()` đóng **chiều gửi** để peer có thể thấy EOF, nhưng chiều nhận của cùng connection vẫn có thể hoạt động. `close()` giải phóng cả channel, không chứng nhận peer đã xử lý payload.

Các ngoại lệ đáng nhận diện: `ClosedChannelException`, `NotYetConnectedException`, `NotYetBoundException`, `ConnectException`/`IOException`, `ClosedByInterruptException`, `AsynchronousCloseException` và `IllegalBlockingModeException` khi vi phạm quy tắc selector/blocking mode.

**Khác biệt bảo đảm:** `SocketChannel.write` thành công chỉ chứng nhận thao tác ghi của channel đã hoàn thành theo giao diện; nó **không chứng minh** ứng dụng peer đọc xong hay giao dịch đã commit. Muốn xác nhận nghiệp vụ cần response/ACK tầng ứng dụng.

## 15. Server blocking phục vụ nhiều client: giới hạn và tính đúng đắn

Một vòng accept blocking không nhất thiết làm **mọi kết nối** bị block, nếu handler được tách ra:

```text
Listener thread (blocking accept)
   |
   +--> client A --> worker A: blocking read/parse/write
   +--> client B --> worker B: blocking read/parse/write
   +--> client C --> worker C: blocking read/parse/write
```

Tuy nhiên, mô hình **một OS thread/client** không scale vô hạn. Nếu client idle hay gửi rất chậm, thread bị giữ lâu. Dùng `ExecutorService` có giới hạn, timeout/deadline, quota và policy reject/close để tránh vô hạn threads/queue. Khi handler tách thread, đảm bảo accepted `SocketChannel` được đóng đúng owner, kể cả lúc submit task bị từ chối.

**Điều phối ghi:** một `SocketChannel` hỗ trợ một read và một write đồng thời theo API, nhưng nhiều writer cùng một hướng có thể làm **frame logic** xen nhau nếu chúng ghi header/body ở nhiều bước. Nên gắn một writer owner, queue outbound bounded hoặc một lock **theo kết nối** bao trọn frame; không dùng một lock global bao trọn I/O của mọi client.

**Đồng bộ dữ liệu chung:** Map/session/counter dùng bởi các worker cần thread-safe algorithm đúng invariant; `ConcurrentHashMap` không biến chuỗi `get→put` thành update nguyên tử. Dùng `compute/merge` hay CAS/snapshot/lock ngắn khi cần; giữ I/O bên ngoài lock bảo vệ shared state.

**Tốc độ gửi/nhận:** ByteBuffer/direct buffer có thể giúp giảm copy trong các workload phù hợp, nhưng áp lực buffer, số syscall, số kết nối và vòng đời tài nguyên quan trọng hơn việc “NIO luôn nhanh hơn IO”. Blocking NIO không tự giải quyết slow client; selector cũng không tự giải quyết backpressure của protocol.

## 16. Những lỗi phổ biến khi bắt đầu với SocketChannel

1. **“NIO tự non-blocking.”** Sai: `SocketChannel` và `ServerSocketChannel` ban đầu blocking. Kiểm tra `isBlocking()`.
2. **“`open()` nghĩa là đã bind/listen.”** Sai: `ServerSocketChannel.open()` chưa bind, phải `bind(...)` trước `accept()`.
3. **“`accept()` luôn trả ngay.”** Sai trong blocking mode: nó chờ. Chỉ trong non-blocking mới có kết quả `null` khi chưa có pending client.
4. **“Server non-blocking nên socket accept cũng non-blocking.”** Sai: accepted channel **được trả ở blocking mode**.
5. **“`read(ByteBuffer)` phải đọc đầy buffer.”** Sai: blocking chỉ bảo đảm đợi ít nhất một byte nếu còn chỗ, EOF hoặc lỗi. Muốn N byte thì lặp đọc đủ theo framing.
6. **“`read` trả `0` nghĩa là peer đã đóng.”** Sai: EOF là `-1`; `0` bình thường khi buffer có `remaining()==0` hoặc trong non-blocking chưa có dữ liệu.
7. **“Quên `flip()` sau khi nhận byte.”** Parser sẽ thấy `position` sai. Sau tiêu thụ, `clear` hoặc `compact` phù hợp.
8. **“Gọi `flip()` trên buffer đã `StandardCharsets.UTF_8.encode` trả về.”** Buffer ấy đã sẵn sàng để được channel đọc; flip lần nữa có thể làm mất vùng còn byte hợp lệ.
9. **“`clear()` xóa byte trong RAM.”** Sai: chỉ reset các chỉ số; byte cũ vẫn có thể còn trong bộ nhớ.
10. **“Một `write` là một message.”** TCP là byte stream. Định nghĩa length-prefix/delimiter và dùng per-connection parser state.
11. **“Dùng read-until-EOF cho mọi request.”** Dễ treo khi hai phía đều giữ socket mở; framing mới là ranh giới message trong kết nối lâu dài.
12. **“Đổi `configureBlocking(false)` nhưng giữ vòng `readFully` chặn.”** `read` có thể trả 0 và vòng loop spin. Thay bằng readiness + buffer state.
13. **“Dùng `Selector.register()` khi channel vẫn blocking.”** Gây `IllegalBlockingModeException`. Đổi channel sang non-blocking trước.
14. **“`Selector` có nghĩa mỗi lần ready là một request đầy đủ.”** Sai: readiness chỉ là dấu hiệu có thể tiến triển I/O; vẫn phải tích lũy và parse đủ frame.
15. **“`socket().setSoTimeout(5000)` chắc chắn làm `SocketChannel.read` timeout.”** Không nên dựa vào giả định đó; chọn API timeout/deadline phù hợp.
16. **“Một channel tạo ra từ accept có thể bỏ quên không đóng.”** Rò connection/file descriptor, tăng memory và cạn tài nguyên; quản lý try-with-resources/owner.
17. **“Blocking mode quyết định tính song song của server.”** Nó chỉ định cách **operation I/O chờ**; concurrency phụ thuộc thread/task/event loop và cách phân chia state.
18. **“Ghi vào channel nghĩa là server đã lưu dữ liệu.”** Không; cần xác nhận tầng ứng dụng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Mở `ServerSocketChannel.open()` rồi `accept()` mà quên `bind()`, có tự lắng nghe port 0 không? **Không.** Channel chưa bound; có thể ném `NotYetBoundException`.

**Câu 2.** Gọi `server.configureBlocking(false)` rồi `accept()` khi chưa có client; kết quả là gì? **`null`**, không phải EOF hay lỗi.

**Câu 3.** Một listener non-blocking accept thành công; accepted channel sẽ ở mode nào? **Blocking**, ngay cả khi listener non-blocking.

**Câu 4.** `SocketChannel.read` vào buffer còn 1024 byte trả 3. Có mất 1021 byte không? **Không**: read được phép trả ít hơn yêu cầu; các byte còn lại có thể đến trong lần sau.

**Câu 5.** Khi `ByteBuffer` đã `put` 7 byte, gọi gì trước khi truyền cho `channel.write(buffer)`? **`flip()`** để đặt limit tại 7. Nếu buffer được trả về từ `StandardCharsets.UTF_8.encode`, nó đã sẵn sàng để viết nên không flip thừa.

**Câu 6.** Chuyển sang non-blocking, `read(dst)` trả 0. Có nên vòng lặp gọi lại liên tục không? **Không.** Giữ state và đợi readiness/`OP_READ`.

**Câu 7.** Vì sao không dùng `read` một lần để đọc một frame length-prefix 4 + 200 byte? **Vì TCP không giữ message boundary và một lần read có thể chỉ trả một phần**; phải đọc header đủ rồi body đủ.

**Câu 8.** Muốn một accepted channel đăng ký `OP_READ` với selector, cần làm gì? **`accepted.configureBlocking(false)`** trước khi register.

**Câu 9.** `shutdownOutput()` của client có ngăn client đọc response từ server không? **Không.** Nó chỉ half-close chiều gửi; chiều nhận vẫn hoạt động cho đến khi đóng/EOF/lỗi.

**Câu 10.** Trong khi thread A đang block ở `accept()`, thread B gọi `listener.close()` thì A có chắc tiếp tục chờ vô hạn không? **Không**; close có thể làm A nhận exception do đóng channel.

## 18. Checklist triển khai và kết luận

Khi thiết kế máy chủ dùng Java NIO, trả lời tuần tự:

1. **Channel nào lắng nghe, channel nào chở dữ liệu?** `ServerSocketChannel` nhận kết nối; mỗi `SocketChannel` mang một byte stream.
2. **Mode đang là gì?** Mặc định blocking; `isBlocking()` để kiểm tra, `configureBlocking(false)` nếu thực sự dùng selector.
3. **Đã bind/connect/accept đúng vòng đời?** Server bind trước accept; client connect hoàn chỉnh trước read/write.
4. **Đã xử lý `ByteBuffer` đúng `flip/clear/compact`?** Không parse byte ngoài `position..limit` hợp lệ.
5. **Đã xử lý read/write còn thiếu?** Đọc theo framing, không giả định một read đủ; khi chuyển non-blocking phải thiết kế lại xử lý `0`/readiness.
6. **Có điều kiện kết thúc request rõ ràng?** Length-prefix, delimiter hay EOF được giao thức quy định; không đoán theo số lượt read.
7. **Có policy cho timeout, EOF, interrupt, close và frame lỗi?** Không block vô hạn trong môi trường production.
8. **Ai sở hữu channel và buffer?** Bounded worker/queue, một writer theo connection khi cần, cleanup trong mọi đường lỗi.
9. **Nếu nhiều kết nối, có chọn được kiến trúc phù hợp không?** Blocking + bounded workers dễ hiểu cho quy mô nhỏ/vừa; non-blocking + selector hữu ích khi phải quản lý nhiều socket/idle connections, nhưng tăng độ phức tạp state machine.
10. **Có nhận thức về mức bảo đảm?** TCP có thứ tự byte nhưng không có ranh giới message, không chứng nhận nghiệp vụ sau write.

**Ghi nhớ:** *NIO là mô hình channel + buffer + khả năng multiplexing; “non-blocking” là một mode phải bật tường minh, không phải đặc tính mặc định*. Trên Java 17, `ServerSocketChannel.accept` và `SocketChannel.read/write` vẫn hoàn toàn có thể hoạt động theo lối blocking thông thường. Hiểu đúng hành vi ấy trước khi học `Selector` sẽ giúp tránh cả deadlock lẫn vòng lặp busy-spin.

### Tài liệu API chuẩn

- [Java SE 17 — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Java SE 17 — `SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 17 — `SelectableChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — `Selector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 17 — `InterruptibleChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html).