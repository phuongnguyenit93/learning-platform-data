# `FileChannel` không phải `SelectableChannel` trong Java NIO

## 1. Mục tiêu và vấn đề thực tế

`java.nio.channels.FileChannel` là API quan trọng để đọc/ghi tệp với `ByteBuffer`, di chuyển vị trí trong tệp, truy cập theo offset, truyền dữ liệu giữa các channel và ánh xạ file vào bộ nhớ. Nhưng **`FileChannel` không phải là `SelectableChannel`**, nên không thể đăng ký trực tiếp vào `Selector` để nhận sự kiện `OP_READ`, `OP_WRITE` như `SocketChannel` hoặc `Pipe.SourceChannel`.

Đây là giới hạn **về hợp đồng kiểu của Java NIO**, không phải thiếu import hay quên gọi một phương thức khởi tạo nào. Một số nhầm lẫn xuất phát từ việc cả hai đều chứa chữ “channel”, nhưng chúng giải quyết hai nhóm nhu cầu khác nhau.

Sau bài, bạn có thể:

1. Giải thích vì sao `FileChannel` không có `register(Selector, ops)` hay `configureBlocking(false)`.
2. Phân biệt file I/O dùng offset với readiness-based I/O trên socket/pipe.
3. Viết và chạy một chương trình chứng minh `FileChannel` không triển khai `SelectableChannel` nhưng có khả năng truy cập tệp ngẫu nhiên.
4. Đăng ký **channel thực sự selectable** với `Selector`, sử dụng `SelectionKey.OP_READ` đúng cách.
5. Chọn giải pháp phù hợp nếu cần xử lý file mà không khóa luồng nghiệp vụ: `AsynchronousFileChannel`, tác vụ thực thi ở thread khác hoặc `WatchService` cho thông báo thay đổi thư mục.
6. Tránh hiểu sai EOF của file, trạng thái “ready” trên selector và lời hứa của các hàm truyền dữ liệu tối ưu.

Ví dụ nhắm đến **Java 17+**, dùng Java SE và không cần Spring hoặc thư viện ngoài.

## 2. Hai họ channel có mục đích khác nhau

### `FileChannel`: làm việc với byte tại vị trí trong tệp

`FileChannel` thuộc `java.nio.channels`, kế thừa `AbstractInterruptibleChannel` và triển khai những giao diện liên quan đến byte I/O, trong đó có:

- `SeekableByteChannel`: `position()`, `position(long)`, `size()`, `truncate(long)`.
- `ReadableByteChannel` và `WritableByteChannel`: đọc/ghi qua `ByteBuffer` khi channel được mở với tùy chọn cho phép.
- `ScatteringByteChannel` và `GatheringByteChannel`: đọc/ghi qua nhiều `ByteBuffer`.
- Các khả năng riêng: `read(dst, position)`, `write(src, position)`, `transferTo`, `transferFrom`, `map`, `lock`, `tryLock`, `force`.

Một `FileChannel` thường được mở bằng:

```java
try (FileChannel file = FileChannel.open(
        path,
        StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(4096);
    int n = file.read(buffer);
}
```

Đoạn này là snippet cần khai báo `path`, import `FileChannel`, `ByteBuffer`, `StandardOpenOption` và xử lý `IOException`. `n` là số byte thực đọc; có thể nhỏ hơn dung lượng buffer. Khi đã đến cuối file, `read` trả `-1`.

### `SelectableChannel`: chọn kênh có trạng thái sẵn sàng I/O

`SelectableChannel` là một lớp trừu tượng cho các channel có thể đăng ký với `Selector` để theo dõi một tập **operation readiness**. Nó cung cấp các API đặc trưng:

- `configureBlocking(boolean)` / `isBlocking()`: chọn blocking hoặc nonblocking, nếu kênh hỗ trợ.
- `validOps()`: tập bit operation có thể đăng ký cho channel cụ thể.
- `register(Selector, int)`: đăng ký nhận thông báo qua một `SelectionKey`.
- `keyFor(Selector)` và `isRegistered()`: kiểm tra đăng ký.

Những loại channel thường gặp có thể chọn là:

| Loại | Operation thường hợp lệ | Công dụng |
| --- | --- | --- |
| `SocketChannel` | `OP_CONNECT`, `OP_READ`, `OP_WRITE` | Kết nối TCP |
| `ServerSocketChannel` | `OP_ACCEPT` | Chấp nhận TCP connection mới |
| `DatagramChannel` | `OP_READ`, `OP_WRITE` | UDP |
| `Pipe.SourceChannel` | `OP_READ` | Đọc byte từ pipe |
| `Pipe.SinkChannel` | `OP_WRITE` | Ghi byte vào pipe |
| **`FileChannel`** | **Không có `SelectionKey`/`validOps()` của `SelectableChannel`** | **I/O tệp; không register selector** |

Các operation và trạng thái thực tế phụ thuộc kênh. Ví dụ `OP_ACCEPT` chỉ có ý nghĩa trên `ServerSocketChannel`, không phải chỉ vì mọi channel cùng thuộc package NIO mà đều nhận cùng mọi bit.

## 3. Sơ đồ quan hệ kiểu: tên giống nhau nhưng không cùng nhánh

```text
                      Channel (interface)
                         |
          +--------------+----------------------+
          |                                     |
   ByteChannel /                            các Channel khác
   SeekableByteChannel                         |
          |                              SelectableChannel
      FileChannel                            (abstract)
   (abstract class)                              |
     | không kế thừa                   AbstractSelectableChannel
     | SelectableChannel                       |
     +--------------------X              SocketChannel,
                                          ServerSocketChannel,
                                          DatagramChannel,
                                          Pipe.SourceChannel,
                                          Pipe.SinkChannel
```

Sơ đồ cố ý chỉ thể hiện những **mối quan hệ liên quan đến tính selectable**, không phải toàn bộ kế thừa của tất cả giao diện. `FileChannel` và `SelectableChannel` đều thuộc cơ chế `Channel`, nhưng `FileChannel` không kế thừa hay triển khai API của `SelectableChannel`.

Một channel **có thể vừa `ReadableByteChannel` vừa selectable** (ví dụ `SocketChannel`); vậy phân loại theo “có `read(ByteBuffer)`” là chưa đủ. Điều quyết định để `register` là đối tượng thuộc **`SelectableChannel`** và channel có operation phù hợp.

### Điều không thể làm

```java
FileChannel file = FileChannel.open(path, StandardOpenOption.READ);

// Các dòng sau CỐ Ý SAI, không biên dịch:
// file.configureBlocking(false);
// file.register(selector, SelectionKey.OP_READ);
// file.validOps();
```

Đoạn trên chỉ là **mã minh họa lỗi**: `FileChannel` không khai báo các phương thức ấy. Cast ép sang `SelectableChannel` cũng không biến đổi đối tượng, và sẽ thất bại nếu cố làm qua một tham chiếu kiểu `Channel` hoặc `Object`. Không có overload của `Selector.register` nhận `FileChannel`.

Đăng ký một `SelectableChannel` đang ở **blocking mode** cũng không đúng: thao tác `register` yêu cầu nonblocking và có thể ném `IllegalBlockingModeException`. Nhưng với `FileChannel`, bạn còn chưa đến bước kiểm tra blocking mode vì bản thân kiểu kênh đã không selectable.

## 4. “Blocking I/O” khác với “selector readiness”

**Blocking call** nghĩa là luồng gọi một thao tác có thể phải chờ thao tác hoàn thành hoặc gặp lỗi. Với file, hệ điều hành có thể cần đọc block từ thiết bị, xử lý cache, mạng filesystem hoặc đồng bộ metadata. Thời gian có thể rất ngắn, nhưng vẫn không thể coi mọi `FileChannel.read()/write()` là không bao giờ chờ.

**Selector readiness** là cơ chế chờ một hoặc nhiều `SelectableChannel` xuất hiện operation được báo là sẵn sàng; ví dụ socket có byte đang đợi để đọc. Readiness không hứa rằng một lệnh I/O bất kỳ sẽ xử lý hết dữ liệu ngay trong một lần, không thay thế kiểm tra `read()/write()`, và không tự cho biết một message của giao thức ứng dụng đã nhận đủ.

Đối với regular file, hệ điều hành có thể báo nó sẵn sàng đọc trong nhiều tình huống, nhưng khái niệm readiness thường không hữu ích theo cùng cách với socket. **Lý do có thể diễn giải như vậy không phải là hợp đồng thay cho API Java**: kết luận đúng, ổn định và đủ dùng để lập trình Java là **`FileChannel` không triển khai `SelectableChannel`**.

