# SelectionKey.interestOpsOr(int): bật interest atomically trong Selector callback (Java 11)

## Mục tiêu học tập

Trong Java NIO, ứng dụng thường có **một luồng chạy sự kiện của `Selector`** và các luồng khác tạo công việc gửi dữ liệu. Khi cần theo dõi thêm một loại sự kiện trên một kênh đã đăng ký, chúng ta phải **bật bit interest mới mà không vô tình xóa các bit đang theo dõi**. Java 11 bổ sung `SelectionKey.interestOpsOr(int)` để xử lý đúng trường hợp đó.

Sau bài học, bạn có thể:

1. Giải thích quan hệ **`SelectableChannel` → `Selector` → `SelectionKey`**, phân biệt `interestOps` với `readyOps`.
2. Đọc đúng hợp đồng `interestOpsOr(int)`: phép OR bit, tính nguyên tử, giá trị trả về, giới hạn các bit hợp lệ và ngoại lệ.
3. Bật một hoặc nhiều operation bits từ callback hoặc từ luồng khác; hiểu khi nào thay đổi được bộ chọn quan sát.
4. Kết hợp `interestOpsOr` với `interestOpsAnd` để bật/tắt `OP_READ`, `OP_WRITE` theo trạng thái I/O.
5. Dùng `Selector.select(Consumer<SelectionKey>)` của Java 11, xử lý callback an toàn và biết trường hợp phải gọi `Selector.wakeup()`.
6. Kiểm thử hành vi bằng chương trình Java độc lập với `Pipe`, bao gồm phép OR, AND, callback, bit không hỗ trợ và key bị hủy.

`interestOpsOr` có **Since: 11** trong Javadoc; API này vẫn xuất hiện trong đặc tả Java hiện đại và không phải một cơ chế đã bị loại bỏ.

## 1. Ngữ cảnh: một SelectionKey chứa những bit nào?

### 1.1. Đăng ký một kênh với selector

Khi đăng ký một `SelectableChannel` đã cấu hình non-blocking với `Selector`, Java trả về một `SelectionKey`. Key đại diện cho **mối quan hệ đăng ký giữa kênh và selector**; kênh có thể đăng ký với các selector khác nhau và mỗi đăng ký có key tương ứng.

~~~java
// Đoạn minh họa: selector và channel phải được tạo, đóng và xử lý IOException.
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

Một key có hai tập bit cần phân biệt:

- **Interest set (`key.interestOps()`):** những loại readiness mà ứng dụng muốn selector theo dõi ở lần chọn tiếp theo.
- **Ready set (`key.readyOps()`):** những loại readiness đã được selector phát hiện trong một lần chọn. Đây là dấu hiệu để thử I/O, **không phải bảo đảm** thao tác I/O chắc chắn không block trong mọi hoàn cảnh.

Javadoc định nghĩa các bit phổ biến:

| Bit | Ý nghĩa | Ví dụ kênh |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | Có kết nối cần được accept. | `ServerSocketChannel` |
| `SelectionKey.OP_CONNECT` | Kết nối bất đồng bộ đã sẵn sàng để hoàn tất hoặc gặp lỗi. | `SocketChannel` |
| `SelectionKey.OP_READ` | Có thể thử đọc, có EOF/đóng phía đọc hoặc lỗi cần xử lý. | `SocketChannel`, `Pipe.SourceChannel` |
| `SelectionKey.OP_WRITE` | Có thể thử ghi hoặc có tình trạng đóng/lỗi cần xử lý. | `SocketChannel`, `Pipe.SinkChannel` |

Không phải mọi kênh đều hỗ trợ mọi bit. Dùng `channel.validOps()` để lấy mask hợp lệ của **chính kênh đó**. Ví dụ `Pipe.SourceChannel` chỉ hỗ trợ `OP_READ`: đăng ký hoặc bật `OP_WRITE` trên source channel là sai.

Một đoạn mã có thể **quan tâm đến đọc** mà **chưa có dữ liệu để đọc**. Khi đó `key.interestOps()` chứa `OP_READ` nhưng `key.readyOps()` không nhất thiết chứa bit này. Chỉ sau một operation `select...` mới nên xem `key.isReadable()`/`readyOps()` như thông tin readiness của lần chọn.

