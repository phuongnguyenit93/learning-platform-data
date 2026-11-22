# Selector callback: Khác biệt với duyệt selected-key set (Java 11+)

## Mục tiêu

Một `Selector` cho phép một luồng theo dõi nhiều `SelectableChannel` ở chế độ non-blocking. Khi một channel sẵn sàng cho I/O, Java có **hai cách chính** để ứng dụng nhận và xử lý `SelectionKey`:

1. Gọi `selector.select()` hoặc `selectNow()`, sau đó lấy `selector.selectedKeys()` và tự duyệt, xóa các key đã xử lý.
2. Từ **Java 11**, gọi `selector.select(Consumer<SelectionKey>)` hoặc các overload tương ứng, để selector chuyển key đã sẵn sàng thẳng cho callback.

Đây là **hai phong cách xử lý được hỗ trợ trong Java hiện đại**; cách duyệt selected-key set không bị loại bỏ. Điểm cần hiểu không chỉ là viết ít dòng hơn: **sự khác nhau nằm ở vòng đời selected-key set, trạng thái ready operations, quản lý khóa đồng bộ, và cách xử lý từng sự kiện**.

Sau bài này, bạn có thể tự chọn kiểu API phù hợp, giải thích chính xác kết quả của `select(...)` và tránh các lỗi lặp sự kiện, bỏ quên `iterator.remove()`, callback quá lâu hoặc gọi `select` đệ quy.

**Phiên bản:** các overload nhận callback được bổ sung trong **Java 11** và vẫn được hỗ trợ ở JDK mới. Mã hoàn chỉnh bên dưới được kiểm tra biên dịch với `--release 11`.

## 1. Nền tảng chung: `Selector` và ba tập key

`java.nio.channels.Selector` được tạo bằng `Selector.open()`. Một channel hỗ trợ selection phải chuyển sang **non-blocking mode** trước khi đăng ký, ví dụ:

```java
source.configureBlocking(false);
SelectionKey key = source.register(selector, SelectionKey.OP_READ);
```

Đây là đoạn minh họa: `source` phải là một `SelectableChannel` phù hợp, `selector` đã mở và các thao tác I/O cần được xử lý ngoại lệ `IOException`. Khi đăng ký, selector quản lý các tập key khác nhau:

| Tập | Ý nghĩa | Truy cập/quản lý |
| --- | --- | --- |
| **Key set** | Mọi channel hiện đang đăng ký với selector | `selector.keys()`; ứng dụng không tự thêm/xóa trực tiếp |
| **Selected-key set** | Các key có readiness đã được ghi nhận bởi những lần selection kiểu tập hợp | `selector.selectedKeys()`; ứng dụng được **xóa** key, không được thêm key trực tiếp |
| **Cancelled-key set** | Các key đã bị hủy nhưng chờ selector hủy đăng ký hoàn tất | Không truy cập trực tiếp; được xử lý trong selection |

Lưu ý: `selector.keys()` **không** đồng nghĩa `selector.selectedKeys()`. Tập thứ nhất chứa các đăng ký, kể cả chưa có I/O sẵn sàng. Tập thứ hai liên quan các kết quả selection theo kiểu cũ.

Mỗi `SelectionKey` còn lưu hai nhóm phép toán:

- **Interest set** qua `interestOps()`: ứng dụng muốn nhận biết loại I/O nào (ví dụ `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE`).
- **Ready set** qua `readyOps()` hoặc `isReadable()/isWritable()/isAcceptable()/isConnectable()`: những loại I/O vừa được selector báo là sẵn sàng.

Sẵn sàng **không có nghĩa** một thao tác `read/write` chắc chắn hoàn tất mọi byte. Với non-blocking I/O, vẫn phải xử lý `read() == 0`, `read() == -1`, ghi một phần và trạng thái kết nối theo đúng loại channel.

## 2. Cách 1: `select()` rồi duyệt `selectedKeys()`

Dạng phổ biến:

```java
int selected = selector.select();

Iterator<SelectionKey> iterator =
        selector.selectedKeys().iterator();

while (iterator.hasNext()) {
    SelectionKey key = iterator.next();
    iterator.remove(); // Xóa khỏi selected-key set sau khi lấy key.

    if (!key.isValid()) {
        continue;
    }
    if (key.isReadable()) {
        // Đọc dữ liệu non-blocking từ channel.
    }
}
```

