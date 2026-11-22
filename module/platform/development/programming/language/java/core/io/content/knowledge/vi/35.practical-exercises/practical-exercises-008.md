# Thực hành Java NIO: xây dựng vòng Selector cho giao tiếp TCP đơn giản

Mục tiêu của bài thực hành là **tạo một TCP echo server sử dụng `Selector`**, không dùng một thread riêng cho từng kết nối. Máy chủ lắng nghe TCP bằng `ServerSocketChannel`; mỗi client được đại diện bởi một `SocketChannel` ở chế độ non-blocking. Một **event-loop thread** gọi `selector.select()` để lần lượt xử lý `OP_ACCEPT`, `OP_READ` và `OP_WRITE`. Khi đọc được một dòng kết thúc bằng `\n`, máy chủ trả về dòng `echo:<nội dung>\n`.

Phần thực hành dùng **Java 17+**, chạy hoàn toàn trên địa chỉ loopback, tự chọn cổng trống, có một TCP client nhỏ ngay trong chương trình để kiểm tra đường đi của dữ liệu. Code minh họa có chủ đích **xử lý một request rồi dừng** để người học thấy rõ vòng đời của selector, socket, key và buffer; các phần mở rộng sau đó giải thích cách chuyển thành server nhiều client phục vụ lâu dài.

Điều cần nhớ trước khi bắt đầu: **readiness không phải completion**. `OP_READ` không đảm bảo đủ một dòng; `OP_WRITE` không đảm bảo gửi hết response. Chúng ta phải giữ trạng thái trên từng kết nối, kiểm tra số byte thực sự chuyển, cập nhật `interestOps` và dọn resource đúng thời điểm.

## 1. Mục tiêu học tập và kết quả cần đạt

Sau bài này, bạn có thể:

1. Mở `Selector`, `ServerSocketChannel`, bind TCP loopback và đăng ký `OP_ACCEPT`.
2. Chấp nhận kết nối bằng `accept()`, đặt `SocketChannel.configureBlocking(false)` rồi đăng ký `OP_READ`.
3. Viết vòng event loop `select() → selectedKeys() → iterator.remove() → handle event`.
4. Lưu `ByteBuffer`, dữ liệu đọc dở và buffer ghi chờ trong `SelectionKey.attachment()`.
5. Tích lũy bytes cho đến delimiter `\n`; không nhầm một TCP `read` với một message.
6. Bật `OP_WRITE` khi thực sự có response; giữ buffer với `hasRemaining()` và tắt quan tâm write khi hết dữ liệu.
7. Xử lý `read()==0`, `read()==-1`, `accept()==null`, `IOException`, key invalid và đóng channel.
8. Chạy test end-to-end qua loopback, kiểm tra stdout và sửa lỗi thường gặp.
9. Phân biệt mô hình server một vòng selector với một thread-per-connection, và xác định giới hạn của ví dụ.

**Đầu ra mong đợi:** chương trình in `reply=echo:ping`, chứng minh ít nhất hai lượt đọc và ba lượt ghi nhờ buffer nhỏ có chủ ý, và xác nhận `roundtrip=true`.

## 2. Chuẩn bị môi trường

Yêu cầu:

- JDK **17 trở lên**, với `java.nio.channels` và `java.net` của Java SE.
- Terminal có lệnh `javac` và `java` trên `PATH`, có quyền mở kết nối loopback nội bộ.
- Không cần thư viện bên ngoài, Maven, Gradle hay cơ sở dữ liệu.
- File nguồn nên được lưu dưới UTF-8; tên file trùng với public class `SelectorTcpEchoDemo.java`.

Kiểm tra:

```bash
java -version
javac -version
```

Các lệnh trên là lệnh môi trường; phiên bản in ra phụ thuộc JDK bạn cài. Với máy không cho phép loopback hoặc bị chặn bởi policy bảo mật, chương trình có thể ném `IOException`, không phải lỗi của API Selector.

Để tránh xung đột cổng, chương trình **bind cổng 0**. Hệ điều hành sẽ cấp một cổng TCP khả dụng. Client lấy địa chỉ thật qua `listener.getLocalAddress()`, nên không cần ghi cứng số cổng 8080 và không cần mở port trên mạng công cộng.

## 3. Bức tranh kiến trúc

```text
                  Java process: hai luồng trong bản demo
┌──────────────────────────────────────────────────────────────┐
│ Main thread (client thử nghiệm)                               │
│                                                              │
│   Socket.connect(loopback, ephemeralPort)                     │
│        │                                                     │
│        ├── send bytes: "ping\n" ────────────────┐            │
│        │                                         │            │
│        └── read response until server closes ◄──┼──────┐     │
│                                                  │      │     │
│ Event-loop thread                                ▼      │     │
│   Selector.select(3000)                          │      │     │
│        │                                         │      │     │
│        ├── OP_ACCEPT → ServerSocketChannel.accept()     │     │
│        │                  └── register peer: OP_READ    │     │
│        ├── OP_READ → SocketChannel.read(ByteBuffer)     │     │
│        │              → accumulate until newline       │     │
│        │              → set OP_WRITE                    │     │
│        └── OP_WRITE → SocketChannel.write(reply) ──────┘     │
│                       → repeat until !hasRemaining()         │
│                       → close peer, exit loop                 │
└──────────────────────────────────────────────────────────────┘
```

**Phân biệt số luồng:** chương trình hoàn chỉnh có một *main thread* làm TCP client kiểm thử và một *event-loop thread* làm server. **Phía server không tạo một thread cho mỗi client**. Nó sử dụng đúng một selector để quan sát các channel đã đăng ký. Không nên mô tả demo này là “toàn chương trình chỉ có một thread”.

**Phân biệt handle:**

