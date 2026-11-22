# EOF, đóng kết nối và đóng một chiều trong Java NIO mạng

## 1. Vấn đề: hết dữ liệu hiện tại khác với kết thúc luồng

Trong mạng TCP, một kết nối truyền **hai luồng byte độc lập theo hướng**: client → server và server → client. Khi xử lý với `java.nio.channels.SocketChannel`, cần phân biệt ba trạng thái:

- **Chưa có byte nào để đọc ngay**: ở chế độ non-blocking, `read(ByteBuffer)` có thể trả `0`; kết nối vẫn có thể nhận dữ liệu trong tương lai.
- **Đầu bên kia đã kết thúc hướng gửi bình thường**: sau khi dữ liệu đang chờ được nhận hết, `read(ByteBuffer)` trả `-1`, nghĩa là *end of stream* (EOF) trên hướng nhận hiện tại.
- **Kết nối hoặc channel gặp lỗi/bị đóng**: lời gọi có thể ném `IOException` hoặc một ngoại lệ cụ thể; không được đánh đồng mọi lỗi này với EOF bình thường.

Java NIO cho phép đóng toàn bộ channel bằng `close()` hoặc đóng **một hướng** (*half-close*) bằng `shutdownOutput()` / `shutdownInput()`. Chọn sai API có thể làm server chờ mãi, làm client không nhận được phản hồi, hoặc cắt mất dữ liệu.

Các mục tiêu của bài: đọc đúng kết quả `-1/0/>0`, hiểu ý nghĩa của TCP FIN, phân biệt full close với half-close, viết giao thức request/response kết thúc bằng EOF an toàn, và xử lý vòng đời trong blocking/non-blocking I/O.

## 2. SocketChannel.read() trả về gì?

Với một `ByteBuffer` còn chỗ nhận dữ liệu:

~~~java
int n = channel.read(buffer);
~~~

Đây là một lời gọi minh họa; `channel` phải là `SocketChannel` đã kết nối, `buffer` là vùng đệm hợp lệ. Ý nghĩa kết quả:

| Kết quả | Ý nghĩa | Hành động thường phù hợp |
| --- | --- | --- |
| `n > 0` | Đã nhận `n` byte và `buffer.position()` tăng tương ứng | Xử lý bytes và tiếp tục theo giao thức |
| `n == 0` | Không chuyển byte trong lần gọi này | Ở non-blocking: đợi readiness tiếp theo; đừng coi là EOF |
| `n == -1` | Hướng nhận đã gặp **EOF**; không còn byte nào tiếp theo trong luồng đó | Xử lý khung cuối, hoàn tất đọc hoặc chuyển trạng thái giao thức |
| Ném `IOException` | Lỗi I/O, ngắt kết nối bất thường hoặc đóng đồng thời... | Xử lý lỗi theo loại và cleanup, không tự biến thành EOF |

**Buffer trống chỗ đọc cũng có thể khiến kết quả bằng 0:** nếu `buffer.remaining() == 0`, thao tác `read` không có nơi chứa byte. Vì thế phải bảo đảm buffer ở trạng thái nhận dữ liệu (thường sau `clear()` hoặc `compact()`). Một `read` trả 0 khi buffer đầy không nói điều gì về trạng thái TCP.

Ở chế độ **blocking**, với buffer có chỗ, `read` thông thường chờ có dữ liệu, EOF hoặc lỗi. Ở chế độ **non-blocking**, khi chưa có dữ liệu khả dụng, `read` có thể trả `0` ngay lập tức. Không viết vòng lặp `while (channel.read(buf) == 0) { }` để quay CPU liên tục; sử dụng `Selector` hoặc bộ điều phối phù hợp.

EOF là tín hiệu **theo hướng**. Khi server nhận `-1` từ client, điều đó nói rằng client không còn gửi thêm byte trên hướng client → server, **không** có nghĩa server đã mất quyền gửi dữ liệu phản hồi trên hướng server → client.