**Đây là đoạn minh họa**, cần import `java.nio.channels.*` và `java.util.Iterator`, phải có `selector` hợp lệ cùng phần xử lý I/O thích hợp. `select()` đợi đến khi có sự kiện, bị `wakeup()` đánh thức, thread bị interrupt hoặc các điều kiện trả về khác theo hợp đồng API.

Cơ chế của nhóm `select()`, `select(long)` và `selectNow()`:

1. Selector xử lý các key bị hủy đang chờ.
2. Hệ điều hành được hỏi về readiness của các channel còn đăng ký.
3. Key mới sẵn sàng được **thêm vào selected-key set**; key đã có trong tập được **cập nhật** tập ready operations.
4. Hàm trả về; ứng dụng duyệt tập và **chủ động loại key đã xử lý** bằng `iterator.remove()` hoặc `selectedKeys().remove(key)`.

Với key đã nằm trong selected-key set, ready-operation set có thể **tích lũy** readiness mới theo phép OR thay vì bị xóa sạch qua mỗi lần selection. Nếu không bỏ key khỏi tập, ứng dụng có thể nhìn thấy thông tin cũ hoặc xử lý nhầm như một sự kiện mới.

**Quan trọng:** giá trị trả về của `select()` không nhất thiết bằng `selector.selectedKeys().size()`. Selected-key set có thể chứa key từ vòng trước chưa bị xóa; giá trị trả về phản ánh số key được thêm hoặc có ready set cập nhật theo đặc tả phiên bản JDK. Đừng dùng kích thước tập làm số event mới vừa xuất hiện.

### Tại sao dùng `iterator.remove()`?

Nếu bạn đã có iterator, `iterator.remove()` xóa key vừa đọc khỏi selected-key set an toàn theo hợp đồng iterator. Chỉ gọi `selectedKeys().clear()` nếu **chủ đích bỏ toàn bộ các key** (kể cả key chưa được xử lý); không clear ở đầu hoặc cuối một cách mù quáng.

Mẫu `Iterator.remove()` vẫn **hợp lệ và được hỗ trợ**, không phải một kỹ thuật bị deprecated. Nó phù hợp khi bạn muốn ứng dụng tự kiểm soát lịch duyệt, phân nhóm sự kiện hoặc hoãn xử lý một số key.

## 3. Cách 2: `select(Consumer<SelectionKey>)` — callback (Java 11+)

Từ Java 11:

```java
int consumed = selector.select(key -> {
    if (!key.isValid()) {
        return;
    }
    if (key.isReadable()) {
        // Xử lý key sẵn sàng cho đọc.
    }
});
```

Đoạn trên minh họa nằm trong phương thức có xử lý `IOException`, với `selector` đã mở. Lambda là một `Consumer<SelectionKey>`: selector gọi `accept(key)` cho các channel có readiness phù hợp interest set.

Các overload được hỗ trợ:

| API | Cách chờ | Ý nghĩa |
| --- | --- | --- |
| `select(Consumer<SelectionKey> action)` | Có thể block đến khi có ready key hoặc bị đánh thức/gián đoạn | Gọi callback trong selection |
| `select(Consumer<SelectionKey> action, long timeout)` | Có thể block tối đa xấp xỉ `timeout` millisecond nếu timeout dương | Callback + thời hạn chờ |
| `selectNow(Consumer<SelectionKey> action)` | Không block chờ I/O | Callback cho readiness hiện có |

Lưu ý `timeout == 0` với overload `select(action, timeout)` có nghĩa **chờ vô hạn**, không có nghĩa “không chờ”. Dùng `selectNow(action)` nếu muốn polling ngay. Timeout âm là không hợp lệ.

Khác biệt cốt lõi:

- Các overload **callback** thực hiện action trên key được chọn, **không thêm key mới vào selected-key set** theo ngữ nghĩa API.
- Ứng dụng không phải tạo iterator và gọi `iterator.remove()` cho **các key được callback xử lý**.
- Trước mỗi lần callback, ready-operation set được thiết lập theo kết quả của selection hiện tại; nó không được dùng như lịch sử tích lũy readiness của key đã còn trong selected-key set.
- **Một key có thể khiến callback được gọi nhiều lần trong cùng một selection** nếu sẵn sàng cho nhiều loại operation. Mỗi lần callback có thể nhận một **tập con** của ready operations. Không mặc định “đúng một lời gọi trên mỗi key”.
- Giá trị `consumed` là **số key riêng biệt được tiêu thụ** theo hợp đồng API, không nhất thiết là số lần `action.accept(...)` được gọi.

