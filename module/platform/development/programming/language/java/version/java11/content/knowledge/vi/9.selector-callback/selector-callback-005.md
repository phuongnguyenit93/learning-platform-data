# Giới hạn đồng bộ và thao tác trong Selector callback (Java 11+)

> **Phạm vi:** `java.nio.channels.Selector`, nhất là các overload nhận `Consumer<SelectionKey>` được giới thiệu từ **Java 11**: `select(action)`, `select(action, timeout)` và `selectNow(action)`. Trọng tâm là **khóa đồng bộ đang được giữ trong callback**, thao tác được phép và thao tác nên tránh. Các quy tắc này vẫn áp dụng trên JDK hiện đại.

## 1. Điều quan trọng nhất: callback chạy trong vùng đồng bộ của Selector

Khi gọi:

~~~java
int count = selector.select(key -> {
    // Xử lý một SelectionKey sẵn sàng I/O
}, 1000);
~~~

`Selector` thực hiện một vòng lựa chọn kênh (*selection*) và gọi `Consumer.accept(key)` cho những key được báo sẵn sàng. **Callback chạy đồng bộ trong chính lời gọi `select(...)`**, trên luồng đang gọi `select`; API không tự mở một luồng xử lý khác cho từng key.

Đặc biệt, Javadoc nêu rõ **`accept` được gọi trong lúc đồng bộ trên đối tượng `selector` và tập `selectedKeys()`**. Các selection operation khóa theo thứ tự:

1. Monitor của **selector**;
2. Monitor của **selected-key set**.

Selector còn đồng bộ trên cancelled-key set trong các giai đoạn xử lý key bị hủy, nhưng ứng dụng không được truy cập trực tiếp tập đó.

Vì vậy, một callback dài, gọi I/O chặn, đợi một tác vụ khác, hoặc cố chạy `select` lồng vào chính selector có thể cản trở vòng I/O và gây deadlock. Đừng xem callback như một `Consumer` bình thường có thể làm việc tùy ý mà không ảnh hưởng tới hệ thống.

**Nguyên tắc thực hành:** trong callback, kiểm tra key, thực hiện lượng I/O **không chặn** và có giới hạn, cập nhật trạng thái cần thiết, rồi trả quyền điều khiển cho `Selector` nhanh nhất có thể.

## 2. Phân biệt ba overload callback và vòng chọn key truyền thống

| API | Chặn hay không | Cách nhận key |
| --- | --- | --- |
| `selector.select(action)` | Có thể chặn đến khi có sự kiện, `wakeup` hoặc interrupt | Trực tiếp gọi `action.accept(key)` |
| `selector.select(action, timeout)` | `timeout > 0`: chặn tối đa gần khoảng thời gian đó; `timeout == 0`: chặn vô hạn theo hợp đồng | Trực tiếp gọi callback |
| `selector.selectNow(action)` | Không chờ sự kiện mới | Trực tiếp gọi callback với key sẵn sàng tại thời điểm chọn |
| `selector.select()` / `select(timeout)` / `selectNow()` | Tùy overload | Cập nhật tập `selector.selectedKeys()` để **caller tự duyệt/xóa** |

**Khác biệt quyết định:** các overload nhận `Consumer` **không dùng selected-key set như cơ chế để trả key cho bạn**; API gọi callback trực tiếp. Các overload truyền thống đưa key vào selected-key set và người gọi thường duyệt tập đó rồi loại key đã xử lý khỏi tập.

Tuy nhiên, **đừng suy ra** sau `select(action)` thì `selectedKeys()` luôn rỗng với mọi implementation. Javadoc của *default implementation* cho phép tập này còn phần tử sau khi hoàn tất. Việc xử lý callback phải dựa vào tham số `key` được truyền vào, **không phụ thuộc kích thước/tình trạng của `selectedKeys()`**.

Giá trị trả về của callback-overload là **số key phân biệt đã được xử lý** (*number of unique keys consumed*), không nhất thiết bằng tổng số lần `action.accept` được gọi. Với một key có nhiều operation sẵn sàng, callback **có thể được gọi nhiều lần cho cùng key** với các tập `readyOps` con khác nhau.

## 3. Vì sao khóa đồng bộ giới hạn những việc được làm?

Một `Selector` cho phép một luồng chờ nhiều kênh I/O; cách vận hành thường gọi là **event loop**. Nếu một callback giữ vùng synchronized lâu, nó kéo dài chính một vòng lựa chọn và khiến các thao tác khác cần monitor tương ứng phải chờ.

### 3.1. Khóa nào đang được giữ?

Trong lúc callback được gọi, API bảo đảm việc đồng bộ theo thứ tự **selector → selected-key set**. Những mã khác sử dụng `synchronized(selector)`, `synchronized(selector.selectedKeys())` hoặc các phương thức phải đồng bộ trên chúng có thể bị ảnh hưởng.

