# SelectionKey, interest set và ready set trong Java NIO Selector

## 1. Bài toán: một luồng theo dõi nhiều channel

Với Java NIO, `Selector` giúp một luồng theo dõi nhiều `SelectableChannel` thay vì phải tạo một thread chặn ở mỗi `SocketChannel.read()`. Ứng dụng đăng ký các thao tác muốn theo dõi, gọi `select()` để đợi channel sẵn sàng, rồi xử lý các key được chọn.

Ba khái niệm dễ bị lẫn:

- **`SelectionKey`:** đối tượng đại diện cho **một đăng ký** giữa một `SelectableChannel` và một `Selector`.
- **Interest set (tập quan tâm):** các thao tác ứng dụng muốn selector giám sát, biểu diễn bằng bitmask lấy từ `key.interestOps()`.
- **Ready set (tập sẵn sàng):** các thao tác mà lần chọn đã xác định là sẵn sàng đối với key, biểu diễn bằng `key.readyOps()`.

Chúng không phải là ba tên gọi cho cùng một trạng thái. Hãy nhìn luồng điều khiển:

```text
SelectableChannel (đặt non-blocking)
          │
          │ register(selector, OP_READ | OP_WRITE)
          ▼
   SelectionKey
          │
          ├── interestOps() : những gì ứng dụng MUỐN theo dõi
          ├── readyOps()    : những gì selector phát hiện SẴN SÀNG
          ├── channel()     : channel đã đăng ký
          ├── selector()    : selector chứa đăng ký
          └── attachment()  : ngữ cảnh ứng dụng, nếu có
          │
          ▼
  selector.select()
          │
          ▼
  selector.selectedKeys()
          │
          ▼
  kiểm tra key.isReadable(), isWritable(), ...
          │
          ▼
  xử lý non-blocking I/O; điều chỉnh interestOps; xóa key khỏi selectedKeys
```

**Mục tiêu bài học:** hiểu quan hệ giữa key, interest set, ready set và selected-key set; sử dụng bitmask `OP_READ`/`OP_WRITE`/`OP_CONNECT`/`OP_ACCEPT`; cập nhật interest đúng lúc; xử lý selected keys an toàn; tránh busy loop và nhầm “ready” với “I/O chắc chắn hoàn tất”.

## 2. `SelectionKey` là kết quả của việc đăng ký

API cơ bản:

```java
Selector selector = Selector.open();
SelectableChannel channel = /* channel thích hợp */;
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
```

Đoạn trên **chỉ minh họa**: `channel` phải là một loại `SelectableChannel` có hỗ trợ `OP_READ`, và caller phải đóng channel/selector khi hoàn tất. `register` trả về `SelectionKey` gắn với cặp channel–selector đó.

Các thuộc tính/phương thức chính:

| Phương thức | Ý nghĩa |
|---|---|
| `key.channel()` | Truy cập channel của đăng ký |
| `key.selector()` | Truy cập selector gắn với đăng ký |
| `key.interestOps()` | Đọc bitmask interest hiện tại |
| `key.interestOps(mask)` | Thay thế interest set bằng bitmask mới |
| `key.readyOps()` | Đọc bitmask readiness của key |
| `key.isReadable()`, `isWritable()`, `isConnectable()`, `isAcceptable()` | Tiện ích kiểm tra các bit trong ready set |
| `key.isValid()` | Key còn là đăng ký hợp lệ hay không |
| `key.cancel()` | Yêu cầu hủy đăng ký; xử lý hủy trong selection tiếp theo |
| `key.attach(obj)` / `key.attachment()` | Gắn và lấy ngữ cảnh nghiệp vụ, không làm thay đổi readiness |

`SelectionKey` là một **registration**, không đại diện cho một event đơn lẻ. Cùng một key có thể được selector chọn nhiều lần trong suốt vòng đời kết nối. Chỉ tạo một key cho một cặp channel–selector tại một thời điểm; đăng ký lại một channel với **cùng selector** khi đã có đăng ký hợp lệ sẽ cập nhật interest/attachment của đăng ký hiện có thay vì tạo key thứ hai độc lập.

### 2.1. Trước khi đăng ký phải cấu hình non-blocking

`SelectableChannel.register` yêu cầu channel ở chế độ non-blocking. Với `SocketChannel`, `ServerSocketChannel` hoặc `Pipe.SourceChannel`, gọi:

```java
channel.configureBlocking(false);
```

Nếu đăng ký một selectable channel vẫn đang blocking, `register` có thể ném `IllegalBlockingModeException`. Nếu cố chuyển một selectable channel có đăng ký còn hợp lệ quay lại blocking, `configureBlocking(true)` cũng không được phép theo contract tương ứng.

**Phân biệt:** `FileChannel` không phải `SelectableChannel`; file disk thông thường không được đăng ký trực tiếp với `Selector` theo mô hình này. `Selector` đặc biệt hữu ích cho socket và những selectable channel tương ứng.

## 3. Các bit `OP_*` và `validOps()`

Java dùng các hằng số bitmask của `SelectionKey`:

| Hằng số | Giá trị int | Thao tác được theo dõi | Channel điển hình |
|---|---:|---|---|
| `SelectionKey.OP_READ` | `1` | Có dữ liệu để đọc, EOF hoặc tình huống đọc không còn chặn theo semantics channel | `SocketChannel`, `Pipe.SourceChannel` |
| `SelectionKey.OP_WRITE` | `4` | Có thể ghi ít nhất một số byte mà không chặn | `SocketChannel`, `Pipe.SinkChannel` |
| `SelectionKey.OP_CONNECT` | `8` | Kết nối không chặn có thể hoàn tất | `SocketChannel` |
| `SelectionKey.OP_ACCEPT` | `16` | Server có thể nhận kết nối mới | `ServerSocketChannel` |

