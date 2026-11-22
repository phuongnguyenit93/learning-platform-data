# Đóng channel, khả năng ngắt và tài nguyên bên dưới trong Java NIO

## 1. Channel là tài nguyên có vòng đời

Trong `java.nio.channels`, một **channel** đại diện cho kết nối tới nguồn hoặc đích I/O như tệp, socket, pipe. Ví dụ: `FileChannel`, `SocketChannel`, `ServerSocketChannel`, `Pipe.SourceChannel` và `Pipe.SinkChannel`. Một channel thường giữ hoặc điều phối **tài nguyên hệ điều hành** như file descriptor, socket handle, file lock, vùng đệm và các thao tác I/O đang chờ.

Vì thế, sử dụng channel đúng không chỉ là gọi `read`/`write`: còn phải xác định **ai sở hữu và chịu trách nhiệm đóng**, hành vi khi **một luồng khác đóng trong lúc đang đọc/ghi**, và chuyện gì xảy ra khi **thread bị interrupt**.

Các điểm cốt lõi:

1. `Channel.close()` kết thúc vòng đời channel; sau đó `isOpen()` là `false` và các thao tác I/O tiếp theo không còn hợp lệ.
2. `InterruptibleChannel` bổ sung hợp đồng đặc biệt khi đang bị chặn trong I/O: close từ luồng khác thường dẫn tới `AsynchronousCloseException`; interrupt luồng thực hiện I/O dẫn tới `ClosedByInterruptException` **và đóng channel**.
3. Đóng channel không đồng nghĩa tự động đóng mọi tài nguyên **độc lập** liên quan: ví dụ vùng nhớ `MappedByteBuffer` đã map có vòng đời riêng; một socket bị đóng cũng không tự đóng các đối tượng tài nguyên khác của ứng dụng.
4. `close()` là thao tác quản lý tài nguyên, không phải phương thức đảm bảo dữ liệu đã được đồng bộ bền vững xuống thiết bị hoặc đảm bảo toàn bộ công việc logic thành công.

Bài này tập trung **vòng đời channel, interruptibility và sở hữu tài nguyên**, không đi sâu thuật toán multiplexing `Selector` hoặc giao thức mạng.

## 2. Hợp đồng cơ bản của Channel

Giao diện `Channel` mở rộng `java.io.Closeable`, nên cũng là `AutoCloseable`. Hai phương thức chung:

~~~java
boolean isOpen();
void close() throws IOException;
~~~

Hợp đồng Java 17 nêu rõ:

- Channel ở trạng thái **open** ngay sau khi tạo thành công. Khi đã closed, nó **không mở lại** được. Muốn tiếp tục I/O, phải tạo một channel mới.
- Các thao tác I/O trên channel đã đóng sẽ gây `ClosedChannelException` (hoặc ngoại lệ dẫn xuất trong tình huống liên quan).
- `close()` có thể được gọi nhiều lần: nếu đã đóng thì lần gọi sau **không có tác dụng**. Nếu một luồng khác đang thực hiện `close()`, lời gọi đóng tiếp theo có thể đợi đến khi lần trước hoàn tất.
- `close()` được phép ném `IOException` nếu có lỗi khi đóng hoặc giải phóng tài nguyên.
- `isOpen()` phản ánh trạng thái **ngay lúc kiểm tra**. Giữa `if (channel.isOpen())` và `channel.read(...)`, luồng khác vẫn có thể đóng channel.

Bởi vậy, `isOpen()` phù hợp để quan sát trạng thái hoặc debug; **không thể thay cho `try/catch` và kiểm soát vòng đời** trong mã chạy đồng thời.

Ví dụ đóng channel sở hữu bởi phạm vi hiện tại:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    // Đọc hoặc xử lý tệp khi channel còn open.
} // tự gọi channel.close(), kể cả khi thân try ném exception
~~~

Đây là **đoạn mã minh họa trong một phương thức**, với biến `Path path` đã được xác định. Với Java 7+, `try-with-resources` là cách thông thường để đóng channel do phạm vi này sở hữu. Nếu thân `try` và lời gọi `close()` đều lỗi, exception khi đóng sẽ được ghi vào danh sách **suppressed exceptions** của exception chính; không nên nuốt cả hai lỗi.

## 3. Ba ngoại lệ đóng channel thường bị nhầm

