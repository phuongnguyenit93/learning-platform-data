# Java 11+ — `Selector.select` có timeout và xử lý callback

## 1. Bài toán: đợi I/O có giới hạn, rồi xử lý `SelectionKey`

Trong Java NIO, `java.nio.channels.Selector` cho phép một luồng theo dõi các `SelectableChannel` đã đăng ký để biết kênh nào có thể đọc, ghi, kết nối hoặc chấp nhận kết nối. Khi có I/O sẵn sàng, một `SelectionKey` mang thông tin về kênh, tập thao tác quan tâm (`interestOps`), tập thao tác sẵn sàng (`readyOps`) và trạng thái đăng ký.

Từ **Java 11**, `Selector` có overload cho phép **đợi tối đa khoảng thời gian chỉ định và xử lý key sẵn sàng trực tiếp trong callback**:

```java
int count = selector.select(key -> {
    // Xử lý trạng thái sẵn sàng của key.
}, 1_000L);
```

Đây là `select(Consumer<SelectionKey> action, long timeout)`:

- `action` là `Consumer<SelectionKey>`; có thể viết bằng lambda hoặc method reference, được gọi **đồng bộ** trong lời gọi `select`.
- `timeout` là thời gian chờ tính bằng **mili giây (milliseconds)**.
- `count` là **số key duy nhất được tiêu thụ**, có thể bằng 0. Nó không nhất thiết bằng số lần chạy callback.
- Phương thức có thể ném `IOException` khi quá trình selection gặp lỗi I/O; callback có thể truyền exception của mình ra caller.

Khác với `select(long timeout)` không callback, phiên bản này chuyển key sẵn sàng đến `action.accept(key)`. Nó là API Java 11 tiếp tục được duy trì trong các bản Java hiện đại, không phải kỹ thuật legacy cần thay thế.

## 2. Quy tắc timeout: dương, bằng 0 và âm

Đây là quy tắc quan trọng nhất của `select(action, timeout)`:

| `timeout` | Ý nghĩa | Kết quả |
| --- | --- | --- |
| **`> 0`** | Đợi kênh sẵn sàng **tối đa khoảng** `timeout` mili giây, trừ khi có điều kiện kết thúc khác sớm hơn. | Có thể trả 0 khi hết hạn hoặc được đánh thức mà không có key; có thể trả số dương khi có key phù hợp. |
| **`== 0`** | **Chờ vô thời hạn** (until ready, `wakeup()`, interrupt hoặc đóng selector). | Không phải “thử một lần không chặn”; có thể ở trạng thái chờ rất lâu. |
| **`< 0`** | Đối số không hợp lệ. | Ném **`IllegalArgumentException`**. |

Lưu ý đặc biệt: **`selector.select(action, 0L)` KHÔNG tương đương `selector.selectNow(action)`**.

```java
// Chờ tối đa khoảng 250 ms:
int ready = selector.select(key -> handle(key), 250L);

// Chờ vô thời hạn:
int indefinitely = selector.select(key -> handle(key), 0L);

// Thăm dò I/O ngay, không đợi kênh mới sẵn sàng:
int immediate = selector.selectNow(key -> handle(key));
```

Ba dòng trên là đoạn minh họa, không chạy độc lập vì cần `selector`, `handle` và vòng đời tài nguyên. Trong ứng dụng thật, chọn **một chiến lược** phù hợp, không gọi cả ba liên tiếp chỉ để chứng minh hành vi.

### Timeout không phải đồng hồ thời gian thực tuyệt đối

Javadoc nêu rõ phương thức không bảo đảm **real-time timing**. Khoảng chờ thực tế có thể bị ảnh hưởng bởi lập lịch của hệ điều hành, độ trễ JVM, trạng thái đồng bộ hoặc công việc khác trong callback. Timeout dùng để **giới hạn thời gian chờ readiness**, không phải giới hạn thời gian **toàn bộ phương thức** bao gồm callback.

Nếu callback mất 5 giây để xử lý key, một lời gọi `select(action, 100L)` vẫn có thể mất hơn 100 ms. Do đó không dùng kết quả đo milliseconds từ một lần chạy để kết luận JDK vi phạm timeout.

## 3. Những điều kiện khiến `select` quay về sớm

Với timeout dương, selector có thể kết thúc bước chờ khi gặp một trong các điều kiện:

