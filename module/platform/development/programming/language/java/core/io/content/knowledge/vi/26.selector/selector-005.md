# Java NIO Selector: `select()`, `selectNow()` và `select(timeout)`

## 1. Selector giải quyết bài toán gì?

Khi server cần theo dõi hàng trăm socket, tạo một luồng luôn chờ đọc trên từng kết nối có thể tốn tài nguyên. Java NIO cung cấp **`java.nio.channels.Selector`** để một luồng kiểm tra những **`SelectableChannel`** nào hiện *sẵn sàng* thực hiện thao tác I/O đã quan tâm, rồi xử lý các channel tương ứng.

Selector không trực tiếp chuyển dữ liệu. Nó chỉ giúp ứng dụng nhận biết các điều kiện sẵn sàng như:

- `SelectionKey.OP_ACCEPT`: server socket có khả năng chấp nhận kết nối.
- `SelectionKey.OP_CONNECT`: socket đang kết nối có thể hoàn tất kết nối.
- `SelectionKey.OP_READ`: channel có thể thực hiện thao tác đọc mà không chờ dữ liệu theo nghĩa readiness của hệ thống.
- `SelectionKey.OP_WRITE`: channel có thể thực hiện thao tác ghi theo điều kiện readiness.

**Sẵn sàng không đồng nghĩa hoàn tất công việc.** Socket sẵn sàng đọc vẫn có thể trả `0`, `-1` hoặc một lượng byte nhỏ hơn kỳ vọng; socket sẵn sàng ghi vẫn có thể chỉ ghi một phần. Selector không thay thế việc kiểm tra kết quả `read/write` và quản lý `ByteBuffer`.

Ba cách chọn key là trọng tâm:

1. `selector.select()`: **chờ** cho đến khi có sự kiện sẵn sàng hoặc được đánh thức/ngắt.
2. `selector.selectNow()`: **kiểm tra ngay**, không chờ.
3. `selector.select(timeoutMillis)`: **chờ có giới hạn thời gian** nếu `timeoutMillis > 0`; riêng **`timeoutMillis == 0` lại chờ không giới hạn**.

Một chương trình non-blocking thường dùng `select()` hoặc `select(timeout)` trong **event loop**. `selectNow()` thích hợp khi chương trình còn các công việc khác và chỉ muốn thăm dò I/O ngay lúc đó.

## 2. Chuẩn bị Selector, channel và SelectionKey

Cú pháp cơ bản:

~~~java
// Đoạn minh họa, không phải toàn bộ chương trình.
try (Selector selector = Selector.open();
     ServerSocketChannel server = ServerSocketChannel.open()) {
    server.configureBlocking(false);
    server.bind(new InetSocketAddress("127.0.0.1", 8080));

    SelectionKey key = server.register(
            selector, SelectionKey.OP_ACCEPT);
    // Chạy vòng chọn và xử lý sự kiện...
}
~~~

Cần các import tương ứng từ `java.net` và `java.nio.channels`. Chỉ đăng ký được channel hỗ trợ selection và được đặt ở **non-blocking mode**:

~~~java
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

Nếu cố đăng ký một channel đang ở blocking mode, có thể gặp `IllegalBlockingModeException`. Nếu interest operation không thuộc `channel.validOps()`, `register` có thể ném `IllegalArgumentException`. Một `FileChannel` thông thường **không phải** `SelectableChannel`; không thể đăng ký FileChannel với Selector như socket.

### Bộ ba tập key

Mỗi selector duy trì những tập key liên quan:

- **Key set — `selector.keys()`:** các `SelectionKey` đã đăng ký với selector, chưa được hủy/loại bỏ hoàn toàn.
- **Selected-key set — `selector.selectedKeys()`:** các key được lựa chọn và chưa bị ứng dụng lấy khỏi tập đã chọn.
- **Cancelled-key set:** tập xử lý nội bộ của selector; `key.cancel()` sẽ lên lịch hủy, và key bị loại khỏi tập trong quá trình chọn tiếp theo hoặc khi selector xử lý việc hủy.

Một `SelectionKey` liên kết **một channel + một selector**, có các thuộc tính:

| Thành phần | Ý nghĩa |
|---|---|
| `channel()` | Channel được đăng ký |
| `selector()` | Selector sở hữu key |
| `interestOps()` | Những thao tác ứng dụng **muốn được thông báo**, như `OP_READ \| OP_WRITE` |
| `readyOps()` | Những thao tác đã được ghi nhận là **sẵn sàng** sau selection |
| `isReadable()/isWritable()/isAcceptable()/isConnectable()` | Kiểm tra bit trong `readyOps` |
| `attachment()/attach(obj)` | Gắn trạng thái kết nối hoặc đối tượng xử lý của ứng dụng |
| `isValid()/cancel()` | Kiểm tra/hủy đăng ký |