Các ngoại lệ này có quan hệ kế thừa:

~~~text
IOException
└── ClosedChannelException
    └── AsynchronousCloseException
        └── ClosedByInterruptException
~~~

| Trường hợp | Ngoại lệ đặc trưng | Ý nghĩa |
|---|---|---|
| Thực hiện I/O **sau khi channel đã đóng** | `ClosedChannelException` | Channel không còn được phép dùng cho I/O |
| Một luồng đang **bị chặn trong I/O**, luồng khác đóng `InterruptibleChannel` | `AsynchronousCloseException` | I/O bị kết thúc vì channel được đóng bất đồng bộ |
| Một luồng đang **bị chặn trong I/O** trên `InterruptibleChannel`, luồng khác gọi `interrupt()` lên nó | `ClosedByInterruptException` | Interrupt đóng channel và đánh dấu interrupt flag của thread |

**Lưu ý về kế thừa:** `ClosedByInterruptException` là lớp con của `AsynchronousCloseException`, và cả hai đều là `ClosedChannelException`. Nếu cần phân biệt nguyên nhân, bắt ngoại lệ **cụ thể trước**:

~~~java
try {
    channel.read(target); // đoạn minh họa, channel/target đã được tạo
} catch (ClosedByInterruptException ex) {
    // Thread bị interrupt trong I/O; channel đã đóng.
} catch (AsynchronousCloseException ex) {
    // Một thread khác đã đóng channel khi I/O đang diễn ra.
} catch (ClosedChannelException ex) {
    // Channel đã đóng trước lời gọi I/O hoặc tại thời điểm dùng.
} catch (IOException ex) {
    // Các lỗi I/O khác.
}
~~~

Khai báo `catch (ClosedChannelException)` đầu tiên sẽ làm các nhánh con phía sau trở thành **unreachable catch** và không biên dịch được.

Ngoại lệ thực tế chịu ảnh hưởng bởi **thời điểm cạnh tranh**: nếu một luồng đóng channel trước khi luồng khác bắt đầu `read`, `ClosedChannelException` có thể xuất hiện thay vì `AsynchronousCloseException`. Hãy đọc API theo điều kiện “**đang bị chặn** trong I/O” trước khi khẳng định một ngoại lệ luôn xuất hiện.

## 4. Channel nào thực sự hỗ trợ interrupt và asynchronous close?

`java.nio.channels.InterruptibleChannel` là giao diện mở rộng `Channel`. Hợp đồng của nó đặc biệt quan trọng khi một phương thức có thể **block vô thời hạn** để chờ dữ liệu hoặc tài nguyên.

Ví dụ các loại hỗ trợ giao diện này trong Java 17:

- `FileChannel`.
- `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`.
- `Pipe.SourceChannel` và `Pipe.SinkChannel`.
- Các subclass của `AbstractInterruptibleChannel` phù hợp.

Kiểm tra tại runtime khi cần:

~~~java
boolean interruptible = channel instanceof InterruptibleChannel;
~~~

Đây là **đoạn mã minh họa** với biến `channel` đã tồn tại. **Không được suy luận mọi lớp triển khai `Channel` đều hỗ trợ chính xác semantics interrupt như `InterruptibleChannel`.** Ví dụ những asynchronous channels có mô hình tác vụ `Future` / `CompletionHandler` và vòng đời đặc thù phải đọc hợp đồng riêng.

### 4.1. Close từ một luồng khác

Giả sử thread A đang chờ `source.read(buffer)` và thread B gọi `source.close()`. Với một `InterruptibleChannel` đang thực sự bị chặn:

1. Close kết thúc channel và khiến thao tác chờ trả về bằng cách ném `AsynchronousCloseException`.
2. `isOpen()` trở thành `false`.
3. Đây **không phải** thao tác interrupt thread A và bản thân `close()` không có nghĩa là đặt interrupt flag của thread A.

Nếu thread A chưa kịp vào thao tác chặn, nó có thể thấy `ClosedChannelException`. Kết quả chi tiết khác nhau theo tiến độ và loại channel, nên logic ứng dụng cần xử lý ngoại lệ chung một cách đúng đắn.

### 4.2. Interrupt luồng đang chờ I/O

Với thread A đang chờ I/O qua `InterruptibleChannel`, thread B gọi:

~~~java
readerThread.interrupt();
~~~

