# Thay đổi interest set khi có nhiều luồng trong Java 11 Selector

**Chủ đề cha:** Selector callback  
**Phạm vi:** Java NIO, `Selector`, `SelectionKey`, thao tác cập nhật `interestOps` từ nhiều luồng, `wakeup()`, callback `select(Consumer)` và thiết kế event loop an toàn.

Một hệ thống NIO thường có một luồng chờ sự kiện trên `Selector`, trong khi nhiều worker xử lý nghiệp vụ hoặc sản sinh dữ liệu muốn gửi. Worker có thể yêu cầu bật `OP_WRITE` khi có payload mới; selector cần tắt `OP_WRITE` khi đã gửi hết. Ở chiều nhận, hệ thống có thể tạm tắt `OP_READ` khi quá tải và bật lại sau khi worker xử lý xong.

Vấn đề không nằm ở một phép OR đơn giản. Các luồng có thể cập nhật cùng một `SelectionKey` trong lúc `select()` đang chờ, callback đang chạy, hoặc connection đã đóng. Để ứng dụng đúng, cần hiểu **interest set**, **ready set**, thời điểm selector nhận thấy thay đổi, tính nguyên tử của phép cập nhật và cách đánh thức vòng lặp. Java 11 bổ sung những API vẫn hữu ích trên JDK hiện đại: `SelectionKey.interestOpsOr(int)`, `interestOpsAnd(int)` và các overload `Selector.select(Consumer<SelectionKey>)`.

## 1. Các khái niệm cần phân biệt

Mỗi `SelectionKey` đại diện cho việc đăng ký một `SelectableChannel` với một `Selector`. Key chứa hai mặt nạ bit quan trọng:

| Tập | API | Ý nghĩa | Thay đổi bởi |
|---|---|---|---|
| **Interest set** | `key.interestOps()` | Những thao tác I/O mà ứng dụng muốn theo dõi | Ứng dụng qua `interestOps(int)`, `interestOpsOr`, `interestOpsAnd` |
| **Ready set** | `key.readyOps()`, `key.isReadable()`, `key.isWritable()` | Những thao tác mà selector vừa phát hiện là sẵn sàng | Selection operation; ứng dụng không trực tiếp ghi ready set |

Cần thêm một tập thứ ba ở mức ứng dụng: **trạng thái nghiệp vụ của kết nối**, chẳng hạn output queue còn dữ liệu, protocol parser đang chờ bao nhiêu byte, kết nối đang đóng hay worker có sẵn sàng nhận việc mới không. Một bit interest **không thay thế** trạng thái nghiệp vụ đó.

Các bit thường gặp:

| Bit | Loại channel phù hợp | Tình huống |
|---|---|---|
| `SelectionKey.OP_READ` | `SocketChannel`, `Pipe.SourceChannel` | Theo dõi khả năng đọc |
| `SelectionKey.OP_WRITE` | `SocketChannel`, `Pipe.SinkChannel` | Còn dữ liệu cần gửi, đợi khả năng ghi tiếp |
| `SelectionKey.OP_CONNECT` | `SocketChannel` | Đợi kết nối non-blocking hoàn thành |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | Nhận kết nối mới |

Phải chọn bit theo `channel.validOps()`. Gọi `interestOpsOr(OP_ACCEPT)` trên `SocketChannel` là không hợp lệ và sẽ ném `IllegalArgumentException`. Với `Pipe.SourceChannel` chỉ dùng `OP_READ`.

**Interest không phải readiness.** Ví dụ key có `OP_READ` ngay khi đăng ký vẫn có thể có `readyOps() == 0`, vì chưa có selection nào báo dữ liệu sẵn sàng. Readiness cũng chỉ là gợi ý của thời điểm phát hiện, không bảo đảm mọi lần `read` hoặc `write` sau đó sẽ hoàn thành ngay.

## 2. Quy tắc thời gian khi nhiều luồng cùng sử dụng Selector

Tài liệu Java SE 11 đưa ra các quy tắc vẫn đúng với Java hiện đại:

1. Một `SelectionKey` an toàn để nhiều luồng sử dụng theo hợp đồng của class. Tuy vậy, quyết định trạng thái nghiệp vụ và các object trong `attachment()` vẫn phải do ứng dụng đồng bộ.
2. Một selection operation sử dụng interest set ở **thời điểm operation bắt đầu**. Thay đổi interest trong lúc selection đang tiến hành không ảnh hưởng lượt đó; nó được xét ở **lượt selection kế tiếp**.
3. `Selector` và `selector.keys()` hỗ trợ truy cập nhiều luồng, nhưng `selector.selectedKeys()` **không phải** concurrent set để tùy tiện sửa/duyệt từ nhiều thread.
4. Các luồng khác có thể `key.cancel()` hoặc close channel bất cứ lúc nào. Việc key đang có trong một tập của selector không chứng minh key còn `isValid()` hoặc channel vẫn mở.
5. `selector.wakeup()` làm selection đang chặn trở về, hoặc làm lần selection kế tiếp trở về ngay nếu chưa có selection đang chờ; nhiều lần wakeup trước một lượt selection được gộp tác dụng.

Hãy hình dung:

```text
Selector thread                         Worker thread
---------------                         -------------
select() bắt đầu với OP_READ
                                        Thêm payload vào output queue
                                        Yêu cầu bật OP_WRITE
                                        selector.wakeup()
select() trở về (có thể 0 key)
Đọc yêu cầu, cập nhật interest
Bắt đầu lượt select tiếp theo
Sử dụng OP_READ + OP_WRITE
Callback nhận readiness mới
```

Không khẳng định callback của **lượt select đang diễn ra** nhìn thấy bit `OP_WRITE` vừa thay đổi. Thay đổi có hiệu lực ở lượt tiếp theo theo hợp đồng API. `wakeup()` giúp vòng lặp sớm có cơ hội bắt đầu lượt tiếp theo; nó không tự cấp dữ liệu, không biến channel thành ready và không tự gọi callback.

### Bật OP_WRITE không đồng nghĩa ghi xong

`key.interestOpsOr(OP_WRITE)` chỉ đăng ký quan tâm. Khi callback báo writable, `SocketChannel.write(buffer)` có thể chỉ ghi **một phần** hoặc trả 0 với channel non-blocking. Phải giữ `ByteBuffer` còn dở, tiếp tục ghi khi sẵn sàng và tắt WRITE khi queue thực sự rỗng.

## 3. Ba phép thay đổi interest set

### 3.1 Thay toàn bộ mask bằng `interestOps(int)`

```java
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
```

Phù hợp khi một luồng duy nhất quản lý interest hoặc code đã kiểm soát thứ tự cập nhật. Phương thức **thay toàn bộ mask**, nên mẫu đọc-sửa-ghi sau dễ bị mất cập nhật nếu nhiều worker cùng thao tác:

```java
// Dễ tạo lost update nếu nhiều luồng chạy đồng thời:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
```

Ví dụ A và B đều đọc mask cũ `0`. A tính `OP_READ`, B tính `OP_WRITE`; nếu B ghi sau A, kết quả có thể chỉ còn WRITE. Tính hợp lệ của từng lời gọi **không** làm chuỗi “đọc rồi ghi” trở nên nguyên tử.

### 3.2 Bật các bit bằng `interestOpsOr(int)`

```java
int before = key.interestOpsOr(SelectionKey.OP_WRITE);
```

Phương thức từ Java 11 thực hiện OR với mask hiện tại theo cách nguyên tử đối với những lời gọi `interestOpsOr` và `interestOpsAnd` đồng thời. Nó giữ các bit khác. Biến `before` nhận **mask cũ**, không phải mask sau cập nhật. Bit không nằm trong `channel.validOps()` gây `IllegalArgumentException`. Key đã cancel gây `CancelledKeyException`.

### 3.3 Tắt các bit bằng `interestOpsAnd(int)`

```java
int before = key.interestOpsAnd(~SelectionKey.OP_WRITE);
```

Phép AND với phần bù của WRITE **xóa riêng OP_WRITE**, không chạm bit READ hay CONNECT đang có. `before` cũng là mask cũ. `interestOpsAnd` không ném `IllegalArgumentException` chỉ vì mask AND có bit không được channel hỗ trợ; API cho phép `~OP_WRITE` để xóa bit. Key bị cancel vẫn gây `CancelledKeyException`.