### Cảnh báo quan trọng về selected-key set

Không nên suy luận rằng “sau khi dùng callback, `selector.selectedKeys()` luôn rỗng”. Đặc tả cho biết các overload callback **không thêm** key vào tập, nhưng trong **triển khai mặc định** của lớp `Selector`, phương thức có thể dọn selected-key set, gọi một selection dạng truyền thống rồi chạy callback; **tập này có thể rỗng hoặc không rỗng khi phương thức hoàn tất**.

Ngoài ra, nếu code đã sử dụng cách duyệt tập trước đó mà chưa xóa hết key, trạng thái cũ có thể vẫn có ý nghĩa. Vì vậy:

1. **Không dùng việc `selectedKeys().isEmpty()` làm điều kiện đúng/sai cho callback API.**
2. **Đừng dựa vào việc callback tự động dọn sạch mọi selected-key set cũ trên mọi Selector provider.**
3. Khi chuyển đổi giữa hai kiểu trong cùng event loop, bảo đảm logic quản lý selected-key set được thiết kế rõ ràng và hiểu đặc tính triển khai đang sử dụng.

Điểm này phân biệt **hợp đồng API** với chi tiết triển khai; nó giúp bài học vẫn chính xác trên Java 11 và các JDK mới.

## 4. Ví dụ chạy được: cùng một `Pipe`, hai kiểu xử lý

Một `Pipe` nội bộ giúp tạo một kênh nguồn có thể đăng ký `OP_READ` mà **không cần mở cổng mạng hoặc phụ thuộc máy chủ bên ngoài**. Chương trình viết byte `A`, duyệt selected-key set để đọc; sau đó viết `B`, dùng callback để đọc.

**Tệp: `SelectorCallbackVsSet.java`** — Java 11+

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.util.Iterator;

