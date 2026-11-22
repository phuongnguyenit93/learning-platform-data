# Kiểm thử wakeup, khóa bị hủy và kết nối đóng với Selector callback (Java 11+)

## 1. Bối cảnh: vì sao cần kiểm thử vòng đời của Selector?

Trong Java NIO, `Selector` theo dõi những `SelectableChannel` đã đăng ký và cho biết kênh nào sẵn sàng cho thao tác I/O. Từ **Java 11**, ngoài kiểu chọn khóa rồi tự duyệt tập `selectedKeys()`, API có các overload dùng **callback**:

```java
selector.select(key -> handle(key));
selector.select(key -> handle(key), 1_000L);
selector.selectNow(key -> handle(key));
```

Callback nhận một `SelectionKey` sẵn sàng và thực hiện xử lý. Những phương thức này vẫn tồn tại trong Java hiện đại. Tuy nhiên, luồng sự kiện I/O có thể bị thay đổi **ngay khi selector đang chờ** hoặc **ngay trước lúc callback chạy**:

- Một thread khác gọi `selector.wakeup()`.
- Một `SelectionKey` bị hủy qua `cancel()`.
- Kênh đã đăng ký bị đóng.
- Peer (đầu bên kia) đóng kết nối TCP, dẫn đến EOF hoặc lỗi I/O.
- Chính `Selector` bị đóng khi còn thao tác chờ.

Bài này kiểm thử cụ thể từng trường hợp, phân biệt hành vi API được **bảo đảm** với điều chỉ xảy ra trên một lần chạy. Ví dụ đầy đủ sử dụng Java 11+, `CountDownLatch`, `Future` và kết nối **loopback** trên máy để tránh phụ thuộc vào máy chủ Internet.

## 2. Ôn nhanh Selector callback: select(Consumer) hoạt động thế nào?

Các phương thức Java 11 cần nhớ:

| Phương thức | Chờ sự kiện? | Vai trò |
| --- | --- | --- |
| `select(Consumer<SelectionKey> action)` | Có thể chờ vô thời hạn | Gọi callback cho các khóa sẵn sàng |
| `select(Consumer<SelectionKey> action, long timeout)` | Chờ tối đa khoảng `timeout` mili giây nếu `timeout > 0`; `0` có nghĩa chờ vô thời hạn | Có giới hạn thời gian khi cần |
| `selectNow(Consumer<SelectionKey> action)` | Không chờ | Thăm dò một lượt và gọi callback cho khóa sẵn sàng |
| `wakeup()` | Không phải thao tác select | Đánh thức một lượt select đang chờ hoặc lượt select tiếp theo |
| `close()` | — | Đóng selector, đánh thức lượt select đang chờ và hủy đăng ký liên quan |

**Giá trị trả về `int` của các overload callback** là **số khóa khác nhau được tiêu thụ (unique keys consumed)**, không nhất thiết là số lần `Consumer.accept(...)` được gọi. Javadoc cho phép một khóa được callback nhiều hơn một lần nếu các tập thao tác sẵn sàng được chia thành những phần khác nhau.

Khác với `select()`/`selectNow()` truyền thống, các overload callback **không thêm** khóa sẵn sàng vào `selected-key set` theo hợp đồng lựa chọn dạng callback. Vì vậy không viết vòng lặp callback rồi lại duyệt `selectedKeys()` với giả định tập này sẽ chứa toàn bộ khóa vừa callback. Phần triển khai mặc định có những chi tiết tương thích riêng; tránh dựa vào tập được giữ rỗng tuyệt đối sau mỗi lần gọi.

**Ràng buộc quan trọng:** `action.accept(key)` có thể chạy khi đang đồng bộ hóa trên selector và selected-key set. Không gọi `select(...)` lồng lại trên **cùng selector** trong callback: hành vi tái nhập không được đặc tả chung và có nguy cơ gây deadlock hay lỗi. Giữ callback ngắn, tránh chờ vô hạn và đồng bộ khóa theo thứ tự tùy tiện.