Hợp đồng gồm **ba hiệu ứng gắn với nhau**:

1. Channel đang được sử dụng bị **đóng**.
2. Thread A nhận `ClosedByInterruptException`.
3. **Interrupt flag** của thread A được đặt thành `true`.

Đây không phải lỗi chỉ có thể “bắt rồi đọc tiếp trên cùng channel”. Sau `ClosedByInterruptException`, channel đó đã hỏng vòng đời và cần **tạo kênh mới** nếu muốn I/O lần sau.

Nếu interrupt flag đã được set **trước khi** thread bắt đầu một thao tác blocking I/O trên `InterruptibleChannel`, channel cũng sẽ bị đóng và lời gọi lập tức có thể ném `ClosedByInterruptException`. Điều này giải thích vì sao “đợi chắc chắn đã block mới interrupt” không cần thiết trong ví dụ dùng Pipe ở mục 6.

Ngược lại, `Thread.sleep()`, `Object.wait()` hoặc `BlockingQueue.take()` thường làm việc với `InterruptedException`, và những API này có semantics về interrupt flag khác. **Không gộp `InterruptedException` và `ClosedByInterruptException` làm một hành vi.**

### 4.3. Đừng tự xóa interrupt flag mà không có chủ đích

`Thread.interrupted()` là phương thức tĩnh kiểm tra **và xóa** interrupt flag của luồng hiện tại. `Thread.currentThread().isInterrupted()` đọc flag **không xóa**.

Vì `ClosedByInterruptException` đã đóng channel, phản ứng phù hợp thường là kết thúc tác vụ/ghi nhận cancellation và đóng những tài nguyên khác do tác vụ sở hữu. Không nên liên tục thử lại cùng channel vì nó đã closed. Khi bắt `InterruptedException` ở API khác, thường cần phục hồi interrupt flag nếu tầng hiện tại không thực sự xử lý cancellation; với `ClosedByInterruptException`, theo hợp đồng flag vốn đã được đặt.

## 5. Tài nguyên bên dưới và quan hệ sở hữu

**Đóng một channel** thường giải phóng kết nối/handle mà channel đang quản lý. Nhưng câu “đóng channel giải phóng mọi thứ” không đúng cho mọi quan hệ tài nguyên.

### 5.1. FileChannel, descriptor, stream và RandomAccessFile

`FileChannel` có thể được tạo bởi `FileChannel.open(...)` hoặc lấy từ `FileInputStream.getChannel()`, `FileOutputStream.getChannel()`, `RandomAccessFile.getChannel()`.

- Với `FileChannel.open(...)`, phạm vi tạo channel thường là **chủ sở hữu** và nên đóng bằng `try-with-resources`.
- Với `FileInputStream.getChannel()` hoặc `FileOutputStream.getChannel()`, channel và stream liên kết tới **cùng tệp và file position**. Đóng stream cũng đóng channel liên quan; đóng channel liên quan cũng ảnh hưởng stream gốc. Không được dùng đối tượng còn lại để I/O như thể tài nguyên vẫn độc lập.
- Với `RandomAccessFile.getChannel()`, file position và dữ liệu cũng liên hệ với `RandomAccessFile`; đóng đối tượng gốc hay associated channel ảnh hưởng đối tượng còn lại.

Ví dụ ý tưởng:

~~~java
try (FileInputStream input = new FileInputStream(file)) {
    FileChannel fc = input.getChannel();
    // input và fc không phải hai tài nguyên I/O hoàn toàn độc lập.
} // input.close() cũng đóng fc
~~~

**Đoạn mã minh họa**, biến `File file` cần tồn tại. Không được cấp quyền sở hữu đóng cả stream lẫn channel cho hai thành phần chạy độc lập mà không có thỏa thuận vì một bên có thể làm bên kia bất ngờ nhận `ClosedChannelException`.

### 5.2. SocketChannel và half-close

Đóng `SocketChannel` chấm dứt channel/socket connection mà nó đại diện. Nhưng đôi khi giao thức cần dừng **một chiều** mà vẫn để chiều kia hoạt động:

- `SocketChannel.shutdownOutput()`: kết thúc phần ghi của kết nối TCP (thông thường peer có thể nhận EOF sau khi dữ liệu đã gửi hết).
- `SocketChannel.shutdownInput()`: kết thúc phần đọc.
- `SocketChannel.close()`: đóng toàn bộ channel, không tương đương với chỉ shutdown một chiều.