- `Selector.close()` cũng đồng bộ theo thứ tự selector rồi selected-key set; đóng từ **luồng khác** có thể phải chờ cho đến khi callback kết thúc.
- Việc chọn key khác trên cùng selector cần vùng khóa của selector; không thể giả định hai lời gọi `select` có thể xử lý song song trên cùng một selector.
- Các callback dài còn khiến kênh khác đã sẵn sàng phải đợi trong cùng event loop, làm tăng độ trễ của toàn bộ hệ thống.
- `keys()` có quy tắc an toàn luồng riêng; không được lấy điều đó làm lý do để bỏ qua khóa được giữ khi callback chạy.

**Đồng bộ của JDK bảo vệ trạng thái selector**, không có nghĩa ứng dụng được phép chặn tùy ý trong callback hay tự động an toàn khi sử dụng mọi object gắn trong `SelectionKey. Trạng thái ứng dụng vẫn cần chính sách sở hữu và đồng bộ rõ ràng.

### 3.2. Deadlock do đảo thứ tự khóa

Xét tình huống có khóa ứng dụng `appLock`:

~~~text
Luồng event loop (A)                       Luồng quản lý (B)
─────────────────────                      ─────────────────────
select(action) đã giữ monitor selector    synchronized(appLock) đã giữ appLock
và selected-key set                       ↓
↓                                         gọi selector.close()
callback gọi synchronized(appLock)        ↓
↓                                         đợi monitor selector
đợi appLock đang do B giữ                 ↓
A đợi B                                    B đợi A  => deadlock
~~~

Đây là ví dụ cơ chế có thể xảy ra, không phải chương trình cần chạy. Đảo thứ tự khóa giữa **selector** và **appLock** tạo vòng chờ.

Cách tránh:

- Hạn chế lấy khóa ứng dụng trong callback, đặc biệt khóa cũng được luồng khác giữ khi gọi `close`, đăng ký channel hoặc thao tác với selector.
- Không `wait`, `join`, `Future.get` hay chờ kết quả tác vụ khác trong callback.
- Không nắm `appLock` khi một luồng khác phải gọi phương thức có thể chờ selector; thiết kế một **hàng đợi lệnh** để event loop xử lý thay.
- Nếu buộc phải có nhiều khóa, cần quy ước thứ tự khóa toàn hệ thống và kiểm thử tình huống shutdown/concurrency; ưu tiên cách thiết kế không cần chia sẻ monitor.

## 4. Tuyệt đối tránh select lồng trên cùng selector

Không viết:

~~~java
selector.select(key -> {
    // SAI về thiết kế: selection reentrant trên cùng selector.
    selector.selectNow(otherKey -> {
        // ...
    });
});
~~~

Đây là **mẫu sai minh họa**, không phải đoạn mã nên chạy. Javadoc nêu rõ **selection operations không bảo đảm reentrant**; hành vi gọi một selection operation lồng trên chính selector từ callback là **implementation-specific/không được đặc tả**. Nó có thể làm rối ready set, callback và trạng thái selection.

Dù monitor `synchronized` của Java hỗ trợ reentrancy cho **cùng luồng**, điều đó **không biến `Selector.select` thành API reentrant**. Tính reentrant của monitor và tính reentrant của thuật toán selection là hai chuyện khác nhau.

Cách đúng là:

1. Cho callback hoàn thành nhanh.
2. Trả về event loop chính.
3. Tiếp tục gọi `select` trong **vòng lặp kế tiếp** khi thích hợp.

Tránh cả gọi gián tiếp: ví dụ callback gọi một helper “pollReady()” nhưng helper ấy lại gọi `selector.selectNow(...)` trên cùng instance.

## 5. Những thao tác được phép theo hợp đồng API

Đừng nhầm “callback giữ khóa” với “callback bị cấm mọi thao tác liên quan đến key”. Javadoc nói rõ một số thao tác vẫn **được phép**, nhưng cần hiểu hậu quả và giới hạn công việc.

| Thao tác bên trong callback | Hợp đồng | Hướng dùng thực tế |
| --- | --- | --- |
| `key.isValid()` | Được phép kiểm tra trạng thái | Kiểm trước `readyOps()` / `isReadable()` / `interestOps()` |
| `key.readyOps()` / `key.isReadable()` / `isWritable()` | Đọc các bit được báo sẵn sàng | Chỉ thực hiện I/O trên thao tác hợp lệ; xử lý key có thể bị hủy đồng thời |
| `channel.read(...)` / `write(...)` trên selectable channel **nonblocking** | Có thể thực hiện | Mỗi callback xử lý một lượng **có giới hạn**; chấp nhận partial I/O hoặc trả 0 |
| `key.interestOps(newOps)` | **Được phép** thay interest set | Thay đổi trong vòng selection hiện tại **chỉ có hiệu lực ở vòng selection kế tiếp** |
| `key.cancel()` | **Được phép** hủy key | Key trở nên invalid; việc deregister và dọn khỏi các tập xảy ra theo quy trình selection |
| `key.channel().close()` | **Được phép** đóng channel đã đăng ký | Channel bị đóng, key bị hủy; tránh sử dụng key như còn hợp lệ sau đó |
| `selector.close()` | Có thể được gọi, **nhưng gây `ClosedSelectorException` khi callback hoàn tất** | Thường nên điều phối đóng **ngoài callback**, khi event loop kết thúc |
| Gọi `selector.select(...)` / `selectNow(...)` trên **chính selector** | Hành vi reentrant **không được đặc tả** | Tránh hoàn toàn |
| Thao tác lâu, khóa ứng dụng, I/O chặn hoặc chờ tương lai | Không bị cú pháp Java ngăn, nhưng gây rủi ro tiến độ và deadlock | Đưa sang worker hoặc xử lý sau vòng selection |
| Sửa `selector.selectedKeys()` trong callback | Tập không thread-safe; callback API không yêu cầu quản lý tập này | Không dùng tập này như hàng đợi callback |

**Thay đổi `interestOps`:** ví dụ một socket có dữ liệu xuất cần bật `OP_WRITE`, sau khi gửi hết thì tắt bit đó để tránh callback ghi lặp không cần thiết. Việc thay đổi trong callback là hợp lệ, nhưng selection hiện tại đã chốt các điều kiện readiness theo quy tắc của nó; đừng yêu cầu bit mới tác động tức thì lên callback đang chạy.

**Hủy key:** `cancel()` làm `isValid()` trả `false`; key có thể vẫn tạm hiện diện trong các tập cho tới khi selection xử lý hủy. Không dùng “key có trong một tập” như chứng minh channel vẫn mở.

## 6. Key không chắc còn valid khi callback nhận được

Trong hệ thống nhiều luồng, thread khác có thể đóng channel hoặc hủy key trong khi selector đang thực hiện selection. Oracle Javadoc cho phép tình huống callback **được gọi với một key đã invalid**, hoặc key bị thay đổi `interestOps` trước lúc callback chạy.

Vì thế một callback thực tế thường có kiểm tra đầu:

~~~java
selector.select(key -> {
    if (!key.isValid()) {
        return;
    }

    try {
        if (key.isReadable()) {
            // Đọc từ channel nonblocking, có giới hạn.
        }
        if (key.isValid() && key.isWritable()) {
            // Ghi phần còn lại của output buffer.
        }
    } catch (java.nio.channels.CancelledKeyException ex) {
        // Key bị hủy đồng thời sau isValid(); bỏ thao tác hiện tại.
    }
});
~~~

Đoạn trên chỉ **minh họa** cấu trúc callback; không phải ứng dụng hoàn chỉnh vì chưa có channel, buffer hoặc logic I/O.

- `isValid()` là ảnh chụp tại một thời điểm, **không khóa vĩnh viễn trạng thái**. Sau khi kiểm tra, key vẫn có thể bị hủy.
- `readyOps()` và các helper như `isReadable()` có thể ném `CancelledKeyException` nếu key đã bị hủy.
- Nếu callback có nhánh `isReadable` rồi `isWritable`, kiểm tra lại `isValid()` giữa hai nhánh khi nhánh thứ nhất có thể đóng/hủy channel.
- Không khẳng định cứ callback là key vẫn valid hoặc ready set chưa thay đổi: phải đọc đúng hợp đồng `Selector` và `SelectionKey`.

### Callback có thể được gọi nhiều lần cho một key

Nếu một channel có nhiều category readiness cùng lúc, `select(action)` có thể chia các bit `readyOps` thành nhiều lần gọi callback cho **cùng một `SelectionKey`**, theo quy tắc không lặp lại các bit đã báo ở những lần gọi trước trong cùng vòng.

Không dựa vào giả định “mỗi key = đúng một lần callback” để:

- Đếm số connection độc lập bằng biến tăng trong callback;
- Giải phóng tài nguyên hoặc phát log “đã đóng” theo mỗi lần gọi mà không kiểm trạng thái;
- Thực hiện một side effect không thể lặp;
- So sánh số lần callback với giá trị `int` trả về từ `select(action)`.

Nếu cần đếm số key phân biệt đã xử lý, dùng giá trị trả về từ selection operation hoặc một cấu trúc theo dõi key phù hợp; đừng coi lần callback là một sự kiện duy nhất vĩnh viễn.

## 7. Readiness không phải lời hứa I/O sẽ hoàn tất

Các `SelectionKey` chỉ báo **ready** theo category, không bảo đảm có thể đọc đủ dữ liệu ứng dụng mong muốn hoặc ghi trọn `ByteBuffer` mà không chờ. Javadoc `SelectionKey` coi ready set là **gợi ý**, có thể không còn chính xác do tình trạng hệ điều hành/luồng khác và chính các thao tác I/O đã diễn ra.

Vì vậy:

- Đặt `SelectableChannel` vào **nonblocking mode** trước `register` (`channel.configureBlocking(false)`).
- `SocketChannel.read(buffer)` có thể trả **số dương** (đã đọc), **0** (chưa có byte tại thời điểm đó) hoặc **-1** (EOF đối với socket đọc). Không gán ý nghĩa “đã đọc toàn bộ message” cho một lần gọi.
- `SocketChannel.write(buffer)` có thể ghi **ít hơn** số byte còn lại. Giữ buffer/offset cho lần ready tiếp theo.
- Không xoay vòng `while` vô hạn trong callback chỉ để đợi đủ message. Mỗi callback nên có ngân sách byte và số lượt xử lý, sau đó quay lại selector để chia sẻ thời gian cho các channel khác.
- Nếu không còn dữ liệu cần ghi, tắt `OP_WRITE`, vì socket có thể thường xuyên writable và tạo vòng event loop tiêu tốn CPU.
- Không dùng `Thread.sleep(...)` để đợi dữ liệu trong callback: nó giữ callback lâu và không tạo readiness mới.

Một thao tác có thể **được phép** theo API nhưng vẫn là lựa chọn kém trong event loop nếu kéo dài thời gian giữ khóa.

## 8. Ví dụ hoàn chỉnh Java 11+: callback xử lý dữ liệu sẵn sàng

Ví dụ dùng `Pipe` thuộc Java NIO để tạo dữ liệu sẵn trong cùng tiến trình. Nhờ vậy bài thử **không cần server, port, kết nối mạng, sleep hoặc thread bổ sung**.

Tạo tệp **`SelectorCallbackDemo.java`**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;

public class SelectorCallbackDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            // Selectable channel phải ở nonblocking mode trước register.
            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            // Đẩy trước một đoạn rất nhỏ vào Pipe để tạo readiness.
            sink.write(ByteBuffer.wrap(
                    "OK".getBytes(StandardCharsets.UTF_8)
            ));

            int count = selector.select(key -> {
                if (!key.isValid() || !key.isReadable()) {
                    return;
                }

                Pipe.SourceChannel readable =
                        (Pipe.SourceChannel) key.channel();
                ByteBuffer buffer = ByteBuffer.allocate(16);

                try {
                    // I/O nonblocking, tối đa một lần đọc nhỏ trong callback.
                    int n = readable.read(buffer);

                    if (n > 0) {
                        buffer.flip();
                        byte[] data = new byte[n];
                        buffer.get(data);

                        System.out.println("payload=" + new String(
                                data, StandardCharsets.UTF_8
                        ));

                        // Không cần nhận thêm OP_READ ở vòng select kế tiếp.
                        key.interestOps(0);
                    }
                } catch (IOException ex) {
                    // Consumer không khai báo checked IOException.
                    throw new UncheckedIOException(ex);
                }
            }, 1000);

            System.out.println("uniqueKeys=" + count);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SelectorCallbackDemo.java
java SelectorCallbackDemo
~~~

**Stdout của ví dụ với một source channel và một bit `OP_READ` sẵn sàng:**

~~~text
payload=OK
uniqueKeys=1
~~~

**Giải thích kết quả:**

1. `Pipe.open()` tạo hai đầu source/sink. `source.configureBlocking(false)` cho phép đăng ký source với selector.
2. `source.register(selector, SelectionKey.OP_READ)` tạo một key quan tâm thao tác đọc. Dữ liệu `"OK"` được ghi vào sink **trước** khi bắt đầu selection, nên source có dữ liệu để đọc.
3. `selector.select(action, 1000)` gọi action với key readable. `ByteBuffer.allocate(16)` chỉ giới hạn lần đọc thử 16 byte; code đọc 2 byte và in `payload=OK`.
4. `key.interestOps(0)` là thao tác hợp lệ trong callback; nó tắt quan tâm read cho **vòng selection tiếp theo**.
5. Giá trị `count` là số **key phân biệt** được xử lý. Trong trường hợp này chỉ có một key nên in `uniqueKeys=1`.
6. `UncheckedIOException` chuyển lỗi I/O checked thành unchecked trong `Consumer`. Nếu xảy ra, ngoại lệ được truyền ra caller của `select`; `try-with-resources` vẫn đóng pipe/selector.

Ví dụ cố ý không gọi `selectedKeys()`, không gọi `select` lồng và không đợi worker trong callback. Trong server thực tế, buffer thường là một phần của state gắn theo connection và có thể được tái sử dụng; không cần cấp phát buffer mới sau mỗi event.

**Phạm vi kết quả:** ví dụ trên đã được kiểm tra với OpenJDK, còn chương trình sản xuất phải xử lý thêm đường đi khi I/O trả 0, key bị hủy, shutdown, lỗi trong callback và nhiều channel đồng thời. Khi sử dụng selection trên mạng, không nên dựa vào timing hay thứ tự các key để tạo test bắt buộc.

## 9. Có thể làm gì khi callback muốn thay đổi interestOps?

Một pattern thông dụng trong event loop:

~~~java
// Minh họa trong callback, giả định key là key hợp lệ của SocketChannel.
if (key.isValid() && key.isWritable()) {
    // Ghi một lượng dữ liệu hữu hạn từ outboundBuffer...
    // Nếu không còn byte cần gửi, tắt OP_WRITE:
    key.interestOpsAnd(~SelectionKey.OP_WRITE);
}
~~~

`interestOpsAnd` được giới thiệu trong Java 11, **xóa bit bằng phép AND nguyên tử** tương đối với các lời gọi `interestOpsAnd` / `interestOpsOr` đồng thời. Với trường hợp trên, `~SelectionKey.OP_WRITE` chỉ giữ các bit khác và xóa `OP_WRITE`, không phải cộng bit mới.

Khi dữ liệu mới sẵn sàng để ghi, có thể bật bit:

~~~java
// Minh họa: key đã được kiểm tra hợp lệ và có OP_WRITE hợp lệ.
key.interestOpsOr(SelectionKey.OP_WRITE);
key.selector().wakeup();
~~~

- `interestOpsOr` thêm `OP_WRITE` mà vẫn giữ các bit hiện có; Javadoc quy định atomic với các lời gọi `interestOpsOr` / `interestOpsAnd`.
- `wakeup` đặc biệt có ích **khi một thread khác** cập nhật interest set trong lúc selector đang block, để vòng select trở về và nhận thay đổi nhanh.
- Không giả định một lệnh `interestOpsOr` từ thread khác **làm selection đang chạy báo ngay bit mới**. Các thay đổi khi selection đang diễn ra chỉ được nhìn thấy ở **vòng selection kế tiếp**.
- Kiểm tra `isValid()` trước thao tác, nhưng vẫn xử lý `CancelledKeyException` có thể xảy ra do hủy đồng thời.
- Đừng gọi `wakeup` liên tục trong vòng lặp nóng mà không có dữ liệu mới; nó có thể làm selector trả ngay nhiều lần và tốn CPU.

**Lưu ý:** nếu phiên bản JDK mục tiêu nhỏ hơn Java 11 thì hai phương thức `interestOpsOr`/`interestOpsAnd` không có; bài này đặt phạm vi Java 11 trở lên, đúng theo API hiện hành và không dùng workaround cũ.

## 10. Đồng bộ với thread khác: queue công việc và wakeup

Trong thiết kế thực tế, một thread bên ngoài có thể muốn đăng ký channel, cập nhật quan tâm `OP_WRITE`, thay đổi trạng thái kết nối hoặc yêu cầu đóng.

Một pattern dễ kiểm soát là **một event-loop thread làm chủ thay đổi trạng thái selector**, trong khi các worker gửi lệnh qua một hàng đợi thread-safe:

~~~text
Worker / HTTP handler                Selector event-loop thread
─────────────────────                ──────────────────────────
enqueue(command)       ───────────>  ConcurrentLinkedQueue
selector.wakeup()       ───────────>  select(...) trả về khi có thể
                                     drain commands
                                     cập nhật key/channel hợp lệ
                                     select(callback)
                                     callback I/O ngắn, return
~~~

Đoạn minh họa Java 11 dưới đây **không phải ứng dụng độc lập**; nó thể hiện lõi điều phối, giả định `selector` và `commands` đã được tạo trong lớp chứa, còn xử lý lỗi và vòng đời shutdown do lớp đó quản lý:

~~~java
private final Selector selector = Selector.open();
private final java.util.concurrent.ConcurrentLinkedQueue<Runnable> commands =
        new java.util.concurrent.ConcurrentLinkedQueue<>();

// Có thể gọi từ thread khác.
void requestInterestChange(SelectionKey key, int newOps) {
    commands.offer(() -> {
        if (key.isValid()) {
            try {
                key.interestOps(newOps);
            } catch (java.nio.channels.CancelledKeyException ignored) {
                // Key đã bị hủy trước khi event loop xử lý lệnh.
            }
        }
    });

    selector.wakeup();
}

// Được gọi trên event-loop thread, ngoài callback.
void drainCommands() {
    Runnable command;
    while ((command = commands.poll()) != null) {
        command.run();
    }
}

// Một vòng trong event loop:
// drainCommands();
// selector.select(key -> processReadyKey(key));
~~~

**Vì sao `wakeup` cần thiết?** Nếu event loop đang block trong `select`, chỉ đẩy một `Runnable` vào queue **không tự làm selector thức dậy**. `selector.wakeup()` giúp vòng select đang block trở về; event loop có cơ hội xử lý lệnh. Nếu gọi `wakeup` trước khi bắt đầu một select, lệnh tiếp theo sẽ trả về ngay theo hợp đồng wakeup (trừ những trường hợp `selectNow` tiêu thụ hiệu ứng đó).

**Giới hạn của ví dụ:** cần đặt lệnh `drainCommands()` ở vị trí rõ ràng trong event loop, quản lý cờ dừng, vòng đời selector, ngoại lệ khi đóng và bounded queue nếu lượng công việc có thể tăng vô hạn. Một `ConcurrentLinkedQueue` không đặt trần dung lượng; nếu worker có thể enqueue dữ liệu không giới hạn, vẫn phải dùng backpressure/chính sách giới hạn ở tầng ứng dụng.

### Không truyền công việc nặng vào callback

Ví dụ không nên làm:

~~~java
selector.select(key -> {
    // Sai về thiết kế: giữ callback để chờ tính toán hoặc I/O chậm.
    byte[] report = remoteServiceCallAndWait();
    saveReportToDisk(report);
});
~~~

Đây là mẫu minh họa anti-pattern, không có định nghĩa các hàm phụ. Thay vào đó, callback nên lưu/cập nhật trạng thái I/O tối thiểu, **đẩy công việc nặng sang executor có giới hạn**, và sau khi worker hoàn tất thì gửi kết quả về event loop qua queue + `wakeup`. Tránh để worker sửa trực tiếp các buffer/attachment dùng đồng thời bởi event loop mà không có quy tắc sở hữu.

**Không cầm monitor app khi chờ worker**, cũng không để worker cầm monitor app rồi gọi `selector.close` đồng thời với callback có thể yêu cầu chính monitor đó.

## 11. Những cách xử lý ngoại lệ và shutdown đúng

### 11.1. Ngoại lệ từ callback được truyền ra select

Theo tài liệu `Selector.select(action)`, **ngoại lệ do action ném ra sẽ được truyền tới caller**. Callback của `Consumer<SelectionKey>` không thể trực tiếp khai báo `throws IOException`, nên mã thường chọn một trong hai cách:

- Xử lý I/O exception ngay trong callback, hủy key/đóng channel và ghi log phù hợp, nếu lỗi chỉ liên quan connection hiện tại.
- Bọc thành `UncheckedIOException` hoặc một unchecked exception riêng rồi để tầng event loop xử lý, nếu cần dừng selection/luồng xử lý.

Ví dụ minh họa cấu trúc:

~~~java
try {
    selector.select(key -> {
        try {
            handleReady(key); // Hàm này có thể throws IOException.
        } catch (IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    });
} catch (java.io.UncheckedIOException e) {
    // Quyết định log/close/retry theo chính sách của event loop.
    System.err.println(e.getCause());
}
~~~

Đây là **đoạn minh họa trong method có `throws IOException`**, cần định nghĩa `handleReady` và sở hữu `selector` ở code bao ngoài.

Không nuốt ngoại lệ một cách im lặng rồi coi dữ liệu đã xử lý thành công. Nếu callback ném lỗi sau khi mới đọc một phần dữ liệu, cần giữ trạng thái/cleanup phù hợp; đừng tự giả định có rollback.

### 11.2. Đóng selector bên trong callback

Javadoc cho phép action đóng selector, nhưng quy định **`ClosedSelectorException` được ném khi callback kết thúc**. Vì vậy:

~~~java
selector.select(key -> {
    selector.close(); // Không nên là lối shutdown mặc định.
});
~~~

Đoạn trên minh họa quyết định không nên dùng. Dù có thể thao tác `close`, nó không phải cách “trả về bình thường khỏi select” và có thể làm các key/channel liên quan mất hiệu lực.

Tổ chức vòng đời dễ kiểm soát hơn là **gửi tín hiệu dừng, gọi wakeup từ thread quản lý nếu cần, thoát vòng lặp, rồi đóng selector trong `try-with-resources` / khối cleanup**. Việc đóng selector không đồng nghĩa mọi channel của ứng dụng tự được đóng theo cách nghiệp vụ mong muốn; quản lý nguồn channel tường minh.

### 11.3. Hủy key hoặc đóng channel trong callback

`key.cancel()` và `key.channel().close()` **được cho phép**. Sau khi hủy key, không gọi `key.readyOps()` hoặc `key.interestOps()` như thể nó còn valid. Việc hủy key là yêu cầu deregister, được xử lý trong quá trình selection; không dùng key đã hủy để khởi động một thao tác I/O tiếp theo.

Có thể có callback cho key đã bị hủy **trước khi action được thực thi** do race. Đây là lý do hợp đồng luôn đòi hỏi code cẩn thận kiểm tra `isValid()` và xử lý cạnh tranh đóng/hủy.

## 12. Những giả định sai dễ dẫn đến bug

| Giả định sai | Thực tế theo hợp đồng API | Hướng xử lý |
| --- | --- | --- |
| “Callback được chạy trên thread riêng nên có thể chờ tùy ý.” | Callback chạy trong selection call, khi selector và selected-key set đang synchronized | Giữ callback ngắn, chuyển việc nặng sang worker |
| “Vì Java monitor reentrant nên gọi `selectNow` lồng là an toàn.” | `Selector` selection **không bảo đảm reentrant** | Để vòng ngoài gọi select kế tiếp |
| “Mọi thao tác với key đều bị cấm trong callback.” | `cancel`, đóng channel, thay `interestOps` được phép | Dùng có chủ đích, kiểm validity và trạng thái |
| “Đổi `interestOps` có hiệu lực ngay với selection hiện tại.” | Thay đổi trong khi select đang chạy có hiệu lực ở lần selection sau | Ghi state và quay lại event loop |
| “Callback chỉ gọi một lần cho mỗi key.” | Có thể gọi nhiều lần cho một key với các bit ready khác nhau | Không gắn side effect không thể lặp với số lần gọi |
| “`select(action)` luôn làm `selectedKeys()` trống.” | Default implementation không hứa tập rỗng sau completion | Không sử dụng selected-key set trong flow callback |
| “Đang nhận callback thì key chắc chắn còn valid.” | Key có thể bị hủy/đóng trước khi action chạy hoặc giữa các bước | Kiểm `isValid` và bắt race cần thiết |
| “Ready nghĩa là đọc đủ message / ghi hết buffer.” | Readiness là tín hiệu có thể lỗi thời; I/O nonblocking có thể partial hoặc 0 | Lưu trạng thái và xử lý incremental |
| “Có thể `synchronized(appLock)` rồi `selector.close` từ thread khác vô hại.” | Có thể đảo thứ tự khóa và deadlock | Queue lệnh, wakeup và single owner |
| “`wakeup` hủy ngay callback đang chạy.” | Nó tác động tới selection đang chờ hoặc lần selection kế tiếp, **không buộc callback hiện tại hoàn tất** | Không thiết kế phụ thuộc preemption |
| “Giá trị trả về bằng số lần callback chạy.” | Giá trị là **số key phân biệt** được tiêu thụ | Đếm đúng chỉ tiêu cần đo |
| “`Selector` thread-safe nghĩa là `selectedKeys` thread-safe.” | Selected-key set không thread-safe nói chung | Không truy cập/chỉnh sửa tùy tiện qua các thread |
| “Bỏ qua exception trong callback vẫn bảo đảm event loop khỏe.” | Lỗi có thể làm trạng thái connection dở dang | Có chính sách lỗi, cleanup và giám sát |

## 13. Bài thực hành và QA tình huống

**Tình huống A — Select lồng:** bạn có đoạn `selector.select(key -> selector.selectNow(other -> {...}))`. Điều gì sai?

**Đáp án:** tạo selection reentrant trên cùng selector, API không đặc tả kết quả. Hãy hoàn thành callback rồi thực hiện lần select tiếp theo ở event loop.

**Tình huống B — Worker chờ lock:** event loop đang chạy callback, lấy `appLock`. Một worker giữ `appLock` và gọi `selector.close()`. Điều gì có thể xảy ra?

**Đáp án:** deadlock do đảo thứ tự monitor. Đừng lấy khóa ứng dụng trong callback nếu thread khác cầm khóa đó khi chờ selector; điều phối qua queue/wakeup hoặc thiết kế owner rõ ràng.

**Tình huống C — Thay interest:** trong callback `key.interestOps(SelectionKey.OP_READ)` để chỉ quan tâm đọc. Có thể yêu cầu key lập tức được chọn lại ở **cùng lần select** vì vừa thay không?

**Đáp án:** Không. Sự thay đổi interest set trong khi selection đang chạy được quan sát ở lần selection tiếp theo.

**Tình huống D — Hủy key:** callback nhận key có `key.isValid()==false`. Có phải lỗi của JDK không?

**Đáp án:** Không hẳn; khi key bị hủy hoặc interest thay đổi trước action, implementation có thể vẫn gọi action cho key không hợp lệ. Callback phải xử lý trường hợp này.

**Tình huống E — Chặn trong callback:** callback gọi API database đồng bộ mất vài giây. Các kênh khác có được xử lý đúng tiến độ không?

**Đáp án:** Không có bảo đảm độ trễ thấp khi callback đang giữ luồng event loop và các monitor của selector. Nên tách tác vụ chặn sang executor có giới hạn, trả kết quả về event loop khi hoàn tất.

**Tình huống F — Đếm callback:** một key có đồng thời `OP_READ` và `OP_WRITE`, callback được gọi hai lần. `select(action)` bắt buộc trả về 2 không?

**Đáp án:** Không. API trả số **key phân biệt** được tiêu thụ; có thể chỉ là 1 trong trường hợp một key được gọi nhiều lần.

**Tình huống G — Đóng selector:** callback tự gọi `selector.close()` rồi kết thúc bình thường. Có nên mong `select` trả 0 không?

**Đáp án:** Không. Javadoc quy định `ClosedSelectorException` được ném khi action đóng selector và hoàn tất.

### Checklist kiểm thử có giá trị

- [ ] Callback không gọi `select`/`selectNow` lồng trên cùng selector.
- [ ] Không có `sleep`, `join`, chờ `Future.get`, mạng đồng bộ hay tác vụ CPU dài bên trong callback.
- [ ] Không có tình huống hai thread lấy khóa app và monitor selector theo thứ tự ngược nhau.
- [ ] Callback kiểm key invalid, `CancelledKeyException`, EOF/0/partial I/O.
- [ ] Thay interest set được kiểm tra ở **lần selection kế tiếp**, không giả định hiệu lực tức thì.
- [ ] Không dựa vào một callback cho một key, thứ tự key hoặc `selectedKeys().isEmpty()` sau `select(action)`.
- [ ] Có đường xử lý `IOException`/`UncheckedIOException`/`ClosedSelectorException` và dọn resources.
- [ ] Có chính sách backpressure, giới hạn thời gian làm việc callback và shutdown event loop.
- [ ] Mã được kiểm thử bằng API JDK mục tiêu (Java 11+), không dùng lớp nội bộ JDK hay cơ chế đã lỗi thời.

## 14. Thiết kế callback hiệu quả khi chương trình mở rộng

Một callback tốt thường theo flow:

~~~text
Selector.select(action)
    └── action(key)
         ├── if (!key.isValid()) return
         ├── đọc ready bits
         ├── làm I/O nonblocking với ngân sách hữu hạn
         ├── cập nhật connection state / interestOps
         ├── enqueue việc chặn hoặc nặng nếu cần
         └── return nhanh
             ↓
         vòng select kế tiếp
~~~

Khi thiết kế nhiều kết nối, có thể gắn state của mỗi connection với `key.attach(...)` và lấy lại qua `key.attachment()`. Khi đó, giới hạn phạm vi chỉnh sửa state về event-loop thread giúp đơn giản hóa đồng bộ. Nếu worker thực sự cần chia sẻ state, vẫn phải có cơ chế đồng bộ/thông điệp rõ ràng. Việc có `attachment` **không tự khiến toàn bộ state bên trong thread-safe**.

Với output buffer, việc đặt và bỏ `OP_WRITE` nên gắn với việc queue có dữ liệu hay không. Khi buffer không còn dữ liệu, loại `OP_WRITE` để tránh “writable event” lặp. Khi worker tạo response, enqueue dữ liệu vào event loop, bật `OP_WRITE` và gọi `wakeup` nếu selector đang block.

Với input parsing, giới hạn byte/công việc trong callback để một connection nhiều dữ liệu không khiến các connection khác bị bỏ đói. Nếu không xử lý được hết trong một vòng, giữ phần dư trong state và tiếp tục ở sự kiện phù hợp hoặc theo chính sách lịch làm việc. Tránh “while(true) read(...)” không có hạn mức bên trong callback.

## Tài liệu chính thức và còn áp dụng

- [`Selector` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html) — các phương thức `select(Consumer)`, đồng bộ trong callback, non-reentrant selection, đóng/hủy key và mặc định của selected-key set.
- [`Selector` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html) — đối chiếu hợp đồng callback trên JDK hiện đại.
- [`SelectionKey` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectionKey.html) — `isValid`, `interestOps`, `readyOps`, `CancelledKeyException`, `interestOpsAnd`/`interestOpsOr`.
- [`SelectableChannel` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectableChannel.html) — chuyển sang nonblocking trước khi register và quy tắc thay blocking mode.
- [`Pipe` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Pipe.html) — nguồn và đích của ví dụ chạy được.
- [`ConcurrentLinkedQueue` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html) — hàng đợi thread-safe dùng minh họa phối hợp với `wakeup`.

**Ghi nhớ:** `Selector.select(Consumer)` là API callback **nằm trong vùng đồng bộ của selector**. Không select lồng trên chính selector; giữ action ngắn và không chặn; được phép hủy key, đóng channel hoặc thay `interestOps` nhưng phải xử lý hiệu lực ở vòng sau, key invalid và ngoại lệ. Đưa việc chậm sang worker, truyền kết quả về event loop bằng cơ chế có kiểm soát và `wakeup`.