## 3. Kiểm thử wakeup(): đánh thức đúng, không nhầm với có dữ liệu

### 3.1. wakeup không có nghĩa là có khóa sẵn sàng

`Selector.wakeup()` buộc một lượt lựa chọn đang chờ **trả về sớm**. Nếu chưa có lượt select nào đang chờ, hiệu lực được giữ để lượt lựa chọn kế tiếp trả về sớm (trừ khi được tiêu thụ bởi một thao tác như `selectNow()` hoặc `selectNow(Consumer)`).

Ví dụ:

```java
try (Selector selector = Selector.open()) {
    selector.wakeup();
    int selected = selector.select(key -> {
        throw new AssertionError("No key expected");
    }, 2_000);

    System.out.println(selected); // 0 khi không có kênh được đăng ký
}
```

Tại đây không có kênh đăng ký nên kết quả là `0`. **Không** suy ra từ `wakeup()` rằng callback chắc chắn phải chạy, hoặc rằng giá trị trả về luôn là `0`: nếu có kênh đang sẵn sàng, lần select được đánh thức vẫn **có thể** trả về số khóa dương.

Các lần `wakeup()` liên tiếp trước một lượt select có hiệu lực như một lần đánh thức; không phải một hàng đợi sự kiện đếm được. `selectNow()`, kể cả bản có callback, có thể tiêu thụ hiệu lực đánh thức đã chờ.

### 3.2. wakeup từ thread khác: kiểm thử không dựa vào Thread.sleep

Kiểm thử tốt nên dùng đồng bộ hóa có mục đích. Ví dụ Java đầy đủ ở phần 6 tạo một worker thread, dùng `CountDownLatch` để xác nhận worker đã đi tới bước chuẩn bị `select`, rồi gọi `wakeup()` và đợi `Future.get(...)` có timeout.

Điều này kiểm tra rằng **lượt select kết thúc sau tín hiệu đánh thức**, không cần đoán thời gian hệ điều hành sẽ lên lịch thread. Lưu ý latch được đếm ngay **trước** lời gọi `select`: có thể `wakeup` xảy ra trước khi thread thật sự bắt đầu chờ; đó vẫn là trường hợp được hợp đồng `wakeup` hỗ trợ.

**Sai lầm:** dùng `Thread.sleep(100)` rồi cho rằng thread kia chắc chắn đang chờ trong `select`. Cách kiểm thử đó dễ thất bại ngẫu nhiên trên máy chậm hoặc lúc tải cao.

## 4. Kiểm thử SelectionKey bị hủy: invalid ngay, dọn đăng ký sau

Một `SelectionKey` được tạo khi `SelectableChannel.register(selector, ops)`. Theo hợp đồng `SelectionKey`:

1. Khi gọi `key.cancel()`, `key.isValid()` trở thành **`false` ngay**.
2. Khóa được đưa vào **cancelled-key set**; nó **chưa chắc lập tức biến mất** khỏi mọi tập khóa của selector.
3. Trong **lượt selection tiếp theo**, selector xử lý những khóa bị hủy và gỡ đăng ký của chúng. Lúc đó khóa được bỏ khỏi các tập tương ứng.
4. Khóa đã hủy **không thể trở lại hợp lệ**. Nếu cần đăng ký tiếp, dùng đăng ký mới sau khi việc hủy/gỡ đăng ký hoàn tất.

Có thể dùng `Pipe.SourceChannel` để kiểm thử hủy khóa mà không cần mở TCP socket:

```java
Pipe pipe = Pipe.open();

try (Selector selector = Selector.open();
     Pipe.SourceChannel source = pipe.source();
     Pipe.SinkChannel sink = pipe.sink()) {

    source.configureBlocking(false);
    SelectionKey key = source.register(selector, SelectionKey.OP_READ);
    key.cancel();

    System.out.println(key.isValid()); // false

    selector.selectNow(k -> {
        throw new AssertionError("Cancelled key should not be delivered");
    });

    System.out.println(selector.keys().contains(key)); // false
}
```