Các bit khác nhau có thể ghép bằng phép OR bit:

```java
int readAndWrite =
        SelectionKey.OP_READ | SelectionKey.OP_WRITE;

boolean wantsRead =
        (readAndWrite & SelectionKey.OP_READ) != 0;

boolean wantsAccept =
        (readAndWrite & SelectionKey.OP_ACCEPT) != 0;
```

Đây là đoạn minh họa có thể đặt trong method. Kết quả `wantsRead == true`, `wantsAccept == false`.

**Không phải mọi channel đều hỗ trợ mọi thao tác.** Kiểm tra:

```java
int supportedMask = channel.validOps();
boolean canRead =
        (supportedMask & SelectionKey.OP_READ) != 0;
```

Đoạn minh họa yêu cầu `channel` là `SelectableChannel` đã được khai báo. Ví dụ:

- `ServerSocketChannel`: thường chỉ hỗ trợ `OP_ACCEPT`.
- `SocketChannel`: hỗ trợ `OP_CONNECT`, `OP_READ`, `OP_WRITE`.
- `Pipe.SourceChannel`: hỗ trợ `OP_READ`.
- `Pipe.SinkChannel`: hỗ trợ `OP_WRITE`.

Nếu `register(selector, ops)` hoặc `key.interestOps(ops)` nhận bit không nằm trong `channel.validOps()`, API ném `IllegalArgumentException`. Đặc biệt, không đăng ký `OP_ACCEPT` trên `SocketChannel` để chờ server nhận kết nối: chỉ `ServerSocketChannel` mới có vai trò accept.

### 3.1. Interest set có thể bằng 0

`key.interestOps(0)` là thao tác hợp lệ: tạm thời không giám sát sự kiện I/O nào trên key. Nó **không xóa đăng ký** và không đóng channel.

Ứng dụng có thể dùng `interestOps(0)` để tạm dừng xử lý khi đang điều phối trạng thái; khi sẵn sàng theo dõi lại, đặt các bit mong muốn. Nếu mục đích là ngừng giám sát mãi mãi, hãy hủy key hoặc đóng channel/selector theo chính sách vòng đời.

## 4. Interest set: ứng dụng muốn selector theo dõi điều gì?

`interestOps()` là **bitmask nguyện vọng** do code ứng dụng quyết định. Ví dụ một socket sau khi kết nối xong có thể muốn đọc nhưng chưa có dữ liệu chờ gửi:

```java
key.interestOps(SelectionKey.OP_READ);
```

Khi hàng đợi output có dữ liệu chưa gửi hết, thêm `OP_WRITE`:

```java
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
```

Khi đã gửi hết dữ liệu, bỏ `OP_WRITE`:

```java
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Các dòng trên là **mã minh họa** với một `SelectionKey key` còn hợp lệ và channel hỗ trợ cả `READ` và `WRITE`. Cách kết hợp bit dùng:

- `|` (OR): thêm bit mà vẫn giữ các bit khác.
- `& ~` (AND NOT): xóa bit mà vẫn giữ các bit khác.
- `&` (AND): kiểm tra xem một bit có được bật không.

Kể từ Java 11, `SelectionKey` còn có `interestOpsOr(ops)` và `interestOpsAnd(ops)` để cập nhật interest theo phép OR/AND nguyên tử đối với các lời gọi phương thức interestOps khác:

```java
key.interestOpsOr(SelectionKey.OP_WRITE);     // Thêm WRITE.
key.interestOpsAnd(~SelectionKey.OP_WRITE);   // Bỏ WRITE.
```

Đây là đoạn minh họa yêu cầu key hợp lệ và OP_WRITE được channel hỗ trợ. Các API atomic bit update hữu ích khi nhiều thread thay đổi interest; tuy nhiên chúng **không tự đồng bộ hóa hàng đợi output, trạng thái protocol hoặc vòng đời channel**. Việc cập nhật bitmask và đẩy dữ liệu vào queue vẫn cần một giao thức thread-safe thống nhất.

### 4.1. Thay interest không viết đè ready set ngay lập tức

`key.interestOps(newMask)` thay đổi điều selector sẽ quan tâm **trong các lần selection**. Nó không có nghĩa `key.readyOps()` được xóa hoặc tính lại tức thì. Interest set và ready set là các bitmask có mục đích khác nhau.

Theo contract selector, khi selection đang diễn ra, một thay đổi interest được gọi đồng thời có thể không được tính đến cho tới lần selection kế tiếp. Khi một worker thread chuyển dữ liệu vào queue và bật `OP_WRITE`, thường gọi thêm `selector.wakeup()` để yêu cầu event loop đang chờ trong `select()` quay lại xử lý thay đổi.

## 5. Ready set: selector đã quan sát trạng thái nào?

Sau `selector.select()`, một key có thể có:

```java
int ready = key.readyOps();