**Giới hạn của tính nguyên tử:** `interestOpsOr/And` bảo toàn những lần bật/tắt bit trong các phép tương ứng, nhưng không quyết định **điều kiện nghiệp vụ** khi một luồng muốn bật WRITE còn luồng khác muốn tắt WRITE. Kết quả cuối phụ thuộc thứ tự hai thao tác. Khi dữ liệu xếp hàng và quyết định bật/tắt phải nhất quán, tốt hơn để một event-loop owner quản lý cả output queue và interest.

Cũng không được mặc định rằng `interestOps(int)` ghi đè mask là nguyên tử theo đúng cùng giao dịch với mọi lời gọi Or/And; Javadoc chỉ cam kết nguyên tử cho Or/And **với nhau**.

## 4. Phối hợp worker và selector.wakeup()

Có hai hướng áp dụng.

**Hướng A — nhiều luồng cập nhật bit độc lập:** worker đưa dữ liệu vào queue an toàn, gọi `key.interestOpsOr(OP_WRITE)` rồi `selector.wakeup()`. Phù hợp khi app có ownership và lifecycle rõ ràng, không có race làm mất quyết định về queue; cần xử lý key bị cancel. Đây là trích đoạn, yêu cầu các biến `key`, `selector` hợp lệ:

```java
outboundQueue.add(payload);
key.interestOpsOr(SelectionKey.OP_WRITE);
selector.wakeup();
```

**Hướng B — worker gửi lệnh, một luồng sở hữu selector thực thi:** worker không trực tiếp sửa key, chỉ thêm task vào hàng đợi an toàn, rồi gọi wakeup. Selector thread lấy các task trước mỗi lần `select`:

```java
// Worker:
commands.add(() -> key.interestOpsOr(SelectionKey.OP_WRITE));
selector.wakeup();
```

```java
// Selector thread (trích đoạn cấu trúc):
while (running) {
    Runnable command;
    while ((command = commands.poll()) != null) {
        command.run();
    }
    if (!running) break;
    selector.select(callback);
}
```

Các đoạn này **không phải chương trình độc lập**: biến `outboundQueue`/`payload`/`commands`/`running`/`selector`/`callback` phải được khai báo cùng chính sách thread-safety. Chương trình hoàn chỉnh ở mục 5 dùng hướng B.

**Thứ tự yêu cầu đúng:** enqueue rồi `wakeup()`. Nếu wakeup xảy ra trước khi event loop đi vào `select`, API cho phép lần select kế tiếp trở về ngay (trừ khi một `selectNow` đã tiêu thụ tác dụng wakeup giữa chừng). Điều này ngăn race đi ngủ ngay sau khi worker gửi task.

**Đừng đếm wakeup:** nhiều lần gọi `wakeup` giữa hai lượt selection có cùng tác dụng như một lần. Hàng đợi chứa tác vụ, không phải bộ đếm wakeup. `select()` có thể trở về với số key bằng 0, hoàn toàn bình thường sau wakeup.

## 5. Ví dụ chạy được — queue và selector callback trên hai luồng

Chương trình sử dụng `Pipe`, tránh phụ thuộc mạng, và `select(Consumer<SelectionKey>)` có từ Java 11. `Pipe.SourceChannel` theo dõi `OP_READ`. Main đóng vai worker: enqueue lệnh bật READ, đánh thức selector, đợi xác nhận lệnh được thực thi rồi gửi byte 65. Callback đọc byte, tắt READ và báo hoàn thành. Các latch giúp kiểm thử đúng thứ tự; timeout 5 giây chỉ là giới hạn chẩn đoán nếu có lỗi, **không phải độ trễ mà thuật toán dựa vào**.