So sánh ba thuật ngữ dễ lẫn:

| Câu hỏi | Nơi trả lời | Ý nghĩa |
| --- | --- | --- |
| Tệp có bao nhiêu byte và đang đọc từ offset nào? | `FileChannel.size()`, `position()` | Trạng thái tệp/đường đọc |
| Socket/pipe có thể đọc ngay theo mô hình readiness không? | `Selector`, `SelectionKey.isReadable()` | Trạng thái sẵn sàng thao tác trên selectable channel |
| Một thao tác tệp hoàn thành khi nào? | `FileChannel.read()` trả về; hoặc `Future/CompletionHandler` của `AsynchronousFileChannel` | Kết quả/completion của thao tác |

Một sự kiện `OP_READ` **không** đồng nghĩa EOF, “file changed” hoặc “đọc đủ record”. Không thiết kế ứng dụng tail log bằng cách thử `fileChannel.register(selector, OP_READ)`.

## 5. Ví dụ Java 17+ chạy được: chứng minh `FileChannel` không selectable

Lưu dưới tên **`FileChannelNotSelectableDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.channels.Channel;
import java.nio.channels.FileChannel;
import java.nio.channels.SelectableChannel;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelNotSelectableDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("not-selectable-", ".txt");

        try {
            Files.writeString(file, "ABC", StandardCharsets.US_ASCII);

            try (FileChannel channel =
                         FileChannel.open(file, StandardOpenOption.READ)) {

                // Kiểm tra runtime qua giao diện chung Channel.
                Channel asChannel = channel;

                System.out.println("selectable="
                        + (asChannel instanceof SelectableChannel));
                System.out.println("seekable="
                        + (asChannel instanceof SeekableByteChannel));
                System.out.println("size=" + channel.size());

                channel.position(1);
                ByteBuffer buffer = ByteBuffer.allocate(2);
                int read = channel.read(buffer);

                buffer.flip();
                byte[] bytes = new byte[buffer.remaining()];
                buffer.get(bytes);

                System.out.println("bytesRead=" + read);
                System.out.println("text="
                        + new String(bytes, StandardCharsets.US_ASCII));
                System.out.println("position=" + channel.position());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac FileChannelNotSelectableDemo.java
java FileChannelNotSelectableDemo
```

Stdout khi các thao tác tệp thành công:

```text
selectable=false
seekable=true
size=3
bytesRead=2
text=BC
position=3
```

Lý giải:

1. `Files.writeString` tạo nội dung ASCII chính xác 3 byte: `A`, `B`, `C`.
2. Biến `asChannel` có kiểu giao diện chung `Channel`, nên phép `instanceof SelectableChannel` là kiểm tra hợp lệ tại runtime. Kết quả `false` vì `FileChannel` không có khả năng selectable.
3. `SeekableByteChannel` là giao diện mà `FileChannel` hỗ trợ, nên kết quả `true`.
4. `channel.position(1)` đưa vị trí đọc đến byte thứ hai (`B`). `read(buffer)` đọc hai byte `BC`, trả `2` và tăng file position lên `3`.
5. `buffer.flip()` đổi buffer từ pha nhận byte sang pha đọc byte. Sau đó `get(bytes)` lấy đúng số byte mới nạp.
6. `try-with-resources` đóng channel trước khi xóa file tạm.

Không có dòng nào cần `Selector` trong tác vụ đọc tệp này. Nếu mục tiêu là xử lý dữ liệu tệp theo vị trí, `FileChannel` đã cung cấp đúng API.

## 6. Ví dụ selectable thực sự: `Pipe.SourceChannel` và `Selector`

Để hiểu sự khác biệt, hãy dùng `Pipe.SourceChannel`. Nó là `SelectableChannel`, có thể đưa về nonblocking mode và đăng ký `OP_READ`.

