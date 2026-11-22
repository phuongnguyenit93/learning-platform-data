# Java 11+ — Selector callback: `selectNow` và lựa chọn không chặn

## 1. Mục tiêu của `selectNow(Consumer<SelectionKey>)`

Khi lập trình Java NIO, một `Selector` theo dõi nhiều `SelectableChannel` đã đăng ký (như `SocketChannel`, `ServerSocketChannel`, `DatagramChannel` hoặc `Pipe.SourceChannel`) để phát hiện khả năng thực hiện những thao tác I/O mà ta quan tâm: đọc, ghi, kết nối hoặc chấp nhận kết nối.

Từ **Java 11**, `Selector` có thêm cách chọn kênh sẵn sàng và **xử lý ngay từng `SelectionKey` bằng callback**:

```java
int selected = selector.selectNow(key -> {
    // Xử lý một key đang báo sẵn sàng cho thao tác quan tâm.
});
```

`selectNow(Consumer<SelectionKey> action)` thực hiện một lần kiểm tra readiness **không chờ kênh trở nên sẵn sàng**, sau đó gọi `action.accept(key)` đồng bộ cho những key được chọn. Nó trả về `int` là **số lượng key khác nhau được xử lý**, có thể bằng 0.

Có hai ý phải phân biệt:

- **“Không chặn” của `selectNow`** nghĩa là bước chọn không đợi sự kiện I/O mới xuất hiện. Nó **không** biến callback thành tác vụ chạy nền, không khiến mọi lệnh bên trong callback tự động không chặn và cũng không loại bỏ các chi phí chạy mã hoặc tranh chấp khóa.
- **“Callback”** nghĩa là đối tượng `Consumer<SelectionKey>` nhận key sẵn sàng ngay trong lần gọi `selectNow` hiện tại. Không cần tự duyệt `selector.selectedKeys()` để lấy danh sách key của lần chọn này.

Cách gọi **`selectNow()` không tham số** đã tồn tại trước Java 11; biến thể **`selectNow(Consumer<SelectionKey>)`** mới là API callback được thêm từ Java 11. Hai overload có hợp đồng xử lý tập selected-key khác nhau.

## 2. So sánh các lựa chọn trong `Selector`

| Phương thức | Chờ I/O trở nên sẵn sàng? | Cách xử lý key sẵn sàng | Giá trị trả về |
| --- | --- | --- | --- |
| `select()` | Có thể chặn đến khi ready/`wakeup`/interrupt. | Cập nhật tập `selectedKeys()`; caller tự duyệt và xử lý. | Số key có trạng thái sẵn sàng được cập nhật. |
| `select(long timeout)` | Có thể chặn tối đa khoảng thời gian dương đã cho; **`timeout == 0` là chờ vô thời hạn**, không phải “thăm dò”. | Cập nhật `selectedKeys()`. | Số key có trạng thái sẵn sàng được cập nhật. |
| `selectNow()` | **Không đợi readiness**. | Cập nhật `selectedKeys()`; caller tự duyệt. | Số key có trạng thái sẵn sàng được cập nhật. |
| `select(Consumer<SelectionKey>)` | Có thể chặn đến khi ready/`wakeup`/interrupt. | Gọi callback với key sẵn sàng. | Số **key duy nhất** được xử lý. |
| `select(Consumer<SelectionKey>, long timeout)` | Với timeout dương, có thể chờ đến hạn; với 0, chờ vô thời hạn. | Gọi callback. | Số **key duy nhất** được xử lý. |
| **`selectNow(Consumer<SelectionKey>)`** | **Không đợi readiness**. | Gọi callback ngay với key đã sẵn sàng. | Số **key duy nhất** được xử lý. |

Trên các overload callback, giá trị trả về đếm **key duy nhất**, **không nhất thiết bằng số lần callback được gọi**. Đối với key sẵn sàng cho nhiều thao tác, callback được phép chạy nhiều lần trên cùng key với những tập bit `readyOps()` khác nhau theo hợp đồng API.

