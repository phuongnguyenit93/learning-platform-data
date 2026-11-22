# Xử lý readiness như tín hiệu cần kiểm tra lại bằng thao tác I/O trong Java NIO Selector

**Chủ đề:** Java Advance - networking  
**Nhóm kiến thức:** Selector

Khi dùng **java.nio.channels.Selector** với **SocketChannel** hoặc **ServerSocketChannel** ở chế độ **non-blocking**, chương trình không đợi một thread riêng cho từng kết nối. Thay vào đó, một selector theo dõi những kênh và những thao tác mà ứng dụng quan tâm, rồi đánh thức vòng lặp khi có tín hiệu **readiness**.

Điểm mấu chốt: **readiness là tín hiệu nên thử thao tác I/O và kiểm tra kết quả thực tế; không phải lời cam kết thao tác đó chắc chắn truyền hoặc nhận được dữ liệu tại thời điểm bạn thực hiện**. Giữa lúc OS phát hiện trạng thái sẵn sàng và lúc Java gọi **accept()**, **finishConnect()**, **read()** hoặc **write()**, trạng thái có thể thay đổi. Tốc độ producer/consumer, nội dung buffer, peer đóng kết nối và các thao tác concurrent cũng ảnh hưởng đến kết quả.

Một thiết kế NIO đúng luôn đặt **giá trị trả về của lời gọi I/O** làm căn cứ cập nhật trạng thái, chứ không suy đoán từ **key.isReadable()**, **key.isWritable()** hoặc số key mà **select()** trả về. Đây là khác biệt quan trọng giữa event loop ổn định và các lỗi mất byte, mất message, busy-loop, read thừa hoặc close sai thời điểm.

## 1. Ba tầng trạng thái: interest, readiness và I/O thực tế

Với mỗi kênh đã đăng ký, Java trả một **SelectionKey**. Có ba khái niệm độc lập:

1. **Interest set**: ứng dụng đang muốn được thông báo về những thao tác nào, xem **key.interestOps()**. Ví dụ **OP_READ**, **OP_WRITE**, **OP_ACCEPT**, **OP_CONNECT**.
2. **Ready set**: selector đã quan sát thao tác nào sẵn sàng tại **lượt lựa chọn**, xem **key.readyOps()** hoặc **key.isReadable()**, **isWritable()**, **isAcceptable()**, **isConnectable()**.
3. **I/O thực tế**: câu trả lời từ **channel.read(...)**, **channel.write(...)**, **server.accept()** hoặc **channel.finishConnect()** khi code thực sự gọi chúng.

~~~text
Ứng dụng đăng ký: interestOps(OP_READ)
             │
             ▼
    Selector theo dõi kênh
             │
             ▼
      select() / selectNow()
             │
             ▼
    selectedKeys(), readyOps()
             │  (tín hiệu được quan sát ở thời điểm lựa chọn)
             ▼
     Kiểm tra key.isValid()
             │
             ▼
       Thử read(buffer)
          /     |      \
        > 0     0       -1
       có byte  chưa có  EOF: peer đóng chiều gửi
                tiến triển
             │
             ▼
   Cập nhật buffer, protocol state, interestOps
~~~

Chẳng hạn, **key.isReadable() == true** nghĩa là kênh đã được selector nhận diện là có một điều kiện đọc đáng quan tâm. Nó **không** bảo đảm **read()** sẽ trả số byte dương hoặc tạo thành một message hoàn chỉnh:

- **read() > 0**: thực sự đã đưa từng ấy byte vào **ByteBuffer**.
- **read() == 0**: không đọc được byte ở lần này; thường có thể xảy ra với non-blocking I/O hoặc khi buffer đích không còn chỗ.
- **read() == -1**: phía nhận đã tới **end-of-stream**; cần xử lý EOF/half-close theo giao thức, không được xem là “tạm thời chưa có byte”.

Tương tự, **key.isWritable()** không chứng minh một **write(ByteBuffer)** sẽ tiêu thụ hết buffer; có thể ghi một phần hoặc **0** byte. **isAcceptable()** không thay thế việc kiểm tra **ServerSocketChannel.accept()** có trả một **SocketChannel** thật hay **null**.

## 2. Readiness có giá trị gì nếu không bảo đảm tiến triển?

Readiness vẫn rất hữu ích: nó giúp ứng dụng **tránh thử I/O mù quáng trên hàng nghìn kênh**. Selector thường đánh thức khi có khả năng một thao tác đã đăng ký có thể thực hiện mà không phải chờ theo cách blocking. Nhờ đó, một thread event loop có thể tiến hành I/O cho nhiều kết nối.

Nhưng hãy xem readiness như một **gợi ý để thử**, không phải dữ kiện nghiệp vụ:

~~~text
Thời điểm T0: OS quan sát kênh có thể đọc.
Thời điểm T1: selector trả key có OP_READ.
Thời điểm T2: handler chuẩn bị đọc, có thể đã có:
  - một thread khác thao tác cùng channel,
  - người gửi đóng kết nối,
  - bộ đệm đích của ứng dụng hết chỗ,
  - trạng thái kênh bị cancel/close hoặc thay đổi.
Thời điểm T3: gọi channel.read(buffer).
Tại T3: chỉ return value / exception từ read mới xác định
        đã đọc bao nhiêu byte, EOF hay lỗi.
~~~