Đây là **mảnh mã** trong phương thức khai báo `throws Exception` với `Pipe`, `Selector`, `SelectionKey` và `SelectionKey.OP_READ` được import. Sau `selectNow(callback)`, việc xử lý cancelled-key set đã hoàn tất. **Không phải** cứ gọi `cancel()` là một thread khác đang chờ `select(...)` sẽ tự động được đánh thức: khi cần thay đổi vòng xử lý từ thread khác, gọi thêm `selector.wakeup()`.

### 4.1. Hủy khóa ngay trong callback

Callback được phép hủy khóa hoặc đóng kênh. Nếu đã đọc xong dữ liệu và không muốn theo dõi nữa:

```java
selector.selectNow(key -> {
    if (!key.isValid()) return;

    if (key.isReadable()) {
        key.cancel();
    }
});
```

**Đây chỉ là đoạn minh họa**, cần chắc chắn bạn đã xử lý dữ liệu I/O theo nghiệp vụ trước khi hủy. Trong ví dụ đầy đủ, chương trình ghi một byte vào `Pipe`, callback đọc byte đó rồi gọi `cancel()`; kiểm tra trạng thái ngay trong cùng lượt.

**Đồng thời:** `key.isValid()` là một bước kiểm tra hữu ích nhưng không phải khóa bảo vệ khỏi tất cả race condition. Nếu thread khác hủy khóa ngay sau kiểm tra, `key.isReadable()`, `readyOps()` hoặc `interestOps()` vẫn có thể ném `CancelledKeyException`. Callback thực tế nên xử lý trường hợp khóa đã hết hiệu lực, lỗi I/O và phối hợp quyền sở hữu kênh.

Nếu khóa bị hủy hay interest set bị sửa **giữa lúc selection đang diễn ra**, Java cho phép hành vi phụ thuộc triển khai về việc callback có nhận khóa đó hay không; callback thậm chí có thể được gọi với **khóa invalid**. Vì thế không nên viết kiểm thử dựa vào số lần callback cố định khi cố tình tạo race ở nhiều thread.

## 5. Kết nối TCP đóng: phân biệt peer close và local close

### 5.1. Peer close không tự động đồng nghĩa SelectionKey invalid

Khi đầu bên kia đóng **đầu ghi TCP theo cách bình thường**, phía đọc có thể nhận tín hiệu **EOF**. Với `SocketChannel.read(ByteBuffer)`, EOF được biểu diễn bằng giá trị **`-1`**:

```java
if (key.isReadable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    int n = channel.read(ByteBuffer.allocate(128));

    if (n == -1) {
        key.cancel();
        channel.close();
    }
}
```

Đây là **mảnh xử lý trong callback**, cần bắt `IOException` phù hợp. `isReadable()` chỉ nói kênh sẵn sàng cho thao tác đọc, không bảo đảm đọc được byte dữ liệu dương. `read(...)` có thể trả:

- **`n > 0`**: đọc được `n` byte.
- **`n == 0`**: chưa có byte nào được đọc ở lần này (đặc biệt với non-blocking channel).
- **`n == -1`**: EOF, phía đọc của kết nối đã kết thúc.

Peer đóng kết nối **không tự đóng đối tượng `SocketChannel` bên phía bạn**. Khi đọc đến EOF, ứng dụng quyết định đóng kênh và hủy `SelectionKey` để tránh tiếp tục nhận tín hiệu OP_READ mà không còn dữ liệu. Nếu peer đóng bất thường hoặc mạng lỗi, có thể gặp `IOException` thay vì một EOF êm; cần xử lý cả hai trường hợp.

### 5.2. Local close làm khóa mất hiệu lực

