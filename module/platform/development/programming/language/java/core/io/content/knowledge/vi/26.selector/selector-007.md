# Wakeup, hủy SelectionKey và đóng Selector trong Java NIO

## 1. Vì sao cần ba thao tác khác nhau?

Trong Java NIO, một `Selector` quản lý nhiều `SelectableChannel` để chương trình có thể đợi những channel sẵn sàng đọc, ghi, nhận kết nối hoặc hoàn tất kết nối mà không cần một luồng chờ trên từng socket. Mỗi lần đăng ký một channel với selector sẽ tạo hoặc trả về một `SelectionKey` đại diện cho mối quan hệ đăng ký đó.

Khi event loop vận hành, ứng dụng thường cần giải quyết ba việc rất khác nhau:

1. **`selector.wakeup()`:** đánh thức một lời gọi selection đang chờ, hoặc khiến lần selection kế tiếp trở về ngay. Selector và các channel vẫn có thể tiếp tục sử dụng.
2. **`key.cancel()`:** hủy đăng ký **một channel với một selector**; key mất hiệu lực ngay, nhưng việc xóa khỏi các tập key và deregister thực tế xảy ra trong một lượt selection tiếp theo.
3. **`selector.close()`:** kết thúc vòng đời **cả selector**, vô hiệu tất cả key gắn với nó và giải phóng tài nguyên của selector; **không tự đóng các channel đã đăng ký**.

Không nên coi ba lời gọi là những cách tương đương để "dừng I/O".

| Thao tác | Điều thay đổi ngay | Các channel có đóng không? | Selector còn sử dụng được? |
|---|---|---|---|
| `wakeup()` | Một lượt select bị đánh thức hoặc next select được báo trước | Không | Có |
| `SelectionKey.cancel()` | Key trở thành invalid; được đưa vào cancelled-key set | Không | Có |
| `Selector.close()` | Selector đóng; key associated bị vô hiệu và deregister | **Không tự động** | Không |
| `channel.close()` | Chính channel đóng và những registration tương ứng bị cancel | **Có, channel đó** | Có nếu selector chưa đóng |

Lưu ý: nếu một channel được đăng ký trên **nhiều selector**, `key.cancel()` chỉ hủy đăng ký gắn với key đó. Ngược lại, `channel.close()` tác động tới bản thân channel và làm các key đăng ký channel ấy mất hiệu lực.

## 2. Hiểu Selector, SelectionKey và ba tập key

`Selector.open()` tạo selector. Chỉ một `SelectableChannel` ở **non-blocking mode** mới được đăng ký qua `channel.register(selector, ops)`. Với TCP:

~~~java
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

Đây là **đoạn minh họa**, cần có biến `Selector selector` còn open, channel ở trạng thái phù hợp và các import. Một channel mới chưa connected thường không nên đăng ký `OP_READ` trước khi kết nối hoàn tất; ví dụ này chỉ minh họa API register, không phải chương trình chạy độc lập.

Một selector theo Java 17 có ba tập logic:

- **Key set — `selector.keys()`:** tập các key đăng ký với selector (không thể tự ý add/remove).
- **Selected-key set — `selector.selectedKeys()`:** các key đã được phát hiện sẵn sàng ở lượt selection trước. Ứng dụng thường phải tự loại key khỏi tập sau khi xử lý.
- **Cancelled-key set:** tập nội bộ chứa key đã bị hủy nhưng chưa hoàn tất deregister. **Không có API public để trực tiếp đọc tập này.**

Đầu vòng đời selector, các tập rỗng. Sau `register`, key xuất hiện trong key set. Sau `select` nhận được readiness, key có thể xuất hiện trong selected-key set. Sau `cancel`, key invalid ngay nhưng vẫn có thể hiện diện trong `keys()` cho đến lượt selection tiếp theo xử lý cancellation.

~~~text
register(channel, OP_READ)
       |
       v
Key hợp lệ trong selector.keys()
       |
       +-- select nhận readiness --> selectedKeys có thể chứa key
       |                                  |
       |                                  +-- application xử lý rồi iterator.remove()
       |
       +-- key.cancel() --------> key invalid ngay
                                         |
                                         v
                              Cancelled-key set nội bộ
                                         |
                                      next select
                                         |
                                         v
                             Deregister, loại khỏi các tập