Không cần có một race hiếm gặp mới sai: ngay cả trên TCP loopback, **một lần read() không có ranh giới message**. Dữ liệu nhận có thể là **một phần**, **nhiều message dính nhau**, hoặc EOF. Nếu handler hiểu **readable = có đủ một request**, lỗi đã có thể xảy ra dù toàn bộ mã chạy trên một event-loop thread.

**Không gọi I/O theo kiểu blocking** sau khi nhận event chỉ vì key báo ready. Các **SocketChannel/ServerSocketChannel** đăng ký với Selector phải ở non-blocking mode; chính handler cũng cần duy trì mode đó và xử lý trường hợp “không tiến triển”.

## 3. Bảng quy tắc cho bốn operation của SelectionKey

| Cờ readiness | Kênh hợp lệ điển hình | Thao tác phải làm | Kết quả cần xét |
| --- | --- | --- | --- |
| **OP_ACCEPT** | **ServerSocketChannel** | **accept()** | Trả **SocketChannel** mới hoặc **null** nếu không có connection để lấy ngay |
| **OP_CONNECT** | **SocketChannel** đang kết nối non-blocking | **finishConnect()** | **true** nếu xong, **false** nếu chưa xong; hoặc exception nếu kết nối lỗi |
| **OP_READ** | **SocketChannel** | **read(ByteBuffer)** | **> 0** có byte; **0** chưa tiến triển; **-1** EOF; hoặc exception |
| **OP_WRITE** | **SocketChannel** | **write(ByteBuffer)** | Số byte thực sự đã lấy từ source buffer; có thể **0** hoặc nhỏ hơn số byte cần gửi |

Các cờ là **bitmask**; một key có thể báo nhiều thao tác ready trong một lần select, và một event cần cập nhật trạng thái/interest cho lượt tiếp theo. **Không** coi isReadable/isWritable là trạng thái tồn tại vĩnh viễn, và đừng giả định mỗi ready event tương ứng một packet hay một message.

**SelectionKey.isValid()** kiểm tra key chưa bị hủy; một key có thể bị **cancel()**, channel có thể bị đóng hoặc selector có thể bị đóng trong lúc xử lý. Trong môi trường có concurrency, trạng thái vẫn có thể đổi sau khi kiểm tra isValid; cần đóng/cleanup nhất quán khi I/O ném exception. **CancelledKeyException** có thể xảy ra khi truy cập thao tác key đã vô hiệu.

**Các cờ chỉ hợp lệ theo loại kênh.** Lấy **channel.validOps()** khi muốn kiểm tra một loại channel hỗ trợ đăng ký operation nào. Không bật OP_ACCEPT cho SocketChannel thông thường, hoặc OP_READ trên ServerSocketChannel.

## 4. Vòng lặp selector đúng: select, duyệt, xóa selected key, thử I/O

Khuôn mẫu cơ bản (pseudocode, chưa phải chương trình đầy đủ):

~~~java
try (Selector selector = Selector.open()) {
    // Đăng ký các channel non-blocking cùng interestOps phù hợp.

    while (running) {
        int n = selector.select(1_000);  // Tối đa khoảng 1 giây đợi sự kiện.
        if (n == 0) {
            // Timeout, wakeup hoặc tình huống không có key mới được chọn.
            // Vẫn kiểm tra shutdown/deadline/công việc đang chờ.
            continue;
        }

        Iterator<SelectionKey> iterator = selector.selectedKeys().iterator();
        while (iterator.hasNext()) {
            SelectionKey key = iterator.next();
            iterator.remove(); // Không để key cũ bám trong selected-key set.

            if (!key.isValid()) {
                continue;
            }

            // Với mỗi readiness bit phù hợp:
            // - gọi accept/finishConnect/read/write thực tế;
            // - kiểm tra return value/exception;
            // - cập nhật buffer, protocol state, interestOps;
            // - hủy key/đóng kênh nếu EOF hoặc lỗi.
        }
    }
}
~~~

Đoạn trên là **khung giải thích**, chưa khai báo **running**, không tạo channel và không thể dùng làm server hoàn chỉnh. Xem chương trình chạy được ở phần 9.

### Tại sao phải iterator.remove()?

**Selector.selectedKeys()** là tập key đã được chọn; các key **không tự biến mất chỉ vì handler đã đọc/ghi xong**. Vòng lặp thường chủ động **iterator.remove()** sau khi lấy key, trước khi xử lý. Nếu không, chương trình có thể xử lý lại key cũ ở các lượt tiếp, khiến trạng thái quan sát và thao tác I/O không khớp, tăng nguy cơ busy-loop hoặc xử lý lặp không mong muốn.

Không được dùng **selector.selectedKeys().clear()** một cách tùy tiện trong lúc vẫn đang dự định duyệt và xử lý các key. Dùng iterator giúp rõ ownership mỗi event và dễ xử lý lỗi trên từng key.

### select() trả bao nhiêu không phải số byte

- **select() / select(timeout)** trả thông tin về key có readiness được cập nhật, **không** trả số connection, byte hoặc message.
- **selectNow()** không chờ; có thể trả 0 khi chưa có trạng thái mới.
- **selector.wakeup()** có thể làm một lần select đang chờ trả về sớm. Một **select() == 0** không nhất thiết là lỗi.
- **select(0)** theo Java Selector API là chờ không giới hạn (không dùng như polling 0ms); muốn không chờ dùng **selectNow()**.
- Timeout của selector không tự hủy kết nối; cần deadline và state riêng cho connect, handshake, request hoặc idle timeout.

