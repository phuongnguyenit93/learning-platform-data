# select, selectNow, select có thời hạn và cơ chế wakeup

## Mục tiêu

Trong Java NIO, `java.nio.channels.Selector` giúp **một luồng điều phối nhiều kênh có thể chọn** (`SelectableChannel`) mà không cần một thread block `read()` cho từng socket. Trọng tâm của bài này là **ba cách thực hiện selection** và cơ chế **`wakeup()`** để đánh thức event loop đúng lúc.

Sau bài học, bạn có thể:

- Phân biệt `selector.select()`, `selector.selectNow()` và `selector.select(timeoutMillis)` về điều kiện chờ, thời điểm trả về và giá trị trả về.
- Hiểu chính xác trường hợp `timeout = 0`, `timeout < 0`, lựa chọn polling không chặn và việc timeout **không bảo đảm độ chính xác thời gian thực**.
- Giải thích `wakeup()` khi có thread đang `select` hoặc khi `wakeup` xảy ra **trước** lần `select` tiếp theo; vì sao wakeup nhiều lần **không tích lũy thành hàng đợi**.
- Xử lý đúng `selectedKeys()`, `SelectionKey.interestOps()`, `readyOps()` và `Iterator.remove()` trong event loop.
- Phối hợp `ConcurrentLinkedQueue` + `wakeup()` để thread khác gửi lệnh đăng ký/đổi interest/shutdown đến thread sở hữu selector; tránh các race thường gặp.
- Chạy ví dụ Java 17+ kiểm chứng các chế độ với kết quả không phụ thuộc thời gian mạng, rồi áp dụng mẫu lặp selection cho TCP server.

Bài tập trung vào **Selector và cơ chế thức dậy**, không phải thiết kế giao thức TCP hoàn chỉnh. Khi ví dụ dùng socket, đó chỉ để giải thích readiness (`OP_ACCEPT`, `OP_READ`, `OP_WRITE`), không đồng nhất readiness với một thông điệp ứng dụng đầy đủ.

## 1. Selector theo dõi readiness, không đọc dữ liệu thay bạn

Một kênh muốn đăng ký với selector cần ở **nonblocking mode**:

~~~java
server.configureBlocking(false);
SelectionKey key = server.register(selector, SelectionKey.OP_ACCEPT);
~~~

Đoạn minh họa giả định `server` là `ServerSocketChannel` đã mở/bind và `selector` đã mở; không phải một chương trình độc lập. Kênh blocking đăng ký với selector sẽ gặp `IllegalBlockingModeException`.

Mỗi registration được biểu diễn bằng `SelectionKey`. Những bit quan trọng:

| Operation | Kiểu kênh điển hình | Ý nghĩa của ready |
|---|---|---|
| `OP_ACCEPT` | `ServerSocketChannel` | Có thể thử `accept()` mà không block |
| `OP_CONNECT` | `SocketChannel` nonblocking | Có tiến triển kết nối để kiểm tra `finishConnect()` |
| `OP_READ` | `SocketChannel`, `DatagramChannel` | Có thể thử đọc/nhận; EOF cũng có thể làm kênh “readable” |
| `OP_WRITE` | `SocketChannel`, `DatagramChannel` | Có thể thử ghi; **không** bảo đảm ghi hết buffer |

**Readiness chỉ có nghĩa một thao tác I/O có khả năng tiến triển, không có nghĩa hoàn tất.** `SocketChannel.read` vẫn có thể trả `0` và `write` vẫn có thể ghi ít hơn số byte cần. Với TCP, ứng dụng cần lưu state/buffer theo từng connection và tự framing message.

Selector quản lý ba tập key:

- `keys()`: các registration còn thuộc selector.
- `selectedKeys()`: key từng được ghi nhận ready trong một selection trước đó hoặc vừa được cập nhật trong selection mới. Tập này **không tự xóa sạch** sau mỗi lần `select`.
- Cancelled-key set (không truy cập trực tiếp): key đã cancel nhưng chờ bước xử lý cancellation/deregistration trong selection tiếp theo.

Một thread thường **sở hữu** event loop và duyệt selected keys; những thread khác gửi lệnh tới nó thay vì đồng thời thao tác trên `selectedKeys()`.

## 2. Ba cách chọn: `select()`, `selectNow()` và `select(timeout)`

