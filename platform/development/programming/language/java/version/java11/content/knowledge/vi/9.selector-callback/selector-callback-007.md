# SelectionKey.interestOpsAnd — cập nhật interest set bằng phép AND (Java 11)

Khi viết một ứng dụng Java NIO không chặn (non-blocking I/O), `Selector` giúp theo dõi những kênh đang sẵn sàng đọc, ghi, chấp nhận kết nối hoặc hoàn tất kết nối. Mỗi kênh được đăng ký với một `Selector` có một `SelectionKey`, trong đó **interest set** ghi lại những loại sự kiện ứng dụng đang muốn được thông báo.

Từ **Java 11**, phương thức **`SelectionKey.interestOpsAnd(int ops)`** cho phép cập nhật interest set bằng phép **AND theo bit một cách nguyên tử**. Tình huống điển hình là **bỏ quan tâm tới `OP_WRITE` khi không còn dữ liệu đang chờ gửi**, để tránh vòng lặp selector liên tục báo có thể ghi nhưng ứng dụng không có việc cần làm. API này vẫn tồn tại và hữu ích trên các JDK hiện đại; không cần giữ một runtime Java 11 cũ chưa được cập nhật để sử dụng kiến thức trong bài.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt `interestOps()`, `readyOps()` và tập `selectedKeys()` của `Selector`.
2. Giải thích chính xác biểu thức `newInterest = oldInterest & mask` và **giá trị trả về là interest set cũ**.
3. Dùng `interestOpsAnd(~SelectionKey.OP_WRITE)` để bỏ một cờ mà không làm mất những cờ khác.
4. Dùng `interestOpsOr(SelectionKey.OP_WRITE)` để bổ sung lại cờ một cách nguyên tử.
5. Biết giới hạn của tính nguyên tử và tác động của thay đổi interest set khi một lệnh `select` đang thực thi.
6. Xử lý `CancelledKeyException`, các thao tác không được kênh hỗ trợ, `Selector.wakeup()` và trường hợp `OP_WRITE` gây vòng lặp bận.
7. Áp dụng phương thức trong mô hình xử lý sự kiện NIO hiện hành, đồng thời hiểu khi nào cần đồng bộ thêm trạng thái ứng dụng.

## 2. Ba khái niệm: interest set, ready set và selected-key set

`SelectionKey` nối **một `SelectableChannel` với một `Selector`**. Hai tập bit trên key có vai trò khác nhau:

| Khái niệm | Trả về / vị trí | Ý nghĩa |
| --- | --- | --- |
| **Interest set** | `key.interestOps()` | Những thao tác mà chương trình **muốn selector theo dõi** ở lần chọn tiếp theo. Ứng dụng có thể thay đổi tập này. |
| **Ready set** | `key.readyOps()` | Những thao tác mà selector đã **phát hiện có khả năng thực hiện** ở một lần chọn. Không phải lệnh bảo đảm I/O chắc chắn thành công ngay. |
| **Selected-key set** | `selector.selectedKeys()` | Các key được lần chọn đưa vào hoặc cập nhật trạng thái sẵn sàng; ứng dụng cần quản lý việc lấy key ra khỏi tập nếu dùng API trả selected keys. |

Ví dụ, một `SocketChannel` có thể đăng ký quan tâm cả đọc và ghi:

```java
SelectionKey key = channel.register(
        selector, SelectionKey.OP_READ | SelectionKey.OP_WRITE);
```

Đây là **đoạn mã minh họa** trong một phương thức mà `channel` là `SocketChannel` đang mở, **đã đặt non-blocking**, và `selector` là `Selector` hợp lệ. Khi đăng ký, interest set gồm `OP_READ` và `OP_WRITE`; điều đó **không** có nghĩa ready set ngay lập tức cũng có cả hai cờ.

Sơ đồ luồng xử lý:

```text
SelectableChannel (non-blocking)
            |
            | register(selector, interestOps)
            v
      SelectionKey
      interestOps = READ | WRITE
            |
            v
   Selector.select(...) / selectNow(...)
            |
            v
  readyOps: những thao tác đã được phát hiện
            |
            v
   Ứng dụng xử lý I/O và điều chỉnh interestOps
```

