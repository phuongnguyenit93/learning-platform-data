# Tuần tự, truy cập ngẫu nhiên, blocking và non-blocking trong Java I/O

Khi thiết kế thao tác nhập/xuất (I/O), có hai câu hỏi khác nhau:

1. **Truy cập dữ liệu theo thứ tự nào?** Đọc/ghi **tuần tự** (sequential) hay có thể **nhảy tới vị trí bất kỳ** (random access)?
2. **Lời gọi phải đợi đến lúc nào?** Thao tác **blocking** có thể giữ luồng đang gọi để chờ; thao tác **non-blocking** trả quyền điều khiển khi chưa thể xử lý ngay.

Đây là **hai trục phân loại độc lập về khái niệm**, không phải bốn loại I/O loại trừ nhau. Một chương trình có thể đọc tuần tự bằng API blocking, hoặc xử lý dữ liệu tuần tự trên kết nối mạng non-blocking. Khả năng kết hợp cụ thể phụ thuộc thiết bị và API: Java NIO không cung cấp chế độ `configureBlocking(false)` cho `FileChannel` của tệp thông thường.

## 1. Tuần tự (sequential) và truy cập ngẫu nhiên (random access)

### 1.1. Truy cập tuần tự

Với truy cập tuần tự, chương trình xử lý dữ liệu theo dòng chảy từ vị trí hiện tại tới vị trí tiếp theo. Ví dụ: đọc từng byte, từng khối byte hoặc từng dòng văn bản; ghi liên tiếp vào cuối hoặc vị trí hiện tại của luồng.

- `InputStream` / `OutputStream` làm việc với byte; `Reader` / `Writer` làm việc với ký tự.
- `BufferedInputStream`, `BufferedReader` giảm số lần truy cập tầng dưới nhờ bộ đệm. `BufferedReader.readLine()` phù hợp cho văn bản chia dòng.
- `Files.newInputStream(path)`, `Files.newBufferedReader(path, charset)` là cách mở luồng/tệp thông dụng.
- `mark()` / `reset()` trên một số `InputStream` chỉ cho quay lại dấu mốc theo điều kiện hỗ trợ; **không tương đương** với việc đặt con trỏ tùy ý vào mọi offset.
- "Tuần tự" nói về **cách truy cập**, không đảm bảo dữ liệu nằm liên tiếp vật lý trên đĩa hay việc đọc luôn nhanh.

Ví dụ Java 17+ độc lập, tạo tệp UTF-8 tạm, đọc từng dòng và dọn dẹp tệp:

```java
// SequentialDemo.java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SequentialDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("sequential-", ".txt");
        try {
            Files.writeString(file, "dòng 1\ndòng 2\n", StandardCharsets.UTF_8);

            try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SequentialDemo.java
java SequentialDemo
```

Đầu ra:

```text
dòng 1
dòng 2
```

`readLine()` tiến dần qua nội dung; `null` báo hết tệp. Nó trả về phần nội dung dòng, không kèm dấu xuống dòng. `try-with-resources` đóng reader; `finally` dọn tệp tạm kể cả khi có lỗi.

### 1.2. Truy cập ngẫu nhiên

Random access cho phép đặt một **vị trí logic (offset)** rồi đọc/ghi tại đó mà không phải đọc lần lượt toàn bộ phần trước. Đây là kỹ thuật thích hợp cho chỉ mục cố định, bản ghi kích thước cố định, cập nhật một vùng trong tệp hoặc đọc header/footer.

Trong Java có ba API tiêu biểu:

| API | Vị trí và ý nghĩa |
| --- | --- |
| `RandomAccessFile` | `seek(long)` di chuyển con trỏ tệp; `getFilePointer()`, `length()`, `setLength()`; hỗ trợ đọc/ghi kiểu nguyên thủy. |
| `SeekableByteChannel` | Trừu tượng channel có `position()` và `position(long)`; các thao tác đọc/ghi tương đối dùng vị trí hiện tại. |
| `FileChannel` | Channel cho tệp; hỗ trợ `position(long)` và `read(ByteBuffer, long)` / `write(ByteBuffer, long)` tại offset chỉ định mà **không đổi vị trí hiện tại** của channel. |

Vị trí trong các API này được tính bằng **byte**, không phải số ký tự Unicode hay số dòng. Khi dùng văn bản UTF-8 có ký tự nhiều byte, không thể giả định `seek(10)` tương ứng ký tự thứ 11. Đồng thời, random access chỉ có ý nghĩa khi nguồn dữ liệu và API cho phép seek; một TCP socket không thể nhảy ngược tới byte cũ của luồng mạng.