Lưu thành **`SelectorInterestDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class SelectorInterestDemo {
    static void await(CountDownLatch latch, String step)
            throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout: " + step);
        }
    }

    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();
        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);
            SelectionKey key = source.register(selector, 0);

            Queue<Runnable> commands = new ConcurrentLinkedQueue<>();
            AtomicBoolean running = new AtomicBoolean(true);
            AtomicReference<Throwable> failure = new AtomicReference<>();
            CountDownLatch enabled = new CountDownLatch(1);
            CountDownLatch received = new CountDownLatch(1);

            Thread eventLoop = new Thread(() -> {
                try {
                    while (running.get()) {
                        Runnable command;
                        while ((command = commands.poll()) != null) {
                            command.run();
                        }
                        if (!running.get()) break;

                        selector.select(selected -> {
                            if (!selected.isValid() || !selected.isReadable()) {
                                return;
                            }
                            ByteBuffer data = ByteBuffer.allocate(8);
                            try {
                                int count = source.read(data);
                                if (count > 0) {
                                    System.out.println("received="
                                            + Byte.toUnsignedInt(data.get(0)));
                                    selected.interestOpsAnd(
                                            ~SelectionKey.OP_READ);
                                    received.countDown();
                                }
                            } catch (IOException ex) {
                                throw new UncheckedIOException(ex);
                            }
                        });
                    }
                } catch (Throwable error) {
                    failure.set(error);
                    enabled.countDown();
                    received.countDown();
                }
            }, "selector-loop");
            eventLoop.start();

            try {
                commands.add(() -> {
                    key.interestOpsOr(SelectionKey.OP_READ);
                    System.out.println("read-enabled="
                            + ((key.interestOps() & SelectionKey.OP_READ) != 0));
                    enabled.countDown();
                });
                selector.wakeup();

                await(enabled, "enable");
                if (failure.get() != null) {
                    throw new IllegalStateException(failure.get());
                }

                sink.write(ByteBuffer.wrap(new byte[]{65}));
                await(received, "receive");
                if (failure.get() != null) {
                    throw new IllegalStateException(failure.get());
                }
                System.out.println("read-enabled-after="
                        + ((key.interestOps() & SelectionKey.OP_READ) != 0));
            } finally {
                running.set(false);
                selector.wakeup();
                eventLoop.join(5000);
            }

            if (eventLoop.isAlive()) {
                throw new IllegalStateException("Event loop did not stop");
            }
            System.out.println("selected-keys="
                    + selector.selectedKeys().size());
        }
    }
}
```

Biên dịch và chạy trên JDK 11 hoặc JDK mới hơn còn hỗ trợ `--release 11`:

```bash
javac --release 11 -encoding UTF-8 SelectorInterestDemo.java
java SelectorInterestDemo
```

Kết quả chương trình khi hoàn thành bình thường:

```text
read-enabled=true
received=65
read-enabled-after=false
selected-keys=0
```

**Giải thích:**

1. `source.register(selector, 0)` đăng ký source non-blocking nhưng chưa theo dõi sự kiện nào.
2. Task bật `OP_READ` được chạy trên selector thread; latch `enabled` xác nhận trước khi main gửi byte 65.
3. Callback của `select(Consumer)` nhận key đã ready, đọc được byte 65, sau đó gọi `interestOpsAnd(~OP_READ)`.
4. Lần selection sau không theo dõi READ cho key này cho đến khi ứng dụng bật lại. Main chỉ in `read-enabled-after=false` sau khi callback đếm `received`.
5. `selected-keys=0` vì overload callback **không thêm** key vào `selectedKeys()`. Main chỉ đọc kích thước tập sau khi eventLoop đã kết thúc để tránh truy cập đồng thời.
6. Khối `finally` chuyển `running` thành false, wakeup selector và `join` để đóng tài nguyên đúng thứ tự.

Ví dụ xử lý một byte để có stdout chính xác. Trong hệ thống thật, cần xử lý buffer chưa đọc hết, EOF, lỗi I/O, callback lặp và shutdown khi không còn kết nối; đừng lấy cách cấp phát một `ByteBuffer` mỗi callback làm tối ưu mặc định.

## 6. Ví dụ chạy được — hai worker thay đổi hai bit đồng thời

Ví dụ tiếp theo kiểm tra riêng **tính nguyên tử của mask**, không thực hiện kết nối TCP hay I/O. `SocketChannel` được tạo ở chế độ non-blocking, đăng ký interest 0; hai worker bật READ và WRITE gần đồng thời bằng `interestOpsOr`. Chúng không dùng `interestOps(key.interestOps() | bit)` nên không ghi đè bit của nhau.

Lưu thành **`AtomicInterestDemo.java`**:

```java
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.SocketChannel;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicInterestDemo {
    static Thread adder(String name, SelectionKey key, int operation,
                        CountDownLatch ready, CountDownLatch start,
                        AtomicReference<Throwable> failure) {
        return new Thread(() -> {
            try {
                ready.countDown();
                if (!start.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Start timeout");
                }
                key.interestOpsOr(operation);
            } catch (Throwable ex) {
                failure.compareAndSet(null, ex);
            }
        }, name);
    }

    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             SocketChannel channel = SocketChannel.open()) {
            channel.configureBlocking(false);
            SelectionKey key = channel.register(selector, 0);

            CountDownLatch ready = new CountDownLatch(2);
            CountDownLatch start = new CountDownLatch(1);
            AtomicReference<Throwable> failure = new AtomicReference<>();

            Thread read = adder("enable-read", key, SelectionKey.OP_READ,
                    ready, start, failure);
            Thread write = adder("enable-write", key, SelectionKey.OP_WRITE,
                    ready, start, failure);

            read.start();
            write.start();
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers not ready");
            }
            start.countDown();
            read.join(5000);
            write.join(5000);
            if (read.isAlive() || write.isAlive() || failure.get() != null) {
                throw new IllegalStateException("Worker failure",
                        failure.get());
            }

            int expected = SelectionKey.OP_READ | SelectionKey.OP_WRITE;
            if (key.interestOps() != expected) {
                throw new AssertionError("Lost interest bit");
            }
            System.out.println("both-bits=true");

            int old = key.interestOpsAnd(~SelectionKey.OP_WRITE);
            System.out.println("previous-had-write="
                    + ((old & SelectionKey.OP_WRITE) != 0));
            System.out.println("read-only="
                    + (key.interestOps() == SelectionKey.OP_READ));

            try {
                key.interestOpsOr(SelectionKey.OP_ACCEPT);
                throw new AssertionError("OP_ACCEPT unexpectedly accepted");
            } catch (IllegalArgumentException expectedError) {
                System.out.println("unsupported-op-rejected=true");
            }
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 AtomicInterestDemo.java
java AtomicInterestDemo
```

```text
both-bits=true
previous-had-write=true
read-only=true
unsupported-op-rejected=true
```

Lệnh bật READ và WRITE có thể chạy theo thứ tự nào cũng được; vì chỉ OR với các bit khác nhau nên kết quả cuối phải có **cả hai**. `old` của `interestOpsAnd` chứa WRITE, dù mask sau lệnh chỉ còn READ. Cuối cùng, `OP_ACCEPT` bị từ chối vì không thuộc validOps của SocketChannel.

Không suy từ kết quả này rằng socket đã sẵn sàng đọc hoặc ghi. Trong demo, socket chưa kết nối và **không gọi `select`**; đây chỉ là kiểm thử độc lập về thao tác interest set. Muốn selector đang block nhận thấy thay đổi sớm, vẫn cần chiến lược `wakeup`.

## 7. Key bị cancel: kiểm tra state và xử lý lỗi

`key.cancel()` khiến key lập tức invalid. Channel close hoặc selector close cũng làm key invalid; việc deregister hoàn tất trong selection operation. Một worker có thể đang giữ key của connection đã đóng, nên cần kiểm soát task đến muộn.

Ví dụ chạy độc lập — **`KeyStateDemo.java`**:

```java
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;

public class KeyStateDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();
        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {
            source.configureBlocking(false);
            SelectionKey key = source.register(selector, SelectionKey.OP_READ);

            System.out.println("initial-read-interest="
                    + ((key.interestOps() & SelectionKey.OP_READ) != 0));
            System.out.println("initial-ready-ops=" + key.readyOps());

            key.interestOpsAnd(~SelectionKey.OP_READ);
            System.out.println("after-disable=" + key.interestOps());

            key.cancel();
            System.out.println("valid-after-cancel=" + key.isValid());

            try {
                key.interestOpsOr(SelectionKey.OP_READ);
                throw new AssertionError("Expected CancelledKeyException");
            } catch (java.nio.channels.CancelledKeyException expected) {
                System.out.println("cancelled-update-rejected=true");
            }
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 KeyStateDemo.java
java KeyStateDemo
```

```text
initial-read-interest=true
initial-ready-ops=0
after-disable=0
valid-after-cancel=false
cancelled-update-rejected=true
```

`readyOps() == 0` ban đầu là đúng: key mới được đăng ký có ready set rỗng dù interest chứa READ. `isValid()` giúp tránh thao tác trên key đã hủy, nhưng một luồng khác vẫn có thể cancel **ngay sau khi kiểm tra**; không dùng check-valid làm bảo đảm vĩnh viễn. Nên quản lý lifecycle kết nối ở owner thread và xử lý `CancelledKeyException` của task đến muộn theo chính sách, thay vì làm chết cả event loop.