Vì thế, chọn `selectNow(action)` khi muốn ghép bước thăm dò I/O vào một vòng lặp đang phải thực hiện các công việc khác. Chọn `select(action)` khi luồng chủ yếu xử lý sự kiện I/O và có thể đợi. Chọn overload có timeout dương khi vòng lặp cần thời hạn chờ có giới hạn. Không dùng `select(action, 0)` để thay thế `selectNow(action)`.

## 3. Chuẩn bị: đăng ký channel ở chế độ không chặn

`Selector` theo dõi readiness của một `SelectableChannel` thông qua đối tượng `SelectionKey`. Khi đăng ký, cần chỉ định interest operations:

```java
// Minh họa trong phương thức có throws IOException.
try (Selector selector = Selector.open();
     SocketChannel channel = SocketChannel.open()) {

    channel.configureBlocking(false);
    SelectionKey key = channel.register(selector, SelectionKey.OP_CONNECT);

    // Khi muốn xử lý sự kiện, gọi selector.selectNow(action).
}
```

Đoạn trên chỉ để minh họa đăng ký một `SocketChannel`; chưa có kết nối đích nên không phải chương trình network hoàn chỉnh. Cần import `java.nio.channels.*` và xử lý trạng thái kết nối khi dùng thực tế.

Các điểm bắt buộc:

1. **`configureBlocking(false)` trước `register`:** đăng ký một channel đang ở chế độ blocking với selector sẽ gây `IllegalBlockingModeException`. `selectNow` không tự chuyển channel sang nonblocking.
2. **Đúng interest set:** dùng `SelectionKey.OP_READ` để theo dõi đọc, `OP_WRITE` để theo dõi ghi, `OP_ACCEPT` cho server chấp nhận kết nối, `OP_CONNECT` cho kết nối chưa hoàn thành, chỉ khi channel hỗ trợ thao tác tương ứng. Không đăng ký bit không được channel hỗ trợ.
3. **`SelectionKey` chỉ là tín hiệu sẵn sàng:** readiness không đồng nghĩa đã có đủ toàn bộ dữ liệu ứng dụng cần. Với nonblocking `SocketChannel` hoặc `Pipe.SourceChannel`, `read` có thể trả `0` (tạm thời không đọc được thêm), số dương (đã đọc được byte) hoặc `-1` (EOF).
4. **Cập nhật interest khi cần:** nếu không có dữ liệu cần ghi, không nên giữ `OP_WRITE` mãi vì nhiều kênh gần như luôn có thể ghi, dẫn đến lặp liên tục không cần thiết.

`Selector` là bộ phân luồng sự kiện readiness, **không phải** một pool luồng, hàng đợi tác vụ hoặc một hệ thống callback bất đồng bộ độc lập.

## 4. Luồng hoạt động của `selectNow(action)`

Có thể hình dung một lần xử lý như sau:

```text
Các channel đã register (interestOps)
               |
               v
    selector.selectNow(action)
               |
      Thăm dò readiness ngay
               |
     +---------+----------+
     |                    |
 Không key ready      Có key ready
     |                    |
 return 0          gọi action.accept(key)
                          |
                đọc/ghi nonblocking phù hợp
                          |
                  return số key duy nhất
```

Các bước thực tế theo hợp đồng Java:

- Selector xử lý key bị hủy (`cancelled`) theo quy trình selection và truy vấn hệ điều hành về những thao tác sẵn sàng ở thời điểm kiểm tra.
- Với key được chọn, tập `readyOps()` được cập nhật rồi callback chạy trên key đó. Callback có thể được gọi hơn một lần trên cùng key cho các nhóm thao tác sẵn sàng khác nhau.
- Callback phải kiểm tra `key.isValid()` khi có nguy cơ channel/key đã bị đóng hoặc hủy, rồi kiểm tra `key.isReadable()`, `isWritable()`, `isAcceptable()` hay `isConnectable()` theo mục tiêu đã đăng ký.
- Khi không có key được chọn, kết quả là `0`. **Không diễn giải `0` là EOF, lỗi mạng hoặc trạng thái kết thúc ứng dụng**: có thể đơn giản là lúc này chưa có thao tác phù hợp đã sẵn sàng.
- Việc kiểm tra readiness không chặn đợi sự kiện tương lai. Nếu cần đợi, caller có thể chọn biến thể blocking hoặc được một event loop điều phối để thăm dò lại đúng thời điểm.

**Sự khác biệt về tập selected-key:** overload callback không thêm key được xử lý vào `selectedKeys()` để caller duyệt. Tuy vậy, hợp đồng implementation mặc định không bảo đảm tập `selectedKeys()` luôn trống sau khi callback kết thúc; nó có thể bị ảnh hưởng bởi trạng thái trước đó và cách triển khai. Vì vậy **không** vừa dựa vào callback vừa đòi `selectedKeys().size() == số callback`. Nếu dùng overload `selectNow()` không tham số, phải tự duyệt và xóa key đã xử lý khỏi tập selected-key bằng iterator.

## 5. Ví dụ Java 11+ chạy độc lập: `Pipe` và callback chọn không chặn

Để minh họa ổn định mà không cần mạng, dùng `Pipe` nội bộ. `Pipe.SourceChannel` được cấu hình nonblocking và đăng ký `OP_READ`. Khi đầu ghi đã đẩy chuỗi `PING`, đầu đọc trở nên sẵn sàng, rồi `selectNow(action)` gọi callback để đọc byte.

Lưu vào **`SelectorSelectNowDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;

public final class SelectorSelectNowDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);

            // No registered channel: selecting now always yields zero.
            int beforeRegistration = selector.selectNow(
                    key -> { throw new AssertionError("unexpected key"); });
            System.out.println("no-registration=" + beforeRegistration);

            source.register(selector, SelectionKey.OP_READ);
            ByteBuffer sent = ByteBuffer.wrap("PING".getBytes(StandardCharsets.UTF_8));
            while (sent.hasRemaining()) {
                sink.write(sent);
            }

            ByteArrayOutputStream received = new ByteArrayOutputStream();

            int selected = selector.selectNow(key -> {
                if (!key.isValid() || !key.isReadable()) {
                    return;
                }

                Pipe.SourceChannel channel = (Pipe.SourceChannel) key.channel();
                ByteBuffer chunk = ByteBuffer.allocate(16);
                try {
                    while (true) {
                        int n = channel.read(chunk);
                        if (n <= 0) {
                            if (n == -1) {
                                key.cancel();
                            }
                            break;
                        }
                        chunk.flip();
                        byte[] bytes = new byte[chunk.remaining()];
                        chunk.get(bytes);
                        received.write(bytes, 0, bytes.length);
                        chunk.clear();
                    }
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            System.out.println("selected=" + selected);
            System.out.println("payload=" +
                    new String(received.toByteArray(), StandardCharsets.UTF_8));
        }
    }
}
```

Biên dịch và chạy với JDK 11 trở lên. `--release 11` xác minh ví dụ chỉ dùng API có trong Java 11:

```bash
javac -encoding UTF-8 --release 11 SelectorSelectNowDemo.java
java SelectorSelectNowDemo
```

Kết quả kiểm chứng với luồng `Pipe` được ghi trước khi thăm dò:

```text
no-registration=0
selected=1
payload=PING
```

Giải thích các phần quan trọng:

- `no-registration=0`: chưa có bất kỳ channel đăng ký, nên không có key sẵn sàng và callback không được gọi. Đây là ví dụ rõ nhất về kết quả `0`.
- `configureBlocking(false)` là điều kiện để đăng ký đầu đọc với selector. Đầu ghi trong fixture đơn giản này giữ chế độ mặc định và ghi trọn bốn byte nhỏ; điều đó không thay đổi tính **không chờ readiness** của lời gọi `selectNow(action)` trên selector.
- `register(..., SelectionKey.OP_READ)` tạo key quan tâm tới đọc. Khi đầu ghi đã gửi `PING`, pipe có dữ liệu sẵn để đọc.
- Callback chỉ đọc khi `key.isValid()` và `key.isReadable()`. Nếu `read` trả `0` thì ngừng vòng đọc trong lần callback này; nếu trả `-1` thì hủy key. Với nonblocking channel, vòng `while` không được tiếp tục vô hạn khi `read` trả `0`.
- `ByteBuffer.flip()` chuyển từ chế độ ghi dữ liệu vào buffer sang chế độ lấy dữ liệu vừa đọc; sau khi xử lý, `clear()` chuẩn bị bộ đệm cho lần đọc tiếp. Đây là thao tác trạng thái buffer, không phải xóa nội dung bên dưới.
- `ByteArrayOutputStream` chỉ thu byte vào bộ nhớ để kiểm tra kết quả ví dụ. `new String(..., UTF_8)` chuyển byte thành văn bản; selector tự nó **không giải mã UTF-8**.
- `selected=1` là số key **duy nhất** được xử lý. Với một pipe chỉ đăng ký `OP_READ`, kết quả thực thi trên môi trường kiểm chứng là 1. Một hệ thống thực tế không được giả định lần thăm dò nào cũng có key ready.
- `IOException` từ `channel.read` được bao lại bằng `UncheckedIOException` vì phương thức `Consumer.accept` không khai báo checked exception; ngoại lệ từ callback sẽ được truyền ra caller.

Ví dụ là chương trình kiểm chứng một lần, không phải event loop mạng hoàn chỉnh. Với selector hoạt động lâu dài, cần tiếp tục thăm dò hoặc dùng blocking selection phù hợp, xử lý đóng kết nối, lỗi I/O, hủy key và giới hạn công việc trên mỗi vòng.

## 6. Vì sao callback “không chặn” vẫn có thể làm ứng dụng đứng lâu?

`selectNow(action)` không chờ thêm readiness nhưng **thực thi callback đồng bộ**. Ví dụ sau là ý tưởng cần tránh:

```java
// Phản ví dụ: callback chờ lâu (chỉ minh họa, không chạy).
selector.selectNow(key -> {
    doSlowDatabaseQuery(); // Một lời gọi có thể chặn lâu
});
```

Nếu `doSlowDatabaseQuery()` chậm, cả lời gọi `selectNow` cũng chậm. Theo Java API, callback chạy trong vùng đồng bộ trên selector và selected-key set. Vì vậy công việc kéo dài hoặc chờ khóa bên trong callback có thể kéo dài thời gian khóa, ảnh hưởng các luồng khác và gây nguy cơ deadlock.

Những nguyên tắc vẫn áp dụng:

1. Callback nên kiểm tra key và xử lý nhanh trạng thái I/O hiện tại; tránh gọi tác vụ mạng blocking khác, truy vấn DB nặng, `Thread.sleep` hoặc chờ `Future.get` trong callback.
2. **Không gọi lại** `selector.select()`, `selector.selectNow()` hoặc overload callback khác trên **cùng selector từ callback**. Selection không được bảo đảm reentrant; kết quả phụ thuộc implementation và có thể phá vỡ giả định của event loop.
3. Đảm bảo channel đã ở chế độ nonblocking và không tự chờ đến lúc đọc đủ N byte. Một lần `read` có thể đọc ít hơn số byte của thông điệp hoặc trả `0`.
4. Nếu cần công việc CPU nặng, sao chép trạng thái/dữ liệu cần thiết rồi chuyển sang tầng xử lý thích hợp sau khi rời callback; cẩn thận với vòng đời `SelectionKey` và dữ liệu chia sẻ qua nhiều luồng.
5. Bắt hoặc truyền ngoại lệ có chủ đích. Một `RuntimeException` ném ra từ callback (kể cả `UncheckedIOException`) được chuyển tới caller; đừng để vòng lặp I/O bỏ qua lỗi.