boolean canRead  = (ready & SelectionKey.OP_READ) != 0;
boolean canWrite = (ready & SelectionKey.OP_WRITE) != 0;
```

Đây là đoạn minh họa: `readyOps()` cần key hợp lệ và nên được đọc trong chu kỳ xử lý key đã chọn. Thông thường đọc readiness qua:

```java
if (key.isReadable()) {
    // Thử read() non-blocking.
}
if (key.isWritable()) {
    // Thử write() non-blocking.
}
```

Những phương thức `isReadable()`/`isWritable()` kiểm tra **ready set**, không kiểm tra interest set. Một key có thể vẫn lưu bit sẵn sàng được phát hiện từ lần chọn trước trong khi interest đã đổi, nên tránh coi `isReadable()` trên một key tùy ý là phép thăm dò trạng thái socket tức thời.

### 5.1. Sẵn sàng không có nghĩa “thao tác sẽ truyền hết dữ liệu”

Với non-blocking `SocketChannel`:

- `isReadable()==true` có nghĩa selector phát hiện điều kiện đọc. `read(buffer)` vẫn có thể trả `0` trong một số tình huống hoặc `-1` ở EOF; không bảo đảm một lần đọc đủ cả message.
- `isWritable()==true` chỉ gợi ý có khả năng ghi được **một lượng byte nào đó** mà không chặn. `write(buffer)` có thể ghi một phần, và sau đó có thể trả `0`.
- `isAcceptable()==true` là tín hiệu nên thử `server.accept()`; thao tác non-blocking vẫn cần xử lý giá trị trả về `null` theo contract.
- `isConnectable()==true` cho biết nên gọi `socket.finishConnect()`; việc kết nối vẫn có thể thất bại với ngoại lệ I/O.

Readiness là điều kiện để **thử thực hiện I/O đúng API**, không phải lời hứa rằng toàn bộ yêu cầu nghiệp vụ đã hoàn thành. Một message có thể gồm nhiều byte hoặc nhiều frame; phải lưu trạng thái khi dữ liệu chưa đủ.

### 5.2. Ready set được cập nhật ra sao khi một key vẫn được chọn?

Selector duy trì một **selected-key set**. Khi một key mới được chọn do một interest op sẵn sàng, ready set được cập nhật theo thao tác được nhận diện. Nếu key **đã nằm** trong selected-key set, các thao tác ready mới có thể được **OR** thêm vào các bit ready hiện có, thay vì tự động làm mới theo mô hình “snapshot hiện tại”.

Hệ quả: `readyOps()` không phải luôn là kết quả của một phép kiểm tra kernel tức thì tại thời điểm bạn đọc nó. Các bit có thể còn từ chu kỳ selection trước nếu chương trình giữ key trong selected set.

Cách viết event loop thông thường là **lấy từng key được chọn, xử lý, rồi loại khỏi `selectedKeys()` bằng iterator.remove()**. Ở lần selection sau, nếu vẫn có readiness thì selector có thể đưa key trở lại set.

## 6. Ba tập của Selector: registered, selected và cancelled

Ngoài hai **bitset trong từng key**, `Selector` quản lý những **tập key**:

| Tập | Lấy bằng / cơ chế | Ý nghĩa |
|---|---|---|
| Registered-key set | `selector.keys()` | Những key hiện đăng ký với selector |
| Selected-key set | `selector.selectedKeys()` | Những key được chọn và chờ ứng dụng xử lý |
| Cancelled-key set | Được selector duy trì nội bộ | Những key đã được yêu cầu hủy, sẽ được xử lý trong thao tác selection |

**Đừng nhầm** `selectedKeys()` (tập đối tượng key) với `key.readyOps()` (bitmask bên trong một key). Chúng có kiểu dữ liệu và ý nghĩa khác nhau.

Một key có thể:

1. Đã đăng ký và hợp lệ, nhưng **chưa** nằm trong selected set.
2. Nằm trong selected set, có ready bit đã được ghi nhận.
3. Được ứng dụng loại khỏi selected set sau xử lý nhưng **vẫn đăng ký** để theo dõi các đợt readiness tiếp theo.
4. Bị `cancel()`, trở nên invalid và được hủy đăng ký qua quy trình selection; không còn sử dụng như key hợp lệ.

### 6.1. Tại sao phải `iterator.remove()`?

Một vòng lặp mẫu:

```java
Iterator<SelectionKey> iterator =
        selector.selectedKeys().iterator();

while (iterator.hasNext()) {
    SelectionKey key = iterator.next();
    iterator.remove(); // Đã nhận key để xử lý.

    if (!key.isValid()) {
        continue;
    }

    if (key.isReadable()) {
        // Đọc non-blocking tới khi không đọc thêm được, hoặc theo quota.
    }
}
```

Mã trên là snippet minh họa nằm trong vòng đời selector đã được tạo, với `import java.util.Iterator` và `java.nio.channels.SelectionKey`. Dùng iterator để xóa khỏi selected set là cách chính thức và thông thường; `selectedKeys().add(...)` không được hỗ trợ.

**Loại khỏi selected-key set không phải `cancel()`.** Hành vi `iterator.remove()` chỉ báo chương trình đã xử lý một lượt notification. Channel và registration vẫn có thể hoạt động; selector sẽ chọn lại nếu có thao tác mới/tiếp diễn thỏa interest.

Nếu quên remove:

- Event loop có thể xử lý một key cũ lặp lại theo trạng thái ready cũ.
- Số key “đang selected” không phản ánh chính xác các sự kiện mới.
- Các bit ready có thể được giữ/OR qua nhiều lần selection khi key chưa ra khỏi selected set.
- Dễ tạo xử lý lặp hoặc làm kết quả quan sát khó hiểu.

## 7. Ví dụ Java 17+ chạy được: quan sát interest và ready trên Pipe

Để không phụ thuộc cổng mạng hay server ngoài, ví dụ dùng `Pipe`. `Pipe.SourceChannel` hỗ trợ `OP_READ` và có thể đăng ký với selector; `Pipe.SinkChannel` ghi dữ liệu vào đầu còn lại.

**Tệp nguồn:** `SelectionKeyDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class SelectionKeyDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            SelectionKey key = source.register(
                    selector, SelectionKey.OP_READ, "inbox");

            System.out.println("interestRead: "
                    + ((key.interestOps() & SelectionKey.OP_READ) != 0));

            ByteBuffer outbound = ByteBuffer.wrap(
                    "NIO".getBytes(StandardCharsets.US_ASCII));

            while (outbound.hasRemaining()) {
                sink.write(outbound);
            }

            System.out.println("selectMatched: "
                    + (selector.select(1000) > 0));

            Iterator<SelectionKey> iterator =
                    selector.selectedKeys().iterator();

            while (iterator.hasNext()) {
                SelectionKey selected = iterator.next();
                iterator.remove();

                if (selected.isValid() && selected.isReadable()) {
                    ByteBuffer inbound = ByteBuffer.allocate(16);
                    int count = source.read(inbound);
                    inbound.flip();

                    System.out.println("readyRead: "
                            + selected.isReadable());
                    System.out.println("readCount: " + count);
                    System.out.println("payload: "
                            + StandardCharsets.US_ASCII.decode(inbound));

                    selected.interestOps(0);
                }
            }

            System.out.println("interestAfter: "
                    + key.interestOps());
            System.out.println("selectedEmpty: "
                    + selector.selectedKeys().isEmpty());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac SelectionKeyDemo.java