### 1.2. Vì sao phải thay đổi interest trong quá trình chạy?

Giả sử một `SocketChannel` ban đầu cần đọc request từ client:

~~~java
key.interestOps(SelectionKey.OP_READ);
~~~

Sau đó bộ xử lý đã có dữ liệu gửi đi và muốn **bật thêm `OP_WRITE` nhưng vẫn giữ `OP_READ`**. Khi kết thúc gửi, cần **tắt riêng `OP_WRITE`**, không làm mất `OP_READ`.

Cách bật một bit bằng read-modify-write thủ công:

~~~java
// Có thể bị lost update nếu nhiều luồng cùng thay đổi interest set.
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
~~~

Câu lệnh này gồm bước đọc, tính OR và ghi set mới. Nếu một luồng khác thay đổi interest set giữa bước đọc và bước ghi, kết quả cuối có thể ghi đè thay đổi đó. **`interestOpsOr` giải quyết trực tiếp thao tác OR của interest set**.

## 2. Hợp đồng chính xác của `SelectionKey.interestOpsOr(int)`

Chữ ký API:

~~~java
public int interestOpsOr(int ops)
~~~

**Since: 11.** Ý nghĩa toán học tại một thời điểm cập nhật nguyên tử:

~~~text
previous = interestSetBeforeUpdate
interestSetAfterUpdate = previous | ops
return previous
~~~

Trong Java, dấu `|` là **bitwise OR**. Một bit bật ở bất kỳ toán hạng nào sẽ bật trong kết quả; những bit đang bật của interest set được giữ nguyên.

Ví dụ logic:

~~~text
Trước: OP_READ
Đưa vào: OP_WRITE
Sau:   OP_READ | OP_WRITE
Giá trị trả về: OP_READ
~~~

Ba điểm phải nhớ:

- `interestOpsOr` **trả về `int` là interest set cũ**, **không** trả về mask mới, boolean, hay chính `SelectionKey`. Muốn xem giá trị mới, gọi `key.interestOps()` sau khi cập nhật.
- Gọi lại với bit đã bật là thao tác **idempotent theo trạng thái mask**: `OP_READ | OP_READ = OP_READ`. Giá trị trả về vẫn là mask trước từng lần gọi.
- Tính nguyên tử được bảo đảm đối với **các lời gọi `interestOpsOr` hoặc `interestOpsAnd` đồng thời trên cùng key**. Điều đó không biến mọi chuỗi thao tác gồm `interestOps()`, `interestOps(int)` hay các bước cập nhật trạng thái ứng dụng thành một giao dịch nguyên tử.

### 2.1. So sánh các API thay đổi interest

| Phương thức | Thao tác | Giá trị trả về | Tình huống |
| --- | --- | --- | --- |
| `key.interestOps()` | Đọc mask interest hiện tại. | `int` mask hiện tại. | Quan sát/tracing. |
| `key.interestOps(mask)` | **Thay thế toàn bộ** interest set bằng `mask`. | `SelectionKey` hiện tại. | Cấu hình trạng thái mới khi đã kiểm soát quyền cập nhật. |
| `key.interestOpsOr(bits)` | **Bật thêm** bit: `old | bits`. | `int` mask **cũ**. | Thêm `OP_WRITE` khi có dữ liệu mới để gửi. |
| `key.interestOpsAnd(mask)` | **Giữ các bit giao nhau**: `old & mask`. | `int` mask **cũ**. | Tắt `OP_WRITE` bằng `~OP_WRITE` sau khi ghi hết dữ liệu. |

Ví dụ luân chuyển mask trong một kết nối socket có cả `OP_READ` và `OP_WRITE` hợp lệ:

~~~java
int previous = key.interestOpsOr(SelectionKey.OP_WRITE);
int now = key.interestOps();

key.interestOpsAnd(~SelectionKey.OP_WRITE); // tắt riêng OP_WRITE
~~~