1. Có ít nhất một channel được chọn theo `interestOps` của key.
2. Một luồng khác gọi `selector.wakeup()`.
3. Luồng đang chờ bị interrupt.
4. Timeout đã hết.
5. Selector bị đóng, dẫn đến hành vi/ngoại lệ tương ứng.

Nếu lời gọi trả `0`, có thể chỉ là **không có key được xử lý ở lượt này**. Không suy luận rằng đầu đối diện đã đóng socket, có lỗi mạng, không còn dữ liệu trong tương lai, hoặc ứng dụng đã hoàn tất.

`wakeup()` đặc biệt hữu ích khi có luồng khác đưa công việc mới vào hàng đợi nội bộ và muốn đánh thức event loop đang chờ I/O. Theo hợp đồng của `Selector`, một lời gọi `wakeup()` trước khi selector bắt đầu đợi có thể khiến **lần selection kế tiếp** trả về ngay. Tuy nhiên `wakeup` không tích lũy nhiều “vé đánh thức” như một bộ đếm; hãy dùng hàng đợi/cờ trạng thái riêng để truyền dữ liệu công việc.

### Sai lầm khi dùng `Duration`

Nếu đầu vào timeout được biểu diễn bằng `java.time.Duration`, đừng vô tình chuyển thời lượng dương **nhỏ hơn 1 ms** thành `0` rồi gọi `select(action, 0)`. Ví dụ:

```java
Duration timeout = Duration.ofNanos(500_000);
long ms = timeout.toMillis(); // 0, dù Duration vẫn dương!
```

Dòng này chỉ minh họa phép đổi đơn vị, cần import `java.time.Duration`. Khi chính sách yêu cầu “chờ có giới hạn”, xác định rõ cách làm tròn thời lượng nhỏ: chuyển thành `selectNow(action)` nếu muốn thăm dò ngay, hoặc tối thiểu 1 ms nếu có thể chờ một khoảng ngắn. **Không truyền `0` với ý định “timeout bằng 0 ms”** trong timed blocking select.

## 4. Callback được gọi như thế nào?

Overload `select(Consumer<SelectionKey>, long)` có hợp đồng xử lý key tương tự các overload callback khác của `Selector`:

- Trong một selection, runtime truy vấn readiness đối với các channel đã đăng ký và thao tác tương ứng `interestOps`.
- Khi phát hiện key sẵn sàng, `readyOps()` của key được cập nhật rồi gọi `action.accept(key)`.
- Nếu một channel sẵn sàng cho nhiều loại thao tác, runtime **có thể gọi action nhiều lần với cùng một key**, mỗi lần mang một **tập con** các bit ready khác nhau.
- Giá trị trả về vẫn đếm **key duy nhất**, **không phải lượt callback**. Ví dụ có thể có 1 key được xử lý nhưng action chạy 2 lần; số đếm là 1.
- Với overload callback, các key được xử lý **không được thêm vào `selectedKeys()`** theo cơ chế dành cho người gọi duyệt. Trong triển khai mặc định, selected-key set **có thể có hoặc không còn phần tử** sau lời gọi, nên không dùng `selectedKeys().size()` để suy ra số key/callback.

`action.accept(key)` được gọi trên **luồng thực hiện `select`**, không tự chạy bất đồng bộ trên một worker thread hay thread pool. Hợp đồng thực thi đồng bộ này giúp xử lý trạng thái I/O trực tiếp nhưng đòi hỏi callback không được chờ công việc dài.

Một callback thường kiểm tra:

```java
// Đoạn minh họa trong callback:
if (!key.isValid()) {
    return;
}
if (key.isReadable()) {
    // Đọc dữ liệu từ channel nonblocking.
}
if (key.isWritable()) {
    // Ghi dữ liệu còn lại trong buffer và cập nhật interest nếu cần.
}
```

Với `Consumer`, `return` ở đoạn trên chỉ kết thúc **lần gọi callback hiện tại**, không “trả về” khỏi hàm bao ngoài và không hủy toàn bộ selector. Key có thể bị hủy/đóng giữa các thao tác trong ứng dụng đa luồng, vì vậy xử lý `CancelledKeyException` hoặc tình huống kênh đóng phù hợp với thiết kế hệ thống.

## 5. So sánh các phương thức selection để chọn đúng API