Không nhầm `interestOps` (cái muốn theo dõi) với `readyOps` (cái đã quan sát sẵn sàng). Trong nhiều tình huống ứng dụng chỉ cần quan tâm `OP_READ`, không nên bật `OP_WRITE` mọi lúc.

## 3. `select()`: chờ sự kiện

Chữ ký:

~~~java
int readyCount = selector.select();
~~~

`select()` thực hiện một lượt selection **blocking**. Theo đặc tả, lời gọi có thể kết thúc khi:

- Có ít nhất một channel được chọn vì sẵn sàng với thao tác thuộc interest set.
- Luồng khác gọi `selector.wakeup()`.
- Luồng đang chọn bị `interrupt()`.
- Selector bị đóng trong quá trình chờ (trường hợp lỗi/vòng đời cần xử lý).

Nó **không có tham số giới hạn thời gian**. Nếu không có gì sẵn sàng và không có tác nhân đánh thức, luồng có thể chờ lâu. Khác với `Thread.sleep()`, selector chờ các điều kiện I/O và quản lý đăng ký key.

Ví dụ luồng xử lý một listener TCP thường là:

~~~java
// Minh họa trong event loop: selector và server đã mở/đăng ký.
while (running) {
    int updated = selector.select();
    if (updated == 0) {
        continue; // Có thể do wakeup/interrupt, không tự giả định có I/O.
    }

    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove(); // Xóa khỏi selected-key set để lần sau chọn lại.
        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            // server.accept(), cấu hình socket non-blocking và register.
        } else if (key.isReadable()) {
            // channel.read(buffer), xử lý 0 / -1 / partial read.
        }
    }
}
~~~

Đoạn trên **không độc lập chạy được** vì `running`, các channel và nhánh xử lý chưa được khai báo. Mục 7 có ví dụ hoàn chỉnh Java 17+.

**Không dùng số trả về để quyết định xử lý một cách máy móc.** `select()` trả số key có **ready-operation set được cập nhật** trong lượt chọn; không nhất thiết bằng số key hiện diện trong `selectedKeys()`. Khi muốn xử lý các key đã được chọn, hãy duyệt selected-key set theo vòng đời của nó.

## 4. `selectNow()`: kiểm tra ngay mà không chờ

Chữ ký:

~~~java
int updated = selector.selectNow();
~~~

- Thực hiện selection **non-blocking**: không chờ một channel trở nên sẵn sàng.
- Có thể trả về `0` nếu không có thao tác sẵn sàng mới được ghi nhận.
- Có thể trả về số dương nếu ready-operation sets của các key được cập nhật.
- Vẫn cập nhật selected-key set theo quy tắc selection thông thường.
- **Xóa tác dụng của các lời gọi `wakeup()` còn đang chờ** trước đó.

Ví dụ:

~~~java
// Minh họa: selector đã có ít nhất một registered key.
doOtherWork();
int updated = selector.selectNow();
if (updated > 0) {
    processSelectedKeys(selector);
}
~~~

`doOtherWork()` và `processSelectedKeys(...)` là hàm do ứng dụng định nghĩa. Nếu luồng liên tục gọi `selectNow()` trong một vòng không chờ và không có việc khác, nó có thể trở thành **busy polling**, tiêu tốn CPU.

### Trường hợp thực tế nên dùng

- Tích hợp việc kiểm tra I/O vào một vòng lặp đã có scheduler, game loop hoặc tác vụ tính toán.
- Kiểm tra xem có event nào sẵn sàng *ngay lúc này* mà không dừng công việc chính.
- Thực hiện một lượt selection không chờ để đồng bộ hóa trạng thái key sau một thay đổi nhất định — nhưng phải nhớ nó có thể **tiêu thụ tác dụng wakeup đang chờ**.

`selectNow()` **không có nghĩa lấy các byte ngay lập tức** và **không tự chuyển channel về non-blocking**. Việc đọc/ghi vẫn phải được ứng dụng thực hiện và phải xử lý kết quả chính xác.

## 5. `select(timeout)`: chờ có giới hạn, với bẫy `timeout=0`

Chữ ký:

~~~java
int readyCount = selector.select(500); // timeout dương: chờ khoảng tối đa 500 ms.
~~~

Tham số của overload này là **`long`, đơn vị millisecond**, không phải giây hoặc nanosecond.