Tạo file **`PipeSelectorDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class PipeSelectorDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            // Ghi byte vào pipe để phía source có dữ liệu đọc.
            ByteBuffer outgoing = ByteBuffer.wrap(
                    "ready".getBytes(StandardCharsets.US_ASCII));
            while (outgoing.hasRemaining()) {
                sink.write(outgoing);
            }

            int n = selector.select(3000); // tối đa 3 giây
            if (n == 0) {
                throw new IOException("No readiness event in time");
            }

            Iterator<SelectionKey> it =
                    selector.selectedKeys().iterator();

            while (it.hasNext()) {
                SelectionKey key = it.next();
                it.remove(); // xử lý xong key của lượt chọn này

                if (key.isValid() && key.isReadable()) {
                    ByteBuffer incoming = ByteBuffer.allocate(16);
                    int count = source.read(incoming);
                    if (count > 0) {
                        incoming.flip();
                        byte[] data = new byte[incoming.remaining()];
                        incoming.get(data);

                        System.out.println("readable=true");
                        System.out.println("text="
                                + new String(data, StandardCharsets.US_ASCII));
                    }
                }
            }
        }
    }
}
```

```bash
javac PipeSelectorDemo.java
java PipeSelectorDemo
```

Stdout **khi thao tác pipe và selector bình thường**:

```text
readable=true
text=ready
```

Luồng xử lý:

1. `Pipe.open()` tạo một cặp channel: `SinkChannel` để ghi và `SourceChannel` để đọc.
2. `source.configureBlocking(false)` cho phép đăng ký với selector.
3. `source.register(selector, SelectionKey.OP_READ)` yêu cầu thông báo khi phía đọc có dữ liệu.
4. Lệnh ghi `"ready"` vào `sink` khiến dữ liệu sẵn sàng cho `source`; `selector.select(3000)` đợi sự kiện tối đa 3 giây. Nếu môi trường không báo sự kiện trong thời gian ấy, ví dụ báo lỗi thay vì in kết quả.
5. Khi có key readable, `source.read(incoming)` vẫn cần trả về số byte thực đã đọc. `incoming.flip()` chỉ cho phép giải mã những byte đã nhận.

Nếu bỏ dòng `source.configureBlocking(false)`, việc đăng ký kênh đang blocking với `Selector` có thể dẫn tới `IllegalBlockingModeException`. Đây là ví dụ về **readiness thực sự**. Thay `Pipe.SourceChannel` bằng `FileChannel` sẽ không biên dịch tại dòng `register`.

## 7. Các cách làm đúng nếu muốn xử lý tệp mà không chờ trên luồng chính

“Không muốn block event loop” không đồng nghĩa “phải dùng `Selector`”. Tùy nhu cầu, có nhiều cách phù hợp hơn.

### Cách A: `AsynchronousFileChannel` (Java NIO.2)

`AsynchronousFileChannel` cung cấp các overload đọc/ghi với `Future<Integer>` hoặc `CompletionHandler<Integer, A>`. Bạn chỉ định offset trong tệp cho mỗi lệnh, nhận kết quả khi thao tác hoàn tất. Nó **không phải `SelectableChannel`** và vẫn không thể đăng ký vào `Selector`.

Đặc điểm:

- `AsynchronousFileChannel.read(dst, position)` trả `Future<Integer>`.
- Một overload khác nhận attachment và `CompletionHandler` để được gọi khi thành công/thất bại.
- Cơ chế triển khai của provider/JDK có thể dùng I/O bất đồng bộ của hệ điều hành hoặc thread pool. API không bảo đảm mọi filesystem hay JVM đều có native kernel async I/O.
- `Future.get()` chặn thread **đang gọi get** cho đến khi Future hoàn tất; vì vậy nếu muốn giữ thread chính không bị chặn, hãy tổ chức luồng công việc qua callback, completion hoặc một executor thích hợp.
- Kết quả `read` là số byte thực đã đọc; không mặc định mỗi lần đều đầy `ByteBuffer`. `-1` biểu thị EOF.

### Ví dụ Java 17+ hoàn chỉnh với `AsynchronousFileChannel`

Lưu thành **`AsyncFileReadDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

public class AsyncFileReadDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("async-file-", ".txt");

        try {
            Files.writeString(path, "HELLO", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel file =
                         AsynchronousFileChannel.open(
                                 path, StandardOpenOption.READ)) {

                ByteBuffer dst = ByteBuffer.allocate(5);
                long offset = 0;

                while (dst.hasRemaining()) {
                    Future<Integer> future = file.read(dst, offset);
                    int n = future.get(); // demo đợi kết quả tại đây

                    if (n == -1) {
                        break;
                    }
                    if (n == 0) {
                        throw new IllegalStateException(
                                "Read did not make progress");
                    }
                    offset += n;
                }

                dst.flip();
                byte[] result = new byte[dst.remaining()];
                dst.get(result);

                System.out.println("bytes=" + result.length);
                System.out.println("text="
                        + new String(result, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac AsyncFileReadDemo.java
java AsyncFileReadDemo
```