| Thành phần | Thực hiện việc gì? | Trạng thái quan trọng |
| --- | --- | --- |
| `ServerSocketChannel` | Bind và chấp nhận TCP clients. | `OP_ACCEPT`; socket server không trực tiếp đọc payload client. |
| `SocketChannel` | Kết nối TCP đã được accept; đọc/ghi bytes. | `OP_READ`, `OP_WRITE`; `ByteBuffer` ứng với client. |
| `Selector` | Đợi và chọn các thao tác I/O có khả năng tiến triển. | `keys()` và `selectedKeys()`. |
| `SelectionKey` | Quan hệ đăng ký giữa channel và selector. | `interestOps()`, `readyOps()`, `attachment()`, `isValid()`. |
| `State` | Dữ liệu dở dang của từng TCP peer. | `input`, `request` và `output`. |
| `ByteBuffer` | Buffer bytes với `position/limit/remaining`. | Phải `flip/clear` đúng pha. |

## 4. Chuỗi sự kiện và interest ops

Vòng đời một request:

```text
   server.bind(...)
      │
      ▼
   server.register(selector, OP_ACCEPT)
      │
      ▼
   Selector.select() ──────► key.isAcceptable()
                                      │
                             listener.accept() != null?
                               ├── no: return to select
                               └── yes:
                                   peer.configureBlocking(false)
                                   peer.register(OP_READ, State)
                                      │
                                 key.isReadable()
                                      │
                               peer.read(input)
                              /       |       \
                            >0       =0       -1
                            │         │        │
                     parse bytes    select   EOF/close
                            │
                     newline reached?
                       no       yes
                       │         │
                     select   create output
                                │
                           interestOps(OP_WRITE)
                                │
                           key.isWritable()
                                │
                           peer.write(output)
                             /        \
                       remaining     drained
                           │            │
                        select       close peer
                                       │
                                   stop demo
```

`interestOps` là **điều ứng dụng muốn theo dõi**; `readyOps` là **readiness đã quan sát được** ở một lần selection. Chúng không phải số lượng byte đã truyền. Phải kiểm tra kết quả `read/write/accept` thực tế.

Ví dụ server không quan tâm `OP_WRITE` trước khi có response. Nếu bật `OP_WRITE` ngay từ đầu và giữ liên tục, socket thường luôn “có thể ghi” dù queue trống, dẫn đến vòng chọn được kích hoạt liên tục và tốn CPU.

## 5. Chương trình Java 17+ đầy đủ, biên dịch và chạy được

Lưu toàn bộ thành **`SelectorTcpEchoDemo.java`**. Chương trình gồm:

- `State`: một input `ByteBuffer` nhỏ (3 byte), một vùng tích lũy request và một output `ByteBuffer`.
- `serve`: server event loop với `OP_ACCEPT/READ/WRITE`, tự loại selected key sau xử lý.
- `main`: mở selector/server, bind loopback, tạo đúng một event-loop thread, sử dụng blocking `Socket` làm client thử nghiệm, đợi thread kết thúc và assert kết quả.
- Bộ đếm nhằm chứng minh **ít nhất** hai lượt read và ba lượt write; trong demo, giới hạn buffer được đặt rõ để làm hiệu ứng partial I/O có thể tái hiện.

```java
import java.io.ByteArrayOutputStream;
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
import java.util.concurrent.atomic.AtomicReference;

public class SelectorTcpEchoDemo {
    private static final class State {
        final ByteBuffer input = ByteBuffer.allocate(3);
        final ByteArrayOutputStream request = new ByteArrayOutputStream();
        ByteBuffer output;
    }

    private static final class Stats {
        int readCalls;
        int writeCalls;
    }

    private static void serve(Selector selector, Stats stats) throws IOException {
        boolean finished = false;
        while (!finished) {
            if (selector.select(3000) == 0) {
                throw new IOException("Server timed out");
            }
            Iterator<SelectionKey> iterator = selector.selectedKeys().iterator();
            while (iterator.hasNext()) {
                SelectionKey key = iterator.next();
                iterator.remove();
                if (!key.isValid()) continue;

                if (key.isAcceptable()) {
                    ServerSocketChannel listener =
                            (ServerSocketChannel) key.channel();
                    SocketChannel peer;
                    while ((peer = listener.accept()) != null) {
                        peer.configureBlocking(false);
                        peer.register(selector, SelectionKey.OP_READ,
                                new State());
                    }
                    continue;
                }

                SocketChannel peer = (SocketChannel) key.channel();
                State state = (State) key.attachment();

                if (key.isReadable()) {
                    int n = peer.read(state.input);
                    if (n == -1) {
                        peer.close();
                        throw new IOException("EOF before request completed");
                    }
                    if (n > 0) {
                        stats.readCalls++;
                        state.input.flip();
                        while (state.input.hasRemaining()) {
                            byte b = state.input.get();
                            if (b == '\n') {
                                String message = state.request.toString(
                                        StandardCharsets.UTF_8);
                                state.output = ByteBuffer.wrap(
                                        ("echo:" + message + "\n")
                                                .getBytes(StandardCharsets.UTF_8));
                                key.interestOps(SelectionKey.OP_WRITE);
                                break;
                            }
                            if (state.request.size() >= 4096) {
                                throw new IOException("Request is too long");
                            }
                            state.request.write(b & 0xff);
                        }
                        state.input.clear();
                    }
                }

                if (key.isValid() && key.isWritable()) {
                    // Only four bytes per call, to demonstrate partial writes.
                    int previousLimit = state.output.limit();
                    state.output.limit(Math.min(previousLimit,
                            state.output.position() + 4));
                    try {
                        int n = peer.write(state.output);
                        if (n > 0) stats.writeCalls++;
                    } finally {
                        state.output.limit(previousLimit);
                    }
                    if (!state.output.hasRemaining()) {
                        key.cancel();
                        peer.close();
                        finished = true;
                    }
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Stats stats = new Stats();
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            listener.configureBlocking(false);
            listener.register(selector, SelectionKey.OP_ACCEPT);

            Thread worker = new Thread(() -> {
                try {
                    serve(selector, stats);
                } catch (Throwable t) {
                    failure.set(t);
                }
            }, "selector-event-loop");
            worker.start();

            String reply;
            try {
                try (Socket client = new Socket()) {
                    client.connect(listener.getLocalAddress(), 3000);
                    client.setSoTimeout(3000);
                    client.getOutputStream().write(
                            "ping\n".getBytes(StandardCharsets.UTF_8));
                    reply = new String(client.getInputStream().readAllBytes(),
                            StandardCharsets.UTF_8);
                }
            } finally {
                worker.join(5000);
                if (worker.isAlive()) {
                    selector.close();
                    worker.join(5000);
                    throw new IOException("Event loop did not terminate");
                }
            }
            if (failure.get() != null) {
                throw new IOException("Event loop failed", failure.get());
            }
            System.out.println("reply=" + reply.stripTrailing());
            System.out.println("read-calls>=2=" + (stats.readCalls >= 2));
            System.out.println("write-calls>=3=" + (stats.writeCalls >= 3));
            System.out.println("roundtrip=" + reply.equals("echo:ping\n"));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SelectorTcpEchoDemo.java
java SelectorTcpEchoDemo
```