java SelectionKeyDemo
```

**Stdout dự kiến trong môi trường bình thường, không có gián đoạn/đánh thức giả trước khi dữ liệu được chọn:**

```text
interestRead: true
selectMatched: true
readyRead: true
readCount: 3
payload: NIO
interestAfter: 0
selectedEmpty: true
```

**Giải thích chi tiết:**

1. `Pipe.open()` tạo đầu nguồn và đầu đích. `Pipe` **không** tự triển khai `AutoCloseable`; ví dụ đóng riêng `source`, `sink` và `selector` bằng `try-with-resources`.
2. `source.configureBlocking(false)` là điều kiện để đăng ký. `source.register(selector, OP_READ, "inbox")` trả key có interest READ; `"inbox"` là attachment.
3. `sink.write(...)` đưa ba byte `NIO` vào pipe. Sau đó `select(1000)` đợi tối đa khoảng một giây để phát hiện nguồn sẵn sàng đọc. Với pipe nội bộ và dữ liệu đã có, dự kiến chọn được key.
4. `selectedKeys()` chứa key vừa được chọn. `iterator.remove()` xóa nó khỏi selected set **nhưng không hủy registration**.
5. `selected.isReadable()` kiểm tra ready bit `OP_READ`. `source.read(inbound)` lấy ba byte, `flip()` chuẩn bị giải mã US-ASCII thành `NIO`.
6. `selected.interestOps(0)` tạm tắt giám sát trên key sau khi đã xử lý. Key vẫn hợp lệ cho đến khi cancel/close.
7. `selectedKeys().isEmpty()` trả `true` vì ứng dụng đã remove các key được chọn.

Ví dụ đóng cả ba tài nguyên đúng phạm vi. Không in object identity, địa chỉ file hay số cổng ngẫu nhiên. Nếu selector bị interrupt hoặc môi trường có hành vi không thường gặp, selection có thể trả về 0; đó là lý do event loop production luôn phải xử lý cả trường hợp `select()` trở về **không có key**.

### 7.1. Đọc dữ liệu sau `isReadable` vẫn phải kiểm tra `read`

Trong ví dụ nhỏ, `source.read` dự kiến trả 3. Với chương trình thật, `read` có thể trả 0 khi chưa có byte để lấy thêm hoặc -1 khi đầu vào kết thúc; khi dữ liệu nhiều hơn kích thước buffer, phải tiếp tục đọc và giữ phần thông điệp chưa hoàn chỉnh để xử lý sau.

**Không suy diễn rằng một key READ-ready chứa đúng một message.** TCP là byte stream, có thể chứa nửa message, nhiều message, hoặc dữ liệu chia thành những lần đọc tùy ý. Một parser phải có state để xác định boundary theo protocol.

## 8. Event loop Selector tối thiểu cho server/socket

Dưới đây là **khung minh họa thuật toán**, không phải chương trình độc lập: nó dùng `selector`, `server`, các handler và queue do ứng dụng định nghĩa. Mục đích là xác định nơi đọc ready bit và cập nhật interest.

```java
while (running) {
    selector.select(); // Có thể trở về không có key.

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
            if (key.isValid() && key.isConnectable()) {
                finishConnection(key);
            }
            if (key.isValid() && key.isReadable()) {
                readAvailableBytes(key);
            }
            if (key.isValid() && key.isWritable()) {
                flushPendingWrites(key);
            }
        } catch (IOException ex) {
            key.cancel();
            key.channel().close();
        }
    }
}
```

**Đây là pseudocode theo cú pháp Java, không tự biên dịch**: `running` và bốn hàm handler là thành phần của ứng dụng. Nó minh họa thứ tự phổ biến:

1. `select()` đợi thao tác từ key mà selector quan tâm.
2. Duyệt selected set, lấy key và remove nó khỏi tập.
3. Kiểm tra valid để tránh xử lý key đã cancel.
4. Xử lý các thao tác được báo ready; việc xử lý có thể thay interestOps, cancel key hoặc đóng channel.
5. Theo dõi lỗi I/O và vòng đời kết nối; không giữ invalid key cho vòng sau.

Việc kiểm tra nhiều `if` thay vì `else if` hợp lý khi một key có thể ready nhiều thao tác cùng lúc. Tuy nhiên handler có thể thay đổi/cancel key, nên ví dụ kiểm tra `isValid()` trước mỗi thao tác kế tiếp.

### 8.1. Server: `OP_ACCEPT` và đăng ký channel vừa được chấp nhận

`ServerSocketChannel` đang non-blocking được đăng ký `OP_ACCEPT`:

```java
server.configureBlocking(false);
SelectionKey acceptKey =
        server.register(selector, SelectionKey.OP_ACCEPT);