| Cách gọi | Chế độ chờ | Nhận xét |
|---|---|---|
| `selector.select()` | Chờ không thời hạn mặc định | Trả khi có readiness, wakeup, interrupt hoặc lỗi/vòng đời tương ứng |
| `selector.selectNow()` | Không chờ | Trả về sau lượt thăm dò hiện tại |
| `selector.select(1)` | Chờ tối đa theo yêu cầu khoảng 1 ms | Không đảm bảo precision 1 ms |
| `selector.select(500)` | Chờ tối đa khoảng 500 ms | Có thể trở về trước timeout |
| `selector.select(0)` | **Chờ vô thời hạn** | **Không tương đương `selectNow()`** |
| `selector.select(-1)` | Không hợp lệ | Ném `IllegalArgumentException` |

Chính xác hơn, Java **không hứa thời hạn real-time tuyệt đối**: scheduling, OS và timer resolution có thể khiến thời điểm trở về sớm/trễ so với thời gian đồng hồ dự kiến. `timeout > 0` là giới hạn chờ theo ngữ nghĩa API, không phải một SLA thời gian cứng.

### Ví dụ dùng timeout cho công việc định kỳ

Một ứng dụng cần xử lý I/O nhưng ít nhất khoảng một lần trong mỗi chu kỳ kiểm tra timer:

~~~java
// Minh họa: selector đã được cấu hình, không phải chương trình độc lập.
while (running) {
    selector.select(250);
    handleSelectedKeys(selector);
    runScheduledTasksIfDue();
}
~~~

Timeout này tránh việc **đợi I/O vô thời hạn** khiến timer không bao giờ được kiểm tra. Tuy vậy:

- Không bảo đảm `runScheduledTasksIfDue()` chạy *chính xác* mỗi 250 ms.
- Nếu `handleSelectedKeys(...)` xử lý lâu, timer còn có thể bị trễ.
- Nếu phải đợi deadline chính xác hơn, tính **thời gian còn lại tới deadline gần nhất**, thay vì luôn chọn một timeout cố định.
- Nếu có thread khác đẩy task cần chạy gấp vào queue, dùng `selector.wakeup()` để không cần chờ hết timeout.

### Không tạo timeout bằng cách luôn truyền 0

Một lỗi nguy hiểm:

~~~java
// Sai nếu mong kiểm tra ngay lập tức:
selector.select(0); // 0 = chờ vô thời hạn, KHÔNG phải poll.
~~~

Hãy dùng `selectNow()` để **poll không chờ**. Nếu cần deadline thực, dùng timeout dương và duy trì deadline bằng `System.nanoTime()` (thích hợp đo khoảng thời gian, tránh phụ thuộc đồng hồ wall-clock bị điều chỉnh).

## 6. So sánh ba phương thức ở cùng một tình huống

Giả sử một `Pipe.SourceChannel` hoặc `SocketChannel` đã đăng ký `OP_READ`, nhưng hiện tại chưa có byte nào để đọc:

~~~text
Không có dữ liệu:
  select()       -> chờ đến khi có sự kiện hoặc wakeup/interrupt
  selectNow()    -> thăm dò rồi trở về ngay, thường trả 0
  select(100)    -> chờ tới khi có event hoặc khoảng 100 ms
  select(0)      -> chờ không thời hạn

Khi dữ liệu mới xuất hiện:
  cả ba phương thức đều có thể ghi nhận OP_READ
  selectedKeys() chứa key tương ứng để ứng dụng xử lý
  ứng dụng vẫn phải gọi read(...) và kiểm tra kết quả
~~~

| Tiêu chí | `select()` | `selectNow()` | `select(timeout > 0)` |
|---|---|---|---|
| Có thể block | Có | Không | Có, tới khi sự kiện/wakeup/interrupt/timeout |
| Có tham số thời gian | Không | Không | Có: millisecond |
| Trả `0` được không | Có | Có | Có |
| Cập nhật `selectedKeys()` | Có | Có | Có |
| Được `wakeup()` đánh thức | Có | Không cần chờ; đồng thời xóa wakeup pending | Có |
| Hợp với trường hợp nào | Event loop chủ yếu chờ I/O | Poll lồng vào công việc khác | Event loop có deadline hoặc timer |
| Rủi ro khi dùng sai | Không chạy việc định kỳ nếu thiếu wakeup | Spin/busy polling tốn CPU | Nhầm `0` với non-blocking; kỳ vọng độ chính xác timer tuyệt đối |