Ví dụ dùng `RandomAccessFile` với ba số nguyên `int` (mỗi số 4 byte):

```java
// RandomAccessDemo.java
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class RandomAccessDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("random-", ".bin");
        try {
            try (RandomAccessFile raf = new RandomAccessFile(file.toFile(), "rw")) {
                raf.setLength(0);
                raf.writeInt(10);  // byte 0..3
                raf.writeInt(20);  // byte 4..7
                raf.writeInt(30);  // byte 8..11

                raf.seek(4);
                System.out.println("second = " + raf.readInt());

                raf.seek(8);
                raf.writeInt(99);  // ghi đè số thứ ba
                raf.seek(0);
                System.out.println("values = " +
                        raf.readInt() + ", " + raf.readInt() + ", " + raf.readInt());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac RandomAccessDemo.java
java RandomAccessDemo
```

Đầu ra:

```text
second = 20
values = 10, 20, 99
```

`seek(4)` đi thẳng tới số nguyên thứ hai; `seek(8)` đi tới số thứ ba. `writeInt` / `readInt` dùng biểu diễn nhị phân 4 byte theo thứ tự big-endian được xác định bởi `DataOutput` / `DataInput`, vì vậy đây **không phải** ví dụ xử lý số ở dạng chuỗi. Với bản ghi có độ dài biến đổi, chỉ `seek()` thôi chưa đủ: cần cấu trúc chỉ mục hoặc định dạng lưu trữ biết offset của bản ghi.

Với `FileChannel`, phân biệt hai kiểu:

```java
channel.position(100);       // đổi vị trí logic của channel
channel.read(buffer);        // đọc từ vị trí hiện tại, cập nhật vị trí
channel.read(buffer, 500);   // đọc tại byte 500, không đổi vị trí hiện tại
```

Ba dòng trên là **đoạn minh họa**, giả định `channel` đã mở và `buffer` còn chỗ trống. `read` có thể đọc ít byte hơn yêu cầu; khi cần đủ một khối, phải lặp và kiểm tra EOF. Các API seek không tự làm I/O thành non-blocking.

## 2. Blocking và non-blocking thực sự có nghĩa gì?

### 2.1. Blocking I/O

Với I/O blocking, lời gọi đang thực hiện **có thể chờ** cho đến khi dữ liệu đến, kết nối được chấp nhận, tài nguyên sẵn sàng hoặc thao tác hoàn tất / thất bại. Trong thời gian đó, luồng Java gọi API chưa tiếp tục chạy các câu lệnh phía sau.

Ví dụ:

- `InputStream.read()` trên socket có thể chờ peer gửi dữ liệu, đóng đầu ra hoặc phát sinh lỗi.
- `ServerSocket.accept()` và `ServerSocketChannel.accept()` ở chế độ blocking có thể chờ kết nối đến.
- `SocketChannel.read(ByteBuffer)` ở chế độ mặc định blocking có thể chờ dữ liệu khi buffer còn chỗ trống.
- `FileChannel.read` / `write` là thao tác đồng bộ và có thể chặn trong khi truy cập hệ thống tệp, dù thuộc gói `java.nio`.

"Blocking" **không có nghĩa mỗi lời gọi luôn đợi lâu**: dữ liệu đã sẵn sàng có thể trả kết quả ngay. Cũng không có nghĩa `read` luôn điền đầy buffer; số byte trả về phải được kiểm tra. Đường đọc có thể kết thúc bằng EOF (`-1`) hoặc lỗi. Timeout/cơ chế hủy của từng API khác nhau; không thể giả định mọi lời gọi blocking đều có cùng cách ngắt.

### 2.2. Non-blocking I/O

Ở chế độ non-blocking, thao tác trên channel được hỗ trợ có thể trả về ngay cả khi chưa đọc/ghi được dữ liệu. Mã ứng dụng tự quyết định khi nào thử lại hoặc đăng ký **sự kiện sẵn sàng** với `Selector`.

Java NIO áp dụng `configureBlocking(false)` cho các `SelectableChannel` như:

- `SocketChannel` — giao tiếp TCP;
- `ServerSocketChannel` — nhận kết nối TCP;
- `DatagramChannel` — gửi/nhận UDP.

Ví dụ `SocketChannel.read(dst)` khi `dst` còn chỗ:

| Kết quả | Cách hiểu |
| --- | --- |
| `n > 0` | Đã đọc `n` byte; chưa chắc đủ một thông điệp. |
| `n == 0` | Hiện chưa có byte nào được đọc; thường gặp ở chế độ non-blocking, không phải EOF. |
| `n == -1` | Đã tới cuối luồng đầu vào của kết nối. |
| Ném exception | Có lỗi I/O; cần xử lý/đóng tài nguyên phù hợp. |

Đối với `SocketChannel.write(src)`, một lần ghi có thể xử lý **ít hơn** `src.remaining()` byte, kể cả trong hoàn cảnh không được giả định ghi đầy. Nếu non-blocking trả `0`, giữ phần buffer chưa gửi và chờ lần sẵn sàng tiếp theo; **không bỏ dữ liệu chưa gửi**.

Lưu ý: `Selector.select()` **có thể tự blocking** để đợi sự kiện dù các channel đã đăng ký ở chế độ non-blocking. Sử dụng `selectNow()` hoặc `select(timeout)` khi cần chính sách chờ khác. Non-blocking giúp một thread quản lý nhiều kết nối bằng sự kiện; bản thân nó không bảo đảm nhanh hơn cho mọi khối lượng công việc.

## 3. Ma trận hai trục và lựa chọn API

| Kiểu truy cập | Blocking/synchronous | Non-blocking/asynchronous |
| --- | --- | --- |
| **Tuần tự** | `BufferedReader` đọc dòng từ tệp; `InputStream` trên socket; `SocketChannel` blocking. | `SocketChannel` / `DatagramChannel` non-blocking + `Selector` xử lý luồng byte hoặc datagram theo sự kiện. |
| **Ngẫu nhiên** | `RandomAccessFile`, `SeekableByteChannel`, `FileChannel` truy cập offset của tệp. | Đối với tệp thông thường, Java không cho chuyển `FileChannel` thành selectable non-blocking. `AsynchronousFileChannel` cung cấp API bất đồng bộ có vị trí, nhưng đó là **mô hình completion** riêng, không phải `SocketChannel.configureBlocking(false)`. |

Hai thuộc tính cần nhìn độc lập khi đọc tên thư viện:

- **`java.io` và `java.nio` không đồng nghĩa tuyệt đối với blocking và non-blocking.** NIO bao gồm `FileChannel` đồng bộ, `SocketChannel` có hai chế độ và `AsynchronousFileChannel`.
- **`AsynchronousFileChannel.read(buffer, position)`** trả `Future<Integer>` hoặc nhận `CompletionHandler`. Nếu gọi `future.get()` thì luồng đang gọi có thể chờ. Việc API bất đồng bộ không bảo đảm thao tác đĩa luôn chạy không cần thread nền.
- **Memory-mapped file** (`FileChannel.map`) hỗ trợ truy cập vị trí qua buffer ánh xạ nhưng lỗi trang / truy cập dữ liệu vẫn có thể chờ I/O; không nên gắn nhãn "luôn non-blocking".
- Một lần đọc `BufferedReader` tuần tự vẫn có thể dựa trên tệp hỗ trợ random access; đây là lựa chọn **cách chương trình truy cập**, không phải thuộc tính bất biến của mọi tệp.

## 4. `Selector`: sự kiện sẵn sàng trong non-blocking networking

Luồng xử lý cơ bản:

1. Mở một `SelectableChannel`, gọi `configureBlocking(false)`.
2. Đăng ký channel với `Selector` bằng các interest operations thích hợp (`OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE`).
3. Gọi `select()`/`select(timeout)` để chờ; duyệt `selectedKeys()` và **loại key đã xử lý** khỏi tập selected.
4. Với kết nối nhận được, cấu hình socket mới sang non-blocking rồi đăng ký `OP_READ`.
5. Khi readable, đọc vào `ByteBuffer`; xử lý `> 0`, `0`, `-1`; lưu phần thông điệp chưa hoàn chỉnh. Khi writable, tiếp tục ghi phần còn lại của buffer.
6. Hủy key/đóng channel khi xong hoặc có lỗi; quản lý timeout và giới hạn bộ đệm khi chạy thực tế.

Ví dụ tự chạy trên loopback, **server ở chế độ non-blocking** và dùng `Selector`. Client trong ví dụ cố ý dùng chế độ blocking mặc định để gửi thông điệp ngắn; như vậy thể hiện rõ chế độ I/O do **từng channel** quyết định:

```java
// NonBlockingDemo.java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Iterator;

public class NonBlockingDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open();
             Selector selector = Selector.open()) {

            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            try (SocketChannel client = SocketChannel.open()) {
                client.connect(server.getLocalAddress());

                ByteBuffer outgoing =
                        ByteBuffer.wrap("ping".getBytes(StandardCharsets.UTF_8));
                while (outgoing.hasRemaining()) {
                    client.write(outgoing);
                }
                client.shutdownOutput();

                ByteArrayOutputStream received = new ByteArrayOutputStream();
                long deadline = System.nanoTime() + Duration.ofSeconds(5).toNanos();
                boolean eof = false;

                while (!eof && System.nanoTime() < deadline) {
                    selector.select(1000);
                    Iterator<SelectionKey> keys = selector.selectedKeys().iterator();

                    while (keys.hasNext()) {
                        SelectionKey key = keys.next();
                        keys.remove();

                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ);
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer = (SocketChannel) key.channel();
                            ByteBuffer buffer = ByteBuffer.allocate(32);
                            int n;

                            while ((n = peer.read(buffer)) > 0) {
                                buffer.flip();
                                received.write(buffer.array(), 0, buffer.remaining());
                                buffer.clear();
                            }
                            if (n == -1) {
                                peer.close();
                                eof = true;
                            }
                        }
                    }
                }

                if (!eof) {
                    throw new IOException("Timeout waiting for EOF");
                }
                System.out.println(received.toString(StandardCharsets.UTF_8));
            }
        }
    }
}
```

```bash
javac NonBlockingDemo.java
java NonBlockingDemo
```

Đầu ra trong điều kiện loopback hoạt động bình thường:

```text
ping
```

Diễn giải: hệ điều hành cấp một cổng loopback còn trống; `OP_ACCEPT` báo có kết nối cần nhận; peer được chuyển sang non-blocking và đăng ký `OP_READ`. Client gửi bốn byte và `shutdownOutput()`, vì vậy server có thể quan sát EOF `-1` sau dữ liệu. Dù `selector.select(1000)` có thể chờ, `server.accept()` và `peer.read()` trên server ở chế độ non-blocking sẽ không chờ dữ liệu/kết nối theo cơ chế blocking. Ví dụ có deadline để tránh vòng lặp vô hạn khi chạy trong môi trường mạng bất thường.

Ở chương trình thật, không thể coi một lần `read` là một thông điệp TCP. TCP là **byte stream**, không giữ ranh giới các lần `write`. Hãy xác định khung thông điệp (độ dài đầu bản tin, dấu phân cách, hoặc giao thức có header), giữ buffer qua nhiều sự kiện và chỉ giải mã ký tự UTF-8 khi đã gom đủ dãy byte. Với dữ liệu lớn, không cấp phát `ByteBuffer` mới cho mọi sự kiện như ví dụ minh họa; quản lý buffer theo connection.

### Các điểm dễ gây lỗi khi dùng NIO

- **`ByteBuffer.flip()`** chuyển từ trạng thái ghi vào buffer sang đọc dữ liệu trong buffer; **`clear()`** chuẩn bị ghi lại nhưng không xóa byte vật lý. Nếu có dữ liệu đọc dở, dùng **`compact()`** để giữ phần chưa xử lý.
- Non-blocking `read() == 0` không báo EOF; không dùng vòng `while (read(...) == 0) {}` chạy liên tục vì tốn CPU. Thường đăng ký `OP_READ` và chờ sự kiện mới.
- Chỉ bật `OP_WRITE` khi thật sự còn dữ liệu chờ gửi. Kết nối thường xuyên writable, đăng ký `OP_WRITE` vô điều kiện dễ khiến `select()` liên tục thức dậy (busy loop).
- `OP_CONNECT` đi với `SocketChannel` kết nối non-blocking: `connect()` có thể trả `false`, khi sẵn sàng kết nối phải kiểm tra `finishConnect()`.
- Sự kiện "readable" / "writable" biểu thị mức độ **sẵn sàng tại thời điểm quan sát**, không bảo đảm đọc đầy buffer hay truyền xong bản tin. Kết nối có thể đóng/lỗi giữa lần báo sự kiện và thao tác.
- Không trộn `InputStream` lấy từ socket với logic selector của cùng socket một cách tùy tiện; điều phối một mô hình đọc/ghi rõ ràng cho mỗi kết nối.