```

Đây là snippet với `server` kiểu `ServerSocketChannel` và `selector` đã được tạo; server phải bind đúng địa chỉ/port trước khi nhận kết nối.

Khi `acceptKey.isAcceptable()`:

```java
SocketChannel client = server.accept();
if (client != null) {
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ);
}
```

Đây là đoạn minh họa cần import `SocketChannel`, xử lý `IOException` và quản lý đóng client khi kết thúc. `accept()` có thể trả `null` khi không có connection chờ tại thời điểm gọi trong non-blocking mode. Với server có nhiều kết nối đến đồng thời, thường accept theo vòng lặp đến khi `null`, có giới hạn số lượng mỗi lượt nếu cần fairness.

**Lỗi cần tránh:** đăng ký `OP_ACCEPT` lên `SocketChannel` của client. Client dùng các op tương ứng như `OP_CONNECT`, `OP_READ` và `OP_WRITE`.

### 8.2. Client: `OP_CONNECT` không thay thế `finishConnect()`

Với `SocketChannel` non-blocking, `connect(remote)` có thể chưa hoàn thành ngay. Nếu còn pending, đăng ký `OP_CONNECT`, rồi khi `isConnectable()`:

```java
SocketChannel client = (SocketChannel) key.channel();

if (client.finishConnect()) {
    key.interestOps(SelectionKey.OP_READ);
}
```

Đoạn minh họa giả định `key` là key của socket đang kết nối, có xử lý `IOException` và `SocketChannel` được import. `finishConnect()` có thể ném lỗi khi kết nối thất bại. Sau khi kết nối thành công, nên bỏ `OP_CONNECT` và chuyển sang các thao tác thật sự cần theo dõi. Nếu còn byte chờ ghi, có thể thêm `OP_WRITE` phù hợp.

## 9. Vì sao `OP_WRITE` dễ gây busy loop?

Trên socket không chặn, hệ thống thường có sẵn một lượng chỗ trống trong send buffer. Vì thế **OP_WRITE có thể luôn ready trong phần lớn thời gian**, ngay cả khi ứng dụng chưa có byte nào cần gửi.

Một pattern nguy hiểm:

```java
client.register(selector,
        SelectionKey.OP_READ | SelectionKey.OP_WRITE);

// Không có dữ liệu để ghi, nhưng vẫn giữ OP_WRITE suốt đời kết nối.
```

Đoạn minh họa với client đã non-blocking, selector hợp lệ và socket hỗ trợ cả READ/WRITE. Selector có thể liên tục thức dậy vì writable; CPU tăng dù ứng dụng không có công việc.

**Cách quản lý hợp lý với hàng đợi ghi:**

- Khi queue output **rỗng**, interest thông thường chỉ cần `OP_READ` (hoặc bộ bit cần thiết khác), **không giữ `OP_WRITE`**.
- Khi enqueue một message để gửi, thêm `OP_WRITE` và đánh thức selector nếu thread khác đang chờ.
- Khi key writable, gọi `SocketChannel.write(ByteBuffer)` để gửi **bao nhiêu byte có thể**, cập nhật position buffer.
- Nếu byte chưa gửi hết do write một phần hoặc bằng 0, giữ `OP_WRITE` để nhận tín hiệu khi socket lại có khả năng ghi.
- Khi queue cạn, **xóa `OP_WRITE`**. Không ghi một lần rồi giả định toàn bộ message đã truyền.

Mã cập nhật bit minh họa:

```java
// Khi có dữ liệu chờ, channel hỗ trợ OP_WRITE:
key.interestOpsOr(SelectionKey.OP_WRITE);

// Khi không còn dữ liệu chờ:
key.interestOpsAnd(~SelectionKey.OP_WRITE);
```

Không gọi hai dòng liên tiếp như một thao tác xử lý thực tế: chúng minh họa **hai thời điểm trạng thái queue khác nhau**. Và đừng để non-I/O thread tự ghi socket đồng thời với event loop mà không có thỏa thuận synchronization rõ ràng.

### 9.1. `isWritable()` không đồng nghĩa đã gửi xong

`key.isWritable()==true` cho biết có readiness ghi; `write(buffer)` có thể chỉ ghi một phần. Kiểm tra `buffer.hasRemaining()` để giữ buffer chưa gửi hết và tiếp tục khi có readiness sau đó. Với giao thức framing, cần giữ nguyên thứ tự các buffer trong queue, tránh tái sử dụng một `ByteBuffer` trong lúc vẫn còn byte chưa gửi.

## 10. Thay đổi interest từ thread khác và `wakeup()`

Một event loop có thể đang chờ trong `selector.select()`. Trong khi đó, thread xử lý nghiệp vụ tạo dữ liệu trả lời và muốn ghi trên socket:

```java
// Worker thread: queue phải an toàn đa luồng.
pendingWrites.add(outgoing);