| Lời gọi | Có chờ không? | Khi nào trả về? | Trường hợp phù hợp |
|---|---|---|---|
| `select()` | Có, có thể chờ vô hạn | Có readiness, `wakeup`, interrupt hoặc lý do kết thúc selection khác | Vòng lặp I/O chỉ cần thức khi có sự kiện/lệnh |
| `selectNow()` | **Không block** | Trả về ngay sau khi khảo sát readiness tại thời điểm đó | Thăm dò ngắn, tích hợp với vòng xử lý có công việc khác |
| `select(timeoutMillis)` với `timeout > 0` | Có, chờ **tối đa khoảng** thời hạn được yêu cầu | Readiness, wakeup, interrupt hoặc timeout | Event loop có tác vụ định kỳ, idle housekeeping/deadline |
| `select(0)` | **Chờ như `select()`, không phải poll** | Khi có nguyên nhân đánh thức | Cần chờ không giới hạn nhưng truyền timeout rõ ràng |
| `select(timeoutMillis)` với `timeout < 0` | Không thực hiện selection | Ném `IllegalArgumentException` | Đầu vào sai, phải kiểm tra trước |

Cần phân biệt hai biểu thức rất dễ nhầm:

~~~java
selector.selectNow(); // Poll ngay; KHÔNG chờ.
selector.select(0);   // Có thể chờ vô hạn; KHÔNG phải poll.
~~~

**Độ dài timeout:** tham số `long timeout` được hiểu theo **mili giây**. `select(250)` có thể đợi khoảng 250 ms nếu không có sự kiện, nhưng việc điều độ thread/OS có độ trễ nên **không có bảo đảm realtime**. Cũng có thể trả về **sớm** vì wakeup, interrupt hoặc sự kiện I/O. Để lập lịch nghiệp vụ chính xác, kiểm tra lại đồng hồ đơn điệu (`System.nanoTime()`) sau mỗi vòng.

**Giá trị trả về:** cả ba overload trả về `int` — số key mà tập ready operations được cập nhật bởi **selection operation vừa thực hiện** (theo mô tả API Java 17). Số này có thể bằng `0`. Nó **không nhất thiết bằng `selector.selectedKeys().size()`**, vì selected-key set có thể còn các key bạn chưa remove từ lần trước.

Ví dụ, `selectNow() == 0` không có nghĩa trong toàn bộ vòng đời chưa từng có channel ready; nó chỉ nói selection vừa rồi không ghi nhận cập nhật readiness theo quy tắc API. Đừng dùng return value làm danh sách công việc còn tồn đọng; hãy xử lý selected-key set và cả hàng đợi lệnh của ứng dụng theo đúng mô hình.

### Khi nào nên chọn từng overload?

- **I/O loop thuần túy:** `select()` để ngủ đến khi có readiness; thread khác phải dùng `wakeup()` khi cần nó xử lý lệnh quản trị.
- **Có heartbeat/cleanup:** `select(positiveMillis)` để không ngủ quá lâu nếu không có network event. Sau khi thức, kiểm tra deadline thực tế chứ không chỉ dựa vào số lần đếm timeout.
- **Đang làm việc khác và chỉ muốn thăm dò:** `selectNow()`, nhưng đừng gọi liên tục trong vòng `while` không ngủ khi không có sự kiện — sẽ gây busy spin.

**Lưu ý:** các overload `select(Consumer<SelectionKey>, ...)` và `selectNow(Consumer<SelectionKey>)` cũng có trong Java 17 (từ Java 11); chúng tiêu thụ key thông qua callback thay vì dùng chính selected-key set theo cách bên dưới. Bài dùng các overload `int select...()` đơn giản để thấy rõ `selectedKeys()`.

## 3. `wakeup()`: tín hiệu thức dậy một lần, không phải datagram hay “sự kiện mới”

Theo Java 17, `selector.wakeup()` khiến **selection operation đầu tiên chưa trả về** kết thúc sớm:

1. **Nếu một thread đang block trong `select()` hoặc `select(timeout)`:** `wakeup()` đánh thức lời gọi ấy. Nó có thể trả `0` nếu không có key ready, hoặc trả số khác 0 nếu có readiness đồng thời.
2. **Nếu chưa có selection nào đang chờ:** lần selection tiếp theo sẽ **trả về ngay**, trừ khi `selectNow()` được gọi ở giữa và xóa hiệu ứng wakeup đang chờ.
3. **Nhiều lời gọi `wakeup()` trước một selection:** có cùng tác dụng như **một** lời gọi. Selector không tích lũy “5 token thức dậy” cho 5 lần `select`.
4. **Sau khi một selection đã sử dụng tín hiệu:** những lần `select` sau có thể block bình thường nếu không có readiness hoặc tín hiệu mới.
5. **`wakeup()` không đổi readiness, không ghi vào socket, không đưa lệnh vào queue và không đóng selector.** Nó chỉ làm cho event loop có cơ hội kiểm tra việc khác.