**Quan trọng:** việc gọi `interestOpsAnd` chỉ thay đổi **interest set**. Nó **không xóa trực tiếp `readyOps`**, không tự hủy key, không tháo kênh khỏi selector và không tự xóa một key đang có trong `selectedKeys()`. Một ready bit cũ có thể còn được quan sát cho tới khi được cập nhật ở lượt selection phù hợp.

## 3. Hợp đồng API của `interestOpsAnd(int)`

Chữ ký:

```java
public int interestOpsAnd(int ops)
```

Hiểu bằng phép toán:

```text
oldInterest = key.interestOps()
newInterest = oldInterest & ops
key.interestOps() trở thành newInterest
Giá trị trả về của interestOpsAnd(ops) là oldInterest
```

Phương thức thực hiện phép **AND nguyên tử** đối với các lời gọi đồng thời của `interestOpsAnd` và `interestOpsOr` trên cùng key. Trong Java 11, triển khai mặc định đồng bộ trên key khi lấy và cập nhật interest set.

- **Tham số `ops` là một bit mask**, không phải tên một thao tác đơn lẻ.
- **Giá trị trả về có kiểu `int`** là **tập bit trước khi thay đổi**, không phải `SelectionKey` và cũng không phải tập bit mới.
- Phương thức chỉ có thể **giữ nguyên hoặc xóa bit**; phép AND **không thể thêm bit `1` chưa có**.
- Nếu key đã bị hủy (cancelled), phương thức ném **`CancelledKeyException`**.
- Khác `interestOps(int)` và `interestOpsOr(int)`, phương thức **không ném `IllegalArgumentException` chỉ vì mask chứa bit không thuộc `channel.validOps()`**. Điều này cho phép truyền phép phủ định bit như `~SelectionKey.OP_WRITE`.
- Khi thay đổi xảy ra trong lúc một lần selection đang chạy, lần selection **đang diễn ra** không bị thay đổi bởi interest set mới; selector sử dụng giá trị mới từ **lần selection tiếp theo**.

Hợp đồng này áp dụng từ Java 11 và vẫn được tài liệu Java SE hiện nay công bố.

### Ví dụ chính: xóa một cờ, giữ những cờ khác

Giả sử interest set hiện tại gồm `OP_READ | OP_WRITE`:

```text
OP_READ  = 0001 (1)
OP_WRITE = 0100 (4)
old      = 0101 (5)
~WRITE   = ...1011 (phủ định mọi bit của mask WRITE trong int)
old & ~WRITE = 0001 (1)
```

Lệnh:

```java
int previous = key.interestOpsAnd(~SelectionKey.OP_WRITE);
```

có kết quả logic:

- `previous` bằng **5**: tập bit **trước khi cập nhật**.
- `key.interestOps()` bằng **1**: `OP_READ` còn, `OP_WRITE` đã được loại bỏ.

Không cần tính `5` thủ công; giá trị thực tế tùy interest set đang có.

**Dấu `~` cực kỳ quan trọng:**

| Biểu thức | Ý nghĩa |
| --- | --- |
| `key.interestOpsAnd(~SelectionKey.OP_WRITE)` | **Xóa** `OP_WRITE`, giữ các bit khác. |
| `key.interestOpsAnd(~SelectionKey.OP_READ)` | **Xóa** `OP_READ`, giữ các bit khác. |
| `key.interestOpsAnd(SelectionKey.OP_READ)` | **Chỉ giữ lại** `OP_READ` nếu bit đó đã có; xóa tất cả bit khác. |
| `key.interestOpsAnd(0)` | Xóa **toàn bộ interest set**; kênh vẫn đăng ký nhưng không còn thao tác nào được quan tâm. |
| `key.interestOpsAnd(~0)` | Giữ nguyên mọi bit (mask toàn bit `1`). |
| `key.interestOpsOr(SelectionKey.OP_WRITE)` | **Thêm hoặc giữ** `OP_WRITE`, không xóa bit khác. |

Một lời gọi `interestOpsAnd(SelectionKey.OP_WRITE)` **không phải “bỏ quan tâm tới ghi”**: nó giữ lại duy nhất bit WRITE nếu có. Đây là lỗi đọc bit mask rất phổ biến.

## 4. Các cờ thao tác và `validOps()`

Java NIO định nghĩa bốn cờ chính trong `SelectionKey`:

| Cờ | Giá trị bit | Mục đích |
| --- | ---: | --- |
| `OP_READ` | `1` | Theo dõi khả năng đọc dữ liệu hoặc một số trạng thái đọc đặc biệt như EOF. |
| `OP_WRITE` | `4` | Theo dõi khả năng ghi, kể cả trường hợp kết nối có thể có lỗi cần xử lý. |
| `OP_CONNECT` | `8` | Theo dõi hoàn tất hoặc thất bại của kết nối non-blocking. |
| `OP_ACCEPT` | `16` | Theo dõi khả năng chấp nhận kết nối đến. |

Không phải kênh nào cũng hỗ trợ mọi cờ. `channel.validOps()` công bố tập cờ hợp lệ cho loại kênh:

- `SocketChannel` hỗ trợ `OP_CONNECT | OP_READ | OP_WRITE`.
- `ServerSocketChannel` hỗ trợ `OP_ACCEPT`.
- `Pipe.SourceChannel` hỗ trợ `OP_READ`.
- `Pipe.SinkChannel` hỗ trợ `OP_WRITE`.

Do đó, `interestOpsOr(SelectionKey.OP_WRITE)` trên key của `Pipe.SourceChannel` sẽ ném `IllegalArgumentException` do bit không được hỗ trợ. Tuy nhiên, **`interestOpsAnd(~SelectionKey.OP_WRITE)` vẫn hợp lệ** trên key đó: mask chỉ dùng để giữ/xóa các bit **đã có**; không thêm WRITE vào interest set.

Mọi channel phải được đặt ở **non-blocking mode** trước khi đăng ký với selector. Hãy kiểm tra `isOpen()`, `isValid()` và quản lý việc cancel/close theo vòng đời của ứng dụng.

## 5. Chương trình độc lập: quan sát bit mask và giá trị cũ

Ví dụ này dùng `Pipe.SourceChannel`, nên không cần mở cổng TCP hay phụ thuộc máy chủ bên ngoài. Mục tiêu là kiểm tra các phép đổi interest set **trước khi chạy selection**, giúp đầu ra về bit luôn có thể dự đoán.

Tạo tệp **`KeyMaskDemo.java`**:

```java
import java.nio.channels.CancelledKeyException;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;

public class KeyMaskDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);
            SelectionKey key =
                    source.register(selector, SelectionKey.OP_READ);

            System.out.println("Source validOps: " + source.validOps());
            System.out.println("Initial interestOps: " + key.interestOps());

            int beforeClear =
                    key.interestOpsAnd(~SelectionKey.OP_READ);
            System.out.println("Before clearing READ: " + beforeClear);
            System.out.println("After clearing READ: " + key.interestOps());

            int beforeRestore =
                    key.interestOpsOr(SelectionKey.OP_READ);
            System.out.println("Before restoring READ: " + beforeRestore);
            System.out.println("After restoring READ: " + key.interestOps());

            key.interestOpsAnd(~SelectionKey.OP_WRITE);
            System.out.println("After ~WRITE mask: " + key.interestOps());

            key.interestOpsAnd(0);
            System.out.println("After clearing all: " + key.interestOps());

            key.cancel();
            System.out.println("Key valid after cancel: " + key.isValid());

            try {
                key.interestOpsAnd(~SelectionKey.OP_READ);
            } catch (CancelledKeyException expected) {
                System.out.println("CancelledKeyException: yes");
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK có hỗ trợ Java 11:

```sh
javac --release 11 -encoding UTF-8 KeyMaskDemo.java
java KeyMaskDemo
```

**Stdout chính xác:**

```text
Source validOps: 1
Initial interestOps: 1
Before clearing READ: 1
After clearing READ: 0
Before restoring READ: 0
After restoring READ: 1
After ~WRITE mask: 1
After clearing all: 0
Key valid after cancel: false
CancelledKeyException: yes
```

**Giải thích từng bước:**

1. `source.validOps() == 1` vì đầu đọc của `Pipe` chỉ hỗ trợ `OP_READ`.
2. `source.register(selector, OP_READ)` tạo key mới có interest set `1`.
3. `interestOpsAnd(~OP_READ)` xóa bit READ; phương thức trả về **1**, còn `key.interestOps()` mới là **0**.
4. `interestOpsOr(OP_READ)` thêm bit READ trở lại; trả về **0**, còn interest set mới là **1**.
5. `interestOpsAnd(~OP_WRITE)` không gây `IllegalArgumentException` dù `SourceChannel` không hỗ trợ WRITE; nó chỉ giữ nguyên bit READ đang có.
6. `interestOpsAnd(0)` tắt tất cả thao tác quan tâm nhưng **không hủy đăng ký**.
7. `key.cancel()` làm key không còn hợp lệ; gọi `interestOpsAnd` sau đó ném `CancelledKeyException`. `cancel()` và `interestOpsAnd(0)` là **hai hành động khác nhau**.

`Pipe.SinkChannel` được mở và đóng cùng nguồn để quản lý tài nguyên hoàn chỉnh dù ví dụ không ghi dữ liệu.

## 6. Selector callback: thao tác sau khi nhận sự kiện

Tên “callback” ở đây chỉ hành động **do chương trình cung cấp** để xử lý key đã sẵn sàng; `SelectionKey` không tự gọi một hàm ứng dụng mỗi khi interest set thay đổi.

Java 11 có các overload `Selector.select(Consumer<SelectionKey>)`, `select(Consumer<SelectionKey>, long)` và `selectNow(Consumer<SelectionKey>)`. Chúng cho phép viết logic xử lý sự kiện theo dạng **action/callback** mà không phải tự lặp và xóa từng phần tử khỏi `selectedKeys()`. Một callback có thể thay đổi interest set bằng `interestOpsAnd`, nhưng hiệu lực lên việc chọn thao tác chỉ đến ở **lượt selection tiếp theo**.

Ví dụ sau dùng một `Pipe` chứa một byte đã được ghi sẵn. Tạo **`SelectorActionDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.util.concurrent.atomic.AtomicInteger;