Stdout khi hoàn thành thành công:

```text
bytes=5
text=HELLO
```

Ở ví dụ học tập này, `future.get()` được gọi để quan sát completion dễ hiểu. Mô hình thật muốn giữ thread nhận request hoạt động không chặn thì **không gọi `get()` ngay trên event loop**; thay bằng cơ chế completion hoặc chuyển phần chờ sang executor. `AsynchronousFileChannel` không được biến thành một đối tượng có thể đăng ký selector chỉ vì tên chứa `Asynchronous`.

### Cách B: chạy file I/O trên worker thread

Nếu ứng dụng đang dùng event loop cho socket, nhưng đôi khi phải đọc tệp thông thường, bạn có thể chuyển các lệnh `FileChannel.read` / `write` sang một executor chuyên dụng và gửi kết quả xử lý về thành phần điều phối. Thread làm I/O vẫn có thể chờ, nhưng event loop không bị chiếm dụng bởi tác vụ file.

Trong Java 17, `ExecutorService` cùng `submit`/`Future` là cách nền tảng để minh họa. Bạn cần xác định kích thước pool, giới hạn số tác vụ chờ, timeout, xử lý hủy tác vụ, đóng channel và cách truyền kết quả an toàn. Đừng tạo vô hạn thread cho mọi byte/record hoặc dùng một pool không giới hạn khi dữ liệu đến nhanh hơn tốc độ ổ đĩa.

Cách này phù hợp khi bạn dùng một thư viện bắt buộc đọc file đồng bộ, không thể đổi sang API async một cách đơn giản.

### Cách C: `WatchService` để biết directory/file thay đổi

Nếu bài toán là “khi file log được sửa thì kiểm tra phần mới”, hãy tìm hiểu `java.nio.file.WatchService`:

- Đăng ký **thư mục** với `WatchService` bằng các event như `ENTRY_CREATE`, `ENTRY_MODIFY` và `ENTRY_DELETE`.
- Gọi `watcher.take()` hoặc `poll()` để lấy thông báo rồi kiểm tra các file có liên quan.
- Khi đã xác định nội dung cần đọc, dùng `FileChannel` hoặc API file phù hợp để lấy dữ liệu.

`WatchService` **không phải** là `Selector` cho nội dung file. Nó báo sự kiện thay đổi directory entry, có thể gộp sự kiện hoặc tràn hàng đợi (`OVERFLOW`), và hành vi phụ thuộc provider/filesystem. Bạn cần xác thực lại size, offset, trường hợp file bị xóa, đổi tên, truncate hoặc thay thế, cũng như khả năng sự kiện không đầy đủ trên mount từ xa.

Không thể suy ra “file đã có đủ một dòng log hoàn chỉnh” chỉ vì nhận được `ENTRY_MODIFY`; việc parse nội dung vẫn phải xử lý chunk chưa đủ và encoding.

### Cách D: đọc tệp bằng `FileChannel` đồng bộ khi thích hợp

Đối với CLI, batch job, import/export dữ liệu hoặc xử lý file theo block, một vòng `FileChannel.read(buffer)` đồng bộ thường là thiết kế đơn giản và đúng:

```java
try (FileChannel file =
             FileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(8192);

    while (true) {
        int n = file.read(buffer);
        if (n == -1) {
            break;
        }
        if (n == 0) {
            continue;
        }

        buffer.flip();
        while (buffer.hasRemaining()) {
            byte value = buffer.get();
            // Xử lý value.
        }
        buffer.clear();
    }
}
```

Đây là snippet cần khai báo `path`, các import và xử lý `IOException`. Với file đọc theo block, code có thể tiến bộ mà không cần selector. Nếu quy mô lớn, nên giải mã/xử lý `ByteBuffer` theo chunk hoặc API streaming phù hợp, không cấp phát bộ nhớ tỷ lệ với kích thước file.

## 8. File, pipe, socket và async: bảng quyết định