| Phương thức | Kiểu chờ | Người xử lý key | Quản lý selected-key set |
| --- | --- | --- | --- |
| `select()` | Chờ vô thời hạn theo điều kiện kết thúc của selector. | Caller duyệt `selectedKeys()`. | Các key sẵn sàng được thêm/cập nhật vào set. |
| `select(long timeout)` | Timeout dương: đợi tối đa khoảng số ms; 0: vô thời hạn. | Caller duyệt `selectedKeys()`. | Các key sẵn sàng được thêm/cập nhật vào set. |
| `selectNow()` | Không chờ readiness. | Caller duyệt `selectedKeys()`. | Các key sẵn sàng được thêm/cập nhật vào set. |
| `select(Consumer<SelectionKey>)` | Chờ vô thời hạn. | Callback `action`. | Không dùng set như danh sách key mới cần xử lý. |
| **`select(Consumer<SelectionKey>, long timeout)`** | Timeout dương có giới hạn, 0 là chờ vô thời hạn. | **Callback `action`**. | Không thêm các key đã xử lý vào set cho caller duyệt. |
| `selectNow(Consumer<SelectionKey>)` | Không chờ readiness. | Callback `action`. | Không thêm các key đã xử lý vào set cho caller duyệt. |

Hai overload callback `select(action)` và `select(action, 0L)` là tương đương về ý nghĩa chờ vô thời hạn.

**Vì sao cần phân biệt?** Với `select(long)`, quên xóa các key đã xử lý khỏi `selectedKeys()` có thể gây xử lý lặp/trạng thái cũ. Với `select(action,long)`, code trong callback chịu trách nhiệm xử lý key được cung cấp; không nên vừa đặt callback vừa duyệt `selectedKeys()` với giả định hai danh sách là một.

## 6. Điều kiện cần: channel nonblocking và interest hợp lệ

Trước khi đăng ký với `Selector`, một `SelectableChannel` phải ở chế độ **nonblocking**. Việc `select` có thể chờ là chờ ở bước **lựa chọn readiness**; bản thân channel được đăng ký vẫn phải nonblocking.

Ví dụ cho kênh nguồn của `Pipe`:

```java
Pipe pipe = Pipe.open();
try (Selector selector = Selector.open();
     Pipe.SourceChannel source = pipe.source();
     Pipe.SinkChannel sink = pipe.sink()) {

    source.configureBlocking(false);
    SelectionKey registration = source.register(selector, SelectionKey.OP_READ);
    // Đầu ghi sink gửi byte; select(action, timeout) theo dõi OP_READ của source.
}
```

Đây là khung minh họa trong phương thức có `throws IOException`; cần import `java.nio.channels.*`. `source.configureBlocking(false)` phải thực hiện trước `register`; nếu cố đăng ký channel ở blocking mode, `IllegalBlockingModeException` có thể được ném.

Một số interest thường gặp:

- `OP_READ`: có khả năng đọc byte; `read` có thể trả số dương, `0` hoặc `-1` (EOF).
- `OP_WRITE`: có khả năng ghi; một lần `write` có thể chỉ ghi được một phần và cần giữ buffer cho lần sau.
- `OP_CONNECT`: trạng thái hoàn thành kết nối nonblocking; thường kiểm tra/hoàn tất bằng `SocketChannel.finishConnect()`.
- `OP_ACCEPT`: khả năng chấp nhận kết nối ở server; với nonblocking `ServerSocketChannel`, `accept()` vẫn có thể trả `null`.

Chỉ đăng ký các thao tác mà loại channel hỗ trợ. Không phải mọi channel có cùng tập thao tác. Trong các vòng lặp thực tế, tránh đăng ký `OP_WRITE` liên tục khi không có dữ liệu cần ghi: nhiều socket gần như luôn writable, có thể làm selector trả liên tục và tốn CPU.

## 7. Ví dụ Java 11+ đầy đủ: timeout, callback, lỗi âm và `wakeup`

Ví dụ sau dùng `Pipe` nội bộ, **không cần mạng**, để kiểm chứng hành vi quan trọng của timed selection. Nó tạo nguồn nonblocking, thử chờ ngắn khi chưa có dữ liệu, kiểm tra timeout âm, gửi hai byte `OK`, đọc bằng callback rồi minh họa `wakeup()` trước lời gọi timeout bằng 0.