key.interestOpsOr(SelectionKey.OP_WRITE);
selector.wakeup();
```

Đây là đoạn minh họa không độc lập: `pendingWrites` là queue phù hợp đồng thời, `outgoing` là buffer có byte, `key` hợp lệ và hỗ trợ WRITE. Gọi `wakeup()` báo selector rời trạng thái chờ trong `select()` (hoặc khiến lần select tiếp theo trở về sớm theo contract), cho phép event loop xử lý queue/interest mới.

Các lưu ý:

- `wakeup()` **không** tự đặt `OP_WRITE` hay readiness bit. Nó chỉ tác động cơ chế đánh thức.
- InterestOps thay đổi trong lúc `select()` đang chạy có thể chỉ được ghi nhận ở lần selection tiếp theo, tùy timing/semantics.
- `select()` có thể trả về 0 sau wakeup; đó là tình huống hợp lệ và event loop vẫn phải chạy phần xử lý công việc được enqueue.
- Cần cơ chế điều phối queue và interest để tránh race: giữa lúc event loop thấy queue rỗng và tắt WRITE, thread khác có thể vừa enqueue. Có thể gom mọi thay đổi interest vào event-loop thread bằng task queue + `wakeup()` để giảm rủi ro.
- `SelectionKey.interestOpsOr/And` giúp cập nhật bitmask mà không làm mất cập nhật đồng thời từ API interest, nhưng **không đồng bộ dữ liệu nghiệp vụ** hoặc thứ tự I/O.

### 10.1. Phân biệt `select()`, `select(timeout)` và `selectNow()`

- `select()`: có thể chờ tới khi có key ready, wakeup, interrupt hoặc điều kiện khác khiến nó trở về.
- `select(long timeout)`: đợi tối đa khoảng thời gian yêu cầu; với timeout `0`, hợp đồng là chờ vô hạn tương tự `select()`, **không phải polling ngay lập tức**.
- `selectNow()`: chọn không chặn và trở về ngay.

Giá trị trả về là số key có ready set được cập nhật bởi thao tác selection hiện tại, **không được đồng nhất mù quáng với `selectedKeys().size()`** nếu ứng dụng giữ các key đã chọn qua nhiều lượt. Một lần select cũng có thể trả về 0 khi bị đánh thức, bị interrupt hoặc hết thời gian chờ; code không nên giả định cứ return là có ít nhất một key.

## 11. `cancel()`, đóng channel và kiểm tra `isValid()`

`key.cancel()` đánh dấu key **không còn hợp lệ** ngay khi yêu cầu hủy và đưa nó vào quy trình xử lý đăng ký bị hủy của selector. Thao tác loại registration khỏi tập của selector được xử lý trong selection tiếp theo theo contract, không phải một lời hứa rằng mọi cấu trúc nội bộ được dọn sạch ngay tức thì.

```java
key.cancel();
System.out.println(key.isValid()); // false
```

Đây là đoạn minh họa khi `key` còn là đối tượng SelectionKey. Sau cancel, gọi các API đòi hỏi key hợp lệ như `interestOps()` hoặc `readyOps()` có thể ném `CancelledKeyException`. Phương thức `channel()` và `selector()` giúp truy xuất ngữ cảnh đăng ký, nhưng điều đó không có nghĩa key còn đang hoạt động.

**Phân biệt các thao tác:**

| Thao tác | Đóng channel? | Hủy registration? | Key còn trong selected set? |
|---|---|---|---|
| `selectedKeys().remove(key)` | Không | Không | Đã loại khỏi selected set |
| `key.interestOps(0)` | Không | Không | Có thể còn nếu chưa remove |
| `key.cancel()` | Không tự đóng channel | Yêu cầu hủy, key invalid ngay | Cleanup trong selection tiếp theo |
| `key.channel().close()` | Có | Khi channel đóng, các key liên quan bị hủy | Cleanup theo selector |
| `selector.close()` | Đóng selector, vô hiệu hóa registration | Có | Tập được dọn theo contract; channel tự nó không nhất thiết đóng |

Một hệ thống lỗi I/O trên socket thường vừa `cancel()` vừa `channel.close()`. Chỉ `cancel` không giải phóng socket; chỉ remove khỏi selected set không hủy đăng ký.

### 11.1. Attachment dùng để làm gì?

`key.attach(obj)` lưu một đối tượng ngữ cảnh của ứng dụng trên key. Ví dụ:

```java
final class ConnectionState {
    ByteBuffer input = ByteBuffer.allocate(4096);
    // Có thể bổ sung output queue, parser state, id phiên...
}

ConnectionState state = new ConnectionState();
key.attach(state);
ConnectionState retrieved =
        (ConnectionState) key.attachment();
