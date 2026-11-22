# Tránh busy loop, nghẽn xử lý và dùng chung buffer sai cách với Java NIO Selector

## 1. Mục tiêu: event loop phải chờ đúng, xử lý nhanh và giữ dữ liệu đúng chủ sở hữu

`java.nio.channels.Selector` giúp một thread theo dõi nhiều channel không chặn (*non-blocking channel*) và xử lý khi chúng sẵn sàng đọc, ghi, chấp nhận kết nối hoặc hoàn tất kết nối. Hiệu quả của mô hình này phụ thuộc vào ba quyết định quan trọng:

1. **Không quay vòng vô ích (*busy loop*)**: không liên tục gọi `selectNow()` hoặc `read()`/`write()` khi không có tiến triển; không duy trì `OP_WRITE` khi không còn bytes cần gửi.
2. **Không để một kết nối làm nghẽn cả event loop**: một callback/block xử lý chậm, CPU-heavy hoặc gọi API blocking sẽ trì hoãn các channel còn lại.
3. **Không dùng chung buffer mutable sai cách**: `ByteBuffer` chứa cả dữ liệu lẫn `position`, `limit`, `mark`; dùng chung cùng một buffer giữa các kết nối hoặc các worker mà không có quy tắc ownership có thể tạo dữ liệu sai, mất byte hoặc lộ dữ liệu từ kết nối khác.

Một selector *không tự* điều phối công việc nghiệp vụ, backpressure, phân quyền buffer hay memory visibility. Nó chỉ cung cấp thông báo về các thao tác channel **có khả năng** tiến triển. Chương trình phải kết hợp selector, trạng thái kết nối và giao thức đóng/mở interest ops đúng cách.

## 2. Hiểu đúng Selector.select() và readiness

Một vòng lặp selector thông dụng:

~~~java
try (Selector selector = Selector.open()) {
    while (running) {
        selector.select(); // chờ readiness hoặc được đánh thức
        Iterator<SelectionKey> iterator = selector.selectedKeys().iterator();
        while (iterator.hasNext()) {
            SelectionKey key = iterator.next();
            iterator.remove();
            if (!key.isValid()) continue;
            // Kiểm tra key.isAcceptable()/isConnectable()/isReadable()/isWritable()
        }
    }
}
~~~

Đây là **khung minh họa** cần đặt trong chương trình có import, biến `running` và xử lý channel thực tế. Đừng dùng khung này như một server hoàn chỉnh: nó chưa đăng ký bất kỳ channel nào nên chưa làm việc hữu ích.

- `selector.select()` chặn cho tới khi có key sẵn sàng, bị `wakeup()`, thread bị interrupt hoặc điều kiện khác theo API. Nó **có thể trả 0**, vì thế không được giả định mọi lần thoát khỏi `select` đều có I/O để làm.
- `selector.select(timeout)` chờ nhiều nhất khoảng thời gian dương chỉ định; khi timeout có thể trả 0. Theo API, **timeout bằng 0 tương đương chờ vô hạn**, không phải polling tức thời.
- `selector.selectNow()` kiểm tra ngay, không chặn. Nếu gọi liên tục trong `while(true)` sẽ tạo polling tốn CPU khi không có dữ liệu.
- `key.readyOps()`/`key.isReadable()` biểu thị sự sẵn sàng do lần selection ghi nhận, **không** chứng minh một thao tác đơn lẻ chắc chắn chuyển byte. Cần kiểm tra `read`/`write` thực tế.
- `key.interestOps(...)` là tập sự kiện ứng dụng muốn theo dõi. Những bit `OP_READ`/`OP_WRITE` không phải lệnh đọc/ghi ngay; chúng quyết định sự kiện nào đánh thức event loop.
- `selector.selectedKeys()` là tập key đã được chọn. Phải xóa key khi xử lý, thường dùng `iterator.remove()`. Nếu để nguyên, cùng một key có thể bị xử lý đi xử lý lại dù không có sự kiện mới.
- Một key có thể sẵn sàng cho nhiều loại thao tác. Phải kiểm tra tính hợp lệ và trạng thái channel sau mỗi thao tác, vì một handler có thể đóng hoặc `cancel()` key.

Phân biệt rõ **selected-key set** (đã được chọn) với **registered-key set** (đã đăng ký). Xóa khỏi selected-key set không hủy đăng ký; `key.cancel()` mới hủy key và channel cần được đóng khi không dùng nữa.

## 3. Ba kiểu busy loop thường gặp

### 3.1. Polling vô hạn bằng selectNow()

**Sai:**