public class SelectorCallbackVsSet {
    private static void writeByte(Pipe.SinkChannel sink, byte value)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(new byte[] { value });
        while (buffer.hasRemaining()) {
            sink.write(buffer);
        }
    }

    private static void readReadyKey(SelectionKey key, String label) {
        if (!key.isValid() || !key.isReadable()) {
            return;
        }

        ByteBuffer buffer = ByteBuffer.allocate(1);
        try {
            int count = ((Pipe.SourceChannel) key.channel()).read(buffer);
            if (count == 1) {
                buffer.flip();
                System.out.println(
                        label + ": " + (char) (buffer.get() & 0xff));
            }
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            // Cách 1: truyền thống — tự duyệt selected-key set.
            writeByte(sink, (byte) 'A');

            selector.select();
            Iterator<SelectionKey> iterator =
                    selector.selectedKeys().iterator();

            while (iterator.hasNext()) {
                SelectionKey key = iterator.next();
                iterator.remove();
                readReadyKey(key, "set");
            }

            // Cách 2: Java 11+ — selector gọi callback.
            writeByte(sink, (byte) 'B');

            selector.select(
                    key -> readReadyKey(key, "callback"));
        }
    }
}
```

Chạy trong thư mục chứa mã nguồn:

```bash
javac -encoding UTF-8 SelectorCallbackVsSet.java
java SelectorCallbackVsSet
```

Trên JDK 11+ cũng có thể chạy trực tiếp:

```bash
java SelectorCallbackVsSet.java
```

Nếu đang sử dụng JDK mới hơn mà muốn **biên dịch theo API Java 11**:

```bash
javac --release 11 -encoding UTF-8 SelectorCallbackVsSet.java
java SelectorCallbackVsSet
```

**Stdout mong đợi và đã được kiểm tra thực tế:**

```text
set: A
callback: B
```

Ví dụ biên dịch thành công bằng `javac --release 11` và chạy ra đúng hai dòng trên.

### Những điểm chính trong ví dụ

1. `Pipe.SourceChannel` được đặt thành non-blocking trước `register(selector, OP_READ)`. `Pipe.SinkChannel` được dùng để gửi một byte, làm source trở nên sẵn sàng đọc.
2. Ở lượt đầu, `selector.select()` cập nhật selected-key set. Sau đó `Iterator` lấy key, `iterator.remove()` **xóa key khỏi tập**, rồi handler đọc byte `A`.
3. Ở lượt hai, `selector.select(key -> ...)` chuyển key thẳng vào handler, **không có bước duyệt selected-key set trong ứng dụng**. Handler đọc byte `B`.
4. Cả hai con đường cuối cùng vẫn phải xử lý cùng loại `SelectionKey`; callback **không tự đọc dữ liệu** và không thay thế code I/O thật.
5. `readReadyKey(...)` kiểm tra `isValid()`/`isReadable()`, vì trạng thái key có thể thay đổi. Trong ví dụ này, hàm đọc một byte mỗi lần để giữ kết quả minh họa ngắn.
6. Nếu xảy ra `IOException` trong handler gọi từ lambda, code bọc bằng `UncheckedIOException` vì `Consumer.accept` không khai báo checked exceptions. Ở ứng dụng thật, hãy bắt ở ranh giới event loop và quyết định đóng channel/cancel key/báo lỗi thích hợp.
7. `try-with-resources` đóng selector và cả hai đầu Pipe. Mỗi channel được đăng ký với selector nên cần giải phóng tài nguyên khi kết thúc.

**Lưu ý vận hành:** hai lệnh `select()` trong ví dụ **có thể block**; chúng được thực hiện sau khi đã ghi dữ liệu vào Pipe để demo chủ động tạo readiness. Trong hệ thống thật, cần chiến lược timeout, `wakeup()`, dừng vòng lặp và đóng tài nguyên thích hợp, không giả định một lần select luôn trả về đúng một key.

## 5. Bảng so sánh hai cách

| Tiêu chí | `select()` + `selectedKeys()` | `select(action)` |
| --- | --- | --- |
| Có từ phiên bản nào? | API gốc của NIO, vẫn được hỗ trợ | **Java 11** trở lên |
| Ai duyệt key? | **Ứng dụng** duyệt tập bằng iterator/for | **Selector** gọi `Consumer.accept(key)` |
| Key mới được thêm vào selected-key set? | **Có** theo điều kiện readiness | **Không** theo ngữ nghĩa API |
| Ai quản lý việc xóa key đã xử lý khỏi selected-key set? | **Ứng dụng**, thường `iterator.remove()` | Callback path không yêu cầu ứng dụng tự loại key vừa được callback |
| Ready operations khi key vẫn ở trong tập? | Có thể được cập nhật bằng cách **OR** readiness mới với cũ | Được thiết lập theo readiness hiện tại; callback có thể được gọi nhiều lần với các tập con |
| Giá trị trả về | Số key được thêm/cập nhật readiness theo đặc tả | Số **key riêng biệt** đã được xử lý qua callback |
| Điều khiển thứ tự và vòng lặp | Ứng dụng tự duyệt và có thể quản lý từng key rõ ràng | Callback do selection gọi; không bảo đảm thứ tự key |
| Khóa đồng bộ | Việc selection dùng lock selector và selected-key set | **Callback được thực thi trong khi các lock này còn được giữ** |
| Trường hợp phù hợp | Code cần giữ/control tập sự kiện, framework có event loop kiểu iterator | Code muốn nhận từng ready key qua callback và không quản lý iterator trực tiếp |

Bảng nói về **hợp đồng API**, không cam kết một kiểu luôn nhanh hơn, và không loại trừ tình huống selected-key set còn dữ liệu sau callback do chi tiết triển khai hoặc xử lý trước đó.

## 6. Callback được gọi trong bối cảnh đồng bộ nào?

Javadoc của `Selector.select(Consumer, long)` nêu rõ `action.accept(key)` được gọi khi đang đồng bộ trên **selector** và **selected-key set**. Điều này khác với kiểu truyền thống: sau khi `select()` trả về, ứng dụng duyệt tập bên ngoài thân lời gọi selection.

Hệ quả cho thiết kế event loop:

- Callback nên **ngắn, dễ kiểm soát và không block lâu**. Nếu nó chờ I/O blocking, lock ngoại vi, truy vấn cơ sở dữ liệu hoặc xử lý CPU kéo dài, nó có thể giữ khóa selection quá lâu và gây nghẽn các thao tác liên quan.
- Tránh gọi lại `selector.select(...)`, `selectNow(...)` hoặc thao tác selection khác **trên chính selector đó từ trong callback**. Selection không được bảo đảm reentrant; cách hành xử khi tái nhập là phụ thuộc triển khai và có thể dẫn đến lỗi hoặc deadlock.
- Không mặc định có thể xử lý an toàn selected-key set từ thread khác: tập này **không thread-safe**. Nếu nhiều thread có thể truy cập và sửa tập, cần đồng bộ đúng cách.
- `key.cancel()`, thay đổi `interestOps(...)` hoặc đóng channel có thể là hành động hợp lệ khi xử lý readiness; nhưng phải hiểu rằng key có thể không còn valid. Nếu có luồng khác cancel key giữa selection và callback, đặc tả cho phép callback được gọi với một key đã invalid tùy triển khai.
- Nếu `action.accept(...)` ném exception, exception được **chuyển cho bên gọi selection**; không có bảo đảm các key khác đã được callback xử lý hết trong lượt đó. Cần chiến lược error handling ở vòng ngoài.

Một mẫu handler hợp lý là kiểm tra readiness, thực hiện thao tác non-blocking với giới hạn công việc, cập nhật trạng thái kết nối rồi trả quyền điều khiển sớm. Việc xử lý CPU nặng hoặc công việc blocking có thể được chuyển sang hàng đợi/worker chuyên biệt, với kế hoạch đồng bộ rõ ràng.

### Tránh điều kiện “một key = một callback”

Theo đặc tả, nếu một channel sẵn sàng cho nhiều operation, callback có thể được gọi **nhiều lần với cùng một key**, mỗi lần có subset ready operations khác nhau. Bởi vậy, code sau đây là một giả định sai về hợp đồng chung:

```java
// Không được giả định rằng mỗi key chỉ vào callback một lần.
// Không được lấy số lần callback làm số key unique.
AtomicInteger callbackCount = new AtomicInteger();
selector.select(key -> callbackCount.incrementAndGet());
```

Đây chỉ là đoạn minh họa cần `AtomicInteger`, `selector` hợp lệ và xử lý `IOException`. Số lần `accept(...)` có thể khác số nguyên trả về bởi `select(action)` (số **unique keys consumed**). Nếu cần thống kê đúng theo mỗi key, hãy thiết kế cách đếm phù hợp; đừng dựa vào số callback mặc định.

## 7. Điều kiện readiness và cách xử lý non-blocking an toàn

Hai API chỉ khác **cách giao key**; các nguyên tắc I/O sau vẫn giống nhau:

- `OP_ACCEPT` trên `ServerSocketChannel`: cần `accept()` theo non-blocking và đăng ký các socket mới với interest ops phù hợp.
- `OP_CONNECT` trên `SocketChannel`: thường cần `finishConnect()` để hoàn tất kết nối.
- `OP_READ`: `read(...)` có thể trả `0` khi chưa có thêm dữ liệu, số dương khi có dữ liệu, hoặc `-1` khi đầu bên kia đã đóng luồng đọc theo hợp đồng channel.
- `OP_WRITE`: việc channel thường xuyên writable **không đồng nghĩa nên luôn đăng ký OP_WRITE**. Hãy điều chỉnh interest set để tránh vòng lặp thức dậy liên tục khi không có dữ liệu đang chờ gửi; xử lý ghi một phần và hàng đợi đầu ra.

Ví dụ bên dưới chỉ minh họa **đăng ký và hủy quan tâm tới ghi**, không phải chương trình độc lập:

```java
// Giả sử key đã được đăng ký trên một SocketChannel hợp lệ.
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
// Khi không còn dữ liệu chờ ghi:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Không thể thêm operation mà loại channel không hỗ trợ. `interestOps(...)` có thể ném exception nếu key đã bị hủy hoặc bit operation không hợp lệ. Những thay đổi interest set trong khi một selection đang chạy sẽ được xét ở **lượt selection tiếp theo** theo đặc tả.