Đây là **đoạn phương thức minh họa**, giả định `key` là key hợp lệ của `SocketChannel`. Phép `~` là bitwise NOT; `~OP_WRITE` có nhiều bit bằng 1, nhưng dùng với `interestOpsAnd` được phép để **xóa một bit** mà không thêm các bit khác.

**Không** thay dòng xóa bit bằng `key.interestOpsOr(~OP_WRITE)`: phép OR với mask đảo có thể chứa các bit không được kênh hỗ trợ và gây `IllegalArgumentException`, đồng thời không thể dùng OR để tắt bit.

### 2.2. Kiểm tra bit được phép bật

Trước khi bật bit mới, phải biết kênh hỗ trợ gì:

~~~java
int valid = key.channel().validOps();
int toEnable = SelectionKey.OP_WRITE;
boolean supported = (toEnable & ~valid) == 0;
~~~

Đoạn trên chỉ là **kiểm tra mask**, không chứng minh channel đang mở hoặc key còn hợp lệ tại thời điểm cập nhật. `interestOpsOr(int)` tự áp dụng kiểm tra bắt buộc; nếu `ops` có bất kỳ bit nào ngoài `channel().validOps()`, nó ném `IllegalArgumentException`. Nếu key đã bị hủy, nó có thể ném `CancelledKeyException`.

Ví dụ: `Pipe.SourceChannel` hỗ trợ `OP_READ`, không hỗ trợ `OP_WRITE`. Bởi vậy `sourceKey.interestOpsOr(OP_WRITE)` là một case lỗi có thể test mà không cần kết nối mạng.

### 2.3. `interestOpsOr(0)` và kiểm tra mask hiện tại

OR với số 0 không bật bit mới:

~~~java
int previous = key.interestOpsOr(0);
int current = key.interestOps();
~~~

Nếu không có luồng khác sửa key giữa hai lệnh, `previous == current`. Trong môi trường đồng thời, **không** biến so sánh hai phép gọi riêng lẻ thành giả định nhất quán tuyệt đối: một luồng khác có thể đã cập nhật mask trước lệnh đọc `interestOps()`.

## 3. Quan hệ với Selector callback của Java 11

### 3.1. Cách nhận sự kiện bằng Consumer

Java 11 có phương thức:

~~~java
public int select(Consumer<SelectionKey> action, long timeout)
        throws IOException
~~~

Nó chờ kênh sẵn sàng hoặc đến thời hạn rồi gọi callback nhận `SelectionKey` của từng kênh được phát hiện. `timeout` dương là số mili giây tối đa theo hợp đồng (không bảo đảm thời gian thực cứng); `timeout == 0` nghĩa là có thể chờ vô hạn. Giá trị trả về là **số key duy nhất được xử lý**, có thể là 0.

Ví dụ callback kiểm tra `readyOps` rồi điều chỉnh `interestOps`:

~~~java
selector.select(key -> {
    if (!key.isValid()) {
        return;
    }
    if (key.isReadable()) {
        // Đọc từ channel của key; xử lý IOException tại đây.
        // Khi chủ động ngừng theo dõi đọc:
        key.interestOpsAnd(~SelectionKey.OP_READ);
    }
}, 1_000);
~~~

Đây là **đoạn minh họa callback**, không phải chương trình độc lập; mã I/O thực phải xử lý kênh, buffer, EOF và ngoại lệ theo giao thức.

Callback **có thể được gọi nhiều lần với cùng một key trong một lần selection**, mỗi lần với tập ready operations khác nhau nếu kênh sẵn sàng nhiều loại thao tác. Kiểm tra `key.isReadable()`, `key.isWritable()`... trước khi xử lý từng loại. `isReadable()` đọc **ready set**, không phải chỉ đơn thuần kiểm tra bạn đã bật `OP_READ` trong interest set.

Tài liệu `Selector.select(Consumer, long)` còn nêu:

- Callback được gọi trong khi đồng bộ hóa trên selector và selected-key set. **Không gọi lồng `select` trên cùng selector trong callback**; hành vi reentrant không được đặc tả và có nguy cơ deadlock.
- Callback được phép hủy key, đóng channel hoặc thay đổi interest set. Tuy vậy nếu một key bị hủy hay đổi interest trước khi action chạy, implementation có thể vẫn gọi action với key không hợp lệ; nên kiểm tra `key.isValid()` khi thích hợp.
- Không giữ callback quá lâu hoặc thực hiện tác vụ blocking không kiểm soát, vì nó làm chậm xử lý các kênh khác. Với network I/O, channel cần được cấu hình **non-blocking**.
- API callback xử lý key theo hành động truyền vào. Không nên dựa vào giả định tùy tiện rằng `selectedKeys()` chắc chắn rỗng sau mọi cách triển khai: Javadoc về default implementation cho phép trạng thái selected-key set tùy implementation.

### 3.2. Thay interest trong callback có hiệu lực lúc nào?

Javadoc `SelectionKey.interestOpsOr` và `Selector` nêu rõ: nếu cập nhật interest khi một **selection operation đang diễn ra**, cập nhật **không ảnh hưởng đến operation đó**. Giá trị interest mới sẽ được quan sát ở **selection operation tiếp theo**.

Do đó:

~~~java
selector.select(key -> {
    if (key.isReadable()) {
        // Xử lý một lần sẵn sàng đọc.
        key.interestOpsAnd(~SelectionKey.OP_READ);
        // Không giả định readyOps() lập tức trở thành 0.
    }
}, 1_000);
~~~

Tắt `OP_READ` ở đây là thay **interest set tương lai**, không phải xóa lịch sử ready event đã khiến callback được gọi. Thay đổi `interestOps` cũng **không** phải lệnh trực tiếp «thực hiện read/write», «gửi dữ liệu» hay «hủy key». Kênh vẫn được đăng ký cho đến khi hủy key hoặc đóng tài nguyên liên quan.

## 4. Luồng khác bật interest: cần xét `wakeup()`

Trong server bất đồng bộ, một luồng producer có thể đưa dữ liệu mới vào hàng chờ trong khi luồng event loop đang chặn tại `selector.select()`. Với một `SocketChannel` hợp lệ hỗ trợ `OP_WRITE`, producer có thể **bật theo dõi ghi**:

~~~java
// Đoạn minh họa trong producer: key là registration của SocketChannel.
pendingOutboundQueue.add(buffer); // Queue phải có cơ chế đồng bộ phù hợp.
try {
    key.interestOpsOr(SelectionKey.OP_WRITE);
    key.selector().wakeup();
} catch (CancelledKeyException ignored) {
    // Kết nối đã đóng: xử lý/hủy dữ liệu chờ theo chính sách ứng dụng.
}
~~~

Tại sao gọi `wakeup()`? Bật bit interest không có nghĩa một selection đang block sẽ tự được đánh thức ngay để xét bit mới. `Selector.wakeup()` khiến một lượt selection đang chờ (hoặc lượt chờ kế tiếp trong một số trường hợp) trả về sớm để event loop tiến hành kiểm tra lại. **`wakeup()` không tự gọi callback và không bảo đảm có một event ghi mới**; luồng event loop vẫn phải thực hiện các lượt `select` tiếp theo.

Đoạn minh họa chỉ nêu thao tác **bật interest + đánh thức selector**. Hàng đợi gửi phải có thiết kế đồng bộ, thứ tự ghi và quản lý connection state đúng cách. Tính nguyên tử của `interestOpsOr` **không thay thế** bảo đảm của hàng đợi, không xử lý thay race giữa việc thêm/đọc hết buffer và không tự quyết định ai sở hữu channel. Trong thực tế nên quy định nhất quán event loop hay luồng producer được phép sửa mask và trạng thái output.

### 4.1. Vì sao không bật `OP_WRITE` thường trực?

Với socket đang kết nối, khả năng ghi thường xuyên ở trạng thái ready. Nếu để `OP_WRITE` bật cả khi **không có dữ liệu gửi**, event loop có thể liên tục nhận sự kiện writable và sử dụng CPU vô ích.