### EOF không phải một byte đặc biệt trong ByteBuffer

`-1` là **giá trị trả về của phương thức đọc**, không phải byte 0xFF nằm trong dữ liệu. TCP mang byte nhị phân tùy ý, kể cả `0xFF`, `0x00`, và chuỗi rỗng. Không tạo một byte “EOF” để chèn vào payload rồi mong `SocketChannel.read` tự nhận ra. Trong ứng dụng, EOF xảy ra do trạng thái kết thúc hướng gửi của kết nối.

## 3. TCP half-close: shutdownOutput() khác close()

Hãy hình dung kết nối hai chiều:

~~~text
Client                                   Server
   │ ---------- request bytes ----------> │
   │ ---------- FIN (write EOF) ---------> │
   │ <--------- response bytes ----------- │
   │ <--------- FIN (write EOF) ---------- │
   │                                       │
   └── close()                    close() ─┘
~~~

Sau khi client đã gửi đủ request, `client.shutdownOutput()` kết thúc **hướng ghi của client**. Với TCP bình thường, phía server sẽ đọc hết request rồi nhận `-1`; nhưng client vẫn có thể đọc response trên hướng ngược lại. Server có thể thực hiện tương tự sau khi gửi response.

So sánh:

| Phương thức | Hướng bị ảnh hưởng tại phía gọi | Sau đó còn làm được gì? |
| --- | --- | --- |
| `channel.shutdownOutput()` | Kết thúc **ghi** của chính channel | Vẫn có thể `read()` từ phía đối tác; `write()` tiếp sẽ ném `ClosedChannelException` |
| `channel.shutdownInput()` | Kết thúc **đọc** của chính channel | Các lần đọc tiếp trả `-1`; vẫn có thể `write()` nếu output chưa shutdown |
| `channel.close()` | Đóng toàn bộ channel và tài nguyên gắn với nó | Không tiếp tục đọc/ghi channel; `isOpen()` thành `false` |
| Đối tác gọi `shutdownOutput()` | Đối tác ngừng gửi vào hướng mình đang đọc | Sau khi bytes đang chờ hết, `read()` ở mình trả `-1`; có thể tiếp tục gửi ngược |
| Đối tác đóng kết nối bình thường | Có thể thấy EOF khi dữ liệu cũ đã đọc hết | Không giả định mình luôn gửi tiếp được; vòng đời đã kết thúc theo phía đối tác |

**Đặc điểm cốt lõi:** `shutdownOutput()` không đóng toàn bộ `SocketChannel`. Sau lời gọi thành công, `channel.isOpen()` vẫn có thể là `true`. Trạng thái “channel còn mở” không đồng nghĩa “cả hai chiều vẫn cho phép đọc/ghi”.

Gọi `shutdownOutput()` thêm lần nữa khi output đã shutdown không có tác dụng. Nhưng nếu channel đã đóng toàn bộ thì `shutdownOutput()` ném `ClosedChannelException`; nếu chưa kết nối, có thể ném `NotYetConnectedException`.

Cần phân biệt **thông báo kết thúc luồng** với **xác nhận nghiệp vụ**. TCP FIN theo sau những byte đã được bên gửi chuyển xuống ngăn xếp TCP theo thứ tự; nó không phải sự xác nhận rằng server đã xử lý, ghi database hoặc cam kết giao dịch thành công. Muốn xác nhận hoàn tất, giao thức ứng dụng cần phản hồi riêng.

## 4. Ví dụ Java 17+ hoàn chỉnh: gửi request, half-close, đọc response

Ví dụ mở `ServerSocketChannel` tại địa chỉ loopback với cổng động (port 0), nên không cần máy chủ bên ngoài và giảm khả năng đụng cổng. Client gửi `ping`, gọi `shutdownOutput()`, chờ server đọc tới EOF và phản hồi `pong`. Server cũng gọi `shutdownOutput()` để client nhận EOF của response.