Cần **kiểm tra tiến triển thực** sau khi select trả về, kể cả khi key cho biết thao tác đã ready.

## 5. OP_ACCEPT: báo có thể accept, vẫn phải kiểm tra null

Với một **ServerSocketChannel**:

~~~java
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);

// Ở handler, khi key.isAcceptable():
SocketChannel peer;
while ((peer = server.accept()) != null) {
    peer.configureBlocking(false);
    peer.register(selector, SelectionKey.OP_READ, new ConnectionState());
}
~~~

Đoạn trên là **snippet**; **server**, **selector** và **ConnectionState** là những biến/lớp do ứng dụng phải tạo. **accept()** trên non-blocking ServerSocketChannel **có thể trả null**, nên không dereference hoặc đăng ký key nếu kết quả null.

Tại sao có thể null dù key vừa **isAcceptable() == true**?

- Readiness ghi nhận khả năng chấp nhận connection tại thời điểm lựa chọn.
- Một handler khác có thể đã chấp nhận connection trước khi handler này gọi accept.
- Trạng thái mạng/kênh có thể đổi.
- Lượt accept trước đó trong cùng vòng lặp đã lấy hết connection đang chờ.

Dùng **while (accept() != null)** giúp xử lý các connection đã sẵn có trong backlog cho tới khi không lấy được ngay nữa. **Không** busy-loop gọi accept khi trả null; quay lại vòng selector và đợi readiness tiếp.

**Sau accept:** SocketChannel mới nhận được từ non-blocking ServerSocketChannel thường cũng ở non-blocking mode theo API, nhưng có thể gọi **configureBlocking(false)** minh bạch. Mỗi connection phải có **state riêng**: inbound buffer, outbound buffer, parser/framer, deadline và lifecycle. Không xem một listener key là key dùng để read/write dữ liệu của connection.

## 6. OP_CONNECT: phải gọi finishConnect() và kiểm tra kết quả

Non-blocking connect có hai nhánh:

~~~java
// Snippet: remote là InetSocketAddress đã xác thực; selector đã mở.
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);

boolean connectedNow = channel.connect(remote);
if (connectedNow) {
    channel.register(selector, SelectionKey.OP_READ);
} else {
    channel.register(selector, SelectionKey.OP_CONNECT);
}

// Sau khi key.isConnectable():
boolean connected = channel.finishConnect();
if (connected) {
    key.interestOps(SelectionKey.OP_READ);
    // Chỉ bổ sung OP_WRITE nếu thực sự có output đang chờ.
} else {
    // Vẫn pending; giữ OP_CONNECT và thử lại khi được báo sẵn sàng.
}
~~~

Đây là **snippet minh họa**, không phải chương trình đầy đủ. Phải xử lý **IOException** và đóng channel nếu connect thất bại, và dùng application deadline cho kết nối quá lâu. Một lời gọi **connect(...)** non-blocking trả **false** không đồng nghĩa kết nối lỗi; nó báo tiến trình kết nối chưa hoàn tất.

**OP_CONNECT không có nghĩa đã kết nối thành công.** **finishConnect()** mới hoàn tất quy trình hoặc ném lỗi như **ConnectException**. Sau khi kết nối hoàn tất, nên bỏ **OP_CONNECT** khỏi interest set; nếu vẫn để cờ không cần thiết, state machine dễ bị gọi sai lần tiếp theo.

Không tự động bật **OP_WRITE** sau connect chỉ để “kiểm tra sẵn sàng”. Với một TCP channel đã kết nối, OP_WRITE thường rất dễ báo ready khi send buffer có chỗ, gây wakeup liên tục nếu chẳng có byte nào cần gửi.

## 7. OP_READ: xem xét ba trường hợp > 0, 0, -1

Handler phải sử dụng **giá trị read thực tế**, và phải có vùng đệm còn chỗ:

~~~java
// Snippet: key thuộc SocketChannel, inbound đang ở write mode.
int n = channel.read(inbound);

if (n > 0) {
    // Tăng bộ đếm byte/tiến trình parser.
    // Kiểm tra có đủ frame hoặc ký tự để xử lý hay chưa.
} else if (n == 0) {
    // Chưa tiến triển: giữ buffer/state và đợi readiness tiếp.
} else { // n == -1
    // Peer đã kết thúc chiều gửi; finalize frame hoặc báo truncated.
    // Close/cancel nếu protocol không hỗ trợ half-close.
}
~~~

**read() > 0** chỉ có nghĩa có **n byte**, không chứng minh một dòng text, một JSON document hoặc một frame đã hoàn chỉnh. Ví dụ protocol length-prefix 4 byte phải tiếp tục tích lũy cho tới khi đọc đủ 4 byte header, rồi đọc tiếp payload theo độ dài. Nếu buffer đầy, handler phải **flip, parse, compact** hoặc xử lý backpressure trước khi đọc thêm; đọc vào ByteBuffer không còn remaining có thể trả **0** dù key từng báo readable.