Đây là tính năng riêng của socket, không áp dụng cho mọi channel. Nếu dùng `SocketChannel.socket()` để lấy đối tượng `Socket` liên kết, hãy hiểu rằng hai API cùng biểu diễn một kết nối và việc đóng phía này có thể làm phía kia không còn sử dụng được.

### 5.3. Pipe gồm hai channel

`Pipe.open()` tạo `Pipe.SourceChannel` và `Pipe.SinkChannel` **riêng biệt**. `SourceChannel` để đọc; `SinkChannel` để ghi. Chúng có vòng đời riêng:

- Đóng source **không tự đóng** sink do ứng dụng nắm giữ.
- Đóng sink làm bên đọc quan sát trạng thái kết thúc pipe khi không còn dữ liệu, theo hành vi của pipe/provider.
- Cần đóng **cả hai đầu** mà ứng dụng sở hữu; chỉ đóng một đầu sẽ để lại tài nguyên ở đầu kia.

Ví dụ chạy ở mục 6 sử dụng `try-with-resources` cho cả source và sink. Khi một thread bị interrupt và source đóng, sink vẫn phải được ứng dụng đóng sau đó.

### 5.4. File mapping tồn tại riêng với FileChannel

`MappedByteBuffer` được tạo bởi `FileChannel.map(...)` là một vùng **memory-mapped file**. Theo tài liệu Java 17, **mapping được thiết lập không phụ thuộc vào việc FileChannel còn open hay không**. Đóng `FileChannel` **không tự làm mapping vô hiệu**; mapping còn hiệu lực cho đến khi buffer được thu hồi, với các hạn chế phụ thuộc hệ điều hành (file bị truncate, vùng nhớ không còn hợp lệ, ...).

Hệ quả thực tiễn:

- Đóng channel **không đảm bảo giải phóng ngay toàn bộ native memory / file mapping**.
- Trên một số OS, mapping còn sống có thể khiến việc đổi tên hoặc xóa tệp gặp hạn chế.
- Nếu thay đổi nội dung qua mapped buffer cần yêu cầu flush, hãy tìm hiểu `MappedByteBuffer.force()`; `FileChannel.force(...)` không được bảo đảm flush mọi thay đổi thực hiện qua mapping.
- Không dựa vào `System.gc()` để có lịch giải phóng mapping xác định.

Ví dụ:

~~~java
MappedByteBuffer mapped;
try (FileChannel fc = FileChannel.open(path, StandardOpenOption.READ)) {
    mapped = fc.map(FileChannel.MapMode.READ_ONLY, 0, fc.size());
}
// fc đã closed; mapping là tài nguyên có vòng đời riêng.
~~~

**Mã minh họa**: yêu cầu file và kích thước hợp lệ; các cách truy cập `mapped` sau đó vẫn phải tính tới các điều kiện OS và thay đổi ở file gốc. Không phải chương trình độc lập.

### 5.5. FileLock và Selector

- `FileLock` do `FileChannel.lock()` hoặc `tryLock()` tạo là tài nguyên cần quản lý. Đóng file channel làm các lock của channel đó không còn hợp lệ; cũng có thể dùng `FileLock.release()`/`close()` theo hợp đồng.
- `SelectableChannel` có thể đăng ký với `Selector`. Đóng channel làm các selection key tương ứng bị hủy; nhưng **Selector là tài nguyên riêng**, phải được đóng bởi thành phần sở hữu nó.
- `Selector.wakeup()` đánh thức thread đang chờ ở `select()`; đó là cơ chế điều phối, **không phải** thay thế cho `channel.close()` hoặc `selector.close()`.

Một thiết kế server thường có trách nhiệm đóng rõ ràng cho socket channel, selector, task executor và các tài nguyên liên quan. Đóng duy nhất một socket không đồng nghĩa executor hoặc selector của server tự dừng.

## 6. Chương trình Java 17+ chạy được: interrupt và channel đóng

Ví dụ dùng `Pipe.SourceChannel` có hỗ trợ `InterruptibleChannel`. Không gửi byte nào vào pipe nên thread đọc sẽ cần chờ. Thread chính gửi interrupt và đợi thread đọc kết thúc trước khi kiểm tra trạng thái.