Mô hình phổ biến:

1. Khi producer thêm dữ liệu cần gửi, **bật `OP_WRITE`** bằng `interestOpsOr(OP_WRITE)` và `wakeup()` nếu cập nhật từ luồng khác.
2. Khi key writable, event loop cố gắng ghi từ queue bằng `SocketChannel.write(ByteBuffer)` theo cơ chế non-blocking; một lần ghi có thể ghi **ít hơn** số byte đang chờ.
3. Nếu buffer còn bytes, **giữ `OP_WRITE`** và thử ghi tiếp ở event tiếp theo.
4. Khi không còn dữ liệu chờ **và đã xử lý đồng bộ với producer**, **tắt riêng `OP_WRITE`** bằng `interestOpsAnd(~OP_WRITE)` để tránh busy loop.

Không đóng channel hoặc hủy key chỉ vì một lần `write` trả về 0: đối với non-blocking channel, ghi chưa tiến triển có thể là trạng thái bình thường. Phân biệt kết nối đóng/hỏng theo API và giao thức.

### 4.2. Ví dụ code minh họa trong handler

~~~java
// Đặt trong một class quản lý một SocketChannel hợp lệ.
// pending là ByteBuffer đã nạp dữ liệu để gửi, ở chế độ đọc.
void onWritable(SelectionKey key, ByteBuffer pending) throws IOException {
    SocketChannel channel = (SocketChannel) key.channel();
    channel.write(pending);
    if (!pending.hasRemaining()) {
        key.interestOpsAnd(~SelectionKey.OP_WRITE);
    }
}
~~~

Đây là **phương thức minh họa**, chưa có đầy đủ queue, đồng bộ, vòng đời channel hay logic EOF. Dùng chỉ khi đã có cơ chế bảo đảm mọi buffer chờ được gửi hết, và tránh race khi luồng khác vừa thêm dữ liệu. Trong một event loop do một luồng sở hữu, có thể gom việc thêm/xóa interest cùng xử lý queue vào luồng đó để kiểm soát thứ tự.

## 5. Ví dụ runnable: Pipe + SelectionKey + callback

Chương trình sau **không cần mạng**, dùng `Pipe.SourceChannel` (chỉ hỗ trợ `OP_READ`) làm kênh đăng ký và `Pipe.SinkChannel` để gửi hai byte. Nhờ đó ta kiểm thử được cả phép OR, phép AND, callback thật, lỗi bit không hỗ trợ và key bị hủy.

Tạo file **InterestOpsOrDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.CancelledKeyException;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.util.concurrent.atomic.AtomicInteger;

public class InterestOpsOrDemo {
    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();
        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {
            source.configureBlocking(false);
            SelectionKey key = source.register(selector, 0);

            int old = key.interestOpsOr(SelectionKey.OP_READ);
            check(old == 0 && key.interestOps() == SelectionKey.OP_READ,
                    "OR must enable OP_READ and return the previous set");
            int again = key.interestOpsOr(SelectionKey.OP_READ);
            check(again == SelectionKey.OP_READ,
                    "OR with an existing bit is idempotent");
            System.out.println("PASS OR returns previous set");

            boolean invalidRejected = false;
            try {
                key.interestOpsOr(SelectionKey.OP_WRITE);
            } catch (IllegalArgumentException expected) {
                invalidRejected = true;
            }
            check(invalidRejected, "source channel cannot select OP_WRITE");
            System.out.println("PASS invalid operation rejected");

            int beforeClear = key.interestOpsAnd(~SelectionKey.OP_READ);
            check(beforeClear == SelectionKey.OP_READ && key.interestOps() == 0,
                    "AND must clear only OP_READ");
            System.out.println("PASS AND clears a bit");

            key.interestOpsOr(SelectionKey.OP_READ);
            ByteBuffer output = ByteBuffer.wrap(new byte[] {65, 66});
            while (output.hasRemaining()) sink.write(output);

            AtomicInteger callbackCalls = new AtomicInteger();
            AtomicInteger byteCount = new AtomicInteger();
            int selected = selector.select(readyKey -> {
                if (!readyKey.isValid() || !readyKey.isReadable()) return;
                try {
                    ByteBuffer input = ByteBuffer.allocate(8);
                    int read = ((Pipe.SourceChannel) readyKey.channel()).read(input);
                    byteCount.set(read);
                    readyKey.interestOpsAnd(~SelectionKey.OP_READ);
                    callbackCalls.incrementAndGet();
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            }, 1000);
            check(selected == 1 && callbackCalls.get() == 1 && byteCount.get() == 2,
                    "selector callback must consume two bytes");
            check(key.interestOps() == 0, "callback must disarm OP_READ");
            System.out.println("PASS select callback consumes data");

            key.cancel();
            boolean cancelledRejected = false;
            try {
                key.interestOpsOr(SelectionKey.OP_READ);
            } catch (CancelledKeyException expected) {
                cancelledRejected = true;
            }
            check(cancelledRejected, "cancelled key must reject interestOpsOr");
            System.out.println("PASS cancelled key rejected");
            System.out.println("ALL INTEREST OPS TESTS PASSED");
        }
    }
}
~~~