Lưu chính xác vào tệp **`TimedSelectorCallbackDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

public final class TimedSelectorCallbackDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            int idle = selector.select(key -> {
                throw new AssertionError("No data should be ready yet");
            }, 25L);
            System.out.println("idle-count=" + idle);

            try {
                selector.select(key -> { }, -1L);
                System.out.println("negative=unexpected-success");
            } catch (IllegalArgumentException ex) {
                System.out.println("negative=IllegalArgumentException");
            }

            ByteBuffer outgoing = ByteBuffer.wrap("OK".getBytes(StandardCharsets.UTF_8));
            while (outgoing.hasRemaining()) {
                sink.write(outgoing);
            }

            AtomicInteger callbacks = new AtomicInteger();
            ByteArrayOutputStream received = new ByteArrayOutputStream();
            int selected = selector.select(key -> {
                callbacks.incrementAndGet();

                if (!key.isValid() || !key.isReadable()) {
                    return;
                }
                Pipe.SourceChannel channel = (Pipe.SourceChannel) key.channel();
                ByteBuffer buffer = ByteBuffer.allocate(8);
                try {
                    int bytesRead = channel.read(buffer);
                    if (bytesRead > 0) {
                        buffer.flip();
                        byte[] chunk = new byte[buffer.remaining()];
                        buffer.get(chunk);
                        received.write(chunk, 0, chunk.length);
                    }
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            }, 1_000L);

            System.out.println("selected-keys=" + selected);
            System.out.println("callback-calls=" + callbacks.get());
            System.out.println("payload=" +
                    new String(received.toByteArray(), StandardCharsets.UTF_8));
        }

        try (Selector selector = Selector.open()) {
            selector.wakeup();
            int awoken = selector.select(key -> {
                throw new AssertionError("No channels are registered");
            }, 0L);
            System.out.println("woken-count=" + awoken);
        }
    }
}
```

Biên dịch và chạy bằng JDK 11 trở lên. Tham số `--release 11` xác nhận chương trình dùng API có trong Java 11:

```bash
javac -encoding UTF-8 --release 11 TimedSelectorCallbackDemo.java
java TimedSelectorCallbackDemo
```

**Stdout đã kiểm chứng:**

```text
idle-count=0
negative=IllegalArgumentException
selected-keys=1
callback-calls=1
payload=OK
woken-count=0
```

Giải thích:

1. `idle-count=0`: `Pipe.SourceChannel` đã đăng ký `OP_READ` nhưng chưa có byte ở đầu đọc; timed select hết khoảng chờ 25 ms và không xử lý key nào. Chương trình **không** in thời gian đo thực tế vì timeout không có bảo đảm real-time.
2. `negative=IllegalArgumentException`: `-1L` là timeout không hợp lệ và bị từ chối. `-1` không mang ý nghĩa “vô hạn”.
3. `ByteBuffer.wrap("OK".getBytes(UTF_8))` tạo hai byte; vòng ghi đảm bảo đầu ghi đẩy hết byte. Trong fixture này đầu ghi dùng thao tác blocking thông thường, còn **đầu đọc đã đăng ký** vẫn là nonblocking.
4. `selected-keys=1`: khi có dữ liệu, `select(action, 1_000L)` phát hiện một key duy nhất và gọi callback. Hàm có thể trở về **trước khi** hết hạn 1.000 ms.
5. `callback-calls=1`: chỉ một `Pipe.SourceChannel` đăng ký `OP_READ` ở ví dụ này. Không suy rộng rằng số lần callback luôn bằng số unique keys trong ứng dụng nhiều interest operations.
6. `payload=OK`: callback đọc byte có sẵn vào `ByteBuffer`, `flip()` chuyển buffer sang chế độ đọc, rồi `ByteArrayOutputStream` thu lại byte. `new String(..., UTF_8)` chỉ dùng để trình bày kết quả; `Selector` không tự giải mã ký tự.
7. `woken-count=0`: selector mới không đăng ký channel. Gọi `wakeup()` **trước** `select(action, 0L)` khiến lần selection đó trở về ngay, dù timeout `0` thông thường nghĩa là chờ vô thời hạn. Không được bỏ `wakeup()` trong trường hợp này rồi mặc định lời gọi sẽ trả ngay.