Trên cả hai đường, luôn kiểm tra `key.isValid()` trước khi đọc ready/interest operations nếu có nguy cơ cancel, và đóng channel/hủy đăng ký khi lỗi không thể khôi phục.

## 8. Khi nào chọn kiểu nào?

### Ưu tiên duyệt selected-key set nếu

- Framework đã có event loop sử dụng `selectedKeys()` và logic xóa key nhất quán.
- Bạn muốn ứng dụng tự điều khiển iterator, chia nhóm sẵn sàng và phân phối sự kiện theo cấu trúc nội bộ.
- Bạn cần tương tác trực tiếp với tập event được tích lũy, hiểu rõ trạng thái và chủ động xóa key khi xử lý xong.

Cách này **không lỗi thời**. Tuy nhiên, với nhiều key và đường xử lý phức tạp, việc quên xóa key hoặc nhầm `selectedKeys()` với toàn bộ key đăng ký là rủi ro thường gặp.

### Ưu tiên callback nếu

- Mục tiêu chỉ là “có key sẵn sàng thì gọi handler”.
- Bạn không cần duyệt hay lưu danh sách key sẵn sàng riêng.
- Bạn muốn tránh boilerplate `iterator/iterator.remove()` cho các key được chọn.

Nhưng callback **không phải hàng đợi job song song**: việc gọi action vẫn thuộc selection operation, được đồng bộ theo các lock đã nêu và có thể ảnh hưởng tiến độ xử lý nếu callback nặng. Cũng không có bảo đảm callback nhanh hơn về hiệu năng hoặc luôn được gọi đúng một lần trên mỗi key.