**Không đánh đồng selector nonblocking với “luôn chạy trong thời gian O(1)”**: số key sẵn sàng, công việc trong callback, khóa và lượng dữ liệu xử lý vẫn quyết định thời gian thực tế.

## 7. Xử lý key đúng: readiness, interest và luồng trạng thái

| Trạng thái key | Cách xử lý thường gặp | Lưu ý |
| --- | --- | --- |
| `key.isReadable()` | `SocketChannel.read(buffer)` hoặc `Pipe.SourceChannel.read(buffer)`. | `read()` có thể trả số dương, 0 hoặc -1; kiểm tra kết quả và quản lý phần thông điệp đọc dở. |
| `key.isWritable()` | Ghi từ `ByteBuffer` có dữ liệu còn lại. | Có thể chỉ ghi **một phần**; giữ phần còn lại và cập nhật `OP_WRITE` theo nhu cầu. |
| `key.isConnectable()` | Với `SocketChannel`, thường gọi `finishConnect()`. | Xử lý trạng thái/kết quả kết nối và lỗi; chưa chắc kết nối đã hoàn tất trước thao tác. |
| `key.isAcceptable()` | Với `ServerSocketChannel`, gọi `accept()` rồi cấu hình socket mới là nonblocking nếu muốn đăng ký tiếp. | Trong nonblocking mode, `accept()` có thể trả `null`; phải kiểm tra. |

Một key có thể quan tâm nhiều thao tác (nếu channel hỗ trợ), nhưng phải hiểu rằng callback có thể được gọi nhiều lần trên cùng key trong **một** selection, mỗi lần với tập `readyOps()` phù hợp. Không giả định callback luôn nhận mọi bit cùng lúc.

Khi không còn muốn ghi, loại `OP_WRITE` khỏi `interestOps` bằng thao tác cập nhật interest phù hợp, ví dụ:

```java
// Đoạn minh họa: key hợp lệ và thuộc channel có hỗ trợ OP_WRITE.
int withoutWrite = key.interestOps() & ~SelectionKey.OP_WRITE;
key.interestOps(withoutWrite);
```

Các thay đổi interest thực hiện trong lúc selection đang diễn ra được xét ở lần selection tiếp theo theo hợp đồng của `Selector`. Đừng coi một lần cập nhật interest là bảo đảm callback đang chạy sẽ lập tức thấy trạng thái khác. Khi channel đóng hoặc key bị `cancel()`, các cấu trúc selector có thể được dọn ở lần selection kế tiếp; kiểm tra tính hợp lệ trước khi thao tác.

## 8. Vòng lặp ứng dụng và lựa chọn cách đợi phù hợp

Nếu ứng dụng đồng thời cập nhật trạng thái khác (ví dụ tick của một chương trình, công việc trên hàng đợi nội bộ hoặc xử lý nhiều nguồn sự kiện), `selectNow(action)` giúp mỗi vòng lặp **thăm dò rồi nhường thời gian cho công việc khác**:

```java
// Pseudocode minh họa, không phải chương trình chạy độc lập.
while (running) {
    int readyCount = selector.selectNow(key -> handleReadyKey(key));
    performOtherWork();
    // Chọn cơ chế chờ/tái lên lịch phù hợp khi không có sự kiện.
}
```