## 8. Callback `select(Consumer)` và các giới hạn đồng thời

Java 11 bổ sung các overload:

- `selector.select(Consumer<SelectionKey> action)`.
- `selector.select(Consumer<SelectionKey> action, long timeout)`.
- `selector.selectNow(Consumer<SelectionKey> action)`.

Các lệnh này chạy action cho key sẵn sàng, **không thêm key vào selected-key set**. Một key có thể khiến action chạy **nhiều lần trong một selection** nếu có nhiều loại readiness được phân phối thành các tập bit khác nhau. Callback phải xử lý đúng bit trên từng lần gọi, không ngầm giả định “mỗi key chính xác một callback”.

**Vấn đề khóa:** Tài liệu Java 11 cho biết action của `select(Consumer)` được thực thi khi đang đồng bộ trên chính selector và selected-key set. Vì vậy:

1. Giữ callback ngắn, tránh gọi HTTP blocking, DB transaction, `Future.get()`, `Thread.join()` hoặc công việc CPU nặng trong callback.
2. Không gọi `select(...)` **lồng trên cùng selector** trong action; thao tác selection không có hợp đồng reentrant tổng quát và có thể có hành vi phụ thuộc triển khai.
3. Tránh lock-order inversion: worker cầm khóa ứng dụng A rồi đợi selector, trong khi callback cầm khóa selector và đợi A. Hàng đợi công việc bất đồng bộ thường rõ ràng hơn.
4. Callback **được phép** thay interest, cancel key hoặc close channel, nhưng không phải mọi readiness đã được chuẩn bị trước đều lập tức biến mất; kiểm tra trạng thái thực tế.
5. `SelectionKey.attachment()` có thể chứa object connection state, nhưng field mutable trong attachment **không tự động an toàn luồng**. Dùng thread confinement, immutable message hoặc đồng bộ có chủ đích.

Đừng coi số lần callback bằng số lần `wakeup`. Wakeup chỉ làm selection trở về; callback được gọi khi channel sẵn sàng theo interest. Khi không có ready channel, lượt `select` có thể trở về với 0.

## 9. Áp dụng cho OP_WRITE và backpressure

### 9.1 Bật WRITE đúng lúc

Socket thường báo writable khi có chỗ trong send buffer. Nếu `OP_WRITE` luôn bật dù không có payload cần gửi, event loop có thể liên tục nhận readiness và chạy vòng lặp vô ích, làm CPU cao.

Một state machine thường dùng:

1. **Queue rỗng:** `OP_WRITE` tắt.
2. **Worker có payload:** enqueue payload theo thứ tự và cơ chế công bố an toàn.
3. **Yêu cầu cập nhật:** queue command bật `OP_WRITE` cho owner thread; gọi `wakeup()`.
4. **Callback writable:** ghi từ buffer đầu queue. Một lần `channel.write(buffer)` có thể ghi một phần hoặc trả 0; giữ buffer chưa hoàn thành.
5. **Còn dữ liệu:** tiếp tục theo dõi WRITE. **Không còn dữ liệu:** tắt WRITE.

Để tránh race “worker vừa enqueue nhưng callback tắt WRITE theo ảnh chụp queue cũ”, đặt quyết định enqueue/enable và drain/disable dưới một hợp đồng thứ tự rõ ràng, lý tưởng để selector owner quản lý cả queue và bit. `interestOpsOr/And` đảm bảo phép bit atomic, **không** tự bảo đảm state machine mạng đúng.

### 9.2 Tạm dừng và khôi phục READ

Khi worker pool quá tải, một kết nối có thể được tạm tắt `OP_READ`. Khi worker đã tiêu thụ xong công việc và cho phép nhận thêm, enqueue task bật `OP_READ`, gọi wakeup. Điều này là một cơ chế **backpressure** ở tầng ứng dụng.

Tắt READ **không** xóa byte đã có trong socket buffer hoặc bắt peer lập tức dừng gửi. Parser phải giữ dữ liệu đã đọc dở và cơ chế protocol framing, không đọc mất ranh giới message. Khi giới hạn buffer của hệ điều hành bị lấp, flow control mạng mới có thể khiến peer chậm lại.

### 9.3 Đóng connection trong khi worker còn task