Chạy trên **JDK 11 hoặc JDK mới hỗ trợ target 11**:

~~~bash
javac --release 11 -encoding UTF-8 InterestOpsOrDemo.java
java InterestOpsOrDemo
~~~

Đầu ra chính xác khi thành công:

~~~text
PASS OR returns previous set
PASS invalid operation rejected
PASS AND clears a bit
PASS select callback consumes data
PASS cancelled key rejected
ALL INTEREST OPS TESTS PASSED
~~~

Phân tích trình tự:

1. Source channel ở chế độ non-blocking đăng ký với interest set `0`. `interestOpsOr(OP_READ)` trả `0` và bật `OP_READ`.
2. Gọi OR `OP_READ` lần nữa không thay mask, và trả về mask cũ `OP_READ`.
3. Cố bật `OP_WRITE` trên `Pipe.SourceChannel` gây `IllegalArgumentException` vì `validOps()` không chứa bit đó.
4. `interestOpsAnd(~OP_READ)` trả mask cũ `OP_READ`, rồi đưa interest set về `0`.
5. Bật lại `OP_READ`; sink ghi hai byte ASCII `A`, `B` vào pipe. `Selector.select(action, 1000)` quan sát readiness và chạy callback. Callback đọc hai byte, tắt `OP_READ` cho lần chọn sau.
6. `key.cancel()` khiến key không còn hợp lệ. Lời gọi `interestOpsOr(OP_READ)` tiếp theo phải ném `CancelledKeyException`.

Trong ví dụ này chỉ một source channel đăng ký `OP_READ`, và bytes được ghi trước khi gọi `select`, nên callback được mong đợi chạy một lần. Điều đó **không** là khẳng định tất cả `select(Consumer)` trên mọi tập kênh đều chỉ gọi callback một lần cho mỗi key. Chương trình dùng `check` ném `AssertionError`, nên các phép thử không bị tắt khi thiếu cờ `-ea`.

`AtomicInteger` ở đây giúp ghi nhận kết quả từ lambda bằng đối tượng thay đổi được; chương trình chạy callback trên luồng gọi `select`. Điều đó **không** minh họa việc callback tự động chạy trên một luồng mới: `Selector.select(Consumer)` là phép gọi đồng bộ của luồng đang thực hiện selection.

## 6. Lỗi phổ biến và cách khắc phục