**read() == 0** với non-blocking channel có thể đến từ tình trạng chưa còn byte để đọc ngay, cạnh tranh trạng thái hoặc buffer không còn chỗ. Đừng biến n=0 thành EOF; đừng tạo vòng lặp **while (read(...) == 0) { }** vì như vậy một thread có thể tiêu CPU vô ích. Hãy để interest phù hợp và quay lại selector; nếu bộ đệm đích đầy, phải tiêu thụ/giải phóng chỗ hoặc tạm ngưng OP_READ có chủ đích, thay vì chờ dữ liệu thêm khi không có chỗ.

**read() == -1** là EOF của chiều nhận. Nếu protocol đã có toàn bộ request và cho phép half-close, server có thể vẫn cần gửi response; nếu request còn thiếu byte, phải xử lý truncated frame. Không coi EOF là “thông báo một frame mới”, cũng không gọi read thêm vô hạn.

### Readiness có thể báo khi peer đóng

Khi peer gửi FIN hoặc xảy ra tình huống lỗi, selector vẫn có thể đánh dấu kênh readable. Lúc đó **read()** trả **-1** hoặc ném **IOException**; readiness không đồng nghĩa “peer còn đang gửi dữ liệu có ích”.

### Nếu một event còn nhiều byte?

Với non-blocking read, có thể đọc nhiều lần trong **một lượt handler** miễn buffer có chỗ và có **giới hạn công việc** để không làm đói các connection khác. Một vòng lặp đọc có thể tiếp tục khi **n > 0**, dừng khi **n == 0**, xử lý EOF khi **n == -1**. Đừng đặt điều kiện “đọc được một lần là đã đủ message”. Trong demo sau, request cố định 4 byte để tập trung vào readiness; mỗi lượt read tiếp tục theo readiness cho đến khi đủ 4 byte.

## 8. OP_WRITE: tín hiệu có thể ghi không bảo đảm gửi hết

Trong non-blocking mode, **SocketChannel.write(ByteBuffer)** đọc một lượng byte từ **position** tới **limit** của buffer nguồn. Kết quả có thể là **0** hoặc một số dương nhỏ hơn **remaining()** ban đầu.

~~~java
// Snippet: pending đang ở read mode, còn byte cần gửi.
int n = channel.write(pending);