Stdout đã được xác nhận bằng biên dịch và chạy thực tế trên JDK 17+ trong môi trường cho phép TCP loopback:

```text
reply=echo:ping
read-calls>=2=true
write-calls>=3=true
roundtrip=true
```

**Vì sao test không in số lần đọc/ghi chính xác?** Với mạng và selector, lịch trình của OS có thể khác nhau. Demo cố ý đặt input buffer chỉ 3 byte, trong khi request `"ping\n"` dài 5 byte, nên cần **ít nhất hai lời gọi read thành công**. Response `"echo:ping\n"` có 10 byte, còn mỗi lần ghi bị tạm hạn chế tối đa 4 byte, nên cần **ít nhất ba lời gọi write thành công**. Số lời gọi thực tế có thể lớn hơn; kiểm tra cận dưới là assertion đúng và ổn định hơn.

Lưu ý đoạn này thực hiện **một request đơn, một lần kết nối**. Nó không phải echo server production, không giữ trạng thái cho nhiều request trên cùng socket, không giải quyết graceful half-close, TLS, authentication hoặc chính sách tổng bộ nhớ. Các bước mở rộng cuối bài chỉ ra nơi cần thay đổi.

## 6. Phân tích phần khởi tạo TCP listener

Đoạn trong `main`:

```java
try (Selector selector = Selector.open();
     ServerSocketChannel listener = ServerSocketChannel.open()) {
    listener.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
    listener.configureBlocking(false);
    listener.register(selector, SelectionKey.OP_ACCEPT);
}
```

Đây là đoạn trích từ chương trình mẫu. Các điểm kỹ thuật:

1. `Selector.open()` tạo selector của provider hiện tại. Ứng dụng không cần điều khiển trực tiếp `epoll/kqueue/poll`.
2. `ServerSocketChannel.open()` tạo channel phục vụ `accept`; trước khi bind nó chưa lắng nghe một cổng tùy chọn của bạn.
3. `InetAddress.getLoopbackAddress()` chỉ phục vụ kết nối nội bộ. Không bind `0.0.0.0` cho bài demo nếu không muốn máy khác có thể thử kết nối.
4. Cổng `0` yêu cầu OS chọn port đang khả dụng. `listener.getLocalAddress()` sau bind là địa chỉ/port đã có thật.
5. `configureBlocking(false)` **bắt buộc** trước khi `register` một channel với selector.
6. `OP_ACCEPT` là thao tác hợp lệ của `ServerSocketChannel`; nó không phải `OP_READ`. Đọc payload sẽ do `SocketChannel` được accept thực hiện.
7. `try-with-resources` đóng selector và listener khi rời scope, bao gồm khi exception xảy ra.

**Sai lầm thường gặp:** viết `listener.register(selector, OP_ACCEPT)` khi channel vẫn ở chế độ blocking, gây `IllegalBlockingModeException`. Hoặc đăng ký `OP_READ` cho `ServerSocketChannel`, không thuộc `validOps()` của loại channel đó.

## 7. OP_ACCEPT: từ server socket sang client SocketChannel

Handler của một selected key có `isAcceptable()`:

```java
ServerSocketChannel listener =
        (ServerSocketChannel) key.channel();
SocketChannel peer;
while ((peer = listener.accept()) != null) {
    peer.configureBlocking(false);
    peer.register(selector, SelectionKey.OP_READ, new State());
}
```

Đây là đoạn chạy trong event loop của chương trình đầy đủ.

**Vì sao `while (accept() != null)`?** Với server channel non-blocking, một `OP_ACCEPT` có thể tương ứng nhiều kết nối chờ được xử lý. Sau khi nhận hết những kết nối hiện sẵn, `accept()` trả `null`, khi ấy quay về vòng chọn. Không giả định có đúng một kết nối cho mỗi ready key.

**Vì sao `peer.configureBlocking(false)`?** Socket mới được accept không tự đảm bảo đang non-blocking theo cấu hình mong muốn; phải đặt rõ chế độ trước khi đăng ký với selector.

**Vì sao `new State()` được attach cho từng peer?** Mỗi client cần input buffer và dữ liệu chờ riêng; nếu các peer cùng chia sẻ một `ByteBuffer` mutable mà không có protocol ownership, bytes từ những kết nối khác nhau có thể lẫn vào nhau.

Trong server thực, một đợt kết nối dồn dập có thể cần giới hạn **số lần accept mỗi vòng**, quota clients, timeout, backpressure và xử lý lỗi khi register thất bại. Demo giữ vòng đơn giản vì chỉ có một client thử nghiệm.

## 8. OP_READ: một request có thể đến thành nhiều phần

TCP cung cấp **luồng byte**, không giữ nguyên ranh giới `write` của phía gửi. Client gửi `"ping\n"` trong một lệnh `Socket.getOutputStream().write(...)`, nhưng server có thể đọc nhiều chunk:

```text
Client sends five UTF-8 bytes:
70 69 6e 67 0a   = "ping\n"

Server input buffer has capacity 3:
1st read: 70 69 6e  -> "pin"
2nd read: 67 0a     -> "g\n"

Accumulated bytes before newline: 70 69 6e 67 = "ping"
Only after 0A is found: frame complete.
```

Với non-blocking `SocketChannel.read(ByteBuffer)`:

| Kết quả | Nghĩa | Hướng xử lý |
| --- | --- | --- |
| `n > 0` | Đã đọc đúng `n` byte và cập nhật `ByteBuffer.position()`. | Parse các bytes vừa đọc, giữ state nếu frame chưa đủ. |
| `n == 0` | Hiện chưa chuyển bytes. | Không quay CPU spin; đợi `OP_READ` khác. |
| `n == -1` | EOF ở phía input (peer đóng phía gửi). | Quyết định đóng, xử lý half-close hoặc phản hồi theo protocol. |

Demo dùng `ByteBuffer.allocate(3)`, gọi `flip()` sau khi đọc để tiêu thụ tất cả byte vừa nhận, rồi `clear()`. Do mỗi byte đã được đưa sang `ByteArrayOutputStream request`, nó **không cần `compact()` trong thiết kế này**. Nếu dùng parser trực tiếp trên input buffer có frame dở mà chưa được copy sang state khác, phải `compact()` để giữ bytes chưa xử lý.

Khi gặp `\n`, chương trình chuyển bytes đã tích lũy thành `String` UTF-8. Đây là điểm đúng để decode vì một ký tự UTF-8 có thể bị tách giữa hai lần đọc, đặc biệt nếu request chứa tiếng Việt hoặc emoji. **Không** gọi `new String(chunkBytes, UTF_8)` riêng cho mỗi chunk rồi nối kết quả; cách đó có thể làm hỏng ký tự đa byte bị cắt.

Giới hạn `4096` byte trước newline giúp tránh một client gửi mãi không có delimiter làm bộ nhớ tăng vô hạn. Đây chỉ là giới hạn **một request**; server thật còn cần giới hạn thời gian gửi từng dòng và tổng bộ nhớ của mọi peer.

## 9. OP_WRITE: giữ tiến độ và chỉ kích hoạt khi cần

Khi đã thấy newline, server chuẩn bị:

```java
state.output = ByteBuffer.wrap(
        ("echo:" + message + "\n").getBytes(StandardCharsets.UTF_8));
key.interestOps(SelectionKey.OP_WRITE);
```

Mẫu này chọn chuyển hẳn interest từ `OP_READ` sang `OP_WRITE` vì **demo chỉ nhận đúng một dòng**, sau đó gửi response và đóng socket. Một echo server nhiều request thường giữ `OP_READ` cùng lúc với `OP_WRITE` khi có outbound pending, hoặc tạm dừng đọc có kiểm soát khi cần backpressure.

Với non-blocking socket, một lần `write(ByteBuffer)` có thể:

- Ghi toàn bộ bytes còn lại.
- Chỉ ghi **một phần**.
- Ghi **0 byte**, ngay cả khi trước đó key được báo writable.

Do vậy phải giữ `ByteBuffer.position()` qua nhiều lần ghi, chỉ coi response được viết hết khi `!state.output.hasRemaining()`:

```java
// Snippet: output đã chuẩn bị (pha đọc), peer non-blocking.
int n = peer.write(state.output);
if (n == 0) {
    // Không bận quay vòng; đợi readiness khác.
}
if (!state.output.hasRemaining()) {
    // Toàn bộ buffer đã được peer.write tiêu thụ.
}
```

Trong demo, để luôn quan sát partial writes, ta **tạm giảm `limit` của output** trước mỗi lời gọi:

```java
int oldLimit = state.output.limit();
state.output.limit(Math.min(
        oldLimit, state.output.position() + 4));
try {
    peer.write(state.output);
} finally {
    state.output.limit(oldLimit);
}
```

Đây là snippet rút từ demo. Việc thu hẹp `limit` không yêu cầu OS thực tế chỉ ghi đúng 4 byte: nó chỉ đặt một **cận trên** cho phép ghi của lời gọi ấy. `FileChannel/SocketChannel.write` vẫn có thể ghi ít hơn. `finally` khôi phục limit cũ, và position đã tăng giữ nguyên.

Khi pending đã hết, demo hủy key/đóng peer và dừng; server phục vụ lâu dài thường **gỡ `OP_WRITE`**:

```java
// Bật khi queue có dữ liệu:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Gỡ khi queue trống, giữ OP_READ hoặc flag khác:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Đây là snippet mở rộng cho server thường trực. **Không giữ `OP_WRITE` bật khi không có data**: socket thường writable dẫn tới các vòng `select` được đánh thức liên tục, làm CPU tăng dù không có request.

## 10. selectedKeys(): đọc đúng, xóa đúng

Mẫu cốt lõi của event loop:

```java
while (!finished) {
    int selected = selector.select(3000);
    if (selected == 0) {
        // Demo: timeout. Server thật cần policy timers/tasks.
        continue;
    }

    Iterator<SelectionKey> iterator =
            selector.selectedKeys().iterator();
    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (!key.isValid()) continue;
        // Kiểm tra isAcceptable/isReadable/isWritable và xử lý.
    }
}
```

Đoạn này là **snippet minh họa cách duyệt**, không phải phần thay thế nguyên xi của hàm `serve`: demo đầy đủ cố ý ném lỗi nếu quá thời gian 3 giây mà không có sự kiện.

- `selector.keys()` là tập key đăng ký; `selectedKeys()` là tập key đã được chọn có readiness.
- `iterator.remove()` xóa **key khỏi selected-key set** sau khi lấy ra. Tập này không được runtime tự xóa chỉ vì code đã gọi handler.
- Không giữ một key cũ rồi cho rằng `readyOps` luôn còn đúng ở thời điểm tương lai; sau thao tác I/O readiness có thể thay đổi.
- `key.cancel()` đánh dấu hủy đăng ký nhưng **không thay cho `SocketChannel.close()`** khi bạn sở hữu socket.
- `key.isValid()` cần được kiểm tra trước các thao tác dễ ném `CancelledKeyException`. Handler có thể cancel/close key ngay trong một sự kiện.
- Một key có thể ready nhiều ops cùng lúc; code demo dùng `if (key.isReadable())` rồi `if (key.isValid() && key.isWritable())` để không giả định chỉ một bit ready.

`Selector.select()` có thể trả 0 vì timeout, wakeup hoặc những điều kiện khác được API cho phép; trong ứng dụng thật không coi mọi lần 0 là lỗi disconnect. Một timeout cấp ứng dụng phải tính theo thời điểm deadline, không nên reset vô hạn mỗi khi có bất kỳ event không liên quan.

## 11. Thử nghiệm client: blocking để kiểm tra server non-blocking

Đoạn client test nằm trong `main`:

```java
try (Socket client = new Socket()) {
    client.connect(listener.getLocalAddress(), 3000);
    client.setSoTimeout(3000);
    client.getOutputStream().write(
            "ping\n".getBytes(StandardCharsets.UTF_8));
    reply = new String(client.getInputStream().readAllBytes(),
            StandardCharsets.UTF_8);
}
```

Đây là snippet lấy từ chương trình. Client dùng `java.net.Socket` blocking **có chủ đích** để giữ bài đơn giản: mục tiêu là viết **server event loop sử dụng Selector**, không yêu cầu cả client cũng non-blocking.

Phương thức `readAllBytes()` trên socket có thể chờ tới EOF, vì TCP là stream. Demo **đóng peer phía server sau khi ghi hết response**, nên client đạt EOF và phép đọc trả về toàn bộ response. Trong giao thức keep-alive/multi-request, không dùng `readAllBytes()` để chờ một dòng phản hồi nếu server giữ socket mở; client phải đọc đến delimiter `\n` hoặc theo length-prefix.

`setSoTimeout(3000)` giới hạn thời gian chờ đọc trên socket blocking để demo không treo vô hạn khi lỗi, nhưng timeout ở môi trường CI quá chậm có thể cần tăng theo chính sách test. Cổng chỉ mở trên loopback, không có authentication và không nên đưa nguyên demo ra internet.

Biến `AtomicReference<Throwable>` chuyển lỗi từ event-loop thread về main thread sau `join()`. Đây là lựa chọn đơn giản cho demo; ứng dụng lớn hơn thường có lifecycle service, futures hoặc cơ chế giám sát exception có cấu trúc.

## 12. Quản lý vòng đời và giải phóng tài nguyên

Bốn nhóm tài nguyên cần chú ý:

| Tài nguyên | Ai sở hữu? | Đóng khi nào? |
| --- | --- | --- |
| `Selector` | Thành phần server/event loop. | Sau khi event loop dừng hoặc bị điều phối shutdown. |
| `ServerSocketChannel` | Thành phần listener. | Khi ngừng nhận kết nối mới, hoặc khi server dừng hoàn toàn. |
| `SocketChannel` của client | Handler/connection manager. | Khi request hoàn tất theo demo, EOF, lỗi, timeout hoặc chính sách đóng. |
| `Socket` blocking client | Phần test. | Sau khi nhận đủ response và kiểm tra, hoặc khi xảy ra exception. |

Demo dùng `try-with-resources` cho selector, listener và blocking client. Ở server, `peer.close()` đóng socket sau khi output buffer đã được tiêu thụ hết.

**Quan trọng:** `ByteBuffer.hasRemaining() == false` chỉ có nghĩa các byte từ buffer được lời gọi `write` chấp nhận theo hợp đồng, **không** chứng minh ứng dụng phía bên kia đã xử lý response thành công. Với protocol cần xác nhận nghiệp vụ, cần ACK ở tầng ứng dụng.

Trong server nhiều client, khi dừng cần đóng **tất cả** accepted channels còn mở, không chỉ listener và selector. Đóng selector làm key invalid nhưng không nên dựa vào nó như cơ chế tự đóng mọi socket đang đăng ký. Duy trì danh sách/ownership rõ ràng, hoặc đóng peer khi xử lý key và bảo đảm cleanup ở một khối `finally`.

## 13. Những giới hạn có chủ ý của chương trình mẫu

Chương trình minh họa hoạt động thật, nhưng một số lựa chọn chỉ phục vụ việc học:

1. **Một request, một response, rồi đóng:** khi gửi xong một dòng, `finished=true`. Để phục vụ nhiều client, bỏ điều kiện stop toàn server; chỉ đóng peer tương ứng.
2. **Không xử lý nhiều frame trong cùng một lượt đọc:** nếu client gửi hai dòng cùng một chunk, demo chỉ xử lý dòng đầu và có thể bỏ phần sau. Production phải giữ bytes còn lại và lặp parser.
3. **Không có queue outbound nhiều buffer:** một connection chỉ cần một `output`; server nhiều request phải có `Deque<ByteBuffer>` và xử lý từng buffer cho đến khi queue trống.
4. **Gửi tối đa 4 byte mỗi lần** là cách kiểm thử partial write, không phải tối ưu hiệu năng.
5. **Input buffer 3 byte** để ép partial read; production thường dùng buffer lớn hơn, memory pooling và quota theo load.
6. **Đọc UTF-8 qua `new String(bytes, UTF_8)` sau newline:** với dữ liệu không tin cậy cần strict decoder khi giao thức bắt buộc UTF-8 hợp lệ, và quy tắc CRLF nếu hỗ trợ.
7. **Giới hạn 4096 byte** chỉ cho request trước delimiter. Không có timeout cho client gửi quá chậm từng byte ngoài timeout `select` chung.
8. **Một thread client blocking** để kiểm tra server; nhiều client thật cần load test riêng.
9. **Lỗi I/O làm dừng toàn server:** demo để người học dễ nhìn thấy lỗi. Production nên đóng kết nối lỗi và tiếp tục phục vụ client khác, trừ lỗi hệ thống không thể phục hồi.
10. **Không có TLS, authentication, metrics, logging hoặc graceful shutdown thực thụ:** không đưa thẳng ra production.

Những giới hạn này không làm ví dụ không chính xác; chúng xác định rõ **phạm vi lab** để bạn không nhầm minh họa event loop tối thiểu với máy chủ chịu tải lớn.

## 14. Mở rộng bài lab thành server nhiều kết nối

Mô hình duy trì nhiều connections:

```text
Selector server
  ├─ ServerSocketChannel => OP_ACCEPT
  ├─ SocketChannel #1 => State(input, parser, outbound queue)
  ├─ SocketChannel #2 => State(input, parser, outbound queue)
  └─ SocketChannel #N => State(input, parser, outbound queue)