Khi gọi `client.close()` trên một `SocketChannel` đã đăng ký, `SelectionKey` của nó bị hủy và `isValid()` thành **`false`. Việc loại khóa khỏi tập đăng ký hoàn thành ở một lượt select tiếp theo.

```java
client.close(); // Kênh cục bộ đóng
System.out.println(key.isValid()); // false
selector.selectNow(k -> {});       // Xử lý khóa hủy đang chờ
```

Không giả định **đóng riêng một kênh** sẽ luôn đánh thức ngay một selector đang block. Nếu đóng kênh hoặc hủy khóa ở thread khác trong vòng event loop, phối hợp gọi `selector.wakeup()` để selector trở lại và xử lý cập nhật kịp thời.

Đừng nhầm hai cấp đóng:

- `SocketChannel.close()`: đóng một kết nối/kênh, hủy những khóa đăng ký gắn với kênh.
- `Selector.close()`: đóng **toàn selector**, vô hiệu hóa các khóa còn liên quan và giải phóng tài nguyên selector. Sau đó gọi selection API sẽ ném `ClosedSelectorException`.

## 6. Chương trình kiểm thử hoàn chỉnh: wakeup, cancel và close

Chương trình sau chạy trên **Java 11+**, không cần thư viện ngoài JDK hay server ở Internet. Nó có sáu nhóm kiểm thử: `wakeup`, cancel trước select, cancel trong callback, peer đóng TCP, đóng TCP cục bộ và gọi selector sau khi đóng.

Phần TCP tạo một `ServerSocketChannel` liên kết tới **địa chỉ loopback**, một `SocketChannel` client kết nối tới đó, rồi `accept()` tạo đầu peer. Mạng ở đây chỉ nằm trên **chính máy chạy thử**; môi trường cấm binding loopback có thể từ chối test qua `IOException`.