Dùng `selectNow` trong vòng `while(true)` chạy liên tục không có chiến lược chờ có thể gây **busy spinning** và chiếm CPU dù chưa có key ready. Khi I/O là công việc chính, `select(action)` hoặc `select(action, timeout)` dương có thể phù hợp hơn. Với ứng dụng có event loop, tích hợp lịch thăm dò và chính sách nhường CPU thay vì tự thêm `Thread.sleep` bừa bãi vào callback.

Ngoài ra, `selectNow()` và `selectNow(action)` **xóa hiệu lực của lời gọi `wakeup()` trước đó** theo hợp đồng API. Nếu nhiều luồng cùng phối hợp đánh thức một selection đang chờ, hãy thiết kế thứ tự gọi `wakeup`, đặt tín hiệu và tiêu thụ tác vụ rõ ràng. `wakeup` không phải một hàng đợi sự kiện đếm được.

**Dùng thế nào khi chỉ có một channel?** `Selector` vẫn hoạt động được, nhưng lợi thế lớn nhất là tập trung theo dõi **nhiều** channel mà không cần một luồng chờ riêng cho mỗi channel. Với một thao tác I/O đơn giản, không nhất thiết phải thêm selector nếu một API trực tiếp dễ hiểu hơn.

## 9. `selectNow()` không callback: vì sao phải xử lý `selectedKeys()`?

Để tránh nhầm với overload Java 11, hãy nhìn phiên bản cũ, nơi caller phải tự duyệt selected-key set:

```java
// Đoạn minh họa trong phương thức có throws IOException.
// Cần import java.nio.channels.SelectionKey và java.util.Iterator.
int updated = selector.selectNow();
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove(); // Bỏ key đã xử lý khỏi selected-key set.
    if (!key.isValid()) {
        continue;
    }
    // Xử lý readiness của key.
}
```

Nếu quên `it.remove()`, các key đã chọn có thể vẫn còn trong set; tập đó không phải danh sách sự kiện mới được xóa tự động sau mỗi lượt xử lý. Điều này dẫn đến xử lý lặp/trạng thái khó hiểu.

Với `selector.selectNow(action)`, phần lớn logic duyệt tập được API bao lại. Tuy nhiên **không dùng số phần tử hiện có trong `selectedKeys()` để suy luận số callback hoặc số key mới xử lý**: hai dạng selection có cơ chế khác nhau và overload callback không hứa rằng selected-key set cuối cùng luôn rỗng. Tránh trộn hai mô hình trên cùng selector khi chưa định rõ cách quản lý selected-key set.

## 10. Ngoại lệ và đồng thời

| Trường hợp | Hành vi / cách xử lý |
| --- | --- |
| Selector đã đóng | `ClosedSelectorException` khi gọi selection. |
| Callback đóng chính selector | `ClosedSelectorException` khi callback hoàn thành, theo hợp đồng overload callback. |
| Lỗi hệ thống trong selection | Có thể ném `IOException`; caller phải xử lý theo ranh giới I/O. |
| `action == null` | `NullPointerException` do thiếu callback hợp lệ. |
| Callback ném exception | Exception được chuyển ra caller; một consumer không khai báo checked `IOException`, nên xử lý hoặc bao bằng `UncheckedIOException`. |
| Key bị hủy/đóng trong lúc chọn | Key có thể không hợp lệ khi callback nhận; kiểm tra `isValid()` và xử lý thay đổi trạng thái. |
| Các luồng cùng dùng selector | Selector và tập đăng ký có hợp đồng đồng thời; **selected-key set không thread-safe tổng quát**, và callback chạy dưới khóa selector/selected-key set. |
| `selectNow(action)` trả 0 | Chưa có key phù hợp sẵn sàng ở lần thăm dò; **không** đồng nghĩa EOF hay lỗi. |

Tránh đồng bộ khóa theo thứ tự ngược với các khóa mà selection đã sử dụng. Một callback giữ khóa của selector trong lúc chờ một luồng khác có thể gây deadlock. Thay vì gọi một selection khác đệ quy, hãy sắp xếp công việc để callback kết thúc rồi mới chọn tiếp ở vòng ngoài.