public class SelectorActionDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);
            SelectionKey key =
                    source.register(selector, SelectionKey.OP_READ);

            ByteBuffer outbound = ByteBuffer.wrap(new byte[] {42});
            while (outbound.hasRemaining()) {
                sink.write(outbound);
            }

            AtomicInteger received = new AtomicInteger(-1);
            long deadlineNanos = System.nanoTime()
                    + 3_000_000_000L;

            while (received.get() < 0
                    && System.nanoTime() < deadlineNanos) {
                selector.select(readyKey -> {
                    if (!readyKey.isValid()
                            || !readyKey.isReadable()) {
                        return;
                    }

                    ByteBuffer oneByte = ByteBuffer.allocate(1);
                    try {
                        int count = source.read(oneByte);
                        if (count == 1) {
                            oneByte.flip();
                            received.set(
                                    Byte.toUnsignedInt(oneByte.get()));
                            readyKey.interestOpsAnd(
                                    ~SelectionKey.OP_READ);
                        }
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                }, 200);
            }

            if (received.get() < 0) {
                throw new IOException("Read event timed out");
            }

            System.out.println("Received: " + received.get());
            System.out.println("Interest after callback: "
                    + key.interestOps());
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 SelectorActionDemo.java
java SelectorActionDemo
```

**Stdout khi nhận được sự kiện đọc trong thời hạn 3 giây:**

```text
Received: 42
Interest after callback: 0
```

Trong chương trình:

- `source` đã được đặt non-blocking; `selector` chỉ theo dõi `OP_READ`.
- Sink ghi byte có giá trị `42` trước khi chọn, nên source sẽ sẵn sàng đọc trong điều kiện hoạt động bình thường.
- `select(Consumer, 200)` cho phép gọi callback khi phát hiện key sẵn sàng, với thời gian chờ mỗi lượt tối đa khoảng 200 ms. Vòng lặp có thời hạn tổng thể để tránh chờ vô hạn nếu nền tảng không phát hiện sự kiện trong thời gian thử nghiệm.
- Callback đọc đúng một byte, kiểm tra `count == 1` và đổi thành số không dấu `0..255` bằng `Byte.toUnsignedInt`.
- Sau khi đã đọc xong dữ liệu cần thiết, `interestOpsAnd(~OP_READ)` bỏ quan tâm tới lần đọc tiếp theo; vì source được đăng ký ban đầu chỉ có READ, interest set trở thành `0`.
- `AtomicInteger` ở đây chỉ là cách giữ trạng thái có thể cập nhật từ lambda; ví dụ **không cần chạy đa luồng**. Trong hệ thống thực, trạng thái kết nối và đồng bộ là bài toán riêng.

**Lưu ý:** Readiness là **gợi ý**, không phải bảo đảm một lần `read` nhất định sẽ đọc được byte; việc code kiểm tra `count` và có deadline giúp minh họa cách xử lý sự kiện thực tế. Chương trình có thể kết thúc bằng lỗi timeout trên môi trường I/O gặp sự cố, thay vì in hai dòng thành công. Không dùng mẫu này như một thư viện production hoàn chỉnh.

### Nếu dùng `selectedKeys()` thay vì callback

Một vòng lặp cổ điển vẫn hợp lệ trong Java hiện nay:

```java
selector.select();
Iterator<SelectionKey> iter =
        selector.selectedKeys().iterator();

while (iter.hasNext()) {
    SelectionKey readyKey = iter.next();
    iter.remove(); // Bỏ key đã lấy khỏi selected-key set

    if (!readyKey.isValid()) {
        continue;
    }
    if (readyKey.isReadable()) {
        // Đọc dữ liệu và xử lý theo giao thức.
    }
}
```

Đây là **đoạn minh họa trong một phương thức có `selector` và import `java.util.Iterator`**, không phải một chương trình độc lập. `selectedKeys()` **không tự biến mất** sau khi chương trình xử lý, nên cần loại những key đã lấy ra bằng `iter.remove()`. Khi dùng `select(Consumer)`, selector chuyển key vào action trực tiếp và không thêm chúng vào selected-key set theo hợp đồng API.

Không duyệt hoặc sửa `selectedKeys()` tùy tiện từ nhiều thread: tập này không được thiết kế để bị các thread khác đồng thời thay đổi mà không có đồng bộ phù hợp.

## 7. Tình huống production: ngừng theo dõi `OP_WRITE` khi hết dữ liệu để gửi

Với socket non-blocking, `OP_WRITE` thường có thể luôn sẵn sàng khi bộ đệm gửi còn chỗ. Nếu application **luôn đăng ký quan tâm WRITE**, selector có thể báo sự kiện ghi liên tục dù hàng đợi ghi đã rỗng; event loop chiếm CPU mà không làm việc hữu ích.

Mẫu thiết kế thường dùng là:

1. **Có dữ liệu cần gửi:** bật `OP_WRITE` bằng `interestOpsOr(SelectionKey.OP_WRITE)`.
2. **Selector báo có thể ghi:** gọi `SocketChannel.write(ByteBuffer)` để gửi dần những buffer đang chờ.
3. **Ghi chưa hết vì socket không còn chỗ:** **giữ `OP_WRITE`** để thử lại khi selector tiếp tục thông báo.
4. **Đã gửi hết mọi buffer đang chờ:** gọi `interestOpsAnd(~SelectionKey.OP_WRITE)` để tránh thông báo WRITE không cần thiết.
5. **Có dữ liệu mới đến từ thread khác:** đưa yêu cầu vào hàng đợi thread-safe, phối hợp với thread sở hữu event loop; bật WRITE và gọi `selector.wakeup()` khi cần đánh thức event loop đang chặn.

Minh họa xử lý ghi (đoạn **phương thức trong lớp**, không phải chương trình độc lập):

```java
static void flushPending(SelectionKey key,
                         Deque<ByteBuffer> pending)
        throws IOException {
    SocketChannel channel = (SocketChannel) key.channel();

    while (!pending.isEmpty()) {
        ByteBuffer buffer = pending.peekFirst();
        channel.write(buffer); // Non-blocking: có thể ghi 0 byte

        if (buffer.hasRemaining()) {
            return; // Còn dữ liệu, giữ OP_WRITE để thử lại
        }

        pending.removeFirst();
    }

    // Chỉ đến đây khi đã gửi hết mọi buffer đang chờ.
    key.interestOpsAnd(~SelectionKey.OP_WRITE);
}
```

Đoạn này cần imports `java.io.IOException`, `java.nio.ByteBuffer`, `java.nio.channels.SocketChannel`, `java.nio.channels.SelectionKey` và `java.util.Deque`. Giả định key thuộc một `SocketChannel` **non-blocking, đã kết nối**, `pending` do event-loop thread quản lý và mọi buffer đã sẵn sàng để ghi. Nó không xử lý toàn bộ lỗi ngắt kết nối, giao thức framing hay phân bổ hàng đợi.

Để bật lại thao tác WRITE trong thread sở hữu selector:

```java
// Sau khi thêm dữ liệu vào pending:
key.interestOpsOr(SelectionKey.OP_WRITE);
```

Khi thread **khác** thêm dữ liệu, cần đồng bộ quyền sở hữu hàng đợi và quyết định cập nhật interest set để tránh tình huống callback vừa xóa `OP_WRITE` trong lúc có buffer mới được thêm. Một thiết kế bền vững là **đẩy yêu cầu vào queue thread-safe**, gọi `selector.wakeup()`, rồi để **một event-loop thread duy nhất** thêm buffer, đổi interest bits và thực hiện I/O. Không coi `interestOpsAnd` là cơ chế tự đồng bộ toàn bộ hàng đợi.

**Ứng dụng khác:** Khi bộ phận xử lý dữ liệu đầu vào đang quá tải, có thể tạm xóa `OP_READ` bằng `interestOpsAnd(~SelectionKey.OP_READ)`, rồi thêm lại `OP_READ` khi có khả năng tiếp nhận dữ liệu. Đây là cách điều chỉnh **những sự kiện selector quan tâm**, không trực tiếp làm kênh không thể đọc hoặc đóng luồng dữ liệu.

## 8. Tính nguyên tử, đa luồng và `Selector.wakeup()`

### Tại sao `interestOpsAnd` tốt hơn read–modify–write thủ công?

Xem đoạn code:

```java
key.interestOps(key.interestOps()
        & ~SelectionKey.OP_WRITE);
```

Đây là hai thao tác riêng rẽ: **đọc interest set** rồi **ghi toàn bộ tập bit mới**. Nếu một thread khác thêm `OP_READ` hoặc `OP_WRITE` giữa hai bước, thao tác ghi cuối có thể làm mất cập nhật hợp lệ của thread đó.

`interestOpsAnd(~SelectionKey.OP_WRITE)` thực hiện phép **xóa bit dưới dạng một cập nhật nguyên tử** và được bảo đảm về tính nguyên tử đối với các lời gọi đồng thời `interestOpsAnd` và `interestOpsOr`. Nó phù hợp khi nhiều thành phần chỉ cần bật/tắt các bit riêng.

**Giới hạn quan trọng:** hợp đồng này **không bảo đảm mọi logic kết nối đều an toàn đa luồng**, cũng không biến bất kỳ chuỗi lời gọi nhiều bước nào thành giao dịch. Không trộn tùy tiện `interestOps(int)` (ghi đè toàn bộ tập) từ thread khác với các phép bật/tắt bit, vì có thể vẫn xảy ra cập nhật bị mất nếu tự viết read–modify–write.

### Thay đổi trong khi selector đang chờ

Các phương thức đổi interest set **không bắt một `select()` đang tiến hành tính lại ngay**. Java quy định thay đổi interest set trong một lần selection chỉ được sử dụng khi **lần selection tiếp theo** bắt đầu. Nếu sự kiện đến từ thread ngoài, có thể cần:

```java
key.interestOpsOr(SelectionKey.OP_WRITE);
key.selector().wakeup();
```

Đây là **đoạn minh họa trong code có key hợp lệ**. `wakeup()` làm một lần `select` đang chờ kết thúc sớm (hoặc làm lần chọn tiếp theo trả về sớm nếu chưa có lượt chọn đang chạy). Nó **không tự phát sinh `OP_WRITE`**, không đảm bảo socket sẵn sàng và không tự gửi dữ liệu.

### `isValid()` có đủ bảo đảm không?

Không. Trong hệ thống nhiều thread, một key có thể bị hủy **sau** khi bạn vừa kiểm tra `key.isValid()`. `interestOpsAnd` hoặc `readyOps()` lúc đó vẫn có thể ném `CancelledKeyException`. Thiết kế vòng đời kênh rõ ràng, bắt ngoại lệ ở ranh giới xử lý phù hợp và đừng cố dùng lại key đã hủy.

## 9. So sánh các cách cập nhật interest set

| API | Vai trò | Giá trị trả về | Khi dùng |
| --- | --- | --- | --- |
| `interestOps()` | Chỉ đọc tập bit quan tâm | `int` hiện tại | Kiểm tra trạng thái, logging/diagnostics |
| `interestOps(int ops)` | Gán **toàn bộ** tập bit mới | `SelectionKey` | Khi đã tính chính xác interest set mới và sở hữu việc điều phối |
| **`interestOpsAnd(int ops)`** | **AND nguyên tử** với mask | **`int` là giá trị cũ** | Bỏ từng cờ như `~OP_WRITE`, `~OP_READ` |
| `interestOpsOr(int ops)` | OR nguyên tử với mask | `int` là giá trị cũ | Bật từng cờ như `OP_WRITE` |
| `readyOps()` | Đọc tập bit đã phát hiện sẵn sàng | `int` | Phân nhánh xử lý I/O sau selection |
| `cancel()` | Hủy key, yêu cầu bỏ đăng ký | `void` | Kết thúc vòng đời đăng ký |
| `selector.wakeup()` | Đánh thức lượt selection | `Selector` | Khi một thread khác cần event loop xem lại yêu cầu |

**Đừng nhầm `interestOpsAnd(0)` với `cancel()`:** giá trị 0 chỉ tắt **sự quan tâm tới thao tác**. Key vẫn hợp lệ và vẫn gắn với selector, cho tới khi hủy hoặc đóng kênh/selector.

**Đừng nhầm interest với readiness:** `key.isWritable()` kiểm tra ready set, **không** kiểm tra xem ứng dụng hiện có đang quan tâm `OP_WRITE` hay không. Muốn kiểm tra interest set, dùng `(key.interestOps() & SelectionKey.OP_WRITE) != 0`. Tập ready có thể phản ánh một lần selection trước đó; không suy luận trạng thái mới của interest set chỉ từ `isWritable()`.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Xóa `OP_WRITE` nhưng các cờ khác cũng biến mất | Dùng `interestOpsAnd(SelectionKey.OP_WRITE)` hoặc `interestOps(0)` | Dùng **`interestOpsAnd(~SelectionKey.OP_WRITE)`** nếu chỉ muốn xóa WRITE |
| Không thể bật lại bit sau AND | `AND` chỉ giữ/xóa, không thêm bit | Dùng `interestOpsOr(SelectionKey.OP_WRITE)` |
| Gán biến `previous` rồi tưởng đó là tập mới | Hàm trả về **giá trị cũ** | Đọc lại `key.interestOps()` khi cần trạng thái mới |
| `IllegalArgumentException` khi thêm cờ | Kênh không hỗ trợ cờ được thêm | Kiểm tra `channel.validOps()`; không đăng ký `OP_WRITE` trên `Pipe.SourceChannel` |
| `CancelledKeyException` | Key bị hủy hoặc kênh/selector đã đóng | Kiểm soát vòng đời, không dùng key cũ |
| Selector liên tục báo WRITE, CPU cao | `OP_WRITE` luôn bật dù không có dữ liệu cần gửi | Xóa WRITE sau khi hàng đợi gửi rỗng |
| Selector không phản ứng ngay sau khi thread khác thêm việc | Interest mới chỉ có hiệu lực ở lượt selection kế tiếp, event loop còn chặn | Điều phối yêu cầu và dùng `selector.wakeup()` khi cần |
| Xóa bit interest nhưng `isReadable()/isWritable()` vẫn có thể báo true | Ready set có thể phản ánh lượt selection trước | Phân biệt ready set và interest set, xử lý đúng vòng đời selected keys |
| Đọc `selectedKeys()` lặp lại cùng một key | Chưa xóa phần tử đã xử lý | Với API `selectedKeys()`, dùng iterator và `remove()` |
| Cập nhật interest set đa luồng làm mất bit | Trộn read–modify–write thủ công với thao tác khác | Dùng các phép bit nguyên tử; tập trung quản lý state trong event-loop thread |
| Callback tự gọi `selector.select(...)` trên chính selector | Selection reentrant không được bảo đảm | Tránh gọi select lồng trong callback; để event loop chính điều phối các lượt chọn |
| Tin rằng ready WRITE bảo đảm ghi hết buffer | Readiness chỉ là gợi ý; `SocketChannel.write` có thể ghi 0 hoặc một phần | Kiểm tra vị trí `ByteBuffer`, xử lý partial write và giữ WRITE khi chưa gửi xong |

## 11. Bài tập thực hành

**Bài 1 — Dự đoán mask.** Một `SocketChannel` có interest set `OP_READ | OP_WRITE` (giá trị `5`). Hãy tính kết quả và giá trị trả về của:

```java
int before = key.interestOpsAnd(~SelectionKey.OP_WRITE);
```

Đáp án: `before == 5`, `key.interestOps() == 1`. Vì bit WRITE bị xóa và bit READ được giữ.

**Bài 2 — Giữ duy nhất READ.** Với interest set `OP_READ | OP_WRITE`, dự đoán kết quả của `interestOpsAnd(SelectionKey.OP_READ)`. Giải thích vì sao lệnh này **khác** `interestOpsAnd(~SelectionKey.OP_READ)`. Hai lệnh có thể lần lượt cho tập bit `READ` và `WRITE`.

**Bài 3 — Hủy và khôi phục.** Chạy `KeyMaskDemo.java`, đối chiếu các dòng trước/sau khi xóa READ và thêm lại READ. Giải thích vì sao `interestOpsAnd(0)` không hủy key, còn `key.cancel()` khiến các phương thức đọc/đổi interest ném `CancelledKeyException`.

**Bài 4 — Callback Java 11.** Chạy `SelectorActionDemo.java`. Mô tả vì sao callback được gọi qua `select(Consumer, timeout)`, tại sao chương trình phải xử lý `read()` không chặn, và khi nào `interestOpsAnd(~OP_READ)` có tác dụng đối với selector.

**Bài 5 — Tránh vòng lặp WRITE.** Thiết kế chính sách cho một socket gửi dữ liệu từ hàng đợi: lúc nào thêm `OP_WRITE`, lúc nào giữ lại khi ghi chưa hết, lúc nào xóa WRITE, và cách thread khác đánh thức event loop mà không làm mất buffer mới.

**Bài 6 — Kiểm tra thao tác không được hỗ trợ.** Với một `Pipe.SourceChannel`, so sánh `interestOpsAnd(~OP_WRITE)` và `interestOpsOr(OP_WRITE)`. Vì sao phép AND hợp lệ, còn phép OR phải từ chối?

### Checklist hoàn thành

- [ ] Biết `SelectionKey.interestOpsAnd(int)` được bổ sung ở Java 11 và vẫn có ích hiện nay.
- [ ] Phân biệt `interestOps`, `readyOps` và `selectedKeys`.
- [ ] Hiểu rõ **`old & mask`**, giá trị trả về là **old interest set**.
- [ ] Dùng `~OP_WRITE` để xóa WRITE mà giữ READ.
- [ ] Dùng `interestOpsOr` để bật lại cờ.
- [ ] Nêu được tính nguyên tử của AND/OR và giới hạn khi có logic đa bước.
- [ ] Giải thích `wakeup()`, hiệu lực ở selection tiếp theo và xử lý key bị cancel.
- [ ] Chạy các ví dụ trên JDK hiện hành với `javac --release 11`, hiểu ứng dụng của OP_WRITE để tránh vòng lặp bận.

## 12. Tài liệu tham khảo chính thức

1. [Java SE 11 — SelectionKey](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOpsAnd` (Since 11), `interestOpsOr`, `interestOps`, `readyOps`, `validOps`, `CancelledKeyException` và quy tắc interest/ready.
2. [Java SE 11 — Selector](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html): lựa chọn key, `selectedKeys()`, `select(Consumer)` và `wakeup()`; lưu ý concurrency và xử lý callbacks.
3. [Java SE 11 — SocketChannel](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SocketChannel.html): `validOps`, channel non-blocking và hành vi đọc/ghi.
4. [Java SE 11 — Pipe](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Pipe.html): `Pipe.SourceChannel` và `Pipe.SinkChannel` dùng để làm ví dụ độc lập.
5. [Java SE 25 — SelectionKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SelectionKey.html): xác nhận `interestOpsAnd` tiếp tục có trên JDK LTS hiện đại.

**Ghi nhớ:** `interestOpsAnd(~OP_WRITE)` là thao tác **xóa một bit interest một cách nguyên tử**, giữ những cờ khác và **trả lại giá trị cũ**. Nó rất hữu ích để bật/tắt sự quan tâm của selector theo trạng thái thật của ứng dụng, đặc biệt tránh lặp vô ích khi socket sẵn sàng ghi nhưng hàng đợi gửi đã rỗng. Để xử lý đúng trong hệ thống thực, cần kết hợp với sự khác biệt giữa interest và ready, điều phối event loop, `wakeup()` và quản lý vòng đời của `SelectionKey`.