| Bài toán | API phù hợp | Có đăng ký `Selector`? |
| --- | --- | --- |
| Đọc/ghi file tại offset bất kỳ | `FileChannel` | Không |
| `map` file vào memory để đọc/truy cập ngẫu nhiên | `FileChannel.map` | Không |
| Khóa vùng trong file, `force` dữ liệu | `FileChannel.lock/force` | Không |
| Nhiều socket hoạt động với readiness | `SocketChannel` + `Selector` | Có, khi cấu hình nonblocking |
| Chấp nhận kết nối TCP | `ServerSocketChannel` + `Selector` | Có, `OP_ACCEPT` |
| Chuyển byte qua pipe trong process | `Pipe.SourceChannel/SinkChannel` | Có, theo operation hợp lệ |
| Đọc/ghi file với completion callback hoặc Future | `AsynchronousFileChannel` | Không |
| Được thông báo khi directory entry thay đổi | `WatchService` | Không; dùng `take/poll` |
| Gọi thư viện blocking nhưng giữ event loop rảnh | `FileChannel` + executor / tác vụ riêng | Không cần selector |

**Chú ý về terminology:** “Channel của NIO” là khái niệm rộng. Một loại channel là `FileChannel`, một số loại khác là `SelectableChannel`. Từ “NIO” không có nghĩa mọi thao tác đều nonblocking, cũng không có nghĩa mọi channel đều được dùng với selector.

## 9. Những hiểu nhầm kỹ thuật cần sửa

### Nhầm 1: “Cùng là `Channel` nên cast `FileChannel` thành `SelectableChannel` được”

Phép ép kiểu không cài đặt thêm interface. Object thực tế của `FileChannel.open` không phải selectable. Nếu phải chuyển sang `SelectableChannel` bằng ép kiểu cưỡng bức qua tham chiếu chung, thao tác sẽ thất bại bằng `ClassCastException` ở runtime. Cách sửa: lựa chọn đúng API ngay từ đầu.

### Nhầm 2: “`FileChannel` phải có `configureBlocking(false)` nếu import đúng”

`configureBlocking` là method của `SelectableChannel`. `FileChannel` không có method đó; lỗi biên dịch là hợp lý. Không tồn tại cờ nonblocking portable cho `FileChannel` theo cùng hợp đồng selector như socket.

### Nhầm 3: “File có dữ liệu nên selector luôn báo readable”

`FileChannel` không có `register` để tạo `SelectionKey`, nên không có sự kiện readable của file trên Java `Selector`. Nếu muốn biết file lớn thêm hoặc đổi nội dung, đọc metadata, theo dõi directory với `WatchService`, hoặc phối hợp bằng giao thức riêng.

### Nhầm 4: “`Selector` giúp file I/O chạy nhanh hơn”

Selector phục vụ multiplex readiness trên các kênh hỗ trợ; nó không phải một nút bật tốc độ đọc ổ đĩa. Với file lớn, hãy cân nhắc kích thước buffer, chiến lược access, `FileChannel.transferTo/transferFrom`, batching và đặc tính thiết bị. Cần đo đạc thực tế thay vì suy đoán từ chữ “nonblocking”.

### Nhầm 5: “`FileChannel.transferTo` luôn zero-copy, không cần lặp”

`transferTo(position, count, target)` có thể tận dụng tối ưu đặc thù provider/OS, nhưng Java không cam kết mọi đường đi đều là zero-copy hoặc một lần gọi truyền toàn bộ `count`. Kết quả là số byte **thực sự truyền**, có thể nhỏ hơn yêu cầu; khi xây vòng truyền hoàn chỉnh phải cập nhật offset và xử lý trường hợp không tiến triển.

Ví dụ `transferTo` nhận `position` làm offset đọc rõ ràng; không đồng nghĩa nhất thiết thay đổi `position()` của source channel theo lời gọi ấy. Phần file mapping/transfer cần được kiểm chứng riêng, không lấy làm bằng chứng file selectable.

### Nhầm 6: “`read()==-1` trên file nghĩa là không có dữ liệu mãi mãi”