Với mỗi key:
  ACCEPT: accept tối đa quota rồi register OP_READ
  READ: đọc tối đa byte budget, decode nhiều frame, enqueue responses
        nếu queue có data => bật OP_WRITE
  WRITE: write từng buffer, giữ partial, gỡ OP_WRITE khi queue trống
  EOF/ERROR: flush theo protocol nếu cần, sau đó close socket
```

Một `State` nhiều request có thể trông như:

```java
// Snippet thiết kế, không phải bản demo chạy độc lập.
final class ConnectionState {
    ByteBuffer inbound = ByteBuffer.allocate(8192);
    ArrayDeque<ByteBuffer> outbound = new ArrayDeque<>();
    long lastActivityNanos = System.nanoTime();
    boolean peerInputClosed;
}
```

Cần import `ArrayDeque` và `ByteBuffer`. Event loop thường **sở hữu** các state này trên một thread. Nếu thread khác muốn gửi dữ liệu vào queue, phải dùng cơ chế đồng bộ và wakeup phù hợp.

### Bước đổi từ single request sang multiple requests

- Thay `finished=true` bằng logic đóng **riêng** `SocketChannel` hoàn tất, còn server event loop chạy.
- Sau khi output queue trống, giữ/re-enable `OP_READ` cho connection nếu protocol cho phép request mới.
- Dùng parser xử lý nhiều newline trong cùng chunk; không bỏ bytes sau newline thứ nhất.
- Giữ một buffer/tập byte dở dang cho request chưa kết thúc, tránh decode UTF-8 theo từng chunk.
- Khi nhận được một frame, enqueue response nhưng tiếp tục tôn trọng hạn mức memory/outbound queue.
- Dùng deadline cho idle connection, request incomplete và shutdown.
- Đóng tất cả accepted channels khi stop service.

**Không lấy cùng một `State` gắn cho mọi key**. Buffer và parser phải gắn với đúng connection để không lẫn request từ hai client.

## 15. Backpressure và tránh vòng quay CPU bận

Một server non-blocking có thể bị client đọc chậm. Khi output queue còn byte nhưng `socket.write` trả 0, không quay vòng:

```java
// Snippet cho SocketChannel non-blocking.
while (!out.hasRemaining()) {
    // Không nên dùng vòng này để giả lập chờ.
}
```

Đoạn trên là **phản ví dụ**: có thể bận CPU hoặc không có ý nghĩa khi output còn bytes. Thay bằng:

```java
// Snippet: key còn valid, out là ByteBuffer đang chờ.
if (out.hasRemaining()) {
    int n = peer.write(out);
    if (n == 0) {
        key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
        // Trở lại vòng select, không retry vô hạn tại đây.
    }
}
```

Mẫu cho queue:

1. Khi có response, đưa `ByteBuffer` đã `flip()` (hoặc `wrap`) vào `outbound`.
2. Bật `OP_WRITE`.
3. Khi ready, cố ghi buffer đầu. Nếu ghi chưa hết, giữ lại `position`. Nếu hết, bỏ buffer đó khỏi queue và tiếp tục buffer sau trong giới hạn workload.
4. Nếu queue trống, **gỡ `OP_WRITE`**. Nếu còn bytes, giữ interest.
5. Giới hạn tổng bytes pending trên từng client và toàn server. Nếu vượt, tạm ngừng đọc từ client đó, báo quá tải hoặc đóng kết nối theo chính sách.

Backpressure không chỉ là vấn đề hiệu năng: không có hạn mức, hàng nghìn client đọc chậm có thể giữ lượng lớn bytes đã encode trong heap cho đến khi ứng dụng hết bộ nhớ.

## 16. select(), selectNow(), wakeup() và thread ownership

Các phương thức:

| API | Tác dụng | Ghi chú |
| --- | --- | --- |
| `selector.select()` | Chờ selection sẵn sàng hoặc cơ chế đánh thức/đóng. | Phù hợp vòng server liên tục, cần cơ chế shutdown và task queue. |
| `selector.select(timeoutMs)` | Chờ tối đa khoảng timeout dương, `0` nghĩa chờ không giới hạn theo hợp đồng API. | Demo dùng 3000 ms để fail-fast. |
| `selector.selectNow()` | Kiểm tra trạng thái selection không blocking. | Không nên spin liên tục khi không có việc. |
| `selector.wakeup()` | Báo thức một vòng select đang hoặc sắp chặn. | Không tự làm socket read/write sẵn sàng. |
| `key.interestOps(mask)` | Cập nhật bitmask interest. | Đừng vô tình tắt `OP_READ` khi bật `OP_WRITE`. |

Khi event loop có thread riêng và producer muốn gửi thêm bytes:

```java
// Snippet: từ thread producer; tasks là queue thread-safe.
tasks.add(() -> enqueueOutbound(connectionId, bytes));
selector.wakeup();
```

Event loop khi thức dậy lấy tasks rồi cập nhật trạng thái của những connection mà nó sở hữu. `wakeup()` chỉ đánh thức lựa chọn, **không gửi byte** thay application. Nếu producer thao tác trực tiếp `ByteBuffer` hoặc `ArrayDeque` thuộc event loop từ một thread khác, cần đồng bộ rõ để tránh race.

**Thread safety của Selector/Channel không thay được tính nhất quán của protocol state.** Một chiến lược dễ giải thích là mọi register, cancel, queue mutation và parse/write của một connection đều do một event-loop thread sở hữu; những thread khác gửi message/task qua queue.

## 17. Lỗi thường gặp khi làm bài thực hành

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `IllegalBlockingModeException` khi register | Quên `configureBlocking(false)` trước `register`. | Cấu hình non-blocking cho listener và accepted socket. |
| `IllegalArgumentException` ở interest mask | `OP_READ` trên `ServerSocketChannel` hoặc flag không thuộc `validOps()`. | Register `OP_ACCEPT` cho listener, `OP_READ/WRITE` cho peer. |
| Server không nhận request sau accept | Quên register `SocketChannel` mới. | `peer.register(selector, OP_READ, new State())`. |
| Handler cứ chạy lại key cũ | Không `iterator.remove()` selected key. | Xóa key khỏi selected set trong vòng duyệt. |
| CPU cao khi không có dữ liệu | Luôn giữ `OP_WRITE` hoặc quay vòng khi `read/write==0`. | Chỉ bật OP_WRITE khi có pending, quay về `select`. |
| Client nhận thiếu response | `write` chỉ chuyển được một phần; buffer bị reset/clear. | Giữ position, lặp qua nhiều readiness đến `!hasRemaining()`. |
| Server coi một chunk là một dòng | TCP không bảo toàn ranh giới request. | Tích lũy bytes đến newline/length-prefix. |
| Tiếng Việt/emoji thành `�` | Decode UTF-8 khi còn thiếu byte giữa các chunk. | Giữ bytes và decode sau đủ frame hoặc dùng decoder incremental. |
| Server gửi response quá sớm | Chưa gặp newline, nhưng tưởng OP_READ là full request. | Parser giữ state đến delimiter. |
| Client `readAllBytes()` chờ mãi | Server giữ socket open kiểu keep-alive, không gửi EOF. | Client đọc theo framing, hoặc server đóng sau response theo protocol. |
| `CancelledKeyException` | Key đã cancel nhưng handler tiếp tục truy cập ready/interest ops. | Kiểm tra `isValid()` và dừng handler khi close/cancel. |
| `ClosedChannelException` | Dùng channel sau `close()` hoặc chọn sai vòng đời. | Quản lý ownership và cleanup. |
| Cổng cố định báo `BindException` | Một process khác đang chiếm port. | Với lab dùng bind port 0 và `getLocalAddress()`. |
| Server chỉ chạy trong máy mình | Loopback không cho máy khác kết nối. | Đây là chính sách an toàn chủ đích; production cần bind theo yêu cầu và bảo vệ mạng. |
| Một client chậm làm server đơ | Handler blocking hoặc xử lý không giới hạn. | Budget mỗi key; offload công việc blocking/CPU nặng. |
| Server tiếp tục mở sockets sau stop | Chỉ đóng selector mà không quản lý accepted channels. | Đóng từng peer, listener, selector theo lifecycle. |

Để debug, log thời điểm, ID kết nối, số bytes `read/write`, `position/limit/remaining`, ready ops, interest ops, số bytes outbound pending và nguyên nhân close. Không log raw payload chứa dữ liệu nhạy cảm hoặc tạo logging blocking nặng trong event loop.

## 18. Quy trình kiểm thử thực tế

### Kiểm thử A — chạy demo và đọc stdout

1. Lưu file theo UTF-8 đúng tên.
2. Chạy `javac -encoding UTF-8 SelectorTcpEchoDemo.java`, kiểm tra exit code.
3. Chạy `java SelectorTcpEchoDemo`.
4. Xác minh `reply=echo:ping` và `roundtrip=true`.
5. Xác minh `read-calls>=2=true`, `write-calls>=3=true`.
6. Nếu timeout, kiểm tra chính sách TCP loopback/antivirus, JVM và cổng; không tự đổi mục tiêu test thành “chạy không exception” mà bỏ qua round-trip.

### Kiểm thử B — payload thay đổi

Đổi lời gửi client từ `"ping\n"` thành `"hello\n"`; đồng thời cập nhật expected reply thành `"echo:hello\n"`. Bảo đảm parser đợi newline và response không bị mất byte. Nếu muốn đo ít nhất ba lượt write, giữ giới hạn 4 byte từ demo.

### Kiểm thử C — không có newline

Cho client gửi `"partial"` mà không đóng hoặc không gửi newline, rồi áp dụng timeout. Server không được tuyên bố frame hoàn tất; test phải có deadline. Khi peer đóng trước newline, demo báo `EOF before request completed`.

### Kiểm thử D — quá dài

Gửi hơn 4096 byte không có delimiter. Server demo sẽ ném `IOException("Request is too long")`. Trong server production, nên đóng **connection vi phạm** và tiếp tục phục vụ các connections khác thay vì dừng toàn service.

### Kiểm thử E — Unicode/UTF-8

Gửi `"Việt 😀\n"` dưới dạng UTF-8, giữ input buffer ba byte. Bên nhận phải tích lũy đủ bytes rồi mới decode. Đầu ra logic `"echo:Việt 😀\n"`. Nếu dùng strict decoder, lỗi malformed phải được từ chối có kiểm soát.

### Kiểm thử F — nhiều client đồng thời

Sau khi mở rộng server để không dừng sau client đầu, chạy 10–100 client thử nghiệm trên loopback, mỗi client gửi nhiều dòng với nhịp khác nhau. Kiểm tra không lẫn state/response, không starvation, không leak sockets và không bị busy loop khi tất cả idle. Thêm quota và timeouts trước khi tăng tải lớn.

### Kiểm thử G — graceful shutdown

Khi đang có connections, đặt cờ stop và `selector.wakeup()`; ngừng accept, xả queue có deadline, đóng accepted peers, đóng listener, rồi đóng selector. Kiểm tra thread sự kiện không kẹt, không bỏ task ngoài chính sách và đóng tất cả resource.

## 19. Bài tập nâng cao sau lab

**Bài 1 — Bật/tắt OP_WRITE thay vì đóng connection.** Giữ kết nối sau một response để nhận dòng tiếp. Khi queue empty, thay vì đóng peer hãy chuyển về `OP_READ` hoặc giữ `OP_READ` liên tục, gỡ `OP_WRITE` bằng bitmask. Chứng minh CPU không cao khi client idle.

**Bài 2 — Xử lý nhiều dòng trong một read.** Cho client gửi `"one\ntwo\n"` cùng một lần write. Thay logic `break` sau newline bằng parser có thể tạo hai responses. Giữ bytes sau newline thay vì bỏ qua; test đúng thứ tự `echo:one`, `echo:two`.

**Bài 3 — Outbound queue và partial write.** Thay `State.output` bằng `ArrayDeque<ByteBuffer>`. Gửi ba response nhỏ và giới hạn mỗi write tối đa hai byte. Kiểm tra dữ liệu cuối không bị mất/trùng dù response được chia thành nhiều lần ghi.

**Bài 4 — Header length-prefix.** Thay framing newline bằng 4 byte đầu chứa chiều dài payload theo `ByteOrder.BIG_ENDIAN`. Tích lũy đủ header, kiểm tra length không âm/không quá 4096, rồi đọc đúng số bytes; test trường hợp header bị cắt giữa hai read.

**Bài 5 — Non-blocking client.** Viết client dùng `SocketChannel` với `OP_CONNECT`. Khi `isConnectable()`, gọi `finishConnect()`; chỉ bật `OP_READ/WRITE` cho application protocol sau khi connect thành công. Xử lý exception khi connect thất bại.

**Bài 6 — Worker pool.** Khi gặp frame hoàn chỉnh, gửi công việc CPU tốn thời gian qua executor, rồi trả response về event loop bằng queue thread-safe + `selector.wakeup()`. Không cho worker mutate `ByteBuffer` thuộc event-loop thread trực tiếp.

**Bài 7 — Backpressure.** Giới hạn 64 KiB outbound pending mỗi connection. Khi client đọc quá chậm, tạm gỡ `OP_READ` hoặc reject/quarantine theo protocol; phục hồi đọc khi queue giảm dưới ngưỡng thấp hơn để tránh bật/tắt liên tục.

**Bài 8 — Protocol error và timeout.** Thêm deadline cho idle connection, frame chưa đầy đủ và thời gian xả response. Client gửi bytes không kết thúc dòng hoặc malformed UTF-8 phải nhận xử lý lỗi rõ, không giữ socket vô hạn.

**Bài 9 — Metrics và load test.** Đo số active clients, bytes read/write, pending buffers, số vòng `select` trả 0 và p95 response latency. Phân biệt throughput, readiness và số request hoàn tất; không suy diễn thành công chỉ từ số event.

**Bài 10 — Dừng server có kiểm soát.** Tạo điều khiển stop thread-safe, gọi `selector.wakeup()`, hủy keys, đóng channels trong thread sở hữu selector rồi `join` với deadline. Kiểm tra không rò file descriptors và không block shutdown.

## 20. Những câu hỏi cần trả lời sau khi chạy

1. `ServerSocketChannel` và `SocketChannel` khác vai trò gì? Tại sao listener dùng `OP_ACCEPT` thay vì `OP_READ`?
2. Vì sao phải gọi `configureBlocking(false)` trước `register()`?
3. Khi `selector.select()` trả về, số key ready có nói được tổng số bytes sẽ đọc/ghi không?
4. Vì sao `iterator.remove()` phải xuất hiện trong vòng duyệt `selectedKeys()`?
5. Vì sao handler đọc từng byte đến newline thay vì coi một `read` là một request?
6. Vì sao input buffer ba byte vẫn đọc được request năm byte?
7. Vì sao thay `key.interestOps(OP_WRITE)` chỉ đúng với single-request demo, nhưng có thể làm mất OP_READ trong server nhiều request?
8. Khi `write(output)` trả 0, tại sao không lặp liên tục cho đến khi nó ghi được?
9. `ByteBuffer.flip()` và `clear()` thay đổi position/limit thế nào? Khi nào phải dùng `compact()`?
10. `key.cancel()` có tự đóng `SocketChannel` và giải phóng mọi memory state không?
11. Nếu client giữ kết nối mở sau response, `readAllBytes()` có thể chờ gì và giao thức nên xử lý ra sao?
12. Tại sao phần server của demo dùng **một event-loop thread**, dù chương trình vẫn có main thread đóng vai client?
13. Khi server gửi xong bytes, nó có biết ứng dụng client đã xử lý response và commit nghiệp vụ chưa?
14. Khi chuyển sang production, cần bổ sung những gì cho nhiều client, backpressure, timeouts, TLS và graceful shutdown?

## 21. Checklist trước khi coi thực hành thành công

- `javac` báo thành công, chạy `java SelectorTcpEchoDemo` không ném exception trong môi trường loopback hỗ trợ.
- Server bind địa chỉ loopback và port OS cấp, không tự mở listener công cộng.
- Listener non-blocking được đăng ký `OP_ACCEPT`.
- Accepted `SocketChannel` non-blocking được đăng ký `OP_READ` với `State` riêng.
- Mỗi selected key được xóa bằng `iterator.remove()`.
- Request chỉ được coi hoàn tất khi gặp delimiter `\n` và không vượt quota.
- Output được gửi theo `ByteBuffer.position()/remaining()` qua nhiều lần write.
- Server không giữ `OP_WRITE` bật khi không có pending response trong kiến trúc server nhiều request.
- Client nhận chính xác `echo:ping\n`, bộ test xác nhận `roundtrip=true`.
- Mỗi socket, listener và selector đều có owner và lộ trình close.
- Hiểu rằng demo một request chưa phải server nhiều client production.
- Biết cách mở rộng parser/queue, xử lý `read==0/-1`, timeouts, lỗi kết nối và shutdown.

## 22. Tài liệu tham khảo

- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): selected-key set, selection, `selectNow`, `wakeup`, close.
- [Java SE 21 — SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready ops, attachments, cancellation.
- [Java SE 21 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): bind và accept non-blocking.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): read/write, blocking mode, connection lifecycle.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip/clear/compact`, `hasRemaining` và semantics của buffer.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 và charset tường minh.

**Ghi nhớ:** Vòng Selector dùng một event-loop thread để điều phối nhiều TCP channels theo **readiness**, không tự truyền dữ liệu hay hoàn tất request. Xây server đúng bằng cách `register` channel non-blocking, `select`, xóa selected keys đã xử lý, giữ per-connection state cho bytes dở dang, bật `OP_WRITE` đúng lúc, xử lý partial I/O và đóng tài nguyên theo lifecycle. Sau khi lab chạy đúng, bước quan trọng tiếp theo là nhiều request, queue có quota, timeouts và graceful shutdown.