~~~

**Phân biệt:** `selectedKeys().remove(key)` chỉ loại key khỏi **danh sách sự kiện đang chờ ứng dụng xử lý**, không hủy đăng ký. `key.cancel()` mới yêu cầu ngừng theo dõi registration này.

## 3. \`Selector.wakeup()\`: đánh thức một lượt selection

`Selector.wakeup()` là công cụ điều phối khi một thread đang đợi trong `select()` hoặc khi thread khác cần cập nhật công việc/interestOps của event loop.

Các trường hợp:

1. **Đã có thread đang block trong `select()`:** `wakeup()` khiến thao tác đó sớm trở về. Nó **không bảo đảm** kết quả trả là `0`, vì có thể đồng thời đã có key ready.
2. **Chưa có selection đang chờ:** lần gọi selection kế tiếp trở về ngay, trừ khi một `selectNow()`/`selectNow(Consumer)` tiêu thụ trạng thái wakeup trước đó.
3. **Gọi wakeup nhiều lần giữa hai lượt selection:** hiệu lực giống **một lần**; không có hàng đợi đếm số tín hiệu wakeup.
4. **Sau lượt selection đã bị đánh thức:** lần selection kế tiếp có thể block bình thường nếu không có readiness hay tín hiệu mới.
5. **`wakeup()` không đăng ký, không cancel, không đóng channel**, cũng không tự đưa một task vào queue của ứng dụng.

Chữ ký:

~~~java
public abstract Selector wakeup()
~~~

Phương thức trả chính selector để có thể gọi theo kiểu chaining, nhưng cách viết rõ ràng trong event loop thường là `selector.wakeup();`.

### Khi nào dùng wakeup?

Giả sử một thread quản lý event loop đang:

~~~java
while (running) {
    selector.select();
    // Xử lý các key ready và task được gửi từ thread khác.
}
~~~

Nếu thread khác cần yêu cầu event loop thay đổi interest set, đăng ký channel, gửi dữ liệu hoặc dừng vòng lặp, có thể **đưa yêu cầu vào queue trước rồi gọi wakeup**. Lúc tỉnh dậy, event loop xử lý yêu cầu rồi mới select tiếp.

~~~text
Thread công việc: queue.add(task) ---> selector.wakeup()
                                            |
                                            v
Thread event loop:  select() trở về --> drain queue --> cập nhật state
                                                  --> xử lý readiness
                                                  --> select tiếp
~~~

Để không làm mất yêu cầu do cạnh tranh, queue phải thread-safe (ví dụ `ConcurrentLinkedQueue`) hoặc có đồng bộ thích hợp. `wakeup` là **tín hiệu đánh thức**, không thay thế queue và không chứa payload.

### Wakeup trước select vẫn có ý nghĩa

Không cần cố dùng `Thread.sleep` để "canh" thời điểm thread đang block. Java bảo đảm **wakeup gọi trước lần select tiếp theo** cũng có hiệu lực. Ví dụ:

~~~java
selector.wakeup();
int updated = selector.select(); // trả ngay, updated có thể là 0
~~~

Đây là đoạn minh họa. Nếu có channel ready, kết quả có thể khác 0. `selectNow()` trả ngay trong mọi trường hợp và **xóa hiệu lực wakeup chưa sử dụng**.

### Wakeup khác Thread.interrupt

Thread khác gọi `selector.wakeup()` **không đặt interrupt flag** trên thread của event loop. Gọi `thread.interrupt()` khi thread đó đang block trong selection sẽ đặt interrupt flag và đánh thức selector như gọi `wakeup()`. Không tự suy luận việc đánh thức `Selector.select()` là `ClosedByInterruptException` hoặc channel bị đóng; loại exception ấy gắn với blocking I/O trên `InterruptibleChannel`, còn select có hợp đồng riêng.

Nếu chủ đích chỉ là báo "có task mới", thường `wakeup()` diễn đạt ý định rõ ràng hơn `interrupt()`.

## 4. \`SelectionKey.cancel()\`: hủy một registration

`SelectionKey.cancel()` có hành vi chính xác:

- Khi trả về, `key.isValid()` là **`false`**.
- Key được đưa vào **cancelled-key set** của selector và sẽ bị loại khỏi mọi tập key, đồng thời channel bị deregister, trong lượt selection tiếp theo.
- Hủy lặp lại cùng key là **idempotent**: lời gọi tiếp theo không có tác dụng mới.
- Key đã bị hủy **không trở lại hợp lệ**. Nếu cần theo dõi lại channel, chờ deregistration hoàn tất rồi gọi `register` để nhận key mới.
- **`cancel()` không đóng channel**. Ứng dụng vẫn có thể dùng channel trực tiếp nếu nó còn open và ở trạng thái cho phép.

Ví dụ quan sát trạng thái:

~~~java
key.cancel();
System.out.println(key.isValid()); // false
selector.selectNow();              // xử lý cancelled-key set
~~~

Đoạn này minh họa thứ tự thao tác khi `selector` còn open. Nếu chỉ cancel và không gọi selection thêm, key có thể vẫn xuất hiện trong `selector.keys()`; đó là trạng thái trung gian hợp lệ.

### Phân biệt cancel và remove khỏi selectedKeys

Hai thao tác thường xuất hiện trong cùng event loop nhưng có tác dụng khác nhau:

~~~java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove(); // đã lấy một event ra khỏi selected-key set

    if (!key.isValid()) {
        continue; // key có thể đã bị cancel ở thread khác
    }

    if (key.isReadable()) {
        // Đọc cho đến khi không còn dữ liệu hiện sẵn hoặc hết budget.
    }
}
~~~

Đây là **đoạn mã trong một phương thức đã có biến selector**; phần xử lý đọc chỉ là chú thích. `it.remove()` không cancel và không đóng channel; nó chỉ tránh xử lý lặp sự kiện cũ. Việc `selectedKeys()` không tự xóa hết key sau mỗi vòng là nguồn lỗi CPU busy loop phổ biến.

### Điều gì xảy ra với selectedKeys khi cancel?

Sau `cancel()`, key invalid ngay nhưng có thể vẫn nằm trong `selectedKeys()`/`keys()` cho đến khi selection operation thực hiện bước xử lý cancellation. Vì vậy khi duyệt selected keys, cần kiểm tra `key.isValid()` trước khi gọi `readyOps()`, `isReadable()`, `isWritable()` hoặc cập nhật `interestOps()`.

Những lời gọi đó có thể ném `CancelledKeyException` nếu key đã invalid. Kiểm tra và thao tác cũng có thể chịu race với thread khác; tránh để nhiều thread tùy ý xử lý cùng key mà không có quy tắc ownership.

### Nếu muốn hủy và đăng ký lại ngay?

`cancel()` không tức thì deregister underlying registration. Trong code chủ động chạy ở event loop, có thể gọi `selector.selectNow()` để thúc đẩy xử lý cancelled keys, sau đó mới `register` lại channel nếu còn open và non-blocking. Điều này giúp phân biệt **vô hiệu key tức thì** với **deregister theo lượt selection**.

Không nên dùng `selectNow()` tùy tiện từ nhiều thread đồng thời với một selector đã có event loop; chọn rõ một thread sở hữu luồng selection để tránh tranh chấp.

## 5. \`Selector.close()\`: dừng selector nhưng không đóng channel

`Selector` triển khai `Closeable` và `AutoCloseable`. Do vậy nên dùng `try-with-resources` hoặc một phương thức shutdown đảm bảo `close()` được gọi đúng chủ sở hữu.

Theo Java 17, `selector.close()`:

1. Đánh dấu selector đã đóng và giải phóng những tài nguyên nội bộ thuộc selector.
2. Nếu thread khác đang block ở một selection operation, nó được đánh thức như qua `wakeup()`.
3. Các key còn đăng ký bị vô hiệu, các channel bị **deregister khỏi selector này**.
4. Gọi `close()` lần thứ hai không có tác dụng mới.
5. Những lần sử dụng selector sau khi đóng (ngoại trừ `close()`/`wakeup()`) ném `ClosedSelectorException`.
6. **Không tự động đóng `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, `Pipe.SourceChannel` hay channel khác đã đăng ký**.

Điểm cuối rất quan trọng với leak tài nguyên: đóng selector **không phải** lệnh đóng tất cả kết nối socket. Server phải tự đóng những channel mình sở hữu, bên cạnh selector.

Ví dụ:

~~~java
Selector selector = Selector.open();
SocketChannel channel = SocketChannel.open();
try {
    channel.configureBlocking(false);
    channel.register(selector, SelectionKey.OP_CONNECT);

    selector.close();
    System.out.println(channel.isOpen()); // true
} finally {
    channel.close();
}
~~~

**Đoạn mã minh họa**: có thể ném `IOException`; socket vừa mở chưa connected nhưng vẫn có thể đăng ký quan tâm `OP_CONNECT` theo `validOps`. `selector.close()` không đóng `channel`. Không coi đây là ví dụ kết nối TCP hoàn chỉnh.

### Close trong lúc thread đang select

Một thread khác có thể gọi `selector.close()` để dừng một `select()` đang block. Nhưng event loop phải chuẩn bị để quan sát selector đã đóng, có thể gặp `ClosedSelectorException` ở thao tác sau đó, và dừng sử dụng selector. **Không dựa vào một số lượng ready keys cố định** khi có close/cancel chạy đồng thời.

Nếu chỉ muốn event loop thức dậy, thực hiện task mới rồi tiếp tục, dùng `wakeup()`. Nếu đã xác định vòng đời selector kết thúc, mới dùng `close()` theo quy trình shutdown.

## 6. Demo Java 17+ chạy được: wakeup, cancel, close

Demo sau chỉ dùng `Pipe` và `Selector` nội bộ, không yêu cầu kết nối mạng hoặc port. Không có byte gửi vào pipe, vì vậy khi chưa có readiness, `wakeup()` giúp `select()` trở về với 0 key được chọn. Sau đó hủy key và chứng minh channel vẫn còn open khi selector đã bị đóng.

**Tệp: `SelectorLifecycleDemo.java`**

~~~java
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;

public class SelectorLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);
            SelectionKey key =
                    source.register(selector, SelectionKey.OP_READ);

            System.out.println("registered=" + selector.keys().size());

            selector.wakeup();
            System.out.println("selected=" + selector.select());

            System.out.println("valid before=" + key.isValid());
            key.cancel();
            System.out.println("valid after=" + key.isValid());
            System.out.println(
                    "pending count=" + selector.keys().size());

            selector.selectNow(); // xử lý cancelled-key set
            System.out.println(
                    "removed count=" + selector.keys().size());
            System.out.println(
                    "source open after cancel=" + source.isOpen());

            SelectionKey second =
                    source.register(selector, SelectionKey.OP_READ);
            System.out.println("second valid=" + second.isValid());

            selector.close();
            System.out.println(
                    "second valid after close=" + second.isValid());
            System.out.println(
                    "source open after selector close=" + source.isOpen());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SelectorLifecycleDemo.java
java SelectorLifecycleDemo
~~~

**Stdout trên JDK 17+ trong điều kiện demo mô tả:**

~~~text
registered=1
selected=0
valid before=true
valid after=false
pending count=1
removed count=0
source open after cancel=true
second valid=true
second valid after close=false
source open after selector close=true
~~~

Giải thích:

1. `source.configureBlocking(false)` là điều kiện cần để đăng ký với selector.
2. `wakeup()` trước `select()` đảm bảo lượt select trở về ngay; vì pipe không có dữ liệu, `selected=0`.
3. `key.cancel()` làm `key.isValid() == false` ngay, nhưng trước lượt selection kế tiếp key còn trong `selector.keys()`: `pending count=1`.
4. `selector.selectNow()` xử lý cancellation và deregister, nên key set rỗng.
5. Source channel vẫn open sau `cancel()`, nên có thể đăng ký lại; key mới là hợp lệ.
6. `selector.close()` làm key mới mất hiệu lực nhưng **không đóng source channel**.
7. `try-with-resources` vẫn đóng cả source và sink khi scope kết thúc, không để lại tài nguyên pipe.

Không có `Thread.sleep()` trong demo: tính tức thì của `select()` xuất phát trực tiếp từ hợp đồng `wakeup()`, không phụ thuộc timing giữa các thread. Demo mô phỏng một channel không có readiness; trong ứng dụng có key ready thì `select()` có thể trả số khác 0 ngay cả khi đã wakeup.

## 7. Event loop nhận lệnh từ thread khác qua task queue và wakeup

Một kiến trúc đơn giản là để **một thread chuyên trách** thực hiện `select`, duyệt `selectedKeys`, thay đổi `interestOps` và đóng những channel thuộc event loop. Các thread khác không tự ý đụng vào selected-key set; chúng gửi command vào queue rồi báo `wakeup`.

Ví dụ mã khung (chỉ minh họa cấu trúc, không phải chương trình hoàn chỉnh):

~~~java
final class LoopCommands {
    private final Selector selector;
    private final Queue<Runnable> pending =
            new ConcurrentLinkedQueue<>();

    LoopCommands(Selector selector) {
        this.selector = selector;
    }

    void submit(Runnable task) {
        pending.add(task);
        selector.wakeup();
    }

    void drain() {
        for (Runnable task; (task = pending.poll()) != null; ) {
            task.run();
        }
    }
}
~~~

Cần import `java.nio.channels.Selector`, `java.util.Queue`, `java.util.concurrent.ConcurrentLinkedQueue` trong chương trình thật. `drain()` được **thread event loop** gọi. Đặt `pending.add(task)` trước `selector.wakeup()` nhằm bảo đảm công việc đã có trong queue khi loop tỉnh.

Một event loop điển hình:

~~~java
while (running) {
    selector.select();
    commands.drain();

    Iterator<SelectionKey> keys = selector.selectedKeys().iterator();
    while (keys.hasNext()) {
        SelectionKey key = keys.next();
        keys.remove();

        if (!key.isValid()) {
            continue;
        }
        // Xử lý OP_ACCEPT / OP_CONNECT / OP_READ / OP_WRITE.
    }
}
~~~

Đây là mã minh họa: `running`, `commands`, `selector` là biến đã được khởi tạo, phần xử lý I/O cần triển khai. Thread khác gọi `commands.submit(...)` để thêm hoặc hủy interest, đổi trạng thái shutdown. Code production cần handling của `IOException`, `CancelledKeyException`, per-client state, backpressure và lỗi trong Runnable để một command lỗi không làm mất toàn bộ event loop không chủ đích.

**Chú ý:** `wakeup()` **không ép selector đang trong một lần selection phải cập nhật ngay interestOps của lần đó**. Java 17 xác định thay đổi interest set trong khi đang select sẽ có hiệu lực ở **lượt selection tiếp theo**. Chính vì vậy, cơ chế queue + wakeup rồi thay interestOps trên event-loop thread dễ kiểm soát hơn.

## 8. Selected-key set và những cạnh tranh thường gặp

### 8.1. selectedKeys không tự bị clear hoàn toàn

API `selector.selectedKeys()` trả tập key được chọn để ứng dụng xử lý. Nếu chỉ duyệt mà không `iterator.remove()`, một key vẫn có thể nằm trong tập đó sau khi đã xử lý readiness. Ở lượt select kế tiếp, ready operations của key sẵn trong tập có thể được gộp vào trạng thái cũ. Điều này dễ tạo **xử lý readiness lặp** và busy loop.

Cách xử lý thông dụng là xóa từng key khỏi selected-key set trước khi dispatch.

### 8.2. Hai kiểu select khác nhau trong Java 17

- `select()` / `select(timeout)` / `selectNow()` dùng **selected-key set** và ứng dụng tự dọn tập này.
- Các overload Java 11+ nhận `Consumer<SelectionKey>` như `select(action)` hay `selectNow(action)` có thể **gọi callback trực tiếp** trên key ready, **không thêm key vào selected-key set** theo dạng selection này.

Với callback selection, phải rất thận trọng vì callback diễn ra trong quá trình synchronized selection. **Không thực hiện một selection operation reentrant trên chính selector bên trong callback**; hành vi không được xác định thống nhất cho mọi provider. Nếu callback đóng selector, lời gọi selection sẽ báo `ClosedSelectorException` khi callback hoàn thành.

### 8.3. Thread safety của các tập

Theo tài liệu `Selector`:

- **Selector và key set** an toàn cho một số thao tác đồng thời được API mô tả.
- **Selected-key set và cancelled-key set không được coi là thread-safe** cho mọi cách dùng trực tiếp.
- `key.cancel()` được phép gọi từ thread khác, nhưng việc deregister thực tế sẽ xảy ra trong selection operation.
- Trước khi xử lý key lấy từ tập, phải nghĩ tới khả năng key đã bị cancel hoặc channel đã closed ở một thread khác.
- Khi nhiều thread thay đổi selected-key set trực tiếp, cần synchronize theo hợp đồng API; đơn giản hơn là giao việc duyệt và xóa selected keys cho một event-loop thread.

`selector.keys()` cũng **không nên được dùng làm danh sách bảo đảm tất cả key hợp lệ**, bởi cancelled key có thể chưa được loại khỏi tập.

## 9. Shutdown đúng: đánh thức, hủy key, đóng channel và đóng selector

Để dừng một server/event loop mà không rò rỉ socket hay file descriptor, cần tách rõ **signal** và **cleanup**.

Một quy trình thường dùng:

1. Đánh dấu trạng thái `running = false` hoặc enqueue một shutdown command theo cơ chế thread-safe.
2. Gọi `selector.wakeup()` để thread event loop đang đợi thoát khỏi `select()` và nhận lệnh dừng.
3. Ngừng nhận registration mới hoặc mở socket mới; ngừng nhận message mới theo chính sách server.
4. Hủy key và/hoặc đóng từng channel còn do service sở hữu. `key.cancel()` đơn thuần không đóng kết nối.
5. Đóng `selector` trong `finally` / `try-with-resources` để giải phóng tài nguyên selector; không tiếp tục gọi `select` sau khi đóng.
6. Thu hồi các tài nguyên còn lại như worker executor, message buffers có ownership đặc biệt, timer hay các adapter liên kết.

Một khung shutdown minh họa:

~~~java
void requestStop() {
    running = false;       // ví dụ running là volatile
    selector.wakeup();     // signal tới event-loop thread
}

void cleanupOnLoopThread() throws IOException {
    for (SelectionKey key : selector.keys()) {
        key.channel().close(); // đóng tài nguyên channel đang do loop sở hữu
    }
    selector.close();
}
~~~

Đây là **mã minh họa trong lớp quản lý** có các biến `volatile boolean running` và `Selector selector`, chưa trình bày handling và đồng bộ đầy đủ. Chỉ dùng vòng lặp đóng tất cả `key.channel()` nếu event loop **thực sự sở hữu** tất cả channel ấy; với channel mượn từ thành phần khác, cần thỏa thuận ownership.

### Vì sao không chỉ gọi selector.close?

Nếu chỉ đóng selector, socket channels vẫn có thể open. Điều này giữ tài nguyên hệ điều hành và kết nối không cần thiết, dẫn tới lỗi kiểu “too many open files”, cạn file descriptor hoặc tài nguyên mạng. **Close selector không thay cho close channel**.

### Vì sao không chỉ gọi key.cancel?

`cancel()` chỉ loại channel khỏi cơ chế multiplexing, và việc loại thực sự xảy ra ở selection tiếp theo. Channel vẫn open. Nếu ứng dụng không có chủ đích giữ channel để xử lý ngoài selector, phải đóng nó khi kết thúc.

### Vì sao không gọi Thread.interrupt để thay wakeup?

Interrupt là tín hiệu ở cấp thread, ảnh hưởng cách task xử lý cancellation và các blocking operations khác. `wakeup` chuyên biệt cho selection; với task queue/event loop, nó thường có semantics dễ hiểu hơn. Nếu thread đã bị interrupt, code phải tôn trọng interrupt flag và chính sách shutdown của ứng dụng.

## 10. Khi nào dùng selectNow, khi nào dùng wakeup?

| Tình huống | API phù hợp | Lưu ý |
|---|---|---|
| Thread A đang có event loop `select()`, B vừa gửi task | `selector.wakeup()` | Task phải được lưu ngoài selector |
| Một thread muốn poll readiness mà không block | `selector.selectNow()` | Đồng thời tiêu thụ pending wakeup |
| Muốn hủy một registration | `key.cancel()` | Không đóng channel, chờ lượt selection |
| Muốn xử lý cancelled key ngay trong thread sở hữu selector | `selector.selectNow()` | Có thể tiến hành deregistration |
| Muốn dừng hẳn selector | `selector.close()` | Key invalid, channel vẫn cần cleanup |
| Muốn kết thúc kết nối TCP | `socketChannel.close()` | Registration của channel cũng bị cancel |
| Chỉ muốn loại event đã dispatch khỏi selected-key set | `iterator.remove()` | Registration vẫn còn hợp lệ |

Một biến thể thường thấy ở code cũ là gọi `selector.wakeup()` nhiều lần để “gửi nhiều task”. Nhưng wakeup **không đếm sự kiện**; nên dùng queue, xử lý đến khi queue rỗng, và dùng wakeup làm tín hiệu đánh thức.

## 11. Lỗi thường gặp

1. **“`wakeup()` đóng selector.”** Sai. Nó chỉ đánh thức một lần selection hoặc đánh dấu pending wakeup.
2. **“Mỗi `wakeup()` cộng một lượt đánh thức trong queue.”** Sai. Nhiều wakeup giữa hai lượt selection có hiệu lực như một.
3. **“Nếu gọi wakeup trước select thì không tác dụng.”** Sai. Lượt select tiếp theo có thể trở về ngay.
4. **“`wakeup()` luôn làm `select()` trả 0.”** Sai. Ready keys vẫn có thể được phát hiện.
5. **“`key.cancel()` xóa key khỏi `keys()` ngay.”** Sai. Key invalid ngay, nhưng deregister được xử lý trong selection operation sau.
6. **“`key.cancel()` đóng socket.”** Sai. Channel vẫn open nếu không bị đóng riêng.
7. **“`selector.close()` đóng tất cả channel đăng ký.”** Sai. Nó đóng selector, invalid key và deregister; channel do chủ sở hữu đóng riêng.
8. **“`selector.keys()` chỉ chứa valid keys.”** Sai. Cancelled keys có thể còn ở đó tạm thời.
9. **“Xóa key khỏi `selectedKeys` là hủy đăng ký.”** Sai. Chỉ dọn event đã chọn.
10. **“selectedKeys được Java tự clear sau mọi select.”** Sai. Ứng dụng thường phải tự remove đã xử lý.
11. **“Cứ đọc `isReadable()` khi key có trong selectedKeys.”** Sai. Key có thể đã bị cancel, nên kiểm tra valid và tính tới race.
12. **“Selector và mọi tập key đều thread-safe để thao tác tùy ý.”** Sai. Selected-key set cần tuân thủ synchronization hoặc chỉ do event-loop thread xử lý.
13. **“Thay đổi interestOps từ thread khác đang select có tác dụng ngay trong chính lượt đó.”** Không được bảo đảm; hiệu lực ở lượt selection tiếp theo.
14. **“Đóng selector rồi có thể select lại sau khi wakeup.”** Sai. Selector đã closed thì selection tiếp tục ném `ClosedSelectorException`.

## 12. Câu hỏi tự kiểm tra

**Câu 1:** Thread A đang `selector.select()`, thread B enqueue task rồi gọi `selector.wakeup()`. A có cần đóng selector để xử lý task không?

**Đáp án:** Không. `wakeup` khiến select trở về; A xử lý task rồi có thể tiếp tục select trên selector còn open.

**Câu 2:** Vừa gọi `key.cancel()`, `key.isValid()` là gì và key còn có thể nằm trong `selector.keys()` không?

**Đáp án:** `false` ngay. Có; việc loại khỏi key set và deregister diễn ra trong lượt selection tiếp theo.

**Câu 3:** Đóng selector có tự đóng `SocketChannel` đã đăng ký không?

**Đáp án:** Không. Selector invalid key/deregister, còn các channel open phải do chủ sở hữu quản lý và đóng nếu cần.

**Câu 4:** Sự khác biệt giữa `iterator.remove()` trên `selectedKeys` và `key.cancel()`?

**Đáp án:** `iterator.remove()` chỉ bỏ một sự kiện khỏi tập selected; `cancel()` làm registration của channel trên selector mất hiệu lực.

**Câu 5:** Năm lần `wakeup()` giữa hai lần `select()` có bảo đảm năm lần select tiếp theo đều không block không?

**Đáp án:** Không. Các wakeup có hiệu lực gộp như một lần; sau lần selection tiêu thụ wakeup, những lần kế tiếp có thể block.

### Tài liệu Java 17 chính thức

- [Selector: key sets, selection, concurrency, wakeup, close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [SelectionKey: cancel, isValid, interestOps](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [SelectableChannel: register và blocking mode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [CancelledKeyException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CancelledKeyException.html)
- [ClosedSelectorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedSelectorException.html)