Tạo file `HalfCloseDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class HalfCloseDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<?> task = executor.submit(() -> {
                    try (SocketChannel peer = listener.accept()) {
                        String request = readUntilEof(peer, "Server");
                        System.out.println("Server request: " + request);
                        writeAll(peer, "pong");
                        peer.shutdownOutput();
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                });

                try (SocketChannel client = SocketChannel.open()) {
                    client.connect(listener.getLocalAddress());
                    writeAll(client, "ping");
                    client.shutdownOutput();
                    String response = readUntilEof(client, "Client");
                    System.out.println("Client response: " + response);
                }
                task.get();
            } finally {
                executor.shutdownNow();
            }
        }
    }

    private static void writeAll(SocketChannel channel, String text)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(text.getBytes(StandardCharsets.UTF_8));
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    private static String readUntilEof(SocketChannel channel, String side)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(16);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        while (true) {
            int n = channel.read(buffer);
            if (n == -1) {
                System.out.println(side + " EOF: -1");
                break;
            }
            if (n == 0) {
                continue;
            }
            buffer.flip();
            byte[] part = new byte[buffer.remaining()];
            buffer.get(part);
            bytes.write(part);
            buffer.clear();
        }
        return bytes.toString(StandardCharsets.UTF_8);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac HalfCloseDemo.java
java HalfCloseDemo
~~~

Đầu ra chính xác đã được kiểm tra bằng cách biên dịch và chạy:

~~~text
Server EOF: -1
Server request: ping
Client EOF: -1
Client response: pong
~~~

**Giải thích vòng đời:**

1. Listener được bind vào loopback; `listener.getLocalAddress()` trả địa chỉ/cổng thực tế để client kết nối. Các `SocketChannel` mặc định ở chế độ blocking.
2. Một tác vụ trên thread riêng gọi `listener.accept()` để nhận socket server. `Future.get()` ở cuối giúp thread chính chờ server hoàn tất và truyền lỗi tác vụ server về thread chính.
3. Client gọi `writeAll` để bảo đảm `ByteBuffer` đã được channel tiêu thụ hết; `write` **có thể ghi ít hơn số byte còn lại** nên phải lặp cho đến khi `hasRemaining()` là false.
4. `client.shutdownOutput()` báo kết thúc hướng gửi. Server `readUntilEof` đọc tất cả byte; chỉ dừng khi `read` trả `-1`, sau đó in request `ping`.
5. Server vẫn có thể gọi `writeAll(peer, "pong")` dù hướng nhận của nó đã EOF. Đây chính là lợi ích của half-close. Sau khi gửi response, server `shutdownOutput()`.
6. Client nhận `pong` và tiếp tục đọc tới EOF ở chiều ngược. Cuối cùng `try-with-resources` đóng hai `SocketChannel` và listener.
7. Ví dụ chỉ minh họa giao thức **một request và một response, kết thúc bằng EOF**; không phải protocol dùng lại cùng kết nối cho nhiều lượt gọi.

`readUntilEof` gom byte rồi mới giải mã UTF-8. Làm vậy tránh tình huống một ký tự đa byte bị tách qua hai lần `read`. Với payload lớn, tránh gom tất cả vào bộ nhớ: giải mã UTF-8 theo luồng hoặc ghi trực tiếp ra tệp/consumer có giới hạn kích thước.

Vòng `n == 0` trong ví dụ không busy-spin trong tình huống bình thường vì channel đang ở chế độ blocking với buffer còn chỗ. **Không chuyển nguyên xi vòng lặp này sang non-blocking mode**; hãy dùng `Selector` và quản lý readiness.

## 5. shutdownInput(): dừng nhận tại phía cục bộ

`channel.shutdownInput()` dừng **hướng đọc của chính channel** mà không nhất thiết đóng hướng gửi. Theo API `SocketChannel`, sau khi shutdown input, các lần `read` tiếp theo trả `-1`. Nếu thread khác đang block trong `read` trên cùng channel, thao tác bị đánh thức và hoàn thành với kết quả `-1` theo hợp đồng của `SocketChannel`.

Ví dụ minh họa, khi `channel` đã kết nối:

~~~java
channel.shutdownInput();
int n = channel.read(ByteBuffer.allocate(8));
System.out.println(n); // -1
~~~

Đây chỉ là đoạn code minh họa cần đặt trong method và xử lý `IOException`.

Điều **không được hiểu nhầm**: gọi `shutdownInput()` ở client không phải lời nhắn “request của tôi đã gửi xong” tới server. Để bên server quan sát EOF của **luồng client gửi đi**, client dùng `shutdownOutput()`. `shutdownInput()` là thay đổi trạng thái đọc cục bộ; dữ liệu chưa đọc có thể bị bỏ đi theo cách của hệ thống, và ứng dụng không nên dùng nó để cố gắng “đọc hết rồi khôi phục” cùng hướng sau đó.

Nếu client cố tình từ chối đọc thêm response, việc đóng input khi server vẫn đang ghi có thể có hậu quả mạng khác tùy nền tảng. Đừng tự giả định server sẽ luôn được báo ngay hoặc việc ghi từ server được bảo đảm thành công.

## 6. Đóng toàn bộ channel: close() không phải half-close

`channel.close()` đóng tài nguyên channel. Trong code sử dụng `try-with-resources`, `close()` được gọi khi thoát khối dù có exception. Đóng hoàn toàn là lựa chọn đúng khi ứng dụng **không còn nhu cầu đọc hoặc ghi** trên kết nối.

~~~java
try (SocketChannel channel = SocketChannel.open(address)) {
    // Trao đổi request/response hoàn chỉnh theo giao thức.
} // close() tại đây
~~~

Đây là đoạn minh họa trong method có `address` hợp lệ và xử lý ngoại lệ. Thứ tự kết thúc thông thường:

1. Hoàn tất phần dữ liệu ứng dụng cần gửi; nếu protocol cần một marker kết thúc request theo hướng gửi, ghi marker/length hoặc gọi `shutdownOutput()` theo hợp đồng protocol.
2. Nếu còn cần response, tiếp tục đọc cho tới khi nhận đủ response theo protocol, có thể là số byte được khai báo hoặc EOF do server.
3. Chỉ khi không cần thêm dữ liệu, đóng toàn bộ channel bằng `close()`.

Nếu client `close()` **ngay sau ghi request** trong một protocol cần chờ response, client có thể mất cơ hội đọc response. Tùy trạng thái socket, hệ điều hành và dữ liệu còn tồn đọng, phía kia có thể thấy EOF hoặc lỗi reset; không nên cam kết “close sẽ luôn gửi FIN và mọi byte sẽ đến nơi”.

Một số ngoại lệ/hiện tượng khi đóng:

- Khi một thread đang chặn ở thao tác I/O và một thread khác đóng channel, thao tác có thể kết thúc bằng `AsynchronousCloseException`.
- Nếu thread đang block trong I/O bị interrupt, channel có thể đóng và báo `ClosedByInterruptException` theo hợp đồng `InterruptibleChannel`.
- Sau full close, `isOpen()` là `false`; các thao tác I/O không thể tiếp tục và thường báo `ClosedChannelException`.
- `shutdownOutput()` chỉ đóng hướng ghi: viết tiếp sau đó ném `ClosedChannelException` **ngay cả khi `isOpen()` còn true**.
- TCP reset từ peer có thể hiển thị như `SocketException`/`IOException` thay vì EOF; hãy log loại lỗi và trạng thái giao thức.

Khác với `SocketChannel` đã kết nối, `ServerSocketChannel` là **listener nhận kết nối**. Nó không có “hướng gửi request và hướng nhận response” trên một kết nối cụ thể; dùng `close()` để ngừng accept và giải phóng listener.

## 7. EOF trong blocking và non-blocking I/O

### 7.1. Vòng đọc blocking chuẩn

Với channel blocking và buffer được chuẩn bị đúng:

~~~java
ByteBuffer buf = ByteBuffer.allocate(4096);
while (true) {
    int n = channel.read(buf);
    if (n == -1) {
        break; // EOF: peer kết thúc hướng gửi.
    }
    if (n == 0) {
        continue; // Không coi là EOF.
    }
    buf.flip();
    // Tiêu thụ các byte trong [position, limit) của buf.
    buf.clear();
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Phải thay phần “tiêu thụ” bằng xử lý thực sự trước `clear()`. `clear()` chỉ đặt lại cursor, **không xóa dữ liệu**. Nếu decoder nhận chưa đủ một frame, cần `compact()` để giữ byte còn dở thay vì bỏ hết.

### 7.2. State machine với Selector

Trong non-blocking mode, một event `SelectionKey.OP_READ` có thể có nghĩa **có dữ liệu để đọc hoặc đã đến trạng thái EOF/lỗi**. Handler cần gọi `channel.read(...)` và phân nhánh theo giá trị, không xem readiness là bằng chứng luôn có `n > 0`.

Mẫu điều khiển khái niệm:

~~~java
if (key.isReadable()) {
    SocketChannel ch = (SocketChannel) key.channel();
    int n = ch.read(receiveBuffer);
    if (n > 0) {
        // Decode / tích lũy frame; chờ event kế tiếp nếu chưa đủ.
    } else if (n == 0) {
        // Chưa có byte: trở về selector, không busy-spin.
    } else { // n == -1
        key.interestOps(key.interestOps() & ~SelectionKey.OP_READ);
        // Đánh dấu input EOF; xử lý request cuối/response đang chờ.
        // Chỉ đóng channel nếu cả hai chiều đã hoàn tất.
    }
}
~~~

Đây là **mã minh họa trong event loop**, giả định `key` hợp lệ, `receiveBuffer` đã được chuẩn bị và các exception được xử lý bên ngoài. `SelectionKey` và `SocketChannel` có thể được import từ `java.nio.channels`.

Nếu sau EOF vẫn luôn để `OP_READ` và lập tức đọc lại mà không chuyển trạng thái, một số hệ thống sẽ tiếp tục báo channel ready liên tục, dẫn tới CPU cao. Cần **ngừng quan tâm đọc**, kết thúc xử lý hướng nhận hoặc đóng kết nối sau khi hướng gửi còn lại hoàn tất.

Với non-blocking `write`, `n == 0` cũng không phải lỗi hay “đã gửi hết”; thường phải giữ buffer còn `hasRemaining()` và đợi `OP_WRITE` khi có dữ liệu chờ. Không đăng ký `OP_WRITE` liên tục nếu không có bytes cần gửi vì socket có thể liên tục writable.

### 7.3. Parser phải phân biệt EOF với frame cuối

TCP là **byte stream**, không bảo toàn ranh giới từng lần `write` thành từng lần `read`. Một request `"hello"` có thể đến qua nhiều lần đọc; nhiều request có thể cùng nằm trong một lần đọc.

Khi EOF tới:

- Nếu protocol dựa trên “đọc đến khi bên gửi đóng hướng output”, EOF đánh dấu kết thúc payload hợp lệ.
- Nếu protocol dùng độ dài cố định/length-prefix và EOF tới khi còn thiếu byte, phải báo **truncated frame**, không nhận phần thiếu làm request hợp lệ.
- Nếu protocol có nhiều frame trên một kết nối lâu dài, EOF thường nói rằng phía kia đã kết thúc hướng gửi, **không** phân chia các frame trước đó; parser vẫn phải xử lý ranh giới theo protocol.
- Khi không có EOF hoặc delimiter/length-prefix, server không thể biết chắc request đã kết thúc chỉ vì một lần `read` trả `0` hoặc client tạm dừng gửi.

Đừng dùng `buffer.hasRemaining()`, `channel.isConnected()` hay `channel.isOpen()` như phép thử thay thế `read() == -1` cho việc peer đã gửi EOF.

## 8. Vì sao server hoặc client bị treo khi chờ EOF?

Ví dụ protocol kiểu “client gửi toàn bộ request, server đợi EOF rồi gửi response”. Nếu client làm như sau:

~~~text
Client: write(request) → read(response)
Server: readUntilEOF(request) → write(response)
~~~

cả hai có thể **chờ nhau vô hạn**:

- Client đang chờ response nên không kết thúc hướng gửi.
- Server đang chờ EOF của request nên chưa tạo response.

Sửa theo giao thức half-close:

~~~text
Client: write(request) → shutdownOutput() → read(response)
Server: readUntilEOF(request) → write(response) → shutdownOutput()
~~~

Một cách khác là thiết kế **framing không cần half-close**:

~~~text
[4 bytes length][N bytes request] → server biết đọc đúng N byte
[4 bytes length][M bytes response] → client biết đọc đúng M byte
~~~

Framing theo length giúp dùng lại kết nối cho nhiều request/response, pipelining hoặc multiplexing. Half-close phù hợp với các protocol có **một luồng dữ liệu kết thúc thật sự**, nơi không cần gửi thêm gì theo hướng đó. Nếu client cần gửi request thứ hai sau khi nhận response thứ nhất, **không** gọi `shutdownOutput()` sau request đầu trong cùng socket.

### Timeout và cancellation

Một client/server trong production không nên chờ vô hạn khi peer không gửi đủ frame hoặc không bao giờ half-close. Với `Selector` có thể quản lý deadline và hủy registration/đóng channel khi hết hạn; với blocking channel cần chính sách timeout/hủy phù hợp (thread interrupt, đóng channel được điều phối, hoặc cơ chế cấp cao hơn). Không tự giả định `Socket.setSoTimeout(...)` sẽ áp dụng đúng như một timeout cho mọi lời gọi `SocketChannel.read(...)`; chọn API timeout phù hợp với mode và cấu trúc ứng dụng thực tế.

## 9. Shutdown và race giữa các thread

Theo Java API, `SocketChannel` có thể được dùng bởi nhiều thread cho đọc và ghi đồng thời, nhưng **tối đa một thread đọc và một thread ghi tại một thời điểm**. Nếu thread A đang `read()` và thread B gọi `shutdownInput()`, lời gọi read đang bị chặn được hoàn thành với `-1`. Nếu thread A đang `write()` và B gọi `shutdownOutput()`, thao tác write đang bị chặn có thể kết thúc bằng `AsynchronousCloseException` theo hợp đồng.

Các API này quản lý vòng đời hướng truyền, **không** làm cho một `ByteBuffer` chia sẻ trở thành thread-safe. Nếu reader và writer cùng thao tác một buffer hoặc nhiều worker sửa `position/limit` của cùng buffer, vẫn phải phân quyền hoặc đồng bộ.

Khuyến nghị về ownership:

- Mỗi kết nối có một bộ điều phối vòng đời xác định trạng thái `OPEN`, `OUTPUT_SHUTDOWN`, `INPUT_EOF`, `FULLY_CLOSED` phù hợp; các trạng thái hướng gửi/nhận có thể kết hợp và xảy ra theo nhiều thứ tự.
- Chỉ gọi `shutdownOutput()` **sau khi tất cả byte cần gửi đã được chấp nhận bởi channel**; với non-blocking I/O phải giữ phần ghi còn lại, không lấy “đã gọi write một lần” làm hoàn tất.
- Các tác vụ đọc phải được thông báo khi output hay toàn connection sắp đóng nếu kết quả công việc phụ thuộc response.
- Chỉ `close()` khi không còn pending read/write quan trọng, hoặc cố ý hủy chúng và chấp nhận lỗi hủy.
- Sau khi nhận EOF, hướng nhận đã kết thúc; nếu ứng dụng vẫn cần gửi response, không tự động full-close ở event handler nhận EOF.

Hãy bảo đảm cleanup dùng `try-with-resources`, `finally` hoặc quản lý lifecycle tương đương. Khi hủy nhiều tác vụ async, tránh các lời gọi đóng kép và lối đi có thể bỏ sót giải phóng selector/key/channel.

## 10. EOF bình thường, reset, timeout và các ngoại lệ

| Quan sát | Không nên hiểu là | Cách xử lý gợi ý |
| --- | --- | --- |
| `read() == -1` | Không phải “chưa có dữ liệu” | Đánh dấu peer ngừng gửi ở hướng đó; xử lý kết thúc thông điệp |
| `read() == 0` | Không phải EOF | Xem buffer còn chỗ, mode blocking/non-blocking và chờ readiness |
| `ClosedChannelException` | Không phải bằng chứng chắc peer gửi FIN | Kiểm tra chính mình đã close/shutdownOutput hoặc code đóng đồng thời |
| `AsynchronousCloseException` | Không phải luôn là lỗi mạng | Xem thread khác đã đóng/shutdown trong lúc I/O bị chặn |
| `ClosedByInterruptException` | Không phải FIN từ phía đối tác | Kiểm tra chính sách interrupt/cancellation |
| `SocketException: Connection reset` (thông điệp tùy nền tảng) | Không phải EOF bình thường | Xử lý lỗi peer/mạng; không giả định payload đã hoàn tất |
| Đã `write()` hết buffer | Không chứng minh peer đã nhận và xử lý | Cần acknowledgment tầng ứng dụng nếu nghiệp vụ yêu cầu |
| `channel.isOpen() == true` | Không chứng minh cả hai chiều còn hoạt động | Theo dõi trạng thái input/output và protocol riêng |

Một connection reset (RST), mạng đứt, máy đối tác crash hoặc lỗi TLS có thể không cho EOF bình thường. Phân biệt graceful EOF và exceptional termination rất quan trọng khi cập nhật trạng thái nghiệp vụ: không đánh dấu “đã hoàn tất thành công” nếu payload chưa thỏa framing và checksum/application acknowledgment.

## 11. Ghi chú khi dùng TLS và giao thức tầng trên

Ví dụ trong bài là **TCP thuần**. Với TLS, ý nghĩa đóng ở tầng ứng dụng còn liên quan đến TLS `close_notify` và cơ chế của `SSLEngine`/thư viện TLS. Không tự coi TCP FIN là bằng chứng đã nhận một thông điệp TLS đóng hợp lệ. Việc đóng thiếu `close_notify` có thể là *truncation* đối với một số giao thức; mỗi ứng dụng phải tuân thủ contract của tầng mã hóa và protocol.

Tương tự, giao thức HTTP có length/chunked framing hoặc những quy tắc riêng về connection persistence; không thể quyết định “đã nhận đủ HTTP response” chỉ bằng việc chờ TCP EOF trong mọi trường hợp. Dùng parser/framing của giao thức thay vì giả định đóng kết nối sau mỗi message.

## 12. Lỗi phổ biến và cách tránh

1. **Coi `read() == 0` là đã đóng:** non-blocking 0 chỉ biểu thị chưa có byte trong lần đọc này, hoặc không có chỗ trong buffer.
2. **Bỏ qua `-1` rồi tiếp tục đăng ký `OP_READ`:** dễ tạo vòng lặp readiness/EOF và đốt CPU.
3. **Chờ EOF mà không `shutdownOutput()` khi protocol yêu cầu:** tạo deadlock client chờ response/server chờ request kết thúc.
4. **Gọi `close()` ngay sau khi gửi request cần response:** mất khả năng đọc chiều ngược.
5. **Gọi `shutdownInput()` để báo server đã gửi xong request:** sai chiều; phải dùng `shutdownOutput()`.
6. **Dùng `shutdownOutput()` rồi cố gửi thêm dữ liệu:** output đã shutdown, write tiếp ném `ClosedChannelException`.
7. **Giả định một `write` gửi đủ hoặc một `read` nhận đủ message:** TCP không giữ ranh giới thông điệp; cần vòng đọc/ghi và framing.
8. **Dùng half-close cho giao thức nhiều request trên cùng chiều:** một khi đã shutdown output, không thể mở lại chiều gửi đó trên cùng channel.
9. **Coi TCP EOF là thành công nghiệp vụ:** EOF chỉ nói rằng hướng gửi kết thúc theo quan sát mạng; cần xác thực payload và phản hồi ứng dụng.
10. **Không quản lý giới hạn kích thước/deadline:** peer có thể gửi quá lớn hoặc không bao giờ kết thúc; production cần giới hạn tài nguyên và timeout.

## 13. Câu hỏi tự kiểm tra

1. Trong non-blocking mode, `read(buffer) == 0` có chứng minh server đã đóng kết nối? **Không**, đây là lần gọi chưa nhận byte (hoặc buffer không còn chỗ), không phải EOF.
2. Client gửi request rồi gọi `shutdownOutput()`. Client có đọc response tiếp được không? **Có**, vì chỉ hướng ghi client bị đóng.
3. Server đọc được `-1`, nhưng vẫn phải trả một kết quả tính toán. Có được gọi `write()` không? **Có**, nếu hướng gửi của server vẫn mở và kết nối không bị đóng/lỗi.
4. Vì sao `shutdownInput()` không thay thế `shutdownOutput()` để thông báo EOF request cho server? Vì `shutdownInput()` dừng **hướng nhận cục bộ**, còn server đang chờ kết thúc **hướng gửi từ client**.
5. Sau `shutdownOutput()`, `isOpen()` có thể vẫn true nhưng `write()` hoạt động không? **Không**, viết tiếp ném `ClosedChannelException`.
6. Client và server cùng chờ `readUntilEOF()` mà không bên nào đóng hướng output: điều gì xảy ra? **Có thể chờ nhau vô hạn**, trừ khi giao thức hoặc một sự kiện hủy/timeout kết thúc tình huống.
7. EOF có luôn xảy ra khi cáp mạng đứt hoặc peer bị kill không? **Không**. Có thể timeout, reset hoặc `IOException`; cũng có thể không có tín hiệu tức thì.
8. Một lời gọi `SocketChannel.read()` trả 5 byte có nghĩa peer chỉ gửi một message dài 5 byte? **Không**. TCP là byte stream; 5 byte có thể là một phần message hay một phần của nhiều message.
9. Nếu server gửi response theo length-prefix, client nhất thiết phải chờ `-1` mới hoàn tất response không? **Không**. Có thể hoàn tất khi đã nhận đủ frame theo độ dài khai báo.
10. Khi dùng `Selector`, nhận `-1` có nên cứ giữ `OP_READ` và đọc lại vô hạn? **Không**. Cần chuyển trạng thái và hủy quan tâm đọc hoặc đóng khi thích hợp.

## Tài liệu API tham khảo

- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `read`, `write`, `shutdownInput`, `shutdownOutput`, đồng bộ khi dùng nhiều thread và kết nối.
- [Java SE 17 — ReadableByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html): ý nghĩa kết quả đọc `n > 0`, `0`, `-1`.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): bind, accept và đóng listener.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `OP_READ`, `OP_WRITE`, trạng thái selection.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `clear`, `compact` và thao tác buffer.