### Trộn hai kiểu trong cùng selector: được, nhưng có chủ đích

Nếu bạn đã gọi `select()` và còn key trong `selectedKeys()` chưa xử lý, rồi chuyển sang callback, không nên kỳ vọng callback tự giải quyết toàn bộ trạng thái cũ. Ngược lại, sau callback cũng không được dùng `selectedKeys().size()` như phép đếm số key mà callback vừa xử lý.

Đề xuất cho event loop: **chọn một phong cách nhất quán** cho đường xử lý chính. Nếu phải chuyển đổi, hãy xác định rõ quyền sở hữu selected-key set, xử lý/hủy các key còn lại và thử nghiệm hành vi trên provider/JDK triển khai thực tế.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Duyệt selected-key set bằng iterator nhưng không `remove()` | Key vẫn còn trong tập; readiness có thể tích lũy, xử lý lại sai | Xóa key đã xử lý, thường `iterator.remove()` |
| Dùng `selector.keys()` thay `selector.selectedKeys()` | Duyệt mọi đăng ký, kể cả chưa ready | Phân biệt key set và selected-key set |
| Dùng callback rồi vẫn tự duyệt `selectedKeys()` như thể là kết quả callback | Có thể xử lý trùng hoặc đọc trạng thái không liên quan | Cho callback xử lý key trực tiếp; không suy diễn từ size của tập |
| Cho rằng `selectedKeys()` luôn rỗng sau callback | Không đúng với mọi triển khai mặc định/trạng thái trước đó | Tuân theo hợp đồng callback, không phụ thuộc giá trị rỗng |
| Cho rằng một key luôn chỉ kích hoạt callback một lần | Sai nếu nhiều ready operations và callback được chia theo subset | Kiểm tra `readyOps()`/`isReadable()`… trong từng lần |
| Đếm số `accept` rồi coi bằng giá trị trả về `select(action)` | Callback có thể nhiều lần cho một key | Dùng đúng nghĩa **unique keys consumed** |
| Gọi `select()` lại trên cùng selector trong callback | Hành vi reentrant không được bảo đảm, có nguy cơ lỗi/deadlock | Trả điều khiển cho event loop, không select lồng nhau |
| Chạy truy vấn mạng blocking hoặc CPU dài trong callback | Giữ khóa selection quá lâu, gây nghẽn | Handler ngắn, non-blocking và phối hợp worker riêng khi cần |
| Quên `configureBlocking(false)` trước `register` | Có thể ném `IllegalBlockingModeException` | Chuyển channel sang non-blocking mode |
| Giả định ready cho read/write nghĩa là có thể xử lý tất cả byte ngay | Bỏ qua EOF, zero read, partial write | Theo dõi trạng thái I/O và buffer đúng cách |
| Đăng ký `OP_WRITE` liên tục không cần thiết | Event loop có thể busy-loop | Chỉ quan tâm khi có dữ liệu chờ ghi |
| Dùng `select(action, 0)` với ý “không chờ” | Có thể block vô hạn | Dùng `selectNow(action)` |
| Cho rằng selected-key set an toàn với nhiều thread | Có thể gặp race/đồng bộ sai | Dùng đồng bộ và quyền sở hữu event loop rõ ràng |