**Tệp: `ChannelLifecycleDemo.java`**

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.Pipe;
import java.util.concurrent.CountDownLatch;

public class ChannelLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            CountDownLatch started = new CountDownLatch(1);
            Thread reader = new Thread(() -> {
                try {
                    started.countDown();
                    source.read(ByteBuffer.allocate(1));
                    System.out.println("reader: completed");
                } catch (ClosedByInterruptException ex) {
                    System.out.println("reader: ClosedByInterruptException");
                    System.out.println("reader interrupted: " +
                            Thread.currentThread().isInterrupted());
                } catch (IOException ex) {
                    System.out.println("reader: " +
                            ex.getClass().getSimpleName());
                }
            });

            reader.start();
            started.await();
            reader.interrupt();
            reader.join();

            System.out.println("source open: " + source.isOpen());

            try {
                source.read(ByteBuffer.allocate(1));
            } catch (ClosedChannelException ex) {
                System.out.println("later: ClosedChannelException");
            }

            sink.close();
            System.out.println("sink open: " + sink.isOpen());
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac ChannelLifecycleDemo.java
java ChannelLifecycleDemo
~~~

**Stdout:**

~~~text
reader: ClosedByInterruptException
reader interrupted: true
source open: false
later: ClosedChannelException
sink open: false
~~~

Giải thích:

1. `Pipe.open()` tạo hai channel. `source.read(...)` đọc 1 byte nhưng sink không gửi dữ liệu.
2. `started.await()` đảm bảo thread đọc đã đến đoạn sắp gọi `read`. Nếu interrupt đến trước khi thực sự block, hợp đồng `InterruptibleChannel` vẫn làm đóng channel khi blocking I/O bắt đầu với interrupt flag đã bật.
3. `reader.interrupt()` làm thread đọc nhận `ClosedByInterruptException`, interrupt flag `true`; source đã đóng.
4. Sau `join()`, thread chính kiểm tra `source.isOpen()` cho `false`. Lời gọi đọc tiếp nhận `ClosedChannelException` vì source đã đóng.
5. Đóng sink riêng biệt và in `sink.isOpen() == false`. Hai channel trong pipe có vòng đời riêng, và `try-with-resources` còn bảo đảm cleanup nếu có exception.

`CountDownLatch` làm bài toán có trật tự đủ rõ; chương trình không dựa vào `Thread.sleep(...)` hoặc thời gian thực thi tuyệt đối. Không sử dụng sleep để “chứng minh” kết quả ngắt theo một thời gian may rủi.

## 7. Asynchronous close từ thread khác: phân biệt với interrupt

Một trường hợp khác: thread A đang bị chặn ở `source.read(dst)`; thread B gọi `source.close()` thay vì `readerThread.interrupt()`.

Nếu thao tác đọc đã bị chặn trong `InterruptibleChannel`, thread A nhận `AsynchronousCloseException`. Đóng channel như vậy **không tự đặt interrupt flag** của A. Nếu A bắt đầu `read` sau khi channel đã bị đóng, có thể nhận `ClosedChannelException` trực tiếp.

Mô hình minh họa (không phải chương trình độc lập):

~~~java
// Thread A:
try {
    source.read(dst);
} catch (ClosedByInterruptException e) {
    // A bị interrupt, channel đóng, interrupt flag được set.
} catch (AsynchronousCloseException e) {
    // Thread khác đóng channel trong khi A đang ở blocking I/O.
}

// Thread B, khi muốn dừng I/O:
source.close();
~~~

Cách dừng phù hợp tùy thiết kế: `interrupt()` biểu thị yêu cầu hủy công việc của thread và có thể đóng các `InterruptibleChannel` đang được dùng; `close()` là hành động kết thúc **tài nguyên channel** mà nhiều tác vụ có thể đang chia sẻ. Không tùy tiện interrupt một worker đang sở hữu channel dùng chung nếu không định đóng channel đó.

## 8. Sự khác biệt với non-blocking mode và async channel

`SelectableChannel.configureBlocking(false)` cho phép một số channel như `SocketChannel`, `Pipe.SourceChannel` hoạt động **non-blocking**. Khi đó, `read` có thể trả `0` nếu hiện chưa có dữ liệu thay vì chờ. Điều này thay đổi cách tổ chức event loop nhưng **không loại bỏ vòng đời close** hay các ngoại lệ nếu channel bị đóng.