if (pending.hasRemaining()) {
    // Chưa gửi hết: giữ chính ByteBuffer này và OP_WRITE.
    // Không clear(), không compact() tùy tiện khi chưa quản lý phần còn lại.
} else {
    // Đã chuyển toàn bộ byte trong buffer cho channel tại phía Java.
    // Bỏ OP_WRITE nếu hiện không còn output đang chờ.
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
~~~

Đây chỉ là **snippet**, không bảo đảm những byte đã được peer nhận hoặc xử lý; write thành công thường mới thể hiện việc byte đã được tầng socket nhận để vận chuyển.

**Quy tắc xử lý partial write:**

1. Đặt **ByteBuffer** ở read mode bằng **flip()** sau khi mã hóa/điền dữ liệu.
2. Gọi **write()** khi có cơ hội ghi, rồi kiểm tra **pending.hasRemaining()**.
3. Nếu còn byte, **giữ nguyên position/limit và dữ liệu chưa gửi** cho lượt OP_WRITE sau. Nếu **n == 0**, tránh spin bằng cách quay về selector.
4. Nếu hết byte, **bỏ OP_WRITE** khi outbound queue không còn dữ liệu. Nếu còn nhiều buffer, chỉ chuyển sang buffer kế tiếp sau khi buffer hiện tại được xử lý đúng.
5. Nếu producer tạo output mới từ một thread khác, cập nhật queue/state an toàn và đánh thức selector khi cần (xem phần 11).

**Không đăng ký OP_WRITE mãi mãi cho tất cả client.** Kênh TCP thường writable khi send buffer có chỗ, khiến selector liên tục báo sự kiện mà handler không có byte để gửi. Đây là lỗi event-loop tiêu CPU rất phổ biến. Chỉ quan tâm OP_WRITE khi thực sự còn dữ liệu đang chờ hoặc có lý do cụ thể khác.

**Bộ đệm ứng dụng khác với kernel send buffer:** việc **pending.hasRemaining() == false** nghĩa là channel đã tiêu thụ số byte đó từ ByteBuffer của Java, không phải peer đã gửi application acknowledgment. Muốn xác nhận giao dịch, phải có response/ACK ở tầng protocol.

## 9. Chương trình Java 17+ đầy đủ: một selector, TCP loopback, đọc/ghi có kiểm tra tiến triển

Ví dụ chạy được dưới đây dùng một **ServerSocketChannel** non-blocking, đăng ký **OP_ACCEPT**, và một client blocking chỉ để tạo luồng PING/PONG trong cùng chương trình. Vòng lặp selector:

- Xóa từng key khỏi **selectedKeys** bằng **iterator.remove()**.
- Kiểm tra **key.isValid()** trước khi xử lý.
- Khi **isAcceptable()**, gọi **accept()** cho đến khi trả **null**, đăng ký **OP_READ** cho connection.
- Khi **isReadable()**, gọi **read(ByteBuffer)** và phân biệt **-1**, **0** và **> 0**; chỉ chuyển sang gửi response khi đã nhận đủ 4 byte.
- Khi **isWritable()**, gọi **write(ByteBuffer)** và chỉ kết thúc khi buffer không còn byte.
- Có deadline và timeout cho client để tránh mắc kẹt vô hạn trong demo.
- Output không phụ thuộc vào port ngẫu nhiên hay việc cố ý tạo zero-byte read: kết quả **0** hoặc **partial write** là nhánh code bảo vệ đúng, nhưng không bắt buộc xuất hiện trong một lần chạy trên loopback.

Tạo file **ReadinessRecheckDemo.java**:

~~~java
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ReadinessRecheckDemo {
    private static final class State {
        final ByteBuffer request = ByteBuffer.allocate(4);
        ByteBuffer response;
    }

    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.configureBlocking(false);
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            listener.register(selector, SelectionKey.OP_ACCEPT);
            InetSocketAddress endpoint =
                    (InetSocketAddress) listener.getLocalAddress();

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> client = executor.submit(() -> {
                    try (Socket socket = new Socket()) {
                        socket.connect(endpoint, 3_000);
                        socket.setSoTimeout(3_000);
                        socket.getOutputStream().write(
                                "PING".getBytes(StandardCharsets.US_ASCII));
                        byte[] response = new byte[4];
                        new DataInputStream(socket.getInputStream())
                                .readFully(response);
                        return new String(response, StandardCharsets.US_ASCII);
                    }
                });

                boolean completed = false;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (!completed && System.nanoTime() < deadline) {
                    if (selector.select(500) == 0) {
                        continue;
                    }

                    Iterator<SelectionKey> iterator =
                            selector.selectedKeys().iterator();

                    while (iterator.hasNext()) {
                        SelectionKey key = iterator.next();
                        iterator.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            ServerSocketChannel server =
                                    (ServerSocketChannel) key.channel();
                            SocketChannel peer;
                            while ((peer = server.accept()) != null) {
                                peer.configureBlocking(false);
                                peer.register(selector,
                                        SelectionKey.OP_READ, new State());
                            }
                            continue;
                        }

                        SocketChannel peer = (SocketChannel) key.channel();
                        State state = (State) key.attachment();

                        if (key.isReadable()) {
                            int n = peer.read(state.request);
                            if (n == -1) {
                                key.cancel();
                                peer.close();
                                throw new EOFException(
                                        "Peer closed before request finished");
                            }
                            if (n > 0 && !state.request.hasRemaining()) {
                                state.request.flip();
                                byte[] request = new byte[4];
                                state.request.get(request);
                                String value = new String(
                                        request, StandardCharsets.US_ASCII);
                                System.out.println("serverReceived=" + value);

                                state.response = ByteBuffer.wrap(
                                        "PONG".getBytes(StandardCharsets.US_ASCII));
                                key.interestOps(SelectionKey.OP_WRITE);
                            }
                            // n == 0: chưa tiến triển; giữ buffer và chờ.
                        }

                        if (key.isValid() && key.isWritable()
                                && state.response != null) {
                            int n = peer.write(state.response);
                            if (!state.response.hasRemaining()) {
                                key.cancel();
                                peer.close();
                                completed = true;
                            }
                            // Nếu n == 0 hoặc ghi một phần, giữ OP_WRITE.
                        }
                    }
                }

                if (!completed) {
                    throw new IOException("Selector demo timed out");
                }
                System.out.println("clientReceived=" +
                        client.get(3, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy với **Java 17 trở lên** (không cần internet):

~~~bash
javac --release 17 -encoding UTF-8 ReadinessRecheckDemo.java
java ReadinessRecheckDemo
~~~

**Stdout chính xác của lượt chạy thành công**, đã kiểm thử bằng JDK 24 với **javac --release 17**:

~~~text
serverReceived=PING
clientReceived=PONG
~~~

### Vì sao ví dụ minh họa được đúng vấn đề?

1. Listener **configureBlocking(false)** trước **register(selector, OP_ACCEPT)**. OS cấp port 0 trên loopback, client dùng endpoint đã bind thật.
2. **isAcceptable()** chỉ kích hoạt thử **server.accept()**; vòng while không giả định sẽ luôn nhận được một connection và dừng khi **accept() == null**.
3. Mỗi connection có một **State** gắn vào **SelectionKey**. **ByteBuffer request** chứa chỗ cho 4 byte; handler chỉ chuyển sang response khi đọc đủ **4 byte**, chứ không vì OP_READ báo ready.
4. **read() == -1** trước khi đủ request được coi là truncated request và ném **EOFException**. **read() == 0** không làm thay đổi state, không tự đóng connection.
5. Khi đủ request, handler **flip()** buffer, in **PING**, chuẩn bị response và đổi interest thành **OP_WRITE**. Điều này tránh ghi trước khi có output.
6. Với OP_WRITE, handler dùng **write()** và **hasRemaining()**. Ghi không hết sẽ giữ byte và interest cho lượt sau; chỉ đóng sau khi toàn bộ 4 byte response đã được channel nhận.
7. Client **DataInputStream.readFully(byte[4])** lấy đủ 4 byte **PONG**, tránh giả định một lần read lấy hết.
8. Demo làm việc trên 1 connection để tập trung nguyên tắc; trong server thật cần thay **completed** bằng event loop dài hạn, thêm resource limits, exception handling per-key, per-connection framing, close policy và shutdown quản lý.

**Điểm không được suy diễn:** Trong một lần chạy loopback, có thể không quan sát thấy read trả 0 hoặc write ghi một phần vì 4 byte rất nhỏ. **Sự đúng đắn nằm ở code đã chuẩn bị xử lý các kết quả hợp lệ ấy**, không nằm ở việc ép chúng xuất hiện. Để test các nhánh hiếm, dùng fake channel/test adapter, giới hạn send buffer, network simulation hoặc test có kiểm soát; đừng khẳng định sự kiện chỉ xảy ra vì thêm sleep.

## 10. Vì sao không dùng readiness làm điều kiện nghiệp vụ?

### Sai: thấy readable là coi như có request

~~~java
// Anti-pattern: bỏ qua return value và framing.
if (key.isReadable()) {
    channel.read(buffer);
    handleRequest(buffer); // Có thể chưa đủ request, hoặc read trả 0/-1.
}
~~~

Không chỉ thiếu xử lý **read() == 0/-1**; đoạn này còn không quản lý **flip()/compact()** và không xác định ranh giới request. Nó có thể parse byte rác, làm mất byte dư hoặc trả lời khi message chưa hoàn chỉnh.

**Đúng về nguyên tắc** là: đọc, kiểm tra **n**, cập nhật accumulator, tách các frame hoàn chỉnh, giữ phần còn lại, rồi quyết định output cần enqueue. Với giao thức length-prefixed hoặc delimiter, parser phải chịu được mọi cách chia mảnh.

### Sai: thấy writable là xóa cả outbound queue

~~~java
// Anti-pattern: write có thể ghi 0 hoặc một phần.
if (key.isWritable()) {
    channel.write(outgoing);
    outgoing.clear();  // Mất byte nếu outgoing.hasRemaining()!
}
~~~

**Đúng:** giữ nguyên buffer đến khi **hasRemaining() == false**. Chỉ clear để tái sử dụng sau khi đã gửi hoặc chuyển tất cả byte một cách có kiểm soát. Nếu output là queue nhiều buffer, tiến trình gửi phải giữ offset của phần còn lại.

### Sai: liên tục thử read/write khi trả 0

~~~java
// Anti-pattern: có thể quay CPU hết tốc độ.
while (channel.read(buffer) == 0) {
    // Không có tiến triển nhưng cũng không chờ readiness mới.
}
~~~

Đúng là quay lại selector hoặc event loop scheduling theo điều kiện; nếu buffer đầy, xử lý capacity/backpressure trước. Một callback nhận readiness không cấp quyền spin vô hạn cho tới khi đủ byte.

### Sai: giữ OP_WRITE cả khi không có dữ liệu

~~~java
// Anti-pattern nếu không thực sự có output.
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

Khi không có pending write, OP_WRITE thường liên tục ready. Thay vào đó, dùng:

~~~java
int ops = SelectionKey.OP_READ;
if (hasPendingOutput) {
    ops |= SelectionKey.OP_WRITE;
}
key.interestOps(ops);
~~~

Hai snippet trên cần biến **key** và **hasPendingOutput** do ứng dụng định nghĩa. **OP_READ** cũng nên được tạm ngưng khi inbound queue đã chạm giới hạn và consumer không thể xử lý tiếp; phải có đường kích hoạt lại sau khi giải phóng capacity.

### Sai: tin rằng một ready event chỉ ứng với một message

~~~text
TCP sender viết:     [frame A] [frame B]
SocketChannel.read:  [nửa A] [còn lại của A và toàn bộ B]

Hoặc:
TCP sender viết:     [frame A]
SocketChannel.read:  [A toàn bộ]
~~~

Selector không cung cấp framing. Một lần read có thể nhận chưa đủ, vừa đủ hoặc nhiều hơn dữ liệu của một frame. Parser phải theo dõi độ dài, delimiter, trạng thái decode và phần dư qua nhiều lần event.

## 11. Vòng đời key, cancellation và concurrency

**selectedKeys** không phải queue bất biến; trong lúc xử lý:

- **key.cancel()** đánh dấu key sẽ bị loại khỏi selector qua quy trình cancellation; **key.isValid()** không còn true.
- **channel.close()** khiến key tương ứng bị invalid/cancel; mọi read/write tiếp theo có thể ném exception.
- **IOException**, **ClosedChannelException**, **CancelledKeyException** cần được xử lý theo ownership của connection: đóng kênh, hủy key, giải phóng buffers/timer, cập nhật state và tránh làm chết toàn bộ server vì một client lỗi.
- Một key có thể có nhiều readiness bit hoặc attachment đã đổi state; hãy sử dụng trạng thái connection thực tại handler, không suy diễn chỉ từ ready set.

### Cập nhật interestOps từ thread khác

Ở hệ thống thực tế, worker thread có thể tạo response cho một connection trong khi selector thread đang chờ select. Một thiết kế thông dụng là:

1. Worker **enqueue** response vào outbound queue **thread-safe** của connection.
2. Worker enqueue một **lệnh cập nhật interestOps** tới hàng đợi task của event-loop thread.
3. Worker gọi **selector.wakeup()** để selector sớm xử lý task.
4. Event-loop thread lấy task, xác minh key còn valid, bật **OP_WRITE**, rồi thực hiện write theo readiness.

~~~text
Worker thread
  ├─ đưa response vào queue có đồng bộ
  ├─ đưa task "enable OP_WRITE" vào selector task queue
  └─ selector.wakeup()
                 │
                 ▼
Selector thread: select() trả về → xử lý tasks → tiếp tục select
                 └─ isWritable → thử write() → kiểm tra byte còn lại
~~~

Không nên để nhiều thread cùng đọc/ghi một **SocketChannel** và cùng thay đổi **position/limit** của một ByteBuffer mà không có quy tắc đồng bộ. Có thể gọi một số phương thức channel từ thread khác theo API, nhưng correctness của **state machine** vẫn là trách nhiệm ứng dụng.

**wakeup() không biến một channel thành writable**. Nó chỉ làm selector thoát chờ để xử lý công việc đang có; việc I/O tiếp theo vẫn phải dựa trên **read/write result**. Khi bắt buộc phối hợp interestOps từ thread khác, xác định rõ ai sở hữu key và tránh race giữa close, cancel, enqueue và enable OP_WRITE.

### Selector readiness và fairness

Một connection gửi rất nhiều dữ liệu có thể giữ handler chạy lâu nếu ứng dụng liên tục read/write cho đến hết. Dù mọi read đều tiến triển, một event loop có thể khiến các connection khác chờ. Đặt **work budget** theo số byte/đoạn thời gian mỗi lần handler, rồi quay lại selector để phân phối công việc. Đây là yếu tố **fairness**, không phủ nhận readiness là tín hiệu hữu ích.

## 12. Deadline, EOF và backpressure không được suy từ selector

Độ trễ có nhiều tầng, cần được quản lý riêng:

| Vấn đề | Không được suy ra từ readiness | Cách xử lý |
| --- | --- | --- |
| Connect mất quá lâu | **OP_CONNECT** không tự đặt timeout kết nối | Deadline cho state CONNECTING; đóng khi quá hạn |
| Request chưa đủ byte | **OP_READ** không nghĩa full message | Parser/frame accumulator + timeout/size limit |
| Không có byte mới | **select() == 0** không có nghĩa peer đã chết | Idle timer/heartbeat theo protocol |
| Sender bị nghẽn | **OP_WRITE** không nghĩa gửi hết queue | Partial-write state và backpressure |
| Peer đóng chiều gửi | Ready bit không phân biệt đầy đủ FIN với dữ liệu | **read() == -1** và protocol half-close |
| Chương trình đang shutdown | **isBound() / key.readyOps()** không nói service còn ready | Trạng thái lifecycle riêng, cancel/close có kiểm soát |

### Backpressure thực tế

Nếu peer đọc chậm, write trên non-blocking SocketChannel có thể trả 0. Outbound queue ở Java tiếp tục tăng nếu handler cứ nhận thêm message và tạo response. Cần **giới hạn tổng byte đang chờ** trên mỗi connection, có thể tạm ngưng OP_READ hoặc báo lỗi/quá tải khi vượt chính sách. Việc tăng buffer vô hạn chỉ chuyển vấn đề sang RAM/GC.

Ngược lại, khi parser/consumer chưa xử lý kịp inbound dữ liệu, không nên tiếp tục đọc vô hạn chỉ vì key readable. Tạm dừng interest **OP_READ** khi vượt watermark và kích hoạt lại khi queue giảm xuống mức an toàn. Mỗi thay đổi interest phải phản ánh tình trạng thật, tránh mất wakeup hoặc không còn thao tác nào được đăng ký.

### EOF và half-close

Với TCP, peer có thể **shutdownOutput()** làm phía nhận thấy EOF nhưng vẫn còn khả năng nhận response ở chiều ngược lại. Một server biết protocol half-close có thể chuyển state sang **SEND_RESPONSE** thay vì đóng cả socket ngay. Demo ở phần 9 cố ý xem EOF khi chưa đủ 4-byte request là lỗi, còn khi đã đủ request thì không cần read tiếp.

## 13. Các tình huống cần test để chứng minh event loop đúng

Thay vì chỉ test một đường chạy thành công, hãy mô phỏng các kết quả hợp lệ của thao tác I/O:

| Thao tác | Kịch bản kiểm thử | Kỳ vọng |
| --- | --- | --- |
| **accept()** | Có lúc trả **null** | Handler dừng thử và quay lại select, không tạo key từ null |
| **finishConnect()** | Trả false khi còn pending hoặc ném IOException | Giữ/đổi state hợp lệ; timeout/fail thì cleanup |
| **read() > 0** | Header/payload bị chia thành nhiều lần | Frame accumulator giữ đúng dữ liệu |
| **read() == 0** | Nonblocking chưa có byte hoặc dst hết remaining | Không đóng connection, không spin |
| **read() == -1** | EOF trước khi đủ frame | Phát hiện truncated frame, không parse như message đủ |
| **write() < remaining** | Chỉ chuyển một phần ByteBuffer | Giữ position và pending bytes, OP_WRITE tiếp tục |
| **write() == 0** | Send buffer tạm đầy | Không clear, không busy-loop |
| **OP_WRITE luôn ready** | Queue đã hết nhưng vẫn giữ OP_WRITE | Phải tắt OP_WRITE sau khi hết pending |
| **key bị cancel** | Close trong khi còn event chờ | Bỏ key invalid, cleanup không double-close logic |
| **selector.select() trả 0** | Timeout hoặc wakeup | Tiếp tục event loop và xử lý tasks/deadlines |

**Một số test nên dùng fake channel/adapter** hoặc test harness để ép các kết quả đặc biệt. Không nên dựa vào sleep hay cố làm mạng chậm rồi khẳng định sẽ tái tạo được một read()==0 sau OP_READ ở mọi OS/JDK.

### Bài tập thực hành

1. Đổi demo từ protocol 4-byte cố định sang **length-prefix** 4 byte (big endian) và body UTF-8. Gửi body thành nhiều chunk; chứng minh parser chỉ xử lý khi đã đủ byte, không dựa vào một lần isReadable.
2. Thêm outbound **ByteBuffer** lớn hơn send buffer. In số lần **write** và total bytes, bảo đảm buffer chỉ được giải phóng khi **!hasRemaining()** và client đọc đủ. Thử thay đổi độ trễ client đọc nhưng đừng dựa vào một số lần write cố định.
3. Viết client SocketChannel non-blocking dùng **OP_CONNECT**. Thử kết nối thành công và cổng không lắng nghe; xử lý **finishConnect()** trả true, false hoặc exception.
4. Thêm deadline cho việc chưa nhận đủ request, idle timeout và graceful shutdown; kiểm tra select() trả 0 không gây đóng nhầm một connection hợp lệ.
5. Cho worker thread tạo response sau khi handler read. Thiết kế task queue + **selector.wakeup()** và đảm bảo chỉ event-loop thread cập nhật interestOps.
6. Đặt watermark cho outbound queue; tạm dừng OP_READ khi queue quá lớn, bật lại khi đã drain. Giải thích tại sao chỉ giữ OP_WRITE liên tục không đủ bảo vệ RAM.

## 14. Lỗi phổ biến khi hiểu sai readiness

| Cách hiểu sai | Hậu quả | Quy tắc sửa |
| --- | --- | --- |
| “OP_READ nghĩa là có đủ request.” | Parse thiếu/nhầm frame | Xem **n** từ read, tích lũy và parse theo framing |
| “OP_WRITE nghĩa là có thể write hết buffer.” | Mất byte của partial write | Kiểm tra **hasRemaining()** và giữ ByteBuffer |
| “accept ready thì accept không thể null.” | NullPointerException hoặc handler sai | Kiểm tra kết quả, thử đến khi null |
| “OP_CONNECT nghĩa là connected.” | Dùng channel khi connection chưa hoàn thành | Gọi **finishConnect()** và xét return/exception |
| “read() == 0 tương đương EOF.” | Đóng connection hợp lệ | Chỉ **-1** là EOF trên SocketChannel |
| “select() == 0 nghĩa server chết.” | Dừng event loop sai | Xét timeout, wakeup, task/lifecycle riêng |
| “Đã handle key thì nó tự rời selectedKeys.” | Xử lý key cũ, event loop không ổn định | **iterator.remove()** cho mỗi key |
| “Giữ OP_WRITE mãi cũng không sao.” | Vòng lặp bận và CPU cao | Chỉ bật khi có byte cần gửi |
| “Key isValid lúc đầu thì mãi mãi valid.” | CancelledKeyException/closed channel | Kiểm tra trạng thái và cleanup theo event |
| “Tăng số thread sẽ sửa lỗi mất byte.” | Race lớn hơn, state lỗi vẫn còn | Sửa state machine, buffer và I/O return checks |
| “Một lần read trả trọn một TCP packet.” | Framing thiếu, đọc dính/tách message | TCP là byte stream, không có message boundary |
| “Sau write thành công chắc peer đã xử lý.” | ACK nghiệp vụ giả | Dùng application response và deadline |

## 15. Checklist triển khai Selector an toàn

- [ ] Kênh đã **configureBlocking(false)** trước khi register?
- [ ] InterestOps khớp **trạng thái hiện tại** của từng connection và **validOps()**?
- [ ] **select() == 0** được xử lý đúng, không bị xem thành I/O failure?
- [ ] Mỗi key được **iterator.remove()** khỏi selected set và **isValid()** được kiểm tra?
- [ ] Mỗi cờ ready dẫn tới một **thao tác I/O thực tế** hoặc quyết định state có lý do?
- [ ] **accept() == null** được chấp nhận bình thường?
- [ ] **finishConnect()** được gọi, xét true/false/IOException, có connect deadline?
- [ ] **read()** xử lý riêng >0, 0, -1 và buffer còn capacity?
- [ ] **write()** giữ byte chưa tiêu thụ khi partial/0, không clear quá sớm?
- [ ] **OP_WRITE** được gỡ khi hết output, và bật lại khi có output mới?
- [ ] Có message framing/parser độc lập với readiness?
- [ ] Có giới hạn queue, per-key workload, backpressure và timeout?
- [ ] Key cancel, channel close, EOF và exception có cleanup nhất quán?
- [ ] Nếu thread khác thêm tác vụ, có đồng bộ và **selector.wakeup()** khi phù hợp?
- [ ] Test có bao phủ trường hợp zero-progress, partial I/O và peer disconnect?

**Ghi nhớ cuối bài:** Selector giúp biết **kênh nào đáng thử I/O**, không thay thế **kết quả của I/O**. Coi **isAcceptable/isConnectable/isReadable/isWritable** như một **tín hiệu**; sau đó gọi **accept/finishConnect/read/write** và xử lý **null, false, 0, -1, partial result hoặc exception** theo một state machine rõ ràng. Chính sự tách bạch này làm chương trình NIO chịu được phân mảnh TCP, cạnh tranh trạng thái và tải thực tế.

**Tài liệu API chính thức để tra cứu:** [Selector (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html), [SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html), [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html), [ServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html) và [ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html).