Trường hợp khó là key bị cancel trong callback, nhưng worker hoàn thành muộn và gửi lệnh bật WRITE. Event-loop owner cần biết connection đã `CLOSING/CLOSED` để bỏ qua task hoặc báo lỗi có nghĩa. Nếu vẫn chạm `interestOps` có thể ném `CancelledKeyException`; xử lý lỗi đó tại biên thao tác và ghi nhận nguyên nhân, không nuốt mọi exception một cách im lặng.

Với nhiều luồng gửi vào cùng queue, thứ tự được xác định bởi thời điểm enqueue thực tế; nếu nghiệp vụ yêu cầu thứ tự theo sequence ID, thiết kế sequence/check version rõ. Atomic bit mask không thể thay thế thứ tự message.

## 10. Kiểm thử đồng thời có ý nghĩa

Đừng dùng `Thread.sleep(100)` rồi hy vọng worker và selector “đã kịp chạy”. Dùng latch/barrier hoặc điểm xác nhận trạng thái để kiểm soát điều kiện test. Ma trận cần bao gồm:

| Ca | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Hai worker cùng thêm READ và WRITE | `interestOpsOr` từ hai thread | Hai bit cùng tồn tại |
| Tắt một bit | Mask READ và WRITE, rồi `interestOpsAnd(~WRITE)` | READ còn, WRITE mất |
| Gọi bit không hợp lệ | OP_ACCEPT trên SocketChannel | `IllegalArgumentException` |
| Key đã cancel | `cancel` rồi `interestOpsOr` | `CancelledKeyException` |
| Chưa select | Key có READ interest | `readyOps() == 0` |
| Enqueue rồi wakeup | Selector đang chờ | Task được xử lý, có thể không có ready key |
| Worker đổi interest khi select chạy | Thay mask và wakeup | Lượt selection kế tiếp xét interest mới |
| Worker gửi nhiều payload | Queue và WRITE bật/tắt | Không mất message, không busy-spin |
| Kênh chỉ ghi một phần | `write` trả số byte nhỏ hơn `remaining` | Buffer còn lại được giữ đúng |
| Worker hoàn thành sau close | Task muộn cho key invalid | Không phá event loop; xử lý theo chính sách |
| Shutdown khi selector block | Đổi running, wakeup, join | Event loop dừng và resource được đóng |

Một test ổn định nên xác minh **kết quả nghiệp vụ**, không cố định lịch scheduler: lệnh select có thể trả 0 sau wakeup; readiness có thể được báo ở vòng lặp khác; thời điểm hoàn tất I/O không có cam kết real-time. Timeout trong test chỉ giúp nhận biết tình trạng treo/hỏng, không phải công cụ xác định thứ tự.

`Pipe` hữu ích cho test READ không cần mạng; `SocketChannel` có thể được dùng để xác minh mask READ/WRITE hợp lệ; bài test tích hợp TCP cần quản lý tài nguyên và kết nối thực theo hợp đồng.

## 11. Lỗi phổ biến

| Lỗi | Tác động | Cách xử lý |
|---|---|---|
| `key.interestOps(key.interestOps() | bit)` từ nhiều luồng | Lost update, mất bit của luồng khác | Dùng `interestOpsOr/And` hoặc owner thread |
| Tưởng đổi bit tác động ngay select hiện tại | Readiness không như dự tính | Thiết kế lượt select kế tiếp |
| Quên wakeup khi cần phản hồi nhanh | Selector vẫn block với interest cũ | Enqueue/thay mask rồi wakeup |
| Dùng wakeup như queue sự kiện | Tín hiệu bị gộp, không chứa payload | Queue/state là nguồn dữ liệu |
| Nhầm `readyOps` với `interestOps` | Kiểm tra sai thứ ứng dụng đăng ký | Đọc đúng mask và phân biệt readiness |
| Để WRITE bật suốt vòng đời | Callback liên tục, CPU cao | Chỉ bật khi có output pending |
| Tự ý duyệt `selectedKeys()` từ worker | Tập không thread-safe | Dùng callback hoặc đồng bộ đúng API |
| Block hoặc gọi select lồng trong callback | Deadlock/hành vi không xác định | Callback ngắn, gửi việc sang worker |
| Tin tuyệt đối `isValid()` trước khi update | Key có thể bị cancel ngay sau check | Ownership rõ, xử lý lỗi key invalid |
| Dùng bit không nằm trong `validOps()` | `IllegalArgumentException` | Kiểm tra loại channel và mask |
| Worker sửa `ByteBuffer` đang được selector gửi | Race position/nội dung, hỏng message | Chuyển ownership hoặc đồng bộ |
| Ghi tất cả bytes trong một `write` | Bỏ sót dữ liệu khi partial write | Duy trì buffer và OP_WRITE |
| Nuốt mọi exception từ callback | Khó điều tra, có thể mất kết nối âm thầm | Xử lý và ghi nhận lỗi cụ thể |