Ví dụ tập trung vào readiness của một `Pipe`. Mô hình I/O mạng thực tế còn cần quản lý kết nối, buffer dữ liệu đọc/ghi dở, chuẩn giao thức, đóng kênh và xử lý lỗi ứng dụng.

## 8. Xử lý I/O trong callback mà không phá vỡ timeout

Callback không nên làm những việc có thể chờ vô hạn, vì callback chạy **trong** lời gọi `select`.

### Nguyên tắc với `read`

Với một channel nonblocking:

```java
// Đoạn minh họa khi key đại diện cho Pipe.SourceChannel:
ByteBuffer buffer = ByteBuffer.allocate(4_096);
int n = ((Pipe.SourceChannel) key.channel()).read(buffer);
if (n > 0) {
    buffer.flip();
    // Xử lý n byte vừa đọc.
} else if (n == 0) {
    // Chưa có byte mới: ngừng đọc trong lượt này, không spin.
} else { // n == -1
    key.cancel(); // Đầu bên kia đã kết thúc: dọn đăng ký theo chính sách app.
}
```

Đừng viết vòng `while` “đợi đủ một thông điệp” mà không xử lý nhánh `n == 0`; khi kênh nonblocking chưa có thêm dữ liệu, việc lặp vô hạn sẽ giữ callback ở trạng thái chạy bận. Với thông điệp dài hơn một lần đọc, lưu trạng thái đọc dở để hoàn tất ở lần selection tương lai.

### Nguyên tắc với `write`

Khi ghi dữ liệu, một `SocketChannel.write` nonblocking có thể ghi ít byte hơn số phần còn lại của buffer hoặc trả 0. Phần dữ liệu chưa ghi phải được giữ lại cho một lần readiness tiếp theo. Chỉ bật `OP_WRITE` khi thật sự có buffer chờ ghi. Sau khi ghi xong, loại `OP_WRITE` khỏi `interestOps` để tránh selector liên tục báo writable.

### Nguyên tắc với công việc nặng

Không truy vấn cơ sở dữ liệu đồng bộ lâu, không `Thread.sleep(...)`, không `Future.get()` chờ kết quả, và không làm CPU-bound nặng trực tiếp bên trong callback. Nếu cần xử lý lớn, sao chép trạng thái/dữ liệu thích hợp rồi đưa sang cơ chế xử lý khác **sau khi** rời selection hoặc qua hàng đợi được quản lý cẩn thận.

## 9. Đồng bộ, reentrancy và ngoại lệ callback

Hợp đồng Java `Selector` cho biết hoạt động selection đồng bộ hóa trên selector và selected-key set. Callback trong overload này cũng được gọi khi các khóa đó đang được giữ. Điều này dẫn đến các yêu cầu:

- **Không gọi selection lồng nhau trên cùng selector** từ callback (ví dụ `selector.selectNow()`, `selector.select(...)`). Reentrant selection không được bảo đảm và kết quả phụ thuộc implementation; có thể dẫn đến trạng thái khó kiểm soát hoặc deadlock.
- Tránh giữ khóa ứng dụng trong callback rồi chờ luồng khác đang cần khóa selector theo chiều ngược lại.
- Khi nhiều luồng cùng sử dụng selector, các thay đổi `interestOps` thực hiện trong lúc selection đang tiến hành không có hiệu lực với lượt selection đang chạy; chúng sẽ được xem xét ở lần selection tiếp theo.
- Một key có thể bị hủy hoặc channel bị đóng giữa lúc phát hiện readiness và lúc callback thao tác; cần kiểm tra tính hợp lệ, trạng thái channel và xử lý ngoại lệ trong điều kiện đồng thời.
- Nếu callback ném exception, ngoại lệ được **truyền ra caller**. `Consumer.accept` không khai báo `throws IOException`, nên trong lambda cần bắt `IOException` rồi quyết định xử lý hoặc bao thành `UncheckedIOException` như chương trình ở mục 7.
- Selector bị đóng trước hoặc trong lời gọi selection có thể dẫn đến `ClosedSelectorException`. Nếu callback đóng selector, Javadoc quy định `ClosedSelectorException` được ném khi action hoàn thành.

Không nên dùng `catch (Exception ignored)` quanh callback để lặng lẽ bỏ mọi lỗi; lỗi có thể cho biết channel hỏng, dữ liệu chưa xử lý hết hoặc logic event loop cần dừng.