| Lỗi | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Tưởng giá trị trả về của `interestOpsOr` là mask mới. | Logic kiểm tra sai giá trị sau khi bật bit. | Nhớ **return = previous interest set**; dùng `key.interestOps()` để xem mask hiện tại. |
| Dùng `interestOps(int)` để bật thêm một bit nhưng chỉ truyền `OP_WRITE`. | Vô tình xóa `OP_READ` đã bật. | Dùng `interestOpsOr(OP_WRITE)` khi muốn thêm bit. |
| Dùng `interestOps(key.interestOps() | bit)` giữa nhiều luồng. | Có thể ghi đè bản cập nhật khác. | Dùng `interestOpsOr`/`interestOpsAnd` cho thao tác bit tương ứng; tổ chức ownership rõ ràng. |
| Dùng `interestOpsOr(~OP_WRITE)` để «tắt» bit ghi. | Có thể ném `IllegalArgumentException` và không đúng phép toán. | Dùng `interestOpsAnd(~OP_WRITE)`. |
| Bật `OP_WRITE` trên `Pipe.SourceChannel`. | `IllegalArgumentException`. | Đối chiếu `channel.validOps()`; `SourceChannel` chỉ hỗ trợ đọc. |
| Nhầm `interestOps()` với `readyOps()`. | Xử lý I/O khi chưa có readiness tương ứng hoặc hiểu sai callback. | Dùng interest để đăng ký nhu cầu; trong callback kiểm `isReadable/isWritable` rồi thực hiện I/O. |
| Giả định cập nhật interest tác động ngay lượt `select` đang chạy. | Sự kiện mới không xuất hiện trong cùng callback/lượt chọn. | Giá trị mới được xem xét ở **selection operation tiếp theo**. |
| Từ producer bật interest nhưng không đánh thức selector đang block. | Event loop có thể tiếp tục chờ theo interest cũ. | Khi phù hợp, gọi `selector.wakeup()` sau cập nhật và để event loop tiếp tục chọn. |
| Để `OP_WRITE` bật khi queue gửi rỗng. | Có thể nhận writable readiness liên tục, tiêu tốn CPU. | Chỉ bật khi có dữ liệu cần gửi; tắt sau khi đã gửi hết và đồng bộ với producer. |
| Coi phép OR nguyên tử là toàn bộ giao thức thread-safe. | Race với queue, callback hoặc hủy key. | Phân định luồng sở hữu trạng thái, đồng bộ queue và xử lý `CancelledKeyException`. |
| Gọi lồng `select` từ callback cùng selector. | Hành vi không được đặc tả, có thể deadlock. | Xử lý callback ngắn và để vòng event loop gọi `select` tiếp. |
| Không xử lý key bị hủy/đóng kênh. | `CancelledKeyException` hoặc lỗi I/O. | Quản lý lifecycle; kiểm `isValid` khi cần và xử lý ngoại lệ/race. |

## 7. Cách kiểm thử trong dự án thật

Ví dụ ở trên xác nhận **hợp đồng API** bằng một kênh duy nhất. Đối với hệ thống dùng `SocketChannel` và luồng producer, nên bổ sung:

- **Mask không bị mất:** sau khi bật `OP_WRITE`, những bit interest có trước vẫn còn; sau `interestOpsAnd(~OP_WRITE)`, các bit khác không bị xóa.
- **Đúng kênh/bit:** thử một bit có trong `validOps` và một bit nằm ngoài `validOps`.
- **Luồng producer + event loop:** producer đưa buffer vào queue, bật `OP_WRITE`, gọi `wakeup`; event loop chuyển dữ liệu và tắt `OP_WRITE` khi queue thật sự rỗng. Chạy lặp nhiều lần để tìm race, không dùng một lần thành công làm chứng minh mọi lịch trình đồng thời đều đúng.
- **Ghi một phần:** với `SocketChannel` non-blocking, kiểm cả trường hợp `write(ByteBuffer)` ghi ít bytes hoặc trả 0; không làm mất vị trí buffer và không tắt `OP_WRITE` sớm.
- **Đóng kết nối đồng thời:** producer có thể đang bật interest khi event loop hủy key; xử lý `CancelledKeyException` và giải phóng buffer theo quy tắc ứng dụng.
- **Độ tải của event loop:** nếu không có output chờ, `OP_WRITE` không nên tạo vòng lặp CPU bận; đo số callback/selection trong test hoặc metrics thực tế.

Không nên viết một bài test «chứng minh tuyệt đối tính nguyên tử» chỉ bằng một lượt chạy hai thread: **bảo đảm nguyên tử là hợp đồng Javadoc**; test đa luồng giúp phát hiện lỗi tích hợp giữa queue, wakeup và lifecycle, nhưng không thể mô phỏng hết lịch trình thread.