~~~java
while (running) {
    selector.selectNow();
    processReadyKeys(selector);
}
~~~

Đây là pseudocode Java (`processReadyKeys` là hàm do ứng dụng cung cấp). Khi không có readiness, vòng lặp không ngủ mà quay lại ngay, có thể làm một CPU core bận gần như liên tục.

**Tốt hơn:** dùng `select()` khi không có deadline, hoặc `select(timeout)` với một thời hạn thực sự cần thiết (ví dụ để xử lý scheduled task). Nếu có công việc nội bộ do thread khác gửi tới, phối hợp qua một hàng đợi và `selector.wakeup()` khi thêm công việc mới. Không dùng `Thread.sleep(1)` ngẫu nhiên để chữa một kiến trúc polling sai.

### 3.2. Vòng read()==0 và write()==0

Trong non-blocking mode:

~~~java
int count = channel.read(input);
if (count == 0) {
    // Chưa có byte khả dụng ngay; chờ selector.
}
if (count == -1) {
    // Peer đã kết thúc hướng gửi: chuyển trạng thái EOF hoặc đóng.
}
~~~

Đây là đoạn minh họa; `channel` và `input` phải tồn tại. `read()==0` không phải EOF. Nếu `input` không còn chỗ (`!input.hasRemaining()`), còn phải xử lý/compact buffer thay vì cứ đợi đọc tiếp.

Tương tự, non-blocking `write(output)` có thể tiêu thụ **một phần hoặc 0 byte** khi socket chưa đủ khả năng nhận dữ liệu. Nếu `output.hasRemaining()`, giữ nguyên buffer và đăng ký `OP_WRITE`; khi có sự kiện sẵn sàng ghi, thử viết tiếp. Không busy-spin:

~~~java
while (output.hasRemaining()) {
    channel.write(output); // SAI với non-blocking nếu write liên tục trả 0.
}
~~~

Ở blocking mode, việc chờ ghi tiếp có thể phù hợp với lời gọi chặn, nhưng code trên là lỗi phổ biến nếu `channel.configureBlocking(false)` và không có cơ chế chờ readiness.

### 3.3. OP_WRITE luôn bật dù không có dữ liệu gửi

Một socket thường xuyên có khả năng ghi thêm bytes. Nếu đăng ký `OP_WRITE` vô điều kiện:

~~~java
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

và tiếp tục giữ bit `OP_WRITE` ngay cả khi outbound queue trống, `select()` có thể trở về liên tục vì socket vẫn writable. Đây là lý do phổ biến khiến event loop ăn CPU dù hệ thống không có tải ứng dụng.

**Quy tắc:** chỉ đăng ký `OP_WRITE` **khi đã có dữ liệu đang chờ gửi**. Sau khi toàn bộ output được ghi hết, gỡ `OP_WRITE`:

~~~java
// Khi outbound vừa chuyển từ rỗng sang có dữ liệu:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Trong handler writable, sau khi ghi hết toàn bộ dữ liệu chờ:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
~~~

Đây là mã minh họa trong event loop, giả định `key` còn hợp lệ. Nếu channel chỉ phục vụ một request rồi kết thúc, đóng/cancel key khi đã flush thay cho việc giữ `OP_READ` không còn cần thiết. Nếu có nhiều frame outbound, chỉ gỡ `OP_WRITE` khi **toàn bộ queue outbound** đã rỗng, không chỉ một buffer vừa hết.

## 4. Ví dụ chạy được với Java 17+: một event loop, buffer riêng, OP_WRITE có điều kiện

Ví dụ sau có server ở loopback với `ServerSocketChannel` không chặn và một client độc lập dùng `SocketChannel` blocking. Client gửi đúng một request kết thúc bằng newline; server nhận request, chuyển sang chỉ quan tâm `OP_WRITE` khi có response, và đóng socket sau khi gửi hết. Mỗi socket server có một object `Connection` chứa `ByteBuffer`/state riêng trong `SelectionKey.attachment()`.