## 10. Thiết kế vòng lặp dùng deadline và timeout

Một timed selection thường đặt trong vòng lặp: chờ key cho đến khi có I/O, timeout, hoặc cần xử lý các công việc khác.

```java
// Pseudocode minh họa, không phải chương trình chạy độc lập.
while (running) {
    int consumed = selector.select(key -> handleReadyKey(key), 200L);

    runQueuedTasks();
    if (consumed == 0) {
        onIdleTick();
    }
}
```

- `runQueuedTasks()` và `onIdleTick()` là công việc ứng dụng; không hàm nào là API của Java `Selector`.
- Số `200L` là **timeout của mỗi lượt chờ**, không phải deadline tuyệt đối cho toàn bộ vòng đời. Khi cần lịch xử lý chính xác hơn, tính thời lượng còn lại từ một **đồng hồ monotonic** như `System.nanoTime()`, rồi chọn timeout dương hoặc `selectNow(action)` khi đã hết thời gian.
- Khi tính budget với thời lượng <1 ms, tránh vô tình làm tròn về 0 như đã giải thích; nếu không sẽ thành chờ vô thời hạn.
- `select(action, timeout)` không tự biết sự kiện ứng dụng ngoài I/O đã đến. Khi luồng khác thêm công việc vào queue, có thể gọi `wakeup()` để selector thoát khỏi chờ và xử lý queue. Dữ liệu task vẫn phải được truyền bằng queue/biến đồng bộ, **không** truyền qua bản thân `wakeup`.
- Không gọi `selectNow(action)` liên tục trong vòng lặp không nghỉ khi chẳng có công việc: dễ gây **busy spinning**. Dùng timed/blocking selection hợp lý với mô hình ứng dụng.

Nếu vòng lặp được yêu cầu dừng, đặt cờ trạng thái có cơ chế nhìn thấy giữa các luồng (`volatile`, `AtomicBoolean` hoặc đồng bộ phù hợp) và đánh thức selector bằng `wakeup()`. Chỉ `wakeup()` không tự đặt cờ dừng, vì vậy caller cần kiểm tra state sau khi lời gọi `select` kết thúc.

## 11. Kiểm thử đúng cho timeout và callback

Một số trường hợp kiểm thử có giá trị cao:

| Tình huống | Cách kiểm chứng | Điều không nên giả định |
| --- | --- | --- |
| Không có channel sẵn sàng với timeout dương | Tạo `Pipe` rỗng, đăng ký `OP_READ`, gọi `select(action, 25L)`, khẳng định callback không nhận byte. | Không khẳng định đúng chính xác 25 ms theo đồng hồ máy. |
| Sẵn sàng trước timeout | Ghi dữ liệu vào `Pipe` trước selection, dùng timeout dương, kiểm tra byte được đọc. | Không luôn bắt buộc đợi hết timeout. |
| Timeout âm | `select(action, -1L)` ném `IllegalArgumentException`. | Không có ý nghĩa “chờ vô hạn”. |
| Timeout bằng 0 + `wakeup` trước | Gọi `wakeup()` rồi `select(action, 0L)` khi không có key. | Không suy luận `0` tự nó là nonblocking. |
| Callback phát sinh lỗi | Test với consumer ném exception chủ định; kiểm tra exception đến caller. | Không kỳ vọng selector tự chuyển lỗi callback thành một giá trị int đặc biệt. |
| Key có nhiều trạng thái readiness | Thiết kế test cho từng loại readiness/interest với channel phù hợp. | Không assert số callback bằng số unique keys trong mọi trường hợp. |
| Channel đăng ký không nonblocking | Thử `register` với channel đang blocking, kiểm tra `IllegalBlockingModeException`. | Không mong timed `select` tự sửa blocking mode. |

Để kiểm thử deadline, có thể đo độ trễ bằng `System.nanoTime()`, nhưng cần dùng một **khoảng dung sai** hợp lý và tránh “assert chính xác 25 ms”. Môi trường CI có tải thay đổi, nên test dựa trên **trạng thái, dữ liệu, số key hoặc ngoại lệ có hợp đồng rõ ràng** sẽ ổn định hơn test thời gian tuyệt đối.