```

Đây là đoạn code minh họa đặt trong phạm vi có `SelectionKey key` hợp lệ và import `ByteBuffer`; cần thiết kế đồng bộ nếu attachment bị truy cập ở nhiều thread. Attachment không tạo I/O readiness, không chứa “message vừa đến” do selector tự giải mã; nó chỉ là nơi thuận tiện để gắn parser/buffer/queue mà chương trình tự quản lý.

Khi cancel/close, cần giải phóng các tài nguyên được tham chiếu bởi attachment theo chính sách ứng dụng, tránh memory leak từ những object vẫn còn tham chiếu trong data structure.

## 12. Trạng thái SELECTED không phải subscription cấp cao

Selector NIO có thể được xem như công cụ báo **khả năng thực hiện thao tác I/O**. Nó không tự:

- Tách gói theo newline, length-prefix, JSON hoặc giao thức tùy chỉnh.
- Bảo đảm fairness giữa các connection; một connection có dữ liệu quá nhiều có thể chiếm thời gian xử lý.
- Đảm bảo một lần `read()` tạo đúng một message.
- Lập lịch retry hay timeout nghiệp vụ.
- Đảm bảo thứ tự event xử lý bằng nhiều thread nếu bạn tự triển khai concurrent handlers.
- Cung cấp backpressure hoàn chỉnh giữa người gửi, output queue và socket.
- Bảo đảm tính đúng đắn của việc giữ/sửa attachment.

Các thiết kế thực tế cần phân biệt lớp **event loop (readiness)** và lớp **protocol/application state (message, retry, timeout, backpressure)**.

### 12.1. Edge-triggered và level-triggered: không suy luận quá mức từ Java API

Một số OS có cơ chế notification khác nhau. Java `Selector` trừu tượng hóa chi tiết provider. Không dựa vào giả định “một ready event = một byte/packet/message mới”, hoặc mỗi lần select luôn cho một sự kiện duy nhất rồi bit được clear như message queue.

Mô hình lập trình bền vững là: khi được chọn, **thử I/O không chặn**, cập nhật bộ đệm/queue, và điều chỉnh interest cho chu kỳ tiếp theo. Với đọc, thường tiếp tục đọc đến khi không còn byte có thể lấy trong lượt đó (hoặc dừng theo quota để giữ fairness); với ghi, quản lý phần chưa gửi và tắt OP_WRITE khi queue đã hết.

## 13. Ví dụ xử lý tình huống interest và ready khác nhau

### Trường hợp A: chỉ quan tâm đọc, socket có thể ghi

```java
key.interestOps(SelectionKey.OP_READ);
```

Dù socket trên OS lúc đó có khả năng ghi, selector không cần đưa ready bit WRITE vào thông báo do chương trình không quan tâm WRITE. **Khả năng I/O cấp OS** không đồng nhất với **interest mask ứng dụng**.

### Trường hợp B: muốn đọc và ghi, nhưng chỉ đọc ready

```java
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
```

Nếu selector chỉ nhận diện READ ready trong lượt chọn, `isReadable()` đúng còn `isWritable()` có thể sai. Interest set có hai bit; ready set có thể chỉ có một. Không lấy `interestOps()` để quyết định gọi `read()/write()` mà không xét readiness và trạng thái queue.

### Trường hợp C: xử lý xong rồi thay interest

Ứng dụng nhận được READ-ready, đọc xong và tạm dừng đọc để áp dụng backpressure:

```java
key.interestOpsAnd(~SelectionKey.OP_READ);
```

Interest set hiện không còn READ. Nhưng `key.readyOps()` có thể vẫn lưu READ từ selection trước; chỉ thay interest không làm ready bit biến mất tức thì. Ứng dụng phải dùng trạng thái điều phối riêng và xử lý theo chu kỳ chọn, không tái gọi read chỉ vì bit cũ còn trên key.

### Trường hợp D: key đã cancel

```java
key.cancel();
boolean stillValid = key.isValid(); // false
```

Không gọi `key.isReadable()` rồi coi trạng thái là hợp lệ; key invalid có thể ném `CancelledKeyException` khi đọc ready set. Chỉ xử lý key sau `isValid()` và vẫn chuẩn bị bắt lỗi I/O vì trạng thái có thể đổi đồng thời.

### Trường hợp E: quên loại key khỏi selected set

Một key vẫn có thể nằm trong `selector.selectedKeys()` khi event loop gọi `select()` lần tiếp theo. Các bit ready có thể tích lũy/thay đổi theo quy tắc key đã selected, không cho ra snapshot đơn giản. Dùng `Iterator.remove` sau khi lấy key để xử lý và không biến selected set thành nơi lưu task queue của ứng dụng.

## 14. Những lỗi phổ biến

1. **Đăng ký channel chưa `configureBlocking(false)`.** Có thể ném `IllegalBlockingModeException`.
2. **Nhầm `FileChannel` với `SelectableChannel`.** FileChannel không đăng ký Selector theo cách của SocketChannel.
3. **Dùng `OP_ACCEPT` cho client SocketChannel.** ServerSocketChannel mới hỗ trợ accept; xem `validOps()`.
4. **Cho rằng `interestOps()` và `readyOps()` bằng nhau.** Interest là yêu cầu theo dõi, ready là kết quả selection.
5. **Dùng `interestOps` để biết kênh đã sẵn sàng chưa.** Phải xem readiness qua `readyOps`/`isReadable` sau selection và thử I/O.
6. **Xem `isWritable` là gửi hết buffer được ngay.** Non-blocking write có thể gửi một phần hoặc trả 0.
7. **Xem `isReadable` là chắc chắn có một message hoàn chỉnh.** Cần parser, giữ byte dư và xử lý EOF.
8. **Để `OP_WRITE` bật liên tục dù output queue rỗng.** Dễ gây busy loop và CPU cao.
9. **Quên `iterator.remove()` khi duyệt selectedKeys.** Các key cũ tồn tại qua vòng selection, dễ xử lý lặp.
10. **Nghĩ remove khỏi selectedKeys là cancel key.** Chúng tác động hai tập và hai mục đích khác nhau.
11. **Gọi `selectedKeys().add(key)` để tạo event giả.** API không cho thêm tùy ý; dùng task queue/wakeup riêng.
12. **Nhầm selected-key set là ready set.** Set chứa đối tượng SelectionKey; ready set là bitmask trên từng key.
13. **Tin `readyOps()` luôn phản ánh trạng thái OS ở đúng nano-giây hiện tại.** Ready bits có thể còn của selection trước nếu key chưa được bỏ selected set.
14. **Cập nhật interest từ worker thread rồi mong select đang chờ tự nhận ngay.** Cần hiểu timing và dùng `selector.wakeup()` theo giao thức.
15. **Xem `wakeup()` là “bật OP_WRITE”.** Nó chỉ đánh thức selector; phải thay interest và chuẩn bị queue thật.
16. **Dùng `key.interestOps(key.interestOps() | bit)` đa luồng mà không xét race.** Cân nhắc `interestOpsOr/And` hoặc gom cập nhật về event-loop thread.
17. **Tiếp tục gọi ready/interests sau `cancel()`.** Có thể gặp `CancelledKeyException`.
18. **Chỉ cancel key mà không đóng socket hỏng.** Registration mất nhưng tài nguyên channel vẫn cần được dọn.
19. **Đọc `select(0)` như “poll ngay”.** Với Java Selector, timeout 0 có nghĩa chờ vô hạn; dùng `selectNow()` để poll.
20. **Cho rằng giá trị return của select luôn bằng kích thước selectedKeys.** Nếu còn key từ lượt trước, hai số có thể khác.
21. **Dùng một lần `read`/`write` rồi bỏ qua phần dữ liệu chưa xong.** ByteBuffer position/remaining cần được giữ trong state.
22. **Dùng một handler blocking lâu trong selector thread.** Tất cả kết nối khác có thể bị chậm; tách tác vụ dài khỏi event loop.
23. **Tưởng `attach()` tự quản lý cleanup, timeout hay thread safety.** Attachment chỉ lưu tham chiếu ứng dụng.
24. **Không xử lý `accept()==null` hoặc `finishConnect()` thất bại.** Ready chỉ dẫn hướng thử I/O, không miễn xử lý tình huống cạnh tranh và ngoại lệ.
25. **Đăng ký OP_READ/WRITE không thuộc `channel.validOps()`.** Gây `IllegalArgumentException`; kiểm tra capability đúng loại channel.

## 15. Tự kiểm tra kiến thức

**Câu 1.** `SelectionKey` đại diện cho một lần read event hay một đăng ký channel–selector?  
**Trả lời:** Một đăng ký. Cùng key có thể được chọn nhiều lần.

**Câu 2.** `key.interestOps()==OP_READ` có bảo đảm `key.isReadable()==true` ngay không?  
**Không.** Interest chỉ là thao tác muốn theo dõi; ready phải được selector phát hiện trong selection.

**Câu 3.** Khác nhau giữa `selector.selectedKeys()` và `key.readyOps()`?  
**Trả lời:** selectedKeys là tập `SelectionKey` đã chọn; readyOps là bitmask thao tác sẵn sàng trên *một key*.

**Câu 4.** Làm sao kiểm tra xem bit OP_READ có được bật trong mask?  
**Trả lời:** `(mask & SelectionKey.OP_READ) != 0`. Không dùng `mask == OP_READ` nếu có thể có nhiều bit.

**Câu 5.** Vì sao `OP_WRITE` không nên luôn luôn bật?  
**Vì** socket thường writable khi send buffer còn chỗ, khiến selector đánh thức liên tục dù queue output rỗng.

**Câu 6.** `iterator.remove()` có đóng channel không?  
**Không.** Nó chỉ gỡ key khỏi selected-key set, không cancel registration.

**Câu 7.** Cần làm gì sau `key.cancel()`?  
**Trả lời:** Không dùng interest/ready trên key invalid; đóng channel khi không dùng nữa và để selector xử lý hủy đăng ký.

**Câu 8.** `selector.select(0)` có giống `selectNow()` không?  
**Không.** Timeout 0 của `select(long)` là chờ vô hạn; `selectNow()` mới không chặn.

**Câu 9.** Một socket `isWritable()==true`, `write(ByteBuffer)` có thể trả 0 không?  
**Có.** Readiness không bảo đảm ghi được toàn bộ dữ liệu; giữ byte chưa gửi và chờ lượt khác.

**Câu 10.** Worker thread muốn gửi dữ liệu cho socket do event loop quản lý. Có cần `wakeup()`?  
**Thường cần** nếu selector có thể đang chờ: enqueue dữ liệu theo giao thức thread-safe, bật interest WRITE hoặc gửi task cập nhật interest cho loop, sau đó `wakeup()`.

**Câu 11.** Nếu `SocketChannel` chưa kết nối xong, một lần `isConnectable()` có bảo đảm đã connected?  
**Không.** Phải gọi `finishConnect()` và xử lý ngoại lệ, sau đó mới cập nhật interest.

**Câu 12.** Một pipe SourceChannel hỗ trợ OP_ACCEPT không?  
**Không.** SourceChannel của pipe chỉ hỗ trợ read; xem `validOps()` thay vì áp đặt các bit không liên quan.

## 16. Ghi nhớ và tài liệu chính thức

**Công thức vận hành:** đăng ký `SelectionKey` với **interest set** phù hợp → gọi `select` → duyệt **selected-key set** → đọc **ready set** → thực hiện non-blocking I/O → cập nhật trạng thái và interest → `iterator.remove()` để sẵn sàng cho đợt selection tiếp theo.

Những phân biệt bắt buộc nhớ:

- `interestOps` là **mong muốn theo dõi**, không phải bằng chứng kênh đang ready.
- `readyOps` là **trạng thái đã được selector ghi nhận**, không thay thế việc kiểm tra kết quả thực tế của `read`/`write`.
- `selectedKeys()` là **tập key cần xử lý**, không phải bitmask; key có thể là registered dù không selected.
- `cancel`, `remove khỏi selectedKeys` và `interestOps(0)` là **ba hành động khác nhau**.
- Tắt `OP_WRITE` khi output queue rỗng, dùng `selector.wakeup()` để phối hợp event loop và các thread khác, và quản lý giao thức non-blocking với buffer/attachment riêng.

Tài liệu Java SE 21:

- `SelectionKey` — `interestOps`, `readyOps`, các bit `OP_*`, `cancel`, `attach`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html
- `Selector` — các key set, `select`, `selectNow`, `wakeup`, quy tắc cập nhật readiness: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html
- `SelectableChannel` — `validOps`, `configureBlocking`, `register`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectableChannel.html
- `SocketChannel` — `connect`, `finishConnect`, `read`, `write`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html
- `ServerSocketChannel` — `accept`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html
- `Pipe` — SourceChannel và SinkChannel: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Pipe.html