## 11. Những nhầm lẫn thường gặp

- **“`selectNow(action)` xử lý bất đồng bộ trên luồng khác.”** Sai. Consumer chạy ngay trong lời gọi hiện tại; có thể làm chậm caller.
- **“`selectNow` bảo đảm không chặn trong mọi dòng code.”** Sai. Chỉ không đợi readiness của selection; callback hoặc thao tác khác vẫn có thể chờ.
- **“`selectNow()` và `selectNow(action)` chỉ khác cách viết lambda.”** Sai. Dạng không callback quản lý `selectedKeys()`; dạng callback truyền key vào `Consumer` và không thêm key được chọn vào set cho caller tự duyệt.
- **“`selectNow(action)` trả số lần gọi `action`.”** Không bảo đảm. Giá trị trả về đếm key duy nhất; một key có thể được gọi callback nhiều lần nếu nhiều thao tác sẵn sàng.
- **“Không cần `configureBlocking(false)` vì đã gọi `selectNow`.”** Sai. Channel được đăng ký phải là nonblocking.
- **“`select(action, 0)` tương đương `selectNow(action)`.”** Sai. Timeout 0 của `select(action, long)` nghĩa là chờ vô thời hạn.
- **“`selectNow(action)` trả 0 tức là phía đối diện đã đóng kênh.”** Sai. Có thể đơn giản chưa có sự kiện sẵn sàng; khi đọc thật, `-1` là tín hiệu EOF của `read`.
- **“Cứ thấy `OP_WRITE` là bật vĩnh viễn để xử lý cho nhanh.”** Không hợp lý. Kênh có thể gần như luôn writable, gây vòng lặp bận.
- **“Bắt ngoại lệ trong callback rồi bỏ qua để chọn tiếp.”** Dễ che lỗi I/O và mất đồng bộ trạng thái. Hãy áp dụng chính sách lỗi cụ thể cho channel và kết nối.
- **“Gọi `selector.selectNow()` lại từ callback cũng an toàn.”** Không có bảo đảm reentrant; tránh thao tác này.

## 12. Checklist triển khai thực tế

1. Dùng **`Selector.selectNow(Consumer<SelectionKey>)`** khi cần thăm dò readiness mà không chờ và muốn xử lý trực tiếp qua callback trong cùng lượt selection.
2. Mở selector đúng vòng đời; cấu hình channel **nonblocking trước khi register** cùng những `interestOps` được hỗ trợ.
3. Trong callback kiểm tra `key.isValid()` và các readiness flag; xử lý `read == 0`, `read == -1`, partial write và việc hủy key.
4. Giữ callback ngắn, không tái gọi selection trên cùng selector, không chờ I/O blocking hoặc tác vụ nặng trong vùng khóa.
5. Hiểu rằng số trả về là **số key duy nhất**; không suy luận callback count hay `selectedKeys().size()` từ số đó.
6. Khi trả về 0, ứng dụng cần kế hoạch tiếp tục công việc và lựa chọn chờ hợp lý để tránh busy loop.
7. Dùng overload không callback thì tự duyệt `selectedKeys()` và loại key đã xử lý; không phụ thuộc tập đó khi dùng overload callback.
8. Xử lý `IOException` và ngoại lệ callback; đóng selector/channel bằng try-with-resources và giữ rõ quyền sở hữu tài nguyên.

### Tài liệu chính thức

- [Java SE 11 — `Selector`: `selectNow(Consumer<SelectionKey>)` (Since 11), callback semantics, concurrency](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 25 — `Selector`: hợp đồng hiện hành cho `selectNow` và callback](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 11 — `SelectionKey`: `readyOps`, `interestOps`, trạng thái hợp lệ](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Java SE 11 — `SelectableChannel`: `configureBlocking` và đăng ký](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/SelectableChannel.html)