### Câu hỏi tự đánh giá

**1.** Interest set hiện tại là `OP_READ`. Gọi `key.interestOpsOr(OP_WRITE)` trả gì, mask mới là gì?

**Đáp án:** Trả về **`OP_READ`**, còn mask mới là **`OP_READ | OP_WRITE`**, giả định channel hỗ trợ cả hai bit và key hợp lệ.

**2.** Khi buffer outbound đã gửi hết, tại sao phải dùng `interestOpsAnd(~OP_WRITE)`?

**Đáp án:** Để bỏ riêng interest ghi, tránh xử lý writable event liên tục trong khi vẫn giữ các interest khác như `OP_READ`.

**3.** Có thể tin rằng `interestOpsOr(OP_WRITE)` từ một luồng khác sẽ lập tức đánh thức `Selector.select()` không?

**Đáp án:** Không. Thay interest không tự cam kết đánh thức một selection đang chặn; khi cần prompt event loop, dùng `selector.wakeup()` và thiết kế vòng lặp xem xét interest mới.

**4.** Nếu callback gọi `key.interestOpsAnd(~OP_READ)`, `key.isReadable()` của callback đang chạy có lập tức thành `false` không?

**Đáp án:** Không được suy luận như vậy. `isReadable()` dựa trên **ready set của selection**, còn `interestOpsAnd` sửa **interest set dành cho các lượt chọn sau**.

**5.** `Pipe.SourceChannel` có thể `interestOpsOr(OP_WRITE)` không?

**Đáp án:** Không; bit không hợp lệ với source channel và phương thức ném `IllegalArgumentException`.

**6.** `interestOpsOr` được bảo đảm nguyên tử với những lời gọi nào?

**Đáp án:** Các lời gọi `interestOpsOr` hoặc `interestOpsAnd` đồng thời trên **cùng key**. Không nên suy rộng bảo đảm sang mọi đoạn code read-modify-write hay trạng thái queue bên ngoài.

**7.** Nếu key bị hủy giữa lúc producer kiểm `isValid()` và gọi `interestOpsOr(...)` thì sao?

**Đáp án:** Đây là race bình thường cần tính đến. Dù đã kiểm `isValid()` trước, lời gọi cập nhật vẫn có thể ném `CancelledKeyException`; ứng dụng phải xử lý theo lifecycle của connection.

## 8. Checklist hoàn thành

- [ ] Giải thích được ý nghĩa **interest set**, **ready set** và `validOps()`.
- [ ] Dùng `interestOpsOr(bits)` để **bật thêm** bit và nhớ **giá trị trả về là mask cũ**.
- [ ] Dùng `interestOpsAnd(~bits)` để **tắt** bit mà giữ các bit khác.
- [ ] Biết khi nào sử dụng `selector.wakeup()` sau cập nhật từ luồng khác.
- [ ] Biết cập nhật interest trong callback **chỉ tác động đến selection operation sau**.
- [ ] Không gọi reentrant selection trên cùng selector trong callback.
- [ ] Tạo key hợp lệ bằng `configureBlocking(false)` và `register` trước khi sửa interest.
- [ ] Chạy được `InterestOpsOrDemo.java` với `javac --release 11`, PASS tất cả các case OR/AND/callback/invalid/cancelled.
- [ ] Xác định chiến lược đồng bộ queue và xử lý partial write khi dùng `OP_WRITE` trong sản phẩm.

## Tài liệu chính thức

- [Java SE 11 — SelectionKey: interestOpsOr, interestOpsAnd, interestOps và readyOps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Java SE 11 — Selector: select(Consumer), callback, đồng thời và wakeup](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 11 — SelectableChannel: register và validOps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [Java SE 11 — Pipe: SourceChannel và SinkChannel](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Pipe.html)
- [Java SE 11 — SocketChannel: non-blocking read/write](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 26 — SelectionKey (đối chiếu API tiếp tục được hỗ trợ ở JDK mới)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SelectionKey.html)