## 10. Câu hỏi và bài tập

**Bài 1 — So sánh vòng đời tập.** Điền thao tác còn thiếu:

```java
selector.select();
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    // ?
    handle(key);
}
```

Đây là mã **minh họa** với `handle(key)` tự định nghĩa. **Đáp án:** `it.remove();` để xóa key đã lấy khỏi selected-key set. Cần quyết định rõ xử lý lỗi nếu handler thất bại sau khi key bị xóa.

**Bài 2 — Chuyển sang callback.** Viết lại dạng duyệt tập với:

```java
selector.select(key -> handle(key));
```

Nếu `handle` ném checked `IOException`, không thể truyền thẳng khi `Consumer.accept` không khai báo checked exceptions. Hãy bắt/bọc lỗi theo chiến lược của ứng dụng, như ví dụ hoàn chỉnh dùng `UncheckedIOException`.

**Bài 3 — Đếm callback.** Một key có readiness cho hai operation và callback được gọi **hai lần** cho key đó trong cùng lượt. Hàm `select(action)` trả về bao nhiêu unique keys đã xử lý? **Đáp án:** 1, dù callback được gọi 2 lần.

**Bài 4 — Hiểu đúng selected-key set.** Nếu một provider dùng default callback implementation và sau `selectNow(action)`, selected-key set không rỗng, điều đó có nhất thiết vi phạm đặc tả không? **Không**: tài liệu cho biết cách triển khai mặc định có thể để tập rỗng hoặc không rỗng.

**Bài 5 — Thực hành.** Thay handler trong `SelectorCallbackVsSet` để đếm tổng số byte đọc. Thử viết lần lượt ba byte `A`, `B`, `C` rồi quyết định cách đọc đến khi `read() == 0` để không bỏ sót dữ liệu. Giữ xử lý EOF và tài nguyên theo hợp đồng I/O.

**Bài 6 — Xử lý event loop.** Nêu ba việc không nên làm trong callback: (1) gọi `select` lồng trên cùng selector, (2) thực hiện tác vụ blocking kéo dài, (3) đếm số callback như số key unique. Giải thích lý do theo đặc tả.

### Checklist áp dụng thực tế

Trước khi chọn đường callback hoặc selected-key set, hãy kiểm tra: (1) channel ở non-blocking mode chưa; (2) interest set phù hợp chưa; (3) key có valid và ready đúng operation không; (4) selected-key set được xóa đúng vòng đời chưa; (5) callback có ngắn và không gọi selection reentrant không; (6) có xử lý zero read/EOF/partial write không; (7) exception có đi tới nơi đóng/hủy channel đúng không; (8) có dựa nhầm vào thứ tự key, số lần callback hay kích thước selected-key set không.

## Tài liệu chính thức

- [Oracle Java SE 11 — Selector](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html): hai nhóm selection, selected-key set, `select(Consumer)`/`selectNow(Consumer)`, locking và mặc định triển khai.
- [Oracle Java SE 25 — Selector](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html): xác nhận API vẫn được hỗ trợ, cùng những lưu ý về callback, ready operations và default implementation.
- [Oracle Java SE 11 — SelectionKey](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, `readyOps`, các loại operation và hủy đăng ký.
- [Oracle Java SE 11 — SelectableChannel](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectableChannel.html): `configureBlocking(false)` và đăng ký với selector.
- [Oracle Java SE 11 — Pipe](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Pipe.html): ví dụ truyền byte qua SourceChannel/SinkChannel.

**Kết luận:** khi duyệt selected-key set, ứng dụng chịu trách nhiệm **đọc và xóa key đã được chọn**. Với callback Java 11+, selector giao key trực tiếp cho action, nhưng callback có quy tắc đồng bộ, đếm key và readiness riêng. Cả hai đều đúng; chọn cách phù hợp với vòng đời event loop và kiểm soát I/O của bạn.