Tạo tệp **`SelectorCallbackTests.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedSelectorException;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class SelectorCallbackTests {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static void wakeupTest() throws Exception {
        try (Selector selector = Selector.open()) {
            selector.wakeup();
            int before = selector.select(key -> {
                throw new AssertionError("No key expected");
            }, 2000);
            check(before == 0, "prearmed wakeup");
            System.out.println("wakeup before select: count=" + before);

            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                CountDownLatch started = new CountDownLatch(1);
                Future<Integer> pending = pool.submit(() -> {
                    started.countDown();
                    return selector.select(key -> {
                        throw new AssertionError("No key expected");
                    }, 5000);
                });
                check(started.await(3, TimeUnit.SECONDS), "worker not started");
                selector.wakeup();
                int result = pending.get(3, TimeUnit.SECONDS);
                check(result == 0, "wakeup count");
                System.out.println("wakeup waiting select: count=" + result);
            } finally {
                selector.wakeup();
                pool.shutdownNow();
                check(pool.awaitTermination(3, TimeUnit.SECONDS), "worker shutdown");
            }
        }
    }

    private static void cancelBeforeSelectTest() throws Exception {
        Pipe pipe = Pipe.open();
        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {
            source.configureBlocking(false);
            SelectionKey key = source.register(selector, SelectionKey.OP_READ);
            key.cancel();
            check(!key.isValid(), "cancel invalidates immediately");
            AtomicInteger callbacks = new AtomicInteger();
            selector.selectNow(k -> callbacks.incrementAndGet());
            check(callbacks.get() == 0, "cancelled key should not be selected");
            check(!selector.keys().contains(key),
                    "cancelled key should be removed after select");
            System.out.println(
                    "cancel before select: invalid=true, removed=true, callbacks=0");
        }
    }

    private static void cancelInsideCallbackTest() throws Exception {
        Pipe pipe = Pipe.open();
        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {
            source.configureBlocking(false);
            SelectionKey key = source.register(selector, SelectionKey.OP_READ);
            sink.write(ByteBuffer.wrap(new byte[] {42}));
            AtomicInteger callbacks = new AtomicInteger();
            int consumed = selector.selectNow(k -> {
                if (!k.isValid()) return;
                try {
                    int n = ((Pipe.SourceChannel) k.channel())
                            .read(ByteBuffer.allocate(1));
                    check(n == 1, "expected exactly one byte");
                    callbacks.incrementAndGet();
                    k.cancel();
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            });
            check(consumed == 1 && callbacks.get() == 1, "callback delivery");
            check(!key.isValid(), "cancel inside callback");
            selector.selectNow(k -> {
                throw new AssertionError("cancelled key delivered");
            });
            check(!selector.keys().contains(key), "eventually deregistered");
            System.out.println(
                    "cancel in callback: consumed=1, invalid=true, removed=true");
        }
    }

    private static void remoteCloseTest() throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            try (SocketChannel client = SocketChannel.open(server.getLocalAddress());
                 SocketChannel peer = server.accept()) {
                client.configureBlocking(false);
                SelectionKey key = client.register(selector, SelectionKey.OP_READ);
                peer.close();
                AtomicBoolean eof = new AtomicBoolean();
                int selected = selector.select(k -> {
                    if (!k.isValid()) return;
                    try {
                        if (k.isReadable()) {
                            int n = ((SocketChannel) k.channel())
                                    .read(ByteBuffer.allocate(1));
                            if (n == -1) {
                                eof.set(true);
                                k.cancel();
                                k.channel().close();
                            }
                        }
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                }, 5000);
                check(eof.get() && selected == 1, "peer EOF not delivered");
                check(!key.isValid() && !client.isOpen(),
                        "close and cancel after EOF");
                System.out.println(
                        "peer close: eof=true, selected=1, keyValid=false");
            }
        }
    }

    private static void localCloseTest() throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            try (SocketChannel client = SocketChannel.open(server.getLocalAddress());
                 SocketChannel peer = server.accept()) {
                client.configureBlocking(false);
                SelectionKey key = client.register(selector, SelectionKey.OP_READ);
                client.close();
                check(!key.isValid(), "close invalidates");
                selector.selectNow(k -> {
                    throw new AssertionError("closed channel should not be delivered");
                });
                check(!selector.keys().contains(key), "removed on next select");
                System.out.println("local close: keyValid=false, removed=true");
            }
        }
    }

    private static void closedSelectorTest() throws Exception {
        Selector selector = Selector.open();
        selector.close();
        boolean rejected = false;
        try {
            selector.selectNow(k -> {});
        } catch (ClosedSelectorException ex) {
            rejected = true;
        }
        check(rejected, "closed selector rejection");
        System.out.println("closed selector: ClosedSelectorException");
    }

    public static void main(String[] args) throws Exception {
        wakeupTest();
        cancelBeforeSelectTest();
        cancelInsideCallbackTest();
        remoteCloseTest();
        localCloseTest();
        closedSelectorTest();
        System.out.println("ALL TESTS PASSED");
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp; `--release 11` kiểm tra mã ở mức Java 11 trên cả các JDK mới hơn:

```bash
javac --release 11 SelectorCallbackTests.java
java SelectorCallbackTests
```

**Đầu ra đã kiểm chứng trên JDK hiện đại, biên dịch với `--release 11`:**

```text
wakeup before select: count=0
wakeup waiting select: count=0
cancel before select: invalid=true, removed=true, callbacks=0
cancel in callback: consumed=1, invalid=true, removed=true
peer close: eof=true, selected=1, keyValid=false
local close: keyValid=false, removed=true
closed selector: ClosedSelectorException
ALL TESTS PASSED
```

Mã kiểm thử dùng `check(...)` để ném `AssertionError` nếu kết quả không khớp, nên một dòng “PASSED” chỉ xuất hiện nếu **tất cả** ca đã đi qua điều kiện kiểm tra. Với môi trường hạn chế mạng loopback hoặc thread scheduling quá chậm, kiểm thử có thể thất bại do giới hạn môi trường thay vì lỗi logic của `Selector`; timeout là **giới hạn an toàn**, không phải lời hứa về thời gian phản hồi chính xác đến mili giây.

## 7. Giải thích các ca và cách tránh kiểm thử nhiễu

### Ca A — `wakeup` trước và trong lúc select

Không có channel nào đăng ký nên hai lần select đều trả `0`. Sau `wakeup()`, không phải xử lý callback nếu không có dữ liệu sẵn sàng. Có thể gọi từ thread khác và không cần sử dụng `Thread.sleep` để cố gắng canh đúng khoảnh khắc.

Trong `finally`, gọi `selector.wakeup()` thêm một lần để bảo đảm có thể giải phóng worker nếu test kết thúc bất thường, sau đó `shutdownNow()` và `awaitTermination(...)`. `Selector` được đóng bằng `try`-with-resources.

### Ca B — cancel trước select

`cancel()` làm `isValid() == false` ngay, rồi `selectNow(action)` xử lý cancelled-key set và loại khóa khỏi `selector.keys()`. Vì kênh chưa gửi byte, callback không có dữ liệu để xử lý.

### Ca C — cancel trong callback

`Pipe.SinkChannel` ghi byte `42`. `SourceChannel` được đăng ký `OP_READ` ở chế độ non-blocking. Callback nhận sự kiện đọc, lấy đúng một byte rồi hủy khóa. Sau lượt selection tiếp theo, khóa không còn nằm trong tập `keys()`. Bài kiểm thử chỉ theo dõi một khóa và một thao tác đọc, nên dễ quan sát kết quả.

### Ca D — peer đóng kết nối

Server loopback nhận kết nối rồi peer gọi `close()`. Client đang theo dõi `OP_READ`; callback đọc `-1` (EOF), đặt cờ, hủy key và đóng client. Khóa mất hiệu lực **do ứng dụng xử lý EOF và đóng kênh**, không phải chỉ vì peer đã đóng một đầu kết nối.

### Ca E — local close

`client.close()` được gọi trên kênh đã đăng ký. `SelectionKey` lập tức invalid, và `selectNow(action)` xử lý việc gỡ đăng ký; không mong callback cho khóa đã bị loại trước lượt select.

### Ca F — Selector đã đóng

Sau `selector.close()`, lệnh `selectNow(action)` gây `ClosedSelectorException`. Đóng selector cũng có tác dụng đánh thức lượt chọn đang chờ và vô hiệu hóa các khóa liên quan; đừng tiếp tục tái sử dụng đối tượng selector đã đóng.

**Lưu ý về tính xác định:** các ca này tránh tạo race tình cờ giữa hủy khóa và gọi callback. Trong ứng dụng thực, `SelectionKey` có thể bị hủy đúng thời điểm selector đang chọn và callback **có thể** được gọi với khóa invalid; đây là hành vi được Javadoc mô tả là phụ thuộc triển khai. Vì vậy, đừng ép mọi JVM/OS phải cung cấp cùng một thứ tự callback trong các bài kiểm thử race phức tạp.

## 8. Thiết kế callback an toàn trong ứng dụng thực

Một mẫu xử lý hợp lý với `SocketChannel`:

```java
// Mảnh mã bên trong event loop; cần import các lớp NIO và IOException.
selector.select(key -> {
    if (!key.isValid()) return;

    try {
        if (key.isReadable()) {
            SocketChannel channel = (SocketChannel) key.channel();
            ByteBuffer buffer = ByteBuffer.allocate(4096);
            int n = channel.read(buffer);

            if (n == -1) {
                key.cancel();
                channel.close();
            } else if (n > 0) {
                buffer.flip();
                // Chuyển dữ liệu qua bộ xử lý của ứng dụng.
            }
        }
    } catch (java.nio.channels.CancelledKeyException ignored) {
        // Key có thể đã bị hủy đồng thời giữa isValid và isReadable.
    } catch (IOException e) {
        key.cancel();
        try {
            key.channel().close();
        } catch (IOException closeError) {
            e.addSuppressed(closeError);
        }
        throw new UncheckedIOException(e);
    }
});
```

Đây là **mảnh mã minh họa**, không phải ứng dụng server hoàn chỉnh: trong sản phẩm thực, cần quản lý buffer, protocol framing, kênh ghi, backpressure và chiến lược báo lỗi. Nếu callback ném exception, exception được đưa ra caller của `select(...)`; vì vậy cần quyết định xử lý lỗi **trong callback hay ở event loop**, tránh làm dừng toàn bộ loop ngoài ý muốn.

Các nguyên tắc quan trọng:

1. **Kiểm tra `key.isValid()`** trước khi truy cập `readyOps`/`interestOps`. Tuy vậy vẫn phải tính đến race sau khi kiểm tra.
2. **Đảm bảo channel non-blocking** trước khi đăng ký: `channel.configureBlocking(false)`. Nếu đăng ký khi channel còn blocking, Java có thể ném `IllegalBlockingModeException`.
3. **Đừng lặp select trên cùng selector trong callback**. Tác vụ nặng/chờ lâu nên được thiết kế ra ngoài callback với cơ chế phối hợp thích hợp.
4. **Khi thay đổi interestOps từ thread khác**, nên gọi `wakeup()` để loop chú ý cập nhật kịp thời. Thay đổi interestOps giữa một lượt select chỉ chắc chắn ảnh hưởng tới lượt select kế tiếp.
5. **Khi hủy key hoặc đóng channel từ thread khác**, dùng `wakeup()` nếu cần loop thoát chờ ngay; bản thân cancel/close channel không phải một cơ chế đánh thức bắt buộc.
6. **Khi đóng selector**, ngừng vòng lặp và không dùng lại selector đó. `ClosedSelectorException` là dấu hiệu trạng thái vòng đời, khác lỗi dữ liệu của một kết nối đơn lẻ.
7. **Không dựa vào số thứ tự callback**; một callback có thể được gọi nhiều lần cho cùng key trong một lượt hoặc nhận key invalid do thay đổi đồng thời, theo chi tiết triển khai.

## 9. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra / xử lý |
| --- | --- | --- |
| `select(...)` vẫn chờ sau khi `cancel()` từ thread khác | Hủy khóa không đồng nghĩa đánh thức selector | Gọi `selector.wakeup()` để event loop xử lý nhanh |
| Callback không chạy sau `wakeup()` | Không có khóa sẵn sàng; wakeup chỉ đánh thức selection | Kiểm tra kết quả select và điều kiện readiness |
| `CancelledKeyException` ở `isReadable()` | Key đã bị hủy hoặc channel đóng trước khi truy cập readyOps | Kiểm tra `isValid()`, xử lý race và vòng đời |
| `ClosedSelectorException` sau `close()` | Gọi phương thức selection trên selector đã đóng | Dừng loop và tạo selector mới nếu cần |
| Không phát hiện client đóng TCP | Chỉ kiểm tra readiness, chưa đọc để phát hiện EOF | Với `OP_READ`, đọc và xử lý `n == -1`; bắt `IOException` |
| Sau EOF callback cứ chạy lại | Không đóng/hủy đăng ký kênh khi EOF | `key.cancel()`, `channel.close()` theo chính sách ứng dụng |
| `IllegalBlockingModeException` khi register | Channel chưa được đặt non-blocking | Gọi `configureBlocking(false)` trước khi `register` |
| Test lúc được lúc không | Dựa vào `Thread.sleep`, callback order hoặc thời điểm OS xử lý socket | Dùng latch/future, timeout, loopback và assert theo hợp đồng |
| Test kiểm tra số callback bằng số unique keys | `select(Consumer)` có thể gọi action nhiều lần trên cùng key | Phân biệt số callback với số unique keys được trả về |
| Vòng lặp có CPU cao hoặc không thoát | Không xử lý timeout/wakeup/EOF/cancel và lỗi I/O | Có điều kiện thoát và kiểm soát vòng đời rõ ràng |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Gọi `selector.wakeup()` khi không có kênh sẵn sàng. Callback có bắt buộc được gọi không?  
**Đáp án:** Không. `wakeup` chỉ tác động việc chờ của lượt selection; kết quả có thể bằng `0`.

**Câu 2.** Sau `key.cancel()`, `key.isValid()` là gì? Khóa có chắc biến mất ngay khỏi `selector.keys()` chưa?  
**Đáp án:** `false` ngay; việc gỡ đăng ký diễn ra trong một lượt selection kế tiếp.

**Câu 3.** Tại sao `if (key.isValid()) key.isReadable()` vẫn có thể ném `CancelledKeyException`?  
**Đáp án:** Có thể có thread khác hủy khóa **giữa hai thao tác**; việc kiểm tra không khóa toàn bộ trạng thái.

**Câu 4.** Socket có readiness đọc nhưng `read(buffer)` trả `-1` nghĩa là gì?  
**Đáp án:** EOF/đầu đọc đã tới kết thúc; ứng dụng nên xử lý đóng kết nối và hủy theo dõi nếu phù hợp.

**Câu 5.** `selector.close()` khác `socketChannel.close()` thế nào?  
**Đáp án:** Đóng selector làm toàn bộ selector không còn dùng được và vô hiệu hóa khóa liên quan; đóng riêng channel hủy đăng ký của kênh đó, không nhất thiết đóng selector.

**Câu 6.** Có nên gọi `selector.select(...)` lần nữa ngay **bên trong** callback `select(...)` cùng selector không?  
**Đáp án:** Không. Hành vi tái nhập không được đặc tả chung; có thể phát sinh deadlock hoặc hành vi phụ thuộc implementation.

**Câu 7.** Sau khi hủy key từ thread khác, muốn đánh thức vòng event loop đang chờ để cập nhật nhanh phải gọi gì?  
**Đáp án:** `selector.wakeup()`.

## 11. Ghi nhớ

Với **Selector callback trong Java 11+**, cần kiểm thử riêng:

- **`wakeup()`:** đánh thức `select` đang chờ hoặc lượt tiếp theo, **không tạo readiness giả** và không bảo đảm callback chạy.
- **`SelectionKey.cancel()`:** key mất hiệu lực **ngay**; đăng ký bị xóa trong **lượt select tiếp theo**. Khi phối hợp đa luồng, dùng `wakeup()` nếu cần phản hồi kịp thời.
- **Peer close:** kênh đọc có thể cho `read() == -1` hoặc gặp lỗi I/O; phát hiện và đóng/hủy đăng ký **do ứng dụng quyết định**, không tự đồng nhất peer close với key invalid.
- **Local channel close:** làm key invalid; selection tiếp theo hoàn tất việc gỡ đăng ký.
- **Selector.close():** vô hiệu hóa selector và các khóa còn liên quan; tiếp tục `select` sẽ ném `ClosedSelectorException`.

Một bộ test tốt dùng **loopback, latch/future, timeout và assert theo hợp đồng** thay vì giả định lịch chạy thread và thứ tự callback.

### Tài liệu chính thức (các API còn được hỗ trợ)

- [Java SE 11 — Selector: select(Consumer), selectNow(Consumer), wakeup và close](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 25 — Selector, hành vi callback và đồng bộ hóa](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 11 — SelectionKey: cancel, isValid và CancelledKeyException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Java SE 11 — SocketChannel.read: đọc EOF bằng -1](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 11 — Pipe và Pipe.SourceChannel](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Pipe.html)