Ví dụ trình tự hợp lệ:

~~~text
Thread A (event loop)             Thread B (producer)
        |                                  |
     select()  <---------------------  wakeup()
        |                                  |
  select() trả về                          |
  kiểm tra queue/selectedKeys              |
        |                                  |
     select() (có thể block tiếp)          |
~~~

Và trường hợp wakeup **trước** khi select:

~~~text
Thread B: queue.add(command)
Thread B: selector.wakeup()

Thread A: selector.select()   → trả về ngay do wakeup đang chờ
Thread A: drain queue         → thực thi command
~~~

Đây là lý do pattern **enqueue trước, wakeup sau** an toàn hơn mô hình chỉ gọi wakeup mà không có nguồn sự thật về công việc. Nếu thread A vừa kiểm tra queue rỗng và chuẩn bị vào `select`, tín hiệu wakeup đến trước `select` vẫn được giữ cho lần selection kế tiếp.

**Bẫy:** giữa `wakeup()` và `select()`, nếu code gọi `selectNow()` thì hiệu ứng wakeup còn chờ bị **xóa**. Nếu đồng thời không còn event hoặc có lệnh chưa xử lý, `select()` sau đó có thể block. Không lấy wakeup làm cơ chế ghi nhận **số lượng** công việc; hãy dùng queue có trạng thái thật.

### `wakeup()` so với `interrupt()` và `close()`

| Thao tác | Ý nghĩa | Hệ quả |
|---|---|---|
| `selector.wakeup()` | Yêu cầu selection sớm trả về | Selector vẫn mở; có thể dùng tiếp |
| `selectionThread.interrupt()` | Yêu cầu interrupt thread đang block | Đánh thức selection, **đặt interrupt status**; cần chính sách xử lý |
| `selector.close()` | Đóng selector | Các registration keys vô hiệu/deregister, selection đang chờ được đánh thức; thao tác select tiếp sẽ ném `ClosedSelectorException` |

`close()` của selector **không đồng nghĩa đóng mọi `SocketChannel` đã đăng ký**. Ứng dụng sở hữu các kênh đó vẫn phải quản lý và đóng chúng theo lifecycle. `interrupt()` không phải lựa chọn thay thế hoàn toàn cho cơ chế stop bình thường nếu event loop còn phải drain tasks và đóng socket có thứ tự.

## 4. Demo Java 17+ kiểm chứng cả ba kiểu chọn và wakeup