## 12. Bài tập tự kiểm tra (có đáp án)

**1.** Hai luồng cùng đọc interest ban đầu `0`; một luồng định bật READ, luồng kia WRITE, rồi cả hai gọi `interestOps(int)`. Vì sao kết quả có thể thiếu một bit?  
**Đáp án:** cả hai thao tác cùng dựa trên mask cũ, lệnh set cuối ghi đè toàn mask. Dùng `interestOpsOr` hoặc thực thi tuần tự ở owner.

**2.** Cần xóa WRITE mà vẫn giữ READ, CONNECT nếu có. Viết gì?  
**Đáp án:** `key.interestOpsAnd(~SelectionKey.OP_WRITE)`. Phương thức trả **mask cũ**.

**3.** Worker bật READ khi selector đang trong `select`. Có bắt buộc callback của lượt đó thấy READ không?  
**Đáp án:** không. Interest mới được xét ở lượt selection tiếp theo.

**4.** Worker gọi `selector.wakeup()` nhưng `select()` trả 0. Có lỗi không?  
**Đáp án:** không. Wakeup không tạo ready channel. Event loop vẫn phải lấy task và xử lý request.

**5.** Vì sao OP_WRITE thường được tắt khi output queue rỗng?  
**Đáp án:** writable readiness có thể xuất hiện liên tục, dẫn đến vòng lặp bận.

**6.** `key.isValid()` trả true, ngay sau đó `interestOpsOr` ném `CancelledKeyException`. Có mâu thuẫn không?  
**Đáp án:** không. Luồng khác có thể cancel key giữa hai lệnh; đó là race check-then-act.

**7.** Khi dùng `select(Consumer)`, có chắc callback chỉ chạy một lần trên mỗi key trong một lượt không?  
**Đáp án:** không; ready của nhiều thao tác có thể được phân phối thành nhiều lần callback. Không gắn logic vào giả định một callback duy nhất.

**8.** Callback có nên chờ worker qua `Future.get()` nếu worker cần event loop làm một việc trước?  
**Đáp án:** không. Callback giữ khóa liên quan selection, và chờ ngược có thể deadlock. Chuyển việc bất đồng bộ, khi worker hoàn tất thì enqueue task và wakeup.

**9.** Hai phép `interestOpsOr(OP_WRITE)` và `interestOpsAnd(~OP_WRITE)` là atomic, liệu đủ để bảo đảm không bỏ lỡ lần gửi mới?  
**Đáp án:** chưa đủ. Chúng atomic về mask, nhưng có thể mâu thuẫn với thứ tự enqueue/disable. Cần quản lý cả state queue và bit theo một hợp đồng thứ tự.

## 13. Tài liệu chuẩn còn áp dụng

- [Java SE 11 — Selector](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html): concurrency, `wakeup`, `select(Consumer)` và tập key.
- [Java SE 11 — SelectionKey](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready, `interestOpsOr`, `interestOpsAnd`, `cancel`, các bit OP_*.
- [Java SE 11 — SelectableChannel](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectableChannel.html): `validOps`, `register`, non-blocking.
- [Java SE 11 — Pipe](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Pipe.html): tạo nguồn sự kiện để kiểm thử.
- [Java SE 11 — SocketChannel](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SocketChannel.html): READ/WRITE/CONNECT và partial I/O.
- [Java SE 11 — ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): truyền task giữa các thread.

**Nguyên tắc thực hành:** Quy định rõ **ai công bố dữ liệu**, **ai quyết định interest** và **khi nào đánh thức selector**. Với các bit độc lập, dùng phép atomic Java 11; với trạng thái kết nối và thứ tự message, để selector owner xử lý queue rồi gọi selection theo vòng lặp là lựa chọn dễ kiểm soát.