Khi test `wakeup` từ luồng khác, hãy có cơ chế đồng bộ để biết luồng selector đã sẵn sàng hoặc ít nhất gọi `wakeup` tại thời điểm mong muốn; không dùng `Thread.sleep` cố định như bảo đảm thứ tự thực thi.

## 12. Các lỗi hiểu sai thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`select(action, 0)` là lựa chọn không chặn.” | Sai: 0 nghĩa là **chờ vô thời hạn**; nonblocking là `selectNow(action)`. |
| “Timeout âm là vô hạn.” | Sai: ném `IllegalArgumentException`. |
| “Timeout tính bằng giây.” | Sai: API nhận `long` mili giây. |
| “`select(action, 100)` chắc chắn trả sau đúng 100 ms.” | Sai: có thể trả sớm; không có bảo đảm thời gian thực, callback có thể chạy lâu. |
| “Hết timeout nghĩa là socket EOF.” | Sai: chỉ không có key xử lý ở lượt này; EOF là kết quả cụ thể của lệnh `read`. |
| “Số trả về bằng số lần consumer chạy.” | Không chắc: giá trị đếm **key duy nhất**. |
| “Callback xử lý I/O trên thread khác.” | Sai: consumer chạy đồng bộ trong lời gọi selection. |
| “Overload callback vẫn cần duyệt `selectedKeys()`.” | Không dùng selected-key set như danh sách kết quả callback; selected-key set không hứa luôn trống. |
| “Có thể gọi `selectNow` đệ quy trong callback.” | Reentrant selection không được bảo đảm; tránh làm vậy. |
| “`select` giúp channel blocking đăng ký được.” | Sai: channel phải `configureBlocking(false)` trước `register`. |
| “`wakeup()` tự chuyển công việc giữa các luồng.” | Sai: chỉ báo selector kết thúc chờ; ứng dụng vẫn cần queue/cờ trạng thái. |
| “Làm `Thread.sleep` trong callback vẫn giữ timeout toàn hàm.” | Sai: timeout chỉ chi phối bước chờ, không giới hạn công việc callback. |
| “Chuyển `Duration.ofNanos(500_000).toMillis()` rồi dùng như timeout ngắn.” | Kết quả là 0, sẽ vô tình chờ vô hạn nếu đưa thẳng vào `select(action, 0)`. |

## 13. Checklist triển khai

1. **Xác định mục tiêu chờ:** dùng `select(action, positiveMillis)` khi muốn giới hạn thời gian đợi readiness; dùng `selectNow(action)` để thăm dò ngay; dùng `select(action)` nếu được phép chờ vô hạn.
2. **Kiểm tra timeout:** mili giây, số âm không hợp lệ, số 0 là vô hạn. Đặc biệt cẩn thận với `Duration.toMillis()` làm tròn về 0.
3. **Đăng ký đúng:** chuyển channel sang nonblocking trước `register`; chỉ quan tâm các thao tác thực sự cần.
4. **Giữ callback ngắn:** đọc/ghi không chặn, xử lý `read == 0`, `read == -1` và partial writes; không gọi selection lồng nhau.
5. **Giá trị trả về là unique keys:** không lấy số callback hoặc `selectedKeys().size()` làm đồng nghĩa.
6. **Thiết kế cơ chế đánh thức:** khi có task hoặc lệnh dừng từ luồng khác, truyền trạng thái bằng hàng đợi/cờ, rồi `wakeup` để thoát khỏi timed selection.
7. **Giữ lỗi minh bạch:** xử lý `IOException`, lỗi callback và trạng thái key bị hủy/selector bị đóng; đóng tài nguyên bằng try-with-resources.
8. **Kiểm thử trạng thái hơn stopwatch:** dùng `Pipe`/socket test phù hợp, kiểm tra timeout dương, 0, âm, dữ liệu sẵn sàng và callback.

### Tài liệu chính thức

- [Oracle Java SE 11 — `Selector`: `select(Consumer<SelectionKey>, long)`, `selectNow`, `wakeup`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html)
- [Oracle Java SE 25 — `Selector`: hợp đồng API vẫn được duy trì](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html)
- [Oracle Java SE 11 — `SelectionKey`: `isReadable()`, `isValid()`, `interestOps()` và `readyOps()`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Oracle Java SE 11 — `SelectableChannel`: `configureBlocking` và `register`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectableChannel.html)