- Với non-blocking I/O, không nên kỳ vọng mọi lần gọi `interrupt` đều tạo `ClosedByInterruptException`: hợp đồng này nói tới **blocking I/O** trên `InterruptibleChannel`.
- `Selector.select()` có thể được đánh thức bằng `Selector.wakeup()` hoặc interrupt thread theo hợp đồng của Selector; đó là chuyện điều phối vòng lặp, không giống thread đang block trong `SocketChannel.read`.
- `AsynchronousFileChannel` và `AsynchronousSocketChannel` dùng `Future` hoặc `CompletionHandler`; cancel operation, close channel và interrupt worker không mặc nhiên đồng nghĩa. Phải đọc hợp đồng cụ thể của từng kiểu asynchronous channel.

Khi gặp I/O tưởng “treo”, trước tiên xác định đây là blocking channel operation, non-blocking event loop hay asynchronous task trước khi chọn cách dừng.

## 9. Quản lý tài nguyên và lỗi trong ứng dụng thực tế

### 9.1. Đặt quyền sở hữu rõ ràng

Một quy ước hữu ích:

| Ai tạo tài nguyên? | Ai nên đóng? | Ghi chú |
|---|---|---|
| Phương thức tự gọi `FileChannel.open` | Phương thức đó, qua `try-with-resources` | Trừ khi chuyển ownership rõ ràng |
| Service giữ channel dùng chung nhiều request | Service khi kết thúc vòng đời | Request không được tự ý đóng channel dùng chung |
| `FileInputStream` và `getChannel()` | Chủ sở hữu stream/channel liên kết | Cùng nguồn tài nguyên, đóng một bên ảnh hưởng bên còn lại |
| `Pipe.open()` | Chủ sở hữu pipe đóng cả source và sink | Hai channel riêng |
| Server giữ `Selector` và các socket channel | Server quản lý và đóng từng loại | Selector/executor không tự đóng khi socket đóng |

`Channels.newInputStream(channel)` và `Channels.newOutputStream(channel)` tạo adapter sang API stream; việc đóng adapter có liên quan đến channel bên dưới. Hãy đọc hợp đồng adapter trước khi trao quyền đóng cho thành phần khác, tránh “double ownership”.

### 9.2. Thực hiện shutdown có thứ tự

Với service đang giữ các task đọc/ghi, quy trình shutdown hợp lý có thể là:

1. Ngừng nhận tác vụ mới.
2. Báo hiệu dừng cho worker và đánh thức thread đang đợi ở tầng điều phối nếu cần.
3. Đóng channel mà service sở hữu để chấm dứt I/O đang chặn.
4. Đợi task kết thúc (có giới hạn thời gian và chính sách failure phù hợp); xử lý `AsynchronousCloseException` / `ClosedByInterruptException` như trạng thái shutdown nếu đó là điều đã chủ động yêu cầu.
5. Đóng những tài nguyên riêng khác: selector, streams, file locks, executor, mapping hoặc tài nguyên native được quản lý theo API tương ứng.

Không nên nuốt tất cả `IOException` một cách vô điều kiện: lỗi close xảy ra bất ngờ ngoài shutdown có thể chỉ ra mất dữ liệu hoặc sự cố backend.

### 9.3. Đóng không đồng nghĩa dữ liệu được lưu bền vững

`FileChannel.close()` giải phóng channel, nhưng nếu ứng dụng yêu cầu bảo đảm đẩy thay đổi xuống thiết bị, cần hiểu `FileChannel.force(boolean metaData)` và khả năng thực tế của file store. Trên thiết bị không phải local, Javadoc không bảo đảm mạnh tương đương. Nếu ghi qua `MappedByteBuffer`, xem `MappedByteBuffer.force()` cho phần dữ liệu thuộc mapping.

Ví dụ minh họa:

~~~java
try (FileChannel fc = FileChannel.open(path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {
    // Ghi dữ liệu qua fc.
    fc.force(true); // yêu cầu flush dữ liệu và metadata theo hợp đồng
}
~~~

**Mã minh họa** với biến `path` và thao tác ghi chưa trình bày. `force(true)` không biến một tập hợp thao tác file thành transaction nguyên tử và không tự bảo vệ trước lỗi logic ứng dụng.

### 9.4. Hết use-scope vẫn có thể còn tài nguyên độc lập

Nếu trả về một `MappedByteBuffer` từ một hàm đã đóng `FileChannel`, mapping vẫn có thể còn tồn tại. Nếu giữ các `ByteBuffer` thường chứa dữ liệu đã đọc, chúng là đối tượng riêng, không vì channel đóng mà bị “xóa” dữ liệu. Một `FileLock`, selector và các stream/socket liên kết lại tuân theo hợp đồng riêng của chúng.

Khi debug lỗi `Too many open files` hoặc leak native memory, kiểm tra cả vòng đời file/channel, socket/selector, mmap và các stream adapter, thay vì chỉ nhìn `isOpen()` của một đối tượng.

## 10. Những lỗi phổ biến cần tránh

1. **Nghĩ `isOpen()` là bảo đảm thao tác ngay sau sẽ thành công.** Thread khác có thể đóng trước khi I/O diễn ra.
2. **Nghĩ `close()` của mọi `Channel` luôn đánh thức mọi kiểu blocking operation như nhau.** Chỉ khẳng định các semantics interrupt/asynchronous close khi API kiểu tương ứng bảo đảm, đặc biệt `InterruptibleChannel`.
3. **Bắt `AsynchronousCloseException` trước `ClosedByInterruptException`.** Khi đó không thể có nhánh catch cụ thể cho subclass phía sau.
4. **Bắt `ClosedByInterruptException` rồi retry trên cùng channel.** Channel đã bị đóng; cần dừng hoặc mở lại channel mới.
5. **Dùng `Thread.interrupted()` chỉ để log.** Phương thức này xóa interrupt flag; dùng `isInterrupted()` nếu chỉ cần đọc.
6. **Đóng channel dùng chung từ request riêng.** Các request khác đang I/O có thể thất bại; quy định ownership ở cấp service.
7. **Cho rằng đóng FileChannel làm `MappedByteBuffer` bị vô hiệu.** Mapping có vòng đời độc lập.
8. **Bỏ quên đầu còn lại của Pipe hoặc Selector.** Chúng là tài nguyên riêng.
9. **Cho rằng đóng channel = flush bền vững.** Xem `FileChannel.force` / `MappedByteBuffer.force` và giới hạn provider.
10. **Biến mọi IOException thành “cancelled”.** Phân loại ngoại lệ theo bối cảnh shutdown, lỗi truy cập hoặc hỏng backend.

## 11. Câu hỏi tự kiểm tra

**Câu 1:** Thread A đang `read` một `InterruptibleChannel` và B gọi `A.interrupt()`. A nhận ngoại lệ gì, channel còn dùng tiếp được không?

**Đáp án:** `ClosedByInterruptException`; interrupt flag của A được set và channel đóng. Muốn tiếp tục I/O cần tạo channel mới.

**Câu 2:** Thread B gọi `channel.close()` khi A đang blocked trong I/O. Có đảm bảo A nhận đúng `AsynchronousCloseException` nếu chưa chắc A đã vào thao tác blocking chưa?

**Đáp án:** Khi A đang blocked theo hợp đồng `InterruptibleChannel` thì có. Nếu B đóng trước khi A gọi `read`, A có thể nhận `ClosedChannelException`. Phải xử lý race đúng.

**Câu 3:** Có thể tiếp tục dùng một `MappedByteBuffer` đã tạo sau khi đóng `FileChannel` không?

**Đáp án:** Theo Javadoc, mapping không phụ thuộc vòng đời FileChannel sau khi được tạo. Tuy vậy, hiệu lực truy cập còn chịu giới hạn OS và thay đổi trên file; việc đóng channel không giải phóng mapping ngay.

**Câu 4:** `isOpen() == true` có chứng minh lệnh `write` kế tiếp chắc chắn thành công không?

**Đáp án:** Không. Thread khác có thể đóng channel hoặc I/O có thể lỗi vì những nguyên nhân khác.

### Tài liệu chính thức (Java 17)

- [Channel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Channel.html)
- [InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html)
- [ClosedChannelException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedChannelException.html)
- [AsynchronousCloseException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html)
- [ClosedByInterruptException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedByInterruptException.html)
- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)
- [MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html)
- [Pipe](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Pipe.html)