File **`SelectorModesDemo.java`** sau có chủ ý **không đăng ký channel nào**. Do không có readiness, mọi lần selection hoàn tất đều trả `0`; ví dụ làm rõ riêng **cơ chế chờ và đánh thức** mà không phụ thuộc vào mạng, cổng hay thời gian packet đến.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.channels.Selector;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SelectorModesDemo {
    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open()) {
            System.out.println("selectNow: " + selector.selectNow());

            selector.wakeup();
            System.out.println("pre-wakeup select: " + selector.select());

            selector.wakeup();
            System.out.println("selectNow clears wakeup: " + selector.selectNow());

            System.out.println("timed select: " + selector.select(50));

            CountDownLatch aboutToSelect = new CountDownLatch(1);
            AtomicInteger result = new AtomicInteger(-1);
            Thread worker = new Thread(() -> {
                aboutToSelect.countDown();
                try {
                    result.set(selector.select());
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            worker.start();
            aboutToSelect.await();
            selector.wakeup();
            worker.join(2_000);

            if (worker.isAlive()) {
                selector.close();
                worker.join();
                throw new IllegalStateException("Selector did not wake");
            }

            System.out.println("cross-thread wakeup select: "
                + result.get());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SelectorModesDemo.java
java SelectorModesDemo
~~~

Stdout cho đường chạy bình thường (đã chạy thử với Java runtime):

~~~text
selectNow: 0
pre-wakeup select: 0
selectNow clears wakeup: 0
timed select: 0
cross-thread wakeup select: 0
~~~

**Giải thích từng bước:**

- `selectNow()` đầu tiên không chờ và không tìm thấy channel đã đăng ký: `0`.
- `wakeup()` xảy ra **trước** `select()` nên `select()` trả ngay, dù không có readiness.
- Gọi `wakeup()` khác, rồi `selectNow()`: lời gọi poll cũng **xóa hiệu ứng wakeup còn chờ**.
- `select(50)` chờ tối đa khoảng 50 ms khi không có key ready. Thời gian thực tế có thể dao động; **không** assert rằng đồng hồ phải đúng 50.000 ms. Giá trị trả về vẫn `0`.
- `CountDownLatch` báo worker đã tới sát điểm gọi `select()`, sau đó main gọi `wakeup()`. Hai lịch chạy đều hợp lệ: worker **đã block** và được đánh thức; hoặc tín hiệu đến **trước** khi worker block và được giữ cho lời gọi sau. `join` giới hạn thời gian test, không dùng `sleep` để “đoán” thời điểm.
- Không có network channel nên `0` ở cuối **không phải lỗi**. Nó chứng minh wakeup có thể trả về không kèm key ready.

Ví dụ là kiểm tra **wakeup semantics**, không phải benchmark thời gian. Nếu hệ thống đang gặp lỗi nền tảng hoặc thread bị chặn bất thường, đoạn kiểm tra thời hạn sẽ báo exception thay vì treo im lặng.

## 5. Demo bổ sung: readiness thật với `OP_ACCEPT`

Một selector thường được dùng sau khi tạo một kênh nonblocking, ví dụ `ServerSocketChannel`. Đoạn Java 17 sau không thay thế cho `main` trên, nhưng cho thấy **selected keys chỉ có ý nghĩa khi đã đăng ký interest**. Đây là **phương thức độc lập có thể đặt trong một class** với import `java.net.*`, `java.nio.channels.*` và `java.util.Iterator`:

~~~java
static void acceptOnce() throws Exception {
    try (Selector selector = Selector.open();
         ServerSocketChannel listener = ServerSocketChannel.open()) {

        listener.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
        listener.configureBlocking(false);
        listener.register(selector, SelectionKey.OP_ACCEPT);

        try (SocketChannel client = SocketChannel.open()) {
            client.connect(listener.getLocalAddress());
            long deadline = System.nanoTime() + 2_000_000_000L;
            boolean accepted = false;

            while (!accepted && System.nanoTime() < deadline) {
                selector.select(200);
                Iterator<SelectionKey> it =
                    selector.selectedKeys().iterator();

                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();

                    if (key.isValid() && key.isAcceptable()) {
                        try (SocketChannel incoming =
                                 ((ServerSocketChannel)
                                 key.channel()).accept()) {
                            accepted = incoming != null;
                        }
                    }
                }
            }

            System.out.println("accepted: " + accepted);
        }
    }
}
~~~

Đã thử phương thức trên với kết nối TCP **loopback** và nhận:

~~~text
accepted: true
~~~

Kết quả này phụ thuộc khả năng tạo kết nối trên máy thực, không phải hằng số mà API cam kết trên mọi môi trường. `select(200)` có thể trả `0` một vài lần, nhưng vòng lặp còn chạy tới deadline. Bản thân `accept()` được gọi trên channel nonblocking nên có thể trả `null`; code kiểm tra trước khi kết luận thành công.

**Vì sao `iterator.remove()` cần thiết?** `selectedKeys()` là tập “đã được chọn” được giữ giữa các vòng; xử lý xong phải **xóa key khỏi selected-key set**, không phải `key.cancel()` một cách tùy tiện. `cancel()` có nghĩa muốn hủy registration, còn remove chỉ đánh dấu **đã xử lý readiness đợt này** và cho selection mới cập nhật thuận lợi.

## 6. Mẫu event loop xử lý đúng selected keys

Mẫu nền tảng trong một I/O thread:

~~~java
while (running) {
    int updated = selector.select(1_000);

    Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove(); // Remove khỏi selected set; không phải cancel.

        if (!key.isValid()) {
            continue; // Có thể đã bị cancel/đóng.
        }

        if (key.isAcceptable()) {
            onAccept(key); // Hàm ứng dụng do bạn triển khai.
        }
        if (key.isReadable()) {
            onRead(key);   // Đọc nonblocking + giữ state theo connection.
        }
        if (key.isWritable()) {
            onWrite(key);  // Ghi nonblocking các byte còn chờ.
        }
    }

    performExpiredTimers();
}
~~~

Đây là **mẫu minh họa**, không phải lớp Java tự chạy: `running`, `selector` và các hàm `onAccept`/`onRead`/`onWrite`/`performExpiredTimers` phải được ứng dụng định nghĩa. Điều cần học không nằm ở tên hàm mà ở **thứ tự**:
1. Chọn readiness hoặc chờ đến timeout/wakeup.
2. Duyệt **toàn bộ** selected-key set, không chỉ số lượng `updated`.
3. Remove từng key khỏi selected-key set **trước** khi dispatch, để tránh xử lý lại key cũ.
4. Kiểm tra `key.isValid()` vì thread khác có thể đóng channel/hủy key.
5. Thực hiện I/O **không block** và không xử lý CPU nặng ngay trong event loop.
6. Làm việc định kỳ sau khi thức dù `updated == 0`.

Nếu mã hiện thực `onRead` đọc không hết dữ liệu ngay được thì vẫn phải quản lý input buffer và protocol framing. Nếu `onWrite` ghi một phần, giữ buffer còn lại, chờ lần `OP_WRITE` tiếp theo. Một selection không phải một read/write đầy đủ.

### `keys()`, `selectedKeys()` và giá trị trả về của select

Đừng viết:

~~~java
int n = selector.select();
if (n > 0) {
    // Sai nếu nghĩ rằng selectedKeys có đúng n phần tử,
    // hoặc quên xử lý task được wakeup khi n == 0.
}
~~~

`n` chỉ phản ánh **selection vừa xong**; `selector.selectedKeys()` có thể giữ key cũ chưa remove. Và một `wakeup()` có thể làm `select` trả `0` dù có lệnh ứng dụng cần thực thi. Cách an toàn là **duyệt selectedKeys và drain command queue**, không xem `n == 0` là bằng chứng “không có việc”.

`selector.keys()` là set tất cả registration, **không** phải các channel đang ready. `key.interestOps()` là các loại I/O ứng dụng muốn theo dõi; `key.readyOps()` là những loại vừa được detector ghi nhận ready. `readyOps` có thể stale nếu không quản lý selected-key set đúng; không tự đồng nhất hai bitmask.

## 7. Thread khác gửi lệnh: command queue + wakeup

Một lỗi khó thấy là thread producer thêm task sau khi event loop đã kiểm tra queue, nhưng trước khi event loop vào `select()`; nếu không gọi `wakeup()`, task có thể đợi tới network event hoặc timeout không mong muốn.

Mô hình phù hợp:

~~~java
// Những khai báo minh họa trong class quản lý event loop:
final Selector selector = Selector.open();
final java.util.concurrent.ConcurrentLinkedQueue<Runnable> commands =
    new java.util.concurrent.ConcurrentLinkedQueue<>();

void submitToEventLoop(Runnable command) {
    commands.offer(command);
    selector.wakeup();
}
~~~

Đây là **đoạn minh họa thuộc class**; cần khai báo/đóng selector theo vòng đời và xử lý `IOException` từ `Selector.open()` trong constructor thích hợp. `commands` là nơi lưu **công việc thật**; `wakeup()` chỉ là tín hiệu để thread selector sớm drain queue.

Event loop sau khi select:

~~~java
selector.select();

Runnable command;
while ((command = commands.poll()) != null) {
    command.run(); // Chỉ công việc ngắn, không chặn event loop lâu.
}

// Sau đó duyệt selector.selectedKeys() bằng iterator/remove.
// Khi shutdown, kiểm tra running flag và đóng các channel theo policy.
~~~

Đây là snippet tương ứng, không phải chương trình `main` độc lập.

**Lệnh đổi interest từ thread khác:** thay vì thread producer tự sửa key trong khi selection đang diễn ra, thường gửi command tới I/O thread:

~~~java
submitToEventLoop(() -> {
    if (key.isValid()) {
        key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
    }
});
~~~

Cần bảo đảm `key` đại diện `SocketChannel` hỗ trợ các operation này. InterestOps thay đổi **trong lúc một selection đang tiến hành** chỉ được xét cho selection kế tiếp theo tài liệu; do đó việc tổ chức cập nhật qua owner thread và wakeup giúp giảm race.

**Bẫy mất tín hiệu:** dùng sai thứ tự `selector.wakeup(); commands.offer(command);` có thể khiến selector thức và kiểm tra queue trước khi command xuất hiện, rồi block trở lại. Thứ tự đúng là **enqueue → wakeup**. Tương tự, sau khi `wakeup` đã tạo tín hiệu chờ, gọi `selectNow()` ở giữa có thể tiêu thụ tín hiệu ấy; nếu ứng dụng dùng queue và kiểm tra nó ở mỗi vòng, công việc vẫn không phụ thuộc vào “đếm wakeup”.

**Bẫy coalescing:** năm task được enqueue nhanh có thể chỉ cần một wakeup. Đừng viết hệ thống mong đợi mỗi `wakeup` tương ứng đúng một lần xử lý; hãy `poll` cho đến khi queue hết. Nếu có task đến trong lúc drain, vì producer gọi wakeup sau offer nên event loop có thể được đánh thức một lần nữa; việc xử lý task chính xác đến từ queue, không từ số wakeup.

## 8. `OP_WRITE` và vấn đề busy loop

Với TCP socket có thể ghi, `OP_WRITE` thường ready phần lớn thời gian. Nếu đăng ký theo dõi `OP_WRITE` **mọi lúc** dù không có byte cần gửi, `select()` sẽ liên tục trả về và event loop có thể dùng CPU cao dù không làm gì hữu ích.

Quy tắc chuẩn:

1. Khi outbound queue **rỗng**, thường chỉ quan tâm `OP_READ` (và các interest khác thực sự cần); **không bật `OP_WRITE`**.
2. Khi có byte cần gửi, đưa dữ liệu vào buffer/queue rồi **bật `OP_WRITE`** qua owner thread, `wakeup()` nếu thao tác từ thread khác.
3. Ở `onWrite`, gọi `SocketChannel.write(buffer)`, có thể chỉ ghi một phần.
4. Nếu vẫn còn byte thì giữ `OP_WRITE`; khi queue đã **drain hết**, **bỏ `OP_WRITE`** để tránh busy-spin.

Ví dụ tính bitmask (đoạn minh họa, biến `key` và trạng thái queue thuộc handler):

~~~java
int current = key.interestOps();
key.interestOps(current | SelectionKey.OP_WRITE);  // Cần gửi.

int afterDrained = key.interestOps();
key.interestOps(afterDrained & ~SelectionKey.OP_WRITE); // Hết dữ liệu.
~~~

Không bật `OP_WRITE` khi channel không có pending outbound data chỉ vì “muốn ghi nhanh”. Tương tự, `selectNow()` gọi liên tục trong một vòng không nghỉ sẽ đốt CPU; selector có thể làm việc hữu ích bằng blocking select hoặc timed select.

## 9. Chờ có thời hạn và deadline nghiệp vụ

`selector.select(500)` chỉ định **một lượt chờ tối đa xấp xỉ 500 ms**, không phải timer chính xác tuyệt đối. Một I/O event hoặc wakeup làm nó trả về sớm. Nếu cần task định kỳ hay timeout client:
- Dùng thời gian đơn điệu `System.nanoTime()` để lưu deadline.
- Sau mỗi lần select — **kể cả khi return value > 0** — kiểm tra các deadline đã hết hạn.
- Tính lại thời gian chờ từ **deadline kế tiếp**, không cứ lấy cố định 500 ms nếu có deadline sớm hơn.
- Khi đổi nanosecond sang millis, cần chặn `0` nếu vẫn muốn **thời hạn dương**: `select(0)` sẽ có nghĩa **chờ vô hạn**.

Một mẫu tính timeout cho mục tiêu còn thời gian (đoạn minh họa Java, biến `deadlineNanos` được tính trước bằng `System.nanoTime()`):

~~~java
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    runExpiredTimers();
} else {
    long millis = Math.max(
        1L,
        java.util.concurrent.TimeUnit.NANOSECONDS
            .toMillis(remainingNanos));
    selector.select(millis);
    runExpiredTimers(); // Recheck bằng System.nanoTime().
}
~~~

Code này **chỉ là một vòng thời hạn minh họa**; event loop thực phải tiếp tục dispatch selected keys và commands. Làm tròn từ nanos sang millis + độ trễ hệ thống có thể làm chọn sai lệch thời điểm nhỏ; nó không thay thế scheduler thời gian thực.

Nếu việc xử lý event/read/write/CPU bên trong event loop kéo dài hàng giây, `select(100)` cũng **không đảm bảo** ứng dụng sẽ chạy timers đúng mỗi 100 ms. I/O thread phải xử lý nhanh, chia work hợp lý và offload CPU nặng ra executor khác.

## 10. Thức dậy khi shutdown và vòng đời resource

Một shutdown phối hợp giữa các thread có thể dùng cờ `running` và queue:

~~~java
// Thread điều phối shutdown:
running.set(false);
selector.wakeup(); // Đánh thức I/O thread khỏi select().

// Trong I/O thread sau khi select trả:
if (!running.get()) {
    // Thoát vòng, đóng registered channels và selector theo lifecycle.
}
~~~

Mẫu này giả định `running` là `AtomicBoolean`. Đừng chỉ đặt cờ false mà quên `wakeup()` nếu event loop đang `select()` vô thời hạn — nó có thể không nhận cờ mới cho đến khi có I/O khác. Với `select(timeout)` hữu hạn, cuối cùng vòng có thể thức khi timeout nhưng shutdown chậm hơn không cần thiết.

Các trường hợp ngoại lệ cần dự liệu:

- **`ClosedSelectorException`:** selector đã đóng, không tiếp tục gọi `select`/`selectedKeys` như bình thường.
- **`CancelledKeyException`:** key đã bị hủy trong lúc kiểm tra readiness/interest ops; cần đóng hoặc bỏ qua channel theo vòng đời.
- **`IOException`:** lỗi hệ thống trong selection/I/O cần được ghi nhận và phục hồi/đóng phù hợp. Không dùng vòng `while(true)` bắt mọi exception rồi lập tức `selectNow()` khiến CPU spin.
- **Thread interrupt:** selector bị đánh thức và interrupt status của thread được đặt. Một vòng lặp không xử lý interrupt có thể cứ quay nhanh; hãy có chính sách thoát/khôi phục rõ.
- **Selector close:** hủy registration và đánh thức selection, nhưng việc quản lý/đóng `SocketChannel`, `ServerSocketChannel` vẫn là trách nhiệm chương trình.

Với ứng dụng có nhiều kết nối, đừng đóng selector ngay khi nhận lệnh shutdown nếu còn việc dọn socket/flush outbound cần thực hiện: hãy xác định rõ cần **graceful drain** hay **immediate close**, có deadline, không giữ kết nối vô hạn.

## 11. Kiểm thử các tình huống biên

| Thử nghiệm | Kết quả mong đợi |
|---|---|
| Selector mới, không đăng ký key, gọi `selectNow()` | Trả `0` ngay |
| `wakeup()` rồi `select()`, chưa có readiness | Trả ngay, có thể `0` |
| `wakeup()` nhiều lần trước selection | Có tác dụng thức cho **một** selection kế, không xếp nhiều lần |
| `wakeup()` rồi `selectNow()`, tiếp theo `select()` | `selectNow` đã xóa hiệu ứng wakeup chờ; `select` sau có thể block |
| `select(50)` với selector không có ready key | Trả khoảng sau timeout hoặc sớm hơn khi có tác nhân đánh thức; `0` trong demo |
| `select(0)` trên selector không có readiness | Có thể chờ vô hạn; cần thread khác wakeup/close/interrupt |
| `select(-1)` | Ném `IllegalArgumentException` |
| Một key nằm trong `selectedKeys` nhưng chưa remove | Có thể tồn tại qua vòng chọn tiếp; không suy `size == return value` |
| Cross-thread enqueue ngay trước `select` | `offer` rồi `wakeup` giúp lệnh sớm được xử lý |
| Bật `OP_WRITE` khi queue output rỗng | Nguy cơ selector quay rất nhanh, CPU cao |
| Cancel key trong event loop | Bỏ qua invalid key; deregistration được xử lý bởi selection |
| Đóng selector khi thread khác đang select | Selection được đánh thức, tài nguyên selector được giải phóng; quản lý channel riêng |

**Lưu ý test thời gian:** không dùng assert `elapsedMillis == 50`. Hãy kiểm tra rằng poll `selectNow` không block lâu, timed `select` không chờ không giới hạn trong điều kiện bình thường, và wakeup làm selection sớm kết thúc; kiểm thử concurrency nên dùng `CountDownLatch` thay vì dựa vào `Thread.sleep` để đoán race. Test nên có deadline riêng để tránh treo CI.

## 12. Những sai lầm thường gặp

| Sai lầm | Vì sao sai? |
|---|---|
| Nghĩ `select(0)` tương đương `selectNow()` | `select(0)` **chờ vô hạn**, còn `selectNow` không block |
| Nghĩ `wakeup()` luôn trả về đúng 0 | Readiness có thể xuất hiện đồng thời, giá trị trả về có thể >0 |
| Nghĩ một wakeup tương ứng một command | Nhiều wakeup coalesce, phải lưu command trong queue |
| Gọi `wakeup()` trước khi enqueue | Có cửa sổ race khiến selector ngủ lại trước khi task xuất hiện |
| Gọi `selectNow()` sau wakeup rồi trông đợi `select()` còn thức | `selectNow` đã xóa hiệu ứng wakeup chờ |
| Nếu `select() == 0` thì bỏ qua command queue | `0` có thể do wakeup/timeout, queue vẫn có việc |
| Cho rằng `select()` trả đúng `selectedKeys().size()` | Tập selected giữ key chưa remove; return value phản ánh selection hiện tại |
| Duyệt `selectedKeys` nhưng không `Iterator.remove()` | Key đã xử lý còn nằm trong tập và bị xử lý lại |
| Dùng `key.cancel()` thay `iterator.remove()` | Cancel hủy registration, không phải đánh dấu đã xử lý một readiness |
| Thay đổi interest set khi selection đang chạy và mong tác dụng tức thời | Thay đổi sẽ được quan sát ở selection kế; phải phối hợp wakeup/owner thread |
| Đăng ký `OP_WRITE` mọi lúc | Socket thường writable → CPU spin |
| Thực hiện CPU task lâu trong selector thread | Làm đình trệ xử lý socket và deadline khác |
| Đăng ký blocking channel với selector | `IllegalBlockingModeException`; `configureBlocking(false)` trước |
| Dựa vào một `read` để có message TCP hoàn chỉnh | Readiness không lưu message framing; TCP là stream |
| `close()` selector rồi nghĩ mọi socket cũng đã đóng | Application phải quản lý vòng đời channel riêng |

## 13. Bài tập tự kiểm tra

1. Vì sao `select(0)` không phải cách kiểm tra sự kiện có sẵn? Hãy nêu API đúng để poll.
2. Thread A đang `select()`, thread B gọi `wakeup()` nhưng không có socket ready. Giá trị `select` trả về có thể bằng bao nhiêu?
3. Một thread gọi `wakeup()` hai lần **trước** khi event loop vào `select()`. Nó có được “hai lần select không block” không? Vì sao?
4. Vì sao phải dùng `queue.offer(command)` **trước** `selector.wakeup()` khi điều khiển event loop từ thread khác?
5. Có 3 key đang nằm trong `selectedKeys` vì vòng trước chưa remove, `selectNow()` mới trả `0`. Có thể kết luận `selectedKeys` rỗng không?
6. Nếu `selectNow()` được gọi ngay sau khi `wakeup()` và trước `select()`, tín hiệu thức dậy còn tác dụng không?
7. Tại sao chỉ thêm `OP_WRITE` khi outbound queue có dữ liệu? Khi đã ghi hết cần làm gì?
8. Một công việc định kỳ phải chạy sau 200 ms. Nếu `select(200)` trả sớm sau 30 ms vì I/O ready, có nên thực thi task ngay không?
9. Thread khác gọi `key.interestOps(...)` trong lúc selection. Có nên kỳ vọng selection đang diễn ra nhận ngay interest mới không?
10. Để dừng event loop đang `select()` vô thời hạn, đặt `running = false` đã đủ chưa?
11. Khi `selectedKeys` có key invalid, xử lý như thế nào? Khác gì với việc cancel mọi key sau mỗi lần xử lý?

**Đáp án gợi ý:** (1) `selectNow()`; (2) có thể `0`; (3) không, wakeup coalesce; (4) tránh race “thức trước khi có việc”; (5) không; (6) `selectNow` xóa wakeup đang chờ; (7) bỏ `OP_WRITE` khi đã drain; (8) chỉ chạy khi kiểm tra deadline thực tế đã tới; (9) không, ảnh hưởng tới selection kế; (10) cần `wakeup()`/cơ chế đánh thức; (11) bỏ qua/đóng đúng lifecycle, `Iterator.remove()` cho selected key đã xử lý khác với `key.cancel()` hủy registration.

## 14. Tổng kết

- **`select()`** chờ readiness/wakeup/interrupt; **`selectNow()`** không chặn; **`select(timeout > 0)`** chờ có thời hạn xấp xỉ; **`select(0)` là chờ vô hạn**, không phải polling.
- **`wakeup()`** đánh thức selection đang chờ hoặc selection tiếp theo; các lần gọi lặp **không tích lũy**. `selectNow()` có thể tiêu thụ pending wakeup.
- **Có thể trả `0` mà vẫn phải làm việc**: kiểm tra command queue và deadlines; dùng `Iterator.remove()` khi xử lý selected keys, không suy return value bằng số selected keys đang tồn đọng.
- **Cross-thread:** giữ công việc trong queue, `offer → wakeup`, cập nhật interest ở owner thread khi có thể.
- **Tránh busy spin:** đừng poll `selectNow` liên tục hoặc bật `OP_WRITE` khi không có output; giữ xử lý I/O nonblocking và CPU work ngắn trong selector thread.
- **Quản lý lifecycle:** cờ dừng + wakeup, xử lý exception/interrupt, đóng selector và các channel theo chính sách rõ ràng.

### Tài liệu tham khảo

- [Oracle Java SE 17 — Selector: select, selectNow, select(timeout), wakeup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Oracle Java SE 17 — SelectionKey: interestOps, readyOps, isValid](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Oracle Java SE 17 — SelectableChannel: configureBlocking/register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [Oracle Java SE 17 — ServerSocketChannel, nonblocking accept](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Oracle Java SE 17 — ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)