## 5. So sánh ưu/nhược và tình huống chọn lựa

| Nhu cầu | Gợi ý | Vì sao |
| --- | --- | --- |
| Đọc log hoặc CSV từ đầu đến cuối | `BufferedReader` / `Files.newBufferedReader` | Đọc tuần tự, ít trạng thái, dễ kết hợp xử lý dòng. |
| Cập nhật bản ghi nhị phân tại offset đã biết | `RandomAccessFile` hoặc `FileChannel` | Truy cập trực tiếp vị trí byte, tránh đọc toàn bộ tệp trước. |
| Sao chép tệp lớn theo từng khối | Luồng đệm hoặc `FileChannel` | Xử lý dữ liệu theo khối, không cần nạp cả tệp vào RAM. |
| Server TCP có nhiều kết nối cần xử lý bằng ít thread I/O | `SocketChannel` non-blocking + `Selector` | Một event loop có thể multiplex nhiều channel; đòi hỏi quản lý trạng thái và buffer. |
| Ứng dụng nhỏ, ít kết nối, muốn code dễ hiểu | Socket blocking hoặc thư viện trừu tượng mức cao | Luồng điều khiển tuyến tính thường dễ viết và kiểm thử. |
| Đọc nhiều vùng tệp qua API completion | `AsynchronousFileChannel` với `CompletionHandler` / `Future` | Biết offset và nhận kết quả khi hoàn tất mà không phải tự thiết kế selector cho tệp. |

**Hiệu năng không quyết định chỉ bởi nhãn.** Random access có thể tăng seek / random disk I/O và phá tính cục bộ bộ nhớ; đọc tuần tự thường tận dụng được readahead. Non-blocking giúp giảm số thread chờ khi phải quản lý nhiều socket, nhưng state machine, selector, framing và backpressure phức tạp hơn. Đo workload thực tế (số kết nối, kích thước buffer, độ trễ, throughput, mức sử dụng CPU/RAM) trước khi thay đổi thiết kế.

## 6. Các nhầm lẫn thường gặp và cách kiểm tra

1. **“Dùng `java.nio` là non-blocking.”** Sai: `FileChannel` và nhiều API NIO vẫn thực hiện I/O đồng bộ; phải kiểm tra channel có phải `SelectableChannel` và trạng thái `isBlocking()` hay không.
2. **“Random access làm thao tác không phải đợi đĩa.”** Sai: seek chỉ thay đổi vị trí logic; truy xuất dữ liệu có thể vẫn blocking.
3. **“Non-blocking read trả `0` tức là kết thúc stream.”** Sai: `-1` mới biểu thị EOF đối với `SocketChannel.read`.
4. **“`read(buffer)` luôn đọc đủ số byte yêu cầu.”** Sai: số byte đọc được có thể ít hơn dung lượng đích; phải dựa vào giá trị trả về, trạng thái buffer và giao thức.
5. **“Selector tự chạy mã khi dữ liệu đến.”** Sai: ứng dụng phải chạy event loop, duyệt selected keys, đọc/ghi và quản lý trạng thái.
6. **“`Future.get()` là cách đọc file không bao giờ chặn.”** Sai: lời gọi `get()` có thể chờ; muốn xử lý bất đồng bộ cần cấu trúc chương trình cho phép tiếp tục công việc khác hoặc dùng completion callback.
7. **“Seek theo số ký tự giống seek theo byte.”** Sai với UTF-8 và nhiều encoding khác; cần chỉ mục byte hoặc giải mã tuần tự đúng cách.

Tự kiểm tra: (a) Muốn đọc dòng 1 đến dòng cuối của một file văn bản, nên dùng kiểu truy cập nào? **Tuần tự**. (b) Muốn thay byte ở offset 4096 của file nhị phân? **Truy cập ngẫu nhiên** qua API seekable. (c) Một `SocketChannel` non-blocking trả `0` khi đọc? **Chưa đọc được byte nào tại thời điểm đó**, giữ trạng thái và đợi readiness. (d) `FileChannel.position(4096)` có khiến lần đọc tiếp theo tự non-blocking? **Không**.

Điểm cần giữ lại: **sequential/random access trả lời “đọc ở đâu”; blocking/non-blocking trả lời “lời gọi có chờ hay không”.** Chọn API dựa trên bản chất nguồn dữ liệu và yêu cầu xử lý, rồi kiểm tra kết quả từng thao tác đọc/ghi thay vì suy từ tên lớp.