Điểm chung: **kết quả trả về không phải số byte** và không phải “bao nhiêu socket đã đọc xong”. Nó liên quan số key có ready set được cập nhật trong lượt chọn.

## 7. Chương trình Java 17+ hoàn chỉnh: kiểm thử cả ba hình thức

Ví dụ dùng `java.nio.channels.Pipe` nên **không cần port mạng** và không bị phụ thuộc vào kết nối Internet. `Pipe.SourceChannel` là `SelectableChannel`, hỗ trợ `OP_READ`; `Pipe.SinkChannel` ghi dữ liệu vào đầu kia.

Chương trình làm theo thứ tự:

1. Đăng ký source non-blocking để theo dõi `OP_READ`.
2. Gọi `selectNow()` khi pipe chưa có dữ liệu.
3. Gọi `select(40)` khi chưa có dữ liệu — kết thúc bởi timeout.
4. Ghi hai byte ASCII `OK` vào sink; sau đó gọi `select()` và nhận key có `OP_READ`.
5. Duyệt `selectedKeys()`, xóa key đã chọn và đọc ra dữ liệu.
6. Gọi `wakeup()` trước một lần `select()` khác để chứng minh có thể đánh thức mà không phải chờ dữ liệu.

Lưu chính xác tệp **`SelectorSelectModesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class SelectorSelectModesDemo {

    private static void writeAll(Pipe.SinkChannel sink, ByteBuffer src)
            throws IOException {
        while (src.hasRemaining()) {
            sink.write(src); // Sink mặc định ở blocking mode.
        }
    }

    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            System.out.println("selectNow(empty)="
                    + selector.selectNow());

            System.out.println("select(40,empty)="
                    + selector.select(40));

            writeAll(sink, ByteBuffer.wrap(
                    "OK".getBytes(StandardCharsets.US_ASCII)));

            System.out.println("select(ready)="
                    + selector.select());

            Iterator<SelectionKey> iterator =
                    selector.selectedKeys().iterator();

            while (iterator.hasNext()) {
                SelectionKey key = iterator.next();
                iterator.remove(); // Rất quan trọng.

                if (!key.isValid() || !key.isReadable()) {
                    continue;
                }

                Pipe.SourceChannel readable =
                        (Pipe.SourceChannel) key.channel();
                ByteBuffer data = ByteBuffer.allocate(16);
                int count = readable.read(data);

                data.flip();
                byte[] bytes = new byte[data.remaining()];
                data.get(bytes);

                System.out.println("read(" + count + ")="
                        + new String(bytes, StandardCharsets.US_ASCII));
            }

            selector.wakeup();
            System.out.println("select(wakeup)=" + selector.select());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SelectorSelectModesDemo.java
java SelectorSelectModesDemo
~~~

**Stdout trong điều kiện chạy bình thường, không có ngắt luồng hay tác nhân I/O bên ngoài:**

~~~text
selectNow(empty)=0
select(40,empty)=0
select(ready)=1
read(2)=OK
select(wakeup)=0
~~~

Giải thích từng dòng:

- `selectNow(empty)=0` vì chưa có byte và lệnh không chờ.
- `select(40,empty)=0` vì chưa có readiness trước khi timeout khoảng 40 ms (không có yêu cầu đo chính xác số milliseconds).
- Sau `writeAll`, pipe đã có hai byte; source được xem là read-ready nên `select()` ghi nhận một key.
- `selectedKeys()` được duyệt và `iterator.remove()` xóa key khỏi tập đã chọn. `read(...)` lấy được hai byte và chương trình hiển thị `OK`.
- Sau khi byte đã được đọc hết, `selector.wakeup()` làm cho lần `select()` tiếp theo trở về ngay và ở ví dụ này không có key ready mới, nên trả 0.

Ví dụ **không dùng `Thread.sleep()` để giả lập I/O**; timeout được chứng minh qua lượt chọn không có dữ liệu và readiness được kích hoạt bởi ghi pipe. Trong một môi trường có sự cố I/O, đóng kênh sớm hoặc ngắt luồng từ ngoài, kết quả có thể không giống stdout mẫu — ứng dụng thật phải xử lý các trường hợp đó.

### Vì sao source cần non-blocking?

Các channel được `register(selector, ...)` phải cho phép selection. `source.configureBlocking(false)` là bước bắt buộc. Lệnh `sink.write(...)` trong ví dụ không đăng ký selector và có thể hoạt động blocking. Đó là hai đối tượng channel khác nhau nên không mâu thuẫn.

## 8. `selectedKeys()` không tự rỗng sau mỗi lần select

Một điểm dễ dẫn tới lỗi là **tập đã chọn tồn tại giữa các lần gọi selection**.

Quy trình của các phương thức `select()` / `selectNow()` / `select(timeout)`:

1. Kiểm tra các đăng ký đang bị hủy và bỏ key không còn hợp lệ khi cần.
2. Hỏi hệ thống về các thao tác channel đang sẵn sàng.
3. Nếu key chưa nằm trong selected-key set, thêm vào và đặt ready-operation set.
4. Nếu key **đã** nằm trong selected-key set, các readiness bit mới có thể được **hợp** (OR) vào ready-operation set hiện có.
5. Selected-key set không được tự động xóa hết bởi mỗi lần select. **Ứng dụng chịu trách nhiệm lấy key đã xử lý ra khỏi tập**.

Ví dụ cách chuẩn:

~~~java
// Đoạn minh họa thuộc một event loop.
int updated = selector.select();
Iterator<SelectionKey> iter = selector.selectedKeys().iterator();

while (iter.hasNext()) {
    SelectionKey key = iter.next();
    iter.remove(); // Không để key cũ lưu mãi trong selectedKeys().

    if (!key.isValid()) {
        continue;
    }
    if (key.isReadable()) {
        // Đọc tới khi phù hợp với non-blocking I/O và protocol.
    }
}
~~~

Có thể dùng `selector.selectedKeys().clear()` sau khi đã lấy một bản sao các key, nhưng `iterator.remove()` trong lúc duyệt thường rõ ràng và ít tạo lỗi hơn. **Không gọi `selector.keys().clear()`** với ý định chỉ loại những key vừa được chọn; `keys()` là tập các đăng ký, không phải selected-key set để consume.

### Vì sao `selectedKeys().size()` và return value có thể khác?

Một key tồn tại trong selected-key set từ lượt trước có thể không được cập nhật readiness ở lượt hiện tại, song vẫn ở trong tập vì ứng dụng chưa remove. Vì vậy:

- `select()` có thể trả `0` mà `selectedKeys()` **chưa rỗng**.
- Không coi `selectedKeys().size()` là “số sự kiện mới trong lượt này”.
- Không dựa vào return value một cách độc lập với việc quản lý tập key và trạng thái channel.

Nếu để key cũ trong selected set quá lâu, `isReadable()` có thể khiến logic xử lý dữ liệu đã cạn hoặc readiness không còn khớp kỳ vọng. Điều này đặc biệt dễ gây busy loop và khó debug khi nhiều thao tác được OR vào `readyOps()`.

## 9. `wakeup()`, interrupt và close

### `selector.wakeup()`

Khi một thread đang chờ trong `select()` hoặc `select(timeout)`, thread khác có thể yêu cầu nó trở về:

~~~java
// Thread quản lý cập nhật tasks/interests:
taskQueue.add(task);
selector.wakeup();
~~~

Event loop sau khi thức dậy cần kiểm tra task queue, thay đổi registrations/interests an toàn và tiếp tục làm việc.

**Quy tắc ít được chú ý:**

- Nếu selection đang chờ, `wakeup()` khiến nó có thể trở về nhanh.
- Nếu chưa có selection đang chờ, hiệu ứng wakeup được giữ cho **lần selection tiếp theo**; lần đó có thể trở về ngay.
- **`selectNow()` tiêu thụ/xóa một wakeup đang chờ**.
- Gọi `wakeup()` nhiều lần trước khi có selection mới **không tích lũy thành nhiều token wakeup**.
- Lần select bị đánh thức **vẫn có thể trả số dương** nếu có key ready, nên không đồng nghĩa return value chắc chắn 0.

Sơ đồ:

~~~text
Thread A (event loop)                     Thread B (worker)
----------------------                    -----------------
selector.select()  [đang chờ]
                                          queue.add(task)
                                          selector.wakeup()
select() trở về
drain task queue
xử lý selected keys
tiếp tục event loop
~~~

### `Thread.interrupt()`

Ngắt thread đang blocked trong selection cũng là lý do làm lượt chọn trở về; việc ngắt thread có thể làm trạng thái interrupt được đặt và còn cần quy tắc dừng thích hợp.

**Đừng xử lý `select() == 0` bằng cách spin vô hạn**. Kiểm tra cờ `running`, trạng thái interrupt, queue công việc và xem selector có đang bị đóng không.

### `close()` và hủy key

`selector.close()` giải phóng tài nguyên selector; các thao tác tiếp theo trên selector đã đóng có thể ném `ClosedSelectorException`. `SelectionKey.cancel()` đánh dấu đăng ký cần hủy; việc tách khỏi selector có thể được hoàn tất trong selection tiếp theo. Khi đóng socket, cần hủy/giải phóng resource và dọn per-connection state.

Không nên đồng thời duyệt `selectedKeys()` trên nhiều thread không có đồng bộ. Selected-key set **không thread-safe**; một event loop nên có owner rõ ràng, các thread khác gửi yêu cầu qua queue rồi gọi `wakeup()`.

## 10. Những lỗi thường gặp với `OP_WRITE` và busy loop

Một `SocketChannel` thường có thể ghi được ngay trong điều kiện bình thường vì OS socket-send buffer còn chỗ. Nếu luôn đăng ký:

~~~java
// Minh họa trường hợp thường không nên làm:
socket.register(selector, SelectionKey.OP_WRITE);
~~~

selector có thể trả về rất thường xuyên ngay cả khi ứng dụng **không có dữ liệu outbound**. Khi đó event loop cứ thức dậy rồi chẳng làm gì, gây CPU cao.

**Chính sách phổ biến cho ứng dụng thực tế:**

1. Khi outbound queue rỗng, **không** giữ `OP_WRITE` trong interest set.
2. Khi có dữ liệu cần gửi, thử write ngay (nếu thiết kế cho phép).
3. Nếu write chỉ gửi một phần, giữ nguyên `ByteBuffer.position()` và bật `OP_WRITE` để đợi socket ghi được.
4. Sau khi write hết queue, tắt `OP_WRITE` để tránh readiness liên tục.

Ví dụ:

~~~java
// Mã minh họa, key là SelectionKey còn hợp lệ.
int ops = key.interestOps();
if (hasPendingOutput) {
    key.interestOps(ops | SelectionKey.OP_WRITE);
} else {
    key.interestOps(ops & ~SelectionKey.OP_WRITE);
}
~~~

`hasPendingOutput` là biến ứng dụng định nghĩa. Không cập nhật `interestOps()` khi key đã bị hủy; có thể gặp `CancelledKeyException`. Nếu thread khác đổi interest trong lúc selector đang chờ, cần sử dụng cơ chế phối hợp với event loop và `wakeup()` để thay đổi có hiệu lực đúng lúc.

## 11. Đọc/ghi non-blocking: ready không đồng nghĩa đã đủ dữ liệu

Với `SocketChannel` non-blocking:

~~~java
// Mã minh họa: socket đã được đăng ký OP_READ và buffer đã chuẩn bị.
int n = socket.read(buffer);
if (n > 0) {
    // Có n byte mới. Frame có thể vẫn chưa đầy đủ.
} else if (n == 0) {
    // Chưa nhận thêm byte trong lượt này; không spin liên tục.
} else { // n == -1
    // End-of-stream: remote peer đã đóng đầu gửi của luồng byte.
    key.cancel();
    socket.close();
}
~~~

Với `OP_ACCEPT`, `server.accept()` trên `ServerSocketChannel` non-blocking **có thể trả `null`**; cần xử lý và không cố thao tác trên channel `null`.

Với `OP_CONNECT`, khi key connectable cần gọi `socket.finishConnect()` theo đúng contract, sau đó cập nhật interest như `OP_READ` hoặc `OP_WRITE`. Không giả định socket đã hoàn thành kết nối chỉ vì `key.isConnectable()` trả true.

Trong ứng dụng truyền frame có length prefix, parser phải tích lũy đủ byte header/body qua **nhiều lượt selection**. `select()` chỉ báo readiness, không nói “một frame hoàn chỉnh đã có”.

## 12. Timeout của selector khác timeout nghiệp vụ

`select(500)` là thời gian chờ cho **một lượt selection**. Nó không tự động tạo các timeout sau:

- **Timeout kết nối:** giới hạn thời gian hoàn tất TCP connect.
- **Timeout đọc đủ một frame:** giới hạn thời gian nhận cả header và payload.
- **Idle timeout:** đóng kết nối nếu không nhận hoạt động trong một khoảng.
- **Request deadline:** hết hạn toàn bộ request gồm cả parse/compute/write.
- **Shutdown deadline:** kết thúc event loop có trật tự.

Mỗi loại cần lưu **deadline** và kiểm tra theo thời gian monotonic như `System.nanoTime()`; đồng thời lựa chọn khoảng chờ của selector bằng khoảng thời gian tới deadline gần nhất.

Ví dụ tính toán *trong ngữ cảnh đã có deadline*:

~~~java
long now = System.nanoTime();
long remainingNanos = deadlineNanos - now;

if (remainingNanos <= 0) {
    expireRequests();
} else {
    long timeoutMs =
            Math.max(1, java.util.concurrent.TimeUnit.NANOSECONDS
                    .toMillis(remainingNanos));
    selector.select(timeoutMs);
}
~~~

Đây là mã minh họa, `deadlineNanos` và `expireRequests()` là thành phần do ứng dụng cung cấp.

**Vì sao `Math.max(1, ...)`?** Nếu còn dương nhưng dưới 1 millisecond, phép chuyển sang milliseconds có thể làm tròn về `0`, và `select(0)` **sẽ chờ vô hạn** thay vì chờ rất ngắn. Cách ép tối thiểu 1 ms tránh bẫy đó, nhưng có thể trễ deadline đôi chút. Nếu độ chính xác cực cao là cần thiết, phải thiết kế scheduler/clock phù hợp thay vì coi `select(timeout)` là hard real-time timer.

### Tránh quên task khi wakeup sớm

Khi thread khác thêm task vào queue và gọi `wakeup()`, event loop cần **xử lý queue sau select**. Không suy ra `select() == 0` chỉ do timer; nguyên nhân có thể là wakeup hoặc interrupt.

## 13. Lỗi, ngoại lệ và trường hợp biên

| Tình huống | Lỗi/hành vi cần dự kiến |
|---|---|
| `select(-5)` | `IllegalArgumentException` |
| `select(0)` | Chờ vô thời hạn, **không phải** poll |
| `selectNow()` | Không chờ, có thể `0`; tiêu thụ wakeup pending |
| `select()` sau `wakeup()` | Trở về ngay, kết quả có thể 0 hoặc dương |
| `selector.close()` rồi select | `ClosedSelectorException` |
| I/O lỗi khi thực hiện selection | `IOException` |
| `key.interestOps()` trên key không còn hợp lệ | `CancelledKeyException` |
| Đăng ký channel ở blocking mode | `IllegalBlockingModeException` |
| Đăng ký operations không hợp lệ với channel | `IllegalArgumentException` |
| Duyệt và thêm trực tiếp vào `selectedKeys()` | Không cho phép thêm key trực tiếp; có thể `UnsupportedOperationException` |
| Dùng nhiều thread sửa/duyệt selectedKeys không đồng bộ | Race và sai kết quả; selected-key set không thread-safe |
| Không remove key đã xử lý | Ready bits/tập selected có thể giữ trạng thái cũ giữa các lần select |
| Non-blocking `read()` trả 0 | Không có tiến triển trong lượt này; đợi readiness phù hợp |
| Non-blocking `read()` trả -1 | End-of-stream, cần xử lý đóng hoặc half-close theo protocol |

**Không giải quyết lỗi bằng cách gọi lặp `selectNow()` vô hạn.** Một event loop tốt phải xử lý lifecycle, backpressure, task queue và thao tác I/O partial.

## 14. Pattern event loop tương đối an toàn

Phần dưới là **khung minh họa**, không phải một server hoàn chỉnh. `processTasks()`, `acceptConnections()`, `readFromConnection()` và `flushPendingOutput()` phải do ứng dụng định nghĩa, kèm xử lý lỗi/đóng socket/đăng ký key.

~~~java
while (running) {
    // Chọn timeout dương theo deadline gần nhất, hoặc dùng select().
    selector.select(250);

    processTasks(); // Xử lý các yêu cầu đã gửi vào queue từ thread khác.

    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();

        if (!key.isValid()) {
            continue;
        }

        try {
            if (key.isAcceptable()) {
                acceptConnections(key);
            }
            if (key.isConnectable()) {
                finishConnecting(key);
            }
            if (key.isReadable()) {
                readFromConnection(key);
            }
            if (key.isWritable()) {
                flushPendingOutput(key);
            }
        } catch (IOException e) {
            closeConnection(key);
        }
    }

    expireDeadlines();
}
~~~

Đặc điểm của khung:

- Duyệt selected keys và remove mỗi key một lần.
- Kiểm tra valid trước khi dùng operations.
- Không giả định chỉ có một readiness bit: cùng key có thể có cả READ và WRITE.
- Không dùng `else if` cho mọi trường hợp nếu cần xử lý nhiều trạng thái readiness trong cùng vòng; tuy nhiên việc một nhánh hủy key có thể đòi hỏi kiểm tra valid lại trước nhánh sau.
- Dùng `selector.wakeup()` khi có tác vụ ngoài luồng cần event loop xử lý ngay.
- Đặt cơ chế đóng channel, cancellation, timeout và backpressure rõ ràng.

Với ứng dụng nhỏ chỉ có một luồng và không có timer, `select()` có thể là lựa chọn đơn giản nhất. Với server có timeout nghiệp vụ, `select(timeout)` thường phù hợp hơn. `selectNow()` chỉ nên dùng khi thật sự cần non-blocking polling.

## 15. Bảng lỗi tư duy và cách sửa

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`select(0)` giống `selectNow()`” | `select(0)` **chờ vô thời hạn**; `selectNow()` không chờ. |
| “`select(100)` luôn chờ đúng 100 ms” | Có thể trả sớm do readiness/wakeup/interrupt; timer không hard real-time. |
| “Giá trị trả về là số byte đọc được” | Đó là số key có ready-operation set được cập nhật, không phải bytes. |
| “`select() == 0` chắc chắn không có việc gì” | Có thể do wakeup/interrupt, queue task hoặc key cũ chưa consume. |
| “`selectedKeys()` tự clear khi gọi `select()` lần mới” | Không; ứng dụng phải remove các selected keys đã xử lý. |
| “`isReadable()` nghĩa là đủ nguyên một message” | Chỉ readiness; phải đọc/parse dữ liệu thực tế, xử lý partial. |
| “FileChannel có thể register với Selector” | FileChannel không phải SelectableChannel. |
| “Chỉ cần `register`, không cần non-blocking” | Channel phải `configureBlocking(false)` trước khi đăng ký. |
| “`selectNow()` luôn tiết kiệm CPU vì không chờ” | Poll dày đặc có thể tạo busy-spin. |
| “Luôn bật OP_WRITE cho mọi socket” | Thường khiến selector wake liên tục; bật khi thực sự có pending write. |
| “`wakeup()` luôn khiến select trả 0” | Nếu có readiness, select vẫn có thể trả số dương. |
| “`wakeup()` là một hàng đợi token tích lũy” | Nhiều lần wakeup trước một selection thường chỉ tương đương một lần. |
| “Timeout selector chính là timeout request” | Cần deadline riêng cho request/protocol, không chỉ chờ I/O. |

## 16. Tự kiểm tra

1. Có `OP_READ` đăng ký nhưng chưa có byte; chọn API nào để trở về ngay? **`selectNow()`**.
2. Gọi `select(0)` thì tối đa chờ bao lâu? **Không giới hạn theo timeout**, tới khi có readiness/wakeup/interrupt hoặc vòng đời khác.
3. Gọi `select(200)` và sau 30 ms có data. Có bắt buộc chờ đủ 200 ms? **Không.** Có thể trở về khi có readiness.
4. `select(200)` trả 0. Có chắc reader không còn dữ liệu có thể xử lý? **Không nên suy luận như vậy**; kiểm tra selected keys, task queue và trạng thái hiện tại.
5. Vì sao phải `iterator.remove()` trong vòng xử lý selected keys? **Tránh giữ key cũ trong selected set cho lượt chọn kế tiếp**.
6. Một socket luôn được đánh dấu writable dù không có byte để gửi; điều chỉnh gì? **Tắt interest `OP_WRITE` khi outbound queue rỗng**.
7. Cần đánh thức một thread đang blocked trong `select()` khi worker thread thêm task. Dùng gì? **`selector.wakeup()`**.
8. `selectNow()` có tác động gì tới `wakeup()` được gọi trước đó? **Nó xóa tác dụng wakeup đang chờ**.
9. Đã `select()` và `key.isReadable()==true`. `read()` có chắc trả đủ nguyên frame không? **Không**.
10. `select(-1)` có hợp lệ không? **Không, `IllegalArgumentException`**.
11. Có thể dùng `FileChannel` với Selector không? **Không**, nó không phải `SelectableChannel`.
12. Có deadline còn 500 microsecond; truyền `select(TimeUnit.NANOSECONDS.toMillis(500_000))` có đúng không? **Không**, nó thành `select(0)` và chờ vô hạn. Phải xử lý thời gian dưới 1 ms cẩn thận.

## 17. Tài liệu chính thức

- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select()`, `selectNow()`, `select(long)`, `selectedKeys()`, `wakeup()`, cách cập nhật ready-operation set và caveat timeout.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, `readyOps`, `isReadable`, `isWritable`, key cancellation.
- [Java SE 17 — SelectableChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): `configureBlocking(false)`, `register`, `validOps`.
- [Java SE 17 — Pipe](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Pipe.html): source/sink channel dùng trong ví dụ có thể chạy không cần server mạng.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): partial read/write, non-blocking, `finishConnect()`.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): đăng ký `OP_ACCEPT`, `accept()` trên non-blocking server.