Tạo tệp **`SelectorSafeDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
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

public class SelectorSafeDemo {
    static final class Connection {
        final ByteBuffer input = ByteBuffer.allocate(128);
        final ByteArrayOutputStream request = new ByteArrayOutputStream();
        ByteBuffer output;
    }

    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            ExecutorService clients = Executors.newSingleThreadExecutor();
            try {
                Future<String> result = clients.submit(() -> {
                    try (SocketChannel channel = SocketChannel.open()) {
                        channel.connect(server.getLocalAddress());
                        ByteBuffer request = ByteBuffer.wrap(
                                "ping\n".getBytes(StandardCharsets.UTF_8));
                        while (request.hasRemaining()) channel.write(request);
                        channel.shutdownOutput();
                        ByteBuffer response = ByteBuffer.allocate(32);
                        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                        while (true) {
                            int n = channel.read(response);
                            if (n == -1) break;
                            response.flip();
                            while (response.hasRemaining()) bytes.write(response.get());
                            response.clear();
                        }
                        return bytes.toString(StandardCharsets.UTF_8).trim();
                    }
                });

                int completed = 0;
                while (completed < 1) {
                    if (selector.select(2000) == 0) {
                        throw new IOException("Timed out waiting for ready channels");
                    }
                    Iterator<SelectionKey> selected = selector.selectedKeys().iterator();
                    while (selected.hasNext()) {
                        SelectionKey key = selected.next();
                        selected.remove();
                        if (!key.isValid()) continue;
                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ, new Connection());
                            }
                        } else {
                            SocketChannel peer = (SocketChannel) key.channel();
                            Connection state = (Connection) key.attachment();
                            if (key.isReadable()) {
                                int n = peer.read(state.input);
                                if (n < 0) {
                                    throw new IOException("Request truncated before newline");
                                }
                                if (n > 0) {
                                    state.input.flip();
                                    while (state.input.hasRemaining()) {
                                        byte value = state.input.get();
                                        if (value == '\n') {
                                            System.out.println("Server received: " +
                                                    state.request.toString(StandardCharsets.UTF_8));
                                            state.output = ByteBuffer.wrap(
                                                    "PONG\n".getBytes(StandardCharsets.UTF_8));
                                            key.interestOps(SelectionKey.OP_WRITE);
                                            break;
                                        }
                                        state.request.write(value);
                                        if (state.request.size() > 64) {
                                            throw new IOException("Request too long");
                                        }
                                    }
                                    state.input.compact();
                                }
                            }
                            if (key.isValid() && key.isWritable()) {
                                peer.write(state.output);
                                if (!state.output.hasRemaining()) {
                                    key.cancel();
                                    peer.close();
                                    completed++;
                                }
                            }
                        }
                    }
                }
                System.out.println("Client received: " + result.get());
                System.out.println("Completed: " + completed);
            } finally {
                clients.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac SelectorSafeDemo.java
java SelectorSafeDemo
~~~

Kết quả **đã kiểm tra bằng cách biên dịch và chạy**:

~~~text
Server received: ping
Client received: PONG
Completed: 1
~~~

### Vì sao ví dụ tránh ba lỗi mục tiêu?

1. **Không busy loop:** server dùng `selector.select(2000)` và chỉ xử lý những key sẵn sàng; không gọi `selectNow()` không ngừng. Thời hạn 2 giây ở đây là *demo timeout*, không phải khuyến nghị cố định cho production.
2. **Không giữ `OP_WRITE` vô ích:** client mới kết nối chỉ có interest `OP_READ`. Khi gặp newline và đã tạo response, server đổi interest thành `OP_WRITE`. Sau khi bytes response được ghi hết, server đóng channel. Ở kết nối dài hạn, thay vì đóng sẽ gỡ bit `OP_WRITE` và giữ các interest thích hợp.
3. **Không chia sẻ buffer giữa các kết nối:** một lần `accept()` tạo một `Connection` riêng. `state.input` và `state.output` được dùng trong một event loop duy nhất, qua `key.attachment()`.
4. **Xử lý partial write:** `peer.write(state.output)` chỉ ghi những byte nó có thể nhận ngay. Nếu vẫn còn bytes, buffer giữ nguyên `position` và `OP_WRITE` vẫn bật để lần sẵn sàng tiếp theo viết nốt. Không gọi `clear()` trước khi gửi xong.
5. **Xử lý framing tối thiểu:** request kết thúc bằng newline, giới hạn nội dung 64 byte. Server không giả định một lần `read` luôn đúng một message. Nếu nhận EOF trước newline, báo truncated request.
6. **Selected key đã xử lý được loại khỏi selected set** bằng `selected.remove()`. Việc này khác với `key.cancel()`: hủy đăng ký chỉ diễn ra khi response đã hoàn tất và server chủ động đóng kết nối.

**Giới hạn có chủ đích của demo:** xử lý đúng **một request ASCII ngắn và một response** trên một kết nối, rồi dừng. Khi đã thấy newline, demo không giữ byte thừa để xử lý request tiếp theo; nó không phải bộ parser nhiều message. Client được chạy riêng và dùng blocking I/O để dễ quan sát; chỉ server mới dùng Selector. Mã production cần xử lý đóng tất cả accepted channel ngay cả khi lỗi/timeout, giới hạn số kết nối, bảo vệ queue, parse nhiều frame nếu cần, quản lý cancel, deadline và shutdown toàn server. Nếu sửa thành protocol lâu dài, cần có cấu trúc outbound queue thay vì chỉ một `state.output`.

## 5. Tại sao một handler chậm làm nghẽn tất cả kết nối?

Một event loop sử dụng **một thread** để xử lý nhiều key. Khi đang xử lý key A, thread đó chưa quay lại kiểm tra key B. Nếu code xử lý A làm một việc chặn, mọi kết nối khác cùng selector sẽ đợi, dù socket của chúng đã sẵn sàng.

Ví dụ hành vi nguy hiểm trong handler:

~~~java
if (key.isReadable()) {
    int n = socket.read(buffer);
    // Sau khi đọc, thực hiện xử lý CPU nặng 10 giây,
    // gọi JDBC đồng bộ hoặc yêu cầu HTTP blocking tại đây.
}
~~~

Đây là mã minh họa. Những việc dễ gây nghẽn bao gồm truy vấn DB đồng bộ, HTTP client blocking, `Thread.sleep()`, khóa mutex lâu, phân tích JSON khổng lồ, mã hóa dữ liệu nặng, ghi log xuống I/O chậm hoặc gọi một API bất đồng bộ rồi `future.get()` ngay trên event loop.

Hệ quả quan sát được:

- Latency tăng đồng loạt trên nhiều kết nối, dù mỗi client gửi rất ít dữ liệu.
- Read buffer không được drain kịp khiến kernel receive buffers tăng áp lực; sender có thể bị chậm do TCP flow control.
- Pending output không được flush khiến hàng đợi response tăng, thời gian sống kết nối và tài nguyên bị giữ lâu.
- Timer và timeout application layer có thể chạy muộn nếu chúng được xử lý trong chính thread bị nghẽn.
- Tăng số channel đăng ký lên cùng selector không làm event loop tự có thêm CPU.

**Định hướng xử lý:** event loop chỉ làm I/O non-blocking, parse frame gọn, cập nhật trạng thái nhỏ và lập lịch tác vụ. Các công việc CPU-heavy hoặc blocking được chuyển sang worker pool có giới hạn. Worker trả kết quả bằng một hàng đợi thread-safe; event loop nhận kết quả, tạo outbound buffers, bật `OP_WRITE` và tiếp tục. Không để worker trực tiếp thao tác đồng thời trên buffer mà event loop đang dùng.

## 6. Offload tác vụ nặng mà vẫn giữ ownership và ordering

Một mô hình an toàn có thể là:

~~~text
SocketChannel (non-blocking)
      │ OP_READ
      ▼
Selector thread ── decode frame / kiểm tra giới hạn
      │
      ├─ copy immutable input / chuyển giao sở hữu
      ▼
Bounded worker queue → Worker xử lý blocking/CPU-heavy
      │
      └─ immutable result / outbound bytes
                   ▼
          Thread-safe completion queue
                   │ selector.wakeup()
                   ▼
Selector thread → queue bytes → enable OP_WRITE → write partial → drain
~~~

Các nguyên tắc quan trọng:

- **Chỉ một chủ sở hữu thao tác cursor của read/write buffer tại mỗi thời điểm.** Event loop có thể chuyển một snapshot byte sang worker; sau khi chuyển ownership thật sự, nó không được `compact/clear/put` vào cùng buffer cho đến lúc worker trả.
- **Không gửi vào worker một tham chiếu `ByteBuffer` mutable rồi tái sử dụng ngay để đọc tiếp.** Worker có thể thấy `position/limit` thay đổi giữa xử lý; kết quả giải mã có thể sai hoặc gây `BufferUnderflowException`.
- **Hàng đợi bounded** giữ số tác vụ chờ có giới hạn. Nếu worker không theo kịp, giảm/tạm tắt `OP_READ` cho những connection cần throttling hoặc phản hồi quá tải theo policy. Không dùng queue vô hạn vì memory có thể tăng tới OOM.
- **Kết quả worker cần gắn với connection generation/id** và phải được bỏ qua nếu socket/key đã đóng hoặc request đã timeout. Tránh gửi response muộn lên channel mới tái sử dụng ID.
- **Giữ thứ tự response** nếu giao thức đòi hỏi: nhiều worker hoàn tất không theo thứ tự request. Dùng sequence number, queue theo connection, hoặc giới hạn một tác vụ đang chạy trên mỗi connection.
- **Giao thức đánh thức Selector:** thread khác có thể thêm kết quả vào completion queue và gọi `selector.wakeup()`. Khi `select()` trở về, event loop drain queue rồi cập nhật interest ops. Đừng dựa vào việc một writer ngoài thread gọi `key.interestOps(...)` mà event loop chắc chắn được đánh thức ngay.
- **Đừng gọi `Future.get()` trong event loop** để đợi worker: điều đó biến offload thành blocking, phá lợi ích của selector.

Ví dụ mô tả cách chuyển thông báo giữa worker và event loop, **không phải chương trình độc lập**:

~~~java
// Ở worker:
completedResults.add(new Result(connectionId, requestId, outputBytes));
selector.wakeup();

// Ở event loop, sau khi select() trở về:
Result done;
while ((done = completedResults.poll()) != null) {
    // Kiểm tra key còn hợp lệ và request còn cần kết quả.
    // Tạo ByteBuffer riêng từ outputBytes hoặc chuyển ownership rõ ràng.
    // Đưa vào outbound queue của chính connection.
    // Đăng ký OP_WRITE nếu queue vừa từ rỗng sang có dữ liệu.
}
~~~

`completedResults` phải là queue thread-safe, `Result` là kiểu do ứng dụng định nghĩa. Việc gọi `selector.wakeup()` **không chuyển dữ liệu thay queue** và không giúp một `ByteBuffer` chia sẻ tùy tiện trở thành an toàn đa luồng.

## 7. Không dùng chung ByteBuffer sai cách

`ByteBuffer` có hai loại trạng thái cần bảo vệ:

1. **Cursor metadata**: `position`, `limit`, `mark`. `get()`, `put()`, `flip()`, `clear()`, `compact()` có thể làm thay đổi chúng.
2. **Backing bytes**: mảng byte hoặc vùng direct/mapped memory. Hai buffer khác object cũng có thể dùng chung storage.

Một lỗi thường gặp:

~~~java
ByteBuffer sharedInput = ByteBuffer.allocate(8192);

// Trong mọi handler OP_READ cho nhiều socket:
int n = channel.read(sharedInput);
sharedInput.flip();
consume(sharedInput);
sharedInput.clear();
~~~

Đây là mã minh họa: `consume` do ứng dụng cung cấp. Khi nhiều connection dùng chung `sharedInput` và dữ liệu đến đan xen, rất dễ đọc byte của client A như byte của client B. Dù các handler chạy tuần tự trên một event loop, nếu parser cần giữ phần frame chưa đủ qua các lần đọc, việc `clear` buffer toàn cục giữa hai connection **làm mất trạng thái dang dở**. Dùng chung buffer còn trở nên nguy hiểm hơn khi offload vào worker.

### 7.1. Một connection, một inbound state và outbound queue

Trong chương trình lớn, có thể lưu trạng thái tại `SelectionKey.attachment()`:

~~~java
final class ConnectionState {
    final ByteBuffer input = ByteBuffer.allocate(8192);
    final Deque<ByteBuffer> outbound = new ArrayDeque<>();
    boolean inputEof;
    long queuedBytes;
}
~~~

Đây là **class minh họa**; cần import `ByteBuffer`, `Deque`, `ArrayDeque`. Nó phù hợp với event loop sở hữu độc quyền; **`ArrayDeque` không phải hàng đợi thread-safe**. Nếu worker có response, hãy post kết quả qua completion queue; event loop mới cập nhật `outbound` và `queuedBytes`.

Mỗi connection có parser state riêng: vùng dữ liệu chưa đủ một frame, chiều dài frame mong đợi, trạng thái đóng, watermark và deadline. Không được chỉ lưu một `ByteBuffer` dùng chung cho mọi connection rồi hy vọng Selector tự tách dữ liệu theo key.

### 7.2. duplicate(), slice() và asReadOnlyBuffer() không tự copy bytes

- `duplicate()` tạo view có con trỏ riêng nhưng **chia sẻ nội dung**.
- `slice()` tạo view cho một vùng còn lại hoặc vùng xác định nhưng **chia sẻ backing storage**.
- `asReadOnlyBuffer()` cấm ghi qua view đó, nhưng alias gốc vẫn có thể ghi vào vùng nhớ.
- `ByteBuffer.wrap(byteArray)` chia sẻ mảng với caller; caller giữ mảng có thể sửa nội dung ngoài buffer.
- `ByteBuffer.allocateDirect(...)` chỉ nói đến kiểu cấp phát, không bảo đảm thread safety.

**Ví dụ dễ nhầm:**

~~~java
ByteBuffer original = ByteBuffer.wrap(new byte[] {1, 2, 3});
ByteBuffer readOnly = original.asReadOnlyBuffer();
original.put(0, (byte) 9);
System.out.println(readOnly.get(0)); // 9
~~~

Đoạn trên có thể đặt trong một method và không cần concurrency để chứng minh rằng read-only view **không sở hữu bản sao immutable**. Nếu thread khác ghi đồng thời vào backing bytes trong khi reader đọc, phải có cơ chế đồng bộ hoặc ownership; nếu cả dữ liệu lẫn cursor hoàn toàn bất biến sau khi publish an toàn, nhiều reader có thể dùng view riêng.

### 7.3. flip()/compact() khi nhận frame chưa đầy

Khi đọc được một phần khung, không tự `clear()` để bỏ byte chưa tiêu thụ:

~~~java
int n = channel.read(input);
if (n > 0) {
    input.flip();
    decodeCompleteFrames(input);
    input.compact(); // giữ phần frame chưa hoàn chỉnh, dồn về đầu vùng ghi
}
~~~

Đây là đoạn minh họa; `decodeCompleteFrames` phải chỉ tăng `position` qua **frame hoàn chỉnh**, để lại byte thiếu trong `remaining()`. `compact()` sao chép byte còn lại về đầu và đặt position để lần đọc mới nối tiếp chúng. Nếu parser đã tiêu thụ toàn bộ dữ liệu, `clear()` là lựa chọn hợp lệ; nếu buffer đầy vì frame lớn hơn capacity, cần chính sách giới hạn, tăng buffer có kiểm soát hoặc streaming parser.

Trong non-blocking write, **không** `clear()`/`compact()` output trước khi `write` trả hết dữ liệu; phần còn lại trong buffer là chính xác những byte chưa được channel tiêu thụ.

## 8. Backpressure: nếu producer nhanh hơn socket

Giả sử worker tạo response 20 MB/s nhưng client chỉ nhận 1 MB/s. Nếu server cứ đưa response mới vào queue mà không giới hạn, pending bytes sẽ tăng dần cho tới khi dùng hết bộ nhớ. Selector chỉ báo khả năng ghi tạm thời; nó không tự giới hạn số bytes chờ trong chương trình.

Cần quy định:

| Tín hiệu | Biện pháp |
| --- | --- |
| Outbound queue vừa có bytes | Bật `OP_WRITE` cho connection |
| `write(...) > 0` nhưng còn bytes | Giữ buffer với position mới và tiếp tục ở sự kiện writable tới |
| `write(...) == 0` | Dừng lượt ghi; đợi `OP_WRITE`, không busy-spin |
| Outbound queue rỗng | Gỡ `OP_WRITE`; chỉ giữ interest còn cần |
| Queued bytes vượt **high watermark** | Tạm dừng nhận thêm công việc, giới hạn producer hoặc phản hồi quá tải |
| Queued bytes giảm xuống dưới **low watermark** | Khôi phục `OP_READ`/tiếp nhận công việc theo chính sách |
| Client không tiến triển vượt deadline | Hủy công việc, giải phóng queue/buffer và đóng connection phù hợp |

Hai watermark tránh bật/tắt liên tục khi queue dao động quanh một ngưỡng duy nhất. Khi tắt `OP_READ`, dữ liệu có thể vẫn được giữ trong kernel receive buffer và peer bị giảm tốc do TCP flow control; điều này không có nghĩa ứng dụng đã từ chối mọi dữ liệu mới trên mạng. Cần thêm giới hạn số connection, kích thước frame và thời gian chờ.

Một handler writable nhiều buffer nên giới hạn **write budget** mỗi vòng, ví dụ tối đa một lượng byte hoặc số buffer, để không chiếm hết event loop khi một client truyền dữ liệu liên tục. Sau khi dùng hết budget mà queue còn dữ liệu, để interest `OP_WRITE` bật cho lượt sau. Điều này hỗ trợ fairness.

## 9. Fairness và tránh “một key độc chiếm”

Ngay cả khi mọi channel không chặn, event loop vẫn có thể bị nghẽn nếu handler của một key:

- Đọc vô hạn cho đến khi `read() == 0` trên một connection luôn có dữ liệu.
- Giải mã hàng trăm nghìn frame trong một lượt selection.
- Gửi toàn bộ outbound queue lớn trong một lần xử lý key.
- Gọi xử lý CPU-heavy hoặc blocking I/O sau mỗi read.
- Giữ một monitor khóa lâu khiến event loop phải đợi thread khác.

Một chiến lược là đặt **budget mỗi key**: tối đa N lượt read, M frame decode hoặc X bytes write trên mỗi vòng. Khi hết budget, lưu state để tiếp tục ở vòng xử lý sau, không làm mất những byte đã đọc. Budget nên phối hợp với mức độ tải thật, fairness, deadlines và backpressure.

Không thể chỉ cắt vòng và quên dữ liệu đã có trong inbound buffer: phần frame đã hoàn chỉnh còn nằm trong bộ nhớ có thể sẽ **không** sinh thêm socket-readiness nếu kernel chưa có byte mới. Nếu đã ngừng xử lý khi còn nhiều frame nội bộ, cần lên lịch một lượt xử lý tiếp theo qua task queue của event loop, hoặc xử lý đến điểm an toàn trước khi kết thúc callback.

## 10. Lỗi EOF, cancel key và vòng đời connection

Trong `OP_READ` handler:

~~~java
int n = channel.read(input);
if (n == -1) {
    // Peer đã kết thúc hướng gửi.
    // Hoàn tất frame cuối hoặc báo truncated frame; quyết định có gửi response không.
}
~~~

`-1` nghĩa là EOF **hướng nhận**, khác với `0` khi chưa có byte. Không giữ `OP_READ` vô hạn và tiếp tục đọc `-1` mà không đổi trạng thái; tùy nền tảng có thể gây readiness loop. Nếu còn response cần gửi sau khi peer half-close, gỡ `OP_READ` và giữ `OP_WRITE` tới khi flush xong. Khi không còn dữ liệu cần trao đổi, đóng channel và hủy key.

Cần xử lý cả:

- `IOException` khi peer reset hoặc network lỗi.
- `ClosedChannelException` nếu channel đóng khi đăng ký hoặc thao tác.
- `CancelledKeyException` nếu key đã cancel rồi vẫn gọi `isReadable/interestOps`.
- `ClosedSelectorException` khi selector bị đóng trong lúc vòng lặp vẫn dùng.
- Connection non-blocking đang connect: `OP_CONNECT` và `finishConnect()` cần được xử lý đúng trước read/write.
- Listener accept: `ServerSocketChannel.accept()` trong non-blocking mode có thể trả `null` ngay cả khi có sự kiện `OP_ACCEPT`; không dereference null.
- EOF/truncated frame: parser phải biết framing của protocol; TCP không giữ ranh giới giữa các lần `write`/`read`.

Với mỗi lỗi, cleanup cần gỡ connection khỏi registry, hủy key, đóng channel và giải phóng các buffer/reference/pending task. Nếu đã offload worker, kết quả hoàn thành muộn phải bị bỏ khi connection không còn hợp lệ.

Không dùng `selector.keys().clear()` hay chỉ `iterator.remove()` để giả định đã đóng socket. Hủy key và đóng channel là thao tác riêng; resource cleanup phải có owner rõ ràng.

## 11. Đọc hiện tượng CPU cao và xử lý sự cố

Nếu process Java dùng nhiều CPU nhưng lưu lượng mạng thấp, kiểm tra trước:

1. Vòng event loop dùng `selectNow()` liên tục hay `select(positiveTimeout)` cực nhỏ không cần thiết?
2. `OP_WRITE` có luôn bật dù outbound queue rỗng?
3. Handler có quên `selectedIterator.remove()` khiến key được xử lý lặp?
4. Sau EOF, có tiếp tục quan tâm `OP_READ`/đọc lại `-1` không?
5. Các lần `read/write` trả 0 có tạo retry trong vòng `while` không?
6. Có exception được bắt rồi bỏ qua, dẫn đến cùng lỗi lặp mãi mà không đóng key/channel không?
7. Có logic `selector.wakeup()` gọi quá thường xuyên từ worker mà không có kết quả mới không?
8. Có lượng dữ liệu lớn ở parser/outbound làm event loop không tới lượt các kết nối còn lại không?

Nếu latency cao nhưng CPU không nhất thiết tăng, kiểm tra tác vụ blocking trong handler, worker pool quá tải, lock contention, outbound queue tích tụ, connection count và thời gian xử lý mỗi vòng selection.

Các chỉ số hữu ích: số channel đăng ký, số selected key theo operation, số lần `select()` trả 0, thời gian mỗi callback, pending bytes theo connection, outbound high-watermark events, worker queue depth, thời gian I/O không tiến triển và số kết nối đóng do timeout.

Những chỉ số này là gợi ý quan sát; chúng không thuộc bản thân API `Selector`. Ứng dụng cần tự ghi metric hoặc dùng profiler/thống kê JVM phù hợp.

## 12. Quy tắc thiết kế tổng hợp

| Nhu cầu | Cách làm phù hợp | Sai lầm cần tránh |
| --- | --- | --- |
| Chờ I/O nhiều socket | `Selector.select()` với channel non-blocking | Polling `selectNow()` vô hạn |
| Không có outbound bytes | Chỉ giữ `OP_READ` (hoặc interest khác cần thiết) | Luôn bật `OP_WRITE` |
| Có bytes chưa ghi hết | Giữ per-connection buffer, để `OP_WRITE` bật | Busy-spin khi write trả 0; clear output quá sớm |
| Nhận frame từng phần | Per-connection input/decoder state, `compact()` đúng lúc | Một buffer toàn cục cho mọi connection |
| Task CPU/DB blocking | Offload vào bounded worker pool | `Future.get()` trong event loop |
| Nhận kết quả worker | Queue thread-safe + `selector.wakeup()` + owner event loop cập nhật interest | Worker mutate cùng ByteBuffer/SelectionKey state thiếu giao thức |
| Tốc độ sinh > tốc độ gửi | Backpressure, watermark, deadline | Outbound queue không giới hạn |
| Connection liên tục có dữ liệu | Budget read/write/parse mỗi lượt | Để một key chiếm event loop vô hạn |
| EOF hoặc lỗi | Cập nhật state, hủy interest, đóng khi đúng lúc | Lặp đọc -1 hoặc bỏ sót cleanup |

Một sơ đồ trách nhiệm dễ kiểm chứng: **event loop sở hữu selector, selection keys và buffer trạng thái I/O; worker xử lý bản dữ liệu đã chuyển giao an toàn; kết quả quay về qua queue thread-safe; event loop tự cập nhật interest ops và thực hiện I/O**. Có thể dùng thiết kế khác, nhưng phải chứng minh được ownership, visibility và giới hạn tài nguyên tương đương.

## 13. Câu hỏi tự kiểm tra

1. `selectNow()` trả 0 liên tục, vòng `while(true)` gọi lại ngay. Hậu quả là gì? **Busy loop**, có thể dùng CPU cao mà không xử lý dữ liệu.
2. `select(0)` có tương đương `selectNow()` không? **Không**; timeout 0 của `select(long)` tương đương chờ không giới hạn, còn `selectNow()` không chặn.
3. Vì sao `OP_WRITE` có thể tạo CPU cao khi output queue rỗng? Vì socket thường xuyên writable, nên selector liên tục chọn key mà handler không có bytes để gửi.
4. `SocketChannel.write(buffer)` trả 0 có nghĩa channel đã đóng không? **Không**; ở non-blocking mode thường là tạm thời không ghi được ngay. Giữ buffer, đợi readiness.
5. Hai kết nối cùng dùng một `ByteBuffer` nhưng chỉ có một event-loop thread, có chắc an toàn không? **Không**: frame chưa hoàn chỉnh và `position/limit` của connection này có thể bị thao tác connection kia ghi đè/làm mất.
6. Dùng `duplicate()` hoặc `asReadOnlyBuffer()` có tạo vùng dữ liệu độc lập không? **Không**; chúng vẫn chia sẻ backing bytes với các alias.
7. Vì sao chuyển JDBC blocking sang worker rồi ngay lập tức gọi `future.get()` trong event loop vẫn chậm? Vì event-loop thread vẫn bị chặn chờ kết quả.
8. Khi worker tạo response, nó có nên trực tiếp `put()` vào outbound buffer mà event loop đang `write()` không? **Không**, trừ khi thiết kế có giao thức ownership/đồng bộ được chứng minh an toàn.
9. Đã gửi hết một buffer nhưng outbound queue còn buffer khác, có gỡ `OP_WRITE` không? **Chưa**; chỉ gỡ khi không còn pending bytes.
10. `read() == -1` rồi vẫn giữ `OP_READ` để đọc lại mãi có ổn không? **Không**; đó là EOF hướng nhận, phải đổi trạng thái/interest hoặc đóng khi giao thức hoàn tất.
11. Tại sao queue worker và output cần bounded? Vì producer nhanh hơn consumer nếu không giới hạn sẽ làm tăng memory không kiểm soát.
12. Có thể giới hạn read budget rồi bỏ qua các frame đã có sẵn trong input buffer không? **Không**; phải lưu parser state và lên lịch tiếp tục xử lý để không bỏ sót frame.

## Tài liệu tham khảo

- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select()`, `selectNow()`, timeout, selected keys, `wakeup()` và yêu cầu đồng bộ.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready operations, attachment, cancel.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking read/write, connect, EOF.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): con trỏ, `flip`, `compact`, view chia sẻ backing storage.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): accept không chặn, cấu hình channel.