Khi `FileChannel.read()` đọc tại EOF hiện tại, kết quả có thể là `-1`. Nhưng nếu một chương trình khác nối thêm dữ liệu vào tệp sau đó, việc đọc lại ở offset phù hợp có thể thấy byte mới. Với log rotation, file có thể bị truncate hoặc thay thế bằng file khác, và channel cũ có thể tiếp tục gắn với đối tượng file cũ. Ứng dụng tail file cần xử lý offset, size, identity, sự kiện và vòng đời tài nguyên; không có selector nào tự giải quyết điều đó.

### Nhầm 7: “`AsynchronousFileChannel` cũng dùng `Selector`”

`AsynchronousFileChannel` thuộc API asynchronous file I/O có `Future`/`CompletionHandler` và không extends `SelectableChannel`. Hai mô hình **completion** và **readiness** khác nhau:

```text
Readiness:
  Selector.select() -> kênh báo sẵn sàng -> ứng dụng thử read/write

Completion:
  AsynchronousFileChannel.read(...) -> thao tác được khởi động
                                     -> Future/CompletionHandler nhận kết quả
```

Không nhầm callback báo tác vụ file hoàn tất với `SelectionKey.OP_READ`.

### Nhầm 8: “Nếu tách file I/O sang thread khác thì hoàn toàn không block”

Kỹ thuật đó giữ **thread gọi/event loop** khỏi chờ trực tiếp, nhưng worker thread vẫn có thể block. Nếu số file operation không được giới hạn, pool và queue có thể quá tải. Cần bảo vệ tài nguyên, backpressure và xử lý lỗi.

## 10. Diễn giải đúng về I/O file và tiến trình đọc

Ví dụ một tiến trình đang ghi file log tăng dần:

```text
time t0: file size=100 bytes
time t1: reader position=100, read() -> -1
time t2: writer append thêm 30 bytes, size=130
time t3: reader có thể đọc bytes tại offset 100..129
```

Điểm cần thiết:

- EOF ở t1 là kết quả tại **thời điểm đó**.
- Tệp thông thường không có cơ chế `Selector.OP_READ` qua `FileChannel` để đợi 30 byte mới.
- Có thể theo dõi `size` định kỳ ở khoảng hợp lý hoặc dùng `WatchService` cho thông báo thay đổi thư mục, sau đó xác minh và đọc phần mới.
- Việc tự thiết kế tailer còn phải xử lý truncate (size giảm), rotation (file path trỏ tới inode/đối tượng khác theo OS), duplicate event, encoding và record chưa hoàn chỉnh.
- Phân biệt xử lý phản hồi HTTP/socket nonblocking với xử lý file log dạng append; hai loại tài nguyên cần chiến lược chờ khác nhau.

Vì `FileChannel` có `read(dst, position)` và `position(long)`, việc giữ offset chính xác là lợi thế. Việc theo dõi **khi nào** offset mới có dữ liệu là trách nhiệm của ứng dụng hoặc `WatchService`, chứ không đến từ `Selector`.

## 11. Kiểm tra kiến thức về `SelectionKey`

Một `SelectionKey` đại diện cho một đăng ký của **`SelectableChannel`** với một `Selector`. Nó có:

- `interestOps()`: tập hoạt động ứng dụng muốn được thông báo.
- `readyOps()` và `isReadable()/isWritable()/isAcceptable()/isConnectable()`: hoạt động mà lần chọn báo sẵn sàng.
- `channel()`: selectable channel được đăng ký.

Đối với kênh đang được đăng ký:

1. Chuyển nó sang nonblocking mode trước khi `register`.
2. Chỉ đăng ký operation nằm trong `channel.validOps()`. Nếu đăng ký bit không hợp lệ, API có thể ném `IllegalArgumentException`.
3. Sau `selector.select(...)`, duyệt `selectedKeys()` rồi loại key đã xử lý khỏi tập được chọn (như `it.remove()`), nếu không logic xử lý sau có thể gặp lại key.
4. Không đồng nhất ready với đã thực hiện I/O; vẫn cần `read/write` và kiểm tra giá trị trả về.
5. Đóng channel hoặc hủy key cần được quản lý cùng tài nguyên ứng dụng.

Các quy tắc này **chỉ áp dụng cho channel selectable**; `FileChannel` không có `SelectionKey` để đem đi kiểm tra.

## 12. Lưu ý về kiểm thử và hiệu năng

Với một chức năng dùng `FileChannel`:

- Viết kiểm thử đọc/ghi một tệp tạm theo byte và offset cụ thể; kiểm tra `size()`, `position()`, EOF, partial transfer khi phù hợp.
- Không viết test mong `FileChannel` hỗ trợ `OP_READ`; xác nhận nó **không** selectable là một thuộc tính ổn định ở tầng API.
- Không dùng số lần `read/write` hay tốc độ máy phát triển làm bảo đảm xử lý trên mọi filesystem.
- Nếu kiểm thử bất đồng bộ, kiểm tra cả thành công, lỗi, hủy, timeout và vấn đề thứ tự; đừng dựa vào tốc độ hoàn thành cố định.
- Đảm bảo dọn `Path` tạm sau khi đóng mọi channel; đặc biệt trên Windows, file còn mở có thể ảnh hưởng khả năng xóa.
- Tải dữ liệu file lớn theo chunk hữu hạn, tránh nạp tất cả vào `byte[]` một lần; đo đạc trước khi tối ưu.
- Với dữ liệu cần độ bền khi ghi, `FileChannel.force(metaData)` có hợp đồng đồng bộ cập nhật tới thiết bị lưu trữ theo khả năng hệ thống, nhưng có các giới hạn về thiết bị, provider và filesystem. Đây là tính năng file channel, không liên quan selector.

## 13. Câu hỏi tự kiểm tra

1. Vì sao một `FileChannel` có `read(ByteBuffer)` nhưng không gọi được `register(selector, OP_READ)`?
2. `FileChannel` và `SocketChannel` có cùng interface `ReadableByteChannel` trong những trường hợp nào? Điều đó có đủ để cả hai selectable không?
3. Khi nào bạn dùng `FileChannel.position(100)`, và khi nào cần một `SelectionKey.OP_READ`? Hai khái niệm trả lời những câu hỏi gì khác nhau?
4. Nếu có 10.000 kết nối TCP, lựa chọn giữa `Selector` và 10.000 `FileChannel` có ý nghĩa gì? Vì sao cách đặt câu hỏi “tối ưu file bằng selector” bị nhầm phạm vi?
5. Muốn nhận thông báo một file log vừa đổi, bạn có thể dùng `WatchService` thế nào, và vì sao vẫn cần kiểm tra file sau khi nhận event?
6. `AsynchronousFileChannel.read(dst, offset)` trả gì? `Future.get()` được gọi trên event loop có còn lợi ích “không chặn” không?
7. Nếu `transferTo` chỉ truyền một phần byte được yêu cầu, ứng dụng phải làm gì trước khi kết luận đã sao chép file xong?
8. `Pipe.SourceChannel` cần gọi gì trước khi đăng ký selector? Có thể áp dụng cùng method đó cho `FileChannel` không?
9. Nếu `FileChannel.read()` trả `-1` nhưng tác giả file tiếp tục append, EOF đó có còn đúng vĩnh viễn không?
10. Sự khác nhau giữa **readiness** và **completion** trong mô hình NIO là gì?

## 14. Tài liệu tham khảo Java SE 17

- [`FileChannel` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): file position, scattering/gathering I/O, transfer, map, lock, force.
- [`SelectableChannel` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): `register`, `configureBlocking`, `validOps`.
- [`Selector` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): chọn readiness của selectable channel.
- [`AsynchronousFileChannel` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): file read/write với `Future` và `CompletionHandler`.
- [`WatchService` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): theo dõi thay đổi directory.

## 15. Ghi nhớ

**`FileChannel` là channel thao tác tệp, không phải `SelectableChannel`.** Nó hỗ trợ `ByteBuffer`, file position, random access, transfer và các tính năng riêng của file, nhưng không thể `configureBlocking(false)` hay `register` với `Selector`. **`Selector`** được dùng cùng các channel thực sự selectable như `SocketChannel`, `ServerSocketChannel` và `Pipe.SourceChannel`.

Nếu cần xử lý file mà không chặn luồng chính, có thể cân nhắc `AsynchronousFileChannel` hoặc chuyển `FileChannel` sang worker thread. Nếu cần thông báo file được sửa, `WatchService` hoặc cơ chế theo dõi phù hợp là hướng giải quyết. Hãy chọn API theo loại tài nguyên và kiểu tín hiệu cần nhận: **offset/size của file**, **readiness của socket/pipe**, **completion của thao tác async** hay **sự kiện thay đổi thư mục**.
